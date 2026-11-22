# SAVEPOINT, ROLLBACK TO SAVEPOINT và RELEASE SAVEPOINT

Một transaction có thể gồm nhiều bước nghiệp vụ. Đôi khi các bước chính đã hợp lệ nhưng một bước tùy chọn hoặc một phần xử lý cần được hủy. `SAVEPOINT` đánh dấu một vị trí trong transaction; `ROLLBACK TO SAVEPOINT` hoàn tác các thay đổi phát sinh sau vị trí đó mà vẫn giữ transaction mở; `RELEASE SAVEPOINT` xóa điểm đánh dấu khi không còn cần dùng.

Trong MySQL với InnoDB, savepoint giúp xây dựng luồng xử lý có thể phục hồi từng phần, ví dụ tạo đơn hàng và giữ hàng tồn kho nhưng bỏ qua một bước áp dụng ưu đãi bị lỗi. Savepoint không tạo transaction con, không commit độc lập và không thay thế việc quản lý transaction ở ứng dụng.

Trong module `DATABASE_MYSQL`, kỹ thuật này liên quan trực tiếp tới transaction, rollback, xử lý lỗi, locking và tính nhất quán dữ liệu. Bài học tập trung vào MySQL 8.x và bảng InnoDB.

## Mục tiêu

Sau bài này, bạn có thể:

- Giải thích vai trò của savepoint trong một transaction đang mở.
- Tạo điểm đánh dấu bằng `SAVEPOINT`.
- Hoàn tác một phần bằng `ROLLBACK TO SAVEPOINT` mà không hủy toàn transaction.
- Xóa điểm đánh dấu bằng `RELEASE SAVEPOINT`.
- Quản lý nhiều savepoint, tên trùng và thứ tự rollback.
- Phân biệt rollback một phần với `ROLLBACK` toàn transaction và `COMMIT`.
- Nhận biết các trường hợp savepoint mất hiệu lực như commit hoặc implicit commit.
- Hiểu giới hạn của savepoint với engine không transactional, auto-increment, lock và deadlock.
- Thiết kế luồng xử lý lỗi an toàn trong ứng dụng.

## 1. Transaction và savepoint

Transaction gom nhiều câu lệnh thành một đơn vị công việc. Với InnoDB, transaction có thể kết thúc bằng `COMMIT` để xác nhận thay đổi hoặc `ROLLBACK` để hoàn tác các thay đổi chưa commit.

Savepoint tạo một mốc bên trong transaction. Sau khi tạo, ứng dụng có thể tiếp tục chạy SQL. Nếu một phần công việc cần hủy, `ROLLBACK TO SAVEPOINT` đưa dữ liệu transactional về trạng thái tại mốc đó; các thao tác trước mốc vẫn nằm trong transaction.

```text
START TRANSACTION
       |
       v
   SQL bước 1
       |
       v
   SAVEPOINT s1
       |
       v
   SQL bước 2, 3
       |
       +---- lỗi/phần tùy chọn không hợp lệ ----+
       |                                        |
       v                                        v
   SQL bước 4                         ROLLBACK TO s1
       |                                        |
       +--------------------+-------------------+
                            |
                            v
                    COMMIT hoặc ROLLBACK
```

Điểm quan trọng: `ROLLBACK TO SAVEPOINT` không kết thúc transaction. Sau khi rollback một phần, ứng dụng vẫn phải quyết định tiếp tục xử lý rồi `COMMIT`, hoặc hủy toàn bộ bằng `ROLLBACK`.

## 2. Điều kiện để dùng savepoint

Savepoint phải nằm trong một transaction đang hoạt động. Với cấu hình mặc định `autocommit = 1`, mỗi câu lệnh độc lập thường được commit tự động; hãy mở transaction rõ ràng trước khi tạo savepoint:

```sql
START TRANSACTION;

UPDATE account
SET balance = balance - 100.00
WHERE account_id = 10;

SAVEPOINT after_debit;

-- Các câu lệnh tiếp theo thuộc cùng transaction.

ROLLBACK TO SAVEPOINT after_debit;
ROLLBACK;
```

Ví dụ trên chỉ minh họa cú pháp và phạm vi transaction. `ROLLBACK TO` hoàn tác phần sau savepoint; `ROLLBACK` cuối cùng hủy toàn bộ transaction, bao gồm cả cập nhật trước savepoint.

Kiểm tra chế độ autocommit:

```sql
SELECT @@SESSION.autocommit;
```

Có thể dùng `SET autocommit = 0` để mỗi session bắt đầu transaction ngầm khi thực hiện thao tác transactional, nhưng với luồng công việc cần ranh giới rõ ràng, `START TRANSACTION` và `COMMIT`/`ROLLBACK` thường dễ đọc hơn. Không nhầm việc đặt `autocommit = 0` với việc một transaction đã được commit.

## 3. SAVEPOINT: tạo điểm đánh dấu

Cú pháp:

```sql
SAVEPOINT savepoint_name;
```

Ví dụ:

```sql
START TRANSACTION;

UPDATE inventory
SET reserved_qty = reserved_qty + 2
WHERE sku = 'KB-01';

SAVEPOINT after_reservation;

INSERT INTO order_note (order_id, note_text)
VALUES (5001, 'Khách yêu cầu giao buổi sáng');

-- Tiếp tục các bước khác...

COMMIT;
```

Savepoint `after_reservation` đánh dấu trạng thái sau khi cập nhật lượng hàng giữ chỗ. Nếu các thao tác tiếp theo cần hủy, ứng dụng có thể quay về mốc này mà vẫn giữ phần cập nhật tồn kho trước đó.

Tên savepoint là tên do ứng dụng chọn. Nên đặt tên phản ánh ranh giới nghiệp vụ, chẳng hạn `before_optional_discount`, `after_stock_reservation` hoặc `before_import_row_20`. Tránh tên quá chung chung như `s1`, `temp` trong luồng có nhiều bước.

## 4. ROLLBACK TO SAVEPOINT: hoàn tác một phần

Cú pháp:

```sql
ROLLBACK TO SAVEPOINT savepoint_name;
```

Lệnh này hoàn tác các thay đổi transactional được thực hiện sau savepoint đã chỉ định. Các thay đổi trước savepoint vẫn nằm trong transaction và có thể được commit hoặc rollback sau đó.

Ví dụ đơn giản:

```sql
START TRANSACTION;

UPDATE account
SET balance = balance - 100.00
WHERE account_id = 10;

SAVEPOINT after_first_update;

UPDATE account
SET balance = balance + 100.00
WHERE account_id = 20;

ROLLBACK TO SAVEPOINT after_first_update;

-- Cập nhật tài khoản 20 đã bị hoàn tác.
-- Cập nhật tài khoản 10 vẫn còn trong transaction.

COMMIT;
```

Sau `COMMIT`, chỉ cập nhật tài khoản 10 được lưu. Ví dụ này cố ý tạo trạng thái chưa cân bằng để minh họa phạm vi rollback; không dùng cách xử lý này cho chuyển tiền thực tế. Với nghiệp vụ chuyển tiền, nếu một vế thất bại thì thường phải rollback toàn transaction để tránh chỉ ghi nợ hoặc chỉ ghi có.

### 4.1. Savepoint được giữ lại sau ROLLBACK TO

`ROLLBACK TO SAVEPOINT` không xóa savepoint được chỉ định. Có thể tiếp tục thao tác rồi rollback về cùng mốc thêm lần nữa:

```sql
START TRANSACTION;

SAVEPOINT checkpoint_a;

INSERT INTO import_log (message) VALUES ('attempt 1');
ROLLBACK TO SAVEPOINT checkpoint_a;

INSERT INTO import_log (message) VALUES ('attempt 2');
ROLLBACK TO SAVEPOINT checkpoint_a;

-- Cả hai lần INSERT sau checkpoint_a đều đã bị hoàn tác.
COMMIT;
```

Transaction vẫn mở sau mỗi lần rollback về mốc. Nếu muốn bỏ mốc đó, gọi `RELEASE SAVEPOINT`.

### 4.2. Các savepoint mới hơn bị loại bỏ

Nếu có nhiều mốc theo thứ tự:

```sql
START TRANSACTION;
SAVEPOINT s1;
SAVEPOINT s2;
SAVEPOINT s3;

ROLLBACK TO SAVEPOINT s1;
```

Khi rollback về `s1`, các thay đổi sau `s1` bị hoàn tác và các savepoint được tạo sau `s1` (`s2`, `s3`) bị xóa. `s1` vẫn còn hiệu lực. Không thể tiếp tục rollback về `s2` hoặc `s3` sau thao tác này.

## 5. RELEASE SAVEPOINT: xóa điểm đánh dấu

