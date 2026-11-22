# Xung đột giao dịch và thử lại toàn đơn vị công việc

Một ứng dụng NoSQL có thể dùng transaction, cập nhật có điều kiện (CAS), phiên bản tài liệu hoặc một SDK tự động retry. Nhưng những cơ chế này không có nghĩa là **mỗi request sẽ thành công ngay lần đầu**, cũng không có nghĩa “gặp lỗi cứ gửi lại lệnh vừa thất bại”.

Khi hai giao dịch cùng đọc và sửa một tập bản ghi, database có thể phát hiện **write conflict**, **serialization failure**, **optimistic concurrency conflict**, **deadlock** hoặc từ chối một lần ghi để bảo vệ tính đúng đắn. Khi đó, application cần quyết định **có nên retry không**, **retry phần nào**, **giữ lại những dữ kiện nào** và **giải quyết ra sao nếu không biết commit đã thành công hay chưa**.

Vấn đề đặc biệt quan trọng với các workflow có nhiều bước phụ thuộc nhau. Giả sử hệ thống bán vé:

~~~text
1. Đọc số ghế còn trống.
2. Xác minh khách được đặt vé.
3. Đánh dấu ghế đã giữ.
4. Tạo Booking.
5. Ghi OutboxEvent.
6. Commit.
~~~

Nếu bước 3 xảy ra xung đột, chỉ thử lại bước 3 với dữ liệu đọc cũ là sai. Ghế có thể đã bị người khác giữ, giá vé đã thay đổi, hoặc khách không còn đủ điều kiện. Một lần thử mới phải **đọc lại trạng thái liên quan, kiểm tra lại bất biến và tạo lại toàn bộ các thay đổi thuộc cùng đơn vị công việc**.

Đó là ý nghĩa thực hành của **thử lại toàn đơn vị công việc (retry the whole unit of work)**. Tuy nhiên, không được tự động chạy lại toàn bộ mọi thứ khi lỗi commit chưa rõ kết quả: làm như vậy có thể tạo đơn hoặc thu tiền hai lần. Bài học phân biệt rõ **transaction bị abort đã biết**, **điều kiện nghiệp vụ thất bại**, và **kết quả commit chưa xác định**.

> **Phạm vi:** Tài liệu bàn về cập nhật đồng thời trong NoSQL, bao gồm transaction nhiều record, atomic conditional write, LWT và optimistic concurrency. Ví dụ MongoDB, DynamoDB, Firestore, Cosmos DB, Couchbase, Cassandra/ScyllaDB, Redis và transactional key–value chỉ minh họa những loại contract phổ biến. Error code, SDK retry, isolation và transaction scope phụ thuộc phiên bản, chế độ triển khai, cấu hình và API thực tế; cần đọc tài liệu của sản phẩm đang chạy trước khi đưa vào production.

## 1. Đơn vị công việc là gì?

**Unit of work (UoW)** là nhóm hành động cùng tạo ra **một kết quả nghiệp vụ nhất quán**, trong đó các phép đọc tạo căn cứ cho quyết định và các phép ghi áp dụng quyết định đó.

Một UoW có thể nhỏ:

~~~text
ReserveStock(sku, requestedQuantity)
    đọc stock của sku
    kiểm tra available >= requestedQuantity
    giảm available
    ghi reservationId
~~~

Hoặc nhiều record:

~~~text
CreateBooking(commandId, customerId, seatId)
    đọc Seat(seatId) và quy tắc giá
    kiểm tra Seat còn trống
    tạo Booking(commandId)
    đánh dấu Seat đã giữ
    tạo OutboxEvent(BookingCreated)
    commit
~~~

Điểm quan trọng: **đơn vị công việc không đồng nghĩa toàn bộ một HTTP request**. Trong HTTP request còn có validate input, xác thực, network calls, gửi email hoặc trả response. Chỉ những hành động thực sự tham gia cùng ranh giới nguyên tử của database mới thuộc **transaction retryable**.

### 1.1. Ba ranh giới cần vẽ riêng

| Ranh giới | Ví dụ | Điều được bảo đảm |
|---|---|---|
| **Đơn vị nghiệp vụ** | Xác nhận một Booking và thanh toán | Kết quả nghiệp vụ mong muốn |
| **Transaction database** | Update Seat + insert Booking + insert Outbox | Atomicity/isolation theo contract DB |
| **Hiệu ứng bên ngoài** | Charge gateway, gửi email, webhook | Cần giao thức riêng, không tự nằm trong DB transaction |

Nếu DB chỉ hỗ trợ transaction cùng logical partition mà Seat và Booking thuộc hai partition, UoW nghiệp vụ **không tự biến thành transaction xuyên partition**. Phải đổi mô hình, chọn API/công nghệ hỗ trợ hoặc thiết kế saga có trạng thái bền.

### 1.2. Mọi dữ liệu quyết định ghi phải được xét lại

Một giao dịch đọc Seat giá 100, kiểm tra coupon và tính tổng 90. Nếu nó bị abort, lần thử mới không nên chỉ thực hiện lại lệnh `INSERT Booking(total=90)` mà không xem giá/coupon hiện tại. Giá, số ghế và điều kiện áp dụng coupon có thể đã thay đổi.

Những phép đọc để **ra quyết định** phải được thực hiện lại trong transaction attempt mới, hoặc được thay thế bằng **predicate nguyên tử** đủ mạnh tại thời điểm ghi.

### 1.3. Không phải mọi dữ liệu input đều cần thay đổi khi retry

**Ý định gốc** phải ổn định: `commandId`, `customerId`, `seatId`, `requestedQuantity`, số tiền mà khách đã đồng ý theo hợp đồng. Nhưng **trạng thái dẫn xuất** từ database như availability, version, giá hiện tại, quota và trạng thái giữ chỗ cần được đọc và kiểm tra lại theo rule.

Phân biệt hai nhóm sẽ giúp retry không vô tình thay đổi ý định của người dùng.

## 2. Xung đột giao dịch có nhiều hình thức

Trong cùng một từ “conflict” có thể ẩn các tình huống rất khác nhau.

| Loại | Nguyên nhân | Hành vi thường cần cân nhắc |
|---|---|---|
| **Write–write conflict** | Hai transaction cùng sửa record/version | Một transaction bị abort hoặc condition fail |
| **Optimistic version mismatch** | Expected version đã cũ | Đọc lại và đánh giá command, hoặc trả conflict |
| **Serialization failure** | Lịch thực thi không đáp ứng mức isolation hứa | Retry toàn transaction nếu an toàn |
| **Deadlock victim** | Các transaction chờ khóa theo vòng | DB hủy một bên, application retry từ đầu |
| **Conditional predicate failed** | Không đủ tồn, sai status hoặc record không tồn tại | Có thể là từ chối nghiệp vụ, không retry mù |
| **Unique constraint conflict** | Hai request cùng tạo key duy nhất | Có thể trả duplicate hoặc đối soát idempotency |
| **Transaction timeout** | Hết thời gian, nghẽn hoặc network | Phải phân biệt abort chắc chắn với outcome chưa rõ |
| **Throttle/capacity** | Giới hạn tài nguyên hoặc hot partition | Backoff và điều tiết tải; không nhất thiết là logical conflict |
| **Unknown commit outcome** | Commit có thể đã thành công, response mất | Đối soát/retry commit đúng protocol trước khi lặp nghiệp vụ |

### 2.1. Write conflict không phải lỗi dữ liệu

Hai transaction cùng muốn đổi Order version 7:

~~~text
T1: read Order v7
T2: read Order v7
T1: update status=CONFIRMED
T1: commit -> v8
T2: attempt update based on v7 -> conflict
~~~

Database **từ chối T2** là một phần của cơ chế bảo vệ dữ liệu. Application không nên coi T2 thất bại là lý do bỏ condition và ép ghi. Có thể đọc v8 để quyết định command của T2 còn hợp lệ hay không.

### 2.2. Deadlock và transaction victim

Hai giao dịch lấy khóa theo thứ tự khác nhau:

~~~text
T1: lock Account A -> chờ Account B
T2: lock Account B -> chờ Account A
~~~

Nếu engine hỗ trợ locking, nó có thể phát hiện deadlock và abort một transaction. Sau đó **các lệnh thuộc attempt bị abort không còn hiệu lực như một phần UoW**. Retry đúng cần bắt đầu một transaction mới, đọc state mới và thực hiện lại logic, không tiếp tục từ câu lệnh đang chờ.

Không phải mọi NoSQL dùng khóa theo mô hình này; nhiều hệ dùng OCC, MVCC hoặc conditional consensus với cách báo lỗi riêng.

### 2.3. Serialization failure

Trong isolation mạnh, engine có thể cho transaction đọc/ghi song song rồi quyết định không thể commit tất cả theo một thứ tự hợp lệ. Một transaction bị abort để giữ tính đúng đắn.

**Điều đáng mừng:** DB đã phát hiện cuộc đua. **Điều application phải làm:** nhận diện đúng loại abort và thử lại **toàn bộ chuỗi đọc–kiểm tra–ghi** nếu command phù hợp.

### 2.4. Business failure không nên bị retry như conflict

Nếu Inventory chỉ còn 1 nhưng khách muốn 3, một conditional write `available >= 3` thất bại không có nghĩa lỗi hạ tầng. Có thể hệ **đã hoạt động đúng** khi từ chối. Thử lại 100 lần chỉ làm tăng tải nếu không có sự kiện bổ sung tồn kho.

