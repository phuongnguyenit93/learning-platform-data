# Thực hành giao dịch, mất kết nối và xử lý kết quả chưa xác định

Một API chuyển 50.000 đồng giữa hai tài khoản trong MongoDB có thể ghi thành công nhưng ứng dụng lại nhận **socket timeout**: gói phản hồi từ primary bị mất đúng lúc transaction commit. Nếu service lập tức thực hiện lại chuyển tiền như một giao dịch mới, khách hàng có thể bị trừ **hai lần**. Ngược lại, nếu ứng dụng thấy lỗi giữa transaction rồi chỉ ghi thêm bên nhận, hệ thống có thể mất tính cân bằng. Đây là những sự cố cần được xử lý bằng **giao dịch, kiểm soát lỗi, idempotency và đối soát**, chứ không chỉ bằng một lệnh `retry()`.

Bài **“Thực hành giao dịch, mất kết nối và xử lý kết quả chưa xác định”** thuộc chương **Thực hành tổng hợp** của module *Database Engine Document MongoDB*. Nội dung là một chuỗi bài thực hành có thể áp dụng trên **replica set thử nghiệm**, từ thiết kế dữ liệu, chạy transaction, cố ý tạo xung đột, mô phỏng failover/mất kết nối, tới phân loại lỗi và xác minh kết quả nghiệp vụ.

Điểm mấu chốt xuyên suốt: **lỗi client nhận được không luôn cho biết dữ liệu đã được commit hay chưa**. Trong trường hợp kết quả commit chưa xác định, mục tiêu đầu tiên là **không tạo thêm tác động nghiệp vụ**, sau đó xác định trạng thái thông qua khóa idempotency và dữ liệu đáng tin cậy.

> **An toàn thực hành:** Chỉ fault injection, step down primary, chặn mạng hoặc sửa cấu hình trên **replica set lab/staging được cấp phép**. Tuyệt đối không làm các thao tác này trên production chỉ để học. Ví dụ sử dụng `mongosh` và Java Sync Driver hiện đại, giả định MongoDB replica set có transactions support. API, error labels và timeout semantics phụ thuộc driver/server/FCV; tra tài liệu chính thức của đúng phiên bản đang chạy. Các số dư, tài khoản và chuyển tiền là dữ liệu mô phỏng, không thay yêu cầu về kế toán, pháp lý, bảo mật của hệ thống thanh toán thật.

## 1. Kết quả học tập

Sau bài này, người học có thể:

1. Phân biệt **single-document atomic update** và **multi-document transaction**.
2. Cấu hình và kiểm tra replica set, session, transaction options, read concern, write concern.
3. Tạo một transaction ghi vào accounts, transfer log, ledger entries và outbox.
4. Giải thích khác biệt giữa **abort trước commit**, **commit chắc chắn thành công**, **commit chắc chắn thất bại** và **kết quả commit chưa xác định**.
5. Nhận diện error labels `TransientTransactionError` và `UnknownTransactionCommitResult`.
6. Thực hiện **retry toàn bộ transaction body** khi phù hợp, so với **retry riêng commit** khi commit outcome chưa rõ.
7. Thiết kế **idempotency key ổn định**, unique constraints và bước xác minh outcome khi client hoặc HTTP gateway retry.
8. Quan sát failover/connection loss, các giới hạn transaction và khôi phục sau sự cố.
9. Viết kiểm thử có lỗi được đưa vào có kiểm soát, không phụ thuộc một race ngẫu nhiên.
10. Xây runbook xử lý kết quả chưa xác định mà không nhân đôi tiền, ledger hoặc thông báo ngoài hệ thống.

## 2. Bản đồ các trạng thái kết quả

### 2.1. Bốn tình huống không được đánh đồng

| Tình huống | Điều ứng dụng biết | Hành động đúng |
|---|---|---|
| **Transaction bị abort rõ ràng trước commit** | Các writes trong transaction không được commit. | Nếu là transient, retry **toàn transaction** theo giới hạn; nếu business conflict, trả lỗi nghiệp vụ. |
| **Commit trả ACK thành công** | Transaction đã commit theo write concern yêu cầu. | Trả thành công, dùng transfer ID cho audit. |
| **Commit trả lỗi dứt khoát** | Có error cụ thể, nhưng phải diễn giải theo server/driver semantics. | Phân loại lỗi, không tự giả định mọi error đều là rollback. |
| **Commit result unknown** | Client không xác nhận được commit thành công hay thất bại. | Retry **commit** theo spec/driver helper hoặc xác minh bằng idempotency record; không tạo transaction mới với ID khác. |

### 2.2. Timeline: server đã commit nhưng response mất

~~~text
Client                 Primary                 Replicas
  |                       |                        |
  |--- commitTransaction ->|                        |
  |                       |--- replication ------->|
  |                       |<-- majority ACK --------|
  |                       | commit durable          |
  |  X--- network breaks -|                        |
  |                       |                        |
  |  Client gets timeout  |                        |
  |                       |                        |
  |  Outcome locally UNKNOWN                       |
~~~

Một mạng lỗi đúng thời điểm làm client **không có thông tin**, chứ không tự động làm server rollback. Các biến thể khác gồm primary stepdown, mất TCP socket, gateway hủy request hoặc application crash sau khi gửi commit.

### 2.3. Retry có hai tầng

~~~text
One business request (transferId = TR-100)
  |
  +-- HTTP/API retry by user or gateway
  |     -> must reuse same idempotency key
  |
  +-- Driver transaction retry
        |
        +-- TransientTransactionError:
        |     retry whole transaction body when appropriate
        |
        +-- UnknownTransactionCommitResult:
              retry commit of the SAME transaction when possible
~~~

**Driver retry** và **business/API retry** không giống nhau. Java driver có thể thử lại transient operations/commit với session hiện hữu; một HTTP request hoàn toàn mới sau process restart phải tìm đúng **business operation ID**, không có cách “tiếp tục session cũ” một cách tùy tiện.

### 2.4. Một nguyên tắc về “exactly once”

Mục tiêu thực tế là **exactly-once business effect** bằng idempotency/unique keys và đối soát, chứ không phải tin rằng network, HTTP, Kafka, MongoDB driver chỉ gửi một gói tin. Dữ liệu phải chịu được **at-least-once invocation**.

## 3. Kiến trúc lab và điều kiện tiên quyết

### 3.1. Topology

MongoDB multi-document transactions yêu cầu deployment hỗ trợ (replica set hoặc sharded cluster được cấu hình đúng). Một standalone `mongod` thông thường **không hỗ trợ multi-document transactions** giống replica set.

Hai cấu hình lab:

| Lab | Mục tiêu | Lưu ý |
|---|---|---|
| **Single-node replica set** | Học session, atomicity, commit/abort, transaction callback. | Không có secondary để thực hành election HA đúng nghĩa. |
| **Three-node replica set** | Học primary stepdown, server selection, majority availability, failover. | Cần hostname/ports reachable từ app, đủ members khỏe mạnh. |

Không biến single-node replica set thành một minh chứng HA; `w:"majority"` trên một node có ý nghĩa majority của **một member**, không thử được mất quorum ba node.

### 3.2. Các lệnh kiểm tra chỉ đọc

~~~javascript
// Run on the authorized lab cluster:
db.hello()
rs.status()
db.getMongo().getDBNames()
~~~

`db.hello()` cho biết primary/secondary view, hosts và setName; `rs.status()` cần quyền phù hợp và có thể không được hỗ trợ qua mọi proxy/Atlas access model. Đối chiếu:

- `setName` đúng tên replica set.
- Có **PRIMARY** và đủ secondaries khỏe mạnh cho bài failover.
- URI advertised hosts có thể resolve và connect từ nơi chạy Java.
- FCV/server version tương thích với transactions.
- User có `readWrite` trên database lab, và chỉ quản trị lab mới có quyền stepdown/failpoints.

### 3.3. Chuỗi kết nối

~~~text
mongodb://lab1.example:27017,lab2.example:27017,lab3.example:27017/txn_lab?replicaSet=rsLab&retryWrites=true
~~~

Đây là hostname giả định, không phải địa chỉ có thể kết nối thực. Với Atlas, dùng SRV URI do cluster cung cấp và secret manager. Không hardcode password, không đưa connection string chứa credentials vào logs.

### 3.4. Những điều nên cố định trong lab

1. Một database `txn_lab` dành riêng cho bài.
2. Phiên bản server/driver/Java và URI đã ghi lại.
3. Test data cô lập với người dùng thật.
4. Mọi IDs, timestamps và amounts được cố định khi chạy một kịch bản.
5. Có cách reset fixture **chỉ trong lab**, và xác nhận đúng cluster trước mọi lệnh write.
6. Có thể xem logs, events và kết quả query sau lỗi.
7. Timeouts nhỏ nhưng đủ cho lab; không dựa vào số liệu benchmark production.

### 3.5. Không bắt đầu bằng fault injection

Trước hết chạy thành công transaction **không lỗi** và kiểm business invariants. Sau đó mới tạo xung đột, abort và mô phỏng mất kết nối. Nếu baseline không ổn định, việc đưa lỗi mạng vào sẽ làm chẩn đoán không có cơ sở.

## 4. Mô hình dữ liệu chuyển tiền có kiểm chứng

### 4.1. Collections

Ta dùng bốn collections:

~~~text
accounts
  acct:A / acct:B          balances by currency

transfers
  TR-100                   stable business operation ID

ledgerEntries
  TR-100:DEBIT
  TR-100:CREDIT            postings for reconciliation

outbox
  transfer:TR-100          downstream event pending dispatch
~~~

### 4.2. Fixture và giả định

~~~javascript
const lab = db.getSiblingDB("txn_lab")

// Insert into fresh lab collections; fixed IDs make a second run
// report duplicate _id rather than silently reset balances.
lab.accounts.insertMany([
  {
    _id: "acct:A",
    currency: "VND",
    balanceMinor: NumberLong("100000"),
    version: NumberLong("0")
  },
  {
    _id: "acct:B",
    currency: "VND",
    balanceMinor: NumberLong("20000"),
    version: NumberLong("0")
  }
])

lab.accounts.createIndex({ currency: 1, balanceMinor: 1 })
lab.transfers.createIndex({ from: 1, to: 1 })
lab.ledgerEntries.createIndex({ transferId: 1 })
lab.outbox.createIndex({ eventType: 1, published: 1 })
~~~

Collection mặc định có unique index trên `_id`. Trong lab, `transfers._id` là transfer ID ổn định. Không cần tạo thêm unique index trên `_id`. Nếu API có nhiều tenants, dùng key hợp lệ như `tenantId + requestId` có canonical encoding không collision; ví dụ rút gọn chỉ dùng một tenant.

### 4.3. Invariants

Giả sử chuyển `50.000 VND` từ A sang B, không phí và không đổi currency. Trước:

~~~text
A = 100000
B =  20000
sum = 120000
~~~

Sau một transfer thành công:

~~~text
A = 50000
B = 70000
sum = 120000

ledger:
  TR-100:DEBIT  = -50000
  TR-100:CREDIT = +50000
  net = 0

transfers.TR-100.status = COMPLETED
outbox.transfer:TR-100 has one pending logical event
~~~

Điều kiện cần:

\[
A_{\mathrm{after}} = A_{\mathrm{before}} - q,\qquad
B_{\mathrm{after}} = B_{\mathrm{before}} + q,\qquad
q > 0
\]

\[
(A+B)_{\mathrm{after}} = (A+B)_{\mathrm{before}}
\]

Với hệ thống thật còn phải kiểm: quyền tài khoản, currency pair, overdraft policy, chống integer overflow, regulatory limits, ledger accounting và authorization. Không sao chép toy wallet model vào ứng dụng thanh toán thật mà chưa có kiến trúc tài chính phù hợp.

### 4.4. Vì sao không lưu tiền bằng Double?

`NumberLong("50000")` là BSON int64 cho đơn vị tiền nhỏ nhất, tránh lỗi binary floating point phổ biến với `0.1`, `0.2`. Với nhiều currencies/giá trị vượt int64 hoặc yêu cầu scale thập phân, có thể dùng Decimal128/BigDecimal theo contract. Điều quan trọng là **cùng một đơn vị/kiểu** ở accounts, transfer request và ledger.

### 4.5. Idempotency fingerprint

Một transfer ID chỉ được gắn với **một payload bất biến**:

~~~text
TR-100:
  from = acct:A
  to = acct:B
  amountMinor = 50000
  currency = VND
~~~

Nếu client gửi lại `TR-100` nhưng `amountMinor=60000`, không được trả “thành công” chỉ vì ID tồn tại. Phải so payload/fingerprint và trả **idempotency conflict**, không âm thầm thực hiện request khác.

## 5. Bài thực hành A — Nhận diện single-document atomicity

### 5.1. Một update có điều kiện

~~~javascript
lab.accounts.updateOne(
  {
    _id: "acct:A",
    currency: "VND",
    balanceMinor: { $gte: NumberLong("50000") }
  },
  {
    $inc: {
      balanceMinor: NumberLong("-50000"),
      version: NumberLong("1")
    }
  }
)
~~~

Một update trên **một document** là atomic: nếu cùng lúc có nhiều lệnh trừ tiền, predicate `balanceMinor >= 50000` được kiểm cùng với write theo semantics của MongoDB. Lệnh thành công có `matchedCount=1`; nếu thiếu tiền hoặc tài khoản không match, `matchedCount=0`. Cần kiểm response chứ không chỉ dựa vào không có exception.

**Không chạy lệnh trên cùng fixture rồi ngay lập tức làm lab transaction B** nếu muốn kỳ vọng số dư A=100.000 ban đầu. Mỗi kịch bản cần fixture riêng hoặc reset được kiểm soát, không cộng dồn một cách ngẫu nhiên.

### 5.2. Tại sao chưa đủ cho chuyển tiền?

Nếu chỉ:

~~~javascript
lab.accounts.updateOne(
  { _id: "acct:A", balanceMinor: { $gte: NumberLong("50000") } },
  { $inc: { balanceMinor: NumberLong("-50000") } }
)

// Network error / process crash at this point.

lab.accounts.updateOne(
  { _id: "acct:B" },
  { $inc: { balanceMinor: NumberLong("50000") } }
)
~~~

thì một lệnh có thể thành công còn lệnh kia chưa chạy, phá invariant tổng A+B. Hai writes độc lập lên **hai documents** không tự tạo một transaction.

### 5.3. Bài tập nhanh

Hãy dự đoán số dư và `matchedCount` nếu chạy hai trừ tiền concurrent trên A=100.000, mỗi request muốn trừ 70.000 có predicate `>=70000`. Không thể cùng trừ thành công vì sau lần đầu còn 30.000; kết quả mong đợi **tối đa một update match**. Dù vậy, điều này không bảo đảm bên nhận được cộng tiền: đó là lý do cần multi-document transaction hoặc mô hình ledger/workflow khác.

## 6. Bài thực hành B — Transaction thành công bằng mongosh

Thực hành trên **fresh fixture** `acct:A=100000, acct:B=20000`, `TR-100` chưa tồn tại. Nếu đã chạy phần `5.1`, chuẩn bị lab mới hoặc phục hồi snapshot fixture hợp lệ.

### 6.1. Session và transaction options

~~~javascript
const session = lab.getMongo().startSession()
const txDb = session.getDatabase("txn_lab")

