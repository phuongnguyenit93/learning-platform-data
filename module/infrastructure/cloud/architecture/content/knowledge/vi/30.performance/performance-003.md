# Độ trễ đuôi và ảnh hưởng của chuỗi gọi phân tán

Một API có thể có latency trung bình 80 ms nhưng vẫn khiến người dùng thường xuyên chờ hơn một giây. Nguyên nhân là **độ trễ đuôi (tail latency)**: phần chậm nhất của phân bố thời gian phản hồi, thường được nhìn qua các percentile như p95, p99 hoặc p99.9. Trong kiến trúc microservices, một request có thể gọi nhiều service nối tiếp hoặc song song. Chỉ một dependency chậm, một hàng đợi quá tải hay một retry không hợp lý cũng có thể kéo dài toàn bộ request. Khi hệ thống tăng số dependency, xác suất ít nhất một nhánh chậm tăng lên, đặc biệt trong fan-out.

Tối ưu latency trung bình không đủ để bảo đảm trải nghiệm ổn định. Cần hiểu phân bố latency, queueing, concurrency, timeout/deadline, retry amplification, fan-out và cách đo SLO theo hành vi nghiệp vụ. Bài học này trình bày cách phân tích chuỗi gọi phân tán, nhận diện nguồn gốc tail latency và chọn biện pháp kiểm soát phù hợp mà không làm quá tải dependency hoặc tăng chi phí vô hạn.

Bài học thuộc chương **Hiệu năng** của module **CLOUD_ARCHITECTURE**. Trọng tâm là thiết kế ứng dụng cloud đáp ứng yêu cầu hiệu năng từ góc nhìn hệ thống, cân bằng độ trễ, độ tin cậy, bảo mật, khả năng mở rộng, chi phí và vận hành theo tư duy Well-Architected.

## 1. Mục tiêu học tập

Sau bài này, người học có thể:

1. Phân biệt latency trung bình, percentile, tail latency và throughput.
2. Giải thích vì sao chuỗi gọi phân tán và fan-out làm tăng xác suất request chậm.
3. Phân tích quan hệ giữa queueing, concurrency, utilization và response time.
4. Tính ngân sách latency cho chuỗi dependency và phân bổ deadline.
5. Thiết kế timeout, retry, backoff, jitter, circuit breaker và load shedding.
6. Đánh giá hedged requests và parallelism theo lợi ích, tải tăng thêm và rủi ro.
7. Dùng tracing, histogram, RED/USE metrics và SLO để tìm bottleneck.
8. Tối ưu theo critical path và workload thực tế thay vì chỉ giảm latency một service.

## 2. Latency trung bình không mô tả đầy đủ trải nghiệm

### 2.1. Phân bố latency

Latency là thời gian từ một mốc bắt đầu tới một mốc hoàn thành được định nghĩa. Với một tập request, latency không phải một con số duy nhất mà là một phân bố. Ví dụ:

| Percentile | Latency ví dụ | Diễn giải |
|---|---:|---|
| p50 | 45 ms | Một nửa request hoàn thành trong 45 ms hoặc ít hơn |
| p90 | 80 ms | 90% request hoàn thành trong 80 ms hoặc ít hơn |
| p95 | 120 ms | 95% request hoàn thành trong 120 ms hoặc ít hơn |
| p99 | 450 ms | 99% request hoàn thành trong 450 ms hoặc ít hơn |
| p99.9 | 1.8 s | 99.9% request hoàn thành trong 1.8 giây hoặc ít hơn |

Các giá trị trên chỉ để minh họa. p99 không có nghĩa 1% request luôn chậm đúng bằng p99; nó là ngưỡng phân vị trong cửa sổ đo. Nên xem histogram hoặc heatmap để hiểu hình dạng phân bố.

### 2.2. Vì sao mean che giấu tail?

Giả sử 990 request hoàn thành trong 50 ms và 10 request mất 2 giây. Mean là:

\[
\frac{990 \times 50 + 10 \times 2000}{1000}=69.5\text{ ms}
\]

Trung bình 69.5 ms trông khá tốt, nhưng 1% người dùng vẫn chờ 2 giây. Với thao tác thanh toán, tìm kiếm hoặc xác nhận đặt chỗ, nhóm request chậm có thể tạo nhiều lần refresh, retry từ client hoặc bỏ dở giao dịch.

### 2.3. Percentile phải đi cùng cửa sổ và quy mô mẫu

p99 tính trên 100 request gần như chỉ phản ánh request chậm nhất; p99 trên hàng triệu request có độ ổn định khác. Khi đọc percentile, phải biết:

- Cửa sổ thời gian và số mẫu.
- Route/operation và region.
- Loại request, payload class hoặc tenant cohort nếu được phép.
- Cách histogram được merge giữa instance.
- Có sampling hoặc drop request hay không.

