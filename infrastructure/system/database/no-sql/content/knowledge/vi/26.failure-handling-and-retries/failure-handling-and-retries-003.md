# Thời hạn toàn yêu cầu (deadline) so với thời gian chờ của từng lần thử

Một API tra cứu đơn hàng được yêu cầu phản hồi trong **800 ms**, nhưng driver NoSQL được cấu hình timeout **600 ms cho mỗi lần thử** và cho phép retry tối đa ba lần. Khi một replica chậm, ứng dụng có thể thực hiện ba lần chờ 600 ms, xen thêm backoff và thời gian lấy kết nối. Khách đã bỏ cuộc từ lâu nhưng server vẫn đang truy vấn, tạo thêm tải vào đúng lúc cụm dữ liệu đang gặp sự cố.

Đây là khác biệt quan trọng giữa **deadline cho toàn bộ ý định/yêu cầu** và **timeout cho từng attempt** trong chương *Lỗi phân tán và retry* của Database No SQL:

- **Deadline toàn yêu cầu** là mốc cuối mà toàn bộ quá trình, gồm chờ hàng đợi, truy vấn, retry, backoff và trả phản hồi, cần tôn trọng.
- **Per-attempt timeout** chỉ chặn thời gian của một lượt thao tác cụ thể; nếu retry mà không xét thời gian còn lại, tổng thời gian vẫn có thể vượt xa SLO.
- **Cancellation** có thể giảm công việc vô ích nhưng không đồng nghĩa thao tác ghi chắc chắn đã rollback.
- **Idempotency và outcome lookup** mới là cơ chế giúp retry an toàn khi một write có thể đã commit nhưng response bị mất.

Bài học trình bày mô hình ngân sách thời gian, kỹ thuật truyền deadline giữa dịch vụ, cách chọn retry và backoff, tác động lên tail latency và hot partitions, các ví dụ Java/NoSQL, cùng thí nghiệm phân biệt timeout, overload và kết quả commit không rõ.

Các con số trong bài là **số giả định để giải thích phương pháp**, không phải mặc định nên dùng cho một sản phẩm. Cú pháp timeout, cancellation, retryable writes, request throttling và write concern khác nhau theo database, driver, phiên bản, topology và môi trường. Khi áp dụng cần đọc hợp đồng của công cụ đang chạy và đo trên tải thực.

## 1. Vấn đề thường gặp: timeout từng attempt cộng dồn

Giả sử:

~~~text
HTTP service deadline mong muốn:   800 ms
DB timeout mỗi attempt:            600 ms
Retry tối đa:                       3 attempts
Backoff giữa attempts:             100 ms, 200 ms
Connection-pool wait:              tối đa 150 ms/lần
~~~

Một lịch trình xấu có thể là:

~~~text
T=   0 ms: request vào API
T= 150 ms: lấy được connection
T= 750 ms: DB attempt #1 timeout
T= 850 ms: hết backoff #1
T=1000 ms: lấy được connection khác
T=1600 ms: DB attempt #2 timeout
T=1800 ms: hết backoff #2
T=1950 ms: lấy được connection khác
T=2550 ms: DB attempt #3 timeout
~~~

Dù service định đáp ứng trong 800 ms, thao tác có thể tiêu tới **2.550 ms**, chưa kể validation, serialization và response network. Công thức ước lượng đơn giản:

\[
T_{\mathrm{total}}
\approx T_{\mathrm{initial}}+
\sum_{i=1}^{n}(T_{\mathrm{queue},i}+T_{\mathrm{attempt},i})+
\sum_{i=1}^{n-1}T_{\mathrm{backoff},i}
+T_{\mathrm{response}}
\]

Các thành phần có thể chồng lấp hoặc chưa hết timeout, nên đây là **mô hình ngân sách**, không phải phép dự báo p99 chính xác. Tuy nhiên, nó cho thấy một điều: đặt timeout 600 ms cho mỗi attempt **không** có nghĩa request được giới hạn 600 ms, và retry count càng lớn thì tổng thời gian càng có thể phình ra.

## 2. Những từ dễ bị dùng lẫn

| Thuật ngữ | Định nghĩa phù hợp | Ví dụ |
|---|---|---|
| **Deadline** | Mốc thời gian cuối của một operation/workflow | Request phải kết thúc trước 10:00:00.800 |
| **Remaining budget** | Thời gian còn lại từ hiện tại đến deadline | Còn 240 ms |
| **Per-attempt timeout** | Giới hạn thời gian một lần gọi dependency | Mỗi DB call tối đa 180 ms |
| **Connect timeout** | Giới hạn thiết lập kết nối ở một tầng | TCP connect tối đa 60 ms |
| **Pool-acquire timeout** | Giới hạn chờ connection từ pool | Chờ pool tối đa 40 ms |
| **Server execution timeout** | Giới hạn một phần xử lý phía server nếu API hỗ trợ | Query execution tối đa 150 ms |
| **Read/socket timeout** | Giới hạn thời gian chờ I/O theo semantics driver | Chờ dữ liệu đọc từ socket |
| **Idle timeout** | Giới hạn khoảng không có hoạt động trên connection/stream | Đóng stream nhàn 30 s |
| **Retry budget** | Giới hạn tổng retry theo số lượt, thời gian hoặc tải | Tối đa hai lượt thêm và trong deadline |
| **Backoff** | Khoảng chờ giữa các lượt thử | 50–200 ms có jitter |
| **SLO** | Mục tiêu chất lượng theo phân phối/thời gian | p99 GET dưới 300 ms khi khỏe |

Một số API có **max execution time**, **requestTimeout**, **operationTimeout**, **socketTimeout** hoặc **maxTimeMS**, nhưng tên giống nhau không có nghĩa bao phủ cùng phạm vi. Có API chỉ chặn một pha I/O, không bao gồm pool wait; có API chỉ chặn thực thi trên server, không chặn connection hoặc retries phía client. Phải xác định chính xác **bắt đầu đếm từ đâu và kết thúc khi nào**.

## 3. Deadline là một mốc, timeout là một khoảng

**Timeout tương đối** nói “cho phép chờ thêm 200 ms kể từ lúc bắt đầu pha này”. **Deadline tuyệt đối** nói “sau mốc D, toàn request không được tiếp tục tiêu thời gian để cố hoàn tất”.

Ví dụ:

~~~text
Request đến lúc 14:00:00.000
Deadline D = 14:00:00.800

Sau auth và routing, DB bắt đầu lúc 14:00:00.270
Remaining = 530 ms

Nếu DB bắt đầu retry lúc 14:00:00.680
Remaining = 120 ms
~~~

Khi retry, **không reset deadline thành 800 ms mới**. Phần còn lại phải giảm dần.

\[
B_{\mathrm{remaining}}(t)=\max(0,D-t)
\]

Cách này cũng giúp một request xếp hàng 400 ms không được nhận lại ngân sách DB 800 ms như thể nó vừa được tạo. **Request time budget phải đi theo request**, không chỉ đi theo method gọi database.

### 3.1. Đồng hồ đơn điệu trong một process

Trong Java, có thể đo khoảng thời gian bằng `System.nanoTime()` vì nó được thiết kế để đo elapsed time, không phải thời gian lịch:

~~~java
long started = System.nanoTime();
long totalBudgetNanos = java.time.Duration
    .ofMillis(800).toNanos();
long deadlineNanos = started + totalBudgetNanos;

// Cùng process:
long remainingNanos =
    Math.max(0L, deadlineNanos - System.nanoTime());
~~~

Ví dụ phù hợp khi budget nhỏ, không gần giới hạn overflow của bộ đếm. **Không truyền raw `System.nanoTime()` của process A sang process B**: origin của monotonic clock không được định nghĩa tương thích giữa processes/machines. Khi đi qua service boundary, truyền một **relative remaining duration** đã tính tại lúc gửi, hoặc dùng giao thức deadline có quy tắc đồng hồ/skew rõ ràng.

## 4. SLO và deadline không hoàn toàn là một

Giả sử API có SLO:

> 99% yêu cầu GET Order trả thành công dưới 300 ms trong điều kiện khỏe.

SLO trên phân phối không có nghĩa mọi request phải bị cắt chính xác 300 ms. Hệ có thể chọn **deadline 500 ms** để có không gian xử lý tail requests, nhưng lúc đo p99 vẫn phải đạt 300 ms. Ngược lại, nếu có **hợp đồng hard deadline 300 ms** (ví dụ UI bỏ request sau thời điểm đó), hệ cần thiết kế để giảm hoặc dừng công việc muộn hơn.

Phải hỏi:

- p50/p95/p99 của **request thành công** hay của **tất cả attempts gồm timeout**?
- Deadline client có giống deadline API gateway không?
- SLO được đo khi hệ khỏe, khi degraded hay dưới failover?
- Request có được trả PENDING/202 thay vì chờ hoàn thành workflow không?
- Thời gian chờ ở queue, auth, pool, serialization và response có được tính không?
- Nếu 99% kịp hạn nhưng 1% lỗi, success rate có đạt availability target không?

**Deadline là công cụ thực thi ràng buộc**, còn SLO là tiêu chí đánh giá chất lượng. Cần phối hợp chúng, không dùng một số mili-giây cho mọi tầng.

## 5. Budget end-to-end phải bao gồm toàn bộ chuỗi

Một request API không chỉ có truy vấn database:

~~~mermaid
flowchart LR
    A["Client / Gateway"] --> B["Authentication"]
    B --> C["Application logic"]
    C --> D["Pool / Routing"]
    D --> E["NoSQL read/write"]
    E --> F["Serialize response"]
    F --> G["Network back to client"]
~~~

Ví dụ budget giả định 900 ms:

| Thành phần | Budget dự kiến |
|---|---:|
| Gateway + routing | 50 ms |
| Authentication/validation | 70 ms |
| Application processing | 60 ms |
| DB phase (gồm attempts + backoff) | 500 ms |
| Serialization + response | 70 ms |
| Buffer cho jitter/chưa chắc chắn | 150 ms |
| **Tổng** | **900 ms** |

Đây là **một phương án phân bổ minh họa**, không phải các chặng bắt buộc chạy tuần tự. Một số request có nhiều DB calls hoặc gọi service khác; khi đó cần chia lại budget theo dependency graph và critical path.

Một nguyên tắc đơn giản: nếu còn 180 ms trước deadline, **không cấp cho DB 500 ms chỉ vì DB config mặc định là 500 ms**.

## 6. Deadline truyền qua nhiều microservices

