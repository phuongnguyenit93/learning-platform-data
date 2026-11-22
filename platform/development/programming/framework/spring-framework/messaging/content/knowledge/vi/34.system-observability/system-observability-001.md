# Đo số lượng gửi nhận, thông lượng và thời gian xử lý

## Mục tiêu

Sau bài này, bạn có thể:

- Xác định chính xác một message được tính là gửi, nhận, xử lý thành công hay thất bại ở đâu trong lifecycle.
- Dùng Counter, Timer, Gauge và DistributionSummary của Micrometer đúng mục đích.
- Tính thông lượng message/giây và byte/giây từ counter tích lũy.
- Đo thời gian gửi, thời gian chờ trong hàng đợi, thời gian xử lý handler và độ trễ end-to-end.
- Đưa metrics và traces vào Spring Boot bằng Micrometer Observation.
- Nhận biết metrics có sẵn của Spring Integration và giới hạn của instrumentation mặc định.
- Thiết kế tag có cardinality thấp, tránh làm hệ thống metrics quá tải.
- Kiểm thử metrics để bảo đảm số liệu phản ánh đúng hành vi messaging.

Bài này thuộc chủ đề **Spring Framework - messaging**, nhánh **Quan sát hệ thống**. Mục tiêu là biến hoạt động gửi, nhận và xử lý message thành số liệu có định nghĩa rõ để theo dõi tải, phát hiện lỗi và tìm nguyên nhân chậm.

## 1. Xác định điều gì được đếm

Trước khi tạo metric, cần định nghĩa ranh giới của từng sự kiện. Trong một luồng messaging, một message có thể đi qua nhiều bước:

~~~text
Application creates message
        |
        v
Send attempt
        |
        v
Transport accepts / publish completes
        |
        v
Message is delivered to consumer
        |
        v
Handler starts
        |
        v
Handler succeeds or fails
        |
        v
Acknowledgement / reply / completion
~~~

Các bước này không đồng nghĩa. Ví dụ, một lời gọi send trả về thành công có thể chỉ có nghĩa là transport đã nhận dữ liệu vào buffer; nó không nhất thiết chứng minh broker đã lưu bền vững hoặc consumer đã xử lý xong.

Một bộ đếm hữu ích có thể phân biệt:

| Sự kiện | Ý nghĩa khi tăng counter |
|---|---|
| send attempt | Ứng dụng bắt đầu một lần gửi |
| send accepted | Transport/API xác nhận đã nhận thao tác gửi theo hợp đồng của nó |
| send failed | Lời gọi gửi thất bại hoặc bị từ chối |
| received | Message tới ranh giới consumer/application |
| processing started | Handler bắt đầu xử lý |
| processed | Handler hoàn tất thành công |
| processing failed | Handler kết thúc bằng lỗi |
| retried | Một lần thử lại được thực hiện |
| redelivered | Consumer nhận lại message đã được giao trước đó |
| dead-lettered | Message được chuyển sang luồng lỗi/DLQ |

Không phải hệ thống nào cũng cần tất cả counter. Chọn các sự kiện phục vụ câu hỏi vận hành cụ thể. Đặc biệt, phải phân biệt retry của producer với redelivery của broker và retry nội bộ của handler.

Một message có thể được gửi hai lần nhưng chỉ xử lý thành công một lần nhờ deduplication. Khi đó send count, receive count và processed count khác nhau; sự khác biệt này có thể là hành vi đúng chứ không nhất thiết là lỗi.

### 1.1. Định nghĩa ranh giới send và receive

Với một producer, hãy xác định send accepted có nghĩa là gì:

- API đã nhận request?
- Byte đã được ghi vào transport?
- Broker đã xác nhận publish?
- Message đã được lưu bền vững?

Với consumer, received có thể là lúc message được chuyển cho callback, lúc handler bắt đầu, hoặc lúc adapter hoàn tất decode. Chọn một ranh giới nhất quán và ghi rõ trong mô tả metric.

