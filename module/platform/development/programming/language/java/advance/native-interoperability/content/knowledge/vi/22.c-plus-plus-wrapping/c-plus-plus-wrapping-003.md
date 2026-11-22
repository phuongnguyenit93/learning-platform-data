# Dùng handle mờ để tạo, sử dụng và hủy đối tượng C++

## 1. Vấn đề: Java không thể tùy tiện điều khiển object layout của C++

Trong chủ đề **Bao bọc thư viện C++**, một yêu cầu phổ biến là cho Java tạo một đối tượng được triển khai bởi C++, gọi các phương thức của nó nhiều lần và hủy resource đúng lúc. Lớp C++ có thể chứa constructor/destructor, `std::string`, `std::vector`, `std::mutex`, virtual methods, inheritance hoặc templates. **Không có một “C++ class ABI” duy nhất bảo đảm Java hiểu được mọi bố trí class** ở các compiler, phiên bản, OS và ABI khác nhau.

Giải pháp phổ biến: tạo **C ABI wrapper** với một **opaque handle (handle mờ)**. Java chỉ giữ một token/pointer có nghĩa “đối tượng C++ của tôi”, chứ **không** nhìn thấy cấu trúc nội bộ. Những functions C-compatible thực hiện toàn bộ công việc:

1. **Create:** gọi một exported C function để tạo C++ object và trả handle.
2. **Use:** gửi handle tới exported C functions để thao tác/đọc state.
3. **Destroy:** gọi **chính hàm hủy do thư viện cung cấp** sau khi mọi lần dùng kết thúc.

~~~text
                Java client                       Native C-compatible wrapper          C++ implementation
       --------------------------------       ------------------------------------     ---------------------
       Java owner private handle --------->  counter_create(initial, &out) ----------> new CounterHandle
                  |                                  |                                     {mutex, value}
                  +--- add(handle, delta) ----------> counter_add(handle, delta, &out) -->  khóa, tăng value
                  |                                  |
                  +--- get(handle) -----------------> counter_get(handle, &out) ---------> đọc state
                  |                                  |
                  +--- close()/destroy(handle) -----> counter_destroy(handle) ----------> delete CounterHandle
                                                                                          destructor + free
~~~

**Cảnh báo quan trọng:** Opaque handle làm API dễ dùng và che giấu implementation, **không tự bảo đảm memory safety**. Sau khi `counter_destroy(h)`, giá trị bit của `h` có thể vẫn khác NULL, nhưng đã trở thành **dangling pointer**. Gọi lại hàm bằng `h` có thể gây undefined behavior, heap corruption hoặc crash JVM. Vì vậy bài này kết hợp C++ boundary, error codes, Java ownership và close-once.

### Mục tiêu học tập

Sau bài này bạn có thể:
- Phân biệt incomplete C type `typedef struct CounterHandle CounterHandle;` với struct C++ được định nghĩa private.
- Thiết kế C ABI có `counter_create`, `counter_add`, `counter_get` và `counter_destroy` cùng hợp đồng ownership.
- Giải thích `extern "C"`, native symbol export, fixed-width integer types và vì sao không export thẳng `std::string`/C++ class.
- Bắt exceptions C++ tại boundary, chuyển sang status codes; với JNI, map status thành Java exception.
- Dùng Java `AutoCloseable`, `try-with-resources` và `synchronized` để hủy đúng một lần và từ chối gọi sau close.
- Truyền handle qua JNI `jlong` hoặc FFM `MemorySegment`/`ValueLayout.ADDRESS` mà không đọc private C++ layout.
- Phân biệt lock bảo vệ trạng thái nội bộ với **lifecycle gate** ngăn destroy xen giữa các native uses.
- Chẩn đoán double-free, use-after-free, memory leak, wrong ABI, error path và library unload.

### Phiên bản và phạm vi kiểm chứng

**Đường JNI chính** chạy trên **Java 17+**. Bộ code đầy đủ đã được **compile/run trên Linux với JDK 21, GCC 14.2, C++17 và `java -Xcheck:jni`**, kèm C11 client và native concurrency test. **Đường FFM bổ sung** sử dụng API finalized `java.lang.foreign` từ **JDK 22+**, đã **compile với `javac --release 22` trên JDK 24 Windows**, nhưng **chưa chạy FFM với Windows DLL** vì máy Windows không có native C++ compiler. Các output được đánh dấu thực nghiệm hoặc kỳ vọng tương ứng; không giả định chạy trên cả ba OS khi mới có chứng cứ ở một OS.

## 2. C API header: một kiểu mờ và bộ hàm ổn định

Tạo **`native/counter_api.h`**:

~~~c
#ifndef COUNTER_API_H
#define COUNTER_API_H

#include <stdint.h>

#ifdef _WIN32
# ifdef COUNTER_BUILD
#  define COUNTER_API __declspec(dllexport)
# else
#  define COUNTER_API __declspec(dllimport)
# endif
#else
# define COUNTER_API __attribute__((visibility("default")))
#endif

#ifdef __cplusplus
extern "C" {
#endif

typedef struct CounterHandle CounterHandle;

typedef enum CounterStatus {
    COUNTER_OK = 0,
    COUNTER_BAD_ARGUMENT = 1,
    COUNTER_OVERFLOW = 2,
    COUNTER_NO_MEMORY = 3,
    COUNTER_INTERNAL_ERROR = 4
} CounterStatus;

/* Trả fixed-width int32_t; enum chỉ dùng đặt tên constants. */
COUNTER_API int32_t counter_create(
        int32_t initial, CounterHandle **out);
COUNTER_API int32_t counter_add(
        CounterHandle *h, int32_t delta, int32_t *out);
COUNTER_API int32_t counter_get(
        CounterHandle *h, int32_t *out);
COUNTER_API void counter_destroy(CounterHandle *h);

#ifdef __cplusplus
}
#endif

#endif
~~~

**Giải thích:**

- `typedef struct CounterHandle CounterHandle;` là **incomplete type**: C callers biết có một kiểu `CounterHandle` và có thể giữ `CounterHandle *`, nhưng không thấy fields; không thể gọi `sizeof(*h)` hay `h->value`. Định nghĩa thật được giữ private trong `.cpp`.
- `CounterHandle *` là pointer tới resource đã được cấp. `CounterHandle **out` cho phép `counter_create` ghi pointer mới vào biến của caller; nếu chỉ truyền `CounterHandle *` thông thường thì không đổi được pointer bên caller.
- `int32_t` thay cho `int` không định độ rộng ở public interface: Java/JNI có carrier `int` 32-bit, và FFM dùng `ValueLayout.JAVA_INT`. Return status cũng dùng `int32_t` thay vì trả trực tiếp enum C (vì kích thước enum có thể bị compiler options chi phối).
- `CounterStatus` cung cấp tên cho những lỗi rõ ràng: invalid argument, overflow, allocation failed, internal failure. Caller kiểm tra status trước khi đọc out parameters.
- `extern "C"` tạo C language linkage cho functions khi header được include bởi C++ compiler. Nó giúp tránh C++ function name mangling, **không** làm class C++ có ABI ổn định, và **không** thay các quy tắc về memory ownership.
- `COUNTER_API` điều khiển export/visibility. Với Windows DLL, dùng `COUNTER_BUILD` khi biên dịch source thư viện; với C caller include header, `__declspec(dllimport)` giúp linker dùng đúng export.
- `counter_destroy` không nhận kiểu return để báo lỗi. Contract phải yêu cầu owner truyền **một handle còn sống** và gọi **đúng một lần**. Nó cho phép NULL, nhưng không thể gọi hai lần với **cùng một non-null pointer**.

