import hashlib, string

MAGIC = '$1$'
ITOA64 = "./0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"

def to64(v, n):
    ret = ''
    while n - 1 >= 0:
        n -= 1
        ret += ITOA64[v & 0x3f]
        v >>= 6
    return ret

def unix_md5_crypt(pw, salt, magic=None):
    if magic is None:
        magic = MAGIC
    if salt[:len(magic)] == magic:
        salt = salt[len(magic):]
    try:
        salt = string.split(salt, '$', 1)[0]
    except AttributeError:
        salt = salt.decode("utf-8").split('$', 1)[0].encode("utf-8")
    salt = salt[:8]
    try:
        ctx = pw + magic + salt
    except TypeError:
        ctx = pw + magic.encode("utf-8") + salt
    final = hashlib.md5(pw + salt + pw).digest()
    for pl in range(len(pw), 0, -16):
        ctx += final[:16] if pl > 16 else final[:pl]
    i = len(pw)
    while i:
        if i & 1:
            try:
                ctx += chr(0)
            except TypeError:
                ctx += chr(0).encode("utf-8")
        else:
            try:
                ctx += pw[0]
            except TypeError:
                ctx += chr(pw[0]).encode("utf-8")
        i >>= 1
    final = hashlib.md5(ctx).digest()
    for i in range(1000):
        ctx1 = b''
        ctx1 += pw if (i & 1) else final[:16]
        if i % 3: ctx1 += salt
        if i % 7: ctx1 += pw
        ctx1 += final[:16] if (i & 1) else pw
        final = hashlib.md5(ctx1).digest()
    passwd = ''
    try:
        passwd += to64((int(ord(final[0]))<<16)|(int(ord(final[6]))<<8)|(int(ord(final[12]))), 4)
        passwd += to64((int(ord(final[1]))<<16)|(int(ord(final[7]))<<8)|(int(ord(final[13]))), 4)
        passwd += to64((int(ord(final[2]))<<16)|(int(ord(final[8]))<<8)|(int(ord(final[14]))), 4)
        passwd += to64((int(ord(final[3]))<<16)|(int(ord(final[9]))<<8)|(int(ord(final[15]))), 4)
        passwd += to64((int(ord(final[4]))<<16)|(int(ord(final[10]))<<8)|(int(ord(final[5]))), 4)
        passwd += to64(int(ord(final[11])), 2)
        return magic + salt + '$' + passwd
    except TypeError:
        passwd += to64((int(final[0])<<16)|(int(final[6])<<8)|(int(final[12])), 4)
        passwd += to64((int(final[1])<<16)|(int(final[7])<<8)|(int(final[13])), 4)
        passwd += to64((int(final[2])<<16)|(int(final[8])<<8)|(int(final[14])), 4)
        passwd += to64((int(final[3])<<16)|(int(final[9])<<8)|(int(final[15])), 4)
        passwd += to64((int(final[4])<<16)|(int(final[10])<<8)|(int(final[5])), 4)
        passwd += to64(int(final[11]), 2)
        return magic + salt.decode("utf-8") + '$' + passwd

md5crypt = unix_md5_crypt
