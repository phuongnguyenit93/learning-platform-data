# Circuit breaker, giới hạn đồng thời và suy giảm chức năng

Khi một dịch vụ managed phản hồi chậm hoặc ngừng hoạt động, các request đang chờ có thể chiếm hết thread, connection pool và bộ nhớ của ứng dụng Spring Boot. Request mới tiếp tục được gửi sang dependency đang lỗi, làm tải tăng và kéo theo các dịch vụ khác. Một lỗi ban đầu ở storage, database hoặc messaging có thể trở thành sự cố diện rộng.

Ba cơ chế cần phối hợp để giới hạn tác động:

- **Circuit breaker:** tạm ngừng gọi dependency khi tỷ lệ lỗi hoặc thời gian phản hồi vượt ngưỡng, sau đó thăm dò có kiểm soát khi dependency có khả năng phục hồi.
- **Giới hạn đồng thời (concurrency limit) và bulkhead:** giới hạn số request đang chạy và cô lập tài nguyên để một dependency hoặc nhóm request không chiếm hết năng lực của ứng dụng.
- **Suy giảm chức năng (graceful degradation):** duy trì phần chức năng còn an toàn khi một dependency không sẵn sàng, ví dụ dùng dữ liệu cache có ghi rõ độ cũ, tắt tính năng phụ hoặc trả trạng thái chờ xử lý.

Circuit breaker không thay thế timeout, retry, rate limit hay bulkhead. Mỗi cơ chế xử lý một dạng rủi ro khác nhau. Trong module Spring Cloud Provider Integration, các cơ chế này cần được áp dụng khi Spring Boot gọi Azure, AWS và Google Cloud managed services, đồng thời phải hiểu retry/throttling vốn có trong SDK của từng provider.

## 1. Mục tiêu học tập

Sau bài này, người học có thể:

1. Giải thích failure cascade và vì sao dependency chậm có thể làm ứng dụng cạn thread/connection.
2. Mô tả trạng thái CLOSED, OPEN và HALF_OPEN của circuit breaker.
3. Chọn sliding window, failure threshold, slow-call threshold và half-open probes.
4. Phân biệt timeout, retry, circuit breaker, bulkhead, concurrency limit và rate limiter.
5. Thiết kế timeout budget, retry budget và admission control.
6. Cô lập tài nguyên theo dependency, operation hoặc tenant.
7. Thiết kế fallback và graceful degradation không che giấu lỗi nghiệp vụ.
8. Cấu hình Spring Boot với Spring Cloud CircuitBreaker và Resilience4j.
9. Kết hợp resilience policy của ứng dụng với SDK retry, quota và throttling của cloud provider.
10. Đo lường, kiểm thử và vận hành các cơ chế phục hồi khi dependency chậm hoặc unavailable.

## 2. Failure cascade: một dependency chậm có thể làm sập nhiều phần

Giả sử Order API gọi Inventory service, database và Payment provider. Inventory bị chậm từ 100 ms lên 8 giây. Nếu mỗi request giữ một servlet thread trong lúc chờ, số request đang chạy tăng nhanh.

~~~mermaid
flowchart TD
    A[Client requests tăng] --> B[Order API gọi Inventory]
    B --> C[Inventory phản hồi chậm]
    C --> D[Request giữ thread và connection]
    D --> E[Thread pool / connection pool cạn]
    E --> F[Request khác timeout]
    F --> G[Retry làm tải tăng thêm]
    G --> C
    E --> H[Payment / database / health endpoint bị ảnh hưởng]
~~~

Vấn đề không chỉ là Inventory không sẵn sàng. Order API vẫn nhận request mới, giữ tài nguyên lâu hơn, retry thêm và làm các dependency khác bị ảnh hưởng. Đây là **cascading failure** hoặc failure cascade.

Một hệ thống có khả năng chịu lỗi cần:

- Phát hiện dependency chậm hoặc lỗi.
- Ngừng tạo thêm tải vô ích.
- Giới hạn số request được phép chờ.
- Giữ tài nguyên riêng cho các chức năng quan trọng.
- Có đường xử lý thay thế khi nghiệp vụ cho phép.
- Khôi phục từ từ để tránh tạo một đợt tải mới.

## 3. Bốn cơ chế khác nhau: timeout, retry, circuit breaker và bulkhead

| Cơ chế | Câu hỏi nó trả lời | Tác dụng |
| --- | --- | --- |
| **Timeout** | Chờ tối đa bao lâu cho một lần gọi? | Không để request chờ vô hạn |
| **Retry** | Có nên thử lại lỗi tạm thời không? | Khắc phục lỗi ngắn hạn |
| **Circuit breaker** | Có nên tiếp tục gọi dependency đang lỗi không? | Tạm dừng lời gọi có xác suất thất bại cao |
| **Bulkhead/concurrency limit** | Bao nhiêu lời gọi được chạy đồng thời? | Giới hạn tài nguyên và cô lập tải |

Có thể bổ sung **rate limiter** để giới hạn số lần gọi trong một khoảng thời gian và **load shedding** để từ chối công việc sớm khi hệ thống quá tải.

Ví dụ:

- Timeout 2 giây giới hạn thời gian chờ một request.
- Retry tối đa một lần với backoff khi nhận lỗi throttling có thể phục hồi.
- Circuit breaker OPEN sau khi quan sát tỷ lệ lỗi cao, từ chối lời gọi mới trong một khoảng thời gian.
- Bulkhead chỉ cho tối đa 20 lời gọi Inventory chạy đồng thời.
- Rate limiter cho phép tối đa 100 request/giây theo quota được phân bổ.

Không cơ chế nào tự thay thế các cơ chế còn lại.

## 4. Circuit breaker hoạt động thế nào?

Circuit breaker theo dõi kết quả các lần gọi dependency và chuyển trạng thái khi điều kiện cấu hình được thỏa mãn.

~~~mermaid
stateDiagram-v2
    [*] --> CLOSED
    CLOSED --> OPEN: Failure / slow-call threshold reached
    OPEN --> HALF_OPEN: Wait duration elapsed
    HALF_OPEN --> CLOSED: Probe calls succeed
    HALF_OPEN --> OPEN: Probe calls fail
