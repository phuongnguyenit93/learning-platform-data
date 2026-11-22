# Kiểm thử cạnh tranh, khóa lạc quan và ràng buộc nghiệp vụ trong MongoDB

Một hệ thống bán hàng còn đúng **một sản phẩm**, nhưng hai khách cùng đặt mua. Một ví điện tử có số dư 100.000 đồng, hai yêu cầu đồng thời muốn trừ 80.000 đồng. Hai người quản trị cùng sửa một đơn hàng và người ghi sau vô tình ghi đè kết quả của người ghi trước. Một request thanh toán đã được MongoDB xử lý nhưng client mất kết nối trước khi nhận xác nhận; ứng dụng gửi lại request, khiến giao dịch có nguy cơ được thực hiện hai lần.

Đây không chỉ là các lỗi “thiếu khóa” hay “thiếu transaction”. Chúng là **lỗi cạnh tranh (race conditions)** liên quan đến thứ tự thao tác, độ nguyên tử, tính nhất quán, identity của yêu cầu và **ràng buộc nghiệp vụ (business invariants)**. Một bài kiểm thử chức năng tuần tự có thể hoàn toàn xanh nhưng production vẫn bán âm kho, tạo lịch đặt chỗ trùng hoặc ghi đè thay đổi của người dùng.

Trong MongoDB, một thao tác ghi đơn lẻ trên **một document** có tính nguyên tử. MongoDB cung cấp conditional updates, unique indexes, transactions và các cơ chế xử lý write conflict. Với Spring Data MongoDB, annotation `@Version` hỗ trợ **optimistic locking** để phát hiện document bị thay đổi từ lúc đọc tới lúc lưu. Tuy vậy, không có một tính năng duy nhất bảo vệ mọi ràng buộc kinh doanh: cần xác định invariant nằm ở một document, nhiều documents, nhiều collections hay cả hệ thống bên ngoài.

Bài thuộc chương **Kiểm thử** của module *Database Engine Document MongoDB*. Nội dung tập trung vào cách **thiết kế và kiểm chứng** sự đúng đắn trước concurrency, không chỉ cách viết query. Ví dụ dùng Java, JUnit 5, MongoDB Java Sync Driver, Spring Data MongoDB và `mongosh`; tên database/URL là giả lập. Các đoạn thử nghiệm có ghi dữ liệu phải chạy trên **database test cô lập**, với quyền hạn phù hợp, không chạy trực tiếp trên production. API, exception, transaction và Testcontainers setup có thể phụ thuộc phiên bản driver/server/framework.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt race condition, lost update, stale read, check-then-act, write conflict, write skew và duplicate business request.
2. Viết invariant dưới dạng **điều kiện kiểm tra được sau mọi interleaving**, không chỉ dựa trên response HTTP.
3. Chỉ ra vì sao đọc rồi ghi bằng hai câu lệnh riêng không mặc nhiên nguyên tử.
4. Bảo vệ tồn kho/số dư bằng `updateOne` có điều kiện và kiểm tra `matchedCount`.
5. Sử dụng compare-and-swap (CAS) với trường `version` để phát hiện stale writes.
6. Hiểu cơ chế `@Version` của Spring Data MongoDB và exception optimistic locking.
7. Phân biệt optimistic conflict ở tầng ứng dụng với MongoDB storage/transaction `WriteConflict`.
8. Thiết kế retry giới hạn, backoff, idempotency key và cách xử lý kết quả commit chưa xác định.
9. Dùng unique index để kiểm tra tính duy nhất khi nhiều writers tranh chấp.
10. Dùng transaction cho những invariants trải qua nhiều documents/collections trong phạm vi MongoDB hỗ trợ.
11. Nhận diện write skew và lý do snapshot isolation không thay thế mọi ràng buộc nghiệp vụ.
12. Dùng `CountDownLatch`/`CyclicBarrier` để tái hiện interleaving thay vì dựa vào sleep ngẫu nhiên.
13. Tạo integration test với MongoDB test deployment phù hợp, bao gồm replica set khi kiểm tra transactions.
14. Phân biệt functional tests, deterministic concurrency tests, stress/soak tests và fault injection.
15. Kiểm tra kết quả cả trên database: tồn kho không âm, số lượt đặt chỗ không vượt quota, không có duplicate ledger và không mất cập nhật.
16. Lập kế hoạch đo contention, conflicts, retries, transaction aborts, latency và những rủi ro vận hành.

## 2. Kiểm thử cạnh tranh khác kiểm thử tuần tự ở đâu?

Kiểm thử tuần tự thường tạo dữ liệu, gọi một command và so với expected result:

~~~text
Given stock=1
When reserve 1 unit
Then stock=0 and reservation succeeds
~~~

Nó không kiểm tra được hai requests cùng thực thi:

~~~text
Given stock=1
When request A and request B both reserve 1 unit concurrently
Then exactly one request succeeds
And stock=0, never negative
And only one confirmed reservation exists
~~~

Vấn đề quan trọng là nhiều lịch thực thi (interleavings) đều có thể xảy ra.

~~~mermaid
sequenceDiagram
    participant A as Request A
    participant DB as MongoDB
    participant B as Request B
    A->>DB: Read stock=1
    B->>DB: Read stock=1
    A->>DB: Write stock=0
    B->>DB: Write stock=0
    Note over A,B: Cả A và B có thể tưởng mình mua thành công
~~~

### 2.1. Không chỉ cần kết quả cuối bằng 0

Nếu cả hai requests báo “Đặt hàng thành công” nhưng document `stock` vẫn bằng 0, invariant **số lượng hàng bán ≤ tồn kho ban đầu** đã bị vi phạm. Kiểm thử chỉ đọc trường stock sẽ bỏ sót lỗi.

### 2.2. Cần assertions ở hai tầng

- **Response-level:** bao nhiêu requests thành công, bị từ chối, retry hoặc timeout?
- **State-level:** tồn kho, reservations, ledger, thanh toán và mọi invariant cuối cùng có đúng không?

Một test đúng phải xem cả hai. “Không có exception” không có nghĩa nghiệp vụ đúng.

## 3. Khái niệm: đồng thời, song song và tính nguyên tử

**Concurrency** nghĩa có nhiều thao tác đang tiến triển và thứ tự các bước có thể xen kẽ. Chúng có thể chạy trên nhiều threads/machines hoặc bị interleave bởi scheduler.

**Parallelism** nghĩa nhiều thao tác thực sự chạy cùng lúc trên các đơn vị xử lý khác nhau.

**Atomicity** nghĩa một đơn vị thao tác được quan sát như một hiệu ứng không thể chia cắt theo phạm vi mà hệ thống bảo đảm. Với MongoDB, một câu lệnh ghi trên một document có độ nguyên tử ở document đó, nhưng hai câu lệnh riêng biệt không tự tạo một transaction.

### 3.1. Một lệnh update có điều kiện khác hai lệnh

~~~javascript
// Sai trong cạnh tranh: check ở client rồi update không kèm điều kiện.
const product = db.inventory.findOne({ _id: "SKU-1" });
if (product.available >= 1) {
  db.inventory.updateOne(
    { _id: "SKU-1" },
    { $inc: { available: -1 } }
  );
}
~~~

Hai workers có thể cùng đọc `available=1` rồi cả hai `$inc(-1)`, làm `available=-1`.

Một lệnh an toàn hơn cho invariant một document:

~~~javascript
const result = db.inventory.updateOne(
  {
    _id: "SKU-1",
    available: { $gte: 1 }
  },
  { $inc: { available: -1 } }
);

if (result.matchedCount === 1) {
  print("RESERVATION_GRANTED");
} else {
  print("OUT_OF_STOCK_OR_NOT_FOUND");
}
~~~

Điều kiện `available >= 1` và phép `$inc(-1)` được thực hiện như một cập nhật có điều kiện nguyên tử trên document. Khi một worker cập nhật xong, worker kia không còn match điều kiện nếu stock đã về 0.

### 3.2. `matchedCount` khác `modifiedCount`

Với lệnh cập nhật có điều kiện, `matchedCount=1` xác nhận có document match filter và write được thừa nhận theo semantics lệnh. `modifiedCount` có thể bằng 0 với update no-op. Nếu nghiệp vụ dựa trên điều kiện CAS và update chắc chắn thay đổi, vẫn nên định nghĩa success bằng việc **filter điều kiện được match** và response đã acknowledged, không đoán từ `modifiedCount` một cách chung chung.

### 3.3. Một document vs nhiều documents

Một thao tác có điều kiện trên `inventory(SKU-1)` không tự bảo đảm document `reservations` cũng được tạo. Nếu invariant đòi **trừ kho và tạo reservation cùng thành công hoặc cùng thất bại**, bạn cần thiết kế lưu chung trong một document, transaction, hoặc một cơ chế nghiệp vụ có reconciliation được chấp nhận.

## 4. Những loại lỗi cạnh tranh thường gặp

| Hiện tượng | Kịch bản | Dấu hiệu |
|---|---|---|
| **Lost update** | A/B đọc cùng version rồi ghi đè nguyên document | Một thay đổi biến mất |
| **Check-then-act / TOCTOU** | Kiểm tra đủ hàng rồi trừ ở lệnh khác | Stock âm hoặc bán quá số lượng |
| **Double booking** | Hai requests cùng xác nhận một chỗ | Nhiều đặt chỗ cho cùng slot |
| **Duplicate request** | Timeout rồi client gửi lại | Ghi nghiệp vụ hai lần |
| **Write conflict** | Transactions/writes tranh cập nhật dữ liệu | Một transaction phải abort/retry |
| **Write skew** | Hai transactions đọc một tập dữ liệu và ghi các documents khác nhau | Invariant liên document bị phá |
| **Stale read** | Đọc secondary lag hoặc snapshot cũ | Quyết định dựa trên trạng thái chưa mới |
| **Phantom/range anomaly** | Số records trong một phạm vi thay đổi giữa các lần đọc | Logic dựa trên count có thể sai |
| **Unique race** | Hai workers insert cùng khóa nghiệp vụ | Một operation DuplicateKey |
| **Unknown outcome** | Mất kết nối sau server apply write/commit | Client không biết đã thành công chưa |

Không đánh đồng những lỗi này. Cách bảo vệ đúng tùy invariant và độ nguyên tử cần thiết.

## 5. Bắt đầu bằng business invariants, không bằng tên framework

Trước khi viết tests, liệt kê quy tắc mà hệ thống **không bao giờ được phá** sau một thao tác đã commit:

~~~text
INV-1: inventory.available >= 0
INV-2: confirmedReservations <= initialStock + replenishments
INV-3: wallet.balanceMinor >= 0
INV-4: một (tenantId, requestId) có tối đa một kết quả nghiệp vụ
INV-5: một seatId trong một event chỉ có một active booking
INV-6: order PAID phải có payment ledger nhất quán
INV-7: revision của document không bị ghi đè bởi client cũ
~~~

### 5.1. Phạm vi của invariant

| Phạm vi | Ví dụ | Cơ chế có thể cần |
|---|---|---|
| Một field/document | `available >= 0` | Conditional atomic update |
| Identity một namespace | Email unique theo tenant | Compound unique index |
| Nhiều documents cùng collection | Không có hai active bookings cho seat | Unique index/transaction/model lại |
| Nhiều collections | Trừ kho + ghi reservation | Transaction hoặc thiết kế một document |
| Ngoài MongoDB | Charge cổng thanh toán + lưu ledger | Idempotency + outbox/reconciliation |

### 5.2. Business invariant không đồng nghĩa HTTP status

Hai requests có thể đều nhận HTTP 200 vì ứng dụng không kiểm tra `matchedCount`; database lúc đó chỉ trừ stock một lần. Trái lại, request có thể nhận timeout nhưng write đã commit. Test phải đối chiếu database state với contract response.

### 5.3. Chấp nhận kết quả nào?

Trong cạnh tranh, thường **không kỳ vọng request A luôn thắng**. Kỳ vọng đúng là một tập kết quả, ví dụ “chính xác một trong A/B thành công, request còn lại nhận OUT_OF_STOCK”, bất kể scheduling.

## 6. Phân biệt linearization point và lịch interleaving

Một thao tác nguyên tử có thể xem như có một **điểm hiệu lực** giữa lúc bắt đầu và lúc kết thúc. Với conditional `updateOne` một document, điểm kiểm tra điều kiện và áp dụng update nằm trong operation nguyên tử.

~~~text
Time →
A:  [ start ---------- update commit -------- response ]
B:      [ start ---------- failed match ------ response ]
                        ^
                 A giữ suất cuối
~~~

Với các thao tác read-then-write tách rời, không có một điểm đơn nhất bảo đảm cả “đọc thấy đủ” và “trừ đủ”. Cần gộp invariant vào một atomic predicate hoặc transaction phù hợp.

### 6.1. Test không thể dựa vào tốc độ máy

Nhiều threads chạy trên laptop mạnh chưa chắc trùng thời điểm ở điểm quan trọng. Có thể mỗi thread hoàn thành tuần tự và test xanh dù code chứa race condition.

