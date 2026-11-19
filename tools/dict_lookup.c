#include <CoreFoundation/CoreFoundation.h>
#include <DictionaryServices/DictionaryServices.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static char *copy_cfstring(CFStringRef s) {
    if (!s) return NULL;
    CFIndex len = CFStringGetLength(s);
    CFIndex max = CFStringGetMaximumSizeForEncoding(len, kCFStringEncodingUTF8) + 1;
    char *buf = malloc(max);
    if (!buf) return NULL;
    if (!CFStringGetCString(s, buf, max, kCFStringEncodingUTF8)) {
        free(buf);
        return NULL;
    }
    return buf;
}

int main(int argc, char **argv) {
    if (argc < 2) {
        fprintf(stderr, "usage: dict_lookup <words.txt>\n");
        return 1;
    }
    FILE *in = fopen(argv[1], "r");
    if (!in) { perror("fopen"); return 1; }
    char line[1024];
    while (fgets(line, sizeof(line), in)) {
        line[strcspn(line, "\r\n")] = 0;
        if (line[0] == 0) continue;
        CFStringRef w = CFStringCreateWithCString(NULL, line, kCFStringEncodingUTF8);
        if (!w) continue;
        CFRange range = CFRangeMake(0, CFStringGetLength(w));
        CFStringRef def = DCSCopyTextDefinition(NULL, w, range);
        char *defstr = copy_cfstring(def);
        if (defstr) {
            for (char *p = defstr; *p; ++p) {
                if (*p == '\n' || *p == '\r' || *p == '\t') *p = ' ';
            }
        }
        // The definition starts with "word | phonetic | meaning".
        // Output the whole definition; Python extracts the fields.
        printf("%s\t%s\n", line, defstr ? defstr : "");
        free(defstr);
        if (def) CFRelease(def);
        CFRelease(w);
    }
    fclose(in);
    return 0;
}
