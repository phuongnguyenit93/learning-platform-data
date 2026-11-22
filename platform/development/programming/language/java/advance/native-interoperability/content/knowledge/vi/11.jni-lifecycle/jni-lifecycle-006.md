# Giải phóng tài nguyên native bằng close tường minh và giới hạn của Cleaner hoặc GC

## 1. Vấn đề vòng đời: Java object khác với tài nguyên native

Ứng dụng Java sử dụng JNI có thể giữ **tài nguyên nằm ngoài Java heap**: vùng nhớ do `malloc` cấp, file descriptor, socket native, thư viện xử lý ảnh, buffer C/C++, đối tượng GPU, database handle hoặc con trỏ tới cấu trúc của thư viện bên thứ ba. Thường một Java object đóng vai trò *wrapper* và lưu một giá trị `long` biểu diễn native handle:

```text
Java heap                            Native memory / OS resource
-----------------                    ----------------------------
NativeBuffer instance                Buffer *p = malloc(...)
  ├─ Java fields                          └─ value = 42
  └─ long address -------------> p
```

**GC biết về khả năng thu gom Java object**, nhưng không tự biết cách gọi `free(p)`, đóng socket, huỷ C++ object hoặc giải phóng GPU handle tương ứng. Tài nguyên native có thể tiếp tục tồn tại **sau khi Java object không còn được sử dụng** nếu không có mã giải phóng thích hợp.

Ba cách quản lý có ý nghĩa khác nhau:

1. **`close()` tường minh:** ứng dụng xác định thời điểm kết thúc sử dụng, gọi API giải phóng trong một luồng điều khiển đã biết.
2. **`Cleaner`:** một hành động dọn dẹp có thể chạy khi Java object trở thành *phantom reachable*, thường trên một thread do Cleaner quản lý; phù hợp làm **lưới an toàn cuối cùng** nếu caller quên `close()`, **không phải hạn chót giải phóng**.
3. **GC:** thu gom vùng nhớ Java heap theo chính sách JVM; không có cam kết sẽ chạy ở thời điểm bạn muốn, không thay thế giao thức đóng tài nguyên native.

**Nguyên tắc chính:** tài nguyên cần được trả đúng lúc phải có **ownership rõ ràng và `close()` tường minh**, thường dùng `AutoCloseable` + `try-with-resources`. `Cleaner` chỉ hỗ trợ xử lý trường hợp bỏ sót; đừng thiết kế tính đúng đắn của chương trình phụ thuộc vào việc GC có chạy kịp thời.

## 2. AutoCloseable và try-with-resources: giải phóng dự đoán được

Interface `java.lang.AutoCloseable` khai báo `close()`. Một wrapper JNI có thể implements `AutoCloseable` để callers dùng:

```java
try (NativeBuffer buffer = new NativeBuffer(42)) {
    int value = buffer.read();
    System.out.println(value);
} // Java gọi buffer.close() khi rời scope này.
```

Đây là **đoạn sử dụng**; `NativeBuffer` được cài đặt đầy đủ trong mục 5.

Lợi ích:

- `close()` được gọi khi thoát khối, bao gồm cả khi có exception trong thân `try`.
- Thời điểm đóng gắn với **điểm kết thúc scope**, không phụ thuộc GC, memory pressure hay thread Cleaner.
- Trách nhiệm sở hữu được diễn đạt rõ ràng: ai mở thì người đó đóng, trừ khi API có cơ chế chuyển ownership minh bạch.
- Nếu thân `try` và `close` cùng ném exception, Java giữ exception của thân `try` là lỗi chính và có thể lưu exception khi close vào danh sách **suppressed exceptions** (`Throwable.getSuppressed()`).

Ví dụ:

```text
mở tài nguyên
   |
   v
try-with-resources
   |
   +--> sử dụng tài nguyên
   |       |
   |       +--> thành công ----------+
   |       |                        |
   |       +--> ném exception ------+
   |                                |
   v                                v
close() được gọi trước khi rời scope
   |
   +--> native release (free/close/cancel)
   |
   v
không được sử dụng tài nguyên đã đóng
```

`try-with-resources` bảo đảm **lời gọi `close()` được thực hiện theo quy tắc ngôn ngữ Java**; nó **không bảo đảm** driver, OS, ổ đĩa hay thư viện C luôn thực hiện thao tác release thành công. Nếu native API có thể báo lỗi khi close, phải thiết kế cách xử lý, propagate hoặc ghi nhận lỗi đó. Không đánh đồng “có lời gọi close” với “mọi I/O đã flush thành công”.

### Hợp đồng close tốt cho JNI wrapper

Một wrapper có native handle thường cần:

- **Đóng đúng một lần** ở tầng native; gọi `close` lặp lại không gây `double free`.
- **Fail fast** với `IllegalStateException` khi đọc/ghi sau close, thay vì đưa con trỏ đã giải phóng xuống C/C++.
- **Đồng bộ close với các operation đang chạy**, tránh luồng A còn dùng handle trong khi luồng B đã giải phóng.
- **Giải phóng khi constructor thất bại một phần**, không để lộ native allocation vừa tạo nhưng chưa được đăng ký dọn dẹp.
- **Có chính sách rõ ràng với lỗi khi đóng**; nếu `close` có thể thất bại, không âm thầm bỏ qua và không giao trách nhiệm báo lỗi cho Cleaner.
- **Không dùng GC làm điều kiện hoàn tất giao dịch**: trước khi trả kết quả hay kết thúc request, những resource cần đóng phải được close theo luồng điều khiển xác định.

