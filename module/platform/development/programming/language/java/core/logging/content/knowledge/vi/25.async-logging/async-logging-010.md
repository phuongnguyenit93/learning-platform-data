# Kiểm thử async logger trong Java

## 1. Vì sao async logger cần cách kiểm thử riêng?

Với logging đồng bộ, lệnh ghi log thường gọi appender trên thread hiện tại. Với **logging bất đồng bộ**, thread tạo sự kiện log có thể chỉ đưa sự kiện vào hàng đợi; một thread nền nhận sự kiện và chuyển đến appender (console, file, hệ thống tập trung) sau đó.

Luồng xử lý điển hình:

```text
Thread nghiệp vụ
    logger.info(...)
         |
         v
  tạo sự kiện log + chụp dữ liệu cần thiết
         |
         v
      queue/buffer
         |
         v
    worker thread
         |
         v
  appender/encoder/sink
         |
         v
   nơi nhận hoặc lưu log
```

**Điểm mấu chốt:** `logger.info(...)` trả về không đồng nghĩa dòng log đã tới sink, đã được flush ra file hoặc đã bền vững trên đĩa. Test kiểu “gọi `logger.info` rồi đọc file ngay” có thể qua ở máy phát triển nhưng thỉnh thoảng thất bại trên CI vì worker chưa chạy.

Hãy phân biệt ba thời điểm:

1. **Accepted/enqueued:** lời gọi log đã được logger chấp nhận hoặc đã xếp vào queue; với chế độ bỏ log khi quá tải, một số sự kiện có thể bị loại theo cấu hình.
2. **Processed/delivered to appender:** worker đã chuyển sự kiện đến appender; đây thường là điểm đồng bộ phù hợp cho **integration test logging**.
3. **Persisted/consumed downstream:** dữ liệu thực sự được đẩy tới file, mạng, dịch vụ thu thập log hoặc nơi lưu trữ. Việc appender nhận sự kiện chưa bảo đảm bước này thành công hay dữ liệu đã `fsync` xuống đĩa.

Phạm vi bài học là kiểm thử hành vi logging bất đồng bộ trong Java: nội dung và metadata của sự kiện, việc chạy nền, thứ tự, xử lý đầy queue, xử lý lỗi, dừng hệ thống và kiểm thử hiệu năng. Đây là **kiểm thử cơ chế logging**; không cần kiểm tra lại toàn bộ hoạt động nghiệp vụ chỉ để xác nhận một câu log xuất hiện.

## 2. Các hợp đồng hành vi cần xác định trước khi test

| Khía cạnh | Câu hỏi cần trả lời | Kiểm chứng phù hợp |
| --- | --- | --- |
| Nội dung | `INFO` có đúng thông điệp và tham số đã định dạng không? | Chặn event tại appender, so sánh `level` và `formattedMessage` |
| Ngữ cảnh | `requestId`/`traceId` có đi theo sự kiện đúng lúc tạo không? | Đổi MDC ở thread tạo sau khi log, kiểm tra snapshot trong event |
| Bất đồng bộ | Sink thực thi trên thread nền hay ngay trên thread gọi? | Ghi nhận thread trong `append(...)` và so với thread nguồn |
| Thứ tự | Hai log từ **một producer** có giữ thứ tự không? | Đưa hai event tuần tự, nhận lần lượt từ sink |
| Song song | Khi nhiều producer cùng ghi, có mất hoặc trùng event ngoài chính sách không? | Mỗi event mang ID duy nhất; so sánh tập và số lượng sau khi drain |
| Quá tải | Queue đầy thì block, drop hay fallback đồng bộ? | Ép sink chậm một cách có kiểm soát rồi quan sát chính sách đã cấu hình |
| Shutdown | Dừng logger có chờ xử lý event còn trong queue không? | Gửi event, gọi API `stop/flush` của implementation, kiểm tra event sau khi dừng |
| Lỗi sink | Appender lỗi thì có gây mất log/ảnh hưởng thread nghiệp vụ ra sao? | Sink giả lập lỗi, kiểm tra log nội bộ và cơ chế xử lý tương ứng |
| Hiệu năng | Độ trễ của thread nghiệp vụ và thông lượng thay đổi thế nào? | Benchmark riêng với warm-up, tải, queue, chính sách drop cố định |

