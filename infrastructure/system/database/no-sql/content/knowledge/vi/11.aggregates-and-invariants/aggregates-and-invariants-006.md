# Đặt hàng, giữ chỗ và các bất biến liên quan đến số lượng

Trong một ứng dụng NoSQL, lưu một đơn hàng (order) hay một bản ghi giữ chỗ (reservation) rất dễ. Bài toán khó hơn nhiều là **không cấp một số lượng hữu hạn cho nhiều người hơn mức cho phép**, ngay cả khi hàng trăm khách cùng đặt, máy chủ bị lỗi, người dùng thanh toán chậm hoặc cùng một yêu cầu bị gửi lại. Đây là bài học điển hình của chương **Nhóm dữ liệu và bất biến**: phải xác định điều kiện nào luôn đúng, đặt ranh giới nhóm dữ liệu phù hợp, rồi chọn thao tác đủ nguyên tử để giữ điều kiện đó.

Hãy tưởng tượng buổi học có 12 vé phổ thông, khách được giữ vé trong 10 phút trước khi thanh toán. Nếu chỉ còn một vé mà hai yêu cầu cùng đọc “còn một” rồi cùng tạo đơn thành công, hệ thống đã bán trùng, dù mỗi câu lệnh đọc/ghi riêng lẻ đều chạy đúng.

Bài học dùng ví dụ vé có số lượng cố định để giải thích nguồn cung, giữ chỗ, xác nhận và hoàn chỗ. Sau đó mở rộng sang tồn kho thực tế, nhiều SKU, nhiều kho, ghế đánh số và quota xuyên vùng. Các ví dụ MongoDB, Redis và một số cơ chế NoSQL khác nhằm trình bày **cách suy luận**, không khẳng định mọi phiên bản hay topology có cùng bảo đảm.

## 1. Xác định đúng thực thể và trách nhiệm

Đối với một lệnh đặt chỗ, thường có ít nhất bốn thực thể:

| Thực thể | Thông tin chính | Câu hỏi nó chịu trách nhiệm |
|---|---|---|
| `CapacityPool` | Sức chứa, số còn có thể giữ, đang giữ, đã xác nhận | Pool còn đủ quota không? |
| `Reservation` | ID, pool, user, quantity, trạng thái, thời hạn | Ai đang giữ bao nhiêu và đến khi nào? |
| `Order` | Dòng hàng, giá chốt, khách, vòng đời đơn | Khách đặt những gì, đơn ở trạng thái nào? |
| `PaymentAttempt` | ID lần thanh toán, trạng thái authorize/capture/refund | Có xử lý thanh toán lặp không? |

Để vận hành còn có thể cần `InventoryLedger` (nhật ký bút toán số lượng) và `OutboxEvent` (sự kiện đã commit cần đồng bộ sang hệ khác). Không bắt buộc phải tách mọi thực thể thành database riêng, nhưng phải xác định rõ **nguồn dữ liệu có thẩm quyền** cho từng bất biến.

Một pool minh họa:

~~~json
{
  "_id": "event-42:standard",
  "capacity": 12,
  "available": 12,
  "held": 0,
  "confirmed": 0,
  "version": 1
}
~~~

Reservation được tạo sau khi giữ hai suất thành công:

~~~json
{
  "_id": "res-1001",
  "poolId": "event-42:standard",
  "orderId": "ord-7788",
  "customerId": "u42",
  "quantity": 2,
  "status": "HELD",
  "createdAt": "2026-11-14T09:00:00Z",
  "expiresAt": "2026-11-14T09:10:00Z"
}
~~~

Trong mô hình này, `confirmed` là số vé đã bán **vẫn chiếm sức chứa**, không phải lượng hàng vật lý đã xuất kho. Khi chuyển sang thương mại điện tử, phải phân biệt các bộ đếm theo quy tắc kho thật.

## 2. Viết bất biến bằng công thức trước khi viết API

Gọi:

- `C`: sức chứa được cấp của pool.
- `A`: số lượng có thể giữ mới.
- `H`: số lượng đang được giữ hợp lệ.
- `K`: số lượng đã xác nhận vẫn chiếm quota.

Bất biến bảo toàn:

\[
C = A + H + K
\]

và:

\[
C,A,H,K \in \mathbb{Z}_{\ge 0}
\]

Một yêu cầu giữ `q` suất cần `q>0` và `A\ge q`. Khi thành công:

\[
(A,H,K)\longrightarrow(A-q,H+q,K)
\]

Khi xác nhận một giữ chỗ còn hiệu lực:

\[
(A,H,K)\longrightarrow(A,H-q,K+q)
\]

Khi hủy hoặc hết hạn trước khi xác nhận:

\[
(A,H,K)\longrightarrow(A+q,H-q,K)
\]

| Chuyển trạng thái | Available | Held | Confirmed | Điều kiện |
|---|---:|---:|---:|---|
| Hold `q` | −q | +q | 0 | `q>0`, `A≥q` |
| Confirm `q` | 0 | −q | +q | Reservation còn `HELD`, chưa quá hạn |
| Cancel/expire hold `q` | +q | −q | 0 | Chỉ áp dụng cho `HELD` một lần |
| Tăng capacity `q` | +q | 0 | 0 | Đồng thời `C+=q` |
| Giảm capacity `q` | −q | 0 | 0 | `A≥q`, đồng thời `C-=q` |
| Hủy vé đã xác nhận và được bán lại | +q | 0 | −q | Quy tắc nghiệp vụ cho phép |

Các số lượng nên là **số nguyên có giới hạn**, validate tại biên API: cấm quantity âm, bằng 0, vượt mức mua, vượt phạm vi số nguyên hoặc thuộc pool không tồn tại. Dùng số nguyên cho lượng hàng; với giá tiền thường dùng đơn vị nhỏ nhất hoặc kiểu decimal phù hợp, không dùng phép tính float tùy tiện cho số tiền.