### Vì sao phải dùng function destroy của đúng thư viện?

Object tạo bởi C++ `new`/`std::make_unique` cần `delete` để gọi destructor, giải phóng `std::mutex`/resource members và dùng đúng allocator của library. Java **không được** dùng libc `free` để hủy object ấy, không nên lấy raw address rồi tự tính destructor offset, và cũng không được suy rằng JVM GC sẽ tự biết C++ object đang sống.

### Header chỉ là hợp đồng, không phải implementation

C library có thể thay `std::mutex` bằng cơ chế khác, thêm field, đổi thuật toán hoặc tối ưu storage mà **không sửa Java ABI** nếu bốn exported functions vẫn giữ signature và semantics tương thích. Đây là lý do “opaque” hữu ích hơn việc cố ánh xạ một C++ class bằng `MemoryLayout.structLayout`.

## 3. Implementation C++: private object, status code, không ném exception qua C boundary

Tạo **`native/counter_api.cpp`**:

~~~cpp
#include "counter_api.h"

#include <cstdint>
#include <limits>
#include <memory>
#include <mutex>
#include <new>

struct CounterHandle {
    std::mutex mu;
    std::int32_t value;

    explicit CounterHandle(std::int32_t initial) : value(initial) {}
};

extern "C" COUNTER_API int32_t counter_create(
        int32_t initial, CounterHandle **out) {
    if (out == nullptr) return COUNTER_BAD_ARGUMENT;

    *out = nullptr;
    if (initial < 0) return COUNTER_BAD_ARGUMENT;

    try {
        auto ptr = std::make_unique<CounterHandle>(initial);
        *out = ptr.release();
        return COUNTER_OK;
    } catch (const std::bad_alloc&) {
        return COUNTER_NO_MEMORY;
    } catch (...) {
        return COUNTER_INTERNAL_ERROR;
    }
}

extern "C" COUNTER_API int32_t counter_add(
        CounterHandle *h, int32_t delta, int32_t *out) {
    if (h == nullptr || out == nullptr || delta < 0)
        return COUNTER_BAD_ARGUMENT;

    try {
        std::lock_guard<std::mutex> lock(h->mu);

        if (delta > std::numeric_limits<std::int32_t>::max() - h->value)
            return COUNTER_OVERFLOW;

        h->value += delta;
        *out = h->value;
        return COUNTER_OK;
    } catch (...) {
        return COUNTER_INTERNAL_ERROR;
    }
}

extern "C" COUNTER_API int32_t counter_get(
        CounterHandle *h, int32_t *out) {
    if (h == nullptr || out == nullptr)
        return COUNTER_BAD_ARGUMENT;

    try {
        std::lock_guard<std::mutex> lock(h->mu);
        *out = h->value;
        return COUNTER_OK;
    } catch (...) {
        return COUNTER_INTERNAL_ERROR;
    }
}

extern "C" COUNTER_API void counter_destroy(CounterHandle *h) {
    // Owner gọi đúng một lần sau khi mọi users ngừng dùng h.
    delete h;
}
~~~

Đây là **C++ source đầy đủ** để biên dịch cùng `counter_api.h`. Trong tests thực tế, GCC 14.2 biên dịch với `-std=c++17 -Wall -Wextra -Werror -pedantic` không có warnings/errors.

### 3.1. Chi tiết về constructor và ownership transfer

`counter_create` không trả pointer trực tiếp: nó ghi qua `CounterHandle **out` và trả status. Tại đầu function, sau khi xác minh `out!=nullptr`, nó set `*out=nullptr` để caller không có pointer rác khi lỗi. `std::make_unique<CounterHandle>(initial)` giữ ownership tạm; `release()` chuyển quyền sở hữu **cho caller native C ABI**. Nếu `new` thất bại, `std::bad_alloc` được map thành `COUNTER_NO_MEMORY`.

Hợp đồng sau create:

~~~text
COUNTER_OK:
   *out != NULL
   caller sở hữu đúng MỘT CounterHandle*
   caller phải counter_destroy(*out) sau khi ngừng dùng

non-COUNTER_OK:
   *out == NULL
   caller không sở hữu object mới
   caller không gọi add/get bằng out pointer
~~~

`COUNTER_OK` chỉ đại diện trạng thái native function, không phải Java `boolean`. Mọi caller (JNI, FFM hoặc C) đều có trách nhiệm kiểm tra.

### 3.2. Chi tiết về use và overflow

`counter_add` yêu cầu delta không âm. Với counter value không âm từ constructor, điều kiện `delta > INT32_MAX - value` được kiểm tra **trước** phép cộng để không tạo signed integer overflow. Nếu không hợp lệ, function trả `COUNTER_BAD_ARGUMENT` hoặc `COUNTER_OVERFLOW`, còn `value` giữ nguyên. Khi thành công, `*out` chứa giá trị mới.

`std::lock_guard<std::mutex>` khóa/nhả mutex theo RAII. Nó bảo vệ **mutable value** khi nhiều threads gọi `counter_add/get` trên cùng object vẫn còn sống. Nhưng nếu thread khác gọi `counter_destroy`, destructor sẽ hủy cả mutex — **không có lock nội bộ nào thay thế một lifecycle gate/lease** bảo đảm object không bị xóa khi có users.

### 3.3. Chi tiết về destroy

`counter_destroy` gọi `delete h`, chạy destructor của `CounterHandle` và thu hồi memory. `delete nullptr` hợp lệ, nên `counter_destroy(nullptr)` là no-op. **Lần thứ hai với pointer cũ non-null không hợp lệ**, vì object đã bị delete; việc pointer vẫn chứa số cũ không cho biết còn live.

Các hàm C ABI không được để C++ exception đi qua ranh giới JNI/FFM. `counter_create/add/get` bắt exceptions và báo status. `CounterHandle` trong bài chỉ chứa `std::mutex` và số nguyên, destructor không ném; với class phức tạp, hãy giữ destructor không ném (thường `noexcept`) và cung cấp API cleanup báo lỗi riêng nếu cần. Không để một C++ exception vô kiểm soát thoát qua native C ABI call.

## 4. Java 17+ owner: một opaque jlong, AutoCloseable và close-once

Tạo file **`src/CounterJni.java`**:

~~~java
public final class CounterJni implements AutoCloseable {
    static {
        System.loadLibrary("counterbridge");
    }

    private long handle;

    private static native long nativeCreate(int initial);
    private static native int nativeAdd(long handle, int delta);
    private static native int nativeGet(long handle);
    private static native void nativeDestroy(long handle);

    public CounterJni(int initial) {
        this.handle = nativeCreate(initial);
        if (handle == 0L) {
            throw new IllegalStateException(
                    "nativeCreate returned null");
        }
    }

