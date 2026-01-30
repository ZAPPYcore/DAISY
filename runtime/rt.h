#pragma once

#include <stdint.h>

#ifdef DAISY_RT_CHECKS
void daisy_rt_fail(const char* msg);
#define DAISY_RT_ASSERT(cond, msg) \
  do { \
    if (!(cond)) { \
      daisy_rt_fail(msg); \
    } \
  } while (0)
#else
#define DAISY_RT_ASSERT(cond, msg) ((void)0)
#endif

const char* daisy_error_last(void);
void daisy_error_clear(void);
void daisy_panic(const char* msg);

#ifdef _WIN32
#include <winsock2.h>
#include <ws2tcpip.h>
#include <windows.h>
#else
#include <pthread.h>
#endif

typedef struct {
  uint8_t* data;
  int64_t size;
} DaisyBuffer;

typedef struct {
  uint8_t* data;
  int64_t size;
  int64_t start;
  int64_t end;
} DaisyView;

typedef struct {
  float* data;
  int64_t rows;
  int64_t cols;
} DaisyTensor;

typedef struct DaisyChannel {
  int64_t value;
  int ready;
  int closed;
#ifdef _WIN32
  CRITICAL_SECTION lock;
  CONDITION_VARIABLE cv;
#else
  pthread_mutex_t lock;
  pthread_cond_t cv;
#endif
} DaisyChannel;

typedef struct {
  int64_t* data;
  int64_t len;
  int64_t cap;
} DaisyVec;

#ifndef DAISY_MAX_FILE_SIZE
#define DAISY_MAX_FILE_SIZE (64 * 1024 * 1024)
#endif

#ifndef DAISY_MAX_NET_READ
#define DAISY_MAX_NET_READ (4 * 1024 * 1024)
#endif

int64_t daisy_print_int(int64_t value);
int64_t daisy_print_str(const char* value);

DaisyBuffer daisy_buffer_create(int64_t size);
void daisy_buffer_release(DaisyBuffer* buffer);
DaisyView daisy_buffer_borrow(DaisyBuffer* buffer, int64_t start, int64_t end, int mutable_flag);
DaisyView daisy_view_borrow(DaisyView view, int mutable_flag);

DaisyTensor daisy_tensor_matmul(DaisyTensor a, DaisyTensor b);
DaisyTensor daisy_tensor_create(int64_t rows, int64_t cols);
void daisy_tensor_release(DaisyTensor* tensor);

DaisyChannel* daisy_channel_create(void);
int64_t daisy_channel_send(DaisyChannel* channel, int64_t value);
int64_t daisy_channel_recv(DaisyChannel* channel);
int64_t daisy_channel_close(DaisyChannel* channel);
void daisy_channel_release(DaisyChannel* channel);

DaisyVec* daisy_vec_new(void);
void daisy_vec_push(DaisyVec* vec, int64_t value);
int64_t daisy_vec_get(DaisyVec* vec, int64_t index);
int64_t daisy_vec_len(DaisyVec* vec);
void daisy_vec_release(DaisyVec* vec);

int64_t daisy_str_len(const char* value);
int64_t daisy_str_is_null(const char* value);
const char* daisy_str_concat(const char* left, const char* right);
int64_t daisy_str_release(const char* value);
int64_t daisy_str_char_at(const char* value, int64_t index);
const char* daisy_str_substr(const char* value, int64_t start, int64_t len);
int64_t daisy_str_find_char(const char* value, int64_t ch, int64_t start);
int64_t daisy_str_starts_with(const char* value, const char* prefix);
const char* daisy_str_trim(const char* value);
int64_t daisy_str_to_int(const char* value);

const char* daisy_file_read(const char* path);
int64_t daisy_file_write(const char* path, const char* content);
const char* daisy_module_load(const char* path);
void daisy_spawn(void* fn_ptr);
void daisy_spawn_with_channel(void* fn_ptr, DaisyChannel* channel);
int64_t daisy_compile_default(void);

int64_t daisy_file_exists(const char* path);
int64_t daisy_file_delete(const char* path);
int64_t daisy_file_move(const char* from, const char* to);
int64_t daisy_file_copy(const char* from, const char* to);
int64_t daisy_dir_create(const char* path);
int64_t daisy_dir_exists(const char* path);

void daisy_log_set_level(int64_t level);
void daisy_log_info(const char* msg);
void daisy_log_warn(const char* msg);
void daisy_log_error(const char* msg);

const char* daisy_int_to_str(int64_t value);
const char* daisy_bool_to_str(int64_t value);
const char* daisy_str_escape_json(const char* value);

int64_t daisy_rt_string_live(void);
int64_t daisy_rt_vec_live(void);
int64_t daisy_rt_buffer_live(void);
int64_t daisy_rt_channel_live(void);

int64_t daisy_net_connect(const char* host, int64_t port);
int64_t daisy_net_send(int64_t sock, const char* data);
const char* daisy_net_recv(int64_t sock, int64_t max_bytes);
int64_t daisy_net_close(int64_t sock);


