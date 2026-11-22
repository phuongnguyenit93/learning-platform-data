# Theo dõi timeout, retry, lỗi có điều kiện và tỷ lệ ghi không rõ kết quả

## 1. Một lệnh ghi bị timeout có nghĩa là thất bại hay đã thành công?

Giả sử một ứng dụng Java dùng NoSQL để tạo đơn hàng:

~~~text
t0 Client gửi CreateOrder(operationId=OP-101, orderId=O101).
t1 NoSQL nhận yêu cầu, kiểm tra điều kiện và commit bản ghi.
t2 Response "success" bị mất do kết nối mạng đứt.
t3 Java driver trả timeout.
t4 Ứng dụng ghi log "CreateOrder failed", rồi retry với orderId=O102.
t5 NoSQL lưu thêm O102.
~~~

Từ góc nhìn **client**, request đầu bị timeout. Từ góc nhìn **storage**, O101 đã được commit. Từ góc nhìn **nghiệp vụ**, một lần nhấn nút tạo đơn có thể dẫn đến hai đơn.

Nếu hệ thống chỉ theo dõi số HTTP 500 hay số timeout của driver, không ai biết request nào đã thực sự tạo ra side effect. Nếu chỉ theo dõi “write success” tại server, lại không nhìn thấy khách hàng nhận lỗi và retry. Đây là lý do phải quan sát cả **kết quả logic**, **mỗi attempt truyền qua mạng** và **trạng thái commit có thể hoặc chưa thể xác minh**.

Bài học nằm trong module **Database No SQL**, chương **Quan sát và chẩn đoán**. Chủ đề chính là cách theo dõi và xử lý bốn tín hiệu dễ bị gộp sai: **timeout**, **retry**, **lỗi có điều kiện** và **ghi không rõ kết quả**.

### Mục tiêu

Sau bài học, bạn có thể:

1. Phân biệt lỗi trước khi gửi request, lỗi khi đang gửi, timeout sau khi backend có thể đã commit và lỗi được backend xác nhận.
2. Định nghĩa logical operation, request attempt, retry, accepted write, committed write và unknown outcome.
3. Thiết kế metric theo **đúng mẫu số**, không nhầm số attempt với số hành động nghiệp vụ.
4. Phân loại conditional conflicts thành tranh chấp dự kiến, lỗi dữ liệu nghiệp vụ hoặc contention bất thường.
5. Theo dõi retry amplification, backoff, deadline và tác động của retry storm đến NoSQL.
6. Dùng idempotency, operation status, version, unique claim và reconciliation để xử lý unknown commits.
7. Thiết kế log, trace, metric, dashboard, alert và runbook chẩn đoán.
8. Vận dụng với MongoDB, DynamoDB, Cassandra/ScyllaDB, Redis và các kiến trúc CDC/outbox.
9. Thực hiện test lỗi mạng, delayed ACK, response loss và fault injection mà không suy nhầm timeout thành rollback.

## 2. Từ vựng phải dùng chính xác

| Thuật ngữ | Định nghĩa trong bài | Điều không thể suy ngay |
|---|---|---|
| Logical operation | Một ý định nghiệp vụ, ví dụ tạo Order O101 | Không nhất thiết tương ứng một network call |
| Attempt | Một lần gửi request xuống driver/backend | Không nhất thiết tạo một side effect mới |
| Retry | Attempt khác nhằm tiếp tục cùng logical operation | Không tự idempotent |
| Timeout | Một thời hạn chờ đã hết | Không tự chứng minh commit thất bại |
| Conditional failure | Một điều kiện/constraint không thỏa theo phản hồi xác định | Không nhất thiết là lỗi hệ thống |
| Definite rejection | Backend xác nhận không áp dụng mutation theo contract | Không bao hàm mọi timeout |
| Known committed | Có bằng chứng commit theo durability/consistency contract | Không tự đảm bảo mọi replica/index đã thấy |
| Unknown outcome | Không đủ bằng chứng mutation đã hoặc chưa commit | Không đồng nghĩa FAILED |
| Reconciliation | Xác minh trạng thái từ nguồn có thẩm quyền sau khi outcome mơ hồ | Không phải blind retry |
| Idempotency key | Định danh ổn định cho cùng logical intention | Không thay unique business key |

### 2.1. Một business operation có thể tạo nhiều requests

~~~text
POST /orders
  -> check idempotency claim
  -> conditional insert Order
  -> append outbox entry
  -> query operation status after timeout
~~~

Không nên gọi bốn requests này là bốn đơn hàng. Tùy transaction design, một business operation có thể cần nhiều DB calls và nhiều attempts.

### 2.2. Backend “success” cần ghi rõ loại bảo đảm

Thành công ở một mức write acknowledgment không tự đồng nghĩa:

- Đã được replicated tới mọi Region.
- Đã visible qua secondary index.
- Đã bền vững qua mọi failure mode.
- Đã hoàn tất side effects ở downstream services.

Log và SLO phải gắn với acknowledgement/transaction semantics thực tế.

### 2.3. Lỗi HTTP và lỗi database không có ánh xạ một-một

Backend trả conditional failure có thể được API chuyển thành HTTP 409. Backend timeout có thể được API trả 503, 504 hoặc trạng thái PENDING/UNKNOWN tùy protocol. Không chỉ dựa trên HTTP status khi điều tra storage behavior.

## 3. Sơ đồ một lần ghi và các điểm có thể đứt

~~~mermaid
sequenceDiagram
    participant C as Java Client
    participant N as Network
    participant DB as NoSQL Authority
    C->>N: Send write attempt #1
    N->>DB: Request bytes
    DB->>DB: Validate condition, apply and commit
    DB-->>N: ACK success
    Note over N: ACK bị mất / kết nối đứt
    N--xC: Client deadline exceeded
    C->>DB: Lookup operationId on authoritative path
    DB-->>C: COMMITTED, revision 8
    Note over C: Return previous result, avoid duplicate creation
~~~

### 3.1. Failure trước khi request được gửi

Ví dụ input validation từ chối trước khi gọi database. Có thể kết luận mutation **không được gửi qua đường này**, dù vẫn cần xét các background workflows khác.

### 3.2. Failure trước khi backend nhận đủ request

Nếu client chắc chắn socket không mở hoặc request chưa được phát, retry có thể an toàn hơn. Tuy nhiên, nhiều network exceptions không cung cấp bằng chứng mạnh như vậy; ghi nhận *not sent* chỉ khi driver/application thực sự biết.

### 3.3. Failure trong lúc backend xử lý

Backend có thể chưa áp dụng mutation, đã áp dụng một phần theo transaction boundary, hoặc đã commit. Client không được kết luận dựa trên thời gian chờ một mình.

### 3.4. Response loss sau commit

Đây là trường hợp quan trọng nhất của **unknown write outcome**. Một retry không-idempotent có thể tạo thêm order, trừ tiền nhiều lần hoặc tăng counter lặp.

### 3.5. Backend trả conditional rejection rõ ràng

Ví dụ DynamoDB trả ConditionalCheckFailedException cho một PutItem có condition. Theo contract, request này không ghi item ở bước conditional mutation đó. Nhưng nó **không tự nói** một attempt trước đã hoặc chưa commit cùng operationId.

### 3.6. Failure sau ACK thành công

Ngay cả khi source write đã được xác nhận, cache invalidation hoặc event publishing có thể thất bại. Nên theo dõi như một trạng thái riêng của downstream projection, không sửa metric source commit thành “failed” tùy tiện.

## 4. Mô hình trạng thái cho một logical write

Một state machine hữu ích:

~~~mermaid
flowchart TD
    A["RECEIVED"] --> B["IN_PROGRESS"]
    B --> C["COMMITTED"]
    B --> D["DEFINITELY_REJECTED"]
    B --> E["UNKNOWN_OUTCOME"]
    E --> F["RECONCILING"]
    F --> C
    F --> D
    F --> G["UNRESOLVED"]
    G --> F
~~~

### 4.1. COMMITTED

Có bằng chứng nguồn đã lưu kết quả cho cùng operationId theo transaction/consistency contract đã định nghĩa.

### 4.2. DEFINITELY_REJECTED

Lệnh bị chặn trước commit do validation hoặc condition xác định. Chỉ dùng trạng thái này nếu có bằng chứng request đã bị từ chối và không có attempt trước mang outcome chưa rõ.

### 4.3. UNKNOWN_OUTCOME

Client không đủ bằng chứng; không được đổi thẳng sang FAILED chỉ vì chờ quá lâu.

### 4.4. UNRESOLVED

Sau một số lần reconciliation/đến deadline nghiệp vụ vẫn chưa quyết định được. Có thể cần manual intervention hoặc cơ chế tiếp tục kiểm tra; không tuyên bố committed hay failed theo suy đoán.

### 4.5. FAILED không phải trạng thái duy nhất

Nếu hệ vẫn muốn có FAILED, cần định nghĩa rõ: failed before submission, definite business rejection, hoặc failed to deliver response. Ba khái niệm này khác nhau về có thể retry và duplicate side effect.

### 4.6. API nên bảo toàn sự mơ hồ khi thực sự có mơ hồ

Một API có thể trả operationId với trạng thái đang xử lý/không xác định và cung cấp endpoint kiểm tra. Không bắt buộc mọi API dùng cùng HTTP status, nhưng **không hứa “không có dữ liệu” khi backend chưa chứng minh điều đó**.

## 5. Timeout có nhiều loại

| Timeout | Điểm chạm | Điều cần theo dõi |
|---|---|---|
| Connect timeout | Mở kết nối TCP/TLS | Attempt có được gửi không? |
| Socket/read timeout | Đọc response từ kết nối | Backend có thể đã xử lý |
| Server selection/discovery timeout | Tìm node/coordinator | Request có được dispatch? |
| Driver per-attempt timeout | Một lần RPC/statement | Số attempts và retry budget |
| End-to-end request deadline | Toàn API/business operation | Thời gian còn lại để retry/reconcile |
| Queue/acquire timeout | Đợi connection hoặc thread | Backend có thể chưa được gọi |
| Transaction deadline | Transaction hết thời hạn | Semantics commit/abort cụ thể |
| Upstream HTTP timeout | Client gọi service | Service vẫn có thể tiếp tục xử lý |

### 5.1. Cần phân biệt cấu hình timeout và quan sát timeout

Timeout cấu hình 1 giây không có nghĩa backend mất đúng 1 giây xử lý. Nó có thể bao gồm queueing, connection acquisition, network, serialization và server processing.

### 5.2. Cancellation không chắc rollback

Java CompletableFuture.cancel(true), HTTP connection close hoặc caller timeout không tự có nghĩa database đã nhận cancel và rollback write. Cần biết protocol và trạng thái nguồn.

### 5.3. Per-attempt timeout ngắn hơn business deadline

Ví dụ:

~~~text
API deadline:         3,000 ms
First DB attempt:      700 ms
Backoff with jitter:   100 ms
Second attempt:        700 ms
Reconciliation budget: 800 ms
Response budget:       phần còn lại
~~~

Đây là minh họa; thực tế budget phải tính network, queue, serialization, retry caps và minimum time cho status lookup.

### 5.4. Không xếp timeout thành retryable tự động

Một timeout của **idempotent GET** có thể retry khi budget còn. Một timeout của **non-idempotent write** phải phân tích rủi ro side effect trước khi retry.

## 6. Phân loại failure trước khi ghi metric

Một taxonomy có thể có:

~~~text
REQUEST_VALIDATION_ERROR
AUTHENTICATION_OR_AUTHORIZATION_DENIED
CONDITIONAL_CONFLICT_EXPECTED
CONDITIONAL_CONFLICT_UNEXPECTED
THROTTLED
BACKEND_UNAVAILABLE
NETWORK_TIMEOUT
CLIENT_DEADLINE
TRANSIENT_SERVER_ERROR
SCHEMA_OR_SERIALIZATION_ERROR
WRITE_OUTCOME_UNKNOWN
KNOWN_COMMITTED
KNOWN_REJECTED
~~~

### 6.1. Không trộn conflict business với availability

Một request đặt unique username đã được sở hữu có thể nhận conflict đúng thiết kế. Nếu 30% username registrations bị trùng, đây chưa chắc là database outage.

### 6.2. Nhưng conflict cũng có thể chỉ ra lỗi

Conditional conflicts tăng đột biến trên một counter/cùng partition có thể là contention hoặc retry storm. Cần phân loại **expected vs unexpected** theo use case.

### 6.3. Throttling khác conditional failure

DynamoDB throttling hoặc Redis/driver backpressure có ý nghĩa tải/capacity. Không gộp với “condition not met”, vì hành động khắc phục khác nhau.

### 6.4. Driver-specific error mapping

Các thư viện Java dùng exception classes và retry behavior khác nhau theo phiên bản. Khi triển khai, lập bảng mapping từ **mã/exception có thật** tới taxonomy ổn định của application; không viết catch(Exception) rồi mặc định timeout.

## 7. “Một phép ghi” phải được định danh xuyên mọi retry

Giả sử một logical create:

~~~json
{
  "operationId": "CREATE-O101-CLIENT7",
  "orderId": "O101",
  "tenantId": "T17",
  "payloadHash": "hash-of-canonical-business-payload"
}
~~~

Nên lưu operationId/tenant scope cùng result hoặc một idempotency record có authoritative durability thích hợp.

### 7.1. Stable operationId

Retry dùng **cùng** operationId. Nếu mỗi attempt tạo operationId mới, backend khó biết chúng là một ý định.

### 7.2. Idempotency và business key khác nhau

Unique orderId ngăn hai records cùng ID, nhưng không ngăn một lần nhấn “Tạo đơn” bị retry với orderId khác. Idempotency key nhận diện ý định; unique business key nhận diện thực thể.

### 7.3. Payload mismatch

Hai requests cùng operationId nhưng payload khác nên bị từ chối như misuse/conflict theo contract. Không âm thầm trả kết quả cũ cho một thao tác khác nội dung.

### 7.4. Result retention

Idempotency record cần giữ đủ lâu cho retry horizon và các failure windows. Nếu TTL record ngắn hơn retry từ mobile app hoặc message broker, duplicate effect có thể xuất hiện sau khi key bị xóa.

### 7.5. Scope và quyền truy cập

OperationId nên được scoped theo tenant/account và kiểm tra authorization. Một caller không được dùng key của người khác để nhìn kết quả hoặc chặn thao tác.

## 8. Logical operations khác physical attempts

Ví dụ:

~~~text
Logical CREATE operations: 1,000
First attempts:           1,000
Retry attempts:             180
Physical attempts:        1,180
Known committed:            960
Known rejected:              25
Still unknown:               15
~~~

Trong đó:

\[
\text{AttemptsPerLogicalOp}
=\frac{1{,}180}{1{,}000}=1.18.
\]

### 8.1. Retry amplification

\[
A_\text{retry}=
\frac{\text{all physical attempts}}
{\text{logical operations initiated}}.
\]

Ở kịch bản không retry và mỗi operation đúng một attempt, A=1. Nếu ứng dụng có intentional multi-step writes, cần tính amplification **theo một loại DB call cụ thể** thay vì lấy tất cả internal requests chia số đơn hàng rồi gọi đó là retry amplification.

### 8.2. Retry fraction

\[
R_\text{attempt}=
\frac{\text{retry attempts}}{\text{all attempts}}
=\frac{180}{1180}\approx15.25\%.
\]

Tỷ lệ trên không giống tỷ lệ operations từng phải retry:

\[
R_\text{logical}=
\frac{\text{logical operations with >=1 retry}}
{\text{all logical operations}}.
\]

Nếu một operation bị retry 10 lần, 10 attempts đó không được tính là 10 logical operations.

### 8.3. Không cộng successes theo attempts thành business throughput

Một attempt #1 đã commit nhưng ACK mất; attempt #2 thấy idempotency record và trả result cũ. Hai requests có thể được ghi nhận là “successful RPC” theo vài bộ đo, nhưng **chỉ một Order được tạo**.

### 8.4. Metric cần có hai lớp

Lớp **business**: one logical operation, one final status.

Lớp **transport/driver**: attempt count, retry count, latency per attempt, timeout/throttle/error type.

### 8.5. Correlation IDs

Gắn operationId và traceId qua retries; mỗi attempt có attemptNumber và span riêng, giúp nhìn một operation bị retry ở đâu và vì sao.

## 9. Theo dõi timeout mà không nhầm ý nghĩa

### 9.1. Timeout rate theo logical operation

\[
\text{LogicalTimeoutRate}=
\frac{\text{logical operations có ít nhất một timeout}}
{\text{logical operations đã bắt đầu trong cohort}}.
\]

### 9.2. Timeout rate theo attempt

\[
\text{AttemptTimeoutRate}=
\frac{\text{attempts kết thúc bởi timeout}}
{\text{attempts được bắt đầu}}.
\]

Hai số khác nhau: một operation có thể gặp ba timeouts nhưng chỉ là một user journey.

### 9.3. Đừng dùng một tên metric cho hai mẫu số

TimeoutRate=5% vô nghĩa nếu không ghi rõ client API request hay DB attempts; hơn nữa, “timeout” có thể là client deadline hay driver socket read timeout.

### 9.4. Window và cohort

Nếu một operation bắt đầu 09:59 và kết thúc 10:01, metric per-minute có thể chênh giữa events started và completed. Với tỷ lệ final statuses, chọn cohort bắt đầu hoặc công bố denominator và pending operations rõ ràng.

### 9.5. Alert theo business impact

Driver timeout tăng từ 1% lên 3% nhưng retries thành công trong SLO có tác động khác việc 1% payments bị UNKNOWN suốt 30 phút. Cần báo cả low-level signal và high-level unresolved outcomes.

## 10. Phân biệt request timeout với slow operation

Một DB call có thể hoàn thành trong 950 ms dưới timeout 1.000 ms. Nó không timeout nhưng có thể vi phạm latency SLO 200 ms.

### 10.1. Nhìn latency distribution

Đo p50, p95, p99 theo operation class và retry count.

### 10.2. Tail amplification

Một API gọi DB ba lần tuần tự có thể có latency tổng lớn hơn p99 của từng DB call. Nếu driver retries, queueing và backoff góp thêm vào total.

### 10.3. “Tăng timeout” chưa chắc là tối ưu

Nâng timeout từ 1s lên 10s có thể làm giảm số exception nhưng giữ nhiều requests chờ, tăng outstanding queue/memory và khiến client trải nghiệm tệ hơn. Phải điều tra nguyên nhân queue, GC, hot partition, throttling hay network.

### 10.4. Đo latency per attempt và per logical operation

~~~text
Attempt #1: 700ms -> timeout
Backoff:     150ms
Attempt #2: 120ms -> success
Total logical latency ≈ 970ms + client overhead
~~~

Nếu chỉ báo attempt #2 = 120ms, hệ che gần một giây người dùng đã chờ.

## 11. Tỷ lệ ghi không rõ kết quả: định nghĩa được mẫu số mới đo được

Trong các metrics, **unknown-write ratio** đặc biệt quan trọng vì đó là phần rủi ro không thể quyết định thành công hay thất bại từ phản hồi hiện có.

Định nghĩa theo cohort:

\[
U_\text{initial}=
\frac{\text{logical write operations có outcome UNKNOWN sau call/deadline đầu}}
{\text{logical write operations bắt đầu trong cohort}}.
\]

Một metric khác, thể hiện rủi ro kéo dài sau reconciliation budget:

\[
U_\text{unresolved}(T)=
\frac{\text{logical write operations chưa xác minh được sau }T}
{\text{logical write operations đủ tuổi }T\text{ trong cohort}}.
\]

### 11.1. Tại sao cần hai metric?

Có 1.000 writes; 50 timeout khiến outcome ban đầu UNKNOWN. Nếu sau status lookup có 48 commits được xác nhận, một definite rejection được xác nhận và một operation còn UNKNOWN:

~~~text
Initial unknown = 50/1000 = 5%.
Unresolved after reconciliation = 1/1000 = 0.1%.
~~~

Không được xóa thống kê “50 initially unknown” chỉ vì sau đó phần lớn được xác minh. Hai số trả lời hai câu hỏi khác nhau: **chất lượng đường ghi** và **rủi ro chưa giải quyết**.

### 11.2. “Unknown” không được tính là failed hoặc successful

Một dashboard:

~~~text
success = 95%
failure = 5%
~~~

sẽ gây hiểu lầm nếu 5% gồm unknown writes có thể đã commit. Cần giữ ba nhóm tối thiểu:

~~~text
KNOWN_COMMITTED
DEFINITELY_NOT_COMMITTED
UNKNOWN
~~~

Với conditional conflicts, phần definitely-not-committed có thể được chia thành business conflict, validation rejection hoặc policy denial.

### 11.3. Cohort chưa đủ tuổi

Không so 100 operations mới gửi 1 giây trước với “unknown after 5 minutes” rồi xem cả 100 đã hết reconciliation SLA. Denominator phải là những operations **đã qua mốc T**.

### 11.4. Đừng trộn retries và logical writes

Một operation có 5 attempts timeout vẫn chỉ đóng góp một đơn vị vào U_initial/U_unresolved. Ngược lại 5 physical timeouts phải được tính trong AttemptTimeoutRate.

### 11.5. Không dùng unknown=0 khi thiếu telemetry

Nếu application không phát operationId/status record, không thể suy “không thấy unknown” nghĩa là không có uncertain commits. Đánh dấu metric là unavailable/incomplete và cải thiện instrumentation.

### 11.6. Kết quả có thể được xác minh muộn

Một operation UNKNOWN sau 5 phút nhưng reconciled COMMITTED sau 30 phút nên cập nhật final status/time-to-resolution. Cần giữ audit trail **trạng thái đã chuyển**, không rewrite lịch sử khiến unknown incidents biến mất.

## 12. Thời gian giải quyết UNKNOWN và backlog reconciliation

### 12.1. Time to resolution

\[
\text{UnknownResolutionLatency}
=t_\text{known terminal outcome}-t_\text{first unknown}.
\]

Đo histogram p50/p95/p99, không chỉ mean.

### 12.2. Backlog

~~~text
unknown_outcomes_pending
oldest_unknown_outcome_age_seconds
reconciliation_attempts_total
reconciliation_success_total
reconciliation_exhausted_total
~~~

### 12.3. Age bucket

Ví dụ:

| Age của UNKNOWN | Số logical operations | Hành động |
|---|---:|---|
| Dưới 10 giây | 45 | Có thể đang chờ retry/status lookup |
| 10–60 giây | 12 | Điều tra khi vượt SLO |
| 1–10 phút | 3 | Cảnh báo reconciliation lag |
| Trên 10 phút | 1 | Escalation nếu business-critical |

Ngưỡng cảnh báo phải dựa trên business SLO, không sao chép nguyên những số minh họa này.

### 12.4. Final outcome theo tuổi

Một hệ có 5% UNKNOWN ban đầu nhưng 0% còn sau 1 phút có đặc điểm khác hệ có 0,5% UNKNOWN còn sau 24 giờ. Cần đo đường cong unresolved theo T.

### 12.5. Báo cáo backlog không đếm trùng

Mỗi operationId đang unresolved được tính một lần; 100 reconciliation attempts cho cùng operation không phải 100 unknown operations.

## 13. Lỗi có điều kiện là gì?

**Conditional write** chỉ ghi khi một predicate đủ điều kiện tại thời điểm backend quyết định:

~~~text
Put if key not exists.
Update if version == 7.
Delete if owner == tenant T17.
Reserve stock if available >= quantity.
~~~

Nếu predicate không đạt, backend trả conditional rejection.

### 13.1. Có thể là hành vi đúng

Hai clients cùng đặt chiếc ghế cuối:

~~~text
Seat available = 1.
Client A reserves successfully.
Client B conditional update is rejected.
~~~

Request B thất bại về mặt giao dịch mong muốn nhưng database đã **bảo vệ invariant**. Đây không nhất thiết là sự cố hệ thống.

### 13.2. Có thể là tín hiệu contention

Nếu một counter hot key bị 95% conditional conflicts do quá nhiều writers cùng expectedVersion, phải điều tra thiết kế update/read-modify-write, retry/backoff hoặc phân phối tải.

### 13.3. Có thể là duplicate retry đã commit

Một PutItem if-not-exists bị timeout; retry thấy key đã tồn tại. Conditional failure của retry có thể là do **attempt trước đã tạo record**, hoặc do operation khác. Cần đọc idempotency record/payload digest/owner generation; không tự gọi “duplicate request failed”.

### 13.4. Classification business-aware

~~~text
CONFLICT_ALREADY_OWNED_BY_SAME_OPERATION
CONFLICT_OWNED_BY_OTHER_OPERATION
CONFLICT_STALE_EXPECTED_VERSION
CONFLICT_INSUFFICIENT_STOCK
CONFLICT_INVALID_STATE_TRANSITION
CONFLICT_UNKNOWN_OWNER_NEEDS_RECONCILIATION
~~~

Các nhãn này là tầng application. Một exception chung của driver có thể cần thêm authoritative read để phân loại.

## 14. Theo dõi conditional conflicts đúng cách

### 14.1. Raw conditional failure rate

\[
C_\text{attempt}=
\frac{\text{conditional rejected attempts}}
{\text{all conditional write attempts}}.
\]

Nó hữu ích cho DB contention nhưng không phải business operation failure rate.

### 14.2. Logical business conflict rate

\[
C_\text{logical}=
\frac{\text{logical operations cuối cùng là business conflict}}
{\text{logical operations có áp dụng điều kiện tương ứng}}.
\]

Một operation retry ba lần và cuối cùng thành công không nên bị đếm thành ba business failures.

### 14.3. Tách duplicate-safe conflict

Nếu retry cùng operationId phát hiện record đã được tạo bởi chính operation đó, kết quả logical cuối có thể là **COMMITTED**, trong khi physical conditional-failure counter vẫn tăng. Đây không phải mâu thuẫn.

### 14.4. Conflicts theo resource class

Phân chia:

~~~text
unique_username_claim
inventory_reservation
optimistic_order_version
payment_idempotency_claim
lease_fencing
~~~

Không dùng một tỷ lệ conflict chung để kết luận. 10% username “already taken” có thể bình thường; 10% payment operations bị conflicting payload là rất đáng ngại.

### 14.5. Cardinality của tags

Không gắn raw username, orderId, operationId vào metric labels; số lượng time series có thể bùng nổ và làm lộ PII. Dùng operation class, error type, tenant tier hoặc shard group với cardinality giới hạn; chi tiết ID nằm trong logs/traces có quyền truy cập và retention phù hợp.

## 15. Decision table: nên retry hay xác minh?

| Tình huống | Outcome của attempt | Hành động khả thi |
|---|---|---|
| Validation reject trước call | Definitely not submitted | Sửa input; không retry mù |
| Backend conditional failure rõ ràng, no prior unknown | Definite rejection cho attempt đó | Trả business conflict hoặc read/refresh version |
| Driver throttled | Chưa commit theo error contract cụ thể | Bounded backoff, giảm rate, giám sát |
| Server unavailable trước dispatch được xác nhận | Not sent | Có thể retry trong budget |
| Network read timeout sau dispatch | Unknown | Stable idempotency/status lookup; cẩn trọng retry |
| Lost response sau commit | Unknown từ client | Reconcile bằng operationId |
| Transaction commit báo ambiguous | Unknown theo semantics engine | Driver-specific commit retry/status verification |
| Retry conditional conflict sau unknown | Ambiguous logical result | Xem owner/payload/result thay vì kết luận failed |
| Retry GET by primary key | Read-only attempt | Có thể retry khi budget/consistency cho phép |
| Payment capture external call timeout | Unknown side effect | Provider idempotency key và authoritative status API |

### 15.1. “Retryable” không đủ

Một driver có thể gắn nhãn retryable cho lỗi ở tầng transport, nhưng application vẫn cần xét operation có idempotent hay không, budget còn bao nhiêu và outcome có được kiểm soát.

### 15.2. Không retry hết lần này tới lần khác khi invariant đã bị chặn

Nếu username thuộc người khác, retry cùng conditional PutItem không làm username trống. Nếu version stale, cần load state/version mới hoặc trả conflict theo business decision.

### 15.3. Retry with jitter

Các clients đồng loạt retry sau đúng 100 ms tạo đợt burst mới. Exponential backoff có jitter giúp phân tán, nhưng không thay capacity planning, load shedding hay correct status handling.

### 15.4. Deadline và retry budget

Một request deadline 2 giây không nên phát một retry cuối khi chỉ còn 10 ms rồi tạo thêm load vô ích; cần dành thời gian cho response/reconciliation và cancellation semantics.

## 16. Retry storm: khi cơ chế tự phục hồi gây quá tải

Giả sử API rate ban đầu là 10.000 logical operations/sec. Mỗi operation gửi một DB attempt. Backend bắt đầu timeout 30%, driver tự retry mỗi timeout một lần.

