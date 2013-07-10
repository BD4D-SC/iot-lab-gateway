#include <stdint.h>
#include <string.h>


// TODO remove me when not printing measures anymore
#define __STDC_FORMAT_MACROS
#include <inttypes.h>
#include <stdio.h>
// TODO remove me when not printing measures anymore



#include <sys/time.h>

#include "common.h"

#include "constants.h"
#include "measures_handler.h"
#include "time_update.h"


struct power_vals {
        unsigned int time;
        float val[3];
};

static struct _measure_handler_state {
        struct timeval time_ref;
        struct {
                int p;
                int v;
                int c;
                int power_source;
                unsigned char conf;
                size_t raw_values_len;
        } power;

} mh_state;


static void handle_pw_pkt(unsigned char *data, size_t len)
{
        int num_measures;
        float p = 0.0, v = 0.0, c = 0.0;

        uint64_t t_s;
        uint32_t t_us;
        unsigned char *current_data_ptr;
        struct power_vals pw_vals;

        size_t values_len = mh_state.power.raw_values_len;

        num_measures     = data[1];
        current_data_ptr = &data[2];

        if ((values_len * num_measures + 2) != len) {
                DEBUG_PRINT("Invalid measure pkt len\n");
                return;
        }

        for (int j = 0; j < num_measures; j++) {
                int i = 0;
                memcpy(&pw_vals, current_data_ptr, values_len);
                current_data_ptr += values_len;

                t_s  = pw_vals.time / TIME_FACTOR;
                t_us = (1000000 * (pw_vals.time % TIME_FACTOR)) / TIME_FACTOR;

                if (mh_state.power.p)
                        p = pw_vals.val[i++];
                if (mh_state.power.v)
                        v = pw_vals.val[i++];
                if (mh_state.power.c)
                        c = pw_vals.val[i++];

                // Handle absolute time with  reference time
                fprintf(LOG, "%lu.%lu:%"PRIu64".%u: %f %f %f\n",
                                mh_state.time_ref.tv_sec, mh_state.time_ref.tv_usec, t_s, t_us, p, v, c);
        }
}

static void handle_ack_pkt(unsigned char *data, size_t len)
{
        (void) len;
        // sync | type | config_type | config
        uint8_t ack_type = data[1];
        uint8_t config   = data[2];

        switch (ack_type) {
                case RESET_TIME:
                        fprintf(LOG, "reset_time ACK frame\n");
                        memcpy(&mh_state.time_ref, &new_time_ref, sizeof(struct timeval));
                        break;
                case CONFIG_POWER_POLL:
                        fprintf(LOG, "config_consumption_measure ACK frame\n");
                        // cleanup for new configuration
                        memset(&mh_state.power, 0, sizeof(mh_state.power));

                        mh_state.power.conf = config;
                        mh_state.power.power_source = config &
                                (SOURCE_3_3V | SOURCE_5V | SOURCE_BATT);

                        mh_state.power.raw_values_len = sizeof(unsigned int);
                        if (config & MEASURE_POWER) {
                                mh_state.power.p = 1;
                                mh_state.power.raw_values_len += sizeof(float);
                        }
                        if (config & MEASURE_VOLTAGE) {
                                mh_state.power.v = 1;
                                mh_state.power.raw_values_len += sizeof(float);
                        }
                        if (config & MEASURE_CURRENT) {
                                mh_state.power.c = 1;
                                mh_state.power.raw_values_len += sizeof(float);
                        }
                        break;
                default:
                        fprintf(LOG, "EE Unkown ACK frame\n");
                        break;
        }
}


int handle_measure_pkt(unsigned char *data, size_t len)
{

        uint8_t pkt_type = data[0];
        (void) pkt_type;
        (void) len;

        switch (pkt_type) {
                case PW_POLL_FRAME:
                        handle_pw_pkt(data, len);
                        break;
                case RADIO_POLL_FRAME:
                        DEBUG_PRINT("NOT IMPLEMENTED RADIO POLL FRAME\n");
                        break;
                case ACK_FRAME:
                        handle_ack_pkt(data, len);
                        break;
                default:
                        return -1;
        }


        return 0;




}

