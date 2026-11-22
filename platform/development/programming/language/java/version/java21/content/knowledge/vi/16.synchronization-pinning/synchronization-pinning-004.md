# Pinning liên quan đến native call và giới hạn chẩn đoán

Virtual thread có thể tạm dừng khi gặp thao tác blocking để nhường carrier thread cho virtual thread khác. Tuy nhiên, khi virtual thread đang thực thi một **native method** hoặc **foreign function**, JVM không thể unmount nó khỏi carrier một cách an toàn. Trạng thái này gọi là **pinning**.

Pinning không làm chương trình sai về mặt chức năng, nhưng native call kéo dài hoặc xảy ra thường xuyên có thể giữ các carrier thread trong thời gian dài, làm giảm khả năng phục vụ nhiều tác vụ đồng thời. Khi điều tra, cần kết hợp JDK Flight Recorder (JFR), thread dump và công cụ quan sát native code; không một công cụ đơn lẻ nào cho thấy toàn bộ nguyên nhân ở cả Java lẫn C/C++.

## 1. Carrier thread và cơ chế pinning

JVM lập lịch virtual thread bằng cách mount nó lên một platform thread, còn gọi là *carrier thread*. Khi virtual thread thực hiện một thao tác blocking mà JVM hỗ trợ suspend, virtual thread có thể unmount; carrier được giải phóng để chạy virtual thread khác.

Khi virtual thread đang chạy trong native code, JVM không thể tách virtual thread khỏi carrier trong lúc native frame còn trên stack. Nếu native method chờ I/O, khóa của thư viện native hoặc một tài nguyên bên ngoài, carrier thread vẫn bị giữ trong thời gian chờ đó.

```text
Virtual thread thực hiện I/O được JVM hỗ trợ:

Virtual thread:  [Java code] [chờ I/O ----------------] [tiếp tục]
Carrier:         [chạy VT]   [được giải phóng cho VT khác] [chạy VT]

Virtual thread gọi native method:

Virtual thread:  [Java code] [native call đang chạy/chờ --------] [tiếp tục]
Carrier:         [chạy VT]   [bị giữ bởi native frame ---------] [được rảnh]
```

Pinning là ràng buộc về khả năng unmount, không phải một loại exception. Chương trình vẫn có thể trả kết quả đúng, nhưng khả năng mở rộng có thể giảm nếu nhiều virtual thread cùng giữ carrier trong các native call lâu.

## 2. Những lời gọi có thể gây pinning

Các trường hợp quan trọng:

- **JNI native method:** phương thức Java được khai báo bằng từ khóa `native` và được cài đặt trong thư viện native, thường viết bằng C hoặc C++.
- **Foreign function:** lời gọi hàm native thông qua Foreign Function and Memory API. Các lời gọi này cũng giữ virtual thread trên carrier trong lúc thực thi native function.

Ví dụ khai báo một JNI method:

```java
public final class NativeBridge {
    static {
        System.loadLibrary("nativebridge");
    }

    public native long calculate(byte[] input);
}
```

Khi virtual thread gọi `calculate(...)`, nó đi vào native implementation. Nếu implementation thực hiện một lời gọi blocking kéo dài, carrier chạy virtual thread đó không thể được tái sử dụng cho virtual thread khác cho đến khi native call trả quyền điều khiển về JVM.

Java 21 cũng có thể dùng Foreign Function and Memory API, nhưng API này ở trạng thái preview trong JDK 21. Không nên lấy ví dụ preview làm cấu hình mặc định cho project Java 21 không bật preview. Dù dùng JNI hay foreign function, nguyên tắc cần nhớ vẫn là native frame có thể giữ carrier.

## 3. Khi nào native pinning trở thành vấn đề?

Một native call ngắn, có thời gian thực thi ổn định và không giữ carrier lâu thường không gây vấn đề đáng kể. Rủi ro xuất hiện khi native call vừa **kéo dài** vừa **xảy ra thường xuyên** hoặc đồng thời trên nhiều request.

Ví dụ, ứng dụng có hàng nghìn virtual threads nhưng thư viện native chỉ có thể hoàn tất một số ít lời gọi cùng lúc. Nếu nhiều virtual threads đi vào thư viện và bị chặn trong native code, nhiều carrier bị giữ. Các virtual threads khác phải chờ scheduler có carrier phù hợp để tiếp tục.

Tác động có thể gồm:

- Throughput giảm khi carrier bị giữ lâu và số tác vụ có thể tiến triển giảm.
- Latency và thời gian chờ trong queue tăng khi tải cao.
- Các request không trực tiếp dùng native library vẫn có thể bị ảnh hưởng nếu dùng chung scheduler và carrier pool.
- Việc tạo thêm virtual threads không giải phóng carrier đang bị native code giữ.

