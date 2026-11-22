# Phân biệt `jlong`, địa chỉ bản địa và kiểu con trỏ của C

Trong Java Native Interface (JNI), một đối số `long` của Java được biểu diễn bên C bằng `jlong`. Trong khi đó, địa chỉ của một vùng nhớ native thường nằm trong biến kiểu `void *`, `char *`, `struct T *` hoặc một kiểu con trỏ C khác. Trên máy 64-bit, các giá trị này thường có cùng độ rộng 64 bit, nhưng **chúng không cùng kiểu, không cùng ý nghĩa và không có cùng vòng đời**.

Sự nhầm lẫn rất thường gặp là: “Java `long` có 64 bit, vậy có thể coi nó là địa chỉ ở mọi nơi”. Điều này nguy hiểm trên nền tảng 32-bit, Windows 64-bit, khi vùng nhớ đã giải phóng, khi GC di chuyển Java object, hoặc khi một con số bất kỳ bị chuyển thành con trỏ. Bài này trình bày cách phân biệt chính xác các khái niệm, cách thiết kế chữ ký JNI, điều kiện chuyển đổi có kiểm soát và một ví dụ Java 17 + C11 chạy được.

## 1. Ba khái niệm cần tách riêng

| Khái niệm | Kiểu ở đâu? | Bản chất | Độ rộng/đặc điểm | Ai quản lý vòng đời? |
| --- | --- | --- | --- | --- |
| `long` | Ngôn ngữ Java | Số nguyên có dấu | **Luôn 64 bit** theo Java | JVM quản lý giá trị primitive |
| `jlong` | Header JNI `jni.h` | Kiểu nguyên thủy native tương ứng Java `long` | **Có dấu, 64 bit** theo JNI | Một giá trị C bình thường, không sở hữu bộ nhớ |
| Địa chỉ native | Không phải một kiểu C riêng | Giá trị tham chiếu tới vị trí trong không gian địa chỉ của tiến trình | Phụ thuộc ABI/kiến trúc và biểu diễn con trỏ | Vùng nhớ đằng sau địa chỉ có lifetime riêng |
| `T *` / `void *` | C/C++ | Con trỏ có kiểu hoặc con trỏ đối tượng tổng quát | `sizeof(void *)` thường 4 hoặc 8 byte trên nền tảng phổ biến | Phải theo contract của allocation |
| `intptr_t` / `uintptr_t` | `<stdint.h>` của C99+ | Kiểu số nguyên có khả năng chứa biểu diễn con trỏ tới đối tượng để round-trip nếu implementation cung cấp | Phù hợp với con trỏ trên implementation đó; **không bắt buộc được hỗ trợ** bởi mọi C implementation | Chỉ chứa số, không kéo dài lifetime |
| `jobject` / `jstring` | JNI | **Reference opaque** của JVM tới Java object | Không được coi như địa chỉ ổn định của object | JVM và các quy tắc local/global JNI references |

Ba ví dụ để nhớ:

- `jlong n = 123;`: đây là **số 123**; không có vùng nhớ native được tạo ra.
- `int *p = malloc(sizeof *p);`: `p` chứa **con trỏ** tới vùng nhớ native, nếu `malloc` thành công; phải giải phóng theo hợp đồng.
- `jlong handle = (jlong)(intptr_t)(void *)p;`: đây là một **quy ước mã hóa con trỏ thành số** do ứng dụng quyết định. JNI không tự theo dõi hay xác thực handle này.

Đặc biệt, Java `Long` (chữ L hoa) là một **object wrapper**: nếu truyền nó vào native method thì JNI nhận `jobject` (với chữ ký object), không phải `jlong` primitive. Không tự ép tham chiếu đối tượng JVM sang `void *` để lấy “địa chỉ Java object”.

## 2. Độ rộng của các kiểu theo ABI

Không được suy ra kích thước `long` của C từ `long` của Java. Trên các ABI thường gặp:

| Nền tảng thường gặp | Mô hình dữ liệu | C `int` | C `long` | `void *` | `intptr_t` | JNI `jlong` |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| Linux 32-bit x86 | ILP32 | 32 | 32 | 32 | 32 | 64 |
| Linux/macOS 64-bit thông dụng | LP64 | 32 | 64 | 64 | 64 | 64 |
| Windows 64-bit | LLP64 | 32 | **32** | 64 | 64 | 64 |

Các con số trong bảng là **bit**; đây là những ABI phổ biến, không phải cam kết cho mọi CPU hoặc mọi C implementation. Có môi trường dùng con trỏ có biểu diễn đặc biệt hoặc rộng hơn 64 bit; ví dụ mẫu bên dưới chủ động không hỗ trợ kiểu môi trường đó.

Hệ quả:

1. `(long)ptr` có thể **cắt mất nửa trên địa chỉ trên Windows 64-bit** vì C `long` chỉ 32 bit.
2. `(jint)ptr` cũng không an toàn cho con trỏ 64-bit. `jint` là số nguyên signed 32 bit.
3. `sizeof(jlong) == sizeof(void *)` trên nhiều máy 64-bit **không biến `jlong` thành con trỏ**; kích thước bằng nhau không bảo đảm quyền truy cập, tính hợp lệ hoặc ownership.
4. `size_t` dùng biểu diễn kích thước đối tượng, `ptrdiff_t` dùng biểu diễn hiệu hai con trỏ trong những trường hợp hợp lệ; cả hai không phải “kiểu con trỏ JNI”. Trên nhiều ABI chúng có độ rộng gần con trỏ, nhưng phải kiểm tra hợp đồng cụ thể.
5. `jlong` signed. Nếu handle là số âm sau chuyển đổi, không được tùy tiện kết luận nó là lỗi chỉ vì `handle < 0`.

Trong JNI, chữ ký JVM cho Java primitive `long` là **`J`**; với `int` là **`I`**; với `void` là **`V`**. Chúng mô tả **kiểu dữ liệu truyền qua JNI**, không mô tả liệu số `long` có chứa pointer hay không.

## 3. `intptr_t` và `uintptr_t`: khi nào được dùng?

Header C `<stdint.h>` có thể định nghĩa:

- `intptr_t`: một kiểu **nguyên có dấu** đủ khả năng để biểu diễn địa chỉ con trỏ **tới đối tượng** theo quy tắc round-trip của implementation.
- `uintptr_t`: phiên bản **nguyên không dấu**, hữu ích khi thao tác/hiển thị bit hoặc kiểm tra giá trị địa chỉ theo quy ước nền tảng.

Hai kiểu này là **tùy chọn theo chuẩn C**: có implementation không thể cung cấp chúng. Khi tồn tại, có thể chuyển `void *` → kiểu số nguyên tương ứng → `void *` và lấy lại con trỏ so sánh bằng con trỏ gốc, miễn là không mất dữ liệu và không vi phạm lifetime. Đây là bảo đảm về **giá trị con trỏ**, không phải lời hứa con trỏ vẫn còn trỏ tới một đối tượng đang sống.

Điểm giới hạn quan trọng: việc chuyển đổi qua `intptr_t`/`uintptr_t` được mô tả cho **con trỏ tới đối tượng**, không phải quy tắc phổ quát cho **function pointer**. Không mặc định ép con trỏ hàm thành `jlong`/`void *` trên mọi C ABI.

### 3.1. Quy ước có kiểm soát cho object pointer ↔ `jlong`

Với implementation có `intptr_t` và con trỏ không rộng hơn 64 bit:

```c
#include <jni.h>
#include <stdint.h>

#ifndef INTPTR_MAX
#  error "This C implementation has no intptr_t"
#endif

_Static_assert(sizeof(intptr_t) <= sizeof(jlong),
               "This JNI handle cannot hold a native pointer");

typedef struct NativeState NativeState;

static jlong encode_pointer(NativeState *p) {
    return (jlong)(intptr_t)(void *)p;
}

static NativeState *decode_pointer(jlong raw) {
    return (NativeState *)(void *)(intptr_t)raw;
}
```

Giải thích từng bước:

1. `NativeState *` → `void *`: chuyển một **object pointer** sang con trỏ đối tượng tổng quát.
2. `void *` → `intptr_t`: chuyển qua **kiểu nguyên phù hợp với độ rộng/con trỏ** của implementation; có round-trip nếu dùng đúng điều kiện.
3. `intptr_t` → `jlong`: chuyển **số nguyên signed** sang kiểu JNI signed 64-bit. Vì ví dụ yêu cầu `sizeof(intptr_t) <= sizeof(jlong)` và hai kiểu signed, trên ABI 32/64-bit phổ biến giá trị được giữ nguyên.
4. Khi đọc lại, chuyển `jlong` → `intptr_t` → `void *` → `NativeState *`. Chỉ được dereference nếu **đúng pointer gốc, đối tượng còn sống, đúng kiểu và không có data race**.

Điều kiện quan trọng: **chỉ giải mã số do chính hàm encode tạo ra trong cùng tiến trình**, với cùng quy ước ABI, trong lifetime của đối tượng. Một giá trị `long` tự nhập từ Java, lấy từ cơ sở dữ liệu, gửi qua mạng hoặc sao chép từ log không mặc nhiên là con trỏ hợp lệ.

### 3.2. Vì sao không dùng một cast trực tiếp?

Những đoạn sau có rủi ro:

```c
/* Tránh: C long có thể chỉ 32 bit trên Win64. */
jlong bad1 = (long)some_pointer;

/* Tránh: ép pointer vào số 32-bit sẽ làm mất dữ liệu. */
jint bad2 = (jint)(intptr_t)some_pointer;

/* Tránh dùng một số ngẫu nhiên như địa chỉ. */
void *bad3 = (void *)(intptr_t)123456;
```

Mã trên chỉ minh họa **anti-pattern**, không phải một chương trình C độc lập. Khi chuyển pointer qua một kiểu số nguyên không đủ khả năng chứa, dữ liệu có thể bị cắt/biến đổi; giải mã lại thành pointer rồi dereference có thể dẫn tới undefined behavior hoặc crash JVM.

Một đường khác hay gặp là `(jlong)(uintptr_t)ptr`. `uintptr_t` không dấu, còn `jlong` có dấu; trên nền tảng 64-bit, số unsigned có bit cao bằng 1 có thể nằm ngoài miền của `jlong`. Quy tắc chuyển sang kiểu signed khi vượt miền là **implementation-defined** trong C. Do đó, với bài toán round-trip trên môi trường hỗ trợ `intptr_t`, cách đi qua **signed `intptr_t`** như ví dụ rõ ràng hơn.

Không xem `sizeof(intptr_t) <= 8` là điều kiện duy nhất đủ cho mọi kiến trúc: ví dụ chỉ áp dụng khi implementation hỗ trợ chuyển đổi con trỏ đối tượng qua `intptr_t` và bảo đảm round-trip. Với nền tảng có capability pointer, địa chỉ phân vùng riêng hoặc con trỏ rộng hơn 64-bit, phải thiết kế handle khác.

### 3.3. In địa chỉ để debug

C dùng định dạng `%p` với đối số kiểu `void *`:

```c
#include <stdio.h>

void show_address(const void *ptr) {
    printf("native address=%p\n", (const void *)ptr);
}
```

Kết quả phần sau dấu `=` phụ thuộc vào tiến trình, ASLR, thư viện C và nền tảng; **không có stdout địa chỉ cố định**. Dùng `%ld` để in pointer là sai kiểu đối số, có thể gây undefined behavior. Giá trị in từ `%p` nhằm chẩn đoán, không phải khóa chính hay định dạng truyền dữ liệu ổn định.

## 4. JNI nhận tham số nào và ký hiệu như thế nào?

Ví dụ Java:

```java
class NativeBridge {
    private static native long open(int size);
    private static native int read(long handle);
    private static native void close(long handle);
}
```

Tương ứng về **kiểu** (chỉ là minh họa chữ ký, chưa có implementation JNI):

| Java method | Method descriptor trong JVM | Kiểu tương ứng của tham số/kết quả C |
| --- | --- | --- |
| `open(int) : long` | `(I)J` | Nhận `jint`, trả `jlong` |
| `read(long) : int` | `(J)I` | Nhận `jlong`, trả `jint` |
| `close(long) : void` | `(J)V` | Nhận `jlong`, trả `void` |

Với hàm native **static**, chữ ký export ở C thường có các tham số đầu `JNIEnv *env, jclass clazz` rồi mới đến tham số Java. Với hàm native **instance**, tham số thứ hai là `jobject self` thay cho `jclass`. Các macro `JNIEXPORT` và `JNICALL` trong header JNI giúp dùng đúng visibility và calling convention. Tên symbol có thể mã hóa tên package, class, method và chữ ký overload; cách ít nhầm nhất là chạy **`javac -h .` để tạo C header** rồi include file đã tạo.

`jlong` **không mang ownership tự thân**. Cùng kiểu `long` ở Java có thể được dùng để chứa timestamp, counter, file offset, ID sinh ngẫu nhiên, pointer được mã hóa hoặc một token tới bảng registry. Cách đọc giá trị phải do **contract của từng phương thức** xác định.

## 5. Ví dụ chạy được: Java 17 + JNI + C11 với native handle

Ví dụ quản lý một struct nhỏ trên C heap, bọc bằng Java `AutoCloseable`. Thao tác `get()/set()` truy cập cùng một đối tượng native. Java chỉ giữ một `long handle`, không dereference bộ nhớ. C mới có quyền biến handle đã được phát hành thành con trỏ và dùng nó.

**Phạm vi chạy:** Linux x64 thông dụng, JDK 17+, GCC/Clang hỗ trợ C11, `intptr_t` có sẵn. Java code không dùng FFM hay internal `Unsafe`.

### 5.1. File `NativeCounter.java`

