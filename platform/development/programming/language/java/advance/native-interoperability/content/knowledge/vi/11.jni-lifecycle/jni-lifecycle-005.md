# Định nghĩa quyền sở hữu handle bản địa gắn với đối tượng Java

## Mục tiêu

Một đối tượng Java có thể đại diện cho tài nguyên được tạo trong C/C++: vùng nhớ cấp phát bằng `malloc` hoặc `new`, socket, file descriptor, đối tượng thư viện đồ họa, context của codec, database connection, hay một cấu trúc có internal state. Java object sống trong heap do JVM quản lý; tài nguyên native lại tuân theo **quy tắc cấp phát/giải phóng của chính thư viện native**. Vì vậy một trường `long handle` trong Java **không tự động tạo ra quyền sở hữu hay cơ chế giải phóng**.

Bài này tập trung trả lời các câu hỏi: **Ai tạo handle? Ai sở hữu tài nguyên? Ai chỉ mượn? Khi nào được sử dụng? Ai đóng nó, đóng bao nhiêu lần, và chuyện gì xảy ra khi Java object bị GC?**

Sau khi học, bạn có thể:

- Phân biệt **JNI reference**, **opaque native handle**, **native pointer** và tài nguyên thực mà pointer/handle trỏ tới.
- Định nghĩa các mô hình **unique ownership**, **borrowed handle**, **shared ownership** và **ownership transfer** bằng hợp đồng API rõ ràng.
- Xây wrapper Java `AutoCloseable` có trạng thái mở/đóng, sentinel `0L`, `close()` idempotent và kiểm soát truy cập sau đóng.
- Gọi JNI đúng với một ví dụ Java 17 + C có `nativeCreate`, `nativeRead`, `nativeIncrement`, `nativeDestroy`; biết rõ giới hạn an toàn của việc mã hóa pointer bằng `jlong`.
- Phòng tránh `double free`, `use-after-free`, rò rỉ native memory, sai kiểu handle, tranh chấp `close`/operation và xử lý lỗi giữa chừng.
- Biết cách dùng `Cleaner` như phương án dự phòng chứ không thay thế cho quản lý vòng đời tường minh.
- Thiết kế/test ownership contract đủ rõ để có thể review ở biên giới JVM–native.

## 1. Java object không đồng nghĩa native resource

Xét lớp Java mô tả một native counter:

~~~java
final class NativeCounter {
    private long handle;
}
~~~

`handle` chỉ là **64 bit dữ liệu** trong Java. Nó có thể biểu diễn:

1. Một địa chỉ native được mã hóa thành số nguyên (quy ước pointer-as-handle).
2. Một token/ID tìm kiếm trong bảng registry của thư viện native.
3. Một OS descriptor hoặc giá trị opaque do SDK trả về.
4. Một chỉ số cộng generation nhằm phát hiện handle cũ.

**Không có kiểu biểu diễn nào trong số này tự áp đặt ownership.** Cũng không nên nhầm `long handle` với `jobject`:

| Khái niệm | Ai quản lý? | Là gì? | Giải phóng bằng gì? |
|---|---|---|---|
| Java object, ví dụ `NativeCounter` | JVM/GC | Instance Java chứa field và method | GC quản lý bộ nhớ heap của object |
| `jobject` / `jclass` local JNI reference | JVM/JNI | Reference hợp lệ trong native frame | `DeleteLocalRef` hoặc frame kết thúc |
| JNI global reference | JVM/JNI | Root giữ object Java qua native calls | `DeleteGlobalRef` |
| JNI weak global reference | JVM/JNI | Weak root, không giữ object sống | `DeleteWeakGlobalRef` |
| `jlong` native handle | Quy ước của thư viện | Số nguyên/token có ý nghĩa theo API | **Không tự được giải phóng** |
| `malloc`-allocated state | C/native allocator | Vùng nhớ C | `free` tương ứng, đúng một lần |
| `new`-allocated C++ object | C++ allocator | Instance C++ | `delete` tương ứng, đúng một lần |
| OS socket/file handle | OS/native SDK | Tài nguyên hệ điều hành | `close`/`closesocket`/API hủy theo nền tảng |

Ví dụ: GC có thể thu hồi `NativeCounter`, nhưng nếu `handle` chứa một địa chỉ đã được `malloc` thì JVM **không tự gọi `free`** dựa trên giá trị số ấy. Ngược lại, `DeleteGlobalRef` chỉ bỏ JNI reference tới Java object, **không giải phóng** một `malloc` pointer được lưu ở field Java.

Vì vậy, cần thiết kế vòng đời ở **hai thế giới**: bộ nhớ Java do GC quản lý và tài nguyên native có owner cụ thể.

## 2. Định nghĩa ownership contract trước khi viết API

Một native handle có thể được truy cập ở nhiều nơi, nhưng mỗi lần giải phóng phải có **quy tắc hợp lệ duy nhất**. Hãy ghi rõ ở tài liệu API:

- **Nguồn tạo:** `nativeCreate`, API SDK, factory hay hàm trả handle mượn?
- **Owner:** Java wrapper, một native manager, một process-wide registry hay đối tượng C++ khác?
- **Quyền của caller:** được gọi đọc/ghi, được lưu lại, được copy, được chuyển quyền, được gọi destroy hay không?
- **Phạm vi hiệu lực:** từ lúc tạo đến lúc `close`, hết callback, hết phiên native, hoặc theo refcount?
- **Ai giải phóng và bằng hàm nào:** `nativeDestroy`, `free`, `delete`, SDK release; đúng allocator và đúng version.
- **Quy tắc sau đóng:** handle invalid; mọi operation phải báo lỗi hoặc trả trạng thái rõ ràng, **không** dereference địa chỉ cũ.
- **Thread-safety:** operation, callback, close và background Cleaner có thể chạy đồng thời không?
- **Lỗi và huỷ:** nếu khởi tạo thất bại giữa chừng, ai trả các tài nguyên đã acquire? Nếu `close` lỗi, còn được thử lại hay phải chặn dùng tiếp?
- **Ranh giới thư viện:** handle có còn hợp lệ sau khi native library unload, process restart, class loader unload hay không?

### Bốn mô hình quyền sở hữu

| Mô hình | Ý nghĩa | Ai được destroy? | Dùng khi |
|---|---|---|---|
| **Unique ownership** | Có một owner quản lý vòng đời | Chỉ owner (hoặc tầng quản lý đại diện cho owner) | Mỗi Java wrapper sở hữu đúng một native resource |
| **Borrowed/non-owning** | Chỉ mượn quyền dùng trong thời hạn đã nêu | **Không** được destroy | Callback, getter trả view/handle nội bộ |
| **Shared/refcounted ownership** | Nhiều owner, mỗi owner có một quyền giữ (retain) | Release quyền của mình; lần cuối native mới hủy | Object dùng chung giữa wrappers/threads |
| **Ownership transfer (move)** | Owner A nhường quyền cho B | B sau transfer; A phải bị vô hiệu hóa | Native factory hoặc giao API trả ownership |

**Không được biến borrow thành own bằng cách copy `long`.** Copy bit pattern của handle không gọi `retain`, không cấp thêm quyền sở hữu và không kéo dài lifetime.