Cú pháp:

```sql
RELEASE SAVEPOINT savepoint_name;
```

`RELEASE SAVEPOINT` xóa mốc khỏi transaction. Nó không hoàn tác các câu lệnh đã thực hiện sau mốc, không commit và không rollback dữ liệu.

```sql
START TRANSACTION;

UPDATE inventory
SET reserved_qty = reserved_qty + 1
WHERE sku = 'KB-01';

SAVEPOINT before_optional_note;

INSERT INTO order_note (order_id, note_text)
VALUES (5001, 'Giao ngoài giờ hành chính');

RELEASE SAVEPOINT before_optional_note;

COMMIT;
```

Ở đây ghi chú vẫn được lưu vì `RELEASE` chỉ xóa điểm đánh dấu. Nếu gọi `ROLLBACK TO SAVEPOINT` trước khi release, thao tác ghi chú mới bị hoàn tác.

Các savepoint còn lại tự động bị giải phóng khi transaction kết thúc bằng `COMMIT` hoặc `ROLLBACK`. Vì vậy, `RELEASE` thường hữu ích khi luồng xử lý còn dài và không cần giữ mốc nữa; không bắt buộc phải release mọi savepoint trước commit.

## 6. Nhiều savepoint và tên bị dùng lại

Có thể tạo nhiều savepoint trong cùng transaction:

```sql
START TRANSACTION;

UPDATE inventory
SET reserved_qty = reserved_qty + 1
WHERE sku = 'KB-01';
SAVEPOINT stock_reserved;

INSERT INTO orders (order_id, sku, quantity, order_status)
VALUES (5001, 'KB-01', 1, 'PENDING');
SAVEPOINT order_created;

INSERT INTO order_note (order_id, note_text)
VALUES (5001, 'Ghi chú tùy chọn');
SAVEPOINT note_added;

ROLLBACK TO SAVEPOINT order_created;

-- note_added đã bị loại bỏ; order_created vẫn còn.
-- Phần ghi chú bị hoàn tác, cập nhật tồn kho và tạo đơn vẫn còn.

COMMIT;
```

Nếu tạo một savepoint mới có cùng tên với savepoint hiện có, savepoint cũ bị thay thế bằng mốc mới:

```sql
START TRANSACTION;

SAVEPOINT step_marker;
UPDATE account SET balance = balance - 10 WHERE account_id = 10;

SAVEPOINT step_marker;
-- Mốc step_marker cũ bị thay bằng mốc mới ở vị trí hiện tại.

ROLLBACK TO SAVEPOINT step_marker;
-- Chỉ hoàn tác các thay đổi sau lần SAVEPOINT thứ hai.

ROLLBACK;
```

Việc tái sử dụng tên có thể gây nhầm lẫn khi đọc log hoặc bảo trì code. Trong luồng phức tạp, dùng tên khác nhau cho từng giai đoạn.

## 7. Ví dụ nghiệp vụ: đơn hàng, tồn kho và bước ưu đãi tùy chọn

Giả sử quy trình đặt hàng có hai phần cốt lõi: tạo đơn và giữ hàng. Áp dụng điểm thưởng/ưu đãi là bước bổ sung; nếu bước này không hợp lệ, hệ thống vẫn có thể tiếp tục đơn hàng theo chính sách nghiệp vụ.

Schema minh họa:

```sql
CREATE TABLE inventory (
    sku VARCHAR(30) NOT NULL,
    available_qty INT NOT NULL,
    reserved_qty INT NOT NULL DEFAULT 0,
    PRIMARY KEY (sku),
    CONSTRAINT chk_inventory_qty
        CHECK (available_qty >= 0 AND reserved_qty >= 0)
) ENGINE=InnoDB;

CREATE TABLE orders (
    order_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    sku VARCHAR(30) NOT NULL,
    quantity INT NOT NULL,
    order_status VARCHAR(20) NOT NULL,
    PRIMARY KEY (order_id),
    KEY idx_orders_sku (sku),
    CONSTRAINT chk_order_quantity CHECK (quantity > 0)
) ENGINE=InnoDB;

CREATE TABLE order_promotion (
    order_id BIGINT UNSIGNED NOT NULL,
    promotion_code VARCHAR(30) NOT NULL,
    discount_amount DECIMAL(12, 2) NOT NULL,
    PRIMARY KEY (order_id, promotion_code),
    CONSTRAINT chk_promotion_discount CHECK (discount_amount >= 0)
) ENGINE=InnoDB;
```