Bảo toàn counter chưa đủ. Cần thêm những bất biến xuyên thực thể:

1. Một Reservation không thể đồng thời `CONFIRMED` và `EXPIRED`.
2. Retry cùng ý định không cấp quota thêm lần nữa.
3. Một Order được báo `HELD` chỉ khi đủ tất cả các dòng bắt buộc.
4. Không capture payment lần thứ hai vì response lần đầu bị mất.
5. Một ghế đánh số không có hai người giữ hợp lệ cùng lúc.
6. Nếu một thao tác thất bại giữa chừng, không có quota bị kẹt vô hạn mà không thể phát hiện/khôi phục.

## 3. Race condition của check-then-write

Giả sử `available=1`:

~~~text
Request A                         Request B
---------                         ---------
READ available -> 1
                                  READ available -> 1
IF available >= 1: TRUE
                                  IF available >= 1: TRUE
WRITE available = 0
                                  WRITE available = 0
CREATE reservation A
                                  CREATE reservation B
~~~

Hai Reservation đã được tạo nhưng chỉ có một suất. Đây là lỗi **read–check–write không nguyên tử**. Lock trong bộ nhớ một tiến trình không ngăn các API instance khác đọc và ghi cùng pool; cache còn có thể làm giá trị đọc chậm cập nhật hơn.

Quyết định cấp quyền cần một thao tác như:

~~~text
ATOMIC:
  IF available >= quantity
     available -= quantity
     held += quantity
     return SUCCESS
  ELSE
     return INSUFFICIENT_CAPACITY
~~~

Cách triển khai có thể là conditional update, compare-and-swap, transaction hoặc command handler tuần tự hóa. Một distributed lock có thời hạn cũng không tự bảo vệ bất biến nếu chủ sở hữu lock cũ hết lease nhưng vẫn ghi; cần cơ chế version/fencing ở nguồn dữ liệu.

## 4. Aggregate root và ranh giới nguyên tử

**Aggregate root** là nơi các thao tác phải đi qua để bảo vệ một tập bất biến. Với quota 12 vé, pool có thể là root giữ sức chứa. Nhưng Reservation có vòng đời riêng và số lượng record tăng theo thời gian; không nên nhúng hàng triệu Reservation vào đúng một document chỉ vì muốn cập nhật nguyên tử.

Hai thiết kế điển hình:

**Thiết kế A: tính tổng Reservation mỗi lần giữ.**

~~~text
used = SUM(quantity WHERE status IN ('HELD','CONFIRMED'))
IF used + requested <= capacity:
    INSERT reservation
~~~

Nếu không có transaction/cơ chế cô lập phù hợp, nhiều request đồng thời có thể cùng thấy tổng cũ rồi tạo Reservation. Một câu query tổng nhanh không trở thành khóa nghiệp vụ.

**Thiết kế B: counter có thẩm quyền trong pool.**

~~~text
CapacityPool
  capacity = 12
  available = 7
  held = 3
  confirmed = 2

Reservation res-1: HELD, quantity=2
Reservation res-2: HELD, quantity=1
...
~~~

Conditional update có thể giữ counter không âm. Nhưng nếu giảm pool thành công rồi process chết trước khi tạo Reservation, một lượng quota bị giữ mà không có record để hết hạn. Vì vậy **bất biến nội bộ pool** và **tính nhất quán pool–Reservation** là hai tầng riêng.

Ba cách kết nối:

- Transaction nhiều document nếu engine/topology đáp ứng phạm vi yêu cầu.
- Một aggregate document nhỏ chứa đúng những dữ liệu cần cùng thao tác (tránh danh sách tăng vô hạn).
- Saga/state machine với ledger, idempotency và đối soát khi không có transaction.

## 5. State machine của giữ chỗ

Hệ thống cần một state machine rõ ràng, thay vì chỉ dùng cờ `reserved=true`:

~~~mermaid
flowchart TD
    A["REQUESTED"] --> B{"Pool đủ số lượng?"}
    B -->|Không| R["REJECTED"]
    B -->|Có| H["HELD"]
    H --> C["CONFIRMED"]
    H --> E["EXPIRED"]
    H --> X["CANCELLED"]
    C --> F["FULFILLED / USED"]
    C --> Y["CANCELLED_AFTER_CONFIRM nếu được phép"]
~~~

Mỗi nhánh từ `HELD` phải được bảo vệ bằng điều kiện trạng thái. Chỉ một nhánh trong `CONFIRMED`, `EXPIRED` hoặc `CANCELLED` được thắng. Xác nhận rồi không được để worker timeout trả lại quota; hết hạn rồi không được xác nhận như vẫn còn hiệu lực.

Order có state machine khác:

~~~text
CREATED -> PENDING_HOLD -> HELD -> PAYMENT_PENDING
        -> PAYMENT_AUTHORIZED -> CONFIRMED -> FULFILLMENT

Các nhánh lỗi:
PENDING_HOLD -> HOLD_FAILED
PAYMENT_PENDING -> PAYMENT_FAILED
CONFIRMED -> PAYMENT_RECONCILIATION (nếu external capture chưa rõ)
~~~

Reservation điều khiển **quyền giữ quota**; Order điều khiển **hợp đồng mua bán**; PaymentAttempt điều khiển **side effect tài chính**. Nếu gom hết vào một trạng thái `PAID` sẽ rất khó biết đã giữ đủ hàng chưa, thanh toán có thể retry được không và có cần refund hay không.

## 6. Conditional update trên một document MongoDB

Trong MongoDB, cập nhật một document có thể gắn điều kiện và các thay đổi trong cùng một thao tác nguyên tử.

~~~javascript
db.capacityPools.insertOne({
  _id: "event-42:standard",
  capacity: 12,
  available: 12,
  held: 0,
  confirmed: 0,
  version: 1
});
~~~

Giữ 2 suất khi và chỉ khi còn đủ:

~~~javascript
const quantity = 2;

const result = db.capacityPools.updateOne(
  {
    _id: "event-42:standard",
    available: { $gte: quantity }
  },
  {
    $inc: {
      available: -quantity,
      held: quantity,
      version: 1
    },
    $currentDate: { updatedAt: true }
  }
);

if (result.matchedCount !== 1) {
  print("INSUFFICIENT_CAPACITY hoặc pool không tồn tại");
}
~~~

Nếu cùng tranh suất cuối, việc kiểm tra `available >= quantity` trong update giúp tránh việc cả hai thao tác trừ dựa trên số cũ. Nhưng ví dụ **chưa tạo Reservation**. Nếu ghi pool và Reservation thành hai lệnh độc lập, crash ở giữa có thể làm mất quyền giữ hoặc tạo dữ liệu mồ côi:

~~~javascript
// KHÔNG PHẢI workflow đầy đủ khi hai lệnh nằm ngoài transaction.
db.capacityPools.updateOne(
  { _id: poolId, available: { $gte: quantity } },
  { $inc: { available: -quantity, held: quantity } }
);

// Nếu server chết tại đây, quota đã giảm nhưng Reservation chưa có.
db.reservations.insertOne({
  _id: reservationId,
  poolId,
  quantity,
  status: "HELD"
});
~~~

Cần thiết kế nguyên tử xuyên document hoặc quy trình khôi phục cụ thể. Bảo đảm một document nguyên tử không tự kéo theo bảo đảm cả workflow nhiều document nguyên tử.

## 7. Transaction giữ pool và Reservation

Ví dụ Node.js với MongoDB official driver. Nó cần topology hỗ trợ transaction, quyền truy cập đúng tenant và các collection đã tạo. Mục tiêu là thấy các bước được commit/abort cùng nhau.

~~~javascript
async function reserveSeats(client, db, command) {
  const { reservationId, orderId, poolId, quantity, now } = command;

  if (!Number.isSafeInteger(quantity) || quantity <= 0) {
    throw new Error("INVALID_QUANTITY");
  }

  const expiresAt = new Date(now.getTime() + 10 * 60 * 1000);
  const session = client.startSession();

  try {
    return await session.withTransaction(async () => {
      // Cùng reservationId là một ý định nghiệp vụ duy nhất.
      const existing = await db.collection("reservations").findOne(
        { _id: reservationId },
        { session }
      );

      if (existing) {
        const sameRequest =
          existing.orderId === orderId &&
          existing.poolId === poolId &&
          existing.quantity === quantity;

        if (!sameRequest) {
          throw new Error("IDEMPOTENCY_KEY_REUSED");
        }

        return existing; // Không trừ quota lần nữa.
      }

      const changed = await db.collection("capacityPools").updateOne(
        {
          _id: poolId,
          available: { $gte: quantity }
        },
        {
          $inc: {
            available: -quantity,
            held: quantity,
            version: 1
          }
        },
        { session }
      );

      if (changed.matchedCount !== 1) {
        throw new Error("INSUFFICIENT_CAPACITY");
      }

      const reservation = {
        _id: reservationId,
        orderId,
        poolId,
        quantity,
        status: "HELD",
        createdAt: now,
        expiresAt
      };

      await db.collection("reservations").insertOne(
        reservation,
        { session }
      );

      return reservation;
    }, {
      readConcern: { level: "snapshot" },
      writeConcern: { w: "majority" }
    });
  } finally {
    await session.endSession();
  }
}
~~~

Ý nghĩa:

1. `reservationId` được tạo **ổn định** cho một ý định, không tạo ID mới khi retry.
2. Kiểm tra và giảm pool nằm trong một update có điều kiện.
3. Insert Reservation và sửa pool cùng transaction.
4. `_id` của Reservation có ràng buộc duy nhất; nếu gặp race/duplicate key cần xử lý theo trạng thái transaction và trả lại kết quả hiện hữu.
5. Một commit có thể thành công nhưng client không nhận được phản hồi. Retry cùng ID phải cho kết quả cũ, không cấp thêm quota.
6. Callback transaction có thể chạy lại do write conflict/retry; **không gọi payment provider hoặc gửi email bên trong callback**.

Ví dụ bỏ qua nhiều yếu tố cần có khi production: xác thực user, giới hạn số vé mỗi người, unique idempotency scope, xử lý retry/backoff có giới hạn, deadline thống nhất, mapping lỗi API và monitoring. Nó cũng không chốt Order; nếu Order phải chuyển trạng thái cùng lúc, cần đưa cập nhật đó vào ranh giới giao dịch hoặc thiết kế workflow phù hợp.

## 8. Confirm: chuyển từ HELD sang CONFIRMED đúng một lần

Khi thanh toán được authorize và Reservation còn hợp lệ:

~~~text
Reservation: HELD -> CONFIRMED
Pool:
  held      -= quantity
  confirmed += quantity
Order:
  đổi trạng thái theo chính sách
Outbox:
  ghi sự kiện đã xác nhận
~~~

Một giao thức:

~~~text
BEGIN TRANSACTION
  require reservation.status == HELD
  require reservation.expiresAt > authoritativeNow
  require payment authorization hợp lệ theo workflow

  conditional UPDATE reservation:
       HELD -> CONFIRMED

  UPDATE pool:
       held -= quantity
       confirmed += quantity

  UPDATE order to expected state
  INSERT outbox event with stable event ID
COMMIT
~~~

Truy vấn điều kiện MongoDB trên Reservation:

~~~javascript
db.reservations.updateOne(
  {
    _id: reservationId,
    status: "HELD",
    expiresAt: { $gt: now }
  },
  {
    $set: {
      status: "CONFIRMED",
      confirmedAt: now
    }
  }
);
~~~