Với RSocket Request-Response, có thể đếm request gửi đi và response nhận về riêng. Với Fire-and-Forget, không có response nghiệp vụ để xác nhận xử lý ở phía server; không gọi publisher completion là bằng chứng rằng side effect phía server đã commit.

## 2. Counter, Timer, Gauge và DistributionSummary

Micrometer cung cấp các meter type khác nhau. Chọn sai loại sẽ khiến dashboard dễ hiểu nhầm.

| Meter | Dùng để đo | Ví dụ messaging |
|---|---|---|
| Counter | Số sự kiện tích lũy, chỉ tăng | Số lần gửi thành công, số message xử lý lỗi |
| Timer | Số lần thực hiện và thời gian của mỗi lần | Thời gian handler xử lý message |
| Gauge | Giá trị hiện tại có thể tăng/giảm | Queue depth, số request đang xử lý |
| DistributionSummary | Phân bố của một đại lượng không phải thời gian | Kích thước payload theo byte |
| LongTaskTimer | Tác vụ đang chạy lâu và thời gian hoạt động | Số flow/handler đang thực hiện kéo dài |

### 2.1. Counter

Counter là bộ đếm tích lũy. Nó tăng khi sự kiện xảy ra và không giảm trong vòng đời của process. Sau khi ứng dụng restart, giá trị trong process mới bắt đầu lại; backend monitoring cần xử lý counter reset.

Ví dụ:

- app.messaging.messages với tag direction=outbound và result=accepted.
- app.messaging.messages với tag direction=inbound và result=processed.
- app.messaging.errors với tag stage=handler.

Không dùng Counter để biểu diễn số message đang nằm trong queue. Giá trị đó có thể tăng và giảm, nên phải dùng Gauge hoặc metric queue do adapter cung cấp.

### 2.2. Timer

Timer đo thời gian của một thao tác và đồng thời ghi nhận số lần đo. Từ Timer có thể lấy count, total time, max và các thống kê phân phối tùy cấu hình registry.

Các timer nên có ranh giới rõ:

- messaging.send: thời gian API gửi/publish thực hiện.
- messaging.handler: thời gian handler xử lý.
- messaging.end.to.end: từ lúc publish đến khi consumer hoàn tất, nếu có timestamp và correlation phù hợp.
- messaging.queue.wait: thời gian từ lúc message được broker nhận tới lúc consumer bắt đầu xử lý, nếu transport cung cấp timestamp đáng tin cậy.

Đừng gộp mọi khoảng thời gian vào một timer duy nhất. Khi latency tăng, các timer riêng giúp xác định thời gian nằm ở producer, broker/queue hay consumer.

### 2.3. Gauge

Gauge đo một giá trị tại thời điểm quan sát:

- Số message đang chờ trong queue.
- Số handler đang chạy.
- Số request in-flight.
- Số slot còn trống trong worker pool.
- Số connection đang hoạt động.

Gauge không phải counter. Không cộng dồn giá trị gauge qua thời gian để tính tổng message. Với queue depth, giá trị cao kéo dài thường là dấu hiệu consumer xử lý chậm hơn tốc độ nhận hoặc consumer bị dừng.

### 2.4. DistributionSummary

DistributionSummary phù hợp với payload size, batch size hoặc số item trong một message. Ví dụ ghi nhận số byte của mỗi payload để xem median, p95 hoặc phân phối kích thước.

Nếu cần tổng byte gửi/nhận tích lũy, dùng Counter riêng cho tổng byte. Nếu cần phân phối kích thước từng message, dùng DistributionSummary. Hai metric trả lời hai câu hỏi khác nhau.

## 3. Tính thông lượng message và byte

**Throughput** là lượng công việc hoàn tất trong một đơn vị thời gian. Với messaging, nên phân biệt:

- Send throughput: số message được chấp nhận gửi mỗi giây.
- Receive throughput: số message tới consumer mỗi giây.
- Processing throughput: số message handler hoàn tất thành công mỗi giây.
- Failure rate: số lần xử lý lỗi mỗi giây hoặc tỷ lệ lỗi.
- Byte throughput: số byte được gửi/nhận mỗi giây.