    private long openHandle() {
        if (handle == 0L) {
            throw new IllegalStateException("Counter closed");
        }
        return handle;
    }

    public synchronized int add(int delta) {
        return nativeAdd(openHandle(), delta);
    }

    public synchronized int get() {
        return nativeGet(openHandle());
    }

    @Override
    public synchronized void close() {
        if (handle != 0L) {
            long old = handle;
            handle = 0L;
            nativeDestroy(old);
        }
    }

    public static void main(String[] args) {
        try (CounterJni c = new CounterJni(10)) {
            System.out.println("added=" + c.add(7));
            System.out.println("value=" + c.get());

            try {
                c.add(-1);
                throw new AssertionError("negative delta accepted");
            } catch (IllegalArgumentException expected) {
                System.out.println("negative=IllegalArgumentException");
            }

            try {
                c.add(Integer.MAX_VALUE);
                throw new AssertionError("overflow accepted");
            } catch (ArithmeticException expected) {
                System.out.println("overflow=ArithmeticException");
            }

            if (c.get() != 17) {
                throw new AssertionError("value changed on error");
            }
        }

        CounterJni c = new CounterJni(1);
        c.close();
        c.close();

        try {
            c.get();
            throw new AssertionError("use after close accepted");
        } catch (IllegalStateException expected) {
            System.out.println("afterClose=IllegalStateException");
        }

        try {
            new CounterJni(-1);
            throw new AssertionError("negative initial accepted");
        } catch (IllegalArgumentException expected) {
            System.out.println("invalidCreate=IllegalArgumentException");
        }

        System.out.println("RESULT: PASS");
    }
}
~~~

**Mẫu này chạy Java 17+**, vì JNI đã có từ lâu. `System.loadLibrary("counterbridge")` yêu cầu JVM tìm được `libcounterbridge.so` trên Linux, `libcounterbridge.dylib` trên macOS hoặc `counterbridge.dll` trên Windows.

### 4.1. Vì sao `private long handle`?

Một JNI `jlong` chứa số nguyên 64-bit mà C++ adapter có thể dùng để round-trip pointer bit pattern trên platforms được hỗ trợ. Nó **không phải** JNI `jobject` (Java reference), không phải stable identifier qua process restart và không nên đưa vào public JSON/API để user tự sửa.

`openHandle()` ném exception khi handle đã đóng. `add/get/close` đều `synchronized`, tức không có close xen giữa một lệnh add/get **trên chính Java wrapper này**. `close()` đổi `handle` thành 0 rồi mới gọi native destructor, giúp close lần hai **không lặp lại destroy**. Có thể kiểm thử một cách an toàn bằng `get()` sau close — wrapper sẽ ném `IllegalStateException` **trước native call**.

**Giới hạn:** `synchronized` chỉ khóa monitor của **một Java instance**. Nếu bạn copy raw pointer sang wrapper khác hoặc C++ workers giữ pointer sau khi Java method return, hai owners không chia sẻ lock này và có thể gây use-after-free. Production cần single-ownership contract hoặc registry/refcount/gate rộng hơn.

### 4.2. Vì sao dùng try-with-resources thay finalizer?

`try (CounterJni c = ...)` đảm bảo `close` được gọi khi thoát block, kể cả Java exception. Native resources cần cleanup có thời điểm rõ ràng; Java GC không hứa thực thi finalizer/Cleaner ngay khi cần. `finalize()` đã bị deprecate để loại bỏ. Có thể cân nhắc `Cleaner` như **fallback** trong thiết kế chuyên biệt, nhưng không thay thế explicit close và không giải quyết race với in-flight native calls.

## 5. JNI adapter: đổi jlong thành CounterHandle* và mapping lỗi

Tạo file **`native/counter_jni.cpp`**:

~~~cpp
#include "CounterJni.h"
#include "counter_api.h"

#include <cstdint>

static_assert(sizeof(jlong) >= sizeof(void*),
              "jlong cannot store pointers");

static CounterHandle *fromHandle(jlong raw) {
    return reinterpret_cast<CounterHandle*>(
            static_cast<std::uintptr_t>(raw));
}

static jlong toHandle(CounterHandle *ptr) {
    return static_cast<jlong>(
            reinterpret_cast<std::uintptr_t>(ptr));
}

static void throwJava(JNIEnv *env,
                      const char *name,
                      const char *message) {
    jclass cls = env->FindClass(name);
    if (cls != nullptr) {
        env->ThrowNew(cls, message);
        env->DeleteLocalRef(cls);
    }
}

static bool checkStatus(JNIEnv *env, int32_t s) {
    if (s == COUNTER_OK) return true;

    switch (s) {
        case COUNTER_BAD_ARGUMENT:
            throwJava(env, "java/lang/IllegalArgumentException",
                      "bad counter argument");
            break;
        case COUNTER_OVERFLOW:
            throwJava(env, "java/lang/ArithmeticException",
                      "counter overflow");
            break;
        case COUNTER_NO_MEMORY:
            throwJava(env, "java/lang/OutOfMemoryError",
                      "native counter allocation");
            break;
        default:
            throwJava(env, "java/lang/IllegalStateException",
                      "native counter failure");
            break;
    }
    return false;
}

extern "C" JNIEXPORT jlong JNICALL Java_CounterJni_nativeCreate(
        JNIEnv *env, jclass, jint initial) {
    CounterHandle *ptr = nullptr;
    int32_t s = counter_create(
            static_cast<int32_t>(initial), &ptr);
    if (!checkStatus(env, s)) return 0L;
    return toHandle(ptr);
}

extern "C" JNIEXPORT jint JNICALL Java_CounterJni_nativeAdd(
        JNIEnv *env, jclass, jlong raw, jint delta) {
    int32_t output = 0;
    int32_t s = counter_add(
            fromHandle(raw), static_cast<int32_t>(delta), &output);
    if (!checkStatus(env, s)) return 0;
    return static_cast<jint>(output);
}

extern "C" JNIEXPORT jint JNICALL Java_CounterJni_nativeGet(
        JNIEnv *env, jclass, jlong raw) {
    int32_t output = 0;
    int32_t s = counter_get(fromHandle(raw), &output);
    if (!checkStatus(env, s)) return 0;
    return static_cast<jint>(output);
}

extern "C" JNIEXPORT void JNICALL Java_CounterJni_nativeDestroy(
        JNIEnv *, jclass, jlong raw) {
    counter_destroy(fromHandle(raw));
}
~~~

### 5.1. Những chi tiết không được lướt qua

