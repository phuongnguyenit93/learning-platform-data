# Điều kiện nghiêm ngặt của `Linker.Option.critical` và hạn chế với hàm chặn hoặc upcall

## 1. Mục tiêu và phạm vi

`Linker.Option.critical(boolean allowHeapAccess)` thuộc Foreign Function & Memory API (FFM) trong `java.lang.foreign`. Đây là tùy chọn khi tạo **downcall handle** để JVM có thể tối ưu đường chuyển từ Java sang hàm native. Trong bài này, “critical” nghĩa là **hợp đồng cực kỳ chặt về hành vi của hàm native được gọi**, không đồng nghĩa với khóa `synchronized`, Java critical section hay một cơ chế tự động tăng tốc.

Sau bài học, bạn cần biết:

- Chỉ ra **hai điều kiện bắt buộc** theo đặc tả: native function chạy cực ngắn **trong mọi trường hợp** (tương tự hàm rỗng) và **không gọi ngược về Java**, kể cả qua FFM upcall stub.
- Hiểu `critical(false)` và `critical(true)` khác nhau ở quyền truyền **heap memory segment** làm con trỏ native, không phải “ít critical” và “nhiều critical”.
- Giải thích vì sao hàm có thể **blocking** (I/O, chờ khóa, sleep, đợi callback, chờ kết quả từ thread khác) hoặc thực hiện **upcall vào Java** không được đánh dấu critical.
- Tạo một downcall critical hợp lệ; tạo một downcall thường có upcall; xác định trường hợp phải bỏ `critical` dù hàm trông có vẻ “nhanh”.
- Phân biệt tối ưu hóa theo triển khai JVM với những gì API bảo đảm; biết hậu quả của khai báo sai: hiệu năng giảm, hành vi không an toàn hoặc JVM crash.

**Phiên bản sử dụng:** API FFM chính thức có từ JDK 22 (JEP 454); ví dụ được viết theo **JDK 25**, không dùng preview flag. Các ví dụ biên dịch native bên dưới dành cho **Linux x86-64**, nơi C `int` thông thường là 32 bit. Trên nền tảng/ABI khác phải kiểm tra lại layout, export symbol và lệnh linker.

## 2. Downcall, upcall và tùy chọn critical

**Downcall:** Java gọi một địa chỉ hàm native bằng `MethodHandle` do `Linker.downcallHandle(...)` tạo. JVM phải thực hiện các bước thích hợp tại ranh giới Java/native, ví dụ chuẩn bị tham số ABI và chuyển trạng thái luồng; cách thực hiện chính xác thuộc JVM.

**Upcall:** C/C++ gọi vào Java thông qua một function pointer được tạo từ `Linker.upcallStub(...)`. Callback Java chạy trong khi lời gọi native còn hiệu lực. Upcall cần chuyển trở lại runtime Java và có thể kích hoạt những hoạt động mà đường critical không được giả định là an toàn.

Một lời gọi thông thường có hình dạng:

```java
MethodHandle normal = linker.downcallHandle(
    targetAddress,
    FunctionDescriptor.of(ValueLayout.JAVA_INT, ValueLayout.JAVA_INT)
);
```

Một lời gọi được khai báo critical:

```java
MethodHandle critical = linker.downcallHandle(
    targetAddress,
    FunctionDescriptor.of(ValueLayout.JAVA_INT, ValueLayout.JAVA_INT),
    Linker.Option.critical(false)
);
```

Hai đoạn trên là **trích đoạn minh họa**, giả sử `linker` và `targetAddress` đã được tạo. `critical(...)` là **option khi liên kết**, không phải một phương thức gọi native và không làm thay đổi C function signature. Để runnable, xem chương trình đầy đủ ở mục 6.

Theo Javadoc, critical là **gợi ý tối ưu hóa** cho một số implementation. JVM có thể tận dụng giả định rất mạnh rằng hàm native kết thúc gần như tức thì và không quay lại Java. **Không có lời hứa chắc chắn về tốc độ**, không có bộ đo timeout tự động và không có bảo đảm JVM sẽ bắt mọi trường hợp bạn khai báo sai. Việc đánh dấu nhầm một hàm không đáp ứng hợp đồng có thể khiến chương trình chậm hơn hoặc JVM crash.

