# Theo dõi trạng thái circuit

## 1. Theo dõi breaker để biết hệ thống đang được bảo vệ hay đang suy giảm

Trong **SPRING_INTEGRATION_PATTERN**, Spring Integration giúp lắp ghép Enterprise Integration Patterns thành các message flow ít phụ thuộc: Gateway nhận yêu cầu, Filter kiểm tra, Transformer chuẩn hóa, Router chuyển nhánh, Service Activator gọi dependency và Splitter/Aggregator phối hợp các kết quả. Circuit breaker được gắn gần điểm gọi dependency để ngăn lời gọi mới khi upstream có dấu hiệu lỗi hoặc quá chậm.

Khi đã có breaker, câu hỏi vận hành không chỉ là **API bên ngoài có trả lỗi không**, mà còn là:

- Breaker của dependency nào đang **CLOSED**, **OPEN** hoặc **HALF_OPEN**?
- Nó mở lúc nào, vì nguyên nhân nào và đã thử phục hồi bao nhiêu lần?
- Bao nhiêu message bị từ chối **trước khi gọi upstream**?
- Gateway có phản hồi nhanh hơn hay người dùng vẫn gặp timeout, fallback và lỗi?
- Một nhánh của Router bị chặn có khiến Aggregator thiếu reply hoặc queue tăng không?
- Có instance/pod nào phục hồi trong khi những instance khác vẫn OPEN không?

**Theo dõi trạng thái circuit** là kết hợp *trạng thái hiện tại*, *sự kiện chuyển trạng thái*, *kết quả lời gọi* và *tác động lên toàn bộ message flow*. Không thể chỉ nhìn một dòng log “circuit opened” rồi kết luận hệ thống đã được bảo vệ hiệu quả.

~~~mermaid
flowchart LR
    A[Gateway] --> B[Filter / Transformer]
    B --> C{Router}
    C --> D[Breaker: stock-api]
    C --> E[Breaker: pricing-api]
    D --> F[Stock Client]
    E --> G[Pricing Client]
    D -.-> M[Events và Metrics]
    E -.-> M
    A -.-> T[Trace / Correlation]
    F -.-> T
    G -.-> T
    M --> H[Dashboard]
    T --> H
    H --> I[Alert / Incident response]
~~~

Điều cốt lõi là **quan sát theo đúng miền lỗi**. Stock API bị OPEN không đồng nghĩa Pricing API cũng đang lỗi, trừ khi hai nhánh thực sự chia sẻ một dependency hoặc tài nguyên gây hỏng chung.

## 2. Ý nghĩa của từng trạng thái khi quan sát

| State | Ý nghĩa kỹ thuật | Nên thấy trong vận hành |
| --- | --- | --- |
| **CLOSED** | Cho phép lời gọi và đo kết quả | Có lưu lượng tới dependency, thành công/thất bại được ghi nhận |
| **OPEN** | Từ chối lời gọi mới | Số client calls giảm; số rejected/not-permitted có thể tăng |
| **HALF_OPEN** | Cấp phép thử có giới hạn | Một số probe đi tới dependency, các request vượt permit có thể bị từ chối |

Ba trạng thái này là **trạng thái của bộ bảo vệ**, không phải kết luận về một request đơn lẻ. Trong CLOSED, request vẫn có thể lỗi. Trong OPEN, request có thể được ứng dụng trả **fallback cache**, nhưng bản thân dependency không được gọi. Trong HALF_OPEN, một probe thành công chưa chắc đủ đóng mạch nếu chính sách yêu cầu nhiều probe.

### 2.1. State hiện tại khác event chuyển trạng thái

Giả sử lúc 10:00 breaker chuyển **CLOSED → OPEN**. Sau đó không có request mới trong 15 phút.

- **State hiện tại** có thể vẫn là OPEN.
- **Số state-transition events** có thể vẫn chỉ là 1.
- **Số rejected calls** có thể bằng 0 vì không có traffic mới.
- **Số HTTP errors tới dependency** có thể bằng 0 vì breaker đã chặn đường gọi.

Một biểu đồ HTTP error bằng 0 trong khoảng thời gian này **không chứng minh upstream đã phục hồi**. Cần nhìn đồng thời state, request volume, not-permitted calls, fallback use và kết quả thăm dò.

### 2.2. Các trạng thái đặc biệt

Một số thư viện, ví dụ **Resilience4j**, còn có các trạng thái vận hành như **DISABLED**, **FORCED_OPEN** và **METRICS_ONLY**. Chúng không có cùng ngữ nghĩa với ba trạng thái thường dùng:

- **DISABLED:** có thể cho phép thực thi mà không vận hành circuit breaker theo cơ chế thông thường.
- **FORCED_OPEN:** chủ động buộc từ chối lời gọi.
- **METRICS_ONLY:** thu thập chỉ số nhưng không chuyển OPEN để chặn request.