Schema chỉ tập trung minh họa savepoint; hệ thống thật cần bổ sung khóa ngoại, kiểm tra tồn kho, quy tắc giá và quyền ghi phù hợp. Bảng dùng InnoDB để các thay đổi có thể rollback. Các ràng buộc `CHECK` được MySQL thực thi từ 8.0.16 trở lên.

### 7.1. Kịch bản bước tùy chọn thành công

```sql
START TRANSACTION;

INSERT INTO orders (sku, quantity, order_status)
VALUES ('KB-01', 2, 'PENDING');

SET @new_order_id = LAST_INSERT_ID();

UPDATE inventory
SET available_qty = available_qty - 2,
    reserved_qty = reserved_qty + 2
WHERE sku = 'KB-01'
  AND available_qty >= 2;

-- Ứng dụng phải kiểm tra ROW_COUNT() = 1.
-- Nếu không cập nhật được đúng một hàng, ROLLBACK toàn transaction.

SAVEPOINT before_optional_promotion;

INSERT INTO order_promotion
    (order_id, promotion_code, discount_amount)
VALUES
    (@new_order_id, 'WELCOME10', 10.00);

RELEASE SAVEPOINT before_optional_promotion;

COMMIT;
```

Khi tất cả bước thành công, đơn hàng, cập nhật giữ hàng và ưu đãi được commit cùng nhau. Nếu ưu đãi không cần rollback, savepoint có thể được release hoặc để tự mất khi commit.

### 7.2. Kịch bản bước tùy chọn thất bại

Giữ nguyên các bước tạo đơn và giữ hàng, nhưng khi bước áp dụng ưu đãi cần hủy:

```sql
ROLLBACK TO SAVEPOINT before_optional_promotion;

-- Đơn hàng và cập nhật tồn kho trước savepoint vẫn còn.
-- Không còn thay đổi ưu đãi sau savepoint.

COMMIT;
```

Đoạn này giả định ứng dụng đã tạo savepoint và thực hiện các thao tác ưu đãi trong cùng transaction. Nếu bước ưu đãi phát sinh lỗi SQL, tầng ứng dụng cần bắt lỗi, xác định transaction vẫn còn hoạt động và gọi rollback về savepoint khi phù hợp. Không chạy đoạn rollback như một statement độc lập sau khi transaction đã kết thúc.

### 7.3. Nếu bước cốt lõi thất bại

Nếu không giữ được hàng hoặc không tạo được đơn, không nên commit một phần trạng thái cốt lõi:

```sql
ROLLBACK;
```

`ROLLBACK` toàn transaction hủy cả việc tạo đơn và thay đổi tồn kho. Quy tắc chọn rollback một phần hay toàn bộ phải dựa trên ranh giới nghiệp vụ, không chỉ dựa trên việc câu lệnh nào phát sinh lỗi.

## 8. Savepoint trong xử lý nhiều bước hoặc import batch

Savepoint có thể giúp xử lý từng bản ghi trong một batch mà vẫn giữ các bản ghi hợp lệ trước đó trong cùng transaction. Ví dụ minh họa:

```sql
START TRANSACTION;

SAVEPOINT before_row_1;
INSERT INTO staging_result (source_id, normalized_value)
VALUES (1, 'A');

SAVEPOINT before_row_2;
INSERT INTO staging_result (source_id, normalized_value)
VALUES (2, 'B');

-- Nếu bản ghi thứ 3 không hợp lệ:
SAVEPOINT before_row_3;
INSERT INTO staging_result (source_id, normalized_value)
VALUES (3, 'INVALID');

-- Sau khi ứng dụng phát hiện lỗi nghiệp vụ:
ROLLBACK TO SAVEPOINT before_row_3;

-- Có thể tiếp tục xử lý bản ghi khác.
SAVEPOINT before_row_4;
INSERT INTO staging_result (source_id, normalized_value)
VALUES (4, 'D');

COMMIT;
```

Các hàng 1, 2 và 4 được commit; hàng 3 bị loại nếu rollback về đúng savepoint. Đây là ví dụ luồng tuần tự; ứng dụng thật cần quản lý tên savepoint, lỗi SQL, trạng thái kết nối và quyết định batch nào phải rollback toàn bộ.

### 8.1. Chọn ranh giới transaction và savepoint

