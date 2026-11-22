# Logger thread-safe trong Java Core Logging

## 1. Logger thread-safe là gì?

Trong ứng dụng Java, nhiều thread có thể cùng xử lý HTTP request, tác vụ nền, message từ queue hoặc công việc trong thread pool. Các thread đó thường ghi log qua **cùng một đối tượng Logger**, ví dụ một trường `static final` dùng chung trong lớp.

Một **logger thread-safe** cho phép nhiều thread gọi các phương thức ghi log đồng thời mà không làm hỏng trạng thái nội bộ của logger. Chẳng hạn, thread A ghi “Đã nhận đơn hàng”, trong lúc thread B ghi “Đã xử lý thanh toán”, thì việc gọi API logger từ cả hai thread là hợp lệ khi logger và logging backend được thiết kế cho truy cập đồng thời.

Tuy nhiên, cần phân biệt các tầng bảo đảm:

- **Logger/API:** việc nhiều thread đồng thời gọi `info`, `warn`, `error`… có được hỗ trợ an toàn hay không.
- **Handler/Appender:** thành phần nhận và ghi từng log event ra console, tệp, mạng hoặc queue. Một handler tùy biến có thể làm mất tính an toàn dù logger dùng chung vẫn đúng cách.
- **Log message và dữ liệu truyền vào:** logger không tự đồng bộ các đối tượng mutable của ứng dụng đang được đưa vào log.
- **Thứ tự và độ bền:** thread-safe không có nghĩa log của các thread xuất hiện theo thứ tự nghiệp vụ, được lưu ngay lập tức hoặc không bao giờ thất lạc.

Với thư viện chuẩn **`java.util.logging.Logger` (JUL)**, có thể dùng cùng logger từ nhiều thread. Trong ứng dụng sử dụng **SLF4J** cùng backend thông dụng như Logback hoặc Log4j 2, mô hình chia sẻ một logger giữa các thread cũng là cách dùng điển hình. Nếu tự viết backend, appender, formatter hoặc handler, phải xem xét riêng khả năng chịu truy cập đồng thời của thành phần đó.

## 2. Dùng chung logger, không cần một logger cho mỗi thread

Một cách phổ biến để khai báo logger của lớp:

~~~java
import java.util.logging.Logger;

public final class OrderService {
    private static final Logger LOGGER =
            Logger.getLogger(OrderService.class.getName());

    public void process(String orderId) {
        LOGGER.info("Processing order " + orderId);
    }
}
~~~

`static final` có nghĩa trường tham chiếu logger được tạo/chọn một lần khi lớp được khởi tạo và các đối tượng `OrderService` dùng chung tham chiếu đó. Đây là lựa chọn tiết kiệm, dễ cấu hình và giúp log có cùng tên nguồn. Bản thân `static final` **không biến bất kỳ đối tượng nào thành thread-safe**; tính an toàn đến từ cách `Logger` và các handler/appender được triển khai.

Không cần tạo một logger mới trong mỗi lời gọi, mỗi request hoặc mỗi thread để tránh xung đột. Việc tạo logger riêng theo thread còn làm khó việc quản trị tên logger, mức log và correlation. Ngược lại, việc một logger an toàn **không làm cho toàn bộ `process` thread-safe**: nếu `process` sửa một danh sách, bộ đếm hoặc cache dùng chung, dữ liệu đó vẫn cần biện pháp đồng bộ phù hợp.

**Phân biệt hai câu hỏi:**

1. “Nhiều thread có thể cùng gọi `LOGGER.info(...)` không?” — Có, với logger và logging backend hỗ trợ concurrency.
2. “Dữ liệu nghiệp vụ được ghi trong log có nhất quán không?” — Chưa chắc. Ví dụ hai thread cùng tăng một biến `int` không đồng bộ vẫn có thể tạo giá trị sai, dù các dòng log được ghi an toàn.

## 3. Ví dụ Java 17 chạy độc lập: 4 thread cùng ghi một logger

Ví dụ dùng `java.util.logging` có sẵn trong JDK, nên **không cần thư viện bên ngoài**. Bốn worker cùng dùng một `Logger`, mỗi worker tạo 25 message khác nhau. Một `Handler` tùy biến gom nội dung vào `ConcurrentLinkedQueue` để kiểm tra sau khi tất cả worker kết thúc.

Tạo tệp **`ThreadSafeLoggerDemo.java`**:

~~~java
import java.util.HashSet;
import java.util.concurrent.ConcurrentLinkedQueue;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public class ThreadSafeLoggerDemo {
    private static final Logger LOGGER =
            Logger.getLogger(ThreadSafeLoggerDemo.class.getName());

    public static void main(String[] args) throws InterruptedException {
        ConcurrentLinkedQueue<String> messages = new ConcurrentLinkedQueue<>();

        Handler collectingHandler = new Handler() {
            @Override
            public void publish(LogRecord record) {
                if (isLoggable(record)) {
                    messages.add(record.getMessage());
                }
            }

            @Override
            public void flush() {
            }

            @Override
            public void close() {
            }
        };

        collectingHandler.setLevel(Level.INFO);
        LOGGER.setLevel(Level.INFO);
        LOGGER.setUseParentHandlers(false); // Ẩn console log mặc định.
        LOGGER.addHandler(collectingHandler);

        ExecutorService pool = Executors.newFixedThreadPool(4);
        CountDownLatch start = new CountDownLatch(1);

        try {
            for (int worker = 0; worker < 4; worker++) {
                final int workerId = worker;
                pool.execute(() -> {
                    try {
                        start.await();
                        for (int event = 0; event < 25; event++) {
                            LOGGER.info("worker=" + workerId + " event=" + event);
                        }
                    } catch (InterruptedException e) {
                        Thread.currentThread().interrupt();
                    }
                });
            }

            start.countDown(); // Cho phép các worker bắt đầu.
            pool.shutdown();

            if (!pool.awaitTermination(30, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Workers did not finish");
            }

            System.out.println("records=" + messages.size());
            System.out.println("unique=" + new HashSet<>(messages).size());
        } finally {
            pool.shutdownNow();
            LOGGER.removeHandler(collectingHandler);
            collectingHandler.close();
        }
    }
}
~~~

Biên dịch và chạy bằng JDK 17 trở lên:

~~~bash
javac ThreadSafeLoggerDemo.java
java ThreadSafeLoggerDemo
~~~

Kết quả khi các worker hoàn thành trong thời hạn 30 giây:

~~~text
records=100
unique=100
~~~

**Giải thích kết quả:**

- Có **4 × 25 = 100** lời gọi `LOGGER.info`; tất cả dùng cùng trường `LOGGER`.
- Mỗi message chứa cặp `workerId` và `event`, nên **100 message là khác nhau**.
- `ConcurrentLinkedQueue` là cấu trúc an toàn khi nhiều thread đồng thời gọi `add`. Đây là điểm quan trọng: handler phải bảo vệ **bộ nhớ dùng chung của chính nó**.
- `CountDownLatch` giúp các worker có cơ hội chạy đồng thời. `awaitTermination` bảo đảm kiểm tra số lượng sau khi các worker đã kết thúc, thay vì đọc queue khi vẫn còn thread ghi.
- Ví dụ **không khẳng định thứ tự** của 100 message. Nếu in từng message trực tiếp, `worker=3` hoàn toàn có thể xuất hiện trước `worker=0`.

Đây là ví dụ minh họa một cách dùng an toàn, **không phải phép chứng minh mọi handler hoặc logging backend đều thread-safe**. Việc thêm một `ArrayList` dùng chung vào handler rồi gọi `add` từ nhiều thread mà không đồng bộ là một thiết kế khác và có thể gây race condition.

## 4. Thread-safe không đồng nghĩa với log theo thứ tự

Xét hai thread xử lý hai request độc lập:

~~~text
Thread-A: bắt đầu A ─────── xử lý A ───────── hoàn tất A
Thread-B: ─── bắt đầu B ── xử lý B ─── hoàn tất B
Log:      [A start] [B start] [B done] [A done]
~~~

Thứ tự trên có thể hoàn toàn đúng. **Thread-safe** chỉ nói về việc thao tác logging đồng thời được xử lý đúng theo hợp đồng của logger/appender, không hứa log của một request sẽ luôn nằm liền nhau. Bộ lập lịch thread, I/O, buffering và asynchronous logging đều ảnh hưởng đến thứ tự quan sát.

Các điểm dễ nhầm:

- **Độ nguyên vẹn một event:** backend có thể xử lý một log event như đơn vị riêng, nhưng formatter/appender tùy biến hoặc ghi trực tiếp ra stream chung có thể tạo output bị trộn.
- **Thời điểm tạo và thời điểm xuất:** với async logging, event có thể được tạo ở worker nhưng được ghi tệp/mạng sau đó. Không được đồng nhất thứ tự xuất log với thứ tự hoàn thành thao tác nghiệp vụ.
- **Thứ tự giữa các thread:** timestamp có thể giống nhau, hệ thống có thể dùng nhiều clock hoặc nhiều service. Không nên dùng thứ tự dòng log làm cơ chế đồng bộ.
- **Thứ tự trong một thread:** lời gọi log trong chương trình có trình tự thực thi, nhưng backend bất đồng bộ hoặc việc gộp log từ nhiều nguồn có thể khiến thứ tự hiển thị khác với suy luận đơn giản.

Nếu cần kiểm tra nhân quả, hãy ghi thêm mã request/trace, mã tác vụ, hoặc một sequence number **được cấp bằng cơ chế đồng bộ phù hợp**. Đừng đưa việc điều phối thread hay thứ tự nghiệp vụ vào trách nhiệm của logger.

## 5. SLF4J và parameterized logging trong ứng dụng thực tế

Trong ứng dụng Java sử dụng SLF4J, thường khai báo logger cấp lớp và gọi từ mọi thread:

~~~java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

public final class PaymentService {
    private static final Logger LOGGER =
            LoggerFactory.getLogger(PaymentService.class);

    public void charge(String requestId, long amount) {
        LOGGER.info("Charging requestId={} amount={}", requestId, amount);
    }
}
~~~

Đoạn này **cần dependency SLF4J và logging backend** khi biên dịch/chạy; nó là ví dụ tích hợp, không phải phần chương trình JDK độc lập ở mục 3. Với backend phổ biến được thiết kế để dùng đồng thời, logger cấp lớp là mẫu thông dụng.

Dùng placeholder `{}` giúp tách thông điệp khỏi tham số, đồng thời tránh nối chuỗi ngay từ đầu khi mức log có thể đang tắt. Tuy vậy:

- Đừng truyền vào logger một đối tượng đang bị thread khác sửa mà mặc nhiên cho rằng biểu diễn `toString()` của nó sẽ an toàn.
- Đừng tự xây dựng message bằng một `StringBuilder` **static dùng chung**, trừ khi có đồng bộ phù hợp. Một biến `StringBuilder` cục bộ trong mỗi lời gọi thì không gặp vấn đề chia sẻ này.
- Đừng gọi phương thức có side effect chỉ để tạo tham số log. Dù event được lọc bỏ, biểu thức đối số của lời gọi Java vẫn được đánh giá trước khi gọi logger.
- Không đưa mật khẩu, access token, thông tin cá nhân nhạy cảm hoặc toàn bộ request body vào log chỉ để nhận diện thread.

Nếu dùng logger bất đồng bộ, cần xem cấu hình **kích thước queue, chính sách khi queue đầy, thời điểm flush/shutdown và khả năng discard**. Việc API chấp nhận một lời gọi không đảm bảo log đã được ghi bền vững ra ổ đĩa hay hệ thống thu thập.

## 6. Thread name, MDC và trace context: ba thứ khác nhau

**Thread name** (ví dụ `pool-1-thread-2`) cho biết thread nào thực hiện lời gọi. Nó hữu ích cho debugging nhưng **không phải request ID**: một thread trong pool có thể xử lý nhiều request nối tiếp nhau. Một request cũng có thể đi qua nhiều thread.

**MDC (Mapped Diagnostic Context)** cho phép đính kèm các trường như `requestId` vào log event, giúp gom log theo yêu cầu. Các triển khai MDC thông dụng lưu context theo thread; vì vậy phải đặt và dọn context cẩn thận:

~~~java
import org.slf4j.MDC;

// Đoạn mã bên trong nơi đã có LOGGER và biến requestId.
MDC.put("requestId", requestId);
try {
    LOGGER.info("Start processing");
    // Xử lý request trong thread hiện tại.
} finally {
    MDC.remove("requestId");
}
~~~

Đây là **đoạn mã tích hợp SLF4J**, không phải chương trình độc lập. `try/finally` tránh để request tiếp theo trên cùng thread pool nhận nhầm `requestId` cũ. Nếu một framework có scope quản lý MDC sẵn, nên dùng scope đó đúng cách. Khi code nằm trong phương thức có nhiều khóa MDC, phải cân nhắc lưu/khôi phục context cũ thay vì xóa bừa các khóa thuộc caller.

**Trace context** gồm `traceId`, `spanId` và quan hệ parent span để liên kết các công việc qua thread/dịch vụ. Tracing instrumentation có thể giúp đưa ID vào MDC/log, nhưng **logger thread-safe không tự truyền trace context**. Khi chuyển sang `ExecutorService`, `CompletableFuture`, reactive pipeline hoặc thread khác, cần cơ chế propagation của framework/tracing thư viện. Không thể suy ra context của request vẫn có mặt chỉ vì cùng sử dụng một Logger.

Ví dụ hai log trên cùng thread có thể có `requestId` khác nhau; ngược lại hai thread khác nhau có thể xử lý các phần của cùng một trace. Hãy dùng **request/trace identifier** để điều tra hành trình, và thread name để xác định vị trí thực thi.

## 7. Lỗi phổ biến khi nhiều thread ghi log

| Hiện tượng | Nguyên nhân cần kiểm tra | Hướng xử lý |
| --- | --- | --- |
| Log của hai request xen kẽ | Thread xử lý đồng thời; xen kẽ là bình thường | Ghi `requestId` hoặc `traceId` và lọc theo ID |
| Log gắn sai mã request | MDC/context không được dọn hoặc không propagate đúng | Dùng scope/`finally` và cơ chế propagation |
| Log bị mất hoặc đến trễ | Queue async đầy, cấu hình lọc/sampling, lỗi exporter, shutdown chưa flush | Kiểm tra chính sách backend và telemetry pipeline |
| Nội dung log hiển thị dữ liệu không nhất quán | Shared mutable object bị sửa đồng thời khi format | Snapshot dữ liệu hoặc bảo vệ trạng thái nghiệp vụ |
| Thiếu event/chuỗi bị hỏng trong custom handler | Collection/formatter/appender tự viết không thread-safe | Dùng collection concurrent, đồng bộ hoặc cơ chế queue phù hợp |
| Log không theo thứ tự nghiệp vụ | Scheduling, buffering hoặc nhiều service | Dùng ID tương quan và dữ kiện thời gian/quan hệ nhân quả |
| Nhiều process cùng ghi một tệp gây lỗi | Bảo đảm thread-safe chỉ trong phạm vi các thread của từng process | Cấu hình multi-process logging hoặc gom log qua hệ thống trung gian |

**Không nên “sửa” mọi vấn đề bằng cách đặt `synchronized` quanh tất cả `LOGGER.info(...)`**. Điều này có thể làm nghẽn throughput, đồng thời không sửa được vấn đề dữ liệu nghiệp vụ, mất MDC hoặc hai process ghi một tệp. Chỉ đồng bộ tại nơi thực sự có trạng thái dùng chung cần bảo vệ.

Khi tự viết `Handler`/`Appender`, cần xác định rõ dữ liệu mutable mà nhiều thread có thể chạm vào: buffer, formatter, counter, writer, socket, queue, cấu hình runtime. Bộ phận này phải có cơ chế an toàn tương ứng và cách đóng/flush đúng vòng đời.

## 8. Checklist áp dụng và tự kiểm tra

Trước khi đưa logging vào dịch vụ Java xử lý đồng thời, kiểm tra:

1. Logger được khai báo cấp lớp/cấp thành phần và dùng chung theo mô hình được backend hỗ trợ; không khởi tạo logger cho mỗi message.
2. Handler/appender, đặc biệt code tự viết, chịu được gọi đồng thời; không dùng collection mutable không bảo vệ.
3. Log event chứa thông tin tương quan hữu ích; thread name chỉ là dữ kiện phụ.
4. MDC và trace context được thiết lập, truyền qua ranh giới async khi cần và dọn/khôi phục sau tác vụ.
5. Thông số async queue, mức log, filter, flush và shutdown được cấu hình theo yêu cầu mất dữ liệu/hiệu năng.
6. Không xem một thứ tự log duy nhất là bằng chứng các thread đã chạy tuần tự.

**Tự hỏi:** Nếu 10 request cùng gọi một `static final Logger`, có cần 10 đối tượng Logger không? **Không**, nếu logger/backend hỗ trợ concurrency. Nếu cả 10 request cùng nối chuỗi vào một `static StringBuilder` rồi log, lời gọi logger có tự sửa được lỗi không? **Không**: `StringBuilder` là trạng thái chia sẻ nằm ngoài hợp đồng thread safety của logger. Nếu log của hai request đan xen mà từng event vẫn đầy đủ, có nhất thiết là lỗi không? **Không**: đây có thể là kết quả bình thường của thực thi song song.

**Ghi nhớ:** Logger thread-safe giúp nhiều thread ghi log qua một logger chung an toàn theo hợp đồng của thư viện. Để log có thể tin cậy khi điều tra lỗi, còn cần handler/appender an toàn, dữ liệu đầu vào nhất quán, context tương quan đúng và hiểu rõ giới hạn về thứ tự cũng như lưu trữ.