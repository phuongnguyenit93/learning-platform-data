# Ràng buộc duy nhất hoặc giao dịch khi dữ liệu nằm ở nhiều phân mảnh trong NoSQL

## 1. Bài toán: hai shard đều kiểm tra “chưa tồn tại”

Một ứng dụng cho phép mỗi tổ chức (*tenant*) đăng ký tài khoản bằng email. Yêu cầu nghiệp vụ:

> Trong cùng tenant, một địa chỉ email đã được chuẩn hóa chỉ có thể thuộc về tối đa một tài khoản đang hoạt động.

Hệ lưu document người dùng trên nhiều phân mảnh (*shard*) theo `userId`:

```text
                            Application
                                 |
                           Shard router
                      +----------+----------+
                      |                     |
                      v                     v
                 Shard S1                Shard S2
                userId range A         userId range B

Request A: tenant=T1, email=an@example.test, userId=U101
Request B: tenant=T1, email=an@example.test, userId=U902
```

Hai request chạy đồng thời:

```text
Request A                                  Request B
---------                                  ---------
Query tất cả user theo email -> chưa có
                                           Query theo email -> chưa có
Insert U101 trên S1 -> OK
                                           Insert U902 trên S2 -> OK
```

Mỗi shard có thể đã thực hiện thao tác `insert` một cách nguyên tử. Tuy nhiên hai shard chứa **hai tài khoản có cùng email**. Lỗi không nằm ở riêng thao tác insert, mà ở chỗ **phạm vi ràng buộc duy nhất không trùng phạm vi điều phối của các thao tác**.

Một bài toán tương tự xuất hiện với:

- Tên đăng nhập duy nhất trong toàn hệ.
- Số hóa đơn duy nhất trong một đơn vị kinh doanh.
- Chỗ ngồi chỉ được bán cho một đơn.
- Một mã giảm giá chỉ được dùng một lần.
- Chuyển tiền giữa tài khoản nằm trên hai shard.
- Chuyển trạng thái đơn kèm cập nhật một bản ghi bảo vệ quyền sở hữu ở shard khác.
- Một giao dịch cập nhật nhiều document và phải commit toàn bộ hoặc không commit gì.

Trong chương **Phân mảnh và định tuyến**, điểm trọng tâm là xác định **ai có quyền quyết định một giá trị đã tồn tại hay một transaction đã commit**, dữ liệu liên quan nằm ở những shard nào, và cơ chế nào giữ được cam kết khi **concurrent requests, timeout, migration hoặc failover** xuất hiện.

## 2. Ràng buộc duy nhất là một bất biến toàn phạm vi, không chỉ một truy vấn

Giả sử mỗi tài khoản \(u\) có:

- `tenantId`: tổ chức sở hữu.
- `userId`: định danh tài khoản.
- `emailKey`: khóa email được chuẩn hóa theo chính sách sản phẩm.
- `state`: trạng thái tài khoản.

Ràng buộc cần bảo vệ là:

\[
\forall u_1,u_2,\quad
\bigl(u_1.tenantId=u_2.tenantId
\land u_1.emailKey=u_2.emailKey
\land active(u_1)\land active(u_2)\bigr)
\Rightarrow u_1.userId=u_2.userId
\]

Tức là **hai tài khoản khác nhau không được đồng thời sở hữu cùng một emailKey còn hiệu lực trong cùng tenant**.

### Phạm vi duy nhất phải được ghi rõ

| Yêu cầu | Khóa logic cần độc nhất |
|---|---|
| Username trên toàn sản phẩm | `usernameKey` |
| Email trong từng tenant | `(tenantId, emailKey)` |
| Mã đơn trong một cửa hàng | `(storeId, orderNumber)` |
| Ghế trong một suất diễn | `(showId, seatId)` cho quyền giữ/chốt còn hiệu lực |
| Một lần sử dụng mã giảm giá cho một user | `(campaignId, userId)` hoặc khóa nghiệp vụ phù hợp |
| Idempotency của một payment request | `(merchantId, requestId)` |

Không tự giả định mọi ràng buộc đều **global**. Nếu sản phẩm cho phép cùng email ở hai tenant, đặt unique key chỉ bằng `emailKey` sẽ **từ chối dữ liệu hợp lệ**. Ngược lại, nếu quy tắc yêu cầu username toàn hệ mà chỉ kiểm tra trong từng shard, hệ có thể nhận duplicate không hợp lệ.

### Dữ liệu “duy nhất khi ACTIVE” phức tạp hơn “duy nhất vĩnh viễn”

Nếu email chỉ phải duy nhất với tài khoản `ACTIVE`, cần định nghĩa:

- Tài khoản `SUSPENDED` có còn giữ email không?
- Tài khoản `DELETED` được đăng ký lại email sau bao lâu?
- Email chưa xác minh có được đặt chỗ không?
- Khi đổi email, quyền sở hữu email cũ mất lúc nào?
- Nếu một thay đổi chưa commit hoặc đang `PENDING`, email có bị khóa không?

Đó là một **state machine về quyền sở hữu**, không thể giải quyết chỉ bằng `SELECT ... LIMIT 1`.

## 3. Vì sao shard key quyết định khả năng bảo vệ uniqueness?

Một hệ sharded thường dùng một hàm định tuyến:

\[
shard = f(shardKey)
\]

Ví dụ:

```text
users shard key = userId

U101 -> S1
U902 -> S2
```

Nếu ràng buộc duy nhất lại là `(tenantId,emailKey)`, hai record có cùng khóa duy nhất **không nhất thiết tới cùng shard**.

### Điều kiện lý tưởng để kiểm tra unique cục bộ

Nếu mọi record có **cùng khóa độc nhất** đều được gửi tới **cùng đơn vị lưu trữ có quyền ra quyết định**:

\[
sameUniqueKey(a,b)\Rightarrow sameOwner(a,b)
\]

thì một unique index hoặc conditional write trên owner đó có thể từ chối cạnh tranh bằng **một thao tác nguyên tử cục bộ**.

Điều kiện này không có nghĩa mọi dữ liệu phải ở một node mãi mãi. Shard có thể chuyển chủ sở hữu trong quá trình resharding, nhưng hệ định tuyến và giao thức chuyển ownership phải bảo vệ **không có hai owner đồng thời chấp nhận cùng khóa**.

### Vì sao thêm một unique index trên mỗi shard chưa đủ?

```text
Shard S1: unique(emailKey)
  an@example.test -> U101

Shard S2: unique(emailKey)
  an@example.test -> U902
```

Mỗi index không có duplicate **trong chính shard**, nhưng ràng buộc global đã bị vi phạm. Hệ phân mảnh cần một trong các cơ chế:

1. Định tuyến cùng unique key về một shard/owner.
2. Dùng một **registry/guard** có unique key được bảo vệ nguyên tử.
3. Có **global unique index/service** với hợp đồng mạnh và điều kiện định tuyến.
4. Có distributed transaction hoặc cơ chế điều phối đủ mạnh để kết hợp việc giữ unique key và tạo dữ liệu nguồn.

**Một truy vấn quét tất cả shard không thay thế các cơ chế này**, vì nó không ngăn một request khác ghi chen vào sau khi quét.

## 4. Sai lầm phổ biến: check-then-insert

Một handler ngây thơ:

```javascript
// Pseudocode dễ bị race; không dùng làm bằng chứng uniqueness.
const existing = await users.findOne({
  tenantId,
  emailKey
});

if (existing) {
  throw new Error("EMAIL_EXISTS");
}

await users.insertOne({
  userId,
  tenantId,
  emailKey
});
```

Hai request đồng thời có thể cùng đọc “không tồn tại”, sau đó đều insert.

```text
Thời điểm      Request A                     Request B
---------      ---------                     ---------
T0             exists(email)=false
T1                                           exists(email)=false
T2             insert U101 -> OK
T3                                           insert U902 -> OK
T4             Cùng email có hai owner
```

### Vì sao “đọc mạnh” vẫn chưa đủ?

Ngay cả khi từng lần `findOne` đọc dữ liệu mới nhất tại thời điểm đọc, việc **kiểm tra rồi ghi** vẫn gồm **hai thao tác riêng**. Sau lần đọc, request khác có thể insert trước.

Một strong read không biến:

```text
READ no owner
...
WRITE new owner
```

thành một atomic compare-and-set.

Muốn bảo vệ bất biến, cần **conditional insert, unique constraint hoặc transaction/serializable coordination** có phạm vi thích hợp. Tăng số lần đọc trước insert chỉ thu hẹp xác suất race trong vài workload, **không xóa race**.

### Vì sao locking ở application memory không đủ?

Một `synchronized` trong JVM chỉ giữ các thread của **một process**. Khi ứng dụng có nhiều instance:

```text
App instance A: synchronized(email) -> chỉ khóa RAM A
App instance B: synchronized(email) -> chỉ khóa RAM B
```

Hai bên vẫn có thể ghi trùng. Distributed lock có thể giúp điều phối, nhưng nếu lock hết hạn, process pause hoặc mất mạng, **không có fencing/conditional write ở nguồn** thì owner cũ vẫn có thể ghi sau owner mới.

## 5. Bốn hướng thiết kế chính

| Hướng | Cách giữ bất biến | Điểm mạnh | Đánh đổi |
|---|---|---|---|
| **A. Colocation theo unique key** | Các record cần so uniqueness tới cùng shard | Rẻ và dễ hiểu nếu mô hình phù hợp | Shard key có thể gây hot shard hoặc khó đáp ứng query khác |
| **B. Unique registry/guard** | Một key riêng đại diện quyền sở hữu, conditional create | Phù hợp khi document nguồn shard bằng ID khác | Phải giữ registry và source nhất quán |
| **C. Cross-shard transaction** | Commit nhiều shard như một transaction khi engine hỗ trợ | Atomicity cho nhiều ghi liên quan | Coordination, latency, locks/conflicts, failover phức tạp |
| **D. Workflow/escrow/định danh từ trước** | Phân bổ quyền hoặc duy trì state machine hợp lệ | Hợp với quy trình không thể dùng distributed ACID | Eventual steps, bù trừ, phải định nghĩa trạng thái PENDING |

