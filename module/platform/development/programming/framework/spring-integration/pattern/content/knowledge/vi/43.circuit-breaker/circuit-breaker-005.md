# Timeout và lỗi làm tăng failure count

## 1. Vì sao phải hiểu chính xác failure count?

Trong module **SPRING_INTEGRATION_PATTERN**, Spring Integration kết nối các Enterprise Integration Patterns (EIP) thành một flow: Gateway nhận lời gọi, Filter kiểm tra message, Transformer chuẩn hóa payload, Router chọn nhánh và Service Activator gọi hệ thống bên ngoài. Việc trao đổi qua channel giúp các thành phần ít phụ thuộc hơn, nhưng một API tồn kho chậm hoặc thường xuyên thất bại vẫn có thể giữ thread, làm tăng hàng đợi và kéo dài thời gian phản hồi của Gateway.

**Circuit breaker** giải quyết một phần vấn đề bằng cách quan sát kết quả lời gọi dependency. Khi số lỗi hoặc tỷ lệ lỗi đạt ngưỡng, breaker chuyển từ **CLOSED** sang **OPEN**, ngăn lời gọi mới đi tới dependency. Sau một khoảng chờ, **HALF_OPEN** cho phép thăm dò để xác định có thể phục hồi hay chưa.

Muốn bảo vệ đúng flow, cần trả lời bốn câu hỏi:

1. Timeout có thực sự phát sinh **trong vùng được circuit breaker theo dõi** không?
2. Exception hoặc HTTP response nào được tính là lỗi của dependency?
3. **Failure count** là số lỗi **liên tiếp** hay số lần thất bại **trong cửa sổ thống kê**?
4. Retry, fallback và xử lý lỗi ở Gateway có làm thay đổi số kết quả breaker quan sát không?

Một timeout được ghi nhận sai có thể khiến breaker vẫn CLOSED dù API đang treo. Ngược lại, tính cả lỗi dữ liệu đầu vào có thể mở circuit dù dependency hoàn toàn khỏe.

## 2. Đường đi của một lời gọi và nơi lỗi được ghi nhận

~~~mermaid
flowchart TD
    A[Gateway nhận message] --> B[Filter / Validate]
    B -->|Hợp lệ| C[Transformer]
    B -->|Không hợp lệ| V[Trả validation error]
    C --> D{Router}
    D -->|Nhánh Stock| E[Circuit breaker]
    D -->|Nhánh Pricing| P[Breaker riêng cho Pricing]
    E -->|Cho phép| F[Service Activator]
    F --> G[HTTP client có timeout]
    G -->|Response hợp lệ| H[Handler thành công]
    G -->|Timeout / lỗi dependency| I[Handler ném exception]
    H --> J[Breaker ghi nhận success]
    I --> K[Breaker ghi nhận failure]
    E -->|OPEN| L[Từ chối nhanh]
    K --> M{Đạt ngưỡng?}
    M -->|Có| N[OPEN]
    M -->|Chưa| O[Giữ CLOSED]
    J --> Q[Reply / Aggregator]
    L --> R[Error / fallback boundary]
    R --> Q
~~~

Trong sơ đồ, các lỗi **được ném từ phần thực thi được breaker bao quanh** mới có cơ hội trở thành failure của breaker. Lỗi ở Filter diễn ra trước breaker; timeout của Gateway đang chờ reply có thể xảy ra ở tầng ngoài và **không đương nhiên** được ghi nhận thành lỗi dependency. Tương tự, lời gọi bị từ chối khi OPEN không giống một lần gọi dependency đã thất bại.

| Nơi phát sinh | Breaker bảo vệ StockClient có thấy không? |
| --- | --- |
| StockClient ném exception và exception đi ra khỏi handler | **Có**, theo chính sách ghi nhận exception |
| StockClient trả HTTP 503 nhưng handler coi là response thành công | **Không nhất thiết**; cần chuyển thành lỗi hoặc cấu hình đánh giá kết quả |
| Gateway chờ reply hết hạn trong khi worker bất đồng bộ vẫn chạy | **Không tự động**; timeout ở boundary Gateway có thể nằm ngoài handler |
| Validator từ chối quantity âm trước breaker | **Không**, và đó là hành vi mong muốn |
| Transformer sau handler phát sinh NullPointerException | **Không nên** tính thành lỗi Stock API |
| Breaker đang OPEN và từ chối một request mới | Được thống kê như request không được cấp phép; **không phải** lần gọi client thất bại |
| Handler catch exception rồi trả object “thành công” | Breaker có thể ghi nhận **success**, dù upstream thực sự hỏng |

