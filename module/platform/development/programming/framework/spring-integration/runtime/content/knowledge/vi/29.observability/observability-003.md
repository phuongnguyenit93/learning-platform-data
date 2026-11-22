# Micrometer Timer, Counter và Distribution trong Spring Integration Runtime

## Mục tiêu bài học

Trong **SPRING_INTEGRATION_RUNTIME**, một message có thể đi qua inbound adapter, channel, poller, executor, handler, gateway và các hệ thống ngoài. Khi flow chậm hoặc backlog tăng, chỉ nhìn CPU và heap thường không đủ để biết nguyên nhân nằm ở đâu. **Micrometer** cung cấp mô hình đo lường thống nhất để quan sát **tần suất**, **thời gian xử lý** và **phân phối kích thước/giá trị** tại những ranh giới quan trọng.

Ba loại meter đặc biệt hữu ích là:

- **Timer**: một thao tác mất bao lâu; có **số lần ghi nhận, tổng thời gian, thời gian lớn nhất** và có thể xuất histogram/percentile tùy cấu hình.
- **Counter**: một loại sự kiện đã xảy ra bao nhiêu lần, ví dụ lỗi parse, timeout, duplicate được chặn, retry attempt.
- **DistributionSummary**: một tập giá trị không mang ngữ nghĩa thời gian, ví dụ kích thước payload (byte), số phần tử trong batch hoặc kích thước message group.

Bài thuộc chương **Observability**, liên hệ ba meter với đặc tính Spring Integration: **DirectChannel, ExecutorChannel, poller, consumer, transaction, retry, errorChannel, correlation và MessageStore**.

Sau bài này, bạn có thể:

1. Chọn đúng loại meter thay vì dùng Counter/Timer/DistributionSummary tùy tiện.
2. Đặt tên metric, đơn vị đo và tag có cardinality an toàn.
3. Ghi Timer bằng **Timer.Sample** quanh một service activator, kể cả khi exception xảy ra.
4. Dùng Counter cho retry/error/duplicate và DistributionSummary cho payload/batch size.
5. Phân biệt **send latency**, **queue wait**, **handler execution latency** và **business end-to-end latency** khi qua channel bất đồng bộ.
6. Xuất metrics từ Spring Boot Actuator/Micrometer sang Prometheus hoặc backend tương thích, hiểu count/sum/bucket và percentile.
7. Kiểm thử meter bằng **SimpleMeterRegistry** và xây dashboard/alert có ý nghĩa khi flow lỗi, restart hoặc scale nhiều instance.

> **Nguyên tắc:** Đầu tiên xác định **đơn vị được đo** (message, attempt, delivery, batch hay business operation), **ranh giới thời gian** và **điểm phát sự kiện**. Sau đó mới chọn loại meter. Metric có số đẹp nhưng đo sai ranh giới dễ dẫn đến kết luận vận hành sai.

## 1. Observability trả lời câu hỏi nào tại runtime?

Xét một luồng nhập đơn hàng:

~~~mermaid
flowchart LR
    S["Broker inbound adapter"] --> C["ordersInput<br/>DirectChannel"]
    C --> Q["QueueChannel<br/>persistent store"]
    Q --> P["Polling consumer"]
    P --> E["ExecutorChannel / worker"]
    E --> H["Order handler"]
    H --> D[("Database")]
    H --> X["Outbound HTTP"]
    H -. "Exception" .-> R["errorChannel / recovery"]
~~~

Một người vận hành có thể hỏi:

| Câu hỏi | Phép đo nên có | Không được nhầm với |
| --- | --- | --- |
| Có bao nhiêu yêu cầu đến? | Counter ingress hoặc receive count | Số giao dịch nghiệp vụ duy nhất |
| Handler mất bao lâu? | Timer quanh handler | Thời gian message xếp hàng trước handler |
| Có bao nhiêu lần retry? | Counter retry attempts | Số message nguồn hoặc số lỗi nghiệp vụ duy nhất |
| Payload lớn tới đâu? | DistributionSummary theo số byte | Timer hoặc Gauge kích thước queue hiện tại |
| Bao nhiêu message đang chờ? | **Gauge** queue depth/backlog | Counter tổng message từng đi vào queue |
| Bao nhiêu flow đang lỗi? | Counter theo error type + rate | Counter tích lũy kể từ lúc JVM start |
| P95 latency tăng vì đâu? | Timer theo từng giai đoạn + queue wait | Một Timer chỉ đo thao tác send vào ExecutorChannel |
| Có bị duplicate không? | Counter duplicate delivery / duplicate effect | Chỉ số delivery count không có idempotency key |

**Logs** cho biết sự kiện cụ thể và khóa nghiệp vụ; **traces** nối các bước trong một execution; **metrics** tổng hợp diễn biến theo thời gian để phát hiện xu hướng và cảnh báo. Ba trụ cột bổ sung cho nhau, không thay thế nhau.

## 2. Mô hình meter của Micrometer

**MeterRegistry** là nơi đăng ký/ghi các meter. Một meter có **name**, **tags** và loại cụ thể; tổ hợp **name + tags** đại diện cho một chuỗi số liệu.

| Loại | Micrometer API | Dữ liệu chính | Thường dùng |
| --- | --- | --- | --- |
| **Counter** | Counter.increment() | Tổng số lần hoặc số lượng tăng | Error, retry, discard, successful events |
| **Timer** | Timer.record(...), Timer.Sample | Số lần, tổng thời gian, tối đa, histogram tùy chọn | Handler/HTTP/DB/poller execution duration |
| **DistributionSummary** | DistributionSummary.record(value) | Count, sum, max, histogram tùy chọn | Byte size, records per batch, message group size |
| **Gauge** | Gauge theo đối tượng/giá trị quan sát | Giá trị tức thời tại thời điểm lấy mẫu | Queue depth, in-flight, executor active |
| **LongTaskTimer** | LongTaskTimer.start()/sample.stop() | Số task dài đang chạy và thời lượng của chúng | Batch dài, job chờ kéo dài, công việc đang thực thi |

**Counter chỉ tăng**, không dùng để biểu diễn số item đang nằm trong hàng đợi. Một QueueChannel có thể nhận 1.000 và xử lý hết 1.000 message: ingress Counter vẫn là 1.000, còn Gauge backlog phải về 0.

**Timer tự bao gồm count**. Nếu chỉ cần biết cả số lần và thời gian của cùng một thao tác, không nhất thiết đăng ký thêm một Counter riêng đếm y hệt từng lần xử lý. Counter riêng hữu ích khi đại diện cho **ngữ nghĩa khác**, chẳng hạn error classified, duplicate suppressed hoặc retry initiated.

**DistributionSummary không phải Timer**. Ghi số 300 vào summary có nghĩa một **giá trị số 300 theo base unit bạn chọn**, không tự biến nó thành 300 ms.

## 3. Timer: đo thời gian thao tác

### Timer ghi nhận những gì?

Sau ba lần xử lý mất lần lượt **80 ms**, **100 ms**, **420 ms**:

| Đại lượng | Giá trị ví dụ |
| --- | ---: |
| Timer count | 3 |
| Timer total time | 600 ms |
| Thời gian trung bình của ba lần | 200 ms |
| Thời gian lớn nhất quan sát | 420 ms |

Trong Micrometer, **Timer ghi thời lượng bằng các API Duration hoặc Runnable/Callable**, còn backend có thể xuất ra **giây** hoặc đơn vị phù hợp. Đừng trộn số nanosecond/millisecond thủ công với unit mà API đang nhận.

~~~java
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import java.time.Duration;

class TimerExamples {
    private final MeterRegistry registry;

