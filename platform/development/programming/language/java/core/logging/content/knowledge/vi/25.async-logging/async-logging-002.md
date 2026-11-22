# Queue log trong Java Logging bất đồng bộ

## 1. Queue log là gì và vì sao cần?

Khi ứng dụng Java gọi `logger.info(...)`, việc ghi ra console, file, socket hoặc hệ thống thu thập log có thể tốn thời gian vì định dạng thông điệp, khóa nội bộ và đặc biệt là I/O. Nếu mọi lời gọi log đều chờ đầu ra hoàn thành, một nơi ghi log chậm có thể kéo tăng độ trễ của request.

**Queue log** là hàng đợi trung gian giữ các *log event* đang chờ được một hoặc nhiều thread ghi log xử lý. Trong kiến trúc logging bất đồng bộ, thread nghiệp vụ (*producer*) thường tạo/đưa event vào queue; thread nền (*consumer/worker*) lấy event và chuyển tới appender đích.

```text
Thread xử lý request A ─┐
Thread xử lý request B ─┼─> tạo LogEvent ─> [ Queue có giới hạn ] ─> worker ─> appender ─> stdout/file/remote
Thread xử lý task C   ─┘                   ^          ^
                                         enqueue     dequeue
```

Mục tiêu chính là **tách thời điểm ứng dụng phát sinh log khỏi thời điểm log thật sự được ghi**, nhờ đó giảm thời gian chờ trên đường xử lý nghiệp vụ khi consumer theo kịp. Tuy nhiên, enqueue có thể chậm hoặc bị chặn khi queue đầy; vì vậy “async” không đồng nghĩa “không bao giờ block”, “không mất log” hay “log đã bền vững trên đĩa”.

Phân biệt ba thời điểm:

1. **Log được tạo**: framework nhận lời gọi `logger.info(...)`, đánh giá level/filter và chuẩn bị event.
2. **Log được chấp nhận vào queue**: producer đã gửi event thành công, nhưng consumer có thể chưa ghi ra đích.
3. **Log được appender xử lý**: consumer đã chuyển event đến appender; bản thân stdout, bộ đệm hệ điều hành hoặc hệ thống mạng vẫn có thể chưa lưu bền vững.

Queue chỉ là **bộ đệm tạm trong tiến trình** đối với hầu hết async appender; không phải hàng đợi durable như Kafka hay cơ chế xác nhận lưu trữ.

## 2. Một log event cần mang những gì?

Một log event thường có: timestamp, severity/level (`TRACE`, `DEBUG`, `INFO`, `WARN`, `ERROR`), tên logger, message và tham số, exception/stack trace nếu có, tên thread và context như `requestId`/`trace_id` trong MDC hoặc ThreadContext.

Mỗi event là đơn vị được đưa qua queue. **Dung lượng queue thường tính theo số lượng event, không phải byte.** Hai event có thể tiêu thụ bộ nhớ rất khác nhau: một dòng text ngắn so với exception có stack trace lớn hoặc object được serialize.

Một vấn đề quan trọng khi đi qua thread: context của request nằm trong `ThreadLocal`/MDC của **producer** có thể không còn tồn tại ở thread worker. Framework async thường chuẩn bị bản chụp các trường phù hợp trước khi enqueue. Không nên để consumer tự đọc `MDC.get(...)` từ thread nền rồi giả định đó là context của request ban đầu. Tương tự, truyền object mutable làm tham số log có thể gây sai lệch nếu giá trị của nó đổi trước lúc message được định dạng; hãy log các giá trị snapshot cần thiết.

Ví dụ log dưới đây giữ nguyên trace context của request tại thời điểm tạo event:

```text
2026-11-10 10:15:20.125 INFO  [http-42] trace_id=4bf92f3577b34da6a3ce929d0e0e4736 order=813 Created order
```

Ở đây timestamp, thread name và trace ID nói về **lúc event được tạo**, dù thread ghi file có thể xử lý vài mili giây sau.

## 3. Queue có giới hạn, producer và consumer hoạt động thế nào?

Mô hình cơ bản gồm các bước:

1. Logger xác định event có vượt ngưỡng level/filter không.
2. Nếu có, framework chuẩn bị event và cố **enqueue**.
3. Queue giữ thứ tự các event đã nhận theo cơ chế của nó.
4. Worker **dequeue** rồi thực hiện I/O với appender đích.
5. Khi ứng dụng dừng, hệ thống phải có cách kết thúc nhận event mới, xử lý phần tồn và dừng worker.

Trong Java, `BlockingQueue<E>` là cách trực quan để học mô hình producer–consumer. `ArrayBlockingQueue` cung cấp queue FIFO có capacity cố định. `LinkedBlockingQueue` cũng hỗ trợ capacity, nhưng nếu dùng constructor không truyền capacity thì giới hạn mặc định rất lớn; điều này không phù hợp để vô tư coi là “vô hạn an toàn”.

| API của `BlockingQueue` | Khi còn chỗ/dữ liệu | Khi queue đầy hoặc rỗng |
| --- | --- | --- |
| `offer(event)` | Chèn ngay, trả `true` | Trả `false` khi không thể chèn ngay |
| `put(event)` | Chèn thành công | Chờ đến khi có chỗ; có thể bị interrupt |
| `offer(event, timeout, unit)` | Chèn và trả `true` | Chờ tối đa timeout rồi trả `false` |
| `poll()` | Trả event đầu hoặc `null` | Trả `null` ngay nếu rỗng |
| `take()` | Lấy event đầu | Chờ cho đến khi có event |
| `poll(timeout, unit)` | Lấy event đầu | Chờ tối đa timeout rồi trả `null` |

Đây là **API Java dùng để minh họa chính sách**, không phải cam kết các logging framework đều dùng trực tiếp `BlockingQueue`. Ví dụ, Log4j 2 `AsyncLogger` dùng *ring buffer/LMAX Disruptor*, trong khi một số async appender dùng blocking queue.

### 3.1. FIFO có bảo đảm mọi log xuất hiện đúng thời gian?

Một queue FIFO giúp consumer lấy các event **theo thứ tự chúng đã được đưa thành công vào queue**. Với một producer tuần tự, thứ tự enqueue thường theo thứ tự lời gọi. Tuy nhiên, khi nhiều request/thread ghi log đồng thời, thứ tự giữa các thread phụ thuộc lịch chạy, thời điểm tạo/đưa event và số consumer; **không thể coi thứ tự ghi là thứ tự tuyệt đối mọi sự kiện trong hệ thống phân tán**.

Ngoài ra, nếu event được copy sang các queue khác nhau, nhiều appender, nhiều service hoặc đầu ra mạng, thứ tự log tại backend có thể thay đổi. Timestamp, trace ID và các trường correlation vẫn cần thiết.

### 3.2. Vì sao queue thường phải có giới hạn?

Nếu producer tạo log nhanh hơn consumer ghi trong một khoảng dài, backlog tăng. Queue giới hạn được bộ nhớ dành cho event chờ, đồng thời buộc hệ thống quyết định rõ phải làm gì khi đầy. Queue không giới hạn thực tế có thể gây GC pressure, tăng heap và kết thúc bằng `OutOfMemoryError`. Queue quá nhỏ có thể làm producer block hoặc mất log ngay khi gặp burst ngắn.

## 4. Khi queue đầy: lựa chọn nào và đánh đổi ra sao?

**Backpressure** là phản ứng của hệ thống khi tốc độ phát sinh log vượt quá khả năng ghi. Không có một chính sách phù hợp mọi ứng dụng.

