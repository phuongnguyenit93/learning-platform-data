# Diễn tập quá tải, lỗi phụ thuộc và phục hồi có kiểm soát

**Nhóm kiến thức:** Bài tập và tình huống trong Software Design, System Architecture và Microservices.

Một hệ thống phân tán không chỉ cần hoạt động khi mọi thành phần đều khỏe. Nó phải tiếp tục bảo vệ dữ liệu và trải nghiệm người dùng khi traffic tăng đột biến, database chậm, broker đầy backlog, dịch vụ đối tác timeout, một vùng mạng bị lỗi hoặc một nhóm worker bị cạn tài nguyên. **Diễn tập quá tải và lỗi phụ thuộc** giúp đội ngũ kiểm chứng những giả định này trong điều kiện có kiểm soát; **phục hồi có kiểm soát** bảo đảm hệ thống trở lại trạng thái bình thường theo từng bước, không tạo thêm một đợt quá tải khi dependency vừa hồi phục.

Một sự cố phân tán thường không dừng ở thành phần đầu tiên bị lỗi. API chờ database lâu hơn, thread pool bị chiếm, request mới xếp hàng, client retry, broker tích tụ message, các consumer khởi động lại đồng loạt và dịch vụ phụ tiếp tục bị tấn công bởi chính lưu lượng nội bộ. Khi mọi thành phần cùng cố gắng xử lý tất cả request, hệ thống có thể sụp đổ theo dây chuyền dù từng service riêng lẻ không có bug.

Bài học này xây dựng cách lập kịch bản failure drill, đặt giới hạn tải, phát hiện saturation, dùng timeout, retry có ngân sách, circuit breaker, bulkhead, rate limiting, admission control, load shedding, backpressure và graceful degradation. Phần phục hồi tập trung vào cô lập blast radius, xác minh dependency, khôi phục theo thứ tự, mở traffic từng bước, bảo vệ dữ liệu, xử lý backlog và xác nhận SLO sau sự cố. Các ví dụ dùng microservices, Java/Spring Boot và các dependency phổ biến như database, broker, cache và API đối tác.

## 1. Mục tiêu của một failure drill

Một failure drill không phải cuộc thi làm hệ thống sập. Nó là một thử nghiệm có giả thuyết, phạm vi, giới hạn tác động, tín hiệu dừng và tiêu chí thành công.

Ví dụ giả thuyết:
- Khi database tăng latency, API Checkout sẽ từ chối request vượt quá timeout budget thay vì giữ thread vô hạn.
- Khi Payment provider không phản hồi, Checkout vẫn trả trạng thái đang xử lý và không capture tiền trùng.
- Khi consumer chậm, queue backlog tăng có cảnh báo nhưng không làm cạn connection pool của Orders DB.
- Khi cache mất, hệ thống giảm tải có kiểm soát và không tạo cache stampede.
- Khi broker hoạt động lại, consumer tăng concurrency theo từng bước thay vì tạo một đợt tải dồn vào database.

Một drill tốt trả lời bốn câu hỏi:
1. Hệ thống phát hiện vấn đề sớm đến đâu?
2. Cơ chế bảo vệ có giới hạn được blast radius không?
3. Người vận hành có thể quyết định và thực hiện phục hồi theo runbook không?
4. Sau phục hồi, dữ liệu và business workflow có hội tụ đúng không?

Kết quả không chỉ là biểu đồ latency. Cần lưu giả thuyết, cấu hình, thời điểm, traffic profile, metric, tác động, quyết định, sai lệch và hành động cải thiện.

## 2. Phân biệt tải cao, saturation và overload

**Tải cao** có thể vẫn nằm trong năng lực dự kiến. **Saturation** xuất hiện khi một tài nguyên tiến gần giới hạn hữu dụng: CPU, memory, thread, connection, IOPS, network, broker partition hoặc quota. **Overload** xảy ra khi nhu cầu vượt quá năng lực phục vụ trong thời gian đủ dài khiến latency, error hoặc backlog tăng không kiểm soát.

| Trạng thái | Dấu hiệu | Hành động |
|---|---|---|
| Normal | SLI ổn định, còn headroom | Phục vụ theo policy |
| Busy | Utilization tăng nhưng latency/error vẫn trong budget | Theo dõi và scale theo kế hoạch |
| Saturating | Queue wait, pool wait hoặc throttling tăng | Giới hạn concurrency, scale bottleneck |
| Overloaded | SLO xấu, backlog tăng nhanh, timeout/retry lan rộng | Admission control, shed load, cô lập |
| Recovering | Dependency vừa khỏe lại, backlog còn lớn | Khôi phục theo từng đợt |
| Stable | SLI và dữ liệu ổn định qua cửa sổ xác minh | Trở lại policy bình thường |

CPU 90% không tự động có nghĩa hệ thống hỏng; một service CPU-bound có thể vận hành tốt ở mức đó nếu latency và throughput đạt SLO. Ngược lại CPU 25% vẫn có thể quá tải nếu DB pool cạn, thread chờ socket hoặc dependency có quota thấp.

Đo **độ trễ chờ tài nguyên và khả năng hoàn tất nghiệp vụ**, không chỉ nhìn utilization trung bình.

## 3. Xây dựng dependency graph trước khi diễn tập

Mỗi critical journey cần một đồ thị dependency:

~~~mermaid
flowchart TD
    U["Client"] --> G["API Gateway"]
    G --> O["Order Service"]
    O --> D[("Orders DB")]
    O --> I["Inventory"]
    O --> P["Payment Provider"]
    O --> B[("Event Broker")]
    B --> N["Notification"]
    B --> A["Analytics"]
    I --> ID[("Inventory DB")]
    N --> M["Mail Provider"]
~~~

Đối với từng cạnh, ghi:
- Giao thức và kiểu giao tiếp: sync hay async.
- Timeout và retry policy.
- Pool/concurrency giới hạn.
- SLO của dependency.
- Có thể cache hoặc degrade không?
- Có side effect hay không?
- Có fallback hoặc alternate provider không?
- Owner và runbook.
- Cách phát hiện dependency chậm/hỏng.

Một service có thể có nhiều dependency dùng chung. Ví dụ Orders, Inventory và Payment đều truy cập một PostgreSQL cluster. Khi DB chậm, scale từng API có thể làm số connection tăng và khiến DB quá tải hơn. Đồ thị phải thể hiện cả shared dependency, network, identity, DNS và hệ thống nền.

## 4. Chọn failure mode có ý nghĩa

Không nên chỉ diễn tập một tình huống “tắt service”. Lỗi thực tế có nhiều dạng:

| Failure mode | Mô phỏng | Câu hỏi cần trả lời |
|---|---|---|
| Latency tăng | Delay response theo phân phối | Timeout có chặn chờ vô hạn? |
| Partial error | Một tỷ lệ request trả 5xx | Retry có khuếch đại tải? |
| Connection reset | Đóng socket ngẫu nhiên | Client phân loại lỗi ra sao? |
| Dependency unavailable | Từ chối kết nối | Circuit breaker có mở? |
| Quota/rate limit | Trả 429 hoặc throttling | Backoff có tôn trọng Retry-After? |
| Slow database | Tăng query latency/lock | Pool và thread có bị cạn? |
| Broker lag | Làm chậm consumer | Backpressure và alert có hoạt động? |
| Cache unavailable | Timeout/connection refused | Fallback có gây DB stampede? |
| DNS failure | Trả lỗi phân giải trong sandbox | Retry có hợp lý? |
| Node/zone loss | Loại một failure domain thử nghiệm | Capacity còn lại có đủ? |
| Memory pressure | Giảm memory limit hoặc tạo tải có kiểm soát | OOM/restart có tạo vòng lặp? |
| Clock/credential issue | Mô phỏng token hết hạn ở môi trường thử | Có phát hiện và phục hồi đúng? |

Chọn lỗi theo dependency graph và incident history. Một drill không cần mô phỏng mọi lỗi cùng lúc; thay đổi quá nhiều biến khiến khó xác định nguyên nhân và tăng blast radius.

## 5. Định nghĩa SLI và điều kiện thành công