session.startTransaction({
  readConcern: { level: "snapshot" },
  writeConcern: { w: "majority", wtimeout: 5000 },
  readPreference: { mode: "primary" }
})
~~~

- **Session** gắn các operations vào cùng logical transaction.
- `readConcern:"snapshot"` cung cấp snapshot isolation theo các điều kiện MongoDB hỗ trợ.
- `writeConcern:"majority"` trên commit yêu cầu majority acknowledgment theo semantics, cải thiện durability.
- `readPreference:"primary"` phù hợp writes trong transaction.
- `wtimeout` là thời gian chờ write concern acknowledgment, **không đồng nghĩa rollback nếu timeout**.

Không đặt options khác nhau trong mỗi thao tác ở trong transaction rồi kỳ vọng driver áp riêng lẻ; đọc docs về transaction-level settings.

### 6.2. Ghi request ID trước trong cùng transaction

~~~javascript
txDb.transfers.insertOne({
  _id: "TR-100",
  from: "acct:A",
  to: "acct:B",
  amountMinor: NumberLong("50000"),
  currency: "VND",
  status: "COMPLETED",
  createdAt: new Date()
})
~~~

Unique `_id` giúp chống tạo hai bản ghi cùng transfer ID. Nếu transaction bị abort, **insert này cũng bị rollback**, không phải một “reservation” độc lập tồn tại trước commit.

### 6.3. Trừ tiền có guard

~~~javascript
const debit = txDb.accounts.updateOne(
  {
    _id: "acct:A",
    currency: "VND",
    balanceMinor: { $gte: NumberLong("50000") }
  },
  {
    $inc: {
      balanceMinor: NumberLong("-50000"),
      version: NumberLong("1")
    }
  }
)

if (debit.matchedCount !== 1) {
  throw new Error("INSUFFICIENT_FUNDS_OR_MISSING_SOURCE")
}
~~~

Đây là **business failure**, không phải tự động một transient error cần retry 100 lần. Caller nên phân biệt không đủ tiền/tài khoản không tồn tại với network lỗi. Việc ném lỗi trong mongosh ở đây đòi hỏi ứng dụng **abort transaction** theo luồng catch/finally; xem mẫu gộp ở `6.6`.

### 6.4. Cộng tiền có guard

~~~javascript
const credit = txDb.accounts.updateOne(
  {
    _id: "acct:B",
    currency: "VND",
    balanceMinor: {
      $lte: NumberLong("9223372036854725807")
    }
  },
  {
    $inc: {
      balanceMinor: NumberLong("50000"),
      version: NumberLong("1")
    }
  }
)

if (credit.matchedCount !== 1) {
  throw new Error("MISSING_DESTINATION_OR_OVERFLOW")
}
~~~

Giới hạn trên bằng `Long.MAX_VALUE - 50000`, minh họa chống overflow int64 cho **một amount cố định**. Production phải tính predicate/giới hạn động theo amount và validate số dư không âm/scale trước khi mở transaction; đồng thời kiểm source/destination **khác nhau** và cùng currency.

### 6.5. Ledger và outbox trong cùng transaction

~~~javascript
txDb.ledgerEntries.insertMany([
  {
    _id: "TR-100:DEBIT",
    transferId: "TR-100",
    accountId: "acct:A",
    currency: "VND",
    deltaMinor: NumberLong("-50000")
  },
  {
    _id: "TR-100:CREDIT",
    transferId: "TR-100",
    accountId: "acct:B",
    currency: "VND",
    deltaMinor: NumberLong("50000")
  }
])

txDb.outbox.insertOne({
  _id: "transfer:TR-100",
  transferId: "TR-100",
  eventType: "TransferCompleted",
  published: false,
  createdAt: new Date()
})

session.commitTransaction()
session.endSession()
~~~

Trong một transaction thành công, các account updates, transfer record, ledger entries và outbox cùng commit; không có trạng thái một phần của **những writes cùng transaction** được nhìn thấy như một committed transaction. Việc gửi email/HTTP payment hay Kafka event **không nằm trong MongoDB transaction** chỉ vì outbox document được commit.

### 6.6. Mẫu gộp bảo đảm cleanup — không nhầm unknown với abort

Khi tự quản lý session/commit bằng mongosh, cần tách giai đoạn **body** khỏi **commit**:

~~~javascript
function transferOnceManually(lab, transferId, amountStr) {
  const session = lab.getMongo().startSession()
  const tdb = session.getDatabase("txn_lab")
  let commitAttempted = false

  try {
    session.startTransaction({
      readConcern: { level: "snapshot" },
      writeConcern: { w: "majority", wtimeout: 5000 }
    })

    tdb.transfers.insertOne({
      _id: transferId,
      from: "acct:A",
      to: "acct:B",
      amountMinor: NumberLong(amountStr),
      currency: "VND",
      status: "COMPLETED"
    })

    const a = tdb.accounts.updateOne(
      { _id: "acct:A",
        balanceMinor: { $gte: NumberLong(amountStr) } },
      { $inc: { balanceMinor: NumberLong("-" + amountStr) } }
    )
    if (a.matchedCount !== 1) throw Error("DEBIT_NOT_MATCHED")

    // Simplified lab demonstration. For real correctness also:
    // validate account/currency/overflow, insert ledger and outbox.
    const b = tdb.accounts.updateOne(
      { _id: "acct:B" },
      { $inc: { balanceMinor: NumberLong(amountStr) } }
    )
    if (b.matchedCount !== 1) throw Error("CREDIT_NOT_MATCHED")

    commitAttempted = true
    session.commitTransaction()
    return { state: "COMMIT_ACKNOWLEDGED", transferId }
  } catch (e) {
    if (!commitAttempted && session.inTransaction()) {
      try { session.abortTransaction() } catch (_) {}
    }
    // If commit was attempted, do NOT claim "rolled back".
    throw e
  } finally {
    session.endSession()
  }
}
~~~

Đây là **mẫu demo ngắn**, chưa tự xử lý retries/errors/verification; `session.endSession()` cleanup tài nguyên client, **không chứng minh** một commit đã được rollback. Trong code production dùng driver transaction helper và idempotency protocol ở các phần sau.

### 6.7. Sau khi commit ACK

~~~javascript
printjson(lab.accounts.find({}, { balanceMinor: 1 }).toArray())
printjson(lab.transfers.findOne({ _id: "TR-100" }))
printjson(lab.ledgerEntries.find({ transferId: "TR-100" }).toArray())
printjson(lab.outbox.findOne({ _id: "transfer:TR-100" }))
~~~

Với fixture ban đầu, A=50.000, B=70.000, transfer và 2 ledger entries tồn tại, outbox một record chưa publish. Đó là bằng chứng kiểm tra **trên lab**; không dùng `toArray()` tùy tiện với hàng triệu records.

## 7. Bài thực hành C — Abort và atomic rollback

### 7.1. Tạo một transaction cố ý abort

Trên **fixture sạch hoặc sau khi ghi nhận balances trước thử nghiệm**, chạy:

~~~javascript
const sAbort = lab.getMongo().startSession()
const dAbort = sAbort.getDatabase("txn_lab")

try {
  sAbort.startTransaction()

  dAbort.accounts.updateOne(
    { _id: "acct:A" },
    { $inc: { balanceMinor: NumberLong("-10000") } }
  )

  dAbort.accounts.updateOne(
    { _id: "acct:B" },
    { $inc: { balanceMinor: NumberLong("10000") } }
  )

  sAbort.abortTransaction()
} finally {
  sAbort.endSession()
}
~~~

### 7.2. Dự đoán

Khi cả hai writes ở trong cùng transaction và `abortTransaction()` được xác nhận trước commit, các số dư committed **không thay đổi** do transaction đó. Một người quan sát bên ngoài không thấy hai intermediate writes như các committed changes.

### 7.3. Lưu ý visibility

Một transaction có thể đọc snapshot của nó và thấy writes của chính nó; query thông thường từ session khác không đọc thấy chúng trước commit theo isolation semantics. Đừng đưa raw result trong cùng session chưa commit làm bằng chứng “đã ghi thành công vào database”.

### 7.4. Abort không giống network failure lúc commit

- **Abort ACK:** biết giao dịch bị hủy.
- **Process crash trước gửi commit:** nếu transaction chưa commit và session kết thúc, server sẽ abort khi xử lý lifecycle/timeout; cần dựa vào transaction semantics và recovery.
- **Mất mạng sau gửi commit:** client có thể không biết kết quả. Không tự xếp vào nhóm abort.

## 8. Transaction options: chọn đúng trước bài lỗi mạng

| Option | Ý nghĩa | Không đảm bảo |
|---|---|---|
| `readConcern: snapshot` | Snapshot isolation cho reads trong transaction theo prerequisites. | Không xóa mọi business write skew ngoài write conflict. |
| `writeConcern: majority` | Commit acknowledgement theo majority. | Không đồng nghĩa HTTP response chắc chắn đến client. |
| `wtimeout` | Giới hạn thời gian chờ write concern acknowledgement. | Không ép server undo write đã thực hiện. |
| `readPreference: primary` | Route operations đúng primary với transaction writes. | Không ngăn election/failover. |
| Transaction lifetime limit | Server giới hạn thời gian transaction mở. | Không phải HTTP timeout / Java socket timeout. |
| Driver socket/selection timeouts | Giới hạn chờ network/topology. | Không xác định business outcome sau timeout. |

### 8.1. Vì sao không mở transaction quá lâu?

Một transaction dài có thể:

- Giữ snapshot/history và chiếm storage/cache tài nguyên.
- Tăng xung đột writes và số lần abort/retry.
- Gặp transaction lifetime threshold của server.
- Bị ảnh hưởng bởi DDL/chunk migration tùy topology/version.
- Khiến connection/caller phải chờ lâu hơn business deadline.

Không dùng một transaction để đọc hàng triệu records rồi gọi external APIs trong nhiều phút; tách jobs/partition/ledger model hoặc workflow idempotent.

### 8.2. Transactions không thay unique index

Nếu hai requests cùng tạo `TR-100`, **unique `_id` trên transfers** bảo vệ identity. Snapshot reads/transactions không thay business idempotency constraint; cần xử lý duplicate/retries và so payload.

### 8.3. Snapshot và majority khác nhau

`readConcern:"snapshot"` kiểm read view trong transaction; `writeConcern:"majority"` là yêu cầu commit acknowledgment/durability. Đây là hai lớp khác nhau. Khi nhiều clusters tham gia, transaction trong một cluster **không bao trùm hệ thống ngoài cluster**.

## 9. Phân loại lỗi: transient vs commit outcome unknown

### 9.1. `TransientTransactionError`

Một operation trong transaction có thể thất bại do write conflict, election, network error, transient condition. MongoDB driver có thể gắn error label:

~~~text
TransientTransactionError
~~~

Thông điệp thiết kế: **transaction hiện tại không nên cố tiếp tục như không có lỗi**. Driver callback helper có thể abort và **retry toàn bộ body** từ một transaction mới nếu còn deadline và lỗi thuộc nhóm retryable.

Tình huống điển hình:

~~~text
Start transaction #1
  read / write
  -> write conflict, error label TransientTransactionError
Abort #1
Backoff within budget
Start transaction #2
  run all database operations from beginning
Commit #2
~~~

**Không phải mọi MongoDB exception đều có label này.** Duplicate key, validation, insufficient funds hoặc auth errors không tự trở thành transient. MongoDB server/driver version và lỗi cụ thể quyết định label.

### 9.2. `UnknownTransactionCommitResult`

Nếu `commitTransaction` được gửi nhưng response không nhận được, driver có thể gắn:

~~~text
UnknownTransactionCommitResult
~~~

Thông điệp: **đừng kết luận transaction đã abort**. Với session/transaction còn có thể tiếp tục, hướng retry theo transaction spec là **gửi lại `commitTransaction` của chính transaction đó**, bởi commit retry được thiết kế để không biến một transaction thành giao dịch mới.

~~~text
Transaction body succeeded
        |
        v
commitTransaction attempt #1
        |
        +-- response ACK --------> SUCCESS
        |
        +-- response lost / unknown
                |
                v
          retry commitTransaction
          SAME session + transaction
                |
                +-- ACK ----------> SUCCESS
                |
                +-- still unknown -> UNKNOWN / verify
~~~

**Không tự gọi lại toàn bộ transfer body ngay sau commit unknown**, đặc biệt nếu body có side effects ngoài MongoDB. Nếu dùng Java driver helper (`withTransaction`), helper thực hiện nhiều retry theo spec; không thêm vòng retry thủ công vô hạn bên ngoài.

### 9.3. Business conflict không phải transient infrastructure error

Ví dụ:

~~~text
Source account balance = 20,000
Requested transfer = 50,000
Conditional debit matchedCount = 0
~~~

Đây là kết quả nghiệp vụ **INSUFFICIENT_FUNDS**, không phải lỗi tạm thời nên tự động retry hàng trăm lần. Nếu account source không tồn tại, trả lỗi tương ứng; nếu user yêu cầu transferId giống nhưng payload khác, trả **IDEMPOTENCY_CONFLICT**.

### 9.4. Những error labels khác không thể bỏ qua

MongoDB drivers có các labels/error codes khác cho retryable writes, network, sharding, timeout và transactions. Một ứng dụng phải:

- Dựa vào **driver exception class, error code/labels** thay vì parse một câu message.
- Kiểm documentation đúng driver/server version.
- Tránh retry auth/validation/duplicate key/insufficient funds như transient.
- Đo số attempts thực vì driver có thể đã retry.
- Giới hạn deadline cho toàn business request.

### 9.5. Bảng quyết định thực hành

| Lỗi/kết quả | Có commit ACK? | Hành động |
|---|---|---|
 Validation trước transaction | Không bắt đầu | Trả lỗi input, không retry. |
 Insufficient funds ở debit | Chưa gửi commit | Abort; trả business conflict. |
 Duplicate transferId với payload giống | Có thể đã có một commit trước | Đọc transfer record, kiểm fingerprint/status; không chuyển lần nữa. |
 Duplicate transferId với payload khác | Không được coi request tương đương | Trả idempotency conflict. |
 Write conflict + `TransientTransactionError` trước commit | Không | Retry whole transaction theo helper/budget. |
 Server selection/network failure trước khi gửi commit, transaction đã báo abort/fail | Không | Đọc error semantics, abort/retry transaction theo label. |
 `UnknownTransactionCommitResult` trên commit | Không biết | Retry **commit same txn** nếu có thể; sau đó verify business result. |
 Majority write concern timeout lúc commit | Không đủ xác nhận | Không khẳng định rollback; retry commit/verify theo spec. |
 HTTP client disconnect sau commit request | Có thể chưa nhận ACK | Same idempotency key + status/read reconciliation. |
 Error sau commit ACK khi gửi email | Transaction đã commit | Không rollback DB bằng cách gọi lại transfer; outbox retry email riêng. |

### 9.6. Mô hình trạng thái tri-state

Tránh boolean `success` khi kết quả chưa rõ. Một internal API có thể dùng:

~~~text
COMMITTED
NOT_COMMITTED_CONFIRMED
UNKNOWN_REQUIRES_VERIFICATION
~~~

