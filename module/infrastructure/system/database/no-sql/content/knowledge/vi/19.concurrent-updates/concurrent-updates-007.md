# Giữ chỗ tài nguyên và giới hạn số lượng được cấp

## 1. Bài toán: hai người cùng muốn phần tài nguyên cuối cùng

Giả sử một hệ thống bán vé còn **1 ghế** trong suất chiếu. Hai khách hàng cùng nhấn “Giữ vé”:

~~~text
Tại thời điểm ban đầu:
  totalCapacity = 1
  confirmed     = 0
  held          = 0
  available     = 1

Request A đọc available = 1.
Request B đọc available = 1.
A tạo giữ chỗ 1 ghế.
B cũng tạo giữ chỗ 1 ghế.
~~~

Nếu chương trình chỉ làm:

~~~java
int available = repository.getAvailable(showId);

if (available >= 1) {
    repository.createReservation(showId, userId, 1);
    repository.setAvailable(showId, available - 1);
}
~~~

thì cả A và B có thể cùng vượt qua điều kiện. Cuối cùng hệ thống tạo **2 reservation cho 1 ghế**. Giá trị `available` trong cơ sở dữ liệu có thể vẫn là 0 vì hai request cùng ghi đè một kết quả cũ, khiến hệ thống không phát hiện đã cấp quá.

Đây là dạng **race condition / check-then-act** và liên quan tới **lost update**. Nó xuất hiện trong hệ NoSQL cũng như hệ quan hệ nếu thao tác đọc–kiểm tra–ghi không có cơ chế đồng bộ thích hợp.

Tài nguyên hữu hạn có thể là:

- Ghế rạp phim, vé sự kiện, phòng khách sạn, bàn nhà hàng.
- Sản phẩm trong kho, số lượng hàng khuyến mãi.
- Mã voucher hoặc lượt đổi quà có hạn.
- Slot xử lý tác vụ, số kết nối hoặc worker song song.
- Quota API, dung lượng lưu trữ hay số thiết bị được phép sử dụng.
- Số suất đăng ký khóa học, lịch hẹn khám, lịch đặt thiết bị.
- Ngân sách quảng cáo hoặc hạn mức tiêu dùng trong một thời kỳ.

Không phải hệ nào cũng cần giữ chỗ. Nhưng khi một hành động được hứa với người dùng trước khi hoàn tất thanh toán hoặc thực thi, **reservation** giúp tách “quyền tạm giữ” khỏi “quyền sở hữu/tiêu dùng đã xác nhận”.

**Mục tiêu của bài:** thiết kế một quy trình giữ chỗ tài nguyên NoSQL sao cho nhiều request cùng lúc không cấp vượt hạn mức, không thất thoát giữ chỗ khi lỗi, không giải phóng hai lần khi timeout và có thể đối soát sau sự cố.

### 1.1. Sau bài học, bạn cần làm được gì?

1. Xác định **bất biến (invariant)** giữa số lượng tổng, đã giữ, đã cấp và còn lại.
2. Phân biệt **reservation/hold**, **commit/confirm**, **cancel**, **expire**, **consume** và **release**.
3. Hiểu vì sao `read -> if -> write` không an toàn khi cạnh tranh đồng thời.
4. Sử dụng **atomic conditional update**, **compare-and-set (CAS)** hoặc transaction khi phù hợp.
5. Thiết kế **reservation ID**, **idempotency key**, thời hạn giữ chỗ và state machine.
6. Giải thích giải pháp trong MongoDB, DynamoDB, Cassandra và Redis, cùng giới hạn nhất quán/độ bền của từng hệ.
7. Xử lý expiry worker, message trùng/lệch thứ tự, payment timeout và quota theo kỳ.
8. Giảm điểm nóng, đánh đổi giữa strict allocation với throughput và availability.
9. Viết kịch bản kiểm thử cạnh tranh, diễn tập lỗi và chỉ số cảnh báo.

---

## 2. Nắm các khái niệm trước khi thiết kế schema

| Khái niệm | Ý nghĩa | Ví dụ |
|---|---|---|
| **Capacity** | Tổng lượng tài nguyên có thể phân phối | 100 vé |
| **Available** | Lượng chưa giữ/chưa cấp có thể dành cho request mới | 17 vé |
| **Held / Reserved** | Lượng đã tạm giữ nhưng chưa xác nhận | 8 vé |
| **Confirmed / Allocated** | Lượng đã được cấp hoặc bán thành công | 75 vé |
| **Reservation** | Bản ghi thể hiện quyền giữ một lượng tài nguyên | `reservation-9001` giữ 2 vé |
| **Hold expiry** | Mốc hết hạn của reservation | Giữ tối đa 10 phút |
| **Release** | Trả lượng đã giữ về pool khi hủy/hết hạn | Trả lại 2 vé |
| **Consume / Confirm** | Chuyển lượng đã giữ thành lượng được cấp | `held -= 2`, `confirmed += 2` |
| **Overselling / Over-allocation** | Cấp nhiều hơn capacity | Bán 101 vé trong tổng 100 |
| **Underutilization** | Tài nguyên còn sử dụng được nhưng đang bị giữ hoặc chưa thu hồi | 5 vé bị giữ treo |
| **Idempotency** | Lặp lại cùng một request không làm cấp/trả thêm | Retry không giữ thêm ghế |
| **CAS / Conditional update** | Chỉ cập nhật khi trạng thái hiện tại thỏa điều kiện | Trừ nếu `available >= qty` |
| **Lease** | Quyền tạm sử dụng trong một khoảng thời gian | Worker sở hữu slot tới `expiresAt` |
| **Fencing token** | Token thế hệ/phiên tăng để chặn chủ sở hữu cũ ghi tiếp | Generation `42`, `43` |

**Cấp một slot** khác với **bán vĩnh viễn một vật phẩm**. Với vé, confirm chuyển quyền sở hữu; với worker slot, confirm có thể là bắt đầu lease và cần release khi task hoàn tất. Cách đếm giống nhau một phần, nhưng trạng thái và chính sách expiry khác nhau.

### 2.1. Cần định nghĩa tài nguyên có được chia nhỏ không?

Ví dụ:

- Vé ghế đánh số: từng seat ID là tài nguyên riêng, phải tránh hai người giữ **cùng ghế**.
- Tồn kho 50 chiếc của cùng SKU: quantity có thể cấp theo lượng.
- Phòng khách sạn: room type, room ID và **khoảng ngày** cùng tham gia điều kiện.
- Quota 100 lượt/ngày: reservation gắn với **cửa sổ thời gian**.
- Số kết nối tối đa: slot có thể thu hồi khi lease hết hạn.

Không thể áp một counter tổng cho mọi bài toán mà bỏ qua **danh tính tài nguyên, khoảng thời gian, tenant, người sử dụng và điều kiện phục vụ**.

## 3. Bất biến quan trọng nhất: không cấp quá giới hạn

Giả sử một pool có capacity cố định \(C\):

- \(A\): available — chưa được giữ hoặc cấp.
- \(H\): held — tạm giữ còn hiệu lực theo trạng thái có thẩm quyền.
- \(S\): confirmed — đã cấp hoặc tiêu dùng.

Bất biến tổng quát:

\[
A+H+S=C
\]

và:

\[
A\ge0,\quad H\ge0,\quad S\ge0.
\]

Tương đương:

\[
H+S\le C,\qquad A=C-H-S.
\]

Nếu hệ cho phép tăng/giảm capacity, hàng hủy hoặc trả lại, phải mô tả rõ cách những thay đổi này bảo toàn phương trình.

### 3.1. Các chuyển trạng thái hợp lệ

Giữ mới \(q\) đơn vị:

\[
(A,H,S)\longrightarrow(A-q,H+q,S)
\]

với điều kiện \(q>0\) và \(A\ge q\).

Xác nhận giữ chỗ:

\[
(A,H,S)\longrightarrow(A,H-q,S+q).
\]

Hủy/hết hạn giữ chỗ:

\[
(A,H,S)\longrightarrow(A+q,H-q,S).
\]

Hoàn trả một lượng đã xác nhận, **nếu nghiệp vụ cho phép**:

\[
(A,H,S)\longrightarrow(A+q,H,S-q).
\]

Cần cẩn thận: hoàn tiền không nhất thiết đồng nghĩa trả tồn kho; vé đã quét có thể không bán lại. **Refund, cancellation, restock và release là các hành vi khác nhau**.

### 3.2. Bất biến dữ liệu tham chiếu

Nếu mỗi reservation có `quantity` và `state`, lý tưởng là:

\[
H=\sum_{\text{reservation state=HELD}} \text{quantity}
\]

và một phép đối soát tương tự cho số đã cấp.

Trong thực tế có thể có **độ trễ của read model hoặc workflow đang xử lý**. Do đó cần định nghĩa **nguồn sự thật** cho số lượng và một quy trình reconciliation, không dựa vào tổng của một secondary index eventually consistent rồi cấp tài nguyên mà không có bước nguyên tử.

### 3.3. Tính đúng dưới concurrency quan trọng hơn giao diện đọc

API có thể hiển thị “còn 1 vé” từ cache hơi trễ. Nhưng ở thời điểm xác nhận giữ chỗ, **một cơ chế ghi có thẩm quyền** phải kiểm tra capacity và dành lượng còn lại nguyên tử.

Không nên coi số lượng hiển thị trên màn hình là cam kết cho đến khi reservation được ghi thành công.

---

## 4. Race condition: “kiểm tra trước rồi ghi” là lỗi gốc

Một timeline phổ biến:

~~~mermaid
sequenceDiagram
    participant A as Request A
    participant DB as Database
    participant B as Request B

    A->>DB: Read available
    DB-->>A: 1
    B->>DB: Read available
    DB-->>B: 1
    A->>DB: Write available=0
    DB-->>A: Success
    B->>DB: Write available=0
    DB-->>B: Success
    Note over A,B: Hai hold được tạo, chỉ có 1 chỗ
