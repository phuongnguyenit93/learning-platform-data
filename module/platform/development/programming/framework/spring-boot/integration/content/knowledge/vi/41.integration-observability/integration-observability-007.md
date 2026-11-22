# Đo lỗi, số lần thử lại và số thông điệp bị chuyển dead-letter

## 1. Bối cảnh: quan sát một luồng tích hợp có thất bại

Trong module **SPRING_BOOT_INTEGRATION**, Spring Boot được dùng để kết nối hệ thống qua HTTP client, cơ sở dữ liệu, cache, broker thông điệp và các adapter Spring Integration. Những luồng này phải quản lý cấu hình, hợp đồng dữ liệu, giao dịch, lỗi, xử lý trùng lặp, kiểm thử và khả năng quan sát. Một request HTTP trả lỗi, một consumer xử lý lại thông điệp, hoặc một bản tin đi vào dead-letter đều có ảnh hưởng đến chất lượng nghiệp vụ nhưng **không thể đo bằng cùng một bộ đếm mơ hồ tên là errors**.

Ví dụ flow nhận thông điệp **OrderPaid** từ RabbitMQ hoặc Kafka:

~~~mermaid
flowchart TD
    A["Broker / inbound adapter"] --> B["Nhận một lần giao message"]
    B --> C["Validate + xử lý nghiệp vụ"]
    C --> D{"Kết quả xử lý"}
    D -->|"Thành công"| E["Commit/ACK phù hợp"]
    D -->|"Lỗi tạm thời"| F["Retry có giới hạn"]
    F --> C
    D -->|"Lỗi không thể retry"| G["Xử lý thất bại cuối cùng"]
    F -->|"Hết retry"| G
    G --> H{"Chính sách phục hồi"}
    H -->|"Dead-letter có xác nhận"| I["DLQ hoặc DLT"]
    H -->|"Không gửi được"| J["Lỗi phát lại / sự cố cần xử lý"]
    H -->|"Giữ để xử lý lại"| K["Requeue / error flow"]
~~~

Một lần giao có thể thất bại ở lần thực thi đầu nhưng thành công sau retry. Bởi vậy phải trả lời riêng:

1. **Bao nhiêu lần xử lý thực sự lỗi?**
2. **Bao nhiêu lần retry thực sự diễn ra?**
3. **Bao nhiêu lần giao hoặc sự kiện kết thúc bằng thất bại?**
4. **Bao nhiêu thông điệp đã thực sự đến dead-letter queue/topic?**

Mục tiêu bài học:

- Xác định đúng sự kiện cần đếm, thời điểm tăng counter và phạm vi số liệu.
- Dùng Micrometer, Spring Boot Actuator và khả năng quan sát sẵn có của Spring Integration.
- Gắn bộ đếm cho retry, final failure, dead-letter và recovery mà không làm thay đổi semantics của broker.
- Thiết kế dashboard, cảnh báo, log/trace và kiểm thử chứng minh metric đúng.
- Phân biệt lỗi ứng dụng, lỗi giao nhận, redelivery, poison message, trùng lặp và quá tải downstream.

## 2. Phân biệt message, delivery, attempt và outcome

Trước khi đặt tên metric, cần có từ điển thống nhất:

| Đơn vị | Ý nghĩa | Một sự kiện có thể sinh ra bao nhiêu? |
| --- | --- | --- |
| **Business event** | Sự kiện logic theo eventId hoặc operationId nghiệp vụ | Một |
| **Delivery** | Một lần broker/adapter giao event cho ứng dụng | Một hoặc nhiều lần do redelivery |
| **Processing attempt** | Một lần chạy logic xử lý, bao gồm attempt đầu và mỗi retry | Một hoặc nhiều lần trong một delivery |
| **Retry started** | Một attempt tiếp theo được thực thi sau khi attempt trước thất bại | Từ 0 đến giới hạn retry |
| **Attempt failure** | Một lần thực thi handler ném lỗi | Có thể nhiều hơn một cho cùng delivery |
| **Final failure** | Một delivery kết thúc không thành công sau chính sách retry | Thường tối đa một kết quả cuối cho delivery |
| **Dead-letter intent** | Ứng dụng quyết định gửi hoặc từ chối message theo hướng DLQ/DLT | Không chứng minh broker đã nhận |
| **Dead-letter confirmed** | Có bằng chứng publish thành công hoặc sự kiện broker route được xác nhận phù hợp | Không đồng nghĩa consumer DLQ đã xử lý |
| **Dead-letter observed** | Một consumer hoặc nguồn metric broker quan sát message tại DLQ/DLT | Có thể lặp nếu message DLQ cũng bị redeliver |

**Received delivery ≠ unique business event**: nếu broker giao cùng eventId ba lần, counter nhận của adapter có thể tăng ba. Muốn đếm số event duy nhất, cần trạng thái dedupe/idempotency hoặc một phép đếm trên nguồn sự thật có bảo đảm tương ứng.

### Ví dụ số học

Trong 5 phút, có 100 delivery vào ứng dụng:

- 60 delivery xử lý thành công ngay lần đầu.
- 30 delivery lỗi lần đầu, retry đúng một lần rồi thành công.
- 10 delivery lỗi lần đầu, retry đúng một lần và vẫn lỗi; sau đó được đưa vào dead-letter có xác nhận.

Kết quả:

| Metric | Giá trị |
| --- | ---: |
| Delivery received | 100 |
| Processing attempts | 140 |
| Retry attempts started | 40 |
| Attempt failures | 50 |
| Delivery success cuối cùng | 90 |
| Delivery final failure | 10 |
| Dead-letter confirmed | 10 |

Ở đây **tỷ lệ thất bại của attempt** là 50/140 ≈ 35,7%, còn **tỷ lệ thất bại cuối của delivery** là 10/100 = 10%. Hai số trả lời hai câu hỏi khác nhau. Nếu một dashboard hiển thị 35,7% mà đặt tên “đơn hàng thất bại”, người vận hành sẽ hiểu sai.

