# Thread name trong Java Logging

## 1. Thread name là gì và vì sao quan trọng?

Trong Java, mỗi đối tượng `Thread` có một **tên luồng** (`thread name`) kiểu `String`. Tên này giúp con người nhận ra luồng nào đang thực thi một đoạn mã khi đọc log, thread dump, thông tin trong debugger hoặc công cụ giám sát.

Một ứng dụng có thể thực hiện nhiều tác vụ đồng thời. Các dòng log sẽ xen kẽ theo thời gian; nếu chỉ có mức log và thông điệp, rất khó biết dòng nào thuộc cùng một luồng. Ví dụ minh họa:

```text
14:20:01.123 [orders-worker-1] INFO  OrderService - Started order 101
14:20:01.125 [orders-worker-2] INFO  OrderService - Started order 102
14:20:01.130 [orders-worker-1] INFO  OrderService - Finished order 101
```

Tên `orders-worker-1` giúp nhận ra dòng thứ nhất và thứ ba được phát ra từ cùng một worker. **Điều đó không tự chứng minh chúng thuộc cùng một request:** thread pool có thể tái sử dụng worker để xử lý nhiều tác vụ khác nhau.

Thread name là **nhãn chẩn đoán**, không phải định danh nghiệp vụ, mã request, trace ID hoặc cơ chế đồng bộ. Tên có thể bị thay đổi và nhiều luồng có thể trùng tên nếu chương trình đặt như vậy.

## 2. API Java liên quan

| API | Tác dụng | Lưu ý |
| --- | --- | --- |
| `Thread.currentThread()` | Lấy đối tượng `Thread` đang chạy đoạn mã hiện tại | Dùng trong đoạn code tạo log để xác định luồng phát sinh sự kiện |
| `thread.getName()` | Đọc tên hiện tại của luồng | Trả về `String`, không bảo đảm duy nhất |
| `thread.setName("...")` | Thay đổi tên một luồng đã tạo | Có hiệu lực với các lần đọc tên sau đó; cần cẩn trọng khi luồng được tái sử dụng |
| `new Thread(runnable, "name")` | Tạo platform thread với tên được chỉ định | Phù hợp khi tự sở hữu vòng đời luồng |
| `ThreadFactory` | Quy định cách đặt tên cho các luồng do executor tạo | Là cách phù hợp với thread pool |
| `Thread.ofVirtual().name(...)` | Đặt tên virtual thread | Có từ Java 21; không biên dịch trên Java 17 |

Tên mặc định do JDK hoặc framework sinh ra có thể như `main`, `Thread-0`, `pool-1-thread-1` hoặc `ForkJoinPool.commonPool-worker-1`. **Không dựa vào chính xác một mẫu tên mặc định** để xây logic: JDK, executor và cấu hình ứng dụng có thể quyết định các mẫu khác nhau.

Việc gọi `getName()` chỉ đọc metadata của thread. Nó không thay đổi lịch chạy, độ ưu tiên hay trạng thái chạy của thread. Việc gọi `setName()` cũng không làm task chạy nhanh hơn hoặc tạo thread mới.

## 3. Ví dụ Java 17: đặt tên thread trực tiếp

Lưu mã sau thành `ThreadNameDemo.java`:

```java
public class ThreadNameDemo {
    public static void main(String[] args) throws InterruptedException {
        Thread worker = new Thread(
                () -> System.out.println(
                        "Running in: " + Thread.currentThread().getName()),
                "orders-worker-1"
        );

        worker.start();
        worker.join();

        System.out.println(
                "Running in: " + Thread.currentThread().getName());
    }
}
```

Biên dịch và chạy:

```bash
javac ThreadNameDemo.java
java ThreadNameDemo
```

`stdout`:

```text
Running in: orders-worker-1
Running in: main
```

Giải thích:

1. Constructor `new Thread(task, "orders-worker-1")` gắn tên vào thread trước khi chạy.
2. `start()` yêu cầu JVM khởi chạy task trên thread mới; `Thread.currentThread()` trong lambda chính là thread `orders-worker-1`.
3. `join()` đợi worker hoàn tất, nên thứ tự hai dòng output trong ví dụ được xác định.
4. Lời gọi `Thread.currentThread()` sau `join()` nằm trong `main`, nên hiện tên `main`.

Trong ứng dụng thật, logging framework thường tự thêm tên thread; không cần tự nối `Thread.currentThread().getName()` vào mọi thông điệp.

