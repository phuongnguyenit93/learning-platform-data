# Điều kiện mở circuit

## 1. Điều gì thực sự khiến circuit breaker mở mạch?

Trong **Spring Integration**, luồng Enterprise Integration Patterns (EIP) thường nhận message qua Gateway, kiểm tra bằng Filter, chuẩn hóa bằng Transformer, phân nhánh bằng Router và gọi dependency ở Service Activator. Một API bên ngoài gặp lỗi liên tục có thể làm cả nhánh chậm, kể cả khi các bước được kết nối bằng message channel để giảm phụ thuộc.

**Circuit breaker chuyển từ CLOSED sang OPEN** khi các kết quả của những lần gọi dependency đã được cho phép đáp ứng một **chính sách mở mạch**. Sau đó, request mới bị từ chối sớm tại breaker nhằm giảm tải lên dependency đang bất ổn.

Điều kiện mở không nhất thiết là “một request lỗi thì mở”. Có ba chiến lược phổ biến:

1. **Lỗi liên tiếp**: ví dụ ba lần thực thi handler liên tiếp ném exception.
2. **Tỷ lệ lỗi (failure rate)**: ví dụ ít nhất 10 request đã được đo và 50% trong cửa sổ gần đây bị lỗi.
3. **Tỷ lệ lời gọi chậm (slow-call rate)**: ví dụ quá nhiều lần gọi vượt giới hạn độ trễ, dù có những lần cuối cùng vẫn thành công.

Spring Integration có **RequestHandlerCircuitBreakerAdvice** với mô hình đếm lỗi liên tiếp. Khi cần cửa sổ thống kê, failure rate hay slow-call rate, có thể dùng **Resilience4j** tại điểm gọi dependency. Hai cơ chế có cách tính khác nhau, nên phải xác định rõ thư viện đang dùng trước khi chọn ngưỡng.

~~~mermaid
flowchart TD
    A[Message đến handler] --> B{Breaker đang CLOSED?}
    B -->|Có| C[Gọi dependency]
    B -->|Không| X[Từ chối hoặc thăm dò theo trạng thái]
    C --> D[Quan sát response, exception, duration]
    D --> E[Phân loại thành công / lỗi / chậm]
    E --> F[Cập nhật bộ đếm hoặc cửa sổ]
    F --> G{Đạt điều kiện mở?}
    G -->|Chưa| H[Giữ CLOSED]
    G -->|Có| I[Chuyển OPEN]
~~~

**Điểm mấu chốt:** request vừa gây chạm ngưỡng đã được gọi tới dependency và thất bại. Các request **đến sau** mới bị chặn ở OPEN.

## 2. Định nghĩa kết quả nào được coi là lỗi

Điều kiện mở mạch có ý nghĩa khi nguồn dữ liệu đúng. Không phải mọi exception hay HTTP status đều chứng tỏ dependency đang không khỏe.

| Kết quả | Có nên tính là thất bại? | Lý do |
| --- | --- | --- |
| Connection refused hoặc lỗi kết nối | Thường có | Không thể hoàn tất lời gọi |
| Timeout khi tra tồn kho | Thường có | Dependency không đáp ứng trong giới hạn |
| HTTP 500/502/503 | Thường có | Dịch vụ ngoài không xử lý thành công |
| HTTP 400 do payload thiếu trường | Thường không | Lỗi đầu vào, nên lọc trước khi gọi |
| HTTP 404 nghĩa là SKU không tồn tại | Thường không | Có thể là kết quả nghiệp vụ bình thường |
| HTTP 429 | Tùy chính sách | Có thể cần backoff/rate limiting riêng |
| Lỗi NullPointerException tại Transformer | Không nên | Lỗi nội bộ, không phản ánh sức khỏe dependency |
| Gọi thành công nhưng rất chậm | Tùy breaker | Có thể ghi nhận slow call, chưa chắc là failure |

Nếu handler bắt exception rồi biến lỗi thành một đối tượng thành công giả, breaker bao bên ngoài sẽ không ghi nhận được lỗi:

~~~java
// Phản ví dụ: dependency lỗi nhưng handler lại trả bình thường.
StockResult lookup(StockQuery query) {
    try {
        return stockClient.lookup(query);
    } catch (Exception ex) {
        return new StockResult(query.sku(), false);
    }
}
~~~

Trong ví dụ này, giá trị **false** dễ bị hiểu thành “đã kiểm tra và hết hàng”, trong khi thực chất là “chưa thể kiểm tra tồn kho”. Nên biểu diễn trạng thái **TEMPORARILY_UNAVAILABLE** ở tầng fallback hoặc trả lỗi rõ ràng tới caller, sau khi breaker đã quan sát được thất bại.

Một API client cũng không nhất thiết ném exception khi nhận HTTP 503. Nếu handler trả response chứa status 503 như một giá trị bình thường, breaker đếm exception sẽ xem lần thực thi là thành công, trừ khi có bước chuyển thành lỗi hoặc một chính sách đánh giá return value.

## 3. Điều kiện mở theo lỗi liên tiếp

Với chính sách **ngưỡng 3 lỗi liên tiếp**, một lần thành công cắt đứt chuỗi lỗi. Ví dụ:

| Lần gọi | Kết quả từ handler | Số lỗi liên tiếp | State sau kết quả |
| --- | --- | ---: | --- |
| 1 | Timeout | 1 | CLOSED |
| 2 | Timeout | 2 | CLOSED |
| 3 | Thành công | 0 | CLOSED |
| 4 | Timeout | 1 | CLOSED |
| 5 | Timeout | 2 | CLOSED |
| 6 | Timeout | 3 | **OPEN** |
| 7 | Request mới | Không thực thi handler | **OPEN**, từ chối sớm |

Sự khác biệt quan trọng: một chuỗi “lỗi, thành công, lỗi, thành công” có thể khiến tỷ lệ lỗi khá cao, nhưng **không đạt ngưỡng liên tiếp**. Vì vậy đếm lỗi liên tiếp phù hợp với tình huống dependency hỏng hẳn trong nhiều request liền nhau, còn tỷ lệ lỗi phù hợp hơn khi lỗi xảy ra xen kẽ.

### 3.1. Cấu hình RequestHandlerCircuitBreakerAdvice

Ví dụ Spring Integration Java DSL dưới đây cho thấy cách bảo vệ một Service Activator. Các import được lược bớt để tập trung vào dòng message:

~~~java
public record StockQuery(String sku, int quantity) {}
public record StockResult(String sku, boolean available) {}

public interface StockClient {
    StockResult lookup(StockQuery query);
}

@MessagingGateway(defaultRequestChannel = "stock.requests")
public interface StockGateway {
    StockResult lookup(StockQuery query);
}

@Configuration
@EnableIntegration
@IntegrationComponentScan
public class StockFlowConfiguration {

    @Bean
    public RequestHandlerCircuitBreakerAdvice stockBreaker() {
        RequestHandlerCircuitBreakerAdvice advice =
                new RequestHandlerCircuitBreakerAdvice();
        advice.setThreshold(3);
        advice.setHalfOpenAfter(15_000); // milliseconds
        return advice;
    }

    @Bean
    public IntegrationFlow stockFlow(
            StockClient stockClient,
            RequestHandlerCircuitBreakerAdvice stockBreaker
    ) {
        return IntegrationFlow.from("stock.requests")
                .handle(
                        StockQuery.class,
                        (query, headers) -> stockClient.lookup(query),
                        endpoint -> endpoint.advice(stockBreaker)
                )
                .get();
    }
}
~~~

Luồng vận hành:

1. Gateway gửi **StockQuery** tới channel **stock.requests**.
2. Handler gọi **StockClient.lookup** và advice quan sát kết quả.
3. Khi đạt ngưỡng lỗi liên tiếp, breaker mở. Các message đến sau không được chuyển tới client trong thời gian OPEN.
4. Sau khoảng chờ cấu hình, breaker có cơ hội thăm dò việc phục hồi với request đến tiếp theo.

