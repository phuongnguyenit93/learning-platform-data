# Ghép đúng hàm cấp phát và giải phóng của cùng thư viện hoặc bộ quản lý bộ nhớ

> **Ngữ cảnh:** Java Advance → Native Interoperability → Con trỏ và sở hữu. Bài học xây dựng quy tắc quản lý tài nguyên khi Java giao tiếp với C/C++/thư viện native qua JNI hoặc Foreign Function & Memory API (FFM): **tài nguyên do allocator/API nào cấp phải được trả về bằng đúng hàm release tương ứng của chính allocator/API đó**. Việc hai hàm cùng nhận `void*` không chứng minh có thể thay thế cho nhau. Ví dụ JNI chạy với Java 17+ và C11 trên Linux; các phần FFM dùng API ổn định từ Java 22.

## 1. Tại sao một địa chỉ không nói được ai có quyền giải phóng?

Một con trỏ C như `void *p` hoặc handle JNI `jlong` thường chỉ biểu diễn **vị trí hoặc định danh tài nguyên**. Nó không mang kèm thông tin đáng tin cậy về:

- Ai đã cấp phát, **allocator domain** nào sở hữu vùng nhớ.
- Vùng nhớ là một object đơn, mảng, mapped file, buffer từ VM hay tài nguyên nội bộ của SDK.
- Có được giải phóng bằng `free`, `delete`, `delete[]`, một hàm `sdk_release` hoặc không được giải phóng thủ công.
- Địa chỉ có phải địa chỉ đầu allocation hay chỉ là **interior pointer/view/slice**.
- Tài nguyên còn bao nhiêu chủ sở hữu, có callback hoặc luồng khác đang sử dụng không.

Ví dụ nguy hiểm:

```c
// SAI: mã này không phải ví dụ chạy; sẽ có thể gây undefined behavior.
void *p = foreign_library_create_buffer();
free(p);  // Không biết foreign_library dùng allocator nào!
```

`foreign_library_create_buffer` có thể trả pointer tới một C++ object tạo bằng `new`, một cấu trúc nằm trong arena/pool, hoặc bộ nhớ có header riêng. `free(p)` từ chương trình gọi có thể phá cấu trúc heap, bỏ qua destructor, gây double-free hoặc crash. Ngay cả khi nhìn thấy `malloc` ở code nguồn của thư viện, việc giải phóng từ một runtime/heap khác (đặc biệt qua DLL/CRT boundaries) vẫn có thể sai.

**Quy tắc đủ mạnh:** *Đúng hàm release* được xác định bởi **hợp đồng của API đã cấp tài nguyên**, không phải bằng kiểu con trỏ, tên file hay điều người gọi phỏng đoán. “Cùng thư viện” là nguyên tắc thiết kế tốt; **cùng allocator/memory manager và đúng cặp API** mới là điều kiện thực sự.

## 2. Sơ đồ ownership: owned, borrowed, transferred và shared

Trước khi viết JNI wrapper, phải xác định rõ con trỏ trả về thuộc dạng nào:

| Hợp đồng | Ai có quyền dispose? | Caller được làm gì? |
|---|---|---|
| **Owned** / new allocation | Caller nhận ownership và phải gọi hàm destroy đã quy định | Dùng, sau đó release **đúng một lần** |
| **Borrowed** / view | Owner ban đầu hoặc SDK | Chỉ đọc/ghi trong thời hạn hợp lệ; **không tự free** |
| **Transferred** / take ownership | Bên nhận mới theo API contract | Bên chuyển không còn free; bên nhận sẽ release theo contract |
| **Shared / reference-counted** | Nhiều chủ sở hữu thông qua retain/release | Mỗi retain có release tương ứng, không tự `free` object |
| **Scoped / arena-managed** | Arena, context hoặc scope | Đóng scope/context; không free từng pointer con trái contract |
| **Static / constant storage** | Compiler, module hoặc process | Không free; chỉ dùng khi module/lifetime còn hiệu lực |

Sơ đồ ownership đúng:

```text
C LIBRARY  (allocator + implementation state)
    |
    | sdk_buffer_create(n)  ->  opaque SdkBuffer *p
    v
JAVA/JNI FACADE  (owns HANDLE, not allocator internals)
    |
    | nativeGet/nativeSet(p)     [only while OPEN]
    |
    | close() -> sdk_buffer_destroy(p)
    v
C LIBRARY  (uses matching free/destructors/heap)
    |
    +-- pointer invalid after release
```

Khác biệt then chốt:

- **Pointer value** có thể sao chép tùy ý. **Ownership** không tự nhân đôi khi sao chép pointer.
- **Aliasing** (`p` và `q` cùng địa chỉ) không cho phép cả hai cùng `free`.
- **Borrowed pointer** có thể hợp lệ trong một lần callback hoặc cho đến lần gọi API kế tiếp, không nhất thiết đến lúc user chủ động `close`.
- **Handle** có thể là pointer, số nguyên token, file descriptor hoặc opaque ID; không suy ra hàm giải phóng chỉ từ cách biểu diễn.
- **GC Java** chỉ tự quản lý object Java. Nó **không** hiểu rằng một `long` đang lưu con trỏ cần `sdk_buffer_destroy`.

## 3. Bảng ghép đúng các cặp cấp phát và giải phóng

| Đối tượng / nguồn tài nguyên | Hàm tạo hoặc acquire | Hàm giải phóng phù hợp | Cấm nhầm với |
|---|---|---|---|
| C heap chuẩn trong **cùng allocator domain** | `malloc`, `calloc`, `realloc` thành công | `free` | `delete`, `delete[]`, JNI `Release...` |
| C++ object đơn | `new T(...)` | `delete p` (gọi destructor) | `free(p)`, `delete[] p` |
| C++ array | `new T[n]` | `delete[] p` | `free(p)`, `delete p` |
| C++ RAII | `std::make_unique<T>()`, container | Destructor của owner/smart pointer | `free(owner.get())` hoặc `delete owner.get()` |
| Windows aligned allocator | `_aligned_malloc` | `_aligned_free` | `free` |
| Windows COM task allocator | `CoTaskMemAlloc` | `CoTaskMemFree` | CRT `free` |
| Windows virtual memory | `VirtualAlloc` | `VirtualFree` với flags hợp lệ | `free` |
| POSIX file mapping | `mmap` | `munmap` đúng address/length | `free` |
| Third-party SDK có opaque handle | `sdk_create`, `sdk_alloc` | `sdk_destroy`, `sdk_free` do SDK công bố | `free` phía ứng dụng nếu không được phép |
| JNI string chars | `GetStringChars` / `GetStringUTFChars` | `ReleaseStringChars` / `ReleaseStringUTFChars` tương ứng | C `free` |
| JNI primitive array elements | `GetIntArrayElements` (và các kiểu khác) | `ReleaseIntArrayElements` đúng array/pointer/mode | C `free`, `DeleteLocalRef` |
| JNI critical array/string | `GetPrimitiveArrayCritical` / `GetStringCritical` | `ReleasePrimitiveArrayCritical` / `ReleaseStringCritical` | C `free` |
| JNI strong global reference | `NewGlobalRef` | `DeleteGlobalRef` | `free`, `DeleteLocalRef` |
| JNI local reference | Local ref do JNI cấp | `DeleteLocalRef` hoặc kết thúc local frame | `DeleteGlobalRef`, C `free` |
| FFM native memory do Arena cấp | `arena.allocate(...)` | `arena.close()` nếu Arena closeable | Gọi C `free` trực tiếp lên segment đó |
| FFM view of external allocation | `MemorySegment.ofAddress`, `reinterpret` | **Đúng SDK deallocator** theo owner; có thể đăng ký cleanup tương ứng | Mặc định giả định `reinterpret` tự free |
| Java `byte[]` / `int[]` | `new byte[n]`, `new int[n]` | JVM GC khi không còn reachable | C `free` lên dữ liệu Java |

