IVERILOG ?= iverilog
VVP ?= vvp
RTL := $(wildcard rtl/*.v)

.PHONY: test xrun waves
test: build/tb_top.vvp
	cd build && $(VVP) tb_top.vvp > simulation.log
	@cat build/simulation.log
	@! grep -Eq 'ERROR|TEST FAILED' build/simulation.log
	@grep -qx 'TEST PASSED' build/simulation.log

build/tb_top.vvp: $(RTL) tb/tb_top.v
	mkdir -p build
	$(IVERILOG) -g2001 -Wall -DDUMP_VCD -s tb_top -o $@ $(RTL) tb/tb_top.v

xrun:
	mkdir -p build/xcelium
	cd build/xcelium && xrun -access +rwc -top tb_top +define+DUMP_VCD ../../rtl/*.v ../../tb/tb_top.v
	@! grep -Eq 'ERROR|TEST FAILED' build/xcelium/xrun.log
	@grep -qx 'TEST PASSED' build/xcelium/xrun.log

waves:
	mkdir -p build/xcelium
	cd build/xcelium && xrun -access +rwc -top tb_top ../../rtl/*.v ../../tb/tb_top.v -input ../../scripts/xrun_waves.tcl
