# Thiết kế đặt chỗ không vượt số lượng dưới tải cạnh tranh

Một hệ thống đặt chỗ phải bảo đảm rằng tổng số lượng đã giữ hoặc đã bán không vượt quá số lượng thực có, kể cả khi hàng nghìn request cùng đặt một sản phẩm trong vài mili giây. Cách làm dễ sai là đọc số lượng còn lại bằng một câu `SELECT`, kiểm tra trong ứng dụng rồi mới `UPDATE`. Nhiều transaction có thể cùng đọc một giá trị cũ và cùng kết luận rằng còn đủ hàng.

Để tránh overbooking, quyết định kiểm tra khả năng đáp ứng và thay đổi số lượng phải được phối hợp nguyên tử ở database. Với một SKU, cách gọn và hiệu quả là **conditional atomic update**: chỉ tăng số lượng đã giữ nếu điều kiện còn đủ hàng vẫn đúng tại thời điểm database thực hiện cập nhật. Một lựa chọn khác là khóa hàng tồn kho bằng `SELECT ... FOR UPDATE`, đọc lại số lượng trong transaction rồi cập nhật. Với yêu cầu nhiều SKU, cần khóa theo thứ tự nhất quán, cập nhật tất cả hoặc rollback tất cả.

Thiết kế đầy đủ còn phải xử lý request gửi lặp, hết hạn reservation, xác nhận thanh toán, hủy đặt chỗ, deadlock/retry và tác dụng phụ ở hệ thống ngoài. Bài này dùng MySQL InnoDB làm ví dụ chính, đồng thời chỉ ra điểm tương ứng ở PostgreSQL. Nguyên tắc cốt lõi là bảo vệ bất biến bằng thao tác database có tính nguyên tử, không dựa vào số lượng đọc từ cache hay replica.

## 1. Xác định bất biến trước khi viết SQL

Giả sử một SKU có tổng số lượng vật lý `on_hand` và số lượng đang được giữ bởi các reservation chưa hoàn tất `reserved`.

Số lượng có thể đặt thêm được tính như sau:

\[
available = on\_hand - reserved
\]

Các bất biến cần luôn đúng:

1. `on_hand >= 0`.
2. `reserved >= 0`.
3. `reserved <= on_hand`.
4. Mỗi reservation đang giữ hàng phải được phản ánh trong `reserved`.
5. Một reservation chỉ được giải phóng hoặc xác nhận một lần.
6. Một request idempotency không được tạo nhiều reservation độc lập.

Ví dụ, nếu kho có 10 đơn vị và đã giữ 7 đơn vị, chỉ còn 3 đơn vị có thể đặt. Hai request đồng thời muốn giữ 2 đơn vị mỗi request không thể cùng thành công; nếu cả hai cùng thành công thì `reserved` thành 11, vượt `on_hand`.

Không nên duy trì thêm một cột `available` có thể bị lệch với `on_hand - reserved`, trừ khi có lý do đo lường rõ ràng và mọi thay đổi đều cập nhật cả ba cột trong cùng transaction. Tính `available` từ hai bộ đếm gốc giúp giảm số trạng thái cần đồng bộ.

## 2. Schema tồn kho và reservation

Ví dụ schema MySQL InnoDB:

```sql
CREATE TABLE inventory (
    sku_id BIGINT NOT NULL,
    on_hand BIGINT NOT NULL,
    reserved BIGINT NOT NULL DEFAULT 0,
    updated_at TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    PRIMARY KEY (sku_id),
    CONSTRAINT chk_inventory_nonnegative
        CHECK (on_hand >= 0 AND reserved >= 0),
    CONSTRAINT chk_inventory_reserved
        CHECK (reserved <= on_hand)
) ENGINE = InnoDB;

CREATE TABLE reservations (
    reservation_id CHAR(36) NOT NULL,
    request_key VARCHAR(150) NOT NULL,
    request_hash CHAR(64) NOT NULL,
    status VARCHAR(20) NOT NULL,
    expires_at TIMESTAMP(6) NULL,
    created_at TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    PRIMARY KEY (reservation_id),
    UNIQUE KEY uk_reservations_request_key (request_key),
    KEY ix_reservations_expiry (status, expires_at),
    CONSTRAINT chk_reservation_status CHECK (
        status IN ('PROCESSING', 'HELD', 'REJECTED', 'CONFIRMED',
                   'CANCELLED', 'EXPIRED')
    )
) ENGINE = InnoDB;

CREATE TABLE reservation_items (
    reservation_id CHAR(36) NOT NULL,
    sku_id BIGINT NOT NULL,
    quantity BIGINT NOT NULL,
    PRIMARY KEY (reservation_id, sku_id),
    CONSTRAINT chk_reservation_quantity CHECK (quantity > 0),
    CONSTRAINT fk_reservation_items_reservation
        FOREIGN KEY (reservation_id) REFERENCES reservations(reservation_id),
    CONSTRAINT fk_reservation_items_inventory
        FOREIGN KEY (sku_id) REFERENCES inventory(sku_id)
) ENGINE = InnoDB;
```

`CHECK` constraints được thực thi trong các phiên bản MySQL hiện đại (MySQL 8.0.16 trở lên). Với phiên bản cũ hơn, cần xác nhận hỗ trợ thực tế và không dựa vào constraint bị bỏ qua. PostgreSQL hỗ trợ `CHECK` và `UNIQUE` theo cách tương tự về mục đích, nhưng kiểu UUID, timestamp và cú pháp có thể được điều chỉnh.

Các trạng thái reservation có ý nghĩa:

| Trạng thái | Ý nghĩa | Có chiếm số lượng `reserved` không? |
|---|---|---:|
| `PROCESSING` | Trạng thái nội bộ trong transaction tạo reservation | Chỉ tồn tại trong transaction chưa commit |
| `HELD` | Hàng đã được giữ trong thời hạn | Có |
| `REJECTED` | Request không đủ hàng hoặc không hợp lệ | Không |
| `CONFIRMED` | Reservation đã được xác nhận và chuyển thành bán/đơn hàng | Không; `on_hand` và `reserved` đã được giảm tương ứng |
| `CANCELLED` | Reservation được hủy trước khi xác nhận | Không |
| `EXPIRED` | Reservation hết hạn và đã giải phóng | Không |

