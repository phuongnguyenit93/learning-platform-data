# Thử lại có giới hạn, tăng khoảng chờ (backoff) và thêm độ lệch ngẫu nhiên (jitter)

Một ứng dụng Java ghi đơn hàng vào cụm NoSQL gồm nhiều bản sao. Bình thường request mất 20 ms. Trong lúc bầu lại leader, một số write bị timeout, nên cả nghìn client cùng thử lại ngay. Những request mới và request được thử lại cùng dồn vào cluster đang hồi phục, gây quá tải connection pool, CPU và log replication. Hệ vừa có leader mới lại không kịp xử lý backlog; client càng timeout, càng retry nhanh, tạo thành **vòng xoáy retry storm**.

Có hai bài toán cần giải quyết đồng thời:

1. **Thử lại để vượt qua lỗi tạm thời** — ví dụ một lần nghẽn mạng ngắn, leader đang chuyển hoặc một phản hồi throttling.
2. **Không làm tình hình xấu hơn hoặc tạo sai dữ liệu** — retry phải bị giới hạn về số lần, thời gian, lượng tải và đặc biệt phải tôn trọng **idempotency** khi không biết request trước đã commit hay chưa.

Vì thế, retry trong NoSQL không thể chỉ là một vòng lặp **catch exception → sleep → gửi lại**. Một chính sách tốt cần quyết định: **lỗi nào được retry, thao tác nào an toàn, khi nào hết hạn, mỗi lần chờ bao lâu, độ ngẫu nhiên được thêm thế nào, và khi nào cần dừng để hệ phục hồi**.

Bài học thuộc **Database No SQL → Lỗi phân tán và retry** giải thích **bounded retries**, **exponential backoff**, **jitter**, retry budgets, timeout/deadline, idempotency và trạng thái kết quả ghi chưa xác định; đi từ thuật toán, phép tính tới mã Java 21, trường hợp NoSQL cụ thể, observability, thử nghiệm lỗi và runbook vận hành.

> **Nguyên tắc cốt lõi:** **Retry là một công cụ phục hồi xác suất dưới điều kiện lỗi tạm thời, không phải cơ chế bảo đảm thành công.** Khi mạng bị phân vùng hoặc thiếu quorum kéo dài, retry không tạo thêm voter, không làm một key hết tranh chấp và không đảo ngược một lệnh đã được commit nhưng mất ACK.

> **Phạm vi:** Mọi tham số độ trễ, timeout, capacity và ví dụ sản phẩm trong bài là minh họa. Những retry defaults, error codes và bảo đảm idempotency thực tế phụ thuộc phiên bản database, driver, SDK và hợp đồng API. Không lấy mã mẫu làm cấu hình production nếu chưa khớp với thao tác cụ thể.

## 1. Vì sao NoSQL phân tán cần retry?

Một request có thể trải qua:

~~~~text
Java service
   |
   | 1. DNS / connect / TLS
   v
NoSQL coordinator / router
   |
   | 2. Routing key đến shard
   v
Leader / replica
   |
   | 3. Quorum, WAL, transaction/conditional guard
   v
Commit hoặc read result
   |
   | 4. Response quay về client
   v
Java service
~~~~

Các điểm thất bại rất khác nhau:

- Trước khi request tới server: lỗi connect, đường mạng không hoạt động.
- Trong lúc tìm leader: redirect, stale topology, election.
- Khi đã tới server: throttling, quá tải, timeout chờ quorum.
- Sau khi write commit: ACK mất giữa server và client.
- Khi đọc replica: replica lag, read mode không đáp ứng.
- Khi nhiều shard tham gia: một shard unavailable làm toàn transaction không thể hoàn tất.
- Khi client bị cancel: caller đã hết deadline nhưng SDK vẫn muốn retry.

Một lần thử lại có thể thành công nếu:
- Leader đã được bầu xong.
- Router cập nhật topology.
- Một connection mới được thiết lập.
- Server vừa có lại capacity.
- Phân vùng mạng đã lành.
- Một xung đột optimistic locking được đọc lại và xử lý đúng.

Nhưng thử lại cũng có thể:
- Tăng request rate đúng lúc server quá tải.
- Kéo dài tail latency.
- Gây duplicate increment, order, charge.
- Làm cache/log/index nóng thêm.
- Bỏ qua hạn chót của request upstream.
- Che giấu lỗi cấu hình, quyền truy cập hoặc schema.

**Retry phải là quyết định theo ngữ cảnh**, không phải một công tắc toàn cục áp cho mọi exception.

## 2. Phân loại lỗi trước khi quyết định thử lại

Một cách thực tế là phân biệt **tạm thời**, **vĩnh viễn/không phù hợp**, và **kết quả chưa biết**.

| Loại tình huống | Ví dụ | Hướng xử lý thông thường |
| --- | --- | --- |
| Lỗi kết nối trước khi gửi | Không kết nối được endpoint | Có thể retry theo budget và circuit breaker |
| Throttle/rate limit | HTTP 429 hoặc mã tương ứng của SDK | Tôn trọng giới hạn, Retry-After, backoff+jitter |
| Service unavailable tạm thời | 503, failover, overload | Retry có giới hạn nếu thao tác an toàn |
| Lỗi network sau khi gửi write | Đã gửi payload nhưng timeout/mất ACK | **UNKNOWN**; retry chỉ dưới idempotency contract |
| Quorum không đạt | Majority không reachable | Không retry nhanh; backoff/circuit và deadline |
| Conditional update thất bại | Version đã đổi, stock không đủ | Thường là business conflict; không retry y hệt vô hạn |
| Validation/schema sai | Thiếu field, type sai, payload quá lớn | Sửa request, không retry |
| Authentication/authorization | Token sai, không có quyền | Không retry cùng credential; xử lý auth theo policy |
| Not found có tính terminal | Resource không tồn tại theo source contract | Thường không retry nếu kết quả xác định |
| Read replica chưa bắt kịp | Session yêu cầu version mới | Chờ/route đúng mode hoặc retry có giới hạn |
| Query quota exceeded | Scan quá lớn hoặc vượt tài nguyên | Đổi query/page/giới hạn; không chỉ tăng attempts |
| Disk full/cluster bị sự cố dài | Thiếu capacity vật lý | Circuit breaker, fail rõ, vận hành khôi phục |
| Client bị hủy | Caller cancel, thread interrupt | **Dừng**, không tiếp tục tự retry nền |

### 2.1. Không phải lỗi 5xx nào cũng an toàn để retry

Lấy ví dụ một HTTP gateway báo **504 Gateway Timeout** sau khi gửi yêu cầu tạo order:
- Order service có thể chưa nhận request.
- Order service có thể đã gọi database.
- Database có thể đã committed.
- Response có thể bị chặn ở network.

Nếu POST tạo order **không idempotent**, retry có nguy cơ tạo order thứ hai. HTTP 504 cho biết upstream không nhận phản hồi đúng hạn, **không chứng minh thao tác gốc đã rollback**.

### 2.2. Phân biệt lỗi đã biết với kết quả chưa xác định

Một số trường hợp server trả rõ:
- **REJECTED:** điều kiện nghiệp vụ không đạt và thao tác không được commit.
- **COMMITTED:** thao tác đã được xác nhận theo hợp đồng.
- **UNKNOWN:** client không quan sát được kết quả cuối cùng.

Không nên biến mọi timeout thành REJECTED chỉ để tránh trạng thái thứ ba. **UNKNOWN** là trạng thái thực tế phải được mô hình hóa trong hệ phân tán.

### 2.3. Retry predicate phải đủ hẹp

Một ví dụ sai:

~~~~java
try {
    repository.write(order);
} catch (Exception e) {
    retryImmediately();
}
~~~~

Nó retry cả:
- Duplicate-key conflict.
- Invalid arguments.
- Permission denied.
- Programming bugs.
- Thread interruption.
- Lỗi network với side effect không idempotent.

Thay vào đó, phân loại cụ thể từ **error semantics của driver** và **hợp đồng của thao tác**. Một exception mang nhãn retriable từ SDK không tự miễn trách nhiệm thiết kế operationId cho side effect nghiệp vụ.

## 3. Ba điều kiện để retry hữu ích

Trước một retry, trả lời đủ ba câu:

1. **Lỗi có khả năng hồi phục trong budget không?** Ví dụ leader election ngắn, throttle tạm thời.
2. **Thao tác có an toàn khi thực thi lại không?** Ví dụ một read không side effect, hoặc write được bảo vệ bằng idempotency/transaction identity.
3. **Còn tài nguyên và thời gian cho lần thử lại không?** Ví dụ request còn 500 ms deadline và chưa tiêu hết retry tokens.

Nếu một trong ba điều kiện không đạt, hành vi đúng thường là **dừng**, trả lỗi phù hợp hoặc giữ UNKNOWN để đối soát.

### 3.1. Flow quyết định tổng quát

~~~~mermaid
flowchart TD
    A["Request failed / outcome unknown"] --> B{"Caller cancelled?"}
    B -->|Yes| STOP["Stop and propagate cancellation"]
    B -->|No| C{"Operation safe to replay?"}
    C -->|No| REC["Reconcile / return UNKNOWN"]
    C -->|Yes| D{"Failure transient and retryable?"}
    D -->|No| FAIL["Return definitive result/error"]
    D -->|Yes| E{"Attempts, deadline and retry budget left?"}
    E -->|No| EXIT["Stop: budget exhausted"]
    E -->|Yes| F["Honor server retry hint / capped backoff + jitter"]
    F --> G{"Enough time remains?"}
    G -->|No| EXIT
    G -->|Yes| H["Retry same logical operationId"]
    H --> A
~~~~

Sơ đồ là logic ứng dụng; không hàm ý server luôn biết chắc “request chưa được chạy” chỉ dựa trên timeout.

## 4. Retry có giới hạn là gì?

**Bounded retry** đặt những giới hạn hữu hạn cho quá trình thử lại, điển hình:

- **Max attempts:** tổng số lần thử, bao gồm lần đầu.
- **Max elapsed time:** thời gian tối đa cho toàn bộ chuỗi attempt + sleep.
- **Per-attempt timeout:** giới hạn mỗi lần gọi backend.
- **End-to-end deadline:** hạn chót kế thừa từ caller.
- **Retry budget:** số retry được phép so với request gốc hoặc token capacity.
- **Max backoff delay:** trần thời gian chờ.
- **Max queued/in-flight retries:** số thao tác được trì hoãn/đang thử lại.
- **Server hint:** Retry-After hoặc throttling guidance khi hợp lệ.

Một cấu hình phải nêu rõ:

~~~~yaml
retryPolicy:
  maxAttemptsIncludingInitial: 4
  maxElapsedMillis: 3000
  perAttemptTimeoutMillis: 500
  baseDelayMillis: 100
  maxDelayMillis: 1000
  jitter: full
  retryableFailures:
    - transient_transport_error
    - throttled
    - temporary_unavailable
  idempotencyRequiredForWrites: true
~~~~

Đây là mô tả minh họa, **không phải cấu hình native** của một thư viện/NoSQL engine cụ thể.

### 4.1. Attempts khác retries

Nếu **maxAttempts=4**:
- Attempt 1: lần đầu.
- Retry 1: attempt 2.
- Retry 2: attempt 3.
- Retry 3: attempt 4.

Tổng cộng tối đa **4 lần gọi**, không phải 1+4=5.

Nếu một thư viện cấu hình **maxRetries=3**, phải kiểm tra nó đếm **3 retries sau lần đầu** hay có semantics khác. Lỗi đếm lệch có thể nhân số request toàn hệ.

### 4.2. Deadline quan trọng hơn số lần

Cho maxAttempts=10 nhưng caller còn 200 ms:
- Nếu mỗi attempt có thể timeout 1 giây, cấu hình không nhất quán.
- Nếu một attempt đầu đã chiếm 180 ms, không nên đợi backoff 500 ms.
- Có thể dừng sớm với trạng thái/exception rõ.

**Số attempts là một trần; deadline là một trần độc lập. Phải áp cả hai.**

### 4.3. Giới hạn không bảo đảm luôn dùng hết attempts

Khi:
- Không còn budget.
- Caller cancel.
- Có lỗi không retryable.
- Server yêu cầu chờ dài hơn deadline.
- Circuit breaker mở.
- Không đủ concurrency permits.

thì chuỗi retry có thể kết thúc **trước maxAttempts**. Đây là hành vi mong muốn.

## 5. Timeout của một attempt và timeout toàn chuỗi

Một request có nhiều tầng:

~~~~text
API Gateway deadline:           4.0 s
Order Service budget:           3.5 s
DB operation total budget:      2.0 s
Per-attempt DB timeout:         0.5 s
Retries and backoff:            within remaining total budget
~~~~

Nếu database client tự retry 5 lần, mỗi lần 1 giây, **tổng DB time** có thể vượt deadline của gateway. Khi đó:
- Gateway đã trả timeout.
- Service vẫn tiêu tài nguyên.
- Database có thể commit muộn.
- Client có thể gửi một logical operation khác.
- Retry storm tăng.

