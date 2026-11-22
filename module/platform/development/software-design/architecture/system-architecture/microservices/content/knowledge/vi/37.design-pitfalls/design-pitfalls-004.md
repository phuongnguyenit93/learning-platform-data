# Chuỗi gọi đồng bộ dài làm giảm độ sẵn sàng

> **Chủ đề:** Software Design Architecture → System Architecture → Microservices → Sai lầm thiết kế.  
> **Mục tiêu:** hiểu vì sao một request đi qua nhiều lời gọi đồng bộ làm tăng latency và giảm availability; nhận diện cascading failures, dependency amplification, timeout/retry sai cách; thiết kế đường xử lý có giới hạn bằng deadline, bulkhead, circuit breaker, graceful degradation, cache, messaging và observability.

## 1. Bài toán: một request phụ thuộc vào quá nhiều service

Một trang checkout của nền tảng thương mại điện tử nhận request tại Checkout API. Để trả kết quả, API gọi lần lượt Customer Service để kiểm tra hồ sơ, Cart Service để đọc giỏ hàng, Pricing để tính giá, Promotion để áp dụng giảm giá, Inventory để giữ hàng, Payment để authorize, Shipping để tính giao hàng và Notification để gửi xác nhận.

Nếu mọi lời gọi đều đồng bộ và request chỉ hoàn thành khi tất cả dependency trả lời, Checkout trở nên phụ thuộc vào sức khỏe của cả chuỗi. Một service chậm làm các bước sau phải chờ; một service lỗi có thể khiến toàn bộ request thất bại dù phần lớn hệ thống vẫn hoạt động.

Trong thời gian chờ, request có thể giữ thread, connection, memory và transaction context. Khi tải tăng, hàng đợi dài ra; client timeout rồi retry; downstream nhận thêm tải; sự cố lan rộng.

**Một API có thể có code rất ngắn nhưng dependency graph phía sau rất dài.** Độ sẵn sàng mà người dùng cảm nhận phụ thuộc vào toàn bộ đường đi bắt buộc của request, không chỉ process đang nhận HTTP.

## 2. Synchronous call chain là gì?

Một lời gọi đồng bộ là lời gọi mà caller cần chờ kết quả để tiếp tục bước hiện tại. Với HTTP/gRPC, caller gửi request và giữ workflow đang chạy cho tới khi nhận response hoặc timeout.

~~~text
Client
  -> API Gateway
     -> Checkout Service
        -> Customer Service
        -> Cart Service
        -> Pricing Service
        -> Promotion Service
        -> Inventory Service
        -> Payment Service
        -> Shipping Service
~~~

Phân biệt:

- **Synchronous:** caller cần kết quả ngay để tiếp tục hoặc trả response.
- **Asynchronous:** caller gửi command/event và tiếp tục; kết quả đến sau qua event, callback hoặc trạng thái workflow.
- **Sequential:** bước sau bắt đầu sau khi bước trước hoàn thành.
- **Parallel fan-out:** nhiều dependency được gọi đồng thời.
- **Nested call:** service được gọi lại gọi thêm service khác.
- **Required dependency:** thiếu kết quả làm use case không thể hoàn thành đúng nghiệp vụ.
- **Optional dependency:** dữ liệu có thể thiếu mà vẫn hoàn thành use case với contract phù hợp.

Không phải mọi lời gọi đồng bộ đều xấu. Vấn đề xuất hiện khi call chain sâu, dependency bắt buộc quá nhiều, timeout không được quản lý, hoặc một request giữ tài nguyên trong thời gian dài.

## 3. Availability end-to-end bị ảnh hưởng thế nào?

Giả sử một request cần năm dependency độc lập và tất cả đều phải thành công. Nếu mỗi dependency có availability 99,9% trong cùng cửa sổ đo, bỏ qua lỗi của caller/gateway:

\[
A_{request} \approx 0.999^5 \approx 0.99501
\]

Kết quả minh họa là khoảng 99,501%. Nếu có mười dependency bắt buộc:

\[
A_{request} \approx 0.999^{10} \approx 0.99004
\]

Đây là phép tính **giả định độc lập**, cùng định nghĩa availability và cùng cửa sổ quan sát. Nó không phải dự báo production: lỗi có thể tương quan do dùng chung network, database, identity provider, cluster hoặc control plane.

### 3.1. Required và optional thay đổi kết quả

Nếu Reviews chỉ dùng để hiển thị điểm đánh giá và không bắt buộc cho checkout, không cần biến nó thành điều kiện để checkout thành công. Khi dependency optional được tách khỏi critical path, lỗi của nó không nhất thiết làm use case thất bại.

Ngược lại, nếu Payment authorization là bắt buộc để xác nhận giao dịch, không thể bỏ qua timeout rồi trả “đã thanh toán”. Cần phân biệt pending/unknown với success.

### 3.2. Availability theo request khác SLO theo cửa sổ

Công thức nhân availability là mô hình đơn giản cho các thành phần nối tiếp và độc lập. SLO thực tế đo tỷ lệ request tốt trong một cửa sổ, có thể tính cả latency và correctness. Retry, fallback, redundancy và correlated failures làm kết quả khác đi.