## 3. Hợp đồng nghiêm ngặt phải thỏa mãn

### 3.1. Thời gian thực thi phải cực ngắn trong **mọi** đường đi

Javadoc mô tả critical function có thời gian chạy **“extremely short ... in all cases (similar to calling an empty function)”**. Không thể chỉ xét thời gian chạy trung bình, median, p99 của dữ liệu tốt hoặc một lần benchmark thành công.

Một candidate phù hợp là hàm C thực hiện vài phép toán cố định, không phụ thuộc độ dài đầu vào và không gọi thư viện có thể block:

```c
int add_one(int x) {
    return x + 1;
}
```

Các ví dụ **không đủ điều kiện** dù đôi khi chạy nhanh:

- `read`/`recv`/`accept`, truy cập file/network hoặc bất kỳ hệ thống I/O nào có thể đợi dữ liệu.
- `sleep`, `nanosleep`, đợi event, condition variable, semaphore, mutex/lock đang bị giữ, `pthread_join` hoặc chờ thread.
- Hàm dùng lock hoặc cấp phát có đường slow path không có giới hạn cực ngắn; wrapper gọi dịch vụ bên ngoài.
- Vòng lặp phụ thuộc kích thước mảng/buffer do caller truyền (ví dụ quét hàng MB); `strlen` với chuỗi dài không giới hạn.
- Hàm gọi thư viện native mà bạn không kiểm soát hoặc chưa xác minh tất cả đường đi, kể cả nhánh lỗi và xử lý signal.
- Hàm “thường mất vài micro giây” nhưng **thỉnh thoảng** block, retry, chờ contention hoặc làm công việc dài.

Giới hạn cực ngắn không được biểu diễn bằng một số mili giây cố định trong API; hãy đánh giá đặc tính **bị chặn chặt về công việc** của mọi nhánh, không tự đặt ngưỡng “dưới 5 ms là critical”.

### 3.2. Tuyệt đối không callback/upcall vào Java

Native function đánh dấu critical **không được gọi ngược vào Java**. Ví dụ vi phạm:

- Nhận function pointer đến `Linker.upcallStub(...)` và **thực sự gọi** function pointer ấy.
- Gọi JNI để thực thi Java method, chẳng hạn `CallStaticVoidMethod` hay `CallObjectMethod`.
- Gọi thư viện native khác mà bên trong có callback sang Java (kể cả callback gián tiếp qua hook/handler).
- Kích hoạt callback một cách không dự đoán được, ví dụ chỉ ở nhánh lỗi hoặc khi cache miss.

Lý do: upcall cần đi từ native trở lại JVM, trong khi implementation có thể tối ưu hóa critical downcall bằng những giả định về trạng thái luồng, GC/safepoint và đường ra/vào runtime. Đánh dấu critical rồi upcall làm phá vỡ các giả định đó. Lỗi có thể dẫn đến JVM crash thay vì một Java exception rõ ràng.

Nếu native API nhận callback và **có thể** gọi callback, cách an toàn để liên kết nó là **downcall thông thường**, không truyền `Linker.Option.critical(...)`. Ngay cả khi callback hiếm khi chạy hoặc chỉ chạy trong tình huống lỗi, chức năng ấy vẫn không đủ điều kiện critical.

### 3.3. Không giữ trạng thái hoặc con trỏ heap sau lời gọi

Một lời gọi critical có thể cho phép native dùng địa chỉ tạm của bộ nhớ Java heap khi `allowHeapAccess=true`. Địa chỉ native này chỉ có hiệu lực **trong lúc hàm native đang được gọi**. Native không được lưu con trỏ vào static/global, trả về để dùng sau, chuyển đến một worker thread xử lý bất đồng bộ, hoặc tiếp tục truy cập nó khi downcall đã kết thúc.

Đặc biệt không được dùng heap pointer tạm ấy để:

- Chờ một thao tác I/O bất đồng bộ sử dụng con trỏ sau khi C function trở về.
- Gửi sang worker thread rồi trả về Java trước khi worker đọc xong.
- Lưu vào struct/cache native để những lần gọi sau dùng lại.

Việc native truy cập ngoài độ dài segment, sai alignment hoặc giữ con trỏ quá hạn vẫn là lỗi memory safety: FFM không thể kiểm tra mọi thao tác C/C++ bên trong một con trỏ đã chuyển qua ABI.

## 4. `critical(false)` khác `critical(true)` thế nào?

Chữ ký API chính thức:

```java
static Linker.Option critical(boolean allowHeapAccess)
```

| Cách liên kết | Heap `MemorySegment.ofArray(...)` làm đối số `ADDRESS` | Ý nghĩa |
| --- | --- | --- |
| Không truyền `critical` | Không được phép theo quy tắc thông thường của downcall address argument | Chuyển Java → native theo đường thông thường; dùng cho hàm có thể block/upcall |
| `Linker.Option.critical(false)` | Không được phép | Cam kết hàm cực ngắn, không upcall; **không** cần heap pointer |
| `Linker.Option.critical(true)` | Được phép | Cam kết **vẫn** cực ngắn, không upcall, đồng thời cho phép nhận con trỏ tạm đến heap memory |

`allowHeapAccess=true` không “nới lỏng” giới hạn thời gian hay cho phép callback. Nó chỉ bổ sung khả năng truyền heap segment vào một tham số có `AddressLayout`, trong những trường hợp sao chép sang off-heap tốn chi phí không tương xứng với công việc cực ngắn của hàm.

Khi truyền heap segment, JVM cung cấp địa chỉ native tạm còn hiệu lực trong **thời gian lời gọi**. Chiến lược triển khai để làm được điều này có thể tùy JVM/GC; không được mặc định mọi JVM luôn “zero-copy” hoặc luôn pin trực tiếp heap theo một cách cố định. Đường truy cập này có thể ảnh hưởng đến GC và độ trễ nếu bị giữ lâu; vì thế điều kiện **cực ngắn** càng quan trọng khi bật heap access.

Hai lỗi nhận thức phổ biến:

1. Dùng `critical(true)` để “tăng tốc mạnh hơn” trong khi chỉ truyền tham số `int`/`long`: tham số `true` không mang ý nghĩa tốc độ; chỉ bật quyền truy cập heap segment.
2. Dùng `critical(true)` cho native I/O đọc thẳng vào `byte[]` nhằm tránh copy: dù bỏ được một số thao tác sao chép, hàm vẫn có thể block và vì thế **không đủ điều kiện critical**. Hãy dùng downcall thường với native/off-heap buffer hoặc một thiết kế I/O khác.

Nếu truyền heap segment cho một downcall có `ADDRESS` nhưng không có `critical(true)`, API sẽ từ chối theo hợp đồng tương ứng (thường là `IllegalArgumentException` khi gọi method handle); **không** xem đây là lý do tùy tiện bật critical cho hàm dài.

## 5. Ma trận quyết định: chọn critical hay downcall thường?

| Hành vi thực tế của native function | Chọn | Giải thích |
| --- | --- | --- |
| Vài phép toán nguyên số cố định, không I/O, không callback, mọi nhánh cực ngắn | Có thể cân nhắc `critical(false)` | Thỏa hợp đồng nếu cả nhánh lỗi cũng cực ngắn |
| Đọc đúng 2 byte từ `byte[]` rồi cộng; không lưu pointer | Có thể cân nhắc `critical(true)` | Truy cập heap trực tiếp trong phạm vi một lời gọi cực ngắn |
| Xử lý buffer có kích thước không giới hạn | Downcall thường | Thời gian phụ thuộc dữ liệu |
| `read` từ socket, `sleep`, chờ lock/semaphore | Downcall thường | Có đường blocking hoặc chờ không dự đoán |
| Native gọi Java callback/upcall stub | Downcall thường | Callback trái hợp đồng critical |
| Wrapper có thể gọi JNI vào Java | Downcall thường | Không bảo đảm không upcall |
| Gọi native library bên thứ ba không rõ đường đi | Downcall thường | Chưa chứng minh được mọi nhánh cực ngắn và không callback |
| Function giữ pointer heap và xử lý tiếp sau khi trả về | Phải **thiết kế lại** quyền sở hữu/vòng đời | Không có lựa chọn `critical` nào làm pointer tạm sống lâu hơn |
| Hàm cực ngắn nhưng gọi rất ít lần | Thường không cần tối ưu | Chỉ benchmark mới chứng minh lợi ích thực tế |

