// Host-side check of button logic; Arduino CI separately compiles for AVR.
#include <cassert>
using byte = unsigned char;
const int HIGH = 1, LOW = 0, INPUT_PULLUP = 2;
unsigned long clockMs = 0;
int pinValue = HIGH;
void pinMode(byte, int) {}
int digitalRead(byte) { return pinValue; }
unsigned long millis() { return clockMs; }
struct SerialStub {
    int sent = 0;
    void begin(int baud) { assert(baud == 9600); }
    void write(char value) { assert(value == 'S'); ++sent; }
} Serial;
#include "../firmware/nano_button/nano_button.ino"

void tick(unsigned long now, int value) {
    clockMs = now;
    pinValue = value;
    loop();
}

int main() {
    setup();
    tick(10, LOW);
    tick(20, HIGH);
    tick(25, LOW);
    tick(64, LOW);
    assert(Serial.sent == 0);
    tick(65, LOW);
    tick(1000, LOW);
    assert(Serial.sent == 1);
    tick(1010, HIGH);
    tick(1050, HIGH);
    tick(1060, LOW);
    tick(1100, LOW);
    assert(Serial.sent == 2);
    // A button held at boot must first be released before it can trigger.
    Serial.sent = 0;
    setup();
    tick(1200, LOW);
    assert(Serial.sent == 0);
    tick(1210, HIGH);
    tick(1250, HIGH);
    tick(1260, LOW);
    tick(1300, LOW);
    assert(Serial.sent == 1);
}