### 5.1. Phân bổ deadline theo chiều sâu

Nếu upstream đưa deadline T, downstream nên biết **thời gian còn lại**, không tự khởi tạo lại timeout đầy đủ ở mỗi tầng.

Công thức khái niệm:

\[
B_{\text{remaining}}=
T_{\text{deadline}}-T_{\text{now}}
\]

Một attempt timeout có thể chọn:

\[
T_{\text{attempt}}=
\min(T_{\text{configured}},B_{\text{remaining}}-\text{reserve})
\]

Trong đó **reserve** có thể để dành cho serialize response, commit verification hoặc cleanup. Không đặt reserve âm và không bắt đầu attempt nếu không còn thời gian hợp lệ.

### 5.2. Đồng hồ monotonic cho elapsed time

Trong Java, dùng **System.nanoTime()** để đo khoảng thời gian:
- Không bị thay đổi giờ hệ thống/NTP giống wall clock.
- Phù hợp tính elapsed deadline trong cùng process.
- Không được dùng làm timestamp chia sẻ giữa các máy.

HTTP Date/Retry-After dạng ngày lại liên quan wall clock và clock skew; cần xử lý riêng.

### 5.3. Không tính riêng sleep rồi quên thời gian attempt

Một cấu hình:
- 4 attempts.
- Mỗi attempt tối đa 500 ms.
- Backoff không jitter lần lượt 100, 200, 400 ms.

Thời gian xấu nhất lý tưởng:

\[
T_{\max}=4(500)+(100+200+400)=2.700\text{ ms}
\]

Cộng serialization, scheduler overhead, connection acquisition hoặc các tầng khác có thể vượt 3.000 ms. Vì vậy phải **kiểm tra elapsed time sau mỗi attempt**, không chỉ ước lượng một lần.

### 5.4. Client timeout không nhất thiết hủy server work

Khi client timeout:
- Socket có thể đóng.
- Server có thể đã commit.
- Server có thể đang chờ quorum và hoàn tất sau đó.
- Request cancel có thể chỉ là best-effort.

**Không tự suy từ timeout rằng lệnh không thể commit trong tương lai**, đặc biệt khi retry non-idempotent operations.

## 6. Exponential backoff: tăng khoảng chờ sau mỗi lần thất bại

**Backoff** chủ động trì hoãn retry để:
- Cho hệ thống thời gian hồi phục.
- Giảm tần suất đánh vào một backend đang lỗi.
- Tránh nhiều request cùng tranh connection/CPU ngay khi leader bầu lại.
- Giảm nguy cơ tạo một luồng retry vô hạn.

Với thời gian chờ gốc \(d_0\), lần thất bại thứ k (k bắt đầu từ 1) có thể dùng:

\[
d_k=\min(d_{\max},d_0\cdot2^{k-1})
\]

Ví dụ \(d_0=100\) ms, \(d_{\max}=1.600\) ms:

| Sau lần thất bại | Backoff không jitter |
| ---: | ---: |
| 1 | 100 ms |
| 2 | 200 ms |
| 3 | 400 ms |
| 4 | 800 ms |
| 5 | 1.600 ms |
| 6 | 1.600 ms |
| 7 | 1.600 ms |

**Capped exponential backoff** tránh thời gian chờ tăng tới giá trị quá lớn, nhưng nếu không giới hạn attempts/elapsed time, client vẫn có thể retry mãi ở mức trần.

### 6.1. Vì sao không tăng tuyến tính?

Linear backoff:

\[
d_k=d_0+k\Delta
\]

có thể phù hợp trong một số workload. Exponential backoff tăng nhanh hơn khi lỗi kéo dài, giúp giảm áp lực lên backend. Không có quy tắc mọi lỗi đều phải exponential; điều quan trọng là **độ hồi phục của lỗi và khả năng chịu tải**.

### 6.2. Không dùng dịch bit không giới hạn

Một cài đặt ngây thơ:

~~~~java
long delayMillis = baseMillis * (1L << retryIndex);
~~~~

có thể gặp:
- Overflow sau nhiều lần dịch.
- Delay âm hoặc trở về 0.
- Ngủ quá lâu ngoài deadline.
- Phụ thuộc retryIndex rất lớn từ thư viện.

Cần **saturating multiplication**, kiểm tra trần trước khi nhân và giới hạn số attempt.

### 6.3. Một base delay không phù hợp mọi hệ

- Local Redis cache trong cùng zone có thể có RTT thấp.
- NoSQL cross-region quorum write có latency hàng chục/hàng trăm ms.
- Một leader election có thể kéo dài nhiều timeout periods.
- Một request bulk import được phép đợi lâu hơn interactive checkout.

Hãy chọn base delay dựa trên **RTT, recovery behavior, deadline, tải và server hints**, thay vì sao chép một hằng số 100 ms cho mọi operation.

## 7. Tại sao phải thêm jitter?

Nếu 10.000 client cùng nhận lỗi lúc T=0 và đều retry chính xác sau 100 ms:

~~~~text
Time    Attempts from affected clients
0 ms    10.000 original requests
100 ms  10.000 retries
300 ms  10.000 retries
700 ms  10.000 retries
...
~~~~

Exponential backoff **không có jitter** vẫn làm các client đồng bộ thành những **sóng request** tại cùng thời điểm, nhất là khi ban đầu chúng cùng thất bại do một sự cố chung.

**Jitter** thêm ngẫu nhiên vào thời gian chờ để trải các retry trên một khoảng, giảm hiệu ứng *thundering herd*.

### 7.1. Full jitter

Cho exponential cap \(d_k\) ở lần thất bại k:

\[
wait_k \sim U(0,d_k)
\]

Tức chọn đều một thời gian giữa 0 và \(d_k\).

Ví dụ \(d_k=400\) ms:
- Client A chọn 18 ms.
- Client B chọn 277 ms.
- Client C chọn 392 ms.
- Client D chọn 144 ms.

Các client không còn cùng retry tại 400 ms.

**Kỳ vọng:**

\[
E[wait_k]=d_k/2
\]

Với d=400 ms, trung bình khoảng 200 ms theo phân bố lý tưởng. Đây là **thống kê của thuật toán**, không bảo đảm tất cả requests rải hoàn toàn đều dưới scheduling/network delays thực.

### 7.2. Equal jitter

Một biến thể:

\[
wait_k=\frac{d_k}{2}+U(0,\frac{d_k}{2})
\]

Với d=400 ms, wait nằm từ khoảng 200 tới 400 ms.

Kỳ vọng:

\[
E[wait_k]=\frac{3d_k}{4}
\]

Equal jitter tránh sleep quá nhỏ, nhưng các client vẫn dồn trong **nửa khoảng cuối** thay vì toàn bộ [0,d].

### 7.3. Decorrelated jitter

Một biến thể thường được mô tả:

\[
wait_k=\min(d_{\max},U(d_0,3\cdot wait_{k-1}))
\]

Nó dùng thời gian chờ trước đó để tạo bước tiếp theo, nên phân bố chuỗi đợi khác full/equal jitter. Cần:
- Kiểm tra tham số tối thiểu/tối đa.
- Cẩn thận tràn số khi nhân ba.
- Khởi tạo wait trước đó nhất quán.
- Cap rõ ràng.
- Benchmark behavior với workload cụ thể.

Không có một biến thể luôn thắng trong mọi phân bố lỗi, số client, latency SLO và cost. **Full jitter** là lựa chọn thường dễ triển khai và kiểm tra; equal/decorrelated có thể phù hợp khi muốn điều chỉnh phân bố.

### 7.4. Bảng so sánh

| Chiến lược | Công thức khái niệm | Ưu điểm | Hạn chế |
| --- | --- | --- | --- |
| Constant wait | \(d_k=d_0\) | Đơn giản | Có thể gây sóng đồng bộ; không giảm tải khi lỗi kéo dài |
| Exponential không jitter | \(\min(cap,base\cdot2^{k-1})\) | Giảm tần suất dần | Các client vẫn đồng bộ |
| Full jitter | \(U(0,d_k)\) | Trải trên toàn cửa sổ | Một số wait có thể rất nhỏ |
| Equal jitter | \(d_k/2+U(0,d_k/2)\) | Có mức đợi tối thiểu | Tập trung hơn full jitter |
| Decorrelated jitter | Phụ thuộc wait trước và khoảng ngẫu nhiên | Giảm nhịp đồng bộ, đa dạng hơn | Stateful và khó dự đoán hơn |
| Server Retry-After | Theo chỉ dẫn server, trong policy bounds | Có thông tin từ server | Có thể nhiều client cùng mốc; cần jitter/quota/deadline |

### 7.5. Jitter không thay thế retry budget

Ngay cả khi 10.000 client được rải đều trong một giây:
- Backend có thể chỉ chịu 1.000 request/s.
- Mọi client đều thử lại nhiều lần.
- Tổng offered load vẫn có thể cao gấp nhiều lần.

Jitter giải quyết **đồng bộ thời điểm**; retry limits/budgets giải quyết **tổng lượng tải được phép**.

## 8. Các ví dụ timeline với jitter

Giả sử mỗi attempt thất bại tức thời; base=100 ms, cap=800 ms, ba retries tối đa.

**Không jitter:**

~~~~text
Original:   T=0
Retry #1:   T=100 ms
Retry #2:   T=300 ms
Retry #3:   T=700 ms
~~~~

**Full jitter, một chuỗi lấy mẫu minh họa:**

~~~~text
Original:   T=0
Sleep #1:  63 ms  -> Retry #1 T=63
Sleep #2: 108 ms  -> Retry #2 T=171
Sleep #3: 367 ms  -> Retry #3 T=538
~~~~

Một client khác có thể chọn 9, 185, 41 ms; retry waves lệch nhau.

**Lưu ý:** T=... là thời điểm tương đối minh họa và chưa cộng thời gian thực thi attempt. Trong production cần tính **attempt latency** vào deadline.

### 8.1. Jitter phân tán nhịp retry chứ không đổi tính đúng của thao tác

Nếu một POST đã commit nhưng ACK mất, đợi 63 hay 367 ms **không làm POST trở thành idempotent**. Cần operationId/guard trước khi cho phép replay.

## 9. Retry-After và server-directed backoff

Server hoặc gateway có thể thông báo client nên chờ.

Ví dụ HTTP:

~~~~http
HTTP/1.1 429 Too Many Requests
Retry-After: 3
Content-Type: application/json

{"error":"temporarily_rate_limited"}
~~~~

Hoặc **Retry-After** có thể là thời điểm HTTP-date theo chuẩn giao thức.

### 9.1. Diễn giải đúng

Một policy hợp lý:
- Phân loại response là có thể retry.
- Lấy thời gian chờ hợp lệ từ server nếu có.
- Áp **deadline và maximum delay** của client.
- Có thể thêm jitter trong phạm vi không vi phạm hướng dẫn server.
- Nếu không đủ thời gian để chờ, dừng thay vì gửi quá sớm.
- Không dùng cùng một mốc retry tuyệt đối cho hàng triệu client nếu có thể phân tán thêm.

### 9.2. Tôn trọng server không nghĩa chờ vô hạn

Nếu caller còn 500 ms nhưng server nói Retry-After: 60 giây:
- Không cố chờ 60 giây trong request đó.
- Trả trạng thái throttled/tạm không khả dụng phù hợp.
- Có thể lên lịch **một công việc mới** nếu ứng dụng có queue/workflow và người dùng đã chấp nhận async semantics.
- Không tự tạo job nền sau khi HTTP caller cancel nếu hợp đồng không cho phép.

### 9.3. HTTP-date và clock skew

Nếu Retry-After biểu diễn giờ tuyệt đối:
- Client clock có thể lệch.
- Header có thể bị proxy chỉnh.
- Deadline nội bộ nên dùng đồng hồ monotonic cho elapsed duration.
- Cần validation, clamping và bỏ qua giá trị bất thường theo policy.

Không nối chuỗi header trực tiếp vào Thread.sleep mà không parse/kiểm tra.

## 10. Retry storm: vòng khuếch đại tải

Giả sử hệ nhận **60.000 request/s**, backend chịu ổn định **80.000 attempts/s**.

Trong sự cố, nếu mỗi original request có xu hướng thử tới **3 lần** và retries xảy ra trong cùng khoảng đo, offered traffic có thể tiến gần:

\[
60.000 \times 3=180.000\text{ attempts/s}
\]

Đây là **giới hạn xấu trong mô hình cùng lúc và ba attempts**, vượt xa công suất. Những request timeout lại khiến các client retry thêm, làm queue tăng.

### 10.1. Hệ số khuếch đại retry

Định nghĩa:

\[
A=\frac{\text{Total backend attempts}}{\text{Original logical requests}}
\]

Ví dụ có 10.000 logical requests, tạo ra 23.000 backend attempts:

\[
A=2{,}3
\]