**Chỉ viết assertion theo hợp đồng thực sự được cấu hình.** Ví dụ, nếu appender được phép loại `DEBUG`/`INFO` khi queue gần đầy, test không thể mặc nhiên đòi 100% những event đó phải có mặt. Ngược lại, trong test chức năng với queue nhỏ nhưng đủ chỗ, hãy vô hiệu hóa chính sách discard và sử dụng chế độ chờ khi đầy để kết quả có ý nghĩa.

### Async logger và async appender có giống nhau không?

Không hoàn toàn. Logback thường dùng `AsyncAppender`: phía trước vẫn tạo `ILoggingEvent`, sau đó chuyển công việc append sang worker. Log4j2 có cả **AsyncLogger** và **AsyncAppender**, với cấu hình và cơ chế nội bộ riêng. Ví dụ Java thực hành trong bài sử dụng **SLF4J + Logback AsyncAppender** để nhìn thấy ranh giới producer/consumer. Khi dùng Log4j2, vẫn áp dụng các nguyên tắc test nhưng phải chọn test appender, API lifecycle, chính sách overflow và cách flush theo implementation đó; không sao chép nguyên lớp `AsyncAppender` của Logback sang Log4j2.

## 3. Chống flaky test: chờ tín hiệu thay vì đoán thời gian

Không nên viết:

```java
logger.info("Order created");
// Sai: worker có thể chưa xử lý event.
assertEquals(1, capturedLogs.size());
```

Cũng không nên “chữa” bằng:

```java
logger.info("Order created");
Thread.sleep(200); // Không có bảo đảm 200 ms đủ trên mọi máy.
assertEquals(1, capturedLogs.size());
```

`Thread.sleep` vừa làm test chậm, vừa phụ thuộc lịch chạy thread và tải CI. Có ba cách đồng bộ hóa thích hợp hơn:

1. **Thread-safe sink + chờ có thời hạn.** Test appender đưa event vào `BlockingQueue`; test gọi `poll(timeout)`. Khi nhận được event, ta biết `append(...)` đã chạy. Nếu hết hạn, test thất bại với thông báo rõ ràng thay vì treo vô thời hạn.
2. **Tín hiệu `CountDownLatch`/`CompletableFuture`.** Dùng khi muốn chờ đúng số event hoặc đánh dấu worker đã vào một đoạn xử lý. Tín hiệu phải được phát tại **điểm hoàn thành đang được kiểm chứng**, không phát ngay sau lệnh enqueue.
3. **API drain/flush/stop của logger.** Phù hợp khi muốn kiểm tra các sự kiện tồn đọng khi shutdown. Phải hiểu timeout và mức bảo đảm riêng của backend; dừng worker xong chưa có nghĩa hệ thống log phía xa đã nhận dữ liệu.

Tránh đọc `ArrayList` đang được worker sửa mà không có đồng bộ; tránh dùng biến boolean thường chia sẻ giữa các thread. `BlockingQueue` và `CountDownLatch` đã có bảo đảm truyền dữ liệu giữa thread phù hợp cho bài test. Đặt timeout hữu hạn để không làm cả bộ test treo nếu worker gặp lỗi.

## 4. Ví dụ chạy được: JUnit 5 kiểm thử Logback AsyncAppender

Ví dụ dưới đây kiểm chứng bốn điều trong một bài test độc lập:

- Hai sự kiện `INFO` đến appender đủ và đúng thứ tự từ cùng một producer.
- Placeholder `{}` được định dạng thành thông điệp đúng.
- MDC `requestId` được chụp theo thời điểm gọi logger, không bị biến thành giá trị mới khi worker xử lý muộn.
- Phần việc `append(...)` thực sự chạy ở thread khác thread đã tạo sự kiện.