| Chính sách | Khi đầy queue | Lợi ích | Chi phí/rủi ro |
| --- | --- | --- | --- |
| **Block producer** | Chờ đến khi có chỗ | Ít bỏ event chỉ vì queue đầy | Tăng latency request, giảm throughput, có thể làm nghẽn thread pool |
| **Drop event mới** | Không enqueue, đếm lần drop | Bảo vệ thời gian phản hồi | Mất một phần dữ liệu quan sát; phải giám sát số lần drop |
| **Drop theo mức độ ưu tiên** | Thường loại `TRACE`/`DEBUG`/`INFO` trước, giữ `WARN`/`ERROR` lâu hơn | Giữ tín hiệu quan trọng trong burst | Luồng sự kiện không còn đầy đủ; các log INFO đôi khi vẫn rất cần |
| **Fallback sang xử lý đồng bộ** | Một số event được ghi trực tiếp trên thread caller | Có cơ hội tiếp tục ghi khi queue nghẽn | Latency biến động mạnh, nguy cơ contention và lỗi I/O trên thread nghiệp vụ |
| **Chờ có timeout** | Chờ một khoảng ngắn rồi quyết định bỏ/fallback | Giới hạn tối đa thời gian chờ | Phải thiết kế rõ chính sách sau timeout |

Chọn **block** khi phải ưu tiên giữ log trong điều kiện tải tăng ngắn hạn và dịch vụ chấp nhận latency. Chọn **drop có đo đếm** khi chức năng chính cần duy trì responsiveness và có giải pháp riêng cho dữ liệu bắt buộc. Với audit trail, giao dịch tài chính hoặc sự kiện phải lưu chắc chắn, **đừng dùng async log queue trong bộ nhớ làm kho lưu trữ duy nhất**; cần cơ chế ghi bền vững, xác nhận thành công và chính sách retry riêng.

“Drop thấp, giữ ERROR” cũng không bảo đảm zero-loss: process crash, disk full, network failure và shutdown đột ngột vẫn có thể làm mất event ở mọi cấp độ. Ngay cả chính sách blocking cũng chỉ giải quyết một phần tình huống queue full.

## 5. Ví dụ Java 17+: mô phỏng queue log có giới hạn

Đây là chương trình **Java chuẩn có thể biên dịch và chạy độc lập**, không cần SLF4J/Logback. Nó cố tình giữ worker ở trạng thái chờ để chứng minh queue capacity bằng 2: hai event được nhận, event thứ ba bị từ chối; sau đó worker xử lý các event đã nhận và nhận tín hiệu kết thúc. Trong ứng dụng thật, nên dùng async appender của logging framework thay vì tự xây hệ thống ghi log này.

Lưu thành `QueueLogDemo.java`:

```java
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.BlockingQueue;
import java.util.concurrent.CountDownLatch;

public class QueueLogDemo {
    private record LogEvent(int number, String message) {}

    // Chỉ dùng làm tín hiệu dừng trong bản minh họa.
    private static final LogEvent STOP = new LogEvent(-1, "stop");

    public static void main(String[] args) throws InterruptedException {
        BlockingQueue<LogEvent> queue = new ArrayBlockingQueue<>(2);
        CountDownLatch startConsumer = new CountDownLatch(1);

        Thread worker = new Thread(() -> {
            try {
                startConsumer.await();
                while (true) {
                    LogEvent event = queue.take();
                    if (event == STOP) {
                        return;
                    }
                    System.out.println(
                            "sink: " + event.number() + " " + event.message());
                }
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        }, "log-writer");
        worker.start();

        System.out.println("enqueue 1: "
                + queue.offer(new LogEvent(1, "A")));
        System.out.println("enqueue 2: "
                + queue.offer(new LogEvent(2, "B")));
        System.out.println("enqueue 3: "
                + queue.offer(new LogEvent(3, "C")));

        startConsumer.countDown();
        queue.put(STOP); // Chờ có chỗ để đặt lệnh dừng sau event đã nhận.
        worker.join();   // Chờ worker xử lý xong trước khi thoát.
        System.out.println("shutdown: drained");
    }
}
```

Biên dịch và chạy trên JDK 17 trở lên:

```bash
javac --release 17 QueueLogDemo.java
java QueueLogDemo
```

Stdout chính xác khi chạy chương trình trên:

```text
enqueue 1: true
enqueue 2: true
enqueue 3: false
sink: 1 A
sink: 2 B
shutdown: drained
```

