# Phân biệt sức khỏe kết nối với khả năng xử lý nghiệp vụ

Trong một ứng dụng Spring Cloud Stream, trạng thái kết nối tới Kafka, RabbitMQ hoặc Pulsar chỉ cho biết ứng dụng có thể giao tiếp với broker ở thời điểm kiểm tra. Nó chưa chứng minh rằng message đang được tiêu thụ, function đang hoàn thành công việc, dữ liệu được ghi vào hệ thống đích hoặc kết quả nghiệp vụ đáp ứng thời hạn.

Một consumer có thể giữ kết nối broker ở trạng thái UP nhưng bị kẹt trong lời gọi cơ sở dữ liệu. Producer có thể kết nối thành công nhưng message liên tục bị đưa vào DLQ. Ngược lại, một ứng dụng có thể không nhận message trong vài phút vì upstream không phát sinh sự kiện; đây không nhất thiết là lỗi.

Vì vậy, cần quan sát riêng ít nhất bốn lớp: sức khỏe tiến trình, sức khỏe kết nối binder/broker, luồng vận chuyển message và kết quả xử lý nghiệp vụ. Chỉ ghép các tín hiệu này mới cho biết dịch vụ có thực sự hoàn thành công việc hay không.

## 1. Bốn lớp sức khỏe cần quan sát

| Lớp | Câu hỏi cần trả lời | Ví dụ tín hiệu |
|---|---|---|
| Tiến trình | Ứng dụng còn sống và có thể nhận việc không? | Liveness, readiness, thread pool, memory |
| Kết nối | Binder có giao tiếp được với broker không? | Binder health indicator, connection, authentication, metadata request |
| Vận chuyển | Message có được nhận, gửi và chuyển tiếp không? | Consumer assignment, publish ack, consumer lag, queue depth, redelivery |
| Nghiệp vụ | Message có tạo ra kết quả đúng và đúng hạn không? | Success rate, processing latency, oldest backlog age, business failure, DLQ |

Các lớp có quan hệ nhưng không thay thế nhau. Broker có thể UP trong khi nghiệp vụ DOWN; một function có thể xử lý thành công nhưng output broker không nhận được; hoặc broker có thể tạm thời DOWN trong khi ứng dụng vẫn giữ trạng thái nghiệp vụ đã hoàn tất cho các message trước đó.

~~~mermaid
flowchart TD
    A["Tiến trình<br/>Liveness / Readiness"] --> B["Binder và broker<br/>Kết nối, xác thực"]
    B --> C["Vận chuyển message<br/>Consume / Publish / Lag"]
    C --> D["Xử lý nghiệp vụ<br/>Validation / Database / Side effect"]
    D --> E["Kết quả đầu ra<br/>ACK / Output / DLQ"]
    F["Metrics, logs, traces"] -. quan sát .-> A
    F -. quan sát .-> B
    F -. quan sát .-> C
    F -. quan sát .-> D
    F -. quan sát .-> E
~~~

Khi thiết kế dashboard và cảnh báo, hãy đặt câu hỏi theo từng lớp thay vì dùng một trạng thái UP/DOWN duy nhất cho mọi thứ.

## 2. Sức khỏe tiến trình: liveness và readiness

Liveness trả lời câu hỏi tiến trình có còn hoạt động hay đã rơi vào trạng thái không thể phục hồi, chẳng hạn deadlock hoặc vòng lặp làm ứng dụng ngừng tiến triển. Readiness cho biết instance đã sẵn sàng tham gia phục vụ theo điều kiện vận hành của ứng dụng hay chưa.

Spring Boot Actuator cung cấp health endpoint và các health group cho Kubernetes:

- Liveness: tiến trình còn sống; nếu thất bại liên tục, nền tảng có thể khởi động lại container.
- Readiness: instance có nên được nhận traffic hoặc được xem là sẵn sàng trong rollout hay không.
- Health tổng hợp: kết hợp các HealthContributor đã được cấu hình.

Với ứng dụng xử lý message, không nên đưa mọi lỗi kết nối broker vào liveness. Broker bên ngoài bị gián đoạn không có nghĩa tiến trình Java đã hỏng. Nếu liveness phụ thuộc broker, Kubernetes có thể liên tục restart các instance trong lúc broker đang phục hồi, tạo thêm kết nối và tải không cần thiết.