Không có một giải pháp phù hợp mọi workload. Nếu chỉ cần unique username, registry có thể đơn giản hơn transaction xuyên nhiều shard. Nếu cần chuyển tiền giữa hai tài khoản, một guard username không đủ: phải bảo vệ **atomicity/isolation và ledger** theo yêu cầu tài chính.

## 6. Phương án A: đặt dữ liệu có cùng ràng buộc vào cùng shard

Ví dụ mỗi tenant có quy mô vừa phải và chỉ cần email duy nhất **trong tenant**:

```text
Shard key = tenantId
Unique key = (tenantId, emailKey)

Tenant T1 users -> cùng logical partition/owner
  (T1, an@example.test) -> U101
  (T1, binh@example.test) -> U102

Tenant T2 users -> partition khác
  (T2, an@example.test) -> U901   (hợp lệ)
```

Với hệ cho phép unique index theo shard key như MongoDB trong phạm vi được hỗ trợ, ta có thể bảo vệ uniqueness tại owner của `tenantId`.

### Ưu điểm

- Dữ liệu liên quan có thể cập nhật/kiểm tra trong cùng phạm vi định tuyến.
- Ít scatter-gather hơn với query theo tenant.
- Một số trường hợp không cần cross-shard coordinator.
- Dễ định nghĩa đơn vị khôi phục, quota và quyền sở hữu.

### Chi phí

- Một tenant rất lớn có thể tạo **hot shard**, vì mọi thao tác tenant đó dồn vào một vùng.
- Không phân tán đều khi tenant có kích thước rất chênh lệch.
- Query theo `userId` có thể cần định tuyến phụ hoặc tra cứu key.
- Nếu shard key cần thêm `userId` để mở rộng tenant lớn, unique theo email có thể không còn phù hợp với local uniqueness của tất cả shard.

**Chọn shard key theo một ràng buộc mạnh có thể mâu thuẫn mục tiêu cân tải.** Đây là đánh đổi thiết kế cần quyết định trước khi dữ liệu đạt quy mô lớn.

### Lưu ý “colocation” theo API thật

Đừng suy rằng cùng prefix ở application key luôn được lưu cùng physical shard trong mọi engine. Với hash partitioning hoặc compound shard keys, cần kiểm tra **toàn bộ shard key, quy tắc phân vùng và unique-index constraints** của engine.

## 7. Phương án B: unique registry / guard item theo khóa cần giữ

Khi user document phải shard theo `userId`, có thể tạo một bảng hoặc collection phụ đóng vai trò **sổ đăng ký quyền sở hữu email**.

```text
                       Register email
                           |
                           v
              +----------------------------+
              | Unique registry            |
              | key=(tenantId,emailKey)    |
              | ownerUserId=U101           |
              +-------------+--------------+
                            |
                after successful claim
                            |
                            v
                   +----------------+
                   | Users by ID    |
                   | userId=U101    |
                   +----------------+
```

Một registry entry:

```json
{
  "_id": "email:T1:an@example.test",
  "tenantId": "T1",
  "emailKey": "an@example.test",
  "ownerUserId": "U101",
  "requestId": "signup-R101",
  "state": "RESERVED",
  "generation": 1
}
```

**Điều kiện đúng:** với mỗi `(tenantId,emailKey)`, chỉ có **một phép tạo claim thành công**; nó phải được bảo vệ ở nơi mọi request đến cùng một owner hoặc dùng hệ cung cấp conditional insert có hiệu lực toàn phạm vi.

### Registry không nhất thiết là một node duy nhất

Unique registry có thể phân mảnh **theo chính unique key**:

\[
registryShard = hash(tenantId,emailKey)
\]

Mọi request tranh cùng email vẫn tới **cùng registry shard**, trong khi các email khác nhau được phân tán. Đây là lợi thế quan trọng so với một bảng guard toàn cục chỉ nằm trên một node.

### Claim thành công chưa có nghĩa user đã được tạo

Nếu không có transaction chung:

```text
1. Acquire unique claim  -> OK
2. Create user document  -> CRASH
```

Lúc này email đã được **giữ chỗ** nhưng user document chưa tồn tại. Đây là một trạng thái trung gian cần xử lý.

Có hai hướng:

- Nếu engine hỗ trợ transaction kết hợp hai record, **ghi guard và user cùng transaction**.
- Nếu không, mô hình hóa workflow **RESERVED → ACTIVE**, có retry và reconciliation; không nói cả hai xuất hiện nguyên tử.

Một registry bền có thể bảo vệ **không có hai owner**, nhưng chưa tự đảm bảo **không có orphaned claim**. Muốn đồng bộ đầy đủ phải thiết kế thêm recovery.

## 8. Registry không transaction: state machine và idempotency

Một giao thức nghiệp vụ giả định:

```text
             Conditional Create Guard
             UNIQUE(T1, emailKey)
                       |
               +-------+-------+
               |               |
          CLAIM WON        CLAIM EXISTS
               |               |
               v               v
          state=RESERVED    SAME requestId?
               |               |
               v            Yes: resume
      Create user with ID       No: conflict
      and requestId stable
               |
               v
      Mark guard ACTIVE if
      owner/request/generation matches
               |
               v
           SUCCESS
```

### Phải xác định trạng thái mà API trả về

| Guard state | Ý nghĩa | API có thể làm gì? |
|---|---|---|
| Không tồn tại | Email chưa được claim | Thử conditional claim |
| `RESERVED` | Một request đang/đã bắt đầu sở hữu | Retry cùng request; request khác nhận conflict/pending |
| `ACTIVE` | Có user được xác nhận | Trả owner hợp lệ hoặc conflict |
| `RELEASING` | Quy trình đổi email/xóa đang chạy | Chặn claim mới đến khi an toàn |
| `TOMBSTONE` | Có lịch sử xóa/thay owner | Bảo vệ khỏi replay/owner cũ |

Không nhất thiết mọi hệ cần đúng năm trạng thái trên; đây là thiết kế minh họa. Những chuyển trạng thái phải được bảo vệ bằng **conditional update theo owner/requestId/generation**.

### Crash ở các bước

| Crash | Trạng thái có thể còn | Hướng phục hồi |
|---|---|---|
| Trước claim | Không có guard | Retry acquire |
| Sau claim, trước user insert | Guard RESERVED | Retry tạo user bằng ID ổn định |
| Sau user insert, trước mark ACTIVE | Guard RESERVED + user đã tồn tại | Xác minh owner/request rồi mark ACTIVE |
| Sau ACTIVE, trước response | Cả hai có thể tồn tại | Retry trả cùng kết quả theo requestId |
| Khi đổi email/xóa | Có guard cũ/mới và source chưa đồng bộ | Reconciliation + state transition có điều kiện |

**Không xóa guard một cách mù quáng khi gặp timeout.** Thao tác tạo user có thể đã thành công rồi mất ACK; xóa claim sẽ mở đường cho request khác lấy cùng email trong khi user đầu vẫn tồn tại.

### Lease không tự là ràng buộc vĩnh viễn

Nếu dùng thời hạn cho `RESERVED` để tránh giữ khóa vô hạn, phải giải quyết:

```text
Request A claim email, worker bị pause
Lease hết hạn
Request B claim cùng email, thành công
Worker A tỉnh lại, tiếp tục tạo user
```

Giải pháp cần **fencing token/generation** và nguồn ghi user phải từ chối request A đã mất quyền, hoặc dùng một giao dịch nguyên tử phù hợp. **TTL tự động xóa guard không bảo đảm uniqueness**.

## 9. Phương án C: giao dịch phân tán giữa các shard

Một transaction có thể cần thay đổi dữ liệu nằm trên hai shard:

```text
Transaction T: Transfer 100 units

Shard S1                        Shard S2
--------                        --------
Account A = A - 100             Account B = B + 100
```

Nếu chỉ chạy tuần tự:

```text
1. Debit A on S1 -> COMMIT
2. Crash
3. Credit B on S2 -> chưa chạy
```

tổng giá trị có thể sai theo nghiệp vụ. Đây là bài toán **atomicity xuyên shard**, không chỉ uniqueness.

### Atomicity cần là một cam kết cụ thể

Với transaction \(T\) bao gồm các thay đổi \(w_1,w_2,\ldots,w_n\), mục tiêu thường là:

\[
commit(T)\Rightarrow \bigwedge_{i=1}^n visibleCommitted(w_i)
\]

và:

\[
abort(T)\Rightarrow \neg visibleCommitted(w_i)\quad\text{với mọi }i
\]

Hai biểu thức mô tả tính nguyên tử khái niệm. Trong triển khai thực, độ nhìn thấy của transaction còn liên quan **isolation/snapshot** và recovery. Atomicity không tự đồng nghĩa mọi reader trên mọi replica đều thấy trạng thái mới ngay, và không tự đảm bảo serializability.

### Điều kiện để dùng transaction xuyên shard

1. Engine thực sự hỗ trợ transaction với **phạm vi nhiều shard/partition** cần thiết.
2. Deployment/topology và phiên bản đáp ứng yêu cầu.
3. Các thao tác đều nằm trong **cùng transaction/session/coordination context**.
4. Read/write concern, commit semantics và retry được dùng đúng.
5. Dữ liệu/quy tắc nhất quán cần thiết có thể được khóa/kiểm tra trong isolation của transaction.
6. Có runbook khi transaction bị timeout hoặc trạng thái commit không rõ.

Không thể gắn cú pháp `BEGIN TRANSACTION` của một database vào lệnh Redis, Kafka hoặc payment API rồi mong thành một transaction ACID xuyên mọi dịch vụ.

## 10. Two-phase commit (2PC) ở mức khái niệm

Một cách phối hợp nhiều participant là **two-phase commit**:

```text
                  Transaction Coordinator
                     /               \
                    v                 v
                Shard S1           Shard S2

Phase 1 — PREPARE:
  Coordinator -> S1: prepare T
  Coordinator -> S2: prepare T
  S1 -> Coordinator: prepared
  S2 -> Coordinator: prepared

Phase 2 — COMMIT/ABORT:
  Coordinator quyết định và ghi decision bền
  Coordinator -> S1: COMMIT T
  Coordinator -> S2: COMMIT T
  Participants áp dụng decision và hoàn tất
```

**Đây là sơ đồ protocol tổng quát**, không phải mô tả đủ mọi thuật toán của MongoDB hay hệ NoSQL khác.

### Vì sao phải có PREPARE?

Nếu coordinator quyết định commit trước khi biết tất cả shard có thể thực hiện, một shard có thể thất bại và tạo transaction nửa vời.

Prepare cho phép từng shard cam kết rằng nó **có thể thực hiện quyết định chung**, theo cơ chế khóa/ghi log của engine.

### Chi phí và tình huống khó

- Thêm network round trips.
- Coordinator và participant phải lưu quyết định bền để recover.
- Participant có thể giữ locks hoặc tài nguyên trong lúc chờ quyết định.
- Failover/network partition kéo dài có thể làm transaction **blocked/in-doubt**.
- Commit có thể đã thành công nhưng response tới client bị mất.
- Transaction trên nhiều shard tăng số failure domains và contention.

2PC giải quyết **atomic commit** trong phạm vi được hỗ trợ; nó không tự đảm bảo isolation serializable, global uniqueness hoặc rollback của email/payment provider ngoài transaction.

## 11. Atomicity, isolation và uniqueness là ba câu hỏi khác nhau

### Atomicity

“Debit A và credit B cùng commit hoặc cùng abort.”

### Isolation

“Hai transaction chạy đồng thời có thể quan sát trạng thái trung gian hay gây write skew/lost update không?”

### Uniqueness

“Có thể có hai record khác nhau cùng sở hữu một khóa nghiệp vụ không?”

Một distributed transaction có atomicity nhưng isolation yếu hơn serializable vẫn có thể vi phạm invariant kiểu **check-then-insert** nếu không có unique constraint hoặc cơ chế khóa/serializable predicate thích hợp.

Ví dụ hai transaction:

```text
T1: READ no email; INSERT U101
T2: READ no email; INSERT U902
```

Nếu mỗi transaction chỉ ghi document của mình ở shard khác, transaction có thể **không có write conflict trực tiếp**; dưới một số isolation model, cả hai vẫn có thể commit. Transaction không tự biến predicate “không có email nào trong mọi shard” thành global unique constraint.

**Giải pháp:** duy trì unique key ở một authority có conditional insert/unique index, hoặc dùng isolation/locking bảo vệ đúng predicate theo hợp đồng.

### Snapshot isolation chưa chắc serializable

Một transaction đọc một snapshot nhất quán rồi cập nhật một key không đồng nghĩa mọi tập transaction tương đương một serial schedule. Một số workload có thể gặp **write skew**.

Khi yêu cầu nghiệp vụ là duy nhất hoặc không bán vượt, phải kiểm tra **chính invariant**, không chỉ thấy câu “supports transactions” trên tài liệu.

## 12. MongoDB: unique index trên sharded collection

MongoDB hỗ trợ những cơ chế liên quan:

- Tính nguyên tử của update một document.
- Unique indexes với các giới hạn riêng cho **sharded collections**.
- Distributed transactions trên những deployment hỗ trợ, có chi phí điều phối.
- Write concern, read concern, session và quy tắc commit.

### 12.1. Shard key và unique index phải tương thích

Với MongoDB sharded collection, unique indexes được hỗ trợ theo những quy tắc chặt chẽ; **thông thường unique index cần shard key đầy đủ làm prefix** của index key (hoặc thuộc trường hợp ngoại lệ được tài liệu phiên bản đó cho phép).

Ví dụ collection sharded theo:

```javascript
// Ví dụ minh họa: lệnh yêu cầu cluster sharded và quyền phù hợp.
sh.shardCollection("shop.users", { tenantId: 1 });
```

Một index có thể phù hợp để bảo vệ email trong từng tenant:

```javascript
db.users.createIndex(
  { tenantId: 1, emailKey: 1 },
  { unique: true }
);
```

Hai document cùng `tenantId=T1` và `emailKey=an@example.test` phải bị constraint từ chối; email này vẫn có thể xuất hiện hợp lệ ở `T2`.

### 12.2. Ví dụ thiết kế không phù hợp

Nếu collection sharded theo:

```javascript
{ tenantId: 1, userId: 1 }
```

thì một unique index:

```javascript
{ tenantId: 1, emailKey: 1 }
```

**không chứa toàn bộ compound shard key ở prefix**, nên không thể suy rằng MongoDB bảo vệ uniqueness email trong mỗi tenant bằng chính index này trên collection sharded. Cần đổi shard key, dùng registry hoặc cơ chế bảo vệ khác đúng phiên bản.

### 12.3. `_id` không phải lúc nào cũng global unique trên shard

Ở các collection sharded mà `_id` không phải shard key, cần đọc kỹ ngoại lệ MongoDB về phạm vi enforce uniqueness của `_id` index. **Không tự coi unique `_id` trên từng shard là global unique** cho mọi trường hợp phân mảnh.

Nếu `_id` không định tuyến tới cùng owner, ứng dụng có thể phải đảm bảo uniqueness ở cấp hệ hoặc chọn một shard key phù hợp.

### 12.4. Hashed shard key và unique constraint

MongoDB có các giới hạn với **hashed indexes** và unique indexes. Không nên suy luận rằng có thể tùy ý tạo một hashed unique index để giải quyết toàn cục. Nếu muốn hash để phân phối tải và enforce uniqueness, cần phân biệt:

- Hashed shard key/index của MongoDB.
- Trường `emailHash` do ứng dụng tính và lưu như một field thông thường.
- Unique compound index và giới hạn của sharded collection.

Nếu tự hash email, chỉ dựa vào hash không có kiểm tra collision/định danh gốc có thể gây **false conflict**; và dù collision hiếm, collision vẫn là một thuộc tính phải đưa vào thiết kế. Thường cần định nghĩa canonical key rõ ràng rồi bảo vệ nó trong một authority.

### 12.5. Unique index không phải magic khi index chưa tồn tại

Nếu collection đã có duplicate, tạo unique index có thể thất bại hoặc bị chặn theo cơ chế triển khai. Cần làm sạch dữ liệu và migration có kiểm soát. Đừng tin “chúng ta sẽ tạo index sau” trong khi API vẫn cho phép insert trùng.

**Điểm mấu chốt:** unique index chỉ bảo vệ được phạm vi mà engine xác nhận hỗ trợ; giới hạn sharding, collation, null/missing field, partial/sparse index và phiên bản đều quan trọng.

## 13. MongoDB: distributed transaction khi nhiều shard phải commit cùng nhau

Ví dụ một giao dịch thay đổi hai account:

```javascript
// Node.js MongoDB driver — minh họa thao tác trong cùng session.
async function transfer(db, client, fromId, toId, amount) {
  const accounts = db.collection("accounts");
  const session = client.startSession();

  try {
    await session.withTransaction(async () => {
      const debit = await accounts.updateOne(
        { _id: fromId, balance: { $gte: amount } },
        { $inc: { balance: -amount } },
        { session }
      );

      if (debit.matchedCount !== 1) {
        throw new Error("INSUFFICIENT_BALANCE_OR_NOT_FOUND");
      }

      const credit = await accounts.updateOne(
        { _id: toId },
        { $inc: { balance: amount } },
        { session }
      );

      if (credit.matchedCount !== 1) {
        throw new Error("DESTINATION_NOT_FOUND");
      }
    }, {
      readConcern: { level: "snapshot" },
      writeConcern: { w: "majority" }
    });
  } finally {
    await session.endSession();
  }
}
```

Trong deployment hỗ trợ transaction xuyên shard, MongoDB có thể phối hợp các participant để quyết định commit. Nhưng đây là **ví dụ mô hình**, chưa phải một service chuyển tiền hoàn chỉnh.

### Những giới hạn quan trọng của ví dụ

1. `amount` phải là số nguyên đơn vị nhỏ nhất hoặc kiểu decimal phù hợp, được kiểm tra `amount>0`; tránh float khi xử lý tiền.
2. `fromId` và `toId` phải khác nhau và thuộc tài khoản người gọi được phép thao tác.
3. Phải lưu **transferId/idempotency ledger** nếu client retry, nếu không cùng transfer có thể bị thực hiện hai lần mặc dù từng transaction atomic.
4. Khi commit mất phản hồi, **không suy rằng transaction chắc chắn abort**. Driver có cơ chế xử lý transient errors/unknown commit results; ứng dụng vẫn phải xác minh idempotency.
5. Hai update trong cùng transaction bảo vệ atomicity của chúng trong phạm vi engine hỗ trợ; **không** commit cùng lệnh thanh toán ngoài hay thông báo broker.
6. Nếu ứng dụng cần ledger kế toán, nên dùng các entry bất biến/định danh giao dịch, reconciliation và audit phù hợp thay vì chỉ cập nhật balance.
7. Transaction xuyên shard có chi phí và giới hạn thời gian/tài nguyên; cần đọc tài liệu đúng MongoDB version, topology và options.

### Ràng buộc uniqueness vẫn cần được thiết kế riêng

Ngay cả khi chuyển nguồn bằng transaction, nếu business rule yêu cầu một email duy nhất trên các shard, nên sử dụng **unique index đúng scope hoặc guard ownership**, không mặc định transaction tự tạo global predicate lock ở mọi shard.

## 14. DynamoDB: conditional write + unique guard item