Cùng lúc backend đang suy yếu, A tăng mạnh là tín hiệu nguy hiểm.

### 10.2. Kỳ vọng số attempts khi lỗi độc lập

Nếu xác suất mỗi attempt thất bại độc lập là p và tối đa m attempts:

\[
E[\text{attempts}]=\sum_{i=0}^{m-1}p^i
\]

Với p=0,2 và m=4:

\[
E=1+0{,}2+0{,}04+0{,}008=1{,}248
\]

Nhưng **giả định lỗi độc lập thường không đúng khi có outage chung**. Khi cả cluster mất quorum, p gần 1 cho mọi client; tất cả có thể dùng hết m attempts, đưa A tiến gần m.

Không dùng phép tính p độc lập để chứng minh retry an toàn trong một sự cố tương quan.

### 10.3. Retry load và recovery capacity

Một cụm vừa hồi phục thường phải:
- Bầu leader.
- Replay log.
- Sync replicas.
- Warm cache.
- Xử lý backlog.
- Chạy compaction/repair.

Năng lực phục vụ **ngay sau recovery** có thể thấp hơn steady-state. Nếu clients đồng loạt retry, cụm có thể lại quá tải và quay vòng election/timeout.

**Giảm offered load là một phần của recovery**, không chỉ tăng số replica.

## 11. Retry budget: một giới hạn trên toàn tập request

MaxAttempts giới hạn **mỗi request**, nhưng không giới hạn tổng retry traffic của nhiều client.

**Retry budget** đặt mức retries được phép tương đối với lưu lượng gốc hoặc capacity.

Ví dụ:
- Hệ nhận 10.000 original requests/s.
- Chính sách cho phép trung bình **tối đa 10% số request gốc** trở thành retry attempts trong một cửa sổ.
- Retry budget khoảng 1.000 attempts/s, tùy cách tính và token burst.

Khi budget hết:
- Không cấp thêm retry.
- Fail fast hoặc trả trạng thái phù hợp.
- Không chặn request mới vô hạn để “đợi có budget”.
- Giữ thông tin operationId/UNKNOWN để đối soát.

### 11.1. Token-based retry budget

Một cơ chế khái niệm:
- Mỗi original request thành công bổ sung một số retry token.
- Mỗi retry tiêu thụ token.
- Token bucket có capacity cố định để cho phép burst ngắn.
- Không refill vô hạn khi hệ đang thất bại hoàn toàn.
- Tính budget theo cell/shard/downstream nếu chúng có failure domains khác nhau.

Một global budget có thể khiến sự cố một shard **ăn hết retry tokens** của shard khác. Cần cân nhắc **blast-radius isolation**.

### 11.2. Per-tenant budgets

Tenant lớn tạo nhiều failures có thể gây noisy neighbor. Nếu mọi tenant chung một connection pool và retry budget:
- Một tenant có thể chiếm hết retry slots.
- Tenant nhỏ bị timeout dù shard riêng khỏe.

Có thể chia theo:
- Tenant tier.
- Cell/shard.
- Operation class.
- Interactive vs batch.
- Read vs write.
- Region hoặc provider.

Quotas phải hợp với công suất thực và hợp đồng SLA, không chỉ với doanh thu của tenant.

### 11.3. Budget cho retries, không cho lỗi vô hạn

Nếu backend báo overload:
- New requests có thể tiếp tục bị admission control giới hạn.
- Retry budget phải được cân bằng với **total admission capacity**.
- Chỉ hạn chế retries mà cho unlimited new traffic cũng có thể không đủ.

Một thiết kế đầy đủ kết hợp **retry budget + rate limiting + concurrency bulkheads + circuit breaker + load shedding**.

## 12. Retry ở nhiều tầng: nhân attempts theo cấp số nhân

Một lỗi phổ biến:

~~~~text
Mobile client:       3 attempts
API Gateway:         3 attempts
Order Service:       3 attempts
Database SDK:        3 attempts
~~~~

Trong trường hợp xấu, một ý định có thể kích hoạt tới:

\[
3\times3\times3\times3=81
\]

backend attempts nếu mỗi tầng lặp lại toàn bộ công việc của tầng dưới và mọi attempt đều dùng hết retry limit.

**81 là trần theo mô hình đơn giản**, không có nghĩa mọi request thực tế luôn tạo 81 calls; nhưng đủ cho thấy tính nguy hiểm khi mỗi tầng tự cho mình “chỉ retry hai lần”.

### 12.1. Chọn nơi sở hữu retry

Một kiến trúc có thể:
- DB SDK retry một số lỗi connection/topology **theo hợp đồng phù hợp**.
- Service sở hữu retry nghiệp vụ/idempotency/transaction outcome.
- Gateway chỉ retry những method được phép, với chính sách không tạo side effect trùng.
- Mobile gửi lại **cùng operationId** theo trạng thái trả về.
- Mọi tầng chia sẻ **end-to-end deadline**.

Không phải lúc nào cũng “chỉ một tầng retry”. Quan trọng là **phối hợp tổng budget và loại lỗi**, tránh retry lồng nhau không kiểm soát.

### 12.2. Một middleware retry mọi HTTP POST là nguy hiểm

Nếu gateway thấy 503/504 và phát lại POST /payments/capture mà không có idempotency:
- Provider có thể capture hai lần.
- Database có thể lưu hai transaction riêng.
- Người dùng có thể bị trừ tiền trùng.

Middleware không hiểu **business operation identity** thì không nên tự replay side effects chỉ dựa vào HTTP status.

## 13. Idempotency: điều kiện an toàn cho write retry

Một thao tác **idempotent** nếu thực hiện lại cùng logical operation không làm trạng thái/side effect vượt ngoài kết quả mong đợi của một lần.

Trực giác:
- **SET x=10** có thể idempotent khi cùng giá trị và những giả định phù hợp.
- **INCREMENT x by 1** không idempotent.
- **DELETE key K** có thể idempotent ở mức trạng thái cuối của key, nhưng event/audit và concurrent recreation có sắc thái riêng.
- **Create order with random new ID** không idempotent nếu mỗi retry tạo order mới.
- **Conditional reserve stock** không tự idempotent nếu điều kiện còn đúng ở retry thứ hai.

### 13.1. Tại sao conditional update chưa đủ?

Giả sử stock=10, mỗi lần đặt một đơn:

~~~~text
IF stock >= 1:
    stock = stock - 1
~~~~

Attempt 1 với OP-101:
- Condition true.
- Commit stock=9.
- ACK mất.

Attempt 2 cùng ý định nhưng không có idempotency guard:
- Condition vẫn true.
- Commit stock=8.

**Không âm tồn kho** vẫn được giữ, nhưng **một ý định đã trừ hai lần**.

### 13.2. Stable operationId

Một request nên có:

~~~~json
{
  "operationId": "OP-101",
  "tenantId": "T-42",
  "sku": "BOOK-42",
  "quantity": 1,
  "requestFingerprint": "sha256:canonical-request"
}
~~~~

Ý nghĩa:
- **operationId** cố định cho cùng ý định nghiệp vụ.
- Nếu HTTP retry sau timeout, không sinh OP-102.
- **requestFingerprint** phát hiện cùng key nhưng body bị thay đổi.
- Ledger lưu kết quả terminal để retry trả cùng outcome.
- Unique/conditional guard phải được enforce **atomically** ở authority.

### 13.3. Ledger và side effect phải nằm trong một ranh giới an toàn

Một thiết kế lý tưởng nếu engine hỗ trợ transaction:

~~~~text
BEGIN TRANSACTION
  existing = OperationLedger[operationId]

  IF existing exists:
      REQUIRE existing.requestFingerprint == fingerprint
      RETURN existing.priorResult

  REQUIRE stock >= quantity
  stock := stock - quantity
  reservation := create(newReservationId)
  INSERT OperationLedger[operationId] =
      {fingerprint, status=COMMITTED, reservationId}
  INSERT OutboxEvent[uniqueEventId]
COMMIT
~~~~

Nếu không có multi-record transaction phù hợp:
- Có thể mô hình hóa **một aggregate atomic item/document**.
- Dùng state machine/claim-reserve-confirm workflow có idempotency và reconciliation.
- Hoặc thiết kế authority chuyên biệt chịu trách nhiệm invariant.
- Không chỉ ghi ledger **sau** decrement bằng một lệnh rời rạc rồi tin là an toàn.

### 13.4. Idempotency có phạm vi và thời hạn

Cần xác định:
- Scope của key: theo tenant, API, merchant, account hay toàn hệ?
- TTL/retention của ledger.
- Bao lâu client/provider có thể retry?
- Sau khi ledger hết hạn, duplicate cũ có thể xuất hiện không?
- Same ID + different payload phải báo conflict.
- OperationId được tạo ở client hay server và lưu ở đâu?
- Region/migration có giữ ledger đủ bền không?
- Độ duy nhất của ID và chính sách chống lạm dụng?

**Idempotency key có TTL 24 giờ không tự bảo vệ retry sau 7 ngày** nếu nghiệp vụ có thể gửi lại cùng ý định lúc đó. Cần quy định lifecycle thích hợp.

## 14. Trạng thái UNKNOWN: phần không thể né trong hệ phân tán

Ví dụ timeline:

~~~~mermaid
sequenceDiagram
    participant C as Client
    participant S as Service
    participant DB as NoSQL authority
    C->>S: POST reserve OP-101
    S->>DB: Conditional transaction OP-101
    DB->>DB: Quorum commit
    DB--xS: ACK lost
    Note over S: Outcome unknown
    S-->>C: UNKNOWN / PENDING VERIFICATION
~~~~

Nếu service timeout, có thể:
- Chưa có commit.
- Commit đã xảy ra.
- Commit sẽ xảy ra sau timeout.
- Transaction đã được quyết định nhưng caller chưa nhận kết quả.

### 14.1. Không làm gì sai khi UNKNOWN

Không:
- Gửi lại với operationId mới.
- Tạo payment charge mới không dùng provider idempotency.
- Trả **REJECTED** chắc chắn chỉ dựa trên socket timeout.
- Đọc từ search index eventual không thấy record rồi coi như chưa xảy ra.
- Dùng một GET tại t1 không thấy để kết luận in-flight request chắc chắn không commit tại t2.

Nên:
- Giữ cùng operationId.
- Tra authoritative operation ledger theo consistency phù hợp.
- Retry **cùng logical operation** dưới guard idempotent khi policy cho phép.
- Trả UNKNOWN/PENDING và cung cấp đường xem trạng thái.
- Đối soát những operation quá tuổi.

### 14.2. Retry cùng ID có thể an toàn, nhưng phải chứng minh bằng thiết kế

Một API:

~~~~http
POST /reservations
Idempotency-Key: OP-101
Content-Type: application/json

{"sku":"BOOK-42","quantity":1}
~~~~

Chỉ thêm header **Idempotency-Key** vào request không đủ. Server phải:
- Lưu và kiểm tra key **atomically**.
- Bảo vệ cùng key concurrent requests.
- Trả cùng prior result hoặc một trạng thái xử lý nhất quán.
- Không tái áp dụng side effects.
- Có kết quả bền vững sau failover/reshard.
- Ngăn key reuse với payload khác.

## 15. Bảo vệ an toàn khi retry increment, append và delete

### 15.1. Counter increment

~~~~text
INCR views:post-42
~~~~

Nếu ACK mất, retry có thể increment hai lần. Với **view counter** đôi khi chấp nhận approximation; với **balance/stock** thường không.

Đề xuất:
- Với thống kê xấp xỉ: công bố semantics và sai số cho phép.
- Với business counter: dùng eventId/operation ledger/transaction.
- Với high throughput: sharded counter + dedup/merge nếu contract cho phép.
- Không suy “INCR atomic” nghĩa exactly-once end-to-end.

### 15.2. Append event

~~~~json
{
  "eventId": "EV-901",
  "operationId": "OP-101",
  "type": "OrderCreated"
}
~~~~

Append vào log có thể nhận event trùng khi producer retry. Consumer cần:
- Idempotent apply theo eventId/version.
- Ordering per key khi cần.
- Xử lý replay/backfill.
- Không dùng timestamp client đơn thuần làm unique ID.

### 15.3. DELETE và tombstone

DELETE cùng key lặp lại có vẻ idempotent về trạng thái “không tồn tại”. Nhưng nếu:
1. Client gửi DELETE K, ACK mất.
2. Một writer khác tạo lại K với version mới.
3. Client retry DELETE K không có version guard.

thì retry có thể xóa **bản mới**. Để bảo vệ concurrency semantics, cần điều kiện version/CAS/tombstone generation phù hợp.

### 15.4. Read không side effect cũng có thể nguy hiểm vì tải

GET/search query thường an toàn về dữ liệu khi replay, nhưng:
- Có thể quét nhiều shard.
- Dùng nhiều CPU/IO.
- Trả dữ liệu stale ở retry qua replica khác.
- Kích hoạt cache fills hoặc refresh jobs.
- Bị retry storm nếu backend quá tải.