```java
public final class NativeCounter implements AutoCloseable {
    static {
        System.loadLibrary("nativecounter");
    }

    // 0 là trạng thái đã đóng/chưa có handle hợp lệ.
    private long handle;

    private static native long nativeCreate(int initial);
    private static native int nativeGet(long handle);
    private static native void nativeSet(long handle, int value);
    private static native void nativeDestroy(long handle);

    public NativeCounter(int initial) {
        long created = nativeCreate(initial);
        if (created == 0L) {
            throw new OutOfMemoryError("Cannot allocate native counter");
        }
        handle = created;
    }

    private void requireOpen() {
        if (handle == 0L) {
            throw new IllegalStateException("NativeCounter is closed");
        }
    }

    public synchronized int get() {
        requireOpen();
        return nativeGet(handle);
    }

    public synchronized void set(int value) {
        requireOpen();
        nativeSet(handle, value);
    }

    @Override
    public synchronized void close() {
        long toRelease = handle;
        handle = 0L; // Không còn gọi native bằng handle này từ wrapper.
        if (toRelease != 0L) {
            nativeDestroy(toRelease);
        }
    }

    public static void main(String[] args) {
        try (NativeCounter counter = new NativeCounter(41)) {
            System.out.println("before=" + counter.get());
            counter.set(42);
            System.out.println("after=" + counter.get());
        }
        System.out.println("closed");
    }
}
```

Ở phía Java:

- `handle` là **một số nguyên signed 64-bit**. Chỉ các native method riêng của lớp hiểu quy ước số này là pointer đã mã hóa.
- `nativeCreate` là **nơi duy nhất cấp phát**. Trong hợp đồng ví dụ, `0L` nghĩa là cấp phát thất bại; đây là quy ước của ví dụ trên ABI đã chọn.
- `get()` và `set()` kiểm tra đối tượng chưa đóng. `synchronized` bảo đảm các lời gọi qua **cùng instance** không xen kẽ với `close()`.
- `close()` xóa trường handle và gọi native destructor đúng một lần; gọi `close()` nhiều lần trên **cùng instance** sẽ không double-free.
- `try-with-resources` bảo đảm `close()` khi ra khỏi block kể cả có Java exception; GC không tự hiểu rằng primitive `long` đang giữ C heap allocation.

### 5.2. Tạo JNI header từ Java

Chạy trong thư mục chỉ chứa mã ví dụ:

```bash
javac -h . NativeCounter.java
```

Lệnh này tạo `NativeCounter.class` và `NativeCounter.h`. Header sinh ra có các khai báo kiểu sau (đây là **bản minh họa chữ ký**; hãy include đúng header do `javac -h` tạo, không tự ghi đè):

```c
JNIEXPORT jlong JNICALL Java_NativeCounter_nativeCreate
    (JNIEnv *, jclass, jint);

JNIEXPORT jint JNICALL Java_NativeCounter_nativeGet
    (JNIEnv *, jclass, jlong);

JNIEXPORT void JNICALL Java_NativeCounter_nativeSet
    (JNIEnv *, jclass, jlong, jint);

JNIEXPORT void JNICALL Java_NativeCounter_nativeDestroy
    (JNIEnv *, jclass, jlong);
```

Chú ý `jlong` là **kiểu giá trị** trong các prototype này. Các chữ ký không chứa `void *` vì Java method không khai báo tham số kiểu pointer.

### 5.3. File `NativeCounter.c`

```c
#include "NativeCounter.h"

#include <stdint.h>
#include <stdlib.h>

#ifndef INTPTR_MAX
#  error "JNI handle example requires intptr_t"
#endif

_Static_assert(sizeof(intptr_t) <= sizeof(jlong),
               "Native pointer does not fit in jlong");

struct NativeState {
    jint value;
};

static jlong encode_state(struct NativeState *state) {
    return (jlong)(intptr_t)(void *)state;
}

static struct NativeState *decode_state(jlong handle) {
    return (struct NativeState *)(void *)(intptr_t)handle;
}

/*
 * Handles only the closed/null sentinel.
 * A forged nonzero handle CANNOT be validated by this test.
 */
static struct NativeState *require_state(JNIEnv *env, jlong handle) {
    if (handle == 0) {
        jclass exceptionClass =
            (*env)->FindClass(env, "java/lang/IllegalStateException");
        if (exceptionClass != NULL) {
            (*env)->ThrowNew(
                env, exceptionClass, "Native handle is closed");
        }
        return NULL;
    }
    return decode_state(handle);
}

JNIEXPORT jlong JNICALL
Java_NativeCounter_nativeCreate(JNIEnv *env,
                                jclass clazz,
                                jint initial) {
    (void)env;
    (void)clazz;

    struct NativeState *state = malloc(sizeof *state);
    if (state == NULL) {
        return (jlong)0;
    }

    state->value = initial;
    return encode_state(state);
}

JNIEXPORT jint JNICALL
Java_NativeCounter_nativeGet(JNIEnv *env,
                             jclass clazz,
                             jlong handle) {
    (void)clazz;
    struct NativeState *state = require_state(env, handle);
    if (state == NULL) {
        return (jint)0; // JNI exception is pending.
    }
    return state->value;
}

JNIEXPORT void JNICALL
Java_NativeCounter_nativeSet(JNIEnv *env,
                             jclass clazz,
                             jlong handle,
                             jint value) {
    (void)clazz;
    struct NativeState *state = require_state(env, handle);
    if (state == NULL) {
        return;
    }
    state->value = value;
}

JNIEXPORT void JNICALL
Java_NativeCounter_nativeDestroy(JNIEnv *env,
                                 jclass clazz,
                                 jlong handle) {
    (void)env;
    (void)clazz;

    if (handle != 0) {
        struct NativeState *state = decode_state(handle);
        free(state);
    }
}
```

