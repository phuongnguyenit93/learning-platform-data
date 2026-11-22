# Nhiều trigger cùng thời điểm/sự kiện và FOLLOWS/PRECEDES

## Mục tiêu bài học

Sau bài này, bạn có thể:

- Giải thích cách MySQL phân loại trigger theo bảng, thời điểm BEFORE/AFTER và sự kiện INSERT/UPDATE/DELETE.
- Hiểu vì sao một bảng có thể có nhiều trigger cho cùng một cặp thời điểm và sự kiện.
- Mô tả thứ tự mặc định theo thời điểm tạo khi không có chỉ dẫn thứ tự.
- Dùng FOLLOWS và PRECEDES để đặt trigger mới sau hoặc trước một trigger đã tồn tại.
- Nhận biết điều kiện bắt buộc của trigger được tham chiếu: cùng bảng, cùng thời điểm và cùng sự kiện.
- Phân biệt thứ tự trong nhóm BEFORE với nhóm AFTER.
- Hiểu cách các trigger BEFORE truyền thay đổi qua NEW cho trigger chạy sau.
- Kiểm tra thứ tự thực thi bằng INFORMATION_SCHEMA.TRIGGERS và ACTION_ORDER.
- Quản lý thay đổi thứ tự trigger khi triển khai, kiểm thử và nâng cấp phiên bản.
- Tránh các lỗi thường gặp khi nhiều trigger cùng cập nhật dữ liệu hoặc ghi audit.

Một trigger được gắn với một bảng, một thời điểm và một sự kiện. Thời điểm có thể là BEFORE hoặc AFTER; sự kiện có thể là INSERT, UPDATE hoặc DELETE. Trong MySQL hiện đại, một bảng có thể có nhiều trigger cùng thuộc một nhóm, ví dụ nhiều BEFORE UPDATE trigger.

Nếu không chỉ định thứ tự, các trigger cùng nhóm chạy theo thứ tự được tạo. Khi cần điều khiển rõ ràng, MySQL cho phép khai báo FOLLOWS hoặc PRECEDES ngay sau FOR EACH ROW trong CREATE TRIGGER. FOLLOWS đặt trigger mới sau trigger được nêu; PRECEDES đặt trigger mới trước trigger được nêu.

Thứ tự này quan trọng khi một trigger chuẩn hóa dữ liệu, trigger tiếp theo kiểm tra dữ liệu đã chuẩn hóa, rồi trigger khác đóng dấu thời gian hoặc ghi audit. Nếu không quản lý thứ tự, logic giữa các trigger có thể phụ thuộc vào lịch sử triển khai và khó chẩn đoán.

## 1. Nhóm trigger theo thời điểm và sự kiện

MySQL xác định một nhóm trigger bằng ba yếu tố:

1. Bảng được gắn trigger.
2. Thời điểm kích hoạt: BEFORE hoặc AFTER.
3. Sự kiện kích hoạt: INSERT, UPDATE hoặc DELETE.

Ví dụ trên bảng orders:

| Nhóm | Thời điểm | Sự kiện | Ví dụ mục đích |
|---|---|---|---|
| 1 | BEFORE | INSERT | Chuẩn hóa dữ liệu trước khi thêm hàng |
| 2 | AFTER | INSERT | Ghi nhận sự kiện tạo đơn |
| 3 | BEFORE | UPDATE | Chuẩn hóa hoặc kiểm tra giá trị mới |
| 4 | AFTER | UPDATE | Ghi audit sau khi cập nhật |
| 5 | BEFORE | DELETE | Kiểm tra điều kiện xóa |
| 6 | AFTER | DELETE | Lưu thông tin hàng đã xóa |

Một bảng có thể có nhiều trigger trong từng nhóm. Ví dụ, có thể tạo ba BEFORE UPDATE trigger và hai AFTER UPDATE trigger cho cùng bảng.

Thứ tự chỉ được xác định giữa các trigger cùng nhóm. Một BEFORE UPDATE trigger không thể được đặt FOLLOWS một AFTER UPDATE trigger vì chúng thuộc hai thời điểm khác nhau. Tương tự, BEFORE INSERT và BEFORE UPDATE là hai nhóm riêng.

### 1.1. Trigger của MySQL luôn là FOR EACH ROW

MySQL chỉ hỗ trợ trigger mức hàng:

~~~sql
CREATE TRIGGER bu_orders_example
BEFORE UPDATE ON orders
FOR EACH ROW
SET NEW.updated_at = CURRENT_TIMESTAMP;
~~~

Nếu một câu UPDATE tác động đến 100 hàng, trigger được kích hoạt cho từng hàng bị tác động. Nếu có ba BEFORE UPDATE trigger trong nhóm, cả ba chạy theo thứ tự đã xác định cho mỗi hàng.

MySQL không hỗ trợ FOR EACH STATEMENT. Không nên thiết kế trigger như thể nó chỉ chạy một lần cho toàn bộ câu UPDATE.

### 1.2. BEFORE và AFTER có nhiệm vụ khác nhau

- BEFORE: chạy trước khi thao tác hàng được hoàn tất. Với INSERT và UPDATE, có thể gán giá trị cho NEW.column.
- AFTER: chạy sau khi thao tác hàng hoàn tất. Có thể đọc OLD và NEW nhưng không thể sửa NEW.