- `CounterJni.h` phải được **sinh bằng `javac -h`** từ `CounterJni.java`; không tự đoán prototype. Khi đổi package/class/native method, cần regenerate header và điều chỉnh tên exports.
- `JNIEXPORT`/`JNICALL` là macros JNI; `extern "C"` bảo đảm tên exported JNI entry point không bị C++ mangling. `jclass` là tham số thứ hai vì Java methods là `static native`; instance native method sẽ có `jobject` thay thế.
- `std::uintptr_t` là integer đủ chứa pointer khi platform hỗ trợ; `static_assert` kiểm tra `jlong` đủ rộng cho pointer. Đây là cách làm phổ biến trên 32/64-bit systems, nhưng không biến `long` thành pointer hợp lệ tùy ý hay stable external ID. Tránh cast giữa số nguyên/địa chỉ khi không hiểu platform ABI.
- `checkStatus` chuyển C status thành pending Java exception bằng `FindClass`/`ThrowNew`. Khi có exception, JNI function trả một `0` giả để thỏa native return type; Java thấy **exception**, không dùng giá trị giả. Nếu `FindClass` thất bại, JNI có thể đã có pending exception; không tùy tiện tiếp tục gọi JNI functions.
- Không được để C++ exceptions vượt `extern "C"`/JNI boundary. Library C ABI đã bắt lỗi trong create/add/get. `counter_destroy` dùng một destructor không ném trong ví dụ.
- Adapter **không thể xác minh** rằng `raw` là một pointer còn sống. Nếu caller trực tiếp fake `jlong`, non-null check bên C++ không đủ bảo vệ. Chính vì vậy methods native là `private`, và wrapper Java kiểm soát scope sử dụng.

## 6. Build/run JNI end-to-end trên ba nền tảng

Các files:

~~~text
opaque-counter/
  src/CounterJni.java
  native/counter_api.h
  native/counter_api.cpp
  native/counter_jni.cpp
  out/                   <- javac tạo .class
  native/CounterJni.h   <- javac -h tạo JNI header
  libcounterbridge.so   <- Linux
  libcounterbridge.dylib<- macOS
  counterbridge.dll     <- Windows
~~~

Binary output chỉ có **một dạng** đúng theo OS đang build. JNI header `CounterJni.h` là generated file, không phải source viết tay.

### 6.1. Linux + GCC/G++ C++17 + JDK 17+

Chạy từ project root, nơi có thư mục `src` và `native`:

~~~sh
mkdir -p out native
javac --release 17 -h native -d out src/CounterJni.java

export JAVA_HOME="$(dirname "$(dirname "$(readlink -f "$(command -v javac)")")")"

g++ -std=c++17 -Wall -Wextra -Werror -pedantic \
  -O2 -fPIC -shared -DCOUNTER_BUILD \
  -I"$JAVA_HOME/include" -I"$JAVA_HOME/include/linux" \
  -Inative \
  -o libcounterbridge.so \
  native/counter_api.cpp native/counter_jni.cpp

java -Xcheck:jni -Djava.library.path=. -cp out CounterJni
~~~

`-DCOUNTER_BUILD` bật đúng macro export trong header. `-Xcheck:jni` kiểm tra một số lỗi dùng JNI API, **không chứng minh native heap không có use-after-free/double-free**. `JAVA_HOME` ở đây tìm JDK đang chứa `javac` trên Linux; môi trường không có `readlink -f` cần đặt thủ công JDK root chứa `include/jni.h`.

### 6.2. macOS + Clang C++17 + JDK 17+

~~~sh
mkdir -p out native
javac --release 17 -h native -d out src/CounterJni.java

export JAVA_HOME="$(/usr/libexec/java_home)"

c++ -std=c++17 -Wall -Wextra -Werror -pedantic \
  -fPIC -dynamiclib -DCOUNTER_BUILD \
  -I"$JAVA_HOME/include" -I"$JAVA_HOME/include/darwin" \
  -Inative \
  -o libcounterbridge.dylib \
  native/counter_api.cpp native/counter_jni.cpp

java -Xcheck:jni -Djava.library.path=. -cp out CounterJni
~~~

Native compiler/JDK phải cùng architecture (arm64 hay x86_64). Nếu macOS linker không thấy symbol, kiểm tra export table và JDK headers. Đây là **mẫu hướng dẫn chưa được chạy trong phiên kiểm thử Linux**, không khẳng định mọi máy macOS cho cùng output khi chưa build.

### 6.3. Windows + MSVC C++17 + JDK 17+

Mở **x64 Native Tools Command Prompt** tương ứng architecture JVM, đặt `JAVA_HOME` tới JDK. Sau khi tạo sources và thư mục `native`:

~~~bat
mkdir out
javac --release 17 -h native -d out src\CounterJni.java

cl /nologo /std:c++17 /EHsc /W4 /LD /DCOUNTER_BUILD ^
  /I"%JAVA_HOME%\include" /I"%JAVA_HOME%\include\win32" /Inative ^
  native\counter_api.cpp native\counter_jni.cpp ^
  /link /OUT:counterbridge.dll

java -Xcheck:jni -Djava.library.path=. -cp out CounterJni
~~~

Nếu `out` đã có, bỏ `mkdir out`. `/LD` build DLL; file `counterbridge.dll` phải được JVM loader tìm thấy theo `java.library.path`/OS dependencies. Trong phiên kiểm thử, môi trường Windows có JDK 24 nhưng **không có C++ compiler `cl`/`g++` trong PATH**, nên lệnh này **chưa được thực thi**. Thực hành chính đã chạy trên Linux.

### 6.4. Stdout JNI đúng đã được quan sát

~~~text
added=17
value=17
negative=IllegalArgumentException
overflow=ArithmeticException
afterClose=IllegalStateException
invalidCreate=IllegalArgumentException
RESULT: PASS
~~~

**Thông tin test:** Linux JDK 21, `javac --release 17 -h` sinh header; GCC 14.2 C++17 với `-Wall -Wextra -Werror -pedantic` biên dịch shared object; `java -Xcheck:jni` cho **đúng bảy dòng**. Các exports `Java_CounterJni_nativeCreate/nativeAdd/nativeGet/nativeDestroy` và `counter_create/add/get/destroy` đã được kiểm tra bằng `nm -D --defined-only`.

### 6.5. Đọc dòng output như một bài kiểm tra lifecycle

1. Constructor dùng `nativeCreate(10)`, C++ tạo một `CounterHandle`.
2. `add(7)` trả 17 và `get()` cũng trả 17: handle trỏ tới **cùng object**.
3. `add(-1)` bị từ chối bằng status `COUNTER_BAD_ARGUMENT`, JNI chuyển thành `IllegalArgumentException`.
4. `add(Integer.MAX_VALUE)` bị chặn overflow trước phép cộng, JNI chuyển thành `ArithmeticException`. Counter vẫn bằng 17, kiểm tra bằng assertion `get()==17`.
5. Khi `try-with-resources` kết thúc, wrapper gọi `close()` và destroy object.
6. Owner thứ hai được close **hai lần**; chỉ lần đầu gọi native destroy.
7. `get()` sau close ném `IllegalStateException` tại **Java-side openHandle check**, trước mọi native pointer dereference.
8. `new CounterJni(-1)` khiến create thất bại; JNI ném `IllegalArgumentException` và không trả object.
9. `RESULT: PASS` xác nhận các điều kiện của test này, **không có ý nghĩa bảo đảm mọi ABI hoặc mọi code C++ memory-safe**.

## 7. C client chứng minh rằng wrapper thực sự dùng C ABI

C API trên không chỉ là JNI glue. Một C program có thể include public header mà **không thấy hoặc biên dịch C++ class definition**. Tạo **`native/client.c`**:

~~~c
#include "counter_api.h"
#include <stdio.h>

int main(void) {
    CounterHandle *h = NULL;
    int32_t current = -1;

    if (counter_create(10, &h) != COUNTER_OK || h == NULL)
        return 1;

    if (counter_add(h, 7, &current) != COUNTER_OK || current != 17)
        return 2;

    if (counter_get(h, &current) != COUNTER_OK || current != 17)
        return 3;

    if (counter_add(h, -1, &current) != COUNTER_BAD_ARGUMENT)
        return 4;

    printf("cValue=%d\n", (int) current);

    counter_destroy(h);
    h = NULL;
    counter_destroy(h); /* NULL no-op, KHÔNG dùng lại pointer cũ. */

    puts("C_ABI_RESULT: PASS");
    return 0;
}
~~~

Linux, sau khi đã build `libcounterbridge.so`:

~~~sh
gcc -std=c11 -Wall -Wextra -Werror -pedantic \
  -Inative native/client.c -L. -lcounterbridge \
  -Wl,-rpath,'$ORIGIN' -o client

./client
~~~

Stdout đã kiểm thử:

~~~text
cValue=17
C_ABI_RESULT: PASS
~~~

Điểm cần thấy: C source chỉ chứa `CounterHandle*`, không biết fields, vẫn tạo/đọc/đổi/hủy object. Đây là bằng chứng **C ABI ổn định hơn nội bộ C++**, không cần JNI hoặc JDK ở client C. `-Wl,-rpath,'$ORIGIN'` giúp Linux loader tìm shared library cùng thư mục executable trong nhiều cấu hình; production cần tuân thủ loader/dependency policies của OS.

## 8. Native concurrency: mutex có ích, nhưng cần join trước destroy

Để kiểm tra value vẫn đúng khi nhiều native threads gọi add, có thể tạo **`native/concurrent.cpp`**:

~~~cpp
#include "counter_api.h"
#include <iostream>
#include <thread>
#include <vector>

int main() {
    CounterHandle *h = nullptr;
    if (counter_create(0, &h) != COUNTER_OK) return 1;

    std::vector<std::thread> threads;
    for (int i = 0; i < 4; ++i) {
        threads.emplace_back([h] {
            for (int j = 0; j < 1000; ++j) {
                int32_t next = -1;
                if (counter_add(h, 1, &next) != COUNTER_OK)
                    std::terminate();
            }
        });
    }

    for (auto &thread : threads) thread.join();

    int32_t total = -1;
    if (counter_get(h, &total) != COUNTER_OK) return 2;

    std::cout << "parallelValue=" << total << '\n';
    counter_destroy(h);

    if (total != 4000) return 3;
    std::cout << "CONCURRENT_RESULT: PASS\n";
}
~~~

Linux:

~~~sh
g++ -std=c++17 -Wall -Wextra -Werror -pedantic -pthread \
  -Inative native/concurrent.cpp -L. -lcounterbridge \
  -Wl,-rpath,'$ORIGIN' -o concurrent

./concurrent
~~~

Kết quả đã chạy:

~~~text
parallelValue=4000
CONCURRENT_RESULT: PASS
~~~

Bốn threads × 1.000 increments = 4.000. Mutex nội bộ giúp không mất updates. Nhưng **main chỉ gọi `counter_destroy(h)` sau khi đã join cả bốn threads**. Nếu gọi destroy trong lúc worker còn dùng pointer, mutex trong object cũng bị destroy — đó là race không thể chữa bằng chính mutex ấy.

### Ranh giới của Java synchronized

Tương tự, Java `synchronized` trên `CounterJni.add/get/close` đảm bảo an toàn lifecycle **trong một Java instance**. Nếu native callback dùng handle bất đồng bộ, C++ code giữ handle trong worker thread, hoặc hai wrappers cùng sở hữu pointer được copy, locking của một Java object không ngăn mọi in-flight uses. Thiết kế service cần owner/gate chung.

## 9. Hướng FFM JDK 22+: opaque handle vẫn chỉ là ADDRESS

Opaque handle không lệ thuộc JNI. Khi dùng **Foreign Function & Memory API (FFM)** từ JDK 22+, Java có thể trực tiếp gọi **C ABI wrapper** trên bằng `SymbolLookup.libraryLookup` và `Linker.downcallHandle`. Không cần biết private struct layout; `ValueLayout.ADDRESS` biểu diễn pointer.

Cần phân biệt hai loại memory:
- **`Arena` của `libraryLookup`** giữ FFM library/symbol code trong lifetime thích hợp.
- **`Arena` của mỗi call** chỉ cấp output slot: `CounterHandle **out` hoặc `int32_t *out`.
- **C++ object** được `counter_create` cấp phát bằng C++ `new`, **không** nằm trong callArena; Java phải gọi `counter_destroy`.
- Nếu đọc pointer từ `ValueLayout.ADDRESS`, nó thường có zero-length segment view; không tự xem object C++ như `MemorySegment` có layout công khai. Giữ pointer như **opaque token**, chỉ truyền lại cho C ABI functions.

### 9.1. Chương trình FFM đầy đủ: `CounterFfm.java`

Source bên dưới **đã compile trên Windows x64 JDK 24.0.2 với `javac --release 22`**, nhưng do máy Windows không có native C++ compiler/DLL tương ứng nên **chưa runtime-test `CounterFfm`**. Khi có thư viện đúng OS/architecture, chạy theo mục tiếp theo.

~~~java
import java.lang.foreign.*;
import java.lang.invoke.MethodHandle;
import java.nio.file.Path;

public final class CounterFfm {
    private static MethodHandle bind(Linker linker, SymbolLookup lib,
                                     String name, FunctionDescriptor signature) {
        MemorySegment address = lib.find(name)
                .orElseThrow(() -> new IllegalStateException(
                        "symbol missing: " + name));
        return linker.downcallHandle(address, signature);
    }

    private static void requireOK(int status) {
        if (status != 0) {
            throw new IllegalStateException("native status=" + status);
        }
    }