Trong mô hình đơn giản, extra attempts khoảng:

\[
10{,}000\times0.30=3{,}000\text{ attempts/sec},
\]

tổng gửi xuống database tăng lên khoảng 13.000 attempts/sec, **nếu chỉ có tối đa một retry** và tỷ lệ timeout trên first attempts.

### 16.1. Nhiều tầng có thể nhân retries

~~~text
HTTP client retries request.
API gateway retries upstream.
Java service retries database call.
Database driver retries request.
~~~

Nếu mỗi tầng không phối hợp, số attempts có thể tăng mạnh hơn mức một tầng riêng. Đếm retries ở từng nơi và giữ end-to-end deadline.

### 16.2. Retry làm tăng queueing

Database đang saturated có thể chậm hơn khi load tăng. Requests chậm dẫn đến nhiều timeout, từ đó tăng retries, tạo vòng lặp dương.

### 16.3. Retry budget theo tỷ lệ

Một hệ có thể giới hạn tổng retry attempts không vượt một tỷ lệ nhỏ so với normal traffic trong một cửa sổ, kết hợp rate limiter/circuit breaker. Các mức budget phải do workload và risk owner quyết định.

### 16.4. Hedged requests

Gửi đồng thời requests dự phòng có thể hữu ích cho một số idempotent reads; với writes side-effecting, hedging cần điều kiện idempotency và consistency cực kỳ rõ. Không áp dụng “speculative second write” chỉ để giảm p99 một cách ngây thơ.

### 16.5. Theo dõi retry success một cách trung thực

“Retry succeeded” cần được phân biệt:

- Backend đã apply mutation ở retry.
- Backend trả committed result của first attempt qua idempotency.
- Operation status lookup xác nhận first attempt đã commit.

Ba trường hợp có business outcome giống nhau nhưng gợi ý nguyên nhân hệ thống khác nhau.

## 17. Chọn backoff và deadline thực dụng

Một thuật toán phổ biến là exponential backoff với full jitter:

\[
\text{cap}_n=\min(B_\max,B_0 2^n),\qquad
\text{sleep}_n\sim Uniform(0,\text{cap}_n).
\]

### 17.1. Cần max attempts và max elapsed time

Chỉ có B_max mà không có overall deadline có thể retry lâu vô hạn. Đặt:

~~~text
maxAttempts
overallDeadline
perAttemptTimeout
minRemainingTimeForRetry
retryableErrorClassifier
~~~

### 17.2. Respect server hints

Nếu service trả Retry-After hoặc throttling metadata đáng tin, phối hợp với deadline và jitter thay vì tự phá hướng dẫn capacity của hệ.

### 17.3. Bắt đầu bằng backpressure

Khi saturating, admission control/bounded concurrency thường cần thiết bên cạnh retries. Không cố giữ success rate bằng cách cho 100.000 requests cùng chờ trong bộ nhớ.

### 17.4. Đếm retries đã bỏ qua

Metric retry_skipped_total với reasons (deadline_exhausted, non_idempotent, budget_exceeded, not_retryable) giúp hiểu vì sao hệ ngừng retry, nhưng đừng coi đó là failure của backend.

## 18. Idempotency như cơ chế quan sát và đảm bảo

Một bảng/collection operation records có thể lưu:

~~~json
{
  "tenantId": "T17",
  "operationId": "CREATE-O101-CLIENT7",
  "payloadDigest": "sha256-of-canonical-payload",
  "state": "COMMITTED",
  "resourceId": "O101",
  "sourceVersion": 8,
  "committedAt": "2026-11-14T08:30:00Z"
}
~~~

### 18.1. Các trạng thái của operation record

~~~text
IN_PROGRESS
COMMITTED
REJECTED
UNKNOWN / NEEDS_RECONCILIATION
~~~

Không ghi COMMITTED trước khi mutation nguồn được commit theo transaction boundary. Một status record tồn tại chưa đủ chứng minh business record đã ghi nếu chúng được ghi bằng hai calls không nguyên tử.

### 18.2. Ghi cùng transaction khi có thể

Nếu nguồn hỗ trợ, commit business record và idempotency result trong cùng transaction/conditional write boundary. Khi không hỗ trợ, thiết kế state machine, compensation/reconciliation và failure semantics rõ ràng.

### 18.3. Không dùng cache Redis làm bằng chứng duy nhất

Redis có thể giữ idempotency key tạm thời, nhưng một cache dễ mất/evict không tự cung cấp authoritative evidence cho payment hoặc inventory reserve. Chọn durability/consistency theo rủi ro.

### 18.4. Payload digest không nên làm lộ thông tin

Không đặt raw sensitive payload trong metric labels hoặc trace baggage. Digest có thể giúp phát hiện reuse operationId khác nội dung, nhưng nên cân nhắc canonicalization, security, HMAC và privacy threat model.

### 18.5. Monitoring

Theo dõi:

~~~text
idempotency_replay_total
idempotency_payload_mismatch_total
idempotency_records_in_progress
idempotency_record_age_seconds
idempotency_expiry_risk_total
~~~

Một đột biến replay_total có thể là client/network instability; payload mismatch tăng có thể là API misuse hoặc lỗi retry client.

## 19. Reconciliation: biến UNKNOWN thành bằng chứng

Sau timeout của create, thay vì sinh một request mới:

~~~text
1. GET authoritative operation status by (tenantId, operationId).
2. If COMMITTED with matching payload digest -> return resourceId/result.
3. If definitely REJECTED -> return business rejection.
4. If IN_PROGRESS -> wait/backoff/poll within budget.
5. If absent but absence cannot be trusted -> remain UNKNOWN.
6. If source has evidence no attempt could commit -> controlled retry.
7. If deadline exhausted -> return pending/unknown, retain reconciliation task.
~~~

### 19.1. NotFound của status record chưa chắc chứng minh thất bại

Nếu operation status được ghi bất đồng bộ **sau** business record, status NOT_FOUND có thể đồng thời tồn tại với một committed order. Cần biết authority và atomicity.

### 19.2. Reconciliation có thể dựa trên business key

Nếu orderId đã cố định và được dùng làm canonical unique key, GET by orderId có thể xác minh một phần. Nhưng phải so tenant, request digest và operation ownership; nếu một operation khác sở hữu cùng key, không thể nhận là thành công của operation hiện tại.

### 19.3. Có time budget cho reconciliation

Không poll mỗi 10 ms trong 10 phút. Dùng exponential backoff, jitter, deadlines, event signals và rate limits; nếu chưa rõ thì chuyển background operational workflow theo contract, không bịa kết luận.

### 19.4. Đối soát side effects xuyên services

Trong Saga, Order Service nói CREATED nhưng Payment Provider status còn UNKNOWN. Không tự coi payment settled vì order có tồn tại. Mỗi authoritative owner phải được hỏi về fact riêng.

### 19.5. Audit trail

Lưu transition:

~~~text
08:30:00 REQUESTED
08:30:01 DB_TIMEOUT (unknown)
08:30:03 STATUS_CHECK #1 -> IN_PROGRESS
08:30:06 STATUS_CHECK #2 -> COMMITTED revision=8
~~~

Audit giúp chứng minh tại sao application trả một kết quả và debug retry behavior sau sự cố.

## 20. Unknown ratio khác lost-write ratio

Một unknown write **không mặc nhiên là lost write**.

### 20.1. Có thể commit và ACK mất

Unknown ban đầu nhưng committed là tình huống bình thường cần xử lý trong hệ phân tán.

### 20.2. Có thể không commit

Backend dừng trước transaction commit, client không được biết. Sau reconciliation mới xác minh no-effect/definite rejection nếu đủ bằng chứng.

### 20.3. Có thể commit rồi bị rollback theo durability semantics đặc thù

Nếu một write được ACK ở mức yếu hơn yêu cầu nghiệp vụ và failover làm mất dữ liệu, đây là durability/correctness vấn đề riêng. Cần biết acknowledged write concern/consistency và quan sát recovery; không gộp tất cả unknown vào lost.

### 20.4. Có thể sinh duplicate side effect do retry sai

Một logical operation tạo hai orders là **duplicate effect**. Đo:

~~~text
duplicate_business_effect_total
reconciled_commit_total
unresolved_write_total
confirmed_missing_after_ack_total
~~~

Chỉ khi có xác minh mới phân loại lost/duplicate. Không đo “write lost” bằng cách đếm driver timeouts.

## 21. MongoDB: retryable writes, duplicate key và ambiguous commit

MongoDB Java Driver có cơ chế retryable writes và các error labels tùy topology, version, operation type và cấu hình. Một trong các yêu cầu quan sát đầu tiên là ghi lại **driver có đang tự retry hay không**.

### 21.1. Một insertOne có thể tạo nhiều attempts

~~~java
import com.mongodb.client.MongoCollection;
import com.mongodb.client.model.Filters;
import org.bson.Document;

MongoCollection<Document> orders = database.getCollection("orders");
Document order = new Document("_id", "O101")
        .append("tenantId", "T17")
        .append("operationId", "CREATE-O101-CLIENT7")
        .append("status", "CREATED");

orders.insertOne(order);
Document persisted = orders.find(Filters.eq("_id", "O101")).first();
~~~

Nếu network timeout sau dispatch, không khẳng định insertOne chưa commit. Driver có thể đã retry một số trường hợp theo retryWrites; application cần theo dõi logical outcome và cấu hình retry.

### 21.2. E11000 duplicate key không luôn là “operation thất bại”

Một retry sau ACK loss có thể gặp duplicate key nếu đi qua một đường không được dedupe theo cùng retryable-write session semantics. Khi đó:

~~~text
Existing _id = O101, operationId=CREATE-O101-CLIENT7
Retry tries same _id O101
E11000 duplicate key
~~~

Nếu persisted record có cùng tenant, operationId/payload digest và đúng business result, logical operation có thể đã thành công. Nếu key thuộc operation khác thì đó là business conflict. Cần authoritative read để phân loại.

### 21.3. Retryable write không thay application idempotency

Một driver retry được cùng statement không bảo vệ toàn bộ workflow gồm nhiều DB writes, provider calls hoặc application tự sinh ID mới mỗi lần. Dùng stable operationId và transaction/outbox khi cần.

### 21.4. Transaction commit có thể không rõ outcome

Trong MongoDB multi-document transactions, một lỗi trên commit có thể mang label **UnknownTransactionCommitResult**. Không phải cứ có exception là transaction đã abort. Cần dùng logic/driver API theo hướng dẫn của phiên bản: retry commit khi phù hợp, hoặc tra kết quả nghiệp vụ có thẩm quyền.

### 21.5. TransientTransactionError khác UnknownTransactionCommitResult

Một lỗi transaction dạng transient có thể dẫn đến retry **toàn transaction** theo pattern được hỗ trợ; unknown commit result liên quan việc xác định commit đã hoàn thành. Không dùng cùng một catch block để xử lý cả hai bằng “chạy lại tất cả business side effects”.

### 21.6. Change stream/outbox

Nếu source write committed nhưng outbox publisher/indexer chậm, có thể thấy source success và search NOT_FOUND. Đo projection lag riêng, không gọi đó là source write failure.

### 21.7. Metrics gợi ý

~~~text
mongo_commands_started_total{command=insert}
mongo_commands_failed_total{error_class=...}
mongo_duplicate_key_total{operation_class=...}
mongo_transaction_commit_unknown_total
mongo_retryable_write_attempts_total
mongo_server_selection_timeout_total
mongo_replication_lag
~~~

Đây là các tên metrics gợi ý do application/collector có thể xây dựng; không phải tên được driver tự động phát với đúng nhãn như ví dụ.

## 22. DynamoDB: ConditionCheckFailed, throttling và retry

Một conditional PutItem:

~~~java
import java.util.Map;
import software.amazon.awssdk.services.dynamodb.model.AttributeValue;
import software.amazon.awssdk.services.dynamodb.model.PutItemRequest;
import software.amazon.awssdk.services.dynamodb.model.ConditionalCheckFailedException;

PutItemRequest request = PutItemRequest.builder()
        .tableName("Orders")
        .item(Map.of(
            "PK", AttributeValue.builder().s("ORDER#O101").build(),
            "operationId", AttributeValue.builder()
                    .s("CREATE-O101-CLIENT7").build(),
            "state", AttributeValue.builder().s("CREATED").build()
        ))
        .conditionExpression("attribute_not_exists(PK)")
        .build();

try {
    dynamoDbClient.putItem(request);
} catch (ConditionalCheckFailedException conflict) {
    // A definite rejection of this conditional attempt.
    // If a previous attempt timed out, inspect authoritative record/operation.
}
~~~

### 22.1. ConditionalCheckFailedException có ý nghĩa gì?

Điều kiện của *attempt được phản hồi* không đạt. Không nên retry y nguyên condition liên tục nếu không có thay đổi dữ liệu hoặc mục tiêu đã đạt.

### 22.2. Khi trước đó đã timeout

Nếu attempt #1 outcome UNKNOWN và attempt #2 bị ConditionalCheckFailed, key có thể đã được tạo bởi attempt #1 hoặc caller khác. Đọc existing item, so operationId/digest và tenant trước khi phân loại.

### 22.3. Throttling là loại riêng

DynamoDB có thể throttle do capacity/partition pressure hoặc các giới hạn dịch vụ. Theo dõi throttled requests, consumed capacity, hot partitions, retry backoff và outstanding requests; không đếm throttles như conditional business conflicts.

### 22.4. Consistent read trong phạm vi thích hợp

Để reconcile một item đã biết primary key, có thể dùng GetItem với ConsistentRead khi table/Region/API hỗ trợ và yêu cầu consistency cho phép. Không áp dụng strongly consistent read cho GSI vì GSI có eventual read semantics.

### 22.5. Transactions và client request token

DynamoDB TransactWriteItems hỗ trợ idempotency thông qua ClientRequestToken theo contract/thời hạn của dịch vụ. Chọn token ổn định và quản lý payload consistency; không coi token tồn tại vĩnh viễn hoặc ngăn mọi duplicate ngoài window được hỗ trợ.

### 22.6. TransactionCanceledException

Một transaction bị hủy có thể có cancellation reasons như ConditionalCheckFailed, TransactionConflict hoặc những lỗi khác theo API. Phải phân loại theo reasons khi SDK trả chúng, chứ không gộp tất cả thành timeout.

### 22.7. Metrics

~~~text
dynamodb_conditional_check_failed_total
dynamodb_transaction_cancel_total{reason=...}
dynamodb_throttled_total
dynamodb_sdk_retry_attempts_total
dynamodb_request_latency_seconds
dynamodb_unknown_write_total
dynamodb_consumed_capacity
~~~