Khi đặt mục tiêu nghiệp vụ, cần đo **business success** hoặc **unique operation success** ở điểm commit có thể kiểm chứng, thay vì suy diễn từ ACK hoặc HTTP 200 đơn lẻ.

## 3. Bắt đầu với Spring Boot Actuator và Micrometer

### 3.1. Dependencies

Ví dụ Maven dùng Spring Boot parent/BOM quản lý phiên bản:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-integration</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-actuator</artifactId>
    </dependency>
    <dependency>
        <groupId>io.micrometer</groupId>
        <artifactId>micrometer-registry-prometheus</artifactId>
        <scope>runtime</scope>
    </dependency>
</dependencies>
~~~

Nếu sử dụng retry qua **RetryTemplate** ở ví dụ sau, thêm **org.springframework.retry:spring-retry** với phiên bản tương thích dự án. Adapter Kafka, RabbitMQ hoặc JDBC còn cần starter/module riêng; Actuator không tự tạo broker, DLQ hay retry policy.

### 3.2. Expose metric có kiểm soát

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: "health,info,metrics,prometheus"
  metrics:
    tags:
      application: order-integration
~~~

Ví dụ trên expose endpoint **/actuator/metrics** và **/actuator/prometheus** khi ứng dụng có các dependency và quyền truy cập phù hợp. Bảo vệ endpoint quản trị bằng mạng, authentication và chính sách phân quyền; không bật mọi endpoint hoặc đưa endpoint quản trị ra Internet công khai.

Sau khi có lưu lượng thực:

~~~text
GET /actuator/metrics
GET /actuator/metrics/app.integration.delivery.received
GET /actuator/prometheus
~~~

Metric tùy biến chỉ xuất hiện sau khi được đăng ký/sử dụng hoặc khởi tạo sẵn. Với nhiều instance, Prometheus thường scrape từng instance rồi dashboard tổng hợp; **counter trong process có thể reset khi ứng dụng restart**. Không cộng các giá trị counter tích lũy một cách thô sơ mà bỏ qua reset.

## 4. Metric có sẵn của Spring Integration đo được gì?

Spring Integration đã tích hợp Micrometer cho nhiều thành phần, chẳng hạn channel, handler và message source. Tuy nhiên, **metric của framework đo hoạt động của thành phần**; nó không mặc nhiên biết nghiệp vụ đã hoàn tất, một lần retry đã bắt đầu hay message thực sự đến DLQ.

Với cơ chế meter truyền thống của Spring Integration:

| Meter phổ biến | Ý nghĩa |
| --- | --- |
| **spring.integration.send** | Timer cho gửi vào channel hoặc xử lý tại handler; thường có nhãn result/exception |
| **spring.integration.receive** | Counter cho nhận từ pollable channel hoặc message source |
| **spring.integration.channel.queue.size** | Gauge độ dài QueueChannel |
| **spring.integration.channel.queue.remaining.capacity** | Gauge dung lượng còn lại của QueueChannel |
| **spring.integration.channels / handlers / sources** | Gauge số thành phần trong application context |

Tùy phiên bản, instrumentation dùng **Micrometer Observation** cũng tạo các metric dạng **spring.integration.gateway**, **spring.integration.handler**, **spring.integration.producer** và các long-task timer liên quan. Observation có thể kết hợp đo metrics và tracing.

### 4.1. Bật observation cho thành phần cần quan sát

Theo cơ chế Spring Integration 6.x+ có thể dùng:

~~~java
@Configuration
@EnableIntegration
@EnableIntegrationManagement(observationPatterns = "order*")
public class IntegrationManagementConfiguration {
}
~~~

Để các thành phần thuộc mẫu tên **order*** được instrument bằng Observation, ứng dụng phải có **ObservationRegistry** được cấu hình (thường qua Spring Boot Actuator) và cơ chế management hoạt động. Giá trị **observationPatterns = "*"** có thể áp dụng cho mọi component nhưng tạo thêm tải và lượng span; chọn mẫu phù hợp để kiểm soát overhead. Không giả định việc chỉ thêm annotation sẽ phát sinh metrics khi thiếu registry hoặc pipeline exporter.

**Chú ý:** đo theo **Micrometer meter truyền thống** và đo bằng **Observation** là hai cơ chế có cách đặt tên/tag khác nhau; một số đường đo có thể thay thế nhau. Trước khi tạo dashboard, kiểm tra metric thực tế ở phiên bản Spring Boot/Spring Integration đang dùng. **Không cộng cả hai tập số liệu như hai lần xử lý độc lập**.

### 4.2. Vì sao cần metric nghiệp vụ riêng?

Một handler có thể bắt exception, retry rồi trả thành công. Timer xử lý cuối của handler có thể ghi **success**, trong khi đã có hai lần lỗi downstream bên trong. Ngược lại, một error flow có thể xử lý được ErrorMessage và hoàn tất bình thường nhưng nghiệp vụ gốc vẫn chưa thành công.

Ngoài meter sẵn có, cần tự định nghĩa những sự kiện quan trọng như:

- Một **processing attempt** thực sự bắt đầu.
- Một **retry attempt** thực sự bắt đầu.
- Handler thất bại tạm thời hoặc vĩnh viễn theo cách phân loại ổn định.
- Delivery kết thúc **success** hoặc **failure**.
- Một thông điệp được chọn đưa vào DLQ/DLT, publish đã được xác nhận, và số message đang chờ xử lý tại queue/topic.

## 5. Thiết kế contract cho các bộ đếm

Một contract thống nhất giúp nhóm phát triển, kiểm thử và vận hành không dùng những định nghĩa khác nhau.