Giả sử đường đi:

~~~text
Client (deadline 1000 ms)
  -> API Gateway
     -> Order Service
        -> Inventory Service
           -> NoSQL DB
~~~

Nếu mỗi tầng tự đặt timeout 1000 ms từ lúc nhận request, tổng thời gian có thể bị “nới” dần. Một call tới Inventory có thể được bắt đầu khi chỉ còn 180 ms trong budget phía client nhưng lại chạy thêm 1000 ms.

Đường đúng là **propagate remaining budget**:

~~~text
T0: Client budget 1000 ms
T1: Gateway bắt đầu xử lý, remaining ~900 ms
T2: Order Service nhận, remaining ~760 ms
T3: Inventory Service nhận, remaining ~410 ms
T4: DB call bắt đầu, remaining ~320 ms
~~~

Mỗi child operation dùng:

\[
D_{\mathrm{child}}\leq D_{\mathrm{parent}}.
\]

Tương đương, child budget không vượt parent remaining budget trừ phần network/response reserve. Nếu child tự thiết lập deadline ngắn hơn để bảo vệ tài nguyên, điều đó hợp lệ; **không được dài hơn chỉ vì default timeout của SDK**.

### 6.1. Absolute deadline qua mạng và clock skew

Có giao thức truyền deadline dạng timestamp UTC, có giao thức truyền relative timeout và tính lại sau mỗi hop. Absolute UTC dễ log và so sánh nhưng clock skew giữa machines có thể làm budget tăng/giảm ngoài dự kiến. Relative duration tránh phụ thuộc cùng clock origin nhưng phải trừ elapsed time ở mỗi hop và tính mạng/transit.

Cần tuân theo cơ chế chuẩn của HTTP/gRPC/framework nếu có; không tự chế một header rồi cho rằng nó chống được clock skew/forged values. Với caller không tin cậy, **clamp budget** vào giới hạn server cho phép; không để client gửi một deadline 24 giờ rồi chiếm tài nguyên vô hạn.

## 7. Deadline của một lời gọi và deadline của workflow dài

Có một điểm cần phân biệt: **một HTTP request** có thể kết thúc sớm trong khi **ý định nghiệp vụ** vẫn đang tiến hành hợp lệ.

Ví dụ API đặt hàng:

~~~text
POST /orders
  validate + persist intent in 200 ms
  -> return 202 PENDING
  background process:
      hold stock
      authorize payment
      confirm / reject
  GET /orders/{id} returns durable state
~~~

Ở đây:

- HTTP request có deadline ngắn để bảo vệ UX và tài nguyên request thread.
- Workflow có một **business expiration/deadline khác**, ví dụ giữ hàng tối đa 5 phút.
- Mỗi bước background vẫn cần per-operation deadlines, leases và retries có budget.
- Khi client timeout, workflow không mặc định hủy nếu ý định đã được commit.

Không được dùng một request deadline 800 ms để suy “Order PENDING sau 800 ms phải rollback” nếu hợp đồng nghiệp vụ cho phép xử lý bất đồng bộ. Ngược lại, nếu API chỉ được trả success sau commit, không thể trả “success” vì đã đưa command vào queue mà chưa ghi nhận trạng thái cần thiết.

## 8. Hierarchical deadline: quan hệ cha–con

Một request nhiều bước nên có cây ngân sách:

~~~text
Checkout deadline: 1200 ms
├── Auth + validation: 150 ms
├── Inventory reservation sub-budget: 420 ms
│   ├── Pool wait: 40 ms
│   ├── Attempt #1: up to 200 ms
│   ├── Backoff: up to 40 ms
│   └── Attempt #2: remaining only
├── Order transaction sub-budget: 350 ms
└── Response + safety buffer: 280 ms
~~~

Mỗi nhánh phải **thừa kế giới hạn của cha** và tiêu thụ từ một budget hữu hạn. Nếu Auth mất 200 ms thay vì 150 ms, DB không được tiếp tục giả định toàn bộ 420 ms “đã đặt sẵn” còn nguyên. Có thể dùng budget động theo remaining time.

Không nhất thiết chia thành các khoản cố định cứng nhắc; thiết kế linh hoạt có thể cho phép một bước dùng phần buffer nếu bước khác nhanh hơn. Nhưng phải bảo vệ **deadline cuối** và giữ một phần thời gian cho cleanup/response.

## 9. Per-attempt timeout dùng để làm gì khi đã có deadline?

Deadline tổng **không thay thế** per-attempt timeout. Nếu cả request còn 2 giây mà một DB attempt bị treo vô hạn trên socket, cần per-attempt timeout để phát hiện/thoát khỏi một dependency chậm và có cơ hội thử đường khác.

Per-attempt timeout còn giúp:

- Phát hiện failure của một node nhanh hơn deadline toàn request.
- Chuyển endpoint/replica hoặc retry khi protocol cho phép.
- Tránh giữ connection/pool slot quá lâu.
- Cô lập tail latency của một lần thử.
- Giới hạn công việc backend và tăng khả năng bảo vệ tài nguyên.

Nhưng timeout của attempt phải **được chặn bởi remaining budget**. Một công thức định hướng:

\[
t_{\mathrm{attempt},i}=
\min(t_{\mathrm{configured}},\ B_{\mathrm{remaining}}-r)
\]

trong đó `r` là phần reserve cho cleanup/response. Nếu kết quả không dương, không nên bắt đầu attempt mới.

### 9.1. Các loại timeout không bao phủ nhau tự động

Một DB driver có thể có:
- Timeout chờ lấy connection pool.
- Timeout thiết lập TCP/TLS.
- Timeout chọn server/coordinator.
- Timeout một socket read/write.
- Timeout xử lý một query ở server.
- Timeout toàn bộ một operation, nếu SDK hỗ trợ.
- Transaction lifetime/commit deadline.

Đặt một timeout 200 ms cho **socket read** không nhất thiết giới hạn tổng toàn call ở 200 ms nếu còn nhiều lần network I/O, pool wait hoặc retry. Cần đặt end-to-end guard/cancellation riêng và hiểu API cụ thể.

## 10. Retry không miễn phí: mỗi attempt làm tăng tải

Khi DB đã chậm, retry của 1000 clients có thể thành 2000–3000 DB requests, gây **retry amplification** ngay trên tài nguyên đang quá tải.

Một mô hình:

\[
\text{Attempt amplification} =
\frac{\text{tổng số attempts}}{\text{số business requests}}.
\]

Nếu 1000 business requests sinh 2500 DB attempts, amplification = 2,5. Đây chưa gồm các truy vấn con do mỗi attempt có fan-out tới nhiều partitions/replicas.

Retry có thể hữu ích cho lỗi ngắn/độc lập, nhưng khi lỗi là **hot partition hoặc overloaded coordinator**, nó có thể làm hàng đợi dài hơn, p99 xấu hơn và thêm timeout. Deadline/budget là cơ chế ngăn một phần vòng lặp xấu này.

## 11. Retry budget phải bị giới hạn bởi thời gian còn lại

Một chính sách hợp lý không chỉ là `maxRetries=2`. Nó phải xét đồng thời:

1. **Số attempts tối đa**.
2. **Remaining request deadline**.
3. **Thời gian backoff+jitter**.
4. **Lỗi có thực sự retryable không**.
5. **Phép ghi có idempotent/outcome lookup không**.
6. **Retry có khả năng thành công kịp hạn không**.
7. **Giới hạn tải retry của cả service**.
8. **Cancellation của parent đã xảy ra chưa**.

Ví dụ:

~~~text
Deadline còn 90 ms
Backoff tính ra 70 ms
Cần reserve 30 ms response/cleanup

90 - 70 - 30 = -10 ms
=> Không nên retry dù maxAttempts chưa hết.
~~~

Nếu còn 500 ms nhưng dependency đang quá tải kéo dài và circuit breaker đã mở, không có lý do gửi thêm requests chỉ vì còn budget thời gian. **Remaining budget là điều kiện cần, không phải giấy phép retry vô điều kiện.**

## 12. Backoff với jitter vẫn phải nằm trong deadline

Exponential backoff thường có dạng:

\[
b_i=\min(b_{\max},\ b_0\,2^{i-1})
\]

với jitter chọn thời gian chờ theo một phân phối thích hợp (ví dụ random trong một khoảng). Jitter giúp nhiều clients không retry **cùng thời điểm**.

Mẫu pseudocode:

~~~text
for attempt = 1 .. maxAttempts:
    remaining = deadline - monotonicNow()
    if remaining <= responseReserve:
        return DEADLINE_EXCEEDED

    timeout = min(perAttemptCap, remaining - responseReserve)
    outcome = tryDatabase(timeout)

    if outcome.success:
        return outcome

    if outcome.isBusinessRejection:
        return outcome

    if not outcome.retryable:
        return outcome

    sleepCandidate = randomJitter(backoffFor(attempt))
    if sleepCandidate + minUsefulAttemptBudget
       + responseReserve >= deadline - monotonicNow():
        return DEADLINE_EXCEEDED_OR_ORIGINAL_ERROR

    sleepWithCancellation(sleepCandidate)
~~~

Đây là **pseudocode** minh họa policy. Trong code production phải phân biệt deadline và operation errors, không tự che một kết quả ghi UNKNOWN thành “chưa ghi”; cũng phải tránh sleep không thể hủy và retry ngoài contract của driver.

## 13. Phân loại lỗi trước khi quyết định có thử lại

Không phải mọi lỗi cơ sở dữ liệu đều “transient” hay an toàn để retry:

| Tình huống | Retry trực tiếp? | Lý do |
|---|---|---|
| Query đọc bị timeout, không side effect | Có thể, nếu còn deadline và nguồn khác hữu ích | Đọc lại thường dễ an toàn hơn ghi |
| Lỗi kết nối trước khi gửi request | Có thể theo contract driver | Cần phân biệt chính xác pha lỗi |
| Write conflict/transaction abort đã xác nhận | Có thể retry transaction nếu callback không có side effect ngoài DB | Giữ cùng business intent |
| Conditional check failed vì hết hàng | Không retry mù | Business rejection |
| Duplicate idempotency key | Đọc kết quả đã ghi | Không tạo effect mới |
| Write timeout sau khi gửi | **Không biết commit outcome** | Outcome lookup/commit protocol |
| Authentication/permission error | Thường không | Retry cùng credential không giải quyết |
| Throttling/rate limit | Có thể nhưng backoff có deadline | Retry sớm gây overload |
| Partition không đủ quorum | Thường fail fast hoặc chờ policy rõ | Retry liên tiếp không tự sửa partition |
| Socket reset khi write đang thực thi | Có thể UNKNOWN | Reset không chứng minh rollback |
| Operation cancelled | Cần xem phạm vi cancellation | Không chắc side effect đã rollback |

