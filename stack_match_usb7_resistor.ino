// ===========================================================
// ASMC 1-3 (Advanced StackMatch Controller)
// Verzija s dvostrukom otporničkom ljestvicom (TX na A6, RX na A7)
// ===========================================================

#include <avr/wdt.h>
#include <EEPROM.h> 

const bool LOW_INPUT_MODE = false; 

// Releji StackMatcha
const int RELAY_1 = 2;
const int RELAY_2 = 3;
const int RELAY_3 = 4;
const int RELAY_4 = 5; 

// Tipkalo za promjenu moda rada ostaje na zasebnom digitalnom pinu A5
const int BTN_RX_MODE = A5;  

// Otporničke ljestvice (Resistor Ladders)
const int LADDER_PIN    = A6; // TX tipke (A, B, C, SVE)
const int RX_LADDER_PIN = A7; // RX tipke (A, B, C, SVE)

// PTT Linije (Dual-Stage Sekvencer)
const int PTT_PIN     = A4; // ULAZ s radiouređaja (Active Low)
const int PTT_OUT1    = 11; // IZLAZ 1 (LOW = aktivno, npr. LNA / koaksijalni relej)
const int PTT_OUT2    = A0; // IZLAZ 2 (LOW = aktivno, npr. Linearno pojačalo - PA)

// --- LED DIODE (Vaš novi raspored) ---
const int LED_RX_A    = A1;
const int LED_RX_B    = A2;
const int LED_RX_C    = A3; 
const int LED_TX_A    = 9; 
const int LED_TX_B    = 10; 
const int LED_TX_C    = 13;

// Varijable stanja
bool rxAnt_A = true;
bool rxAnt_B = false;
bool rxAnt_C = false;

bool txAnt_A = true;
bool txAnt_B = false;
bool txAnt_C = false;

bool rxFlexibleMode = false;
int lastPttState = HIGH;

// Stanja za sekvencer (Faze preklapanja)
int sequencerStage = 0; 
unsigned long pttActionTime = 0;

const unsigned long TX_PRE_DELAY_MS = 20;     
const unsigned long TX_STAGE2_DELAY_MS = 20;  
const unsigned long TAIL_DELAY_MS = 80;       

unsigned long lastStatusSendTime = 0;
const unsigned long STATUS_INTERVAL_MS = 500; 

const unsigned long DEBOUNCE_DELAY = 50;
unsigned long lastBtnDebounce       = 0;

// EEPROM postavke (Lazy Write)
const int EEPROM_ADDR_RX = 0;
const int EEPROM_ADDR_TX = 3;
const int EEPROM_ADDR_MODE = 6;
unsigned long lastStateChangeTime = 0;
bool eepromSavePending = false;
const unsigned long EEPROM_DELAY_MS = 300000; // 5 minuta odgode

void updateStatusLEDs();
void sendStatusToPython();
void visualModeFeedback(int blinks);
void driveSJ2WRelays(bool antA, bool antB, bool antC);
void setRelayPins(uint8_t r1, uint8_t r2, uint8_t r3, uint8_t r4);
bool isPttActive();
void saveStatesToEEPROM();
void loadStatesFromEEPROM();
int readResistorLadder();
int readRxResistorLadder();
void handleRxButton(int antIndex);

void setup() {
  Serial.begin(9600);

  pinMode(RELAY_1, OUTPUT);
  pinMode(RELAY_2, OUTPUT);
  pinMode(RELAY_3, OUTPUT);
  pinMode(RELAY_4, OUTPUT);

  pinMode(LED_RX_A, OUTPUT);
  pinMode(LED_RX_B, OUTPUT);
  pinMode(LED_RX_C, OUTPUT);
  
  pinMode(LED_TX_A, OUTPUT);
  pinMode(LED_TX_B, OUTPUT); 
  pinMode(LED_TX_C, OUTPUT); 

  pinMode(BTN_RX_MODE, INPUT_PULLUP);
  pinMode(PTT_PIN, INPUT_PULLUP);
  
  pinMode(PTT_OUT1, OUTPUT);
  digitalWrite(PTT_OUT1, HIGH); 
  pinMode(PTT_OUT2, OUTPUT);
  digitalWrite(PTT_OUT2, HIGH); 

  loadStatesFromEEPROM();
  lastPttState = digitalRead(PTT_PIN);

  updateStatusLEDs();
  
  if (!isPttActive()) {
    driveSJ2WRelays(rxAnt_A, rxAnt_B, rxAnt_C);
  }

  wdt_enable(WDTO_2S);
}