| Tên Micrometer đề xuất | Type | Khi nào tăng? | Các tag nên có |
| --- | --- | --- | --- |
| **app.integration.delivery.received** | Counter | Adapter đưa một delivery vào flow | flow, source |
| **app.integration.processing.attempts** | Counter | Trước mỗi lần gọi logic xử lý | flow, operation |
| **app.integration.processing.attempt.failures** | Counter | Một attempt ném lỗi | flow, error_kind |
| **app.integration.retry.started** | Counter | Một attempt thứ hai trở đi bắt đầu | flow, operation |
| **app.integration.delivery.outcomes** | Counter | Delivery kết thúc thành công hoặc thất bại | flow, result |
| **app.integration.deadletter.decisions** | Counter | Chọn route sang DLQ/DLT | flow, reason |
| **app.integration.deadletter.confirmed** | Counter | Có xác nhận phù hợp rằng publish DLQ/DLT thành công | flow, destination |
| **app.integration.deadletter.observed** | Counter | Một lần consumer đọc message tại DLQ/DLT | destination, source |
| **app.integration.redrive.completed** | Counter | Một redrive được xác nhận hoàn tất theo chính sách | destination, result |
| **app.integration.handler.duration** | Timer | Thời gian của attempt hoặc toàn delivery, chọn một | flow, result |

Tên trên là **quy ước đề xuất cho ứng dụng minh họa**, không phải bộ metric mặc định của Spring Integration hay RabbitMQ/Kafka.

**Chọn đúng mẫu tên Prometheus:** Micrometer nhận tên dạng dấu chấm, chẳng hạn **app.integration.retry.started**. Prometheus exporter có thể chuẩn hóa thành **app_integration_retry_started_total**. Không tự thêm một hậu tố **_total** khác khi định nghĩa Counter trong Java rồi lại cộng thêm trong PromQL. Luôn xem tên thực trên endpoint **/actuator/prometheus**, vì naming convention có thể thay đổi theo registry/phiên bản.

### Tag có cardinality thấp

Tag phù hợp:

~~~text
flow = paid-order | inventory-sync | shipment-updates
source = rabbitmq | kafka | http
error_kind = timeout | unavailable | invalid_payload | conflict | other
result = success | failure
destination = paid-order-dlq | inventory-dlt
~~~

**Không** đưa các giá trị sau vào tag metric: eventId, requestId, orderId, customerId, URL chứa ID động, stack trace, nguyên message, tên exception tùy ý từ thư viện hoặc tenantId có hàng triệu giá trị. Chúng làm bùng nổ số time series, chi phí Prometheus và độ trễ truy vấn.

Với exception, **phân loại** vào tập cố định:

| error_kind | Ví dụ | Retry thường phù hợp? |
| --- | --- | --- |
| timeout | Read/connect timeout, response deadline | Có thể, tùy tính lũy đẳng |
| unavailable | DB/broker/HTTP downstream tạm mất | Có thể, backoff giới hạn |
| rate_limited | HTTP 429 hoặc limiter downstream | Theo Retry-After và ngân sách |
| invalid_payload | JSON/schema không hợp lệ, thiếu trường bắt buộc | Không; sửa dữ liệu hoặc DLQ |
| business_rejected | Không đủ hàng, xung đột nghiệp vụ | Không retry mù |
| duplicate | Event đã được xử lý | Thường không phải lỗi hệ thống |
| other | Lỗi chưa phân loại | Điều tra và chọn policy cụ thể |

## 6. Instrumentation tối thiểu bằng MeterRegistry

Một service chuyên đo metric giúp các handler không lặp cú pháp Micrometer. Ví dụ sau dùng tag **flow** cố định từ cấu hình; không truyền raw eventId thành tag.

~~~java
import io.micrometer.core.instrument.MeterRegistry;
import org.springframework.stereotype.Component;

@Component
public class IntegrationMeters {

    private final MeterRegistry registry;

    public IntegrationMeters(MeterRegistry registry) {
        this.registry = registry;
    }

    public void received(String flow, String source) {
        registry.counter("app.integration.delivery.received",
                "flow", flow, "source", source).increment();
    }

    public void attempt(String flow, String operation) {
        registry.counter("app.integration.processing.attempts",
                "flow", flow, "operation", operation).increment();
    }

    public void attemptFailure(String flow, String errorKind) {
        registry.counter("app.integration.processing.attempt.failures",
                "flow", flow, "error_kind", errorKind).increment();
    }

    public void retryStarted(String flow, String operation) {
        registry.counter("app.integration.retry.started",
                "flow", flow, "operation", operation).increment();
    }

    public void finalOutcome(String flow, String result) {
        registry.counter("app.integration.delivery.outcomes",
                "flow", flow, "result", result).increment();
    }

    public void deadLetterDecision(String flow, String reason) {
        registry.counter("app.integration.deadletter.decisions",
                "flow", flow, "reason", reason).increment();
    }

    public void deadLetterConfirmed(String flow, String destination) {
        registry.counter("app.integration.deadletter.confirmed",
                "flow", flow, "destination", destination).increment();
    }
}
~~~

**Điều kiện sử dụng:** flow/source/errorKind/operation/result/destination được lấy từ **tập giá trị hữu hạn mà ứng dụng kiểm soát**, không lấy nguyên từ message payload. Ở ứng dụng tải rất cao, có thể đăng ký Counter cố định một lần trong constructor thay vì lookup theo tag mỗi lần; Micrometer registry vẫn cache meter theo ID. Việc tăng Counter là thay đổi trạng thái trong process, không thay thế được transaction nghiệp vụ.

### Vì sao không đếm lỗi tại mọi catch?

Ví dụ một exception được ném tại HTTP client, được catch ở service để retry, rồi được wrap thành MessageHandlingException tại endpoint. Nếu cả ba tầng đều tăng cùng **processing.failure**, dashboard sẽ báo ba lỗi dù chỉ có **một attempt** thất bại.

Thay vào đó, chọn **một ranh giới chuẩn**:

- **Attempt failure**: tại wrapper xử lý mỗi lần attempt.
- **Final failure**: bên ngoài retry policy, khi xác định delivery đã kết thúc thất bại.
- **Dead-letter confirmed**: khi đường publish hoặc broker báo xác nhận phù hợp.

Các lỗi tầng thấp vẫn có thể được đo bằng metric riêng của HTTP/JDBC/client; không gộp nhầm với số delivery thất bại.

## 7. Đếm retry chính xác với RetryTemplate

