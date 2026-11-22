# Bulkhead, circuit breaker và cô lập lỗi dây chuyền

## Mục tiêu học tập

Trong hệ thống phân tán, một dịch vụ thường phụ thuộc vào database, API nội bộ, dịch vụ thanh toán, message broker hoặc nhà cung cấp bên ngoài. Khi một dependency chậm hoặc lỗi, request có thể giữ thread, connection và bộ nhớ lâu hơn bình thường. Hàng đợi chờ tăng lên, pool cạn, timeout lan sang caller và các thành phần vốn khỏe mạnh cũng bắt đầu lỗi. Hiện tượng đó là **cascading failure (lỗi dây chuyền)**.

Ba kỹ thuật thường dùng để giảm phạm vi sự cố là:

- **Bulkhead:** chia tài nguyên thành các khoang cô lập để một nhóm workload không chiếm hết tài nguyên của nhóm khác.
- **Circuit breaker:** theo dõi lỗi của dependency và tạm ngừng lời gọi khi dependency có dấu hiệu không khỏe, cho phép hệ thống phục hồi.
- **Fault isolation:** thiết kế ranh giới để lỗi được giới hạn trong một thành phần, tenant, request class, vùng hoặc dependency.

Các kỹ thuật này bổ trợ cho timeout, retry budget, backpressure, load shedding, queue và graceful degradation. Chúng không làm dependency hết lỗi; mục tiêu là bảo vệ phần còn lại của hệ thống, giữ khả năng phục vụ chức năng quan trọng và phục hồi có kiểm soát.

Bài học thuộc chương **Độ tin cậy**, tập trung vào Bulkhead, circuit breaker và cô lập lỗi dây chuyền. Trong bối cảnh Cloud Architecture, việc chọn ranh giới cô lập cần xuất phát từ yêu cầu nghiệp vụ, topology mạng, compute, database, mô hình triển khai và mức độ chia sẻ tài nguyên; cần cân bằng độ tin cậy, bảo mật, khả năng mở rộng, chi phí và vận hành theo Well-Architected.

Sau bài học, bạn có thể:

- Giải thích cách lỗi một dependency lan thành sự cố toàn hệ thống.
- Nhận diện resource exhaustion, queue buildup, retry storm và thread/connection starvation.
- Thiết kế bulkhead theo dependency, workload class, tenant, vùng và criticality.
- Mô tả circuit breaker với các trạng thái Closed, Open và Half-Open.
- Chọn failure threshold, slow-call threshold, open duration và probe policy có căn cứ.
- Phối hợp circuit breaker với timeout, retry, backoff, jitter và idempotency.
- Thiết kế fallback/degraded mode không vi phạm bất biến nghiệp vụ.
- Phân biệt lỗi tạm thời, lỗi vĩnh viễn, overload và lỗi nghiệp vụ.
- Quan sát sự cố qua latency, concurrency, queue, breaker state và business SLO.
- Kiểm thử fault injection, recovery, tenant isolation và các kịch bản failover.
- Đánh giá chi phí và rủi ro khi áp dụng các pattern trong hệ thống cloud.

## 1. Lỗi dây chuyền hình thành như thế nào?

Giả sử hệ thống đặt phòng có luồng đồng bộ:

1. API nhận yêu cầu xác nhận booking.
2. Booking service kiểm tra inventory.
3. Booking service gọi payment service.
4. Booking service ghi database và trả kết quả.
5. Notification service gửi thông báo.

Nếu payment service tăng latency từ 100 ms lên 8 giây, các request booking sẽ chờ lâu hơn. Mỗi request giữ thread và có thể giữ connection hoặc tài nguyên khác. Số request đang xử lý đồng thời tăng, pool cạn và request mới bắt đầu chờ. API gateway hết deadline và trả timeout, nhưng tác vụ downstream có thể vẫn tiếp tục tiêu thụ tài nguyên. Client retry, làm số lời gọi payment tăng thêm. Các service khác bị kéo vào sự cố dù bản thân chúng không hỏng.

~~~mermaid
flowchart TD
    C["Traffic vào tăng"] --> API["Booking API"]
    API --> PAY["Payment service chậm"]
    PAY --> WAIT["Request/thread chờ lâu"]
    WAIT --> POOL["Thread / connection pool cạn"]
    POOL --> TIMEOUT["API timeout"]
    TIMEOUT --> RETRY["Client và service retry"]
    RETRY --> PAY
    RETRY --> LOAD["Tải tăng thêm"]
    LOAD --> WAIT
~~~

### 1.1. Các cơ chế lan truyền

| Cơ chế | Điều xảy ra | Hệ quả |
| --- | --- | --- |
| Resource exhaustion | Thread, connection, memory hoặc file descriptor bị giữ | Request mới không được xử lý |
| Queue buildup | Request/job đến nhanh hơn khả năng hoàn tất | Latency và backlog tăng liên tục |
| Retry amplification | Nhiều lớp cùng retry một thao tác | Dependency đang lỗi nhận thêm tải |
| Timeout mismatch | Caller timeout nhưng callee vẫn chạy | Công việc vô ích tiếp tục chiếm tài nguyên |
| Synchronous dependency chain | Một request chờ nhiều dịch vụ tuần tự | Latency cộng dồn, một lỗi ảnh hưởng nhiều service |
| Shared resource contention | Nhiều workload dùng chung DB, pool hoặc executor | Tenant/chức năng khác bị ảnh hưởng |
| Recovery storm | Nhiều client kết nối lại hoặc replay đồng thời | Dependency vừa phục hồi lại bị quá tải |

### 1.2. Availability của chuỗi phụ thuộc

Nếu request cần tất cả dependency tuần tự phải thành công, availability của toàn chuỗi thường thấp hơn từng thành phần. Với giả định độc lập đơn giản:

~~~text
Availability(path)
  = A(service 1) × A(service 2) × ... × A(service n)
~~~

Ví dụ ba dependency có availability 99,9% mỗi dependency, giả sử độc lập:

~~~text
0.999 × 0.999 × 0.999 ≈ 99.7003%
~~~

Đây chỉ là mô hình minh họa. Trong thực tế failure có thể tương quan do chung region, network, identity provider hoặc database. Fallback, cache, queue và degraded mode có thể giảm số dependency bắt buộc cho một số use case.

## 2. Fault isolation: xác định ranh giới cần bảo vệ

Cô lập lỗi bắt đầu bằng câu hỏi: **một thành phần hỏng thì những workload nào được phép bị ảnh hưởng?**

Ranh giới cô lập có thể theo:

- Dependency: payment, search, notification, reporting.
- Resource: thread pool, connection pool, queue, CPU, memory.
- Workload class: interactive, background, batch, admin.
- Tenant/customer: một tenant không chiếm hết tài nguyên shared.
- Region/zone: lỗi vùng không lan sang vùng khác.
- Criticality: booking confirmation tách khỏi email notification.
- Data plane/control plane: thao tác phục vụ người dùng không phụ thuộc hoàn toàn vào control-plane API.

### 2.1. Dependency graph và failure domain

Vẽ dependency graph để xác định những thành phần có thể tạo failure propagation:

~~~mermaid
flowchart LR
    U["Client"] --> G["API Gateway"]
    G --> B["Booking service"]
    B --> I["Inventory DB"]
    B --> P["Payment API"]
    B --> N["Notification"]
    B --> S["Search"]
    N --> Q["Message queue"]
    Q --> W["Notification worker"]
    S --> IDX[("Search index")]
~~~

Trong ví dụ, notification thường không cần nằm trên đường đồng bộ xác nhận booking. Có thể ghi notification intent vào outbox/queue sau khi booking commit để payment/search outage không làm booking thất bại. Inventory DB và payment có thể là dependency quan trọng hơn, nhưng payment cũng có thể được phối hợp bằng trạng thái pending và saga thay vì giữ request mở vô hạn.

### 2.2. Phân loại criticality

| Loại chức năng | Khi dependency lỗi | Hành vi mong muốn |
| --- | --- | --- |
| Booking/inventory invariant | Không được tạo booking sai | Từ chối/giữ trạng thái pending an toàn |
| Payment capture | Không được giả định đã trừ tiền | Trạng thái UNKNOWN và reconciliation |
| Search recommendation | Có thể giảm trải nghiệm | Cache/stale result hoặc bỏ thành phần phụ |
| Notification email | Có thể gửi trễ | Queue và retry có giới hạn |
| Analytics dashboard | Có thể chậm dữ liệu | Hiển thị thời điểm cập nhật và backlog |
| Admin export | Có thể trì hoãn | Queue riêng, quota, status tracking |

Không phải chức năng nào cũng cần cùng mức availability. Thiết kế degrade phải dựa trên hậu quả nghiệp vụ nếu bước đó bị bỏ hoặc chậm.

## 3. Bulkhead pattern là gì?

Bulkhead lấy ý tưởng các khoang ngăn trên tàu: nếu một khoang bị ngập, các khoang khác vẫn có thể hoạt động. Trong phần mềm, bulkhead chia tài nguyên hoặc năng lực xử lý thành các vùng giới hạn riêng để sự cố của một workload không chiếm hết capacity chung.

~~~mermaid
flowchart TB
    API["Application"] --> B1["Interactive pool"]
    API --> B2["Payment dependency pool"]
    API --> B3["Reporting pool"]
    B1 --> D1["Interactive DB/API"]
    B2 --> D2["Payment API"]
    B3 --> D3["Reporting DB"]
~~~

Nếu reporting bị chậm, pool riêng của reporting có thể đầy nhưng request interactive vẫn còn tài nguyên. Đây là lợi ích cốt lõi: **giới hạn blast radius**.

### 3.1. Bulkhead theo thread/concurrency pool

Mỗi dependency hoặc workload class có giới hạn concurrency riêng. Khi một dependency chậm, chỉ pool dành cho dependency đó bị bão hòa. Các dependency khác không phải tranh cùng toàn bộ thread.

Ví dụ:

| Pool | Maximum concurrent calls | Mục đích |
| --- | ---: | --- |
| Inventory calls | 24 | Kiểm tra/giữ tồn kho |
| Payment calls | 12 | Gọi provider thanh toán |
| Search calls | 20 | Truy vấn tìm kiếm |
| Reporting jobs | 4 | Báo cáo nặng |
| Notification | Async queue | Không chặn API chính |

Con số phải dựa trên capacity downstream, traffic profile và SLO. Không chia đều số thread theo cảm tính.

### 3.2. Bulkhead theo connection pool

Một ứng dụng có thể dùng pool JDBC riêng cho reporting và transactional path, hoặc giới hạn concurrency cho từng workload. Nếu reporting truy vấn nặng, nó không nên chiếm toàn bộ connection mà booking transaction cần.

Tuy nhiên, hai pool vẫn kết nối tới cùng database. Tổng connection phải nằm trong connection budget; bulkhead ở application không tự cô lập CPU, I/O hoặc lock của database. Có thể cần read replica, workload group hoặc database riêng cho isolation mạnh hơn.

### 3.3. Bulkhead theo queue/worker

Tách queue hoặc consumer concurrency cho job nặng và job quan trọng:

- Queue interactive event có latency priority.
- Queue export/report có concurrency thấp.
- Queue payment reconciliation có retention và alert riêng.
- Notification có thể chấp nhận delay và được xử lý theo throughput còn lại.

Nếu tất cả job dùng chung FIFO queue, tenant hoặc workload có nhiều message có thể tạo head-of-line blocking. Tách queue giúp isolation nhưng tăng số thành phần cần quan sát và quản lý.

### 3.4. Bulkhead theo tenant

Trong nền tảng multi-tenant, có thể áp dụng:

- Per-tenant rate limit và concurrency cap.
- Weighted fair queueing theo service tier.
- Per-tenant job quota và storage quota.
- Dedicated worker/database pool cho tenant đặc biệt.
- Shard/partition theo tenant group.
- Per-tenant circuit breaker khi gọi dependency riêng của tenant.