Test dùng một logger có tên duy nhất, tắt tính kế thừa appender qua root, kiểm soát queue, và thu thập event vào `BlockingQueue`. Nó không bắt đầu lại hay reset cấu hình logger toàn ứng dụng.

### 4.1. Cấu trúc dự án Maven tối thiểu

```text
async-logger-test/
├── pom.xml
└── src/
    └── test/
        └── java/
            └── example/
                └── AsyncAppenderTest.java
```

Tạo `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>async-logger-test</artifactId>
    <version>1.0-SNAPSHOT</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>ch.qos.logback</groupId>
            <artifactId>logback-classic</artifactId>
            <version>1.5.16</version>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>org.junit.jupiter</groupId>
            <artifactId>junit-jupiter</artifactId>
            <version>5.11.4</version>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-surefire-plugin</artifactId>
                <version>3.2.5</version>
            </plugin>
        </plugins>
    </build>
</project>
```

Ví dụ chỉ sử dụng Logback làm SLF4J provider. Trong dự án thật, hãy dùng đúng bộ phiên bản phụ thuộc đã được quản lý và kiểm tra chỉ một SLF4J provider phù hợp trên classpath.

### 4.2. Test appender có tín hiệu khi event đã đến sink

Tạo `src/test/java/example/AsyncAppenderTest.java`:

```java
package example;

import ch.qos.logback.classic.Level;
import ch.qos.logback.classic.Logger;
import ch.qos.logback.classic.LoggerContext;
import ch.qos.logback.classic.spi.ILoggingEvent;
import ch.qos.logback.classic.AsyncAppender;
import ch.qos.logback.core.AppenderBase;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.Timeout;
import org.slf4j.LoggerFactory;
import org.slf4j.MDC;

import java.util.Map;
import java.util.UUID;
import java.util.concurrent.BlockingQueue;
import java.util.concurrent.LinkedBlockingQueue;
import java.util.concurrent.TimeUnit;

import static org.junit.jupiter.api.Assertions.*;

class AsyncAppenderTest {
    record Captured(ILoggingEvent event, String sinkThreadName) {}

    static final class QueueAppender extends AppenderBase<ILoggingEvent> {
        private final BlockingQueue<Captured> received = new LinkedBlockingQueue<>();

        @Override
        protected void append(ILoggingEvent event) {
            // Chạy bên trong worker của AsyncAppender.
            received.add(new Captured(
                    event, Thread.currentThread().getName()));
        }

        Captured awaitEvent() throws InterruptedException {
            return received.poll(5, TimeUnit.SECONDS);
        }
    }

    @Test
    @Timeout(15)
    void deliversFormattedMessagesAndMdcOnWorkerThread() throws Exception {
        LoggerContext context =
                (LoggerContext) LoggerFactory.getILoggerFactory();

        Logger logger = context.getLogger(
                "example.async.test." + UUID.randomUUID());
        logger.setAdditive(false);
        logger.setLevel(Level.INFO);

        QueueAppender sink = new QueueAppender();
        sink.setContext(context);
        sink.setName("test-sink");
        sink.start();

        AsyncAppender async = new AsyncAppender();
        async.setContext(context);
        async.setName("test-async");
        async.setQueueSize(64);
        async.setDiscardingThreshold(0);
        async.setNeverBlock(false);
        async.setMaxFlushTime(0);
        async.addAppender(sink);
        async.start();

        Map<String, String> previousMdc = MDC.getCopyOfContextMap();
        logger.addAppender(async);

        try {
            MDC.put("requestId", "req-01");
            logger.info("step {}", 1);

            MDC.put("requestId", "req-02");
            logger.info("step {}", 2);

            Captured first = sink.awaitEvent();
            Captured second = sink.awaitEvent();

            assertNotNull(first, "Event 1 chưa đến sink trong 5 giây");
            assertNotNull(second, "Event 2 chưa đến sink trong 5 giây");

            assertEquals("step 1", first.event().getFormattedMessage());
            assertEquals("step 2", second.event().getFormattedMessage());
            assertEquals(Level.INFO, first.event().getLevel());
            assertEquals(Level.INFO, second.event().getLevel());

            assertEquals("req-01",
                    first.event().getMDCPropertyMap().get("requestId"));
            assertEquals("req-02",
                    second.event().getMDCPropertyMap().get("requestId"));

            // ILoggingEvent giữ tên thread TẠO log.
            // sinkThreadName ghi thread thực sự chạy append(...).
            assertNotEquals(first.event().getThreadName(),
                    first.sinkThreadName());
            assertNotEquals(second.event().getThreadName(),
                    second.sinkThreadName());
        } finally {
            if (previousMdc == null) {
                MDC.clear();
            } else {
                MDC.setContextMap(previousMdc);
            }
            logger.detachAppender(async);
            async.stop();
            sink.stop();
        }
    }
}
```