Giá trị **15_000** là thời gian chờ trước cơ hội thăm dò, **không phải timeout của request**. Connection timeout và read/response timeout vẫn phải đặt ở HTTP client.

Lưu ý **RequestHandlerCircuitBreakerAdvice** đếm lỗi ở ranh giới handler. Nếu lắp retry bên trong advice, một request nghiệp vụ có nhiều attempt có thể chỉ cho advice thấy kết quả cuối. Không được nhầm ngưỡng ba lỗi handler với ba exception mạng ở tầng sâu nếu các exception đã được retry rồi xử lý.

## 4. Điều kiện mở theo tỷ lệ lỗi (failure rate)

Khi dependency phản hồi thất thường, một cách đo khác là tính tỷ lệ lỗi trên cửa sổ thống kê:

\[
\text{Failure rate} =
\frac{\text{Số lời gọi được ghi nhận là thất bại}}
{\text{Tổng số lời gọi được đo trong cửa sổ}}
\times 100\%.
\]

**Resilience4j** hỗ trợ cửa sổ theo:

- **COUNT_BASED:** một số lượng lời gọi gần nhất, ví dụ 10 hoặc 100 request.
- **TIME_BASED:** các lời gọi trong một khoảng thời gian gần đây, ví dụ 30 giây.

Thông thường cần cấu hình thêm **minimumNumberOfCalls**. Đây là số mẫu tối thiểu trước khi quyết định mở mạch theo failure rate; nếu mẫu chưa đủ, một lỗi duy nhất dù tạo tỷ lệ 100% vẫn không đủ để kết luận dependency hỏng.

Giả sử cấu hình cửa sổ 10 lời gọi, tối thiểu 5 lời gọi và ngưỡng failure rate **50%**:

| Lời gọi đã ghi nhận | Lời gọi lỗi | Tỷ lệ | Có thể OPEN? |
| ---: | ---: | ---: | --- |
| 4 | 4 | 100% | Chưa, thiếu số mẫu tối thiểu |
| 5 | 2 | 40% | Chưa đạt ngưỡng |
| 6 | 3 | 50% | **Có**, nếu breaker đang CLOSED |
| 10 | 4 | 40% | Chưa đạt ngưỡng |
| 10 | 7 | 70% | **Có**, nếu breaker đang CLOSED |

Đây là **những kịch bản độc lập**, không phải các dòng nối tiếp trong cùng một lần chạy: nếu breaker đã OPEN ở một kịch bản, request bị chặn không tiếp tục đi vào cửa sổ như những lần gọi tới dependency thông thường.

Ví dụ Java:

~~~java
CircuitBreakerConfig config = CircuitBreakerConfig.custom()
        .slidingWindowType(
                CircuitBreakerConfig.SlidingWindowType.COUNT_BASED)
        .slidingWindowSize(10)
        .minimumNumberOfCalls(5)
        .failureRateThreshold(50.0f)
        .waitDurationInOpenState(Duration.ofSeconds(15))
        .permittedNumberOfCallsInHalfOpenState(2)
        .build();

CircuitBreaker stockBreaker =
        CircuitBreaker.of("stock-service", config);

// Chỉ bọc lời gọi dependency bên trong handler.
StockResult result = stockBreaker.executeSupplier(
        () -> stockClient.lookup(query)
);
~~~

Khi đủ mẫu và failure rate đạt từ 50% trở lên, Resilience4j có thể chuyển sang OPEN. Request bị từ chối bởi breaker có thể gây **CallNotPermittedException**; Gateway hoặc error flow phải có chính sách xử lý loại lỗi này.

Ở các hệ thống ít traffic, cửa sổ đếm có thể giữ kết quả cũ khá lâu trước khi đủ mẫu hoặc bị đẩy ra. Ở các hệ thống traffic cao, cửa sổ theo thời gian có thể chứa số lượng lớn request. Nên chọn cửa sổ dựa trên đặc tính lưu lượng và SLO, thay vì chọn một con số dùng chung cho mọi dependency.

## 5. Điều kiện mở vì lời gọi chậm

