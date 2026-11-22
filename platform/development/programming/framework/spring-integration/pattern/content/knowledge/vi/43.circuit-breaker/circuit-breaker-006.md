# Reset circuit và thời gian chờ

## 1. Circuit breaker phục hồi như thế nào sau khi mở?

Trong **SPRING_INTEGRATION_PATTERN**, các Enterprise Integration Patterns được ghép thành luồng message bằng Spring Integration: Gateway tiếp nhận yêu cầu, Filter xác thực dữ liệu, Transformer chuẩn hóa payload, Router chọn nhánh, Service Activator gọi dependency và có thể dùng Splitter/Aggregator để phối hợp kết quả. Cấu trúc channel giúp các thành phần ít phụ thuộc hơn, nhưng một dependency bị lỗi có thể khiến handler giữ thread lâu, tăng queue và làm chậm cả flow.

Khi dependency liên tục lỗi, **circuit breaker** chuyển sang **OPEN** để từ chối nhanh các cuộc gọi mới. Nhưng dịch vụ bên ngoài có thể được khôi phục sau vài giây. Nếu circuit không có cơ chế thử lại và đóng mạch, các message sẽ tiếp tục bị từ chối dù dependency đã khỏe.

Đó là lý do cần hiểu **thời gian chờ trước khi thăm dò**, **trạng thái HALF_OPEN** và **reset circuit**. Chúng liên quan nhau nhưng không phải một hành động:

- **Chờ ở OPEN:** giữ việc từ chối lời gọi mới trong một khoảng thời gian cấu hình.
- **Thăm dò ở HALF_OPEN:** cấp quyền cho một số lời gọi mới đi qua để đánh giá sức khỏe dependency.
- **Tự phục hồi về CLOSED:** kết quả thăm dò đáp ứng chính sách phục hồi của breaker; traffic trở lại bình thường.
- **Reset thủ công:** thao tác quản trị chủ động đưa breaker về trạng thái và bộ thống kê ban đầu, bỏ qua kết luận bảo vệ hiện tại. Chỉ nên dùng khi có lý do vận hành rõ ràng.

Bài này tập trung vào hành vi đó trong flow Spring Integration, phân biệt cơ chế native **RequestHandlerCircuitBreakerAdvice** và **Resilience4j**, rồi thực hành cấu hình, kiểm thử và giám sát.

## 2. Vòng đời CLOSED → OPEN → HALF_OPEN → CLOSED

~~~mermaid
stateDiagram-v2
    [*] --> CLOSED
    CLOSED --> OPEN: Lỗi đạt điều kiện mở mạch
    OPEN --> HALF_OPEN: Đủ thời gian chờ và có cơ chế chuyển trạng thái
    HALF_OPEN --> CLOSED: Probe đáp ứng điều kiện phục hồi
    HALF_OPEN --> OPEN: Probe cho thấy dependency còn lỗi
    OPEN --> CLOSED: Reset thủ công có chủ đích
    HALF_OPEN --> CLOSED: Reset thủ công có chủ đích
~~~

| Trạng thái | Lời gọi mới | Điều kiện chuyển đi |
| --- | --- | --- |
| **CLOSED** | Được phép thực thi và được thống kê | Đủ lỗi hoặc lời gọi chậm theo chính sách thì **OPEN** |
| **OPEN** | Bị chặn trước khi tới dependency | Hết thời gian chờ thì **có cơ hội** đi tới HALF_OPEN |
| **HALF_OPEN** | Chỉ một số lời gọi thăm dò được phép; các lời gọi khác có thể bị từ chối | Kết quả probe làm **CLOSED** hoặc trở lại **OPEN** |

Sơ đồ thể hiện vòng đời thông thường. Số probe cần thiết, cách tổng hợp kết quả và thời điểm chuyển chính xác phụ thuộc implementation.

**Quan trọng:** hết thời gian chờ không có nghĩa circuit đã xác nhận dependency khỏe. Mạch cần **kết quả thăm dò** trước khi quyết định quay CLOSED. Nếu không có traffic, một số triển khai vẫn giữ trạng thái OPEN cho tới khi có request tiếp theo.

Một breaker là bộ điều khiển **trạng thái cho các lời gọi đến tương lai**. Nó không tự sửa kết nối đã lỗi, không tự khởi động lại dependency và không mặc định hủy các request đã được cho qua trước lúc mở mạch.

## 3. Bốn loại thời gian dễ bị nhầm