Nhóm `UNKNOWN` không có nghĩa “đã thành công 50%”; nó là trạng thái **thiếu thông tin từ phía client**. Đôi khi sau khi xác minh, kết quả là committed; đôi khi transaction chưa commit. Hãy giữ cùng business transfer ID xuyên retry/recovery.

## 10. Bài thực hành D — Java Sync Driver với `withTransaction`

Đây là phiên bản ưu tiên cho nhiều ứng dụng Java imperative: dùng driver **transaction helper**, tránh tự viết retry loop quanh mọi lệnh. Ví dụ hướng tới MongoDB Java Sync Driver 5.x; chọn artifact version theo BOM và driver documentation của dự án.

### 10.1. Dependency minh họa

~~~groovy
dependencies {
    implementation 'org.mongodb:mongodb-driver-sync:<compatible-5.x-version>'
}
~~~

Placeholder `<compatible-5.x-version>` cần được thay bằng version phù hợp; không tự phối driver mới với BOM cũ. Code mẫu tập trung vào transaction API, chưa là một service bảo mật production hoàn chỉnh.

### 10.2. Hàm chuyển tiền có guard trong callback

~~~java
import com.mongodb.ConnectionString;
import com.mongodb.MongoException;
import com.mongodb.ReadConcern;
import com.mongodb.ReadPreference;
import com.mongodb.TransactionOptions;
import com.mongodb.WriteConcern;
import com.mongodb.client.ClientSession;
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.MongoDatabase;
import com.mongodb.client.model.Filters;
import com.mongodb.client.model.Updates;
import com.mongodb.client.result.UpdateResult;
import org.bson.Document;
import java.util.List;
import java.util.concurrent.TimeUnit;

public final class TransferInTransaction {
    public static String transferOnce(
            MongoClient client, String transferId,
            String from, String to,
            long amountMinor, String currency) {

        if (transferId == null || transferId.isBlank()) {
            throw new IllegalArgumentException("transferId required");
        }
        if (from == null || to == null || from.equals(to)) {
            throw new IllegalArgumentException("invalid accounts");
        }
        if (amountMinor <= 0) {
            throw new IllegalArgumentException("amount must be positive");
        }
        if (currency == null || currency.isBlank()) {
            throw new IllegalArgumentException("currency required");
        }

        MongoDatabase db = client.getDatabase("txn_lab");
        MongoCollection<Document> accounts =
            db.getCollection("accounts");
        MongoCollection<Document> transfers =
            db.getCollection("transfers");
        MongoCollection<Document> ledger =
            db.getCollection("ledgerEntries");
        MongoCollection<Document> outbox =
            db.getCollection("outbox");

        TransactionOptions options = TransactionOptions.builder()
            .readConcern(ReadConcern.SNAPSHOT)
            .writeConcern(WriteConcern.MAJORITY
                .withWTimeout(5, TimeUnit.SECONDS))
            .readPreference(ReadPreference.primary())
            .build();

        try (ClientSession session = client.startSession()) {
            return session.withTransaction(() -> {
                // Unique _id: business idempotency anchor.
                transfers.insertOne(session, new Document()
                    .append("_id", transferId)
                    .append("from", from)
                    .append("to", to)
                    .append("amountMinor", amountMinor)
                    .append("currency", currency)
                    .append("status", "COMPLETED"));

                UpdateResult debit = accounts.updateOne(
                    session,
                    Filters.and(
                        Filters.eq("_id", from),
                        Filters.eq("currency", currency),
                        Filters.gte("balanceMinor", amountMinor)),
                    Updates.inc("balanceMinor", -amountMinor));

                if (debit.getMatchedCount() != 1) {
                    throw new IllegalStateException(
                        "SOURCE_MISSING_OR_INSUFFICIENT_FUNDS");
                }

                // Guard against signed int64 overflow on credit.
                long upperBound = Long.MAX_VALUE - amountMinor;
                UpdateResult credit = accounts.updateOne(
                    session,
                    Filters.and(
                        Filters.eq("_id", to),
                        Filters.eq("currency", currency),
                        Filters.lte("balanceMinor", upperBound)),
                    Updates.inc("balanceMinor", amountMinor));

                if (credit.getMatchedCount() != 1) {
                    throw new IllegalStateException(
                        "DESTINATION_MISSING_OR_OVERFLOW");
                }

                ledger.insertMany(session, List.of(
                    new Document("_id", transferId + ":DEBIT")
                        .append("transferId", transferId)
                        .append("accountId", from)
                        .append("currency", currency)
                        .append("deltaMinor", -amountMinor),
                    new Document("_id", transferId + ":CREDIT")
                        .append("transferId", transferId)
                        .append("accountId", to)
                        .append("currency", currency)
                        .append("deltaMinor", amountMinor)));

                outbox.insertOne(session, new Document()
                    .append("_id", "transfer:" + transferId)
                    .append("transferId", transferId)
                    .append("eventType", "TransferCompleted")
                    .append("published", false));

                return transferId;
            }, options);
        }
    }
}
~~~

Giải thích:

- `ClientSession` xác định scope transaction; collection methods nhận **session** ở mỗi write.
- `withTransaction` thực hiện commit/abort và hỗ trợ transaction retry/commit retry theo Java driver specs; callback **có thể chạy lại**.
- Unique IDs trên `transfers`, `ledgerEntries`, `outbox` ngăn duplicate effect nếu business request được lặp nhưng phải xử lý conflict/verify.
- Debit dùng atomic predicate và check matchedCount.
- Credit có guard int64 overflow cho amount >0. Account balances ban đầu phải có correct BSON int64 và business range; không dùng mixed numeric types.
- Code chưa kiểm ACL/tenant, limits/currency exponent, idempotency fast path, full exception API response, audit/recovery hay application deadline. Đây là **lab example** để hiểu cơ chế.

### 10.3. Vì sao không gửi email trong transaction callback?

**Sai:**

~~~java
session.withTransaction(() -> {
    // MongoDB operations...
    emailClient.sendTransferConfirmation(transferId);
    return transferId;
}, options);
~~~

Nếu transaction callback bị retry, email có thể gửi nhiều lần; nếu DB abort sau email, user nhận thông báo giả. **Đúng hơn:** ghi `outbox` trong transaction; một worker khác publish email/event sau commit với idempotent delivery.

### 10.4. Đừng catch và nuốt MongoException trong body

**Nguy hiểm:**

~~~java
session.withTransaction(() -> {
    try {
        accounts.updateOne(session, filter, update);
    } catch (MongoException e) {
        log.warn("ignore and continue", e);
    }
    return "OK";
});
~~~

Transaction có thể đã bị server đánh dấu abort hoặc body thiếu write quan trọng. Không nuốt lỗi rồi trả success. Nếu thật sự có optional operation, phải hiểu transaction state và business invariants; lỗi write-critical phải **propagate** để helper abort/retry đúng.

### 10.5. Callback có thể chạy lại, source data có thể thay đổi

Vì retry whole body sử dụng snapshot mới, một concurrent transfer khác có thể đổi số dư giữa attempts. Không cache `balanceMinor` từ một lần đọc trước transaction rồi áp sang attempt sau; dùng **conditional update** làm guard thực tế. Với nghiệp vụ yêu cầu price quote/FX rate bất biến, persist reference/rate contract và verify consistency thay vì đọc tỷ giá mới trong mỗi callback retry mà không được business cho phép.

## 11. Bài thực hành E — Java tự quản lý commit: thấy rõ hai vòng retry

Để hiểu driver helper, có thể xem **pseudocode thuật toán** (không phải copy-paste production):

~~~text
function withTransaction(body, deadline):
  while before deadline:
    session.startTransaction()
    try:
      result = body()
    catch e:
      abortTransactionIfPossible()
      if e.hasLabel(TransientTransactionError) and budget:
        backoff()
        continue  // WHOLE transaction
      throw e

    while before deadline:
      try:
        commitTransaction()
        return result
      catch e:
        if e.hasLabel(UnknownTransactionCommitResult) and budget:
          backoff()
          continue  // COMMIT same transaction
        if e.hasLabel(TransientTransactionError) and policy says retry body:
          break     // restart whole transaction
        throw e

  throw DeadlineExceededOrUnknownOutcome
~~~

Đây chỉ là sơ đồ **ý nghĩa**; driver specification có nhiều ngoại lệ, timeout handling, labels và server-version behavior chi tiết hơn. Không triển khai vòng retry nhà làm chỉ bằng snippet này vì có thể sai với write concern errors, commit retries, session lifecycle, transaction numbers và driver CSOT.

### 11.1. Nhận diện error labels trong Java

~~~java
try {
    String result = TransferInTransaction.transferOnce(
        client, "TR-200", "acct:A", "acct:B", 5000L, "VND");
    System.out.println("Commit ACK for " + result);
} catch (MongoException e) {
    if (e.hasErrorLabel("UnknownTransactionCommitResult")) {
        // Do not declare rollback.
        // Proceed with controlled verification of TR-200.
        System.err.println("COMMIT_OUTCOME_UNKNOWN: TR-200");
    } else if (e.hasErrorLabel("TransientTransactionError")) {
        // Driver helper may already have retried;
        // preserve deadline and original idempotency key.
        System.err.println("TRANSIENT_TRANSACTION_FAILURE");
    } else {
        System.err.println("MONGO_FAILURE: " + e.getCode());
    }
}
~~~

Đây là **phân loại sau khi helper trả lỗi**; không tạo vòng retry vô hạn từ Java catcher. `hasErrorLabel` nhận string, nên cần dùng error-label name đúng spec và cập nhật theo driver version.

### 11.2. Java retryable writes khác transaction retry

MongoDB Java driver có `retryWrites=true` theo điều kiện deployment/operation. Retryable write ngoài transaction dùng protocol hỗ trợ để cố gắng không apply một eligible write hai lần trong một logical attempt. Nhưng:

- Không phải mọi write operation đều retryable.
- Không phải mọi lỗi/network fail đều được retry.
- Một HTTP request **mới** có thể có session/transaction IDs mới.
- Tránh tạo **random business ID mới** trên mỗi retry.
- Transaction callback retry và commit retry có semantics riêng.

Vì vậy giữ idempotency record/unique key **ở tầng nghiệp vụ**, không phụ thuộc `retryWrites` là bảo vệ duy nhất.

### 11.3. Hạn mức retry

Giả sử API deadline 2 giây, driver selection 1 giây, callback có 2 DB queries và commit có thể retry. Cần tính **remaining total request budget**. Retry thành công sau khi client HTTP timeout có thể khiến request trước hoàn tất trong DB nhưng client không biết. Kết hợp:

- Deadline rõ ở ingress.
- Attempt cap/backoff với jitter.
- Metric retry attempts.
- Stable transferId.
- Status lookup/verification khi unknown.

Không đặt mọi retries bằng `while(true)` hay “retry trong 60 giây” khi SLO chỉ cho 500 ms.

## 12. Bài thực hành F — API idempotency khi client gửi lại request

### 12.1. Một HTTP retry độc lập với transaction driver

Giả sử client gọi:

~~~http
POST /transfers
Idempotency-Key: TR-100
Content-Type: application/json

{
  "from": "acct:A",
  "to": "acct:B",
  "amountMinor": 50000,
  "currency": "VND"
}
~~~

Nếu gateway timeout nhưng DB commit, client có thể gửi lại **cùng request với cùng `Idempotency-Key`**. Service không được tạo `TR-101` chỉ để “thử lại một lần nữa”.

### 12.2. Unique operation record là bằng chứng durable

Một record:

~~~javascript
{
  _id: "TR-100",
  requestFingerprint: "<canonical-request-hash>",
  from: "acct:A",
  to: "acct:B",
  amountMinor: NumberLong("50000"),
  currency: "VND",
  status: "COMPLETED",
  committedAt: ISODate("2026-11-14T03:00:00Z")
}
~~~

`transfers` record được **insert cùng transaction** với hai account updates và ledger. Vì vậy sự tồn tại của record committed với payload đúng là bằng chứng đã chạy workflow tới commit, trong phạm vi contract. `requestFingerprint` phải được tính từ các trường payload canonicalized và policy có version; không lưu placeholder ở production.

### 12.3. Logic xử lý request đã tồn tại

~~~text
receive transferId + payload
          |
          v
validate authentication / tenant / amount / currency
          |
          v
read transfers[transferId] with approved consistency
          |
          +-- exists, same fingerprint, COMPLETED
          |       -> return original result, NO debit
          |
          +-- exists, different fingerprint
          |       -> return IDEMPOTENCY_CONFLICT
          |
          +-- exists, in-progress state (if separate request ledger)
          |       -> return PENDING/verify/retry later
          |
          +-- missing
                  -> attempt transaction with UNIQUE transfer ID
                  -> on duplicate/conflict, re-read and classify
                  -> on unknown commit, verify same ID
~~~

**Read-before-write không đủ chống race**. Hai requests có thể cùng đọc “missing” rồi cùng bắt đầu transaction. **Unique index** và handling write conflicts/duplicate key là lớp bảo vệ cuối cùng; đừng coi pre-check là atomic lock.

### 12.4. So fingerprint thế nào?

Canonical input nên gồm:

~~~text
tenantId
authenticated initiator / scope
fromAccount
toAccount
amountMinor (int64 semantics)
currency
business purpose/version if relevant
~~~

Không hash raw JSON string nếu property order/whitespace có thể đổi. Dùng deterministic encoding hoặc canonical JSON có version. Hãy kiểm **tính hợp lệ của input mới** trước khi so/cho trả lại kết quả cũ; không để user không được phép truy vấn trạng thái transfer của tenant khác chỉ vì biết ID.

### 12.5. Xử lý duplicate key đúng

~~~java
try {
    return TransferInTransaction.transferOnce(
        client, transferId, from, to, amount, currency);
} catch (MongoException e) {
    // The exact error class/code depends on operation/server/driver.
    // Duplicate-key 11000 is one possible result for reused ID.
    if (e.getCode() == 11000) {
        // Read committed transfer record with suitable consistency;
        // compare canonical payload and return previous result if same.
    }
    throw e;
}
~~~

Đoạn này minh họa **decision point**: khi duplicate key, không trả success mù. Đọc record đã commit và xác thực payload/status/tenant, hoặc báo `409 Conflict` khi cùng ID nhưng payload khác. Một duplicate key trên **ledger/outbox khác** có thể là data corruption, không phải request đã hoàn tất; phải biết constraint nào gây lỗi.

### 12.6. Một ledger request riêng trước transaction?

Đôi khi ứng dụng tạo `idempotencyRequests` với `PENDING` **trước khi** mở transaction:

~~~text
HTTP request accepted
  |
  v
INSERT PENDING(idempotencyKey, fingerprint, lease/owner)
  |
  v
execute transaction
  |
  +-- commit -> mark result COMPLETED
  |
  +-- timeout/worker crash -> recovery worker verifies outcome
~~~

Cách này hỗ trợ status polling và dedupe concurrent callers, nhưng thêm **state machine riêng**: PENDING có thể bị bỏ dở khi process crash; phải có lease/expiry/owner fencing, recovery, atomic transitions và phân biệt “chưa chạy” với “chưa biết kết quả”. Không đặt TTL tự xóa PENDING trước khi chắc chắn không còn side effect. Nếu chưa cần persistent pending, dùng `transfers` record committed + gateway idempotency cache đúng policy, nhưng đừng giả vờ xử lý unknown result chỉ với cache memory trong process.

### 12.7. HTTP response khi outcome unknown