Quy tắc review: Nếu bạn không thể mô tả và chứng minh **mọi nhánh** đều gần như tức thời và **không upcall**, hãy dùng downcall thường. Không dùng benchmark của happy path để thay bằng chứng về tính an toàn.

## 6. Lab chạy được: hai critical hợp lệ và một upcall thường

Bài lab tránh cố ý vi phạm critical vì chạy ví dụ native nguy hiểm có thể làm **crash JVM**. Thay vào đó, chương trình cho thấy **hai lời gọi critical an toàn** cùng **một upcall dùng đúng downcall thường**.

### 6.1. Mã native: `criticallab.c`

Trên Linux x86-64, lưu toàn bộ nội dung sau thành `criticallab.c`:

```c
#include <stdint.h>

#if defined(_WIN32)
#define EXPORT __declspec(dllexport)
#else
#define EXPORT __attribute__((visibility("default")))
#endif

/* Chi mot phep tinh: khong cap phat, khong block, khong callback. */
EXPORT int add_one(int value) {
    return value + 1;
}

/* Java phai bao dam mang it nhat 2 byte.
 * Con tro chi duoc doc trong thoi gian loi goi nay. */
EXPORT int sum_two_bytes(const unsigned char *bytes) {
    return (int)bytes[0] + (int)bytes[1];
}

typedef int (*int_callback)(int);

/* Goi callback do Java tao: KHONG DUOC DANH DAU CRITICAL. */
EXPORT int call_callback(int value, int_callback callback) {
    return callback(value) + 1;
}
```

`add_one` chỉ cộng 1, `sum_two_bytes` đọc chính xác 2 byte unsigned, đều có công việc cố định cực ngắn và không gọi Java. Ngược lại, `call_callback` thực thi function pointer dẫn về Java: phải dùng downcall thường dù bản thân wrapper chỉ có một dòng.

### 6.2. Java: `CriticalLinkerDemo.java`

```java
import java.lang.foreign.Arena;
import java.lang.foreign.FunctionDescriptor;
import java.lang.foreign.Linker;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.SymbolLookup;
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;

import static java.lang.foreign.ValueLayout.ADDRESS;
import static java.lang.foreign.ValueLayout.JAVA_INT;

public final class CriticalLinkerDemo {
    private static int twice(int value) {
        return value * 2;
    }

    public static void main(String[] args) throws Throwable {
        System.loadLibrary("criticallab");

        Linker linker = Linker.nativeLinker();
        SymbolLookup symbols = SymbolLookup.loaderLookup();

        // Case A: critical khong dung con tro Java heap.
        MethodHandle addOne = linker.downcallHandle(
            symbols.find("add_one").orElseThrow(),
            FunctionDescriptor.of(JAVA_INT, JAVA_INT),
            Linker.Option.critical(false)
        );
        int first = (int) addOne.invokeExact(41);
        System.out.println("critical(false): " + first);

        // Case B: native chi doc 2 byte tu mang Java trong loi goi.
        MethodHandle sumTwo = linker.downcallHandle(
            symbols.find("sum_two_bytes").orElseThrow(),
            FunctionDescriptor.of(JAVA_INT, ADDRESS),
            Linker.Option.critical(true)
        );
        byte[] pair = {7, 11};
        MemorySegment heapSegment = MemorySegment.ofArray(pair);
        int second = (int) sumTwo.invokeExact(heapSegment);
        System.out.println("critical(true): " + second);

        // Case C: native se upcall Java. Khong dung critical.
        MethodHandle callbackTarget = MethodHandles.lookup().findStatic(
            CriticalLinkerDemo.class,
            "twice",
            MethodType.methodType(int.class, int.class)
        );

        try (Arena arena = Arena.ofConfined()) {
            MemorySegment upcallStub = linker.upcallStub(
                callbackTarget,
                FunctionDescriptor.of(JAVA_INT, JAVA_INT),
                arena
            );

            MethodHandle callCallback = linker.downcallHandle(
                symbols.find("call_callback").orElseThrow(),
                FunctionDescriptor.of(JAVA_INT, JAVA_INT, ADDRESS)
            );

            int third = (int) callCallback.invokeExact(20, upcallStub);
            System.out.println("ordinary + upcall: " + third);
        }
    }
}
```