### 6.2. Điều khiển interleaving

Dùng `CountDownLatch` hoặc `CyclicBarrier` chặn hai workers sau bước đọc, khiến cả hai sử dụng cùng snapshot cũ trước khi ghi. Đây là cách tạo một test **có khả năng tái hiện lỗi rõ ràng**, thay vì gọi `Thread.sleep(50)` và mong scheduler may mắn.

## 7. Bộ dữ liệu lab: inventory, wallet, booking và request ledger

Các ví dụ mongosh sau **chỉ sử dụng database riêng**:

~~~javascript
use mongo_concurrency_lab

db.inventory.insertMany([
  {
    _id: "SKU-A",
    available: 1,
    reserved: 0,
    version: NumberLong(0)
  },
  {
    _id: "SKU-B",
    available: 100,
    reserved: 0,
    version: NumberLong(0)
  }
])

db.wallets.insertOne({
  _id: "wallet-1",
  tenantId: "t-01",
  balanceMinor: NumberLong(100000),
  version: NumberLong(0)
})

db.bookings.createIndex(
  { tenantId: 1, eventId: 1, seatId: 1 },
  { name: "uniq_tenant_event_seat", unique: true }
)

db.requestLedger.createIndex(
  { tenantId: 1, requestId: 1 },
  { name: "uniq_tenant_request", unique: true }
)
~~~

Giả định những collections chưa có dữ liệu trùng. Chạy lại inserts có `_id` cố định sẽ gặp duplicate key; không sao chép lệnh này sang production.

### 7.1. Khóa nghiệp vụ

`_id` unique theo collection; nhưng một email/seat/request ID có thể cần unique theo nhiều fields, ví dụ `(tenantId,eventId,seatId)`. MongoDB chỉ thực thi ràng buộc như vậy nếu tạo unique index/constraint tương ứng hoặc thiết kế identity phù hợp.

### 7.2. Dữ liệu kiểm thử phải được cô lập

Không chia sẻ collection chung giữa các tests chạy song song nếu tests có thể reset/delete dữ liệu của nhau. Mỗi test nên dùng database/namespace riêng hoặc fixture IDs độc lập, cleanup có kiểm soát.

## 8. Kiểm thử anti-pattern lost update

Hai workers cùng đọc:

~~~text
Counter = 0

Worker A: read 0
Worker B: read 0
Worker A: replace counter with 1
Worker B: replace counter with 1

Final counter = 1 (đúng phải là 2 increments)
~~~

Mỗi `replaceOne` là atomic trên một document, nhưng cả chuỗi **read → compute → replace** không atomic.

### 8.1. Ví dụ mongosh không có interleaving được điều khiển

~~~javascript
const old = db.counters.findOne({ _id: "views" });
const next = old.count + 1;

db.counters.replaceOne(
  { _id: "views" },
  { _id: "views", count: next }
);
~~~

Đoạn này không tự gây race nếu chạy một luồng; nó minh họa pattern **không bảo vệ stale state**. Muốn tái hiện race, chạy hai workers với barrier sau read.

### 8.2. Nếu chỉ tăng counter

Sửa bằng một lệnh server-side:

~~~javascript
db.counters.updateOne(
  { _id: "views" },
  { $inc: { count: 1 } }
);
~~~

Hai concurrent `$inc` đều có thể được áp đúng thành count = 2 theo tính nguyên tử một document. Tuy nhiên, **gửi lại cùng một business request sau timeout** có thể làm `$inc` lần nữa; atomicity không tự cấp idempotency.

## 9. Optimistic locking là gì?

**Optimistic locking** giả định xung đột không thường xuyên, cho phép nhiều bên đọc cùng tài liệu nhưng khi ghi sẽ kiểm tra tài liệu **vẫn ở phiên bản đã đọc** hay không.

Document:

~~~javascript
{
  _id: "order-1001",
  status: "PENDING",
  version: NumberLong(4)
}
~~~

Hai editors đọc version 4. Editor A ghi với điều kiện version 4 và nâng lên 5; editor B dùng điều kiện version 4 sẽ không còn match. Thay vì âm thầm ghi đè, B nhận conflict.

~~~mermaid
sequenceDiagram
    participant A as Editor A
    participant DB as MongoDB
    participant B as Editor B
    A->>DB: find order version=4
    B->>DB: find order version=4
    A->>DB: update where version=4; set status; inc version
    DB-->>A: matchedCount=1
    B->>DB: update where version=4; set status; inc version
    DB-->>B: matchedCount=0
    Note over B: OPTIMISTIC_CONFLICT; không ghi đè thay đổi của A
~~~

### 9.1. Không phải database lock giữ suốt thời gian người dùng chỉnh form

Không có thread nào phải cầm mutex từ lúc mở trang edit đến khi bấm Save. Việc kiểm tra xảy ra **tại lúc ghi**. Điều này thích hợp với forms và updates có khoảng thời gian đọc–ghi dài.

### 9.2. Conflict là kết quả nghiệp vụ hợp lệ

Hai editors thay đổi cùng record: một người lưu thành công, người còn lại có thể nhận HTTP 409 Conflict và yêu cầu reload/merge. Không tự retry cùng payload cũ đến khi thắng, vì có thể phá ý định của editor đầu.

### 9.3. Version không thay authorization

Condition `version=4` không bảo đảm user được phép sửa order. Filter còn phải có tenant/owner/role constraints.

## 10. Compare-and-swap (CAS) bằng MongoDB updateOne

Ví dụ cập nhật order nếu version vẫn là 4:

~~~javascript
const result = db.orders.updateOne(
  {
    _id: "order-1001",
    tenantId: "t-01",
    version: NumberLong(4)
  },
  {
    $set: { status: "APPROVED" },
    $inc: { version: NumberLong(1) }
  }
);

if (result.matchedCount === 0) {
  print("CONFLICT_OR_NOT_FOUND_OR_NOT_AUTHORIZED");
}
~~~

Filter và update được thực hiện nguyên tử trên cùng document. `version` tăng nếu thao tác thành công, làm các writes từ bản cũ thất bại.

### 10.1. Kết quả `matchedCount=0` chưa đủ phân loại

Không biết chính xác:

- Document đã bị xóa?
- Tenant filter không match?
- Version đã thay đổi?
- Status/điều kiện nghiệp vụ không thỏa?

Ứng dụng có thể chọn response chung để tránh lộ sự tồn tại của record, hoặc thực hiện truy vấn có quyền sau đó để phân biệt conflict và not found theo API policy.

### 10.2. `upsert` có thể phá CAS nếu dùng sai

Không bật `upsert:true` cho một phép update version-constrained vốn chỉ nên sửa document tồn tại, trừ khi có một protocol create/insert riêng đã thiết kế rõ. Một attempt stale có thể chuyển thành insert mới, gây duplicate key hoặc dữ liệu ngoài ý muốn.

### 10.3. Version phải được tăng cùng update

Nếu cập nhật content ở một lệnh rồi tăng version ở lệnh sau, giữa hai lệnh vẫn có race. Đặt `$set` và `$inc` trong **cùng atomic update**.

## 11. CAS cho trạng thái đơn hàng

Giả sử order chỉ được chuyển:

~~~text
PENDING → APPROVED → FULFILLED
        ↘ CANCELLED
~~~

Một transition hợp lệ:

~~~javascript
const result = db.orders.updateOne(
  {
    _id: "order-1001",
    tenantId: "t-01",
    status: "PENDING",
    version: NumberLong(4)
  },
  {
    $set: {
      status: "APPROVED",
      approvedAt: new Date()
    },
    $inc: { version: NumberLong(1) }
  }
);
~~~

Kết hợp **expected status** và **expected version**:

- Status bảo vệ business state machine.
- Version chống ghi đè bất kỳ thay đổi document nào đã xảy ra sau read.

### 11.1. Chỉ version hay chỉ status?

Chỉ status có thể đủ cho một transition đơn giản nếu mọi thuộc tính khác không liên quan. Chỉ version có thể phát hiện stale writes nhưng không ngăn chuyển từ trạng thái không hợp lệ nếu code gọi sai. Với workflow quan trọng, kiểm thử cả hai quy tắc.

### 11.2. Concurrent approve vs cancel

Hai requests cùng đọc PENDING. Một thao tác APPROVED thành công, thao tác CANCELLED không còn match status/version; không thể vừa APPROVED vừa CANCELLED nếu cả hai dùng conditional update đúng.

### 11.3. Retry command khác retry decision

Không tự đọc phiên bản mới rồi retry CANCELLED nếu workflow business cấm cancel sau approve. Retry phải **đánh giá lại điều kiện nghiệp vụ**, không đơn thuần lặp thao tác đến khi database chấp nhận.

## 12. Conditional update cho số dư và tồn kho

Ví dụ ví có 100.000 đồng, hai requests mỗi request muốn trừ 80.000 đồng:

~~~javascript
const amount = NumberLong(80000);
const result = db.wallets.updateOne(
  {
    _id: "wallet-1",
    tenantId: "t-01",
    balanceMinor: { $gte: amount }
  },
  {
    $inc: { balanceMinor: NumberLong(-80000) }
  }
);
~~~

Với dữ liệu ban đầu 100.000, **tối đa một** trong hai concurrent conditional updates có thể match. Sau thành công, balance = 20.000, không âm.

### 12.1. Vì sao không cần đọc trước?

Điều kiện đủ tiền đã nằm trong filter của write, nên không có khoảng trống giữa “check” và “act”. Có thể đọc trước để hiển thị UI, nhưng quyết định cuối phải dựa vào atomic update.

### 12.2. Monetary types

Ví dụ dùng integer minor units; nếu lưu money bằng `double`, phép so sánh và phép trừ có thể gặp sai số floating-point. Dùng integer minor units hoặc Decimal128 theo schema phù hợp, xác định giới hạn số, tỷ giá và rounding policy.

### 12.3. Không idempotent khi resend

Hai requests **khác nhau** tranh 80.000: tối đa một thành công. Nhưng nếu request đầu đã trừ 80.000, client không nhận response và gửi lại khi số dư được nạp thêm, cùng business request có thể bị trừ lần nữa. Conditional update không thay idempotency key.

## 13. Spring Data MongoDB `@Version`

Spring Data MongoDB có annotation `@Version` để quản lý optimistic locking cho entity được lưu qua mapping operations phù hợp:

~~~java
package example.concurrency;

import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.Version;
import org.springframework.data.mongodb.core.mapping.Document;

@Document("wallets")
public class Wallet {
    @Id
    private String id;
    private String tenantId;
    private long balanceMinor;

    @Version
    private Long version;

    public Wallet() {}

    public Wallet(String id, String tenantId, long balanceMinor) {
        this.id = id;
        this.tenantId = tenantId;
        this.balanceMinor = balanceMinor;
    }

    public String getId() { return id; }
    public String getTenantId() { return tenantId; }
    public long getBalanceMinor() { return balanceMinor; }
    public Long getVersion() { return version; }

    public void setBalanceMinor(long amount) {
        this.balanceMinor = amount;
    }
}
~~~

### 13.1. Spring Data làm gì?

Với những thao tác save/versioned update được Spring Data hỗ trợ, framework đưa **current version** vào điều kiện ghi và cập nhật version khi thành công. Nếu không có document match version cũ, framework có thể ném `OptimisticLockingFailureException` thay vì âm thầm ghi đè.

### 13.2. Không hardcode initial version

Thời điểm và giá trị version ban đầu cho entity mới có thể phụ thuộc kiểu primitive/wrapper và Spring Data version. Trong tests, nên **save entity rồi đọc lại version thực tế**, không giả định mọi trường hợp tự bắt đầu bằng 0.

### 13.3. Write concern phải acknowledged

Để Spring Data phát hiện một versioned update không match, kết quả ghi cần được server thừa nhận. Dùng acknowledged write concern phù hợp; write concern unacknowledged có thể khiến optimistic locking không xác định được conflict.

### 13.4. Annotation không bao phủ mọi raw write

Nếu một module khác dùng MongoDB Java Driver trực tiếp với `updateOne({_id})` mà không kiểm tra/increment version, nó có thể **bỏ qua cơ chế `@Version`**. Cần quy ước tất cả đường cập nhật cùng một entity phải tuân thủ version protocol hoặc atomic business predicate tương đương.

## 14. Kiểm thử stale entity với Spring Data MongoTemplate

Một test đơn giản, **không cần hai threads**, đủ chứng minh stale version bị từ chối:

~~~java
import static org.junit.jupiter.api.Assertions.*;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.dao.OptimisticLockingFailureException;
import org.springframework.data.mongodb.core.MongoTemplate;

class WalletOptimisticLockIntegrationTest {
    @Autowired
    MongoTemplate mongoTemplate;

