# Closed, open và half-open state

## 1. Vì sao Circuit Breaker cần một máy trạng thái?

Trong **Spring Integration**, luồng Enterprise Integration Patterns thường nhận message qua Gateway, dùng Filter/Transformer để chuẩn hóa, Router để chọn nhánh rồi gọi một dependency ở Service Activator. Việc các bước giao tiếp qua channel giúp giảm phụ thuộc giữa thành phần, nhưng một API bên ngoài bị chậm hoặc lỗi lặp lại vẫn có thể khiến toàn bộ nhánh bị tắc nghẽn.

**Circuit Breaker** đặt tại điểm gọi dependency để quyết định **có cho phép một lần gọi mới đi qua hay không**. Quyết định đó phụ thuộc vào ba trạng thái chính:

- **CLOSED (đóng mạch):** cho request đi qua, quan sát kết quả.
- **OPEN (mở mạch):** từ chối sớm request mới, tránh tiếp tục gây tải lên dependency đang lỗi.
- **HALF_OPEN (nửa mở):** sau thời gian chờ, cho phép một số request thử có kiểm soát để xem dependency đã phục hồi chưa.

Đây là **trạng thái của bộ bảo vệ** chứ không phải trạng thái thành công/thất bại của từng message. Ví dụ: khi breaker ở CLOSED, một lời gọi vẫn có thể thất bại; chính các thất bại được ghi nhận đó mới có thể dẫn đến OPEN.

~~~mermaid
stateDiagram-v2
    [*] --> CLOSED
    CLOSED --> CLOSED: Gọi thành công / lỗi chưa chạm ngưỡng
    CLOSED --> OPEN: Đủ điều kiện mở mạch
    OPEN --> OPEN: Từ chối request mới trong thời gian chờ
    OPEN --> HALF_OPEN: Hết thời gian chờ và có request thăm dò
    HALF_OPEN --> CLOSED: Kết quả thăm dò đủ điều kiện phục hồi
    HALF_OPEN --> OPEN: Kết quả thăm dò cho thấy vẫn lỗi
~~~

Giản đồ trên mô tả **hành vi khái niệm**. Cách định nghĩa “đủ điều kiện” và số request thăm dò phụ thuộc vào thư viện và cấu hình. Ví dụ, **RequestHandlerCircuitBreakerAdvice** của Spring Integration sử dụng ngưỡng lỗi liên tiếp, còn **Resilience4j** có thể dựa trên tỷ lệ lỗi trong cửa sổ thống kê.

## 2. CLOSED: hoạt động bình thường và thu thập tín hiệu

Ở trạng thái CLOSED, breaker cho lời gọi đi tới dependency:

~~~mermaid
sequenceDiagram
    participant G as Gateway / Flow
    participant B as Circuit Breaker
    participant D as Dependency
    G->>B: Request A
    B->>D: Forward A
    D-->>B: Response / exception
    B-->>G: Response / exception
    Note over B: Ghi nhận kết quả, đánh giá điều kiện mở mạch
~~~

Điều quan trọng là **CLOSED không bảo đảm dependency khỏe**. Trạng thái này chỉ nói rằng breaker chưa có đủ bằng chứng để từ chối request mới. Một số request ở CLOSED vẫn có thể timeout hoặc nhận HTTP 5xx.

### Điều gì được tính là thất bại?

Phải phân biệt rõ ba lớp kết quả:

| Kết quả | Ví dụ | Có nên ảnh hưởng breaker? |
| --- | --- | --- |
| Thành công kỹ thuật và nghiệp vụ | Service trả dữ liệu tồn kho hợp lệ | Được tính là lời gọi thành công |
| Lỗi dependency tạm thời | Kết nối bị từ chối, timeout, HTTP 503 | Thường nên tính là thất bại |
| Lỗi nghiệp vụ dự đoán trước | Số lượng âm, mã SKU không tồn tại, yêu cầu không hợp lệ | Thường xử lý như kết quả nghiệp vụ; không nên làm mở mạch |

Nếu một handler bắt mọi exception rồi trả đối tượng “thành công” giả, breaker có thể không biết dependency đã lỗi. Ngược lại, nếu đưa cả lỗi validate đầu vào vào phần thực thi được bảo vệ, dữ liệu xấu từ client có thể làm mạch mở không cần thiết.

### Ngưỡng lỗi và cửa sổ thống kê

Có hai kiểu tính thường gặp:

1. **Lỗi liên tiếp:** sau một chuỗi thất bại đủ dài, breaker chuyển sang OPEN. Với ngưỡng ba lỗi liên tiếp, chuỗi **lỗi → lỗi → thành công → lỗi** chưa tạo ba lỗi liên tiếp.
2. **Tỷ lệ lỗi trên sliding window:** theo dõi một cửa sổ gồm các lời gọi gần đây; khi có đủ số mẫu và tỷ lệ lỗi vượt ngưỡng cấu hình, breaker có thể chuyển OPEN. Ví dụ **5/10 lời gọi lỗi** tương ứng tỷ lệ lỗi 50%, nhưng chỉ có ý nghĩa nếu điều kiện minimum calls đã đạt.

Hai kiểu đo trả lời hai câu hỏi khác nhau: “dependency vừa lỗi liên tục bao nhiêu lần?” và “trong một nhóm request gần đây, tỷ lệ lỗi cao đến đâu?”. Cần chọn theo tải thực tế, đặc tính lỗi và mức độ chấp nhận suy giảm.

## 3. OPEN: ngắt đường gọi dependency, trả kết quả nhanh

Khi điều kiện mở mạch được thỏa mãn, breaker chuyển sang OPEN. Request mới bị chặn ngay tại breaker và **không được gửi tới dependency**:

~~~mermaid
sequenceDiagram
    participant G as Gateway / Flow
    participant B as Circuit Breaker
    participant D as Dependency
    G->>B: Request B
    Note over B: State = OPEN
    B--xG: Exception / kết quả fallback
    Note over D: Không nhận Request B
~~~

Mục đích của OPEN là **giảm tổn hại dây chuyền**: tránh tốn thêm socket, thread, thời gian chờ và request lên dependency đã có dấu hiệu hỏng. Nhưng OPEN **không tự tạo dữ liệu thay thế**. Flow phải định nghĩa chuyện gì xảy ra với message bị từ chối.

Có ba lựa chọn phổ biến:

| Chính sách | Hành vi ở OPEN | Ví dụ |
| --- | --- | --- |
| Fail fast | Trả lỗi dịch vụ tạm không khả dụng cho caller | API xác nhận thanh toán |
| Fallback có điều kiện | Đọc cache và đánh dấu dữ liệu cũ | Gợi ý danh mục sản phẩm |
| Defer | Đưa yêu cầu vào hàng đợi để xử lý sau | Đồng bộ thông báo hoặc báo cáo |

Không được biến “không liên lạc được dịch vụ tồn kho” thành “chắc chắn hết hàng”. Hai trạng thái có ý nghĩa nghiệp vụ khác nhau, và Transformer/Aggregator phía sau cần phân biệt được.

Trong Gateway **đồng bộ** dùng DirectChannel, lỗi khi OPEN thường được truyền về caller theo đường gọi đồng bộ. Với flow **bất đồng bộ** hoặc endpoint dùng poller, lỗi có thể đi qua cơ chế **ErrorMessage/error channel** phù hợp. Không nên giả định chỉ cần khai báo error channel là mọi exception ở Gateway đồng bộ tự chuyển qua đó.

### OPEN không có nghĩa là dừng mọi việc đang diễn ra

Một số request có thể đã được cho qua **trước khi** mạch mở và vẫn đang xử lý. Breaker thường chặn các lời gọi **mới**, không tự hủy mọi lời gọi đang chạy. Vì vậy vẫn cần timeout tại HTTP/DB client và giới hạn tài nguyên khi dependency chậm. Cũng cần tiếp tục theo dõi lỗi upstream, queue depth và số rejected calls trong thời gian OPEN.

## 4. HALF_OPEN: thăm dò khả năng phục hồi

OPEN không nên kéo dài mãi khi dependency đã phục hồi. Sau **thời gian chờ cấu hình**, breaker có thể bước vào giai đoạn thử lại có kiểm soát, gọi là HALF_OPEN.

- Một hoặc một nhóm giới hạn lời gọi **thăm dò** được phép đi tới dependency.
- Nếu kết quả đáp ứng chính sách phục hồi, breaker quay lại CLOSED và nhận traffic bình thường.
- Nếu kết quả thăm dò cho thấy dependency vẫn lỗi, breaker chuyển OPEN trở lại để tiếp tục nghỉ.
- Khi nhiều thread gọi đồng thời, khả năng cho qua/thông báo từ chối phụ thuộc vào cách thư viện quản lý permit và concurrency; không mặc định mọi thư viện đều chỉ cho đúng một probe.

