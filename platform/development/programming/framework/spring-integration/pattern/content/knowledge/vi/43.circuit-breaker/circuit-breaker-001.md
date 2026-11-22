# Circuit breaker bảo vệ flow gọi dependency

## 1. Vấn đề: một dependency chậm có thể làm nghẽn cả flow

Trong một hệ thống dùng **Spring Integration** để triển khai Enterprise Integration Patterns (EIP), một message thường đi qua nhiều bước: Gateway nhận yêu cầu, Router chọn nhánh, Transformer chuẩn hóa dữ liệu, Service Activator gọi hệ thống bên ngoài, rồi Aggregator ghép kết quả. Các bước được nối bằng channel giúp giảm phụ thuộc trực tiếp giữa các thành phần, nhưng **flow vẫn có thể bị ảnh hưởng bởi dependency ở xa**.

Ví dụ: luồng xử lý đơn hàng cần hỏi dịch vụ tồn kho. Khi dịch vụ này mất kết nối hoặc liên tục trả lỗi, mỗi lần gọi đều phải chờ timeout. Nếu traffic tăng, các thread xử lý message bị giữ lại, hàng đợi tích tụ, Gateway phản hồi chậm và các nhánh khác cũng chịu áp lực.

**Circuit breaker** (bộ ngắt mạch) bảo vệ điểm gọi dependency bằng cách theo dõi các lần thực thi thất bại. Khi lỗi vượt ngưỡng, breaker **mở mạch** và từ chối sớm các lời gọi tiếp theo. Sau một khoảng chờ, breaker cho phép thử lại có kiểm soát; nếu dependency đã phục hồi, mạch đóng và luồng trở lại bình thường.

Mục tiêu của bài này là đặt circuit breaker đúng vị trí trong flow Spring Integration, hiểu tác động lên Router, Gateway, retry, error channel và correlation, đồng thời thiết kế cách kiểm thử và theo dõi trạng thái.

## 2. Vị trí trong kiến trúc EIP

~~~mermaid
flowchart LR
    A[Messaging Gateway] --> B[Validate / Transform]
    B --> C{Router}
    C -->|Cần tồn kho| D[Channel: stock.requests]
    D --> E[Circuit breaker]
    E -->|Mạch đóng / cho thử| F[Stock client]
    E -->|Mạch mở| G[Xử lý từ chối / fallback]
    F --> H[Stock service]
    H --> I[Response / Aggregator]
    G --> I
    C -->|Không cần tồn kho| J[Nhánh khác]
    J --> I
~~~

Breaker nên bao quanh **thao tác có thể thất bại vì dependency**, không bao toàn bộ flow. Nếu đặt breaker trước bước validate, lỗi dữ liệu đầu vào có thể bị tính nhầm thành lỗi dịch vụ bên ngoài. Nếu bao cả các nhánh sau khi lấy kết quả, lỗi Mapper hoặc Aggregator cũng có thể làm mở mạch sai nguyên nhân.

Một breaker thường gắn với **một dependency hoặc một nhóm endpoint có cùng miền lỗi**. Nếu tồn kho và thanh toán là hai dịch vụ khác nhau, dùng hai breaker độc lập để sự cố của tồn kho không khóa đường gọi thanh toán.

| Thành phần | Nhiệm vụ | Khác circuit breaker ở điểm nào? |
| --- | --- | --- |
| Timeout | Giới hạn thời gian của **mỗi lần gọi** | Không tự ngăn các lần gọi sau khi dependency liên tục lỗi |
| Retry | Thử lại khi một lần gọi thất bại | Có thể tăng tải lên dependency nếu không được giới hạn |
| Circuit breaker | Chặn nhanh lời gọi khi dependency đang không khỏe | Không thay thế timeout hay cơ chế giới hạn đồng thời |
| Bulkhead | Giới hạn tài nguyên hoặc số lời gọi đồng thời | Cô lập áp lực tài nguyên, kể cả khi dependency chỉ **chậm** |
| Rate limiter | Khống chế tốc độ gửi request | Không tự suy ra dependency đang lỗi |
| Error channel | Đưa lỗi message sang luồng xử lý lỗi | Không tự quyết định khi nào cần tạm ngừng gọi dependency |