Nếu counter ghi nhận tổng số sự kiện, throughput trung bình trong một cửa sổ có thể tính:

~~~text
throughput = (counter_end - counter_start) / elapsed_seconds
~~~

Ví dụ, nếu processed counter tăng từ 12.000 lên 15.000 trong 60 giây:

~~~text
(15,000 - 12,000) / 60 = 50 messages/second
~~~

Trong hệ thống monitoring, dùng hàm rate/increase của backend thay vì tự đọc counter mỗi lần. Với Prometheus, ví dụ:

~~~promql
sum(rate(app_messaging_messages_total{
  direction="inbound",
  result="processed"
}[1m]))
~~~

Kết quả là tốc độ message xử lý thành công mỗi giây trên toàn bộ các series phù hợp.

Để xem số message thành công trong 5 phút:

~~~promql
sum(increase(app_messaging_messages_total{
  direction="inbound",
  result="processed"
}[5m]))
~~~

Tên metric Prometheus thực tế phụ thuộc quy tắc chuyển đổi tên của Micrometer và registry. Hãy kiểm tra endpoint metrics trước khi sao chép query vào dashboard.

### 3.1. Message/second và byte/second

Message throughput không phản ánh đầy đủ tải nếu kích thước payload thay đổi nhiều. Một hệ thống xử lý 1.000 message nhỏ mỗi giây khác với hệ thống xử lý 1.000 message 5 MB mỗi giây.

Đo cả hai:

- messages/second: số lượng message qua mỗi ranh giới.
- bytes/second: tổng byte payload hoặc byte wire qua ranh giới đã chọn.

Cần ghi rõ byte được đo trước hay sau serialization, có tính metadata/header hay không. Nếu producer đo object size còn consumer đo encoded bytes, hai metric không thể so sánh trực tiếp.

### 3.2. Đọc throughput cùng queue depth

Throughput giảm trong khi queue depth tăng thường gợi ý consumer không theo kịp producer. Throughput tăng nhưng processing latency cũng tăng có thể cho thấy hệ thống đang gần giới hạn tài nguyên.

Một dashboard tốt nên hiển thị ít nhất:

- Send accepted rate.
- Receive rate.
- Processed rate.
- Failure rate.
- Queue depth và remaining capacity.
- Processing latency p50/p95/p99.

Chỉ nhìn send rate cao không chứng minh hệ thống đang xử lý nhanh. Message có thể đang tích tụ ở broker hoặc queue.

## 4. Đo thời gian xử lý và latency

Thời gian xử lý cần được đo quanh đúng lifecycle. Một handler reactive có thể trả về Mono ngay lập tức nhưng công việc thật chỉ kết thúc sau đó. Nếu chỉ đo thời gian gọi method để lấy Mono, kết quả sẽ quá nhỏ và sai.

Phân biệt các khoảng thời gian:

| Khoảng thời gian | Bắt đầu | Kết thúc |
|---|---|---|
| Send duration | Bắt đầu gọi API gửi | API/transport hoàn tất theo contract |
| Queue wait | Broker nhận message | Consumer bắt đầu xử lý |
| Handler duration | Handler bắt đầu | Handler complete/error/cancel |
| End-to-end latency | Producer tạo/publish event | Consumer hoàn tất nghiệp vụ |
| Acknowledgement latency | Consumer xử lý xong | Broker/transport ghi nhận ack nếu có |

### 4.1. Timer quanh handler

Với xử lý đồng bộ, Timer.record có thể bao quanh lời gọi nghiệp vụ. Timer ghi nhận cả số lần thực hiện và thời gian:

~~~java
Timer handlerTimer = Timer.builder("app.messaging.handler")
    .tag("operation", "process")
    .register(meterRegistry);

handlerTimer.record(() -> handler.handle(message));
~~~

