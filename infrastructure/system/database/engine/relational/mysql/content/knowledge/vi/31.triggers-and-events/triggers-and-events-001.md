# BEFORE/AFTER trigger cho INSERT, UPDATE và DELETE

Trigger trong MySQL là stored program được database tự động gọi khi một sự kiện trên bảng xảy ra. Với bảng InnoDB, trigger có thể kiểm tra dữ liệu trước khi ghi, chuẩn hóa giá trị đầu vào hoặc ghi audit record sau khi một hàng được thêm, sửa hay xóa. Trigger chạy theo từng hàng (`FOR EACH ROW`), vì vậy một câu lệnh tác động 1.000 hàng có thể gọi trigger 1.000 lần.

MySQL hỗ trợ hai thời điểm `BEFORE` và `AFTER`, kết hợp với ba sự kiện `INSERT`, `UPDATE`, `DELETE`. Trong trigger, `NEW` đại diện cho giá trị hàng mới và `OLD` đại diện cho giá trị hàng trước thao tác. Với `BEFORE INSERT` và `BEFORE UPDATE`, có thể gán giá trị cho `NEW.column`; trigger `AFTER` chỉ đọc được các giá trị liên quan. `DELETE` chỉ có `OLD` vì sau thao tác không còn hàng mới.

Trigger phù hợp với quy tắc dữ liệu cần được áp dụng nhất quán bất kể client nào ghi vào bảng, ví dụ chuẩn hóa trường, kiểm tra chuyển trạng thái hoặc ghi audit trong cùng transaction. Trigger không phù hợp để gọi HTTP, gửi email, điều phối dịch vụ hay chứa quy trình nghiệp vụ dài khó quan sát.

## 1. Trigger là gì?

Trigger là đối tượng schema gắn với một bảng và được MySQL tự động kích hoạt khi bảng nhận thao tác thuộc loại đã khai báo. Ứng dụng không gọi trigger bằng `CALL`; ứng dụng thực hiện `INSERT`, `UPDATE` hoặc `DELETE`, rồi trigger chạy theo định nghĩa.

Các đặc điểm chính:

- Trigger gắn với một bảng cơ sở.
- Trigger chạy theo từng hàng; MySQL không có statement-level trigger.
- Mỗi trigger có một event (`INSERT`, `UPDATE`, `DELETE`) và một timing (`BEFORE`, `AFTER`).
- Trigger dùng `OLD`/`NEW` để truy cập giá trị của hàng.
- Trigger chạy trong ngữ cảnh câu lệnh kích hoạt và cùng transaction nếu các bảng dùng engine transactional như InnoDB.
- Trigger không tạo transaction độc lập và không được tự `COMMIT`/`ROLLBACK`.

Từ MySQL 5.7.2, một bảng có thể có nhiều trigger cùng timing/event. Nếu không chỉ định thứ tự, chúng chạy theo thứ tự tạo; có thể dùng `FOLLOWS` hoặc `PRECEDES` để quy định thứ tự tương đối.

## 2. Sáu tổ hợp BEFORE/AFTER và INSERT/UPDATE/DELETE

| Trigger | Thời điểm | Có thể đọc | Có thể gán |
| --- | --- | --- | --- |
| `BEFORE INSERT` | Trước khi thêm từng hàng | `NEW` | `NEW.column` |
| `AFTER INSERT` | Sau khi thêm từng hàng | `NEW` | Không được sửa `NEW` |
| `BEFORE UPDATE` | Trước khi cập nhật từng hàng | `OLD`, `NEW` | `NEW.column` |
| `AFTER UPDATE` | Sau khi cập nhật từng hàng | `OLD`, `NEW` | Không được sửa `NEW` |
| `BEFORE DELETE` | Trước khi xóa từng hàng | `OLD` | Không có `NEW` |
| `AFTER DELETE` | Sau khi xóa từng hàng | `OLD` | Không có `NEW` |

`OLD` luôn là ảnh hàng trước thao tác; `NEW` là ảnh hàng mới đối với INSERT/UPDATE. Không dùng `OLD` trong trigger INSERT hoặc `NEW` trong trigger DELETE.

## 3. Cú pháp CREATE TRIGGER

Cú pháp tổng quát:

```sql
CREATE
    [DEFINER = user]
    TRIGGER trigger_name
    trigger_time trigger_event
    ON tbl_name
    FOR EACH ROW
    [FOLLOWS other_trigger | PRECEDES other_trigger]
    trigger_body;
```

