#include "rt.h"

#include <errno.h>
#include <limits.h>
#include <stdio.h>
#ifndef _WIN32
#include <stdatomic.h>
#endif
#include <stdlib.h>
#include <string.h>
#ifdef _WIN32
#include <process.h>
#include <direct.h>
#include <winsock2.h>
#include <ws2tcpip.h>
#else
#include <pthread.h>
#include <sys/socket.h>
#include <sys/stat.h>
#include <sys/types.h>
#include <netdb.h>
#include <unistd.h>
#endif

int64_t daisy_print_int(int64_t value) {
  printf("%lld\n", (long long)value);
  return 0;
}

int64_t daisy_print_str(const char* value) {
  if (!value) {
    printf("\n");
    return 0;
  }
  printf("%s\n", value);
  return 0;
}

static int daisy_error_initialized = 0;
#ifdef _WIN32
static __declspec(thread) char daisy_last_error[256];
#else
static _Thread_local char daisy_last_error[256];
#endif

#ifdef _WIN32
static volatile LONG64 daisy_string_live = 0;
static volatile LONG64 daisy_vec_live = 0;
static volatile LONG64 daisy_buffer_live = 0;
static volatile LONG64 daisy_channel_live = 0;
#else
static _Atomic int64_t daisy_string_live = 0;
static _Atomic int64_t daisy_vec_live = 0;
static _Atomic int64_t daisy_buffer_live = 0;
static _Atomic int64_t daisy_channel_live = 0;
#endif

static void daisy_track_string_alloc(const void* ptr) {
  if (!ptr) {
    return;
  }
#ifdef _WIN32
  InterlockedIncrement64(&daisy_string_live);
#else
  atomic_fetch_add(&daisy_string_live, 1);
#endif
}

static void daisy_track_string_free(const void* ptr) {
  if (!ptr) {
    return;
  }
#ifdef _WIN32
  InterlockedDecrement64(&daisy_string_live);
#else
  atomic_fetch_sub(&daisy_string_live, 1);
#endif
}

static void daisy_track_vec_alloc(const void* ptr) {
  if (!ptr) {
    return;
  }
#ifdef _WIN32
  InterlockedIncrement64(&daisy_vec_live);
#else
  atomic_fetch_add(&daisy_vec_live, 1);
#endif
}

static void daisy_track_vec_free(const void* ptr) {
  if (!ptr) {
    return;
  }
#ifdef _WIN32
  InterlockedDecrement64(&daisy_vec_live);
#else
  atomic_fetch_sub(&daisy_vec_live, 1);
#endif
}

static void daisy_track_buffer_alloc(const void* ptr) {
  if (!ptr) {
    return;
  }
#ifdef _WIN32
  InterlockedIncrement64(&daisy_buffer_live);
#else
  atomic_fetch_add(&daisy_buffer_live, 1);
#endif
}

static void daisy_track_buffer_free(const void* ptr) {
  if (!ptr) {
    return;
  }
#ifdef _WIN32
  InterlockedDecrement64(&daisy_buffer_live);
#else
  atomic_fetch_sub(&daisy_buffer_live, 1);
#endif
}

static void daisy_track_channel_alloc(const void* ptr) {
  if (!ptr) {
    return;
  }
#ifdef _WIN32
  InterlockedIncrement64(&daisy_channel_live);
#else
  atomic_fetch_add(&daisy_channel_live, 1);
#endif
}

static void daisy_track_channel_free(const void* ptr) {
  if (!ptr) {
    return;
  }
#ifdef _WIN32
  InterlockedDecrement64(&daisy_channel_live);
#else
  atomic_fetch_sub(&daisy_channel_live, 1);
#endif
}

int64_t daisy_rt_string_live(void) {
#ifdef _WIN32
  return (int64_t)InterlockedAdd64(&daisy_string_live, 0);
#else
  return atomic_load(&daisy_string_live);
#endif
}

int64_t daisy_rt_vec_live(void) {
#ifdef _WIN32
  return (int64_t)InterlockedAdd64(&daisy_vec_live, 0);
#else
  return atomic_load(&daisy_vec_live);
#endif
}