MySQL thực hiện các kiểm tra cơ bản về giá trị cột trước khi kích hoạt trigger. Vì vậy, không thể dựa vào BEFORE trigger để chuyển một giá trị đã sai kiểu hoặc không hợp lệ theo khai báo cột thành giá trị hợp lệ. Hãy bảo đảm dữ liệu đầu vào vượt qua kiểm tra kiểu và ràng buộc cơ bản trước khi trigger xử lý nghiệp vụ.

Các giá trị OLD/NEW phụ thuộc sự kiện:

| Sự kiện | OLD | NEW |
|---|---|---|
| INSERT | Không có | Hàng sắp được thêm |
| UPDATE | Hàng trước cập nhật | Hàng sau cập nhật |
| DELETE | Hàng sắp bị xóa | Không có |

OLD và NEW là từ khóa không phân biệt chữ hoa/chữ thường. Chúng chỉ truy cập hàng đang được trigger xử lý.

### 1.3. Nhiều trigger trong cùng nhóm chạy tuần tự

Với một hàng UPDATE, thứ tự tổng quát là:

~~~text
BEFORE UPDATE trigger 1
BEFORE UPDATE trigger 2
BEFORE UPDATE trigger 3
       |
       v
Thao tác cập nhật hàng
       |
       v
AFTER UPDATE trigger 1
AFTER UPDATE trigger 2
~~~

Đây là thứ tự khái niệm cho một hàng. Khi câu lệnh cập nhật nhiều hàng, quy trình được lặp lại cho từng hàng.

Không có một thứ tự chung để trộn BEFORE và AFTER vào cùng một danh sách. Tất cả BEFORE của hàng chạy trước thao tác hàng; sau đó các AFTER mới chạy.

## 2. Hỗ trợ nhiều trigger cùng thời điểm/sự kiện

Trước MySQL 5.7.2, mỗi bảng chỉ được có tối đa một trigger cho mỗi tổ hợp thời điểm và sự kiện. Ví dụ, một bảng chỉ có thể có một BEFORE UPDATE trigger.

Từ MySQL 5.7.2, giới hạn này được gỡ bỏ. Một bảng có thể có nhiều trigger cùng nhóm và có thể điều khiển thứ tự bằng FOLLOWS/PRECEDES.

| Phiên bản | Nhiều trigger cùng nhóm | FOLLOWS/PRECEDES | ACTION_ORDER |
|---|---|---|---|
| Trước MySQL 5.7.2 | Không | Không | Chưa có thứ tự nhiều trigger |
| MySQL 5.7.2 trở lên | Có | Có | Có trong INFORMATION_SCHEMA.TRIGGERS |
| MySQL 8.0 | Có | Có | Có |
| MySQL 8.4 | Có | Có | Có |

Nếu phải hỗ trợ server cũ hơn 5.7.2, cần gộp logic vào một trigger cho mỗi nhóm hoặc nâng cấp server. Không nên triển khai nhiều trigger cùng nhóm trên source rồi kỳ vọng replica cũ xử lý giống nhau.

### 2.1. Tên trigger có phạm vi schema

Tên trigger phải duy nhất trong schema chứa trigger. Hai bảng khác nhau trong cùng schema không thể có hai trigger trùng tên. Hai schema khác nhau có thể dùng cùng tên trigger.

Vì vậy, nên đặt tên thể hiện bảng, sự kiện và trách nhiệm:

- bu_orders_10_normalize
- bu_orders_30_validate
- bu_orders_40_stamp
- au_orders_10_audit

Tiền tố bu có thể được hiểu là BEFORE UPDATE, au là AFTER UPDATE. Phần số giúp người đọc nhận ra thứ tự dự kiến, nhưng tên số không điều khiển thứ tự thực tế. Thứ tự thực tế do creation order hoặc FOLLOWS/PRECEDES quyết định.

## 3. Thứ tự mặc định khi tạo nhiều trigger

Nếu không ghi FOLLOWS hoặc PRECEDES, trigger mới được đặt sau các trigger đã tồn tại có cùng bảng, thời điểm và sự kiện.

Ví dụ:

~~~sql
CREATE TRIGGER bu_orders_first
BEFORE UPDATE ON orders
FOR EACH ROW
SET NEW.status = UPPER(NEW.status);

CREATE TRIGGER bu_orders_second
BEFORE UPDATE ON orders
FOR EACH ROW
SET NEW.updated_at = CURRENT_TIMESTAMP;
~~~

Nếu bu_orders_first được tạo trước bu_orders_second, thứ tự mặc định của hai trigger là:

1. bu_orders_first
2. bu_orders_second

Đây là thứ tự theo thời điểm tạo, không phải thứ tự từ tên trigger, thứ tự alphabet hoặc thứ tự file migration.

Nếu trigger bị DROP rồi tạo lại, thứ tự mặc định có thể thay đổi vì trigger vừa tạo trở thành trigger mới nhất trong nhóm. Do đó, với logic có phụ thuộc dữ liệu giữa các trigger, hãy dùng FOLLOWS/PRECEDES để thể hiện quan hệ thứ tự ngay trong DDL.