~~~

### CLOSED

- Request được phép đi tới dependency.
- Circuit breaker ghi nhận thành công, lỗi và/hoặc thời gian phản hồi.
- Khi tỷ lệ lỗi hoặc slow call vượt threshold trong cửa sổ quan sát, breaker chuyển OPEN.

### OPEN

- Request mới bị từ chối nhanh mà không gọi dependency.
- Ứng dụng có thể chạy fallback hoặc trả lỗi phù hợp.
- Sau thời gian chờ, breaker chuyển HALF_OPEN hoặc được chuyển tự động theo cấu hình.

### HALF_OPEN

- Chỉ cho phép một số lượng nhỏ probe call.
- Nếu probe thành công theo policy, breaker chuyển CLOSED.
- Nếu probe thất bại hoặc quá chậm, breaker quay lại OPEN.
- Những request vượt số probe cho phép vẫn bị từ chối.

### Vì sao cần HALF_OPEN?

Nếu sau một outage, mọi instance đồng thời gửi hàng nghìn request tới dependency vừa phục hồi, dịch vụ có thể bị quá tải lần nữa. HALF_OPEN giới hạn số lời gọi thăm dò và tăng tải dần khi có bằng chứng dependency đã phục hồi.

Circuit breaker không nhất thiết hủy các request đang chạy khi chuyển OPEN. Những request đã được gửi vẫn cần timeout/cancellation riêng.

## 5. Failure rate và slow-call rate

Circuit breaker có thể đánh giá hai loại tín hiệu:

- **Failure rate:** tỷ lệ call được xem là thất bại trong sliding window.
- **Slow-call rate:** tỷ lệ call vượt ngưỡng thời gian được coi là chậm.

Ví dụ cửa sổ có 20 call:

- 10 call thất bại, failure rate là 50%.
- 12 call mất hơn 2 giây, slow-call rate là 60%.

Nếu threshold tương ứng là 50% và 60%, breaker có thể OPEN khi đủ số call tối thiểu và điều kiện được thỏa mãn theo cấu hình.

### Các tham số cần chọn

| Tham số | Ý nghĩa | Câu hỏi thiết kế |
| --- | --- | --- |
| Sliding window type | Cửa sổ theo số call hoặc thời gian | Traffic có đều hay theo burst? |
| Sliding window size | Số call hoặc thời gian được quan sát | Cần phản ứng nhanh tới mức nào? |
| Minimum number of calls | Số call tối thiểu trước khi tính tỷ lệ | Tránh mở circuit chỉ từ một lỗi đơn lẻ |
| Failure rate threshold | Tỷ lệ lỗi kích hoạt OPEN | Mức lỗi nào không còn chấp nhận được? |
| Slow-call duration threshold | Ngưỡng một call bị xem là chậm | Phù hợp latency budget của operation? |
| Slow-call rate threshold | Tỷ lệ call chậm kích hoạt OPEN | Dependency chậm tới mức nào cần ngừng gọi? |
| Wait duration in OPEN | Thời gian giữ circuit OPEN | Dependency thường phục hồi trong bao lâu? |
| Permitted calls in HALF_OPEN | Số probe được phép | Thăm dò bao nhiêu để đủ tin cậy? |

Không sao chép một bộ threshold cho mọi dependency. Một truy vấn cache, lệnh ghi payment và thao tác upload file có latency profile, rủi ro và SLA khác nhau.

## 6. Chọn lỗi nào được tính vào circuit breaker?

Không phải mọi exception đều chứng minh dependency đang lỗi.

Nên phân biệt:

- Network timeout, connection reset, service unavailable: thường là dependency failure.
- HTTP 429 hoặc lỗi throttling: dependency/quota đang bị giới hạn; có thể tính là failure nhưng cần phối hợp Retry-After và rate control.
- HTTP 5xx: thường là lỗi phía dịch vụ, tùy operation.
- HTTP 400 do payload sai: lỗi request/application, không nên làm breaker mở.
- HTTP 401/403 do thiếu quyền: lỗi cấu hình/identity, thường cần cảnh báo và xử lý riêng; retry liên tục không sửa được.
- Business rejection như insufficient inventory hoặc payment declined: kết quả nghiệp vụ hợp lệ, không phải dependency outage.
- Validation exception trong ứng dụng: không tính là lỗi dịch vụ bên ngoài.

Dùng allowlist/denylist exception có chủ đích. Nếu breaker tính mọi RuntimeException, một bug trong code hoặc business rejection có thể làm circuit OPEN dù dependency khỏe.

### Ignore exception và record exception

Trong Resilience4j, có thể cấu hình exception cần ghi nhận và exception cần bỏ qua. Cần tránh cấu hình mâu thuẫn và kiểm tra thứ tự ưu tiên theo phiên bản thư viện.

Nếu một exception bị ignore, nó không nên làm tăng failure rate. Nhưng ứng dụng vẫn phải trả kết quả nghiệp vụ phù hợp và ghi log/metric cho lỗi đó.

## 7. Circuit breaker không giới hạn concurrency

Circuit breaker OPEN ngăn lời gọi mới sau khi threshold bị vượt. Nhưng khi circuit còn CLOSED, nó có thể cho phép rất nhiều request đồng thời. Nếu dependency chậm nhưng chưa đủ số call để mở circuit, thread và connection vẫn có thể cạn.

Vì vậy cần phối hợp:

- Timeout để giới hạn thời gian chờ.
- Bulkhead/concurrency limit để giới hạn in-flight calls.
- Circuit breaker để ngừng gọi dependency khi failure/slow-call rate cao.
- Rate limiter để giới hạn tốc độ request.
- Queue bounds để giới hạn công việc chờ.

Đây là các lớp bảo vệ khác nhau.

## 8. Bulkhead và giới hạn đồng thời

Bulkhead lấy ý tưởng từ các khoang kín trên tàu: sự cố ở một khoang không làm toàn bộ tàu chìm. Trong ứng dụng, mỗi dependency hoặc nhóm công việc có ngân sách tài nguyên riêng.

