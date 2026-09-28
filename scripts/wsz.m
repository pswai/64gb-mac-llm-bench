// Prints Metal's effective GPU working-set limit (what iogpu.wired_limit_mb controls).
#import <Metal/Metal.h>
#include <stdio.h>
int main(void) {
    id<MTLDevice> d = MTLCreateSystemDefaultDevice();
    unsigned long long b = [d recommendedMaxWorkingSetSize];
    printf("recommendedMaxWorkingSetSize=%llu bytes (%.2f GiB, %llu MiB)\n", b, b / 1073741824.0, b >> 20);
    return 0;
}