| Thời gian | Đo ở đâu? | Ý nghĩa |
| --- | --- | --- |
| **Connect timeout** | HTTP/gRPC/DB client | Giới hạn thời gian thiết lập kết nối |
| **Read/response timeout hoặc deadline** | Client gọi dependency | Giới hạn thời gian chờ một lời gọi cụ thể |
| **OPEN wait duration / halfOpenAfter** | Circuit breaker | Khoảng chờ trước khi được phép thăm dò |
| **HALF_OPEN maximum wait** | Breaker có hỗ trợ cấu hình này | Giới hạn thời gian chờ thu đủ kết quả probe, tùy implementation |
| **Gateway reply timeout** | Gateway / kênh reply | Giới hạn thời gian caller chờ message trả về |
| **Aggregator group timeout** | Aggregator | Giới hạn thời gian nhóm message chờ đủ thành phần |

Không dùng cùng một giá trị vì các đồng hồ giải quyết những vấn đề khác nhau.

Ví dụ:

- Stock HTTP client có timeout mỗi request là **2 giây**.
- Breaker chuyển OPEN và chờ **20 giây** trước cơ hội thăm dò.
- Gateway đồng bộ có giới hạn chờ riêng, tương thích với budget xử lý toàn flow.
- Aggregator có group timeout cho trường hợp một nhánh không trả message.

Nếu chỉ tăng OPEN wait từ 20 lên 60 giây, **lời gọi mạng được phép thực thi vẫn có thể treo** khi client thiếu timeout. Nếu chỉ giảm Gateway reply timeout xuống 1 giây, breaker bao quanh một handler bất đồng bộ chưa chắc đã quan sát được failure ở đúng thời điểm Gateway ngừng chờ.

### 3.1. Đo thời gian chờ từ đâu?

Đối với cấu hình kiểu **waitDurationInOpenState**, mốc thực tế thường gắn với lúc circuit **chuyển sang OPEN**. Những lời gọi bị từ chối trong thời gian OPEN không phải những lần gọi dependency mới và thường **không làm bắt đầu lại khoảng chờ**.

Một ví dụ minh họa với 20 giây:

| Thời điểm | Sự kiện | Hành vi |
| --- | --- | --- |
| 10:00:00 | Lỗi cuối cùng đạt ngưỡng | Chuyển **OPEN**; bắt đầu khoảng chờ |
| 10:00:05 | Request A tới | Bị từ chối nhanh |
| 10:00:17 | Request B tới | Tiếp tục bị từ chối; thời điểm mở mạch không bị đẩy lùi |
| 10:00:20 | Đủ thời gian chờ | Circuit đủ điều kiện cho quá trình thăm dò |
| 10:00:23 | Request C tới | Có thể là lời gọi probe đầu tiên nếu implementation chuyển trạng thái khi có traffic |
| Sau probe | Nhận kết quả thành công/thất bại | Quyết định **CLOSED** hoặc **OPEN** theo chính sách |

Khoảng chờ sau một lần probe thất bại có thể bắt đầu lại khi circuit **mở lại**, không phải từ lúc OPEN đầu tiên.

## 4. Hết thời gian chờ chưa đồng nghĩa có probe

Cần phân biệt hai kiểu kích hoạt:

**Chuyển trạng thái khi có lời gọi:** một request đến sau thời hạn sẽ kích hoạt kiểm tra và có thể chuyển OPEN sang HALF_OPEN; request ấy trở thành ứng viên thăm dò. Nếu không có request mới, có thể không có bất kỳ lời gọi mạng nào được thử.

**Chuyển trạng thái theo bộ giám sát nền:** thư viện có thể chuyển OPEN sang HALF_OPEN khi hết thời gian chờ, kể cả không có caller. Nhưng **chuyển trạng thái không có nghĩa tự gửi probe**; lời gọi thử vẫn cần một nguồn request hoặc cơ chế thăm dò riêng.

Trong Resilience4j, hành vi phổ biến mặc định là đánh giá cơ hội chuyển OPEN → HALF_OPEN khi có request mới. Tùy phiên bản, có thể dùng **automaticTransitionFromOpenToHalfOpenEnabled(true)** để chuyển trạng thái bằng một tác vụ theo dõi nền. Không nên bật chỉ vì muốn “tự ping dependency”: tùy chọn đó không tự tạo traffic probe.

~~~mermaid
sequenceDiagram
    participant A as Caller / Gateway
    participant B as Circuit breaker
    participant D as Stock API
    Note over B: OPEN, còn trong wait duration
    A->>B: Request 1
    B--xA: Từ chối nhanh
    Note over B: Hết wait duration
    A->>B: Request 2
    Note over B: Kiểm tra điều kiện HALF_OPEN
    B->>D: Cho phép probe
    D-->>B: Kết quả probe
    B-->>A: Response hoặc exception
    Note over B: Đánh giá chuyển CLOSED / OPEN
~~~

**Tránh nhầm với health check:** nếu triển khai một job chủ động gửi request thăm dò, nó phải có timeout, giới hạn tần suất, quan sát được kết quả và không thực hiện tác vụ gây tác dụng phụ ngoài ý muốn.

