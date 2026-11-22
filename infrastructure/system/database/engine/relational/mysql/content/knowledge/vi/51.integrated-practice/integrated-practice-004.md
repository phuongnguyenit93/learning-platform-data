# Thiết kế giữ chỗ tồn kho và kiểm chứng cạnh tranh giữa nhiều phiên

Một cửa hàng còn 10 sản phẩm trong kho. Hai khách hàng gần như đồng thời đặt mỗi người 7 sản phẩm. Nếu cả hai request cùng đọc số lượng còn 10, sau đó đều kiểm tra đủ hàng rồi mới cập nhật, hệ thống có thể xác nhận 14 sản phẩm dù kho chỉ có 10. Đây là lỗi overselling do thao tác đọc–kiểm tra–ghi không được bảo vệ bằng một cơ chế đồng thời phù hợp.

Bài học này thuộc chương **Thực hành tổng hợp** của module **DATABASE_MYSQL**. Trong lộ trình làm chủ MySQL từ thiết kế bảng, kiểu dữ liệu, khóa và truy vấn SQL đến index, transaction, kiểm soát đồng thời, đọc kế hoạch thực thi, tối ưu truy vấn, phân quyền, sao lưu và vận hành, bài thực hành kết hợp thiết kế schema, ràng buộc dữ liệu, transaction InnoDB, khóa hàng, idempotency và kiểm thử nhiều session. Mục tiêu là xây dựng luồng giữ chỗ có thể chịu request đồng thời, retry và tác vụ hết hạn mà không làm số lượng hàng khả dụng âm.

## 1. Mô hình nghiệp vụ và invariant

Trước khi viết SQL, xác định các đại lượng:

- **on_hand_qty:** số lượng vật lý đang có trong kho.
- **reserved_qty:** số lượng đang được giữ cho các đơn chưa xác nhận.
- **available_qty:** số lượng còn có thể giữ, tính bằng on_hand_qty trừ reserved_qty.
- **reservation:** một bản ghi giữ chỗ gắn với một yêu cầu duy nhất, kho, SKU, số lượng và thời hạn.
- **request_key:** khóa idempotency do ứng dụng tạo cho mỗi yêu cầu giữ chỗ.

Các invariant cần luôn đúng:

~~~text
on_hand_qty >= 0
reserved_qty >= 0
reserved_qty <= on_hand_qty
available_qty = on_hand_qty - reserved_qty
quantity của mỗi reservation > 0
reserved_qty = tổng quantity của các reservation đang RESERVED
~~~

Invariant cuối cùng liên kết bộ đếm tổng hợp ở bảng inventory với các bản ghi reservation. MySQL có thể kiểm tra giới hạn trên từng hàng bằng CHECK constraint, nhưng không thể dùng CHECK thông thường để so sánh tổng từ một bảng khác. Ứng dụng phải cập nhật inventory và reservation trong cùng transaction; quy trình đối soát định kỳ phát hiện sai lệch nếu có lỗi vận hành hoặc dữ liệu được sửa ngoài luồng chuẩn.

Một reservation có các trạng thái:

| Trạng thái | Ý nghĩa | Tác động tới reserved_qty |
|---|---|---:|
| RESERVED | Đang giữ hàng, chưa xác nhận | Cộng quantity |
| CONFIRMED | Đơn đã xác nhận, hàng được xuất khỏi tồn kho khả dụng | Đã trừ quantity khỏi on_hand_qty và reserved_qty |
| RELEASED | Đã hủy giữ chỗ | Đã trừ quantity khỏi reserved_qty |
| EXPIRED | Hết hạn và được giải phóng | Đã trừ quantity khỏi reserved_qty |

Không chuyển trạng thái về RESERVED sau khi đã RELEASED hoặc EXPIRED. Nếu khách hàng đặt lại, tạo một reservation mới với request key mới. Việc giữ lịch sử trạng thái giúp audit và điều tra retry dễ hơn.

## 2. Thiết kế bảng inventory và reservations

Bảng inventory có một hàng cho mỗi cặp kho và SKU. Khóa chính ghép bảo đảm chỉ có một bộ đếm tồn kho cho mỗi mặt hàng trong từng kho.

~~~sql
CREATE TABLE inventory (
  warehouse_id BIGINT UNSIGNED NOT NULL,
  sku VARCHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  on_hand_qty BIGINT UNSIGNED NOT NULL DEFAULT 0,
  reserved_qty BIGINT UNSIGNED NOT NULL DEFAULT 0,
  PRIMARY KEY (warehouse_id, sku),
  CONSTRAINT chk_inventory_reserved
    CHECK (reserved_qty <= on_hand_qty)
) ENGINE=InnoDB;
~~~

Các cột số lượng dùng UNSIGNED để không lưu số âm. CHECK constraint được MySQL thực thi từ MySQL 8.0.16; nếu vận hành phiên bản cũ hơn, không dựa vào CHECK mà phải bảo vệ invariant trong câu UPDATE và logic ghi dữ liệu, đồng thời nâng cấp phiên bản khi có thể.

Bảng reservation lưu từng lần giữ hàng:

~~~sql
CREATE TABLE inventory_reservations (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  request_key VARCHAR(64)
    CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  order_id BIGINT UNSIGNED NOT NULL,
  warehouse_id BIGINT UNSIGNED NOT NULL,
  sku VARCHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  quantity BIGINT UNSIGNED NOT NULL,
  status VARCHAR(16)
    CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  created_at DATETIME(6) NOT NULL,
  expires_at DATETIME(6) NOT NULL,
  confirmed_at DATETIME(6) NULL,
  released_at DATETIME(6) NULL,
  PRIMARY KEY (id),
  UNIQUE KEY uq_reservation_request (request_key),
  KEY ix_reservation_expiry (status, expires_at, id),
  KEY ix_reservation_order (order_id),
  KEY ix_reservation_inventory (warehouse_id, sku),
  CONSTRAINT chk_reservation_quantity CHECK (quantity > 0),
  CONSTRAINT chk_reservation_status
    CHECK (status IN ('RESERVED', 'CONFIRMED', 'RELEASED', 'EXPIRED')),
  CONSTRAINT fk_reservation_inventory
    FOREIGN KEY (warehouse_id, sku)
    REFERENCES inventory (warehouse_id, sku)
    ON UPDATE RESTRICT
    ON DELETE RESTRICT
) ENGINE=InnoDB;
~~~