Một dependency có thể không ném exception nhưng mất vài giây để trả lời. Gateway vẫn bị chậm, thread vẫn bị chiếm và hàng đợi vẫn tăng. Khi đó, **tỷ lệ slow call** có thể là chỉ dấu sớm của sự cố.

Ví dụ Resilience4j:

~~~java
CircuitBreakerConfig config = CircuitBreakerConfig.custom()
        .slidingWindowSize(20)
        .minimumNumberOfCalls(10)
        .slowCallDurationThreshold(Duration.ofMillis(800))
        .slowCallRateThreshold(60.0f)
        .failureRateThreshold(50.0f)
        .build();
~~~

Sau khi có đủ 10 lời gọi được ghi nhận, nếu 6/10 lời gọi chậm hơn ngưỡng **800 ms**, slow-call rate đạt **60%** và breaker có thể OPEN, ngay cả khi phần lớn các lời gọi đó không ném exception. Một lời gọi vừa chậm vừa thất bại có thể xuất hiện trong cả thống kê slow và failed; **không cộng hai tỷ lệ với nhau** để ra điều kiện mở.

Phân biệt ba khái niệm:

| Cơ chế | Nhiệm vụ |
| --- | --- |
| Client timeout | Giới hạn thời gian một lời gọi mạng được phép chờ |
| Slow-call threshold | Đánh dấu lời gọi chậm phục vụ thống kê |
| Circuit breaker OPEN | Chặn **lời gọi mới** khi chỉ số thống kê vượt ngưỡng |

Slow-call threshold **không tự hủy một lời gọi chậm đang chạy**. Vì vậy, hệ thống vẫn cần timeout/deadline ở client và giới hạn đồng thời, đặc biệt khi dependency bị treo mà không trả kết quả.

Với native advice đếm lỗi liên tiếp, lời gọi chậm nhưng vẫn hoàn tất thành công thường không phải một exception để tăng bộ đếm; muốn mở theo độ chậm cần chính sách đo phù hợp.

## 6. Ghi nhận đúng exception và response

Một ngưỡng tốt cũng vô dụng nếu lỗi bị phân loại sai. Nên chia thành hai vùng:

~~~mermaid
flowchart LR
    A[Gateway] --> B[Validate / Filter]
    B -->|Hợp lệ| C[Transformer]
    C --> D[Circuit breaker]
    D --> E[External API]
    B -->|Không hợp lệ| F[Trả validation error]
~~~

**Trước breaker:** Filter/Validator từ chối SKU rỗng hoặc quantity âm, không tính lỗi input thành lỗi API tồn kho. Router giữ trách nhiệm lựa chọn nhánh nghiệp vụ.

**Bên trong vùng breaker:** chỉ bao phần thực thi có khả năng thất bại do dependency. Tránh để lỗi tại Transformer hoặc Aggregator góp vào thống kê của Stock API.

Resilience4j có cấu hình phân loại exception, ví dụ:

~~~java
CircuitBreakerConfig config = CircuitBreakerConfig.custom()
        .recordExceptions(
                java.io.IOException.class,
                java.util.concurrent.TimeoutException.class
        )
        .ignoreExceptions(BusinessValidationException.class)
        .build();
~~~

**BusinessValidationException** ở đây là class nghiệp vụ do ứng dụng định nghĩa. Khi dùng **recordExceptions**, cần kiểm tra exception thực tế mà HTTP client ném ra, bao gồm các wrapper exception, vì một lỗi kết nối có thể không mang đúng kiểu nguyên thủy mong đợi.

Các lưu ý vận hành:

- **HTTP 503** sẽ không được tính lỗi nếu handler nuốt status và trả dữ liệu bình thường, trừ khi đã chủ động cấu hình cách đánh giá return value.
- **HTTP 404** có thể là kết quả nghiệp vụ hợp lệ, tùy ý nghĩa API.
- **HTTP 429** có thể cần backoff và rate limiting; quyết định có record là lỗi breaker phụ thuộc vào trách nhiệm và hợp đồng của dependency.
- Một exception được **ignore** không nhất thiết có cùng tác động lên số mẫu và bộ đếm như một cuộc gọi thất bại; cần bám vào ngữ nghĩa implementation, không suy diễn từ tên exception.