Nếu handler ném exception, Timer vẫn ghi nhận thời gian thực thi. Counter riêng nên ghi nhận success/failure để dashboard phân biệt kết quả.

### 4.2. Đo một reactive handler tới khi kết thúc

Với Reactor, không đo thời gian chỉ từ lúc tạo publisher. Có thể bắt đầu Timer.Sample khi publisher được subscribe và dừng khi hoàn tất, lỗi hoặc bị cancel:

~~~java
Mono<Reply> process(Message<?> message) {
    return Mono.defer(() -> {
        Timer.Sample sample = Timer.start(meterRegistry);

        return handler.handle(message)
            .doOnSuccess(reply -> processed.increment())
            .doOnError(error -> processingFailed.increment())
            .doFinally(signal -> sample.stop(handlerTimer));
    });
}
~~~

Đây là ví dụ minh họa một publisher được subscribe. Timer dừng ở terminal signal, bao gồm complete, error và cancel. Nếu cancellation cần được phân tích riêng, hãy có counter cho signal CANCEL và dùng outcome metric thích hợp.

Nếu đặt retry ở trong hay ngoài vùng đo, thời gian sẽ mang ý nghĩa khác nhau:

- Timer bên trong retry có thể ghi một mẫu cho mỗi attempt.
- Timer bên ngoài retry đo tổng thời gian của toàn bộ thao tác, bao gồm các lần chờ và thử lại.

Đặt tên và mô tả metric theo đúng ranh giới được đo. Không so sánh hai timer có ngữ nghĩa khác nhau.

### 4.3. End-to-end latency và clock skew

Nếu producer ghi publishedAt và consumer ghi processedAt, có thể tính latency từ hai timestamp. Tuy nhiên, hai máy có thể lệch đồng hồ. Với latency ngắn, clock skew vài chục mili giây đã có thể làm số liệu sai đáng kể hoặc âm.

Để đo end-to-end:

- Đồng bộ clock giữa các host bằng cơ chế time synchronization.
- Dùng tracing để liên kết producer và consumer.
- Ưu tiên đo duration trong cùng một process khi cần thời gian chính xác tại một đoạn.
- Phân biệt broker queue wait với handler duration.
- Không dùng timestamp do client tùy ý cung cấp làm mốc đáng tin cậy nếu chưa xác thực.

Trace giúp theo dõi một message qua nhiều service. Metrics cho xu hướng tổng thể; trace giúp tìm một request cụ thể bị chậm ở đâu.

## 5. Histogram, percentile và SLA

Average latency có thể che giấu các request rất chậm. Ví dụ, phần lớn message xử lý trong 10 ms nhưng một số message mất 5 giây. Mean có thể trông chấp nhận được trong khi người dùng vẫn thấy timeout.

Theo dõi ít nhất:

- p50: latency của điểm giữa.
- p90/p95: latency mà phần lớn request thấp hơn.
- p99: tail latency, nhạy với một nhóm request chậm.
- max: mẫu lớn nhất trong cửa sổ quan sát, hữu ích nhưng dễ dao động.
- error rate: tỷ lệ lỗi trên tổng số message đã xử lý.

Micrometer Timer có thể xuất histogram để backend tính percentile tổng hợp. Với Prometheus, có thể dùng histogram_quantile:

~~~promql
histogram_quantile(
  0.95,
  sum by (le) (
    rate(app_messaging_handler_seconds_bucket[5m])
  )
)
~~~

Tên metric và đơn vị được chuẩn hóa theo registry; Timer thường được xuất theo đơn vị giây trên Prometheus. Kiểm tra tên thực tế tại endpoint trước khi dùng query.

Có hai cách phổ biến:

- **Client-side percentiles:** tính percentile trong từng process. Dễ đọc cục bộ nhưng không thể cộng gộp chính xác percentile của nhiều instance.
- **Histogram buckets:** gửi bucket counts để backend tổng hợp rồi tính percentile. Phù hợp cho dashboard phân tán và so sánh nhiều instance.