Không lấy availability từng service rồi nhân máy móc nếu kiến trúc có failover, cache, replica, optional branches hoặc shared failure domain.

## 4. Latency tích lũy trong chuỗi gọi

Giả sử một request có bốn bước tuần tự:

~~~text
Gateway       15 ms
Customer      40 ms
Pricing       70 ms
Inventory    100 ms
-------------------
Tổng gần đúng 225 ms
~~~

Nếu Payment thêm 180 ms, request tăng lên khoảng 405 ms, chưa tính queue wait, serialization, network, connection acquisition và thời gian xử lý tại caller.

Với lời gọi tuần tự:

\[
T_{total} \approx \sum_{i=1}^{n} T_i + T_{overhead}
\]

Với các lời gọi thực sự song song và caller đợi tất cả:

\[
T_{fanout} \approx \max(T_1,T_2,\ldots,T_n)+T_{join}
\]

Đây là mô hình gần đúng. Các lời gọi có thể chồng lấn một phần, có dependency giữa chúng, và tail latency không thể tính chính xác bằng cách cộng p99 riêng lẻ.

**Critical path** là chuỗi dependency quyết định thời điểm request có thể hoàn tất. Tối ưu một service không nằm trên critical path có thể không làm request nhanh hơn. Distributed trace giúp nhìn thời điểm bắt đầu/kết thúc từng span, khoảng overlap và queue wait.

## 5. Call graph sâu làm tăng failure surface

Một request tại edge có thể kích hoạt nhiều lời gọi ở các tầng:

~~~text
API
  -> Checkout
       -> Pricing -> Tax
       -> Inventory -> Warehouse
       -> Payment -> Fraud -> Provider adapter
       -> Shipping -> Carrier quote
~~~

Mỗi tầng thêm một network boundary, timeout, connection pool, queue, authentication, serialization, nơi có thể retry và dependency cần vận hành.

Nếu nhiều tầng cùng retry, số attempt có thể tăng theo cấp số nhân theo số tầng. Cần giới hạn fan-out, chiều sâu call graph và số dependency bắt buộc cho từng use case.

## 6. Cascading failure: lỗi một service lan thành sự cố hệ thống

Một vòng lặp thường gặp:

1. Inventory database chậm vì lock contention.
2. Inventory API giữ request và connection lâu hơn.
3. Checkout giữ thread chờ Inventory.
4. Thread pool hoặc connection pool của Checkout cạn.
5. Checkout latency tăng và client timeout.
6. Client retry, làm số request tăng.
7. API Gateway cũng retry Checkout.
8. Inventory nhận thêm tải từ những attempt trùng.
9. Các service dùng chung database/network bắt đầu chậm.

~~~mermaid
flowchart TD
  I[Inventory chậm] --> Q[Checkout queue tăng]
  Q --> T[Checkout timeout]
  T --> R[Client/Gateway retry]
  R --> L[Downstream load tăng]
  L --> I
  Q --> C[Connection/thread pool cạn]
  C --> E[Checkout errors tăng]
~~~

Đây là vòng phản hồi dương: càng chậm càng retry, càng retry càng chậm. Cascading failure thường bắt đầu từ việc nhận nhiều công việc hơn khả năng xử lý và giữ chúng chờ quá lâu.

## 7. Queueing và saturation

Latency không chỉ là thời gian CPU xử lý. Request còn có thể chờ thread/worker, connection từ pool, semaphore permit, database lock, event-loop slot, network socket, rate-limit token hoặc message consumer capacity.

Khi hệ thống gần bão hòa, thời gian chờ có thể tăng rất nhanh. Queue không giới hạn có thể khiến request vẫn được nhận nhưng hoàn thành quá muộn, đồng thời tiêu thụ memory và giữ resource.

Little’s Law trong trạng thái ổn định:

\[
L=\lambda W
\]

Trong đó L là số request trung bình trong hệ thống, λ là throughput và W là thời gian trung bình trong hệ thống. Nếu throughput giữ nguyên nhưng thời gian chờ tăng, số request in-flight tăng theo.

Ví dụ 500 request/giây và thời gian trung bình 0,2 giây tương ứng khoảng 100 request in-flight. Nếu thời gian tăng lên 1 giây, con số có thể thành khoảng 500. Đây là minh họa theo giá trị trung bình, không phải công thức trực tiếp cho p99.

## 8. Tail latency làm request cha chậm

Một dependency có p50 tốt nhưng p99 rất xấu vẫn có thể quyết định tail của API cha.

~~~text
Inventory:
p50    35 ms
p90    70 ms
p95   110 ms
p99   650 ms
~~~

Nếu Checkout đợi Inventory trên critical path, những request rơi vào tail của Inventory cũng có thể nằm trong tail của Checkout.

Nếu một request đợi tất cả n lời gọi độc lập, xác suất có ít nhất một nhánh chậm hơn ngưỡng p là:

\[
P(\text{ít nhất một nhánh chậm})=1-(1-p)^n
\]

Với p=1% và n=20, xác suất xấp xỉ 18,2%. Đây là mô hình độc lập và các call đều bắt buộc. Khi có shared bottleneck, sự chậm có thể tương quan và cần đo bằng trace/metrics thật.