Trong hệ thống thật, có thể tách reservation header, line items, payment state và shipment state thành các bảng riêng. Điều quan trọng là mọi thay đổi của bộ đếm tồn kho phải có transaction và trạng thái nghiệp vụ tương ứng.

## 3. Cách sai: SELECT rồi kiểm tra trong ứng dụng

Giả sử `inventory` đang có `on_hand = 10`, `reserved = 8`, nghĩa là còn 2 đơn vị. Hai request cùng muốn đặt 2 đơn vị.

Code sai thường có dạng:

```sql
-- Bước 1: đọc số lượng
SELECT on_hand, reserved
FROM inventory
WHERE sku_id = 100;

-- Ứng dụng tính available = on_hand - reserved.
-- Nếu available >= 2 thì chạy:

-- Bước 2: cập nhật
UPDATE inventory
SET reserved = reserved + 2
WHERE sku_id = 100;
```

Lịch cạnh tranh có thể xảy ra:

```text
Session A                         Session B
---------                         ---------
SELECT -> available = 2
                                  SELECT -> available = 2
Kiểm tra: đủ hàng
                                  Kiểm tra: đủ hàng
UPDATE reserved = reserved + 2
                                  UPDATE reserved = reserved + 2
COMMIT                            COMMIT
```

Kết quả có thể là `reserved = 12`, vượt `on_hand = 10`. Mỗi câu `UPDATE` là một thao tác nguyên tử, nhưng **điều kiện đủ hàng đã được kiểm tra bên ngoài câu lệnh ghi**. Việc kiểm tra và thay đổi không còn là một quyết định nguyên tử.

Đặt isolation level cao hơn không phải cách sửa tổng quát cho mẫu code này. Với MVCC snapshot, hai transaction có thể đọc cùng một giá trị; nếu cập nhật cùng hàng thì engine có thể tuần tự hóa ghi nhưng câu `UPDATE` không có điều kiện vẫn có thể tăng bộ đếm vượt giới hạn. Cần đặt điều kiện ngay trong thao tác ghi hoặc khóa hàng trước khi đọc và quyết định.

## 4. Cách đơn giản cho một SKU: conditional atomic UPDATE

Đưa điều kiện đủ hàng vào chính câu lệnh cập nhật:

```sql
UPDATE inventory
SET reserved = reserved + :quantity,
    updated_at = CURRENT_TIMESTAMP(6)
WHERE sku_id = :sku_id
  AND :quantity > 0
  AND on_hand - reserved >= :quantity;
```

Ứng dụng kiểm tra số hàng bị ảnh hưởng:

- `1`: đã giữ được số lượng yêu cầu.
- `0`: SKU không tồn tại, quantity không hợp lệ hoặc không còn đủ hàng.

Vì điều kiện và phép tăng `reserved` nằm trong cùng một statement, database khóa hàng cần cập nhật và đánh giá điều kiện trong quá trình thực hiện ghi. Nếu transaction khác vừa tăng `reserved`, câu lệnh đang chờ sẽ tiếp tục dựa trên trạng thái hiện tại và điều kiện có thể không còn đúng; khi đó không có hàng nào được cập nhật.

### Ví dụ hai request cùng tranh một đơn vị

Ban đầu `on_hand = 10`, `reserved = 9`. Hai session cùng chạy:

```sql
UPDATE inventory
SET reserved = reserved + 1
WHERE sku_id = 100
  AND on_hand - reserved >= 1;
```

Một session lấy khóa và cập nhật `reserved` thành 10. Session còn lại phải chờ. Sau khi session đầu commit, session còn lại kiểm tra điều kiện trên trạng thái mới: `10 - 10 >= 1` là sai, nên affected rows bằng 0.

Kết quả là chỉ một request thành công và bất biến `reserved <= on_hand` vẫn đúng.

### PostgreSQL: dùng RETURNING

PostgreSQL có thể trả hàng được cập nhật:

```sql
UPDATE inventory
SET reserved = reserved + $1,
    updated_at = CURRENT_TIMESTAMP
WHERE sku_id = $2
  AND $1 > 0
  AND on_hand - reserved >= $1
RETURNING sku_id, on_hand, reserved;
```

Nếu có một hàng được trả về thì giữ thành công; không có hàng trả về thì không đủ điều kiện hoặc SKU không tồn tại. Với một request cần phân biệt hai trường hợp, ứng dụng có thể đọc trạng thái sau đó bằng một truy vấn phù hợp, nhưng không được dùng lần đọc đó để đảo ngược kết quả cập nhật.

### Vì sao không cần đọc trước?

Nếu chỉ cần biết giữ được hàng hay không, affected-row count hoặc `RETURNING` đã đủ. Đọc trước chỉ để hiển thị số lượng có thể đặt là một thao tác thông tin; nó không được dùng làm căn cứ cuối cùng cho quyết định đặt chỗ.

## 5. Bảo vệ bằng CHECK constraint như lớp phòng thủ cuối

Điều kiện trong `UPDATE` là cơ chế nghiệp vụ chính. `CHECK` constraint bảo vệ dữ liệu nếu có một đường code khác cập nhật bộ đếm sai:

```sql
CONSTRAINT chk_inventory_reserved
    CHECK (reserved <= on_hand)
```

Nếu code vô tình chạy:

```sql
UPDATE inventory
SET reserved = reserved + 100
WHERE sku_id = 100;
```

database sẽ từ chối thay đổi nếu nó làm `reserved > on_hand`.

Constraint không thay thế conditional update:

- Constraint chỉ ngăn trạng thái vi phạm được commit; ứng dụng vẫn cần trả kết quả nghiệp vụ rõ ràng.
- Constraint không tự phân bổ hàng giữa nhiều SKU hoặc warehouse.
- Constraint trên một hàng không thể trực tiếp kiểm tra tổng reservation qua nhiều bảng.
- Constraint không giải quyết request bị gửi lặp hoặc trạng thái reservation bị chuyển hai lần.

Hãy dùng cả điều kiện nguyên tử, transaction và constraint phù hợp. Constraint là hàng rào bảo vệ cuối, không phải toàn bộ thuật toán đặt chỗ.

## 6. Mẫu pessimistic locking: SELECT ... FOR UPDATE

Khi cần đọc nhiều thuộc tính hoặc thực hiện nhiều quyết định trước khi cập nhật, có thể khóa hàng tồn kho trước:

```sql
START TRANSACTION;

SELECT on_hand, reserved
FROM inventory
WHERE sku_id = 100
FOR UPDATE;

-- Ứng dụng tính available = on_hand - reserved.
-- Nếu đủ hàng:
UPDATE inventory
SET reserved = reserved + 2
WHERE sku_id = 100;

-- Nếu không đủ: ROLLBACK hoặc ghi kết quả từ chối theo chính sách.

COMMIT;
```

`FOR UPDATE` yêu cầu exclusive row/index lock phù hợp và giữ đến khi transaction kết thúc. Request khác cần cập nhật cùng SKU phải chờ; sau khi được cấp khóa, nó đọc trạng thái hiện tại rồi kiểm tra lại.

### Điều kiện bắt buộc

- `SELECT ... FOR UPDATE` phải chạy trong transaction còn mở.
- `UPDATE` phải dùng cùng connection/transaction.
- Sau khi quyết định, transaction phải commit hoặc rollback sớm.
- Không gọi payment API, gửi email hoặc chờ người dùng khi đang giữ khóa tồn kho.
- Phải xử lý lock wait timeout và deadlock.

Nếu `autocommit=1` và chạy một locking `SELECT` độc lập ngoài transaction tường minh, khóa có thể được giải phóng ngay khi statement transaction kết thúc. Muốn giữ khóa qua bước kiểm tra và cập nhật, dùng `START TRANSACTION`/`BEGIN`.

### So sánh hai cách

| Tiêu chí | Conditional atomic UPDATE | SELECT FOR UPDATE rồi UPDATE |
|---|---|---|
| Số bước | Thường một câu ghi | Đọc khóa, kiểm tra, ghi |
| Kiểm tra đủ hàng | Predicate trong UPDATE | Ứng dụng kiểm tra sau khi khóa hàng |
| Thích hợp | Một bộ đếm và một điều kiện đơn giản | Nhiều thuộc tính/quy tắc cần đọc trước khi ghi |
| Thời gian giữ khóa | Thường ngắn hơn | Có thể dài hơn do nhiều bước |
| Rủi ro code | Phải kiểm tra affected rows | Phải giữ đúng transaction và không dùng connection khác |
| Deadlock | Vẫn có thể nếu nhiều hàng/index | Vẫn có thể, đặc biệt khi khóa nhiều hàng theo thứ tự khác nhau |

Với một SKU, conditional update thường là lựa chọn gọn. Với nhiều SKU hoặc logic phức tạp, khóa tường minh giúp kiểm soát việc đọc/kiểm tra trước khi thay đổi.

## 7. Tạo reservation header và idempotency key trong cùng transaction

Một request đặt chỗ có thể được gửi lại vì client timeout, retry HTTP hoặc message broker giao lại. Nếu mỗi lần gửi đều tăng `reserved`, một request duy nhất có thể giữ hàng nhiều lần.

Client nên gửi một idempotency key ổn định cho cùng một ý định đặt chỗ, ví dụ `checkout-8f2...`. Database đặt unique constraint trên `request_key`:

```sql
UNIQUE KEY uk_reservations_request_key (request_key)
```

Khi nhận request:

1. Chuẩn hóa danh sách SKU và số lượng.
2. Tính hash của payload nghiệp vụ đã chuẩn hóa.
3. Tạo `reservation_id`.
4. Bắt đầu transaction.
5. Insert reservation header với `request_key` và `request_hash`.
6. Khóa/kiểm tra inventory và cập nhật bộ đếm.
7. Insert reservation items và đặt trạng thái cuối trong transaction.
8. Commit.

Nếu một request cùng key đến đồng thời, unique index sẽ phân xử. Transaction thứ hai có thể phải chờ transaction đầu kết thúc; sau đó nó gặp duplicate key nếu transaction đầu commit. Ứng dụng rollback transaction thứ hai, đọc reservation đã có trong transaction mới và trả lại kết quả cũ.

Nếu cùng key nhưng payload hash khác, trả lỗi conflict. Không được dùng một idempotency key cho hai giỏ hàng khác nhau.

### Pseudocode xử lý duplicate

```text
try:
    BEGIN
    INSERT reservation(request_key, request_hash, status)
    ... reserve inventory ...
    COMMIT
    return reservation result
catch duplicate_request_key:
    ROLLBACK
    existing = SELECT reservation WHERE request_key = ?
    if existing.request_hash != incoming.request_hash:
        return IDEMPOTENCY_KEY_REUSED_WITH_DIFFERENT_PAYLOAD
    return existing result
```

Không đọc reservation hiện có trong transaction đã rơi vào trạng thái lỗi hoặc tiếp tục dùng connection sau duplicate mà không xử lý đúng. Mẫu an toàn là kết thúc transaction thất bại rồi đọc kết quả đã commit bằng transaction mới.

## 8. Chính sách idempotency cho request bị từ chối

Có hai chính sách hợp lệ, nhưng cần chọn rõ:

**Chỉ idempotent với reservation thành công:** nếu không đủ hàng, transaction rollback và không lưu request key. Cùng key có thể thử lại sau khi kho bổ sung hàng. Cách này đơn giản nhưng một request từng bị từ chối có thể thành công ở lần gọi sau.

**Lưu cả kết quả từ chối:** transaction tạo request record, khóa và kiểm tra toàn bộ inventory; nếu thiếu hàng, cập nhật reservation thành `REJECTED` rồi commit mà không thay đổi bộ đếm. Lần gửi lại cùng key trả lại kết quả từ chối cũ, kể cả sau khi kho được bổ sung. Muốn thử lại, client phải tạo một ý định mới với key mới.

Với checkout, lưu kết quả cuối theo idempotency key thường giúp client retry an toàn và nhận cùng kết quả. Để làm được điều này cho nhiều SKU, khóa và kiểm tra tất cả hàng trước khi cập nhật bất kỳ bộ đếm nào.

## 9. Đặt chỗ nhiều SKU: khóa tất cả, kiểm tra rồi mới cập nhật

Một đơn hàng có thể chứa nhiều SKU. Nếu cập nhật từng SKU rồi gặp một SKU hết hàng, không được để các SKU trước đó vẫn bị giữ nếu nghiệp vụ yêu cầu toàn bộ giỏ thành công hoặc thất bại cùng nhau.