Giải thích ownership của C code:

1. `malloc()` tạo `struct NativeState` trong native heap; nó **không** nằm trên Java heap và không phải một JNI `jobject`.
2. `encode_state()` chuyển giá trị pointer qua `intptr_t` rồi sang `jlong` để Java lưu tạm. **Không cấp phát thêm bộ nhớ** ở bước encode.
3. `get/set` giải mã handle và thao tác trên struct **đã được cấp phát và còn sống**. Kiểm tra `handle == 0` chỉ nhận biết sentinel, **không thể xác minh một handle khác 0 thật sự trỏ tới vùng nhớ hợp lệ**.
4. `nativeDestroy()` gọi `free()` ở đúng phía C đã `malloc()`. Sau khi giải phóng, mọi bản sao handle cũ đều là **dangling handle**, dù giá trị số vẫn giữ nguyên.
5. Native code không giữ con trỏ qua lời gọi async hay trả nó cho một đối tượng wrapper thứ hai. Điều kiện đó cùng `synchronized` ở Java khiến ví dụ có lifetime rõ ràng khi các thao tác chỉ đi qua wrapper đã định nghĩa.

Trong C, `jint` là signed 32-bit theo JNI. Lưu trực tiếp giá trị `int` của Java vào trường `jint` không liên quan đến việc ánh xạ pointer. `JNIEnv *` là JNI interface pointer dùng trong thread gọi native method; không lưu `env` để sử dụng từ thread khác.

### 5.4. Build shared library và chạy

Đặt `NativeCounter.java` và `NativeCounter.c` trong cùng thư mục. Trên Linux, thiết lập `JAVA_HOME` trỏ tới thư mục JDK thực sự đang dùng, sau đó:

```bash
javac -h . NativeCounter.java
cc -std=c11 -Wall -Wextra -Wpedantic -fPIC \
  -I"$JAVA_HOME/include" -I"$JAVA_HOME/include/linux" \
  -shared NativeCounter.c -o libnativecounter.so
java -Djava.library.path=. NativeCounter
```

**Stdout chính xác** trên đường thành công:

```text
before=41
after=42
closed
```

Nếu Java báo `UnsatisfiedLinkError`, kiểm tra tên thư viện, đường dẫn native, kiến trúc JDK (32/64-bit), header JNI và tên symbol. `System.loadLibrary("nativecounter")` tương ứng với `libnativecounter.so` trên Linux, `nativecounter.dll` trên Windows và tên thư viện nền tảng tương ứng trên macOS. Ví dụ build command là cho **Linux**, không thể sao chép nguyên phần include `linux` và cờ `-fPIC` sang MSVC/Windows.

Ở các bản JDK có chính sách hạn chế native access, việc load hoặc gọi JNI có thể cần cấu hình cho phép native access phù hợp, ví dụ `--enable-native-access=ALL-UNNAMED` đối với ứng dụng classpath; xem tài liệu phiên bản JDK đang chạy. Trên JDK 17 thông thường, lệnh chạy bên trên đủ để minh họa JNI cơ bản.

## 6. Nhìn rõ dòng dữ liệu và lifetime

```text
Java NativeCounter(41)
    |
    | nativeCreate(41)        Java int -> JNI jint
    v
C malloc(sizeof NativeState)
    |
    | NativeState *p
    | encode: p -> void* -> intptr_t -> jlong
    v
Java handle : long           (chỉ giữ số, không giữ allocation sống)
    |
    | nativeGet(handle)       Java long -> JNI jlong
    v
C decode: jlong -> intptr_t -> void* -> NativeState*
    |
    | dereference khi đối tượng còn sống
    v
C state->value : jint = 41
    |
    v
Java int = 41
    |
    | close() -> nativeDestroy(handle)
    v
C free(p)
    |
    v
Java handle = 0              (handle cũ không còn hợp lệ)
```

Hai phân biệt quan trọng:

- **Giá trị pointer ≠ vùng nhớ:** copy pointer hoặc encode thành `jlong` không copy vùng dữ liệu được trỏ tới và không tạo ownership thứ hai.
- **Giữ số ≠ giữ đối tượng sống:** Java có thể giữ `handle` mãi, nhưng nếu C đã `free(p)` thì việc decode không làm vùng nhớ xuất hiện trở lại. Con trỏ có thể trùng địa chỉ với allocation mới (bẫy ABA).