Parallel fan-out giảm thời gian chờ so với tuần tự, nhưng **không loại bỏ rủi ro một nhánh straggler**.

## 9. Timeout: giới hạn thời gian chờ

Mỗi outbound call cần timeout phù hợp. Không để HTTP client, database query hoặc connection acquisition chờ vô hạn.

Các loại timeout:

- DNS/connect timeout.
- TLS handshake timeout.
- Connection pool acquisition timeout.
- Response/read timeout.
- Database query/statement timeout.
- Queue wait timeout.
- Overall request deadline.

Timeout cần dựa trên SLO và phân phối latency. Timeout quá ngắn tạo false failures; timeout quá dài giữ tài nguyên và làm queue kéo dài.

### 9.1. Timeout từng bước chưa đủ

Nếu Checkout có budget 500 ms nhưng gọi năm dependency, mỗi dependency đặt timeout 500 ms, request có thể vượt xa 500 ms khi các bước nối tiếp hoặc retry.

Cần một **overall deadline** và truyền remaining budget xuống các tầng. Child timeout không được vượt thời gian còn lại của parent.

~~~text
Client budget              500 ms
Gateway/auth overhead       40 ms
Checkout internal work      30 ms
Remaining for dependencies 430 ms
Response/serialization      30 ms
Reserve                      30 ms
~~~

Các con số minh họa. Phải đo overhead thật và phân bổ budget theo critical path.

## 10. Deadline propagation và cancellation

Timeout là giới hạn của một operation. **Deadline** là thời điểm cuối cùng mà toàn bộ workflow cần hoàn thành.

Khi service A gọi B, A truyền deadline hoặc remaining duration. B tiếp tục chia budget cho C. Không reset một timeout mới đầy đủ ở mỗi tầng.

Giao thức có thể truyền absolute deadline hoặc thời lượng còn lại. Khi dùng absolute timestamp giữa máy, cần xét clock skew. Trong một process Java, dùng monotonic clock như System.nanoTime() để đo elapsed time; không truyền mốc nanoTime giữa process.

Server vẫn cần cap deadline theo giới hạn nội bộ để client không yêu cầu giữ tài nguyên vô hạn.

Khi parent timeout/cancel, child calls nên được hủy nếu transport/framework hỗ trợ. Tuy nhiên cancellation không đảm bảo server từ xa đã dừng query hoặc side effect.

Cần propagate cancellation context, đặt timeout tại HTTP/DB client, kiểm tra request còn hợp lệ trước công việc đắt tiền, đo task tiếp tục sau parent cancellation và dùng idempotency cho thao tác có side effect. Không coi timeout là bằng chứng giao dịch chưa commit.

## 11. Retry: hữu ích nhưng dễ khuếch đại sự cố

Retry có thể xử lý transient failure như connection reset ngắn hoặc một số lỗi rate-limit. Nhưng retry khi backend đang quá tải làm số attempt tăng và giữ queue lâu hơn.

Nguyên tắc:

1. Chỉ retry lỗi được phân loại là retryable.
2. Giới hạn số attempt.
3. Exponential backoff có jitter.
4. Có retry budget theo traffic.
5. Chỉ một tầng chịu trách nhiệm retry cho logical operation khi có thể.
6. Không retry nếu remaining deadline không đủ.
7. Chỉ retry side effect khi có idempotency.
8. Theo dõi attempts per operation và extra QPS.

Nếu ba tầng, mỗi tầng tối đa ba attempt, một request logic có thể tạo tối đa 27 attempt ở tầng cuối trong một số cách lồng retry. Cần kiểm tra policy toàn call graph thay vì xem riêng từng service.

### 11.1. Retry không thay timeout

Retry không có timeout sẽ chờ vô hạn. Timeout không có retry policy phù hợp có thể làm một lỗi tạm thời thành thất bại người dùng. Hai cơ chế cần phối hợp trong cùng deadline.

### 11.2. Không retry mọi HTTP status

- Một số 5xx có thể transient, nhưng không phải luôn luôn.
- 429 thường cần tôn trọng Retry-After và budget.
- 400/401/403 thường không tự hết khi retry.
- Timeout có thể xảy ra sau khi server đã commit.
- POST/payment cần idempotency key hoặc query trạng thái trước khi retry.

## 12. Circuit breaker: fail-fast khi dependency suy giảm

Circuit breaker thường có ba trạng thái:

- **CLOSED:** cho phép request và thu thập lỗi/slow-call metrics.
- **OPEN:** từ chối nhanh request mới trong thời gian cooldown.
- **HALF_OPEN:** cho một số request thử để kiểm tra phục hồi.

Nếu Reviews đang chậm, breaker có thể mở và Checkout trả phần review unavailable thay vì giữ request lâu. Nếu Payment là dependency bắt buộc, breaker OPEN phải trả trạng thái lỗi/pending phù hợp, không giả lập thanh toán thành công.

Circuit breaker giúp caller không tiếp tục dồn request vào dependency đang suy giảm. Nó không thay thế timeout, bulkhead, rate limiting hoặc capacity planning.

Cấu hình cần xét failure rate, slow-call rate, minimum calls, sliding window, open duration, half-open probes và exception/status được tính là failure. Threshold quá nhạy gây flapping; threshold quá lỏng phát hiện muộn. Phải kiểm thử bằng traffic đại diện.