Một flow đáng tin cậy thường kết hợp timeout của HTTP/gRPC/DB client, retry hữu hạn cho lỗi tạm thời, breaker tại điểm gọi và phương án xử lý khi dependency không khả dụng.

## 3. Ba trạng thái của circuit breaker

~~~mermaid
stateDiagram-v2
    [*] --> CLOSED
    CLOSED --> OPEN: Lỗi chạm ngưỡng
    OPEN --> HALF_OPEN: Hết thời gian chờ, có lời gọi thử
    HALF_OPEN --> CLOSED: Lời gọi thử thành công
    HALF_OPEN --> OPEN: Lời gọi thử thất bại
~~~

- **CLOSED (đóng mạch):** request được phép đi tới dependency. Breaker theo dõi kết quả thực thi. Đây là trạng thái hoạt động bình thường.
- **OPEN (mở mạch):** request mới bị từ chối tại chỗ; không tạo lời gọi mạng tương ứng. Gateway có thể nhận lỗi nhanh hoặc flow chuyển sang phương án dự phòng.
- **HALF_OPEN (nửa mở):** một hoặc một số lời gọi thử được cho qua để đánh giá khả năng phục hồi. Thành công cho phép trở lại CLOSED; thất bại có thể mở mạch trở lại.

**Chú ý ngữ nghĩa ngưỡng:** Spring Integration có cơ chế native **RequestHandlerCircuitBreakerAdvice** dựa trên ngưỡng **lỗi liên tiếp**. Những thư viện như Resilience4j có thể tính **tỷ lệ lỗi trên cửa sổ thống kê** với số mẫu tối thiểu và nhiều tùy chọn hơn. Không nên coi hai cách đếm này là một.

Ví dụ với ngưỡng ba lỗi liên tiếp: hai lần lỗi rồi một lần thành công **không tương đương** ba lần lỗi liên tiếp. Trong mô hình tỷ lệ lỗi, cùng chuỗi sự kiện đó có thể đóng góp vào tỷ lệ thống kê tùy cấu hình cửa sổ và số lời gọi tối thiểu.

## 4. Triển khai với Spring Integration Java DSL

### 4.1. Hợp đồng message và Gateway

Giả sử flow kiểm tra tồn kho có payload đầu vào là mã hàng và số lượng. Client bên ngoài được biểu diễn qua một interface, để dễ thay bằng mock/fake trong kiểm thử.

~~~java
public record StockRequest(String sku, int quantity) {}

public record StockResult(
        String sku,
        boolean available,
        int remaining
) {}

public interface StockClient {
    StockResult check(StockRequest request);
}

@MessagingGateway(defaultRequestChannel = "stock.requests")
public interface StockGateway {
    StockResult check(StockRequest request);
}
~~~

Messaging Gateway giúp mã ứng dụng gọi phương thức đồng bộ, còn Spring Integration thực hiện việc chuyển phương thức đó thành message, gửi vào channel và nhận reply.

### 4.2. Gắn RequestHandlerCircuitBreakerAdvice đúng handler

Ví dụ dưới đây dùng Spring Integration Java DSL và **RequestHandlerCircuitBreakerAdvice**. Các import Java được lược bớt để tập trung vào cách lắp ghép. Trong ứng dụng Spring Boot, cấu hình component scan cho Gateway (ví dụ qua **@IntegrationComponentScan**) và khai báo Spring Integration dependency phù hợp với phiên bản dự án.

~~~java
@Configuration
@EnableIntegration
@IntegrationComponentScan
public class StockIntegrationConfig {

    @Bean
    public RequestHandlerCircuitBreakerAdvice stockCircuitBreaker() {
        RequestHandlerCircuitBreakerAdvice advice =
                new RequestHandlerCircuitBreakerAdvice();

        advice.setThreshold(3);
        advice.setHalfOpenAfter(15_000); // mili giây
        return advice;
    }