## 3. Vì sao chỉ dựa vào GC là không đủ?

### 3.1. Java heap và native memory không cùng cơ chế sở hữu

GC của JVM xử lý reachability của **Java objects**. Một object nhỏ chỉ giữ `long address` có thể tương ứng với bộ nhớ native rất lớn. Heap pressure có thể vẫn thấp ngay cả khi native heap hoặc GPU memory sắp cạn. Khi JVM chưa thấy cần GC, tài nguyên native chưa được giải phóng bằng cơ chế phụ thuộc GC.

`System.gc()` chỉ yêu cầu hoặc gợi ý GC, **không phải một API “giải phóng native resources ngay lập tức”**. JVM có thể không thực hiện GC ngay, có thể chỉ thu gom một phần đối tượng, và không hứa Cleaner sẽ hoàn thành trước khi `System.gc()` trả về.

### 3.2. Đối tượng “không còn được sử dụng trong source” không đồng nghĩa lập tức được thu gom

JIT có thể tối ưu phạm vi sống của local variables; GC phụ thuộc các strong roots còn tồn tại, loại collector và thời điểm thu gom. Tài nguyên native không nên có timeout hoặc hạn mức dựa trên điều kiện kiểu:

```java
buffer = null;
System.gc(); // Không được xem là thay thế buffer.close().
```

Trong một ứng dụng server chạy lâu, hàng nghìn native allocations có thể làm cạn file descriptors hoặc off-heap memory trước khi Cleaner kịp chạy, dù Java heap vẫn trông ổn.

### 3.3. JVM shutdown không có cam kết sẽ chạy tất cả Cleaner actions

Cleaner API ghi rõ hành vi khi `System.exit` mang tính implementation-specific; không bảo đảm cleaning actions được gọi. Thread mặc định của Cleaner là **daemon**, và hệ thống có thể kết thúc trước khi fallback cleanup hoàn tất. Sự cố, kill process, crash, mất điện hoặc native abort càng không cho phép trông chờ cleanup theo Java.

Ngay cả `finally` và `try-with-resources` cũng không thể chạy trong mọi trường hợp process chết đột ngột; nhưng chúng cho phép giải phóng **dự đoán được trên những đường điều khiển Java bình thường và exception propagation thông thường**, tốt hơn hẳn việc đợi GC.

## 4. Cleaner thực sự hoạt động thế nào?

`java.lang.ref.Cleaner` xuất hiện từ Java 9, có trong Java 17+. Cleaner theo dõi một Java object và một hành động `Runnable` được đăng ký. Khi object trở thành **phantom reachable** và JVM xử lý tham chiếu tương ứng, Cleaner có thể chạy action trên Cleaner thread.

Đăng ký:

```java
private static final Cleaner CLEANER = Cleaner.create();
Cleaner.Cleanable cleanable = CLEANER.register(owner, cleanupState);
```

- `owner` là **Java object được theo dõi reachability**.
- `cleanupState` là `Runnable` có thông tin đủ để giải phóng native resource.
- `cleanable.clean()` bỏ đăng ký và kích hoạt cleaning action **tường minh**, tối đa một lần.
- Nếu không gọi `clean()` và `owner` trở thành phantom reachable, Cleaner có thể chạy action **không đồng bộ** sau đó.
- Cleaning action chạy **tối đa một lần** theo hợp đồng `Cleanable`, nhưng thời điểm chạy tự động **không được đảm bảo**.
- Exceptions do cleaning action ném trên Cleaner thread bị bỏ qua theo Cleaner API; do đó nó **không phải kênh báo lỗi quản trị tài nguyên đáng tin cậy**.

### Cleaner action tuyệt đối không giữ strong reference tới owner

Một lỗi phổ biến:

```java
// SAI: lambda này tham chiếu this, có thể giữ owner còn reachable.
cleanable = CLEANER.register(this, () -> nativeFree(this.address));
```

Cleaner phải giữ `Runnable` để có thể chạy nó. Nếu `Runnable` giữ lại `this`, ta tạo đường tham chiếu mạnh ngược về object đang theo dõi:

```text
Cleaner -> cleanup action -> owner
                            ^
             owner không thể phantom reachable
```

Hệ quả: action có thể **không bao giờ** được chạy tự động; đúng lúc quên close thì fallback cũng mất tác dụng.

**Mẫu đúng:** tạo `static nested class State implements Runnable`, chỉ chứa dữ liệu độc lập như native address, file descriptor hoặc trạng thái giải phóng. **State không chứa `NativeBuffer` hoặc bất kỳ callback/lambda nào giữ owner**. Khi constructor đăng ký, `Cleaner.register(this, state)` có thể theo dõi owner mà action không làm owner sống lại.

### Không tự nới hạn mức bằng Cleaner

Cleaner không đảm bảo deadline, thứ tự giữa nhiều resources, thứ tự shutdown hay thread affinity. Một native resource buộc phải được giải phóng đúng thread (ví dụ một số GPU/context/GUI handles, thiết bị ngoại vi hoặc thư viện C có trạng thái thread-local) **không thể mặc nhiên được giải phóng trực tiếp từ Cleaner thread**. Cần thiết kế close đúng thread và nếu có fallback, cơ chế giao việc an toàn cho owner thread — nhưng cơ chế giao việc đó cũng không đảm bảo hoàn thành lúc shutdown.