Trước khi chạy, xác định:
- **Availability:** tỷ lệ request/transaction thành công theo định nghĩa nghiệp vụ.
- **Latency:** p50, p95, p99 và timeout.
- **Throughput:** request/second, completed transaction/second.
- **Correctness:** duplicate, missing, invalid state và reconciliation mismatch.
- **Freshness:** tuổi của event, queue lag, thời gian hoàn tất workflow.
- **Capacity:** CPU/RAM, pool utilization, queue wait và headroom.
- **Recovery:** thời gian phát hiện, cô lập, phục hồi và hội tụ dữ liệu.

Ví dụ tiêu chí minh họa cho một API:
- p95 dưới 300 ms trong tải mục tiêu.
- p99 dưới 800 ms.
- Success rate tối thiểu 99,9% theo cửa sổ đo đã chọn.
- Không có duplicate payment.
- Queue age dưới 60 giây sau khi dependency phục hồi.
- Không vượt connection limit của DB.

Đây chỉ là ví dụ; ngưỡng thật phải lấy từ SLO và business impact. Một API đọc danh mục và một bước capture payment không nên dùng cùng chính sách chấp nhận lỗi.

Cần xác định mẫu tối thiểu và cửa sổ quan sát. Một phút xanh với 20 request không chứng minh hệ thống ổn định khi peak traffic có hàng nghìn request mỗi phút.

## 6. Baseline trước khi inject failure

Chạy một lượt tải bình thường trước khi cố tình gây lỗi. Ghi:
- Request rate và concurrency.
- p50/p95/p99 latency.
- Success rate, 4xx, 5xx, timeout.
- CPU, heap, RSS, GC và thread count.
- DB pool active/idle/pending, query latency và lock wait.
- Broker publish/consume rate, lag và DLQ.
- Cache hit ratio, eviction và connection.
- Network throughput, retransmit và DNS latency.
- Autoscaler events, replica count và node capacity.
- Business outcomes như order completion hoặc payment authorization.

Baseline cần bao phủ warm-up và tải ổn định. Nếu không có baseline, khó phân biệt lỗi do inject với biến động tự nhiên của workload.

Ghi cả phiên bản ứng dụng, config, dataset, topology và dependency version. Kết quả chỉ so sánh được khi biết điều kiện chạy.

## 7. Capacity planning và saturation point

Một hệ thống có throughput giới hạn bởi bottleneck trên critical path. Ví dụ:
- API có thể xử lý 2.000 request/giây.
- Database chỉ chịu 400 transaction/giây.
- Một provider giới hạn 100 request/giây.
- Consumer xử lý 500 event/giây.

Nếu API phát 1.000 request/giây và mỗi request gọi provider một lần, giới hạn provider trở thành bottleneck dù API còn CPU. Tăng replica API không tăng năng lực provider.

Ước lượng đơn giản:

\[
\text{Required concurrency} \approx \text{Arrival rate} \times \text{Average service time}
\]

Ví dụ 200 request/giây, thời gian xử lý trung bình 0,25 giây:

\[
200 \times 0.25 = 50
\]

Khoảng 50 request đồng thời đang được xử lý theo giả định ổn định. Đây là ước lượng theo Little's Law, không phải giới hạn thread tối ưu. Cần đo phân phối latency, burst, queueing và tài nguyên thực tế.

Khi utilization tiến sát 100%, thời gian chờ có thể tăng rất nhanh. Giữ headroom phù hợp với peak, autoscaling delay và failure scenario.

## 8. Overload thường bắt đầu từ queue chờ

Khi arrival rate lớn hơn service rate:
- Request xếp hàng.
- Thời gian chờ tăng.
- Thread/connection bị giữ lâu.
- Client timeout.
- Client retry.
- Số request thực tế tăng.
- Queue càng dài và hệ thống càng khó phục hồi.

~~~text
Incoming rate > Processing rate
          |
          v
      Queue grows
          |
          v
   Wait time increases
          |
          v
   Client timeout/retry
          |
          v
  Effective load increases
          |
          +------> More saturation
~~~

Queue không tạo thêm capacity; nó chỉ trì hoãn việc xử lý. Với request tương tác, queue quá dài thường chỉ giữ công việc đã hết deadline. Cần giới hạn queue length/age và từ chối sớm khi không còn khả năng hoàn thành hữu ích.

Đối với message queue, backlog có thể chấp nhận nếu event còn giá trị và retention đủ dài. Nhưng cần freshness SLO và capacity phục hồi để backlog không tăng mãi.

## 9. Timeout: giới hạn thời gian chờ ở mọi ranh giới

Một lời gọi mạng không được chờ vô hạn. Cần timeout cho:
- DNS/connect.
- TLS handshake.
- Connection pool acquisition.
- Request/response.
- Database query/transaction.
- Broker publish/consume.
- Lock wait.
- Workflow deadline.

Timeout của downstream phải nhỏ hơn timeout còn lại của request upstream. Nếu API gateway timeout sau 2 giây nhưng service chờ Payment 10 giây, thread vẫn bị giữ thêm 8 giây sau khi client đã bỏ cuộc.

Ví dụ budget:
~~~text
Client deadline:              2.0 s
Gateway budget:               1.8 s
Order service processing:     1.5 s
  Inventory call:             0.4 s
  Payment authorize:          0.7 s
  Local DB and response:      0.4 s
~~~

Các con số chỉ minh họa. Không cộng p99 độc lập một cách máy móc; latency phân phối và concurrency cần được đo. Propagate deadline/cancellation khi giao thức hỗ trợ.

Timeout không đồng nghĩa request chắc chắn thất bại ở phía server. Provider có thể đã xử lý nhưng response bị mất. Với side effect, timeout phải chuyển sang trạng thái UNKNOWN/RECONCILIATION nếu chưa biết kết quả.

## 10. Retry có thể cứu lỗi tạm thời hoặc khuếch đại overload

Retry phù hợp khi:
- Lỗi có khả năng tạm thời.
- Thao tác idempotent hoặc có idempotency key.
- Còn deadline.
- Dependency có khả năng phục hồi.
- Retry budget chưa cạn.

Retry nguy hiểm khi:
- Lỗi permanent như validation/schema/auth.
- Client đã retry nhưng service cũng retry.
- Mọi request retry cùng thời điểm.
- Timeout xảy ra sau khi side effect đã thành công.
- Dependency đang quá tải và retry làm tăng arrival rate.

Một policy nên có:
1. Phân loại retryable/non-retryable.
2. Giới hạn số lần thử.
3. Exponential backoff.
4. Jitter ngẫu nhiên để tránh đồng bộ.
5. Tôn trọng Retry-After nếu có.
6. Dùng deadline tổng.
7. Idempotency cho side effect.
8. Metric về attempt và retry exhaustion.

Ví dụ backoff minh họa:
~~~text
Attempt 1: ngay lập tức
Attempt 2: 200 ms + jitter
Attempt 3: 400 ms + jitter
Attempt 4: 800 ms + jitter
Sau đó: dừng hoặc chuyển workflow sang trạng thái cần xử lý
~~~

Không retry vô hạn. Retry phải được xem là một phần của tải, không phải hành động miễn phí.

## 11. Retry budget và tránh retry ở nhiều tầng

Giả sử client retry 3 lần, gateway retry 2 lần, service retry 3 lần và SDK provider retry 2 lần. Số attempt có thể nhân lên rất lớn trong một request gốc.

Nên quy định rõ:
- Tầng nào sở hữu retry.
- Dependency nào được retry.
- Tối đa bao nhiêu attempt trên toàn deadline.
- Có retry khi lỗi kết nối trước khi gửi payload hay sau khi gửi không.
- Tác vụ nào chuyển sang async workflow thay vì retry trong request.

Với thao tác thanh toán, retry phải dùng cùng idempotency key và provider reference phù hợp. Nếu kết quả lần trước không rõ, query trạng thái trước khi gửi thao tác mới.

## 12. Circuit breaker: ngừng gọi dependency đang lỗi

Circuit breaker bảo vệ caller khi dependency liên tục lỗi hoặc chậm.

Các trạng thái:
- **CLOSED:** cho phép request đi qua và theo dõi lỗi.
- **OPEN:** từ chối nhanh hoặc dùng fallback, không tiếp tục tạo tải lên dependency.
- **HALF_OPEN:** cho một số probe giới hạn để kiểm tra phục hồi.