## 5. Spring Integration native: threshold và halfOpenAfter

Khi cần bảo vệ một Service Activator trong Spring Integration, có thể gắn **RequestHandlerCircuitBreakerAdvice** vào handler bằng Java DSL.

Ví dụ minh họa:

~~~java
public record StockQuery(String sku, int quantity) {}

public record StockResult(String sku, int availableUnits) {}

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
public class StockIntegrationConfiguration {

    @Bean
    public RequestHandlerCircuitBreakerAdvice stockBreakerAdvice() {
        RequestHandlerCircuitBreakerAdvice advice =
                new RequestHandlerCircuitBreakerAdvice();

        advice.setThreshold(3);
        advice.setHalfOpenAfter(20_000); // mili giây
        return advice;
    }

    @Bean
    public IntegrationFlow stockFlow(
            StockClient stockClient,
            RequestHandlerCircuitBreakerAdvice stockBreakerAdvice
    ) {
        return IntegrationFlow.from("stock.requests")
                .handle(
                        StockQuery.class,
                        (query, headers) -> stockClient.lookup(query),
                        endpoint -> endpoint.advice(stockBreakerAdvice)
                )
                .get();
    }
}
~~~

Đoạn code lược bớt import, giả định dự án đã có Spring Integration và cấu hình đăng ký Gateway tương ứng.

**Hai tham số quan trọng:**

- **threshold = 3:** advice mở mạch sau khi số lần thực thi handler thất bại liên tiếp đạt ngưỡng theo cơ chế native.
- **halfOpenAfter = 20.000 ms:** khoảng chờ trước cơ hội thử dependency khi mạch đang OPEN.

Hãy đặt advice **ngay tại handler gọi StockClient**, tránh để exception của Filter, Transformer hoặc Aggregator tác động sai tới breaker của Stock API. StockClient vẫn phải có connection và response timeout; **halfOpenAfter không thay thế timeout client**.

### Native advice và “reset” nghĩa là gì?

Trong chế độ CLOSED, một lời gọi thành công có thể làm chuỗi lỗi liên tiếp được tính lại theo quy tắc của advice. Sau khi OPEN, breaker cần thử phục hồi; kết quả ở giai đoạn nửa mở quyết định việc đóng lại hoặc tiếp tục ngắt.

Đừng áp các thuộc tính của Resilience4j như **sliding window**, **minimumNumberOfCalls**, **permittedNumberOfCallsInHalfOpenState** vào native advice: chúng thuộc một thuật toán và API khác. Khi cần kiểm soát chi tiết số probe, tỷ lệ lỗi phục hồi hoặc reset thủ công bằng API quản trị, hãy đánh giá thư viện chuyên dụng thay vì tự suy đoán tính năng native.

## 6. Resilience4j: cấu hình chờ và quy tắc HALF_OPEN

Resilience4j cung cấp nhiều lựa chọn hơn để kiểm soát độ nhạy của breaker và thời điểm phục hồi. Ví dụ:

~~~java
CircuitBreakerConfig config = CircuitBreakerConfig.custom()
        .slidingWindowType(
                CircuitBreakerConfig.SlidingWindowType.COUNT_BASED)
        .slidingWindowSize(10)
        .minimumNumberOfCalls(5)
        .failureRateThreshold(50.0f)
        .waitDurationInOpenState(Duration.ofSeconds(20))
        .permittedNumberOfCallsInHalfOpenState(2)
        .maxWaitDurationInHalfOpenState(Duration.ofSeconds(10))
        .automaticTransitionFromOpenToHalfOpenEnabled(false)
        .build();

CircuitBreaker stockBreaker =
        CircuitBreaker.of("stock-api", config);
~~~

| Thuộc tính | Vai trò |
| --- | --- |
| **slidingWindowSize(10)** | Giữ kết quả 10 lời gọi gần đây để tính thống kê |
| **minimumNumberOfCalls(5)** | Đòi đủ số mẫu trước khi xét failure rate |
| **failureRateThreshold(50%)** | Điều kiện mở khi tỷ lệ lỗi đạt ngưỡng |
| **waitDurationInOpenState(20s)** | Thời gian mạch giữ OPEN trước khi có thể thăm dò |
| **permittedNumberOfCallsInHalfOpenState(2)** | Số permit dành cho probe ở HALF_OPEN |
| **maxWaitDurationInHalfOpenState(10s)** | Giới hạn thời gian đợi hoàn tất giai đoạn HALF_OPEN theo cơ chế Resilience4j |
| **automaticTransitionFromOpenToHalfOpenEnabled(false)** | Cho phép chuyển trạng thái theo request tới, thay vì tự lên lịch chuyển |