int64_t daisy_rt_buffer_live(void) {
#ifdef _WIN32
  return (int64_t)InterlockedAdd64(&daisy_buffer_live, 0);
#else
  return atomic_load(&daisy_buffer_live);
#endif
}

int64_t daisy_rt_channel_live(void) {
#ifdef _WIN32
  return (int64_t)InterlockedAdd64(&daisy_channel_live, 0);
#else
  return atomic_load(&daisy_channel_live);
#endif
}

static void daisy_set_error(const char* msg) {
  if (!daisy_error_initialized) {
    daisy_last_error[0] = '\0';
    daisy_error_initialized = 1;
  }
  if (!msg) {
    daisy_last_error[0] = '\0';
    return;
  }
  strncpy(daisy_last_error, msg, sizeof(daisy_last_error) - 1);
  daisy_last_error[sizeof(daisy_last_error) - 1] = '\0';
}

static void daisy_set_error_errno(const char* prefix) {
  const char* err = strerror(errno);
  char buffer[256];
  if (prefix) {
    snprintf(buffer, sizeof(buffer), "%s: %s", prefix, err);
    daisy_set_error(buffer);
  } else {
    daisy_set_error(err);
  }
}

const char* daisy_error_last(void) {
  if (!daisy_error_initialized) {
    daisy_last_error[0] = '\0';
    daisy_error_initialized = 1;
  }
  return daisy_last_error;
}

void daisy_error_clear(void) { daisy_set_error(NULL); }

void daisy_panic(const char* msg) {
  fprintf(stderr, "DAISY panic: %s\n", msg ? msg : "unknown");
  abort();
}

void daisy_rt_fail(const char* msg) {
  fprintf(stderr, "DAISY runtime check failed: %s\n", msg ? msg : "unknown");
  abort();
}

static int daisy_checked_add_size(size_t a, size_t b, size_t* out) {
  if (SIZE_MAX - a < b) {
    return 0;
  }
  *out = a + b;
  return 1;
}

static int daisy_checked_mul_size(size_t a, size_t b, size_t* out) {
  if (a != 0 && SIZE_MAX / a < b) {
    return 0;
  }
  *out = a * b;
  return 1;
}

DaisyBuffer daisy_buffer_create(int64_t size) {
  DaisyBuffer buffer;
  buffer.data = NULL;
  buffer.size = 0;
  if (size <= 0 || (uint64_t)size > (uint64_t)SIZE_MAX) {
    return buffer;
  }
  buffer.data = (uint8_t*)malloc((size_t)size);
  if (!buffer.data) {
    return buffer;
  }
  daisy_track_buffer_alloc(buffer.data);
  buffer.size = size;
  return buffer;
}

void daisy_buffer_release(DaisyBuffer* buffer) {
  if (buffer && buffer->data) {
    daisy_track_buffer_free(buffer->data);
    free(buffer->data);
    buffer->data = NULL;
    buffer->size = 0;
  }
}

DaisyView daisy_buffer_borrow(DaisyBuffer* buffer, int64_t start, int64_t end, int mutable_flag) {
  DaisyView view;
  (void)mutable_flag;
  view.data = NULL;
  view.size = 0;
  view.start = 0;
  view.end = 0;
#ifdef DAISY_RT_CHECKS
  DAISY_RT_ASSERT(buffer && buffer->data, "buffer_borrow null");
  DAISY_RT_ASSERT(start >= 0 && end >= start, "buffer_borrow range");
  if (buffer) {
    DAISY_RT_ASSERT(end <= buffer->size, "buffer_borrow bounds");
  }
#endif
  if (!buffer || !buffer->data || start < 0 || end < 0 || start > end || end > buffer->size) {
    return view;
  }
  view.data = buffer->data + start;
  view.size = end - start;
  view.start = start;
  view.end = end;
  return view;
}

DaisyView daisy_view_borrow(DaisyView view, int mutable_flag) {
  (void)mutable_flag;
  return view;
}

