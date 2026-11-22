# Write conflict, gửi lại thao tác và yêu cầu về tính lặp an toàn trong MongoDB

Một ứng dụng xử lý đơn hàng thường gặp tình huống hai request cùng muốn trừ tồn kho, hai worker cùng sửa một document, hoặc client gửi lại yêu cầu vì không nhận được phản hồi từ server. Có khi MongoDB trả lỗi **write conflict**; có khi thao tác đã ghi thành công nhưng phản hồi thất lạc; cũng có khi không xuất hiện lỗi nào, nhưng ứng dụng vô tình thực hiện **hai lần một tác động nghiệp vụ**.

Ba vấn đề này có liên quan nhưng **không phải một**:

- **Cạnh tranh ghi / write conflict:** nhiều thao tác đồng thời không thể cùng thực thi theo lịch sử quan sát và quy tắc nhất quán dự kiến; một thao tác có thể cần abort và thử lại.
- **Retry / gửi lại:** một tầng trong hệ thống thực hiện lại lệnh sau lỗi tạm thời, timeout hoặc kết quả commit chưa rõ.
- **Idempotency / tính lặp an toàn:** việc gửi **cùng một yêu cầu nghiệp vụ** nhiều lần không tạo thêm tác động so với thực hiện thành công một lần; kết quả có thể được tái sử dụng hoặc đối chiếu qua một khóa yêu cầu ổn định.

Một câu quan trọng xuyên suốt bài: **MongoDB bảo đảm nguyên tử cho một thao tác ghi trên một document, nhưng không tự bảo đảm mọi lần gọi API trùng nhau chỉ tác động nghiệp vụ một lần.** Tương tự, retryable writes ở mức driver không có nghĩa mọi lần retry HTTP hoặc chạy lại cả business function đều là an toàn.

Bài thuộc chương **Nguyên tử và cạnh tranh** của *Database Engine Document MongoDB*. Ví dụ chủ yếu dùng **mongosh**, thêm một mẫu **MongoDB Node.js Driver** để minh họa giao dịch và khóa idempotency. Các lệnh viết vào database `write_conflict_lab` chỉ dành cho môi trường học tập. Để thử transaction, cần triển khai MongoDB **replica set hoặc sharded cluster có hỗ trợ transaction**, không phải standalone server thông thường. Hình dạng lỗi và mức tự động retry tùy phiên bản MongoDB, driver và cấu hình deployment.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt write conflict của storage/transaction với lỗi trùng khóa, thiếu điều kiện nghiệp vụ và thao tác ghi không sửa được document nào.
2. Giải thích nguyên tử ở cấp **một document**, và vì sao `find() → tính toán → update()` có thể mắc race condition.
3. Dùng `$inc`, conditional update và **optimistic concurrency với version** để cập nhật an toàn trong trường hợp phù hợp.
4. Hiểu cách MongoDB báo lỗi/nhãn `WriteConflict`, `TransientTransactionError` và `UnknownTransactionCommitResult`, cùng giới hạn của việc retry.
5. Phân biệt **driver retryable writes**, **transaction retry** và **application/API retry**.
6. Thiết kế `Idempotency-Key` ổn định, giới hạn theo tenant/operation và gắn với fingerprint của payload.
7. Dùng **unique index + request ledger + transaction** để chỉ áp dụng một lần thay đổi nghiệp vụ gồm nhiều document.
8. Xử lý timeout hoặc mất phản hồi mà không mặc định lần ghi chưa diễn ra.
9. Tránh side effect bên ngoài MongoDB bị chạy lại khi transaction callback được retry.
10. Áp dụng backoff, retry budget, quan sát metric, kiểm thử cạnh tranh và chính sách lưu khóa idempotency.

## 2. Bốn khái niệm cần tách biệt

| Khái niệm | Câu hỏi cần trả lời | Ví dụ |
|---|---|---|
| **Atomicity** | Một thay đổi được áp dụng trọn vẹn hay không? | Trừ tồn kho và tăng reserved trong **cùng document** |
| **Concurrency control** | Hai bên cùng ghi có làm mất hoặc ghi đè thay đổi của nhau không? | Hai người cùng sửa bản nháp version 7 |
| **Retryability** | Sau lỗi tạm thời, có thể thực hiện lại lệnh theo giao thức nào? | Transaction bị abort vì write conflict |
| **Idempotency** | Cùng một yêu cầu được gửi lại có tạo tác động thứ hai không? | Retry thanh toán không thu tiền lần hai |

Các thuộc tính này bổ sung cho nhau. Một lệnh `$inc` có thể nguyên tử và hoạt động tốt khi nhiều client cùng tăng counter, nhưng **hai lời gọi `$inc` mới** sẽ tăng counter **hai lần**. Một unique index có thể chặn insert trùng mã nghiệp vụ, nhưng không tự bảo đảm nội dung phản hồi của request đã thực hiện được trả lại khi client gửi lại.

### 2.1. Minh họa mất phản hồi

~~~mermaid
sequenceDiagram
    participant C as Client
    participant A as API
    participant M as MongoDB
    C->>A: POST /reserve (requestId=R1)
    A->>M: Trừ tồn kho 1 đơn vị
    M-->>A: Ghi thành công
    A--xC: Phản hồi bị mất
    Note over C: Không biết đã trừ kho chưa
    C->>A: Gửi lại POST /reserve, vẫn requestId=R1
    Note over A: Nếu chạy $inc như request mới thì có thể trừ lần hai
~~~

MongoDB đã làm đúng ở từng thao tác. **Lỗi nằm ở thiết kế application retry** khi lần gửi lại không được nhận diện là cùng một yêu cầu nghiệp vụ.

## 3. Race condition: đọc rồi ghi không đồng nghĩa nguyên tử

Giả sử tồn kho ban đầu:

~~~javascript
{
  _id: "sku-A",
  tenantId: "t-01",
  available: 1,
  reserved: 0,
  version: 7
}
~~~

Hai API cùng kiểm tra còn hàng:

~~~javascript
const item = db.inventory.findOne({ _id: "sku-A" })

if (item.available > 0) {
  db.inventory.updateOne(
    { _id: "sku-A" },
    { $inc: { available: -1, reserved: 1 } }
  )
}
~~~

Giữa `findOne()` và `updateOne()`, một request khác có thể giảm stock. Nếu cả A và B đọc `available = 1`, cả hai cùng quyết định được đặt hàng rồi trừ một đơn vị, kết quả có thể thành **available = -1**. Mỗi update vẫn nguyên tử trên document, nhưng **điều kiện kiểm tra stock nằm ngoài thao tác ghi** nên không còn đúng ở thời điểm ghi.

~~~mermaid
sequenceDiagram
    participant A as Request A
    participant DB as MongoDB
    participant B as Request B
    A->>DB: findOne(_id=sku-A)
    DB-->>A: available=1
    B->>DB: findOne(_id=sku-A)
    DB-->>B: available=1
    A->>DB: $inc available:-1
    DB-->>A: available=0
    B->>DB: $inc available:-1
    DB-->>B: available=-1
    Note over A,B: Cả hai tin rằng còn hàng khi đọc trước
~~~

### 3.1. Đưa điều kiện vào chính lệnh update

~~~javascript
const result = db.inventory.updateOne(
  {
    _id: "sku-A",
    tenantId: "t-01",
    available: { $gte: 1 }
  },
  {
    $inc: {
      available: -1,
      reserved: 1
    }
  }
)

printjson({
  matchedCount: result.matchedCount,
  modifiedCount: result.modifiedCount
})
~~~

Đây là một **conditional atomic update**. Khi hai thao tác tranh chấp một đơn vị hàng cuối cùng, với các điều kiện bình thường và tất cả writer tuân theo cùng quy tắc, chỉ thao tác còn thấy `available >= 1` tại lúc thực thi được trừ hàng. Thao tác còn lại không khớp filter và có thể trả `matchedCount = 0`.

**Quan trọng:** `matchedCount = 0` **không phải lỗi `WriteConflict`**. Nó là một kết quả nghiệp vụ bình thường: tại thời điểm cập nhật không có document thỏa đủ điều kiện.

### 3.2. Bảo vệ quantity bất kỳ

Với request đặt `qty = 3`:

~~~javascript
const qty = 3

const result = db.inventory.updateOne(
  {
    _id: "sku-A",
    tenantId: "t-01",
    available: { $gte: qty }
  },
  {
    $inc: {
      available: -qty,
      reserved: qty
    }
  }
)
~~~

Ứng dụng phải validate `qty` là số nguyên dương trong giới hạn hợp lý trước khi gửi vào database. Một qty âm có thể đảo ngược ý nghĩa `$inc` và tạo lỗi nghiệp vụ dù query hoàn toàn hợp lệ.

### 3.3. Vì sao conditional update chưa đủ idempotency?

Nếu tồn kho có 10 đơn vị, cùng request `R1` được gửi hai lần:

~~~text
Lần 1: available 10 → 9, modifiedCount=1
Lần 2: available  9 → 8, modifiedCount=1
~~~

Cả hai lần đều thỏa `available >= 1`. Lệnh cập nhật nguyên tử và không vượt kho, nhưng **cùng một yêu cầu đã bị áp dụng hai lần**. Để ngăn điều đó, cần gắn **identity của request** vào thao tác hoặc lưu một request ledger có unique constraint.

## 4. Optimistic concurrency: cập nhật theo version

Với một document cần tránh ghi đè thay đổi của người khác, có thể dùng **version compare-and-swap**.

### 4.1. Tình huống lost update

Document:

~~~javascript
{
  _id: "draft-001",
  tenantId: "t-01",
  title: "Bản nháp",
  content: "Nội dung gốc",
  version: 7
}
~~~

Editor A và B cùng đọc version 7. A sửa title; B sửa content nhưng gửi lại cả document cũ. Nếu ứng dụng dùng `replaceOne({_id})` không ràng buộc version, B có thể ghi đè title do A vừa sửa.

### 4.2. Cập nhật có điều kiện version

~~~javascript
const expectedVersion = 7

const result = db.drafts.updateOne(
  {
    _id: "draft-001",
    tenantId: "t-01",
    version: expectedVersion
  },
  {
    $set: {
      title: "Tiêu đề mới"
    },
    $inc: { version: 1 }
  }
)

if (result.matchedCount === 0) {
  print("CONFLICT: document đã đổi version hoặc không tồn tại")
}
~~~

Hai client cùng gửi `version: 7` thì chỉ thao tác đầu tiên đổi version thành 8; thao tác đến sau không còn khớp. Tầng API có thể trả **HTTP 409 Conflict** hoặc phản hồi yêu cầu đọc lại để giải quyết xung đột.

**Không tự động retry cùng một bản nội dung cũ với version mới** nếu hành động đó có thể ghi đè sửa đổi của người khác. Retry ở đây là một **quyết định nghiệp vụ**: người dùng/ứng dụng cần merge, đọc lại hoặc báo conflict.

### 4.3. HTTP 409 không đồng nghĩa MongoDB WriteConflict