**Read retry không cần business idempotency như write, nhưng vẫn cần budget, deadline và consistency contract.**

## 16. Phân biệt optimistic concurrency conflict với lỗi tạm thời

Một conditional update theo version:

~~~~text
UPDATE Document
SET balance = ...
IF version == 17
~~~~

Nếu condition failed, nghĩa là **version đã khác** hoặc precondition không đạt.

Không đúng nếu cứ retry y hệt với version=17 vô hạn.

Một chiến lược optimistic concurrency hợp lý:
1. Đọc lại trạng thái **theo consistency phù hợp**.
2. Tính toán lại business intent trên version mới.
3. Kiểm tra invariant.
4. Thử conditional write với version mới.
5. Dừng sau số xung đột/budget giới hạn.

### 16.1. Không phải conflict nào cũng nên retry

- **Stock hết:** trả OUT_OF_STOCK, không retry ngay chỉ để mong khách khác trả hàng.
- **Unique email trùng:** trả conflict, không retry cùng payload.
- **Version mismatch vì concurrent update:** có thể retry sau reread nếu business semantics cho phép.
- **Lease/ownership lost:** cần xác định owner mới, không cố retry với stale fencing token.
- **Transaction serialization conflict:** có thể retry toàn transaction nếu driver/API cho phép và không có side effect ngoài transaction.

### 16.2. Reread phải đúng nguồn

Nếu version mới đã commit nhưng query đọc từ replica stale trả version cũ, retry loop có thể tiếp tục bắn condition version=17 và thất bại.

Cần:
- Strong/authoritative read khi quyết định business update.
- Hoặc session/causal context đủ mới theo contract.
- Không tự cache version quá hạn qua nhiều attempts.

## 17. Retry khi partition hoặc thiếu quorum

Một mạng phân vùng:

~~~~text
Majority group A,B,C       X       Minority D,E
     3/5 voters                        2/5
~~~~

Nếu write yêu cầu majority:
- Phía A,B,C có thể commit khi leader/protocol ổn định.
- Phía D,E **không thể commit** theo quorum này.
- Retry liên tục ở D/E không tạo thêm voter.
- Nếu client có thể route tới majority qua đường khác, redirect/retry có thể hữu ích.
- Nếu không có network path, cần fail/degrade theo contract.

### 17.1. No-quorum khác transient 503 ngắn

Một 503 do leader election 100–500 ms có thể hồi phục nhanh.

Một 503 vì mất region và chỉ còn minority có thể kéo dài hàng giờ. Dùng cùng retry policy cho hai tình huống:
- Làm cạn connection pools.
- Đốt hết budget.
- Tăng backlog lúc repair.
- Tạo thêm unknown operations.

Nên dùng failure classification/circuit breaker và observability per shard/region.

### 17.2. Quorum có trở lại chưa?

Không chỉ ping endpoint. Cần kiểm tra:
- Leader/term ổn định.
- Voting majority reachable.
- Commit index tiến triển.
- WAL/replica apply không bị kẹt.
- Request p99 dưới giới hạn.
- Tỷ lệ throttling/timeout giảm.

**Liveness của consensus group** không tự đồng nghĩa đã có capacity để nhận toàn bộ retry burst.

### 17.3. Fail closed cho thao tác nhạy cảm

Nếu business invariant là:
- Không bán quá stock.
- Không double-charge.
- Không cấp hai booking cùng slot.
- Thu hồi quyền truy cập có hiệu lực theo contract.

thì khi authority unavailable:
- Không trả CONFIRMED dựa vào eventual cache.
- Có thể trả TEMPORARILY_UNAVAILABLE, PENDING hoặc UNKNOWN tùy đã nhận request tới đâu.
- Có thể nhận intent cục bộ với **hợp đồng khác**, nhưng không mạo nhận đã commit toàn cục.

## 18. Retry khi leader election và stale topology

Trong single-leader/consensus-backed systems, lỗi thường gặp:
- Request gửi leader cũ.
- Node trả not-leader/redirect.
- Election đang diễn ra.
- Router chưa cập nhật leader map.
- Candidate chưa ổn định.
- Commit timeout trong lúc chuyển term.

Một chiến lược tốt:
- Cho driver/topology discovery xử lý những redirect nó hiểu.
- Không tự duy trì cache leader vô hạn ở application.
- Retry có hạn khi gặp transient not-leader.
- Giới hạn tổng attempts/deadline **kể cả SDK tự retry**.
- Không gửi một write không idempotent sang nhiều leader “race” đồng thời để lấy response nhanh.
- Ghi term/leader switch nếu driver cho phép để debug.

### 18.1. Hedged requests khác retry tuần tự

**Hedging** gửi thêm một bản request trước khi request đầu chắc chắn thất bại để giảm tail latency.

Với read eventual, một số hệ có thể dùng hedged reads dưới policy phù hợp. Với write có side effect:
- Hai request có thể cùng commit/đụng guard.
- Cần idempotency mạnh hoặc không hedging.
- Tăng offered load ngay cả khi không có lỗi.
- Có thể làm hot shard nặng hơn.

**Hedging không nên được bật chung cho mọi NoSQL operation**.

### 18.2. Failover và retry ẩn ở SDK

Một driver có thể tự retry connection hoặc một tập writes nhất định theo semantics của nó. Application cần biết:
- MaxAttempts effective.
- Timeout effective.
- Operations nào driver coi là retryable.
- Transaction commit retry thuộc ai.
- Idempotency ở cấp DB request có bảo vệ **business workflow** không.

Không lồng thêm một vòng 10 attempts bên ngoài SDK 10 attempts mà không tính amplification.

## 19. Throttling và backpressure

Throttling là tín hiệu rằng server chưa có đủ capacity hoặc policy không cho nhận thêm tải.

Ví dụ:
- HTTP 429 Too Many Requests.
- Lỗi exceeded provisioned throughput của managed database.
- Coordinator từ chối vì queue đầy.
- Per-tenant quota.
- TooManyRequestsException hoặc tương đương.

Một retry đúng có thể:
- Giảm tốc.
- Tôn trọng hướng dẫn server.
- Phân tán chờ bằng jitter.
- Dừng khi quá deadline.
- Thay đổi concurrency hoặc batch size.
- Chờ budget được cấp lại.

### 19.1. Cần giảm concurrency, không chỉ tăng sleep

Nếu 1.000 worker cùng gặp throttle:
- Tăng sleep mỗi worker giúp giảm tần suất, nhưng vẫn có 1.000 concurrent logical operations giữ state/threads.
- Có thể cần semaphore/bulkhead giảm **in-flight requests**.
- Với batch import, có thể giảm producer rate hoặc dynamic concurrency.

### 19.2. Retry-After không phải bypass quota

Nếu tenant đã vượt quota 10.000 writes/s:
- Chờ 100 ms rồi gửi lại 100.000 writes cùng lúc không giúp.
- Cần cơ chế queue/drain theo rate.
- HTTP caller interactive có thể fail fast.
- Background import có thể persist job state và xử lý chậm lại theo budget.

### 19.3. AIMD và adaptive concurrency

Một chiến lược nâng cao:
- **Additive increase** capacity/concurrency khi tình trạng tốt.
- **Multiplicative decrease** khi latency/overload tăng.

Hoặc dùng adaptive limiter dựa trên queue time/p99. Cần cẩn thận với feedback delay, workload thay đổi và fairness giữa tenants.

Backoff+jitter là lớp **giảm tần suất retry**, không thay được mô hình control load toàn hệ.

## 20. Circuit breaker, bulkhead và load shedding

**Circuit breaker** ngừng gửi thử request tới dependency đang thất bại theo ngưỡng/health policy.

Các trạng thái khái niệm:
- **CLOSED:** cho request đi qua và đo lỗi.
- **OPEN:** từ chối nhanh thay vì tiếp tục tải lỗi.
- **HALF_OPEN:** chỉ cho số ít probe/requests để đánh giá phục hồi.

### 20.1. Vì sao circuit breaker bổ sung retry?

Không có circuit:
- Mỗi client vẫn dùng hết retry budget.
- Backend outage kéo dài bị gọi liên tục.
- Connection pools bị chiếm.

Có circuit:
- Một phần traffic fail fast.
- Có probe giới hạn để phát hiện hồi phục.
- Retry không bị lặp vô ích.

### 20.2. Breaker phải theo failure domain

Một global breaker cho toàn database có thể chặn tất cả tenants nếu chỉ một shard hỏng.

Nên cân nhắc breaker theo:
- Shard/partition hoặc cell.
- Region/endpoint.
- Operation class.
- Backend dependency.

Nhưng không tạo hàng triệu breaker objects cho từng random key mà không có giới hạn memory/cardinality.

### 20.3. Bulkhead

Per-tenant/per-workload concurrency cap:
- BIG import không chiếm hết interactive connections.
- Report queries không lấp đầy checkout pool.
- Retry worker dùng queue và slot budget riêng.

### 20.4. Load shedding

Khi hệ quá tải:
- Từ chối sớm request ít ưu tiên.
- Bảo vệ hoạt động nhạy cảm với độ trễ.
- Trả **429/503** với semantics rõ.
- Không tự xác nhận success cho write chưa commit.

Load shedding làm giảm một phần availability ngắn hạn nhưng có thể cải thiện **khả năng phục hồi và SLO tổng**.

## 21. Java 21: triển khai bounded retry với full jitter

Dưới đây là ví dụ **Java SE** tập trung vào một lớp retry đồng bộ. Mục tiêu:
- Giới hạn **số attempt**.
- Giới hạn **elapsed time** bằng đồng hồ monotonic.
- Áp **full jitter** với capped exponential backoff.
- Không che mất **InterruptedException**.
- Để caller quyết định **exception nào retry được**.
- Truyền remaining deadline vào mỗi attempt.
- **Không tự replay side effect nếu caller chưa có idempotency**.

~~~~java
import java.time.Duration;
import java.util.Objects;
import java.util.concurrent.ThreadLocalRandom;
import java.util.concurrent.TimeUnit;

public final class BoundedRetry {
    private BoundedRetry() {}

    public record Policy(
            int maxAttempts,
            Duration maxElapsed,
            Duration perAttemptTimeout,
            Duration baseDelay,
            Duration maxDelay
    ) {
        public Policy {
            if (maxAttempts < 1) {
                throw new IllegalArgumentException("maxAttempts < 1");
            }
            Objects.requireNonNull(maxElapsed);
            Objects.requireNonNull(perAttemptTimeout);
            Objects.requireNonNull(baseDelay);
            Objects.requireNonNull(maxDelay);

            if (maxElapsed.isNegative() || maxElapsed.isZero()
                    || perAttemptTimeout.isNegative()
                    || perAttemptTimeout.isZero()
                    || baseDelay.isNegative() || baseDelay.isZero()
                    || maxDelay.compareTo(baseDelay) < 0) {
                throw new IllegalArgumentException("invalid retry timing");
            }

            // Giữ chuyển đổi Duration -> nanos trong phạm vi long.
            if (maxElapsed.compareTo(Duration.ofDays(1)) > 0
                    || perAttemptTimeout.compareTo(Duration.ofHours(1)) > 0
                    || maxDelay.compareTo(Duration.ofMinutes(5)) > 0) {
                throw new IllegalArgumentException("policy out of bounds");
            }
        }
    }

    @FunctionalInterface
    public interface Attempt<T> {
        T execute(Duration perAttemptBudget) throws Exception;
    }

    @FunctionalInterface
    public interface Retryable {
        boolean test(Exception failure);
    }

    public static <T> T run(
            Policy policy,
            Attempt<T> attempt,
            Retryable retryable
    ) throws Exception {
        Objects.requireNonNull(policy);
        Objects.requireNonNull(attempt);
        Objects.requireNonNull(retryable);

        final long started = System.nanoTime();
        final long limitNanos = policy.maxElapsed().toNanos();

        for (int number = 1; number <= policy.maxAttempts(); number++) {
            long elapsed = System.nanoTime() - started;
            long remaining = limitNanos - elapsed;

            if (remaining <= 0) {
                throw new RetryDeadlineExceededException(
                        "total retry deadline exhausted");
            }

            Duration budget = Duration.ofNanos(
                    Math.min(remaining, policy.perAttemptTimeout().toNanos())
            );

            try {
                // Caller PHẢI đảm bảo underlying I/O tôn trọng budget.
                return attempt.execute(budget);
            } catch (InterruptedException interrupted) {
                Thread.currentThread().interrupt();
                throw interrupted;
            } catch (Exception failure) {
                // Không tự retry mọi exception hay business failure.
                if (!retryable.test(failure)
                        || number == policy.maxAttempts()) {
                    throw failure;
                }

                long elapsedAfter = System.nanoTime() - started;
                long leftAfter = limitNanos - elapsedAfter;
                if (leftAfter <= 0) {
                    throw new RetryDeadlineExceededException(
                            "retry deadline exhausted", failure);
                }

                long capNanos = cappedExponentialNanos(
                        policy.baseDelay().toNanos(),
                        policy.maxDelay().toNanos(),
                        number
                );

                // Full jitter: wait thuộc [0, capNanos].
                long waitNanos =
                        ThreadLocalRandom.current().nextLong(capNanos + 1L);

                // Không khởi động attempt kế tiếp sau deadline.
                if (waitNanos >= leftAfter) {
                    throw new RetryDeadlineExceededException(
                            "insufficient time for next retry", failure);
                }

                // Sleep có thể bị interrupt; propagation là bắt buộc.
                TimeUnit.NANOSECONDS.sleep(waitNanos);
            }
        }
        throw new IllegalStateException("unreachable");
    }