**Điều kiện CLOSED sau HALF_OPEN:** khi các kết quả probe đáp ứng ngưỡng thành công và không vi phạm điều kiện failure/slow-call của breaker, state trở lại CLOSED. Với cấu hình **2 probe** và ngưỡng failure rate **50%**, nếu một probe lỗi và một probe thành công thì failure rate đạt 50%; đó là tình huống có thể khiến breaker OPEN trở lại. Không khẳng định “một probe thành công là luôn đóng mạch” cho mọi cấu hình.

**Giới hạn HALF_OPEN khác timeout mạng:** giới hạn 10 giây ở HALF_OPEN điều phối việc thu kết quả và state; nó không tự bảo đảm một HTTP request đang treo sẽ được hủy. Mỗi StockClient call vẫn phải có timeout/deadline riêng.

### 6.1. Gắn Resilience4j vào handler

~~~java
@Bean
public IntegrationFlow stockFlow(
        StockClient stockClient,
        CircuitBreaker stockBreaker
) {
    return IntegrationFlow.from("stock.requests")
            .handle(
                    StockQuery.class,
                    (query, headers) ->
                            stockBreaker.executeSupplier(
                                    () -> stockClient.lookup(query)
                            )
            )
            .get();
}
~~~

Điều cần giữ là **supplier chỉ bao lời gọi dependency**. Nếu handler bắt exception rồi trả kết quả thành công giả **bên trong** supplier, breaker có thể không tăng failure count và không chuyển OPEN khi thực sự cần. Nếu dùng fallback, nên thực hiện ở ranh giới **bên ngoài** lệnh executeSupplier, sau khi breaker đã quan sát kết quả.

Không dùng cùng lúc cả breaker native và Resilience4j cho một điểm gọi nếu không có lý do rõ ràng. Hai bộ điều khiển có thể đưa ra quyết định OPEN/HALF_OPEN khác nhau, gây khó quan sát và chẩn đoán.

## 7. Phân biệt đóng mạch tự nhiên, reset bộ đếm và reset thủ công

Từ “reset” thường bị dùng cho ba hành vi khác nhau:

| Hành vi | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| **Xóa chuỗi lỗi liên tiếp ở CLOSED** | Native breaker thấy một lần thành công giữa các lần lỗi | Bộ đếm lỗi liên tiếp không còn bằng giá trị trước đó |
| **Phục hồi CLOSED sau HALF_OPEN** | Dependency đã khỏe, các probe đủ điều kiện thành công | Breaker đóng mạch theo chính sách phục hồi |
| **Reset thủ công về trạng thái ban đầu** | Operator gọi API reset được thư viện hỗ trợ | Bỏ trạng thái và thống kê hiện tại theo semantics API; các call mới có thể được phép ngay |

Với **Resilience4j**, API **reset()** dùng để reset circuit breaker về trạng thái ban đầu và xóa các thống kê nội bộ theo cơ chế của thư viện:

~~~java
CircuitBreaker breaker = circuitBreakerRegistry
        .circuitBreaker("stock-api");

// Thao tác quản trị có chủ đích, không gọi trong đường request bình thường.
breaker.reset();
~~~

Sau reset, breaker thường trở về **CLOSED** và các request mới có thể đi vào dependency. Đây là một thao tác **mạnh hơn** việc chờ hết thời gian OPEN. Nếu dependency vẫn hỏng, reset tạo đợt request thất bại mới trước khi lại đạt ngưỡng.

**Không tự động gọi reset() trong catch hoặc error channel của mỗi request.** Làm vậy có thể vô hiệu hóa bảo vệ: mạch vừa OPEN đã bị đóng ngay, request tiếp theo lại thử dependency.

Nếu muốn reset sau khi bên vận hành sửa cấu hình mạng hoặc khôi phục upstream, cần xác minh dependency thực sự khỏe, có phương án kiểm soát lượng traffic tăng lại và ghi nhận audit. Việc reset phải có quyền và phạm vi cụ thể, chẳng hạn **stock-api** thay vì tất cả breaker của ứng dụng.

### 7.1. Reset thủ công có rủi ro gì?

- **Thundering herd:** nhiều request tồn đọng đồng loạt tràn vào dependency vừa hồi phục.
- **Mất bằng chứng ngắn hạn:** thống kê lỗi cũ bị xóa có thể làm chậm việc điều tra sự cố nếu chưa ghi metric/log.
- **Không đồng bộ giữa pod:** breaker in-process ở mỗi instance có state riêng; reset một pod không tự động reset tất cả.
- **Sửa triệu chứng:** reset liên tục mà không xử lý root cause chỉ làm chu kỳ lỗi → OPEN lặp lại.
- **Sai ranh giới nghiệp vụ:** reset cho phép lời gọi, nhưng không làm những message đã thất bại hoặc bị bỏ qua được xử lý lại.