Lệnh riêng này **chưa phải toàn bộ giải pháp** vì còn cập nhật pool và Order; cần bảo đảm các tác động cùng commit hoặc bù trừ đúng. Một lần retry thấy Reservation đã `CONFIRMED` phải trả trạng thái hiện tại, không tăng `confirmed` thêm lần nữa.

Giá trị `now` phải được xác định bằng chính sách thời gian đáng tin cậy. Một node có đồng hồ chậm không nên xác nhận hold đã hết hạn chỉ vì clock lệch. Ứng dụng cần định nghĩa rõ thời điểm chấp nhận và độ lệch thời gian được phép.

## 9. Expire và TTL không giống nhau

Đặt TTL 10 phút lên document Reservation thường chỉ yêu cầu cơ sở dữ liệu **hết hạn hoặc dọn dữ liệu**. Nó không tự tăng `available` hoặc giảm `held` ở pool. Nếu TTL xóa record trước khi đối soát, hệ có thể mất cả thông tin cần để giải phóng quota.

Worker hết hạn cần chuyển trạng thái có điều kiện:

~~~text
IF reservation.status == HELD
AND reservation.expiresAt <= authoritativeNow:
    change status to EXPIRED
    pool.held -= quantity
    pool.available += quantity
    record ledger / outbox when required
ELSE:
    do nothing
~~~

Nó phải được triển khai với transaction/compare-and-swap và cơ chế phục hồi phù hợp.

### Cuộc đua confirm–expire

~~~text
Confirm worker                      Expiry worker
--------------                      -------------
Đọc HELD                            Đọc HELD
Thử HELD -> CONFIRMED               Thử HELD -> EXPIRED

Chỉ một bước chuyển trạng thái được commit thành công.
Nhánh thua đọc lại trạng thái; không sửa counter nữa.
~~~

Nếu confirm thắng, expiry không được trả chỗ. Nếu expiry thắng, confirm bị từ chối và payment authorization cần được void/refund theo hợp đồng. Trong môi trường có transaction, một nhánh có thể bị write conflict và phải xử lý retry.

Sau khi `EXPIRED`, có thể lưu bản ghi đủ lâu cho audit/idempotency rồi mới xóa theo retention. **TTL dọn record hoàn tất khác với nghiệp vụ hoàn quota**.

## 10. Idempotency: retry không phải ý định mới

Một client có thể timeout sau khi server đã commit:

~~~text
Client                         Server
  POST /reservations --------> COMMIT thành công
  response bị mất <---X
  retry cùng key ------------> trả reservation cũ
~~~

Nếu lần retry sinh reservation ID mới, pool có thể bị trừ hai lần. Cần tách:

- Request ID của một lần gửi HTTP.
- Business idempotency key của một **ý định giữ chỗ**.
- PaymentAttempt ID của lần authorize/capture.
- Event ID của thông điệp outbox có thể publish lặp.

Ví dụ:

~~~http
POST /v1/reservations
Idempotency-Key: hold-u42-cart771-v1
Content-Type: application/json

{
  "poolId": "event-42:standard",
  "quantity": 2,
  "orderId": "ord-7788"
}
~~~

Quy tắc:

| Tình huống | Kết quả |
|---|---|
| Cùng key, cùng payload | Trả kết quả/trạng thái hiện hữu |
| Cùng key, payload khác | Từ chối xung đột rõ ràng |
| Commit thành công nhưng response mất | Retry cùng key, không giữ thêm |
| Reservation đã `EXPIRED` | Trả trạng thái hết hạn; lần giữ mới cần ý định mới |
| Consumer thấy cùng `ReservationConfirmed` nhiều lần | Dedup theo event ID, không tạo tác dụng phụ lần nữa |

Idempotency key phải gắn với user/tenant và payload đã chuẩn hóa; giữ dấu vết đủ lâu so với cửa sổ retry và đối soát. Không thể suy từ tên tính năng “exactly once” rằng mọi side effect ngoài database được xử lý đúng một lần.

## 11. Đơn hàng nhiều SKU và bất biến xuyên pool

Đơn:

~~~text
Order ord-7788:
  SKU-A, Kho HN, qty=2
  SKU-B, Kho HN, qty=1
  SKU-C, Kho HCM, qty=3
~~~

Từng pool có thể luôn giữ `available >= 0` nhưng Order lại chỉ giữ được hai trong ba dòng. Có thêm bất biến:

> Order chỉ được chuyển `HELD` hoặc `CONFIRMED` khi tất cả các dòng bắt buộc đều đã giữ/xác nhận theo chính sách nghiệp vụ.

Nếu engine hỗ trợ transaction phù hợp trên các pool:

~~~text
BEGIN TRANSACTION
  conditional reserve SKU-A qty=2
  conditional reserve SKU-B qty=1
  conditional reserve SKU-C qty=3
  create reservation records
  set Order.status = HELD
  insert outbox event
COMMIT
~~~

Một dòng không đủ → toàn bộ abort. Nhưng transaction có giới hạn và chi phí về số item/partition, thời gian, contention và topology; phải kiểm tra đúng engine.

### Saga khi không có transaction đa pool

~~~mermaid
flowchart TD
    A["Order PENDING_HOLD"] --> B["Hold SKU-A"]
    B --> C{"Thành công?"}
    C -->|Không| R["HOLD_FAILED"]
    C -->|Có| D["Hold SKU-B"]
    D --> E{"Thành công?"}
    E -->|Không| X["Release SKU-A"]
    E -->|Có| F["Hold SKU-C"]
    F --> G{"Thành công?"}
    G -->|Không| Y["Release SKU-A và SKU-B"]
    G -->|Có| H["Order HELD"]
    X --> R
    Y --> R
~~~

Mỗi hold riêng phải an toàn theo pool. Saga có trạng thái `PENDING_HOLD/PARTIAL_HOLD` và compensation được retry. Không được quảng bá Order `HELD` khi mới giữ một phần, nhưng cũng không được gọi saga là transaction nguyên tử: trong một khoảng ngắn, một phần quota đang bị giữ dù Order chưa thể hoàn tất.