JVM không thể tùy ý unmount virtual thread giữa một native call, vì native code có thể đang giữ con trỏ hoặc trạng thái phụ thuộc vào stack/thread hiện tại. Đây là ràng buộc an toàn của tương tác Java-native, không phải lỗi có thể sửa chỉ bằng cách tăng số virtual threads.

## 4. Ví dụ: gọi native code từ virtual thread

Đoạn code sau minh họa một tác vụ virtual thread gọi JNI method:

```java
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public class NativeCallDemo {
    public static void main(String[] args) throws Exception {
        NativeBridge bridge = new NativeBridge();
        byte[] input = {1, 2, 3, 4};

        try (ExecutorService executor = Executors.newVirtualThreadPerTaskExecutor()) {
            Future<Long> result = executor.submit(() -> bridge.calculate(input));

            // Luồng main chờ kết quả; virtual thread thực thi JNI call.
            System.out.println(result.get());
        }
    }
}
```

`NativeBridge` cần có thư viện `nativebridge` tương ứng và native implementation đã được nạp thành công. Code Java minh họa cách gọi; bản thân nó không cung cấp thư viện C/C++ để chạy độc lập.

Nếu `calculate(...)` chỉ thực hiện tính toán native ngắn, pinning có thể chỉ tồn tại trong thời gian ngắn. Nếu nó gọi API hệ điều hành blocking, chờ thiết bị hoặc chờ khóa nội bộ lâu, carrier sẽ bị giữ lâu hơn. Đặc tính thực tế phụ thuộc vào native implementation và thư viện mà ứng dụng sử dụng.

## 5. Cách cô lập native call blocking

Nếu thư viện native có các lời gọi blocking kéo dài và không thể sửa để hỗ trợ suspend, có thể cô lập chúng trên một nhóm platform threads chuyên biệt, có giới hạn số luồng và hàng đợi. Virtual thread của request gửi tác vụ sang nhóm này rồi chờ Future; trong lúc chờ Future, virtual thread có thể unmount khỏi carrier.

Ví dụ về một executor riêng cho native work:

```java
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.ThreadFactory;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;

ThreadFactory nativeThreadFactory =
        Thread.ofPlatform().name("native-worker-", 0).factory();

ThreadPoolExecutor nativeExecutor = new ThreadPoolExecutor(
        4,
        4,
        0L,
        TimeUnit.MILLISECONDS,
        new ArrayBlockingQueue<>(64),
        nativeThreadFactory,
        new ThreadPoolExecutor.AbortPolicy());
```

Sau đó submit native call vào `nativeExecutor`:

```java
Future<Long> result = nativeExecutor.submit(() -> bridge.calculate(input));
long value = result.get();
```

Nhóm platform thread chuyên biệt giới hạn số native calls đang chạy cùng lúc; hàng đợi hữu hạn giúp ứng dụng có hành vi từ chối tải khi quá tải thay vì giữ một lượng task chờ không giới hạn. Các con số `4` và `64` chỉ là ví dụ, cần chọn theo khả năng của thư viện native, CPU, tài nguyên hệ điều hành và mức tải.

Đây là ranh giới cô lập tài nguyên native, không phải khuyến nghị đưa mọi virtual-thread task vào platform-thread pool. Chỉ chuyển phần native blocking thực sự cần cô lập. Cần đóng executor khi ứng dụng dừng và có chính sách xử lý `RejectedExecutionException`, timeout, cancellation và lỗi native.

`Future.cancel(true)` chỉ gửi yêu cầu interrupt cho thread đang chạy tác vụ. Native library có thể không phản hồi interrupt; vì vậy timeout của Future không đảm bảo native call dừng. Hãy dùng timeout hoặc cơ chế hủy do chính thư viện native cung cấp nếu có, và thiết kế thời gian chờ của ứng dụng phù hợp với giới hạn của native API.

## 6. Chẩn đoán pinning bằng JDK Flight Recorder

JDK Flight Recorder có event `jdk.VirtualThreadPinned` để ghi nhận trường hợp virtual thread bị pin và carrier không được giải phóng vượt quá ngưỡng thời gian. Trong cấu hình mặc định của JDK 21, event này được bật với threshold 20 ms.

Có thể bắt đầu ghi JFR khi chạy ứng dụng:

```shell
java -XX:StartFlightRecording:dumponexit=true,filename=pinning.jfr com.example.NativeCallDemo
```

