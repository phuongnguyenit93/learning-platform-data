# Backpressure log trong logging bất đồng bộ (Java)

## 1. Backpressure log là gì?

**Backpressure trong logging** là tình huống hệ thống tạo sự kiện log nhanh hơn tốc độ mà phần ghi log (file, console, mạng, collector hoặc nền tảng phân tích log) có thể xử lý. Với **logging bất đồng bộ**, ứng dụng thường đưa sự kiện vào hàng đợi, còn một hoặc nhiều consumer ghi log ở luồng nền. Khi consumer chậm, hàng đợi tích tụ và cuối cùng đạt giới hạn.

Backpressure chính là cơ chế/quyết định ứng dụng **phải làm gì khi đường ghi log không theo kịp**: chờ, chờ có giới hạn, từ chối/bỏ sự kiện, lấy mẫu, chuyển qua đường dự phòng hoặc tăng khả năng xử lý. Không có chính sách nào cùng lúc bảo đảm độ trễ thấp, bộ nhớ hữu hạn và không bao giờ mất log trong mọi trạng thái lỗi.

Một luồng xử lý điển hình:

```text
Business thread(s)
      |
      | gọi logger.info/debug/error(...)
      v
 [Capture/format event]
      |
      v
 [Bounded async queue]  <-- backlog tăng nếu producer nhanh hơn consumer
      |
      v
 [Logging worker]
      |
      v
 [File / stdout / network / collector]
```

Gọi logger là thao tác nhanh chỉ khi bước chuẩn bị sự kiện, đưa vào queue và đường ghi còn đủ khả năng phục vụ. Khi queue đầy, **chính sách bão hòa (saturation policy)** có thể khiến lời gọi logger chặn luồng nghiệp vụ hoặc làm mất một số sự kiện.

Ví dụ: một API tạo 3.000 sự kiện/giây, nhưng worker chỉ ghi được 2.000 sự kiện/giây trong một đợt disk chậm. Hàng đợi phải hấp thụ khoảng 1.000 sự kiện/giây; nếu không giảm tải hoặc tăng throughput, nó sẽ đầy.

## 2. Tại sao async logging vẫn có thể làm chậm ứng dụng?

Async logging **tách phần ghi I/O khỏi luồng gọi**, chứ không làm mất chi phí của logging. Producer vẫn có thể phải tạo đối tượng sự kiện, lấy timestamp, định dạng tham số hoặc thông tin context tùy framework, rồi đưa dữ liệu vào queue.

Các nguyên nhân phổ biến khiến queue dâng cao:

- Ghi file chậm vì ổ đĩa gần đầy, I/O cạnh tranh, flush hoặc rotation.
- Xuất log qua mạng gặp độ trễ, collector bị giới hạn tốc độ hoặc không phản hồi.
- Bùng nổ log DEBUG/INFO trong một vòng lặp hoặc sau một lỗi lặp lại.
- Exception stack trace lớn khiến từng sự kiện tốn nhiều CPU, bộ nhớ và I/O.
- Một consumer đơn không theo kịp nhiều producer; hoặc worker bị pause, lỗi, ngừng.
- Pipeline nhiều tầng: queue trong JVM có thể thoát nhanh nhưng agent/collector phía sau lại ùn ứ. Backpressure có thể lan ngược tới ứng dụng nếu sink bị chặn.

Cần phân biệt:

- **Backlog:** sự kiện đang chờ xử lý, có thể là bình thường trong một đợt burst ngắn.
- **Saturation:** queue gần hoặc đã đầy, các quyết định chặn/bỏ log bắt đầu có tác dụng.
- **Backpressure:** cách thành phần phía trước nhận tín hiệu hoặc chịu hậu quả khi thành phần phía sau chậm.
- **Log loss:** sự kiện bị từ chối, bỏ theo chính sách, hoặc mất khi tiến trình/thiết bị gặp sự cố. Không phải mọi backlog đều đã gây mất log.

## 3. Hiểu dung lượng queue bằng số liệu

Gọi:

- `λ` (lambda): số sự kiện log producer tạo ra mỗi giây.
- `μ` (mu): số sự kiện consumer/sink thực sự xử lý mỗi giây.
- `Q`: số vị trí chờ còn trống trong queue.

Khi `λ > μ` kéo dài và các tốc độ tương đối ổn định:

```text
backlog tăng xấp xỉ (λ - μ) × thời gian
thời gian tới khi queue đầy xấp xỉ Q / (λ - μ)
```

Ví dụ: queue còn trống 10.000 vị trí, tốc độ tạo 2.500 sự kiện/giây và tốc độ ghi 2.000 sự kiện/giây. Backlog tăng khoảng 500 sự kiện/giây, nên **sau khoảng 20 giây** queue sẽ đầy nếu không thay đổi gì. Đây chỉ là ước lượng: log có kích thước khác nhau, tốc độ I/O biến động, có thể có burst và nhiều tầng queue.

Queue lớn giúp **chịu burst ngắn** tốt hơn nhưng không giải quyết được quá tải kéo dài. Nó còn giữ nhiều đối tượng trong heap, có thể tăng áp lực GC và kéo dài thời gian chờ log xuất hiện ở sink.

Về bộ nhớ, phép tính sơ bộ:

```text
payload lưu trong queue ≈ queue_capacity × kích thước sự kiện trung bình
```

Chẳng hạn 10.000 sự kiện × 2 KiB ≈ 19,5 MiB dữ liệu sự kiện, **chưa kể overhead đối tượng, tham chiếu, chuỗi và dữ liệu phụ của framework**. Đừng xem kết quả này là dự báo chính xác lượng heap.

## 4. Các chính sách khi queue đầy

| Chính sách | Cơ chế | Lợi ích | Đánh đổi và khi nào phù hợp |
| --- | --- | --- | --- |
| **Block producer** | Chờ tới khi còn vị trí trong queue (`put`, hoặc cơ chế enqueue có chặn) | Hạn chế mất sự kiện vì riêng lý do queue đầy | Tăng latency, chiếm thread nghiệp vụ, có nguy cơ lan sự cố từ logging sang request |
| **Bounded wait** | Chờ tối đa một khoảng thời gian (`offer(timeout)`) | Có ngân sách latency rõ ràng | Hết timeout vẫn phải quyết định drop/fallback; đo tỉ lệ timeout |
| **Drop newest** | Từ chối sự kiện mới khi queue đầy (`offer` trả `false`) | Giữ đường nghiệp vụ không bị chặn lâu; dễ giới hạn bộ nhớ | Mất log mới; cần counter và policy theo mức độ quan trọng |
| **Drop oldest** | Bỏ sự kiện cũ để ưu tiên log mới | Giữ tín hiệu gần thời điểm hiện tại | Có thể làm mất diễn biến dẫn tới lỗi; chỉ áp dụng nếu queue/framework hỗ trợ |
| **Sampling/rate limit** | Giảm lượng sự kiện đưa vào pipeline từ sớm | Giảm CPU, bộ nhớ và I/O ngay tại nguồn | Không còn toàn bộ chi tiết; phải ghi rõ chính sách lấy mẫu |
| **Synchronous fallback** | Khi queue đầy, producer tự ghi qua sink | Có thể cứu sự kiện quan trọng nếu sink còn hoạt động | Đưa I/O chậm trở lại luồng nghiệp vụ; có thể làm nghẽn API |
| **Durable spill/queue** | Ghi sự kiện vào vùng đệm bền vững (ví dụ queue trên đĩa) | Tăng khả năng vượt sự cố tạm thời, phụ thuộc triển khai | Chi phí lưu trữ/đồng bộ/khôi phục cao; vẫn cần giới hạn và chính sách khi đầy |

**Không mặc định chọn “không bao giờ drop”** cho hệ thống phục vụ request có yêu cầu độ trễ chặt. Nếu một luồng request phải chờ logger trong lúc giữ lock quan trọng, sự cố log có thể khuếch đại thành nghẽn toàn hệ thống. Nhưng cũng không nên mặc định drop mọi log: sự kiện kiểm toán, giao dịch, an ninh hoặc pháp lý có thể yêu cầu một đường thu nhận đáng tin cậy riêng.