### 3.1. Cú pháp CREATE TRIGGER và vị trí trigger_order

Cú pháp tổng quát:

~~~sql
CREATE
    [DEFINER = user]
    TRIGGER trigger_name
    { BEFORE | AFTER } { INSERT | UPDATE | DELETE }
    ON table_name
    FOR EACH ROW
    [ FOLLOWS other_trigger_name | PRECEDES other_trigger_name ]
    trigger_body;
~~~

Trong đó:

- trigger_name: tên trigger mới, duy nhất trong schema.
- BEFORE hoặc AFTER: thời điểm kích hoạt.
- INSERT, UPDATE, DELETE: sự kiện.
- table_name: bảng permanent được gắn trigger.
- FOLLOWS hoặc PRECEDES: tùy chọn xác định thứ tự tương đối.
- trigger_body: một câu lệnh hoặc khối BEGIN ... END.

FOLLOWS/PRECEDES nằm ngay sau FOR EACH ROW. Trigger không thể gắn vào view hoặc TEMPORARY table.

## 4. FOLLOWS: đặt trigger mới sau trigger hiện có

FOLLOWS làm trigger mới kích hoạt sau trigger được chỉ định. Trigger được tham chiếu phải tồn tại và phải có cùng bảng, cùng thời điểm, cùng sự kiện.

Cú pháp:

~~~sql
CREATE TRIGGER new_trigger
BEFORE UPDATE ON orders
FOR EACH ROW
FOLLOWS existing_trigger
trigger_body;
~~~

Ví dụ:

~~~sql
CREATE TRIGGER bu_orders_validate
BEFORE UPDATE ON orders
FOR EACH ROW
FOLLOWS bu_orders_normalize
BEGIN
    IF NEW.total_amount < 0 THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'total_amount cannot be negative';
    END IF;
END;
~~~

Nếu bu_orders_normalize là BEFORE UPDATE trigger trên cùng bảng orders, trigger validate được đặt sau nó.

Điều này có ý nghĩa nếu trigger normalize thay đổi NEW.status hoặc NEW.total_amount. Trigger validate sẽ kiểm tra các giá trị sau khi trigger normalize đã chạy.

### 4.1. FOLLOWS không có nghĩa là gọi trigger khác

FOLLOWS chỉ xác định thứ tự kích hoạt trong server. Nó không gọi trigger như gọi stored procedure, không truyền tham số và không tạo một lời gọi lồng nhau.

Khi câu UPDATE tác động đến một hàng, MySQL tự kích hoạt toàn bộ trigger trong nhóm theo thứ tự. Mỗi trigger vẫn là một database object riêng với body riêng.

### 4.2. Trigger được tham chiếu phải cùng nhóm

Ví dụ sau không hợp lệ nếu au_orders_audit là AFTER UPDATE trigger:

~~~sql
CREATE TRIGGER bu_orders_validate
BEFORE UPDATE ON orders
FOR EACH ROW
FOLLOWS au_orders_audit
BEGIN
    IF NEW.total_amount < 0 THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'Invalid amount';
    END IF;
END;
~~~

Lý do: trigger mới là BEFORE UPDATE, còn trigger được tham chiếu là AFTER UPDATE. Hai trigger không cùng action time nên không thể thiết lập quan hệ FOLLOWS.

Tương tự, không thể tham chiếu BEFORE INSERT trigger khi đang tạo BEFORE UPDATE trigger, dù chúng cùng bảng.

## 5. PRECEDES: đặt trigger mới trước trigger hiện có

PRECEDES làm trigger mới kích hoạt trước trigger được chỉ định.

Ví dụ:

~~~sql
CREATE TRIGGER bu_orders_default_status
BEFORE UPDATE ON orders
FOR EACH ROW
PRECEDES bu_orders_validate
BEGIN
    IF TRIM(NEW.status) = '' THEN
        SET NEW.status = 'NEW';
    END IF;
END;
~~~

Nếu bu_orders_validate là BEFORE UPDATE trigger trên cùng bảng, trigger default status sẽ chạy trước validate.

PRECEDES phù hợp khi muốn thêm một bước chuẩn bị dữ liệu vào trước trigger kiểm tra hoặc trước trigger thực hiện hành động phụ thuộc.

### 5.1. Chỉ định một trigger làm mốc

Một trigger mới chỉ có một trigger_order clause: FOLLOWS hoặc PRECEDES, không thể ghi đồng thời cả hai.

Ví dụ không hợp lệ:

~~~sql
CREATE TRIGGER bu_orders_default
BEFORE UPDATE ON orders
FOR EACH ROW
FOLLOWS bu_orders_normalize
PRECEDES bu_orders_validate
SET NEW.status = 'NEW';
~~~

Nếu cần kiểm soát chuỗi dài, hãy tạo các trigger theo thứ tự rõ ràng và liên kết từng trigger với một trigger mốc. Sau khi tạo, kiểm tra ACTION_ORDER để xác nhận kết quả thực tế.

### 5.2. FOLLOWS/PRECEDES không thay đổi event hoặc timing

