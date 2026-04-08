import hashlib
import datetime
from zoneinfo import ZoneInfo, available_timezones
import json
import os
import multiprocessing as mp

MASK_64 = (1 << 64) - 1

def _det_uint(key):
    digest = hashlib.sha3_256(str(key).encode()).digest()
    return int.from_bytes(digest[:8], "big")

def randint(a, b, digits=3, key=""):
    num = (_det_uint(f"randint:{a}:{b}:{digits}:{key}") % (b - a + 1)) + a
    return str(num).zfill(digits)

def _u64(value):
    return value & MASK_64

def _rotl(value, shift):
    shift &= 63
    value &= MASK_64
    return ((value << shift) | (value >> ((-shift) & 63))) & MASK_64

def _rotr(value, shift):
    shift &= 63
    value &= MASK_64
    return ((value >> shift) | (value << ((-shift) & 63))) & MASK_64

def _seed_triplet(testata, korpo, pending, salt):
    raw = f"{testata}|{korpo}|{pending}|{salt}".encode()
    digest = hashlib.sha512(raw).digest()
    a = int.from_bytes(digest[0:8], "big")
    b = int.from_bytes(digest[8:16], "big")
    c = int.from_bytes(digest[16:24], "big")
    return a, b, c

def _bytefold(value):
    value &= MASK_64
    left = ((value & 0x00FF00FF00FF00FF) << 8)
    right = ((value & 0xFF00FF00FF00FF00) >> 8)
    return (left | right) & MASK_64

def _nibble_weave(a, b):
    mask = 0x0F0F0F0F0F0F0F0F
    return (((a & mask) << 4) | ((b & ~mask) >> 4)) & MASK_64

def _hash_pulse(x, y, z, salt):
    h = hashlib.blake2s(f"{x}:{y}:{z}:{salt}".encode()).digest()
    return int.from_bytes(h[:8], "big")

def _stage_0(x, y, z, lane):
    twist = _rotl(x ^ 11400714785074694791, 1)
    fold = _bytefold(y + 14029467366897019727)
    gate = _nibble_weave(twist, fold)
    x = _u64((gate ^ z) * 0x100000001B3)
    y = _u64((_rotr(fold ^ x, lane % 31 + 1) + z) * 0xC6A4A7935BD1E995)
    z = _u64((_rotl(gate ^ y, lane % 29 + 3) + x) * 0x9E3779B185EBCA87)
    return x, y, z

def _stage_1(x, y, z, lane):
    anchor = _rotr(y + 11400715884586323002, 12)
    braid = _nibble_weave(z ^ 6983438112510666596, x)
    x = _u64((x ^ anchor ^ lane) + _rotl(braid, lane % 17 + 5))
    y = _u64((y + braid + _bytefold(anchor)) * 0xD6E8FEB86659FD93)
    z = _u64((z ^ x ^ _rotl(y, 7)) * 0xA24BAED4963EE407)
    return x, y, z

def _stage_2(x, y, z, lane):
    drift = _u64((x + y + 11400716984097951213) ^ _rotl(z, 11))
    shard = _u64((z + 18384152931833865081) ^ _rotr(y, 35))
    pulse = _hash_pulse(drift, shard, x, lane)
    x = _u64((drift ^ pulse) * 0x9FB21C651E98DF25)
    y = _u64((shard + _rotl(pulse, 9) + x) * 0xC3A5C85C97CB3127)
    z = _u64((z ^ _bytefold(y) ^ _rotr(x, 13)) + pulse)
    return x, y, z

def _stage_3(x, y, z, lane):
    s1 = _rotl(x ^ 11173821941947921074, 34)
    s2 = _rotr(y + 11400718083609579424, 16)
    s3 = _bytefold(z ^ 11338123677447511950)
    x = _u64((s1 + (s2 ^ lane)) * 0xBF58476D1CE4E5B9)
    y = _u64((s2 + (s3 ^ x)) * 0x94D049BB133111EB)
    z = _u64((s3 + (s1 ^ y)) * 0x369DEA0F31A53F85)
    return x, y, z

def _stage_4(x, y, z, lane):
    orbit = _u64((x * 11400719183121207635) ^ _rotl(y, 6))
    echo = _u64((z * 4292094423061158819) ^ _rotr(x, 45))
    mesh = _nibble_weave(orbit, echo)
    x = _u64(mesh + _rotl(orbit, lane % 21 + 3))
    y = _u64((_bytefold(mesh ^ y) + _rotr(echo, lane % 19 + 5)))
    z = _u64((z ^ x ^ y ^ lane) * 0x27D4EB2F165667C5)
    return x, y, z

def _stage_5(x, y, z, lane):
    delta = _u64((x - y + 11400720282632835846) ^ _rotl(z, 26))
    sigma = _u64((y - z + 15692809242384357304) ^ _rotr(x, 56))
    if (delta ^ sigma ^ lane) & 1:
        x = _u64((_rotl(delta, 7) + sigma) * 0x9E6C63D0676A9A99)
        y = _u64((_rotr(sigma, 11) ^ x) * 0xC2B2AE3D27D4EB4F)
    else:
        x = _u64((_rotr(delta, 5) ^ sigma) * 0x165667B19E3779F9)
        y = _u64((_rotl(sigma, 13) + x) * 0x85EBCA77C2B2AE63)
    z = _u64(z ^ _bytefold(x + y + lane))
    return x, y, z