~~~mermaid
stateDiagram-v2
    [*] --> CLOSED
    CLOSED --> OPEN: Failure threshold reached
    OPEN --> HALF_OPEN: Wait duration elapsed
    HALF_OPEN --> CLOSED: Probe success
    HALF_OPEN --> OPEN: Probe failure
~~~

Cần cấu hình:
- Failure rate hoặc slow-call rate threshold.
- Sliding window và minimum calls.
- Open duration.
- Số probe ở half-open.
- Exception/status nào được tính là failure.
- Fallback có thực sự an toàn không.

Không tính lỗi validation 4xx như dependency failure nếu policy không yêu cầu. Không đặt threshold quá nhạy khiến breaker mở vì một vài lỗi tự nhiên. Cũng không đặt quá cao đến khi thread pool đã cạn mới mở.

Circuit breaker là cơ chế ngăn lời gọi, không tự sửa dữ liệu hay phục hồi nghiệp vụ.

## 13. Bulkhead: cô lập tài nguyên giữa dependency

Bulkhead giới hạn concurrency hoặc pool cho từng nhóm công việc để lỗi một dependency không chiếm toàn bộ tài nguyên của service.

Ví dụ:
- Payment calls có tối đa 30 concurrent requests.
- Inventory calls có pool riêng tối đa 40.
- Analytics/background jobs có pool thấp ưu tiên.
- Request phục vụ health/status không bị xếp sau batch job.

Nếu Payment chậm, tối đa 30 slot bị giữ; các slot còn lại của service vẫn phục vụ capability khác.

Các lựa chọn:
- Thread pool riêng.
- Semaphore concurrency limit.
- Connection pool riêng.
- Queue riêng và worker riêng.
- Process/container riêng cho workload có rủi ro cao.
- CPU/memory quota theo workload.

Bulkhead phải được đặt theo resource thực sự dùng chung. Tách thread pool nhưng vẫn dùng chung một DB pool không giải quyết được DB saturation.

## 14. Rate limiting và quota

Rate limiting kiểm soát tốc độ request theo client, tenant, API key, route hoặc dependency.

Các thuật toán thường gặp:
- Fixed window.
- Sliding window.
- Token bucket.
- Leaky bucket.

**Token bucket** cho phép burst trong giới hạn token tích lũy, đồng thời giới hạn tốc độ dài hạn. Đây là lựa chọn phổ biến cho API có traffic burst.

Cần phân biệt:
- Global limit để bảo vệ toàn hệ thống.
- Per-tenant limit để một khách hàng không chiếm hết capacity.
- Per-user/API key để hạn chế lạm dụng.
- Per-dependency limit để tuân thủ quota đối tác.
- Concurrency limit để giới hạn số request đang xử lý.

Khi từ chối, trả status phù hợp, có thể kèm Retry-After. Không để mọi tenant dùng chung một quota nếu một tenant lớn có thể làm người khác bị starvation.

Rate limit không thay thế authorization hoặc fraud control. Một request hợp lệ vẫn có thể vượt capacity.

## 15. Admission control và load shedding

**Admission control** quyết định request nào được phép vào hệ thống dựa trên capacity hiện tại, priority và deadline.

**Load shedding** chủ động từ chối hoặc bỏ bớt công việc ít quan trọng khi quá tải để bảo vệ phần cốt lõi.

Ví dụ:
- Từ chối request mới nếu queue wait dự kiến vượt deadline.
- Giảm tần suất refresh dashboard.
- Tạm ngưng export/report nặng.
- Từ chối request vượt quota.
- Bỏ telemetry/debug sampling không thiết yếu.
- Ưu tiên thanh toán và tra cứu trạng thái so với recommendation.

Phân loại workload:
1. Critical: payment state, order commit, inventory correctness.
2. Important: order status, customer support workflow.
3. Deferrable: email, analytics, report, recommendation refresh.
4. Best effort: debug telemetry hoặc tác vụ không ảnh hưởng business state.

Không shed tùy tiện giao dịch đã được chấp nhận hoặc message cần bảo toàn. Nếu từ chối, phải trả trạng thái rõ để client biết có thể retry hay cần tra cứu idempotency key.

## 16. Graceful degradation: giữ capability quan trọng

Graceful degradation cho phép hệ thống giảm một phần chức năng nhưng vẫn phục vụ hành trình chính.

Ví dụ:
- Recommendation lỗi: hiển thị danh sách mặc định.
- Analytics chậm: chấp nhận dashboard stale với timestamp.
- Notification lỗi: giữ event để gửi sau, không hủy order.
- Search lỗi: dùng category browse hoặc cache nếu phù hợp.
- Loyalty provider lỗi: ghi nhận trạng thái pending hoặc tạm ẩn điểm thưởng theo business policy.
- Payment provider lỗi: không báo thanh toán thành công; chuyển sang pending/unknown và reconciliation.

Một fallback phải đúng về nghiệp vụ. Không dùng dữ liệu cache cũ để quyết định số dư hoặc quyền thanh toán nếu freshness không được chấp nhận.

Cần xác định:
- Capability nào có thể degrade?
- Fallback data có freshness tối đa bao lâu?
- User thấy thông báo gì?
- Khi nào fallback hết hạn?
- Cách quay lại trạng thái đầy đủ?
- Metric nào cho biết degradation đang diễn ra?

## 17. Cache fallback và cache stampede

Cache có thể giảm tải dependency, nhưng khi cache mất hoặc hết hạn đồng loạt, mọi request có thể dồn về database.

Các kỹ thuật:
- TTL có jitter để tránh hết hạn cùng lúc.
- Request coalescing/single-flight cho cùng cache key.
- Stale-while-revalidate khi business chấp nhận dữ liệu cũ.
- Negative caching có thời hạn.
- Giới hạn concurrency vào DB.
- Pre-warm cache theo kế hoạch.
- Circuit breaker cho cache/DB.
- Fallback an toàn khi cache unavailable.

Không cache kết quả nhạy cảm giữa tenant nếu cache key thiếu tenant/user scope. Không dùng stale cache cho dữ liệu mà business yêu cầu consistency mạnh.

## 18. Thread pool, connection pool và queue saturation

Trong Java service, overload có thể xuất hiện ở:
- Tomcat/Jetty request threads.
- Executor cho async task.
- HTTP client connection pool.
- JDBC connection pool.
- Kafka consumer concurrency.
- Scheduler threads.
- Common ForkJoinPool nếu bị dùng không kiểm soát.

Theo dõi:
- Active threads, queued tasks, rejected tasks.
- Connection acquire wait và timeout.
- Pool active/idle/max.
- Thread blocked/waiting.
- Request queue depth.
- GC pause và allocation.
- CPU throttling.

Một pool không giới hạn có thể biến overload thành memory exhaustion. Một pool quá nhỏ gây queueing và latency. Chọn bounded queue, rejection policy và timeout phù hợp.

Không tăng max thread/connection một cách mù quáng. Nếu DB chỉ chịu 100 concurrent query, nâng pool từ 100 lên 500 chỉ chuyển hàng đợi từ ứng dụng sang DB.

## 19. Database overload và lock contention

Dấu hiệu:
- Connection pool pending tăng.
- Query p95/p99 tăng.
- Lock wait/deadlock tăng.
- CPU/IOPS/database storage saturation.
- Replication lag tăng.
- Transaction dài và idle-in-transaction.
- Slow query count tăng.

Cách bảo vệ:
- Query timeout và transaction timeout.
- Index và query plan phù hợp.
- Giới hạn connection theo service.
- Pooler/proxy khi phù hợp.
- Read replica cho workload đọc chấp nhận lag.
- Batch write có kích thước giới hạn.
- Backpressure consumer.
- Tách report nặng khỏi OLTP.
- Giới hạn transaction scope.
- Không retry mọi lỗi DB.

Khi DB đang quá tải, scale API thường làm tình hình tệ hơn. Trước hết phải xác định bottleneck, giảm arrival rate, dừng workload không ưu tiên và giữ connection cho critical transaction.

## 20. Broker overload và consumer lag