Ví dụ hợp đồng nên ghi bằng ngôn ngữ cụ thể:

> `createNative(initial)` trả một handle **owned** mới. Mỗi handle thành công thuộc duy nhất một `NativeCounter`. `readNative` và `incrementNative` chỉ **borrow** handle trong thời gian lời gọi đang diễn ra. `destroyNative` nhận quyền sở hữu của handle, giải phóng tài nguyên đúng một lần và làm handle hết hiệu lực. Sau `close()`, Java wrapper không gọi operation nào với handle cũ.

Định nghĩa này quan trọng hơn việc field trong Java tên là `pointer`, `address` hay `handle`.

## 3. Trạng thái và bất biến cho unique owner

Với lớp owner đơn giản, ta dùng máy trạng thái:

~~~text
       constructor Java
              |
              v
   nativeCreate(...) thành công
              |
              v
        OPEN (handle != 0)
           |        |
           |        +--- value()/increment(): mượn handle tạm thời
           |
           v
    close(): đổi trạng thái
           |
           v
        CLOSED (handle == 0)
           |        |
           |        +--- mọi operation: IllegalStateException
           |
           +--- close() lần nữa: không làm gì
~~~

Nếu `nativeCreate` thất bại, object **không được công bố** ở trạng thái OPEN với handle không hợp lệ. Nếu `nativeDestroy` không thể thất bại (như `free` với pointer hợp lệ trong ví dụ), `close` có thể đặt handle về `0` rồi destroy một lần.

Các bất biến tối thiểu:

1. `OPEN` chỉ khi handle đang đại diện cho native state hợp lệ.
2. `CLOSED` khi handle bằng sentinel `0L`; chỉ dùng sentinel này nếu native API bảo đảm không bao giờ cấp giá trị đó làm handle hợp lệ.
3. Một handle **owned** không được có hai Java wrappers độc lập cùng gọi native destroy.
4. Không có native operation nào được sử dụng resource **sau** khi việc destroy hoàn tất.
5. `close` được gọi lặp lại trên **cùng wrapper** phải vô hại (idempotent ở phía Java).
6. Trước khi resource được trao thành công cho owner mới, lỗi giữa chừng phải được cleanup bởi nơi còn giữ quyền sở hữu.
7. Không coi dấu âm của `long` là bằng chứng handle sai: nếu mã hóa raw pointer, bit cao có thể được đặt; so sánh với sentinel đã định nghĩa, **không** tự suy luận `handle > 0`.

**Idempotent ở wrapper không có nghĩa native `free` idempotent.** C standard `free` cùng một non-null pointer đã giải phóng lần thứ hai là undefined behavior. Java wrapper phải bảo đảm `nativeDestroy` **chỉ nhận handle từng được hủy đúng một lần**, hoặc native registry phải có cơ chế chống trùng lặp độc lập.

## 4. Mẫu thiết kế Java: AutoCloseable là đường đóng chính

Với resource có vòng đời rõ như file, context hoặc session, dùng `AutoCloseable` và `try-with-resources` để chủ động đóng. Không đợi GC.

~~~java
try (NativeCounter counter = new NativeCounter(5)) {
    System.out.println(counter.value());
    System.out.println(counter.increment());
} // close() được gọi khi rời block (kể cả khi có Java exception)
~~~

Đây là **mảnh Java minh họa**; lớp chạy đầy đủ có ở phần tiếp theo. `AutoCloseable` giúp Java đảm bảo `close()` được gọi lúc rời `try` theo cơ chế ngôn ngữ. Nó không quyết định cách native resource được hủy; bạn phải tự hiện thực `close` đúng.

Các quyết định trong lớp wrapper:

- **Ẩn handle:** để `private`; API bình thường không công khai một `long` để caller tùy ý giả mạo/chuyển giữa wrappers.
- **Giữ một owner:** không có copy constructor tạo wrapper thứ hai từ cùng raw address mà không thực hiện ownership transfer/refcount.
- **Mọi method dùng handle kiểm tra OPEN trước khi gọi JNI.**
- **Đồng bộ `close` và native operations trên cùng lock** để chặn close chạy song song với một call đang dùng handle.
- **Không thêm logic Java phức tạp sau khi đã acquire native state nhưng trước khi owner sẵn sàng:** nếu giai đoạn đó có thể throw, cần `try/finally` cleanup khi factory không trả được object.
- **Không giữ native resource sống vô hạn** chỉ vì một Java object vẫn được tham chiếu; cung cấp `close` cho phép ứng dụng trả resource sớm.

## 5. Ví dụ đầy đủ Java 17 + JNI C: một owner, một lần giải phóng

Bài thực hành dùng một native struct `CounterState` trên heap C. Java wrapper giữ một handle mã hóa địa chỉ của struct. `close` có trách nhiệm hủy state và ngăn dùng lại. Đây là **mẫu học tập dành cho handle nội bộ đáng tin cậy trong một wrapper duy nhất**, không phải hệ thống xác thực handle không đáng tin cậy hoặc chia sẻ pointer tùy ý giữa nhiều Java objects.

### 5.1. File Java: `NativeCounterDemo.java`

~~~java
public final class NativeCounterDemo {
    static {
        System.loadLibrary("nativecounterdemo");
    }

    private static native long createNative(int initial);
    private static native int readNative(long handle);
    private static native int incrementNative(long handle);
    private static native void destroyNative(long handle);

    public static final class NativeCounter implements AutoCloseable {
        private long handle;

        public NativeCounter(int initial) {
            long created = createNative(initial);
            if (created == 0L) {
                throw new OutOfMemoryError("Cannot allocate NativeCounter");
            }
            handle = created;
        }

        private void requireOpen() {
            if (handle == 0L) {
                throw new IllegalStateException("NativeCounter is closed");
            }
        }

        public synchronized int value() {
            requireOpen();
            return readNative(handle);
        }

        public synchronized int increment() {
            requireOpen();
            return incrementNative(handle);
        }

        public synchronized boolean isClosed() {
            return handle == 0L;
        }

        @Override
        public synchronized void close() {
            if (handle == 0L) {
                return; // Đóng lần thứ hai không free thêm.
            }

            long owned = handle;
            handle = 0L; // Hết hiệu lực ở Java trước khi nativeDestroy.

            destroyNative(owned); // Chỉ gọi một lần cho handle này.
        }
    }

    public static void main(String[] args) {
        NativeCounter counter = new NativeCounter(5);

        try (counter) {
            System.out.println("before=" + counter.value());
            System.out.println(
                    "afterIncrement=" + counter.increment());
            System.out.println("afterRead=" + counter.value());
        }

        System.out.println("closed=" + counter.isClosed());

        counter.close();
        System.out.println(
                "closedTwice=" + counter.isClosed());

        try {
            counter.value();
        } catch (IllegalStateException error) {
            System.out.println("afterClose=" + error.getMessage());
        }
    }
}
~~~

**Những điểm quyết định quyền sở hữu:**