Ví dụ:

~~~text
Order API thread pool: 200 threads
  ├── Inventory calls: max 20 concurrent
  ├── Payment calls: max 10 concurrent
  ├── Blob uploads: max 8 concurrent
  └── Optional recommendations: max 5 concurrent
~~~

Nếu Inventory chậm, nó chỉ chiếm tối đa 20 slot được phân bổ. Payment và các chức năng khác còn tài nguyên để hoạt động.

### Semaphore bulkhead

Semaphore bulkhead giới hạn số lời gọi đang chạy:

- Không tạo thread pool riêng.
- Lời gọi chạy trên thread hiện tại.
- Có thể cấu hình thời gian chờ lấy permit.
- Khi hết permit, request bị từ chối hoặc chờ trong thời gian ngắn theo policy.

Phù hợp với lời gọi đồng bộ và cần giới hạn in-flight calls mà không muốn tạo thêm executor.

### Thread-pool bulkhead

Thread-pool bulkhead dùng executor và queue riêng:

- Tách worker của dependency khỏi thread pool chính.
- Có queue giới hạn.
- Có thể cách ly lời gọi blocking.
- Khi thread và queue đều đầy, request bị từ chối.
- Tốn thêm thread, context switching và quản lý lifecycle.

Phù hợp khi cần cô lập một nhóm tác vụ blocking. Queue phải có giới hạn; queue không giới hạn chỉ chuyển overload thành độ trễ và memory growth.

### Chọn semaphore hay thread pool

| Tiêu chí | Semaphore bulkhead | Thread-pool bulkhead |
| --- | --- | --- |
| Cô lập thread | Không tạo pool riêng | Có executor riêng |
| Giới hạn in-flight | Có | Có |
| Queue | Thường không có queue công việc riêng | Có queue hữu hạn |
| Chi phí | Thấp hơn | Cao hơn |
| Blocking call | Dùng thread gọi hiện tại | Có thể cách ly khỏi request thread |
| Phù hợp | Giới hạn concurrency đơn giản | Cô lập tác vụ blocking và queue |

Không dùng thread-pool bulkhead để che giấu một dependency chậm bằng cách tăng queue. Mục tiêu là giới hạn tác động và từ chối sớm khi quá tải.

## 9. Concurrency limit, rate limit và admission control

Ba khái niệm liên quan nhưng khác nhau:

- **Concurrency limit:** tối đa bao nhiêu request được thực hiện cùng lúc.
- **Rate limit:** tối đa bao nhiêu request được nhận trong một đơn vị thời gian.
- **Admission control:** quyết định có nhận công việc mới hay từ chối ngay dựa trên năng lực hiện tại.

Ví dụ dependency xử lý 50 request/giây, mỗi request mất 2 giây. Có thể cần khoảng 100 request đang chạy nếu muốn duy trì throughput đó. Nhưng nếu latency tăng lên 10 giây, cùng một concurrency có thể khiến throughput giảm và backlog tăng.

Giới hạn concurrency bảo vệ số tác vụ đang giữ tài nguyên. Rate limiter bảo vệ quota theo thời gian. Admission control kết hợp tình trạng thread pool, queue, deadline và priority để quyết định nhận công việc.

### Không xếp hàng vô hạn

Một queue dài có thể làm request chờ lâu hơn deadline của client. Khi cuối cùng được xử lý, client có thể đã timeout và gửi lại request khác.

Dùng queue có giới hạn và quy định:

- Queue capacity.
- Maximum queue wait.
- Deadline/TTL của công việc.
- Priority hoặc fairness giữa tenant.
- Hành động khi queue đầy: reject, shed hoặc lưu bền vững vào queue managed.
- Metrics queue depth và oldest wait.

### Per-tenant fairness

Một tenant gửi burst lớn không nên chiếm hết capacity của dependency dùng chung. Có thể áp dụng concurrency/rate budget theo tenant hoặc tier, nhưng cần tránh tạo quá nhiều limiter instance không được cleanup.

## 10. Timeout budget và deadline propagation

Timeout phải được thiết kế theo toàn bộ request path, không cấu hình độc lập từng lớp.

Ví dụ API có deadline 3 giây:

~~~text
Client deadline: 3.0 s
  ├── Authentication / validation: 0.2 s
  ├── Inventory call: 1.0 s
  ├── Database: 0.8 s
  └── Response / safety margin: 1.0 s
~~~

Nếu mỗi dependency timeout 3 giây, request tổng thể có thể kéo dài nhiều lần deadline của client.

### Timeout cần có ở nhiều lớp

- Connection timeout: thời gian thiết lập kết nối.
- Read/response timeout: thời gian chờ phản hồi.
- Request/operation timeout: deadline cho một lần gọi.
- Queue wait timeout: thời gian chờ permit hoặc executor.
- Overall request deadline: giới hạn toàn bộ request.
- Broker processing/visibility/lock deadline: phù hợp thời gian xử lý message.

### Deadline propagation

Khi service A gọi service B, nên truyền deadline hoặc remaining timeout để B không tiếp tục xử lý sau khi caller đã hết thời gian chờ. Không phải mọi SDK đều hỗ trợ truyền deadline thống nhất; cần cấu hình client timeout và cancellation phù hợp.

Với blocking SDK call, cancellation của Future hoặc TimeLimiter không chắc đã dừng network operation nếu client không hỗ trợ interrupt. Cấu hình timeout ngay trong HTTP client/cloud SDK.

## 11. Retry cần có budget và backoff

Retry hữu ích khi lỗi ngắn hạn, nhưng retry không giới hạn có thể khuếch đại sự cố.

Nếu mỗi request thử lại 3 lần ở 3 tầng (API, service và SDK), số lời gọi có thể tăng theo tích số. Khi dependency đã quá tải, retry storm làm tình hình xấu hơn.

### Retry policy

- Chỉ retry lỗi có khả năng phục hồi.
- Giới hạn số lần thử.
- Dùng exponential backoff và jitter.
- Tôn trọng Retry-After nếu dịch vụ trả về.
- Không retry khi overall deadline không còn đủ.
- Dùng idempotency key cho thao tác ghi.
- Không retry business rejection hoặc lỗi validation.
- Xác định một tầng chịu trách nhiệm retry chính.