Một số metrics có thể lấy từ SDK/CloudWatch tùy cấu hình, một số là application-level; cần ghi rõ nguồn đo.

## 23. Cassandra/ScyllaDB: LWT và timeout không phải cùng một lỗi

Ví dụ một conditional insert trong CQL:

~~~sql
INSERT INTO username_claims (tenant_id, username, owner_id)
VALUES ('T17', 'alice', 'U101')
IF NOT EXISTS;
~~~

### 23.1. Kết quả [applied] = true/false

Khi backend trả kết quả bình thường:

- applied=true: conditional statement được áp dụng theo consistency/protocol.
- applied=false: điều kiện không đạt; có thể kèm current data tùy driver/query.

### 23.2. Timeout khi đang chạy LWT

Nếu coordinator/client không nhận kết quả, **không tự kết luận LWT đã thất bại**. Conditional operation có thể đang được xử lý/đã được quyết định trong quorum Paxos path.

### 23.3. Retry cùng claim với same owner

Nếu timeout rồi retry IF NOT EXISTS và nhận applied=false, cần đọc record claim:

~~~text
ownerId == U101 with same operationId -> may be replay success.
ownerId == U999 -> business conflict.
owner unknown/stale -> reconcile.
~~~

### 23.4. Consistency level và serial consistency

LWT dùng cơ chế serial consistency riêng cho conditional coordination. Read CL và serial CL ảnh hưởng semantics/latency; benchmark và monitoring phải ghi cấu hình thực tế. Không giả định một SELECT ở consistency thấp đủ xác minh một claim toàn cụm.

### 23.5. WriteTimeout và WriteFailure

Các exceptions này mang thông tin từ driver/coordinator về timeout, write type và replicas liên quan. Mapping sang “UNKNOWN” cần dựa trên operation, phase và error semantics cụ thể; không suy toàn bộ rollback chỉ vì write timeout.

### 23.6. Contention metrics

LWT conflicts tăng ở hot partition có thể kéo theo latency và retries. Theo dõi coordinator saturation, per-partition hotspots, Paxos contention (khi engine cung cấp), p99 conditional ops và unresolved outcomes.

## 24. Redis: timeout của INCR hoặc SET NX

Redis xử lý một command trên server theo atomicity của command đó, nhưng nếu client mất response thì vẫn có uncertainty.

### 24.1. INCR có thể bị lặp

~~~text
INCRBY account:counter 1
  -> Redis increments successfully.
  -> Network drops response.

Client retries INCRBY account:counter 1
  -> Redis increments again.
~~~

Một lần logical increment có thể thành hai increments. Không coi atomic command đồng nghĩa idempotent command.

### 24.2. SET NX không tự giải thích quyền sở hữu

~~~text
SET claim:alice U101 NX
  -> timeout
Retry SET claim:alice U101 NX
  -> nil (key exists)
~~~

Kết quả retry nói key tồn tại lúc retry, chưa nói caller U101 hay người khác đang sở hữu. Đọc value/generation và kiểm tra operationId.

### 24.3. Lua giúp nguyên tử trong Redis, không xuyên hệ

Lua có thể gộp SET NX, result marker và validation trong một atomic Redis execution, nhưng nếu đồng thời ghi MongoDB/Payment Provider thì không có distributed transaction chỉ vì một script.

### 24.4. Expiration/failover

Nếu claim có TTL và expire, cùng key có thể được cấp lại. Ownership token/generation, fencing và durability policy quan trọng khi resource có external side effects.

### 24.5. Redis có thể là cache hoặc authoritative state

Trước khi dùng GET để reconcile operation, xác định Redis key có phải nguồn bền vững đủ tiêu chuẩn hay chỉ là cache có thể evict. Một cache không tự là authoritative evidence cho payment committed.

## 25. Search index/CDC: một loại “ghi chưa thấy” khác

Một source Order đã commit, nhưng Elasticsearch/OpenSearch hoặc materialized read model chưa nhận sự kiện:

~~~text
Order source:       O101 exists, version=8.
Outbox:             event published.
Search index:       O101 missing.
~~~

### 25.1. Phân biệt hai câu hỏi

- **Source write committed?** Hỏi Order authority.
- **Projection visible?** Hỏi search/read model và watermark.

Không dùng search NOT_FOUND để kết luận create thất bại.

### 25.2. CDC/outbox lag

Theo dõi:

~~~text
outbox_oldest_pending_age_seconds
cdc_capture_lag_seconds
broker_consumer_lag
projection_applied_source_version
search_refresh_visibility_latency_seconds
~~~

### 25.3. Event duplicate

Outbox publisher có thể gửi lặp khi ACK mất; projector phải idempotent theo eventId/entityVersion. Đừng gộp repeated event deliveries vào “duplicate business writes”.

### 25.4. Compensation và Saga

Trong workflow nhiều nguồn, source Order COMMITTED nhưng Payment UNKNOWN không chứng minh toàn checkout thành công. Dashboard cần phân biệt status từng domain owner.

## 26. Multi-Region: xác minh ở đâu?

Một hệ active-active có các Regions A và B:

~~~text
Region A acknowledges write O101.
Region B has not replicated O101.
Client retries via Region B.
~~~

### 26.1. Region B NOT_FOUND chưa đủ

Nếu cross-Region replication eventual, read tại B có thể stale. Không dùng B NOT_FOUND làm bằng chứng A chưa commit.

### 26.2. Operation routing

Hệ có thể pin một operationId tới home Region/owner hoặc dùng global coordination protocol để giữ cùng một authority qua retry. Cần nêu rõ mô hình write ownership và failover.

### 26.3. Conflict resolution của Global Tables

Nếu các Regions đều nhận writes và conflict được resolve theo một chính sách như last-writer-wins, đó không tự bảo vệ unique business claims hoặc tránh duplicate payment. Theo dõi conflict rates và business reconciliation.

### 26.4. Regional dashboards

Đo timeout/retry/unknown theo Region/AZ, network path và replica placement. Một p99 global có thể che một Region đang có 10% unknown outcomes.

### 26.5. Khi home Region mất

Failover có thể làm outcome chưa rõ lâu hơn. Protocol cần xác định safe retry, owner epoch/fencing và nơi tra operation status. Không chuyển sang Region mới rồi phát lại blind non-idempotent writes.

## 27. Phân biệt write acknowledgment với durable business outcome

### 27.1. Acknowledged by node

Một backend có thể xác nhận request theo một cấp durability/consistency yếu hơn quorum/majority. Nếu business yêu cầu surviving failure, test và metric phải gắn đúng acknowledgment mode.

### 27.2. Quorum acknowledgement

Quorum không tự đồng nghĩa mọi global replica hay secondary index đã bắt kịp. Source consistency và projection freshness là các contract khác nhau.

### 27.3. Transaction commit

Một transaction có thể commit đúng source boundary nhưng downstream email/search chưa chạy. Theo dõi transaction outcome và side effects riêng.

### 27.4. External payment

Provider đã capture tiền nhưng Order DB update thất bại là cross-service inconsistency. Không sửa bằng cách tự chuyển UNKNOWN thành FAILED rồi capture lại không-idempotent.

### 27.5. SLO đúng theo rủi ro

Với search catalog, eventual visibility vài giây có thể chấp nhận. Với payment ledger, unknown-write aging và duplicate effect là các chỉ số quan trọng hơn chỉ p95 network latency.

## 28. Thiết kế telemetry theo ba tầng

Một sơ đồ observability:

~~~mermaid
flowchart TD
    A["Client / API logical operation"] --> B["Java Service"]
    B --> C["DB driver attempt #1"]
    B --> D["DB driver attempt #2"]
    C --> E["NoSQL authoritative store"]
    D --> E
    B --> F["Operation state / reconciliation"]
    F --> E
    B --> G["Metrics"]
    C --> G
    D --> G
    F --> G
    B --> H["Traces and structured logs"]
    F --> H
    G --> I["Dashboards and alerts"]
    H --> I
~~~

### 28.1. Logical operation metrics

~~~text
business_operation_started_total
business_operation_finalized_total{outcome=...}
business_operation_unknown_initial_total
business_operation_unresolved_after_deadline_total
business_operation_duration_seconds
~~~

### 28.2. Driver/transport attempt metrics

~~~text
db_attempts_total{operation_class=...,result=...}
db_attempt_duration_seconds{operation_class=...}
db_retry_attempts_total{reason=...}
db_retry_skipped_total{reason=...}
db_connection_acquire_timeout_total
db_throttled_attempts_total
~~~

### 28.3. Reconciliation/projection metrics

~~~text
unknown_outcomes_pending
oldest_unknown_outcome_age_seconds
unknown_resolution_duration_seconds
reconciliation_attempts_total{result=...}
outbox_oldest_pending_age_seconds
projection_lag_seconds
~~~

### 28.4. Gắn owner cho các signals

Timeout của driver thuộc service/DB path; source unknown backlog thuộc team vận hành service business; search lag thuộc projector. Đừng tạo một alert chung mà không biết ai chịu trách nhiệm.

### 28.5. Chọn tên metric ổn định

Các tên trong bài là gợi ý, không phải một tiêu chuẩn bắt buộc. Hãy giữ consistency về hậu tố _total, _seconds và semantics counter/gauge/histogram theo monitoring library.

## 29. Metric counter, gauge và histogram dùng khi nào?

### 29.1. Counter

Số attempts, timeouts, retry attempts, conditional failures là events tích lũy:

~~~text
db_attempts_total
db_timeouts_total
conditional_conflicts_total
~~~

Counter thường chỉ tăng, có reset khi process restart; hệ đo lấy rate/increase theo window thay vì dùng raw delta một cách ngây thơ.

### 29.2. Gauge

Outstanding in-flight requests, queue depth, unknown backlog:

~~~text
db_outstanding_requests
unknown_outcomes_pending
reconciliation_queue_depth
~~~

Gauge thay đổi lên/xuống. Nếu chỉ đếm gauge của một process rồi cộng lại, phải bảo đảm operation state không được duplicate trên nhiều service instances.

### 29.3. Histogram

Duration per attempt, total logical operation latency, time to reconcile:

~~~text
db_attempt_duration_seconds
business_operation_duration_seconds
unknown_resolution_duration_seconds
~~~

Histograms giúp phân tích p95/p99/percentile gần đúng trong hệ đo được cấu hình đúng buckets.

### 29.4. Không dùng average che tail

Một số attempts 30 giây có thể hiếm nhưng gây SLO breach và retry storms. Theo dõi p99, timeouts và age of UNKNOWN; average 20 ms không thể hiện toàn bộ.

### 29.5. Phân biệt “in-flight” với “unknown”

Một operation đang chờ response có thể là IN_PROGRESS; chỉ khi response/deadline làm kết quả không xác định và chưa được reconciled mới đặt UNKNOWN theo state machine.

## 30. Java với Micrometer: ghi nhận attempt và result

Ví dụ khái niệm, giả định ứng dụng dùng Micrometer:

~~~java
import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;

public final class DbAttemptMetrics {
    private final MeterRegistry registry;

    public DbAttemptMetrics(MeterRegistry registry) {
        this.registry = registry;
    }

    public void record(
            String operationClass,
            String resultClass,
            long durationNanos
    ) {
        Counter.builder("db_attempts_total")
                .tag("operation_class", operationClass)
                .tag("result", resultClass)
                .register(registry)
                .increment();

        Timer.builder("db_attempt_duration")
                .tag("operation_class", operationClass)
                .tag("result", resultClass)
                .register(registry)
                .record(java.time.Duration.ofNanos(durationNanos));
    }
}
~~~

### 30.1. Cố ý không có raw key tag

Không thêm orderId, operationId, username hay SQL/CQL full text vào tags. Những giá trị này có cardinality rất cao và có thể chứa dữ liệu nhạy cảm.

### 30.2. Timer không mặc định là toàn business latency

Timer trên đo một **physical attempt**. API có thể retry hai lần và reconcile, nên cần timer khác cho logical operation.

### 30.3. Tags cần allowlist

operationClass có thể nhận:

~~~text
order.create
order.confirm
stock.reserve
payment.capture
~~~

resultClass có thể nhận:

~~~text
committed_ack
conditional_conflict
throttled
timeout
server_error
unknown
~~~

Tránh điền exception message/user input vào label.

### 30.4. Nhắc về naming conventions

Micrometer có các naming conventions và exporter chuyển đổi tên metric theo backend. Ví dụ ở đây thể hiện ý định; xem tên thực trong Prometheus/OTel exporter khi tích hợp để tránh đếm trùng hậu tố.

### 30.5. Đừng double-count khi driver auto retry

Nếu application bao một client method bằng timer, nó có thể ghi **một method call** dù driver đã gửi hai wire attempts. Muốn đo physical attempts, cần driver telemetry/command listeners/SDK instrumentation; phân biệt hai tầng trong metrics.

## 31. Java: timer logical operation và final result

Một wrapper minh họa:

~~~java
import java.util.function.Supplier;
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;

public final class OperationMetrics {
    private final MeterRegistry registry;

    public OperationMetrics(MeterRegistry registry) {
        this.registry = registry;
    }

    public <T> T measure(
            String operationClass,
            Supplier<T> action
    ) {
        Timer.Sample sample = Timer.start(registry);
        try {
            return action.get();
        } finally {
            sample.stop(Timer.builder("business_operation_duration")
                    .tag("operation_class", operationClass)
                    .register(registry));
        }
    }
}
~~~

### 31.1. Timer wrapper đo tới khi action kết thúc, chưa chắc tới khi outcome cuối được xác minh

Nếu action trả UNKNOWN sau 2 giây, reconciliation chạy tiếp 5 phút, timer trên chỉ đo API call. Cần metric riêng cho resolution latency và final status.

### 31.2. Final outcome metric chỉ ghi một lần

Một operationId chỉ được chuyển sang terminal state theo conditional state machine. Nếu worker A và B cùng reconcile, tránh cả hai tăng counter “finalized” cho cùng transition.

### 31.3. Exactly-once metrics khó hơn business correctness

Đồng bộ metric counter với DB transaction thường không nguyên tử. Để tính **số final outcomes tuyệt đối**, có thể tổng hợp từ durable operation state/audit log. In-memory counters thích hợp tín hiệu vận hành nhưng có thể chênh khi crash/replay.

### 31.4. Logical errors không phải mọi exceptions

Một conditional business rejection có thể là terminal response hợp lệ về hệ thống. Ghi outcome=business_conflict, không coi nó là availability failure nếu SLO availability của API định nghĩa khác.