Bảng là **nguyên tắc định hướng**, luôn đối chiếu tài liệu cụ thể. Ví dụ C++ có custom operator `new/delete` hoặc placement new, SDK có reference counting, `mmap`/`VirtualAlloc` dùng flags và length đặc thù. Các trường hợp này không thể được rút gọn về “cứ gọi free”.

**Với C++**, kiểu `void*` che mất thông tin constructor/destructor. C++ code nên tự bảo đảm cặp `new/delete` hoặc `new[]/delete[]`; Java chỉ nên thấy **opaque handle** và gọi một API `destroy` do C++ wrapper export.

## 4. Lỗi thiết kế thường gặp: cho Java tự chọn hàm free

Giả sử thư viện có interface:

```c
// Giao diện không tốt: trả void* mà không có ownership docs.
void *make_resource(int n);
```

Java JNI bridge nhận địa chỉ rồi nghĩ rằng có thể:

```c
// ANTI-PATTERN: KHÔNG chạy.
void *p = make_resource(100);
free(p);  // Có thể sai allocator domain, loại object, destructor.
```

Thay bằng API đối xứng:

```c
// sample_sdk.h: phía thư viện quy định rõ ownership.
typedef struct SdkBuffer SdkBuffer;

SdkBuffer *sdk_buffer_create(size_t count);
void sdk_buffer_destroy(SdkBuffer *buffer);
```

Ghi tài liệu: `sdk_buffer_create` trả **owned handle**; người gọi phải ghép với `sdk_buffer_destroy`; mỗi handle destroy **đúng một lần** sau khi mọi operation/callback đã kết thúc; handle `NULL` thể hiện tạo thất bại; không free bằng hàm khác. Cấu trúc bên trong `SdkBuffer` không lộ ra ABI nên thư viện có thể đổi allocator mà không thay code Java/JNI caller.

Một ưu điểm khác: API destroy có thể đóng file descriptor, giải phóng GPU resource, gọi destructor hoặc giải phóng buffer từ memory pool—những việc `free` đơn thuần không thể thực hiện.

## 5. C chuẩn: `malloc/calloc/realloc/free` và những bẫy cụ thể

Trong **cùng hệ thống C allocator**, vùng nhớ từ `malloc`/`calloc` trả về được trả lại bằng `free`. `realloc` có thể di chuyển allocation sang địa chỉ mới; trường hợp thành công làm pointer cũ không còn hợp lệ.

**Ví dụ C11 độc lập `c_memory_demo.c`:**

```c
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>

int main(void) {
    size_t count = 3;
    if (count > SIZE_MAX / sizeof(int32_t)) {
        return 1;
    }

    int32_t *items = calloc(count, sizeof(*items));
    if (items == NULL) {
        return 1;
    }

    items[0] = 7;
    items[1] = 11;
    items[2] = 13;

    printf("sum=%d\n", (int)(items[0] + items[1] + items[2]));

    size_t grownCount = 5;
    if (grownCount > SIZE_MAX / sizeof(*items)) {
        free(items);
        return 1;
    }

    // KHÔNG gán thẳng 'items = realloc(items, ...)'.
    int32_t *grown =
            realloc(items, grownCount * sizeof(*items));
    if (grown == NULL) {
        // realloc thất bại: items cũ vẫn hợp lệ, phải free nó.
        free(items);
        return 1;
    }

    items = grown;
    items[3] = 17;  // realloc không tự zero phần mở rộng.
    items[4] = 19;

    printf("sum5=%d\n", (int)(items[0] + items[1]
            + items[2] + items[3] + items[4]));

    free(items);
    items = NULL;   // Chỉ vô hiệu hóa local alias này.
    return 0;
}
```

Biên dịch/chạy Linux hoặc macOS có GCC/Clang:

```bash
gcc -std=c11 -Wall -Wextra -pedantic c_memory_demo.c -o c_memory_demo
./c_memory_demo
```

**stdout thành công:**

```text
sum=31
sum5=67
```

`realloc` thất bại **không** tự giải phóng vùng cũ, nên lưu result vào biến tạm. `realloc` thành công phải dùng pointer mới từ đó trở đi, kể cả khi địa chỉ hiển thị không thay đổi. Giải phóng đúng **địa chỉ gốc của allocation**; `free(items + 1)` là sai. `free(NULL)` là an toàn trong C chuẩn, nhưng **hai lần `free` cùng một non-NULL pointer** là undefined behavior. Đặt local variable về `NULL` sau khi free giúp ngăn một lỗi ở chính biến đó, nhưng **không xóa các alias khác**.

Không nhầm `calloc` zero-initialization với constructor của C++ object hoặc với bảo đảm Java object tồn tại. Với tài nguyên C++/SDK, làm đúng **lifecycle API** thay vì áp dụng mô hình C thô.

## 6. C++: destructor và khác biệt `new` với `new[]`

C++ allocations không chỉ có “số byte” mà còn có **lifetime của object**:

```cpp
#include <memory>
#include <vector>

struct Widget {
    int id;
    explicit Widget(int x) : id(x) {}
    ~Widget() { /* release object-specific resources */ }
};

void example() {
    Widget *one = new Widget(42);
    delete one;               // Đúng một object và destructor.

    Widget *many = new Widget[2]{Widget(1), Widget(2)};
    delete[] many;            // Đúng array form.

    auto owned = std::make_unique<Widget>(7);
    // Không delete/free owned.get(): unique_ptr là owner.
} // owned tự gọi destructor qua unique_ptr.
```

Đây là **hàm C++ minh họa** bên trong chương trình/library; không có `main`. Những trường hợp sau là sai:

```cpp
// ANTI-PATTERNS: KHÔNG chạy.
Widget *one = new Widget(1);
free(one);            // Destructor không chạy, allocator mismatch.

Widget *array = new Widget[2]{Widget(1), Widget(2)};
delete array;         // Sai dạng; phải delete[] array.
```

Nếu một thư viện C++ export native handle cho Java, nên tạo *C ABI facade*:

```cpp
extern "C" {
    Widget *widget_create(int id) {
        return new Widget(id);
    }

    void widget_destroy(Widget *p) {
        delete p;  // Chỉ hàm này biết đúng object/allocator.
    }
}
```

Trong sản phẩm thực, boundary C ABI không nên để exception C++ vượt qua JNI. Nên catch exception và chuyển sang error code/null, giữ `widget_destroy` noexcept khi có thể. Trường hợp class có destructor hoặc deallocator tùy biến, thư viện sở hữu chúng và cũng phải thực hiện cleanup.

### Tại sao Windows DLL/CRT đặc biệt dễ gặp mismatch?