Không tự trả `200 OK`, cũng không luôn trả `500 retry with new ID`. Một API có thể:

- Trả trạng thái riêng `UNKNOWN/PENDING_VERIFICATION` và `operationId` qua job/status protocol **nếu backend có durable state để tra cứu**.
- Hoặc trả `503`/`504` với thông báo “không xác nhận được kết quả, dùng lại cùng Idempotency-Key, kiểm status endpoint”, không tiết lộ internal DB topology.
- Với `409`, chỉ báo payload khác một key đã sử dụng; không cho user ghi đè.

`202 Accepted` chỉ nên dùng nếu hệ thống đã **durably accepted** request và có cơ chế tiếp tục/phản hồi trạng thái. Đừng dùng 202 để giấu unknown outcome mà không có nơi tra cứu.

### 12.8. Retry của client cũng phải bounded

Client HTTP có thể retry theo exponential backoff + jitter, giới hạn attempts/total deadline. Nếu tất cả clients retry cùng 1 giây, primary mới sau failover có thể chịu **retry storm**. Status endpoint/read-repair giúp tránh gọi lại write path quá nhiều khi chỉ cần biết outcome.

## 13. Bài thực hành G — Đối soát outcome sau commit không xác định

### 13.1. Ba nguồn bằng chứng

Sau `UnknownTransactionCommitResult`, có thể kiểm:

1. `transfers[transferId]` có committed record đúng fingerprint/status không?
2. `ledgerEntries` có đúng debit/credit legs và balanced sum không?
3. `accounts` có invariant phù hợp khi ghép với ledger không?

**Không** dùng riêng số dư hiện tại để kết luận một transfer đã chạy, vì cùng lúc có thể có **các transfers khác** lên hai accounts. Transfer record và ledger với stable IDs là bằng chứng trực tiếp hơn.

### 13.2. Query xác minh bằng mongosh

~~~javascript
const t = lab.transfers.findOne({ _id: "TR-100" })
const legs = lab.ledgerEntries
  .find({ transferId: "TR-100" })
  .toArray()

printjson({ transfer: t, ledger: legs })
~~~

Ở lab nhỏ, `toArray()` lấy tối đa hai ledger legs theo contract. Với ledger lớn/real system, giới hạn query và check unique keys; tránh xuất PII. Query này **chưa phải cùng một snapshot** nếu các collections đang thay đổi; muốn bằng chứng consistent cần read concern/snapshot policy.

### 13.3. Kiểm tổng ledger theo transferId

~~~javascript
lab.ledgerEntries.aggregate([
  { $match: { transferId: "TR-100" } },
  {
    $group: {
      _id: "$transferId",
      n: { $sum: 1 },
      netMinor: { $sum: "$deltaMinor" },
      types: { $addToSet: { $type: "$deltaMinor" } },
      accounts: { $addToSet: "$accountId" }
    }
  }
])
~~~

Với toy model, cần **n=2**, netMinor=0, types chỉ gồm `long`, account IDs đúng và có đúng một debit/credit. Nếu không thấy transfer record và ledger, **không lập tức kết luận NOT_COMMITTED** sau một commit timeout: primary election, replication lag, stale reads hoặc in-flight commit còn đang xử lý có thể khiến chứng cứ chưa đủ.

### 13.4. Mức nhất quán của verification read

Với replica set khỏe mạnh, có thể đọc bằng `readPreference primary` và `readConcern majority` để giảm rủi ro đọc rollback-able data. Tuy nhiên một majority read **không tạo snapshot chung** giữa hai independent queries nếu không dùng transaction/snapshot, và absence không tuyệt đối chứng minh commit chưa từng/không còn có thể diễn ra.

Trong recovery protocol, cần:

- Chờ cluster trở lại trạng thái có eligible primary/quorum.
- Kiểm kết quả với cùng transferId và payload.
- Nếu không có record, giữ `UNKNOWN` đến khi retry/verification protocol có thể kết luận theo thời hạn/fencing.
- Nếu an toàn chạy lại logic idempotent, dùng **cùng key**, không tạo business ID mới.
- Có escalation/manual review khi outcome không thể xác minh.

### 13.5. Không dùng “đếm chênh tổng A+B” làm câu trả lời duy nhất

Nếu A và B đang nhận các transfers khác, tổng có thể vẫn bằng 120.000 dù `TR-100` không chạy; hoặc tổng có thể thay đổi vì nạp/rút tiền hợp lệ khác. Cần **event/ledger identity** và đối soát theo transferId, không chỉ aggregate snapshot của hai tài khoản.

### 13.6. Kịch bản process chết sau commit

~~~text
1. HTTP request TR-100 arrives.
2. MongoDB transaction commits.
3. Process crashes before returning HTTP 201.
4. Client retries TR-100 through another pod.
5. Pod reads committed transfers.TR-100.
6. Fingerprint matches -> return original completed result.
7. NO second debit or credit.
~~~

Đây là ví dụ rõ nhất vì sao **idempotency record thuộc dữ liệu durable**, không nên chỉ để một cờ trong bộ nhớ JVM.

### 13.7. Recovery worker và trạng thái uncertain

Một worker độc lập có thể quét idempotencyRequests đang `PENDING_VERIFICATION`, kiểm trạng thái MongoDB và reconciliation. Workflow:

~~~text
PENDING_VERIFICATION
        |
        +--> transfer record matches + invariants
        |       -> COMPLETED_VERIFIED
        |
        +--> same ID but payload differs
        |       -> CONFLICT / MANUAL_INVESTIGATION
        |
        +--> no conclusive evidence yet
        |       -> RETRY_LATER with backoff
        |
        +--> controlled idempotent re-execution authorized
                -> use SAME transferId, verify again
~~~

Không chuyển một request sang `FAILED` chỉ vì 3 lần query bị server selection timeout; đó là **monitoring/recovery failure**, không phải chứng minh chuyển tiền không xảy ra.

## 14. Bài thực hành H — Mô phỏng primary stepdown trên replica set lab

### 14.1. Mục tiêu

Quan sát:

- Transaction đang chạy bị xung đột/fail khi primary thay đổi.
- Driver SDAM cập nhật cluster description.
- Lệnh mới chờ server selection.
- Một số lỗi có thể mang `TransientTransactionError` hoặc `UnknownTransactionCommitResult` tùy **chính xác thời điểm** mạng/election xảy ra.

**Không bảo đảm** mỗi lần stepdown sẽ tạo `UnknownTransactionCommitResult`. Nếu client chưa gửi commit, outcome thường không phải unknown-commit; nếu commit đã ACK, có thể chẳng thấy lỗi nào. Đây là bài về **phân loại thời điểm**, không phải ép xuất hiện một label bằng may rủi.

### 14.2. Điều kiện

- Một **3-node replica set lab** có healthy electable secondary.
- Không có traffic của người dùng thật, có quyền cluster admin cho lab.
- App dùng seed list/replicaSet URI đúng, không `directConnection=true` tới một primary cũ.
- Metrics/trace có correlation ID cho mỗi request.
- Script khởi tạo fixture riêng, không reuse `TR-100` đã commit nếu muốn test transaction mới.

### 14.3. Chạy transaction lặp có giới hạn trên lab

Ví dụ một worker chạy một loạt transfer IDs khác nhau với amount nhỏ, **có giới hạn số lượng**:

~~~text
TR-LAB-001: transfer 100
TR-LAB-002: transfer 100
TR-LAB-003: transfer 100
...
TR-LAB-010: transfer 100
~~~

Trên terminal khác, kết nối trực tiếp **primary của lab**, kiểm `rs.status()` rồi chủ động stepdown:

~~~javascript
// ONLY on an authorized, disposable replica set primary in LAB:
rs.stepDown(15)
~~~

Lệnh có thể ngắt mongosh session, khiến primary cũ không nhận writes một thời gian và thúc đẩy election nếu secondary đủ điều kiện. Nó **ảnh hưởng availability**; không chạy trên production. Nếu không có electable secondary/quorum, lệnh có thể fail hoặc tạo downtime không mong muốn. Không dùng `force:true` để vượt kiểm tra an toàn chỉ nhằm tạo bài học.

### 14.4. Ghi lại timeline

~~~text
time       event
--------   ---------------------------------------------------
12:00:00   TR-LAB-003 body started on primary A
12:00:01   PRIMARY A stepdown initiated
12:00:02   Server selection fails / SDAM sees topology change
12:00:04   SECONDARY B elected PRIMARY
12:00:05   Driver selects B, retries eligible transaction
12:00:06   TR-LAB-003 eventually acknowledged or reported unknown
~~~

Thời điểm và kết quả là **kịch bản minh họa**, không phải log từ lab đã chạy. Phải ghi **actual** Java timestamps, error codes/labels, command events và DB outcome khi thực hành.

### 14.5. Điều cần rút ra

Nếu driver ghi lỗi lúc **body trước commit**, retry transaction có thể cần thiết. Nếu lỗi ở **commit result**, không được khởi động transfer hoàn toàn mới với ID khác. Sau election, verify bằng stable transferId; nếu client đã dùng `withTransaction`, nhớ helper có thể đã retry nội bộ.

### 14.6. Khi cluster chưa có primary

`serverSelectionTimeoutMS` có thể hết hạn; lỗi loại này nói **client chưa tìm thấy eligible server** tại thời điểm chọn. Không tăng connection pool vô hạn để chữa primary election. Chọn request deadline/fallback phù hợp; với writes đang có outcome ambiguous, giữ trạng thái xác minh thay vì tuyên bố thất bại dứt khoát.

## 15. Bài thực hành I — Mất kết nối đúng ranh giới commit

### 15.1. Những điểm ngắt cần phân biệt

~~~text
P0 before transaction start
P1 after first debit, before credit
P2 after all writes, before commit send
P3 commit sent, before server applies
P4 commit applied, before client receives ACK
P5 after commit ACK, before HTTP response
~~~

| Điểm | Điều ta có thể suy luận |
|---|---|
| P0 | Request chưa bắt đầu DB transaction, nhưng phải chắc không có attempt cũ cùng key. |
| P1 | Nếu transaction chưa commit và bị abort, debit không tồn tại như committed write. |
| P2 | Nếu commit chưa gửi, transaction chưa thành công; session/timeout xử lý abort. |
| P3 | Client không chắc server đã nhận/áp commit hay không. |
| P4 | Server có thể đã commit, client không biết. |
| P5 | Database commit thành công; HTTP client vẫn có thể nhìn thấy timeout và retry. |

Điểm **P3/P4** là lý do cụ thể cho `UnknownTransactionCommitResult`/verification. Không dùng một network error string để xác định chính xác điểm P nào nếu không có instrumentation.

### 15.2. Mô phỏng bằng fault proxy/test harness

Để tái hiện **commit response lost**, dùng một lab test harness/proxy có khả năng:

1. Để commit request **thực sự tới server**.
2. Cho server thực hiện commit.
3. Cố ý drop/delay **response** trên đường về client.
4. Ghi transferId, transaction attempt, timestamps và observed driver errors.
5. Sau đó tắt fault và đọc DB để xác minh.

Không chỉ “tắt network trước khi gửi commit” rồi tuyên bố đã kiểm unknown commit. Với Toxiproxy/Chaos Mesh/fault-injection frameworks, cấu hình cụ thể phụ thuộc network topology/TLS và phải được cấp phép; interceptor sai vị trí có thể chặn **trước khi server commit**, tạo case khác.

### 15.3. MongoDB `failCommand` test failpoint

Một số test deployments có failpoint `failCommand` để đưa lỗi vào command, kể cả các commands giao dịch tùy server/test enablement. **Không mặc định failpoint có thể sử dụng trên Atlas/production**, và một failpoint `closeConnection` khi nhận `commitTransaction` có thể đóng kết nối **trước khi commit được thực hiện**, không tự chứng minh case “server committed but response lost”. Cần xác minh vị trí fault theo server traces và tham khảo đúng test framework.

### 15.4. Dự đoán ba lần thử

- **Lần A:** Drop request trước khi commit tới server → không thể khẳng định commit xảy ra; transaction có thể abort sau timeout.
- **Lần B:** Drop response sau server đã majority commit → client timeout/unknown nhưng transfer record/ledger vẫn hiện diện.
- **Lần C:** Không drop gì → commit ACK rõ; HTTP vẫn có thể timeout nếu network phía gateway khác.

Đầu ra mong đợi là **phân loại tình huống theo bằng chứng**, không phải tỉ lệ các error labels cố định.

### 15.5. Nếu không dựng được proxy?

Có thể viết integration test **mock transaction gateway** trả `UNKNOWN` sau khi repository đã hoàn thành, để kiểm **application idempotency/status recovery**. Test này chứng minh **logic ứng dụng** đúng với injected ambiguity, không chứng minh MongoDB driver ở runtime sẽ trả đúng exception class/label trong một network fault thật.

### 15.6. Quan sát kết quả bằng same ID

Sau khi fault được gỡ:

~~~javascript
lab.transfers.findOne({ _id: "TR-LAB-007" })
lab.ledgerEntries.find({ transferId: "TR-LAB-007" })
~~~

Nếu thấy transfer và hai legs đúng, không thực hiện lại với `TR-LAB-007-RETRY`. Nếu không thấy record, **không suy absent tức rollback ngay khi cluster vừa mất quorum**; làm verification đúng deadline, consistency và retry policy.

## 16. Bài thực hành J — Hai requests cạnh tranh và write conflict

### 16.1. Cùng tài khoản, hai transfer IDs khác nhau

Ban đầu tài khoản A có 100.000. Hai request đến đồng thời:

~~~text
TR-C1: A -> B amount 80000
TR-C2: A -> C amount 80000
~~~

Theo policy **không cho overdraft**, hai requests không thể đều thành công. MongoDB transaction giúp đảm bảo các writes của **mỗi transfer** atomic; predicate `balanceMinor >= amount` giúp kiểm điều kiện tồn tại tại lúc ghi. Concurrent transactions có thể sinh **write conflict** và được driver helper retry theo transient labels, rồi một request nhìn số dư mới, không đủ tiền và phải trả business conflict.

### 16.2. Không thay guard bằng một read đơn thuần

**Sai:**

~~~text
T1 reads A = 100000
T2 reads A = 100000
T1 decides 80000 is affordable
T2 decides 80000 is affordable
~~~

Read-before-write không đủ nếu không có conditional update/version checks. Transaction snapshot không bảo đảm một business decision đọc từ document sẽ **không bao giờ stale**; guard tại write là lớp cần thiết.

### 16.3. Bài lab đồng thời có giới hạn

Trên fixture có A=100.000 và B/C hợp lệ, chạy hai tasks bằng một executor hai workers, mỗi task gọi `TransferInTransaction.transferOnce(...)` với ID riêng `TR-C1`/`TR-C2`. Đừng viết thread spawn không giới hạn. Sau khi cả hai tasks đã hoàn tất hoặc trả lỗi:

1. Xác minh tối đa một transfer status COMPLETED theo contract.
2. Tính tổng account balances và ledger legs liên quan.
3. Kiểm không có amount âm ở A nếu overdraft bị cấm.
4. Kiểm logs có write conflict/transient retry không (có thể có hoặc không, phụ thuộc scheduler).
5. Không dựa vào thứ tự task submit để đoán transfer nào thắng.

### 16.4. Cùng transferId đến hai pods