~~~mermaid
sequenceDiagram
    participant G as Gateway / Flow
    participant B as Circuit Breaker
    participant D as Dependency
    Note over B: OPEN, đã hết thời gian chờ
    G->>B: Request thăm dò
    Note over B: HALF_OPEN
    B->>D: Thử lời gọi
    alt Phục hồi đủ điều kiện
        D-->>B: Thành công
        Note over B: CLOSED
        B-->>G: Response
    else Chưa phục hồi
        D--xB: Lỗi
        Note over B: OPEN trở lại
        B--xG: Exception / fallback
    end
~~~

**Thời gian chờ trước HALF_OPEN khác timeout của request.** Ví dụ mạch chờ 15 giây trước khi thử lại, nhưng lời gọi thử vẫn có timeout HTTP riêng là 2 giây. Tăng thời gian chờ breaker không thể thay thế timeout mạng.

Trong nhiều cách triển khai, việc hết thời gian chờ không có nghĩa một luồng nền sẽ chủ động gọi dependency. Trạng thái có thể chỉ thay đổi hoặc phép thử mới bắt đầu **khi request kế tiếp đến**. Vì vậy muốn kiểm tra phục hồi chủ động cần health check riêng với chính sách phù hợp, thay vì mặc định breaker tự gửi heartbeat.

### HALF_OPEN với traffic lớn

Ví dụ dependency vừa hồi phục nhưng 500 request cùng tới: nếu tất cả đều được phép đi qua HALF_OPEN, dịch vụ có thể lại bị quá tải. Thư viện như **Resilience4j** cho phép cấu hình số lời gọi được phép trong HALF_OPEN, còn các lời gọi không được cấp quyền sẽ bị từ chối. Với **native Spring Integration advice**, không tự suy ra có bộ giới hạn probe với cùng ngữ nghĩa; cần theo dõi chính xác phiên bản và cấu hình đang dùng.

## 5. Theo dấu một vòng đời thực tế

Giả sử hệ thống kiểm tra tồn kho có **ngưỡng 3 lỗi liên tiếp** và chờ **15 giây** trước khi cho thử lại. Bảng sau là một diễn tiến minh họa theo mô hình lỗi liên tiếp, với thời gian được tính từ lúc mạch mở:

| Bước | Sự kiện | State sau sự kiện | Có gọi Stock Service? |
| --- | --- | --- | --- |
| 1 | Request A thành công | CLOSED | Có |
| 2 | Request B timeout | CLOSED | Có |
| 3 | Request C timeout | CLOSED | Có |
| 4 | Request D timeout, đạt ngưỡng | OPEN | Có (request D đã được gọi rồi mới lỗi) |
| 5 | Request E đến khi mạch đang OPEN | OPEN | **Không** |
| 6 | Đến thời điểm được phép thăm dò, Request F đến | HALF_OPEN trong lúc thăm dò | **Có, thăm dò** |
| 7a | F thành công và đạt điều kiện phục hồi | CLOSED | Có |
| 7b | Hoặc F tiếp tục lỗi | OPEN trở lại | Có |

Bước 7a và 7b là **hai nhánh loại trừ nhau**, không phải hai sự kiện xảy ra tuần tự. Ví dụ minh họa bản chất state machine, còn chi tiết chuyển trạng thái sau một hay nhiều probe được quyết định bởi implementation.

Một điểm dễ nhầm: **lời gọi D đã thất bại mới khiến mạch OPEN**. Request D không bị chặn từ trước; request E đến sau mới nhận tác dụng bảo vệ của OPEN. Bài kiểm thử cần kiểm tra số lần client thực sự được gọi để chứng minh điều này.

## 6. Gắn Circuit Breaker vào Spring Integration

### 6.1. Gateway và hợp đồng message

Ví dụ dưới đây giả sử Spring Integration và Java DSL đã được cấu hình trong dự án Spring. Các import được lược bớt cho dễ đọc.

~~~java
public record StockQuery(String sku, int requiredQuantity) {}

public record StockSnapshot(
        String sku,
        int availableQuantity,
        boolean enoughStock
) {}

public interface StockClient {
    StockSnapshot lookup(StockQuery query);
}

@MessagingGateway(defaultRequestChannel = "stock.lookup.requests")
public interface StockGateway {
    StockSnapshot lookup(StockQuery query);
}
~~~

