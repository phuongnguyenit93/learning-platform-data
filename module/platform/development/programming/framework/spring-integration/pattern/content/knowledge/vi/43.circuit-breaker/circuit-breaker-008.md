# Không retry vô hạn khi circuit đã mở

## 1. Vấn đề: breaker ngắt API nhưng retry vẫn lặp lại

Trong module **SPRING_INTEGRATION_PATTERN**, Spring Integration cho phép xây dựng luồng theo Enterprise Integration Patterns (EIP): Gateway nhận yêu cầu, Filter kiểm tra message, Transformer chuẩn hóa dữ liệu, Router chuyển nhánh, Service Activator gọi dependency, còn Splitter/Aggregator phối hợp kết quả nhiều nhánh. Các message channel giảm phụ thuộc giữa thành phần, nhưng một dependency không khả dụng vẫn có thể gây nghẽn nếu hệ thống thiếu chính sách lỗi.

**Circuit breaker** bảo vệ điểm gọi dependency thông qua ba trạng thái:

- **CLOSED:** cho phép request đi qua và đo kết quả.
- **OPEN:** từ chối nhanh các request mới; dependency không nhận thêm lời gọi tương ứng.
- **HALF_OPEN:** cho một số request thăm dò theo chính sách, sau đó quyết định đóng lại hoặc mở tiếp.

**Retry** dành cho lỗi tạm thời có khả năng phục hồi. Một sai lầm nguy hiểm là để Retry bắt mọi exception và thử lại vô hạn, kể cả khi breaker đã OPEN. Mỗi attempt sẽ nhận cùng một lỗi từ chối. Dù không tạo thêm HTTP request, nó vẫn chiếm thời gian, worker thread, bộ nhớ, log và có thể gây tắc nghẽn tại Gateway hoặc hàng đợi.

**Nguyên tắc:** khi breaker từ chối thực thi, **dừng retry tức thời của request hiện tại**. Trả lỗi có ý nghĩa, dùng fallback an toàn hoặc lưu công việc để xử lý sau với giới hạn, backoff và thời hạn rõ ràng. Thời gian chờ OPEN thuộc về breaker; một vòng retry vô hạn không làm dependency hồi phục.

~~~mermaid
flowchart TD
    A[Gateway nhận message] --> B[Validate / Transform]
    B --> C[Circuit breaker]
    C -->|Được cấp quyền| D[Dependency]
    D -->|Thành công| E[Reply]
    D -->|Lỗi tạm thời| F{Còn retry budget?}
    F -->|Có và an toàn| G[Backoff hữu hạn]
    G --> C
    F -->|Không| H[Error / fallback]
    C -->|OPEN hoặc hết permit| I[Dừng retry tức thời]
    I --> H
    H --> J[Fail fast / Cache / Durable defer]
~~~

Sơ đồ thể hiện chính sách logic. Vị trí Retry nằm ngoài hay trong Circuit Breaker ảnh hưởng số attempt được breaker quan sát; cần quyết định rõ thay vì chỉ lắp hai advice theo thói quen.

## 2. Phân biệt lỗi của dependency với lỗi breaker từ chối

| Trường hợp | Dependency đã được gọi? | Hành động thường phù hợp |
| --- | --- | --- |
| Connection refused hoặc response timeout | Có | Retry hữu hạn nếu an toàn, có backoff |
| HTTP 503 được client chuyển thành exception | Có | Có thể retry hữu hạn theo chính sách |
| HTTP 429 | Có thể có | Tôn trọng chính sách quota hoặc Retry-After nếu có |
| Validation error do Filter phát hiện | Không | Trả lỗi đầu vào, không retry |
| Circuit đang **OPEN** | **Không** | Không retry ngay, dùng fallback hoặc fail fast |
| **HALF_OPEN** không còn permit | **Không** | Không vòng lặp tranh permit |
| Probe HALF_OPEN bị timeout | Có | Để breaker ghi nhận lỗi, xử lý theo policy |
| Lỗi lập trình ở Transformer | Không phải lỗi dependency | Sửa lỗi ứng dụng, không retry API mù quáng |

Với **Resilience4j**, lời gọi bị từ chối khi circuit không cấp quyền có thể ném **CallNotPermittedException**. Đây là lỗi từ bộ bảo vệ, không chứng minh HTTP client vừa lỗi. Không nên cộng những lần bị từ chối vào số lần Stock API thực thi thất bại; cần đo bằng chỉ số **not-permitted/rejected calls** riêng.