Phải đọc ngữ nghĩa theo phiên bản/thư viện thực tế trước khi xây dashboard. Nếu quy mọi trạng thái lạ thành CLOSED, hệ thống có thể hiển thị sai mức độ bảo vệ. Các thao tác ép state/reset cần quyền quản trị và audit riêng.

## 3. Bốn lớp tín hiệu cần thu thập

Một hệ thống quan sát tốt không chỉ xuất metric ở Circuit Breaker, mà còn đo trước và sau nó.

| Lớp | Tín hiệu nên thu thập | Giúp trả lời |
| --- | --- | --- |
| **Trạng thái** | Current state, state transition, thời điểm vào OPEN/HALF_OPEN | Circuit đã mở bao lâu và có đang dao động không? |
| **Thao tác được bảo vệ** | Successful, failed, slow, buffered calls, latency | Upstream thực sự khỏe hay chậm/lỗi? |
| **Lời gọi bị chặn** | Not-permitted/rejected calls, reason code | Có bao nhiêu request bị breaker từ chối trước client? |
| **Message flow** | Gateway latency, error/fallback, retry, queue depth, Aggregator pending | Circuit ảnh hưởng đến người dùng và các EIP thế nào? |

Những số liệu này không thể thay thế cho nhau. Một lời gọi **not-permitted** không phải là một HTTP attempt thất bại; một lần fallback thành công về mặt xử lý nghiệp vụ cũng không có nghĩa upstream đang khỏe.

### 3.1. Gauge, counter và event nên dùng cho mục đích nào?

- **State gauge:** biểu diễn trạng thái hiện tại theo breaker name và instance. Cần thống nhất mapping hoặc dùng gauge riêng cho từng state do instrumentation cung cấp.
- **State-transition event/counter:** đếm số lần CLOSED → OPEN, OPEN → HALF_OPEN, HALF_OPEN → OPEN, HALF_OPEN → CLOSED. Hữu ích để nhận biết mạch dao động.
- **Call outcome counters:** ghi nhận số calls thành công, thất bại, chậm và bị từ chối theo cửa sổ thời gian của hệ thống metrics.
- **Latency histogram/timer:** quan sát p95/p99 hoặc phân phối độ trễ; không thể suy ra tất cả từ failure count.
- **Trace/log:** điều tra một message cụ thể theo correlation ID, exception, dependency và nhánh xử lý.

Không nên dùng **counter tích lũy** để biểu diễn “circuit hiện đang OPEN”. Ngược lại, một gauge OPEN hiện tại không nói breaker đã mở mấy lần trong một giờ.

## 4. Metric dễ bị hiểu sai

Giả sử breaker của Stock API đã OPEN do lỗi, Gateway vẫn nhận 1.000 request/phút và tất cả được trả **UNAVAILABLE** nhanh.

| Chỉ số | Có thể quan sát được | Diễn giải đúng |
| --- | --- | --- |
| Số lời gọi thực tới Stock API | Rất thấp hoặc bằng 0 | Breaker đã ngăn traffic tới dependency |
| Lỗi HTTP từ Stock API | Có thể về 0 | Không đủ chứng minh Stock API đã khỏe |
| Not-permitted calls | Gần lượng request cần Stock API | Nhiều request đang bị ngắt tại breaker |
| Gateway latency | Có thể giảm | Fail fast hoạt động, nhưng nghiệp vụ vẫn suy giảm |
| Gateway error hoặc fallback rate | Có thể tăng mạnh | Người dùng không nhận kết quả fresh |
| State | OPEN | Chưa có đủ bằng chứng phục hồi |

Nếu chỉ nhìn lượng timeout HTTP giảm, dashboard có thể báo **xanh giả**. Do đó cần hiển thị cùng nhau **state + rejected calls + Gateway outcome + fallback rate**, và tốt nhất có thông tin từ health check của dependency độc lập với breaker.

### 4.1. Failure rate và minimum calls

Với breaker dựa trên sliding window, failure rate có dạng:

\[
\text{Failure rate}
=
\frac{\text{Số lời gọi thất bại được ghi nhận}}
{\text{Số lời gọi được ghi nhận trong cửa sổ}}
\times 100\%.
\]

Ví dụ 5/10 lời gọi lỗi cho tỷ lệ 50%. Tuy nhiên **Resilience4j** có cấu hình **minimumNumberOfCalls**: khi chưa đủ số mẫu, giá trị failure rate có thể được biểu diễn bằng một giá trị sentinel như **-1**, tức **chưa có tỷ lệ hợp lệ**, chứ không phải “-1% lỗi”.