Để quan sát đúng, cần đặt breaker **sát thao tác gọi dependency**. Không nên dùng một breaker bao trùm cả Router, Filter, Transformer và Aggregator.

## 3. Timeout nào sẽ làm tăng failure count?

“Timeout” là tên chung của nhiều giới hạn thời gian ở các tầng khác nhau. Cần biết tầng nào báo timeout và báo bằng cách nào.

| Loại timeout | Nó giới hạn gì? | Liên quan tới failure count |
| --- | --- | --- |
| **Connect timeout** | Thời gian thiết lập kết nối tới upstream | Nếu client ném lỗi ra khỏi handler, breaker có thể tính failure |
| **Read / response timeout** | Thời gian chờ dữ liệu hoặc phản hồi theo ngữ nghĩa của HTTP client | Exception đi qua breaker có thể được tính failure |
| **Request deadline** | Hạn xử lý tổng thể một lời gọi, nếu client hỗ trợ | Cần bảo đảm timeout thực sự làm lời gọi hoàn tất bằng lỗi |
| **Gateway reply timeout** | Thời gian Gateway chờ message trả về | Có thể chỉ xảy ra ở Gateway, ngoài vùng được breaker bảo vệ |
| **Poller / queue receive timeout** | Thời gian chờ có message để lấy ra xử lý | Không tự chứng minh dependency bên ngoài lỗi |
| **Breaker open wait duration** | Thời gian giữ OPEN trước cơ hội thăm dò HALF_OPEN | **Không phải timeout** của request mạng |
| **Slow-call duration threshold** | Ngưỡng đánh dấu một lời gọi chậm phục vụ thống kê | Chậm có thể làm tăng **slow-call count**, không nhất thiết tăng **failure count** |

**Ví dụ:** Gateway có reply timeout 1 giây, nhưng Stock HTTP client cho phép chờ 10 giây. Nếu request được xử lý ở worker bất đồng bộ, caller có thể đã nhận timeout sau 1 giây trong khi client vẫn đang chờ; breaker bao quanh handler chưa hề nhận exception. Vì vậy Gateway timeout không thay thế được client timeout.

Ngược lại, nếu StockClient chủ động ném exception do vượt deadline sau 800 ms, và exception đi ra khỏi handler được breaker theo dõi, breaker có thể ghi nhận một failure. Trong luồng đồng bộ, Gateway có thể nhận lại exception đó; trong luồng bất đồng bộ, lỗi có thể đi qua cơ chế ErrorMessage/error channel tùy endpoint và channel.

### 3.1. Timeout của từng request khác với chờ OPEN

~~~mermaid
sequenceDiagram
    participant G as Gateway
    participant B as Breaker CLOSED
    participant C as HTTP Client
    participant S as Stock API
    G->>B: Message 1
    B->>C: Cho phép gọi
    C->>S: Gửi request
    Note over C: Client deadline 800 ms
    S--xC: Không phản hồi đúng hạn
    C--xB: Timeout exception
    Note over B: Ghi nhận một failure
    B--xG: Truyền lỗi / fallback
    Note over B: Đủ ngưỡng thì OPEN
~~~

Breaker chỉ ghi nhận kết quả khi lời gọi được bảo vệ hoàn tất hoặc báo lỗi. Nếu client không có timeout và một call treo vô thời hạn, **không có sự kiện thất bại hoàn tất** để tăng bộ đếm theo cách thông thường. Cần timeout ở client và, với những lời gọi đồng thời lớn, cả giới hạn đồng thời/bulkhead.

**Slow-call threshold không tự hủy lời gọi chậm.** Một thư viện có thể ghi nhận lời gọi thành công nhưng quá chậm khi nó cuối cùng hoàn tất. Muốn dừng chờ, phải cấu hình timeout/deadline ở lớp thực thi hoặc dùng một cơ chế time limiter phù hợp.

## 4. Ánh xạ lỗi trước khi đưa vào breaker

Không nên coi mọi exception là một sự cố hạ tầng.

