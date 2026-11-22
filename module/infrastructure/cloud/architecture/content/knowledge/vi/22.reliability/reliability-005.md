# Retry có backoff, jitter và ngân sách thử lại

## 1. Retry giúp phục hồi lỗi tạm thời, nhưng cũng có thể làm sự cố nặng hơn

Trong hệ thống cloud, một request có thể thất bại vì network chập chờn, connection reset, service quá tải, giới hạn tốc độ, node failover hoặc dependency tạm thời không sẵn sàng. Thử lại (retry) giúp vượt qua một số lỗi ngắn hạn mà không buộc người dùng tự gửi lại thao tác. Tuy nhiên, nếu nhiều client cùng retry ngay lập tức, hệ thống có thể tạo ra một làn sóng request mới đúng lúc dependency đang yếu.

Đây là **retry amplification**: một request ban đầu sinh ra nhiều lần gọi bổ sung, làm tăng tải, queue, latency và số lỗi. Khi các service retry lẫn nhau, số lần gọi có thể nhân lên qua nhiều tầng.

Trong module **CLOUD_ARCHITECTURE**, độ tin cậy được thiết kế từ yêu cầu nghiệp vụ đến compute, network, storage và cách vận hành. Retry là cơ chế phục hồi ở application layer; nó phải phối hợp với timeout, deadline, idempotency, circuit breaker, rate limit và capacity budget để bảo vệ SLO.

Sau bài này, bạn có thể phân biệt lỗi tạm thời, lỗi vĩnh viễn và kết quả không rõ ràng; chọn operation an toàn để retry; tính exponential backoff, giới hạn lần thử và thời gian chờ; dùng jitter để tránh request đồng bộ; thiết kế retry budget; phối hợp timeout/deadline; tránh retry storm ở service và queue; và kiểm chứng bằng metrics, fault injection cùng Well-Architected review.

## 2. Bản chất của retry và ngữ nghĩa kết quả

Retry nghĩa là gửi lại một operation sau khi lần gọi trước không đạt kết quả mong muốn. Điều quan trọng là **không phải mọi lỗi đều có cùng ý nghĩa**.

### 2.1. Ba nhóm kết quả

| Nhóm kết quả | Ví dụ | Hướng xử lý |
|---|---|---|
| Thành công xác định | Server trả response hợp lệ, operation đã hoàn tất | Không retry |
| Thất bại xác định | Validation error, permission denied, business conflict | Không retry tự động; sửa input/quyền hoặc xử lý nghiệp vụ |
| Kết quả không rõ (ambiguous) | Timeout sau khi server có thể đã commit; connection reset trước response | Tra cứu trạng thái hoặc retry cùng idempotency key |

Timeout chỉ nói caller không nhận được response đúng hạn. Nó **không chứng minh** server chưa thực hiện operation. Với POST tạo booking hoặc charge payment, lần gọi đầu có thể đã commit nhưng response bị mất. Retry bằng request mới có thể tạo side effect trùng.

### 2.2. Retryable không đồng nghĩa với mọi 5xx

Phân loại theo semantics và contract của dependency, không chỉ theo HTTP status:

| Tình huống | Thường retry? | Lý do/cách xử lý |
|---|---|---|
| DNS/network transient failure | Có thể | Giới hạn attempt/deadline; xác minh lỗi có thể phục hồi |
| Connection reset trước khi gửi request | Có thể | Có thể chưa tới server; vẫn cần phân biệt phase |
| Timeout sau khi gửi request | Có điều kiện | Kết quả có thể đã commit; cần idempotency/status lookup |
| HTTP 408 | Có thể | Theo contract và deadline |
| HTTP 429 | Có điều kiện | Tuân thủ Retry-After và quota; tránh vượt budget |
| HTTP 502/503/504 | Có thể | Nếu dependency công bố semantics transient và operation an toàn |
| HTTP 400 validation | Không | Cùng request sẽ tiếp tục sai |
| HTTP 401 | Không theo kiểu blind retry | Làm mới credential theo authentication flow nếu hợp lệ |
| HTTP 403 | Không | Sửa authorization/policy |
| HTTP 404 | Thường không | Có thể retry nếu contract định nghĩa eventual resource propagation |
| HTTP 409 business conflict | Không theo kiểu retry ngay | Làm mới trạng thái/đề xuất hành động khác |
| Insufficient funds / invalid state | Không | Thất bại nghiệp vụ xác định |
| Circuit breaker open | Không gọi dependency | Fallback hoặc trả lỗi có kiểm soát |

Ngay cả với status code có thể retry, vẫn phải xét operation, error code, Retry-After, deadline và giới hạn retry.

### 2.3. Retry policy phải gắn với operation