Vì vậy không nên tạo cảnh báo hoặc biểu đồ mặc định coi failure rate âm là 0%. Hãy hiển thị **INSUFFICIENT_DATA** hoặc thiếu mẫu và bổ sung số buffered calls/throughput để giải thích.

### 4.2. Slow calls không nhất thiết failed calls

Một lời gọi mất 2 giây nhưng trả kết quả hợp lệ có thể là **slow success**. Nó tăng số lời gọi chậm, không nhất thiết tăng failure count. Một lời gọi timeout có thể vừa **slow** vừa **failed**. Không cộng failed calls và slow calls rồi coi đó là tổng số cuộc gọi độc lập.

**Not-permitted calls** xảy ra trước khi supplier/handler gọi client, nên không thể dùng nó làm mẫu số cho tỷ lệ lỗi của những lời gọi dependency đã thực thi.

## 5. Theo dõi circuit trong Resilience4j

**Resilience4j** cung cấp API xem trạng thái, metrics snapshot và **EventPublisher** để lắng nghe chuyển trạng thái. Ví dụ Spring Integration Java DSL sau minh họa cách giữ một breaker dùng lại cho điểm gọi Stock API.

### 5.1. Hợp đồng message và client

~~~java
public record StockQuery(String sku, int quantity) {}

public record StockReply(
        String sku,
        int availableUnits
) {}

public interface StockClient {
    StockReply lookup(StockQuery query);
}

@MessagingGateway(defaultRequestChannel = "stock.requests")
public interface StockGateway {
    StockReply lookup(StockQuery query);
}
~~~

**StockClient** là adapter do ứng dụng tự triển khai, cần có connect/read/response timeout và chuyển lỗi dependency phù hợp thành exception. Các ví dụ Java lược bỏ phần import và cấu hình HTTP thực tế để tập trung vào circuit.

### 5.2. Cấu hình registry, breaker và event listener

~~~java
@Configuration
@EnableIntegration
@IntegrationComponentScan
public class StockCircuitConfiguration {

    private static final Logger log =
            LoggerFactory.getLogger(StockCircuitConfiguration.class);

    @Bean
    public CircuitBreakerRegistry circuitBreakerRegistry() {
        CircuitBreakerConfig config = CircuitBreakerConfig.custom()
                .slidingWindowSize(10)
                .minimumNumberOfCalls(5)
                .failureRateThreshold(50.0f)
                .waitDurationInOpenState(Duration.ofSeconds(20))
                .permittedNumberOfCallsInHalfOpenState(2)
                .build();

        return CircuitBreakerRegistry.of(config);
    }

    @Bean
    public CircuitBreaker stockCircuitBreaker(
            CircuitBreakerRegistry registry
    ) {
        CircuitBreaker breaker =
                registry.circuitBreaker("stock-api");

        // Đăng ký đúng một lần lúc khởi tạo,
        // không gắn listener lại cho mỗi request.
        breaker.getEventPublisher()
                .onStateTransition(event ->
                        log.warn(
                                "breaker={} transition={} time={}",
                                event.getCircuitBreakerName(),
                                event.getStateTransition(),
                                event.getCreationTime()
                        )
                );

        return breaker;
    }

    @Bean
    public IntegrationFlow stockFlow(
            StockClient stockClient,
            CircuitBreaker stockCircuitBreaker
    ) {
        return IntegrationFlow.from("stock.requests")
                .handle(
                        StockQuery.class,
                        (query, headers) ->
                                stockCircuitBreaker.executeSupplier(
                                        () -> stockClient.lookup(query)
                                )
                )
                .get();
    }
}
~~~

Ở đây, **stock-api** là tên breaker ổn định. Tất cả request đi qua bean này dùng chung state trong **cùng một process**. Khi có sự kiện state transition, listener ghi log một bản ghi gồm tên breaker, chiều chuyển và thời điểm.

**Không nên gắn listener trong handler của từng request.** Mỗi request có thể thêm một listener mới, gây rò rỉ bộ nhớ hoặc ghi log một sự kiện nhiều lần. Cũng không nên đăng ký cùng một listener lặp lại ở nhiều chỗ khi dùng registry. Với hệ thống nhiều breakpoint/tenant, cần cơ chế đăng ký cho mỗi instance breaker được tạo, đồng thời kiểm soát số lượng tên.

**Không log exception payload, token truy cập hoặc dữ liệu nhạy cảm** trong state-transition log. Nếu cần điều tra một request lỗi cụ thể, dùng trace/log ở client adapter với correlation ID và chính sách bảo vệ dữ liệu.

### 5.3. Đọc snapshot trạng thái và bộ thống kê

~~~java
CircuitBreaker.State state = stockCircuitBreaker.getState();
CircuitBreaker.Metrics metrics = stockCircuitBreaker.getMetrics();