Giả sử request cần:

```text
SKU 100: quantity 2
SKU 200: quantity 1
SKU 300: quantity 4
```

Quy trình transaction an toàn:

1. Gộp các dòng trùng SKU để mỗi SKU chỉ còn một quantity.
2. Sắp xếp SKU theo thứ tự tăng dần.
3. Mở transaction và tạo reservation header với unique request key.
4. Khóa từng inventory row theo thứ tự SKU tăng dần.
5. Đọc `on_hand` và `reserved` hiện tại của từng SKU.
6. Nếu bất kỳ SKU nào thiếu hoặc không đủ, ghi kết quả `REJECTED` (nếu chính sách lưu từ chối) và commit mà không thay đổi bộ đếm.
7. Nếu tất cả đủ, tăng `reserved` cho từng SKU, insert reservation items và đặt trạng thái `HELD`.
8. Commit một lần cho toàn bộ giỏ.

### Vì sao khóa theo thứ tự cố định?

Hai request có thể chứa cùng hai SKU nhưng theo thứ tự khác nhau:

```text
Request A: khóa SKU 100 rồi SKU 200
Request B: khóa SKU 200 rồi SKU 100
```

Nếu A giữ 100 và chờ 200 trong khi B giữ 200 và chờ 100, database có thể phát hiện deadlock. Nếu mọi transaction khóa theo thứ tự tăng dần:

```text
Request A: 100 -> 200
Request B: 100 -> 200
```

thì chúng tranh chấp tại SKU đầu tiên và ít có khả năng tạo vòng chờ do đảo thứ tự.

Để kiểm soát thứ tự rõ ràng, có thể thực hiện các primary-key lookup riêng lẻ theo danh sách SKU đã sort, thay vì giả định `ORDER BY` của một truy vấn phức tạp luôn xác định thứ tự vật lý lấy mọi lock. Cần xác nhận execution plan và hành vi của engine.

### Không cập nhật trước khi đã xác nhận đủ tất cả SKU

Nếu cập nhật SKU 100 và SKU 200 rồi mới phát hiện SKU 300 không đủ, có thể rollback toàn transaction. Tuy nhiên, mô hình khóa tất cả và kiểm tra trước giúp đơn giản hóa chính sách lưu kết quả `REJECTED`: không có bộ đếm nào đã thay đổi, nên có thể commit request record bị từ chối mà không cần bù trừ.

### Inventory row nên tồn tại trước

Đối với SKU có thể bán, nên có một inventory row được tạo trước cho từng warehouse/SKU. Khi SKU không có row, cần coi là không có hàng hoặc xử lý trạng thái chưa khởi tạo một cách rõ ràng. Truy vấn `FOR UPDATE` không tìm thấy row không khóa một record tồn tại; gap lock khi tìm key không tồn tại phụ thuộc engine, index và isolation level. Không dựa vào gap lock để thay thế quy trình khởi tạo inventory.

## 10. Mẫu transaction nhiều SKU bằng MySQL

Pseudocode sau minh họa transaction cho request đã được chuẩn hóa và sắp xếp SKU. Các câu `SELECT ... FOR UPDATE` được thực hiện lần lượt theo thứ tự tăng dần bằng cùng connection:

```sql
START TRANSACTION;

INSERT INTO reservations (
    reservation_id, request_key, request_hash, status
)
VALUES (
    :reservation_id, :request_key, :request_hash, 'PROCESSING'
);

-- Lặp theo sku_id tăng dần, mỗi lần dùng cùng transaction:
SELECT on_hand, reserved
FROM inventory
WHERE sku_id = :sku_id
FOR UPDATE;

-- Ứng dụng kiểm tra on_hand - reserved >= quantity cho TẤT CẢ SKU.

-- Nếu thiếu bất kỳ SKU nào: không chạy các UPDATE bộ đếm.
UPDATE reservations
SET status = 'REJECTED',
    updated_at = CURRENT_TIMESTAMP(6)
WHERE reservation_id = :reservation_id;

-- Nếu đủ tất cả SKU, thay vào đó tăng reserved cho từng SKU:
UPDATE inventory
SET reserved = reserved + :quantity,
    updated_at = CURRENT_TIMESTAMP(6)
WHERE sku_id = :sku_id
  AND on_hand - reserved >= :quantity;

-- Kiểm tra mỗi UPDATE ảnh hưởng đúng một hàng.
-- Insert các reservation_items.
-- Chuyển header sang HELD và đặt expires_at.

COMMIT;
```

Đây là mẫu điều khiển, không phải một script chạy nguyên khối: nhánh `REJECTED` và nhánh `HELD` là hai nhánh thay thế nhau. Nếu bất kỳ câu lệnh nào lỗi, rollback toàn transaction. Nếu mỗi inventory row đã được khóa và không có đường code nào bỏ qua quy tắc, điều kiện trong UPDATE vẫn là hàng rào bổ sung.

Trong code ứng dụng, cần kiểm tra:

- Số lượng đầu vào dương và không vượt giới hạn kiểu dữ liệu.
- Không có SKU trùng sau bước aggregate.
- Mọi SKU được khóa theo cùng thứ tự.
- Mỗi `SELECT FOR UPDATE` tìm đúng một inventory row đã được provision.
- Mỗi `UPDATE` thành công ảnh hưởng đúng một hàng.
- Mọi reservation item và bộ đếm được ghi cùng transaction.
- `COMMIT` chỉ xảy ra khi toàn bộ giỏ hợp lệ hoặc khi đã ghi kết quả từ chối theo chính sách.

## 11. Chuyển từ HELD sang CONFIRMED

Khi thanh toán hoặc bước nghiệp vụ tiếp theo thành công, reservation được xác nhận. Với mô hình `on_hand` là lượng vật lý còn trong kho và `reserved` là phần đang giữ, xác nhận bán cần giảm cả hai:

```sql
UPDATE inventory
SET on_hand = on_hand - :quantity,
    reserved = reserved - :quantity,
    updated_at = CURRENT_TIMESTAMP(6)
WHERE sku_id = :sku_id
  AND on_hand >= :quantity
  AND reserved >= :quantity;
```