Chọn bucket quanh ngưỡng SLA. Nếu SLA là handler p95 dưới 200 ms, bucket cần đủ độ phân giải quanh 200 ms. Không tạo hàng trăm bucket vô ích cho mọi timer.

## 6. Micrometer Observation trong Spring Boot

Spring Boot sử dụng Micrometer Observation làm abstraction cho metrics và traces. Một Observation có thể tạo meter và span tùy ObservationHandler đã cấu hình.

Spring Boot có thể cung cấp ObservationRegistry và MeterRegistry khi các dependency/auto-configuration phù hợp được bật. Với code nghiệp vụ, có thể tạo observation riêng:

~~~java
Observation.createNotStarted("messaging.process", observationRegistry)
    .lowCardinalityKeyValue("messaging.destination", "orders")
    .lowCardinalityKeyValue("messaging.operation", "handle")
    .observe(() -> orderHandler.handle(message));
~~~

Ví dụ này đo một lời gọi đồng bộ. Low-cardinality key-value được đưa vào metrics và traces. High-cardinality key-value như messageId hoặc customerId chỉ nên dùng trong trace khi thực sự cần, không nên đưa vào metric label.

Đối với reactive publisher, phải giữ observation sống tới terminal signal và bảo đảm context được truyền qua Reactor pipeline. Không dùng ví dụ đồng bộ ở trên để bao một lời gọi trả về Mono rồi kết thúc observation ngay khi publisher được tạo. Nếu cần đo duration reactive đơn giản, Timer.Sample với Mono.defer và doFinally là một lựa chọn dễ hiểu.

### 6.1. Metrics mặc định có giới hạn theo integration

Không phải mọi Spring Messaging handler hoặc RSocket endpoint đều tự động phát cùng một bộ metric. Hãy kiểm tra adapter và integration đang dùng.

Spring Framework có các observation tích hợp cho một số thành phần như HTTP, JMS publish/process và scheduled task. Với handler RSocket hoặc message flow tự viết, hãy chủ động instrument ở ranh giới send, receive và processing hoặc dùng integration có hỗ trợ tương ứng.

Nếu dùng Spring Integration, Micrometer metrics có thể được đăng ký cho các component như AbstractMessageChannel, AbstractMessageHandler và AbstractMessageSource khi MeterRegistry hiện diện. Tên metric truyền thống bao gồm:

- spring.integration.send: timer cho thao tác gửi của channel và handler, có tag type, name, result và exception.
- spring.integration.receive: counter cho thao tác nhận của pollable channel và message source.
- spring.integration.channel.queue.size: gauge kích thước QueueChannel.
- spring.integration.channel.queue.remaining.capacity: gauge dung lượng còn lại của QueueChannel.

Spring Integration từ phiên bản 6 có Micrometer Observation support. Việc instrument component phụ thuộc cấu hình IntegrationManagement, ObservationRegistry và observationPatterns; không nên giả định mọi component đã được bật nếu chưa cấu hình. Các observation producer/handler/gateway có convention và metric riêng của Spring Integration.

Đây là metrics của Spring Integration, không phải một cam kết rằng mọi MessageChannel hoặc RSocket handler thuần Spring Framework đều tự động có cùng meter.

## 7. Thiết kế tag và tránh cardinality bùng nổ

Tag giúp phân tích metric theo chiều như destination, operation và result. Nhưng mỗi tổ hợp tag tạo một meter series. Nếu giá trị tag không bị giới hạn, số series có thể tăng rất lớn.

Tag thường phù hợp:

- operation: send, receive, process.
- destination: orders, payments, notifications nếu danh sách hữu hạn.
- result: success, failure, rejected.
- transport: rsocket, jms, kafka nếu có tập nhỏ.
- exception: nhóm exception hoặc simple class name đã kiểm soát.

Không nên dùng làm metric tag:

- messageId, correlationId, traceId.
- userId, customerId, orderId.
- raw route hoặc destination do người dùng tùy ý tạo.
- exception message chứa dữ liệu động.
- payload, email hoặc thông tin nhạy cảm.

Các ID duy nhất phù hợp hơn trong logs/traces có sampling và retention được kiểm soát. Metrics cần chiều phân tích có số lượng giá trị hữu hạn.

Ví dụ tag tốt:

~~~text
destination=orders
operation=handle
result=failure
transport=rsocket
~~~

Ví dụ tag xấu:

~~~text
messageId=evt-7f92...
customerId=customer-483920...
exceptionMessage=failed for order 123456...
~~~

## 8. Spring Boot Actuator và export metrics

Một ứng dụng Spring Boot thường dùng Actuator và một Micrometer registry phù hợp với backend monitoring.

Dependency cơ bản:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-actuator</artifactId>
</dependency>
<dependency>
    <groupId>io.micrometer</groupId>
    <artifactId>micrometer-registry-prometheus</artifactId>
</dependency>
~~~

Dùng Spring Boot dependency management để chọn phiên bản tương thích. Không pin riêng Micrometer khác với BOM nếu không có lý do cụ thể.

Cấu hình endpoint ví dụ:

~~~properties
management.endpoints.web.exposure.include=health,metrics,prometheus
~~~

Endpoint /actuator/metrics giúp tra cứu meter theo tên và tag. Endpoint /actuator/prometheus cung cấp exposition format cho Prometheus nếu registry và endpoint đã được cấu hình. Cần bảo vệ endpoint management bằng network policy và authentication phù hợp; không nên công khai toàn bộ thông tin vận hành ra Internet.

Một luồng cơ bản:

~~~text
Messaging handler
      |
      v
Micrometer Counter / Timer / Observation
      |
      v
MeterRegistry + ObservationRegistry
      |
      v
Prometheus registry / OTLP registry
      |
      v
Prometheus / metrics backend
      |
      v
Dashboard + alert
~~~

Metrics không thay thế logs và traces. Metrics cho biết xu hướng như processing rate giảm hoặc p99 tăng; trace giúp tìm message nào đi qua thành phần nào và chậm ở đâu; logs cung cấp chi tiết lỗi và ngữ cảnh nghiệp vụ.

## 9. Ví dụ Java 17: đo send/receive và processing duration

Ví dụ sau dùng Micrometer Core và SimpleMeterRegistry để mô phỏng một luồng message. Trong ứng dụng Spring Boot, thay SimpleMeterRegistry bằng MeterRegistry được auto-configure hoặc registry được inject.

### Maven dependency

Trong project Spring Boot, dùng dependency management của Boot:

~~~xml
<dependency>
    <groupId>io.micrometer</groupId>
    <artifactId>micrometer-core</artifactId>
</dependency>
~~~

### Source code

Lưu thành **MessageMetricsDemo.java**:

~~~java
import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;

import java.util.List;

public class MessageMetricsDemo {

    public static void main(String[] args) {
        MeterRegistry registry = new SimpleMeterRegistry();

        Counter sendAttempts = Counter.builder("demo.messaging.messages")
            .tag("direction", "outbound")
            .tag("result", "attempt")
            .register(registry);

        Counter sendAccepted = Counter.builder("demo.messaging.messages")
            .tag("direction", "outbound")
            .tag("result", "accepted")
            .register(registry);

        Counter received = Counter.builder("demo.messaging.messages")
            .tag("direction", "inbound")
            .tag("result", "received")
            .register(registry);

        Counter processed = Counter.builder("demo.messaging.messages")
            .tag("direction", "inbound")
            .tag("result", "processed")
            .register(registry);

        Counter processingFailed =
            Counter.builder("demo.messaging.messages")
                .tag("direction", "inbound")
                .tag("result", "failed")
                .register(registry);

        Timer handlerTimer = Timer.builder("demo.messaging.handler")
            .tag("handler", "orders")
            .register(registry);

        List<String> outgoing = List.of("order-1", "order-2");
        sendAttempts.increment(outgoing.size());
        sendAccepted.increment(outgoing.size());

        for (String message : outgoing) {
            received.increment();

            Timer.Sample sample = Timer.start(registry);
            try {
                handle(message);
                processed.increment();
            } catch (IllegalArgumentException ex) {
                processingFailed.increment();
            } finally {
                sample.stop(handlerTimer);
            }
        }

        System.out.println("send-attempts=" + (long) sendAttempts.count());
        System.out.println("send-accepted=" + (long) sendAccepted.count());
        System.out.println("received=" + (long) received.count());
        System.out.println("processed=" + (long) processed.count());
        System.out.println(
            "processing-failed=" + (long) processingFailed.count()
        );
        System.out.println("processing-samples=" + handlerTimer.count());

        registry.close();
    }