def _stage_6(x, y, z, lane):
    q = _u64(x ^ 11400721382144464057 ^ lane)
    w = _u64(y + 8646779987998004173 + lane * 3)
    e = _u64(z ^ 2291311880793451371 ^ lane * 7)
    x = _u64((_rotl(q, 9) + _rotr(w, 3) + e) * 0xA0761D6478BD642F)
    y = _u64((_rotl(w, 19) ^ _rotr(e, 5) ^ x) * 0xE7037ED1A0B428DB)
    z = _u64((_rotl(e, 29) + _rotr(q, 7) + y) * 0x8EBC6AF09C88C6E3)
    return x, y, z

def _stage_7(x, y, z, lane):
    m = _hash_pulse(x ^ 11400722481656092268, y ^ lane, z ^ 1600750733611651042, lane + 7)
    r = _rotl(m, lane % 31 + 1)
    x = _u64((x ^ r ^ _bytefold(y)) + 0x9E3779B97F4A7C15)
    y = _u64((y + _rotr(r, 7) ^ _nibble_weave(z, x)) * 0x94D049BB133111EB)
    z = _u64((z ^ _rotl(x, 17) ^ _rotr(y, 23)) * 0x2545F4914F6CDD1D)
    return x, y, z

def _stage_8(x, y, z, lane):
    left = _u64((x + 11400723581167720479) * 0x9E3779B185EBCA87)
    mid = _u64((y ^ 13001465552934849527) * 0xC2B2AE3D27D4EB4F)
    right = _u64((z + 14816382580400023185) * 0x165667B19E3779F9)
    mix = _nibble_weave(_bytefold(left), _rotr(right, 9))
    x = _u64(left ^ _rotl(mid, lane % 27 + 3) ^ mix)
    y = _u64(mid + _rotr(right, lane % 25 + 5) + _bytefold(x))
    z = _u64(right ^ _rotl(left, lane % 23 + 7) ^ _bytefold(y))
    return x, y, z

def _stage_9(x, y, z, lane):
    p = _u64((x ^ y ^ 11400724680679348690) + lane)
    q = _u64((y ^ z ^ 5955436298548496396) + lane * 5)
    r = _u64((z ^ x ^ 11855545893348533284) + lane * 11)
    g1 = _rotl(p, 3) ^ _rotr(q, 7)
    g2 = _rotl(q, 13) ^ _rotr(r, 17)
    g3 = _rotl(r, 29) ^ _rotr(p, 23)
    x = _u64((g1 + g2 + _bytefold(g3)) * 0xDB4F0B9175AE2165)
    y = _u64((g2 ^ g3 ^ _bytefold(g1)) * 0xBBE0563303A4615F)
    z = _u64((g3 + g1 + _bytefold(g2)) * 0xA0F2EC75A1FE1575)
    return x, y, z

def _stage_10(x, y, z, lane):
    twist = _rotl(x ^ 11400725780190976901, 51)
    fold = _bytefold(y + 17356151117871694881)
    gate = _nibble_weave(twist, fold)
    x = _u64((gate ^ z) * 0x100000001B3)
    y = _u64((_rotr(fold ^ x, lane % 31 + 1) + z) * 0xC6A4A7935BD1E995)
    z = _u64((_rotl(gate ^ y, lane % 29 + 3) + x) * 0x9E3779B185EBCA87)
    return x, y, z

def _stage_11(x, y, z, lane):
    anchor = _rotr(y + 11400726879702605112, 59)
    braid = _nibble_weave(z ^ 10310121863485341750, x)
    x = _u64((x ^ anchor ^ lane) + _rotl(braid, lane % 17 + 5))
    y = _u64((y + braid + _bytefold(anchor)) * 0xD6E8FEB86659FD93)
    z = _u64((z ^ x ^ _rotl(y, 7)) * 0xA24BAED4963EE407)
    return x, y, z

def _stage_12(x, y, z, lane):
    drift = _u64((x + y + 11400727979214233323) ^ _rotl(z, 61))
    shard = _u64((z + 3264092609098988619) ^ _rotr(y, 16))
    pulse = _hash_pulse(drift, shard, x, lane)
    x = _u64((drift ^ pulse) * 0x9FB21C651E98DF25)
    y = _u64((shard + _rotl(pulse, 9) + x) * 0xC3A5C85C97CB3127)
    z = _u64((z ^ _bytefold(y) ^ _rotr(x, 13)) + pulse)
    return x, y, z

def _stage_13(x, y, z, lane):
    s1 = _rotl(x ^ 12199145142573680, 18)
    s2 = _rotr(y + 11400729078725861534, 3)
    s3 = _bytefold(z ^ 14664807428422187104)
    x = _u64((s1 + (s2 ^ lane)) * 0xBF58476D1CE4E5B9)
    y = _u64((s2 + (s3 ^ x)) * 0x94D049BB133111EB)
    z = _u64((s3 + (s1 ^ y)) * 0x369DEA0F31A53F85)
    return x, y, z

def _stage_14(x, y, z, lane):
    orbit = _u64((x * 11400730178237489745) ^ _rotl(y, 50))
    echo = _u64((z * 7618778174035833973) ^ _rotr(x, 29))
    mesh = _nibble_weave(orbit, echo)
    x = _u64(mesh + _rotl(orbit, lane % 21 + 3))
    y = _u64((_bytefold(mesh ^ y) + _rotr(echo, lane % 19 + 5)))
    z = _u64((z ^ x ^ y ^ lane) * 0x27D4EB2F165667C5)
    return x, y, z

def _stage_15(x, y, z, lane):
    delta = _u64((x - y + 11400731277749117956) ^ _rotl(z, 13))
    sigma = _u64((y - z + 572748919649480842) ^ _rotr(x, 40))
    if (delta ^ sigma ^ lane) & 1:
        x = _u64((_rotl(delta, 7) + sigma) * 0x9E6C63D0676A9A99)
        y = _u64((_rotr(sigma, 11) ^ x) * 0xC2B2AE3D27D4EB4F)
    else:
        x = _u64((_rotr(delta, 5) ^ sigma) * 0x165667B19E3779F9)
        y = _u64((_rotl(sigma, 13) + x) * 0x85EBCA77C2B2AE63)
    z = _u64(z ^ _bytefold(x + y + lane))
    return x, y, z