Vì vậy **tự phục hồi bằng HALF_OPEN** nên là đường bình thường. Reset thủ công dành cho thao tác vận hành có lý do và quyền kiểm soát rõ ràng.

## 8. Diễn tiến minh họa: chờ 20 giây, cho hai probe

Giả sử breaker Resilience4j đã mở lúc **12:00:00**, chờ **20 giây** và cho **2 probe** khi HALF_OPEN. Đây là ví dụ theo chính sách tỷ lệ lỗi, với điều kiện mở đã được đáp ứng trước mốc thời gian này.

| Thời điểm | Sự kiện | Hành vi / trạng thái |
| --- | --- | --- |
| 12:00:00 | Đạt điều kiện mở | **OPEN**, từ chối lời gọi mới |
| 12:00:06 | Request A đến | Bị từ chối; không gọi Stock API |
| 12:00:19 | Request B đến | Bị từ chối; không kéo dài thời gian chờ |
| 12:00:20 | Đủ wait duration | Có thể bắt đầu chuyển HALF_OPEN theo cơ chế cấu hình |
| 12:00:22 | Request C đến | Được cấp permit probe đầu tiên |
| 12:00:22 | Request D đến | Có thể được cấp permit probe thứ hai |
| 12:00:23 | Request E đến, đã hết permit | Bị từ chối; không có cuộc gọi Stock API thứ ba |
| Sau khi C và D hoàn tất | Cả hai probe thành công | Có thể chuyển **CLOSED** |
| Nhánh thay thế | Một probe lỗi, một thành công | Có thể chuyển **OPEN** trở lại do tỷ lệ lỗi HALF_OPEN đạt ngưỡng |

Hai dòng cuối là **hai nhánh kết quả thay thế**, không xảy ra tuần tự trong một lượt thăm dò.

Nếu mạch OPEN lại tại **12:00:24**, khoảng chờ mới được tính từ lần mở lại đó. Một lời gọi đến quá sớm vẫn bị chặn; không được kết luận rằng “đã từng đợi đủ 20 giây nên từ nay mọi request đều có thể đi qua”.

### Khi không có request sau khoảng chờ

Với chế độ chuyển trạng thái theo lời gọi, đến 12:00:20 chưa chắc đã có phép thử nào. Nếu request tiếp theo đến lúc **12:05**, việc thăm dò có thể bắt đầu vào lúc đó. Một health-check job riêng có thể giúp quan sát dependency từ bên ngoài, nhưng không nên gây side effect và không được hiểu là breaker đã tự kiểm tra.

## 9. HALF_OPEN dưới tải lớn và khi probe bị treo

Khi hệ thống có traffic cao, hàng trăm request có thể tới cùng lúc sau thời gian OPEN. Nếu không giới hạn probe, dependency chưa phục hồi hoàn toàn có thể bị quá tải ngay lập tức.

**Resilience4j** cho phép đặt số permit ở HALF_OPEN. Chỉ các request được cấp permit mới tới dependency; các request còn lại có thể được xử lý qua đường lỗi hoặc fallback. Điều này giảm nguy cơ “phục hồi một giây rồi sập lại”.

Tuy nhiên cần xử lý ba vấn đề:

1. **Probe bị chậm hoặc treo:** phải có timeout của HTTP/gRPC/DB client. Khi tất cả permit bị giữ, các request khác vẫn có thể bị từ chối.
2. **Không có đủ request thăm dò:** nếu traffic quá ít, HALF_OPEN có thể kéo dài khi chưa thu đủ kết quả. Cấu hình giới hạn thời gian ở HALF_OPEN hoặc health-check chủ động phải được đánh giá theo thư viện thực tế.
3. **Probe có tác dụng phụ:** không nên dùng yêu cầu tạo đơn hoặc trừ tiền chỉ để kiểm tra sức khỏe. Nếu một yêu cầu ghi thực tế được cho đi qua, nó cần idempotency và hợp đồng xử lý rõ ràng.

Trong một flow có **Splitter**, một yêu cầu nghiệp vụ có thể tạo nhiều message con tới cùng breaker. Nếu chỉ cho hai permit, những message còn lại có thể bị từ chối trong HALF_OPEN. Aggregator cần hiểu trạng thái của từng nhánh, giữ correlation ID và không chờ vô hạn.

## 10. Retry, fallback và error channel trong giai đoạn phục hồi

### 10.1. Retry không được phá OPEN wait

~~~mermaid
flowchart LR
    A[Gateway] --> B[Fallback boundary]
    B --> C[Circuit breaker]
    C --> D[Retry hữu hạn nếu phù hợp]
    D --> E[Stock API]
    C -->|Không cấp phép| B
~~~