## 13. Bulkhead: giới hạn tài nguyên theo dependency

Bulkhead tách hạn mức để một dependency chậm không chiếm hết tài nguyên của caller.

~~~text
Một instance Checkout:
Inventory calls:        tối đa 30 in-flight
Payment calls:          tối đa 20 in-flight
Pricing calls:          tối đa 25 in-flight
Recommendations calls:  tối đa  5 in-flight
~~~

Khi Reviews/Recommendations chậm, chúng không được lấy hết worker/connection dành cho Payment.

Bulkhead có thể thực hiện bằng semaphore, thread pool riêng, connection pool riêng, concurrency limit, queue bounded hoặc rate limit.

Cần tính tổng trên toàn bộ replicas. Nếu 10 instances đều có 30 permits cho Inventory, backend có thể nhận 300 calls đồng thời.

### 13.1. Queue bounded và fast rejection

Queue vô hạn che giấu overload bằng cách tích lũy công việc. Queue nhỏ giúp hệ thống từ chối sớm, giảm thời gian chờ và bảo vệ memory.

Khi quá giới hạn, trả 429/503 hoặc fallback theo API contract. Không để rejection biến thành lỗi 500 khó phân biệt nếu nguyên nhân là overload đã biết.

## 14. Graceful degradation: giữ chức năng cốt lõi

Không phải mọi dependency đều có cùng mức quan trọng.

| Dependency | Vai trò | Khi chậm/lỗi |
| --- | --- | --- |
| Customer identity/authorization | Bảo vệ quyền truy cập | Không bỏ qua kiểm tra bảo mật |
| Pricing | Xác định giá giao dịch | Không trả giá giả hoặc stale ngoài policy |
| Inventory reservation | Giữ hàng | Trả pending/unavailable theo contract |
| Payment authorization | Giao dịch tiền | Không báo paid khi chưa xác nhận |
| Reviews | Nội dung bổ trợ | Có thể hiển thị unavailable |
| Recommendations | Gợi ý | Có thể bỏ qua hoặc dùng cache hợp lệ |
| Delivery estimate | Ước tính | Có thể trì hoãn nếu không phải cam kết |
| Notification | Thông báo sau giao dịch | Có thể xử lý bất đồng bộ sau commit |

Graceful degradation có nghĩa hệ thống vẫn cung cấp phần chức năng đúng mà nó có thể bảo đảm. Không có nghĩa bỏ qua invariant để trả HTTP 200.

Một API có thể trả dữ liệu chính và trạng thái phần tùy chọn:

~~~json
{
  "orderId": "ORD-100",
  "status": "PENDING",
  "price": {
    "status": "READY",
    "amountMinor": 150000,
    "currency": "VND"
  },
  "recommendations": {
    "status": "UNAVAILABLE",
    "items": []
  }
}
~~~

READY với items rỗng khác UNAVAILABLE. Client cần biết dữ liệu chưa có, không có kết quả, stale hay lỗi.

## 15. Đẩy công việc không cần kết quả tức thời sang asynchronous

Một số tác vụ không cần hoàn thành trước khi trả response:

- Gửi email/SMS.
- Tạo audit/reporting events.
- Cập nhật analytics.
- Đồng bộ search index.
- Tính recommendations.
- Cập nhật read model.
- Chạy workflow dài có trạng thái.

Thay vì Checkout chờ Notification và email provider, có thể ghi business mutation cùng outbox record trong một transaction, sau đó publisher gửi event đến broker và Notification worker xử lý.

~~~mermaid
flowchart LR
  C[Checkout] --> DB[(Order DB + Outbox)]
  DB --> P[Outbox publisher]
  P --> B[Message broker]
  B --> N[Notification worker]
  N --> E[Email provider]
~~~

Request cốt lõi không phải chờ email provider. Nếu broker/worker tạm chậm, outbox/backlog giữ công việc để retry theo policy.

Asynchronous không miễn phí. Cần xử lý duplicate delivery, consumer idempotency, ordering, retry, dead-letter queue, backpressure, schema evolution, workflow state và quan sát end-to-end completion. API phải biểu diễn accepted/pending rõ ràng.

## 16. Saga cho workflow xuyên nhiều service

Nếu checkout cần Order, Inventory và Payment, không nên kéo một request đồng bộ chờ cả chuỗi dài nếu workflow có thể chạy nhiều bước.

~~~mermaid
flowchart TD
  A[Create pending order] --> B[Reserve inventory]
  B --> C[Authorize payment]
  C --> D[Confirm order]
  D --> E[Publish events]
  B -->|reservation rejected| X[Cancel pending order]
  C -->|payment failed| Y[Release inventory]
  Y --> X
~~~

Nếu payment thất bại sau khi reserve hàng, saga gửi compensation release inventory. Đây không phải rollback ACID toàn cục; compensation là một nghiệp vụ mới và cũng có thể thất bại.

Cần state machine bền vững, idempotency, retry policy, timeout từng bước, compensation semantics, manual recovery, correlation ID và cách query workflow status. Saga giúp tách thời gian xử lý dài khỏi HTTP request nhưng không xóa độ phức tạp nghiệp vụ.