Readiness có thể bao gồm điều kiện kết nối broker nếu quy trình triển khai cần chờ binder sẵn sàng trước khi coi instance là healthy. Tuy nhiên, readiness của HTTP service không tự động dừng consumer message. Kafka consumer group hoặc Rabbit listener có vòng đời riêng do binder quản lý; cần hiểu hành vi của binder khi readiness chuyển DOWN.

Ví dụ bật probe và các endpoint quan sát:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,metrics,prometheus
  endpoint:
    health:
      probes:
        enabled: true
      show-details: when-authorized
  health:
    binders:
      enabled: true
~~~

Để xuất metrics Prometheus, thêm registry tương ứng, ví dụ micrometer-registry-prometheus, vào dependency của ứng dụng. Chỉ mở các endpoint cần thiết và bảo vệ chi tiết health/metrics bằng cơ chế xác thực, mạng nội bộ hoặc chính sách nền tảng.

## 3. Sức khỏe kết nối binder và broker

Spring Cloud Stream có health indicator cho binder. Health tổng hợp có thể cho biết binder có kiểm tra được trạng thái kết nối tới middleware theo cơ chế của binder implementation hay không. Thuộc tính management.health.binders.enabled điều khiển health indicator này; hãy đối chiếu mặc định và cách triển khai với phiên bản Spring Cloud Stream trong BOM của ứng dụng.

Một binder health indicator hữu ích để phát hiện:

- Broker không thể truy cập hoặc connection bị đóng.
- Sai thông tin xác thực hoặc lỗi phân quyền khi tạo kết nối.
- Không thể thực hiện thao tác kiểm tra broker cần thiết.
- Một binder trong ứng dụng nhiều binder bị lỗi trong khi binder khác vẫn hoạt động.

Nhưng health indicator không phải phép thử end-to-end. Trạng thái UP không khẳng định rằng consumer group đã nhận partition, queue đang có consumer, function không bị nghẽn, hoặc output đã được hệ thống đích xử lý.

Ví dụ, RabbitMQ có thể chấp nhận TCP connection và AMQP channel nhưng queue đang có zero consumer. Kafka bootstrap broker có thể phản hồi metadata request nhưng consumer group chưa được assign partition. Pulsar broker có thể chấp nhận kết nối trong khi subscription backlog vẫn tăng.

### 3.1. Kết nối thành công không đồng nghĩa message được xử lý

| Tình huống | Health kết nối | Khả năng xử lý |
|---|---|---|
| Broker reachable, consumer chưa được assign partition | Có thể UP | Chưa tiêu thụ được message |
| Rabbit connection mở, queue không có consumer | Có thể UP | Message tích tụ trong queue |
| Producer kết nối broker nhưng publish bị reject do ACL/topic policy | Có thể UP | Output không được ghi như mong đợi |
| Function nhận message nhưng gọi database timeout | UP | Xử lý nghiệp vụ thất bại |
| Function hoàn tất nhưng message bị retry do lỗi ack/commit | UP | Có thể xử lý lặp |
| Broker tạm ngắt nhưng ứng dụng vẫn đang phục vụ request độc lập | DOWN ở lớp kết nối | Một số chức năng khác vẫn có thể hoạt động |

Do đó, hãy hiển thị trạng thái binder riêng với các chỉ số consumer, producer và nghiệp vụ. Không diễn giải một dấu UP trên dashboard thành kết luận toàn bộ pipeline khỏe.

## 4. Sức khỏe vận chuyển message

Lớp vận chuyển trả lời message có đi qua hệ thống theo đúng nhịp hay không. Tối thiểu cần quan sát cả đầu vào và đầu ra:

- Số message được publish.
- Số message được consume hoặc dispatch.
- Số message được acknowledge/commit.
- Số lần redelivery hoặc retry.
- Consumer lag hoặc queue backlog.
- Tuổi của message cũ nhất đang chờ.
- Số message vào DLQ hoặc parking-lot queue.