    private static long cappedExponentialNanos(
            long base,
            long cap,
            int failedAttemptNumber
    ) {
        long delay = base;
        for (int i = 1; i < failedAttemptNumber; i++) {
            delay = delay >= cap / 2L
                    ? cap
                    : Math.min(cap, delay * 2L);
        }
        return delay;
    }

    public static final class RetryDeadlineExceededException
            extends Exception {
        public RetryDeadlineExceededException(String message) {
            super(message);
        }

        public RetryDeadlineExceededException(
                String message, Throwable cause
        ) {
            super(message, cause);
        }
    }
}
~~~~

### 21.1. Cấu hình và gọi

~~~~java
BoundedRetry.Policy policy = new BoundedRetry.Policy(
        4,
        Duration.ofSeconds(3),
        Duration.ofMillis(500),
        Duration.ofMillis(100),
        Duration.ofSeconds(1)
);

String id = BoundedRetry.run(
        policy,
        perAttemptBudget -> {
            // SDK timeout phải được đặt <= perAttemptBudget.
            // readCustomerById là một read an toàn để replay.
            return client.readCustomerById("C-42", perAttemptBudget);
        },
        failure -> isTransientReadFailure(failure)
);
~~~~

Các hàm **client.readCustomerById** và **isTransientReadFailure** do ứng dụng định nghĩa; đoạn gọi minh họa cách cắm vào client thực. Cần dùng loại lỗi và timeout mà SDK tương ứng công bố.

### 21.2. Điểm giới hạn của ví dụ

- Vòng retry đồng bộ giữ thread trong lúc sleep; với tải cao nên cân nhắc async scheduling không blocking.
- Bộ phân loại lỗi chưa được implement vì phụ thuộc SDK.
- Không xử lý Retry-After/server-directed delay.
- Không có shared retry token budget/circuit breaker/bulkhead.
- Per-attempt deadline chỉ được truyền đi: nếu callback **bỏ qua budget và block vô hạn**, lớp retry không thể cứu.
- MaxElapsed không tự bao gồm deadline của caller khác trừ khi caller truyền policy phù hợp.
- Không đưa operationId vào callback: caller phải tự bảo đảm.
- Một full-jitter sample bằng 0 có thể retry ngay; overall load cần retry budget.
- Trong production nên dùng thư viện được kiểm chứng và đo behavior của retry ở tất cả các tầng.

### 21.3. Vì sao validate maxDelay <= 5 phút?

Cụ thể mã dùng **capNanos + 1** để chọn số ngẫu nhiên inclusive. Bound <= 5 phút giúp tránh overflow long trong ví dụ. Nếu xây library hỗ trợ Duration cực lớn, phải thêm thuật toán xử lý overflow và kiểm tra policy toàn diện.

### 21.4. Một thận trọng về elapsed deadline

Code dùng **System.nanoTime() - started**, không so trực tiếp hai wall-clock timestamps. Với các khoảng thời gian giới hạn ngắn, đây là cách đo elapsed phù hợp. Khi deadline được truyền xuyên nhiều máy, cần quy tắc conversion/clock skew ở biên dịch vụ.

## 22. Java: HTTP idempotency và timeouts

Một HTTP caller Java có thể giữ operationId ổn định và dùng timeout cho mỗi attempt. Ví dụ minh họa:

~~~~java
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;

public final class ReservationHttpClient {
    private final HttpClient client = HttpClient.newHttpClient();
    private final URI endpoint;

    public ReservationHttpClient(URI endpoint) {
        this.endpoint = endpoint;
    }

    public HttpResponse<String> reserveOnce(
            String operationId,
            String canonicalBody,
            Duration timeout
    ) throws Exception {
        HttpRequest request = HttpRequest.newBuilder(endpoint)
                .timeout(timeout)
                .header("Content-Type", "application/json")
                .header("Idempotency-Key", operationId)
                .POST(HttpRequest.BodyPublishers.ofString(canonicalBody))
                .build();

        return client.send(
                request,
                HttpResponse.BodyHandlers.ofString()
        );
    }
}
~~~~

**Lưu ý:**
- Header Idempotency-Key chỉ có tác dụng nếu **server thực sự bảo vệ và lưu key**.
- HttpClient timeout không khẳng định request chưa commit.
- Nếu client.send bị interrupt, code cần preserve/correctly propagate interrupt; không âm thầm retry.
- Cùng một operationId phải đi cùng **cùng logical payload**; thay payload giữa retries cần báo conflict.
- HTTP 200/201/202/409/429/503 phải được phân loại theo **hợp đồng API**, không chỉ dựa vào số.
- Dừng retry khi caller cancel dù có socket activity còn tồn tại phía server.

### 22.1. Không đổi operationId trong mỗi attempt

Sai:

~~~~java
for (int i = 0; i < 4; i++) {
    String opId = java.util.UUID.randomUUID().toString();
    // Mỗi attempt có thể là một logical operation mới!
    sendReservation(opId);
}
~~~~

Đúng về mặt ý định:

~~~~java
String opId = java.util.UUID.randomUUID().toString();
// Lưu opId cùng hành động người dùng trước khi phát request.

for (int i = 0; i < 4; i++) {
    // Retry cùng logical operationId.
    sendReservation(opId);
}
~~~~

Vòng lặp thứ hai chỉ minh họa **identity**, chưa có backoff/deadline/error classification; cần kết hợp một retry policy đầy đủ.

## 23. Java async: scheduler thay vì ngủ trên mọi worker

Khi có hàng nghìn requests đồng thời:
- Thread.sleep giữ mỗi platform thread trong lúc chờ.
- Virtual threads trong Java 21 giúp chi phí blocking threads dễ quản lý hơn trong nhiều trường hợp, nhưng không giảm **số logical retries** hoặc tải database.
- Async CompletableFuture/scheduled executor có thể dùng lịch retry không chiếm worker thực thi chính.

Một mô hình:

~~~~text
Attempt future completed exceptionally
    -> classify error
    -> check deadline + retry budget
    -> schedule next attempt after jitter
    -> propagate success/failure/cancellation
~~~~

Những vấn đề không được bỏ qua:
- Cancellation của outer future phải ngăn scheduling retry mới.
- Nếu một attempt vẫn chạy khi caller cancel, không giả định server đã rollback.
- Không để hàng triệu scheduled retry tasks trong RAM.
- Propagate traceId/operationId và deadline.
- Close executor/resource đúng lifecycle.
- Không tạo một scheduler/thread mới cho mỗi request.
- Backpressure ở queue và concurrency cap.

**Dùng async không làm idempotency tự nhiên xuất hiện**. Nó chỉ thay đổi cách chờ.

## 24. Spring/Resilience4j và thư viện retry: áp nguyên tắc, không chép cấu hình mù

Ứng dụng Java có thể dùng các thư viện resilience đã được kiểm chứng (ví dụ Resilience4j hoặc retry facilities từ framework/SDK). Những thư viện này thường hỗ trợ một phần của:
- Max attempts.
- Wait interval.
- Backoff function.
- Jitter/randomization.
- Retry exception/result predicate.
- Circuit breaker.
- Rate limiter/bulkhead.
- Metrics/events.

Nhưng phải kiểm tra **phiên bản đang dùng**:
- Max attempts đếm cả lần đầu?
- Retry timeout có bao gồm thời gian chờ?
- Jitter là full/equal/decorrelated hay percentage randomization?
- Có retry khi result predicate true?
- Fallback có che business errors không?
- Có propagate interruption/cancellation?
- RetryAfter support có hoạt động theo response cụ thể?
- SDK NoSQL bên dưới có retry sẵn không?

### 24.1. Annotation không thay business semantics

Một phương thức:

~~~~java
@Retry(name = "databaseWrites")
public Order createOrder(CreateOrderRequest request) {
    return repository.insert(request);
}
~~~~

**Annotation trên chỉ là ví dụ hình thức**, không gồm import/config đầy đủ và không chứng minh phương thức an toàn. Nếu mỗi lần gọi sinh một orderId mới, retry có thể nhân đôi order.

Cần tạo **operationId bên ngoài retry boundary**, lưu ledger atomically và kiểm tra payload fingerprint.

### 24.2. Đừng retry cả transaction body có external side effect

Ví dụ sai:

~~~~text
retry(() -> {
    database.reserve();
    paymentProvider.capture();
    email.send();
});
~~~~

Nếu payment capture thành công nhưng email timeout, retry toàn body có thể:
- Reserve lần hai.
- Capture lần hai.
- Gửi email trùng.

Nên dùng:
- Atomic DB transaction/outbox trong phạm vi hỗ trợ.
- Payment provider idempotency.
- Workflow/saga state machine.
- Worker dedup cho email.
- Retry **từng bước** có operationId và outcome check.

## 25. MongoDB: retryable writes và transaction outcome

MongoDB cung cấp các khả năng driver/server liên quan đến **retryable reads/writes** theo những điều kiện, topology và operations nhất định; transactions có labels/error semantics riêng.

Điểm cần hiểu:
- Driver retry được một loại write **không có nghĩa mọi business workflow tự exactly-once**.
- Một write đơn lẻ với retry identity của driver khác một service tạo order + charge + send email.
- Write concern timeout và network timeout có thể không cho client biết cuối cùng đã commit hay chưa.
- Transaction commit có thể trả **unknown commit result**; cách thử lại commit/transaction theo đúng driver contract khác việc làm lại mọi side effect tùy ý.
- Duplicate key/validation failure thường không được retry nguyên xi.
- Read preference/secondary lag ảnh hưởng read-after-write/verification.

### 25.1. Một lệnh insert với ID ổn định

Nếu application dùng một **_id cố định** cho cùng logical order:
- Attempt đầu insert có thể thành công rồi ACK mất.
- Retry insert cùng _id có thể gặp duplicate key.
- Duplicate key **không tự chứng minh payload hiện có chính là payload mong muốn**.
- Nên đọc authoritative record và so fingerprint/operationId trước khi quyết định trả kết quả cũ.

Một lớp idempotency phải phân biệt:
1. Duplicate cùng logical operation → trả prior result.
2. Duplicate ID nhưng payload khác → conflict.
3. ID đã bị tái sử dụng bởi thao tác khác → lỗi tính toàn vẹn.

### 25.2. Quá nhiều lớp retry

Driver có thể retry theo hợp đồng của nó. Service retry bên ngoài:
- Phải biết effective attempt count.
- Không tự retry một non-idempotent multi-step workflow.
- Giữ cùng session/transaction identity nếu protocol yêu cầu.
- Không tự phân loại mọi MongoException là transient.

Chỉ dùng semantics được tài liệu của phiên bản/driver hỗ trợ, không suy từ tên exception chung.

## 26. Cassandra: QUORUM timeout và LWT có ý nghĩa riêng

Cassandra có write/read consistency levels và các cơ chế khác cho **conditional/LWT**.

Một write QUORUM timeout có thể:
- Không đạt đủ ACK trong deadline.
- Đã được một số replica chấp nhận.
- Không có response hoàn chỉnh phía coordinator.
- Sau đó các replica tiếp tục hội tụ/repair tùy cơ chế.

Với write thường, không nên coi mọi timeout là “chắc chắn không có effect”, đặc biệt đối với counters hoặc workflow có side effect.

### 26.1. Normal write khác CAS/LWT

Một ordinary upsert cùng key/value có thể gần idempotent về trạng thái cuối theo conflict semantics, nhưng:
- Timestamps, TTL, concurrent writes và application-generated IDs có thể ảnh hưởng.
- Counter increments thường không idempotent.
- LWT/conditional operations có session/serial consistency và failure handling riêng.
- Driver có thể phân loại retry dựa trên tính idempotent được khai báo.

**Không khai báo một counter increment là idempotent** chỉ để driver tự retry nhanh hơn.

### 26.2. Reread sau LWT timeout

Nếu CAS outcome không rõ:
- Dùng logical operationId trong state/ledger khi cần.
- Reread theo consistency contract để phân biệt kết quả.
- Không dùng eventual read stale làm bằng chứng cuối.
- Retry trong bounded budget và hiểu serial operation semantics.

### 26.3. Retry không chữa thiếu replica