### Circuit breaker và retry order

Thứ tự decorator ảnh hưởng breaker quan sát điều gì:

- Nếu breaker bao ngoài retry, một logical operation có thể được tính là một call; thời gian đo có thể bao gồm toàn bộ retry.
- Nếu retry bao ngoài breaker, từng attempt có thể được breaker quan sát riêng; một logical operation có thể làm failure counter tăng nhiều lần.

Không có một thứ tự đúng cho mọi trường hợp. Chọn theo ý nghĩa muốn đo và kiểm tra cấu hình decorator/aspect của phiên bản Resilience4j đang dùng. Dù chọn cách nào, retry vẫn phải có budget tổng.

## 12. Graceful degradation: giữ chức năng còn an toàn

Graceful degradation là thiết kế để hệ thống tiếp tục cung cấp phần giá trị còn có thể bảo đảm khi một dependency không sẵn sàng.

Ví dụ:

| Dependency gặp sự cố | Có thể suy giảm chức năng |
| --- | --- |
| Recommendation API | Ẩn khu vực gợi ý; vẫn cho tìm và đặt hàng |
| Product image storage | Hiển thị placeholder hoặc metadata; không làm hỏng trang sản phẩm |
| Read replica/search index | Dùng cache hoặc truy vấn nguồn chính trong giới hạn |
| Notification provider | Lưu notification intent vào outbox; gửi sau |
| Analytics | Ghi buffer/queue hoặc tạm dừng analytics; không chặn checkout |
| Inventory service | Hiển thị trạng thái chưa xác nhận; không tự khẳng định còn hàng |
| Payment provider | Giữ order ở trạng thái PAYMENT_PENDING; không đánh dấu đã thanh toán |

### Fallback phải trung thực

Fallback không được biến lỗi thành một kết quả nghiệp vụ giả:

- Không trả “payment successful” khi payment provider timeout.
- Không hiển thị tồn kho chính xác nếu chỉ có cache cũ.
- Không coi notification đã gửi khi chỉ mới lưu outbox.
- Không trả dữ liệu stale mà không có metadata/giới hạn độ cũ khi người dùng cần dữ liệu mới.
- Không trả success cho thao tác ghi nếu hệ thống chưa lưu bền vững ý định xử lý.

Fallback nên thể hiện rõ trạng thái như PENDING, STALE, UNAVAILABLE hoặc DEGRADED tùy API contract.

## 13. Các kiểu fallback phổ biến

### Cache fallback

Đọc dữ liệu cache gần nhất khi nguồn chính unavailable:

- Lưu cachedAt hoặc version.
- Có maximum staleness.
- Chỉ dùng với dữ liệu chấp nhận được độ cũ.
- Không dùng cache stale để quyết định payment, balance hoặc inventory tuyệt đối nếu không có policy.

### Feature fallback

Tắt tính năng không thiết yếu:

- Bỏ recommendation.
- Ẩn thống kê realtime.
- Dùng layout cơ bản.
- Tạm ngừng export hoặc báo cáo lớn.

### Async acceptance

Khi xử lý đồng bộ không thể hoàn tất, có thể lưu command/outbox bền vững và trả HTTP 202 Accepted cùng operation ID. Chỉ trả 202 sau khi ý định được lưu bền vững. Client tra cứu trạng thái sau.

### Read-only mode

Khi dependency ghi dữ liệu bị lỗi, ứng dụng có thể cho phép đọc dữ liệu an toàn và tạm từ chối thao tác ghi. Cần nêu rõ dữ liệu đọc có thể stale.

### Static/default response

Dùng giá trị mặc định chỉ khi nó không gây hiểu nhầm. Ví dụ ảnh placeholder có thể chấp nhận; số dư tài khoản mặc định bằng 0 thì không.

## 14. Load shedding và ưu tiên công việc

Khi năng lực xử lý thấp hơn lưu lượng đến, không thể giữ mọi request trong queue vô thời hạn. **Load shedding** từ chối một phần công việc để bảo vệ phần quan trọng hơn.

Có thể ưu tiên:

- Payment/order state transitions cao hơn analytics.
- Request tương tác người dùng cao hơn batch backfill.
- Tenant có quota/priority phù hợp.
- Công việc còn deadline đủ dài.
- Tác vụ có thể retry an toàn.

Từ chối sớm thường tốt hơn để request chờ đến khi hết deadline rồi thất bại. API có thể trả 429 Too Many Requests khi client vượt rate quota hoặc 503 Service Unavailable khi server/dependency tạm thời không thể nhận thêm công việc. Dùng Retry-After nếu có thể đưa ra thời điểm thử lại hợp lý.

Không trả 429/503 như một cách che giấu lỗi business validation; status phải phản ánh đúng loại vấn đề.

## 15. Spring Boot và Resilience4j

Resilience4j cung cấp các module circuit breaker, retry, bulkhead, rate limiter và time limiter. Spring Cloud CircuitBreaker cung cấp abstraction để ứng dụng gọi qua một API thống nhất với implementation tương ứng.

Các ví dụ dưới đây minh họa cách tổ chức; dependency và cấu hình phải khớp Spring Boot, Spring Cloud release train và Resilience4j version của dự án.

### 15.1. Circuit breaker annotation

~~~java
@Service
public class InventoryClient {

    private final InventoryHttpClient httpClient;

    public InventoryClient(InventoryHttpClient httpClient) {
        this.httpClient = httpClient;
    }

    @CircuitBreaker(
            name = "inventory",
            fallbackMethod = "inventoryFallback")
    public InventoryResult getInventory(String sku) {
        return httpClient.getInventory(sku);
    }

    private InventoryResult inventoryFallback(
            String sku,
            Throwable cause) {
        return InventoryResult.unavailable(sku);
    }
}
~~~

Fallback có cùng tham số gốc và thêm exception ở cuối theo quy tắc fallback method của Resilience4j. Kiểm tra signature thực tế khi dùng overload/reactive type.