Không lấy trung bình p99 của từng instance để suy ra p99 toàn fleet. Cần merge histogram/bucket đúng cách hoặc dùng telemetry system có hỗ trợ percentile trên tập dữ liệu phù hợp.

## 3. Chuỗi gọi phân tán và critical path

### 3.1. Gọi nối tiếp

Một request có thể đi qua gateway, auth, booking service, inventory service và database theo trình tự. Với các bước thực sự nối tiếp, latency tổng gần bằng tổng thời gian từng bước cộng network/queue/serialization overhead.

~~~mermaid
flowchart LR
    C[Client] --> G[Gateway 12 ms]
    G --> A[Auth 18 ms]
    A --> B[Booking 35 ms]
    B --> I[Inventory 42 ms]
    I --> D[Database 28 ms]
    D --> R[Response]
~~~

Nếu tất cả giá trị đều nằm trên critical path, tổng thời gian xử lý phụ thuộc vào từng thành phần. Giảm 10 ms ở một bước nằm ngoài critical path có thể không thay đổi response time mà user nhìn thấy.

### 3.2. Gọi song song và fan-out

Nếu service gọi ba dependency song song và chỉ trả kết quả sau khi tất cả hoàn thành, thời gian của nhóm nhánh gần bằng thời gian của nhánh chậm nhất:

\[
T_{\text{fan-out}} \approx \max(T_1,T_2,\ldots,T_n)
\]

~~~mermaid
flowchart TD
    REQ[Request] --> P[Aggregator]
    P --> A[Inventory]
    P --> B[Pricing]
    P --> C[Availability]
    A --> JOIN[Join results]
    B --> JOIN
    C --> JOIN
    JOIN --> RESP[Response]
~~~

Fan-out giảm latency so với gọi tuần tự khi các nhánh độc lập, nhưng làm request phụ thuộc vào nhiều tail distribution hơn. Nếu một nhánh chậm, toàn bộ response chậm; nếu một nhánh fail và kết quả bắt buộc, cả request có thể thất bại.

### 3.3. Fan-out amplification

Giả sử mỗi dependency có xác suất 1% vượt một ngưỡng latency. Nếu request cần tất cả 20 dependency cùng hoàn thành và giả định các biến cố độc lập:

\[
P(\text{ít nhất một nhánh chậm})=1-(1-0.01)^{20}\approx18.2\%
\]

Như vậy dù từng dependency chỉ chậm 1% thời gian, gần 18.2% request tổng hợp có thể gặp ít nhất một nhánh chậm. Trong hệ thống thật, các lỗi thường có tương quan do chung region, network, database hoặc đợt traffic spike; giả định độc lập khi đó không còn đúng.

### 3.4. Quorum và partial response

Không phải request nào cũng cần chờ tất cả nhánh. Một search service có thể trả kết quả khi đủ số shard hoặc đủ quorum; dashboard có thể cho phép một widget lỗi mà phần còn lại hiển thị. Thiết kế partial response giảm phụ thuộc vào slowest branch, nhưng cần định nghĩa:

- Kết quả nào là bắt buộc và kết quả nào có thể thiếu.
- Số nhánh tối thiểu hoặc quorum.
- Cách đánh dấu dữ liệu chưa đầy đủ.
- Có thể trả stale/fallback result hay không.
- Cách tránh biến partial success thành dữ liệu nghiệp vụ sai.

Không được bỏ qua dependency bắt buộc chỉ để đạt latency. Ví dụ payment authorization hoặc inventory reservation có semantics nhất quán riêng.

## 4. Queueing, concurrency và utilization

### 4.1. Request time gồm service time và waiting time

Response time của một thao tác thường gồm thời gian chờ hàng đợi, thời gian thực thi và overhead khác:

\[
T_{\text{response}}=T_{\text{queue}}+T_{\text{service}}+T_{\text{network/overhead}}
\]

Một dependency có CPU xử lý nhanh vẫn có thể trả chậm nếu request chờ connection pool, worker thread, database lock, rate limit hoặc broker consumer slot.

### 4.2. Luật Little

Định luật Little mô tả quan hệ ở trạng thái ổn định:

\[
L=\lambda W
\]

Trong đó:

- \(L\): số request trung bình đang ở trong hệ thống (in-flight).
- \(\lambda\): throughput/arrival rate trung bình (request mỗi giây).
- \(W\): thời gian trung bình ở trong hệ thống (giây).

Ví dụ, nếu hệ thống nhận 500 request/giây và thời gian trung bình trong hệ thống là 0.2 giây, số request in-flight trung bình xấp xỉ 100. Đây là quan hệ hữu ích để ước lượng concurrency, nhưng không mô tả riêng tail distribution hoặc hành vi khi hệ thống không ổn định.