Với các mức log, chính sách thực tế thường ưu tiên giảm **TRACE/DEBUG**, cân nhắc sampling đối với INFO có lưu lượng cao, và bảo vệ WARN/ERROR bằng ngân sách chờ hoặc kênh dự phòng phù hợp. Đây là **quyết định vận hành**: WARN/ERROR không được tự động bảo đảm còn nguyên chỉ vì mức severity cao.

## 5. Ví dụ Java 17: thấy queue đầy và sự kiện bị từ chối

Ví dụ độc lập sau dùng `ArrayBlockingQueue` có sức chứa 1, một producer là `main` và một consumer chạy ở thread riêng. `CountDownLatch` tạm giữ consumer để minh họa trạng thái bão hòa một cách **xác định**, tránh kết quả ngẫu nhiên do scheduler.

Lưu thành `BackpressureLogDemo.java`:

```java
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.BlockingQueue;
import java.util.concurrent.CountDownLatch;

public class BackpressureLogDemo {
    public static void main(String[] args) throws InterruptedException {
        BlockingQueue<String> queue = new ArrayBlockingQueue<>(1);
        CountDownLatch allowConsume = new CountDownLatch(1);

        Thread logWorker = new Thread(() -> {
            try {
                allowConsume.await();
                System.out.println("written: " + queue.take());
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        }, "log-worker");
        logWorker.start();

        boolean first = queue.offer("INFO order-created");
        boolean second = queue.offer("DEBUG payload-details");

        System.out.println("accepted first: " + first);
        System.out.println("accepted second: " + second);
        System.out.println("queue size: " + queue.size());

        allowConsume.countDown();
        logWorker.join();
    }
}
```

Biên dịch và chạy trên JDK 17+:

```bash
javac BackpressureLogDemo.java
java BackpressureLogDemo
```

Kết quả `stdout`:

```text
accepted first: true
accepted second: false
queue size: 1
written: INFO order-created
```

Giải thích:

1. Consumer đợi latch nên chưa lấy được log ra khỏi queue.
2. Lệnh `offer` đầu tiên trả `true`: queue có một vị trí trống.
3. Lệnh `offer` thứ hai trả `false` ngay: queue đã đầy. Đây là **drop-new ở phía producer nếu chương trình bỏ qua sự kiện bị từ chối**.
4. Main in kết quả trước khi gọi `countDown()`; nhờ đó thứ tự stdout ổn định.
5. Consumer lấy log đầu tiên ra và kết thúc; `join()` đợi worker hoàn tất.

Đây là **mô phỏng nguyên lý queue**, chưa phải logging framework dùng trong ứng dụng thật. `System.out.println` ở worker mô phỏng ghi sink, không có retry, chính sách dừng bền vững, kiểm soát lỗi I/O hay bảo đảm độ bền. Trong thực tế worker cần vòng đời và xử lý shutdown đầy đủ.

## 6. API BlockingQueue giúp hiện thực backpressure

Trong Java, các API của `BlockingQueue<E>` thể hiện các chính sách khác nhau:

| Phương thức | Queue đã đầy | Ý nghĩa |
| --- | --- | --- |
| `offer(event)` | Trả `false` ngay | Không chặn; chương trình cần đếm drop hoặc fallback |
| `put(event)` | Chờ cho tới khi còn chỗ (hoặc bị interrupt) | Có thể làm producer chờ không giới hạn |
| `offer(event, timeout, unit)` | Đợi tối đa thời lượng đã cho rồi trả `false` nếu vẫn đầy | Chặn có giới hạn, phù hợp với latency budget |
| `add(event)` | Ném `IllegalStateException` nếu không còn chỗ | Thường không phải API mong muốn cho log thông thường |

Một đoạn **minh họa tích hợp**, không phải chương trình độc lập (giả sử `queue` là `BlockingQueue<LogEvent>` và có `droppedCounter`):