Chạy từ thư mục chứa `pom.xml` bằng JDK 17+ và Maven:

```bash
mvn test
```

Khi test thành công, Maven báo build thành công và bộ test có 1 test passed; thời gian và số dòng console khác nhau theo môi trường. Báo cáo JUnit/Surefire nằm trong `target/surefire-reports/`. Nếu test thất bại, thông điệp assertion hoặc timeout chỉ ra điểm chưa đạt; không nên giả định sẵn một stdout chính xác cho lịch chạy bất đồng bộ.

### 4.3. Tại sao test này đáng tin cậy hơn sleep?

- `QueueAppender.append(...)` thêm `Captured` vào `LinkedBlockingQueue` **sau khi** worker bắt đầu giao sự kiện cho sink. `poll(5, TimeUnit.SECONDS)` chờ đúng sự kiện cần quan sát.
- `AsyncAppender` xử lý tuần tự các event từ queue của chính nó. Hai lệnh log được gọi lần lượt từ cùng một test thread; vì thế thứ tự `step 1`, `step 2` là kỳ vọng hợp lý với cấu hình này. Không suy rộng thành bảo đảm thứ tự toàn cục giữa các producer chạy cạnh tranh.
- `getFormattedMessage()` cho biết nội dung sự kiện sau khi tham số `{}` được thay, trong khi `getMDCPropertyMap()` kiểm tra correlation ID gắn với từng event.
- `ILoggingEvent.getThreadName()` biểu diễn **thread nguồn** nơi gọi logger, kể cả khi appender chạy async. Ta ghi thêm `Thread.currentThread().getName()` ngay trong `append(...)` để phân biệt thread tiêu thụ. Nếu chỉ so `getThreadName()` với tên thread test rồi kết luận appender chạy đồng bộ thì đó là một kiểm thử sai.
- `async.setDiscardingThreshold(0)` tránh policy loại event mức thấp khi queue gần đầy trong ví dụ chức năng. `async.setNeverBlock(false)` quy định khi queue đầy producer sẽ chờ có chỗ thay vì chọn cách bỏ event tức thời. Test này ghi chỉ hai event nên không nhằm đo backpressure.
- `finally` khôi phục MDC cũ, tháo async appender khỏi logger, dừng worker và sink. `setMaxFlushTime(0)` yêu cầu Logback chờ worker hoàn tất khi dừng; dùng thận trọng nếu sink có thể treo. `@Timeout(15)` giới hạn thời gian chạy test, nhưng lỗi sink thực tế vẫn cần được xử lý ở tầng ứng dụng.

**Chú ý:** assertion đã nhận event ở sink chỉ chứng minh giao đến appender đã xảy ra. Nó **không chứng minh** có file được flush bền vững hoặc dịch vụ thu thập log từ xa đã xác nhận.