### 4.3. Utilization và tail latency

Khi utilization tăng gần giới hạn công suất, chỉ một burst nhỏ cũng làm queue tăng nhanh. Thời gian chờ có thể tăng nhanh hơn nhiều so với mức tăng traffic. Không có một ngưỡng utilization chung cho mọi hệ thống: workload CPU-bound, I/O-bound, lock-heavy và bursty có đặc tính khác nhau.

### 4.4. Connection pool và thread pool

Pool quá nhỏ làm request chờ slot; pool quá lớn có thể làm dependency bị quá tải do quá nhiều concurrent operation. Cần quan sát:

- Pool active/idle/waiting.
- Acquisition wait time và timeout.
- Database connection saturation.
- Worker queue depth và task age.
- Lock wait, transaction duration và retry.
- CPU, memory, network và IO saturation.

Tăng pool size chỉ hữu ích khi dependency còn capacity. Nếu DB đã bão hòa, mở thêm connection thường làm contention và tail latency tệ hơn.

## 5. Deadline và latency budget

### 5.1. Timeout riêng lẻ có thể cộng dồn

Nếu client timeout sau 2 giây nhưng service A có thể chờ dependency B 3 giây, service A vẫn tiếp tục công việc sau khi client đã bỏ request. Tài nguyên bị giữ cho thao tác không còn người chờ, làm queue tăng và tạo thêm tail latency.

### 5.2. Deadline end-to-end

Deadline là thời điểm cuối cùng mà kết quả còn có ích. Khi request đi qua các service, propagate deadline hoặc remaining time thay vì mỗi service tự đặt timeout độc lập không liên quan.

Ví dụ budget 800 ms:

| Thành phần | Budget gợi ý |
|---|---:|
| Gateway/auth | 80 ms |
| Booking service logic | 100 ms |
| Inventory dependency | 220 ms |
| Pricing dependency | 180 ms |
| Database/write | 140 ms |
| Serialization/network reserve | 80 ms |
| **Tổng** | **800 ms** |

Đây là ví dụ phân bổ, không phải quota mặc định. Cần đo percentile, concurrency, retry và network ở môi trường thực.

### 5.3. Remaining deadline

Trước khi gọi dependency, service tính remaining time. Timeout cho call mới không nên vượt quá remaining deadline sau khi trừ thời gian cần dành cho xử lý response và cleanup. Nếu remaining time quá nhỏ để có cơ hội thành công, service có thể từ chối sớm hoặc dùng fallback theo semantics.

### 5.4. Deadline propagation

Có thể truyền deadline bằng metadata RPC hoặc application header đã chuẩn hóa. Cần kiểm soát clock skew nếu truyền absolute timestamp; truyền remaining timeout có thể giảm phụ thuộc đồng hồ nhưng phải trừ elapsed time chính xác. Không tin deadline do client tùy ý gửi nếu nó vượt giới hạn server policy.

### 5.5. Cancellation

Khi caller timeout hoặc hủy request, cancellation nên lan tới operation con nếu an toàn. Database query, HTTP call và background task cần hỗ trợ cancel hoặc bounded execution. Không phải mọi thao tác có thể dừng ngay; transaction cần kết thúc theo semantics và đảm bảo không để side effect mơ hồ.

## 6. Retry có thể khuếch đại sự cố

### 6.1. Retry amplification

Khi dependency chậm, client hoặc service có thể retry. Request gốc vẫn đang chạy, request mới tạo thêm tải; tải tăng khiến dependency càng chậm và gây thêm retry. Đây là feedback loop nguy hiểm.

~~~mermaid
flowchart TD
    SPIKE[Traffic spike / dependency slow] --> QUEUE[Queue and latency rise]
    QUEUE --> TIMEOUT[Caller timeout]
    TIMEOUT --> RETRY[Retries increase]
    RETRY --> LOAD[More concurrent load]
    LOAD --> QUEUE
~~~

Nếu mỗi tầng trong chuỗi có retry riêng, số lần thử có thể nhân lên. Ví dụ 3 tầng, mỗi tầng thử tối đa 3 lần, worst-case số call tới dependency cuối có thể lên tới 27 trong một đường đi, tùy vị trí retry và semantics. Cần có retry budget toàn hệ thống hoặc quy định rõ tầng nào chịu trách nhiệm retry.

### 6.2. Chỉ retry lỗi tạm thời có thể phục hồi

Retry có thể phù hợp với throttling, connection reset hoặc một số 5xx. Không retry mù quáng lỗi validation, authorization, business conflict hoặc lỗi không thể khắc phục. Đặc biệt với thao tác ghi, cần idempotency key hoặc deduplication để tránh tạo giao dịch trùng.