Theo Microsoft, các DLL hoặc application liên kết với những bản CRT khác nhau có thể dùng **heap managers khác nhau**, gây heap corruption nếu cấp ở một nơi rồi `free` bằng allocator khác. Ngay cả khi CRT giống nhau, pointer cấp từ **khác heap** không tự trở nên hợp lệ để giải phóng chéo.

Không nên đưa ra quy tắc tuyệt đối rằng “bất kỳ `free` từ DLL khác đều sai”: nếu hai thành phần được thiết kế/document để dùng cùng CRT allocator và cùng heap, một số trường hợp hợp lệ. Nhưng giao diện thư viện bền vững nhất vẫn là **export hàm release riêng** để tránh bắt caller phụ thuộc vào cách liên kết CRT.

## 7. Ví dụ JNI đầy đủ: Java sở hữu handle, SDK sở hữu allocator

Ta xây một SDK C nhỏ có **opaque `SdkBuffer*`**. SDK tự `calloc` dữ liệu và tự `free` bằng `sdk_buffer_destroy`; JNI wrapper **không đụng `free`** vào tài nguyên SDK. Java chỉ giữ token `long` và cung cấp `AutoCloseable` để mọi đường kết thúc đều gọi đúng destroy.

Bài thực hành có bốn file:

- `sample_sdk.h` — định nghĩa API của SDK và ownership contract.
- `sample_sdk.c` — triển khai allocator + deallocator **cùng thư viện**.
- `OwnershipDemo.java` — Java facade và chương trình main.
- `OwnershipDemo.c` — JNI bridge gọi đúng `sdk_buffer_*`.

Môi trường: **Linux, GCC, JDK 17+**, biến `JAVA_HOME` trỏ tới JDK, các file nằm cùng thư mục. Ta build SDK thành shared library riêng `libsample_sdk.so` và JNI bridge thành `libownerdemo.so` để minh họa **ranh giới hai thư viện thật**, thay vì chỉ trình bày hai hàm trong cùng một file C.

### 7.1. Tệp `sample_sdk.h` — hợp đồng C ABI

```c
#ifndef SAMPLE_SDK_H
#define SAMPLE_SDK_H

#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

// OPAQUE: Client không biết cấu trúc và không được tự free.
typedef struct SdkBuffer SdkBuffer;

// Returns owned buffer or NULL on allocation failure.
// count must be > 0. Pair EXACTLY with sdk_buffer_destroy.
SdkBuffer *sdk_buffer_create(size_t count);

// Return 0 on success, -1 on invalid buffer/index.
int sdk_buffer_put(SdkBuffer *b, size_t index, int32_t value);
int sdk_buffer_get(const SdkBuffer *b, size_t index, int32_t *out);

// Must be called exactly once for each non-NULL owned buffer,
// after all operations finish. Accepts NULL as a no-op.
void sdk_buffer_destroy(SdkBuffer *b);

#ifdef __cplusplus
}
#endif
#endif
```

**Tính quan trọng của API:** caller **không** có cách hợp lệ tự biết `SdkBuffer` có mấy cấp phát nội bộ. Nếu sau này SDK dùng memory pool, ref-count hoặc custom allocator, JNI client vẫn không phải thay `free`/`delete`: nó chỉ gọi `sdk_buffer_destroy`.

### 7.2. Tệp `sample_sdk.c` — chính SDK tạo và hủy memory

```c
#include "sample_sdk.h"
#include <stdlib.h>
#include <stdint.h>

struct SdkBuffer {
    size_t count;
    int32_t *items;
};

SdkBuffer *sdk_buffer_create(size_t count) {
    if (count == 0 || count > SIZE_MAX / sizeof(int32_t)) {
        return NULL;
    }

    SdkBuffer *b = malloc(sizeof(*b));
    if (b == NULL) return NULL;

    b->items = calloc(count, sizeof(*b->items));
    if (b->items == NULL) {
        free(b);
        return NULL;
    }

    b->count = count;
    return b;
}

int sdk_buffer_put(SdkBuffer *b, size_t index, int32_t value) {
    if (b == NULL || index >= b->count) return -1;
    b->items[index] = value;
    return 0;
}

int sdk_buffer_get(const SdkBuffer *b, size_t index, int32_t *out) {
    if (b == NULL || out == NULL || index >= b->count) return -1;
    *out = b->items[index];
    return 0;
}

void sdk_buffer_destroy(SdkBuffer *b) {
    if (b == NULL) return;
    free(b->items);
    free(b);
}
```

**Hai cấp ownership**: SDK tạo `SdkBuffer` bằng `malloc` rồi tạo `items` bằng `calloc`. SDK destroy gọi `free(items)` trước, sau đó `free(b)`. JNI không thể chỉ `free(b)` vì sẽ rò `items`; cũng không thể tự biết đúng heap nếu SDK thay allocator.

**Thread safety:** đây là SDK ví dụ đơn giản, **không thread-safe cho concurrent get/put/destroy**. Java facade bên dưới tuần tự hóa mọi lần dùng handle trong một instance. Nếu API C thật có callbacks, native workers hoặc một SDK global handle registry, cần thêm quiescence trước destroy.

### 7.3. Tệp `OwnershipDemo.java` — Java owner có `AutoCloseable`

```java
public final class OwnershipDemo {
    static {
        System.loadLibrary("ownerdemo");
    }

    private static native long nativeCreate(int count);
    private static native void nativePut(long handle, int index, int value);
    private static native int nativeGet(long handle, int index);
    private static native void nativeDestroy(long handle);

    static final class NativeBuffer implements AutoCloseable {
        private long handle;

        NativeBuffer(int count) {
            if (count <= 0) {
                throw new IllegalArgumentException("count must be > 0");
            }
            handle = nativeCreate(count);
            if (handle == 0) {
                throw new OutOfMemoryError("nativeCreate failed");
            }
        }

        // synchronized bảo vệ check+use của handle với close().
        synchronized void set(int index, int value) {
            ensureOpen();
            nativePut(handle, index, value);
        }

        synchronized int get(int index) {
            ensureOpen();
            return nativeGet(handle, index);
        }

        private void ensureOpen() {
            if (handle == 0) {
                throw new IllegalStateException("buffer is closed");
            }
        }

        @Override
        public synchronized void close() {
            if (handle == 0) return;  // Idempotent.
            nativeDestroy(handle);   // sdk_buffer_destroy qua JNI.
            handle = 0;              // Pointer cũ không còn hợp lệ.
        }
    }

    public static void main(String[] args) {
        try (NativeBuffer buffer = new NativeBuffer(3)) {
            buffer.set(0, 7);
            buffer.set(1, 11);
            buffer.set(2, 13);

            int sum = buffer.get(0)
                    + buffer.get(1) + buffer.get(2);
            System.out.println("sum=" + sum);
            System.out.println("last=" + buffer.get(2));

            buffer.close();
            buffer.close();  // Lần hai không đụng native memory.

            try {
                buffer.get(0);
            } catch (IllegalStateException expected) {
                System.out.println(
                        "afterClose=IllegalStateException");
            }
        }  // try-with-resources gọi close lần nữa: no-op.
        System.out.println("done");
    }
}
```

`NativeBuffer` **sở hữu** một native handle cho đến khi `close()` hoàn tất. Nó không export `long handle` cho client sử dụng tùy ý. `synchronized` bảo vệ `get/set` và `close` đồng thời trên **cùng Java instance**: không có tình huống một Java thread đang dùng handle thì Java thread khác free nó ở giữa call.