    @Test
    void staleEntityMustNotOverwriteFreshEntity() {
        Wallet created = mongoTemplate.save(
            new Wallet("wallet-stale-test", "t-01", 100000L)
        );

        Wallet editorA = mongoTemplate.findById(
            created.getId(), Wallet.class
        );
        Wallet editorB = mongoTemplate.findById(
            created.getId(), Wallet.class
        );

        assertNotNull(editorA);
        assertNotNull(editorB);
        assertEquals(editorA.getVersion(), editorB.getVersion());

        editorA.setBalanceMinor(90000L);
        mongoTemplate.save(editorA);

        editorB.setBalanceMinor(20000L);
        assertThrows(
            OptimisticLockingFailureException.class,
            () -> mongoTemplate.save(editorB)
        );

        Wallet persisted = mongoTemplate.findById(
            created.getId(), Wallet.class
        );
        assertNotNull(persisted);
        assertEquals(90000L, persisted.getBalanceMinor());
    }
}
~~~

### 14.1. Đây là skeleton tích hợp vào test context

Ví dụ giả định `MongoTemplate` được inject bởi Spring Test configuration, test chạy trên **database cô lập** và versioned entity có mapping hợp lệ. Cần cleanup/unique IDs hoặc database riêng giữa tests để tránh dữ liệu tồn từ lượt trước.

### 14.2. Tại sao test tuần tự vẫn có giá trị?

Nó xây hai **ảnh chụp đối tượng riêng** cùng version trước khi ghi. Sau khi A save, B là stale. Không cần phụ thuộc thread scheduling để xác nhận semantics của `@Version`.

### 14.3. Đây chưa phải stress test

Test stale save không chứng minh behavior khi hàng nghìn requests tranh nhau dưới load, network partitions hoặc transaction retries. Cần tầng concurrency/fault tests bổ sung.

## 15. Spring Data repository và exception mapping

Repository:

~~~java
import org.springframework.data.mongodb.repository.MongoRepository;

public interface WalletRepository
        extends MongoRepository<Wallet, String> {
}
~~~

Một update từ form:

~~~java
public Wallet saveUserEdit(Wallet edited) {
    return walletRepository.save(edited);
}
~~~

Khi version cũ, Spring Data có thể ném `OptimisticLockingFailureException`. Service/controller nên chuyển nó thành **conflict có ý nghĩa**, chẳng hạn HTTP 409, thay vì trả HTTP 500 chung.

### 15.1. Không lặng lẽ retry stale form

Nếu user A sửa địa chỉ giao hàng và user B sửa nội dung ghi chú từ cùng version, ứng dụng có thể cung cấp UI merge hoặc reload. Tự retry toàn bộ entity của B trên version mới có thể ghi đè thay đổi A.

### 15.2. Retry command trong batch jobs

Nếu operation là “tăng counter 1 đơn vị” và business cho phép, job có thể re-read/recompute và retry CAS với số lần giới hạn. Nhưng phải khác với thao tác “ghi toàn bộ giá trị người dùng đã chỉnh từ form cũ”.

### 15.3. `@Version` không thay uniqueness

Version của từng document không ngăn **hai documents khác nhau** có cùng email/seat. Cần unique index cho ràng buộc identity liên documents.

## 16. Spring Data `@Version` và raw updates

Một ứng dụng đôi khi trộn:

~~~java
// Đường A: Spring Data save có @Version.
walletRepository.save(wallet);

// Đường B: Raw MongoDB driver update chỉ theo _id.
rawWalletCollection.updateOne(
    Filters.eq("_id", walletId),
    Updates.set("balanceMinor", 12345L)
);
~~~

Đường B **không tự được annotation của class Java** bảo vệ vì database chỉ thấy filter/update được gửi. Một bên có thể sửa balance mà không tăng version, khiến các editors không biết document đã đổi.

### 16.1. Quy tắc nhất quán trong codebase

Đối với cùng aggregate:

- Sử dụng các Spring Data operations có hỗ trợ `@Version` đúng cách; hoặc
- Dùng atomic conditional updates kiểm tra/increment version rõ ràng; hoặc
- Chọn một mô hình concurrency khác và kiểm thử toàn bộ write paths.

Đừng dựa vào việc “entity có @Version” để chứng minh những writes qua pipelines/scripts/other services đều tôn trọng protocol.

### 16.2. Test hỗn hợp

Tạo entity qua repository, sửa bằng raw update không tăng version, rồi xem repository stale save có ghi đè không. Nếu test phơi bày lỗ hổng, sửa raw update path. Đây là một loại **compatibility/integration test** quan trọng khi nhiều services cùng ghi.

## 17. Optimistic conflict khác `WriteConflict` của MongoDB

Hai thông báo có thể trông giống nhau nhưng khác nguồn gốc:

| Loại | Ai phát hiện | Ví dụ | Cách xử lý |
|---|---|---|---|
| **Application optimistic conflict** | Version predicate/Spring Data | `matchedCount=0`, `OptimisticLockingFailureException` | Trả conflict, reload/merge/recompute theo business |
| **MongoDB WriteConflict** | Storage/transaction concurrency control | WriteConflict code 112 trong transaction context | Có thể retry transaction nếu transient và được driver hỗ trợ |
| **DuplicateKey** | Unique index | E11000/code 11000 | Xác minh identity/request, không retry mù |
| **Network/timeout** | Client/transport/server selection | Không nhận được reply | Outcome có thể chưa xác định; reconcile/idempotency |

### 17.1. Không retry mọi exception

`OptimisticLockingFailureException` không giống transient transaction error. Tự retry stale form có thể gây lost update về mặt nghiệp vụ. DuplicateKey thường là một kết quả cạnh tranh hợp lệ của uniqueness constraint.

### 17.2. Có thể có nhiều cơ chế cùng lúc

Một transaction chứa optimistic version update có thể abort do write conflict. Một request cũng có thể gặp duplicate key ở ledger và network timeout khi commit. Error handling phải phân biệt **storage state** và **business outcome**.

## 18. Unique index: ràng buộc phải ở database

Hai users cùng chọn một seat duy nhất. Pattern nguy hiểm:

~~~javascript
const existing = db.bookings.findOne({
  tenantId: "t-01",
  eventId: "EV-1",
  seatId: "A-01"
});

if (!existing) {
  db.bookings.insertOne({
    tenantId: "t-01",
    eventId: "EV-1",
    seatId: "A-01",
    state: "ACTIVE"
  });
}
~~~

Hai workers có thể cùng thấy không có booking rồi insert hai documents khác `_id`.

Unique index:

~~~javascript
db.bookings.createIndex(
  {
    tenantId: 1,
    eventId: 1,
    seatId: 1
  },
  { unique: true, name: "uniq_tenant_event_seat" }
);
~~~

Khi cả hai cùng insert khóa giống nhau, index bảo đảm không thể có hai documents hợp lệ với cùng key **theo đúng semantics của index**; một writer có thể gặp E11000.

### 18.1. Unique constraint đúng nghĩa business

Nếu một seat được phép có nhiều lịch sử booking CANCELLED nhưng tối đa một ACTIVE, unique index đơn giản trên tenant/event/seat có thể quá chặt. Có thể dùng **partial unique index** nếu phù hợp:

~~~javascript
db.bookings.createIndex(
  { tenantId: 1, eventId: 1, seatId: 1 },
  {
    unique: true,
    name: "uniq_active_seat",
    partialFilterExpression: { state: "ACTIVE" }
  }
);
~~~

Điều kiện index cần khớp chính xác business semantics, kể cả trạng thái HOLD/PENDING/EXPIRED nếu các trạng thái này cũng giữ chỗ.

### 18.2. Null, collation và sharding

Unique indexes có quy tắc về null/missing keys, collation và giới hạn trên sharded collections. Một unique index theo email case-insensitive cần collation/normalization phù hợp. Trên sharded cluster, tính duy nhất toàn cluster còn phụ thuộc tương thích với shard key/index constraints. Không assume chỉ thêm annotation `@Indexed(unique=true)` là mọi deployment thực thi đúng.

### 18.3. Không chỉ test có index annotation

Test phải xác nhận **index đã được tạo thật trên MongoDB test instance**. Spring Data auto-index creation có thể tắt theo cấu hình/phiên bản; metadata Java không phải bằng chứng index tồn tại.

## 19. Xử lý DuplicateKey như kết quả cạnh tranh

Java driver có thể báo duplicate key dưới dạng `MongoWriteException` với code 11000:

~~~java
import com.mongodb.MongoWriteException;
import com.mongodb.client.MongoCollection;
import org.bson.Document;

public boolean tryBookSeat(
        MongoCollection<Document> bookings,
        String tenantId,
        String eventId,
        String seatId,
        String bookingId
) {
    try {
        bookings.insertOne(
            new Document("_id", bookingId)
                .append("tenantId", tenantId)
                .append("eventId", eventId)
                .append("seatId", seatId)
                .append("state", "ACTIVE")
        );
        return true;
    } catch (MongoWriteException error) {
        if (error.getError().getCode() == 11000) {
            return false;
        }
        throw error;
    }
}
~~~

### 19.1. “Đã có booking” không luôn là HTTP 409

Nếu client **gửi lại cùng request ID**, duplicate key có thể có nghĩa cùng giao dịch đã thành công; cần đọc ledger để trả lại kết quả cũ. Nếu là **khách khác tranh cùng seat**, trả “seat unavailable”/409 có thể phù hợp. Không gộp hai tình huống chỉ vì cùng error code.

### 19.2. Không retry insert bằng ID mới

Nếu unique seat conflict, tạo booking mới với một `_id` ngẫu nhiên khác **không làm seat trống**. Retry như vậy có thể tiếp tục gặp lỗi hoặc tạo duplicate nếu index sai.

## 20. Unique index và optimistic locking bổ sung nhau

| Nhu cầu | Bảo vệ thích hợp |
|---|---|
| Không hai records cùng seat ACTIVE | Unique/partial unique index |
| Không ghi đè update stale của một booking | Version CAS/`@Version` |
| Một request không tạo hai bookings khi retry | Idempotency key/ledger unique |
| Booking và payment record cùng commit | Transaction trong MongoDB + external reconciliation |
| Seat không quá số lượng quota tổng | Conditional quota document hoặc transaction + guard |

Một application có thể cần **cả bốn**: unique constraint, optimistic locking, transaction và idempotency. Không có cơ chế nào tự động thay thế toàn bộ cơ chế khác.

## 21. Test hạ tầng: integration database phải thật

Mocks có thể giúp unit test service branch, nhưng một mock `MongoCollection` không chứng minh server enforce atomicity, unique index, transactions hoặc wire errors.

Các mức kiểm thử:

| Tầng | Mục đích | Giới hạn |
|---|---|---|
| Unit test thuần Java | Business rule/DTO/result mapping | Không kiểm tra MongoDB concurrency semantics |
| Integration test MongoDB thật | Atomic filters, unique indexes, mapping, `@Version` | Thường tải nhỏ |
| Deterministic concurrency test | Tái hiện một interleaving cụ thể | Không bao phủ mọi lịch thực thi |
| Stress/soak test | Contention, p95/p99, resource leaks | Có thể không tái hiện race hiếm |
| Fault injection | Network timeout, rollback, commit uncertainty | Yêu cầu hạ tầng và quyền đặc biệt |

### 21.1. Standalone vs replica set

Single-document atomic updates và unique index có thể được kiểm thử trên MongoDB lab đơn giản. **Multi-document transactions** cần topology hỗ trợ như replica set/sharded cluster và cấu hình phù hợp. Một standalone mongod thông thường không phải môi trường đầy đủ để test transactions.

### 21.2. Testcontainers

Có thể dùng Testcontainers để cấp MongoDB test instance hoặc replica set theo module/version tương ứng. Testcontainers đã thay đổi package/API qua các major versions, nên chọn integration phù hợp dependencies đang dùng. Không hardcode một class/method chỉ vì nó xuất hiện trong một đoạn code cũ mà không xác minh.

### 21.3. Test isolation

Mỗi test nên có một namespace/DB riêng hoặc IDs duy nhất và cleanup an toàn. Một stress test chạy song song với migration/test khác trên cùng database có thể tạo flaky failures và phá kết quả.

## 22. Cấu hình Java test dependencies

Với Gradle (minh họa, thay các placeholders bằng versions đã pin):

~~~kotlin
dependencies {
    testImplementation("org.junit.jupiter:junit-jupiter:REPLACE_WITH_PINNED_VERSION")
    testImplementation("org.mongodb:mongodb-driver-sync:REPLACE_WITH_PINNED_VERSION")

    // Khi dùng Spring Data test:
    testImplementation("org.springframework.boot:spring-boot-starter-test")

    // Nếu dùng Testcontainers, thêm module và integration phù hợp
    // Testcontainers major version của dự án.
}

tasks.test {
    useJUnitPlatform()
}
~~~

Đây là **mẫu khai báo dependency**, không phải build file có thể copy chạy ngay khi chưa thay placeholder/cấu hình dependency management. Không cần thêm mọi module nếu dự án đã có MongoDB driver qua starter Spring Data.

### 22.1. Tách test URL khỏi production

Các ví dụ dưới đây dùng `MONGODB_TEST_URI`. Biến này phải chỉ tới cluster **dành cho tests** với credentials giới hạn. Không fallback sang `MONGODB_URI` của production nếu test URI thiếu.