- GET product thường có thể retry khi lỗi mạng tạm thời vì thao tác đọc không tạo side effect.
- PUT đặt trạng thái resource về giá trị cụ thể có thể idempotent theo semantics API, nhưng vẫn cần kiểm tra version/concurrency.
- POST tạo booking chỉ retry an toàn khi API hỗ trợ idempotency key hoặc client có thể tra cứu kết quả bằng operation ID.
- POST charge payment cần provider idempotency và reconciliation; không retry với key mới chỉ vì timeout.
- DELETE có thể idempotent về trạng thái cuối nhưng log, notification hoặc external side effect vẫn phải được thiết kế không lặp ngoài ý muốn.

## 3. Exponential backoff

Nếu dependency đang quá tải hoặc có lỗi transient, retry ngay có thể đẩy thêm request vào queue. **Backoff** tăng khoảng chờ giữa các lần thử.

Với exponential backoff cơ bản:

\[
d_n = \min(d_{\max}, d_0 \times 2^{n-1})
\]

Trong đó d0 là delay ban đầu, n là số thứ tự lần retry bắt đầu từ 1, dmax là delay tối đa và dn là thời gian chờ trước lần retry thứ n.

Ví dụ chọn delay ban đầu 200 ms và cap 5 giây:

| Lần retry | Delay trước jitter |
|---:|---:|
| 1 | 200 ms |
| 2 | 400 ms |
| 3 | 800 ms |
| 4 | 1.600 ms |
| 5 | 3.200 ms |
| 6 | 5.000 ms (đã cap) |
| 7 trở đi | 5.000 ms |

Đây là ví dụ minh họa; delay thực tế còn phụ thuộc latency, SLA, deadline và tải dependency.

### 3.1. Vì sao có cap?

Không có cap, delay tăng rất nhanh và request có thể chờ lâu hơn giá trị nghiệp vụ cho phép. Cap giới hạn khoảng chờ từng lần thử nhưng không tự giới hạn tổng thời gian. Cần đồng thời giới hạn số lần thử tối đa, tổng thời gian retry, deadline của request/workflow và tổng lượng retry được phép cho dependency.

### 3.2. Fixed delay, linear backoff và exponential backoff

| Cách | Công thức khái quát | Khi cân nhắc | Hạn chế |
|---|---|---|---|
| Fixed delay | Mỗi lần chờ cùng một khoảng | Retry đơn giản với tải thấp | Client dễ đồng bộ |
| Linear backoff | Delay tăng đều theo attempt | Hệ thống có tải ổn định | Tăng chậm khi sự cố kéo dài |
| Exponential backoff | Delay tăng theo cấp số nhân, có cap | Dependency quá tải hoặc transient outage | Có thể tạo cụm retry nếu không có jitter |

## 4. Jitter: phá đồng bộ các lần retry

Nếu 10.000 client cùng lỗi tại một thời điểm và đều dùng delay 1, 2, 4, 8 giây, chúng có thể retry gần như đồng loạt. Hiện tượng này gọi là **thundering herd**. Jitter thêm yếu tố ngẫu nhiên vào delay để phân tán request theo thời gian.

### 4.1. Full jitter

Với exponential cap bn, full jitter chọn:

\[
d_n \sim U(0, b_n)
\]

Nếu cap theo backoff là 800 ms thì delay thực tế được chọn ngẫu nhiên từ 0 đến 800 ms. Cách này phân tán mạnh request; một số request có thể thử lại khá sớm nên deadline và retry budget vẫn phải kiểm soát.

### 4.2. Equal jitter

Một biến thể chọn:

\[
d_n = \frac{b_n}{2} + U(0, \frac{b_n}{2})
\]

Delay không thấp hơn một nửa exponential cap. Điều này giảm khả năng retry quá sớm nhưng mức phân tán nhỏ hơn full jitter.

### 4.3. Decorrelated jitter

Một dạng decorrelated jitter chọn delay tiếp theo dựa trên delay trước:

\[
d_n = \min(d_{\max}, U(d_{\min}, 3d_{n-1}))
\]

Nó tránh lịch retry lặp theo chu kỳ cố định. Cần kiểm tra implementation của thư viện đang dùng vì tên gọi và công thức cụ thể có thể khác nhau.

### 4.4. Minh họa lịch retry

~~~mermaid
flowchart TD
    A["Attempt 1"] -->|"Failure"| B["Compute exponential cap"]
    B --> C["Apply jitter"]
    C --> D{"Deadline and retry budget remain?"}
    D -->|"No"| E["Stop / fallback / fail"]
    D -->|"Yes"| F["Wait selected delay"]
    F --> G["Attempt next"]
    G --> H{"Success?"}
    H -->|"Yes"| I["Return result"]
    H -->|"No"| B
~~~