def _stage_16(x, y, z, lane):
    q = _u64(x ^ 11400732377260746167 ^ lane)
    w = _u64(y + 11973463738972679327 + lane * 3)
    e = _u64(z ^ 9576433157697655593 ^ lane * 7)
    x = _u64((_rotl(q, 9) + _rotr(w, 3) + e) * 0xA0761D6478BD642F)
    y = _u64((_rotl(w, 19) ^ _rotr(e, 5) ^ x) * 0xE7037ED1A0B428DB)
    z = _u64((_rotl(e, 29) + _rotr(q, 7) + y) * 0x8EBC6AF09C88C6E3)
    return x, y, z

def _stage_17(x, y, z, lane):
    m = _hash_pulse(x ^ 11400733476772374378, y ^ lane, z ^ 4927434484586326196, lane + 17)
    r = _rotl(m, lane % 31 + 1)
    x = _u64((x ^ r ^ _bytefold(y)) + 0x9E3779B97F4A7C15)
    y = _u64((y + _rotr(r, 7) ^ _nibble_weave(z, x)) * 0x94D049BB133111EB)
    z = _u64((z ^ _rotl(x, 17) ^ _rotr(y, 23)) * 0x2545F4914F6CDD1D)
    return x, y, z

def _stage_18(x, y, z, lane):
    left = _u64((x + 11400734576284002589) * 0x9E3779B185EBCA87)
    mid = _u64((y ^ 16328149303909524681) * 0xC2B2AE3D27D4EB4F)
    right = _u64((z + 3654759783594675791) * 0x165667B19E3779F9)
    mix = _nibble_weave(_bytefold(left), _rotr(right, 9))
    x = _u64(left ^ _rotl(mid, lane % 27 + 3) ^ mix)
    y = _u64(mid + _rotr(right, lane % 25 + 5) + _bytefold(x))
    z = _u64(right ^ _rotl(left, lane % 23 + 7) ^ _bytefold(y))
    return x, y, z

def _stage_19(x, y, z, lane):
    p = _u64((x ^ y ^ 11400735675795630800) + lane)
    q = _u64((y ^ z ^ 9282120049523171550) + lane * 5)
    r = _u64((z ^ x ^ 693923096543185890) + lane * 11)
    g1 = _rotl(p, 3) ^ _rotr(q, 7)
    g2 = _rotl(q, 13) ^ _rotr(r, 17)
    g3 = _rotl(r, 29) ^ _rotr(p, 23)
    x = _u64((g1 + g2 + _bytefold(g3)) * 0xDB4F0B9175AE2165)
    y = _u64((g2 ^ g3 ^ _bytefold(g1)) * 0xBBE0563303A4615F)
    z = _u64((g3 + g1 + _bytefold(g2)) * 0xA0F2EC75A1FE1575)
    return x, y, z

def _stage_20(x, y, z, lane):
    twist = _rotl(x ^ 11400736775307259011, 38)
    fold = _bytefold(y + 2236090795136818419)
    gate = _nibble_weave(twist, fold)
    x = _u64((gate ^ z) * 0x100000001B3)
    y = _u64((_rotr(fold ^ x, lane % 31 + 1) + z) * 0xC6A4A7935BD1E995)
    z = _u64((_rotl(gate ^ y, lane % 29 + 3) + x) * 0x9E3779B185EBCA87)
    return x, y, z

def _stage_21(x, y, z, lane):
    anchor = _rotr(y + 11400737874818887222, 43)
    braid = _nibble_weave(z ^ 13636805614460016904, x)
    x = _u64((x ^ anchor ^ lane) + _rotl(braid, lane % 17 + 5))
    y = _u64((y + braid + _bytefold(anchor)) * 0xD6E8FEB86659FD93)
    z = _u64((z ^ x ^ _rotl(y, 7)) * 0xA24BAED4963EE407)
    return x, y, z

def _stage_22(x, y, z, lane):
    drift = _u64((x + y + 11400738974330515433) ^ _rotl(z, 48))
    shard = _u64((z + 6590776360073663773) ^ _rotr(y, 60))
    pulse = _hash_pulse(drift, shard, x, lane)
    x = _u64((drift ^ pulse) * 0x9FB21C651E98DF25)
    y = _u64((shard + _rotl(pulse, 9) + x) * 0xC3A5C85C97CB3127)
    z = _u64((z ^ _bytefold(y) ^ _rotr(x, 13)) + pulse)
    return x, y, z

def _stage_23(x, y, z, lane):
    s1 = _rotl(x ^ 7297320422046777902, 2)
    s2 = _rotr(y + 11400740073842143644, 53)
    s3 = _bytefold(z ^ 17991491179396862258)
    x = _u64((s1 + (s2 ^ lane)) * 0xBF58476D1CE4E5B9)
    y = _u64((s2 + (s3 ^ x)) * 0x94D049BB133111EB)
    z = _u64((s3 + (s1 ^ y)) * 0x369DEA0F31A53F85)
    return x, y, z

def _stage_24(x, y, z, lane):
    orbit = _u64((x * 11400741173353771855) ^ _rotl(y, 31))
    echo = _u64((z * 10945461925010509127) ^ _rotr(x, 13))
    mesh = _nibble_weave(orbit, echo)
    x = _u64(mesh + _rotl(orbit, lane % 21 + 3))
    y = _u64((_bytefold(mesh ^ y) + _rotr(echo, lane % 19 + 5)))
    z = _u64((z ^ x ^ y ^ lane) * 0x27D4EB2F165667C5)
    return x, y, z