    private static void handle(String message) {
        if ("order-2".equals(message)) {
            throw new IllegalArgumentException("Invalid test message");
        }
    }
}
~~~

### Biên dịch và chạy

~~~bash
javac -cp micrometer-core.jar MessageMetricsDemo.java
java -cp .;micrometer-core.jar MessageMetricsDemo
~~~

Hai lệnh trên minh họa cách chạy khi micrometer-core.jar và các dependency transitives đã có trong classpath. Trong project Maven/Gradle thực tế, để build tool quản lý dependency sẽ thuận tiện hơn.

Output chính xác:

~~~text
send-attempts=2
send-accepted=2
received=2
processed=1
processing-failed=1
processing-samples=2
~~~

Timer ghi nhận hai lần xử lý, bao gồm một lần thành công và một lần lỗi. Các counter cho biết kết quả nghiệp vụ. Ví dụ dùng SimpleMeterRegistry để kiểm tra trong bộ nhớ; registry production có thể export dữ liệu sang Prometheus hoặc backend khác.

## 10. Dashboard và alert cần trả lời câu hỏi gì?

Một dashboard messaging nên giúp người vận hành trả lời các câu hỏi:

**Producer có gửi được không?**
- Send attempts và send accepted rate.
- Send failures theo result/exception.
- Send duration p95.

**Consumer có nhận và xử lý kịp không?**
- Receive rate và processed rate.
- Processing failures và retries/redeliveries.
- Handler duration p50/p95/p99.
- Queue depth và active handler count.

**Hệ thống có bị nghẽn không?**
- Queue depth tăng liên tục.
- Processed rate thấp hơn receive rate trong một khoảng đủ dài.
- In-flight request tăng.
- p95/p99 tăng trong khi throughput không tăng tương ứng.
- Worker pool hoặc connection pool cạn capacity.

**Có sự cố nghiệp vụ hay hạ tầng?**
- Lỗi validation/conflict khác với timeout hoặc connection error.
- Một destination cụ thể lỗi khác với toàn hệ thống.
- Consumer không hoạt động khác với consumer hoạt động nhưng xử lý chậm.

Alert nên dựa trên cửa sổ thời gian và ngưỡng phù hợp với workload. Không alert chỉ vì một mẫu p99 cao trong một cửa sổ có rất ít message. Kết hợp latency với traffic volume và error rate để giảm cảnh báo nhiễu.

## 11. Kiểm thử metrics

Metrics cũng là một phần của hành vi ứng dụng và cần được kiểm tra.

Các test hữu ích:

1. Gửi một message thành công; send accepted và processed counter tăng đúng một.
2. Send thất bại; failure counter tăng nhưng accepted không tăng.
3. Handler ném exception; processing Timer vẫn ghi nhận một mẫu và failure counter tăng.
4. Handler reactive bị cancel; timer dừng và cancellation được phân loại riêng nếu cần.
5. Một message được retry; attempt count tăng theo số lần thử, nhưng business success chỉ tăng theo số thao tác thành công.
6. Một message được redeliver; receive/redelivery count phản ánh đúng chính sách adapter.
7. Một message được deduplicate; receive count có thể tăng nhưng business processed count không tăng thêm.
8. Timer được đo tới terminal signal, không dừng khi publisher vừa được tạo.
9. Tags chỉ dùng các giá trị hữu hạn; messageId không tạo meter riêng.
10. Prometheus scrape hiển thị metric name, unit và labels đúng như dashboard đang dùng.