Các điểm cần kiểm tra trên code:

- `FunctionDescriptor.of(JAVA_INT, JAVA_INT)` mô tả `int add_one(int)` và `int twice(int)` trên ABI Linux x86-64; `MethodHandle.invokeExact` yêu cầu tham số và kiểu trả về **khớp chính xác**.
- `FunctionDescriptor.of(JAVA_INT, ADDRESS)` mô tả `int sum_two_bytes(const unsigned char*)`, nhưng chỉ vì đã cam kết `critical(true)` mà Java heap segment được phép làm `ADDRESS`.
- `FunctionDescriptor.of(JAVA_INT, JAVA_INT, ADDRESS)` mô tả `int call_callback(int, int (*)(int))`. Mã Java **không truyền tùy chọn critical** khi tạo handle này vì C sẽ gọi ngược qua `upcallStub`.
- `Arena.ofConfined()` kiểm soát vòng đời upcall stub. C gọi callback **đồng bộ trước khi trở về**; stub được dùng khi arena còn mở và trên luồng sở hữu arena.
- Callback `twice` không ném exception. Upcall target trong ứng dụng thực tế phải tự bắt/biến đổi lỗi trước khi exception thoát ra biên native; tài liệu `Linker.upcallStub` cảnh báo exception thoát khỏi upcall có thể khiến JVM kết thúc đột ngột.
- Chương trình có `throws Throwable` để đơn giản hóa demo với `MethodHandle.invokeExact`; trong ứng dụng thực tế cần chiến lược xử lý lỗi rõ ràng hơn.

### 6.3. Biên dịch và chạy trên Linux x86-64

Yêu cầu JDK 25, C compiler (`cc` hoặc `gcc`), và cả hai file ở cùng một thư mục:

```bash
cc -std=c11 -O2 -fPIC -shared criticallab.c -o libcriticallab.so
javac CriticalLinkerDemo.java
java --enable-native-access=ALL-UNNAMED -Djava.library.path=. CriticalLinkerDemo
```

**Stdout kỳ vọng chính xác:**

```text
critical(false): 42
critical(true): 18
ordinary + upcall: 41
```

Diễn giải từng dòng:

- 41 + 1 = 42 qua `add_one` với `critical(false)`.
- Byte unsigned 7 + 11 = 18 qua `sum_two_bytes` với `critical(true)`, không giữ con trỏ sau lời gọi.
- C gọi callback Java `twice(20)` → 40, rồi cộng 1 → 41 qua **downcall thường**.

`System.loadLibrary("criticallab")` nạp `libcriticallab.so`; `SymbolLookup.loaderLookup()` lấy địa chỉ symbol của thư viện đã nạp theo class loader. `--enable-native-access=ALL-UNNAMED` bật native access cho chương trình chạy từ classpath, vì các API FFM liên quan bị hạn chế quyền truy cập. `-Djava.library.path=.` cho phép JVM tìm thư viện trong thư mục hiện tại. Vì code dùng API chính thức của JDK 25, không dùng `--enable-preview`.

Trên macOS cần tạo `libcriticallab.dylib` (ví dụ `cc -dynamiclib criticallab.c -o libcriticallab.dylib`); trên Windows cần tạo `criticallab.dll`, dùng lệnh compiler/linker phù hợp và bảo đảm đúng kiến trúc. Ví dụ và stdout nêu trên được thiết kế cho môi trường Linux x86-64/JDK 25; thay ABI hoặc compiler cần kiểm tra lại.