## 5. Ví dụ JNI hoàn chỉnh: close xác định, Cleaner chỉ dự phòng

Ta xây dựng `NativeBuffer`, wrapper Java cho một allocation C chứa một `jint`. Mã minh họa các khái niệm thiết yếu:

1. `nativeAlloc(int)` dùng `malloc`, trả handle về Java dưới dạng `long`.
2. `read()` dùng native pointer khi tài nguyên còn mở.
3. `close()` gọi `Cleaner.Cleanable.clean()` để giải phóng **ngay trong đường gọi close**, không chờ GC.
4. `State.run()` lấy handle và đặt nó về 0 bằng `AtomicLong.getAndSet(0)`, tránh native `free` hai lần nếu close và Cleaner action cạnh tranh.
5. `read()` và `close()` đều `synchronized`, khiến các lời gọi qua cùng wrapper không chồng lấn nhau.
6. `Reference.reachabilityFence(this)` giữ wrapper mạnh tới sau native operation để tránh premature cleanup do tối ưu hóa JIT.
7. Cleaner action nằm trong **static nested class**, không giữ strong reference đến wrapper.

Ví dụ dành cho JDK **17+** và C compiler trên Linux/macOS/Windows. Nó mô phỏng native memory thực tế; không cần driver, GUI hay GPU.

### 5.1. File `src/example/jni/NativeBuffer.java`

```java
package example.jni;

import java.lang.ref.Cleaner;
import java.lang.ref.Reference;
import java.util.concurrent.atomic.AtomicLong;

public final class NativeBuffer implements AutoCloseable {
    private static final Cleaner CLEANER = Cleaner.create();

    static {
        System.loadLibrary("nativebuffer");
    }

    private final State state;
    private final Cleaner.Cleanable cleanable;

    // Không được tham chiếu tới NativeBuffer.this.
    private static final class State implements Runnable {
        private final AtomicLong address = new AtomicLong();

        void setAddress(long value) {
            address.set(value);
        }

        long address() {
            return address.get();
        }

        @Override
        public void run() {
            long ptr = address.getAndSet(0L);
            if (ptr != 0L) {
                nativeFree(ptr);
            }
        }
    }

    public NativeBuffer(int value) {
        State fresh = new State();  // Tạo State trước khi cấp phát native.
        long ptr = nativeAlloc(value);

        if (ptr == 0L) {
            throw new IllegalStateException("nativeAlloc returned null");
        }
        fresh.setAddress(ptr);

        Cleaner.Cleanable registration;
        try {
            registration = CLEANER.register(this, fresh);
        } catch (RuntimeException | Error failure) {
            fresh.run();  // Nếu đăng ký thất bại, giải phóng ngay.
            throw failure;
        }

        this.state = fresh;
        this.cleanable = registration;
    }

    public synchronized int read() {
        long ptr = state.address();
        if (ptr == 0L) {
            throw new IllegalStateException("Resource is closed");
        }

        try {
            return nativeRead(ptr);
        } finally {
            Reference.reachabilityFence(this);
        }
    }

    public synchronized boolean isClosed() {
        return state.address() == 0L;
    }

    @Override
    public synchronized void close() {
        cleanable.clean();
    }

    private static native long nativeAlloc(int value);
    private static native int nativeRead(long ptr);
    private static native void nativeFree(long ptr);

    public static void main(String[] args) {
        NativeBuffer buffer = new NativeBuffer(42);

        try (buffer) {  // Java 9+: biến buffer effectively final.
            System.out.println("Value: " + buffer.read());
        }

        buffer.close(); // Đóng lần hai: không gọi free lần nữa.
        System.out.println("Closed: " + buffer.isClosed());

        try {
            buffer.read();
        } catch (IllegalStateException expected) {
            System.out.println("Read after close: blocked");
        }
    }
}
```

**Tại sao constructor tạo `State` trước `nativeAlloc`?** Nếu cấp phát Java object phụ trợ thất bại **sau** khi đã gọi `malloc`, có nguy cơ mất địa chỉ native mà chưa có cleanup owner. Mẫu tạo `State` trước native allocation, sau đó cập nhật address và đăng ký Cleaner. Nếu `CLEANER.register` thất bại, catch giải phóng handle ngay. Mã C ở dưới có đường báo lỗi cho `malloc` thất bại.

**Tại sao `close()` gọi `cleanable.clean()` chứ không gọi `nativeFree` trực tiếp?** Vì cùng một cleaning action được dùng cho **đóng tường minh** và fallback, cơ chế `Cleanable` bảo đảm action chạy tối đa một lần. `State.run()` dùng thêm `getAndSet(0)` để chặn double-free tại tầng state, và `isClosed()` có thể kiểm tra trạng thái.

Trong thực tế, nếu hàm native release có thể thất bại và cần báo lỗi rõ ràng, nên thiết kế close riêng để xử lý báo lỗi; **không** xem Cleaner action vốn được phép chạy bất đồng bộ và bỏ qua exception là cơ chế error-handling chính.

### 5.2. Dùng javac -h để tạo header JNI

Từ thư mục gốc dự án, trên Linux/macOS shell:

```bash
mkdir -p build/classes build/include build/native

javac -h build/include \
    -d build/classes \
    src/example/jni/NativeBuffer.java
```

Kết quả có class file `build/classes/example/jni/NativeBuffer.class` và JNI header `build/include/example_jni_NativeBuffer.h`.

Phần prototype được `javac -h` tạo (bỏ comment/guard):