request_key dùng collation nhị phân để khóa idempotency phân biệt chính xác ký tự hoa/thường. Kiểu và collation của sku ở hai bảng phải khớp nhau để foreign key hợp lệ. Nếu SKU có quy tắc chữ hoa/thường khác, chọn charset/collation theo nghiệp vụ rồi áp dụng đồng nhất cho cả hai bảng.

Foreign key dùng ON DELETE RESTRICT và reservation được giữ lại để audit, vì vậy không xóa vật lý hàng inventory khi còn lịch sử reservation tham chiếu. Nếu SKU ngừng kinh doanh, đánh dấu inactive ở schema thực tế hoặc archive lịch sử theo quy trình trước khi xóa hàng inventory.

Index ix_reservation_expiry(status, expires_at, id) hỗ trợ worker tìm các reservation đã hết hạn. Index theo order hỗ trợ tra cứu các dòng giữ chỗ của đơn. Index theo kho/SKU hỗ trợ truy vấn và đối soát theo inventory.

Bảng inventory lưu bộ đếm reserved_qty để kiểm tra khả dụng nhanh, còn bảng reservations lưu chi tiết từng yêu cầu. Vì đây là dữ liệu tổng hợp được duy trì song song, mọi luồng tạo, xác nhận, hủy và hết hạn phải cập nhật hai bảng trong cùng transaction. Không cập nhật riêng một bảng bằng script vận hành nếu chưa có quy trình đối soát.

## 3. Chuẩn bị dữ liệu thử

Tạo hai mặt hàng trong kho:

~~~sql
INSERT INTO inventory
  (warehouse_id, sku, on_hand_qty, reserved_qty)
VALUES
  (1, 'SKU-CHAIR', 10, 0),
  (1, 'SKU-DESK', 5, 0);
~~~

Kiểm tra số lượng khả dụng:

~~~sql
SELECT
  warehouse_id,
  sku,
  on_hand_qty,
  reserved_qty,
  on_hand_qty - reserved_qty AS available_qty
FROM inventory
ORDER BY warehouse_id, sku;
~~~

Kết quả ban đầu:

| Kho | SKU | On hand | Reserved | Available |
|---:|---|---:|---:|---:|
| 1 | SKU-CHAIR | 10 | 0 | 10 |
| 1 | SKU-DESK | 5 | 0 | 5 |

Giả sử ứng dụng nhận yêu cầu giữ 7 ghế cho hai đơn hàng khác nhau. Mỗi request có một request_key duy nhất và được giữ trong 15 phút. Dùng DATETIME(6) theo quy ước lưu UTC; tạo và so sánh thời hạn bằng UTC_TIMESTAMP(6) để tránh phụ thuộc timezone session.

## 4. Tạo reservation trong một transaction

Luồng tạo reservation phải thực hiện hai thay đổi cùng transaction. Trong thiết kế có foreign key từ reservation tới inventory, hãy cập nhật và khóa hàng inventory trước rồi mới insert hàng con. Việc insert hàng con có kiểm tra foreign key trên hàng cha; nếu hai session cùng insert reservation trước rồi cùng nâng khóa hàng cha từ shared sang exclusive để cập nhật, chúng có thể deadlock do lock upgrade.

1. Tăng reserved_qty chỉ khi số lượng khả dụng vẫn đủ; UPDATE lấy exclusive record lock trên hàng inventory.
2. Tạo bản ghi reservation với request key duy nhất trong khi vẫn giữ khóa inventory.

Ví dụ SQL dưới đây dùng placeholder ? để ứng dụng bind giá trị bằng PreparedStatement. Kiểm tra số hàng affected do executeUpdate() trả về sau UPDATE trước khi chạy INSERT và COMMIT.

~~~sql
START TRANSACTION;

UPDATE inventory
SET reserved_qty = reserved_qty + ?
WHERE warehouse_id = ?
  AND sku = ?
  AND on_hand_qty - reserved_qty >= ?;

-- Nếu UPDATE ảnh hưởng 0 hàng: ROLLBACK và kiểm tra request_key.

INSERT INTO inventory_reservations
  (request_key, order_id, warehouse_id, sku, quantity, status, created_at, expires_at)
VALUES
  (?, ?, ?, ?, ?, 'RESERVED', UTC_TIMESTAMP(6),
   UTC_TIMESTAMP(6) + INTERVAL 15 MINUTE);

-- Chỉ COMMIT khi cả UPDATE và INSERT đều thành công.

COMMIT;
~~~

Trong ví dụ, quantity được bind ba lần: một lần cho phần tăng reserved_qty, một lần cho điều kiện đủ hàng và một lần cho reservation row. Ứng dụng phải kiểm tra quantity lớn hơn 0 trước khi gửi SQL. CHECK constraint trên reservation là lớp bảo vệ bổ sung.

Nếu UPDATE ảnh hưởng 0 hàng, có thể không tồn tại SKU trong kho hoặc lượng khả dụng không đủ. Ứng dụng phải ROLLBACK; sau rollback, kiểm tra request_key để phân biệt một request đã được xử lý trước đó với một yêu cầu thực sự hết hàng. Nếu INSERT reservation thất bại, chẳng hạn do duplicate request_key, cũng phải ROLLBACK để hoàn tác phần tăng reserved_qty. Không COMMIT một reservation chưa được trừ vào bộ đếm tồn kho.

Có thể kiểm tra số hàng bị tác động bằng JDBC executeUpdate(); giá trị trả về của câu UPDATE là số hàng thay đổi. Vì quantity phải lớn hơn 0, một UPDATE thành công sẽ tăng bộ đếm và ảnh hưởng một hàng. Không cần chạy SELECT trước để kiểm tra tồn kho rồi mới UPDATE; điều kiện trong UPDATE là phép kiểm tra nguyên tử dưới khóa hàng.