- `NativeCounterDemo` chứa các JNI methods dạng `private static native`; ứng dụng bình thường không thể gọi trực tiếp với một số handle tùy ý.
- `new NativeCounter(5)` nhận đúng **một** native allocation. Trường `handle` chỉ được gán khi tạo thành công.
- `value()` và `increment()` mượn handle trong lúc method chạy, không nhận ownership mới; native code không tự do giải phóng resource ở hai lời gọi này.
- Cả `value()`, `increment()` và `close()` là `synchronized` trên **cùng object Java**, vì vậy các lời gọi thông thường tới wrapper này không đồng thời đọc handle và giải phóng nó. Không có một `close` từ thread khác chen ngang khi `readNative` đang chạy.
- `close()` thay handle bằng `0L` trước khi gọi hủy. `destroyNative` trong ví dụ chỉ thực hiện `free` đối với pointer hợp lệ và không báo lỗi; thứ tự này bảo đảm lần close sau không gọi `free` lặp lại.
- Sau đóng, `value()` ném `IllegalStateException` ở **Java** trước khi truyền con trỏ cũ sang C.
- `try (counter)` là cú pháp Java 9+ cho biến effectively final; Java 17 hỗ trợ. Sau block, ta vẫn dùng wrapper Java để quan sát trạng thái CLOSED, **không** sử dụng native resource đã giải phóng.

**Giới hạn rõ ràng:** sự đồng bộ ở đây chỉ bảo vệ các lời gọi công khai trên **chính wrapper**. Nếu một native module khác tự giữ/copy raw pointer, hoặc người dùng cố phá encapsulation bằng reflection/Unsafe, JVM không có cách phát hiện pointer cũ. Mẫu này không thay thế native registry có validation/refcount khi handles được chia sẻ hay không đáng tin.

### 5.2. Sinh JNI header

Trong thư mục chứa file Java, với JDK 17 trở lên:

~~~bash
javac -h . NativeCounterDemo.java
~~~

Lệnh này biên dịch `NativeCounterDemo.class`, `NativeCounterDemo$NativeCounter.class` và sinh `NativeCounterDemo.h` từ chữ ký các native methods. Việc dùng `javac -h` giúp tên exported JNI function khớp chính xác khai báo Java; khi thay tên class/package hoặc signature, cần sinh header và build lại thư viện native.

### 5.3. File C: `nativecounterdemo.c`

~~~c
#include "NativeCounterDemo.h"

#include <stdint.h>
#include <stdlib.h>

typedef struct {
    jint value;
} CounterState;

/*
 * Chỉ sử dụng với handle đáng tin, được tạo bởi createNative,
 * chưa bị destroy và được giữ sống bởi một owner duy nhất.
 */
static CounterState *state_from(jlong handle) {
    return (CounterState *)(uintptr_t)(uint64_t)handle;
}

JNIEXPORT jlong JNICALL
Java_NativeCounterDemo_createNative(
        JNIEnv *env, jclass declaringClass, jint initial) {
    (void)declaringClass;

    CounterState *state = malloc(sizeof *state);
    if (state == NULL) {
        jclass errorClass = (*env)->FindClass(
                env, "java/lang/OutOfMemoryError");
        if (errorClass != NULL) {
            (*env)->ThrowNew(
                    env, errorClass, "native malloc failed");
            (*env)->DeleteLocalRef(env, errorClass);
        }
        return (jlong)0;
    }

    state->value = initial;
    return (jlong)(uintptr_t)state;
}

JNIEXPORT jint JNICALL
Java_NativeCounterDemo_readNative(
        JNIEnv *env, jclass declaringClass, jlong handle) {
    (void)env;
    (void)declaringClass;

    CounterState *state = state_from(handle);
    return state->value;
}

JNIEXPORT jint JNICALL
Java_NativeCounterDemo_incrementNative(
        JNIEnv *env, jclass declaringClass, jlong handle) {
    (void)declaringClass;

    CounterState *state = state_from(handle);
    if (state->value == INT32_MAX) {
        jclass errorClass = (*env)->FindClass(
                env, "java/lang/ArithmeticException");
        if (errorClass != NULL) {
            (*env)->ThrowNew(
                    env, errorClass, "counter overflow");
            (*env)->DeleteLocalRef(env, errorClass);
        }
        return (jint)0;
    }

    ++state->value;
    return state->value;
}

JNIEXPORT void JNICALL
Java_NativeCounterDemo_destroyNative(
        JNIEnv *env, jclass declaringClass, jlong handle) {
    (void)env;
    (void)declaringClass;

    CounterState *state = state_from(handle);
    free(state);
}
~~~

**Giải thích từng bước:**

1. `createNative` cấp phát `CounterState` bằng `malloc`. Sau khi phân bổ thành công, C đặt `value` rồi trả handle dưới dạng `jlong`, chuyển quyền sở hữu cho wrapper Java.
2. `readNative` và `incrementNative` chỉ **borrow** con trỏ, không `free`. `readNative` không giữ con trỏ sau khi return; `incrementNative` cập nhật trong lifetime do owner bảo đảm.
3. `incrementNative` kiểm tra `INT32_MAX` để tránh signed integer overflow của `jint` (tương ứng Java `int` 32 bit). Nếu vượt giới hạn, nó ném `ArithmeticException` qua JNI; Java wrapper vẫn **OPEN**, vì phép cộng lỗi không đồng nghĩa native state bị giải phóng.
4. `destroyNative` giải phóng đúng allocation bằng `free`. Với handle này, sau lời gọi ấy mọi lần `readNative`/`incrementNative` sẽ là use-after-free, nên wrapper ngăn gọi lại.
5. Không có `DeleteLocalRef` cho native pointer vì nó không phải JNI object reference. Trong hai nhánh tạo exception, `errorClass` là local JNI reference từ `FindClass` nên được `DeleteLocalRef` đúng loại.
6. `uintptr_t` giúp biểu diễn phép chuyển đổi pointer ↔ integer trên các nền tảng có kiểu integer đủ rộng. **Đây là mô hình triển khai phụ thuộc ABI**: mã này giả định pointer của nền tảng có thể round-trip qua `uintptr_t` và `jlong` 64 bit. Nó không tự động phù hợp với kiến trúc capability-pointer, pointer rộng hơn 64 bit hoặc hệ thống có quy định handle đặc biệt.
7. **Không có bước native validation trong `state_from`.** Nếu đầu vào là số giả mạo, null, handle đã giải phóng hoặc bị sử dụng đồng thời bởi một owner khác, dereference/free có thể gây crash hoặc undefined behavior. Vì thế API Java cố ý không công khai `handle`, và ta cần cơ chế registry nếu muốn bảo vệ khỏi input không đáng tin.

### 5.4. Biên dịch và chạy

Chọn **một** hệ điều hành phù hợp với JVM đang sử dụng. `JAVA_HOME` cần trỏ đến JDK 17+ có JNI headers và kiến trúc tương thích.

**Linux (GCC):**

~~~bash
gcc -std=c11 -Wall -Wextra -fPIC -shared \
  -I"$JAVA_HOME/include" -I"$JAVA_HOME/include/linux" \
  nativecounterdemo.c -o libnativecounterdemo.so

java -Djava.library.path=. NativeCounterDemo
~~~

**macOS (Clang):**