## 32. MongoDB Java Driver command monitoring

MongoDB Java Driver cung cấp command monitoring API, giúp quan sát commands gửi đi và kết quả theo driver.

~~~java
import com.mongodb.event.CommandListener;
import com.mongodb.event.CommandStartedEvent;
import com.mongodb.event.CommandSucceededEvent;
import com.mongodb.event.CommandFailedEvent;
import java.util.concurrent.TimeUnit;

public final class MongoCommandObserver implements CommandListener {
    @Override
    public void commandStarted(CommandStartedEvent event) {
        // Record start for operation class / command name.
        // Never log full command payload without redaction.
    }

    @Override
    public void commandSucceeded(CommandSucceededEvent event) {
        long ms = event.getElapsedTime(TimeUnit.MILLISECONDS);
        // Record command-level latency and success.
    }

    @Override
    public void commandFailed(CommandFailedEvent event) {
        long ms = event.getElapsedTime(TimeUnit.MILLISECONDS);
        // Map failure to a controlled taxonomy.
    }
}
~~~

Đăng ký listener qua MongoClientSettings/driver configuration theo phiên bản đang sử dụng.

### 32.1. Correlation

Command events có request metadata giúp liên kết started/succeeded/failed trong phạm vi driver. Nhưng gắn business operationId vào trace vẫn cần application context.

### 32.2. Không log nguyên command

MongoDB commands có thể chứa email, token, địa chỉ, số tài khoản hoặc PII. Command monitoring không được trở thành kênh rò dữ liệu.

### 32.3. Command-level metrics không thay business outcome

Một insert command succeeded có thể thuộc một transaction chưa commit hoặc một step của Saga. Không tăng business committed_count chỉ từ mọi commandSucceeded.

### 32.4. Auto retry visibility

Kiểm tra driver version/command instrumentation để hiểu liệu command monitoring phản ánh từng retry attempt và server selection failures ra sao. Không suy một method invocation tương đương một command event duy nhất.

## 33. AWS SDK Java: tách retry policy và application metrics

AWS SDK for Java v2 có cơ chế retry strategies và metric publishing/observability tùy cấu hình. Khi dùng DynamoDB:

- Ghi physical attempts của SDK nếu có.
- Ghi error code, throttling reason và operation API.
- Ghi ConsumedCapacity/RequestId khi được trả và được phép.
- Ghi logical operationId ở application layer.
- Không tạo hai retry loops độc lập không có chung overall deadline.

### 33.1. SDK retry vs application retry

Một PutItem call có thể retry nội bộ; sau khi call ném timeout, outer HTTP handler lại retry toàn command. Để chẩn đoán, cần biết retries của cả SDK và service.

### 33.2. SDK request IDs

Request IDs hữu ích khi làm việc với support và correlate logs, nhưng không là business identity hoặc operationId.

### 33.3. Throttling và conditional errors

Throttles có thể được retry theo policy; conditional failures thường là điều kiện không thỏa, cần application decision. Không blanket retry mọi DynamoDbException.

### 33.4. Transaction status

Một network timeout của TransactWriteItems vẫn có thể làm outcome mơ hồ. ClientRequestToken có idempotency semantics trong window được hỗ trợ; sau window cần operation record/reconciliation phù hợp.

## 34. Cassandra driver: thông tin coordinator và execution

Một Java CQL driver có thể cung cấp request latency, pool/in-flight, coordinator, retry policy và exception metadata tùy version.

### 34.1. Cần đo theo statement class

~~~text
SELECT users_by_id
SELECT orders_by_customer LIMIT 50
INSERT orders_by_id
UPDATE stock IF available >= ?
INSERT username_claim IF NOT EXISTS
~~~

Không gắn raw CQL có tenantId/values vào metric labels; dùng statement template/operation class.

### 34.2. LWT riêng

Track applied=true/false, timeouts, contention, serial consistency và reconciliation. Đừng nhập LWT conditional failure vào cùng denominator với regular INSERT.

### 34.3. Read/Write timeout context

Một write timeout có thể kèm write type, received vs required acks theo driver/engine; ghi structured fields an toàn để điều tra nhưng không tự biến chúng thành bằng chứng commit đã rollback.

### 34.4. Driver retry policy

Phải đọc cấu hình retry policy và speculative execution hiện có. Một application có thể đã có physical attempts bổ sung mà business code không trực tiếp gọi.

## 35. OpenTelemetry tracing: một operation nhiều spans

Một trace:

~~~text
HTTP POST /orders
  ├─ validate request
  ├─ DB insert attempt=1 (timeout)
  ├─ retry backoff
  ├─ DB insert attempt=2 (condition not met)
  ├─ authoritative operation status read
  └─ logical result COMMITTED
~~~

### 35.1. Span attributes

Ví dụ các attributes do application định nghĩa:

~~~text
app.operation.class = order.create
app.operation.outcome = committed
app.db.attempt.number = 2
app.db.retry.reason = network_timeout
app.db.conditional.reason = already_owned_same_operation
app.reconciliation.used = true
~~~

Tên minh họa; nếu áp dụng OpenTelemetry semantic conventions chính thức, dùng tên/phiên bản được framework hỗ trợ, tránh tự tuyên bố chúng là attributes chuẩn.

### 35.2. Span status và business status

Một DB attempt span có thể ERROR (timeout), trong khi parent logical span cuối cùng COMMITTED. Ghi cả hai, không rewrite attempt failure sau khi reconciliation thành công.

### 35.3. Sampling

Nếu trace sampling bỏ hết các requests thành công, cần giữ cách lấy mẫu unknown/conditional anomalies và logs có cấu trúc tương ứng. Không bật “collect every full request body” để debug lỗi.

### 35.4. Cross-service propagation

Traceparent/baggage/correlation IDs giúp nối API → Order → Inventory → Payment. Nhưng operationId/business IDs cần lifecycle và access control khác traceId; traceId không thay idempotency key.

## 36. Structured logging cho unknown write

Một log event:

~~~json
{
  "event": "db_write_outcome_unknown",
  "service": "order-service",
  "operationClass": "order.create",
  "operationIdHash": "hmac-or-redacted-id",
  "tenantTier": "enterprise",
  "attempt": 1,
  "driverErrorClass": "READ_TIMEOUT",
  "sourceRegion": "region-a",
  "elapsedMs": 701,
  "retryAllowed": false,
  "reconciliationScheduled": true
}
~~~

### 36.1. Những field hữu ích

~~~text
timestamp
operationClass
correlationId/traceId
operationId (protected) or safe hash
attemptNumber
backend operation type
endpoint/collection/table template
region/node/partition group when available
timeout/deadline budgets
exception type/code/label
status transition
sourceVersion/commit evidence if known
~~~

### 36.2. Đừng log secrets

Không log plaintext passwords, authorization headers, full payment payloads, personal emails hay unredacted document body. Retention và RBAC cho logs phải phù hợp security policy.

### 36.3. Correlation vs uniqueness

Một trace có thể được tạo mới cho mỗi retry ở client. Dùng stable operationId/HMAC để nối logical operation; trace IDs phục vụ điều tra cuộc gọi và có thể thay đổi.

### 36.4. Event log và metrics cần liên kết

Khi một alert unknown backlog tăng, dashboard nên dẫn tới logs/traces đã lọc theo operation class, error label và thời gian, không yêu cầu engineer đoán từ hàng triệu lines.

## 37. Thiết kế dashboard: bốn tín hiệu không được trộn

Một dashboard vận hành NoSQL nên có ít nhất bốn khu vực:

| Khu vực | Biểu đồ chính | Câu hỏi |
|---|---|---|
| Timeout | Attempt timeout rate, logical timeout rate, latency p99 | Requests chậm hoặc mất response ở đâu? |
| Retry | Retry attempts/sec, amplification, budget exhausted | Retry đang giúp hay gây quá tải? |
| Conditional failure | Conflict rate theo business operation, expected/unexpected | Predicate bị chặn đúng hay hệ đang contention? |
| Unknown writes | Initial unknown ratio, pending, age, resolution rate | Bao nhiêu writes chưa biết có commit hay không? |

### 37.1. Header overview

~~~text
Logical writes/sec:                8,000
Known committed (matured cohort): 98.8%
Definite business rejects:         0.9%
Unresolved after 60s:               0.3%
Retry amplification:                1.17x
DB attempt p99:                     180 ms
End-to-end logical p99:             420 ms
Oldest UNKNOWN:                    280 sec
~~~

Các số chỉ minh họa và cần gắn window/cohort/operation class. Không cộng phần trăm từ nhiều denominators khác nhau thành một pie chart.

### 37.2. Breakdown theo loại lệnh

Tách:

~~~text
order.create
order.confirm
inventory.reserve
payment.capture
username.claim
~~~

Một service có thể khỏe ở GET nhưng hỏng PUT conditional hoặc payment capture. Một overview p99 chung che tình trạng đó.

### 37.3. Breakdown theo Region, AZ, node, partition group

Nếu unknown tăng chỉ ở Region B hoặc một coordinator, điều tra network/topology khác với unknown tăng đồng thời toàn hệ.

### 37.4. Overlay thay đổi hệ thống

Đánh dấu deployment, index build, cache invalidation incident, capacity changes, compaction/repair và burst traffic trên timeline.

### 37.5. Không lấy “cache hit 99%” làm kết luận

Một Redis cache trả stale NOT_FOUND có thể có hit rate cao trong lúc source writes vẫn committed. Read path correctness và unknown-write dashboard cần phân biệt.

## 38. Alert: ít nhưng đúng hành động

### 38.1. Alert về tỷ lệ UNKNOWN sau deadline

~~~text
Unresolved write ratio after 60s > agreed threshold
for 5 consecutive minutes,
with enough matured sample size.
~~~

Ngưỡng và thời gian được xác định theo SLO/risk, không mặc định một giá trị cho mọi hệ.

### 38.2. Alert về oldest UNKNOWN

Một operation payment UNKNOWN 30 phút có thể quan trọng dù ratio rất nhỏ. Sử dụng age-of-oldest theo operation criticality, kết hợp absolute backlog.

### 38.3. Alert retry amplification

Retry amplification tăng nhanh cùng backend p99 và throttles có thể báo trước retry storm; ưu tiên rate limiting/backpressure hơn tăng maxAttempts.

### 38.4. Alert conditional conflict bất thường

Không alert “username already taken 20%” nếu đây là hành vi bình thường. Alert tăng đột biến của unexpected conflict hoặc cùng hot key gây p99/availability violation.

### 38.5. Alert theo data correctness

~~~text
duplicate_business_effect_total > 0
confirmed_missing_after_ack_total > 0
reconciliation_checksum_mismatch_total > threshold
~~~

Nếu một business invariant nghiêm trọng bị vi phạm, báo ngay theo policy thay vì chờ timeout rate tăng.

### 38.6. Alert có runbook và owner

Mỗi alert nên có:

- Ý nghĩa và denominator.
- Dashboard/traces liên quan.
- Dịch vụ và nhóm on-call.
- Hướng giảm tác động an toàn.
- Điều kiện auto-resolve/escalate.

## 39. SLO khác nhau theo lệnh

### 39.1. GET không nhất thiết có unknown write

Read path chủ yếu đo freshness, availability, latency, errors. Unknown-write chỉ áp dụng operations có mutation hoặc external side effect chưa xác minh.

### 39.2. Conditional unique claim

Business conflict có thể là kết quả bình thường và không nằm trong availability-error budget, trong khi timeout/UNKNOWN của claim đáng lưu ý.

### 39.3. Inventory reservation

Một retry làm reserve hai lần là correctness failure. SLO cần phản ánh duplicate reserve prevention và time-to-known-outcome.

### 39.4. Payment capture

Đặc biệt quan trọng:

~~~text
No duplicate capture for same operation.
Unknown capture has bounded reconciliation duration.
No false "failed" presented as permission to capture again.
~~~

### 39.5. Product catalog write

Một product update source thành công nhưng search index trễ vài giây có thể được chấp nhận theo freshness SLO. Không nên xử lý như uncertain source commit chỉ vì search GET không thấy.

### 39.6. SLO không chỉ là p99

Availability, correctness, durable commits, unknown ratio and resolution latency là các dimension khác. Một system p99=20 ms nhưng 1% duplicate charges không thể coi là khỏe.

## 40. Khi gặp timeout spike, điều tra theo lớp

### Lớp 1 — Client/gateway

- Offered rate vs completed rate.
- Request deadline và saturation ở client.
- Connection pool exhaustion, DNS/TLS/network errors.
- Gateway retry count và upstream timeouts.

### Lớp 2 — Java service

- Thread pool saturation, queue depth, GC pauses.
- Serialization and payload size tail.
- Circuit breaker/rate limiter state.
- Nested retry loops, expired deadlines.

### Lớp 3 — Driver

- Server selection/connection acquisition.
- Per-attempt latency, error labels, retries.
- In-flight commands/pool usage.
- Retry policy thay đổi sau upgrade.

### Lớp 4 — NoSQL backend

- Hot partition/shard, CPU, disk, network.
- Throttling/quorum timeouts.
- Replication lag, leader elections/failovers.
- Compaction, index build, repair, checkpoint/flush.
- Conditional write contention/LWT.

### Lớp 5 — Outcome reconciliation

- Có committed records matching operationId không?
- Pending unknown operations bao nhiêu?
- Outbox/CDC có lag không?
- Có duplicate effects vì retry không-idempotent không?

### 40.1. Một nguyên nhân có thể tạo nhiều triệu chứng

Hot partition làm p99 tăng → client timeout → automatic retry → tăng load → nhiều conditional conflicts. Đừng chữa triệu chứng bằng cách tăng timeouts/retries trước khi xác định nguồn.

### 40.2. Hệ thống có thể phục hồi nhưng backlog không tự hết

Sau database ổn định, reconciliation queue và outbox backlog có thể tồn tại. Cần đo drain rate và tránh phát repair load làm cluster quá tải lần nữa.

## 41. Runbook cụ thể: một CreateOrder có outcome UNKNOWN

### Bước 1 — Dừng việc retry sinh ID mới

Giữ nguyên tenantId, operationId và business payload. Nếu phía client đã retry bằng key mới, cần xác định duplicate risk và ngừng phát thêm side effects.

### Bước 2 — Tìm operation record

Tra nguồn có thẩm quyền bằng tenantId+operationId, theo read consistency phù hợp. Không chỉ nhìn cache/search projection.

### Bước 3 — Nếu COMMITTED

