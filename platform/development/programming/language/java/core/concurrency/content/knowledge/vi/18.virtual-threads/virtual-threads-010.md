# ThreadLocal và chi phí dữ liệu theo từng virtual thread

## 1. Vấn đề đặt ra

Từ Java 21, **virtual threads** (JEP 444) cho phép Java chạy rất nhiều tác vụ đồng thời, đặc biệt khi tác vụ chờ I/O. Mỗi virtual thread vẫn là một `java.lang.Thread`; JVM có thể tạm dừng nó, trả platform thread đang chạy nó (thường gọi là *carrier*) về scheduler, rồi tiếp tục virtual thread trên carrier khác.

`ThreadLocal<T>` vẫn được hỗ trợ đầy đủ: **mỗi virtual thread có giá trị riêng cho từng khóa ThreadLocal**. Khi virtual thread thay carrier, giá trị không tự mất, không chuyển sang virtual thread khác và cũng không thuộc về carrier. Vấn đề nằm ở **quy mô dữ liệu**: số virtual threads sống đồng thời có thể lớn hơn rất nhiều so với số platform threads truyền thống. Cache hoặc trạng thái gắn với từng thread có thể trở thành nguồn tiêu thụ heap và cấp phát lớn.

Ví dụ, ứng dụng cũ có 32 platform threads trong pool, mỗi thread giữ một buffer 64 KiB qua `ThreadLocal`. Tổng payload ước lượng 2 MiB khi cả 32 thread đều khởi tạo. Chuyển cùng logic sang 10.000 virtual threads đang sống, mỗi thread tự tạo buffer 64 KiB, payload riêng đã khoảng **625 MiB**, chưa tính metadata, object header, stack, tham chiếu và những object khác. Đây là ước lượng dung lượng, **không phải benchmark**.

Mục tiêu: hiểu `ThreadLocal` trên virtual threads, phân biệt chi phí bộ nhớ với khả năng lập lịch, tổ chức vòng đời dữ liệu hợp lý và lựa chọn API thay thế khi cần.

## 2. ThreadLocal lưu gì và lưu ở đâu?

Một đối tượng `ThreadLocal<T>` là **khóa** giúp thread hiện tại truy cập giá trị thuộc riêng nó; khóa dùng chung không có nghĩa value dùng chung. Các phương thức:

| API | Hành vi |
| --- | --- |
| `new ThreadLocal<>()` | Giá trị ban đầu của thread chưa đặt là `null`. |
| `ThreadLocal.withInitial(supplier)` | Tạo giá trị khi thread gọi `get()` lần đầu; sau `remove()`, lần `get()` tiếp theo có thể khởi tạo lại. |
| `get()` | Trả giá trị của thread **đang thực thi**. |
| `set(value)` | Gắn value vào thread hiện tại, không cập nhật thread khác. |
| `remove()` | Xóa liên kết của thread hiện tại với khóa. |

Trong JDK, các liên kết này được quản lý bằng cấu trúc dạng map gắn với đối tượng `Thread`. Trên virtual thread, map đó thuộc **virtual thread**, không thuộc carrier. Chi phí dữ liệu là theo những ThreadLocal **thực sự được sử dụng**, không có nghĩa cứ tạo một virtual thread là ngay lập tức cấp phát buffer của mọi `ThreadLocal.withInitial` khai báo trong chương trình.

Diễn tiến minh họa:

1. Virtual thread V1 gọi `TRACE_ID.set("A")`.
2. V1 chờ I/O và tạm dừng; carrier có thể chuyển sang chạy V2.
3. V2 gọi `TRACE_ID.get()`: nó đọc giá trị riêng của V2, không được tự động thấy `"A"`.
4. V1 tiếp tục chạy trên một carrier khác: `TRACE_ID.get()` vẫn trả `"A"`, cho đến khi V1 thay đổi hoặc xóa giá trị.

**Giới hạn:** `ThreadLocal` bảo vệ tính tách biệt của ánh xạ từng thread, không khiến một object mutable được chia sẻ theo cách khác trở nên thread-safe. Nếu hai ThreadLocal values cùng trỏ một object, mã sửa object đó vẫn phải đồng bộ khi cần.

## 3. Ví dụ Java 21+: dữ liệu tách biệt và sống qua lời gọi hàm

Lưu thành `VirtualThreadLocalDemo.java`:

```java
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public class VirtualThreadLocalDemo {
    private static final ThreadLocal<String> REQUEST_ID = new ThreadLocal<>();

    static String handle(String requestId) {
        REQUEST_ID.set(requestId);
        try {
            return "virtual=" + Thread.currentThread().isVirtual()
                    + ", id=" + readFromNestedMethod();
        } finally {
            REQUEST_ID.remove();
        }
    }

    static String readFromNestedMethod() {
        return REQUEST_ID.get();
    }

    public static void main(String[] args) throws Exception {
        try (ExecutorService executor =
                     Executors.newVirtualThreadPerTaskExecutor()) {
            Future<String> first = executor.submit(() -> handle("REQ-101"));
            Future<String> second = executor.submit(() -> handle("REQ-202"));

            System.out.println(first.get());
            System.out.println(second.get());
        }
        System.out.println("Caller=" + REQUEST_ID.get());
    }
}
```

Biên dịch và chạy bằng JDK 21 trở lên, không cần cờ preview:

```bash
javac -encoding UTF-8 VirtualThreadLocalDemo.java
java VirtualThreadLocalDemo
```

Output chính xác:

```text
virtual=true, id=REQ-101
virtual=true, id=REQ-202
Caller=null
```

`Executors.newVirtualThreadPerTaskExecutor()` tạo một virtual thread mới cho mỗi task. `Future.get()` được đọc tuần tự nên thứ tự hai dòng đầu xác định. `readFromNestedMethod()` nhận context ngầm qua `ThreadLocal` trong cùng virtual thread; main thread không có giá trị đó. Khối `finally` bảo đảm dọn giá trị cả khi xử lý lỗi.

Lưu ý: `REQUEST_ID.remove()` chỉ xóa giá trị ở **thread gọi nó**. Gọi `remove()` ở main thread không thể dọn ThreadLocal của những worker khác.

## 4. Chi phí bộ nhớ và vòng đời trong thực tế

Có ba nhóm chi phí:

- **Bản thân virtual thread:** object, trạng thái thực thi, continuation/stack và tham chiếu khác mà JVM cần quản lý.
- **Cấu trúc lưu ThreadLocal:** metadata và entry cho các khóa được sử dụng.
- **Value và đồ thị object được giữ:** String, byte array, buffer, context, cache, tài nguyên hoặc những object được value trỏ tới.

Có thể hình dung:

```text
Tổng dữ liệu ThreadLocal còn sống ≈
  tổng giá trị và metadata còn được giữ bởi các virtual threads còn sống
```

Tính chất của object sharing và garbage collection khiến đây không phải một công thức đo heap chính xác. Nếu hai value cùng trỏ một immutable object, không tính double dung lượng object đó. Ngược lại, một value rất nhỏ có thể tham chiếu đến một đồ thị object lớn.

**Hai con số phải phân biệt:** số virtual threads *đã tạo tổng cộng* và số thread *đang còn sống cùng thời điểm*. Một triệu tác vụ ngắn chạy theo đợt có thể tạo áp lực **allocation/GC** lớn nhưng không nhất thiết giữ dữ liệu của cả triệu thread trong heap cùng lúc. Ngược lại, hàng chục nghìn virtual threads đang đợi mạng hoặc bị giữ bởi các tham chiếu khác có thể giữ dữ liệu ThreadLocal lâu hơn dự kiến.

### Cache theo thread không còn là cache theo worker

Đây là tình huống dễ mắc nhất khi chuyển từ platform-thread pool sang virtual-thread-per-task.

- Pool 16 platform threads: một cache `ThreadLocal.withInitial` có thể được tái sử dụng qua rất nhiều task chạy lần lượt trên cùng worker.
- Virtual thread cho từng task: mỗi task là một thread khác; cache lần đầu chỉ được dùng lại **trong chính task đó**, sau đó có thể bị loại bỏ cùng thread.
- Nếu một triệu task đều tạo cache 64 KiB, số **lượt cấp phát** và băng thông bộ nhớ rất lớn ngay cả khi không phải một triệu cache tồn tại đồng thời.

Không giải quyết bằng cách tạo pool virtual threads để tái sử dụng buffer. Mô hình khuyến nghị là một virtual thread cho một tác vụ; nếu cần pool tài nguyên đắt tiền, hãy tạo **pool tài nguyên có giới hạn riêng**, độc lập với danh tính thread.

## 5. Ví dụ Java 21+: quan sát chi phí khởi tạo per-task

Lưu thành `VirtualThreadLocalCostDemo.java`:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.atomic.AtomicInteger;

public class VirtualThreadLocalCostDemo {
    private static final AtomicInteger CREATED = new AtomicInteger();