    @Bean
    public IntegrationFlow stockFlow(
            StockClient client,
            RequestHandlerCircuitBreakerAdvice stockCircuitBreaker
    ) {
        return IntegrationFlow.from("stock.requests")
                .handle(
                        StockRequest.class,
                        (request, headers) -> client.check(request),
                        endpoint -> endpoint.advice(stockCircuitBreaker)
                )
                .get();
    }
}
~~~

Trong đoạn này:

1. Gateway gửi **StockRequest** vào channel **stock.requests**.
2. Service Activator gọi **StockClient.check(...)**; advice bao quanh lần xử lý của handler này.
3. Khi dependency thành công, **StockResult** trở về reply channel mà Gateway đang chờ.
4. Khi handler liên tục ném exception tới ngưỡng cấu hình, breaker mở; lời gọi mới bị từ chối trước khi vào client.
5. Sau thời gian **halfOpenAfter**, lời gọi mới có thể được dùng để thăm dò khả năng phục hồi.

Trạng thái breaker thuộc về **instance advice**. Không chia sẻ cùng một advice bean giữa hai dependency độc lập nếu muốn chúng có trạng thái lỗi riêng. Khi chạy nhiều instance ứng dụng, mỗi instance thường giữ trạng thái breaker riêng; đây không phải một công tắc toàn cục được tự động đồng bộ giữa các pod.

### 4.3. Ranh giới cần giữ rõ

Phương thức **StockClient.check** phải có timeout ở tầng client thực tế. Ví dụ với HTTP, cần cấu hình connection timeout và response/read timeout theo SLA; thời gian **halfOpenAfter** chỉ quyết định khi nào breaker được phép thăm dò, **không** giới hạn thời gian của một request mạng.

Không nên chuyển mọi lỗi thành một kết quả thành công bên trong handler được advice bao quanh. Nếu catch exception rồi trả về StockResult giả trước khi exception đến breaker, breaker sẽ không thấy lỗi cần thống kê.

Cũng không nên để lỗi nghiệp vụ được dự đoán trước (SKU không hợp lệ, quantity âm, nghiệp vụ từ chối yêu cầu hợp lệ) làm mở breaker. Hãy validate trước bước gọi dependency và biểu diễn các kết quả nghiệp vụ theo hợp đồng dữ liệu rõ ràng. Chỉ những thất bại thuộc miền dependency mới nên tác động đến trạng thái mạch.

## 5. Xử lý khi mạch mở và khi handler lỗi

**Mở mạch không tự tạo fallback.** Trong luồng Gateway/DirectChannel đồng bộ, lỗi từ handler hoặc từ advice thường được truyền ngược theo chuỗi gọi; tầng gọi cần biết nên trả lỗi, dùng dữ liệu cũ hay hoãn xử lý. Trong flow bất đồng bộ, lỗi có thể được phát dưới dạng ErrorMessage qua cơ chế error channel tương ứng; cách xử lý cụ thể phụ thuộc loại channel, poller và error channel được cấu hình.

Có ba cách xử lý phổ biến:

| Chiến lược | Khi phù hợp | Điều phải kiểm soát |
| --- | --- | --- |
| Fail fast | Thanh toán, xác nhận quyền, dữ liệu phải chính xác tức thời | Trả trạng thái dịch vụ tạm không khả dụng; không giả vờ thành công |
| Fallback cache | Danh mục, tồn kho tham khảo hoặc dữ liệu cho phép cũ | Gắn dấu thời gian và độ mới; tránh dùng dữ liệu cũ để quyết định thanh toán |
| Defer / queue | Tác vụ có thể xử lý sau như đồng bộ hóa hoặc gửi thông báo | Bảo đảm idempotency, retry sau, TTL và nơi lưu tác vụ thất bại |

Nên biểu diễn trạng thái dự phòng bằng một kiểu kết quả cụ thể, ví dụ:

~~~java
public enum LookupStatus {
    FRESH,
    STALE_CACHE,
    TEMPORARILY_UNAVAILABLE
}

public record StockLookupOutcome(
        String sku,
        LookupStatus status,
        StockResult data,
        String correlationId
) {}
~~~