~~~

Sai lầm không phải NoSQL “không có transaction”; sai lầm là **đặt điều kiện kiểm tra ở ngoài thao tác cấp phát có tính nguyên tử**.

### 4.1. Atomic decrement có điều kiện

Cách tư duy đúng:

~~~text
RESERVE(resourceId, q):
  Atomically:
    if available >= q:
      available -= q
      held += q
      success
    else:
      out_of_stock
~~~

Hai request cạnh tranh trên một resource phải được **sắp thứ tự logic hoặc chịu điều kiện cạnh tranh an toàn**, sao cho chỉ lượng hợp lệ được cấp.

Nếu hai request cùng giữ chiếc cuối cùng:

~~~text
Request A: available 1 -> 0, HELD + 1
Request B: available 0, rejected
~~~

Thao tác này không được tách thành “đọc available”, “kiểm tra Java”, “ghi available” ở các bước có thể bị xen ngang.

### 4.2. Atomic counter chưa chắc đồng nghĩa atomic reservation

Giả sử hệ làm:

1. Trừ `available` thành công.
2. Process crash trước khi tạo document reservation.

Lúc đó hệ còn `available=0`, nhưng không có record để người dùng confirm hoặc để expiry worker release. Đây là **lost reservation / leaked capacity**.

Ngược lại, nếu tạo reservation trước rồi trừ stock sau, có thể hiển thị một reservation mà chưa thực sự dành lượng tài nguyên.

Vì vậy cần:

- Transaction bao gồm **counter + reservation record**, nếu DBMS hỗ trợ phù hợp.
- Hoặc đặt cả quyết định và metadata cần thiết trong **một đơn vị atomic**.
- Hoặc workflow cấp phát có **đánh dấu pending, idempotency, timeout và reconciliation** được thiết kế kỹ, với giả định rõ về rủi ro over-allocation.

**Atomic decrement trên một trường chỉ giải quyết một phần bài toán.**

## 5. Mô hình state machine cho reservation

Một reservation không nên được quản lý bằng hai boolean như `reserved=true` và `paid=false` nếu nhiều luồng có thể cùng thay đổi. Nên mô hình hóa trạng thái có ranh giới rõ.

~~~mermaid
stateDiagram-v2
    [*] --> REQUESTED
    REQUESTED --> HELD: Cấp phát thành công
    REQUESTED --> REJECTED: Không còn quota
    HELD --> CONFIRMED: Thanh toán / xác nhận
    HELD --> CANCELLED: Khách hủy
    HELD --> EXPIRED: Hết thời hạn
    CONFIRMED --> REFUNDED: Theo quy tắc nghiệp vụ
    REJECTED --> [*]
    CANCELLED --> [*]
    EXPIRED --> [*]
    REFUNDED --> [*]
~~~

Một số hệ có thể bỏ `REQUESTED` khỏi DB và tạo trực tiếp `HELD`; một số hệ cần `PAYMENT_PENDING` hoặc `PROCESSING`. State machine phải phản ánh workflow thực, không nhất thiết có mọi trạng thái trên.

### 5.1. Quy tắc chuyển trạng thái

| Từ trạng thái | Đến trạng thái | Thao tác số lượng |
|---|---|---|
| Chưa có reservation | `HELD` | `available -= q`, `held += q` |
| `HELD` | `CONFIRMED` | `held -= q`, `confirmed += q` |
| `HELD` | `CANCELLED` | `available += q`, `held -= q` |
| `HELD` | `EXPIRED` | `available += q`, `held -= q` |
| `CONFIRMED` | `REFUNDED` | Tùy chính sách restock, không tự trả quota |
| `CANCELLED` | `CANCELLED` | Không thao tác thêm |
| `EXPIRED` | `EXPIRED` | Không thao tác thêm |
| `CONFIRMED` | `CONFIRMED` | Không thao tác thêm |

Điều cốt lõi: **mỗi reservation chỉ được release hoặc confirm từ trạng thái `HELD` đúng một lần**.

### 5.2. Xung đột confirm và expire

~~~text
T0: Reservation R vẫn HELD.
T1: Payment service bắt đầu confirm R.
T2: Expiry worker thấy R đã đến deadline.
T3: Hai bên cùng muốn thay state và counter.
~~~

Không được để:

- Confirm tăng `confirmed` **và**
- Expiry tăng `available`

cho **cùng một hold**, vì như vậy tổng lượng được cấp có thể vượt capacity.

Cần một trạng thái quyết định **atomic có điều kiện**:

~~~text
CONFIRM nếu state == HELD và expiresAt > now
EXPIRE  nếu state == HELD và expiresAt <= now
~~~

Chỉ một transition thắng. Điều kiện expiry phải được kiểm tra tại điểm quyết định có thẩm quyền, không chỉ dựa trên một bản đọc stale vài giây trước.

### 5.3. Mã định danh bền vững

Một reservation thường cần:

~~~json
{
  "reservationId": "res-9001",
  "requestId": "hold-cart-42-1",
  "resourceId": "sku-42",
  "tenantId": "tenant-7",
  "customerId": "customer-42",
  "quantity": 2,
  "state": "HELD",
  "createdAt": "2026-11-14T08:00:00Z",
  "expiresAt": "2026-11-14T08:10:00Z",
  "version": 1,
  "policyVersion": 3
}
~~~

Đây là schema minh họa. Một đơn hàng có nhiều SKU cần nhiều dòng giữ chỗ hoặc một transaction/workflow đa tài nguyên, không thể chỉ giữ `resourceId` duy nhất như trên.

### 5.4. Unique business key

Nếu ứng dụng nhận retry sau network timeout, `requestId` phải nhận diện **cùng một ý định đặt chỗ**. Hệ cần unique constraint hoặc conditional write phù hợp để hai request trùng `requestId` không tạo hai reservation.

Không nên để client tự chọn `quantity` khác ở lần retry với cùng `requestId` rồi lặng lẽ coi đó là một request hợp lệ. Phải so nội dung hoặc request hash và báo conflict nếu khác.

---

## 6. Chọn nguồn sự thật: counter hay reservation ledger?

Có hai hướng lớn.

### 6.1. Counter là nguồn cấp phát

Resource document chứa:

~~~json
{
  "_id": "sku-42",
  "capacity": 100,
  "available": 17,
  "held": 8,
  "confirmed": 75,
  "version": 918
}
~~~

Hệ chỉ chấp nhận giữ chỗ khi **atomic conditional update** thành công trên resource. Reservation document là bằng chứng chi tiết được ghi cùng transaction hoặc quy trình có đối soát.

Ưu điểm:

- Điều kiện `available >= quantity` rõ.
- Dễ chặn over-allocation.
- Query nhanh theo một khóa.

Đánh đổi:

- Một SKU rất nóng tạo **contention trên resource document/partition**.
- Counter có thể lệch ledger nếu workflow nhiều bước không atomic.

### 6.2. Reservation ledger là nguồn sự thật

Hệ lưu từng reservation như một sự kiện/record có trạng thái, sau đó tính số còn lại từ ledger hoặc một read model.

Ưu điểm:

- Có lịch sử trạng thái và audit.
- Có thể tái dựng counter.
- Dễ truy nguồn gốc.

Rủi ro:

- Nếu nhiều request cùng tính tổng `HELD` từ một index **không có transaction/cơ chế đồng bộ bảo vệ giới hạn**, chúng vẫn có thể cùng cấp vượt.
- Tổng hợp toàn ledger trên mỗi reservation có thể cực chậm.
- Read model eventually consistent không đủ làm điểm quyết định strict capacity.

**Ledger tốt cho audit và reconciliation; điểm cấp phát strict cần một cơ chế đồng bộ có thẩm quyền.**

### 6.3. Kết hợp

Nhiều hệ thực tế dùng:

- Counter/đơn vị atomic để bảo vệ capacity.
- Reservation record để quản lý trạng thái.
- Outbox/event cho luồng thanh toán, analytics và search.
- Reconciliation để so counter với ledger theo lịch.

Điều quan trọng là **counter và reservation không được rời khỏi các trạng thái hợp lệ mà không có cơ chế phát hiện, bù trừ an toàn**.

## 7. MongoDB: cấp phát bằng atomic conditional update

MongoDB hỗ trợ cập nhật một document có tính nguyên tử, gồm bước match điều kiện và update trên document đó.

Giả sử:

~~~javascript
db.inventory.insertOne({
  _id: "sku-42",
  capacity: 100,
  available: 100,
  held: 0,
  confirmed: 0,
  version: 1
});
~~~

### 7.1. Reserve chỉ với một resource document

~~~javascript
const qty = 2;

const result = db.inventory.findOneAndUpdate(
  {
    _id: "sku-42",
    available: { $gte: qty }
  },
  {
    $inc: {
      available: -qty,
      held: qty,
      version: 1
    }
  },
  {
    returnDocument: "after"
  }
);

if (!result) {
  // Không có resource hoặc không còn đủ số lượng.
}
~~~

Nếu `available` chỉ còn 1, điều kiện `available >= 2` thất bại; giá trị không bị trừ xuống âm.

Nếu hai request cạnh tranh cho 1 đơn vị cuối, thao tác match-and-update nguyên tử trên **cùng document** không cho cả hai thành công khi điều kiện chỉ đủ cho một.

**Điều kiện cần**: `qty` được kiểm tra > 0 và trong giới hạn hợp lệ, không tin giá trị client tùy ý. Phải phân biệt resource không tồn tại với hết hàng theo hợp đồng API.

### 7.2. Vì sao vẫn chưa xong?

Nếu thao tác trên thành công nhưng ứng dụng crash **trước khi tạo reservation document**, counter bị giữ lại mà không có record tham chiếu.

Sai:

~~~javascript
const updated = db.inventory.findOneAndUpdate(
  { _id: sku, available: { $gte: qty } },
  { $inc: { available: -qty, held: qty } }
);