~~~bash
clang -std=c11 -Wall -Wextra -dynamiclib \
  -I"$JAVA_HOME/include" -I"$JAVA_HOME/include/darwin" \
  nativecounterdemo.c -o libnativecounterdemo.dylib

java -Djava.library.path=. NativeCounterDemo
~~~

**Windows (MSVC Developer Command Prompt):**

~~~bat
cl /LD /I "%JAVA_HOME%\include" /I "%JAVA_HOME%\include\win32" nativecounterdemo.c /Fe:nativecounterdemo.dll
java -Djava.library.path=. NativeCounterDemo
~~~

Các lệnh trên dựa vào `System.loadLibrary("nativecounterdemo")` và tên file thông thường của JVM trên từng OS. Trên Windows phải dùng Developer Command Prompt có cấu hình `cl`. File native phải đúng kiến trúc **tiến trình JVM**, C runtime và các thư viện phụ thuộc; nếu sai, bạn có thể gặp `UnsatisfiedLinkError` ngay lúc load, trước mọi output.

### 5.5. Output mong đợi

Khi compilation, loading và execution thành công:

~~~text
before=5
afterIncrement=6
afterRead=6
closed=true
closedTwice=true
afterClose=NativeCounter is closed
~~~

Từ kết quả:

- Counter bắt đầu ở 5, increment tăng lên 6, đọc lại vẫn là 6.
- Rời `try` gọi `close` → handle trở thành `0L` và native state được giải phóng.
- Gọi `close` lần nữa là no-op ở wrapper, không `free` lần thứ hai.
- Sau close, `value` ném `IllegalStateException` từ Java **trước** khi gọi JNI, tránh sử dụng pointer đã hết hiệu lực.

Đây là output logic xác định cho **mã mẫu đúng môi trường**; không coi stdout là bằng chứng có thể chống mọi lỗi lifetime trong một ứng dụng phức tạp. Với memory safety, cần kiểm tra resource ownership và các đường chạy khác, kể cả concurrency.

## 6. Sai lầm nghiêm trọng: hai wrappers cùng sở hữu một handle

Giả sử bằng cách nào đó hai Java objects giữ cùng một pointer:

~~~text
Java wrapper A ---> 0xABC ---> C resource R
Java wrapper B ---/

A.close()  ---> free(R)
B.value()  ---> dereference freed R    (use-after-free)
B.close()  ---> free(R) lần nữa         (double free)
~~~

**Không sửa** bằng `if (handle != 0)` ở mỗi wrapper: khi `A` đặt *field của A* thành zero, *field của B* vẫn giữ số cũ. Trạng thái của hai wrappers không được liên kết.

Có ba cách xử lý đúng, tùy hợp đồng:

1. **Unique owner:** không cho phép tạo B từ cùng resource. Nếu chuyển A → B, phải bảo đảm thao tác transfer hủy quyền của A và cấp quyền mới cho B một cách nguyên tử theo mô hình dùng.
2. **Shared ownership:** native object có reference count hoặc shared control block. Mỗi wrapper nhận một **quyền retain độc lập**, và `close` của từng wrapper chỉ release quyền của mình; lần release cuối mới hủy resource.
3. **Borrowed view:** B không bao giờ được destroy. B chỉ dùng khi owner A còn sống và có lease/lock phù hợp; sau A.close, B không được truy cập. Không dựa đơn thuần vào một `long` copy để kiểm tra điều này.

Nếu API của SDK trả `getHandle()` nhưng tài liệu nói “do thư viện sở hữu, đừng free”, đó là **borrowed handle** dù được biểu diễn bằng pointer. Đừng gắn `Cleaner` tự động `free` vào giá trị này.

## 7. Close đồng thời với operation: vì sao phải có đồng bộ hóa?

Mã sau là **phản ví dụ**:

~~~java
public int value() {
    if (handle == 0L) {
        throw new IllegalStateException("closed");
    }
    return readNative(handle);
}

public void close() {
    if (handle != 0L) {
        destroyNative(handle);
        handle = 0L;
    }
}
~~~

Nếu thread T1 vừa kiểm tra handle hợp lệ, T2 có thể xen vào `destroyNative`, rồi T1 gọi `readNative` với pointer đã free. Ngoài ra, hai lần `close` đồng thời có thể cùng thấy nonzero và gọi destroy hai lần. Đây là **anti-pattern Java minh họa**, không phải mã được phép đưa vào sản phẩm.

### Lời giải cho mẫu wrapper duy nhất

Trong ví dụ chạy đầy đủ, `value`, `increment` và `close` đều `synchronized` trên cùng Java object, do đó:

~~~text
T1 vào synchronized value()
    ---> readNative(handle) hoàn thành
    ---> T1 rời monitor

T2 vào synchronized close()
    ---> handle = 0
    ---> destroyNative(old)
    ---> T2 rời monitor
~~~

Hoặc T2 có thể vào trước T1; khi ấy T1 thấy handle zero và ném lỗi. **Không có thứ tự thứ ba** trong đó một thread đóng resource giữa lời gọi native của thread kia, miễn là mọi đường truy cập cùng resource đều đi qua cùng wrapper/monitor và native method không đưa handle cho tác nhân độc lập.

Chỉ thêm `volatile long handle` **không đủ**: volatile giúp visibility/order của đọc ghi field nhưng không giữ resource sống suốt khoảng `readNative`. `AtomicLong.getAndSet(0)` có thể ngăn hai close cùng free, nhưng **không tự ngăn** operation đã đọc handle cũ rồi bị close chen ngang. Cần lock, refcount/lease hoặc registry thực sự quản lý in-flight usages.

### Khi JVM callback ngược Java trong lúc native operation

Java monitor là **reentrant**. Nếu native operation gọi ngược vào một Java method khác có thể `close()` cùng owner trên **chính thread đó**, monitor có thể được lấy lại và resource bị đóng **ngay giữa native call**. Mẫu `synchronized` đơn giản phía trên an toàn vì `readNative`/`incrementNative` là leaf operations, **không callback** và không xuất handle.

Với native API có callback/reentrant logic, cần thêm trạng thái `inUse`/`closing`, lease hoặc native-side reference count; đóng phải bị hoãn cho đến khi mọi in-flight borrow hoàn tất. **Không** giả định synchronized giải quyết mọi kiểu reentrancy.

### Dùng nhiều wrappers hoặc threads ngoài Java

Một native handle được truy cập qua registry toàn process, C thread riêng, background worker hoặc callback có thể vượt khỏi phạm vi monitor của wrapper. Khi đó việc khóa ở wrapper A **không bảo vệ** wrapper B hay C thread khác. Thiết kế sở hữu native phải cùng tham gia đồng bộ hóa ở nơi tài nguyên thực sự được sử dụng.

## 8. Native registry và token thế hệ: khi nào tốt hơn raw pointer?

`jlong` không nhất thiết chứa pointer. Với thư viện yêu cầu kiểm soát tính hợp lệ ở native boundary, một lựa chọn là bảng registry:

~~~text
Java:
  long token = 0x0007_0000002A   (ví dụ mã hóa, không phải địa chỉ)