### Vì sao phải khóa inventory trước rồi mới INSERT reservation?

Các thao tác thay đổi reservation cần tuân theo một thứ tự khóa thống nhất: inventory trước, reservation sau. Với INSERT reservation có foreign key, InnoDB kiểm tra hàng cha; nếu transaction chưa giữ khóa inventory, kiểm tra foreign key có thể lấy shared lock trên hàng cha. Hai session cùng giữ shared lock rồi cùng muốn cập nhật hàng cha có thể deadlock khi nâng lên exclusive lock. Cập nhật inventory trước giúp transaction giữ exclusive lock trước khi kiểm tra foreign key của hàng con.

- Tạo mới: UPDATE inventory có điều kiện, rồi INSERT reservation.
- Xác nhận: đọc trước khóa kho/SKU, khóa inventory FOR UPDATE, rồi khóa reservation FOR UPDATE.
- Hủy/hết hạn: dùng cùng thứ tự inventory trước, reservation sau.

Đây là quy ước lock order của bài thực hành. Nếu một transaction xử lý nhiều SKU, hãy khóa các hàng inventory theo thứ tự xác định, chẳng hạn (warehouse_id, sku) tăng dần, sau đó mới ghi các reservation. Mọi luồng confirm, cancel và expiry cũng phải theo thứ tự này.

## 5. Không kiểm tra tồn kho bằng SELECT rồi mới UPDATE

Mẫu dễ sai:

~~~sql
SELECT on_hand_qty - reserved_qty AS available_qty
FROM inventory
WHERE warehouse_id = 1
  AND sku = 'SKU-CHAIR';

-- Ứng dụng thấy available_qty = 10 rồi quyết định giữ 7.

UPDATE inventory
SET reserved_qty = reserved_qty + 7
WHERE warehouse_id = 1
  AND sku = 'SKU-CHAIR';
~~~

Hai request có thể cùng đọc 10 trước khi một request cập nhật. Nếu không có khóa và kiểm tra lại trong transaction, cả hai có thể cộng 7.

Mẫu an toàn đưa điều kiện vào chính UPDATE:

~~~sql
UPDATE inventory
SET reserved_qty = reserved_qty + 7
WHERE warehouse_id = 1
  AND sku = 'SKU-CHAIR'
  AND on_hand_qty - reserved_qty >= 7;
~~~

InnoDB khóa hàng cần cập nhật. Nếu một transaction khác đang cập nhật cùng hàng, câu UPDATE còn lại phải chờ. Khi được chạy tiếp, điều kiện được đánh giá trên trạng thái hàng hiện tại; nếu số lượng khả dụng không còn đủ, UPDATE ảnh hưởng 0 hàng. Đây là cách bảo vệ cạnh tranh mà không phụ thuộc vào một lần đọc snapshot cũ.

Một lựa chọn khác là SELECT ... FOR UPDATE, sau đó đọc số lượng và cập nhật trong cùng transaction. Đây là locking read, phù hợp khi cần đọc nhiều thuộc tính hoặc thực hiện logic phức tạp. Với một điều kiện tăng bộ đếm đơn giản, conditional UPDATE thường gọn hơn.

## 6. Mô phỏng hai session cạnh tranh

Bắt đầu từ trạng thái:

~~~text
SKU-CHAIR: on_hand_qty = 10, reserved_qty = 0
Request A muốn giữ 7
Request B muốn giữ 7
~~~

Mở hai cửa sổ MySQL client, mỗi cửa sổ là một connection độc lập.

### Session A

~~~sql
START TRANSACTION;

UPDATE inventory
SET reserved_qty = reserved_qty + 7
WHERE warehouse_id = 1
  AND sku = 'SKU-CHAIR'
  AND on_hand_qty - reserved_qty >= 7;

INSERT INTO inventory_reservations
  (request_key, order_id, warehouse_id, sku, quantity, status, created_at, expires_at)
VALUES
  ('req-A', 1001, 1, 'SKU-CHAIR', 7, 'RESERVED', UTC_TIMESTAMP(6),
   UTC_TIMESTAMP(6) + INTERVAL 15 MINUTE);

-- Kết quả: 1 hàng được cập nhật.
-- Tạm thời chưa COMMIT.
~~~

### Session B

Trong lúc Session A chưa COMMIT, chạy ở Session B:

~~~sql
START TRANSACTION;

UPDATE inventory
SET reserved_qty = reserved_qty + 7
WHERE warehouse_id = 1
  AND sku = 'SKU-CHAIR'
  AND on_hand_qty - reserved_qty >= 7;

-- Chỉ chạy INSERT reservation nếu UPDATE ảnh hưởng đúng 1 hàng.
~~~

UPDATE của Session B phải chờ khóa hàng inventory do Session A giữ.

Quay lại Session A:

~~~sql
COMMIT;
~~~

Sau khi A commit, UPDATE của B tiếp tục. Điều kiện on_hand_qty - reserved_qty >= 7 lúc này không còn đúng vì chỉ còn 3 sản phẩm khả dụng. UPDATE của B ảnh hưởng 0 hàng; B không chạy INSERT reservation và phải ROLLBACK transaction. Nếu UPDATE của B ảnh hưởng 1 hàng (ví dụ A đã rollback), lúc đó B mới chạy INSERT reservation trong cùng transaction.

~~~sql
-- Session B
ROLLBACK;
~~~

Kết quả cuối:

| Chỉ số | Giá trị |
|---|---:|
| on_hand_qty | 10 |
| reserved_qty | 7 |
| available_qty | 3 |
| Reservation RESERVED | 1 |
| Tổng số lượng được giữ | 7 |

Nếu Session A ROLLBACK thay vì COMMIT, Session B có thể tiếp tục và giữ thành công 7. Chỉ một transaction được phép xác nhận giữ hàng cho số lượng vượt quá khả năng còn lại.

Đây là test cốt lõi: hai session độc lập cùng tranh chấp một hàng inventory và database phải bảo đảm invariant sau khi cả hai transaction kết thúc.

## 7. Idempotency khi client retry