**Giới hạn:** thiết kế này giả định không có native worker/callback tự sử dụng buffer sau khi `nativePut/get` trả về. Nếu SDK có xử lý bất đồng bộ, phải stop/register barrier/join trước khi destroy; Java monitor không tự biết những native workers đó.

### 7.4. Sinh JNI header

```bash
javac -encoding UTF-8 -h . OwnershipDemo.java
```

Tạo `OwnershipDemo.h` và `OwnershipDemo.class`. Không đoán JNI symbol nếu thay class/package/signature; JNI header từ compiler là nguồn đúng.

### 7.5. Tệp `OwnershipDemo.c` — JNI chỉ gọi SDK API

```c
#include <jni.h>
#include <stdint.h>
#include "OwnershipDemo.h"
#include "sample_sdk.h"

static void throwJava(JNIEnv *env, const char *type,
                      const char *message) {
    if ((*env)->ExceptionCheck(env)) return;
    jclass cls = (*env)->FindClass(env, type);
    if (cls == NULL) return;  // FindClass có thể đã ném exception.
    (*env)->ThrowNew(env, cls, message);
    (*env)->DeleteLocalRef(env, cls);
}

static SdkBuffer *fromHandle(jlong handle) {
    return (SdkBuffer *)(intptr_t)handle;
}

JNIEXPORT jlong JNICALL Java_OwnershipDemo_nativeCreate(
        JNIEnv *env, jclass owner, jint count) {
    (void)owner;
    if (count <= 0) {
        throwJava(env, "java/lang/IllegalArgumentException",
                  "count must be > 0");
        return 0;
    }

    SdkBuffer *b = sdk_buffer_create((size_t)count);
    if (b == NULL) {
        throwJava(env, "java/lang/OutOfMemoryError",
                  "sdk_buffer_create failed");
        return 0;
    }

    // Demo cho các nền tảng intptr_t có thể chứa pointer,
    // và jlong đủ rộng để lưu giá trị đó.
    return (jlong)(intptr_t)b;
}

JNIEXPORT void JNICALL Java_OwnershipDemo_nativePut(
        JNIEnv *env, jclass owner,
        jlong handle, jint index, jint value) {
    (void)owner;
    if (handle == 0) {
        throwJava(env, "java/lang/IllegalStateException",
                  "handle is closed");
        return;
    }
    if (index < 0 || sdk_buffer_put(fromHandle(handle),
                                   (size_t)index,
                                   (int32_t)value) != 0) {
        throwJava(env, "java/lang/IndexOutOfBoundsException",
                  "invalid index");
    }
}

JNIEXPORT jint JNICALL Java_OwnershipDemo_nativeGet(
        JNIEnv *env, jclass owner, jlong handle, jint index) {
    (void)owner;
    if (handle == 0) {
        throwJava(env, "java/lang/IllegalStateException",
                  "handle is closed");
        return 0;
    }
    int32_t value = 0;
    if (index < 0 || sdk_buffer_get(fromHandle(handle),
                                   (size_t)index, &value) != 0) {
        throwJava(env, "java/lang/IndexOutOfBoundsException",
                  "invalid index");
        return 0;
    }
    return (jint)value;
}

JNIEXPORT void JNICALL Java_OwnershipDemo_nativeDestroy(
        JNIEnv *env, jclass owner, jlong handle) {
    (void)env;
    (void)owner;
    if (handle == 0) return;
    sdk_buffer_destroy(fromHandle(handle)); // ĐÚNG library/API.
}
```

**Điểm quyết định:** JNI bridge không include `stdlib.h` để tự `free` pointer SDK. Nó gọi `sdk_buffer_destroy` đã được công bố bởi cùng SDK cấp phát. Phía Java cũng không gọi một API “generic free” chỉ vì `handle` là số `long`.

Trong demo chỉ cần `intptr_t` để chuyển pointer qua `jlong` trên các ABI được hỗ trợ (JVM 64-bit thông dụng). Với platform mà pointer không biểu diễn được an toàn bằng `jlong`, cần thiết kế opaque handle registry thay cho pointer-cast. Giá trị số được cast lại chỉ hợp lệ khi pointer còn sống và thuộc đúng SDK instance.

### 7.6. Biên dịch thành hai shared libraries thật

Trên Linux, từ thư mục có bốn file, sau khi đã chạy `javac -h .`:

```bash
gcc -std=c11 -fPIC -shared \
  -o libsample_sdk.so sample_sdk.c

gcc -std=c11 -fPIC -shared \
  -I"$JAVA_HOME/include" \
  -I"$JAVA_HOME/include/linux" \
  -L. -Wl,-rpath,'$ORIGIN' \
  -o libownerdemo.so OwnershipDemo.c -lsample_sdk

java -Djava.library.path=. OwnershipDemo
```

`-L. -lsample_sdk` liên kết JNI bridge tới **SDK shared library**. `-Wl,-rpath,'$ORIGIN'` đặt ELF runtime search path cạnh `libownerdemo.so` để dynamic loader tìm `libsample_sdk.so` khi chạy. Cú pháp `'$ORIGIN'` được quote để shell không khai triển biến môi trường. Với một hệ thống đóng gói/deploy thực tế, cần kiểm tra riêng RPATH/RUNPATH, loader security policies và vị trí phát hành thư viện.

Với **JDK 24+** khi JVM yêu cầu hoặc cảnh báo quyền JNI native access cho classpath, chạy:

```bash
java --enable-native-access=ALL-UNNAMED \
  -Djava.library.path=. OwnershipDemo
```

Trên macOS/Windows, điều chỉnh tên `.dylib`/`.dll`, JNI include platform-specific và thư viện liên kết theo compiler/toolchain. **Đặc biệt trên Windows:** nên đảm bảo SDK DLL export functions và Java JNI DLL import đúng ABI. Không mặc định lệnh Linux là build cross-platform.

**stdout mong đợi khi mọi bước thành công:**

```text
sum=31
last=13
afterClose=IllegalStateException
done
```

Đây là kết quả tính toán logic và trình tự Java deterministic, không phụ thuộc thứ tự scheduling vì một main thread thực hiện `set/get/close`. Nếu thiếu `libsample_sdk.so`, đường tìm thư viện sai hoặc tên JNI symbol không khớp, chương trình sẽ lỗi load/link; điều đó là **vấn đề triển khai**, không phải dấu hiệu được phép thay `sdk_buffer_destroy` bằng `free`.

## 8. Đường lỗi: ai dọn gì khi allocate/create thất bại?

Một API sở hữu tốt phải có câu trả lời cho **mọi trạng thái lỗi**:

```text
JNI nativeCreate(count)
    |
    +-- count <= 0      -> throw Java IllegalArgumentException
    |
    +-- malloc(SdkBuffer) fails
    |                        -> NULL; no allocation to free
    |
    +-- calloc(items) fails
    |                        -> sdk frees its partial SdkBuffer
    |                        -> NULL
    |
    +-- all success    -> return owned SdkBuffer * wrapped as handle
                             |
                             v
                       Java NativeBuffer
                             |
                      close() exactly once
                             |
                             v
                      sdk_buffer_destroy
```

**Cần phân biệt**:

- Allocation chưa thành công → chưa có resource phải giải phóng ở phía Java.
- Allocation thành công nhưng bước tiếp theo thất bại → dọn bằng **allocator tương ứng** cho từng sub-resource. Ví dụ `sample_sdk.c` đã `free(b)` trong nhánh `calloc` lỗi.
- Đã chuyển ownership cho Java facade → C entrypoint **không** tự free trước khi trả handle; Java `close` chịu trách nhiệm gọi destroy.
- `close` có thể được gọi nhiều lần trong Java → façade biến nó thành idempotent. **Không** gọi `sdk_buffer_destroy` hai lần trên pointer không null.
- Nếu create trả con trỏ tới borrowed/static memory thay vì owned → **không** đăng ký auto-close như một owned pointer; contract phải được công bố khác.

Nếu một SDK API có hai hàm `sdk_query(..., out)` và `sdk_free_result(...)`, caller phải giải phóng kết quả theo SDK API. Nếu hàm chỉ cho **borrowed view** hợp lệ đến lần gọi kế tiếp, không được giữ view lâu hoặc tự free. Các trường hợp cần copy phải dùng vùng đích do Java/JNI sở hữu và quản lý riêng.

### Đừng nhầm zero handle với “invalid pointer checker”

`if (handle == 0)` chỉ bắt sentinel mà Java facade đã đặt. Một `long` khác 0 vẫn có thể là pointer đã `free` nếu client bypass wrapper. **Native function không có cách portable xác minh mọi pointer tùy ý còn hợp lệ chỉ bằng cách nhìn địa chỉ.** Vì vậy:

- Ẩn handle sau private field và synchronized methods.
- Khi cần nhiều callers, dùng handle table + generation IDs/refcount/acquire-release barrier; không expose pointer thô.
- Nếu SDK có thread/callback nền, shutdown phải stop/drain/join trước destroy.
- Không gọi `nativeGet`/`nativePut` sau khi `nativeDestroy` đã release.
- Không dùng `System.gc()` hoặc `Cleaner` làm tín hiệu rằng SDK resources chắc chắn đã được giải phóng.

## 9. JNI pointers không phải vùng nhớ C bạn sở hữu

Nhiều JNI APIs trả `const char*` hoặc `jint*` khiến coder tưởng đó là `malloc` buffer. Thực tế pointer có thể là copy do JVM cấp, vùng memory bị pin hoặc một implementation-specific view.

**Ví dụ đúng cho `GetStringUTFChars`:**

```c
// Trích đoạn bên trong một JNI native method.
// env và input là tham số hợp lệ của đúng Java thread.
const char *chars = (*env)->GetStringUTFChars(env, input, NULL);
if (chars == NULL) {
    // OutOfMemoryError hoặc exception liên quan có thể pending.
    return;
}

// Xử lý bytes dạng JNI Modified UTF-8 ở đây.
// Không giữ pointer sau release, không gọi free(chars).

(*env)->ReleaseStringUTFChars(env, input, chars);
```

**Một số cặp JNI đặc trưng:**

| Acquire | Release | Ghi chú |
|---|---|---|
| `GetStringUTFChars(env,s,...)` | `ReleaseStringUTFChars(env,s,p)` | UTF-8 **modified**, không phải UTF-8 chuẩn |
| `GetStringChars(env,s,...)` | `ReleaseStringChars(env,s,p)` | UTF-16 code units |
| `GetIntArrayElements(env,a,...)` | `ReleaseIntArrayElements(env,a,p,mode)` | `mode` điều khiển copy-back/release |
| `GetByteArrayElements(env,a,...)` | `ReleaseByteArrayElements(env,a,p,mode)` | Không tự `free` pointer |
| `GetPrimitiveArrayCritical` | `ReleasePrimitiveArrayCritical` | Vùng critical: giới hạn JNI calls/blocking |
| `GetStringCritical` | `ReleaseStringCritical` | Giới hạn tương tự critical arrays |
| `NewGlobalRef` | `DeleteGlobalRef` | JNI root, không phải C heap block |
| `NewWeakGlobalRef` | `DeleteWeakGlobalRef` | Weak JNI root, không phải C heap block |

Ví dụ JNI primitive array:

```c
// Trích đoạn minh họa, array là jintArray hợp lệ.
jboolean copied = JNI_FALSE;
jint *elements = (*env)->GetIntArrayElements(env, array, &copied);
if (elements == NULL) return;

jsize n = (*env)->GetArrayLength(env, array);
for (jsize i = 0; i < n; ++i) {
    elements[i] += 1;
}

// mode 0: trả thay đổi về array nếu cần và giải phóng/unpin.
(*env)->ReleaseIntArrayElements(env, array, elements, 0);
```

**`JNI_ABORT`:** bỏ các thay đổi trong bản copy và release; nếu VM đã pin trực tiếp, việc thay đổi dữ liệu có thể đã xảy ra. **`JNI_COMMIT`:** copy back khi cần nhưng **không kết thúc việc giữ các phần tử** theo hợp đồng thông thường; cần release đúng cách sau đó để tránh leak/pin kéo dài. **`mode=0`:** copy back (nếu cần) và release.

`isCopy == JNI_FALSE` **không miễn** nghĩa vụ gọi `Release...`, cũng không cấp quyền sử dụng `free`. Trong critical region không gọi các JNI operations tùy ý hoặc block lâu. Khi mã native muốn giữ dữ liệu vượt quá lifetime của JNI acquire, hãy **copy sang allocation mình sở hữu**, rồi release pointer JNI ngay và dọn allocation copy bằng đúng allocator đã tạo nó.

## 10. Global references, local references và raw C pointers là ba loại khác nhau

Ba cách “giữ” một Java object có hợp đồng giải phóng độc lập:

- **Local JNI reference** `jobject` nhận từ tham số hoặc `FindClass`: thường chỉ hợp lệ trong thread/local frame tạo ra nó; `DeleteLocalRef` hoặc trả về Java để frame tự dọn.
- **Strong global JNI reference** do `NewGlobalRef` tạo: có thể dùng giữa threads attach cùng JVM khi còn sống; **bắt buộc** `DeleteGlobalRef` sau khi mọi callback/worker dừng. Không dùng `free` trên `jobject`.
- **Native object pointer** như `SdkBuffer*`: thuộc allocation của SDK; `sdk_buffer_destroy` mới là đúng hàm release.

Một global reference chỉ giữ **Java object** khỏi GC; nó không tự giữ sống một native pointer mà Java object chứa dưới dạng `long`. Ngược lại, một native pointer tồn tại không làm Java listener sống nếu code chỉ giữ local reference đã hết hạn. Khi SDK giữ cả native state và Java listener, shutdown phải chờ mọi callback kết thúc, sau đó xóa global references và destroy native state bằng API tương ứng.

**Kết luận nhỏ:** Đừng có một hàm chung `release(void*)` áp cho mọi JNI handle. Hãy thiết kế **owner-specific cleanup** cho từng loại tài nguyên.

## 11. FFM: bộ nhớ do Arena cấp khác với con trỏ `malloc` của thư viện

Từ JDK 22, Foreign Function & Memory API có `Arena` và `MemorySegment`. Những kiểu này giúp quản lý lifetime tốt hơn nhưng **không đổi quy tắc allocator pairing**.

### 11.1. Vùng nhớ do Java Arena cấp

**Tệp `ArenaOwnership.java` (Java 22+):**