`trigger_time` là `BEFORE` hoặc `AFTER`; `trigger_event` là `INSERT`, `UPDATE` hoặc `DELETE`; `trigger_body` là một câu lệnh hoặc compound statement `BEGIN ... END`.

Ví dụ tối giản:

```sql
CREATE TRIGGER bi_customers_set_created_at
BEFORE INSERT ON customers
FOR EACH ROW
SET NEW.created_at = COALESCE(NEW.created_at, CURRENT_TIMESTAMP);
```

Khi tạo trigger bằng MySQL command-line client, thường cần đổi `DELIMITER` vì phần thân có thể chứa dấu chấm phẩy. `DELIMITER` là lệnh của client, không phải câu SQL gửi đến server; migration framework/JDBC thường cần gửi nguyên câu `CREATE TRIGGER` theo cơ chế riêng của công cụ.

## 4. Chuẩn bị bảng minh họa

Ví dụ dùng bảng khách hàng và bảng audit. Audit table không có foreign key đến `customers`, để lịch sử vẫn tồn tại sau khi khách hàng bị xóa:

```sql
CREATE TABLE customers (
    customer_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    email VARCHAR(255) NOT NULL,
    display_name VARCHAR(150) NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'pending',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (customer_id),
    UNIQUE KEY uq_customers_email (email)
) ENGINE=InnoDB DEFAULT CHARACTER SET utf8mb4;

CREATE TABLE customer_audit (
    audit_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    customer_id BIGINT UNSIGNED NOT NULL,
    operation VARCHAR(10) NOT NULL,
    old_status VARCHAR(20) NULL,
    new_status VARCHAR(20) NULL,
    changed_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    PRIMARY KEY (audit_id),
    KEY idx_customer_audit_customer_time (customer_id, changed_at)
) ENGINE=InnoDB;
```

Trong hệ thống thật, audit có thể cần actor, request ID, source service hoặc snapshot các trường thay đổi. Chỉ lưu danh tính từ session variable nếu ứng dụng thiết lập nó qua connection đáng tin cậy và không cho caller tùy ý giả mạo.

## 5. BEFORE INSERT: chuẩn hóa và kiểm tra giá trị mới

`BEFORE INSERT` chạy trước khi hàng mới được ghi. Đây là nơi phù hợp để chuẩn hóa giá trị đầu vào và từ chối dữ liệu không hợp lệ:

```sql
DELIMITER //

CREATE TRIGGER bi_customers_normalize
BEFORE INSERT ON customers
FOR EACH ROW
BEGIN
    SET NEW.email = LOWER(TRIM(NEW.email));
    SET NEW.display_name = TRIM(NEW.display_name);

    IF NEW.email = '' THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'Email must not be empty';
    END IF;

    IF NEW.status NOT IN ('pending', 'active', 'suspended') THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'Invalid customer status';
    END IF;
END//

DELIMITER ;
```

`NEW` là hàng đang chuẩn bị insert, vì vậy trigger có thể gán `NEW.email` và `NEW.display_name`. Nếu điều kiện không hợp lệ, `SIGNAL` phát lỗi và câu INSERT thất bại.

Không kiểm tra trùng email bằng một `SELECT` trước khi insert: giữa bước kiểm tra và ghi có thể xảy ra race condition. Dùng `UNIQUE KEY` để database bảo đảm tính duy nhất; trigger chỉ nên xử lý quy tắc mà constraint không thể diễn đạt.

## 6. AFTER INSERT: ghi audit sau khi thêm hàng

`AFTER INSERT` chạy sau khi hàng mới được thêm vào bảng nền. Có thể ghi audit record dùng giá trị `NEW`:

```sql
DELIMITER //

CREATE TRIGGER ai_customers_audit
AFTER INSERT ON customers
FOR EACH ROW
BEGIN
    INSERT INTO customer_audit (
        customer_id, operation, old_status, new_status
    )
    VALUES (
        NEW.customer_id, 'INSERT', NULL, NEW.status
    );
END//

DELIMITER ;
```

Trigger có thể đọc `NEW.customer_id` sau khi MySQL đã gán giá trị `AUTO_INCREMENT`. Audit row được ghi trong cùng transaction InnoDB với INSERT gốc. Nếu insert audit thất bại, câu INSERT gốc cũng thất bại; hai thay đổi không được commit tách rời.

