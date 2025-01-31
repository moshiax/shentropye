import random
import datetime
import pytz
import json

def shentropye(limit=None):
    timezones = pytz.all_timezones  
    pending = random.randint(1, 10000) 

    def pendings(value, pending):
        value_str = str(value)
        shift_amount = pending % len(value_str) 
        shifted_value_str = value_str[shift_amount:] + value_str[:shift_amount]  
        return int(shifted_value_str)

    data = []  

    for tz in timezones:
        tz_obj = pytz.timezone(tz)
        now = datetime.datetime.now(tz_obj)

        codes_for_timezone = []
        for _ in range(5): 
            testata = f"{random.randint(100, 999)}"  
            korpo = f"{random.randint(100, 999)}" 
            chance = 50  

            while len(korpo) < limit: 
                if random.randint(1, 100) <= chance: 
                    chance -= 10  
                    korpo += str(random.randint(0, 9)) 
                else:
                    break

            trombino = f"{random.randint(10, 99)}" 

            korpo = ''.join([str(pendings(int(digit), pending)) for digit in korpo])

            code = f"{testata}-{korpo}.{trombino}"
            codes_for_timezone.append(code)

        generation_time = now.strftime("%Y-%m-%d")
        
        data.append({
            "timezone": tz,
            "codes": codes_for_timezone,
            "generation_time": generation_time
        })

    with open("shentropye_codes.json", "w") as f:
        json.dump(data, f, indent=4)

shentropye(limit=3)