## 12. Thanh toán là hệ ngoài transaction

Một database transaction không thể tự atomic commit cùng API thanh toán bên ngoài.

Một workflow có authorize/capture có thể:

1. Tạo Reservation `HELD`.
2. Gửi authorize với `paymentAttemptId` ổn định.
3. Khi authorize thành công, nếu Reservation còn hợp lệ, confirm bằng giao thức có điều kiện.
4. Capture/hoàn tất thanh toán theo chính sách nhà cung cấp.
5. Nếu capture chưa rõ kết quả, đưa Order vào trạng thái `PAYMENT_RECONCILIATION` thay vì tự đoán.
6. Gửi fulfillment/thông báo dựa trên trạng thái đã commit và event có ID ổn định.

Nếu tiền bị thu nhưng hold đã hết hạn, hệ cần void/refund/reconciliation. Nếu đã confirm nhưng capture lỗi, phải có quy tắc giữ chỗ tạm, hủy hoặc xử lý thủ công; **không tự động trả quota mà chưa biết tác động thanh toán**.

Không gọi API thanh toán trong callback transaction có thể retry. Điều này có thể tạo nhiều side effect khi database chỉ commit một lần.

## 13. Outbox và ledger

Ledger ghi thay đổi số lượng:

~~~json
{
  "_id": "ledger-hold-res1001",
  "poolId": "event-42:standard",
  "reservationId": "res-1001",
  "type": "HOLD",
  "availableDelta": -2,
  "heldDelta": 2,
  "confirmedDelta": 0,
  "occurredAt": "2026-11-14T09:00:00Z"
}
~~~

Outbox ghi event cần gửi:

~~~json
{
  "_id": "evt-res1001-held",
  "type": "ReservationHeld",
  "aggregateId": "res-1001",
  "aggregateVersion": 1,
  "status": "PENDING",
  "payload": {
    "poolId": "event-42:standard",
    "quantity": 2
  }
}
~~~

Outbox nên được ghi cùng thay đổi nghiệp vụ nếu cần bảo đảm “commit xong thì event có thể được phát lại”. Worker publish có thể crash sau khi gửi event nhưng trước khi đánh dấu `SENT`, nên downstream cần idempotent consumer.

Ledger có thể là nguồn chuẩn của kiến trúc event sourcing hoặc là hệ audit đối chiếu với pool. Phải chọn rõ ai có thẩm quyền để tránh việc một dashboard eventual consistency được sử dụng ra quyết định giữ suất cuối.

## 14. Các nhóm bảo đảm trong NoSQL

Không đúng khi nói “mọi NoSQL đều không có transaction”. Cũng không đúng khi cho rằng mọi transaction đều có phạm vi như nhau.

| Công nghệ minh họa | Cơ chế cần xem | Điểm giới hạn |
|---|---|---|
| MongoDB | Atomic document update, conditional predicate, multi-document transaction | Topology, write conflict, retry, chi phí xuyên shard |
| DynamoDB | Conditional write, CAS/version, transactional write | Giới hạn transaction, hot partition, consistency |
| Redis | Atomic commands, Lua/Functions | Cluster hash slot, durability, replication/failover |
| Cassandra/ScyllaDB | Conditional update/LWT | Partition, serial consistency, contention |
| Hệ KV/document khác | CAS, versioning hoặc transaction | Phạm vi nguyên tử là key/document/partition hay nhiều entity? |

### Conditional update kiểu DynamoDB

Pseudocode:

~~~text
UpdateItem(
  Key = { poolId: "event-42:standard" },
  ConditionExpression = "available >= :q",
  UpdateExpression = "SET available = available - :q,
                          held = held + :q"
)
~~~

Đây là biểu diễn ý tưởng, không phải request SDK hoàn chỉnh. Bảo vệ counter một item chưa bảo vệ insert Reservation ở item khác; cần transaction hoặc phục hồi.

### Atomic script kiểu Redis

~~~lua
local q = tonumber(ARGV[1])
if not q or q <= 0 or q % 1 ~= 0 then
  return redis.error_reply("INVALID_QUANTITY")
end

local available = tonumber(redis.call("HGET", KEYS[1], "available"))
if not available then
  return redis.error_reply("POOL_NOT_FOUND")
end

if available < q then
  return 0
end

redis.call("HINCRBY", KEYS[1], "available", -q)
redis.call("HINCRBY", KEYS[1], "held", q)
return 1
~~~

Script kiểm tra và dịch counter trong một lần thực thi trên server, **chưa tạo Reservation bền vững**. Với Redis Cluster, thao tác nhiều key có điều kiện slot riêng; persistence/replication và failover cũng phải được đánh giá nếu Redis là nguồn ghi có thẩm quyền.

### Conditional CQL

~~~sql
UPDATE capacity_by_pool
SET available = 9
WHERE pool_id = 'event-42:standard'
IF available = 10;
~~~

Câu này minh họa compare-and-set cho một giá trị kỳ vọng. Nó không đổi `held` cùng lúc và không chứng minh có transaction đa bảng/đa partition. Cần xem phạm vi LWT và bảo đảm theo phiên bản Cassandra/ScyllaDB.

## 15. Eventual consistency và bán trùng xuyên vùng

Nếu còn một vé và hai region đều đọc replica cũ thấy `available=1`, hai region có thể đồng thời hứa vé cho hai khách. Khi dữ liệu được merge về sau, một counter cuối cùng trông “đúng” không thể sửa lời hứa đã đưa ra.

~~~text
Region VN: available = 1 -> giữ 1
Region EU: available = 1 -> giữ 1
Replicate sau: hai Reservation thành công, chỉ có 1 suất.
~~~

Các hướng giải quyết:

- Định tuyến hold tới một **owner có thẩm quyền**.
- Dùng coordinated/conditional write với phạm vi consistency bảo vệ bất biến.
- Chia **quyền bán (escrow quota)** trước cho từng region.
- Chấp nhận overbooking chỉ nếu nghiệp vụ có chủ đích và có biện pháp xử lý rõ.

Counter CRDT có thể hợp nhất những phép tăng/giảm theo quy tắc riêng, nhưng không tự bảo vệ `available>=0` trên toàn hệ nếu mỗi replica được trừ tùy ý.

### Escrow quota

Ví dụ 100 vé:

~~~text
VN: được cấp 60 quyền giữ
EU: được cấp 30 quyền giữ
Global unallocated: 10

Tổng quyền VN + EU + unallocated = 100.
~~~

Mỗi region chỉ bán trong hạn mức đã nhận. Muốn chuyển 10 quyền từ EU sang VN phải có transfer ID/version và một giao thức không cấp trùng khi retry. Nhược điểm: VN có thể tạm hết suất trong khi EU còn quota. Escrow giảm phối hợp **mỗi lần bán**, đổi lại phải phối hợp **mỗi lần tái phân bổ**.

## 16. Hot pool khi mở bán cao điểm

Một pool nổi tiếng có thể nhận hàng chục nghìn request/giây. Một document nguyên tử giúp chống oversell, nhưng nhiều writer cùng cạnh tranh có thể làm tăng conflict, queue và p99.

| Biện pháp | Mục tiêu | Giá phải trả |
|---|---|---|
| Admission control / waiting room | Hạn số yêu cầu tranh pool cùng lúc | Thời gian chờ, fairness |
| Per-user/cart limit | Ngăn một user giữ vô hạn | Quota theo user cũng phải có bất biến |
| Backoff + jitter | Giảm retry storm | Độ trễ retry tăng |
| Escrow allocation | Phân tải quyền bán | Cân bằng quota/region khó hơn |
| Cache số lượng hiển thị | Giảm read load | Giao diện có thể hiển thị số trễ |
| Hold timeout hợp lý | Tránh quota bị giữ vô ích | Có thể không đủ thời gian thanh toán |
| Tách pool theo kho/loại vé | Chia tranh chấp nếu thực sự độc lập | Sai nếu phá yêu cầu nghiệp vụ |

Không được sao chép `available=100` lên 10 shard và cho mỗi shard cấp 100 quyền. Muốn mở rộng an toàn phải phân tán **quyền cấp phát**, không chỉ sao chép dữ liệu đọc.

## 17. Tồn kho vật lý khác sức chứa vé

Một pool vé hữu hạn dùng `C=A+H+K` rất trực quan. Hàng vật lý cần các khái niệm riêng:

- `OnHand`: hàng thực tại kho.
- `Reserved`: hàng đang giữ tạm.
- `Allocated`: hàng đã cam kết cho Order chưa xuất kho.
- `Damaged/OtherHolds`: hàng chưa thể bán.
- `InTransit`: hàng đang chuyển kho.
- `Backorder`: nhu cầu chưa có hàng, nếu chính sách cho phép.

Một công thức minh họa:

\[
\text{SellableAvailable}
= \text{OnHand}
- \text{Reserved}
- \text{Allocated}
- \text{OtherHolds}
\]

Khi ship, `OnHand` và `Allocated` có thể cùng giảm. Nếu lúc hold đã giảm `OnHand` rồi lại giảm khi ship, tồn kho bị giảm hai lần.

Với nhiều kho, `SKU-A` còn 10 chiếc ở Hà Nội nhưng 0 ở TP.HCM không nghĩa là đơn cần giao ngay từ TP.HCM có sẵn hàng. Pool nên gắn ranh giới `(SKU, warehouse)` hoặc `(SKU, lot)` khi nghiệp vụ cần.

Di chuyển hàng giữa kho phải tránh để cùng kiện hàng đồng thời được tính “có thể bán” ở hai kho; cần trạng thái in-transit và ledger.

## 18. Quota theo user, coupon và ghế có mã riêng

Bất biến số lượng còn có thể xuất hiện tại các ranh giới khác:

| Nghiệp vụ | Bất biến | Đơn vị cần bảo vệ |
|---|---|---|
| Vé không định ghế | Tổng vé giữ/xác nhận ≤ capacity | Event + loại vé |
| Ghế đánh số | Một ghế không có hai chủ giữ hợp lệ | Event + seat ID |
| Mỗi user tối đa 4 vé | Tổng quyền mua của user ≤ 4 | Event + user |
| Coupon tối đa 100 lượt | Redemptions hợp lệ ≤ 100 | Coupon campaign |
| Phòng theo từng đêm | Không bán trùng phòng/đêm | Room + stay date |
| Rate limit | Request trong cửa sổ ≤ quota | User + window |
| Tài nguyên điện toán | Tổng allocation ≤ capacity | Resource pool |

Với ghế A12, chỉ kiểm tra counter tổng có thể vẫn cấp A12 cho hai người còn A13 bỏ trống. Cần conditional state riêng:

~~~text
Seat A12:
  AVAILABLE -> HELD(reservationId)
  HELD(reservationId) -> CONFIRMED
  HELD(reservationId) -> AVAILABLE khi hết hạn
~~~

Nếu khách cần hai ghế **ngồi cạnh nhau**, việc giữ hai seat records là một bất biến nhóm; transaction hoặc cơ chế bù trừ phải xử lý trường hợp một ghế giữ thành công còn ghế kia thất bại.

Một Order dùng cả coupon và pool hàng hóa cũng có bất biến xuyên hai nguồn quota. Cần điều phối, không thể chỉ kiểm tra mỗi counter đơn lẻ.

## 19. Đối soát và xử lý sai lệch

Tổng `C=A+H+K` có thể đúng trong pool nhưng Reservation và Order vẫn sai. Ví dụ một hold `HELD` đã quá hạn nhưng chưa được worker giải phóng, hoặc hai Order trỏ tới cùng một ghế.