### 6.3. Exponential backoff và jitter

Backoff tăng thời gian chờ giữa các lần thử; jitter ngẫu nhiên hóa thời điểm để các client không đồng loạt retry:

~~~text
delay = random(0, min(maxDelay, baseDelay * 2^attempt))
~~~

Phải giới hạn số lần retry và tổng thời gian retry trong deadline. Một số policy dùng full jitter; một số dùng equal/decorrelated jitter. Lựa chọn tùy workload và client library.

### 6.4. Retry budget

Giới hạn tỷ lệ retry so với request gốc hoặc giới hạn retry traffic trên dependency. Khi budget cạn, fail fast hoặc trả lỗi có kiểm soát thay vì tiếp tục tạo tải. Theo dõi retry rate, retry success rate, attempt count và timeout ratio.

## 7. Circuit breaker, bulkhead và load shedding

### 7.1. Circuit breaker

Circuit breaker ngăn gọi liên tục tới dependency đang lỗi:

- Closed: cho phép call bình thường và quan sát lỗi.
- Open: chặn call trong thời gian cool-down, trả fallback hoặc lỗi nhanh.
- Half-open: cho phép số probe giới hạn để kiểm tra phục hồi.

Circuit breaker giảm tải khi dependency lỗi nhưng có thể tạo gián đoạn giả nếu threshold/cooldown sai. Phải tránh mở circuit theo một lỗi đơn lẻ không đại diện và có cách quan sát trạng thái.

### 7.2. Bulkhead

Bulkhead cô lập tài nguyên giữa dependency hoặc nhóm workload. Ví dụ payment call dùng pool riêng với search call; tenant hoặc priority class được giới hạn concurrency riêng. Khi một dependency chậm, nó không chiếm hết worker/connection khiến các luồng khác ngừng hoạt động.

### 7.3. Load shedding

Khi hệ thống quá tải, từ chối một phần request trước khi queue và latency vượt ngưỡng có thể bảo vệ request quan trọng. Có thể shedding theo:

- Priority nghiệp vụ.
- Endpoint và cost class.
- Tenant quota/fairness.
- Remaining deadline.
- Request mới so với công việc đã bắt đầu.

Phản hồi overload cần giúp client backoff. Không nên trả 200 giả cho thao tác chưa thực hiện.

### 7.4. Admission control và concurrency limit

Giới hạn số operation in-flight hoặc số request được nhận. So với rate limit, concurrency limit thích ứng tốt hơn khi service time biến động: request chậm giữ slot lâu, hệ thống tự giảm lượng request mới. Tuy vậy, cần cấu hình fairness và queue bound; queue không giới hạn chỉ chuyển overload thành latency vô tận.

## 8. Hedged requests và speculative execution

### 8.1. Ý tưởng

Hedged request gửi một bản gọi phụ tới replica khác khi request đầu vượt một ngưỡng latency; dùng kết quả hợp lệ đầu tiên và hủy phần còn lại nếu an toàn. Cách này có thể giảm tail latency khi replica có latency độc lập và còn dư capacity.

~~~mermaid
sequenceDiagram
    participant A as Caller
    participant R1 as Replica 1
    participant R2 as Replica 2
    A->>R1: Request
    Note over A,R1: Wait hedge threshold
    A->>R2: Hedged request
    R2-->>A: Result first
    A->>R1: Cancel if supported
~~~

### 8.2. Điều kiện phù hợp

- Operation chủ yếu là read hoặc có semantics idempotent.
- Có nhiều replica độc lập về failure/latency.
- Replica có đủ spare capacity.
- Có thể hủy request thua cuộc hoặc giới hạn công việc phát sinh.
- Hedge threshold dựa trên latency distribution, không phải giá trị tùy tiện.

Không hedge write không idempotent như charge payment hoặc create order nếu không có protocol deduplication. Nếu mọi caller cùng hedge khi dependency chậm, tải bổ sung có thể làm sự cố nặng hơn.

### 8.3. Tối ưu threshold

Threshold quá thấp khiến hầu hết request tạo duplicate work; quá cao thì không đủ giảm tail. Cần đo hedge rate, win rate, duplicate request load, cancellation success và p99 end-to-end. Có thể chỉ bật theo endpoint và khi capacity headroom còn.

## 9. Caching, coalescing và stale response

### 9.1. Cache giảm dependency calls

Cache giúp giảm latency và tải DB/service cho dữ liệu có thể tái sử dụng. Tuy nhiên, cache miss burst, key nóng hết hạn hoặc cache outage có thể làm request đồng loạt rơi về backend.

### 9.2. Request coalescing