Broker có thể khỏe nhưng consumer không theo kịp. Cần theo dõi:
- Publish rate so với consume rate.
- Lag theo partition/group.
- Oldest message age.
- Consumer processing latency.
- Retry/DLQ.
- Partition skew.
- Rebalance frequency.
- Broker disk/retention/network.
- Outbox backlog.

Khi lag tăng:
1. Xác định consumer chậm do CPU, DB, external API hay poison message.
2. Không tăng concurrency trước khi biết downstream chịu được.
3. Tách event priority nếu có contract.
4. Giảm producer rate hoặc pause workload không khẩn cấp.
5. Tăng consumer theo từng bước.
6. Kiểm tra ordering và idempotency.
7. Dự báo thời gian drain backlog.
8. Reconcile workflow quá deadline.

Backlog có thể là dữ liệu cần xử lý, không phải rác. Không xóa message quan trọng chỉ để làm dashboard xanh.

## 21. Dependency bên ngoài bị lỗi

API đối tác có thể trả:
- 429 quota exceeded.
- 5xx service unavailable.
- Timeout không rõ kết quả.
- 401/403 do token hoặc quyền.
- Response sai schema.
- Latency tăng nhưng vẫn trả 200.
- DNS/TLS/network failure.

Phân loại:
- Retryable theo Retry-After.
- Cần refresh credential.
- Permanent/business rejection.
- Unknown outcome cần reconciliation.
- Contract violation cần quarantine và alert.

Không retry 401/403 vô hạn. Không coi timeout payment là payment thất bại chắc chắn. Cần query provider theo reference/idempotency key trước khi tạo thao tác mới.

Nếu có alternate provider, cần policy routing, credential, data consistency và failover drill. Chuyển provider không chỉ là đổi URL; cần hiểu idempotency và semantics của từng nhà cung cấp.

## 22. Cascading failure và retry amplification

Một chuỗi điển hình:
1. Payment provider chậm.
2. Order Service giữ request thread lâu.
3. HTTP pool cạn.
4. Client timeout và retry.
5. Gateway retry thêm.
6. Payment nhận nhiều attempt hơn.
7. Circuit breaker mở muộn.
8. Notification/Inventory cũng bị ảnh hưởng vì shared executor hoặc DB.

Biện pháp:
- Timeout budget xuyên request.
- Retry budget một tầng rõ ràng.
- Circuit breaker theo dependency.
- Bulkhead riêng.
- Concurrency/rate limit.
- Bounded queues.
- Admission control.
- Cancellation propagation.
- Graceful degradation.
- Theo dõi end-to-end business outcome.

Mục tiêu là **ngăn lỗi cục bộ trở thành lỗi toàn hệ thống**. Không phải mọi service đều cần dừng; các capability độc lập vẫn nên hoạt động nếu dữ liệu và policy cho phép.

## 23. Failure drill: thiết kế kịch bản có giới hạn

Mỗi kịch bản cần:
- Hypothesis.
- Môi trường và phạm vi.
- Người điều phối và người quan sát.
- Dependency/failure được inject.
- Traffic profile và duration.
- SLI/SLO và stop conditions.
- Rollback/abort plan.
- Data safety constraints.
- Kết quả mong đợi.
- Hành động sau drill.

Một template:

~~~yaml
drill:
  name: payment-latency-degradation
  environment: staging
  hypothesis: order-api-remains-responsive
  injection:
    dependency: payment-sandbox
    behavior: latency
    delayMillis: 1800
    percentage: 40
  traffic:
    requestsPerSecond: 80
    durationMinutes: 10
  guardrails:
    maxErrorRate: 0.02
    maxDbConnections: 70
    stopOnDuplicatePayment: true
  expected:
    circuitBreaker: open-after-threshold
    userState: payment-pending-or-unknown
    recovery: gradual-probe-and-drain
~~~

Đây là cấu hình mô tả minh họa, không phải file cấu hình Chaos tool cụ thể. Cần chuyển sang cú pháp của công cụ thử nghiệm đang dùng.

## 24. Các cấp độ diễn tập

Có thể tiến hành theo mức tăng dần:

1. **Unit/component fault injection:** mock timeout, 429, 5xx và connection reset.
2. **Integration drill:** broker/DB container chậm hoặc restart.
3. **Staging load test:** tải đại diện và dependency failure.
4. **Pre-production resilience test:** node/pod/zone failure trong topology tương tự production.
5. **Production canary drill:** phạm vi nhỏ, có phê duyệt vận hành, stop condition và rollback tức thì.
6. **Game day:** nhiều vai trò cùng thực hiện incident playbook, tập trung vào giao tiếp và quyết định.

Không nhảy thẳng từ unit test sang việc tắt dependency production. Mức độ inject phải phù hợp khả năng quan sát, kiểm soát và khôi phục.

## 25. Stop conditions và kill switch

Một drill phải dừng ngay khi:
- Ảnh hưởng vượt cohort/phạm vi được phép.
- Critical journey SLO vượt ngưỡng dừng.
- Có duplicate/lost transaction.
- Data correctness không còn xác minh được.
- Dependency ngoài phạm vi bị ảnh hưởng.
- Không thể rollback injection.
- Monitoring hoặc người điều phối mất khả năng quan sát.
- Tài nguyên production tiến gần giới hạn an toàn.
- Có tác động tới khách hàng thật ngoài phạm vi cho phép.

Kill switch phải:
- Được thử trước.
- Có owner và quyền thao tác.
- Tắt được injection độc lập.
- Không phụ thuộc chính dependency đang bị lỗi.
- Có metric xác nhận injection đã dừng.

Không tiếp tục drill chỉ để thu thập thêm dữ liệu khi guardrail đã bị vi phạm.

## 26. Controlled recovery: phục hồi theo từng lớp

Khi lỗi được phát hiện:
1. Dừng inject hoặc thay đổi gây lỗi.
2. Giữ nguyên bằng chứng và timeline.
3. Giới hạn traffic mới nếu hệ thống còn quá tải.
4. Xác định dependency nào đã khỏe và dependency nào vẫn degraded.
5. Kiểm tra queue, pool, DB và downstream capacity.
6. Khôi phục một phần workload ưu tiên.
7. Probe dependency với concurrency thấp.
8. Tăng traffic từng bước.
9. Drain backlog theo tốc độ an toàn.
10. Reconcile business state và side effects.
11. Xác nhận SLO trong cửa sổ ổn định.
12. Kết thúc incident/drill và lưu bài học.

Không mở toàn bộ traffic chỉ vì health endpoint trả 200. Health check đơn giản có thể không kiểm tra quota, DB capacity, queue lag hay khả năng hoàn tất transaction.

## 27. Vì sao dependency hồi phục vẫn có thể làm hệ thống sập lần hai?

Khi provider trở lại:
- Hàng nghìn request đang retry đồng loạt.
- Half-open circuit breaker cho quá nhiều probe.
- Consumer cùng tăng concurrency.
- Queue backlog tạo spike.
- Cache cold làm DB nhận toàn bộ read.
- Connection pool đồng loạt reconnect.
- Autoscaler thêm instance nhanh hơn khả năng dependency hấp thụ.
- Scheduled job bị dồn lịch.

Đây là **recovery storm**. Khôi phục phải có rate limit và ramp-up.

Ví dụ:
~~~text
0-2 phút: probe 1-2 request/giây
2-5 phút: mở 5% traffic nếu metric ổn
5-10 phút: tăng 10-20% mỗi bước
Sau mỗi bước: kiểm tra latency, error, pool và backlog
Nếu xấu đi: giảm traffic, mở breaker hoặc pause consumer
~~~

Tỷ lệ/thời gian chỉ minh họa. Quyết định theo capacity thực và business deadline. Không dùng lịch cứng nếu metric không đạt.

## 28. Recovery order và dependency readiness

Một thứ tự phục hồi có thể là:
1. Network/DNS/identity cần thiết.
2. Database và storage.
3. Broker/control plane.
4. Core domain services.
5. API gateway/traffic.
6. Async consumers và background workers.
7. Notification, analytics và batch không critical.

Thứ tự thực tế phụ thuộc dependency graph. Một consumer có thể cần DB trước broker; một service có thể khởi động nhưng không readiness cho tới khi credential được refresh.