    TimerExamples(MeterRegistry registry) {
        this.registry = registry;
    }

    void recordOneDuration() {
        Timer timer = Timer.builder("orders.validation.duration")
                .description("Duration of order validation")
                .tag("flow", "order-import")
                .register(registry);

        timer.record(Duration.ofMillis(125));
    }

    void recordRunnable() {
        Timer timer = registry.timer(
                "orders.normalization.duration",
                "flow", "order-import");

        timer.record(() -> normalizeOrder());
    }

    private void normalizeOrder() {
        // Demo: phần việc cần đo.
    }
}
~~~

### Timer.Sample khi outcome chỉ biết sau khi chạy

Đây là cách phù hợp để gắn tag **outcome=success/error** sau khi handler kết thúc:

~~~java
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import org.springframework.integration.annotation.ServiceActivator;
import org.springframework.messaging.Message;
import org.springframework.stereotype.Component;

record OrderCommand(String orderId, int itemCount) {}

interface OrderProcessor {
    void process(OrderCommand order);
}

@Component
class InstrumentedOrderHandler {
    private final MeterRegistry registry;
    private final OrderProcessor processor;

    InstrumentedOrderHandler(MeterRegistry registry,
                             OrderProcessor processor) {
        this.registry = registry;
        this.processor = processor;
    }

    @ServiceActivator(inputChannel = "orderRequests")
    public void handle(Message<OrderCommand> message) {
        Timer.Sample sample = Timer.start(registry);
        String outcome = "success";

        try {
            processor.process(message.getPayload());
        } catch (RuntimeException failure) {
            outcome = "error";
            throw failure; // Để error flow/transaction nhận lỗi thật.
        } finally {
            Timer timer = Timer.builder("orders.handler.duration")
                    .description("Execution duration of order handler attempt")
                    .tag("flow", "order-import")
                    .tag("handler", "order-handler")
                    .tag("outcome", outcome)
                    .register(registry);
            sample.stop(timer);
        }
    }
}
~~~

**Cách đọc chính xác:**

1. Một lần **handle(...) được gọi** tương ứng một sample, kể cả khi RuntimeException ném ra.
2. Khi có **RequestHandlerRetryAdvice** bên ngoài method, method có thể được gọi nhiều lần. Timer trên sẽ đo **mỗi attempt của handler**, không mặc định đo một business operation duy nhất.
3. Khi có **ExecutorChannel**, method chạy trên worker thread; Timer đo phần việc trong method, **không đo thời gian chờ trong executor queue**.
4. Không đưa **orderId, correlationId, messageId, exception message** vào tag, vì các giá trị này có thể gần như duy nhất mỗi request.
5. Mẫu này phân loại RuntimeException; nếu nghiệp vụ dùng các loại lỗi khác hoặc trả status thất bại nhưng không ném exception, cần định nghĩa **outcome** tương ứng.
6. **Timer.Sample** là đối tượng đo một lần thực thi. Nếu cần đo nhiều pha, tạo nhiều sample tại các ranh giới rõ ràng, không dừng cùng sample nhiều lần cho những metric khác nhau.

### Timer API cần chọn đúng ranh giới

| Timer | Bắt đầu | Kết thúc | Ý nghĩa |
| --- | --- | --- | --- |
| **send duration** | Trước MessageChannel.send | Khi send trả/throw | Thời gian gửi qua channel, có thể chỉ là handoff |
| **poll duration** | Khi poller bắt đầu lượt poll | Khi lượt poll kết thúc | Chi phí poll/receive/dispatch theo topology |
| **queue wait** | Khi message được enqueue | Khi consumer bắt đầu xử lý | Độ trễ xếp hàng |
| **handler duration** | Khi handler được gọi | Khi handler trả/throw | Thời gian chạy handler attempt |
| **business end-to-end** | Khi nghiệp vụ được chấp nhận | Khi kết quả cuối được commit/xác nhận | SLA nghiệp vụ; có thể qua nhiều delivery/retry |

Các Timer trên **không mặc nhiên cộng lại thành một con số duy nhất** nếu có xử lý song song, overlap, chờ retry hoặc nhiều nhánh. Cần xác định topology và timestamp/clock đo thực tế.

## 4. Counter: đo sự kiện và nguyên nhân lỗi

Counter đo **số lượng tăng**. Ví dụ mỗi lần một message bị đánh dấu duplicate:

~~~java
import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;

class DuplicateMeter {
    private final Counter duplicates;

    DuplicateMeter(MeterRegistry registry) {
        this.duplicates = Counter.builder("orders.duplicate.suppressed")
                .description("Business duplicate events safely suppressed")
                .tag("flow", "order-import")
                .register(registry);
    }

    void duplicateWasSuppressed() {
        duplicates.increment();
    }
}
~~~

Counter có thể tăng một số dương khác 1 khi đang đếm một **số lượng thực sự được xử lý**, nhưng giá trị âm không phù hợp với tính chất Counter.

### Định nghĩa counter theo sự kiện quan sát được

| Metric ví dụ | Khi nào tăng? | Không nên tăng khi |
| --- | --- | --- |
| **orders.ingress.received** | Một message được consumer nhận theo đơn vị delivery | Chỉ vì producer gửi request nhưng adapter chưa nhận |
| **orders.handler.failed** | Một handler attempt thật sự thất bại | Một message nằm chờ queue mà chưa chạy |
| **orders.retry.attempted** | Một lần retry được bắt đầu | Lần attempt đầu tiên nếu policy định nghĩa “retry” là các lần sau |
| **orders.duplicate.suppressed** | Bản lặp bị xác minh và chặn an toàn | Chỉ thấy cùng correlationId; đó chưa chắc là duplicate |
| **orders.dlq.published** | DLQ/quarantine đã nhận thành công theo hợp đồng | Mới quyết định gửi DLQ nhưng chưa gửi được |
| **orders.operation.completed** | Một business operation được xác nhận hoàn tất | Mỗi lần handler được gọi hoặc mỗi HTTP retry |

**Vì sao phân biệt attempt và operation?** Nếu broker giao lại message ba lần và mỗi delivery retry handler hai lần, có thể có nhiều **handler failure events** cho **một** business operation. Dashboard không được gọi handler attempts là “số đơn hàng lỗi” mà không có dedup.

### Tránh tăng Counter ở cả catch và errorChannel cho cùng lỗi

~~~text
Handler catch exception:
    orders.handler.failed += 1

ErrorChannel consumer nhận lại cùng exception:
    orders.handler.failed += 1  <-- Đếm hai lần nếu đây cùng một sự kiện.
~~~

Thay vào đó:

- Đặt **handler.failed** tại một điểm duy nhất, ví dụ interceptor/handler entry.
- Đặt **error.message.received** tại errorChannel nếu bạn muốn đo số ErrorMessage được giao cho error flow (đó là **đơn vị khác**).
- Đặt **recovery.completed** sau khi business recovery thực sự hoàn tất.
- Đặt **operation.failed** khi nghiệp vụ chuyển sang trạng thái thất bại cuối, nếu có nguồn sự thật bền vững.

## 5. DistributionSummary: đo kích thước và phân phối

**DistributionSummary** phù hợp với các giá trị **không phải thời lượng**, ví dụ số byte của payload hoặc số bản ghi trong batch.

~~~java
import io.micrometer.core.instrument.DistributionSummary;
import io.micrometer.core.instrument.MeterRegistry;

class PayloadSizeMetrics {
    private final DistributionSummary bytes;
    private final DistributionSummary batchRecords;

