#!/bin/bash

# WiZ light room identification script

# Tests ONLY rooms containing exactly two lights.

ROOMS=(
"12515964|10.0.0.46|10.0.0.251"
"12304474|10.0.0.50|10.0.0.153"
"12304439|10.0.0.95|10.0.0.154"
)

send_red() {
local IP="$1"

```
echo "Sending RED command to $IP..."

echo -n '{"method":"setPilot","params":{"state":true,"r":255,"g":0,"b":0}}' |
    timeout 3 nc -u -w1 "$IP" 38899 </dev/null

echo "Command sent to $IP"
```

}

for ROOM in "${ROOMS[@]}"; do

```
IFS="|" read -r ROOM_ID LIGHT_1 LIGHT_2 <<< "$ROOM"

echo
echo "================================================="
echo "Testing WiZ Room ID: $ROOM_ID"
echo "Lights:"
echo "  1. $LIGHT_1"
echo "  2. $LIGHT_2"
echo "================================================="
echo
echo "Press ENTER to test this pair..."
read -r

send_red "$LIGHT_1"
sleep 1

send_red "$LIGHT_2"

echo
echo "The two lights above should now be RED."
echo
echo "If nothing happened, note the IP addresses displayed."
echo
echo "Press ENTER to continue to the next pair."
read -r
```

done

echo
echo "================================================="
echo "Finished testing all rooms with exactly two lights."
echo "================================================="