| Tình huống | Ví dụ | Chính sách đề xuất |
| --- | --- | --- |
| Lỗi kết nối | Connection refused, reset, DNS lỗi | Thường ghi nhận failure |
| Timeout upstream | Connect timeout, read timeout | Thường ghi nhận failure |
| Lỗi phía server | HTTP 500/502/503/504 | Thường ghi nhận failure sau khi ánh xạ response thành lỗi |
| Rate limit upstream | HTTP 429 | Cân nhắc ghi nhận failure, kết hợp backoff/rate limiting |
| Request sai | SKU rỗng, quantity âm | Validate trước breaker, không tính lỗi dependency |
| Không tìm thấy sản phẩm | HTTP 404 là kết quả nghiệp vụ hợp lệ | Trả kết quả “không tồn tại” thay vì exception |
| Tranh chấp nghiệp vụ | HTTP 409 theo hợp đồng domain | Xử lý riêng, không mặc định tính lỗi dependency |
| Lỗi lập trình | NullPointerException trong Transformer | Sửa bug; không để tác động đến breaker của dependency |
| Call bị breaker chặn | Not-permitted / circuit OPEN | Ghi nhận số lần bị từ chối riêng, không xem là một kết quả thực thi của client |

Việc phân loại phụ thuộc hợp đồng: cùng HTTP 404 có thể là “không có hàng” trong API tồn kho hoặc “endpoint không tồn tại” do cấu hình sai. Cần dựa trên semantics thực tế, không chỉ mã trạng thái.

### 4.1. Không nuốt exception trong phần được bảo vệ

~~~java
// Sai: breaker chỉ thấy một kết quả trả về bình thường.
StockResult lookup(StockQuery request) {
    try {
        return stockClient.lookup(request);
    } catch (Exception ex) {
        return new StockResult(request.sku(), false);
    }
}
~~~

Cách làm này vừa che lỗi khỏi failure count vừa nhầm “không thể kiểm tra tồn kho” thành “đã kiểm tra và không còn hàng”.

Thay vào đó, để dependency ném một **exception đã được phân loại** ra khỏi phần được breaker bảo vệ, rồi xử lý fallback ở boundary bên ngoài. Một outcome fallback nên phân biệt **FRESH**, **STALE_REFERENCE** và **UNAVAILABLE**, kèm correlation ID và nguyên nhân để downstream không diễn giải sai.

## 5. Spring Integration: đếm lỗi liên tiếp của handler

Spring Integration có **RequestHandlerCircuitBreakerAdvice**. Advice này được gắn vào endpoint handler; nó theo dõi các lần thực thi handler, và dùng **ngưỡng thất bại liên tiếp** để chuyển OPEN.

Giả sử ngưỡng là **3**:

| Request | Kết quả thực thi handler | Số lỗi liên tiếp sau request | Trạng thái sau request |
| --- | --- | ---: | --- |
| A | Timeout exception | 1 | CLOSED |
| B | Timeout exception | 2 | CLOSED |
| C | Thành công | 0 | CLOSED |
| D | HTTP 503 được chuyển thành exception | 1 | CLOSED |
| E | Connect timeout exception | 2 | CLOSED |
| F | Read timeout exception | 3 | **OPEN** |
| G | Đến khi OPEN, không được gọi client | Không tăng thêm một lần gọi dependency | **OPEN** |

Request F **đã vào client**, thất bại rồi mới làm circuit mở. Request G là request đầu tiên trong bảng bị từ chối sớm.

### 5.1. Ví dụ cấu hình advice

Các đoạn Java sau giả định đã khai báo Spring Integration Java DSL và component scan tương ứng; các import thông thường được lược bớt.

~~~java
public record StockQuery(String sku) {}

public record StockResult(String sku, boolean available) {}

public interface StockClient {
    StockResult lookup(StockQuery query);
}

@MessagingGateway(defaultRequestChannel = "stock.lookup.requests")
public interface StockGateway {
    StockResult lookup(StockQuery query);
}

@Configuration
@EnableIntegration
@IntegrationComponentScan
public class StockIntegrationConfig {

    @Bean
    public RequestHandlerCircuitBreakerAdvice stockBreakerAdvice() {
        RequestHandlerCircuitBreakerAdvice advice =
                new RequestHandlerCircuitBreakerAdvice();

        advice.setThreshold(3);
        advice.setHalfOpenAfter(15_000); // mili giây
        return advice;
    }

    @Bean
    public IntegrationFlow stockLookupFlow(
            StockClient client,
            RequestHandlerCircuitBreakerAdvice stockBreakerAdvice
    ) {
        return IntegrationFlow.from("stock.lookup.requests")
                .handle(
                        StockQuery.class,
                        (query, headers) -> client.lookup(query),
                        endpoint -> endpoint.advice(stockBreakerAdvice)
                )
                .get();
    }
}
~~~