Trong ví dụ, unavailable phải thể hiện trạng thái không xác định/không sẵn sàng. Không trả số lượng tồn kho bằng 0 nếu đó không phải dữ liệu thật.

### 15.2. Cấu hình circuit breaker

Ví dụ YAML:

~~~yaml
resilience4j:
  circuitbreaker:
    instances:
      inventory:
        slidingWindowType: COUNT_BASED
        slidingWindowSize: 20
        minimumNumberOfCalls: 10
        failureRateThreshold: 50
        slowCallDurationThreshold: 2s
        slowCallRateThreshold: 60
        waitDurationInOpenState: 10s
        permittedNumberOfCallsInHalfOpenState: 3
        automaticTransitionFromOpenToHalfOpenEnabled: true
~~~

Các giá trị chỉ là điểm bắt đầu để minh họa. Trong production cần đo latency và error baseline, sau đó chọn threshold theo SLO và traffic thực tế.

### 15.3. Phân loại exception

~~~yaml
resilience4j:
  circuitbreaker:
    instances:
      inventory:
        recordExceptions:
          - java.io.IOException
          - java.util.concurrent.TimeoutException
        ignoreExceptions:
          - com.example.BusinessRuleException
~~~

Ví dụ chỉ ra ý tưởng phân loại. Các exception thực tế có thể được bọc trong SDK exception hoặc CompletionException; cần xác minh exception chain mà breaker quan sát được. Không ignore một exception chỉ vì muốn tránh mở circuit nếu đó thực chất là dependency failure.

## 16. Cấu hình Bulkhead và TimeLimiter

### Semaphore bulkhead

~~~yaml
resilience4j:
  bulkhead:
    instances:
      inventory:
        maxConcurrentCalls: 20
        maxWaitDuration: 0
~~~

Giới hạn 20 call đang chạy đồng thời và không chờ lấy permit. Khi hết slot, call mới bị từ chối nhanh theo policy.

### Thread-pool bulkhead

~~~yaml
resilience4j:
  thread-pool-bulkhead:
    instances:
      blobUpload:
        maxThreadPoolSize: 8
        coreThreadPoolSize: 4
        queueCapacity: 16
        keepAliveDuration: 20ms
~~~

Thread pool và queue cần được sizing theo thời gian xử lý, CPU, memory và giới hạn kết nối. Queue capacity 16 không có nghĩa mọi request đều được xử lý; khi đầy, caller cần nhận rejection và fallback/HTTP response phù hợp.

### TimeLimiter

~~~yaml
resilience4j:
  timelimiter:
    instances:
      inventory:
        timeoutDuration: 2s
        cancelRunningFuture: true
~~~

TimeLimiter phù hợp với lời gọi bất đồng bộ/Future theo integration được hỗ trợ. cancelRunningFuture không bảo đảm mọi blocking network call dừng ngay. Cấu hình connect/read/operation timeout của HTTP client hoặc cloud SDK vẫn cần thiết.

## 17. Dùng Spring Cloud CircuitBreaker API

Spring Cloud CircuitBreaker cho phép ứng dụng làm việc với CircuitBreakerFactory. Ví dụ minh họa:

~~~java
@Service
public class CatalogService {

    private final CircuitBreakerFactory<?, ?> circuitBreakerFactory;
    private final CatalogClient catalogClient;

    public CatalogService(
            CircuitBreakerFactory<?, ?> circuitBreakerFactory,
            CatalogClient catalogClient) {
        this.circuitBreakerFactory = circuitBreakerFactory;
        this.catalogClient = catalogClient;
    }

    public CatalogItem find(String id) {
        return circuitBreakerFactory
                .create("catalog")
                .run(
                    () -> catalogClient.find(id),
                    error -> CatalogItem.unavailable(id));
    }
}
~~~

API cụ thể và cách cấu hình fallback phụ thuộc implementation/factory được chọn. Nếu cần bulkhead, retry hoặc time limiter, kiểm tra integration tương ứng; không giả định mọi factory tự áp dụng toàn bộ resilience modules.

### Annotation hay programmatic API?

| Cách dùng | Khi phù hợp |
| --- | --- |
| Annotation | Policy rõ ràng theo method, code ít |
| Programmatic API | Cần chọn policy động, compose operation hoặc truyền fallback tại call site |
| Spring Cloud CircuitBreaker | Muốn abstraction giữa implementation |
| Resilience4j trực tiếp | Cần dùng đầy đủ module/API đặc thù của thư viện |

Không đặt breaker ở quá nhiều tầng cho cùng một dependency mà không có mục đích. Một request có thể đi qua controller, service, client wrapper và SDK; nếu mỗi tầng có breaker độc lập, việc đo failure rate và fallback trở nên khó hiểu.

## 18. Reactive và blocking call

Ứng dụng Spring MVC và WebFlux có mô hình tài nguyên khác nhau.

- Blocking SDK call giữ thread trong lúc chờ.
- Reactive client có thể giải phóng event-loop thread khi chờ I/O, nhưng vẫn có thể cạn connection pool, pending queue hoặc memory.
- Không chạy blocking SDK trực tiếp trên reactive event loop.
- Nếu phải gọi blocking API, đưa sang bounded elastic/dedicated executor có giới hạn.
- Circuit breaker không làm blocking code trở thành non-blocking.
- Timeout/cancellation cần được kiểm tra với HTTP client và SDK thực tế.

Với WebFlux, dùng operator và adapter tương thích với reactive publisher. Không bọc Mono trong Future rồi chặn block ở event loop.

## 19. Retry và CircuitBreaker trong Resilience4j

Có thể dùng các module riêng:

~~~java
@Retry(name = "inventory")
@CircuitBreaker(name = "inventory")
@Bulkhead(name = "inventory")
public InventoryResult getInventory(String sku) {
    return inventoryClient.getInventory(sku);
}
~~~

Đây là minh họa composition. Thứ tự aspect/decorator phụ thuộc cấu hình và phiên bản. Cần xác minh:

- Một logical request được breaker tính là một call hay nhiều retry attempt?
- Bulkhead permit được giữ qua toàn bộ retry hay từng attempt?
- TimeLimiter áp dụng cho một attempt hay toàn operation?
- Fallback được gọi khi retry exhausted hay khi breaker OPEN?
- Business exception có bị retry không?
- Cancellation có dừng SDK request không?

Không gắn mọi annotation lên mọi method theo mẫu. Chọn một policy có owner rõ ràng và test các trạng thái.

## 20. Kết hợp với SDK retry của cloud provider

Azure, AWS và Google Cloud SDK có retry, timeout và throttling behavior riêng. Nếu ứng dụng thêm Resilience4j, cần tính tổng số attempt và thời gian chờ.

Ví dụ một lần gọi service có:
- Application retry: tối đa 2 lần thử.
- SDK retry: tối đa 3 attempt mỗi lần gọi.
- HTTP client retry: thêm một tầng.

Tổng request thực tế có thể cao hơn dự kiến. Nên chọn một retry owner chính và giới hạn tổng retry budget.

### AWS

AWS SDK retry mode có thể áp dụng retry cho lỗi transient/throttling theo service và cấu hình. Khi gọi DynamoDB, S3 hoặc SQS:

- Phân biệt throttling với lỗi validation/authorization.
- Dùng SDK timeout và retry policy có budget.
- Giới hạn concurrency theo quota/service capacity.
- Với DynamoDB, theo dõi throttled requests và consumed capacity.
- Với SQS, kiểm soát receive/delete throughput và consumer concurrency.
- Với S3, timeout và retry cần phối hợp multipart upload và cleanup.

### Azure

Azure SDK/service có thể trả 429, 503 hoặc lỗi throttling/server busy tùy dịch vụ:

- Với Cosmos DB, chú ý RU throttling và Retry-After.
- Với Service Bus, xử lý ServerBusy, lock expiry và settlement timeout.
- Với Blob Storage, dùng retry policy nhưng giới hạn số request đồng thời.
- Tránh retry một lỗi RBAC/403 như thể đó là outage tạm thời.
- Theo dõi quota/capacity và latency theo account, container hoặc namespace.

### Google Cloud

Google Cloud client libraries có retry/timeout policy theo API:

- Với Pub/Sub, dùng flow control để giới hạn số message/byte đang xử lý.
- Với Firestore/Spanner, phân biệt transient abort/resource exhaustion với lỗi dữ liệu hoặc permission.
- Với Cloud Storage, giới hạn upload/download concurrency và xử lý retry theo operation semantics.
- Theo dõi quota, 429/503 và request latency.
- Dùng idempotency/conditional write khi retry thao tác ghi.

Không copy nguyên cấu hình retry giữa các provider. Mỗi SDK có exception type, retryable code, deadline và semantics riêng.

## 21. Thiết kế fallback theo loại operation

### Read operation

Có thể dùng cache hoặc stale-while-revalidate nếu dữ liệu chấp nhận độ cũ. Response cần có timestamp/version để caller biết dữ liệu được cập nhật lần cuối khi nào.

### Write operation

Không trả thành công nếu chưa biết write đã commit. Nếu có outbox/local durable queue, trả 202 cùng operation ID khi ý định đã được lưu bền vững. Nếu không thể lưu, trả lỗi có thể retry theo API contract.

### Payment

Không fallback thành payment success. Khi timeout với unknown outcome, giữ trạng thái PENDING/UNKNOWN và reconcile theo provider reference/idempotency key.

### Messaging

Nếu broker unavailable, có thể lưu outbox trong database nếu local transaction thành công. Không ACK message đầu vào chỉ vì event tiếp theo chưa được publish nếu ý định chưa được lưu bền vững.

### Optional feature

Tắt recommendation, analytics hoặc thumbnail generation nếu chức năng chính vẫn có thể hoạt động an toàn. Theo dõi degraded mode để biết tính năng nào đang bị tắt.

## 22. Circuit breaker scope và nhiều instance

Circuit breaker thường lưu state trong process. Mỗi replica có cửa sổ quan sát và trạng thái riêng:

~~~text
Replica A: CLOSED
Replica B: OPEN
Replica C: CLOSED
Replica D: HALF_OPEN
~~~

Điều này có thể xảy ra khi traffic và lịch sử call khác nhau giữa instance. Không giả định một breaker local là circuit toàn cluster.

### Tác động

- Khi một instance OPEN, instance khác có thể vẫn gọi dependency.
- Khi dependency phục hồi, nhiều instance có thể đồng thời chuyển HALF_OPEN và thăm dò.
- Autoscaling tạo instance mới với breaker state ban đầu.
- Local rate limiter/concurrency limit không nhất thiết áp dụng cho toàn fleet.

### Biện pháp

- Chọn probe count nhỏ và giới hạn concurrency theo instance.
- Dùng provider quota/global rate limit nếu cần giới hạn toàn fleet.
- Dùng shared coordination chỉ khi thật sự cần và hiểu thêm dependency mới mà nó tạo ra.
- Theo dõi breaker state theo instance và dependency.
- Dùng jitter cho thời điểm retry/recovery để tránh đồng bộ.
- Thiết kế dependency đủ capacity cho traffic từ tất cả replica.

Không nhất thiết phải đồng bộ circuit breaker state giữa mọi replica. Local breaker thường giúp mỗi instance tự bảo vệ nhanh; quota toàn cục là vấn đề khác.

## 23. Fallback và circuit breaker không nên che giấu lỗi

Fallback hữu ích khi có phương án an toàn. Nhưng fallback không được:

- Trả dữ liệu mặc định làm sai nghĩa nghiệp vụ.
- Bắt mọi Throwable rồi trả success.
- Nuốt lỗi authorization hoặc bug code.
- Gửi request mới tới cùng dependency qua một đường khác không có giới hạn.
- Retry vô hạn bên trong fallback.
- Tạo side effect không idempotent.
- Làm caller mất khả năng phân biệt dữ liệu thật và dữ liệu stale.