DaisyTensor daisy_tensor_create(int64_t rows, int64_t cols) {
  DaisyTensor out;
  out.data = NULL;
  out.rows = 0;
  out.cols = 0;
  if (rows <= 0 || cols <= 0) {
    return out;
  }
  if ((uint64_t)rows > (uint64_t)SIZE_MAX || (uint64_t)cols > (uint64_t)SIZE_MAX) {
    return out;
  }
  size_t count = 0;
  if (!daisy_checked_mul_size((size_t)rows, (size_t)cols, &count)) {
    return out;
  }
  out.data = (float*)calloc(count, sizeof(float));
  if (!out.data) {
    return out;
  }
  out.rows = rows;
  out.cols = cols;
  return out;
}

DaisyTensor daisy_tensor_matmul(DaisyTensor a, DaisyTensor b) {
  DaisyTensor out;
  if (!a.data || !b.data || a.cols != b.rows) {
    out.data = NULL;
    out.rows = 0;
    out.cols = 0;
    return out;
  }
  out = daisy_tensor_create(a.rows, b.cols);
  if (!out.data) {
    return out;
  }
  for (int64_t i = 0; i < a.rows; i++) {
    for (int64_t j = 0; j < b.cols; j++) {
      float sum = 0.0f;
      for (int64_t k = 0; k < a.cols; k++) {
        sum += a.data[i * a.cols + k] * b.data[k * b.cols + j];
      }
      out.data[i * out.cols + j] = sum;
    }
  }
  return out;
}

void daisy_tensor_release(DaisyTensor* tensor) {
  if (tensor && tensor->data) {
    free(tensor->data);
    tensor->data = NULL;
    tensor->rows = 0;
    tensor->cols = 0;
  }
}

DaisyChannel* daisy_channel_create(void) {
  DaisyChannel* channel = (DaisyChannel*)malloc(sizeof(DaisyChannel));
  if (!channel) {
    return NULL;
  }
  daisy_track_channel_alloc(channel);
  channel->value = 0;
  channel->ready = 0;
  channel->closed = 0;
#ifdef _WIN32
  InitializeCriticalSection(&channel->lock);
  InitializeConditionVariable(&channel->cv);
#else
  pthread_mutex_init(&channel->lock, NULL);
  pthread_cond_init(&channel->cv, NULL);
#endif
  return channel;
}

int64_t daisy_channel_send(DaisyChannel* channel, int64_t value) {
  if (!channel) {
    return 0;
  }
#ifdef _WIN32
  EnterCriticalSection(&channel->lock);
  while (channel->ready && !channel->closed) {
    SleepConditionVariableCS(&channel->cv, &channel->lock, INFINITE);
  }
  if (channel->closed) {
    LeaveCriticalSection(&channel->lock);
    return 0;
  }
  channel->value = value;
  channel->ready = 1;
  WakeConditionVariable(&channel->cv);
  LeaveCriticalSection(&channel->lock);
#else
  pthread_mutex_lock(&channel->lock);
  while (channel->ready && !channel->closed) {
    pthread_cond_wait(&channel->cv, &channel->lock);
  }
  if (channel->closed) {
    pthread_mutex_unlock(&channel->lock);
    return 0;
  }
  channel->value = value;
  channel->ready = 1;
  pthread_cond_signal(&channel->cv);
  pthread_mutex_unlock(&channel->lock);
#endif
  return 0;
}

int64_t daisy_channel_recv(DaisyChannel* channel) {
  if (!channel) {
    return 0;
  }
#ifdef _WIN32
  EnterCriticalSection(&channel->lock);
  while (!channel->ready && !channel->closed) {
    SleepConditionVariableCS(&channel->cv, &channel->lock, INFINITE);
  }
  if (!channel->ready && channel->closed) {
    LeaveCriticalSection(&channel->lock);
    return 0;
  }
  int64_t value = channel->value;
  channel->ready = 0;
  WakeConditionVariable(&channel->cv);
  LeaveCriticalSection(&channel->lock);
  return value;
#else
  pthread_mutex_lock(&channel->lock);
  while (!channel->ready && !channel->closed) {
    pthread_cond_wait(&channel->cv, &channel->lock);
  }
  if (!channel->ready && channel->closed) {
    pthread_mutex_unlock(&channel->lock);
    return 0;
  }
  int64_t value = channel->value;
  channel->ready = 0;
  pthread_cond_signal(&channel->cv);
  pthread_mutex_unlock(&channel->lock);
  return value;
#endif
}

