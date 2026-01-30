#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>

int main(void) {
  int64_t cap = 0;
  int64_t len = 0;
  int64_t* data = NULL;
  for (int64_t i = 0; i < 200000; i++) {
    if (len == cap) {
      int64_t next = cap == 0 ? 4 : cap * 2;
      int64_t* buf = (int64_t*)realloc(data, (size_t)next * sizeof(int64_t));
      if (!buf) {
        free(data);
        return 1;
      }
      data = buf;
      cap = next;
    }
    data[len++] = i;
  }
  printf("%lld\n", (long long)len);
  free(data);
  return 0;
}