Fallback nên có metric riêng: fallback invoked, fallback success, fallback unavailable, stale response và business outcome. Nếu fallback luôn thành công về mặt HTTP nhưng trả dữ liệu không dùng được, SLI phải phản ánh chất lượng nghiệp vụ chứ không chỉ status code.

## 24. Health check và readiness

Không để health check tạo thêm tải hoặc làm sai trạng thái ứng dụng.

- **Liveness:** tiến trình có còn hoạt động không; thường không nên phụ thuộc mọi external service.
- **Readiness:** instance có sẵn sàng nhận loại traffic được định tuyến tới nó không.
- **Dependency health:** quan sát tình trạng từng dependency; không phải mọi dependency optional đều phải làm readiness fail.
- **Circuit breaker health:** trạng thái OPEN có thể là tín hiệu degraded mode, không nhất thiết cần restart instance.

Nếu readiness phụ thuộc một dependency đang outage, toàn bộ replica có thể bị loại khỏi load balancer cùng lúc. Điều này có thể làm hệ thống không phục vụ cả chức năng vẫn còn hoạt động. Chọn dependency critical theo request path và dùng degraded behavior khi phù hợp.

## 25. Observability cho resilience

Theo dõi riêng latency, failure, rejection và fallback.

| Metric | Ý nghĩa |
| --- | --- |
| dependency_call_total | Số lời gọi theo dependency/operation và outcome |
| dependency_latency_seconds | Phân bố latency của lời gọi |
| circuitbreaker_state | Trạng thái CLOSED/OPEN/HALF_OPEN |
| circuitbreaker_not_permitted_total | Số call bị breaker từ chối |
| circuitbreaker_failure_rate | Tỷ lệ lỗi trong cửa sổ |
| circuitbreaker_slow_call_rate | Tỷ lệ call chậm |
| bulkhead_available_concurrent_calls | Số slot còn trống |
| bulkhead_rejected_total | Số call bị từ chối do hết slot |
| executor_queue_depth | Độ sâu queue của thread pool |
| rate_limiter_rejected_total | Số request bị rate limit |
| retry_attempt_total | Số lần retry |
| fallback_invoked_total | Số lần fallback |
| degraded_response_total | Số response ở degraded mode |
| timeout_total | Số timeout theo dependency/operation |

### Log và trace

Ghi các trường:

- Dependency và operation.
- Circuit breaker name/state.
- Retry attempt và retry reason.
- Timeout budget còn lại.
- Bulkhead rejection hoặc queue wait.
- Fallback type và freshness/version của cache.
- Correlation/trace ID.
- Provider request ID khi có.

Không đưa payload nhạy cảm, access token hoặc connection string vào log. Tránh dùng user ID, order ID hoặc request ID làm metric label cardinality cao.

### Dashboard cần trả lời

1. Dependency nào đang chậm hoặc lỗi?
2. Circuit breaker nào OPEN và đã bao lâu?
3. Số request bị từ chối bởi breaker/bulkhead/rate limiter?
4. Thread pool, connection pool và queue có gần đầy không?
5. Retry có khuếch đại traffic không?
6. Fallback có đang trả dữ liệu stale không?
7. Các operation quan trọng như checkout/payment còn thành công không?

## 26. Kiểm thử circuit breaker và bulkhead

Unit test logic fallback chưa đủ. Cần kiểm tra trạng thái breaker và hành vi tài nguyên khi dependency lỗi.

### Circuit breaker test matrix

| Kịch bản | Kết quả mong đợi |
| --- | --- |
| Dependency thành công ổn định | Breaker CLOSED |
| Lỗi dưới threshold | Tiếp tục CLOSED |
| Đủ sample và failure rate vượt threshold | Chuyển OPEN |
| Call khi OPEN | Không gọi dependency; fallback/reject |
| Hết wait duration | Chuyển HALF_OPEN theo policy |
| Probe thành công | Chuyển CLOSED |
| Probe thất bại | Quay lại OPEN |
| Slow-call rate vượt threshold | Có thể OPEN theo cấu hình |
| Business rejection bị ignore | Không tăng failure rate |
| Timeout | Được phân loại đúng theo exception policy |

### Bulkhead test matrix

| Kịch bản | Kết quả mong đợi |
| --- | --- |
| Số call dưới limit | Được thực hiện |
| Vượt semaphore limit | Rejected hoặc chờ đúng maxWaitDuration |
| Thread pool và queue đầy | Rejected theo policy |
| Dependency chậm | Không chiếm quá số slot đã cấp |
| Dependency A bão hòa | Dependency B còn capacity riêng |
| Request hết deadline trong queue | Không tiếp tục xử lý công việc vô ích |

### Failure injection

1. Làm dependency trả 503 trong một khoảng thời gian.
2. Tạo latency tăng dần nhưng chưa có lỗi để kiểm tra slow-call threshold.
3. Giữ request pending để làm đầy bulkhead.
4. Làm HTTP connection pool cạn.
5. Làm dependency trả 429/Retry-After.
6. Khôi phục dependency đột ngột và quan sát HALF_OPEN probes.
7. Scale nhiều replica và kiểm tra recovery burst.
8. Làm fallback cache quá cũ để xác minh response bị từ chối/đánh dấu stale.
9. Cho retry và SDK retry cùng hoạt động để xác minh tổng attempt budget.
10. Kiểm tra liveness/readiness trong degraded mode.

## 27. Bài thực hành: bảo vệ Order API khi Inventory chậm

**Bối cảnh:** Spring Boot Order API gọi Inventory service trên cloud. Inventory có thể trả 429/503 hoặc chậm 5–10 giây. Recommendation và analytics là tính năng phụ. Payment là bước quan trọng và không được giả định thành công khi timeout.

### Phần A — Timeout và retry budget

1. Đặt overall request deadline.
2. Chọn connection/read timeout cho Inventory.
3. Chỉ retry lỗi transient/throttling theo policy.
4. Dùng backoff/jitter và tôn trọng Retry-After.
5. Giới hạn tổng attempt qua application và SDK.

### Phần B — Circuit breaker