Khi `matchedCount = 0` do version không còn khớp, MongoDB thường **không ném lỗi write conflict**. API có thể chủ động tạo HTTP 409 dựa trên quy tắc optimistic locking. Ngược lại, một transaction có thể bị server abort với lỗi/nhãn transient write conflict ngay cả khi không có HTTP 409 nào được phát sinh.

## 5. Write conflict trong MongoDB là gì?

Khi các thao tác cạnh tranh ảnh hưởng tới dữ liệu hoặc index cùng lúc, MongoDB sử dụng cơ chế điều khiển concurrency của storage engine và transaction. Một số xung đột có thể được server xử lý nội bộ; một số được **trả lên client**, đặc biệt trong multi-document transaction khi snapshot và các write tranh chấp không thể được thực hiện theo lịch trình hợp lệ.

Một lỗi điển hình có thể mang:

~~~text
code: 112
codeName: "WriteConflict"
message: "... WriteConflict ..."
~~~

Nhưng **không dựa tuyệt đối vào text thông báo**. Trong thực tế cần kiểm tra **error code** và nhất là **error labels** do driver/server cung cấp, vì hình dạng lỗi, chỗ lỗi xuất hiện và các nhãn có thể khác giữa phiên bản và loại thao tác.

### 5.1. Write conflict thường xuất hiện ở đâu?

- Hai transaction cùng sửa một document trong khi một transaction khác đang có thay đổi chưa kết thúc.
- Một transaction đọc snapshot cũ rồi cố ghi lên document đã bị transaction khác thay đổi theo cách gây conflict.
- Các thao tác ghi cạnh tranh trong một số tình huống với index/transaction, dẫn đến abort theo cơ chế của engine.
- Thao tác transaction cần được retry vì bị tác động bởi concurrency/failover hoặc lỗi tạm thời.

Không phải **mọi** cập nhật đồng thời đều trả `WriteConflict`. Ví dụ hai request không có transaction cùng dùng `$inc` trên cùng counter thường có thể được MongoDB điều phối để mỗi lần tăng được áp dụng nguyên tử; thứ tự hoàn tất phụ thuộc cạnh tranh. Một số xung đột cấp storage được engine xử lý nội bộ, không nhất thiết lộ ra ứng dụng.

### 5.2. Write conflict không giống unique-key conflict

~~~javascript
db.request_log.createIndex(
  { tenantId: 1, operation: 1, requestId: 1 },
  { unique: true }
)
~~~

Hai request cùng insert document có tổ hợp `tenantId + operation + requestId` giống nhau có thể làm một request bị lỗi **duplicate key**:

~~~text
code: 11000
codeName: "DuplicateKey"
~~~

Đây là một **ràng buộc uniqueness** được thực thi, không đồng nhất với lỗi `WriteConflict` code 112. Với request ledger, duplicate key có thể là dấu hiệu hai request dùng cùng idempotency key; ứng dụng cần kiểm tra bản ghi đã có và đối chiếu payload trước khi quyết định replay.

### 5.3. Write concern và timeout cũng khác

Một lệnh có thể:

1. Đã được primary áp dụng.
2. Nhưng client chưa nhận được xác nhận mong muốn từ replica set.
3. Hoặc phản hồi bị mất trên mạng.

Trong trường hợp này, không được mặc định “lệnh đã thất bại nên chưa ghi”. **Kết quả thao tác có thể không chắc chắn** dù client thấy timeout, network error hoặc write concern error.

## 6. Bảng phân loại kết quả và lỗi

| Tình huống | Ý nghĩa thường gặp | Retry/ứng xử thích hợp |
|---|---|---|
| `modifiedCount = 1` | Conditional update đã áp dụng thay đổi | Trả thành công; lưu kết quả nếu cần replay |
| `matchedCount = 0` | Không có document thỏa filter/version/stock | Xử lý như kết quả nghiệp vụ, không coi là transient |
| `WriteConflict` (ví dụ code 112) | Thao tác/transaction gặp cạnh tranh ghi | Với transaction có nhãn transient, abort và retry **cả transaction** theo giao thức |
| `TransientTransactionError` label | Transaction gặp điều kiện tạm thời | Có thể retry transaction body bằng helper driver và backoff/budget |
| `UnknownTransactionCommitResult` label | Chưa xác định kết quả commit transaction | Retry **commit**/reconcile theo request ID; không mặc định chạy lại tác động |
| `DuplicateKey` / E11000 | Vi phạm unique index | Kiểm tra key nào trùng, đối chiếu ledger/business identity; không retry mù |
| Validation error | Payload/schema không hợp lệ | Sửa đầu vào; gửi y nguyên không giúp |
| Insufficient stock | Điều kiện available không thỏa | Trả kết quả nghiệp vụ; không tự tạo nhiều lần đặt hàng |
| Network timeout sau ghi | Có thể ghi đã thành công | Dùng cùng request ID để kiểm tra/replay; không tạo operation mới |
| Write concern timeout | Không nhận mức xác nhận mong muốn | Trạng thái có thể chưa rõ; kiểm tra/reconcile |
| Transaction lifetime exceeded | Transaction quá lâu/tài nguyên không đáp ứng | Thiết kế transaction ngắn, xử lý lỗi phù hợp, không vòng lặp vô hạn |

**Cảnh báo:** bảng này là định hướng. Một lỗi có thể đi kèm nhiều thông tin, và quyết định retry phải dựa vào **ngữ cảnh thao tác + nhãn lỗi + hợp đồng nghiệp vụ**. Không gộp tất cả lỗi có chữ “conflict”, “timeout” hoặc “duplicate” vào một nhánh `retry()`.

## 7. Ba tầng retry không tương đương

~~~mermaid
flowchart TD
    User["Client gửi request có ID ổn định"] --> HTTP["Application/API retry"]
    HTTP --> Logic["Business operation"]
    Logic --> Driver["Driver retryable write"]
    Driver --> Server["MongoDB"]
    Logic --> Tx["Transaction helper retry"]
    Tx --> Server
    Note["Identity của request phải sống qua mọi tầng retry"] -.-> HTTP
    Note -.-> Logic
~~~

### 7.1. Retryable writes ở mức driver

Trong topology và phiên bản hỗ trợ, MongoDB driver có cơ chế **retryable writes** cho những lệnh ghi đủ điều kiện, thường gắn với session và identity của write operation. Driver có thể thử lại khi gặp lỗi mạng hoặc lỗi tạm thời phù hợp mà không biến đó thành một **logical write mới** theo giao thức retryable writes.

Nhưng:

- Không phải mọi lệnh đều thuộc nhóm retryable writes; ví dụ các ghi đa document có những giới hạn khác với ghi một document.
- Không phải mọi lỗi được tự động retry.
- Không phải mọi deployment đều bật/hỗ trợ giống nhau.
- Một request HTTP được gửi lại có thể tạo **driver operation hoàn toàn mới** với identity khác.
- Nếu business function gồm nhiều lệnh MongoDB và side effect ngoài DB, retryable write cho từng lệnh **không** biến toàn function thành giao dịch idempotent.

Ví dụ:

~~~javascript
// Một invocation của driver có thể được driver retry theo cơ chế hỗ trợ.
db.counters.updateOne(
  { _id: "views" },
  { $inc: { value: 1 } }
)
~~~

Nếu **ứng dụng tự gọi `updateOne()` lần thứ hai** sau timeout như một thao tác mới, cả hai invocation có thể tăng counter. Không dùng “driver có retryWrites=true” như bằng chứng rằng hành vi cấp API idempotent.

### 7.2. Retry transaction

Multi-document transaction có nhiều thao tác đọc/ghi cùng phạm vi commit. Khi một transaction gặp lỗi transient như write conflict, ứng dụng có thể phải **abort rồi chạy lại toàn bộ transaction body** trên một snapshot mới.

Nếu transaction đã thực hiện xong phần body nhưng kết quả **commit không chắc chắn**, chiến lược đúng có thể là **retry commit của transaction đó**, không chạy lại một transaction business mới ngay lập tức.

Driver cung cấp helper như `withTransaction()` hoặc `withSession()` tùy ngôn ngữ. Helper có cơ chế xử lý các nhãn transient/unknown commit theo driver specification; vẫn cần lập kế hoạch khi helper trả lỗi cuối cùng hoặc hết thời gian thử.

### 7.3. Retry ở cấp API và hàng đợi

Một HTTP client, message broker consumer hoặc scheduler có thể gửi lại cùng công việc sau timeout, crash hoặc redelivery. Đây là **business retry**; nó có thể chạy trên một process khác, session khác và transaction khác. Muốn an toàn, cần khóa idempotency/identity ổn định **vượt qua các lần chạy**.

Ví dụ:

~~~text
POST /reservations
Idempotency-Key: reservation-r-123

Body: { sku: "sku-A", qty: 1 }
~~~

Nếu client gửi lại, server phải nhận ra đây là **cùng intent R123**, không phải một đơn đặt chỗ mới.

### 7.4. Retry của application không được vô hạn

Ngay cả thao tác có thể retry cũng cần:

- Số lần thử hoặc thời gian ngân sách tối đa.
- Backoff theo lũy thừa và jitter.
- Timeout tổng và deadline của request.
- Phân biệt lỗi transient với permanent.
- Logging/metrics theo request ID, không ghi thông tin nhạy cảm.
- Cơ chế dừng hoặc đưa vào dead-letter khi không thể hoàn tất.

Retry không kiểm soát có thể tạo **retry storm**, làm tăng contention và khiến hệ thống vừa lỗi càng lỗi nặng hơn.

## 8. Transaction và cạnh tranh: vì sao có thể phải chạy lại toàn bộ

Giả sử cần chuyển 100 đơn vị tiền giữa hai tài khoản lưu trong hai document:

~~~javascript
// accounts
{ _id: "acc-A", balanceCents: 20000 }
{ _id: "acc-B", balanceCents: 5000 }
~~~

Nếu trừ tài khoản A thành công nhưng process chết trước khi cộng tài khoản B, dữ liệu không còn cân bằng. Một multi-document transaction có thể giúp hai update **cùng commit hoặc cùng abort** trong deployment hỗ trợ.

### 8.1. Mẫu thao tác bên trong transaction

~~~javascript
// Pseudocode của phần thân transaction:
const debit = accounts.updateOne(
  { _id: "acc-A", balanceCents: { $gte: 10000 } },
  { $inc: { balanceCents: -10000 } },
  { session }
)

if (debit.matchedCount !== 1) {
  throw new Error("INSUFFICIENT_FUNDS")
}

accounts.updateOne(
  { _id: "acc-B" },
  { $inc: { balanceCents: 10000 } },
  { session }
)
~~~

Đây là **pseudocode**: trong mã thực cần `await` với driver async, kiểm tra tài khoản nhận có tồn tại, số tiền hợp lệ, bảo mật và xử lý error. Một transaction cần có commit rõ ràng và write concern thích hợp. Dùng số nguyên đơn vị nhỏ nhất như cents hoặc Decimal128 để tránh sai số dấu phẩy động.

### 8.2. Hai transaction cùng sửa một tài khoản