Jitter phân tán thời điểm, không giảm tổng số attempt một cách tự động. Retry budget mới giới hạn tổng tải bổ sung.

## 5. Retry budget: giới hạn lượng tải do retry tạo ra

Một policy chỉ nói “retry tối đa 5 lần” không đủ khi service có hàng triệu request. Trong outage, mỗi request có thể dùng hết 5 lần và làm dependency quá tải hơn.

**Retry budget** là giới hạn tài nguyên hoặc tỷ lệ dành cho request retry trong một cửa sổ thời gian. Mục tiêu là bảo đảm retry chỉ chiếm một phần hữu hạn của traffic/capacity.

### 5.1. Budget theo tỷ lệ

Một cách diễn đạt phổ biến là giới hạn số retry so với số request ban đầu hoặc số request thành công trong cửa sổ.

Ví dụ policy:

- Cho phép tối đa 10 retry trên mỗi 100 request ban đầu trong một cửa sổ đo.
- Nếu budget hết, request mới thất bại tạm thời hoặc dùng fallback thay vì tiếp tục gọi dependency.
- Budget được bổ sung lại khi traffic khỏe hoặc theo rolling window đã định nghĩa.

Con số trên chỉ là ví dụ. Budget cần được tính từ capacity headroom, SLO, error rate và đặc điểm dependency.

### 5.2. Budget token bucket

Có thể triển khai budget như token bucket: mỗi retry tiêu thụ một token; token được bổ sung với tốc độ xác định; bucket có dung lượng tối đa để cho phép burst retry ngắn; hết token thì dừng retry hoặc chuyển fallback.

Bucket có thể ở process, service instance, sidecar hoặc tầng điều phối tập trung. Budget cục bộ dễ triển khai nhưng tổng retry toàn cluster tăng theo số replica; budget phân tán chính xác hơn nhưng thêm dependency và coordination.

### 5.3. Budget theo dependency và tenant

Một service thường gọi nhiều dependency. Budget nên tách theo dependency để lỗi ở Payment không tiêu hết ngân sách retry của Database hoặc Identity provider.

Có thể phân bổ tiếp theo dependency/endpoint; tenant hoặc client tier; foreground request so với background job; operation critical so với tác vụ phụ; region/zone hoặc failure domain nếu có blast radius riêng.

Không chia quá nhiều bucket nhỏ đến mức vận hành khó hiểu hoặc mỗi bucket có quá ít token để hấp thụ burst hợp lý.

### 5.4. Retry budget và rate limit khác nhau

| Cơ chế | Điều nó giới hạn |
|---|---|
| Rate limit | Tổng tốc độ request đến resource/client/route |
| Concurrency limit | Số operation đang chạy đồng thời |
| Retry budget | Phần request bổ sung được phép tạo ra do retry |
| Circuit breaker | Ngăn gọi dependency khi failure vượt ngưỡng |
| Deadline | Thời gian tối đa operation còn giá trị với caller |

Chúng phối hợp nhưng không thay thế nhau. Rate limit có thể cho request ban đầu đi qua nhưng không biết request nào là retry; retry budget làm rõ phần tải phát sinh do lần thử lại.

## 6. Timeout, deadline và tổng thời gian retry

Retry chỉ hữu ích nếu lần thử tiếp theo có đủ thời gian tạo ra kết quả còn giá trị.

### 6.1. Timeout mỗi lần gọi

Timeout giới hạn một attempt, ví dụ connect timeout, TLS handshake timeout, response timeout hoặc total request timeout của client. Nếu timeout quá ngắn, client có thể cắt operation vẫn đang xử lý ở server; nếu quá dài, request đồng thời tích tụ và tiêu thụ tài nguyên.

Timeout phải dựa trên latency distribution, network path, dependency SLO và loại operation. Không dùng một giá trị tùy ý giống nhau cho mọi dependency.

### 6.2. Deadline tổng

Deadline là thời điểm cuối cùng operation còn được phép chạy. Giả sử HTTP request bên ngoài có deadline còn 2 giây. Nếu attempt trước đã dùng 1,5 giây, không thể chờ backoff 1 giây rồi bắt đầu attempt mới mà vẫn đáp ứng deadline.

~~~text
remaining = deadline - monotonic_now()

if remaining <= minimum_attempt_time:
    stop retry
else:
    wait = min(jittered_backoff, remaining - minimum_attempt_time)
    wait
    call dependency with timeout <= remaining
~~~

Đây là pseudocode. Trong hệ thống thật, dùng monotonic clock cho đo duration/deadline trong process; không dùng wall clock thay thế nếu có thể bị chỉnh giờ.

### 6.3. Timeout của các tầng phải phối hợp

Ví dụ request đi qua API gateway → Booking service → Inventory service → Database:

- Gateway có deadline tổng.
- Booking có timeout nội bộ nhỏ hơn phần deadline còn lại.
- Inventory có timeout cho connection và response.
- Database query có statement timeout phù hợp.

Mỗi tầng không nên đặt timeout dài hơn deadline caller còn lại rồi retry sau khi caller đã bỏ cuộc. Nên truyền deadline/remaining timeout có giới hạn giữa các service để tránh công việc “mồ côi”.

### 6.4. Backoff không được vượt deadline

Tổng thời gian một workflow cần tính cả:

\[
T_{\text{total}} = \sum T_{\text{attempt}} + \sum T_{\text{backoff}} + T_{\text{overhead}}
\]

Nếu tổng thời gian vượt deadline, dừng retry và chọn kết quả phù hợp: trả lỗi tạm thời, trả trạng thái PROCESSING với operation ID, đưa job vào queue hoặc chuyển sang reconciliation.

## 7. Idempotency và kết quả không rõ ràng

Backoff và jitter giải quyết **khi nào** retry; idempotency giải quyết **retry có lặp side effect hay không**.

### 7.1. Idempotent operation

Một operation idempotent có cùng hiệu ứng trạng thái cuối khi thực hiện một hay nhiều lần với cùng điều kiện. HTTP GET thường được thiết kế safe/idempotent; PUT và DELETE có thể idempotent về semantics tài nguyên. Điều đó không có nghĩa mọi log, notification hoặc external side effect phía sau tự nhiên chỉ xảy ra một lần.

### 7.2. Idempotency key cho POST

~~~http
POST /v1/bookings
Authorization: Bearer <token>
Idempotency-Key: booking-create-user-120-req-781
Content-Type: application/json

{
  "deviceId": "dev-017",
  "slotId": "slot-0900"
}
~~~

Server nên xác định scope của key; lưu key cùng hash payload, trạng thái xử lý và kết quả; với cùng key/payload trả kết quả trước đó hoặc trạng thái đang xử lý; với cùng key nhưng payload khác thì từ chối; giữ key đủ lâu so với retry window và workflow timeout; đồng bộ lưu idempotency record với thay đổi nghiệp vụ trong transaction khi có thể.

Không dùng key mới sau timeout chỉ vì client không biết lần đầu thành công hay chưa. Hãy tra cứu bằng cùng key hoặc operation ID.

### 7.3. Kết quả ambiguous

~~~mermaid
sequenceDiagram
    autonumber
    participant C as Client
    participant A as Booking API
    participant DB as Database
    C->>A: POST booking + idempotency key K
    A->>DB: Commit booking + result for K
    DB-->>A: Commit success
    Note over A,C: Response lost / connection timeout
    C->>A: Retry same request + key K
    A->>DB: Lookup idempotency record K
    DB-->>A: Existing committed result
    A-->>C: Return original booking result
~~~

Nếu idempotency record và business row được ghi ở hai transaction độc lập, crash giữa hai lần ghi vẫn tạo cửa sổ duplicate hoặc mất kết quả. Cần transaction chung, unique constraint hoặc protocol phù hợp.

## 8. Retry storm và khuếch đại qua nhiều tầng

Giả sử mobile client retry tối đa 3 lần; API gateway retry 2 lần; Booking service retry 3 lần tới Inventory. Nếu mọi tầng retry lồng nhau mà không thống nhất, số lần gọi có thể nhân theo tích số attempt của các tầng.

Ví dụ đơn giản: gateway có thể chuyển tối đa 2 lần; service có thể thử Inventory 3 lần cho mỗi lần nhận. Inventory có thể nhận tới 6 lần gọi, chưa tính retry bên trong database client.

~~~mermaid
flowchart TD
    CLIENT["Client: attempts"] --> GW["Gateway: retries"]
    GW --> SVC["Booking service: retries"]
    SVC --> DEP["Inventory dependency"]
    DEP --> DB["Database"]
    DEP -. "Failure responses" .-> SVC
    SVC -. "Failure responses" .-> GW
    GW -. "Failure responses" .-> CLIENT
~~~

### 8.1. Chọn một tầng sở hữu retry

- Xác định tầng nào hiểu semantics operation và có quyền quyết định retry.
- Tránh retry ở mọi tầng cho cùng một lỗi.
- Tầng thấp có thể retry lỗi transport hẹp nếu operation chắc chắn chưa được gửi; tầng nghiệp vụ quản lý retry theo operation ID.
- Truyền deadline và retry metadata/budget giữa các tầng.
- Không để gateway retry POST không idempotent một cách mù quáng.

Không phải lúc nào chỉ một tầng được retry tuyệt đối. Database driver có thể retry lỗi transaction serialization; application có thể retry workflow. Nhưng tổng số lần thử phải được mô hình hóa để không nhân bội ngoài ý muốn.