Phân biệt:
- **Liveness:** process có còn sống và có thể tự tiến triển?
- **Readiness:** instance có thể nhận traffic nghiệp vụ?
- **Startup probe:** ứng dụng đã hoàn tất khởi động?
- **Dependency health:** dependency có khỏe và đủ capacity?
- **Business readiness:** critical journey có thể hoàn tất đúng?

Không làm liveness probe restart liên tục một process chỉ vì dependency bên ngoài tạm thời lỗi. Restart storm làm tình hình xấu hơn. Readiness có thể ngừng nhận traffic trong khi process vẫn sống và tiếp tục recovery.

## 29. Health check không nên tạo thêm tải

Health endpoint bị gọi thường xuyên bởi nhiều orchestrator/load balancer. Nếu mỗi lần probe lại chạy query nặng, gọi mọi dependency hoặc kiểm tra toàn bộ workflow, chính health check có thể tạo overload.

Thiết kế:
- Liveness kiểm tra process/runtime nội bộ, nhanh và ít dependency.
- Readiness kiểm tra khả năng nhận loại traffic tương ứng.
- Dependency checks có cache/interval hoặc endpoint riêng.
- Không dùng health endpoint thay monitoring/SLO.
- Không restart mọi instance khi shared DB lỗi.
- Phân biệt degraded với dead.

Một service có thể healthy về process nhưng không ready cho Payment operation. Có thể dùng capability-specific readiness nếu platform hỗ trợ và policy rõ.

## 30. Autoscaling trong sự cố

Autoscaling giúp tăng capacity nhưng có độ trễ và giới hạn:
- Image pull/startup JVM.
- Node provisioning.
- Quota provider.
- DB connection growth.
- Broker partition count.
- Downstream capacity.
- Scale-down stabilization.

Không scale dựa CPU duy nhất nếu bottleneck là DB hoặc external provider. Metric tốt hơn có thể là queue depth/age, request concurrency, latency và saturation, nhưng phải có giới hạn max và guardrail downstream.

Trong recovery:
- Đặt max replica có kiểm soát.
- Giới hạn connection pool tổng.
- Tăng worker theo từng bước.
- Giữ min capacity cho critical path.
- Không scale down quá sớm khi backlog chưa drain.
- Kiểm tra chi phí và capacity sau khi ổn định.

## 31. Data correctness trong quá tải và phục hồi

Trong failure, response timeout có thể xảy ra sau khi transaction đã commit. Không thể suy ra “client timeout = transaction thất bại”.

Cần:
- Idempotency key cho request có side effect.
- Event ID ổn định.
- Inbox/outbox.
- State machine có UNKNOWN/PENDING nếu kết quả chưa rõ.
- Provider reconciliation.
- Transaction status query.
- Audit trail.
- Deduplication và replay có kiểm soát.

Ví dụ payment:
1. Gửi authorize với idempotency key K.
2. Provider xử lý nhưng response bị mất.
3. Service không biết authorize đã thành công chưa.
4. Không gửi request mới với key khác.
5. Query provider theo K/reference.
6. Cập nhật trạng thái từ kết quả xác thực.
7. Nếu quá deadline, chuyển manual review theo policy.

Không để client retry tạo payment attempt mới chỉ vì không nhận được response đầu tiên.

## 32. Queue draining và backlog recovery

Giả sử backlog có 600.000 event, consumer xử lý được 1.000 event/giây và producer tiếp tục thêm 200 event/giây. Năng lực ròng là 800 event/giây:

\[
\text{Drain time} \approx \frac{600000}{1000-200}=750\text{ seconds}
\]

Khoảng 12,5 phút theo giả định ổn định. Thực tế còn có partition skew, retry, payload size, downstream latency và event không đồng nhất.

Trước khi tăng consumer:
- Đo processing rate thật.
- Xác nhận DB/HTTP dependency chịu tải.
- Kiểm tra event priority/deadline.
- Tính retention còn lại.
- Kiểm tra poison message và retry.
- Đặt max concurrency.
- Theo dõi oldest age và business completion.

Có thể tách event cũ theo partition/tenant hoặc ưu tiên critical workflow, nhưng phải giữ ordering và fairness theo contract.

## 33. Circuit breaker half-open và probe có kiểm soát

Khi breaker chuyển HALF_OPEN, không cho toàn bộ request đổ vào dependency cùng lúc. Chỉ cho số probe nhỏ:
- Một vài request nhẹ.
- Không thực hiện side effect nếu không cần.
- Có timeout ngắn.
- Đo latency và error.
- Tăng concurrency sau nhiều probe thành công.
- Mở lại ngay khi có dấu hiệu thất bại.

Nếu probe chỉ kiểm tra health endpoint nhưng API nghiệp vụ vẫn bị quota hoặc DB nghẽn, breaker có thể đóng quá sớm. Probe phải đại diện cho khả năng dependency thực sự cần.

Không dùng health request tạo giao dịch thanh toán hoặc thay đổi dữ liệu.

## 34. Java/Spring: timeout và circuit breaker

Ví dụ dùng Resilience4j để minh họa cách giới hạn lời gọi:

~~~java
@Service
class PaymentClient {
    private final WebClient webClient;

    PaymentClient(WebClient.Builder builder) {
        this.webClient = builder
            .baseUrl("https://payment.example")
            .build();
    }

    @CircuitBreaker(name = "payment", fallbackMethod = "fallback")
    @TimeLimiter(name = "payment")
    public CompletableFuture<PaymentResult> authorize(
        PaymentCommand command
    ) {
        return webClient.post()
            .uri("/authorizations")
            .bodyValue(command)
            .retrieve()
            .bodyToMono(PaymentResult.class)
            .toFuture();
    }

    private CompletableFuture<PaymentResult> fallback(
        PaymentCommand command,
        Throwable error
    ) {
        return CompletableFuture.completedFuture(
            PaymentResult.pendingReconciliation(command.id())
        );
    }
}
~~~

Đây là ví dụ minh họa, cần cấu hình TimeLimiter/CircuitBreaker và loại exception phù hợp với phiên bản thư viện. Fallback PENDING chỉ hợp lệ khi nghiệp vụ có trạng thái chưa rõ và reconciliation. Không được trả PaymentAuthorized hoặc PaymentRejected chỉ để API không báo lỗi.

### 34.1. Cấu hình minh họa

~~~yaml
resilience4j:
  circuitbreaker:
    instances:
      payment:
        slidingWindowType: COUNT_BASED
        slidingWindowSize: 50
        minimumNumberOfCalls: 20
        failureRateThreshold: 50
        slowCallRateThreshold: 60
        slowCallDurationThreshold: 700ms
        waitDurationInOpenState: 10s
        permittedNumberOfCallsInHalfOpenState: 3
  timelimiter:
    instances:
      payment:
        timeoutDuration: 900ms
        cancelRunningFuture: true
~~~

Các giá trị chỉ để minh họa. Cần khớp với deadline upstream, latency distribution, provider SLA và semantics cancellation. Hủy Future không bảo đảm provider đã hủy side effect.

## 35. Java: bounded executor và bulkhead

Một executor có queue hữu hạn và rejection policy:

~~~java
@Bean
Executor paymentExecutor() {
    return new ThreadPoolExecutor(
        12,
        12,
        0L,
        TimeUnit.MILLISECONDS,
        new ArrayBlockingQueue<>(80),
        new ThreadPoolExecutor.AbortPolicy()
    );
}
~~~

Khi queue đầy, task mới bị từ chối thay vì giữ vô hạn trong memory. Ứng dụng cần bắt rejection và trả kết quả phù hợp, ví dụ 503/429 hoặc đưa vào workflow async nếu đã được chấp nhận trước đó.

Không chạy side effect rồi mới phát hiện task bị từ chối. Admission control nên xảy ra trước khi ghi nhận giao dịch hoặc cần có trạng thái phục hồi rõ.

### 35.1. Semaphore bulkhead

~~~java
final class DependencyBulkhead {
    private final Semaphore permits = new Semaphore(20);

