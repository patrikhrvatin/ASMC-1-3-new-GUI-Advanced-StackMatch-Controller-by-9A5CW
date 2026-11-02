# ASMC-1-3-new-GUI-Advanced-StackMatch-Controller-by-9A5CW
![ASMC RX Stanje](asmc_rx.png)
# ASMC 1-3 (Advanced StackMatch Controller)

An advanced, microcontroller-based antenna stacking and matching controller designed for amateur radio operators. The system utilizes an **Arduino Nano** paired with a custom Python/CustomTkinter GUI for seamless remote operation, hardware safety sequencing, and robust relay management based on the classic **SJ2W** architectural model.

---

## Features & Capabilities

* **Dual-Band Antenna Control:** Independent management of up to 3 RX and 3 TX antenna ports, supporting single or multiple simultaneous antenna selections.
* **Flexible & Exclusive Modes:** 
  * `EXCL` (Exclusive): Standard radio switching where selecting one antenna deselects others.
  * `FLEX` (Flexible/Multi): Allows combining multiple antennas simultaneously.
* **Dual-Stage PTT Sequencer:** Built-in hardware timing protection to safeguard sensitive devices (LNAs and Power Amplifiers) during TX/RX transitions:
  * **TX Pre-Delay (20 ms):** Safe switching of RF relays before power is applied.
  * **Stage-2 Delay (20 ms):** Safe sequential keying of linear amplifiers (`PTT_OUT2`).
  * **Tail Delay (80 ms):** Ensures residual RF energy clears before returning to RX state.
* **Resistor Ladder Architecture:** Optimized analog input management allowing 4 distinct physical buttons to be read reliably over a single analog pin (`A6` for TX, `A7` for RX).
* **Galvanic Isolation:** Safe PTT keying via an **PC817 optocoupler** to protect the microcontroller from RF feedback and ground loops.
* **EEPROM State Retention:** Lazy-write EEPROM storage to remember the last used antenna configurations and operating modes across power cycles.
* **Watchdog Safety:** Integrated 2-second watchdog timer (`WDT`) to automatically recover from any software lockups.
* **Interactive Python GUI:** Cross-platform desktop interface featuring real-time bi-directional status synchronization over a serial (COM) port.

---

## Hardware Pinout & Component Mapping

| Pin / Line | Component / Function | Description / Connection |
| :--- | :--- | :--- |
| **Pin 2** | `RELAY_1` | StackMatch Relay 1 (Active Low / Driver) |
| **Pin 3** | `RELAY_2` | StackMatch Relay 2 (Active Low / Driver) |
| **Pin 4** | `RELAY_3` | StackMatch Relay 3 (Active Low / Driver) |
| **Pin 5** | `RELAY_4` | StackMatch Relay 4 (Automatic stacking logic for multi-antennas) |
| **Pin 9** | `LED_TX_A` | Status LED for TX Antenna A |
| **Pin 10** | `LED_TX_B` | Status LED for TX Antenna B |
| **Pin 13** | `LED_TX_C` / Onboard LED | Status LED for TX Antenna C (shares Arduino built-in LED) |
| **Pin A1** | `LED_RX_A` | Status LED for RX Antenna A |
| **Pin A2** | `LED_RX_B` | Status LED for RX Antenna B |
| **Pin A3** | `LED_RX_C` | Status LED for RX Antenna C |
| **Pin A0** | `PTT_OUT2` | Sequencer Output 2 (Active Low, e.g., Linear Amplifier / PA) |
| **Pin A4** | `PTT_PIN` | PTT Input from Transceiver (Active Low via PC817 Optocoupler) |
| **Pin A5** | `BTN_RX_MODE` | Pushbutton to toggle between `EXCL` and `FLEX` modes |
| **Pin A6** | `LADDER_PIN` | Analog input for TX Resistor Ladder (4 buttons: A, B, C, ALL) |
| **Pin A7** | `RX_LADDER_PIN` | Analog input for RX Resistor Ladder (4 buttons: A, B, C, ALL) |
| **Pin 11** | `PTT_OUT1` | Sequencer Output 1 (Active Low, e.g., LNA / Coaxial Relay) |

---

## Component Wiring Guide

### 1. Resistor Ladders (TX on A6, RX on A7)
To minimize pin usage, each group of 4 physical buttons uses a resistor ladder configuration:
* **Top Pull-up Resistor:** 10kohm connected between the analog pin (`A6`/`A7`) and $+5\text{V}$.
* **Series Resistors:** 4.7kohm resistors placed between individual push buttons to ground (`GND`).
* **Button Layout:**
  * **Button 1:** Antenna A
  * **Button 2:** Antenna B
  * **Button 3:** Antenna C
  * **Button 4:** `ALL` (Selects/enables all three antennas simultaneously)

### 2. PTT Optical Isolation (PC817 Optocoupler)
To prevent RF feedback and protect the Arduino Nano:
* **Transceiver Side (Input LED):**
  * **Pin 1 (Anode):** Connected via a current-limiting resistor ($330\Omega$ to $470\Omega$) to $+5\text{V}$ (or $+12\text{V}$).
  * **Pin 2 (Cathode):** Connected directly to the transceiver’s PTT output (open-collector/relay pulling to ground during TX).
* **Arduino Side (Transistor Output):**
  * **Pin 3 (Emitter):** Connected to Arduino `GND`.
  * **Pin 4 (Collector):** Connected directly to Arduino **Pin A4** (`PTT_PIN`), utilizing the internal pull-up (`INPUT_PULLUP`).

---

## PC Communication & Protocol

The Arduino communicates with the Python desktop GUI over a standard serial link at **9600 baud**. 

### Incoming Commands (Python --> Arduino):
* `TOGGLE_MODE`: Switches the RX operation mode between Exclusive (`EXCL`) and Flexible (`FLEX`).
* `SET:abc`: Sets RX antenna states (e.g., `SET:101` sets RX A=ON, B=OFF, C=ON).
* `SETTX:abc`: Sets TX antenna states (e.g., `SETTX:110` sets TX A=ON, B=ON, C=OFF).

### Outgoing Status Stream (Arduino --> Python):
Every 500 ms (or immediately upon state changes), the Arduino broadcasts a structured status string:
```text
RX:101 TX:110 PTT:RX MOD:FLEX

```

* `RX:...`: Binary state of antennas A, B, and C.
* `TX:...`: Binary state of transmission antennas A, B, and C.
* `PTT:...`: Current radio state (`RX` or `TX`).
* `MOD:...`: Current operational mode (`EXCL` or `FLEX`).

---

## License

This project is open-source and intended for amateur radio experimentation and personal use.

```

```