### 8.2. Circuit breaker và load shedding

Khi dependency liên tục thất bại, circuit breaker chuyển từ Closed sang Open, chặn lời gọi mới trong một khoảng; sau đó Half-open cho một số probe kiểm tra phục hồi. Retry budget giới hạn tải retry; circuit breaker ngăn request tiếp tục đến dependency đang lỗi; load shedding từ chối tác vụ ít ưu tiên khi capacity cạn.

~~~mermaid
stateDiagram-v2
    [*] --> Closed
    Closed --> Open: failure threshold reached
    Open --> HalfOpen: cooldown elapsed
    HalfOpen --> Closed: probe succeeds
    HalfOpen --> Open: probe fails
~~~

## 9. Retry trong queue và background job

Queue consumer thường retry message khi handler lỗi. Nếu không quản lý, một message poison có thể được giao lặp vô hạn, chặn partition hoặc làm backlog tăng.

### 9.1. Retry topic/queue hoặc delayed delivery

Có thể dùng delayed retry queue với delay tăng dần; visibility timeout/lease cho message processing; maximum delivery/attempt count; dead-letter queue (DLQ) sau khi vượt giới hạn; consumer idempotency để duplicate delivery không lặp side effect.

### 9.2. Backoff theo message

| Lần xử lý | Delay minh họa | Hành vi |
|---:|---:|---|
| 1 | 1 giây | Retry nhanh cho lỗi ngắn |
| 2 | 5 giây | Chờ dependency hồi phục |
| 3 | 30 giây | Giảm tốc độ gửi |
| 4 | 2 phút | Thử lại trong giới hạn |
| Vượt max attempt | DLQ | Điều tra/replay có kiểm soát |

Delay thực tế cần jitter và phù hợp retention, visibility timeout, message ordering và business deadline. Không để retry làm message hết hạn trước khi có cơ hội xử lý.

### 9.3. Poison message và DLQ

Message lỗi do schema sai hoặc dữ liệu nghiệp vụ không hợp lệ sẽ không tự sửa khi retry. Sau số lần thử hợp lý, chuyển DLQ, lưu nguyên nhân và metadata an toàn, alert owner. Replay chỉ sau khi đã sửa nguyên nhân và có idempotency; không replay toàn bộ DLQ trực tiếp vào production mà không kiểm tra blast radius.

### 9.4. Retry theo workflow dài

Với saga hoặc job kéo dài, không giữ request thread để retry hàng phút. Lưu state bền vững, schedule lần thử tiếp theo, cho caller operation ID để poll/status hoặc nhận event, và có cơ chế cancel/deadline/reconciliation.

## 10. Thiết kế retry policy

Một policy có thể mô tả bằng bảng:

| Thuộc tính | Ví dụ cho Inventory API | Mục đích |
|---|---|---|
| Retryable failures | Network transient, 503, 429 theo Retry-After | Chỉ thử lại lỗi có khả năng phục hồi |
| Max attempts | 3 lần tổng cộng | Chặn retry vô hạn |
| Initial delay | 100 ms | Chờ trước lần retry đầu |
| Backoff | Exponential | Tăng khoảng chờ |
| Jitter | Full jitter | Phá đồng bộ client |
| Max delay | 1 giây | Giới hạn chờ từng lần |
| Per-attempt timeout | Theo latency/SLO dependency | Không giữ request vô hạn |
| Overall deadline | Nằm trong deadline request | Dừng khi kết quả không còn hữu ích |
| Retry budget | Tỷ lệ theo cửa sổ đã định nghĩa | Giới hạn tải bổ sung |
| Idempotency | Required cho hold/release theo operation ID | Tránh giữ/nhả lặp |
| Circuit breaker | Theo failure/slow-call threshold | Ngăn gọi dependency đang lỗi |
| Exhaustion behavior | Trả 503 hoặc workflow PENDING | Báo kết quả nhất quán |

Các con số trên chỉ là mẫu. Từng API cần policy theo latency distribution, SLO, semantics, capacity và dependency contract.

### 10.1. Pseudocode minh họa

~~~text
call_with_retry(operation, deadline, policy):
    for attempt in 1..policy.max_attempts:
        remaining = deadline - monotonic_now()
        if remaining <= policy.minimum_attempt_time:
            return DEADLINE_EXCEEDED

        if attempt > 1:
            if not retry_budget.try_consume(operation.dependency):
                return RETRY_BUDGET_EXHAUSTED

            cap = min(
                policy.max_delay,
                policy.initial_delay * 2 ** (attempt - 2)
            )
            delay = random(0, cap)  # full jitter

            if delay + policy.minimum_attempt_time >= remaining:
                return DEADLINE_EXCEEDED

            sleep(delay)

        timeout = min(policy.per_attempt_timeout, remaining)
        result = operation.execute(timeout)

        if result.success:
            return result

        if not policy.is_retryable(result):
            return result

        if not operation.is_safe_to_retry:
            return UNKNOWN_OUTCOME_OR_RECONCILE

    return ATTEMPTS_EXHAUSTED