FOLLOWS/PRECEDES chỉ sắp xếp thứ tự trong cùng nhóm. Chúng không thể:

- Đưa BEFORE trigger chạy sau thao tác ghi hàng.
- Đưa AFTER trigger chạy trước thao tác ghi hàng.
- Đưa INSERT trigger vào giữa các UPDATE trigger.
- Thay đổi bảng mà trigger được gắn vào.

Nếu cần logic chạy sau khi UPDATE hoàn tất, hãy tạo AFTER UPDATE trigger. Không thể dùng FOLLOWS để biến BEFORE thành AFTER.

## 6. Thay đổi NEW qua chuỗi BEFORE trigger

Một lý do quan trọng để xác định thứ tự là các BEFORE trigger có thể cùng đọc và sửa giá trị NEW.

Ví dụ chuỗi xử lý:

1. Trigger mặc định gán NEW.status = 'NEW' nếu trạng thái rỗng.
2. Trigger chuẩn hóa chuyển trạng thái thành chữ hoa và bỏ khoảng trắng.
3. Trigger kiểm tra xác nhận trạng thái thuộc tập cho phép.
4. Trigger đóng dấu NEW.updated_at.

Trigger sau nhìn thấy giá trị NEW đã được trigger BEFORE chạy trước đó thay đổi. Do đó, thứ tự có thể làm thay đổi kết quả nghiệp vụ.

Ví dụ:

~~~sql
CREATE TRIGGER bu_orders_normalize
BEFORE UPDATE ON orders
FOR EACH ROW
SET NEW.status = UPPER(TRIM(NEW.status));

CREATE TRIGGER bu_orders_validate
BEFORE UPDATE ON orders
FOR EACH ROW
FOLLOWS bu_orders_normalize
BEGIN
    IF NEW.status NOT IN ('NEW', 'PAID', 'CANCELLED') THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'Unsupported order status';
    END IF;
END;
~~~

Khi cập nhật status thành ' paid ', trigger normalize đổi thành PAID. Trigger validate sau đó kiểm tra PAID, không phải chuỗi đầu vào ban đầu.

Nếu đảo thứ tự, validate có thể từ chối chuỗi ' paid ' trước khi normalize có cơ hội sửa nó.

### 6.1. AFTER trigger đọc kết quả cuối cùng

AFTER trigger không thể sửa NEW. Nó có thể đọc OLD và NEW để ghi audit hoặc cập nhật bảng khác.

Ví dụ:

~~~sql
CREATE TRIGGER au_orders_audit
AFTER UPDATE ON orders
FOR EACH ROW
INSERT INTO order_audit (
    order_id,
    old_status,
    new_status,
    changed_at
)
VALUES (
    OLD.order_id,
    OLD.status,
    NEW.status,
    CURRENT_TIMESTAMP
);
~~~

Nếu có nhiều AFTER UPDATE trigger, chúng cũng có thứ tự riêng. Thứ tự của chúng không bị trộn với các BEFORE UPDATE trigger.

## 7. Lab: chuẩn hóa, mặc định, kiểm tra và ghi audit

Lab tạo bốn BEFORE UPDATE trigger có thứ tự rõ ràng và một AFTER UPDATE trigger ghi audit. Các trigger BEFORE minh họa cả FOLLOWS và PRECEDES.

### 7.1. Tạo bảng

~~~sql
CREATE TABLE orders_trigger_demo (
    order_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    status VARCHAR(20) NOT NULL,
    total_amount DECIMAL(12, 2) NOT NULL,
    updated_at DATETIME NULL,
    PRIMARY KEY (order_id)
) ENGINE = InnoDB;

CREATE TABLE orders_trigger_audit_demo (
    audit_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    order_id BIGINT UNSIGNED NOT NULL,
    old_status VARCHAR(20) NOT NULL,
    new_status VARCHAR(20) NOT NULL,
    old_amount DECIMAL(12, 2) NOT NULL,
    new_amount DECIMAL(12, 2) NOT NULL,
    changed_at DATETIME NOT NULL,
    PRIMARY KEY (audit_id),
    KEY idx_audit_order (order_id)
) ENGINE = InnoDB;

INSERT INTO orders_trigger_demo (
    status, total_amount
)
VALUES ('new', 100.00);
~~~

### 7.2. Tạo trigger chuẩn hóa đầu tiên

Trigger này được tạo đầu tiên trong nhóm BEFORE UPDATE:

Lệnh DELIMITER là lệnh của mysql command-line client để đổi ký tự kết thúc câu lệnh khi gửi định nghĩa trigger có nhiều dấu chấm phẩy. Đây không phải câu SQL gửi tới server; nếu dùng một công cụ client khác, hãy dùng cơ chế delimiter tương ứng của công cụ đó.

~~~sql
DELIMITER $$

CREATE TRIGGER bu_orders_10_normalize
BEFORE UPDATE ON orders_trigger_demo
FOR EACH ROW
SET NEW.status = UPPER(TRIM(NEW.status))$$

DELIMITER ;
~~~

### 7.3. Tạo trigger kiểm tra bằng FOLLOWS

Trigger validate phải chạy sau normalize:

~~~sql
DELIMITER $$