Native registry (được khóa/đồng bộ):
  slot 42; generation 7 ---> CounterState*
  slot 43; generation 2 ---> FileState*

nativeRead(token):
  decode slot=42, generation=7
  acquire protected lease / retain
  validate active + correct resource type
  use CounterState
  release lease

nativeDestroy(token):
  mark slot 42 closing/closed, invalidate token
  wait/defer until all in-flight leases end
  release resource đúng một lần
~~~

Đây là **sơ đồ ý tưởng**, không phải code độc lập hay định dạng token chuẩn. Một registry thực tế cần:

- Có kiểm tra loại tài nguyên và quyền truy cập; không cho `FileHandle` bị dùng như `CounterHandle`.
- Có generation để token cũ không trỏ nhầm resource mới khi slot được tái sử dụng (**ABA/stale handle**).
- Bảo vệ lookup → use bằng lock/lease/refcount đồng bộ với destroy; chỉ check token rồi nhả lock **trước** dereference thì vẫn có race.
- Có kế hoạch khi generation counter bị wrap, khi process reload và khi library/classloader unload.
- Có quy định rõ ownership transfer, retain và release; không chỉ thêm bảng mà bỏ qua vòng đời.
- Không lấy token từ input ngoài tin cậy rồi coi nó là quyền được dereference một raw pointer bất kỳ.

**Lợi ích:** có thể trả lỗi “invalid/stale handle” thay vì dereference địa chỉ sai. **Chi phí:** lookup và synchronization overhead, cấu trúc registry cần quản lý memory, refcount, shutdown.

Với một wrapper nội bộ ít thao tác, raw pointer + unique owner có thể đủ. Với API công khai, plugin system, nhiều owners hoặc concurrency phức tạp, registry/opaque ID thường dễ kiểm soát hơn.

## 9. Ownership transfer: không được để lại hai owners sau khi “move”

Một factory có thể tạo native resource ở C, sau đó giao ownership cho Java. Hợp đồng đúng là:

~~~text
Native create():
  allocate R
  |
  +-- thất bại khi chuẩn bị: native free(R)
  |
  +-- chuyển ownership thành công:
           Java wrapper sở hữu R
           native factory KHÔNG free(R) nữa
~~~

Nếu một API native chuyển handle từ wrapper A sang B, phải vô hiệu hóa A và chỉ cho phép B destroy. Việc transfer phải được đồng bộ với các borrow còn hoạt động. **Không** viết `new Wrapper(a.handle)` rồi để cả hai wrapper `close`.

Một pattern an toàn hơn là factory Java nhận handle và lập tức gán vào một owner có phạm vi rõ; nếu quá trình xây wrapper Java còn bước có thể ném lỗi sau native allocation, cần `try/finally` hoặc transaction tách biệt:

~~~java
long acquired = createNative(5);
boolean transferred = false;
try {
    NativeCounter wrapper = adoptOwned(acquired);
    transferred = true;
    return wrapper;
} finally {
    if (!transferred && acquired != 0L) {
        destroyNative(acquired);
    }
}
~~~

Đây là **mảnh minh họa** cho quy trình factory (giả định `adoptOwned` tồn tại, kiểm tra preconditions và **không tự destroy handle khi báo lỗi**). Nếu factory phân phối resource sang nơi khác rồi ném exception sau đó, cách đặt cờ `transferred` phải phản ánh đúng thời điểm chuyển quyền; một đoạn code không thể thay thế ownership protocol đã định nghĩa.

**Ghi rõ semantics ở mỗi API**: các tên như `borrow`, `retain`, `adoptOwned`, `detachOwned`, `release` thường truyền đạt lifetime tốt hơn một hàm chung chung `fromHandle`. Tên vẫn phải đi cùng tài liệu và test.

## 10. `Cleaner` là phương án dự phòng, không phải vòng đời chính

Java GC chỉ quản lý Java heap. Nếu code bỏ quên `close()` và wrapper không còn reachable, native state có thể tồn tại cho đến khi process kết thúc. Một `Cleaner` có thể đăng ký hành động release resource khi JVM phát hiện referent phantom-reachable. Tuy nhiên:

- **Không xác định khi nào, hoặc liệu, cleaning action có chạy trước khi process thoát.** Vì vậy `Cleaner` không thay thế `AutoCloseable`.
- Cleaning action **không được giữ strong reference đến chính owner**, nếu không owner không thể trở thành phantom-reachable. Tránh lambda kiểu `() -> this.close()` hoặc inner class non-static vô tình capture `this`.
- Explicit `cleanable.clean()` cho phép trigger action khi `close`, nhưng action phải chống gọi hai lần bằng logic ownership hợp lệ.
- Cleaner có thể chạy trên thread khác với method của wrapper; operation và cleaner destroy cần đồng bộ hóa/lease chung.
- Không nên giả định mọi native destructor đều an toàn khi chạy ở cleaner thread: một số thư viện yêu cầu destruction trên thread, UI context hay event loop cụ thể.
- Nếu Cleaner action gọi JNI static native method từ Java, việc load library và thread context phải hợp lệ. Một native pointer không mang tự động JNI environment cho thread tùy ý.

### Minh họa cơ chế state riêng cho Cleaner

~~~java
import java.lang.ref.Cleaner;

final class ResourceOwner implements AutoCloseable {
    private static final Cleaner CLEANER = Cleaner.create();

    private static final class State implements Runnable {
        private long handle;

        State(long handle) {
            this.handle = handle;
        }

        synchronized long requireOpen() {
            if (handle == 0L) {
                throw new IllegalStateException("closed");
            }
            return handle;
        }

        @Override
        public synchronized void run() {
            if (handle != 0L) {
                long old = handle;
                handle = 0L;
                nativeDestroy(old);
            }
        }
    }

    private static native void nativeDestroy(long handle);

    private final State state;
    private final Cleaner.Cleanable cleanable;

    ResourceOwner(long ownedHandle) {
        if (ownedHandle == 0L) {
            throw new IllegalArgumentException("invalid handle");
        }
        state = new State(ownedHandle);
        cleanable = CLEANER.register(this, state);
    }

    @Override
    public void close() {
        cleanable.clean();
    }
}
~~~

**Đây là đoạn mẫu riêng về cấu trúc Cleaner, chưa phải chương trình độc lập**: cần định nghĩa/load native library và có một factory cấp `ownedHandle` hợp lệ; tuyệt đối không truyền số tự đặt vào `nativeDestroy`. `State` không giữ reference tới `ResourceOwner`, giúp tránh vòng tham chiếu strong từ cleaning action về owner. Việc `run()` synchronized ngăn hai lần cleanup đồng thời trên cùng state; một method dùng resource **cũng phải đồng bộ trên cùng State trong suốt native call** nếu muốn an toàn với Cleaner.

`requireOpen()` chỉ trả raw handle sau khi thả monitor của `State`: **không đủ** để bảo vệ call native diễn ra sau đó trước khi Cleaner chạy. Muốn có `read()` thực sự, hãy thiết kế `synchronized int read() { check; return nativeRead(handle); }` **bên trong State**, hoặc dùng lease/refcount. Mục đích của đoạn Cleaner trên là minh họa state tách khỏi referent và quyền release một lần, **không** phải chứng minh mẫu đầy đủ đã thread-safe cho mọi operation.

