# Lựa chọn constraint, trigger, event hoặc tác vụ từ ứng dụng

Một quy tắc nghiệp vụ có thể được thực thi ở nhiều nơi: constraint trong schema, trigger chạy theo thao tác ghi, event chạy theo lịch hoặc tác vụ do ứng dụng điều phối. Chọn sai vị trí thường tạo ra dữ liệu không nhất quán, side effect khó truy vết, job chạy trùng hoặc logic bị lặp ở nhiều service.

Hãy bắt đầu từ câu hỏi: quy tắc cần được bảo vệ ở mọi lần ghi dữ liệu, cần phản ứng ngay khi một hàng thay đổi, cần chạy theo thời gian, hay cần điều phối một quy trình nghiệp vụ bên ngoài cơ sở dữ liệu? Constraint là lựa chọn đầu tiên cho bất biến dữ liệu mà MySQL biểu diễn được. Trigger phù hợp với phản ứng đồng bộ ngay trong DML và các side effect chỉ thuộc cơ sở dữ liệu. Event Scheduler dành cho công việc định kỳ đơn giản nằm trong MySQL. Application job phù hợp với workflow cần retry, quan sát, gọi dịch vụ khác hoặc phối hợp nhiều bước.

Bài học thuộc module `DATABASE_MYSQL`, nơi bạn làm chủ thiết kế bảng, kiểu dữ liệu, khóa, truy vấn SQL, index, transaction, kiểm soát đồng thời, đọc execution plan, tối ưu truy vấn và vận hành cơ sở dữ liệu quan hệ. Mục tiêu là đặt mỗi quy tắc ở đúng tầng, hiểu ranh giới transaction và bảo mật, rồi kiểm chứng hành vi khi nhiều ứng dụng cùng ghi dữ liệu.

Sau bài học, bạn có thể:

- Phân biệt constraint, trigger, Event Scheduler và application job.
- Chọn `PRIMARY KEY`, `UNIQUE`, `NOT NULL`, `FOREIGN KEY` và `CHECK` cho bất biến dữ liệu.
- Nhận diện khi generated column hoặc câu lệnh DML tường minh phù hợp hơn trigger.
- Dùng trigger cho kiểm tra hàng, audit nội bộ hoặc cập nhật dữ liệu phụ có kiểm soát.
- Hiểu trigger chạy theo từng hàng, cùng transaction với statement gọi nó trên bảng transactional.
- Lập lịch công việc đơn giản bằng MySQL Event Scheduler.
- Chọn application job cho retry, queue, gọi API và workflow nhiều bước.
- Tránh job chạy trùng khi replication, failover hoặc nhiều worker cùng xử lý.
- Thiết kế idempotency, observability, quyền tối thiểu và quy trình vận hành.

## 1. Bốn cơ chế giải quyết bốn loại vấn đề

| Cơ chế | Khi nào chạy? | Phạm vi | Dùng tốt cho | Hạn chế chính |
| --- | --- | --- | --- | --- |
| Constraint | Khi INSERT/UPDATE/DELETE liên quan được kiểm tra | Bất biến của dữ liệu trong schema | PK, unique, quan hệ FK, miền giá trị và điều kiện trên một hàng | Không biểu diễn được mọi quy tắc nhiều bảng hoặc workflow |
| Trigger | Đồng bộ với INSERT/UPDATE/DELETE trên bảng | Mỗi hàng bị tác động | Audit trong DB, chuẩn hóa/kiểm tra theo OLD/NEW, ghi dữ liệu phụ cùng transaction | Logic ẩn, chạy theo từng hàng, có giới hạn và ảnh hưởng latency DML |
| Event Scheduler | Theo thời điểm hoặc chu kỳ | Server MySQL và database | Cleanup, tổng hợp hoặc bảo trì định kỳ đơn giản | Phụ thuộc scheduler/definer/topology; khả năng retry/quan sát hạn chế |
| Application job | Theo queue, lịch hoặc sự kiện ứng dụng | Service/worker và các hệ thống liên quan | Gửi thông báo, gọi API, retry, workflow nhiều bước, điều phối phân tán | Cần thiết kế retry, idempotency, quyền và độ tin cậy của worker |

Các cơ chế có thể phối hợp nhưng không nên cùng thực thi một quy tắc theo nhiều cách khác nhau. Ví dụ, constraint bảo vệ `quantity > 0`; trigger ghi audit thay đổi trạng thái; outbox lưu sự kiện cần gửi; application worker gửi thông báo; Event Scheduler chỉ dọn dữ liệu hết hạn theo lịch.

## 2. Quy trình chọn cơ chế

Hãy phân loại yêu cầu theo bản chất:

1. **Bất biến phải đúng với mọi đường ghi:** ưu tiên constraint. Dữ liệu có thể được ghi từ API, batch, migration, script vận hành hoặc một ứng dụng khác; constraint bảo vệ tất cả các đường đó.
2. **Phản ứng đồng bộ với thay đổi của một hàng:** cân nhắc trigger nếu logic phải chạy trong cùng statement/transaction và chỉ tác động tới cơ sở dữ liệu.
3. **Công việc cần chạy theo giờ/ngày:** dùng Event Scheduler nếu tác vụ nhỏ, độc lập, chỉ làm việc với dữ liệu MySQL và chấp nhận mô hình vận hành của server. Nếu cần retry/monitoring/phối hợp hệ thống, dùng application scheduler/queue.
4. **Quy trình nhiều bước hoặc có side effect bên ngoài:** đặt trong ứng dụng. Dùng transaction/outbox để ghi nhận ý định gửi, sau đó worker xử lý với retry và idempotency.