## 4. Hiển thị thread name trong log

### 4.1. Logback với SLF4J

Khi ứng dụng sử dụng **SLF4J + Logback**, cấu hình mẫu `src/main/resources/logback.xml` có thể là:

```xml
<configuration>
    <appender name="STDOUT" class="ch.qos.logback.core.ConsoleAppender">
        <encoder>
            <pattern>%d{HH:mm:ss.SSS} [%thread] %-5level %logger{36} - %msg%n</pattern>
        </encoder>
    </appender>
    <root level="INFO">
        <appender-ref ref="STDOUT"/>
    </root>
</configuration>
```

Trong mẫu này:

- `%d{HH:mm:ss.SSS}`: thời điểm log được tạo.
- `[%thread]`: tên thread gắn với sự kiện log; Logback cũng hỗ trợ dạng ngắn `%t`.
- `%-5level`: mức log, căn theo độ rộng tối thiểu năm ký tự.
- `%logger{36}`: tên logger được viết gọn; `%msg%n`: thông điệp và xuống dòng.

Đoạn sử dụng logger dưới đây **minh họa trong một class đã cấu hình SLF4J/Logback**, không phải chương trình độc lập chỉ cần JDK:

```java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

public class OrderService {
    private static final Logger log =
            LoggerFactory.getLogger(OrderService.class);

    public void process(long orderId) {
        log.info("Processing order {}", orderId);
    }
}
```

Khi `process(101)` chạy trên thread có tên `orders-worker-1`, một dòng log có thể trông như sau (timestamp chỉ mang tính minh họa):

```text
14:20:01.123 [orders-worker-1] INFO  OrderService - Processing order 101
```

Từng logging framework có cú pháp cấu hình riêng; mẫu `%thread` ở trên dành cho **Logback**. Cấu hình logger, thư viện và appender phải có trong dự án thì mẫu này mới phát huy tác dụng.

### 4.2. Khi nào nên ghi rõ thread name?

Nên bật trường tên thread trong pattern/structured logging khi cần theo dõi lỗi race condition, thread pool, xử lý nền, deadlock hoặc hoạt động bất đồng bộ. Với JSON logs, ghi tên vào một trường riêng như `thread.name` hoặc `threadName` để lọc được theo thuộc tính; tên trường phụ thuộc schema logging của hệ thống.

Không dùng tên thread như một trường chứa thông tin nhạy cảm: nó có thể xuất hiện trong log, thread dump và công cụ giám sát.

## 5. Đặt tên cho thread pool bằng ThreadFactory

Trong ứng dụng server, thường **executor quản lý vòng đời thread**. Vì vậy, thay vì tạo `new Thread(...)` cho mỗi công việc, hãy cung cấp `ThreadFactory` khi xây executor. Một tên ổn định dạng `report-worker-1`, `report-worker-2` làm rõ vai trò của nhóm luồng và số thứ tự trong nhóm.

Ví dụ Java 17 độc lập, lưu thành `NamedThreadPoolDemo.java`:

```java
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.ThreadFactory;
import java.util.concurrent.atomic.AtomicInteger;

public class NamedThreadPoolDemo {
    public static void main(String[] args) throws Exception {
        AtomicInteger nextNumber = new AtomicInteger(1);
        ThreadFactory defaults = Executors.defaultThreadFactory();
        ThreadFactory namedFactory = task -> {
            Thread thread = defaults.newThread(task);
            thread.setName("report-worker-" + nextNumber.getAndIncrement());
            return thread;
        };

        ExecutorService executor =
                Executors.newSingleThreadExecutor(namedFactory);
        try {
            Future<String> first = executor.submit(() ->
                    "job-A: " + Thread.currentThread().getName());
            Future<String> second = executor.submit(() ->
                    "job-B: " + Thread.currentThread().getName());

            System.out.println(first.get());
            System.out.println(second.get());
        } finally {
            executor.shutdown();
        }
    }
}
```

Chạy:

```bash
javac NamedThreadPoolDemo.java
java NamedThreadPoolDemo
```

`stdout`:

```text
job-A: report-worker-1
job-B: report-worker-1
```

Đây là **single-thread executor**, nên cả hai tác vụ được xử lý lần lượt trên cùng một worker được tái sử dụng. `Future.get()` cũng bảo đảm kết quả đã sẵn sàng trước khi in. Nếu đổi sang `Executors.newFixedThreadPool(2, namedFactory)`, hệ thống có thể tạo `report-worker-1` và `report-worker-2`, nhưng **thứ tự gán task cho từng thread không được bảo đảm**; không nên viết test dựa trên thứ tự đó.