Hai requests với **cùng `TR-C1`** có thể cùng đọc “missing” trước khi transaction khởi chạy. Cần unique record/conditional write để một business effect duy nhất commit. Nếu một caller bị duplicate key/write conflict, **verify transfer record** và trả original result khi payload giống; không khởi tạo `TR-C1-2`.

### 16.5. Write conflict không tự là lỗi ứng dụng cuối cùng

Nếu driver helper retry và transaction hoàn tất trong deadline, HTTP có thể trả success dù log thấy một transient conflict ở attempt đầu. Nếu retries hết budget, trả trạng thái phù hợp và giữ stable ID. Tránh hiện chi tiết nội bộ “WiredTiger write conflict at X” cho người dùng.

## 17. Majority write concern, timeout và durability

### 17.1. `wtimeout` không phải timeout toàn transaction

Nếu commit dùng:

~~~javascript
writeConcern: { w: "majority", wtimeout: 5000 }
~~~

`wtimeout=5000` giới hạn thời gian chờ **majority acknowledgement**. Một timeout tại đây không bảo đảm write bị rollback. Lệnh có thể đã được primary áp dụng, và kết quả phụ thuộc replication/quorum/failover.

### 17.2. Điều gì khi mất quorum?

Trên replica set 3 nodes, nếu đủ members không thể xác nhận majority, một số writes/commits không thể hoàn tất majority acknowledgement theo deadline. Nhưng **tắt/quấy rối hai nodes** là thử nghiệm gây outage, chỉ làm trên lab disposable có điều khiển; không cần cố gây tình trạng này trên production để học.

### 17.3. Write concern khác read concern

| Câu hỏi | Cơ chế liên quan |
|---|---|
| “Có bao nhiêu members xác nhận commit?” | `writeConcern`. |
| “Transaction đọc một view nhất quán nào?” | `readConcern`. |
| “Client có nhận response commit hay không?” | Network/socket/driver retry. |
| “Một request trùng có làm chuyển tiền hai lần?” | Idempotency key + unique constraint/business protocol. |
| “Ledger có cân bằng?” | Independent business reconciliation. |

Không lấy `w:"majority"` làm bằng chứng **HTTP exactly once**, cũng không lấy `readConcern:"snapshot"` làm bằng chứng external email đã được gửi đúng một lần.

### 17.4. `retryWrites` và rollback

Server có thể rollback một số writes chưa majority committed khi primary failover theo replication semantics; majority commit có độ bền mạnh hơn theo điều kiện của deployment. Nhưng response timeout không cho client biết chính xác branch nào xảy ra. Với operation critical, yêu cầu phù hợp về write concern, verify với consistency policy và idempotency thay vì suy luận từ network error.

### 17.5. Client operation timeout

Java driver có nhiều timeout layers: server selection, socket/network, connection checkout, server-side `maxTimeMS` và trong driver versions hỗ trợ **client-side operation timeout (CSOT)**. Ngoài ra HTTP gateway có deadline. Chúng **không đồng nhất**, và cancellation tại một tầng không luôn dừng server command đã gửi.

~~~text
HTTP request deadline
  |
  +-- app request queue
  +-- server selection
  +-- connection checkout
  +-- transaction body commands
  +-- commit/retry and verification
  +-- HTTP response serialization
~~~

Thiết kế deadline từ **business SLO**, giữ phần thời gian cho recovery/status response, và tránh tự nới tất cả timeout lên nhiều phút để “không còn lỗi”.

### 17.6. Tránh công thức “tăng timeout là xong”

Khi primary unavailable, `serverSelectionTimeoutMS` dài hơn làm client chờ lâu hơn, không làm primary xuất hiện. Khi CPU DB saturated, tăng socket timeout có thể che queue buildup. Khi commit unknown, timeout dài hơn **không tự cung cấp idempotency**. Quan sát stage bị chậm rồi chọn action phù hợp.

## 18. Outbox: đưa side effects ra ngoài transaction nhưng vẫn có thể phục hồi

### 18.1. Vấn đề gửi email trước commit

~~~text
MongoDB transaction opened
  debit/credit prepared
  send email "Transfer completed"
  transaction aborts
~~~

Email đã gửi không được MongoDB rollback. Tương tự payment SDK/call HTTP/Kafka publish là **external side effects** không tự tham gia MongoDB transaction.

### 18.2. Transactional outbox

~~~text
One MongoDB transaction:
    update accounts
    insert transfer record
    insert ledger entries
    insert outbox event PENDING
       |
       v
COMMIT
       |
       v
Outbox publisher (separate job)
    read pending events
    publish to broker/email service
    mark published or checkpoint
~~~

Nếu transaction abort, không có outbox event committed. Nếu commit nhưng publisher crash, event vẫn pending và có thể được gửi sau. **Không bảo đảm exactly-once publish**: publisher có thể gửi thành công rồi crash trước khi đánh dấu published.

### 18.3. Idempotent publish/consume

Mỗi event có stable ID:

~~~json
{
  "_id": "transfer:TR-100",
  "transferId": "TR-100",
  "eventType": "TransferCompleted",
  "published": false
}
~~~

Consumer nên lưu processed event ID hoặc dùng provider idempotency key, và chỉ xử lý event lần đầu trong phạm vi policy. Nếu broker nhận cùng event hai lần, downstream không nên gửi hai hóa đơn hoặc trừ tiền hai lần.

### 18.4. Lịch sử publish cần audit

Outbox worker nên giữ:

- Event ID + transfer ID.
- Attempts count, nextRetryAt, lastErrorCode (redacted).
- PublishedAt/ack evidence.
- Lease/owner fencing cho nhiều workers.
- Dead-letter/manual review khi retries vượt ngưỡng.

Không xóa outbox event trước khi có confirm theo protocol. Unique `_id` giúp dedupe logical event, nhưng không thay consumer idempotency.

### 18.5. Khi nào dùng saga?

Nếu một business operation phải phối hợp MongoDB, payment gateway và inventory service khác nhau, một transaction MongoDB không bao trùm cả ba. **Saga** chia thành các bước local transaction có retry/compensation và idempotent state machine. Compensation không đồng nghĩa rollback vật lý tuyệt đối: hoàn tiền là một **nghiệp vụ mới có audit**, không xóa quá khứ payment đã captured.

## 19. Kiểm chứng independent business invariants

### 19.1. Accounts có đúng tài khoản và currency không?

~~~javascript
lab.accounts.find(
  { _id: { $in: ["acct:A", "acct:B"] } },
  { balanceMinor: 1, currency: 1, version: 1 }
)
~~~

Trong lab cô lập, tổng A+B trước/sau phải giữ 120.000, nếu chỉ có các transfers nội bộ không phí. Nếu accounts có các movements khác, so tổng hiện tại **không đủ** để xác định riêng `TR-100`.

### 19.2. Ledger per-transfer

~~~javascript
lab.ledgerEntries.aggregate([
  { $match: { transferId: "TR-100" } },
  {
    $group: {
      _id: "$transferId",
      entries: { $sum: 1 },
      netDelta: { $sum: "$deltaMinor" },
      dataTypes: { $addToSet: { $type: "$deltaMinor" } },
      accounts: { $addToSet: "$accountId" }
    }
  }
])
~~~

Với toy transfer không phí, kỳ vọng 2 entries, netDelta=0, type `long`, account A/B đúng. Nhưng netDelta=0 **chưa đủ**: hai entries sai dấu/ID có thể tự bù; so per-leg IDs/amount/currency/status.

### 19.3. Tìm transfer có ledger sai count

~~~javascript
lab.ledgerEntries.aggregate([
  {
    $group: {
      _id: "$transferId",
      n: { $sum: 1 },
      net: { $sum: "$deltaMinor" }
    }
  },
  {
    $match: {
      $or: [
        { n: { $ne: 2 } },
        { net: { $ne: 0 } }
      ]
    }
  }
])
~~~

Đây là rule **chỉ cho toy model hai legs/không phí**. Trong ledger thật có multi-leg/fees/currency, định nghĩa đúng debit-credit balance theo business. Quan trọng: `$sum` có thể bỏ non-numeric values, nên phải kiểm `$type`/required fields trước khi cho kết quả PASS.

### 19.4. Tìm transfer không có đủ legs

~~~javascript
lab.transfers.aggregate([
  {
    $lookup: {
      from: "ledgerEntries",
      localField: "_id",
      foreignField: "transferId",
      as: "legs"
    }
  },
  {
    $match: {
      $expr: { $ne: [{ $size: "$legs" }, 2] }
    }
  },
  {
    $project: {
      _id: 1,
      status: 1,
      nLegs: { $size: "$legs" }
    }
  }
])
~~~

Chỉ dùng trên cùng database và dataset vừa phải, với index `ledgerEntries.transferId`. Một `$lookup` tạo array lớn có resource limits, nên production reconciliation nên stream theo partition, không join toàn bộ ledger vài TB trong một query không có guard.

### 19.5. Outbox không bị mất

~~~javascript
lab.transfers.aggregate([
  {
    $lookup: {
      from: "outbox",
      let: { tid: "$_id" },
      pipeline: [
        { $match: {
            $expr: { $eq: ["$transferId", "$$tid"] }
        }}
      ],
      as: "events"
    }
  },
  {
    $match: {
      $expr: { $ne: [{ $size: "$events" }, 1] }
    }
  }
])
~~~

Kỳ vọng mỗi completed transfer có đúng một **logical outbox event**; trạng thái `published` có thể vẫn false nếu worker chưa xử lý. Không gọi đó là transfer chưa commit.

### 19.6. Diễn giải trạng thái không nhất quán

Nếu thấy `transfers.TR-100.status=COMPLETED` nhưng thiếu ledger hoặc outbox, có thể là:

- Dữ liệu legacy/migration không đi qua workflow mới.
- Có write trực tiếp ngoài transaction.
- Bug transaction/session handling.
- Database restore/migration partial.
- Query consistency/snapshot không đúng.

Không “chữa” bằng cách chuyển tiền lại. Trước hết khoanh vùng record/version, cách ghi và bằng chứng commit; remediate ledger/outbox theo approval, idempotent logic và audit.

## 20. Quan sát driver và MongoDB khi mất kết nối

### 20.1. Tách ba thời điểm

Một HTTP request chậm có thể nằm ở:

~~~text
HTTP request accepted
   |
   v
MongoDB server selection
   |
   v
Connection checkout / TCP reconnect
   |
   v
Transaction body commands
   |
   v
commitTransaction
   |
   v
HTTP response
~~~

`MongoTimeoutException` trong **server selection** khác với network read timeout khi **commit đã được gửi**. Nếu chỉ thấy HTTP 504 và không ghi command-phase timeline, không thể suy ngay transaction có commit hay không.

### 20.2. Driver event listeners

MongoDB Java Driver có các API để quan sát:

| Listener/Event family | Giúp trả lời |
|---|---|
| **Command monitoring** — `CommandStarted`/`Succeeded`/`Failed` | Transaction body/commit/abort command có được driver gửi, duration/error thế nào? |
| **SDAM** — cluster/server description/heartbeat | Primary nào eligible, có election hoặc topology change không? |
| **CMAP** — pool created/cleared, checkout started/success/failed | Driver đang đợi connection, clear pool hay kết nối mới sau failover? |
| **Application tracing** — request/transfer ID, attempts, deadline | Một business operation tạo bao nhiêu DB attempts/HTTP retries? |
| **MongoDB server logs/metrics** | Commit/replication/recovery và database resource symptoms ra sao? |

Không coi command listener logs là audit trail đáng tin duy nhất cho transfer result: nó có thể thiếu events khi process crash, listener không đảm bảo retention, và chỉ nhìn một client không biết các pods khác làm gì.

### 20.3. Java CommandListener đếm attempts theo command name

~~~java
import com.mongodb.event.CommandListener;
import com.mongodb.event.CommandStartedEvent;
import com.mongodb.event.CommandSucceededEvent;
import com.mongodb.event.CommandFailedEvent;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.LongAdder;

final class TransactionCommandMetrics implements CommandListener {
    private final ConcurrentHashMap<String, LongAdder> started =
        new ConcurrentHashMap<>();

    @Override
    public void commandStarted(CommandStartedEvent event) {
        started.computeIfAbsent(
            event.getCommandName(), ignored -> new LongAdder())
            .increment();
    }

    @Override
    public void commandSucceeded(CommandSucceededEvent event) {
        // Observe command name, elapsed time, outcome.
        // Do not log full command BSON.
    }

    @Override
    public void commandFailed(CommandFailedEvent event) {
        // Observe failure type/command name with redaction.
    }
}
~~~

Đăng ký listener qua `MongoClientSettings.builder().addCommandListener(...)` và pass settings khi `MongoClients.create(settings)`. Metrics nên phân biệt `commitTransaction`, `abortTransaction`, `update`, `insert`, số attempts và failures. **Listener không phải nơi thay đổi retry behavior** hoặc chặn/làm giả responses; nó phục vụ quan sát.

### 20.4. Correlation và thông tin nên lưu

~~~text
operationId:            TR-LAB-007
requestFingerprint:     sha256:<computed>
serviceInstance:        transfer-api-pod-2
attemptNo:              2
phase:                  COMMIT
driverErrorClass:       MongoSocketReadTimeoutException
errorLabels:            [UnknownTransactionCommitResult]
primaryBefore:          lab1
primaryAfter:           lab2
elapsedMs:              320
result:                 UNKNOWN_REQUIRES_VERIFICATION
~~~

Các values là **mẫu log**, không phải log quan sát thật. Không ghi full connection URI/password/BSON có PII, session credentials hoặc auth headers. Giữ requestId/transferId trong **traces/logs có retention**, không gắn raw high-cardinality operation IDs vào Prometheus labels.

### 20.5. Metrics backend quan trọng

- `transactions.started/committed/aborted` theo server metrics khả dụng ở phiên bản.
- Replication state/election counts, majority availability.
- Driver connection checkout wait và connectionPoolCleared.
- Server selection failures, socket errors và command p95/p99.
- Transaction retry body/commit attempts riêng biệt.
- Business `unknown_commit_results_total` và recovery age.
- Idempotency conflicts, duplicate-key errors.
- Ledger imbalance/transfer-without-outbox alerts.
- HTTP p95/p99, 429/503/504, pod restarts/GC pressure.

Nếu log “transaction fail” nhưng transfer record hiện diện, dashboard phải phân biệt **client-observed failure** khỏi **committed business effect**.

### 20.6. `serverStatus` và `currentOp`

Trên lab có quyền đọc monitoring:

~~~javascript
const status = db.getSiblingDB("admin")
  .runCommand({ serverStatus: 1 })

printjson(status.connections)
printjson(status.transactions)
printjson(status.metrics?.commands)
~~~

Tên/availability của nested metrics khác theo server version/topology. Nếu field không tồn tại, tra docs tương ứng; không hardcode dashboard theo ví dụ. `$currentOp`/`db.currentOp()` có thể giúp thấy active operations nhưng thường đòi privileges; tránh xuất raw commands có sensitive data.

### 20.7. Không restart tất cả pods khi primary election

Nếu liveness probe kill pods chỉ vì DB mất primary vài giây, các pods cùng restart rồi tạo MongoClients/pools/TLS handshakes, có thể gây **connection storm**. Thiết kế liveness khác readiness/dependency status; dùng retry/backoff/jitter và bounded queue để hệ thống phục hồi thay vì tăng áp lực lên primary mới.