Không nhất thiết tạo pool vật lý cho từng tenant. Với hàng chục nghìn tenant, số pool/broker/resource riêng có thể quá lớn. Có thể dùng limiter và scheduler chia sẻ nhưng có fairness, quota và isolation có mức độ.

### 3.5. Bulkhead theo region hoặc availability zone

Các region hoặc zone có thể có compute, network và database endpoint riêng. Bulkhead vùng giúp một lỗi DNS, egress hoặc dependency theo region không làm ảnh hưởng toàn bộ deployment. Cần tránh shared control plane, secret service hoặc global database trở thành điểm lỗi chung.

## 4. Chọn kích thước bulkhead

Bulkhead quá nhỏ gây reject/throttle dù downstream còn capacity. Bulkhead quá lớn không giới hạn được blast radius. Kích thước phải xuất phát từ downstream capacity và budget tổng.

### 4.1. Ước lượng concurrency từ Little's Law

Trong điều kiện steady state:

~~~text
Concurrent calls ≈ Arrival rate × Average service time
~~~

Ví dụ payment API nhận 80 call/giây, thời gian service trung bình 150 ms:

~~~text
80 calls/s × 0.15 s = 12 concurrent calls
~~~

Nếu p99 tăng lên 2 giây, concurrency tức thời có thể tăng cao hơn nhiều. Dùng average để ước lượng ban đầu, nhưng benchmark với phân phối duration, burst và tail latency.

### 4.2. Xác định capacity budget

Giả sử payment provider cho phép 100 concurrent requests trên tài khoản của tổ chức, nhưng còn có một service khác dùng chung 30. Booking service chỉ nên được cấp phần capacity đã thỏa thuận, chẳng hạn 50 concurrent với headroom còn lại cho retry/reconciliation. Bulkhead local cần nhân với số application replica và vùng triển khai.

~~~text
Fleet concurrency ceiling
  = Instance count × Per-instance bulkhead limit
~~~

Nếu 8 pod cùng có semaphore limit 20, tổng số call có thể đạt 160. Nếu provider chỉ cho phép 100, local bulkhead không đủ; cần distributed limiter, proxy/gateway quota hoặc phân bổ budget theo replica/region.

### 4.3. Queue length và queue timeout

Bulkhead không chỉ là concurrency. Queue chờ không giới hạn sẽ biến overload thành latency lớn và memory growth.

Cần quy định:

- Maximum pending tasks.
- Maximum wait time.
- Reject policy khi đầy.
- Priority và fairness.
- Deadline propagation.
- Cancellation khi caller không còn cần kết quả.

Với request tương tác, reject nhanh có hướng dẫn retry-after đôi khi tốt hơn giữ request quá deadline.

## 5. Circuit breaker là gì?

Circuit breaker ngăn ứng dụng tiếp tục gọi một dependency đang lỗi hoặc quá chậm. Thay vì mỗi request đều chờ timeout dài, breaker mở và trả lỗi/fallback nhanh trong một khoảng thời gian. Sau đó, nó cho phép một số probe kiểm tra dependency đã phục hồi chưa.

~~~mermaid
stateDiagram-v2
    [*] --> Closed
    Closed --> Open: Failure/slow-call threshold reached
    Open --> HalfOpen: Wait duration elapsed
    HalfOpen --> Closed: Probe successes meet policy
    HalfOpen --> Open: Probe failure / threshold breached
~~~

Ba trạng thái chính:

- **Closed:** lời gọi được phép đi qua; breaker ghi nhận success/failure/slow call trong cửa sổ đo.
- **Open:** lời gọi bị chặn ngay, không gọi dependency; có thể trả fallback hoặc lỗi có kiểm soát.
- **Half-Open:** chỉ cho một số probe giới hạn đi qua để thử dependency; kết quả quyết định đóng lại hay mở lại.

Circuit breaker thường hoạt động theo dependency và đôi khi theo operation class. Không dùng một breaker toàn ứng dụng nếu các endpoint có đặc tính lỗi và SLO khác nhau.

## 6. Các tham số của circuit breaker

| Tham số | Ý nghĩa | Câu hỏi thiết kế |
| --- | --- | --- |
| Failure rate threshold | Tỷ lệ lỗi kích hoạt breaker | Bao nhiêu lỗi trong bao nhiêu call? |
| Slow call duration threshold | Thời gian coi là call chậm | Ngưỡng phù hợp với deadline nào? |
| Slow call rate threshold | Tỷ lệ call chậm kích hoạt breaker | Latency tail nào báo hiệu quá tải? |
| Sliding window size | Số call hoặc khoảng thời gian được thống kê | Traffic thấp cần window thế nào? |
| Minimum number of calls | Số mẫu tối thiểu trước khi đánh giá | Tránh mở breaker vì một lỗi đơn lẻ |
| Open state duration | Thời gian chặn trước probe | Dependency cần bao lâu để phục hồi? |
| Permitted half-open calls | Số probe cho phép | Có đủ thấp để không tạo recovery storm? |
| Exception/result classifier | Loại lỗi nào được tính là failure | 4xx nghiệp vụ có nên mở breaker? |

Các threshold phải dựa trên baseline và dependency contract. Ví dụ 50% lỗi trên tối thiểu 20 call trong 30 giây có thể là điểm bắt đầu cho một service có traffic cao; không phải giá trị chung cho mọi hệ thống.

### 6.1. Không tính mọi response lỗi như nhau

Ví dụ:

- HTTP 503 hoặc connection reset từ dependency: thường là technical failure.
- Timeout: failure hoặc slow call.
- HTTP 429: overload/rate limiting; có thể cần backoff và breaker riêng.
- HTTP 400 do input không hợp lệ: thường không cho biết dependency hỏng.
- HTTP 401 do credential sai: có thể là cấu hình/identity incident, không nhất thiết là transient failure.
- Business rejection như “không còn phòng”: không phải dependency availability failure.