Throughput cao chưa chắc tốt: hệ thống có thể đang xử lý một lượng lớn message lỗi rồi retry. Throughput thấp cũng chưa chắc xấu: upstream có thể không có sự kiện mới. Phải so sánh tốc độ vào, tốc độ ra, backlog và tuổi message.

### 4.1. Chỉ số theo từng broker

| Broker | Chỉ số vận chuyển nên theo dõi |
|---|---|
| Kafka | Consumer lag theo group/partition, records consumed, fetch rate, rebalance, commit rate, producer send/error rate |
| RabbitMQ | Ready messages, unacked messages, consumer count, publish/ack/nack rate, redelivery, connection/channel, DLQ depth |
| Pulsar | Subscription backlog, unacked messages, redelivery, ack rate, publish/dispatch rate, consumer count và topic backlog |

Tên metric cụ thể phụ thuộc binder, client và phiên bản. Không nên giả định mọi binder xuất cùng một tên metric hoặc có cùng ngữ nghĩa. Hãy xem danh sách metrics thực tế qua Actuator/Micrometer, broker dashboard và tài liệu của phiên bản đang triển khai.

### 4.2. Phân biệt lag với lỗi nghiệp vụ

Kafka consumer lag là chênh lệch giữa vị trí record mới nhất và offset consumer group đã xử lý/commit. Lag tăng có thể do tốc độ phát cao hơn tốc độ tiêu thụ, consumer không hoạt động, rebalance kéo dài hoặc handler chậm.

RabbitMQ queue depth là số message đang ready hoặc unacked tùy chỉ số. Queue ready tăng trong khi consumer count bằng 0 thường cho thấy queue chưa được tiêu thụ. Unacked tăng cao có thể phản ánh consumer đang giữ nhiều delivery hoặc xử lý chậm.

Pulsar subscription backlog thể hiện lượng message còn chờ theo subscription. Backlog tăng liên tục cần được xem cùng ack rate, redelivery và trạng thái consumer.

Lag/backlog là tín hiệu vận chuyển. Nó chưa chỉ ra nguyên nhân nghiệp vụ. Muốn biết vì sao xử lý chậm, cần ghép với processing duration, lỗi dependency, trace và trạng thái output.

## 5. Sức khỏe xử lý nghiệp vụ

Sức khỏe nghiệp vụ tập trung vào kết quả mà dịch vụ được giao phải tạo ra. Ví dụ với consumer xử lý đơn hàng:

- Bao nhiêu đơn hàng đã được xử lý thành công?
- Tỷ lệ đơn hàng thất bại do validation, database hay dịch vụ thanh toán là bao nhiêu?
- Thời gian từ lúc sự kiện được phát đến khi đơn hàng được cập nhật là bao lâu?
- Message cũ nhất chưa hoàn tất đã chờ bao lâu?
- Có message nào bị đưa vào DLQ không?
- Một event ID có bị xử lý lặp hoặc tạo side effect trùng không?

Một bộ chỉ số nghiệp vụ nên có:

| Metric/SLI | Ý nghĩa |
|---|---|
| Business events received | Số sự kiện đã vào handler |
| Business events succeeded | Số sự kiện hoàn thành quy trình nghiệp vụ |
| Business events failed | Số lần xử lý thất bại, có phân loại nguyên nhân |
| Processing duration | Thời gian handler hoặc use case thực thi |
| End-to-end latency | Thời gian từ event timestamp đến kết quả hoàn tất |
| Oldest pending age | Tuổi message hoặc công việc chưa hoàn tất lâu nhất |
| Retry count | Số lần thử lại |
| DLQ/parking-lot count | Số sự kiện cần can thiệp hoặc điều tra |
| Duplicate/idempotency hit | Số lần phát hiện sự kiện đã được xử lý trước đó |

Nên đo thời gian nghiệp vụ từ một mốc có ý nghĩa. Timer bao quanh handler đo thời gian thực thi handler; nó không nhất thiết bao gồm thời gian message nằm trong broker, thời gian chờ retry hoặc thời gian downstream hoàn tất bất đồng bộ.

End-to-end latency nên dùng event timestamp hoặc timestamp được ghi nhận khi hệ thống nhận sự kiện, rồi so sánh với thời điểm hoàn tất nghiệp vụ. Cần xử lý clock skew và sự kiện đến muộn khi tính toán.