    PayloadSizeMetrics(MeterRegistry registry) {
        bytes = DistributionSummary.builder("orders.payload.size")
                .description("Serialized payload sizes")
                .baseUnit("bytes")
                .tag("flow", "order-import")
                .publishPercentileHistogram()
                .register(registry);

        batchRecords = DistributionSummary.builder("orders.batch.records")
                .description("Number of records in each submitted batch")
                .tag("flow", "order-import")
                .register(registry);
    }

    void onPayload(byte[] serializedPayload) {
        bytes.record(serializedPayload.length);
    }

    void onBatch(int recordCount) {
        if (recordCount < 0) {
            throw new IllegalArgumentException("Negative batch size");
        }
        batchRecords.record(recordCount);
    }
}
~~~

**Điều được đo phải định nghĩa rõ:**

- **serializedPayload.length** là số byte của **biểu diễn đã serialize**, không phải chính xác lượng RAM mà Java object chiếm.
- Nếu đọc JSON String rồi dùng **length()**, đó là số đơn vị ký tự UTF-16, **không phải số byte UTF-8**. Muốn số byte, đo sau khi encode hoặc từ byte[] thực.
- Nếu message được nén, kích thước **trước nén** và **trên wire sau nén** khác nhau; đặt tên meter/tag theo ranh giới đo.
- DistributionSummary ghi một quan sát **mỗi batch** trong ví dụ; nếu cùng batch bị retry, bạn sẽ ghi nhiều sample. Đó là distribution của **attempted batches**, không tự là distribution của **business batches duy nhất**.

### Khi nào dùng Gauge thay vì DistributionSummary?

~~~text
Group A vừa nhận 10 message, rồi release và rỗng.
Group B có 200 message đang chờ.
~~~

- Muốn biết **kích thước của group tại thời điểm release**: ghi **DistributionSummary** một sample bằng 10 và một sample bằng 200.
- Muốn biết **số nhóm đang chờ ngay bây giờ** hoặc **tổng queued messages ngay bây giờ**: dùng **Gauge**.
- Muốn biết tổng số message **từng được nhận** từ lúc process start: dùng **Counter**.

Không tạo một Gauge mới cho mỗi groupId; số nhóm có thể tăng vô hạn. Thay vào đó, lấy snapshot/tổng hợp từ store và chỉ phát metric theo flow/status được kiểm soát.

## 6. Tên metric, tags và giới hạn cardinality

Một metric được đăng ký như:

~~~text
name: orders.handler.duration
tags:
    application = order-service
    flow = order-import
    handler = order-handler
    outcome = success
~~~

Các tag có thể tạo nhiều chuỗi meter độc lập. Nếu:

~~~text
4 flows × 8 handlers × 3 outcomes × 5 instances = 480 time series
~~~

thì khi xuất histogram, **mỗi time series còn có nhiều bucket**. Hệ số này tăng rất nhanh. Cần tránh tag có **giá trị không giới hạn**:

| Tag nên cân nhắc | Cardinality | Lý do |
| --- | --- | --- |
| flow, endpoint (danh sách hữu hạn) | Thấp đến trung bình | Xác định vị trí lỗi |
| outcome=success/error/timeout | Thấp | Phân loại kết quả |
| errorType=validation/network/db/unknown | Thấp nếu phân nhóm cố định | Chẩn đoán lỗi |
| transport=kafka/http/file | Thấp | Phân biệt adapter |
| application, environment, instance | Theo hạ tầng | Lọc theo service/replica; instance count phải được tính |
| **orderId/paymentId/eventId** | Rất cao | Không dùng làm meter tag |
| **messageId/correlationId/traceId** | Rất cao | Đặt trong log/trace |
| **exception message, URI đầy đủ, SQL text** | Không giới hạn, có thể nhạy cảm | Dùng error category và route template |

**Đặt tên/đơn vị:** Micrometer có thể chuyển đổi tên khi xuất sang backend. Ví dụ Timer **orders.handler.duration** có thể thành chuỗi Prometheus với hậu tố **_seconds**, còn DistributionSummary có **baseUnit("bytes")** có thể mang hậu tố tương ứng. Không hardcode một quy ước hậu tố rồi mặc định nó giống trên mọi registry.

## 7. Spring Integration có những meter tự động nào?

Spring Integration có tích hợp Micrometer/management cho các thành phần như channel và endpoint, tùy phiên bản, dependency và cấu hình quản trị. Một số đường còn có hỗ trợ **Micrometer Observation**, kết hợp metric và tracing.

**Không mặc định rằng mỗi endpoint luôn tự xuất một bộ metric giống nhau.** Tên meter, tag, cơ chế capture và thời điểm instrument phụ thuộc:

1. Phiên bản **Spring Integration**, Spring Framework, Spring Boot và Micrometer.
2. Có **MeterRegistry**/metrics captor hoặc observation infrastructure phù hợp trong context không.
3. Endpoint/channel có bật management/observation theo cấu hình không.
4. Endpoint thực tế là **message-driven**, **polling**, **gateway** hay channel async.
5. Registry xuất sang backend nào và cấu hình filter/rename như thế nào.

### Quy trình xác minh metrics thực tế

- Bật quan sát tối thiểu trong môi trường dev/test.
- Gửi một message thành công và một message có lỗi có kiểm soát.
- Xem danh sách meter trong **MeterRegistry** hoặc endpoint Actuator **/actuator/metrics** khi được bật.
- Đối chiếu **tên, tag, meter type, count và timing scope** với hành vi thật.
- Kiểm tra một send qua DirectChannel, một send qua ExecutorChannel, một poll không nhận được message và một handler thất bại; các đường có thể cho quan sát khác nhau.

**Tránh xếp chồng tự động và thủ công:** Nếu framework đã có Timer cho cùng một **handler execution**, việc thêm Timer do ứng dụng tự ghi có thể hữu ích cho phân tích nghiệp vụ nhưng phải đặt tên/định nghĩa khác để không khiến dashboard cộng hai metric và xem chúng là số request tăng gấp đôi.

## 8. Spring Boot Actuator và backend Prometheus

Một ứng dụng Spring Boot dùng Micrometer có thể cung cấp endpoint metrics thông qua **spring-boot-starter-actuator**. Với Prometheus, thường cần dependency registry phù hợp, ví dụ **micrometer-registry-prometheus**; tên artifact và auto-configuration nên được đối chiếu với phiên bản project.

Ví dụ cấu hình:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,metrics,prometheus
  metrics:
    tags:
      application: order-service
      environment: staging
~~~

**Chú ý bảo mật:** Đây là ví dụ cho môi trường có management endpoint được bảo vệ. Không công khai toàn bộ **/actuator/metrics** hoặc **/actuator/prometheus** trên Internet. Cấu hình authentication, network policy, authorization và scrape access theo tiêu chuẩn vận hành.

### Chênh lệch giữa metrics trong registry và dữ liệu được scrape

**Timer** đăng ký trong JVM có thể cung cấp:

~~~text
name = orders.handler.duration
count = 20
totalTime = 4.7 seconds
max = 0.63 seconds
~~~

Khi export qua Prometheus, timer dạng histogram thường trở thành những metric gần với:

~~~text
orders_handler_duration_seconds_count{flow="order-import",outcome="success"} ...
orders_handler_duration_seconds_sum{flow="order-import",outcome="success"} ...
orders_handler_duration_seconds_bucket{flow="order-import",outcome="success",le="0.5"} ...
~~~

Các chuỗi **_bucket** chỉ xuất hiện khi histogram/SLO buckets được cấu hình phù hợp. Cách đặt tên chính xác còn phụ thuộc version/registry; hãy kiểm tra endpoint scrape thực tế thay vì giả định mọi meter xuất đủ count, sum, max, bucket, percentile theo cùng cách.

