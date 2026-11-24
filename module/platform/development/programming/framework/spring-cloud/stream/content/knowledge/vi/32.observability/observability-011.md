# Giới hạn nhãn metric có độ đa dạng cao

Trong hệ thống Spring Cloud Stream, mỗi message có thể mang event ID, correlation ID, tenant ID, customer ID, topic, partition, routing key và nhiều header khác. Những giá trị này rất hữu ích khi điều tra một message cụ thể, nhưng không phải tất cả đều phù hợp để đưa vào nhãn (tag/label) của metric.

**Cardinality** là số lượng giá trị khác nhau mà một chiều dữ liệu có thể nhận. Metric có cardinality cao khi nhãn có quá nhiều giá trị hoặc gần như không giới hạn. Nếu mỗi message tạo ra một giá trị nhãn mới, Micrometer phải đăng ký thêm meter và hệ thống metrics backend phải lưu thêm time series. Hệ quả có thể là tăng bộ nhớ, CPU, kích thước dữ liệu scrape/remote write, chi phí lưu trữ và độ trễ truy vấn.

Quy tắc thiết kế quan trọng: metric dùng để tổng hợp và so sánh theo một tập chiều dữ liệu nhỏ, ổn định; log và distributed trace dùng để tra cứu từng event, request hoặc message cụ thể. Spring Cloud Stream tích hợp Micrometer Observation, vì vậy có thể giữ các chiều có cardinality thấp cho metrics và đưa dữ liệu có cardinality cao vào trace.

## 1. Cardinality và time series là gì?

Một metric là phép đo như số message đã xử lý, thời gian xử lý, số lần retry hoặc kích thước batch. Tag bổ sung chiều phân loại cho phép truy vấn metric theo binding, outcome, binder hoặc môi trường.

Ví dụ metric:

~~~text
stream.messages.processed{binding="orders-in-0", outcome="success"} 1250
stream.messages.processed{binding="orders-in-0", outcome="error"} 12
~~~

Hai tổ hợp tag khác nhau tạo ra hai meter riêng trong Micrometer. Với counter/gauge đơn giản, mỗi meter thường tương ứng một time series trong Prometheus; timer/histogram có thể tạo thêm nhiều series cho bucket, sum và count. Trong Prometheus, mỗi tổ hợp duy nhất của tên metric và các cặp label key/value tạo ra một time series.

Cardinality của một nhãn là số giá trị khác nhau mà nhãn đó có thể nhận. Cardinality của metric còn phụ thuộc vào tổ hợp của tất cả nhãn. Nếu một metric có:

- 4 binding.
- 3 binder.
- 4 outcome.
- 6 instance.

Số tổ hợp tối đa về mặt lý thuyết là:

\[
4 \times 3 \times 4 \times 6 = 288
\]

Không phải mọi tổ hợp đều nhất thiết xuất hiện, nhưng tích số này giúp ước lượng giới hạn trên. Nếu thêm nhãn `eventId` có 100.000 giá trị khác nhau, số tổ hợp lý thuyết tăng lên:

\[
288 \times 100\,000 = 28\,800\,000
\]

Chỉ một nhãn theo từng message có thể làm số time series tăng từ vài trăm lên hàng chục triệu.

~~~mermaid
flowchart TD
    A[Metric: stream.messages.processed] --> B[Tag binding: 4 giá trị]
    A --> C[Tag outcome: 4 giá trị]
    A --> D[Tag instance: 6 giá trị]
    A --> E[Tag eventId: 100.000 giá trị]
    B --> F[Tổ hợp tag tạo time series]
    C --> F
    D --> F
    E --> F
    F --> G[Cardinality và chi phí tăng mạnh]
~~~

Cardinality không phải số sample được ghi trong một phút. Một time series có thể nhận hàng triệu sample theo thời gian mà cardinality vẫn bằng một. Ngược lại, một metric chỉ được cập nhật một lần cho mỗi event vẫn có cardinality rất cao nếu mỗi event tạo ra một bộ tag khác nhau.

## 2. Vì sao cardinality cao gây vấn đề?

Mỗi meter trong Micrometer được định danh bằng tên, kiểu và tập tag. Khi tag thay đổi, registry có thể phải đăng ký một meter mới. Với Prometheus, backend lưu mỗi tổ hợp label thành một time series riêng.

Cardinality cao tác động ở nhiều lớp:

1. **Trong ứng dụng:** registry giữ thêm meter và cấu trúc dữ liệu; đăng ký meter liên tục làm tăng allocation, bộ nhớ và chi phí CPU.
2. **Khi export:** endpoint scrape hoặc exporter phải duyệt và serialize nhiều series hơn; payload metrics lớn hơn.
3. **Trong backend:** Prometheus/remote storage phải tạo index, giữ metadata, nén và truy vấn nhiều series hơn.
4. **Trong dashboard:** truy vấn group-by, aggregation và join trên tập series lớn có thể chậm hoặc tốn tài nguyên.
5. **Trong chi phí vận hành:** nhiều nền tảng tính phí theo số series, sample hoặc dung lượng ingest; cardinality tăng có thể làm chi phí tăng nhanh.
6. **Trong khả năng cảnh báo:** alert rule phải đánh giá nhiều series hơn và có thể tạo quá nhiều alert instance.

Timer và histogram còn khuếch đại tác động. Mỗi tổ hợp tag của histogram có thể sinh nhiều bucket series cùng các series sum/count. Số bucket phụ thuộc cấu hình registry/backend; vì vậy một timer có nhãn cardinality cao thường tốn kém hơn một counter đơn giản có cùng tổ hợp tag.

## 3. Nhãn nào phù hợp với metric xử lý message?

Một tag tốt có tập giá trị hữu hạn, ổn định và có ý nghĩa khi tổng hợp. Với Spring Cloud Stream, có thể bắt đầu bằng các chiều sau:

| Tag | Ví dụ giá trị | Đánh giá | Lý do |
|---|---|---|---|
| `binding` | `orders-in-0`, `orders-out-0` | Thường phù hợp | Binding name được khai báo trong cấu hình ứng dụng. |
| `binder` | `kafka`, `rabbit`, `pulsar` | Phù hợp | Số loại binder thường nhỏ và được kiểm soát. |
| `outcome` | `success`, `retry`, `error`, `discarded` | Phù hợp | Tập trạng thái hữu hạn do ứng dụng định nghĩa. |
| `error_category` | `validation`, `timeout`, `serialization`, `other` | Phù hợp | Nhóm lỗi ổn định, không chứa nội dung lỗi tự do. |
| `exception` | `IllegalArgumentException`, `TimeoutException` | Có điều kiện | Tên class thường hữu hạn trong code; không dùng exception message. |
| `destination` | `orders.created`, `orders.validated` | Có điều kiện | Phù hợp nếu destination là danh sách tĩnh, hữu hạn. |
| `partition` | `0`, `1`, `2` | Có điều kiện | Số partition hữu hạn, nhưng kết hợp với nhiều topic/instance có thể tăng tổng series. |
| `consumer_group` | `order-projection` | Có điều kiện | Hợp lý nếu group được cấu hình tĩnh; không dùng group sinh theo request/tenant. |
| `region` | `ap-southeast-1`, `ap-northeast-1` | Thường phù hợp | Tập region thường nhỏ và ổn định. |
| `event_id` | `evt-8f3...` | Không phù hợp | Mỗi message có thể có ID riêng. |
| `correlation_id` | `corr-...` | Không phù hợp | Gần như duy nhất cho từng luồng request/message. |
| `trace_id`, `span_id` | ID của trace/span | Không phù hợp | Giá trị mới liên tục; dùng trace để tra cứu. |
| `customer_id`, `user_id`, `tenant_id` | ID của từng khách hàng | Thường không phù hợp | Tập giá trị lớn, thay đổi theo dữ liệu nghiệp vụ. |
| `exception_message` | Nội dung exception | Không phù hợp | Nội dung tự do, có thể chứa ID, URL, input hoặc secret. |
| `payload`, `routing_key` tùy ý | Nội dung message hoặc header | Không phù hợp | Có thể thay đổi theo từng message. |
| `timestamp` | Thời điểm từng event | Không phù hợp | Gần như mỗi message có một giá trị khác. |

Một tag không tự động an toàn chỉ vì nó là số hoặc chuỗi ngắn. `tenant_id` có thể có hàng trăm nghìn giá trị; `partition` có thể có vài giá trị. Hãy xem xét số giá trị thực tế, số tổ hợp với các tag khác và nhu cầu truy vấn.

## 4. Cardinality trong Spring Cloud Stream

Các luồng message thường có một số nguồn phát sinh nhãn cardinality cao:

### 4.1. Gắn event ID hoặc correlation ID vào custom counter

Đoạn code sau tạo meter riêng cho từng event:

~~~java
registry.counter(
    "stream.messages.processed",
    "eventId",
    event.eventId()
).increment();
~~~