```c
#include <jni.h>

JNIEXPORT jlong JNICALL Java_example_jni_NativeBuffer_nativeAlloc
  (JNIEnv *, jclass, jint);

JNIEXPORT jint JNICALL Java_example_jni_NativeBuffer_nativeRead
  (JNIEnv *, jclass, jlong);

JNIEXPORT void JNICALL Java_example_jni_NativeBuffer_nativeFree
  (JNIEnv *, jclass, jlong);
```

Đã xác minh riêng mã Java với `javac -h` trên JDK 24: class biên dịch thành công và header có chính xác ba prototype này. `JNICALL` và `JNIEXPORT` phải được giữ trong C function definitions theo JNI ABI.

### 5.3. File `NativeBuffer.c`

```c
#include <jni.h>
#include <stdint.h>
#include <stdlib.h>
#include "example_jni_NativeBuffer.h"

typedef struct {
    jint value;
} Buffer;

JNIEXPORT jlong JNICALL Java_example_jni_NativeBuffer_nativeAlloc(
        JNIEnv *env, jclass cls, jint value) {
    (void)cls;

    Buffer *p = (Buffer *)malloc(sizeof(*p));
    if (p == NULL) {
        jclass oom = (*env)->FindClass(env, "java/lang/OutOfMemoryError");
        if (oom != NULL) {
            (*env)->ThrowNew(env, oom, "native malloc failed");
            (*env)->DeleteLocalRef(env, oom);
        }
        return 0L;
    }

    p->value = value;
    return (jlong)(intptr_t)p;
}

JNIEXPORT jint JNICALL Java_example_jni_NativeBuffer_nativeRead(
        JNIEnv *env, jclass cls, jlong handle) {
    (void)env;
    (void)cls;

    // Handle chỉ đến đây từ Java wrapper sau khi kiểm tra open.
    Buffer *p = (Buffer *)(intptr_t)handle;
    return p->value;
}

JNIEXPORT void JNICALL Java_example_jni_NativeBuffer_nativeFree(
        JNIEnv *env, jclass cls, jlong handle) {
    (void)env;
    (void)cls;

    if (handle != 0L) {
        free((void *)(intptr_t)handle);
    }
}
```

Đối với các nền tảng JNI phổ biến có con trỏ không rộng hơn 64 bit, `intptr_t` hỗ trợ chuyển con trỏ sang số nguyên đủ rộng, sau đó chứa trong `jlong`. Đây là **mã minh họa ABI trên các nền tảng thông dụng**, không phải chuẩn serialization pointer hay handle an toàn giữa hai process. Không ghi các địa chỉ này vào database để nạp lại sau khi process khởi động lại.

**Điểm quan trọng hơn phép cast:** `nativeRead(handle)` **chỉ an toàn khi handle hợp lệ và chưa bị free**. C không thể xác minh bằng kiểm tra `handle != 0` rằng con trỏ chưa bị giải phóng; contract bảo vệ vòng đời nằm ở wrapper Java và các quy tắc đồng bộ. Không công khai một native method nhận arbitrary pointer từ mã Java không tin cậy.

`nativeFree` dùng `free`, là thao tác release đơn giản không có callback Java và không đòi thread cụ thể. Điều này làm nó phù hợp làm Cleaner fallback. Với native resource cần thread-affine release hoặc thao tác có thể thất bại, giải pháp phải phức tạp hơn và không thể áp dụng y nguyên ví dụ.

### 5.4. Build và chạy trên Linux

Yêu cầu: **JDK 17+**, GCC và `JAVA_HOME` trỏ đến thư mục JDK có `include/jni.h`.

```bash
gcc -std=c11 -O2 -fPIC -shared \
    -I"$JAVA_HOME/include" \
    -I"$JAVA_HOME/include/linux" \
    -Ibuild/include \
    -o build/native/libnativebuffer.so \
    NativeBuffer.c

java -Djava.library.path=build/native \
    -cp build/classes \
    example.jni.NativeBuffer
```

**Stdout khi biên dịch và nạp thành công:**

```text
Value: 42
Closed: true
Read after close: blocked
```

Giải thích:

- `new NativeBuffer(42)` cấp phát `Buffer` ở C.
- `read()` lấy `jint value` qua `nativeRead`, in `42`.
- Thoát `try (buffer)` buộc gọi `close()`; `cleanable.clean()` chạy action, `getAndSet(0)` lấy pointer cũ và `nativeFree` giải phóng nó.
- `buffer.close()` lần thứ hai không thể giải phóng lại native pointer.
- `isClosed()` thấy address đã bằng `0`; `read()` tiếp theo ném `IllegalStateException` **trước khi gọi JNI**, rồi Java bắt và in dòng cuối.
- Không cần gọi `System.gc()`, không phụ thuộc lịch Cleaner.

### 5.5. Build trên macOS và Windows

**macOS**, sau khi tạo class/header bằng cùng lệnh `javac -h`:

```bash
clang -O2 -dynamiclib \
    -I"$JAVA_HOME/include" \
    -I"$JAVA_HOME/include/darwin" \
    -Ibuild/include \
    -o build/native/libnativebuffer.dylib \
    NativeBuffer.c

java -Djava.library.path=build/native \
    -cp build/classes \
    example.jni.NativeBuffer
```

**Windows**, từ Visual Studio Developer Command Prompt đã cấu hình JDK, `cl` và `JAVA_HOME`:

```bat
mkdir build\classes
mkdir build\include
mkdir build\native

javac -h build\include -d build\classes src\example\jni\NativeBuffer.java

cl /nologo /LD /I"%JAVA_HOME%\include" /I"%JAVA_HOME%\include\win32" /I"build\include" NativeBuffer.c /Febuild\native\nativebuffer.dll

java -Djava.library.path=build\native -cp build\classes example.jni.NativeBuffer
```

`System.loadLibrary("nativebuffer")` yêu cầu tên logic; JVM ánh xạ thành `libnativebuffer.so` (Linux), `libnativebuffer.dylib` (macOS), hoặc `nativebuffer.dll` (Windows). Compiler native và JVM phải cùng kiến trúc/ABI tương ứng. Nếu môi trường JDK mới yêu cầu cấp quyền native access khi chạy JNI, thêm lựa chọn runtime phù hợp phiên bản/module, chẳng hạn `--enable-native-access=ALL-UNNAMED` khi được hỗ trợ và cần thiết.

**Kiểm chứng thực tế:** phần `NativeBuffer.java` và JNI header đã được biên dịch/tạo bằng `javac -h`. C source được thiết kế tương thích với header; việc chạy C cần một C compiler và môi trường JVM đúng hệ điều hành. Kết quả stdout mô tả đường thực thi khi build và load native library thành công.

## 6. Bốn tuyến vòng đời phải được giải quyết riêng

### 6.1. Tuyến bình thường: gọi close trước khi hết scope

```text
new NativeBuffer
   -> nativeAlloc
   -> Cleaner.register
   -> read, read, ...
   -> close
   -> cleanable.clean
   -> State.address.getAndSet(0)
   -> nativeFree(handle)
   -> về Java với resource closed
```

Đây là tuyến **được kỳ vọng**. Nó hoạt động bất kể GC hay Cleaner thread có chạy vào thời điểm đó hay không. Nếu caller dùng `try-with-resources`, cleanup còn được gọi khi thân `try` ném exception.

### 6.2. Tuyến quên close: chỉ có thể hy vọng Cleaner

```text
new NativeBuffer
   -> nativeAlloc
   -> Cleaner.register
   -> caller bỏ tham chiếu đến wrapper
   -> [có thể rất lâu, không có deadline]
   -> GC xác định phantom reachability
   -> Cleaner xử lý action
   -> State.run -> nativeFree
```

Tuyến này **không thể được dùng làm bằng chứng về thời gian release**. Process có thể kết thúc trước khi action chạy, hoặc native memory tăng trước khi GC thu gom đủ object wrappers. Đây là **fallback best effort**, không phải điều kiện hoàn tất hợp đồng.

### 6.3. Tuyến constructor thất bại

Constructor có thể tạo native resource rồi thất bại ở bước tiếp theo, ví dụ do không thể đăng ký Cleaner. Nếu để mặc định Java object constructor fail mà không cleanup, native allocation trở thành orphan.

Trong ví dụ:

```text
State = new State()              // Java resource phụ trợ
nativeAlloc()                    // native resource đã mở
State.setAddress(...)
Cleaner.register(...)  -- nếu fail --> State.run() -> nativeFree()
```

Nếu `malloc` trong C thất bại, `nativeAlloc` tạo `OutOfMemoryError` (hoặc lỗi JNI lookup exception nếu việc tạo exception thất bại), không có pointer hợp lệ để free. **Không mặc nhiên dựa vào Cleaner để dọn tài nguyên từ constructor chưa hoàn tất.**

Khi mở nhiều resource nối tiếp trong constructor, nên dùng các local variables kèm `try/finally` hoặc quy trình *acquire → validate → transfer ownership* để release tất cả thành phần đã được cấp phát nếu bất kỳ bước nào fail.

### 6.4. Tuyến concurrent close và use

Trên một wrapper JNI, tình huống nguy hiểm:

```text
Thread A                            Thread B
--------                            --------
ptr = address  // nonzero
                                    close() -> free(ptr)
nativeRead(ptr)  // use-after-free!
```

**AtomicLong.getAndSet(0) chỉ chặn double-free của những lần release cạnh tranh; nó KHÔNG tự ngăn use-after-free giữa read và close.**

Ví dụ xử lý việc **Java calls** bằng `synchronized read()` và `synchronized close()` trên cùng wrapper:

```text
Thread A                         Thread B
--------                         --------
enter monitor(buffer)
get pointer
nativeRead(pointer)
Reference.reachabilityFence(buffer)
exit monitor(buffer)
                                 enter monitor(buffer)
                                 cleanable.clean -> free(pointer)
                                 exit monitor(buffer)
```

Nếu thread B tới trước, A sẽ đọc address = 0 và ném `IllegalStateException`. Nếu A tới trước, B đợi tới khi A đọc xong mới free. Với nhiều native threads hoặc C callbacks dùng handle bên ngoài hai Java methods, **monitor của wrapper không tự bảo vệ tất cả native consumers**; cần native mutex, ref counting, lease/borrow API hoặc cơ chế quản lý vòng đời phù hợp.

## 7. Reference.reachabilityFence và “premature cleaning”

Một trường hợp khó nhận ra: Java code có thể chỉ đọc `long address` rồi gọi native method, sau đó **không đọc thêm field nào của wrapper**. JIT đôi khi chứng minh Java object không còn cần thiết sau khi đã đọc address; collector có thể coi owner không còn strongly reachable **trước khi native operation hoàn tất**, dù source code còn ở trong phương thức.