int buffered = metrics.getNumberOfBufferedCalls();
int failed = metrics.getNumberOfFailedCalls();
int successful = metrics.getNumberOfSuccessfulCalls();
long rejected = metrics.getNumberOfNotPermittedCalls();

float failureRate = metrics.getFailureRate();
float slowCallRate = metrics.getSlowCallRate();
~~~

Ví dụ nêu các API Resilience4j phổ biến; signatures cụ thể cần đối chiếu dependency/version được dự án sử dụng.

**Điều cần phân biệt:**

- **buffered/failed/successful** thường là thống kê của cửa sổ hiện tại, không phải counter toàn bộ thời gian chạy.
- **failureRate/slowCallRate** có thể chưa hợp lệ khi thiếu số mẫu.
- **rejected/not-permitted** phản ánh request bị từ chối ở breaker, không phải số client HTTP failures.
- **state** là ảnh chụp tức thời; có thể thay đổi ngay sau khi đọc vì request đồng thời.

Đừng dựng bộ đếm tổng số request bằng cách cộng các snapshot cửa sổ từng giây. Một cuộc gọi có thể xuất hiện trong nhiều lần chụp, gây đếm trùng. Muốn đếm event dài hạn, dùng metrics/counters hoặc event publisher đúng mục đích.

## 6. Tích hợp Micrometer và dashboard

Nếu ứng dụng có **Micrometer** và module **resilience4j-micrometer** tương thích, có thể bind registry breaker vào MeterRegistry. Một ví dụ bean binder:

~~~java
@Bean
public MeterBinder circuitBreakerMeterBinder(
        CircuitBreakerRegistry circuitBreakerRegistry
) {
    return meterRegistry ->
            TaggedCircuitBreakerMetrics
                    .ofCircuitBreakerRegistry(circuitBreakerRegistry)
                    .bindTo(meterRegistry);
}
~~~

Nếu dùng Spring Boot Actuator, hệ thống có thể xuất metrics qua actuator hoặc hệ thống thu thập được cấu hình. Cần kiểm tra **module có thực sự nằm trên classpath**, endpoint có được bật/cấp quyền hay chưa và **metric names/tags của phiên bản đang dùng**. Không mặc định chỉ thêm breaker là Prometheus sẽ tự có đủ biểu đồ.

Một dashboard tối thiểu nên có:

| Khung hiển thị | Nội dung |
| --- | --- |
| **Breaker states** | Danh sách breaker và state theo instance |
| **State transitions** | Số lần OPEN/HALF_OPEN/CLOSED trong khoảng thời gian |
| **Call outcomes** | Successful, failed, slow và not-permitted |
| **Latency** | p50/p95/p99 của HTTP client và Gateway |
| **Fallback** | Tỷ lệ cache stale, UNAVAILABLE, fail fast |
| **Queue** | Depth, tuổi message cũ nhất, số message DLQ |
| **Retry** | Attempt per logical request, rejected-retry attempts |
| **Aggregator** | Pending groups, expired groups, partial results |

Metric names có thể thay đổi theo module, version và hệ thống export. Khi viết PromQL hoặc dashboard, **khám phá tên metric được xuất thực tế** thay vì sao chép tên từ ví dụ không cùng version.

### 6.1. Không dùng nhãn có cardinality vô hạn

Breaker có thể được đặt theo service, endpoint, region hoặc tenant group. Tránh đặt breaker name bằng:

- Request ID, correlation ID hoặc trace ID.
- URL đầy đủ chứa query parameters hoặc SKU.
- Mọi tenant ID không giới hạn khi số lượng tenant lớn.
- Email, token hoặc định danh bí mật.

Ưu tiên nhãn ổn định như **breaker_name**, **operation**, **region**, **instance**, **outcome** hoặc **tenant_group** đã được kiểm soát. ID chi tiết nên nằm trong trace/log có phân quyền, không phải metric tags tạo vô số time series.

## 7. Với Spring Integration native advice, theo dõi thế nào?

Spring Integration có **RequestHandlerCircuitBreakerAdvice** để bao quanh request handler. Đây là lựa chọn hữu ích khi cần ngưỡng lỗi liên tiếp, nhưng **không được mặc định nó cung cấp đầy đủ API event và Micrometer metrics giống Resilience4j**.

Ví dụ đặt advice ngay tại Service Activator:

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
public IntegrationFlow stockFlow(
        StockClient stockClient,
        RequestHandlerCircuitBreakerAdvice stockCircuitAdvice
) {
    return IntegrationFlow.from("stock.requests")
            .handle(
                    StockQuery.class,
                    (query, headers) -> stockClient.lookup(query),
                    endpoint -> endpoint.advice(stockCircuitAdvice)
            )
            .get();
}
~~~

**Nguyên tắc instrument native advice:**