Với **RequestHandlerCircuitBreakerAdvice** native của Spring Integration, kiểu exception khi từ chối có thể khác Resilience4j. Nếu dùng Spring Retry, cần xác định exception thực tế của phiên bản thư viện trong flow, rồi đưa nó vào nhóm **không được retry**. Không giả định mọi breaker đều ném CallNotPermittedException.

## 3. Retry khi OPEN gây lãng phí như thế nào?

Giả sử Gateway gửi yêu cầu tra tồn kho, breaker đã OPEN từ trước. Retry được cấu hình tối đa 5 attempts, mỗi lần cách nhau 200 ms nhưng lại retry tất cả RuntimeException.

~~~mermaid
sequenceDiagram
    participant G as Gateway
    participant R as Retry
    participant B as Breaker OPEN
    participant S as Stock API
    G->>R: StockQuery
    loop 5 attempts
        R->>B: Thử lại
        B--xR: Not permitted
        Note over S: Không nhận HTTP request
    end
    R--xG: Lỗi cuối cùng
~~~

Trong ví dụ này Stock API nhận **0 lời gọi**, nhưng Retry vào breaker **5 lần**. Nếu không giới hạn retry, một request có thể giữ worker trong thời gian rất dài. Khi lưu lượng lớn, hệ thống tốn CPU, tăng latency và tích tụ message chỉ để biết rằng circuit vẫn OPEN.

Một trường hợp nghiêm trọng hơn: consumer lấy message từ broker, nhận lỗi OPEN, rồi **NACK/requeue ngay**. Broker phát lại message, consumer tiếp tục nhận lỗi, rồi lại NACK. Chuỗi này có thể diễn ra vô hạn dù không có request HTTP nào tới upstream.

Cần phân biệt ba lớp retry có thể xuất hiện cùng lúc:

1. **Retry ở HTTP/client:** thử lại lời gọi vật lý tới dependency.
2. **Retry trong handler/message flow:** Spring Retry hoặc Resilience4j Retry thực hiện lại logic của handler.
3. **Redelivery ở broker/Gateway caller:** toàn bộ message hoặc request nghiệp vụ được gửi lại.

Nếu mỗi lớp có giới hạn riêng nhưng không có budget tổng, số lần gọi có thể nhân lên. Ví dụ 3 attempts ở client, 4 deliveries ở broker và 2 lần caller gửi lại có thể tạo tối đa **24 lần gọi vật lý** nếu mọi lớp đều cho thực thi. Do đó cần giới hạn số attempts **tổng thể**, lưu correlation và chống trùng khi cần.

## 4. Xây dựng retry policy có điểm dừng

| Quy tắc | Cách áp dụng |
| --- | --- |
| Retry đúng loại lỗi | Chỉ lỗi transport hoặc một số lỗi upstream tạm thời |
| Dừng ở OPEN | Loại CallNotPermittedException và lỗi từ chối tương ứng |
| Giới hạn attempts | Ví dụ tối đa 3 attempts, kể cả lần đầu |
| Dùng backoff và jitter | Giảm nguy cơ hàng loạt client thử lại cùng lúc |
| Có deadline tổng thể | Không vượt thời gian Gateway được phép chờ |
| Kiểm tra idempotency | Tránh lặp các lệnh tạo đơn, giữ tồn kho hoặc thu tiền |
| Hết budget phải kết thúc | Trả lỗi, fallback hoặc durable defer có TTL |
| Quan sát attempts | Tách request logic, attempt vào breaker, HTTP call và redelivery |

**Resilience4j Retry** quy định **maxAttempts(3)** là tổng số lần thực thi, gồm một lần đầu và tối đa hai lần retry. Với thư viện khác, phải kiểm tra maxAttempts có phải tổng attempts hay số retry bổ sung.

### Backoff, jitter và deadline

Exponential backoff có thể tăng khoảng chờ sau các lỗi từ 200 ms lên 400 ms rồi 800 ms; **jitter** thêm một độ lệch ngẫu nhiên được giới hạn để các caller không cùng gửi lại. Các con số chỉ là ví dụ, cần điều chỉnh theo SLO và tải upstream.

Một client timeout 800 ms với tối đa ba attempts, cộng backoff 200 ms và 400 ms, có thể mất khoảng **3 giây** nếu cả ba lần đều đụng timeout. Nếu Gateway có reply deadline 1,5 giây, policy đó không đáp ứng yêu cầu ngay cả khi cuối cùng thành công. Các bước trong flow cũng tiêu tốn thời gian, nên deadline tổng cần bao trùm cả Transformer, Router, handler và reply.