**Retry quyết định theo semantics**, không chỉ theo HTTP status hoặc exception class chung. Với database/driver thực, xem chính sách retryable reads/writes và transaction transient labels. Không bắt mọi `Exception` rồi chạy lại nguyên handler.

## 14. Deadline có thể hết sau khi database đã commit

Một lịch trình:

~~~text
T=000 ms: Client gửi CreateReservation(id=R42)
T=550 ms: Database commit thành công
T=580 ms: Response DB tới API
T=600 ms: API chuẩn bị response
T=610 ms: Kết nối client đã hết deadline
T=700 ms: Client retry từ thiết bị khác
~~~

Nếu API coi client timeout là “chưa ghi”, lần retry có thể tạo Reservation mới hoặc trừ tồn kho thêm. **Deadline giới hạn thời gian quan sát/tiêu tài nguyên, không phải cam kết rollback.**

Cần:

- Một **business intent ID** bền qua retry.
- Unique/conditional create hoặc outcome ledger ngăn effect lặp.
- Truy vấn outcome theo ID khi response mất.
- Trạng thái `UNKNOWN/PENDING_RECONCILIATION` nếu chưa xác minh.
- Driver transaction/commit protocol phù hợp.

Hai mục tiêu riêng:

1. **Timeliness:** Không chạy vô ích quá deadline khi có thể hủy an toàn.
2. **Correctness:** Không áp effect trùng và không báo sai khi commit xảy ra sát deadline.

## 15. Ví dụ NoSQL: giữ hàng với retry an toàn

Một API giữ 2 chiếc SKU-A cần bảo vệ:

- **Capacity invariant:** `available>=quantity` được kiểm tra trong atomic update.
- **Intent idempotency:** `reservationId=R42` chỉ tạo một hold.

Mô hình trong transaction phù hợp:

~~~text
BEGIN DATABASE TRANSACTION
  Find Intent(R42)
  If existing:
      compare fingerprint
      return stored outcome
  Else:
      Insert Intent(R42, fingerprint) IF ABSENT
      Conditional decrease Stock where available >= quantity
      If matched:
          Create Reservation(R42, HELD)
          Store Intent outcome=HELD
      Else:
          Store Intent outcome=REJECTED
COMMIT
~~~

Nếu timeout xảy ra sau lần đầu, client retry bằng **cùng R42 và cùng payload**. Server tìm kết quả hiện có thay vì trừ thêm.

### 15.1. Chỉ retry `$inc` chưa đủ

~~~javascript
db.stockPools.updateOne(
  { _id: "SKU-A", available: { $gte: 2 } },
  { $inc: { available: -2, held: 2 } }
);
~~~

Câu lệnh ngăn stock âm cho mỗi cập nhật nguyên tử, nhưng nếu response mất và kho còn đủ, retry có thể trừ thêm 2. Muốn an toàn cần **gắn marker intent và effect trong cùng consistency boundary** hoặc recovery workflow tương đương. Timeout 600 ms không làm một decrement trở thành idempotent.

## 16. Cancellation: hủy chờ không luôn hủy commit

Khi deadline hết, application có thể:

- Ngừng chờ response từ dependency.
- Hủy future/stream hoặc context.
- Yêu cầu driver gửi tín hiệu cancel.
- Đóng connection hoặc release pool slot.
- Không bắt đầu attempts mới.
- Giải phóng resources ở application nếu đã hủy an toàn.

Nhưng các pha khác nhau:

~~~text
Before request sent:
  Có thể ngăn thao tác bắt đầu.

During server execution:
  Server có thể nhận cancel hoặc đã xử lý một phần.

During commit:
  Quyết định commit có thể đã bền trước khi cancel tới.

After commit, before ACK:
  Cancellation không quay ngược commit đã hoàn tất.
~~~

**Không đồng nhất `future.cancel()` hoặc HTTP disconnect với transaction rollback.** Nếu có side effect, phải đọc authoritative state hoặc dùng idempotent retry.

### 16.1. Trách nhiệm cleanup

Deadline bị vượt không nên để lại:

- Connection checkout mãi không release.
- Transaction/session chưa end/abort theo contract.
- Background task không còn owner theo dõi outcome.
- Retry timer không thể hủy.
- Query tiếp tục chạy dài khi không còn caller.
- Reservation bị kẹt mà không có expiration/reconciliation.

Cleanup cũng cần bounded time. Tuy nhiên không nên bỏ durable intent/outcome nếu đó là điều kiện giữ đúng nghiệp vụ. Workflow có thể tiếp tục ở background **chỉ khi** có ownership/trạng thái bền và deadline riêng, không biến một HTTP request bị hủy thành worker sống vô hạn.

## 17. Timeout client và server không tự đồng bộ

Một request có thể bị chặn ở nhiều tầng:

~~~text
Browser timeout:                1000 ms
API Gateway timeout:             900 ms
Application deadline:            850 ms
DB driver per-attempt timeout:   700 ms
DB server execution timeout:     600 ms
~~~

Những con số không tự đồng bộ: Gateway có thể ngắt kết nối mà app chưa được báo; driver tự retry dưới một call; server query limit không tính pool wait/routing.

Nguyên tắc:

1. Hiểu đầy đủ **phạm vi của từng timeout**.
2. Truyền remaining budget và clamp vào giới hạn nội bộ.
3. Đặt pool-acquire và connect timeout phù hợp sub-budget.
4. Bật cancellation/interrupt theo API thật nếu hỗ trợ.
5. Đo mốc bắt đầu/kết thúc của từng tầng.
6. Không để driver auto-retries kéo vượt parent deadline.
7. Không khởi tạo transaction mới khi gần hết deadline.

Không có quy tắc “DB timeout luôn bằng 90% gateway timeout” áp dụng cho mọi trường hợp. Cần xét đường đi, loại request và response reserve.

## 18. Java: deadline helper dùng monotonic clock

Một lớp Java dùng deadline **trong cùng process**:

~~~java
import java.time.Duration;
import java.util.concurrent.TimeoutException;

public final class RequestDeadline {
    private final long deadlineNanos;

    private RequestDeadline(long deadlineNanos) {
        this.deadlineNanos = deadlineNanos;
    }

    public static RequestDeadline after(Duration budget) {
        if (budget.isZero() || budget.isNegative()) {
            throw new IllegalArgumentException("Budget must be positive");
        }
        return new RequestDeadline(
            System.nanoTime() + budget.toNanos()
        );
    }

    public long remainingNanos() {
        return Math.max(0L, deadlineNanos - System.nanoTime());
    }

    public Duration remaining() {
        return Duration.ofNanos(remainingNanos());
    }

    public boolean expired() {
        return remainingNanos() == 0L;
    }

    public Duration attemptLimit(
            Duration configured, Duration responseReserve
    ) throws TimeoutException {
        long usable = remainingNanos() - responseReserve.toNanos();
        if (usable <= 0L) {
            throw new TimeoutException("Request deadline exhausted");
        }
        long capped = Math.min(configured.toNanos(), usable);
        if (capped <= 0L) {
            throw new TimeoutException("No budget for next attempt");
        }
        return Duration.ofNanos(capped);
    }
}
~~~

**Giới hạn:** giả định budget đủ nhỏ để không overflow phép cộng `nanoTime + budget` hoặc `Duration.toNanos()`, và helper chỉ dùng trong **một process**. Code thư viện production nên xử lý overflow hoặc dùng Deadline primitive của framework.

`attemptLimit()` chỉ **tính Duration**. Caller phải truyền vào driver có timeout thực sự hoặc kết hợp cancellation/guard ở tầng app. Một blocking DB method không hỗ trợ timeout sẽ không tự dừng chỉ vì đã tính được deadline.

## 19. Java: retry bounded bởi parent deadline

Một skeleton tách policy khỏi driver cụ thể:

~~~java
import java.time.Duration;
import java.util.concurrent.ThreadLocalRandom;
import java.util.concurrent.TimeoutException;

public final class BoundedRetry {
    @FunctionalInterface
    public interface DbAttempt<T> {
        T run(Duration attemptTimeout) throws Exception;
    }

    public static final class RetryableDbException
            extends Exception {
        public RetryableDbException(String message) {
            super(message);
        }
    }

    public static <T> T execute(
            RequestDeadline deadline,
            int maxAttempts,
            Duration attemptCap,
            Duration responseReserve,
            DbAttempt<T> operation
    ) throws Exception {
        if (maxAttempts < 1) {
            throw new IllegalArgumentException("maxAttempts");
        }

        for (int attempt = 1; attempt <= maxAttempts; attempt++) {
            Duration perTry = deadline.attemptLimit(
                attemptCap, responseReserve
            );
            try {
                return operation.run(perTry);
            } catch (RetryableDbException error) {
                if (attempt == maxAttempts) {
                    throw error;
                }

                // Jitter chỉ minh họa.
                long maxSleepMs = Math.min(200L, 25L * attempt);
                long sleepMs = ThreadLocalRandom.current()
                    .nextLong(maxSleepMs + 1L);

                long requiredNanos =
                    Duration.ofMillis(sleepMs).toNanos()
                    + responseReserve.toNanos()
                    + Duration.ofMillis(20).toNanos();

                if (deadline.remainingNanos() <= requiredNanos) {
                    throw new TimeoutException(
                        "Not enough budget to retry"
                    );
                }

                // Production: cancellation-aware delay thường
                // tốt hơn Thread.sleep trong request thread.
                Thread.sleep(sleepMs);
            }
        }
        throw new AssertionError("Unreachable");
    }
}
~~~

**Mã khung:** callback `operation.run(perTry)` phải thực hiện timeout/interrupt/cleanup trong driver. Nếu driver tự retry, tổng attempts thực có thể vượt `maxAttempts`. Hãy chọn **tầng chịu trách nhiệm retry chính** hoặc phối hợp rõ chính sách ở tất cả tầng.

Skeleton chỉ retry `RetryableDbException`. Không được gói một write timeout có outcome UNKNOWN vô điều kiện thành exception retryable rồi replay; phải xác định outcome hoặc dựa trên business idempotency.

## 20. Java HTTP client: timeout xuống service khác

JDK `HttpClient` có thể đặt connect timeout và request timeout:

~~~java
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;

HttpClient client = HttpClient.newBuilder()
    .connectTimeout(Duration.ofMillis(100))
    .build();

Duration remaining = deadline.attemptLimit(
    Duration.ofMillis(300),
    Duration.ofMillis(50)
);

HttpRequest request = HttpRequest.newBuilder()
    .uri(URI.create("https://inventory.example/api/holds/R42"))
    .timeout(remaining)
    .GET()
    .build();

HttpResponse<String> response = client.send(
    request,
    HttpResponse.BodyHandlers.ofString()
);
~~~

Ví dụ cho việc **lấy timeout từ parent deadline**, không phải endpoint thật. `HttpRequest.timeout` giới hạn một lời gọi theo semantics JDK; Inventory Service vẫn cần truyền tiếp deadline đến NoSQL. Trong reactive/async code, cancellation theo context thường tốt hơn block request thread. Virtual threads không giảm số DB operations hay trách nhiệm bảo vệ deadline.

## 21. Deadline qua queue khác message lifetime

Một message nằm trong queue 30 giây trước khi worker nhận. Nếu hạn nghiệp vụ là “gửi thông báo trước 10:05”, worker không được nhận lại 5 phút ngân sách chỉ vì mới bắt đầu.

~~~json
{
  "eventId": "evt-1001",
  "operation": "SEND_CONFIRMATION",
  "createdAt": "2026-11-14T10:00:00Z",
  "expiresAt": "2026-11-14T10:05:00Z",
  "attempt": 1
}
~~~

Cần hỏi: khi hết hạn thì bỏ qua hay ghi EXPIRED; event tài chính có bắt buộc xử lý muộn không; queue delay có tính vào business SLO không; dead-letter replay có tái kích hoạt ý định cũ không; consumer có idempotency không?

**Queue retention, HTTP deadline, message processing deadline và business expiry là bốn khái niệm riêng**. Một event đã commit không được biến mất khỏi nghĩa vụ đối soát chỉ vì HTTP client timeout.

## 22. Retry nhiều tầng có thể bùng nổ

~~~text
Gateway: tối đa 3 attempts
  Order Service: tối đa 3 attempts
    Inventory Client: tối đa 3 attempts
      DB Driver: tối đa 3 attempts
~~~

Trường hợp xấu có thể tạo:

\[
3\times3\times3\times3=81
\]

DB attempts cho một business request, nếu mỗi tầng đều chạy đủ lượt. Đây là **mô hình cảnh báo**, không phải hành vi mọi driver.

Cần:

- Một tầng chủ đạo chịu trách nhiệm retry cho từng loại lỗi.
- Giới hạn hoặc tắt auto retries ở các tầng khác.
- Parent deadline đi qua toàn chuỗi.
- Metric `attempts per business intent`, `total downstream calls`.
- Retry token budget để giảm storm.
- Business ID/idempotency key ổn định.
- Backoff có jitter, không đồng loạt.

**Max attempts phải xét end-to-end**, không chỉ một SDK.

## 23. Hedged read theo deadline: nhanh hơn nhưng tăng tải

Nếu replica A chậm, có thể gửi cùng read tới B và dùng response hợp lệ đến trước:

~~~text
T=0      Read replica A
T=40ms   A chưa trả, hedge tới B
T=65ms   B trả kết quả phù hợp
T=70ms   Cancel/ignore A nếu còn
~~~

Lưu ý:

- Không hedge khi parent deadline gần hết.
- Giới hạn số hedges và extra traffic.
- **Response đến trước có thể stale**, phải kiểm tra consistency/version.
- Cancellation của A không nhất thiết dừng server work.
- Không hedge non-idempotent write tới hai owners độc lập.
- Khi cả replicas đều quá tải, hedging làm p99 tệ hơn.

Đây là tối ưu tail latency **chỉ khi đã bảo vệ semantics, deadline và load**.

## 24. Connection-pool wait cũng tiêu thụ deadline

Một bug phổ biến: DB query timeout 200 ms nhưng chờ pool không giới hạn.

~~~text
T=0       Request enters handler
T=850ms   Acquires DB connection
T=1050ms  DB query times out
~~~

Nếu API deadline 700 ms, request đã muộn **trước khi DB query bắt đầu**.

Cần:

- Pool-acquire timeout được chặn bởi remaining budget.
- Đo queue wait, pool utilization, reject rate.
- Không giữ connection trong lúc backoff sleep.
- Release session trong `finally` hoặc lifecycle hooks.
- Bounded concurrency/admission control trước pool.
- Hủy pool waiting nếu parent đã cancelled.

Pool lớn hơn không tự giải hot partition; có thể chỉ tạo thêm requests tranh cùng key và tăng conflicts.

## 25. MongoDB: timeout operation, chọn server và query execution

Với MongoDB, một request có thể tiêu thời gian ở nhiều pha:

~~~text
Application deadline
  -> Chọn server phù hợp read preference/topology
  -> Chờ connection pool
  -> TCP/TLS/network
  -> Gửi command
  -> MongoDB thực thi
  -> Nhận response
  -> Driver retry hoặc transaction commit logic
~~~

Các nhóm thiết lập/cơ chế cần phân biệt:

| Loại thiết lập/operation | Điều cần tìm hiểu |
|---|---|
| Server selection timeout | Driver chờ tìm primary/secondary phù hợp bao lâu? |
| Connect timeout | Một kết nối được thiết lập trong bao lâu? |
| Socket timeout | Một pha network I/O hoặc socket được giới hạn thế nào? |
| Pool checkout wait | Chờ connection tới bao giờ? |
| Server-side max execution | Lệnh nào áp dụng giới hạn thực thi, gồm giới hạn `maxTimeMS` khi có hỗ trợ? |
| Client-side operation timeout | Driver/phiên bản có cơ chế tổng operation timeout hay không, bao gồm những pha nào? |
| Transaction lifetime | Một transaction/session được phép kéo dài tới đâu? |
| Retryable reads/writes | Driver retry loại lệnh/lỗi nào và thời gian có bị khấu trừ đúng không? |

Không xem `maxTimeMS` của một query như “timeout toàn HTTP request”. Nó không bao gồm authentication, Java code trước/sau query, toàn bộ chờ gateway và các call khác. Ngay cả khi một command báo server timeout, ứng dụng vẫn phải xử lý cleanup và quyền retry theo contract.

### 25.1. Ví dụ truy vấn có giới hạn phía server

Ví dụ mongosh:

~~~javascript
db.orders.find(
  { customerId: "u42", status: "CONFIRMED" }
)
  .sort({ createdAt: -1 })
  .limit(50)
  .maxTimeMS(200);
~~~

`maxTimeMS(200)` là **giới hạn server-side execution theo semantics của command**, không phải giới hạn mọi công việc từ lúc HTTP request được nhận. Nếu request chỉ còn 80 ms, ứng dụng vẫn cần chọn timeout ngắn hơn hoặc không khởi tạo query.

Với các MongoDB driver hiện đại, cần đọc đúng hướng dẫn **client-side operation timeout** (nếu được hỗ trợ ở phiên bản đang dùng) và transaction helper; không sao chép cấu hình của driver khác rồi coi là tương đương.

### 25.2. Retryable write và unknown commit

MongoDB có cơ chế retryable writes/transaction error handling trong những phạm vi được hỗ trợ. Tuy nhiên một endpoint “Reserve và gửi email” không tự idempotent chỉ vì một lệnh write được driver retry đúng protocol.

Một timeout ở lúc commit có thể dẫn tới **unknown transaction commit result**. Ứng dụng nên dùng protocol/driver helper được hỗ trợ để xác định outcome, giữ business ID ổn định và không replay external side effect trong callback transaction.

## 26. DynamoDB: phân biệt API call timeout và attempt timeout

Trong AWS SDK for Java 2.x có khái niệm **API call timeout** cho toàn bộ một SDK API call và **API call attempt timeout** cho một attempt; chính sách retry của SDK ảnh hưởng tổng thời gian. Tên cấu hình cụ thể và khả năng kế thừa cần kiểm tra theo SDK đang sử dụng.

Ví dụ ý tưởng:

~~~text
HTTP request deadline = 800 ms
Remaining before DynamoDB = 500 ms

SDK API call total budget <= 450 ms
Per-attempt budget <= 180 ms
Retry attempts only if:
  retryable error
  remaining budget sufficient
  business operation safe
  global retry capacity allows
~~~

Nếu một AWS SDK call có `apiCallTimeout` 450 ms, điều đó **chỉ giới hạn SDK call**, không bao gồm thời gian HTTP request đã dùng ở gateway, validation hoặc những database calls khác. Một service có hai DynamoDB calls liên tiếp vẫn phải chia parent remaining budget cho cả hai.

DynamoDB có throttling, provisioned/on-demand capacity, partition hot spots, conditional writes và transactional APIs. Khi nhận throttling:

- Backoff/jitter giúp tránh flood nhưng không chữa được partition key quá nóng.
- Retry count cao có thể đẩy request vượt deadline.
- Condition failure vì nghiệp vụ không đủ hàng thường **không** nên retry mù.
- Một `TransactWriteItems` hoặc conditional write có retry/timeout phải tuân theo idempotency và client-token contract tương ứng.
- Một API call timeout không tự cho biết write đã commit hay chưa từ góc nhìn client.

### 26.1. Ví dụ chọn deadline theo attempt

~~~java
// Pseudocode gắn với builder thực tế tùy phiên bản SDK:
remaining = requestDeadline.remaining();
totalSdkBudget = min(remaining - responseReserve, configuredTotalCap);
attemptSdkBudget = min(configuredAttemptCap, totalSdkBudget);

// Cấu hình SDK API call timeout và attempt timeout tại
// điểm gọi hoặc client theo khả năng SDK version.
// Driver retries không được vượt totalSdkBudget.
~~~

Đây là **pseudocode**, không phải lời gọi AWS SDK Java hoàn chỉnh. Cấu hình retry ở client-level có thể khác cách override per-request; nếu không thể truyền dynamic timeout, phải lựa chọn client/context architecture phù hợp và có top-level cancellation guard.

## 27. Cassandra/ScyllaDB: timeout của coordinator và driver

Với Cassandra/ScyllaDB, một request có thể chạm coordinator và nhiều replicas theo consistency level. Timeout xảy ra khi:

- Client không tìm được node/coordinator phù hợp.
- Connection pool/reconnection đang chậm.
- Coordinator chờ quá lâu cho đủ replica responses.
- Node có GC pause, compaction hoặc disk pressure.
- Partition nóng gây queue hoặc read/write contention.
- LWT/conditional operation cần thêm coordination.
- Speculative execution/driver retry tạo thêm attempts.

Sự khác biệt cần hỏi:

| Timeout | Góc nhìn |
|---|---|
| Driver request timeout | Client ngừng chờ operation ở mức nào? |
| Server-side read/write timeout | Coordinator không đạt điều kiện trong thời gian quy định |
| Connection timeout | Không thiết lập/duy trì đường truyền |
| LWT/serial operation timeout | Quá hạn trong protocol điều kiện |
| Parent HTTP deadline | Toàn bộ hành trình từ request đến response |

Một read timeout theo consistency level không tự giống write timeout. Với write timeout, **một số replicas có thể đã nhận/áp dữ liệu**, và outcome có thể không rõ với caller.

Không coi retry trên coordinator khác là an toàn cho mọi write nếu statement không idempotent. CQL có thể có counter updates, batches và LWT với semantics khác nhau; cần đánh dấu/idempotent policy theo từng statement và xác định **driver speculative execution** có chạy nhiều requests đồng thời không.

### 27.1. Ví dụ một CQL truy vấn theo partition

~~~sql
SELECT occurred_at, event_id, payload
FROM events_by_device
WHERE device_id = 'device-42'
  AND bucket_day = '2026-11-14'
LIMIT 100;
~~~

Đây là ví dụ query shape; điều kiện partition-key phù hợp hay không phụ thuộc schema thật. Nếu query chạm hot partition, tăng timeout có thể làm queue dài hơn; hãy đo coordinator wait, partition skew, read repairs, tombstones và throttling. Một timeout tổng nhỏ hơn không sửa vấn đề data model, nhưng giúp tránh tiếp tục tiêu tài nguyên vào lời gọi đã quá deadline của người dùng.

## 28. Redis: command timeout, pool wait và script chạy lâu

Redis thường có thao tác ngắn trên một key, nhưng ứng dụng vẫn có thể bị chậm do:

- Network RTT hoặc connection pool bão hòa.
- Redis server event loop đang xử lý operation/script dài.
- Một key rất lớn hoặc command có độ phức tạp cao.
- Replication/failover khiến client reconnect.
- Retry đồng loạt sau timeout.
- Luồng pipeline có nhiều commands và response backpressure.

Một ví dụ khái niệm:

~~~text
API deadline: 500 ms
Connection pool wait cap: 30 ms
Command timeout cap: 100 ms
Optional retry: 1 attempt if read-only and remaining allows
Remaining after command: used for response/cleanup
~~~

Không đồng nhất Redis command atomic với việc có thể retry tùy ý sau timeout. Với `INCR`, server có thể đã tăng counter rồi mất response; gửi lại `INCR` làm tăng lần nữa. Với luồng cần exactly-once business effect, dùng stable intent/event ID và atomic dedup theo phạm vi thích hợp, hoặc chuyển nguồn quyết định sang datastore có durability contract đủ mạnh.

### 28.1. Script atomic không đồng nghĩa hủy tức thời

Một script Lua hoặc function đang chạy server-side có semantics/giới hạn thực thi riêng. Client timeout hoặc ngắt kết nối **không tự đảm bảo** script bị đảo ngược. Không tạo script dài chỉ vì client có timeout 200 ms; cần giới hạn độ phức tạp thao tác và dùng cách xử lý batch khi phù hợp.

## 29. Timeout và consistency level là hai trục tương tác

Một read cần consistency mạnh hơn có thể phải chờ nhiều replicas hoặc leader. Ví dụ (mô hình giả định):

~~~text
Read local replica không chờ:
  p50=8 ms, p99=60 ms, có thể stale

Read cần xác nhận nguồn có thẩm quyền:
  p50=35 ms, p99=180 ms, freshness mạnh hơn theo protocol
~~~

Nếu deadline đọc tổng là 100 ms:

- Một read consistency mạnh hơn có thể **không kịp p99** của request.
- Fallback đọc stale có thể vi phạm business requirement.
- Retry cùng thao tác trên replica khác không tạo dữ liệu mới nếu toàn hệ đang chờ quorum.
- Cần quyết định rõ: **fail closed**, `PENDING`, cache có nhãn stale hay kéo deadline.
- Khi business invariant như “cấp vé cuối” đòi consistency mạnh, không được hạ mức nhất quán chỉ để né timeout.

Một quyết định timeout phải xem cả **mức nhất quán, read/write concerns, topology và failure mode**, không chỉ đo RTT trung bình.

## 30. Tail latency: per-attempt p99 không phải request p99

Giả sử per-attempt latency khi khỏe trông khá tốt, nhưng 2% attempts bị timeout và retry. Logical request latency có thể có nhiều “bậc”:

~~~text
Requests hoàn thành attempt 1:  40–100 ms
Requests cần attempt 2:       200–400 ms
Requests cần attempt 3:       500–800 ms
Requests exhausted deadline:  800 ms hoặc lỗi
~~~

Ngay cả khi phần lớn requests thành công rất nhanh, **p99 toàn request** có thể bị chi phối bởi retries. Không thể suy p99 request từ p99 mỗi attempt nếu không biết tỷ lệ retry, phân phối latency, tương quan giữa attempts và backoff.

### 30.1. Đừng chỉ đo latency của successful attempts

Nếu 99 requests thành công trong 30 ms còn 1 request timeout sau 800 ms, dashboard chỉ tính successful DB calls có thể báo p99 ≈ 30 ms và che người dùng bị chờ 800 ms.

Nên có các phân phối:

- End-to-end latency **tất cả requests**, tách success/failure/deadline.
- DB attempt latency, tách success/timeout.
- Retry count và attempts per business intent.
- Time remaining lúc mỗi attempt bắt đầu.
- Pool wait và queue wait.
- Caller-cancelled-but-backend-still-running work.
- Commit-unknown duration và reconciliation age.

**SLO theo người dùng** cần tính cả những requests không có câu trả lời thành công, không chỉ những DB operations thành công.

## 31. Little's Law: deadline liên quan trực tiếp lượng request in-flight

Với hệ ổn định dưới các giả định phù hợp:

\[
L=\lambda W
\]

Trong đó `L` là số request trung bình trong hệ, `λ` là throughput đến/hoàn tất bình quân và `W` là thời gian ở trong hệ.

Ví dụ **giả định** 500 requests/s, mỗi request ở trong service trung bình 100 ms:

\[
L=500\times0,1=50.
\]

Nếu vì retry và chờ, thời gian ở service tăng lên 800 ms mà throughput vẫn giữ 500/s:

\[
L=500\times0,8=400.
\]

Số in-flight trung bình tăng từ 50 lên 400 theo mô hình. Điều này có thể làm pool, RAM, queue và downstream pressure tăng.

**Không suy `L` bằng số DB connections**: request có thể chờ queue hoặc chạy CPU mà không giữ connection. Khi hệ bão hòa, throughput có thể giảm, khiến các giả định λ không đổi không còn đúng. Little's Law là công cụ quan sát/ước lượng, không phải một phép đo khóa đang giữ.

### 31.1. Vì sao timeout dài có thể gây vòng lặp quá tải?

~~~text
DB chậm
  -> request lifetime dài
  -> more in-flight and pool wait
  -> client deadline exceeded
  -> retries tăng
  -> DB càng chậm
~~~

Giới hạn end-to-end deadline, admission control và retry budget giúp tránh đưa những requests đã vô ích vào hàng đợi. Tuy vậy, giảm deadline quá mạnh có thể làm **false timeouts** khi DB đang khỏe nhưng latency tail hợp lệ, nên cần chọn dựa trên dữ liệu.

## 32. Circuit breaker, admission control và load shedding

Khi dependency quá tải hoặc không có quorum, retry mỗi 50 ms không giúp. Một kiến trúc có thể dùng:

~~~mermaid
flowchart TD
    A["Incoming business requests"] --> B["Admission / rate limit"]
    B --> C{"Còn capacity và deadline?"}
    C -->|Không| D["Reject fast / pending contract"]
    C -->|Có| E["Bounded queue and DB attempt"]
    E --> F{"Kết quả?"}
    F -->|Success| G["Return result"]
    F -->|Business rejection| H["Return business result"]
    F -->|Retryable technical| I{"Budget và breaker cho phép?"}
    I -->|Có| J["Backoff+jitter bounded"]
    J --> E
    I -->|Không| K["Stop, timeout / reconcile"]
~~~

Các cơ chế:

- **Admission control:** giới hạn request mới trước khi tiêu pool/database resources.
- **Bounded queue:** không cho hàng đợi tăng vô hạn.
- **Circuit breaker:** khi dependency đang lỗi kéo dài, fail fast ở những call không đáng gửi.
- **Load shedding:** bỏ/hoãn request theo ưu tiên dịch vụ.
- **Backpressure:** báo downstream đang quá tải để upstream giảm tốc.
- **Retry token budget:** chỉ cho một tỷ lệ retry nhất định nhằm giữ capacity cho yêu cầu mới.
- **Per-key concurrency limit:** giảm số writes tranh cùng hot key.
- **Deadline propagation:** request hết hạn không còn được cấp attempt mới.

**Fail fast cần đúng business contract.** Một API đọc có thể trả lỗi 503 nhanh, nhưng một thao tác tài chính có outcome UNKNOWN cần trả trạng thái để đối soát, không được tuyên bố đã thất bại chắc chắn.

## 33. Dashboard nên đo request deadline và attempt timeout riêng

Một dashboard chỉ có `database_timeout_count` không cho biết request có thật sự vượt thời hạn của người dùng hay không. Cần đo từng lớp:

| Nhóm | Metric | Ý nghĩa |
|---|---|---|
| End-to-end | HTTP p50/p95/p99, success/error/deadline | Người dùng chờ bao lâu? |
| Deadline | Deadline exceeded count, remaining budget | Có bắt đầu call khi quá muộn không? |
| Attempts | Attempts per intent và retry amplification | Có retry storm không? |
| Attempt timeout | Timeout rate theo DB operation/replica | Dependency nào chậm? |
| Queueing | Waiting time trong app và DB pool | Tắc trước khi DB thực thi? |
| Backoff | Tổng thời gian backoff mỗi request | Retry chờ bao lâu? |
| Server processing | Query execution latency và scanned items | DB work thật sự tốn bao nhiêu? |
| Concurrency | In-flight requests, pool utilization, max queue | Overload hay thừa capacity? |
| Dependency | Retryable error types, throttling, connection reset | Phân loại lỗi đúng chưa? |
| Correctness | Unknown commit outcomes, duplicate effect, pending intents | Có bảo vệ nghiệp vụ khi timeout không? |
| Cancellation | Cancel attempts, successful cancels, orphan work | Có công việc vô ích sau deadline không? |
| Reliability | Circuit breaker opens, admission rejects | Có fail fast đúng lúc không? |