void daisy_channel_release(DaisyChannel* channel) {
  if (channel) {
    daisy_channel_close(channel);
#ifdef _WIN32
    DeleteCriticalSection(&channel->lock);
#else
    pthread_mutex_destroy(&channel->lock);
    pthread_cond_destroy(&channel->cv);
#endif
    daisy_track_channel_free(channel);
    free(channel);
  }
}

int64_t daisy_channel_close(DaisyChannel* channel) {
  if (!channel) {
    return 0;
  }
#ifdef _WIN32
  EnterCriticalSection(&channel->lock);
  channel->closed = 1;
  channel->ready = 0;
  WakeAllConditionVariable(&channel->cv);
  LeaveCriticalSection(&channel->lock);
#else
  pthread_mutex_lock(&channel->lock);
  channel->closed = 1;
  channel->ready = 0;
  pthread_cond_broadcast(&channel->cv);
  pthread_mutex_unlock(&channel->lock);
#endif
  return 0;
}

typedef struct {
  void (*fn)(void);
} DaisySpawnArgs;

typedef struct {
  int64_t (*fn)(DaisyChannel*);
  DaisyChannel* channel;
} DaisySpawnChannelArgs;

#ifdef _WIN32
static unsigned __stdcall daisy_spawn_thread(void* arg) {
  DaisySpawnArgs* args = (DaisySpawnArgs*)arg;
  if (args && args->fn) {
    args->fn();
  }
  free(args);
  return 0;
}

static unsigned __stdcall daisy_spawn_channel_thread(void* arg) {
  DaisySpawnChannelArgs* args = (DaisySpawnChannelArgs*)arg;
  if (args && args->fn) {
    (void)args->fn(args->channel);
  }
  free(args);
  return 0;
}
#else
static void* daisy_spawn_thread(void* arg) {
  DaisySpawnArgs* args = (DaisySpawnArgs*)arg;
  if (args && args->fn) {
    args->fn();
  }
  free(args);
  return NULL;
}

static void* daisy_spawn_channel_thread(void* arg) {
  DaisySpawnChannelArgs* args = (DaisySpawnChannelArgs*)arg;
  if (args && args->fn) {
    (void)args->fn(args->channel);
  }
  free(args);
  return NULL;
}
#endif

void daisy_spawn(void* fn_ptr) {
  if (!fn_ptr) {
    return;
  }
  DaisySpawnArgs* args = (DaisySpawnArgs*)malloc(sizeof(DaisySpawnArgs));
  if (!args) {
    return;
  }
  args->fn = (void (*)(void))fn_ptr;
#ifdef _WIN32
  uintptr_t handle = _beginthreadex(NULL, 0, daisy_spawn_thread, args, 0, NULL);
  if (handle) {
    CloseHandle((HANDLE)handle);
  } else {
    free(args);
  }
#else
  pthread_t thread;
  if (pthread_create(&thread, NULL, daisy_spawn_thread, args) == 0) {
    pthread_detach(thread);
  } else {
    free(args);
  }
#endif
}

void daisy_spawn_with_channel(void* fn_ptr, DaisyChannel* channel) {
  if (!fn_ptr) {
    return;
  }
  DaisySpawnChannelArgs* args = (DaisySpawnChannelArgs*)malloc(sizeof(DaisySpawnChannelArgs));
  if (!args) {
    return;
  }
  args->fn = (int64_t (*)(DaisyChannel*))fn_ptr;
  args->channel = channel;
#ifdef _WIN32
  uintptr_t handle = _beginthreadex(NULL, 0, daisy_spawn_channel_thread, args, 0, NULL);
  if (handle) {
    CloseHandle((HANDLE)handle);
  } else {
    free(args);
  }
#else
  pthread_t thread;
  if (pthread_create(&thread, NULL, daisy_spawn_channel_thread, args) == 0) {
    pthread_detach(thread);
  } else {
    free(args);
  }
#endif
}