def _stage_25(x, y, z, lane):
    delta = _u64((x - y + 11400742272865400066) ^ _rotl(z, 63))
    sigma = _u64((y - z + 3899432670624155996) ^ _rotr(x, 24))
    if (delta ^ sigma ^ lane) & 1:
        x = _u64((_rotl(delta, 7) + sigma) * 0x9E6C63D0676A9A99)
        y = _u64((_rotr(sigma, 11) ^ x) * 0xC2B2AE3D27D4EB4F)
    else:
        x = _u64((_rotr(delta, 5) ^ sigma) * 0x165667B19E3779F9)
        y = _u64((_rotl(sigma, 13) + x) * 0x85EBCA77C2B2AE63)
    z = _u64(z ^ _bytefold(x + y + lane))
    return x, y, z

def _stage_26(x, y, z, lane):
    q = _u64(x ^ 11400743372377028277 ^ lane)
    w = _u64(y + 15300147489947354481 + lane * 3)
    e = _u64(z ^ 16861554434601859815 ^ lane * 7)
    x = _u64((_rotl(q, 9) + _rotr(w, 3) + e) * 0xA0761D6478BD642F)
    y = _u64((_rotl(w, 19) ^ _rotr(e, 5) ^ x) * 0xE7037ED1A0B428DB)
    z = _u64((_rotl(e, 29) + _rotr(q, 7) + y) * 0x8EBC6AF09C88C6E3)
    return x, y, z

def _stage_27(x, y, z, lane):
    m = _hash_pulse(x ^ 11400744471888656488, y ^ lane, z ^ 8254118235561001350, lane + 27)
    r = _rotl(m, lane % 31 + 1)
    x = _u64((x ^ r ^ _bytefold(y)) + 0x9E3779B97F4A7C15)
    y = _u64((y + _rotr(r, 7) ^ _nibble_weave(z, x)) * 0x94D049BB133111EB)
    z = _u64((z ^ _rotl(x, 17) ^ _rotr(y, 23)) * 0x2545F4914F6CDD1D)
    return x, y, z

def _stage_28(x, y, z, lane):
    left = _u64((x + 11400745571400284699) * 0x9E3779B185EBCA87)
    mid = _u64((y ^ 1208088981174648219) * 0xC2B2AE3D27D4EB4F)
    right = _u64((z + 10939881060498880013) * 0x165667B19E3779F9)
    mix = _nibble_weave(_bytefold(left), _rotr(right, 9))
    x = _u64(left ^ _rotl(mid, lane % 27 + 3) ^ mix)
    y = _u64(mid + _rotr(right, lane % 25 + 5) + _bytefold(x))
    z = _u64(right ^ _rotl(left, lane % 23 + 7) ^ _bytefold(y))
    return x, y, z

def _stage_29(x, y, z, lane):
    p = _u64((x ^ y ^ 11400746670911912910) + lane)
    q = _u64((y ^ z ^ 12608803800497846704) + lane * 5)
    r = _u64((z ^ x ^ 7979044373447390112) + lane * 11)
    g1 = _rotl(p, 3) ^ _rotr(q, 7)
    g2 = _rotl(q, 13) ^ _rotr(r, 17)
    g3 = _rotl(r, 29) ^ _rotr(p, 23)
    x = _u64((g1 + g2 + _bytefold(g3)) * 0xDB4F0B9175AE2165)
    y = _u64((g2 ^ g3 ^ _bytefold(g1)) * 0xBBE0563303A4615F)
    z = _u64((g3 + g1 + _bytefold(g2)) * 0xA0F2EC75A1FE1575)
    return x, y, z

def _stage_30(x, y, z, lane):
    twist = _rotl(x ^ 11400747770423541121, 25)
    fold = _bytefold(y + 5562774546111493573)
    gate = _nibble_weave(twist, fold)
    x = _u64((gate ^ z) * 0x100000001B3)
    y = _u64((_rotr(fold ^ x, lane % 31 + 1) + z) * 0xC6A4A7935BD1E995)
    z = _u64((_rotl(gate ^ y, lane % 29 + 3) + x) * 0x9E3779B185EBCA87)
    return x, y, z

def _stage_31(x, y, z, lane):
    anchor = _rotr(y + 11400748869935169332, 27)
    braid = _nibble_weave(z ^ 16963489365434692058, x)
    x = _u64((x ^ anchor ^ lane) + _rotl(braid, lane % 17 + 5))
    y = _u64((y + braid + _bytefold(anchor)) * 0xD6E8FEB86659FD93)
    z = _u64((z ^ x ^ _rotl(y, 7)) * 0xA24BAED4963EE407)
    return x, y, z

def _stage_32(x, y, z, lane):
    drift = _u64((x + y + 11400749969446797543) ^ _rotl(z, 35))
    shard = _u64((z + 9917460111048338927) ^ _rotr(y, 41))
    pulse = _hash_pulse(drift, shard, x, lane)
    x = _u64((drift ^ pulse) * 0x9FB21C651E98DF25)
    y = _u64((shard + _rotl(pulse, 9) + x) * 0xC3A5C85C97CB3127)
    z = _u64((z ^ _bytefold(y) ^ _rotr(x, 13)) + pulse)
    return x, y, z

def _stage_33(x, y, z, lane):
    s1 = _rotl(x ^ 14582441698950982124, 49)
    s2 = _rotr(y + 11400751068958425754, 40)
    s3 = _bytefold(z ^ 2871430856661985796)
    x = _u64((s1 + (s2 ^ lane)) * 0xBF58476D1CE4E5B9)
    y = _u64((s2 + (s3 ^ x)) * 0x94D049BB133111EB)
    z = _u64((s3 + (s1 ^ y)) * 0x369DEA0F31A53F85)
    return x, y, z