Vì Java `long` là số signed, **chỉ so `handle != 0L`** khi hợp đồng dùng 0 làm sentinel; không kiểm tra `handle > 0L`. Một địa chỉ mã hóa thành giá trị signed âm vẫn có thể là handle đã phát hành hợp lệ trên nền tảng cho phép mã hóa đó.

Ví dụ còn có giả định: các native method chỉ thực thi công việc đồng bộ và hoàn tất trước khi trả về Java. Nếu thư viện C tự tạo worker thread, queue một pointer rồi mới xử lý, Java `close()` ngay sau native call có thể free sớm. Khi đó phải thêm reference counting, cơ chế đồng bộ hoặc quy tắc ownership transfer theo đúng contract của thư viện.

## 7. Khi nào pointer-as-`jlong` không đủ an toàn?

Wrapper mẫu làm rõ kiến thức chuyển đổi nhưng **không xác thực được handle tùy ý**. Giả sử một native entry point công khai nhận một `long` từ JSON hoặc Java code không đáng tin cậy:

```java
// Minh họa nguy hiểm: số do caller tự chọn, không được native cấp.
long forgedHandle = 0x1234L;
```

Nếu C coi nó là `NativeState *` và dereference, kết quả có thể là segmentation fault hoặc hỏng bộ nhớ. `handle != 0` hoàn toàn không bảo vệ trước giá trị giả, stale handle hay pointer bị đổi kiểu. `synchronized` chỉ ngăn race giữa các method trên **cùng wrapper**, không bảo vệ trước handle bị sao chép sang đối tượng hay thread khác.

Với API cần nhận handle từ nhiều client/module hoặc có khả năng misuse, dùng **opaque ID registry**:

1. Native code tạo resource và lưu pointer thực trong một bảng dưới mutex (hoặc cấu trúc an toàn đồng thời).
2. Trả về một số ID/token có định dạng do thư viện sở hữu, có thể gồm index + generation để chống tái dùng ID cũ.
3. Mỗi operation tra bảng, kiểm tra ID còn hiệu lực, loại resource, quyền sở hữu và trạng thái đóng **trước** khi chạm đến pointer.
4. Destructor xóa registry entry, release resource đúng một lần; concurrent operation phải giữ lease/refcount hoặc khóa phù hợp để pointer không bị free khi đang dùng.
5. Không xem token dự đoán được là bằng chứng phân quyền: với dữ liệu nhạy cảm còn cần kiểm soát truy cập độc lập.

Khi đó, `jlong` là **ID**, hoàn toàn không cần cast thành C pointer trong JNI entry point. Registry có thêm chi phí và thiết kế đồng bộ, đổi lại cho phép phát hiện invalid/stale handle và quản lý vòng đời tập trung. Tùy bài toán, có thể dùng object wrapper Java, `ByteBuffer` trực tiếp hoặc FFM `MemorySegment` thay vì công khai integer handle.

### 7.1. Lựa chọn API theo nhu cầu

| Nhu cầu | Thiết kế phù hợp | Lưu ý |
| --- | --- | --- |
| Native object riêng, wrapper kiểm soát lifetime, nội bộ một tiến trình | `jlong` chứa pointer đã mã hóa + `AutoCloseable` | Chỉ nhận handle do thư viện cấp; release đúng một lần |
| Caller có thể truyền ID giả hoặc stale, nhiều thread/owner | `jlong` chứa **opaque ID**, lookup qua registry | Validate + generation + đồng bộ trước dereference |
| Làm việc với buffer byte có thể đọc/ghi từ Java | JNI direct `ByteBuffer` hoặc copy mảng | Đừng để buffer truy cập memory đã được C giải phóng |
| Cần lifetime và bounds native memory được mô hình hóa trong Java hiện đại | FFM `MemorySegment` / `Arena` (JDK 22+) | Theo scope và API của FFM, vẫn phải quản lý allocation từ C đúng owner |
| Chỉ cần số nguyên 64-bit từ C | `jlong` như **số**, không chuyển sang pointer | Tránh “pointer hóa” một giá trị dữ liệu |

Với `NewDirectByteBuffer(env, nativeAddress, capacity)`, JNI có thể tạo Java direct buffer nhìn vào địa chỉ được cung cấp. Lời gọi này **không tự chuyển ownership allocation của C cho JVM**; phía thư viện phải bảo đảm vùng nhớ còn sống cho tới khi buffer không còn được truy cập. `GetDirectBufferAddress` có thể trả về con trỏ tới native memory của direct buffer (hoặc `NULL` theo tình huống được JNI quy định). Đừng giữ pointer khi lifetime của buffer hoặc native allocation chưa được xác lập.