Ví dụ dùng Spring Retry 2.x qua **RetryTemplate** và một hàm xử lý lũy đẳng theo business event ID. Mẫu code minh họa cách đếm **số lần thử lại thực sự bắt đầu**, không đếm số lần policy dự kiến sẽ retry.

~~~java
@Configuration
public class RetryPolicyConfiguration {
    @Bean
    RetryTemplate paymentRetryTemplate() {
        return RetryTemplate.builder()
                .maxAttempts(3)
                .exponentialBackoff(200, 2.0, 2000, true)
                .retryOn(TransientDownstreamException.class)
                .build();
    }
}

public class TransientDownstreamException extends RuntimeException {
    public TransientDownstreamException(String message) {
        super(message);
    }
}
~~~

**maxAttempts(3)** có nghĩa là **một attempt đầu + tối đa hai retry**. **retryOn** chỉ cho phép thử lại các lỗi được chỉ định; ví dụ **IllegalArgumentException** do payload sai không nên bị retry. Backoff có randomization giúp giảm nhiều instance cùng thử lại một lúc. Phiên bản Spring Retry trong dự án quyết định các overload builder có sẵn; cần kiểm tra dependency tương thích Spring Boot/Java.

Handler:

~~~java
@Service
public class PaidOrderProcessor {
    private static final String FLOW = "paid-order";
    private static final String OPERATION = "apply-payment";

    private final RetryTemplate retryTemplate;
    private final IntegrationMeters meters;
    private final PaidOrderService paidOrderService;

    public PaidOrderProcessor(
            RetryTemplate paymentRetryTemplate,
            IntegrationMeters meters,
            PaidOrderService paidOrderService) {
        this.retryTemplate = paymentRetryTemplate;
        this.meters = meters;
        this.paidOrderService = paidOrderService;
    }

    public void handle(OrderPaid event) {
        meters.received(FLOW, "rabbitmq");

        try {
            retryTemplate.execute(context -> {
                meters.attempt(FLOW, OPERATION);
                if (context.getRetryCount() > 0) {
                    meters.retryStarted(FLOW, OPERATION);
                }

                try {
                    paidOrderService.applyIdempotently(event);
                    return null;
                } catch (RuntimeException ex) {
                    meters.attemptFailure(FLOW, classify(ex));
                    throw ex;
                }
            });

            meters.finalOutcome(FLOW, "success");
        } catch (RuntimeException ex) {
            meters.finalOutcome(FLOW, "failure");
            // Giao lại cho adapter/recoverer quyết định ACK, retry broker,
            // requeue hoặc dead-letter; không coi ném lỗi là đã publish DLQ.
            throw ex;
        }
    }

    private String classify(Throwable error) {
        if (error instanceof TransientDownstreamException) {
            return "unavailable";
        }
        if (error instanceof IllegalArgumentException) {
            return "invalid_payload";
        }
        return "other";
    }
}
~~~

**OrderPaid** và **PaidOrderService** là kiểu nghiệp vụ của ứng dụng, không phải lớp Spring. Phương thức **applyIdempotently** phải tự bảo vệ việc ghi trùng tại database hoặc API đích; chỉ retry ở client không biến ghi nhiều lần thành an toàn.

Cách đếm này có các tính chất:

1. **received** tăng một lần khi handler nhận delivery; nếu broker redeliver thì có delivery mới và counter lại tăng.
2. **attempts** tăng trước mỗi lần chạy business logic, gồm attempt đầu.
3. **retry.started** tăng khi **getRetryCount() > 0** trong callback, nghĩa là lần retry đã bắt đầu; không tính lần chỉ mới lên lịch backoff rồi bị hủy.
4. **attempt.failures** tăng đúng một lần cho mỗi exception thoát khỏi attempt wrapper.
5. **delivery.outcomes{result=success|failure}** tăng một lần khi retry hoàn tất thành công hoặc phát sinh thất bại cuối cho delivery.

Nếu kết hợp thêm **retry ở adapter/broker**, cùng một event có thể vào **handle** thêm lần nữa sau redelivery; metric nhận delivery sẽ tăng, còn các retry ngoài process này phải có metric riêng. Không cộng số lần retry trong Spring Retry với số broker redelivery như thể chúng cùng một đơn vị.

### Tình huống retry bị hủy hoặc mất deadline

Giả sử policy lên lịch retry sau backoff 2 giây nhưng service bị dừng trước khi retry bắt đầu. Nếu tăng counter tại lúc **scheduled**, bạn sẽ báo một retry không thực sự chạy. Đo **retry_started** trong callback sau khi backoff kết thúc sẽ chính xác hơn; nếu muốn nghiên cứu áp lực retry có thể thêm **retry_scheduled** với định nghĩa riêng.

Một deadline của toàn flow còn cần kiểm soát thời gian backoff, lần gọi HTTP/DB và waiting time. Counter retry đơn lẻ không cho biết request có vượt SLO hay không; kết hợp thêm Timer/Observation và cơ chế timeout tại client nền.

## 8. Dead-letter: đếm ở đúng thời điểm

**Dead-letter queue (DLQ)** với RabbitMQ/JMS và **dead-letter topic (DLT)** với Kafka có các cơ chế chuyển thông điệp khác nhau. Một lỗi xử lý và một quyết định chuyển dead-letter **chưa chắc đã trở thành một message ở đích**.

### 8.1. Ba mốc nên quan sát riêng

~~~mermaid
flowchart LR
    A["Handler exhausted / invalid payload"] --> B["DLQ/DLT decision"]
    B --> C["Publish, broker reject/nack, route"]
    C --> D["Đích đã nhận hoặc đã có xác nhận"]
    D --> E["DLQ/DLT consumer đọc"]
    B --> F["deadletter.decisions +1"]
    D --> G["deadletter.confirmed +1 nếu đủ bằng chứng"]
    E --> H["deadletter.observed +1"]
~~~