CREATE TRIGGER bu_orders_30_validate
BEFORE UPDATE ON orders_trigger_demo
FOR EACH ROW
FOLLOWS bu_orders_10_normalize
BEGIN
    IF NEW.total_amount < 0 THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'total_amount cannot be negative';
    END IF;

    IF NEW.status NOT IN ('NEW', 'PAID', 'CANCELLED') THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'Unsupported order status';
    END IF;
END$$

DELIMITER ;
~~~

### 7.4. Tạo trigger đóng dấu thời gian

Trigger này chạy sau validate:

~~~sql
DELIMITER $$

CREATE TRIGGER bu_orders_40_stamp
BEFORE UPDATE ON orders_trigger_demo
FOR EACH ROW
FOLLOWS bu_orders_30_validate
SET NEW.updated_at = CURRENT_TIMESTAMP$$

DELIMITER ;
~~~

### 7.5. Tạo trigger mặc định bằng PRECEDES

Trigger này được tạo sau cùng nhưng đặt trước normalize:

~~~sql
DELIMITER $$

CREATE TRIGGER bu_orders_00_default
BEFORE UPDATE ON orders_trigger_demo
FOR EACH ROW
PRECEDES bu_orders_10_normalize
BEGIN
    IF TRIM(NEW.status) = '' THEN
        SET NEW.status = 'NEW';
    END IF;
END$$

DELIMITER ;
~~~

Thứ tự mong đợi trong nhóm BEFORE UPDATE:

| ACTION_ORDER | Trigger | Nhiệm vụ |
|---:|---|---|
| 1 | bu_orders_00_default | Gán NEW nếu status rỗng |
| 2 | bu_orders_10_normalize | Bỏ khoảng trắng và viết hoa |
| 3 | bu_orders_30_validate | Kiểm tra trạng thái và số tiền |
| 4 | bu_orders_40_stamp | Gán updated_at |

Mặc dù trigger default được tạo cuối cùng, PRECEDES đặt nó trước trigger normalize. FOLLOWS tạo quan hệ normalize → validate → stamp.

### 7.6. Tạo AFTER UPDATE trigger để ghi audit

~~~sql
DELIMITER $$

CREATE TRIGGER au_orders_10_audit
AFTER UPDATE ON orders_trigger_demo
FOR EACH ROW
INSERT INTO orders_trigger_audit_demo (
    order_id,
    old_status,
    new_status,
    old_amount,
    new_amount,
    changed_at
)
VALUES (
    OLD.order_id,
    OLD.status,
    NEW.status,
    OLD.total_amount,
    NEW.total_amount,
    CURRENT_TIMESTAMP
)$$

DELIMITER ;
~~~

Trigger audit thuộc nhóm AFTER UPDATE, độc lập với nhóm BEFORE UPDATE. Nó đọc kết quả sau khi các BEFORE trigger đã xử lý NEW và thao tác UPDATE thành công.

### 7.7. Kiểm tra thứ tự trong metadata

~~~sql
SELECT
    TRIGGER_NAME,
    EVENT_MANIPULATION,
    ACTION_TIMING,
    ACTION_ORDER
FROM INFORMATION_SCHEMA.TRIGGERS
WHERE TRIGGER_SCHEMA = DATABASE()
  AND EVENT_OBJECT_TABLE = 'orders_trigger_demo'
ORDER BY
    EVENT_MANIPULATION,
    ACTION_TIMING,
    ACTION_ORDER;
~~~

ACTION_ORDER là vị trí thực thi của trigger trong danh sách trigger cùng bảng, cùng EVENT_MANIPULATION và cùng ACTION_TIMING. Không so sánh ACTION_ORDER giữa BEFORE UPDATE và AFTER UPDATE như thể chúng thuộc một danh sách chung.

Có thể xem định nghĩa trigger:

~~~sql
SHOW CREATE TRIGGER bu_orders_30_validate;
SHOW CREATE TRIGGER bu_orders_00_default;
~~~

SHOW CREATE TRIGGER giúp kiểm tra trigger body và phần khai báo FOLLOWS/PRECEDES.

### 7.8. Thử cập nhật giá trị cần chuẩn hóa

~~~sql
UPDATE orders_trigger_demo
SET status = ' paid ',
    total_amount = 150.00
WHERE order_id = 1;

SELECT *
FROM orders_trigger_demo
WHERE order_id = 1;

SELECT *
FROM orders_trigger_audit_demo
WHERE order_id = 1
ORDER BY audit_id;
~~~

Kết quả mong đợi:

- Trigger default không thay đổi status vì giá trị không rỗng.
- Trigger normalize đổi ' paid ' thành PAID.
- Trigger validate chấp nhận trạng thái và số tiền.
- Trigger stamp gán updated_at.
- AFTER trigger ghi audit với OLD.status là new và NEW.status là PAID.

### 7.9. Thử PRECEDES với trạng thái rỗng

~~~sql
UPDATE orders_trigger_demo
SET status = '   '
WHERE order_id = 1;

SELECT order_id, status, updated_at
FROM orders_trigger_demo
WHERE order_id = 1;
~~~