Không nhất thiết tạo một savepoint cho mọi câu SQL. Hãy đặt mốc ở ranh giới có ý nghĩa:

- Sau phần dữ liệu cốt lõi đã được xác thực.
- Trước bước tùy chọn có thể bỏ qua.
- Trước một nhóm thao tác có thể thử lại độc lập.
- Trước một bản ghi trong batch khi chính sách cho phép giữ các bản ghi khác.

Quá nhiều savepoint làm code khó hiểu và tăng công sức quản lý. Với batch rất lớn, chia thành nhiều transaction nhỏ có thể phù hợp hơn một transaction dài chứa hàng nghìn savepoint; quyết định phụ thuộc yêu cầu atomicity và khả năng phục hồi.

## 9. Savepoint không phải nested transaction

MySQL không tạo transaction lồng nhau bằng cách gọi `START TRANSACTION` bên trong transaction đang hoạt động. `START TRANSACTION` khi được gọi trong lúc đã có transaction sẽ kết thúc transaction hiện tại bằng implicit commit trước khi bắt đầu transaction mới.

Savepoint chỉ là mốc rollback bên trong cùng một transaction:

| Hành động | Savepoint | Nested transaction thực sự |
|---|---|---|
| Có thể rollback một phần | Có | Có, tùy hệ quản trị |
| Có thể commit phần con độc lập | Không | Có thể có trong hệ hỗ trợ nested transaction |
| Phần trước mốc vẫn chờ transaction ngoài | Có | Tùy mô hình |
| `COMMIT` toàn bộ | Commit mọi thay đổi còn lại của transaction | Phụ thuộc hệ quản trị |

Ví dụ:

```sql
START TRANSACTION;
INSERT INTO audit_event (event_name) VALUES ('outer start');

SAVEPOINT inner_work;
INSERT INTO audit_event (event_name) VALUES ('optional step');
ROLLBACK TO SAVEPOINT inner_work;

-- Không có COMMIT độc lập cho inner_work.
COMMIT;
```

Chỉ `outer start` được lưu. Dữ liệu sau savepoint bị hoàn tác; savepoint không thể commit riêng phần thay đổi của nó.

## 10. Savepoint và trạng thái transaction

| Lệnh | Ảnh hưởng dữ liệu | Transaction sau lệnh | Savepoint |
|---|---|---|---|
| `SAVEPOINT s` | Không thay đổi dữ liệu | Vẫn mở | Tạo hoặc thay thế `s` |
| `ROLLBACK TO SAVEPOINT s` | Hoàn tác thay đổi sau `s` | Vẫn mở | `s` còn; các mốc mới hơn bị xóa |
| `RELEASE SAVEPOINT s` | Không hoàn tác thay đổi | Vẫn mở | Xóa `s` |
| `COMMIT` | Xác nhận mọi thay đổi còn lại | Kết thúc | Tất cả mốc bị xóa |
| `ROLLBACK` | Hoàn tác toàn transaction | Kết thúc | Tất cả mốc bị xóa |

Nếu tham chiếu một savepoint không còn tồn tại hoặc tên không đúng, MySQL báo lỗi. Những nguyên nhân thường gặp là đã commit/rollback transaction, đã rollback về một mốc cũ làm mất các mốc mới hơn, hoặc đã release mốc đó.

## 11. Tác động của COMMIT ngầm và câu lệnh DDL

Savepoint chỉ tồn tại trong transaction hiện tại. Khi transaction kết thúc, các savepoint mất hiệu lực. Một số câu lệnh trong MySQL gây implicit commit; nhiều câu lệnh DDL như `CREATE TABLE`, `ALTER TABLE`, `DROP TABLE` và các thao tác quản trị khác thuộc nhóm này.

Ví dụ không nên kỳ vọng rollback về savepoint sau DDL:

```sql
START TRANSACTION;
UPDATE account SET balance = balance - 10 WHERE account_id = 10;
SAVEPOINT before_ddl;

CREATE TABLE temp_work (id INT PRIMARY KEY);

-- DDL có thể đã implicit commit transaction trước đó.
-- Không thể dựa vào before_ddl để rollback phần cập nhật cũ.
```

Một số ngoại lệ liên quan tới temporary table có quy tắc implicit commit riêng; không nên khái quát rằng mọi câu DDL đều có hành vi giống nhau. Kiểm tra tài liệu phiên bản MySQL đang dùng trước khi trộn DDL với transaction nghiệp vụ.