`available = on_hand - reserved` không đổi trong bước chuyển từ hàng đang giữ sang hàng đã bán. Ví dụ trước xác nhận: `on_hand=10`, `reserved=3`, `available=7`; sau khi xác nhận 2 đơn vị: `on_hand=8`, `reserved=1`, `available=7`.

Chuyển trạng thái reservation và giảm bộ đếm phải nằm trong cùng transaction. Không giảm `reserved` hai lần nếu hai request xác nhận cùng reservation đến đồng thời.

## 12. Hủy hoặc hết hạn: chỉ giải phóng một lần

Khi reservation bị hủy hoặc hết hạn, chỉ giảm `reserved`; `on_hand` không thay đổi vì hàng vẫn còn trong kho:

```sql
UPDATE inventory
SET reserved = reserved - :quantity,
    updated_at = CURRENT_TIMESTAMP(6)
WHERE sku_id = :sku_id
  AND reserved >= :quantity;
```

Để không giải phóng hai lần, transaction phải khóa reservation header và chỉ thực hiện release nếu trạng thái hiện tại là `HELD`:

```sql
START TRANSACTION;

SELECT status
FROM reservations
WHERE reservation_id = :reservation_id
FOR UPDATE;

-- Chỉ nếu status = 'HELD':
-- 1. Đọc reservation_items theo sku_id tăng dần.
-- 2. Giảm reserved của từng inventory row.
-- 3. Đổi status thành CANCELLED hoặc EXPIRED.

COMMIT;
```

Hai worker cùng xử lý một reservation sẽ tuần tự hóa trên reservation row. Worker đầu chuyển `HELD` thành `EXPIRED`; worker sau đọc trạng thái mới và không giảm bộ đếm lần nữa.

### Race giữa confirm và expire

Confirmation và expiration có thể đến cùng lúc. Cả hai phải khóa cùng reservation header trước, sau đó mới khóa inventory rows theo thứ tự SKU thống nhất.

- Nếu confirm lấy khóa trước và thời hạn còn hiệu lực, nó chuyển sang `CONFIRMED`; expiry worker sau đó thấy trạng thái không còn `HELD` và không release.
- Nếu expiry lấy khóa trước và thời hạn đã qua, nó release và chuyển sang `EXPIRED`; confirm sau đó thấy trạng thái không hợp lệ và không thể bán hàng đã giải phóng.
- Nếu confirm đến sau `expires_at` nhưng expiry worker chưa chạy, confirm vẫn phải kiểm tra thời hạn bằng database time và từ chối; không được dựa chỉ vào việc trạng thái còn `HELD`.

Đặt thứ tự khóa nhất quán trong mọi luồng: reservation header trước, inventory rows theo `sku_id` tăng dần. Nếu một code path khóa inventory trước rồi mới khóa reservation, deadlock có thể xuất hiện.

## 13. Hết hạn reservation bằng worker

Một worker định kỳ tìm reservation hết hạn:

```sql
SELECT reservation_id
FROM reservations
WHERE status = 'HELD'
  AND expires_at <= CURRENT_TIMESTAMP(6)
ORDER BY expires_at, reservation_id
LIMIT 100;
```

Truy vấn tìm ứng viên không tự nó bảo đảm worker duy nhất xử lý mỗi reservation. Khi có nhiều worker, dùng transaction claim/`FOR UPDATE SKIP LOCKED` nếu database hỗ trợ, hoặc để mỗi worker khóa từng reservation header và kiểm tra lại trạng thái/thời hạn sau khi lấy khóa.

Không lấy danh sách hết hạn rồi giảm bộ đếm ngoài transaction. Worker phải:

1. Mở transaction.
2. Khóa reservation header.
3. Kiểm tra lại `status='HELD'` và `expires_at <= CURRENT_TIMESTAMP`.
4. Khóa inventory rows theo thứ tự SKU.
5. Giảm `reserved` cho các dòng.
6. Đổi trạng thái sang `EXPIRED`.
7. Commit.

Nếu worker crash trước commit, cả việc giảm bộ đếm và đổi trạng thái rollback. Worker khác có thể thử lại. Nếu crash sau commit, trạng thái đã là `EXPIRED`, worker sau không giải phóng lần nữa.

Dùng thời gian database để kiểm tra hạn nhằm tránh lệch đồng hồ giữa application instances. Ghi rõ timezone và precision của cột `expires_at`.

## 14. Không giữ khóa tồn kho trong khi gọi payment API

Một sai lầm phổ biến là mở transaction, khóa inventory, gọi payment gateway qua HTTP rồi mới commit. Payment provider có thể mất vài giây hoặc timeout; trong thời gian đó mọi request cùng SKU phải chờ khóa.

Thiết kế tốt hơn:

1. Transaction ngắn tạo reservation `HELD`, tăng `reserved` và ghi outbox event `PaymentRequested`.
2. Commit, giải phóng inventory locks.
3. Worker gọi payment provider ngoài transaction bằng idempotency key ổn định.
4. Khi payment thành công, transaction mới xác nhận reservation nếu còn hiệu lực.
5. Khi payment thất bại, transaction mới release reservation.
6. Nếu payment thành công sau khi reservation đã hết hạn, thực hiện compensation như refund hoặc xử lý thủ công theo quy tắc nghiệp vụ.

Luồng này là một saga với các transaction cục bộ. Outbox bảo đảm ý định gọi payment được lưu cùng reservation; idempotency key của provider ngăn thu tiền trùng khi worker retry. Database và payment API không cùng một transaction ACID.

## 15. Retry deadlock và lỗi tạm thời

Khi nhiều request đặt nhiều SKU, deadlock vẫn có thể xảy ra do index, foreign key, trigger hoặc code path khác lấy khóa theo thứ tự khác. Ứng dụng cần:

- Bắt đúng lỗi deadlock/serialization/lock timeout.
- Rollback transaction thất bại.
- Bắt đầu transaction mới.
- Đọc lại reservation và inventory.
- Tính lại quyết định từ dữ liệu mới.
- Retry toàn bộ đơn vị công việc với số lần hữu hạn và backoff có jitter.

Không retry riêng câu `UPDATE` cuối bằng số lượng đã đọc trước đó. Không retry mọi exception; lỗi validation, SKU không tồn tại, idempotency key dùng sai payload và lỗi quyền không tự biến mất khi retry.

