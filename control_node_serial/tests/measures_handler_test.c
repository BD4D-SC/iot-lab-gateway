#include <gtest/gtest.h>

#include <math.h>
#include "mock_fprintf.h"  // include before other includes

#include "measures_handler.c"

#define OML_CONFIG_PATH "utils/oml_measures_config.xml"

static int start_called = 0;
int oml_measures_start(char *oml_config_file_path)
{
        start_called += 1;
        return 0;
}
int oml_measures_stop()
{
        return 0;
}

static int consumption_mock_called = 0;
static struct {
        uint64_t timestamp_s;
        uint32_t timestamp_us;
        double current;
        double voltage;
        double power;
} consumption_call_args;

void oml_measures_consumption(uint64_t timestamp_s, uint32_t timestamp_us,
                double power, double voltage, double current)
{
        consumption_call_args.timestamp_s = timestamp_s;
        consumption_call_args.timestamp_us = timestamp_us;
        consumption_call_args.current = current;
        consumption_call_args.voltage = voltage;
        consumption_call_args.power = power;
        consumption_mock_called +=1;
}
static int radio_mock_called = 0;
static struct {
        uint64_t timestamp_s;
        uint32_t timestamp_us;
        int32_t rssi;
        int32_t lqi;
} radio_call_args;
void oml_measures_radio(uint64_t timestamp_s, uint32_t timestamp_us,
                int32_t rssi, int32_t lqi)
{
        radio_call_args.timestamp_s = timestamp_s;
        radio_call_args.timestamp_us = timestamp_us;
        radio_call_args.rssi = rssi;
        radio_call_args.lqi = lqi;
        radio_mock_called +=1;
}


/*
 * Mock exit, mocking directly cause
 *     warning: 'noreturn' function does return [enabled by default]
 */

// handle_measure_pkt
TEST(handle_measure_pkt, test_different_packets)
{
        unsigned char data[64];
        int ret;
        data[0] = ACK_FRAME;
        ret = handle_measure_pkt(data, 0);
        ASSERT_EQ(ret, 0);

        data[0] = PW_POLL_FRAME;
        ret = handle_measure_pkt(data, 0);
        ASSERT_EQ(ret, 0);

        data[0] = RADIO_POLL_FRAME;
        ret = handle_measure_pkt(data, 0);
        ASSERT_EQ(ret, 0);

        // Invalid packet type
        data[0] = 0x00;
        ret = handle_measure_pkt(data, 0);
        ASSERT_NE(ret, 0);
}


