# Native method và foreign function: những trường hợp pinning của Virtual Threads vẫn phải đánh giá

> Phạm vi: **Java concurrency ở cấp JVM/JDK**, từ Java 21 trở lên; đặc biệt chú ý thay đổi trong JDK 24 và các đường gọi **JNI** / **Foreign Function & Memory API (FFM)**. Kiến thức ở đây áp dụng cho ứng dụng Java thuần, không phụ thuộc Spring.

## 1. Vì sao native/foreign call là một ranh giới đặc biệt?

Một **virtual thread** là `java.lang.Thread` do JVM lập lịch trên một **carrier thread** (platform thread). Khi virtual thread đang chờ thao tác mà JDK hỗ trợ suspend/unmount, trạng thái thực thi của nó được lưu lại và carrier có thể phục vụ virtual thread khác.

Nhưng Java cũng phải gọi xuống thư viện/mã máy bên ngoài JVM qua hai cơ chế:

- **JNI native method:** phương thức Java được khai báo `native` và được hiện thực bằng mã C/C++ hoặc thư viện nền tảng. Java vẫn nhìn thấy chữ ký phương thức, nhưng mã thực thi và thao tác chặn bên trong nằm ở phía native.
- **Foreign function:** lời gọi từ Java vào hàm ngoài JVM bằng FFM API, thường qua `Linker.downcallHandle(...)` và `MethodHandle`. FFM có API mạnh hơn để mô tả ABI, biểu diễn bộ nhớ native và kiểm soát vòng đời, nhưng một downcall vẫn đi qua ranh giới Java–native.

Native frame có thể phụ thuộc ngăn xếp OS thread, thanh ghi, trạng thái kernel, bộ nhớ native và thread-local state của thư viện. JVM không thể tự do dời/ngắt một lời gọi native đang thực thi để “unmount rồi chạy tiếp trên carrier khác” như một số thao tác blocking Java do JDK quản lý.

Vì vậy, **khi virtual thread đang chạy native method hoặc foreign function, nó có thể bị pin với carrier**. Nếu lời gọi trở về nhanh, tác động không đáng kể. Nếu nó chờ lâu (đọc thiết bị, gọi thư viện đồng bộ, DNS qua native library, C API chờ lock, syscall, JNI callback bị chặn...), một carrier có thể bị giữ lâu dù ứng dụng tạo rất nhiều virtual threads.

### Ba khái niệm không được đánh đồng

| Khái niệm | Điều đang xảy ra | Hệ quả |
|---|---|---|
| **Mount** | Virtual thread đang chạy trên một carrier | Carrier đang dùng CPU/OS thread để phục vụ nó |
| **Unmount khi chờ** | JDK suspend virtual thread tại điểm hỗ trợ | Carrier được giải phóng, có thể làm việc khác |
| **Pinning** | Virtual thread không thể unmount tại điểm cần chờ | Nếu chờ lâu, carrier bị giữ; có thể giảm throughput |

**Một native call ngắn không tự trở thành “lỗi pinning”.** Rủi ro quan trọng là **mức độ thường xuyên × thời gian carrier bị chiếm × số task đồng thời**, chứ không phải chỉ sự hiện diện của `native`/`downcallHandle` trong source code.

```text
Đường chờ được JDK hỗ trợ:
Virtual thread -> Java socket read / park -> UNMOUNT -> carrier rảnh
                                               -> resume khi sẵn sàng

Đường native chặn lâu:
Virtual thread -> JNI/FFM -> native blocking call -> carrier vẫn bị chiếm
                                              (không có điểm unmount an toàn)
```

Đây là giản đồ hành vi điển hình, không khẳng định mọi lời gọi Java nội bộ có native code đều chặn carrier. JDK có các triển khai/chuyển đổi đặc biệt cho nhiều API blocking chuẩn; hãy đo đường thực thi cụ thể.

## 2. Phân biệt JDK 21–23 và JDK 24 trở lên

Virtual threads chính thức có trong **Java 21 (JEP 444)**. Khi phân tích pinning phải nêu phiên bản JDK:

| Trường hợp | JDK 21–23 | JDK 24+ |
|---|---|---|
| Blocking trong `synchronized` method/block | Có thể pin carrier | JEP 491 cho phép unmount trong trường hợp monitor thông thường |
| Chờ monitor / `Object.wait()` thông thường | Có thể gây hạn chế tương tự | JEP 491 cải thiện cách virtual thread chờ và tái chiếm monitor |
| JNI native method chạy dài/chặn | **Vẫn phải đánh giá** | **Vẫn phải đánh giá** |
| FFM downcall sang hàm C/native chặn | **Vẫn phải đánh giá** | **Vẫn phải đánh giá** |
| Native callback (JNI/FFM upcall) quay về Java và gọi API blocking | Có khả năng pin khi còn native frame | Vẫn có khả năng pin khi native frame còn trên stack |
| Chờ khởi tạo lớp hoặc một số vùng đặc biệt trong VM | Cần quan sát | Vẫn có trường hợp đặc biệt cần quan sát |

**JEP 491 không đồng nghĩa “Java 24 xóa hoàn toàn pinning”.** Nó giải quyết vấn đề monitor-related rất quan trọng, nhưng không thể biến các syscall và native library đồng bộ thành thao tác tự động suspend được. Thay toàn bộ `synchronized` bằng `ReentrantLock` để “sửa native pinning” là sai mục tiêu; thay đổi lock Java không giải phóng được một OS thread đang bị giữ trong native function.

Từ JDK 22, **FFM API được chuẩn hóa theo JEP 454**; nếu dùng JDK 21 thì FFM còn là preview và lệnh chạy/API có thể khác. Ví dụ FFM ở mục 5 dùng **JDK 25**, đã cố ý ghi rõ nền tảng để tránh nhầm cú pháp phiên bản.

## 3. Những dạng native/foreign path cần kiểm tra

### 3.1. JNI gọi một tác vụ I/O hoặc đồng bộ chặn lâu

Ví dụ chữ ký cầu nối JNI:

```java
final class NativeBridge {
    static {
        System.loadLibrary("nativebridge");
    }

    static native int readSensorBlocking();
}
```

*Đoạn này chỉ là khai báo cầu nối; muốn chạy phải có thư viện native tương ứng. Không phải chương trình Java độc lập.*

Nếu `readSensorBlocking()` đợi dữ liệu thiết bị 500 ms bên trong C/C++, virtual thread gọi nó không tự được JDK đưa vào danh sách chờ I/O để unmount. Hàng nghìn virtual threads cùng gọi hàm có thể chiếm nhiều OS threads hoặc khiến carrier khan hiếm.

Tương tự với thư viện mã hóa/hardware token, driver thiết bị, media codec, thư viện xử lý file chuyên dụng hay JNI wrapper gọi một thư viện C legacy. Cần xác minh **cơ chế chờ thực tế**: syscall blocking, mutex/condition variable, polling, callback, hay chỉ tính toán CPU.

### 3.2. FFM downcall gọi hàm native đồng bộ

Một lời gọi FFM có dạng:

```java
// Minh họa về API; cần tạo linker và function descriptor đúng ABI.
MethodHandle function = linker.downcallHandle(symbol, signature);
Object result = function.invokeWithArguments(arguments);
```

Dùng `Linker` và `MethodHandle` **không biến** hàm C đồng bộ thành Java non-blocking. Nếu hàm gốc chờ I/O hoặc lock bên native trong 2 giây, carrier thường không thể được trả cho scheduler trong khoảng đó. Với FFM, cần đọc cả tài liệu của C function: thao tác nào chặn, timeout, khả năng bị ngắt, affinity, thread-safety và hành vi callback.

### 3.3. Native gọi ngược vào Java (JNI callback / FFM upcall)

```text
Virtual thread
  -> Java wrapper
     -> JNI/FFM native function
        -> native C code
           -> callback Java
              -> LockSupport.park / Thread.sleep / socket read
                 -> không thể unmount khi native frame còn nằm trong stack
```

Đây là trường hợp dễ bị bỏ sót: lệnh chờ xuất hiện trong **mã Java callback**, nhưng stack vẫn có native frame ở phía dưới. Một cuộc gọi `Thread.sleep(...)` thông thường có thể unmount; cùng thao tác nằm trong chuỗi callback từ native lại có thể khiến carrier bị giữ. Khả năng tạo pinning phải được kiểm tra trên bản JDK, JVM, cách nối JNI/FFM và workload thật.