Trigger default chạy trước normalize, đổi chuỗi rỗng thành NEW. Trigger normalize tiếp tục chuẩn hóa thành NEW, validate chấp nhận, stamp cập nhật thời gian.

### 7.10. Thử lỗi validation

~~~sql
UPDATE orders_trigger_demo
SET total_amount = -1.00
WHERE order_id = 1;
~~~

Câu UPDATE bị từ chối với SQLSTATE 45000. Các trigger sau trigger validate trong nhóm BEFORE UPDATE không chạy cho lần cập nhật đó; thao tác hàng không hoàn tất và AFTER UPDATE audit không được kích hoạt.

Với InnoDB, thay đổi của statement bị lỗi được rollback theo quy tắc transaction của engine. Không nên giả định hành vi rollback tương tự cho bảng dùng storage engine không hỗ trợ transaction.

## 8. Kiểm tra và quản lý trigger

### 8.1. Liệt kê trigger trong schema

~~~sql
SHOW TRIGGERS;
~~~

SHOW TRIGGERS hữu ích để xem danh sách trigger, sự kiện, thời điểm, bảng, định nghĩa và definer. Mệnh đề LIKE của SHOW TRIGGERS lọc theo tên trigger, không phải tên bảng được gắn trigger. Để lọc theo bảng và kiểm tra thứ tự, dùng truy vấn INFORMATION_SCHEMA.TRIGGERS ở phần tiếp theo.

### 8.2. Xem thứ tự và định nghĩa bằng INFORMATION_SCHEMA

~~~sql
SELECT
    TRIGGER_NAME,
    EVENT_OBJECT_TABLE,
    EVENT_MANIPULATION,
    ACTION_TIMING,
    ACTION_ORDER,
    ACTION_STATEMENT
FROM INFORMATION_SCHEMA.TRIGGERS
WHERE TRIGGER_SCHEMA = DATABASE()
ORDER BY
    EVENT_OBJECT_TABLE,
    EVENT_MANIPULATION,
    ACTION_TIMING,
    ACTION_ORDER;
~~~

Các cột quan trọng:

- TRIGGER_NAME: tên trigger.
- EVENT_OBJECT_TABLE: bảng gắn trigger.
- EVENT_MANIPULATION: INSERT, UPDATE hoặc DELETE.
- ACTION_TIMING: BEFORE hoặc AFTER.
- ACTION_ORDER: vị trí trong nhóm trigger cùng event và timing.
- ACTION_STATEMENT: nội dung trigger body.

Cần quyền phù hợp để xem metadata của schema. Không dùng ACTION_ORDER đơn lẻ mà bỏ qua bảng, event và timing.

### 8.3. Xóa trigger

~~~sql
DROP TRIGGER IF EXISTS bu_orders_30_validate;
~~~

Nếu trigger không thuộc database mặc định, chỉ rõ schema:

~~~sql
DROP TRIGGER IF EXISTS app_db.bu_orders_30_validate;
~~~

DROP TRIGGER chỉ xóa trigger được chỉ định. Nó không xóa bảng gắn trigger.

Nếu xóa bảng, các trigger gắn với bảng đó cũng bị xóa.

### 8.4. Thay đổi thứ tự trigger hiện có

FOLLOWS/PRECEDES được chỉ định khi CREATE TRIGGER. Không dùng ALTER TRIGGER để đổi thứ tự kích hoạt.

Nếu cần thay đổi quan hệ thứ tự của trigger hiện có, hãy lập kế hoạch DROP và CREATE lại trigger với trigger_order phù hợp. Vì thao tác này có thể tạo khoảng thời gian trigger chưa tồn tại, hãy triển khai trong migration có kiểm soát và xác minh ACTION_ORDER sau khi hoàn tất.

Khi một trigger được DROP, những trigger còn lại trong nhóm vẫn là các trigger độc lập. Không dựa vào thứ tự cũ sau khi thay đổi tập trigger; luôn kiểm tra metadata và tạo lại các quan hệ FOLLOWS/PRECEDES cần thiết.

## 9. Lỗi thường gặp khi dùng nhiều trigger