// handle_pw_pkt
TEST(handle_pw_pkt, coverage_for_pw_pkt_different_configuration)
{
        unsigned char data[256];
        data[0] = ((char)PW_POLL_FRAME);
        data[1] = 2;
        struct power_vals power;
        size_t data_size;

        consumption_mock_called = 0;

        measures_handler_start(0, OML_CONFIG_PATH);
        mh_state.power.power_source = (char) SOURCE_3_3V;
        mh_state.power.is_valid = 1;
        mh_state.power.p = 1;
        mh_state.power.v = 1;
        mh_state.power.c = 1;
        data_size = sizeof(unsigned int) + 3*sizeof(float);
        mh_state.power.raw_values_len = data_size;

        power.time = (unsigned int) 0;
        power.val[0] = 1.0;
        power.val[1] = 2.0;
        power.val[2] = 3.0;
        memcpy(&data[2], &power, data_size);

        power.time = (unsigned int) TIME_FACTOR;  // 1sec in tics
        power.val[0] = 4.0;
        power.val[1] = 5.0;
        power.val[2] = 6.0;
        memcpy(&data[2 + data_size], &power, data_size);

        // num == 1
        data[1] = 1;
        handle_pw_pkt(data, 2 + data[1] * data_size);
        ASSERT_EQ(0, consumption_call_args.timestamp_s);
        ASSERT_EQ(0, consumption_call_args.timestamp_us);
        ASSERT_EQ(1.0, consumption_call_args.power);
        ASSERT_EQ(2.0, consumption_call_args.voltage);
        ASSERT_EQ(3.0, consumption_call_args.current);
        ASSERT_EQ(1, consumption_mock_called);

        // num == 2
        consumption_mock_called = 0;
        data[1] = 2;
        handle_pw_pkt(data, 2 + data[1] * data_size);
        ASSERT_EQ(1, consumption_call_args.timestamp_s);
        ASSERT_EQ(0, consumption_call_args.timestamp_us);
        ASSERT_EQ(4.0, consumption_call_args.power);
        ASSERT_EQ(5.0, consumption_call_args.voltage);
        ASSERT_EQ(6.0, consumption_call_args.current);
        ASSERT_EQ(2, consumption_mock_called);

        measures_handler_stop();



        consumption_mock_called = 0;
        measures_handler_start(1, OML_CONFIG_PATH); // print_measures == true for coverage
        // P + C
        mh_state.power.power_source = (char) SOURCE_3_3V;
        mh_state.power.is_valid = 1;
        mh_state.power.p = 1;
        mh_state.power.v = 0;
        mh_state.power.c = 1;
        data_size = sizeof(unsigned int) + 2*sizeof(float);
        mh_state.power.raw_values_len = data_size;
        data[1] = 1;
        handle_pw_pkt(data, 2 + data[1] * data_size);
        ASSERT_EQ(0, consumption_call_args.timestamp_s);
        ASSERT_EQ(0, consumption_call_args.timestamp_us);
        ASSERT_EQ(1.0, consumption_call_args.power);
        ASSERT_TRUE(isnan(consumption_call_args.voltage));
        ASSERT_EQ(2.0, consumption_call_args.current);

        ASSERT_EQ(1, consumption_mock_called);


        // only V
        mh_state.power.p = 0;
        mh_state.power.v = 1;
        mh_state.power.c = 0;
        data_size = sizeof(unsigned int) + 2*sizeof(float);
        mh_state.power.raw_values_len = data_size;
        data[1] = 1;
        handle_pw_pkt(data, 2 + data[1] * data_size);
        ASSERT_EQ(0, consumption_call_args.timestamp_s);
        ASSERT_EQ(0, consumption_call_args.timestamp_us);
        ASSERT_TRUE(isnan(consumption_call_args.power));
        ASSERT_EQ(1.0, consumption_call_args.voltage);
        ASSERT_TRUE(isnan(consumption_call_args.current));

        measures_handler_stop();
        ASSERT_EQ(2, consumption_mock_called);

        // No OML
        consumption_mock_called = 0;
        measures_handler_start(0, NULL);
        // P + C
        mh_state.power.power_source = (char) SOURCE_3_3V;
        mh_state.power.is_valid = 1;
        mh_state.power.p = 1;
        mh_state.power.v = 0;
        mh_state.power.c = 1;
        data_size = sizeof(unsigned int) + 2*sizeof(float);
        mh_state.power.raw_values_len = data_size;
        data[1] = 1;
        handle_pw_pkt(data, 2 + data[1] * data_size);
        measures_handler_stop();

        ASSERT_EQ(0, consumption_mock_called);
}

TEST(handle_pw_pkt, invalid_calls)
{
        unsigned char data[64];

        // measure packet when not configured
        measures_handler_start(0, OML_CONFIG_PATH);
        handle_pw_pkt(data, 0);
        ASSERT_STREQ("cn_serial_error: "
                        "Got PW measure without being configured\n",
                        print_buff);

        // invalid packet length received
        mh_state.power.raw_values_len = 4 + 3*4;
        mh_state.power.is_valid = 1;
        data[1] = 1; // num_measures
        int len = 10; // 4 + 1*4 + 2
        handle_pw_pkt(data, len);
        ASSERT_STREQ("cn_serial_error: "
                        "Invalid measure pkt len: 10 != expected 18\n",
                        print_buff);
        measures_handler_stop();
}


// handle_radio_measure_pkt
TEST(handle_radio_measure_pkt, coverage_for_pw_pkt_different_configuration)
{
        unsigned char data[256];
        data[0] = ((char)RADIO_POLL_FRAME);
        data[1] = 1;  // measure_count
        struct radio_measure_vals radio;
        size_t data_size = 6;

        measures_handler_start(0, OML_CONFIG_PATH);
        memset(print_buff, '\0', sizeof(print_buff));

        // first value
        radio.time = (unsigned int) 0;
        radio.rssi = -42;
        radio.lqi  = 66;
        memcpy(&data[2], &radio, data_size);

        // second value
        radio.time = (unsigned int) TIME_FACTOR;
        radio.rssi = 42;
        radio.lqi  = 0;
        memcpy(&data[2 + data_size], &radio, data_size);

        // num == 1
        radio_mock_called = 0;
        data[1] = 1;
        handle_radio_measure_pkt(data, 2 + data[1] * data_size);
        ASSERT_EQ(0, radio_call_args.timestamp_s);
        ASSERT_EQ(0, radio_call_args.timestamp_us);
        ASSERT_EQ(-42, radio_call_args.rssi);
        ASSERT_EQ(66, radio_call_args.lqi);
        measures_handler_stop();
        ASSERT_EQ(1, radio_mock_called);
        // num == 2
        radio_mock_called = 0;
        measures_handler_start(1, OML_CONFIG_PATH); // print_measures == true for coverage
        data[1] = 2;
        handle_radio_measure_pkt(data, 2 + data[1] * data_size);
        ASSERT_EQ(1, radio_call_args.timestamp_s);
        ASSERT_EQ(0, radio_call_args.timestamp_us);
        ASSERT_EQ(42, radio_call_args.rssi);
        ASSERT_EQ(0, radio_call_args.lqi);
        measures_handler_stop();
        ASSERT_EQ(2, radio_mock_called);

        // NO OML
        radio_mock_called = 0;
        measures_handler_start(0, NULL);
        handle_radio_measure_pkt(data, 2 + data[1] * data_size);
        measures_handler_stop();
        ASSERT_EQ(0, radio_mock_called);

}