DynamoDB dùng primary key để định danh item; **GSI không phải một unique index tổng quát trên giá trị attribute**. Nếu muốn email duy nhất trong tenant, một mẫu thiết kế là giữ **guard item** với key đại diện cho email.

Ví dụ một bảng single-table:

```text
Users table:

PK="USER#U101"
  type="USER", tenantId="T1", emailKey="an@example.test"

PK="UNIQUE#EMAIL#T1#an@example.test"
  type="EMAIL_CLAIM", ownerUserId="U101", tenantId="T1"
```

Hai request có email giống nhau đều phải ghi **cùng guard key**. `attribute_not_exists(PK)` trên guard sẽ cho tối đa một request thắng ở key đó, trong phạm vi các guarantee của API.

### 14.1. Guard và user cần transaction nếu phải commit cùng nhau

Một mẫu low-level `TransactWriteItems` giả định table có **partition key chỉ là `PK`**:

```json
{
  "TransactItems": [
    {
      "Put": {
        "TableName": "Users",
        "Item": {
          "PK": { "S": "USER#U101" },
          "type": { "S": "USER" },
          "tenantId": { "S": "T1" },
          "emailKey": { "S": "an@example.test" }
        },
        "ConditionExpression": "attribute_not_exists(PK)"
      }
    },
    {
      "Put": {
        "TableName": "Users",
        "Item": {
          "PK": { "S": "UNIQUE#EMAIL#T1#an@example.test" },
          "type": { "S": "EMAIL_CLAIM" },
          "ownerUserId": { "S": "U101" }
        },
        "ConditionExpression": "attribute_not_exists(PK)"
      }
    }
  ],
  "ClientRequestToken": "signup-T1-request-R101"
}
```

Đây là **ví dụ request payload** để giải thích pattern, không bao gồm credential hay mã gọi SDK. Hai item có **PK khác nhau**, và cả hai được viết trong một transaction được dịch vụ hỗ trợ. Request token có semantics idempotency, thời hạn hiệu lực và điều kiện payload phải đọc theo tài liệu API cụ thể; **không** coi token đó là dedup vĩnh viễn cho mọi retry sau nhiều ngày.

### 14.2. Điều kiện dùng pattern

- Mọi nơi tạo account bắt buộc đi qua quy trình guard; nếu một luồng import bỏ qua nó thì invariant bị phá.
- Chuẩn hóa `emailKey` thống nhất giữa mọi writer trước khi tính guard key.
- Khi đổi email/xóa user, phải cập nhật guard cũ/mới và user theo transaction hoặc state machine đúng.
- Transaction service có giới hạn theo API, số item, size, region/account và phiên bản; xem docs hiện hành.
- Transaction không trải tự động qua một payment provider, Redis, Kafka hay replication liên vùng có semantics riêng.
- Nếu nhiều region cùng cho phép write độc lập, **một transaction trong region A không tự là global uniqueness guarantee cho mọi region**. Phải xét mode Global Tables và kiến trúc authority.

### 14.3. Vì sao chỉ query GSI trước insert không đủ?

```text
Query EmailGSI("an@example.test") -> empty
Put USER#U101 -> success
```

Hai request có thể cùng query empty, vì **check-then-put** không atomic. GSI còn có thể trễ; việc query GSI mạnh hay yếu theo API không biến một query predicate và Put thành một transaction guard. **Key của guard + conditional insert mới là nơi tranh quyền.**

## 15. Cassandra/ScyllaDB: primary key và lightweight transaction theo partition

Trong Cassandra, dữ liệu được phân phối theo **partition key**, còn clustering columns sắp xếp dữ liệu trong partition. Một `PRIMARY KEY` xác định định danh của row, nhưng không tự tạo global uniqueness tùy ý trên attribute khác thuộc những partition khác.

Ví dụ lưu user theo ID:

```sql
CREATE TABLE users_by_id (
    user_id text PRIMARY KEY,
    tenant_id text,
    email_key text,
    display_name text
);
```

Hai user IDs khác nhau có thể cùng `email_key` nếu ứng dụng không đặt thêm bảo vệ.

### 15.1. Bảng guard partition theo unique key

```sql
CREATE TABLE email_claims (
    tenant_id text,
    email_key text,
    owner_user_id text,
    request_id text,
    state text,
    PRIMARY KEY ((tenant_id, email_key))
);
```

Mỗi `(tenant_id,email_key)` chính là một partition key. Có thể dùng lightweight transaction:

```sql
INSERT INTO email_claims (
    tenant_id, email_key, owner_user_id, request_id, state
) VALUES (
    'T1', 'an@example.test', 'U101', 'signup-R101', 'RESERVED'
)
IF NOT EXISTS;
```

Ứng dụng phải kiểm tra kết quả `[applied]`:

```text
[applied] = true  -> claim thành công
[applied] = false -> đã có claim, xem owner/request theo hợp đồng
```

LWT có semantics điều phối/serial consistency riêng theo partition và phiên bản; nó tốn chi phí hơn write thông thường.

### 15.2. Guard LWT và users_by_id không tự chung transaction

```text
LWT email_claims -> claim OK
INSERT users_by_id -> crash
```

Đó vẫn là **hai partition/đường ghi**. Một LWT trên guard không tự biến insert ở bảng `users_by_id` thành một atomic transaction cùng guard. Phải dùng state machine `RESERVED/ACTIVE` và retry/reconciliation hoặc chọn thiết kế khác có atomicity mạnh theo engine thật.

### 15.3. CQL BATCH không phải giao dịch SQL tổng quát

`BEGIN BATCH ... APPLY BATCH` trong Cassandra có semantics riêng về nhóm mutation và logging, nhưng **không cung cấp isolation/serializability tổng quát xuyên nhiều partition như một RDBMS transaction**. Không dùng batch như mẹo thay thế global uniqueness.

Đừng nhầm **atomicity của batch theo phạm vi được hỗ trợ** với “predicate check rồi insert trên mọi shard chạy serializable”.

### 15.4. Những hạn chế cần ghi

- LWT và serial consistency có chi phí network/latency.
- Conditional operation có phạm vi/điều kiện hỗ trợ cụ thể; đọc docs theo phiên bản Cassandra/ScyllaDB.
- Cross-DC quorum/latency và failure modes ảnh hưởng khả năng phục vụ.
- Bảng guard có thể có hot partitions nếu khóa không phân phối đều.
- Tombstones, TTL, repair và clock semantics làm quy trình release/cleanup cần được thiết kế cẩn thận.

## 16. Redis và distributed locks: hỗ trợ điều phối nhưng không tự hoàn tất uniqueness

Redis hỗ trợ thao tác nguyên tử ở phạm vi key/instance phù hợp, ví dụ:

```redis
SET claim:email:T1:an@example.test U101 NX PX 30000
```

Nghĩa khái quát: đặt key nếu chưa tồn tại, kèm TTL 30 giây. Điều này **có thể dùng làm một cơ chế đặt chỗ/điều phối tạm thời**, nhưng không tự là global unique registry bền qua mọi failover, expiration và storage crash.

### Race khi lease hết hạn

```text
T0 Worker A giữ lock email, lease 30s
T1 A pause 45s
T2 Lease hết hạn
T3 Worker B giữ lock, tạo user U902
T4 Worker A chạy lại, tạo user U101
```

Nếu write vào MongoDB/DynamoDB source **không kiểm tra quyền sở hữu/fencing token**, cả hai user có thể được tạo.

Một distributed lock có thể giúp giảm xung đột và contention, nhưng **không thay thế unique constraint hoặc conditional write tại nguồn dữ liệu có thẩm quyền**.

### Redis Cluster và nhiều key

Các thao tác nhiều key/script/transaction có giới hạn định tuyến theo hash slot và phiên bản Redis Cluster. Không tự suy rằng một `MULTI/EXEC` hoặc Lua script có thể atomic update các key nằm trên những shard khác nhau.

Khi cần uniqueness bền toàn tenant, nên đặt quyền quyết định ở datastore/protocol có hợp đồng phù hợp thay vì chỉ dựa vào một cache key có TTL.

## 17. Search index không phải nguồn ràng buộc duy nhất

Một index tìm kiếm hoặc bảng `users_by_email` được dựng từ CDC/outbox có thể phục vụ:

```text
find users where emailKey = "an@example.test"
```

Nhưng nếu nó cập nhật bất đồng bộ:

```text
Source: email đã claim cho U101
Search projector: chưa nhận event
Query search: empty
Client B: quyết định tạo U902 vì search empty
```

thì ứng dụng có thể ghi trùng.

**Search/index projection là đường tra cứu, không phải người cấp quyền sở hữu duy nhất**, trừ khi chính hệ đó được thiết kế làm authority cho unique key và cam kết atomic conditional create trên đường ghi được dùng.

### Truy vấn scatter-gather không làm check-then-insert nguyên tử

Ngay cả khi query tất cả shard trả lời đúng tại thời điểm kiểm tra, ngay sau đó một writer khác có thể tạo record:

```text
Time T0: scatter READ -> none
Time T1: writer A INSERT email on S1
Time T2: writer B INSERT email on S2
```

Muốn biến kết quả kiểm tra thành quyền ghi, cần **khóa/guard/transaction/predicate serialization** mà mọi writer phải tôn trọng.

## 18. Chuẩn hóa unique key: một vấn đề nghiệp vụ, không chỉ index

Đối với email, cách tính `emailKey` phải được **định nghĩa chính xác**. Ví dụ sản phẩm có thể muốn tránh trùng khác chữ hoa/chữ thường ở những phần nhất định, hoặc chuẩn hóa Unicode theo chính sách.

```text
User input: "An@Example.Test"
Product canonicalization policy -> "an@example.test"
Guard key -> (T1, "an@example.test")
```

### Không tùy tiện chuẩn hóa toàn bộ email

Việc hạ chữ thường phần local-part của email không phải lúc nào cũng tương ứng với quy tắc kỹ thuật của mọi nhà cung cấp; dấu chấm, dấu cộng, Unicode và domain internationalized cũng có semantics riêng. **Không tự áp quy tắc “xóa dấu chấm” hoặc “bỏ mọi phần sau dấu +” trên mọi domain** nếu nghiệp vụ không định nghĩa rõ.