1. **Đếm request vào handler và duration** tại client adapter để biết số lần thực sự gọi upstream.
2. **Đếm exception được truyền ra** từ handler, phân loại timeout, lỗi kết nối, HTTP 5xx và lỗi nghiệp vụ.
3. **Đếm rejected/fallback outcomes** ở ranh giới lỗi với việc phân loại đúng exception từ native advice của phiên bản đang chạy.
4. **Ghi correlation ID** từ message flow để liên kết request và kết quả.
5. **Đo Gateway latency/error, retry attempts, queue và Aggregator group timeout** để biết ảnh hưởng của circuit đến hệ thống.
6. Nếu cần báo **state CLOSED/OPEN/HALF_OPEN chính xác**, dùng API/điểm mở rộng được phiên bản đang sử dụng hỗ trợ hoặc chọn implementation có state/events được công khai, thay vì tự suy diễn state từ số lỗi client.

Không nên tính “3 timeout gần nhất” trong một bộ đếm tự viết rồi báo state = OPEN nếu không đọc được state thật: advice có thể reset counter khi có một lần thành công, đang ở HALF_OPEN hoặc có lỗi đã bị retry/fallback che khuất. Cách đo suy diễn như vậy có thể không khớp state nội bộ của breaker.

## 8. Tracing và correlation qua Gateway, Router, Splitter/Aggregator

Trong một flow nhiều nhánh, event “stock-api OPEN” chỉ cho biết tình trạng của một breaker. Muốn biết request nào bị ảnh hưởng, cần thông tin message flow:

~~~mermaid
flowchart LR
    A[Gateway: correlation id] --> B{Router}
    B --> C[Stock breaker]
    B --> D[Pricing breaker]
    C --> E[Stock reply / UNAVAILABLE]
    D --> F[Pricing reply]
    E --> G[Aggregator]
    F --> G
    G --> H[Response / Error]
    C -.-> I[Trace / Log]
    D -.-> I
    G -.-> I
~~~

**Correlation ID** giúp theo dấu logical request qua các endpoint và message channel. Với **Splitter**, từng message con còn có sequence metadata và id nhánh. **Aggregator** dùng correlation/group semantics để tổng hợp; nếu một nhánh bị breaker từ chối mà không trả reply, group có thể tồn tại cho tới khi timeout.

Nên thu thập hoặc ghi log các trường sau ở những boundary liên quan:

| Trường | Ý nghĩa |
| --- | --- |
| **traceId / correlationId** | Nối các sự kiện thuộc một logical request |
| **messageId** | Xác định message cụ thể trong channel |
| **flow / endpoint name** | Nhánh EIP đã xử lý message |
| **breaker name** | Miền lỗi mà request đã đi qua |
| **operation / tenant group** | Ngữ cảnh được chuẩn hóa, không lộ dữ liệu nhạy cảm |
| **outcome** | FRESH, FALLBACK, UNAVAILABLE, REJECTED, ERROR |
| **exception category** | Timeout, connection, upstream 5xx, not-permitted |
| **duration và attempt count** | Phân biệt chậm vì upstream hay vì retry |
| **aggregator group / sequence status** | Điều tra nhóm thiếu reply |

Không nên giả định một header correlation là bí mật hoặc đủ để xác thực tenant. Header do client bên ngoài cung cấp cần được kiểm tra tại ingress; ngữ cảnh tenant/ủy quyền phải dựa trên identity đã xác thực.

### 8.1. Error channel không đồng nhất với breaker event

Trong Gateway **đồng bộ** dùng DirectChannel, exception từ Service Activator hoặc breaker thường có thể truyền ngược tới caller. Với flow **bất đồng bộ**, adapter hoặc poller có thể phát **ErrorMessage** vào error channel theo cấu hình.

Một event **OPEN** của breaker không nhất thiết tạo ErrorMessage: nó là thay đổi trạng thái của breaker. Ngược lại, **CallNotPermittedException** có thể được Gateway xử lý bằng fallback ngay, không phát bất kỳ ErrorMessage nào. Vì vậy:

- Đo **state transition** tại breaker.
- Đo **not-permitted** ở breaker.
- Đo **fallback/terminal outcome** ở Gateway hoặc handler boundary.
- Đo **ErrorMessage** ở error flow nếu có.
- Giữ correlation và phân loại lỗi để không đếm một sự cố thành nhiều lỗi upstream độc lập.

## 9. Retry, fallback và hàng đợi có thể che tình trạng OPEN

### 9.1. Retry che lỗi khi breaker nằm ngoài

Nếu breaker bao **ngoài Retry**, ba attempt lỗi rồi một attempt thành công có thể khiến breaker chỉ thấy success ở mức request logic. Metric **failed calls của breaker** thấp không có nghĩa HTTP client không phải thử nhiều lần. Cần thêm **retry_attempts** và **client_call_errors** ở adapter.