bool isPttActive() {
  int currentPttRaw = digitalRead(PTT_PIN);
  if (LOW_INPUT_MODE) {
    return (currentPttRaw == HIGH);
  } else {
    return (currentPttRaw == LOW);
  }
}

// Čitanje TX otporničke ljestvice s A6 (1 do 4 = tipke)
int readResistorLadder() {
  return 0; // <-- PRIVREMENO ONEMOGUĆENO ZA TEST U GUI-JU
  
  int raw = analogRead(LADDER_PIN);
  if (raw > 900) return 0; 

  if (raw < 150)  return 1; // Tipka 1 -> TX Antena A
  if (raw < 400)  return 2; // Tipka 2 -> TX Antena B
  if (raw < 650)  return 3; // Tipka 3 -> TX Antena C
  if (raw < 850)  return 4; // Tipka 4 -> TX SVE (ALL)
  
  return 0;
}

// Čitanje RX otporničke ljestvice s A7 (1 do 4 = tipke)
int readRxResistorLadder() {
  return 0; // <-- PRIVREMENO ONEMOGUĆENO ZA TEST U GUI-JU
  
  int raw = analogRead(RX_LADDER_PIN);
  if (raw > 900) return 0; 

  if (raw < 150)  return 1; // Tipka 1 -> RX Antena A
  if (raw < 400)  return 2; // Tipka 2 -> RX Antena B
  if (raw < 650)  return 3; // Tipka 3 -> RX Antena C
  if (raw < 850)  return 4; // Tipka 4 -> RX SVE (ALL)
  
  return 0;
}

// Logika za RX tipke
void handleRxButton(int antIndex) {
  if (rxFlexibleMode) {
    if (antIndex == 0) rxAnt_A = !rxAnt_A;
    if (antIndex == 1) rxAnt_B = !rxAnt_B;
    if (antIndex == 2) rxAnt_C = !rxAnt_C;
  } else {
    rxAnt_A = (antIndex == 0);
    rxAnt_B = (antIndex == 1);
    rxAnt_C = (antIndex == 2);
  }
}