~~~

Đây là pseudocode để thể hiện luồng quyết định, không phải thư viện production. Cần bổ sung cancellation, interruption, exception classification, clock injection, observability, server-directed Retry-After, concurrency control và semantics riêng cho ambiguous outcome. Điều kiện safe-to-retry phải bao gồm idempotency hoặc status lookup phù hợp.

## 11. Retry-After và tín hiệu từ server

Khi server trả 429 hoặc 503, header Retry-After có thể chỉ ra thời điểm/độ trễ nên thử lại. Client nên parse đúng định dạng contract hỗ trợ; không retry sớm hơn thời gian server yêu cầu; vẫn áp deadline và retry budget; có jitter bổ sung có kiểm soát để tránh client retry cùng thời điểm; không giữ thread/request không giới hạn nếu Retry-After quá dài.

Server nên phát Retry-After phù hợp quota/recovery policy và tránh gợi ý thời điểm quá chính xác cho hàng triệu client nếu sẽ tạo herd mới.

## 12. Thư viện retry và cấu hình an toàn

Khi chọn HTTP client, database driver, messaging client hoặc resilience library, kiểm tra:

- Có retry mặc định hay không và bật ở tầng nào.
- Những exception/status nào được retry.
- Có exponential backoff/jitter hay không.
- Max attempts và max elapsed time.
- Có tôn trọng Retry-After không.
- Có deadline/cancellation propagation không.
- Retry chỉ áp dụng method/operation nào; POST có bị retry không.
- Có metric/log cho attempt number, reason và exhaustion.
- Có retry budget hoặc hook để tích hợp budget service không.
- Có tương tác với circuit breaker/rate limiter khiến retry không bị nhân đôi không.

Tránh để nhiều middleware tự động retry mà không biết nhau. Viết integration test xác nhận số lần request thực tế ở wire level khi dependency trả lỗi.

## 13. Quan sát và vận hành retry

Chỉ số tổng request thành công có thể che giấu việc hệ thống đang retry rất nhiều. Cần phân biệt traffic gốc và traffic retry.

### 13.1. Metrics

| Metric | Ý nghĩa | Cách diễn giải |
|---|---|---|
| Original request count | Lượng request nghiệp vụ ban đầu | Mẫu số để tính amplification |
| Retry attempt count | Lần gọi bổ sung | Tăng cao cho thấy dependency hoặc policy bất ổn |
| Retry ratio | Retry/original requests | Đo mức tải khuếch đại |
| Retry success rate | Tỷ lệ retry chuyển lỗi thành công | Xác định retry có hiệu quả hay chỉ tốn tải |
| Retry budget exhaustion | Số lần budget hết | Báo hệ thống đang chạm giới hạn an toàn |
| Attempts per operation | Phân bố số attempt | Phát hiện tail có nhiều lần thử |
| Backoff delay histogram | Thời gian chờ thực tế | Xác nhận jitter và cap |
| Deadline exceeded | Operation hết thời gian | Phân biệt timeout do dependency với retry quá dài |
| Circuit breaker state | Closed/Open/Half-open | Theo dõi dependency health |
| DLQ depth/age | Message chờ xử lý thủ công | Phát hiện poison message/backlog |

### 13.2. Log và trace

Ghi attempt number, dependency, error classification, delay, timeout, idempotency/operation ID đã mask phù hợp, retry budget decision và final outcome. Trong distributed trace, biểu diễn từng attempt là span riêng liên kết cùng parent operation.

Không đưa token, secret, payment data hoặc PII nguyên dạng vào log. Không dùng operation ID duy nhất làm metric label nếu gây cardinality cao; giữ ID trong trace/log có quyền truy cập.

### 13.3. SLO và error budget

Retry có thể làm request cuối cùng thành công dù một số attempt thất bại. Cần quyết định SLO đo ở đâu:

- User-visible success/latency: phản ánh trải nghiệm cuối.
- Dependency attempt success/error: phản ánh sức khỏe từng lần gọi.
- Retry amplification: phản ánh tải bổ sung.
- Queue completion age: phản ánh thời gian xử lý bất đồng bộ.

Không che giấu sự cố dependency bằng cách chỉ báo success cuối. Nếu latency tăng mạnh do nhiều retry, success rate có thể vẫn đạt nhưng trải nghiệm và capacity đang suy giảm.

## 14. Kiểm thử retry và fault injection