Gộp các request đồng thời có cùng cache key thành một lookup nguồn duy nhất. Các caller khác chờ chung kết quả, giảm duplicate work. Phải giới hạn thời gian chờ và xử lý lỗi để không giữ cả nhóm request quá lâu.

### 9.3. Stale-while-revalidate

Với dữ liệu cho phép eventual consistency, có thể trả bản cache cũ trong một giới hạn và cập nhật nền. Điều này giảm tail khi backend chậm. Không dùng cho dữ liệu cần chính xác tức thời như available inventory, payment status hoặc quyền truy cập nếu semantics không cho phép.

### 9.4. Cache stampede và negative caching

TTL jitter, single-flight, prewarming và stale policy có thể giảm stampede. Negative caching có thể tránh lookup lặp cho key không tồn tại, nhưng cần TTL/invalidation và giới hạn cardinality. Mỗi biện pháp có trade-off freshness và memory.

## 10. Bounded queues và backpressure

### 10.1. Queue không tạo thêm capacity

Queue hấp thụ burst nhưng không làm hệ thống xử lý nhanh hơn. Nếu arrival rate lâu dài cao hơn service rate, queue tăng không giới hạn và tail latency ngày càng lớn.

### 10.2. Bounded queue

Đặt giới hạn chiều dài hoặc tuổi message; khi đạt ngưỡng, từ chối, shed load hoặc điều tiết producer. Alert nên theo oldest message age và queue growth rate, không chỉ queue depth.

### 10.3. Backpressure

Consumer có thể giảm tốc độ nhận message hoặc broker pause delivery khi downstream không đủ capacity. Producer có thể nhận tín hiệu và giảm tốc độ. Backpressure hiệu quả khi truyền được qua các tầng; nếu một tầng âm thầm đệm vô hạn thì latency chỉ chuyển chỗ.

### 10.4. Queue latency và user-facing latency

Với asynchronous workflow, HTTP request có thể trả nhanh sau khi enqueue, nhưng nghiệp vụ chỉ hoàn tất khi consumer xử lý xong. Đo cả enqueue response latency, queue age, processing duration và end-to-end completion time. Không coi API nhanh là workflow đã nhanh.

## 11. Đo tail latency và bottleneck

### 11.1. Histogram thay vì chỉ average

Histogram cho phép tính percentile và phân tích phân bố ở nhiều cửa sổ. Chọn bucket phù hợp latency SLO; ghi đơn vị nhất quán (ms hoặc s). Không merge percentile đã tính từ từng instance bằng phép lấy trung bình.

### 11.2. RED và USE

RED cho service request:

- Rate: số request/giây.
- Errors: số/tỷ lệ request lỗi.
- Duration: phân bố latency.

USE cho resource:

- Utilization: mức sử dụng.
- Saturation: mức xếp hàng/chờ.
- Errors: lỗi thiết bị hoặc resource.

Kết hợp RED với USE giúp phân biệt service chậm do code/dependency hay do CPU, memory, disk, connection pool hoặc queue.

### 11.3. Distributed tracing

Trace cho thấy span nằm trên critical path và dependency nào chiếm thời gian. Với fan-out, nhìn nhánh chậm nhất; với call chain, tìm span dài và waiting time. Cần phân biệt client-side wait, server processing và queue delay; một span cha dài không có nghĩa code của service cha tự tiêu tốn toàn bộ thời gian.

### 11.4. Metric theo dependency

Theo dõi latency/error/timeout theo dependency, operation, region và result class. Không dùng raw user ID, request ID hoặc arbitrary URL làm metric label vì cardinality quá cao. ID cụ thể để trong trace/log có kiểm soát.

### 11.5. Percentile aggregation

Nếu dùng histogram bucket, percentile nên tính trên tập observation gộp đúng bucket. Với histogram có bucket boundaries thống nhất, có thể cộng bucket counts rồi tính quantile. Với summary percentile cục bộ, thường không thể merge chính xác percentile thành percentile toàn fleet.

## 12. Load testing và tail behavior

### 12.1. Test theo open-loop và closed-loop

- Closed-loop client gửi request tiếp theo sau khi nhận response. Khi service chậm, tốc độ phát request tự giảm; có thể che khuất overload.
- Open-loop generator phát request theo lịch độc lập với response. Nó mô phỏng arrival rate cố định tốt hơn nhưng có thể tạo queue lớn nếu hệ thống không kịp xử lý.

Nên chọn mô hình phù hợp hành vi người dùng và kiểm tra cả hai khi cần. Tránh coordinated omission: load generator không ghi nhận những request lẽ ra đã được gửi trong lúc đang chờ response chậm.

### 12.2. Kịch bản cần thử