    public static void main(String[] args) throws Throwable {
        Path binary = Path.of(
                System.mapLibraryName("counterbridge")).toAbsolutePath();

        try (Arena libraryArena = Arena.ofConfined()) {
            Linker linker = Linker.nativeLinker();
            SymbolLookup lib =
                    SymbolLookup.libraryLookup(binary, libraryArena);

            MethodHandle create = bind(linker, lib, "counter_create",
                    FunctionDescriptor.of(ValueLayout.JAVA_INT,
                            ValueLayout.JAVA_INT, ValueLayout.ADDRESS));

            MethodHandle add = bind(linker, lib, "counter_add",
                    FunctionDescriptor.of(ValueLayout.JAVA_INT,
                            ValueLayout.ADDRESS, ValueLayout.JAVA_INT,
                            ValueLayout.ADDRESS));

            MethodHandle get = bind(linker, lib, "counter_get",
                    FunctionDescriptor.of(ValueLayout.JAVA_INT,
                            ValueLayout.ADDRESS, ValueLayout.ADDRESS));

            MethodHandle destroy = bind(linker, lib, "counter_destroy",
                    FunctionDescriptor.ofVoid(ValueLayout.ADDRESS));

            MemorySegment opaque;
            try (Arena callArena = Arena.ofConfined()) {
                MemorySegment slot = callArena.allocate(
                        ValueLayout.ADDRESS);
                requireOK((int) create.invokeExact(10, slot));

                opaque = slot.get(ValueLayout.ADDRESS, 0L);
                if (opaque.address() == 0) {
                    throw new IllegalStateException(
                            "native create returned null");
                }
            }

            try {
                try (Arena callArena = Arena.ofConfined()) {
                    MemorySegment output =
                            callArena.allocate(ValueLayout.JAVA_INT);

                    requireOK((int) add.invokeExact(opaque, 7, output));
                    System.out.println("ffiAdded="
                            + output.get(ValueLayout.JAVA_INT, 0L));

                    requireOK((int) get.invokeExact(opaque, output));
                    System.out.println("ffiValue="
                            + output.get(ValueLayout.JAVA_INT, 0L));
                }
            } finally {
                destroy.invokeExact(opaque);
            }

            System.out.println("FFM_RESULT: PASS");
        }
    }
}
~~~

### 9.2. Lệnh và expected output

Đặt file `CounterFfm.java` và native library tương ứng trong thư mục làm việc; build và chạy bằng JDK 22+:

~~~sh
mkdir -p out
javac --release 22 -d out CounterFfm.java
java --enable-native-access=ALL-UNNAMED \
  -cp out CounterFfm
~~~

**Expected output** trên một platform có binary/export đúng:

~~~text
ffiAdded=17
ffiValue=17
FFM_RESULT: PASS
~~~

**Chỉ có compile QA cho source FFM trong phiên này**; ba dòng trên là kết quả dự kiến theo native API đã test, **không phải stdout FFM đã được quan sát**. `--enable-native-access=ALL-UNNAMED` cho phép các restricted FFM operations trên classpath. Nếu dùng named Java module, cấp quyền cho đúng module.

### 9.3. Không nhầm Arena với C++ object ownership

~~~text
Library Arena OPEN
  |
  +-- SymbolLookup + MethodHandles
  |
  +-- Call Arena #1: allocate ADDRESS slot -> counter_create(10, &slot)
  |      |
  |      +-- read pointer h, then close call arena
  |
  +-- C++ object h is STILL ALIVE (allocated by new, not call arena)
  |
  +-- Call Arena #2: allocate INT output -> counter_add/get
  |      |
  |      +-- close output arena
  |
  +-- counter_destroy(h)  [must happen before unload]
  |
Library Arena CLOSE (function addresses must not be used)
~~~

Một FFM pointer `MemorySegment` chỉ biểu diễn địa chỉ. Dù Java object giữ pointer còn tồn tại, C++ resource đã mất hiệu lực ngay sau `counter_destroy`. Ngược lại, `callArena.close()` **không** xóa C++ object do native library tự cấp. Trong production, bọc pointer bằng Java `AutoCloseable` owner, reset handle về `MemorySegment.NULL` sau destroy và chặn concurrent uses.

## 10. JNI vs FFM: khác bridge, cùng lifetime contract

| Khía cạnh | JNI (Java 17+) | FFM (JDK 22+) |
|---|---|---|
| Java giữ native handle | `private long handle` | `MemorySegment` address |
| C++ nhận gì? | `CounterHandle*` sau khi JNI adapter convert `jlong` | C ABI `CounterHandle*` qua `ValueLayout.ADDRESS` |
| Cơ chế gọi C functions | JNI `Java_CounterJni_native*` adapter | `SymbolLookup` + `FunctionDescriptor` + `Linker` |
| Bảo vệ đối tượng Java | `AutoCloseable`, `synchronized` | Java owner + close gate/`AutoCloseable` |
| Bảo vệ dữ liệu C++ | C++ `std::mutex` | Vẫn cùng C++ `std::mutex` |
| Ai hủy object? | `counter_destroy` trong C++ lib | Vẫn `counter_destroy` |
| C++ class trực tiếp qua ABI? | Không | Không |
| Điều kiện runtime | JNI native library + JDK | FFM finalized JDK 22+, native access + library |
| Khi C++ tạo pointer cho out arg | JNI adapter cầm `CounterHandle **` | FFM call arena chứa ADDRESS slot |

Nên dùng JNI khi dự án phải hỗ trợ Java 17/JDK cũ, cần API JNI sâu với Java objects hoặc đã có adapter. FFM thuận tiện khi JDK22+ và muốn bind C ABI functions mà không viết thêm JNI adapter. **Không có bridge nào cho phép Java bỏ qua ownership hoặc safely dereference private C++ class layout.**

## 11. Ownership và threading cho production

### 11.1. Một owner, nhiều borrows

Nếu native resource phải sống qua nhiều Java calls, hãy có **một owner** được tạo lúc create và hủy lúc close. Mỗi method call chỉ *borrow* handle khi owner còn OPEN. Borrower không được `counter_destroy`. Khi close được yêu cầu, owner từ chối borrow mới, đợi tất cả borrow đang hoạt động kết thúc rồi destroy. Điều này giống resource lease hơn là “một pointer được chuyền tự do”.

~~~text
OPEN
  accept borrows -> activeCount++
  native operation
  release borrow -> activeCount--

request close:
  mark CLOSING
  reject new borrows
  wait activeCount == 0
  unregister callbacks / stop native workers
  counter_destroy(handle) exactly once
  mark CLOSED

CLOSED:
  no future native calls using old handle
~~~

`synchronized` trong `CounterJni` là phiên bản đơn giản cho **một owner Java và calls đồng bộ**. Khi có nhiều owners, aliases, C++ async workers hoặc callbacks, cần native registry/locks/refcounts hợp lý thay vì giả vờ tất cả methods đi qua một Java monitor.

### 11.2. Vì sao native mutex không đủ?

Mutex là một **member của C++ object**. `counter_add` khóa nó để sửa `value`. Nhưng `counter_destroy` giải phóng cả object và mutex. Nếu thread A đang chuẩn bị `lock(h->mu)` còn thread B xóa h, thread A có thể dereference freed memory. Cho phép destroy chỉ sau khi mọi native operations đã stop/join, hoặc dùng một lifecycle gate **nằm ngoài object sắp bị hủy** để bảo vệ.

### 11.3. Khi nào dùng handle registry thay pointer trực tiếp?

Nếu handle có thể bị input không tin cậy giả mạo, copy vào nhiều Java objects hoặc bị tái sử dụng lâu dài, raw pointer không có validation. Một **registry** có thể phát hành token gồm **slot index + generation ID**:

~~~text
token = (slotIndex, generation)
          |
registry.lookup(token)
          |
validate slot occupied and generation matches
          |
acquire active-use lease
          |
operate C++ CounterHandle
          |
release lease

destroy(token) -> mark closing -> reject new leases
               -> wait current leases -> delete C++ object
               -> increment generation, recycle slot
~~~