## 7. BEFORE UPDATE: kiểm tra thay đổi và chuẩn hóa NEW

`BEFORE UPDATE` có cả ảnh cũ `OLD` và ảnh mới dự kiến `NEW`. Có thể so sánh trạng thái, từ chối chuyển trạng thái không hợp lệ hoặc đặt timestamp:

```sql
DELIMITER //

CREATE TRIGGER bu_customers_validate
BEFORE UPDATE ON customers
FOR EACH ROW
BEGIN
    SET NEW.email = LOWER(TRIM(NEW.email));
    SET NEW.display_name = TRIM(NEW.display_name);

    IF NEW.status NOT IN ('pending', 'active', 'suspended') THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'Invalid customer status';
    END IF;

    IF NOT (OLD.status <=> NEW.status)
       AND OLD.status = 'suspended'
       AND NEW.status = 'active' THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'Suspended customer cannot be reactivated here';
    END IF;

    SET NEW.updated_at = CURRENT_TIMESTAMP;
END//

DELIMITER ;
```

`<=>` là toán tử so sánh NULL-safe của MySQL. `NOT (OLD.status <=> NEW.status)` phát hiện khác biệt kể cả khi một giá trị là NULL. Trigger có thể thay đổi `NEW` trong BEFORE UPDATE; không gán vào `OLD` vì đó là ảnh hàng trước thao tác và chỉ đọc.

## 8. AFTER UPDATE: lưu giá trị cũ và mới

`AFTER UPDATE` có thể đọc cả `OLD` và `NEW`. Ví dụ chỉ ghi audit khi trạng thái thay đổi:

```sql
DELIMITER //

CREATE TRIGGER au_customers_audit
AFTER UPDATE ON customers
FOR EACH ROW
BEGIN
    IF NOT (OLD.status <=> NEW.status) THEN
        INSERT INTO customer_audit (
            customer_id, operation, old_status, new_status
        )
        VALUES (
            NEW.customer_id, 'UPDATE', OLD.status, NEW.status
        );
    END IF;
END//

DELIMITER ;
```

Không thể sửa `NEW.status` trong AFTER trigger. Nếu cần thay giá trị trước khi ghi, thực hiện trong BEFORE trigger. AFTER trigger phù hợp với side effect trong database như ghi audit hoặc outbox row.

Không dùng AFTER trigger để cập nhật lại chính bảng `customers` đang được câu UPDATE sử dụng; MySQL chặn trigger sửa bảng đã được statement kích hoạt sử dụng và có thể báo lỗi 1442.

## 9. BEFORE DELETE: từ chối xóa theo quy tắc dữ liệu

`BEFORE DELETE` chỉ có `OLD`. Có thể kiểm tra hàng hiện tại trước khi cho phép xóa:

```sql
DELIMITER //

CREATE TRIGGER bd_customers_protect_active
BEFORE DELETE ON customers
FOR EACH ROW
BEGIN
    IF OLD.status = 'active' THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'Active customer cannot be deleted';
    END IF;
END//

DELIMITER ;
```

Nếu trigger phát `SIGNAL`, thao tác DELETE cho hàng đó bị từ chối. Không có `NEW` trong DELETE trigger vì hàng bị xóa không có ảnh sau thao tác.

Với quy tắc quan hệ như “không xóa khách hàng còn đơn hàng”, foreign key `RESTRICT` thường phù hợp và rõ ràng hơn trigger tự đếm hàng. Dùng trigger khi điều kiện không thể biểu diễn bằng constraint hoặc cần hành vi bổ sung.

## 10. AFTER DELETE: lưu audit trước khi mất hàng

`AFTER DELETE` chạy sau khi hàng bị xóa khỏi bảng nền, nhưng vẫn đọc được giá trị cũ qua `OLD`:

```sql
DELIMITER //

CREATE TRIGGER ad_customers_audit
AFTER DELETE ON customers
FOR EACH ROW
BEGIN
    INSERT INTO customer_audit (
        customer_id, operation, old_status, new_status
    )
    VALUES (
        OLD.customer_id, 'DELETE', OLD.status, NULL
    );
END//

DELIMITER ;
```

Audit table không có foreign key đến `customers`, nên bản ghi lịch sử vẫn tồn tại sau khi customer bị xóa. Trigger chạy trong cùng transaction với DELETE gốc; nếu audit insert thất bại trên InnoDB, DELETE cũng không commit riêng lẻ.