So payload digest/resourceId, trả kết quả cũ và ghi nhận reconciliation success. Không tạo Order thứ hai.

### Bước 4 — Nếu REJECTED

Xác định rejection có phải của **cùng attempt/operation** và không còn prior unknown attempts. Trả business response đúng semantics.

### Bước 5 — Nếu IN_PROGRESS

Poll/backoff theo budget; kiểm tra worker/transaction không bị kẹt. Không tự chuyển IN_PROGRESS sang FAILED chỉ vì quá mốc chờ mà không có recovery protocol.

### Bước 6 — Nếu record vắng mặt

Kiểm tra operation status có được ghi cùng transaction không, nguồn đọc có authoritative không, retention của record còn không. Absent có thể không đủ chứng minh no commit.

### Bước 7 — Nếu vẫn UNKNOWN

Ghi pending reconciliation, trả trạng thái không kết luận theo API contract, giới hạn retries và escalate theo severity.

### Bước 8 — Đối soát phụ thuộc

Với Saga, xác định Order source, Inventory reservation, Payment capture và outbox events riêng; không dùng một service chưa thấy record làm chứng cứ dịch vụ khác chưa commit.

### Bước 9 — Theo dõi đến terminal state

Ghi resolution time và final evidence. Đừng xóa UNKNOWN record chỉ vì API request đã kết thúc.

## 42. Runbook: ConditionalCheckFailed tăng đột biến

### 42.1. Xác định operation class

Unique claim, optimistic version, stock reserve hay CAS counter? Expected conflict baseline khác nhau.

### 42.2. Đối chiếu first-attempt timeout

Nếu timeouts tăng trước conflicts, có thể retries sau unknown commit bị reject vì key đã tồn tại. Tỷ lệ conflict tăng không nhất thiết là nhiều người dùng tạo trùng thật.

### 42.3. Đọc existing owner

Kiểm tra owner/version, tenant và idempotency digest. Phân loại same-operation replay vs competing operation vs stale version.

### 42.4. Theo dõi hot keys/partitions

Không log plaintext key vào metric label; dùng sampled trace/hashing với quyền truy cập, và các shard-level metrics engine cung cấp.

### 42.5. Chặn retry vô ích

Nếu condition không thể trở thành true nếu không có state change, trả conflict hoặc refresh state; không retry cùng expectedVersion 1.000 lần.

### 42.6. Tìm lỗi logic sau deploy

Một code mới có thể tăng expectedVersion sai hoặc gửi conditionExpression không còn phù hợp schema. Đối chiếu deploy timeline, payload validation, request traces và pre/post data.

## 43. Runbook: Retry storm

### 43.1. Nhận diện

~~~text
Offered logical ops/sec stable.
Physical DB attempts/sec sharply increases.
Retry amplification jumps from 1.05 to 2.8.
DB throttles and p99 rise together.
~~~

### 43.2. Kiểm tra nested retries

HTTP client, gateway, service wrapper và SDK có đang retry độc lập? Một nâng cấp driver có thể thay retry defaults.

### 43.3. Giảm tác động

- Bật bounded concurrency/rate limits.
- Giảm hoặc tạm vô hiệu hóa retries không an toàn.
- Áp deadline và jitter.
- Ưu tiên traffic critical.
- Không kích hoạt kill/replay jobs đồng loạt trên source đang chậm.

### 43.4. Không tắt idempotency/status lookup

Khi giảm retry tải, vẫn phải giữ khả năng reconcile UNKNOWN và tránh duplicate effects.

### 43.5. Quan sát sau sửa

Physical attempts/sec có giảm? p99/timeout có giảm? Unknown backlog có đang được giải quyết? Business success và correctness có giữ nguyên?

## 44. Runbook: Source khỏe nhưng API vẫn báo lỗi ghi

### 44.1. Xác định nơi lỗi phát sinh

Gateway timeout? Java GC? Driver pool exhausted? Network giữa services? Cache write failure? Outbox publisher?

### 44.2. So bằng chứng commit

Source operation status/transaction log có committed records matching operationId không? Nếu có, không đổi backend successful write thành business failure chỉ vì HTTP ACK mất.

### 44.3. Đừng xóa dữ liệu đã commit để “đồng bộ log”

Log API “failed” có thể do response loss, không phải quyết định nghiệp vụ undo transaction. Dùng reconciliation và correction workflow hợp lệ nếu cần.

### 44.4. Kiểm tra đọc qua replica/index

API tạo thành công nhưng status GET trả NOT_FOUND từ GSI/search lag; đó là projection/read freshness. Không phân loại source write UNKNOWN nếu nguồn commit đã rõ.

### 44.5. Khắc phục đường phản hồi

Đo client-side connection resets, TLS, proxy/load balancer timeouts, response buffering và JSON serialization errors.

## 45. Sự kiện lỗi có điều kiện phải đi cùng phiên bản dữ liệu

Một update:

~~~text
Order O101 expectedVersion=7
Current source version=8
~~~

Backend reject CAS. Để chẩn đoán, cần biết:

- Client đọc version 7 từ đâu (cache/replica)?
- Bao lâu từ read tới update?
- Một update hợp lệ khác đã commit version 8?
- Retry có cố dùng version 7 nhiều lần?
- Có code ghi đè version từ stale DTO?

### 45.1. Nếu stale read bình thường

Hãy refresh từ nguồn hoặc trả 409 theo API contract. Đừng tăng retry attempts vô hạn khi expected version không được cập nhật.

### 45.2. Nếu concurrent legitimate writes

Conflict rate có thể phản ánh contention thực. Có thể cần giảm critical section, partition workload, serialize một vài commands hoặc thiết kế commutative operations theo invariant.

### 45.3. Nếu duplicate retry

Một update trước đã commit version 8 nhưng ACK mất; retry với expectedVersion=7 nhận conflict. Reconcile theo operationId/result version, không gọi update lại với expectedVersion=8 nếu điều đó làm apply effect hai lần.

### 45.4. Log current version có quyền kiểm soát

Source version thường hữu ích và ít nhạy cảm hơn raw payload, nhưng không phát ID/tenant/raw values trong metrics có cardinality không giới hạn.

## 46. Không có correlation IDs thì khó điều tra retries

Một flow có các identifiers:

~~~text
business operationId = CREATE-O101-CLIENT7
HTTP requestId       = HTTP-174
traceId              = TRACE-A
DB attempt #1        = DBREQ-301
DB attempt #2        = DBREQ-302
~~~

### 46.1. Một operation nhiều HTTP requests

Mobile client có thể POST lại sau mất kết nối, sinh requestId/traceId mới nhưng giữ operationId ổn định.

### 46.2. Một HTTP request nhiều DB attempts

Driver tự retry trong cùng method call; requestId vẫn một, nhưng wire requests có identifiers khác nhau.

### 46.3. Metrics không giữ high-cardinality IDs

operationId và requestId thuộc logs/traces, không gắn vào Counter tags. Dashboard tổng hợp theo operation class, error kind, region và cohort.

### 46.4. Đường xác minh

Trace từ API tới DB status lookup phải có kết nối bằng operationId hoặc safe hashed ID, để tìm outcome cuối cùng sau khi trace ban đầu đã kết thúc.

## 47. Mỗi lỗi là event hay trạng thái?

Một driver timeout là **event** xảy ra tại t1. Một operation unresolved là **state** kéo dài từ t1 tới t2.

### 47.1. Event counters

~~~text
timeouts_total (increment on timeout event)
conditional_conflicts_total (increment on conflict)
retry_attempts_total (increment per retry)
~~~

### 47.2. State gauges

~~~text
unknown_outcomes_pending
oldest_unknown_age_seconds
reconciliation_queue_depth
~~~

### 47.3. Event/state mapping

Một operation được reconcile COMMITTED không xóa timeout event từng xảy ra. Nó làm gauge unknown pending giảm và tăng counter reconciliation_completed.

### 47.4. Tránh đếm sai sau restart

Gauge unknown pending nên dựa vào durable operation state hoặc cách tổng hợp có bảo đảm, không chỉ biến static/in-memory mất khi process restart. Event counters có thể reset và backend monitoring phải xử lý restart.

## 48. Failure injection: tạo ACK loss một cách có chủ đích

Một test timeout đơn giản “delay database 2 giây” chưa đủ kiểm tra unknown commit. Cần có test **commit thực sự thành công nhưng response không tới client**.

### 48.1. Các vị trí có thể tiêm lỗi

~~~text
Before client sends request
After request is sent, before server accepts
After server accepts, before commit
After commit, before response leaves server
After response leaves server, before client receives
After client receives ACK, before service sends HTTP response
~~~

### 48.2. Bài test quan trọng

~~~text
1. Start logical CREATE with operationId K.
2. Intercept/drop the backend success response after commit.
3. Observe client timeout and classify UNKNOWN.
4. Retry/status-check with same operationId K.
5. Assert exactly one committed business resource/effect.
6. Assert metrics show initial UNKNOWN then COMMITTED.
~~~

### 48.3. Simulate network partition safely

Chỉ test trên môi trường cô lập/được phép, có kiểm soát TTL/cleanup; không cắt kết nối production hoặc cố gây overload trên dữ liệu người dùng.

### 48.4. Test không nên suy từ timing may mắn

Sử dụng fault proxy/hook/barrier để đảm bảo commit-before-drop khi cần. Nếu chỉ tăng latency ngẫu nhiên, test có thể vô tình đo failure-before-commit rồi bỏ sót trường hợp nguy hiểm nhất.

### 48.5. Sau test, xác minh nguồn

Đếm committed records và inspect operationId/payload digest theo authoritative read. Không chỉ assert HTTP trả 500/504.

## 49. Test matrix: timeout, retry, conditional và UNKNOWN

| Test | Khi nào fault xảy ra? | Điều phải xác minh |
|---|---|---|
| Request rejected before send | Validation | Không có side effect, không UNKNOWN |
| Connect timeout | Chưa kết nối được | Retry classifier đúng, không nhận bừa rollback proof |
| Response lost after commit | Sau source commit | UNKNOWN → COMMITTED, không duplicate |
| Retry same idempotency key | Sau timeout | Trả kết quả cũ |
| Retry different payload, same key | Sau timeout | Reject payload mismatch |
| Retry with fresh key | Client bug | Test phát hiện duplicate-risk |
| Conditional insert same owner | Attempt #1 commit, ACK mất | Conflict của retry được reconcile |
| Conditional insert other owner | Competing operation | Trả business conflict |
| CAS stale version | Concurrent writer | Rejection expected, không retry vô hạn |
| Throttle burst | Capacity pressure | Bounded jitter, no storm |
| LWT timeout | Coordinator mất ACK | Không suy not-applied |
| Redis INCR ACK loss | Sau INCR | Không increment hai lần cho một intention |
| Driver auto retry | Network transient | Physical attempt count đúng |
| Gateway + SDK retry | Hai tầng cùng retry | Total amplification được đo |
| Region failover | Replication lag | Không dùng Region B absent làm proof |
| CDC lag | Source committed | Projection freshness riêng |
| Reconciliation unavailable | Status source outage | Unresolved persists; alert age |
| Operation record TTL expiry | Retry rất muộn | Không duplicate effect |
| Restart service | Unknown queue persisted | State không biến mất |
| Several reconcilers | Concurrency | Single terminal transition |
| Low sample count | Metric window ít requests | Không tạo alert ratio nhiễu |

### 49.1. Test final status không double-count

Nếu hai workers cùng đọc UNKNOWN và cùng kết luận COMMITTED, application chỉ ghi một terminal state transition bền vững. Metrics event counters có thể cần tổng hợp từ transition audit để chống double-count sau crash.

### 49.2. Test perf under fault

Không chỉ kiểm chứng một operation. Khi timeout 10% ở 10.000 ops/sec, theo dõi p99, physical attempts, throttle, queue và unknown backlog trong khi injection được bật.

### 49.3. Test recovery

Sau khi tắt injection, unknown backlog có drain hết trong SLO? Có retry storm tiếp diễn không? Có duplicate data sau repair hay không?

## 50. Prometheus: ví dụ truy vấn metrics, không trộn mẫu số

Giả sử exporter có counters:

~~~text
db_attempts_total{operation_class="order.create",result="timeout"}
db_attempts_total{operation_class="order.create",result="success"}
db_retry_attempts_total{operation_class="order.create"}
logical_operations_started_total{operation_class="order.create"}
logical_operations_initial_unknown_total{operation_class="order.create"}
~~~

### 50.1. Attempt timeout ratio

~~~promql
sum(rate(db_attempts_total{operation_class="order.create",result="timeout"}[5m]))
/
sum(rate(db_attempts_total{operation_class="order.create"}[5m]))
~~~

Tỷ lệ theo physical attempts, không theo logical operations.

### 50.2. Retry amplification

Nếu mỗi logical operation luôn có một base attempt của loại DB command đang được đo:

~~~promql
sum(rate(db_attempts_total{operation_class="order.create"}[5m]))
/
sum(rate(logical_operations_started_total{operation_class="order.create"}[5m]))
~~~

Công thức này chỉ là proxy đúng khi số DB attempts cơ bản trên mỗi operation là một và windows cân bằng. Nếu business operation có hai inserts bình thường, cần đếm attempt theo DB command class hoặc dùng counter cho retries.

### 50.3. Initial unknown ratio

~~~promql
sum(increase(logical_operations_initial_unknown_total{
  operation_class="order.create"
}[1h]))
/
sum(increase(logical_operations_started_total{
  operation_class="order.create"
}[1h]))
~~~

Đây là xấp xỉ time-window khi events unknown được phát trễ hơn started. Nếu cần chính xác cohort, tổng hợp từ durable operation status theo **start-time cohort** thay vì chỉ lấy hai counters trong cùng window.

### 50.4. Unresolved ratio sau T cần cohort-aware data

Không lấy gauge unknown_outcomes_pending chia rate(logical_operations_started_total): đơn vị không cùng nhau (count chia count/sec). Tính từ bảng/audit:

~~~text
SELECT count(logical operations unresolved after T)
     / count(logical operations whose start time <= now-T)
FROM committed operation tracking data
WHERE cohort_start_in_window(...)
~~~

Đây là pseudocode về phương pháp đo, không phải một câu SQL có thể chạy trực tiếp trên mọi NoSQL.

### 50.5. Nếu denominator bằng 0

Không trả 0% và kết luận khỏe khi không có writes. Dashboard nên thể hiện no data/insufficient samples; alert ratio đặt minimum volume để tránh noise.

### 50.6. Tránh metric arithmetic vô nghĩa