def _stage_34(x, y, z, lane):
    orbit = _u64((x * 11400752168470053965) ^ _rotl(y, 12))
    echo = _u64((z * 14272145675985184281) ^ _rotr(x, 60))
    mesh = _nibble_weave(orbit, echo)
    x = _u64(mesh + _rotl(orbit, lane % 21 + 3))
    y = _u64((_bytefold(mesh ^ y) + _rotr(echo, lane % 19 + 5)))
    z = _u64((z ^ x ^ y ^ lane) * 0x27D4EB2F165667C5)
    return x, y, z

def _stage_35(x, y, z, lane):
    delta = _u64((x - y + 11400753267981682176) ^ _rotl(z, 50))
    sigma = _u64((y - z + 7226116421598831150) ^ _rotr(x, 8))
    if (delta ^ sigma ^ lane) & 1:
        x = _u64((_rotl(delta, 7) + sigma) * 0x9E6C63D0676A9A99)
        y = _u64((_rotr(sigma, 11) ^ x) * 0xC2B2AE3D27D4EB4F)
    else:
        x = _u64((_rotr(delta, 5) ^ sigma) * 0x165667B19E3779F9)
        y = _u64((_rotl(sigma, 13) + x) * 0x85EBCA77C2B2AE63)
    z = _u64(z ^ _bytefold(x + y + lane))
    return x, y, z

def _stage_36(x, y, z, lane):
    q = _u64(x ^ 11400754367493310387 ^ lane)
    w = _u64(y + 180087167212478019 + lane * 3)
    e = _u64(z ^ 5699931637796512421 ^ lane * 7)
    x = _u64((_rotl(q, 9) + _rotr(w, 3) + e) * 0xA0761D6478BD642F)
    y = _u64((_rotl(w, 19) ^ _rotr(e, 5) ^ x) * 0xE7037ED1A0B428DB)
    z = _u64((_rotl(e, 29) + _rotr(q, 7) + y) * 0x8EBC6AF09C88C6E3)
    return x, y, z

def _stage_37(x, y, z, lane):
    m = _hash_pulse(x ^ 11400755467004938598, y ^ lane, z ^ 11580801986535676504, lane + 37)
    r = _rotl(m, lane % 31 + 1)
    x = _u64((x ^ r ^ _bytefold(y)) + 0x9E3779B97F4A7C15)
    y = _u64((y + _rotr(r, 7) ^ _nibble_weave(z, x)) * 0x94D049BB133111EB)
    z = _u64((z ^ _rotl(x, 17) ^ _rotr(y, 23)) * 0x2545F4914F6CDD1D)
    return x, y, z

def _stage_38(x, y, z, lane):
    left = _u64((x + 11400756566516566809) * 0x9E3779B185EBCA87)
    mid = _u64((y ^ 4534772732149323373) * 0xC2B2AE3D27D4EB4F)
    right = _u64((z + 18225002337403084235) * 0x165667B19E3779F9)
    mix = _nibble_weave(_bytefold(left), _rotr(right, 9))
    x = _u64(left ^ _rotl(mid, lane % 27 + 3) ^ mix)
    y = _u64(mid + _rotr(right, lane % 25 + 5) + _bytefold(x))
    z = _u64(right ^ _rotl(left, lane % 23 + 7) ^ _bytefold(y))
    return x, y, z

def _stage_39(x, y, z, lane):
    p = _u64((x ^ y ^ 11400757666028195020) + lane)
    q = _u64((y ^ z ^ 15935487551472521858) + lane * 5)
    r = _u64((z ^ x ^ 15264165650351594334) + lane * 11)
    g1 = _rotl(p, 3) ^ _rotr(q, 7)
    g2 = _rotl(q, 13) ^ _rotr(r, 17)
    g3 = _rotl(r, 29) ^ _rotr(p, 23)
    x = _u64((g1 + g2 + _bytefold(g3)) * 0xDB4F0B9175AE2165)
    y = _u64((g2 ^ g3 ^ _bytefold(g1)) * 0xBBE0563303A4615F)
    z = _u64((g3 + g1 + _bytefold(g2)) * 0xA0F2EC75A1FE1575)
    return x, y, z

def _stage_40(x, y, z, lane):
    twist = _rotl(x ^ 11400758765539823231, 12)
    fold = _bytefold(y + 8889458297086168727)
    gate = _nibble_weave(twist, fold)
    x = _u64((gate ^ z) * 0x100000001B3)
    y = _u64((_rotr(fold ^ x, lane % 31 + 1) + z) * 0xC6A4A7935BD1E995)
    z = _u64((_rotl(gate ^ y, lane % 29 + 3) + x) * 0x9E3779B185EBCA87)
    return x, y, z

def _stage_41(x, y, z, lane):
    anchor = _rotr(y + 11400759865051451442, 11)
    braid = _nibble_weave(z ^ 1843429042699815596, x)
    x = _u64((x ^ anchor ^ lane) + _rotl(braid, lane % 17 + 5))
    y = _u64((y + braid + _bytefold(anchor)) * 0xD6E8FEB86659FD93)
    z = _u64((z ^ x ^ _rotl(y, 7)) * 0xA24BAED4963EE407)
    return x, y, z

def _stage_42(x, y, z, lane):
    drift = _u64((x + y + 11400760964563079653) ^ _rotl(z, 22))
    shard = _u64((z + 13244143862023014081) ^ _rotr(y, 22))
    pulse = _hash_pulse(drift, shard, x, lane)
    x = _u64((drift ^ pulse) * 0x9FB21C651E98DF25)
    y = _u64((shard + _rotl(pulse, 9) + x) * 0xC3A5C85C97CB3127)
    z = _u64((z ^ _bytefold(y) ^ _rotr(x, 13)) + pulse)
    return x, y, z