Khi status là **TEMPORARILY_UNAVAILABLE**, dữ liệu có thể vắng mặt; các bước Router/Aggregator phải xử lý trạng thái này tường minh. Không tự biến lỗi thành **StockResult.available = false**: “không biết tồn kho” khác hẳn “đã kiểm tra và hết hàng”.

Đối với error channel, phân biệt hai tình huống:

- **Đồng bộ:** Gateway gọi qua DirectChannel; exception có thể nổi trực tiếp về caller. Có thể xử lý ở boundary ứng dụng hoặc dùng một error flow được cấu hình có chủ đích.
- **Bất đồng bộ:** ExecutorChannel hoặc endpoint chạy theo poller có đường phát ErrorMessage. Consumer ở error channel cần xác định message gốc, cause, correlation ID và chính sách retry/đưa vào hàng chờ lỗi.

Chỉ gắn tên **errorChannel** trên message không đồng nghĩa mọi lỗi đồng bộ đều tự động đi qua một nhánh xử lý lỗi. Cần kiểm tra mô hình dispatcher và boundary thực thi của flow thực tế.

## 6. Tương tác với retry, Router, Splitter và Aggregator

### Retry nằm ở đâu so với breaker?

~~~mermaid
flowchart LR
    A[Gateway] --> B[Breaker]
    B --> C[Retry hữu hạn]
    C --> D[Dependency]
~~~

Với thứ tự **breaker bao ngoài retry**, một yêu cầu nghiệp vụ đi qua nhiều lần thử bên trong có thể được breaker nhìn như **một lần thực thi thành công hoặc thất bại cuối cùng**. Điều này hữu ích khi muốn breaker đánh giá kết quả theo từng request logic, nhưng retry phải giới hạn số lần thử và dùng backoff để tránh khuếch đại tải.

Nếu đặt **retry bao ngoài breaker**, mỗi lần thử có thể đi qua breaker và góp vào bộ đếm riêng; khi breaker đã OPEN, các lần retry tiếp theo thường chỉ nhận từ chối nhanh. Cần thiết kế chính sách retry để không retry mù quáng đối với trường hợp mạch mở.

Ví dụ chính sách hợp lý: timeout ngắn ở client, retry tối đa một hoặc hai lần cho lỗi tạm thời có khả năng phục hồi, backoff có jitter và breaker bao ngoài. Các con số phải dựa trên SLA, đặc điểm dependency và mức độ an toàn khi gọi lặp.

### Router và Filter

Router nên chọn nhánh dựa vào **ý nghĩa nghiệp vụ của message**. Breaker đặt trong nhánh có dependency tương ứng; không nên dùng trạng thái mạch như điều kiện duy nhất để quyết định nghiệp vụ mà không có trạng thái fallback rõ ràng. Filter vẫn chịu trách nhiệm loại message không hợp lệ trước khi gây lời gọi tốn tài nguyên.

### Splitter và Aggregator

Nếu một đơn hàng được Splitter chia thành nhiều request con để gọi nhiều dịch vụ, việc mạch mở ở một nhánh có thể khiến Aggregator thiếu reply. Khi đó cần định nghĩa rõ:

- Khi nào nhóm message được coi là hoàn tất: đủ mọi kết quả, kết quả từng phần hay timeout?
- Khi không nhận được kết quả từ một dependency, có phát một outcome **TEMPORARILY_UNAVAILABLE** để Aggregator ra quyết định không?
- Group timeout, expiration, discard channel và cơ chế dọn group được cấu hình như thế nào?

**Correlation ID** và sequence headers cần được giữ xuyên suốt các nhánh, bao gồm nhánh fallback hoặc hoãn xử lý. Với một flow bất đồng bộ, message lỗi cũng phải mang đủ ngữ cảnh để đối chiếu lại request gốc. Không để nhóm Aggregator chờ vô hạn chỉ vì breaker đã từ chối một phần công việc.

### Idempotency khi retry và phục hồi

Các lời gọi đọc dữ liệu thường dễ retry hơn các thao tác gây tác dụng phụ (thu tiền, tạo đơn, trừ tồn kho). Nếu dependency đã xử lý thành công nhưng reply bị mất, retry có thể lặp thao tác. Với lệnh ghi, cần idempotency key và cơ chế chống xử lý trùng tại phía nhận trước khi bật retry hoặc phát lại message từ queue.