    private static final ThreadLocal<byte[]> BUFFER =
            ThreadLocal.withInitial(() -> {
                CREATED.incrementAndGet();
                return new byte[64 * 1024];
            });

    private static boolean task() {
        try {
            byte[] first = BUFFER.get();
            byte[] second = BUFFER.get();
            return first == second;
        } finally {
            BUFFER.remove();
        }
    }

    public static void main(String[] args) throws Exception {
        List<Future<Boolean>> results = new ArrayList<>();

        try (ExecutorService executor =
                     Executors.newVirtualThreadPerTaskExecutor()) {
            for (int i = 0; i < 4; i++) {
                results.add(executor.submit(
                        VirtualThreadLocalCostDemo::task));
            }
            for (Future<Boolean> result : results) {
                if (!result.get()) {
                    throw new IllegalStateException("Not the same buffer");
                }
            }
        }
        System.out.println("Buffers created: " + CREATED.get());
    }
}
```

```bash
javac -encoding UTF-8 VirtualThreadLocalCostDemo.java
java VirtualThreadLocalCostDemo
```

```text
Buffers created: 4
```

Mỗi virtual thread gọi `get()` hai lần và nhận **cùng một buffer trong thread đó**. Tuy nhiên bốn task tương ứng bốn virtual threads; supplier chạy bốn lần. `AtomicInteger` giúp đếm chính xác trong môi trường đa luồng. Sau `remove()`, nếu thread đó tiếp tục gọi `get()` thì supplier có thể chạy lại và cấp phát một buffer mới.

Bài này dùng số tác vụ nhỏ để chứng minh cơ chế. Đừng tùy tiện tăng bài demo tới hàng trăm nghìn task đồng thời với buffer lớn trên máy có heap hạn chế.

## 6. Cleanup đúng và rủi ro giữ tham chiếu

Một quy tắc hữu ích với context theo tác vụ là **đặt, dùng, dọn trong `finally`**. Đoạn sau là minh họa phương thức nằm trong lớp, không phải chương trình độc lập:

```java
private static final ThreadLocal<String> TRACE_ID = new ThreadLocal<>();

static void process(String traceId) {
    TRACE_ID.set(traceId);
    try {
        doWork();
    } finally {
        TRACE_ID.remove();
    }
}
```

Nếu có context lồng nhau cần quay lại giá trị cũ sau khi xử lý nhánh con, chỉ `remove()` là chưa đủ; phải thiết kế lưu/khôi phục state cha đúng semantics. Tránh để thư viện nằm sâu trong call chain tùy ý thay đổi giá trị được kỳ vọng là bất biến.

**ThreadLocal có gây memory leak vĩnh viễn không?** Không phải cứ thiếu `remove()` trong virtual thread là leak vĩnh viễn. Khi virtual thread đã kết thúc và không còn được giữ tham chiếu, dữ liệu đi cùng nó có thể được GC. Tuy nhiên, nếu thread còn sống lâu (kể cả đang chờ I/O) thì value vẫn có thể được giữ; code chạy trên platform-thread pool cũng có thể giữ state qua nhiều request. Vì vậy cleanup có chủ đích giúp kiểm soát vòng đời và tránh rò dữ liệu giữa task khi code được sử dụng trong nhiều môi trường.

Trong cách triển khai ThreadLocalMap của JDK, key là tham chiếu yếu và value thường là tham chiếu mạnh. Nếu key không còn được tham chiếu ở nơi khác, entry cũ không nhất thiết được dọn ngay; dựa hoàn toàn vào việc GC của key để giải phóng value là thiếu an toàn.

**Đừng nhầm `remove()` với đóng tài nguyên.** Nếu value chứa socket, kết nối hoặc resource `AutoCloseable`, `remove()` chỉ bỏ liên kết; code sở hữu tài nguyên vẫn phải đóng nó (`close()`/`try-with-resources`). Không đưa toàn bộ body dữ liệu hay buffer quá lớn vào ThreadLocal chỉ để tránh truyền tham số.

## 7. ThreadLocal và InheritableThreadLocal khác nhau

`ThreadLocal` thông thường không tự truyền value từ parent thread sang thread mới. `InheritableThreadLocal` hỗ trợ kế thừa **giá trị khởi đầu khi tạo thread**. Trong Java 21, `Thread.ofVirtual()` mặc định kế thừa `InheritableThreadLocal`; muốn tắt có thể gọi `inheritInheritableThreadLocals(false)`.

Lưu thành `VirtualInheritanceDemo.java`:

```java
public class VirtualInheritanceDemo {
    private static final InheritableThreadLocal<String> TRACE =
            new InheritableThreadLocal<>();