~~~mermaid
sequenceDiagram
    participant A as Transaction A
    participant DB as MongoDB
    participant B as Transaction B
    A->>DB: Bắt đầu snapshot và đọc acc-A
    B->>DB: Bắt đầu snapshot và đọc acc-A
    A->>DB: Ghi acc-A
    B->>DB: Cố ghi acc-A cùng thời điểm
    DB-->>B: Có thể WriteConflict / transient abort
    A->>DB: commit
    DB-->>A: thành công
    B->>DB: Retry transaction mới, đọc trạng thái mới
~~~

MongoDB không cho hai transaction cùng giả định chúng đều có thể commit trên một lịch sử cập nhật mâu thuẫn. Khi B bị abort, phần ghi của B trong transaction không được commit. Retry toàn transaction phải đọc lại điều kiện và số dư/tồn kho hiện tại; **không được giữ kết quả kiểm tra từ snapshot cũ**.

### 8.3. Tại sao không retry mỗi lệnh cuối?

Nếu transaction đã đọc dữ liệu ở snapshot cũ, chỉ chạy lại lệnh update bị lỗi mà vẫn giữ quyết định từ snapshot đó có thể vi phạm invariant nghiệp vụ. Khi transaction bị abort vì transient error, cách tiếp cận đúng là tạo/được helper tạo một lần thực thi transaction mới, **đọc lại dữ liệu, kiểm tra lại điều kiện, thực hiện lại toàn body**.

### 8.4. Vì sao callback transaction phải tránh side effect ngoài database?

Một helper driver có thể gọi callback nhiều lần:

~~~javascript
// CẦN TRÁNH trong callback có thể được thực thi lại:
await sendEmail("Đã chuyển tiền")
await chargeCardWithNewPaymentId()
await publishMessageWithoutDedupe()
~~~

Nếu transaction bị abort sau khi email đã gửi, callback chạy lại có thể gửi thêm email. Transaction MongoDB **không rollback email, HTTP API, payment gateway hoặc message broker**.

Để kết hợp thay đổi MongoDB với external side effect, xem mẫu **transactional outbox** ở phần sau.

## 9. Phân biệt `TransientTransactionError` và `UnknownTransactionCommitResult`

Hai nhãn này dẫn tới hai chiến lược khác nhau:

### 9.1. Lỗi transient khi transaction body đang chạy

Một lỗi có nhãn `TransientTransactionError` thường cho biết transaction hiện tại cần được bỏ và **thử lại toàn bộ transaction** (theo giao thức driver phù hợp).

~~~text
Transaction A:
  read stock
  update stock
  write ledger
  -> TransientTransactionError

Retry:
  bắt đầu transaction mới
  đọc lại stock
  cập nhật hoặc từ chối theo điều kiện hiện tại
  ghi/replay ledger
  commit
~~~

Khi retry, điều kiện nghiệp vụ có thể đổi: lần trước còn stock, lần sau hết stock. Đó là hành vi đúng vì retry không được dùng snapshot đã lỗi.

### 9.2. Kết quả commit chưa rõ

Trong tình huống:

~~~text
Client gửi commitTransaction
MongoDB có thể đã commit
Phản hồi commit bị mất
~~~

driver có thể gắn nhãn `UnknownTransactionCommitResult`. **Không được mặc định transaction đã abort** và bắt đầu một giao dịch nghiệp vụ mới với khóa mới.

Hành động phù hợp:

1. Dùng cơ chế retry **commit** của cùng transaction nếu vẫn nằm trong ngữ cảnh driver/session phù hợp.
2. Khi không thể xác định, tra cứu **request ledger** bằng identity ổn định.
3. Trả trạng thái chưa xác định/đang xử lý theo hợp đồng API nếu chưa reconcile được.
4. Mọi lần gửi lại ở cấp API phải giữ **cùng idempotency key**.

### 9.3. Không đánh đồng ACK với sự thật nghiệp vụ

Ứng dụng thấy “timeout” không chứng minh MongoDB chưa commit; ứng dụng thấy “request retry thành công” cũng không chứng minh các external side effect chỉ chạy một lần. Cần ranh giới cam kết rõ:

- **MongoDB transaction**: phạm vi các ghi trong MongoDB được đưa vào transaction.
- **Idempotency ledger**: nhận diện một yêu cầu nghiệp vụ qua nhiều lần gọi.
- **Outbox / consumer dedupe**: điều phối tác động ngoài MongoDB có khả năng bị gửi/nhận lặp.

## 10. Idempotency: định nghĩa chính xác

Một operation `f` được gọi là idempotent nếu áp dụng cùng intent thêm lần nữa **không tạo thêm thay đổi so với lần áp dụng thành công đầu tiên** trong phạm vi hợp đồng đã định.

~~~text
Đặt trạng thái: set status = "DONE"
  Gửi lại nhiều lần thường giữ trạng thái DONE

Tăng số: $inc counter by 1
  Gửi lại operation mới nhiều lần tăng nhiều lần

Chuyển tiền 100.000đ:
  Cùng requestId phải chỉ chuyển một lần
  Hai requestId khác nhau có thể là hai lần chuyển hợp lệ
~~~

Idempotency **không có nghĩa** tất cả request cùng body đều phải được coi là một. Nếu người dùng thực sự mua **hai sản phẩm giống nhau trong hai lần đặt hàng**, hai intent hợp lệ phải có **hai request ID khác nhau**.

### 10.1. Phân biệt ba loại khóa

| Loại khóa | Ví dụ | Vai trò |
|---|---|---|
| Business identity | `orderId = ord-101` | Nhận diện thực thể nghiệp vụ |
| Idempotency/request identity | `requestId = R-abc` | Nhận diện một **ý định thao tác** qua retry |
| Driver retry identity | Session/transaction statement identity | Hỗ trợ retry một operation ở tầng driver theo cơ chế MongoDB |

Các loại identity có thể liên quan nhưng không tự thay thế nhau. Với API tạo order, có thể dùng `orderId` do client sinh ổn định như business key kiêm idempotency boundary, hoặc lưu request ID riêng để replay response.

### 10.2. Scope của idempotency key

Một khóa client có thể trùng giữa hai tenant hoặc hai endpoint:

~~~text
tenant=t-01, operation=RESERVE_STOCK, key=R1
tenant=t-02, operation=RESERVE_STOCK, key=R1
tenant=t-01, operation=CANCEL_ORDER,  key=R1
~~~

Ba trường hợp này là ba **identity hợp lệ khác nhau** nếu API định nghĩa scope theo tenant + operation + key.

Khóa unique nên được áp dụng trên đúng scope, chẳng hạn:

~~~javascript
db.request_log.createIndex(
  {
    tenantId: 1,
    operation: 1,
    requestId: 1
  },
  {
    unique: true,
    name: "uq_request_scope"
  }
)
~~~

`tenantId` phải lấy từ ngữ cảnh xác thực, không chỉ từ body do client tự khai báo.

### 10.3. Một key không được đổi payload âm thầm

Lần đầu:

~~~text
key: R1
payload: { sku: "sku-A", qty: 1 }
~~~

Lần sau:

~~~text
key: R1
payload: { sku: "sku-A", qty: 5 }
~~~

Đây không phải retry của cùng intent. API nên báo **IDEMPOTENCY_KEY_REUSED_WITH_DIFFERENT_PAYLOAD** hoặc phản hồi conflict rõ ràng. Muốn làm việc này, lưu **fingerprint** của payload sau canonicalization, không chỉ lưu key.

Canonicalization cần xác định:

- Thứ tự field object không ảnh hưởng ý nghĩa.
- Kiểu số và quy ước Decimal128/int không bị đổi ngầm.
- Các giá trị mặc định được chuẩn hóa trước khi hash.
- Field không ảnh hưởng intent như trace ID hoặc header phụ không làm khác fingerprint nếu contract nói chúng không phải dữ liệu nghiệp vụ.
- Operation và tenant thuộc scope của identity.

Một `JSON.stringify` tùy ý trên object bất kỳ **không luôn là canonical serialization**. Với payload phức tạp, cần bộ quy tắc canonicalization ổn định giữa client/server và giữa các phiên bản API.

## 11. Unique index: chốt chặn bắt buộc chống request trùng

Đoạn mã sau **không an toàn** trước concurrency:

~~~javascript
const old = db.request_log.findOne({
  tenantId: "t-01",
  operation: "RESERVE_STOCK",
  requestId: "R1"
})

if (!old) {
  // Hai worker có thể cùng thấy chưa có key R1.
  db.request_log.insertOne({
    tenantId: "t-01",
    operation: "RESERVE_STOCK",
    requestId: "R1"
  })
}
~~~

Hai worker có thể cùng `findOne()` được `null` trước khi bất kỳ worker nào insert. Đây là **check-then-insert race**.

### 11.1. Dùng unique index

~~~javascript
db.request_log.createIndex(
  { tenantId: 1, operation: 1, requestId: 1 },
  { unique: true, name: "uq_request_scope" }
)
~~~

Nếu hai writer cùng insert cùng scope, chỉ một bản ghi có thể tồn tại; writer còn lại nhận duplicate key hoặc xung đột phù hợp với tình huống transaction. **Unique index là hàng rào cuối cùng**, không phụ thuộc vào việc mọi ứng dụng đều kiểm tra trước.

### 11.2. Duplicate key phải được diễn giải đúng

Không dùng:

~~~javascript
try {
  // insert request marker
} catch (err) {
  if (err.code === 11000) {
    return { success: true } // SAI: chưa biết key nào trùng và request cũ làm gì.
  }
}
~~~

Thay vào đó:

1. Phân biệt duplicate key thuộc **index request scope** hay index business khác.
2. Đọc bản ghi request theo scope chính xác.
3. So fingerprint.
4. Nếu đã hoàn tất, trả kết quả đã lưu.
5. Nếu request còn xử lý, áp dụng trạng thái pending/wait/retry có giới hạn.
6. Nếu khác payload, trả conflict, **không áp dụng tác động mới**.

### 11.3. Chỉ tạo marker rồi update business ở bên ngoài không đủ

~~~text
1. insert request marker R1 thành công
2. process crash trước khi trừ stock
3. Retry thấy marker R1 rồi trả "đã xử lý"
~~~

Đây là **mất tác động**, dù không trùng. Ngược lại:

~~~text
1. trừ stock
2. process crash trước khi ghi request marker
3. Retry không thấy marker và trừ stock lần nữa
~~~

Đây là **tác động lặp**. Nếu marker và business update nằm ở **hai document** và cần cùng nhất quán, hãy dùng **multi-document transaction** hoặc thiết kế một thao tác nguyên tử trong cùng một document khi có thể.

## 12. Request ledger và state machine

Một ledger có thể lưu:

~~~javascript
{
  _id: ObjectId("..."),
  tenantId: "t-01",
  operation: "RESERVE_STOCK",
  requestId: "R1",
  payloadHash: "sha256-canonical-payload",
  state: "COMPLETED",
  result: {
    ok: true,
    reservationId: "res-101",
    sku: "sku-A",
    qty: 1
  },
  createdAt: ISODate("2026-11-01T10:00:00Z"),
  completedAt: ISODate("2026-11-01T10:00:01Z")
}
~~~