// handle_ack_pkt
TEST(handle_ack_pkt, reset_time)
{
        unsigned char data[8];
        data[1] = RESET_TIME;
        data[2] = 0; // unused

        ASSERT_EQ(mh_state.time_ref.tv_sec, 0);
        ASSERT_EQ(mh_state.time_ref.tv_usec, 0);

        handle_ack_pkt(data, 3);

        ASSERT_NE(mh_state.time_ref.tv_sec, 0);
        ASSERT_NE(mh_state.time_ref.tv_usec, 0);
}

TEST(handle_ack_pkt, power_poll_ack)
{
        unsigned char data[8];
        data[1] = CONFIG_POWER_POLL;
        measures_handler_start(0, OML_CONFIG_PATH);

        // PC
        data[2]  = 0;
        data[2] |= SOURCE_BATT;
        data[2] |= MEASURE_POWER;
        data[2] |= MEASURE_CURRENT;
        handle_ack_pkt(data, 3);

        ASSERT_TRUE(mh_state.power.is_valid);
        ASSERT_EQ(1, mh_state.power.p);
        ASSERT_EQ(0, mh_state.power.v);
        ASSERT_EQ(1, mh_state.power.c);

        // V
        data[2]  = 0;
        data[2] |= SOURCE_3_3V;
        data[2] |= MEASURE_VOLTAGE;
        handle_ack_pkt(data, 3);

        ASSERT_TRUE(mh_state.power.is_valid);
        ASSERT_EQ(0, mh_state.power.p);
        ASSERT_EQ(1, mh_state.power.v);
        ASSERT_EQ(0, mh_state.power.c);

        measures_handler_stop();
}

TEST(handle_ack_pkt, radio_acks)
{
        unsigned char data[8];
        data[1] = CONFIG_RADIO;
        data[2] = 42;  // tx pow
        data[3] = 16;  // channel

        handle_ack_pkt(data, 3);
        ASSERT_STREQ("config_ack config_radio_signal\n", print_buff);


        data[1] = CONFIG_RADIO_POLL;
        data[2] = 1;  // state

        handle_ack_pkt(data, 2);
        ASSERT_STREQ("config_ack config_radio_measure\n", print_buff);

}

TEST(handle_ack_pkt, invalid_msgs)
{
        unsigned char data[8];
        data[1] = 0x00; // not a real ack type
        handle_ack_pkt(data, 3);
        ASSERT_STREQ("cn_serial_error: Unkown ACK frame 0x00\n", print_buff);
}

TEST(calculate_time, overflow_on_usec_sum)
{
        struct timeval time_final, time_ref;
        unsigned int cn_time;

        // sum of control node u_seconds and time_ref u_seconds
        // is bigger than 1 second, so it should be seen in 'seconds'
        cn_time = (TIME_FACTOR -1);
        time_ref.tv_sec = 0;
        time_ref.tv_usec = 999999;
        calculate_time(&time_final, &time_ref, cn_time);
        ASSERT_EQ(1, time_final.tv_sec);
}


// init_measures_handler
TEST(init_measures_handler, test)
{
        mh_state.time_ref.tv_sec = 0xDEAD;
        mh_state.time_ref.tv_usec = 0xBEEF;
        mh_state.power.is_valid = 42;
        start_called = 0;
        measures_handler_start(0, OML_CONFIG_PATH);
        ASSERT_EQ(0, mh_state.time_ref.tv_sec);
        ASSERT_EQ(0, mh_state.time_ref.tv_usec);
        ASSERT_EQ(0, mh_state.power.is_valid);
        measures_handler_stop();
        ASSERT_EQ(1, start_called);

        // cover case init not called
        start_called = 0;
        measures_handler_start(0, NULL);
        measures_handler_stop();
        ASSERT_EQ(0, start_called);
}