1. Tạo breaker riêng cho Inventory read operation.
2. Chọn sliding window và minimum calls theo traffic.
3. Cấu hình failure và slow-call threshold.
4. Phân loại business rejection khỏi dependency failure.
5. Kiểm tra OPEN/HALF_OPEN và probe count.

### Phần C — Bulkhead và admission control

1. Giới hạn Inventory concurrency.
2. Dùng queue hữu hạn hoặc semaphore không chờ dài.
3. Giữ capacity riêng cho Payment và database.
4. Áp dụng rate limit theo quota provider.
5. Trả 503/429 khi không thể nhận thêm công việc an toàn.

### Phần D — Graceful degradation

1. Recommendation lỗi thì ẩn khu vực gợi ý.
2. Analytics lỗi thì ghi nhận để xử lý sau.
3. Inventory timeout thì không khẳng định còn hàng; trả trạng thái cần xác nhận hoặc yêu cầu thử lại.
4. Payment timeout thì giữ PENDING/UNKNOWN và reconcile.
5. Nếu command đã được lưu outbox, trả 202 với operation ID theo contract.

### Phần E — Kiểm thử và quan sát

1. Làm Inventory chậm và xác minh bulkhead không vượt limit.
2. Làm lỗi vượt threshold và xác minh breaker OPEN.
3. Phục hồi Inventory và xác minh HALF_OPEN.
4. Làm recommendation unavailable nhưng checkout vẫn hoạt động.
5. Làm payment timeout và xác minh không trả success giả.
6. Đo rejection, retry, fallback, queue depth và business success rate.

### Sản phẩm cần nộp

- Sơ đồ timeout/retry/circuit breaker/bulkhead.
- Bảng threshold theo dependency và operation.
- Cấu hình Resilience4j và code fallback.
- Bằng chứng concurrency limit và circuit state transition.
- Chính sách degraded response cho read/write/payment.
- Dashboard dependency latency, breaker state, retry và rejection.
- Kết quả failure-injection tests.

### Câu hỏi tự kiểm tra

1. Vì sao timeout không thay thế circuit breaker?
2. Circuit breaker OPEN có giải phóng các request đang chạy không?
3. CLOSED, OPEN và HALF_OPEN khác nhau thế nào?
4. Failure rate và slow-call rate đo điều gì?
5. Vì sao business rejection không nên tính là dependency failure?
6. Bulkhead khác rate limiter thế nào?
7. Semaphore bulkhead và thread-pool bulkhead có trade-off gì?
8. Vì sao queue không giới hạn làm overload nặng hơn?
9. Retry ở nhiều tầng có thể tạo retry storm ra sao?
10. Vì sao cancellation của Future không bảo đảm dừng blocking SDK call?
11. Fallback nào phù hợp với read, write, payment và notification?
12. Vì sao circuit breaker state giữa nhiều replica có thể khác nhau?
13. Azure Cosmos DB 429 và AWS/GCP throttling nên được xử lý cùng retry budget như thế nào?
14. Khi nào nên trả 202, 429 hoặc 503?
15. Health readiness có nên fail khi một dependency optional bị outage không?

## 28. Ghi nhớ

- Timeout giới hạn thời gian chờ; retry xử lý lỗi tạm thời; circuit breaker tạm ngừng gọi dependency đang lỗi; bulkhead giới hạn tài nguyên đồng thời.
- Circuit breaker có ba trạng thái CLOSED, OPEN và HALF_OPEN; probe ở HALF_OPEN cần được giới hạn.
- Failure rate và slow-call rate phải đủ sample trước khi kích hoạt theo policy.
- Không tính business rejection, validation hoặc lỗi code vào dependency failure một cách máy móc.
- Circuit breaker không giới hạn concurrency và không nhất thiết hủy request đang chạy.
- Bulkhead cần giới hạn cả in-flight calls và queue; queue vô hạn chỉ trì hoãn overload.
- Rate limit kiểm soát tốc độ; concurrency limit kiểm soát số việc đang chạy; admission control quyết định có nhận việc mới.
- Retry cần budget tổng, backoff/jitter, deadline và idempotency; phối hợp với retry của SDK.
- Graceful degradation chỉ dùng fallback an toàn, thể hiện rõ stale/pending/unavailable; không giả vờ payment hay write đã thành công.
- Circuit breaker thường có state cục bộ theo instance; quota toàn fleet cần cơ chế giới hạn phù hợp.
- Theo dõi dependency latency, breaker state, rejection, retry, queue, fallback và business success.
- Kiểm thử outage, slow call, throttling, half-open recovery, saturation và degraded mode.

## Tài liệu tham khảo

- [Spring Cloud CircuitBreaker reference](https://docs.spring.io/spring-cloud-circuitbreaker/reference/)
- [Resilience4j CircuitBreaker](https://resilience4j.readme.io/docs/circuitbreaker)
- [Resilience4j Bulkhead](https://resilience4j.readme.io/docs/bulkhead)
- [Resilience4j Retry](https://resilience4j.readme.io/docs/retry)
- [Resilience4j RateLimiter](https://resilience4j.readme.io/docs/ratelimiter)
- [Resilience4j TimeLimiter](https://resilience4j.readme.io/docs/timeout)
- [Azure Cosmos DB request units and throttling](https://learn.microsoft.com/azure/cosmos-db/request-units)
- [Azure Service Bus throttling](https://learn.microsoft.com/azure/service-bus-messaging/service-bus-throttling)
- [AWS SDK retry behavior](https://docs.aws.amazon.com/sdkref/latest/guide/feature-retry-behavior.html)
- [Amazon DynamoDB throttling](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/Programming.Errors.html)
- [Google Cloud retry strategy](https://cloud.google.com/storage/docs/retry-strategy)
- [Google Cloud Pub/Sub flow control](https://cloud.google.com/pubsub/docs/flow-control)
- [Google Cloud API design: errors](https://cloud.google.com/apis/design/errors)
- [Microsoft Azure Architecture Center — Bulkhead pattern](https://learn.microsoft.com/azure/architecture/patterns/bulkhead)
- [Microsoft Azure Architecture Center — Circuit Breaker pattern](https://learn.microsoft.com/azure/architecture/patterns/circuit-breaker)