## 5. Thiết kế test khi nhiều thread cùng ghi log

Để kiểm tra concurrent logging, hãy gán **event ID duy nhất** cho mỗi lời gọi, chẳng hạn `producer=3, sequence=7` hoặc khóa `eventId`. Dùng `CountDownLatch` tạo điểm bắt đầu chung; sử dụng `ExecutorService` với số producer cố định. Sau khi tất cả producer kết thúc và hệ thống đã drain theo cơ chế có thật, so sánh tập ID đã thu được tại sink với tập ID dự kiến.

Một kịch bản hữu ích:

1. Tạo 4 producer, mỗi producer phát 50 event có ID dạng `P0-0` đến `P3-49`.
2. Chặn các producer ở `startGate.await()`; mở cổng một lần bằng `startGate.countDown()` để chúng chạy cạnh tranh.
3. Chờ tất cả `Future` bằng `get(timeout)` và bảo đảm mọi tác vụ hoàn thành trước khi chốt.
4. Chờ đủ số event ở sink (nếu policy cấu hình **không discard**), hoặc gọi drain/stop được backend hỗ trợ.
5. Đếm đúng 200 ID duy nhất, không trùng; nếu implementation bảo đảm thứ tự mỗi producer, kiểm tra chuỗi thứ tự **riêng từng producer**.

Không assert một thứ tự duy nhất như `P0-0, P1-0, P2-0,...` giữa tất cả producer: scheduler và thời gian enqueue khác nhau khiến thứ tự xen kẽ thay đổi hợp lệ. Với implementation giữ FIFO theo queue, kiểm tra trật tự của những sự kiện đã được một producer enqueue tuần tự; muốn áp dụng với nhiều producer phải xem lại hợp đồng thực tế của backend.

Đừng dùng `CopyOnWriteArrayList` lớn làm sink cho benchmark thông lượng: mỗi lần thêm có thể phải sao chép mảng, khiến benchmark phản ánh chi phí của **test collector** hơn là async logger. `BlockingQueue` phù hợp cho test chức năng; benchmark thật nên dùng appender/sink được kiểm soát riêng và đo chi phí của nó.

### Truyền MDC qua thread

Cần phân biệt hai bài test:

- **Producer → async logging worker:** event do logger tạo tại thread nghiệp vụ có thể chụp MDC của producer trước khi worker ghi. Ví dụ JUnit ở trên kiểm tra việc này.
- **Producer A → tác vụ nghiệp vụ B trên `ExecutorService`:** thread B cần nhận logging context theo cơ chế truyền context của ứng dụng. Logger async **không tự chuyển MDC của một request** sang thread B để phục vụ lệnh `logger.info` được gọi từ B. Phải test context propagation tại ranh giới submit riêng.

Với cùng một pool thread được tái sử dụng, nên chạy hai tác vụ có `requestId` khác nhau và một tác vụ không có context, xác nhận chúng không lấy nhầm ID từ request trước. Xóa hoặc khôi phục MDC của từng tác vụ trong `finally`. Test async logger không thay thế test context propagation của executor.

## 6. Kiểm thử queue đầy: backpressure, discard và lỗi quá tải

Test thông thường có queue đủ chỗ không chứng minh logger an toàn khi đột ngột nhận nhiều log hơn tốc độ appender có thể xử lý. Hãy tạo **slow/blocking test appender** với `CountDownLatch` để chủ động giữ worker ở một sự kiện; sau đó đẩy thêm event để queue đầy.

Với Logback `AsyncAppender`, hai cài đặt đáng chú ý:

- `discardingThreshold` điều khiển ngưỡng loại các sự kiện có mức độ ưu tiên thấp khi queue bắt đầu đầy; với Logback, hành vi mặc định có thể bỏ `TRACE`, `DEBUG` và `INFO` để nhường chỗ cho event quan trọng. `setDiscardingThreshold(0)` tắt cơ chế loại theo ngưỡng này trong test không mất log.
- `neverBlock=false`: khi queue thật sự đầy, phía gửi sẽ chờ có chỗ. `neverBlock=true`: phía gửi cố enqueue không chặn và có thể bỏ event nếu hết chỗ. Hành vi này khác với loại event do `discardingThreshold`.