Tầng adapter của **StockClient** cần cấu hình connection timeout và response timeout. Validation cho SKU, requiredQuantity nên thực hiện trước lời gọi dependency để loại lỗi dữ liệu đầu vào khỏi thống kê sức khỏe của dịch vụ tồn kho.

### 6.2. Dùng RequestHandlerCircuitBreakerAdvice

**RequestHandlerCircuitBreakerAdvice** cho phép bảo vệ một request handler. Ví dụ dùng ngưỡng lỗi liên tiếp và thời gian chờ trước khi thăm dò:

~~~java
@Configuration
@EnableIntegration
@IntegrationComponentScan
public class StockFlowConfiguration {

    @Bean
    public RequestHandlerCircuitBreakerAdvice stockBreakerAdvice() {
        RequestHandlerCircuitBreakerAdvice advice =
                new RequestHandlerCircuitBreakerAdvice();

        advice.setThreshold(3);
        advice.setHalfOpenAfter(15_000); // milliseconds
        return advice;
    }

    @Bean
    public IntegrationFlow stockLookupFlow(
            StockClient stockClient,
            RequestHandlerCircuitBreakerAdvice stockBreakerAdvice
    ) {
        return IntegrationFlow.from("stock.lookup.requests")
                .handle(
                        StockQuery.class,
                        (request, headers) -> stockClient.lookup(request),
                        endpoint -> endpoint.advice(stockBreakerAdvice)
                )
                .get();
    }
}
~~~

Ở flow này, Gateway gửi **StockQuery** tới channel; handler gọi StockClient khi breaker cho phép. Advice ghi nhận kết quả của handler và quyết định có từ chối các lần xử lý tiếp theo không. Khi OPEN, lời gọi sẽ không đi tiếp tới StockClient, nên Gateway cần hợp đồng xử lý exception rõ ràng.

**Lưu ý:** ngưỡng lỗi liên tiếp của native advice **không phải** cấu hình tỷ lệ lỗi theo sliding window. Các ví dụ về failure rate và số probe HALF_OPEN ở phần sau thuộc **Resilience4j**, không áp trực tiếp vào native advice.

### 6.3. Khi cần tùy chỉnh HALF_OPEN với Resilience4j

Resilience4j hỗ trợ failure-rate threshold, minimum calls, cửa sổ thống kê và số lần gọi được phép khi HALF_OPEN. Ví dụ cấu hình:

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

// Chỉ bao lời gọi dependency trong handler:
StockSnapshot snapshot =
        stockBreaker.executeSupplier(() -> stockClient.lookup(query));
~~~

Theo cấu hình minh họa, khi đủ ít nhất 5 lời gọi trong cửa sổ và tỷ lệ lỗi đạt ngưỡng, breaker có thể mở. Sau 15 giây, tối đa 2 lời gọi thăm dò được cấp quyền trong HALF_OPEN; việc đánh giá quay CLOSED hay OPEN dựa trên kết quả theo quy tắc của Resilience4j.

Trong một hệ thống thực tế, phải phân loại exception cần ghi nhận và exception được bỏ qua, bổ sung timeout thích hợp, đặt tên breaker theo dependency và tích hợp metrics. Không dùng chung một instance breaker cho nhiều dependency không có cùng miền lỗi.

## 7. State machine tác động đến các EIP khác thế nào?

### Gateway và Router

**Gateway** là ranh giới giữa lời gọi ứng dụng và message flow. Khi breaker OPEN, caller có thể nhận exception nhanh, hoặc một lớp ứng dụng chuyển thành response thể hiện dịch vụ tạm không khả dụng. **Router** chọn nhánh dựa trên nghiệp vụ; đặt breaker ở nhánh thực sự gọi dependency sẽ giữ được tính độc lập giữa các nhánh.

~~~mermaid
flowchart LR
    A[Gateway] --> B[Filter / Transformer]
    B --> C{Router}
    C -->|Tra tồn kho| D[Circuit breaker: stock]
    C -->|Tra giá| E[Circuit breaker: pricing]
    D --> F[Stock service]
    E --> G[Pricing service]
    D --> H[Reply / fallback]
    E --> H
~~~

Khi stock breaker OPEN nhưng pricing breaker CLOSED, nhánh tra giá vẫn có thể chạy. Đó là một ví dụ circuit breaker hỗ trợ thiết kế flow ít phụ thuộc và dễ mở rộng.

### Retry và trạng thái

Retry và breaker giải quyết các vấn đề khác nhau:

- **Retry** dành cho lỗi có khả năng phục hồi nhanh; mỗi lần thử thêm đều tạo tải.
- **Circuit breaker** ngăn tạo tải mới khi dependency đang có dấu hiệu lỗi liên tục.
- **Timeout** giới hạn thời gian một lời gọi chiếm tài nguyên; breaker không thay thế timeout.

Thứ tự bao advice thay đổi số “lần gọi” mà breaker ghi nhận. Nếu breaker bao ngoài retry, một nhóm attempt có thể được đánh giá như một lần thực thi cuối cùng. Nếu retry bao ngoài breaker, mỗi attempt có thể đi qua breaker; khi OPEN, retry thêm có thể chỉ tạo một loạt từ chối nhanh. Vì vậy **không retry không giới hạn các lỗi do OPEN**.

### Splitter, Aggregator và correlation

Nếu **Splitter** tách đơn hàng thành nhiều message con, một nhánh gọi dependency đang OPEN có thể không trả về payload như bình thường. **Aggregator** có thể thiếu một phần kết quả và chờ mãi nếu không có chính sách hoàn tất nhóm.

Cần giữ các **correlation ID**, sequence headers và định nghĩa kết quả rõ ràng cho nhánh không khả dụng. Ví dụ một nhánh phát kết quả **TEMPORARILY_UNAVAILABLE** kèm correlation ID để Aggregator tổng hợp thành partial response; hoặc timeout nhóm và đưa message sang luồng xử lý lỗi có kiểm soát.

Ở tác vụ ghi dữ liệu có side effect, việc phát lại message sau khi HALF_OPEN/đóng mạch có thể tạo xử lý trùng. Cần idempotency key trước khi kết hợp retry hoặc queue replay.

### Error channel

Khi breaker OPEN, lỗi từ handler đồng bộ thường nổi về caller. Với các endpoint bất đồng bộ, lỗi có thể được chuyển vào **error channel** theo cơ chế xử lý lỗi của channel/poller. Không nên xem error channel là cách thay thế hợp đồng fallback: người nhận vẫn cần biết request nào bị từ chối, có an toàn để thử lại hay không, và cách xử lý correlation.

## 8. Kiểm thử ba trạng thái bằng fake dependency

Dùng một fake StockClient có thể chuyển đổi hành vi giữa **trả thành công** và **ném exception**, đồng thời đếm tổng số lần được gọi. Từ test, gửi message qua Gateway thật để xác minh toàn bộ đường đi của Spring Integration.

| Tình huống | Kiểm chứng mong đợi |
| --- | --- |
| CLOSED, dependency thành công | Nhận đúng StockSnapshot; client được gọi đúng một lần |
| CLOSED, lỗi chưa đủ ngưỡng | Caller nhận lỗi; request kế tiếp vẫn có thể đến client |
| Đạt điều kiện mở mạch | Lời gọi gây lỗi đã đi vào client; breaker chuyển OPEN |
| OPEN, nhiều request mới | Các lời gọi bị từ chối nhanh; **call counter không tăng** |
| Hết khoảng chờ rồi có request | Có request thăm dò đi qua theo chính sách HALF_OPEN |
| Thăm dò thành công | Breaker phục hồi về CLOSED khi đạt điều kiện |
| Thăm dò thất bại | Breaker quay OPEN, chặn request tiếp theo |
| Retry kết hợp OPEN | Số lần gọi client hữu hạn; không retry mù quáng lỗi do OPEN |
| Splitter/Aggregator gặp OPEN | Có partial result/timeout/error path; không chờ vô hạn |
| Nhiều instance ứng dụng | Không giả định breaker tự đồng bộ trạng thái giữa các instance |

Một quy trình test đơn giản cho ví dụ **3 lỗi liên tiếp**:

1. Cho fake client ném lỗi trong ba request đi qua Gateway.
2. Ghi lại **call counter = 3** (giả sử không bật retry).
3. Gửi request tiếp theo khi mạch còn OPEN; kiểm tra **call counter vẫn = 3**.
4. Qua khoảng chờ cấu hình, cho fake trả thành công và gửi request thăm dò.
5. Kiểm tra đường xử lý thăm dò và các request sau khi breaker phục hồi.

Để test ổn định, nên dùng khoảng chờ ngắn riêng cho môi trường kiểm thử hoặc cách kiểm soát clock thích hợp nếu thư viện hỗ trợ. Tránh test chỉ assert thông báo exception: nó không chứng minh được OPEN thực sự chặn cuộc gọi đến dependency.