FFM `MemorySegment` không đồng nghĩa với “mọi địa chỉ đều an toàn”; con trỏ native trần vẫn cần contract về kích thước, quyền truy cập, alignment và lifetime. Một `long` trả về từ `MemorySegment.address()` (khi API hỗ trợ) cũng chỉ là địa chỉ ở mức số, không tự kéo theo kiểm tra bounds của segment.

## 8. `jobject`, `jmethodID` và con trỏ do JNI trả về khác nhau ra sao?

Tên typedef trong `jni.h` dễ tạo nhầm lẫn khi đọc code C. Cần phân loại:

**1. `jobject`, `jclass`, `jstring`, `jarray`.** Đây là JNI reference tới đối tượng trên Java heap; đối tượng do JVM quản lý và có thể bị GC di chuyển. Không lấy giá trị numeric của JNI reference làm địa chỉ của Java object, không lưu nó thành `jlong` để dùng sau. Local reference có lifetime gắn với lời gọi/thread; muốn giữ Java object qua nhiều lời gọi thì dùng `NewGlobalRef`, rồi `DeleteGlobalRef` đúng lúc. Global reference là cơ chế giữ **Java object** sống, không phải `malloc` của native C.

**2. `jfieldID` và `jmethodID`.** Đây là ID opaque dùng để truy cập field/method qua JNI. Chúng không phải Java object references thông thường; lifetime liên quan class chứa field/method. Không dùng làm pointer tới struct của ứng dụng, và không serialize thành long tùy ý.

**3. `GetByteArrayElements`, `GetStringUTFChars`, `GetPrimitiveArrayCritical`.** JNI có thể cho native code pointer tới nội dung Java object hoặc vùng copy. Caller phải tuân thủ cặp hàm `Release...` tương ứng. Pointer này không mặc nhiên thuộc quyền `free()` của C và không thể giữ lâu tùy ý. Với critical API còn có hạn chế riêng về các thao tác JNI có thể làm trong critical region.

**4. Con trỏ C tự tạo từ `malloc()`.** Đây là native allocation thực sự; JVM không biết nó chỉ vì Java lưu địa chỉ dưới dạng `jlong`. Ownership phải do contract Java/C quản lý riêng.

**5. `JNIEnv *`.** Đây là con trỏ interface của JNI cho **thread đang gọi**. Không lưu và dùng lại cùng `JNIEnv *` từ một thread native khác; thread native riêng cần attach vào JVM theo quy tắc JNI và lấy interface của chính thread đó.

## 9. Những lỗi thường gặp và cách sửa

| Mã/mô hình có vấn đề | Vì sao sai | Cách sửa |
| --- | --- | --- |
| `jlong h = (long)ptr;` | C `long` có thể chỉ 32 bit trên Win64 | Dùng `intptr_t` rồi `jlong` với check ABI |
| `jint h = (jint)(intptr_t)ptr;` | 32 bit có thể cắt địa chỉ 64 bit | Không dùng `jint` chứa địa chỉ 64 bit |
| `void *p = (void *)(intptr_t)userLong;` với số bất kỳ | Không có bảo đảm pointer hợp lệ | Chỉ decode handle đã phát hành hoặc dùng registry |
| `if (h > 0) ...` | Pointer mã hóa có thể có `jlong` âm | Dùng sentinel chính xác theo hợp đồng |
| `free(pointer)` sau khi đã free một lần | Double free, heap corruption | Một owner; `close()` idempotent; ownership rõ |
| Dùng `h` sau `close()` | Use-after-free; `h` vẫn là số hợp lệ | Invalidate handle và bảo vệ mọi operation |
| Lưu `jobject` cast thành `jlong` | GC reference không phải pointer C ổn định | `NewGlobalRef/DeleteGlobalRef` nếu cần giữ object |
| Lưu `GetStringUTFChars` pointer rồi không release | Rò rỉ/pin/copy giữ quá lâu | Dùng đúng cặp `ReleaseStringUTFChars` |
| Dùng `sizeof(void*) == 8` để khẳng định mọi ABI giống nhau | Không xét alignment, pointer representation, ABI đặc biệt | Kiểm tra đúng platform và thiết kế contract |
| Ghi pointer handle xuống database và dùng lại sau restart | Không gian địa chỉ của tiến trình thay đổi; ASLR, lifetime khác | Dùng ID bền vững, không dùng địa chỉ runtime |
| Hai wrapper cùng sở hữu một pointer và cùng đóng | Double free | Single ownership hoặc reference counting/registry |
| Đóng native resource khi native thread vẫn dùng | Data race/use-after-free | Lease/lock/refcount và đồng bộ rõ |
| Nhầm `Java long` với C `long` trong prototype | Lệch kích thước trên LLP64 | C native method dùng `jlong` từ `jni.h` |
| Tự viết JNI symbol trong code đã đổi package/overload | JVM không resolve được function | Chạy lại `javac -h`; include header sinh ra |

