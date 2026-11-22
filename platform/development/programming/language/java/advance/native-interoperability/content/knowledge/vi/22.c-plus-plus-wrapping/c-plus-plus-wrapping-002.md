# Xuất một lớp API C ổn định bằng extern "C" quanh thư viện C++

## 1. Mục tiêu và vấn đề thực tế

Một thư viện C++ có thể dùng class, constructor, destructor, template, `std::string`, `std::vector`, namespace, overload và exception. Những khả năng này tiện lợi bên trong C++, nhưng không phải một hợp đồng nhị phân đơn giản cho chương trình C, Java/JNI, Rust FFI, Python ctypes hoặc Java FFM.

Để các ngôn ngữ khác sử dụng thư viện, ta thường xây **C ABI façade**: một lớp export bằng `extern "C"`, có một header hợp lệ cho C compiler và chỉ lộ các hàm, con trỏ opaque, primitive có kích thước rõ, error codes cùng quy tắc ownership. C++ class và STL vẫn được dùng ở **phía sau façade**, không đi qua ABI.

Sau bài này, bạn sẽ biết:

- `extern "C"` giải quyết name mangling/language linkage như thế nào, và **không** tự bảo đảm binary portability xuyên OS, ABI hoặc compiler.
- Tạo `counter_api.h` dùng được từ C11 và C++17, với `#ifdef __cplusplus` và symbol-export macros.
- Giấu C++ object layout bằng `typedef struct counter_handle counter_handle;`.
- Định nghĩa `create/get/add/destroy`, matching allocator, borrowed/owned pointer, error handling và versioning.
- Bắt C++ exceptions ở C boundary, chuyển thành status; ở Java JNI đổi status thành Java exception.
- Build **một shared library** chứa public C ABI và JNI adapter, gọi cùng lõi C++ từ **C client** và **Java 17 client**.
- Phân tích lỗi double-free, use-after-free, class layout, ABI mismatch, thread race, DLL import/export, FFM/JDK 22+ và tương thích phiên bản.

> **Yêu cầu chạy mẫu:** Java 17+, C++17, C11, native compiler phù hợp Linux/macOS/Windows và JDK có JNI headers. Đây là ví dụ Java 17 + JNI, **không** dùng API FFM chưa ổn định trong Java 17. Từ JDK 22, có thể thay adapter JNI bằng FFM downcalls tới cùng C ABI.

## 2. Vì sao không export trực tiếp class C++?

Một class nội bộ có thể trông như:

~~~cpp
#include <string>

namespace engine {
class Counter {
public:
    explicit Counter(int start);
    int add(int amount);
    int value() const;
    std::string describe() const;
};
}
~~~

Đây là **khai báo minh họa**, chưa có code thực thi. C compiler không hiểu constructor, namespace hoặc `std::string`. JNI không thể biết cách gọi C++ non-static member function như một C function pointer thường.

Khó khăn ở ranh giới nhị phân:

| Yếu tố C++ | Rủi ro khi lộ trực tiếp |
|---|---|
| Name mangling | Tên symbol phụ thuộc compiler/ABI và overload |
| Class layout/vtable | Kích thước, alignment, inheritance, field offsets có thể thay đổi |
| STL types | `std::string`/`std::vector` phụ thuộc C++ standard library ABI/allocator |
| Exceptions | Không có giao thức portable để C caller nhận exception C++ |
| new/delete | Không được tự ý hoán đổi với malloc/free hoặc CRT khác |
| Templates/overloads | Không thể coi là tập C symbols cố định |
| C++ references | Không phải một C ABI contract minh bạch |
| `long`, `size_t`, calling convention | Độ rộng và cách truyền tham số tùy target |
| ABI evolution | Sửa signature/layout có thể phá client đã build |

**C ABI façade** che đi các chi tiết ấy: chỉ public primitive types, pointers và hàm C có contract cố định. Implementation có thể tiếp tục sử dụng tính năng C++ tùy ý.

## 3. extern "C": điều nó làm và không làm

~~~cpp
extern "C" int counter_api_version(void);
~~~

Trong C++, `extern "C"` chỉ định **C language linkage** cho function name/type phù hợp. Trên toolchains phổ biến, exported symbol sẽ mang tên C như `counter_api_version` thay vì symbol name-mangled của C++.

Nó **không**:

1. Chuyển `std::string` thành chuỗi C.
2. Ẩn class layout hoặc làm C compiler hiểu template.
3. Cố định calling convention cho mọi CPU/OS.
4. Tự export tên hàm từ Windows DLL.
5. Bắt C++ exception.
6. Quản lý native heap hoặc bảo vệ pointer đã free.
7. Đảm bảo DLL Linux x86-64 chạy được trên Windows ARM64.
8. Giữ tương thích nếu thay `int32_t` thành `int64_t` ở cùng một exported symbol.

Vì `extern "C"` là cú pháp **C++**, public header dùng guard:

~~~c
#ifdef __cplusplus
extern "C" {
#endif

/* Các hàm C-compatible ở đây. */

#ifdef __cplusplus
}
#endif
~~~

C11 compiler sẽ bỏ phần language linkage, còn C++ compiler áp dụng nó. Đây là cách để một header có thể được include từ cả C client và C++ implementation.

## 4. Thiết kế public C API cho một C++ Counter

Giả sử đối tượng counter do thư viện C++ sở hữu state. API nhỏ:

| Hàm | Ý nghĩa | Ownership |
|---|---|---|
| `counter_api_version()` | Trả major ABI version | Không resource |
| `counter_create(start, &handle)` | Tạo counter; status riêng | Chuyển **owned handle** cho caller khi thành công |
| `counter_get(handle, &out)` | Đọc giá trị | Borrowed handle trong lời gọi |
| `counter_add(handle, delta, &out)` | Cộng và lấy giá trị mới | Borrowed handle |
| `counter_destroy(handle)` | Hủy counter | Consume owned handle |
| `counter_status_message(code)` | Mô tả status | Borrowed static string, caller không free |

**Hợp đồng chính:**

- Public header chỉ có `counter_handle*`, không có constructor, STL hay C++ exceptions.
- `create` và `destroy` là cặp do **cùng thư viện** triển khai.
- Function return là `int32_t` status, output data qua pointer; kết quả giá trị 0 không nhầm với status 0.
- Status codes phải có ý nghĩa nhất quán giữa các minor versions.
- Opaque pointer không phải token bảo mật. Forged/stale pointer vẫn nguy hiểm nếu API dereference trực tiếp.

### Vì sao dùng int32_t thay vì long?

`int32_t` từ `<stdint.h>` có đúng 32 bit khi tồn tại. C `long` có thể 64 bit trên nhiều Unix x64 nhưng 32 bit trên Windows x64. Java `long` là 64 bit còn JNI `jint` tương ứng Java `int` 32 bit. Với những tham số phải có chiều rộng cố định, dùng fixed-width types và xác minh ABI thay vì đoán.

## 5. File đầy đủ: counter_api.h

~~~c
#ifndef COUNTER_API_H
#define COUNTER_API_H

#include <stdint.h>

/* Symbol visibility: export ở library, import ở Windows client. */
#if defined(_WIN32)
    #if defined(COUNTER_BUILD_SHARED)
        #define COUNTER_API __declspec(dllexport)
    #else
        #define COUNTER_API __declspec(dllimport)
    #endif
#elif defined(__GNUC__) || defined(__clang__)
    #define COUNTER_API __attribute__((visibility("default")))
#else
    #define COUNTER_API
#endif

#define COUNTER_ABI_VERSION 1u

#define COUNTER_OK            0
#define COUNTER_BAD_ARGUMENT  1
#define COUNTER_NO_MEMORY     2
#define COUNTER_OVERFLOW      3
#define COUNTER_INTERNAL      4

#ifdef __cplusplus
extern "C" {
#endif

/* Incomplete type: client không biết layout. */
typedef struct counter_handle counter_handle;

/* Success: *out là owned pointer, phải destroy đúng một lần. */
COUNTER_API int32_t counter_create(
        int32_t initial, counter_handle **out);

/* Borrowed pointer, không chuyển quyền sở hữu. */
COUNTER_API int32_t counter_get(
        const counter_handle *handle, int32_t *out_value);

COUNTER_API int32_t counter_add(
        counter_handle *handle, int32_t delta,
        int32_t *out_value);

/* Consumer release; phải dùng đúng hàm của thư viện. */
COUNTER_API void counter_destroy(counter_handle *handle);

/* Không free pointer trả về: trỏ tới static string literal. */
COUNTER_API const char *counter_status_message(
        int32_t status);

COUNTER_API uint32_t counter_api_version(void);

#ifdef __cplusplus
}
#endif

#endif /* COUNTER_API_H */
~~~

**Giải thích các quyết định:**

- `#ifdef __cplusplus` giữ header hợp lệ ở C11.
- `COUNTER_API` điều khiển export/import: trên Windows dùng `__declspec(dllexport)` khi build DLL, `dllimport` ở client; trên GCC/Clang dùng visibility.
- `COUNTER_ABI_VERSION` là major version của contract, không là version C++ class.
- Macros status dùng số nguyên nhỏ, exported functions trả `int32_t` rõ ràng.
- `typedef struct counter_handle counter_handle;` là opaque handle. C client không được `sizeof(counter_handle)` hay truy cập fields.
- `counter_create` trả ownership qua `counter_handle **out`. Trên lỗi, implementation cố gắng để `*out=NULL`.
- `counter_get/add` nhận borrowed handle, không giữ pointer sau return.
- `counter_destroy` nhận một owner hợp lệ; gọi lặp với cùng non-null pointer là lỗi nghiêm trọng.
- `counter_status_message` trả borrowed literal. Không `free` ở caller.
- Không có `JNIEnv*`, `jstring` hay `std::string` trong public API: C client độc lập không cần Java hoặc C++ headers.

## 6. File C++ implementation: counter_api.cpp

~~~cpp
#include "counter_api.h"

#include <cstdint>
#include <limits>
#include <new>

/* Private C++ layout, không có trong public header. */
struct counter_handle {
    std::int32_t value;

    explicit counter_handle(std::int32_t start) noexcept
        : value(start) {}
};