- Steady-state ở nhiều mức load.
- Burst ngắn và sustained overload.
- Một dependency tăng latency hoặc trả 5xx.
- Queue consumer giảm capacity hoặc restart.
- Database pool gần cạn và lock contention.
- Cache cold start/flush.
- Region/network degradation.
- Retry storm và client reconnect.

### 12.3. Đo p50, p95, p99 và throughput cùng nhau

Tăng concurrency có thể làm throughput tăng cho tới một điểm, sau đó queue và tail latency tăng mạnh. Chỉ nhìn throughput có thể kết luận sai rằng hệ thống tốt hơn. Ghi cả error rate, rejected requests, saturation và resource cost.

## 13. Tối ưu critical path

### 13.1. Rút ngắn dependency chain

Nếu request cần ba lần gọi nối tiếp tới cùng một service, xem xét gộp API, batch hoặc precompute để giảm round trip. Đánh đổi là coupling, payload size và ownership.

### 13.2. Parallelize phần độc lập

Có thể chạy authz lookup, catalog lookup hoặc computation độc lập song song. Tuy nhiên, fan-out tăng tải tức thời và phụ thuộc vào slowest branch. Cần concurrency cap và deadline.

### 13.3. Giảm work trên synchronous path

Chuyển tác vụ không cần trả ngay (email, analytics, search indexing) sang asynchronous workflow. Đo end-to-end completion riêng và xử lý eventual consistency rõ ràng.

### 13.4. Giảm serialization và payload

Payload lớn làm tăng encode/decode, network transfer và memory pressure. Chỉ truyền field cần thiết, dùng pagination/streaming khi hợp lý và tránh N+1 dependency calls.

### 13.5. Co-locate và locality

Đặt service/data gần nhau về network hoặc region có thể giảm RTT. Nhưng locality phải tôn trọng data residency, failure domain, replication và disaster recovery. Co-locate mọi thứ trong một zone có thể giảm latency nhưng tăng blast radius.

## 14. Công thức và ví dụ latency budget

### 14.1. Sequential chain

Nếu request gọi nối tiếp ba dependency:

\[
T_{\text{total}} \approx T_A+T_B+T_C+T_{\text{local}}
\]

Ví dụ latency một lần đo: local 25 ms, A 40 ms, B 70 ms, C 35 ms; tổng khoảng 170 ms cộng overhead. Tuy nhiên p99 tổng không bằng tổng p99 một cách tổng quát nếu phân bố/tương quan khác nhau; dùng trace và đo end-to-end để xác nhận.

### 14.2. Fan-out

Nếu request chờ tất cả ba nhánh song song:

\[
T_{\text{total}} \approx T_{\text{setup}}+\max(T_A,T_B,T_C)+T_{\text{join}}
\]

Nếu chỉ cần hai trong ba kết quả, thời gian phụ thuộc vào nhánh hoàn thành thứ hai (second-fastest), nhưng semantics partial result phải được chấp nhận rõ.

### 14.3. Latency budget phải có reserve

Đừng phân bổ hết deadline cho dependency. Cần reserve cho serialization, scheduling delay, network variance, response encoding và cancellation. Timeout ở dependency cuối phải ngắn hơn remaining deadline; nếu không, caller đã hết thời gian nhưng service vẫn giữ tài nguyên.

### 14.4. p99 của fan-out

Với n nhánh độc lập và mỗi nhánh có xác suất q vượt một ngưỡng, xác suất ít nhất một nhánh vượt ngưỡng là:

\[
1-(1-q)^n
\]

Khi n tăng, tail của aggregator xấu đi ngay cả khi mỗi dependency không đổi. Đây là lý do cần giảm số nhánh bắt buộc, dùng quorum/fallback hợp lệ hoặc cải thiện tail của dependency.

## 15. Kiến trúc ví dụ: trang booking tổng hợp

Giả sử trang chi tiết booking cần:

- Booking record từ database.
- Availability từ inventory service.
- Giá từ pricing service.
- User entitlement từ identity/profile.
- Recommendation từ ML service.

### 15.1. Phân loại dependency

| Dependency | Có bắt buộc? | Cách xử lý khi chậm |
|---|---|---|
| Booking record | Có | Deadline rõ; lỗi thì không hiển thị booking |
| Authorization | Có | Fail closed hoặc policy fallback được phê duyệt |
| Availability | Có với thao tác đặt | Read-only display có thể hiển thị trạng thái chưa xác nhận |
| Pricing | Có trước xác nhận giá | Có thể dùng quote cache còn hiệu lực nếu policy cho phép |
| Recommendation | Không | Timeout ngắn, bỏ kết quả hoặc trả stale |

### 15.2. Flow

