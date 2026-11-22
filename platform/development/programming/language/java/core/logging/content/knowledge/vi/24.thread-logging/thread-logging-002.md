# Thread ID trong Java Logging

## 1. Thread ID là gì?

**Thread ID** là số định danh của một đối tượng luồng `java.lang.Thread` trong JVM. Khi nhiều luồng ghi log đan xen, trường `threadId` giúp xác định **luồng Java nào đã thực thi câu lệnh ghi log**. Đây là thông tin chẩn đoán quan trọng khi theo dõi thứ tự sự kiện, lỗi đồng thời, tranh chấp tài nguyên và thread pool.

Các thuộc tính cần nhớ:

- ID có kiểu `long`, là số dương, được JVM gán khi tạo `Thread` và không đổi trong vòng đời của luồng.
- Các luồng đang tồn tại có ID khác nhau trong cùng JVM. Không dùng ID như định danh toàn cục cho nhiều JVM, container hoặc nhiều lần khởi động ứng dụng; không dựa vào giả định ID vĩnh viễn không được tái sử dụng.
- `threadId` và `threadName` là hai trường khác nhau. Tên có thể trùng, đổi được và có ý nghĩa mô tả; ID là số giúp phân biệt luồng.
- Java Thread ID **không được bảo đảm bằng** thread ID của hệ điều hành (OS TID). Không đối chiếu trực tiếp ID trong log Java với `top -H`/`ps -L` hoặc công cụ hệ điều hành nếu chưa xác định cách ánh xạ.
- ID chỉ trả lời câu hỏi “luồng nào chạy đoạn code này?”. Một HTTP request, message hay transaction có thể đi qua nhiều luồng; một luồng trong pool có thể xử lý nhiều yêu cầu theo thời gian.

Ví dụ cấu trúc log hữu ích:

~~~text
2026-11-10T09:40:00Z level=INFO service=checkout instance=checkout-2 threadId=37 threadName=worker-2 traceId=8f2a... event=payment_start
~~~

Trong ví dụ, `threadId=37` là ID minh họa, không phải giá trị cố định. `traceId` liên kết các sự kiện thuộc cùng thao tác nghiệp vụ; `threadId` mô tả môi trường thực thi của **từng** sự kiện.

## 2. Lấy ID của luồng đang chạy

| Phiên bản Java | API nên dùng | Ghi chú |
| --- | --- | --- |
| Java 17–18 | `Thread.currentThread().getId()` | Trả về `long`; hoạt động với chương trình Java 17. |
| Java 19+ | `Thread.currentThread().threadId()` | API `final` được bổ sung từ Java 19, nên ưu tiên cho code mới. |
| Java 19+ với code cũ | `getId()` vẫn tồn tại | `Thread.getId()` được đánh dấu deprecated từ Java 19 vì method có thể bị subclass override; không nên dùng cho code mới khi đã có `threadId()`. |

Đoạn mã minh họa trong một phương thức chạy trên Java 17:

~~~java
Thread current = Thread.currentThread();
long id = current.getId();
String name = current.getName();
System.out.printf("threadId=%d threadName=%s%n", id, name);
~~~

Trên Java 19+, thay dòng lấy ID bằng:

~~~java
long id = Thread.currentThread().threadId();
~~~

**Phải lấy ID tại điểm xảy ra sự kiện.** Nếu ở luồng `main` bạn gọi `worker.getId()`, kết quả là ID của đối tượng `worker`, không phải ID của luồng `main` đang ghi log. Dùng `Thread.currentThread()` để gắn ID của luồng thực sự đang thực thi câu lệnh.

Không giả định số bắt đầu từ 1, các ID liên tiếp hoặc thứ tự ID phản ánh thời điểm công việc được xử lý. Không ép kiểu `long` sang `int`; kiểu `int` có thể không đủ để giữ giá trị ID.

## 3. Ghi Thread ID bằng java.util.logging (Java 17, không cần thư viện ngoài)