Nếu 500.000 message có 500.000 event ID khác nhau, registry có thể giữ khoảng 500.000 meter cùng tên. Đưa event ID vào log hoặc trace để tìm đúng message; counter chỉ nên có tag như binding và outcome.

### 4.2. Destination động từ StreamBridge

`StreamBridge` có thể tạo output binding cho destination được xác định khi chạy. Điều này hữu ích khi ứng dụng gửi message tới một số destination khác nhau. Tuy nhiên, nếu destination được tạo từ tenant ID, customer ID hoặc giá trị request tùy ý, việc dùng destination làm tag có thể tạo một series mới cho mỗi tenant/request.

Không nên thêm trực tiếp destination động vào mọi metric. Có thể phân loại destination theo nhóm nghiệp vụ hữu hạn, ví dụ `orders`, `audit`, `notification`, `other`; đồng thời log destination thật hoặc ghi nó vào trace khi cần điều tra.

### 4.3. Consumer group và partition

Tên consumer group và partition có thể là chiều quan sát hữu ích. Tuy nhiên, nếu mỗi tenant hoặc mỗi request tạo một consumer group mới, tag `consumer_group` không còn có cardinality thấp. Tương tự, partition là chiều hữu hạn trong một topic nhưng tổ hợp `topic × partition × instance × outcome` có thể tăng đáng kể khi số topic và replica lớn.

Chỉ đưa partition vào metric khi dashboard hoặc cảnh báo thực sự cần theo dõi từng partition. Nếu mục tiêu là throughput tổng thể của binding, hãy aggregate theo binding và outcome.

### 4.4. Exception và header

Không dùng `exception.getMessage()` làm tag. Message có thể chứa order ID, URL, SQL, tên file hoặc input gây lỗi. Tên exception class thường có tập giá trị nhỏ hơn, nhưng nên chuẩn hóa thành `error_category` do ứng dụng kiểm soát nếu có nhiều loại exception hoặc thư viện bên ngoài.

Header message cũng không mặc nhiên là tag metric. Các header như `eventId`, `traceparent`, `x-correlation-id`, `tenant`, `user-agent` hoặc `routingKey` thường chứa giá trị thay đổi liên tục. Chỉ trích xuất những thuộc tính có tập giá trị nhỏ, được xác thực và có nhu cầu tổng hợp.

## 5. Tính cardinality trước khi thêm tag

Trước khi thêm một tag, ước lượng:

- Tag đó có bao nhiêu giá trị khác nhau trong một instance?
- Có bao nhiêu instance của ứng dụng?
- Có bao nhiêu binding, destination, group và outcome?
- Metric là counter, gauge, timer hay histogram?
- Backend giữ dữ liệu trong bao lâu?
- Có cần truy vấn riêng theo chiều đó hay chỉ cần tìm một event cụ thể?

Ví dụ một metric xử lý message có 5 binding, 4 outcome và 8 instance. Nếu thêm 20 destination tĩnh, số series tối đa lý thuyết là:

\[
5 \times 4 \times 8 \times 20 = 3\,200
\]

Nếu destination trở thành 10.000 tenant destination:

\[
5 \times 4 \times 8 \times 10\,000 = 1\,600\,000
\]

Đây mới chỉ là một metric; nếu có thêm timer histogram, retry metrics và nhiều meter khác, tổng số series sẽ còn cao hơn. Số liệu là ước lượng theo tổ hợp tối đa; thực tế phụ thuộc các tổ hợp đã phát sinh.

Một nguyên tắc thực dụng là đặt ngân sách cardinality cho mỗi metric family. Mỗi tag mới phải có chủ sở hữu, tập giá trị dự kiến và lý do truy vấn. Không thêm tag chỉ vì giá trị có sẵn trong message.

## 6. Thiết kế tag có tập giá trị hữu hạn

Thay vì truyền chuỗi tùy ý, hãy chuyển giá trị đầu vào sang enum hoặc nhóm trạng thái:

~~~java
enum ProcessingOutcome {
    SUCCESS,
    VALIDATION_ERROR,
    TRANSIENT_ERROR,
    OTHER_ERROR
}

enum DestinationGroup {
    ORDERS,
    AUDIT,
    NOTIFICATIONS,
    OTHER
}
~~~

Hàm phân loại:

~~~java
DestinationGroup classifyDestination(String destination) {
    if (destination == null) {
        return DestinationGroup.OTHER;
    }
    if (destination.startsWith("orders.")) {
        return DestinationGroup.ORDERS;
    }
    if (destination.startsWith("audit.")) {
        return DestinationGroup.AUDIT;
    }
    if (destination.startsWith("notifications.")) {
        return DestinationGroup.NOTIFICATIONS;
    }
    return DestinationGroup.OTHER;
}
~~~

Ghi counter với tag đã chuẩn hóa:

~~~java
registry.counter(
    "stream.messages.processed",
    "binding", "orders-in-0",
    "destination_group", classifyDestination(destination).name(),
    "outcome", outcome.name().toLowerCase(Locale.ROOT)
).increment();
~~~

Tập tag có thể dự đoán trước: binding được cấu hình tĩnh, destination group có bốn giá trị, outcome có bốn giá trị. Không có event ID hoặc destination tùy ý trong meter identity.

Nếu cần giữ destination thật, ghi destination vào log có cấu trúc hoặc span/trace. Khi cần báo cáo theo tenant, cân nhắc bảng phân tích hoặc hệ thống analytics chuyên dụng thay vì biến metric time series thành kho dữ liệu theo từng tenant.

## 7. Đăng ký custom metric bằng Micrometer

Spring Boot Actuator tự cấu hình `MeterRegistry` và Micrometer. Có thể inject registry vào component để tạo counter, timer hoặc gauge.

Ví dụ component ghi số message:

~~~java
import io.micrometer.core.instrument.MeterRegistry;
import org.springframework.stereotype.Component;

import java.util.Locale;

@Component
class StreamMetrics {

    private final MeterRegistry registry;

    StreamMetrics(MeterRegistry registry) {
        this.registry = registry;
    }

    void recordProcessed(String binding, ProcessingOutcome outcome) {
        registry.counter(
            "stream.messages.processed",
            "binding", binding,
            "outcome", outcome.name().toLowerCase(Locale.ROOT)
        ).increment();
    }
}
~~~

Micrometer nhận diện meter bằng tên và tập tag. Khi tên và tag giống nhau, registry tái sử dụng meter đã đăng ký; khi tag value thay đổi, registry cần meter khác. Vì vậy `binding` và `outcome` trong ví dụ phải lấy từ tập giá trị được kiểm soát.

Không viết:

~~~java
void recordProcessed(OrderEvent event) {
    registry.counter(
        "stream.messages.processed",
        "eventId", event.eventId(),
        "customerId", event.customerId()
    ).increment();
}
~~~

Đoạn code trên tạo meter theo từng tổ hợp event/customer. Khi traffic tăng, số meter có thể tăng gần tuyến tính theo số event.

Nếu có số tổ hợp tag cố định và được gọi rất thường xuyên, có thể đăng ký trước Counter/Timer khi khởi tạo bean rồi tái sử dụng. Dù đăng ký trước hay dùng `registry.counter(...)` mỗi lần, điều quan trọng vẫn là tag set phải ổn định và hữu hạn.

## 8. Đưa dữ liệu cardinality cao vào Observation và trace

Micrometer Observation phân biệt low-cardinality và high-cardinality key-value:

- Low-cardinality key-value được dùng để tạo metric tags và cũng có thể xuất hiện trong trace.
- High-cardinality key-value không được dùng làm metric tags; chúng dành cho trace hoặc handler khác có thể xử lý dữ liệu chi tiết.

Ví dụ một observation xử lý message:

~~~java
Observation.createNotStarted("stream.message.process", observationRegistry)
    .lowCardinalityKeyValue("binding", "orders-in-0")
    .lowCardinalityKeyValue("outcome", "success")
    .lowCardinalityKeyValue("binder", "kafka")
    .highCardinalityKeyValue("eventId", event.eventId())
    .highCardinalityKeyValue("correlationId", correlationId)
    .observe(() -> orderService.process(event));
~~~

Ở đây metrics có thể tổng hợp theo binding, outcome và binder. Trace có thể chứa event ID/correlation ID để tìm một lần xử lý cụ thể, nếu tracing handler được cấu hình.

Không nên chuyển toàn bộ dữ liệu nhạy cảm sang trace chỉ vì trace chấp nhận cardinality cao. Trace vẫn có chi phí ingest/storage và có thể chứa dữ liệu cá nhân. Không thêm password, access token, email hoặc payload bí mật; áp dụng masking, retention và quyền truy cập phù hợp.

Nếu ứng dụng đã có Observation do Spring Cloud Stream tạo cho function invocation, hãy xem xét convention/context hiện có trước khi tạo thêm một Observation cho cùng thao tác. Chỉ tạo observation lồng nhau khi cần đo một operation con có ý nghĩa riêng.