Đối với thao tác ngắn gọn trong một transaction, có thể **insert ledger, update business và lưu result trong cùng transaction**. Bản ghi ledger chỉ hiển thị sau commit nếu tất cả cùng commit; trạng thái `PROCESSING` tạm thời bên trong transaction không được dùng như “khóa đã phát hành” cho request khác trước commit.

### 12.1. Các trạng thái thường gặp

~~~mermaid
stateDiagram-v2
    [*] --> RECEIVED
    RECEIVED --> PROCESSING: Claim request
    PROCESSING --> COMPLETED: Commit thành công
    PROCESSING --> REJECTED: Quy tắc nghiệp vụ từ chối
    PROCESSING --> RETRYABLE: Lỗi tạm thời
    RETRYABLE --> PROCESSING: Retry cùng requestId
    PROCESSING --> UNKNOWN: Mất phản hồi / commit chưa rõ
    UNKNOWN --> COMPLETED: Reconcile thấy kết quả
    UNKNOWN --> RETRYABLE: Chứng minh chưa commit
~~~

Đây là **mô hình ứng dụng**, không phải trạng thái tự động do MongoDB cung cấp. Cách lưu các trạng thái này phụ thuộc thiết kế:

- Với **short transaction** lưu marker và tác động cùng commit, bên ngoài có thể chỉ thấy trạng thái terminal `COMPLETED/REJECTED`.
- Với **long-running process** (gọi payment gateway, xử lý file), thường cần persisted `PROCESSING` kèm lease/heartbeat, recovery worker và trạng thái terminal.
- `UNKNOWN` biểu thị **chưa biết kết quả**, không đồng nghĩa thất bại và không cho phép thực thi lại với key mới.

### 12.2. Có nên lưu thất bại nghiệp vụ?

Giả sử request R1 bị từ chối vì hết hàng. Sau đó có hàng nhập thêm và client retry R1. Nếu contract định nghĩa “cùng request luôn được replay cùng kết quả”, cần **lưu cả kết quả OUT_OF_STOCK** để lần sau vẫn trả như cũ. Nếu contract cho phép retry quyết định sau khi điều kiện kinh doanh thay đổi, cần quy định rõ key và trạng thái mới; **không được tùy tiện thay đổi ý nghĩa của cùng requestId**.

Một phương án phổ biến: ghi trạng thái `REJECTED` và response ổn định cho lỗi nghiệp vụ terminal; không lưu thành công giả cho lỗi hạ tầng transient.

### 12.3. Dữ liệu lưu trong ledger

Nên lưu đủ:

- Scope: tenant, operation, requestId.
- Fingerprint/canonical payload hoặc thông tin cần kiểm tra equivalence.
- Trạng thái và kết quả đủ để replay contract.
- Business entity ID đã tạo/đã tác động.
- Mốc thời gian, phiên bản schema/API, attempt metadata khi cần.

Tránh lưu thông tin bí mật hoặc payload thanh toán nhạy cảm không cần thiết. Ledger cũng phải được phân quyền, mã hóa/lưu trữ theo chính sách, giám sát dung lượng và có chính sách retention.

## 13. Thiết kế end-to-end: reserve stock đúng một lần

Yêu cầu nghiệp vụ:

> API nhận một yêu cầu giữ `qty` đơn vị của `sku`. Cùng `tenantId + operation + requestId` được gửi lại phải không giữ hàng lần thứ hai và trả kết quả của lần đã xử lý. Hai `requestId` khác nhau có thể là hai giao dịch giữ hàng độc lập.

Dữ liệu:

~~~javascript
// inventory
{
  _id: "sku-A",
  tenantId: "t-01",
  available: 10,
  reserved: 0
}

// request_log
// Unique index trên tenantId + operation + requestId
~~~

### 13.1. Thuật toán transaction

~~~text
Input: authenticatedTenantId, requestId, sku, qty

Validate:
  qty là số nguyên dương trong giới hạn
  sku hợp lệ, tenant đã xác thực
  requestId có định dạng và độ dài được phép

Identity = (tenantId, "RESERVE_STOCK", requestId)
Fingerprint = SHA256(canonical({sku, qty}))

BEGIN TRANSACTION
  existing = request_log.findOne(Identity)
  if existing:
    if existing.fingerprint != Fingerprint: CONFLICT
    return existing.savedResult

  request_log.insertOne(Identity, Fingerprint, trạng thái tạm)

  updated = inventory.findOneAndUpdate(
    sku + tenant + available >= qty,
    $inc available -= qty, reserved += qty
  )

  if không tìm thấy/không đủ stock:
    result = OUT_OF_STOCK
  else:
    result = RESERVED với reservationId ổn định

  request_log.updateOne(Identity, state=COMPLETED, result)
COMMIT TRANSACTION

Return savedResult
~~~

**Vì insert ledger, cập nhật inventory và lưu result cùng một transaction**, một lần commit thành công có thể đem lại một outcome nhất quán cho business operation. Nếu transaction abort, không có bản ghi ledger và không có giảm stock nào thuộc transaction đó được commit.

### 13.2. Đồng thời cùng requestId

~~~mermaid
sequenceDiagram
    participant A as Request A / R1
    participant B as Request B / R1
    participant DB as MongoDB
    A->>DB: Transaction insert ledger R1
    B->>DB: Transaction insert ledger R1
    Note over DB: Unique index chỉ cho một record R1
    A->>DB: Giảm stock và lưu result
    A->>DB: Commit
    DB-->>A: RESERVED
    DB-->>B: Duplicate key / conflict / transient abort
    B->>DB: Đọc lại ledger R1 sau khi outcome rõ
    DB-->>B: Trả result đã lưu, không trừ thêm
~~~

Thứ tự thực tế phụ thuộc scheduling: bên nào thắng có thể đảo, một transaction có thể retry hoặc thấy bản ghi đã commit. **Không giả định lỗi sẽ luôn là E11000**. Unique constraint và transaction tạo hàng rào; tầng ứng dụng cần xử lý các nhánh lỗi/commit chưa chắc chắn.

### 13.3. Đồng thời hai requestId khác nhau

~~~text
R1 giữ 1 đơn vị sku-A
R2 giữ 1 đơn vị sku-A
~~~

Đây là **hai intent khác nhau**, không được dedupe chỉ vì cùng SKU/qty. Nếu stock đủ, cả hai có thể thành công. Nếu stock không đủ, conditional update chặn overselling; trong transaction, cạnh tranh có thể phát sinh transient write conflict và phải retry rồi kiểm tra lại stock mới.

### 13.4. Lưu trạng thái OUT_OF_STOCK

Nếu không còn hàng, transaction vẫn có thể commit **ledger kết quả từ chối** mà không sửa inventory:

~~~javascript
{
  ok: false,
  code: "OUT_OF_STOCK",
  sku: "sku-A",
  qty: 1
}
~~~

Khi client gửi lại cùng R1 sau khi kho được nhập thêm, API replay kết quả từ chối (nếu contract đã chọn semantics này). Muốn đặt hàng lại theo trạng thái kho mới, client tạo **request mới với requestId mới**.

## 14. Mẫu Node.js Driver: ledger + transaction + conditional update

Ví dụ sử dụng MongoDB Node.js Driver hiện đại, trong môi trường có transaction support. Nó minh họa khung xử lý cơ bản; production cần bổ sung authentication, request tracing, error mapping, rate limiting, schema validation và chính sách retention.

### 14.1. Index và dữ liệu ban đầu

Chạy trong mongosh ở `write_conflict_lab`:

~~~javascript
db.inventory.insertOne({
  _id: "sku-A",
  tenantId: "t-01",
  available: 10,
  reserved: 0,
  version: 1
})

db.request_log.createIndex(
  { tenantId: 1, operation: 1, requestId: 1 },
  { unique: true, name: "uq_request_scope" }
)
~~~

### 14.2. Hàm xử lý business

~~~javascript
import { MongoClient } from "mongodb";
import { createHash } from "node:crypto";

// Dùng connection string của replica set/sharded cluster có transaction support.
const client = new MongoClient(process.env.MONGODB_URI);
await client.connect();

const database = client.db("write_conflict_lab");
const inventory = database.collection("inventory");
const requests = database.collection("request_log");

class IdempotencyConflict extends Error {
  constructor() {
    super("IDEMPOTENCY_KEY_REUSED_WITH_DIFFERENT_PAYLOAD");
    this.name = "IdempotencyConflict";
  }
}

async function reserveStock({
  tenantId,       // Lấy từ auth context.
  requestId,      // Client giữ ổn định qua retry.
  sku,
  qty
}) {
  if (!tenantId || !requestId || !sku ||
      !Number.isSafeInteger(qty) || qty <= 0 || qty > 1000) {
    throw new Error("INVALID_INPUT");
  }

  const identity = {
    tenantId,
    operation: "RESERVE_STOCK",
    requestId
  };

  // Với payload cố định {sku, qty}, thứ tự key được chủ động ổn định.
  // Với JSON tổng quát phải dùng canonicalization nhất quán hơn.
  const fingerprint = createHash("sha256")
    .update(JSON.stringify({ sku, qty }))
    .digest("hex");

  const session = client.startSession();

  try {
    return await session.withTransaction(async () => {
      const previous = await requests.findOne(identity, { session });

      if (previous) {
        if (previous.fingerprint !== fingerprint) {
          throw new IdempotencyConflict();
        }
        return previous.result;
      }

      await requests.insertOne({
        ...identity,
        fingerprint,
        state: "PROCESSING",
        createdAt: new Date()
      }, { session });

      const updated = await inventory.findOneAndUpdate(
        {
          _id: sku,
          tenantId,
          available: { $gte: qty }
        },
        {
          $inc: {
            available: -qty,
            reserved: qty,
            version: 1
          }
        },
        {
          session,
          returnDocument: "after",
          projection: {
            _id: 1,
            available: 1,
            reserved: 1
          }
        }
      );

      const result = updated === null
        ? {
            ok: false,
            code: "OUT_OF_STOCK",
            sku,
            qty
          }
        : {
            ok: true,
            code: "RESERVED",
            sku,
            qty,
            remaining: updated.available
          };

      await requests.updateOne(
        identity,
        {
          $set: {
            state: "COMPLETED",
            result,
            completedAt: new Date()
          }
        },
        { session }
      );

      return result;
    }, {
      readConcern: { level: "snapshot" },
      writeConcern: { w: "majority" }
    });
  } catch (error) {
    // Xử lý ngoài transaction: không được giả định lỗi = chưa commit.
    // Một request trùng key, lỗi commit chưa rõ hoặc network error
    // cần được đối chiếu theo identity trước khi quyết định kết quả API.
    if (error.code === 11000 ||
        error.hasErrorLabel?.("UnknownTransactionCommitResult")) {
      const existing = await requests.findOne(identity);
      if (existing) {
        if (existing.fingerprint !== fingerprint) {
          throw new IdempotencyConflict();
        }
        if (existing.state === "COMPLETED") {
          return existing.result;
        }
      }
    }

    // Không biết outcome hoặc lỗi chưa phục hồi: để tầng API
    // báo trạng thái phù hợp / retry cùng key theo ngân sách.
    throw error;
  } finally {
    await session.endSession();
  }
}