## 11. NEW và OLD: quy tắc sử dụng

| Trigger | `OLD.column` | `NEW.column` | Ghi vào `NEW`? |
| --- | --- | --- | --- |
| BEFORE INSERT | Không hợp lệ | Giá trị sắp insert | Có |
| AFTER INSERT | Không hợp lệ | Giá trị đã insert | Không |
| BEFORE UPDATE | Giá trị trước update | Giá trị mới dự kiến | Có |
| AFTER UPDATE | Giá trị trước update | Giá trị sau update | Không |
| BEFORE DELETE | Giá trị sắp xóa | Không hợp lệ | Không |
| AFTER DELETE | Giá trị đã xóa | Không hợp lệ | Không |

`OLD`/`NEW` chỉ tham chiếu cột của hàng hiện tại. Muốn đọc hàng khác, dùng SELECT trong phạm vi trigger nếu không vướng các hạn chế của MySQL.

## 12. Trigger chạy theo từng hàng

Nếu một câu lệnh tác động 500 hàng, trigger tương ứng có thể chạy 500 lần:

```sql
UPDATE customers
SET status = 'suspended'
WHERE status = 'pending';
```

Với 500 hàng thỏa điều kiện, BEFORE UPDATE và AFTER UPDATE được kích hoạt theo từng hàng. Một trigger có truy vấn phụ nặng hoặc insert audit lớn sẽ nhân chi phí theo số hàng.

MySQL không hỗ trợ statement-level trigger chạy một lần cho toàn bộ câu UPDATE. Nếu cần xử lý cả tập dữ liệu, ưu tiên câu SQL set-based ở ứng dụng/procedure hoặc thiết kế batch rõ ràng. Không giả định MySQL cung cấp bảng ảo `inserted`/`deleted` chứa toàn bộ tập hàng.

## 13. Nhiều trigger cùng timing và event

Trên MySQL 5.7.2 trở lên, có thể tạo nhiều trigger cho cùng bảng, timing và event. Nếu không chỉ định thứ tự, chúng chạy theo thứ tự tạo. Có thể chỉ định:

```sql
CREATE TRIGGER bu_customers_second_check
BEFORE UPDATE ON customers
FOR EACH ROW
FOLLOWS bu_customers_validate
BEGIN
    SET NEW.display_name = TRIM(NEW.display_name);
END;
```

`FOLLOWS`/`PRECEDES` xác định thứ tự tương đối với trigger cùng timing/event trên cùng bảng. Trigger được tham chiếu phải tồn tại. Khi có nhiều trigger, kiểm tra `ACTION_ORDER` trong metadata và quản lý thứ tự qua migration.

## 14. SIGNAL để từ chối dữ liệu

Trong trigger, dùng `SIGNAL` để phát lỗi SQL có chủ đích:

```sql
SIGNAL SQLSTATE '45000'
    SET MESSAGE_TEXT = 'Business rule violated';
```

`45000` là SQLSTATE dành cho exception do ứng dụng định nghĩa. Caller nhận lỗi và có thể ánh xạ thành lỗi nghiệp vụ phù hợp. Đặt message ngắn, ổn định và không đưa dữ liệu nhạy cảm vào message. Không âm thầm bỏ qua dữ liệu sai hoặc sửa dữ liệu theo cách caller không thể dự đoán.

## 15. Transaction và rollback của trigger

Với bảng InnoDB, câu lệnh kích hoạt trigger và các thao tác InnoDB do trigger thực hiện thuộc cùng transaction:

- Nếu INSERT/UPDATE/DELETE gốc thất bại, thay đổi trong trigger cũng rollback.
- Nếu thao tác audit trong trigger thất bại, statement gốc thất bại.
- Nếu transaction caller rollback sau khi statement thành công, cả thay đổi bảng gốc và audit đều rollback.
- Trigger không được tự mở transaction, `COMMIT` hoặc `ROLLBACK`.

Điều này phù hợp với audit row hoặc outbox row cần atomic với thay đổi dữ liệu. Ưu tiên InnoDB cho bảng nền và bảng phụ do trigger ghi. Nếu dùng nontransactional engine, không giả định mọi side effect đều rollback cùng nhau.

Trigger không nên gửi email hoặc gọi HTTP. Ghi một outbox event trong cùng transaction; worker Java đọc outbox và thực hiện side effect sau commit.

## 16. Giới hạn quan trọng của trigger MySQL