extern "C" {

COUNTER_API int32_t counter_create(
        int32_t initial, counter_handle **out) {

    if (out == nullptr) {
        return COUNTER_BAD_ARGUMENT;
    }
    *out = nullptr;

    try {
        *out = new counter_handle(initial);
        return COUNTER_OK;
    } catch (const std::bad_alloc &) {
        return COUNTER_NO_MEMORY;
    } catch (...) {
        return COUNTER_INTERNAL;
    }
}

COUNTER_API int32_t counter_get(
        const counter_handle *handle, int32_t *out_value) {

    if (handle == nullptr || out_value == nullptr) {
        return COUNTER_BAD_ARGUMENT;
    }

    try {
        *out_value = handle->value;
        return COUNTER_OK;
    } catch (...) {
        return COUNTER_INTERNAL;
    }
}

COUNTER_API int32_t counter_add(
        counter_handle *handle, int32_t delta,
        int32_t *out_value) {

    if (handle == nullptr || out_value == nullptr) {
        return COUNTER_BAD_ARGUMENT;
    }

    try {
        const std::int64_t wide =
                static_cast<std::int64_t>(handle->value)
                + static_cast<std::int64_t>(delta);

        if (wide < std::numeric_limits<std::int32_t>::min()
                || wide > std::numeric_limits<std::int32_t>::max()) {
            return COUNTER_OVERFLOW;
        }

        handle->value = static_cast<std::int32_t>(wide);
        *out_value = handle->value;
        return COUNTER_OK;
    } catch (...) {
        return COUNTER_INTERNAL;
    }
}

COUNTER_API void counter_destroy(counter_handle *handle) {
    /* Trivial destructor không throw, delete nullptr hợp lệ. */
    delete handle;
}

COUNTER_API const char *counter_status_message(
        int32_t status) {
    switch (status) {
        case COUNTER_OK: return "ok";
        case COUNTER_BAD_ARGUMENT: return "bad argument";
        case COUNTER_NO_MEMORY: return "out of memory";
        case COUNTER_OVERFLOW: return "integer overflow";
        case COUNTER_INTERNAL: return "internal C++ error";
        default: return "unknown status";
    }
}

COUNTER_API uint32_t counter_api_version(void) {
    return COUNTER_ABI_VERSION;
}

} // extern "C"
~~~

**Cơ chế:**

1. `counter_handle` là một C++ struct thật trong implementation; C caller chỉ giữ opaque pointer.
2. `counter_create` cấp bằng `new` và catch `std::bad_alloc` cùng các exception khác. Không cho C++ exception thoát qua C ABI.
3. `counter_get` và `counter_add` chỉ borrow; không free handle.
4. `counter_add` nâng operands sang `int64_t` **trước** phép cộng để tránh undefined behavior do signed overflow 32-bit; kiểm tra giới hạn rồi mới cập nhật state.
5. Nếu overflow, trả `COUNTER_OVERFLOW` mà **không thay đổi** giá trị counter.
6. `counter_destroy` dùng `delete` đúng allocator của `new`; object ở demo có trivial/no-throw destructor.
7. `counter_status_message` trả static string literal với lifetime do thư viện quản lý.

**Điểm giới hạn:** `catch (...)` không biến forged pointer, stale handle, concurrent destroy hoặc memory corruption thành một lỗi Java/C an toàn. Những tình huống đó có thể là undefined behavior. Với API nhận handles không đáng tin, phải dùng registry hoặc generation tokens và đồng bộ hóa lookup-to-use.

### Nếu destructor có thể lỗi

Không sao chép `void counter_destroy` sang SDK có destructor/callback có thể throw hoặc resource close có thể thất bại. Định nghĩa destructor `noexcept` và xử lý lỗi có chủ đích, hoặc thêm hàm `counter_close` trả status rồi mới release. C ABI không được để exception đi xuyên C callers/JNI frame.

## 7. File client C11: c_client.c

Đây là phép kiểm tra quan trọng: **client được biên dịch bằng C compiler**, không cần cú pháp C++.

~~~c
#include "counter_api.h"

#include <inttypes.h>
#include <stdio.h>

int main(void) {
    counter_handle *handle = NULL;
    int32_t current = 0;

    int32_t status = counter_create(10, &handle);
    if (status != COUNTER_OK) {
        fprintf(stderr, "create: %s\n",
                counter_status_message(status));
        return 1;
    }

    int exit_code = 0;
    do {
        printf("c-api-version=%u\n",
               (unsigned)counter_api_version());

        status = counter_add(handle, 5, &current);
        if (status != COUNTER_OK) {
            exit_code = 1;
            break;
        }
        printf("c-after-add=%" PRId32 "\n", current);

        status = counter_add(handle, INT32_MAX, &current);
        printf("c-overflow-status=%" PRId32 "\n", status);
        if (status != COUNTER_OVERFLOW) {
            exit_code = 1;
            break;
        }

        status = counter_get(handle, &current);
        if (status != COUNTER_OK) {
            exit_code = 1;
            break;
        }
        printf("c-still=%" PRId32 "\n", current);

    } while (0);

    counter_destroy(handle);
    handle = NULL;
    return exit_code;
}
~~~

### Stdout C client

~~~text
c-api-version=1
c-after-add=15
c-overflow-status=3
c-still=15
~~~

Counter bắt đầu bằng 10; cộng 5 thành 15. Sau đó `15 + INT32_MAX` không vừa trong signed 32-bit, nên status 3 (`COUNTER_OVERFLOW`). Do hàm kiểm tra overflow **trước khi ghi**, `counter_get` vẫn trả 15. Client gọi destroy đúng một lần kể cả khi một operation trung gian thất bại.

Dùng `PRId32` từ `inttypes.h` tránh giả định format của `int32_t`; public header hoàn toàn C-compatible. Nếu client muốn chia sẻ một handle giữa nhiều threads, cần lock/refcount/lease — mẫu này có một owner và một thread.

## 8. Java 17 sử dụng cùng C ABI qua JNI

Kiến trúc của ví dụ:

~~~text
Java CounterDemo.Counter (AutoCloseable)
            |
        JNI methods
            |
            v
counter_jni.cpp
  - nhận jint / jlong
  - đổi status thành Java exception
            |
            v
counter_api.h (PUBLIC C ABI)
            |
            v
counter_api.cpp (C++17 private state)
  - new / delete
  - overflow check

c_client.c --------> counter_api.h (cùng hợp đồng)
~~~

