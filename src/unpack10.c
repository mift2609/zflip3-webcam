#include <stdio.h>
#include <stdint.h>

/* Convert V4L2 10-bit packed Bayer (pgAA / SGRBG10P) to 8-bit grey.
 * Four 10-bit samples are packed into five bytes, little-endian bit order.
 * Output is one byte per pixel, suitable for ffmpeg rawvideo gray input. */
int main(void) {
    unsigned char in[5];
    unsigned char out[4];
    static unsigned char ibuf[65536], obuf[65536];
    setvbuf(stdin, (char *)ibuf, _IOFBF, sizeof(ibuf));
    setvbuf(stdout, (char *)obuf, _IOFBF, sizeof(obuf));

    while (fread(in, 1, 5, stdin) == 5) {
        uint16_t p0 = ((uint16_t)in[0] << 2) | (in[1] >> 6);
        uint16_t p1 = ((uint16_t)(in[1] & 0x3f) << 4) | (in[2] >> 4);
        uint16_t p2 = ((uint16_t)(in[2] & 0x0f) << 6) | (in[3] >> 2);
        uint16_t p3 = ((uint16_t)(in[3] & 0x03) << 8) | in[4];
        out[0] = (unsigned char)(p0 >> 2);
        out[1] = (unsigned char)(p1 >> 2);
        out[2] = (unsigned char)(p2 >> 2);
        out[3] = (unsigned char)(p3 >> 2);
        if (fwrite(out, 1, 4, stdout) != 4) return 1;
    }
    fflush(stdout);
    return 0;
}