Nếu lỗi xảy ra ở thời điểm commit và client không biết commit đã thành công chưa, hãy tra cứu bằng `request_key` trước khi thực hiện lại. Không tạo idempotency key mới cho cùng một request.

## 16. Không dùng cache hoặc read replica làm quyết định cuối

Cache và read replica hữu ích để hiển thị số lượng còn lại, nhưng có thể stale:

- Cache chưa được invalidated sau reservation vừa commit.
- Replica đang có replication lag.
- Hai API instances đọc cùng một số lượng cũ.

Có thể hiển thị `available` từ cache như thông tin tham khảo, nhưng thao tác giữ hàng phải được quyết định trên database primary/leader có thẩm quyền bằng conditional update hoặc locking transaction. Nếu primary không khả dụng, không nên tự chuyển sang quyết định giữ hàng trên replica đọc.

Nếu hệ thống phân vùng dữ liệu theo warehouse hoặc shard, mọi request tranh cùng một lượng tồn kho phải được điều phối trên cùng nguồn ghi có tính nhất quán. Giao dịch nhiều shard cần thiết kế distributed transaction hoặc saga/partition reservation; không thể giả định local transaction trên một shard bảo vệ được tổng số lượng toàn hệ thống.

## 17. Cách xử lý SKU và warehouse

Khóa chính `sku_id` chỉ phù hợp nếu hệ thống có một kho duy nhất. Nếu có nhiều warehouse, tồn kho phải được định danh theo cặp:

```sql
PRIMARY KEY (warehouse_id, sku_id)
```

Conditional update trở thành:

```sql
UPDATE inventory
SET reserved = reserved + :quantity
WHERE warehouse_id = :warehouse_id
  AND sku_id = :sku_id
  AND on_hand - reserved >= :quantity;
```

Nếu hệ thống tự phân bổ một request qua nhiều kho, phải xác định chiến lược phân bổ trước khi giữ hàng. Có thể thử các kho theo thứ tự ưu tiên trong một transaction, nhưng phải kiểm soát khóa trên tất cả hàng đã chọn và rollback nếu tổng lượng không đủ.

Đừng để hai worker cùng phân bổ dựa trên một bản snapshot cache rồi ghi vào các kho độc lập mà không có một cơ chế phối hợp. Tổng số lượng đã giữ qua mọi kho vẫn phải thỏa giới hạn nghiệp vụ.

## 18. Tối ưu contention khi một SKU quá nóng

Conditional update và row lock bảo đảm tính đúng nhưng các request cùng SKU phải tuần tự hóa trên một inventory row. Đây là điểm nóng có chủ đích: để không bán vượt số lượng, database phải phân xử quyền giữ hàng.

Khi throughput chưa đủ, trước tiên đo:

- Số request đồng thời trên mỗi SKU.
- Thời gian chờ row lock và số deadlock.
- Thời gian transaction và số câu SQL trong transaction.
- Tỷ lệ request thất bại do hết hàng so với timeout.
- Tải của index và connection pool.

Giảm công việc trong critical section: dùng primary-key lookup, cập nhật một hàng, tránh truy vấn không cần thiết, không gọi HTTP và commit nhanh.

Một số hệ thống rất lớn có thể chia tồn kho thành bucket/quota được cấp trước cho các worker hoặc partition. Cách này chỉ an toàn nếu tổng quota cấp cho mọi bucket không vượt số lượng vật lý và không có đường ghi nào vượt quota cục bộ. Khi chuyển quota giữa bucket, cần transaction/coordination riêng. Chia một counter thành nhiều counter mà không phân bổ quota trước chỉ làm mất điểm khóa chung và có thể tái tạo overbooking.

## 19. Kiểm tra dữ liệu và phát hiện sai lệch

Sau mỗi đợt test, kiểm tra constraint và đối chiếu bộ đếm với reservation đang giữ:

```sql
SELECT
    i.sku_id,
    i.on_hand,
    i.reserved,
    i.on_hand - i.reserved AS available,
    COALESCE(SUM(
        CASE WHEN r.status = 'HELD' THEN ri.quantity ELSE 0 END
    ), 0) AS held_from_reservations
FROM inventory AS i
LEFT JOIN reservation_items AS ri
  ON ri.sku_id = i.sku_id
LEFT JOIN reservations AS r
  ON r.reservation_id = ri.reservation_id
GROUP BY i.sku_id, i.on_hand, i.reserved
HAVING i.reserved <> held_from_reservations
    OR i.reserved > i.on_hand
    OR i.reserved < 0
    OR i.on_hand < 0;
```

Truy vấn đối chiếu giả định `reserved` đúng bằng tổng line item của reservation ở trạng thái `HELD`. Nếu hệ thống có thêm trạng thái giữ khác, điều chỉnh predicate. Nếu reservation item có thể được lưu trữ/xóa theo retention, cần một nguồn ledger/audit khác để đối soát.

Kiểm tra request key trùng:

```sql
SELECT request_key, COUNT(*) AS row_count
FROM reservations
GROUP BY request_key
HAVING COUNT(*) > 1;
```

Unique constraint đã phải ngăn trường hợp này; truy vấn là một kiểm tra bổ sung khi migration hoặc dữ liệu cũ được nhập.

Không chỉ kiểm tra `reserved <= on_hand`. Bộ đếm có thể không vượt kho nhưng vẫn lệch với các reservation đang `HELD`, dẫn đến hàng bị giữ vĩnh viễn hoặc hàng có thể bán bị ẩn.

## 20. Kiểm thử tải cạnh tranh để chứng minh không overbook

Một test đơn giản và có giá trị cao:

1. Tạo một SKU có `on_hand = 100`, `reserved = 0`.
2. Khởi chạy 500 request độc lập, mỗi request muốn giữ 1 đơn vị.
3. Dùng barrier để nhiều worker bắt đầu gần như đồng thời.
4. Mỗi request dùng idempotency key riêng; các lần retry của cùng request phải giữ nguyên key.
5. Chờ tất cả request kết thúc, bao gồm retry/deadlock nếu có.
6. Đếm số reservation thành công và kiểm tra inventory.

Kết quả kỳ vọng:

- Chính xác 100 request thành công nếu mọi request đều hợp lệ và không có hủy/expiry trong lúc test.
- 400 request còn lại bị từ chối vì không đủ hàng.
- `reserved = 100`.
- `on_hand = 100`.
- `available = 0`.
- Không có `reserved > on_hand`.
- Tổng quantity của reservation `HELD` bằng 100.
- Không có request key tạo nhiều reservation.

Nếu test dùng cùng một idempotency key cho nhiều worker, các worker đó phải nhận cùng một kết quả reservation thay vì được tính như nhiều request độc lập.

### Test nhiều SKU

Tạo hai SKU, mỗi SKU có 10 đơn vị. Sinh nhiều request cần cả hai SKU nhưng đảo thứ tự dòng item ở một phần request. Ứng dụng phải chuẩn hóa và khóa theo cùng thứ tự SKU. Kiểm tra:

- Không có reservation chỉ giữ một phần giỏ nếu nghiệp vụ yêu cầu all-or-nothing.
- Tổng `reserved` mỗi SKU không vượt `on_hand`.
- Không có deadlock kéo dài không được xử lý; nếu có deadlock victim, retry toàn transaction.
- Mỗi request key chỉ có một kết quả cuối.

## 21. Thu bằng chứng lock và transaction khi test

Với MySQL InnoDB, trong lúc tải chạy có thể quan sát:

```sql
SELECT
    trx_id,
    trx_mysql_thread_id AS connection_id,
    trx_started,
    TIMESTAMPDIFF(SECOND, trx_started, NOW()) AS transaction_age_seconds,
    trx_state,
    trx_rows_locked,
    trx_rows_modified,
    trx_query
FROM information_schema.innodb_trx
ORDER BY trx_started;
```

```sql
SELECT
    ENGINE_TRANSACTION_ID,
    THREAD_ID,
    OBJECT_NAME,
    INDEX_NAME,
    LOCK_MODE,
    LOCK_STATUS,
    LOCK_DATA
FROM performance_schema.data_locks
WHERE OBJECT_SCHEMA = DATABASE()
  AND OBJECT_NAME = 'inventory';
```

```sql
SELECT *
FROM performance_schema.data_lock_waits;
```

Các view cho biết transaction và lock đang tồn tại tại thời điểm quan sát. Không thấy wait row không có nghĩa chưa từng có contention; wait có thể đã kết thúc trước lúc lấy mẫu. Ghi timestamp và thu thập trong cửa sổ tải.

Với PostgreSQL, dùng `pg_stat_activity`, `pg_blocking_pids()` và `pg_locks` để tìm backend chờ và blocker. Dùng `EXPLAIN` để kiểm tra access path của câu update/select; actual plan chỉ chạy trong môi trường test vì nó thực thi câu lệnh.

## 22. Lịch hai session để tái hiện overbooking ở cách làm sai

Để hiểu vì sao read-check-write sai, có thể tạo fixture nhỏ trong database test:

```sql
CREATE TABLE inventory_bad_demo (
    sku_id BIGINT PRIMARY KEY,
    on_hand INT NOT NULL,
    reserved INT NOT NULL DEFAULT 0
) ENGINE = InnoDB;

INSERT INTO inventory_bad_demo VALUES (100, 10, 8);
```

Session A:

```sql
START TRANSACTION;
SELECT on_hand, reserved
FROM inventory_bad_demo
WHERE sku_id = 100;
-- Ứng dụng thấy available = 2; dừng ở đây.
```

Session B:

```sql
START TRANSACTION;
SELECT on_hand, reserved
FROM inventory_bad_demo
WHERE sku_id = 100;
-- Cũng thấy available = 2; dừng ở đây.
```

Sau khi cả hai đã đọc:

```sql
-- Session A
UPDATE inventory_bad_demo
SET reserved = reserved + 2
WHERE sku_id = 100;
COMMIT;
```

```sql
-- Session B
UPDATE inventory_bad_demo
SET reserved = reserved + 2
WHERE sku_id = 100;
COMMIT;
```

Hai update có thể chạy tuần tự trên cùng row lock nhưng cả hai đều không có predicate kiểm tra hàng còn đủ. Giá trị cuối có thể là `reserved=12`. Đây là lỗi logic trong điều kiện ghi, không phải vì database không khóa hàng.

Reset fixture rồi lặp lại bằng conditional update:

```sql
UPDATE inventory_bad_demo
SET reserved = reserved + 2
WHERE sku_id = 100
  AND on_hand - reserved >= 2;
```

Chỉ một session có thể cập nhật thành công; session còn lại nhận affected rows bằng 0 sau khi trạng thái mới được kiểm tra.

## 23. Deadlock và lock wait không phải overbooking

Một request bị deadlock hoặc lock timeout không có nghĩa đã giữ hàng thành công. Kết quả chỉ được xem là thành công sau khi transaction commit và reservation ở trạng thái hợp lệ.

- **Deadlock:** database hủy một transaction để phá vòng chờ. Rollback toàn bộ thao tác đặt chỗ rồi retry transaction mới nếu còn ngân sách.
- **Lock wait timeout:** transaction có thể chỉ bị chờ quá lâu. Rollback theo chính sách, kiểm tra blocker và retry hữu hạn.
- **Insufficient stock:** conditional update ảnh hưởng 0 hàng hoặc bước validation phát hiện thiếu. Đây là kết quả nghiệp vụ, không nên retry liên tục như lỗi hạ tầng.
- **Connection lost at commit:** kết quả có thể không xác định từ phía client. Tra cứu bằng idempotency key trước khi gửi lại.

Không tăng `reserved` ở memory/cache trước rồi coi đó là thành công. Database commit là điểm xác nhận trạng thái tồn kho.

## 24. Các lỗi thiết kế thường gặp