### Khác biệt giữa Counter và rate

Counter thường bắt đầu lại từ 0 khi process restart. Dashboard nên xem **tốc độ gia tăng theo khoảng thời gian** khi phân tích hiện tượng gần đây.

Ví dụ PromQL minh họa nếu meter **orders.duplicate.suppressed** được export thành Counter phù hợp:

~~~promql
sum(rate(orders_duplicate_suppressed_total[5m]))
~~~

Đây là **số duplicate bị chặn trung bình mỗi giây** trong 5 phút, không phải tổng duplicate kể từ đầu đời hệ thống. Dùng **increase(metric[...])** khi muốn ước lượng số sự kiện tăng trong một khoảng thời gian:

~~~promql
sum(increase(orders_duplicate_suppressed_total[1h]))
~~~

**Không dùng trực tiếp raw Counter chia cho số giây hệ thống uptime** để suy ra tốc độ hiện tại: nhiều process restart và thay đổi số replica có thể làm kết quả sai.

## 9. Histogram, percentile và phân phối latency

**Thời gian trung bình** không mô tả được tail latency. Ví dụ 99 request chạy 50 ms, một request mất 5 giây. Trung bình vẫn tương đối thấp so với **P99**, nhưng 1% người dùng có trải nghiệm rất chậm.

Micrometer hỗ trợ cấu hình percentile histogram/SLO buckets tùy meter/backend:

~~~java
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import java.time.Duration;

class OrderTimerConfiguration {
    private final Timer orderHandlerTimer;

    OrderTimerConfiguration(MeterRegistry registry) {
        this.orderHandlerTimer =
                Timer.builder("orders.handler.stage.duration")
                        .description("Order processing stage duration")
                        .tag("flow", "order-import")
                        .publishPercentileHistogram()
                        .serviceLevelObjectives(
                                Duration.ofMillis(100),
                                Duration.ofMillis(500),
                                Duration.ofSeconds(2))
                        .register(registry);
    }

    void record(Duration duration) {
        orderHandlerTimer.record(duration);
    }
}
~~~

Ví dụ trên minh họa một **Timer cố định** cho một stage. Nếu muốn tag outcome sau khi biết kết quả, có thể xây Timer theo outcome như ở phần 3, nhưng phải **giữ cùng chính sách histogram và service level objectives** cho mọi outcome để dashboard so sánh nhất quán.

### P50/P95/P99 có nghĩa gì?

| Quantile | Cách đọc |
| --- | --- |
| **P50** | Khoảng một nửa các quan sát nhỏ hơn hoặc bằng mức này |
| **P95** | Khoảng 95% các quan sát nằm dưới hoặc bằng mức này |
| **P99** | Khoảng 99% các quan sát nằm dưới hoặc bằng mức này |

P99 **không phải** thời gian lớn nhất; các request chậm nhất vẫn có thể lớn hơn P99 đáng kể. Với lưu lượng ít, percentile có thể không ổn định do số sample thấp.

### Percentile tính trong instance và histogram tổng hợp

**Client-side percentiles** được Micrometer tính sẵn theo phân phối của từng registry/instance, thường **không thể cộng/trung bình** một cách chính xác để tạo percentile chung cho cluster.

**Histogram buckets** phù hợp với backend như Prometheus để tính quantile trên dữ liệu đã **tổng hợp qua instance**. Ví dụ với timer tùy biến ở trên:

~~~promql
histogram_quantile(
  0.95,
  sum by (le) (
    rate(orders_handler_stage_duration_seconds_bucket[5m])
  )
)
~~~

**Điều kiện:** Meter phải export bucket với tên và label phù hợp. Trong ứng dụng nhiều flow/handler, thường cần lọc theo **flow** hoặc **endpoint** trước khi tổng hợp. Nếu gộp các handler có đặc tính rất khác nhau vào một histogram, P95 tổng có thể che giấu bottleneck.

### Tỷ lệ request trên một ngưỡng

Nếu Timer có bucket cho **2 giây**, tỷ lệ số quan sát **vượt 2 giây** có thể ước tính qua count và bucket, với cùng filter/aggregation:

~~~promql
(
  sum(rate(orders_handler_stage_duration_seconds_count[5m]))
  -
  sum(rate(orders_handler_stage_duration_seconds_bucket{le="2.0"}[5m]))
)
/
sum(rate(orders_handler_stage_duration_seconds_count[5m]))
~~~

Phải kiểm tra label **le** thực tế; backend có thể thể hiện giá trị bucket theo dạng khác, chẳng hạn **"2"**. Khi mẫu số bằng 0 (không có traffic), dashboard/alert cần xử lý kết quả trống/không xác định thay vì báo là 0% lỗi chắc chắn.

### DistributionSummary cũng có histogram

Nếu muốn biết **P95 kích thước payload** hoặc tỷ lệ payload lớn hơn ngưỡng, có thể cấu hình histogram hoặc SLO buckets trên DistributionSummary. Nhưng chi phí bộ nhớ/export tăng theo số meter/tag. Chỉ bật histogram cho các metric thực sự hỗ trợ một quyết định về SLO/capacity.

## 10. Đo latency chính xác khi flow có DirectChannel và ExecutorChannel

Trường hợp **DirectChannel**:

~~~text
Producer thread
  send(message)
    → DirectChannel
       → Handler (150 ms)
  send returns (sau khoảng 150 ms + overhead)
~~~

Vì handler đồng bộ trong thread sender, một Timer quanh send có thể **bao gồm** thời gian handler. Nhưng với **ExecutorChannel**:

~~~text
Producer thread                   Worker thread
  send(message)
    → ExecutorChannel
       → enqueue task -------------→ wait in queue (500 ms)
  send returns (5 ms)              → handler (150 ms)
                                   → DB / HTTP
~~~

Một Timer quanh **send()** lúc này có thể chỉ thấy **5 ms**, trong khi người dùng chịu **655 ms** trước khi business step xong. Nếu dashboard nhầm send latency với **end-to-end latency**, bạn sẽ tưởng hệ thống nhanh dù executor backlog tăng.

### Ba phép đo nên tách

1. **dispatch duration:** từ trước send() đến send() trả kết quả.
2. **queue wait:** từ khi message thực sự được enqueue đến khi worker bắt đầu xử lý.
3. **processing duration:** từ lúc worker bắt đầu handler đến khi handler hoàn tất/throw.

Khi nghiệp vụ cần một SLA từ nguồn đến đích, đo thêm **business end-to-end duration** bằng một mốc bắt đầu đáng tin cậy và trạng thái kết thúc. Nhiều message có thể đại diện cho một operation, nên cần tránh ghi completion Timer nhiều lần do retry/replay.

### Đo queue wait bằng thời điểm enqueue

Một cách minh họa là gắn metadata thời điểm enqueue:

~~~java
import java.time.Duration;
import java.time.Instant;
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import org.springframework.messaging.Message;

class QueueWaitObserver {
    private final MeterRegistry registry;

    QueueWaitObserver(MeterRegistry registry) {
        this.registry = registry;
    }

    void observeWhenDequeued(Message<?> message) {
        Object header = message.getHeaders().get("enqueuedAtEpochMillis");
        if (!(header instanceof Long started)) {
            return; // Thiếu metadata: không ghi sample giả.
        }

        long elapsed = Instant.now().toEpochMilli() - started;
        if (elapsed < 0) {
            // Clock thay đổi: không coi giá trị âm là latency hợp lệ.
            return;
        }

        Timer.builder("orders.queue.wait.duration")
                .tag("flow", "order-import")
                .register(registry)
                .record(Duration.ofMillis(elapsed));
    }
}
~~~