~~~mermaid
flowchart TD
    REQ[GET booking page] --> CORE[Load booking and authorize]
    CORE --> PAR[Parallel enrichment]
    PAR --> INV[Inventory]
    PAR --> PRICE[Pricing]
    PAR --> REC[Recommendation]
    INV --> JOIN[Join by policy]
    PRICE --> JOIN
    REC --> JOIN
    JOIN --> RESP[Build response]
    RESP --> METRIC[Record latency and completeness]
~~~

Recommendation có thể có timeout thấp và không chặn response. Inventory/pricing cần policy theo trạng thái nghiệp vụ: hiển thị dữ liệu tham khảo không đồng nghĩa cho phép commit booking. Khi người dùng xác nhận, backend cần kiểm tra lại giá và availability trong transaction/workflow phù hợp.

### 15.3. Ngân sách minh họa

Với deadline 600 ms, có thể dành 80 ms cho gateway/auth, 120 ms cho core booking, tối đa 250 ms cho nhóm enrichment song song, 70 ms cho response và 80 ms reserve. Nhánh recommendation có thể được timeout ở 100 ms và không chặn join. Các con số phải được đo theo p95/p99 và workload thực.

### 15.4. Điều kiện rollout

- p95/p99 end-to-end trong SLO.
- Inventory/pricing error không vượt ngưỡng.
- Recommendation timeout không kéo theo timeout toàn request.
- DB connection pool và downstream concurrency còn headroom.
- Timeout/retry không làm tăng request amplification.
- Completeness/partial response được đo và phù hợp semantics.

## 16. Sai lầm thường gặp

| Sai lầm | Hệ quả | Cách cải thiện |
|---|---|---|
| Chỉ tối ưu average latency | Tail của nhóm người dùng bị bỏ qua | Theo dõi histogram và p95/p99/p99.9 |
| Fan-out tới quá nhiều dependency bắt buộc | Xác suất ít nhất một nhánh chậm tăng | Giảm nhánh, quorum hoặc partial response hợp lệ |
| Timeout từng service độc lập | Tổng deadline bị vượt, tài nguyên tiếp tục chạy | Propagate deadline/remaining time và cancellation |
| Retry ở mọi tầng | Retry amplification và overload | Retry budget, backoff, jitter và một tầng chịu trách nhiệm |
| Retry write không idempotent | Giao dịch/trừ tiền trùng | Idempotency key và deduplication |
| Tăng connection pool khi DB bão hòa | Contention và queue tăng | Đo saturation, giới hạn concurrency, tối ưu query |
| Queue không giới hạn | Latency tăng vô hạn khi arrival vượt service rate | Bounded queue, backpressure và load shedding |
| Hedge mọi request | Duplicate load làm dependency tệ hơn | Chỉ hedge phù hợp, threshold đo được và capacity guard |
| Chỉ nhìn processing time của consumer | Bỏ qua queue age | Đo oldest message age và end-to-end completion |
| Dùng percentile cục bộ rồi lấy trung bình | Sai percentile toàn fleet | Merge histogram/bucket đúng cách |
| Load test closed-loop duy nhất | Che khuất overload và coordinated omission | Bổ sung open-loop và workload model phù hợp |
| Trả stale data không phân biệt | Nghiệp vụ có thể ra quyết định sai | Policy freshness theo loại dữ liệu |

## 17. Đánh giá theo Well-Architected

| Trụ cột | Câu hỏi | Biện pháp và đánh đổi |
|---|---|---|
| **Operational Excellence** | Có quan sát được critical path, queue và dependency latency không? | Tracing, histogram, dashboard, runbook; cần chuẩn hóa instrumentation |
| **Security** | Load shedding, cache và fallback có bỏ qua authorization không? | Authz vẫn nằm trên critical path, fail closed và kiểm soát stale data |
| **Reliability** | Hệ thống chịu được dependency chậm, timeout và overload ra sao? | Deadline, retry budget, circuit breaker, bulkhead và backpressure |
| **Performance Efficiency** | Có giảm round trip, queue wait và fan-out không cần thiết? | Parallelize hợp lý, batching, locality và pool tuning |
| **Cost Optimization** | Có đang trả chi phí cho duplicate calls, hedge và capacity dư? | Capacity headroom có chủ đích, cache/coalescing và retry control |
| **Sustainability** | Có thực hiện công việc lặp do retry hoặc polling quá mức? | Event-driven update, bounded retry, backoff và load shedding |

Tối ưu tail latency là bài toán liên kết giữa performance và reliability. Một hệ thống phản hồi nhanh bằng cách bỏ qua kiểm tra bắt buộc hoặc tạo quá nhiều duplicate work không phải là kiến trúc tốt.

## 18. Bài tập áp dụng

### Bài tập A — Mean đẹp, p99 xấu