Nếu breaker đang OPEN, retry liên tục đối với lỗi **CallNotPermittedException** không giúp dependency khỏe hơn. Mỗi attempt mới vẫn bị từ chối, nhưng tốn CPU, log và làm tăng latency.

Khi có một probe trong HALF_OPEN, nếu bao **retry bên trong breaker**, nhiều lần thử mạng của một request logic có thể tạo tải lớn hơn một probe vật lý. Nếu **retry bao ngoài breaker**, từng attempt có thể đòi permit riêng. Cần chọn rõ breaker đo **request logic** hay **attempt**, đặt giới hạn retry/backoff và tuân thủ deadline tổng thể.

Không dùng retry không giới hạn cho các thao tác có side effect. Nếu dependency đã nhận lệnh nhưng reply bị mất, thử lại có thể thực thi trùng. Với tác vụ ghi, cần idempotency key và kiểm soát replay.

### 10.2. Fallback trong OPEN và HALF_OPEN

**Circuit breaker chỉ quyết định có được phép gọi hay không.** Nó không tự định nghĩa dữ liệu thay thế.

| Nhánh nghiệp vụ | Khi mạch từ chối | Phương án |
| --- | --- | --- |
| Tra cứu danh mục | Không thể lấy thông tin mới | Có thể dùng cache nếu TTL và nguồn dữ liệu đạt yêu cầu |
| Xác nhận tồn kho trước checkout | Không thể xác nhận số lượng mới | **Fail fast** hoặc trả UNAVAILABLE, không giả định hết hàng |
| Gửi notification xử lý sau | Chưa gọi được provider | Có thể ghi vào durable queue/outbox kèm idempotency key |
| Thanh toán | Không xác định giao dịch hoàn tất chưa | Trả trạng thái cần đối soát; tránh tự coi thất bại hoặc retry mù |

Một outcome có thể mang **FRESH**, **STALE_REFERENCE** hoặc **UNAVAILABLE**, thêm **reasonCode** để phân biệt **BREAKER_REJECTED**, **UPSTREAM_TIMEOUT**, **CACHE_EXPIRED**. Đừng dùng một payload “đã thành công” giả để che tình trạng phụ thuộc đang lỗi.

### 10.3. Gateway, error channel và correlation

Trong Gateway đồng bộ trên **DirectChannel**, exception do breaker từ chối có thể truyền thẳng về caller. Với flow bất đồng bộ hoặc endpoint chạy poller, exception có thể trở thành **ErrorMessage** được gửi vào **error channel** tùy cách cấu hình. Cần phân biệt boundary thực thi trước khi quyết định nơi xử lý fallback.

Với **Splitter/Aggregator**, một nhánh đang OPEN hoặc HALF_OPEN thiếu permit có thể không tạo reply thông thường. Phải giữ **correlation ID**, sequence headers và có một trong các cơ chế:

- Trả outcome suy giảm cho nhánh đó để Aggregator đủ thông tin.
- Cho phép partial result theo hợp đồng nghiệp vụ.
- Cấu hình group timeout, expiration và discard/error path để không giữ group vô thời hạn.

Reset breaker không tự phát lại các message đã được route vào error channel hoặc dead-letter queue. Nếu cần replay, phải có quy trình riêng và bảo đảm idempotency.

## 11. Quan sát để biết circuit đã thật sự phục hồi

Sự kiện breaker chuyển CLOSED chỉ là một tín hiệu; cần kiểm tra thêm sức khỏe dependency và trải nghiệm của caller.

| Chỉ số / sự kiện | Câu hỏi vận hành |
| --- | --- |
| State transition CLOSED/OPEN/HALF_OPEN | Mạch nào đang chờ, mạch nào vừa phục hồi? |
| Thời điểm OPEN và số lần OPEN trở lại | Breaker có dao động liên tục không? |
| Failed và slow calls | Dependency còn lỗi hoặc chậm trong probe không? |
| Not-permitted / rejected calls | Bao nhiêu request bị chặn ở OPEN/HALF_OPEN? |
| Probe outcomes và latency | Thăm dò có đủ số mẫu và đúng deadline không? |
| Fallback use rate và cache age | Hệ thống có đang hoạt động nhờ dữ liệu cũ quá lâu? |
| Gateway latency/error rate | Caller có thực sự được phục vụ tốt hơn? |
| Queue depth và tuổi message cũ nhất | Công việc hoãn có đang tồn đọng không? |
| Aggregator pending/expired groups | Nhánh bị chặn có gây thiếu kết quả không? |
| Correlation/trace ID trong log | Có thể lần theo message gây sự cố không? |

Với Resilience4j, có thể đăng ký state-transition event và tích hợp metrics (chẳng hạn Micrometer). Native advice cần được quan sát theo khả năng thực tế của phiên bản Spring Integration sử dụng, có thể bổ sung đo thời gian và lỗi ở handler/client.

