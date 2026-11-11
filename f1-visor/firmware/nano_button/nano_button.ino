// Button-to-Bluetooth reference, based on the author's validated prototype.
// Classic Nano: button D2 -> GND; HC-06 UART at 9600 baud.
// D1/TX -> level shifter -> HC-06 RX; HC-06 TX -> D0/RX; common GND.
const byte BUTTON_PIN = 2;
const unsigned long DEBOUNCE_MS = 40;
int lastReading = HIGH;
int stableState = HIGH;
unsigned long changedAt = 0;
bool armed = false;

void setup() {
  pinMode(BUTTON_PIN, INPUT_PULLUP);
  Serial.begin(9600);
  lastReading = digitalRead(BUTTON_PIN);
  stableState = lastReading;
  armed = (lastReading == HIGH);
}

void loop() {
  int reading = digitalRead(BUTTON_PIN);
  if (reading != lastReading) {
    changedAt = millis();
    lastReading = reading;
  }
  if (millis() - changedAt >= DEBOUNCE_MS && reading != stableState) {
    stableState = reading;
    if (stableState == HIGH) {
      armed = true;
    } else if (armed) {
      Serial.write('S');
      armed = false;  // One command per press; holding the button never repeats.
    }
  }
}