API có mean 70 ms, p50 45 ms, p99 900 ms. Nhóm đề xuất tối ưu thêm 5 ms ở median.

**Câu hỏi:** Nên điều tra gì trước?

**Gợi ý:** Xem histogram/trace của slow request, dependency, queue wait, connection pool, GC, region và retry. Tối ưu median 5 ms chưa chắc cải thiện tail.

### Bài tập B — Fan-out 30 dependency

Aggregator chờ 30 service; mỗi service có 0.5% xác suất vượt 500 ms. Giả sử độc lập.

**Câu hỏi:** Xác suất ít nhất một nhánh vượt 500 ms là bao nhiêu?

**Gợi ý:** Tính 1 - 0.995^30, xấp xỉ 14%. Giả định độc lập chỉ để minh họa; common-mode failure làm kết quả khác.

### Bài tập C — Deadline bị vượt

Gateway timeout ở 1 giây nhưng downstream service có timeout riêng 2 giây.

**Câu hỏi:** Hệ quả và cách thiết kế lại?

**Gợi ý:** Downstream tiếp tục giữ connection/worker sau khi caller bỏ. Propagate deadline, tính remaining time, cancel call khi caller timeout và giới hạn cleanup.

### Bài tập D — Retry storm

Ba tầng service đều retry tối đa ba lần khi nhận timeout.

**Câu hỏi:** Tại sao hệ thống có thể tạo nhiều call hơn request ban đầu?

**Gợi ý:** Retry nhân qua từng tầng, gây amplification; chỉ định tầng retry, bounded attempts, backoff+jitter, retry budget và idempotency.

### Bài tập E — Cache và freshness

Recommendation service chậm nhưng dữ liệu có thể stale vài phút; inventory service chậm nhưng cần chính xác khi commit.

**Câu hỏi:** Có thể dùng cùng fallback policy không?

**Gợi ý:** Không. Recommendation có thể dùng stale cache hoặc bỏ qua; inventory ở bước commit phải xác minh nguồn có thẩm quyền và không được chấp nhận stale availability.

### Bài tập F — Hedged request

Read replica thứ hai còn capacity, nhưng write endpoint không idempotent.

**Câu hỏi:** Nên hedge operation nào?

**Gợi ý:** Chỉ xem xét read có semantics phù hợp và replica đủ độc lập; không hedge write tạo side effect nếu chưa có deduplication/protocol an toàn.

## 19. Checklist trước khi tối ưu tail latency

- [ ] SLO latency được định nghĩa theo endpoint/operation và percentile phù hợp.
- [ ] Histogram có bucket phù hợp, đủ mẫu và có cách merge đúng trên toàn fleet.
- [ ] Trace thể hiện critical path, dependency span, queue wait và retry.
- [ ] Fan-out/fan-in được phân loại theo dependency bắt buộc/tùy chọn.
- [ ] Partial response/quorum có semantics nghiệp vụ rõ.
- [ ] Có latency budget end-to-end và deadline propagation.
- [ ] Timeout/cancellation được áp dụng xuyên các dependency.
- [ ] Retry chỉ cho lỗi phù hợp, có backoff, jitter, attempt cap và retry budget.
- [ ] Write retry có idempotency/deduplication.
- [ ] Connection/thread pool có metric active, waiting và saturation.
- [ ] Queue có bound, oldest-message-age alert và backpressure.
- [ ] Circuit breaker/bulkhead/load shedding có threshold và runbook.
- [ ] Hedged request chỉ áp dụng cho operation phù hợp và có capacity guard.
- [ ] Cache coalescing/stale policy tuân theo freshness và authorization.
- [ ] Metrics phân biệt processing duration với queue age/end-to-end completion.
- [ ] Load test có steady, burst, overload, dependency failure và open-loop phù hợp.
- [ ] Theo dõi p50/p95/p99 cùng throughput, error và saturation.
- [ ] Có dashboard/alert theo dependency và region, không tạo cardinality vô hạn.
- [ ] Đo chi phí duplicate calls, extra capacity và telemetry sau tối ưu.
- [ ] Mọi thay đổi đã được kiểm tra bằng workload và SLO thực tế.

**Điểm cốt lõi:** tail latency thường xuất hiện ở cấp chuỗi gọi chứ không chỉ một service. Fan-out làm request phụ thuộc vào nhánh chậm nhất; queueing tăng mạnh khi utilization gần giới hạn; retry thiếu kiểm soát có thể biến chậm thành quá tải. Hãy đo percentile và critical path, truyền deadline, giới hạn concurrency/queue, dùng retry budget và fallback theo semantics. Mục tiêu là giữ trải nghiệm end-to-end trong SLO mà không làm dependency yếu hơn hoặc hy sinh tính đúng đắn nghiệp vụ.