Nếu Retry bao **ngoài breaker**, từng attempt có thể tác động state. Khi breaker OPEN, retry phải **ngừng đối với lỗi từ chối**, không lặp vô ích. Đo attempts vào breaker và remote calls sẽ cho biết policy có hoạt động đúng hay không.

### 9.2. Fallback trả response nhưng vẫn phải báo suy giảm

Một fallback cache hợp lệ có thể giúp Gateway trả reply rất nhanh. Tuy nhiên ứng dụng cần phân biệt:

- **FRESH:** dữ liệu mới được lấy từ upstream.
- **STALE_REFERENCE:** cache còn trong TTL cho phép và được gắn nhãn tham khảo.
- **UNAVAILABLE:** không có dữ liệu đủ an toàn.

Nếu không đo **fallback_used** và **cache_age**, dashboard có thể hiện tỷ lệ response 200 rất cao trong khi dependency bị OPEN nhiều giờ. Không coi một reply stale là bằng chứng Stock API khỏe.

### 9.3. Queue có thể tăng dù breaker đang bảo vệ upstream

Với notification hoặc đồng bộ bất đồng bộ, khi breaker OPEN có thể đưa công việc vào durable queue/outbox để thử sau. Dù không gây thêm HTTP calls, số **pending messages** và **oldest message age** có thể tiếp tục tăng.

Nên đo **queue depth, age, attempts, dead-letter rate, backlog recovery throughput**; đặt giới hạn tiếp nhận hoặc backpressure. Nếu consumer cứ NACK/requeue tức thời, sẽ tạo vòng redelivery không có ích. Một ErrorMessage hoặc broker delivery mới không được mặc định là một lần dependency đã thực sự lỗi.

## 10. State theo từng endpoint, tenant và instance

Nếu ứng dụng có các breaker:

- **stock.read**
- **stock.reserve**
- **pricing.read**

thì mỗi breaker có thể có state riêng. Nếu một số tenant dùng quota/provider độc lập, có thể cần breaker theo **tenant group** hoặc tenant đã được xác thực với số lượng được kiểm soát. Không dùng chung một breaker vô tình cho mọi dependency, cũng không tạo breaker theo mọi SKU hay request ID.

Trong triển khai **nhiều pod**, các breaker **in-process** thường giữ state độc lập:

| Instance | Breaker stock-api | Điều quan sát được |
| --- | --- | --- |
| pod-1 | OPEN | Request tới pod-1 bị từ chối |
| pod-2 | CLOSED | Request tới pod-2 có thể tiếp tục gọi upstream |
| pod-3 | HALF_OPEN | Một số probe đang thử phục hồi |

Vì vậy một biểu đồ duy nhất “stock-api = CLOSED” không đại diện chính xác cho cả cluster nếu nó chỉ lấy state của một pod hoặc lấy giá trị cuối cùng không rõ nguồn.

Cách trình bày hữu ích hơn:

- **Phân bố số instance theo state**, kèm tên dependency.
- **State transition theo instance và thời gian**.
- **Tổng rejected calls theo breaker name**, có khả năng drill down theo pod.
- **Lưu lượng và latency upstream** để xác định sự cố chung hay cục bộ.
- **Nhãn rollout/version** khi cần đánh giá breaker chỉ lỗi trên một phiên bản ứng dụng.

Không mặc định Resilience4j tự đồng bộ state trên các pod. Nếu cần hạn chế quota trên phạm vi toàn cluster, phải bổ sung cơ chế kiểm soát chung như rate limiter phân tán hoặc cấu trúc tương đương, không coi breaker in-process là bộ điều phối toàn cục.

## 11. Ví dụ diễn tiến sự cố và những biểu đồ nên đi cùng

Giả sử Stock API timeout liên tục, breaker có wait duration 20 giây và các request tiếp tục đến:

| Thời điểm | Sự kiện | Các tín hiệu nên thấy |
| --- | --- | --- |
| 14:00:00 | Breaker đang CLOSED; gọi Stock API | Client calls, latency và outcomes bình thường |
| 14:00:03 | Lỗi đủ điều kiện OPEN | State transition CLOSED → OPEN, failed calls |
| 14:00:04 | 100 request mới đến | Not-permitted tăng; remote calls không tăng tương ứng |
| 14:00:10 | Gateway trả fallback cache | Fallback rate tăng, Gateway latency có thể thấp |
| 14:00:23 | Đủ thời gian chờ | Có cơ hội HALF_OPEN theo chính sách thư viện |
| 14:00:25 | Một request thăm dò thành công | Probe outcome thành công; chưa chắc đủ để CLOSED |
| 14:00:26 | Các probe đủ điều kiện phục hồi | State transition HALF_OPEN → CLOSED |
| 14:00:30 | Traffic bình thường trở lại | Remote calls và fresh outcomes tăng, rejected giảm |