Không cộng timeout rate theo attempts với conditional conflict rate theo logical operations rồi nói “tỷ lệ lỗi 7%”. Nếu cần một tổng, xây outcome taxonomy **mutually exclusive trên cùng cohort** trước.

## 51. Bảng trạng thái vận hành trong NoSQL

Một operation tracking table có thể dùng các fields:

| Field | Ý nghĩa |
|---|---|
| tenantId | Phạm vi quyền và uniqueness |
| operationId | Stable logical intent ID |
| operationClass | order.create / inventory.reserve |
| payloadDigest | Kiểm tra retry cùng nội dung |
| state | IN_PROGRESS, COMMITTED, REJECTED, UNKNOWN |
| attemptCount | Số attempts đã phát (cần phân biệt command) |
| firstAttemptAt | Bắt đầu |
| firstUnknownAt | Thời điểm đầu tiên không xác minh được |
| lastCheckedAt | Lần reconciliation gần nhất |
| nextReconcileAt | Lịch kiểm tra tiếp theo |
| resourceId | Entity được tạo hoặc cập nhật nếu có |
| sourceVersion | Bằng chứng version/commit khi biết |
| terminalAt | Khi đã được xác minh terminal |
| errorCategory | Phân loại nguyên nhân |

### 51.1. Tránh cập nhật state dựa trên thời gian đơn thuần

Không tự đổi UNKNOWN → REJECTED nếu đã 5 phút mà không thấy kết quả, trừ khi có một protocol/consistency guarantee chứng minh request không thể commit.

### 51.2. Atomic terminal transition

Nhiều reconcilers có thể cùng kiểm tra. Dùng conditional state update để chỉ một worker chuyển UNKNOWN → COMMITTED/REJECTED khi đã có bằng chứng, tránh trạng thái đi lùi.

### 51.3. Version monotonicity

Một event đến muộn không được làm COMMITTED quay về UNKNOWN. Định nghĩa state machine với quy tắc terminal states và owner riêng cho correction.

### 51.4. Retention

Giữ tracking data ít nhất qua cửa sổ retry/reconciliation, cần cân nhắc audit retention và privacy policy. Nếu xóa sớm, retries rất muộn có thể tạo side effects mới.

### 51.5. Capacity

Nếu mỗi user request ghi một tracking record và nhiều reconciliation updates, operational tracking cũng tiêu thụ write capacity/index/compaction. Thiết kế partition key và TTL theo access patterns.

## 52. Khi nào cần tự động sửa và khi nào cần con người?

### 52.1. Tự động reconcile được

Một Order create có stable orderId/operationId, source record matching digest, và các downstream steps có idempotent status. Worker có thể tự đánh dấu COMMITTED.

### 52.2. Cần kiểm tra thủ công

Payment provider không cung cấp idempotency/status API đáng tin, hoặc đã có hai captures khác nhau và không thể xác định ai sở hữu. Hệ nên giữ case UNRESOLVED, không phát một capture mới theo đoán mò.

### 52.3. Không tự rollback bên ngoài authority

Nếu một mutation đã commit, quyết định undo thường là business command mới (cancel/refund), không xóa trực tiếp data để metrics “trông đẹp”.

### 52.4. Escalation criteria

Dựa trên:

- Business severity (payment vs catalog metadata).
- Age of unknown.
- Tỷ lệ/giá trị tiền có rủi ro.
- Có dấu hiệu duplicate effect hay không.
- Khả năng source mất dữ liệu/replica failover.

### 52.5. Điều tra an toàn

Với các lệnh nhạy cảm, read-only investigation trước khi mutate. Mọi manual correction cần audit trail, authorization và idempotency của chính correction operation.

## 53. Phân tích nguyên nhân gốc bằng một timeline

Giả sử dashboard cho thấy:

~~~text
09:00:00 Product release raises offered write rate.
09:00:15 Top partition CPU/latency increases.
09:00:18 Client socket timeouts increase.
09:00:20 SDK retries double physical attempts.
09:00:23 Conditional conflicts on same hot key increase.
09:00:30 UNKNOWN write backlog starts growing.
09:04:00 Release rolled back; source latency recovers.
09:08:00 Reconciliation backlog drains.
~~~

### 53.1. Root cause không nhất thiết là “nhiều conflicts”

Conflicts có thể là hậu quả của hot partition và retries. Sửa code catch conflict không giải quyết thiết kế partition hoặc tải đột biến.

### 53.2. Đo trước/sau rollback

Kiểm tra actual logical throughput, retry amplification, p99, conditional conflicts theo operation class và unknown backlog.

### 53.3. Giữ chứng cứ

Lưu deployment marker, metrics/traces phù hợp retention, client/driver versions và source commit audit. Không cần chứa PII/raw payload để điều tra hầu hết timeout.

### 53.4. Làm rõ customer impact

Bao nhiêu logical operations nhận UNKNOWN? Bao nhiêu được xác nhận COMMITTED sau đó? Có duplicate effects không? Thời gian tới kết quả cuối là bao lâu?

## 54. Anti-patterns phổ biến

| Anti-pattern | Hậu quả | Hướng thay |
|---|---|---|
| Catch timeout rồi trả FAILED | Một committed write bị báo không tồn tại | Trạng thái UNKNOWN + reconcile |
| Retry với ID mới mỗi lần | Duplicate orders/payments | Stable operationId |
| Driver retry và service retry không giới hạn | Retry storm | Shared deadline/budget/backoff |
| Coi mọi 409/condition failure là outage | False alerts | Phân loại business vs infra |
| Coi duplicate key luôn là retry thất bại | Bỏ qua first attempt committed | Read owner/payload digest |
| Gộp SDK attempts vào business throughput | Đếm một lệnh nhiều lần | Logical vs physical metrics |
| Một Counter “errors_total” duy nhất | Không điều tra được nguyên nhân | Taxonomy có kiểm soát |
| Đếm UNKNOWN là failed | Sai tỷ lệ thành công | Three-state outcome model |
| Đếm UNKNOWN là successful vì “có thể commit” | Che rủi ro correctness | Pending + reconciliation |
| Count retry successes như writes mới | Thổi phồng throughput | Operation-level terminal status |
| Expose raw operationId/email trong metric label | High cardinality, PII leakage | Structured logs + safe tags |
| Không theo dõi unknown age | Case bị kẹt nhiều giờ | Backlog/oldest age/SLO |
| Tăng timeout liên tục để hết lỗi | Queue tăng và UX xấu | Tìm bottleneck, bounded concurrency |
| Retry CAS stale expectedVersion vô hạn | Không thể thành công nếu không refresh | 409/refresh/merge |
| Dùng search index NOT_FOUND để kiểm chứng create | False negative do indexing lag | Source authority |
| Dùng eventual Region B NOT_FOUND sau Region A write | Kết luận sai | Home region/consistency |
| Thấy status record vắng là chưa commit | Status có thể ghi sau source | Atomic status hoặc evidence |
| Metric “retries=0” dù SDK auto retry | Không thấy amplification | Driver telemetry |
| Bỏ 5xx/timeout khỏi latency distributions | SLO trông quá đẹp | Error/timeout budget riêng |
| Ghi operation tracking vào Redis cache có thể evict | Mất bằng chứng | Durable source phù hợp |
| Xóa UNKNOWN queue khi process restart | Mất reconciliation | Persist state/checkpoints |
| Đếm reconciliation attempts thành unknown cases | Sai mẫu số | Unique operationId |
| Không test mất response sau commit | Không phát hiện duplicate retries | Fault injection ACK loss |
| Chỉ làm unit test một thread | Bỏ race terminal transitions | Multi-worker conditional tests |
| Coi HTTP 202 PENDING là commit thành công | Lẫn accepted và committed | Clear operation contract |
| Bỏ qua correction audit | Không truy vết sửa dữ liệu | Audited domain command |

## 55. Checklist thiết kế quan sát trước khi triển khai

### 55.1. Về operation semantics

- Logical operation và physical attempts có định nghĩa riêng?
- Stable operationId/idempotency key trên tất cả retries?
- Có operation outcome UNKNOWN thay vì chỉ SUCCESS/FAILED?
- Commit proof theo source/durability semantics nào?
- Conditional rejection có được phân loại theo business reason?

### 55.2. Về retries

- Driver/SDK có tự retry không?
- Gateway/service/client có retry riêng không?
- Có overall deadline, max attempts, jitter, retry budget?
- Với mutation không idempotent, retry có an toàn không?
- Client có giữ cùng payload/operationId khi retry?

### 55.3. Về metrics

- Timeout ratio theo attempts và logical operations riêng?
- Retry amplification được đo đúng DB command class?
- Conditional conflict theo attempts và business outcomes riêng?
- Initial unknown ratio và unresolved-after-T ratio có cohort rõ?
- Backlog, oldest age và resolution latency có dashboard?
- Có p99, throttles, node/partition metrics và error taxonomy?

### 55.4. Về logs/traces

- Trace có attemptNumber và logical operation liên kết?
- Logs giữ failure cause/error labels/region/latency?
- Không lưu PII/raw keys ở metrics labels?
- Có retained evidence khi process restart/failover?

### 55.5. Về vận hành

- Có endpoint/status lookup để reconcile?
- Có terminal state atomic update và retention?
- Có runbook unknown writes, retry storm, conditional conflict?
- Có tests ACK loss, stale replica, region failover, transaction ambiguity?
- Đo duplicate business effects và data correctness sau recovery?

## 56. Hệ thống nhỏ có cần mọi metric không?

Không nhất thiết dựng toàn bộ stack ngay từ đầu. Ưu tiên theo rủi ro:

### Mức cơ bản

- Số logical requests và final outcomes.
- Database attempt errors/latency.
- Timeout và retry counts.
- Conditional failure rate theo operation class.
- Log traceId và stable operationId có bảo vệ.

### Mức giao dịch quan trọng

- Durable idempotency record.
- Initial UNKNOWN và unresolved aging.
- Reconciliation worker/status endpoint.
- Duplicate effect indicators.
- Fault-injection test sau commit.

### Mức phân tán lớn

- Per-Region/per-partition dashboards.
- Driver-level retry amplification.
- Saga/outbox/CDC cross-service lineage.
- Cohort-based SLO, runbooks và automated safe reconciliation.

Lựa chọn phụ thuộc business criticality; một hệ thanh toán ít traffic vẫn có thể cần unknown-write correctness mạnh hơn một hệ catalog cực lớn.

## 57. Bài tập 1 — timeout không bằng rollback

Một Java service tạo Order O101 bằng insert. Backend đã commit O101 nhưng ACK bị mất. Driver ném read timeout; API trả HTTP 504.

1. Đâu là kết quả của physical attempt?
2. Đâu là trạng thái đúng của logical operation ngay khi API nhận timeout?
3. Có được đổi thẳng sang FAILED không?
4. Nếu client retry với orderId=O102, rủi ro nào xuất hiện?
5. Đề xuất stable operationId và status lookup để trả kết quả cuối cùng.
6. Những metrics nào cần tăng ở thời điểm timeout và tại thời điểm reconciliation hoàn tất?

## 58. Bài tập 2 — phân biệt các loại timeout

Các tình huống:

~~~text
A. Server selection timeout before any command sent.
B. Timeout waiting for pooled connection.
C. Socket read timeout after request was dispatched.
D. HTTP gateway deadline exceeded after service committed.
E. Conditional update returned version conflict.
F. Database returned throttling response.
~~~

1. Trường hợp nào có thể chắc chắn chưa gửi DB command nếu instrumentation xác nhận?
2. Trường hợp nào có khả năng unknown commit?
3. Trường hợp nào là definite conditional rejection?
4. Trường hợp nào nên backoff vì capacity?
5. Tạo mapping tới taxonomy REQUEST_NOT_SENT, OUTCOME_UNKNOWN, CONDITION_REJECTED và THROTTLED.

## 59. Bài tập 3 — retry amplification

Một hệ ghi:

~~~text
Logical writes initiated:       10,000
First DB attempts:              10,000
Retry attempts:                  2,500
Total physical DB attempts:     12,500
Logical operations with retry:   1,800
~~~

1. Tính attempts/logical write.
2. Tính retry attempts fraction trên tổng attempts.
3. Tính tỷ lệ logical operations từng phải retry.
4. Vì sao ba chỉ số khác nhau?
5. Nếu một operation có 10 retries, nó đóng góp bao nhiêu vào từng numerator?
6. Nếu mỗi logical write bình thường có hai DB calls, phải thay công thức amplification thế nào?

## 60. Bài tập 4 — tỷ lệ unknown ban đầu và sau reconciliation

Một cohort có 2.000 logical writes. Sau first deadline:

~~~text
120 operations UNKNOWN.
Trong 120:
  110 được xác minh COMMITTED.
    8 được xác minh DEFINITELY_REJECTED.
    2 còn UNKNOWN sau 60 giây.
~~~

1. Tính U_initial.
2. Tính U_unresolved(60s) khi cả cohort đủ tuổi 60 giây.
3. Có được coi 120 là write failures không?
4. Vì sao final COMMITTED không xóa timeout event đã xảy ra?
5. Vẽ state transitions cho ba loại outcome.
6. Nếu một operation còn UNKNOWN qua 24 giờ, alert nào nên kích hoạt?

## 61. Bài tập 5 — cohort bias

Trong khoảng 10:00–10:01 có 1000 operations mới bắt đầu; chỉ 200 đã qua 60 giây khi dashboard lấy mẫu.

1. Có thể tính U_unresolved(60s) trên cả 1000 operations không?
2. Denominator đúng phải chọn ra sao?
3. Nếu metrics started và unknown events nằm ở hai phút khác nhau, rate-of-counters ratio có nhược điểm gì?
4. Thiết kế truy vấn dựa trên durable operation records.
5. Khi sample count rất nhỏ, alert ratio cần safeguards gì?

## 62. Bài tập 6 — conditional failure của retry

Timeline:

~~~text
t1 PutItem if attribute_not_exists(PK) sent.
t2 Backend commits Order O101.
t3 Response lost -> client timeout.
t4 Client retries same conditional PutItem.
t5 Backend says ConditionalCheckFailed.
~~~

1. Attempt #2 có commit không?
2. Có thể kết luận logical CREATE thất bại không?
3. Phải đọc item nào để xác minh owner?
4. Nếu existing operationId giống request, final result là gì?
5. Nếu existing operationId khác request, xử lý ra sao?
6. Nếu source read eventual chưa thấy item, được phép cache NOT_FOUND không?

## 63. Bài tập 7 — optimistic concurrency