// Khi kết thúc vòng đời ứng dụng, đóng client bằng await client.close().
~~~

### 14.3. Giải thích những điểm quan trọng

1. **Identity ổn định:** `tenantId + operation + requestId` được dùng để đọc/ghi ledger. Unique index ngăn hai bản ghi cùng identity.
2. **Fingerprint:** phát hiện client dùng lại key với payload khác. Ví dụ dùng thứ tự field cố định; production cần canonicalization tổng quát nếu payload phức tạp.
3. **Transaction:** marker, stock update và kết quả được commit cùng nhau.
4. **Conditional update:** `available >= qty` được kiểm tra ngay trong lệnh ghi, tránh overselling.
5. **Replay:** nếu ledger đã commit, request lặp trả `previous.result` mà không giảm stock thêm.
6. **Retry transaction:** `withTransaction` có thể thực hiện lại callback khi gặp lỗi transient theo giao thức driver; callback **không gọi dịch vụ ngoài**.
7. **Unknown outcome:** catch không tự coi mọi exception là abort; nếu chưa thấy record, không tạo key mới rồi thử lại thao tác bất chấp.
8. **No stock:** result `OUT_OF_STOCK` cũng được lưu, tạo semantics replay ổn định.

### 14.4. Các giới hạn của snippet

- Đoạn mã **không thay thế** service hoàn chỉnh; cần dùng connection URI hợp lệ và thiết lập triển khai hỗ trợ transaction.
- Kết quả `findOneAndUpdate` phụ thuộc phiên bản API của Node driver; code trên giả định driver hiện đại trả document hoặc `null` trực tiếp theo mặc định, không phải wrapper kiểu cũ có `value`.
- Nếu gặp duplicate key do transaction khác đang tranh chấp **chưa commit**, đọc ledger ngay có thể chưa thấy bản ghi; cần bounded retry/reconcile. Không tự kết luận “không thấy key nên insert lại với key mới”.
- Với kết quả commit không chắc chắn, driver helper có thể đã retry commit; nếu cuối cùng vẫn trả exception, cần xử lý ở cấp API theo hợp đồng `UNKNOWN/PENDING` và dùng cùng requestId cho các lần hỏi lại.
- Một transaction có thể abort vì lỗi hạ tầng, thời gian sống quá dài hoặc contention; không nên kéo HTTP call, email hoặc payment gateway vào callback.
- Điều kiện `_id = sku` trong ví dụ giả định SKU được định danh duy nhất toàn collection. Nếu thực tế `sku` chỉ duy nhất **trong tenant**, khóa document phải được thiết kế lại để không trùng xuyên tenant (ví dụ `_id` có namespace tenant hoặc dùng unique compound key).
- Nếu cần **reservationId** bất biến, hãy sinh/định nghĩa ID theo requestId và lưu trong result cùng transaction; không tạo ID mới mỗi lần replay.

## 15. Nếu chỉ thay đổi một document: tránh transaction khi không cần

Transaction hữu ích khi cần đồng bộ **nhiều document**. Nếu một operation có thể được biểu diễn bằng một atomic update trên **một document**, cách đó có thể đơn giản và rẻ hơn.

Ví dụ một counter theo công việc, chỉ cho cùng request ID tăng một lần:

~~~javascript
db.job_counters.insertOne({
  _id: "job-1",
  completed: 0,
  appliedRequestIds: []
})
~~~

Thao tác:

~~~javascript
const requestId = "R1"

const result = db.job_counters.updateOne(
  {
    _id: "job-1",
    appliedRequestIds: { $ne: requestId }
  },
  {
    $inc: { completed: 1 },
    $addToSet: { appliedRequestIds: requestId }
  }
)
~~~

Filter kiểm tra requestId **chưa xuất hiện**, còn `$inc` và `$addToSet` xảy ra trong **cùng update một document**. Hai lần gửi cùng R1 thường chỉ có lần đầu khớp; lần sau `matchedCount = 0`.

### 15.1. Giới hạn quan trọng

- Mảng `appliedRequestIds` tăng theo số request, có thể làm document rất lớn và tạo contention/hot document.
- Giới hạn BSON 16 MiB và chi phí duy trì array khiến mẫu này **không phù hợp lịch sử request không giới hạn**.
- Muốn replay toàn bộ response phức tạp vẫn cần nơi lưu result.
- Nếu caller cần phân biệt request đã dùng với điều kiện khác không khớp, cần readback phù hợp.

Đây là mẫu có ích cho **scope nhỏ, số key có giới hạn** hoặc cửa sổ xử lý ngắn. Với hệ thống có hàng triệu request, ledger riêng thường dễ quản lý retention và quy mô hơn.

### 15.2. `$set` và `$addToSet` có phải luôn idempotent?

~~~javascript
db.orders.updateOne(
  { _id: "ord-1" },
  { $set: { status: "PAID" } }
)
~~~

Thường có hiệu ứng idempotent về **trạng thái field status** khi lặp lại cùng giá trị. Nhưng nếu operation còn tạo email, audit event hoặc cập nhật counter ngoài document, toàn workflow chưa chắc idempotent.

~~~javascript
db.orders.updateOne(
  { _id: "ord-1" },
  { $addToSet: { tags: "vip" } }
)
~~~

`$addToSet` tránh thêm **cùng phần tử vào array** nhiều lần theo quy tắc so sánh phần tử, nhưng không tự giải quyết mọi business intent, mảng lớn, hay những object có cấu trúc khác nhau. Idempotency cần được định nghĩa ở mức toàn operation, không chỉ một operator.

## 16. Vì sao retry `$inc` cần đặc biệt cẩn thận?

`$inc` thường được dùng cho:

- Tăng số lượt xem/đếm.
- Giảm stock.
- Cộng/trừ số dư.
- Tăng số lần thử xử lý.
- Tính counter trạng thái.

Nó có tính nguyên tử khi tác động một document, nhưng **không idempotent nếu được chạy thành hai invocation mới**.

### 16.1. Counter loại “có thể sai số”

Một analytics counter không yêu cầu chính xác tuyệt đối có thể chấp nhận mô hình at-least-once hoặc quy tắc hợp nhất về sau. Nhưng phải công bố độ chính xác dự kiến; không dùng mẫu này cho tiền tệ hoặc ràng buộc stock chặt.

### 16.2. Counter cần chính xác

Ví dụ xác nhận đã giao hàng:

~~~text
Request R1: xác nhận một package đã giao
Business effect: tăng deliveredCount đúng 1 lần
~~~

Nếu request R1 có thể redeliver, nên gắn identity ổn định với trạng thái package hoặc request ledger:

~~~javascript
db.packages.updateOne(
  {
    _id: "pkg-101",
    status: { $ne: "DELIVERED" }
  },
  {
    $set: { status: "DELIVERED" }
  }
)
~~~

Nếu cần tăng counter tổng của warehouse **cùng lúc** với đổi trạng thái package ở document khác, cân nhắc transaction hoặc event/outbox + dedupe/reconciliation. Nếu chỉ retry `$inc` trên counter warehouse sau timeout, rất dễ double count.

### 16.3. Cần phân biệt “lệnh lặp” với “ý định lặp”

~~~text
Giống payload: increase counter by 1
  R1 và R2 khác nhau => hai lần tăng hợp lệ
  R1 được gửi hai lần => chỉ một lần tăng nếu contract idempotent
~~~

Không thể suy ra hai request cùng payload là trùng nhau khi thiếu request identity.

## 17. Write conflict và backoff có giới hạn

Khi nhiều worker cùng ghi một hot document, việc đồng loạt retry ngay lập tức có thể tạo **thundering herd**:

~~~text
100 workers gặp transient conflict
100 workers retry ngay lập tức
Lại đụng hot document
Nhiều worker tiếp tục retry
~~~

### 17.1. Chiến lược backoff

Một công thức tham khảo:

\[
\mathrm{delay} = \min(\mathrm{cap}, \mathrm{base}\cdot 2^{\mathrm{attempt}})\times\mathrm{jitter}
\]

Trong đó `jitter` là hệ số ngẫu nhiên có giới hạn để các worker không retry đồng thời. Ví dụ base 20 ms, cap 1.000 ms; ứng dụng cần áp thêm **tổng thời gian tối đa**, không chỉ số lần.

### 17.2. Mẫu retry bên ngoài helper

~~~javascript
// Pseudocode: dùng khi operation/driver layer chưa tự retry
// đúng những lỗi transient tương ứng. Không bọc retry vô hạn.
async function retryTransient(operation, maxAttempts = 4) {
  for (let attempt = 0; attempt < maxAttempts; attempt++) {
    try {
      return await operation();
    } catch (error) {
      const transient = error.hasErrorLabel?.("TransientTransactionError");
      if (!transient || attempt === maxAttempts - 1) {
        throw error;
      }

      const exponential = Math.min(1000, 20 * (2 ** attempt));
      const jitter = 0.5 + Math.random();
      const delay = Math.floor(exponential * jitter);
      await new Promise(resolve => setTimeout(resolve, delay));
    }
  }
}
~~~

Đây là **mẫu minh họa**, không phải lời khuyên bọc trực tiếp mọi `withTransaction()` mà không xét helper đang retry những gì. Một số driver đã tự retry transaction body/commit theo nhãn. Retry chồng nhiều tầng có thể làm tăng số attempt ngoài mong đợi. Với `UnknownTransactionCommitResult`, **không** áp dụng cơ học cùng logic retry whole operation.

### 17.3. Phân loại lỗi trước khi retry

Không retry mù:

- `DuplicateKey` do unique business key — phải đối chiếu key và intent.
- Payload validation — gửi y nguyên vẫn lỗi.
- Hết stock — không tự giả định sẽ có hàng ngay.
- Version mismatch — cần business conflict resolution.
- Authorization failure — retry không tạo thêm quyền.
- Unknown commit outcome — phải retry commit hoặc reconcile trước.

### 17.4. Giảm contention trước khi tăng retry

Backoff giúp giảm áp lực, nhưng giải pháp gốc có thể là:

- Giảm thời gian transaction và số document bị giữ trong transaction.
- Chuyển hot counter sang mô hình có ít contention hơn nếu yêu cầu cho phép.
- Partition workload theo tenant/key hoặc chia hàng đợi xử lý.
- Batch hợp lý, tránh nhiều request cập nhật cùng một global document.
- Đưa tác vụ dài ra khỏi transaction.
- Tối ưu index/filter để các transaction đụng ít dữ liệu hơn.

Retry là **khả năng phục hồi**, không phải thay thế thiết kế concurrency.

## 18. Write concern, read concern và độ bền

### 18.1. Atomicity không đồng nghĩa majority durability

Một update nguyên tử trên document vẫn có thể được xác nhận theo mức write concern cụ thể. Trong replica set:

- `w: 1` thường xác nhận từ primary theo cấu hình tương ứng.
- `w: "majority"` yêu cầu mức xác nhận majority theo semantics của deployment, có tác động tới latency và khả năng tồn tại qua failover.
- Journal/durability và cách ghi nhận commit còn chịu ảnh hưởng cấu hình storage/replica set.

Với thao tác giá trị cao, cần xác định **mức chấp nhận mất dữ liệu khi failover**, không chỉ dựa vào việc client nhận ACK.

### 18.2. Read concern khi đối chiếu ledger

Sau một kết quả commit không chắc chắn, ứng dụng có thể đọc ledger để xác minh. Nếu đọc từ secondary chậm hơn hoặc dùng read preference/read concern không phù hợp, **không tìm thấy bản ghi ngay** chưa chứng minh transaction không commit.

Khi cần reconciliation, phải định nghĩa cách đọc phù hợp với consistency của hệ thống, ưu tiên nguồn có thể quan sát trạng thái commit đáng tin cậy, và retry việc **kiểm tra** trong giới hạn thay vì ngay lập tức tạo tác động mới.

### 18.3. Write concern error không phải business rejection

Nếu MongoDB trả write concern timeout, ứng dụng không nên coi đó tương đương `available < qty`. Một cái là **mức xác nhận ghi chưa đạt/không rõ**, cái kia là **điều kiện nghiệp vụ đã không khớp**.

Trộn hai trạng thái sẽ dẫn đến lỗi nghiêm trọng: khách hàng nhận thông báo “hết hàng” dù kho có thể đã bị trừ, hoặc hệ thống retry tạo giao dịch mới rồi trừ tiếp.

## 19. Transactional outbox: idempotency cho side effect ngoài MongoDB

Giả sử sau khi reserve stock, hệ thống cần phát sự kiện `StockReserved` cho một dịch vụ khác. Nếu gọi broker ngay trong transaction callback, callback có thể chạy lại và phát trùng; broker lại không tham gia commit MongoDB.

### 19.1. Mẫu outbox

Trong **cùng transaction** với inventory và ledger:

~~~javascript
// Pseudocode bên trong transaction MongoDB:
inventory.updateOne(/* trừ hàng với điều kiện */, { session })
request_log.insertOne(/* identity + result */, { session })
outbox.insertOne({
  _id: "event-R1",
  type: "StockReserved",
  requestId: "R1",
  tenantId: "t-01",
  sku: "sku-A",
  qty: 1,
  status: "PENDING",
  createdAt: new Date()
}, { session })
~~~

**Không có network publish trong transaction callback.** Worker ngoài transaction đọc outbox đã commit, phát event, rồi đánh dấu đã gửi.

~~~mermaid
flowchart LR
    API["API reserve R1"] --> TX["MongoDB transaction"]
    TX --> DB1["inventory"]
    TX --> DB2["request ledger"]
    TX --> DB3["outbox event-R1"]
    DB3 --> Worker["Outbox relay"]
    Worker --> Broker["Message broker"]
    Broker --> Consumer["Consumer dedupe event-R1"]
~~~

### 19.2. Outbox vẫn có thể gửi trùng

Worker có thể:

1. Publish event thành công.
2. Crash trước khi đánh dấu outbox là SENT.
3. Khởi động lại và publish cùng event một lần nữa.

Vì vậy outbox thường mang semantics **at-least-once delivery**; consumer cần dedupe theo `eventId` hoặc một business key ổn định, thường với unique index/ledger ở phía nhận. Không tuyên bố outbox tự tạo “exactly once end-to-end”.

### 19.3. External payment API

Khi gọi cổng thanh toán, nếu đối tác hỗ trợ **idempotency key**, nên truyền khóa ổn định tương ứng với intent và lưu mapping giữa internal request ID với external charge ID. Với đối tác không hỗ trợ, cần thiết kế reconciliation/dedupe riêng. MongoDB transaction không thể rollback khoản tiền đã được đối tác xử lý.

### 19.4. Không tạo event ID ngẫu nhiên mỗi lần retry

Nếu request R1 được gửi lại mà ứng dụng tạo `event-Random2` thay vì `event-R1`, consumer có thể coi là hai event độc lập. Event identity phải được ràng buộc rõ vào business operation, nếu mục tiêu là dedupe.

## 20. TTL và chính sách lưu idempotency key

Một request ledger sẽ tăng theo số request. Có thể dùng TTL để dọn những record không cần giữ mãi, nhưng **xóa ledger nghĩa là mất bằng chứng chống lặp trong khoảng thời gian trước đó**.

### 20.1. TTL index tham khảo

~~~javascript
db.request_log.createIndex(
  { expiresAt: 1 },
  { expireAfterSeconds: 0, name: "ttl_request_expiration" }
)
~~~

Mỗi ledger record có thể mang `expiresAt`. TTL monitor xóa document **không tức thì chính xác tại mốc hết hạn**, và quá trình dọn có độ trễ theo cơ chế MongoDB. TTL là công cụ retention, không phải một khóa deadline nghiệp vụ có độ chính xác tức thời.

### 20.2. Retry horizon

Nếu client có thể retry sau 48 giờ nhưng ledger được dọn sau 1 giờ, cùng key có thể bị coi như request mới và tác động lần hai.

Chính sách retention nên dài ít nhất bằng **cửa sổ retry được cam kết** cộng thời gian phục hồi/replay/hàng đợi liên quan, hoặc có một business identity bền vững hơn đảm bảo không lặp.

### 20.3. Khi nào không nên chỉ dựa vào TTL?

Với invoice, payment, order confirmation hoặc chuyển tiền cần truy vết dài hạn, business key/transaction record có thể phải được giữ theo yêu cầu kế toán/pháp lý. Request ledger ngắn hạn có thể hỗ trợ replay API, nhưng **không thay thế** ràng buộc duy nhất bền vững của thực thể nghiệp vụ.

### 20.4. TTL và transaction đang xử lý

Đừng đặt thời gian hết hạn quá ngắn khiến record đang chờ reconciliation bị xóa trước khi kết quả rõ. Cần tách policy cho terminal records và những request đang xử lý/unknown, hoặc chỉ gán `expiresAt` khi an toàn để dọn.

## 21. Sharding, unique index và hot keys

Trên sharded cluster, unique index có những ràng buộc riêng về shard key và phạm vi uniqueness. Không giả định có thể tạo bất kỳ unique index compound nào rồi được enforce toàn cluster như collection unsharded. Khi thiết kế ledger trên sharded collection:

- Xác định shard key, tenant scope và phân phối request IDs.
- Kiểm tra **quy tắc unique index** cho sharded collection theo phiên bản MongoDB.
- Tránh partition để hai bản ghi cùng business identity có thể rơi vào phạm vi không được unique constraint bảo vệ.
- Đánh giá distributed transaction nếu inventory, ledger hoặc outbox nằm trên các shard khác nhau.
- Không dùng một hot counter document toàn cluster nếu mọi request đều ghi vào nó và tạo contention lớn.

Đối với nghiệp vụ tài chính/stock, tính đúng đắn của **unique identity + atomic transaction + routing** quan trọng hơn việc chỉ tối ưu throughput.

### 21.1. Transaction xuyên shard

Một multi-document transaction trên sharded cluster có thêm chi phí điều phối so với cập nhật một document đơn lẻ. Khi scale, có thể:

- Đặt các document liên quan gần nhau theo key phù hợp khi data model cho phép.
- Dùng atomic single-document update cho invariant chỉ thuộc một document.
- Giới hạn transaction time và số document touched.
- Chọn flow outbox/saga khi workflow trải nhiều dịch vụ không thể có một MongoDB transaction chung.

**Không coi transaction là miễn phí** và không dùng nó để bao trọn thao tác mạng dài.

## 22. Từ write conflict đến HTTP contract

API cần phân biệt:

| Tình huống | HTTP/status ứng viên | Phản hồi nên chứa |
|---|---|---|
| Request lần đầu thành công | `200`/`201` | Result và business ID |
| Retry cùng key và payload, đã hoàn tất | Cùng response semantics đã lưu | Replay result, không tác động lần hai |
| Key cũ nhưng payload khác | `409 Conflict` | Mã `IDEMPOTENCY_KEY_REUSED` |
| Stock không đủ, kết quả terminal | `409` hoặc `422` tùy API | Mã `OUT_OF_STOCK` được lưu để replay nếu contract yêu cầu |
| Transaction transient vượt retry budget | `503` hoặc lỗi tạm thời phù hợp | Retry cùng key, không tạo key mới |
| Commit/outcome chưa rõ | `202 Accepted`/pending hoặc lỗi tạm thời rõ semantics | Request ID và cách kiểm tra trạng thái |
| Payload invalid | `400`/`422` | Validation errors |
| User không có quyền | `403`/`404` theo policy | Không tiết lộ tài nguyên trái quyền |

Đây là **lựa chọn thiết kế API**, không phải HTTP code bắt buộc của MongoDB. Một API có thể trả `409` cho version conflict hoặc business rejection, nhưng phải có **machine-readable code** để client không nhầm với transient database conflict.

### 22.1. API có thể cung cấp endpoint tra cứu request

~~~http
POST /reservations
Idempotency-Key: R1

GET /operations/R1
~~~

Endpoint tra cứu trạng thái nên scope theo principal/tenant, không để biết request ID là có thể xem kết quả của người khác. Client khi mất phản hồi nên **truy vấn trạng thái hoặc gửi lại cùng key**, không gửi một key mới để “chắc chắn thành công”.

### 22.2. Không phản hồi thành công khi chưa chắc chắn

Nếu process không biết transaction đã commit, không được tự trả:

~~~javascript
{ ok: true, reservationId: "res-new" }
~~~

khi chưa có bằng chứng. Cũng không được tự trả “đã thất bại, có thể đặt lại với key mới” nếu request cũ có thể đang commit. Một trạng thái **UNKNOWN/PENDING với khả năng reconcile** tốt hơn một lời khẳng định sai.

## 23. Quan sát và vận hành

Các metric hữu ích:

| Metric | Mục đích |
|---|---|
| `write_conflict_count` | Phát hiện contention trong transaction/write path |
| `transaction_retry_count` | Đánh giá số lần chạy lại transaction |
| `unknown_commit_count` | Theo dõi trạng thái commit chưa rõ và khả năng reconcile |
| `idempotency_replay_count` | Tỷ lệ request lặp hợp lệ |
| `idempotency_payload_conflict_count` | Phát hiện key bị dùng lại khác intent |
| `duplicate_key_count` theo index | Phân biệt dedupe expected với lỗi business data |
| `request_pending_age` | Phát hiện request kẹt lâu |
| `hot_document_update_latency` | Quan sát contention trên stock/counter nóng |
| `outbox_delivery_attempts` | Xác định event phát lại và consumer dedupe |
| `p95/p99 operation latency` | Đo tác động retry tới SLO |

Không phải tất cả metric có sẵn nguyên tên trong MongoDB; nhiều số liệu cần **instrumentation trong ứng dụng**, một số lấy từ server metrics/profiler/diagnostic logs theo phiên bản.

### 23.1. Log tối thiểu cho một request