Không chọn trigger chỉ vì muốn “tự động hóa” mọi thứ. Trigger làm một thao tác DML có thể thực hiện thêm nhiều việc mà người gọi không nhìn thấy trong câu SQL. Không chọn Event Scheduler chỉ vì muốn chạy SQL định kỳ nếu tổ chức đã có nền tảng job có giám sát và điều phối tập trung.

## 3. Constraint: lựa chọn đầu tiên cho bất biến dữ liệu

Constraint là quy tắc được khai báo trong schema. MySQL kiểm tra quy tắc khi dữ liệu được ghi, bất kể câu lệnh đến từ ứng dụng nào.

### 3.1. NOT NULL và DEFAULT

`NOT NULL` ngăn cột nhận NULL. `DEFAULT` cung cấp giá trị mặc định khi INSERT bỏ qua cột hoặc dùng từ khóa DEFAULT; DEFAULT không tự thay thế một constraint kiểm tra miền giá trị.

```sql
CREATE TABLE inventory_item (
    item_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    sku VARCHAR(40) NOT NULL,
    quantity INT UNSIGNED NOT NULL DEFAULT 0,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (item_id),
    UNIQUE KEY uq_inventory_item_sku (sku),
    CONSTRAINT chk_inventory_quantity_nonnegative
        CHECK (quantity >= 0)
) ENGINE = InnoDB;
```

Schema bảo vệ SKU không NULL và duy nhất, quantity không NULL và không âm. Ứng dụng không cần tự kiểm tra trước mọi INSERT để bảo đảm các bất biến này; ứng dụng vẫn nên validate sớm để trả thông báo thân thiện, còn database là lớp bảo vệ cuối cùng.

### 3.2. PRIMARY KEY và UNIQUE

- `PRIMARY KEY` định danh duy nhất mỗi hàng và không cho phép NULL.
- `UNIQUE` ngăn giá trị trùng trong unique key.
- Với MySQL, unique index có thể chứa nhiều hàng có NULL ở cột nullable; NULL không được xem như một giá trị bằng nhau theo phép so sánh unique thông thường. Nếu nghiệp vụ yêu cầu bắt buộc có giá trị, kết hợp `NOT NULL`.

```sql
CREATE TABLE app_user (
    user_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    email VARCHAR(255) NOT NULL,
    external_ref VARCHAR(80) NULL,
    PRIMARY KEY (user_id),
    UNIQUE KEY uq_app_user_email (email),
    UNIQUE KEY uq_app_user_external_ref (external_ref)
) ENGINE = InnoDB;
```

Email không được NULL và không trùng. `external_ref` có thể NULL; nhiều hàng chưa có external reference vẫn có thể tồn tại. Nếu quy tắc yêu cầu external_ref luôn có và duy nhất, đổi cột thành NOT NULL.

### 3.3. FOREIGN KEY

Foreign key bảo vệ quan hệ giữa bảng con và bảng cha. Nó ngăn hàng con tham chiếu tới khóa cha không tồn tại, đồng thời định nghĩa hành vi khi hàng cha bị xóa hoặc cập nhật.

```sql
CREATE TABLE sales_order (
    order_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    customer_id BIGINT UNSIGNED NOT NULL,
    order_date DATETIME NOT NULL,
    order_status VARCHAR(20) NOT NULL DEFAULT 'OPEN',
    PRIMARY KEY (order_id),
    KEY idx_sales_order_customer (customer_id),
    CONSTRAINT fk_sales_order_customer
        FOREIGN KEY (customer_id)
        REFERENCES customer (customer_id)
        ON UPDATE RESTRICT
        ON DELETE RESTRICT
) ENGINE = InnoDB;
```

Chọn `RESTRICT`, `CASCADE` hoặc `SET NULL` theo semantics nghiệp vụ. Không dùng CASCADE chỉ để tiện xóa nếu dữ liệu con cần lưu cho audit hoặc báo cáo. Cần index phù hợp cho khóa ngoại để kiểm tra và join hiệu quả.

### 3.4. CHECK

CHECK phù hợp với điều kiện trên hàng hiện tại:

```sql
CREATE TABLE product_price (
    product_id BIGINT UNSIGNED NOT NULL PRIMARY KEY,
    list_price DECIMAL(12, 2) NOT NULL,
    discount_price DECIMAL(12, 2) NULL,
    CONSTRAINT chk_list_price_nonnegative CHECK (list_price >= 0),
    CONSTRAINT chk_discount_valid CHECK (
        discount_price IS NULL
        OR (discount_price >= 0 AND discount_price <= list_price)
    )
) ENGINE = InnoDB;
```

MySQL thực thi CHECK từ phiên bản 8.0.16. Các phiên bản trước đó có thể phân tích cú pháp nhưng không thực thi constraint như mong đợi; luôn xác minh phiên bản và `SHOW CREATE TABLE` khi triển khai schema. CHECK không phải nơi để truy vấn bảng khác, gọi service hoặc thực hiện quy tắc cần đọc nhiều hàng.

### 3.5. Khi nào constraint chưa đủ?