## 7. Retry ảnh hưởng trực tiếp đến điều kiện mở

Với EIP, retry có thể triển khai dưới dạng advice quanh handler. Thứ tự đặt retry và breaker quyết định breaker đo **request logic** hay **attempt vật lý**.

~~~mermaid
flowchart LR
    A[Gateway] --> B[Circuit breaker]
    B --> C[Retry hữu hạn]
    C --> D[Dependency]
~~~

**Breaker bao ngoài retry:** một request được thử ba lần, cả ba thất bại, có thể chỉ tạo **một kết quả thất bại cuối cùng** mà breaker quan sát.

~~~mermaid
flowchart LR
    A[Gateway] --> B[Retry hữu hạn]
    B --> C[Circuit breaker]
    C --> D[Dependency]
~~~

**Retry bao ngoài breaker:** mỗi attempt có thể được breaker quan sát riêng. Một request có thể khiến breaker chạm ngưỡng nhanh hơn; sau khi OPEN, các lần retry tiếp tục chỉ nhận lỗi từ chối mà không giúp dependency phục hồi.

Với ngưỡng 3 lỗi liên tiếp và một request có 3 attempt đều timeout:

- Breaker bên ngoài retry: có thể ghi nhận **1** lần thất bại.
- Breaker bên trong retry: có thể ghi nhận đủ **3** lần thất bại.

Không có một thứ tự phù hợp cho mọi nghiệp vụ. Chọn theo đơn vị đo mong muốn và giới hạn số attempt; chỉ retry lỗi có khả năng phục hồi, có backoff hợp lý. Với lệnh ghi, cần **idempotency key** để không tạo tác dụng phụ lặp khi dependency đã xử lý request nhưng response bị thất lạc.

## 8. Chọn ngưỡng theo từng dependency

Nếu Router gửi một nhánh sang **Stock API** và một nhánh sang **Pricing API**, nên có breaker riêng. Hai dịch vụ có miền lỗi, lưu lượng và mức độ quan trọng khác nhau.

| Bối cảnh | Hướng chọn điều kiện mở |
| --- | --- |
| Dịch vụ traffic cao, lỗi xen kẽ | Failure rate theo sliding window và minimum calls |
| Dịch vụ traffic thấp | Ngưỡng lỗi liên tiếp hoặc sliding window/minimum calls cân đối |
| Dịch vụ thường chậm trước khi lỗi | Slow-call rate kết hợp timeout client |
| Nhiều lỗi nghiệp vụ được trả về bằng HTTP 4xx | Phân loại response/exception trước khi đếm |
| Dependency nhạy với bùng nổ retry | Giới hạn số attempt, backoff, rate limiter/bulkhead |
| Triển khai nhiều pod | Quan sát từng breaker instance; không giả định trạng thái được đồng bộ |

Một quy trình lựa chọn ngưỡng:

1. Đo error rate, timeout, throughput, latency p95/p99 khi hệ thống khỏe.
2. Xác định mức lỗi hoặc độ trễ khiến việc tiếp tục gọi có hại rõ rệt.
3. Chọn ngưỡng đủ nhạy để chặn sự cố, nhưng đủ số mẫu để tránh false positive.
4. Định nghĩa thời gian chờ trước HALF_OPEN và mức độ thăm dò khả năng phục hồi.
5. Thử các tình huống traffic thấp, cao, lỗi xen kẽ, lỗi kéo dài và phục hồi.

Ngưỡng quá thấp gây mở mạch do lỗi nhất thời. Ngưỡng quá cao khiến request tiếp tục timeout, chiếm thread và làm tăng queue. Mục tiêu là bảo vệ **flow tổng thể**, không chỉ giảm số lỗi ở riêng một client.

## 9. Khi điều kiện mở đã đạt: điều gì xảy ra với message?