JNI adapter không tự cấp phát một implementation khác: nó dùng `counter_create/get/add/destroy` như C client. Vì thế public C API độc lập với JVM. Nếu thay C++ core từ struct đơn giản thành class phức tạp, Java JNI code vẫn dùng cùng façade.

### Vì sao Java cần AutoCloseable?

Java `long` chỉ giữ một **giá trị số**. GC không tự biết số ấy là địa chỉ của đối tượng được C++ `new`. Wrapper cần chủ động gọi release bằng `close()`:

~~~java
try (CounterDemo.Counter counter =
         new CounterDemo.Counter(40)) {
    System.out.println(counter.value());
} // close() -> JNI -> counter_destroy()
~~~

Đây là mảnh Java minh họa. Lớp hoàn chỉnh bên dưới đảm bảo close nhiều lần trên một wrapper không gọi delete thêm.

## 9. File Java đầy đủ: CounterDemo.java

~~~java
public final class CounterDemo {
    static {
        System.loadLibrary("counterbridge");
    }

    private CounterDemo() {}

    private static native int nVersion();
    private static native long nCreate(int initial);
    private static native int nGet(long handle);
    private static native int nAdd(long handle, int delta);
    private static native void nDestroy(long handle);

    public static final class Counter implements AutoCloseable {
        private long handle;

        public Counter(int initial) {
            long created = nCreate(initial);
            if (created == 0L) {
                throw new IllegalStateException(
                        "Native allocation failed");
            }
            handle = created;
        }

        private void requireOpen() {
            if (handle == 0L) {
                throw new IllegalStateException("Counter is closed");
            }
        }

        public synchronized int value() {
            requireOpen();
            return nGet(handle);
        }

        public synchronized int add(int delta) {
            requireOpen();
            return nAdd(handle, delta);
        }

        public synchronized boolean isClosed() {
            return handle == 0L;
        }

        @Override
        public synchronized void close() {
            if (handle == 0L) {
                return;
            }

            long owned = handle;
            handle = 0L;
            nDestroy(owned);
        }
    }

    public static void main(String[] args) {
        System.out.println("apiVersion=" + nVersion());

        Counter counter = new Counter(40);
        try (counter) {
            System.out.println("initial=" + counter.value());
            System.out.println("afterAdd=" + counter.add(2));

            try {
                counter.add(Integer.MAX_VALUE);
            } catch (ArithmeticException ex) {
                System.out.println(
                        "overflow=" + ex.getClass().getSimpleName());
            }

            System.out.println("unchanged=" + counter.value());
        }

        System.out.println("closed=" + counter.isClosed());

        counter.close();
        System.out.println("closedTwice=" + counter.isClosed());

        try {
            counter.value();
        } catch (IllegalStateException ex) {
            System.out.println(
                    "afterClose=" + ex.getClass().getSimpleName());
        }
    }
}
~~~

**Thread/lifetime contract của wrapper:**

- `value`, `add` và `close` đều synchronized trên cùng Java object. `close` không thể chạy giữa `requireOpen` và JNI call của một method đã lấy monitor.
- Khi resource đóng, `handle=0L` và các operation mới từ Java bị chặn bằng `IllegalStateException` trước khi vào JNI.
- `close` lặp lại trên **cùng wrapper** là no-op. Điều này **không** làm native `delete` idempotent.
- `try (counter)` hợp lệ trong Java 17; nó tự gọi close khi rời block.
- Nếu native resource có thể được sử dụng bởi C worker khác hoặc một Java wrapper thứ hai, synchronized instance **không đủ**: cần native-side lease/refcount hoặc registry.

**Không xuất public `long getHandle()` nếu người dùng có thể giả mạo/copy giá trị rồi gọi destroy độc lập.** Trong ví dụ, mọi native methods đều private; đó là encapsulation, không phải lớp phòng vệ trước mã Java độc hại có quyền reflection/Unsafe.

## 10. JNI adapter: counter_jni.cpp

Đầu tiên tạo header từ khai báo Java thật:

~~~bash
javac -h . CounterDemo.java
~~~

Lệnh tạo `CounterDemo.class`, `CounterDemo$Counter.class` và `CounterDemo.h`. Vì `native` methods khai báo trên **class CounterDemo ngoài**, tên JNI exports là `Java_CounterDemo_nCreate`, không phải tên của nested class.

~~~cpp
#include "CounterDemo.h"
#include "counter_api.h"

#include <cstdint>

static_assert(sizeof(std::uintptr_t) <= sizeof(jlong),
              "Example requires pointer width <= 64 bits");

/*
 * Chỉ dành cho trusted wrapper và một process/ABI.
 * Không serialize pointer hoặc cho caller bịa giá trị.
 */
static jlong to_java_handle(counter_handle *handle) noexcept {
    return static_cast<jlong>(
            reinterpret_cast<std::uintptr_t>(handle));
}

static counter_handle *from_java_handle(jlong handle) noexcept {
    return reinterpret_cast<counter_handle *>(
            static_cast<std::uintptr_t>(handle));
}

/* Chỉ gọi khi chưa có pending Java exception. */
static void throw_status(JNIEnv *env, int32_t status) {
    const char *klass = "java/lang/IllegalStateException";

    if (status == COUNTER_OVERFLOW) {
        klass = "java/lang/ArithmeticException";
    } else if (status == COUNTER_NO_MEMORY) {
        klass = "java/lang/OutOfMemoryError";
    } else if (status == COUNTER_BAD_ARGUMENT) {
        klass = "java/lang/IllegalArgumentException";
    }

    jclass cls = env->FindClass(klass);
    if (cls != nullptr) {
        env->ThrowNew(cls, counter_status_message(status));
        env->DeleteLocalRef(cls);
    }
}