Khi breaker đang OPEN, đợi vài trăm mili giây rồi retry ngay **không tương đương** chờ thời gian OPEN. Cách phù hợp là kết thúc lần thực thi hiện tại và, nếu được phép, lưu lệnh để lên lịch ở tương lai bằng hạ tầng durable thay vì giữ thread ngủ.

## 5. Thứ tự Retry và Circuit Breaker

### 5.1. Breaker ở ngoài Retry

~~~mermaid
flowchart LR
    G[Gateway] --> B[Circuit breaker]
    B --> R[Retry hữu hạn]
    R --> D[Stock API]
~~~

Breaker có thể quan sát **kết quả cuối của một request logic**. Nếu retry ba lần đều timeout, breaker ngoài có thể ghi nhận một lần thực thi thất bại. Nếu lần ba thành công, breaker có thể thấy một success dù client đã có hai attempt lỗi.

Khi mạch OPEN, Retry bên trong **không chạy** vì breaker từ chối từ bên ngoài. Nhưng khi HALF_OPEN, **một permit thăm dò có thể chứa nhiều lời gọi mạng** do Retry bên trong. Điều này có thể tăng tải lên dependency vừa phục hồi. Cần giới hạn attempts và deadline dành cho probe.

### 5.2. Retry ở ngoài Breaker

~~~mermaid
flowchart LR
    G[Gateway] --> R[Retry hữu hạn]
    R --> B[Circuit breaker]
    B --> D[Stock API]
~~~

Từng attempt đi qua breaker và có thể đóng góp vào failure count. Một request nghiệp vụ có thể làm breaker OPEN giữa các attempts. Khi đó lỗi từ chối phải được phân loại **không retry**, tránh thử lại vô ích.

| Tiêu chí | Breaker ngoài Retry | Retry ngoài Breaker |
| --- | --- | --- |
| Đơn vị breaker đo | Thường là kết quả cuối của request logic | Từng attempt được phép thực thi |
| Ba timeout cùng một request | Có thể đóng góp 1 failure | Có thể đóng góp 3 failures |
| Breaker OPEN trước request | Retry không chạy | Retry phải dừng khi nhận lỗi từ chối |
| HALF_OPEN | Một probe có thể gồm nhiều HTTP attempts | Mỗi attempt có thể cần permit riêng |
| Tín hiệu cần quan sát | Logical call và HTTP attempts | Retry count, breaker events, rejected calls |

Không có thứ tự áp dụng cho tất cả hệ thống. Mục tiêu là chọn **đơn vị đo lỗi**, mức bảo vệ upstream và tổng số call vật lý khi HALF_OPEN; sau đó kiểm thử đúng advice chain triển khai thực tế.

## 6. Ví dụ Spring Integration Java DSL với Resilience4j

Ví dụ minh họa flow tra tồn kho. **StockClient** là adapter của ứng dụng, có timeout và chuyển lỗi kết nối/5xx phù hợp thành **StockTransportException**. Các import Java được lược bớt; cần dùng các module Resilience4j Retry/CircuitBreaker khớp phiên bản dự án.

### 6.1. Hợp đồng

~~~java
public record StockQuery(String sku, int quantity) {}

public record StockReply(String sku, int availableUnits) {}

public interface StockClient {
    StockReply lookup(StockQuery query);
}

public class StockTransportException extends RuntimeException {
    public StockTransportException(String message, Throwable cause) {
        super(message, cause);
    }
}
~~~

Đặt Filter hoặc Validator trước handler để loại quantity âm, SKU rỗng. Không biến exception validate thành StockTransportException: breaker chỉ nên đánh giá sức khỏe dependency.

### 6.2. Cấu hình breaker và retry hữu hạn

~~~java
@Configuration
@EnableIntegration
@IntegrationComponentScan
public class StockFlowConfig {

    @Bean
    public CircuitBreaker stockBreaker() {
        CircuitBreakerConfig config = CircuitBreakerConfig.custom()
                .slidingWindowSize(10)
                .minimumNumberOfCalls(5)
                .failureRateThreshold(50.0f)
                .waitDurationInOpenState(Duration.ofSeconds(20))
                .permittedNumberOfCallsInHalfOpenState(2)
                .build();

        return CircuitBreaker.of("stock-api", config);
    }

    @Bean
    public Retry stockRetry() {
        RetryConfig config = RetryConfig.custom()
                .maxAttempts(3)
                .waitDuration(Duration.ofMillis(200))
                .retryExceptions(StockTransportException.class)
                .ignoreExceptions(CallNotPermittedException.class)
                .build();

        return Retry.of("stock-retry", config);
    }