Các thao tác như `START TRANSACTION` khi transaction cũ đang mở, hoặc thay đổi `autocommit` từ 0 sang 1, cũng có thể kết thúc transaction hiện tại. Hãy tránh thực hiện DDL và các thao tác implicit commit ở giữa luồng cần rollback bằng savepoint.

## 12. Storage engine và những thay đổi không rollback được

Savepoint chỉ có ý nghĩa đối với thay đổi của storage engine hỗ trợ transaction/savepoint. InnoDB là lựa chọn mặc định phù hợp cho các luồng cần atomicity.

Nếu một transaction cập nhật cả bảng InnoDB và bảng dùng engine không transactional, `ROLLBACK TO SAVEPOINT` hoặc `ROLLBACK` không thể đảm bảo hoàn tác thay đổi ở bảng nontransactional. Khi thiết kế luồng nghiệp vụ cần rollback một phần, tất cả bảng tham gia nên dùng engine transactional tương thích.

### 12.1. AUTO_INCREMENT có thể bị khuyết sau rollback

Giá trị `AUTO_INCREMENT` đã cấp không nhất thiết được tái sử dụng sau rollback:

```sql
START TRANSACTION;

INSERT INTO orders (sku, quantity, order_status)
VALUES ('KB-01', 1, 'PENDING');

ROLLBACK;
```

Lần insert đã lấy một ID nhưng transaction bị rollback. ID đó có thể không xuất hiện trong bảng và lần insert sau có thể nhận ID lớn hơn. Không coi ID tăng liên tục là bằng chứng về số lượng bản ghi hoặc lỗi của savepoint.

## 13. Locking, isolation và lỗi đồng thời

Savepoint không tạo transaction mới và không giải phóng toàn bộ lock như thể transaction đã kết thúc. Với InnoDB, rollback về savepoint có thể hoàn tác dữ liệu nhưng các row lock đã được giữ trong bộ nhớ sau savepoint không nhất thiết được giải phóng. Vì vậy, không dùng savepoint với kỳ vọng tự động nhường mọi lock cho transaction khác.

Transaction vẫn giữ phạm vi isolation và snapshot theo quy tắc của isolation level hiện tại. `ROLLBACK TO SAVEPOINT` không khởi động transaction mới và không tự tạo snapshot mới.

### 13.1. Lock wait timeout và deadlock

Khi xảy ra lock wait timeout, InnoDB mặc định thường rollback statement bị timeout; nếu `innodb_rollback_on_timeout` được bật thì có thể rollback toàn transaction. Ứng dụng cần biết cấu hình và trạng thái transaction trước khi quyết định rollback về savepoint hay rollback toàn bộ.

Khi InnoDB phát hiện deadlock, nó chọn một transaction làm nạn nhân và rollback toàn transaction đó. Savepoint không giữ lại phần trước điểm đánh dấu trong trường hợp transaction bị rollback do deadlock. Ứng dụng thường phải retry toàn bộ đơn vị công việc trong transaction mới.

Kiểm tra cấu hình timeout rollback:

```sql
SELECT @@GLOBAL.innodb_rollback_on_timeout;
```

Không retry một câu lệnh tùy tiện trong transaction nếu chưa xác định transaction còn hợp lệ và các thao tác trước đó đang ở trạng thái nào.

## 14. Mẫu xử lý lỗi trong ứng dụng

SQL script minh họa thường viết tuần tự, nhưng ứng dụng phải quyết định nhánh thành công/thất bại dựa trên kết quả từng statement. Một mẫu xử lý tổng quát:

```text
begin transaction
execute required steps
if a required step fails:
    rollback entire transaction
else:
    create savepoint before_optional_step
    execute optional steps
    if optional step fails and policy allows skipping it:
        rollback to savepoint before_optional_step
        continue with valid core work
    else:
        release savepoint when no longer needed
    commit transaction
```

Các nguyên tắc triển khai:

- Dùng cùng một connection cho toàn bộ transaction và savepoint.
- Không trả connection về pool khi transaction chưa được commit/rollback.
- Nếu lỗi khiến transaction bị server rollback toàn bộ, không tiếp tục dùng savepoint cũ.
- Nếu rollback về savepoint thành công, vẫn cần commit hoặc rollback transaction ngoài.
- Bảo đảm mọi bảng cần phục hồi đều dùng engine transactional.
- Giữ transaction ngắn để giảm thời gian giữ lock.
- Không thực hiện side effect bên ngoài database (gửi email, gọi API thanh toán) với giả định rollback SQL sẽ hoàn tác side effect đó.