Đừng gộp **client deadline exceeded** với **server operation timeout** thành một biểu đồ đơn. Một DB call có thể hoàn thành trong 50 ms nhưng request đã chờ queue 700 ms và vượt deadline; ngược lại một DB call timeout 100 ms rồi retry thành công vẫn có thể kịp deadline 500 ms.

### 33.1. Phân biệt tỷ lệ retry với tỷ lệ request lỗi

Ví dụ:

~~~text
Business requests:     1.000
Total DB attempts:     1.300
DB attempts timeout:     180
Business requests failed: 20
~~~

Attempt timeout rate = 180/1300 ≈ 13,8%, nhưng business failure rate = 20/1000 = 2%. Nếu hệ retry tốt, nhiều DB timeouts không hiện thành lỗi với người dùng — nhưng chúng vẫn tốn capacity và có thể tạo p99 lớn. Cần theo dõi **cả hai tỉ lệ**.

## 34. Tracing: hiển thị thời gian đã tiêu ở đâu

Một trace giả định:

~~~text
traceId=tr-1001, reservationId=R42
Parent deadline: 800 ms

  Gateway and routing            35 ms
  Auth and validation            50 ms
  Inventory pool wait            90 ms
  DB attempt #1                 180 ms -> timeout
  Retry backoff                  45 ms
  DB attempt #2                 160 ms -> success
  Commit result handling         40 ms
  Serialization + network        30 ms

Total logical request:          630 ms
Remaining at response:         170 ms
~~~

Các con số minh họa và giả định các bước tuần tự để dễ cộng. Trong hệ thực, spans có thể chồng lấp và tổng duration cần dựa vào actual critical path.

Một span phụ nên chứa metadata an toàn:

~~~text
db.system = "mongodb"  (hoặc db platform)
db.operation = "FindOrder"
retry.attempt = 2
retry.reason = "transient_timeout"
retry.remaining_budget_ms = 320
db.pool_wait_ms = 15
db.attempt_timeout_ms = 200
caller.deadline_ms = 800
commit.outcome = "known_success"
~~~

Không log plaintext credentials, payment details hoặc payload nhạy cảm. Với high-cardinality business IDs, cân nhắc sampling và cardinality limits trong metrics; dùng tracing/log phù hợp để điều tra từng intent khi cần.

### 34.1. Traces cho timeout sau client disconnect

Nếu client ngắt ở T=800 ms nhưng DB operation vẫn chạy tới T=2.000 ms, tracing cần làm rõ:

- Lời gọi còn active sau parent cancellation bao lâu?
- Driver/connector có nhận cancel signal không?
- Có giữ connection/transaction trong thời gian đó không?
- Commit đã xảy ra hay chưa?
- Side effect được xác minh bằng business ID nào?
- Có worker background nào được handoff một cách bền vững không?

Không kết luận “database chậm 2 giây” nếu thực tế 1,5 giây là queue wait hoặc timeout không được propagate.

## 35. Định nghĩa response khi hết deadline

Một API có thể trả:

| Trạng thái | Khi nào hợp lý | Lưu ý |
|---|---|---|
| Success với kết quả | Có bằng chứng operation hoàn tất trước deadline xử lý | Không tạo success giả nếu chỉ accepted |
| Business rejection | Operation bị từ chối hợp lệ (hết hàng/không đủ quyền) | Không retry vô hạn |
| Deadline exceeded / timeout | Hết ngân sách thời gian | Không suy commit chưa xảy ra |
| Accepted/PENDING | Đã ghi durable intent và workflow tiếp tục theo contract | Cần status endpoint/notifications |
| UNKNOWN/RECONCILING | Có side effect có thể đã commit nhưng chưa xác nhận | Cần outcome lookup |
| Service unavailable / overloaded | Dependency không có quorum/capacity | Có thể hướng dẫn bounded retry với same ID |
| Partial result | Read được phép trả thiếu/stale có ghi nhãn | Không áp dụng cho mọi operation |

HTTP status code là lựa chọn của API. Ví dụ `202 Accepted` phù hợp khi intent đã được lưu bền và có cơ chế xử lý tiếp; `503` phù hợp khi service không thể nhận thêm công việc. Không có một mapping cứng áp dụng cho mọi hệ. Điều quan trọng hơn là **caller biết retry thế nào, dùng ID nào và khi nào kết quả là cuối cùng**.

### 35.1. Khi caller tự đặt deadline ngắn

Nếu client gửi một deadline 50 ms nhưng API tối thiểu cần 100 ms để xác minh quyền và ghi durable intent, server có thể từ chối sớm thay vì khởi tạo một write khó hoàn thành kịp. Việc **fail fast** có thể bảo vệ correctness và tài nguyên tốt hơn cố ghi rồi cắt connection ở giữa commit.

Ngược lại, nếu đã có transaction commit được xác nhận nhanh mà client connection vừa hết hạn, không được tự rollback một business result hoàn tất chỉ vì đường trả response chậm.

## 36. Mẫu policy theo từng loại operation

| Operation | Deadline tổng | Per-attempt cap | Retry policy | Khi timeout |
|---|---|---|---|---|
| GET catalog cache | Ngắn | Ngắn | Một fallback/retry nếu còn thời gian | Có thể stale cache nếu contract cho |
| GET Order theo ID | Vừa | Ngắn hơn parent | Retry read nếu consistency phù hợp | Trả lỗi/pending, không đoán |
| Search nhiều partitions | Có fan-out budget | Cap mỗi subquery | Retry một subset nếu có room | Partial nếu API hỗ trợ, nếu không fail |
| Conditional reserve | Chặt theo UX | Phải đủ cho commit hợp lệ | Chỉ theo driver + business ID | Tra outcome, không trừ lại vô điều kiện |
| Multi-document transaction | Cần phân bổ đủ cho commit/rollback | Cân nhắc transaction helper | Retry transient abort đúng contract | Unknown commit handling |
| Analytics batch | Có thể dài và async | Mỗi batch/chunk có cap | Checkpoint/resume | Đưa vào job state |
| Payment provider | Theo hợp đồng provider | Cap provider call | Stable paymentAttemptId | Query/reconcile outcome |

Bảng là **mô hình để bắt đầu thiết kế**, không phải số timeout cụ thể. Cùng một NoSQL database có thể được truy cập qua các operation có rủi ro và budgets rất khác.

## 37. Thực nghiệm A: một attempt dài vs nhiều attempts bounded

Dựng một stub NoSQL dependency có thể giả lập latency mà không làm hỏng dữ liệu thật. Giả sử parent deadline 900 ms và response reserve 80 ms.

Thử ba chính sách:

| Chính sách | Attempt timeout | Retry | Backoff |
|---|---:|---:|---|
| A | 800 ms | Không | Không |
| B | 250 ms | Tối đa 3 attempts | 50, 100 ms |
| C | 250 ms | Tối đa 3 attempts nhưng kiểm tra remaining | Jitter theo budget |

Cho dependency latency giả:

~~~text
Request 1:  60 ms
Request 2: 120 ms
Request 3: 700 ms
Request 4: 1500 ms
Request 5: DB trả transient error sau 100 ms
~~~

Hãy đo:

1. Tổng thời gian mỗi logical request.
2. Số attempts thực đã bắt đầu.
3. Từng attempt có timeout đúng không?
4. Số requests vượt 900 ms.
5. Thời gian dependency còn xử lý sau khi client đã bỏ cuộc.
6. Total DB work/đơn vị thời gian.
7. Có bao nhiêu successes được cứu bởi retry trong deadline?
8. Policy nào tạo tail latency và extra load tốt hơn trong mô hình?

Đừng mặc định policy B/C luôn tốt hơn A: nếu dependency đều trả 700 ms và timeout 250 ms, cả B/C có thể tạo **false timeouts và không hoàn tất được request**, dù một attempt dài hơn có thể thành công trước 900 ms. Chọn cutoff từ latency distribution và failover characteristics thực tế.

## 38. Thực nghiệm B: lỗi mạng trước và sau commit

Đây là lab kiểm tra **đúng nghiệp vụ**, không chỉ timeout:

~~~text
Case 1: TCP connect không thành công; request chưa gửi.
Case 2: DB đã nhận request, đang thực thi.
Case 3: DB commit thành công, response bị cắt.
Case 4: DB transaction abort được xác nhận.
Case 5: Client cancellation tới sau khi DB commit.
~~~

Với command `Reserve(R42, quantity=2)`:

- Giữ business ID R42 ổn định giữa attempts.
- Lưu intent/result ledger theo consistency boundary.
- Sau case 3 và case 5, xác minh DB state bằng outcome query.
- Đảm bảo không có hai holds cho cùng R42.
- Đảm bảo available stock không âm.
- Phân biệt **known abort** với **unknown commit**.
- Không gọi external payment/email trong callback transaction có thể retry.

Kỳ vọng: timeout/cancel không dẫn tới duplicate business effect, dù application có thể trả UNKNOWN để đối soát.

## 39. Thực nghiệm C: overload và retry storm

Dựng môi trường thử với một hot partition, tăng load cho tới khi latency/timeout tăng. So sánh:

1. Retry lập tức không jitter.
2. Exponential backoff có jitter.
3. Backoff + retry budget + request deadline.
4. Bounded concurrency + admission control.
5. Circuit breaker/open khi dependency lỗi kéo dài.

Đo:

~~~text
Offered requests/sec
Achieved successful business operations/sec
DB attempt amplification
HTTP p95/p99 (success + timeout)
Pool queue wait
Active/in-flight requests
Transient errors vs business rejections
Deadline exceeded rate
DB resource saturation per hot partition
~~~

Nếu throughput giữ nguyên mà DB attempts/sec tăng mạnh, retries đang gây waste. Nếu một request bị timeout ở gateway nhưng server vẫn chạy dài, cần đo orphan work. Không chỉ xem success rate ở các requests ngắn rồi kết luận hệ khỏe.

### 39.1. Fault injection phải đúng phạm vi