```java
import java.lang.foreign.Arena;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.ValueLayout;

public class ArenaOwnership {
    public static void main(String[] args) {
        MemorySegment saved;

        try (Arena arena = Arena.ofConfined()) {
            MemorySegment segment = arena.allocate(ValueLayout.JAVA_INT);
            saved = segment;
            segment.set(ValueLayout.JAVA_INT, 0, 42);
            System.out.println("value=" +
                    segment.get(ValueLayout.JAVA_INT, 0));
        } // Chính Arena quản lý việc release memory.

        try {
            saved.get(ValueLayout.JAVA_INT, 0);
        } catch (IllegalStateException expected) {
            System.out.println("afterClose=IllegalStateException");
        }
    }
}
```

Chạy:

```bash
javac ArenaOwnership.java
java ArenaOwnership
```

**stdout:**

```text
value=42
afterClose=IllegalStateException
```

Ở đây memory được `arena.allocate(...)` tạo, nên **`arena.close()`** là hành động quản lý đúng. Không gọi C `free(segment.address())`, không thêm một cleanup callback khác cũng free memory. `MemorySegment.asSlice` và `asReadOnly` là views; chúng không tạo allocation độc lập và không được free riêng.

### 11.2. Con trỏ được `malloc` hoặc SDK trả về qua FFM

Khi một native function trả `void *` qua FFM downcall, nó thường được biểu diễn thành **zero-length `MemorySegment`** mang address, với lifetime không tự gắn với allocator của SDK. Chỉ tạo một view kích thước khác bằng `reinterpret` **không tự gọi `free`** và có thể nguy hiểm nếu chọn sai size hoặc dùng sau SDK free.

JDK Linker documentation đưa ra mẫu rõ ràng: `malloc.invokeExact(size)` trả pointer; `segment.reinterpret(size, arena, cleanup)` gắn view với Arena và cung cấp cleanup gọi **chính `free`**. Nếu pointer thật được SDK `sdk_alloc` tạo, cleanup phải gọi **`sdk_free` từ SDK**, **không** lấy `free` mặc định từ CRT khác.

**Pseudocode FFM, không phải file chạy độc lập:**

```java
// Các handle malloc, sdkFree và Arena đã được thiết lập;
// sdkFree trỏ đến hàm release tương ứng của CHÍNH SDK.
MemorySegment rawAddress = (MemorySegment) sdkAlloc.invokeExact(100L);

MemorySegment ownedView = rawAddress.reinterpret(
        100,
        arena,
        address -> {
            try {
                sdkFree.invokeExact(address);
            } catch (Throwable error) {
                throw new RuntimeException(error);
            }
        }
);

// Khi Arena đóng, registered cleanup sẽ gọi SDK release.
// Không gọi SDK free một lần thứ hai từ Java.
```

Đây là dạng **restricted FFM operation**; cần cấu hình quyền native access phù hợp JDK và hiểu rõ contract pointer/size. Để ví dụ trên thật sự chạy, phải khai báo đúng `MethodHandle` method types, `FunctionDescriptor`, `Linker` lookup và handle `sdkAlloc/sdkFree` theo ABI. Không diễn giải pseudocode như một API có sẵn.

**Đặc biệt nguy hiểm:** nếu sdk trả pointer **borrowed** (không owned), tuyệt đối không gắn cleanup `sdkFree`. Nếu SDK chỉ cho pointer sống tới lần gọi tiếp theo, gắn view vào Arena lâu hơn **không kéo dài lifetime thật**. Java scope bounds và native allocation lifetime phải tương thích; `reinterpret` là restricted vì JVM không thể xác minh bạn đã nói đúng.

## 12. DirectByteBuffer, Java arrays và pointer có địa chỉ mà không có quyền free

Một số byte buffers cho phép native truy cập trực tiếp, nhưng việc sở hữu phụ thuộc nguồn cấp:

**Java direct buffer**

```java
import java.nio.ByteBuffer;
ByteBuffer buffer = ByteBuffer.allocateDirect(1024);
// Java/JVM quản lý allocation của buffer theo API.
// Không truyền địa chỉ tới free() của thư viện tùy ý.
```

Đây là một trích đoạn. `GetDirectBufferAddress` trả địa chỉ truy cập tới direct buffer khi buffer thích hợp; nó **không** trao quyền `free` cho caller JNI. Buffer có thể là view của vùng nhớ được tạo ở nơi khác; người dùng phải giữ owner/Java reference sống trong suốt thời gian native sử dụng.

**`NewDirectByteBuffer` phía JNI**

```c
// Trích đoạn minh họa: p đã là vùng nhớ hợp lệ dài n byte
// và có một owner native rõ ràng.
jobject view = (*env)->NewDirectByteBuffer(env, p, (jlong)n);
```

Tạo DirectByteBuffer **không chuyển ownership một cách tự động** hay biến buffer thành owner của `p`. Native code phải quản lý `p`, callback/worker, mọi Java view đang sống, và thời điểm release. Nếu giải phóng `p` khi Java còn đọc view, có thể xảy ra use-after-free. JNI local/global reference tới `view` cũng có contract riêng và không phải C deallocator.

**Java arrays**

`jbyteArray`, `jintArray` là Java heap objects. Nếu cần copy từ SDK buffer vào Java, dùng `NewByteArray`/`SetByteArrayRegion`; sau khi copy thành công, có thể giải phóng **SDK buffer bằng SDK deallocator**. Không `free` Java array. Ngược lại, pointer từ `GetByteArrayElements` phải `ReleaseByteArrayElements`, không free. Việc **copy** là cách đổi owner dữ liệu rõ ràng: SDK vẫn sở hữu allocation cũ cho đến khi destroy, còn Java sở hữu một heap array chứa bản sao.

## 13. Nhiều allocator trong một process: C runtime, pool, GPU, OS

Có thể cùng một process có nhiều **allocation domains**:

```text
JVM heap        -> new byte[], object     -> Java GC
JVM JNI pin/copy-> GetStringUTFChars      -> ReleaseStringUTFChars
JVM FFM Arena   -> arena.allocate         -> arena.close
SDK private heap-> sdk_buffer_create      -> sdk_buffer_destroy
C++ heap        -> new T                   -> delete T
C++ array heap  -> new T[n]                -> delete[] T
Windows COM     -> CoTaskMemAlloc         -> CoTaskMemFree
OS mapping      -> mmap                   -> munmap
GPU driver      -> gpuCreateBuffer        -> gpuDestroyBuffer
```

**Cùng process không có nghĩa cùng allocator.** Các vùng nhớ có thể nằm cạnh nhau trong không gian địa chỉ ảo nhưng dùng tracking metadata và quy tắc giải phóng khác nhau. Ví dụ `VirtualAlloc` đòi `VirtualFree` với loại giải phóng/địa chỉ thích hợp; không thể vì pointer có dạng `void*` mà đưa vào C `free`.

**Cùng thư viện cũng chưa đủ:** một library có thể cung cấp hai allocator khác nhau: pool A và pool B, hoặc “temporary” arena và “persistent” heap. Vẫn phải ghép đúng **owner-specific pair**. Đặc biệt, nhiều SDK export các hàm `create`/`release`/`retain` với semantics khác hẳn `malloc/free`; tên API là một phần của contract, nhưng phải đọc docs thay vì suy đoán.