FFM **upcall stub** cho phép C gọi lại Java; khi thư viện ngoại tự tạo thread để gọi callback, các quy tắc thread và quan sát có thể khác so với downcall khởi đầu từ virtual thread. Không giả định callback chắc chắn đang chạy trên cùng loại thread; hãy kiểm tra bằng `Thread.currentThread().isVirtual()` và stack trace thực tế.

### 3.4. Native code tính toán CPU lâu

Native call có thể chiếm carrier lâu mà **không có một lệnh chờ blocking rõ ràng**. Đây là giới hạn sử dụng CPU/carrier, không nhất thiết là pinning event do virtual thread cố unmount rồi thất bại. Ví dụ: codec native xử lý ảnh hàng giây, thuật toán C chạy liên tục hoặc thư viện mã hóa ngốn CPU. Giải pháp chính là quản trị song song theo CPU, tránh tăng vô hạn virtual threads; chỉ nhìn event pinning sẽ bỏ sót bottleneck này.

### 3.5. Chờ native lock, khởi tạo lớp và vùng giới hạn của JVM

JNI/FFM có thể gọi những thư viện với **native mutex, condition variable, thread-local storage** hoặc yêu cầu thread-affinity. Cần xem đường gọi có trả về nhanh hay đợi lâu ở mutex/OS. Ngoài native boundary, JVM vẫn có một số tình huống hiếm khiến virtual thread không thể unmount, như chờ class initialization và vùng VM đặc biệt. Đừng quy toàn bộ hiện tượng không mở rộng được cho `synchronized` hay JNI khi chưa có stack/metrics.

## 4. Phân biệt “carrier bị chặn” và sự kiện `jdk.VirtualThreadPinned`

**Một điểm quan trọng khi đo:** JFR event `jdk.VirtualThreadPinned` chủ yếu giúp phát hiện các thời điểm virtual thread **định park/block mà không thể unmount**, kèm ngưỡng thời gian cấu hình. Native function tự chặn trong C trong một giây có thể làm carrier bận một giây **mà không nhất thiết tạo sự kiện pinned đúng khoảng thời gian đó**.

Ví dụ: virtual thread đang trong `sleep(1)` của C qua FFM. Nó chờ bên trong native call; JVM có thể không quan sát lệnh chờ đó như một điểm Java parking sinh `jdk.VirtualThreadPinned`. Ngược lại, nếu native frame gọi ngược vào Java rồi Java `LockSupport.park(...)`, JFR có thể ghi native frame là nguyên nhân không unmount được.

Vì thế:

- **Có sự kiện pinned dài và lặp lại**: bằng chứng mạnh về việc carrier không được trả khi một virtual thread bị chặn.
- **Không có sự kiện pinned**: **không chứng minh** không có thời gian chặn native hoặc không có carrier starvation.
- **Có frame native trong stack**: chỉ là manh mối; cần kết hợp duration/frequency và trạng thái carrier.
- **Số virtual threads rất cao**: không tự chứng minh bottleneck; theo dõi cả runnable backlog, CPU và tài nguyên downstream.

Khi điều tra một native path, hãy phối hợp JFR + thread dumps + profiler native/OS nếu cần; phân tích cả thời gian thực thi native chứ không dừng ở một loại event.

## 5. Demo FFM có thể chạy: gọi hàm C `sleep` trên Linux/x64

Ví dụ này dùng **JDK 25+, Linux/x64** và hàm C chuẩn trên hệ POSIX. Nó giúp thấy sự khác nhau giữa **chạy native trực tiếp trong virtual thread** và **đưa native blocking call vào một pool platform threads có giới hạn**. Ví dụ không tuyên bố rằng một lần chạy chắc chắn sẽ phát ra `jdk.VirtualThreadPinned`.

Tạo tệp **`NativeBoundaryDemo.java`**:

```java
import java.lang.foreign.FunctionDescriptor;
import java.lang.foreign.Linker;
import java.lang.invoke.MethodHandle;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

import static java.lang.foreign.ValueLayout.JAVA_INT;

public class NativeBoundaryDemo {
    // C: unsigned int sleep(unsigned int seconds);
    // Trên Linux/x64, unsigned int có layout 32 bit.
    private static final MethodHandle NATIVE_SLEEP = findNativeSleep();

    private static MethodHandle findNativeSleep() {
        Linker linker = Linker.nativeLinker();
        return linker.downcallHandle(
                linker.defaultLookup().findOrThrow("sleep"),
                FunctionDescriptor.of(JAVA_INT, JAVA_INT));
    }

    private static int callNativeSleep() {
        try {
            return (int) NATIVE_SLEEP.invokeExact(1);
        } catch (Throwable problem) {
            throw new IllegalStateException("Native call failed", problem);
        }
    }

    public static void main(String[] args) throws InterruptedException {
        // Cách 1: gọi native trực tiếp trong virtual thread.
        Thread direct = Thread.ofVirtual().start(() -> {
            System.out.println("direct virtual="
                    + Thread.currentThread().isVirtual());
            System.out.println("direct remaining=" + callNativeSleep());
        });
        direct.join();

        // Cách 2: dùng số lượng platform threads có giới hạn
        // để thực thi phần native đang blocking.
        try (ExecutorService nativePool = Executors.newFixedThreadPool(2)) {
            Thread caller = Thread.ofVirtual().start(() -> {
                System.out.println("offload caller virtual="
                        + Thread.currentThread().isVirtual());
                Future<Integer> result = nativePool.submit(() -> {
                    System.out.println("native worker virtual="
                            + Thread.currentThread().isVirtual());
                    return callNativeSleep();
                });

                try {
                    // Future.get() chờ theo API Java; virtual caller có thể unmount.
                    System.out.println("offload remaining=" + result.get());
                } catch (InterruptedException interruption) {
                    result.cancel(true);
                    Thread.currentThread().interrupt();
                } catch (ExecutionException failure) {
                    throw new IllegalStateException(failure.getCause());
                }
            });
            caller.join();
        }
    }
}
```

Biên dịch/chạy trên **JDK 25+, Linux/x64**:

```bash
javac NativeBoundaryDemo.java
java --enable-native-access=ALL-UNNAMED NativeBoundaryDemo
```

Khi hai lần `sleep(1)` kết thúc bình thường (không có signal ngắt), stdout:

```text
direct virtual=true
direct remaining=0
offload caller virtual=true
native worker virtual=false
offload remaining=0
```

Với C `sleep`, return value khác 0 nếu bị ngắt và còn thời gian ngủ; do đó `remaining=0` là **kết quả trong trường hợp không bị gián đoạn**, không phải lời bảo đảm cho mọi môi trường. `defaultLookup()` và `unsigned int` là phụ thuộc ABI/nền tảng; trên Windows hoặc ABI khác phải chọn đúng thư viện, symbol và layout tương ứng. Không dùng nguyên mã này như demo đa nền tảng.

**Giải thích:** phần direct thực hiện native blocking trên carrier của virtual thread. Phần offload thực hiện native blocking trên **platform worker** của `nativePool`; virtual caller chờ `Future.get()` và có thể nhường carrier theo cơ chế JDK. Pool hai worker chỉ cho tối đa hai tác vụ native chạy đồng thời; nó không rút ngắn `sleep(1)` hay biến một hàm C thành non-blocking. Với một số API native, đặc biệt API đòi thread-affinity hoặc callback, phải kiểm tra có được phép chuyển thread hay không trước khi áp dụng.

Lưu ý `Future.cancel(true)`/interrupt của Java **không bảo đảm** dừng một native syscall hoặc thư viện C không hỗ trợ cancellation. Với hệ thống thực, phải dùng timeout/cancellation do chính native API cung cấp khi có.

### Demo này có giới hạn gì?