Nếu mọi HTTP 4xx/5xx đều được tính giống nhau, breaker có thể mở do lỗi nghiệp vụ hoặc client gửi dữ liệu sai. Cần exception/result classifier rõ ràng.

### 6.2. Sliding window

Có thể đánh giá theo số lượng call gần nhất hoặc khoảng thời gian gần nhất. Window theo count phù hợp khi traffic ổn định; window theo time phản ánh tốc độ lỗi theo thời gian nhưng cần minimum calls để tránh mẫu quá nhỏ.

Traffic thấp cần chính sách khác: breaker không nên mở chỉ vì một call lỗi rồi đóng ngay khi hết thời gian nếu chưa có probe đủ tin cậy.

## 7. Circuit breaker không thay thế timeout

Nếu không có timeout, request có thể treo lâu trước khi breaker thấy failure hoặc slow call. Timeout đặt giới hạn cho một lời gọi; circuit breaker kiểm soát việc có tiếp tục gửi lời gọi hay không.

~~~mermaid
flowchart LR
    R["Incoming request"] --> CB["Circuit breaker"]
    CB --> T["Dependency timeout"]
    T --> D["Dependency"]
    CB --> F["Fallback / controlled error"]
~~~

Timeout nên ngắn hơn deadline tổng của caller và phù hợp với SLO. Ví dụ request deadline 2 giây, phần dependency có budget 500 ms; không để call payment giữ request trong 10 giây.

### 7.1. Timeout budget xuyên chuỗi

Nếu request gọi ba dependency tuần tự, tổng thời gian có thể là tổng các timeout cộng xử lý nội bộ. Cần phân chia budget:

~~~text
Total request deadline
  = Internal processing budget
  + Dependency A budget
  + Dependency B budget
  + Persistence/response budget
~~~

Với lời gọi song song, latency là thời gian của nhánh chậm nhất cộng overhead; nhưng mỗi nhánh vẫn tiêu thụ tài nguyên. Khi deadline đã hết, cancel work nếu có thể để tránh thao tác vô ích tiếp tục chạy.

## 8. Retry, backoff và circuit breaker

Retry hữu ích với lỗi transient, nhưng retry không giới hạn có thể tăng tải lên dependency đang yếu. Kết hợp retry và breaker cần xác định rõ thứ tự và ngân sách.

### 8.1. Exponential backoff với jitter

~~~text
delay(attempt)
  = min(maxDelay, baseDelay × 2^attempt) + randomJitter
~~~

Backoff giúp giãn các lần thử; jitter tránh nhiều client retry cùng nhịp. Giới hạn attempts và tổng elapsed time theo deadline. Không retry lỗi permanent như validation failure hoặc permission denied.

### 8.2. Retry budget

Có thể giới hạn số retry theo tỷ lệ so với request gốc hoặc theo một ngân sách toàn service. Khi retry budget cạn, trả lỗi có kiểm soát hoặc đưa công việc vào queue nếu nghiệp vụ cho phép.

Không retry đồng thời ở mọi tầng. Nếu client retry 3 lần, API retry 3 lần, service downstream retry 3 lần, một thao tác có thể tạo tới 27 lời gọi. Chọn một tầng sở hữu retry cho mỗi dependency hoặc truyền retry budget/deadline xuyên chuỗi.

### 8.3. Idempotency

Retry một operation ghi có thể tạo duplicate side effect nếu response đầu tiên bị mất sau khi commit. Cần idempotency key, unique business key, conditional update hoặc reconciliation. Circuit breaker không giải quyết ambiguity của transaction đã commit.

## 9. Phối hợp bulkhead và circuit breaker

Hai pattern có vai trò khác nhau:

| Pattern | Câu hỏi được giải quyết | Tác dụng chính |
| --- | --- | --- |
| Timeout | Một call chờ tối đa bao lâu? | Giới hạn thời gian giữ tài nguyên |
| Bulkhead | Bao nhiêu call có thể chạy đồng thời? | Giới hạn blast radius |
| Circuit breaker | Có nên tiếp tục gọi dependency? | Ngừng gửi traffic tới dependency lỗi |
| Rate limiter | Tốc độ request tối đa? | Bảo vệ capacity và entitlement |
| Retry budget | Được thử lại bao nhiêu? | Hạn chế retry amplification |
| Backpressure | Producer cần giảm tốc ra sao? | Điều hòa lưu lượng |
| Load shedding | Khi quá tải, bỏ loại traffic nào? | Giữ capacity cho workload quan trọng |
| Queue | Có thể trì hoãn công việc không? | Hấp thụ burst và tách thời gian xử lý |

Một luồng thường có thể là: request vào rate limiter → lấy slot bulkhead → kiểm tra circuit breaker → thực hiện call với timeout → retry có giới hạn nếu policy cho phép → trả kết quả/fallback. Thứ tự thực tế phụ thuộc thư viện và cách tính concurrency; cần kiểm tra slot có bị giữ trong suốt retry hay không.

### 9.1. Ví dụ cấu hình Resilience4j

Ví dụ cấu hình minh họa:

~~~yaml
resilience4j:
  circuitbreaker:
    instances:
      paymentProvider:
        slidingWindowType: COUNT_BASED
        slidingWindowSize: 20
        minimumNumberOfCalls: 10
        failureRateThreshold: 50
        slowCallDurationThreshold: 500ms
        slowCallRateThreshold: 50
        waitDurationInOpenState: 10s
        permittedNumberOfCallsInHalfOpenState: 3
        automaticTransitionFromOpenToHalfOpenEnabled: true
  timelimiter:
    instances:
      paymentProvider:
        timeoutDuration: 600ms
  bulkhead:
    instances:
      paymentProvider:
        maxConcurrentCalls: 12
        maxWaitDuration: 50ms
~~~

Các giá trị cần hiệu chỉnh theo traffic, provider quota, latency baseline và timeout budget. Tùy phiên bản/module, cách cấu hình TimeLimiter, thread pool bulkhead và circuit breaker decorator có thể khác. Hãy xác minh đúng phiên bản thư viện và test integration.