Với Java 17, `Cleaner` là cơ chế dự phòng được hỗ trợ. Không dùng finalizer `finalize()` để làm hợp đồng native lifecycle: finalization không xác định thời điểm và có nhiều rủi ro về an toàn/bảo trì. Nếu resource quý hiếm, thiết kế `close` tường minh và giám sát leak mới là ưu tiên.

### Khi nào cần `Reference.reachabilityFence`?

Nếu code trích raw pointer ra khỏi Java owner rồi sử dụng nó trong một thao tác không giữ tham chiếu tới owner đủ lâu, JIT/GC có thể coi owner không còn reachable trước khi native use hoàn tất; Cleaner khi đó có thể chạy sớm. `Reference.reachabilityFence(owner)` là một công cụ giúp giữ đối tượng reachable tới một điểm xác định, nhưng **không thay thế synchronization/lease** khi người khác có thể gọi `close()` rõ ràng.

Trong ví dụ `NativeCounterDemo`, các synchronized instance methods giữ monitor của chính owner xuyên suốt lời gọi native, nên vấn đề sớm-dọn qua Cleaner không phát sinh (và ví dụ chính không sử dụng Cleaner). Ở API dùng asynchronous native work hay external callbacks, phải thiết kế quyền giữ sống riêng theo thời hạn công việc.

## 11. JNI global references và native handle là hai nghĩa vụ độc lập

Giả sử native resource giữ reference tới một Java callback để gọi về sau:

~~~c
/* Trước lúc có lỗi/pending exception, trong hàm tạo. */
jobject saved_callback = (*env)->NewGlobalRef(env, callback);

/* Khi hủy resource, nếu callback reference đã được sở hữu: */
(*env)->DeleteGlobalRef(env, saved_callback);
~~~

Đây là **các dòng JNI minh họa** trong hàm C có biến `env`/`callback` hợp lệ. `NewGlobalRef` có thể thất bại; cần kiểm tra `NULL`. Khi tạo callback global ref thành công, native state sở hữu **hai loại** tài nguyên:

1. Bộ nhớ native chứa struct.
2. JNI global reference dùng để giữ một Java object reachable qua nhiều JNI calls.

Destructor đúng có thể phải `DeleteGlobalRef` rồi `free` struct. Chỉ `free` struct sẽ **rò rỉ global reference**; chỉ `DeleteGlobalRef` mà quên `free` sẽ rò rỉ native memory.

Cần lưu ý:

- `jobject` local reference tạo trong native method không được cache để sử dụng ở callback/call tiếp theo; nếu cần lưu dài hạn, dùng `NewGlobalRef` và `DeleteGlobalRef`.
- Global ref có thể giữ Java object sống ngoài ý muốn; đối tượng đó có thể giữ lại những resource khác, tạo leak lớn.
- Weak global ref không thay cho owning reference; cần kiểm tra khả năng object đã được GC và nâng thành local reference hợp lệ nếu muốn dùng.
- `JNIEnv*` gắn với thread; một native thread khác cần attach đúng cách để dùng JNI, rồi detach khi thích hợp; không giữ env pointer xuyên thread.
- `DeleteGlobalRef` được phép khi Java exception đang pending; nhưng phần lớn JNI method khác **không được phép** trong trạng thái đó. Thiết kế destructor/cleanup để không gọi thêm JNI tùy tiện khi còn pending exception.

Đừng nhầm `jlong` là “reference Java lâu dài”: nó chỉ là một token nguyên thủy và **GC không thể giữ native state sống dựa vào pointer số học**.

## 12. Exception safety: một tài nguyên chỉ có một đường cleanup

Khởi tạo có thể gồm nhiều bước:

~~~text
malloc struct              OK
nativeOpenSocket           OK
NewGlobalRef(callback)     FAIL
Java wrapper chưa nhận handle
~~~

Ai phải đóng socket và `free` struct? **C factory**, vì chưa hoàn tất ownership transfer cho Java. Java `close` không thể dọn một tài nguyên mà nó chưa nhận.

Một khung C đơn giản:

~~~c
NativeState *state = NULL;
jobject callback_global = NULL;

/* state = malloc(...); */
/* if (state == NULL) ... goto cleanup; */

/* state->socket = native_open(...); */
/* if (socket invalid) ... goto cleanup; */

/* callback_global = (*env)->NewGlobalRef(env, callback); */
/* if (callback_global == NULL) goto cleanup; */

/* Khi tất cả thành công: gắn vào state, chuyển ownership. */
/* return (jlong)(uintptr_t)state; */

cleanup:
    if (callback_global != NULL) {
        (*env)->DeleteGlobalRef(env, callback_global);
    }
    if (state != NULL) {
        /* Đóng socket nếu đã mở, rồi free(state). */
    }
    return (jlong)0;
~~~

Đây là **khung minh họa, không phải C function độc lập**: kiểu `NativeState` và `native_open` chưa được định nghĩa. Điểm quan trọng là mỗi giai đoạn acquire có cờ/field đánh dấu trạng thái đủ để cleanup các phần thành công, kể cả khi giai đoạn sau lỗi.

Nếu một JNI call đã đặt pending Java exception, cleanup JNI phải giới hạn ở những thao tác được phép (chẳng hạn `DeleteGlobalRef` hoặc các `Release...` tương ứng). Không tự ý `FindClass`/`ThrowNew` thêm khi exception vẫn pending. Tài nguyên native do C sở hữu vẫn có thể dọn bằng các hàm C/OS thích hợp.

### Close thất bại thì sao?

Trong ví dụ chính, `nativeDestroy` gọi `free` với pointer hợp lệ và không có cơ chế báo lỗi. Thực tế `closeNative` có thể cần flush file, gửi dữ liệu, đóng kết nối, giải phóng GPU context hoặc gọi SDK destructor có thể thất bại.

Quyết định hợp đồng:

- Đóng là **best-effort** hay bảo đảm giải phóng?
- Sau lỗi cleanup, handle đã bị hủy hay còn hợp lệ?
- Được retry không, retry có thể gây double-free không?
- Lỗi đóng được báo với caller bằng exception, status hay log?
- Khi `try-with-resources` có lỗi từ thân `try` **và** `close` ném lỗi, Java sẽ xử lý suppression theo cơ chế của nó; đừng nuốt lỗi đóng mà không có chính sách.

Nếu destructor có thể thất bại mà tài nguyên vẫn sống, `handle=0` trước khi destroy (như mẫu) có thể khiến retry không thực hiện được. Khi đó cần state machine `OPEN → CLOSING → CLOSED/FAILED` hoặc một native release protocol idempotent, **không sao chép nguyên mẫu `free` sang các loại resource này**.

## 13. Handle hết hiệu lực, bảo mật và ABI

### Không coi raw pointer là một mã số an toàn

Một `jlong` chứa địa chỉ thật là dữ liệu đặc biệt nhạy cảm với các giả định nội bộ: nếu người gọi cung cấp `0x12345678` hoặc pointer đã free rồi JNI dereference, chương trình có thể crash. **Pointer không có runtime tag** cho Java biết nó còn sống hoặc thuộc loại struct nào.