DaisyVec* daisy_vec_new(void) {
  DaisyVec* vec = (DaisyVec*)malloc(sizeof(DaisyVec));
  if (!vec) {
    return NULL;
  }
  daisy_track_vec_alloc(vec);
  vec->data = NULL;
  vec->len = 0;
  vec->cap = 0;
  return vec;
}

void daisy_vec_push(DaisyVec* vec, int64_t value) {
  if (!vec) {
    return;
  }
  if (vec->len == vec->cap) {
    int64_t new_cap = vec->cap == 0 ? 4 : vec->cap * 2;
    if (new_cap < vec->cap || (uint64_t)new_cap > (uint64_t)SIZE_MAX) {
      return;
    }
    size_t bytes = 0;
    if (!daisy_checked_mul_size((size_t)new_cap, sizeof(int64_t), &bytes)) {
      return;
    }
    int64_t* next = (int64_t*)realloc(vec->data, bytes);
    if (!next) {
      return;
    }
    vec->data = next;
    vec->cap = new_cap;
  }
  vec->data[vec->len++] = value;
}

int64_t daisy_vec_get(DaisyVec* vec, int64_t index) {
#ifdef DAISY_RT_CHECKS
  DAISY_RT_ASSERT(vec != NULL, "vec_get null");
  DAISY_RT_ASSERT(index >= 0, "vec_get index negative");
#endif
  if (!vec || index < 0 || index >= vec->len) {
    return 0;
  }
#ifdef DAISY_RT_CHECKS
  DAISY_RT_ASSERT(index < vec->len, "vec_get out of range");
#endif
  return vec->data[index];
}

int64_t daisy_vec_len(DaisyVec* vec) {
  if (!vec) {
    return 0;
  }
  return vec->len;
}

void daisy_vec_release(DaisyVec* vec) {
  if (!vec) {
    return;
  }
  free(vec->data);
  daisy_track_vec_free(vec);
  free(vec);
}

int64_t daisy_str_len(const char* value) {
  if (!value) {
    return 0;
  }
  return (int64_t)strlen(value);
}

int64_t daisy_str_is_null(const char* value) {
  return value == NULL ? 1 : 0;
}

int64_t daisy_str_char_at(const char* value, int64_t index) {
  if (!value || index < 0) {
    return -1;
  }
  size_t len = strlen(value);
  if ((size_t)index >= len) {
    return -1;
  }
  return (unsigned char)value[index];
}

const char* daisy_str_substr(const char* value, int64_t start, int64_t len) {
  if (!value || start < 0 || len < 0) {
    return NULL;
  }
  size_t slen = strlen(value);
  if ((size_t)start > slen) {
    return NULL;
  }
  size_t maxlen = slen - (size_t)start;
  size_t out_len = (size_t)len;
  if (out_len > maxlen) {
    out_len = maxlen;
  }
  size_t alloc_size = 0;
  if (!daisy_checked_add_size(out_len, 1, &alloc_size)) {
    return NULL;
  }
  char* out = (char*)malloc(alloc_size);
  if (!out) {
    return NULL;
  }
  daisy_track_string_alloc(out);
  memcpy(out, value + start, out_len);
  out[out_len] = '\0';
  return out;
}

int64_t daisy_str_find_char(const char* value, int64_t ch, int64_t start) {
  if (!value || start < 0) {
    return -1;
  }
  size_t len = strlen(value);
  if ((size_t)start >= len) {
    return -1;
  }
  for (size_t i = (size_t)start; i < len; i++) {
    if ((unsigned char)value[i] == (unsigned char)ch) {
      return (int64_t)i;
    }
  }
  return -1;
}

int64_t daisy_str_starts_with(const char* value, const char* prefix) {
  if (!value || !prefix) {
    return 0;
  }
  size_t vlen = strlen(value);
  size_t plen = strlen(prefix);
  if (plen > vlen) {
    return 0;
  }
  return (int64_t)(strncmp(value, prefix, plen) == 0);
}