**Hạn chế quan trọng:**

- Phải gắn timestamp **tại thời điểm thực sự enqueue**; gắn từ producer trước nhiều transformer sẽ đo thêm các bước khác.
- Wall clock **có thể thay đổi**, và clock giữa các host có thể lệch. Nếu đo một đoạn trong **cùng process**, nên ưu tiên monotonic clock, chẳng hạn **System.nanoTime()**; không dùng nanoTime value để so sánh giữa JVM hoặc sau restart.
- Nếu message qua broker/persistent store và restart, timestamp epoch có thể được giữ để đo thời gian chờ xuyên process, nhưng cần clock synchronization, format và quản lý schema.
- Không thêm timestamp của từng message vào **metric tag**. Nó là dữ liệu để tính một duration, không phải chiều phân nhóm.

## 11. Poller, consumer và MessageStore: timer nào giúp ích?

Một polling endpoint thường có các giai đoạn:

~~~text
Scheduled poll begins
  → MessageSource.receive()
  → message có thể null hoặc không
  → dispatch / handle
  → commit / rollback
Poll finishes
~~~

**Các câu hỏi khác nhau cần metric khác nhau:**

| Phép đo | Loại | Tín hiệu |
| --- | --- | --- |
| Số lần poll | Counter | Poller có chạy đúng lịch không |
| Số poll rỗng | Counter | Poll liên tục nhưng không có dữ liệu? |
| Thời gian receive() | Timer | Nguồn DB/file/broker chậm hay không |
| Thời gian xử lý một lượt poll | Timer | Một lần poll chiếm thread bao lâu |
| Messages per poll | DistributionSummary | Batch lớn/nhỏ, sự thay đổi tải |
| Thời gian chờ trong MessageStore | Timer/Gauge phù hợp | Backlog già đi hay tăng |
| Số message đang chờ | Gauge | Backpressure |
| Số commit/rollback | Counter theo outcome | Transaction fail rate |

Một poll rỗng **không phải** một message bị lỗi. Nếu đếm toàn bộ lần poll vào **orders.ingress.received**, dashboard sẽ báo traffic không có thật.

### Timer quanh receive() khác Timer quanh toàn poll

Nếu receive() trả trong 10 ms nhưng handler mất 900 ms, **poll total duration** có thể gần 910 ms trong đường xử lý đồng bộ; **receive duration** chỉ nên ghi 10 ms. Tách hai chỉ số giúp phân biệt bottleneck do nguồn dữ liệu với bottleneck ở xử lý.

Với poller có **maxMessagesPerPoll > 1**, một lượt poll có thể xử lý nhiều message. Số lần poll **không đồng nhất** với số delivery; khi so sánh throughput phải định nghĩa mẫu số đúng.

### MessageGroupStore và aggregator

Các group của aggregator/resequencer có thể chờ lâu do thiếu phần, sai correlation hoặc lỗi store. Nên dùng:

- **Gauge** số group đang incomplete và kích thước backlog (nếu store hỗ trợ truy xuất hiệu quả).
- **DistributionSummary** cho kích thước group **tại lúc release**.
- **Timer** từ khi group bắt đầu tới khi release, với điều kiện timestamp bền vững và đồng hồ tin cậy.
- **Counter** cho normal releases, partial releases, timeouts, discarded late messages và failures.

Một completed group giữ metadata có thể có size 0; không nên coi size=0 nghĩa là không có state. Đồng thời, đừng mỗi lần scrape metrics mà tải **toàn bộ payload của mọi MessageGroup**; có thể dùng metadata/stored aggregate cho phép đo nhẹ hơn.

## 12. Retry, errorChannel và transaction: số đo rất dễ bị thổi phồng

Giả sử:

~~~text
Broker: 2 deliveries
RequestHandlerRetryAdvice: 3 attempts mỗi delivery
HTTP client: 2 attempts mỗi handler call
~~~

Trong tình huống lỗi toàn bộ, lý thuyết có thể phát sinh **2 × 3 × 2 = 12 HTTP calls** cho **một business operation**.

Các meter phải đặt đúng tên theo đơn vị:

| Metric | Nếu ghi tại đúng điểm | Số tối đa trong ví dụ |
| --- | --- | ---: |
| Broker delivery Counter | Consumer nhận một delivery | 2 |
| Handler attempt Timer count | Mỗi lần thực thi handler | 6 |
| HTTP client attempt Timer count | Mỗi lần HTTP call | 12 |
| Business operation Counter | Một operation được xác nhận hoàn tất | 0 hoặc 1 tùy kết quả nghiệp vụ |

Không có nghĩa mọi flow tự động phát những con số trên: kết quả tùy adapter, cách thực thi retry và điểm instrument. Bảng chỉ minh họa việc **cùng một operation có thể có nhiều sự kiện kỹ thuật**.

### Gắn outcome khi lỗi propagate

Trong handler:

- Đo Timer cả khi success/error, dùng **try/catch/finally** phù hợp.
- Giữ exception truyền ra ngoài nếu transaction/error handling cần xử lý; không catch rồi return success để chỉ đẹp metric.
- Dùng tag **outcome=error** và Counter theo **error category hữu hạn**; tránh tag toàn bộ exception stack trace.
- Tách số **attempt thất bại** khỏi số **business operation thất bại cuối cùng**.

Trong **errorChannel**:

- Đếm **ErrorMessage delivered**, không mặc định đó là toàn bộ exception xảy ra ở mọi tầng.
- Truy originalMessage hoặc MessagingException.failedMessage khi có để ghi log với correlationId/eventId.
- Không mặc định ErrorMessage chứa business correlation ở headers ngoài cùng.
- Khi recovery chuyển sang DLQ, chỉ tăng **dlq.published** sau khi chuyển giao được xác nhận theo hợp đồng.

### Metric không được tự coi transaction đã commit

Nếu handler tăng **orders.operation.completed** trước DB commit, rồi transaction rollback, Counter có thể vẫn tăng. Micrometer Counter **không nằm trong DB transaction** và không tự rollback theo transaction.

Để đo business completion chính xác hơn:

- Định nghĩa nguồn sự thật là **DB state**, event outbox đã commit hoặc hệ thống nghiệp vụ được xác nhận.
- Đặt Counter ở điểm **đã xác nhận kết quả**, không ở điểm mới bắt đầu update.
- Với callback **afterCommit**, nhớ có crash window sau commit trước callback: một event đo có thể bị bỏ lỡ; dashboard vận hành không nên dùng Counter trong RAM như nguồn kiểm toán duy nhất.
- Dùng **query từ dữ liệu bền vững** hoặc reconciliation nếu số hoàn tất phải chính xác phục vụ tài chính/đối soát.

**Metrics là quan sát best-effort**, không thay thế sổ cái giao dịch hay message delivery guarantee.

## 13. Kiểm thử Timer, Counter và DistributionSummary bằng SimpleMeterRegistry

**SimpleMeterRegistry** cho phép test meter ngay trong JVM mà không cần Prometheus server. Kiểm tra nên tập trung vào:

- Meter **được đăng ký đúng tên và tag**.
- Một lần gọi success/error tạo **đúng một sample** theo đơn vị đo.
- Timer ghi nhận thời lượng **không âm** và có count đúng; không dùng test yêu cầu duration chính xác từng nanosecond.
- Counter chỉ tăng tại đúng sự kiện, không bị tăng hai lần khi retry/error flow.
- DistributionSummary ghi số lượng hợp lệ và đúng đơn vị byte/record.