Trong JUL (Java Util Logging), mỗi `LogRecord` ghi nhận ID của luồng phát sinh sự kiện. Từ Java 16, dùng `LogRecord.getLongThreadID()` để lấy đúng kiểu `long` khi xây dựng formatter. API `LogRecord.getThreadID()` trả về `int` đã deprecated từ Java 16 và có thể trả về giá trị tổng hợp khác với Java Thread ID thực.

Tạo tệp **ThreadIdLoggingDemo.java**:

~~~java
import java.util.logging.ConsoleHandler;
import java.util.logging.Formatter;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public final class ThreadIdLoggingDemo {
    private static final Logger LOG =
            Logger.getLogger(ThreadIdLoggingDemo.class.getName());

    public static void main(String[] args) throws InterruptedException {
        LOG.setUseParentHandlers(false);
        LOG.setLevel(Level.INFO);

        ConsoleHandler handler = new ConsoleHandler();
        handler.setLevel(Level.INFO);
        handler.setFormatter(new Formatter() {
            @Override
            public String format(LogRecord record) {
                return "threadId=" + record.getLongThreadID()
                        + " level=" + record.getLevel().getName()
                        + " " + formatMessage(record)
                        + System.lineSeparator();
            }
        });
        LOG.addHandler(handler);

        Thread worker = new Thread(() -> {
            String name = Thread.currentThread().getName();
            LOG.info(() -> "event=start threadName=" + name);
            LOG.info(() -> "event=end threadName=" + name);
        }, "logging-worker");

        worker.start();
        worker.join();
        handler.flush();
    }
}
~~~

Biên dịch và chạy bằng JDK 17+:

~~~bash
javac ThreadIdLoggingDemo.java
java ThreadIdLoggingDemo
~~~

Dạng kết quả (giá trị ID thực tế do JVM quyết định, **không** in nguyên văn phần trong ngoặc nhọn):

~~~text
threadId=<ID dương> level=INFO event=start threadName=logging-worker
threadId=<cùng ID> level=INFO event=end threadName=logging-worker
~~~

Hai bản ghi cùng ID vì chúng được phát ra trong **cùng một thread**. `ConsoleHandler` mặc định ghi ra standard error; việc hiển thị cùng terminal với standard output không làm thay đổi ý nghĩa Thread ID.

**Giải thích cơ chế:**

1. `new Thread(..., "logging-worker")` tạo một luồng có tên dễ đọc.
2. `worker.start()` thực thi `Runnable` trên luồng mới; trong `Runnable`, `Thread.currentThread()` trỏ đến chính luồng đó.
3. `LOG.info(...)` tạo bản ghi với thông tin luồng phát sinh; formatter truy xuất `record.getLongThreadID()`.
4. `worker.join()` khiến `main` chờ luồng hoàn tất để ví dụ không kết thúc sớm.
5. `LOG.setUseParentHandlers(false)` tránh việc logger cha in cùng sự kiện lần thứ hai bằng formatter mặc định.

Việc ghi trực tiếp `Thread.currentThread().getId()` vào nội dung thông điệp cũng hợp lệ trên Java 17:

~~~java
Thread t = Thread.currentThread();
LOG.info(() -> "event=validate threadId=" + t.getId()
        + " threadName=" + t.getName());
~~~

Dùng formatter là lựa chọn tốt khi muốn một trường `threadId` nhất quán ở **mọi bản ghi**, kể cả khi lập trình viên quên thêm ID vào từng câu lệnh. Dùng message là cách đơn giản khi chỉ cần vài điểm log. Trong hệ thống thực tế, hãy chuẩn hóa trường ở layout/encoder hoặc cấu hình logging chung để tránh lặp ID giữa cả metadata lẫn message.

## 4. Thread ID trong thread pool: một luồng có thể xử lý nhiều việc