Nếu chỉ có một replica reachable mà consistency level cần quorum:
- Thử lại mười lần không tạo thêm replica.
- Cần topology recovery, routing hoặc thay hợp đồng consistency có chủ đích.
- Không tự giảm consistency level của transaction giữ invariant chỉ để nhận HTTP 200.

## 27. DynamoDB: throttling, conditional failures và transactions

Ở DynamoDB:
- Một số lỗi throttling/capacity/service transient là ứng viên retry với backoff+jitter.
- ConditionalCheckFailedException biểu thị condition không đạt, không phải lời mời retry y hệt vô hạn.
- Một update có điều kiện vẫn có thể lặp effect nếu condition tiếp tục đúng ở lần thứ hai.
- Transaction APIs có cơ chế idempotency token trong **phạm vi/cửa sổ được dịch vụ định nghĩa**, không thay một operation ledger giữ lâu nếu business cần.
- GSI có eventual visibility; một item chưa xuất hiện ở GSI không chứng minh source write thất bại.

### 27.1. Partition hot và retry

Nếu tenantId/key cực nóng tạo throttling:
- Backoff+jitter giảm sóng retry.
- Nhưng logical partition vẫn có thể chịu giới hạn capacity.
- Có thể cần sharding/bucketing, đổi access pattern hoặc giảm producer rate.
- Nếu cùng item phải bảo vệ invariant, không được random tách item mà phá atomicity.

### 27.2. Retry cả TransactWriteItems?

Cần xem transaction outcome và token semantics được SDK/API hỗ trợ. Không mặc định:
- Throttle = transaction không có effect.
- Timeout = transaction rollback.
- Dùng token mới = cùng logical operation.
- Transaction an toàn nếu trong body có external HTTP payment.

Giữ **same logical intent**, phù hợp với idempotency contract của API và deadline.

## 28. Redis: connection retry, redirection và lệnh không idempotent

Redis có các tình huống:
- Network timeout.
- Connection reset.
- Master/replica failover.
- Cluster routing với MOVED/ASK redirection theo semantics client.
- Lua script hoặc lệnh atomic ở instance.
- Replication ACK có mức durability riêng tùy policy.

### 28.1. INCR không thể replay tùy ý

~~~~text
INCRBY quota:T-42 1
ACK bị mất
Retry INCRBY quota:T-42 1
~~~~

Counter có thể tăng hai lần. Việc mỗi INCR atomic không ngăn duplicate logical intent.

Có thể cần:
- EventId/operation ledger.
- Lua/transaction pattern phù hợp với cùng-slot constraints nếu dùng Redis Cluster.
- Hoặc dùng authority có durability/atomicity phù hợp với nghiệp vụ.

### 28.2. MOVED/ASK khác business retry

Một Redis Cluster client có thể cần cập nhật routing khi slot chuyển chủ. Đây là **topology redirect**, không tương đương việc server khẳng định lệnh trước chưa thực thi trong mọi trường hợp.

Driver hiểu protocol thường có thể xử lý các redirect phù hợp. Application không nên tự gửi cùng side-effect write tới nhiều nodes vì thấy redirect lỗi.

### 28.3. Redis cache retry cần fallback hợp đồng

Khi cache timeout:
- Có thể bypass về authoritative database nếu backend đủ capacity.
- Cần tránh **cache stampede**.
- Không retry cache read mười lần rồi làm cạn HTTP deadline.
- Fallback trả dữ liệu cũ chỉ khi API cho phép staleness.
- Không dùng cache stale để xác nhận tồn kho/thanh toán/quyền nếu cần dữ liệu mạnh.

## 29. HBase và write-heavy pipelines

Trong HBase, lỗi tạm thời có thể liên quan:
- RegionServer/region movement.
- RPC timeout.
- WAL/hạ tầng lưu trữ.
- Compaction hoặc pressure.
- Routing metadata lỗi thời.

Driver/API có thể có retry semantics riêng cho thao tác phù hợp. Nhưng ứng dụng cần phân biệt:
- Put overwrite theo row key ổn định với increment/append.
- Conditional mutation và bất biến nghiệp vụ.
- Timeout trước/sau khi region server đã xử lý.
- Multi-row workflow không tự atomic chỉ vì mỗi Put có retry.

### 29.1. Batch import

Với batch gồm 1.000 rows:
- Không mặc định một timeout chứng minh cả batch thất bại.
- Có thể có partial successes hoặc per-row outcomes theo API.
- Retry phải dùng stable keys/eventIds.
- Đừng replay toàn batch không có dedup guard nếu có increment hoặc external side effects.

### 29.2. Throttle import khi compaction quá tải

Backoff+jitter giảm nhịp retry, nhưng nếu ingestion ổn định vượt throughput có thể duy trì:
- WAL/compaction backlog tăng.
- RegionServers hot.
- p99 interactive queries xấu.

Cần admission/batch sizing, split/partitioning và tài nguyên dự phòng, không chỉ tăng timeout.

## 30. Search/secondary indexes: retry read không làm dữ liệu mới hơn ngay

Một source transaction commit v42. Search index chưa apply v42.

Client query ngay:

~~~~text
Query #1 -> v41
Query #2 -> v41
Query #3 -> v41
Query #4 -> v42
~~~~

Nếu API hứa eventual search với freshness SLO:
- Có thể hiển thị v41 có nhãn phù hợp.
- Có thể dùng bounded wait/polling khi user cần thấy thay đổi vừa thực hiện.
- Nếu deadline hết, trả PENDING_INDEXING thay vì giả vờ source chưa commit.
- Không tăng QPS polling quá cao khi indexer lag.

### 30.1. Read-your-writes cần token/routing

Một số hệ có session token hoặc minVersion read. Nếu client vừa write v42:
- Gửi token để chỉ nhận ít nhất v42 khi contract hỗ trợ.
- Chờ/reroute tới replica đã apply.
- Nếu không đáp ứng trong deadline, fail/return pending.

**Retry GET trên replica stale không có minimum-version guard có thể liên tục trả v41**, thậm chí đi lùi giữa các lần.

### 30.2. Polling trạng thái khác retry commit

Sau khi tạo order:
- POST commit một lần theo idempotency policy.
- GET /operations/OP-101 có thể được polling với backoff+jitter và deadline phù hợp.
- Không phát lại POST với ID mới chỉ vì search chưa thấy.

Polling là một API workload riêng, cũng cần budget và server support.

## 31. Chính sách riêng cho từng nhóm thao tác

| Thao tác | Retry trong lỗi transient? | Điều kiện an toàn | Khi hết budget |
| --- | --- | --- | --- |
| Point GET eventual | Có thể | Giới hạn load/deadline | Trả lỗi hoặc fallback stale theo contract |
| Strong read | Có thể | Không hạ consistency lén; session context | Unavailable/timeout |
| Full scan/aggregation | Rất hạn chế | Query cost budget, cursor | Fail/cancel/defer batch |
| Upsert theo ID ổn định | Có thể | Check payload/version/concurrent semantics | UNKNOWN hoặc lỗi phù hợp |
| Increment counter | Không mù | EventId/dedup hoặc chấp nhận xấp xỉ | UNKNOWN/reconcile |
| Create order | Chỉ dưới idempotency | OperationId + atomic result ledger | UNKNOWN/PENDING |
| Conditional stock reserve | Chỉ dưới idempotency | Guard cho **cùng intent** | UNKNOWN/REJECTED theo chứng cứ |
| Payment capture | Theo provider contract | Provider idempotency key | UNKNOWN + provider reconciliation |
| CAS/version conflict | Có thể sau reread | Recompute business intent | Conflict/abort |
| Transaction commit | Theo driver protocol | Giữ transaction identity, không lặp side effect | UNKNOWN và tra kết quả |
| CDC consumer apply | Thường có | EventId/version/idempotent projection | DLQ/replay với audit |
| Delete | Có điều kiện | Version/generation tránh xóa bản tạo lại | UNKNOWN/reconcile |
| Background import | Có | Stable row IDs, checkpoint, rate control | Persist checkpoint/defer |

**Policy theo operation** tốt hơn một **global retry count=10**.

## 32. SLO và chính sách retry tương tác thế nào?

Giả sử checkout yêu cầu p99 < 300 ms. Nếu:
- Attempt 1 timeout sau 250 ms.
- Backoff 100 ms.
- Attempt 2 mất 250 ms.

thì request hoàn tất khoảng 600 ms, **không đạt p99** dù retry có thể giúp eventual success.

### 32.1. Success rate và latency phải đo cùng nhau

Đo:
- Tỷ lệ requests thành công **trong deadline**.
- Tỷ lệ thành công nhưng vượt SLO.
- Tỷ lệ failure không retryable.
- Tỷ lệ retry budget exhausted.
- Retry amplification.
- Per-attempt latency và toàn request latency.
- Unknown write outcomes và thời gian reconcile.
- DB error rate, throttling, leader elections.

Một chiến lược tăng success rate từ 95% lên 98% nhưng đẩy p99 từ 200 ms lên 4 giây có thể không phù hợp sản phẩm.

### 32.2. Tail latency và retries

Retry khi một request chậm có thể:
- Chuyển request tới node khỏe và giảm tail latency, nếu backend vẫn đủ capacity.
- Tăng queue/contension và làm p99 xấu hơn.
- Trì hoãn những request khác.
- Làm server xử lý duplicate attempts cùng lúc nếu request đầu chưa cancel.

Cần đo **offered load vs achieved throughput**, không chỉ latency của request cuối thành công.

### 32.3. Chọn deadline theo business critical path

Một GET listing 100 ms và một reconciliation job 30 phút không nên dùng cùng retry policy. Interactive request cần:
- Attempts ít.
- Deadline ngắn.
- Fail fast khi server không thể phục vụ.
- Trạng thái pending rõ.

Background workflow có thể:
- Persist state/checkpoint.
- Chờ lâu hơn với jitter lớn.
- Respect quota.
- Đối soát ID sau crash.
- Không giữ một HTTP request mở 30 phút vô ích.

## 33. Thiết kế server trả lỗi và tín hiệu retry

Backend có thể giúp client hành xử đúng bằng một contract rõ:

| Response/result | Ý nghĩa cần diễn đạt | Client |
| --- | --- | --- |
| 200/201 COMMITTED | Đã xác nhận theo contract | Dừng |
| 202 ACCEPTED/PENDING | Intent được nhận, chưa necessarily business committed | Poll operation status |
| 400/422 validation | Payload sai | Không retry y hệt |
| 401/403 | Auth hoặc quyền không phù hợp | Xử lý auth, không spam retry |
| 404 definitive | Resource không có theo authoritative contract | Dừng hoặc xử lý business |
| 409 conflict | Precondition/uniqueness conflict | Reread/recompute hoặc báo người dùng |
| 429 throttled | Limit tạm | Backoff, Retry-After, budget |
| 503 unavailable | Backend tạm không phục vụ | Backoff/circuit và deadline |
| 504 timeout | Upstream không có kết quả trong hạn | Nếu write, có thể UNKNOWN |
| Transport failure after send | Kết quả không rõ | Reconcile/idempotent replay |

Không nhất thiết mọi service dùng đúng status ở bảng; quan trọng là **hợp đồng machine-readable phân biệt committed, rejected, pending và unknown**.

### 33.1. Thông tin hữu ích trong error body

~~~~json
{
  "errorCode": "QUORUM_TEMPORARILY_UNAVAILABLE",
  "retryable": true,
  "operationId": "OP-101",
  "outcome": "UNKNOWN",
  "retryAfterMillis": 500,
  "requestId": "REQ-901"
}
~~~~

**Không tin tuyệt đối vào trường retryable do một proxy tùy tiện thêm**: SDK/service phải bảo vệ contract của operation và xác minh idempotency. Một lỗi có retryable=true không làm mất rủi ro double side effect khi operationId không được enforce.

### 33.2. Độ trễ phụ thuộc retry location

Một 503 do shard 17 bị thiếu quorum không nên khiến client spam tất cả shard khác. Lỗi cần có:
- Shard/cell/region identifier để quan sát.
- Hướng redirect nếu protocol hỗ trợ.
- Scope của throttling.
- Server retry hint theo tải.

Không lộ internal topology nhạy cảm ra API public nếu không cần; có thể ánh xạ thành retry policy fields an toàn.

## 34. Observability: nhìn retries như một workload riêng

Dashboard tối thiểu nên có:

| Metric | Câu hỏi cần trả lời |
| --- | --- |
| Original request rate | Người dùng thực sự đang tạo bao nhiêu ý định? |
| Total attempts rate | Backend phải xử lý bao nhiêu calls gồm retry? |
| Retry amplification factor | Mỗi logical request tạo bao nhiêu attempts? |
| Retry attempts histogram | Các request thường dùng hết bao nhiêu lần? |
| Retry reason breakdown | Throttle, network, leader change, quorum, timeout? |
| Backoff distribution | Jitter có thực sự rải chờ? |
| Retry budget remaining/denials | Tải thử lại có bị giới hạn? |
| Circuit breaker state | Phần dependency nào đang open/half-open? |
| Per-tenant/cell retries | Một tenant có gây noisy-neighbor không? |
| Per-attempt timeout rate | Backend có chậm hơn timeout được cấp không? |
| End-to-end deadline misses | Có trả thành công sau khi caller đã hết hạn không? |
| UNKNOWN operation count/age | Có bao nhiêu write chưa xác minh outcome? |
| Idempotency hits/conflicts | Bao nhiêu replay trả prior result hoặc reuse key sai? |
| Duplicate business effects | Có double order/debit/increment không? |
| Leader elections/quorum health | Retry có trùng với failover/partition không? |
| Queue depth/backlog | Retry có làm pressure kéo dài không? |
| Recovery time after fault | Backend hồi phục mất bao lâu dưới retry load? |

### 34.1. Không chỉ đếm số exception

Một hệ có thể giảm exception rate bằng cách retry vô hạn trong SDK, nhưng:
- Request p99 tăng.
- Backlog tăng.
- Client timeout trước khi SDK hoàn tất.
- DB attempts tăng.
- UNKNOWN outcomes bị giấu.

Đo cả **inner attempts và outer logical results**.

### 34.2. Tracing theo logical operation

Một trace có thể:

~~~~text
traceId = TR-901
operationId = OP-101
originalRequest = true

attempt #1:
    endpoint = node-A
    failure = leader_not_ready
    elapsed = 150 ms

backoff:
    cap = 100 ms
    chosenJitter = 68 ms

attempt #2:
    endpoint = node-B
    failure = timeout_unknown
    elapsed = 300 ms

reconciliation:
    ledger OP-101 = COMMITTED
    reservationId = RES-77

final:
    COMMITTED (prior result)
~~~~

Không tạo operationId mới cho mỗi span; attemptId riêng là tốt để debug nhưng phải liên kết với **cùng logical identity**.

### 34.3. Metric cardinality

Không đưa operationId hoặc mọi userId vào labels của time-series metrics:
- Cardinality tăng không giới hạn.
- Monitoring có thể thành hệ noisy neighbor.
- Lộ thông tin nhận dạng.

Dùng labels ở mức operation type, cell, region, error category; chứa operationId trong logs/traces được kiểm soát.

## 35. Thử nghiệm jitter và retry khi có outage chung

Một test chỉ gửi một request rồi làm server trả 503 chưa đủ để đánh giá retry storm.

### 35.1. Kịch bản 10.000 clients đồng thời

Giả sử:
- 10.000 clients bắt đầu cùng lúc.
- Server tạm unavailable 1 giây.
- Mỗi client có tối đa 4 attempts.
- Base delay=100 ms, cap=1.000 ms.
- So sánh **no jitter** với **full jitter**.

Cần đo:
- Attempts/10 ms bucket.
- Peak attempted QPS.
- Tổng attempts đến backend.
- Queue depth và CPU.
- Recovery duration.
- Success within deadline.
- p95/p99.
- Retry budget denials.

No jitter thường tạo những sóng đúng tại các mốc backoff lý thuyết; full jitter rải request trên khoảng nhưng **không tự giới hạn số attempts**.

### 35.2. Fault matrix

| Sự cố | Loại thao tác | Điều cần kiểm tra |
| --- | --- | --- |
| Connect fail trước send | Idempotent GET | Retry theo budget thành công sau recovery |
| Network timeout sau commit | Create order | Same operationId không tạo order trùng |
| Leader election 500 ms | Strong write | Backoff giảm storms và không phá deadline |
| Minority partition 10 phút | Quorum write | Dừng có kiểm soát, không retry vô hạn |
| Throttling 429 | Batch importer | Honor Retry-After và giới hạn QPS |
| Repeated 503 | GET/Search | Circuit breaker và fallback theo contract |
| Version conflict | CAS update | Reread/recompute bounded; không lặp version cũ |
| Quota exceeded hard | Any write | Không retry y hệt khi account không đủ quota |
| Slow query p99 | Scatter-gather read | Retry không làm scan load tăng quá mức |
| Cache outage | Product listing | Bypass/guard thundering herd |
| Follower stale | Read-your-writes | Không trả version cũ dưới promise stronger |
| SDK + service nested retry | Any request | Effective attempts không vượt budget |
| Interrupted/cancelled | Java worker | Không phát retry mới sau cancel |
| Idempotency ledger lag | Operation status | Không kết luận chưa commit từ eventual read |
| Background replay | CDC consumer | Duplicate/out-of-order events idempotent |
| Cold cache after failover | Read-heavy | Gradual recovery, admission caps |
| Restart Java process | Durable job | Same operationId và retry history survive |
| Provider payment timeout | Capture | Reconcile provider không double charge |

### 35.3. Tiêu chí pass/fail

Ví dụ:
- **Correctness:** không double reserve/charge; no stale read ngoài mode.
- **Amplification:** attempts/original requests dưới ngưỡng đã định.
- **Budget:** không request nào vượt maxAttempts của tầng sở hữu policy.
- **Deadline:** không retry sau caller cancellation; timeout được báo rõ.
- **Recovery:** service ổn định lại trong mục tiêu; không retry surge ngay sau failover.
- **Fairness:** tenant nhỏ không vượt SLO vì tenant lớn bị lỗi.
- **Observability:** mọi retry có reason, attempt number và outcome phân biệt.
- **Unknown reconciliation:** số operation UNKNOWN giảm theo runbook, không bị quên mãi.

**Không đánh giá correctness chỉ bằng HTTP success rate**.

## 36. Benchmark ảnh hưởng của retry policy đến capacity

Một đặc tả thí nghiệm:

~~~~yaml
experiment: bounded-backoff-jitter-nosql
application:
  javaVersion: 21
  operationClasses:
    - point_read
    - conditional_reserve
    - create_order_idempotently
    - append_event
    - batch_import
traffic:
  originalRequestsPerSecond: 12000
  clientConcurrency: 3000
  distribution: zipfian
  burstMultiplier: 4
policies:
  - no_retry
  - immediate_retry_3_times
  - exponential_without_jitter
  - exponential_full_jitter
  - exponential_equal_jitter
  - full_jitter_with_retry_budget
bounds:
  maxAttemptsIncludingInitial: 4
  totalDeadlineMillis: 3000
  perAttemptTimeoutMillis: 500
  baseDelayMillis: 100
  capDelayMillis: 1000
faults:
  - normal
  - leader_election
  - node_partition
  - service_throttling
  - slow_disk
  - ack_loss_after_commit
  - hot_partition
measure:
  - backend_attempts_per_second
  - retry_amplification
  - p50_p95_p99_end_to_end
  - error_and_timeout_rate
  - unique_operations_committed
  - duplicate_business_effects
  - unknown_operation_count
  - retry_budget_denied
  - recovery_time
  - cpu_memory_disk_network_queue_depth
~~~~

Đây là **mô tả thí nghiệm**, không phải cấu hình native có thể chạy trực tiếp. Cần gắn load generator vào SDK và cách fault injection được phép.

### 36.1. Kết quả minh họa

| Policy trong outage giả định | Peak attempts/s | End-to-end p99 | Recovery | Vấn đề |
| --- | ---: | ---: | --- | --- |
| No retry | 12.000 | 400 ms (nhiều lỗi) | Nhanh về tải, nhưng nhiều request fail | UX thiếu phục hồi ngắn hạn |
| Immediate retry 3 lần | 46.000 | 2.400 ms | Chậm hơn | Storms và queue |
| Exponential không jitter | 32.000 vào từng đợt | 1.800 ms | Có sóng | Đồng bộ retries |
| Full jitter | 21.000 | 1.500 ms | Tốt hơn trong ví dụ | Vẫn cần budget |
| Full jitter + budget | 14.000 | 1.200 ms | Ổn định hơn | Một số requests bị từ chối retry |

**Số liệu chỉ giả định**, không phải định luật hay benchmark thực. Khi đọc bảng:
- Peak attempts/s khác tổng attempts.
- p99 chỉ trên successful requests có thể che timeout; cần báo both.
- Recovery còn phụ thuộc disk/log replay/network.
- Một policy thành công hơn về availability có thể tệ hơn về cost hoặc latency.
- Với write non-idempotent, policy nhanh nhất vẫn **không được chấp nhận** nếu gây side effect trùng.

### 36.2. Thử lỗi tương quan

Đừng mô phỏng chỉ 1% random failures độc lập. Cần cả:
- Mọi client cùng thấy lỗi 503 trong 30 giây.
- 30% shards mất quorum.
- Mạng EU↔VN partition.
- Từng node bị disk slow.
- Một mega-tenant dồn query vào một hot partition.
- Response bị mất **sau khi commit**.

Đây là những kịch bản trong đó retries có thể nguy hiểm nhất.

## 37. Runbook khi retry storm làm NoSQL không hồi phục

### Bước 1 — Nhận diện storm

- Original request rate có thay đổi nhiều không?
- Backend attempt rate có tăng vượt mức original?
- Retry amplification A là bao nhiêu?
- Retry reasons chủ đạo là throttle, timeout, leader change hay quorum?
- Max attempts effective có bị nhân qua SDK/gateway/service?
- Có một tenant/endpoint/shard gây phần lớn retry không?

### Bước 2 — Xác định dependency thật đang lỗi

- Node/leader election health?
- Voting quorum?
- Disk fsync/compaction?
- Network packet loss/RTT?
- Hot key/partition?
- Rate limits và capacity?
- Connection pool bị full?
- Search/index lag hay source DB thật sự lỗi?

### Bước 3 — Giảm tải chủ động

- Giới hạn retries theo budget.
- Kích hoạt circuit breaker phù hợp scope.
- Throttle batch import/background jobs.
- Giảm in-flight concurrency.
- Trả fast 429/503/PENDING theo contract.
- Giữ interactive capacity cho các thao tác quan trọng.
- Không tự trả COMMITTED để che lỗi.

### Bước 4 — Bảo vệ dữ liệu đang UNKNOWN

- Không xóa/đổi operationId khi timeout.
- Tra authoritative ledger/transaction status.
- Dùng provider idempotency cho payment.
- Không retry non-idempotent writes nếu thiếu dedup.
- Giữ danh sách operations unresolved và tuổi của chúng.

### Bước 5 — Khôi phục và mở traffic có kiểm soát

- Chờ quorum/leader/storage ổn định.
- Kiểm tra replication/log replay progress.
- Half-open circuit với số probe giới hạn.
- Gradual ramp-up/QPS caps.
- Backoff+jitter cho queued workers.
- Giám sát cache warmup và repair load.

### Bước 6 — Đối soát sau sự cố

- Số operation UNKNOWN còn lại?
- Có duplicate booking/debit/counter effect không?
- Retry amplification về baseline chưa?
- p99/error budget theo tenant có phục hồi?
- Có backlog CDC/index/search?
- Có need thay timeout, retry owner hoặc topology?
- Có lỗ hổng observability khi một tầng tự retry ẩn không?

**Trong outage, ưu tiên khôi phục năng lực hệ và bảo vệ correctness hơn là cố làm mọi client nhận HTTP 200 bằng retries vô hạn.**

## 38. Những hiểu nhầm dễ gây lỗi