### 6.4. Vì sao không thêm `critical` vào case C?

Giả sử có người thay cách liên kết `call_callback` như sau:

```java
// MINH HOA SAI — KHONG CHAY:
MethodHandle dangerous = linker.downcallHandle(
    symbols.find("call_callback").orElseThrow(),
    FunctionDescriptor.of(JAVA_INT, JAVA_INT, ADDRESS),
    Linker.Option.critical(false)
);
```

Đây **không phải phiên bản runnable an toàn**. Vì `call_callback` sẽ gọi `callback(value)` dẫn về Java, giả định “không upcall” của critical bị vi phạm. Đừng chạy để thử xem JVM có báo lỗi hay không: Javadoc cảnh báo misuse có thể làm JVM crash. Sửa đúng là **bỏ `Linker.Option.critical(...)`**, như case C của chương trình đầy đủ.

## 7. Với hàm chặn, callback hoặc công việc dài: thiết kế thay thế

### 7.1. Hàm chặn

Ví dụ `read`, `recv`, `accept`, chờ lock, chờ signal hay I/O ngoài tiến trình thường có thời gian không kiểm soát. **Không** dùng `critical(false)` và cũng **không** dùng `critical(true)`. Tạo downcall thường theo đúng signature và ABI. Trường hợp yêu cầu latency thấp, cân nhắc timeout, native nonblocking API, worker riêng, completion/event-driven API hoặc tách việc dài khỏi đoạn native cực ngắn.

Mẫu chọn cách liên kết (trích đoạn, chưa khai báo `linker`, `address`, `descriptor`):

```java
// Ham native co the block: downcall thuong.
MethodHandle blockingCall = linker.downcallHandle(address, descriptor);
```

Việc không truyền `critical` **không** khiến thao tác I/O tự thành asynchronous: thread gọi method handle vẫn phải đợi native function kết thúc, trừ khi bạn thiết kế bất đồng bộ ở nơi khác.

### 7.2. API sử dụng callback

Nếu thư viện C nhận function pointer có thể gọi ngược Java, tạo `upcallStub` và liên kết hàm C bằng downcall thường. Bảo đảm arena chứa stub còn sống trong toàn bộ thời gian C có thể gọi. Nếu thư viện giữ callback sau khi downcall kết thúc, **không** dùng `Arena.ofConfined()` trong một try-block ngắn như lab: phải thiết kế registration/unregistration và vòng đời stub dài tương ứng. Callback được C gọi từ luồng nào cũng cần đánh giá ràng buộc thread confinement và trạng thái runtime; một callback bất đồng bộ phải không dùng con trỏ hoặc stub đã bị giải phóng.

Mọi `upcallStub` phải có target `MethodHandle` khớp ABI và xử lý ngoại lệ ở biên Java; không để exception không được xử lý thoát qua biên native. Đây là rủi ro riêng của upcall **kể cả khi downcall bình thường**.

### 7.3. Xử lý buffer/heap và thời gian chạy

Nếu native cần đọc/ghi nhiều dữ liệu Java heap hoặc thời gian xử lý thay đổi theo kích thước, dùng cơ chế copy vào native `Arena`/off-heap memory rồi truyền address theo downcall thường, hoặc thiết kế thao tác streaming/khác phù hợp. Không hy sinh an toàn để tránh một lần copy.

Nếu chỉ đọc vài byte được kiểm soát, có thể đo `critical(true)` sau khi chứng minh dữ liệu đủ dài, đồng bộ, không escaping pointer và không callback. Hãy ghi rõ invariant về độ dài, alignment, lifetime trong code review; các kiểm tra độ dài của `MemorySegment` ở phía Java **không tự động bảo vệ** việc native dereference con trỏ sai.

## 8. Hiệu năng: khi nào critical thực sự đáng dùng?