Một job reconciliation:

1. Chỉ ra nguồn nào là bản chuẩn: pool/ledger/Reservation theo hợp đồng.
2. Đọc dữ liệu trong phạm vi nhất quán phù hợp.
3. Tính số giữ/xác nhận theo trạng thái hợp lệ.
4. So với counter và ledger transitions.
5. Ghi mismatch với pool/reservation/order/version, không chỉ ghi số tổng.
6. Sửa bằng command có idempotency/version; không cộng/trừ trực tiếp khi writer khác đang hoạt động.
7. Kiểm tra lại và phát cảnh báo nếu lỗi lặp.

Cần phân biệt **projection trễ hợp lệ** với **sai lệch bền vững**. Một view eventual consistency chưa bắt kịp không tự chứng minh dữ liệu gốc đã sai.

| Sự cố | Phát hiện | Phục hồi |
|---|---|---|
| Quota đã giảm nhưng thiếu Reservation | Pool–Reservation mismatch | Tra transaction/ledger rồi release hoặc tái tạo |
| Reservation EXPIRED, counter chưa release | State/counter lệch | Retry release có điều kiện |
| Payment authorized, Order chưa confirm | PaymentAttempt treo | Đối soát provider, confirm hoặc void/refund |
| Outbox event phát trùng | Consumer thấy ID cũ | Dedup theo ID |
| Cache báo còn hàng khi pool hết | Hold thất bại dù UI còn | Refresh/invalidate; pool quyết định |
| Quota hai region không khớp | Escrow ledger mismatch | Dừng cấp mới, đối soát transfer |

## 20. Quan sát và đo lường bất biến

Hệ thống cần metric theo từng trạng thái và loại lỗi:

- `hold_success`, `hold_insufficient_capacity`, `hold_error`.
- Transaction conflict/CAS retry, timeout, p50/p95/p99 hold.
- Thời gian từ `HELD` tới `CONFIRMED` hoặc `EXPIRED`.
- Số Reservation quá hạn vẫn `HELD`, tuổi lớn nhất của hold treo.
- Số Order `PENDING_HOLD` hoặc `PAYMENT_RECONCILIATION` quá lâu.
- Payment authorization/capture/refund chưa đối soát.
- Outbox lag, duplicate event, lỗi consumer.
- Sai lệch pool–ledger–Reservation–Order.
- Hot pool, throughput và kích thước batch/queue.

Chọn metric có cardinality hợp lý; không biến mọi reservation ID thành một label time-series riêng. Sử dụng correlation ID và audit log để truy sự cố cụ thể.

## 21. Thực nghiệm cạnh tranh: 100 người tranh 10 suất

Tạo pool sức chứa 10. Gửi đồng thời 100 yêu cầu giữ 1 suất, mỗi request có idempotency key riêng. Sau đó đọc **trạng thái đã commit** để xác nhận:

\[
0 \le H+K \le 10,\qquad A+H+K = 10
\]

Nếu hệ thống timeout hoặc admission control, số hold thành công có thể ít hơn 10; không được yêu cầu đúng 10 trong mọi trường hợp. Nhưng **không bao giờ được quá 10**.

| Vòng | Tải | Kiểm tra |
|---|---|---|
| T1 | 100 request khác key, `q=1` | Không vượt sức chứa |
| T2 | 20 retry cùng key | Chỉ trừ quota một lần |
| T3 | 10 request đồng thời, `q=3` | Counter không âm |
| T4 | Confirm và expire cùng hold | Một state transition thắng |
| T5 | Crash sau commit trước response | Retry trả kết quả cũ |
| T6 | Crash giữa hai bước ngoài txn | Có recovery/compensation |
| T7 | Expiry worker chạy trùng | Không hoàn quota hai lần |
| T8 | Order 3 SKU, 1 SKU hết | Không báo Order đủ |
| T9 | Hai vùng mất kết nối | Không cấp trùng quyền quota |
| T10 | Hủy vé sau xác nhận | Tuân thủ chính sách bán lại |

Giả mã:

~~~text
createPool(capacity=10)

responses = concurrently(
    for i in 1..100:
        POST /reservations {
            poolId: "test-pool",
            quantity: 1,
            idempotencyKey: "hold-" + i
        }
)

pool = readAuthoritativePool()
reservations = readAuthoritativeReservations()

assert pool.available >= 0
assert pool.held >= 0
assert pool.confirmed >= 0
assert pool.available + pool.held + pool.confirmed == 10
assert sum(activeUniqueReservationQuantities) <= 10
assert eachBusinessIntentAppliedAtMostOnce
assert noReservationBothConfirmedAndExpired
~~~

**Không chỉ đếm HTTP 200.** Một response bị timeout có thể là giao dịch đã commit. Cần tra lại theo business key rồi mới xác định kết quả. Khi benchmark, ghi cả offered load, achieved throughput, lỗi, p99 và conflict; hệ từ chối mọi request tuy không oversell nhưng không phải hệ đặt hàng hữu ích.

## 22. Bài tập thiết kế và triển khai

**Bối cảnh:** nền tảng bán 50 vé thường và 10 vé VIP, giữ chỗ 5 phút, một user mua tối đa 4 vé mỗi loại. Có ba API instance, payment provider ngoài hệ và hai vùng địa lý.

### Bài A — Thiết kế aggregate

1. Viết công thức và counter cho pool STANDARD và VIP.
2. Xác định bất biến “mỗi user tối đa 4 vé” nằm ở đâu; một quota user–event có bị tranh khi có hai Order đồng thời không?
3. Vẽ state machine Reservation và Order; liệt kê trạng thái kết thúc của hold.
4. Nếu VIP gồm ghế A1–A10, cần thêm bất biến nào ngoài tổng 10 ghế?
5. Nếu một Order gồm 2 vé thường và 1 VIP, chọn transaction hay saga và giải thích đánh đổi.