void loop() {
  wdt_reset();
  unsigned long currentMillis = millis();

  if (eepromSavePending && (currentMillis - lastStateChangeTime >= EEPROM_DELAY_MS)) {
    saveStatesToEEPROM();
    eepromSavePending = false;
  }

  if (currentMillis - lastStatusSendTime >= STATUS_INTERVAL_MS) {
    lastStatusSendTime = currentMillis;
    sendStatusToPython();
  }

  bool activePTT = isPttActive();
  int currentPttRaw = digitalRead(PTT_PIN);

  // --- 1. SERIJSKI ULAZ IZ PYTHONA ---
  if (Serial.available() > 0) {
    String incomingCmd = Serial.readStringUntil('\n');
    incomingCmd.trim();
    
    if (incomingCmd == "TOGGLE_MODE" && !activePTT) {
      rxFlexibleMode = !rxFlexibleMode;
      lastStateChangeTime = currentMillis; 
      eepromSavePending = true;
      sendStatusToPython();
    }
    else if (incomingCmd.startsWith("SET:")) { 
      String antState = incomingCmd.substring(4);
      if (antState.length() >= 3) {
        rxAnt_A = (antState[0] == '1'); 
        rxAnt_B = (antState[1] == '1'); 
        rxAnt_C = (antState[2] == '1');
        lastStateChangeTime = currentMillis; 
        eepromSavePending = true;
        
        if (!activePTT && sequencerStage == 0) { 
          driveSJ2WRelays(rxAnt_A, rxAnt_B, rxAnt_C); 
        }
        updateStatusLEDs();
        sendStatusToPython();
      }
    }
    else if (incomingCmd.startsWith("SETTX:")) { 
      String antState = incomingCmd.substring(6);
      if (antState.length() >= 3) {
        txAnt_A = (antState[0] == '1'); 
        txAnt_B = (antState[1] == '1'); 
        txAnt_C = (antState[2] == '1');
        lastStateChangeTime = currentMillis; 
        eepromSavePending = true;
        updateStatusLEDs();
        sendStatusToPython();
      }
    }
  }

  // --- 2. OČITAVANJE FIZIČKIH TIPKALA ---
  bool stateChanged = false;
  int ladderBtn   = readResistorLadder();    // Očitavanje TX ljestvice (A6)
  int rxLadderBtn = readRxResistorLadder(); // Očitavanje RX ljestvice (A7)

  if (digitalRead(BTN_RX_MODE) == LOW && !activePTT) {
    if (currentMillis - lastBtnDebounce > 250) {
      lastBtnDebounce = currentMillis;
      rxFlexibleMode = !rxFlexibleMode; 
      visualModeFeedback(rxFlexibleMode ? 2 : 1);
      stateChanged = true;
    }
  }
  // Očitavanje RX tipkala s otporničke ljestvice na pinu A7
  else if (rxLadderBtn > 0 && (currentMillis - lastBtnDebounce > DEBOUNCE_DELAY)) {
    lastBtnDebounce = currentMillis;
    
    if (rxLadderBtn == 1) {
      handleRxButton(0); // RX Antena A (poštuje EXCL/FLEX)
    } 
    else if (rxLadderBtn == 2) {
      handleRxButton(1); // RX Antena B
    } 
    else if (rxLadderBtn == 3) {
      handleRxButton(2); // RX Antena C
    } 
    else if (rxLadderBtn == 4) {
      // Tipka 4: Uključi sve RX antene (Sve odjednom)
      rxAnt_A = true;
      rxAnt_B = true;
      rxAnt_C = true;
    }
    
    stateChanged = true;
  }
  // Očitavanje TX tipkala s otporničke ljestvice na pinu A6
  else if (ladderBtn > 0 && (currentMillis - lastBtnDebounce > DEBOUNCE_DELAY)) {
    lastBtnDebounce = currentMillis;
    
    if (ladderBtn == 1) {
      txAnt_A = !txAnt_A; // Prebaci stanje TX A
    } 
    else if (ladderBtn == 2) {
      txAnt_B = !txAnt_B; // Prebaci stanje TX B
    } 
    else if (ladderBtn == 3) {
      txAnt_C = !txAnt_C; // Prebaci stanje TX C
    } 
    else if (ladderBtn == 4) {
      // Tipka 4: Odaberi sve TX antene odjednom
      txAnt_A = true;
      txAnt_B = true;
      txAnt_C = true;
    }
    
    stateChanged = true;
  }

  if (stateChanged) {
    lastStateChangeTime = currentMillis;
    eepromSavePending = true;
    updateStatusLEDs();
    if (!activePTT && sequencerStage == 0) {
      driveSJ2WRelays(rxAnt_A, rxAnt_B, rxAnt_C);
    }
    sendStatusToPython();
  }

  // --- 3. DUAL-STAGE PTT SEKVENCER ---
  if (currentPttRaw != lastPttState) {
    pttActionTime = currentMillis;
    lastPttState = currentPttRaw;

    if (activePTT) {
      driveSJ2WRelays(txAnt_A, txAnt_B, txAnt_C);
      updateStatusLEDs(); 
      sequencerStage = 1; 
    } else {
      digitalWrite(PTT_OUT2, HIGH);
      digitalWrite(PTT_OUT1, HIGH);
      sequencerStage = 4; 
    }
    sendStatusToPython();
  }

  if (activePTT) {
    if (sequencerStage == 1 && (currentMillis - pttActionTime >= TX_PRE_DELAY_MS)) {
      digitalWrite(PTT_OUT1, LOW); 
      pttActionTime = currentMillis; 
      sequencerStage = 2;
    }
    else if (sequencerStage == 2 && (currentMillis - pttActionTime >= TX_STAGE2_DELAY_MS)) {
      digitalWrite(PTT_OUT2, LOW); 
      sequencerStage = 3; 
    }
  } else {
    if (sequencerStage == 4 && (currentMillis - pttActionTime >= TAIL_DELAY_MS)) {
      driveSJ2WRelays(rxAnt_A, rxAnt_B, rxAnt_C); 
      updateStatusLEDs(); 
      sequencerStage = 0; 
    }
  }

  updateStatusLEDs();
}

// ===========================================================
// POMOĆNE FUNKCIJE
// ===========================================================

