import secrets
import hashlib
import datetime
import pytz
import json

def randint(a, b, digits=3):
    num = secrets.randbelow(b - a + 1) + a
    return str(num).zfill(digits)

def get_trombino(testata, korpo):

    rounds = int(hashlib.sha256((testata + korpo).encode()).hexdigest()[:2], 16) % 8 + 1
    s = testata + korpo
    for _ in range(rounds):
        s = hashlib.sha256(s.encode()).hexdigest()
    digits = ''.join(filter(str.isdigit, s))

    while not digits:
        digits = ''.join(filter(str.isdigit, hashlib.sha256(digits.encode()).hexdigest()))
    
    idx1 = secrets.randbelow(len(digits))
    idx2 = secrets.randbelow(len(digits))
    return digits[idx1] + digits[idx2]

def shentropye(limit=None):
    timezones = pytz.all_timezones  
    pending = randint(0, 9999, 4)

    def pendings(value, pending):
        value_str = str(value)
        for _ in range(secrets.randbelow(3)+1):
            step = int(hashlib.sha1(pending.encode()).hexdigest(), 16) % len(value_str)
            value_str = value_str[step:] + value_str[:step]
        return int(value_str)

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