`ExecutorService` thường tái sử dụng luồng. Vì thế hai tác vụ có `taskId` khác nhau **có thể có cùng** `threadId`. Đó là hành vi đúng, không phải lỗi trùng ID.

Tạo tệp **PoolThreadIdDemo.java**:

~~~java
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;

public final class PoolThreadIdDemo {
    public static void main(String[] args) throws Exception {
        ExecutorService pool = Executors.newSingleThreadExecutor();
        try {
            for (int i = 1; i <= 3; i++) {
                final int taskId = i;
                pool.submit(() -> {
                    long threadId = Thread.currentThread().getId();
                    System.out.printf(
                            "taskId=%d threadId=%d%n", taskId, threadId);
                }).get();
            }
        } finally {
            pool.shutdown();
            if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
                pool.shutdownNow();
            }
        }
    }
}
~~~

~~~bash
javac PoolThreadIdDemo.java
java PoolThreadIdDemo
~~~

Dạng đầu ra:

~~~text
taskId=1 threadId=<N>
taskId=2 threadId=<N>
taskId=3 threadId=<N>
~~~

`<N>` ở cả ba dòng chỉ cùng một giá trị ID dương trong lần chạy bình thường: executor một luồng xử lý các tác vụ lần lượt, và `Future.get()` chờ xong từng tác vụ. Không mặc định kết quả này đúng cho pool nhiều luồng hoặc pool có luồng bị thay thế sau lỗi.

Với pool nhiều luồng, log có thể đan xen. Muốn truy lỗi một yêu cầu, ghi thêm `requestId` hoặc `traceId` do ứng dụng tạo/cấp; đừng dựa vào `threadId` để ghép toàn bộ vòng đời request.

## 5. SLF4J/Logback: thêm ID vào message hoặc MDC

Các framework logging khác nhau có pattern riêng. Với Logback, `%thread` thường hiển thị **tên** luồng, không phải số Java Thread ID. Để có trường số, bạn có thể ghi trực tiếp vào message hoặc đưa ID vào MDC (Mapped Diagnostic Context).

**Cách 1 — trực tiếp trong log (minh họa, cần có SLF4J và biến `log`):**

~~~java
long threadId = Thread.currentThread().getId(); // Java 17
log.info("event=order_validate threadId={} orderId={}", threadId, orderId);
~~~

Đây là đoạn mã trong ứng dụng đã cấu hình SLF4J; không phải chương trình Java SE độc lập. Trên Java 19+, có thể thay `getId()` bằng `threadId()`.

**Cách 2 — đặt trong MDC cho những log phát ra trong cùng phạm vi:**

~~~java
import org.slf4j.MDC;

// Trong phương thức xử lý, đã có logger SLF4J và biến orderId.
String id = Long.toString(Thread.currentThread().getId());
MDC.put("threadId", id);
try {
    log.info("event=order_validate orderId={}", orderId);
    // Các log khác cùng thread, trong khối này, cũng đọc được MDC.
} finally {
    MDC.remove("threadId");
}
~~~

Một cấu hình pattern Logback minh họa:

~~~text
%d{ISO8601} %-5level threadId=%X{threadId} threadName=%thread %logger - %msg%n
~~~

`%X{threadId}` đọc **giá trị ứng dụng chủ động đặt vào MDC**; nó không tự động gọi `Thread.threadId()`. Phải đặt MDC trước khi ghi log và xóa trong `finally` để không rò context sang tác vụ tiếp theo trên cùng thread pool. Nếu có nhiều lớp cùng sử dụng khóa `threadId`, nên lưu giá trị cũ và khôi phục đúng phạm vi thay vì xóa tùy tiện.

MDC thường gắn với thread hiện tại; khi chạy bất đồng bộ hoặc chuyển sang luồng khác, **không được mặc định context sẽ tự truyền theo**. Cần cơ chế context propagation phù hợp với framework. `requestId`/`traceId` phải được truyền qua ranh giới async nếu muốn theo dõi cùng một giao dịch; copy lại `threadId` từ thread trước sẽ làm sai thông tin thực thi.