    @Bean
    public StockLookupService stockLookupService(
            StockClient client,
            CircuitBreaker stockBreaker,
            Retry stockRetry
    ) {
        return new StockLookupService(client, stockBreaker, stockRetry);
    }

    @Bean
    public IntegrationFlow stockFlow(StockLookupService service) {
        return IntegrationFlow.from("stock.requests")
                .handle(
                        StockQuery.class,
                        (query, headers) -> service.lookup(query)
                )
                .get();
    }
}

@MessagingGateway(defaultRequestChannel = "stock.requests")
public interface StockGateway {
    StockReply lookup(StockQuery request);
}
~~~

**retryExceptions** giới hạn loại lỗi được thử lại. **ignoreExceptions(CallNotPermittedException.class)** cho phép exception từ chối đi ra ngoài mà không tiếp tục retry. Cấu hình này vẫn cần kiểm chứng exception có bị wrap trong một loại exception khác ở ranh giới handler hay không.

### 6.3. Thực thi đúng thứ tự bằng decorator

~~~java
public class StockLookupService {

    private final StockClient client;
    private final CircuitBreaker breaker;
    private final Retry retry;

    public StockLookupService(
            StockClient client,
            CircuitBreaker breaker,
            Retry retry
    ) {
        this.client = client;
        this.breaker = breaker;
        this.retry = retry;
    }

    public StockReply lookup(StockQuery request) {
        Supplier<StockReply> remoteCall =
                () -> client.lookup(request);

        Supplier<StockReply> breakerProtected =
                CircuitBreaker.decorateSupplier(breaker, remoteCall);

        // Retry là lớp ngoài. Khi breaker từ chối, retry dừng.
        Supplier<StockReply> boundedRetry =
                Retry.decorateSupplier(retry, breakerProtected);

        return boundedRetry.get();
    }
}
~~~

Thứ tự ở đây là **Retry → Circuit Breaker → StockClient**. Nếu StockClient timeout khi CLOSED, lỗi đi qua breaker và có thể được Retry thử lại trong giới hạn. Nếu circuit OPEN, breaker không thực thi supplier và ném CallNotPermittedException; Retry đã được cấu hình bỏ qua lỗi này nên kết thúc ngay. Gateway nhận exception hoặc tầng xử lý fallback tiếp nhận nó.

**Không bắt exception bên trong remoteCall rồi trả StockReply giả**. Nếu làm vậy, breaker có thể chỉ thấy success và không mở mạch khi upstream thất bại. Nếu muốn cache/fallback, xử lý **sau khi breaker đã ghi nhận lỗi**, ở ranh giới bên ngoài decorator.

### 6.4. Nếu chọn Breaker bao ngoài Retry

Đảo decorator để breaker chỉ thấy kết quả cuối:

~~~java
Supplier<StockReply> remoteCall =
        () -> client.lookup(request);

Supplier<StockReply> retryInner =
        Retry.decorateSupplier(retry, remoteCall);

Supplier<StockReply> breakerOuter =
        CircuitBreaker.decorateSupplier(breaker, retryInner);

return breakerOuter.get();
~~~

Khi OPEN, retryInner không chạy. Tuy nhiên HALF_OPEN có thể cho một request logic chứa ba attempts vật lý. Cần quyết định có chấp nhận mức tải đó hay không, nhất là khi dependency phục hồi chậm.

## 7. Spring Integration native advice và Spring Retry

Spring Integration cung cấp **RequestHandlerCircuitBreakerAdvice** và **RequestHandlerRetryAdvice**. Khi dùng chúng cùng một handler, **thứ tự advice chain** quyết định breaker đếm request logic hay từng attempt.

Ví dụ cấu hình nguyên tắc:

~~~java
@Bean
public RequestHandlerCircuitBreakerAdvice stockCircuitAdvice() {
    RequestHandlerCircuitBreakerAdvice advice =
            new RequestHandlerCircuitBreakerAdvice();
    advice.setThreshold(3);
    advice.setHalfOpenAfter(20_000);
    return advice;
}

@Bean
public RequestHandlerRetryAdvice stockRetryAdvice() {
    RequestHandlerRetryAdvice advice =
            new RequestHandlerRetryAdvice();

    RetryTemplate template = new RetryTemplate();

    Map<Class<? extends Throwable>, Boolean> retryable =
            new HashMap<>();
    retryable.put(StockTransportException.class, true);

    SimpleRetryPolicy policy =
            new SimpleRetryPolicy(3, retryable, true, false);
    template.setRetryPolicy(policy);

    FixedBackOffPolicy backOff = new FixedBackOffPolicy();
    backOff.setBackOffPeriod(200);
    template.setBackOffPolicy(backOff);

    advice.setRetryTemplate(template);
    return advice;
}
~~~

