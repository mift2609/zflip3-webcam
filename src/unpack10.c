#include <stdio.h>
#include <stdint.h>
#include <stdlib.h>

/* Convert V4L2 10-bit packed Bayer (pgAA / SGRBG10P) to 8-bit grey.
 * Usage: unpack10 [width height bytesperline]
 * Defaults: 1824 1368 2288 (Z Flip3 front camera /dev/video1).
 * Four 10-bit samples are packed into five bytes; each row may have padding. */
int main(int argc, char **argv) {
    int w = 1824, h = 1368, bpl = 2288;
    if (argc > 1) w = atoi(argv[1]);
    if (argc > 2) h = atoi(argv[2]);
    if (argc > 3) bpl = atoi(argv[3]);
    if (w <= 0 || h <= 0 || bpl < w * 5 / 4) return 2;

    size_t row_in = (size_t)w * 5 / 4;
    size_t row_out = (size_t)w;
    unsigned char *in = malloc(row_in);
    unsigned char *out = malloc(row_out);
    unsigned char pad[64];
    if (!in || !out) return 3;

    static unsigned char ibuf[65536], obuf[65536];
    setvbuf(stdin, (char *)ibuf, _IOFBF, sizeof(ibuf));
    setvbuf(stdout, (char *)obuf, _IOFBF, sizeof(obuf));

    for (int y = 0; y < h; y++) {
        if (fread(in, 1, row_in, stdin) != row_in) goto done;
        for (int x = 0; x < w; x += 4) {
            const unsigned char *b = in + (size_t)x * 5 / 4;
            uint16_t p0 = ((uint16_t)b[0] << 2) | (b[1] >> 6);
            uint16_t p1 = ((uint16_t)(b[1] & 0x3f) << 4) | (b[2] >> 4);
            uint16_t p2 = ((uint16_t)(b[2] & 0x0f) << 6) | (b[3] >> 2);
            uint16_t p3 = ((uint16_t)(b[3] & 0x03) << 8) | b[4];
            out[x] = (unsigned char)(p0 >> 2);
            out[x + 1] = (unsigned char)(p1 >> 2);
            out[x + 2] = (unsigned char)(p2 >> 2);
            out[x + 3] = (unsigned char)(p3 >> 2);
        }
        if (fwrite(out, 1, row_out, stdout) != row_out) goto done;
        size_t skip = (size_t)bpl - row_in;
        while (skip > 0) {
            size_t n = skip > sizeof(pad) ? sizeof(pad) : skip;
            if (fread(pad, 1, n, stdin) != n) goto done;
            skip -= n;
        }
    }
done:
    fflush(stdout);
    free(in);
    free(out);
    return 0;
}