Không nên gom lỗi `INSUFFICIENT_STOCK`, `INVALID_ORDER_STATE` hoặc `FORBIDDEN` vào cùng retry policy với serialization failure.

## 3. Vì sao chỉ retry câu lệnh thất bại có thể sai?

Giả sử một giao dịch chọn ghế:

~~~text
T1:
  read Seat A1: AVAILABLE
  read Price: 100
  calculate Total: 90 after coupon
  update Seat A1 -> HELD
  insert Booking(total=90)
  insert Outbox
  commit
~~~

Trong lúc T1 đang chạy, T2 giữ ghế A1 trước và giá/coupon có thể thay đổi.

Nếu DB phát hiện conflict và abort T1, một cách retry **sai**:

~~~text
Retry only:
  update Seat A1 -> HELD
  insert Booking(total=90 from old snapshot)
~~~

Những giá trị đã đọc/kiểm tra thuộc attempt cũ không còn căn cứ. Thậm chí nếu bước update Seat thành công sau đó, Booking có thể vi phạm quy tắc giá hoặc giữ ghế đã thuộc người khác.

### 3.1. Retry đúng

~~~text
New attempt:
  BEGIN NEW TRANSACTION
  read Seat A1
  read current pricing/coupon state
  validate availability and eligibility
  calculate new candidate (or reject if agreed price differs)
  update Seat conditionally
  insert Booking with stable commandId
  insert Outbox with stable eventId
  COMMIT
~~~

Nếu Seat đã bị giữ, command trả `SEAT_UNAVAILABLE` thay vì cố ghi. Nếu giá hiện tại khác mức người dùng đồng ý, hệ không được âm thầm tính lại và thu giá mới; cần business precondition hoặc yêu cầu người dùng xác nhận lại.

### 3.2. Ví dụ chuyển tiền

Ban đầu:

~~~text
Account A = 120
Account B = 50

Transfer 100:
  kiểm tra A >= 100
  trừ A 100
  cộng B 100
  ghi Ledger
~~~

Khi transaction bị abort vì conflict trên A, không thể chỉ retry lệnh cộng B. Toàn transfer phải được đánh giá lại từ trạng thái có thẩm quyền; các bước phải cùng commit hoặc dùng một giao thức giao dịch khác đáp ứng invariant.

### 3.3. Lệnh độc lập là ngoại lệ, không phải mặc định

Đối với một phép atomic increment đơn lẻ không phụ thuộc read trước, retry *một thao tác* có thể là toàn UoW. Nhưng nếu request có thể đã commit rồi mất ACK, vẫn cần **idempotency** để không tăng hai lần. “Retry toàn UoW” không có nghĩa mọi UoW phải chứa nhiều lệnh.

## 4. Mô hình vòng đời một transaction attempt

~~~mermaid
stateDiagram-v2
    [*] --> NEW
    NEW --> ACTIVE: Begin transaction
    ACTIVE --> COMMITTING: Validate + write
    ACTIVE --> ABORTED: Conflict/validation/timeout with known abort
    COMMITTING --> COMMITTED: Commit ACK
    COMMITTING --> ABORTED: Confirmed abort
    COMMITTING --> UNKNOWN: Response lost / ambiguous outcome
    ABORTED --> NEW: Retry permitted, whole UoW
    UNKNOWN --> RESOLVING: Query commandId / protocol retry
    RESOLVING --> COMMITTED: Found committed result
    RESOLVING --> ABORTED: Confirmed not committed
    RESOLVING --> UNKNOWN: Still ambiguous
    COMMITTED --> [*]
~~~

Một request ngoài hệ có thể kết thúc khi transaction vẫn `UNKNOWN`; phải lưu đủ **commandId và trạng thái đối soát** để không quên nghiệp vụ.

### 4.1. Attempt không đồng nghĩa command

~~~text
commandId = checkout-7281

attempt 1: transaction conflict -> aborted
attempt 2: transient conflict -> aborted
attempt 3: commit -> success
~~~

Ba attempt thuộc **cùng một command**. Chúng có thể có transaction ID và read snapshot khác nhau, nhưng dùng cùng idempotency key của nghiệp vụ.

### 4.2. Abort đã xác nhận khác ACK bị mất

**Confirmed abort:** DB đã xác nhận lần thử không commit; ứng dụng có thể tạo attempt mới theo policy.

**Unknown commit:** client không biết lệnh commit đã có hiệu lực chưa. Không tự chạy lại UoW như thể chắc chắn abort. Trước tiên theo cơ chế của SDK/DB để xác định outcome hoặc retry commit nếu protocol cho phép; nếu không, tra cứu business commandId từ nguồn có thẩm quyền.

### 4.3. Trạng thái lệnh nghiệp vụ nên được bền

Một orchestrator có thể lưu:

~~~json
{
  "commandId": "checkout-7281",
  "status": "RESOLVING_COMMIT",
  "orderId": "O-100",
  "lastAttempt": 3,
  "requestedAt": "2026-11-14T08:00:00Z"
}
~~~

Đây là ví dụ metadata workflow, không phải cấu trúc bắt buộc. Việc ghi `status` này cũng cần tính nguyên tử/idempotency tương ứng, tránh ghi một kết quả mâu thuẫn với transaction chính.

## 5. Ba nhóm kết quả và policy retry

| Outcome | Đã biết transaction có commit không? | Nên làm gì? |
|---|---|---|
| **Success / committed** | Có | Trả kết quả, không thực hiện lại command |
| **Known conflict abort** | Biết không commit | Có thể chạy lại toàn transaction từ đầu |
| **Business rejection** | Không commit theo predicate | Trả lỗi nghiệp vụ hoặc yêu cầu thay đổi input |
| **Known transaction timeout abort** | Biết không commit theo contract | Retry giới hạn nếu thích hợp |
| **Throttling trước commit** | Tùy API, cần phân loại outcome | Backoff/retry theo hướng dẫn API |
| **Unknown commit result** | Không | Đối soát hoặc tiếp tục protocol commit |
| **Authentication/authorization failure** | Không được phép | Không retry như xung đột |
| **Invalid request/schema** | Request sai | Sửa lỗi, không retry tự động |
| **Transaction too large / unsupported scope** | Không thể commit với API này | Đổi thiết kế, không retry liên tục |

**Không được phân loại chỉ bằng nội dung chuỗi lỗi.** Ưu tiên error code/label có định nghĩa từ SDK và loại exception cụ thể; version SDK có thể thay đổi thông điệp.

### 5.1. Một lỗi có thể được báo từ nhiều lớp

Ví dụ `timeout` có thể là:

- Hết thời gian chờ lấy kết nối trước khi bắt đầu transaction.
- Hết thời gian một attempt transaction được phép tồn tại.
- Network timeout khi thực thi lệnh nhưng chưa commit.
- Network timeout lúc gửi `COMMIT`.
- Server trả lỗi `transaction aborted` có mã rõ.

Chỉ nhãn timeout không đủ để biết có an toàn khi tạo attempt mới không.

### 5.2. Retry budget

Một transaction có thể được thử lại N lần hoặc trong **tổng thời gian** tối đa. Cần giới hạn đồng thời:

~~~text
maxAttempts
maxElapsedTime
perAttemptTimeout
maxBackoff
overallRequestDeadline
~~~

Một retry loop có giới hạn theo số lần nhưng mỗi attempt treo vô hạn vẫn không có thời gian phản hồi hữu ích.

## 6. Retry toàn UoW có nghĩa gì ở mã ứng dụng?

Một transaction attempt gồm:

1. **Mở transaction mới** và lấy snapshot/phiên bản theo cơ chế của DB.
2. **Đọc lại các bản ghi** liên quan tới quyết định.
3. **Đánh giá lại bất biến** từ state hiện tại.
4. **Tính lại thay đổi dẫn xuất** từ state mới.
5. **Ghi toàn bộ thay đổi** cần nguyên tử trong transaction.
6. **Commit và phân loại kết quả**, hoặc abort đúng cách.
7. Nếu abort vì conflict **có thể retry**, bắt đầu attempt khác từ bước 1.

~~~mermaid
flowchart TD
    CMD["Business command với commandId ổn định"] --> BEGIN["Begin new attempt"]
    BEGIN --> READ["Read current state"]
    READ --> RULE["Validate invariants + recalculate"]
    RULE --> VALID{"Business rule satisfied?"}
    VALID -->|Không| REJECT["Business rejection"]
    VALID -->|Có| WRITE["Write all dependent records"]
    WRITE --> COMMIT["Commit"]
    COMMIT --> RESULT{"Outcome?"}
    RESULT -->|Committed| DONE["Record final result"]
    RESULT -->|Known retryable abort| BACK["Bounded backoff + jitter"]
    BACK --> BEGIN
    RESULT -->|Unknown| RESOLVE["Resolve commit by protocol / commandId"]
    RESULT -->|Nonretryable| FAIL["Return/compensate as specified"]
~~~

### 6.1. Những gì giữ nguyên qua các attempt

| Giá trị | Giữ nguyên? | Giải thích |
|---|---|---|
| `commandId` / `reservationId` | **Có** | Nhận diện cùng ý định |
| Customer, SKU, số lượng đã yêu cầu | **Có** | Không đổi ý định người dùng |
| Số tiền/giá đã được khách đồng ý | **Có hoặc phải yêu cầu đồng ý lại** | Không âm thầm thu giá khác |
| Current Inventory, version, status | **Không** | Phải đọc lại |
| Tính toán dựa trên current state | **Không** | Phải đánh giá lại |
| Event ID logic của cùng command | Thường giữ ổn định | Dedupe downstream |
| Transaction ID/attempt count | **Khác** | Mỗi attempt là một transaction |
| External side effect đã xảy ra | Không được tự phát lại | Cần idempotency và đối soát |