### Unit test Timer quanh handler

Ví dụ JUnit 5 dưới đây áp dụng trực tiếp **InstrumentedOrderHandler** và **OrderProcessor** ở phần 3:

~~~java
import static org.junit.jupiter.api.Assertions.*;

import io.micrometer.core.instrument.Timer;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import org.junit.jupiter.api.Test;
import org.springframework.messaging.support.MessageBuilder;

class HandlerMetricsTest {

    @Test
    void successCreatesOneSuccessSample() {
        SimpleMeterRegistry registry = new SimpleMeterRegistry();
        try {
            OrderProcessor processor = order -> {
                // Giả lập thao tác thành công.
            };
            InstrumentedOrderHandler handler =
                    new InstrumentedOrderHandler(registry, processor);

            handler.handle(
                    MessageBuilder.withPayload(
                            new OrderCommand("O-42", 3)).build());

            Timer timer = registry.find("orders.handler.duration")
                    .tag("flow", "order-import")
                    .tag("handler", "order-handler")
                    .tag("outcome", "success")
                    .timer();

            assertNotNull(timer);
            assertEquals(1L, timer.count());
            assertTrue(timer.totalTime(
                    java.util.concurrent.TimeUnit.NANOSECONDS) >= 0);
        } finally {
            registry.close();
        }
    }

    @Test
    void failureIsTimedAndStillPropagates() {
        SimpleMeterRegistry registry = new SimpleMeterRegistry();
        try {
            OrderProcessor processor = order -> {
                throw new IllegalStateException("DB unavailable");
            };
            InstrumentedOrderHandler handler =
                    new InstrumentedOrderHandler(registry, processor);

            assertThrows(IllegalStateException.class, () ->
                    handler.handle(
                            MessageBuilder.withPayload(
                                    new OrderCommand("O-43", 2)).build()));

            Timer timer = registry.find("orders.handler.duration")
                    .tag("outcome", "error")
                    .timer();
            assertNotNull(timer);
            assertEquals(1L, timer.count());
        } finally {
            registry.close();
        }
    }
}
~~~

**Giới hạn của test:** Gọi thẳng handle(...) chỉ kiểm tra **metric ứng dụng tự ghi**. Nó **không** xác minh metric của framework sinh ra khi message đi qua DirectChannel, advice chain hay errorChannel. Để kiểm tra phần đó, cần tạo Spring Integration context thật và gửi message qua channel.

### Test Counter và DistributionSummary

~~~java
import static org.junit.jupiter.api.Assertions.*;

import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.DistributionSummary;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import org.junit.jupiter.api.Test;

class PayloadAndDuplicateMetricsTest {

    @Test
    void countsDuplicateAndRecordsPayloadBytes() {
        SimpleMeterRegistry registry = new SimpleMeterRegistry();
        try {
            DuplicateMeter duplicates = new DuplicateMeter(registry);
            PayloadSizeMetrics sizes = new PayloadSizeMetrics(registry);

            duplicates.duplicateWasSuppressed();
            duplicates.duplicateWasSuppressed();
            sizes.onPayload(new byte[128]);
            sizes.onPayload(new byte[512]);

            Counter counter = registry.find(
                    "orders.duplicate.suppressed").counter();
            DistributionSummary summary = registry.find(
                    "orders.payload.size").summary();

            assertNotNull(counter);
            assertEquals(2.0, counter.count());
            assertNotNull(summary);
            assertEquals(2L, summary.count());
            assertEquals(640.0, summary.totalAmount(), 0.0001);
        } finally {
            registry.close();
        }
    }
}
~~~

**Lưu ý:** Nếu backend export đơn vị hoặc đổi tên metric, tìm meter trong **SimpleMeterRegistry** bằng tên API đăng ký là một chuyện; tìm series của **Prometheus registry** có thể cần tên đã normalize và unit suffix.

### Test integration: DirectChannel và ExecutorChannel

Một bài test framework thực sự nên có hai nhánh:

**Nhánh A — DirectChannel**

1. Tạo IntegrationFlow với inbound DirectChannel và handler có Timer.
2. Gửi message và xác minh handler đã hoàn tất trước khi send trả.
3. Kiểm tra Timer handler count tăng đúng một với một delivery không retry.
4. Cho handler ném exception; xác minh error propagation và outcome=error.

**Nhánh B — ExecutorChannel**

1. Dùng executor có kích thước có kiểm soát và **CountDownLatch** giữ worker đang chạy.
2. Gửi message; ghi riêng dispatch duration quanh send().
3. Xếp thêm message để tạo queue wait.
4. Thả latch, đợi handler kết thúc theo điều kiện có timeout.
5. Xác minh **dispatch duration** nhỏ có thể đồng thời tồn tại **queue wait dài**, handler duration có sample riêng.
6. Kích hoạt exception ở worker, xác minh error flow có thể quan sát; không giả định exception sẽ ném về thread gửi.

Không dùng Thread.sleep cố định làm cơ sở duy nhất cho timing assertion. Các bài test về latency có thể thay đổi theo load của CI; dùng **latch, fake clock/clock abstraction hoặc điều kiện Awaitility** khi cần kiểm chứng chính xác logic.

## 14. Annotation @Timed, @Observed và nguy cơ đo trùng

Ngoài việc tạo meter thủ công, Micrometer và Spring ecosystem có các annotation/cơ chế quan sát như **@Timed** và **@Observed**.

**Không tự giả định annotation nào cũng hoạt động ngay sau khi thêm vào method.** Chúng cần infrastructure phù hợp (ví dụ Aspect/observation handler hoặc auto-configuration theo phiên bản). Đặc biệt:

- Một annotation trên **private method** hoặc method được gọi bằng **self-invocation** có thể không được proxy/aspect nhìn thấy nếu giải pháp dựa trên AOP.
- Một endpoint Spring Integration có thể đã được management/observation instrumentation; cộng thêm annotation và Timer thủ công có thể đo **cùng đoạn thực thi nhiều lần**.
- Khi **@Observed** sinh cả observation/tracing và metrics, cần tránh cấu hình thêm một Timer khác cùng ý nghĩa nhưng tag khác không có chủ đích.
- Các annotation thường đo **method execution**; với ExecutorChannel, không tự đo toàn bộ queue wait hoặc thời gian end-to-end của workflow.

### Chọn giữa instrumentation tự động và thủ công

| Yêu cầu | Phù hợp |
| --- | --- |
| Nắm tổng quan channel/handler invocation | Built-in Spring Integration metrics/observation nếu đã cấu hình |
| Đo một stage nghiệp vụ cụ thể | Timer thủ công hoặc annotation được hỗ trợ |
| Gắn outcome sau khi biết kết quả xử lý | Timer.Sample với tag outcome |
| Đếm duplicate được chặn ở DB | Counter tại điểm xác minh dedup |
| Đo số byte payload đã serialize | DistributionSummary tại ranh giới serialize |
| End-to-end SLA qua nhiều message/restart | Timestamp/business state bền vững + instrumentation hoàn tất |
| Điều tra một paymentId cụ thể | Trace/log với business ID an toàn; không phải meter tag |

**Cách kiểm tra tránh trùng:** Vẽ sơ đồ mọi nơi có meter, đặt tên **đơn vị đo** cho mỗi meter và dùng một bộ test gửi N message để đối chiếu count. Nếu N=10 nhưng dashboard cộng hai timer count khác nghĩa để báo 20 requests, logic dashboard cần chỉnh.

## 15. Dashboard mẫu cho Spring Integration Runtime

Một dashboard hữu ích nên tách **traffic**, **latency**, **errors** và **saturation**, đồng thời có thông tin health/lifecycle của endpoint.