**Kịch bản backpressure có kiểm soát:**

1. Cấu hình queue capacity 1, `discardingThreshold=0`, `neverBlock=false`.
2. Đẩy sự kiện thứ nhất, chờ tín hiệu cho biết worker đã đi vào appender giả lập đang bị giữ.
3. Đẩy sự kiện thứ hai để chiếm chỗ trong queue.
4. Gửi sự kiện thứ ba từ **một producer phụ** và quan sát rằng lệnh enqueue chưa hoàn tất trong khi sink vẫn bị chặn.
5. Mở latch để worker tiếp tục, sau đó dùng `Future.get(timeout)` xác nhận producer thứ ba kết thúc và cả ba event tới sink.

Không gọi lệnh log thứ ba trực tiếp trên thread điều phối test, vì nó có thể block làm thread đó không thể mở latch, gây deadlock. Khi kiểm tra trạng thái producer, dùng tín hiệu cho biết producer đã bắt đầu lời gọi log, rồi quan sát việc hoàn tất qua `Future` hoặc latch; đừng dựa vào mỗi một khoảng sleep ngắn.

Để test policy **discard**, giữ sink chậm tương tự nhưng cấu hình `neverBlock=true` hoặc ngưỡng discard, sau đó so sánh **số event được nhận với quy tắc thực tế**. Đừng đặt số sự kiện bị drop cứng nếu không kiểm soát đủ thời điểm worker lấy item; dùng latch để định hình chính xác queue state trước khi đưa sự kiện cần thử.

Trong production, các metric như queue utilization, số event bị loại, thời gian block của producer và lỗi appender giúp giải thích vì sao log thiếu. Một test tải chỉ thấy ít log không đủ kết luận lỗi vì có thể hệ thống đang chủ động thực thi discard policy.

## 7. Kiểm thử flush và shutdown

Những thứ cần phân biệt:

| Hành động | Ý nghĩa có thể kiểm chứng | Không nên suy luận |
| --- | --- | --- |
| `logger.info(...)` trả về | Producer đã hoàn tất thao tác gửi event theo policy | Sink đã nhận hoặc file đã sync xuống đĩa |
| Nhận event từ test appender | Worker đã gọi appender với event | Remote collector đã nhận |
| `stop/flush` thành công | Backend đã thực hiện quy trình dừng/xả theo API và timeout cấu hình | Mọi sink đều bảo đảm durability sau crash |
| Process bị kill đột ngột | Có thể mất event còn trong queue/buffer | Giống graceful shutdown |

Với Logback `AsyncAppender`, `stop()` cố gắng xử lý event còn trong queue và chờ worker theo `maxFlushTime`. Với thời hạn hữu hạn, worker có thể chưa xả hết trước khi hết thời gian; `maxFlushTime=0` chờ không giới hạn thời gian theo cơ chế của Logback. Cấu hình này hữu ích trong test có sink chắc chắn sẽ hoàn tất, nhưng không nên đặt tùy tiện cho hệ thống có sink có thể treo. Luôn đặt timeout ở lớp kiểm thử và bảo đảm đã mở tất cả latch của sink trước khi stop.

Kịch bản kiểm thử shutdown:

1. Gửi N event khi appender chạy bình thường, giữ một số event đang chờ trong queue có kiểm soát.
2. Cho worker tiếp tục xử lý; gọi `stop()` tại điểm lifecycle đúng và chờ hoàn tất.
3. So khớp N ID tại sink, nếu cấu hình không cho phép discard và shutdown bảo đảm drain trong thời gian đã chọn.
4. Xác nhận không có thread thử nghiệm nào còn treo; cleanup executor, appender và MDC trong `finally`.