### 9.2. Semaphore hay thread-pool bulkhead?

- **Semaphore bulkhead:** giới hạn số call đồng thời trên thread hiện tại. Ít thread switching, phù hợp lời gọi blocking nếu caller thread budget được quản lý.
- **Thread-pool bulkhead:** dùng executor/thread pool riêng, có queue giới hạn. Có thể tách thread workload nhưng tạo thêm thread, context switching và queue; cần timeout/rejection policy.

Không tạo thread pool lớn cho mọi dependency. Tổng thread count trên toàn instance và toàn fleet vẫn phải nằm trong capacity của compute.

## 10. Fallback và graceful degradation

Khi breaker Open, ứng dụng cần quyết định trả gì. Fallback hợp lệ tùy nghiệp vụ:

- Search có thể dùng cached result với thời điểm cập nhật.
- Recommendation có thể bỏ qua và hiển thị nội dung mặc định.
- Notification có thể queue lại để gửi sau.
- Analytics có thể hiển thị dữ liệu stale với freshness marker.
- Booking có thể trả trạng thái pending hoặc tạm không xác nhận.
- Payment không nên báo “thành công” chỉ vì provider timeout.

### 10.1. Fallback phải giữ business invariant

Fallback không được biến lỗi kỹ thuật thành thành công giả. Ví dụ inventory service không phản hồi không có nghĩa phòng còn trống. Payment timeout không có nghĩa giao dịch thất bại hay thành công; trạng thái có thể là UNKNOWN và phải query/reconcile.

### 10.2. Cache fallback

Cache có thể giữ dữ liệu gần nhất khi dependency unavailable. Cần quy định:
- Dữ liệu nào được phép stale?
- Stale tối đa bao lâu?
- Có marker thời gian và nguồn không?
- Có dữ liệu nào không được dùng để ra quyết định ghi?
- Cache miss trong lúc breaker Open sẽ trả gì?

Cache fallback phù hợp với dữ liệu tham khảo; không dùng snapshot tồn kho cũ để xác nhận booking nếu có thể bán vượt khả năng.

### 10.3. Queue fallback

Nếu thao tác có thể xử lý bất đồng bộ, ghi intent bền vững vào outbox/queue rồi trả Accepted/Pending. Phải có job ID, trạng thái tra cứu, retry policy, deadline nghiệp vụ và DLQ. Chỉ trả Accepted sau khi intent được ghi bền vững.

## 11. Bulkhead và multi-tenant isolation

Trong SaaS multi-tenant, một tenant lớn có thể tạo burst API, export hoặc query. Bulkhead có thể chia concurrency theo tenant group, service tier hoặc workload class.

~~~mermaid
flowchart TB
    T1["Tenant A requests"] --> L["Tenant-aware limiter"]
    T2["Tenant B requests"] --> L
    T3["Tenant C requests"] --> L
    L --> QA["Queue / pool A"]
    L --> QB["Queue / pool B"]
    L --> QC["Queue / pool C"]
    QA --> W["Shared worker capacity"]
    QB --> W
    QC --> W
~~~

Một scheduler công bằng cần tránh để tenant có nhiều message chiếm toàn bộ worker. Có thể dùng weighted fair queue, per-tenant concurrency cap hoặc reservation theo tier. Với số tenant lớn, chia tenant thành shard/queue group thay vì tạo một queue và pool riêng cho từng tenant.

### 11.1. Per-tenant circuit breaker

Nếu mỗi tenant gọi một integration endpoint riêng, breaker theo tenant có thể ngăn endpoint của tenant X đang lỗi ảnh hưởng các tenant khác. Nhưng nếu tất cả tenant dùng chung một provider endpoint, breaker quá chi tiết có thể tạo quá nhiều state và bỏ lỡ provider-wide outage.

Phải đặt key theo failure domain thật: provider-wide, tenant-specific endpoint, region hoặc operation class. Không chọn key chỉ vì có tenant ID.

## 12. Failure isolation ở database và network

### 12.1. Database

- Tách pool transactional và reporting.
- Dùng statement timeout/lock timeout.
- Giới hạn query concurrency và connection budget.
- Dùng read replica/warehouse cho workload phân tích.
- Partition workload theo database role/resource group nếu engine hỗ trợ.
- Tránh transaction dài và lock giữ qua external I/O.

Bulkhead ở application không ngăn một query tốn CPU hoặc lock làm ảnh hưởng database toàn cục. Cần isolation ở DB engine hoặc tách workload physically khi risk đủ lớn.

### 12.2. Network và dependency

- Tách subnet/security group theo workload và dependency.
- Có quota kết nối/egress và DNS capacity phù hợp.
- Timeout connect/read/write rõ.
- Tránh tất cả service phụ thuộc một NAT/proxy đơn lẻ.
- Multi-AZ endpoint hoặc redundant path khi cần.
- Circuit breaker theo endpoint/region khi failure domain khác nhau.
- Giám sát connection reset, retransmission, DNS error và TLS handshake latency.

Network segmentation phục vụ bảo mật và isolation nhưng không tự cung cấp resilience. Một proxy tập trung duy nhất có thể trở thành failure domain mới nếu không có HA.

## 13. Khi breaker bị cấu hình sai

Circuit breaker cũng có thể gây lỗi nếu threshold hoặc scope không phù hợp.