### 6.2. Không dùng dữ liệu cache cũ làm nguồn quyết định

Nếu UoW mở transaction mới nhưng lại dùng bản Inventory từ cache của attempt trước để quyết định số tồn, đó không phải retry đúng nghĩa. Điều kiện bảo vệ phải dựa vào **nguồn có thẩm quyền** hoặc atomic predicate được DB áp dụng lúc commit.

### 6.3. Nếu invariant chỉ thuộc một item

Có thể tránh read–modify–write nhiều bước bằng một conditional update:

~~~text
UPDATE Inventory
IF available >= quantity AND reservationId not processed
THEN decrease available AND record reservationId
~~~

Câu lệnh minh họa; khả năng kiểm tra reservationId cùng số tồn phụ thuộc data model và transaction scope. Một atomic conditional write có thể **là toàn UoW** cho invariant cục bộ, giảm tranh chấp so với transaction đọc trước.

## 7. Retry toàn transaction không đồng nghĩa retry toàn HTTP request

Giả sử endpoint:

~~~text
POST /checkout
    validate JWT
    fetch shipping quote from another service
    run DB transaction
    charge external gateway
    send email
    return response
~~~

Nếu DB transaction bị abort vì conflict, không nên đơn giản gọi lại **toàn endpoint** mà không quản lý payment/email. Cần thiết kế các ranh giới:

~~~text
Request:
    parse + authenticate + validate immutable input
    create stable commandId
    prepare external data under explicit validity policy

Retryable transaction body:
    read authoritative DB state
    validate business preconditions
    change DB records
    insert outbox/intent

After commit:
    drive idempotent external workflow
    send response or report pending
~~~

### 7.1. External side effects làm callback không thuần

Sai:

~~~text
transaction(() => {
    decrementStock()
    chargeCreditCard()  // may execute twice!
    insertOrder()
})
~~~

Nếu SDK tự retry callback sau conflict, gateway có thể bị gọi nhiều lần, ngay cả khi cuối cùng database chỉ commit một lần.

### 7.2. Callback nên chỉ làm việc phù hợp transaction scope

Hợp lý hơn:

~~~text
transaction(() => {
    read + validate current Stock
    reserve Stock
    create Order(status=PAYMENT_PENDING)
    insert Outbox(PaymentRequested, commandId)
})

Payment worker:
    read durable intent
    call gateway with paymentId/idempotency key
    store/confirm result idempotently
    advance Order state conditionally
~~~

Một số ứng dụng có thể chọn authorize Payment trước rồi giữ Stock sau; cần có luồng cancel/void phù hợp nếu bước sau thất bại. Thứ tự cụ thể phụ thuộc business contract, không có một thứ tự chung đúng cho mọi hệ.

### 7.3. Cẩn trọng với logging/metrics trong callback

Ghi log kỹ thuật mỗi attempt có thể hữu ích nhưng không được đếm thành **số booking đã tạo**. Callback chạy ba lần không đồng nghĩa ba transaction đã commit. Phân biệt `attempts_started`, `attempts_aborted`, `committed_commands` và `external_effects`.

## 8. Mẫu Java: retry runner với boundary rõ

Để tách khỏi một driver cụ thể, xem một contract mẫu:

~~~java
public record ReserveCommand(
    String commandId,
    String tenantId,
    String sku,
    int quantity
) {}

public record ReservationResult(
    String reservationId,
    boolean reserved,
    String reason
) {}

public interface TxContext {
    InventorySnapshot readInventory(String tenantId, String sku);
    void changeInventory(String tenantId, String sku, int delta);
    void insertReservation(String reservationId, ReserveCommand command);
    void insertOutbox(String eventId, String type, String reservationId);
}

public record InventorySnapshot(int available, long version) {}

@FunctionalInterface
public interface TxWork<T> {
    T execute(TxContext tx);
}

public interface TransactionRunner {
    // Phải begin, commit/abort và phân loại kết quả theo DB thật.
    <T> T runOneAttempt(TxWork<T> work);
}
~~~

Các interface là **mã khung để giảng giải**, chưa phải adapter chạy được. Implementation phải thực hiện những thao tác liên quan trong một transaction thật; một method tên `runOneAttempt` không tự tạo atomicity.

### 8.1. Các exception phân biệt outcome

~~~java
public class KnownRetryableAbort extends RuntimeException {
    public KnownRetryableAbort(Throwable cause) {
        super(cause);
    }
}

public class UnknownCommitOutcome extends RuntimeException {
    public UnknownCommitOutcome(Throwable cause) {
        super(cause);
    }
}

public class BusinessRejection extends RuntimeException {
    public BusinessRejection(String message) {
        super(message);
    }
}
~~~

Các lớp trên là abstraction ở application, **không phải tên exception của một sản phẩm**. Adapter cần ánh xạ error codes/labels của sản phẩm một cách chính xác.

### 8.2. Logic retry toàn work unit

~~~java
public final class ReservationService {
    private final TransactionRunner runner;
    private final CommitResolver resolver;
    private final Backoff backoff;

    public ReservationService(
        TransactionRunner runner,
        CommitResolver resolver,
        Backoff backoff
    ) {
        this.runner = runner;
        this.resolver = resolver;
        this.backoff = backoff;
    }

    public ReservationResult reserve(ReserveCommand command) {
        if (command.quantity() <= 0) {
            throw new IllegalArgumentException("quantity must be positive");
        }

        final String reservationId = command.commandId();
        final String eventId = "reservation:" + command.commandId();
        final int maxAttempts = 5;

        for (int attempt = 1; attempt <= maxAttempts; attempt++) {
            try {
                return runner.runOneAttempt(tx -> {
                    // Mọi dữ liệu quyết định ghi được đọc lại ở mỗi attempt.
                    InventorySnapshot stock =
                        tx.readInventory(command.tenantId(), command.sku());

                    if (stock.available() < command.quantity()) {
                        throw new BusinessRejection("INSUFFICIENT_STOCK");
                    }

                    tx.changeInventory(
                        command.tenantId(),
                        command.sku(),
                        -command.quantity()
                    );
                    tx.insertReservation(reservationId, command);
                    tx.insertOutbox(
                        eventId, "ReservationCreated", reservationId
                    );

                    return new ReservationResult(
                        reservationId, true, "RESERVED"
                    );
                });
            } catch (KnownRetryableAbort ex) {
                if (attempt == maxAttempts) {
                    throw ex;
                }
                backoff.beforeNextAttempt(attempt);
            } catch (UnknownCommitOutcome ex) {
                // Tuyệt đối không suy ra transaction đã abort.
                return resolver.resolveOrReportPending(command.commandId());
            }
        }

        throw new IllegalStateException("unreachable");
    }
}

public interface CommitResolver {
    ReservationResult resolveOrReportPending(String commandId);
}

public interface Backoff {
    void beforeNextAttempt(int attempt);
}
~~~

**Những điều ví dụ cố tình không giấu:**

- `runOneAttempt` phải có atomicity và isolation phù hợp cho read–check–write, không chỉ gọi ba repository rời rạc.
- Nếu `BusinessRejection` được ném trong transaction, adapter phải abort đúng cách và không biến thành lỗi retryable.
- `insertReservation`/`insertOutbox` phải có uniqueness/idempotency theo `commandId` trong cùng atomic boundary.
- Nếu một lần gửi lại cùng `commandId` sau successful commit, cần **tra cứu kết quả đã lưu trước khi bắt đầu một transaction tạo reservation mới**; ví dụ tập trung vào transient abort, không thay thế hệ thống dedupe đầy đủ.
- Trên một số isolation mode, việc đọc stock rồi thay đổi theo giá trị cũ chưa bảo vệ oversell nếu không có conflict detection hoặc atomic predicate; implementation phải bảo vệ invariant này tại storage.
- `resolveOrReportPending` phải trả một kết quả xác minh được hoặc trạng thái PENDING rõ ràng, **không được tự tuyên bố RESERVED** khi chưa đối soát.
- Retry budget cũng nên có giới hạn tổng thời gian và cancellation; mẫu cố tình giản lược phần đó.

### 8.3. Vì sao vòng lặp đặt ngoài transaction?

Mỗi iteration phải gọi **một transaction attempt mới**. Nếu chỉ loop lại `tx.changeInventory` bên trong một transaction đã bị abort hoặc bị đánh dấu rollback-only, driver có thể không còn cho phép commit. Nhiều SDK cung cấp helper retry callback; khi dùng helper đó, không cần thêm một vòng retry trùng lặp thiếu kiểm soát ở ngoài.

## 9. Retry nội bộ SDK và retry ở ứng dụng

Có ba lớp retry dễ bị chồng lên nhau:

~~~text
HTTP client retry
    -> Application retry
        -> Database SDK transaction retry
            -> Driver/network retry
~~~

Nếu mỗi lớp thử tối đa 5 lần mà không phối hợp, một business command có thể tạo **rất nhiều attempt**, làm tải và tail latency tăng vọt.

### 9.1. Chọn một nơi quản lý retry transaction

Nếu SDK có helper chạy lại toàn callback theo documented error categories, application nên hiểu giới hạn helper và không viết thêm vòng lặp mù. Nếu SDK chỉ trả lỗi và không tự retry transaction, application có thể tự triển khai bounded retry với adapter phân loại lỗi.

### 9.2. Outer request retry vẫn cần idempotency