- Trigger chỉ chạy `FOR EACH ROW`; không có statement-level trigger.
- Không được dùng `START TRANSACTION`, `COMMIT` hoặc `ROLLBACK` trong trigger.
- Không được trả result set trực tiếp cho client.
- Không thể dùng `RETURN` để kết thúc trigger như function.
- Trigger không thể sửa bảng đang được câu lệnh kích hoạt nó sử dụng; thao tác đó có thể báo lỗi 1442.
- Không tạo trigger trên view; trigger gắn với bảng cơ sở.
- `TRUNCATE TABLE` là DDL và không kích hoạt DELETE trigger.
- Các thao tác cascade do foreign key thực hiện không kích hoạt trigger tương ứng.
- Không có cú pháp `UPDATE OF column`; cần so sánh `OLD`/`NEW` để biết cột nào đổi.
- Trigger làm tăng latency và lock duration của câu lệnh gốc.

Mọi giới hạn stored-program áp dụng cho phần thân trigger. Không thiết kế trigger như nơi orchestration mạng hoặc điều khiển transaction.

## 17. Kiểm tra cột thực sự thay đổi

MySQL không có cú pháp trigger kiểu `AFTER UPDATE OF status`. Trigger UPDATE được khai báo cho bảng; nếu chỉ muốn audit một số cột, so sánh `OLD` và `NEW`:

```sql
IF NOT (OLD.email <=> NEW.email)
   OR NOT (OLD.display_name <=> NEW.display_name) THEN
    -- Ghi audit cho thay đổi thông tin liên hệ.
END IF;
```

Toán tử `<=>` so sánh NULL-safe, khác với `=` khi có NULL. Không dùng `OLD.col <> NEW.col` nếu cần nhận biết chính xác trường hợp NULL đổi sang giá trị hoặc ngược lại.

## 18. INSERT đặc biệt và đường ghi dữ liệu

Ngoài INSERT thông thường, MySQL có các dạng ghi đặc biệt:

- `INSERT ... ON DUPLICATE KEY UPDATE` có thể đi qua logic trigger INSERT và UPDATE tùy mỗi hàng được insert mới hay xử lý nhánh duplicate.
- `REPLACE` có thể xóa hàng xung đột rồi chèn hàng mới; trigger DELETE và INSERT liên quan có thể được kích hoạt.
- `LOAD DATA` cũng có thể kích hoạt INSERT trigger cho các hàng được nạp.

Các dạng này có thứ tự và số lần kích hoạt riêng theo đường đi thực tế. Nếu bảng có trigger audit hoặc chuẩn hóa, hãy kiểm thử từng dạng DML mà ứng dụng sử dụng; không giả định mọi lệnh ghi chỉ kích hoạt INSERT trigger.

## 19. Trigger, foreign key và cascade

Foreign key và trigger là hai cơ chế khác nhau. InnoDB có thể tự thực hiện `ON DELETE CASCADE` hoặc `ON UPDATE CASCADE`, nhưng thao tác cascade do foreign key thực hiện không kích hoạt trigger trên các bảng bị cascade.

Nếu xóa một customer làm các hàng con bị xóa qua `ON DELETE CASCADE`, DELETE trigger của bảng con không chạy cho những hàng bị xóa do cascade. Nếu cần audit các thay đổi cascade, phải thiết kế cơ chế khác hoặc thực hiện thao tác xóa tường minh qua ứng dụng/procedure.

Không thay foreign key bằng trigger tự kiểm tra quan hệ nếu constraint có thể biểu diễn đúng yêu cầu. Constraint được database quản lý và bảo vệ tốt hơn trước race condition.

## 20. Trigger và bảo mật DEFINER

Trigger có thuộc tính `DEFINER`; khi trigger chạy, MySQL kiểm tra quyền đối với đối tượng nền theo quyền của definer. Trigger không có mệnh đề `SQL SECURITY INVOKER` như procedure/function.

Điều này cho phép user ứng dụng thực hiện DML trên bảng và trigger ghi audit theo quyền của definer. Cần:

- Dùng tài khoản definer chuyên dụng, có quyền tối thiểu.
- Bảo đảm definer tồn tại ở mọi môi trường triển khai phù hợp.
- Không dùng tài khoản DBA hoặc tài khoản cá nhân có quyền quá rộng.
- Cấp quyền `TRIGGER` cho tài khoản tạo trigger và quyền cần thiết trên bảng liên quan.
- Kiểm tra quyền của definer trên audit/outbox table sau migration.
- Quản lý `DEFINER` bằng source control/migration và review thay đổi quyền.

