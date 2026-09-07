/* Drives the original C bots with a scripted guess sequence and a scripted
   opponent so their moves can be diffed against the Python ports.

   usage: harness iocaine|greenberg guesses.txt opponent.txt > moves.txt

   The originals are pulled in by #include; verify.py fetches them. */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define trials 1001            /* one more than the rounds we play: Greenberg indexes gear[][T] */
#define rock 0
#define paper 1
#define scissors 2

int my_history[trials + 1], opp_history[trials + 1];
static FILE *guesses;

int biased_roshambo(double prob_rock, double prob_paper) {
    int g;
    if (fscanf(guesses, "%d", &g) != 1) { fprintf(stderr, "out of guesses\n"); exit(1); }
    return g;
}

#include "iocaine.c"
#include "greenberg_fixed.c"

int main(int argc, char **argv) {
    if (argc != 4) { fprintf(stderr, "usage: %s iocaine|greenberg guesses opponent\n", argv[0]); return 2; }
    guesses = fopen(argv[2], "r");
    FILE *opp = fopen(argv[3], "r");
    if (!guesses || !opp) { perror("open"); return 2; }
    int (*bot)(void) = strcmp(argv[1], "iocaine") == 0 ? iocainebot : (int (*)(void))greenberg;
    int o, n = 0;
    my_history[0] = opp_history[0] = 0;
    while (n < trials - 1 && fscanf(opp, "%d", &o) == 1) {
        int m = bot();
        ++n;
        my_history[n] = m; opp_history[n] = o;
        my_history[0] = opp_history[0] = n;
        printf("%d\n", m);
    }
    return 0;
}