// Crash có thể xảy ra ở đây!
db.reservations.insertOne({
  _id: reservationId,
  sku,
  qty,
  state: "HELD"
});
~~~

Do đó, khi counter và reservation ở **hai document**, cần transaction hoặc giao thức khác được thiết kế cho failure/reconciliation.

### 7.3. Transaction trên nhiều document

Ví dụ khái niệm với `mongosh` và session, trong cấu hình MongoDB hỗ trợ transaction:

~~~javascript
const session = db.getMongo().startSession();

try {
  const txnDb = session.getDatabase(db.getName());
  const inventory = txnDb.getCollection("inventory");
  const reservations = txnDb.getCollection("reservations");

  session.startTransaction();

  const reservationId = "res-9001";
  const qty = 2;
  const now = new Date();
  const expiresAt = new Date(now.getTime() + 10 * 60 * 1000);

  // _id cố định giúp phát hiện retry đã được áp dụng.
  reservations.insertOne({
    _id: reservationId,
    requestId: "hold-cart-42-1",
    resourceId: "sku-42",
    quantity: qty,
    state: "HELD",
    createdAt: now,
    expiresAt
  });

  const changed = inventory.updateOne(
    {
      _id: "sku-42",
      available: { $gte: qty }
    },
    {
      $inc: {
        available: -qty,
        held: qty
      }
    }
  );

  if (changed.modifiedCount !== 1) {
    throw new Error("CAPACITY_EXHAUSTED");
  }

  session.commitTransaction();
} catch (error) {
  session.abortTransaction();
  throw error;
} finally {
  session.endSession();
}
~~~

Đây là **ví dụ workflow**. Với production cần:

- Thử lại những lỗi transaction có nhãn retryable/commit outcome unknown theo hướng dẫn driver.
- Xử lý `DuplicateKey` và phân biệt retry cùng request với ID xung đột.
- Không gửi email/thu tiền bên trong callback transaction có thể chạy lại.
- Kiểm tra transaction support, timeout, write concern, read concern và topology.
- Thực hiện uniqueness cho `requestId` với phạm vi tenant phù hợp.
- Không gọi `abortTransaction()` như thể nó chắc chắn có thể hủy sau khi commit không rõ; phải xử lý trạng thái theo API transaction thực tế.

Ví dụ nhằm làm rõ **counter và reservation cùng commit hoặc cùng không commit**, chứ không đưa ra một service production có thể chép nguyên xi.

### 7.4. Unique index cho idempotency

~~~javascript
db.reservations.createIndex(
  { tenantId: 1, requestId: 1 },
  { unique: true, name: "uniq_hold_request_per_tenant" }
);
~~~

Hãy thêm `tenantId` vào document và kiểm tra quyền ở backend. Nếu client gửi lại request với cùng idempotency key, hệ nên trả reservation cũ **nếu payload khớp**.

### 7.5. Confirm/cancel cũng cần transaction có điều kiện

Để confirm:

1. Tìm reservation `HELD` còn hạn.
2. Chỉ một transaction được đổi `HELD -> CONFIRMED`.
3. Cùng transaction chuyển `held -= q, confirmed += q`.
4. Ghi outbox event nếu có.

Để cancel:

1. Chỉ khi `state == HELD` mới đổi sang `CANCELLED`.
2. Cùng transaction chuyển `held -= q, available += q`.
3. Retry cancel sau khi đã `CANCELLED` không cộng lại lần hai.

Khi confirm và expire cạnh tranh, transaction/write conflict hoặc conditional update phải bảo vệ một **quyết định duy nhất**. Driver có thể yêu cầu retry transaction khi có conflict; retry cần dùng lại reservation ID và kiểm tra trạng thái.

---

## 8. DynamoDB: conditional write và transaction

DynamoDB cho phép cập nhật có điều kiện trên item; nếu cần cập nhật nhiều item trong một đơn vị atomic, có thể dùng **TransactWriteItems** trong phạm vi giới hạn dịch vụ.

### 8.1. Chỉ giảm `available` nếu đủ

Dữ liệu bảng `Inventory`:

~~~json
{
  "resourceId": "sku-42",
  "capacity": 100,
  "available": 17,
  "held": 8,
  "confirmed": 75
}
~~~

DynamoDBDocumentClient JavaScript v3:

~~~javascript
import { UpdateCommand } from "@aws-sdk/lib-dynamodb";

await documentClient.send(new UpdateCommand({
  TableName: "Inventory",
  Key: { resourceId: "sku-42" },
  UpdateExpression:
    "SET available = available - :qty, held = held + :qty",
  ConditionExpression:
    "attribute_exists(resourceId) AND available >= :qty",
  ExpressionAttributeValues: {
    ":qty": 2
  }
}));
~~~

Nếu capacity không đủ, request gặp **ConditionalCheckFailed** thay vì tạo một counter âm. Nên kiểm tra `qty > 0` ở server trước.

Tuy nhiên, ví dụ trên chỉ cập nhật một item counter. Nếu phải tạo reservation riêng, cần thêm bước atomic hoặc quy trình có đối soát.

### 8.2. Transaction giữ chỗ gồm hai item

Một schema minh họa:

~~~text
Inventory table:
  PK = resourceId

Reservations table:
  PK = reservationId
  attributes: requestId, resourceId, quantity, state, expiresAt
~~~

~~~javascript
import { TransactWriteCommand } from "@aws-sdk/lib-dynamodb";

await documentClient.send(new TransactWriteCommand({
  TransactItems: [
    {
      Update: {
        TableName: "Inventory",
        Key: { resourceId: "sku-42" },
        UpdateExpression:
          "SET available = available - :q, held = held + :q",
        ConditionExpression:
          "attribute_exists(resourceId) AND available >= :q",
        ExpressionAttributeValues: { ":q": 2 }
      }
    },
    {
      Put: {
        TableName: "Reservations",
        Item: {
          reservationId: "res-9001",
          requestId: "hold-cart-42-1",
          tenantId: "tenant-7",
          resourceId: "sku-42",
          quantity: 2,
          state: "HELD",
          expiresAt: 1790000000
        },
        ConditionExpression:
          "attribute_not_exists(reservationId)"
      }
    }
  ],
  ClientRequestToken: "stable-client-token-9001"
}));
~~~

Điểm quan trọng:

- `expiresAt` ở ví dụ là **số epoch seconds minh họa**, không phải timestamp cần sao chép vào hệ thật.
- `ClientRequestToken` hỗ trợ idempotency **của giao thức transaction DynamoDB** trong phạm vi/thời hạn theo dịch vụ; không thay thế idempotency nghiệp vụ dài hạn.
- `reservationId` phải ổn định trên retry.
- Nếu `requestId` là unique business key nhưng không phải primary key, DynamoDB **không tự thực thi unique constraint tùy ý trên GSI**. Có thể đặt primary key theo `tenantId#requestId` hoặc tạo một item guard đặc biệt trong transaction.
- Không thể đặt hai thao tác transaction cùng nhắm một item theo những cách dịch vụ cấm; schema cần phù hợp giới hạn của `TransactWriteItems`.

### 8.3. Conditional confirm/cancel

Confirm một hold cần transaction:

~~~text
Condition reservation.state == HELD
AND reservation.expiresAt > now

Update reservation.state = CONFIRMED
Update inventory.held -= q
Update inventory.confirmed += q
~~~

Cancel/expire:

~~~text
Condition reservation.state == HELD

Update reservation.state = CANCELLED or EXPIRED
Update inventory.held -= q
Update inventory.available += q
~~~

Nếu hai luồng cùng chạy, chỉ một transition có điều kiện được commit; luồng còn lại phải đọc lại trạng thái và xử lý idempotent.

Trong DynamoDB, điều kiện thời gian trên reservation dùng giá trị `now` do backend/worker cung cấp; cần kiểm soát clock skew, timezone và mốc quyền quyết định. Không nên tin đồng hồ client.

### 8.4. TTL không tự giải phóng quota

DynamoDB TTL xóa item đủ hạn **bất đồng bộ**. Nếu bật TTL cho reservation `HELD`, việc item biến mất **không tự cộng lại** quantity vào `Inventory.available`.

Tệ hơn, nếu TTL xóa reservation trước khi expiry worker chuyển state, hệ có thể mất bằng chứng để release.

Đối với strict quota:

- Dùng `expiresAt` làm điều kiện state transition.
- Có expiry worker truy vấn những hold đã đến hạn.
- Chuyển `HELD -> EXPIRED` và hoàn trả counter **nguyên tử có điều kiện**.
- Giữ tombstone/trạng thái terminal đủ lâu theo nhu cầu idempotency và audit.
- Chỉ cho TTL xóa record terminal sau khi hoàn thành quy trình và chính sách retention.

**TTL là cơ chế lifecycle dữ liệu, không phải transaction hoàn lại số chỗ.**

---

## 9. Cassandra: lightweight transaction và giới hạn đa partition

Cassandra thường tối ưu các thao tác theo partition key. Với strict reservation, nếu chỉ đọc counter rồi ghi lại bằng CQL thông thường, hai client có thể cùng dựa trên trạng thái cũ.

### 9.1. Bảng inventory

~~~sql
CREATE TABLE inventory_by_resource (
  resource_id text PRIMARY KEY,
  available int,
  held int,
  confirmed int,
  version bigint
);
~~~

Giả sử resource hiện có:

~~~text
resource_id = sku-42
available   = 5
held        = 2
confirmed   = 93
version     = 7
~~~

### 9.2. Compare-and-set bằng LWT

Ứng dụng đọc giá trị và version, tính trạng thái mong muốn rồi dùng conditional update:

~~~sql
UPDATE inventory_by_resource
SET available = 3,
    held = 4,
    version = 8
WHERE resource_id = 'sku-42'
IF version = 7;
~~~

Nếu request khác đã đổi version, điều kiện thất bại và ứng dụng phải đọc lại trước khi thử tiếp.