Ví dụ khái niệm:

```java
long ptr = state.address();
int result = nativeRead(ptr);
// Nếu owner bị xem là không còn sống trước khi nativeRead kết thúc,
// Cleaner action có thể giải phóng ptr đúng lúc đang dùng.
```

`Reference.reachabilityFence(this)` bảo đảm object truyền vào còn strongly reachable **ít nhất đến thời điểm gọi fence**. Đặt fence trong `finally` sau native operation đảm bảo nó được thực hiện cả khi JNI call kết thúc bằng một Java exception:

```java
try {
    return nativeRead(ptr);
} finally {
    Reference.reachabilityFence(this);
}
```

Điều này bảo vệ khỏi **premature GC-based cleanup** của chính owner. Nó **không** thay thế synchronization giữa explicit close và use, và không tự bảo vệ handle bị xóa bởi native thread khác không tuân thủ ownership. Bởi vậy ví dụ dùng **cả `synchronized` và `reachabilityFence`**, mỗi thứ giải quyết một loại race riêng.

## 8. Vì sao State phải độc lập và release chỉ một lần?

### 8.1. Tách referent khỏi action

`CLEANER.register(this, fresh)` có hai vai trò khác nhau:

- `this` là owner dùng để theo dõi GC reachability.
- `fresh` chứa handle và biết cách release nhưng **không tham chiếu `this`**.

Với `State` là `static final class`, không có implicit outer instance. Không viết cleanup action bằng instance method reference như `this::releaseNative`, hoặc lambda trực tiếp truy cập field của owner; các biểu thức ấy có thể giữ owner reachable.

### 8.2. Atomic swap thành 0 trước khi free

```java
long ptr = address.getAndSet(0L);
if (ptr != 0L) {
    nativeFree(ptr);
}
```

Đặt thành 0 trước đảm bảo nếu action được gọi lần nữa, không có pointer cũ để free. `Cleaner.Cleanable.clean()` vốn cũng có hợp đồng **at-most-once**; `getAndSet` là lớp bảo vệ tại state và làm `isClosed` hoạt động. Tuy nhiên nếu native free **có thể fail**, đánh dấu 0 trước thao tác release nghĩa là không thể retry qua state; cần thiết kế giao thức đóng và báo lỗi khác, không sao chép mẫu này cho tài nguyên có cleanup failure semantics phức tạp.

### 8.3. Không dùng finalizer làm cleanup chính

`Object.finalize()` bị deprecated và có nhiều hạn chế: không dự đoán được timing, thứ tự, nguy cơ deadlock và vấn đề resurrection. Với tài nguyên ngoài heap, API hiện đại ưu tiên **explicit close**; `Cleaner` chỉ là lựa chọn fallback có kiểm soát hơn finalization, **không biến cleanup bất đồng bộ thành deterministic cleanup**.

## 9. So sánh các cơ chế giải phóng

| Cơ chế | Khi nào được gọi | Giải phóng native đúng hạn? | Ghi chú |
| --- | --- | --- | --- |
| `close()` do caller gọi đúng lúc | Khi caller quyết định xong resource | **Có thể thiết kế để đúng hạn**, nếu code release thành công | Lựa chọn chủ đạo cho JNI handles |
| `try-with-resources` | Khi ra khỏi scope, kể cả vì exception thông thường | **Có**, nhờ gọi `close` xác định | Nên dùng cho resource có scope rõ ràng |
| `Cleaner.Cleanable.clean()` gọi tường minh | Ngay tại code gọi `clean()` | **Có thể**, nếu action phù hợp và hoàn tất | Trong ví dụ được gọi từ `close()` |
| Cleaner action tự động | Sau phantom reachability và xử lý Cleaner | **Không** | Không có thời hạn; bất đồng bộ; thread riêng |
| GC / `System.gc()` | Theo quyết định collector/runtime | **Không** | GC không tự biết `malloc`/`free` của JNI wrapper |
| `finalize()` | Cơ chế finalization cũ (deprecated) | **Không** | Không dùng làm release strategy |
| `Runtime.addShutdownHook` | Một số đường shutdown có trật tự | **Không bảo đảm** | Không chạy trong mọi kiểu termination; không thay `close` |

Một resource có ràng buộc *capacity*, ví dụ tối đa vài trăm file descriptors hoặc native handles, cần **đóng theo contract** và có thể thêm quota/backpressure. Đừng chỉ “đợi GC” khi đối tượng Java bao bọc rất nhẹ so với native allocation lớn.

## 10. Khi nào Cleaner fallback không thích hợp?

### Tài nguyên gắn với thread hoặc context

Một số native APIs yêu cầu release tại đúng OS thread hoặc context đã tạo: GPU graphics contexts, GUI toolkits, một số C/C++ thread-affine libraries, COM apartment, thread-local allocators. Cleaner thread **khác** owner thread; trực tiếp gọi native destructor từ Cleaner có thể vi phạm contract của library.

Giải pháp là **explicit close đúng context**. Nếu vẫn muốn fallback, action có thể chỉ ghi nhận cảnh báo/rò rỉ hoặc yêu cầu chuyển việc tới đúng owner thread qua cơ chế phù hợp; không đảm bảo yêu cầu được xử lý nếu owner thread/process đã chết.

### Cleanup có thể chặn lâu hoặc phát sinh lỗi quan trọng