const char* daisy_str_trim(const char* value) {
  if (!value) {
    return NULL;
  }
  const char* start = value;
  while (*start && (*start == ' ' || *start == '\t' || *start == '\r' || *start == '\n')) {
    start++;
  }
  const char* end = value + strlen(value);
  while (end > start && (*(end - 1) == ' ' || *(end - 1) == '\t' || *(end - 1) == '\r' || *(end - 1) == '\n')) {
    end--;
  }
  size_t out_len = (size_t)(end - start);
  size_t alloc_size = 0;
  if (!daisy_checked_add_size(out_len, 1, &alloc_size)) {
    return NULL;
  }
  char* out = (char*)malloc(alloc_size);
  if (!out) {
    return NULL;
  }
  daisy_track_string_alloc(out);
  memcpy(out, start, out_len);
  out[out_len] = '\0';
  return out;
}

int64_t daisy_str_to_int(const char* value) {
  if (!value) {
    return 0;
  }
  return (int64_t)strtoll(value, NULL, 10);
}

const char* daisy_str_concat(const char* left, const char* right) {
  if (!left || !right) {
    return NULL;
  }
  size_t len_left = strlen(left);
  size_t len_right = strlen(right);
  size_t merged = 0;
  if (!daisy_checked_add_size(len_left, len_right, &merged)) {
    return NULL;
  }
  size_t alloc_size = 0;
  if (!daisy_checked_add_size(merged, 1, &alloc_size)) {
    return NULL;
  }
  char* out = (char*)malloc(alloc_size);
  if (!out) {
    return NULL;
  }
  daisy_track_string_alloc(out);
  memcpy(out, left, len_left);
  memcpy(out + len_left, right, len_right);
  out[len_left + len_right] = '\0';
  return out;
}

int64_t daisy_str_release(const char* value) {
  if (value) {
    daisy_track_string_free(value);
    free((void*)value);
  }
  return 0;
}

const char* daisy_file_read(const char* path) {
  if (!path) {
    daisy_set_error("file_read: path is null");
    return NULL;
  }
  FILE* fp = fopen(path, "rb");
  if (!fp) {
    daisy_set_error_errno("file_read: open failed");
    return NULL;
  }
#ifdef _WIN32
  if (_fseeki64(fp, 0, SEEK_END) != 0) {
    fclose(fp);
    return NULL;
  }
  int64_t size = _ftelli64(fp);
  if (_fseeki64(fp, 0, SEEK_SET) != 0) {
    fclose(fp);
    return NULL;
  }
#else
  if (fseeko(fp, 0, SEEK_END) != 0) {
    fclose(fp);
    return NULL;
  }
  off_t size = ftello(fp);
  if (fseeko(fp, 0, SEEK_SET) != 0) {
    fclose(fp);
    return NULL;
  }
#endif
  if (size < 0 || (uint64_t)size > (uint64_t)DAISY_MAX_FILE_SIZE) {
    fclose(fp);
    daisy_set_error("file_read: invalid size");
    return NULL;
  }
  if ((uint64_t)size > (uint64_t)SIZE_MAX) {
    fclose(fp);
    daisy_set_error("file_read: size overflow");
    return NULL;
  }
  size_t alloc_size = 0;
  if (!daisy_checked_add_size((size_t)size, 1, &alloc_size)) {
    fclose(fp);
    daisy_set_error("file_read: alloc overflow");
    return NULL;
  }
  char* buffer = (char*)malloc(alloc_size);
  if (!buffer) {
    fclose(fp);
    daisy_set_error("file_read: alloc failed");
    return NULL;
  }
  daisy_track_string_alloc(buffer);
  size_t read = fread(buffer, 1, (size_t)size, fp);
  buffer[read] = '\0';
  if (read != (size_t)size && ferror(fp)) {
    free(buffer);
    fclose(fp);
    daisy_set_error_errno("file_read: read failed");
    return NULL;
  }
  fclose(fp);
  daisy_error_clear();
  return buffer;
}