Constraint phù hợp với quy tắc có thể diễn đạt trực tiếp trong schema: một hàng phải có giá trị hợp lệ, một khóa phải duy nhất, hoặc quan hệ FK phải tồn tại. Các quy tắc như “tổng hạn mức của tất cả đơn chưa thanh toán không vượt ngân sách khách hàng” cần phối hợp nhiều hàng và đồng thời. Một câu SELECT kiểm tra trước rồi INSERT không đủ an toàn vì hai transaction có thể cùng vượt qua kiểm tra.

Với quy tắc nhiều hàng, hãy thiết kế transaction và locking phù hợp, dùng một hàng tổng hợp/ledger được cập nhật nguyên tử, hoặc một quy trình nghiệp vụ có cơ chế serialize. Trigger tự nó không loại bỏ race condition.

## 4. Ưu tiên generated column hoặc DML tường minh trước trigger

Một số nhu cầu tự động hóa không cần trigger:

- Giá trị mặc định: dùng `DEFAULT`.
- Giá trị suy ra từ các cột cùng hàng: dùng generated column nếu biểu thức và yêu cầu phù hợp.
- Giá trị do ứng dụng biết rõ: truyền trực tiếp trong INSERT/UPDATE.
- Dữ liệu tổng hợp cần cập nhật theo một workflow: cân nhắc câu lệnh DML tường minh trong transaction hoặc bảng summary có quy trình refresh.

Ví dụ generated column:

```sql
CREATE TABLE order_line (
    line_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    quantity INT UNSIGNED NOT NULL,
    unit_price DECIMAL(12, 2) NOT NULL,
    line_total DECIMAL(14, 2)
        GENERATED ALWAYS AS (quantity * unit_price) STORED,
    PRIMARY KEY (line_id),
    CONSTRAINT chk_order_line_quantity CHECK (quantity > 0),
    CONSTRAINT chk_order_line_price CHECK (unit_price >= 0)
) ENGINE = InnoDB;
```

`line_total` luôn được tính từ quantity và unit_price. Không cần trigger sao chép cùng một phép tính vào cột thường; generated column giúp schema thể hiện quan hệ dữ liệu trực tiếp.

## 5. Trigger: phản ứng đồng bộ với thay đổi hàng

Trigger được gắn với một bảng và một sự kiện `INSERT`, `UPDATE` hoặc `DELETE`. MySQL trigger chạy theo từng hàng (`FOR EACH ROW`), với thời điểm `BEFORE` hoặc `AFTER`.

| Thời điểm | Có thể đọc | Có thể thay đổi | Mục đích thường gặp |
| --- | --- | --- | --- |
| BEFORE INSERT | `NEW` | Gán giá trị cho `NEW` | Chuẩn hóa hoặc kiểm tra hàng sắp chèn |
| AFTER INSERT | `NEW` | Không sửa hàng nguồn qua NEW | Ghi audit hoặc hàng phụ sau khi insert thành công |
| BEFORE UPDATE | `OLD`, `NEW` | Gán giá trị cho `NEW` | Kiểm tra chuyển trạng thái hoặc chuẩn hóa |
| AFTER UPDATE | `OLD`, `NEW` | Không sửa hàng nguồn qua NEW | Ghi lại thay đổi |
| BEFORE DELETE | `OLD` | Không sửa OLD | Kiểm tra trước khi xóa |
| AFTER DELETE | `OLD` | Không sửa OLD | Ghi audit hoặc cập nhật dữ liệu phụ |

### 5.1. BEFORE trigger kiểm tra thay đổi

Ví dụ chỉ cho phép chuyển đơn từ OPEN sang PAID hoặc CANCELLED; không cho sửa đơn đã kết thúc:

```sql
DELIMITER //

CREATE TRIGGER bu_sales_order_status
BEFORE UPDATE ON sales_order
FOR EACH ROW
BEGIN
    IF OLD.order_status IN ('PAID', 'CANCELLED')
       AND NEW.order_status <> OLD.order_status THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'A completed order cannot change status';
    END IF;

    IF NEW.order_status NOT IN ('OPEN', 'PAID', 'CANCELLED') THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'Unsupported order status';
    END IF;
END//

DELIMITER ;
```

Trigger có thể đọc OLD và NEW để so sánh trạng thái. Tuy nhiên, nếu chỉ cần kiểm tra tập giá trị hợp lệ, CHECK thường đơn giản và dễ thấy hơn. Trigger ở đây minh họa một quy tắc chuyển trạng thái có xét giá trị cũ.

### 5.2. AFTER trigger ghi audit

Audit log là ví dụ phù hợp khi cần ghi lại thay đổi cùng transaction với dữ liệu nguồn.

```sql
CREATE TABLE sales_order_status_audit (
    audit_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    order_id BIGINT UNSIGNED NOT NULL,
    old_status VARCHAR(20) NOT NULL,
    new_status VARCHAR(20) NOT NULL,
    changed_at TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    connection_account VARCHAR(288) NOT NULL,
    PRIMARY KEY (audit_id),
    KEY idx_order_status_audit_order_time (order_id, changed_at)
) ENGINE = InnoDB;
```

```sql
DELIMITER //

CREATE TRIGGER au_sales_order_status_audit
AFTER UPDATE ON sales_order
FOR EACH ROW
BEGIN
    IF NOT (OLD.order_status <=> NEW.order_status) THEN
        INSERT INTO sales_order_status_audit (
            order_id,
            old_status,
            new_status,
            connection_account
        )
        VALUES (
            NEW.order_id,
            OLD.order_status,
            NEW.order_status,
            USER()
        );
    END IF;
END//

DELIMITER ;
```