extern "C" {

JNIEXPORT jint JNICALL
Java_CounterDemo_nVersion(JNIEnv *env, jclass klass) {
    (void)env;
    (void)klass;
    return static_cast<jint>(counter_api_version());
}

JNIEXPORT jlong JNICALL
Java_CounterDemo_nCreate(
        JNIEnv *env, jclass klass, jint initial) {
    (void)klass;

    counter_handle *created = nullptr;
    const int32_t status =
            counter_create(static_cast<int32_t>(initial), &created);

    if (status != COUNTER_OK) {
        throw_status(env, status);
        return static_cast<jlong>(0);
    }

    return to_java_handle(created);
}

JNIEXPORT jint JNICALL
Java_CounterDemo_nGet(
        JNIEnv *env, jclass klass, jlong handle) {
    (void)klass;

    int32_t value = 0;
    const int32_t status =
            counter_get(from_java_handle(handle), &value);

    if (status != COUNTER_OK) {
        throw_status(env, status);
        return static_cast<jint>(0);
    }

    return static_cast<jint>(value);
}

JNIEXPORT jint JNICALL
Java_CounterDemo_nAdd(
        JNIEnv *env, jclass klass, jlong handle, jint delta) {
    (void)klass;

    int32_t value = 0;
    const int32_t status =
            counter_add(
                    from_java_handle(handle),
                    static_cast<int32_t>(delta), &value);

    if (status != COUNTER_OK) {
        throw_status(env, status);
        return static_cast<jint>(0);
    }

    return static_cast<jint>(value);
}

JNIEXPORT void JNICALL
Java_CounterDemo_nDestroy(
        JNIEnv *env, jclass klass, jlong handle) {
    (void)env;
    (void)klass;
    counter_destroy(from_java_handle(handle));
}

} // extern "C"
~~~

### Quy tắc JNI quan trọng

- `jint` là Java integer 32-bit; C ABI dùng `int32_t` tương ứng ở những target hỗ trợ.
- `jlong` là Java 64-bit. Pointer → `uintptr_t` → `jlong` chỉ phù hợp với ABI nơi pointer có thể round-trip qua integer trong 64 bit. Capability-pointer platforms có thể yêu cầu registry/token khác.
- `JNIEnv*` gắn với thread hiện tại. Không lưu để dùng từ một native thread khác.
- `FindClass` trả JNI local reference; `DeleteLocalRef` chỉ xóa reference này, **không** hủy C++ allocation.
- `ThrowNew` đặt pending Java exception; adapter trả ngay bằng dummy value nếu status lỗi. Java sẽ nhận exception.
- `nDestroy` gọi đúng public `counter_destroy`; không dùng `free` sai allocator.
- `JNIEXPORT` xử lý việc xuất JNI symbol, còn public `COUNTER_API` xuất C ABI symbols; hai nhóm hàm có vai trò khác.
- C ABI catches C++ exceptions trước khi JNI nhận, nhưng nếu JNI adapter thêm logic C++ có thể throw, adapter cũng phải catch trước khi return.
- Forged nonzero `jlong` có thể bị cast thành pointer invalid và gây crash. Chỉ cấp quyền sử dụng qua wrapper kiểm soát lifetime hoặc xây native registry cho input không đáng tin.

## 11. Build và chạy Linux

Trong một thư mục có đúng năm files:

~~~text
counter_api.h
counter_api.cpp
c_client.c
CounterDemo.java
counter_jni.cpp
~~~

Lệnh với JDK 17+, GCC/G++:

~~~bash
javac -h . CounterDemo.java

g++ -std=c++17 -Wall -Wextra -fPIC -shared \
  -DCOUNTER_BUILD_SHARED \
  -I"$JAVA_HOME/include" \
  -I"$JAVA_HOME/include/linux" \
  counter_api.cpp counter_jni.cpp \
  -o libcounterbridge.so

gcc -std=c11 -Wall -Wextra \
  c_client.c -L. -lcounterbridge \
  -Wl,-rpath,'$ORIGIN' \
  -o c_client

./c_client
java -Djava.library.path=. CounterDemo
~~~

`g++` build C++ core + JNI adapter thành **một shared library** `libcounterbridge.so`. `gcc -std=c11` build client C thuần; việc này cho thấy public header không cần C++ syntax. `javac -h` sinh JNI header trước khi C++ adapter compile. `-Wl,-rpath,'$ORIGIN'` giúp C executable tìm library cạnh nó, còn JVM dùng `-Djava.library.path=.` để tìm JNI library.

## 12. Build và chạy macOS

~~~bash
javac -h . CounterDemo.java

clang++ -std=c++17 -Wall -Wextra -dynamiclib \
  -DCOUNTER_BUILD_SHARED \
  -I"$JAVA_HOME/include" \
  -I"$JAVA_HOME/include/darwin" \
  counter_api.cpp counter_jni.cpp \
  -Wl,-install_name,@rpath/libcounterbridge.dylib \
  -o libcounterbridge.dylib

clang -std=c11 -Wall -Wextra \
  c_client.c -L. -lcounterbridge \
  -Wl,-rpath,@loader_path \
  -o c_client

./c_client
java -Djava.library.path=. CounterDemo
~~~

`clang++` tạo `libcounterbridge.dylib`, còn `clang` compile C consumer. Native library/JVM cần cùng CPU architecture (Apple Silicon hoặc Intel). Một ứng dụng hardened runtime/code signing có thể cần thêm cấu hình loader; mẫu giả định môi trường phát triển cho phép load dylib tự build.

## 13. Build và chạy Windows