| Khu vực | Metric/đồ thị | Câu hỏi |
| --- | --- | --- |
| **Traffic** | Ingress deliveries per second | Nguồn có gửi đều hay bị dừng? |
| **Handler latency** | Timer P50/P95/P99 và count | Handler nào chậm? Có đủ sample không? |
| **Queue wait** | Timer queue wait P95 | Backlog khiến message chờ lâu không? |
| **Errors** | Rate handler errors, error messages, DLQ | Lỗi phát sinh ở đâu, recovery có hoàn tất không? |
| **Retries** | Retry attempts per operation (ước tính từ nguồn nghiệp vụ) | Retry có khuếch đại tải không? |
| **Payload sizes** | DistributionSummary size P95 và largest | Có payload lớn bất thường? |
| **Saturation** | Queue depth, executor active/queue/rejections | Có thiếu worker/DB connection? |
| **Persistence** | MessageStore read/write latency, pending groups | Store có thành bottleneck không? |
| **Correlation** | Incomplete groups, expiration, discard | Có message thiếu hoặc group release trễ? |
| **Lifecycle** | isRunning, desired vs actual, poll rate | Flow bị stop, pause hay có sự cố? |

### PromQL mẫu: handler attempt throughput

Nếu Timer **orders.handler.duration** được export như một Prometheus histogram/timer count:

~~~promql
sum by (outcome) (
  rate(orders_handler_duration_seconds_count[5m])
)
~~~

Đây là **số handler attempts mỗi giây**, phân theo outcome. Nó không phải trực tiếp số business operations.

### PromQL mẫu: average handler duration

~~~promql
sum(
  rate(orders_handler_duration_seconds_sum[5m])
)
/
sum(
  rate(orders_handler_duration_seconds_count[5m])
)
~~~

Kết quả thường có đơn vị **giây** với Timer export theo Prometheus conventions; kiểm tra series name và unit thực tế.

### PromQL mẫu: tỷ lệ error của handler attempts

~~~promql
sum(
  rate(orders_handler_duration_seconds_count{outcome="error"}[5m])
)
/
sum(
  rate(orders_handler_duration_seconds_count[5m])
)
~~~

**Đây là error rate trên handler attempts**, không phải error rate trên mỗi đơn hàng duy nhất. Với retry, lỗi attempt đầu rồi success attempt sau vẫn góp vào tử số; điều đó hữu ích để phát hiện downstream bất ổn nhưng không đồng nghĩa đơn hàng cuối cùng thất bại.

**Mẫu số bằng 0:** Khi flow bị stop hoặc không có traffic, biểu thức có thể không có giá trị; đừng thay thành “100% thành công” mà không thông báo trạng thái **no data**.

### Khi cần cảnh báo

Tránh chỉ cảnh báo “Counter tổng lỗi > 100”, vì tổng tích lũy sẽ tiếp tục tăng theo uptime. Nên dùng các điều kiện:

- Error **rate** hoặc tăng bất thường so với baseline.
- P95 latency vượt SLO **với lưu lượng đủ để percentile có ý nghĩa**.
- Queue depth hoặc tuổi message tăng liên tục trong nhiều chu kỳ scrape.
- Executor active gần capacity, rejection tăng, handler throughput giảm.
- DLQ/persistent retry pending age vượt thời hạn phục hồi.
- Incomplete MessageGroup cũ quá SLA hoặc duplicate business effects > 0.
- Desired state RUNNING nhưng endpoint actual STOPPED hoặc poll count không đổi.

Khi hệ thống restart, một số Counter reset và gauges mất/đổi giá trị. Dashboard phải xem **instance lifecycle** và **rate** thay vì so trực tiếp total của hai lần khởi động JVM.

## 16. Performance: meter cũng có chi phí

Instrumentation tốt không nên trở thành bottleneck mới:

- **Cardinality:** Mỗi tổ hợp tag là meter độc lập. Dynamic orderId tạo số meter gần với số message, gây tốn RAM và làm backend chậm.
- **Histogram:** Nhiều bucket nhân với số tag khiến memory/export cost tăng. Chỉ bật cho vài latency/size quan trọng.
- **Hot path:** Không serialize payload chỉ để đo kích thước nếu bước xử lý chính chưa cần serialize; có thể làm tăng CPU đáng kể.
- **Blocking metrics:** Ghi metric không nên gọi network đồng bộ tới monitoring backend trên thread handler; dùng registry/exporter đúng thiết kế.
- **Sampling:** Metrics thường tổng hợp gần như mọi lần quan sát ở client; tracing có thể sampling. Đừng mặc định số traces bằng Counter.
- **Expensive Gauge:** Gauge chạy query lớn hoặc scan toàn bộ MessageStore mỗi lần scrape có thể gây load hoặc lock contention.
- **Exemplars:** Nếu backend hỗ trợ gắn trace exemplar vào histogram, dùng capability được cấu hình đúng, không biến traceId thành tag cố định trên mọi sample.

### Metadata và data privacy

Metric tags phải là thông tin có thể đưa lên hệ thống monitoring với quyền truy cập thích hợp. Không đưa số tài khoản, email, tên khách hàng, raw exception message hoặc payload vào metric.

Đối với trace/log chứa business key:

- Dùng masking/hash/tokenization khi cần.
- Thiết lập retention và access control.
- Tránh lộ payload ở error channel hoặc exporter.
- Tránh tạo high-cardinality metrics qua các biến từ header message không được validate.

## 17. Kịch bản chẩn đoán: flow chậm dù Timer handler vẫn tốt

Giả sử dashboard cho biết:

~~~text
Ingress = 1,500 messages/min
Handler P95 = 120 ms
Queue wait P95 = 15 s
Queue depth = 42,000 messages
Executor active = max workers
Error rate = 0.5%
~~~

**Kết luận phù hợp:** Handler có thể chạy nhanh **khi đã vào worker**, nhưng phần lớn độ trễ đến từ **queue wait/saturation**. Tăng timeout của gateway không sửa nguyên nhân. Cần kiểm tra tốc độ nhận/tốc độ xử lý, số consumer, DB capacity, contention, executor pool và backpressure.

Một kịch bản khác:

~~~text
Ingress = 200 operations/min
Handler attempts = 850/min
HTTP calls = 1,700/min
Handler P95 = 2.5 s
HTTP timeout count tăng
~~~

Tỷ lệ attempts/operations tăng gợi ý **retry amplification**. Không nên nhân thêm worker ngay khi downstream đã quá tải. Kiểm tra retry owner, max attempts, deadline, backoff/jitter, circuit breaker và idempotency.

Một kịch bản khác:

~~~text
Aggregator incomplete groups = 12,500
Incoming message rate bình thường
Release rate giảm gần 0
MessageGroupStore read latency tăng
~~~

Điều tra correlation key, release condition, message đến thiếu/lệch thứ tự, persistent store/index, lock contention và group expiry. Đếm inbound messages không chứng minh group đã nhận đúng **các loại phần nghiệp vụ** mà nó cần.

## 18. Bài thực hành: instrument một flow nhập đơn hàng

**Đề bài:** Flow sau có hai replica và nhận đơn qua broker:

~~~text
Broker inbound adapter
   → ordersIngress
   → QueueChannel backed by persistent MessageStore
   → polling consumer
   → OrderHandler (DB + HTTP)
   → outbound event
   ↘ errorChannel / retry / DLQ
~~~

Yêu cầu quan sát:

1. Thông lượng **deliveries** và số **business operations completed** phải tách biệt.
2. Có Timer cho **handler attempt**, **queue wait** và **outbound HTTP attempt**.
3. Counter cho **retry attempts**, **duplicate safely suppressed**, **DLQ published** và **handler failed**.
4. DistributionSummary cho **serialized payload bytes** và **batch records**.
5. Dashboard hiển thị **P95 queue wait**, **P95 handler**, error rate, backlog, throughput và trạng thái endpoint.
6. Không có metric tag chứa orderId, eventId, correlationId hoặc traceId.
7. Test retry một operation ba lần không bị coi là ba đơn hàng hoàn tất.
8. Sau restart, Counter có thể reset nhưng DB/outbox vẫn là nguồn sự thật về business completion.

### Hướng giải

**Bước 1 — Vẽ các ranh giới.** Xác định thời điểm thật sự enqueue/dequeue, handler begin/end, DB commit, HTTP request begin/end và business completion.

**Bước 2 — Đặt tên meter.** Ví dụ orders.delivery.received, orders.queue.wait.duration, orders.handler.duration, orders.http.duration, orders.payload.size, orders.retry.attempted, orders.duplicate.suppressed.

**Bước 3 — Chọn tag.** flow, endpoint, outcome và errorType từ tập giá trị hữu hạn; application/environment ở common tags. Không thêm business IDs vào meter.

**Bước 4 — Instrument bằng Micrometer.** Dùng Timer.Sample quanh handler trong try/finally, Counter tại điểm sự kiện có nghĩa, DistributionSummary ở serializer/batch boundary, Gauge cho backlog.

**Bước 5 — Xác minh built-in metric.** Nếu Spring Integration management đã có send/receive/handler meter, không tạo dashboard đếm trùng hoặc gọi chúng là business operation count.

**Bước 6 — Kiểm thử.** Dùng SimpleMeterRegistry để xác minh count/tags; dùng IntegrationFlow thật với DirectChannel/ExecutorChannel để xác minh scope; dùng persistent store và broker test cho restart/redelivery.

**Bước 7 — Tạo dashboard/alert.** Dùng rate() cho Counter, histogram_quantile() cho histogram, Gauge cho backlog. Phân biệt **no traffic** với **healthy throughput**.

### Ma trận test khuyến nghị

| Ca | Đầu vào/tình huống | Assertion |
| --- | --- | --- |
| 1 | Handler thành công một lần | Timer outcome=success count=1 |
| 2 | Handler throw RuntimeException | Timer outcome=error count=1, exception vẫn propagate |
| 3 | Cùng eventId redeliver hai lần | Duplicate Counter tăng đúng 1 nếu lần hai bị chặn |
| 4 | Handler retry 3 attempts | Handler Timer count theo attempts; business completion không tăng 3 |
| 5 | Payload 128 và 512 bytes | Summary count=2, sum=640 bytes |
| 6 | Executor queue bị chặn bằng latch | Queue wait tăng, send duration không bị nhầm là end-to-end |
| 7 | Poll không có message | Poll Counter tăng, ingress delivery Counter không tăng |
| 8 | ErrorChannel xử lý cùng lỗi từ handler | Không double-count cùng metric handler.failed |
| 9 | Transaction rollback sau handler | Không coi business operation completed nếu DB chưa commit |
| 10 | Restart giữa delivery và ack | Meter mới có thể reset, idempotency/DB outcome vẫn đúng |
| 11 | 10.000 orderId khác nhau | Số series không tăng theo orderId |
| 12 | Group bị thiếu phần quá SLA | Incomplete/timeout/discard metric phản ánh đúng kết cục |

## 19. Checklist trước khi đưa vào production

- Đã phân biệt **Counter, Timer, DistributionSummary và Gauge** theo dữ liệu thật cần đo?
- Mỗi meter có định nghĩa **đơn vị và ranh giới sự kiện** rõ ràng?
- Timer handler có ghi cả **success và error** không?
- Có tách **dispatch/send**, **queue wait**, **handler processing** và **end-to-end SLA**?
- Khi qua ExecutorChannel, có tránh coi send latency là business latency không?
- Khi poller trả null, không tăng nhầm message delivery count?
- Retry metrics có phân biệt **delivery, handler attempt, external call và business operation**?
- Metric ở errorChannel có double-count lỗi đã ghi ở handler không?
- Counter business completion có được ghi **trước commit** gây sai khi rollback không?
- DistributionSummary có dùng **đúng số byte thực/đúng số record** thay vì nhầm String length?
- Tên metric, base unit và quy tắc export sang Prometheus đã được xác minh trong phiên bản hiện tại?
- Histogram/P95/P99 có thực sự bật, có đủ lưu lượng và không tăng cardinality quá lớn?
- Tags chỉ dùng tập giá trị hữu hạn, không chứa orderId/eventId/correlationId/traceId/exception message?
- Dashboard sử dụng **rate/increase** thích hợp khi Counter reset sau restart?
- Có **Gauge backlog** và chỉ số executor saturation, không chỉ dùng handler Timer?
- Built-in Spring Integration metrics/Observation và custom meters có tránh đo trùng không?
- Management endpoints có xác thực/giới hạn truy cập và không để lộ dữ liệu nhạy cảm?
- Có unit test SimpleMeterRegistry, integration test channel/poller/executor và test retry/restart?

## Kết luận

**Micrometer Timer, Counter và DistributionSummary** là ba công cụ quan sát khác nhau nhưng bổ sung lẫn nhau: **Timer** đo thời lượng, **Counter** đếm sự kiện, **DistributionSummary** đo phân phối giá trị như byte size hoặc batch size. Chọn sai loại meter hoặc đặt sai ranh giới sẽ tạo một dashboard có vẻ chính xác nhưng đánh lạc hướng điều tra.

Trong Spring Integration Runtime, phải xem metric theo **channel, endpoint, poller, consumer, executor, transaction, retry, message store, error flow và correlation**. Một Timer quanh send qua ExecutorChannel không đo phần queue wait; một handler Counter không cho biết số business operation duy nhất; một DB rollback không rollback Micrometer Counter. Vì vậy cần định nghĩa đơn vị đo, giới hạn cardinality, phối hợp logs/traces và đối chiếu các phép đo với trạng thái nghiệp vụ bền vững.

Khi được triển khai và kiểm thử đúng, ba loại meter này giúp phát hiện **backpressure, retry storm, latency tail, payload bất thường và lỗi phục hồi**, từ đó ra quyết định vận hành có bằng chứng thay vì dựa vào một vài log hoặc số liệu tổng mơ hồ.

## Tài liệu tham khảo

- [Micrometer Reference — Timers](https://docs.micrometer.io/micrometer/reference/concepts/timers.html)
- [Micrometer Reference — Counters](https://docs.micrometer.io/micrometer/reference/concepts/counters.html)
- [Micrometer Reference — Distribution Summaries](https://docs.micrometer.io/micrometer/reference/concepts/distribution-summaries.html)
- [Micrometer Reference — Histograms and Percentiles](https://docs.micrometer.io/micrometer/reference/concepts/histogram-quantiles.html)
- [Micrometer Reference — Meter Filters](https://docs.micrometer.io/micrometer/reference/concepts/meter-filters.html)
- [Spring Boot Reference — Metrics](https://docs.spring.io/spring-boot/reference/actuator/metrics.html)
- [Spring Integration Reference — Metrics and Management](https://docs.spring.io/spring-integration/reference/metrics.html)
- [Spring Integration Reference — Message Channels](https://docs.spring.io/spring-integration/reference/channel/implementations.html)
- [Spring Integration Reference — Polling Consumer](https://docs.spring.io/spring-integration/reference/endpoint/polling-consumer.html)