Generation giúp reject stale tokens ngay cả khi allocator tái sử dụng địa chỉ cũ (ABA problem). Nhưng registry phải được đồng bộ, bảo đảm generation không wrap trong threat model và cần explicit cleanup. **Chỉ đổi raw pointer thành số integer không tự làm mọi thứ an toàn.**

### 11.4. Native callbacks và destructor phức tạp

Nếu destructor của object dừng worker, join threads hoặc gọi Java callback, tránh giữ Java monitor/write lock trong suốt một native function có thể reenter Java và cần chính lock ấy; dễ **deadlock**. Pattern tổng quát là chuyển sang CLOSING, chặn calls mới, thả khóa cần thiết, stop/unregister callbacks, đợi in-flight work, rồi destroy khi quiescent. Bài Counter đơn giản không có callbacks, nên close đồng bộ là chấp nhận được trong scope demo.

### 11.5. Có nên tự động giải phóng bằng Cleaner?

`Cleaner` có thể là safety net nếu code quên close, nhưng không cung cấp deadline và có thể rắc rối nếu cleaner chạy trong lúc resource còn được native dùng. `finalize` bị deprecate để loại bỏ. Đối với native memory có ownership rõ, mặc định dùng `AutoCloseable`/try-with-resources; nếu thêm Cleaner, phải tích hợp state machine/close-once và bảo đảm không tạo strong reference làm đối tượng không thể reach GC.

## 12. Những lỗi phổ biến và cách chẩn đoán

| Triệu chứng | Gốc lỗi | Hướng xử lý |
|---|---|---|
| JVM báo `UnsatisfiedLinkError` khi load JNI | Thiếu `libcounterbridge.so`/DLL, wrong `java.library.path`, JNI exports không đúng | Check binary location, dependencies, bitness, `javac -h` và `nm/dumpbin` |
| C ABI exported symbol name bị mangled | Quên `extern "C"` | Kiểm tra `nm -D --defined-only`, build lại với C linkage |
| `new CounterJni(-1)` ném exception | `counter_create` trả `COUNTER_BAD_ARGUMENT` | Là hành vi dự kiến; không dùng handle khi create fail |
| Java `IllegalArgumentException` lúc add(-1) | Invalid delta được C ABI status map | Validate input và giữ state unchanged |
| Java `ArithmeticException` khi add quá lớn | Native check ngăn signed overflow | Check before arithmetic, không dựa vào undefined behavior |
| `IllegalStateException` sau close | Java wrapper đã chặn use-after-close | Đúng contract; tạo owner mới nếu muốn dùng tiếp |
| Double-free, heap corruption | Hai lần `counter_destroy(h)` với cùng non-null h | Single owner, wrapper close-once, không expose handle |
| Use-after-free | Dereference h sau destroy, h vẫn là số non-null | Gate và reset token; không dựa vào null check C++ |
| Memory leak | Quên close, create failure nửa chừng, copies không có owner | try-with-resources, rollback/cleanup, leak tests |
| `free` dùng để hủy memory tạo bằng C++ `new` | Mismatch allocator/destructor | Gọi `counter_destroy` của library |
| Deadlock lúc shutdown | Destructor callback đợi lock bị Java close giữ | Lifecycle state, quiesce callbacks, thiết kế lock order |
| Native status bị bỏ qua | Caller dùng out pointer/output khi function trả lỗi | Luôn check status trước dùng out |
| C++ exception vượt boundary | Không catch các lỗi C++ | Catch tại C ABI, map status, destructor nonthrowing |
| JNI `jlong` bị fake thành pointer | Không có validation trước deref | Private owner hoặc registry/generation IDs |
| `WrongMethodTypeException` FFM | MethodHandle carrier/arity sai | So `FunctionDescriptor` và `MethodHandle.type()` |
| `Arena.close()` nhưng object C++ còn sống | C++ `new` không phải arena allocation | Gọi `counter_destroy` riêng, trước unload library |
| Multi-thread test pass nhưng shutdown crash | Mutex bảo vệ value, không bảo vệ destroy lifecycle | Join/leases/gate bảo vệ resource lifetime |
| Java native function trả 0 khi lỗi | JNI đã có pending exception hoặc code chưa map status | Sửa JNI error mapping; không dùng giá trị giả nếu exception |
| Windows DLL build lỗi linker | Sai `/LD`, compiler/arch hoặc unresolved JNI/C++ runtime deps | MSVC Developer Prompt và export/dependency checks |

**Phân biệt lỗi:**
- **Java-side predictable**: `IllegalStateException` sau close là lỗi state được xử lý.
- **Native status**: argument/overflow/oom là lỗi C API có mã và có thể map sang Java exception.
- **Native memory corruption**: stale pointer, double delete, pointer race có thể crash JVM mà **không** có Java exception an toàn. Không dùng `try/catch(Throwable)` như một cơ chế cứu JVM khỏi lỗi C++ heap.

## 13. Kiểm thử và thiết bị quan sát theo từng lớp

**C ABI native:** dùng `gcc` compile C client chỉ biết header; `nm -D --defined-only libcounterbridge.so`/`dumpbin /EXPORTS` xác nhận names; chạy C++ direct test để kiểm tra new/use/delete. Header phải parse được dưới **C compiler**, không chỉ g++.

**JNI:** dùng `javac --release 17 -h` sinh header, build JNI adapter đúng JDK include dirs, chạy `java -Xcheck:jni`; test create/get/add, negative/overflow, close twice, get after close. `-Xcheck:jni` giúp phát hiện một số JNI API misuse, **không** có nghĩa mọi lỗi C++ memory đã được loại trừ.

**Concurrency:** N threads dùng handle còn sống, đợi join rồi destroy; có thể dùng ThreadSanitizer/ASan/native heap profiler trong môi trường thử nghiệm. Không tạo một normal test cố ý dereference freed pointer chỉ để kiểm tra nó có crash hay không.

**FFM:** compile Java 22+; khi đã có native binary đúng architecture, bật `--enable-native-access=ALL-UNNAMED` nếu code trên classpath, kiểm tra exported C symbols, mapping int32_t↔JAVA_INT và pointer↔ADDRESS. Đảm bảo callArena không bị đóng trước khi C dùng xong output slots, và library arena không bị đóng trước `counter_destroy`. Không ép Java tạo `MemoryLayout` cho opaque C++ class.

### Workflow debug khi native code crash

1. Ghi lifecycle state của owner trước mỗi create/add/get/destroy, không log raw pointer ra nơi không tin cậy.
2. Kiểm tra `counter_destroy` có được gọi một lần không và có outstanding C++ threads/callbacks không.
3. Kiểm tra C ABI symbols và signatures. `javac -h` giúp so JNI export; FFM `FunctionDescriptor` phải khớp C header.
4. Chạy C client để tách C++ implementation khỏi JVM bridge.
5. Chạy sanitizer/native debugger: Linux `gdb`/`ldd`/`nm`, macOS `lldb`/`otool`, Windows debugger/`dumpbin`.
6. Dưới tải nhiều thread, nhìn vào gate/leases và destructor, không chỉ mutex bên trong C++ object.
7. Không cố tiếp tục chạy JVM sau native memory corruption nghiêm trọng; ưu tiên fix root cause.