Dùng `AtomicInteger` vì `ThreadFactory.newThread(...)` có thể được gọi từ nhiều luồng. Bọc `Executors.defaultThreadFactory()` giữ các mặc định phù hợp của factory cơ sở, rồi chỉ tùy chỉnh tên. Luôn quản lý vòng đời executor và gọi `shutdown()` khi không còn dùng.

## 6. Đổi tên tạm thời trong worker: phải khôi phục

Một luồng trong pool có thể phục vụ request A rồi đến request B. Nếu đổi tên thread thành `request-A` mà không khôi phục, log của request B có thể vẫn mang tên request A, gây sai lệch khi điều tra.

Ví dụ Java 17 độc lập, lưu thành `TemporaryThreadNameDemo.java`:

```java
public class TemporaryThreadNameDemo {
    public static void main(String[] args) {
        Thread current = Thread.currentThread();
        String originalName = current.getName();

        try {
            current.setName("batch-export-42");
            System.out.println("Inside: " + current.getName());
        } finally {
            current.setName(originalName);
        }

        System.out.println("After: " + current.getName());
    }
}
```

Chạy:

```bash
javac TemporaryThreadNameDemo.java
java TemporaryThreadNameDemo
```

`stdout`:

```text
Inside: batch-export-42
After: main
```

Mẫu `try/finally` bảo đảm khôi phục tên ngay cả khi tác vụ ném exception. Tuy nhiên, nếu mục tiêu là theo dõi **request ID**, nên dùng cơ chế logging context phù hợp thay vì đổi tên thread cho mỗi request; tên thread chủ yếu mô tả worker hay vai trò thực thi.

## 7. Tên thread trong tác vụ bất đồng bộ

Khi công việc vượt ranh giới thread, **tên thread có thể thay đổi** dù vẫn thuộc cùng một luồng nghiệp vụ:

- `ExecutorService.submit(...)`: tên lấy từ thread do executor chọn.
- `CompletableFuture.supplyAsync(...)` không truyền `Executor`: mặc định thường chạy trên `ForkJoinPool.commonPool()` (với các điều kiện thực thi thích hợp), nên tên không nhất thiết giống thread gọi.
- `CompletableFuture.supplyAsync(..., executor)`: tên phản ánh worker của executor được cung cấp.
- Framework web, scheduler và thư viện reactive có thể chuyển công việc qua nhiều thread; mỗi dòng log hiển thị thread thực sự tạo sự kiện đó.

Ví dụ chuỗi sự kiện có thể trông như:

```text
[http-worker-3]  INFO  Request accepted
[report-worker-2] INFO  Report generated
[http-worker-3]  INFO  Response returned
```

Từ tên thread một mình **không thể khẳng định** ba dòng đó thuộc cùng request. Dùng thêm correlation ID / trace ID để liên kết chúng.

### Virtual threads (Java 21 trở lên)

Virtual thread cũng là `Thread` và có `getName()`. Không nên giả định mọi virtual thread đều có tên tự sinh dễ đọc: cấu hình khởi tạo có thể để tên rỗng. Có thể đặt tên trực tiếp để tiện chẩn đoán.

Ví dụ riêng cho **Java 21+**, lưu `VirtualThreadNameDemo.java`:

```java
public class VirtualThreadNameDemo {
    public static void main(String[] args) throws InterruptedException {
        Thread virtualWorker = Thread.ofVirtual()
                .name("virtual-report-1")
                .start(() ->
                        System.out.println(Thread.currentThread().getName()));

        virtualWorker.join();
    }
}
```

```bash
javac VirtualThreadNameDemo.java
java VirtualThreadNameDemo
```

`stdout`:

```text
virtual-report-1
```

Tên ở đây là tên **virtual thread đang thực thi tác vụ**, không phải tên carrier/platform thread hỗ trợ chạy virtual thread. Virtual thread có thể được thực thi trên các carrier khác nhau theo thời gian. Trên Java 17, ví dụ này không biên dịch được vì chưa có API `Thread.ofVirtual()`.

## 8. Thread name và MDC/trace ID: hai mục đích khác nhau