Chỉ khi sản phẩm đã chọn **canonicalization contract** và kiểm chứng tính phù hợp, mọi writer mới dùng cùng một hàm để tính `emailKey`.

### Version của thuật toán chuẩn hóa

Nếu đổi chính sách:

```text
canonicalization v1: key K1
canonicalization v2: key K2
```

có thể phát sinh collision giữa những tài khoản cũ. Cần migration có kiểm soát, dual-validation hoặc guard bổ sung trong giai đoạn chuyển đổi. Không đơn giản thay code app rồi tin rằng unique index cũ bảo vệ theo quy tắc mới.

### Null/missing và partial unique

Một số hệ cho phép index unique trên các trường nullable/partial/sparse với semantics đặc thù. Nếu nhiều user chưa có email, phải quyết định:

- Có bỏ họ khỏi phạm vi uniqueness không?
- Khi chuyển từ null sang email, ai cấp claim?
- Unique index có cho phép nhiều null/missing theo cấu hình đã chọn không?

Không suy luận giống nhau giữa MongoDB, DynamoDB và Cassandra; kiểm tra API/index semantics của từng hệ.

## 19. Chuyển quyền sở hữu email: bài toán khó hơn tạo mới

Giả sử U101 đang sở hữu `emailOld` và muốn đổi sang `emailNew`.

### Với transaction xuyên các record liên quan

Nếu cùng một transaction được hỗ trợ:

```text
BEGIN TRANSACTION
    Acquire guard(emailNew) if absent
    Update user U101 emailOld -> emailNew with expectedVersion
    Release guard(emailOld) only if owner=U101
COMMIT
```

Nếu một bước không đáp ứng điều kiện, abort transaction, giữ trạng thái cũ.

### Nếu không có transaction

Có thể dùng workflow:

```text
1. Reserve emailNew for U101, requestId=R1
2. Update user U101 with expectedVersion and R1
3. Mark emailNew ACTIVE
4. Release emailOld if it still belongs to U101
5. Reconcile any interrupted step
```

**Thứ tự và trạng thái API phải rõ:** nếu bước 2 thành công nhưng bước 4 chưa xong, có thể tạm thời có cả old/new claim thuộc U101. Điều đó có thể an toàn về uniqueness nhưng gây **khóa email cũ lâu**. Đây là trade-off liveness/cleanup; không được “sửa” bằng cách release email cũ trước khi chắc source không còn dùng nó.

### Concurrent rename

Nếu U101 đồng thời gửi:

```text
R1: emailOld -> emailA
R2: emailOld -> emailB
```

phải dùng version/CAS trên user, request ID ổn định và guard ownership để chỉ một transition có hiệu lực. Request thua phải release claim nó đã giữ, nhưng **chỉ sau khi xác minh claim đó không còn cần thiết và không đã được commit hợp lệ**.

## 20. Delete, soft-delete và tái sử dụng unique key

Một email được đăng ký lại sau khi account cũ xóa. Quy tắc phải định nghĩa:

1. Account xóa logic (*soft delete*) có còn giữ email?
2. Có khoảng chờ trước khi tái sử dụng không?
3. Những event cũ có thể được replay lại trong bao lâu?
4. Hệ có cần audit lịch sử chủ sở hữu không?
5. Những session hoặc token cũ còn quyền tác động không?

### Tombstone / generation

Ví dụ guard:

```json
{
  "_id": "email:T1:an@example.test",
  "ownerUserId": "U101",
  "generation": 5,
  "state": "RELEASED",
  "releasedAt": "2026-11-14T09:30:00Z"
}
```

Nếu email được cấp lại cho U902, tăng generation. Một worker cũ từ thế hệ 5 không được phép hoàn thành thao tác cập nhật của thế hệ 6 chỉ vì nó còn giữ một request cũ.

Điều kiện kiểu:

```text
WHERE guard.generation = expectedGeneration
  AND guard.ownerUserId = expectedOwner
```

phải được thực thi **nguyên tử ở authority**, không phải chỉ kiểm tra trong RAM rồi ghi sau.

### TTL có thể phá invariant

Nếu guard `ACTIVE` tự hết TTL trong khi user vẫn tồn tại, người khác có thể chiếm email. TTL chỉ nên dùng khi quy tắc sản phẩm thực sự cho phép claim hết hạn và có **cơ chế bảo vệ writer cũ**, ví dụ explicit lease/fencing và cập nhật source có điều kiện.

**Xóa dữ liệu và replay event cũ** cần được kiểm soát cùng version/tombstone để account đã xóa không bị hồi sinh ở read model.

## 21. Shard migration và resharding: ownership phải chuyển an toàn

Khi cân tải, shard key range hoặc partition có thể chuyển từ S1 sang S2.

```text
Before migration:
    uniqueKey K -> shard S1

During migration:
    copying records, routing metadata changes

After migration:
    uniqueKey K -> shard S2
```

Nếu router cũ vẫn đưa request tới S1 và router mới đưa tới S2 mà **cả hai đều cho phép claim K độc lập**, invariant bị phá.

### Nguyên tắc cần giữ

- Chỉ có một owner hợp lệ cho unique key theo **epoch/generation**.
- Request gửi tới owner cũ bị chuyển hướng/từ chối hoặc được xử lý theo giao thức chuyển quyền an toàn.
- Outstanding transactions/claims được kết thúc hoặc chuyển đổi có quy tắc.
- Unique index/guard được duy trì khi migrate.
- Retry từ router cũ không tạo một đường bypass.
- Sau cutover phải có đối soát duplicate và quyền sở hữu.

Trong hệ có cơ chế balancer/resharding bản địa, nên tin vào **quy tắc chính thức của engine** và dùng đúng router/metadata management; không tự xây logic “copy rồi xóa shard cũ” cho dữ liệu có ràng buộc mạnh.

### Fencing bằng epoch

Một mẫu tổng quát:

```text
S1 owns K at epoch=11
S2 receives ownership at epoch=12

S1 write with epoch=11 -> rejected after transfer
S2 write with epoch=12 -> allowed
```

Fencing cần được enforce ở nơi lưu dữ liệu hoặc coordinator có thẩm quyền. Nếu chỉ để epoch trong log debug mà không kiểm tra lúc ghi, nó không bảo vệ gì.

## 22. Ràng buộc duy nhất trên nhiều loại dữ liệu

### 22.1. Username toàn hệ

Một registry sharded theo `usernameKey` có thể phù hợp. Record người dùng shard theo `userId` để phục vụ profile lookup; transaction hoặc workflow đảm bảo registry và user cùng thống nhất.

### 22.2. Invoice number theo tổ chức

Nếu `(tenantId, invoiceNo)` là unique key, có thể đặt quyền cấp invoice number tại một authority theo tenant, hoặc dùng số định danh theo nguồn cấp phát có phạm vi rõ. Không nên dựa vào `MAX(invoiceNo)+1` ở nhiều shard concurrent.

Nếu hóa đơn yêu cầu thứ tự liên tục không có gap, đó còn là một bất biến khác **khó hơn uniqueness**: transaction abort có thể tạo gap trong bộ phát số, nên phải định nghĩa yêu cầu pháp lý/nghiệp vụ thật thay vì tự thêm “không gap” một cách vô tình.

### 22.3. Một suất diễn, một ghế

Định tuyến bởi `(showId,seatId)` tới authority cho ghế. Conditional update từ `AVAILABLE` sang `HELD` hoặc một transaction cấp quyền. Không dùng cache hiển thị số ghế còn trống để xác nhận.

### 22.4. Coupon dùng một lần

Một key đại diện redemption `(campaignId, userId)`, claim có điều kiện. Nếu promotion có quota chung 10.000 lần sử dụng, còn cần **global quota**; unique per-user không tự bảo vệ tổng quota.

### 22.5. Payment idempotency

Định danh request `(merchantId,idempotencyKey)` cần duy nhất, nhưng ràng buộc này **không đảm bảo** nhà cung cấp thanh toán ngoài chỉ charge một lần nếu có hai lệnh gọi. Cần đồng bộ hiệu ứng tới provider bằng key ổn định và reconciliation.

**Mỗi bài toán có một loại bất biến khác nhau**; không thể giải mọi thứ chỉ bằng index unique đơn giản.

## 23. Multi-key transaction khác saga

### Transaction mạnh

Một hệ hỗ trợ distributed transaction có thể commit nhiều record trong một phạm vi nguyên tử:

```text
T: reserve seat + create reservation document + update ledger
COMMIT all or ABORT all
```

Điều kiện là tất cả resource đều thuộc phạm vi transaction mà engine hỗ trợ.

### Saga / workflow

Nếu tồn kho ở service A, thanh toán ở service B, giao hàng ở service C:

```text
Reserve inventory -> Charge payment -> Schedule shipment
         |                 |                    |
         v                 v                    v
    Local commit       Local commit         Local commit
```

Không có một ACID transaction chung. Một saga điều phối các bước và **compensation**:

```text
Charge failed -> Release inventory
Shipping failed after charge -> Refund/manual review
```

Refund là **một giao dịch mới**, không làm biến mất lịch sử charge. Saga có thể đảm bảo workflow cuối cùng đạt trạng thái hợp lệ nhưng **không tự bảo vệ một global uniqueness invariant tại mọi thời điểm**.

Nếu điều kiện “chỉ một user sở hữu email” phải đúng ngay khi tạo account, cần guard/authority mạnh; saga không thay thế claim nguyên tử.

## 24. Độ bền và quorum ảnh hưởng kết quả sau failover

Một guard/unique index có vẻ bảo vệ đúng khi hệ bình thường, nhưng cần hỏi:

```text
T0 Node A accepts guard K, ACK
T1 Replica B chưa nhận guard K
T2 A mất node
T3 B được bầu leader
T4 Request khác thử claim K
```