| Sai lầm | Hệ quả | Điều chỉnh |
| --- | --- | --- |
| Minimum calls quá thấp | Mở breaker vì một vài lỗi ngẫu nhiên | Tăng sample requirement, xem traffic |
| Window quá dài | Phản ứng chậm với outage mới | Điều chỉnh theo tốc độ thay đổi |
| Threshold quá nhạy | Breaker flapping | Dùng hysteresis và probe policy |
| Không phân loại exception | Lỗi nghiệp vụ mở breaker | Chỉ tính lỗi dependency phù hợp |
| Open duration quá dài | Dependency đã khỏe nhưng traffic vẫn bị chặn | Half-open probe và quan sát recovery |
| Probe đồng thời quá nhiều | Recovery storm | Giới hạn half-open calls |
| Breaker toàn app | Một endpoint lỗi chặn các endpoint khỏe | Tách theo failure domain |
| Không có fallback rõ | Trả lỗi khó hiểu hoặc thành công giả | Định nghĩa degraded behavior |
| Retry trước breaker không giới hạn | Breaker khó bảo vệ dependency | Retry budget và timeout hợp lý |
| Chỉ có local breaker mỗi pod | Mọi pod cùng probe dependency | Probe jitter hoặc shared coordination khi cần |

### 13.1. Breaker flapping

Nếu breaker liên tục chuyển Open/Closed vì dependency hồi phục ngắn rồi lại lỗi, traffic probe có thể làm provider dao động. Có thể điều chỉnh open duration, half-open permitted calls, slow-call threshold và sampling window. Cần xem state transition và dependency metrics cùng lúc.

### 13.2. Local breaker và distributed breaker

Breaker local trong mỗi instance đơn giản và không cần coordination. Nhưng khi có 50 pod, mỗi pod có thể tự mở/đóng dựa trên sample riêng. Điều đó có thể làm probe tổng thể lớn hơn dự kiến.

Distributed breaker chia sẻ state giúp phối hợp toàn fleet nhưng thêm dependency, consistency và failure mode. Thường bắt đầu bằng local breaker có half-open concurrency thấp, jitter và global rate limit; chỉ dùng distributed coordination khi có lý do đo được.

## 14. Quan sát bulkhead, breaker và lỗi dây chuyền

Cần theo dõi không chỉ số lỗi mà còn trạng thái tài nguyên và tác động nghiệp vụ.

| Nhóm | Metrics | Ý nghĩa |
| --- | --- | --- |
| Bulkhead | Active calls, available permits, rejected calls, queue depth/wait | Pool có đang bão hòa? |
| Circuit breaker | State, failure rate, slow-call rate, not-permitted calls, transitions | Dependency có bị chặn không? |
| Dependency | Latency p50/p95/p99, timeout, 5xx/429, connection errors | Dependency đang khỏe ra sao? |
| Application | Thread pool, connection pool, CPU, memory, event loop lag | Tài nguyên app có cạn? |
| Queue | Oldest message age, backlog, retry, DLQ | Công việc đang bị trì hoãn? |
| Business | Booking success, payment outcome, pending/unknown count | Người dùng có hoàn tất nghiệp vụ? |
| Recovery | Half-open success, reconnect rate, replay rate | Dependency phục hồi ổn định chưa? |

### 14.1. Log và trace

Ghi service, dependency, operation class, breaker state, retry attempt, timeout reason, bulkhead rejection, tenant tier và correlation ID. Tránh ghi payload nhạy cảm hoặc token.

Trace cần phân biệt:
- Thời gian chờ slot bulkhead.
- Thời gian chờ connection/pool.
- Network/connect time.
- Dependency execution time.
- Retry delay.
- Fallback duration.

Nếu chỉ thấy tổng latency, khó biết request chậm vì queue, app pool hay dependency.

### 14.2. Alert theo tác động

- Breaker Open kéo dài hơn ngưỡng.
- Bulkhead rejection vượt baseline.
- Queue oldest age vượt deadline nghiệp vụ.
- Dependency p99 tăng và slow-call rate vượt ngưỡng.
- Payment UNKNOWN hoặc reconciliation backlog tăng.
- Nhiều service cùng timeout tới một endpoint.
- Half-open probe liên tục thất bại.
- Thread/connection pool pending tăng dù CPU không cao.

Mỗi alert cần owner và runbook. Không nên page người trực cho từng breaker transition đơn lẻ nếu không có tác động; tổng hợp theo dependency và business SLO.

## 15. SLO và kịch bản chất lượng

Các giá trị dưới đây chỉ là ví dụ minh họa. Hãy thay bằng SLO của sản phẩm và capacity đã kiểm chứng.

| Mã | Tình huống | Phản hồi kỳ vọng | Thước đo minh họa |
| --- | --- | --- | --- |
| QA-REL-01 | Payment API timeout liên tục | Breaker Open, request không giữ thread chờ dài | Open trong 30 giây sau khi threshold đạt; booking API giữ deadline |
| QA-REL-02 | Reporting worker quá tải | Pool reporting đầy nhưng interactive pool còn năng lực | Interactive p95 không tăng quá budget đã định |
| QA-REL-03 | Dependency bắt đầu phục hồi | Half-open probe giới hạn, breaker chỉ đóng khi đủ success | Không tạo probe burst; success probe đạt policy |
| QA-REL-04 | Notification provider lỗi | Booking vẫn commit, notification được queue | Booking success không phụ thuộc email provider |
| QA-REL-05 | Tenant tạo burst export | Fair scheduler/tenant cap bảo vệ tenant khác | Interactive SLO của tenant khác vẫn đạt |
| QA-REL-06 | Retry và timeout đồng thời | Retry budget giới hạn amplification | Số attempt tối đa theo policy; không vượt provider quota |
| QA-REL-07 | Payment response mất sau commit | Không retry mù tạo payment duplicate | UNKNOWN được đối soát; không có charge trùng trong fault test |
| QA-REL-08 | Một AZ/proxy lỗi | Traffic chuyển sang capacity khỏe theo policy | RTO và error budget đạt; không recovery storm |

### 15.1. SLO kỹ thuật và SLO nghiệp vụ

Circuit breaker Open có thể làm tăng số request bị từ chối nhưng ngăn toàn hệ thống sụp đổ. Do đó cần theo dõi cả:
- Availability/latency của endpoint.
- Tỷ lệ booking/payment hoàn tất đúng.
- Tỷ lệ fallback và dữ liệu stale.
- Thời gian queue job hoàn tất.
- Số operation UNKNOWN cần reconciliation.