## 14. Câu hỏi tự kiểm tra và đáp án

**1. Opaque handle là gì?**  
Một pointer/token tới native resource với kiểu **không định nghĩa nội bộ trong public header**. Caller chỉ được truyền lại cho các public C API functions; không truy cập fields.

**2. `extern "C"` có làm class C++ portable giữa MSVC và GCC không?**  
Không. Nó giúp exposed functions dùng C linkage. C++ class layout, exception ABI và allocator vẫn private, không đi trực tiếp qua boundary.

**3. Vì sao create cần `CounterHandle **out`?**  
Vì function phải ghi pointer mới vào **biến handle của caller**, nên cần pointer-to-pointer.

**4. Vì sao status tách khỏi result?**  
Vì số 0 hoặc âm có thể là dữ liệu hợp lệ; trả `int32_t status` và ghi result qua output pointer tránh lẫn giá trị với lỗi.

**5. Sau destroy, `h!=NULL` có chứng minh h còn sống không?**  
Không. `delete` không set các biến/aliases bằng NULL; pointer có thể non-null nhưng dangling.

**6. Có thể thay `counter_destroy(h)` bằng `free(h)` không?**  
Không; object được cấp bằng C++ `new` và có destructor. Hãy dùng hàm hủy do library xuất.

**7. Java wrapper close hai lần có double-free?**  
Không trong ví dụ: `close` `synchronized`, lần đầu đặt `handle=0`; lần hai là no-op. Tuy nhiên gọi raw `counter_destroy` hai lần với cùng non-null pointer vẫn sai.

**8. Mutex trong object có đủ để destroy song song với add không?**  
Không. Destructor hủy chính mutex/object. Cần lifecycle gate hoặc bảo đảm mọi users join/release trước delete.

**9. FFM Arena đóng có tự delete CounterHandle?**  
Không. Arena chỉ sở hữu memory nó allocate và scope library/symbol được liên kết, không tự biết C++ `new` trong `counter_create`. Phải gọi `counter_destroy` tường minh.

**10. Khi nào dùng registry thay raw pointer?**  
Khi token có thể đến từ untrusted callers, bị alias qua nhiều owners hoặc cần reject stale handles. Registry + generation + lease giúp ngăn nhiều lỗi, nhưng phải đồng bộ chính nó.

**11. C++ exception có thể đi xuyên qua JNI xuống Java một cách tự động không?**  
Không nên dựa vào điều ấy. C ABI/JNI wrappers phải catch C++ exceptions và map sang error codes/Java exceptions, không để C++ exception thoát biên.

**12. FFM bắt buộc từ JDK nào theo mã trong bài?**  
Mã sử dụng `java.lang.foreign` finalized từ JDK **22**; JNI example chạy JDK 17+. Source FFM đã compile JDK24 `--release 22` nhưng chưa runtime test trên Windows native DLL.

## 15. Checklist trước khi dùng trong dự án thật

- [ ] Public header chỉ lộ `CounterHandle*` incomplete type và C-compatible API, không lộ C++ STL/classes.
- [ ] Functions được export với `extern "C"` và visibility đúng, kiểm tra symbol table trên từng OS.
- [ ] ABI dùng fixed-width types, rõ return status, pointer out parameters và ownership.
- [ ] `counter_create` đặt out=null khi fail, catch exceptions và không leak object.
- [ ] `counter_add/get` kiểm tra null/arguments/overflow; native state được bảo vệ khi nhiều threads hợp lệ cùng dùng.
- [ ] `counter_destroy` do đúng native library gọi đúng một lần, sau mọi borrows; không dùng `free` khác allocator.
- [ ] Java JNI owner dùng `private long`, `AutoCloseable`, `synchronized` hoặc lifecycle gate và close-once.
- [ ] JNI header được `javac -h` sinh từ Java native declarations; đúng class/package, generated prototypes, JNI include paths.
- [ ] JNI error mapping có `ThrowNew` cho invalid arguments/overflow/OOM; không để C++ exception vượt C boundary.
- [ ] FFM Java chỉ dùng `ValueLayout.ADDRESS` cho opaque pointer, không đọc private object layout; JDK22+ native-access flags đúng.
- [ ] FFM library arena và call arena phân tách lifetime; C++ object hủy trước khi library unload.
- [ ] Không expose raw pointer/`jlong` cho mã untrusted; nếu cần public token, cân nhắc generation registry.
- [ ] Không destroy khi C++ threads, callbacks hoặc JNI/FFM calls còn in-flight; lock order tránh deadlock.
- [ ] Có test native C ABI, JNI status, close twice/after-close, concurrency và leak checks.
- [ ] Biên dịch trên đúng OS/arch/compiler ABI, chạy `nm`/`dumpbin` và kiểm tra native dependencies.
- [ ] Không coi `-Xcheck:jni`, Java `synchronized` hay GC là bằng chứng native memory hoàn toàn an toàn.

## 16. Tổng kết và tài liệu tham khảo

~~~text
Opaque handle = quyền mượn/sở hữu C++ resource, KHÔNG phải Java object.
C header      = create / use / destroy C ABI contract, không lộ C++ layout.
C++ source    = new, methods, mutex, delete và bắt exception.
Java wrapper  = AutoCloseable, private handle, close-once và reject after-close.
JNI           = jlong handle + JNI exported methods.
FFM JDK22+    = ADDRESS handle + Linker downcalls.
~~~

**Khi thiết kế tốt**, Java không cần biết object C++ được cấp bao nhiêu bytes hay có những virtual methods nào. **Khi thiết kế chưa tốt**, opaque pointer chỉ che giấu double-delete và use-after-free cho đến lúc JVM crash. Vì vậy mỗi binding cần có một hợp đồng rõ: **create thành công → use trong scope hợp lệ → ngăn borrows mới → đợi calls hoàn tất → destroy đúng một lần**.

Nguồn tham khảo:
- [Oracle Java SE 21 — Java Native Interface Specification](https://docs.oracle.com/en/java/javase/21/docs/specs/jni/index.html)
- [Oracle Java SE 21 — JNI Design Overview](https://docs.oracle.com/en/java/javase/21/docs/specs/jni/design.html)
- [Oracle Java SE 21 — JNI Functions](https://docs.oracle.com/en/java/javase/21/docs/specs/jni/functions.html)
- [OpenJDK JEP 454 — Foreign Function & Memory API finalized in JDK 22](https://openjdk.org/jeps/454)
- [Oracle Java SE 22 — java.lang.foreign package](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/package-summary.html)
- [Oracle Java SE 22 — Linker](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/Linker.html)
- [Oracle Java SE 22 — Arena](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/Arena.html)
- [Oracle Java SE 22 — SymbolLookup](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/SymbolLookup.html)

Giới hạn QA: JNI/native C ABI được **build và chạy** trên Linux, JDK21/GCC14; FFM alternative được **compile** trên JDK24 Windows bằng `--release 22` nhưng **chưa chạy** với Windows DLL. Khi đưa vào production, biên dịch và chạy lại trên OS/architecture/ABI của dự án, không suy một lần PASS là chứng minh mọi biến thể toolchain an toàn.