Cleaner thread phục vụ nhiều actions; một action làm I/O dài, gọi Java callbacks, chờ locks, hoặc thực hiện destructor phức tạp có thể trì hoãn các actions khác. Tác vụ cleanup nên ngắn, an toàn, không phụ thuộc vào đối tượng đã phantom reachable và hạn chế blocking.

Nếu `close` có thể ném lỗi cần hiển thị cho caller, thiết kế một **explicit close path** có trả lỗi/exception rõ ràng. Cleaner chỉ còn là fallback không thể đảm bảo báo lỗi giống `close`. Trong ví dụ, `free` được dùng vì có thể release đơn giản, không có ý nghĩa nghiệp vụ cần báo lỗi.

### Resource liên quan đến giao dịch hoặc flush

Ví dụ ghi file native, flush database transaction, commit message, gửi dữ liệu tới thiết bị: bỏ thao tác quyết định vào Cleaner có thể làm mất dữ liệu hoặc vi phạm giao dịch. **Bắt buộc dùng close/commit/rollback tường minh** và xử lý failures trong Java code có quyền quyết định kết quả nghiệp vụ.

## 11. Debug và kiểm thử vòng đời native

Một bộ kiểm thử hợp lý nên chia thành hai nhóm: **deterministic tests** cho explicit close và **best-effort observations** cho Cleaner fallback.

### Kiểm thử deterministic

- Tạo wrapper, gọi native operation, sau đó `close`: xác nhận không còn sử dụng được.
- Gọi `close` lần hai: không xảy ra `double free` hoặc crash.
- Gọi `read` sau close: ném `IllegalStateException` ở Java trước khi chạm native pointer.
- Đặt exception bên trong `try-with-resources`: xác nhận close vẫn được gọi; nếu close cũng ném, kiểm tra suppressed exception.
- Concurrent read/close: xác minh không có use-after-free qua tất cả đường truy cập handle.
- Constructor fail sau khi native allocation: xác minh cleanup xảy ra ở nhánh exception.
- Stress test nhiều vòng `open/read/close`, giám sát native memory, file descriptors và nhật ký giải phóng. Khi phù hợp có thể dùng AddressSanitizer, Valgrind hoặc công cụ native profiler phù hợp OS.

### Không viết những unit test dựa trên GC như một deadline

Ví dụ **không nên**:

```java
NativeBuffer buffer = new NativeBuffer(10);
buffer = null;
System.gc();
Thread.sleep(100);
assert nativeAllocationCount() == 0; // Không được bảo đảm!
```

GC có thể không thu gom, Cleaner action có thể chưa chạy, và thời gian 100ms không phải một phần contract. Nếu phải thử fallback Cleaner, dùng bài test tích hợp riêng, có deadline theo yêu cầu test harness và chấp nhận kết quả phụ thuộc môi trường; **không dùng nó làm tiêu chuẩn đảm bảo việc release trong ứng dụng**.

Với việc debug JNI, `-Xcheck:jni` trên HotSpot/OpenJDK cũng giúp phát hiện một số vi phạm JNI, nhưng **không thể thay thế** bảo vệ handle ownership và đồng bộ read/close. Những lỗi như double-free hoặc use-after-free C pointer thường cần sanitizer và kiểm thử native chuyên dụng.

## 12. Các hiểu nhầm và lỗi thường gặp

| Hiểu nhầm | Vì sao sai | Cách làm đúng |
| --- | --- | --- |
| “Java có GC nên không cần free vùng nhớ malloc” | GC không sở hữu allocation C tùy ý | Native allocation phải có native release |
| “Đặt `buffer = null` rồi `System.gc()` tương đương close” | GC không có deadline; Cleaner có thể chưa chạy | `close()` tường minh |
| “Cleaner chạy khi object hết scope” | Hết scope source không đồng nghĩa phantom reachability hay action được schedule ngay | Dùng `try-with-resources` |
| “Dùng Cleaner thì JVM luôn dọn ở shutdown” | Không bảo đảm System.exit, crash, kill process | Đóng trước shutdown khi luồng còn kiểm soát |
| “Cleaner action có thể gọi `this.nativeFree()`” | Action giữ owner => owner không phantom reachable | Tách `static State` không capture owner |
| “AtomicLong getAndSet(0) ngăn mọi race” | Chỉ ngăn giải phóng lặp; không ngăn read-vs-free | Đồng bộ/quản lý borrow, dùng reachability fence |
| “Chỉ cần `synchronized close()`” | Native operation không cùng đồng bộ vẫn có thể giữ stale handle | Đồng bộ **tất cả** đường dùng handle |
| “Cleaner có thể gọi destructor ở bất kỳ native thread nào” | Resource có thể thread-affine | Close đúng thread/context |
| “Sau khi gọi free, vẫn có thể dùng long address cũ” | Use-after-free, có thể JVM crash | Zero handle, kiểm tra closed trước JNI |
| “Native buffer lớn sẽ khiến heap GC tự chạy kịp” | Heap pressure không phản ánh đầy đủ native resource pressure | Đóng xác định, quota, quan sát native metrics |
| “Mọi lỗi khi close đều có thể bỏ qua” | Có thể mất dữ liệu, rò tài nguyên hoặc vi phạm giao dịch | Thiết kế error reporting cho explicit close |

## 13. Checklist review một JNI wrapper