| Lỗi | Hậu quả | Cách khắc phục |
|---|---|---|
| SELECT available rồi UPDATE vô điều kiện | Nhiều request cùng dùng một số lượng cũ và overbook | Conditional UPDATE hoặc SELECT FOR UPDATE trong transaction |
| Chỉ dùng cache để quyết định đủ hàng | Cache stale có thể cho nhiều request cùng thành công | Database primary là nguồn quyết định cuối |
| Không có unique idempotency key | Retry HTTP/message có thể tạo nhiều reservation | Unique request key và payload hash |
| Cập nhật nhiều SKU nhưng commit từng SKU | Một phần giỏ được giữ dù phần khác thất bại | Một transaction all-or-nothing hoặc workflow phân bổ được thiết kế rõ |
| Khóa SKU theo thứ tự đầu vào | Hai request đảo thứ tự có thể deadlock | Aggregate và sort SKU trước khi khóa |
| Gọi payment API trong transaction đang giữ inventory lock | Lock tồn kho bị giữ trong thời gian network chậm | Commit reservation trước; dùng outbox và saga |
| Expiry worker giảm reserved mà không kiểm tra trạng thái | Có thể release hai lần hoặc release reservation đã confirm | Khóa header và chuyển trạng thái có điều kiện trong cùng transaction |
| Confirm không kiểm tra expires_at | Reservation hết hạn nhưng vẫn được xác nhận sau khi hàng đã release | Kiểm tra thời hạn bằng database time khi khóa header |
| Retry câu UPDATE cuối với dữ liệu cũ | Quyết định dựa trên trạng thái không còn đúng | Retry toàn transaction và đọc lại |
| CHECK constraint bị xem là toàn bộ giải pháp | Không bảo vệ idempotency hoặc tổng hợp qua nhiều bảng | Kết hợp constraint, transaction và state machine |
| Không đối soát reservation với counter | Bộ đếm có thể bị lệch dù vẫn không âm | Reconciliation query và ledger/audit |

## 25. Quy trình thiết kế và triển khai

1. Xác định bất biến `0 <= reserved <= on_hand` và định nghĩa chính xác khi nào hàng được giữ, xác nhận hoặc giải phóng.
2. Chọn mô hình bộ đếm; ưu tiên `on_hand` và `reserved`, tính `available` từ hiệu của chúng.
3. Tạo primary key cho mỗi inventory row và constraint bảo vệ giá trị hợp lệ.
4. Với một SKU, dùng conditional atomic update và kiểm tra affected-row count/`RETURNING`.
5. Với nhiều SKU, chuẩn hóa input, gộp SKU trùng, khóa theo thứ tự ổn định, kiểm tra tất cả rồi cập nhật tất cả trong một transaction.
6. Tạo unique idempotency key và ràng buộc payload hash để xử lý request lặp.
7. Chọn chính sách cho kết quả từ chối: có lưu kết quả cuối để retry cùng key trả cùng response hay cho phép thử lại.
8. Thiết kế state machine cho `HELD`, `CONFIRMED`, `CANCELLED`, `EXPIRED` và chỉ chuyển trạng thái hợp lệ.
9. Xử lý confirm/expire/cancel bằng cùng thứ tự khóa: reservation header rồi inventory rows theo SKU.
10. Không giữ row lock trong khi gọi payment hoặc dịch vụ ngoài; dùng outbox/idempotency và compensation.
11. Retry deadlock/serialization failure bằng transaction mới, đọc lại dữ liệu và giới hạn số lần thử.
12. Dùng primary database để quyết định, không dùng cache/replica làm nguồn xác nhận.
13. Kiểm thử tải đồng thời với barrier và database thật; kiểm tra counter, reservation lines và idempotency.
14. Thu lock telemetry, đo hot-key contention và đối soát bộ đếm định kỳ.

## 26. Tự kiểm tra

**Vì sao `SELECT available` rồi `UPDATE reserved = reserved + quantity` có thể overbook?**

Hai transaction có thể cùng đọc một giá trị available trước khi một transaction cập nhật. Nếu câu UPDATE không kiểm tra lại điều kiện đủ hàng trong database, cả hai lần ghi vẫn có thể thành công tuần tự và tổng reserved vượt on_hand.

**Conditional UPDATE bảo vệ điều kiện thế nào?**

Predicate `on_hand - reserved >= quantity` nằm trong cùng statement với phép tăng reserved. Database khóa hàng để ghi và đánh giá điều kiện trên trạng thái hiện tại; sau khi transaction trước cập nhật, request sau có thể ảnh hưởng 0 hàng.

**Khi nào nên dùng SELECT FOR UPDATE?**

Khi cần đọc nhiều thuộc tính hoặc kiểm tra nhiều quy tắc trước khi ghi. Phải giữ cùng transaction/connection từ lúc khóa đến khi commit hoặc rollback.

**Vì sao nhiều SKU phải khóa theo thứ tự cố định?**

Các request có cùng tập SKU nhưng thứ tự khác nhau có thể tạo chu trình chờ. Khóa theo thứ tự tăng dần giúp các transaction tranh chấp theo cùng thứ tự và giảm deadlock.

**Làm sao tránh request retry tạo reservation thứ hai?**

Dùng idempotency key ổn định và unique constraint. Nếu key đã tồn tại, đọc và trả kết quả cũ; nếu payload khác, từ chối việc tái sử dụng key.

**Hủy reservation có giảm on_hand không?**

Không. Hủy chỉ giảm reserved vì hàng chưa được bán. Khi xác nhận bán, giảm cả on_hand và reserved để available không thay đổi trong bước chuyển từ held sang sold.

**Làm sao tránh expiry worker giải phóng hai lần?**

Khóa reservation header, kiểm tra trạng thái còn `HELD`, giảm reserved và đổi trạng thái sang `EXPIRED` trong cùng transaction. Worker sau thấy trạng thái đã đổi sẽ không thực hiện lại.

**Có nên giữ transaction mở trong khi gọi payment API?**

Không. Tạo reservation và outbox event trong transaction ngắn, commit rồi gọi payment ngoài transaction bằng idempotency key. Dùng saga/compensation nếu kết quả payment và thời hạn reservation không khớp.

**Nếu client mất kết nối ngay khi COMMIT, có thể tạo request key mới để thử lại không?**

Không. Commit có thể đã thành công dù client không nhận phản hồi. Tra cứu reservation bằng cùng idempotency key trước; không tạo key mới cho cùng một ý định.

Đặt chỗ an toàn dưới tải cạnh tranh dựa trên việc **database là nơi phân xử cuối cùng cho số lượng**, điều kiện đủ hàng nằm trong thao tác ghi hoặc được bảo vệ bằng row lock trong transaction, và mọi trạng thái reservation được cập nhật cùng bộ đếm. Khi thêm idempotency, thứ tự khóa ổn định, xử lý hết hạn và kiểm thử bất biến, hệ thống có thể từ chối request dư một cách nhất quán mà không bán vượt số lượng.