Ngay cả khi SDK retry đúng, HTTP client có thể gửi lại cùng request sau vài giây vì không nhận response. `commandId` phải bền và được kiểm tra theo business scope, không chỉ gắn với một invocation callback.

### 9.3. Cancellation/deadline phải truyền xuống

Nếu client đã hủy request hoặc overall deadline hết, hệ không nên tạo retry mới vô hạn. Nhưng cần phân biệt việc không mở attempt mới với những transaction đã commit hoặc external workflow đang chờ đối soát.

## 10. Backoff, jitter và retry storm

Khi nhiều giao dịch cạnh tranh trên một hot key, retry ngay lập tức có thể làm xung đột nghiêm trọng hơn.

Giả sử 500 request cùng đọc Inventory version 10:

~~~text
500 attempts read version 10.
1 attempt commits version 11.
499 attempts conflict.

Nếu 499 attempt retry ngay:
    tất cả lại có thể đọc version 11
    1 commit version 12
    498 conflict...
~~~

Đây là **retry storm**. Không thể giải quyết chỉ bằng tăng maxAttempts.

### 10.1. Exponential backoff

Một công thức khái niệm:

\[
\operatorname{cap}(n)=\min(\operatorname{maxDelay}, \operatorname{baseDelay}\times 2^{n-1})
\]

Nếu thử lại lần thứ n, delay tăng dần tới maxDelay. Nhưng các client vẫn có thể đồng bộ cùng nhịp nếu không có jitter.

### 10.2. Full jitter

~~~text
upper = min(maxDelay, baseDelay * 2^(attempt - 1))
delay = random duration in [0, upper]
~~~

Đây là một chiến lược phổ biến, không phải luật bắt buộc. Hệ có thể chọn equal jitter, decorrelated jitter hoặc scheduler khác. Quan trọng là **tránh nhiều retry cùng một thời điểm**, giới hạn tổng thời gian và phù hợp với latency SLO.

### 10.3. Retry chỉ khi có khả năng tiến triển

Nếu `INSUFFICIENT_STOCK`, `ORDER_ALREADY_CANCELED` hoặc `VALIDATION_FAILED` là trạng thái ổn định, backoff không biến command thành hợp lệ. Nếu contention rất cao, queue theo key, single writer, quota reservation hoặc admission control có thể hiệu quả hơn OCC với retry.

### 10.4. Respect server-side signals

Nếu API cung cấp retry-after/rate-limit hint có nghĩa rõ, có thể dùng nó theo tài liệu. Nhưng không để các hint vượt tổng deadline hoặc làm server thread/connection bị giữ không cần thiết.

## 11. Retry không được phá invariant nghiệp vụ

Retry được xem là an toàn chỉ khi:

- **Các bước quyết định của mỗi attempt dựa trên state hiện tại** và nằm trong phạm vi bảo vệ.
- Có **bằng chứng attempt trước đã abort** trước khi tạo attempt mới, hoặc có idempotency để xử lý outcome chưa rõ.
- Command không được đổi ý định nếu chưa có xác nhận người dùng.
- Các side effect ngoài transaction được tách ra và idempotent.
- Mỗi lần thử có thể rollback/abort theo semantics của sản phẩm.
- Lỗi nghiệp vụ được trả riêng, không retry mù.

### 11.1. Không tự tăng giá đã được khách đồng ý

Một Booking được khách duyệt giá 100. Khi retry, DB cho biết giá là 120. Hệ không nên âm thầm đổi tổng sang 120 rồi charge. Transaction attempt mới cần kiểm tra `agreedPrice=100` vẫn hợp lệ hoặc trả `PRICE_CHANGED` để khách xác nhận lại.

### 11.2. Conditional state transition

Nếu retry `ConfirmOrder` sau khi Order đã thành `CANCELED`, không được tiếp tục ép status `CONFIRMED`. Phải đọc state mới hoặc dùng condition `status=PENDING AND version=expected`.

### 11.3. Uniqueness và duplicate command

Nếu `OrderId` duy nhất mà retry insert nhận duplicate key, cần phân biệt:

- **Đơn đã được tạo bởi cùng commandId:** trả lại kết quả cũ.
- **Key đã bị dùng bởi command khác:** trả conflict/duplicate đúng nghĩa.

Không tự coi mọi duplicate key là transaction đã thành công; cũng không đổi sang một ID mới rồi tạo hai đơn từ cùng ý định.

## 12. Phân biệt conflict trong transaction với conflict giữa các aggregate

Một database có thể transaction nhiều item trong cùng partition; nhưng Order và Inventory có thể nằm ở hai service khác nhau.

~~~mermaid
flowchart LR
    API["Checkout command"] --> O["Order DB transaction"]
    API --> I["Inventory DB transaction"]
    API --> P["Payment gateway"]
~~~

Hai transaction cục bộ **không tự là một transaction toàn workflow**. Nếu Order đã commit nhưng Inventory chưa, retry toàn **Order transaction** không tự rollback Inventory hoặc Payment.

Khi không có atomic boundary chung:

- Định nghĩa **saga state** bền.
- Mỗi bước cục bộ bảo vệ invariant bằng CAS/transaction của nguồn đó.
- Retry mỗi bước theo **idempotency key** tương ứng.
- Dùng compensation khi bước sau không thành công.
- Theo dõi trạng thái kẹt và đối soát.

### 12.1. Saga retry khác transaction retry

| Thuộc tính | Retry transaction đã abort | Retry bước saga |
|---|---|---|
| Phạm vi | Một atomic DB transaction | Một hoặc nhiều local action |
| Thay đổi từ attempt cũ | Được rollback/không commit theo contract | Bước trước có thể đã commit |
| Có phải đọc lại state? | Có, với dependent reads | Có, nhưng phải nhớ bước nào đã hoàn tất |
| Idempotency | Cần cho client retry/unknown outcome | Bắt buộc ở các bước có thể phát lại |
| Bù trừ | Thường không cần cho attempt abort nội bộ | Có thể cần refund/release |
| External side effect | Tránh trong transaction body | Xử lý bằng workflow có đối soát |

### 12.2. Compensation cũng có conflict

Một reservation đã được release trong lần bù trước đó, worker retry `ReleaseReservation` sau timeout. Nếu dùng lệnh `available += 2` không có idempotency, stock có thể bị cộng hai lần. Compensation phải có commandId/state transition được bảo vệ, không phải thao tác ngược toán học mù.

## 13. MongoDB: retry transaction và retry commit là hai điều khác nhau

MongoDB hỗ trợ multi-document transactions trên những topology được hỗ trợ. Driver/SDK có cơ chế nhận diện lỗi transaction tạm thời và kết quả commit không xác định.

Hai khái niệm rất quan trọng:

- **TransientTransactionError** có thể chỉ ra rằng attempt transaction cần được thử lại từ đầu theo hướng dẫn driver/API.
- **UnknownTransactionCommitResult** thể hiện tình huống kết quả commit chưa rõ; hướng xử lý thường liên quan **retry commit theo protocol của driver**, không được tự động chạy lại toàn body như thể transaction chắc chắn abort.

Không suy từ nhãn lỗi thành quy tắc chung cho mọi thời điểm/lệnh; phải xem đặc tả và helper của phiên bản driver đang dùng.

### 13.1. Mẫu Java dùng session transaction

~~~java
try (ClientSession session = mongoClient.startSession()) {
    session.withTransaction(() -> {
        Document stock = inventory.find(
            session, Filters.eq("_id", sku)
        ).first();

        if (stock == null || stock.getInteger("available") < qty) {
            throw new BusinessRejection("INSUFFICIENT_STOCK");
        }

        UpdateResult updated = inventory.updateOne(
            session,
            Filters.and(
                Filters.eq("_id", sku),
                Filters.gte("available", qty)
            ),
            Updates.inc("available", -qty)
        );
        if (updated.getMatchedCount() != 1) {
            throw new BusinessRejection("INSUFFICIENT_STOCK");
        }

        orders.insertOne(
            session,
            new Document("_id", stableOrderId)
                .append("sku", sku)
                .append("quantity", qty)
        );
        outbox.insertOne(
            session,
            new Document("_id", stableEventId)
                .append("type", "OrderCreated")
                .append("orderId", stableOrderId)
        );

        return stableOrderId;
    });
}
~~~

Ví dụ sử dụng ký hiệu và biến giả định (`mongoClient`, collections, qty, IDs); cần import, indexes, tenant authorization và error mapping để chạy được. Phần đáng chú ý là **mọi lệnh database tham gia cùng session** và callback có thể được SDK thực hiện lại tùy error handling.

### 13.2. Tránh side effect trong callback

Không gọi `paymentGateway.charge()` hoặc gửi email trong `withTransaction` callback. Khi SDK retry callback, các lệnh ngoài DB có thể đã thành công trước đó mà không thể rollback cùng transaction.

### 13.3. Chọn write concern/durability

Việc transaction commit thành công có mức durability nào phụ thuộc write concern/journaling/topology và protocol thực. Nếu ứng dụng cần chịu lỗi leader, không chỉ nhìn callback trả về; xác minh cấu hình và test fault model.

### 13.4. Conflict vẫn có thể biến thành business rejection

Sau retry, Inventory có thể không còn đủ hàng. Kết quả đúng là `INSUFFICIENT_STOCK`, không phải tiếp tục thử tới khi có một transaction tình cờ thành công hoặc ghi âm tồn.

## 14. DynamoDB: transaction conflicts, condition failures và idempotency