Khi StockClient ném exception ra khỏi handler, advice có thể ghi nhận một thất bại. Khi circuit đã OPEN, handler không tiếp tục gọi StockClient cho các request bị từ chối. Giá trị **halfOpenAfter** quyết định thời gian chờ trước cơ hội thăm dò, không quy định HTTP request timeout.

Một instance advice giữ trạng thái của chính nó. Đừng chia sẻ cùng một instance cho các dependency độc lập nếu muốn sự cố Stock API không làm ngắt Pricing API. Trong hệ thống nhiều pod, mỗi instance thường có breaker state riêng; không giả định tự đồng bộ qua cluster.

### 5.2. Timeout có thể tạo exception như thế nào?

Ví dụ dưới dùng **java.net.http.HttpClient** của JDK. Giả sử endpoint thử nghiệm trả plain text **true** hoặc **false** cho status 200, trả 404 khi SKU không tồn tại, còn các status khác được xem là sự cố tích hợp trong ví dụ. API thực tế có thể trả JSON và cần parse theo hợp đồng của nó.

~~~java
public class StockDependencyException extends RuntimeException {
    public StockDependencyException(String message) {
        super(message);
    }

    public StockDependencyException(String message, Throwable cause) {
        super(message, cause);
    }
}

public class HttpStockClient implements StockClient {

    private final HttpClient http = HttpClient.newBuilder()
            .connectTimeout(Duration.ofMillis(500))
            .build();

    private final String baseUrl;

    public HttpStockClient(String baseUrl) {
        this.baseUrl = baseUrl;
    }

    @Override
    public StockResult lookup(StockQuery query) {
        String sku = URLEncoder.encode(
                query.sku(), StandardCharsets.UTF_8);

        HttpRequest request = HttpRequest.newBuilder(
                        URI.create(baseUrl + "/stock?sku=" + sku))
                .timeout(Duration.ofSeconds(2))
                .GET()
                .build();

        try {
            HttpResponse<String> response = http.send(
                    request, HttpResponse.BodyHandlers.ofString());

            if (response.statusCode() == 404) {
                return new StockResult(query.sku(), false);
            }

            if (response.statusCode() != 200) {
                throw new StockDependencyException(
                        "Unexpected Stock API status: "
                                + response.statusCode());
            }

            String body = response.body().trim();
            if (!body.equals("true") && !body.equals("false")) {
                throw new StockDependencyException(
                        "Invalid Stock API response body");
            }

            return new StockResult(
                    query.sku(), Boolean.parseBoolean(body));
        } catch (HttpTimeoutException timeout) {
            throw new StockDependencyException(
                    "Stock API timed out", timeout);
        } catch (IOException ioFailure) {
            throw new StockDependencyException(
                    "Stock API I/O failure", ioFailure);
        } catch (InterruptedException interrupted) {
            Thread.currentThread().interrupt();
            throw new StockDependencyException(
                    "Stock API call interrupted", interrupted);
        }
    }
}
~~~

Trong JDK HttpClient, connection timeout giới hạn việc tạo kết nối, còn timeout trên **HttpRequest** giới hạn thời gian dành cho request. **HttpTimeoutException** là một dạng IOException; bắt riêng trước IOException để phân biệt nguyên nhân timeout. Việc bắt **InterruptedException** rồi khôi phục cờ interrupt giữ được tín hiệu hủy của thread.

Đây là ví dụ minh họa đường phát sinh exception: **handler gọi StockClient → StockClient ném StockDependencyException → advice nhìn thấy lỗi**. Không dùng nó như một bộ HTTP adapter production hoàn chỉnh; cần thêm xử lý authentication, tracing, policy riêng cho 429/4xx, retry và dữ liệu JSON theo hợp đồng thực tế.

**Lưu ý về luồng thread:** nếu tầng ngoài đã hủy request hoặc time out trước khi HttpClient hoàn tất, việc breaker ghi nhận failure còn phụ thuộc liệu thao tác được bảo vệ có thực sự hoàn tất bằng exception hay không. Không thể chỉ cấu hình timeout tại Gateway rồi kết luận failure count sẽ tăng.

## 6. Resilience4j: failed calls trong sliding window

Resilience4j cung cấp CircuitBreaker dựa trên **failure rate** và có thể mở mạch theo **slow-call rate**. Khác với bộ đếm lỗi liên tiếp của native advice, Resilience4j lưu các kết quả trong cửa sổ thống kê.

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
        CircuitBreaker.of("stock-api", config);

StockResult result = stockBreaker.executeSupplier(
        () -> stockClient.lookup(query)
);
~~~