### 22.2. Timeouts có chủ đích

Test concurrency không được treo vô hạn khi một worker lỗi trước khi mở barrier. Dùng `await(timeout)`, `Future.get(timeout)`, đóng thread pools và client trong `finally`.

### 22.3. Không cần sleep để “làm concurrency”

`Thread.sleep` chỉ trì hoãn tương đối, không bảo đảm cả hai readers đã đọc snapshot cũ. Dùng barriers/latches khi cần tái hiện interleaving; dùng load generator riêng cho stress.

## 23. Test nguyên tử: hai workers tranh một sản phẩm

Ví dụ JUnit 5 dưới đây tạo database tên ngẫu nhiên trên **test deployment**, insert stock = 1, cho hai threads cùng bắt đầu lệnh update có điều kiện rồi xác nhận:

- Chính xác **một** worker thành công.
- `available` cuối bằng 0.
- Không có stock âm.

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.util.UUID;
import java.util.concurrent.Callable;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.MongoDatabase;
import com.mongodb.client.result.UpdateResult;
import com.mongodb.client.model.Filters;
import com.mongodb.client.model.Updates;
import org.bson.Document;
import org.junit.jupiter.api.Test;

class StockConcurrencyTest {

    @Test
    void exactlyOneOfTwoRequestsMayReserveLastUnit()
            throws Exception {

        String uri = System.getenv("MONGODB_TEST_URI");
        assertNotNull(uri, "MONGODB_TEST_URI must point to isolated test DB");

        try (MongoClient client = MongoClients.create(uri)) {
            String dbName = "concurrency_lab_" +
                UUID.randomUUID().toString().replace("-", "");

            MongoDatabase db = client.getDatabase(dbName);
            MongoCollection<Document> inventory =
                db.getCollection("inventory");

            ExecutorService pool = Executors.newFixedThreadPool(2);
            CountDownLatch ready = new CountDownLatch(2);
            CountDownLatch start = new CountDownLatch(1);

            try {
                inventory.insertOne(
                    new Document("_id", "SKU-A")
                        .append("available", 1)
                );

                Callable<Boolean> reserve = () -> {
                    ready.countDown();
                    if (!start.await(5, TimeUnit.SECONDS)) {
                        throw new IllegalStateException("Start gate timeout");
                    }

                    UpdateResult result = inventory.updateOne(
                        Filters.and(
                            Filters.eq("_id", "SKU-A"),
                            Filters.gte("available", 1)
                        ),
                        Updates.inc("available", -1)
                    );
                    return result.getMatchedCount() == 1;
                };

                Future<Boolean> a = pool.submit(reserve);
                Future<Boolean> b = pool.submit(reserve);

                assertTrue(ready.await(5, TimeUnit.SECONDS));
                start.countDown();

                int wins =
                    (a.get(10, TimeUnit.SECONDS) ? 1 : 0) +
                    (b.get(10, TimeUnit.SECONDS) ? 1 : 0);

                Document finalDoc = inventory.find(
                    Filters.eq("_id", "SKU-A")
                ).first();

                assertNotNull(finalDoc);
                assertEquals(1, wins);
                assertEquals(0, finalDoc.getInteger("available"));
            } finally {
                start.countDown();
                pool.shutdownNow();
                db.drop(); // Chỉ DB ngẫu nhiên đã tạo cho test này.
            }
        }
    }
}
~~~

### 23.1. Điều quan trọng ở `Filters.gte`

Nếu bỏ điều kiện này và chỉ dùng `Filters.eq("_id","SKU-A")`, cả hai workers có thể cùng `$inc(-1)` và kết quả `available=-1`.

### 23.2. Latch có bảo đảm hai updates cùng một nanosecond?

Không. `start` cho hai threads đi tiếp gần nhau, tăng cơ hội tranh chấp, nhưng scheduler vẫn có thể tuần tự hóa. Dù vậy **invariant chính xác một thành công** được bảo vệ bởi atomic condition trong mọi thứ tự thực thi thông thường, không phụ thuộc hai threads có cùng lúc hay không.

### 23.3. Test này chưa kiểm tra reservation document

Nó chứng minh invariant stock cho một document; chưa kiểm tra giao dịch liên collection. Nếu production còn tạo `reservations`, cần test transaction hoặc cơ chế reconciliation tương ứng.

## 24. Test lost update có kiểm soát bằng CyclicBarrier

Để chứng minh pattern read-then-replace không an toàn, cần **cả hai workers đọc giá trị cũ trước khi một trong hai ghi**.

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.util.concurrent.*;

import com.mongodb.client.MongoCollection;
import com.mongodb.client.model.Filters;
import org.bson.Document;

// Giả sử "counter" thuộc database test cô lập;
// client và cleanup do test fixture quản lý.
void demonstratesLostUpdate(
        MongoCollection<Document> counter
) throws Exception {
    counter.insertOne(
        new Document("_id", "hits").append("count", 0)
    );

    CyclicBarrier bothHaveRead = new CyclicBarrier(2);
    ExecutorService pool = Executors.newFixedThreadPool(2);

    Callable<Void> wrongIncrement = () -> {
        Document snapshot = counter.find(
            Filters.eq("_id", "hits")
        ).first();

        assertNotNull(snapshot);
        int next = snapshot.getInteger("count") + 1;

        // Cả A và B chắc chắn đã đọc trước khi replace.
        bothHaveRead.await(5, TimeUnit.SECONDS);

        counter.replaceOne(
            Filters.eq("_id", "hits"),
            new Document("_id", "hits").append("count", next)
        );
        return null;
    };

    try {
        Future<Void> a = pool.submit(wrongIncrement);
        Future<Void> b = pool.submit(wrongIncrement);
        a.get(10, TimeUnit.SECONDS);
        b.get(10, TimeUnit.SECONDS);

        Document finalDoc = counter.find(
            Filters.eq("_id", "hits")
        ).first();
        assertNotNull(finalDoc);
        assertEquals(1, finalDoc.getInteger("count"));
    } finally {
        pool.shutdownNow();
    }
}
~~~

### 24.1. Test này cố ý chứng minh bug

Nó cho thấy **hai increments logic chỉ tạo một increment persisted**, không phải code được phép dùng production. Sau khi sửa bằng atomic `$inc` hoặc CAS, expected result phải đổi thành 2.

### 24.2. Vì sao barrier đặt sau read?

Nếu barrier đặt trước read, A có thể đọc và ghi xong rồi B mới đọc. Test có thể xanh một cách tình cờ vì cả hai increments thành công tuần tự. Barrier **sau read** buộc cả hai có snapshot cũ.

### 24.3. Timeout ngăn test treo

`CyclicBarrier.await(timeout)` sẽ thất bại nếu một thread không tới barrier. Test cần báo lỗi rõ và cleanup thread pool thay vì chạy mãi.

## 25. Test CAS: một winner, một conflict

Với document:

~~~javascript
{ _id: "counter", count: 0, version: NumberLong(0) }
~~~

Hai workers đọc cùng `version=0`, đồng bộ tại barrier rồi cùng gửi:

~~~javascript
db.counters.updateOne(
  { _id: "counter", version: NumberLong(0) },
  {
    $inc: {
      count: 1,
      version: NumberLong(1)
    }
  }
);
~~~

Kỳ vọng:

~~~text
Worker A matchedCount=1, B matchedCount=0
hoặc:
Worker A matchedCount=0, B matchedCount=1

Final count=1, version=1
~~~

Đây là **expected optimistic conflict**: có đúng một change được chấp nhận từ version 0. Muốn cả hai **business increments hợp lệ** cuối cùng được áp, worker thua phải đọc lại version/current state, tính lại và thử lần tiếp theo.

### 25.1. Test các điều kiện cần

1. Không có update nào thành công với version đã stale.
2. Version tăng đúng một lần sau mỗi accepted change.
3. Không có lost update do ghi đè full document.
4. Nếu có retry, final state phản ánh số operations được chấp nhận, không phải chỉ tổng số attempts.

### 25.2. Không tự động biến conflict thành success

`matchedCount=0` không có nghĩa “update đã thành công trước đó”. Nó có thể là một writer khác đã sửa record. Với request có identity/idempotency key, cần tra ledger hoặc xác minh operation cụ thể.

## 26. Retry CAS có giới hạn

Với một operation **được phép tính lại trên trạng thái mới**, có thể dùng vòng lặp bounded:

~~~java
import com.mongodb.client.MongoCollection;
import com.mongodb.client.model.Filters;
import com.mongodb.client.model.Updates;
import com.mongodb.client.result.UpdateResult;
import org.bson.Document;

public boolean incrementWithCas(
        MongoCollection<Document> counters,
        String id,
        int maxAttempts
) {
    if (maxAttempts < 1) {
        throw new IllegalArgumentException("maxAttempts");
    }

    for (int attempt = 1; attempt <= maxAttempts; attempt++) {
        Document current = counters.find(
            Filters.eq("_id", id)
        ).first();
        if (current == null) {
            return false;
        }

        Long version = current.getLong("version");
        if (version == null) {
            throw new IllegalStateException("version required");
        }

        UpdateResult result = counters.updateOne(
            Filters.and(
                Filters.eq("_id", id),
                Filters.eq("version", version)
            ),
            Updates.combine(
                Updates.inc("count", 1),
                Updates.inc("version", 1L)
            )
        );

        if (result.getMatchedCount() == 1) {
            return true;
        }
        // Conflict: đọc lại trên vòng lặp tiếp theo.
        // Production: thêm bounded backoff/jitter/deadline.
    }
    return false;
}
~~~

### 26.1. Vì sao không retry vô hạn?

Khi nhiều workers cùng tranh một document, retry ngay lập tức liên tục có thể gây contention storm. Dùng giới hạn attempts, backoff/jitter, deadline và observability; trả lỗi phù hợp khi hết budget.

### 26.2. Quan trọng: loại operation

Code này cho “tăng counter 1” khi mỗi **call độc lập** được phép tăng. Với một request có thể gửi lại sau network timeout, cần **idempotency key** nếu muốn exactly-once business effect; vòng CAS không tự đảm bảo điều đó.

### 26.3. Đọc lại không luôn hợp lệ

Nếu hai users cùng chỉnh form với intent khác nhau, không thể tự recompute bằng cách lấy các fields cũ rồi save lại. Phải chọn merge policy hoặc trả conflict cho người dùng.

## 27. State machine và ràng buộc nghiệp vụ

Một order có transitions hợp lệ:

~~~mermaid
stateDiagram-v2
    [*] --> PENDING
    PENDING --> APPROVED
    PENDING --> CANCELLED
    APPROVED --> FULFILLED
    APPROVED --> CANCELLED: nếu policy cho phép
    FULFILLED --> [*]
    CANCELLED --> [*]
~~~

Test cạnh tranh nên xem:

- APPROVE vs CANCEL ở cùng version.
- APPROVE gửi hai lần cùng request ID.
- FULFILL vs CANCEL ở trạng thái APPROVED.
- Update notes đồng thời với transition.
- Retry khi response bị mất.

### 27.1. Atomic predicate cho transition

~~~javascript
db.orders.updateOne(
  {
    _id: "order-1",
    tenantId: "t-01",
    status: "PENDING"
  },
  {
    $set: { status: "APPROVED" },
    $inc: { version: NumberLong(1) }
  }
);
~~~

Chỉ một competing transition có thể chuyển PENDING sang trạng thái khác nếu **mọi write paths** đều kiểm tra expected status đúng.

### 27.2. Kiểm thử giá trị âm/đầu vào xấu

Nếu API cho `quantity=-1`, điều kiện `available >= quantity` có thể match và `$inc(-quantity)` làm tăng stock trái ý muốn. Business validation phải kiểm tra `quantity > 0`, giới hạn số lượng và kiểu dữ liệu trước khi gửi MongoDB command.

### 27.3. Kiểm thử boundary

Với stock 0, 1, N và request quantities 0, 1, N, N+1; test concurrent demands sao cho tổng có thể vượt quota. Dữ liệu boundary thường phơi bày lỗi mà random test trung bình không bắt được.

## 28. Transaction khi một business operation chạm nhiều documents

Giả sử một reservation cần:

1. Giảm `inventory.available`.
2. Tạo `reservations` record.
3. Lưu `requestLedger` để chống gửi lại.

Nếu các steps chạy riêng:

~~~text
Update inventory succeeded
Process crashed
Reservation document was not inserted
~~~

Stock đã giảm nhưng không có reservation tương ứng. Một **MongoDB multi-document transaction** có thể đặt các changes trong cùng một commit khi deployment hỗ trợ.

~~~mermaid
flowchart TD
    Request["Reserve request tenant + requestId"] --> Tx["Start MongoDB transaction"]
    Tx --> Ledger["Insert unique request ledger"]
    Ledger --> Stock["Atomic conditional inventory update"]
    Stock --> Decision{"Stock matched?"}
    Decision -->|"Không"| Abort["Abort transaction; reject"]
    Decision -->|"Có"| Reservation["Insert reservation record"]
    Reservation --> Commit["Commit transaction"]
    Commit --> Return["Return committed result"]