Đối với test với SimpleMeterRegistry, có thể kiểm tra count và totalTime bằng API Micrometer. Với integration test, nên xác minh adapter thực tế phát meter nào thay vì giả định mọi transport có cùng semantics.

## 12. Sai lầm thường gặp

- Đếm send API call như thể broker đã lưu bền vững.
- Đếm message received như thể handler đã xử lý thành công.
- Dùng Gauge cho tổng số message tích lũy.
- Dùng Counter cho queue depth hiện tại.
- Tính throughput từ giá trị counter tuyệt đối mà không xét thời gian và reset.
- Chỉ theo dõi average latency mà bỏ p95/p99.
- Đo thời gian gọi method trả về Mono thay vì thời gian publisher hoàn tất.
- Trộn queue wait, handler duration và end-to-end latency vào một timer.
- Không phân biệt retry, redelivery và xử lý thành công.
- Đưa messageId/userId vào tag làm cardinality tăng không giới hạn.
- Cho rằng Spring Messaging/RSocket handler nào cũng có metric tự động.
- Bật instrumentation ở cả framework và custom code mà không kiểm tra duplicate observations.
- Dùng một metric name giống nhau cho hai ranh giới đo khác nhau.

## 13. Checklist triển khai

- [ ] Send attempt, send accepted, receive, processed và failed có định nghĩa rõ.
- [ ] Retry/redelivery/deduplication được đếm riêng khi cần.
- [ ] Counter dùng cho sự kiện tích lũy; Gauge dùng cho giá trị hiện tại.
- [ ] Timer bao quanh đúng ranh giới xử lý.
- [ ] Reactive timer dừng ở complete/error/cancel.
- [ ] Có throughput message/second và byte/second.
- [ ] Có processing latency p50/p95/p99 và error rate.
- [ ] Queue depth và in-flight work được quan sát.
- [ ] Tag có cardinality thấp, không chứa ID duy nhất hoặc payload.
- [ ] Micrometer Observation/Tracing được cấu hình ở ranh giới cần theo dõi.
- [ ] Metrics mặc định của transport/integration đã được xác minh.
- [ ] Có test cho success, failure, retry, redelivery và cancellation.
- [ ] Dashboard và alert dùng đúng metric semantics.

## Kết luận

Đo messaging hiệu quả bắt đầu từ định nghĩa chính xác một lần gửi, nhận và xử lý. Counter cho biết số sự kiện; Timer đo duration và phân phối latency; Gauge cho biết queue/in-flight state. Thông lượng phải được tính từ tốc độ tăng counter, còn p95/p99 giúp phát hiện tail latency mà average che giấu. Micrometer và Spring Boot cung cấp nền tảng quan sát; custom RSocket/message handler cần được instrument theo lifecycle thực tế, còn Spring Integration có bộ metrics/observations riêng theo component và cấu hình.

## Tài liệu tham khảo

- [Spring Boot Reference - Observability](https://docs.spring.io/spring-boot/reference/actuator/observability.html)
- [Spring Boot Reference - Metrics](https://docs.spring.io/spring-boot/reference/actuator/metrics.html)
- [Spring Framework Reference - Observability](https://docs.spring.io/spring-framework/reference/integration/observability.html)
- [Spring Integration Reference - Metrics and Management](https://docs.spring.io/spring-integration/reference/metrics.html)
- [Micrometer Reference - Meters](https://docs.micrometer.io/micrometer/reference/concepts/meters.html)
- [Micrometer Reference - Timers](https://docs.micrometer.io/micrometer/reference/concepts/timers.html)
- [Prometheus Documentation - Querying](https://prometheus.io/docs/prometheus/latest/querying/basics/)