    <T> T execute(Callable<T> operation) throws Exception {
        if (!permits.tryAcquire(50, TimeUnit.MILLISECONDS)) {
            throw new RejectedExecutionException(
                "Dependency concurrency limit reached"
            );
        }
        try {
            return operation.call();
        } finally {
            permits.release();
        }
    }
}
~~~

Ví dụ giới hạn 20 lời gọi đồng thời và chờ permit tối đa 50 ms. Production cần metric active permits, rejection, wait time và timeout; semaphore phải được quản lý theo dependency/tenant phù hợp.

## 36. Java: token bucket rate limiter minh họa

Một token bucket đơn giản:

~~~java
final class TokenBucket {
    private final long capacity;
    private final double tokensPerNano;
    private double tokens;
    private long lastRefillNanos;

    TokenBucket(long capacity, double tokensPerSecond) {
        this.capacity = capacity;
        this.tokensPerNano = tokensPerSecond / 1_000_000_000.0;
        this.tokens = capacity;
        this.lastRefillNanos = System.nanoTime();
    }

    synchronized boolean tryAcquire() {
        long now = System.nanoTime();
        long elapsed = now - lastRefillNanos;
        tokens = Math.min(
            capacity,
            tokens + elapsed * tokensPerNano
        );
        lastRefillNanos = now;

        if (tokens < 1.0) {
            return false;
        }
        tokens -= 1.0;
        return true;
    }
}
~~~

Đây là implementation học tập trong một process. Nó không đồng bộ limit giữa nhiều instance, không xử lý distributed quota và không có persistence. Production thường dùng gateway/distributed limiter hoặc atomic storage; cần xử lý clock, burst, fairness và race condition.

## 37. Java: kiểm tra deadline tổng

Ví dụ mô hình deadline để tránh retry vượt quá thời gian còn lại:

~~~java
record Deadline(long endNanos) {
    static Deadline after(Duration duration) {
        return new Deadline(
            System.nanoTime() + duration.toNanos()
        );
    }

    Duration remaining() {
        long left = endNanos - System.nanoTime();
        return Duration.ofNanos(Math.max(0, left));
    }

    boolean expired() {
        return endNanos - System.nanoTime() <= 0;
    }
}
~~~

Khi gọi dependency, lấy remaining budget để đặt timeout nhỏ hơn thời gian còn lại. Không bắt đầu retry nếu không còn đủ thời gian để hoàn tất một attempt có ích.

Deadline monotonic trong process; khi truyền qua network cần quy ước phù hợp, không truyền một giá trị nanoTime giữa các máy.

## 38. Load test và stress test khác nhau

**Load test:** kiểm tra hệ thống ở tải mục tiêu và profile dự kiến.

**Stress test:** tăng tải vượt mức thiết kế để tìm saturation/breaking point.

**Spike test:** tăng traffic đột ngột để quan sát autoscaling, queue và cache.

**Soak test:** duy trì tải lâu để tìm memory leak, pool leak, disk growth hoặc backlog drift.

**Capacity test:** tìm throughput tối đa trong khi vẫn đạt SLO.

**Resilience/failure test:** kết hợp workload với dependency failure hoặc resource loss.

Một kế hoạch tốt thường kết hợp nhiều kiểu, nhưng mỗi lượt phải có mục tiêu riêng. Stress test không thay thế load test; hệ thống có thể chịu peak ngắn nhưng không chịu được tải vừa phải kéo dài vì memory leak.

## 39. Kịch bản quá tải theo từng cấp

Một ma trận thực hành:

| Kịch bản | Tải | Failure | Kỳ vọng |
|---|---|---|---|
| Baseline | 1x | Không | SLO đạt |
| Target | 1x mục tiêu | Không | Capacity đủ |
| Peak | 2x trong thời gian ngắn | Không | Headroom/autoscale hoạt động |
| Spike | 1x lên 4x nhanh | Không | Admission/queue không mất kiểm soát |
| Dependency slow | 1x | DB +500 ms | Timeout/bulkhead bảo vệ |
| Dependency down | 0,5x | Payment unavailable | Degrade và giữ trạng thái đúng |
| Broker lag | 1x | Consumer giảm 70% | Backlog được giới hạn/cảnh báo |
| Recovery storm | backlog lớn | Dependency vừa hồi phục | Ramp-up an toàn |
| Soak | 0,8x kéo dài | Không | Không leak hoặc tăng backlog |

Các hệ số chỉ minh họa. Chọn dựa trên traffic thực và khả năng của môi trường. Không áp 4x traffic vào hệ thống shared staging nếu các team khác cùng dùng tài nguyên.

## 40. Chaos engineering có kiểm soát

Chaos engineering không phải random kill process liên tục. Nó là cách kiểm tra giả thuyết về độ bền bằng cách inject failure có giới hạn.

Nguyên tắc:
- Bắt đầu ở staging hoặc canary nhỏ.
- Chỉ inject một failure mode mỗi lần.
- Có baseline và metric.
- Có blast-radius boundary.
- Có kill switch.
- Có owner giám sát.
- Không inject vào hệ thống bên ngoài không được phép.
- Có kế hoạch dừng và phục hồi.
- Ghi lại kết quả và remediation.

Khi tổ chức đã có maturity, có thể mở rộng game day hoặc production experiment theo policy. Mỗi experiment phải có phạm vi và người chịu trách nhiệm rõ.

## 41. Runbook incident: phát hiện và phân loại

Khi alert xuất hiện:
1. Xác định customer/business impact.
2. Xác định thời điểm bắt đầu và phạm vi tenant/region.
3. Kiểm tra SLI critical journey.
4. Tìm bottleneck trên dependency graph.
5. So sánh traffic/latency/error với baseline.
6. Kiểm tra deploy/config gần đây.
7. Xác định overload, dependency failure hay data correctness issue.
8. Chọn hành động giới hạn blast radius.
9. Ghi timeline và quyết định.

Không bắt đầu bằng restart mọi service. Restart có thể giải phóng một số tài nguyên nhưng cũng gây mất kết nối, rebalance, warm-up và recovery storm.

## 42. Runbook: quá tải API

Một trình tự tham khảo:
1. Bật hoặc siết admission control.
2. Tạm dừng workload không critical.
3. Giới hạn concurrency và queue length.
4. Kiểm tra thread/connection pool saturation.
5. Xác định dependency chậm.
6. Mở circuit breaker nếu ngưỡng được xác nhận.
7. Tăng capacity chỉ khi bottleneck có thể scale.
8. Giữ capacity cho health/status và critical transaction.
9. Giảm traffic từng bước khi SLI hồi phục.
10. Xác nhận request bị từ chối có trạng thái/idempotency rõ.

Không tăng replica khi bottleneck là quota provider hoặc DB. Tăng caller có thể làm dependency bị tấn công mạnh hơn.

## 43. Runbook: database chậm

1. Kiểm tra query latency, lock, CPU/IOPS và replication lag.
2. Kiểm tra pool active/pending và transaction dài.
3. Tạm dừng report/batch không critical.
4. Giới hạn consumer concurrency ghi DB.
5. Bảo vệ connection cho critical workflow.
6. Kiểm tra slow query và thay đổi gần đây.
7. Không chạy migration/index build nặng trong lúc incident nếu chưa đánh giá.
8. Scale DB hoặc storage chỉ khi bottleneck và phương án rõ.
9. Khôi phục consumer từng bước.
10. Reconcile transaction timeout/unknown outcome.

Không xóa backlog hoặc kill transaction tùy tiện. Cần hiểu transaction nào đã commit và side effect nào đã xảy ra.

## 44. Runbook: broker backlog tăng

1. Xác định topic/group/partition gây lag.
2. Đo producer rate, consumer rate và oldest event age.
3. Kiểm tra poison message/DLQ.
4. Xác định bottleneck downstream.
5. Giới hạn producer nếu business cho phép.
6. Tăng worker từng bước nếu DB/provider còn capacity.
7. Ưu tiên workflow theo policy.
8. Dự báo thời gian drain.
9. Theo dõi event quá deadline và reconciliation.
10. Chỉ kết thúc incident khi lag/freshness ổn định và business state hội tụ.

Broker disk đầy và consumer lag là hai vấn đề khác nhau; cần phân biệt storage retention, partition skew và worker throughput.

## 45. Runbook: dependency đối tác timeout