Đây là một **kịch bản minh họa**; thời điểm chuyển và số probe cụ thể phụ thuộc thư viện, cấu hình, số request đến và thời gian lời gọi.

Nếu ở 14:00:26 một probe lại timeout, breaker có thể quay OPEN, tạo thêm sự kiện **HALF_OPEN → OPEN**. Khi lặp nhiều lần, có hiện tượng **state flapping**. Chỉ số state transition giúp phát hiện hiện tượng này tốt hơn chỉ nhìn current state.

## 12. Thiết kế cảnh báo có hành động cụ thể

Không nên cảnh báo trên mọi lỗi HTTP đơn lẻ. Hãy kết hợp **tình trạng breaker**, **mức độ ảnh hưởng người dùng** và **thời gian kéo dài**.

| Dấu hiệu | Cảnh báo nên nêu | Hướng xử lý ban đầu |
| --- | --- | --- |
| OPEN kéo dài trong giờ cao điểm | Dependency nào, bao nhiêu pod OPEN, tỉ lệ fallback/rejected | Kiểm tra upstream, credential, network, timeout |
| HALF_OPEN → OPEN lặp lại | Số lần transition và probe failures | Kiểm tra recovery, quá tải, timeout và số permit |
| Rejected tăng nhưng fallback có giới hạn | Tỷ lệ UNAVAILABLE và Gateway lỗi | Xem hợp đồng caller, cache TTL và fail-fast policy |
| Queue depth/age tăng liên tục | Số công việc tồn, tuổi lớn nhất | Giới hạn tiếp nhận, đánh giá backlog và DLQ |
| CLOSED nhưng timeout client tăng | Failure rate, minimum calls, retry attempts | Kiểm tra exception mapping, threshold, scope và retry |
| Chỉ một pod OPEN bất thường | Pod/region/version cụ thể | Điều tra lỗi môi trường cục bộ |
| State unknown / metrics mất | Mất quan sát một breaker đang được dùng | Kiểm tra instrumentation, export và monitoring pipeline |

Ví dụ **điều kiện cảnh báo minh họa** (không phải ngưỡng production mặc định):

- Một breaker **OPEN liên tục hơn 2 phút** *và* có request thật đang cần nó.
- Tỷ lệ **UNAVAILABLE** của Gateway vượt giới hạn SLO trong 5 phút.
- Số lần **HALF_OPEN → OPEN** lặp từ 3 lần trở lên trong 10 phút.
- **Queue oldest age** vượt thời hạn mà nghiệp vụ cho phép.
- Một breaker có **not-permitted calls rất cao nhưng state/transition metrics lại vắng mặt**.

Các ngưỡng cụ thể phải lấy từ SLO, lưu lượng, recovery time và mức độ quan trọng của dependency. Với service ít traffic, không có request mới sau OPEN chưa chắc là sự cố cần paging. Một cảnh báo state đơn độc nên bổ sung request volume và user-impact signal để tránh gây nhiễu.

## 13. Kiểm thử việc theo dõi trạng thái và sự kiện

Một test tốt phải chứng minh **trạng thái nội bộ, state-transition event và hành vi thực tế** khớp nhau. Không chỉ assert số log messages vì log có thể thay đổi format hoặc bị lấy mẫu.

### 13.1. JUnit 5: OPEN phát transition và chặn client

Ví dụ này dùng một fake supplier ném exception để đưa Resilience4j breaker tới OPEN. Event listener ghi nhận transition và số lần bị từ chối:

~~~java
@Test
void recordsTransitionAndRejectedCall() {
    CircuitBreakerConfig config = CircuitBreakerConfig.custom()
            .slidingWindowSize(2)
            .minimumNumberOfCalls(2)
            .failureRateThreshold(100.0f)
            .waitDurationInOpenState(Duration.ofMinutes(1))
            .build();

    CircuitBreaker breaker =
            CircuitBreaker.of("stock-test", config);

    List<String> transitions = new CopyOnWriteArrayList<>();
    AtomicInteger rejectedEvents = new AtomicInteger();
    AtomicInteger remoteCalls = new AtomicInteger();

    breaker.getEventPublisher()
            .onStateTransition(event ->
                    transitions.add(
                            event.getStateTransition().toString()
                    )
            )
            .onCallNotPermitted(event ->
                    rejectedEvents.incrementAndGet()
            );

    Supplier<String> failingClient = () -> {
        remoteCalls.incrementAndGet();
        throw new IllegalStateException("Stock API unavailable");
    };

    assertThrows(
            IllegalStateException.class,
            () -> breaker.executeSupplier(failingClient)
    );
    assertThrows(
            IllegalStateException.class,
            () -> breaker.executeSupplier(failingClient)
    );

    assertEquals(CircuitBreaker.State.OPEN, breaker.getState());
    assertTrue(transitions.contains("CLOSED_TO_OPEN"));
    assertEquals(2, remoteCalls.get());

    assertThrows(
            CallNotPermittedException.class,
            () -> breaker.executeSupplier(failingClient)
    );

    assertEquals(2, remoteCalls.get());
    assertEquals(1, rejectedEvents.get());
}
~~~