~~~text
traceId=...
tenantId=t-01
operation=RESERVE_STOCK
requestId=R1
attempt=2
transactionOutcome=COMMITTED|ABORTED|UNKNOWN
replayed=true|false
errorCode=...
errorLabels=[...]
durationMs=...
~~~

Hạn chế log dữ liệu nhạy cảm (token, số thẻ, full payload). Nếu request ID có thể chứa thông tin bí mật do client cung cấp, cần quy định format/độ dài và có thể dùng ID được tạo an toàn ở server.

### 23.2. Alert đáng cân nhắc

- Conflict/retry rate tăng đột ngột sau deploy.
- Tỷ lệ request unknown/pending không về terminal.
- Stock âm hoặc counter bất thường dù business invariant cấm.
- Ledger trùng scope (không nên có nếu unique constraint đúng).
- Outbox backlog tăng và consumer duplicate rate tăng.
- Transaction latency tăng và số transaction abort nhiều.
- TTL xóa quá sớm hoặc ledger phát triển vượt ngân sách.

## 24. Phòng lab: atomicity, optimistic concurrency và retry

Thực hành này chỉ sửa **dữ liệu lab**. Để quan sát transaction write conflict thật, cần MongoDB replica set/sharded cluster hỗ trợ transaction. Không bảo đảm hai thao tác đồng thời sẽ luôn tạo lỗi cùng mã: kết quả phụ thuộc scheduling, locking và driver.

### 24.1. Khởi tạo

~~~javascript
use write_conflict_lab

db.inventory.insertOne({
  _id: "sku-lab",
  tenantId: "t-01",
  available: 2,
  reserved: 0,
  version: 1
})

db.request_log.createIndex(
  { tenantId: 1, operation: 1, requestId: 1 },
  { unique: true, name: "uq_request_scope" }
)

db.drafts.insertOne({
  _id: "draft-lab",
  tenantId: "t-01",
  title: "Bản đầu",
  version: 1
})
~~~

Chỉ chạy setup một lần trên database lab rỗng; chạy lại cùng `_id` sẽ gặp duplicate key.

### 24.2. Bài A — Conditional stock update

~~~javascript
const qty = 1

const result = db.inventory.updateOne(
  {
    _id: "sku-lab",
    available: { $gte: qty }
  },
  {
    $inc: {
      available: -qty,
      reserved: qty
    }
  }
)

printjson(result)
printjson(db.inventory.findOne({ _id: "sku-lab" }))
~~~

Thực hiện liên tiếp ba lần. Dự đoán:

~~~text
Ban đầu: available=2, reserved=0
Lần 1:  available=1, reserved=1, modifiedCount=1
Lần 2:  available=0, reserved=2, modifiedCount=1
Lần 3:  available=0, reserved=2, matchedCount=0
~~~

Giải thích vì sao không bị stock âm nhưng **hai lần đầu vẫn có thể là tác động lặp** nếu requestId của chúng giống nhau.

### 24.3. Bài B — Optimistic concurrency

~~~javascript
const before = db.drafts.findOne({ _id: "draft-lab" })

const updateA = db.drafts.updateOne(
  {
    _id: "draft-lab",
    version: before.version
  },
  {
    $set: { title: "Editor A" },
    $inc: { version: 1 }
  }
)

const updateB = db.drafts.updateOne(
  {
    _id: "draft-lab",
    version: before.version
  },
  {
    $set: { title: "Editor B" },
    $inc: { version: 1 }
  }
)

printjson({
  a: updateA.matchedCount,
  b: updateB.matchedCount
})
~~~

Vì cả hai dùng `before.version = 1`, kết quả tuần tự dự kiến:

~~~text
A matchedCount=1
B matchedCount=0
Document cuối: title="Editor A", version=2
~~~

Đây là **version conflict nghiệp vụ**, không nhất thiết là lỗi `WriteConflict` của MongoDB.

### 24.4. Bài C — Unique request key

~~~javascript
const identity = {
  tenantId: "t-01",
  operation: "RESERVE_STOCK",
  requestId: "R1"
}

db.request_log.insertOne({
  ...identity,
  payloadHash: "hash-for-sku-lab-1",
  state: "COMPLETED",
  result: { ok: true, sku: "sku-lab", qty: 1 }
})

// Cố tình chạy lại insert cùng identity:
db.request_log.insertOne({
  ...identity,
  payloadHash: "hash-for-sku-lab-1",
  state: "COMPLETED"
})
~~~

Lệnh thứ hai dự kiến gặp duplicate key. Hãy giải thích vì sao lỗi này **chưa đủ** chứng minh business stock đã được cập nhật nếu marker và stock update không nằm trong cùng transaction.

### 24.5. Bài D — Request key khác payload

~~~javascript
const old = db.request_log.findOne({
  tenantId: "t-01",
  operation: "RESERVE_STOCK",
  requestId: "R1"
})

const incomingHash = "hash-for-sku-lab-5"

if (old && old.payloadHash !== incomingHash) {
  print("IDEMPOTENCY_KEY_REUSED_WITH_DIFFERENT_PAYLOAD")
}
~~~

Mục tiêu: phân biệt **retry cùng intent** với **dùng lại key cho intent mới**. Trong production fingerprint phải là hash của canonical payload thật, không dùng chuỗi minh họa.

### 24.6. Bài E — Quan sát write conflict của transaction

Chạy trên replica set lab, có thể dùng hai phiên mongosh. Mỗi phiên tạo session với transaction và thử sửa **cùng một document** trước khi cả hai commit.

**Phiên A:**

~~~javascript
use write_conflict_lab
const sessionA = db.getMongo().startSession()
const txDbA = sessionA.getDatabase("write_conflict_lab")
sessionA.startTransaction({
  readConcern: { level: "snapshot" },
  writeConcern: { w: "majority" }
})

printjson(txDbA.drafts.findOne({ _id: "draft-lab" }))

txDbA.drafts.updateOne(
  { _id: "draft-lab" },
  { $set: { title: "Transaction A" } }
)

// Chưa commit ngay để phiên B tranh chấp.
~~~

**Phiên B (trong lúc A vẫn mở):**

~~~javascript
use write_conflict_lab
const sessionB = db.getMongo().startSession()
const txDbB = sessionB.getDatabase("write_conflict_lab")
sessionB.startTransaction({
  readConcern: { level: "snapshot" },
  writeConcern: { w: "majority" }
})

printjson(txDbB.drafts.findOne({ _id: "draft-lab" }))

try {
  printjson(txDbB.drafts.updateOne(
    { _id: "draft-lab" },
    { $set: { title: "Transaction B" } }
  ))
} catch (e) {
  printjson({
    code: e.code,
    codeName: e.codeName,
    errorLabels: e.errorLabels,
    message: e.message
  })
  try { sessionB.abortTransaction() } catch (_) {}
}
~~~

**Quay lại phiên A:**

~~~javascript
try {
  sessionA.commitTransaction()
} finally {
  sessionA.endSession()
}
~~~

**Dọn phiên B** nếu transaction còn hoạt động:

~~~javascript
try { sessionB.abortTransaction() } catch (_) {}
sessionB.endSession()
~~~

Trong thực tế, phiên B có thể thấy write conflict/transient error khi sửa document đã bị A ghi trong transaction chưa commit. Điều này phụ thuộc timing; nếu các phiên không chồng lên nhau, kết quả có thể khác. Không buộc test phải nhận đúng code 112 trong mọi lượt. Nếu transaction bị abort, cần **retry transaction mới**, không tiếp tục commit cùng session state đã hỏng.

### 24.7. Bài F — Lost response

Giả lập về mặt logic:

~~~text
Request R2 gửi tới API
Transaction ledger + stock commit
Server mất kết nối trước khi trả JSON
Client retry R2 sau 5 giây
~~~

Hãy thiết kế phản hồi: server tra cứu ledger theo scope, đối chiếu fingerprint, trả result cũ; **không gọi lại $inc** như intent mới.

### 24.8. Bài G — External side effect

Trong transaction callback có lệnh giả:

~~~javascript
await sendEmail("Reserved")
~~~

Giải thích điều gì xảy ra nếu callback được gọi lại sau transient error; sửa thiết kế bằng transactional outbox và consumer dedupe.

### 24.9. Bài H — Retry budget

Một transaction có bốn lần lỗi transient liên tiếp. Thiết kế lịch retry với backoff/jitter, giới hạn tổng deadline, log attempt và fallback khi hết budget. Tại sao không retry ngay 1.000 lần trên một hot document?

### 24.10. Bài I — TTL

API cho phép client retry cùng requestId trong 72 giờ, nhưng TTL ledger chỉ 24 giờ. Điều gì có thể xảy ra ở giờ thứ 50? Đề xuất chính sách retention và business uniqueness bền vững hơn.

## 25. Đáp án định hướng

**Bài A:** Hai lần đầu là hai atomic update hợp lệ nếu chỉ xem stock. Nếu đó là retry cùng R1, hệ thống trừ hai lần: conditional update giải quyết overselling, **không giải quyết idempotency**. Lần thứ ba không đủ hàng nên matchedCount=0.

**Bài B:** A sửa thành version 2, B dùng version cũ nên matchedCount=0. API có thể trả version conflict, yêu cầu đọc lại hoặc merge, không bắt buộc có lỗi WriteConflict.

**Bài C:** Unique index chặn hai ledger record cùng scope. Nếu marker được ghi riêng với stock, crash giữa hai bước vẫn gây mất hoặc trùng hiệu ứng. Cần transaction hoặc thiết kế cùng document.

**Bài D:** Một key với hash khác là **intent conflict**, không phải retry hợp lệ. Trả mã lỗi rõ ràng và không tác động kho.

**Bài E:** Transaction có thể gặp xung đột ghi khi hai phiên cùng sửa document. Khi bị transient abort, chạy lại **toàn bộ transaction** với snapshot mới; khi commit outcome không rõ, retry commit/reconcile.

**Bài F:** Nếu ledger đã commit, replay response của R2. Nếu outcome chưa rõ, giữ requestId và reconcile; không gửi một key mới để tránh double reserve.

**Bài G:** Callback retry có thể gửi email nhiều lần. Ghi outbox cùng transaction; relay publish bên ngoài, consumer dedupe bằng event ID ổn định.

**Bài H:** Backoff+jitter giảm retry storm. Deadline/budget ngăn giữ request và tài nguyên vô hạn; sau đó trả trạng thái cần retry cùng key hoặc đưa job vào cơ chế phục hồi.

**Bài I:** Nếu ledger bị xóa sau 24 giờ, retry ở giờ thứ 50 có thể bị coi là request mới. Chọn retention đủ dài so với retry horizon, thêm uniqueness bền vững theo business entity khi cần.

## 26. Các sai lầm phổ biến