## 6. Gắn metrics vào function của Spring Cloud Stream

Ví dụ dưới đây dùng Consumer để xử lý side effect. Service chỉ trả về sau khi giao dịch nghiệp vụ đã commit thành công. Metric success vì thế biểu diễn kết quả use case, không chỉ là việc function được gọi.

Kiểu dữ liệu:

~~~java
public record OrderAccepted(
    String eventId,
    String orderId,
    String customerId
) {}
~~~

Theo dõi tiến độ gần nhất:

~~~java
import java.time.Instant;
import java.util.concurrent.atomic.AtomicReference;

import org.springframework.stereotype.Component;

@Component
class ProcessingProgress {

    private final AtomicReference<Instant> lastReceived =
        new AtomicReference<>();

    private final AtomicReference<Instant> lastSucceeded =
        new AtomicReference<>();

    void received() {
        lastReceived.set(Instant.now());
    }

    void succeeded() {
        lastSucceeded.set(Instant.now());
    }

    Instant lastReceived() {
        return lastReceived.get();
    }

    Instant lastSucceeded() {
        return lastSucceeded.get();
    }
}
~~~

Đo số lần xử lý và thời gian:

~~~java
import java.util.function.Consumer;

import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class OrderConsumerConfiguration {

    @Bean
    Consumer<OrderAccepted> processOrder(
            OrderService orderService,
            ProcessingProgress progress,
            MeterRegistry registry) {

        Counter succeeded = Counter.builder("orders.processing")
            .tag("outcome", "success")
            .register(registry);

        Counter failed = Counter.builder("orders.processing")
            .tag("outcome", "failure")
            .register(registry);

        Timer duration = Timer.builder("orders.processing.duration")
            .description("Thời gian xử lý nghiệp vụ đơn hàng")
            .register(registry);

        return event -> {
            progress.received();
            Timer.Sample sample = Timer.start(registry);
            try {
                orderService.processAndCommit(event);
                progress.succeeded();
                succeeded.increment();
            }
            catch (RuntimeException exception) {
                failed.increment();
                throw exception;
            }
            finally {
                sample.stop(duration);
            }
        };
    }
}
~~~

Hàm processAndCommit cần đại diện cho ranh giới hoàn tất nghiệp vụ, chẳng hạn cập nhật database trong transaction và commit trước khi trả về. Khi exception được ném lại, binder có thể áp dụng retry hoặc error handling theo cấu hình.

Metric trên đếm số lần gọi handler thành công/thất bại. Nếu binder retry một message ba lần, một event logic có thể tạo nhiều lần failure trước khi thành công. Vì vậy, không diễn giải trực tiếp số lần gọi handler thành số event nghiệp vụ duy nhất. Nếu cần đếm kết quả cuối cùng của mỗi event, hãy ghi nhận theo event ID tại ranh giới xử lý cuối hoặc tổng hợp thêm số message đưa vào DLQ.

Không gắn eventId, orderId, customerId, email hoặc giá trị payload làm metric tag. Các giá trị có cardinality cao làm tăng bộ nhớ và chi phí lưu trữ metrics. Dùng log có cấu trúc và trace attributes để tra cứu từng sự kiện.

## 7. Health indicator nghiệp vụ phải có ngữ nghĩa rõ

Có thể tạo HealthIndicator riêng để biểu diễn tiến độ xử lý. Ví dụ sau đánh dấu DOWN khi gần đây handler có nhận message nhưng không ghi nhận thành công trong khoảng thời gian cho phép:

~~~java
import java.time.Duration;
import java.time.Instant;

import org.springframework.boot.actuate.health.Health;
import org.springframework.boot.actuate.health.HealthIndicator;
import org.springframework.stereotype.Component;

@Component("businessProcessing")
class BusinessProcessingHealthIndicator implements HealthIndicator {

    private static final Duration STALE_AFTER = Duration.ofMinutes(5);

    private final ProcessingProgress progress;

    BusinessProcessingHealthIndicator(ProcessingProgress progress) {
        this.progress = progress;
    }