## 9. Observability của Spring Cloud Stream

Spring Cloud Stream tích hợp Micrometer Observation ở cấp Spring Cloud Function:

- Với imperative function, framework có thể bọc function bằng `ObservationFunctionAroundWrapper`. Khi các dependency observability cần thiết có mặt, mỗi lần function được gọi (thường tương ứng một message) có một observation.
- Với reactive function, function là bước khởi tạo stream và được gọi khi ứng dụng khởi động. Framework không thể mặc định coi mỗi item trong Flux là một invocation độc lập; cần gắn observation vào đoạn xử lý reactive một cách chủ động.

Các dependency thường dùng cho observability bao gồm Spring Boot Actuator, `reactor-core-micrometer` trong trường hợp reactive và một tracing bridge phù hợp. Chi tiết dependency và cách bật observation phụ thuộc phiên bản Spring Boot/Spring Cloud.

Ví dụ với Reactor, gắn observation cho từng message bằng `tap`:

~~~java
@Bean
Function<Flux<OrderEvent>, Flux<OrderEvent>> normalize(
        ObservationRegistry observationRegistry) {
    return events -> events
        .flatMap(event -> Mono.just(event)
            .map(this::normalizeOrder)
            .tap(Micrometer.observation(observationRegistry)));
}
~~~

Đoạn ví dụ cho thấy điểm gắn observation; convention/context cần được cấu hình để thêm các low-cardinality tag hữu hạn và high-cardinality metadata phù hợp. Không dùng event ID làm low-cardinality key-value.

## 10. Giữ metric name ổn định

Cardinality không chỉ đến từ tag. Tạo tên metric động cũng làm registry có nhiều meter:

~~~java
// Không nên: tên meter thay đổi theo từng order.
registry.counter("orders." + orderId + ".processed").increment();
~~~

`HighCardinalityTagsDetector` chủ yếu phát hiện nhiều meter có cùng tên do tag; nó không phát hiện mọi trường hợp gắn random value vào tên meter. Vì vậy, luôn dùng tên metric cố định:

~~~java
registry.counter(
    "orders.processed",
    "outcome", "success"
).increment();
~~~

Thông tin biến thiên nên nằm ở tag có tập giá trị hữu hạn, log hoặc trace. Không tạo một metric name cho từng message, khách hàng hoặc destination động.

## 11. Common tags và tag theo môi trường

Spring Boot cho phép cấu hình common tags cho toàn bộ metric:

~~~yaml
management:
  metrics:
    tags:
      application: orders-stream
      environment: production
      region: ap-southeast-1
~~~

Các giá trị như application, environment và region thường có tập giá trị nhỏ, ổn định, hữu ích để so sánh giữa môi trường hoặc vùng triển khai.

Cần cân nhắc tag instance/host/pod:

- Nếu số replica được giới hạn và cần xem từng instance, tag instance có thể hữu ích.
- Nếu mỗi lần restart tạo một ID ngẫu nhiên và backend giữ dữ liệu dài ngày, số instance value tích lũy có thể tăng theo thời gian.
- Không gắn request ID, event ID hoặc container ID theo từng tác vụ vào mọi metric chỉ vì chúng có sẵn.

Common tags được thêm vào tất cả meter, nên một tag có cardinality cao ở cấp toàn ứng dụng có thể làm tăng số series của rất nhiều metric cùng lúc.

## 12. Dùng MeterFilter làm hàng rào bảo vệ

`MeterFilter` có thể chặn meter, biến đổi tên/tag hoặc giới hạn số giá trị tag. Đây là hàng rào bảo vệ khi instrumentation chưa thể sửa ngay, không phải cách thiết kế tag chính.

Ví dụ giới hạn số destination value cho một metric family:

~~~java
import io.micrometer.core.instrument.config.MeterFilter;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class StreamMetricFilterConfiguration {

    @Bean
    MeterFilter limitDestinationTags() {
        return MeterFilter.maximumAllowableTags(
            "stream.messages.processed",
            "destination",
            20,
            MeterFilter.deny()
        );
    }
}
~~~

Filter trên áp dụng cho meter có tên bắt đầu bằng `stream.messages.processed`, giới hạn tối đa 20 giá trị khác nhau của tag `destination`. Khi vượt giới hạn, `MeterFilter.deny()` từ chối đăng ký meter mới; registry trả về NOOP meter và dữ liệu ghi qua meter đó bị bỏ.