Toán tử `<=>` là so sánh NULL-safe của MySQL. `USER()` ghi nhận account kết nối mà server quan sát được; nó không nhất thiết là danh tính người dùng cuối trong ứng dụng. Nếu cần actor nghiệp vụ, ứng dụng phải truyền context từ một nguồn tin cậy và kiểm soát quyền đặt context. Không xem một session variable tùy ý do client tự đặt là bằng chứng xác thực.

Với InnoDB, INSERT audit và UPDATE hàng nguồn tham gia cùng transaction. Nếu ghi audit thất bại, statement cập nhật hàng nguồn cũng thất bại; nếu transaction rollback, audit row cũng rollback. Đây là lợi ích của side effect nội bộ trong cùng database transaction.

## 6. Những giới hạn quan trọng của trigger

- Trigger chạy theo từng hàng, không có statement-level trigger. Một UPDATE tác động 100.000 hàng có thể gọi trigger 100.000 lần.
- Trigger không trả result set trực tiếp cho client. Dùng `SIGNAL` để từ chối statement với lỗi có chủ đích.
- Trigger không được tự điều khiển transaction bằng `START TRANSACTION`, `COMMIT` hoặc `ROLLBACK`.
- Trigger không thể sửa bảng đang được statement kích hoạt nó sử dụng theo cách gây lỗi mutating-table; thiết kế tránh cập nhật lại chính bảng nguồn trong trigger.
- Không dùng trigger để gọi HTTP, gửi email hoặc thực hiện side effect ngoài MySQL. Database transaction không thể rollback một request HTTP đã gửi.
- Trigger không gắn vào view hoặc temporary table; trigger được định nghĩa trên bảng cơ sở phù hợp.
- `TRUNCATE TABLE` không kích hoạt DELETE trigger. Các hành động xóa/cập nhật do foreign key cascade cũng không kích hoạt trigger tương ứng.
- Trigger có giới hạn về dynamic SQL, result set và các statement được phép; kiểm tra Reference Manual theo phiên bản trước khi đưa logic phức tạp vào.
- Trigger là logic ẩn đối với người chỉ đọc câu INSERT/UPDATE. Cần tài liệu hóa và quan sát hiệu năng.

MySQL hỗ trợ nhiều trigger cho cùng một bảng, cùng thời điểm và sự kiện. Có thể dùng `FOLLOWS` hoặc `PRECEDES` để quy định thứ tự tương đối khi tạo trigger mới. Không nên chia một quy tắc thành nhiều trigger phụ thuộc thứ tự nếu có thể gom thành một trigger rõ ràng.

### 6.1. Trigger không giải quyết race condition tự động

Giả sử cần bảo đảm tổng số hàng đặt trước không vượt tồn kho. Một trigger đọc `available_stock`, kiểm tra rồi ghi reservation có thể gặp race condition nếu hai transaction cùng đọc số lượng trước khi transaction kia cập nhật.

Giải pháp phải dựa vào thao tác nguyên tử và khóa phù hợp, ví dụ:

```sql
UPDATE inventory
SET available_quantity = available_quantity - p_quantity
WHERE product_id = p_product_id
  AND available_quantity >= p_quantity;
```

Sau đó kiểm tra affected rows trong cùng transaction. Nếu không có hàng được cập nhật, không đủ tồn kho. Câu UPDATE vừa kiểm tra điều kiện vừa thay đổi giá trị dưới cơ chế khóa của InnoDB. Trigger không thay thế cho thiết kế concurrency này.

## 7. Event Scheduler: công việc chạy theo lịch trong MySQL

Event là một đối tượng database được MySQL Event Scheduler thực thi tại một thời điểm hoặc theo chu kỳ. Nó phù hợp với công việc định kỳ đơn giản chỉ cần thao tác dữ liệu trong cùng server, ví dụ xóa batch session hết hạn hoặc refresh một bảng tổng hợp.

### 7.1. Kiểm tra scheduler

```sql
SHOW VARIABLES LIKE 'event_scheduler';
```

Giá trị thường gặp:

- `ON`: Event Scheduler hoạt động và có thể chạy event đang ENABLE.
- `OFF`: scheduler không chạy event; event vẫn có thể tồn tại.
- `DISABLED`: scheduler bị vô hiệu hóa ở mức khởi động và không thể bật lại bằng thay đổi runtime thông thường.

Muốn bật scheduler cần quyền quản trị phù hợp và cấu hình server cho phép. Trong production, việc bật/tắt phải thuộc runbook DBA, không để một ứng dụng tùy ý thay đổi biến global.

### 7.2. Tạo event định kỳ

Ví dụ xóa tối đa 1.000 session hết hạn mỗi 5 phút:

```sql
CREATE EVENT ev_purge_expired_sessions
ON SCHEDULE EVERY 5 MINUTE
STARTS CURRENT_TIMESTAMP + INTERVAL 5 MINUTE
ON COMPLETION PRESERVE
ENABLE
DO
    DELETE FROM app_session
    WHERE expires_at < CURRENT_TIMESTAMP
    ORDER BY expires_at
    LIMIT 1000;
```

Nên có index trên `expires_at`:

```sql
CREATE INDEX idx_app_session_expires_at
ON app_session (expires_at);
```

Giới hạn batch giảm thời gian một lần chạy và lượng lock/undo phát sinh. Nếu mỗi lần xóa 1.000 hàng nhưng tốc độ tạo session hết hạn cao hơn tốc độ dọn, backlog sẽ tăng; cần theo dõi số hàng tồn và điều chỉnh chu kỳ/batch.