## 6. Virtual thread (Java 21+)

Virtual thread vẫn là `java.lang.Thread` và vẫn có Java Thread ID riêng. `Thread.currentThread().threadId()` trên virtual thread trả về ID của **virtual thread hiện tại**, không phải ID của platform thread đang làm carrier cho nó. Trong suốt vòng đời, virtual thread có thể được gắn hoặc tháo khỏi các carrier khác nhau; không dùng carrier thread để suy ra danh tính yêu cầu.

Tạo tệp **VirtualThreadIdDemo.java** (cần JDK 21+):

~~~java
public final class VirtualThreadIdDemo {
    public static void main(String[] args) throws InterruptedException {
        Thread worker = Thread.ofVirtual()
                .name("request-virtual")
                .start(() -> {
                    Thread t = Thread.currentThread();
                    System.out.printf(
                            "isVirtual=%s threadId=%d threadName=%s%n",
                            t.isVirtual(), t.threadId(), t.getName());
                });
        worker.join();
    }
}
~~~

~~~bash
javac VirtualThreadIdDemo.java
java VirtualThreadIdDemo
~~~

Dạng đầu ra:

~~~text
isVirtual=true threadId=<ID dương> threadName=request-virtual
~~~

Lưu ý khi vận hành:

- Hàng nghìn virtual thread có thể tồn tại. ID hữu ích cho chẩn đoán từng luồng nhưng tạo rất nhiều giá trị khác nhau; không dùng `threadId` làm label cho metric có cardinality thấp như tổng số request theo endpoint.
- Tên virtual thread có thể trống nếu không đặt; đưa cả ID và thông tin nghiệp vụ vào log sẽ dễ đọc hơn.
- Truy vết request vẫn cần `traceId`/`requestId`, kể cả khi một request thường chạy trong một virtual thread.

## 7. Phân tích log đúng cách

Khi điều tra một sự cố đồng thời, hãy xem cả **ID luồng, thời điểm, instance và ID nghiệp vụ**:

1. Xác định ứng dụng/JVM nào phát log: service, instance/container, khoảng thời gian, lần khởi động.
2. Lọc các sự kiện theo `threadId` để thấy chuỗi hoạt động của một luồng trong khoảng thời gian liên quan.
3. Đối chiếu `requestId`, `traceId`, `taskId` để biết sự kiện thuộc yêu cầu nào. Với thread pool, cùng ID không đồng nghĩa cùng một request.
4. So các sự kiện giữa những thread khác nhau bằng timestamp và correlation ID. Đừng suy diễn thứ tự tuyệt đối chỉ dựa vào thứ tự các dòng log được ghi ra hoặc số Thread ID.
5. Nếu cần chẩn đoán treo/chờ khóa, kết hợp thread dump, Java Flight Recorder (JFR), `ThreadMXBean` và ID trong log. Đối chiếu theo Java thread ID trong cùng phiên JVM; tránh nhầm Java ID với OS TID.

Nếu lưu log dạng JSON, các khóa nên có tên rõ và kiểu nhất quán, ví dụ:

~~~json
{
  "timestamp": "2026-11-10T09:40:00Z",
  "level": "WARN",
  "service": "checkout",
  "instance": "checkout-2",
  "threadId": 37,
  "threadName": "pool-1-thread-2",
  "requestId": "req-123",
  "event": "lock_wait"
}
~~~

Trong JSON này, `threadId` là số; `requestId` là chuỗi. Các giá trị chỉ minh họa cách biểu diễn, không khẳng định tình huống chạy thực tế.

## 8. Lỗi thường gặp và cách tránh