Một request có thể đã COMMIT thành công ở MySQL nhưng kết nối bị mất trước khi ứng dụng nhận phản hồi. Client gửi lại cùng request. Nếu ứng dụng tạo reservation mới với request key khác, hàng có thể bị giữ hai lần.

Dùng request_key duy nhất để biến retry thành thao tác idempotent:

- Mỗi yêu cầu nghiệp vụ tạo một request key ổn định.
- Mọi lần retry cùng yêu cầu phải dùng lại key đó.
- Nếu INSERT gặp duplicate key, rollback transaction hiện tại rồi đọc reservation đã tồn tại.
- So sánh order_id, kho, SKU và quantity với payload retry.
- Nếu payload giống nhau, trả lại kết quả reservation hiện tại.
- Nếu payload khác, trả conflict; không âm thầm dùng một key cho hai yêu cầu khác nhau.

Không dùng INSERT IGNORE để che duplicate request. Cần phân biệt “request đã xử lý” với “lỗi dữ liệu khác”. Unique key giúp MySQL tuần tự hóa hai request cùng request key: một transaction tạo hàng, transaction còn lại chờ kết quả unique check rồi nhận duplicate nếu hàng đầu tiên đã commit.

Nếu transaction đầu tiên rollback, request thứ hai có thể insert thành công. Vì vậy, retry cùng key vừa tránh tạo reservation trùng sau commit, vừa cho phép request được thử lại khi lần trước chưa commit.

Nếu commit trả về lỗi do network, ứng dụng không thể luôn biết transaction đã commit hay chưa. Retry bằng cùng request key rồi đọc trạng thái đã lưu là cách xác định kết quả an toàn hơn so với tạo một key mới.

Với lock order inventory trước reservation, hai request cùng request key có thể gặp hai tình huống: UPDATE inventory của request sau trả 0 vì request đầu đã giữ hết lượng khả dụng, hoặc UPDATE thành công nhưng INSERT bị duplicate. Cả hai nhánh đều phải ROLLBACK trước, rồi mới tra request_key ở transaction mới. Nếu payload khớp, trả kết quả đã lưu; nếu payload khác, trả conflict; nếu không có reservation tương ứng, trả hết hàng hoặc lỗi SKU theo đúng nguyên nhân.

## 8. Xác nhận reservation và trừ tồn kho

Khi thanh toán hoặc nghiệp vụ xác nhận đơn hoàn tất, reservation chuyển từ RESERVED sang CONFIRMED. Khi đó giảm cả on_hand_qty và reserved_qty cùng lượng đã giữ.

Để giữ cùng lock order inventory trước, reservation sau, trước hết đọc khóa kho/SKU bất biến của reservation, sau đó khóa hàng inventory và cuối cùng khóa reservation để kiểm tra trạng thái hiện tại. Lần đọc đầu chỉ lấy khóa định vị; lần đọc FOR UPDATE mới là lần kiểm tra trạng thái có khóa.

~~~sql
START TRANSACTION;

SELECT warehouse_id, sku
FROM inventory_reservations
WHERE id = ?;

SELECT warehouse_id, sku
FROM inventory
WHERE warehouse_id = ?
  AND sku = ?
FOR UPDATE;

SELECT id, warehouse_id, sku, quantity, status, expires_at
FROM inventory_reservations
WHERE id = ?
FOR UPDATE;
~~~

Ứng dụng kiểm tra trạng thái:

- CONFIRMED: thao tác đã hoàn tất trước đó; trả kết quả idempotent, không trừ kho lần nữa.
- RELEASED hoặc EXPIRED: không thể xác nhận reservation này.
- RESERVED và còn hạn: tiếp tục.
- RESERVED nhưng đã hết hạn: giải phóng theo luồng hết hạn, không xác nhận.

Với reservation còn hạn, cập nhật inventory:

~~~sql
UPDATE inventory
SET
  on_hand_qty = on_hand_qty - ?,
  reserved_qty = reserved_qty - ?
WHERE warehouse_id = ?
  AND sku = ?
  AND on_hand_qty >= ?
  AND reserved_qty >= ?;
~~~

Nếu UPDATE ảnh hưởng đúng một hàng, cập nhật trạng thái reservation:

~~~sql
UPDATE inventory_reservations
SET
  status = 'CONFIRMED',
  confirmed_at = UTC_TIMESTAMP(6)
WHERE id = ?
  AND status = 'RESERVED'
  AND expires_at > UTC_TIMESTAMP(6);
~~~

Ứng dụng phải xác nhận cả hai UPDATE ảnh hưởng đúng một hàng trước COMMIT. Nếu một điều kiện không còn đúng, ROLLBACK toàn bộ transaction. Điều kiện thời hạn ở câu UPDATE trạng thái giúp kiểm tra lại ngay trước khi hoàn tất chuyển trạng thái.

Khi transaction thành công:

- on_hand_qty giảm vì hàng đã được xác nhận tiêu thụ.
- reserved_qty giảm vì số lượng không còn nằm trong nhóm đang giữ.
- available_qty giữ nguyên tại thời điểm chuyển trạng thái.
- Reservation chuyển sang CONFIRMED.

Hai thay đổi inventory và reservation phải nằm trong cùng transaction. Không cập nhật trạng thái CONFIRMED trước rồi mới trừ kho ở transaction khác.

## 9. Hủy reservation đúng một lần

Khi đơn bị hủy trước xác nhận, giải phóng số lượng đang giữ. Đọc kho/SKU bất biến trước, khóa inventory rồi mới khóa reservation để giữ cùng thứ tự khóa với luồng tạo và xác nhận:

~~~sql
START TRANSACTION;

SELECT warehouse_id, sku
FROM inventory_reservations
WHERE id = ?;

SELECT warehouse_id, sku
FROM inventory
WHERE warehouse_id = ?
  AND sku = ?
FOR UPDATE;

SELECT id, warehouse_id, sku, quantity, status
FROM inventory_reservations
WHERE id = ?
FOR UPDATE;
~~~

Chỉ nếu status là RESERVED mới trừ bộ đếm:

~~~sql
UPDATE inventory
SET reserved_qty = reserved_qty - ?
WHERE warehouse_id = ?
  AND sku = ?
  AND reserved_qty >= ?;
~~~

Sau đó chuyển trạng thái:

~~~sql
UPDATE inventory_reservations
SET
  status = 'RELEASED',
  released_at = UTC_TIMESTAMP(6)
WHERE id = ?
  AND status = 'RESERVED';
~~~

Kiểm tra cả hai UPDATE thành công rồi COMMIT. Nếu reservation đã RELEASED hoặc EXPIRED, trả kết quả đã giải phóng mà không trừ reserved_qty thêm lần nữa. Nếu đã CONFIRMED, nghiệp vụ hủy đơn phải đi qua luồng hoàn kho/đổi trạng thái riêng; không thể chỉ giải phóng reservation đã tiêu thụ.

Khóa inventory tuần tự hóa các thay đổi trên cùng kho/SKU; khóa FOR UPDATE trên reservation bảo vệ chuyển trạng thái. Request đầu tiên chuyển RESERVED sang RELEASED; request thứ hai sau khi lấy được các khóa sẽ thấy trạng thái RELEASED và không cập nhật inventory lần nữa. Đây là tính idempotent của thao tác chuyển trạng thái.

## 10. Tự động hết hạn bằng worker

Reservation không nên giữ hàng vô thời hạn. Một worker định kỳ tìm reservation RESERVED đã quá hạn và giải phóng.

Index (status, expires_at, id) hỗ trợ truy vấn lấy một nhóm ID ứng viên. Lượt quét này không khóa reservation; mỗi ID được xử lý trong transaction riêng theo lock order inventory trước, reservation sau:

~~~sql
SELECT id
FROM inventory_reservations
WHERE status = 'RESERVED'
  AND expires_at <= UTC_TIMESTAMP(6)
ORDER BY expires_at, id
LIMIT 100;
~~~

Không dùng SELECT ... FOR UPDATE trên reservation ở bước quét ứng viên rồi mới khóa inventory. Làm vậy sẽ đảo thứ tự khóa và có thể tạo deadlock với luồng confirm/cancel. Nếu nhiều worker cùng lấy một ID, chúng sẽ tuần tự hóa ở hàng inventory; worker lấy khóa sau phải đọc lại trạng thái reservation và bỏ qua nếu worker trước đã xử lý. Có thể phân chia phạm vi ID giữa worker để giảm công việc trùng. SKIP LOCKED hữu ích cho queue worker, nhưng chỉ áp dụng khi thiết kế truy vấn giữ được thứ tự inventory trước, reservation sau.

Với mỗi ID ứng viên, trong một transaction:

1. Đọc warehouse_id và sku của reservation để định vị hàng inventory.
2. Khóa hàng inventory bằng SELECT ... FOR UPDATE.
3. Khóa lại reservation bằng SELECT ... FOR UPDATE và kiểm tra trạng thái/thời hạn hiện tại.
4. Nếu vẫn RESERVED và đã hết hạn, giảm reserved_qty rồi chuyển trạng thái sang EXPIRED.
5. Kiểm tra số hàng bị ảnh hưởng và COMMIT.

Ví dụ phần xử lý sau khi worker đã khóa inventory rồi khóa reservation:

~~~sql
START TRANSACTION;

SELECT warehouse_id, sku
FROM inventory_reservations
WHERE id = ?;

SELECT warehouse_id, sku
FROM inventory
WHERE warehouse_id = ?
  AND sku = ?
FOR UPDATE;

SELECT id, quantity, status, expires_at
FROM inventory_reservations
WHERE id = ?
FOR UPDATE;

-- Chỉ chạy hai UPDATE dưới đây nếu status = 'RESERVED'
-- và expires_at <= UTC_TIMESTAMP(6).

UPDATE inventory
SET reserved_qty = reserved_qty - ?
WHERE warehouse_id = ?
  AND sku = ?
  AND reserved_qty >= ?;

UPDATE inventory_reservations
SET
  status = 'EXPIRED',
  released_at = UTC_TIMESTAMP(6)
WHERE id = ?
  AND status = 'RESERVED'
  AND expires_at <= UTC_TIMESTAMP(6);

COMMIT;
~~~

Nếu một UPDATE không ảnh hưởng đúng một hàng, ROLLBACK và ghi nhận lỗi để điều tra; không tiếp tục chuyển trạng thái khi bộ đếm không được cập nhật.

Có thể xử lý một reservation mỗi transaction để đơn giản hóa lock order và giới hạn thời gian giữ khóa. Nếu xử lý batch, khóa tất cả hàng inventory theo thứ tự kho/SKU tăng dần trước, sau đó mới khóa các reservation tương ứng; giới hạn batch size và kiểm thử deadlock.

Nếu worker chạy trễ, hàng đã hết hạn trên đồng hồ vẫn có thể nằm trong reserved_qty cho đến khi được giải phóng. Điều này làm available thấp hơn thực tế trong một khoảng thời gian, nhưng không gây oversell. Nếu nghiệp vụ cần giải phóng tức thời, phải thiết kế một luồng xử lý hết hạn đồng bộ có khóa và kiểm thử cạnh tranh với confirm/cancel.

## 11. Cạnh tranh giữa confirm, cancel và expiry

Ba thao tác có thể xảy ra cùng lúc trên một reservation. Tất cả phải tuân theo cùng lock order: xác định kho/SKU, khóa hàng inventory trước, rồi khóa reservation bằng SELECT ... FOR UPDATE và kiểm tra lại trạng thái.

| Cuộc đua | Kết quả hợp lệ |
|---|---|
| Confirm và cancel | Chỉ một thao tác chuyển RESERVED thành trạng thái cuối; thao tác còn lại đọc trạng thái mới và không thay đổi bộ đếm |
| Confirm và expiry worker | Chỉ một thao tác lấy được khóa trước; nếu confirm hợp lệ trước hạn thì worker bỏ qua, nếu expiry chuyển trạng thái trước thì confirm không thể tiêu thụ |
| Hai cancel | Lần đầu giải phóng; lần sau thấy RELEASED và không trừ lần nữa |
| Hai expiry worker | Worker lấy khóa inventory trước xử lý; worker còn lại đợi rồi đọc trạng thái đã đổi và bỏ qua |
| Retry confirm | Nếu đã CONFIRMED, trả kết quả cũ và không trừ tồn kho thêm |