### Bài B — Ghi có điều kiện

1. Viết conditional update giảm `available` và tăng `held` khi đủ quota.
2. Thiết kế transaction tạo Reservation và update pool cùng commit.
3. Thêm idempotency key ổn định, định nghĩa lỗi khi key dùng với payload khác.
4. Mô tả confirm đúng một lần, kèm điều kiện chưa hết hạn.
5. Mô tả expiry worker release đúng một lần và xử lý confirm–expire race.

### Bài C — Workflow thanh toán

1. Payment được authorize nhưng Reservation đã hết hạn: hệ phải làm gì?
2. Capture thành công nhưng response mất: vì sao retry với payment ID mới không an toàn?
3. Có hai trong ba dòng đã giữ rồi API instance chết: worker khôi phục thế nào?
4. Consumer nhận `OrderConfirmed` hai lần: ngăn tạo hai shipment ra sao?
5. Hàng đã được giao, sau đó Order bị refund: tồn kho thay đổi lúc nào?

### Bài D — Khả năng mở rộng

1. Phân 60 quyền bán giữa VN và EU theo escrow. Thiết kế chuyển 10 quyền từ EU sang VN an toàn khi retry.
2. Chạy 100 request tranh 10 suất; chứng minh bất biến từ dữ liệu đã commit.
3. Đo p95/p99, conflict rate, tỷ lệ hold hết hạn, số Order treo.
4. Giả lập mất node/worker giữa các bước; giải thích giới hạn của môi trường POC một node.
5. Viết một runbook cho trường hợp pool counter không khớp tổng Reservation.

## 23. Các sai lầm phổ biến

| Nhầm lẫn | Vì sao nguy hiểm | Cách làm tốt hơn |
|---|---|---|
| GET rồi SET theo giá trị đã đọc | Race và lost update | Atomic conditional update |
| DECR rồi mới kiểm tra âm | Có thể cấp quá quota | Kiểm tra và giảm trong cùng thao tác |
| Pool giảm rồi insert Reservation ngoài txn | Quota mồ côi khi crash | Transaction hoặc state machine phục hồi |
| TTL xóa record tức là hoàn chỗ | Không cập nhật counter liên quan | Expiry transition có điều kiện |
| Confirm và expire độc lập | Vừa bán vừa trả quota | CAS từ `HELD`, chỉ một nhánh thắng |
| Retry với ID mới | Trừ quota, thanh toán trùng | Idempotency key ổn định |
| Tin số lượng trong cache | Đọc stale dẫn đến oversell | Nguồn pool có thẩm quyền quyết định |
| Order có 2/3 dòng giữ nhưng báo thành công | Đơn không thể giao đủ | Transaction hoặc saga `PARTIAL_HOLD` |
| Merge hai counter vùng tự do | Bán trùng quyền toàn cục | Owner/coordination/escrow |
| Giảm OnHand hai lần | Sai số lượng kho | Phân biệt Reserved/Allocated/OnHand |
| Gọi payment trong txn callback | Side effect có thể lặp | Provider idempotency + orchestrator |
| Counter hợp lệ thì bỏ audit | Có thể Reservation/Order vẫn sai | Ledger, reconciliation |
| Retry vô hạn khi conflict | Retry storm và p99 tăng | Backoff, giới hạn, admission control |

## 24. Câu hỏi tự kiểm tra

1. Vì sao mỗi `GET` và `SET` đúng riêng lẻ không đủ ngăn oversell?
2. Bảo đảm nguyên tử của một document có bảo vệ Reservation ở document khác không?
3. `HELD -> CONFIRMED` và `HELD -> EXPIRED` phải tranh chấp như thế nào?
4. TTL và release quota khác nhau ở điểm nào?
5. Vì sao cùng một business key không được dùng cho hai payload khác nhau?
6. Khi khách timeout sau commit, API nên làm gì trước khi cấp ID mới?
7. Một Order gồm ba pool giữ được hai pool có thể báo `HELD` chưa?
8. Saga khác transaction ở ngữ nghĩa all-or-nothing tức thời ra sao?
9. Vì sao counter CRDT không tự bảo vệ giới hạn sức chứa toàn cầu?
10. Pool bán hàng nóng nên được mở rộng bằng cách nào mà không cấp trùng quyền?
11. Vì sao `OnHand` không được dùng như tên khác của `available`?
12. Bán ghế A12 khác bán một vé không định ghế ở bất biến nào?
13. Payment provider có thể nằm trong transaction MongoDB không?
14. Ledger và outbox khác nhau về mục đích và cách retry thế nào?
15. Counter bảo toàn tổng có chứng minh mọi Reservation/Order đều hợp lệ không?

## 25. Nguyên tắc kết luận

Điểm xuất phát của thiết kế đặt hàng là **bất biến nào bắt buộc luôn đúng**, không phải “database nào có API nhanh nhất”. Hãy xác định pool/quota có thẩm quyền, đặt điều kiện số lượng trong thao tác ghi nguyên tử, rồi mô hình hóa Reservation bằng state machine và idempotency key ổn định.

Nếu một bất biến trải qua nhiều document, pool hoặc dịch vụ, hãy chọn transaction phù hợp hoặc saga với trạng thái trung gian, compensation và đối soát. Khi mở rộng nhiều vùng, phải phân biệt sao chép số đếm với phân bổ quyền bán; khi phối hợp payment, phải tránh side effect lặp và xử lý trạng thái không chắc chắn. Khi đưa vào vận hành, cần đo cả tính đúng đắn, p95/p99, contention, hold treo và chênh lệch ledger.

Một hệ thống giữ chỗ đủ tin cậy phải trả lời được ba câu hỏi: **ai có quyền cấp số lượng, thao tác nào bảo vệ bất biến, và khi một bước thành công nhưng bước tiếp theo thất bại thì điều gì sẽ phục hồi mà không cấp hoặc hoàn cùng một suất hai lần?**
