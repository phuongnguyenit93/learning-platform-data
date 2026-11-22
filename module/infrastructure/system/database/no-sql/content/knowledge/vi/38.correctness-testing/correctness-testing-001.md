# Chuyển yêu cầu nghiệp vụ thành bất biến có thể tự động kiểm tra

## 1. Mở đầu: “Không được bán quá số vé” có phải là một bài kiểm thử?

Một hệ thống đặt vé dùng Java và một cơ sở dữ liệu NoSQL. Product owner yêu cầu:

> Một sự kiện có 100 vé thì hệ thống không được bán quá 100 vé, kể cả khi nhiều khách đặt cùng lúc.

Đội phát triển viết một test:

~~~java
assertEquals(100, event.getCapacity());
~~~

Test chạy xanh, nhưng nó chỉ kiểm **giá trị cấu hình**, không kiểm hệ thống có bán vượt hay không. Một test khác chạy 100 requests tuần tự cũng xanh, nhưng production có 2.000 requests đồng thời; hai requests có thể cùng đọc “còn một vé” rồi cùng bán.

Để biến yêu cầu này thành thứ có thể tự động xác minh, phải làm rõ:

- **Đối tượng:** một sự kiện hay toàn hệ thống?
- **Đơn vị:** một vé, một ghế hay một yêu cầu đặt vé có số lượng \(q\)?
- **Trạng thái:** vé còn trống, đang giữ chỗ, đã bán, bị hủy, hoàn tiền?
- **Điểm commit:** khi database xác nhận giữ chỗ, khi thanh toán thành công hay khi phát hành vé?
- **Nguồn sự thật:** bản ghi inventory, reservations ledger hay tổng các orders?
- **Bất biến:** điều gì **không được sai ở bất kỳ trạng thái hợp lệ nào**?
- **Quan sát:** lấy bằng chứng bằng query nào, ở consistency level nào?
- **Tải và lỗi:** điều gì phải đúng khi có concurrency, timeout, retry, leader failover, CDC trễ và restore?

Một đặc tả có thể là:

\[
\forall e,\quad 0 \le \operatorname{available}(e)
\]

và, nếu số lượng vé cố định và mỗi vé chỉ ở đúng một trạng thái:

\[
\operatorname{available}(e)
+\operatorname{held}(e)
+\operatorname{sold}(e)
= \operatorname{capacity}(e).
\]

Đây mới là **ứng viên bất biến**. Phải tiếp tục xác định semantics của `held`, `sold`, `cancelled`, `expired` và các nguồn dữ liệu trước khi dùng nó như test oracle.

Bài học **“Chuyển yêu cầu nghiệp vụ thành bất biến có thể tự động kiểm tra”** thuộc chương **“Kiểm thử tính đúng”** trong module **Database No SQL**. Trọng tâm là một quy trình có thể áp dụng cho MongoDB, Cassandra, DynamoDB, Redis, Couchbase, các read models và nhiều hệ thống NoSQL phân tán khác nhau.

### Mục tiêu học tập

Sau bài học, bạn có thể:

1. Biến yêu cầu tự nhiên thành **điều kiện trước, điều kiện sau và bất biến trạng thái/lịch sử**.
2. Phân biệt **safety property**, **liveness property**, SLO và giả định môi trường.
3. Xác định đúng **phạm vi nguyên tử, điểm commit, đối tượng kiểm chứng và thời gian quan sát**.
4. Thiết kế bất biến cho tồn kho, giữ chỗ, thanh toán, uniqueness, idempotency, state machine, quota và tenant isolation.
5. Xác định khi nào một test tuần tự không chứng minh được an toàn dưới concurrency.
6. Viết **test oracle độc lập** thay vì gọi lại cùng logic production đang cần kiểm.
7. Tổ chức unit, property-based, state-machine, integration, concurrency và fault-injection tests.
8. Dùng Java 17 và JUnit 5 mô tả, kiểm tra và tạo dữ liệu test cho bất biến.
9. Phân biệt trạng thái **chưa hội tụ** với trạng thái **vi phạm bất biến** trong hệ eventual consistency.
10. Lập hồ sơ evidence, seed, lịch sử thao tác, witness và điều kiện go/no-go cho những invariant quan trọng.

---

## 2. Từ yêu cầu tự nhiên sang đặc tả kiểm chứng

Một câu nghiệp vụ thường thiếu định nghĩa về thời điểm, đối tượng hoặc điều kiện ngoại lệ.

| Câu nghiệp vụ | Câu hỏi phải làm rõ | Ứng viên đặc tả |
|---|---|---|
| Không bán quá số vé | Giữ chỗ có chiếm vé? Hủy đơn trả vé khi nào? | `available >= 0`, conservation |
| Không thu tiền hai lần | Hai retries cùng request ID hay hai đơn khác nhau? | At most one successful charge per business operation |
| Không cho tenant A đọc dữ liệu B | API nào? Admin exceptions? | Authorized result set subset of tenant scope |
| Trạng thái đơn không đi ngược | Refund/cancel có ngoại lệ? | Only allowed state transitions |
| Đã ghi thành công phải đọc lại được | Từ replica nào? Sau bao lâu? | Read-your-writes hoặc linearizable read contract |
| Không phát sự kiện trùng | Duplicate deliveries có được? | Deduped *side effect*, không nhất thiết exactly-once delivery |
| Token hết hạn không được dùng | Dựa vào wall clock nào? | Authorization rejects when `now >= expiresAt` |
| Dữ liệu xóa phải biến mất | Cache/index/backup cũng có? | No unauthorized visibility after accepted delete boundary |
| Số dư không âm | Có overdraft hợp lệ? | `balance >= overdraftLimit` |
| Mỗi user chỉ có một primary email | Phạm vi tenant? soft-deleted rows? | Uniqueness over active scoped records |

### 2.1. Viết lại thành mẫu kiểm chứng

Một mẫu hữu ích:

~~~text
Given:
  Trạng thái ban đầu và các giả định.

When:
  Một hoặc nhiều thao tác được gọi, có thể đồng thời/lặp/lỗi.

Then:
  Điều gì phải luôn đúng, tại phạm vi commit nào.

Eventually:
  Điều gì phải đúng về sau, nếu điều kiện môi trường được đáp ứng.

Evidence:
  Dùng nguồn dữ liệu, lịch sử và test oracle nào để xác nhận.
~~~

### 2.2. Tránh đặc tả chỉ lặp lại cách triển khai

“Database phải có `conditionalWrite=true`” là một yêu cầu implementation. “Hai yêu cầu đồng thời tranh một vé không được cùng được công nhận thành công” là yêu cầu **observable correctness**.

Cơ chế có thể là transaction, CAS, LWT, script nguyên tử, một writer tuần tự, ledger hay coordinator. Bất biến phải đứng độc lập với lựa chọn đó.

---

## 3. Phân biệt bất biến trạng thái và thuộc tính lịch sử

### 3.1. State invariant

Một predicate phải đúng trên **mọi trạng thái hợp lệ đã commit**.

\[
I(S)=\text{true}.
\]

Ví dụ:

\[
I(S)\equiv
\operatorname{stockAvailable}(S)\ge0.
\]

Nếu một trạng thái committed có `available = -1`, bất biến bị phá.

### 3.2. Transition property