Với JDBC, `Connection.setSavepoint()`, `Connection.rollback(savepoint)` và `Connection.releaseSavepoint(savepoint)` là các API tương ứng. Tắt auto-commit hoặc bắt đầu transaction theo cấu hình phù hợp trước khi gọi chúng; dùng cùng connection cho tới khi transaction kết thúc.

Ví dụ Java rút gọn:

```java
connection.setAutoCommit(false);

try {
    createOrder(connection);
    reserveInventory(connection);

    Savepoint optionalStep = connection.setSavepoint("before_optional_promotion");
    try {
        applyPromotion(connection);
        connection.releaseSavepoint(optionalStep);
    } catch (SQLException optionalFailure) {
        connection.rollback(optionalStep);
        // Chỉ tiếp tục nếu chính sách cho phép bỏ qua ưu đãi.
    }

    connection.commit();
} catch (SQLException failure) {
    try {
        connection.rollback();
    } catch (SQLException rollbackFailure) {
        failure.addSuppressed(rollbackFailure);
        // Đánh dấu connection không an toàn để tái sử dụng và evict khỏi pool.
    }
    throw failure;
}
```

Đây là khung minh họa, chưa bao gồm mọi chính sách quản lý connection. Sau khi commit hoặc rollback thành công, khôi phục `autoCommit` theo hợp đồng của connection pool. Nếu rollback thất bại, không trả connection đó về pool như một connection sạch; hãy đóng hoặc evict nó theo cơ chế của pool. Không đặt `setAutoCommit(true)` vô điều kiện trong `finally`, vì việc bật auto-commit khi transaction còn hoạt động có thể commit transaction. Nếu `commit()` gặp lỗi kết nối, kết quả commit có thể không xác định với client; cần cơ chế idempotency hoặc đối soát theo ID nghiệp vụ trước khi retry.

## 15. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| `ROLLBACK TO SAVEPOINT` báo không tồn tại | Chưa tạo, đã release, transaction đã kết thúc hoặc mốc mới hơn bị xóa | Kiểm tra luồng và thứ tự savepoint |
| Rollback về mốc nhưng transaction vẫn chưa kết thúc | Đây là hành vi đúng | Tiếp tục rồi `COMMIT` hoặc `ROLLBACK` toàn bộ |
| Dữ liệu sau savepoint vẫn còn | Đã dùng `RELEASE` thay vì `ROLLBACK TO`, hoặc thao tác thuộc engine không transactional | Xác minh engine và đúng lệnh rollback |
| Dữ liệu trước savepoint bị mất | Ứng dụng gọi `ROLLBACK` toàn transaction hoặc gặp deadlock | Phân biệt rollback một phần và rollback toàn bộ |
| Savepoint cũ không còn sau khi rollback | Rollback về mốc cũ loại bỏ các mốc được tạo sau nó | Tạo lại mốc cần dùng sau rollback |
| Savepoint biến mất sau DDL | Statement gây implicit commit | Tách DDL khỏi transaction nghiệp vụ |
| Tưởng RELEASE hoàn tác dữ liệu | Nhầm xóa marker với rollback | `RELEASE` chỉ xóa savepoint; dùng `ROLLBACK TO` để hoàn tác |
| Lock vẫn còn sau rollback một phần | InnoDB transaction vẫn mở và lock có thể tiếp tục được giữ | Kết thúc transaction sớm khi có thể |
| ID AUTO_INCREMENT bị nhảy | Giá trị đã cấp không được tái sử dụng sau rollback | Không dựa vào ID liên tục |
| Retry savepoint sau deadlock thất bại | InnoDB đã rollback toàn transaction | Bắt đầu transaction mới và retry toàn bộ đơn vị công việc |

## 16. Quy trình chọn rollback một phần hay toàn bộ

Trước khi đặt savepoint, xác định ranh giới nghiệp vụ:

1. Bước nào bắt buộc để giao dịch được xem là hợp lệ?
2. Bước nào tùy chọn và có thể bỏ qua mà không làm sai trạng thái cốt lõi?
3. Nếu bước tùy chọn thất bại, dữ liệu trước savepoint có còn nhất quán không?
4. Tất cả bảng tham gia có dùng InnoDB hoặc engine transactional tương thích không?
5. Có DDL hoặc câu lệnh implicit commit nào nằm giữa savepoint và rollback không?
6. Lỗi là lỗi statement, lock timeout hay deadlock khiến toàn transaction bị rollback?
7. Có side effect ngoài database cần bù trừ hoặc xử lý qua outbox không?
8. Sau rollback một phần, transaction có thể commit an toàn không?