Critical là một **tuyên bố về hành vi** để JVM *có thể* giảm chi phí của lời gọi native. Khác biệt có ý nghĩa nhất khi một hàm cực ngắn được gọi **rất nhiều lần**, và overhead chuyển Java ↔ native chiếm tỷ trọng lớn so với công việc thực tế.

Để đánh giá khách quan:

1. Trước hết chứng minh tính đủ điều kiện: kiểm tra mã C/C++, các hàm phụ, nhánh lỗi, xử lý buffer, lock, I/O và callback **trên mọi đường đi**. Kiểm tra library version sẽ triển khai production.
2. Tạo **hai handle cùng signature** cho cùng một native function hợp lệ: một downcall thường và một handle `critical(false)` (hoặc `critical(true)` nếu thật sự cần heap).
3. Dùng benchmark có warm-up, JVM/JDK/GC nhất quán, vòng lặp đủ lớn và cơ chế chống loại bỏ kết quả. Với Java, JMH thường thuận tiện hơn tự đo một lần bằng `System.nanoTime()`.
4. Kiểm tra cả throughput và latency, kể cả mức tail (p95/p99) và hoạt động GC, dưới workload thực. Nếu `allowHeapAccess=true`, theo dõi cả ảnh hưởng GC khi gọi dày đặc.
5. Chỉ giữ optimization nếu lợi ích có thể lặp lại và đủ bù chi phí bảo trì/rủi ro, không vì tên `critical`.

**Không nên benchmark bằng việc cố ý gắn critical cho `sleep`/I/O/upcall**. Đó là một thử nghiệm vi phạm hợp đồng và có thể gây sự cố ở mức JVM.

## 9. Chẩn đoán lỗi và ngộ nhận thường gặp

| Hiện tượng | Khả năng cần kiểm tra | Hướng xử lý |
| --- | --- | --- |
| JVM crash sau khi thêm `critical` | Native function có upcall/block/sai signature hoặc vi phạm memory safety | Bỏ `critical`, kiểm tra callback/ABI/con trỏ; lấy crash log nếu có |
| Cải thiện benchmark nhưng production tăng tail latency | Đường native có contention, GC interaction hoặc slow path | Kiểm tra mọi nhánh; đo workload thực; quay về downcall thường nếu không chứng minh được hợp đồng |
| `IllegalArgumentException` khi truyền `MemorySegment.ofArray(...)` làm `ADDRESS` | Downcall không cho phép heap segment address | Dùng native buffer với downcall thường, hoặc **chỉ khi đủ điều kiện critical** cân nhắc `critical(true)` |
| `UnsatisfiedLinkError` | Native library hoặc export symbol sai tên/đường dẫn/kiến trúc | Kiểm tra `libcriticallab.so`, `java.library.path`, symbol export và ABI |
| `IllegalCallerException` hoặc cảnh báo native access | Module chưa được bật native access | Dùng `--enable-native-access=ALL-UNNAMED` cho classpath hoặc tên module cụ thể |
| `WrongMethodTypeException` khi `invokeExact` | Kiểu Java tại lời gọi không khớp `MethodHandle.type()` | Sửa `FunctionDescriptor`/kiểu đối số/cast theo chữ ký thực |
| Upcall gây abort/JVM exit | Callback Java ném exception hoặc signature/lifetime không đúng | Bắt lỗi tại callback, map sang kết quả native và giữ stub còn sống |

**Ba điểm cần phân biệt kỹ:**

- `Linker.Option.critical` **không phải** JNI `GetPrimitiveArrayCritical` và **không phải** JVM `-Xcheck:jni`. Các cơ chế có thể liên quan đến việc tránh đường đi GC nhưng không thay thế lẫn nhau.
- Không có exception Java hay cảnh báo rõ ràng **không đồng nghĩa** với việc đánh dấu critical là an toàn. Hành vi sau một vi phạm hợp đồng có thể phụ thuộc JVM, GC, kiến trúc và nhánh code.
- Một Java method hoặc native function “không trực tiếp gọi Java” vẫn phải rà **lời gọi gián tiếp** đến thư viện khác, function pointer hoặc error handler: bất kỳ đường đi nào có upcall đều không phù hợp critical.