    public static void main(String[] args) throws InterruptedException {
        TRACE.set("parent");
        try {
            Thread inheriting = Thread.ofVirtual().start(
                    () -> System.out.println("Inherited: " + TRACE.get()));
            inheriting.join();

            Thread isolated = Thread.ofVirtual()
                    .inheritInheritableThreadLocals(false)
                    .start(() -> System.out.println("Isolated : " + TRACE.get()));
            isolated.join();
        } finally {
            TRACE.remove();
        }
    }
}
```

```bash
javac -encoding UTF-8 VirtualInheritanceDemo.java
java VirtualInheritanceDemo
```

```text
Inherited: parent
Isolated : null
```

Điều cần nhớ:

- Giá trị được kế thừa khi thread mới được tạo, **không đồng bộ liên tục** mỗi khi thread cha gọi `set()`.
- Với mutable object, mặc định child có thể nhận cùng tham chiếu với parent; hai thread sửa object đó có thể gây race. Đây không phải deep copy.
- Sao chép các ánh xạ inheritable vào nhiều virtual threads có chi phí, nhất là khi parent có nhiều entries.
- Với executor, cần biết thread **thực sự tạo virtual thread** là thread nào và tạo lúc nào; đừng mặc định mọi context ở nơi gọi `submit()` đều được tự động truyền đúng trong mọi executor và cơ chế async.

Không dùng `InheritableThreadLocal` như một phương án truyền context tổng quát qua mọi async boundary. Hãy xác định rõ ai tạo thread, ai sở hữu value, và value có được phép chia sẻ hay không.

## 8. Chọn phương án khác khi cần truyền context hoặc tái sử dụng tài nguyên

| Mục đích | Cách phù hợp để cân nhắc | Lưu ý |
| --- | --- | --- |
| Chỉ vài phương thức cần một giá trị | Truyền tham số tường minh hoặc record immutable | Dễ biết ownership, lifetime, dễ test. |
| Thư viện Java 21 hiện hữu dựa vào context cục bộ | `ThreadLocal` với `finally/remove` | Tương thích và tiện nhưng phải kiểm soát kích thước value. |
| Ngữ cảnh chỉ đọc truyền xuyên các phương thức | `ScopedValue` từ Java 25 | Lifetime theo lexical scope, giảm trạng thái ẩn có thể thay đổi. |
| Tài nguyên dùng chung và đắt tiền | Pool tài nguyên bounded, service shared với thread safety rõ ràng | Dùng chung thực sự giữa task; quản lý cấp phát và đóng. |
| Giới hạn số tác vụ dùng tài nguyên | `Semaphore` hoặc capacity limit | Không cần pool virtual threads để giới hạn DB/network. |

### ScopedValue: phân biệt phiên bản Java

`ScopedValue` có mặt ở dạng **preview trong Java 21–24**; API preview có thể thay đổi giữa các bản và yêu cầu bật preview. Nó trở thành API chuẩn từ **Java 25** (JEP 506). Do đó các ví dụ runnable bên trên dùng Java 21+ không cần preview; đoạn sau chỉ minh họa một phần của lớp trên **JDK 25+**, không phải tệp độc lập Java 21:

```java
private static final ScopedValue<String> TRACE_ID = ScopedValue.newInstance();