Thời điểm hết hạn nên được đánh giá bằng thời gian MySQL (UTC_TIMESTAMP(6)) để các worker và ứng dụng không dựa vào đồng hồ máy khác nhau. Cột expires_at trong ví dụ lưu UTC theo quy ước ứng dụng.

## 12. Giữ nhiều SKU trong một đơn

Một đơn có thể cần nhiều mặt hàng. Nếu chính sách yêu cầu giữ tất cả hoặc không giữ gì, tạo reservation cho tất cả dòng trong một transaction:

1. Chuẩn hóa danh sách kho/SKU, gộp các dòng trùng SKU nếu nghiệp vụ cho phép.
2. Kiểm tra quantity dương.
3. Sắp xếp theo (warehouse_id, sku).
4. Cập nhật/khóa tất cả hàng inventory theo thứ tự đó và kiểm tra đủ số lượng.
5. Insert reservation cho từng dòng với request key duy nhất theo dòng.
6. Nếu bất kỳ dòng nào không đủ hàng, ROLLBACK toàn bộ.
7. COMMIT khi tất cả dòng giữ thành công.

Khóa theo thứ tự xác định làm giảm khả năng deadlock giữa hai đơn có các SKU chồng lấn nhưng thứ tự đầu vào khác nhau. Không dựa vào thứ tự item do client gửi; chuẩn hóa ở server.

Nếu nghiệp vụ cho phép partial fulfillment, mô hình trạng thái phải thể hiện rõ dòng nào giữ được, dòng nào thiếu và cách tính tổng đơn. Không dùng cùng một transaction all-or-nothing rồi âm thầm bỏ qua SKU thiếu.

## 13. Xử lý deadlock và lock wait timeout

Ngay cả khi lock order nhất quán, deadlock vẫn có thể xảy ra do index phụ, foreign key, thao tác khác hoặc các transaction không tuân thủ cùng thứ tự khóa.

Các nguyên tắc:

- Giữ transaction ngắn; không gọi payment API hoặc gửi email khi đang giữ row lock.
- Khóa tất cả hàng inventory theo thứ tự (warehouse_id, sku), rồi mới ghi/khóa reservation.
- Dùng khóa chính/unique index trong điều kiện WHERE để giới hạn phạm vi khóa.
- Không giữ inventory/reservation lock rồi chờ người dùng hoặc hệ thống bên ngoài.
- Kiểm tra deadlock bằng SHOW ENGINE INNODB STATUS và Performance Schema.
- Retry toàn bộ transaction khi gặp deadlock (error 1213) với số lần giới hạn và backoff có jitter.
- Với lock wait timeout (thường error 1205), rollback transaction rõ ràng theo chính sách rồi mới retry nếu nghiệp vụ còn hợp lệ.
- Không retry lỗi hết hàng như thể đó là lỗi tạm thời.

InnoDB thường rollback một transaction được chọn làm nạn nhân deadlock. Lock wait timeout mặc định có thể chỉ rollback statement gây timeout, tùy cấu hình innodb_rollback_on_timeout; ứng dụng nên chủ động rollback transaction trước khi thử lại toàn bộ đơn vị công việc.

Retry phải dùng lại request key để không tạo reservation trùng nếu lần trước đã commit nhưng phản hồi bị mất.

## 14. Đối soát bộ đếm inventory với reservation

Vì reserved_qty là bộ đếm tổng hợp, cần một truy vấn đối soát định kỳ. Có thể tổng hợp reservation đang hoạt động rồi so với inventory:

~~~sql
SELECT
  i.warehouse_id,
  i.sku,
  i.reserved_qty AS stored_reserved_qty,
  COALESCE(r.calculated_reserved_qty, 0) AS calculated_reserved_qty
FROM inventory AS i
LEFT JOIN (
  SELECT
    warehouse_id,
    sku,
    SUM(quantity) AS calculated_reserved_qty
  FROM inventory_reservations
  WHERE status = 'RESERVED'
  GROUP BY warehouse_id, sku
) AS r
  ON r.warehouse_id = i.warehouse_id
 AND r.sku = i.sku
WHERE i.reserved_qty <> COALESCE(r.calculated_reserved_qty, 0);
~~~

Kết quả phải rỗng khi dữ liệu đã nhất quán. Với bảng lớn, chạy theo phạm vi kho/SKU hoặc batch, vào thời điểm phù hợp và xem xét tải truy vấn. Cần thống nhất snapshot đọc nếu dữ liệu đang thay đổi; nếu đối soát chạy đồng thời với reservation transaction, có thể nhìn thấy một thời điểm trước/sau khác nhau. Dùng consistent snapshot hoặc tạm dừng/điều phối ghi trong quy trình sửa lệch.

Không tự động đặt reserved_qty bằng tổng tính lại trên production khi chưa hiểu nguyên nhân. Trước khi sửa, xác định reservation nào bị thiếu/thừa, kiểm tra audit trail và thực hiện điều chỉnh trong transaction có kiểm soát.

## 15. Kiểm thử cạnh tranh với hai connection độc lập

Một test concurrency phải dùng hai session MySQL thực sự. Hai thread dùng chung một Connection không mô phỏng được hai transaction độc lập.

Bộ test tích hợp tối thiểu:

| Test | Thiết lập | Điều cần xác nhận |
|---|---|---|
| Hai request tranh 7 trên 10 | Hai connection, hai request key | Chỉ một reservation thành công; available không âm |
| Request A rollback | A giữ hàng nhưng rollback khi B đang chờ | B có thể tiếp tục giữ hàng |
| Retry cùng request key | Gửi cùng payload nhiều lần | Chỉ một reservation tồn tại |
| Cùng key, payload khác | Dùng lại key với quantity/SKU khác | Trả conflict, không thay đổi kho |
| Cancel hai lần | Gọi cancel đồng thời hoặc lặp | reserved_qty chỉ giảm một lần |
| Confirm và expiry cạnh tranh | Worker và confirm cùng khóa một reservation | Chỉ một trạng thái cuối được ghi |
| Nhiều SKU khác thứ tự | Hai đơn có danh sách SKU đảo thứ tự | Không oversell; deadlock được giảm và retry được xử lý |
| Rollback do thiếu một SKU | Một dòng đủ hàng, dòng khác thiếu | Không còn reservation hoặc bộ đếm dở dang |
| Mất phản hồi sau COMMIT | Retry cùng request key | Đọc lại kết quả cũ, không giữ hàng lần hai |

Với Testcontainers, pin phiên bản MySQL mục tiêu và dùng Connector/J thật. Tạo hai connection từ DataSource, dùng CountDownLatch hoặc barrier để điều khiển thời điểm bắt đầu, rồi kiểm tra số hàng affected và trạng thái cuối. Không dùng Thread.sleep() làm cơ chế đồng bộ chính vì timing không ổn định.

Có thể kiểm tra invariant sau mỗi test:

~~~sql
SELECT
  on_hand_qty >= 0 AS on_hand_nonnegative,
  reserved_qty >= 0 AS reserved_nonnegative,
  reserved_qty <= on_hand_qty AS reserved_not_over_on_hand
FROM inventory
WHERE warehouse_id = 1
  AND sku = 'SKU-CHAIR';
~~~

Ngoài invariant từng hàng, chạy truy vấn đối soát tổng reservation ở phần trước để bảo đảm bộ đếm tổng hợp khớp chi tiết.

## 16. Tích hợp vào Spring/JDBC

Một service Spring có thể dùng @Transactional để bảo vệ cả UPDATE inventory và INSERT reservation. Mọi thao tác phải dùng cùng DataSource và transaction manager; thứ tự này cũng giữ inventory lock trước khi foreign key của reservation được kiểm tra.

Luồng xử lý ở tầng service:

~~~text
reserve(request)
    |
    +--> validate quantity > 0
    |
    +--> begin transaction
    |
    +--> conditional UPDATE inventory
    |       |
    |       +--> affected rows = 0: rollback, then resolve request_key
    |       |
    |       +--> affected rows = 1
    |              |
    |              +--> insert reservation with request_key
    |                         |
    |                         +--> duplicate/error: rollback
    |                         +--> success: commit
    |
    +--> return reservation id
~~~

Ví dụ khung service:

~~~java
@Transactional
public Reservation reserve(ReserveCommand command) {
    if (command.quantity() <= 0) {
        throw new IllegalArgumentException("quantity must be positive");
    }

    int updated = jdbcTemplate.update("""
        UPDATE inventory
        SET reserved_qty = reserved_qty + ?
        WHERE warehouse_id = ?
          AND sku = ?
          AND on_hand_qty - reserved_qty >= ?
        """,
        command.quantity(),
        command.warehouseId(),
        command.sku(),
        command.quantity()
    );

    if (updated != 1) {
        throw new OutOfStockException(command.sku());
    }

    reservationRepository.insertReserved(
        command.requestKey(),
        command.orderId(),
        command.warehouseId(),
        command.sku(),
        command.quantity()
    );

    return reservationRepository.findByRequestKey(command.requestKey())
        .orElseThrow();
}
~~~

OutOfStockException nên là unchecked exception hoặc cấu hình @Transactional(rollbackFor = ...) nếu dùng checked exception. Nếu không, Spring có thể không rollback theo mặc định cho checked exception và reservation row có nguy cơ được commit dù inventory không tăng.

Duplicate key cần được xử lý theo transaction boundary riêng. Nếu conditional UPDATE ảnh hưởng 0 hàng, transaction phải rollback rồi mới đọc request_key để phân biệt request đã commit trước đó với yêu cầu hết hàng. Nếu UPDATE thành công nhưng INSERT reservation gặp duplicate key, rollback sẽ hoàn tác reserved_qty; sau đó ở luồng ngoài transaction đọc request key đã tồn tại và so sánh payload. Trong Spring, một lỗi database có thể khiến transaction hiện tại bị đánh dấu rollback-only; không tiếp tục sử dụng transaction đó để đọc kết quả idempotency.

Không gọi dịch vụ thanh toán, gửi email hoặc publish message đồng bộ trong khi transaction giữ khóa inventory. Nếu cần phát sự kiện sau commit một cách tin cậy, dùng transactional outbox hoặc cơ chế tương đương.

## 17. Quan sát vận hành

Theo dõi cả số lượng nghiệp vụ và hành vi database:

- Tổng số reservation RESERVED, CONFIRMED, RELEASED và EXPIRED.
- Tuổi reservation hết hạn lâu nhất chưa được worker xử lý.
- Tỷ lệ request hết hàng và duplicate idempotency key.
- Số lần deadlock, lock wait timeout và retry.
- Thời gian giữ transaction và thời gian chờ connection pool.
- available_qty theo kho/SKU.
- Sai lệch giữa reserved_qty và tổng reservation RESERVED.
- Thời gian chạy worker expiry và số reservation xử lý mỗi batch.

Khi điều tra lock, dùng performance_schema.data_lock_waits, performance_schema.data_locks, SHOW ENGINE INNODB STATUS và processlist. Với truy vấn worker, dùng EXPLAIN để xác nhận index expiry được sử dụng; không để worker quét toàn bộ bảng reservation theo chu kỳ.

Đặt cảnh báo nếu reservation hết hạn nhưng vẫn chiếm kho quá lâu, hoặc bộ đếm tổng hợp lệch chi tiết. Những cảnh báo này phát hiện sớm cả lỗi code lẫn job không chạy.

## 18. Các lỗi thiết kế thường gặp

