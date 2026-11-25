#include <math.h>
#include <stdio.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>

/* Convert a stream of V4L2 10-bit packed Bayer frames (pgAA / pBAA) to grey8 or
 * half-resolution RGB24 (2x2 block debayer).
 *
 * Usage: unpack10 [width height bytesperline [out.rgb|-] [pattern|gray]]
 * Defaults: 2104 1560 2640 - gray   (Z Flip3 rear main imx258, /dev/video4)
 * Patterns: bggr grbg rggb gbrg (row0 then row1), or "gray".
 *
 * Input rows are bpl bytes (row padding is skipped). Each 2x2 Bayer block holds
 * one R, two G and one B sample, so a block average is a true RGB pixel at half
 * resolution: 4 lookups instead of a full bilinear kernel, and 4x less data for
 * the MJPEG encoder. Frames are consumed until EOF, so the V4L2 pipe is never
 * restarted per frame. OUT receives frame 0 only (cover-preview source). */

static int cfa[2][2];   /* 0=R 1=G 2=B */
static int color, w, h, bpl, ow, oh;
static size_t row_in;
static unsigned char *in, *rows, *rgb;
static FILE *dump;
static unsigned char lut[3][256];
static double gain[3] = { 1.5, 1.0, 1.7 };   /* R G B, refined per frame (grey-world) */

static void build_lut(void)
{
    for (int c = 0; c < 3; c++) {
        for (int i = 0; i < 256; i++) {
            double v = i * gain[c] / 255.0;
            if (v > 1.0) v = 1.0;
            lut[c][i] = (unsigned char)(255.0 * pow(v, 1.0 / 1.8) + 0.5);
        }
    }
}

static void parse_pattern(const char *s)
{
    for (int i = 0; i < 4; i++)
        cfa[i / 2][i % 2] = s[i] == 'r' ? 0 : s[i] == 'b' ? 2 : 1;
}

/* Read one padded Bayer row and unpack it to 8-bit samples. Returns 0 on EOF. */
static int read_row(unsigned char *dst)
{
    static unsigned char pad[64];
    if (fread(in, 1, row_in, stdin) != row_in)
        return 0;
    for (int x = 0; x < w; x += 4) {
        const unsigned char *b = in + (size_t)x * 5 / 4;
        /* MIPI RAW10: four 8-bit high parts, then one byte holding the four
         * 2-bit low parts. Getting this wrong yields a period-4 pattern that
         * masquerades as extreme image noise. */
        unsigned int low = b[4];
        dst[x]     = (unsigned char)((b[0] << 2 | ((low >> 6) & 3)) >> 2);
        dst[x + 1] = (unsigned char)((b[1] << 2 | ((low >> 4) & 3)) >> 2);
        dst[x + 2] = (unsigned char)((b[2] << 2 | ((low >> 2) & 3)) >> 2);
        dst[x + 3] = (unsigned char)((b[3] << 2 | (low & 3)) >> 2);
    }
    size_t skip = (size_t)bpl - row_in;
    while (skip > 0) {
        size_t n = skip > sizeof(pad) ? sizeof(pad) : skip;
        if (fread(pad, 1, n, stdin) != n)
            return 0;
        skip -= n;
    }
    return 1;
}

static void write_out(const unsigned char *buf, size_t len)
{
    fwrite(buf, 1, len, stdout);
    if (dump)
        fwrite(buf, 1, len, dump);
}

/* One frame; returns 0 when the input stream ends. */
static int frame(void)
{
    if (!color) {
        for (int y = 0; y < h; y++) {
            if (!read_row(in))
                return 0;
            write_out(in, (size_t)w);
        }
        return 1;
    }
    build_lut();
    double sum[3] = { 0, 0, 0 };
    double cnt = 0;
    for (int j = 0; j < oh; j++) {
        unsigned char *r0 = rows, *r1 = rows + w;
        if (!read_row(r0) || !read_row(r1))
            return 0;
        for (int i = 0; i < ow; i++) {
            int x = 2 * i + (2 * i + 1 >= w ? -1 : 0);
            unsigned int s[3] = { 0, 0, 0 };
            int n[3] = { 0, 0, 0 };
            for (int k = 0; k < 2; k++) {
                for (int m = 0; m < 2; m++) {
                    int c = cfa[k][(x + m) & 1];
                    s[c] += (k ? r1 : r0)[x + m];
                    n[c]++;
                }
            }
            for (int c = 0; c < 3; c++) {
                unsigned char v = (unsigned char)(s[c] / n[c]);
                sum[c] += v;            /* statistics in the linear domain */
                rgb[i * 3 + c] = lut[c][v];
            }
            cnt++;
        }
        write_out(rgb, (size_t)ow * 3);
    }
    /* Grey-world white balance on linear means, gently damped and clamped: a
     * percentile anchor overshoots on point-lit dark scenes and flips the cast
     * to the opposite hue. Green is the reference because Bayer green has the
     * highest gain and the least noise. */
    if (cnt > 0 && sum[1] > 0) {
        const double target[3] = { sum[1] / (sum[0] ? sum[0] : 1), 1.0,
                                   sum[1] / (sum[2] ? sum[2] : 1) };
        for (int c = 0; c < 3; c++) {
            double t = target[c] < 0.7 ? 0.7 : target[c] > 4.0 ? 4.0 : target[c];
            gain[c] = 0.85 * gain[c] + 0.15 * t;
            if (gain[c] < 0.7) gain[c] = 0.7;
            if (gain[c] > 4.0) gain[c] = 4.0;
        }
    }
    return 1;
}

int main(int argc, char **argv)
{
    w = 2104; h = 1560; bpl = 2640;
    if (argc > 1) w = atoi(argv[1]);
    if (argc > 2) h = atoi(argv[2]);
    if (argc > 3) bpl = atoi(argv[3]);
    const char *out_path = argc > 4 && strcmp(argv[4], "-") ? argv[4] : NULL;
    const char *pat = argc > 5 ? argv[5] : "gray";
    if (w <= 0 || h <= 0 || bpl < w * 5 / 4) return 2;

    color = strcmp(pat, "gray") != 0;
    if (color) parse_pattern(pat);
    row_in = (size_t)w * 5 / 4;
    ow = color ? w / 2 : w;
    oh = color ? h / 2 : h;

    in = malloc(row_in);
    rows = malloc((size_t)w * 2);
    rgb = malloc((size_t)ow * 3);
    if (!in || !rows || !rgb) return 3;
    dump = out_path ? fopen(out_path, "wb") : NULL;

    static unsigned char ibuf[65536], obuf[65536];
    setvbuf(stdin, (char *)ibuf, _IOFBF, sizeof(ibuf));
    setvbuf(stdout, (char *)obuf, _IOFBF, sizeof(obuf));

    while (frame()) {
        if (dump) {                     /* keep frame 0 only */
            fclose(dump);
            dump = NULL;
        }
    }

    fflush(stdout);
    if (dump) fclose(dump);
    free(in);
    free(rows);
    free(rgb);
    return 0;
}