### 7.3. Event một lần và event lặp lại

Chạy một lần tại thời điểm cụ thể:

```sql
CREATE EVENT ev_rebuild_monthly_summary
ON SCHEDULE AT '2026-12-01 02:00:00'
ON COMPLETION NOT PRESERVE
DO
    CALL sp_rebuild_monthly_summary();
```

Chạy lặp:

```sql
CREATE EVENT ev_refresh_daily_summary
ON SCHEDULE EVERY 1 DAY
STARTS '2026-11-20 02:00:00'
ON COMPLETION PRESERVE
DO
    CALL sp_refresh_daily_summary();
```

Ví dụ yêu cầu hai procedure tồn tại, có quyền thực thi phù hợp và thực hiện công việc mà không phụ thuộc vào client đọc result set. Event không có client tương tác để tiêu thụ kết quả như một lời gọi API. Event cũng không có tham số đầu vào như một API; nếu cần cấu hình, lưu cấu hình trong bảng hoặc gọi một procedure đọc cấu hình đã được kiểm soát.

### 7.4. Quản lý và quan sát event

```sql
SHOW EVENTS FROM reporting_db;

SELECT
    EVENT_NAME,
    DEFINER,
    TIME_ZONE,
    EVENT_TYPE,
    EXECUTE_AT,
    INTERVAL_VALUE,
    INTERVAL_FIELD,
    STATUS,
    LAST_EXECUTED
FROM INFORMATION_SCHEMA.EVENTS
WHERE EVENT_SCHEMA = 'reporting_db';
```

Tạm dừng và bật lại:

```sql
ALTER EVENT ev_purge_expired_sessions DISABLE;
ALTER EVENT ev_purge_expired_sessions ENABLE;
```

Xóa event:

```sql
DROP EVENT IF EXISTS ev_purge_expired_sessions;
```

`LAST_EXECUTED` cho biết lần chạy gần nhất, không phải lịch sử đầy đủ của mọi lần chạy. Nếu cần lịch sử, số hàng xử lý, duration, lỗi và retry, hãy ghi log có cấu trúc trong bảng vận hành hoặc dùng hệ thống giám sát bên ngoài.

## 8. Những giới hạn và rủi ro của Event Scheduler

- Event chỉ chạy khi `event_scheduler` đang ON và event được ENABLE.
- Event chạy trong context của definer; definer phải tồn tại và có quyền cần thiết cho các câu lệnh trong event/procedure được gọi.
- Event không nhận tham số như một API; dữ liệu cấu hình thường lấy từ bảng.
- Event không tự cung cấp queue retry, exponential backoff, dead-letter queue hoặc dashboard job như một nền tảng worker chuyên dụng.
- Event body vẫn tiêu thụ CPU, I/O, lock và connection/thread của server; một job quá nặng có thể ảnh hưởng workload giao dịch.
- Lịch chạy theo server/database; phải xác định timezone và hành vi khi server dừng hoặc failover.
- Không giả định event sẽ chạy đúng một lần trong mọi kịch bản HA. Phải thiết kế job idempotent và quy định node nào được phép chạy scheduler.
- Event có thể gọi procedure, nhưng procedure phải tuân thủ các giới hạn của stored program và transaction.

Quyền tạo/quản lý event là quyền `EVENT` trên schema. Cấp quyền có chủ đích và quản lý definer như một danh tính vận hành có vòng đời rõ ràng.

## 9. Application job: workflow do ứng dụng điều phối

Application job phù hợp khi công việc cần tương tác với nhiều hệ thống hoặc yêu cầu năng lực vận hành cao hơn Event Scheduler:

- Gửi email, SMS, push notification hoặc gọi HTTP API.
- Xử lý file, object storage hoặc dịch vụ thanh toán.
- Chạy workflow nhiều bước, có trạng thái, retry và dead-letter queue.
- Phân phối việc cho nhiều worker và điều chỉnh concurrency.
- Cần dashboard, tracing, alert, SLA và khả năng pause/resume.
- Cần chính sách backoff, giới hạn tốc độ hoặc lịch theo tenant/người dùng.

Không nên chỉ chuyển toàn bộ logic sang ứng dụng rồi bỏ constraint. Các bất biến dữ liệu vẫn nên được bảo vệ ở database; application job điều phối quy trình và side effect.

### 9.1. Idempotency và xử lý ít nhất một lần

Worker thường có thể nhận lại một job khi timeout, process crash hoặc mất xác nhận. Vì vậy, hãy thiết kế xử lý idempotent: chạy lại cùng một job không tạo ra tác động nghiệp vụ trùng lặp.

Ví dụ bảng outbox/job:

```sql
CREATE TABLE outbox_event (
    event_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    idempotency_key VARCHAR(120) NOT NULL,
    aggregate_type VARCHAR(40) NOT NULL,
    aggregate_id BIGINT UNSIGNED NOT NULL,
    event_type VARCHAR(80) NOT NULL,
    payload JSON NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'PENDING',
    created_at TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    processed_at TIMESTAMP(6) NULL,
    PRIMARY KEY (event_id),
    UNIQUE KEY uq_outbox_idempotency (idempotency_key),
    KEY idx_outbox_pending (status, event_id),
    CONSTRAINT chk_outbox_status
        CHECK (status IN ('PENDING', 'PROCESSING', 'DONE', 'FAILED'))
) ENGINE = InnoDB;
```