Một thao tác từ trạng thái \(S\) sang \(S'\) phải thoả:

\[
P(S,op)\Rightarrow Q(S,S',result).
\]

Ví dụ, nếu `Reserve(q)` thành công, số lượng available phải giảm đúng \(q\), số lượng held tăng đúng \(q\), và `q > 0`.

### 3.3. History property

Một thuộc tính cần nhìn **chuỗi thao tác và kết quả**, không thể xác minh từ snapshot hiện tại.

Ví dụ “một request ID chỉ tạo một payment charge” cần xem toàn bộ lịch sử request/charge/dedup hoặc ledger có bảo đảm đầy đủ.

### 3.4. Quan hệ giữa ba loại

Một hệ có thể có snapshot cuối `stockAvailable = 0` (hợp lệ) dù trong quá trình đã từng bán vượt rồi điều chỉnh lại. Kiểm snapshot cuối không chứng minh không từng vi phạm **safety**.

### 3.5. Biểu diễn tổng quát

~~~text
S0 --op1--> S1 --op2--> S2 --op3--> S3

State invariant:      I(S0), I(S1), I(S2), I(S3)
Transition contract:  Q(Si, op, Si+1)
History property:     H([invoke, result, ...]) == valid
~~~

Bất biến cần kiểm tại những **logical commit points**; không nhất thiết mọi bước memory nội bộ trung gian của một transaction phải có hình dạng dữ liệu giống committed state.

---

## 4. Safety và liveness là hai câu hỏi khác nhau

### 4.1. Safety: “Không bao giờ xảy ra điều xấu”

Ví dụ:

- Không oversell.
- Không double charge.
- Không đọc dữ liệu của tenant khác.
- Không có hai owners cùng giữ lease hợp lệ cho cùng một tài nguyên khi downstream đã áp fencing.
- Không áp event version thấp đè lên version cao.
- Không trả quyền đã bị revoke sau điểm có hiệu lực được định nghĩa.

Safety violation thường có **finite counterexample**: một lịch sử đủ ngắn chứng minh điều sai đã xảy ra.

### 4.2. Liveness: “Cuối cùng điều tốt phải xảy ra”

Ví dụ:

- Đơn đã được chấp nhận cuối cùng chuyển sang trạng thái kết thúc hoặc được escalated.
- Event trong outbox cuối cùng được xử lý nếu broker/consumer hồi phục.
- Replica cuối cùng bắt kịp dữ liệu trong điều kiện mạng/nguồn ổn định.
- Hold hết hạn cuối cùng được release.

### 4.3. Liveness cần giả định môi trường

Nếu mạng mất mãi mãi, một hệ không thể vừa chờ phục hồi vừa bảo đảm luôn hoàn tất ngay. Đặc tả phải ghi:

> “Nếu mạng ổn định trở lại, worker được chạy đủ thời gian, không có lỗi vĩnh viễn và nguồn dữ liệu còn nguyên, mọi outbox event hợp lệ sẽ được xử lý trong thời gian mục tiêu \(T\).”

### 4.4. SLO không thay safety

Một API p99 40 ms nhưng bán vượt kho vẫn sai. Một API từ chối một phần requests để giữ an toàn có thể không đạt availability SLO, song vẫn giữ đúng bất biến.

### 4.5. Safety có thể ưu tiên trước availability

Khi không đủ quorum để biết inventory hiện tại, hệ có thể **fail closed** với thao tác giữ chỗ thay vì chấp nhận bán vượt. Đây là trade-off phải được business duyệt, không phải lý do bỏ kiểm tra.

---

## 5. Mô hình trạng thái, hành động và điều kiện cho phép

Trước khi viết test, định nghĩa:

\[
\mathcal{M}=(S_0, A, T, I)
\]

trong đó:

- \(S_0\): các trạng thái ban đầu hợp lệ.
- \(A\): tập commands/actions hợp lệ và không hợp lệ.
- \(T(S,a)\): transition khi thực hiện action.
- \(I(S)\): tập bất biến cần giữ.

Ví dụ kho vé:

~~~text
State:
  capacity
  available
  held
  sold
  reservation[id] -> status, quantity, version
  processedRequest[id] -> payloadHash, result

Actions:
  reserve(requestId, quantity)
  confirm(reservationId, paymentId)
  expire(reservationId, observedAt)
  cancel(reservationId)
  retry(requestId)
  restock(quantity)
~~~

### 5.1. Định nghĩa “thành công”

`reserve` thành công nghĩa tạo một hold có thể thực thi, không chỉ queue đã nhận request. Nếu API trả `202 Accepted`, phải phân biệt accepted-for-processing và reservation đã committed.

### 5.2. Định nghĩa điều kiện đầu vào

`quantity > 0`, `requestId` không trống, inventory thuộc tenant đúng, reservation không ở trạng thái terminal.

### 5.3. Định nghĩa trạng thái lỗi

- `REJECTED_INSUFFICIENT_STOCK`.
- `REJECTED_INVALID_INPUT`.
- `REJECTED_DUPLICATE_WITH_DIFFERENT_PAYLOAD`.
- `CONFLICT_STALE_VERSION`.
- `UNKNOWN_OUTCOME`.

Một timeout là **observation**, không phải phép chứng minh transaction chưa commit.

---

## 6. Ví dụ xuyên suốt: bất biến cho giữ chỗ và bán vé

Giả sử `capacity` cố định tại thời điểm kiểm, không xét hoàn trả đã làm đổi capacity.

Ký hiệu:

- \(A\): số vé còn có thể giữ.
- \(H\): số vé trong reservations active `HELD`.
- \(S\): số vé đã xác nhận bán `CONFIRMED`.
- \(C\): tổng số vé được phép bán.

Một tập bất biến:

\[
A\ge0,\quad H\ge0,\quad S\ge0.
\]

\[
A+H+S=C.
\]

Và:

\[
\forall r,\quad quantity(r)>0.
\]

### 6.1. Chỉ giữ chỗ mới tiêu thụ available

~~~text
Before:
  C=100, A=100, H=0, S=0

reserve(3) succeeds:
  C=100, A=97, H=3, S=0

confirm(3) succeeds:
  C=100, A=97, H=0, S=3
~~~

### 6.2. Hủy hold

~~~text
Before:
  C=100, A=97, H=3, S=0

cancel(active hold of 3):
  C=100, A=100, H=0, S=0
~~~

### 6.3. Hết hạn hold

Thời gian hết hạn tự nó không đồng nghĩa cả hệ đã giải phóng inventory. Phải định nghĩa atomic transition `HELD -> EXPIRED` và tăng available đúng một lần.

### 6.4. Đổi capacity

Nếu business bổ sung ghế, `C` thay đổi có chủ đích và công thức vẫn phải giữ; nếu giảm capacity xuống dưới `held+sold` thì phải từ chối hoặc có quy trình business đặc biệt.

### 6.5. Khi nào conservation formula không đủ?

Nếu có waitlist, refund, transferred tickets, reserved-for-admin, gift seats hoặc inventory đa bucket, phải mở rộng mô hình trạng thái. Không ép mọi state vào \(A+H+S=C\) nếu business có categories khác.

---

## 7. Viết precondition và postcondition cho `reserve`

### 7.1. Precondition thành công

\[
q>0
\land
\operatorname{available}\ge q
\land
\operatorname{requestIdValid}.
\]

### 7.2. Postcondition khi thành công

\[
A'=A-q,\quad H'=H+q,\quad S'=S.
\]

Và tồn tại chính xác một reservation active liên kết `requestId`.

### 7.3. Postcondition khi không đủ số lượng

Nếu trả lỗi `INSUFFICIENT_STOCK` dứt khoát, **không được tạo hold** cho request đó. Lưu ý một số hệ có thể commit audit record về attempt thất bại; ta chỉ ràng buộc phần business state cần bảo vệ.

### 7.4. Retries cùng request

Nếu client gửi lại cùng `requestId` với payload hash trùng, trả cùng logical outcome/receipt; không trừ kho lần hai.

### 7.5. Duplicate ID nhưng payload khác

Nếu cùng `requestId` nhưng quantity khác, phải trả explicit conflict, không âm thầm gán lại dữ liệu để tạo một reservation khác.

---

## 8. Tại sao test tuần tự không chứng minh được concurrency safety?

Giả sử chỉ còn 1 vé:

~~~mermaid
sequenceDiagram
    participant A as Client A
    participant DB as NoSQL
    participant B as Client B
    A->>DB: Read available=1
    B->>DB: Read available=1
    A->>DB: Write available=0; create hold A
    B->>DB: Write available=0; create hold B
    Note over DB: Two successful holds, one physical ticket
~~~

Snapshot counter có thể vẫn là 0; nhưng reservation ledger chứa **hai holds**. Nếu test chỉ assert `available >= 0`, nó bỏ sót oversell.

### 8.1. Test đúng phải đọc nhiều nguồn sự thật

- Kiểm inventory counter.
- Kiểm số active holds + sold.
- Kiểm uniqueness của allocated seat.
- Kiểm chỉ một yêu cầu tranh vé được success.
- Kiểm retries không nhân effect.

### 8.2. Đồng thời không phải chỉ tạo nhiều threads

Cần cố gắng ép lịch interleaving có nguy cơ race, dùng start barriers, fault injection, delayed responses và test chạy đủ repetitions dưới database thật.

### 8.3. Không mặc định atomicity từ API shape

Một operation gồm `GET` rồi `PUT` trên hai calls không thành atomic transaction chỉ vì được bọc trong một method Java `synchronized` trên một process. Nhiều replicas/instances Java không chia sẻ JVM lock.

### 8.4. Giải pháp phải nằm ở ranh giới phù hợp

Một atomic conditional update/transaction/serial executor theo partition/ledger với unique constraint có thể bảo vệ invariant. Cơ chế cụ thể tùy database và data model.

---

## 9. Uniqueness: “không có hai tài khoản cùng email” cần phạm vi

Yêu cầu “email là duy nhất” còn thiếu:

- Email duy nhất trên toàn hệ hay trong mỗi tenant?
- Có phân biệt hoa/thường không?
- Có Unicode/IDN normalization không?
- Tài khoản đã soft delete có chiếm uniqueness không?
- Email chưa verified có được giữ chỗ không?
- Thời gian giữa tạo account và gửi verification email có window?
- Multiple write regions có conflict behavior thế nào?

### 9.1. Phát biểu định lượng

Ví dụ, với tập accounts active:

\[
\forall a,b\in ActiveAccounts:
\]

\[
tenant(a)=tenant(b)
\land
normalizedEmail(a)=normalizedEmail(b)
\Rightarrow a.id=b.id.
\]

### 9.2. “Đếm trước rồi insert” có race

Hai writers cùng thấy `count=0` rồi cùng insert. Cần constraint/conditional create/unique guard trong transaction boundary hoặc một ownership protocol an toàn.

### 9.3. Uniqueness claim khác thực tế source

Nếu source đã có duplicates, migration không tự “chữa” bằng ghi đè. Đánh dấu conflicts và owner remediation.

### 9.4. Kiểm thử

- Hai creates đồng thời cùng normalized key.
- Case changes.
- Delete/re-register.
- Retry after timeout.
- Two regions/conflicting writes.
- Unique guard release khi account bị hủy.

---

## 10. Idempotency: một yêu cầu nghiệp vụ, không phải một HTTP request

Một payment request có thể có:

~~~text
POST /charge
Idempotency-Key: charge-order-123

Attempt 1 -> timeout
Attempt 2 -> retry
Attempt 3 -> retry after client reconnect
~~~

Bất biến ví dụ:

\[
\#\{\text{successful external charges for operation }k\}\le1.
\]

### 10.1. At-most-once *effect* khác at-most-once delivery

Broker, HTTP clients và workers có thể gửi thông điệp nhiều lần. Hệ phải chống duplicate effect bằng stable key/ledger hoặc provider hỗ trợ idempotency.

### 10.2. “Cùng key” phải gắn payload

Dùng `requestId -> payloadHash, logicalResult`, tránh chấp nhận một key cũ với số tiền mới.

### 10.3. TTL của ledger

Nếu idempotency key chỉ sống 1 giờ nhưng provider có thể retry sau 48 giờ, bất biến không còn được đảm bảo trong khoảng dài. Retention của ledger phải phù hợp business replay horizon.

### 10.4. Sau unknown outcome

Không coi `timeout` là thất bại xác định. Thử read authoritative request status/provider receipt trước khi gửi action có side effect mới.

### 10.5. Test

Đặt fault đúng sau commit nhưng trước ACK, gửi lại cùng requestId, đối chiếu external ledger: số charge tối đa một và kết quả logical ổn định.

---

## 11. State machine: không cho trạng thái đi theo đường cấm

Ví dụ đơn hàng:

~~~mermaid
stateDiagram-v2
    [*] --> CREATED
    CREATED --> RESERVED
    RESERVED --> PAID
    RESERVED --> CANCELLED
    PAID --> FULFILLED
    PAID --> REFUND_PENDING
    REFUND_PENDING --> REFUNDED
    CREATED --> CANCELLED
~~~

Nếu business không cho `FULFILLED -> CREATED`, phải kiểm history transitions, không chỉ hiện tại `status` thuộc enum hợp lệ.

### 11.1. Invariant của state machine

\[
(status_t,status_{t+1})\in AllowedTransitions.
\]

### 11.2. Version luôn tăng khi successful mutation

Một rule:

\[
version_{t+1}=version_t+1
\]

cho mỗi commit thành công có làm đổi trạng thái theo contract.

### 11.3. Retry cùng command không tăng version lần hai

Một idempotent retry không phải transition nghiệp vụ mới.

### 11.4. Out-of-order CDC

Một event `status=PAID, version=8` không được bị event `status=RESERVED, version=7` đến muộn ghi đè.

### 11.5. Chuỗi audit giúp tìm lỗi tạm thời

Snapshot cuối có `REFUNDED` hợp lệ chưa chứng minh rằng trong quá trình chưa từng đi qua trạng thái không cho phép.

---

## 12. Bất biến về quyền truy cập và tenant isolation

Giả sử API `GET /orders/{orderId}` nhận `tenantId` từ **authenticated context**.

Một safety property:

\[
\forall responseRecord,\quad
tenant(responseRecord)=tenant(authenticatedPrincipal)
\]

trừ các trường hợp được policy cho phép rõ ràng.

### 12.1. Không tin tenantId trong body/query một mình

Một request có thể gửi `tenantId=B` dù principal thuộc A. Phải dựa vào authorization context, không chỉ filter của caller.

### 12.2. Test âm tính quan trọng

- Tenant A đọc ID của B.
- ID trùng namespace giữa tenants.
- Cursor/pagination token của B được dùng bởi A.
- Search index trả bản ghi của B.
- Cache key không có tenant prefix.
- Export/batch endpoint bỏ tenant guard.
- Restore/migration làm mất tenant field.
- Permissions bị revoke rồi cache vẫn cấp quyền.

### 12.3. Kiểm cả side effects

Không chỉ response không lộ dữ liệu: caller A không được sửa trạng thái hay tạo event tác động tới dữ liệu B.

### 12.4. Bảo mật là bất biến nghiệp vụ

Một hệ có p99 tốt và dữ liệu đủ nhưng lộ dữ liệu cross-tenant là sai nghiêm trọng; test phải **block cutover/release**.

---

## 13. Bất biến về thời gian và TTL

“Session hết hạn lúc 10:00” không đồng nghĩa record bị xóa vật lý đúng 10:00.

### 13.1. Hợp đồng đáng kiểm

Nếu thời gian đánh giá đáng tin:

\[
now \ge expiresAt
\Rightarrow
\operatorname{authorizeSession}=false.
\]

### 13.2. Test dùng clock điều khiển được

Với Java, inject `Clock` thay vì đọc `Instant.now()` trong mọi nhánh. Test boundaries:

~~~text
expiresAt - 1 ms => valid if policy allows
expiresAt        => expired
expiresAt + 1 ms => expired
~~~

### 13.3. Clock skew và lease

Trong cụm phân tán, wall-clock giữa nodes có thể lệch; nếu một lease/expiry bảo vệ side effect, chỉ TTL không đủ để ngăn stale owner tiếp tục ghi. Có thể cần fencing token/epoch tại destination.

### 13.4. Liveness của cleanup

“Expired record cuối cùng bị dọn” là liveness. Nó không thay safety “expired token không được chấp nhận”.

### 13.5. Restore từ backup cũ

Record đã expired/revoked trước sự cố không được coi hợp lệ chỉ vì backup chứa lại nó. Verify theo expiration/revocation authority khi phục hồi.

---

## 14. Bất biến về số tiền và ledger

Một hệ thanh toán có thể giữ:

~~~text
Order amount
Captured amount
Refunded amount
Outstanding amount
~~~

Những predicate cần business xác nhận:

\[
capturedAmount\ge0,\quad refundedAmount\ge0,
\]

\[
refundedAmount\le capturedAmount
\]

trong mô hình không có reversal/chargeback đặc biệt.

### 14.1. Không dùng `double` cho tiền chính xác

Dùng minor units nguyên hoặc `BigDecimal` với currency scale/rounding policy đã chốt.

### 14.2. Ledger là nguồn sự thật

Một cache `order.paid=true` không đủ để chứng minh capture thực sự thành công ở provider. Cần durable receipt và reconciliation.

### 14.3. Outbox và external effects

Một DB transaction có thể commit outbox intent cùng order state, nhưng gửi request tới payment provider bên ngoài có thể thất bại/unknown. Bất biến cross-system cần provider idempotency key và reconciliation.

### 14.4. Kiểm bằng nguồn độc lập

Đối chiếu DB ledger với provider receipts, không chỉ đọc hai projections được xây từ cùng một bug.

---

## 15. Khi bất biến cần nhiều collections hoặc nhiều systems

Giả sử:

~~~text
orders table
inventory table
payment ledger
outbox events
search projection
~~~

### 15.1. Ranh giới atomicity

Một transaction chỉ bảo vệ những writes **nằm trong transaction boundary được engine hỗ trợ**. Không mặc định có atomicity khi writes vượt hai DBs hoặc external provider.

### 15.2. Safety có thể cần thiết kế khác

Một invariant “không bán quá tồn kho” có thể bảo vệ ở inventory authority bằng reservation token; search projection eventual không cần tham gia commit của inventory.

### 15.3. Eventual projections

Với search index có thể tạm lag, không kiểm `search == orders` ngay sau mọi write nếu contract cho phép eventual consistency. Thay bằng:

> Khi CDC đã xử lý tới source watermark \(w\), projection phải phản ánh tất cả updates trong phạm vi \(w\) theo mapping đã định nghĩa.

### 15.4. Cross-system transactions

Nếu phải có exactly-once business effect qua external systems, thường dùng idempotent commands, outbox/inbox, saga và reconciliation; **không** đơn giản test một atomic DB transaction rồi kết luận external effects an toàn.

---

## 16. Viết một Invariant Card

Để người khác có thể tự động hóa, mỗi yêu cầu có thể thành một thẻ:

~~~yaml
id: INV-INVENTORY-001
name: no-oversell
owner: ticket-domain
severity: critical
scope:
  entity: event
  tenant: any
  dataAuthority: inventory-ledger
assumptions:
  - capacity changes only via approved command
  - one seat belongs to one lifecycle bucket
predicate: "available >= 0 AND available + held + sold = capacity"
operations:
  - reserve
  - confirm
  - cancel
  - expire
evidence:
  - authoritative snapshot at consistent cut
  - ordered reservation command/result history
faultScenarios:
  - concurrent reserve on last seat
  - retry after commit-before-ACK timeout
  - primary failover
  - old CDC event after new event
passCriteria:
  - zero committed-state violations
  - no two successful holds for same physical seat
unknownPolicy: fail-test-and-investigate
~~~

### 16.1. Trường bắt buộc

- `id`, `owner`, `severity`.
- Định nghĩa state/hành động.
- Predicate và phạm vi.
- Giả định.
- Oracle/evidence.
- Thời điểm được đánh giá.
- Fault/concurrency scenarios.
- Hành vi khi dữ liệu đo không đầy đủ.
- Điều kiện PASS/FAIL/UNKNOWN.

### 16.2. Invariant Card là đặc tả, không phải phép đo

Một predicate viết rõ nhưng backend không expose đủ dữ liệu để kiểm phải có kế hoạch instrument hoặc query/ledger riêng.

### 16.3. Không lấy query làm nguồn duy nhất nếu query có thể stale

Một snapshot đọc từ replica eventual có thể hiển thị counter cũ trong khi ledger mới, tạo false violation. Cần consistency snapshot hoặc watermark/versions để so cùng mốc.

---

## 17. Biến bất biến thành test oracle

**Test oracle** là cơ chế quyết định kết quả quan sát có đúng với đặc tả không.

### 17.1. Oracle trực tiếp

Một query trên authoritative state với snapshot consistent để tính:

\[
A+H+S=C.
\]

### 17.2. Oracle theo lịch sử

Thu `invoke`, `response`, `commit evidence`, request ID, version rồi đánh giá có thể sắp các thao tác theo lịch sử hợp lệ hay không.

### 17.3. Oracle độc lập

Reference model nhỏ, viết bằng logic đơn giản và khác đường code production, làm tiêu chuẩn cho một phần quan sát.

### 17.4. Oracle theo kiểm chứng external

Đối soát payment provider receipts, inventory allocation hoặc audit records với DB.

### 17.5. Tránh “oracle là cùng repository vừa được kiểm”

Nếu implementation và oracle dùng cùng một bug trong mapping, test có thể xanh giả. Dùng invariant tính từ dữ liệu và history độc lập hoặc so hai nguồn đủ tin cậy.

### 17.6. Không có bằng chứng thì UNKNOWN

Nếu một node không truy vấn được hoặc CDC đã mất history cần kiểm, không tự trả PASS vì query hiện tại không thấy lỗi.

---

## 18. Định nghĩa điểm quan sát: trước, trong và sau transaction

### 18.1. Committed-state invariant

Bất biến được yêu cầu sau mỗi atomic commit, không bắt buộc trong mọi buffer nội bộ mà transaction không expose.

### 18.2. Operation-level postcondition

Một write thành công phải để lại effect theo contract, sau khi client quan sát được ACK trong mô hình đã định nghĩa.

### 18.3. Read visibility contract

Nếu strong read/RYW được yêu cầu, một read sau successful write phải thấy giá trị không cũ hơn theo session/consistency contract. Nếu eventual read được phép stale, test phải đánh giá đúng window.

### 18.4. Cross-shard snapshot

Query đồng thời nhiều shards có thể không là consistent snapshot. Cộng counters từ nhiều shards tại nhiều thời điểm rồi kiểm conservation có thể tạo false positive. Cần cut/transaction snapshot hoặc replay ledger.

### 18.5. Cutoff theo time không luôn đủ

Timestamp giữa nodes có thể skew; sequence/commit index/version/watermark của engine thường thích hợp hơn khi có cam kết semantics.

---

## 19. Unit test: kiểm pure invariant logic trước

Một hàm pure nhận snapshot đã kiểm chứng và trả violations giúp tách logic nghiệp vụ khỏi driver.

Ví dụ Java 17:

~~~java
import java.util.ArrayList;
import java.util.List;

public final class InventoryInvariants {

    public record State(
        long capacity,
        long available,
        long held,
        long sold
    ) {}

    public static List<String> violations(State state) {
        List<String> problems = new ArrayList<>();

        if (state.capacity() < 0) {
            problems.add("NEGATIVE_CAPACITY");
        }
        if (state.available() < 0) {
            problems.add("NEGATIVE_AVAILABLE");
        }
        if (state.held() < 0) {
            problems.add("NEGATIVE_HELD");
        }
        if (state.sold() < 0) {
            problems.add("NEGATIVE_SOLD");
        }

        try {
            long total = Math.addExact(
                Math.addExact(state.available(), state.held()),
                state.sold()
            );
            if (total != state.capacity()) {
                problems.add("CONSERVATION_VIOLATION");
            }
        } catch (ArithmeticException overflow) {
            problems.add("COUNTER_OVERFLOW");
        }

        return List.copyOf(problems);
    }
}
~~~

### 19.1. `Math.addExact` có ý nghĩa

Không để integer overflow khiến một tổng sai tình cờ trở thành giá trị có vẻ hợp lệ.

### 19.2. Không che dấu sai số

Đối với tồn kho nguyên, không dùng tolerance mơ hồ. Với decimal/float domain, tolerance/rounding phải được định nghĩa theo business contract.

### 19.3. Dữ liệu đầu vào phải là snapshot nhất quán

Hàm pure chỉ xác định tính đúng của số liệu **được truyền vào**, không chứng minh chúng được đọc cùng thời điểm hay từ authority.

### 19.4. Độ bao phủ

Nên kiểm boundary, số âm, tổng thiếu, quá nhiều, overflow và trạng thái hợp lệ.

---

## 20. JUnit 5: kiểm oracle với các trạng thái rõ ràng

~~~java
import static org.junit.jupiter.api.Assertions.*;
import org.junit.jupiter.api.Test;

public class InventoryInvariantsTest {

    @Test
    void freshInventoryIsValid() {
        var state = new InventoryInvariants.State(
            100, 100, 0, 0
        );
        assertTrue(
            InventoryInvariants.violations(state).isEmpty()
        );
    }

    @Test
    void heldAndSoldPreserveConservation() {
        var state = new InventoryInvariants.State(
            100, 72, 8, 20
        );
        assertTrue(
            InventoryInvariants.violations(state).isEmpty()
        );
    }

    @Test
    void negativeAvailableIsRejected() {
        var state = new InventoryInvariants.State(
            100, -1, 51, 50
        );
        assertTrue(
            InventoryInvariants.violations(state)
                .contains("NEGATIVE_AVAILABLE")
        );
    }

    @Test
    void twoHoldsForOneSeatBreakConservation() {
        var state = new InventoryInvariants.State(
            1, 0, 2, 0
        );
        assertTrue(
            InventoryInvariants.violations(state)
                .contains("CONSERVATION_VIOLATION")
        );
    }

    @Test
    void overflowingCountersAreRejected() {
        var state = new InventoryInvariants.State(
            10, Long.MAX_VALUE, 1, 1
        );
        assertTrue(
            InventoryInvariants.violations(state)
                .contains("COUNTER_OVERFLOW")
        );
    }
}
~~~

### 20.1. Đây là test của oracle

Nó cho biết predicate hoạt động theo ví dụ. **Chưa chứng minh** MongoDB/Cassandra/DynamoDB implementation giữ invariant dưới concurrent requests.

### 20.2. Test giá trị khác và trạng thái khác

Property-based tests có thể sinh hàng nghìn states hợp lệ/bất hợp lệ thay vì chỉ vài ví dụ cố định.

---

## 21. Reference model: oracle không phụ thuộc storage engine

Một **reference model** có thể là một bộ state thuần trong memory, xử lý commands **tuần tự** theo đặc tả.

~~~text
Model:
  available=1
  reservedIds={}

reserve("a"):
  succeeds; available=0; reservedIds={"a"}

reserve("b"):
  fails; available=0

retry("a"):
  returns existing outcome; available=0
~~~

### 21.1. Tại sao model phải nhỏ?

Mục tiêu là dễ hiểu, dễ review, ít bugs hơn implementation phân tán. Nếu model sao chép lại toàn bộ driver/repository logic thì không còn độc lập.

### 21.2. Model và system under test

Cho cùng chuỗi commands, đối chiếu logical outcomes; có thể bỏ qua internal timestamps hoặc fields không thuộc contract.

### 21.3. Model-based state-machine testing

Sinh chuỗi ngẫu nhiên:

~~~text
reserve -> retry -> expire -> confirm
reserve -> cancel -> retry
reserve -> concurrent reserve -> failover -> retry
~~~

Sau mỗi step, kiểm model state và business invariants.

### 21.4. Cần model time và failures

Một model không có TTL/timeout/unknown outcome sẽ không phát hiện lỗi ở các đường này.

---

## 22. Property-based testing: kiểm tính chất, không chỉ test case

Với property-based tests, ta sinh nhiều input/state/command sequences và kiểm một thuộc tính tổng quát.

### 22.1. Ví dụ cho reserve

Với `C >= 0`, `q > 0`:

- Nếu `q <= available`, reserve thành công và conservation giữ.
- Nếu `q > available`, reserve bị từ chối và số active holds không đổi.
- Retry cùng idempotency key không tăng allocated quantity.
- Cancel/expire cùng reservation nhiều lần chỉ release một lần.

### 22.2. Shrinking

Khi tìm ra lỗi sau 120 thao tác, framework có thể thu nhỏ thành lịch sử tối giản, ví dụ:

~~~text
capacity=1
reserve(A,1)
reserve(B,1) concurrently
both succeeded
~~~

Một counterexample ngắn rất giá trị cho điều tra.

### 22.3. Seed

Ghi random seed và versions để tái lập. Nếu không thể reproduce, vẫn phải lưu đủ trace và môi trường để phân tích.

### 22.4. Framework

Java có thể dùng jqwik, QuickTheories hoặc tự xây generator có kiểm soát. Cú pháp/phụ thuộc phụ thuộc version; ví dụ ở đây mô tả strategy, không gán một API framework cụ thể.

### 22.5. Không lẫn model invariant với database history

Sinh input ngẫu nhiên giỏi vẫn không chứng minh behavior khi quorum mất hoặc retries trong network partitions nếu không chạy trên hệ thật.

---

## 23. Metamorphic testing khi không có expected output đầy đủ

Một số phép chuyển đổi input phải giữ một quan hệ xác định, ngay cả khi ta không biết trước toàn bộ output.

Ví dụ:

- Thay thứ tự các requests độc lập của **hai sự kiện khác nhau** không đổi tổng sold per event.
- Gửi cùng một idempotent request nhiều lần không tăng số charges.
- Rebuild search projection từ authoritative source với cùng checkpoint cho ra logical result set tương đương.
- Chuyển Java app node sang region khác không làm cross-tenant authorization mất hiệu lực.

### 23.1. Chỉ áp quan hệ khi có giả định đúng

Không đổi thứ tự hai operations cùng order nếu state machine đòi thứ tự. Không kết luận các requests luôn giao hoán.

### 23.2. Không phải exact bytes comparison

Hai JSON maps có thứ tự fields khác nhau nhưng cùng logic có thể tương đương. Define canonicalization rõ.

---

## 24. Từ invariant đến property-based command generator

Một generator tốt không chỉ gọi `reserve(1)`:

~~~text
Create:
  capacity = 0, 1, 2, 100, max
  quantity = -1, 0, 1, available, available+1
  requestId = fresh, duplicate, duplicate-different-payload

Sequence:
  reserve
  retry
  confirm
  cancel
  expire
  restock

Concurrency:
  all reserve last seat
  cancel vs confirm
  expire vs confirm
  duplicate request arriving on multiple nodes

Failures:
  timeout before response
  client retry
  leader change
  replica isolation
  process crash
  CDC reordering
~~~

### 24.1. Invariants tại mỗi bước

Sau từng successful committed transition, kiểm conservation và uniqueness ở consistent snapshot.

### 24.2. Outcomes không xác định

Khi timeout, không tự thêm `FAIL` vào model; ghi `UNKNOWN` rồi reconcile bằng request ID.

### 24.3. Trạng thái không hợp lệ cũng phải được sinh

`quantity=0`, negative, overflow, unknown reservation, wrong tenant, expired token, stale version.

### 24.4. Giới hạn test

Một generator không bao phủ mọi interleaving; tăng chất lượng bằng targeted failure windows, scheduler hooks và model checking khi phù hợp.

---

## 25. Integration tests: chạy bất biến trên storage thật

### 25.1. Mục tiêu

Bảo đảm cơ chế atomicity/transaction/conditional write của database được dùng đúng, chứ không chỉ Java service tự giữ state trong memory.

### 25.2. Cấu trúc

~~~text
Test runner
  -> Real Java adapter
  -> Disposable test cluster
  -> Authoritative reads + event trace
  -> Independent invariant checker
~~~

### 25.3. Cô lập

Mỗi test có namespace/table/keyspace/tenant độc lập, idempotency IDs riêng và cleanup có kiểm soát.

### 25.4. Không dùng production data

Tạo synthetic records và test environments được phê duyệt. Với security tests, không sao chép secrets/PII vào test logs.

### 25.5. Đo đúng consistency

Nếu dùng một eventual read trên replica để kiểm counter, có thể đọc state chưa hội tụ. Dùng read concern/CL phù hợp, consistent snapshots hoặc versioned event history.

### 25.6. Cleanup cũng là test

Sau khi hủy hold, kiểm available được trả lại đúng một lần, không tạo orphan records/tombstones bất thường theo contract.

---

## 26. Concurrency test bằng barrier: cùng tranh một tài nguyên

Ví dụ Java 17 dùng một interface repository để test race. `ReservationStore` trong ví dụ là adapter tới database **thật**, nơi `reserve` phải là thao tác điều kiện nguyên tử theo contract.

~~~java
import java.util.List;
import java.util.concurrent.Callable;

public interface ReservationStore {
    boolean reserve(
        String eventId,
        String requestId,
        int quantity
    );

    InventoryInvariants.State readAuthoritativeState(
        String eventId
    );

    List<String> successfulRequestIds(
        String eventId
    );
}
~~~

Một test dùng barrier để đồng thời bắt đầu:

~~~java
import static org.junit.jupiter.api.Assertions.*;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.*;
import org.junit.jupiter.api.Test;

public abstract class ReservationConcurrencyContractTest {

    protected abstract ReservationStore store();
    protected abstract String seedEvent(int capacity);

    @Test
    void oneSeatCanBeReservedOnlyOnce() throws Exception {
        String eventId = seedEvent(1);
        int contenders = 20;

        ExecutorService pool =
            Executors.newFixedThreadPool(contenders);

        CountDownLatch start = new CountDownLatch(1);
        List<Future<Boolean>> results = new ArrayList<>();

        try {
            for (int i = 0; i < contenders; i++) {
                String requestId = "request-" + i;

                results.add(pool.submit(() -> {
                    if (!start.await(10, TimeUnit.SECONDS)) {
                        throw new IllegalStateException(
                            "start barrier timeout");
                    }

                    return store().reserve(
                        eventId, requestId, 1);
                }));
            }

            start.countDown();

            int successes = 0;
            for (Future<Boolean> result : results) {
                if (result.get(30, TimeUnit.SECONDS)) {
                    successes++;
                }
            }

            assertEquals(1, successes);

            var state =
                store().readAuthoritativeState(eventId);

            assertTrue(
                InventoryInvariants.violations(state)
                    .isEmpty()
            );

            assertEquals(
                1,
                store().successfulRequestIds(eventId).size()
            );
        } finally {
            start.countDown();
            pool.shutdownNow();
        }
    }
}
~~~

### 26.1. Test này chưa bao phủ mọi interleaving

Đồng bộ start tăng cơ hội race nhưng scheduler/network vẫn bất định. Chạy lặp có seed/trace và chủ động chèn delays ở các mốc nguy hiểm.

### 26.2. Không dùng fake repository làm chứng cứ concurrency

Một in-memory fake synchronized sẽ luôn pass dù production dùng `GET` rồi `PUT` không atomic. Contract test cần chạy trên actual target adapter/cluster.

### 26.3. Kết quả timeout

Nếu một future timeout, test không nên đơn giản coi request failed. Ghi event/request ID và reconcile trạng thái server trước khi kết luận.

### 26.4. Không dùng concurrency test để tạo tải phá production

Chạy ở disposable cluster/staging và giữ bounded concurrency/cleanup.

---

## 27. Linearizability: khi nào cần kiểm lịch sử thao tác?

Nếu nghiệp vụ yêu cầu một register/counter/lock có semantics “như các thao tác xảy ra nguyên tử theo một thứ tự tôn trọng thời gian thực”, có thể phải kiểm **linearizability**.

### 27.1. Khái niệm

Mỗi operation được xem như có một điểm tuyến tính hóa giữa invoke và response. Một lịch sử hợp lệ phải tương ứng một chuỗi thao tác tuần tự theo model và giữ **real-time precedence** của các thao tác không chồng lấn.

### 27.2. Ví dụ register

~~~text
write(x=5) returns SUCCESS
read(x) starts after write response
read(x) returns 3
~~~

Nếu cùng key, không có write hợp lệ xen vào và contract là linearizable read/write, lịch sử vi phạm.

### 27.3. Concurrent calls

Hai calls chồng lấn có thể được sắp theo nhiều thứ tự; không yêu cầu trùng thứ tự request arrival nếu contract không nói vậy.

### 27.4. `UNKNOWN` trong lịch sử

Một write timeout có thể đã commit. Checker phải cân nhắc cả hai khả năng hoặc dùng additional evidence, không tự gắn nó là thất bại.

### 27.5. Linearizability không là mặc định của mọi NoSQL operation

Cassandra consistency `ONE`/`QUORUM`, MongoDB read concerns, DynamoDB base-table/GSI reads, Redis async failover và Elasticsearch search visibility khác nhau. Phải kiểm **contract cụ thể**, không hứa toàn cluster linearizable vì có nhiều replicas.

---

## 28. Ghi lịch sử có đủ bằng chứng

Một trace ví dụ:

~~~json
{
  "operationId": "op-42",
  "requestId": "reserve-42",
  "clientId": "client-A",
  "target": "event-7",
  "action": "reserve",
  "quantity": 1,
  "invokedAtMonotonicNanos": 17000000,
  "completedAtMonotonicNanos": 18500000,
  "result": "SUCCESS",
  "observedVersion": 9,
  "node": "db-2",
  "failureContext": "leader-election-3"
}
~~~

### 28.1. Monotonic timestamp

Đo thời gian trong cùng host/process có thể dùng monotonic clock; không được so tùy tiện `System.nanoTime()` giữa các hosts vì origin khác nhau.

### 28.2. Cross-host ordering

Dùng explicit operation relationships, vector/causal context khi cần, server commit sequence, hoặc clock discipline có bounds đã biết. Đừng giả định đồng hồ wall time trên mọi node hoàn hảo.

### 28.3. Kết quả cần phân biệt

- `SUCCESS`.
- `DEFINITELY_REJECTED`.
- `UNKNOWN`.
- `CANCELLED_BEFORE_SEND`.
- `OBSERVATION_FAILED`.

### 28.4. Privacy

Trace chỉ nên lưu pseudonymous IDs và metadata cần thiết; không log payment token, password hoặc toàn bộ document PII.

### 28.5. Bảo toàn traces khi fail

Nếu worker crash, in-memory trace có thể mất chính các operations quan trọng. Dùng test harness độc lập/persisted logs phù hợp, nhưng không làm test engine trở thành nguyên nhân quá tải.

---

## 29. Tại sao đọc snapshot cuối có thể bỏ sót lỗi?

Lịch sử:

~~~text
capacity=1

T1: reserve A succeeds
T2: reserve B succeeds  <-- oversell
T3: compensation cancels B
T4: available=0, held=1, sold=0
~~~

Snapshot lúc T4 hợp lệ, nhưng tại T2 hệ đã công nhận hai holds. Nếu cả hai clients đã nhận success, nghiệp vụ có thể đã hứa một vé cho hai người.

### 29.1. Kiểm state invariant

Sau những committed transitions được ghi nhận.

### 29.2. Kiểm acknowledgment invariant

Không có hai successful receipts cấp cùng một seat/capacity slot.

### 29.3. Kiểm external effects

Nếu email vé hoặc payment đã được gửi, một compensation database sau đó chưa chắc khôi phục được quyền lợi khách hàng.

### 29.4. Khi data model không lưu đủ lịch sử

Cần audit/ledger/test instrumentation cho run quan trọng; nếu chỉ xem aggregate counter thì không thể chứng minh lịch sử không vi phạm.

---

## 30. Eventual consistency: đừng nhầm lag với vi phạm

Nếu target là search index được dựng từ source bằng CDC, một update `order.status=PAID` có thể chưa xuất hiện ngay.

### 30.1. Hợp đồng liveness có điều kiện

Ví dụ:

> “Khi source stream tới checkpoint \(w\) và consumer đã xử lý đến \(w\), search document phải phản ánh version không cũ hơn những changes tương ứng.”

### 30.2. Một timeout theo thời gian

Có thể đặt mục tiêu `99% updates visible within 5s` cho SLO projection, đồng thời giữ invariant nghiêm hơn cho nguồn authority.

### 30.3. Vi phạm safety trên projection

Nếu search projection luôn trả deleted record cho tenant khác, đó không chỉ là lag về mặt correctness nếu contract/security cấm hiển thị ngay sau commit deletion/revocation.

### 30.4. Test chờ có giới hạn

Không dùng `Thread.sleep(30000)` rồi đo một lần. Poll bounded với deadline, capture progress/watermark, và báo timeout có context.

### 30.5. Không nới timeout vô hạn

Nếu CDC đã mắc kẹt và watermark không tiến, việc chờ mãi khiến tests treo và che liveness failure.

---

## 31. Bất biến với CDC và xử lý sự kiện

Một hệ dùng outbox/CDC cần tối thiểu:

- Stable event IDs.
- Version hoặc ordering key.
- Idempotent inbox/consumer.
- Delete propagation.
- Explicit processed checkpoint.
- Dead-letter visibility.
- Retry/backoff policies.

### 31.1. Không mất sự kiện đã commit

Nếu business record và outbox được ghi trong cùng transaction được hỗ trợ, một invariant:

> Mọi business transition được commit và cần phát event đều có một intent/outbox record tương ứng.

### 31.2. Không phát side effect trùng

Delivery có thể lặp nhưng downstream effect phải deduplicate theo event/operation ID.

### 31.3. Không đi lùi version

\[
version_{\text{target,next}}
\ge
version_{\text{target,current}}.
\]

Đây chỉ là ordering property khi versions có nghĩa thứ tự đúng; nếu version reset theo entity recreation/epoch, cần thêm epoch.

### 31.4. Xóa là event

Nếu delete đến trước một backfill insert cũ, insert không được hồi sinh record. Dùng tombstone/version guards và retention phù hợp.

### 31.5. Gap không được coi là đã đồng bộ

Nếu CDC bị mất event vì log retention, cần resnapshot/reconcile; không báo pass chỉ vì consumer offset đã chuyển tới cuối stream.

---

## 32. Kiểm uniqueness sau replication và failover

Một hệ có nhiều regions có thể chấp nhận writes gần đồng thời.

### 32.1. Unique key trên một replica không đủ

Nếu mỗi region cho insert cùng email mà không có global coordination/ownership, cuối cùng có thể conflict hoặc hai successes từng được ACK.

### 32.2. Định nghĩa scope chính xác

Yêu cầu uniqueness toàn cục cần protocol hoặc single-writer ownership phù hợp. Nếu uniqueness chỉ trong một tenant/region, nói rõ boundary.

### 32.3. Merge conflicts

Last-write-wins có thể khiến một bản ghi biến mất, nhưng không “xóa” lịch sử người dùng đã nhận success. Test phải xem receipts và external side effects.

### 32.4. Reconciliation

Nếu business cho phép nhận conflict rồi resolve, bất biến mới phải nói rõ lúc nào temporary conflict được phép và hành vi gì không được xuất hiện với users.

---

## 33. Fencing token và lease: chống stale owner

Giả sử một worker giữ lease để xử lý invoice. Lease hết hạn và worker B được cấp lease mới, nhưng worker A không biết mình đã mất quyền do network pause.

~~~text
Worker A lease epoch=7
Worker A stalls
Worker B lease epoch=8
Worker B writes
Worker A resumes and tries to write
~~~

### 33.1. Bất biến cần giữ

Một write từ epoch cũ không được overwrite state thuộc epoch mới.

### 33.2. Fencing tại nơi nhận ghi

Destination lưu `lastAcceptedEpoch`; chỉ chấp nhận command có epoch không cũ hơn theo chính sách, phối hợp identity/version để tránh duplicate effects.

### 33.3. TTL không phải fencing

Worker A có thể tiếp tục ghi dù lease đã hết nếu destination không kiểm authority.

### 33.4. Test

Tạm dừng worker A, cấp lease B, cho B ghi, cho A tiếp tục và xác minh A bị từ chối.

### 33.5. Không suy bảo đảm chỉ từ “single leader”

Cần kiểm leader term/epoch và phạm vi hiệu lực khi mạng phân hoạch, restore hoặc failover.

---

## 34. Kiểm toán tính đúng sau restore và migration

Một bản backup hoặc migration có thể tạo trạng thái hợp lệ về schema nhưng sai nghiệp vụ.

### 34.1. Khôi phục cũ và revocation

Một permission đã revoke trước sự cố có thể hồi sinh sau restore snapshot cũ.

### 34.2. Idempotency ledger

Nếu ledger bị restore tới một mốc cũ hơn charges đã xảy ra ở provider, retry có thể double charge nếu không có external idempotency.

### 34.3. Inventory

Nếu restored orders và reservations không cùng checkpoint, conservation invariant có thể vỡ dù mỗi table riêng còn đọc được.

### 34.4. Migration bản ghi cũ

Một backfill insert version 6 không được overwrite version 8 do live CDC đã áp.

### 34.5. Acceptance criteria

- Same authoritative business facts at specified checkpoint.
- No unreviewed uniqueness/tenant violations.
- No double side effects.
- Deletes/revocations reconciled.
- Data source/projection versions within agreed lag.
- Quorum/replication và recovery invariants đạt trước cutover.

---

## 35. MongoDB: biến invariants thành atomic operations

### 35.1. Conditional update

Ví dụ MongoDB query điều kiện:

~~~javascript
db.inventory.updateOne(
  { _id: "event-7", available: { $gte: 1 } },
  { $inc: { available: -1, held: 1, version: 1 } }
)
~~~

Nếu `matchedCount = 1`, điều kiện được thỏa tại thời điểm atomic document update. Nhưng ví dụ **chưa tạo reservation ledger và idempotency receipt**; nếu cần conservation giữa inventory và holds collection, có thể phải dùng transaction hoặc redesign trong document.

### 35.2. Unique index

Có thể dùng unique index cho `(tenantId, normalizedEmail)` theo semantics đã định, kể cả cách xử lý null/missing/partial index. Đừng suy unique index một field tự giải mọi policy soft delete.

### 35.3. Multi-document transactions

Khi invariant trải nhiều documents/collections, xác định transaction boundary và retry rules. Các trạng thái transaction commit có thể **unknown** với client khi response bị mất.

### 35.4. Read concern và write concern

Một test đọc từ secondary có thể stale. Dùng read preference/concern và causal/session semantics đúng với contract đang kiểm.

### 35.5. Không gọi `$inc` là solution hoàn chỉnh

Nếu reservation ledger và payment provider nằm ở các hệ khác, cần thêm idempotency, outbox và đối soát.

---

## 36. Cassandra: partition, LWT và consistency

### 36.1. Counters không mặc định thay CAS

Cassandra counters có semantics/operational caveats riêng. Không dùng một counter tăng/giảm đơn giản để hứa invariant conservation liên quan nhiều records dưới retries nếu chưa có idempotency/atomicity plan.

### 36.2. LWT cho điều kiện ghi

Lightweight transactions/conditional updates (`IF`) có thể cung cấp compare-and-set semantics trong phạm vi hỗ trợ. Thiết kế partition/operation boundary để điều kiện ghi bảo vệ đúng invariants.

### 36.3. Consistency levels

`LOCAL_QUORUM`, `QUORUM`, `ONE` ảnh hưởng yêu cầu replicas và visibility, nhưng không tự tạo global transactions hoặc toàn bộ lịch sử tuyến tính hóa tùy ý.

### 36.4. Denormalized tables

Nếu `orders_by_customer` và `orders_by_merchant` được cập nhật ở hai tables, CQL batch không mặc định giải quyết mọi bài toán atomic visibility, distributed invariants hoặc idempotent replay. Phải định nghĩa source of truth và reconciliation.

### 36.5. Tombstone/repair

Một deleted record có thể hồi sinh từ replica quá cũ nếu các điều kiện repair/tombstone không được giữ. Test restore/rejoin và deleted data invariants theo horizon phù hợp.

### 36.6. Test keyspace thực

Sử dụng partition keys có phân phối đại diện; một test chỉ trên một partition nóng không chứng minh mọi data ranges an toàn.

---

## 37. DynamoDB: conditions và transaction limits

### 37.1. Conditional writes

Một `UpdateItem` có `ConditionExpression` có thể kiểm available đủ và giảm số lượng trong một atomic item update.

Ví dụ dạng ý tưởng:

~~~text
UpdateItem:
  Key = event-7
  ConditionExpression = available >= :q
  UpdateExpression =
    SET available = available - :q,
        held = held + :q
~~~

Đây là pseudo-configuration, không phải payload SDK hoàn chỉnh; expression syntax/attribute aliasing cần theo API.

### 37.2. Idempotency record

Nếu chỉ giảm inventory item mà chưa tạo receipt cho request ID, retry sau timeout có thể trừ tiếp. Có thể cần transaction chứa inventory update và unique request ledger item theo constraints của DynamoDB, hoặc một thiết kế single-item idempotency nếu phù hợp.

### 37.3. `TransactWriteItems`

Transactions có phạm vi và giới hạn service về số items/size/operation; kiểm tài liệu của version/region đang dùng. Không tự suy có thể commit vô hạn items trong một transaction.

### 37.4. GSI eventual read

Một GSI có thể chưa phản ánh write mới. Không dùng GSI eventual read làm oracle ngay sau write khi contract yêu cầu strong/current source state.

### 37.5. TTL

TTL deletion bất đồng bộ; yêu cầu bảo mật “đã hết hạn không được dùng” phải được kiểm bằng `expiresAt`, không chờ item biến mất vật lý.

### 37.6. Global tables

Conflict/replication semantics tùy chế độ dịch vụ; một conditional write trong một region không đủ để hứa global uniqueness trên nhiều writable regions nếu chưa có coordination policy phù hợp.

---

## 38. Redis: atomic script không tương đương durable invariant

### 38.1. Trên một primary

Một Redis Lua script hoặc operation nguyên tử có thể giúp kết hợp kiểm và cập nhật state trên cùng server trong điều kiện phù hợp.

~~~lua
-- Minh họa đơn giản cho một key integer,
-- chưa bao gồm idempotency ledger hoặc durability.
local available = tonumber(redis.call("GET", KEYS[1]))
local q = tonumber(ARGV[1])

if not available or q <= 0 or available < q then
    return 0
end

redis.call("DECRBY", KEYS[1], q)
return 1
~~~

### 38.2. Giới hạn quan trọng

Script nguyên tử tại primary trong lúc chạy không tự bảo đảm đã replicate/durable trước khi ACK. Sau failover asynchronous, write có thể mất; nếu business cần durable idempotency, phải chọn architecture phù hợp.

### 38.3. Redis Cluster

Các thao tác nhiều keys có hash slot restrictions. Nếu muốn atomically cập nhật inventory và idempotency key, cần kiểm keys cùng slot và các semantics/limits khác.

### 38.4. Lua không bảo vệ external side effect

Một script reserve thành công nhưng payment provider charge timeout vẫn cần đối soát/idempotency ngoài Redis.

### 38.5. Test

- Script error/timeout.
- Primary failure after write.
- Replica promotion.
- Client retry.
- Duplicate ID.
- Expiry vs confirm.
- Multi-key cross-slot behavior.

---

## 39. Elasticsearch/OpenSearch và các read models

Search index thường là projection, không phải ledger transactional cho inventory.

### 39.1. Search correctness

- Không trả documents từ tenant khác.
- Không trả soft-deleted records trái contract.
- Query filters và sort đúng.
- Results phản ánh mapping/version theo watermark.
- Pagination không làm rò security scopes.

### 39.2. Refresh lag

Một index operation ACK chưa chắc document được search nhìn thấy ngay do refresh behavior. Định nghĩa visibility contract và test tại mốc phù hợp.

### 39.3. Optimistic concurrency

Một số search engines có version/sequence-number based conditional updates. Không dùng chúng như bảo đảm global transaction cho nhiều indexes.

### 39.4. Snapshot/reindex

Rebuild một index phải bảo đảm không mất deletes/events trong khoảng snapshot + tail. Kiểm version precedence và chỉ cutover alias khi validation đủ.

---

## 40. Couchbase và database khác: kiểm semantics theo phiên bản

Couchbase có document CAS và transactions trong các phạm vi được hỗ trợ. Một invariant per-document có thể dựa vào CAS; một invariant multi-document có thể cần transaction/ledger design.

### 40.1. Không suy cùng chữ “CAS” là cùng bảo đảm

Engine A và B có durability, transaction isolation, conflict/failover semantics khác nhau. Cần kiểm docs/version/config và chạy failure tests.

### 40.2. Managed services

Với các NoSQL managed services, không thể inject crash trực tiếp vào storage nodes như self-hosted; có thể test network faults, client timeouts, region failover simulations được phép và backup/restore drills.

### 40.3. App-layer correctness vẫn quan trọng

Một database có strong conditional updates không ngăn app thiếu tenant check hoặc gửi payment charge trùng ngoài transaction.

---

## 41. Đặc tả bất biến bằng toán học: làm đủ rõ, không cần hàn lâm

Một template:

\[
\forall e\in Events,\quad
I(e,S)\equiv
(A_e \ge0)\land(A_e+H_e+S_e=C_e).
\]

Command `Reserve(e,q,k)`:

\[
q>0\land A_e\ge q\land k\notin Ledger
\]

dẫn tới:

\[
A'_e=A_e-q,\quad H'_e=H_e+q.
\]

Với duplicate `k` có cùng payload:

\[
Reserve(e,q,k)\equiv\text{return previous receipt, no new effect}.
\]

### 41.1. Dùng lượng từ cho đúng

“Không có hai active reservations cùng seat ID”:

\[
\forall r_1,r_2\in ActiveReservations,\quad
seat(r_1)=seat(r_2)\Rightarrow r_1=r_2.
\]

### 41.2. Phân biệt equality theo business

“Same amount” có thể yêu cầu cùng currency, scale policy và precision; không so các `double` tùy tiện.

### 41.3. Dùng code làm bản thực thi

Biểu thức toán là đặc tả dễ review; Java checker/DB queries là implementation của oracle. Hai thứ cần được nối bằng test cases và owner review.

---

## 42. Temporal logic: “luôn luôn” và “cuối cùng”

Có thể dùng các ký hiệu trực quan:

- \(G P\): **globally/always**, P luôn đúng.
- \(F P\): **eventually**, sẽ có lúc P đúng.
- \(P\,U\,Q\): P đúng cho đến khi Q xảy ra theo semantics của logic đang dùng.

### 42.1. Safety

\[
G(\operatorname{available}\ge0).
\]

### 42.2. Liveness

\[
G(
\operatorname{eventCommitted}
\Rightarrow
F(\operatorname{eventProcessed}\lor\operatorname{escalated})
).
\]

Nhưng cần điều kiện fairness, không có permanent outage và không mất history; nếu không, liveness này có thể không thực hiện được.

### 42.3. Bounded liveness

Trong product SLO, có thể muốn:

> Một outbox event được commit phải được xử lý hoặc dead-letter trong tối đa 5 phút khi dependencies đáp ứng điều kiện hoạt động đã định nghĩa.

Đó là một time-bounded requirement, không chỉ \(F\) không giới hạn.

### 42.4. Model checking

Với những protocol quan trọng (leader fencing, state transitions, lease ownership), một mô hình nhỏ trong TLA+/PlusCal, Alloy hoặc state explorer có thể tìm interleavings mà unit tests khó chạm tới. Kết quả model checking đúng **chỉ cho mô hình và giả định được viết**, không tự chứng minh implementation thực tế.

---

## 43. Phân biệt invariant, expectation và metric

| Câu hỏi | Loại | Kiểm chứng |
|---|---|---|
| `available` không âm | Safety invariant | Snapshot/history checker |
| Mỗi charge ID chỉ có một effect | Safety/history | Provider + ledger reconciliation |
| Outbox retry cuối cùng thành công | Conditional liveness | Trace + deadline/watermark |
| 99% reads dưới 100 ms | Performance SLO | Histograms/load tests |
| Replica lag dưới 5 giây | Freshness SLO | Replication metrics |
| 99.9% requests thành công | Availability SLO | Request metrics |
| No tenant data leak | Security invariant | Negative tests/authorization oracle |
| DB node `UP` | Operational state | Engine health |
| Backups khôi phục được | Recovery property | Restore drill + correctness validation |

### 43.1. Không kết luận safety từ dashboard p99

Một hệ có thể nhanh và sai.

### 43.2. Không kết luận consistency từ replica count

Một RF=3 không tự bảo đảm linearizability, transaction atomicity hay không double charge.

### 43.3. Gắn severity

Một retry tạo email trùng có thể có severity khác retry trừ tiền trùng; cả hai là lỗi, nhưng release gates và mitigations cần business quyết định.

---

## 44. Thiết kế test pyramid theo từng invariant

~~~mermaid
flowchart TD
    SPEC["Business requirement"]
    MODEL["Formalized predicate / reference model"]
    UNIT["Unit + property tests"]
    INT["Real database integration tests"]
    CONC["Concurrency/history tests"]
    FAULT["Failover/network/restore tests"]
    PROD["Runtime reconciliation and alerts"]
    SPEC --> MODEL --> UNIT --> INT --> CONC --> FAULT --> PROD
~~~

### 44.1. Unit

Kiểm pure rule, boundary, state transitions, invalid inputs.

### 44.2. Integration

Kiểm atomic conditional update/index/transaction semantics của database thật.

### 44.3. Concurrency

Kiểm nhiều clients/instances tranh tài nguyên.

### 44.4. Fault injection

Kiểm crash, leader failover, network partition, retries, log delay và restore trong môi trường được phê duyệt.

### 44.5. Runtime reconciliation

Một test xanh trước deploy không chứng minh production luôn đúng. Dùng ledger audit/sampling/reconciliation và alert cho những invariants có thể quan sát liên tục.

---

## 45. Fault injection: tạo lỗi đúng mốc mới thấy bug

Một request có các mốc:

~~~text
A  Client starts call
B  Server receives command
C  Conditional update committed
D  Outbox record committed
E  Server sends response
F  Client receives success
G  CDC consumer receives event
H  External payment/email side effect
~~~

### 45.1. Các khoảng cần thử

- Trước B: request chưa tới server.
- Sau B, trước C: reject/timeout.
- Sau C, trước E: committed nhưng response chưa tới.
- Giữa D và G: CDC lag/outbox replay.
- Sau G, trước H: consumer retry.
- Sau H, trước ACK consumer: duplicate delivery.
- Trong leader election: stale owner writes.
- Trong restore: event đến muộn, deleted record hồi sinh.

### 45.2. Không giả định từng mốc luôn tách được

Một DB có thể commit business state và outbox trong một transaction; một hệ khác không hỗ trợ. Fault plan phải theo actual architecture.

### 45.3. Seed và lịch sử

Ghi workload seed, node topology, network fault schedule, operation IDs, build version và trace artifacts để reproduce.

### 45.4. An toàn thử nghiệm

Network partition, node kill, disk-full, clock skew và destructive restore chỉ thực hiện trong staging/disposable environments hoặc chương trình chaos được phê duyệt.

---

## 46. Race giữa hủy và xác nhận hold

Một reservation đang `HELD` có thể đồng thời nhận:

~~~text
confirm(reservationId)
cancel(reservationId)
~~~

### 46.1. Bất biến

Một reservation chỉ được chuyển tới **một** terminal outcome theo transition rules; không vừa bán vừa trả inventory.

### 46.2. Postcondition

Nếu `confirm` thắng, `held` giảm và `sold` tăng; `cancel` sau phải từ chối hoặc áp một business workflow riêng.

Nếu `cancel` thắng, `held` giảm và `available` tăng; `confirm` sau không được bán vé đã trả kho.

### 46.3. CAS/version

Dùng conditional transition `status=HELD AND version=n` tại authoritative store. Hai concurrent writers không được cùng nhận successful transition.

### 46.4. Kiểm history

Không chỉ assert tổng cuối đúng. Đếm successful terminal responses và external effects. Hai responses thành công cho `confirm`/`cancel` cùng reservation thường là vi phạm nếu contract không hỗ trợ compensation rõ ràng.

---

## 47. Race giữa expiry job và payment callback

Một khách giữ vé đến 10:00. Payment callback đến đúng mốc 10:00, đồng thời expiry worker chạy.

### 47.1. Cần business quyết định boundary

- Payment được xem thành công theo thời điểm provider capture hay DB callback commit?
- Nếu payment capture xảy ra trước expiry nhưng callback trễ, có phục hồi reservation không?
- Nếu hold đã expire và vé được người khác mua, xử lý refund/alternate seat thế nào?

### 47.2. Không thể suy rule từ TTL alone

DB TTL cleanup có thể bất đồng bộ và không giải quyết conflict giữa nghiệp vụ thanh toán và giữ chỗ.

### 47.3. Một state transition có thể là CAS

`HELD -> CONFIRMED` và `HELD -> EXPIRED` tranh cùng version. Chỉ một transition thắng, và workflow còn lại phải thực hiện compensation/reconciliation theo quy tắc đã duyệt.

### 47.4. Test

Dùng clock điều khiển được, callback delay và failure injection quanh ranh giới; kiểm không oversell và không double charge.

---

## 48. Determinism: giảm flaky tests

### 48.1. Inject Clock

Dùng `Clock.fixed`, `Clock.offset` hoặc fake clock cho TTL/domain expiration, thay vì `sleep` dựa trên thời gian thực.

### 48.2. Điều khiển thứ tự

Cho phép test harness chặn một bước trước CAS, release bằng latch/barrier hoặc proxy/fault hook phù hợp.

### 48.3. Bounded wait

Chờ eventual consistency với deadline và kiểm progress, không sleep cố định 30 giây.

### 48.4. Namespace riêng

Mỗi test có event IDs/tenant IDs độc lập, không bị run khác thay đổi dữ liệu.

### 48.5. Không bỏ qua flaky test

Một concurrency test thi thoảng fail có thể chính là race nghiêm trọng. Phải lưu trace và root cause, không đơn giản tăng retry của test tới khi xanh.

### 48.6. Dữ liệu thời gian

Đồng bộ NTP khi cần so logs giữa hosts, nhưng không suy wall-clock đủ để sắp xếp total order operations trong distributed test.

---

## 49. Thiết kế workload có tính đại diện

Những input cần có:

- Trạng thái gần hết capacity.
- Hot key/partition.
- Nhiều tenants.
- Records lớn/nhỏ và legacy versions.
- Deletes/TTL expiry.
- Network latency khác zones.
- Burst retries.
- Clients mất connection.
- Truy vấn từ replicas khác nhau.
- Long-running batch/CDC.
- Failover giữa write.
- Index build/compaction background.
- Clock skew khi protocol cho phép thử.
- Rebalance hoặc restore.

### 49.1. Vì sao peak load quan trọng?

Một race có thể xuất hiện nhiều hơn khi hệ quá tải, queue dài và retries tăng. Correctness test nên có sustained workloads, không chỉ test một giây.

### 49.2. Nhưng performance pass không là correctness pass

Chạy 100k QPS chỉ có giá trị correctness khi đồng thời thu history/evidence và kiểm predicate.

### 49.3. Đừng tăng tải đến mức không thu được evidence

Nếu test harness mất logs/counterexamples, kết quả `PASS` không đáng tin. Cần kiểm soát throughput sampling và durable trace.

---

## 50. Các bất biến quan sát trong production

Không phải invariant nào cũng có thể kiểm toàn bộ dữ liệu mỗi giây. Có thể tổ chức:

| Cơ chế | Ví dụ | Giới hạn |
|---|---|---|
| Synchronous guard | Atomic conditional decrement | Phải nằm tại authority |
| Event-level validation | Reject invalid transition | Có thể thiếu external state |
| Metrics counter | Rejected stale versions | Không chứng minh không có silent violation |
| Sampled reconciliation | So orders và payment receipts | Không bao phủ mọi record |
| Partitioned full audit | Tính conservation theo entity cohorts | Có độ trễ/chi phí |
| CDC invariant worker | Track versions, duplicate IDs | Phụ thuộc log completeness |
| Scheduled restore drill | Replay và kiểm deletion | Không kiểm runtime hiện tại |
| Security negative probes | Wrong-tenant access denied | Coverage hữu hạn |

### 50.1. Phản ứng với vi phạm

Một alert `CONSERVATION_VIOLATION` phải có:

- Affected scope.
- Evidence/source positions.
- Severity.
- Quy trình tạm dừng writes gây hỏng thêm.
- Quarantine và reconciliation.
- Owner/escalation.
- Không tự sửa dữ liệu mù quáng.

### 50.2. `UNKNOWN` cũng cần cảnh báo

Nếu verifier mất quyền đọc, CDC history gap hoặc consistent snapshot không khả dụng, đó là thiếu bằng chứng, không phải bằng chứng đúng.

---

## 51. Metrics và tracing cho correctness

Một bộ metric có thể gồm:

~~~text
business_invariant_violation_total{
  invariant="no_oversell",scope="ticket"
}

business_invariant_check_total{
  invariant="no_oversell",outcome="pass|fail|unknown"
}

business_operation_total{
  operation="reserve",result="success|reject|unknown"
}

business_idempotency_duplicate_total{
  operation="charge",outcome="deduplicated|conflict"
}

business_reconciliation_lag_seconds{
  projection="orders_search"
}

business_unreconciled_outcome_count{
  operation="payment"
}
~~~

Tên metric chỉ là gợi ý, không khẳng định framework/exporter có sẵn.

### 51.1. Tránh high cardinality

Không gắn raw `orderId`, `requestId`, `email`, `tenantId` tùy ý vào Prometheus labels. Detail có thể lưu trong secure trace/audit bằng references.

### 51.2. Số violations bằng 0 chưa đủ

Nếu số lượng checks bằng 0 hoặc verifier không hoạt động, không thể kết luận an toàn. Theo dõi **coverage**, latest check timestamp và error/UNKNOWN rate.

### 51.3. Record witness

Khi fail, lưu tối thiểu:

~~~text
invariantId
logical entity reference (pseudonymous)
observed commit/version/watermark
operation timeline
failure context
source/target deployment
checker version
repro seed
~~~

### 51.4. Không alert lặp quá mức

Một invariant violation có thể tạo hàng nghìn symptoms; cần deduplicate/incidents theo invariant/scope, nhưng không bỏ details để điều tra.

---

## 52. Phân loại lỗi: test fail không luôn cùng nguyên nhân

| Hiện tượng | Có thể là | Cách phân biệt |
|---|---|---|
| Counter âm | Race/lost update | History + conditional write evidence |
| Count mismatch | Snapshot stale/inconsistent | Read concern/watermark |
| Duplicate charge | Missing idempotency | Provider receipts, request IDs |
| Duplicate CDC event | At-least-once delivery bình thường | Kiểm duplicate **effect** |
| Search trả trạng thái cũ | Eventual lag | Projection watermark và freshness contract |
| Search trả tenant khác | Security bug | Auth context + filters/index |
| Timeout | Outcome unknown | Request ledger/commit evidence |
| Version giảm | Old event overwrite | Event sequence, target guard |
| Expired token accepted | App check thiếu/clock skew | Expiry policy, time injection |
| Restore làm dữ liệu hồi sinh | Deletion ledger gap | Backup point + delete history |
| Checker báo lỗi bất thường | Oracle bug | Pure tests/reference model review |
| Test pass chỉ một lần | Insufficient coverage | Repeat/targeted interleavings |

### 52.1. Tách oracle failure khỏi system failure

Nếu checker có bug, sửa checker nhưng giữ trace nguyên để tái kiểm. Không xóa counterexample khi chưa có kết luận.

### 52.2. Đừng hạ invariant khi gặp lỗi

Một regression có thể quan trọng; nếu business thay contract, cần formal approval và test mới, không sửa assert để build xanh.

---

## 53. Quy trình chuyển một yêu cầu thành test tự động

### Bước 1 — Viết business statement

Ví dụ: “Một request giữ chỗ chỉ được trừ kho tối đa một lần.”

### Bước 2 — Xác định entity và scope

`eventId`, `requestId`, tenant, regions, active/expired lifecycle.

### Bước 3 — Xác định authority

Inventory store và request ledger là nguồn kiểm. Không dùng cache eventual làm duy nhất.

### Bước 4 — Viết predicate

\[
\forall k,\quad\#\operatorname{ReserveEffect}(k)\le1.
\]

### Bước 5 — Liệt kê commands và outcomes

Reserve, retry, cancel, expire, confirm; SUCCESS, REJECTED, UNKNOWN.

### Bước 6 — Viết pre/postconditions

Khi success, trừ đúng quantity và tạo receipt; khi same-key retry, không trừ thêm.

### Bước 7 — Chỉ ra atomicity boundary

Một atomic document/item/partition/transaction? Có external provider? Nếu cần phối hợp nhiều systems, phải có ledger/reconciliation.

### Bước 8 — Chọn oracle

Consistent snapshot + event/receipt history hoặc source authoritative.

### Bước 9 — Tạo test pyramid

Pure predicate test → integration → concurrent duplicate retries → timeout/failover → restore.

### Bước 10 — Chọn coverage và failure injections

Last-unit race, exact retry, process crash after commit, stale leader, CDC delay.

### Bước 11 — Viết PASS/FAIL/UNKNOWN

Không PASS khi thiếu query history, logs hoặc source quorum.

### Bước 12 — Gắn owner và release gate

Một safety violation severity critical phải chặn release/cutover cho tới khi được giải quyết hoặc có phê duyệt thay đổi hợp đồng theo governance.

---

## 54. Một bộ invariant catalog thực tế

| ID | Predicate | Oracle | Mức độ |
|---|---|---|---|
| INV-01 | Không bán vượt capacity | Inventory + reservation history | Critical |
| INV-02 | Một request ID tối đa một reservation effect | Idempotency ledger | Critical |
| INV-03 | Một payment operation tối đa một capture effect | Provider + DB ledger | Critical |
| INV-04 | Không có duplicate active email theo tenant | Unique guard/index | High |
| INV-05 | User chỉ đọc đúng tenant data | Auth + API/query tests | Critical |
| INV-06 | State transitions chỉ đi theo allowed graph | Event/version history | High |
| INV-07 | Record version không giảm | Versioned updates/CDC history | High |
| INV-08 | Expired token không authorize | Clock-controlled API oracle | Critical |
| INV-09 | Outbox intent tồn tại cho committed action | Atomic source transaction | High |
| INV-10 | External email/payment effect không nhân khi redelivery | Downstream receipts | High/Critical |
| INV-11 | Deleted PII không được phục vụ trái policy | Deletion ledger + API/search | Critical |
| INV-12 | Projection cuối cùng bắt kịp checkpoint | CDC watermark | Medium/High |
| INV-13 | Counter conservation theo committed cut | Consistent state checker | High |
| INV-14 | Fencing từ chối stale owner epoch | Destination write history | Critical |
| INV-15 | Không mất ACKed writes theo defined durability contract | Client+server history/restore | Critical |
| INV-16 | Tất cả operation IDs được trace khi UNKNOWN | Request ledger coverage | High |

Các mức độ chỉ minh họa; một hệ nội bộ khác có thể ưu tiên khác.

### 54.1. Không gộp nhiều invariant vào một assert

`assertTrue(systemHealthy())` không chỉ ra lỗi nào sai; catalog với IDs rõ giúp traceability.

### 54.2. Mỗi invariant có implementation strategy và test plan riêng

Một số bảo vệ bằng DB condition, một số bằng external reconciliation, một số cần security test.

---

## 55. Ma trận 40 tình huống kiểm thử tính đúng

| ID | Kịch bản | Điều cần chứng minh |
|---|---|---|
| V01 | Capacity = 0 | Reserve bị từ chối |
| V02 | Capacity = 1, 20 concurrent requests | Tối đa một success |
| V03 | Quantity = 0 hoặc âm | Input bị từ chối, state không đổi |
| V04 | Quantity vượt available | Không tạo hold |
| V05 | Retry cùng requestId/payload | Không trừ kho lần hai |
| V06 | Retry cùng requestId nhưng payload khác | Conflict, không đổi effect |
| V07 | Client timeout sau commit trước ACK | Reconcile UNKNOWN, không duplicate |
| V08 | Cancel cùng hold hai lần | Inventory release một lần |
| V09 | Confirm cùng hold hai lần | Sold tăng một lần |
| V10 | Confirm vs cancel cùng lúc | Chỉ một terminal outcome |
| V11 | Confirm vs expiry cùng lúc | Không oversell/double refund |
| V12 | Restock đồng thời reservations | Conservation và capacity rules |
| V13 | Integer overflow/negative counters | Reject/flag, không wrap |
| V14 | Concurrent creates cùng normalized email | Unique theo tenant |
| V15 | Two tenants dùng cùng email | Uniqueness scope đúng |
| V16 | Email soft delete/re-register | Uniqueness policy đúng |
| V17 | Tenant A truy cập order B | Denied/không lộ |
| V18 | Cursor từ tenant B dùng ở A | Denied/re-bound đúng |
| V19 | Cache key thiếu tenant prefix | Test phát hiện isolation risk |
| V20 | Stale version update | CAS conflict |
| V21 | Concurrent state transitions | Allowed graph, monotonic version |
| V22 | CDC event version cũ đến sau version mới | No rollback |
| V23 | CDC duplicate delivery | Không duplicate side effect |
| V24 | CDC gap vượt retention | Không đánh dấu projection synchronized |
| V25 | Delete trước backfill insert cũ | Không hồi sinh record |
| V26 | Token dùng tại `expiresAt` | Denied theo boundary |
| V27 | TTL cleanup delayed | Expired token vẫn denied |
| V28 | Clock skew đối với lease | Stale owner bị fencing |
| V29 | Primary failover trong reserve | Commit/dedup đúng |
| V30 | Replica read ngay sau write | Đáp read freshness contract |
| V31 | Network partition mất quorum | Không nhận unsafe writes |
| V32 | Node crash trong outbox processing | Replay idempotent |
| V33 | Payment provider đã charge, DB timeout | Không charge lần hai |
| V34 | Ledger restore cũ hơn provider state | Reconciliation bắt buộc |
| V35 | Multi-shard inconsistent snapshot | Checker không PASS giả |
| V36 | Search eventual lag | Deadline/watermark đúng |
| V37 | Search trả deleted or cross-tenant record | Security predicate chặn |
| V38 | Backfill cũ ghi đè live update | Version guard bảo vệ |
| V39 | High contention/IO throttling | Safety giữ dù availability giảm |
| V40 | Oracle thiếu một phần lịch sử | UNKNOWN chứ không PASS |

**Lưu ý:** Fault injection phá node, partition mạng, clock skew, restore dữ liệu cũ hoặc tạo tải lớn chỉ chạy trong staging/disposable environment được phê duyệt và có giới hạn an toàn.

---

## 56. Bài tập 1 — Biến câu nghiệp vụ thành invariant

Các câu:

1. “Không được bán quá số hàng trong kho.”
2. “Mỗi email chỉ thuộc một tài khoản active trong một tenant.”
3. “Một đơn hàng đã giao không trở về trạng thái mới tạo.”
4. “Một yêu cầu hoàn tiền không được xử lý hai lần.”
5. “Phiên đăng nhập hết hạn không thể truy cập API.”
6. “Dữ liệu khách hàng đã xóa không được lộ lại qua search.”

Với mỗi câu, hãy viết:

- Phạm vi/entity.
- Giả định.
- State hoặc history predicate.
- Pre/postcondition.
- Oracle độc lập.
- Một concurrency/failure test.
- Khi nào kết quả UNKNOWN.
- Mức độ nghiêm trọng và owner.

---

## 57. Bài tập 2 — Mô hình hóa kho vé

Giả sử event có `capacity = 5`.

Commands:

~~~text
reserve(requestId, q)
confirm(reservationId)
cancel(reservationId)
expire(reservationId)
restock(q)
~~~

Yêu cầu:

1. Định nghĩa các trạng thái của một reservation.
2. Viết \(A+H+S=C\) và các non-negative rules.
3. Ghi pre/postconditions của từng command.
4. Xử lý requestId duplicate.
5. Xử lý confirm vs cancel.
6. Xử lý confirm vs expire tại cùng thời điểm.
7. Đặt oracle cho inventory, holds, receipts.
8. Tạo command sequences kiểm boundary và lỗi.

---

## 58. Bài tập 3 — Tìm interleaving gây oversell

Hai Java instances cùng làm:

~~~java
long available = repository.readAvailable(eventId);

if (available > 0) {
    repository.writeAvailable(
        eventId, available - 1
    );
    repository.createHold(eventId, requestId);
    return SUCCESS;
}
return REJECTED;
~~~

Hãy:

1. Chỉ ra lịch interleaving của hai clients gây lỗi.
2. Vì sao `synchronized` trong một JVM không đủ?
3. Vì sao snapshot counter có thể không âm dù đã oversell?
4. Thiết kế conditional update/transaction hoặc ownership protocol.
5. Bổ sung idempotency ledger.
6. Viết test 20 concurrent requests tranh một vé.
7. Chèn timeout sau commit nhưng trước response.
8. Định nghĩa những metric và trace cần giữ.

---

## 59. Bài tập 4 — Chọn oracle cho eventual consistency

Một service ghi MongoDB Orders rồi CDC sang Elasticsearch. Product yêu cầu:

~~~text
Sau khi order PAID được commit:
  Trang tài khoản phải hiển thị PAID ngay.
  Search có thể trễ tối đa 10 giây trong điều kiện bình thường.
  Không bao giờ cho tenant khác xem order.
~~~

Yêu cầu:

1. Đặt contract cho authoritative account page.
2. Đặt bounded liveness property cho search.
3. Định nghĩa CDC watermark.
4. Chỉ ra test nào dùng strongly-consistent/RYW read path.
5. Chỉ ra test nào chờ eventual convergence.
6. Định nghĩa security invariant độc lập với lag.
7. Nếu CDC vượt retention, tại sao không PASS?
8. Thiết kế alert cho late projection và missing history.

---

## 60. Bài tập 5 — Kiểm idempotency payment

Giả sử:

~~~text
charge(orderId, requestId, amount)
Provider processes payment
Client experiences timeout
Client retries same requestId
~~~

Hãy:

1. Viết invariant số external successful charges.
2. Đặt `requestId` và payload-hash contract.
3. Định nghĩa `SUCCESS`, `DEFINITELY_REJECTED`, `UNKNOWN`.
4. Thiết kế authoritative ledger/provider receipt lookup.
5. Test duplicate retries từ nhiều app instances.
6. Test provider charge thành công rồi DB crash.
7. Xác định thời gian retention idempotency key.
8. Viết reconciliation oracle.
9. Phân biệt at-least-once event delivery và at-most-once business effect.
10. Thiết kế một runbook khi vi phạm được phát hiện.

---

## 61. Bài tập 6 — Đánh giá tính đúng sau migration

Bạn chuyển `orders` từ MongoDB sang DynamoDB bằng backfill + CDC:

~~~text
Backfill copies order version 5
CDC applies version 8
Backfill finishes late and overwrites version 8
Search projection still has version 7
~~~

Yêu cầu:

1. Xác định invariant đã bị phá.
2. Thiết kế version-guarded target write.
3. Đặt rules cho duplicate/out-of-order CDC.
4. Phân biệt source authority và projection.
5. Dùng consistent cut để so dữ liệu.
6. Kiểm tenant isolation và deleted records.
7. Viết property-based test sinh reordered events.
8. Đặt cutover gates cho source/target.
9. Khi nào nên rollback, khi nào cần reconcile?

---

## 62. Bài tập 7 — Viết Java invariant checker

Sử dụng `InventoryInvariants` làm điểm xuất phát:

1. Thêm `reservedIds` và `seatId` uniqueness checker.
2. Thêm lịch sử `ReserveReceipt`.
3. Phát hiện hai success receipts cho cùng một seat.
4. Phát hiện duplicate requestId với payload khác.
5. Sinh 1.000 states/command sequences ngẫu nhiên.
6. Ghi random seeds khi fail.
7. Dùng test database với conditional writes.
8. Thêm một test có barrier cho concurrency.
9. Dùng một oracle độc lập so với repository implementation.
10. Ghi PASS/FAIL/UNKNOWN và repro trace.

Không cần chạy fault injection lên production.

---

## 63. Bài tập 8 — Thiết kế kế hoạch kiểm thử phân tán

Một hệ gồm 3 nodes NoSQL, 5 Java API instances, outbox worker và payment provider sandbox.

Hãy lập kế hoạch bao gồm:

- Safety/liveness invariants.
- Preconditions/postconditions.
- Concurrency workloads.
- Fault-injection points.
- Failover/leader election.
- Network partitions.
- Unknown write outcomes.
- External payment receipts.
- Event redelivery/CDC lag.
- TTL/expiry.
- Restore/migration.
- Security/tenant isolation.
- Test oracle và authoritative data.
- Coverage/UNKNOWN criteria.
- Artifacts và seed.
- Go/no-go release gates.

Mỗi test cần ghi **giả định**, **chứng cứ**, **expected property** và **khi nào không được tuyên bố PASS**.

---

## 64. Những ngộ nhận thường gặp

| Ngộ nhận | Hiểu đúng hơn |
|---|---|
| “Test `capacity=100` chứng minh không oversell.” | Phải kiểm trạng thái/history khi concurrent |
| “Có 100 test xanh nên invariant được đảm bảo tuyệt đối.” | Tests có coverage hữu hạn |
| “NoSQL không có schema nên không có invariants.” | Business/data contracts vẫn tồn tại |
| “Một API method là một transaction.” | Atomicity thuộc storage/protocol boundary |
| “`synchronized` giữ đúng trên nhiều Java services.” | Lock JVM không chia sẻ trên nodes |
| “Counter không âm chắc không oversell.” | Ledger có thể có hai holds cho một vé |
| “Snapshot cuối hợp lệ chứng minh chưa từng sai.” | Cần history để tìm transient violation |
| “Quorum replicas nghĩa mọi operation linearizable.” | Cần protocol/consistency cụ thể |
| “Read từ replica luôn là latest.” | Có thể stale tùy engine/level |
| “Timeout nghĩa write failed.” | Có thể committed nhưng mất response |
| “Retry giống một request mới.” | Cần idempotency/unknown outcome |
| “At-least-once delivery là bug.” | Duplicate delivery có thể bình thường; effect phải dedup |
| “Exactly-once delivery tự bảo đảm exactly-once payment.” | External side effects cần ledger/provider idempotency |
| “Một uniqueness check trước insert là đủ.” | Check-then-insert có race |
| “DynamoDB GSI strong read như base table.” | GSI reads có eventual consistency |
| “Redis script nguyên tử là durable qua failover.” | Atomic execution và replication durability khác |
| “Cassandra `LOCAL_QUORUM` là global transaction.” | CL không đồng nghĩa atomic multi-table |
| “MongoDB `$inc` bảo vệ cả external provider.” | DB atomicity không vượt external boundary |
| “TTL cleanup đúng giờ nên không cần kiểm expiresAt.” | Cleanup có thể bất đồng bộ |
| “Clock trên mọi nodes đồng nhất.” | Clock skew và time semantics cần mô hình |
| “Lease hết hạn đủ chặn stale worker.” | Cần fencing tại destination |
| “Search index chậm 1 giây là vi phạm mọi contract.” | Phải xét specified freshness |
| “Chờ mãi cuối cùng chắc pass.” | Bounded liveness cần deadline |
| “CDC version cũ không sao vì cuối cùng sẽ cập nhật lại.” | Có thể làm hồi sinh deleted data |
| “Backfill luôn có thể upsert vô điều kiện.” | Old snapshot có thể ghi đè version mới |
| “Restore data thành công là business correct.” | Cần đối soát deletion, payment, dependencies |
| “Một oracle dùng lại production logic là độc lập.” | Có thể lặp đúng cùng một bug |
| “Không có metric violation nghĩa không có bug.” | Có thể verifier chưa chạy |
| “Model checking chứng minh toàn bộ production.” | Chỉ chứng minh mô hình/giả định |
| “Performance test xanh nghĩa correctness test xanh.” | Nhanh và sai vẫn sai |
| “Flaky race test nên bỏ qua.” | Có thể là counterexample thật |
| “Chỉ test happy path là đủ.” | Các lỗi nằm ở retries/failover/boundaries |
| “Quyền tenant chỉ là API concern.” | Query/cache/index/export đều có thể lộ |
| “UNKNOWN có thể coi PASS để khỏi chặn deploy.” | Thiếu bằng chứng không phải bằng chứng an toàn |

---

## 65. Checklist chuyển yêu cầu thành bất biến kiểm chứng được

- [ ] Câu nghiệp vụ đã được viết lại không mơ hồ.
- [ ] Có owner cho từng invariant.
- [ ] Xác định object/tenant/region/data scope.
- [ ] Xác định source of truth.
- [ ] Phân biệt state, transition và history property.
- [ ] Phân biệt safety/liveness/SLO.
- [ ] Ghi giả định failure và availability.
- [ ] Ghi preconditions và postconditions cho mỗi command.
- [ ] Định nghĩa success/rejected/unknown outcome.
- [ ] Xác định logical commit point/atomicity boundary.
- [ ] Chọn oracle độc lập đủ mạnh.
- [ ] Có cách lấy consistent snapshot hoặc commit history phù hợp.
- [ ] Không coi stale read là violation khi contract cho phép.
- [ ] Không coi stale read là PASS cho contract mạnh.
- [ ] Có unit tests cho predicate boundaries/overflow.
- [ ] Có model/reference tests cho command sequences.
- [ ] Có property-based input/sequence generation.
- [ ] Có integration tests trên database thật.
- [ ] Có concurrency tests trên nhiều clients/instances.
- [ ] Có test timeout sau commit trước response.
- [ ] Có test duplicate retry với requestId/payload hash.
- [ ] Có test CAS/stale versions và conflict.
- [ ] Có test expiry/cancel/confirm races.
- [ ] Có test failover và replica consistency.
- [ ] Có test CDC duplicate/reorder/gap.
- [ ] Có test restore/deletion reconciliation.
- [ ] Có test tenant isolation ở API/query/cache/search.
- [ ] Có test external side effects với provider sandbox.
- [ ] Có bounded liveness deadline và fairness assumptions.
- [ ] Có PASS/FAIL/UNKNOWN outcomes.
- [ ] Có request IDs, seed, versions và repro trace.
- [ ] Có coverage/last checker-run monitoring.
- [ ] Không log raw PII/secrets vào tests.
- [ ] Không dùng destructive faults lên production ngoài chương trình được duyệt.
- [ ] Có triage/escalation khi violation xuất hiện.
- [ ] Không tự sửa sai business state thiếu phê duyệt.
- [ ] Có regression test cho mỗi incident đã tìm thấy.
- [ ] Release/cutover gates liên kết với invariant severity.
- [ ] Đặc tả và code checker được version hóa/review độc lập.
- [ ] Khi business rule đổi, invariant card và tests được cập nhật có chủ đích.

---

## 66. Tổng kết

**Yêu cầu nghiệp vụ chỉ trở thành một bảo đảm có thể kiểm chứng khi ta định nghĩa được điều gì phải luôn đúng, ở phạm vi và thời điểm nào, dưới những thao tác và lỗi nào, rồi thu đủ bằng chứng để kiểm tra.**

Những nguyên tắc chính:

1. **Bắt đầu từ business statement, không bắt đầu từ câu lệnh database.** “Không oversell” là invariant; `$inc`/CAS/transaction chỉ là phương tiện.
2. **Viết rõ state, transition và history properties.** Snapshot cuối không chứng minh một hệ chưa từng sai.
3. **Phân biệt safety và liveness.** “Không bao giờ double charge” khác “cuối cùng email được gửi”.
4. **Xác định commit/atomicity boundary.** Một method Java hoặc một HTTP request không tự là giao dịch phân tán.
5. **Dùng oracle độc lập và dữ liệu có thẩm quyền.** Không dựa vào stale cache hoặc cùng logic implementation để tự xác nhận.
6. **Kiểm concurrency và lỗi ở đúng thời điểm nguy hiểm.** Timeout sau commit, duplicate retry, stale leader và expiry races thường quan trọng hơn happy path.
7. **Theo đúng consistency contract của từng NoSQL.** Không suy linearizability chỉ từ số replica hoặc từ lời gọi “quorum”.
8. **Kiểm external side effects và downstream projections riêng.** Outbox, idempotency, CDC, provider receipts và deletion state có invariant riêng.
9. **Không có chứng cứ thì kết quả là UNKNOWN.** Test/metric không chạy không đồng nghĩa hệ an toàn.
10. **Tự động hóa theo nhiều tầng**: pure property checker, model-based test, database integration, concurrency/fault tests và production reconciliation.

**Câu cần nhớ: “Đừng chỉ hỏi chức năng có chạy không. Hãy hỏi trạng thái nào tuyệt đối không được xuất hiện, chuỗi thao tác nào có thể tạo ra nó, và bằng chứng độc lập nào sẽ phát hiện ngay khi điều đó xảy ra.”**
