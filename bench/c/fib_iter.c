#include <stdint.h>
#include <stdio.h>

int main(void) {
  int64_t a = 0;
  int64_t b = 1;
  for (int64_t i = 0; i < 2000000; i++) {
    int64_t tmp = a + b;
    a = b;
    b = tmp;
  }
  printf("%lld\n", (long long)a);
  return 0;
}