Về mặt bảo mật, địa chỉ bộ nhớ không phải credential hay capability chống giả mạo. Log địa chỉ tùy tiện có thể làm lộ thông tin bố cục không gian địa chỉ (ASLR). Trong API công khai, chỉ phát hành opaque token có quản lý, và kiểm soát truy cập khi cần.

## 10. Kiểm thử boundary Java/C

Với ví dụ `NativeCounter`, nên kiểm tra theo những nhóm sau:

1. **Đường thành công:** create `41` → get `41` → set `42` → get `42` → close; đúng stdout đã nêu.
2. **Sau khi đóng:** `get()/set()` phải ném `IllegalStateException` ở Java trước khi gọi native; `close()` lần hai là no-op.
3. **Thread cùng wrapper:** nhiều Java thread gọi `get/set/close` phải được serialize qua `synchronized`; nếu ứng dụng cho native code giữ pointer qua lời gọi thì cần đồng bộ bổ sung.
4. **Allocation failure:** kích hoạt `malloc` fail bằng fault injection hoặc allocator giả để xác nhận `nativeCreate` trả `0` và constructor Java ném `OutOfMemoryError`. Không thử bằng cách cấp phát kích thước vô hạn.
5. **32-bit/64-bit:** build trên các ABI thực sự hỗ trợ; kiểm tra `sizeof(jlong)`, `sizeof(intptr_t)`, `sizeof(void*)` trong C, và thử encode → decode trên đối tượng sống.
6. **Quản lý heap:** chạy AddressSanitizer/LeakSanitizer khi toolchain cho phép; kiểm tra không có leak, double free và use-after-free trên các đường thoát.
7. **Invalid handle:** không cố dereference `12345L` chỉ để “test”; với registry, có thể kiểm tra invalid/stale ID mà không chạm tới pointer không hợp lệ.
8. **Tương thích thư viện:** kiểm tra `UnsatisfiedLinkError`, tên native export, đúng JDK headers, cùng architecture và compiler ABI giữa JVM/native library.

Một kiểm tra C hữu ích cho CI trên nền tảng mục tiêu là:

```c
#include <jni.h>
#include <stdint.h>
#include <stdio.h>

int main(void) {
#ifdef INTPTR_MAX
    printf("jlong_bytes=%zu\n", sizeof(jlong));
    printf("void_ptr_bytes=%zu\n", sizeof(void *));
    printf("intptr_bytes=%zu\n", sizeof(intptr_t));
#else
    puts("intptr_t unavailable");
#endif
    return 0;
}
```

Đây là chương trình **độc lập**, cần include JNI headers bằng cờ `-I` tương tự lệnh build native ở trên. Trên Linux x64 thông dụng, stdout dự kiến:

```text
jlong_bytes=8
void_ptr_bytes=8
intptr_bytes=8
```

Chỉ đo kích thước không kiểm tra toàn bộ contract. Việc pointer còn sống, thuộc allocation nào và có thể giải phóng ra sao vẫn phải được kiểm chứng qua thiết kế/lifetime.

## 11. Quy tắc ghi nhớ khi thiết kế JNI

- **Kiểu số:** `Java long` ↔ `JNI jlong` ↔ signed 64 bit. Nó chỉ là dữ liệu.
- **Kiểu địa chỉ:** `void *`/`T *` mô tả con trỏ C, có ABI và lifetime cụ thể. Không suy ra pointer từ tên kiểu `long`.
- **Chuyển đổi có điều kiện:** `pointer → intptr_t → jlong → intptr_t → pointer` cho object pointer khi implementation hỗ trợ và giá trị còn trong cùng lifetime/tiến trình. Không tự suy rộng cho function pointer hoặc pointer >64 bit.
- **Không gian địa chỉ và GC:** C allocation và Java object là hai cơ chế quản lý khác nhau. `jobject` là opaque JNI reference, không phải địa chỉ trực tiếp của Java object.
- **Ownership:** số `jlong` không giữ C allocation sống; caller phải đóng đúng resource, bằng đúng destructor và đúng thời điểm.
- **API công khai:** nếu phải xác thực, đóng và chia sẻ native resource giữa nhiều bên, dùng opaque ID registry thay cho con trỏ thô.

Tham khảo: [JNI Types and Data Structures (Java SE 17)](https://docs.oracle.com/en/java/javase/17/docs/specs/jni/types.html), [JNI Design Overview, native signatures và lifetime references](https://docs.oracle.com/en/java/javase/17/docs/specs/jni/design.html), [C pointer conversions](https://en.cppreference.com/w/c/language/conversion), [`javac -h` native headers](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javac.html).