## 21. Runbook vận hành: `UNKNOWN_REQUIRES_VERIFICATION`

Một quy trình thực tế cần **owner, deadline, bằng chứng, escalation** và không đổi idempotency key khi retry.

### Bước 1 — Cố định identity của operation

Giữ:

~~~text
transferId = TR-100
fingerprint = hash(from,to,amountMinor,currency,tenant,...)
receivedAt = T0
driver session/attempt correlation (if available)
~~~

Không tạo transaction ID mới hoặc random HTTP idempotency key trong cùng logical request chỉ vì gateway trả timeout.

### Bước 2 — Ghi nhận giai đoạn lỗi

Phân biệt:

- Trước khi transaction start.
- Trong body trước commit.
- Trong `commitTransaction`.
- Sau commit ACK nhưng trước response HTTP.

Nếu không có đủ trace, ghi **PHASE_UNKNOWN**, không đoán. Kiểm error labels/codes, SDAM/CMAP, topology timeline; không log password/PII.

### Bước 3 — Không thực hiện compensating transfer ngay

Nếu chưa biết debit đã xảy ra, một “reverse transfer” có thể **tạo tiền sai** khi transaction gốc thật ra chưa commit. Compensation chỉ được tạo khi đã xác minh state và business policy chấp thuận; nó là operation mới có transferId/audit riêng.

### Bước 4 — Đợi server ổn định và xác minh

Chọn cluster healthy, primary eligible, read concern/write concern phù hợp. Tra `transfers[TR-100]` theo stable ID và so full payload/fingerprint. Nếu record committed, kiểm ledger/outbox invariants theo cùng consistency cut hoặc đã đủ bằng chứng.

### Bước 5 — Nếu không có record, tiếp tục thận trọng

Không đánh dấu `NOT_COMMITTED` chỉ vì một lần read thấy missing ngay sau election. Với app protocol cho phép **idempotent re-execution**, chạy lại cùng stable key với unique constraint (hoặc retry commit nếu cùng session/transaction vẫn còn). Nếu không có đủ bằng chứng và policy không cho phép retry, giữ trạng thái unknown/escalate.

### Bước 6 — Chuyển trạng thái recovery

~~~text
UNKNOWN_REQUIRES_VERIFICATION
         |
         +-- committed record matches + checks pass
         |       -> COMMITTED_VERIFIED
         |
         +-- definitive abort evidence / safe retry
         |       -> NOT_COMMITTED_CONFIRMED / RETRY_SAME_KEY
         |
         +-- different payload / inconsistent ledger
         |       -> SECURITY_OR_DATA_CONFLICT / MANUAL_REVIEW
         |
         +-- no reliable evidence yet
                 -> RETRY_STATUS_CHECK_WITH_BACKOFF
~~~

Trạng thái `NOT_COMMITTED_CONFIRMED` cần chứng cứ thật (ví dụ abort đã ACK và commit chưa hề bắt đầu trong workflow đó), không phải assumption từ “read thấy null”.

### Bước 7 — Trả thông tin đúng cho client

- `COMMITTED_VERIFIED`: trả original transfer result, không ghi thêm.
- `RETRY_SAME_KEY`: chỉ khi protocol bảo đảm idempotency, thông báo dùng lại same key.
- `UNKNOWN`: cho biết không xác nhận được outcome; đưa operation ID để tra trạng thái.
- `CONFLICT`: same key với khác payload, không thực hiện request mới.

Không làm lộ balances/account IDs của tenant khác qua status endpoint; auth và tenant isolation là bắt buộc.

### Bước 8 — Sau khi phục hồi

- Đối soát ledger/transfer/outbox, không để unknown cases vô hạn.
- Lưu root cause: stepdown, network, timeout, pool starvation, app crash.
- Cập nhật alert threshold/runbook.
- Test lại idempotency under concurrent requests và client retries.
- Có báo cáo tài chính/business incidents nếu tác động thật.

### 21.1. Operational service levels

Định nghĩa riêng:

~~~text
API response SLO
  -> time to respond ACK or UNKNOWN accurately

Resolution SLO
  -> time to classify UNKNOWN to committed/not committed

Reconciliation SLO
  -> time to prove ledger and dependent effects are consistent
~~~

Không thể hứa tất cả transfers có commit confirmation trong 200 ms khi cluster đang election, nhưng có thể thiết kế API trả **trạng thái trung thực, recoverable** và không nhân đôi effect.

## 22. Kế hoạch kiểm thử tích hợp và fault injection

### 22.1. Ba tầng kiểm thử

| Tầng | Kiểm điều gì? | Không kiểm được |
|---|---|---|
| **Unit tests** | Mapping payload, idempotency fingerprint, status machine, error classification. | MongoDB server commit/rollback behavior thực tế. |
| **Integration tests trên replica set lab** | Session, transaction atomicity, unique index, concurrent write conflict và verification queries. | Network partition thật nếu không có harness. |
| **Fault-injection tests được kiểm soát** | Election, timeout, drop/delay commit response, process crash/recovery. | Không đại diện mọi combination production topology/network. |

Không dùng standalone MongoDB mock để tuyên bố đã kiểm multi-document transaction. Integration tests nên dùng **replica set test topology** có server version gần production.

### 22.2. Bảng cases bắt buộc

| Test ID | Inject/điều kiện | Kết quả business bắt buộc |
|---|---|---|
| T01 | Normal commit, amount 50.000 | Một transfer committed, A−50.000/B+50.000, 2 ledger legs, 1 outbox. |
| T02 | Debit thiếu tiền | Abort, không có committed transfer/ledger/outbox, balances không đổi. |
| T03 | Destination không tồn tại | Abort toàn transaction, A không bị trừ. |
| T04 | Currency mismatch | Reject/abort, không chuyển chéo currency im lặng. |
| T05 | from == to | Reject input trước transaction. |
| T06 | amount ≤0 | Reject input, không ghi DB. |
| T07 | Credit int64 overflow | Abort, không tạo transfer partial. |
| T08 | Two transfers cùng account cạnh tranh | Không overspend, retries bounded, invariants giữ. |
| T09 | Same transferId same payload gửi hai lần | Chỉ một business effect, second returns same result. |
| T10 | Same transferId different payload | Idempotency conflict; không ghi mới. |
| T11 | Crash sau body trước commit | Không có committed partial transfer. |
| T12 | Explicit abort | Balances/ledger không đổi từ transaction đó. |
| T13 | TransientTransactionError trong body | Helper retry eligible body; không external side effects lặp. |
| T14 | Commit response lost after commit | Client thấy unknown, DB có đúng một committed effect. |
| T15 | Commit request không tới server | Không được báo success; retry/recovery theo same key. |
| T16 | Primary stepdown giữa body/commit | Không double transfer, phân loại labels/timeline. |
| T17 | Majority write concern timeout | Không kết luận rollback từ wtimeout. |
| T18 | HTTP client timeout sau DB ACK | Retry same key trả original result. |
| T19 | Outbox publisher crash sau broker ACK | Consumer dedupe event ID; không nhân đôi external effect. |
| T20 | Recovery worker restarts nhiều lần | Persistent status/idempotency giữ nguyên, eventually resolves. |

### 22.3. Mục tiêu assertions chính xác

Trong test isolated, ví dụ:

~~~text
before:
  accounts A=100000, B=20000
  no transfer TR-500

after one successful transfer of 50000:
  A=50000, B=70000
  transfers.TR-500 present, status COMPLETED
  ledger.TR-500:DEBIT  = -50000
  ledger.TR-500:CREDIT = +50000
  outbox.transfer:TR-500 exists
  no other records sharing business transfer ID
~~~

Với một **failed/aborted** transaction, assert **tất cả** phần này không thay đổi. Với **unknown** outcome, test phải xác minh app **không suy là rollback** và có khả năng phân loại theo durable transfer record. Không chỉ assert một exception class rồi bỏ qua DB state.

### 22.4. Chụp baseline và cleanup

Mỗi test nên:

1. Dùng database/collection prefix riêng hoặc fixture isolated.
2. Xác nhận replica set test URI, không phải production.
3. Ghi expected balances và transfer IDs cố định/unique per test.
4. Gây lỗi có chủ đích, điều kiện lặp lại được.
5. Đọc committed state sau fault và so invariants.
6. Đóng sessions/clients và clear fault settings.
7. Lưu test evidence (sanitized), kể cả khi fail.

Không để một failpoint/network rule còn bật sau test, gây lỗi ngẫu nhiên cho tests khác. Một test harness tốt có cleanup **ngay cả khi assertion fail**.

### 22.5. Giới hạn concurrency khi tạo write conflicts

Để thử race, dùng **hai hoặc vài workers**, cùng account, dữ liệu có expected conflict; đừng phát 100.000 transaction requests để ép DB lỗi. Test phải chứng minh correctness sau cạnh tranh, không dựa vào một số milliseconds cố định.

### 22.6. Kiểm tra retry callbacks có external side effects

Trong unit test helper/service, inject transient error lần đầu để callback chạy lại, đếm invocation của email/payment mock. Kết quả mong muốn:

~~~text
transaction body attempts = 2
MongoDB committed transfer count = 1
external payment charge in transaction body = 0
outbox logical event count = 1
~~~

Đây là **kết quả kỳ vọng của test scenario**, không phải cam kết driver sẽ retry đúng 2 lần trong mọi môi trường. External publisher/consumer có thể nhận event nhiều lần và phải idempotent.

### 22.7. Mock unknown commit không thay cluster test

Trong unit test, mock gateway “server committed, client lost response” để test HTTP status/recovery. Sau đó integration test trên replica set kiểm transaction/invariants, và controlled proxy fault test nếu hạ tầng hỗ trợ. Không gộp ba tầng và tuyên bố “đã thử network partition” chỉ vì mock ném `MongoSocketException`.

### 22.8. Kiểm các trạng thái lâu ngày chưa xác minh

Tạo synthetic `PENDING_VERIFICATION` quá SLA, kiểm recovery worker:

- Không tự gán FAILED nếu thiếu chứng cứ.
- Không retry với key mới.
- Có bounded attempts và dead-letter/escalation.
- Ghi lastSeen/lastError/nextRetryAt.
- Sau khi DB phục hồi, đọc transfer record và resolve.

### 22.9. Test quyền truy cập

Một user tenant-a không được xem status/ledger của `TR-tenant-b` chỉ vì biết transferId. Auth/idempotency keys phải scoped theo tenant/user phù hợp. Test cross-tenant status GET, replay POST và conflict responses không tiết lộ amount/account numbers.

### 22.10. Load test sự phục hồi

Chạy workload có giới hạn, tăng traffic theo stages trong lab, đo HTTP p99, server election delay, pool checkout wait, transactions aborted/committed, retry amplification và unresolved unknown age. Tối ưu headroom; không tăng retries/pool khi DB CPU/IOPS đã bão hòa.

## 23. Những lỗi suy luận thường gặp

| Sai lầm | Vì sao nguy hiểm | Thay bằng |
|---|---|---|
| “Socket timeout nghĩa transaction rollback.” | Commit có thể đã xảy ra nhưng ACK mất. | UNKNOWN + verify same ID. |
| “Mọi MongoException đều nên retry nguyên body.” | Có non-transient business/validation errors. | Error code/labels + bounded policy. |
| “`UnknownTransactionCommitResult` => start transaction mới với ID mới.” | Dễ double debit/credit. | Retry same commit nếu có thể; idempotent status verification. |
| “`TransientTransactionError` => retry chỉ credit.” | Partial workflow sai semantics. | Retry whole transaction theo helper/spec. |
| “`withTransaction` callback chỉ chạy một lần.” | Driver có thể retry callback. | Không external side effects trong callback. |
| “Send email trước commit rồi abort sẽ thu hồi email.” | MongoDB không rollback email. | Transactional outbox. |
| “`writeConcern:majority` đảm bảo HTTP ACK tới client.” | Network có thể làm mất response. | Idempotency + status endpoint. |
| “`wtimeout` ép rollback.” | Write có thể đã áp dụng/commit. | Classify/verify outcome. |
| “`retryWrites=true` làm toàn business exactly once.” | HTTP requests mới có session/IDs khác. | Stable business transferId + unique index. |
| “Đọc missing transfer một lần là chắc không commit.” | Stale read/election/in-flight commit. | Verified consistency and recovery protocol. |
| “Idempotency key có cũng được, không có cũng được.” | HTTP retries tạo effect mới. | Required stable client-supplied/generated-once key. |
| “Same key nhưng payload khác thì trả previous success.” | Che wrong request hoặc malicious retry. | Fingerprint compare, 409 conflict. |
| “Read-before-insert đủ chống concurrent duplicate.” | Hai pods cùng thấy missing. | Unique index + conflict handling. |
| “Unique transfer ID bảo vệ mọi ledger rows.” | Child/outbox IDs cũng có thể duplicate. | Stable deterministic child IDs + transaction. |
| “Money Double giữ exact financial decimals.” | Floating point/scale. | int64 minor units/Decimal128 contract. |
| “Hai writes độc lập thành một transaction vì cùng request.” | Atomicity chỉ theo operation/document nếu không có transaction. | ClientSession + transaction. |
| “Một bulkWrite tự atomic trên mọi documents.” | Bulk operations không tự thành multi-doc transaction. | Multi-document transaction khi cần. |
| “Transactions tự ngăn overspend mọi case.” | Business predicate có thể sai, concurrent attempts. | Conditional debit, validation, unique IDs. |
| “Snapshot read thay được unique index.” | Concurrent identity creation race. | Unique index trên transfer ID. |
| “Không cần kiểm matchedCount.” | Debit no-op vì insufficient funds vẫn có thể credit. | Validate matchedCount, abort on failure. |
| “Transaction cho phép gửi Kafka/payment trực tiếp.” | External systems không bị rollback cùng DB. | Outbox/saga/idempotency. |
| “Consecutive REST calls với cùng status=OK là một commit.” | Logs/caches có thể thiếu/replay. | Durable transfer record + ledger proof. |
| “Ledger net=0 là chắc đúng từng transfer.” | Entries sai có thể tự bù. | Per-leg identity/type/value checks. |
| “Primary stepdown luôn tạo unknown commit label.” | Timing khác nhau tạo kết quả khác. | Capture actual phase/errors/DB state. |
| “Có thể fault-inject production để chứng minh.” | Gây downtime và mất dữ liệu thật. | Replica set lab/test proxy, authorization. |
| “Tăng pool sẽ chữa mất primary.” | Không có eligible server. | SDAM/network/election monitoring. |
| “Restart toàn service khi DB election.” | Có thể tạo reconnect storm. | Liveness/readiness separation. |
| “Timeout ngắn hơn nghĩa write không tới server.” | Client deadline không rollback server work. | Unknown-outcome protocol. |
| “Retry vô hạn giúp chắc chắn thành công.” | Retry amplification gây overload/double effects. | Attempt cap/backoff/jitter/deadline. |
| “Transaction có thể mở vài phút để gọi API ngoài.” | Lifetime/resource conflicts, side effect repeat. | Short DB transaction + workflow/saga. |
| “Rollback chỉ cần ghi ngược tiền vào account.” | Unknown outcome có thể chưa commit. | Verify first; compensation with new audited operation. |
| “Status endpoint trả PENDING từ memory là đủ.” | Process crash mất state. | Durable request status/recovery protocol. |
| “Một test mock exception là đã thử failover.” | Mock không mô tả server/network behavior. | Real replica-set integration/fault tests. |
| “Có đủ transfers record thì không cần ledger.” | Có thể dữ liệu legacy/corruption. | Independent business invariants/reconciliation. |
| “Các monitoring logs là bằng chứng commit duy nhất.” | Logs có thể thiếu sau crash. | Durable DB state and write concern evidence. |