- Dùng 2 công việc và `sleep(1)` chỉ để minh họa ranh giới. Nó **không** cung cấp benchmark throughput, p99 hay xác nhận có/không pinning event.
- Nếu chạy đo, cần kiểm soát scheduler parallelism, số lượng công việc, thời gian chờ, platform pool và mức tải. Không dùng một kết quả chạy đơn lẻ để quyết định cấu hình production.
- Nếu native API trả về gần như ngay lập tức, việc đẩy qua pool có thể tốn thêm hàng đợi/context switching hơn là gọi trực tiếp; offload chủ yếu dành cho **native call có thể chặn lâu và xuất hiện thường xuyên**.

## 6. Quan sát và xác minh pinning trên JVM thật

### Bước 1: xác nhận runtime và các đường gọi

Ghi lại `java -version`, OS/ABI, tên/phiên bản thư viện native, JNI hay FFM, số kết nối/thiết bị, và native function cụ thể. Kiểm tra API nào thật sự blocking, có timeout, dùng callback, affinity hay native locks; không kết luận chỉ từ tên thư viện.

### Bước 2: bật JDK Flight Recorder

Ví dụ với chương trình `NativeBoundaryDemo` ở trên (JDK 25):

```bash
java --enable-native-access=ALL-UNNAMED \
  -XX:StartFlightRecording:filename=native-recording.jfr,dumponexit=true \
  NativeBoundaryDemo

jfr print --events jdk.VirtualThreadPinned native-recording.jfr
```