Sau khi recording được tạo, in các event pinning:

```shell
jfr print --events jdk.VirtualThreadPinned pinning.jfr
```

Trong JDK 21, event có thể giúp xác định stack trace của virtual thread bị pin trong lúc có blocking operation. Khi đọc kết quả, hãy tìm các dấu hiệu như:

- Stack trace có native method hoặc frame đi qua JNI.
- Thời lượng pinning và tần suất event.
- Virtual thread và carrier liên quan nếu event cung cấp thông tin đó.
- Blocking operation dẫn đến việc virtual thread không thể nhường carrier.

Một event đơn lẻ không chứng minh native library là nút thắt của toàn hệ thống. Hãy đối chiếu với throughput, latency, CPU, số carrier đang bận và thời gian thực thi của native API.

## 7. Giới hạn của JFR và các công cụ chẩn đoán

JFR hữu ích nhưng không phải bản ghi đầy đủ mọi nanosecond mà virtual thread nằm trong native code:

- Event `jdk.VirtualThreadPinned` có threshold mặc định 20 ms trong JDK 21. Pinning ngắn hơn ngưỡng có thể không xuất hiện trong recording mặc định.
- Event tập trung vào tình huống pinning kéo dài gắn với blocking; không nên coi số event là tổng số lần gọi native hoặc tổng thời gian CPU chạy trong native code.
- Không có event trong recording không chứng minh rằng ứng dụng không gọi native method hoặc không có pinning ngắn.
- Stack trace Java có thể chỉ ra ranh giới native method, nhưng không nhất thiết cho thấy hàm C/C++ cụ thể, mutex native, system call hoặc lý do thư viện native đang chờ.
- Kết quả phụ thuộc cấu hình JFR, thời gian recording, workload và ngưỡng event.

Vì vậy, dùng JFR để tìm thời điểm và Java call path đáng chú ý, sau đó dùng profiler native hoặc công cụ hệ điều hành phù hợp để phân tích sâu phần C/C++ khi cần.

## 8. Thread dump và giới hạn quan sát native internals

Trong JDK 21, có thể tạo thread dump chứa thông tin platform threads và virtual threads bằng `jcmd`:

```shell
jcmd <PID> Thread.dump_to_file -format=text threads.txt
jcmd <PID> Thread.dump_to_file -format=json threads.json
```

Thread dump giúp quan sát virtual threads, trạng thái và stack trace Java tại thời điểm chụp. Tuy nhiên, định dạng dump này của JDK 21 không chứa object addresses, lock details, JNI statistics hoặc heap statistics như một số thông tin có trong thread dump truyền thống. Nó cũng không thay thế native stack profiler và không giải thích đầy đủ trạng thái bên trong thư viện C/C++.

Thread dump là ảnh chụp tại một thời điểm. Nếu vấn đề chỉ xảy ra trong thời gian ngắn, một lần chụp có thể bỏ lỡ sự kiện. Hãy chụp trong lúc tải tái hiện được vấn đề và kết hợp nhiều mẫu với JFR recording.

## 9. jdk.tracePinnedThreads trong JDK 21

JDK 21 có thể dùng system property `jdk.tracePinnedThreads` để in stack trace khi virtual thread block trong lúc đang pinned:

```shell
java -Djdk.tracePinnedThreads=full com.example.NativeCallDemo
```

Hai chế độ được cung cấp:

- `full`: in stack trace đầy đủ và làm nổi bật native frames cùng các frame giữ monitor.
- `short`: giới hạn output vào những frame có liên quan trực tiếp đến tình huống pinning.

Đây là công cụ hỗ trợ chẩn đoán theo thời điểm xảy ra blocking, không phải profiler liên tục, không đo tổng thời gian native call và có thể tạo nhiều log nếu tình huống xảy ra thường xuyên. Chỉ bật có chủ đích trong môi trường điều tra; JFR phù hợp hơn để thu thập và phân tích sự kiện trong một khoảng thời gian.

Khi triển khai trên JDK mới hơn, không nên mặc định dựa vào property này. JDK 24 đã thay đổi cơ chế monitor pinning và loại bỏ cơ chế trace cũ; dùng JFR `jdk.VirtualThreadPinned` và các công cụ quan sát được hỗ trợ bởi đúng phiên bản JDK đang chạy.

## 10. Phân biệt hành vi Java 21 và JDK mới hơn

Đây là điểm quan trọng khi đọc tài liệu pinning cũ hoặc vận hành ứng dụng đã nâng cấp JDK:

| Trường hợp | Java 21 | JDK 24 trở lên |
|---|---|---|
| Virtual thread chạy native method hoặc foreign function | Bị pin vào carrier | Vẫn bị pin vào carrier |
| Virtual thread blocking trong `synchronized` block/method, không có native frame | Có thể pin carrier | JEP 491 cho phép unmount trong trường hợp monitor này; không còn pin theo cơ chế cũ |
| Gọi native method trong khi đang giữ monitor | Bị pin do native frame và có thể đồng thời giữ monitor | Vẫn bị pin do native frame; JEP 491 không loại bỏ native pinning |
| JFR `jdk.VirtualThreadPinned` | Có, threshold mặc định 20 ms | Vẫn là công cụ chẩn đoán pinning |
| `jdk.tracePinnedThreads` | Có trong JDK 21 | Không còn là lựa chọn chẩn đoán được hỗ trợ sau thay đổi ở JDK 24 |

Vì vậy, không áp dụng máy móc lời khuyên cũ “thay mọi `synchronized` bằng `ReentrantLock`” cho JDK mới. Với native call, pinning vẫn là vấn đề cần đánh giá ở cả Java 21 và các JDK mới hơn. JEP 491 thay đổi monitor pinning, không loại bỏ ràng buộc an toàn khi virtual thread đang ở trong native code.

## 11. Quy trình điều tra native pinning

Khi nghi ngờ native call giữ carrier quá lâu, có thể thực hiện theo trình tự:

1. **Xác định ranh giới native:** tìm các JNI method, thư viện native hoặc foreign function được gọi trên đường xử lý request.
2. **Tái hiện dưới tải đại diện:** dùng workload gần với production để xem pinning có xảy ra thường xuyên và kéo dài không.
3. **Ghi JFR:** thu thập `jdk.VirtualThreadPinned`, rồi lọc theo thời lượng, stack trace và thời điểm latency tăng.
4. **Chụp thread dump:** dùng `jcmd` trong lúc vấn đề xảy ra để xem virtual threads và call path Java.
5. **Đo phần native:** dùng profiler hoặc công cụ của hệ điều hành để xác định native function đang chạy CPU, chờ khóa hay chờ I/O.
6. **Chọn cách xử lý:** tối ưu native implementation, dùng API native có timeout/cancellation, hoặc cô lập native blocking trên nhóm platform threads có giới hạn.
7. **Đo lại:** so sánh throughput, p95/p99 latency, số carrier bị giữ và error rate trước/sau thay đổi.

Không kết luận chỉ từ một thread dump hoặc một event JFR. Cần liên hệ bằng chứng pinning với tác động quan sát được ở hệ thống và kiểm tra trên đúng JDK mà ứng dụng đang sử dụng.

## 12. Checklist khi dùng virtual threads với native library

- Xác định các JNI native methods và foreign function trên đường xử lý request.
- Biết native call có thể chờ I/O, khóa native hoặc tài nguyên bên ngoài trong bao lâu.
- Tránh để native call blocking kéo dài chạy đồng thời không giới hạn trên carrier của virtual threads.
- Cân nhắc cô lập native blocking bằng executor platform-thread chuyên biệt, có giới hạn worker và queue.
- Dùng timeout/cancellation do native API hỗ trợ khi có; không giả định `interrupt` có thể dừng native code.
- Ghi JFR và theo dõi `jdk.VirtualThreadPinned`, đồng thời hiểu threshold và giới hạn của event.
- Dùng thread dump để tìm Java call path; dùng native profiler khi cần xem sâu C/C++ stack và system call.
- Phân biệt hành vi pinning của JDK 21 với monitor pinning đã thay đổi từ JDK 24.
- Đánh giá bằng workload thực tế, throughput, latency và tài nguyên carrier thay vì chỉ đếm số virtual threads.

Native call có thể giữ virtual thread gắn với carrier cho đến khi native code trả quyền điều khiển về JVM. JFR và thread dump giúp tìm dấu hiệu và call path, nhưng không thay thế công cụ phân tích native internals. Khi hiểu rõ giới hạn chẩn đoán và phiên bản JDK, có thể quyết định nên tối ưu thư viện, giới hạn native concurrency hay cô lập blocking work mà không áp dụng nhầm các hướng dẫn pinning đã thay đổi ở JDK mới.

## Tài liệu tham khảo

- [Oracle Java 21: Virtual Threads](https://docs.oracle.com/en/java/javase/21/core/virtual-threads.html)
- [Oracle Java 24: Virtual Threads](https://docs.oracle.com/en/java/javase/24/core/virtual-threads.html)
- [JEP 491: Synchronize Virtual Threads without Pinning](https://openjdk.org/jeps/491)