Trong transaction nghiệp vụ, ứng dụng cập nhật dữ liệu và INSERT outbox event. Nếu transaction rollback, cả dữ liệu nghiệp vụ và outbox row cùng rollback. Worker đọc outbox sau commit, gửi message/API, rồi cập nhật trạng thái. Nếu gửi thành công nhưng worker crash trước khi đánh dấu DONE, message có thể được gửi lại; consumer hoặc API đích cần idempotency key.

### 9.2. Tránh nhiều worker xử lý cùng một job

Với nhiều worker, cần cơ chế claim có tính nguyên tử, lease hoặc khóa. MySQL hỗ trợ `SELECT ... FOR UPDATE SKIP LOCKED` trong các phiên bản phù hợp để lấy hàng chưa xử lý mà không chờ các worker đang giữ khóa hàng khác:

```sql
START TRANSACTION;

SELECT event_id, idempotency_key, payload
FROM outbox_event
WHERE status = 'PENDING'
ORDER BY event_id
LIMIT 20
FOR UPDATE SKIP LOCKED;

-- Ứng dụng đánh dấu các event đã claim trong cùng transaction.
UPDATE outbox_event
SET status = 'PROCESSING'
WHERE event_id IN (/* IDs đã lấy */);

COMMIT;
```

Đây là khung minh họa; trong ứng dụng thực tế, tạo danh sách ID bằng prepared statement và cập nhật có kiểm soát. Không giữ transaction mở trong lúc gọi HTTP. Claim job trong transaction ngắn, commit, thực hiện side effect bên ngoài, rồi ghi kết quả bằng transaction khác. Dùng lease/timeout để thu hồi job bị bỏ dở.

## 10. Transaction và tính nguyên tử theo từng cơ chế

| Cơ chế | Ranh giới thực thi | Tính nguyên tử cần hiểu |
| --- | --- | --- |
| Constraint | Trong statement DML | Nếu vi phạm, statement bị từ chối; với InnoDB thay đổi của statement được rollback |
| Trigger | Bên trong statement kích hoạt | DML của trigger tham gia transaction của statement; lỗi trigger làm statement thất bại; với bảng transactional, thay đổi liên quan rollback cùng nhau |
| Event | Một lần thực thi event trên server | Các DML transactional tuân theo transaction của session/event; thiết kế transaction rõ ràng nếu event gọi nhiều bước |
| Application job | Do worker/ứng dụng quản lý | DB transaction không bao trùm HTTP hoặc message broker; cần outbox/saga/idempotency cho side effect ngoài DB |

Không cho rằng việc INSERT một hàng audit trong trigger có thể bảo đảm email đã được gửi. Trigger có thể ghi outbox row trong cùng transaction; worker gửi email sau khi commit.

## 11. Replication, failover và nơi chạy event

Trigger và event đều là object database, nhưng tác động của chúng với replication cần được tính trong thiết kế:

- DML chạy trên source/primary được ghi binary log theo cấu hình; replica áp dụng thay đổi theo cơ chế replication.
- Với row-based logging, replica áp dụng row changes từ binary log và không chạy lại trigger cho các row event đó như một statement DML độc lập.
- Với statement-based logging, statement có thể được thực thi trên replica và trigger có thể tham gia; cần bảo đảm semantics và cấu hình logging phù hợp.
- Event definition có thể được replicate, nhưng không nên để scheduler chạy đồng thời trên nhiều node có thể cùng là writer.
- Khi failover, runbook phải chỉ định node primary mới được phép bật scheduler và node cũ phải dừng chạy event trước khi nhận write hoặc bị cô lập.
- Application workers cũng cần leader/lease hoặc queue coordination để tránh hai deployment cùng thực hiện một tác vụ độc quyền.

Kiểm tra `binlog_format`, topology và quy trình failover thực tế. Không bật Event Scheduler trên mọi replica chỉ để “phòng trường hợp” vì có thể tạo chạy trùng khi vai trò node thay đổi.

## 12. Bảo mật và quyền tối thiểu

| Cơ chế | Quyền/identity cần quản lý |
| --- | --- |
| Constraint | Quyền DML/DDL của schema; ứng dụng không thể bỏ qua constraint chỉ bằng cách dùng một đường ghi khác thông thường |
| Trigger | Definer của trigger và quyền cần cho trigger body; quản lý definer còn tồn tại và không cấp quá rộng |
| Event | Quyền `EVENT` để tạo/quản lý và quyền của definer để thực thi body |
| Application job | Service account, secret, quyền DB tối thiểu, quyền API và quyền truy cập queue |

Trigger/event có thể chạy với quyền definer. Một routine hoặc trigger được định nghĩa bởi tài khoản đặc quyền có thể khiến DML của user ít quyền thực hiện thêm hành động vượt khỏi quyền trực tiếp của user đó. Review `SHOW CREATE TRIGGER`, `SHOW CREATE EVENT`, `DEFINER` và grant liên quan khi triển khai.

Không nhúng mật khẩu/API key vào trigger hoặc event definition. Dùng secret manager của ứng dụng cho thông tin xác thực dịch vụ bên ngoài.

## 13. Hiệu năng và khả năng quan sát

### 13.1. Constraint

Constraint thường có chi phí nhỏ và rõ ràng so với lợi ích toàn vẹn dữ liệu. Unique/FK cần index và có thể phát sinh kiểm tra khóa/lock. Đừng xóa constraint chỉ để tăng tốc khi chưa đo; tối ưu index, batch size và transaction trước.

### 13.2. Trigger