Order v7 có status DRAFT. Hai writers A và B đều đọc v7; A confirm Order thành v8, B muốn cancel theo expectedVersion=7.

1. A conditional update thành công có ý nghĩa gì?
2. B nhận version conflict có phải database outage không?
3. Nếu B retry với version=7 mười lần, điều gì xảy ra?
4. Khi nào nên refresh state và trả 409/merge theo domain?
5. Nếu A timeout sau commit rồi retry, version conflict có thể là replay success không?
6. Đề xuất metric phân biệt legitimate concurrent conflict và stale retry.

## 64. Bài tập 8 — Cassandra LWT

Một service gọi:

~~~sql
INSERT INTO username_claims (tenant_id, username, owner_id)
VALUES ('T17', 'alice', 'U101')
IF NOT EXISTS;
~~~

Request timeout. Retry nhận applied=false.

1. applied=false của retry nói điều gì về attempt đó?
2. Tại sao chưa thể kết luận first attempt không được áp dụng?
3. Đọc ownerId để phân loại same-owner replay vs other-owner conflict.
4. LWT contention khác regular write throughput ở điểm nào?
5. Cần ghi read consistency/serial consistency trong benchmark và logs ra sao?
6. Nếu owner đổi giữa các attempts, cần generation/fencing gì?

## 65. Bài tập 9 — Redis increment sau ACK loss

Client gửi:

~~~text
INCRBY inventory:counter 1
~~~

Redis thực hiện, nhưng ACK không tới. Client retry INCRBY.

1. Kết quả cuối của counter có thể tăng mấy đơn vị?
2. Vì sao atomic command không đồng nghĩa idempotent?
3. Thiết kế Lua script kết hợp operationId marker và increment trong một atomic Redis execution.
4. Nếu Redis key marker có TTL ngắn và retry rất muộn, duplicate risk là gì?
5. Nếu Redis là cache chứ không là authority, có nên dùng làm ledger duy nhất không?
6. Theo dõi các metrics retry và duplicate-effect nào?

## 66. Bài tập 10 — MongoDB duplicate key

MongoDB source có unique index trên (tenantId, orderNumber). Một insert báo network timeout; retry tạo lại cùng orderNumber rồi nhận duplicate key.

1. Duplicate key có thể là kết quả của ai?
2. Có cần đọc existing document và operationId/payloadDigest không?
3. Nếu existing thuộc chính request đầu, API nên trả gì?
4. Nếu existing thuộc request khác, API nên trả gì?
5. Retryable writes driver khác application idempotency thế nào?
6. Một transaction commit mang UnknownTransactionCommitResult cần xử lý ra sao?

## 67. Bài tập 11 — DynamoDB GSI và reconciliation sai

Một PutItem đã commit trên base table. Client timeout. Service query GSI theo externalId rồi thấy empty và kết luận “không commit”.

1. GSI empty có chứng minh base table không có record không?
2. Có thể dùng strongly consistent GetItem theo known PK trong phạm vi API hỗ trợ không?
3. Nếu chưa có PK, nên thiết kế operation claim/status record như thế nào?
4. Vì sao retry PutItem với ID mới là nguy hiểm?
5. Theo dõi GSI propagation lag và source UNKNOWN riêng ra sao?

## 68. Bài tập 12 — retry storm

Hệ nhận 10.000 logical writes/sec. Khi p99 database tăng, 40% first attempts timeout và mỗi lỗi đều retry hai lần không giới hạn bởi overall deadline.

1. Ước lượng physical attempts/sec nếu mọi timeout đầu tiên đều phát thêm hai attempts (giả sử các retries không tiếp tục timeout).
2. Nếu retries cũng timeout, vì sao kết quả thực có thể cao hơn?
3. Nếu gateway và SDK cùng retry, amplification tăng theo những bước nào?
4. Đề xuất jitter, retry budget, rate limit và max outstanding.
5. Metrics nào cho biết generator offered RPS không đổi nhưng DB attempts tăng?
6. Có nên tăng timeout gấp mười lần ngay lập tức để “giảm lỗi” không? Vì sao?

## 69. Bài tập 13 — dashboard bốn signals

Thiết kế dashboard cho service đặt chỗ với các metrics:

~~~text
HTTP logical requests
DB physical attempts
Driver socket timeouts
SDK retries
CAS version conflicts
Unresolved bookings
Duplicate booking effects
~~~

1. Chọn Counter/Gauge/Histogram cho từng signal.
2. Xác định denominator của timeout rate theo attempts và theo logical operations.
3. Thiết kế metric U_unresolved(5min) theo cohort.
4. Thêm phân loại theo operationClass, Region và tenant tier.
5. Những labels nào có cardinality/PII risk?
6. Đề xuất ba alerts có runbook rõ ràng.

## 70. Bài tập 14 — tracing nhiều attempts

Một trace:

~~~text
POST /orders operationId=K
  DB attempt #1 -> socket timeout 700ms
  backoff -> 100ms
  DB attempt #2 -> conditional conflict 50ms
  status lookup -> committed 80ms
~~~

1. Root logical outcome là gì nếu status record xác minh cùng K/payload?
2. Những attempt spans nào nên ghi ERROR hoặc conflict?
3. Vì sao parent logical operation không được xem là failed chỉ vì child attempt timeout?
4. End-to-end latency xấp xỉ bao nhiêu, bỏ qua overhead?
5. Những fields nào nên là span attributes, những fields nào chỉ nên ở protected logs?
6. Nếu trace sampling mất first HTTP request nhưng second retry trace còn, làm sao nối chúng bằng operationId?

## 71. Bài tập 15 — PromQL và mẫu số

Metrics trong 5 phút:

~~~text
db attempts: 12,000
attempt timeouts: 600
logical operations initiated: 10,000
logical operations with at least one timeout: 450
logical operations initially UNKNOWN: 120
logical operations unresolved after 60s in matured cohort: 10
matured cohort size: 9,000
~~~

1. Tính attempt timeout ratio.
2. Tính logical timeout ratio.
3. Tính attempts/logical operations, với giả định một base attempt mỗi logical operation.
4. Tính U_initial.
5. Tính U_unresolved(60s) trên matured cohort.
6. Vì sao không lấy unknown_outcomes_pending chia attempts/sec?
7. Viết một PromQL query cho attempt timeout ratio theo operationClass.

## 72. Bài tập 16 — source vs projection

Order Service đã commit O101 v8. Một event outbox chưa được search index apply. Client GET search trả NOT_FOUND, còn Order API authoritative trả FOUND.

1. Source write có phải UNKNOWN không nếu có commit evidence?
2. Search freshness khác source write outcome ra sao?
3. Những metrics CDC/outbox/search nào cần ghi?
4. Có nên retry CreateOrder chỉ vì search chưa thấy không?
5. Nếu search index nhận event hai lần, có nên tạo hai orders không?
6. Thiết kế API read-your-writes không phụ thuộc immediate search refresh.

## 73. Bài tập 17 — multi-Region

Region A nhận conditional create và ACK thành công. Region B chưa replicate, client ở B không thấy record nên retry với ID mới.

1. Vì sao Region B NOT_FOUND không đủ để kết luận A không commit?
2. Nếu global table dùng eventual conflict resolution, những business invariants nào có nguy cơ?
3. Đề xuất home Region/operation routing để giữ authority.
4. Khi Region A failover, fencing/epoch có vai trò gì?
5. Đề xuất breakdown metrics theo Region và consistency mode.
6. Làm thế nào để reconcile khi operation status chỉ có ở Region đang lỗi?

## 74. Bài tập 18 — unknown outcome trong Saga

Checkout gồm:

~~~text
OrderCreated
ReserveInventory
CapturePayment
ArrangeShipment
~~~

Payment Provider đã capture nhưng response timeout; Order Service vẫn đang PENDING.

1. Payment outcome được quyết định bởi owner nào?
2. Có nên gọi CapturePayment lần nữa với operationId mới không?
3. Provider idempotency key và status endpoint được dùng thế nào?
4. Những states nào cần ở Saga orchestrator?
5. Nếu shipment thất bại sau capture, compensation/refund có phải rollback ACID không?
6. Thiết kế metrics UNKNOWN payment, duplicate captures và reconciliation latency.

## 75. Bài tập 19 — fault injection sau commit

Thiết kế integration test cho CreateOrder qua Java service và NoSQL:

~~~text
1. Send create operation K.
2. Backend commits O101.
3. Fault proxy drops ACK.
4. Client sees timeout.
5. Service retries/reconciles.
~~~

1. Làm sao đảm bảo fault injection xảy ra **sau commit**, không phải trước?
2. Test assertion về số business records cuối cùng?
3. Test assertion về operation state transitions?
4. Metrics cần tăng lần lượt ở first timeout, retry/status lookup và terminal outcome?
5. Nếu hai reconcilers chạy song song, làm sao tránh duplicate terminal transitions?
6. Sau service restart, unresolved task có còn không?
7. Khi fault injection tắt, nên kiểm tra retry backlog/drain rate thế nào?

## 76. Bài tập 20 — phân tích sự cố production

Một dịch vụ SaaS ghi 5.000 logical operations/sec. Sau deploy, telemetry:

~~~text
Before:
  DB attempt p99            = 80ms
  Retry amplification       = 1.03x
  Conditional conflict rate = 2% of CAS attempts
  Unknown after 60s         = 0.01%

After:
  DB attempt p99            = 950ms
  Retry amplification       = 2.70x
  Conditional conflict rate = 18% of CAS attempts
  Unknown after 60s         = 0.9%
  One shard CPU             = 100%
  Average cluster CPU       = 43%
~~~

1. Có thể kết luận database toàn cluster thiếu CPU không?
2. Những mối quan hệ nhân quả nào đáng điều tra giữa hot shard, latency, timeouts, retries và conditional conflicts?
3. Vì sao không nên tăng max retry attempts?
4. Đề xuất cách giảm tác động ngay mà không làm mất khả năng reconcile.
5. Các metrics và traces nào giúp phát hiện shard/hot partition?
6. Làm sao kiểm tra liệu 18% conditional conflicts là real contention hay retries sau commit?
7. Lập kế hoạch rollback/canary và A/B load test có kiểm soát.
8. Tạo post-incident report về số operations UNKNOWN, resolution time và duplicate effects.

## 77. Bài tập 21 — thiết kế contract cho API tạo bản ghi

Một API POST /orders phải hoạt động an toàn khi client mobile mất kết nối và tự retry sau nhiều phút.

Yêu cầu:

1. Định nghĩa operationId, tenant scope và payload digest.
2. Định nghĩa states IN_PROGRESS, COMMITTED, REJECTED và UNKNOWN.
3. Thiết kế endpoint tra operation status.
4. Định nghĩa độ bền/retention của idempotency result.
5. Định nghĩa status HTTP khi request được nhận nhưng commit chưa xác minh.
6. Chỉ ra các trường hợp có thể retry với cùng key và khi phải reconcile.
7. Thiết kế metric U_initial và U_unresolved(T) theo cohort.
8. Thiết kế alert unresolved backlog/age và một runbook manual correction.

## 78. Tổng kết

Quan sát timeout và retry trong NoSQL không chỉ là đếm exception. Một request bị lỗi ở tầng transport vẫn có thể tạo side effect; một conditional rejection vẫn có thể cho thấy database đang bảo vệ invariant đúng. Muốn chẩn đoán chính xác, phải xem **sự thật nghiệp vụ**, **mỗi DB attempt** và **bằng chứng commit** như những lớp riêng.

Những điểm cần nhớ:

1. **Timeout không chứng minh rollback.** Sau khi request đã được dispatch, response loss có thể khiến client không biết backend đã commit hay chưa.
2. **UNKNOWN không phải FAILED.** Giữ trạng thái không xác định, tra nguồn có thẩm quyền và chỉ chốt kết quả khi có bằng chứng.
3. **Logical operation khác physical attempt.** Một người dùng tạo một đơn có thể tạo nhiều driver requests vì retry/status lookup; không được đếm như nhiều đơn hàng.
4. **Tính tỷ lệ với mẫu số phù hợp.** AttemptTimeoutRate, LogicalTimeoutRate, RetryAmplification, ConditionalConflictRate, U_initial và U_unresolved(T) trả lời các câu hỏi khác nhau.
5. **Giữ cohort và tuổi của UNKNOWN.** Một tỷ lệ unknown thấp không an toàn nếu một số payment operations tồn tại không rõ kết quả nhiều giờ.
6. **Conditional failure không mặc định là outage.** CAS version mismatch, unique key conflict và insufficient stock có thể là nghiệp vụ hoặc contention; phân loại theo operation class.
7. **Một retry condition conflict có thể là bằng chứng gián tiếp của commit trước.** Đọc operationId, payload digest, owner/generation để xác minh.
8. **Idempotency key là danh tính của ý định.** Giữ ổn định qua network retries, gateway retries và background reprocessing; database _id duy nhất chưa chắc ngăn duplicate logical actions.
9. **Retry cần budget và jitter.** Retry storm có thể làm backend càng chậm, trong khi timeout lớn không sửa nguyên nhân hot shard/capacity/network.
10. **Driver và application có retry riêng.** Instrument wire/SDK attempts lẫn logical results để nhìn đúng amplification.
11. **NoSQL engines có semantics khác.** MongoDB retryable writes/transaction labels, DynamoDB condition/transaction token, Cassandra LWT và Redis INCR/SET NX đều cần classifier phù hợp.
12. **Replica và search index không xác nhận mọi write.** Một query eventual trả NOT_FOUND không đủ kết luận source commit thất bại.
13. **Quan sát bằng metric, log và trace bổ sung nhau.** Counter/gauge/histogram cho patterns; structured logs/traces cho từng operation có IDs được bảo vệ.
14. **Đo correctness, không chỉ throughput.** Duplicate business effects, false failures, unknown aging và confirmed-missing-after-ACK có thể nghiêm trọng hơn p99.
15. **Fault injection phải bao gồm ACK loss sau commit.** Đây là con đường trực tiếp phát hiện duplicate retries và false FAILED status.
16. **Reconciliation là một workflow có trạng thái.** Giữ audit trail, backoff, terminal transitions nguyên tử, retention và escalation; không để UNKNOWN biến mất khi worker restart.

Câu hỏi then chốt khi thấy một lệnh ghi timeout là:

> **“Chúng ta biết chắc điều gì về attempt đã gửi, điều gì về logical operation, bằng chứng nào cho thấy mutation đã hoặc chưa commit, và cơ chế nào giúp retry mà không tạo thêm tác dụng nghiệp vụ?”**