Đoạn code lược bỏ import, cần JUnit 5, Resilience4j và các kiểu concurrency từ Java. Test này xác minh một transition và một request bị chặn; **không** kiểm tra HTTP timeout thực hay logic phục hồi theo thời gian.

### 13.2. Ma trận test cần có

| Tình huống | Quan sát cần kiểm chứng |
| --- | --- |
| CLOSED, request thành công | State CLOSED; handler/client được gọi |
| Đủ lỗi mở breaker | Event CLOSED → OPEN, state OPEN |
| Request mới trong OPEN | Remote calls không tăng; not-permitted tăng |
| Hết wait duration và có request mới | Có cơ hội HALF_OPEN theo implementation |
| Probe thành công đủ điều kiện | HALF_OPEN → CLOSED, fresh calls phục hồi |
| Probe lỗi | HALF_OPEN → OPEN và rejected lại tăng |
| Retry ngoài breaker | Phân biệt retry attempts với remote calls |
| Fallback cache trả kết quả | Fallback metric tăng dù client không được gọi |
| Gateway đồng bộ phát exception | Outcome/latency đúng; không giả định có ErrorMessage |
| Error flow bất đồng bộ | Có cause và correlation message gốc |
| Splitter/Aggregator có nhánh OPEN | Partial/UNAVAILABLE/timeout và group không treo |
| Hai breaker độc lập | State của Stock OPEN không tự mở Pricing |
| Nhiều pod | State đúng theo từng instance, dashboard không gộp sai |
| Thiếu số mẫu trong sliding window | Failure rate không bị hiển thị thành 0% hợp lệ |
| Metrics export tắt | Có phát hiện mất telemetry, không báo giả dependency khỏe |

Ở integration test, dùng fake dependency có thể đổi giữa thành công, timeout, lỗi và phản hồi chậm; đếm lời gọi để xác minh breaker thực sự chặn request. Để kiểm tra vòng đời HALF_OPEN, dùng cấu hình wait ngắn riêng cho test hoặc cơ chế kiểm soát thời gian được thư viện hỗ trợ, tránh dựa vào sleep dài thiếu ổn định.

## 14. Checklist vận hành

- [ ] Có danh sách breaker theo dependency/endpoint/tenant group và owner rõ ràng.
- [ ] Theo dõi state hiện tại **và** transition events; không chỉ nhìn một metric HTTP error.
- [ ] Có successful, failed, slow, buffered, not-permitted/rejected calls.
- [ ] Không coi not-permitted là lỗi client đã thực thi, cũng không coi fallback thành công là upstream khỏe.
- [ ] Phân biệt failure rate thiếu số mẫu với failure rate thật bằng 0%.
- [ ] Nếu dùng Resilience4j, listener đăng ký một lần và Micrometer binder được kiểm tra bằng metric thực tế.
- [ ] Nếu dùng native advice, không suy diễn state chính xác từ counter tự viết; instrument handler, exception và outcomes.
- [ ] Gateway, Router, Filter, Transformer, Splitter/Aggregator và error channel giữ trace/correlation cần thiết.
- [ ] Có metric cho retry attempts, fallback rate, cache age, queue depth, DLQ và Aggregator timeouts.
- [ ] Dashboard phân biệt các pod và không giả định breaker state đồng bộ toàn cluster.
- [ ] Nhãn metric được giới hạn cardinality; tenant ID/request ID nhạy cảm không bị đưa vào metric công khai.
- [ ] Cảnh báo kết hợp OPEN duration, rejected calls và user impact, gắn với SLO.
- [ ] Test xác minh state transition, rejected event và remote call counter, không chỉ kiểm tra exception.
- [ ] Có runbook để điều tra upstream, timeout, retry, cấu hình breaker và khả năng phục hồi.

**Theo dõi trạng thái circuit** là theo dõi cả quyết định của bộ bảo vệ lẫn hệ quả của nó đối với message flow. Khi kết hợp state transitions, kết quả lời gọi, rejected calls, Gateway outcomes và correlation, ta biết breaker đã ngắt đúng dependency, hệ thống có thực sự giảm tải và người dùng có đang nhận kết quả đáng tin cậy hay không. Đây là nền tảng để vận hành Spring Integration an toàn, dễ kiểm thử và dễ mở rộng khi thêm Router, retry, error channel hoặc các nhánh xử lý mới.