~~~mermaid
flowchart TD
    A[Gateway] --> B{Router}
    B -->|Cần tồn kho| C[Stock breaker]
    C -->|CLOSED| D[Stock API]
    C -->|OPEN| E{Chính sách xử lý}
    E -->|Fail fast| F[Trả lỗi tạm không khả dụng]
    E -->|Có cache phù hợp| G[Trả kết quả stale có đánh dấu]
    E -->|Xử lý sau| H[Queue có idempotency key]
    B -->|Nhánh giá| I[Pricing API]
    D --> J[Response / Aggregator]
    G --> J
    I --> J
~~~

**Breaker OPEN không tự tạo fallback.** Trong Gateway đồng bộ qua DirectChannel, exception có thể nổi ngược về caller; trong flow bất đồng bộ hoặc endpoint dùng poller, lỗi có thể đi qua cơ chế **ErrorMessage/error channel** tùy cách cấu hình. Phải xác định rõ ranh giới xử lý lỗi thay vì cho rằng mọi exception đều tự chuyển sang error channel.

Nếu Splitter chia một message thành nhiều nhánh và một nhánh bị breaker từ chối, Aggregator có thể thiếu reply. Cần giữ **correlation ID**, sequence headers và có chính sách kết thúc nhóm: partial result, timeout hoặc đưa vào luồng xử lý lỗi. Một nhánh OPEN không được khiến Aggregator chờ vô hạn.

Kết quả fallback cần giữ ý nghĩa nghiệp vụ. **OUT_OF_STOCK** (hết hàng đã kiểm tra) khác **TEMPORARILY_UNAVAILABLE** (không thể kiểm tra do dependency không khả dụng).

## 10. Kiểm thử đúng điều kiện OPEN

Kiểm thử tốt nhất không chỉ assert lỗi ở Gateway mà còn xác minh **StockClient không bị gọi nữa** khi breaker OPEN.

### 10.1. Unit test cho failure rate của Resilience4j

Ví dụ JUnit 5 kiểm tra rằng 4 lần lỗi đủ mở mạch, còn request thứ năm bị từ chối ngay:

~~~java
@Test
void opensCircuitWhenFailureRateExceedsThreshold() {
    CircuitBreakerConfig config = CircuitBreakerConfig.custom()
            .slidingWindowSize(4)
            .minimumNumberOfCalls(4)
            .failureRateThreshold(50.0f)
            .waitDurationInOpenState(Duration.ofSeconds(30))
            .build();

    CircuitBreaker breaker = CircuitBreaker.of("stock-test", config);
    AtomicInteger clientCalls = new AtomicInteger();

    Supplier<String> failingClient = () -> {
        clientCalls.incrementAndGet();
        throw new IllegalStateException("dependency unavailable");
    };

    for (int i = 0; i < 4; i++) {
        assertThrows(
                IllegalStateException.class,
                () -> breaker.executeSupplier(failingClient)
        );
    }

    assertEquals(CircuitBreaker.State.OPEN, breaker.getState());
    assertThrows(
            CallNotPermittedException.class,
            () -> breaker.executeSupplier(failingClient)
    );
    assertEquals(4, clientCalls.get());
}
~~~

Test này có 4/4 lỗi, đủ minimum calls và vượt ngưỡng 50%. Khoảng OPEN là 30 giây để lần gọi thứ năm vẫn bị chặn trong vòng test. Ví dụ lược bỏ các import thông thường.

### 10.2. Ma trận kiểm thử integration flow

| Tình huống | Kết quả cần xác minh |
| --- | --- |
| Native advice: lỗi chưa đủ ngưỡng | CLOSED, request mới tiếp tục tới handler |
| Native advice: một thành công chen giữa | Chuỗi lỗi liên tiếp được tính lại phù hợp |
| Native advice: chạm ngưỡng | Request gây chạm ngưỡng đã vào client, request sau bị chặn |
| Resilience4j: tỷ lệ lỗi cao nhưng thiếu minimum calls | Chưa mở mạch |
| Resilience4j: failure rate đủ mẫu đạt ngưỡng | OPEN, số lần client gọi không tăng ở request bị từ chối |
| Slow-call rate chạm ngưỡng | OPEN nếu cấu hình chính sách đo độ chậm |
| Filter từ chối request sai | Không tính lỗi input là lỗi dependency |
| HTTP 503 được ánh xạ thành exception | Breaker ghi nhận thất bại |
| Retry bên trong và ngoài breaker | Số kết quả breaker thấy phù hợp vị trí advice |
| Splitter/Aggregator gặp nhánh OPEN | Có fallback, timeout hoặc lỗi có correlation |
| Một breaker trên nhiều instance | Không mặc định state đồng bộ giữa các pod |