**Vì sao kết quả xác định?** Worker đợi `CountDownLatch` trước khi lấy phần tử. Trong khi đó main thread lần lượt `offer` ba event vào queue capacity 2, nên lần thứ ba trả `false`. Sau khi nhả latch, một worker duy nhất đọc hai event FIFO. `STOP` được đặt sau hai event đã được chấp nhận, rồi `join()` đợi worker kết thúc.

Ví dụ trên biểu diễn **drop khi queue đầy** bằng kết quả `offer(false)`; nó không phải mẫu shutdown sản xuất: `queue.put(STOP)` cũng có thể chờ lâu nếu worker kẹt, worker dừng bất thường hoặc sink hỏng. Ứng dụng thật cần timeout, xử lý interrupt, đếm drop, báo lỗi worker và giới hạn thời gian drain. Đồng thời, câu “drained” trong ví dụ chỉ có nghĩa consumer đã in xong các event qua `System.out`, không khẳng định nội dung đã được lưu bền vững xuống đĩa.

Nếu thay `offer` bằng `put`, lời gọi thứ ba sẽ **block** cho đến khi worker lấy event; với latch trong ví dụ này, gọi `put` trước khi nhả latch sẽ gây chờ mãi. Đây là minh họa tại sao **blocking enqueue có thể tạo deadlock hoặc khuếch đại sự cố** nếu thiết kế quan hệ thread không cẩn thận.

## 6. Logback: cấu hình queue với AsyncAppender

Với ứng dụng Spring Boot dùng **SLF4J + Logback**, `ch.qos.logback.classic.AsyncAppender` là cách phổ biến để đặt queue trước appender ghi log. Ví dụ `src/main/resources/logback-spring.xml`:

```xml
<configuration>
    <appender name="STDOUT" class="ch.qos.logback.core.ConsoleAppender">
        <encoder>
            <pattern>%d{HH:mm:ss.SSS} %-5level [%thread] %logger{36} - %msg%n</pattern>
        </encoder>
    </appender>

    <appender name="ASYNC" class="ch.qos.logback.classic.AsyncAppender">
        <queueSize>1024</queueSize>
        <discardingThreshold>0</discardingThreshold>
        <neverBlock>false</neverBlock>
        <includeCallerData>false</includeCallerData>
        <maxFlushTime>10000</maxFlushTime>
        <appender-ref ref="STDOUT"/>
    </appender>

    <root level="INFO">
        <appender-ref ref="ASYNC"/>
    </root>
</configuration>
```

Trong cấu hình này:

- `STDOUT` vẫn chịu trách nhiệm định dạng và ghi; `ASYNC` giữ queue/worker. Root logger chỉ tham chiếu `ASYNC` để tránh ghi đồng bộ thêm một bản từ cùng event.
- `queueSize=1024` là sức chứa tính bằng **event**, không phải số byte.
- `discardingThreshold=0` vô hiệu hóa **cơ chế loại log thấp khi queue sắp đầy** của `AsyncAppender`. Nó **không bảo đảm không mất log** vì shutdown, crash, lỗi sink hoặc cấu hình khác vẫn có thể gây mất.
- `neverBlock=false` cho phép producer chờ khi queue **đầy hẳn**. Khi lưu lượng cao kéo dài, lời gọi `logger.info(...)` có thể trở nên chậm tương tự logging đồng bộ.
- `includeCallerData=false` tránh chi phí lấy thông tin vị trí gọi (class/file/line) khi không cần thiết.
- `maxFlushTime=10000` cho worker tối đa khoảng 10 giây để flush khi appender dừng; nếu không drain hết trong thời gian đó, event còn lại có thể mất. Đây là hạn chờ khi shutdown, **không phải độ trễ mỗi log**.

**Mặc định Logback cần nhớ:** `queueSize` mặc định là **256**. Khi queue chỉ còn khoảng **20% chỗ trống**, `AsyncAppender` mặc định có thể bỏ các event `TRACE`, `DEBUG` và `INFO`; `WARN` và `ERROR` được ưu tiên giữ khi queue gần đầy. `neverBlock` mặc định là `false`. Nếu ứng dụng cần giữ log INFO khi burst, phải xem xét `discardingThreshold=0` cùng khả năng backpressure; đừng chỉ tăng queue size và mặc định rằng không còn drop.