**Qua DLL boundary trên Windows:** thay vì yêu cầu mọi Java runtime và native module dùng cùng CRT heap, nên expose C ABI với hàm `sdk_buffer_destroy`. Mô hình này giảm rủi ro khi update compiler, switching `/MT` vs `/MD`, dùng plugin SDK của bên thứ ba hoặc thay nội bộ allocator.

## 14. Thứ tự giải phóng khi có callback hoặc worker nền

Đúng allocator pairing là **điều kiện cần nhưng chưa đủ**. Nếu callback/native thread vẫn dùng `SdkBuffer*` khi caller gọi `sdk_buffer_destroy` thì vẫn là use-after-free dù destroy là hàm đúng.

Một giao thức đóng đúng:

```text
OPEN
  | stop accepting new work
  v
CLOSING
  | unregister SDK callbacks / stop queueing
  | request worker stop, wake threads
  | wait in-flight callbacks to return
  | join native workers
  v
QUIESCENT
  | sdk_buffer_destroy(ownedHandle)
  | DeleteGlobalRef(listenerRef)
  | release other native resources in dependency order
  v
CLOSED
```

Không giữ mutex mà callback/worker cần trong lúc `join`. Không giải phóng library/module bằng `dlclose`/`FreeLibrary` khi callback function pointer hoặc worker vẫn có thể thực thi trong module đó. Với external library SDK, **SDK destroy/stop API** có thể tự bao gồm chờ thread, hoặc chỉ yêu cầu caller thực hiện trước; phải theo đúng tài liệu của SDK.

**Không dùng Java `finalize`/`Cleaner` làm shutdown chính.** GC không đảm bảo thời điểm callback dừng và cũng có thể bị ngăn thu gom bởi global references. Dùng `AutoCloseable`, lifecycle owner rõ ràng, shutdown barriers và dự phòng leak detection khi thực sự cần.

## 15. Các mẫu lỗi và cách sửa

| Sai lầm | Hậu quả | Cách sửa |
|---|---|---|
| `sdk_create` trả handle, Java gọi C `free` | Sai allocator, thiếu destructor/cleanup | Export và gọi `sdk_destroy` |
| C++ `new T` rồi `free` | Không gọi destructor, undefined behavior | `delete p` bên C++ owner |
| C++ `new T[n]` rồi `delete p` | Sai array form, undefined behavior | `delete[] p` |
| `malloc` rồi `delete` | Sai allocator family | C `free` từ đúng allocator |
| `_aligned_malloc` rồi `free` trên Windows | Heap corruption/mismatch | `_aligned_free` |
| `CoTaskMemAlloc` rồi `free` | Sai COM memory manager | `CoTaskMemFree` |
| `mmap` rồi `free` | Không unmap đúng | `munmap` theo OS contract |
| `GetStringUTFChars` rồi `free` | Phá JVM-managed pointer | `ReleaseStringUTFChars` |
| `GetIntArrayElements` rồi `free` | Phá JNI ownership/pin | `ReleaseIntArrayElements` |
| `NewGlobalRef` rồi `DeleteLocalRef` | Wrong reference kind | `DeleteGlobalRef` |
| `Arena.allocate` rồi C `free` trước `arena.close` | Double-free/use-after-free tiềm ẩn | Arena là owner duy nhất |
| SDK-owned `void*` gắn FFM cleanup gọi CRT `free` | Sai deallocator | Gọi SDK-specific release |
| Borrowed pointer bị đăng ký cleanup | Release memory không thuộc mình | Không cleanup borrowed view |
| `NewDirectByteBuffer` rồi quên native owner | Rò memory hoặc dangling view | Explicit handle/owner + close barrier |
| Call native với `long handle` đã close | Stale pointer, crash | Guard check+use/close; không expose handle |
| Hai Java threads `nativeGet`/`close` không lock | Check-then-use race | Monitor hoặc native refcount/acquire-release |
| Native callback còn chạy khi destroy | Use-after-free dù dùng đúng hàm | Stop/drain/join trước destroy |
| `realloc` thất bại nhưng gán đè con trỏ gốc | Mất pointer gốc gây leak | Dùng temporary pointer |
| Hai alias cùng `free` | Double free/heap corruption | Chỉ một owner, release đúng một lần |
| Native exception/error trong create bị bỏ qua | Đưa handle hỏng cho Java | Kiểm tra NULL/status, chuyển thành Java exception |

### Đối chiếu với một crash thực tế

Khi thấy `EXCEPTION_ACCESS_VIOLATION`, `SIGSEGV` hoặc heap corruption trong JNI, đặt các câu hỏi theo thứ tự:

1. **Allocation ở đâu?** Tên API, thư viện, version, CRT/toolchain, thread, thời gian.
2. **Có phải owned pointer?** Hay borrowed/local/weak/cached/static view?
3. **Release tương ứng là gì?** SDK docs có mô tả `sdk_free`/`destroy`/`retain/release` không?
4. **Có release đúng một lần?** Event/callback có thể close lại không, có alias không?
5. **Có đang được dùng?** In-flight JNI call, callback, worker, Java DirectByteBuffer view?
6. **Có ABI mismatch?** Kiểu pointer, calling convention, char encoding, size, linker?
7. **Có test instrumented?** AddressSanitizer/UBSan, valgrind khi phù hợp, CRT debug heap, `-Xcheck:jni`, logs owner-state?

**Không chữa crash** bằng cách bỏ lệnh free hoàn toàn trừ khi cần cô lập sự cố tạm thời trong test. Đúng là phải **xác định chủ sở hữu và đường cleanup**; bỏ release vô hạn sẽ gây native memory leak và có thể khiến JVM hết bộ nhớ ngoài heap.

## 16. Thực hành kiểm thử contract: không chỉ “chạy không crash”

Một tập test hữu ích cho ownership boundary:

1. **Create → use → destroy:** đọc/ghi ra giá trị đúng, không báo lỗi allocator.
2. **Create failure:** inject lỗi `malloc/calloc`; không có handle Java nửa hợp lệ hoặc rò sub-allocation.
3. **Close hai lần:** lần hai không gọi native destroy thêm; không free hai lần.
4. **Use sau close:** Java facade ném `IllegalStateException` trước native dereference.
5. **Nhiều lần mở/đóng:** chạy vòng lặp để phát hiện native leak qua RSS/heap profiler.
6. **Hai Java threads cùng dùng/đóng:** đảm bảo check+use atomic tương đối với close.
7. **Callback/worker đang chạy:** close chờ hết consumer trước destroy.
8. **API trả borrowed pointer:** xác minh caller không delete/free nó.
9. **C++ destructor:** test destructor/resource cleanup xảy ra đúng một lần qua destroy ABI.
10. **Windows DLL khác CRT:** dùng đúng exported release thay vì free chéo.
11. **FFM view external:** test cleanup callback gọi SDK deallocator đúng một lần và không được gắn vào borrowed memory.
12. **Library unload/reload:** không còn handle/function pointer tới mã thư viện đã unload.

Trong native test build, AddressSanitizer thường bắt use-after-free/double-free tốt hơn việc quan sát “stdout đúng”. Trên Java, `-Xcheck:jni` giúp phát hiện một số lỗi JNI nhưng **không kiểm tra mọi deallocator mismatch giữa các native libraries**. Kết hợp instrumentation bên C/C++/SDK.

### Checklist vận hành