int64_t daisy_file_write(const char* path, const char* content) {
  if (!path || !content) {
    daisy_set_error("file_write: invalid arguments");
    return 0;
  }
  FILE* fp = fopen(path, "wb");
  if (!fp) {
    daisy_set_error_errno("file_write: open failed");
    return 0;
  }
  size_t len = strlen(content);
  size_t written = fwrite(content, 1, len, fp);
  fclose(fp);
  if (written != len) {
    daisy_set_error_errno("file_write: write failed");
  } else {
    daisy_error_clear();
  }
  return (int64_t)(written == len);
}

const char* daisy_module_load(const char* path) {
  return daisy_file_read(path);
}

int64_t daisy_compile_default(void) {
#ifdef _WIN32
  return system("python tools\\cli\\daisy.py build src\\main.dsy");
#else
  return system("python3 tools/cli/daisy.py build src/main.dsy");
#endif
}

int64_t daisy_file_exists(const char* path) {
  if (!path) {
    return 0;
  }
  FILE* f = fopen(path, "rb");
  if (!f) {
    return 0;
  }
  fclose(f);
  return 1;
}

int64_t daisy_file_delete(const char* path) {
  if (!path) {
    return 0;
  }
  return remove(path) == 0 ? 1 : 0;
}

int64_t daisy_file_move(const char* from, const char* to) {
  if (!from || !to) {
    return 0;
  }
  return rename(from, to) == 0 ? 1 : 0;
}

int64_t daisy_file_copy(const char* from, const char* to) {
  if (!from || !to) {
    return 0;
  }
  FILE* in = fopen(from, "rb");
  if (!in) {
    return 0;
  }
  FILE* out = fopen(to, "wb");
  if (!out) {
    fclose(in);
    return 0;
  }
  char buffer[8192];
  size_t n = 0;
  while ((n = fread(buffer, 1, sizeof(buffer), in)) > 0) {
    if (fwrite(buffer, 1, n, out) != n) {
      fclose(in);
      fclose(out);
      return 0;
    }
  }
  fclose(in);
  fclose(out);
  return 1;
}

int64_t daisy_dir_create(const char* path) {
  if (!path) {
    return 0;
  }
#ifdef _WIN32
  return _mkdir(path) == 0 ? 1 : 0;
#else
  return mkdir(path, 0755) == 0 ? 1 : 0;
#endif
}

int64_t daisy_dir_exists(const char* path) {
  if (!path) {
    return 0;
  }
#ifdef _WIN32
  DWORD attr = GetFileAttributesA(path);
  return (attr != INVALID_FILE_ATTRIBUTES && (attr & FILE_ATTRIBUTE_DIRECTORY)) ? 1 : 0;
#else
  struct stat st;
  if (stat(path, &st) != 0) {
    return 0;
  }
  return S_ISDIR(st.st_mode) ? 1 : 0;
#endif
}

static int daisy_log_level = 1;

void daisy_log_set_level(int64_t level) { daisy_log_level = (int)level; }

static void daisy_log_emit(const char* tag, const char* msg) {
  if (!msg) {
    msg = "";
  }
  fprintf(stderr, "[%s] %s\n", tag, msg);
}

void daisy_log_info(const char* msg) {
  if (daisy_log_level <= 1) {
    daisy_log_emit("info", msg);
  }
}

void daisy_log_warn(const char* msg) {
  if (daisy_log_level <= 2) {
    daisy_log_emit("warn", msg);
  }
}

void daisy_log_error(const char* msg) {
  if (daisy_log_level <= 3) {
    daisy_log_emit("error", msg);
  }
}

const char* daisy_int_to_str(int64_t value) {
  char buffer[64];
  snprintf(buffer, sizeof(buffer), "%lld", (long long)value);
  return daisy_str_concat(buffer, "");
}

const char* daisy_bool_to_str(int64_t value) { return value ? "true" : "false"; }