def _stage_43(x, y, z, lane):
    s1 = _rotl(x ^ 3420818902145634730, 33)
    s2 = _rotr(y + 11400762064074707864, 27)
    s3 = _bytefold(z ^ 6198114607636660950)
    x = _u64((s1 + (s2 ^ lane)) * 0xBF58476D1CE4E5B9)
    y = _u64((s2 + (s3 ^ x)) * 0x94D049BB133111EB)
    z = _u64((s3 + (s1 ^ y)) * 0x369DEA0F31A53F85)
    return x, y, z

def _stage_44(x, y, z, lane):
    orbit = _u64((x * 11400763163586336075) ^ _rotl(y, 56))
    echo = _u64((z * 17598829426959859435) ^ _rotr(x, 44))
    mesh = _nibble_weave(orbit, echo)
    x = _u64(mesh + _rotl(orbit, lane % 21 + 3))
    y = _u64((_bytefold(mesh ^ y) + _rotr(echo, lane % 19 + 5)))
    z = _u64((z ^ x ^ y ^ lane) * 0x27D4EB2F165667C5)
    return x, y, z

def _stage_45(x, y, z, lane):
    delta = _u64((x - y + 11400764263097964286) ^ _rotl(z, 37))
    sigma = _u64((y - z + 10552800172573506304) ^ _rotr(x, 55))
    if (delta ^ sigma ^ lane) & 1:
        x = _u64((_rotl(delta, 7) + sigma) * 0x9E6C63D0676A9A99)
        y = _u64((_rotr(sigma, 11) ^ x) * 0xC2B2AE3D27D4EB4F)
    else:
        x = _u64((_rotr(delta, 5) ^ sigma) * 0x165667B19E3779F9)
        y = _u64((_rotl(sigma, 13) + x) * 0x85EBCA77C2B2AE63)
    z = _u64(z ^ _bytefold(x + y + lane))
    return x, y, z

def _stage_46(x, y, z, lane):
    q = _u64(x ^ 11400765362609592497 ^ lane)
    w = _u64(y + 3506770918187153173 + lane * 3)
    e = _u64(z ^ 12985052914700716643 ^ lane * 7)
    x = _u64((_rotl(q, 9) + _rotr(w, 3) + e) * 0xA0761D6478BD642F)
    y = _u64((_rotl(w, 19) ^ _rotr(e, 5) ^ x) * 0xE7037ED1A0B428DB)
    z = _u64((_rotl(e, 29) + _rotr(q, 7) + y) * 0x8EBC6AF09C88C6E3)
    return x, y, z

def _stage_47(x, y, z, lane):
    m = _hash_pulse(x ^ 11400766462121220708, y ^ lane, z ^ 14907485737510351658, lane + 47)
    r = _rotl(m, lane % 31 + 1)
    x = _u64((x ^ r ^ _bytefold(y)) + 0x9E3779B97F4A7C15)
    y = _u64((y + _rotr(r, 7) ^ _nibble_weave(z, x)) * 0x94D049BB133111EB)
    z = _u64((z ^ _rotl(x, 17) ^ _rotr(y, 23)) * 0x2545F4914F6CDD1D)
    return x, y, z

def _stage_48(x, y, z, lane):
    left = _u64((x + 11400767561632848919) * 0x9E3779B185EBCA87)
    mid = _u64((y ^ 7861456483123998527) * 0xC2B2AE3D27D4EB4F)
    right = _u64((z + 7063379540597736841) * 0x165667B19E3779F9)
    mix = _nibble_weave(_bytefold(left), _rotr(right, 9))
    x = _u64(left ^ _rotl(mid, lane % 27 + 3) ^ mix)
    y = _u64(mid + _rotr(right, lane % 25 + 5) + _bytefold(x))
    z = _u64(right ^ _rotl(left, lane % 23 + 7) ^ _bytefold(y))
    return x, y, z

def _stage_49(x, y, z, lane):
    p = _u64((x ^ y ^ 11400768661144477130) + lane)
    q = _u64((y ^ z ^ 815427228737645396) + lane * 5)
    r = _u64((z ^ x ^ 4102542853546246940) + lane * 11)
    g1 = _rotl(p, 3) ^ _rotr(q, 7)
    g2 = _rotl(q, 13) ^ _rotr(r, 17)
    g3 = _rotl(r, 29) ^ _rotr(p, 23)
    x = _u64((g1 + g2 + _bytefold(g3)) * 0xDB4F0B9175AE2165)
    y = _u64((g2 ^ g3 ^ _bytefold(g1)) * 0xBBE0563303A4615F)
    z = _u64((g3 + g1 + _bytefold(g2)) * 0xA0F2EC75A1FE1575)
    return x, y, z

def _stage_50(x, y, z, lane):
    twist = _rotl(x ^ 11400769760656105341, 62)
    fold = _bytefold(y + 12216142048060843881)
    gate = _nibble_weave(twist, fold)
    x = _u64((gate ^ z) * 0x100000001B3)
    y = _u64((_rotr(fold ^ x, lane % 31 + 1) + z) * 0xC6A4A7935BD1E995)
    z = _u64((_rotl(gate ^ y, lane % 29 + 3) + x) * 0x9E3779B185EBCA87)
    return x, y, z