Dấu `\` cuối dòng ở ví dụ shell là cú pháp nối dòng của Bash/Linux. Nếu dùng Windows PowerShell, chạy lệnh `java` trên một dòng hoặc dùng cú pháp riêng của PowerShell.

Các event nên xét gồm `jdk.VirtualThreadPinned`, event blocking như `jdk.SocketRead`/`jdk.ThreadSleep` khi có, và các event về CPU/sampling tùy cấu hình. Trên các JDK có event `jdk.VirtualThreadPinned`, ngưỡng mặc định thường **20 ms**; sự kiện quá ngắn có thể không được ghi. Điều chỉnh threshold trong JFR nếu cần chứng minh vấn đề ở thời lượng ngắn.

Trên **JDK 21–23**, có thể dùng thêm `-Djdk.tracePinnedThreads=full` hoặc `short` để tìm stack khi virtual thread block trong lúc pinned. Đó là công cụ chẩn đoán theo phiên bản cũ; đừng mặc định những tùy chọn và nội dung trace giữ nguyên giữa các JDK.

### Bước 3: thu thread dump khi có tải

```bash
jcmd <PID> Thread.dump_to_file -format=json threads.json
```

`<PID>` là PID của JVM đang chạy; phải thay bằng số thực tế. Thread dump hỗ trợ xem nhiều virtual threads và trạng thái carrier, nhưng là **ảnh chụp tại một thời điểm**, chưa đủ đo thời lượng hoặc gọi tên native library. Nếu JFR chỉ vào native/VM frame, hãy đối chiếu stack, thời gian và mẫu CPU/native profiler (ví dụ công cụ profiler/OS tương thích môi trường). Chỉ dùng profiler native có hỗ trợ môi trường và bảo đảm quan sát được các stack frame cần thiết.

### Bước 4: đo một workload đại diện

Tối thiểu theo dõi:

| Nhóm phép đo | Câu hỏi cần trả lời |
|---|---|
| Throughput và p95/p99 latency | Với nhiều tác vụ đồng thời, hệ thống còn tăng thông lượng không hay bị đuôi trễ? |
| CPU / số OS threads / carrier | Native blocking có giữ nhiều platform threads mà CPU không bận tương ứng? |
| JFR pinned events | Có điểm chờ Java nào không unmount được do native frame? Tần suất/thời lượng? |
| Native function wall time / profiler | Hàm C thực sự chờ ở syscall, lock hay làm CPU? |
| Queue length / worker saturation | Pool offload có bị nghẽn và đẩy latency sang hàng đợi không? |
| Connection/native resource limits | Đã hết sockets, descriptors, buffer, native memory hay tài nguyên dịch vụ? |

Dùng so sánh trước–sau trên **cùng JDK, tải và giới hạn tài nguyên**, hoặc ghi rõ sự khác biệt khi đổi JDK. `jdk.VirtualThreadPinned` chỉ là một phần của bằng chứng. Nếu JFR im lặng mà wall time native tăng/OS threads bị chặn, tiếp tục điều tra native path.

## 7. Giảm ảnh hưởng mà vẫn giữ tính đúng đắn

### Cách A: ưu tiên API blocking Java được JDK quản lý khi có thể

Nếu nhu cầu là I/O mạng thông thường, cân nhắc API Java chuẩn tương thích virtual threads để JVM có cơ hội unmount lúc chờ. Việc chuyển từ JNI blocking sang API Java chuẩn **có thể** cải thiện concurrency, nhưng phải kiểm tra tính tương đương về chức năng, timeout, format, latency và tác dụng phụ. Không có quy tắc “mọi Java API đều unmount” hoặc “mọi native call đều phải bỏ”.

### Cách B: tách native blocking workload sang bounded platform pool

Dùng `Executors.newFixedThreadPool(n)` chuyên cho thư viện native có thể chặn dài, để virtual caller chờ `Future.get()` hoặc kết quả tương đương. Điều này **giới hạn số OS threads** bị chặn vì thư viện native; queue phải có giới hạn/backpressure và thời gian đợi phải được quản lý để tránh chuyển từ cạn carrier sang quá tải hàng đợi. `newFixedThreadPool` dùng hàng đợi không giới hạn mặc định; trong production cần thiết kế giới hạn số task in-flight/queue, hoặc semaphore/admission control phù hợp.

Không dùng pool này chỉ để “pool virtual threads”; mục đích là cô lập và kiểm soát một tài nguyên native hữu hạn. Không đổi thread tùy tiện với API native yêu cầu tất cả call diễn ra trên một OS thread, ví dụ một số API đồ họa, toolkit và thư viện có thread-local context; phải tôn trọng hợp đồng thư viện.

### Cách C: giới hạn concurrency tại tài nguyên gốc

Dùng `Semaphore`, connection pool, worker queue có giới hạn, timeout hoặc rate limit để quản lý số lời gọi native đồng thời. Chẳng hạn thư viện cho tối đa 8 phiên làm việc với thiết bị thì chỉ cấp 8 permits, dù có 100.000 virtual threads. Nhớ giải phóng permit trong `finally`; `Semaphore.acquire()` nên diễn ra **trước khi vào native path** để phần chờ permit có thể unmount trên virtual thread.

### Cách D: ưu tiên native API có timeout/asynchronous completion

Nếu thư viện cung cấp API không đồng bộ/callback từ thread riêng hoặc khả năng hủy, hãy cân nhắc nó sau khi đánh giá ownership, callback thread, memory lifetime và tương tác với Java. Một native API “async” có thể vẫn giữ lock nội bộ, spawn thread đắt tiền hay gọi callback giữ native frame; cần chứng minh thực nghiệm cơ chế chờ/hoàn thành.

### Cách E: nâng JDK khi bottleneck là monitor, không phải native

Nếu JFR cho thấy `synchronized` gây pin trên JDK 21–23, JDK 24+ có thể giải quyết bằng JEP 491. Nhưng nếu hàm C đang ngủ 500 ms trên carrier, nâng JDK chỉ vì JEP 491 **không đảm bảo** xử lý được native wait. Hãy phân loại đúng nguyên nhân trước khi đổi `synchronized`, thay JNI/FFM hay điều chỉnh scheduler.

## 8. Những lỗi chẩn đoán và thiết kế phổ biến

1. **“Không có `jdk.VirtualThreadPinned` nên native không block.”** Sai: native syscall blocking có thể chiếm carrier mà không tạo Java parking event tương ứng.
2. **“Đổi sang FFM thì sẽ hết pinning của JNI.”** Sai: FFM đổi giao diện và quản lý foreign call; downcall blocking vẫn chạy native trên OS thread.
3. **“Java 24 đã chữa mọi pinning.”** Sai: JEP 491 tập trung vào monitors; native/VM frames vẫn cần quan sát.
4. **“Lệnh native nào cũng làm nghẽn hệ thống.”** Sai: lệnh rất nhanh thường ít ảnh hưởng; quan trọng là thời gian, tần suất và đồng thời.
5. **“Tăng `jdk.virtualThreadScheduler.parallelism` để chữa triệt để.”** Thay đổi cấu hình có thể che bớt triệu chứng trong bài đo nhưng không bỏ blocking native hay giới hạn downstream; cần xem đúng bottleneck.
6. **“`Future.cancel(true)` chắc chắn hủy được hàm C.”** Không bảo đảm. Native API phải hỗ trợ hủy hoặc timeout theo giao thức của nó.
7. **“Platform thread pool tự tạo backpressure đủ tốt.”** `newFixedThreadPool` có hàng đợi mặc định không giới hạn; phải thiết kế admission/backpressure nếu số task không được kiểm soát.
8. **“Có thể chuyển native call sang bất kỳ thread nào.”** Không phải mọi thư viện native đều thread-safe hay không có thread-affinity; phải đọc API contract.
9. **“Native memory tự có GC giống heap Java.”** FFM `Arena` và JNI thường đòi quản lý lifetime/ownership rõ ràng; dùng segment sau khi arena đóng hoặc giữ pointer không hợp lệ gây lỗi nghiêm trọng, độc lập với pinning.
10. **“Đẩy mọi native function sang platform pool luôn nhanh hơn.”** Offload cũng có chi phí task queue/context switching và có thể tăng latency; cân nhắc nếu native blocking **thực sự dài và thường xuyên**.

## 9. Quy trình audit một JNI/FFM library trước khi triển khai Virtual Threads

1. **Lập bản đồ call path:** từ task Java → wrapper → JNI/FFM → thư viện C → syscall/lock/callback → trở về Java; đánh dấu những điểm có thể chờ hoặc phụ thuộc OS thread.
2. **Phân loại native call:** quick/CPU-bound/long blocking/callback/thread-affine; xác minh timeout, hủy, signal và thread-safety.
3. **Khóa phiên bản để đo:** JDK 21–23 khác JDK 24+ về monitors; FFM chuẩn từ JDK 22. Ghi lại ABI, OS và phiên bản native library.
4. **Thu JFR và stack/OS samples:** tìm cả Java-side pinning và native blocking vô hình với JFR event. Không kết luận chỉ từ trace đơn lẻ.
5. **Giới hạn tài nguyên trước khi mở tải:** native calls in-flight, queue, native memory, connection/file descriptors và downstream capacity.
6. **So sánh phương án:** direct virtual-thread call; API Java blocking tương thích; native platform executor có giới hạn; native asynchronous API. Kiểm tra throughput, tail latency, CPU, OS threads, lỗi và cancellation.
7. **Chốt thiết kế dựa trên dữ liệu:** chỉ sửa hotspot đã chứng minh; ghi rõ điều kiện cần đo lại khi nâng JDK hoặc thay JNI/FFM library.

## Tài liệu chuẩn

- [JEP 444 — Virtual Threads](https://openjdk.org/jeps/444): giới thiệu tính năng chính thức ở Java 21 và giới hạn native/foreign.
- [JEP 491 — Synchronize Virtual Threads without Pinning](https://openjdk.org/jeps/491): thay đổi monitor từ JDK 24; không xóa mọi native pinning.
- [JEP 454 — Foreign Function & Memory API](https://openjdk.org/jeps/454): FFM thành API chính thức ở Java 22.
- [Oracle JDK 25 — Virtual Threads](https://docs.oracle.com/en/java/javase/25/core/virtual-threads.html): mount/unmount, native pinning, JFR và thread dump.
- [Oracle JDK 25 — Linker API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/foreign/Linker.html): downcall, layout và ABI.
- [Oracle JDK 25 — Memory Segments and Arenas](https://docs.oracle.com/en/java/javase/25/core/memory-segments-and-arenas.html): vòng đời native memory.

**Điểm cần nhớ:** JNI và FFM đều có thể giữ carrier khi đi qua mã native; điều gây hại là **chờ lâu và thường xuyên** trên tài nguyên OS thread hữu hạn. JDK 24+ sửa pinning do monitor thông thường, còn đường native phải được audit bằng cả Java/JFR **và quan sát native/OS**, sau đó mới chọn API khác, giới hạn số lời gọi hoặc offload có kiểm soát.