## 10. Checklist code review trước khi chọn `Linker.Option.critical`

- [ ] Mọi đường đi của C/C++ function có thời gian chạy cực ngắn, gần mức hàm rỗng; công việc bị chặn chặt, không phụ thuộc input size lớn.
- [ ] Không thực hiện I/O, chờ scheduler, sleep, lock, semaphore, allocation/slow path không bảo đảm cực ngắn hoặc đợi event.
- [ ] Không có callback/upcall Java, kể cả qua function pointer, JNI, thư viện trung gian hoặc nhánh lỗi.
- [ ] Signature `FunctionDescriptor`, kiểu C, calling convention/ABI và `MethodHandle.invokeExact` khớp.
- [ ] `critical(false)` được ưu tiên khi không cần truyền heap segment; `critical(true)` chỉ khi thực sự cần con trỏ vào heap và chứng minh được lợi ích.
- [ ] Độ dài/alignment của buffer được kiểm chứng; mọi con trỏ heap tạm chỉ được dùng **trong** lời gọi native.
- [ ] Không lưu, phát tán hoặc truy cập heap pointer sau khi downcall kết thúc; không giao việc bất đồng bộ với địa chỉ tạm.
- [ ] Đã đối chiếu tài liệu/JDK đang chạy và hiểu option chỉ là hint tối ưu hóa, không có bảo đảm tăng tốc.
- [ ] Có benchmark thông thường so với critical, với warm-up, workload thật và quan sát GC/tail latency.
- [ ] Khi bất kỳ điều kiện nào chưa chứng minh được, dùng **downcall thường**.

## 11. Câu hỏi tự kiểm tra

**1.** Một C function thường chạy 20 ns nhưng khi lock contention sẽ đợi vài giây. Có dùng `critical(false)` không?  
**Đáp án:** Không. Điều kiện “cực ngắn trong mọi trường hợp” bị phá vỡ bởi nhánh chờ lock.

**2.** Một C function chỉ gọi `callback(7)` rồi trả về. Dù rất ngắn, có thể dùng `critical(true)` không?  
**Đáp án:** Không. Bất cứ callback nào vào Java đều vi phạm hợp đồng; dùng downcall thường.

**3.** `critical(true)` có cho phép dùng con trỏ heap từ `MemorySegment.ofArray` sau khi native function trả về không?  
**Đáp án:** Không. Địa chỉ native tạm chỉ hợp lệ trong thời gian lời gọi.

**4.** Hai handle gọi cùng hàm native an toàn, một thường và một critical, có nhất thiết critical nhanh hơn không?  
**Đáp án:** Không. Nó là optimization hint, tùy triển khai JVM và workload; phải benchmark.

**5.** Vì sao không sửa lỗi “heap segment bị từ chối” bằng cách luôn thêm `critical(true)`?  
**Đáp án:** Vì `true` chỉ cho phép heap argument khi **đồng thời** đáp ứng điều kiện hàm cực ngắn và không upcall. Một hàm I/O hoặc chờ callback vẫn không đủ điều kiện.

## Tài liệu tham khảo chuẩn

- Oracle JDK 25, `Linker.Option.critical(boolean)`, định nghĩa thời gian cực ngắn, không upcall, hậu quả khi dùng sai và `allowHeapAccess`: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/foreign/Linker.Option.html
- Oracle JDK 25, `Linker`, downcall/upcall, giới hạn an toàn ABI và exception tại upcall: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/foreign/Linker.html
- Oracle JDK 25, `MemorySegment`, heap/native segments, scope và `ofArray`: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/foreign/MemorySegment.html
- Oracle JDK 25, `SymbolLookup`, `loaderLookup` và symbol resolution: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/foreign/SymbolLookup.html
- Oracle JDK 25, Restricted Methods / native access: https://docs.oracle.com/en/java/javase/25/core/restricted-methods.html
- OpenJDK JEP 454, *Foreign Function & Memory API* (finalized in JDK 22): https://openjdk.org/jeps/454