1. **Ownership:** Ai sở hữu native handle? Bên tạo hay bên nhận chịu trách nhiệm đóng? Khi truyền qua FFI/JNI có bị copy handle sang nơi khác mà không chuyển ownership không?
2. **Acquisition:** Nếu tạo native resource thành công nhưng bước đăng ký/constructor kế tiếp thất bại, đã cleanup bằng `finally`/catch chưa?
3. **Explicit close:** Wrapper có `AutoCloseable` và `close` tương thích `try-with-resources` không? API có tài liệu hóa trạng thái sau close?
4. **Double-free:** close lặp có bị release trùng không? State có chuyển atomically từ OPEN sang CLOSED không?
5. **Use-after-free:** close có chờ các native operations đang dùng resource không? Tất cả read/write/methods có cùng giao thức đồng bộ không?
6. **Cleaner reachability:** Cleanup action có giữ strong reference tới owner không? Có lỡ dùng non-static inner class, lambda hay method reference capture `this` không?
7. **Cleaner limitations:** Cleanup có an toàn trên Cleaner thread không? Có khả năng blocking, JNI callbacks, exceptions hoặc thread affinity không?
8. **Reachability fence:** Có rủi ro owner bị JIT coi là unreachable trong lúc native method còn dùng raw pointer không? `Reference.reachabilityFence(owner)` đặt sau last use có phù hợp không?
9. **Errors:** Native release thất bại thì báo thế nào? Có bị Cleaner thread bỏ qua exception không? Có che mất lỗi chính khi đóng?
10. **Tests:** Có unit tests deterministic cho close, close twice, use-after-close, constructor failure, concurrent close/read và exception trong scope không?

## 14. Câu hỏi tự kiểm tra

**Câu 1.** Wrapper Java chỉ giữ một `long address` đến `malloc`. Vì sao GC không thể tự thay thế `free(address)`?

**Đáp án:** GC quản lý Java heap object và reachability; nó không hiểu contract của allocation C gắn với `long`, không tự gọi destructor riêng. Native resource cần code release và ownership rõ ràng.

**Câu 2.** `System.gc()` có đảm bảo Cleaner action chạy trước khi lệnh kế tiếp được thực hiện không?

**Đáp án:** Không. GC có thể không diễn ra ngay hoặc không xử lý object đó; action chạy bất đồng bộ sau khi object phantom reachable và Cleaner nhận thông báo.

**Câu 3.** `cleanable.clean()` khác gì với “đợi GC gọi Cleaner”?

**Đáp án:** `clean()` được gọi tường minh và kích hoạt cleaning action ngay trong luồng thao tác, at most once; đợi GC/cleaner thread là bất đồng bộ, không có thời hạn.

**Câu 4.** Vì sao một lambda như `() -> nativeFree(this.address)` không thích hợp làm Cleaner action?

**Đáp án:** Vì nó capture `this`; Cleaner giữ action, action giữ owner, nên owner có thể không bao giờ phantom reachable để trigger cleanup tự động.

**Câu 5.** `AtomicLong.getAndSet(0)` đã giải quyết xong mọi vấn đề đồng thời chưa?

**Đáp án:** Chưa. Nó giúp tránh double-free nếu nhiều cleanup cùng được kích hoạt, nhưng không ngăn luồng khác đã lấy pointer tiếp tục dùng trong khi close vừa free. Phải đồng bộ/quản lý quyền sử dụng handle.

**Câu 6.** `Reference.reachabilityFence(this)` có thay `synchronized` không?

**Đáp án:** Không. Fence giúp owner strongly reachable tới điểm xác định trước GC-based cleanup; synchronized bảo vệ khỏi concurrent explicit close. Hai cơ chế giải quyết hai loại race khác nhau.

**Câu 7.** Một native resource cần release trên thread đã tạo nó. Có nên gọi release trực tiếp từ Cleaner thread không?

**Đáp án:** Không mặc nhiên. Phải tôn trọng thread/context ownership; dùng close tường minh trên đúng thread hoặc thiết kế fallback phù hợp nhưng không phụ thuộc fallback để bảo đảm deadline.

**Câu 8.** Một request Java đã xong việc với native buffer và cần giải phóng ngay để phục vụ request tiếp. Nên chọn cơ chế nào?

**Đáp án:** `try-with-resources` và `close` ở cuối scope/request, kiểm tra lỗi release nếu có. Cleaner/GC chỉ dự phòng, không bảo đảm thời gian giải phóng.

## Tài liệu chính thức

- [Oracle Java SE 17 — AutoCloseable](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/AutoCloseable.html)
- [Oracle Java SE 17 — Cleaner và Cleaner.Cleanable](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ref/Cleaner.html)
- [Oracle Java SE 17 — Cleaner.Cleanable.clean()](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ref/Cleaner.Cleanable.html)
- [Oracle Java SE 17 — Reference.reachabilityFence](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ref/Reference.html#reachabilityFence(java.lang.Object))
- [Oracle Java SE 17 — JVM GC: Other Considerations / Cleaner](https://docs.oracle.com/en/java/javase/17/gctuning/other-considerations.html)
- [Oracle Java SE 17 — JNI Design Overview](https://docs.oracle.com/en/java/javase/17/docs/specs/jni/design.html)
- [Oracle Java SE 17 — javac -h](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javac.html)

**Kết luận:** **`close()` tường minh là hợp đồng chính cho vòng đời JNI**; `try-with-resources` giúp thực thi hợp đồng ở thời điểm biết trước. **`Cleaner` là fallback không có cam kết thời hạn** và chỉ nên chạy cleanup ngắn, độc lập owner, an toàn với thread thực thi. **GC không sở hữu native handle và không thay được việc free/close đúng lúc**.