Nếu ACK ban đầu là chế độ yếu và write có thể bị rollback, guard K có thể biến mất sau failover. B có thể cho request khác claim, trong khi ứng dụng trước đó đã báo “đăng ký thành công”.

Vì vậy cần kết hợp:

- **Uniqueness primitive** thực sự nguyên tử trong đúng phạm vi.
- **Write ACK/durability** phù hợp với yêu cầu lời hứa đã trả client.
- **Read consistency** phù hợp khi truy vấn tình trạng claim.
- **Failover protocol** bảo toàn lịch sử đã commit theo mode được cam kết.
- **Idempotency** để xử lý timeout/ACK thất lạc.

Quorum intersection giúp các tập replica giao nhau trong giả định phù hợp, nhưng không tự là **global unique constraint**. Nếu các shard sở hữu hai user khác nhau và không chung guard, mỗi shard vẫn có thể commit một record trùng business key dù mỗi shard dùng majority.

## 25. Unknown commit result và retry an toàn

Một trường hợp rất phổ biến:

```text
Client -> DB: create U101 + claim email
DB: transaction COMMITTED
Network: mất phản hồi
Client: timeout, không biết kết quả
```

Client không được tự suy rằng transaction thất bại và tạo user ID mới:

```text
Retry with U902, new requestId -> có thể conflict hoặc tạo side effect trùng
```

### Thiết kế idempotency

Chọn `requestId` ổn định cho **một yêu cầu nghiệp vụ logic**:

```json
{
  "requestId": "signup-T1-R101",
  "tenantId": "T1",
  "userId": "U101",
  "emailKey": "an@example.test"
}
```

Sau timeout:

1. Retry với **cùng requestId và payload hợp lệ tương ứng**.
2. Nếu transaction đã commit, đọc lại ledger/guard/user để xác nhận.
3. Nếu thấy claim của **cùng requestId/owner**, trả kết quả tương ứng hoặc resume.
4. Nếu thấy claim thuộc request khác, xử lý conflict theo hợp đồng.
5. Nếu chưa thể xác minh vì mất quorum, trả `UNKNOWN/PENDING` có nghĩa rõ, **không cấp một lời hứa mới**.

### Không đặt toàn bộ niềm tin vào token có thời hạn ngắn

Một số API cung cấp transaction idempotency token với **cửa sổ hiệu lực hữu hạn**. Nếu nghiệp vụ có thể retry sau nhiều ngày, cần ledger/request ID bền riêng, không suy rằng SDK token là cơ chế dedup vĩnh viễn.

### HTTP response cần phân biệt trạng thái

| Response nghiệp vụ | Nghĩa |
|---|---|
| `CREATED` | User và quyền sở hữu unique key đã commit theo hợp đồng |
| `CONFLICT` | Unique key đã thuộc về yêu cầu khác |
| `PENDING` | Workflow đã được nhận nhưng chưa hoàn tất/đã xác minh |
| `UNAVAILABLE` | Không thể quyết định an toàn hiện tại |
| `UNKNOWN` | Kết quả một thao tác trước chưa xác minh được |

Không trả `CREATED` chỉ vì đã ghi một email claim `RESERVED` mà user chưa được tạo khi API hứa account sẵn sàng.

## 26. Index bảo vệ ràng buộc và query tìm kiếm có vai trò khác nhau

Một ứng dụng có thể cần hai đường:

```text
              WRITE (authoritative)
Client ------------------------------> Unique authority
                                     conditional claim
                                          |
                                     create user
                                          |
                                    outbox / CDC
                                          |
                                          v
                                      Search index
                                          ^
Client ------ SEARCH / FILTER ------------+
```

Unique authority quyết định **ai được sở hữu email**. Search index giúp **tìm nhanh** theo email hoặc tên.

Nếu search lag, user có thể chưa thấy account mới trong kết quả. Nhưng hệ **không được nhận duplicate** chỉ vì search chưa thấy; mọi write phải kiểm tra authority.

### Rebuild search không được tạo lại quyền sở hữu

Khi mất search index, projector có thể rebuild từ nguồn. Nó không nên tự “tạo lại guard” từ kết quả index cũ mà không kiểm tra authoritative state, vì có thể chứa bản cập nhật trễ hoặc đã bị xóa.

**Dẫn xuất phục vụ đọc** và **ràng buộc định danh** phải có nguồn đúng rõ ràng.

## 27. Mô hình lỗi chi tiết và cách khôi phục

| Sự cố | Nguy cơ | Cơ chế cần |
|---|---|---|
| Hai request cùng email trên hai shard | Duplicate nếu check-then-insert | Unique owner/guard/constraint |
| Registry claim thành công, user insert lỗi | Orphaned RESERVED claim | Retry/reconciliation/state machine |
| User insert thành công, ACTIVE update timeout | Kết quả mơ hồ | Idempotency và xác minh ownership |
| Transaction commit thành công, ACK mất | Retry tạo tác động trùng | Request ledger, retry commit phù hợp |
| Lease hết hạn, worker cũ tỉnh lại | Stale worker tạo user | Fencing generation/conditional source write |
| Primary rollback write guard chưa đủ bền | Mất quyền sở hữu đã báo client | Write concern/durability đúng |
| Shard router metadata cũ | Ghi sai owner | Redirect/fencing/epoch theo giao thức |
| Resharding cắt ngang transaction | Conflict/timeout/retry khó | Engine-supported migration, retry an toàn |
| GSI/search chưa cập nhật | Query “không tồn tại” giả | Không dùng GSI/search làm guard |
| Email đổi đồng thời hai nơi | Hai guard mới, source không nhất quán | CAS version + cleanup có điều kiện |
| Guard bị xóa TTL sớm | Email bị tái chiếm | Bảo vệ ACTIVE claim, state machine |
| Event delete tới muộn | Projection hồi sinh dữ liệu | Tombstone + version guard |
| Cross-shard transaction chậm | Lock/timeout và giảm throughput | Colocation, giảm scope, tuning |
| Multi-region write độc lập | Hai authority cấp cùng key | Home region/quorum hoặc conflict policy đúng nghiệp vụ |

Đây là lý do một thiết kế đúng phải có **cả cơ chế chặn trùng ở đường ghi lẫn quy trình phục hồi sau lỗi**, không chỉ happy-path transaction.

## 28. Multi-region và nhiều vùng độc lập

Giả sử có region A và B:

```text
Region A: guard email K chưa tồn tại
Region B: guard email K chưa tồn tại

Network partition giữa regions

Client A -> claim K at A -> ACK
Client B -> claim K at B -> ACK
```

Nếu hai region đều độc lập cấp quyền sở hữu K, có thể tồn tại hai claim trước khi replication hội tụ.

### Giải pháp thường cân nhắc

1. **Home region/owner per key:** mọi claim K đến một authority, nếu không liên lạc được thì không xác nhận.
2. **Coordination mạnh liên vùng:** commit chỉ khi đạt điều kiện bảo vệ uniqueness, chấp nhận latency/availability trade-off.
3. **Phân quyền trước:** với tài nguyên có thể phân chia, dùng escrow/quota theo miền; không phù hợp với một username duy nhất được cấp cho hai người.
4. **Cho phép conflict và bù trừ:** chỉ phù hợp nếu nghiệp vụ chấp nhận những claim ban đầu là provisional, **không gọi đó là bảo đảm unique tức thời**.

### CAP trong bài toán này

Khi các region không trao đổi được thông tin, không thể vừa cho **mọi region cấp cùng unique key thành công độc lập** vừa giữ bất biến “chỉ một owner hợp lệ” cho mọi lịch sử. Một region có thể phải chờ/từ chối hoặc thay đổi ngữ nghĩa response thành `PENDING`.

Không nên gắn nhãn toàn sản phẩm CP/AP; chỉ cần mô tả **operation cấp quyền, phạm vi key, partition cụ thể và điều kiện ACK**.

## 29. Hot key và hiệu năng của unique registry

Một registry theo `hash(tenantId,emailKey)` phân phối các email khác nhau, nhưng một **email cực kỳ nóng** vẫn đưa mọi request tranh chấp về **một owner**. Đó không phải bug; nó phản ánh thực tế phải có một điểm quyết định quyền sở hữu **cùng unique key**.

### Theo dõi các chỉ số

| Nhóm | Metric gợi ý |
|---|---|
| Uniqueness | Conditional conflict count, duplicate-key errors |
| Routing | Shard lookup latency, stale metadata redirects |
| Hot keys | Top contention keys theo giá trị đã ẩn danh/nhóm, retries |
| Transactions | Commit latency p50/p95/p99, abort/conflict, in-doubt |
| Registry workflow | RESERVED age, ACTIVE count, orphaned claims |
| Idempotency | Duplicate request hits, unknown-result recovery |
| Failover | Leader election, rollback events, replica lag |
| Reconciliation | Registry↔source mismatches, repair count |
| Migration | Transfer progress, route errors, epoch conflicts |
| Capacity | Per-shard QPS, CPU, disk I/O, cache hit, network RTT |

Không đưa nguyên văn email/username vào **metric labels** gây cardinality cao và rủi ro lộ dữ liệu. Cần phân loại log/audit với quyền truy cập hạn chế.

### Vì sao cross-shard transaction thường đắt hơn?

- Nhiều network round trips tới các shard.
- Nhiều participant phải ghi log và giữ tài nguyên.
- Khả năng conflict/abort tăng theo số participant và thời gian transaction mở.
- Failover/network partition có thể làm transaction bị kéo dài.
- Coordinating commit decision tăng tail latency.

Một tối ưu thường có hiệu quả là **giảm số shard tham gia một transaction bằng mô hình dữ liệu phù hợp**, chứ không chỉ tăng timeout.

## 30. Thiết kế kiểm thử cạnh tranh: hai client không đủ

Thử hai request là điểm bắt đầu, nhưng cần kiểm tra dưới tải và lỗi.