void updateStatusLEDs() {
  // RX LED diode (sada su A1, A2 i A3)
  digitalWrite(LED_RX_A, rxAnt_A ? HIGH : LOW);
  digitalWrite(LED_RX_B, rxAnt_B ? HIGH : LOW);
  digitalWrite(LED_RX_C, rxAnt_C ? HIGH : LOW); // Čisto i jednostavno bez provjere pina 13!

  // TX LED diode (sada su 9, 10 i 13)
  if (!isPttActive()) {
    digitalWrite(LED_TX_A, txAnt_A ? HIGH : LOW);
    digitalWrite(LED_TX_B, txAnt_B ? HIGH : LOW);
    digitalWrite(LED_TX_C, txAnt_C ? HIGH : LOW); // TX C sada koristi pin 13 i onboard LED diodu
  }
}

void sendStatusToPython() {
  bool isTX = isPttActive();
  
  String msg = "RX:";
  msg += (rxAnt_A ? "1" : "0");
  msg += (rxAnt_B ? "1" : "0");
  msg += (rxAnt_C ? "1" : "0");
  msg += " TX:";
  msg += (txAnt_A ? "1" : "0");
  msg += (txAnt_B ? "1" : "0");
  msg += (txAnt_C ? "1" : "0");
  msg += " PTT:";
  msg += (isTX ? "TX" : "RX");
  msg += " MOD:";
  msg += (rxFlexibleMode ? "FLEX" : "EXCL");
  
  Serial.println(msg);
}

void visualModeFeedback(int blinks) {
  for (int i = 0; i < blinks; i++) {
    digitalWrite(LED_RX_A, HIGH); digitalWrite(LED_RX_B, HIGH); digitalWrite(LED_RX_C, HIGH);
    delay(100);
    digitalWrite(LED_RX_A, LOW); digitalWrite(LED_RX_B, LOW); digitalWrite(LED_RX_C, LOW);
    delay(100);
  }
  updateStatusLEDs();
}

void driveSJ2WRelays(bool antA, bool antB, bool antC) {
  int activeCount = (antA ? 1 : 0) + (antB ? 1 : 0) + (antC ? 1 : 0);
  uint8_t r4State = (activeCount >= 2) ? HIGH : LOW;

  if (antA && !antB && !antC)      { setRelayPins(HIGH, LOW,  LOW,  r4State); } 
  else if (!antA && antB && !antC) { setRelayPins(LOW,  HIGH, LOW,  r4State); } 
  else if (!antA && !antB && antC) { setRelayPins(LOW,  LOW,  HIGH, r4State); } 
  else if (antA && antB && !antC)  { setRelayPins(HIGH, HIGH, LOW,  r4State); } 
  else if (antA && !antB && antC)  { setRelayPins(HIGH, LOW,  HIGH, r4State); } 
  else if (!antA && antB && antC)  { setRelayPins(LOW,  HIGH, HIGH,  r4State); } 
  else if (antA && antB && antC)   { setRelayPins(HIGH, HIGH, HIGH,  r4State); } 
  else {
    setRelayPins(LOW, LOW, LOW, LOW); 
  }
}

void setRelayPins(uint8_t r1, uint8_t r2, uint8_t r3, uint8_t r4) {
  digitalWrite(RELAY_1, !r1);
  digitalWrite(RELAY_2, !r2);
  digitalWrite(RELAY_3, !r3);
  digitalWrite(RELAY_4, !r4);
}

void saveStatesToEEPROM() {
  byte rxByte = (rxAnt_A << 2) | (rxAnt_B << 1) | rxAnt_C;
  byte txByte = (txAnt_A << 2) | (txAnt_B << 1) | txAnt_C;
  EEPROM.update(EEPROM_ADDR_RX, rxByte);
  EEPROM.update(EEPROM_ADDR_TX, txByte);
  EEPROM.update(EEPROM_ADDR_MODE, rxFlexibleMode ? 1 : 0);
}

void loadStatesFromEEPROM() {
  byte rxByte = EEPROM.read(EEPROM_ADDR_RX);
  byte txByte = EEPROM.read(EEPROM_ADDR_TX);
  byte modeByte = EEPROM.read(EEPROM_ADDR_MODE);

  if (rxByte != 0xFF) {
    rxAnt_A = (rxByte >> 2) & 1;
    rxAnt_B = (rxByte >> 1) & 1;
    rxAnt_C = rxByte & 1;
  }
  if (txByte != 0xFF) {
    txAnt_A = (txByte >> 2) & 1;
    txAnt_B = (txByte >> 1) & 1;
    txAnt_C = (txByte & 1);
  }
  if (modeByte != 0xFF) {
    rxFlexibleMode = (modeByte == 1);
  }
}