Không gắn **correlation ID** hoặc SKU có số lượng giá trị rất lớn làm nhãn metric. Dùng các ID đó trong log/trace; metric nên gắn **breaker name**, **dependency**, **flow** và **outcome type** ở mức cardinality hợp lý.

### Khi breaker dao động OPEN → HALF_OPEN → OPEN

Khả năng cao dependency mới phục hồi một phần, timeout chưa hợp lý hoặc lưu lượng probe quá cao. Hãy kiểm tra thông tin thực tế trước khi thay đổi ngưỡng:

1. Lời gọi probe có thật sự tới đúng upstream không?
2. HTTP client có timeout, DNS/TLS/connection pool hoạt động bình thường không?
3. Tỷ lệ lỗi và slow-call rate trong HALF_OPEN là bao nhiêu?
4. Số probe có đủ để đánh giá nhưng không gây quá tải không?
5. Có nhánh fallback, retry hoặc cache đang che mất kết quả mà breaker phải quan sát không?

Tăng wait duration có thể cho dependency thêm thời gian phục hồi, nhưng cũng kéo dài giai đoạn từ chối người dùng. Chọn thời gian dựa trên SLO, recovery time của dependency, traffic thực tế và chi phí fallback, thay vì chỉ tăng mặc định.

## 12. Kiểm thử reset và thời gian chờ

Dùng **fake StockClient** có thể đổi giữa thành công và lỗi, kèm **call counter** để chứng minh hành vi OPEN. Trong test phục hồi, cần kiểm tra trạng thái, số request được phép thăm dò và số request bị từ chối.

### 12.1. Unit test reset thủ công với Resilience4j

Test JUnit 5 dưới đây cho thấy **reset() đóng breaker** và cho phép lời gọi mới; đây là bài test cho **thao tác quản trị**, không phải xác minh wait duration tự động.

~~~java
@Test
void manualResetClosesCircuitAndAllowsNewCall() {
    CircuitBreakerConfig config = CircuitBreakerConfig.custom()
            .slidingWindowSize(2)
            .minimumNumberOfCalls(2)
            .failureRateThreshold(50.0f)
            .waitDurationInOpenState(Duration.ofMinutes(1))
            .build();

    CircuitBreaker breaker = CircuitBreaker.of("stock-test", config);
    AtomicInteger remoteCalls = new AtomicInteger();
    AtomicBoolean dependencyHealthy = new AtomicBoolean(false);

    Supplier<String> call = () -> {
        remoteCalls.incrementAndGet();
        if (!dependencyHealthy.get()) {
            throw new IllegalStateException("Stock API unavailable");
        }
        return "OK";
    };

    assertThrows(
            IllegalStateException.class,
            () -> breaker.executeSupplier(call)
    );
    assertThrows(
            IllegalStateException.class,
            () -> breaker.executeSupplier(call)
    );

    assertEquals(CircuitBreaker.State.OPEN, breaker.getState());
    assertEquals(2, remoteCalls.get());

    assertThrows(
            CallNotPermittedException.class,
            () -> breaker.executeSupplier(call)
    );
    assertEquals(2, remoteCalls.get());

    dependencyHealthy.set(true);
    breaker.reset(); // Chỉ minh họa thao tác quản trị có chủ đích.

    assertEquals(CircuitBreaker.State.CLOSED, breaker.getState());
    assertEquals("OK", breaker.executeSupplier(call));
    assertEquals(3, remoteCalls.get());
}
~~~

Code lược bỏ import; cần có Resilience4j, JUnit 5, **AtomicInteger**, **AtomicBoolean**, **Supplier**. Test không dùng HTTP thực hay sleep, nên xác minh trực tiếp cơ chế **reset thủ công** và **call counter**.

### 12.2. Ma trận kiểm thử phục hồi tự động

| Kịch bản | Kết quả cần xác minh |
| --- | --- |
| CLOSED, lỗi dưới ngưỡng | Mạch chưa OPEN, handler vẫn thực thi |
| Đạt ngưỡng | Mạch OPEN, request tiếp theo không gọi client |
| Request tới trước OPEN wait | Từ chối nhanh, **call counter không tăng** |
| Không có request trong lúc OPEN | Không tự khẳng định đã có probe |
| Request đầu tiên sau wait | Được xét cấp permit HALF_OPEN theo chính sách |
| Số probe nhỏ hơn tổng request đồng thời | Chỉ số permit hợp lệ tới client |
| Probe đủ điều kiện thành công | Mạch quay CLOSED, request sau được phép bình thường |
| Probe lỗi hoặc quá chậm | Mạch có thể OPEN lại, bắt đầu khoảng chờ mới |
| Probe bị treo | Client timeout và HALF_OPEN wait có cơ chế thoát rõ ràng |
| Operator gọi reset() | State/counters được đặt lại, request mới được phép |
| Reset trên một pod | Không giả định các pod khác đã reset |
| Gateway/Splitter/Aggregator gặp OPEN | Caller hoặc nhánh có outcome/error/timeout rõ, correlation không mất |