### 30.1. Bộ dữ liệu

```text
tenant=T1
same emailKey=an@example.test
100 requestIds: R001..R100
100 distinct userIds: U001..U100
All requests start near-simultaneously
```

Điều kiện cuối:

\[
count(\text{ACTIVE owners of }(T1,emailKey))\le1
\]

Với thiết kế nghiệp vụ “một lần đăng ký thành công”, kỳ vọng có **tối đa một response CREATED tương ứng với owner commit hợp lệ**; các response còn lại là conflict/pending/unknown và có thể được đối soát.

### 30.2. Các phép thử cần có

1. Nhiều request song song trên **cùng unique key**.
2. Nhiều unique key khác nhau để đo phân phối shard.
3. Same requestId retry sau timeout.
4. Crash sau guard claim trước user insert.
5. Crash sau user insert trước mark ACTIVE.
6. Primary failover ngay sau ACK dưới các write concern.
7. Network partition giữa registry và source.
8. Shard migration trong khi claim/rename.
9. Hai yêu cầu đổi email đồng thời.
10. Delete/re-register trong lúc event cũ đến trễ.
11. Multi-region concurrent claims, nếu deployment có multi-region.
12. Restore backup/CDC replay và đối soát nguồn–guard.

### 30.3. Kiểm chứng từ nguồn có thẩm quyền

Đừng chỉ đọc GSI/search để đếm duplicate, vì index có thể chưa hội tụ. Dùng authoritative snapshot/đường đọc phù hợp và kiểm tra:

- Số guard ACTIVE mỗi unique key.
- Số user ACTIVE cùng key.
- Mapping ownerUserId có tồn tại và đúng tenant không.
- Claim RESERVED quá hạn quy trình, cần xử lý.
- Có CREATED response nào không có dữ liệu commit tương ứng.
- Có duplicate payment/email verification side effects không.

Kết quả phải xét cả **trạng thái database và lời hứa đã trả client**, không chỉ count hiện tại.

## 31. Ví dụ Java: kiểm thử invariant trong concurrent workload

Đoạn Java 17 dưới đây minh họa một harness độc lập với database driver. Giao diện `RegistrationService` phải được triển khai bằng một trong các cơ chế unique thật; code này **không tự tạo uniqueness**.

```java
import java.util.ArrayList;
import java.util.List;
import java.util.UUID;
import java.util.concurrent.Callable;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

interface RegistrationService {
    // CREATED, CONFLICT, PENDING hoặc UNKNOWN.
    String register(
        String tenantId,
        String emailKey,
        String userId,
        String requestId
    ) throws Exception;

    long countActiveOwners(String tenantId, String emailKey)
        throws Exception;
}

public final class UniqueRegistrationRace {
    static void run(RegistrationService service) throws Exception {
        int clients = 100;
        ExecutorService pool = Executors.newFixedThreadPool(clients);
        CountDownLatch start = new CountDownLatch(1);
        List<Future<String>> results = new ArrayList<>();

        try {
            for (int i = 0; i < clients; i++) {
                final int index = i;
                Callable<String> attempt = () -> {
                    String requestId = "R-" + index;
                    String userId = "U-" + index;
                    start.await();

                    try {
                        return service.register(
                            "T1", "an@example.test", userId, requestId
                        );
                    } catch (Exception timeoutOrFailure) {
                        return "UNKNOWN";
                    }
                };
                results.add(pool.submit(attempt));
            }

            start.countDown();

            long created = 0;
            for (Future<String> result : results) {
                if ("CREATED".equals(result.get())) {
                    created++;
                }
            }

            // Việc đếm phải dùng nguồn authoritative,
            // sau khi xử lý hoặc phân loại các request UNKNOWN.
            long activeOwners = service.countActiveOwners(
                "T1", "an@example.test"
            );

            if (created > 1 || activeOwners > 1) {
                throw new AssertionError(
                    "Global uniqueness invariant violated"
                );
            }
        } finally {
            pool.shutdown();
        }
    }
}
```

### Cách đọc giới hạn

- Các imports `UUID` ở đây không cần thiết cho ví dụ chính; trong test thật cần **ID ổn định giữa retry**, không tạo UUID mới mỗi lần retry một request logic.
- Nếu API trả `UNKNOWN`, không được gọi kết quả là failed và bỏ qua; phải **xác minh commit outcome**.
- Chỉ đếm `ACTIVE` là chưa đủ nếu claim RESERVED đang bảo vệ email và chưa hoàn tất. Cần đối soát state machine.
- Test phải dùng source/guard đọc ở mode phù hợp, không dựa vào search projection.
- Một lần test không tìm thấy duplicate **không chứng minh** mọi lịch sử đều an toàn. Cần fault injection trong lab, kiểm tra trên shard/region và history.
- Nếu test cùng lúc 100 request không đảm bảo race tại đúng mốc, có thể bổ sung barrier, pause hoặc network fault có kiểm soát trong **môi trường cô lập**, không can thiệp production.

## 32. Quan sát và điều tra sự cố duplicate

Khi phát hiện hai user cùng email, đừng ngay lập tức xóa một user tùy ý.

### Bước 1 — Bảo toàn dấu vết

Thu thập:

- User IDs, tenant, canonical unique key.
- Request IDs và thời điểm invoke/ACK.
- Shard ownership/route và topology.
- Unique index/guard state và epoch.
- Transaction IDs, write concern, retries.
- Change streams/outbox events và import jobs.
- Failover/resharding events gần thời điểm lỗi.

Sử dụng quyền và chính sách bảo mật phù hợp khi truy xuất dữ liệu cá nhân.

### Bước 2 — Xác định nguyên nhân

Các nguyên nhân thường gặp:

- Chỉ unique trên từng shard, thiếu global authority.
- Bỏ qua guard ở một ingestion path.
- Canonicalization khác nhau giữa các service.
- Race check-then-insert.
- Guard lease hết hạn, worker cũ vẫn ghi.
- Retry tạo ID mới sau timeout.
- Write chưa đạt durability bị rollback.
- Shard migration để hai owner đồng thời nhận ghi.
- Restore/CDC replay tạo duplicate sai quy tắc.

### Bước 3 — Chặn phát sinh mới

Đưa mọi write qua authority/guard phù hợp; nếu chưa đảm bảo tính đúng, có thể tạm từ chối một nhóm thao tác thay vì tiếp tục tạo duplicate.

### Bước 4 — Xác định owner có thẩm quyền

Không chọn tự động theo `updatedAt` mới nhất khi chưa xác định semantics. Cần xem các ACK hợp lệ, thứ tự transaction/epoch, source of truth và các tác động nghiệp vụ đã diễn ra.

### Bước 5 — Sửa và đối soát

Hợp nhất hoặc xử lý những bản ghi theo chính sách, sửa guard/source/index dẫn xuất, thông báo khi cần, theo dõi các side effects như email/payment. Dùng một repair job **idempotent** và ghi audit.

### Bước 6 — Chứng minh lỗi không tái diễn

Thêm concurrency/failover/migration tests tương ứng, cảnh báo duplicate và dashboard conflict/guard orphan.

## 33. Cách chọn phương án theo bài toán

| Bài toán | Hướng bắt đầu | Không nên làm |
|---|---|---|
| Email unique trong tenant nhỏ | Colocate theo tenant + unique index đúng shard key | Chỉ check tồn tại trước insert |
| Username unique toàn hệ, user shard theo userId | Registry theo normalized username + conditional claim | Unique index chỉ trên từng user shard |
| Tạo user + guard có hỗ trợ cross-shard transaction | Atomic transaction cho hai record | Publish email/payment trong transaction callback |
| Tạo user + guard không có transaction chung | Durable state machine, retry, reconcile | Dùng TTL lock như bằng chứng duy nhất |
| Trừ tiền A và cộng B ở hai shard | Transaction/ledger có thẩm quyền, idempotency | Hai update độc lập rồi coi là chuyển tiền hoàn tất |
| Đặt chỗ độc quyền | Conditional atomic reservation tại owner ghế | Dựa vào availability preview/cache |
| Coupon có quota chung | Owner quota/escrow/atomic counter + per-user claim | Chỉ unique theo user mà quên tổng quota |
| Search theo email | Projection/index để tra cứu, không làm nguồn xác nhận | Dùng kết quả search empty để cấp username |
| Đổi email | Acquire mới + update + release cũ atomically hoặc workflow có version | Xóa guard cũ trước khi commit thay đổi |
| Multi-region active-active | Phân định key owner/coordination hoặc chấp nhận conflict theo hợp đồng | Hứa unique toàn cầu khi hai region ghi độc lập không phối hợp |

### Quy trình ra quyết định 10 bước

1. **Viết invariant** bằng khóa logic và phạm vi tenant/global.
2. **Liệt kê mọi write path**, gồm API, import, batch, CDC replay, admin scripts.
3. **Xác định shard key thực tế** và cách router chọn owner.
4. **Kiểm tra index constraint** theo engine/version/sharding topology.
5. **Quyết định colocate, registry hay distributed transaction**.
6. **Tách atomicity khỏi isolation**, kiểm tra transaction có bảo vệ đúng predicate không.
7. **Thiết kế idempotency và commit ambiguity**, tránh retry tạo side effect trùng.
8. **Thiết kế release/migration/fencing**, không dừng ở create path.
9. **Chạy concurrency/fault tests**, đọc nguồn có thẩm quyền và audit ACK.
10. **Theo dõi metric và viết runbook**, gồm cleanup orphan guard và resharding.

## 34. Những ngộ nhận cần tránh