DynamoDB có các transaction API như TransactWriteItems trong phạm vi được hỗ trợ. Có thể gặp transaction cancellation vì condition không đạt, transaction conflict hoặc lỗi tài nguyên.

### 14.1. Một transaction minh họa

~~~text
TransactWriteItems:
    Update Inventory(SKU-A)
        Condition available >= 2
        SET available = available - 2

    Put Order(O-100)
        Condition key not exists

    Put Outbox(OrderCreated:O-100)
        Condition event key not exists
~~~

Nếu bị transaction conflict đã được xác định là retryable, một attempt mới phải **xét lại cả điều kiện và toàn transaction request**. Nếu condition `available >= 2` không còn đúng, đó là business rejection.

### 14.2. Client request token

Một số API transaction write hỗ trợ client request token theo phạm vi và thời gian hiệu lực được tài liệu hóa. Hãy dùng đúng semantics: token ổn định với cùng payload, tránh dùng cùng token cho payload khác, và **không coi token có thời hạn giới hạn là cơ chế business idempotency vĩnh viễn**.

### 14.3. Không tự tách transaction khi vượt giới hạn

Nếu transaction chứa nhiều item vượt action/bytes limit, không được tự chia thành hai transaction rồi vẫn báo kết quả nguyên tử. Cần đổi mô hình, giảm UoW, hoặc dùng workflow bền với trạng thái trung gian phù hợp.

### 14.4. Region scope

Một commit transaction ở region A không mặc nhiên là một transaction serializable toàn cầu với writer ở region B. Nếu invariant đòi đúng cross-region, đọc contract global tables/multi-region và cân nhắc single writer hoặc quota đã phân bổ.

## 15. Firestore: transaction callback có thể được gọi lại

Trong Cloud Firestore, transaction callback có thể được SDK retry khi document đã thay đổi theo cơ chế transaction. Điều này trực tiếp minh họa nguyên tắc **chạy lại toàn đơn vị công việc**.

~~~javascript
await runTransaction(db, async (tx) => {
  const stockSnap = await tx.get(stockRef);

  if (!stockSnap.exists()) {
    throw new Error("INVENTORY_MISSING");
  }

  const available = stockSnap.data().available;
  if (available < requestedQuantity) {
    throw new Error("INSUFFICIENT_STOCK");
  }

  tx.update(stockRef, {
    available: available - requestedQuantity
  });
  tx.set(bookingRef, {
    commandId: stableCommandId,
    quantity: requestedQuantity,
    status: "RESERVED"
  });
});
~~~

Đây là ví dụ cấu trúc sử dụng SDK; sản phẩm có các giới hạn về read-before-write, thời gian, số write/bytes và security rules. Cần đảm bảo `bookingRef` và `stableCommandId` được quản lý idempotently, không chỉ tự tạo ID mới khi callback chạy lại.

### 15.1. Không giữ snapshot của callback trước

Nếu transaction retry, lần callback mới phải đọc `stockRef` lại. Tránh lưu `available` vào biến ngoài rồi dùng lại sau conflict.

### 15.2. Không gọi side effect trong callback

Một callback chạy lại 3 lần có thể khiến analytics event, payment charge hoặc email được phát 3 lần nếu code không tách. Đừng dùng số lần callback là số transaction đã commit.

### 15.3. Transaction khác batched writes

Batch ghi nhiều document không có cùng read–modify–write callback hoặc retry semantics. Chọn đúng API dựa trên bảo đảm thật và không tự suy transaction behavior từ chữ “batch”.

## 16. Cosmos DB: retry trong đúng logical partition

Với Azure Cosmos DB for NoSQL, transactional batch/stored procedure có ranh giới **logical partition** theo API hỗ trợ. ETag/If-Match giúp phát hiện optimistic concurrency trên item.

~~~text
Transaction batch:
    Update Order O-100
    Create OrderLine O-100/I-3
    Update Order total/version

Điều kiện: các item thuộc cùng logical partition
theo partition key thực tế và API sử dụng.
~~~

### 16.1. Không mở rộng phạm vi sau conflict

Nếu OrderLine nằm ngoài logical partition, thử lại batch 10 lần không khiến nó tự trở thành transaction cross-partition. Đó là **lỗi lựa chọn phạm vi**, không phải transient conflict.

### 16.2. ETag stale khác transient throttling

If-Match thất bại có thể chỉ ra record đã thay đổi: cần đọc lại, kiểm tra command và tạo condition mới nếu hợp lệ. Throttling cần backoff/capacity handling. Không gom hai loại này vào một retry vô điều kiện.

### 16.3. Multi-region cần contract riêng

Một transaction trong logical partition tại một region không tự bảo vệ một invariant nếu các region khác có writer và reconciliation theo semantics khác. Kiểm thử topology thực, không chỉ localhost emulator.

## 17. Couchbase: các attempt và transaction cleanup

Couchbase SDK transaction có những cơ chế theo dõi attempt, staging, commit và cleanup riêng. Với retry callback:

- Mọi dependent read/modify/write phải chạy lại trong attempt mới.
- Không mang staged transaction state của attempt trước sang attempt mới.
- Không gọi external side effect không idempotent trong callback.
- Không coi timeout là abort chắc chắn nếu commit outcome còn không rõ.
- Xem tài liệu về timeout, durability, cleanup và phản hồi lỗi của phiên bản SDK.

### 17.1. Test khi bị conflict

Hai transaction cùng sửa Inventory. Buộc chúng đọc cùng phiên bản; một transaction commit, transaction kia cần được retry/abort theo hợp đồng. Kiểm tra không có booking trùng hoặc stock âm sau khi mọi attempt có outcome rõ.

### 17.2. Test khi node chết giữa commit/cleanup

Staged mutation hoặc metadata dở dang cần được engine/SDK xử lý đúng protocol. Không xóa thủ công các transaction metadata vì trông giống rác; làm vậy có thể phá recovery.

## 18. Cassandra/ScyllaDB: LWT conflict và batch

Trong họ Cassandra/ScyllaDB, câu lệnh CQL `IF` có thể dùng lightweight transaction (LWT) trong phạm vi hỗ trợ.

~~~sql
UPDATE inventory
SET available = 3,
    version = 8
WHERE warehouse_id = 'W-1'
  AND sku = 'SKU-A'
IF version = 7;
~~~

Kết quả `[applied] = false` có thể nghĩa condition không khớp; không nên retry y nguyên lệnh mãi. Phải đọc phiên bản hiện tại và đánh giá command theo invariant.

### 18.1. LWT không thay thế transaction tùy ý xuyên partition

Một logged batch hoặc một loạt LWT trên các partition khác nhau **không mặc nhiên là một transaction serializable toàn bộ**. Nếu hai bản ghi cần commit cùng nhau, phải xác minh contract batch/transaction cụ thể hoặc dùng workflow/DB khác.

### 18.2. Paxos/contention

LWT có chi phí phối hợp, và nhiều writer tranh cùng partition/key có thể làm tăng latency. Retry có jitter và giới hạn có thể giúp tải ổn định; hot key lớn vẫn có thể cần queue/quota.

### 18.3. Timeout không chứng minh LWT chưa commit

Nếu response bị mất, cần đọc state hoặc dùng command identity để biết mutation có được áp dụng không, thay vì gửi lệnh có hiệu ứng mới tùy tiện.

## 19. Redis: WATCH/MULTI/EXEC và retry toàn logic

Redis hỗ trợ pattern OCC với `WATCH`:

~~~text
WATCH inventory:SKU-A
available = GET inventory:SKU-A

if available < requested:
    UNWATCH
    return INSUFFICIENT

MULTI
DECRBY inventory:SKU-A requested
EXEC
~~~

Nếu một key được WATCH đã thay đổi, EXEC có thể không thực hiện transaction. Client cần:

~~~text
1. WATCH lại.
2. GET current value lại.
3. Kiểm tra available >= requested lại.
4. MULTI/EXEC lại.
~~~

Chỉ gọi `EXEC` thêm lần nữa mà không thực hiện lại read/check là không đúng mô hình OCC.

### 19.1. Không nhầm EXEC abort với runtime error

Redis MULTI/EXEC có semantics riêng: một lỗi runtime của command trong EXEC không tương đương việc tự rollback tất cả command đã chạy như transaction SQL. Cần kiểm tra kỹ tài liệu và không dựa vào tính năng này để chứng minh một group invariant mà nó không bảo vệ.

### 19.2. Script nguyên tử vẫn cần idempotency

Một Lua script kiểm tra rồi trừ tồn có thể nguyên tử trong phạm vi Redis, nhưng nếu response mất sau khi đã trừ, retry không có reservationId có thể trừ tiếp. Atomicity không tự tạo exactly-once business processing.

### 19.3. Cluster và durability

Nếu nhiều key thuộc các hash slot khác nhau, phạm vi multi-key operation cần được xác minh theo Redis Cluster. Persistence AOF/RDB và failover có durability semantics riêng, không thể suy từ `EXEC` thành công rằng ghi đã ở một quorum bền.

## 20. Transactional key–value: retry conflicts trên read/write set

Một số hệ như FoundationDB cung cấp giao dịch nhiều key/range với optimistic conflict detection và retry API riêng. Ý tưởng có thể là:

~~~text
retryLoop:
    begin transaction
    read keys/ranges needed for invariant
    compute candidate writes
    attempt commit
    on documented retryable conflict:
        follow SDK retry policy
        re-execute all reads and writes in new attempt
~~~

Khi dùng helper retry, phải xem semantics **read/write conflict ranges**, timeout, giới hạn số bytes và các hành vi khi không xác định commit outcome. Không sao chép một retry policy từ MongoDB hay Firestore sang một transactional KV khác.