Để ưu tiên giữ latency thay vì chờ queue:

```xml
<neverBlock>true</neverBlock>
```

Khi queue đầy, producer không chờ và event mới có thể bị bỏ. Chỉ nên bật nếu đã hiểu và giám sát mức mất log. Trong cả hai chính sách, throughput thực tế vẫn bị giới hạn bởi appender đích (đặc biệt stdout khi log shipper hoặc đích lưu trữ bị nghẽn).

### 6.1. Logback và MDC

MDC chứa các trường như `requestId` hoặc `trace_id` phục vụ correlation. Logback AsyncAppender chuẩn bị các trường “rẻ” như tên thread và MDC ở phía caller trước khi dispatch, giúp pattern ở worker vẫn có ngữ cảnh đúng. Ví dụ sửa pattern thành:

```xml
<pattern>%d{HH:mm:ss.SSS} %-5level [%thread] request=%X{requestId} trace=%X{trace_id} - %msg%n</pattern>
```

Đây là **thay thế pattern** bên trong appender có sẵn, không thêm appender khác. Ứng dụng vẫn phải gán MDC tại đầu request và dọn/khôi phục trong `finally` hoặc dùng instrumentation có hỗ trợ; async queue không tự tạo trace context.

Nếu bật thông tin vị trí gọi `%class`, `%method`, `%file`, `%line` thì cần kiểm tra `includeCallerData` theo thực tế; lấy stack/caller info thường làm tăng chi phí trên thread caller. Đừng bật chỉ để log trông đầy đủ hơn.

### 6.2. Khi nào Logback queue vẫn gây chậm?

Ở mức ổn định, nếu event đến nhanh hơn khả năng ghi, queue dần đầy. Sau đó:
- Với `neverBlock=false`, producer bị chặn lúc enqueue; latency request tăng và có thể ảnh hưởng thread pool.
- Với `neverBlock=true`, throughput nghiệp vụ có thể ít bị ảnh hưởng hơn nhưng log bị drop.
- Với ngưỡng discard mặc định, một phần log mức thấp bị bỏ **trước cả khi queue đầy**.

Do đó, cấu hình async không thay thế yêu cầu kiểm tra tốc độ ghi thực tế, log volume, filtering và retention.

## 7. Log4j 2: AsyncAppender và AsyncLogger khác gì?

**Log4j 2 AsyncAppender** dùng blocking queue để đưa log event sang thread gọi appender đích. Ví dụ `log4j2.xml` trong ứng dụng đã cấu hình dùng Log4j 2 Core:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<Configuration status="WARN">
    <Appenders>
        <Console name="STDOUT" target="SYSTEM_OUT">
            <PatternLayout pattern="%d{HH:mm:ss.SSS} %-5p [%t] %c - %m%n"/>
        </Console>
        <Async name="ASYNC" bufferSize="1024" blocking="true">
            <AppenderRef ref="STDOUT"/>
        </Async>
    </Appenders>
    <Loggers>
        <Root level="info">
            <AppenderRef ref="ASYNC"/>
        </Root>
    </Loggers>