Để test **thời gian chờ** thật, dùng khoảng chờ nhỏ trong cấu hình test, cơ chế kiểm soát thời gian mà thư viện cung cấp (nếu có), hoặc kiểm tra sự kiện state transition trong integration test. Tránh sleep dài tùy ý và phụ thuộc vào thời điểm scheduler chạy; cũng không nên ép trạng thái thủ công rồi tuyên bố đã kiểm thử logic wait duration.

### 12.3. Hai kiểm chứng dễ bị bỏ sót

**Kiểm chứng 1: Reset không replay message.** Gửi message khi OPEN, xác nhận nó đã được chuyển sang error/fallback hoặc queue theo policy. Gọi reset rồi gửi một message **mới**; không mặc định rằng message cũ tự gửi lại.

**Kiểm chứng 2: HALF_OPEN không nhận vô hạn traffic.** Khi nhiều lời gọi tới đồng thời, dùng barrier/latch trong test để giữ các probe đủ lâu, quan sát call counter chỉ tăng theo permit; các lời gọi vượt permit phải nhận lỗi hoặc fallback xác định.

## 13. Lỗi thiết kế thường gặp

1. **Đồng nhất OPEN wait với timeout mạng:** chờ 20 giây trước probe không giới hạn một HTTP request đang chạy.
2. **Cho rằng hết wait là đã CLOSED:** cần kết quả thăm dò và policy đánh giá.
3. **Cho rằng tự chuyển HALF_OPEN nghĩa là tự ping dependency:** chuyển trạng thái có thể không sinh bất kỳ request mạng nào.
4. **Không giới hạn probe:** traffic dồn vào dependency vừa phục hồi, khiến nó sập trở lại.
5. **Gọi reset() sau mọi exception:** vô hiệu hóa OPEN và liên tục dội traffic lên dịch vụ lỗi.
6. **Retry CallNotPermittedException:** tăng latency, log và CPU mà không thêm thông tin sức khỏe.
7. **Dùng probe ghi dữ liệu thiếu idempotency:** gây thực thi lặp khi retry hoặc timeout.
8. **Không có deadline cho probe:** HALF_OPEN có thể kéo dài vì request đang treo.
9. **Reset một pod rồi coi tất cả đã phục hồi:** mỗi breaker in-process có thể giữ trạng thái riêng.
10. **Không giữ correlation hoặc timeout Aggregator:** nhánh bị từ chối làm group chờ vô hạn.
11. **Không đo fallback:** mạch OPEN dài nhưng chỉ nhìn tỷ lệ lỗi API bên ngoài có thể khiến tưởng hệ thống đã khỏe.
12. **Tự đóng mạch vì dữ liệu cache thành công:** nếu fallback chạy bên trong vùng breaker, kết quả cache che mất lỗi dependency.

## 14. Checklist trước khi triển khai

- [ ] Phân biệt rõ timeout client, OPEN wait, HALF_OPEN wait và Gateway/Aggregator timeout.
- [ ] Hiểu implementation chuyển OPEN → HALF_OPEN theo request hay bộ giám sát nền.
- [ ] Có timeout tại dependency client và chính sách thăm dò an toàn.
- [ ] Cấu hình threshold, wait duration và số probe theo tải/SLO của dependency.
- [ ] Không dùng chung breaker cho Stock, Pricing và các miền lỗi độc lập.
- [ ] Fallback nằm sau boundary breaker; kết quả phân biệt fresh, stale và unavailable.
- [ ] Retry hữu hạn, không retry lỗi circuit từ chối; thao tác có side effect cần idempotency.
- [ ] Giữ correlation và định nghĩa error path/group timeout trong Splitter/Aggregator.
- [ ] Chỉ dùng reset thủ công khi có lý do vận hành, ghi audit và kiểm soát traffic phục hồi.
- [ ] Kiểm thử OPEN, wait, HALF_OPEN, đóng lại, mở lại và reset với call counter.
- [ ] Theo dõi state transition, rejected calls, probe outcomes, Gateway latency và queue.

**Reset circuit và thời gian chờ** quyết định hệ thống có thể phục hồi một cách có kiểm soát sau sự cố dependency hay không. Khi đặt breaker đúng ranh giới handler của Spring Integration, giới hạn probe, giữ timeout thực tế và định nghĩa fallback/error flow rõ ràng, Gateway và các nhánh Router, Splitter, Aggregator vẫn duy trì hợp đồng message nhất quán trong suốt quá trình OPEN → HALF_OPEN → CLOSED.