## 21. Tính idempotent phải được thiết kế theo command, không theo attempt

### 21.1. Một command có nhiều transaction attempt

~~~text
commandId = reserve-9001

Attempt 1: conflict, rollback
Attempt 2: conflict, rollback
Attempt 3: commit reservation
HTTP response: timeout
Attempt 4? Không được tự giả định chưa commit.
~~~

Application cần tra commandId để biết reservation đã tồn tại. Nếu transaction source lưu `reservationId=reserve-9001` cùng trừ tồn trong một atomic boundary, retry của cùng command có thể trả kết quả cũ.

### 21.2. At-least-once delivery là tình huống bình thường

HTTP client, message broker hoặc workflow engine có thể gửi lại cùng command. Vì vậy transaction retry logic phải là một phần của **hệ thống idempotent**, không chỉ một đoạn catch exception.

### 21.3. Token SDK và ID nghiệp vụ khác nhau

Một SDK có transaction token chỉ hiệu lực trong một khoảng thời gian hoặc một invocation. Business commandId cần tồn tại đủ lâu theo nghiệp vụ để chống duplicate xuyên client restart, worker replay, network timeout và những lần gọi khác nhau.

### 21.4. Định nghĩa kết quả khi command đã xử lý

Nếu cùng commandId và cùng payload:

~~~text
return prior committed result
~~~

Nếu cùng commandId nhưng payload khác:

~~~text
reject as idempotency key reused inconsistently
~~~

Nếu command đang xử lý:

~~~text
return IN_PROGRESS / retry-later according to API contract
~~~

Không dùng cùng idempotency key cho hai ý định khác nhau chỉ vì cùng user hoặc cùng SKU.

## 22. Transaction retry và outbox

Giả sử tạo Order và Outbox trong transaction:

~~~text
BEGIN
  INSERT Order(O-100)
  INSERT Outbox(
      eventId = OrderCreated:O-100,
      type = OrderCreated
  )
COMMIT
~~~

Nếu attempt conflict và abort, **cả Order và Outbox của attempt đó đều không được commit** theo đúng atomic scope. Callback retry sẽ thực hiện lại cả hai lệnh.

Sau successful commit, publisher đọc Outbox và gửi event. Nếu publisher chết sau publish nhưng trước khi đánh dấu đã gửi, nó có thể phát lại event. Consumer cần dedupe theo eventId/aggregate version.

### 22.1. Event ID ổn định qua các attempt

Nếu mỗi attempt tạo event ID ngẫu nhiên mới rồi commit outcome không rõ, request retry có thể tạo event logic trùng. Một event ID gắn với `commandId` và `eventType` giúp dedupe, nhưng vẫn cần uniqueness trong nguồn và quy trình xử lý version/ordering.

### 22.2. Outbox phải ở cùng transaction scope

Nếu Order và Outbox nằm ở hai partition trong DB chỉ hỗ trợ single-partition transaction, dù code chạy cả hai lệnh trong cùng một function, invariant “Order commit thì Outbox có” vẫn chưa được bảo vệ. Không retry mạnh hơn để sửa một **lỗ hổng phạm vi**.

### 22.3. Không “publish rồi commit”

Nếu gửi event ra broker trước khi DB commit, consumer có thể thấy OrderCreated rồi Order transaction abort. Nếu commit trước rồi publish ngoài transaction, worker chết có thể làm mất event. Outbox hoặc CDC có contract phù hợp giúp xử lý dual-write problem.

## 23. Chuyển tiền: phân biệt toàn UoW và unknown outcome

Giả sử:

~~~text
Account A = 200
Account B = 100
Transfer T-100: 50 từ A sang B.
~~~

Một transaction được thiết kế:

~~~text
BEGIN
  ASSERT Transfer(T-100) chưa commit
  ASSERT A.balance >= 50
  UPDATE A.balance -= 50
  UPDATE B.balance += 50
  INSERT Ledger(T-100, A, B, 50)
COMMIT
~~~

### 23.1. Conflict trên Account A

Một transfer khác trừ A trước. Nếu transaction T-100 bị abort, retry **không được chỉ cộng 50 vào B**. Phải bắt đầu từ việc đọc A/B/ledger hoặc sử dụng predicate nguyên tử theo isolation đã thiết kế, và commit cả nhóm khi đủ điều kiện.

### 23.2. Unknown commit khi ACK mất

Nếu transaction T-100 đã commit nhưng response mất, gọi lại cùng transfer với **transferId mới** là rủi ro chuyển tiền hai lần. Phải đối soát T-100 bằng stable ID và chỉ tiếp tục khi biết trạng thái.

### 23.3. Cross-service transfer

Nếu A/B nằm ở hai service không có transaction chung, không thể chuyển toàn UoW thành transaction DB bằng cách đặt vòng retry quanh hai HTTP call. Cần ledger/protocol nghiệp vụ bền, idempotency, settlement và reconciliation thích hợp.

### 23.4. Precision của tiền

Dùng integer minor units hoặc decimal theo contract, không dùng floating-point tùy tiện. Retry đúng nhưng làm tròn sai vẫn có thể phá invariant.

## 24. Case study đặt vé và giữ chỗ

Một hệ vé sự kiện có:

~~~text
Seat(seatId, status, version)
Booking(bookingId, seatId, customerId, price)
Coupon(code, remainingUsage)
Outbox(eventId, type, bookingId)
~~~

Command:

~~~json
{
  "commandId": "booking-9001",
  "customerId": "C-12",
  "seatId": "A1",
  "coupon": "SAVE10",
  "agreedMaxTotal": 100
}
~~~

### 24.1. Transaction attempt

~~~text
1. Read Seat A1, price and Coupon.
2. Check Seat available and Coupon remainingUsage > 0.
3. Calculate total, ensure total <= agreedMaxTotal.
4. Change Seat to HELD with concurrency protection.
5. Decrement Coupon usage atomically.
6. Insert Booking(commandId).
7. Insert Outbox(eventId derived from commandId).
8. Commit.
~~~

Điều kiện “coupon còn lượt” cũng phải được bảo vệ ở commit, không chỉ đọc rồi trừ từ snapshot cũ.

### 24.2. Nếu attempt 1 bị abort

Attempt 2 đọc lại Seat và Coupon. Có thể Seat đã bị giữ; khi đó trả `SEAT_UNAVAILABLE`. Có thể coupon hết lượt; trả `COUPON_EXHAUSTED`. Không cố giữ Booking có coupon không còn hợp lệ.

### 24.3. Nếu commit chưa rõ

Tra `commandId=booking-9001` ở nguồn có thẩm quyền. Nếu Booking đã tồn tại và mọi invariant được commit, trả bookingId cũ. Nếu chưa thể khẳng định, báo trạng thái đang xác minh; đừng tạo booking mới bằng ID khác.

### 24.4. Nếu nghiệp vụ vượt transaction scope

Seat có thể ở một partition, Coupon ở partition khác và Booking ở dịch vụ riêng. Nếu DB không hỗ trợ một transaction chung, cần cơ chế reserve seat/coupon có idempotency, deadline và compensation. Không thể kỳ vọng retry transaction của Booking bảo vệ Coupon ở hệ khác.

## 25. Kiểm thử: chứng minh retry toàn đơn vị công việc

Test happy path chỉ xác nhận một lần commit thuận lợi. Cần tạo xung đột có kiểm soát.

### 25.1. Hai writer trên cùng version

~~~text
Initial Order version = 7.

T1 reads v7.
T2 reads v7.
T1 commits v8.
T2 attempts commit using v7 -> conflict.
~~~

Kỳ vọng:

- Không có lost update âm thầm.
- Attempt T2 được abort hoặc condition failed theo contract.
- Nếu T2 retry, nó đọc lại version hiện tại và đánh giá lại command.
- Không áp lại thay đổi dẫn xuất từ v7 mà bỏ qua v8.

### 25.2. Test retry toàn transaction chứ không phải một write

Thiết lập hai record A/B và một invariant:

~~~text
Total = A + B.
T1 đọc A, B và tính một thay đổi cho cả hai.
T2 thay A trước khi T1 commit.
T1 bị abort, retry.
~~~

Quan sát retry attempt phải **đọc A và B lại** và tính lại các giá trị liên quan. Dùng transaction tracing/test hooks nếu SDK cung cấp; chỉ nhìn kết quả cuối có thể chưa cho biết callback đã thật sự được chạy lại.

### 25.3. Test write skew

Hai bác sĩ cùng trực:

~~~text
T1 reads A=true, B=true -> update A=false.
T2 reads A=true, B=true -> update B=false.
~~~

Nếu invariant cần “ít nhất một bác sĩ trực”, một transaction serializable đúng phạm vi có thể abort một transaction. Nhưng dưới snapshot isolation chỉ bảo vệ write–write conflict, hai transaction ghi hai record khác nhau có thể cùng commit; retry không sửa một **hợp đồng isolation không đủ**. Test phải đối chiếu đúng mức isolation DB hứa.

### 25.4. Test commit outcome chưa rõ

Chèn lỗi network sau khi DB đã commit nhưng trước khi client nhận ACK. Kỳ vọng application **đối soát bằng commandId** hoặc tiếp tục protocol commit hợp lệ, không tạo một command thứ hai.

### 25.5. Test callback side effect

Tạo conflict khiến transaction callback được thử lại, rồi xác minh **không có payment/email trực tiếp trong callback**. Đo số attempt và số event/charge đã commit riêng.