Chi phí trigger nhân theo số hàng DML. Một UPDATE 50.000 hàng có thể tạo 50.000 audit rows. Trigger gọi thêm truy vấn hoặc cập nhật bảng nóng có thể tăng lock duration, deadlock và replication lag. Đo statement latency, số hàng tác động, deadlock và thời gian transaction.

### 13.3. Event

Theo dõi `LAST_EXECUTED`, `STATUS`, thời gian chạy và số hàng xử lý. `INFORMATION_SCHEMA.EVENTS` không phải kho lịch sử job đầy đủ. Ghi log cho mỗi lần chạy nếu cần SLA, retry hoặc cảnh báo. Đặt batch limit và index theo điều kiện lọc.

### 13.4. Application job

Theo dõi queue depth, tuổi job lâu nhất, success/failure rate, retry count, processing duration, lease expiration và dead-letter count. Dùng correlation ID để nối job với transaction tạo outbox row và request nghiệp vụ ban đầu.

## 14. Các anti-pattern cần tránh

| Anti-pattern | Vì sao nguy hiểm | Hướng xử lý |
| --- | --- | --- |
| Validate unique bằng SELECT rồi INSERT | Hai transaction có thể cùng vượt qua SELECT | Dùng UNIQUE constraint và xử lý duplicate-key |
| Dùng trigger thay CHECK cho điều kiện đơn giản | Logic bị ẩn, khó thấy trong schema | Dùng CHECK/NOT NULL/UNIQUE/FK |
| Trigger gửi email hoặc gọi HTTP | Side effect ngoài DB không rollback cùng transaction | Ghi outbox rồi để worker gửi |
| Trigger cập nhật lại bảng đang bị DML tác động | Có thể gặp lỗi mutating-table và vòng lặp logic | Thiết kế DML tường minh hoặc bảng phụ phù hợp |
| Trigger chạy query nặng cho từng hàng | Tăng latency và lock time theo số hàng | Giảm công việc hoặc chuyển batch sang job |
| Dùng Event Scheduler cho workflow cần retry phức tạp | Thiếu queue/lease/dead-letter/observability chuyên dụng | Dùng application job platform |
| Bật scheduler trên mọi node | Có thể chạy cùng job nhiều lần sau failover | Chỉ định writer và runbook chuyển vai trò |
| Job xóa dữ liệu không có batch/index | Lock lâu, undo lớn và ảnh hưởng workload | Batch nhỏ, index, theo dõi backlog |
| Cho rằng event chạy đúng một lần | Restart/failover/triển khai có thể tạo lần chạy lặp hoặc bỏ lỡ | Thiết kế idempotent và theo dõi trạng thái |
| Lưu business rule chỉ trong một service | Script/batch/service khác có thể ghi dữ liệu sai | Đưa bất biến vào constraint hoặc DB transaction phù hợp |
| Dùng session variable làm actor đáng tin cậy | Client có thể tự đặt giá trị nếu không kiểm soát | Dùng identity/context từ kênh được xác thực và audit nguồn |

## 15. Ma trận lựa chọn theo tình huống

| Yêu cầu | Lựa chọn ưu tiên | Lý do |
| --- | --- | --- |
| Email phải duy nhất | `UNIQUE` + `NOT NULL` | Bảo vệ mọi đường ghi và xử lý race condition ở database |
| Số lượng không âm | `CHECK` + `NOT NULL` | Bất biến trên một hàng |
| Hàng con phải có hàng cha | `FOREIGN KEY` | Referential integrity do engine bảo vệ |
| Giá trị tổng hợp từ cột cùng hàng | Generated column | Tránh đồng bộ bằng trigger |
| Ghi audit thay đổi một hàng trong cùng transaction | Trigger hoặc DML audit tường minh | Trigger hữu ích khi mọi writer phải được bao phủ; DML tường minh dễ nhìn hơn khi chỉ một service sở hữu write |
| Gửi email sau khi tạo đơn | Outbox + application worker | Side effect ngoài DB, cần retry/idempotency |
| Xóa session hết hạn theo chu kỳ | Event Scheduler hoặc application scheduler | Chọn theo nhu cầu giám sát và topology |
| Tổng hợp báo cáo lớn mỗi đêm | Application job hoặc event gọi procedure | Cần batch, theo dõi thời gian và khả năng chạy lại |
| Kiểm tra ngân sách dùng chung nhiều hàng | Transaction/locking hoặc mô hình ledger | Cần xử lý concurrency, không chỉ trigger |
| Gọi nhiều service và chờ phản hồi | Application workflow | Cần timeout, retry, compensation và observability |

## 16. Runbook triển khai

### Trước khi triển khai

1. Viết quy tắc bằng ngôn ngữ nghiệp vụ và xác định dữ liệu cần bảo vệ.
2. Xác định mọi writer: API, batch, ETL, admin script và service tích hợp.
3. Chọn cơ chế và ghi rõ transaction boundary.
4. Xem xét race condition, deadlock và hành vi retry.
5. Kiểm tra MySQL version, engine, binary logging và topology.
6. Review quyền, definer, schema migration và khả năng rollback.
7. Tạo test cho dữ liệu hợp lệ, dữ liệu vi phạm và ghi đồng thời.

### Khi triển khai