1. Kiểm tra provider status/latency và quota.
2. Dừng retry storm; giữ retry budget.
3. Mở circuit breaker theo policy.
4. Với read-only, dùng cache/fallback nếu freshness cho phép.
5. Với side effect, chuyển trạng thái UNKNOWN/PENDING.
6. Tra cứu provider bằng idempotency/reference trước retry mới.
7. Chỉ chuyển alternate provider nếu semantics và routing đã được kiểm chứng.
8. Theo dõi backlog/outbox.
9. Khi provider hồi phục, probe và ramp-up.
10. Reconcile các giao dịch không rõ kết quả.

Không báo PaymentFailed chỉ vì timeout; cũng không báo PaymentSucceeded nếu chưa xác nhận.

## 46. Controlled recovery: checklist sau khi dependency khỏe lại

- Dependency health và capacity được xác nhận.
- Credential, DNS và network đã ổn định.
- Probe nhỏ thành công qua đường nghiệp vụ phù hợp.
- Circuit breaker chuyển half-open theo giới hạn.
- Request rate tăng theo cohort.
- Consumer concurrency tăng theo từng bước.
- DB pool/CPU/lock và provider quota được theo dõi.
- Queue age và outbox backlog giảm.
- Retry được phân tán bằng backoff/jitter.
- Cache được warm có kiểm soát.
- Không có duplicate/lost transaction.
- SLO và business outcome ổn định đủ cửa sổ.
- Runbook/incident timeline được cập nhật.

Một health endpoint trả 200 chỉ là một tín hiệu; cần kiểm tra capability thực tế và business correctness.

## 47. Game day: phân vai và thực hành quyết định

Một game day có thể có:
- Incident commander: điều phối và quyết định.
- Service owner: kiểm tra ứng dụng.
- Data owner/DBA: bảo vệ dữ liệu và database.
- Platform/SRE: hạ tầng, network và capacity.
- Observer: ghi timeline, câu hỏi và độ trễ quyết định.
- Communications owner: cập nhật trạng thái theo quy trình tổ chức.

Không cần nhiều người nếu hệ thống nhỏ, nhưng phải biết ai có quyền dừng drill và ai chịu trách nhiệm xác nhận dữ liệu.

Kịch bản:
1. Bắt đầu tải baseline.
2. Inject latency vào Payment sandbox.
3. Quan sát timeout, breaker và user state.
4. Tăng traffic có kiểm soát.
5. Dừng injection.
6. Cho provider hồi phục nhưng giữ backlog.
7. Thực hiện probe và ramp-up.
8. Reconcile payment state.
9. Kết thúc khi SLO và data correctness đạt.
10. Review điều gì hoạt động/chưa hoạt động.

Observer không nên sửa hệ thống trong lúc drill trừ khi stop condition được kích hoạt; nếu không, dữ liệu thử nghiệm khó diễn giải.

## 48. Đo thời gian phục hồi và chất lượng phản ứng

Các mốc:
- TTD: time to detect.
- TTA: time to acknowledge.
- TTM: time to mitigate.
- TTR: time to restore service.
- Time to data convergence.
- Time to drain backlog.
- Time to close customer impact.

Phân biệt service restoration với business recovery. API có thể trả 200 trở lại nhưng 30.000 order vẫn ở trạng thái UNKNOWN hoặc notification chưa được gửi.

Sau drill, tìm:
- Alert nào đến quá muộn?
- Dashboard nào thiếu?
- Ai không rõ quyền quyết định?
- Runbook nào không chạy được?
- Cơ chế nào làm blast radius tăng?
- Điều gì khiến recovery storm?
- Dữ liệu nào cần reconciliation thủ công?
- Cải thiện nào có owner/deadline?

## 49. Error budget và quyết định giảm tính năng

Nếu error budget đang bị tiêu hao nhanh, đội có thể cần:
- Dừng release không liên quan.
- Tắt tính năng best-effort.
- Giảm batch/report.
- Giữ capacity cho critical journey.
- Chuyển một số tác vụ sang async.
- Tạm dừng experiment.

Không tự động tắt feature quan trọng chỉ vì CPU cao. Quyết định phải theo user impact, SLO và policy. Error budget giúp cân bằng tốc độ thay đổi và reliability, không phải lý do để bỏ qua incident.

## 50. Anti-patterns trong overload và recovery

| Anti-pattern | Hậu quả | Cách làm tốt hơn |
|---|---|---|
| Retry vô hạn | Khuếch đại tải | Retry budget, backoff, jitter |
| Timeout quá dài | Thread/pool bị giữ | Deadline budget xuyên request |
| Queue không giới hạn | Memory/latency tăng vô hạn | Bounded queue và admission control |
| Scale caller khi dependency chết | Dependency càng quá tải | Bulkhead, breaker, rate limit |
| Restart tất cả instance | Restart/reconnect storm | Restart có chọn lọc, readiness |
| Đóng breaker ngay khi health xanh | Recovery storm | Probe nhỏ và ramp-up |
| Tăng consumer vô hạn | DB/provider quá tải | Scale theo downstream capacity |
| Dùng fallback stale cho mọi dữ liệu | Quyết định nghiệp vụ sai | Fallback theo semantics/freshness |
| Shed giao dịch đã commit | Mất trạng thái | Idempotency và reconciliation |
| Chỉ nhìn CPU | Bỏ qua pool/queue/lock | Theo dõi saturation đa chiều |
| Health check gọi mọi dependency | Tạo thêm tải và restart storm | Liveness/readiness riêng |
| Xóa backlog để dashboard xanh | Mất business event | Drain/replay/reconcile |
| Không diễn tập kill switch | Không dừng được injection | Test abort path trước |
| Không có observer | Mất timeline/bằng chứng | Ghi quyết định và metric |
| Mở toàn traffic cùng lúc | Recovery storm | Canary/ramp-up |
| Chỉ xác nhận API 200 | Dữ liệu chưa hội tụ | Business SLI và reconciliation |

## 51. Case study: Payment provider chậm

**Bối cảnh:** Checkout nhận 300 request/giây. Payment provider bắt đầu phản hồi trong 4 giây thay vì 300 ms. Gateway timeout ở 2 giây.

Hệ quả nếu không có bảo vệ:
- Order threads chờ provider.
- Connection pool và executor tăng hàng đợi.
- Client retry.
- Payment provider nhận nhiều attempt.
- Kết quả authorization không rõ.
- Order bị treo hoặc duplicate.

Thiết kế có kiểm soát:
1. Timeout Payment theo remaining request budget.
2. Bulkhead giới hạn concurrent authorization.
3. Circuit breaker mở khi slow-call/failure threshold đạt.
4. API trả trạng thái PENDING/UNKNOWN theo contract.
5. Idempotency key giữ nguyên.
6. Reconciliation query provider trước retry.
7. Notification/Analytics tiếp tục độc lập.
8. Provider hồi phục: probe nhỏ, mở traffic theo cohort.
9. Đối soát mọi payment attempt chưa rõ.
10. Chỉ đóng incident khi order/payment state hội tụ.

Kết quả cần đo: p99 Checkout, thread/connection wait, provider attempt count, duplicate capture, pending age và thời gian reconciliation.

## 52. Case study: DB quá tải vì consumer scale-out

**Bối cảnh:** Broker có backlog 2 triệu event. Team tăng consumer từ 10 lên 100. Mỗi consumer mở pool 10 connection vào cùng Orders DB.

Potential connection demand tăng từ 100 lên 1.000. Database không đủ capacity, query latency tăng và API đồng bộ cũng bị ảnh hưởng.

Phục hồi:
- Hạn chế consumer concurrency.
- Tách consumer có write pattern khác nhau.
- Dùng batch và giới hạn connection.
- Giảm workload analytics/background.
- Scale DB nếu workload và giới hạn cho phép.
- Drain backlog theo throughput ròng.
- Theo dõi API latency cùng consumer lag.
- Không mở lại concurrency cao trước khi DB ổn định.

Bài học: broker throughput không phải capacity của downstream. Scaling phải theo bottleneck end-to-end.

## 53. Case study: cache outage tạo stampede

**Bối cảnh:** Redis mất kết nối. Mọi request Catalog chuyển sang DB. DB CPU và connection wait tăng nhanh.