**Đây là ví dụ CAS bằng Lightweight Transaction (LWT)**. LWT sử dụng cơ chế đồng thuận trong phạm vi hỗ trợ của Cassandra và có latency/chi phí cao hơn các ghi thông thường.

Cần bảo đảm:

- Đọc `available >= q` trước khi tính giá trị mới.
- Mỗi update CAS ràng buộc chính xác version đã đọc.
- Khi CAS thất bại, không lặp lại cùng giá trị mới một cách mù quáng.
- Giới hạn số retry/backoff khi contention cao.
- Khởi tạo resource/counter theo cách có thẩm quyền.
- Điều kiện/semantics cụ thể phù hợp phiên bản Cassandra và driver.

### 9.3. CAS một row chưa đủ cho hai row

Nếu inventory và reservation nằm ở hai partition khác nhau:

~~~text
Partition inventory: resource_id = sku-42
Partition reservation: reservation_id = res-9001
~~~

CAS trên inventory giúp tránh trừ quá counter, nhưng chưa bảo đảm **reservation document và counter cùng commit** nếu ứng dụng viết thành hai câu lệnh riêng.

Cassandra `BATCH` thông thường **không phải transaction SQL serializable** qua mọi partition. Không nên giả định ghép hai CQL statements trong một batch là đủ để có state machine giữ chỗ strict.

Các chiến lược cần cân nhắc:

- Giới hạn trạng thái cấp phát trong một partition/đơn vị có conditional semantics phù hợp, nếu mô hình cho phép và không thành hot partition lớn.
- Xây coordinator service có reservation ledger, CAS và reconciliation rõ.
- Dùng một transactional store khác cho phần **quyết định cấp phát strict**, còn Cassandra lưu read model hoặc event history.
- Dùng quota phân bổ trước theo shard/owner để giảm contention nhưng có protocol điều chỉnh capacity.

### 9.4. LWT có thể tạo hotspot

Mọi request giữ vé cuối cho một resource sẽ tranh cùng một row/version. LWT dưới contention cao có thể tăng latency và retry thất bại.

Cần đo p95/p99, throughput, số CAS rejected/conflicts và failover, không chỉ xem conditional update có đúng trên một test nhỏ.

---

## 10. Redis: thao tác nguyên tử bằng Lua, nhưng durability cần tách riêng

Redis xử lý các lệnh trên một primary theo mô hình tuần tự của server. Một Lua script nhỏ có thể kiểm tra và cập nhật nhiều key **nguyên tử trong phạm vi thực thi script trên node đó**, giúp tránh race của `GET` rồi `DECR` tách biệt.

### 10.1. Vì sao GET + DECR không đủ?

Sai:

~~~text
Client A: GET available -> 1
Client B: GET available -> 1
Client A: DECR available -> 0
Client B: DECR available -> -1
~~~

Ngay cả khi `DECR` là một lệnh atomic, **quyết định được phép giữ** đã xảy ra từ hai lệnh `GET` bên ngoài, nên vẫn có thể over-allocation.

### 10.2. Script kiểm tra và cấp phát

Một ví dụ minh họa dùng:

~~~text
KEYS[1] = {sku-42}:inventory
KEYS[2] = {sku-42}:reservation:res-9001
KEYS[3] = {sku-42}:expiry-index

ARGV[1] = quantity
ARGV[2] = expiresAtEpochMs
ARGV[3] = reservationId
~~~

~~~lua
local qty = tonumber(ARGV[1])
local expiresAt = tonumber(ARGV[2])
local reservationId = ARGV[3]

if not qty or qty <= 0 or qty % 1 ~= 0 then
  return {err = "INVALID_QUANTITY"}
end

if redis.call("EXISTS", KEYS[2]) == 1 then
  return "ALREADY_EXISTS"
end

local available = tonumber(
  redis.call("HGET", KEYS[1], "available")
)

if not available then
  return {err = "UNKNOWN_RESOURCE"}
end

if available < qty then
  return "OUT_OF_CAPACITY"
end

redis.call("HINCRBY", KEYS[1], "available", -qty)
redis.call("HINCRBY", KEYS[1], "held", qty)

redis.call(
  "HSET", KEYS[2],
  "state", "HELD",
  "quantity", qty,
  "expiresAt", expiresAt
)

redis.call(
  "ZADD", KEYS[3], expiresAt, reservationId
)

return "HELD"
~~~

Những key trong Redis Cluster cần nằm cùng **hash slot** nếu script thực hiện nhiều-key operation trên một node. Ví dụ hash tag `{sku-42}` giúp chúng được gắn cùng slot theo quy tắc Redis Cluster.

**Đoạn Lua chỉ minh họa**, chưa bao gồm đủ validation overflow, xác thực tenant, audit, confirm/cancel, persistence, TTL của record terminal hoặc quy trình phục hồi.

### 10.3. Expiry không tự động trả lượng đã giữ

Trong ví dụ này, expiry được lưu ở sorted set để worker tìm các reservation đã đến hạn.

Nếu chỉ đặt:

~~~text
EXPIRE reservationKey 600
~~~

và mong Redis tự tăng `available` khi key hết hạn thì **sai**: key expiration không đồng nghĩa thực hiện transaction hoàn lại counter.

Worker phải:

1. Tìm reservation đã tới deadline.
2. Kiểm tra `state == HELD`.
3. Trong một script/atomic unit, đổi state sang `EXPIRED`.
4. `held -= q`, `available += q`.
5. Loại ID khỏi expiry index.
6. Giữ terminal record đủ lâu để chống retry trùng.

### 10.4. Atomic Lua không đồng nghĩa chống mất node

Redis script atomic theo phạm vi server thực thi, nhưng ghi có thể vẫn phụ thuộc **AOF/RDB, fsync mode, replication và failover**. Một request đã được primary ACK nhưng chưa được replica/persistence bảo vệ có thể mất sau sự cố theo cấu hình.

**Tính nguyên tử khi cạnh tranh trên một primary và độ bền sau failover là hai bài toán khác nhau.** Với tài nguyên có giá trị cao, không nên coi Redis cache không persistence là source of truth duy nhất mà không có thiết kế durability và recovery thỏa yêu cầu.

### 10.5. Script lớn cũng có chi phí

Lua chạy trên server nên tránh quét hàng triệu reservation hoặc xử lý lâu trong một script. Dùng các thao tác O(1)/giới hạn rõ, worker chia batch và cân nhắc khả năng hot key.

---

## 11. Giữ chỗ có thời hạn: lease và expiration

Một reservation thường có hạn 5 hoặc 10 phút để người dùng thanh toán.

~~~text
createdAt = 10:00:00 UTC
expiresAt = 10:10:00 UTC
```

Khi người dùng không hoàn tất, hệ phải **giải phóng tài nguyên**. Nhưng việc đến hạn và việc hoàn trả counter thường là **hai mốc khác nhau**.

### 11.1. Hết hạn về mặt nghiệp vụ

Một request confirm tại 10:10:05 không được chấp nhận nếu policy yêu cầu giữ chỗ kết thúc lúc 10:10:00, dù worker cleanup chưa chạy.

Cần kiểm tra:

~~~text
state == HELD
AND expiresAt > authoritativeNow
```

**Không lấy thời gian trên thiết bị người dùng làm mốc quyết định.** Đồng hồ backend/DB có thể lệch; cần thống nhất cách tính expiration, UTC và một nguồn thời gian đáng tin tương ứng với kiến trúc.

### 11.2. Hết hạn vật lý và hoàn lại capacity

Worker có thể chạy mỗi vài giây hoặc theo queue/scheduler:

~~~text
scan due reservations:
  state == HELD
  expiresAt <= now

for each:
  attempt atomic transition HELD -> EXPIRED
  if won:
    decrement held
    increment available
~~~

Nếu worker chậm, tài nguyên đã hết hạn **vẫn còn bị giữ trong counter** một thời gian. Điều này gây underutilization nhưng **an toàn hơn** việc cộng `available` mà chưa chắc reservation đã mất quyền confirm.

### 11.3. Không cho confirm và expire cùng thắng

Timeline:

~~~text
T1: Payment callback xử lý R.
T2: Expiry worker xử lý R.
T3: Cả hai đọc state=HELD.
~~~

Đúng:

~~~text
Payment:
  condition state=HELD and now<expiresAt
  transition to CONFIRMED
  held--, confirmed++

Expiry:
  condition state=HELD and now>=expiresAt
  transition to EXPIRED
  held--, available++
```

Điều kiện và update phải thuộc một atomic unit hoặc transaction phù hợp. Nếu một bên thắng, bên kia nhận conditional failure và **không thay đổi counter lần hai**.

### 11.4. Renewal / gia hạn lease

Một số tài nguyên cho phép gia hạn hold (ví dụ người dùng đã bắt đầu thanh toán):

- Chỉ gia hạn khi `state == HELD`.
- Có giới hạn số lần gia hạn và tổng thời gian.
- Việc gia hạn phải cập nhật `expiresAt` cạnh tranh an toàn với worker expiry.
- Worker cần xác minh deadline hiện tại, không dùng dữ liệu của một lần scan cũ.
- Người dùng không được tự tăng deadline nếu chưa có quyền.

Nếu job worker xử lý tác vụ dài, gia hạn lease còn cần **fencing token** để ngăn một worker cũ đã mất lease tiếp tục ghi kết quả sau khi worker mới tiếp quản.

### 11.5. Fencing token cho tài nguyên cần chủ sở hữu duy nhất

Ví dụ worker A có lease generation 41. A bị pause lâu, lease hết hạn. Worker B nhận lease generation 42. Khi A chạy tiếp, hệ đích phải từ chối thao tác với token 41 nếu đã thấy token 42.

~~~text
Worker A: token=41  -> stale, reject
Worker B: token=42  -> current, accept
~~~

TTL/lease expiry **một mình** không ngăn worker cũ tiếp tục thực hiện side effect khi nó tỉnh lại. Fencing cần được thực thi bởi tài nguyên đích hoặc một hệ có thẩm quyền phù hợp.

---

## 12. Giới hạn theo thời gian: quota và rate limiting

“Giới hạn số lượng được cấp” có thể là:

- **Capacity tổng:** chỉ có 100 vé trong sự kiện.
- **Quota theo kỳ:** mỗi tài khoản được dùng tối đa 100 request/ngày.
- **Concurrent limit:** tối đa 20 task chạy đồng thời.
- **Rate limit:** tối đa 50 request/giây.
- **Budget:** tối đa một số tiền/đơn vị tiêu dùng trong tháng.

Những bài toán này **không hoàn toàn giống nhau**.

### 12.1. Fixed window quota

Với quota 100 request/ngày:

~~~text
Key = (tenantId, quotaType, UTC_DAY)
used = số lượt đã cấp trong cửa sổ
```