| Sai lầm | Vì sao nguy hiểm? | Cách xử lý |
|---|---|---|
| Coi `$inc` nguyên tử là idempotent | Hai invocation mới sẽ tăng hai lần | Stable request ID + ledger hoặc guard trong cùng document |
| Đọc stock rồi update theo `_id` | Điều kiện stock có thể cũ | Đặt `available:{$gte:qty}` trong atomic filter |
| Coi `matchedCount=0` là WriteConflict | Nhầm kết quả nghiệp vụ với lỗi storage | Phân biệt conflict version/stock với transient error |
| Retry mọi lỗi có chữ “conflict” | Duplicate/validation/version không tự hết lỗi | Phân loại code, label và business meaning |
| Retry commit unknown bằng một transaction mới và key mới | Có thể tác động hai lần | Retry commit/reconcile, giữ cùng key |
| Không dùng unique index cho ledger | Hai worker có thể cùng insert | Unique index đúng scope |
| Chỉ check ledger rồi insert | Check-then-insert race | Unique constraint và transaction |
| Insert marker rồi update stock ngoài transaction | Crash tạo trạng thái nửa vời | Cùng transaction hoặc cùng document |
| Trừ stock rồi ghi ledger riêng | Crash trước marker làm retry trừ lần hai | Transaction |
| Retry transaction body có email/payment call | Side effect bên ngoài không rollback | Outbox/external idempotency |
| Dùng một key với payload khác | Request replay sai intent | Fingerprint + conflict |
| Dedupe mọi request cùng body | Loại nhầm hai đơn hợp lệ | Phân biệt request IDs |
| TTL ledger ngắn hơn cửa sổ retry | Key cũ bị coi là mới | Retention phù hợp hoặc business identity lâu dài |
| Đọc ledger stale rồi kết luận chưa commit | Commit có thể chưa quan sát được | Consistency/reconcile thích hợp |
| Bật retry vô hạn | Retry storm, contention và timeout | Budget + exponential backoff + jitter |
| Cho rằng transaction bao phủ broker/payment | Không có atomic commit xuyên hệ thống | Outbox/saga/consumer dedupe |
| Dùng unique index không phù hợp shard key | Ràng buộc có thể không được enforce như kỳ vọng | Thiết kế sharding và unique scope đúng |
| Log payload/ID nhạy cảm đầy đủ | Rủi ro rò rỉ dữ liệu | Logging tối thiểu, masking |

## 27. Câu hỏi ôn tập

**1. Write conflict là gì?**

Là tình huống cạnh tranh ghi làm một thao tác/transaction không thể tiếp tục hoặc commit theo lịch sử nhất quán được engine chấp nhận, nên có thể bị abort/trả lỗi và cần retry đúng tầng.

**2. Mọi update đồng thời có trả WriteConflict không?**

Không. Nhiều single-document updates có thể được engine điều phối/serialize nguyên tử; một số conflict chỉ lộ ra trong transaction. Không suy ra có lỗi từ việc hai request đến cùng thời điểm.

**3. `modifiedCount=0` có tương đương MongoDB WriteConflict không?**

Không. Nó có thể là kết quả bình thường khi filter không khớp hoặc cập nhật không làm đổi giá trị. Cần xem `matchedCount` và quy tắc nghiệp vụ.

**4. Vì sao `findOne()` rồi `updateOne({_id})` không đủ bảo vệ stock?**

Giữa đọc và ghi, request khác có thể sửa stock. Điều kiện `available >= qty` cần được kiểm tra trong chính atomic update.

**5. Conditional update bảo vệ stock có đảm bảo retry cùng request không trừ lần hai?**

Không. Nếu stock vẫn đủ, request trùng được gửi như operation mới có thể trừ thêm; cần idempotency identity.

**6. Retryable writes bảo đảm điều gì?**

Ở những điều kiện hỗ trợ, driver có thể retry cùng write operation theo MongoDB retryable writes protocol. Nó không biến mọi HTTP retry hay chạy lại business function thành idempotent.

**7. `TransientTransactionError` nên xử lý thế nào?**

Abort transaction hiện tại và retry cả transaction body theo giao thức driver/helper, đọc lại trạng thái trong snapshot mới, có giới hạn số lần/thời gian.

**8. `UnknownTransactionCommitResult` khác thế nào?**

Chưa biết commit đã thành công chưa. Không chạy lại business operation mù; retry commit trong ngữ cảnh phù hợp hoặc đối chiếu ledger bằng request ID.

**9. Vì sao unique ledger index quan trọng?**

Nó chặn hai writer đồng thời tạo hai record cùng tenant/operation/requestId, khắc phục check-then-insert race.

**10. Duplicate key E11000 có luôn nghĩa cùng request đã thành công không?**

Không. Phải xác định index/key trùng, đọc ledger và đối chiếu fingerprint/trạng thái; duplicate key có thể xuất phát từ business constraint khác.

**11. Fingerprint dùng để làm gì?**

Phát hiện một request ID được dùng lại với payload/intent khác; cho phép replay khi cùng key và cùng intent.

**12. Có nên lưu kết quả OUT_OF_STOCK vào ledger không?**

Nếu API chọn semantics “cùng request replay cùng outcome”, có. Nếu muốn xét lại kho khi có hàng mới, dùng request mới hoặc quy tắc khác được định nghĩa rõ.

**13. Tại sao transaction callback không nên gọi payment API?**

Callback có thể được retry; MongoDB không rollback charge bên ngoài, nên dễ thanh toán lặp. Dùng idempotency key phía payment và/hoặc outbox/reconciliation.

**14. Outbox có đảm bảo event không bao giờ được gửi trùng không?**

Không. Relay có thể publish rồi crash trước khi đánh dấu sent, dẫn đến gửi lại. Consumer cần dedupe theo event ID ổn định.

**15. Unique index business và idempotency key khác gì?**

Business index bảo vệ tính duy nhất của thực thể như orderNo. Idempotency key nhận diện một yêu cầu thao tác để replay và tránh lặp hiệu ứng; đôi khi cùng identity nhưng không luôn trùng.

**16. Version mismatch thường là loại lỗi gì?**

Là optimistic concurrency conflict ở tầng nghiệp vụ, thường được phát hiện qua `matchedCount=0` và có thể ánh xạ thành HTTP 409, không mặc định MongoDB WriteConflict.

**17. Tại sao retry cần backoff+jitter?**

Để tránh nhiều worker retry đồng thời trên cùng hot document, giảm contention và retry storm.

**18. Có được retry sau network timeout bằng request ID mới không?**

Không nên. Lần trước có thể đã commit; dùng ID mới có thể làm tác động lặp. Phải giữ cùng ID và reconcile.

**19. TTL ledger ngắn hơn retry horizon gây vấn đề gì?**

Record cũ có thể biến mất trước khi client retry, khiến server coi retry là intent mới. Chọn retention và business uniqueness phù hợp.

**20. MongoDB transaction có tự cung cấp exactly-once end-to-end không?**

Không. Nó nguyên tử trên các ghi MongoDB trong transaction; API retry, external side effects, outbox delivery và consumer cần cơ chế idempotency riêng.

## 28. Bảng ghi nhớ nhanh

| Yêu cầu | Mẫu/giải pháp |
|---|---|
| Tăng counter nguyên tử trong một document | `updateOne({_id},{$inc:{value:1}})` |
| Không trừ stock dưới 0 | `updateOne({_id,available:{$gte:qty}},{$inc:{available:-qty}})` |
| Không ghi đè document đã đổi | `updateOne({_id,version:expected},{$set:{...},$inc:{version:1}})` |
| Chặn ledger trùng request | Unique `{tenantId:1,operation:1,requestId:1}` |
| Cùng request, khác payload | Hash/canonical payload + `409` conflict |
| Lưu ledger và thay đổi business cùng lúc | Multi-document transaction |
| Transaction transient abort | Retry **whole transaction** theo label và budget |
| Transaction commit chưa rõ | Retry **commit**/reconcile, không phát intent mới |
| Retry HTTP sau mất phản hồi | Gửi **cùng Idempotency-Key** |
| Chỉ cần set trạng thái ổn định | `$set` trong điều kiện phù hợp, xét toàn workflow |
| One-document dedupe ít key | Conditional update + `$addToSet` trong cùng document |
| Phát event sau commit | Transactional outbox + consumer dedupe |
| Xử lý external payment | Idempotency key của provider + reconciliation |
| Giảm hot contention | Transaction ngắn, partition hợp lý, backoff+jitter |
| Dọn ledger | TTL sau retry horizon/retention phù hợp |

## 29. Checklist trước khi cho phép retry trong production

- [ ] Đã định nghĩa rõ **một intent nghiệp vụ** và request identity của nó?
- [ ] Client giữ cùng ID qua timeout, retry và redelivery?
- [ ] Idempotency key có scope đúng tenant + operation?
- [ ] Có canonical payload fingerprint để chặn key reuse khác intent?
- [ ] Unique index đã được tạo và kiểm chứng, kể cả với sharded topology?
- [ ] Các thao tác update có điều kiện stock/version ngay trong filter không?
- [ ] Nếu cần nhiều document, business changes và ledger có chung transaction không?
- [ ] Transaction callback có side effect ngoài DB không? Nếu có, đã chuyển sang outbox hoặc giao thức an toàn chưa?
- [ ] Có phân biệt transient transaction error và unknown commit result?
- [ ] Retry của driver/helper và retry của application có bị chồng chéo vô hạn không?
- [ ] Có xử lý duplicate key bằng readback ledger, không tự báo thành công?
- [ ] Nếu request đang pending/unknown, có endpoint/status reconciliation không?
- [ ] Có giới hạn retry attempts, deadline, backoff, jitter và rate limit?
- [ ] Có xử lý terminal business rejection và replay response tương ứng?
- [ ] Ledger retention dài hơn retry horizon, với business uniqueness bền vững khi cần?
- [ ] Observability có requestId, attempt, error labels, outcome, p95/p99, write-conflict rate?
- [ ] Đã thử concurrent same-key, distinct-key, lost response, failover và callback retry?
- [ ] Có kiểm soát quyền/tenant và không log secrets hay dữ liệu nhạy cảm?

## 30. Kết luận

**Write conflict** là một biểu hiện của cạnh tranh ghi trong MongoDB, đặc biệt đáng chú ý với multi-document transactions. Khi thao tác bị abort vì lỗi transient, retry đúng thường là **thực hiện lại toàn bộ transaction** trên trạng thái mới; còn khi commit result chưa rõ, cần **retry commit hoặc reconcile** thay vì tự cho rằng chưa ghi.

Nhưng **retry thành công về mặt hạ tầng không đồng nghĩa tính lặp an toàn ở mức nghiệp vụ**. Cùng một HTTP request có thể được gửi lại sau khi database đã commit. Một lệnh `$inc` nguyên tử vẫn có thể trừ tiền hoặc trừ kho hai lần nếu được gọi như hai thao tác mới. Hãy nhận diện request bằng **idempotency key ổn định**, ràng buộc bằng **unique index**, đối chiếu **payload fingerprint**, lưu **kết quả để replay**, và dùng **transaction** khi ledger với business changes nằm ở nhiều document. Với email, payment hay broker, cần **outbox, dedupe và reconciliation** riêng.

Kết quả mong muốn là một hệ thống **vừa chịu được concurrency, vừa phục hồi được sau timeout/crash, vừa không biến một lần gửi lại thành tác động nghiệp vụ thứ hai**.