### 23.1. Review một pull request transaction

Những câu hỏi cần trả lời trước merge:

1. Mỗi business request có **transferId/idempotency key ổn định** không?
2. Unique index và payload fingerprint có được enforce/verify không?
3. Có check debit/credit matchedCount và currency/overflow/ACL không?
4. Mọi writes cần atomic có dùng **cùng ClientSession** không?
5. Callback có side effects ngoài DB, gọi `subscribe()` hay logic không idempotent không?
6. Có phân biệt transient body retry với unknown commit không?
7. Có deadline/backoff/cap cho retry và recovery không?
8. Có verify transfer/ledger/outbox sau timeout, process crash, failover không?
9. Test đã dùng replica set, fault injection an toàn và kiểm DB state chưa?
10. Monitoring/alerts có giúp phân biệt “client failed” với “business committed” không?

## 24. Bài tập thực hành có đáp án

Các bài sử dụng **dữ liệu giả định trong lab**. Đối với fault injection và failover, chỉ thực hiện trên replica set test được cấp phép. Mục tiêu là diễn giải **kết quả DB và trạng thái tri thức của client**, không coi một exception string là sự thật tuyệt đối về commit.

### Bài 1 — Một document và hai documents

**Đề:** `updateOne` giảm balance của A với predicate `>= q` có atomic không? Hai `updateOne` riêng trên A/B có cùng atomicity không?

**Đáp án:** Một update trên **một document** là atomic. Hai updates riêng trên hai documents không tự atomic cùng nhau; nếu lỗi giữa chừng có thể lệch tổng. Cần multi-document transaction hoặc thiết kế workflow khác có invariant/reconciliation.

### Bài 2 — Standalone MongoDB

**Đề:** Developer chạy MongoDB standalone rồi gọi `startTransaction`. Có đủ điều kiện hỗ trợ multi-document transactions?

**Đáp án:** Không. Cần replica set/sharded deployment hỗ trợ transactions. Single-node **replica set** thích hợp cho lab commit/abort nhưng không thực hành HA election như ba node.

### Bài 3 — Phải truyền session?

**Đề:** Bắt đầu `ClientSession` và start transaction, nhưng `accounts.updateOne(...)` không nhận session, còn `ledger.insertOne(session, ...)` nhận session. Hai writes có chắc cùng transaction không?

**Đáp án:** Không. Java Sync Driver operations phải dùng **session overload** tương ứng để tham gia transaction. Đọc code theo từng write, không suy từ việc session tồn tại trong một method.

### Bài 4 — Commit ACK

**Đề:** `commitTransaction` được ACK theo majority write concern. App có nên trả success cho transfer ID?

**Đáp án:** Có thể trả success theo contract và verification/business state (nếu không còn lỗi application khác), ghi transfer ID để audit. Majority ACK là bằng chứng DB commit theo semantics; vẫn cần xử lý tình huống HTTP response có thể thất lạc.

### Bài 5 — Timeout tại commit

**Đề:** Client đã gửi `commitTransaction`, socket bị đóng trước response. Có chắc toàn transaction rollback?

**Đáp án:** Không. Outcome **unknown**; server có thể đã commit. Retry **commit of same transaction** nếu session/helper cho phép hoặc dùng stable transfer ID để verify.

### Bài 6 — TransientTransactionError

**Đề:** Trong body, update bị write conflict với label `TransientTransactionError`. Retry riêng operation update thứ hai hay transaction body?

**Đáp án:** Theo transaction retry pattern, abort và **retry toàn bộ transaction body** trong transaction mới khi eligible và còn budget; dùng driver helper để áp spec. Không tiếp tục transaction đã lỗi như không có gì.

### Bài 7 — UnknownTransactionCommitResult

**Đề:** Commit có label `UnknownTransactionCommitResult`. Có nên gọi lại callback với transfer ID mới?

**Đáp án:** Không. Cố retry `commitTransaction` cùng session/txn nếu được hỗ trợ, sau đó verify durable state. Một callback mới với ID mới có thể gây double debit nếu transaction cũ đã commit.

### Bài 8 — wtimeout

**Đề:** `wtimeout=5000` trên majority commit hết hạn. Có chứng minh write chưa được primary áp dụng?

**Đáp án:** Không. Chờ majority acknowledgment hết thời gian không có nghĩa server rollback. Cần classify outcome và không retry business effect bằng key mới.

### Bài 9 — Không đủ tiền

**Đề:** A có 30.000, request q=50.000, debit predicate `balance >= q` trả `matchedCount=0`. Có nên tiếp tục credit B?

**Đáp án:** Không. Abort transaction; trả business conflict/insufficient funds, không credit và không ghi transfer COMPLETED. Không retry vô hạn vì đây là business precondition failure.

### Bài 10 — Destination không tồn tại

**Đề:** Debit A đã chạy trong transaction, credit B không match vì B không có. A có mất tiền không?

**Đáp án:** Nếu transaction được **abort đúng** và không commit, debit chưa trở thành committed effect. Phải throw/abort, không catch rồi commit. Verification trên lab cần xác nhận balances/ledger không đổi.

### Bài 11 — Two transfers cạnh tranh

**Đề:** A có 100.000; TR1 chuyển 80.000, TR2 chuyển 80.000 đồng thời, không overdraft. Hai transfers có cùng thành công không?

**Đáp án:** Không nên có cả hai thành công nếu guard/transaction đúng. Có thể một transaction gặp write conflict rồi retry; sau đó một request không đủ tiền và trả business failure. Điều quan trọng là **không âm balance và không lệch ledger**.

### Bài 12 — Same ID, same payload

**Đề:** Client gửi lại `TR-100` với from/to/amount/currency giống hệt sau HTTP 504. Cách xử lý?

**Đáp án:** Đọc durable transfer record, so fingerprint và status. Nếu đã committed, trả original result, **không debit lần nữa**. Nếu unknown/pending, dùng recovery cùng ID.

### Bài 13 — Same ID, different payload

**Đề:** `TR-100` trước đó là 50.000, client retry với 70.000. Có thể coi là cùng request?

**Đáp án:** Không. Trả **idempotency conflict** theo API policy, không thực hiện thêm hoặc ghi đè record cũ. Khóa phải scoped theo tenant/authenticated caller phù hợp.

### Bài 14 — Read-before-write race

**Đề:** Hai pods đều đọc thấy `transfers.TR-100` chưa tồn tại. Có thể cả hai inserts cùng thành công?

**Đáp án:** Unique `_id` ngăn cả hai cùng commit hai transfer records với same ID; một có thể gặp duplicate key/write conflict. Read-before-write chỉ tối ưu, không là synchronization guarantee. Caller lỗi phải verify committed record/payload.

### Bài 15 — Callback side effects

**Đề:** `withTransaction` body gọi email API, sau đó write conflict khiến callback chạy lại. Có thể gửi mấy emails?

**Đáp án:** Có thể nhiều hơn một, kể cả nếu chỉ một transaction commit. Không gửi email trong callback; ghi outbox event trong transaction, publish bên ngoài với idempotent consumer.

### Bài 16 — Abort ACK

**Đề:** Sau update A/B chưa commit, `abortTransaction()` xác nhận thành công. Có cần reverse transfer để hoàn tiền?

**Đáp án:** Không. Các transaction writes đó đã bị abort, không committed. Reverse transfer sẽ là một movement mới sai. Chỉ compensation khi đã xác minh một committed movement cần đảo theo business.

### Bài 17 — Process crash sau commit ACK

**Đề:** Database đã commit, app crash trước HTTP response. HTTP client retry request trên pod khác. Vì sao cần idempotency storage?

**Đáp án:** Pod mới không có memory của pod cũ. Durable transfer ID/unique index và status lookup trả original committed result; tránh chuyển tiền lần hai.

### Bài 18 — Server selection timeout

**Đề:** Replica set tạm không có primary, driver không tìm được eligible server. Tăng `maxPoolSize` có giải quyết không?

**Đáp án:** Không. Pool không tạo ra primary. Kiểm SDAM/election/network/read preference, deadline/backoff. Nếu operation trước đã gửi commit thì phải theo protocol unknown, không suy mọi selection timeout là “chưa ghi gì”.

### Bài 19 — Stepdown và error label

**Đề:** Chạy `rs.stepDown(15)` trong lab lúc workload đang chạy. Có chắc mọi transaction trả `UnknownTransactionCommitResult`?

**Đáp án:** Không. Timing quyết định lỗi: body transient, selection timeout, commit unknown, hoặc operation đã thành công trước stepdown. Cần command-phase trace và durable DB state để phân loại.

### Bài 20 — retryWrites=true

**Đề:** Đã bật `retryWrites=true`, có cần stable transfer ID cho HTTP POST không?

**Đáp án:** Vẫn cần. Driver retryable writes chỉ áp dụng eligible operations trong protocol và session semantics; client/gateway có thể tạo HTTP request mới sau timeout. Business key/unique constraints mới chống duplicate effect ở tầng nghiệp vụ.

### Bài 21 — Int64 overflow ở bên nhận

**Đề:** B có balance gần `Long.MAX_VALUE`, cộng q=50.000 có thể overflow. Transaction có tự biết business rule này không?

**Đáp án:** Không. Validate input và guard update bằng `balanceMinor <= Long.MAX_VALUE - q`, check matchedCount. Nếu không match, abort, không để debit commit. Với nhiều currencies/precision, dùng mô hình số phù hợp.

### Bài 22 — Currency mismatch

**Đề:** A dùng VND còn B dùng USD, request chuyển 50.000 nhưng code chỉ increment/decrement hai balances. Điều gì sai?

**Đáp án:** Giao dịch có thể atomic nhưng **sai nghiệp vụ**; không cộng hai currencies như cùng đơn vị. Phải enforce currency match hoặc có FX workflow/rate/rounding và ledger per currency được thiết kế rõ.

### Bài 23 — Session không được truyền cho mọi write

**Đề:** `transfers.insertOne(session,...)` và `ledger.insertMany(session,...)` nằm trong transaction, nhưng `accounts.updateOne(...)` không truyền session. Có thể commit một phần dù method tên `transferAtomic`?

**Đáp án:** Có. Accounts update không nhất thiết tham gia transaction; nếu transaction abort, accounts có thể đã thay đổi độc lập. Mọi write cần atomic phải dùng cùng ClientSession trong Java Sync Driver.

### Bài 24 — Majority read thấy missing

**Đề:** Ngay sau commit response loss, một majority read thấy `transfers.TR-100` không có. Có đủ để tuyên bố rollback?

**Đáp án:** Không tuyệt đối. Cần xác nhận cluster ổn định, cut/commit state và recovery protocol; commit có thể còn in-flight hoặc read chưa phù hợp thời điểm. Giữ unknown, retry commit same session nếu được, hoặc idempotent re-execution same key với unique constraint.

### Bài 25 — Ledger tổng bằng không

**Đề:** Ledger có hai entries `+50.000` và `−50.000`, net=0. Đủ để xác nhận TR-100 đúng?

**Đáp án:** Chưa. Phải kiểm leg IDs, account IDs, từ/to, currency, types, status và record identity; hai legs sai tài khoản vẫn có thể net=0.

### Bài 26 — Outbox publisher crash

**Đề:** Worker gửi event lên broker thành công rồi crash trước update `published=true`. Khi restart có thể gửi trùng không?

**Đáp án:** Có. Outbox thường là **at-least-once delivery**. Consumer cần idempotent processing theo stable event ID/provider key; không gọi duplicate event là hai transfers mới.

### Bài 27 — Email trong callback

**Đề:** Gửi email ở cuối transaction callback trước khi driver gọi commit. Nếu commit thất bại, email có thu hồi không?

**Đáp án:** Không. Email là external effect. Ghi outbox trong transaction, để worker gửi sau commit và dedupe/retry riêng.

### Bài 28 — Không có outbox nhưng account/ledger đã commit

**Đề:** Verification thấy transfer completed và hai ledger legs đúng, nhưng outbox event thiếu. Nên chuyển tiền lại để tạo event?

**Đáp án:** Không. Tiền đã có thể được chuyển đúng; chạy lại transfer gây double effect. Điều tra code/legacy/migration, tạo repair event idempotent theo approval, audit và recheck.

### Bài 29 — Test mock lỗi network

**Đề:** Một unit test mock ném `MongoSocketException`, service trả UNKNOWN. Điều đó chứng minh MongoDB thật đã commit rồi mất response chưa?

**Đáp án:** Chưa. Test chứng minh **application behavior** khi được inject lỗi. Để kiểm server/driver cần replica-set integration/fault proxy test và đọc durable state.

### Bài 30 — `failCommand` closeConnection

**Đề:** Test failpoint đóng connection ngay khi nhận `commitTransaction`. Có chắc mô phỏng “server commit xong mới mất ACK” không?

**Đáp án:** Không. Connection có thể bị đóng **trước khi lệnh được áp dụng**. Muốn mô phỏng lost response after commit cần fault harness chứng minh request đã được thực thi, và kiểm server/driver timeline.

### Bài 31 — Fault injection trên production

**Đề:** Một thành viên đề xuất chạy `rs.stepDown` trên production để test retry. Có phù hợp với phạm vi bài?

**Đáp án:** Không. Bài chỉ cho phép lab/staging được cấp phép. Production chaos tests cần chương trình riêng được phê duyệt, với blast radius/rollback/incident plan; không thực hiện vì một bài học.

### Bài 32 — CommandListener là bằng chứng business?

**Đề:** Log Java ghi `commitTransaction started`. Có nghĩa transaction đã commit?

**Đáp án:** Không. Started chỉ nói client/driver bắt đầu phát command; có thể network fail hoặc server error. Cần commit ACK hoặc durable status verification.

### Bài 33 — Lỗi khi callback chạy lần hai

**Đề:** Driver helper gọi transaction body lại vì transient error. Logic cấp phát một transfer ID mới bằng UUID trong body mỗi lần. Có rủi ro gì?

**Đáp án:** Business identity không ổn định giữa attempts, khó dedupe/verify unknown outcome. Tạo/nhận **transferId một lần ở request boundary**, giữ bất biến giữa các lần retry.

### Bài 34 — Retry hết HTTP deadline

**Đề:** API deadline 800 ms, driver sau 750 ms mới gặp transient error. App nên retry body thêm 5 giây rồi trả success?

**Đáp án:** Không nếu vi phạm end-to-end SLO/contract. Giữ deadline/attempt cap; có thể trả UNKNOWN/temporary failure phù hợp và recovery status. Nếu một commit có thể đã gửi, không giả định không có side effect.

### Bài 35 — Compensation khi outcome unknown

**Đề:** Client không biết TR-100 có commit không, nên tạo transfer ngược B→A ngay. Có an toàn?