Cần atomic conditional increment:

~~~text
if used + q <= limit:
  used += q
  allow
else:
  reject
```

Ranh giới ngày và timezone phải được định nghĩa rõ. Một client ở timezone khác không được tự chọn cửa sổ để vượt quota.

### 12.2. Sliding window, token bucket và leaky bucket

Các thuật toán rate limit thường gặp:

- **Fixed window:** đơn giản, có thể tạo burst quanh ranh giới cửa sổ.
- **Sliding window:** xét một khoảng thời gian trượt, chính xác hơn nhưng cần trạng thái/chi phí khác.
- **Token bucket:** token được bổ sung theo tốc độ; cho phép burst trong giới hạn bucket.
- **Leaky bucket:** kiểm soát nhịp xử lý/đầu ra.

Đây là bài toán **tốc độ**, không nhất thiết là reservation tồn kho. Một token bị tiêu dùng trong rate limiter thường không được hoàn lại khi request đã đi vào hệ, trong khi slot concurrency phải được release sau task.

### 12.3. Concurrent slots bằng lease

Nếu hệ chỉ cho 20 job chạy đồng thời:

~~~text
maxSlots = 20
activeLeases <= 20
```

Khi worker nhận task, cần reserve một slot atomically; khi task hoàn tất, release. Khi worker chết, lease hết hạn và recovery thu hồi slot.

Nếu worker chạy quá lâu, lease cần gia hạn; hệ đích có thể cần fencing token để chặn worker cũ sau khi slot được giao lại.

### 12.4. Quota theo tenant

Không nên chỉ ghi counter toàn hệ nếu hợp đồng là “mỗi tenant 100 lượt/ngày”. Key phải bao gồm **tenantId + quota type + period**, và backend phải xác minh tenant được phép thay vì tin một field trong request.

### 12.5. Truy vấn số lượng còn lại có thể eventual, quyết định cấp phát phải chặt

Dashboard có thể sử dụng read model eventual để hiển thị lượng tiêu dùng. Nhưng nếu strict quota quan trọng, quyết định cấp phát phải dựa trên **atomic authoritative state**, không phải dựa vào một cache counter chưa cập nhật.

---

## 13. Đa tài nguyên: giữ cả giỏ hàng

Một giỏ có:

~~~text
SKU-A: 2 đơn vị
SKU-B: 1 đơn vị
SKU-C: 3 đơn vị
```

Nếu giữ A thành công rồi B thất bại, hệ phải quyết định:

- **All-or-nothing:** hoặc giữ tất cả, hoặc không giữ gì.
- **Partial allocation:** cho phép khách chỉ giữ phần có sẵn.
- **Saga/compensation:** giữ lần lượt rồi release những phần đã giữ nếu có bước lỗi.

### 13.1. Transaction khi có cùng phạm vi atomicity

Nếu DBMS hỗ trợ multi-item transaction với các item nguồn/hold liên quan, có thể ràng buộc toàn bộ giỏ trong một transaction, miễn là đáp ứng giới hạn về số item, dung lượng và phạm vi của dịch vụ.

Ưu điểm: một kết quả atomic.

Đánh đổi: transaction có thể tăng contention, latency và tỉ lệ conflict khi giỏ chứa nhiều SKU nóng.

### 13.2. Saga và compensation khi vượt phạm vi transaction

Luồng minh họa:

~~~mermaid
flowchart TD
    A["Reserve SKU-A"] --> B{"A thành công?"}
    B -->|"Không"| Z["Reject cart"]
    B -->|"Có"| C["Reserve SKU-B"]
    C --> D{"B thành công?"}
    D -->|"Không"| E["Release SKU-A"]
    E --> Z
    D -->|"Có"| F["Reserve SKU-C"]
    F --> G{"C thành công?"}
    G -->|"Không"| H["Release A và B"]
    H --> Z
    G -->|"Có"| I["All HELD, chờ confirm"]
~~~

**Compensation không phải rollback nguyên tử tức thời.** Giữa lúc A được giữ và lúc release, một phần capacity có thể bị khóa. Nếu worker chết, cần retry và reconciliation. Mọi thao tác reserve/release phải idempotent.

### 13.3. Tránh deadlock và lock contention

Khi giữ nhiều resource và dùng lock/transaction, có thể chuẩn hóa thứ tự resource ID để giảm vòng chờ. Với distributed workflow, không nên phụ thuộc lock trong bộ nhớ của một Java instance vì các instance khác không chia sẻ lock đó.

### 13.4. Phân biệt cam kết kho với thanh toán

Giữ hàng trước khi gọi payment provider giúp giảm nguy cơ đã thu tiền nhưng không có hàng. Nhưng callback thanh toán có thể đến trễ sau expiry, nên quy trình cần quy tắc:

- Nếu hold còn hiệu lực: confirm.
- Nếu hold đã expired: không tự tăng sold; xử lý thanh toán theo chính sách refund/retry.
- Nếu callback lặp: không confirm hai lần.
- Nếu đã confirm nhưng client timeout: trả trạng thái đã confirm khi retry.

**Không để payment callback tự cấp thêm inventory vì “khách đã trả tiền”.**

---

## 14. Idempotency: lặp request không được giữ hoặc trả tài nguyên hai lần

Ví dụ client gửi hold request:

~~~http
POST /reservations
Idempotency-Key: hold-cart-42-1

{
  "resourceId": "sku-42",
  "quantity": 2
}
~~~

Server giữ 2 đơn vị, nhưng response bị mất. Client retry.

Nếu mỗi lần retry tạo reservation mới, khách có thể giữ 4, 6 hoặc 8 đơn vị.

### 14.1. Cần ba nhóm định danh

1. **Business request ID:** cùng một ý định từ client.
2. **Reservation ID:** định danh bản ghi giữ chỗ.
3. **Resource ID:** tài nguyên được giữ.

Một request nên ánh xạ ổn định tới cùng reservation/result.

### 14.2. Retry không được cộng thêm counter

Sai:

~~~text
Request #1:
  available -= 2
  create res-1
  response lost

Request #2:
  available -= 2
  create res-2
~~~

Đúng về logic:

~~~text
If requestId already processed:
  if payload matches:
    return previous reservation/result
  else:
    return conflict
Else:
  atomically create reservation and decrease capacity
~~~

Nếu reservation cũ đã `EXPIRED`, retry cùng request ID **không được lặng lẽ tạo hold mới** trừ khi API định nghĩa một request mới có ID mới.

### 14.3. Idempotent cancel

~~~text
First cancel:
  HELD -> CANCELLED
  available += 2

Retry cancel:
  state already CANCELLED
  no counter change
~~~

Tương tự, expiry worker có thể nhận cùng ID nhiều lần mà không được trả quantity hai lần.

### 14.4. Conditional failure không phải lúc nào là lỗi nghiệp vụ mới

Một conditional insert thất bại vì ID đã tồn tại có thể chỉ ra request trước đã thành công. Cần đọc lại và xác minh payload.

Tuy nhiên, cũng có thể là **xung đột ID** với request khác, nên không coi mọi duplicate key là thành công mà không kiểm tra.

---

## 15. Quản lý expiration: độ đúng trước, dọn dẹp sau

Một hệ có 1 triệu giữ chỗ/ngày không thể phụ thuộc hoàn toàn vào việc TTL xóa record để giải phóng capacity.

### 15.1. Dùng expiry index/queue

Có thể có một index hoặc hàng đợi theo `expiresAt`:

~~~text
Reservation R1 -> 10:05
Reservation R2 -> 10:08
Reservation R3 -> 10:11
~~~

Worker lấy những reservation tới hạn rồi **revalidate** trạng thái và deadline tại thời điểm update.

### 15.2. Không xem một bản đọc cũ là bằng chứng để release

Sai:

~~~text
T0: Worker đọc R1 expiresAt=10:05.
T1: Client gia hạn R1 tới 10:15.
T2: Worker vẫn release R1 dựa trên snapshot T0.
~~~

Đúng: dùng conditional transition có ràng buộc **phiên bản/deadline hiện tại**, để worker không giải phóng reservation đã được gia hạn hợp lệ.

### 15.3. Worker chết giữa chừng

Nếu worker nhận expiry job và crash:

- Job có thể được giao lại.
- Transition phải idempotent.
- Checkpoint chỉ đánh dấu thành công khi state/counter đã được cập nhật đúng.
- Nếu DBMS trả timeout sau commit, worker phải đọc lại trạng thái thay vì cộng lần hai.

### 15.4. Quét toàn bộ reservation có thể quá tốn

Một hệ có hàng chục triệu record không nên định kỳ scan toàn bộ chỉ để tìm vài hold mới hết hạn. Cần index theo trạng thái/deadline, bucket theo thời gian hoặc một schedule/queue phù hợp, nhưng vẫn kiểm tra state hiện tại trước release.

### 15.5. Lưu terminal state đủ lâu

Nếu record `CANCELLED` hoặc `EXPIRED` bị TTL dọn quá sớm, retry cũ có thể bị hệ xem như request mới. Vì vậy, **retention của idempotency record** là một chính sách riêng, thường cần dài hơn khoảng retry có thể xảy ra.

---

## 16. Cập nhật đồng thời, version và optimistic locking

Ngoài conditional decrement, một số schema dùng **version** để phát hiện thay đổi cạnh tranh.

Resource:

~~~json
{
  "resourceId": "sku-42",
  "available": 5,
  "held": 2,
  "version": 17
}
~~~

Request A và B cùng đọc version 17. A muốn giữ 2:

~~~text
UPDATE only if version==17
  available = 3
  held = 4
  version = 18
~~~

B cũng thử dựa trên version 17, nên thất bại. B phải đọc lại version 18 và tính tiếp.

### 16.1. CAS tốt khi nào?

- Bản ghi cần cập nhật có state nhỏ, biết chính xác khóa.
- Mức cạnh tranh vừa phải.
- Conflict được retry có giới hạn.
- Workload đọc thường hơn ghi hoặc số client trên một key không quá lớn.

### 16.2. Vấn đề khi contention rất cao

Một SKU flash sale có hàng nghìn request cùng lúc; gần như tất cả đều tranh một version:

- CAS failed rate cao.
- Retry tăng CPU/network.
- p99 tăng.
- User có thể thấy lỗi dù hệ còn một ít capacity.
- Hot partition trở thành giới hạn throughput.

Lúc này cần tối ưu cách phân phối quyền cấp phát, không chỉ tăng vô hạn số lần retry.

### 16.3. Pessimistic locking

Một số hệ có thể dùng lock hoặc transaction để serialize thao tác. Nhưng distributed lock:

- Có thể bị hết lease khi chủ sở hữu vẫn đang chạy.
- Cần fencing token cho side effect.
- Dễ tạo điểm nghẽn.
- Lock trong JVM chỉ bảo vệ cùng một process.

**Nếu một atomic conditional update trong DB đủ bảo vệ invariant, không nên thêm distributed lock một cách máy móc.**

---

## 17. Hot resource và phân chia quota

Một SKU bình thường có vài request/giây; SKU flash sale có thể nhận hàng chục nghìn request/giây. Một document counter có thể trở thành **hot key/hot partition**.

### 17.1. Vì sao sharding counter nguy hiểm?

Giả sử capacity = 100 và chia thành 10 shard, mỗi shard chứa quota 10. Nếu mỗi shard chỉ được cấp trong quota riêng, tổng không vượt 100.

Nhưng nếu 10 shard đều đọc “available toàn cục = 100” rồi mỗi shard tự cấp thêm mà không có ngân sách phân bổ, hệ có thể cấp quá.

**Sharding chỉ an toàn khi mỗi shard có quyền cấp phát đã được phân bổ rõ hoặc có một điểm quyết định đồng bộ chung.**

### 17.2. Escrow / preallocated quota

Một phương án:

~~~text
Total capacity = 100

Shard A allocated budget = 30
Shard B allocated budget = 30
Shard C allocated budget = 40

Invariant:
  granted(A) <= 30
  granted(B) <= 30
  granted(C) <= 40
  sum(budgets) = 100
~~~

Mỗi shard chỉ cấp từ ngân sách được giao. Khi shard A hết quota nhưng B còn, hệ cần **tái phân phối quota** bằng một quy trình an toàn; không được tự ý tăng ngân sách ở hai nơi.

### 17.3. Ưu và nhược điểm

Ưu điểm:

- Giảm contention ở một counter trung tâm.
- Tăng throughput khi request được trải qua nhiều shard.
- Có thể phân phối quyền cấp phát theo vùng/tenant.

Nhược điểm:

- Có thể còn capacity ở shard khác nhưng shard hiện tại đã hết.
- Chuyển quota giữa shard cần giao thức bảo toàn tổng.
- Một shard lỗi có thể giữ ngân sách chưa dùng.
- Theo dõi và reconciliation phức tạp.
- Phải xác định người dùng nào có thể dùng shard nào.

### 17.4. Strict cap và overbooking

Một số doanh nghiệp chủ động **overbook** với một ngưỡng nhất định, dựa trên dự báo hủy. Đây là chính sách nghiệp vụ khác, không phải lỗi race condition.

Nếu cho phép overbooking, invariant phải đổi thành giới hạn được phê duyệt, ví dụ:

\[
\mathrm{confirmed}+\mathrm{held}\le \mathrm{allowedLimit}
\]

với `allowedLimit` được quản trị rõ. Không được dùng cấu hình overbooking để che giấu việc hệ không bảo vệ concurrency.

---

## 18. Quota đồng thời khác quota theo thời gian

### 18.1. Quota “100 lượt trong ngày”

Key logic:

~~~text
(tenantId, operationType, UTC_DAY)
~~~

Một conditional increment:

~~~text
if used + requestCost <= limit:
  used += requestCost
  allow
else:
  reject
~~~

Cần xác định timezone, ngày nghiệp vụ, khi nào reset và có hoàn lượt khi request lỗi hay không.

### 18.2. Concurrency limit “20 job đang chạy”

Bất biến:

\[
activeLeases\le 20.
\]

Lúc job bắt đầu, reserve một lease. Khi job kết thúc, release. Nếu worker chết, lease có thể hết hạn và được tái cấp. Do đó cần chống **worker cũ tiếp tục ghi** sau khi mất lease bằng fencing token nếu side effect quan trọng.

### 18.3. Rate limit

Token bucket/sliding window quản lý **tốc độ** chứ không hẳn là tồn kho. Token có thể được tiêu dùng theo request mà không hoàn lại, tùy hợp đồng. Không nên đồng nhất việc “trả slot” với việc “hoàn token” trong mọi hệ.

### 18.4. Quota theo tenant

Khi limit là 100 request/ngày/tenant, key phải chứa tenant ID và backend phải lấy tenant được phép từ authentication/authorization. Không chỉ tin một trường `tenantId` do client gửi.

---

## 19. Tính nhất quán của read model và số lượng hiển thị

Hệ thương mại điện tử có thể hiển thị `available = 3` từ Redis cache hoặc search index, trong khi nguồn authoritative đã hết hàng.

Đó là một vấn đề hiển thị:

~~~text
Read model says: 3 left
Authoritative conditional reserve: OUT_OF_CAPACITY
~~~

Không nên để frontend dựa vào con số cache rồi cam kết đơn đã được giữ.

### 19.1. Hai loại dữ liệu

- **Authoritative allocation state:** quyết định có cấp tài nguyên không.
- **Read model/display state:** hiển thị số lượng gần đúng và tìm kiếm.

Read model có thể eventual nếu UX chấp nhận; API reserve phải có kết quả từ nguồn quyết định.

### 19.2. Cập nhật cache sau commit

Sau khi transaction reserve commit, có thể phát event cập nhật cache. Nếu event trễ, số hiển thị tạm thời cũ. Không được dựa vào cache để phục hồi counter nếu nó không phải nguồn sự thật.

### 19.3. Underutilization an toàn hơn overselling

Nếu expiry worker chậm, `held` vẫn chiếm chỗ dù deadline đã qua. Đây là **capacity leakage tạm thời** và ảnh hưởng doanh thu/trải nghiệm.

Nhưng nếu hệ tự tăng `available` trước khi state thực sự hết hiệu lực, một payment callback có thể confirm cùng giữ chỗ và gây over-allocation. Khi phải lựa chọn, hệ strict nên **ưu tiên bất biến**, đồng thời dùng metrics và worker đáng tin để giảm leakage.

---

## 20. Tính đúng khi thanh toán và các hệ ngoài DB

Giữ chỗ không đồng nghĩa đã thu tiền. Các thành phần có thể gồm:

~~~mermaid
sequenceDiagram
    participant User as User
    participant Order as Order service
    participant DB as Reservation store
    participant Pay as Payment provider
    participant Worker as Outbox/expiry worker

    User->>Order: Reserve 2 units
    Order->>DB: Atomic hold + reservation
    DB-->>Order: HELD
    Order-->>User: Hold id + deadline
    User->>Order: Start payment
    Order->>Pay: Charge with idempotency key
    Pay-->>Order: Payment result/callback
    Order->>DB: Confirm if HELD and within policy
    DB-->>Order: CONFIRMED or EXPIRED
    Worker->>DB: Expire stale HELD records
~~~

Các bước qua payment provider và DB **không nằm trong một transaction thông thường**. Cần xử lý callback đến trễ, trùng hoặc out-of-order.

### 20.1. Callback đến sau expiry

Ví dụ:

~~~text
10:00 Hold created, expires 10:10
10:09 Payment initiated
10:11 Payment succeeded callback arrives
10:10 Expiry worker already released hold
~~~

Không được tự confirm hold đã `EXPIRED` mà không có quy trình cấp phát lại. Có thể cần:

- Refund/void thanh toán.
- Thử cấp phát mới nếu nghiệp vụ cho phép và còn hàng.
- Giữ trạng thái cần đối soát/điều tra.
- Quy tắc riêng cho payment đang xử lý trước deadline, nếu được thiết kế sẵn.

### 20.2. Callback lặp

Payment provider có thể gửi cùng callback nhiều lần. Nếu callback đầu đã `HELD -> CONFIRMED`, callback sau phải thấy `CONFIRMED` và **không tăng confirmed lần nữa**.

### 20.3. Outbox

Để thông báo downstream về một reservation được confirm, có thể ghi một outbox event trong cùng transaction với state transition nếu DBMS hỗ trợ phù hợp. Worker publish event, consumer xử lý idempotent.

Không gửi event từ code giữa transaction nếu callback transaction có thể retry. Nếu event gửi thành công rồi transaction rollback, downstream có thể quan sát sai.

---

## 21. Failure matrix: điều gì có thể hỏng?

| Thời điểm lỗi | Hậu quả nếu thiết kế yếu | Cách bảo vệ |
|---|---|---|
| Hai request cùng thấy available=1 | Cấp 2/1 | Atomic conditional reserve |
| Counter trừ xong, reservation chưa tạo | Mất slot không có chủ | Transaction hoặc protocol đối soát |
| Reservation tạo xong, counter chưa trừ | Hold không được bảo đảm | Transaction/cấp phát có điều kiện |
| Response reserve bị mất | Retry tạo hai hold | Idempotency key và unique guard |
| Confirm và expiry chạy cùng lúc | Vừa bán vừa trả slot | State transition có điều kiện, atomic |
| Cancel bị retry | Hoàn lại nhiều lần | Release chỉ từ `HELD` |
| Expiry worker chết | Slot treo | Retry + expiry index + reconciliation |
| Dữ liệu expiry bị TTL xóa sớm | Không còn bằng chứng release | Chỉ TTL record terminal phù hợp |
| Payment callback đến trễ | Thu tiền nhưng đã hết hold | Refund/reconciliation hoặc policy xử lý riêng |
| Replica/index lag | Hiển thị còn hàng dù đã hết | Quyết định từ nguồn authoritative |
| Mất node sau ACK yếu | Hold mới có thể biến mất | Durability/replication phù hợp |
| Thay đổi quota đồng thời | Có thể cấp vượt hạn mới | Update capacity có điều kiện |
| Job cũ chạy sau hết lease | Hai worker cùng thao tác | Fencing token |
| Shard được phân quota sai | Tổng grant vượt capacity | Escrow/budget invariant |

### 21.1. Cần bảo vệ cả durability

Một reservation được ghi nguyên tử trên một node nhưng biến mất sau failover vì ACK/persistence yếu cũng có thể tạo hậu quả lớn:

~~~text
Client nhận HELD
Client tiến hành thanh toán
Primary mất write và failover
Reservation không còn ở nguồn mới
~~~

**Atomicity chống race trong phạm vi thao tác; durability bảo vệ write sau sự cố.** Cả hai cần được xem xét nếu một hold là lời hứa có giá trị.

### 21.2. Đừng giả định timeout là thất bại

Một write có thể commit nhưng client không nhận phản hồi. Khi retry, phải đọc theo ID ổn định hoặc dùng transaction idempotency semantics phù hợp, không tạo reservation mới.

---

## 22. Reconciliation: khôi phục bất biến khi có lỗi ngoài ý muốn

Ngay cả khi dùng transaction, hệ vẫn cần đối soát để phát hiện bug, migration sai, manual update hoặc dữ liệu từ phiên bản cũ.

### 22.1. Đối soát tổng số lượng

Giả sử resource có:

~~~text
capacity = 100
available = 17
held = 8
confirmed = 75
~~~

Kiểm tra:

\[
17+8+75=100.
\]

Sau đó kiểm tra `held` với ledger `HELD` và `confirmed` với tập cấp phát có thẩm quyền theo thời điểm snapshot nhất quán.

Một phép đối soát trong lúc hệ liên tục cập nhật có thể thấy lệch **ảo** nếu đọc hai collection ở những thời điểm khác nhau. Cần snapshot/version/watermark hoặc quy trình cố định phạm vi phù hợp.

### 22.2. Không tự sửa counter bằng một tổng eventual

Nếu một scan từ secondary index chưa bắt kịp báo `held=7` trong khi nguồn authoritative đang có 8, việc tự đặt counter thành 7 có thể giải phóng sai 1 slot.

Reconciliation cần:

1. Xác định nguồn sự thật.
2. Chọn mốc nhất quán.
3. Tính và giải thích sai lệch.
4. Chặn ghi hoặc áp dụng repair có kiểm soát.
5. Ghi audit ai/cơ chế nào sửa.
6. Theo dõi xem sai lệch có lặp lại không.

### 22.3. Sự kiện terminal nên được giữ đủ lâu

Reservation `CANCELLED`, `EXPIRED` và `CONFIRMED` cung cấp bằng chứng xử lý khi retry/callback cũ quay lại. Xóa quá sớm có thể làm hệ quên lịch sử và cấp thêm. Retention cần bám thời gian tối đa của retry, payment callback, chargeback và yêu cầu audit phù hợp.

---

## 23. Quan sát: metric nào cho biết hệ đang an toàn?

| Nhóm | Metric/câu hỏi | Mục đích |
|---|---|---|
| Bất biến | `available + held + confirmed == capacity` | Phát hiện sai tổng |
| Safety | Số lần `available < 0` hoặc grant vượt giới hạn | Lỗi nghiêm trọng |
| Demand | Reserve requests/s, accepted/s, rejected/s | Tải và nhu cầu thực |
| Contention | CAS/conditional failure rate | Hot key và cạnh tranh |
| Latency | Reserve/confirm/cancel p95, p99 | SLO người dùng |
| Expiry | Expiry backlog và release lag | Capacity leakage |
| State | Hold theo tuổi, số HELD quá hạn | Phát hiện worker chậm |
| Idempotency | Duplicate request/replayed callback | Retry và networking |
| Payment | Paid-but-expired, refund/reconcile rate | Vấn đề giữa dịch vụ |
| Data correctness | Counter-ledger mismatch | Sự cố đồng bộ |
| Durability | Write timeouts, replication lag, rollback | Mất hold sau failover |
| Hot partition | Writes/s theo resource, throttling | Quyết định sharding/escrow |
| Fairness | Wait time, tỷ lệ reject theo tenant | Tránh độc quyền tài nguyên |
| Cost | Transaction units, storage, index/queue overhead | Dự báo chi phí |

### 23.1. Tạo cảnh báo theo mức độ

- **Nghiêm trọng:** `available < 0`, tổng cấp vượt capacity, một seat có hai reservation CONFIRMED.
- **Cao:** ledger/counter mismatch, confirm và expiry đều báo thành công trên một hold.
- **Vừa:** expiry lag quá ngưỡng, tỷ lệ conditional retries tăng, hot resource throttling.
- **Thông tin:** số hold hủy, tỷ lệ không hoàn tất thanh toán, số request idempotent.

Không nên chỉ theo dõi số request trả HTTP 200. Cần metric phản ánh **bất biến nghiệp vụ**.

## 24. Bảo mật và phạm vi tenant

Trong multi-tenant NoSQL:

- Resource phải gắn tenant hoặc namespace rõ.
- Chỉ cho phép caller tác động reservation thuộc tenant/quyền của họ.
- Không cho client tự thay `quantity`, `resourceId`, `expiresAt` ngoài chính sách.
- RequestId nên unique trong phạm vi đã định; không trộn giữa tenant.
- API confirm/cancel phải kiểm tra chủ sở hữu hoặc quyền dịch vụ.
- Log không tiết lộ thông tin cá nhân/payment không cần thiết.
- Admin capacity change cần audit.
- Rate limiting bảo vệ endpoint reserve khỏi spam giữ chỗ nhằm khóa hàng đối thủ.

Một conditional update đúng về số lượng nhưng thiếu authorization vẫn có thể làm khách A hủy hold của khách B và trả hàng trái phép.

### 24.1. Giữ chỗ giả để chiếm hàng

Một tác nhân có thể liên tục reserve toàn bộ inventory rồi chờ expiry, khiến người thật không mua được dù hệ không oversell.

Biện pháp có thể gồm:

- Giới hạn số hold đang hoạt động theo tài khoản/thiết bị/tenant.
- Rate limit và chống bot theo chính sách sản phẩm.
- Deadline giữ ngắn phù hợp UX.
- Không gia hạn vô hạn.
- Ưu tiên/fair queue khi cạnh tranh cao.
- Phân biệt hold đã bắt đầu thanh toán với hold không có hoạt động.

**Safety không đồng nghĩa fairness hoặc availability.** Hệ có thể không oversell nhưng vẫn bị lạm dụng làm cạn slot.

---

## 25. Kiểm thử concurrency: không chỉ chạy từng request riêng

Một bộ test cần kiểm tra invariant dưới cạnh tranh và lỗi.

### 25.1. Test chiếc vé cuối

~~~text
capacity=1
100 request đồng thời, mỗi request hold qty=1
```