## 17. Chọn synchronous hay asynchronous theo use case

| Câu hỏi | Synchronous phù hợp khi | Asynchronous phù hợp khi |
| --- | --- | --- |
| Có cần kết quả ngay? | Có, caller cần quyết định tiếp | Không, xử lý sau được |
| Thời gian xử lý | Ngắn, có giới hạn | Dài hoặc khó dự đoán |
| Coupling | Caller chấp nhận dependency availability | Có thể chấp nhận eventual consistency |
| Failure handling | Trả lỗi/fallback ngay | Retry, backlog, trạng thái pending |
| Side effect | Cần kết quả trước response | Có thể xác nhận tiếp nhận rồi xử lý |
| UX | User chờ kết quả | User theo dõi trạng thái/notification |

Không chuyển mọi lời gọi sang queue chỉ để tránh latency. Nếu Checkout cần xác nhận tồn kho trước khi xác nhận đơn, phải có quyết định đồng bộ hoặc workflow trạng thái rõ ràng.

## 18. Cache, read model và batching giảm dependency trên hot path

Nếu mỗi request phải gọi Catalog, Customer và Pricing để dựng dữ liệu, có thể cân nhắc cache dữ liệu ít thay đổi, read model/projection, snapshot giá/địa chỉ tại thời điểm đặt đơn, batch lookup và request coalescing.

Cache có thể giảm số call và latency cho cache hit, nhưng cache miss thường quyết định tail. Cache key phải gồm tenant, currency, locale, customer segment và quyền truy cập khi các yếu tố đó làm kết quả khác nhau.

Không dùng stale cache để thay thế dữ liệu bắt buộc mới nhất như payment status hoặc giá charge nếu policy không cho phép.

Nếu một request hiển thị 30 sản phẩm và gọi Inventory 30 lần, batch endpoint có thể giảm overhead. Cần giới hạn batch size/body size, timeout, response size, partial error theo item, query plan và fairness giữa tenants. Mục tiêu là giảm total resource cost và cải thiện p99, không chỉ giảm số HTTP requests.

## 19. API Gateway và BFF không nên thành chuỗi orchestration quá sâu

Gateway phù hợp cho routing, authentication, rate limiting và cross-cutting policies. Nếu Gateway gọi nhiều business service, sau đó mỗi service tiếp tục gọi nhiều service khác, Gateway trở thành một call chain khó kiểm soát.

BFF có thể tổng hợp dữ liệu phục vụ một client, nhưng nên giữ orchestration cần thiết, phân biệt required/optional fields, có deadline tổng, giới hạn fan-out/concurrency, không sao chép business invariants của domain owner và cân nhắc read model nếu query tổng hợp quá nặng.

Không đưa toàn bộ domain workflow vào API Gateway chỉ vì nó đứng trước mọi request.

## 20. Timeout budget trong Java/Spring

Một ứng dụng Java có thể đặt timeout ở WebClient hoặc HTTP client. Ví dụ minh họa với Reactor:

~~~java
Mono<InventoryResult> inventory =
    webClient.get()
        .uri("/inventory/{sku}", sku)
        .retrieve()
        .bodyToMono(InventoryResult.class)
        .timeout(Duration.ofMillis(120));
~~~

Timeout 120 ms chỉ là ví dụ. Trong production cần overall deadline từ ingress, connect/response timeout của underlying HTTP client, connection pool acquire timeout, propagation remaining budget, cancellation, error mapping, retry budget và metrics cho queue/acquire/response time.

Reactive timeout không tự bảo đảm mọi công việc blocking bên dưới bị dừng. Không chạy blocking JDBC hoặc synchronous network calls trên event-loop.

### 20.1. Blocking client và thread pool

Với blocking I/O, mỗi call có thể giữ worker trong lúc chờ. Dùng pool có giới hạn và queue bounded. Nếu dùng một pool chung cho mọi dependency, Reviews chậm có thể chiếm worker khiến Payment không còn chỗ chạy.

Có thể dùng bulkhead/pool riêng theo dependency hoặc priority. Đừng tạo executor mới cho mỗi request.

### 20.2. Virtual threads

Java virtual threads giảm chi phí quản lý nhiều tác vụ blocking trong trường hợp phù hợp. Chúng không làm database connection, socket, downstream QPS hoặc rate limits trở nên vô hạn.

Vẫn cần concurrency limits, deadlines, queue bounds và capacity planning.

## 21. Resilience4j và các cơ chế bảo vệ

Resilience4j cung cấp các module như CircuitBreaker, Retry, RateLimiter, Bulkhead và TimeLimiter. Chúng có thể phối hợp, nhưng thứ tự decorator và cách map lỗi ảnh hưởng behavior.

Policy ví dụ cho Inventory client:

- Overall remaining deadline.
- Response timeout bounded.
- Bulkhead giới hạn in-flight.
- Circuit breaker fail-fast khi slow/failure rate cao.
- Retry chỉ cho lỗi transient, tối đa một attempt phụ.
- Fallback trả UNKNOWN/UNAVAILABLE theo contract.

Không có bộ giá trị mặc định đúng cho mọi service. Cần load test và fault injection. Retry quanh circuit breaker hoặc bulkhead có thể tạo hành vi khác nhau tùy thứ tự; đọc tài liệu version đang dùng và kiểm tra trace/metrics.