~~~

### 28.1. Transaction không tự cho phép stock âm

Ngay trong transaction, nếu code đọc stock rồi trừ mà không có predicate bảo vệ, bạn vẫn cần hiểu concurrency interactions. MongoDB có write conflicts với overlapping writes, nhưng thiết kế đúng vẫn nên dùng **conditional update bảo vệ invariant** và xử lý transaction retries.

### 28.2. Không đặt side effect bên ngoài vào transaction callback

Gọi payment gateway, gửi email hoặc publish Kafka trực tiếp trong callback có thể tạo side effect lặp nếu transaction body được retry. External systems không tự rollback khi MongoDB transaction abort. Dùng transactional outbox/idempotent consumers hoặc orchestration/reconciliation phù hợp.

## 29. Java Driver: transaction skeleton

Ví dụ cho replica set/sharded topology hỗ trợ transactions, collections đã tạo và quyền phù hợp:

~~~java
import com.mongodb.ReadConcern;
import com.mongodb.WriteConcern;
import com.mongodb.TransactionOptions;
import com.mongodb.client.ClientSession;
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.model.Filters;
import com.mongodb.client.model.Updates;
import org.bson.Document;

import static com.mongodb.client.model.Filters.*;

public String reserveInTransaction(
        MongoClient client,
        MongoCollection<Document> inventory,
        MongoCollection<Document> reservations,
        MongoCollection<Document> requestLedger,
        String tenantId,
        String requestId,
        String sku
) {
    TransactionOptions txOptions = TransactionOptions.builder()
        .readConcern(ReadConcern.SNAPSHOT)
        .writeConcern(WriteConcern.MAJORITY)
        .build();

    try (ClientSession session = client.startSession()) {
        return session.withTransaction(() -> {
            requestLedger.insertOne(
                session,
                new Document("tenantId", tenantId)
                    .append("requestId", requestId)
                    .append("state", "COMMITTED")
                    .append("sku", sku)
            );

            long matched = inventory.updateOne(
                session,
                and(eq("_id", sku),
                    gte("available", 1)),
                Updates.inc("available", -1)
            ).getMatchedCount();

            if (matched != 1) {
                throw new IllegalStateException("OUT_OF_STOCK");
            }

            reservations.insertOne(
                session,
                new Document("tenantId", tenantId)
                    .append("requestId", requestId)
                    .append("sku", sku)
                    .append("state", "CONFIRMED")
            );

            return "CONFIRMED";
        }, txOptions);
    }
}
~~~

### 29.1. Đây là skeleton, không phải checkout production hoàn chỉnh

Cần tạo unique index trên `(tenantId,requestId)`, định nghĩa quantity, xác minh tenant/product ownership, xử lý duplicate idempotency ledger, normalize errors, kiểm soát retry/deadlines và chỉ trả success sau commit xác nhận. Trong ví dụ, `state:"COMMITTED"` được ghi **trong transaction**, nên không thể được quan sát như một transaction đã commit nếu toàn transaction abort.

### 29.2. `withTransaction` có retry behavior

Driver convenience API có thể retry transaction body hoặc commit theo error labels phù hợp. Callback phải không làm side effects ngoài MongoDB và phải chịu được việc được gọi lại theo semantics của driver. Kiểm tra driver/version và error-handling contract cụ thể.

### 29.3. Không bắt mọi exception rồi tiếp tục transaction

Nếu stock không đủ, cần abort toàn bộ business operation; ném domain error ra khỏi callback giúp transaction không được commit khi chưa đủ hàng. Nếu bạn catch lỗi rồi vẫn trả result thành công, có thể commit ledger mà không có reservation.

### 29.4. Unique index trên ledger

~~~javascript
db.requestLedger.createIndex(
  { tenantId: 1, requestId: 1 },
  { unique: true, name: "uniq_tenant_request" }
);
~~~

Nếu cùng request ID chạy hai lần, một attempt có thể nhận duplicate key. Caller phải **reconcile kết quả cũ** nếu payload tương ứng, không tự tuyên bố failure hay chạy lại stock deduction với request ID mới.

## 30. Transaction isolation không thay business invariant

MongoDB transactions cung cấp cơ chế snapshot isolation/atomic commit trong phạm vi hỗ trợ. Nhưng ứng dụng không nên suy ra “có transaction là mọi ràng buộc liên documents tự đúng”.

### 30.1. Ví dụ write skew

Hai bác sĩ A và B trực ca, invariant là **phải còn ít nhất một bác sĩ trực**. Mỗi doctor là một document:

~~~text
doctors:
{ _id: "A", onCall: true }
{ _id: "B", onCall: true }
~~~

Hai transactions đồng thời:

~~~text
Tx1 đọc A/B đều trực, quyết định cho A nghỉ, ghi A.onCall=false
Tx2 đọc A/B đều trực, quyết định cho B nghỉ, ghi B.onCall=false
~~~

Vì mỗi transaction có thể ghi vào **document khác nhau**, nếu không có xung đột ghi chung hoặc guard khác, snapshot isolation có thể cho phép cả hai quyết định dựa trên cùng snapshot và sau đó invariant không ai trực bị vi phạm. Đây là **write skew** về mặt lý thuyết/isolation; khả năng xảy ra và xử lý cụ thể phải được kiểm chứng trên MongoDB topology/version đang dùng.

### 30.2. Bảo vệ guard chung

Các giải pháp có thể:

1. Model tất cả người trực trong **một document** và cập nhật có điều kiện `countOnCall > 1`.
2. Dùng **guard/sentinel document** được cả hai transactions cập nhật để buộc xung đột nếu cùng thay đổi ca.
3. Dùng một protocol serialization ở tầng ứng dụng/queue có bảo đảm phù hợp.

Điều quan trọng là thiết kế một **điểm tranh chấp chung** để mọi transitions ảnh hưởng invariant đi qua, không chỉ đọc cùng một count rồi sửa documents riêng.

### 30.3. Test write skew

Cho hai transaction workers đọc cùng snapshot, đồng bộ sau read rồi thực hiện writes vào hai docs khác nhau. Assert invariant sau khi cả hai kết thúc; nếu nó bị phá, thêm guard và chạy lại. Không đánh giá chỉ dựa trên “mỗi transaction commit thành công”.

## 31. MongoDB WriteConflict và transaction retries

Khi hai transactions tranh ghi cùng document hoặc resource, MongoDB có thể abort một transaction với lỗi write conflict. Error có thể mang label `TransientTransactionError`, báo rằng retry **toàn bộ transaction body** theo driver policy là phù hợp trong những trường hợp được hỗ trợ.

### 31.1. Retry từ đầu không phải retry mỗi câu lệnh

Nếu transaction đã đọc tồn kho, tạo ledger và update trạng thái, retry chỉ dòng update cuối với snapshot cũ có thể sai. Với transient transaction failure, thường phải **khởi động lại transaction** để có snapshot và quyết định mới.

### 31.2. UnknownTransactionCommitResult

Nếu connection mất sau khi gửi commit, client có thể không biết server đã commit chưa. Trường hợp có error label `UnknownTransactionCommitResult` cần xử lý **commit retry theo driver semantics hoặc reconcile**, không mặc định chạy lại business body từ đầu.

### 31.3. Bảng xử lý khái niệm

| Tình huống | Retry phù hợp? | Điều cần chú ý |
|---|---|---|
| `TransientTransactionError` | Có thể retry toàn transaction body | Bounded retries, callback side-effect-free |
| `UnknownTransactionCommitResult` | Retry commit/reconcile | Không nhân đôi business effect |
| `OptimisticLockingFailureException` | Chỉ nếu business cho phép re-read/recompute | Không ghi đè user intent |
| E11000 unique ledger | Reconcile request ID/payload | Có thể là request đã hoàn tất |
| Stock predicate không match | Thường là business rejection | Không retry mù để “thắng” |
| Validation error | Sửa input/schema | Không retry hệt request vô hạn |
| Network timeout | Outcome có thể chưa xác định | Stable request identity, query ledger |

### 31.4. Retry budget

Đặt giới hạn attempts/deadline, backoff với jitter, đo conflicts và phân biệt lỗi transient với permanent. Một test dưới tải cao phải xác nhận hệ thống không tạo retry storm khiến latency tăng vô hạn.

## 32. Idempotency là yêu cầu riêng

Giả sử client gửi request `PAY-123`:

~~~text
T1 Client gửi PAY-123
T2 MongoDB commit payment
T3 Network mất trước response
T4 Client gửi lại PAY-123
~~~

Không thể biết request lần hai là một hành động **mới** hay **gửi lại cùng hành động** nếu không có identity ổn định.

### 32.1. Idempotency key

Một ledger có unique key:

~~~javascript
{
  tenantId: "t-01",
  requestId: "PAY-123",
  payloadHash: "sha256-of-canonical-payload",
  status: "COMMITTED",
  result: { paymentId: "payment-789" }
}
~~~

Unique index:

~~~javascript
db.requestLedger.createIndex(
  { tenantId: 1, requestId: 1 },
  { unique: true }
);
~~~

### 32.2. Cùng key, cùng payload

Nếu request lần hai có cùng key và payload hash, trả **kết quả đã ghi** thay vì tạo payment mới. Khi trạng thái request đang xử lý, cần một protocol `PENDING/COMMITTED/FAILED` hoặc transaction/lease phù hợp.

### 32.3. Cùng key, khác payload

Đây là misuse/conflict; không âm thầm dùng kết quả cũ cho payload mới hoặc thực hiện request mới. Trả lỗi phù hợp và audit.

### 32.4. Unique ledger phải cùng atomic boundary khi cần

Nếu ghi ledger ở một command, trừ tiền ở command thứ hai mà không có transaction/compensation, crash ở giữa vẫn tạo trạng thái không nhất quán. Chọn atomic transaction hoặc protocol state/reconciliation được thiết kế đầy đủ.

## 33. Đừng nhầm retryable writes với exactly-once business operation

MongoDB drivers hỗ trợ retryable writes cho những loại operations/topologies được hỗ trợ; cơ chế có thể giúp tránh áp dụng lại cùng command khi driver retry trong phiên logic phù hợp.

Nhưng:

- HTTP request retry từ một service instance khác có thể là **một logical operation mới** đối với driver.
- Ứng dụng có thể sinh `_id` mới mỗi lần.
- Một business operation có thể gồm nhiều commands, nhiều collections và external service calls.
- Những thao tác như `$inc` mang semantics không idempotent nếu bị gửi lại như business request mới.

### 33.1. Test hai loại retry khác nhau

1. Driver-level retry sau transient network error trong cùng invocation.
2. Application-level retry của **toàn HTTP request** từ client sau timeout.

Test thứ hai mới trực tiếp chứng minh idempotency contract của business API.

### 33.2. Exactly-once effect cần phạm vi rõ

Không hứa “exactly once toàn hệ thống” khi MongoDB và payment gateway không chia sẻ atomic transaction. Mục tiêu thực tế là **effectively once** trong phạm vi đã thiết kế: stable operation ID, dedupe, reconciliation, outbox/inbox, idempotent consumers và audit.

## 34. Kiểm thử cùng request ID chạy song song

Một test idempotency đúng nên tạo nhiều concurrent callers với:

~~~text
tenantId = t-01
requestId = CHECKOUT-123
payload = sku-A, quantity 1, price 120000
~~~

Kỳ vọng:

1. Nhiều callers có thể nhận các response khác nhau về thời điểm (COMMITTED/IN_PROGRESS/retry), nhưng phải đối chiếu về **một business result**.
2. Ledger có **một** entry theo `(tenantId,requestId)`.
3. Inventory giảm **một lần**.
4. Reservation/payment của request này xuất hiện **một lần**.
5. Nếu một caller mất response rồi retry, kết quả cuối vẫn giống request ban đầu.

### 34.1. Đừng assert chỉ trên E11000

Nếu một writer thất bại unique index nhưng đã trừ stock trước khi insert ledger, unique constraint không cứu được invariant. Test phải kiểm tra cả ledger **và** inventory.

### 34.2. Hạn chế số losers

Không kỳ vọng đúng một thread có HTTP 200 và tất cả threads khác HTTP 409 nếu contract nói duplicate request nên trả cùng success. Kết quả HTTP phải xuất phát từ **idempotency policy**, không từ thứ tự scheduling tình cờ.

## 35. Kiểm thử nhiều request IDs tranh stock

Khác với duplicate request, đây là **những business requests độc lập**:

~~~text
Initial stock = 5
Request IDs = R-1, R-2, ..., R-20
Each quantity = 1
20 concurrent callers
~~~

Invariant:

~~~text
successfulDistinctRequests <= 5
finalStock = 5 - successfulDistinctRequests
finalStock >= 0
confirmedReservations = successfulDistinctRequests
~~~

Nếu mọi successful reservation có transaction bảo vệ, có thể kỳ vọng **5 successful requests** khi không có validation/network failures khác; trong test có fault injection, cần phân loại uncertain outcomes và reconcile trước khi khẳng định con số.