Nếu appender đích là file, có thể tạo file tạm riêng cho test, dừng/flush logger, đọc lại bằng `Files.readString(...)` rồi xóa file tạm. Đây là **integration test file appender**, khác với test thu event trong bộ nhớ. Không dùng console của cả test suite làm nguồn assertion vì log từ thư viện và các test khác có thể xen kẽ.

Với crash bất ngờ, “không mất log” là yêu cầu độ bền của cả pipeline (queue, encoder, sink, file/network, phía nhận), không thể được chứng minh chỉ bằng một unit test gọi `stop()`.

## 8. Khi nào cần kiểm thử lỗi appender?

Async logging giúp tách thời gian ghi log khỏi luồng nghiệp vụ, nhưng không có nghĩa mọi lỗi sink đều biến mất. Test nên bao gồm:

- Appender phát sinh exception khi append: backend có bắt và báo lỗi nội bộ hay worker chết? Sự kiện sau đó có tiếp tục được xử lý theo đúng hành vi hệ thống không?
- Sink chậm hoặc tạm không khả dụng: queue tăng tới ngưỡng nào, producer block/drop ra sao?
- Thông điệp hoặc tham số định dạng gây lỗi: hệ thống có xử lý theo thiết kế, và liệu logging có vô tình đổi trạng thái nghiệp vụ không?
- Trạng thái restart/stop: có cho phép enqueue sau khi dừng không? Hành vi API thực tế là gì?

Không nên viết test mong một `RuntimeException` từ appender chắc chắn ném ngược về thread gọi `logger.info`, vì trong thiết kế async ngoại lệ có thể xảy ra ở worker và được backend ghi nhận riêng. Muốn test lỗi, lắp appender giả lập ném exception và quan sát **đúng kênh trạng thái, error handler hoặc metric** mà implementation cung cấp. Tránh bắt một exception bất kỳ rồi coi đó là đáp ứng mong muốn.

## 9. Kiểm thử hiệu năng đúng phạm vi

Test chức năng xác minh event đúng và đến nơi. Test hiệu năng hỏi một câu khác: với tốc độ tạo log và độ chậm của sink cụ thể, logging ảnh hưởng thread nghiệp vụ thế nào?

Các đại lượng nên đo:

| Đại lượng | Cách hiểu |
| --- | --- |
| Producer latency p50/p95/p99 | Thời gian một lời gọi logging làm thread nghiệp vụ bận/chờ |
| Throughput | Số event appender hoàn tất trong một đơn vị thời gian |
| Queue depth / capacity | Lượng backlog và nguy cơ queue đầy |
| Drop count | Số event bị loại theo policy quá tải |
| Drain duration | Thời gian xả backlog lúc dừng |
| Memory / allocation | Chi phí giữ sự kiện, chuỗi và context trong queue |

Phương pháp hợp lý:

1. Chọn cùng loại payload, mức log, format, số producer và sink cho phương án sync/async.
2. Warm-up đủ trước khi ghi số liệu; để benchmark chạy riêng với test chức năng.
3. Đo tổng số event **được appender xử lý**, không chỉ số lần gọi `logger.info(...)`.
4. Quan sát khi queue cạn, khi queue đầy và khi sink chậm; async có thể nhanh ở tải nhẹ nhưng bắt đầu block/drop khi áp lực lớn.
5. Dùng JMH hoặc công cụ tải thích hợp và nhiều lần chạy để so số liệu phân phối; đừng viết unit test kiểu `assertTrue(elapsed < 10 ms)` vì scheduler, GC, máy CI và I/O không ổn định.

**Async không mặc nhiên nhanh hơn mọi trường hợp.** Nếu appender nhanh và lượng log thấp, chi phí queue, thread chuyển ngữ cảnh và cấp phát đối tượng có thể không đáng; nếu sink chậm, async giảm độ trễ ở producer cho tới khi backlog vượt khả năng phục vụ.