Trong ví dụ:

- **slidingWindowSize(10)**: thống kê tối đa 10 lời gọi gần đây trong CLOSED.
- **minimumNumberOfCalls(5)**: phải có đủ số mẫu trước khi failure rate được dùng để quyết định mở.
- **failureRateThreshold(50.0f)**: khi đã đủ mẫu và tỷ lệ thất bại đạt ngưỡng, breaker có thể OPEN.
- **waitDurationInOpenState(15 giây)**: thời gian chờ trước cơ hội thăm dò, không phải deadline của HttpClient.
- **permittedNumberOfCallsInHalfOpenState(2)**: giới hạn số lời gọi thử trong HALF_OPEN.

Công thức:

\[
\text{Failure rate} =
\frac{\text{Lời gọi được ghi nhận thất bại trong cửa sổ}}
{\text{Tổng lời gọi được ghi nhận trong cửa sổ}}
\times 100\%.
\]

| Số kết quả trong cửa sổ | Số kết quả thất bại | Failure rate | Có đủ điều kiện mở? |
| ---: | ---: | ---: | --- |
| 4 | 4 | 100% | **Chưa**, thiếu minimumNumberOfCalls |
| 5 | 2 | 40% | Chưa đạt 50% |
| 6 | 3 | 50% | **Có**, nếu breaker còn CLOSED |
| 10 | 4 | 40% | Chưa đạt 50% |
| 10 | 7 | 70% | **Có**, nếu breaker còn CLOSED |

Các dòng là **kịch bản độc lập**, không phải lịch sử nối tiếp của một breaker sau khi nó đã OPEN.

### 6.1. Failed call khác not-permitted call

Khi breaker đang OPEN, Resilience4j có thể ném **CallNotPermittedException** thay vì thực thi supplier. Lời gọi này được thống kê như **not permitted / rejected**, không phải một lần StockClient đã thực thi rồi thất bại trong cửa sổ CLOSED.

Do đó cần quan sát **hai loại tín hiệu**: số failed calls cho biết kết quả lời gọi được phép, còn not-permitted calls cho biết lượng traffic đang bị breaker bảo vệ bằng cách từ chối.

Nếu chỉ đếm exception bắt được tại Gateway mà không phân loại, bạn có thể vô tình cộng cả **CallNotPermittedException** vào “lỗi mới của Stock API”, dù API chưa hề nhận các request đó.

### 6.2. Chậm không nhất thiết là thất bại

Resilience4j có thể thêm chính sách mở mạch vì lời gọi chậm:

~~~java
CircuitBreakerConfig config = CircuitBreakerConfig.custom()
        .slidingWindowSize(20)
        .minimumNumberOfCalls(10)
        .slowCallDurationThreshold(Duration.ofMillis(800))
        .slowCallRateThreshold(60.0f)
        .failureRateThreshold(50.0f)
        .build();
~~~

Một lời gọi mất 1.200 ms nhưng trả kết quả hợp lệ có thể là **successful slow call**. Nó góp vào thống kê lời gọi chậm, nhưng không tự trở thành **failed call**. Một lời gọi timeout sau 2 giây có thể vừa **chậm** vừa **thất bại**, tùy cấu hình và kết quả được ghi nhận.

Không cộng failure rate và slow-call rate lại với nhau để quyết định OPEN. Hai điều kiện được đánh giá riêng theo implementation.

## 7. Chỉ định exception được record và ignore

Với Resilience4j, có thể cấu hình những loại exception được coi là lỗi hoặc cần bỏ qua khi đánh giá.

~~~java
CircuitBreakerConfig config = CircuitBreakerConfig.custom()
        .recordExceptions(
                StockDependencyException.class,
                java.net.SocketTimeoutException.class
        )
        .ignoreExceptions(BusinessValidationException.class)
        .build();
~~~

**BusinessValidationException** ở đây là một kiểu exception do ứng dụng tự định nghĩa. Đây là ví dụ chính sách, không phải danh sách đầy đủ lỗi của mọi HTTP client.

Cần đọc kỹ semantics của thư viện khi dùng **recordExceptions**: các exception không nằm trong danh sách được record có thể được xem là lời gọi thành công về mặt thống kê, trừ khi chúng được cấu hình bỏ qua. Điều này có thể làm sai failure rate nếu một lỗi mạng được bọc thành kiểu exception khác danh sách đã chọn.