Nếu không thể chứng minh trạng thái còn lại hợp lệ, hãy rollback toàn transaction. Savepoint chỉ hữu ích khi ranh giới phục hồi từng phần được định nghĩa rõ ràng.

## 17. Bài thực hành

Thực hiện trong schema lab riêng với bảng InnoDB:

1. Mở transaction, cập nhật một hàng, tạo savepoint, cập nhật hàng khác và rollback về savepoint; xác minh chỉ cập nhật đầu tiên còn trong transaction.
2. Sau `ROLLBACK TO`, thực hiện thêm một cập nhật rồi rollback về cùng savepoint lần nữa; xác nhận savepoint vẫn còn hiệu lực.
3. Tạo `s1`, `s2`, `s3`, rollback về `s1`; thử rollback về `s2` và ghi nhận lỗi vì mốc mới hơn đã bị loại.
4. Tạo hai savepoint cùng tên ở hai thời điểm; xác minh tên cũ được thay thế và rollback chỉ về vị trí mới.
5. Dùng `RELEASE SAVEPOINT`, sau đó thử rollback về tên vừa release; xác nhận không còn mốc.
6. So sánh `ROLLBACK TO SAVEPOINT` với `ROLLBACK` toàn transaction và `COMMIT`.
7. Tạo một transaction đặt savepoint rồi thực hiện DDL; quan sát implicit commit và xác minh savepoint không còn dùng được.
8. Chèn hàng có `AUTO_INCREMENT` rồi rollback; chèn lại và quan sát ID có thể bị khuyết.
9. Tạo một bảng transactional và một bảng nontransactional trong lab nếu engine được hỗ trợ; so sánh khả năng rollback và ghi lại giới hạn.
10. Dùng `SHOW ENGINE INNODB STATUS` để quan sát deadlock trong môi trường thử nghiệm; xác nhận deadlock có thể rollback toàn transaction thay vì chỉ rollback về savepoint.
11. Viết luồng tạo đơn/giữ hàng/bước ưu đãi tùy chọn; xác định rõ trường hợp rollback một phần và trường hợp rollback toàn bộ.
12. Viết chương trình JDBC dùng `Savepoint`; kiểm tra việc dùng cùng connection, xử lý exception và kết thúc transaction.

Bạn hoàn thành bài khi có thể dự đoán chính xác phần thay đổi nào còn lại sau mỗi lệnh, biết lúc nào savepoint mất hiệu lực và thiết kế được nhánh phục hồi mà không để lại trạng thái nghiệp vụ dở dang.

## 18. Nguyên tắc cần ghi nhớ

- `SAVEPOINT name` tạo mốc trong transaction đang mở.
- `ROLLBACK TO SAVEPOINT name` hoàn tác thay đổi sau mốc nhưng không kết thúc transaction.
- Savepoint được rollback tới vẫn còn hiệu lực; các savepoint được tạo sau nó bị loại bỏ.
- `RELEASE SAVEPOINT name` chỉ xóa mốc, không commit và không hoàn tác dữ liệu.
- `COMMIT` và `ROLLBACK` toàn transaction xóa mọi savepoint.
- Dùng lại tên savepoint sẽ thay thế mốc cũ bằng mốc mới.
- Savepoint không phải nested transaction và không thể commit phần con độc lập.
- Bắt đầu transaction mới hoặc chạy câu lệnh implicit commit có thể làm savepoint mất hiệu lực.
- Chỉ dữ liệu transactional mới có thể được phục hồi theo transaction/savepoint; ưu tiên InnoDB cho mọi bảng tham gia.
- Rollback không bảo đảm tái sử dụng giá trị `AUTO_INCREMENT` đã cấp.
- Rollback về savepoint không đồng nghĩa giải phóng mọi row lock; transaction vẫn mở.
- Deadlock của InnoDB có thể rollback toàn transaction; ứng dụng phải retry đơn vị công việc trong transaction mới.
- Chỉ rollback một phần khi các bước còn lại vẫn tạo thành trạng thái nghiệp vụ hợp lệ; nếu không, rollback toàn bộ.