static void dispatch() {
    ScopedValue.where(TRACE_ID, "REQ-7")
            .run(() -> System.out.println(TRACE_ID.get()));
}
```

Giá trị ràng buộc tồn tại trong vùng `run` và được kết thúc tự động khi ra khỏi vùng. Đây là lựa chọn rất phù hợp cho ngữ cảnh chỉ đọc. `ScopedValue` không thể thay thế một cách máy móc các use case cần thay đổi tùy ý state cục bộ giữa quá trình thực thi; lúc đó phải thiết kế API và state theo nhu cầu thực.

## 9. Sai lầm thường gặp

**“Giá trị ThreadLocal chạy theo carrier.”** Sai. Nó gắn với virtual thread; scheduler thay carrier không làm các virtual threads dùng chung value.

**“Có một triệu virtual threads nghĩa là có một triệu bản sao của mọi ThreadLocal.”** Sai. Values thường được khởi tạo theo nhu cầu; lượng dữ liệu phụ thuộc những ThreadLocal được truy cập và số thread còn sống. Nhưng nếu mọi task đều `get()` cache lớn, chi phí thực sự rất cao.

**“static final ThreadLocal đồng nghĩa static singleton value.”** Sai. Đối tượng khóa là static, còn mapping value vẫn độc lập cho từng thread.

**“withInitial chỉ chạy một lần.”** Sai. Nó chạy theo thread ở lần khởi tạo cần thiết và có thể chạy lại sau `remove()`.

**“ThreadLocal làm dữ liệu mutable bên trong an toàn.”** Sai. Nếu object được chia sẻ bằng một con đường khác hoặc qua `InheritableThreadLocal`, cần kiểm soát data race riêng.

**“remove sẽ đóng kết nối và trả tài nguyên về pool.”** Sai. `remove()` không `close()` value và không quản lý lifecycle của pool.

**“Giữ ThreadLocal cache và pool virtual threads để tái sử dụng.”** Không phù hợp với mô hình virtual-thread-per-task; quản lý cache hoặc tài nguyên dùng chung ở lớp abstraction khác.

## 10. Đo đạc và ra quyết định

Trước khi đưa `ThreadLocal` vào workload có nhiều virtual threads:

1. Đếm số virtual threads **còn sống đồng thời**, không chỉ số task đã xử lý.
2. Đo kích thước value và những object giữ qua tham chiếu; phân biệt object chia sẻ và object tạo riêng từng task.
3. Theo dõi allocation rate, heap live set, GC pauses, p95/p99 latency, đặc biệt lúc tải cao và các task chờ I/O lâu.
4. Dùng JFR, Java heap profiler hoặc một bộ đếm khởi tạo có kiểm soát để phát hiện cache được tạo mới theo từng task.
5. Kiểm tra giá trị có bị giữ quá thời gian cần thiết, có cleanup đúng khi exception hay không.
6. Tách bạch mục đích **truyền ngữ cảnh** với mục đích **tái sử dụng tài nguyên**. Trường hợp thứ hai thường nên có pool/capacity độc lập.
7. Nếu context chỉ đọc và dự án đã ở Java 25+, cân nhắc `ScopedValue`. Với dự án Java 21, cân nhắc tham số tường minh hoặc `ThreadLocal` có scope rõ ràng.

Virtual threads cải thiện khả năng mở rộng của code blocking I/O, không biến phép tính CPU-bound thành nhanh hơn, và cũng không gỡ bỏ giới hạn của database/network phía sau.

## 11. Câu hỏi tự kiểm tra

**Hỏi:** V1 tạm dừng, V2 được chạy trên cùng carrier. V2 có thấy `ThreadLocal` của V1 không?  
**Đáp:** Không, vì ThreadLocal thuộc từng virtual thread.

**Hỏi:** 20.000 virtual threads mỗi thread giữ 128 KiB có ảnh hưởng gì?  
**Đáp:** Payload có thể lên tới hàng GiB nếu tất cả cùng sống và giữ giá trị; còn phải tính metadata, object khác và áp lực GC.

**Hỏi:** Virtual thread kết thúc nhưng không gọi `remove()` có nghĩa chắc chắn memory leak vĩnh viễn?  
**Đáp:** Không. Thread và dữ liệu không còn được giữ tham chiếu có thể được thu gom. Vấn đề là thời gian dữ liệu sống và số thread còn hoạt động, cùng khả năng code được dùng trên thread lâu sống.

**Hỏi:** `InheritableThreadLocal` có sao chép sâu một `ArrayList` mutable từ cha sang con?  
**Đáp:** Không theo mặc định; child có thể chia sẻ tham chiếu, cần thiết kế tránh race.

**Hỏi:** Trong Java 21, có thể dùng trực tiếp `ScopedValue` như API ổn định không?  
**Đáp:** Chưa. Java 21–24 là preview; Java 25 trở đi mới có API chuẩn.

**Ghi nhớ:** `ThreadLocal` vẫn hoạt động trên virtual threads, nhưng mỗi virtual thread có dữ liệu cục bộ của riêng nó. Khi tăng số task đồng thời, hãy đặc biệt thận trọng với **cache theo thread, buffer lớn, khả năng kế thừa context và vòng đời cleanup**.

### Tài liệu tham khảo

- [OpenJDK JEP 444: Virtual Threads](https://openjdk.org/jeps/444)
- [Java 21 API: ThreadLocal](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/ThreadLocal.html)
- [Java 21 API: Thread.Builder.OfVirtual](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Thread.Builder.OfVirtual.html)
- [OpenJDK JEP 506: Scoped Values](https://openjdk.org/jeps/506)
- [Java 25 API: ScopedValue](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/ScopedValue.html)