Trước production, tạo các tình huống:

1. Dependency trả 503 trong hai lần rồi thành công.
2. Dependency trả 429 kèm Retry-After.
3. Connection reset trước khi request gửi xong.
4. Request được xử lý và commit nhưng response bị drop.
5. Dependency chậm hơn per-attempt timeout.
6. Nhiều client cùng lỗi tại một thời điểm.
7. Retry budget cạn trong outage kéo dài.
8. Circuit breaker mở khi failure threshold bị vượt.
9. Queue consumer nhận poison message.
10. Client cancel request khi server vẫn đang xử lý.

### 14.1. Tiêu chí kiểm chứng

- Tổng attempt không vượt max attempts.
- Không attempt nào bắt đầu sau deadline.
- Delay phân tán qua jitter khi nhiều client lỗi đồng thời.
- Retry budget giới hạn phần tải bổ sung theo policy.
- POST tạo booking/payment không tạo side effect trùng khi response bị mất.
- Lỗi non-retryable không bị lặp.
- Retry-After được tôn trọng.
- Circuit breaker và load shedding giảm origin QPS khi dependency lỗi.
- DLQ giữ message vượt max delivery và replay có kiểm soát.
- Metrics phân biệt original request, retry attempt và final outcome.

## 15. Ví dụ: retry policy cho BookingCloud

Booking API gọi Inventory để giữ slot và Payment provider để authorize. Hai operation có semantics khác nhau:

| Thành phần | Hold inventory | Authorize payment |
|---|---|---|
| Operation identity | hold_id/booking_id ổn định | payment operation ID ổn định |
| Idempotency | Required | Required theo provider contract |
| Retryable | Network transient, 429/503 theo policy | Network transient, 429/503 theo provider policy |
| Ambiguous timeout | Query hold status hoặc retry cùng key | Query payment status cùng reference/key |
| Backoff | Exponential + jitter | Theo Retry-After + exponential/jitter |
| Budget | Riêng Inventory dependency | Riêng Payment dependency |
| Exhaustion | Booking PENDING hoặc fail theo hold deadline | Payment outcome unknown, chuyển reconciliation |
| Compensation | Release hold idempotent | Void authorization; không tạo charge/refund mù |

~~~mermaid
flowchart TD
    START["Create booking request"] --> BUDGET{"Request deadline and budget available?"}
    BUDGET -->|"No"| PENDING["Return PROCESSING / controlled failure"]
    BUDGET -->|"Yes"| HOLD["Hold inventory with stable key"]
    HOLD -->|"Success"| PAY["Authorize payment with stable key"]
    HOLD -->|"Transient failure"| RETRYH["Backoff + jitter + inventory budget"]
    RETRYH --> HOLD
    HOLD -->|"Permanent / exhausted"| FAIL["Fail or compensate"]
    PAY -->|"Success"| CONFIRM["Confirm booking"]
    PAY -->|"Ambiguous timeout"| QUERY["Query payment status"]
    QUERY -->|"Authorized"| CONFIRM
    QUERY -->|"Not authorized, retry allowed"| RETRYP["Retry same key within deadline"]
    RETRYP --> PAY
    QUERY -->|"Still unknown"| RECON["Reconciliation / manual review"]
    PAY -->|"Definitive decline"| FAIL
    CONFIRM --> DONE["Completed"]
~~~

Luồng này minh họa quy trình có trạng thái. Với API đồng bộ có deadline ngắn, hệ thống có thể trả PROCESSING kèm operation ID và tiếp tục workflow nền. Không giữ request HTTP hàng chục giây chỉ để chờ đủ retry nếu caller có thể poll hoặc nhận event.

## 16. Đánh giá theo Well-Architected

| Góc nhìn | Câu hỏi review | Bằng chứng cần có |
|---|---|---|
| **Operational Excellence** | Retry policy có owner, dashboard, runbook và thay đổi được kiểm soát? | Policy inventory, attempt metrics, exhaustion alert, replay/incident runbook |
| **Security** | Retry có lặp thao tác nhạy cảm, vượt tenant quota hoặc làm lộ dữ liệu trong log? | Idempotency, auth revalidation, least privilege, log redaction |
| **Reliability** | Outage có tạo retry storm? Có deadline, jitter, budget và recovery path? | Fault injection, amplification ratio, budget exhaustion, circuit breaker tests |
| **Performance Efficiency** | Backoff/attempts có tăng latency hoặc giữ tài nguyên quá lâu? | p95/p99, attempt histogram, connection/queue utilization |
| **Cost Optimization** | Retry làm tăng compute, network, provider charge và queue cost bao nhiêu? | Cost per successful operation, duplicate request count |
| **Sustainability** | Có retry loop hoặc polling thừa làm tiêu thụ compute không cần thiết? | Retry success rate, bounded attempts, queue polling/retention metrics |