Biện pháp:
- Circuit breaker cho cache.
- Single-flight cho cache miss cùng key.
- Stale-while-revalidate với dữ liệu cho phép cũ.
- Rate limit các query nặng.
- Giới hạn DB concurrency.
- Tạm giảm recommendation/filter nặng.
- Phục hồi cache và warm key theo batch.
- Không cho toàn bộ instance reconnect đồng loạt.

Kiểm tra tính đúng của cache key theo tenant/locale/permission. Cache fallback không được rò dữ liệu hoặc dùng stale value cho giá/thanh toán nếu semantics không cho phép.

## 54. Case study: broker phục hồi sau outage

**Bối cảnh:** Consumer ngừng 20 phút. Producer vẫn ghi outbox; khi broker hồi phục, publisher và consumer đồng loạt tăng tốc.

Kế hoạch:
1. Xác minh broker, partition, retention và ACL.
2. Bắt đầu publisher với rate giới hạn.
3. Xác nhận event ID và ordering.
4. Mở consumer concurrency thấp.
5. Theo dõi DB/provider và queue age.
6. Tăng dần theo throughput ròng.
7. Cô lập poison message.
8. Xử lý event hết deadline theo business policy.
9. Reconcile workflow pending.
10. Chỉ kết thúc khi backlog trong ngưỡng và freshness SLO đạt.

Không xóa outbox hoặc DLQ chỉ để giảm dung lượng. Phải biết event nào đã được xử lý, event nào chưa và event nào cần xử lý thủ công.

## 55. Bài tập thực hành

**Bài A — timeout budget:** Client deadline 2 giây, gateway 1,8 giây, Order Service gọi Inventory và Payment. Chia budget cho connect, pool wait, response và local processing; giải thích vì sao timeout ở từng tầng phải nhỏ hơn deadline còn lại.

**Bài B — retry amplification:** Client retry 3 lần, gateway retry 2 lần, service retry 3 lần. Tính số attempt tối đa theo mô hình nhân và thiết kế lại để giới hạn retry toàn workflow.

**Bài C — circuit breaker:** Payment có 20% lỗi trong cửa sổ 50 request, slow-call threshold 700 ms. Đề xuất minimum calls, failure/slow thresholds và half-open probes dựa trên SLO.

**Bài D — bulkhead:** Order có 3 dependency: Inventory, Payment và Recommendation. Chia concurrency/pool và nêu cách bảo vệ request status khi Recommendation chậm.

**Bài E — DB overload:** Connection pool pending tăng, CPU DB 95%, consumer lag tăng. Lập thứ tự hành động để bảo vệ Checkout và giảm backlog mà không làm DB quá tải thêm.

**Bài F — cache stampede:** Redis outage làm DB nhận gấp 8 lần query. Đề xuất single-flight, stale cache, rate limit và điều kiện không được dùng dữ liệu cũ.

**Bài G — provider timeout:** Payment timeout sau khi request được gửi. Xác định trạng thái UNKNOWN, idempotency key, provider lookup và cách tránh capture trùng.

**Bài H — recovery storm:** Dependency vừa hồi phục, 5.000 request đang retry và 300.000 message chờ. Thiết kế probe, ramp-up, retry jitter và giới hạn consumer.

**Bài I — load shedding:** Phân loại Checkout, Payment, Notification, Analytics, Recommendation và export theo priority. Nêu response/status khi từ chối request mới.

**Bài J — broker lag:** Producer 1.200 event/s, consumer 900 event/s, backlog 540.000. Tính tốc độ tăng backlog và drain time nếu producer hạ còn 500 event/s và consumer giữ 900 event/s.

**Bài K — failure drill:** Viết plan mô phỏng DB latency tăng 500 ms trong staging, gồm baseline, injection, guardrail, stop conditions và kết quả cần thu.

**Bài L — game day:** Phân vai incident commander, service owner, DBA, SRE và observer. Tạo timeline từ alert tới phục hồi và reconciliation.

**Bài M — health check:** Một shared DB outage làm liveness của 20 service fail và orchestrator restart liên tục. Thiết kế lại liveness/readiness và dependency health.

**Bài N — soak test:** Hệ thống chạy 0,8x peak trong 8 giờ, backlog tăng chậm dù request latency ổn. Đề xuất metric, giả thuyết leak và cách tìm service rate thấp hơn arrival rate.

**Bài O — capacity:** API xử lý 250 request/s, average service time 200 ms. Ước lượng concurrency theo Little's Law, sau đó nêu dữ liệu cần có để chọn thread pool thực tế.

## 56. Checklist chuẩn bị failure drill

1. Chọn một giả thuyết rõ ràng.
2. Xác định critical journey và dependency graph.
3. Chọn môi trường/phạm vi an toàn.
4. Lưu baseline và traffic profile.
5. Xác định SLI/SLO, mẫu tối thiểu và cửa sổ đo.
6. Chọn đúng một failure mode chính.
7. Định nghĩa injection và duration.
8. Đặt stop conditions và kill switch.
9. Xác nhận dữ liệu thử nghiệm và side effects an toàn.
10. Phân vai người điều phối, owner và observer.
11. Kiểm tra dashboard/alert trước khi inject.
12. Chuẩn bị rollback/abort.
13. Ghi version/config/seed/dataset.
14. Thực hiện theo từng bước.
15. Lưu metric, timeline và quyết định.

## 57. Checklist phục hồi có kiểm soát

- [ ] Dừng injection và thay đổi gây lỗi.
- [ ] Xác nhận dependency thực sự khỏe và đủ capacity.
- [ ] Kiểm tra network, DNS, credential và quota.
- [ ] Giới hạn traffic mới nếu còn overload.
- [ ] Kiểm tra queue, pool, DB và consumer lag.
- [ ] Probe với concurrency nhỏ.
- [ ] Mở circuit breaker theo half-open policy.
- [ ] Tăng traffic/consumer theo từng bước.
- [ ] Phân tán retry bằng backoff và jitter.
- [ ] Warm cache theo batch, tránh stampede.
- [ ] Drain backlog theo capacity downstream.
- [ ] Reconcile request/payment/event có kết quả chưa rõ.
- [ ] Kiểm tra duplicate, missing và invalid business state.
- [ ] Xác nhận SLO và freshness qua cửa sổ đủ dài.
- [ ] Ghi timeline, owner và bài học.

## 58. Ghi nhớ

- **Overload là vấn đề hệ thống và queueing**, không chỉ là CPU cao.
- **Timeout phải có budget xuyên dependency**, không để request giữ thread vô hạn.
- **Retry có thể khuếch đại tải**; dùng retry budget, backoff, jitter và idempotency.
- **Circuit breaker** ngăn tiếp tục gọi dependency đang lỗi; **bulkhead** giới hạn blast radius.
- **Rate limiting, admission control và load shedding** bảo vệ capability quan trọng khi nhu cầu vượt capacity.
- **Graceful degradation** chỉ an toàn khi fallback giữ đúng semantics và freshness.
- **Queue không tạo capacity**; cần giới hạn backlog, theo dõi age và bảo vệ downstream.
- **Health check không nên restart cả hệ thống vì một dependency ngoài đang lỗi.**
- **Dependency hồi phục chưa có nghĩa hệ thống đã ổn**; recovery storm có thể gây sự cố lần hai.
- **Phục hồi theo từng bước**: probe, ramp-up, drain backlog và reconcile.
- **Timeout không chứng minh side effect thất bại**; dùng UNKNOWN/PENDING và provider reconciliation.
- **Failure drill cần giả thuyết, baseline, guardrail, kill switch và observer.**
- **Đo business recovery**, không chỉ việc API trả 200 trở lại.
- **Runbook phải có owner và được diễn tập**; một tài liệu chưa chạy chưa chứng minh khả năng phục hồi.

Một hệ thống microservices bền vững không phải hệ thống không bao giờ gặp lỗi. Đó là hệ thống **giới hạn được lượng công việc đang chờ, ngăn lỗi lan qua ranh giới service, giữ đúng trạng thái nghiệp vụ khi kết quả không rõ, và khôi phục capacity theo nhịp mà dependency có thể hấp thụ**.