### 35.1. Stress test thay đổi stock

Chạy với stock = 0, 1, 5, 100 và concurrency = 1, 2, 10, 100. Quan sát conflicts, retries, p95/p99 và final invariant. Không benchmark trên database có workloads khác.

### 35.2. Số requests nhiều hơn số CPU cores

Concurrency ở client tạo áp lực scheduler và connection pool; không đảm bảo mọi operations thật sự chạy cùng nanosecond. Mục tiêu test là kiểm chứng invariant dưới nhiều interleavings, không nhất thiết “đồng thời tuyệt đối”.

## 36. Test unique seat booking dưới concurrency

Tạo unique index **trước khi** chạy hai insert workers:

~~~java
import com.mongodb.client.MongoCollection;
import com.mongodb.client.model.Indexes;
import com.mongodb.client.model.IndexOptions;
import org.bson.Document;

bookings.createIndex(
    Indexes.ascending("tenantId", "eventId", "seatId"),
    new IndexOptions().unique(true)
);
~~~

Cho 10 workers đồng thời insert:

~~~text
tenantId=t-01, eventId=EV-1, seatId=A-01
each has different booking _id
~~~

Expected:

- Một document tồn tại với key đó.
- Một insert thành công; những attempts còn lại không được tạo bản sao.
- Các lỗi duplicate key được nhận diện là business conflict.
- Nếu index chỉ tồn tại dưới dạng annotation nhưng chưa được tạo trên test DB, test phải thất bại, không được bỏ qua.

### 36.1. Test partial unique

Nếu policy cho phép nhiều CANCELLED nhưng chỉ một ACTIVE, thử:

~~~text
ACTIVE + ACTIVE => conflict
CANCELLED + CANCELLED => allowed
CANCELLED + ACTIVE => allowed
ACTIVE -> CANCELLED rồi tạo ACTIVE mới => allowed
~~~

Cần kiểm tra transitions dưới contention vì update status từ CANCELLED sang ACTIVE cũng chịu unique index constraints.

## 37. Test timeout/unknown outcome bằng fault injection

Không phải mọi lỗi cạnh tranh thể hiện qua hai threads cùng ghi. Một lỗi quan trọng:

~~~text
Server committed write
Connection closed before client received reply
Client sees timeout
Client retries business request
~~~

MongoDB test deployments có thể dùng các cơ chế failpoint được hỗ trợ, ví dụ `configureFailPoint`/`failCommand` trên topology cho phép. Việc bật failpoint yêu cầu quyền đặc biệt và thường **không phù hợp production**; ở Atlas managed tier có thể không được cấp quyền.

### 37.1. Không cần một failpoint cụ thể để hiểu test

Test có thể đặt một controlled proxy/network fault giữa driver và MongoDB trong môi trường cô lập, rồi quan sát retry behavior. Nhưng **đóng connection trước server xử lý** khác với **đóng connection sau commit nhưng trước response**; cần phân biệt để tránh test sai failure mode.

### 37.2. Assertion sau fault

Sau khi hồi phục network:

1. Đọc ledger theo stable request ID.
2. Kiểm tra payment/reservation chỉ có một business effect.
3. Kiểm tra stock/số dư.
4. Nếu commit outcome chưa xác định, reconcile trước khi retry không idempotent.
5. Đảm bảo request không bị bỏ quên vô hạn ở trạng thái PENDING.

### 37.3. Fault injection không phải load test

Một fault đã điều khiển có thể chứng minh handling của một lỗi cụ thể. Stress/load tests cần bổ sung để phát hiện contention/latency/resource problems.

## 38. Kiểm thử transaction rollback

Một test giao dịch nhiều collections:

~~~text
Given stock=0
When transaction inserts ledger then tries to reserve one item
Then stock predicate fails
And transaction aborts
And no ledger/reservation persists
~~~

Điểm cần assert là **không có một phần hiệu ứng** còn tồn tại sau abort.

### 38.1. Force failure

Có thể dùng business rejection `OUT_OF_STOCK`, validation error hoặc controlled exception sau một write trong transaction để xác nhận rollback. Không cần phá process/database mới test được cơ chế atomic rollback.

### 38.2. Verify ở session khác sau transaction

Đọc từ một independent session/client sau abort/commit để kiểm tra persisted state, thay vì chỉ nhìn objects trong transaction callback.

### 38.3. Transaction không gồm side effect HTTP bên ngoài

Nếu callback đã gọi gateway thanh toán trước khi abort MongoDB, gateway có thể vẫn charge khách. Test integration cần mock/fake external gateway có idempotency để phát hiện/gán kết quả rõ.

## 39. Kiểm thử snapshot read và stale secondary

Replica set có thể phục vụ read ở primary hoặc secondaries theo read preference, với read concern phù hợp. Secondary có thể lag:

~~~text
T1 primary commit: stock=0
T2 secondary chưa apply: stock=1
T3 client đọc secondary và hiển thị stock=1
~~~

Một UI hiển thị stale stock không nhất thiết phá invariant nếu **quyết định trừ kho** vẫn thực hiện atomic conditional update trên primary và dựa vào matchedCount.

### 39.1. Test consistency contract

- Nếu API chỉ hứa “stock có thể trễ”, stale read có thể được chấp nhận.
- Nếu API hứa “đã thanh toán thì đọc ngay được trạng thái”, cần read-your-writes/session/consistency strategy phù hợp.
- Nếu balance là quyết định an toàn, đừng dùng client-side stale read làm điều kiện cuối.

### 39.2. Read concern không tự khóa business logic

`majority` và `snapshot` có những semantics cụ thể nhưng không thay conditional write predicate. Kiểm thử thứ tự đọc/ghi dưới failover khi requirement nhạy cảm với thời gian.

## 40. Không dùng `Thread.sleep()` để chứng minh tính an toàn

Một test như:

~~~java
Thread workerA = new Thread(() -> reserve());
Thread workerB = new Thread(() -> reserve());
workerA.start();
Thread.sleep(10);
workerB.start();
~~~

không bảo đảm một interleaving cụ thể và có thể phụ thuộc tải CPU của CI. `Thread.sleep` có thể hữu ích khi mô phỏng delay, nhưng **không phải synchronization primitive** để chứng minh race condition.

### 40.1. Các công cụ nên dùng

| Công cụ | Vai trò |
|---|---|
| `CountDownLatch` | Chờ N workers sẵn sàng hoặc mở một start gate |
| `CyclicBarrier` | Bảo đảm N workers cùng đi qua một điểm sau bước đọc |
| `ExecutorService` | Quản lý thread pool và tasks |
| `Future.get(timeout)` | Lấy result/exception và timeout |
| `AtomicInteger` | Đếm kết quả trong JVM test, không thay DB invariant |
| `CompletableFuture` | Ghép async tasks; cần xử lý exceptions |
| `Testcontainers` | Cấp database test cô lập theo môi trường |

### 40.2. Dùng barrier đúng vị trí

Để tái hiện lost update, barrier **sau read, trước write**. Để test stock conditional update, start gate **trước lệnh atomic update** là đủ để tăng cạnh tranh, vì correctness không phụ thuộc race được cố tình tạo.

### 40.3. Không giữ barrier trong production transaction

Barriers dành cho test process, không phải business synchronization giữa các service instances thật. Production phải dựa vào database constraints/transaction protocol và idempotency.

## 41. Quản lý isolation của tests

Một test concurrency có thể fail vì test khác cùng chạy `deleteMany({})` trên shared collection, không phải vì hệ thống cần sửa concurrency logic.

### 41.1. Database ngẫu nhiên cho mỗi test

~~~java
String dbName = "concurrency_test_" +
    UUID.randomUUID().toString().replace("-", "");
MongoDatabase db = client.getDatabase(dbName);
~~~

Sau test:

~~~java
db.drop();
~~~

**Chỉ drop database ngẫu nhiên do test tạo trên test cluster.** Không để test có quyền drop database production. Với Testcontainers ephemeral instance, container cleanup có thể thay database drop theo lifecycle.

### 41.2. Transaction tests cần topology đúng

Một Testcontainers MongoDB được chạy kiểu standalone có thể không hỗ trợ transaction test. Chọn replica set-enabled setup và readiness criteria phù hợp với phiên bản module Testcontainers MongoDB. Đừng tự giả định vì Docker container đã chạy thì replica set election đã hoàn tất.

### 41.3. Không parallelize tests có cùng fixture ID

Nếu JUnit chạy song song và hai tests đều insert `_id="wallet-1"` trong cùng DB, chúng có thể ảnh hưởng lẫn nhau. Dùng namespaced IDs hoặc test DB riêng.

## 42. Assertions phải gắn với invariants

Đối với mỗi concurrent scenario, có một bảng kỳ vọng:

| Test | Inputs | Expected persisted state |
|---|---|---|
| Hai requests tranh stock=1 | A/B mỗi request 1 | 1 accepted, stock=0 |
| Hai requests tranh balance=100k | A/B trừ 80k | ≤1 accepted, balance≥0 |
| Hai stale editors | Cùng version | 1 save wins, 1 conflict |
| Hai bookings cùng seat | Khác booking ID, same seat key | 1 active booking |
| Hai retries cùng request ID | Same payload | 1 ledger + 1 effect |
| Transaction thiếu stock | Stock=0 | Không có ledger/reservation commit |
| Transaction abort sau write | Controlled failure | Không có partial state |
| Hai requests khác IDs tranh quota=5 | 20 × qty1 | ≤5 confirmed, stock nonnegative |

### 42.1. Không chỉ assert result count

Nếu code báo 1 thành công nhưng tồn kho -1, vẫn sai. Nếu stock=0 nhưng có 2 confirmed bookings, cũng sai. Luôn đọc actual persisted state.

### 42.2. Không chỉ assert DB state mà bỏ response

Nếu cả hai clients nhận success nhưng DB giữ một booking, API contract đã nói dối một khách. Test phải kiểm tra number of business successes và identity của result.

### 42.3. Kiểm tra không có bản ghi “mồ côi”

Ví dụ reservation CONFIRMED không có inventory decrement hoặc payment ledger. Có thể dùng aggregation hoặc query đối soát để phát hiện inconsistent state sau retries/faults.

## 43. Invariant bằng aggregation

Ví dụ kiểm tra số lượng booking active cho từng seat:

~~~javascript
db.bookings.aggregate([
  { $match: { state: "ACTIVE" } },
  {
    $group: {
      _id: {
        tenantId: "$tenantId",
        eventId: "$eventId",
        seatId: "$seatId"
      },
      count: { $sum: 1 }
    }
  },
  { $match: { count: { $gt: 1 } } }
])
~~~

Kỳ vọng **không có document nào trả về**. Test này kiểm tra hậu điều kiện nghiệp vụ, còn unique index ngăn lỗi xảy ra ở database. Cần cả hai vì index có thể chưa được tạo hoặc partial index filter sai.

### 43.1. Inventory không âm

~~~javascript
db.inventory.find({
  available: { $lt: 0 }
})
~~~

Kỳ vọng không có documents.

### 43.2. Ledger trùng request

~~~javascript
db.requestLedger.aggregate([
  {
    $group: {
      _id: {
        tenantId: "$tenantId",
        requestId: "$requestId"
      },
      count: { $sum: 1 }
    }
  },
  { $match: { count: { $gt: 1 } } }
])
~~~

Kỳ vọng không có documents. Nếu unique index đảm bảo điều kiện, count là phép kiểm chứng chéo của test hoặc dữ liệu legacy.

### 43.3. Đọc snapshot kiểm chứng

Trong test transaction, đọc sau khi commit/abort đã kết thúc và qua connection/concern phù hợp để tránh assert trên trạng thái chưa thừa nhận. Nếu có nhiều collections, cân nhắc cách đọc nhất quán cho invariants kiểm tra sau concurrency, nhất là khi còn các writes nền.

## 44. Property-based/concurrent randomized testing

Ngoài các interleavings cố định, tạo nhiều sequences ngẫu nhiên có seed:

~~~text
Initial stock: 20
Operations:
  reserve(qty=1..5)
  replenish(qty=1..5)
  cancelReservation(...)
  retryExistingRequest(...)
  queryStatus(...)
Concurrent workers: 2..50
Seed: 184726
~~~

Kết thúc, tính expected stock dựa trên **các operations đã được xác nhận và idempotency identity**, không dựa đơn thuần vào số HTTP requests.

### 44.1. Lưu random seed và schedule context

Khi test fail, lưu seed, danh sách operation IDs, payloads, outcomes, số retries và timestamps. Nếu không thể tái tạo input, race hiếm sẽ khó điều tra.

### 44.2. Random không thay deterministic

Random stress dễ tìm unexpected interactions nhưng không bảo đảm tái hiện interleaving quan trọng. Giữ các test barrier-driven cốt lõi để chặn regression rõ ràng.

### 44.3. Model-based testing

Xây một **sequential reference model** thực thi các business rules trên dữ liệu nhỏ. So sánh final state và histories của concurrent MongoDB implementation với những outcomes được model cho phép.