Trong **x64 Native Tools Developer Command Prompt** của MSVC (nếu JVM x64):

~~~bat
javac -h . CounterDemo.java

cl /nologo /W4 /EHsc /std:c++17 /LD ^
  /DCOUNTER_BUILD_SHARED ^
  /I "%JAVA_HOME%\include" ^
  /I "%JAVA_HOME%\include\win32" ^
  counter_api.cpp counter_jni.cpp /Fe:counterbridge.dll

cl /nologo /W4 /TC c_client.c /link counterbridge.lib

c_client.exe
java -Djava.library.path=. CounterDemo
~~~

Windows tạo `counterbridge.dll` và import library `counterbridge.lib` từ các C API exports. `System.loadLibrary("counterbridge")` dùng tên logical. Cần đảm bảo JVM, DLL, MSVC runtime dependencies và C executable đúng 32/64-bit; không trộn architectures hoặc gọi convention không tương thích.

**Ở production:** có thể tách core `libcounter_core` khỏi JNI `libcounter_jni`, nhưng phải xử lý dependency paths/load order và vẫn để C ABI là lớp độc lập với Java.

## 14. Stdout mong đợi của Java 17

~~~text
apiVersion=1
initial=40
afterAdd=42
overflow=ArithmeticException
unchanged=42
closed=true
closedTwice=true
afterClose=IllegalStateException
~~~

Phân tích:

1. `nVersion` gọi `counter_api_version` và nhận 1.
2. `Counter(40)` gọi JNI → C ABI → C++ `new`.
3. `add(2)` cập nhật 40 thành 42.
4. `add(Integer.MAX_VALUE)` bị `counter_add` chặn overflow; JNI đổi `COUNTER_OVERFLOW` thành Java `ArithmeticException`.
5. Value vẫn là 42 vì native state chưa bị sửa ở đường lỗi.
6. Rời `try (counter)`, Java `close` invalid handle rồi gọi `counter_destroy` đúng một lần.
7. Close lần hai không destroy lại.
8. Value sau close ném `IllegalStateException` ở **Java** trước khi gọi JNI.

**Lưu ý kiểm chứng:** đây là stdout xác định theo logic ví dụ khi build/load đúng. Không khẳng định mã đã được biên dịch thực tế trên mọi OS/CPU; việc kiểm thử chạy và sanitizer vẫn cần thực hiện trên toolchain đích.

## 15. C ABI ổn định cần giữ điều gì ngoài tên symbol?

**Symbol contract:** các tên export như `counter_create` phải giữ nguyên, không bị name-mangle hoặc ẩn symbol. Trên Linux dùng `nm -D`/`readelf -Ws`; macOS dùng `nm -gU`; Windows dùng `dumpbin /exports`.

**Calling convention:** nếu Windows API yêu cầu `__cdecl`, `__stdcall` hoặc convention khác, phải thể hiện thống nhất trong public declarations và implementation. `extern "C"` không giải quyết mọi khác biệt calling convention.

**Type/layout contract:** tránh C++ classes, STL, templates, references, exceptions và C bitfields trong ABI. Public structs C nếu bắt buộc phải có size/version/alignment rõ; opaque handles thường dễ ổn định hơn.

**Lifetime contract:** hàm cấp phát phải đi cặp hàm giải phóng. Không trả buffer từ `new[]` rồi yêu cầu C client `free`. Static message pointer không được client free. Double-destroy và dùng pointer sau destroy là lỗi.

**Semantic contract:** success/failure, output values và việc state có đổi trên lỗi không được thay đổi tùy tiện. Versioning phải phản ánh breaking changes.

### Giữ symbol nhưng đổi parameter type vẫn có thể phá ABI

Version 1:

~~~c
int32_t process_data(const uint8_t *data, uint32_t size);
~~~

Version 2:

~~~c
int32_t process_data(const uint8_t *data, uint64_t size);
~~~

Đây là **hai chữ ký minh họa thuộc hai phiên bản khác nhau**. C linkage vẫn có thể export cùng tên `process_data`, nhưng binary client cũ truyền `uint32_t` trong khi library mới mong đợi `uint64_t`. Link thành công **không chứng minh binary compatible**. Hãy giữ v1 và xuất một `process_data_v2` hoặc làm major ABI change theo chính sách phát hành.

### Versioning thực tế

- `counter_api_version()` trả major ABI version và có thể bổ sung API query capabilities.
- Thêm function mới thường ít phá client cũ hơn đổi chữ ký cũ.
- Không tái sử dụng status code cũ với ý nghĩa mới.
- Nếu bắt buộc có public struct, cân nhắc `struct_size`, `version` và reserved fields, nhưng vẫn phải quản lý packing/alignment.
- Kiểm thử **old binary client** với new shared library, không chỉ rebuild tất cả rồi gọi là compatible.

## 16. Không để C++ exception thoát qua biên giới

Mẫu sai:

~~~cpp
extern "C" int32_t bad_export(void) {
    throw std::runtime_error("failed");
}
~~~

Đây là **anti-pattern**, không phải hàm nên export. C caller không có C++ unwind/exception contract; JNI caller cũng không nên nhận C++ exception. Nguy cơ là terminate hoặc hành vi không được bảo đảm.

Mẫu tốt:

~~~cpp
extern "C" int32_t safe_export(void) noexcept {
    try {
        /* C++ code có thể throw. */
        return 0;
    } catch (const std::bad_alloc &) {
        return 2;
    } catch (...) {
        return 4;
    }
}
~~~