Có thể mô phỏng network delay, packet loss, node failover, coordinator pause, throttling hoặc connection pool exhaustion trong **môi trường thử được phép gây gián đoạn**. Không gây network partition hoặc kill production DB để đo timeout tùy tiện.

Một fault injector trả “timeout” ngay có thể không tái tạo đúng case **server đã commit nhưng ACK mất**. Cần thiết kế case commit-success-response-lost riêng.

## 40. Thực nghiệm D: deadline propagation xuyên ba service

Một giả lập ba service:

~~~text
Client -> Gateway -> Order -> Inventory -> NoSQL
~~~

Với parent deadline 1.000 ms:

- Gateway tiêu 100 ms.
- Order tiêu 180 ms.
- Inventory nhận còn khoảng 720 ms trước network/safety reserve.
- NoSQL read/write và retries phải dùng thời gian còn lại, không reset 1.000 ms.
- Mỗi service ghi `remainingDeadlineAtEntry` và trước mỗi dependency attempt.
- So sánh thời gian request ở từng service với parent deadline.

Làm phiên bản **không truyền deadline** và phiên bản **truyền remaining budget**. Gây queue wait ở Inventory 600 ms, quan sát DB attempt có còn được khởi tạo sau khi parent hết hạn không.

Hãy đặt acceptance criteria:

1. Không bắt đầu DB attempt mới nếu remaining budget không đủ mức tối thiểu.
2. Parent cancellation được truyền đến child theo khả năng framework.
3. Không có retry timer tiếp tục vô hạn.
4. Với write outcome unknown, business ID vẫn được đối soát.
5. Không trả success nếu chỉ có intent accepted.

## 41. Cách hiệu chỉnh timeout từ dữ liệu thực tế

Không nên lấy một số timeout từ blog rồi áp cho mọi hệ. Một quy trình:

1. **Chọn loại operation:** point read, range scan, LWT, transaction, write một document.
2. **Chọn latency SLO:** p95/p99 end-to-end và success target.
3. **Đo phân phối khỏe:** pool wait, network RTT, DB execution, retries, tail under background load.
4. **Xác định failure modes:** node failure, cross-region RTT, quorum unavailable, throttling.
5. **Chọn deadline tổng** với UX/caller budget và response reserve.
6. **Chọn per-attempt cutoff** dựa trên latency tail của healthy requests và tỷ lệ false timeout chấp nhận được.
7. **Giới hạn max attempts** bởi deadline/backoff và extra load budget.
8. **Phân loại read/write semantics** và các lỗi được phép retry.
9. **Thiết kế cancellation/cleanup** và recovery cho unknown commit.
10. **Thử fault injection**, so kết quả theo SLO và correctness.
11. **Triển khai từng bước**, theo dõi timeout rate và p99 trước/sau.
12. **Điều chỉnh theo evidence**, không chỉ nâng timeout khi lỗi tăng.

Nếu một attempt khỏe thường cần 350 ms ở p99, đặt cap 100 ms có thể khiến nhiều healthy operations bị cắt rồi retry vô ích. Nếu dependency bị kẹt hàng chục giây mà parent deadline chỉ 800 ms, cap 30 giây không giúp request hoàn thành hợp lệ. Chọn ngưỡng giữa hai thái cực.

## 42. Runbook: khi timeout tăng đột biến

Giả sử cảnh báo:

~~~text
GET /orders p99: 280 ms -> 1.800 ms
DB attempt timeouts: 0.5% -> 18%
Retry amplification: 1.1 -> 2.9
Pool checkout p99: 15 ms -> 620 ms
~~~

Một quy trình xử lý sự cố nên đi theo bằng chứng:

1. **Xác định phạm vi:** chỉ một endpoint/tenant/partition hay mọi DB operations?
2. **Đo parent deadline:** bao nhiêu requests thực sự vượt end-to-end deadline?
3. **Phân rã span:** queue, pool wait, connection, server selection, execution, retries, serialization.
4. **Xem retry amplification:** driver/gateway/app có cùng retry và nhân tải không?
5. **Kiểm tra hot partitions/replicas:** skew, throttling, leader changes, slow storage và network RTT.
6. **Nhìn consistency mode:** có đang chờ quorum/primary không reachable không?
7. **Giảm retries vô ích:** bật retry budget/backoff/jitter; cân nhắc breaker/admission control.
8. **Giữ business safety:** không hạ consistency đối với stock/payment chỉ để giảm timeout.
9. **Kiểm tra unknown writes:** với timeout sau send, đối soát theo business IDs.
10. **Khôi phục có kiểm soát:** kiểm tra pool, queues, pending intents, leaked sessions.
11. **Đo hồi phục:** end-to-end p99, attempt rate, successful business ops, backlog.
12. **Postmortem:** bổ sung test và timeout scope docs vào runbook.

### 42.1. Những biện pháp “nhanh” có thể làm tệ hơn

- Tăng đồng loạt timeout mọi tầng gấp mười: request giữ resources lâu hơn, overload tiếp tục.
- Tăng pool size không giới hạn: làm nhiều requests tranh cùng hot key.
- Retry ngay sau every timeout: tăng áp lực lên dependency lỗi.
- Giảm consistency level khi checkout: có thể mất invariant.
- Tự động replay một payment bằng ID mới: có thể double charge.
- Cắt mọi background tasks ngay khi HTTP disconnect: có thể để lại business intent đã ghi nhưng không có owner xử lý.

Biện pháp tốt thường là **đúng lỗi, đúng tầng**: nếu bottleneck ở pool wait, xử lý saturation/admission; nếu ở coordinator timeout do quorum unavailable, retry liên tiếp không giúp; nếu ở hot partition, sửa data model/load distribution.

## 43. Lỗi DeadlineExceeded phải chứa thông tin gì?

Khi trả timeout/deadline exceeded, service không nhất thiết tiết lộ chi tiết nội bộ, nhưng cần một contract để caller hành động đúng.

Ví dụ response mô tả có thể là:

~~~json
{
  "error": "DEADLINE_EXCEEDED",
  "requestId": "req-a82",
  "reservationId": "R42",
  "outcome": "UNKNOWN",
  "statusLookup": "/v1/reservations/R42",
  "retryPolicy": "RETRY_SAME_INTENT_ID_AFTER_STATUS_CHECK"
}
~~~

Chỉ trả `outcome=UNKNOWN` khi đúng là không xác định commit; với một read-only timeout có thể chỉ cần `DEADLINE_EXCEEDED`. Không phải mọi timeout đều đòi status lookup. Đảm bảo API không lộ ID/URL cho người không đủ quyền và tránh cho client dự đoán kết quả chỉ từ response code.

Một response khác cho workflow async:

~~~json
{
  "reservationId": "R42",
  "status": "PENDING",
  "pollAfterMs": 1000
}
~~~

Chỉ hợp lệ nếu intent đã được **ghi nhận bền** và hệ có worker/reconciliation chịu trách nhiệm hoàn tất hoặc quyết định cuối. Nếu chỉ đặt message trong RAM rồi trả PENDING, một process crash có thể làm mất lời hứa xử lý.

## 44. Deadline theo ưu tiên nghiệp vụ và fairness

Không phải mọi request có cùng mức quan trọng:

| Operation | Độ ưu tiên tương đối | Chiến lược |
|---|---|---|
| GET catalog | Có thể degrade | Cache với freshness metadata |
| GET Order vừa cập nhật | Cần read-your-writes | Fallback nguồn phù hợp theo budget |
| Confirm reservation | Cao, liên quan invariant | Giữ consistency và outcome tracking |
| Background analytics | Có thể hoãn | Batch checkpoint, rate-limit |
| Reconciliation tài chính | Không nên bỏ mất | Durable workflow, deadline mỗi bước riêng |
| Expire hold | Cần hoàn quota có điều kiện | Bounded worker + idempotent release |

Nếu analytics quét hàng triệu records trong cùng pool với checkout, timeout của checkout có thể tăng dù không có node lỗi. Các cơ chế tách pool/capacity, rate limit theo tenant, workload isolation và admission control thường quan trọng hơn chỉ chỉnh per-attempt timeout.

### 44.1. Deadline ngắn không thay thế admission control

Một request có deadline 100 ms nhưng vẫn có thể tiêu CPU/network/DB work trong 100 ms. Hàng triệu requests như vậy vẫn có thể làm cụm quá tải. Deadline giúp giới hạn **thời gian mỗi request**, còn admission/rate limits giúp giới hạn **số requests và mức tài nguyên tổng**.

Không sử dụng deadline do client chỉ định làm lý do chiếm nhiều tài nguyên hơn. Server cần clamp budgets và bảo vệ fairness.

## 45. Những nhầm lẫn thường gặp

| Nhầm lẫn | Vì sao sai | Cách làm đúng |
|---|---|---|
| “DB timeout 500 ms nghĩa HTTP request tối đa 500 ms” | Chưa tính auth, queue, network, retries | Parent deadline end-to-end |
| “Ba retries × timeout luôn trong SLO” | Attempts và backoff cộng dồn | Kiểm tra remaining trước mỗi attempt |
| “Timeout per attempt không cần khi có deadline” | Một attempt có thể treo tới deadline | Per-attempt cap + parent guard |
| “Đã đặt server max execution thì đủ” | Chỉ bao phủ pha thực thi nhất định | Driver/pool/network/HTTP budgets |
| “Client disconnect nghĩa DB rollback” | Commit có thể xảy ra trước ACK | Business ID và outcome lookup |
| “Cancel future chắc chắn cancel transaction” | Cancellation có thể tới sau commit | Reconcile unknown outcome |
| “Retry một write timeout luôn an toàn” | Có thể nhân đôi side effect | Idempotency và driver contract |
| “Hết hàng là lỗi transient” | Business rejection | Không retry mù |
| “Bất kỳ Exception đều retry được” | Có permission/validation/business errors | Phân loại lỗi |
| “Nâng timeout giải quyết overload” | Requests in-flight tăng | Điều tra queue, hotspot, admission |
| “Pool lớn hơn giải mọi timeout” | Có thể tăng contention | Bounded concurrency và per-key limits |
| “Cùng retry policy trên mọi service là tốt” | Multiplicative attempts | Một owner retry rõ |
| “Jitter không cần vì có deadline” | Clients vẫn có thể retry đồng loạt | Backoff có jitter và budget |
| “Còn 100 ms thì cứ bắt đầu call 500 ms” | Call vượt parent | Cap theo remaining/reserve |
| “Absolute deadline UTC luôn đúng giữa máy” | Clock skew/misconfiguration | Giao thức propagating budget |
| “Java nanoTime của hai máy cùng mốc” | Monotonic origin khác nhau | Chỉ dùng trong process |
| “GET replica nhanh nhất luôn đạt consistency” | Replica có thể stale | Kiểm tra read concern/version |
| “Hedged write tăng tốc như hedged read” | Có thể nhân đôi write effect | Không hedge non-idempotent write |
| “p99 DB attempt là p99 của user” | Retry, queue và HTTP overhead khác | Đo logical end-to-end |
| “Chỉ ghi successful latency là đủ” | Loại bỏ timeout cases khỏi biểu đồ | Đo mọi responses/outcomes |
| “Hết HTTP deadline thì message đã commit được bỏ qua” | Workflow khác vòng đời HTTP | Durable intent/owner/reconciliation |
| “Tăng timeout không ảnh hưởng capacity” | Little's Law: in-flight có thể tăng | Theo dõi queue/concurrency |
| “Một timeout là data loss” | Có thể chỉ stale/response lost | Verify authoritative outcome |
| “Timeout ở managed DB giống mọi engine” | SDK policies khác nhau | Đọc docs của driver và phiên bản |