## 9. Quan sát và chẩn đoán chuyển trạng thái

Để vận hành, nên ghi nhận tối thiểu:

| Tín hiệu | Ý nghĩa |
| --- | --- |
| Current state theo dependency | Biết nhánh nào đang CLOSED, OPEN hoặc HALF_OPEN |
| State transition event | Biết mạch mở khi nào, phục hồi khi nào, có dao động không |
| Failed / slow call rate | Phân biệt lỗi dependency và hiện tượng latency tăng |
| Rejected / not-permitted calls | Đo số request bị ngắt ở OPEN và khi HALF_OPEN thiếu permit |
| Gateway latency và queue depth | Đánh giá tác động đến toàn bộ flow |
| Correlation ID, error type, branch | Truy vết message và dependency gây lỗi |

Resilience4j có event publisher và khả năng tích hợp Micrometer. Với native Spring Integration advice, cần kiểm tra cơ chế quan sát hiện có của phiên bản đang sử dụng và tự bổ sung instrumentation phù hợp; không mặc định tất cả metric trên sẽ xuất hiện tự động.

Nếu breaker **dao động OPEN ↔ HALF_OPEN** liên tục, có thể dependency chưa thực sự hồi phục, thời gian chờ quá ngắn hoặc lượng probe quá cao. Nếu breaker vẫn CLOSED nhưng gateway liên tục chậm, cần xem timeout client, ngưỡng lỗi, tỷ lệ lỗi, thread pool và giới hạn đồng thời.

## 10. Các hiểu nhầm dễ gây lỗi

1. **“CLOSED tức là mọi request đều thành công.”** Sai: CLOSED chỉ cho phép gọi và đang đo kết quả.
2. **“OPEN có nghĩa client được gọi nhưng trả lỗi ngay.”** Sai: request mới bị từ chối ở breaker; client không cần được gọi.
3. **“Sau đúng 15 giây, dependency tự động nhận một probe.”** Không nhất thiết: nhiều triển khai chỉ thử khi có request tiếp theo.
4. **“HALF_OPEN chắc chắn cho mọi request đi qua.”** Sai: có thể giới hạn số probe; điều kiện và chính sách phụ thuộc implementation.
5. **“Tăng half-open wait sẽ sửa timeout mạng.”** Sai: hai khoảng thời gian phục vụ mục tiêu khác nhau.
6. **“Mỗi exception đều phản ánh lỗi hạ tầng.”** Sai: phải phân loại lỗi nghiệp vụ và lỗi dependency.
7. **“OPEN làm biến mất message nên Aggregator tự hoàn tất.”** Sai: cần timeout, fallback hoặc message lỗi có correlation rõ ràng.
8. **“Một state được dùng chung trên mọi pod.”** Không mặc định: breaker dạng in-process thường có trạng thái theo từng instance.
9. **“Retry càng nhiều càng nhanh khỏi lỗi.”** Sai: trong sự cố diện rộng, retry có thể làm quá tải dependency và trì hoãn phục hồi.

## 11. Tự kiểm tra trước khi đưa flow vào vận hành

- [ ] Chỉ bao quanh lời gọi dependency có khả năng lỗi; validate dữ liệu trước breaker.
- [ ] Hiểu rõ thư viện đếm lỗi **liên tiếp** hay theo **tỷ lệ trong sliding window**.
- [ ] Biết kết quả caller nhận ở OPEN và nơi ErrorMessage được xử lý.
- [ ] Có timeout thực tế ở client; retry hữu hạn và an toàn với idempotency.
- [ ] Xác định điều kiện, số lượng probe và khoảng chờ HALF_OPEN theo implementation.
- [ ] Đảm bảo Router/Splitter/Aggregator xử lý được nhánh thiếu dữ liệu và giữ correlation.
- [ ] Có kiểm thử chứng minh OPEN ngăn lời gọi client bằng call counter.
- [ ] Theo dõi trạng thái, chuyển trạng thái, rejected calls và ảnh hưởng lên latency/queue.

**CLOSED** là giai đoạn cho phép và quan sát, **OPEN** là giai đoạn bảo vệ bằng cách từ chối sớm, **HALF_OPEN** là giai đoạn xác minh phục hồi. Hiểu đúng ba trạng thái giúp đặt Circuit Breaker vào các flow Spring Integration mà vẫn giữ được tính tách biệt giữa các EIP, đường xử lý lỗi và hợp đồng kết quả cho từng message.