## 22. Admission control và load shedding

Khi service gần bão hòa, từ chối một phần công việc sớm có thể giữ cho phần còn lại hoạt động.

- Concurrency limit theo route/dependency.
- Queue nhỏ, bounded.
- Rate limit theo tenant/client.
- Từ chối request vượt capacity bằng 429/503 phù hợp.
- Bỏ nhánh optional như recommendations.
- Ưu tiên checkout/payment hơn báo cáo nền.
- Tạm dừng batch jobs nặng khi hệ thống nóng.
- Hạ tải theo feature flag đã chuẩn bị.

Không load-shed kiểm tra authorization hoặc bỏ qua invariant tài chính. Overload response rõ ràng tốt hơn trả kết quả sai.

## 23. Fallback phải có semantics nghiệp vụ

Fallback có thể là cache hợp lệ còn trong freshness window, partial response, read-only mode, pending workflow, provider dự phòng đã kiểm chứng hoặc từ chối có kiểm soát.

Fallback không nên:

- Trả giá bằng 0 khi Pricing timeout.
- Giả định inventory còn hàng khi service không phản hồi.
- Trả payment success khi không biết kết quả.
- Bỏ qua tenant authorization.
- Trả dữ liệu stale mà không công bố nếu user cần freshness.

Một fallback tốt có owner, điều kiện kích hoạt, thời hạn, metric và cách phục hồi.

## 24. Hedged requests và replica

Hedging gửi một request dự phòng khi attempt đầu có dấu hiệu straggler, thường đến replica khác, rồi chọn kết quả hợp lệ đến trước.

Có thể giảm tail khi replicas độc lập và operation read-only/idempotent. Nhưng nó làm tăng extra load và có thể khiến backend đang quá tải càng tệ.

Chỉ dùng khi operation an toàn để thực hiện nhiều lần, có giới hạn tỷ lệ hedge, replica thuộc failure domain phù hợp, consistency đáp ứng contract, deadline còn đủ, có metric winner/loser/extra load và có cách tắt nhanh khi saturation.

Không hedge payment charge hoặc side effect không có idempotency/deduplication.

## 25. Phân biệt các pattern bảo vệ

| Pattern | Câu hỏi được giải quyết | Tác dụng |
| --- | --- | --- |
| Timeout/deadline | Chờ tối đa bao lâu? | Giới hạn thời gian giữ request |
| Circuit breaker | Có nên tiếp tục gọi dependency đang lỗi? | Fail-fast khi suy giảm |
| Bulkhead | Một dependency được dùng bao nhiêu tài nguyên? | Cô lập saturation |
| Retry | Có nên thử lại lỗi transient? | Tăng cơ hội thành công có kiểm soát |
| Rate limiter | Tốc độ nhận request tối đa? | Bảo vệ capacity |
| Load shedding | Khi quá tải thì bỏ công việc nào? | Giữ năng lực cho request ưu tiên |
| Cache/read model | Có cần gọi dependency cho mọi read? | Giảm call volume |
| Async messaging | Có cần chờ kết quả trong request? | Tách thời gian xử lý |
| Fallback | Có thể cung cấp phần nào khi dependency lỗi? | Duy trì chức năng đúng |

Một kiến trúc bền thường phối hợp nhiều cơ chế thay vì tìm một annotation giải quyết mọi lỗi.

## 26. Observability: biết dependency nào làm giảm availability

Cần đo tại cả caller và callee:

- Request rate, error rate, latency histogram.
- p50/p95/p99 theo route.
- Outbound latency theo dependency.
- Connection acquisition và queue wait.
- In-flight requests và rejection.
- Timeout/cancellation.
- Retry attempts và extra QPS.
- Circuit breaker state/transitions.
- Bulkhead permits/queue depth.
- Cache hit/miss/stale served.
- Partial response/fallback rate.
- Consumer backlog và workflow completion time.

Distributed tracing cần propagate trace context qua HTTP/gRPC/message. Trace cho biết call graph, span duration và critical path.

Không chỉ xem average latency. Không cộng duration của các span song song để tính wall-clock time. Không lấy trung bình p99 giữa replicas; dùng histogram/observations có thể tổng hợp đúng.

## 27. SLO cho API tổng hợp

Ví dụ SLO:

> 99% request Checkout API phải trả kết quả hợp lệ trong 500 ms trong cửa sổ 28 ngày.

Cần định nghĩa latency đo từ ingress hay client, HTTP 4xx nào được loại, timeout tính là lỗi hay chỉ latency, partial response có được coi là good event không, payment pending có hợp lệ cho use case nào, region/tenant/client nào nằm trong phạm vi và error budget/burn-rate alert ra sao.

Một endpoint trả 200 nhanh nhưng không giữ được inventory hoặc không biết payment status không phải success nếu nghiệp vụ yêu cầu các kết quả đó.

SLO của dependency không thể cộng hoặc nhân máy móc để chứng minh SLO parent. Phải dùng call graph, critical path, traffic, failure correlation và dữ liệu thực tế.

## 28. Kiểm thử lỗi và saturation