## 46. Bài tập A — Tính tổng thời gian tối đa và deadline

Một endpoint có:

~~~text
Request deadline = 1000 ms
Auth/validation = 120 ms
Response reserve = 100 ms
Pool wait per DB attempt = 80 ms
Per-attempt DB execution timeout = 250 ms
Max attempts = 3
Backoff giữa attempts = 60 ms, 120 ms
~~~

Giả sử ba attempts đều chạy đến timeout, chờ pool và backoff tuần tự:

1. Tính tổng thời gian không xét deadline guard.
2. Khoảng thời gian nào HTTP request thực tế vượt 1000 ms?
3. Nếu request còn 350 ms trước attempt #3, attempt #3 tối đa được chờ bao lâu sau khi trừ response reserve và pool wait?
4. Nếu backoff #2 có jitter 120 ms nhưng remaining chỉ 150 ms, còn nên retry không?
5. Nếu DB đang quá tải và mọi attempts đều timeout, maxRetries=3 có cải thiện business success không?
6. Nếu request deadline đổi thành 700 ms, policy nào nên thay đổi?
7. Vì sao cần đo pool wait riêng với DB execution?
8. Nếu một write commit ở attempt #2 nhưng ACK mất, kết quả cuối của API nên được diễn giải thế nào?
9. Tại sao không dùng `maxAttempts × perAttemptTimeout` làm hard bound nếu driver còn auto retry?
10. Viết pseudocode tính remaining budget trước mỗi attempt.

## 47. Bài tập B — Thiết kế retry cho GET và POST khác nhau

Hai API:

~~~http
GET /orders/O42
POST /reservations
Idempotency-Key: R42
Content-Type: application/json

{"sku":"SKU-A","quantity":2}
~~~

Hãy:

1. Định nghĩa consistency requirement cho GET Order.
2. Chọn parent deadline, per-attempt timeout và số retries theo số liệu giả định của bạn.
3. Nếu GET replica A timeout, liệu đọc replica B có thể trả stale version không?
4. Với POST, mô tả atomic condition giữ stock không âm.
5. Mô tả durable ledger/idempotency để retry R42 không trừ hai lần.
6. Nếu POST commit rồi response mất, client làm gì?
7. Nếu POST bị từ chối vì hết hàng, retry ngay có hợp lý không?
8. Nếu cancellation đến lúc commit, cần outcome lookup như thế nào?
9. Vẽ trace chứa pool wait, attempt #1, backoff, attempt #2.
10. Nêu các metrics xác nhận không có business duplicate.

## 48. Bài tập C — Dịch vụ nhiều tầng và retry amplification

Cho:

~~~text
Gateway -> Order -> Inventory -> NoSQL

Gateway max attempts: 2
Order max attempts:   3
Inventory max:        2
Driver max:           3
~~~

Bài tập:

1. Tính upper bound attempts theo mô hình mọi tầng retry đầy đủ.
2. Phân tích vì sao upper bound này có thể không xuất hiện trong thực tế.
3. Thiết kế policy để chỉ còn một retry owner ở tầng thích hợp.
4. Parent deadline 1.200 ms được truyền từ Gateway qua Order và Inventory thế nào?
5. Nếu Order đã tiêu 500 ms, Inventory có được tự đặt thêm 1.200 ms không?
6. Nếu Inventory đang chờ pool 400 ms, DB attempt cần được cấp bao nhiêu thời gian?
7. Khi Inventory trả unknown commit, Gateway có nên replay POST với một ID mới không?
8. Cần alert gì nếu amplification tăng gấp đôi mà business success rate không tăng?
9. Bật circuit breaker ở đâu và khi nào không nên fallback sang stale data?
10. Thiết kế fault injection tái tạo mất response sau commit.

## 49. Bài tập D — Sửa một API có retry sai

Pseudocode ban đầu:

~~~java
public Reservation createReservation(Command cmd) {
    for (int i = 0; i < 5; i++) {
        try {
            return db.decrementStockAndInsertOrder(cmd);
        } catch (Exception e) {
            Thread.sleep(500);
        }
    }
    throw new RuntimeException("Failed");
}
~~~

Hãy tìm và sửa các vấn đề:

- Không có request deadline tổng.
- Per-attempt timeout/DB pool wait không rõ.
- Bắt mọi exception không phân loại.
- Retry không kiểm tra remaining budget.
- Sleep không có jitter, có thể không hủy.
- Có nguy cơ double-decrement sau unknown commit.
- Không có business ID/fingerprint/result ledger.
- Không thể phân biệt business rejection với lỗi kỹ thuật.
- Không xử lý interruption/cancellation/session cleanup.
- Không ghi telemetry attempts, backoff, outcome.
- Có thể driver tự retry bên trong, làm số attempts thực khác số vòng lặp.

Bản sửa cần nêu **business invariant** trước khi chọn timeout: cùng ý định chỉ giữ một lần; capacity không âm; deadline hết không được tạo effect trùng hoặc giả báo rollback.

## 50. Câu hỏi tự kiểm tra

1. Deadline khác per-attempt timeout thế nào?
2. Vì sao ba attempts mỗi attempt 300 ms có thể vượt request deadline 700 ms?
3. Một deadline tuyệt đối có được reset khi retry không?
4. Vì sao monotonic clock hữu ích trong một process?
5. Có được truyền raw `System.nanoTime()` giữa hai máy không?
6. SLO p99 và hard deadline có phải một không?
7. Những pha nào ngoài DB execution cũng tiêu request budget?
8. Deadline cha được propagate xuống child operations theo điều kiện nào?
9. Tại sao pool checkout wait cần được giới hạn?
10. Vì sao server query execution timeout không tự giới hạn HTTP call?
11. Những lỗi nào nên retry và lỗi nào không?
12. Tại sao retry budget phải tính backoff?
13. Jitter giúp giải vấn đề gì?
14. Một write timeout sau khi gửi request có chứng minh rollback không?
15. Cần business ID/outcome ledger khi nào?
16. Client cancellation có bắt buộc server rollback không?
17. Driver auto retry và application retry có thể nhân tải ra sao?
18. Hedged read có nguy cơ trả stale response không?
19. Tại sao hedged write không nên dùng tùy tiện?
20. Khi nào cần fail fast hoặc circuit breaker?
21. Vì sao tăng pool size có thể làm hot partition tệ hơn?
22. Little's Law liên hệ request lifetime và in-flight như thế nào?
23. p99 DB attempt có phản ánh p99 HTTP không?
24. Vì sao dashboard phải tính cả requests timeout?
25. GET read timeout khác transaction write timeout ra sao?
26. MongoDB server max execution khác client operation deadline thế nào?
27. DynamoDB SDK API call timeout và attempt timeout khác phạm vi ra sao?
28. Cassandra coordinator timeout có cho biết mọi replica chưa ghi không?
29. Redis `INCR` có an toàn khi client timeout và retry không?
30. Business workflow deadline khác HTTP request deadline ra sao?
31. Một message quá hạn có luôn được phép bỏ không?
32. Retry có thể làm tăng load trong sự cố như thế nào?
33. Khi nào một attempt mới không còn đủ minimum useful budget?
34. Dấu hiệu nào chứng minh request vẫn chạy sau client disconnect?
35. Khi ứng dụng trả UNKNOWN, cần kế hoạch reconciliation nào?

## 51. Tổng kết: một thời hạn cho hành trình, nhiều giới hạn cho các chặng

**Deadline toàn yêu cầu** ràng buộc toàn bộ hành trình từ lúc nhận request đến lúc phản hồi hoặc chuyển trạng thái theo contract. **Per-attempt timeout** giới hạn từng lượt gọi cụ thể và giúp phát hiện dependency chậm, nhưng tự nó không ngăn tổng thời gian vượt SLO khi có queue, pool wait, retry, backoff, transaction hoặc nhiều services.

Một thiết kế NoSQL an toàn và thực tế nên:

~~~text
1. Đặt end-to-end deadline dựa trên UX/SLO và risk.
2. Tính remaining budget bằng monotonic clock ở mỗi process.
3. Propagate remaining budget giữa services một cách đáng tin.
4. Cấp attempt timeout <= remaining budget trừ response reserve.
5. Giới hạn max attempts, backoff+jitter và retry capacity.
6. Phân loại lỗi; không retry business rejection hoặc unknown write bừa.
7. Dùng idempotency key và result lookup cho những write có side effect.
8. Truyền cancellation và cleanup, nhưng không coi cancel là rollback.
9. Dùng admission control/circuit breaker khi overload.
10. Đo request p99, attempt timeout, pool wait và retry amplification.
11. Thử lỗi mạng, commit-success-response-lost và orphan work.
12. Điều chỉnh chính sách theo evidence, không chỉ kéo dài timeout.
~~~

Điểm khó của hệ phân tán không nằm ở việc chọn một con số “timeout hợp lý” duy nhất. Nó nằm ở **biết mỗi giới hạn áp dụng cho pha nào, còn bao nhiêu thời gian thực sự, retry có tạo thêm tải hoặc side effect không, và điều gì phải xảy ra khi deadline hết mà kết quả commit chưa rõ**.

Khi những câu hỏi đó có câu trả lời cụ thể trong API contract, driver configuration, tracing và recovery workflow, hệ thống vừa có thể bảo vệ độ trễ người dùng vừa không làm sai dữ liệu nghiệp vụ.