**Đáp án:** Không. Nếu TR-100 chưa commit, reverse sẽ chuyển tiền sai hướng. Xác minh outcome trước; compensation chỉ là nghiệp vụ mới có audit/approval khi transfer gốc thật sự committed và cần đảo.

### Bài 36 — Giao dịch chỉ có một transfer record

**Đề:** `transfers` có đúng một TR-100, nhưng ledger có bốn legs với ID khác nhau. Unique transfer `_id` đã bảo đảm exactly once chưa?

**Đáp án:** Chưa. Cần unique deterministic IDs cho child legs/outbox, transaction scope đầy đủ và per-transfer cardinality/invariants; record một mình không chứng minh mọi side effect đúng.

### Bài 37 — HTTP status cho unknown

**Đề:** Commit unknown, backend không có durable pending state. Có nên trả `200 Transfer Completed`?

**Đáp án:** Không. Trả trạng thái trung thực `UNKNOWN`/temporary error với operation ID/status query theo protocol. Chỉ dùng `202 Accepted` khi request đã được durably accepted và có cơ chế tiếp tục xử lý/status.

### Bài 38 — Cross-tenant idempotency

**Đề:** Tenant-b gửi status query với transferId của tenant-a và nhận số tiền, tài khoản. Vi phạm gì?

**Đáp án:** Lỗ hổng authorization/data isolation. Scope idempotency keys/status reads theo trusted principal/tenant; không trả raw records dựa trên guessed ID, ngay cả nếu transaction correctness hoàn hảo.

### Bài 39 — Thống kê lỗi từ hai tầng

**Đề:** Driver đã retry transaction hai lần, gateway retry HTTP request một lần. API log chỉ ghi “one request” nên DBA cho rằng chỉ một DB attempt. Vì sao sai?

**Đáp án:** **Business request, HTTP attempt, transaction body attempt và commit attempt là bốn đơn vị khác nhau**. Phải monitor correlation IDs và retries theo tầng; quá nhiều attempts có thể gây retry amplification khi failover.

### Bài 40 — Thiết kế workflow chuyển tiền chịu lỗi

**Đề:** Thiết kế API chuyển tiền MongoDB replica set 3 nodes, chịu primary election, socket response loss, gateway retry và crash của outbox worker. Business yêu cầu không double debit, đủ ledger audit và trạng thái truy vấn được. Nêu kiến trúc, code pattern và tiêu chí chấp nhận.

**Đáp án gợi ý:**

1. Dùng replica set đúng URI/quorum, MongoDB Java Sync Driver phiên bản tương thích, một MongoClient dùng chung theo app.
2. Nhận stable `transferId`/idempotency key ngay request boundary; verify authentication/tenant, currency/amount/range/from≠to.
3. Enforce unique transfer ID (scope đúng tenant) và request fingerprint bất biến.
4. Dùng `ClientSession.withTransaction` với readConcern snapshot, majority commit write concern và primary routing phù hợp.
5. Trong cùng callback, insert transfer record, conditional debit guard, credit overflow guard, 2 ledger entries và một outbox event.
6. Check matchedCount và throw business exception khi precondition fail; không swallow lỗi MongoDB hay gửi external effects trong callback.
7. Dùng helper để retry transient body/commit according to labels; cap deadline/attempts, backoff/jitter khi application retry.
8. Trên `UnknownTransactionCommitResult`, không tuyên bố rollback; retry same commit nếu session còn hợp lệ và helper hỗ trợ, hoặc verify durable transfer record/ledger/outbox bằng same ID.
9. Trên HTTP retry same payload, trả original committed result; payload khác same ID trả conflict; hai concurrent callers được chặn bằng unique index.
10. Outbox publisher thực hiện after commit, có lease/retry/idempotent consumer/processed event IDs; gửi trùng event không được gây effect nghiệp vụ thứ hai.
11. Có state machine `PENDING_VERIFICATION` (nếu dùng durable request ledger), recovery worker, escalation/manual review và status API có ACL.
12. Test trên replica set: success, abort, insufficient funds, destination missing, two concurrent transfers, same-ID retries, stepdown, lost commit response, process crash và outbox replay.
13. Đo CommandListener/SDAM/CMAP, HTTP p99, business unknown count/age, transaction retries, ledger imbalances và alerts.
14. Không chỉ assert HTTP 200: cần chứng minh **exactly one committed business effect**, correct balances, 2 exact ledger legs, 1 logical outbox event, no cross-tenant leakage.
15. Chỉ fault-inject trên lab/staging được phép; có recovery/cleanup khi test kết thúc.

Một thiết kế đạt yêu cầu là thiết kế **không cần biết client có nhận commit ACK hay không để vẫn ngăn được nghiệp vụ chạy hai lần**. Khi thiếu chứng cứ, nó giữ trạng thái cần xác minh thay vì biến lỗi mạng thành một kết luận dữ liệu không có cơ sở.

## 25. Tài liệu chính thức và hướng dẫn tra cứu theo phiên bản

Các nguồn sau giúp kiểm tra cú pháp/session semantics, retry behavior, error labels và điều kiện deployment. Một số đường dẫn `current` có thể chuyển đến release mới, vì vậy cần chọn đúng **MongoDB Server version, FCV, Java Driver version và replica set/sharding topology** khi triển khai. Các đoạn code trong bài được viết cho mục tiêu học tập trên lab; không khẳng định đã chạy trên cluster thực của người đọc.

### 25.1. Giao dịch và snapshot/majority

1. [MongoDB Manual — Transactions](https://www.mongodb.com/docs/manual/core/transactions/) — các đặc tính multi-document transactions, sessions, atomicity và deployment support.
2. [MongoDB Manual — Transactions Production Considerations](https://www.mongodb.com/docs/manual/core/transactions-production-consideration/) — transaction lifetime, operations restrictions, locking, cache/resources và deployment behavior.
3. [MongoDB Manual — Read Concern `snapshot`](https://www.mongodb.com/docs/manual/reference/read-concern-snapshot/) — snapshot read semantics và prerequisites.
4. [MongoDB Manual — Write Concern](https://www.mongodb.com/docs/manual/reference/write-concern/) — `majority`, `wtimeout`, acknowledgment và durability.
5. [MongoDB Manual — Retryable Writes](https://www.mongodb.com/docs/manual/core/retryable-writes/) — eligible retryable writes và limitations; khác business idempotency.
6. [MongoDB Manual — Replication](https://www.mongodb.com/docs/manual/replication/) — election, majority, rollback, oplog và replica-set semantics.

### 25.2. Java Driver transactions/error handling

7. [MongoDB Java Sync Driver — Transactions](https://www.mongodb.com/docs/drivers/java/sync/current/crud/transactions/) — `ClientSession`, `TransactionOptions`, `withTransaction`, callback và session lifecycle.
8. [MongoDB Java Sync Driver — Connection Pools](https://www.mongodb.com/docs/drivers/java/sync/current/connection/specify-connection-options/connection-pools/) — pool lifecycle, checkout limits và connection churn.
9. [MongoDB Java Sync Driver — Cluster Settings](https://www.mongodb.com/docs/drivers/java/sync/current/connection/specify-connection-options/cluster-settings/) — server selection, replica set discovery, latency/topology.
10. [MongoDB Java Sync Driver — Monitoring](https://www.mongodb.com/docs/drivers/java/sync/current/logging-monitoring/monitoring/) — command/CMAP/SDAM listeners và driver observability.
11. [MongoDB Driver Specification — Transactions](https://github.com/mongodb/specifications/blob/master/source/transactions/transactions.md) — normative transaction helper retry patterns, errors, commit retry và server/driver interoperability.
12. [MongoDB Driver Specification — Retryable Writes](https://github.com/mongodb/specifications/blob/master/source/retryable-writes/retryable-writes.md) — wire protocol và retry semantics.

### 25.3. Kịch bản failover và kiểm thử

13. [MongoDB Manual — `rs.stepDown()`](https://www.mongodb.com/docs/manual/reference/method/rs.stepDown/) — primary stepdown, điều kiện election và tác động availability. **Chỉ dùng ở lab trong phạm vi bài này.**
14. [MongoDB Manual — `replSetStepDown`](https://www.mongodb.com/docs/manual/reference/command/replSetStepDown/) — command-level stepdown behavior và prerequisites.
15. [MongoDB Manual — `serverStatus`](https://www.mongodb.com/docs/manual/reference/command/serverStatus/) — connection/transaction/server metrics theo version.
16. [MongoDB Manual — Connection String Options](https://www.mongodb.com/docs/manual/reference/connection-string-options/) — replicaSet, retryWrites, read/write concern và timeout URI options.
17. [MongoDB Manual — `configureFailPoint`](https://www.mongodb.com/docs/manual/reference/command/configureFailPoint/) — cơ chế cấu hình failpoints trên deployments/test binaries hỗ trợ; không mặc định có quyền/dùng được trên production.

### 25.4. Spring Data và kiến trúc ngoài MongoDB

18. [Spring Data MongoDB — Sessions & Transactions](https://docs.spring.io/spring-data/mongodb/reference/mongodb/client-session-transactions.html) — `MongoTransactionManager`, reactive transaction manager, session binding và caveats.
19. [MongoDB Manual — Schema Validation](https://www.mongodb.com/docs/manual/core/schema-validation/) — enforce BSON data shape, hỗ trợ business correctness nhưng không thay multi-collection invariants.
20. [MongoDB Manual — Unique Indexes](https://www.mongodb.com/docs/manual/core/index-unique/) — unique IDs, missing/null, sharding restrictions và duplicate protection.
21. [MongoDB Manual — Change Streams](https://www.mongodb.com/docs/manual/changeStreams/) — xây consumers/outbox workflows và resume requirements; không tự bảo đảm exactly-once external effects.

### 25.5. Khi đổi driver/server version, kiểm gì?

1. `withTransaction` API signature và driver automatic retries còn đúng theo release line không?
2. Error labels `TransientTransactionError`/`UnknownTransactionCommitResult` gắn cho các classes/codes cụ thể nào?
3. Client-side operation timeout và commit retry deadline behavior thay đổi không?
4. Majority write concern/journaling và transaction lifetime defaults có đúng cluster không?
5. Transactions có hỗ trợ trên standalone/single-node replica set/sharded deployment tương ứng không?
6. Monitor events có cung cấp command names/durations và redact BSON theo default không?
7. `rs.stepDown`/failpoints có khác về privileges, options và server version không?
8. App có retry layer khác bên ngoài driver (Spring Retry, HTTP gateway, message consumer) không?

## 26. Checklist tổng kết lab

### 26.1. Checklist thao tác an toàn

| Câu hỏi | Điều kiện đạt |
|---|---|
| Có chắc kết nối vào replica set **lab**? | URI/cluster verified, không có người dùng thật. |
| Có biết số dư trước bài? | Fixture/baseline ghi rõ, không reuse IDs không kiểm soát. |
| Giao dịch cập nhật nhiều documents? | Có session/transaction đúng và tất cả writes tham gia. |
| Có kiểm business guards? | Matched count, currency, amount >0, overflow, from≠to. |
| Có idempotency key? | Stable per logical request, unique và fingerprint kiểm. |
| Có phân biệt lỗi? | Transient body vs unknown commit vs business conflict. |
| Có retry bounded? | Deadline/cap/jitter và biết driver retry tự động. |
| Có fault injection được cấp phép? | Replica set lab, cleanup/recovery khi kết thúc. |
| Có kiểm durable state? | Transfer record, exact ledger legs, balances và outbox. |
| Có xử lý chưa biết outcome? | Trạng thái unknown/status query/recovery, không double transfer. |
| External side effects có tách? | Outbox/consumer idempotency. |
| Có test cạnh tranh và crash? | Same-ID and different-ID concurrency; post-commit response loss. |

### 26.2. Bốn điều phải phân biệt trong incident review

~~~text
1. Transaction ATTEMPT
     = one execution attempt inside driver/client.

2. Transaction COMMIT
     = durable database outcome under the chosen write concern.

3. Client OBSERVATION
     = what the application received (ACK/error/timeout).

4. Business EFFECT
     = whether exactly one intended transfer and ledger event exists.
~~~

Một request HTTP có thể có nhiều driver attempts, một commit có thể không được client quan sát và một business effect có thể đã tồn tại dù HTTP báo lỗi. **Không** dùng bốn khái niệm này như đồng nghĩa.

### 26.3. Mẫu báo cáo thực hành

~~~text
Lab run ID:               TXN-LAB-20261114-01
Cluster:                  rsLab / 3-node disposable replica set
Server version / FCV:     <verified>
Java driver version:      <verified>
Fault scenario:           primary stepdown / commit response loss
Business transfer ID:     TR-LAB-007
Request fingerprint:      <computed>
Observed error class:     <actual>
Observed error labels:    <actual>
Transaction body attempts:<measured>
Commit attempts:          <measured>
Majority commit ACK:      yes/no/unknown
Transfer record:          present/missing/unverified
Ledger:                   balanced/invalid/unverified
Outbox:                   one/none/multiple/unverified
Business outcome:         COMMITTED / NOT_COMMITTED / UNKNOWN
Recovery action:          <what was done, same ID>
Data loss/double effect:  <evidence>
Fault cleanup:            confirmed
Reviewer:                 <lab owner>
~~~

Các placeholders phải được thay bằng kết quả từ **lab thật** nếu bài được thực hành. Không điền “PASS” chỉ vì command không ném exception, và không ghi `NOT_COMMITTED` khi bằng chứng chỉ là một timeout/response loss.

## 27. Kết luận

Giao dịch MongoDB có thể bảo đảm nhiều writes trong cùng session/transaction được **commit hoặc abort nguyên khối**, nhưng **không bảo đảm client luôn nhận được kết quả commit**. Mạng, election, gateway timeout và process crash có thể xảy ra đúng ranh giới phản hồi khiến client chỉ biết rằng **outcome chưa xác định**.

Khi xử lý tình huống này, hãy giữ ba quy tắc:

1. **Retry đúng phần:** `TransientTransactionError` có thể cần retry toàn bộ transaction body theo driver helper và deadline; `UnknownTransactionCommitResult` hướng tới retry **commit cùng transaction** hoặc xác minh durable outcome, không tạo transfer mới với ID khác.
2. **Idempotency ở tầng nghiệp vụ:** Dùng một transfer ID ổn định, unique constraint, payload fingerprint, conditional debit/credit và ledger/outbox được commit trong cùng transaction. HTTP/gateway retries không được tạo tác động thứ hai.
3. **Đối soát thay cho suy đoán:** Khi ACK thất lạc, tra transfer record và ledger theo cùng ID với consistency policy phù hợp; nếu chứng cứ chưa đủ, giữ trạng thái `UNKNOWN_REQUIRES_VERIFICATION` và recovery protocol, không gọi timeout là rollback.

Thực hành phải tách rõ **transaction correctness**, **network visibility**, **external side effects** và **khả năng khôi phục**. Một hệ thống tốt không chỉ thành công khi mọi thứ khỏe mạnh: khi primary đổi, socket bị đóng hoặc caller bị timeout, nó vẫn giữ được dữ liệu đúng và giải thích trung thực những gì đã biết, những gì chưa biết.

**Bài học quan trọng nhất: lỗi mất kết nối không phải bằng chứng giao dịch thất bại; tính đúng đắn đến từ transaction được thiết kế đúng, khóa idempotency ổn định, và khả năng xác minh kết quả đã commit trước khi hành động lại.**