</Configuration>
```

`bufferSize` là số event tối đa được xếp hàng (mặc định theo tài liệu Log4j 2 hiện hành là 1024). `blocking=true` cho phép chờ khi queue đầy. Nếu đổi sang `blocking=false`, hành vi cụ thể khi full chịu tác động bởi queue-full policy và `errorRef` nếu cấu hình; **không tự suy luận rằng các event sẽ luôn được ghi một cách đồng bộ hoặc được lưu lại**. Nếu appender đích lỗi trên thread async, exception thường không truyền trở lại thread đã gọi logger.

**Log4j 2 AsyncLogger** là cơ chế khác: sử dụng **LMAX Disruptor/ring buffer**, có khả năng giảm contention trong nhiều workload. Nó cũng là một cấu trúc buffer có capacity và vẫn phải quyết định chính sách khi đầy. Để dùng AsyncLogger toàn phần hoặc trộn với sync logger cần cấu hình Log4j 2 tương ứng cùng dependency Disruptor tương thích. Không phải chỉ đặt `<Async>` trong `log4j2.xml` là đã chuyển thành AsyncLogger.

| Thuộc tính | Logback AsyncAppender | Log4j 2 AsyncAppender | Log4j 2 AsyncLogger |
| --- | --- | --- | --- |
| Cơ chế truyền event | Blocking queue | Blocking queue | Ring buffer qua LMAX Disruptor |
| Thread ghi thực tế | Worker của appender | Worker của appender | Consumer/async logging thread |
| Backpressure | Chờ hoặc bỏ theo `neverBlock`; có discard threshold | Blocking/queue-full policy, `errorRef` | Queue-full policy của async components |
| Điểm cần chú ý | Ngưỡng discard và `maxFlushTime` | Queue/full policy, lỗi appender nền | Dependency, wait strategy, ring-buffer size và queue-full policy |

Không xếp **AsyncAppender ngay sau AsyncLogger** mà không có lý do; hai lớp async bổ sung có thể tạo thêm queue, overhead và khiến việc truy dấu loss/latency khó hơn. Hãy đo đạc trước khi chọn cơ chế.

## 8. Tính kích thước queue và nhận diện bottleneck

Gọi:

- `λ` (*lambda*) là tốc độ producer tạo event (event/giây).
- `μ` (*mu*) là tốc độ consumer/appender xử lý ổn định (event/giây).
- `T` là thời gian burst (giây).
- `Q` là số event xếp hàng tại một thời điểm.

Nếu `λ > μ` trong một khoảng ngắn, backlog tăng xấp xỉ:

```text
backlog_tang ≈ (lambda - mu) × T
```

Ví dụ peak phát sinh **12.000 event/giây**, sink chỉ xử lý **8.000 event/giây** trong **2 giây**. Queue cần hấp thụ khoảng **8.000 event** chỉ cho burst đó, nếu ban đầu rỗng và mô hình tốc độ này giữ ổn định. Capacity 10.000 có thể là điểm thử nghiệm để tạo một ít khoảng đệm; **không phải công thức cấu hình production mặc định**, vì kích thước event, GC, tăng đột biến và thời gian xử lý thay đổi.

Nếu sau burst producer trở lại **6.000 event/giây**, sink 8.000 event/giây sẽ xả backlog với chênh lệch 2.000 event/giây; xả 8.000 event ước khoảng **4 giây**. Nếu producer **liên tục** 12.000 event/giây trong khi consumer chỉ đạt 8.000, tăng capacity chỉ hoãn thời điểm đầy. Phải giảm log volume, tăng hiệu suất sink/consumer, lọc level, điều chỉnh pipeline hoặc chấp nhận chính sách mất log/backpressure.

### 8.1. Chi phí bộ nhớ

Queue size không phản ánh trực tiếp heap usage. Để ước tính thô, cần biết event object, tham số/exception, message đã format hay chưa, MDC snapshot và overhead của chính queue. Ví dụ **10.000 event × 1 KiB/event ≈ 9,8 MiB** chỉ là giả định minh họa; một stack trace dài hoặc object graph bị giữ tham chiếu có thể lớn hơn nhiều. Nên đo heap và GC với workload thật.

### 8.2. Batch và throughput

Consumer có thể ghi theo batch hoặc appender có buffer để giảm chi phí I/O mỗi event. Nhưng batch lớn có thể tăng thời gian log nằm chờ và lượng dữ liệu mất khi process chết. Cần phân biệt:
- **Event queued**: đang chờ consumer.
- **Event forwarded**: đã được appender xử lý.
- **Buffered/OS flushed**: dữ liệu đã đi tới tầng buffer hoặc hệ điều hành.
- **Durably stored**: đích lưu trữ bảo đảm ở mức phù hợp; không mặc định chỉ vì gọi flush.

Mục tiêu tốt là throughput đạt yêu cầu cùng độ trễ log chấp nhận được, chứ không phải chỉ tăng queue capacity.

## 9. Quan sát queue: cần đo gì?

Một hệ thống dùng async log queue nên cung cấp hoặc suy ra các chỉ số sau:

| Chỉ số | Ý nghĩa vận hành | Dấu hiệu cần chú ý |
| --- | --- | --- |
| Queue depth / utilization | Số event đang chờ / capacity | Liên tục gần 100% hoặc tăng không hạ |
| Enqueue rate | Số event được chấp nhận mỗi giây | Burst vượt năng lực sink |
| Dequeue/processed rate | Số event worker xử lý mỗi giây | Thấp bất thường, I/O nghẽn |
| Dropped event count/rate | Số lần event bị bỏ do policy | Bất kỳ giá trị nào với log quan trọng |
| Enqueue block duration | Thời gian producer chờ queue | p95/p99 request tăng theo thời gian chờ |
| Event age / queue wait time | Chênh giữa lúc tạo và lúc được xử lý | Log xuất hiện trễ, gần timeout/retention |
| Appender errors/retries | Lỗi disk, network, encoder, endpoint | Queue không drain, retry storm |
| Shutdown drain duration | Thời gian xử lý log còn lại lúc dừng | Bị cắt vì timeout, log cuối bị mất |

Tính `queue.size()` trong môi trường concurrent chỉ là **snapshot tức thời**; không dùng một phép đọc làm bằng chứng đủ để kết luận hệ thống không có drop. Các framework có khả năng thống kê khác nhau: xem metrics/instrumentation thực sự hỗ trợ, hoặc bọc tại lớp vận hành nếu cần.

Nên thử nghiệm các tình huống:
1. Burst ngắn cao hơn throughput bình thường: queue đầy bao nhiêu phần trăm, xả trong bao lâu?
2. Sink bị chậm hoặc ngừng: latency request biến động thế nào, bao nhiêu log bị mất?
3. Ghi exception lớn liên tục: heap và GC thay đổi ra sao?
4. Dừng ứng dụng khi còn backlog: thời gian drain và tỷ lệ log cuối được ghi?
5. Lỗi permission/disk full/network: appender báo lỗi ở đâu, người vận hành có nhận cảnh báo không?
6. Tải nhiều producer: throughput thực, contention và thứ tự log có đáp ứng yêu cầu không?

Với hệ thống có `trace_id`, kiểm tra thêm rằng context trong event lấy từ producer và không biến thành context của thread log worker.

## 10. Shutdown và độ tin cậy của log

Một vòng đời hợp lý với queue có giới hạn:

```text
RUNNING (nhận event) -> STOPPING (không nhận thêm event mới)
    -> drain queue còn lại -> flush appender/sink -> dừng worker -> STOPPED