Trong ví dụ này, policy chỉ cho retry **StockTransportException** và được giới hạn **3 attempts**. **StockTransportException** là class ứng dụng tự định nghĩa. Cần kiểm tra exception wrapper và khả năng traverse cause chain theo phiên bản Spring Retry, để timeout thực tế được phân loại đúng.

Lắp advice vào Service Activator:

~~~java
@Bean
public IntegrationFlow stockFlow(
        StockClient client,
        RequestHandlerCircuitBreakerAdvice stockCircuitAdvice,
        RequestHandlerRetryAdvice stockRetryAdvice
) {
    return IntegrationFlow.from("stock.requests")
            .handle(
                    StockQuery.class,
                    (query, headers) -> client.lookup(query),
                    endpoint -> endpoint.advice(
                            stockCircuitAdvice,
                            stockRetryAdvice
                    )
            )
            .get();
}
~~~

Ví dụ thể hiện ý định **breaker bao ngoài Retry**. Khi triển khai, cần xác nhận thứ tự thực thi của advice chain bằng integration test có fake client, vì advisor ordering và cơ chế proxy trong cấu hình cụ thể có thể ảnh hưởng ngữ nghĩa. Không đưa exception **breaker từ chối** vào whitelist retryable.

Nếu dùng recovery callback để trả fallback, kiểm tra vị trí recovery: một fallback nằm bên trong vùng được breaker bảo vệ có thể nuốt exception và khiến breaker không thấy lỗi dependency. Với Resilience4j và native advice, nguyên tắc đều là để breaker **quan sát thất bại thật** trước khi biến nó thành kết quả suy giảm.

## 8. OPEN: fail fast, cache hay durable defer?

Circuit breaker không quyết định kết quả nghiệp vụ khi OPEN. Flow phải chọn phương án phù hợp.

| Phương án | Trường hợp | Kết quả cần diễn đạt |
| --- | --- | --- |
| **Fail fast** | Checkout, thanh toán, xác nhận giữ hàng | **UNAVAILABLE** hoặc exception có cấu trúc |
| **Cache có TTL** | Thông tin danh mục chỉ để tham khảo | **STALE_REFERENCE**, ghi nguồn và thời gian dữ liệu |
| **Provider dự phòng** | Nguồn thứ hai có hợp đồng tương đương | Dùng timeout và breaker riêng cho nguồn dự phòng |
| **Durable defer** | Gửi thông báo, đồng bộ nền | **ACCEPTED_FOR_LATER** sau khi lưu bền vững |

Không trả **available = false** khi không gọi được Stock API: “không xác định tồn kho” khác với “đã xác minh hết hàng”. Cần hợp đồng tách **FRESH**, **STALE_REFERENCE**, **UNAVAILABLE** để Router và Aggregator phía sau không diễn giải sai.

**Không retry tức thời khi OPEN** không có nghĩa vĩnh viễn bỏ tác vụ. Với công việc cho phép xử lý sau, có thể lập lịch một lần thử khác trong tương lai. Điểm khác biệt là **mỗi lần thử phải có giới hạn và được theo dõi**.

~~~mermaid
flowchart TD
    A[Consumer nhận message] --> B{Còn attempt budget và TTL?}
    B -->|Không| Z[DLQ / terminal failure]
    B -->|Có| C[Circuit breaker]
    C -->|Được phép| D[Dependency]
    D -->|Thành công| E[ACK hoàn thành]
    D -->|Lỗi tạm thời| F[Lưu lịch retry có backoff]
    C -->|OPEN / không cấp permit| F
    F --> G[Delayed queue / durable outbox]
    G -->|Tới lịch xử lý| A
~~~

Để defer an toàn, cần:

- **ACK sau khi lưu bền vững**, không trả thành công trước khi message thực sự được ghi.
- **attemptCount / maxAttempts**, **firstFailureAt**, **nextAttemptAt**, **expiresAt**.
- **Backoff với jitter**, giới hạn queue và cơ chế backpressure.
- **Dead-letter queue** hoặc trạng thái terminal khi hết số lần thử hoặc TTL.
- **Correlation ID, tenant context và idempotency key** để truy vết và tránh xử lý trùng.