## 7. Lựa chọn native advice hay Resilience4j?

**RequestHandlerCircuitBreakerAdvice** hợp với flow Spring Integration cần một ngưỡng lỗi liên tiếp và thời gian chờ đơn giản, gắn trực tiếp vào handler qua advice chain. Ưu điểm là cấu hình gọn, ít thành phần bổ sung và dễ minh họa vị trí bảo vệ.

Khi cần đánh giá tỷ lệ thất bại theo sliding window, đặt minimum number of calls, giới hạn số probe ở HALF_OPEN, phân loại exception hoặc gắn metrics/events chi tiết, **Resilience4j CircuitBreaker** là một phương án phù hợp. Khi đó breaker vẫn nên bao đúng lời gọi dependency:

~~~java
// Minh họa phần handler nếu dùng Resilience4j thay cho native advice.
// pricingBreaker là io.github.resilience4j.circuitbreaker.CircuitBreaker.
.handle(
    StockRequest.class,
    (request, headers) ->
        pricingBreaker.executeSupplier(() -> client.check(request))
)
~~~

Không lắp cả Resilience4j và native advice cùng bảo vệ một lời gọi nếu chưa có lý do cụ thể, vì hai bộ trạng thái có thể đưa ra kết luận khác nhau và làm khó quan sát. Nếu chọn Resilience4j, đặt tên breaker theo dependency, cấu hình sliding window/minimum calls/failure threshold/wait duration, và chỉ định loại exception cần được tính là lỗi khi nghiệp vụ yêu cầu.

## 8. Quan sát trạng thái và xử lý sự cố

Một breaker hoạt động đúng vẫn có thể làm nhiều request bị từ chối trong lúc dependency chưa phục hồi. Vì vậy cần theo dõi **cả nguyên nhân gốc lẫn tác động lên flow**:

| Tín hiệu | Câu hỏi vận hành |
| --- | --- |
| Trạng thái CLOSED / OPEN / HALF_OPEN theo dependency | Mạch nào đang mở, mở từ khi nào và có phục hồi không? |
| Số lỗi/timeout của client, độ trễ p95/p99 | Dependency lỗi thật hay timeout quá ngắn? |
| Số lời gọi bị từ chối nhanh | Có bao nhiêu request bị ảnh hưởng dù không gọi qua mạng? |
| Tỷ lệ dùng fallback/cache và độ cũ dữ liệu | Hệ thống đang suy giảm chức năng tới mức nào? |
| Gateway latency, queue depth, thread pool saturation | Breaker đã giảm áp lực lên flow hay tắc nghẽn chuyển sang nơi khác? |
| Correlation ID / trace ID và loại exception | Một request thất bại ở nhánh nào, do nguyên nhân nào? |

Với Resilience4j có thể đăng ký event listener và tích hợp Micrometer để theo dõi state transition, call outcomes và denied calls. Với native advice, cần instrument quanh handler, Gateway và dependency client theo hệ thống metrics/tracing đang dùng; đừng mặc định mọi metric sẽ tự xuất hiện.

Log nên ghi dependency, breaker name, state, exception class, correlation ID và thời điểm; hạn chế ghi payload nhạy cảm hoặc tạo log trùng lặp theo từng retry. Có thể cảnh báo khi tỷ lệ request bị từ chối tăng lâu, hoặc breaker liên tục dao động OPEN/HALF_OPEN.

## 9. Kịch bản kiểm thử bắt buộc

Dùng một fake **StockClient** kiểm soát được số lần được gọi, kết quả và exception. Tách logic thời gian để test ổn định; với cấu hình native có thể dùng khoảng chờ nhỏ có kiểm soát trong integration test, tránh phụ thuộc thời gian chờ thực tế dài.