def _stage_51(x, y, z, lane):
    anchor = _rotr(y + 11400770860167733552, 58)
    braid = _nibble_weave(z ^ 5170112793674490750, x)
    x = _u64((x ^ anchor ^ lane) + _rotl(braid, lane % 17 + 5))
    y = _u64((y + braid + _bytefold(anchor)) * 0xD6E8FEB86659FD93)
    z = _u64((z ^ x ^ _rotl(y, 7)) * 0xA24BAED4963EE407)
    return x, y, z

def _stage_52(x, y, z, lane):
    drift = _u64((x + y + 11400771959679361763) ^ _rotl(z, 9))
    shard = _u64((z + 16570827612997689235) ^ _rotr(y, 3))
    pulse = _hash_pulse(drift, shard, x, lane)
    x = _u64((drift ^ pulse) * 0x9FB21C651E98DF25)
    y = _u64((shard + _rotl(pulse, 9) + x) * 0xC3A5C85C97CB3127)
    z = _u64((z ^ _bytefold(y) ^ _rotr(x, 13)) + pulse)
    return x, y, z

def _stage_53(x, y, z, lane):
    s1 = _rotl(x ^ 10705940179049838952, 17)
    s2 = _rotr(y + 11400773059190989974, 14)
    s3 = _bytefold(z ^ 9524798358611336104)
    x = _u64((s1 + (s2 ^ lane)) * 0xBF58476D1CE4E5B9)
    y = _u64((s2 + (s3 ^ x)) * 0x94D049BB133111EB)
    z = _u64((s3 + (s1 ^ y)) * 0x369DEA0F31A53F85)
    return x, y, z

def _stage_54(x, y, z, lane):
    orbit = _u64((x * 11400774158702618185) ^ _rotl(y, 37))
    echo = _u64((z * 2478769104224982973) ^ _rotr(x, 28))
    mesh = _nibble_weave(orbit, echo)
    x = _u64(mesh + _rotl(orbit, lane % 21 + 3))
    y = _u64((_bytefold(mesh ^ y) + _rotr(echo, lane % 19 + 5)))
    z = _u64((z ^ x ^ y ^ lane) * 0x27D4EB2F165667C5)
    return x, y, z

stages = [
    _stage_0,
    _stage_1,
    _stage_2,
    _stage_3,
    _stage_4,
    _stage_5,
    _stage_6,
    _stage_7,
    _stage_8,
    _stage_9,
    _stage_10,
    _stage_11,
    _stage_12,
    _stage_13,
    _stage_14,
    _stage_15,
    _stage_16,
    _stage_17,
    _stage_18,
    _stage_19,
    _stage_20,
    _stage_21,
    _stage_22,
    _stage_23,
    _stage_24,
    _stage_25,
    _stage_26,
    _stage_27,
    _stage_28,
    _stage_29,
    _stage_30,
    _stage_31,
    _stage_32,
    _stage_33,
    _stage_34,
    _stage_35,
    _stage_36,
    _stage_37,
    _stage_38,
    _stage_39,
    _stage_40,
    _stage_41,
    _stage_42,
    _stage_43,
    _stage_44,
    _stage_45,
    _stage_46,
    _stage_47,
    _stage_48,
    _stage_49,
    _stage_50,
    _stage_51,
    _stage_52,
    _stage_53,
    _stage_54,
]

def _braid_links(idx, lane, x, y, z):
    n = len(stages)
    flux = _u64((x ^ _rotl(y, (idx % 23) + 3) ^ _rotr(z, (lane % 29) + 1)) + idx + lane)
    jump = ((flux >> 7) ^ (flux >> 19) ^ (flux >> 41)) % n
    sway = ((flux * 0x9E3779B185EBCA87) ^ _bytefold(flux)) % n
    link_a = (idx + jump + lane + (x & 0x1F)) % n
    link_b = (idx ^ sway ^ (y & 0x3F) ^ ((z >> 11) & 0x1F)) % n
    if link_a == idx:
        link_a = (link_a + 1 + (flux & 0x7)) % n
    if link_b in (idx, link_a):
        link_b = (link_b + 3 + ((flux >> 5) & 0xF)) % n
    return link_a, link_b, flux

def _labyrinth_number(testata, korpo, pending, salt):
    x, y, z = _seed_triplet(testata, korpo, pending, salt)
    rounds_seed = _det_uint(f'{salt}:{pending}:{testata}:{korpo}')
    rounds = 41 + (rounds_seed % 37)
    pending_int = int(pending)
    lane = (pending_int % 53) + 1
    stages_local = stages
    n = len(stages_local)
    rotl = _rotl
    rotr = _rotr
    u64 = _u64
    bytefold = _bytefold

    for r in range(rounds):
        idx = (x ^ rotl(y, (r % 17) + 5) ^ rotr(z, (r % 13) + 7) ^ (r * 0x9E3779B1)) % n
        x, y, z = stages_local[idx](x, y, z, lane + r)

        lane_r = lane + r
        flux = u64((x ^ rotl(y, (idx % 23) + 3) ^ rotr(z, (lane_r % 29) + 1)) + idx + lane_r)
        jump = ((flux >> 7) ^ (flux >> 19) ^ (flux >> 41)) % n
        sway = ((flux * 0x9E3779B185EBCA87) ^ bytefold(flux)) % n
        link_a = (idx + jump + lane_r + (x & 0x1F)) % n
        link_b = (idx ^ sway ^ (y & 0x3F) ^ ((z >> 11) & 0x1F)) % n
        if link_a == idx:
            link_a = (link_a + 1 + (flux & 0x7)) % n
        if link_b in (idx, link_a):
            link_b = (link_b + 3 + ((flux >> 5) & 0xF)) % n

        if (r + idx + lane) % 2 == 0:
            x, y, z = stages_local[link_a](x, y, z, lane + link_a)
        else:
            x, y, z = stages_local[link_b](x, y, z, lane + link_b)

        if ((r + idx + (flux & 0xF)) % 5 == 0) or ((flux >> 17) & 1):
            bounce = (n - 1 - idx + lane + (flux % 11)) % n
            x, y, z = stages_local[bounce](x, y, z, lane + bounce)

        x = u64(x ^ rotl(flux + z, (idx % 19) + 1))
        y = u64(y + rotr(flux ^ x, (lane % 23) + 1))
        z = u64(z ^ bytefold(x + y + flux + r))
        lane = (lane + idx + link_a + link_b + (x & 0xF) + ((flux >> 9) & 0x1F)) % 97 + 1

    chaotic = hashlib.sha3_512(f'{x}:{y}:{z}:{salt}:{lane}'.encode()).digest()
    num = int.from_bytes(chaotic[:16], 'big') ^ x ^ rotl(y, 11) ^ rotr(z, 29)
    return u64(num)