**Giới hạn này không tự gom các giá trị vượt ngưỡng thành `other`.** Nếu muốn giữ số liệu tổng hợp, phải chuẩn hóa giá trị trước khi tạo meter, ví dụ ánh xạ destination không nằm trong allowlist thành `other`.

Có thể loại một tag không cần thiết khỏi meter:

~~~java
@Bean
MeterFilter removeEventIdTag() {
    return MeterFilter.ignoreTags("eventId");
}
~~~

`ignoreTags` bỏ tag có tên tương ứng khỏi mọi meter đi qua filter. Vì phạm vi ảnh hưởng là toàn registry, hãy kiểm tra tất cả instrumentation trước khi áp dụng. Nếu tag chỉ cần bỏ ở một nhóm metric, có thể dùng filter có điều kiện theo meter name prefix.

MeterFilter được áp dụng theo thứ tự đăng ký. Một filter `deny` có thể làm meter thành NOOP; một filter biến đổi tag có thể thay đổi identity của meter. Kiểm thử thứ tự và tác động trước khi triển khai.

## 13. Phát hiện cardinality cao bằng Micrometer

Micrometer có `HighCardinalityTagsDetector` để tìm các meter name có số meter vượt ngưỡng. Có thể bật trên registry:

~~~java
registry.config().withHighCardinalityTagsDetector();
~~~

Đặt lời gọi này trong phần cấu hình của Spring-managed `MeterRegistry` (chẳng hạn registry customizer) để detector quan sát đúng registry được export. Hoặc tạo detector với ngưỡng và callback phù hợp theo API của phiên bản Micrometer đang dùng; kiểm tra phiên bản được Spring Boot BOM quản lý trước khi dùng API mới. Detector đếm số meter cùng tên và cảnh báo khi vượt ngưỡng; đây là heuristic để phát hiện khả năng tag cardinality cao.

Detector có giới hạn:

- Nó không phát hiện tên meter bị tạo động theo event ID.
- Nó không phát hiện mọi nguyên nhân tăng bộ nhớ.
- Nó có thể chỉ báo meter đầu tiên vượt ngưỡng; cần xử lý từng metric family.
- Ngưỡng phù hợp phụ thuộc quy mô ứng dụng và backend.

Nên bật detector trong môi trường production hoặc staging có tải gần thực tế, đồng thời kiểm thử instrumentation để phát hiện lỗi trước khi phát hành. Không chỉ tăng ngưỡng khi có cảnh báo; cần tìm tag hoặc meter name gây tăng trưởng.

## 14. Kiểm tra cardinality bằng Prometheus

Nếu dùng Prometheus, có thể xem số series theo metric name:

~~~promql
count by (__name__) ({job="orders-stream"})
~~~

Để xem những metric family có nhiều series nhất:

~~~promql
topk(20, count by (__name__) ({job="orders-stream"}))
~~~

Nếu metric có tag `destination`, có thể xem số series theo destination:

~~~promql
count by (destination) (stream_messages_processed_total)
~~~

Tên metric trong Prometheus có thể khác tên Micrometer do quy tắc chuẩn hóa và hậu tố counter/timer. Hãy thay bằng tên thực tế được export trong hệ thống.

Khi điều tra, tìm:

- Metric family tăng series nhanh bất thường.
- Tag value là UUID, timestamp, URL đầy đủ, email hoặc ID nghiệp vụ.
- Destination/group được tạo động.
- Metric name thay đổi theo event hoặc tenant.
- Histogram có nhiều bucket kết hợp với tag cardinality cao.
- Số series cũ còn tồn tại theo retention dù instance hoặc destination đã bị xóa.

Spring Boot Actuator `/actuator/metrics` cho phép xem meter name và lọc theo tag trong registry của ứng dụng. Endpoint metrics không được expose qua HTTP mặc định; chỉ expose khi cần và bảo vệ bằng authentication/network policy phù hợp. Endpoint này hữu ích để kiểm tra meter được đăng ký ở phía ứng dụng; backend Prometheus mới cho thấy series thực tế sau khi scrape và chuyển đổi naming convention.

## 15. Kiểm thử instrumentation không tạo meter theo từng event

Nên có test chứng minh nhiều event khác ID vẫn dùng chung một tập meter hữu hạn:

~~~java
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;

class StreamMetricsTest {

