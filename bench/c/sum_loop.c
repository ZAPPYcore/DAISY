#include <stdint.h>
#include <stdio.h>

int main(void) {
  int64_t acc = 0;
  for (int64_t i = 1; i <= 5000000; i++) {
    acc += i;
  }
  printf("%lld\n", (long long)acc);
  return 0;
}