```java
// Event đã được chụp thành dữ liệu bất biến trước khi enqueue.
try {
    boolean accepted = queue.offer(event, 10, TimeUnit.MILLISECONDS);
    if (!accepted) {
        droppedCounter.increment();
    }
} catch (InterruptedException e) {
    Thread.currentThread().interrupt();
    droppedCounter.increment();
}
```

Lớp/method ở trên yêu cầu các import tương ứng (`TimeUnit`, `BlockingQueue`) và các biến `queue`, `event`, `droppedCounter` của ứng dụng. Bản thân **10 ms chỉ là ví dụ**; ngưỡng cần dựa trên SLO, lượng log và môi trường. Nếu thread bị interrupt, khôi phục interrupt flag; cần chính sách rõ ràng cho sự kiện chưa enqueue. `droppedCounter` chỉ đúng nếu sự kiện thực sự bị bỏ sau nhánh này.

Đừng sử dụng queue không giới hạn mà không có memory budget: nó có thể trì hoãn bão hòa cho tới khi heap cạn. Ngoài ra, chỉ kiểm tra `remainingCapacity()` rồi gọi `put()` cũng không bảo đảm không chặn vì nhiều producer có thể chạy đồng thời. Hãy dựa trên kết quả thật của lệnh enqueue.

## 7. Logback AsyncAppender: cấu hình liên quan

Trong ứng dụng Java dùng **SLF4J với Logback Classic**, `ch.qos.logback.classic.AsyncAppender` dùng queue có giới hạn để đưa sự kiện sang appender phía sau. Cách Logback chọn bỏ/chặn sự kiện phụ thuộc cấu hình, không chỉ phụ thuộc level logger.

Ví dụ `src/main/resources/logback.xml` dưới đây là **cấu hình mẫu**. `FILE` được đơn giản hóa để tập trung vào backpressure; ứng dụng production thường cần rolling, retention và giám sát ổ đĩa.

```xml
<configuration>
    <appender name="FILE" class="ch.qos.logback.core.FileAppender">
        <file>application.log</file>
        <append>true</append>
        <encoder>
            <pattern>%d{ISO8601} [%thread] %-5level %logger - %msg%n</pattern>
        </encoder>
    </appender>

    <appender name="ASYNC" class="ch.qos.logback.classic.AsyncAppender">
        <queueSize>2048</queueSize>
        <discardingThreshold>0</discardingThreshold>
        <neverBlock>false</neverBlock>
        <maxFlushTime>5000</maxFlushTime>
        <includeCallerData>false</includeCallerData>
        <appender-ref ref="FILE"/>
    </appender>

    <root level="INFO">
        <appender-ref ref="ASYNC"/>
    </root>
</configuration>
```

Ý nghĩa của các thiết lập quan trọng:

- **`queueSize`**: sức chứa hàng đợi sự kiện async (ở đây là 2.048 sự kiện). Không có nghĩa là 2.048 bytes; mỗi event có kích thước khác nhau.
- **`discardingThreshold`**: ngưỡng mà Logback chủ động loại bớt các event có mức thấp khi queue ít chỗ trống. Đặt `0` vô hiệu hóa cơ chế loại bỏ *sớm* đó; không đồng nghĩa mọi trường hợp đều không thể mất log.
- **`neverBlock=false`**: khi queue đầy, đường enqueue có thể chờ để có chỗ. Điều này ưu tiên giữ log đã chấp nhận nhưng làm thời gian gọi logger của producer tăng lên.
- **`neverBlock=true`**: enqueue không đợi khi queue đầy và có thể bỏ sự kiện, kể cả sự kiện mức cao, tùy tình huống.
- **`maxFlushTime=5000`**: khi dừng async appender, cấu hình khoảng đợi tối đa cho worker hoàn tất là 5.000 ms; nếu không xử lý kịp, các sự kiện còn lại có thể chưa được ghi. `0` có nghĩa đợi không giới hạn theo cơ chế shutdown của Logback.
- **`includeCallerData=false`**: tránh chi phí thu thập thông tin file/dòng gọi log, mặc định thường tắt.