1. Triển khai schema/constraint trước khi bật luồng ứng dụng phụ thuộc vào nó.
2. Tạo trigger/event bằng migration có thể review và theo dõi.
3. Kiểm tra `SHOW CREATE TABLE`, `SHOW CREATE TRIGGER` hoặc `SHOW CREATE EVENT`.
4. Xác nhận Event Scheduler và event status trên đúng node.
5. Chạy smoke test với một transaction kiểm soát được.
6. Quan sát lỗi constraint, trigger latency, deadlock, event execution và replication lag.

### Khi rollback hoặc failover

- Tắt event trước khi chuyển vai trò nếu node cũ còn hoạt động.
- Không DROP trigger trước khi xác định tác động tới integrity/audit.
- Giữ schema constraint tương thích với mọi phiên bản ứng dụng đang chạy.
- Nếu worker job đã gửi side effect, rollback database không thể thu hồi side effect đó; dùng compensation hoặc idempotency.
- Xác minh definer và quyền trên node mới.

## 17. Bài tập thực hành

1. Tạo bảng có NOT NULL, PRIMARY KEY, UNIQUE, FOREIGN KEY và CHECK. Thử INSERT/UPDATE vi phạm từng constraint và ghi nhận lỗi.
2. Tạo unique key nullable; chèn nhiều hàng có NULL và giải thích vì sao kết quả hợp lệ. Sau đó đổi cột thành NOT NULL.
3. Tạo generated column tính line total và so sánh với cách lưu cột thường được cập nhật bằng trigger.
4. Tạo BEFORE UPDATE trigger kiểm tra chuyển trạng thái. Thử chuyển trạng thái hợp lệ và không hợp lệ.
5. Tạo AFTER UPDATE audit trigger. Kiểm tra audit row được rollback cùng transaction nguồn.
6. Cố ý làm INSERT audit thất bại bằng một constraint trong bảng audit; quan sát UPDATE nguồn có thất bại theo hay không.
7. Chạy UPDATE nhiều hàng và đo số audit rows/latency phát sinh từ trigger.
8. Tạo Event Scheduler job xóa tối đa 1.000 hàng hết hạn mỗi lần. Kiểm tra `event_scheduler`, `SHOW EVENTS` và `LAST_EXECUTED`.
9. Tắt event, xác nhận event không chạy; bật lại và kiểm tra chu kỳ tiếp theo.
10. Tạo outbox row cùng transaction tạo đơn hàng. Rollback transaction và xác nhận không còn outbox row.
11. Mô phỏng worker gửi cùng một idempotency key hai lần; bảo đảm consumer không tạo side effect trùng.
12. Mô phỏng hai worker claim job bằng transaction ngắn và `SKIP LOCKED`; không giữ transaction trong lúc gọi dịch vụ ngoài.
13. Viết decision record cho một yêu cầu: constraint, trigger, event hay application job; nêu lý do, transaction, retry, security và monitoring.

## 18. Checklist hoàn thành

- [ ] Bất biến dữ liệu được biểu diễn bằng constraint khi có thể.
- [ ] Đã xem xét generated column/default trước khi tạo trigger.
- [ ] Trigger chỉ làm công việc đồng bộ, ngắn và thuộc phạm vi database.
- [ ] Trigger không gửi email/HTTP và không tự quản lý transaction.
- [ ] Đã hiểu trigger chạy theo từng hàng và tác động tới bulk DML.
- [ ] Đã kiểm tra các giới hạn TRUNCATE, FK cascade và mutating table.
- [ ] Event có lịch, timezone, definer, quyền và batch limit rõ ràng.
- [ ] Event Scheduler chỉ chạy trên node được chỉ định trong topology.
- [ ] Application job có idempotency, retry, lease và dead-letter phù hợp.
- [ ] Side effect ngoài DB được điều phối bằng outbox/workflow.
- [ ] Đã xác định transaction boundary và xử lý concurrency.
- [ ] Có log, metric, alert và runbook cho lỗi/failover.
- [ ] Có test cho đường ghi trực tiếp, bulk write, rollback và retry.

## 19. Tiêu chí hoàn thành

Bạn hoàn thành bài khi có thể phân loại một yêu cầu thành bất biến dữ liệu, phản ứng đồng bộ, công việc định kỳ hoặc workflow ứng dụng; chọn đúng constraint/trigger/event/application job; giải thích transaction và concurrency; đồng thời thiết kế được quyền, idempotency, replication/failover và monitoring tương ứng. Bạn cũng cần chỉ ra được vì sao một trigger hoặc event không thể thay thế một job queue khi quy trình cần gọi dịch vụ ngoài và retry có kiểm soát.

## Tài liệu tham khảo

- [MySQL 8.4 Reference Manual — Constraint](https://dev.mysql.com/doc/refman/8.4/en/constraints.html)
- [MySQL 8.4 Reference Manual — CHECK Constraints](https://dev.mysql.com/doc/refman/8.4/en/create-table-check-constraints.html)
- [MySQL 8.4 Reference Manual — Trigger Syntax and Examples](https://dev.mysql.com/doc/refman/8.4/en/trigger-syntax.html)
- [MySQL 8.4 Reference Manual — Using Triggers](https://dev.mysql.com/doc/refman/8.4/en/triggers.html)
- [MySQL 8.4 Reference Manual — Event Scheduler](https://dev.mysql.com/doc/refman/8.4/en/events.html)
- [MySQL 8.4 Reference Manual — CREATE EVENT Statement](https://dev.mysql.com/doc/refman/8.4/en/create-event.html)
- [MySQL 8.4 Reference Manual — Replication and Triggers](https://dev.mysql.com/doc/refman/8.4/en/replication-features-triggers.html)