const char* daisy_str_escape_json(const char* value) {
  if (!value) {
    return "\"\"";
  }
  size_t len = strlen(value);
  size_t cap = len * 2 + 3;
  char* out = (char*)malloc(cap);
  if (!out) {
    return "\"\"";
  }
  daisy_track_string_alloc(out);
  size_t idx = 0;
  out[idx++] = '"';
  for (size_t i = 0; i < len; i++) {
    char ch = value[i];
    if (ch == '"' || ch == '\\') {
      out[idx++] = '\\';
      out[idx++] = ch;
    } else if (ch == '\n') {
      out[idx++] = '\\';
      out[idx++] = 'n';
    } else if (ch == '\r') {
      out[idx++] = '\\';
      out[idx++] = 'r';
    } else if (ch == '\t') {
      out[idx++] = '\\';
      out[idx++] = 't';
    } else {
      out[idx++] = ch;
    }
    if (idx + 2 >= cap) {
      cap *= 2;
      out = (char*)realloc(out, cap);
      if (!out) {
        return "\"\"";
      }
    }
  }
  out[idx++] = '"';
  out[idx] = '\0';
  return out;
}

#ifdef _WIN32
static int daisy_winsock_ready = 0;
static void daisy_winsock_init(void) {
  if (daisy_winsock_ready) {
    return;
  }
  WSADATA data;
  if (WSAStartup(MAKEWORD(2, 2), &data) == 0) {
    daisy_winsock_ready = 1;
  }
}
#endif

int64_t daisy_net_connect(const char* host, int64_t port) {
  if (!host || port <= 0 || port > 65535) {
    return -1;
  }
#ifdef _WIN32
  daisy_winsock_init();
#endif
  struct addrinfo hints;
  struct addrinfo* result = NULL;
  memset(&hints, 0, sizeof(hints));
  hints.ai_family = AF_UNSPEC;
  hints.ai_socktype = SOCK_STREAM;
  char port_str[16];
  snprintf(port_str, sizeof(port_str), "%lld", (long long)port);
  if (getaddrinfo(host, port_str, &hints, &result) != 0) {
    return -1;
  }
  int64_t handle = -1;
  for (struct addrinfo* rp = result; rp != NULL; rp = rp->ai_next) {
#ifdef _WIN32
    SOCKET sock = socket(rp->ai_family, rp->ai_socktype, rp->ai_protocol);
    if (sock == INVALID_SOCKET) {
      continue;
    }
    if (connect(sock, rp->ai_addr, (int)rp->ai_addrlen) == 0) {
      handle = (int64_t)sock;
      break;
    }
    closesocket(sock);
#else
    int sock = socket(rp->ai_family, rp->ai_socktype, rp->ai_protocol);
    if (sock < 0) {
      continue;
    }
    if (connect(sock, rp->ai_addr, rp->ai_addrlen) == 0) {
      handle = (int64_t)sock;
      break;
    }
    close(sock);
#endif
  }
  freeaddrinfo(result);
  return handle;
}

int64_t daisy_net_send(int64_t sock, const char* data) {
  if (!data) {
    return 0;
  }
#ifdef DAISY_RT_CHECKS
  DAISY_RT_ASSERT(sock >= 0, "net_send invalid socket");
#endif
#ifdef _WIN32
  return (int64_t)send((SOCKET)sock, data, (int)strlen(data), 0);
#else
  return (int64_t)send((int)sock, data, strlen(data), 0);
#endif
}

const char* daisy_net_recv(int64_t sock, int64_t max_bytes) {
  if (max_bytes <= 0) {
    return daisy_str_concat("", "");
  }
#ifdef DAISY_RT_CHECKS
  DAISY_RT_ASSERT(sock >= 0, "net_recv invalid socket");
  DAISY_RT_ASSERT(max_bytes <= DAISY_MAX_NET_READ, "net_recv too large");
#endif
  size_t cap = (size_t)max_bytes + 1;
  char* buffer = (char*)malloc(cap);
  if (!buffer) {
    return daisy_str_concat("", "");
  }
  daisy_track_string_alloc(buffer);
#ifdef _WIN32
  int n = recv((SOCKET)sock, buffer, (int)max_bytes, 0);
#else
  int n = (int)recv((int)sock, buffer, (size_t)max_bytes, 0);
#endif
  if (n < 0) {
    free(buffer);
    return daisy_str_concat("", "");
  }
  buffer[n] = '\0';
  return buffer;
}

int64_t daisy_net_close(int64_t sock) {
#ifdef _WIN32
  closesocket((SOCKET)sock);
#else
  close((int)sock);
#endif
  return 0;
}