| Tình huống | Kết quả cần xác minh |
| --- | --- |
| Dependency khỏe | Gateway nhận đúng reply; client được gọi; breaker đóng |
| Chưa đủ lỗi liên tiếp | Request tiếp theo vẫn đến client |
| Đạt ngưỡng lỗi liên tiếp | Breaker mở; lời gọi mới bị từ chối trước client |
| Đang OPEN | Số lần gọi client **không tăng**; caller nhận lỗi hoặc outcome fallback đúng hợp đồng |
| Hết thời gian chờ | Lời gọi thăm dò được phép; thành công đóng mạch, thất bại mở lại |
| Một request lỗi nghiệp vụ | Validation và lỗi nghiệp vụ không làm breaker đánh giá sai dependency |
| Gateway đồng bộ | Exception/reply truyền về đúng boundary, không treo chờ |
| Flow có Splitter/Aggregator | Correlation được giữ; thiếu nhánh có timeout/partial outcome rõ ràng |
| Nhiều instance chạy song song | Hiểu rằng trạng thái breaker ở mỗi instance có thể khác nhau |

Ví dụ giả lập cụ thể: ngưỡng lỗi liên tiếp là **3**; tạo ba lần client ném exception. Gửi request thứ tư và kiểm tra **client không được gọi thêm**. Sau khoảng chờ, cho client trả kết quả thành công ở lần thăm dò rồi xác minh các request mới lại đi qua. Nếu chỉ mock Gateway để kiểm tra exception mà không kiểm tra số lần client được gọi, test chưa chứng minh được tác dụng bảo vệ của breaker.

## 10. Những lỗi thiết kế thường gặp

1. **Không đặt timeout tại client:** một lời gọi bị treo vẫn giữ tài nguyên rất lâu trước khi có failure cho breaker ghi nhận.
2. **Retry vô hạn hoặc retry lệnh ghi thiếu idempotency:** làm trầm trọng sự cố và có thể tạo tác dụng phụ lặp lại.
3. **Dùng một breaker cho mọi dependency:** một hệ thống lỗi kéo theo các hệ thống khỏe bị ngắt.
4. **Bắt exception rồi trả thành công giả:** breaker không biết dependency hỏng và dữ liệu downstream trở nên sai.
5. **Nhầm lỗi nghiệp vụ với lỗi hạ tầng:** dữ liệu đầu vào không hợp lệ làm mở mạch không cần thiết.
6. **Không định nghĩa fallback contract:** Gateway/Aggregator không biết phân biệt dữ liệu hợp lệ, dữ liệu cũ và trạng thái chưa xác định.
7. **Không giám sát rejected calls và queue:** breaker có thể đang mở hàng giờ mà chỉ quan sát lỗi client nên tưởng lỗi đã hết.
8. **Cho rằng trạng thái được chia sẻ giữa các pod:** một pod đã OPEN nhưng pod khác vẫn liên tục gọi dependency.

## 11. Checklist trước khi đưa vào vận hành

- [ ] Xác định đúng dependency và handler cần được bảo vệ, dùng breaker riêng cho miền lỗi độc lập.
- [ ] Có timeout tại client, retry hữu hạn nếu cần và chính sách cho thao tác không idempotent.
- [ ] Chọn rõ thuật toán: lỗi liên tiếp của native advice hay failure-rate window của Resilience4j.
- [ ] Định nghĩa kết quả khi OPEN: fail fast, cache có kiểm soát hoặc xử lý bất đồng bộ.
- [ ] Giữ correlation ID, xử lý ErrorMessage đúng mô hình đồng bộ/bất đồng bộ và đặt hạn cho Aggregator.
- [ ] Đo trạng thái breaker, số request bị chặn, lỗi dependency, độ trễ và ảnh hưởng lên queue.
- [ ] Kiểm thử mạch mở, thăm dò, phục hồi và xác minh bằng **số lần gọi client thực tế**.

Circuit breaker giúp flow Spring Integration **suy giảm có kiểm soát** khi dependency bất ổn. Hiệu quả bảo vệ đến từ việc đặt nó sát lời gọi bên ngoài, phân loại lỗi đúng, dùng timeout và retry hợp lý, rồi bảo đảm các nhánh message vẫn có kết quả hoặc đường xử lý lỗi rõ ràng.