Không đưa raw native address vào network protocol, database, serialized Java object hoặc log công khai như một ID ổn định. Khi process restart, ASLR đổi bố cục address space và con trỏ cũ không còn ý nghĩa. Nếu cần persistent ID, thiết kế ID nghiệp vụ độc lập với pointer.

### Kiểu dữ liệu và nền tảng

- `jlong` luôn tương ứng Java `long` 64 bit. Native pointer có thể khác độ rộng; `uintptr_t` tồn tại ở các nền tảng hỗ trợ một unsigned integer đủ chứa pointer.
- Việc chuyển đổi pointer ↔ integer có tính phụ thuộc triển khai/ABI, không phải một phép chứng minh tuyệt đối cho mọi loại con trỏ.
- Không ép `jobject` thành `jlong` rồi dùng như `malloc` pointer; JNI references là opaque và có lifetime riêng do JVM quản lý.
- Một thư viện JNI phải được build đúng OS/CPU/ABI của JVM, có allocator/deallocator tương ứng. Không trả pointer do C++ `new` rồi giải phóng qua C `free`.
- Không dùng cùng `long` cho nhiều loại resource mà không có type check. Một token sai loại có thể dẫn đến cast và destructor sai.

### Tránh ABA và giải phóng lặp

Sau `free(R)`, allocator có thể tái sử dụng cùng địa chỉ cho resource mới. Một stale `long` mang bit địa chỉ của R có thể bỗng trỏ tới object khác — lỗi **ABA**. So sánh bằng giá trị pointer để phát hiện stale handle không đủ. Registry token có generation và invalidation, cộng lock/refcount, là thiết kế thường phù hợp hơn khi có bất kỳ đường nào lưu handle lâu hoặc chia sẻ.

## 14. Giao thức Java–native cần đồng nhất về đóng

Một ví dụ hợp đồng API rõ:

| API | Input ownership | Output ownership | Hiệu ứng |
|---|---|---|---|
| `nativeCreate(int)` | Không có handle đầu vào | Trả **owned** handle mới, hoặc báo lỗi | C tạo native state; Java nhận quyền sở hữu |
| `nativeRead(long)` | **Borrowed** handle đang OPEN | Trả giá trị Java primitive | Không giữ handle sau return |
| `nativeIncrement(long)` | **Borrowed** handle đang OPEN | Trả giá trị | Không destroy hoặc retain |
| `nativeDestroy(long)` | **Consumes owned** handle | Không có handle đầu ra | Hủy đúng một resource, handle cũ invalid |
| `NativeCounter.close()` | Wrapper sở hữu handle | Không chuyển handle | Đưa wrapper về CLOSED, gọi destroy tối đa một lần |
| `NativeCounter.value()` | Không công khai handle; borrow nội bộ | Trả `int` | Ném `IllegalStateException` nếu CLOSED |

Một số quy ước nên được ghi rõ trong JavaDoc của thư viện:

> **Thread-safety:** Tất cả method instance thao tác handle được đồng bộ trên cùng wrapper. Không cung cấp raw handle cho native code bất đồng bộ hoặc wrapper khác. Cách này không đủ cho native callbacks có thể tái nhập hoặc hệ thống có nhiều owners.

> **Lifetime:** Resource được giải phóng khi `close` thành công; caller phải dùng `try-with-resources`. Không bảo đảm native resource được dọn nếu caller bỏ quên `close` trong thiết kế không có Cleaner.

> **Failure:** `createNative` thất bại không trả owner sử dụng được; `readNative`/`incrementNative` không consume ownership. `nativeDestroy` trong bản demo chỉ giải phóng cấp phát từ `malloc` và không báo lỗi; backend khác phải có contract riêng.

> **Invalidation:** Sau `close`, mọi operation ngoài `isClosed`/`close` trên wrapper ném lỗi trước khi gọi JNI. Các bản sao handle ngoài wrapper (nếu có) **không được bảo vệ** bởi quy tắc này.

Ghi hợp đồng ở cả hai phía code review, không chỉ đặt comment ở field `handle`.

## 15. Kiểm thử vòng đời và concurrency

Một bài kiểm thử ownership không chỉ kiểm tra “tạo được và gọi được”. Cần kiểm thử các luồng sau:

| Test | Kết quả đúng |
|---|---|
| Tạo một resource rồi đọc/ghi | Operation được thực thi khi OPEN |
| `try-with-resources` kết thúc bình thường | `close` gọi một lần, state thành CLOSED |
| Thân `try` ném Java exception | `close` vẫn được gọi theo cơ chế ngôn ngữ |
| Gọi `close` hai hoặc nhiều lần | Không double-free; các lần sau no-op hoặc theo hợp đồng riêng |
| Gọi `value` sau `close` | Lỗi Java rõ, không dereference stale pointer |
| Hai Java threads gọi `value` và `close` đồng thời | Với wrapper đồng bộ: hoặc value hoàn thành trước close, hoặc thấy CLOSED; không UAF |
| Native constructor/acquire thất bại giữa chừng | Mọi resource đã acquire được cleanup, không có owner nửa vời |
| Native operation ném Java exception | Ownership không bị destroy ngoài ý muốn; vẫn có đường cleanup hợp lệ |
| Copy cùng handle vào hai owner độc lập | Phải bị cấm hoặc xử lý bởi registry/refcount; không bao giờ hai destroy cho cùng resource |
| GC xảy ra khi resource còn OPEN | Không dựa vào GC để xác định thời điểm native resource free |
| Có `Cleaner` fallback | Không giữ owner sống do capture; action được thiết kế đúng thread/lease; explicit close là chính |
| Callback/reentrant close | Có cơ chế cấm/hoãn close khi native đang borrow, không tự do free giữa call |
| Native library unload/shutdown | Không còn resource/callback đang dùng code hoặc global state của library bị unload |

### Cách theo dõi allocation và release

Ở môi trường test, có thể thêm bộ đếm **native** và kiểm tra số lượng resource đang sống sau một vòng chạy, hoặc dùng AddressSanitizer/Valgrind/leak detector phù hợp nền tảng. Với debug build, một registry có thể log token, loại resource, owner và trạng thái OPEN/CLOSED, **không cần log raw pointer ra môi trường sản xuất**.

Một phép thử `System.gc()` **không** chứng minh Cleanup chắc chắn xảy ra, bởi GC và Cleaner không cam kết thời điểm. Kiểm thử chức năng cần chủ động gọi `close`. Test Cleaner chỉ kiểm tra phương án dự phòng với giả định thời điểm không xác định, không biến nó thành hợp đồng chính.

Với HotSpot, `-Xcheck:jni` giúp tìm một số lỗi JNI misuse (reference sai, exception pending...) nhưng **không thay thế** sanitizer cho heap C hoặc chứng minh tính đúng đắn của ownership/lock.

## 16. Các lỗi thường gặp và sửa thế nào?