Với Logback Classic, khi `discardingThreshold` không đặt rõ, ngưỡng mặc định thường tương đương **20% sức chứa queue**. Khi còn ít chỗ trống, Logback có thể chủ động bỏ các mức **TRACE/DEBUG/INFO**, còn WARN/ERROR được ưu tiên hơn trong bước chọn sự kiện. Nhưng nếu bật `neverBlock=true` và queue đã đầy, sự kiện WARN/ERROR **vẫn có thể bị loại**. Cần kiểm tra hành vi theo phiên bản Logback thực tế được dùng.

Tổ hợp cấu hình trên (`discardingThreshold=0`, `neverBlock=false`) phù hợp để **minh họa phương án ưu tiên không bỏ do queue quá tải**, song yêu cầu đo latency và cân nhắc rủi ro upstream bị block. Không coi đây là cấu hình mặc định tối ưu cho mọi ứng dụng.

Để thay đổi chính sách, có thể lựa chọn dựa trên workload:

```xml
<!-- Ví dụ đánh đổi: producer không chờ khi queue đầy;
     phải chấp nhận và theo dõi khả năng mất log. -->
<neverBlock>true</neverBlock>
```

Đoạn này là **một thuộc tính của AsyncAppender**, không phải XML cấu hình đầy đủ để chạy riêng.

Các logging backend khác có cơ chế riêng. Ví dụ **Log4j 2 Async Logger** có ring buffer và chính sách queue-full tùy cấu hình/phiên bản; không sao chép trực tiếp tên thuộc tính Logback sang Log4j 2. **`java.util.logging`** với handler tiêu chuẩn cũng không mặc nhiên sử dụng AsyncAppender của Logback.

## 8. Tính nhất quán, ordering và giới hạn đảm bảo

### 8.1. Một sự kiện được enqueue chưa chắc đã đến đích

Chấp nhận event vào queue chỉ cho biết **đã nhận vào vùng đệm trong tiến trình**, chưa chứng minh đã được ghi xuống đĩa hoặc chuyển tới collector. Có thể mất log khi:

- JVM crash hoặc bị kill trước khi consumer drain queue.
- Máy bị mất điện, sink trả lỗi, file system không sẵn sàng.
- Worker không thoát sạch, vượt thời gian flush lúc shutdown.
- Collector/downstream từ chối, mất dữ liệu hoặc áp dụng sampling riêng.
- Queue đầy và chính sách chủ động bỏ sự kiện.

Ngay cả khi gọi ghi file trực tiếp, việc write hoàn tất cũng không tự động đồng nghĩa dữ liệu đã được `fsync` bền vững trên ổ đĩa. Nếu có yêu cầu audit/financial compliance, cần thiết kế persistence, acknowledgment, retry/idempotency và chính sách lỗi theo yêu cầu, thường là **pipeline riêng**.

### 8.2. Thứ tự và timestamp

Trong **một queue có thứ tự với một consumer**, các sự kiện đã enqueue thường được consumer lấy ra theo thứ tự queue. Nhưng trong hệ thống nhiều producer, thứ tự enqueue phản ánh việc tranh chấp lúc ghi vào queue, không nhất thiết là thứ tự nghiệp vụ tổng thể. Với nhiều worker, nhiều sink hoặc pipeline phân tán, thời điểm log xuất hiện ở đích có thể khác thứ tự các thao tác ban đầu.

Timestamp có thể được chụp lúc tạo sự kiện rồi mới ghi ra sau. Do đó **thời điểm log hiện ra trên file/collector không nhất thiết là lúc sự kiện xảy ra**. Muốn theo dõi từng luồng công việc, dùng thêm request/trace ID và timestamp nhất quán. Logging backend nên chụp context cần thiết trước khi giao việc cho worker; nếu tự xây queue, đừng đưa đối tượng mutable rồi thay đổi trước khi consumer đọc.

## 9. Cách chọn chiến lược theo độ quan trọng của log

**Log chẩn đoán lưu lượng cao:** với TRACE/DEBUG có thể dùng sampling, loại sớm hoặc queue có giới hạn. Quan trọng là biết **đã bỏ bao nhiêu** và khi nào; tránh ghi counter drop bằng chính logger đang nghẽn.