| Ngộ nhận | Sự thật |
|---|---|
| “Có unique index trên mọi shard thì unique toàn cục” | Local uniqueness không tự thành global uniqueness |
| “Query tất cả shard thấy empty thì insert an toàn” | Check-then-insert có race |
| “Strong read sẽ tránh insert trùng” | Strong read không tự bảo vệ khoảng giữa read và write |
| “Mọi transaction đều serializable” | Atomicity và isolation có phạm vi/level khác nhau |
| “Transaction xuyên shard tự cấp unique cho mọi field” | Cần guard/index/predicate coordination |
| “Shard key nào cũng tạo được unique index tùy ý” | Engine có quy tắc sharded unique index |
| “MongoDB `_id` luôn global unique bất kể shard key” | Cần xem phạm vi sharded `_id` index theo phiên bản |
| “GSI DynamoDB unique theo email” | GSI không thay thế guard conditional write |
| “LWT Cassandra cho một partition là transaction xuyên mọi partition” | LWT có phạm vi giới hạn |
| “Cassandra BATCH giống RDBMS serializable transaction” | Batch semantics khác isolation tổng quát |
| “SET NX trong Redis là global unique vĩnh viễn” | TTL/failover/persistence/fencing có rủi ro |
| “Distributed lock đã đủ” | Source vẫn cần conditional write/fencing |
| “Kafka exactly-once bảo vệ cả MongoDB + Redis” | Broker transaction không tự bao phủ hệ ngoài |
| “Saga giống ACID rollback” | Compensation là tác động nghiệp vụ mới |
| “Timeout = transaction chưa commit” | Có thể commit rồi mất ACK |
| “TTL guard giải phóng claim an toàn” | Owner cũ có thể còn hoạt động |
| “Resharding chỉ là copy dữ liệu” | Ownership/routing/epoch và concurrent write quan trọng |
| “LWW đủ cho username unique” | Hai ACK độc lập có thể hứa quyền xung đột |
| “Search index thấy không có user thì email trống” | Search/CDC có thể trễ |
| “Một lần test 100 request là chứng minh formal” | Chỉ là một workload mẫu, cần nhiều fault cases |

## 35. Bài tập thực hành

### Bài 1 — Chứng minh race check-then-insert

Hai client cùng kiểm tra email `an@example.test` chưa tồn tại rồi tạo U101 trên S1 và U902 trên S2. Hãy vẽ lịch sử xen kẽ và giải thích vì sao mỗi shard atomic insert vẫn không bảo vệ global uniqueness.

### Bài 2 — Chọn phạm vi unique

Một SaaS cho phép cùng email xuất hiện ở nhiều tenant, nhưng mỗi tenant chỉ có một owner. Hãy viết khóa uniqueness và giải thích vì sao index chỉ trên email từ chối những user hợp lệ.

### Bài 3 — Shard key MongoDB

Collection sharded theo `{tenantId:1}` muốn unique `{tenantId:1,emailKey:1}`. Sau đó một kiến trúc sư đề xuất đổi shard key thành `{tenantId:1,userId:1}`. Hãy phân tích sự phù hợp của unique index với shard key mới và lựa chọn thay thế.

### Bài 4 — Global guard

Users sharded theo userId. Hãy thiết kế registry item theo `(tenantId,emailKey)` gồm `ownerUserId`, `requestId`, `state` và `generation`. Vì sao mọi request tranh cùng email phải đến cùng guard key?

### Bài 5 — Crash sau claim

Worker claim email thành công rồi crash trước insert user. Khi retry, trạng thái `RESERVED` còn. Hãy thiết kế hành vi của **cùng requestId** và **requestId khác**. Tại sao không xóa guard ngay?

### Bài 6 — Lease hết hạn

Worker A có lease 30 giây, bị pause 45 giây; worker B lấy claim rồi commit. Làm sao dùng generation/fencing ở nguồn để từ chối worker A sau khi tỉnh lại?

### Bài 7 — DynamoDB transaction guard

Một bảng có primary key `PK`. Viết hai `Put` trong `TransactWriteItems`: `USER#U101` và `UNIQUE#EMAIL#T1#an@example.test`, đều có `attribute_not_exists(PK)`. Điều gì xảy ra khi request khác muốn tạo U902 cùng email?

### Bài 8 — Cassandra LWT

Tạo bảng `email_claims` có partition key `(tenant_id,email_key)` và insert `IF NOT EXISTS`. Vì sao kết quả `[applied]=true` không đồng nghĩa row `users_by_id` ở partition khác cũng đã commit?

### Bài 9 — Distributed transaction

Chuyển 100 đơn vị từ A trên S1 sang B trên S2. Liệt kê trạng thái có thể xảy ra nếu làm hai update tuần tự. Giải thích 2PC ngăn commit nửa vời thế nào và còn những vấn đề retry/isolation nào.

### Bài 10 — Email rename

U101 muốn đổi từ email X sang Y; đồng thời U102 cũng muốn lấy Y. Thiết kế các thao tác claim Y, update source bằng expectedVersion và release X. Nếu bước cuối thất bại, invariant nào vẫn phải giữ và job đối soát làm gì?

### Bài 11 — Delete và re-register

Email X được giải phóng sau khi user cũ xóa. Một event cũ `UserUpdated` đến muộn. Hãy dùng tombstone, generation và idempotency để ngăn user cũ hồi sinh hoặc chiếm lại email.

### Bài 12 — Shard migration

Khóa K chuyển S1 → S2 khi có request cạnh tranh. Router A vẫn gửi S1, router B gửi S2. Hãy mô tả cách dùng owner epoch, redirect hoặc protocol migration để ngăn hai shard cùng chấp nhận K.

### Bài 13 — Multi-region

Region A và B tách mạng, mỗi bên đều nhận đăng ký username `anna` và trả CREATED. Sau khi mạng nối lại, LWW giữ một owner. Vì sao điều này không bảo vệ lời hứa uniqueness đã trả? Hãy chọn một architecture giảm rủi ro.

### Bài 14 — Retry sau timeout

Transaction đã commit account U101 và guard, nhưng response mất. Client retry bằng U902 và requestId mới. Hãy phân tích failure mode, đề xuất request ledger và cách trả cùng kết quả cho retry logic.

### Bài 15 — Phân biệt uniqueness và quota

Mỗi user chỉ nhận coupon một lần, chương trình có tối đa 10.000 lượt. Unique `(campaignId,userId)` bảo vệ điều gì? Nó chưa bảo vệ điều gì? Đề xuất thêm nguồn quản lý quota có cơ chế atomic/escrow phù hợp.

### Bài 16 — Thiết kế test concurrency

Cho 100 request khác userId nhưng cùng unique key. Hãy liệt kê các trường log cần ghi, điều kiện kiểm tra sau test, và các fault cases để phân biệt duplicate do check-then-insert, rollback, TTL race hoặc resharding.

### Bài 17 — Chính sách chuẩn hóa

Một service chuyển toàn email thành lowercase, service khác chỉ chuyển domain thành lowercase. Điều gì xảy ra khi cùng một người đăng ký các biến thể khác nhau? Cần thiết kế canonicalization contract và migration ra sao?

### Bài 18 — Chọn kiến trúc

So sánh ba hệ: (A) tenant nhỏ, (B) một tenant rất lớn, (C) multi-region active-active. Với username unique trong tenant, hãy chọn colocate/registry/distributed transaction hoặc owner routing, nêu đánh đổi latency, throughput và availability.

## 36. Kết luận

**Ràng buộc duy nhất và giao dịch khi dữ liệu nằm ở nhiều phân mảnh** không thể được bảo đảm bằng cách chạy nhiều lệnh “kiểm tra rồi ghi” ở các shard độc lập. Để giữ bất biến, hệ cần một **phạm vi quyết định có thẩm quyền** và một **cơ chế commit/conditional write thật sự nguyên tử** trong phạm vi đó.

Những nguyên tắc đáng nhớ:

1. **Định nghĩa đúng unique scope.** Username toàn hệ, email theo tenant, số hóa đơn theo cửa hàng hay ghế theo suất diễn là những ràng buộc khác nhau.
2. **Shard key ảnh hưởng trực tiếp uniqueness.** Nếu hai record có cùng unique key có thể tới hai shard không phối hợp, local unique index không đủ.
3. **Colocation thường rẻ hơn coordination.** Nếu thiết kế shard key đưa cùng invariant về một owner, conditional write/unique index có thể bảo vệ tốt hơn và nhanh hơn.
4. **Unique registry là một mẫu quan trọng.** Định tuyến theo unique key rồi claim có điều kiện, nhưng phải xử lý claim/source atomicity, crash, TTL, release và reconciliation.
5. **Distributed transaction giải quyết atomic commit trong phạm vi engine hỗ trợ**, với chi phí latency/locks/coordination; isolation và uniqueness vẫn cần thiết kế đúng.
6. **Các công nghệ có phạm vi khác nhau.** MongoDB có giới hạn unique index trên sharded collections và distributed transactions; DynamoDB có conditional writes/transaction guard; Cassandra có LWT theo phạm vi; Redis locks và search index không tự thay thế global authority.
7. **Retry an toàn là bắt buộc.** Timeout không có nghĩa transaction thất bại. Request ID ổn định, ledger và xác minh kết quả bảo vệ khỏi side effect trùng.
8. **Resharding, failover và multi-region mới là những bài kiểm tra khó.** Ownership phải được fencing và ACK phải tôn trọng cam kết durable/consistent phù hợp.
9. **Đối soát sau sự cố không phải tùy chọn.** Guard, user records, search projections và những lời hứa đã trả client phải cùng phù hợp.

Trước khi quyết định dùng một unique index hoặc transaction, hãy hỏi:

> “**Ai là authority của khóa duy nhất này?** Hai request cạnh tranh sẽ gặp nhau ở **một thao tác nguyên tử nào**? Nếu thao tác hoặc mạng bị ngắt giữa chừng, **retry và recovery** có thể đưa hệ về trạng thái đúng mà không xác nhận trùng hay không?”

Khi trả lời được ba câu hỏi ấy theo đúng **shard key, consistency model, API và failure mode**, kiến trúc NoSQL mới có nền tảng vững để giữ **global uniqueness và giao dịch nhiều phân mảnh** ở quy mô lớn.