Không coi breaker “hoạt động đúng” là thành công nếu người dùng không thể hoàn tất nghiệp vụ trong thời gian dài.

## 16. Fault injection và chaos testing

Một thiết kế resilience chỉ đáng tin khi các failure mode đã được thử. Test nên có giả thuyết, giới hạn blast radius, điều kiện dừng và tiêu chí phục hồi.

### 16.1. Thử nghiệm nên có

1. Tăng latency dependency lên 5 lần trong thời gian ngắn.
2. Làm dependency trả 5xx/429 theo tỷ lệ xác định.
3. Ngắt network giữa application và dependency.
4. Làm chậm database để kiểm tra pool exhaustion.
5. Làm đầy reporting bulkhead và xác minh interactive path còn hoạt động.
6. Dừng worker khi queue backlog tăng.
7. Làm breaker chuyển Open rồi phục hồi Half-Open.
8. Tăng burst traffic trong lúc dependency vừa phục hồi.
9. Tạo duplicate request/retry sau khi side effect đã commit.
10. Gây lỗi một tenant hoặc một shard và kiểm tra tenant khác.
11. Fail một AZ hoặc proxy theo môi trường staging/game day phù hợp.
12. Làm log/metrics backend chậm để xác minh observability không gây sự cố thứ cấp.

### 16.2. Bằng chứng cần ghi

- Arrival rate, concurrency và latency.
- Active permits, rejection và pending queue.
- Breaker state transition/time.
- Dependency status và recovery time.
- Thread/connection pool utilization.
- Business success, pending và duplicate count.
- Blast radius: tenant/workload/region nào bị ảnh hưởng.
- Chi phí test và lượng retry/egress phát sinh.

Không chạy chaos experiment không giới hạn trên production. Bắt đầu staging hoặc canary; production experiment cần phạm vi, guardrail và người chịu trách nhiệm rõ.

## 17. Case study: Booking service bảo vệ payment dependency

### 17.1. Bối cảnh

Booking service chạy 12 pod trên Kubernetes. Mỗi pod nhận tối đa 100 request đồng thời. Payment provider có latency bình thường p95 250 ms, nhưng đôi khi chậm tới vài giây. Booking API có deadline 2 giây. Notification và report chạy nền.

Vấn đề: khi payment chậm, thread của Booking service bị giữ, pool HTTP client cạn và request retry làm số call payment tăng. Notification/report cũng dùng chung executor nên bị ảnh hưởng.

### 17.2. Thiết kế lại

- Tạo payment semaphore bulkhead riêng, giới hạn tổng concurrency theo quota provider.
- Timeout payment call 600 ms trong request path.
- Circuit breaker đánh giá failure/slow call với minimum sample và half-open probe nhỏ.
- Retry tối đa theo policy và chỉ cho lỗi transient; dùng idempotency key cho payment operation.
- Notification ghi intent vào outbox sau booking commit, worker có queue riêng.
- Reporting dùng executor/queue riêng với concurrency thấp.
- Khi payment timeout không rõ kết quả, booking ở trạng thái PAYMENT_PENDING/UNKNOWN và reconciliation truy vấn provider.
- Dashboard theo dõi breaker state, rejected calls, payment p99, unknown count và queue age.

~~~mermaid
flowchart TB
    U["Client"] --> API["Booking API"]
    API --> B["Payment bulkhead"]
    B --> CB["Payment circuit breaker"]
    CB --> T["600 ms timeout"]
    T --> PAY["Payment provider"]
    API --> TX["Booking transaction"]
    TX --> DB[("Booking DB")]
    TX --> O[("Outbox")]
    O --> NQ[("Notification queue")]
    NQ --> NW["Notification worker"]
    RQ[("Reporting queue")] --> RW["Reporting worker"]
~~~

### 17.3. Hành vi khi payment lỗi

Nếu provider chậm hoặc lỗi, breaker mở sau khi threshold được đáp ứng. Booking API không tiếp tục gửi lượng call không giới hạn. Client nhận trạng thái pending/temporarily unavailable theo contract; request không báo payment thành công. Khi provider có dấu hiệu phục hồi, một số probe được phép đi qua. Nếu probe đạt policy, breaker đóng lại dần; payment operation chưa rõ kết quả được reconciliation xử lý riêng.

### 17.4. Đánh giá kết quả

Đo trước và sau:
- Booking request p95/p99.
- Payment concurrent calls và timeout.
- Bulkhead rejection.
- Breaker Open duration.
- Số payment UNKNOWN/duplicate.
- Notification completion lag.
- Reporting completion.
- CPU/thread/connection pool utilization.

Một thiết kế chỉ đạt khi failure payment không làm notification/report hoặc booking API mất toàn bộ capacity và khi recovery không tạo burst thứ hai.

## 18. TCO và đánh đổi

Bulkhead và circuit breaker thường tăng thêm cấu hình, telemetry, test và đôi khi compute riêng. Đổi lại, chúng có thể giảm incident lan rộng, giữ capacity cho chức năng quan trọng và giảm lãng phí retry.

Chi phí cần tính:
- Pool/thread/executor/queue riêng và headroom.
- Proxy/gateway/limiter/distributed coordination nếu có.
- Observability cho breaker state và per-dependency metrics.
- Fallback cache hoặc storage.
- Queue retention, replay và reconciliation.
- Kiểm thử failure/chaos và vận hành runbook.
- Capacity nhàn rỗi do isolation hoặc reserved concurrency.

~~~text
Resilience investment value
  = Expected avoided outage impact
    + Reduced retry/overload cost
    + Preserved critical business throughput
    - Added infrastructure and operational cost
~~~

Không thể quy đổi mọi lợi ích thành tiền chính xác. Hãy gắn investment với business impact: số booking được bảo vệ, thời gian gián đoạn giảm, tenant bị ảnh hưởng giảm và error budget được giữ.

## 19. Lỗi thiết kế phổ biến