Đây là **mảnh minh họa**. `noexcept` có thể đặt ở C++ definition nhưng không đặt trực tiếp trong header C11; `catch` và không throw qua boundary mới là điều cần đảm bảo. Không nghĩ `catch (...)` bảo vệ được native pointer invalid hay signed overflow — những vấn đề ấy cần thiết kế memory safety và kiểm tra arithmetic riêng.

Ở JNI adapter, trả Java exception bằng `ThrowNew` khi không còn pending exception; sau đó native method trả ngay. JNI local refs được cleanup bằng `DeleteLocalRef`, C++ resource release bằng façade destroy. Hai cơ chế không thể thay nhau.

## 17. Dữ liệu chuỗi và buffer: không xuất std::string

Ví dụ không nên đưa qua C ABI:

~~~cpp
extern "C" std::string counter_name();
~~~

Language linkage là C, nhưng return type vẫn là C++ object với destructor/allocator/layout phụ thuộc implementation. Thay bằng **caller-owned buffer**:

~~~c
int32_t counter_name_copy(
    const counter_handle *handle,
    char *buffer,
    uint64_t capacity_bytes,
    uint64_t *required_bytes);
~~~

Hoặc **library-owned buffer với release function**:

~~~c
int32_t counter_name_alloc(
    const counter_handle *handle,
    char **out_utf8,
    uint64_t *out_size);

void counter_string_release(char *owned_utf8);
~~~

Đây là các **chữ ký minh họa**, chưa được implement trong chương trình counter. Phải document encoding (ví dụ UTF-8), byte length, NUL terminator, error khi buffer nhỏ và quyền ownership. Một pointer chuỗi do library cấp không được caller `free` trừ khi contract cho phép. JNI adapter có thể copy byte/UTF-16 sang Java `String`, nhưng Java-specific types không xuất hiện trong core C header.

## 18. Thread safety khác hoàn toàn C ABI stability

Một thư viện có stable C ABI vẫn có thể bị data race:

~~~text
Thread A: counter_get(handle)
                   |
                   +-- C++ dereference
Thread B: counter_destroy(handle)
                   |
                   +-- C++ delete
Thread A: tiếp tục dùng pointer đã free
~~~

Trong ví dụ Java, synchronized instance methods tránh close xen giữa operation trên **một Java wrapper**. Nhưng nếu C client/native worker đã giữ pointer riêng, lock Java không bảo vệ nó.

Các lựa chọn khi cần chia sẻ:

- Unique ownership và một mutex điều phối get/add/destroy.
- Shared ownership bằng `retain/release` và refcount ở native side.
- Scoped borrow/lease và close đợi mọi in-flight users.
- Opaque numeric registry token có generation/type checks để phát hiện stale/ABA handle.
- Thread-affinity contract khi SDK yêu cầu resource chỉ dùng trên một event loop.

Một check `handle != NULL` không chứng minh handle còn sống. Pointer có thể còn non-null sau destroy hoặc được allocator tái sử dụng cho allocation khác.

## 19. Lỗi phổ biến và cách xử lý

| Sai lầm | Hậu quả | Hướng sửa |
|---|---|---|
| Dùng `extern "C"` trực tiếp trong C11 header | C compiler lỗi | Guard bằng `#ifdef __cplusplus` |
| Tưởng `extern "C"` làm ABI portable tuyệt đối | Calling convention/layout vẫn khác | Thiết kế C-compatible API theo target ABI |
| Không export symbol khỏi Windows DLL | Linker/loader không thấy | `dllexport` và import library |
| Public API trả C++ class/`std::string` | Caller không có compatible ABI | Opaque handles hoặc buffers C |
| C++ exception thoát C/JNI function | Termination/undefined behavior | Catch tại C++ façade |
| C++ `new` nhưng C `free` | Allocator mismatch/UB | Matching exported destroy |
| Two owners destroy cùng handle | Double-free | Unique owner/refcount |
| Java bỏ quên close | Native leak | `AutoCloseable`/try-with-resources |
| C++ pointer copy thành `jlong` ở process khác | Địa chỉ vô nghĩa | Không serialize raw pointers |
| Forged pointer vào `counter_get` | Crash | Registry/validated opaque token |
| JNI method tên không khớp | `UnsatisfiedLinkError` | `javac -h` rồi include header |
| C `long` coi như Java `long` | Width sai trên Windows x64 | `int32_t`/`uint64_t` rõ |
| Java close race với get/add | Use-after-free | synchronized/lock/lease |
| Đổi public signature nhưng giữ symbol | Binary client cũ có thể sai ABI | API version/new function |
| Suy ra `catch (...)` bảo vệ stale pointer | C++ exceptions không bắt UB | Lifetime/validation |
| Đưa `JNIEnv*` vào core public C ABI | C clients phải phụ thuộc JVM | Tách JNI adapter |
| C gọi JNI từ thread khác với cached env | JNI thread misuse | Attach đúng thread, không share `JNIEnv*` |
| Load DLL sai kiến trúc hoặc thiếu runtime | Load failure | Kiểm tra OS/CPU/ABI/dependencies |

## 20. Kiểm thử và QA khi phát hành thư viện