| Lỗi hoặc hiểu nhầm | Thực tế | Cách xử lý |
|---|---|---|
| Một bảng chỉ có một BEFORE UPDATE trigger | Từ MySQL 5.7.2 có thể có nhiều trigger cùng nhóm | Kiểm tra phiên bản server |
| Trigger mới luôn chạy đầu tiên | Mặc định trigger mới chạy sau trigger cùng nhóm đã có | Dùng PRECEDES nếu cần chạy trước |
| Tên trigger quyết định thứ tự | Tên không điều khiển thứ tự | Dùng FOLLOWS/PRECEDES và kiểm tra ACTION_ORDER |
| FOLLOWS có thể tham chiếu bất kỳ trigger nào | Trigger được tham chiếu phải cùng bảng, event và timing | Kiểm tra nhóm trước khi tạo |
| PRECEDES thay đổi timing | Nó chỉ đổi thứ tự trong cùng nhóm | Tạo đúng BEFORE/AFTER ngay từ đầu |
| BEFORE và AFTER nằm trong cùng danh sách | Hai thời điểm là hai nhóm độc lập | Kiểm tra ACTION_TIMING |
| AFTER trigger sửa được NEW | NEW chỉ đọc trong AFTER | Chuyển logic sửa giá trị sang BEFORE |
| Trigger sau không nhìn thấy thay đổi NEW trước đó | Các BEFORE trigger sau nhìn thấy giá trị NEW đã được trigger trước sửa | Xác định thứ tự rõ ràng |
| Thứ tự theo số trong tên | Tên như _10_ hoặc _20_ chỉ là quy ước | Không thay thế FOLLOWS/PRECEDES |
| ACTION_ORDER là thứ tự toàn schema | ACTION_ORDER có ý nghĩa trong cùng bảng, event và timing | ORDER BY đủ các cột nhóm |
| Có thể dùng FOLLOWS và PRECEDES cùng lúc | Một trigger chỉ có một trigger_order clause | Thiết kế một quan hệ mốc cho mỗi trigger |
| DROP rồi CREATE không ảnh hưởng thứ tự | Trigger mới có thể trở thành phần tử mới trong nhóm | Khai báo lại thứ tự và xác minh |
| Trigger lỗi nhưng statement vẫn tiếp tục | Lỗi trigger làm statement thất bại | Dùng SIGNAL có chủ đích và kiểm thử transaction |
| Foreign key cascade kích hoạt trigger | Cascaded foreign key actions không kích hoạt trigger | Đặt logic cần thiết ở nơi phù hợp khác |
| Trigger trên TEMPORARY table | MySQL không hỗ trợ trigger cho TEMPORARY table hoặc view | Gắn trigger vào permanent table |
| Replication luôn chạy trigger giống source | Statement-based và row-based replication xử lý trigger khác nhau | Kiểm tra binlog format và topology |

## 10. Lưu ý về sự kiện và replication

### 10.1. INSERT ... ON DUPLICATE KEY UPDATE

Câu lệnh INSERT ... ON DUPLICATE KEY UPDATE có thể kích hoạt chuỗi trigger khác nhau tùy hàng mới có xung đột khóa hay không.

Với một hàng, BEFORE INSERT được kích hoạt trước. Nếu xảy ra duplicate key, nhánh UPDATE tiếp tục kích hoạt BEFORE UPDATE và AFTER UPDATE; nếu không có duplicate, nhánh INSERT kết thúc với AFTER INSERT.

Vì vậy, khi một bảng có cả INSERT và UPDATE trigger, hãy kiểm thử riêng cả hai nhánh của câu lệnh này. Không suy luận rằng một câu INSERT chỉ kích hoạt trigger INSERT trong mọi trường hợp.

### 10.2. Foreign key cascade

Các hành động cascade của foreign key không kích hoạt trigger. Ví dụ, nếu ON DELETE CASCADE xóa hàng con do xóa hàng cha, DELETE trigger trên bảng con không được kích hoạt bởi thao tác cascade đó.

Nếu cần audit cả các thay đổi do cascade, hãy thiết kế cơ chế audit ở tầng nghiệp vụ hoặc mô hình dữ liệu phù hợp; không giả định trigger trên bảng con sẽ nhận mọi thao tác xóa.

### 10.3. Statement-based và row-based replication

Cách trigger hoạt động trên replica phụ thuộc binlog format:

- Statement-based replication: câu lệnh được thực thi trên replica và trigger của replica được kích hoạt bởi câu lệnh đó.
- Row-based replication: trigger không chạy lại trên replica cho các thay đổi hàng được replicate; thay đổi do trigger tạo ra trên source được ghi thành row events và áp dụng trên replica.

Khi triển khai nhiều trigger trong topology replication, mọi server cần có schema và trigger definition tương thích. Không nâng cấp source trước replica nếu replica còn dùng phiên bản không hỗ trợ nhiều trigger cùng nhóm.

## 11. Quy trình thiết kế và triển khai thứ tự trigger

Khi một bảng có nhiều trigger cùng thời điểm và sự kiện:

1. Liệt kê các trách nhiệm: chuẩn hóa, mặc định, kiểm tra, đóng dấu thời gian, audit.
2. Phân loại từng trách nhiệm vào BEFORE hoặc AFTER và INSERT/UPDATE/DELETE.
3. Đưa các thao tác cần sửa NEW vào BEFORE.
4. Xác định quan hệ phụ thuộc dữ liệu giữa các BEFORE trigger.
5. Chọn một trigger mốc và khai báo FOLLOWS/PRECEDES cho trigger phụ thuộc.
6. Dùng AFTER cho audit hoặc thao tác cần đọc hàng đã được ghi.
7. Kiểm tra thứ tự trong INFORMATION_SCHEMA.TRIGGERS bằng ACTION_ORDER.
8. Kiểm thử nhiều hàng, giá trị rỗng, giá trị hợp lệ và giá trị gây SIGNAL.
9. Kiểm tra lỗi của một trigger có ngăn trigger sau chạy hay không.
10. Kiểm tra transaction behavior của storage engine.
11. Kiểm tra trigger definition và thứ tự sau migration.
12. Xác minh binlog format và khả năng tương thích của replica.
13. Ghi lại trách nhiệm của từng trigger để người vận hành hiểu vì sao thứ tự tồn tại.