    @Override
    public Health health() {
        Instant received = progress.lastReceived();
        Instant succeeded = progress.lastSucceeded();
        Instant now = Instant.now();

        if (received == null) {
            return Health.unknown()
                .withDetail("state", "NO_MESSAGE_OBSERVED")
                .build();
        }

        boolean recentInput =
            Duration.between(received, now).compareTo(STALE_AFTER) <= 0;

        boolean successIsStale = succeeded == null
            || Duration.between(succeeded, now).compareTo(STALE_AFTER) > 0;

        if (recentInput && successIsStale) {
            return Health.down()
                .withDetail("state", "INPUT_WITHOUT_RECENT_SUCCESS")
                .withDetail("lastReceived", received)
                .withDetail("lastSucceeded", succeeded)
                .build();
        }

        return Health.up()
            .withDetail("lastReceived", received)
            .withDetail("lastSucceeded", succeeded)
            .build();
    }
}
~~~

Đây là ví dụ chính sách đơn giản, không phải định nghĩa chung cho mọi ứng dụng. Trong production, nên cấu hình ngưỡng theo SLO, số lượng message, thời gian xử lý bình thường và đặc điểm lưu lượng.

Nếu không có traffic, indicator trả UNKNOWN thay vì kết luận DOWN chỉ vì không có lần xử lý thành công mới. Nếu input liên tục đến nhưng không có success, indicator phát hiện tình trạng đình trệ. Tuy nhiên, nó chỉ quan sát handler đã được gọi; message đang nằm trong broker mà chưa được giao tới handler cần được phát hiện bằng lag hoặc queue backlog.

Với workload theo lô hoặc lưu lượng rất thưa, không nên dùng một ngưỡng cố định năm phút. Hãy kết hợp:

- Input rate hoặc số message đang chờ.
- Consumer lag/queue depth.
- Tuổi message cũ nhất.
- Thời điểm xử lý thành công gần nhất khi có input.
- Lịch xử lý dự kiến nếu chỉ chạy theo batch.

Không đưa mọi lỗi nghiệp vụ vào liveness. Một record sai schema hoặc một giao dịch thất bại có thể khiến business health DOWN nhưng tiến trình vẫn hoạt động và có thể tiếp tục xử lý record khác.

## 8. Phân biệt handler success với output delivery success

Với Consumer, service có thể cập nhật database rồi trả về; khi đó handler success đo được việc use case hoàn thành trong ranh giới service. Với Function trả về một message, function hoàn thành khi tạo ra output object, nhưng binder còn phải publish object đó tới broker đích.

Do đó, hai tín hiệu cần được tách:

1. Function transformation success: dữ liệu đầu vào đã được chuyển đổi thành output.
2. Output delivery success: binder/client đã publish và nhận xác nhận theo semantics của broker.

Nếu output đi qua broker thứ hai, việc function trả về không chứng minh broker thứ hai đã nhận hoặc consumer cuối đã xử lý. Hãy theo dõi producer error/ack/return và trạng thái consumer downstream.

Trong ứng dụng dùng Kafka và RabbitMQ cùng lúc, không có transaction phân tán tự động bao trùm cả hai binder. Một phía có thể hoàn tất trong khi phía còn lại thất bại. Hãy dùng outbox, idempotency, retry có giới hạn hoặc quy trình bù trừ theo yêu cầu giao nhận.

## 9. Quan sát backlog và tuổi message

Backlog count cho biết số lượng công việc chờ. Backlog age cho biết công việc cũ nhất đã chờ bao lâu. Hai chỉ số bổ sung cho nhau:

- Queue có 100.000 message nhưng throughput lớn và tuổi message thấp có thể đang bắt kịp tải.
- Queue chỉ có 20 message nhưng message cũ nhất đã chờ 45 phút có thể vi phạm SLO nghiêm trọng.
- Consumer lag tăng liên tục cho thấy tốc độ xử lý không theo kịp tốc độ phát.
- Lag bằng 0 nhưng DLQ tăng cho thấy message đã rời luồng chính nhưng nghiệp vụ vẫn thất bại.