| Sai lầm | Hậu quả | Cách khắc phục |
| --- | --- | --- |
| Dùng một pool chung cho mọi dependency | Một dependency chậm chiếm toàn bộ thread | Bulkhead theo failure domain |
| Bulkhead limit chỉ tính từng pod | Fleet vượt quota downstream | Tính tổng concurrency và phân bổ global budget |
| Queue không giới hạn | Memory/backlog tăng vô hạn | Bounded queue, deadline và load shedding |
| Circuit breaker không có timeout | Call treo trước khi breaker phản ứng | Timeout rõ theo deadline |
| Retry ở mọi tầng | Retry amplification | Chọn retry owner và budget |
| Mọi lỗi đều mở breaker | Business rejection làm dependency bị chặn | Phân loại exception/result |
| Half-open cho quá nhiều probe | Recovery storm | Giới hạn probe, jitter |
| Fallback trả thành công giả | Sai invariant nghiệp vụ | Pending/UNKNOWN hoặc fallback chỉ cho dữ liệu tham khảo |
| Bulkhead chỉ ở app | DB/queue/network vẫn là shared bottleneck | Cô lập ở đúng tầng tài nguyên |
| Breaker state không quan sát được | Khó giải thích lỗi và vận hành | Dashboard, log, transition alert |
| Không kiểm thử side effect retry | Payment/order bị lặp | Idempotency và reconciliation |
| Dùng circuit breaker như rate limiter | Chặn nhầm hoặc không bảo vệ burst | Tách breaker và rate limiter |

## 20. Bài tập thực hành

Một nền tảng thương mại điện tử có checkout gọi inventory, payment, tax và notification. API deadline là 2 giây. Payment đôi khi chậm 4 giây; notification có thể trễ 5 phút; tax provider giới hạn 50 request/giây. Reporting job chạy cùng cluster và từng làm thread pool cạn.

Hãy thực hiện:

1. Vẽ dependency graph và xác định failure domain.
2. Phân loại dependency nào nằm trên critical path và dependency nào có thể chuyển async.
3. Thiết kế bulkhead concurrency cho inventory, payment, tax, reporting và notification.
4. Tính tổng concurrency toàn fleet nếu có 10 pod với các limit đề xuất; so với quota tax 50 request/giây.
5. Chọn timeout budget cho từng dependency sao cho tổng không vượt deadline 2 giây.
6. Đề xuất circuit breaker threshold, minimum calls, open duration và half-open probe; giải thích cách benchmark.
7. Thiết kế retry/backoff/jitter và retry owner; tính nguy cơ amplification nếu hai tầng cùng retry.
8. Xác định fallback an toàn cho inventory, payment, tax và notification.
9. Thiết kế trạng thái UNKNOWN và reconciliation cho payment timeout sau commit.
10. Xây dashboard/alert theo dependency, bulkhead, breaker và business outcome.
11. Viết fault injection plan cho payment latency, tax 429, reporting overload và worker outage.
12. Đánh giá shared vs isolated pool theo chi phí và blast radius; viết ADR.

**Gợi ý tự đánh giá:** Bài làm đạt khi chỉ ra được resource bị giữ, ranh giới cô lập, tổng capacity toàn fleet, timeout/retry budget, fallback không vi phạm invariant và cách xác minh bằng fault injection.

## 21. Checklist trước production

- [ ] Có dependency graph và failure domain cho các luồng quan trọng.
- [ ] Đã xác định criticality và degraded behavior của từng chức năng.
- [ ] Bulkhead có giới hạn concurrency, queue length và wait time.
- [ ] Capacity được tính ở cấp toàn fleet, gồm autoscaling và deployment overlap.
- [ ] Có isolation theo dependency/workload/tenant khi cần.
- [ ] Circuit breaker phân loại đúng lỗi và có sliding window/minimum calls.
- [ ] Có Closed/Open/Half-Open policy, probe limit và recovery jitter.
- [ ] Timeout budget xuyên request path và cancellation phù hợp.
- [ ] Retry có owner, maximum attempts, backoff, jitter và budget.
- [ ] Operation ghi có idempotency và reconciliation khi outcome không rõ.
- [ ] Fallback không vi phạm invariant nghiệp vụ hoặc security.
- [ ] Queue/backlog có capacity, retention, DLQ và backpressure.
- [ ] Dashboard theo dõi pool, breaker, dependency và business SLO.
- [ ] Alert có owner, severity và runbook.
- [ ] Đã fault-inject outage, latency, overload, duplicate và recovery storm.
- [ ] Đã đánh giá TCO, operational overhead và rủi ro shared bottleneck.

## 22. Đánh giá theo Well-Architected

| Trụ cột | Câu hỏi khi review bulkhead và circuit breaker |
| --- | --- |
| **Operational Excellence** | Breaker state, resource saturation, runbook, game day và recovery có đo/diễn tập được không? |
| **Security** | Tenant/dependency isolation có tránh rò context, credential hoặc dữ liệu giữa các failure domain không? |
| **Reliability** | Bulkhead, timeout, breaker, retry budget và fallback giới hạn blast radius và phục hồi an toàn không? |
| **Performance Efficiency** | Pool size, concurrency, queue và probe có đáp ứng SLO mà không overprovision không? |
| **Cost Optimization** | Isolation capacity, proxy, queue và observability có đem lại lợi ích tương xứng không? |
| **Sustainability** | Có tránh retry vô ích, compute chờ lâu và tài nguyên nhàn rỗi quá mức không? |

**Kết luận:** Bulkhead giới hạn tài nguyên mà một workload có thể chiếm; circuit breaker ngừng gửi lời gọi tới dependency đang lỗi để bảo vệ phần còn lại; fault isolation xác định blast radius theo dependency, tenant, workload hoặc vùng. Chúng chỉ phát huy hiệu quả khi phối hợp với timeout, retry budget, backpressure, idempotency và fallback đúng nghiệp vụ. Hãy đo capacity ở cấp toàn fleet, kiểm thử trạng thái lỗi và phục hồi, rồi điều chỉnh theo SLO cùng các đánh đổi Well-Architected.
