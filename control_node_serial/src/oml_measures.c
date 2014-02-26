#include <stdio.h>
#include <oml2/omlc.h>
#define OML_FROM_MAIN
#include "control_node_measures_oml.h"

#include "oml_measures.h"
#include "common.h"

int oml_measures_start(char *oml_config_file_path)
{
        int result;
        const char *argv[] = {
                "argv0",
                "--oml-log-level", "-2",  // log only errors
                "--oml-log-file", "/tmp/oml.log",
                "--oml-config", oml_config_file_path
        };
        int argc = (sizeof(argv) / sizeof(char *));

        result = omlc_init("control_node_measures", &argc, argv, NULL);
        if (result == -1) {
                PRINT_ERROR("omlc_init failed: %d\n", result);
                return result;
        }

        oml_register_mps();

        result = omlc_start();
        if (result == -1) {
                PRINT_ERROR("omlc_start failed: %d\n", result);
                return result;
        }
        return 0;
}


void oml_measures_consumption(uint32_t timestamp_s, uint32_t timestamp_us,
                              double power, double voltage, double current)
{
        oml_inject_consumption(g_oml_mps_control_node_measures->consumption,
                               timestamp_s, timestamp_us,
                               power, voltage, current);
}

void oml_measures_radio(uint32_t timestamp_s, uint32_t timestamp_us,
                        uint32_t channel, int32_t rssi)
{
        oml_inject_radio(g_oml_mps_control_node_measures->radio,
                         timestamp_s, timestamp_us, channel, rssi);
}


int oml_measures_stop(void)
{
        return omlc_close();
}