Nên theo dõi oldest pending age hoặc end-to-end latency percentile cùng với backlog. Với Kafka, lag theo partition giúp phát hiện một partition bị nóng trong khi tổng lag có vẻ ổn. Với RabbitMQ, cần tách ready và unacked. Với Pulsar, theo dõi backlog và redelivery theo subscription.

Một số dashboard hữu ích:

| Dashboard | Biểu đồ chính |
|---|---|
| Broker connectivity | Binder health, connection errors, authentication failures |
| Message transport | Input/output rate, lag/backlog, consumer count, redelivery |
| Business processing | Success/failure, processing duration, end-to-end latency |
| Error handling | Retry rate, DLQ ingress, parking-lot depth, exception category |
| Dependency health | Database latency, downstream API error rate, connection pool |

## 10. Phân loại lỗi theo nơi phát sinh

Nếu chỉ có một counter tên errors, đội vận hành khó biết cần xử lý ở broker, serialization hay nghiệp vụ. Hãy phân loại lỗi theo ranh giới:

| Loại lỗi | Ví dụ | Tín hiệu cần theo dõi |
|---|---|---|
| Connectivity | Timeout, connection refused, TLS/authentication | Binder health, connection error |
| Provisioning/permission | Topic/exchange không tồn tại, ACL thiếu | Provisioning error, producer error |
| Serialization | Không deserialize được payload hoặc schema không tương thích | Deserialization error, invalid message |
| Delivery | Publish nack/return, consumer redelivery | Producer error, redelivery, unacked |
| Business validation | Thiếu trường, trạng thái đơn hàng không hợp lệ | Validation failure, DLQ reason |
| Dependency | Database/API timeout hoặc unavailable | Dependency latency/error |
| Business rule | Không đủ hạn mức, giao dịch bị từ chối | Business outcome theo mã nguyên nhân |

Không retry mọi lỗi giống nhau. Connectivity timeout có thể tạm thời; payload sai schema thường cần quarantine hoặc DLQ; lỗi nghiệp vụ từ chối có thể là kết quả hợp lệ chứ không phải lỗi hệ thống. Metric và log nên giữ phân loại này.

## 11. Logging, correlation ID và distributed tracing

Metrics cho biết xu hướng và mức độ. Log giúp điều tra một lần xử lý cụ thể. Trace cho thấy thời gian và quan hệ giữa các bước trong pipeline.

Mỗi event nên có một định danh ổn định, chẳng hạn eventId, cùng correlationId hoặc trace context. Ghi các trường này trong structured log để liên kết:

- Consumer nhận record.
- Function hoặc service bắt đầu xử lý.
- Lời gọi database hoặc API downstream.
- Kết quả commit.
- Producer gửi output.
- Consumer tiếp theo hoàn tất.

Không ghi toàn bộ payload nhạy cảm vào log. Chỉ ghi metadata cần thiết, loại sự kiện, eventId, correlationId, destination, partition/offset hoặc queue, kết quả và mã lỗi đã chuẩn hóa.

Distributed tracing có thể tạo span cho việc nhận message, xử lý function và lời gọi downstream. Nếu trace context được truyền qua message header, các service có thể liên kết trace xuyên qua broker. Cần cấu hình propagation tương thích với phiên bản Micrometer Tracing/OpenTelemetry và binder đang dùng.

Khi retry hoặc redelivery, cần phân biệt cùng một event logic với từng lần thử. Có thể giữ eventId ổn định và tạo span/attempt attribute riêng cho từng lần delivery. Điều này giúp xác định một sự kiện đã thử bao nhiêu lần mà không tạo metric tag có cardinality cao.

## 12. Alert theo triệu chứng nghiệp vụ, không chỉ theo trạng thái broker

Một cảnh báo tốt gắn với hành động cụ thể. Ví dụ:

| Điều kiện quan sát | Diễn giải | Hành động điều tra |
|---|---|---|
| Binder DOWN và publish/consume lỗi | Có thể mất kết nối hoặc xác thực | Kiểm tra broker, DNS, network, TLS, credential và ACL |
| Binder UP nhưng consumer lag tăng liên tục | Consumer không theo kịp hoặc không xử lý | Kiểm tra assignment, concurrency, handler latency và dependency |
| Input rate cao, success rate thấp, DLQ tăng | Pipeline đang nhận nhưng không hoàn tất nghiệp vụ | Phân loại exception, schema, database và rule validation |
| Queue ready tăng, consumer count bằng 0 | Queue không có consumer hoạt động | Kiểm tra listener lifecycle, binding và deployment |
| Unacked tăng và processing duration cao | Consumer giữ delivery lâu | Kiểm tra thread pool, downstream timeout và prefetch |
| Lag thấp nhưng end-to-end latency cao | Message không backlog nhưng từng xử lý chậm | Kiểm tra thời gian chờ dependency và bước đồng bộ |
| Không có input và không có backlog | Có thể là trạng thái idle bình thường | Đối chiếu lịch và lưu lượng upstream trước khi cảnh báo |
| Broker UP, success gần đây nhưng một partition lag cao | Có thể hot partition hoặc phân phối key lệch | Kiểm tra lag theo partition và key skew |

Đặt cảnh báo theo thời gian duy trì và mức độ ảnh hưởng. Một lần broker health chập chờn trong vài giây không nhất thiết cần paging. Ngược lại, oldest pending age vượt SLO hoặc tỷ lệ thất bại tăng liên tục cần được ưu tiên ngay cả khi broker vẫn UP.

Ví dụ biểu thức PromQL minh họa:

~~~promql
sum(rate(orders_processing_total{outcome="failure"}[5m]))
/
clamp_min(sum(rate(orders_processing_total[5m])), 1)
~~~

Biểu thức giả định registry xuất metric Micrometer tên orders_processing_total và label outcome. Tên metric cuối cùng có thể được chuẩn hóa khác nhau theo registry. Hãy xác minh metric thực tế trước khi dùng alert rule.

## 13. Canary event và kiểm tra end-to-end

Health indicator kết nối và metrics nội bộ không chứng minh toàn bộ tuyến xử lý đang hoạt động. Có thể bổ sung một canary event định kỳ:

1. Một probe publisher gửi event kiểm tra vào tuyến riêng.
2. Consumer thực hiện các bước tương tự pipeline cần giám sát.
3. Một điểm xác nhận cuối ghi nhận eventId và thời điểm hoàn tất.
4. Monitor đo thời gian từ lúc phát đến lúc nhận xác nhận.

Canary cần có event type hoặc tenant riêng để không gây side effect nghiệp vụ thật. Nếu phải đi qua cùng topic production, handler cần nhận diện canary và xử lý idempotent, đồng thời tránh tạo đơn hàng, thanh toán hoặc thông báo thật.

Canary đo end-to-end latency và phát hiện lỗi ở những đoạn mà health check từng thành phần không nhìn thấy. Nó nên bổ sung cho metrics, không thay thế kiểm tra backlog và business outcomes.

## 14. Ví dụ tình huống: broker UP nhưng đơn hàng bị đình trệ

Giả sử dashboard có các tín hiệu:

| Tín hiệu | Giá trị |
|---|---:|
| Kafka binder health | UP |
| Input rate | 120 events/s |
| Consumer lag | Tăng từ 500 lên 40.000 |
| Processing success | Giảm còn 5 events/s |
| Processing duration p95 | 8 giây |
| Database timeout | Tăng mạnh |
| DLQ ingress | Tăng |

Kết luận phù hợp là kết nối broker vẫn hoạt động, nhưng pipeline nghiệp vụ không theo kịp input. Điều tra nên tập trung vào database pool, timeout, concurrency và chính sách retry. Restart consumer không chắc giải quyết được nguyên nhân nếu database vẫn quá tải.

Một tình huống khác:

| Tín hiệu | Giá trị |
|---|---:|
| Rabbit binder health | UP |
| Queue ready | 15.000 |
| Consumer count | 0 |
| Business success | 0 |
| DLQ ingress | 0 |

Kết nối broker có thể đang mở, nhưng queue không có consumer. Kiểm tra binding name, function definition, listener lifecycle, group và log khởi tạo consumer.

Cuối cùng, nếu broker UP, input rate bằng 0, queue ready bằng 0, lag bằng 0 và không có lịch phát sự kiện trong khoảng đó, dịch vụ có thể đang idle bình thường. Không cảnh báo chỉ vì không có success mới nếu không có công việc cần xử lý.