```

Trong framework, phương thức/lifecycle cụ thể khác nhau. Với Logback, `AsyncAppender` cố flush queue khi `LoggerContext` dừng theo `maxFlushTime`; quá timeout thì có thể bỏ phần còn lại. Đóng ứng dụng bằng `kill -9`, process crash hoặc container bị terminate quá nhanh không cho worker cơ hội drain. Khi triển khai container, cấu hình thời gian graceful termination đủ cho tình huống backlog thực tế, đồng thời không giữ shutdown vô hạn nếu sink đang kẹt.

**Không đồng nhất drain với durability:** khi worker đã lấy hết queue và gọi appender, dữ liệu có thể còn trong OS buffer, transport hoặc pipeline xa. Với log quan trọng cần độ bền cao, hãy phân biệt yêu cầu “đã gửi”, “đã được nhận”, “đã persist” và thiết kế đường thu thập theo đúng mức bảo đảm cần có.

Đối với exception trong worker:
- Không im lặng nuốt lỗi disk/encoder/transport; dùng cơ chế status/error reporting phù hợp, tránh log lỗi nội bộ bằng chính queue đang hỏng gây đệ quy.
- Retry có giới hạn, có backoff; nếu cứ retry vô hạn mà giữ toàn bộ event trên heap, OOM vẫn có thể xảy ra.
- Khi thất bại kéo dài, cần chính sách có chủ đích về drop, failover hoặc dừng dịch vụ tùy mức quan trọng của log.

## 11. Lỗi thường gặp khi triển khai

| Hiện tượng | Khả năng nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Bật async nhưng p99 latency vẫn tăng khi traffic spike | Queue đầy và producer đang block | Đo queue depth, enqueue wait, sink throughput và policy. |
| Không tìm thấy log INFO dù code đã chạy | Logback discard threshold, level/filter hoặc full queue | Xem cấu hình discard, số lần drop, level. |
| Tăng queueSize mãi vẫn đầy | Tốc độ tạo log lớn hơn tốc độ xử lý kéo dài | Sửa bottleneck, giảm log volume thay vì chỉ mở rộng queue. |
| Memory/GC tăng mạnh | Event giữ object/stack trace lớn, queue quá dài | Đo heap, rút gọn payload và giới hạn capacity. |
| Log cuối mất khi rolling restart | Không drain hết, timeout dừng thấp | Chỉnh graceful shutdown, theo dõi remaining events. |
| Hai dòng log cho cùng một event | Root logger tham chiếu cả async và sink sync hoặc nhiều pipeline thu | Kiểm tra appender references, additivity và collector. |
| Trace ID hoặc requestId bị sai | Context không được snapshot đúng khi enqueue hoặc MDC không được dọn | Kiểm tra MDC lifecycle trên thread tạo event. |
| Thấy “flushed” nhưng backend thiếu log | OS/network/backend buffering hoặc lỗi export | Kiểm tra chuỗi delivery và chính sách xác nhận từ phía đích. |
| Worker logging gặp exception rồi im lặng | Lỗi trên thread async không quay lại caller | Bật status/error monitoring của framework, kiểm tra sink failure. |

Với log chứa dữ liệu nhạy cảm, **lọc/mask trước khi event được đưa vào queue**. Đừng giữ token, password, thông tin cá nhân hay object chứa secret trong event nhằm trông chờ consumer loại bỏ về sau; dữ liệu đã nằm trong bộ nhớ và có thể bị ghi ra đích khác.

## 12. Cách quyết định có nên dùng queue log

Dùng async logging khi đo thực tế cho thấy I/O/encoding của log đang ảnh hưởng request latency hoặc throughput và ứng dụng có thể chấp nhận các đánh đổi của queue. Với dịch vụ log volume thấp, synchronous logging đơn giản hơn, dễ phát hiện lỗi và không cần thêm bộ đệm.

Trước khi triển khai, cần trả lời được:

1. Mỗi giây tạo bao nhiêu event ở mức bình thường và peak?
2. Sink ghi được bao nhiêu event/giây trong tình huống chậm nhất?
3. Cho phép producer chờ bao lâu khi queue đầy?
4. Nếu phải drop, log nào được phép mất và làm sao phát hiện việc đó?
5. Queue chiếm bao nhiêu heap với event lớn và exception?
6. Dừng ứng dụng có bao lâu để drain, và yêu cầu bền vững thực sự đến đâu?
7. MDC/trace context và thứ tự log có được bảo toàn tới đích không?

Một thiết kế đúng không chỉ “có queue” mà còn **có capacity hữu hạn, policy khi đầy, giám sát mất/chờ log, và quy trình shutdown có giới hạn thời gian**. Queue là công cụ cân bằng giữa latency nghiệp vụ và độ đầy đủ của dữ liệu quan sát; chọn cấu hình theo số đo thực tế.

## Tài liệu tham khảo

- [Oracle Java 21 – BlockingQueue](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/BlockingQueue.html).
- [Oracle Java 21 – ArrayBlockingQueue](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/ArrayBlockingQueue.html).
- [Logback manual – AsyncAppender và các cấu hình queue](https://logback.qos.ch/manual/appenders-async-sift.html).
- [Apache Log4j 2 – Async appender](https://logging.apache.org/log4j/2.x/manual/appenders/delegating.html).
- [Apache Log4j 2 – Asynchronous loggers](https://logging.apache.org/log4j/2.x/manual/async.html).
- [Apache Log4j 2 – Performance](https://logging.apache.org/log4j/2.x/manual/performance.html).