    @Test
    void reusesMetersForManyEvents() {
        SimpleMeterRegistry registry = new SimpleMeterRegistry();

        for (int i = 0; i < 1_000; i++) {
            registry.counter(
                "stream.messages.processed",
                "binding", "orders-in-0",
                "outcome", "success"
            ).increment();
        }

        assertThat(registry.getMeters()).hasSize(1);
        assertThat(registry.get("stream.messages.processed")
            .tag("binding", "orders-in-0")
            .tag("outcome", "success")
            .counter()
            .count()).isEqualTo(1_000);

        registry.close();
    }
}
~~~

Test này tạo 1.000 lần cập nhật cùng một meter identity. Có thể mở rộng với một số outcome hữu hạn và xác minh số meter bằng đúng số tổ hợp dự kiến.

Để thấy anti-pattern, thay tag `outcome` bằng `eventId` duy nhất cho từng vòng lặp; registry sẽ đăng ký nhiều meter. Không đưa anti-pattern vào production chỉ để kiểm thử; có thể kiểm tra trên SimpleMeterRegistry trong test cô lập.

Ngoài số meter, cần kiểm tra:

- Tag values luôn thuộc enum/allowlist.
- Destination không xác định được ánh xạ thành `other`.
- Exception message không được đưa vào tag.
- Metric name không chứa ID động.
- Histogram chỉ bật cho metric cần thiết.
- Observation đưa ID chi tiết vào high-cardinality metadata, không phải low-cardinality key-value.

## 16. Lưu ý khi dùng histogram và timer

Timer đo thời gian xử lý message thường hữu ích:

~~~java
Timer.builder("stream.message.processing")
    .tag("binding", "orders-in-0")
    .tag("outcome", "success")
    .register(registry)
    .record(() -> orderService.process(event));
~~~

Không thêm event ID hoặc customer ID vào timer. Mỗi tag set có thể tạo một timer riêng; nếu bật percentile histogram hoặc SLO buckets, mỗi timer còn tạo thêm chuỗi dữ liệu ở backend.

Chỉ bật percentile histogram khi cần truy vấn percentile có thể aggregate ở backend và đã ước lượng số bucket/series. Nếu cần latency theo từng message, dùng trace/span; timer metric nên trả lời câu hỏi tổng hợp như p95 latency theo binding/outcome.

## 17. Tách metrics, logs và traces theo mục tiêu

| Nhu cầu | Công cụ phù hợp | Ví dụ dữ liệu |
|---|---|---|
| Có bao nhiêu message thành công/thất bại? | Counter metric | binding, binder, outcome |
| Thời gian xử lý p95 của binding? | Timer/histogram | binding, outcome |
| Consumer group nào đang lag? | Broker/binder metric | topic, group, partition có giới hạn |
| Event `evt-123` bị lỗi ở bước nào? | Log có cấu trúc hoặc trace | event ID, correlation ID, exception detail |
| Một request đi qua những service nào? | Distributed trace | trace ID, span ID, event ID phù hợp |
| Lỗi nào tăng theo nhóm nghiệp vụ? | Metric với error category | validation, timeout, serialization |
| Payload nào gây lỗi? | Log/DLQ có kiểm soát | payload hoặc bản tham chiếu đã che dữ liệu nhạy cảm |

Metrics phải có khả năng tổng hợp và cảnh báo. Logs/traces phục vụ drill-down. Không dùng metric backend như một cơ sở dữ liệu để lưu mọi event ID.

## 18. Quy trình xử lý khi phát hiện cardinality tăng

1. Xác định metric family tăng nhanh bằng dashboard/backend query.
2. Xem danh sách tag key và một mẫu tag value để nhận ra ID, URL, timestamp hoặc destination động.
3. Kiểm tra nơi tạo meter: custom MeterRegistry, ObservationConvention, binder instrumentation hoặc common tags.
4. Xác định chiều đó có cần thiết cho aggregation/alert hay chỉ dùng để tìm một event.
5. Nếu cần phân tích tổng hợp, chuẩn hóa thành enum, category, template hoặc range.
6. Nếu cần điều tra chi tiết, chuyển giá trị sang trace/log và áp dụng masking/retention.
7. Nếu không cần, bỏ tag khỏi instrumentation hoặc dùng MeterFilter làm biện pháp tạm thời.
8. Kiểm thử số meter và số series trước khi phát hành.
9. Theo dõi lại cardinality, memory và ingest rate sau khi triển khai.
10. Ghi rõ ngân sách tag và quy tắc cho metric mới trong review instrumentation.