def get_trombino(testata, korpo, pending, seed_key):
    bag = []
    for turn in range(4):
        salt = f'trombino-{turn}-{seed_key}'
        value = _labyrinth_number(testata, korpo, pending, salt)
        bag.append(str(value))
    digits = ''.join(ch for chunk in bag for ch in chunk if ch.isdigit())
    if not digits:
        digits = '3141592653589793238462643383279'
    idx1 = _det_uint(f'{seed_key}:idx1:{testata}:{korpo}') % len(digits)
    idx2 = _det_uint(f'{seed_key}:idx2:{pending}:{len(digits)}') % len(digits)
    return digits[idx1] + digits[idx2]

def _pendings(value, pending, lane, seed_key):
    value_str = str(value)
    pending_int = int(pending)
    churn = _labyrinth_number(value_str, pending, pending, f'{lane}-{seed_key}')
    loops = 3 + (churn % 4)
    for i in range(loops):
        pivot = (churn >> (i * 9)) % max(1, len(value_str))
        value_str = value_str[pivot:] + value_str[:pivot]
        mirror = value_str[::-1]
        weave = ''.join(a + b for a, b in zip(value_str, mirror))
        value_str = weave[:len(value_str)] if weave else value_str
        churn = _u64(churn ^ _rotl(churn + i + pending_int + lane, (i * 7 + lane) % 63 + 1))
    return int(value_str) if value_str else value

def _extend_korpo(korpo, pending, limit, seed_key):
    chance = 91
    lane = 0
    while len(korpo) < limit:
        lane += 1
        pulse = _labyrinth_number(korpo, pending, pending, f'extend-{lane}-{seed_key}')
        roll = int(randint(1, 100, 1, key=f'{seed_key}:roll:{lane}:{korpo}'))
        threshold = max(11, chance - (pulse % 19))
        if roll <= threshold:
            addition = _det_uint(f'{seed_key}:digit:{lane}:{pulse}') % 100_000
            digit = str((pulse ^ addition) % 10)
            korpo += digit
            chance = max(23, chance - 6 - (lane % 4))
        else:
            break
    return korpo

def _generate_code_for_timezone(tz, pending, limit, generation_time, code_index):
    seed_key = f'{tz}|{generation_time}|{code_index}|{pending}'
    testata = randint(0, 999, 3, key=f'{seed_key}:testata')
    korpo = randint(0, 999, 3, key=f'{seed_key}:korpo')
    korpo = _extend_korpo(korpo, pending, limit, seed_key)
    trombino = get_trombino(testata, korpo, pending, seed_key)

    transformed_digits = []
    for lane, digit in enumerate(korpo, start=1):
        shifted = _pendings(int(digit), pending, lane, seed_key)
        mixer = _labyrinth_number(testata, str(shifted), pending, f'mix-{tz}-{lane}-{generation_time}-{seed_key}')
        offset = _det_uint(f'{seed_key}:offset:{lane}:{shifted}') % 1000
        transformed_digits.append(str((shifted + mixer + offset) % 10))
    final_korpo = ''.join(transformed_digits)
    code = f"{testata}-{final_korpo}.{trombino}"
    return code



def _build_timezone_payload(task):
    tz, pending, limit, generation_time = task
    codes_for_timezone = []
    for code_index in range(5):
        code = _generate_code_for_timezone(tz, pending, limit, generation_time, code_index)
        codes_for_timezone.append(code)
    return {
        "timezone": tz,
        "codes": codes_for_timezone,
        "generation_time": generation_time
    }

def _parallel_payloads(tasks, workers):
    if workers <= 1:
        return [_build_timezone_payload(task) for task in tasks]

    start_methods = mp.get_all_start_methods()
    if "fork" in start_methods:
        method = "fork"
    elif "spawn" in start_methods:
        method = "spawn"
    else:
        return [_build_timezone_payload(task) for task in tasks]

    ctx = mp.get_context(method)
    chunk = max(1, len(tasks) // (workers * 4))
    with ctx.Pool(processes=workers) as pool:
        return pool.map(_build_timezone_payload, tasks, chunksize=chunk)


def shentropye(limit=None):
    timezones = sorted(available_timezones())
    if limit is None:
        limit = 3

    tasks = []
    for tz in timezones:
        tz_obj = ZoneInfo(tz)
        now = datetime.datetime.now(tz_obj)
        generation_time = now.strftime('%Y-%m-%d')
        pending = randint(0, 9999, 4, key=f'{tz}|{generation_time}|pending')
        tasks.append((tz, pending, limit, generation_time))

    workers = min(32, os.cpu_count() or 1, len(tasks))
    data = _parallel_payloads(tasks, workers)

    with open("shentropye_codes.json", "w") as f:
        json.dump(data, f, indent=4)


if __name__ == "__main__":
    mp.freeze_support()
    shentropye(limit=3)
