import secrets
import hashlib
import datetime
import pytz
import json

def randint(a, b, digits=3):
    num = secrets.randbelow(b - a + 1) + a
    return str(num).zfill(digits)

def get_trombino(testata, korpo):

    random_number = randint(0, 1488, 4)
    string_to_hash = testata + korpo + random_number

    def get_digits(string_to_hash):
        sha256_hash = hashlib.sha256(string_to_hash.encode()).hexdigest()
        digits_only = ''.join(filter(str.isdigit, sha256_hash))

        return digits_only

    digits_only = get_digits(string_to_hash)

    while not digits_only:
        digits_only = get_digits(digits_only)
    
    return digits_only[0] + digits_only[-1]

def shentropye(limit=None):
    timezones = pytz.all_timezones  
    pending = randint(0, 9999, 4)

    def pendings(value, pending):
        value_str = str(value)
        shift_amount = int(pending) % len(value_str)
        shifted_value_str = value_str[shift_amount:] + value_str[:shift_amount]  
        return int(shifted_value_str)

    data = []  

    for tz in timezones:
        tz_obj = pytz.timezone(tz)
        now = datetime.datetime.now(tz_obj)

        codes_for_timezone = []
        for _ in range(5): 
            testata = randint(0, 999, 3)  
            korpo = randint(0, 999, 3) 
            chance = 50  

            while len(korpo) < limit: 
                if randint(1, 100) <= chance:
                    chance -= 10  
                    korpo += str(randint(0, 9, 1))
                else:
                    break

            trombino = get_trombino(testata, korpo)  

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