### 25.6. Test duplicate request

Gửi đồng thời hai request cùng commandId. Kỳ vọng một kết quả nghiệp vụ duy nhất và response nhất quán hoặc một request nhận `IN_PROGRESS`. Hai commandId khác nhau vẫn phải cạnh tranh theo invariant stock/uniqueness.

### 25.7. Test hot key

Cho 2.000 request tranh 100 đơn vị hàng; đo số committed reservations không vượt 100, attempt/retry distribution, p95/p99, throttling, và thời gian hoàn thành. Không chỉ kiểm tra 100 request được chấp nhận; cần kiểm tra 1.900 request còn lại được phân loại đúng.

### 25.8. Test deadline

Cho transaction conflict liên tục. Đảm bảo retry dừng trong budget đã thiết kế, trả lỗi hoặc trạng thái phù hợp, không treo request vô hạn.

## 26. Kiểm thử fault injection và failover

Xung đột logic và lỗi hạ tầng có thể xuất hiện cùng lúc. Một suite nên bao gồm:

| Fault | Kỳ vọng cần kiểm tra |
|---|---|
| Process chết trước commit | Attempt chưa commit không tạo partial state |
| Mất response ngay sau commit | Unknown outcome được đối soát, không duplicate |
| Leader failover sau ACK | Dữ liệu giữ theo durability contract đã chọn |
| Replica đọc trễ | Phép đọc kiểm chứng dùng đúng consistency |
| Partition mạng | Retry/backoff tuân thủ availability/consistency contract |
| Throttling | Không tạo retry storm hoặc vượt deadline |
| Disk full/transaction too large | Lỗi được phân loại, không retry như conflict |
| Message broker phát lại | Consumer idempotent |
| Worker saga chết giữa bước | Workflow phục hồi và bù trừ |
| Multi-region simultaneous writers | Không giả định CAS cục bộ bảo vệ invariant toàn cầu |

### 26.1. Không diễn giải timeout thành abort

Test giả lập response bị mất **sau successful commit** là khác với cố làm database abort transaction trước commit. Hai trường hợp phải có expected outcomes khác nhau.

### 26.2. Process kill không phải power failure

Khi kill process, OS page cache có thể còn. Nếu muốn kiểm tra durability khi mất điện, cần một fault model phù hợp và môi trường được cấp quyền. Không tuyên bố “không mất dữ liệu khi mất điện” từ bài test kill service.

### 26.3. Test trên topology phù hợp

Một local emulator hoặc single-node test không chứng minh behavior của sharded cluster, replica set hoặc multi-region. Ghi version, SDK, configuration, write concern/read concern, region topology và fault type cho mọi báo cáo.

### 26.4. Không phá production tùy tiện

Các bài test kill node, chặn network, full disk hoặc failover nên thực hiện trên môi trường thử nghiệm cô lập và có quyền. Test có dữ liệu giả, giới hạn tài nguyên, cleanup và cách dừng khi ảnh hưởng vượt ngưỡng.

## 27. Test harness Java dùng barrier cho xung đột

Một ví dụ JUnit 5 để ép hai command chạy gần nhau:

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.util.concurrent.*;
import org.junit.jupiter.api.Test;

class ReservationConcurrencyTest {

    private final ReservationTestAdapter adapter =
        TestEnvironment.reservationAdapter();

    @Test
    void concurrentReservationsMustNotOversell() throws Exception {
        adapter.resetStock("SKU-RACE", 5);

        CountDownLatch ready = new CountDownLatch(2);
        CountDownLatch start = new CountDownLatch(1);
        ExecutorService pool = Executors.newFixedThreadPool(2);

        Callable<ReservationOutcome> first = () -> {
            ready.countDown();
            start.await();
            return adapter.reserve("SKU-RACE", "R-A", 4);
        };
        Callable<ReservationOutcome> second = () -> {
            ready.countDown();
            start.await();
            return adapter.reserve("SKU-RACE", "R-B", 3);
        };

        try {
            Future<ReservationOutcome> a = pool.submit(first);
            Future<ReservationOutcome> b = pool.submit(second);

            assertTrue(ready.await(5, TimeUnit.SECONDS));
            start.countDown();

            ReservationOutcome oa = a.get(15, TimeUnit.SECONDS);
            ReservationOutcome ob = b.get(15, TimeUnit.SECONDS);

            // UNKNOWN phải được đối soát trước khi kết luận.
            assertNotEquals(ReservationOutcome.UNKNOWN, oa);
            assertNotEquals(ReservationOutcome.UNKNOWN, ob);

            assertEquals(
                1,
                (oa == ReservationOutcome.RESERVED ? 1 : 0)
                + (ob == ReservationOutcome.RESERVED ? 1 : 0)
            );
            assertEquals(5, adapter.reservedTotal("SKU-RACE")
                + adapter.available("SKU-RACE"));
        } finally {
            pool.shutdownNow();
        }
    }
}

enum ReservationOutcome {
    RESERVED, INSUFFICIENT, UNKNOWN
}

interface ReservationTestAdapter {
    void resetStock(String sku, int available);
    ReservationOutcome reserve(String sku, String commandId, int quantity);
    int reservedTotal(String sku);
    int available(String sku);
}
~~~

`TestEnvironment` là fixture giả định do nhóm cung cấp. Test chỉ có ý nghĩa khi adapter kết nối thật tới DB/topology mục tiêu, có unique IDs, cleanup cô lập và cách đọc nguồn có thẩm quyền.

### 27.1. Barrier không đảm bảo conflict thực sự xảy ra

Latch đồng bộ lúc bắt đầu, nhưng thread scheduling/network có thể khiến lệnh thực tế chạy tuần tự. Nếu muốn chứng minh logic retry sau conflict, dùng test hook ở thời điểm read snapshot hoặc fault injector/adapter trả **known abort** có kiểm soát. Đừng chỉ tuyên bố đã test conflict vì dùng hai thread.

### 27.2. Không đặt barrier sai trong SDK auto-retry

Một callback có thể chạy lại nhưng thread còn lại đã rời barrier; nếu code luôn chờ barrier trong mọi retry attempt, test có thể deadlock giả. Dùng barrier cho lần thử đầu hoặc có control flow điều chỉnh theo attempt.

### 27.3. Kết quả cần đọc lại ở nguồn

Sau mọi attempt/timeout, đọc record từ nguồn có thẩm quyền theo consistency phù hợp và xác minh invariant. Một response của client không đủ để kết luận toàn bộ hệ đã đúng.

## 28. Quan sát production: số lần thử không phải số giao dịch commit

Một bộ metric hữu ích:

| Metric | Câu hỏi |
|---|---|
| Transaction attempts started | Một command trung bình cần bao nhiêu attempt? |
| Known retryable aborts | Những conflict nào được thử lại? |
| Business precondition failures | Từ chối nghiệp vụ có bị retry mù không? |
| Commit successes | Bao nhiêu command có commit xác nhận? |
| Unknown commit results | Bao nhiêu outcome cần đối soát? |
| Reconciliation duration | Đối soát mất bao lâu? |
| Retry count distribution | p50/p95/p99 attempts trên một command |
| Backoff total time | Retry ảnh hưởng latency bao nhiêu? |
| Transaction p95/p99 | Thời gian attempt hoặc toàn command |
| Hot key/partition contention | Key nào gây conflict nhiều nhất? |
| Duplicate commands prevented | Dedupe hoạt động ra sao? |
| Outbox/consumer lag | Event downstream chậm bao lâu? |
| Saga compensation backlog | Có bước bù đang kẹt không? |
| Invariant violations | Oversell, duplicate Order, negative balance |

### 28.1. Correlation ID và attempt ID

Một cấu trúc tracing:

~~~text
commandId = checkout-7281
traceId = trace-401

attempt=1:
    txId=tx-a, outcome=KNOWN_CONFLICT

attempt=2:
    txId=tx-b, outcome=COMMIT_UNKNOWN

reconciliation:
    commandId=checkout-7281, result=COMMITTED
~~~

Giữ `commandId` ổn định và ghi `attemptId` riêng giúp tìm nguyên nhân timeout/retry. Không log token, payment details hoặc payload nhạy cảm không cần thiết.

### 28.2. Tỷ lệ conflict cao có thể là vấn đề data model

Nếu mọi request của flash sale cùng sửa một stock document, tăng maxAttempts có thể làm hệ tệ hơn. Cân nhắc:

- Atomic conditional decrement thay read–modify–write không cần thiết.
- Single writer/queue theo key.
- Quota cấp trước cho các shard có kiểm soát tổng.
- Rate limit/admission control.
- Tách aggregate khi bất biến cho phép.

### 28.3. Quan sát đúng tỉ lệ thành công

Không nên báo “99% transaction thành công” nếu mỗi command có 20 attempt và 19 attempt bị conflict. Cần cả **attempt success rate** và **business command completion rate**, cùng latency end-to-end.

## 29. Những sai lầm phổ biến

### “Một câu lệnh lỗi thì chỉ retry câu đó”

Sai khi câu lệnh dựa trên state đã đọc ở đầu transaction. Phải chạy lại toàn logic phụ thuộc trong một transaction mới.

### “Đã mở transaction nên có thể dùng giá trị cache cũ sau conflict”

Không. State thay đổi và bất biến cần được đánh giá lại từ nguồn có thẩm quyền.

### “Transaction abort là lỗi nghiêm trọng của database”

Không nhất thiết. Một số conflict abort là hành vi dự kiến để giữ isolation.

### “Serialization failure giống business rule không đạt”