Một test bình thường không cho biết hệ thống hoạt động thế nào khi dependency chậm. Hãy kiểm thử:

1. Inventory thêm 500 ms ở một tỷ lệ request.
2. Payment trả timeout sau khi có thể đã commit.
3. Reviews trả 503 liên tục.
4. Connection pool bị cạn.
5. Database lock wait tăng.
6. DNS/network jitter.
7. Broker backlog tăng.
8. Một dependency trả response rất lớn.
9. Client cancel giữa workflow.
10. Retry cùng lúc ở Gateway và service.
11. Cache miss spike.
12. Một region mất kết nối tới region khác.
13. Một tenant gửi burst traffic.
14. Thread/event-loop bị block.

Đo p95/p99, throughput, errors, queue, in-flight, downstream QPS và business correctness. Xác nhận hệ thống phục hồi sau khi fault dừng.

Không chỉ kiểm tra circuit breaker đã chuyển OPEN; cần xác minh resource caller được giải phóng và dependency không bị tiếp tục overload.

## 29. Ví dụ thiết kế lại Checkout

### Trước

~~~text
POST /checkout
  -> Customer lookup
  -> Cart lookup
  -> Pricing
  -> Promotion
  -> Inventory reserve
  -> Fraud check
  -> Payment authorize
  -> Shipping quote
  -> Notification
  -> Return response
~~~

Mọi bước đều chờ đồng bộ. Notification provider chậm cũng có thể làm người dùng chờ dù đơn đã được tạo.

### Sau

~~~text
POST /checkout
  -> Validate identity/cart
  -> Price and required policy checks
  -> Reserve inventory
  -> Start durable checkout workflow
  -> Return PENDING/accepted state

Workflow:
  -> Fraud assessment
  -> Payment authorization
  -> Confirm order
  -> Publish events
  -> Shipping/notification asynchronously
~~~

Đây là hướng minh họa; thứ tự thực tế phụ thuộc nghiệp vụ. Một số bước phải hoàn tất trước khi xác nhận đơn. Workflow phải lưu trạng thái và hỗ trợ idempotency/compensation.

Các cải tiến gồm deadline tổng cho phần synchronous, required dependencies có giới hạn, notification rời critical path, optional UI data dùng cache/partial response, payment/inventory có idempotency và saga quản lý bước dài.

## 30. Những sai lầm thường gặp

1. Một request đi qua quá nhiều service đồng bộ.
2. Tất cả dependency đều bị coi là bắt buộc.
3. Không vẽ call graph và critical path.
4. Chỉ đặt timeout ở Gateway, không ở outbound client.
5. Mỗi tầng tự reset timeout đầy đủ.
6. Không propagate deadline.
7. Retry mọi lỗi và mọi HTTP status.
8. Retry ở nhiều tầng làm nhân số attempt.
9. Retry POST/payment không có idempotency.
10. Dùng queue vô hạn để giữ mọi request.
11. Dùng chung thread pool cho dependency quan trọng và optional.
12. Không giới hạn in-flight calls.
13. Chỉ dùng circuit breaker mà không có timeout.
14. Fallback trả dữ liệu giả để giữ HTTP 200.
15. Gửi email/notification trong critical path.
16. Dùng synchronous chain cho workflow kéo dài nhiều phút.
17. Chuyển mọi thứ sang event mà không có trạng thái/ordering/dedup.
18. Không xử lý compensation failure của saga.
19. Cache stale cho dữ liệu giao dịch bắt buộc mới.
20. Fan-out N+1 tới từng item.
21. Không quan sát queue wait/connection acquisition.
22. Chỉ theo dõi average, bỏ qua p95/p99.
23. Lấy trung bình percentile giữa các pod.
24. Không test dependency chậm hoặc network partition.
25. Không kiểm tra công việc tiếp tục sau parent timeout.
26. Cho optional dependency dùng hết pool của required path.
27. Không tính retry/hedge vào downstream capacity.
28. Coi Pod Ready là dependency sẵn sàng cho mọi workflow.
29. Không phân biệt pending với success.
30. Không gắn owner cho fallback và runbook.

## 31. Checklist thiết kế call chain

### Kiến trúc và dependency

- [ ] Đã vẽ call graph theo use case.
- [ ] Đã xác định critical path.
- [ ] Phân loại required và optional dependencies.
- [ ] Giới hạn fan-out và độ sâu call chain.
- [ ] Không có service nào truy cập storage nội bộ của service khác.
- [ ] Có cân nhắc cache, batch và read model.
- [ ] Workflow dài có trạng thái bền vững.

### Resilience và capacity

- [ ] Có overall deadline và propagation.
- [ ] Outbound calls có timeout.
- [ ] Cancellation được truyền khi có thể.
- [ ] Retry bounded, jittered và có budget.
- [ ] Side effects có idempotency.
- [ ] Bulkhead và queue bounded.
- [ ] Circuit breaker có threshold đã kiểm thử.
- [ ] Rate limit/admission control/load shedding.
- [ ] Fallback đúng semantics nghiệp vụ.
- [ ] Optional dependency không chiếm resource của required path.

### Observability và vận hành