- **deadletter.decisions**: đếm số lần hệ thống muốn gửi bản tin đi nhánh lỗi, hữu ích để chẩn đoán policy.
- **deadletter.confirmed**: chỉ tăng khi adapter/publisher có xác nhận đã publish/routed theo cơ chế mình thật sự có. Không được gọi nó là confirmed chỉ vì code đã gọi phương thức **send()** bất đồng bộ.
- **deadletter.observed**: đếm số delivery vào consumer DLQ/DLT. Đây là bằng chứng có bản tin ở đầu vào DLQ consumer nhưng cũng có thể lặp khi consumer này bị redelivery.

Với **dead-letter route do broker tự thực hiện**, publisher ứng dụng thường không trực tiếp nhận confirm cho lần broker chuyển nội bộ. Khi đó **không nên cố tăng deadletter.confirmed tại handler**, mà lấy số liệu từ broker hoặc quan sát thực tế tại queue/topic; chỉ gắn tên “confirmed” khi có dữ liệu chứng minh.

### 8.2. RabbitMQ: dead-letter exchange và republish là hai đường khác nhau

**Đường 1 — Broker dead-lettering**:

- Queue nguồn cần được cấu hình dead-letter exchange/routing key hoặc policy broker tương đương.
- Khi consumer reject/nack **requeue=false** hoặc message gặp điều kiện dead-letter khác, RabbitMQ có thể route sang DLX.
- Nếu DLX/route/queue đích không tồn tại hoặc policy broker thay đổi, không thể kết luận message đã đến DLQ từ một exception ở ứng dụng.
- **AmqpRejectAndDontRequeueException** diễn tả quyết định reject không requeue; nó không chứng minh DLQ đã nhận thành công.

**Đường 2 — Application republish**:

- **RepublishMessageRecoverer** trong Spring AMQP có thể gửi message lỗi sang một exchange/topic đích khi retry hết.
- Khi recoverer xử lý thành công và không ném exception, container có thể ACK message nguồn; message không tự động được broker dead-letter chỉ vì dùng tên “recoverer”.
- Khi cần xác nhận publish, xem **RepublishMessageRecovererWithConfirms** và cấu hình publisher confirms/returns tương ứng. **Không tăng confirmed trước khi thao tác publish/confirm thành công**.

Ví dụ pseudocode cho application republish, với ranh giới xác nhận tường minh:

~~~java
public void handleTerminalFailure(Envelope envelope, Throwable error) {
    meters.deadLetterDecision("paid-order", "retries_exhausted");

    // Abstraction ứng dụng: return chỉ sau khi publisher confirm thành công;
    // nếu publish không thành công thì ném exception cho recovery policy.
    confirmedDeadLetterPublisher.publishAndConfirm(
            "paid-order-dlq", envelope, error);

    meters.deadLetterConfirmed("paid-order", "paid-order-dlq");
}
~~~

**Envelope** và **ConfirmedDeadLetterPublisher** ở đây là giao diện do ứng dụng định nghĩa; không phải Spring API có sẵn. Trong production cần triển khai bằng adapter broker tương ứng, xử lý publisher confirm, return/unroutable và transaction/ACK. Nếu cần chặt chẽ hơn, có thể dùng outbox để điều phối publish và ACK.

### 8.3. Kafka: DLT và consumer của DLT

Với Spring Kafka, **DefaultErrorHandler**, **DeadLetterPublishingRecoverer** hoặc **@RetryableTopic** có thể đưa bản tin đến DLT sau chính sách retry phù hợp. Cần phân biệt:

- Retry xử lý đồng bộ trong listener container.
- Retry qua các retry topic (non-blocking retries) tạo thêm bản ghi trên topic trung gian.
- Producer retry nội bộ do Kafka client tự thực hiện, không nhất thiết tạo một attempt nghiệp vụ mới.
- Publish tới DLT có thể bất đồng bộ; một lệnh send được gọi không đủ làm chứng cứ broker ghi thành công.

Một listener chỉ để **quan sát các delivery đi vào DLT** có thể được tạo như sau:

~~~java
@Component
public class DeadLetterObserver {
    private final MeterRegistry meters;

    public DeadLetterObserver(MeterRegistry meters) {
        this.meters = meters;
    }

    @KafkaListener(
            topics = "orders.DLT",
            groupId = "orders-dlt-observer")
    public void observe(ConsumerRecord<String, String> record) {
        meters.counter("app.integration.deadletter.observed",
                "destination", "orders.DLT",
                "source", "kafka").increment();

        // Quyết định xử lý nội dung, ACK/commit và redrive cần được
        // thiết kế riêng. Đây chỉ là điểm đo một lần giao ở DLT.
    }
}
~~~

Đoạn trên cần dependency Spring Kafka cùng consumer/deserializer phù hợp. Nó đếm **số lần listener nhận record DLT**, không phải số event logic duy nhất hoặc số event hiện đang nằm chờ trong DLT. Nếu consumer này là observer thuần túy, việc commit offset và chi phí đọc cũng phải được tính toán; không thêm consumer mới chỉ để đo nếu broker/exporter đã cung cấp số liệu đầy đủ.

### 8.4. Spring Integration errorChannel không đồng nghĩa DLQ

Với flow bất đồng bộ, Spring Integration có thể đóng gói exception thành **ErrorMessage** và gửi đến **errorChannel**. Với **RequestHandlerRetryAdvice**, **ErrorMessageSendingRecoverer** có thể gửi lỗi cuối tới recovery channel. Đây là **kênh xử lý lỗi trong ứng dụng**, không tự động là queue/topic dead-letter của broker.

Một error flow hoàn tất không chứng minh bản tin đã vào DLQ. Để đo đúng, phải quan sát **hành động thực sự publish/route**, kết quả confirm và ACK sau đó. Nếu flow chỉ log ErrorMessage và ACK nguồn, cần đặt tên metric là **error_handled** hoặc **terminal_failure**, không đặt là **deadletter.confirmed**.

## 9. Kết hợp metric ứng dụng với dữ liệu từ broker

Counter của ứng dụng và gauge/số liệu broker nhìn từ hai phía khác nhau:

| Nguồn dữ liệu | Trả lời được | Không tự trả lời được |
| --- | --- | --- |
| Counter **retry.started** của app | Có bao nhiêu retry trong process bắt đầu | Bao nhiêu broker redelivery hoặc client producer retry |
| Counter **delivery.outcomes** của app | Handler trả success/failure bao nhiêu lần | Event nghiệp vụ duy nhất đã hoàn tất bao nhiêu |
| Counter **deadletter.decisions** của app | Có bao nhiêu quyết định gửi dead-letter | Đích có nhận được hay không |
| Broker **DLQ depth/lag** | Hiện còn bao nhiêu message chưa tiêu thụ hoặc backlog | Tổng message từng vào DLQ từ trước đến nay |
| Broker **DLQ ingress/publish rate** | Tốc độ message được ghi/route vào đích theo cách exporter đo | Handler nào tạo lỗi nếu thiếu correlation |
| DLQ consumer **observed** | Đã thấy bao nhiêu delivery tại DLQ | Có bao nhiêu event logic duy nhất; đã xử lý thành công hay chưa |

Đối soát ví dụ:

~~~text
Application quyết định dead-letter 40 lần
   ↓
Publisher xác nhận thành công 37 lần
   ↓
Broker ghi nhận 37 lần publish/routing có thể truy vết
   ↓
DLQ vẫn tồn đọng 32 message sau khi xử lý/redrive
~~~

Ba sự kiện publish lỗi phải có đường retry/alert riêng; không thể giả định chúng đã đến DLQ. **DLQ depth** còn phụ thuộc consumer, TTL, xóa, redrive và chính sách broker; không kỳ vọng depth = số quyết định chuyển DLQ.

**Không dùng một counter tăng bằng cách đo chiều dài queue định kỳ.** Queue depth là gauge thể hiện ảnh chụp một thời điểm; counter ghi nhận số sự kiện tăng theo thời gian. Một queue có thể giữ 0 message dù 10.000 message đã đi qua và được xử lý hết.

## 10. Dashboard và truy vấn Prometheus

Các ví dụ dưới đây giả định Micrometer xuất các Counter với tên Prometheus tương ứng:

### Tốc độ delivery và retry

~~~promql
sum by (flow) (
  rate(app_integration_delivery_received_total[5m])
)
~~~

~~~promql
sum by (flow) (
  rate(app_integration_retry_started_total[5m])
)
~~~

### Tỷ lệ final failure của delivery

~~~promql
sum by (flow) (
  rate(app_integration_delivery_outcomes_total{result="failure"}[5m])
)
/
clamp_min(
  sum by (flow) (
    rate(app_integration_delivery_outcomes_total[5m])
  ),
  1e-9
)
~~~

Tỷ lệ trên có mẫu số là **delivery đã có kết quả cuối**. Nó không đo số event unique và có thể bị ảnh hưởng nếu quá nhiều delivery còn đang xử lý. Để đo SLO end-to-end, cần thêm độ trễ và số message đang pending theo nghiệp vụ.

### Số dead-letter đã xác nhận trong một giờ

~~~promql
sum by (flow, destination) (
  increase(app_integration_deadletter_confirmed_total[1h])
)
~~~

Để biết dead-letter đang tích tụ, dùng thêm **gauge DLQ depth / Kafka consumer lag** từ exporter broker với tên metric thực tế tương ứng, vì gauge này không được tạo tự động bởi IntegrationMeters.

### Khi các số có thể không cộng khớp

Đừng viết luật cố định kiểu:

~~~text
received = success + failure + dead-letter
~~~

Vì:

1. **dead-letter** có thể là một kết cục của **failure**, cộng cả hai sẽ đếm trùng.
2. Delivery đang xử lý, chờ backoff hoặc pending ACK chưa có final outcome.
3. Một message có thể redeliver, khiến số delivery lớn hơn số event unique.
4. Counter reset khi process restart, khác biệt nhịp scrape và metric mất mẫu có thể làm chênh lệch tạm thời.
5. Dead-letter do broker route hoặc producer retry ở ngoài process có thể không hiện trong counter ứng dụng.

Muốn đối soát chính xác phải xác định **cùng đơn vị, cùng tập message, cùng time window và cùng điểm commit**.

## 11. Cảnh báo dựa trên hành vi, không dựa vào một con số đơn

| Tín hiệu | Ý nghĩa vận hành | Hành động đầu tiên |
| --- | --- | --- |
| Final failure rate tăng liên tục | Dịch vụ downstream, payload hoặc code gặp sự cố | Phân theo error_kind, deployment và trace |
| Retry started tăng nhưng final failure không tăng | Sự cố tạm thời đang được retry che khỏi người dùng | Kiểm tra latency và ngân sách retry |
| Retry và final failure cùng tăng | Retry không phục hồi được | Kiểm tra availability/rate limit và giảm tải |
| Dead-letter decisions tăng, confirmed không tăng theo | Có thể publish DLQ thất bại hoặc mất confirm | Kiểm tra publisher confirms, return/unroutable |
| DLQ depth hoặc Kafka DLT lag tăng đều | Đội xử lý lỗi/redrive không theo kịp | Phân loại poison message, scale xử lý có kiểm soát |
| Retry thấp nhưng latency p99 tăng | Chờ connection, lock, pool hoặc retry chưa được instrument | Kiểm tra timer, queue và client metrics |
| Poison message lặp lại nhiều lần | Validator/retry policy không phân loại đúng | Đưa lỗi không thể retry vào dead-letter |

Không có ngưỡng **5 lỗi/phút** hay **DLQ > 0** phù hợp cho mọi hệ thống. Xây ngưỡng theo lưu lượng, SLO, mức quan trọng của event, lịch sử và hậu quả nghiệp vụ. Với luồng tài chính, chỉ một poison message có thể cần điều tra; với luồng analytics, một số lỗi có thể chấp nhận trong ngân sách đã thống nhất.

Dashboard nên kết hợp **traffic, errors, latency, saturation và dead-letter backlog**, có đường xem log/trace từ alert. Đừng đặt alert chỉ vì counter tích lũy khác 0: Counter không giảm và có thể giữ lại những lỗi đã khắc phục từ nhiều ngày trước.