| Hiện tượng/sai lầm | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Chỉ log tên luồng rồi xem đó là ID | Tên do người dùng/framework đặt, có thể trùng hoặc đổi | Ghi `threadId` kiểu `long` và tùy chọn `threadName`. |
| Dùng `LogRecord.getThreadID()` trong Java 17 | API kiểu `int` đã deprecated, có thể là ID tổng hợp | Dùng `LogRecord.getLongThreadID()`. |
| Ép ID thành `int` hoặc đoán ID tăng liên tục | Làm mất thông tin hoặc suy diễn quy luật không được bảo đảm | Dùng `long`; đối chiếu theo thời gian và JVM cụ thể. |
| Gọi `otherThread.getId()` khi đang log | Lấy ID đối tượng thread khác, không phải luồng đang chạy | Lấy `Thread.currentThread()` tại điểm phát sinh log. |
| Xem tất cả log chung Thread ID là một request | Worker trong pool tái sử dụng thread | Ghi `requestId`/`traceId` riêng. |
| Mang `threadId` cũ sang thread mới qua MDC | Đồng nhất sai luồng phát log | Tính lại Thread ID trong thread thực thi, truyền correlation context riêng. |
| Không dọn MDC sau tác vụ | Giá trị của tác vụ trước có thể xuất hiện ở log tác vụ sau | Dùng `try/finally` để xóa/khôi phục context. |
| So sánh trực tiếp Java Thread ID với OS TID | Hai không gian định danh không được bảo đảm trùng | Dùng công cụ có ánh xạ tường minh; với JFR phân biệt Java/OS thread IDs. |
| Lọc log theo ID mà bỏ qua JVM/instance | Hai JVM khác nhau có thể có cùng số ID | Kết hợp `service`, `instance` và phạm vi thời gian. |
| Dùng Thread ID như khóa định danh người dùng/yêu cầu | Thread ID chỉ biểu diễn luồng | Dùng ID nghiệp vụ/correlation ID và kiểm soát quyền riêng. |

## 9. Tự kiểm tra kiến thức

1. Một executor một luồng thực thi 100 tác vụ nối tiếp. Tại sao có thể thấy chỉ một `threadId` nhưng 100 `taskId` khác nhau?
2. Hai luồng khác tên có luôn khác Thread ID không? Hai luồng cùng tên có bắt buộc cùng ID không? Trả lời trong **phạm vi cùng JVM và thời gian hai thread cùng tồn tại**.
3. Tại sao sau `CompletableFuture.supplyAsync(...)` có thể thấy cùng `requestId` nhưng `threadId` khác?
4. Khác biệt giữa `Thread.getId()` trên Java 17 và `Thread.threadId()` trên Java 19+ là gì?
5. Khi dùng `java.util.logging.LogRecord`, tại sao nên lấy `getLongThreadID()` thay vì `getThreadID()`?
6. Với Logback, `%thread` và `%X{threadId}` lấy dữ liệu từ đâu? Điều gì xảy ra nếu chưa gọi `MDC.put("threadId", ...)`?
7. Với virtual thread, ID trong log đại diện cho virtual thread hay carrier thread?

**Gợi ý đáp án:** (1) pool tái sử dụng luồng; (2) các luồng đang tồn tại có ID riêng nhưng tên có thể trùng; (3) tác vụ bất đồng bộ có thể chuyển thread; (4) `threadId()` được bổ sung Java 19 và là `final`, còn `getId()` deprecated từ Java 19; (5) dùng kiểu `long` tránh ID `int` tổng hợp; (6) `%thread` là tên thread, `%X{threadId}` là MDC và có thể rỗng nếu chưa đặt; (7) virtual thread hiện tại.

## 10. Tài liệu tham khảo

- [Java SE 21 — Thread API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Thread.html): `threadId()`, `getId()` và `isVirtual()`.
- [Java SE 17 — LogRecord API](https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/LogRecord.html): `getLongThreadID()` và `getThreadID()`.
- [Java SE 21 — Virtual Threads](https://docs.oracle.com/en/java/javase/21/core/virtual-threads.html): virtual thread và carrier thread.