- [ ] Mọi native pointer/handle có tài liệu **allocator owner**.
- [ ] Đã phân loại **owned / borrowed / transferred / shared / scope-owned**.
- [ ] Mỗi owned resource có đúng một release path với API phù hợp.
- [ ] Không đưa `free` vào nơi chỉ biết pointer nhưng không biết allocator.
- [ ] `new/delete` và `new[]/delete[]` được ghép đúng bởi code C++.
- [ ] JNI acquires được trả bằng JNI Release tương ứng, không free.
- [ ] `NewGlobalRef` được xóa bằng `DeleteGlobalRef` khi mọi worker/callback đã dừng.
- [ ] Arena-owned memory chỉ được dọn theo Arena; external pointer chỉ cleanup bằng owner-specific deallocator.
- [ ] Java facade giữ opaque handle private, đóng idempotent và không cho use-after-close.
- [ ] Nếu có thread/callback nền, đã stop/drain/join trước destroy/unload.
- [ ] Thư viện native và JNI bridge có ABI và linker contract được kiểm thử.
- [ ] Failure paths, race paths và long-running leak tests đều được kiểm tra.

## 17. Bài tập tự kiểm tra (kèm đáp án)

**Bài 1 — SDK buffer.** Hàm `sdk_alloc_result()` trả `void*` và docs ghi “caller owns result; call `sdk_free_result`”. C JNI bridge đang gọi `free(result)`. Đúng hay sai?

**Đáp án:** Sai. Cần gọi `sdk_free_result(result)`, kể cả khi thư viện nội bộ đang dùng C `malloc`: contract có thể thay đổi, và heap/CRT có thể khác.

**Bài 2 — JNI string.** `const char *s = GetStringUTFChars(env, jstr, NULL)`. Sau khi dùng, gọi `free((void*)s)` được không?

**Đáp án:** Không. Gọi `ReleaseStringUTFChars(env, jstr, s)` cùng đúng `jstring` và `JNIEnv` theo contract. Pointer có thể là copy hoặc vùng JVM quản lý; không tự quyết định deallocator.

**Bài 3 — Java long handle.** `long h` trả từ `nativeCreate`, Java `close` đã gọi native destroy, nhưng còn một thread đang `nativeGet(h)`. Cần làm gì?

**Đáp án:** Không đủ an toàn. Dùng synchronized check+use/close, hoặc native handle table với in-flight refcounts; nếu native có worker/callback nội bộ, còn phải chờ quiescence trước destroy.

**Bài 4 — C++ array.** Một API C++ tạo `new Widget[8]` và export pointer qua JNI. Bên Java nên gọi `free` hay `delete[]` trực tiếp?

**Đáp án:** Không gọi trực tiếp bên Java. SDK/C++ wrapper export `widget_array_destroy` thực hiện `delete[]` trong đúng runtime/allocator. JNI bridge gọi hàm đó.

**Bài 5 — FFM Arena.** `MemorySegment s = arena.allocate(1024)`; muốn dọn s ngay bằng downcall `free(s)` rồi để `arena.close()` chạy sau, có được không?

**Đáp án:** Không. Arena sở hữu allocation; free ngoài luồng có thể phá lifetime, rồi Arena lại dọn dẫn đến double-free. Thiết kế lại scope để đóng đúng lúc.

**Bài 6 — FFM external pointer.** SDK trả pointer borrowed sống tới lần gọi tiếp theo. Java dùng `reinterpret(n, arena, cleanup -> sdk_free)`. Sai ở đâu?

**Đáp án:** Borrowed pointer không thuộc Java; gắn cleanup tự release là sai. Cần view chỉ trong thời hạn hợp lệ, hoặc copy vào segment riêng sở hữu bởi Arena. Scope Java không gia hạn native lifetime thực tế.

**Bài 7 — realloc.** `p = realloc(p, newSize)` trả `NULL`. Vấn đề gì?

**Đáp án:** Pointer allocation cũ bị mất vì gán đè `p`, gây leak. Dùng `tmp = realloc(p,...); if(tmp) p=tmp; else /* xử lý với p cũ còn hợp lệ */`.

**Bài 8 — Windows DLL.** Một DLL tạo dữ liệu bằng private heap và trả `void*`. App dùng `free` từ CRT của mình. Vì sao nguy hiểm?

**Đáp án:** Heap managers khác nhau có metadata/giải phóng khác nhau; giải phóng chéo gây heap corruption. DLL phải cung cấp destroy/free API tương ứng và app gọi đúng API đó.

**Bài 9 — giải phóng quá sớm.** Caller dùng đúng `sdk_buffer_destroy` nhưng callback SDK vẫn có `SdkBuffer*`. Có còn lỗi không?

**Đáp án:** Có. Dùng đúng deallocator **không cho phép** free tài nguyên đang được dùng. Phải ngăn callback mới và chờ mọi in-flight callback/worker hoàn tất.

**Bài 10 — Java reference.** Một JNI wrapper tạo `jobject global = NewGlobalRef(env,obj)`, rồi dùng C `free(global)`. Sửa thế nào?

**Đáp án:** `global` là JNI global reference handle, không phải C-heap allocation; sau khi mọi thread/callback ngừng dùng, gọi `DeleteGlobalRef(env,global)` trên thread đã attach cùng JVM.

## 18. Kết luận và tài liệu gốc

**Ba câu hỏi bắt buộc trước mọi lệnh release:**

1. **Ai tạo?** Nguồn allocation và memory manager chính xác là gì?
2. **Ai sở hữu?** Owned, borrowed, transferred, shared hay arena-managed; ownership đã đổi chưa?
3. **Ai còn dùng?** Có Java/JNI call, native callback hoặc worker chưa kết thúc không?

Một lệnh destroy đúng phải đáp ứng **cả ba**. Dùng `sdk_buffer_destroy` cho `sdk_buffer_create` thay vì `free` là cách giữ hợp đồng rõ ràng qua Java–JNI–native SDK. Dùng `ReleaseStringUTFChars` sau `GetStringUTFChars`; `DeleteGlobalRef` sau `NewGlobalRef`; đóng `Arena` cho memory do Arena cấp; `delete[]` cho C++ array. Những cặp này **không có deallocator dùng chung**.

### Tài liệu tham khảo chính thức

- [Oracle JNI Specification — String operations, primitive array release, global/local refs](https://docs.oracle.com/en/java/javase/25/docs/specs/jni/functions.html)
- [Oracle JNI Specification — Invocation API và lifecycle](https://docs.oracle.com/en/java/javase/25/docs/specs/jni/invocation.html)
- [Java SE 25 — Arena: ownership, lifetime và close](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/foreign/Arena.html)
- [Java SE 25 — MemorySegment: `reinterpret`, scope và cleanup callback](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/foreign/MemorySegment.html)
- [Java SE 25 — Linker: `malloc/free` và `reinterpret(...,arena,cleanup)` example](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/foreign/Linker.html)
- [JEP 454 — Foreign Function & Memory API, Java 22](https://openjdk.org/jeps/454)
- [Microsoft Learn — Potential Errors Passing CRT Objects Across DLL Boundaries](https://learn.microsoft.com/en-us/cpp/c-runtime-library/potential-errors-passing-crt-objects-across-dll-boundaries)
- [C++ language — delete expression, scalar/array forms](https://en.cppreference.com/w/cpp/language/delete)