Kỳ vọng trong hệ strict:

~~~text
successfulDistinctReservations <= 1
available >= 0
held + confirmed <= 1
```

Nếu mọi request dùng ID khác, tối đa một request được cấp. Những request thất bại vì hết hàng phải được phân biệt với timeout/unknown.

### 25.2. Test 100 vé cho nhiều request

~~~text
capacity=100
1.000 request đồng thời, mỗi request qty=1
```

Kỳ vọng:

- Không có thời điểm authoritative allocation vượt 100.
- Số hold thành công không vượt 100.
- Sau khi cancel/expire đúng các hold, `available` trở lại theo công thức.
- Retry cùng ID không chiếm thêm slot.

### 25.3. Test confirm vs expire

Cho một reservation gần deadline:

~~~text
Thread A: confirm
Thread B: expire
```

Kỳ vọng chỉ một transition terminal thành công. Counter chỉ đổi một lần, theo hướng tương ứng.

### 25.4. Test crash giữa các bước

Nếu hệ dùng counter và reservation ở hai nơi, giả lập crash tại:

1. Trước khi ghi counter.
2. Sau khi giữ counter nhưng trước record.
3. Sau khi ghi record nhưng trước response.
4. Sau transaction commit nhưng trước publish event.
5. Sau release nhưng trước ACK cho expiry worker.

Nếu có transaction đúng phạm vi, những trạng thái nửa vời phải không thể trở thành committed state. Nếu dùng saga, phải có đường reconciliation/compensation để phục hồi.

### 25.5. Test với dữ liệu thực và workload nóng

Trên môi trường thử nghiệm:

- Tạo phân bố nhiều SKU ít tải và một SKU cực nóng.
- Chạy reserve/cancel/confirm lặp, với retry và latency mạng.
- Kiểm tra p95/p99, conflict, throttling, expiry backlog.
- Thử primary failover/replica lag nếu được phép.
- Đối soát mọi reservation thành công.

Không chủ động gây hỏng production để kiểm tra race hoặc durability.

### 25.6. Một bộ assertion logic

~~~java
record ResourceSnapshot(
    long capacity,
    long available,
    long held,
    long confirmed
) {}

static void assertInvariant(ResourceSnapshot s) {
    if (s.available() < 0 || s.held() < 0
            || s.confirmed() < 0) {
        throw new AssertionError("Negative counter");
    }

    if (s.available() + s.held() + s.confirmed()
            != s.capacity()) {
        throw new AssertionError("Capacity invariant broken");
    }
}
~~~

**Cần đọc snapshot authoritative một cách nhất quán** để assertion không báo sai do đọc từng counter ở các thời điểm khác nhau. Code chỉ minh họa ý tưởng invariant.

---

## 26. Bài tập thực hành: 100 vé sự kiện

Bối cảnh:

~~~text
Event ID: event-42
Số vé: 100
Hold TTL: 10 phút
Mức mua tối đa: 4 vé/request
Có 3.000 request reserve trong 5 giây
Payment callback có thể tới trễ hoặc gửi lại
Reservation cần theo dõi theo customerId
Ứng dụng có nhiều instance Java
```