| Triệu chứng | Nguyên nhân thường gặp | Hướng khắc phục |
|---|---|---|
| Java object biến mất nhưng native memory vẫn tăng | Chỉ GC Java object, không `nativeDestroy` | `AutoCloseable`, `try-with-resources`, đo leak; Cleaner chỉ fallback |
| Crash sau `close()` | JNI vẫn dùng handle cũ | Kiểm tra OPEN và đồng bộ operation/close; native lease |
| Double-free | Hai owners cùng gọi destroy hoặc close không idempotent | Chỉ một owner hoặc explicit retain/release; đóng một lần |
| Java field handle đã zero nhưng native thread vẫn dùng pointer | Native work bất đồng bộ đang chạy | Chờ/hoãn destroy tới khi in-flight usages hoàn tất |
| `volatile long handle` vẫn UAF | Visibility không giữ lifetime suốt JNI call | Lock/refcount/lease |
| Global JNI references rò rỉ | Native struct chứa `NewGlobalRef` nhưng destructor chỉ `free` | `DeleteGlobalRef` rồi giải phóng struct đúng quy tắc |
| C++ resource hủy bằng `free` | Sai allocator/deallocator | Dùng `delete`/SDK destroy tương ứng |
| Handle có vẻ hợp lệ nhưng trỏ nhầm object mới | Địa chỉ/registry slot được tái dùng (ABA) | Generation token/registry và validation |
| Wrapper bị GC giữa thao tác nền | Ownership không giữ object/resource sống đến khi xong | Strong reference/lease/reachability fence tùy thiết kế |
| Cleaner chạy ở thread không phù hợp | Destructor yêu cầu UI/thread-affine context | Explicit close hoặc dispatch cleanup đến thread được phép |
| Constructor Java ném sau native allocation | Transfer chưa hoàn tất, resource không được release | Factory với `finally` và ownership commit rõ ràng |
| C gọi Java khi đã pending exception trong destructor | Cleanup có thêm JNI API không được phép | Phân tách cleanup cho phép và xử lý exception có chủ đích |

## 17. Bài tập tự kiểm tra

**Bài 1 — ai sở hữu?** Một C API trả `FILE*` được mở bởi factory. Java wrapper giữ số địa chỉ dưới dạng `long`. Khi trả về Java thành công, ai đóng file? **Owner được ghi trong API contract**, thường là wrapper qua `close` và JNI destroy dùng `fclose` (không phải `free` trực tiếp đối với `FILE*`).

**Bài 2 — borrowed handle.** Native method `getInternalHandle()` trả pointer tới state thuộc owner A. Java B lưu handle và gọi nativeDestroy khi hết dùng. Sai ở đâu? **B chỉ borrow, không được destroy**. Để dùng lâu hơn cần explicit retain hoặc giao thức bảo đảm A vẫn sở hữu và sống trong toàn bộ thời hạn mượn.

**Bài 3 — double close.** Vì sao `if (handle != 0) { destroyNative(handle); handle = 0; }` không an toàn trong hai thread nếu không có đồng bộ? Hai thread có thể cùng đọc nonzero và cùng destroy. Cách sửa: `synchronized`/lock hoặc cơ chế state transition nguyên tử phối hợp với lifetime của operation.

**Bài 4 — race đọc/đóng.** Atomic `getAndSet(0)` trong close đã đủ chưa? **Chưa** nếu operation trước đó đã đọc handle rồi đang chạy hoặc sắp vào JNI. Cần lease/lock giữ resource sống tới khi operation hoàn tất.

**Bài 5 — raw handle.** Vì sao không cho client truyền một số `long` bất kỳ đến `nativeRead`? Vì có thể bị cast thành pointer không hợp lệ và dereference gây crash; cần encapsulation và, nếu input không đáng tin, registry lookup có kiểm tra token/type/lifetime.

**Bài 6 — Cleaner.** Viết `CLEANER.register(this, () -> this.close())` có gì nguy hiểm? Action capture `this` bằng strong reference, có thể ngăn owner trở nên phantom-reachable. Hãy dùng `static State` tách khỏi owner và `cleanable.clean()` khi close tường minh.

**Bài 7 — resource kép.** Native struct có `jobject callbackGlobal` từ `NewGlobalRef` và một buffer `malloc`. Destroy phải làm gì? **`DeleteGlobalRef`** đúng môi trường JNI và **`free`** buffer/struct đúng allocator. Đây là hai quyền sở hữu độc lập.

**Bài 8 — failed close.** Nếu native SDK `destroy` có thể thất bại mà resource chưa được giải phóng, có nên luôn đặt handle về 0 trước khi gọi không? Không mặc nhiên. Cần xác định trạng thái sau lỗi, quy tắc retry hoặc native idempotence. Mẫu trong bài áp dụng cho `free` không báo lỗi.

## Tài liệu tham chiếu

- [Java SE 17 — JNI Functions](https://docs.oracle.com/en/java/javase/17/docs/specs/jni/functions.html): JNI references, Java/native method invocation, exception handling và global/local refs.
- [Java SE 17 — JNI Design: Global and Local References](https://docs.oracle.com/en/java/javase/17/docs/specs/jni/design.html): lifecycle và phạm vi của JNI references.
- [Java SE 17 — AutoCloseable](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/AutoCloseable.html): contract đóng resource tường minh.
- [Java SE 17 — Cleaner](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ref/Cleaner.html): cách đăng ký cleaning action, trạng thái và các hạn chế GC.
- [Java SE 17 — Reference.reachabilityFence](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ref/Reference.html#reachabilityFence(java.lang.Object)): giữ referent reachable tới một điểm chương trình.
- [Java SE 17 — try-with-resources (JLS `14.20.3)](https://docs.oracle.com/javase/specs/jls/se17/html/jls-14.html#jls-14.20.3): close, exception và suppressed exceptions.

## Ghi nhớ

**Native handle là một giá trị opaque, không phải một đối tượng tự quản lý vòng đời.** Đối tượng Java giữ handle phải có **hợp đồng ownership**: tạo, mượn, chuyển giao, release, đồng bộ và xử lý lỗi.

- **Unique owner:** một wrapper chịu trách nhiệm destroy đúng một lần; `close()` idempotent, mọi method kiểm tra OPEN.
- **Borrowed handle:** không được destroy, không giữ quá lifetime của owner/lease.
- **Shared handle:** phải có retain/release hoặc refcount/registry; copy `long` không tạo ownership.
- **Concurrency:** phải giữ tài nguyên sống cho toàn bộ native operation; volatile/atomic check riêng lẻ không đủ chống use-after-free.
- **GC và Cleaner:** GC không tự giải phóng `malloc` chỉ vì Java `long` biến mất; `AutoCloseable` và `try-with-resources` mới là cơ chế đóng chủ động. Cleaner chỉ là fallback không có thời hạn bảo đảm.
- **JNI references khác native pointers:** `DeleteGlobalRef` giải phóng JNI root, `free`/`delete`/SDK release giải phóng native resource. Nếu một object sở hữu cả hai, phải cleanup cả hai đúng cách.

Thiết kế một hợp đồng rõ ràng trước khi viết JNI: **ai sở hữu tài nguyên ở từng thời điểm và ai được quyền kết thúc lifetime của nó**. Đó là cơ sở để tránh leak, double-free và use-after-free.