**Log vận hành ứng dụng:** INFO/WARN/ERROR nên có quy tắc phù hợp SLO. Nếu cho producer chờ, đặt ngân sách thời gian và theo dõi p95/p99 latency; nếu chấp nhận drop, đo tỉ lệ mất event theo level. Đừng giả định WARN/ERROR “không bao giờ mất” chỉ vì cấu hình ưu tiên.

**Audit hoặc bản ghi bắt buộc:** không dùng buffer log best-effort làm nguồn sự thật duy nhất. Nên dùng cơ chế ghi bền vững, có xác nhận và xử lý lỗi được thiết kế riêng (ví dụ một thành phần giao dịch hoặc durable event pipeline phù hợp). Việc dùng cùng asynchronous appender với DEBUG/INFO có thể khiến audit bị ảnh hưởng bởi log nhiễu.

**Khi sink đang hỏng:** nâng queue size chỉ kéo dài thời gian trước khi hết bộ nhớ hoặc đầy queue. Cần có cảnh báo, bảo vệ đường request, giới hạn log burst, cơ chế recovery và runbook vận hành.

Một quy trình lựa chọn thực tế:

1. Xác định nhóm log nào bắt buộc phải giữ, nhóm nào có thể lấy mẫu/bỏ.
2. Đặt giới hạn latency mà lời gọi logger được phép cộng vào request.
3. Đo peak producer rate, sustained sink rate, kích thước event và RAM budget.
4. Chọn queue hữu hạn + policy khi đầy; ghi rõ tín hiệu đếm drop/timeout.
5. Thử tải với sink chậm hoặc ngừng để kiểm tra cả latency lẫn log loss.
6. Kiểm tra graceful shutdown, burst kéo dài và hành vi sau khi sink phục hồi.

## 10. Metrics và alerting cần có

Nếu có thể, ghi metrics độc lập với pipeline log đang nghẽn:

| Metric | Giúp trả lời |
| --- | --- |
| `log_queue_depth` | Có bao nhiêu sự kiện đang chờ? |
| `log_queue_capacity` hoặc tỷ lệ sử dụng | Queue gần đầy đến mức nào? |
| `log_events_enqueued_total` | Bao nhiêu event được chấp nhận vào queue? |
| `log_events_dropped_total{level,reason}` | Bao nhiêu event bị bỏ, vì sao và mức nào? |
| `log_enqueue_wait_seconds` | Producer mất bao lâu để enqueue? |
| `log_sink_write_seconds` và throughput | Sink ghi chậm ở đâu? |
| `log_queue_oldest_event_age_seconds` | Event lâu nhất đã phải đợi bao lâu? |
| `log_sink_errors_total` | Sink/collector đang lỗi với tần suất nào? |

Các tên trên là **gợi ý đặt metric**, không phải metric mặc định được mọi logging framework cung cấp. Phải kiểm tra khả năng instrument của framework, appender và công cụ giám sát đang dùng. Với nhãn metric, chỉ dùng giá trị hữu hạn như level, appender, reason; **không đưa request ID hoặc thông điệp log làm label** vì cardinality có thể tăng không kiểm soát.

`queue_depth / capacity` là dấu hiệu hữu ích nhưng phép đọc tức thời có thể thay đổi ngay khi nhiều thread cùng chạy. Cần xem **xu hướng và tốc độ tăng queue**, số sự kiện bị bỏ, thời gian enqueue, latency dịch vụ và tình trạng sink; queue chưa đầy vẫn có thể đã tạo đuôi trễ lớn.

Một bộ cảnh báo có ý nghĩa thường theo dõi: drop khác 0 đối với nhóm log trọng yếu; queue cao kéo dài; p99 thời gian enqueue tăng; lỗi ghi sink; backlog không giảm sau khi tải bình thường trở lại. Ngưỡng cụ thể tùy SLO và quy mô.

## 11. Kiểm tra backpressure có kiểm soát