## 45. Kiểm tra linearizability và giới hạn

Với một object đơn giản như counter/stock, có thể ghi log:

~~~text
operationId, invokedAt, returnedAt, args, result
~~~

Một lịch chạy có thể được kiểm tra xem có tồn tại một thứ tự tuần tự của các operations tôn trọng **real-time precedence** và cho kết quả hợp lệ không. Đây là ý tưởng **linearizability testing**.

### 45.1. Không nhầm với serializable transactions

Linearizability của một register/counter hoặc một atomic document update không có nghĩa mọi transaction nhiều documents của MongoDB tự đạt full serializable isolation cho mọi business invariant.

### 45.2. Clock giữa machines

Timestamps từ nhiều hosts có clock skew; nếu cần đối chiếu real-time precedence trong distributed test, cần instrumentation và clock model phù hợp. Với test một process, vẫn cần cẩn thận về việc đo invocation/response boundaries.

### 45.3. Histories có timeout

Một operation timeout có thể đã commit. Trong một history checker, outcome “unknown” không được tự coi là “failed” nếu database state chưa được reconcile. Đây là lý do lưu operation identity và đọc ledger sau faults.

## 46. Kiểm thử performance khi có contention

Một thiết kế correctness tốt nhưng mọi requests tranh một document có thể gặp **hotspot**:

~~~text
1000 workers
  -> cùng inventory document SKU-POPULAR
  -> nhiều optimistic conflicts / transaction retries
  -> p99 latency tăng
~~~

### 46.1. Những metrics cần thu

| Metric | Câu hỏi |
|---|---|
| Successful operations/s | Throughput thật đã commit? |
| Business rejections/s | OUT_OF_STOCK hoặc conflict có bình thường? |
| Optimistic conflict count | Bao nhiêu matchedCount=0/stale saves? |
| Transaction abort/retry count | Có contention cao? |
| Duplicate key count | Bao nhiêu requests tranh same identity? |
| p50/p95/p99 latency | Người dùng có bị chờ lâu? |
| Retry attempts distribution | Có retry storm? |
| Connection pool wait | App có thiếu connections? |
| MongoDB CPU/I/O/lock-related metrics | Bottleneck nằm ở server hay app? |
| Ledger reconciliation backlog | Request unknown outcome có bị kẹt? |

### 46.2. Rethink data model

Nếu mọi writes phải sửa một document quota toàn cầu, đó có thể là điểm serialize bắt buộc để bảo vệ invariant. Tăng thread pool không tạo thêm throughput vô hạn. Cân nhắc sharding/partitioning quota theo business semantics, phân phối ownership hoặc queue; phải chứng minh vẫn giữ tổng quota.

### 46.3. Reject nhanh đôi khi đúng hơn retry mãi

Khi stock=0, OUT_OF_STOCK là business result bình thường, không phải lỗi hệ thống cần retry 100 lần.

## 47. Outbox và test side effects bên ngoài

Một order thành công có thể cần publish event:

~~~text
MongoDB order CONFIRMED
Kafka message OrderConfirmed
Email confirmation
Payment gateway capture
~~~

MongoDB transaction không tự gồm Kafka/email/payment provider. Nếu event được gửi ngay trong transaction callback, callback retry có thể phát event nhiều lần dù database chỉ commit một lần.

### 47.1. Transactional outbox

Trong cùng MongoDB transaction, ghi `order` và `outboxEvent` có stable event ID. Một publisher riêng lấy event và gửi; consumer dedupe theo event ID, xử lý at-least-once delivery.

### 47.2. Test event duplicate

Giả lập publisher gửi event thành công nhưng crash trước khi đánh dấu đã gửi; lần sau gửi lại. Consumer phải không trừ hàng/charge thêm nếu cùng event ID.

### 47.3. External payment

Dùng idempotency key với payment provider (nếu được hỗ trợ), reconcile trạng thái charge trước khi retry. Không hứa transaction của MongoDB rollback được một khoản charge đã thành công bên ngoài.

## 48. HTTP contract cho optimistic conflict

Một API có thể đặt:

~~~text
PUT /orders/O-1001
If-Match: "revision-4"

Body: { "status": "APPROVED" }
~~~

Service ánh xạ revision sang expected version và condition nghiệp vụ. Nếu stale:

~~~json
{
  "code": "OPTIMISTIC_CONFLICT",
  "message": "Order was modified; reload before saving",
  "currentRevision": "revision-5"
}
~~~

Đây là **API contract minh họa**. HTTP `If-Match`/ETag có semantics tiêu chuẩn; nếu chọn cách dùng ETag thực tế, triển khai đúng so sánh strong/weak validators và mapping version.

### 48.1. Conflict không phải luôn 500

Một stale edit bình thường có thể trả `409 Conflict` hoặc `412 Precondition Failed` theo API contract. Không log mọi optimistic conflicts như server error nghiêm trọng nếu đó là tình huống sử dụng bình thường.

### 48.2. Không tiết lộ state trái quyền

Nếu caller không có quyền xem order, response conflict không nên trả currentRevision hoặc những nội dung nhạy cảm khiến người dùng đoán record tồn tại.

### 48.3. Retry semantics minh bạch

API nên phân biệt:

- `OUT_OF_STOCK`: business rejection.
- `OPTIMISTIC_CONFLICT`: stale version, cần reload.
- `DUPLICATE_REQUEST`: idempotency key trùng với payload khác.
- `IN_PROGRESS`: cùng key đang xử lý.
- `TEMPORARY_UNAVAILABLE`: có thể retry có kiểm soát.

## 49. Những trường hợp test cần nhiều bước

| Kịch bản | Lỗi dễ bỏ sót |
|---|---|
| Client click nút Pay hai lần | Hai HTTP requests khác nhau cùng intent |
| Client timeout rồi mobile app retry | Duplicate effect vì identity mới |
| Worker restart sau update stock | Không có reservation/ledger |
| Approval và cancellation đồng thời | State machine không được enforce |
| Secondary lag khi xem stock | UI hiển thị stale nhưng quyết định phải atomic |
| Two admins edit full document | Lost update với replace/save không có version |
| Bulk updates bởi script migration | Bỏ qua version protocol của Spring Data |
| Payment provider trả unknown | Retry charge mù |
| Unique index chưa build | Double booking lọt qua |
| Transaction callback retry | External event được gửi hai lần |
| TTL xóa ledger quá sớm | Request cũ retry trở thành request mới |
| Shard migration/failover | Network errors/unknown outcomes cần xử lý |

### 49.1. Retention của idempotency ledger

Nếu ledger giữ 24 giờ nhưng khách có thể retry cùng request sau 7 ngày, policy chưa đủ. TTL/retention phải gắn với **thời hạn có thể gửi lại, audit và hợp đồng nghiệp vụ**, không chỉ để tiết kiệm disk.

### 49.2. Clock và thời gian

Test dùng timestamps cần kiểm soát timezone, clock skew và timestamp precision. Với deadline/expiration, không dựa vào `Thread.sleep` để chứng minh request đã hết hạn chính xác tại boundary; dùng injectable clock cho business logic khi có thể.

## 50. Bài thực hành A — phân loại anomalies

Cho các mô tả:

1. Hai editors đọc version 3; người thứ hai replace full document và xóa mất field người đầu đã sửa.
2. Hai checkout requests cùng đọc stock=1 rồi mỗi request giảm 1.
3. Hai transactions mỗi transaction cho một bác sĩ nghỉ, dựa trên snapshot có hai bác sĩ.
4. Client mất response sau commit rồi gửi lại cùng thanh toán.

Hãy gọi tên lỗi, xác định invariant bị phá và đề xuất cơ chế bảo vệ cho từng trường hợp.

## 51. Bài thực hành B — conditional stock update

Viết `updateOne` bảo vệ `available >= quantity`, với `quantity > 0` được validate ở service. Hai requests độc lập tranh stock=1. Viết assertions cho number of successes, final stock và booking count.

## 52. Bài thực hành C — lost update

Dùng `CyclicBarrier(2)` để hai workers đọc `count=0` trước khi replace. Giải thích vì sao final count có thể là 1. Sau đó thay bằng atomic `$inc` và thay expected final count thành 2.

## 53. Bài thực hành D — CAS

Tạo document `{_id:"x",count:0,version:0}`. Hai workers cùng dùng expected version=0. Kỳ vọng bao nhiêu matchedCount=1? Viết vòng retry bounded để cả hai business increments cuối cùng được áp hợp lệ.

## 54. Bài thực hành E — Spring Data @Version

Tạo entity `Wallet` với `@Version Long version`. Hai bản copy cùng version được đọc. Save A rồi save B. Kiểm tra exception của B và persisted balance. Vì sao write concern unacknowledged khiến việc phát hiện conflict không đáng tin?

## 55. Bài thực hành F — trạng thái đơn

Order PENDING, version 7. Hai workers tranh APPROVED và CANCELLED. Thiết kế filter bắt expected status/version. Nêu các business states được phép sau khi cả hai hoàn tất và điều gì xảy ra với writer thua.

## 56. Bài thực hành G — unique seat

Tạo unique index `(tenantId,eventId,seatId)`. Cho 20 workers insert cùng seat với `_id` khác. Kiểm tra số booking. Nếu nghiệp vụ chỉ cấm hai ACTIVE bookings nhưng muốn giữ nhiều CANCELLED records, sửa index thế nào?

## 57. Bài thực hành H — idempotency

Cho 10 concurrent HTTP requests cùng `requestId="PAY-123"`, cùng payload. Thiết kế ledger unique index, transaction/atomic boundary và cách trả kết quả cho retry. Viết invariant số payment charges và số ledger rows. Nếu payload khác nhưng cùng key thì sao?

## 58. Bài thực hành I — transaction rollback

Transaction insert ledger, sau đó reserve stock nhưng `available=0`. Business code ném `OUT_OF_STOCK`. Sau khi abort, ledger và reservation còn tồn tại không? Những assertions nào chứng minh rollback?

## 59. Bài thực hành J — transient và unknown commit

Phân biệt handling của `TransientTransactionError` với `UnknownTransactionCommitResult`. Tại sao retry **toàn business body** ngay sau unknown commit có nguy cơ nhân đôi effect?

## 60. Bài thực hành K — write skew

Hai doctors A/B đều onCall=true. Mỗi transaction đọc cả hai rồi sửa một document riêng. Tại sao có thể còn 0 người trực? Đề xuất một document guard chung hoặc model một document để bảo vệ invariant.

## 61. Bài thực hành L — raw update bỏ version

Một service dùng Spring Data `@Version` còn một scheduled job dùng raw `updateOne({_id},{$set:{...}})`. Thiết kế test cho thấy write path của job có thể làm version-based editor không phát hiện thay đổi; đề xuất quy tắc sửa.

## 62. Bài thực hành M — fault injection

Simulate network loss sau khi business write được commit nhưng trước khi client nhận response. Tại sao client timeout không chứng minh write thất bại? Cách dùng request ID, ledger reconciliation và retry policy để đạt một business effect?

## 63. Bài thực hành N — concurrency matrix

Với stock 5, chạy requests count 1, 2, 5, 10, 100 và quantities 1, 2, 5, 6. Xác định những invariants cần assert trong mọi kịch bản, bao gồm trường hợp request quantity vượt stock và trường hợp retry cùng request ID.

## 64. Bài thực hành O — theo dõi contention

Đo p95/p99 latency, optimistic conflict count, transaction aborts, duplicate key, retry attempts và throughput khi 100 workers cùng tranh một SKU. Tại sao tăng thread pool từ 100 lên 1000 có thể **giảm** throughput?

## 65. Gợi ý đáp án bài thực hành

**A:** 1 lost update → CAS/@Version; 2 check-then-act/oversell → conditional update; 3 write skew → shared guard/single-document invariant; 4 duplicate business request → idempotency key/ledger/reconcile.

**B:** Dùng filter `{_id:sku,available:{$gte:qty}}` và `$inc:{available:-qty}` trong một command, validate qty>0. Với stock=1, 2 requests qty1: tối đa một success, final stock≥0; nếu có reservation, tạo đúng một record bằng transaction/protocol.

**C:** Barrier sau read buộc hai workers tính `0+1`; last replace ghi count=1. Atomic `$inc` cho final count=2 với hai accepted operations.

**D:** Tối đa một matchedCount=1 ở version 0; worker thua đọc lại version=1, retry bounded, final count/version phản ánh hai accepted increments.

**E:** Stale B phải gặp `OptimisticLockingFailureException` khi dùng version-aware save và acknowledged writes, persisted value là của A.

**F:** APPROVED hoặc CANCELLED thắng, không thể cả hai transitions cùng thành công từ PENDING với expected status/version; loser nhận conflict/rejection.

**G:** Một unique key chỉ cho một booking; với nhiều lịch sử CANCELLED và một ACTIVE, cân nhắc partial unique index theo `state:"ACTIVE"`, kèm kiểm thử transitions.