## 10. Lỗi thường gặp khi viết test async logger

| Triệu chứng | Nguyên nhân có thể | Cách sửa |
| --- | --- | --- |
| Test đôi lúc thất bại vì log “chưa xuất hiện” | Assert ngay sau enqueue | Chờ event bằng queue/latch với timeout |
| Test phải sleep nhiều giây mới đậu | Đồng bộ hóa bằng thời gian | Báo hiệu tại appender hoặc gọi drain được hỗ trợ |
| Log từ test khác lọt vào kết quả | Dùng root logger hoặc sink dùng chung | Logger riêng, `additive=false`, cleanup trong `finally` |
| Test so tên thread sai | `ILoggingEvent.getThreadName()` là thread nguồn | Ghi `Thread.currentThread()` bên trong appender |
| MDC hiển thị giá trị cuối cho nhiều event | Dùng object/map mutable hoặc snapshot sai chỗ | Kiểm tra snapshot event và propagation tại ranh giới đúng |
| Thiếu log khi tải cao | `discardingThreshold`, `neverBlock` hoặc sink chậm | Biết rõ chính sách trước khi assert đủ event |
| Test deadlock khi queue đầy | Thread test tự block trước khi mở latch | Gửi lệnh có thể block từ producer phụ, dùng timeout và release trong `finally` |
| Test throughput rất chậm | Collector test có lock/I/O/copy array nặng | Tách collector chức năng khỏi sink benchmark |
| Test xanh nhưng shutdown mất log | Chỉ kiểm tra accepted/enqueued | Test lifecycle drain và timeout thực tế |
| CI treo khi test lỗi | `take()` vô hạn, `join()` không giới hạn | Dùng `poll(timeout)`, `Future.get(timeout)` và `@Timeout` |

### Quy trình chẩn đoán khi test không ổn định

- Xác định assertion đang đo **enqueue**, **append** hay **persist**; đặt điểm chờ đúng ranh giới.
- Kiểm tra tên logger, mức log và cấu hình filter để chắc event dự kiến thực sự được tạo.
- Quan sát queue size, discard policy, trạng thái worker và exception/status của backend.
- Kiểm tra rò MDC, appender chưa `stop`, executor chưa `shutdown` hoặc shared logger bị test khác thay cấu hình.
- Chạy lặp lại với cả tốc độ thấp, nhiều producer và chính sách queue được xác định; không tăng sleep tùy tiện để che race condition.

## 11. Checklist hoàn thành một bộ test async logger

Một bộ test có giá trị nên chứng minh được:

- [ ] Sự kiện đúng message, level, logger name và các field cần thiết.
- [ ] Test chờ theo tín hiệu do **sink** phát ra, có timeout rõ ràng.
- [ ] Có kiểm tra đường đi qua thread nền khi đó là hành vi cần đảm bảo.
- [ ] MDC hoặc correlation context được chụp đúng lúc tạo event và không rò giữa các công việc.
- [ ] Có kiểm tra thứ tự trong phạm vi backend cam kết; không ép thứ tự giữa các producer tùy lịch chạy.
- [ ] Queue và drop/backpressure policy được cấu hình rõ cho từng test.
- [ ] Có test shutdown/drain cho sự kiện đang chờ, nếu ứng dụng yêu cầu.
- [ ] Dọn appender, MDC, executor và file tạm sau test kể cả khi assertion thất bại.
- [ ] Benchmark hiệu năng được tách khỏi JUnit assertion phụ thuộc thời gian máy.

**Ghi nhớ:** gọi logger chỉ bắt đầu hành trình của một sự kiện bất đồng bộ. Test đáng tin cậy phải xác định điểm hoàn thành cần kiểm chứng, dùng tín hiệu đồng bộ hóa thực sự tại điểm đó và đối chiếu kết quả theo đúng chính sách queue, thread, MDC và shutdown mà ứng dụng đã chọn.