1. **“Retry ngay sẽ giảm latency.”** Khi nhiều client cùng lỗi, retry ngay có thể làm backend quá tải.
2. **“Exponential backoff là đủ.”** Không jitter vẫn tạo sóng đồng bộ.
3. **“Jitter là giải pháp chống mọi retry storm.”** Nó trải thời gian, không giới hạn tổng attempts.
4. **“MaxAttempts=3 luôn nghĩa ba retry sau lần đầu.”** Phải đọc semantics của thư viện.
5. **“Có maxAttempts thì không cần deadline.”** Một attempt có thể block quá lâu.
6. **“Có timeout mỗi attempt thì total timeout được giới hạn.”** Nhiều attempts + sleep có thể vượt deadline.
7. **“Đã có deadline thì không cần retry budget.”** Hàng triệu request vẫn có thể tăng tải quá mức.
8. **“Mọi 5xx đều nên retry.”** Không nếu side effect có thể đã commit.
9. **“504 nghĩa server rollback.”** ACK có thể mất sau commit.
10. **“Exception ghi DB nghĩa lệnh không được chạy.”** Transport errors thường không cho biết outcome.
11. **“Counter atomic nên retry INCR an toàn.”** Atomic không đồng nghĩa idempotent.
12. **“Conditional stock >=1 ngăn double reserve.”** Một intent có thể trừ hai lần nếu đủ stock.
13. **“Thêm Idempotency-Key header là đủ.”** Server phải enforce atomically.
14. **“Duplicate key luôn là success của cùng operation.”** Phải so operationId/fingerprint.
15. **“Tạo UUID mới khi retry giúp tránh trùng.”** Chính nó có thể tạo duplicate effect.
16. **“GET eventual không thấy record nghĩa write chưa commit.”** Replica/index có thể trễ.
17. **“Read strong không thấy record tại t1 chứng minh in-flight write không commit ở t2.”** Chưa chắc nếu request còn đang xử lý.
18. **“Retry đến khi quorum có lại là an toàn.”** Có thể mất hàng giờ, gây storms.
19. **“Chỉ tăng số thread là server hồi phục.”** Nếu DB thiếu quorum/hot key, threads tạo thêm pressure.
20. **“Tăng timeout vô hạn giải quyết leader election.”** Làm backlog kéo dài và UX treo.
21. **“Retries ở gateway và SDK không liên quan nhau.”** Attempts có thể nhân cấp số nhân.
22. **“Driver retryable write bao trùm payment/email.”** Không có cross-service guarantee.
23. **“Hedged writes an toàn như hedged reads.”** Không nếu không có guard.
24. **“Full jitter bảo đảm delay không bao giờ 0.”** Phân bố có thể chọn gần 0.
25. **“Equal jitter luôn tốt hơn full jitter.”** Phụ thuộc workload và mục tiêu.
26. **“Decorrelated jitter không cần state.”** Thường phụ thuộc previous delay.
27. **“Retry-After phải luôn được chờ dù caller hết deadline.”** Có thể dừng sớm.
28. **“RetryAfter chỉ có đơn vị giây.”** HTTP có thể cho thời điểm HTTP-date.
29. **“Sleep có thể nuốt InterruptedException.”** Phải xử lý cancellation.
30. **“Virtual threads làm retry storm biến mất.”** Backend attempts không giảm.
31. **“Throttling nghĩa cứ retry sớm.”** Cần giảm offered load.
32. **“Circuit breaker global luôn tốt.”** Có thể lan sự cố một shard sang mọi tenant.
33. **“Nếu retry success thì metric ban đầu không cần ghi.”** Cần đo amplification và failures.
34. **“Chỉ báo p99 success là đủ.”** Bỏ qua timeout/rejections và unknown outcomes.
35. **“Một test random 1% lỗi đại diện production.”** Outage thường tương quan.
36. **“Retry cả transaction body chứa provider capture là ổn.”** Có thể charge trùng.
37. **“Read-only không cần giới hạn retry.”** Query scan vẫn tốn CPU/IO.
38. **“Tăng retry count luôn tăng success.”** Khi backend quá tải, có thể giảm cả success và recovery.
39. **“Trả HTTP 202 là đã commit.”** Có thể chỉ là queue intent.
40. **“Backoff chỉ cần ở client.”** Server admission/load shedding cũng quan trọng.

## 39. Bài tập tình huống: booking NoSQL ba vùng

Một dịch vụ booking dùng Java 21 và NoSQL, với các giả định:
- Ba vùng **VN, EU, US**.
- Cụm có quorum cho những thao tác giữ booking.
- 12.000 logical requests/s ở peak.
- 40% reads, 40% conditional reservations, 20% event ingestion.
- Gateway có timeout **4 giây**.
- Order Service có deadline **3 giây** cho DB workflow.
- SDK có retry built-in theo một số lỗi.
- Search index được cập nhật async.
- Một slot không thể được confirmed cho hai khách.
- Cùng operationId không được tạo nhiều reservation.
- Một lần failover có thể khiến 50% requests timeout trong 2 giây.
- Một region có thể bị partition trong 10 phút.

### Phần A — Phân loại lỗi

Cho danh sách:
1. Connect refused trước khi send.
2. 429 Retry-After: 2.
3. 503 trong lúc bầu leader.
4. 504 sau khi request reserve stock đã gửi.
5. 400 invalid quantity.
6. 409 version conflict.
7. ConditionalCheckFailed vì slot đã giữ.
8. Quorum unavailable 10 phút.
9. Client thread interrupted.
10. Search GET trả dữ liệu cũ hơn source.

Với từng lỗi, chỉ ra:
- Transient/permanent/unknown?
- Retry có an toàn không?
- Có cần operationId/ledger?
- Có thể giải bằng backoff không?
- Khi hết budget cần báo gì?

### Phần B — Tính lịch backoff

Giả sử:
- Base delay = 100 ms.
- Cap delay = 800 ms.
- Max attempts = 5 (gồm lần đầu).

1. Tính các capped exponential delays sau những lần thất bại.
2. Tính phạm vi full jitter cho từng delay.
3. Tính phạm vi equal jitter.
4. So sánh kỳ vọng chờ mỗi bước.
5. Giải thích vì sao no-jitter khiến hàng nghìn client đồng bộ.

### Phần C — Tính tổng thời gian

Giả sử 4 attempts, mỗi attempt có timeout 500 ms, backoff không jitter giữa chúng là 100, 200, 400 ms.

- Tính worst-case lý tưởng tổng thời gian.
- Với deadline 2 giây, có thể dùng hết 4 attempts không?
- Nếu attempt đầu tốn 900 ms vì callback không tôn trọng timeout, policy có còn đúng không?
- Vì sao cần monotonic elapsed deadline và per-attempt timeout thực thi ở SDK?

### Phần D — Tính retry amplification

Có 12.000 original requests/s. Trong một outage, tất cả requests dùng hết 4 attempts.

1. Giới hạn offered backend attempts/s theo mô hình cùng cửa sổ là bao nhiêu?
2. Nếu backend chịu 25.000 attempts/s, hệ có thể bị overload không?
3. Thêm full jitter có tự giảm tổng 48.000 attempts không?
4. Một retry budget 10% originals giới hạn added retry traffic xấp xỉ ra sao?
5. Tại sao một outage tương quan khác lỗi độc lập p=0,2?

**Gợi ý:** Với 4 attempts, giới hạn xấu đơn giản là **48.000 attempts** cho **12.000 original logical requests** cùng cohort. Jitter đổi thời điểm gửi; budget mới hạn chế tổng số retries.

### Phần E — Mất ACK sau commit

OP-101 đã reserve thành công, nhưng service mất ACK. Client retry:
- Tại sao dùng OP-102 sẽ sai?
- Thiết kế OperationLedger + fingerprint ra sao?
- Phải làm gì nếu ledger ghi riêng sau reserve?
- GET search ở EU chưa thấy OP-101 có chứng minh chưa commit không?
- UI nên hiển thị COMMITTED, REJECTED hay UNKNOWN/PENDING?

### Phần F — Retry theo loại thao tác

Thiết kế policy cho:
- Point GET eventual.
- Strong read sau write.
- Conditional room-slot reserve.
- Update version=17 bị conflict.
- Event append theo eventId.
- Payment capture.
- Full scan report.
- Background 1 triệu event import.

Mỗi policy cần:
- Retryable condition.
- Idempotency guard.
- Max attempts.
- Max elapsed.
- Backoff/jitter.
- Circuit/budget.
- Outcome khi hết budget.

### Phần G — Java

Từ ví dụ BoundedRetry:
1. Chỉ ra chỗ kiểm tra cancellation.
2. Vì sao callback phải tôn trọng perAttemptBudget?
3. Bổ sung retry budget và Retry-After.
4. Đặt operationId ở ngoài retry loop.
5. Thiết kế một test với ThreadLocalRandom được thay bằng deterministic random source khi cần kiểm soát timing trong unit tests.
6. Không dùng Thread.sleep trong event loop xử lý hàng nghìn connections.

### Phần H — Retry nhiều tầng

Giả sử:
- Mobile 3 attempts.
- Gateway 2 attempts.
- Service 3 attempts.
- SDK 4 attempts.

Tính worst-case nested amplification:

\[
3\times2\times3\times4=72
\]

Nếu một original action có thể tạo 72 calls, làm sao phân quyền retry theo tầng và chia sẻ deadline? Tầng nào nên sở hữu **idempotency và business outcome**? Tầng nào nên sở hữu **topology reconnect**?

### Phần I — Fault injection

Thiết kế test gồm:
1. Leader election 500 ms.
2. Minority partition 10 phút.
3. Throttling 429 với Retry-After.
4. Burst đồng thời 10.000 clients.
5. ACK lost after DB commit.
6. CAS conflicts liên tục.
7. Cache outage và stampede.
8. Search index lag 15 giây.
9. SDK ẩn retry 3 lần.
10. Client cancel trong lúc sleep.
11. One tenant flood retries.
12. Recovery và queue drain.

Với từng test, đặt tiêu chí pass/fail về:
- Correctness.
- Deadline.
- Total attempts.
- p99.
- Retry budget.
- Operation UNKNOWN.
- Recovery time.

### Phần J — Phản biện thiết kế

Một đồng nghiệp đề xuất:

> “Cứ retry 10 lần không sleep vì lỗi NoSQL thường tự hết. POST tạo order có transaction nên cứ tạo UUID mới mỗi lần cho chắc. Khi timeout thì coi như thất bại để người dùng bấm lại. Nếu tất cả client cùng retry thì backend autoscale sẽ xử lý.”

Hãy phản biện bằng:
- Retry storms và amplification.
- Capped exponential backoff + jitter.
- Attempts/deadline/budget.
- UNKNOWN commit và operationId idempotency.
- Điều kiện không có quorum.
- Khả năng autoscaling có độ trễ và hot partition không tự được chia.
- Tracing/metrics/fault injection cần thiết.

### Hướng giải

Một hệ khả thi có thể:
- **Retry** chỉ lỗi transient đã phân loại, và chỉ replay write khi có **operationId/atomic guard**.
- Giới hạn attempts, elapsed deadline, per-attempt timeout và shared budget.
- Dùng capped exponential backoff với **full jitter**, tôn trọng Retry-After khi phù hợp.
- Cho circuit breaker/load shedding ngăn retry storm trong outage kéo dài.
- Giữ trạng thái UNKNOWN nếu commit ACK mất và **reconcile** theo authoritative ledger.
- Tách search/eventual reads khỏi quyết định booking/payment.
- Kiểm chứng trên lỗi **tương quan**, không chỉ random failure.

## 40. Checklist áp dụng retry an toàn vào production

Trước khi bật retry cho một NoSQL operation, cần trả lời:

1. **Có phân loại transient, permanent và UNKNOWN rõ không?**
2. **Operation có side effect không?**
3. **Nếu có, replay được bảo vệ bằng idempotency key và atomic ledger không?**
4. **OperationId có giữ nguyên qua HTTP, gateway, service và SDK không?**
5. **Same key + different payload có bị từ chối không?**
6. **Ledger retention có dài đủ với mọi retry workflow không?**
7. **Conditional update có được hiểu đúng là khác idempotency không?**
8. **Max attempts đếm bao gồm attempt đầu chưa?**
9. **Max elapsed và end-to-end deadline có được áp đồng thời không?**
10. **Per-attempt timeout có thực sự được underlying I/O tôn trọng không?**
11. **Client cancel/Thread interrupt có dừng retries mới không?**
12. **Backoff có trần và tránh overflow không?**
13. **Có jitter để giảm thundering herd không?**
14. **Retry-After được parse/clamp/honor đúng không?**
15. **Có retry budget toàn hệ hoặc theo failure domain không?**
16. **Có admission rate và concurrency bulkhead không?**
17. **Circuit breaker có scope theo shard/cell/region phù hợp không?**
18. **Có phát hiện SDK/gateway/service retries chồng nhau không?**
19. **Có tránh hedging non-idempotent writes không?**
20. **Timeout sau gửi có được biểu diễn UNKNOWN thay vì auto rollback không?**
21. **Có API hoặc workflow để tra/reconcile operation outcome không?**
22. **Read verification có dùng authoritative/appropriate consistency mode không?**
23. **Có ngăn retry nhanh khi mất quorum kéo dài không?**
24. **Có phân biệt version conflict với transient system failure không?**
25. **Batch import có checkpoint và idempotency riêng không?**
26. **Có theo dõi retry amplification và original logical QPS không?**
27. **Có metrics p99/error budget cả successful lẫn failed requests không?**
28. **Có đo tác động retry tới tenant khác và backend recovery không?**
29. **Có fault injection lost ACK, partition và correlated outage chưa?**
30. **Có runbook giảm tải, mở circuit dần và reconcile dữ liệu không?**

**Kết luận:** Trong NoSQL phân tán, **thử lại có giới hạn** là cách đối phó những lỗi tạm thời nhưng chỉ an toàn khi được đặt trong **deadline, retry budget và hợp đồng idempotency**. **Exponential backoff** giúp giảm nhịp retry khi lỗi kéo dài; **jitter** phá sự đồng bộ của nhiều client cùng thất bại; **circuit breaker, admission control và bulkheads** giúp ngăn retry storm ăn hết tài nguyên khi backend chưa phục hồi. Tuy nhiên, **không thuật toán chờ nào biến một write không idempotent thành an toàn**, và **timeout không chứng minh transaction rollback**. Hãy giữ nguyên operationId, đối soát trạng thái UNKNOWN ở nguồn có thẩm quyền, đo **attempt amplification, p99, error rate và business invariants**, rồi kiểm chứng chính sách bằng fault injection có phân vùng, leader election, throttle và mất ACK sau commit.