Nếu cần linh hoạt hơn, có thể dùng **recordException** hoặc **ignoreException** predicate theo contract cụ thể của ứng dụng. Ưu tiên ánh xạ exception của HTTP client về một hoặc một số loại **StockDependencyException** ở adapter, để policy breaker không lệ thuộc vào mọi kiểu lỗi của thư viện truyền tải.

**Đừng che lỗi ứng dụng bằng fallback đại trà.** Ví dụ một NullPointerException do bug tại Transformer không nên bị chuyển thành StockDependencyException chỉ để tất cả lỗi cùng đi qua một handler. Điều này khiến breaker đếm sai và làm việc chẩn đoán khó hơn.

## 8. Retry có thể nhân số attempt nhưng thay đổi failure count

Giả sử một yêu cầu nghiệp vụ có thể thử lại tối đa 3 lần. Thứ tự lắp advice quyết định breaker quan sát **một request logic** hay **từng attempt vật lý**.

### 8.1. Breaker bao ngoài retry

~~~mermaid
flowchart LR
    G[Gateway] --> B[Breaker]
    B --> R[Retry tối đa 3 lần]
    R --> C[StockClient]
~~~

Nếu cả ba attempt đều timeout, breaker bên ngoài có thể chỉ quan sát **một lần thực thi cuối cùng bị lỗi**. Nếu lần thứ ba thành công, breaker có thể chỉ thấy một kết quả thành công cho request đó.

### 8.2. Retry bao ngoài breaker

~~~mermaid
flowchart LR
    G[Gateway] --> R[Retry tối đa 3 lần]
    R --> B[Breaker]
    B --> C[StockClient]
~~~

Ở thứ tự này, từng attempt có thể góp vào bộ đếm failure. Với ngưỡng 3 lỗi liên tiếp, một request nghiệp vụ có thể khiến circuit OPEN sau ba attempt. Những attempt sau khi OPEN chỉ nhận lỗi từ chối; **không nên retry mù quáng các lỗi do breaker không cấp phép**.

| Tiêu chí | Breaker ngoài retry | Retry ngoài breaker |
| --- | --- | --- |
| Đơn vị breaker thường thấy | Kết quả cuối cùng của một request logic | Từng attempt đi qua breaker |
| Một request thử ba lần đều lỗi | Có thể đóng góp 1 failure | Có thể đóng góp 3 failures |
| Kết quả cuối cùng thành công | Có thể được ghi nhận là success | Có thể đã ghi nhận các attempt lỗi trước đó |
| Tác động đến tốc độ mở | Có thể mở chậm hơn theo số request | Có thể mở nhanh theo số attempt |
| Điều cần kiểm soát | Retry không quá nhiều, deadline tổng thể | Không retry not-permitted và không khuếch đại traffic |

Không có thứ tự phù hợp cho mọi hệ thống. Chọn dựa trên đối tượng cần đánh giá và mục tiêu bảo vệ, rồi kiểm thử thứ tự advice thực tế.

Nếu retry thao tác ghi như trừ tồn kho hoặc tạo đơn, timeout không chứng minh request chưa được phía nhận xử lý. Phải có **idempotency key** và cơ chế chống xử lý trùng trước khi cho retry hoặc replay message.

## 9. Gateway, error channel và correlation có thể che mất nguyên nhân

### 9.1. Lỗi đồng bộ và bất đồng bộ

Với Gateway đồng bộ qua **DirectChannel**, exception từ handler/advice có thể truyền thẳng về caller. Trong flow có **ExecutorChannel**, poller hoặc adapter bất đồng bộ, exception có thể được đưa vào **ErrorMessage** theo cơ chế error channel tương ứng. Một error channel được khai báo không có nghĩa mọi lỗi đồng bộ tự chuyển sang error flow.

**Điểm đặt breaker** cần đi theo lời gọi dependency thực sự. Ví dụ một Gateway timeout vì phải chờ Aggregator đủ ba nhánh không chứng minh Stock API timeout. Nếu tăng failure count của Stock API chỉ vì Gateway chờ Aggregator, ta sẽ mở mạch sai dependency.

### 9.2. Splitter và Aggregator

Splitter có thể tạo nhiều message con, mỗi message gọi một dependency. Nếu một nhánh bị breaker chặn hoặc timeout, Aggregator có thể không nhận đủ reply. Cần:

- Giữ **correlation ID**, sequence headers và định danh nhánh trong cả kết quả thành công, lỗi và fallback.
- Xác định **group timeout**, partial result, expired-group handling và discard/error path rõ ràng.
- Tránh để nhóm Aggregator chờ vô thời hạn khi circuit của một nhánh đang OPEN.
- Không tính một timeout ở Aggregator thành failure của client khi không có bằng chứng lời gọi client đã thất bại.