`CURRENT_USER()` trong trigger phản ánh security context/definer đang thực thi, không mặc nhiên là danh tính người dùng cuối của ứng dụng. Nếu cần audit actor, truyền danh tính qua cơ chế ứng dụng đáng tin cậy và bảo vệ khả năng giả mạo.

## 21. Kiểm tra trigger và metadata

Liệt kê trigger:

```sql
SHOW TRIGGERS FROM app_db;
```

Xem định nghĩa:

```sql
SHOW CREATE TRIGGER app_db.ai_customers_audit\G
```

Tra metadata:

```sql
SELECT
    TRIGGER_NAME,
    EVENT_MANIPULATION,
    EVENT_OBJECT_TABLE,
    ACTION_TIMING,
    ACTION_ORDER,
    DEFINER,
    SQL_MODE,
    ACTION_STATEMENT
FROM INFORMATION_SCHEMA.TRIGGERS
WHERE TRIGGER_SCHEMA = 'app_db'
ORDER BY EVENT_OBJECT_TABLE, EVENT_MANIPULATION,
         ACTION_TIMING, ACTION_ORDER;
```

Metadata giúp xác nhận trigger, event/timing, thứ tự và definer. Cần quyền phù hợp để xem đầy đủ định nghĩa. Không chỉ dựa vào tên trigger; hãy đọc `ACTION_STATEMENT` và kiểm thử hành vi.

Xóa trigger:

```sql
DROP TRIGGER IF EXISTS app_db.ai_customers_audit;
```

Thay đổi trigger thường cần `DROP` rồi `CREATE` lại bằng migration. Thực hiện có kiểm soát vì khoảng thời gian giữa drop/create có thể khiến DML không còn trigger; lập kế hoạch migration và kiểm tra sau khi hoàn tất.

## 22. Chi phí hiệu năng và vận hành

Trigger chạy đồng bộ trong câu lệnh gốc. Thời gian xử lý trigger cộng trực tiếp vào latency của INSERT/UPDATE/DELETE và có thể kéo dài thời gian giữ khóa.

- Giữ trigger ngắn, số truy vấn phụ nhỏ và có index phù hợp.
- Tránh cursor/vòng lặp từng hàng nếu có thể dùng set-based SQL.
- Tránh ghi audit nhiều cột lớn nếu không cần; quản lý dung lượng và retention.
- Kiểm tra deadlock khi trigger ghi nhiều bảng hoặc transaction cập nhật theo thứ tự khác nhau.
- Đo DML trước/sau khi tạo trigger dưới tải đại diện.
- Theo dõi dung lượng audit/outbox, index và tốc độ purge/archive.
- Kiểm tra mọi đường ghi: ứng dụng, batch, ETL, `LOAD DATA`, upsert và công cụ quản trị.

Trigger có thể tạo side effect khó nhận ra từ SQL ở ứng dụng. Ghi rõ trong tài liệu schema và migration rằng bảng có trigger; developer/DBA cần kiểm tra trigger khi điều tra DML chậm hoặc lỗi bất ngờ.

## 23. Quy trình kiểm thử trigger

1. Tạo schema thử nghiệm tương đương và dữ liệu đại diện.
2. Kiểm tra từng event INSERT, UPDATE, DELETE ở timing cần dùng.
3. Kiểm tra `OLD`/`NEW`, NULL, default và `AUTO_INCREMENT`.
4. Kiểm tra DML nhiều hàng để xác nhận trigger chạy theo từng hàng.
5. Kiểm tra `SIGNAL` làm statement thất bại và InnoDB rollback đúng.
6. Kiểm tra audit khi transaction commit và khi caller rollback.
7. Kiểm tra upsert, REPLACE, LOAD DATA nếu workload sử dụng.
8. Kiểm tra foreign key cascade có bỏ qua trigger bảng con hay không.
9. Kiểm tra quyền definer và quyền user runtime.
10. Kiểm tra thứ tự khi có nhiều trigger cùng event/timing.
11. Đo latency, lock wait, deadlock và dung lượng phát sinh.
12. Chuẩn bị migration rollback và xác minh trigger sau deploy.

## 24. Những lỗi và hiểu nhầm thường gặp