| Dữ liệu | Trả lời câu hỏi | Hạn chế |
| --- | --- | --- |
| Thread name | “Đoạn mã này đang chạy trên worker nào?” | Worker có thể xử lý nhiều request; một request có thể dùng nhiều worker |
| MDC `requestId` | “Dòng log này thuộc request/tác vụ logic nào?” | Cần gắn, truyền context qua ranh giới async và dọn sạch |
| Trace ID | “Các hoạt động có liên quan xuyên thread/service nào?” | Cần tracing/correlation instrumentation |

Với SLF4J MDC, mã sau chỉ là **đoạn minh họa tích hợp** cần thư viện SLF4J và logging backend hỗ trợ MDC:

```java
import org.slf4j.MDC;

MDC.put("requestId", requestId);
try {
    log.info("Starting calculation");
    performCalculation();
} finally {
    MDC.remove("requestId");
}
```

Nếu dùng Logback, có thể thêm `%X{requestId}` vào pattern, chẳng hạn:

```text
%d{HH:mm:ss.SSS} [%thread] [request=%X{requestId}] %-5level %logger - %msg%n
```

MDC của các hệ thống logging thông dụng gắn với context thực thi của thread và **không tự động được truyền sang mọi executor/CompletableFuture**. Khi nhảy thread, cần cơ chế propagation được thiết kế cho framework đang dùng; khi worker tái sử dụng, phải dọn MDC ở `finally` để tránh rò context. `requestId` và `log`/`performCalculation()` trong ví dụ trên là biến/phương thức của ứng dụng, không phải class chạy độc lập.

## 9. Quy ước đặt tên hữu ích

Một tên dễ hiểu thường gồm **vai trò + số thứ tự**, chẳng hạn `billing-worker-1`, `email-sender-2`, `scheduler-cleanup-1`. Với nhiều pool, mỗi pool nên có prefix riêng. Giữ tên ngắn, ổn định, nhất quán và dễ tìm kiếm; nếu phải đưa định danh tác vụ vào tên tạm thời, khôi phục sau khi chạy.

Tránh dùng tên như `Thread-1` do tự đặt ở nhiều pool khác nhau vì khó phân biệt. Không gắn mật khẩu, token, email khách hàng hay dữ liệu cá nhân vào tên thread. Không xây business logic kiểu `if (thread.getName().contains("admin"))`: tên là dữ liệu có thể đổi và không bảo đảm tính duy nhất hay quyền hạn.

Khi cần phân tích sự cố đa luồng, phối hợp **timestamp + level + logger + thread name + request/trace ID**. Thread dump/JFR giúp xem thread nào đang chờ khóa, đang chạy hoặc bị nghẽn; log giúp lần lại thứ tự các sự kiện.

## 10. Lỗi thường gặp và cách kiểm tra

1. **Không thấy tên thread trong log:** kiểm tra pattern/appender của logging backend có xuất `%thread` hay trường tương đương chưa; chỉ đặt `setName()` chưa đủ để log tự hiển thị.
2. **Mọi task đều có cùng tên:** single-thread executor cố ý tái sử dụng một worker. Trong fixed pool, số tên phụ thuộc số worker đã được tạo; không suy ra số task từ số tên.
3. **Tên thread bị “dính” từ task trước:** có thể đã đổi tên trên pooled thread mà quên khôi phục trong `finally`.
4. **Dòng log của một request mang nhiều tên:** có thể request chuyển qua executor, callback, scheduler hoặc event loop. Dùng correlation ID/trace ID để nối lại.
5. **Nhầm tên với định danh độc nhất:** hai `Thread` khác nhau có thể cùng tên; tên cũng có thể đổi trong lúc ứng dụng chạy.
6. **Test không ổn định:** task chạy song song không bảo đảm thứ tự log; dùng `join()`, `Future.get()` hoặc công cụ đồng bộ phù hợp để xác định điểm hoàn tất trong test.
7. **MDC sai ở request kế tiếp:** dọn MDC và propagate context đúng ở các task async. Đổi tên thread không giải quyết việc truyền MDC.

**Tự kiểm tra nhanh:** Khi thấy log `[report-worker-1] Finished task`, có thể kết luận sự kiện được ghi bởi worker có tên `report-worker-1`. Không thể chỉ từ đó kết luận task thuộc request nào, worker là duy nhất trong hệ thống hay thread sẽ tiếp tục xử lý cùng request. Hãy dùng thêm mã tương quan và thông tin nghiệp vụ đã được ghi log an toàn.