### 9.3. Router và Filter

Router giúp cách ly các nhánh Stock, Pricing, Shipping; mỗi miền lỗi nên có breaker riêng. Filter và Validator cần loại dữ liệu sai **trước** điểm gọi dependency. Transformer chuyển đổi payload nên đứng ngoài phạm vi đếm lỗi của breaker dành riêng cho API bên ngoài, trừ khi bản thân việc chuyển đổi chính là một phần của lời gọi dependency có chủ đích.

~~~mermaid
flowchart LR
    A[Gateway] --> B[Filter]
    B --> C[Transformer]
    C --> D{Router}
    D --> E[Stock breaker]
    D --> F[Pricing breaker]
    E --> G[Stock service]
    F --> H[Pricing service]
~~~

## 10. Kiểm thử: chứng minh failure count tăng đúng lúc

Chỉ kiểm tra Gateway ném exception là chưa đủ. Một bài test Circuit Breaker cần kiểm tra **số lần thực sự gọi dependency** trước và sau khi OPEN.

### 10.1. Ví dụ JUnit 5 với Resilience4j

Đoạn test sau minh họa 4 lần lỗi có thể mở mạch, và lời gọi thứ năm **không vào client**:

~~~java
@Test
void timeoutsOpenBreakerAndRejectNextCall() {
    CircuitBreakerConfig config = CircuitBreakerConfig.custom()
            .slidingWindowSize(4)
            .minimumNumberOfCalls(4)
            .failureRateThreshold(50.0f)
            .waitDurationInOpenState(Duration.ofSeconds(30))
            .build();

    CircuitBreaker breaker = CircuitBreaker.of("stock-test", config);
    AtomicInteger remoteCalls = new AtomicInteger();

    Supplier<StockResult> failingClient = () -> {
        remoteCalls.incrementAndGet();
        throw new StockDependencyException(
                "request timed out",
                new java.net.SocketTimeoutException());
    };

    for (int i = 0; i < 4; i++) {
        assertThrows(
                StockDependencyException.class,
                () -> breaker.executeSupplier(failingClient)
        );
    }

    assertEquals(CircuitBreaker.State.OPEN, breaker.getState());
    assertEquals(4, remoteCalls.get());

    assertThrows(
            CallNotPermittedException.class,
            () -> breaker.executeSupplier(failingClient)
    );
    assertEquals(4, remoteCalls.get());
}
~~~

Test này dùng exception mô phỏng timeout, không gọi mạng thật. Bốn lời gọi đầu được phép thực thi và thất bại; lời gọi sau bị breaker từ chối ngay. Khi kiểm thử riêng timeout của HTTP client, cần thêm integration test có server giả lập chậm hoặc chủ động đóng kết nối để xác minh adapter thực sự ném đúng exception.

### 10.2. Ma trận kiểm thử flow

| Tình huống | Kết quả mong đợi |
| --- | --- |
| Native advice: lỗi liên tiếp chưa đủ ngưỡng | CLOSED, handler tiếp tục được gọi |
| Native advice: một lần thành công giữa chuỗi lỗi | Bộ đếm lỗi liên tiếp được tính lại |
| Native advice: đạt ngưỡng | Lời gọi gây chạm ngưỡng đã vào client; lời gọi sau bị chặn |
| Resilience4j: 4/4 lỗi, minimum calls = 5 | Chưa OPEN do chưa đủ số mẫu |
| Resilience4j: tỷ lệ lỗi đạt 50% khi đã đủ mẫu | OPEN |
| HTTP 503 được trả dạng dữ liệu thường | Breaker không tăng failure nếu không có bước ghi nhận lỗi |
| HTTP 503 được adapter ánh xạ thành exception | Breaker ghi nhận failure |
| Validation bị Filter từ chối | Không gọi client, không tăng failure dependency |
| Gateway timeout nhưng client vẫn đang chạy | Không mặc định coi là failure của client |
| Client timeout thực sự ném exception | Failure được ghi nhận theo chính sách |
| Breaker OPEN | Request mới bị từ chối, **remote call counter không tăng** |
| Retry trước/sau breaker | Kết quả đếm theo đúng đơn vị logical call/attempt |
| Fallback ngoài breaker | Vẫn có metric failure và trả outcome suy giảm |
| Splitter/Aggregator có nhánh timeout | Giữ correlation, kết thúc group theo policy, không treo |