Retry chỉ có ích khi xác suất phục hồi và giá trị business lớn hơn chi phí tải, latency và side effect. Nếu retry liên tục không làm khả năng thành công tăng lên, cần dừng, giảm tải hoặc chuyển sang recovery workflow.

## 17. Bài thực hành: chống retry storm khi Inventory lỗi

BookingCloud nhận 4.000 request/giây. Mỗi request cần gọi Inventory một lần. Inventory bắt đầu trả 503 trong 30 giây. Hiện tại:

- API gateway retry 2 lần.
- Booking service retry 3 lần.
- HTTP client có thêm 2 lần retry mặc định.
- Không có idempotency key cho hold slot.
- Timeout mỗi attempt là 2 giây; request deadline là 5 giây.
- Không có retry budget.

Hãy thực hiện:

**Bài 1 — Amplification:** tính số lần gọi tối đa có thể phát sinh theo cấu hình retry lồng nhau. Nêu vì sao không thể chỉ cộng attempt của các tầng nếu chúng lồng nhau.

**Bài 2 — Retry ownership:** chọn tầng sở hữu retry theo semantics Inventory; tắt hoặc giới hạn retry dư ở các tầng còn lại.

**Bài 3 — Backoff/jitter:** đề xuất initial delay, exponential cap, full/equal/decorrelated jitter và max attempts dựa trên deadline.

**Bài 4 — Idempotency:** thiết kế hold operation ID và xử lý trường hợp Inventory đã hold nhưng response bị mất.

**Bài 5 — Retry budget:** thiết kế token budget theo dependency và cách hành xử khi budget hết.

**Bài 6 — Circuit breaker:** chọn tín hiệu mở/half-open và cách bảo vệ capacity khi Inventory đang phục hồi.

**Bài 7 — Kiểm chứng:** viết fault-injection test cho outage 30 giây, 429, timeout sau commit và nhiều client retry đồng bộ.

### Khung phân tích tự kiểm tra

| Hiện trạng | Rủi ro | Hướng sửa |
|---|---|---|
| Retry ở gateway + service + client | Attempt bị nhân bội | Xác định tầng owner; giới hạn retry lồng nhau |
| Không có idempotency | Hold lặp hoặc giữ nhiều lần | Stable operation key, unique constraint/status lookup |
| Không có jitter | Thundering herd | Exponential backoff + jitter |
| Không có retry budget | Retry ăn hết capacity | Token/rate budget theo dependency |
| Timeout 2 giây nhưng deadline 5 giây | Không đủ thời gian cho nhiều retry/backoff | Tính remaining deadline trước từng attempt |
| Không có circuit breaker | Tiếp tục gọi dependency đang lỗi | Open/half-open và load shedding |

Đừng chỉ kiểm tra tổng thời gian; hãy đo cả số lần gọi thực tế đến Inventory và side effect đã ghi.

## 18. Checklist trước khi bật retry trong production

- [ ] Đã phân loại lỗi retryable, permanent và ambiguous theo contract.
- [ ] Mỗi operation có semantics/idempotency phù hợp với side effect.
- [ ] Có max attempts, exponential backoff và max delay.
- [ ] Có jitter để phân tán client retry.
- [ ] Backoff không vượt deadline tổng; mỗi attempt có timeout/cancellation phù hợp.
- [ ] Tôn trọng Retry-After nhưng vẫn áp dụng budget/deadline.
- [ ] Có retry budget theo dependency và các nhóm tải quan trọng.
- [ ] Tránh retry chồng tầng không kiểm soát; biết số attempt thực tế ở wire level.
- [ ] Circuit breaker, concurrency limit, rate limit và load shedding phối hợp với retry.
- [ ] Queue retry có max delivery, delayed retry và DLQ.
- [ ] Ambiguous result có status lookup/idempotency/reconciliation.
- [ ] Metrics phân biệt request gốc, retry attempt, retry success, exhaustion và final outcome.
- [ ] Log/trace có correlation nhưng không ghi secret/PII nhạy cảm.
- [ ] Đã fault-injection test outage, timeout-after-commit, duplicate, 429 và herd.

Retry là một phần của thiết kế độ tin cậy, không phải vòng lặp thử lại vô hạn. Exponential backoff giảm tốc độ khi lỗi kéo dài; jitter phá đồng bộ; retry budget giới hạn tải khuếch đại; timeout/deadline giới hạn thời gian và tài nguyên; idempotency bảo vệ side effect. Kết hợp các cơ chế này với circuit breaker, backpressure và quan sát đầy đủ giúp hệ thống phục hồi lỗi tạm thời mà không tự biến một dependency chậm thành sự cố diện rộng.