Dùng fake client điều khiển được return, exception, thời gian phản hồi và call counter. Các bài kiểm thử Gateway nên chạy qua đúng handler và advice, tránh mock mất tầng cần xác minh.

## 11. Quan sát nguyên nhân OPEN và điều chỉnh

Vận hành production cần nhìn cả **nguyên nhân mở mạch** và **ảnh hưởng đến flow**:

| Tín hiệu | Giúp trả lời |
| --- | --- |
| Breaker state và state transition | Mạch nào mở, mở lúc nào, phục hồi chưa? |
| Failure count/rate, minimum calls, cửa sổ | Có đủ mẫu và đạt ngưỡng thật không? |
| Slow-call count/rate, latency | Dependency lỗi hay chỉ chậm bất thường? |
| Not-permitted/rejected calls | Bao nhiêu request đã bị chặn nhanh? |
| Exception class, HTTP status, timeout | Lỗi được phân loại đúng hay bị nuốt? |
| Gateway latency, channel queue depth | OPEN có giảm áp lực dây chuyền không? |
| Correlation/trace ID, pending Aggregator groups | Những nhánh message nào chịu ảnh hưởng? |

Resilience4j có event publisher và tích hợp metrics như Micrometer. Với native advice, cần kiểm tra instrumentation có sẵn của phiên bản Spring Integration đang dùng và bổ sung quan sát ở handler hoặc client; không mặc định mọi metric trên tự xuất hiện.

Nếu breaker **luôn CLOSED** dù dependency timeout nhiều, hãy kiểm tra: exception bị catch không, retry làm thay đổi đơn vị đếm không, ngưỡng quá cao không, hoặc minimum calls chưa đạt. Nếu breaker **OPEN quá thường xuyên** khi dịch vụ khỏe, kiểm tra phân loại lỗi nghiệp vụ, timeout quá ngắn hoặc sliding window có quá ít mẫu. Nếu lặp **OPEN → HALF_OPEN → OPEN**, cần xem mức độ phục hồi thực tế của dependency, thời gian chờ và chính sách probe.

## 12. Checklist triển khai

- [ ] Breaker bảo vệ đúng lời gọi dependency, không bao nhầm Filter, Transformer hoặc Aggregator.
- [ ] Xác định response/exception nào là lỗi hạ tầng, lỗi nghiệp vụ và slow call.
- [ ] Biết breaker đang đếm **lỗi liên tiếp**, **failure rate** hay **slow-call rate**.
- [ ] Nếu dùng sliding window, có minimum calls và thời gian/cỡ cửa sổ hợp lý.
- [ ] Có timeout thật tại client và giới hạn đồng thời khi dependency chậm.
- [ ] Xác định thứ tự retry với breaker, số attempt tối đa và idempotency.
- [ ] Gateway/error channel và Aggregator xử lý được nhánh OPEN, giữ correlation.
- [ ] Test chứng minh request đến sau khi OPEN **không làm tăng số cuộc gọi client**.
- [ ] Thu thập state transition, failed/slow/rejected calls để điều chỉnh ngưỡng theo SLO.

**Điều kiện mở circuit** là kết luận dựa trên những lời gọi dependency đã được quan sát theo một chính sách cụ thể. Chọn đúng loại tín hiệu, phạm vi đo và ngưỡng giúp Spring Integration bảo vệ nhánh xử lý lỗi, giữ Router, Gateway, Splitter và Aggregator hoạt động nhất quán và dễ theo dõi.