Một consumer không nên dùng vòng Thread.sleep kéo dài theo thời gian OPEN, vì sẽ giữ worker và làm giảm năng lực xử lý message khác. Ưu tiên scheduled poller, delayed queue hoặc outbox theo khả năng hạ tầng.

## 9. Error channel và broker redelivery

Trong Spring Integration, cần phân biệt ranh giới lỗi:

- **Gateway đồng bộ qua DirectChannel:** exception có thể truyền thẳng về caller. Boundary REST/application quyết định fail fast hoặc fallback.
- **ExecutorChannel, poller hoặc adapter bất đồng bộ:** tùy cấu hình, exception có thể được phát dưới dạng **ErrorMessage** tới error channel.
- **Broker consumer:** rollback hoặc NACK có thể khiến broker redeliver. Nếu redelivery tức thời vô hạn khi breaker OPEN, tạo vòng lặp message bị từ chối.

**Error channel là đường vận chuyển lỗi, không phải chính sách retry.** Consumer của error channel phải phân loại failure, số lần thử và nơi tiếp theo của message. Không nên catch mọi exception rồi NACK/requeue ngay không giới hạn.

Một hợp đồng deferred message có thể như sau:

~~~java
public record DeferredCommand(
        String commandId,
        String correlationId,
        String tenantId,
        String idempotencyKey,
        int attemptCount,
        Instant firstFailureAt,
        Instant nextAttemptAt,
        Instant expiresAt,
        byte[] payload
) {}
~~~

Đây là record do ứng dụng tự định nghĩa, không phải kiểu mặc định của Spring Integration. Tránh lưu hoặc log payload nhạy cảm ngoài chính sách bảo vệ dữ liệu.

| Loại lỗi | Cách xử lý |
| --- | --- |
| **BREAKER_REJECTED** | Fail fast hoặc hoãn có lịch; không retry tức thời |
| **UPSTREAM_TIMEOUT** | Retry hữu hạn nếu an toàn; hết budget thì defer/DLQ |
| **VALIDATION_ERROR** | Kết thúc, không retry |
| **BUSINESS_REJECTED** | Trả kết quả nghiệp vụ, không retry transport |
| **EXPIRED_COMMAND** | Terminal failure, không phát lại |
| **UNKNOWN_WRITE_RESULT** | Đối soát trước khi thử lệnh ghi lần nữa |

**Delivery count của broker không tương đương HTTP attempt count** nếu bên trong handler còn Retry advice. Muốn giới hạn tổng nỗ lực, cần đo các lớp riêng và thống nhất retry budget theo request nghiệp vụ.

## 10. Splitter, Aggregator và correlation

Một đơn hàng có thể được Splitter tách thành các nhánh **stock**, **pricing**, **shipping**. Nếu stock breaker OPEN, nhánh tồn kho cần trả outcome **UNAVAILABLE** hoặc được giải quyết bằng error flow thay vì cứ retry và khiến Aggregator thiếu reply.

~~~mermaid
flowchart LR
    A[Gateway] --> B[Splitter]
    B --> C[Stock breaker OPEN]
    B --> D[Pricing service]
    B --> E[Shipping service]
    C --> F[UNAVAILABLE outcome]
    D --> G[Aggregator]
    E --> G
    F --> G
~~~

Nếu một nhánh không trả kết quả, phải cấu hình **group timeout**, expiration, partial result hoặc discard/error path. Cần giữ **correlation ID** và sequence headers khi chuyển sang fallback hoặc defer. Không để một nhóm Aggregator chờ vô hạn chỉ vì message đang trong vòng retry hoặc broker redelivery.

Router vẫn chọn nhánh theo ý nghĩa nghiệp vụ, Filter kiểm tra dữ liệu đầu vào, Transformer chuyển payload. Một lỗi Transformer không có lý do trở thành request timeout của Stock API; phân loại đúng giúp tránh retry lệnh gọi dependency vì bug ứng dụng.

## 11. Lệnh ghi cần idempotency, không được retry vì không thấy response

Với thao tác đọc, retry thường dễ kiểm soát hơn. Với lệnh **tạo đơn, giữ tồn kho, thanh toán**, một lần timeout chỉ nói caller **chưa nhận được kết quả**, không chứng minh upstream chưa xử lý lệnh.

Ví dụ: Stock API đã giữ 5 sản phẩm nhưng response bị mất. Client timeout và thử lại với lệnh mới. Nếu Stock API không chống trùng, nó có thể giữ thêm 5 sản phẩm, dù user chỉ đặt một lần.

Với retry hoặc replay lệnh ghi, cần:

1. **Idempotency key** ổn định theo lệnh nghiệp vụ và tenant.
2. Upstream trả lại kết quả cho key đã xử lý hoặc bảo đảm không thực thi trùng.
3. **Reconciliation** cho trạng thái không rõ đã thành công hay chưa.
4. Deadline, attempts tối đa và trạng thái terminal.
5. Đường điều tra/khắc phục khi thất bại, tránh retry vĩnh viễn một lệnh có side effect.

Circuit breaker bảo vệ số lần gọi mới; nó **không tự cung cấp exactly-once processing**. Không được dùng Retry và breaker như biện pháp thay thế cho idempotency.

## 12. Kiểm thử: OPEN không vào client và Retry chỉ thử một lần

Để chứng minh policy đúng, cần đo ít nhất hai bộ đếm:

- **Remote calls:** tổng số lần thực thi dependency.
- **Entries into breaker:** số lần Retry cố đi qua breaker.

Ví dụ JUnit 5 dưới đây cho thấy sau khi circuit OPEN, một request mới bị từ chối, **client không được gọi thêm** và Retry **không thử lại** exception từ chối dù maxAttempts là 5. Các import được lược bớt.

~~~java
@Test
void openBreakerIsNotRetried() {
    CircuitBreakerConfig config = CircuitBreakerConfig.custom()
            .slidingWindowSize(2)
            .minimumNumberOfCalls(2)
            .failureRateThreshold(100.0f)
            .waitDurationInOpenState(Duration.ofMinutes(1))
            .build();

    CircuitBreaker breaker = CircuitBreaker.of("stock-test", config);
    AtomicInteger remoteCalls = new AtomicInteger();

    Supplier<String> failingClient = () -> {
        remoteCalls.incrementAndGet();
        throw new StockTransportException(
                "timeout", new java.net.SocketTimeoutException()
        );
    };

    // Hai cuộc gọi thật thất bại để mở mạch.
    assertThrows(
            StockTransportException.class,
            () -> breaker.executeSupplier(failingClient)
    );
    assertThrows(
            StockTransportException.class,
            () -> breaker.executeSupplier(failingClient)
    );

    assertEquals(CircuitBreaker.State.OPEN, breaker.getState());
    assertEquals(2, remoteCalls.get());

    RetryConfig retryConfig = RetryConfig.custom()
            .maxAttempts(5)
            .waitDuration(Duration.ofMillis(10))
            .retryExceptions(StockTransportException.class)
            .ignoreExceptions(CallNotPermittedException.class)
            .build();

    Retry retry = Retry.of("stock-test-retry", retryConfig);
    AtomicInteger entries = new AtomicInteger();

    Supplier<String> breakerProtected = () -> {
        entries.incrementAndGet();
        return breaker.executeSupplier(failingClient);
    };
    Supplier<String> outerRetry =
            Retry.decorateSupplier(retry, breakerProtected);

    assertThrows(CallNotPermittedException.class, outerRetry::get);
    assertEquals(2, remoteCalls.get());  // Không gọi client mới.
    assertEquals(1, entries.get());      // Không retry lỗi OPEN.
}
~~~

Test này không kiểm tra timeout của HTTP client thật. Để xác minh adapter, cần thêm integration test với server giả lập chậm/đóng kết nối và kiểm tra exception mapping. Test retry advice Spring Integration nên chạy qua Gateway và handler thật, vì thứ tự advice có thể làm kết quả khác nhau.

### Ma trận kiểm thử đề nghị

| Kịch bản | Kết quả mong đợi |
| --- | --- |
| CLOSED, upstream thành công | Một attempt, trả reply đúng |
| CLOSED, timeout rồi thành công | Retry hữu hạn, remote calls trong budget |
| CLOSED, mọi attempts thất bại | Trả lỗi cuối, breaker ghi nhận theo thứ tự advice |
| OPEN trước khi có request | Không gọi client, không retry not-permitted |
| Circuit OPEN giữa các attempts | Retry dừng khi nhận lỗi từ chối |
| HALF_OPEN hết permit | Không liên tục retry để giành permit |
| Breaker ngoài Retry, probe HALF_OPEN | Tổng attempt mạng trong probe được giới hạn |
| Validation bị Filter từ chối | Không gọi dependency, không retry |
| HTTP 429 có Retry-After | Hoãn/throttle đúng chính sách, không tạo bão retry |
| Broker redelivery khi OPEN | Có delay/TTL/DLQ, không vòng NACK tức thời |
| Deferred message hết budget | Kết thúc terminal, không phát lại mãi |
| Splitter có nhánh OPEN | Aggregator có outcome/timeout và correlation |
| Lệnh ghi bị mất response | Replay có idempotency, không phát sinh side effect trùng |
| Nhiều instance/pod | Không giả định breaker state được đồng bộ |