| Hiểu nhầm / lỗi | Thực tế | Cách xử lý |
| --- | --- | --- |
| AFTER trigger có thể sửa NEW | NEW trong AFTER là chỉ đọc | Gán giá trị trong BEFORE trigger |
| DELETE trigger có NEW | DELETE chỉ có OLD | Đọc dữ liệu qua OLD |
| Trigger chạy một lần cho cả statement | MySQL chạy FOR EACH ROW | Ước lượng chi phí theo số hàng |
| Có thể COMMIT trong trigger | Trigger tham gia transaction của statement/caller | Để caller sở hữu transaction |
| TRUNCATE kích hoạt DELETE trigger | TRUNCATE là DDL, không chạy DELETE trigger | Dùng DELETE nếu cần row-level trigger |
| FK CASCADE kích hoạt trigger bảng con | Cascade do InnoDB thực hiện không kích hoạt trigger | Thiết kế audit cascade riêng |
| Có thể UPDATE lại bảng đang kích hoạt trigger | MySQL chặn sửa bảng đang được statement sử dụng (1442) | Gán NEW trong BEFORE hoặc ghi bảng khác |
| Trigger chỉ chạy từ Java | Mọi client DML trên bảng đều có thể kích hoạt | Kiểm thử cả ETL, batch và admin tools |
| Trigger không ảnh hưởng latency | Trigger chạy đồng bộ cùng DML | Đo chi phí dưới tải thật |
| DEFINER là user cuối của request | Trigger chạy theo quyền definer | Thiết kế actor audit riêng, đáng tin cậy |

## 25. Bài tập thực hành

1. Tạo `customers` và `customer_audit` theo ví dụ.
2. Tạo BEFORE INSERT để trim/lowercase email và từ chối email rỗng bằng `SIGNAL`.
3. Tạo AFTER INSERT để ghi audit; kiểm tra `AUTO_INCREMENT` trong `NEW`.
4. Tạo BEFORE UPDATE để kiểm tra trạng thái và đặt `NEW.updated_at`.
5. Tạo AFTER UPDATE chỉ ghi audit khi `OLD.status` khác `NEW.status` bằng NULL-safe comparison.
6. Tạo BEFORE DELETE từ chối xóa customer active; kiểm tra lỗi caller nhận được.
7. Tạo AFTER DELETE ghi `OLD.customer_id` và `OLD.status` vào audit table.
8. UPDATE nhiều hàng; đếm audit record và giải thích trigger chạy theo từng hàng.
9. Tạo hai BEFORE UPDATE trigger cùng bảng; dùng `FOLLOWS` và kiểm tra `ACTION_ORDER`.
10. Thử `TRUNCATE TABLE` và FK `ON DELETE CASCADE`; quan sát trigger không được kích hoạt như DELETE thông thường.
11. Thử `INSERT ... ON DUPLICATE KEY UPDATE`, `REPLACE`, `LOAD DATA` nếu môi trường lab hỗ trợ.
12. Cấp quyền `TRIGGER` cho user triển khai và quyền tối thiểu cho definer.
13. Đo thời gian DML trước/sau khi thêm trigger và khi audit table có index phù hợp.
14. Thiết kế trigger chỉ ghi outbox event vào InnoDB; dùng worker ngoài database để xử lý side effect.

## 26. Ghi nhớ

MySQL trigger gắn với một bảng, một timing (`BEFORE`/`AFTER`) và một event (`INSERT`/`UPDATE`/`DELETE`), chạy `FOR EACH ROW`. `BEFORE INSERT`/`BEFORE UPDATE` có thể đọc và gán `NEW`; `AFTER` chỉ đọc; DELETE chỉ có `OLD`. Dùng BEFORE để chuẩn hóa/kiểm tra, `SIGNAL SQLSTATE '45000'` để từ chối dữ liệu; dùng AFTER để ghi audit hoặc outbox row cùng transaction.

Trigger không phải statement-level trigger, không được tự COMMIT/ROLLBACK, không trả result set, không được sửa bảng đang được statement kích hoạt sử dụng, `TRUNCATE` không kích hoạt DELETE trigger và FK cascade không kích hoạt trigger bảng con. Side effect chạy đồng bộ, tăng latency và lock duration; giữ trigger ngắn, dùng constraint khi phù hợp, quản lý quyền DEFINER/`TRIGGER`, kiểm tra `OLD`/`NEW`, thứ tự nhiều trigger và metadata. Kiểm thử mọi đường DML thực tế; dùng outbox/worker cho side effect bên ngoài database.