## 12. Liên kết metric, log và distributed tracing

Metric giúp thấy mức độ, log giúp đọc nguyên nhân, trace giúp tìm vị trí lỗi trong chuỗi service. Một mẫu điều tra:

~~~text
Alert: retry.started tăng tại flow=paid-order
   ↓
Metric: attempt.failures{error_kind="timeout"} tăng
   ↓
Trace: inbound AMQP/Kafka → handler → HTTP downstream
   ↓
Log: timeout gọi payment-gateway, retry attempt=2
   ↓
Đánh giá: upstream chậm, deadline quá dài, pool bị cạn?
~~~

Các thuộc tính hữu ích trong **log hoặc span có kiểm soát**:

- traceId/spanId, flow name, operation và adapter.
- Business event ID hoặc request ID đã xử lý phù hợp chính sách dữ liệu.
- Delivery attempt, retry index, classifier error_kind.
- Tên downstream, trạng thái HTTP/SQL/broker và thời gian chờ.
- Kết quả publish DLT/DLQ và mã correlation khi có confirm.

**Phân biệt high cardinality giữa log/trace và metric:** eventId có thể cần trong log đã bảo vệ để truy vết một event, nhưng **không** nên dùng làm tag Counter. Nếu flow đi qua broker, cần kiểm tra truyền trace context giữa producer và consumer, cũng như sampling; một trace bị lấy mẫu bỏ đi không có nghĩa xử lý không xảy ra.

### Retry hoặc DLQ có thể làm mất ngữ cảnh

Khi một event được gửi sang retry topic hoặc DLQ, message mới có thể có header/baggage khác hoặc trace mới. Để liên kết chuỗi, lưu thông tin tương quan phù hợp (original topic/queue, eventId, attempt, error_kind) nhưng tránh ghi stack trace vô hạn hoặc dữ liệu nhạy cảm vào header. Thống nhất thời gian sống, kích thước và quyền truy cập của dead-letter payload.

## 13. Kiểm thử metric theo contract

Kiểm thử chỉ đảm bảo “handler gọi một lần” chưa đủ để xác nhận dashboard đúng. Dùng **SimpleMeterRegistry** trong unit test để kiểm tra số counter; dùng broker thật trong integration test để kiểm tra requeue, ACK và dead-letter routing.

### 13.1. Test RetryTemplate: hai retry sau attempt đầu

Ví dụ độc lập với broker:

~~~java
@Test
void twoRetriesAreCountedAsTwoStarts() {
    SimpleMeterRegistry registry = new SimpleMeterRegistry();
    IntegrationMeters meters = new IntegrationMeters(registry);

    RetryTemplate retry = RetryTemplate.builder()
            .maxAttempts(3)
            .fixedBackoff(1)
            .retryOn(TransientDownstreamException.class)
            .build();

    AtomicInteger invocations = new AtomicInteger();

    retry.execute(context -> {
        meters.attempt("paid-order", "apply-payment");
        if (context.getRetryCount() > 0) {
            meters.retryStarted("paid-order", "apply-payment");
        }
        if (invocations.incrementAndGet() < 3) {
            meters.attemptFailure("paid-order", "unavailable");
            throw new TransientDownstreamException("Temporary");
        }
        return null;
    });

    assertEquals(3, invocations.get());
    assertEquals(3.0, registry
            .get("app.integration.processing.attempts")
            .tag("flow", "paid-order")
            .tag("operation", "apply-payment")
            .counter().count());
    assertEquals(2.0, registry
            .get("app.integration.retry.started")
            .tag("flow", "paid-order")
            .tag("operation", "apply-payment")
            .counter().count());
    assertEquals(2.0, registry
            .get("app.integration.processing.attempt.failures")
            .tag("flow", "paid-order")
            .tag("error_kind", "unavailable")
            .counter().count());
}
~~~

Các import JUnit 5, AtomicInteger, RetryTemplate và SimpleMeterRegistry được lược bỏ. Test chứng minh quy ước đếm attempt/retry ở mức callback; **chưa chứng minh ACK của broker hay message đã được publish vào DLQ**.

### 13.2. Kịch bản kiểm thử integration

| Kịch bản | Các số đếm mong đợi | Cần xác minh ngoài metric |
| --- | --- | --- |
| Thành công ngay | attempts=1, retry=0, final success=1 | Commit/ACK thành công |
| Lỗi transient hai lần, lần ba thành công | attempts=3, retry=2, attempt failures=2, final success=1 | Không có side effect trùng |
| Payload không hợp lệ | retry=0, final failure=1 | Routing poison message theo policy |
| Retry hết rồi publish dead-letter thành công | final failure=1, decision=1, confirmed=1 | Broker có message ở queue/topic đích |
| Publish dead-letter thất bại | decision=1, confirmed=0 | Original message vẫn có đường phục hồi |
| Broker redeliver một event sau crash | received delivery tăng thêm | Nghiệp vụ vẫn idempotent |
| Worker chết giữa backoff | Retry scheduled có thể có, retry started không tăng thêm | Message được phục hồi/điều phối hợp lý |
| Consumer DLQ đọc lại message | observed tăng theo delivery | Không nhầm với số event unique |
| Hai instance xử lý cùng eventId | Metric cộng theo instance; không suy ra exactly-once | Kho idempotency chặn hiệu ứng trùng |

Với RabbitMQ, cần test queue, DLX và publisher confirms thật; với Kafka, cần test consumer config, error handler, topic DLT và producer ack. Testcontainer hoặc broker test phù hợp thường có giá trị hơn chỉ mock **send()** trả thành công.

### 13.3. Xác minh metric end-to-end

1. Gửi test message với eventId xác định và một lỗi transient có thể kiểm soát.
2. Kiểm tra handler retry đúng số lần, outcome đúng và backend nghiệp vụ chỉ commit một lần.
3. Đọc **/actuator/metrics** hoặc **/actuator/prometheus**; xác nhận tên, tag và giá trị thực sự được export.
4. Kích hoạt lỗi không retry để đi nhánh terminal failure; xác minh DLQ/DLT theo hệ thống broker thật.
5. Đối chiếu decision, confirmed, observed và backlog sau khi chờ exporter/scrape hội tụ.
6. Khởi động lại một instance để bảo đảm dashboard xử lý counter reset và redelivery đúng semantics.