### Yêu cầu 1: thiết kế bất biến

Đặt các biến:

\[
C=100,\quad A+H+S=C.
\]

Định nghĩa điều kiện giữ mới, confirm và release sao cho không oversell.

### Yêu cầu 2: thiết kế schema

Đề xuất ít nhất hai loại document/item:

~~~json
{
  "resourceId": "event-42",
  "capacity": 100,
  "available": 100,
  "held": 0,
  "confirmed": 0
}
~~~

~~~json
{
  "reservationId": "res-9001",
  "requestId": "client-intent-001",
  "resourceId": "event-42",
  "customerId": "customer-42",
  "quantity": 2,
  "state": "HELD",
  "expiresAt": "2026-11-14T08:10:00Z"
}
~~~

Chỉ ra unique constraint hoặc conditional insert cần dùng để chống retry.

### Yêu cầu 3: chọn công nghệ

So sánh:

1. MongoDB atomic update + transaction.
2. DynamoDB conditional update + TransactWriteItems.
3. Cassandra LWT với hạn chế khi cần hai partition.
4. Redis Lua cùng durability/replication policy.

Đối với từng phương án, trả lời:

- **Điểm quyết định capacity nằm ở đâu?**
- **Reservation record và counter có atomic không?**
- **Hai request cùng giữ vé cuối được giải quyết thế nào?**
- **Timeout sau commit được xử lý ra sao?**
- **Mất primary sau ACK có thể gây vấn đề gì?**

### Yêu cầu 4: viết API

Thiết kế:

~~~http
POST /reservations
POST /reservations/{id}/confirm
POST /reservations/{id}/cancel
GET  /reservations/{id}
~~~

Với mỗi endpoint, ghi:

- Authorization.
- Idempotency key.
- Preconditions.
- Conditional state transition.
- Response khi thiếu capacity, expired, conflict hoặc unknown.
- Các side effect/notifications được gửi sau commit bằng cách nào.

### Yêu cầu 5: expiry worker

Thiết kế:

- Cách lấy những hold đến hạn.
- Cách claim/retry.
- Điều kiện `HELD -> EXPIRED`.
- Cách cập nhật counter một lần duy nhất.
- Xử lý concurrent payment confirm.
- Reconciliation nếu worker chết.

### Yêu cầu 6: performance

Giả sử 3.000 request trong 5 giây tranh một resource; tính tải trung bình:

\[
\lambda = 3000 / 5 = 600\ \text{request/giây}.
\]

Hãy giải thích:

- Tại sao contention có thể rất cao dù database có throughput lớn?
- Khi nào chỉ có 100 vé mà 3.000 request vẫn hợp lý để reject sớm?
- Có cần escrow/sharding không?
- Những metric nào để quyết định?
- Tối ưu read model có thay thế được atomic grant không?

### Gợi ý lời giải

Một hướng cho strict capacity:

1. Resource authoritative có `available`, `held`, `confirmed`.
2. API validate `1 <= qty <= 4`, tenant và request ID.
3. Transaction/atomic protocol giữ chỗ khi `available >= qty`.
4. Cùng đơn vị đúng đắn tạo record `HELD` và trừ counter.
5. Payment confirm chỉ khi state còn HELD và chưa hết deadline.
6. Cancel/expire release với conditional state transition.
7. TTL dọn terminal record **sau** khi các tác vụ nghiệp vụ hoàn tất.
8. Retry không tạo hold mới với cùng request ID.
9. Reconciliation phát hiện counter/ledger mismatch.
10. Thử 3.000 request đồng thời với khả năng timeout/failover.

## 27. Bài tập thực hành: quota 20 job đồng thời

Một nền tảng xử lý background job giới hạn 20 job cho mỗi tenant.

Yêu cầu:

- Cho phép reserve slot khi `activeLeases < 20`.
- Mỗi slot có `leaseId`, `ownerId`, `expiresAt`, `generation`.
- Worker heartbeat gia hạn lease.
- Worker chết thì slot được thu hồi.
- Worker cũ thức dậy sau khi mất lease không được ghi kết quả của phiên mới.
- Một job retry không nhận hai lease đồng thời.

Cần giải thích vì sao:

- `INCR active` riêng lẻ có thể làm vượt limit nếu không có điều kiện.
- TTL xóa lease không tự giảm counter.
- Release phải idempotent.
- Fencing token cần được kiểm tra bởi nơi ghi kết quả.
- Giới hạn per-tenant phải được bảo vệ cả khi nhiều Java worker instance cùng thao tác.

## 28. Những sai lầm phổ biến

| Sai lầm | Hậu quả | Cách làm đúng |
|---|---|---|
| Đọc available rồi kiểm tra ở Java | Hai request cùng giữ phần cuối | Atomic conditional grant |
| Chỉ dùng atomic decrement, không tạo hold cùng scope đúng | Lost reservation hoặc leaked capacity | Transaction/protocol có recovery |
| Dùng counter được cache để quyết định | Oversell khi cache stale | Quyết định từ authoritative state |
| `available` âm vẫn chấp nhận | Vượt giới hạn | Preconditions và assertions |
| Retry bằng reservation ID mới | Giữ chỗ nhiều lần | Stable request/reservation ID |
| Cancel/expire cộng lại không kiểm tra state | Double release | Chỉ release từ `HELD` một lần |
| Confirm không kiểm tra deadline | Bán hold đã hết hạn | Conditional transition theo authoritative time |
| Redis TTL tự giải phóng counter | Counter treo hoặc mất chứng cứ | Expiry worker atomically release |
| DynamoDB TTL được coi như transaction | Item bị xóa nhưng stock không trả | State machine + transaction |
| Cassandra QUORUM được coi như transaction multi-partition | Counter/ledger có thể lệch | Hiểu CL/LWT và giới hạn |
| LWT không giới hạn retry | Hot key gây nghẽn | Retry budget, backoff, contention metrics |
| Redis Lua được coi như durability đa node | Mất hold sau failover | Persistence/replication/failure model |
| Payment callback tự bán hàng nếu đã thu tiền | Oversell sau expiry | Reconcile/refund hoặc cấp lại theo policy |
| Snapshot read model dùng sửa counter | Sai do eventual lag | Reconciliation từ nguồn nhất quán |
| Split counter mà không chia ngân sách | Shards cùng cấp vượt tổng | Escrow/preallocated quota |
| Lease hết hạn là worker cũ tự dừng | Stale worker có thể gây side effect | Fencing token |
| Không giới hạn số hold mỗi user | Bot giữ hết hàng | Fairness/rate limit/abuse controls |
| Dùng lock trong JVM cho nhiều service instance | Instance khác không tôn trọng lock | Atomic DB or distributed protocol |
| Chỉ test tuần tự | Không phát hiện race | Concurrency/failure injection tests |
| Chỉ theo dõi HTTP 200 | Không phát hiện sai tổng | Invariant/reconciliation/expiry metrics |

---

## 29. Tổng kết

**Giữ chỗ tài nguyên và giới hạn số lượng được cấp** là bài toán về **tính đúng đắn dưới concurrency**, không chỉ là việc giảm một counter.

Các nguyên tắc quan trọng:

1. **Định nghĩa invariant trước:** `available + held + confirmed = capacity`, các giá trị không âm và không cấp vượt limit.
2. **Cấp phát nguyên tử có điều kiện:** không thực hiện `read -> if -> write` như nhiều thao tác tách biệt có thể tranh chấp.
3. **Counter và reservation phải đi cùng quy trình đúng đắn:** transaction khi có thể, hoặc giao thức có idempotency/recovery/reconciliation khi không có atomicity chung.
4. **State machine rõ ràng:** `HELD`, `CONFIRMED`, `CANCELLED`, `EXPIRED` và các transition hợp lệ.
5. **Confirm, cancel và expire cạnh tranh an toàn:** mỗi hold chỉ được confirm hoặc release đúng một lần.
6. **TTL không đồng nghĩa hoàn lại capacity:** background expiration và conditional release phải được tách bạch.
7. **Retry có ID ổn định:** network timeout không chứng minh write chưa commit.
8. **Hiểu giới hạn DBMS:** MongoDB document atomicity/transaction, DynamoDB condition/transaction, Cassandra LWT, Redis Lua và durability.
9. **Hot resource cần chiến lược:** CAS contention, preallocated quota/escrow và fairness, nhưng không phá invariant.
10. **Theo dõi và diễn tập:** metric safety, expiry lag, payment mismatch, reconcile và failure test.

**Một hệ NoSQL cấp phát tài nguyên đáng tin cậy không chỉ biết “còn bao nhiêu”, mà phải bảo đảm “ai đã được giữ bao nhiêu, trong bao lâu, điều kiện nào được phép xác nhận và làm thế nào không một tài nguyên nào bị cấp hoặc hoàn lại hai lần”.**