Các test phụ thuộc thời gian nên dùng clock/test configuration phù hợp hoặc timeout ngắn riêng trong test. Tránh dùng những vòng sleep dài để đo ngưỡng OPEN; test dễ chậm, phụ thuộc scheduler và khó tái hiện.

## 11. Quan sát failure count và phát hiện cấu hình sai

Nên theo dõi ít nhất các tín hiệu sau theo **dependency** và **breaker name**:

| Tín hiệu | Câu hỏi cần trả lời |
| --- | --- |
| Breaker CLOSED / OPEN / HALF_OPEN | Circuit đang ở đâu trong vòng đời? |
| Failure count hoặc failure rate | Có đủ lỗi đã quan sát để mở mạch chưa? |
| Successful calls | Có lần thành công xen giữa lỗi không? |
| Not-permitted / rejected calls | Bao nhiêu request bị chặn ngay khi OPEN? |
| Timeout type và exception class | Timeout phát sinh ở HTTP client, Gateway hay Aggregator? |
| Slow calls, latency p95/p99 | Dependency chỉ chậm hay thực sự thất bại? |
| Retry attempts per logical request | Retry có khuếch đại số attempt và ảnh hưởng failure count không? |
| Gateway error/latency, channel queue depth | Breaker có giảm nghẽn của flow không? |
| Correlation ID và error channel outcome | Lỗi thuộc nhánh nào và message gốc là gì? |

Resilience4j có thể phát sự kiện circuit breaker và tích hợp **Micrometer** để đo trạng thái, kết quả được phép, lời gọi bị từ chối và chuyển trạng thái. Với native advice, cần kiểm tra instrumentation thực có của phiên bản Spring Integration đang dùng; khi cần, bổ sung metrics ở handler, client và Gateway để phân biệt timeout theo tầng.

Một số dấu hiệu thường gặp:

- **Breaker vẫn CLOSED dù HTTP client liên tục timeout:** exception có thể đã bị catch, timeout xảy ra ở Gateway bên ngoài advice, retry che kết quả hoặc ngưỡng/minimum calls chưa đạt.
- **Breaker OPEN dù dependency khỏe:** có thể đang đếm nhầm lỗi validation, exception từ Transformer hoặc chọn timeout quá ngắn.
- **Failed calls ít nhưng Gateway báo nhiều lỗi:** có thể nhiều request bị từ chối khi OPEN hoặc Gateway timeout do queue/Aggregator.
- **OPEN rồi HALF_OPEN rồi OPEN liên tục:** dependency chưa phục hồi ổn định hoặc thời gian chờ và policy thăm dò chưa phù hợp.

## 12. Checklist thiết kế và kiểm tra

- [ ] Breaker bao sát điểm gọi dependency, không bao nhầm toàn bộ message flow.
- [ ] Client có connect timeout, request/response timeout hoặc deadline theo SLA.
- [ ] Timeout làm handler hoàn tất bằng exception hoặc tín hiệu được breaker nhận diện.
- [ ] Đã phân loại HTTP status, exception hạ tầng và lỗi nghiệp vụ; lỗi validate được xử lý trước breaker.
- [ ] Hiểu native advice đếm lỗi **liên tiếp**, còn Resilience4j có thể tính **failure rate trong sliding window**.
- [ ] Đã chọn minimum calls, failure threshold, slow-call threshold và wait duration theo traffic thực tế.
- [ ] Không nhầm lời gọi **not permitted** với lần gọi dependency đã thất bại.
- [ ] Biết retry nằm trước hay sau breaker và số attempt thực sự được đo.
- [ ] Fallback không nuốt lỗi trước khi breaker ghi nhận; outcome suy giảm có trạng thái rõ.
- [ ] Gateway, error channel, Router, Splitter và Aggregator giữ được correlation và đường lỗi.
- [ ] Test số lần gọi client khi CLOSED/OPEN, test exception mapping và trường hợp timeout ở Gateway.
- [ ] Metrics phân biệt timeout của dependency, lỗi upstream, denied calls, slow calls và lỗi nghiệp vụ.

**Timeout và lỗi chỉ làm tăng failure count khi chúng được breaker quan sát và được chính sách ghi nhận coi là thất bại.** Trong Spring Integration, thiết kế đúng ranh giới handler, timeout, retry và fallback giúp mở circuit kịp thời khi dependency hỏng, đồng thời tránh ngắt nhầm các nhánh xử lý vẫn đang khỏe.