1. Compile `c_client.c` thật sự bằng C11 compiler (không lén dùng g++).
2. Compile `counter_api.cpp` bằng C++17; kiểm tra exported C symbols và không có mangling ngoài ý muốn.
3. Chạy C client, xác minh version/add/overflow/state unchanged và destroy một lần.
4. Chạy `javac -h`, build JNI adapter, dùng Java 17 chạy toàn bộ output.
5. Gọi Java close nhiều lần và operation sau close; xác nhận không double-free/UAF.
6. Test API null pointers/invalid arguments theo contract; **không** fuzz raw forged pointers nếu không có registry/isolated testing.
7. Thêm tests lỗi allocation, overflow, JNI exceptions và C++ destructor policy.
8. Kiểm tra concurrency riêng: read/write/destroy cùng handle phải được đồng bộ hoặc bị cấm.
9. Kiểm tra ABI với **client binary từ phiên bản cũ**, không chỉ rebuild client.
10. Kiểm tra exported names bằng `nm`/`readelf`/`dumpbin`, dependencies với `ldd`/`otool`/`dumpbin`.
11. Dùng `java -Xcheck:jni -Djava.library.path=. CounterDemo` để phát hiện một số JNI misuse; dùng AddressSanitizer/Valgrind tương ứng để phân tích C++ memory bugs.
12. Test x86-64/ARM64, Windows/MSVC, Linux/GCC, macOS/Clang trong phạm vi target thực tế; cùng tên symbol không chứng minh binary portability xuyên platforms.

## 21. Bài tập và câu hỏi tự kiểm tra

**1. `extern "C"` có biến `std::string` thành kiểu C ABI không?** Không. Nó tác động tới language linkage, không làm STL layout portable.

**2. Vì sao header phải có `#ifdef __cplusplus`?** C11 không hiểu `extern "C"`, trong khi C++ cần nó để giữ C linkage.

**3. Vì sao dùng opaque handle?** Ẩn C++ object layout khỏi client để có thể thay implementation mà không phá struct ABI public.

**4. Ai giải phóng object do `counter_create` tạo?** Caller sở hữu owned handle và phải gọi `counter_destroy` đúng một lần.

**5. Vì sao Java không gọi `free` trên native pointer?** C++ cấp bằng `new`; phải release bằng đúng allocator/module của implementation.

**6. Tại sao `counter_add` tính tổng trong `int64_t`?** Để kiểm tra overflow trước khi cast/ghi signed 32-bit.

**7. Nếu overflow, state có thay đổi không?** Không; implementation trả status trước khi cập nhật.

**8. Tại sao JNI bridge đổi error code thành Java exception?** C core không phụ thuộc Java, còn Java caller mong đợi lỗi theo Java API.

**9. `AutoCloseable.close()` và `Arena.close()` có giống nhau?** Đây là các API khác nhau. Wrapper trong demo cho phép close lặp; một native destroy không được coi tự idempotent.

**10. Có thể đổi `uint32_t length` thành `uint64_t length` mà giữ C symbol cũ?** Không an toàn; đó là breaking ABI dù linker vẫn tìm thấy tên.

**11. C API có thread-safe chỉ vì là C ABI?** Không. Data races và resource lifetime phải được thiết kế riêng.

**12. Java 22+ có dùng cùng core C ABI không?** Có, bằng FFM downcalls qua `Linker`/`SymbolLookup`, nhưng vẫn phải quản lý opaque pointer và close đúng hạn.

**13. `counter_status_message` có trả owned string không?** Không; là borrowed static literal, caller không free.

**14. Nếu một raw pointer vẫn khác NULL sau destroy, có dùng được không?** Không; con trỏ đã dangling.

**15. Vì sao dùng C compiler để build c_client.c?** Để kiểm chứng public header thật sự dùng được bởi C, không vô tình phụ thuộc cú pháp C++.

## Tài liệu tham khảo

- [Oracle Java SE 17 — JNI Design](https://docs.oracle.com/en/java/javase/17/docs/specs/jni/design.html): native method naming, linking và JNI ABI.
- [Oracle Java SE 17 — JNI Functions](https://docs.oracle.com/en/java/javase/17/docs/specs/jni/functions.html): exceptions và local references.
- [Oracle Java SE 17 — AutoCloseable](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/AutoCloseable.html): đóng resource tường minh.
- [Oracle Java SE 22 — Linker](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/Linker.html): FFM downcalls qua native ABI.
- [Oracle Java SE 22 — SymbolLookup](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/SymbolLookup.html): tra exported functions.
- [JEP 454 — Foreign Function & Memory API](https://openjdk.org/jeps/454): FFM trở thành API chuẩn trong Java 22.
- [cppreference — Language linkage](https://en.cppreference.com/w/cpp/language/language_linkage): `extern "C"` và linkage semantics.
- [Microsoft Learn — dllexport/dllimport](https://learn.microsoft.com/en-us/cpp/cpp/dllexport-dllimport): Windows DLL symbol export/import.

## Ghi nhớ

**Một lớp C ABI ổn định quanh thư viện C++ gồm nhiều yếu tố chứ không phải chỉ `extern "C"`.** Cần public header C-compatible, exported symbols/calling convention, fixed-width types, opaque handles, exception containment, matching allocators, ownership và API versioning.

Quy trình thiết kế hữu ích:

1. Giữ C++ class, STL và exceptions **bên trong implementation**.
2. Xuất một C header biên dịch được từ C11, có `extern "C"` guard cho C++.
3. Trả status code và dữ liệu qua output pointers; document success/failure semantics.
4. Cấp/hủy resource trong cùng library; Java dùng JNI adapter thay vì động vào C++ allocator.
5. Java 17 wrapper dùng `AutoCloseable` và bảo vệ operations khỏi close race.
6. Kiểm tra symbol và ABI bằng cả C client lẫn JNI client, sử dụng old binary tests khi nâng phiên bản.
7. Khi cần JDK 22+ FFM, giữ nguyên C façade và thay đổi cách gọi Java thay vì làm public C++ ABI mới.

**Câu cần nhớ:** *C++ được phép đổi phía sau lớp vỏ; hợp đồng đi ra ngoài phải là một C ABI nhỏ, có version và ownership rõ ràng.*