Khi cần chặn khẩn cấp, `maximumAllowableTags` có thể bảo vệ registry/backend, nhưng các meter vượt giới hạn sẽ bị từ chối và số liệu tương ứng bị mất. Hãy sửa nguồn instrumentation và gỡ hàng rào tạm thời khi không còn cần thiết.

## 19. Lỗi thường gặp

1. Thêm `eventId`, `traceId` hoặc `customerId` vào tag để tìm message. Dùng trace/log cho việc này.
2. Dùng exception message làm tag. Message có thể thay đổi và chứa dữ liệu không giới hạn.
3. Tạo metric name có chứa ID. MeterFilter theo tag không giải quyết được tên meter động.
4. Đưa destination động của StreamBridge vào metric mà không giới hạn tập giá trị.
5. Dùng tenant ID làm tag chỉ vì số tenant hiện tại còn ít; cần xem tăng trưởng và retention dài hạn.
6. Thêm partition và instance vào mọi metric dù dashboard chỉ cần số tổng.
7. Cho rằng counter không có histogram nên tag cardinality không gây tốn kém.
8. Bật histogram cho metric có nhiều chiều mà chưa tính số bucket/series.
9. Nghĩ `maximumAllowableTags` sẽ gom tag vượt ngưỡng thành `other`; mặc định `deny` làm meter mới thành NOOP.
10. Dùng `ignoreTags` toàn registry mà không kiểm tra các metric khác phụ thuộc tag đó.
11. Chỉ kiểm tra số sample/giây mà bỏ qua số time series đang tồn tại.
12. Tăng ngưỡng detector nhưng không tìm nguyên nhân gốc.
13. Đưa dữ liệu nhạy cảm vào trace vì cho rằng trace không có chi phí hoặc không cần bảo vệ.
14. Dùng metric để lưu từng event thay vì dùng log, trace hoặc hệ thống phân tích sự kiện.

## 20. Checklist thiết kế metric cho Spring Cloud Stream

- [ ] Tên metric cố định, không chứa event ID, tenant ID hoặc destination động.
- [ ] Mỗi tag có tập giá trị hữu hạn và được kiểm soát.
- [ ] `binding`, `binder`, `outcome`, `error_category` có giá trị chuẩn hóa.
- [ ] `destination`, `consumer_group`, `partition` chỉ được thêm khi có nhu cầu và ngân sách cardinality.
- [ ] Không dùng event ID, correlation ID, trace ID, user/customer ID hoặc payload làm metric tag.
- [ ] Exception tag dùng class/category ổn định, không dùng exception message.
- [ ] Common tags như application, environment và region có giá trị ổn định.
- [ ] Destination động được ánh xạ thành nhóm hữu hạn trước khi ghi metric.
- [ ] Histogram/timer có số bucket và tổ hợp tag phù hợp.
- [ ] High-cardinality metadata được đưa vào trace/log theo chính sách dữ liệu.
- [ ] MeterFilter chỉ là hàng rào bảo vệ; hiểu rõ meter bị deny sẽ mất số liệu.
- [ ] Có kiểm thử số meter với nhiều event ID khác nhau.
- [ ] Có dashboard/alert theo dõi số series và detector trong môi trường phù hợp.
- [ ] Metric mới có ngân sách cardinality và mục đích truy vấn được ghi nhận.

Giới hạn nhãn metric có độ đa dạng cao giúp hệ thống quan sát giữ được khả năng tổng hợp khi lưu lượng message tăng. Trong Spring Cloud Stream, hãy dùng các chiều ổn định như binding, binder, outcome và nhóm lỗi cho metrics; giữ event ID, correlation ID và dữ liệu theo từng message trong trace/log. Kết hợp tag normalization, MeterFilter guardrail, detector và kiểm thử instrumentation sẽ giúp phát hiện sớm cardinality explosion mà vẫn giữ đủ thông tin để điều tra sự cố.

## Tài liệu tham khảo

- [Spring Cloud Stream – Observability](https://docs.spring.io/spring-cloud-stream/reference/observability.html)
- [Spring Boot – Actuator Metrics](https://docs.spring.io/spring-boot/reference/actuator/metrics.html)
- [Micrometer – High Cardinality Tags Detector](https://docs.micrometer.io/micrometer/reference/concepts/high-cardinality-tags-detector.html)
- [Micrometer – Meter Filters](https://docs.micrometer.io/micrometer/reference/concepts/meter-filters.html)
- [Micrometer – Observation Introduction](https://docs.micrometer.io/micrometer/reference/observation/introduction.html)
- [Prometheus – Metric and Label Naming](https://prometheus.io/docs/practices/naming/)