## 14. Sai lầm thường gặp

**“Lần xử lý đầu lỗi rồi retry thành công vẫn phải tính là message thất bại.”** Không phải nếu metric muốn đo final failure. Hãy đếm attempt failure và final outcome riêng.

**“Đặt Counter bên trong catch ở ba tầng cho số lỗi chính xác hơn.”** Dễ đếm cùng exception nhiều lần. Chọn một điểm đo chuẩn cho mỗi đơn vị.

**“RetryTemplate maxAttempts=3 nghĩa là có ba lần retry.”** Sai. Nó nghĩa là tối đa ba attempts, bao gồm attempt đầu.

**“Gọi deadLetterSender.send() là có một message ở DLQ.”** Chưa đủ với publisher bất đồng bộ, unroutable exchange/topic hoặc broker tự chuyển DLX. Đo confirm hoặc số liệu broker.

**“Đếm ErrorMessage trên errorChannel tức là đếm dead-letter.”** Error channel là routing lỗi trong ứng dụng; chỉ khi flow thực sự publish dead-letter mới có thể gắn metric dead-letter.

**“DLQ queue depth chính là tổng lỗi trong ngày.”** Queue depth là số bản ghi còn tồn tại; message có thể vào rồi được tiêu thụ/redrive.

**“Một thông điệp redeliver hai lần nghĩa là có hai business events.”** Cần event ID ổn định và phép đếm unique nếu thực sự muốn đo business events.

**“Counter trong app không cần tính reset.”** Counter tích lũy reset khi process restart; với Prometheus dùng rate/increase và label instance phù hợp.

**“Chỉ cần tag eventId để truy tìm lỗi nhanh.”** EventId gây cardinality cao; dùng log/trace correlation thay vì metric tag.

**“Micrometer đã bật nên có đầy đủ retry và DLQ metric.”** Framework có meter cho component, nhưng retry policy, kết quả publish DLQ và business outcome cần instrumentation ở ranh giới phù hợp.

**“Đã gửi DLT tức là có thể ACK mọi lúc.”** Phải xem publisher confirm, transaction, error handler và adapter semantics; nếu DLT publish thất bại nhưng original được ACK, có nguy cơ mất message.

## 15. Checklist trước khi vận hành

1. Viết định nghĩa cho **delivery, attempt, retry_started, final_failure, DLQ decision, DLQ confirmed, DLQ observed**.
2. Xác định bên nào tạo retry: Spring Retry, Spring Integration advice, Kafka retry topic, Rabbit redelivery, HTTP client hay producer; tránh đo lặp.
3. Instrument attempt tại lúc chạy, final outcome sau khi retry kết thúc và dead-letter tại mốc có bằng chứng rõ.
4. Expose Actuator/Prometheus có kiểm soát; kiểm tra tên metric thực tế theo phiên bản và registry.
5. Dùng tag flow, operation, source, error_kind, destination trong một danh sách giá trị giới hạn.
6. Phân loại lỗi retryable/permanent, áp dụng maxAttempts, backoff, jitter, deadline và idempotency.
7. Với broker, kiểm tra ACK/requeue, retry topic hoặc DLX, producer confirms, errorChannel và chính sách khi DLT/DLQ publish thất bại.
8. Kết hợp counter của app với broker ingress, DLQ backlog, consumer lag và trace; không lấy một số thay cho toàn bộ chuỗi.
9. Kiểm thử error taxonomy, retry count, failure count, dead-letter success/failure, restart và redelivery bằng test phù hợp.
10. Dashboard thể hiện traffic, errors, retries, latency, saturation và backlog; alert theo xu hướng và SLO, có đường điều tra bằng logs/traces.

**Kết luận:** Muốn đo được độ tin cậy thực sự của luồng tích hợp, cần tách rõ **lỗi của một attempt**, **retry đã thực thi**, **kết quả cuối của delivery** và **sự kiện dead-letter đã được xác nhận**. Spring Boot Actuator, Micrometer và Spring Integration tạo nền tảng quan sát; ứng dụng phải bổ sung những bộ đếm có contract và đối chiếu với dữ liệu broker để không đưa ra kết luận sai về các thông điệp thất bại.

## Tài liệu tham khảo

- [Spring Integration Reference — Metrics and Management](https://docs.spring.io/spring-integration/reference/metrics.html): meter kênh/handler, ObservationRegistry, @EnableIntegrationManagement và observation patterns.
- [Spring Integration Reference — Error Handling](https://docs.spring.io/spring-integration/reference/error-handling.html): errorChannel, ErrorMessage và định tuyến lỗi bất đồng bộ.
- [Spring Integration Reference — Provided Advice Classes](https://docs.spring.io/spring-integration/reference/handler-advice/classes.html): RequestHandlerRetryAdvice và recovery channel.
- [Spring Boot Reference — Actuator Endpoints](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html): cấu hình expose và bảo vệ endpoint.
- [Spring Boot Reference — Metrics](https://docs.spring.io/spring-boot/reference/actuator/metrics.html): Micrometer, metric exporters và naming conventions.
- [Spring Retry API — RetryTemplateBuilder](https://docs.spring.io/spring-retry/docs/2.0.x/apidocs/spring.retry/org/springframework/retry/support/RetryTemplateBuilder.html): maxAttempts, retryOn và backoff.
- [Spring AMQP Reference — Resilience and Message Recovery](https://docs.spring.io/spring-amqp/reference/amqp/resilience-recovering-from-errors-and-broker-failures.html): RepublishMessageRecoverer, confirm và hành vi ACK.
- [Spring Kafka Reference — Handling Exceptions](https://docs.spring.io/spring-kafka/reference/kafka/annotation-error-handling.html): DefaultErrorHandler, DeadLetterPublishingRecoverer và recovery của listener.