Có thể dùng môi trường thử nghiệm với sink mô phỏng chậm, giảm throughput ghi hoặc bơm log trong khoảng thời gian xác định. Không nên gây lỗi I/O thật trên hệ thống production để “thử”.

Các bài thử cần kiểm chứng:

1. **Burst ngắn:** queue dâng rồi tự thoát, không làm request vượt SLO.
2. **Quá tải kéo dài:** khi queue đầy, chính xác policy nào diễn ra? Có tăng `dropped_total`, có chặn request hoặc vượt timeout không?
3. **Log level:** sự kiện INFO/DEBUG và ERROR xử lý khác nhau như cấu hình không? Thử cả tình huống queue **đã đầy**.
4. **Sink không phản hồi:** worker có retry vô hạn, tăng memory, ghi lặp hoặc gây deadlock không?
5. **Recovery:** khi sink khỏe lại, backlog xả trong bao lâu và có gây đột biến CPU/I/O không?
6. **Shutdown:** hệ thống dừng sạch có drain đúng thời gian cho phép không; nếu buộc dừng, đã nhận diện rõ rủi ro mất pending events chưa?
7. **Observability:** dashboard có phản ánh dropped, latency, queue depth; lỗi trong appender có được báo qua kênh riêng mà không log đệ quy vào chính nó không?

Đo kết quả bằng cả metrics **đầu nguồn** (tạo log) và **đích ghi** (log đã đến sink). Chỉ đếm `logger.info()` được gọi bao nhiêu lần không chứng minh có bấy nhiêu dòng log được lưu.

## 12. Lỗi thường gặp

- **“Async nên không bao giờ block”:** sai khi appender/queue chọn chính sách block hoặc sink yêu cầu công việc đồng bộ ở producer.
- **“Queue càng lớn càng an toàn”:** queue lớn ngốn heap, tăng độ trễ và không giải quyết `λ > μ` kéo dài.
- **“WARN/ERROR chắc chắn không mất”:** sai khi queue đầy với policy drop, khi process crash hoặc shutdown chưa xả xong.
- **“Đã enqueue = đã ghi đĩa”:** sai; phải phân biệt accepted, written, flushed, acknowledged và durable.
- **“Đổi sang queue không giới hạn là hết backpressure”:** có thể đổi vấn đề thành OOM/GC pause.
- **“Không thấy ERROR là không có lỗi”:** khi đang drop log, sự vắng mặt của log không phải bằng chứng hệ thống khỏe.
- **“Log thật nhiều để dễ debug”:** log burst có thể làm hỏng chính kênh quan sát. Cần giảm log lặp, sampling và correlation có kiểm soát.
- **“Metric drop cũng cứ ghi bằng logger đó”:** khi queue nghẽn, dòng báo drop lại có thể tiếp tục mất hoặc làm nghẽn nặng hơn; dùng metric/counter tách biệt.
- **“Chỉ log lỗi I/O bằng cùng appender lỗi”:** dễ gây vòng lặp hoặc che lỗi; có đường status/metrics độc lập.
- **“Một log được tạo trên request thread chắc sẽ xuất hiện ngay”:** log async có độ trễ queue và sink, nhất là khi backlog.

## 13. Tóm kết thực hành

Backpressure log là bài toán **tốc độ tạo sự kiện > tốc độ tiêu thụ**, thể hiện rõ nhất tại queue hữu hạn của async logging. Mục tiêu là biết hệ thống làm gì khi hàng đợi đầy và **kiểm soát được đánh đổi** giữa độ trễ nghiệp vụ, bộ nhớ, mức độ hoàn chỉnh của log và khả năng phục hồi.

Để triển khai an toàn: xác định mức quan trọng của từng loại sự kiện; dùng queue có giới hạn; lựa chọn block, timeout, drop, sampling hoặc fallback theo SLO; đo queue/drop/wait/sink; và thử nghiệm trạng thái nghẽn, phục hồi, shutdown. Với dữ liệu bắt buộc phải giữ, xây đường ghi bền vững riêng thay vì chỉ trông chờ vào appender bất đồng bộ nằm trong RAM.