**H:** Unique ledger theo tenant+requestId, payload hash, result persisted và atomic boundary với payment effect. Same key/same payload trả kết quả cũ; same key/different payload trả conflict.

**I:** Transaction abort phải loại mọi writes bên trong: không còn ledger/reservation, stock giữ 0; assert từ session khác.

**J:** Transient transaction error có thể retry toàn body theo driver support; unknown commit cần retry commit/reconcile, không chạy lại non-idempotent business operation mù.

**K:** Hai transactions đọc snapshot giống nhau nhưng cập nhật docs khác nhau, không có write conflict chung; cần guard document chung, một document chứa quota, hoặc serialization policy.

**L:** Raw update không có version predicate/increment có thể tránh detection. Buộc mọi writers theo cùng protocol, bổ sung integration tests giữa các đường viết.

**M:** Timeout là outcome chưa xác định, không phải khẳng định rollback; đọc ledger bằng stable request ID và dùng idempotent retries để tránh nhân đôi effect.

**N:** Assert stock≥0, số units confirmed≤initial+replenished, mỗi request ID chỉ một effect, no orphan reservations; trường hợp quantity>stock bị từ chối.

**O:** Cùng một hot document gây conflicts/retries, CPU và connection waits tăng; contention có thể khiến nhiều threads làm hệ thống chậm hơn, cần rate limits/backoff/data model phù hợp.

## 66. Những lỗi triển khai thường gặp

| Sai lầm | Nguy cơ | Cách sửa |
|---|---|---|
| Read stock rồi update bằng `_id` | Oversell/stock âm | Atomic predicate `available>=qty` |
| Replace full document không version | Lost update | `@Version` hoặc CAS |
| Version update thành hai commands | Race giữa data/version | Một atomic update |
| Catch optimistic conflict rồi trả success | Che stale write | Domain conflict/reload |
| Retry stale form vô hạn | Ghi đè user intent | Business merge policy |
| Dùng `modifiedCount` cho mọi business result | No-op bị hiểu sai | Contract rõ về matched/acknowledged |
| Unique index chỉ có annotation nhưng chưa build | Double booking | Assert index trong integration test |
| Insert duplicate rồi retry với ID mới | Không giải quyết seat conflict | Kiểm tra business key/ledger |
| Ledger ghi ngoài transaction với stock | Partial state sau crash | Atomic boundary/reconciliation |
| Transaction body gọi payment gateway | Side effect lặp khi retry | Outbox/idempotent external protocol |
| Retry whole body sau unknown commit | Double business effect | Commit retry/reconcile |
| Không phân biệt lỗi transient/business | Retry storm | Error taxonomy |
| `Thread.sleep` để tạo race | Flaky tests | Barrier/latch |
| Shared test DB và `deleteMany({})` | Tests tác động lẫn nhau | Database/fixture isolation |
| Test transactions trên standalone không hỗ trợ | Test sai môi trường | Replica set-enabled test |
| Test chỉ assert HTTP 200 | Bỏ qua invariant DB | Validate persisted state |
| Test chỉ assert stock=0 | Bỏ qua double-success | Validate result count và reservations |
| Reuse request ID với payload khác | Nhầm identity | Payload fingerprint + conflict |
| TTL ledger quá ngắn | Retry muộn gây double effect | Retention theo replay horizon |
| Chỉ kiểm thử một interleaving | Race khác chưa bắt | Deterministic + stress + fault |
| Không timeout Future/barrier | CI treo | Bounded waits/cleanup |

## 67. Câu hỏi ôn tập

**1. Single-document atomicity bảo vệ gì?** — Một thao tác cập nhật document là nguyên tử trong phạm vi MongoDB hỗ trợ; không tự gộp nhiều commands thành một transaction.

**2. Vì sao read-then-write có thể sai?** — Hai writers đọc cùng trạng thái cũ rồi ra quyết định trước khi một trong hai ghi.

**3. Lost update là gì?** — Một writer ghi đè thay đổi của writer khác mà không phát hiện.

**4. Cách an toàn để tăng counter?** — Atomic `$inc` hoặc versioned CAS theo semantics.

**5. Cách giảm stock không âm?** — `updateOne` với `available >= qty` và `$inc:-qty` trong cùng atomic operation.

**6. Vì sao quantity phải được validate?** — Quantity 0/âm/sai kiểu có thể phá logic của predicate/update.

**7. CAS dùng điều kiện gì?** — ID/owner/business predicate và expected version.

**8. Version phải tăng khi nào?** — Cùng command ghi thành công.

**9. `matchedCount=0` chứng minh stale version không?** — Không; còn có thể not found/tenant mismatch/business predicate fail.

**10. `@Version` của Spring Data giúp gì?** — Phát hiện stale saves/versioned updates qua version predicate.

**11. Có thể dùng unacknowledged writes để kiểm tra optimistic lock không?** — Không đáng tin vì thiếu confirmed match result.

**12. Raw MongoDB update có tự tôn trọng `@Version` trên POJO không?** — Không, phải gửi đúng predicate/update protocol.

**13. Optimistic conflict có giống MongoDB WriteConflict không?** — Không; chúng đến từ tầng khác nhau và có retry policies khác nhau.

**14. Khi nào dùng unique index?** — Bảo vệ uniqueness của business key dưới concurrent inserts/updates.

**15. Unique index có tự bảo vệ quota tổng không?** — Không, cần invariant design khác.

**16. Transaction dùng để làm gì?** — Atomic commit/abort của nhiều operations trong phạm vi MongoDB hỗ trợ.

**17. Transaction có thể bảo vệ external payment gateway không?** — Không trực tiếp; cần idempotency/outbox/reconciliation.

**18. Snapshot isolation có ngăn mọi write skew không?** — Không nên giả định; cần guard chung hoặc model phù hợp.

**19. `TransientTransactionError` xử lý thế nào?** — Có thể retry transaction body theo driver semantics và retry budget.

**20. `UnknownTransactionCommitResult` nghĩa gì?** — Client không chắc kết quả commit; retry commit/reconcile.

**21. DuplicateKey luôn là lỗi ứng dụng cần retry?** — Không; có thể là business conflict hoặc duplicate idempotent request.

**22. Idempotency key dùng để làm gì?** — Nhận diện cùng một business request khi gửi lại.

**23. Cùng key nhưng khác payload xử lý sao?** — Conflict/reject, không tái sử dụng lặng lẽ.

**24. Atomic update có tự đảm bảo idempotency HTTP retries không?** — Không.

**25. Tại sao dùng `CyclicBarrier` sau read?** — Buộc hai workers cùng dùng snapshot cũ để tái hiện lost update.

**26. `Thread.sleep` có đủ làm concurrency test không?** — Không, scheduling không được bảo đảm.

**27. Chỉ mock repository đã kiểm tra MongoDB atomicity chưa?** — Chưa; cần integration test với MongoDB thật.

**28. Multi-document transaction test cần topology gì?** — Replica set/sharded deployment hỗ trợ, không phải standalone thông thường.

**29. Vì sao test DB phải cô lập?** — Tránh tests khác xóa/sửa fixture và tránh ảnh hưởng production.

**30. Tại sao kiểm tra DB state ngoài response?** — Response có thể sai hoặc mất trong khi write đã commit.

**31. Stale secondary có tự gây oversell không?** — Có thể dẫn tới UI/decision stale; atomic write predicate đúng vẫn có thể bảo vệ stock invariant.

**32. Một hot document ảnh hưởng gì?** — Contention, retries và tail latency tăng.

**33. Có thể retry stock OUT_OF_STOCK hàng trăm lần để “thắng” không?** — Không nên; đó thường là business rejection.

**34. Khi nào optimistic lock phù hợp?** — Xung đột hiếm, cần phát hiện stale edits và merge/reload.

**35. Một test concurrency được coi hoàn thành khi nào?** — Cả outcomes và persisted invariants đúng, lỗi/timeouts được phân loại và test có cleanup.

## 68. Bảng ghi nhớ nhanh

| Vấn đề | Giải pháp/test |
|---|---|
| Lost update khi replace | `@Version` hoặc CAS expected version |
| Counter update | Atomic `$inc` |
| Stock không âm | `updateOne({_id,available:{$gte:qty}},{$inc:{available:-qty}})` |
| Stale entity Spring Data | `OptimisticLockingFailureException` |
| Unique seat/email | Unique/partial unique index |
| Trừ kho + insert reservation | Transaction hoặc model atomic một document |
| Request gửi lại | Stable idempotency key + ledger + payload hash |
| Unknown commit | Commit retry/reconcile theo driver semantics |
| Transient transaction failure | Retry toàn transaction có giới hạn |
| Write skew | Shared guard/single-document invariant |
| Reproduce lost update | `CyclicBarrier` sau read |
| Competing start | `CountDownLatch` start gate |
| Threads/tasks | `ExecutorService`, `Future.get(timeout)` |
| Tests MongoDB semantics | Integration test MongoDB thật |
| Tests transactions | Replica set-enabled test topology |
| Validate hậu điều kiện | Database queries/aggregations + response counts |
| Retrying side effects | Outbox/idempotent consumer/reconciliation |
| Production contention | Conflict/retry metrics, p95/p99, backoff |

## 69. Checklist kiểm thử trước khi release

- [ ] Các business invariants đã được viết thành assertions rõ?
- [ ] Đã xác định invariant nằm trong một document hay nhiều documents/services?
- [ ] Mọi stock/balance deduction dùng atomic predicate tại lúc ghi?
- [ ] Input quantities, money values và ownership được validate?
- [ ] Mọi optimistic writes kiểm tra expected version và tăng version cùng update?
- [ ] `@Version` có được mọi write paths (repository, raw driver, scripts) tôn trọng?
- [ ] Write concern đủ để phát hiện stale version?
- [ ] Có response contract cho optimistic conflict/not found/business rejection?
- [ ] Unique indexes tồn tại thật trên database, không chỉ annotation?
- [ ] Partial unique index/filter/collation phù hợp business states?
- [ ] MongoDB transaction bao bọc những writes cần atomic cùng nhau?
- [ ] Có test abort/rollback, transient retry và unknown commit?
- [ ] Transaction callback không gọi external side effects không idempotent?
- [ ] Idempotency keys ổn định theo tenant/operation và có payload fingerprints?
- [ ] Same request ID concurrent/retry tạo đúng một business effect?
- [ ] TTL/retention ledger dài hơn replay window?
- [ ] Có test khác request IDs tranh stock/quota?
- [ ] Có test lost update deterministic với barrier sau read?
- [ ] Có timeout cho barriers/futures và cleanup thread pools?
- [ ] Tests chạy trên MongoDB thực với database cô lập?
- [ ] Transaction tests dùng replica set/sharded test topology phù hợp?
- [ ] Tests không fallback sang production URI nếu thiếu test config?
- [ ] Assert cả responses và persisted invariants?
- [ ] Có kiểm tra duplicate bookings, âm kho, orphan ledger/reservations?
- [ ] Có test concurrent transitions của business state machine?
- [ ] Có test stale secondary/read-consistency nếu business phụ thuộc?
- [ ] Có stress test nhiều mức concurrency và randomized seed tái hiện được?
- [ ] Có fault injection cho timeout/unknown result khi môi trường hỗ trợ?
- [ ] Có metrics conflicts/retries/aborts/latency/throughput và retry budget?
- [ ] Có kế hoạch rollback và reconciliation khi phát hiện dữ liệu sai?

## 70. Kết luận

Kiểm thử cạnh tranh trong MongoDB phải bắt đầu từ câu hỏi: **“Những trạng thái nghiệp vụ nào tuyệt đối không được xuất hiện?”** Một single-document update có thể nguyên tử nhưng logic đọc trước–ghi sau vẫn có race. Một `@Version` bảo vệ stale saves nhưng không thay unique index. Một transaction cho phép commit nhiều writes cùng nhau nhưng không tự bao trùm external payment side effects hoặc mọi invariant liên documents.

Với tồn kho và số dư, ưu tiên **atomic conditional updates** bảo vệ điều kiện tại thời điểm ghi. Với nhiều editors hoặc read–modify–write workflow, dùng **optimistic locking/CAS** để phát hiện version cũ và trả conflict/recompute đúng business semantics. Với identity như seat, email hoặc request ID, dùng **unique indexes và idempotency ledgers**. Khi một operation cần thay đổi nhiều documents, dùng transaction theo phạm vi MongoDB hỗ trợ, đồng thời thiết kế retries, unknown commit handling và reconciliation có kiểm soát.

Cuối cùng, đừng tin một bài test chạy tuần tự hoặc hai threads được khởi động “gần nhau” là đủ. Hãy dùng **barrier/latch để tái hiện interleavings**, MongoDB thật để kiểm tra semantics, stress/fault tests để mở rộng coverage, và assertions lên **trạng thái đã persisted**: không âm kho, không double booking, không lost update, không double charge và không có record mồ côi. Một hệ thống chỉ thực sự đáng tin khi **mọi kết quả được phép của cạnh tranh** vẫn giữ nguyên các ràng buộc nghiệp vụ.