Không. Một bên là xung đột theo lịch chạy có thể retry, bên kia có thể là từ chối nghiệp vụ ổn định.

### “Commit timeout tức transaction đã rollback”

Không. Commit có thể thành công nhưng client mất ACK.

### “Gặp unknown commit cứ chạy lại body từ đầu”

Nguy hiểm nếu cùng command đã commit. Cần đối soát hoặc tiếp tục protocol commit theo tài liệu.

### “Callback transaction chỉ chạy một lần”

Nhiều SDK có thể tự retry; không gọi email/gateway không idempotent bên trong callback.

### “Có CAS thì request retry không trừ kho hai lần”

CAS phát hiện stale version, không tự nhận diện cùng command đã thực hiện trước đó. Cần reservationId/idempotency.

### “Retry nhiều sẽ giải quyết thiếu tồn kho”

Không. Business precondition failed không nhất thiết thay đổi chỉ nhờ chờ.

### “Cứ tăng maxAttempts là throughput tốt hơn”

Hot key có thể tạo retry storm và tăng p99. Cần backoff/jitter và điều tiết tải.

### “Saga retry giống transaction retry”

Không. Trong saga, các bước trước có thể đã commit và cần compensation/idempotency.

### “Snapshot isolation luôn ngăn write skew”

Không. Retry không thể vá một isolation contract không bảo vệ invariant cần thiết.

### “Logged batch trong wide-column là transaction cross-partition”

Không thể mặc định. Phải đọc đúng atomicity/isolation của sản phẩm.

### “Ghi Order và Outbox trong một method là transactional”

Chỉ khi cả hai thuộc một atomic boundary được DB hỗ trợ.

### “Test hai thread là đã ép được race”

Không. Cần quan sát lịch đọc/ghi hoặc điều khiển conflict trong harness.

### “Một read replica thấy nửa state tức transaction source đã hỏng”

Chưa chắc. Phải kiểm tra read consistency và nguồn có thẩm quyền.

### “Khởi động transaction mới sau failover nghĩa là command cũ chưa commit”

Không. Failover và mất response có thể để lại outcome chưa xác định.

## 30. Checklist thiết kế retry cho một UoW

| Câu hỏi | Quyết định |
|---|---|
| Business command là gì? | Tên command, ID, immutable intent |
| Bất biến nào cần đúng? | Stock, trạng thái, unique key, ledger |
| Atomic boundary ở đâu? | Item/partition/multi-item/cluster |
| Isolation có đủ không? | Write conflict, write skew, phantom |
| Những dependent reads là gì? | Phải đọc lại khi retry |
| SDK có auto-retry callback không? | Ai sở hữu retry loop |
| Lỗi nào cho biết abort chắc chắn? | Mã/label chính thức của sản phẩm |
| Lỗi nào là business rejection? | Không retry mù |
| Commit outcome có thể UNKNOWN không? | Reconciliation/commit retry protocol |
| Dedupe theo gì? | commandId/reservationId/eventId |
| Side effect nào nằm ngoài DB? | Outbox/idempotent workflow |
| Retry budget bao nhiêu? | Attempts, elapsed time, per-attempt timeout |
| Backoff thế nào? | Jitter, maxDelay, retry-after |
| Phân loại và metric? | Conflict, unknown, business failures |
| Hot key có thể quá tải không? | Queue/quota/admission control |
| Test nào bắt được lỗi? | Barrier, fault injection, idempotency |
| Multi-region có writer không? | Contract replication/consistency |

### 30.1. Một quyết định mẫu

~~~text
Use case: Reserve ticket seat
Business commandId: booking-9001 (stable across retries)
Atomic owner: Seat + Booking + Outbox in supported transaction scope
Preconditions: Seat AVAILABLE; quote within agreed price
Retryable: confirmed serialization abort / documented write conflict
Nonretryable: seat unavailable; invalid coupon; forbidden
Unknown commit: query booking by commandId, or follow SDK commit protocol
External effects: payment and email outside callback
Backoff: bounded exponential with jitter
Overall budget: fixed per API SLO
Monitoring: conflicts per seat, attempts, p99, unresolved commits
Tests: two customers same seat; commit ACK lost; callback rerun
~~~

## 31. Bài tập thực hành

### Bài 1 — Retry một câu lệnh hay toàn UoW?

Giao dịch đọc Inventory=10, tính discount theo loyalty status, giảm tồn 3 rồi tạo Order. Transaction bị abort khi một writer khác cập nhật Inventory và loyalty status.

Hãy chỉ ra những phép đọc/kiểm tra phải thực hiện lại trong attempt mới. Giải thích vì sao retry riêng `INSERT Order` với discount cũ là sai.

### Bài 2 — Known abort và unknown commit

Xây state machine cho một command ReserveStock khi: (a) DB báo serialization failure và confirmed abort; (b) client timeout ngay sau COMMIT; (c) business predicate available không đủ.

Mỗi trường hợp được phép retry kiểu gì? Khi nào phải đối soát theo commandId?

### Bài 3 — Callback tự retry

Một callback transaction Firestore hoặc MongoDB gọi payment gateway sau khi giảm kho. Callback bị chạy lại do write conflict.

Hãy mô tả đường dẫn dẫn tới charge trùng và thiết kế lại thành outbox/payment workflow idempotent.

### Bài 4 — Idempotency

HTTP client gửi cùng request `checkout-7281` ba lần, lần đầu đã commit Order nhưng ACK mất.

Hãy thiết kế unique key, bản ghi kết quả, xử lý request đang IN_PROGRESS và response khi payload của cùng commandId bị thay đổi.

### Bài 5 — Write skew

Hai bác sĩ đang trực, mỗi transaction tắt ca mình sau khi đọc người còn lại. Dưới snapshot isolation cho phép write skew, cả hai cùng commit.

Vì sao retry không tự giải quyết được? Đề xuất transaction serializable hoặc một aggregate chung để giữ invariant.

### Bài 6 — Hot key

500 request cùng giữ một SKU còn 30 sản phẩm, CAS liên tiếp gây conflict.

Thiết kế bounded retry với jitter, đo attempts/command, p99, throughput và đề xuất khi nào nên chuyển sang queue/quota.

### Bài 7 — MongoDB

Với transaction chứa Update Inventory, Insert Order và Insert Outbox, phân biệt hướng xử lý `TransientTransactionError` và `UnknownTransactionCommitResult` theo driver. Nêu vì sao callback không được có side effect.

### Bài 8 — DynamoDB

Một TransactWriteItems có condition `available >= quantity` thất bại. Làm sao phân biệt thiếu tồn với transaction conflict? Khi retry, cần giữ stable IDs nào và vì sao không được chia transaction thành hai request?

### Bài 9 — Redis WATCH

Hai client cùng WATCH một stock key, một client EXEC trước. Client còn lại phải làm gì để retry an toàn? Vì sao chỉ gọi lại EXEC mà không WATCH/GET lại là không đúng?

### Bài 10 — Cross-service checkout

Order và Inventory ở hai database, Payment ở gateway thứ ba. Hãy thiết kế saga gồm reserve, authorize, confirm/cancel, release/refund, với trạng thái bền, idempotency và điều kiện dừng retry.

### Bài 11 — Concurrency test

Thiết kế một JUnit test dùng barrier để hai worker cùng đọc version 7 và cố commit. Bổ sung cách quan sát retry attempt, kiểm tra trạng thái cuối tại nguồn và trường hợp barrier gây deadlock khi SDK tự retry.

### Bài 12 — Fault injection

Giả lập process kill trước COMMIT và mất response sau COMMIT. Hai test phải có expected outcomes nào khác nhau? Vì sao process kill không đủ chứng minh durability khi mất điện?

### Bài 13 — Multi-region

Hai region nhận đồng thời lệnh giữ 10 sản phẩm khi tổng tồn là 15 và replication trễ.

Hãy kiểm tra contract CAS cục bộ so với invariant toàn cầu, thiết kế single writer/quota vùng và phương án đối soát khi failover.

### Bài 14 — Price protection

Khách đồng ý giá 100, transaction bị abort. Lần retry đọc được giá 120.

Hãy viết business precondition để không âm thầm thu giá mới, và response phù hợp khi giá đã đổi.

### Bài 15 — Review một retry loop

Một đoạn code bắt mọi exception, sleep 100 ms rồi chạy lại toàn checkout tối đa 100 lần. Hãy chỉ ra lỗi phân loại exception, unknown commit, payment side effects, retry storm, missing deadline và thiếu commandId; đề xuất một thiết kế thay thế.

---

**Kết luận:** Trong NoSQL, xung đột giao dịch thường là cơ chế bảo vệ dữ liệu, không đơn thuần là “DB lỗi”. Khi một attempt đã **abort chắc chắn** do conflict có thể thử lại, cách an toàn là **mở attempt mới và chạy lại toàn bộ các phép đọc–kiểm tra–ghi phụ thuộc nhau trong ranh giới nguyên tử**, với backoff và giới hạn rõ ràng. Nhưng **business rejection không phải lỗi để retry mù**, còn **unknown commit outcome không được giả định là rollback**. Một thiết kế vững chắc kết hợp **hợp đồng isolation/durability đúng phạm vi, business commandId ổn định, idempotency, side effects nằm ngoài callback, outbox/saga khi vượt transaction scope, và kiểm thử concurrency/failure có chủ đích**. Chỉ khi phân biệt được những trường hợp ấy, retry mới thực sự tăng khả năng phục hồi thay vì nhân đôi nghiệp vụ hoặc phá bất biến.