| Cách làm sai | Hậu quả | Cách sửa |
|---|---|---|
| SELECT available rồi UPDATE không điều kiện | Hai request cùng thấy đủ hàng và oversell | Conditional UPDATE hoặc locking read trong transaction |
| Tạo reservation ở transaction khác với cập nhật inventory | Có reservation nhưng không giữ hàng hoặc ngược lại | Cùng transaction InnoDB |
| Không có request key duy nhất | Retry tạo nhiều reservation | Unique idempotency key và payload comparison |
| Hủy reservation không khóa theo lock order | Hai request cùng trừ reserved_qty hoặc deadlock | Khóa inventory trước, reservation sau và chuyển trạng thái có điều kiện |
| Worker expiry khóa reservation trước inventory | Confirm và expiry có thể deadlock hoặc xử lý trùng | Lấy candidate không khóa, khóa inventory trước rồi khóa lại reservation |
| Xóa reservation sau khi hủy | Mất audit và khó idempotent | Giữ trạng thái cuối RELEASED/EXPIRED |
| Dùng cache làm nguồn quyết định tồn kho | Cache cũ có thể xác nhận quá số lượng | MySQL transaction là nguồn quyết định cuối |
| Gọi API ngoài trong transaction | Giữ lock lâu, tăng deadlock và timeout | Chia transaction, dùng outbox/saga |
| Xử lý nhiều SKU theo thứ tự client gửi | Tăng nguy cơ deadlock | Sắp xếp lock order ổn định |
| Retry mọi lỗi | Hết hàng bị retry vô ích; request có thể trùng | Phân loại lỗi và dùng request key ổn định |

## 19. Bài thực hành hoàn chỉnh

Thực hiện lần lượt các phần sau trên MySQL thử nghiệm:

1. Tạo hai bảng inventory và inventory_reservations cùng constraint/index.
2. Nạp SKU-CHAIR với 10 đơn vị và SKU-DESK với 5 đơn vị.
3. Viết transaction reserve: conditional update inventory, insert reservation, kiểm tra affected rows và commit/rollback.
4. Mở hai session, cùng giữ 7 ghế và xác nhận chỉ một session thành công.
5. Gửi lại request thành công với cùng request key; xác minh không tăng reserved_qty lần hai.
6. Thử cùng request key nhưng payload khác; xác minh hệ thống trả conflict.
7. Xác nhận một reservation; kiểm tra on_hand và reserved cùng giảm.
8. Hủy một reservation còn RESERVED hai lần; xác minh chỉ lần đầu giảm reserved.
9. Tạo reservation hết hạn và chạy worker lấy candidate rồi khóa inventory trước, reservation sau.
10. Tạo hai đơn nhiều SKU với thứ tự SKU khác nhau; kiểm tra lock order và xử lý deadlock.
11. Chạy truy vấn đối soát reserved_qty với tổng quantity của reservation RESERVED.
12. Ghi lại kết quả, error code, thời gian chờ, số hàng affected và invariant sau mỗi test.

**Tiêu chí hoàn thành:**

- Không có trường hợp reserved_qty > on_hand_qty.
- Không có reservation RESERVED nếu inventory không được tăng tương ứng.
- Retry cùng request key không tạo giữ chỗ thứ hai.
- Confirm/cancel/expiry chỉ chuyển trạng thái một lần.
- Rollback hoàn tác cả reservation row và bộ đếm inventory.
- Hai session tranh chấp chỉ giữ được lượng hàng thực có.
- Worker expiry có thể chạy song song mà không xử lý trùng reservation.
- Có truy vấn đối soát và log đủ để điều tra sai lệch.

## 20. Ghi nhớ

- Tách tồn vật lý, lượng giữ và lượng khả dụng thành các đại lượng rõ ràng.
- Dùng InnoDB và khóa chính (warehouse_id, sku) để xác định duy nhất bộ đếm kho/SKU.
- Tạo reservation và tăng reserved_qty trong cùng transaction.
- Đưa điều kiện đủ hàng vào UPDATE để kiểm tra và ghi một cách nguyên tử.
- Dùng lock order inventory trước, reservation sau; dùng SELECT ... FOR UPDATE để xác minh trạng thái trước khi confirm, cancel hoặc expiry.
- Dùng request key duy nhất để retry an toàn sau timeout hoặc mất phản hồi COMMIT.
- Xử lý trạng thái cuối idempotent; không trừ bộ đếm lần thứ hai.
- Worker hết hạn lấy candidate không khóa rồi xử lý từng reservation trong transaction theo lock order thống nhất.
- Khóa nhiều SKU theo thứ tự xác định và retry deadlock có giới hạn.
- Đối soát bộ đếm inventory với tổng reservation đang RESERVED.
- Kiểm thử bằng nhiều connection MySQL độc lập; mock hoặc một connection dùng chung không chứng minh được cạnh tranh InnoDB.

Thiết kế giữ chỗ đáng tin cậy dựa trên invariant rõ ràng và transaction nguyên tử. Khi mọi luồng tạo, xác nhận, hủy và hết hạn đều khóa theo cùng quy ước, dùng idempotency key và được kiểm chứng bằng nhiều session thật, hệ thống có thể xử lý cạnh tranh mà không xác nhận vượt tồn kho.

## Tài liệu tham khảo

- [MySQL 8.0 Reference Manual: InnoDB Locking](https://dev.mysql.com/doc/refman/8.0/en/innodb-locking.html)
- [MySQL 8.0 Reference Manual: Locking Reads](https://dev.mysql.com/doc/refman/8.0/en/innodb-locking-reads.html)
- [MySQL 8.0 Reference Manual: InnoDB Transaction Model](https://dev.mysql.com/doc/refman/8.0/en/innodb-transaction-model.html)
- [MySQL 8.0 Reference Manual: SELECT ... FOR UPDATE and SKIP LOCKED](https://dev.mysql.com/doc/refman/8.0/en/innodb-locking-reads.html)
- [MySQL 8.0 Reference Manual: Deadlocks in InnoDB](https://dev.mysql.com/doc/refman/8.0/en/innodb-deadlocks.html)
- [MySQL 8.0 Reference Manual: CHECK Constraints](https://dev.mysql.com/doc/refman/8.0/en/create-table-check-constraints.html)
- [Spring Framework Reference: Declarative Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative.html)
- [Testcontainers for Java: MySQL Module](https://java.testcontainers.org/modules/databases/mysql/)

