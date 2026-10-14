import struct, hashlib, sys
def parse(path):
    d = open(path, 'rb').read()
    assert d[:4] == b'AVB0', "no AVB0 magic"
    (maj, mn, auth_sz, aux_sz, alg, hoff, hsz, soff, ssz, poff, psz, pmoff, pmsz,
     doff, dsz, rb, flags, rbloc) = struct.unpack('>IIQQIQQQQQQQQQQQII', d[4:128])
    rel = d[128:176].split(b'\0')[0].decode()
    aux = 256 + auth_sz
    desc = d[aux + doff: aux + doff + dsz]
    out = []; p = 0
    while p < len(desc):
        tag, n = struct.unpack('>QQ', desc[p:p+16]); b = desc[p+16:p+16+n]; p += 16 + ((n + 7) & ~7)
        if tag == 2:      # hash descriptor
            image_size = struct.unpack('>Q', b[:8])[0]
            halg = b[8:40].split(b'\0')[0].decode()
            pl, sl, dl, fl = struct.unpack('>IIII', b[40:56])
            name = b[116:116+pl].decode(); salt = b[116+pl:116+pl+sl]; dig = b[116+pl+sl:116+pl+sl+dl]
            out.append(('hash', name, image_size, halg, salt, dig, fl))
        elif tag == 1:    # hashtree descriptor
            image_size = struct.unpack('>Q', b[4:12])[0]
            halg = b[56:88].split(b'\0')[0].decode()
            pl, sl, dl, fl = struct.unpack('>IIII', b[88:104])
            name = b[164:164+pl].decode()
            out.append(('hashtree', name, image_size, halg, fl))
        elif tag == 4:    # chain partition descriptor
            rbl, pl, kl = struct.unpack('>III', b[:12])
            name = b[76:76+pl].decode(); key = b[76+pl:76+pl+kl]
            out.append(('chain', name, rbl, kl, hashlib.sha256(key).hexdigest()[:16]))
        elif tag == 0:    # property
            kl, vl = struct.unpack('>QQ', b[:16]); k = b[16:16+kl].decode(); v = b[16+kl+1:16+kl+1+vl].decode(errors='replace')
            out.append(('prop', k, v))
        elif tag == 3:
            fl, cl = struct.unpack('>II', b[:8]); out.append(('cmdline', fl, b[8:8+cl].decode(errors='replace')))
        else:
            out.append(('tag%d' % tag, n))
    return dict(ver=(maj, mn), alg=alg, flags=flags, rb=rb, rbloc=rbloc, rel=rel, auth=auth_sz, aux=aux_sz,
                desc=out, data=d, real=256 + auth_sz + aux_sz, pk=d[aux+poff:aux+poff+psz])
if __name__ == '__main__':
    for f in sys.argv[1:]:
        v = parse(f)
        print("\n=====", f.split('/')[-1], "| libavb %d.%d | algo %d | flags %d | rollback_index %d | rb_location %d | release '%s' | real size %d | pubkey sha256 %s.." %
              (v['ver'][0], v['ver'][1], v['alg'], v['flags'], v['rb'], v['rbloc'], v['rel'], v['real'], hashlib.sha256(v['pk']).hexdigest()[:16]))
        for x in v['desc']:
            if x[0] == 'hash': print("  HASH     %-14s image_size=%-9d %s flags=%d digest=%s.." % (x[1], x[2], x[3], x[6], x[5].hex()[:16]))
            elif x[0] == 'chain': print("  CHAIN    %-14s rollback_loc=%d pubkey_len=%d key_sha256=%s.." % (x[1], x[2], x[3], x[4]))
            elif x[0] == 'hashtree': print("  HASHTREE %-14s image_size=%-10d %s flags=%d" % (x[1], x[2], x[3], x[4]))
            elif x[0] == 'prop': print("  PROP     %s = %s" % (x[1], x[2][:80]))
            elif x[0] == 'cmdline': print("  CMDLINE  flags=%d %s" % (x[1], x[2][:100]))
            else: print("  ", x)