## 15. Thiết kế SLI và SLO cho pipeline

SLI cần đo trải nghiệm hoặc kết quả mà hệ thống cung cấp. Một pipeline sự kiện có thể chọn:

- Processing success ratio: tỷ lệ event hợp lệ hoàn tất nghiệp vụ.
- End-to-end latency: thời gian từ event phát sinh đến khi kết quả hoàn tất.
- Oldest pending age: tuổi công việc chưa xử lý.
- DLQ rate: tỷ lệ event bị chuyển khỏi luồng chính.
- Data freshness: độ mới của trạng thái downstream so với nguồn.

Ví dụ SLO minh họa:

| SLI | Mục tiêu ví dụ | Cửa sổ đánh giá |
|---|---:|---|
| Event hợp lệ hoàn tất thành công | 99,9% | 30 ngày |
| End-to-end latency p95 | Dưới 30 giây | 7 ngày |
| Oldest pending age | Dưới 2 phút | Liên tục |
| Event vào DLQ do lỗi kỹ thuật | Dưới 0,1% | 7 ngày |

Các con số này chỉ là ví dụ. Mục tiêu thật phải dựa trên yêu cầu nghiệp vụ, tải, dependency và khả năng phục hồi. Không đặt SLO chỉ dựa trên khả năng của broker; một broker có uptime cao không đảm bảo trạng thái đơn hàng được cập nhật đúng hạn.

Khi tính success ratio, cần xác định đơn vị là lần delivery hay event logic duy nhất. Retry có thể tạo nhiều lần gọi handler cho một event; nếu mẫu số và tử số không cùng đơn vị, tỷ lệ sẽ gây hiểu nhầm. Có thể dùng eventId để deduplicate kết quả nghiệp vụ ở nơi lưu trạng thái hoàn tất.

## 16. Checklist triển khai quan sát

- [ ] Bật Actuator health và các probe phù hợp.
- [ ] Quan sát binder health riêng cho từng broker/binder.
- [ ] Không đưa broker availability vào liveness nếu điều đó có thể gây restart loop.
- [ ] Theo dõi consumer count, assignment, lag hoặc queue/subscription backlog.
- [ ] Theo dõi input rate và output rate.
- [ ] Đo processing success, failure và duration tại ranh giới nghiệp vụ.
- [ ] Theo dõi oldest pending age và end-to-end latency.
- [ ] Theo dõi retry, redelivery, DLQ và parking-lot.
- [ ] Phân loại lỗi connectivity, delivery, serialization, dependency và business rule.
- [ ] Dùng correlation ID, event ID và trace context trong log/tracing.
- [ ] Tránh metric tag có cardinality cao.
- [ ] Có cảnh báo phân biệt idle bình thường với backlog không tiến triển.
- [ ] Bổ sung canary event nếu cần kiểm tra toàn tuyến.
- [ ] Đặt SLI/SLO theo kết quả nghiệp vụ và thời hạn xử lý.
- [ ] Kiểm thử dashboard/alert bằng cách mô phỏng broker down, consumer dừng, dependency chậm và message lỗi.

## Tài liệu tham khảo chính thức

- [Spring Cloud Stream - Health Indicator](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/health-indicator.html): health indicator và trạng thái binder.
- [Spring Boot Actuator - Endpoints](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html): health, metrics và cách expose endpoint.
- [Spring Boot Actuator - Kubernetes Probes](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html#actuator.endpoints.kubernetes-probes): liveness và readiness cho Kubernetes.
- [Micrometer Documentation](https://docs.micrometer.io/micrometer/reference/): metrics, Timer, Counter, registry và quy tắc instrument ứng dụng.
- [Apache Kafka Monitoring](https://kafka.apache.org/documentation/#monitoring): consumer lag, producer/consumer metrics và giám sát broker.
- [RabbitMQ Monitoring](https://www.rabbitmq.com/docs/monitoring): queue, connection, consumer và broker metrics.
- [Apache Pulsar Monitoring](https://pulsar.apache.org/docs/next/administration-metrics/): broker, topic, subscription và backlog metrics.