Sơ đồ triển khai:

~~~mermaid
flowchart TD
    A[Phân tích nghiệp vụ] --> B[Chia nhóm BEFORE/AFTER và INSERT/UPDATE/DELETE]
    B --> C[Liệt kê trigger cùng nhóm]
    C --> D[Xác định phụ thuộc giữa các trigger]
    D --> E[Chọn FOLLOWS/PRECEDES]
    E --> F[Tạo trigger]
    F --> G[Đọc INFORMATION_SCHEMA.TRIGGERS]
    G --> H{ACTION_ORDER đúng?}
    H -->|Không| I[Điều chỉnh migration]
    I --> F
    H -->|Có| J[Kiểm thử DML và lỗi]
    J --> K[Kiểm tra audit, transaction và replication]
    K --> L[Triển khai có kiểm soát]
~~~

## 12. Bài tập thực hành

### Bài 1: Nhiều BEFORE UPDATE trigger

Tạo hai BEFORE UPDATE trigger trên một bảng. Trigger đầu chuẩn hóa status, trigger thứ hai kiểm tra status. Chứng minh trigger thứ hai nhìn thấy NEW.status sau chuẩn hóa.

### Bài 2: Thứ tự mặc định

Tạo ba trigger cùng nhóm theo thứ tự khác nhau. Truy vấn ACTION_ORDER và xác nhận thứ tự mặc định.

### Bài 3: FOLLOWS

Tạo một trigger mới với FOLLOWS trigger đã có. Kiểm tra ACTION_ORDER trước và sau khi tạo.

### Bài 4: PRECEDES

Tạo trigger mặc định status với PRECEDES trigger normalize. Thử cập nhật status thành chuỗi rỗng và quan sát kết quả.

### Bài 5: Tham chiếu sai nhóm

Thử dùng FOLLOWS để tham chiếu AFTER UPDATE trigger khi tạo BEFORE UPDATE trigger. Ghi lại lỗi và giải thích điều kiện cùng nhóm.

### Bài 6: BEFORE so với AFTER

Tạo một BEFORE UPDATE trigger thay đổi NEW và một AFTER UPDATE trigger ghi audit. So sánh giá trị NEW được ghi trong audit với giá trị ban đầu của câu UPDATE.

### Bài 7: ACTION_ORDER

Viết truy vấn INFORMATION_SCHEMA.TRIGGERS liệt kê trigger theo schema, table, event, timing và action order. Giải thích vì sao phải nhóm đủ các trường.

### Bài 8: Trigger lỗi

Tạo BEFORE UPDATE trigger dùng SIGNAL khi total_amount âm. Kiểm tra trigger sau không chạy và AFTER UPDATE audit không ghi hàng cho statement thất bại.

### Bài 9: Thay đổi thứ tự sau DROP/CREATE

DROP một trigger trong nhóm rồi tạo lại. Quan sát ACTION_ORDER và tạo lại quan hệ FOLLOWS/PRECEDES cần thiết.

### Bài 10: Kiểm tra replication

Dùng môi trường thử nghiệm có source và replica. So sánh trigger behavior với statement-based và row-based binlog format. Xác minh dữ liệu audit không bị ghi hai lần trên replica.

## Kết luận

MySQL cho phép nhiều trigger cùng bảng, cùng thời điểm và cùng sự kiện từ phiên bản 5.7.2. Khi không chỉ định thứ tự, trigger trong cùng nhóm chạy theo thứ tự tạo. FOLLOWS đặt trigger mới sau một trigger cùng nhóm; PRECEDES đặt trigger mới trước một trigger cùng nhóm.

Thứ tự rõ ràng đặc biệt quan trọng khi các BEFORE trigger cùng sửa NEW hoặc khi một trigger kiểm tra dữ liệu do trigger trước chuẩn hóa. AFTER trigger thuộc nhóm riêng và thường phù hợp để ghi audit sau thao tác hàng. Hãy dùng INFORMATION_SCHEMA.TRIGGERS và ACTION_ORDER để xác minh thứ tự thực tế, rồi kiểm thử cả dữ liệu hợp lệ lẫn đường lỗi trước khi triển khai.

## Tài liệu tham khảo

- MySQL 8.4 Reference Manual — Trigger Syntax and Examples: https://dev.mysql.com/doc/refman/8.4/en/trigger-syntax.html
- MySQL 8.4 Reference Manual — CREATE TRIGGER Statement: https://dev.mysql.com/doc/refman/8.4/en/create-trigger.html
- MySQL 8.4 Reference Manual — INFORMATION_SCHEMA TRIGGERS Table: https://dev.mysql.com/doc/refman/8.4/en/information-schema-triggers-table.html
- MySQL 8.4 Reference Manual — DROP TRIGGER Statement: https://dev.mysql.com/doc/refman/8.4/en/drop-trigger.html
- MySQL 8.4 Reference Manual — Replication and Triggers: https://dev.mysql.com/doc/refman/8.4/en/replication-features-triggers.html
- MySQL 5.7.2 Release Notes — Multiple Triggers for the Same Event and Action Time: https://dev.mysql.com/doc/relnotes/mysql/5.7/en/news-5-7-2.html