- [ ] Có p50/p95/p99 và histogram theo route.
- [ ] Có outbound latency theo dependency.
- [ ] Có queue wait, connection pool và in-flight metrics.
- [ ] Có retry, breaker, fallback và cancellation metrics.
- [ ] Distributed tracing có context propagation.
- [ ] Có SLO/error budget và burn-rate alert.
- [ ] Đã test straggler, overload, partition và recovery.
- [ ] Có runbook cho dependency degraded.

## 32. Câu hỏi tự kiểm tra

**1. Vì sao chuỗi năm dependency bắt buộc có thể kém availability hơn từng dependency?**  
Nếu độc lập và tất cả phải thành công, xác suất request thành công gần bằng tích availability từng dependency.

**2. Parallel fan-out có loại bỏ dependency failure không?**  
Không. Nó giảm thời gian chờ so với tuần tự nhưng nếu tất cả nhánh required, một nhánh lỗi vẫn có thể làm request thất bại.

**3. Vì sao call chain sâu dễ gây cascading failure?**  
Lỗi/chậm giữ tài nguyên caller, làm queue tăng, timeout và retry tạo thêm tải xuống các tầng.

**4. Timeout từng dependency bằng overall timeout có đủ không?**  
Không. Cần remaining deadline vì các bước tuần tự và overhead có thể làm tổng request vượt budget.

**5. Circuit breaker và timeout khác nhau thế nào?**  
Timeout giới hạn thời gian một call; circuit breaker ngăn tiếp tục gọi dependency đang suy giảm trong một khoảng.

**6. Bulkhead giải quyết vấn đề gì?**  
Giới hạn tài nguyên mỗi dependency để một nhánh chậm không chiếm hết năng lực caller.

**7. Vì sao retry có thể làm sự cố nặng hơn?**  
Mỗi logical request tạo thêm attempts đúng lúc downstream đã quá tải.

**8. Khi nào fallback là sai?**  
Khi nó làm giả trạng thái nghiệp vụ, như trả payment success hoặc giá 0 khi chưa xác minh.

**9. Notification có nên nằm trong checkout critical path?**  
Thường không; có thể phát event/outbox sau commit và xử lý bất đồng bộ.

**10. Asynchronous có nghĩa không còn lỗi duplicate?**  
Không. Message có thể replay; consumer cần idempotency và xử lý ordering.

**11. Saga có rollback như transaction database không?**  
Không. Saga dùng local transactions và compensation; compensation cũng có thể thất bại.

**12. Vì sao virtual threads không thay bulkhead?**  
Database, socket, downstream QPS và connection pools vẫn hữu hạn.

**13. p99 của parent có bằng tổng p99 của child không?**  
Không. Percentile của tổng/max phụ thuộc phân phối, overlap, correlation và call graph.

**14. Metric nào giúp phân biệt service chậm với queue chờ?**  
Outbound span, server processing time, queue wait, connection acquisition, pool saturation và trace.

**15. Khi nào nên chuyển sang asynchronous workflow?**  
Khi caller không cần kết quả ngay, tác vụ dài hoặc side effect có thể xử lý sau với trạng thái/consistency rõ.

## 33. Tài liệu tham khảo

- Google SRE Book — Addressing Cascading Failures: https://sre.google/sre-book/addressing-cascading-failures/
- Google SRE Book — Handling Overload: https://sre.google/sre-book/handling-overload/
- Google SRE Book — Service Level Objectives: https://sre.google/sre-book/service-level-objectives/
- Google Research — The Tail at Scale: https://research.google/pubs/the-tail-at-scale/
- Martin Fowler — Circuit Breaker: https://martinfowler.com/bliki/CircuitBreaker.html
- Microsoft — Circuit Breaker pattern: https://learn.microsoft.com/en-us/azure/architecture/patterns/circuit-breaker
- Microsoft — Bulkhead pattern: https://learn.microsoft.com/en-us/azure/architecture/patterns/bulkhead
- Microsoft — Retry pattern: https://learn.microsoft.com/en-us/azure/architecture/patterns/retry
- Microsoft — Queue-Based Load Leveling: https://learn.microsoft.com/en-us/azure/architecture/patterns/queue-based-load-leveling
- Microsoft — Saga distributed transactions: https://learn.microsoft.com/en-us/azure/architecture/patterns/saga
- Resilience4j Documentation: https://resilience4j.readme.io/docs
- Spring WebClient Reference: https://docs.spring.io/spring-framework/reference/web/webflux-webclient.html
- Project Reactor Reference Guide: https://projectreactor.io/docs/core/release/reference/
- OpenTelemetry — Traces: https://opentelemetry.io/docs/concepts/signals/traces/
- Prometheus — Histograms and Summaries: https://prometheus.io/docs/practices/histograms/

**Ghi nhớ:** Chuỗi gọi đồng bộ dài làm request phụ thuộc vào nhiều failure domains và giữ tài nguyên lâu hơn. Thiết kế tốt bắt đầu từ **giảm dependency bắt buộc**, đặt **deadline xuyên tầng**, giới hạn **concurrency/queue**, dùng **retry và circuit breaker có điều kiện**, đưa tác vụ không cần kết quả ngay sang **asynchronous workflow**, và đo critical path bằng tracing cùng SLO. Mọi fallback phải giữ đúng trạng thái nghiệp vụ.