Với các test này, cần phân biệt **logical request count**, **retry attempt count**, **remote call count** và **message delivery count**. Chỉ assert exception cuối chưa đủ để biết một vòng retry có đang diễn ra phía sau hay không.

## 13. Giám sát để phát hiện retry loop

Breaker OPEN có thể khiến metric HTTP error ở upstream **giảm**, đơn giản vì request bị chặn trước client. Vì vậy phải theo dõi thêm Retry và message flow.

| Tín hiệu | Điều cần phát hiện |
| --- | --- |
| Breaker state / state transitions | Circuit OPEN bao lâu, có dao động OPEN/HALF_OPEN không? |
| Not-permitted / rejected calls | Lượng request bị từ chối ở breaker |
| Retry attempts per request | Có request nào bị thử quá nhiều lần không? |
| Retry attempts vì breaker rejected | Policy có đang retry nhầm lỗi OPEN không? |
| Remote client call count | Có giảm traffic tới upstream thật không? |
| Gateway latency và timeout rate | Retry có kéo quá deadline không? |
| Deferred queue depth / oldest age | Message có đang tích tụ không? |
| Dead-letter volume | Có nhiều công việc đã hết TTL/attempt budget không? |
| Fallback rate và cache age | Có đang che lỗi dependency bằng dữ liệu quá cũ không? |
| Aggregator pending / expired groups | Có nhánh đang chờ thiếu reply không? |
| Correlation ID / idempotency key trong trace/log | Có lần theo request và chống trùng được không? |

Metric nên gắn nhãn có cardinality vừa phải như **breaker name**, **operation**, **outcome**; correlation ID và ID tenant cụ thể nên nằm trong log/trace được kiểm soát quyền truy cập.

Dấu hiệu thường gặp:

- **Rejected calls tăng cùng số retry attempts/request:** đang thử lại lỗi circuit từ chối.
- **Remote calls thấp nhưng queue tăng vô hạn:** cần giới hạn tiếp nhận công việc, lịch hoãn và DLQ.
- **OPEN → HALF_OPEN → OPEN liên tục:** upstream chưa hồi phục hoặc probe/retry tạo tải quá lớn.
- **Breaker vẫn CLOSED dù nhiều timeout:** exception bị catch trước breaker, hoặc Retry che kết quả.
- **Gateway timeout nhưng backend vẫn thực thi:** có nguy cơ duplicate do caller/broker retry.

## 14. Checklist áp dụng cho Spring Integration

- [ ] Circuit breaker bao sát lời gọi dependency và có timeout thực tại client.
- [ ] Retry policy chỉ chọn lỗi tạm thời có thể phục hồi, **không retry lỗi breaker từ chối**.
- [ ] Có maxAttempts, backoff/jitter và deadline tổng cho một request.
- [ ] Hiểu thứ tự Retry/Breaker và kiểm chứng bằng call counter.
- [ ] HALF_OPEN có giới hạn permit và số attempt vật lý trong mỗi probe.
- [ ] Fallback phân biệt **FRESH / STALE_REFERENCE / UNAVAILABLE**, không trả kết quả giả.
- [ ] Nếu xử lý sau, có durable outbox/queue, nextAttemptAt, attemptCount, TTL và DLQ.
- [ ] Không dùng NACK/requeue tức thời vô hạn khi broker redelivery lúc OPEN.
- [ ] Lệnh ghi có idempotency key và quy trình reconciliation khi response không rõ.
- [ ] Router, Filter, Transformer và error channel phân loại lỗi đúng miền trách nhiệm.
- [ ] Splitter/Aggregator giữ correlation, có partial result hoặc group timeout.
- [ ] Test cả số lần vào breaker và số cuộc gọi client khi OPEN/HALF_OPEN.
- [ ] Đo retry attempts, rejected calls, queue age, fallback rate và Gateway latency.

**Không retry vô hạn khi circuit đã mở** giúp breaker thực sự giảm tải thay vì chuyển nghẽn từ HTTP client sang Retry, Gateway hoặc broker. Trong Spring Integration, dừng ngay việc retry lỗi từ chối, áp dụng deadline cho các lỗi tạm thời và defer có giới hạn cho công việc hợp lệ sẽ giữ luồng EIP dễ kiểm thử, dễ quan sát và phục hồi có kiểm soát.
