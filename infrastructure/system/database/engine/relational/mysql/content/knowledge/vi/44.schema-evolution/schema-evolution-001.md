# Quản lý DDL, stored program và dữ liệu tham chiếu bằng version control

Schema MySQL là một phần của mã nguồn ứng dụng. Bảng, index, constraint, stored procedure, function, trigger, event và dữ liệu tham chiếu đều quyết định cách ứng dụng đọc và ghi dữ liệu. Nếu thay đổi chúng thủ công trên từng môi trường, các database dễ lệch nhau và khó xác định phiên bản nào đang chạy. Quản lý chúng bằng version control và migration có thứ tự giúp mỗi thay đổi được review, triển khai lặp lại, kiểm tra và truy vết.

Bài học này thuộc chương **Thay đổi schema** của module **DATABASE_MYSQL**. Trong lộ trình làm chủ MySQL từ thiết kế bảng, kiểu dữ liệu, khóa và truy vấn SQL đến index, transaction, kiểm soát đồng thời, đọc kế hoạch thực thi, tối ưu truy vấn, phân quyền, sao lưu và vận hành, schema evolution kết nối thay đổi cấu trúc với vòng đời phát hành ứng dụng. Phạm vi bài học gồm DDL, stored program và dữ liệu tham chiếu được lưu trong repository, sau đó triển khai theo từng migration có kiểm soát.

## 1. Vì sao cần version hóa thay đổi database?

Một ứng dụng có thể phát hành phiên bản mới nhưng database vẫn giữ schema cũ. Nếu deploy code mà thiếu cột, index, routine hoặc dữ liệu tham chiếu cần thiết, ứng dụng có thể lỗi ngay khi chạy. Ngược lại, thay đổi database trước khi code tương thích có thể làm phiên bản ứng dụng đang chạy không hoạt động.

Version control cho database giúp trả lời các câu hỏi:

- Schema ở môi trường development, staging và production khác nhau ở điểm nào?
- Thay đổi nào đã được triển khai, vào thời điểm nào và bởi ai?
- Một stored procedure đang chạy có đúng phiên bản trong repository không?
- Dữ liệu tham chiếu nào được thêm, sửa hoặc ngừng sử dụng trong từng release?
- Khi migration thất bại, có thể tiếp tục, khôi phục hoặc triển khai bản sửa như thế nào?

Cần quản lý ít nhất bốn nhóm tài sản:

| Nhóm | Ví dụ | Cách version hóa |
|---|---|---|
| Cấu trúc schema | Database, table, column, index, constraint | Migration DDL theo thứ tự |
| Stored program | Procedure, function, trigger, event | Script tạo/cập nhật có kiểm soát |
| Dữ liệu tham chiếu | Trạng thái đơn hàng, loại khách hàng, mã quốc gia | Migration DML idempotent |
| Quyền và cấu hình liên quan | GRANT, role, SQL mode, event scheduler | Script triển khai riêng theo môi trường và chính sách bảo mật |

Không phải mọi dữ liệu đều là dữ liệu tham chiếu. Dữ liệu nghiệp vụ như đơn hàng, giao dịch, lịch sử khách hàng và dữ liệu cá nhân phải được quản lý qua backup, data migration hoặc quy trình đồng bộ dữ liệu. Không đưa bản dump production vào repository chỉ để version hóa schema.

## 2. Tổ chức repository cho database

Có thể tách migration và định nghĩa stored program thành các thư mục riêng. Ví dụ:

~~~text
database/
  migrations/
    V20261119_01__create_customer_status.sql
    V20261119_02__seed_customer_status.sql
    V20261119_03__add_status_to_customers.sql
    V20261119_04__create_customer_summary_procedure.sql
  reference/
    README.md
  routines/
    procedures/
    functions/
    triggers/
    events/
  tests/
    schema/
    data-integrity/
~~~

Cấu trúc này chỉ là một cách tổ chức. Nếu công cụ migration yêu cầu một thư mục cụ thể, hãy tuân theo cấu hình của công cụ và giữ quy ước nhất quán.

Một migration nên có tên mô tả hành động và một phiên bản duy nhất. Ví dụ với quy ước Flyway:

- `V20261119_01__create_customer_status.sql`
- `V20261119_02__seed_customer_status.sql`
- `V20261119_03__add_status_to_customers.sql`

Flyway ghi nhận các migration đã chạy trong bảng lịch sử schema, bao gồm phiên bản, checksum, thời gian và trạng thái. Những file versioned migration đã áp dụng cần được xem là bất biến. Nếu cần sửa logic, tạo migration mới; sửa file cũ sẽ làm checksum khác và khiến trạng thái triển khai không còn khớp lịch sử.

Một số công cụ dùng khái niệm tương tự nhưng tên bảng, quy tắc đặt file và cơ chế checksum khác nhau. Hãy đọc cấu hình của công cụ đang dùng trước khi chọn convention. Không để hai migration có cùng version sau khi merge branch.

## 3. Migration DDL: thay đổi schema theo từng bước

Ví dụ cần bổ sung bảng trạng thái khách hàng. Bước đầu tiên tạo bảng tham chiếu:

~~~sql
CREATE TABLE customer_status (
  status_code VARCHAR(24) NOT NULL,
  label VARCHAR(80) NOT NULL,
  sort_order SMALLINT UNSIGNED NOT NULL DEFAULT 0,
  is_active BOOLEAN NOT NULL DEFAULT TRUE,
  PRIMARY KEY (status_code)
) ENGINE=InnoDB;
~~~

Tiếp theo, bổ sung cột mới vào bảng khách hàng. Khi ứng dụng đang chạy, nên bắt đầu bằng cột nullable hoặc có default tương thích để phiên bản code cũ vẫn tiếp tục hoạt động:

~~~sql
ALTER TABLE customers
  ADD COLUMN status_code VARCHAR(24) NULL,
  ADD INDEX idx_customers_status_code (status_code);
~~~

Sau khi bảng tham chiếu và cột mới tồn tại, thêm foreign key:

~~~sql
ALTER TABLE customers
  ADD CONSTRAINT fk_customers_status
  FOREIGN KEY (status_code)
  REFERENCES customer_status (status_code)
  ON UPDATE RESTRICT
  ON DELETE RESTRICT;
~~~

Ở bước này, cột cho phép NULL nên các hàng cũ chưa có trạng thái vẫn hợp lệ. Sau đó mới backfill dữ liệu và chuyển code sang đọc/ghi cột mới. Khi tất cả hàng đã có giá trị hợp lệ, có thể phát hành một migration riêng để chuyển cột sang NOT NULL nếu nghiệp vụ yêu cầu.

Không nên gộp một thay đổi lớn thành một file khó phục hồi. Chia migration theo mục đích: tạo đối tượng, nạp dữ liệu tham chiếu, backfill, thêm constraint cuối cùng hoặc xóa cấu trúc cũ. Các bước phải được sắp xếp sao cho mỗi phiên bản ứng dụng đang chạy vẫn tương thích với schema tại thời điểm deploy.

## 4. DDL của MySQL và ranh giới transaction

DDL gồm các lệnh như `CREATE TABLE`, `ALTER TABLE`, `CREATE INDEX`, `DROP TABLE`, `CREATE PROCEDURE` và `CREATE TRIGGER`. Phần lớn lệnh DDL của MySQL gây implicit commit. Vì vậy, không thể dựa vào `START TRANSACTION` rồi `ROLLBACK` để hoàn tác toàn bộ một migration có DDL.

Ví dụ:

~~~sql
START TRANSACTION;

UPDATE customers
SET display_name = TRIM(display_name)
WHERE display_name <> TRIM(display_name);

ALTER TABLE customers
  ADD COLUMN migrated_at TIMESTAMP NULL;

ROLLBACK;
~~~

Lệnh `ALTER TABLE` có thể commit transaction đang mở trước khi thực hiện; `ROLLBACK` sau đó không hoàn tác DDL và cũng không thể khôi phục phần DML đã được implicit commit trước đó.

MySQL 8.0 hỗ trợ **atomic DDL** cho nhiều thao tác trên các đối tượng được hỗ trợ. Atomic DDL giúp một thao tác DDL riêng lẻ hoàn tất toàn bộ hoặc được phục hồi khi server gặp sự cố trong quá trình thực hiện. Điều này không biến DDL thành thao tác có thể rollback bằng transaction của người dùng, cũng không làm nhiều câu lệnh DDL trở thành một transaction chung.

Do đó:

- Tách DDL khỏi DML backfill khi cần ranh giới transaction rõ ràng.
- Không viết migration với giả định một lệnh ROLLBACK sẽ đảo ngược ALTER TABLE.
- Lập kế hoạch cho trạng thái trung gian nếu migration dừng giữa các file.
- Với thay đổi phá hủy dữ liệu, chuẩn bị backup hoặc bản sao có thể phục hồi trước khi chạy.
- Kiểm tra hành vi trên đúng phiên bản MySQL và storage engine đang dùng.

DML thông thường vẫn có thể được nhóm trong transaction InnoDB nếu không xen DDL gây implicit commit:

~~~sql
START TRANSACTION;

UPDATE customers
SET status_code = 'ACTIVE'
WHERE status_code IS NULL
  AND id >= 1
  AND id < 1001;

COMMIT;
~~~

Với bảng lớn, chia backfill thành các batch theo khóa chính và commit từng batch để giới hạn undo log, thời gian giữ khóa và tác động tới replica.

## 5. Quản lý lịch sử migration và tính lặp lại

Một migration runner thường lưu lịch sử trong một bảng riêng. Flyway mặc định dùng bảng `flyway_schema_history`; công cụ khác có thể dùng tên và schema khác. Bảng lịch sử giúp xác định file nào đã chạy, version nào đang áp dụng và checksum có khớp với file hiện tại hay không.

Quy tắc quan trọng:

1. **Version duy nhất:** mỗi migration version chỉ xuất hiện một lần trong toàn bộ lịch sử.
2. **Migration đã áp dụng là bất biến:** không sửa nội dung file versioned đã chạy trên bất kỳ môi trường chia sẻ nào.
3. **Thay đổi mới tạo migration mới:** dùng một file mới để sửa lỗi hoặc điều chỉnh schema.
4. **Kiểm tra checksum:** nếu checksum khác, điều tra nguyên nhân. Không tự xóa lịch sử hoặc sửa checksum để làm pipeline xanh.
5. **Không chạy song song migration:** chỉ một tiến trình được phép điều phối schema change tại một database tại một thời điểm.
6. **Ghi log triển khai:** lưu phiên bản ứng dụng, migration version, thời gian, kết quả và người/tiến trình thực hiện.

Nếu hai nhánh phát triển cùng tạo migration, cần giải quyết trùng version trước khi merge. Không đổi thứ tự migration đã chạy trên production bằng cách đổi tên file; tạo một migration tiếp theo để đưa schema về trạng thái mong muốn.

Một migration idempotent có thể được chạy lại mà không tạo tác động ngoài dự kiến, nhưng không phải mọi DDL đều tự động idempotent. Ví dụ, `CREATE TABLE IF NOT EXISTS` không xác minh cấu trúc bảng hiện tại có đúng định nghĩa mong đợi hay không. Migration runner nên là nguồn quyết định file nào đã chạy; đừng dùng `IF NOT EXISTS` để che schema drift.

## 6. Quản lý stored procedure và function

Stored procedure và function là mã nguồn database. Hãy lưu định nghĩa đầy đủ trong repository, review cùng ứng dụng và triển khai bằng migration có phiên bản.

Ví dụ một procedure báo cáo số đơn theo khách hàng:

~~~sql
DELIMITER //

DROP PROCEDURE IF EXISTS get_customer_order_count//

CREATE PROCEDURE get_customer_order_count(
  IN p_customer_id BIGINT UNSIGNED
)
SQL SECURITY INVOKER
READS SQL DATA
BEGIN
  SELECT
    customer_id,
    COUNT(*) AS order_count
  FROM orders
  WHERE customer_id = p_customer_id
  GROUP BY customer_id;
END//

DELIMITER ;
~~~

Trong ví dụ:

- `DROP PROCEDURE IF EXISTS` cho phép tạo lại procedure cùng tên.
- `SQL SECURITY INVOKER` khiến routine chạy với quyền của caller. Mặc định của routine là `DEFINER`, vì vậy cần chọn rõ mô hình quyền theo nhu cầu.
- `READS SQL DATA` mô tả đặc tính routine; khai báo này không thay thế việc kiểm tra logic và quyền truy cập.
- `DELIMITER` là lệnh của MySQL command-line client để đổi dấu kết thúc câu lệnh khi phần thân routine có dấu chấm phẩy; trong MySQL Shell dùng lệnh `\delimiter`. Đây là lệnh phía client, không phải câu lệnh SQL gửi tới server. Migration runner cũng phải hỗ trợ cách phân tách statement phù hợp với routine body.

Cách drop rồi create có một khoảng thời gian procedure không tồn tại; nếu CREATE thất bại, procedure cũ đã bị xóa. Với hệ thống cần tính sẵn sàng cao, có thể tạo procedure mới bằng tên phiên bản mới, chuyển ứng dụng sang gọi tên mới, xác minh rồi mới loại bỏ tên cũ ở migration sau. Nếu dùng cùng tên, chọn cửa sổ triển khai phù hợp và kiểm thử trước.

MySQL không hỗ trợ `CREATE OR REPLACE PROCEDURE` theo cách một số hệ quản trị khác hỗ trợ. Không giả định `CREATE PROCEDURE` sẽ ghi đè routine hiện có.

### Định nghĩa và quyền của routine

Routine có thuộc tính `SQL SECURITY DEFINER` hoặc `SQL SECURITY INVOKER`:

- **DEFINER:** routine thực thi với quyền của tài khoản definer. Cần quản lý tài khoản đó và quyền của nó cẩn thận.
- **INVOKER:** routine thực thi với quyền của người gọi. Caller phải có quyền trên các đối tượng được truy cập.

Không hardcode definer là một tài khoản cá nhân hoặc tài khoản chỉ tồn tại ở một môi trường. Nếu cần DEFINER, dùng tài khoản dịch vụ được quản lý thống nhất, kiểm soát quyền và bảo đảm tài khoản tồn tại ở nơi triển khai. Sau khi drop/create, kiểm tra lại quyền EXECUTE và các GRANT liên quan; việc tạo lại routine có thể yêu cầu áp dụng lại quyền đã cấp trên routine.

Function có thêm yêu cầu về tính xác định, quyền và các đặc tính khai báo. Không khai báo `DETERMINISTIC` chỉ để vượt qua cấu hình binary logging nếu function thực tế phụ thuộc dữ liệu hoặc trạng thái thay đổi. Khai báo phải phản ánh đúng hành vi.

## 7. Quản lý trigger và event

Trigger được gắn với một bảng và thời điểm như `BEFORE INSERT`, `AFTER UPDATE` hoặc `BEFORE DELETE`. Lưu từng trigger thành script riêng hoặc gom theo bảng với thứ tự rõ ràng.

Ví dụ:

~~~sql
DELIMITER //

DROP TRIGGER IF EXISTS customers_before_insert//

CREATE TRIGGER customers_before_insert
BEFORE INSERT ON customers
FOR EACH ROW
BEGIN
  SET NEW.display_name = TRIM(NEW.display_name);
END//

DELIMITER ;
~~~

Trigger không có cú pháp `CREATE OR REPLACE TRIGGER` phổ quát trong MySQL. Khi thay đổi trigger, phải có kế hoạch drop/create hoặc tạo trigger mới có tên khác, sau đó kiểm tra định nghĩa và thứ tự kích hoạt. MySQL hỗ trợ nhiều trigger cùng thời điểm và sự kiện trong các phiên bản hiện đại, nhưng thứ tự cần được khai báo/kiểm tra rõ ràng nếu logic phụ thuộc nhau.

Trigger có thể tạo tác động ẩn đối với ứng dụng, vì vậy nên giữ logic ngắn, có thể dự đoán và dễ kiểm thử. Tránh đưa toàn bộ quy trình nghiệp vụ phức tạp vào trigger nếu người vận hành khó truy vết tác dụng phụ.

Event Scheduler thực thi event theo lịch. Ví dụ:

~~~sql
CREATE EVENT ev_archive_old_audit
ON SCHEDULE EVERY 1 DAY
DO
  INSERT INTO audit_archive
    (event_id, action_name, created_at)
  SELECT event_id, action_name, created_at
  FROM audit_log
  WHERE created_at < CURRENT_DATE - INTERVAL 90 DAY;
~~~

Ví dụ chỉ minh họa cấu trúc. Một event production cần có cơ chế tránh copy lặp, xóa dữ liệu nguồn sau khi lưu trữ thành công, batch size, xử lý lỗi và giám sát. Không chạy event mẫu trên dữ liệu thật nếu chưa bổ sung các điều kiện đó.

Kiểm tra event scheduler và event đã tạo:

~~~sql
SHOW VARIABLES LIKE 'event_scheduler';
SHOW EVENTS FROM appdb;
SHOW CREATE EVENT ev_archive_old_audit;
~~~

Event Scheduler phải được bật thì event mới được thực thi. Việc bật scheduler là cấu hình vận hành riêng; không giả định script `CREATE EVENT` tự bật nó. Trigger, event và routine cũng có definer và quyền cần được quản lý như các đối tượng có mã thực thi.

## 8. Version hóa dữ liệu tham chiếu

Dữ liệu tham chiếu là tập giá trị nhỏ, ổn định và được nhiều phần của ứng dụng dùng chung, ví dụ trạng thái đơn hàng, loại khách hàng, đơn vị đo, mã tiền tệ hoặc mã quốc gia. Các giá trị này cần được version hóa cùng schema vì code thường phụ thuộc vào chúng.

Ưu tiên khóa nghiệp vụ ổn định như `status_code`, thay vì phụ thuộc vào giá trị AUTO_INCREMENT có thể khác giữa môi trường.

~~~sql
CREATE TABLE order_status (
  status_code VARCHAR(24) NOT NULL,
  label VARCHAR(80) NOT NULL,
  sort_order SMALLINT UNSIGNED NOT NULL DEFAULT 0,
  is_terminal BOOLEAN NOT NULL DEFAULT FALSE,
  PRIMARY KEY (status_code)
) ENGINE=InnoDB;
~~~

Nạp các giá trị chuẩn bằng migration:

~~~sql
INSERT INTO order_status
  (status_code, label, sort_order, is_terminal)
VALUES
  ('PENDING', 'Pending', 10, FALSE),
  ('PAID', 'Paid', 20, FALSE),
  ('SHIPPED', 'Shipped', 30, FALSE),
  ('CANCELLED', 'Cancelled', 90, TRUE)
ON DUPLICATE KEY UPDATE
  label = VALUES(label),
  sort_order = VALUES(sort_order),
  is_terminal = VALUES(is_terminal);
~~~

Cú pháp `VALUES(column)` trong nhánh `ON DUPLICATE KEY UPDATE` đã deprecated từ MySQL 8.0.20. Với MySQL 8.0.19 trở lên, có thể dùng row alias:

~~~sql
INSERT INTO order_status
  (status_code, label, sort_order, is_terminal)
VALUES
  ('PENDING', 'Pending', 10, FALSE),
  ('PAID', 'Paid', 20, FALSE)
AS incoming
ON DUPLICATE KEY UPDATE
  label = incoming.label,
  sort_order = incoming.sort_order,
  is_terminal = incoming.is_terminal;
~~~

Chọn cú pháp tương thích với phiên bản MySQL của hệ thống. Ví dụ đầu tiên dễ dùng trên các phiên bản cũ hơn nhưng phát sinh deprecation warning ở các bản mới; ví dụ alias cần MySQL 8.0.19 trở lên.

Upsert giúp migration có thể áp dụng lại mà không tạo bản ghi trùng theo khóa chính. Tuy nhiên, nó cũng cập nhật các cột được chỉ định mỗi khi khóa đã tồn tại. Chỉ dùng cho dữ liệu chuẩn do repository sở hữu. Nếu người dùng hoặc bộ phận vận hành được phép sửa label hay trạng thái trong production, hãy tách phần cấu hình do người dùng quản lý khỏi dữ liệu seed chuẩn.

### Thêm, đổi và ngừng sử dụng mã tham chiếu

- **Thêm mã:** thêm row bằng migration trước khi code bắt đầu ghi mã đó.
- **Đổi nhãn:** cập nhật label nếu mã ổn định và chỉ thay đổi nội dung hiển thị.
- **Đổi ý nghĩa:** tạo mã mới thay vì âm thầm đổi nghĩa mã cũ.
- **Ngừng sử dụng:** đánh dấu `is_active = FALSE` hoặc `is_deprecated = TRUE`; giữ row nếu dữ liệu lịch sử còn tham chiếu.
- **Xóa mã:** chỉ xóa khi chắc chắn không có dữ liệu lịch sử hoặc foreign key tham chiếu và quy tắc nghiệp vụ cho phép.

Không tái sử dụng một mã đã ngừng hoạt động cho ý nghĩa khác. Điều đó làm các báo cáo lịch sử diễn giải sai dữ liệu cũ.

## 9. Triển khai theo mô hình expand–migrate–contract

Khi ứng dụng đang phục vụ người dùng, thay đổi schema nên được chia thành ba giai đoạn:

<text>**Expand** — thêm cấu trúc mới theo cách tương thích ngược.</text>

- Thêm cột nullable, bảng mới, index hoặc routine mới.
- Giữ cấu trúc cũ để phiên bản ứng dụng hiện tại vẫn chạy.
- Deploy code có thể đọc/ghi cấu trúc mới nhưng vẫn tương thích với schema cũ nếu cần.

<text>**Migrate** — chuyển dữ liệu và luồng ứng dụng.</text>

- Backfill dữ liệu theo batch.
- Kiểm tra null, duplicate, foreign key và số lượng.
- Chuyển ứng dụng sang đọc/ghi cấu trúc mới.
- Theo dõi lỗi, lag replication và thời gian truy vấn.

<text>**Contract** — loại bỏ cấu trúc cũ sau khi không còn client sử dụng.</text>

- Xác nhận không còn code hoặc job đọc cột/routine cũ.
- Gỡ cấu trúc cũ trong một migration riêng.
- Theo dõi sau deploy và giữ phương án phục hồi phù hợp.

Ví dụ đổi tên cột `full_name` thành `display_name`: thay vì rename ngay khiến code cũ lỗi, hãy thêm `display_name`, đồng bộ dữ liệu từ `full_name`, phát hành code dùng cột mới, theo dõi rồi mới drop `full_name` ở release sau. Nếu có nhiều phiên bản ứng dụng chạy đồng thời, cần dual-write hoặc một cơ chế đồng bộ được kiểm thử trong giai đoạn chuyển tiếp.

Đối với dữ liệu lớn, backfill theo khoảng khóa chính:

~~~sql
UPDATE customers
SET display_name = full_name
WHERE id >= 1
  AND id < 1001
  AND display_name IS NULL;
~~~

Ứng dụng migration lặp lại câu lệnh theo từng khoảng ID, ghi nhận checkpoint và chỉ chuyển batch tiếp theo sau khi batch trước thành công. Không giữ một transaction duy nhất cho hàng triệu bản ghi nếu điều đó tạo undo log lớn hoặc giữ khóa quá lâu.

## 10. Online DDL, metadata lock và tác động production

Không phải mọi thay đổi DDL đều có cùng chi phí. Tùy thao tác, phiên bản MySQL và cấu trúc bảng, `ALTER TABLE` có thể:

- Thay đổi metadata mà không rebuild dữ liệu.
- Thực hiện tại chỗ nhưng vẫn cần tài nguyên I/O/CPU.
- Rebuild bảng và index.
- Chờ metadata lock từ transaction hoặc truy vấn đang giữ metadata trên bảng.

MySQL có các thuật toán DDL như `INSTANT`, `INPLACE` và `COPY`; khả năng hỗ trợ phụ thuộc từng thao tác và phiên bản. Ví dụ, nếu một thay đổi được hỗ trợ instant, có thể yêu cầu rõ:

~~~sql
ALTER TABLE customers
  ADD COLUMN source_system VARCHAR(32) NULL,
  ALGORITHM=INSTANT;
~~~

Nếu server không hỗ trợ thuật toán đã yêu cầu cho thao tác đó, lệnh sẽ lỗi thay vì tự chuyển sang cách khác. Không suy luận rằng mọi ADD COLUMN đều instant hoặc mọi INPLACE đều không khóa.

Một số thao tác cho phép `LOCK=NONE` để giảm chặn DML trong quá trình thực hiện:

~~~sql
ALTER TABLE customers
  ADD INDEX idx_customers_created_at (created_at),
  ALGORITHM=INPLACE,
  LOCK=NONE;
~~~

Chỉ dùng khi thao tác và phiên bản hỗ trợ. Ngay cả online DDL vẫn có thể cần metadata lock ở đầu/cuối, dùng nhiều tài nguyên và làm tăng replication lag.

Trước migration lớn:

- Kiểm tra dung lượng trống, tốc độ I/O, kích thước bảng và thời gian dự kiến.
- Xác định transaction dài có thể giữ metadata lock.
- Thử trên bản sao có kích thước gần production.
- Chạy trong cửa sổ phù hợp, có timeout và kế hoạch dừng.
- Theo dõi process list, metadata lock, CPU, I/O và replica lag.
- Cân nhắc công cụ online schema change như gh-ost hoặc pt-online-schema-change nếu native DDL không đáp ứng yêu cầu; kiểm tra kỹ foreign key, trigger, replication topology và giới hạn của công cụ.

Có thể kiểm tra metadata lock đang chờ qua Performance Schema:

~~~sql
SELECT
  OBJECT_SCHEMA,
  OBJECT_NAME,
  LOCK_TYPE,
  LOCK_DURATION,
  LOCK_STATUS,
  OWNER_THREAD_ID
FROM performance_schema.metadata_locks
WHERE OBJECT_SCHEMA = DATABASE()
  AND LOCK_STATUS IN ('PENDING', 'GRANTED');
~~~

Kết quả cần được đối chiếu với process list và thread đang giữ lock. Không tự động kill mọi session đang giữ metadata lock; xác định transaction, chủ sở hữu và tác động trước khi xử lý.

## 11. Rollback và phục hồi khi migration lỗi

Không phải migration nào cũng có thể rollback an toàn. Thêm cột nullable thường có thể giữ lại mà không ảnh hưởng code cũ; xóa cột hoặc chuyển đổi dữ liệu mất mát thì khó đảo ngược.

Phân biệt ba khái niệm:

- **Database rollback:** dùng transaction để hoàn tác DML chưa commit; không áp dụng cho phần lớn DDL do implicit commit.
- **Down migration:** script đảo ngược thay đổi schema. Chỉ an toàn nếu dữ liệu và ứng dụng vẫn cho phép đảo ngược.
- **Forward fix:** tạo migration mới sửa trạng thái sai hoặc đưa hệ thống tiến tới trạng thái hợp lệ.

Ví dụ thêm một cột không cần down migration ngay. Nếu code mới gặp lỗi, có thể rollback ứng dụng trong khi giữ cột mới vì code cũ vẫn tương thích. Ngược lại, nếu đã drop cột cũ và phát hiện code cũ vẫn cần nó, phải phục hồi dữ liệu từ backup hoặc tạo migration bổ sung có thể khôi phục dữ liệu.

Trước thay đổi phá hủy:

1. Xác định dữ liệu sẽ mất hoặc biến đổi.
2. Có backup và kiểm tra khả năng restore.
3. Lưu số lượng, checksum hoặc tổng nghiệp vụ trước thay đổi.
4. Xác định cửa sổ triển khai và người chịu trách nhiệm.
5. Có script phục hồi hoặc forward fix đã thử nghiệm.
6. Không xóa migration history để ép runner chạy lại file cũ.

Nếu migration thất bại giữa nhiều câu DDL, kiểm tra schema thực tế và migration history trước khi tiếp tục. Một số DDL có thể đã hoàn tất dù câu lệnh sau đó thất bại. Không chạy lại toàn bộ script một cách mù quáng; xác định chính xác các đối tượng đã được tạo hoặc thay đổi.

## 12. Review và kiểm thử migration trong CI/CD

Pipeline nên kiểm tra migration trước khi triển khai lên database dùng chung:

- Tạo database rỗng với phiên bản MySQL mục tiêu và chạy toàn bộ migration từ đầu.
- Nâng cấp một database ở phiên bản trước để kiểm tra đường migration thực tế.
- Kiểm tra migration không có version trùng, file đã áp dụng không bị sửa và checksum phù hợp.
- Xác minh bảng, cột, index, constraint và stored program sau migration.
- Chạy test cho routine, trigger, event và các truy vấn ứng dụng phụ thuộc.
- Nạp dữ liệu tham chiếu và xác minh mã bắt buộc tồn tại.
- Thử migration với dữ liệu mẫu có duplicate, NULL, khóa ngoại mồ côi và kích thước gần thực tế.
- Kiểm tra thời gian chạy, metadata lock và replication lag trong môi trường staging.

Một truy vấn kiểm tra cột có thể dùng `information_schema.COLUMNS`:

~~~sql
SELECT
  TABLE_NAME,
  COLUMN_NAME,
  COLUMN_TYPE,
  IS_NULLABLE
FROM information_schema.COLUMNS
WHERE TABLE_SCHEMA = DATABASE()
  AND TABLE_NAME = 'customers'
ORDER BY ORDINAL_POSITION;
~~~

Kiểm tra routine:

~~~sql
SHOW CREATE PROCEDURE get_customer_order_count;
SHOW CREATE TRIGGER customers_before_insert;
~~~

Kiểm tra dữ liệu tham chiếu:

~~~sql
SELECT status_code
FROM order_status
ORDER BY sort_order, status_code;
~~~

CI nên kiểm tra kết quả và điều kiện mong đợi, không chỉ xác nhận câu lệnh SQL chạy không lỗi. Với event, không chờ lịch production để kiểm thử; kiểm tra định nghĩa, quyền, trạng thái scheduler và gọi logic nghiệp vụ qua routine/test riêng nếu có thể.

## 13. Những lỗi quản lý schema thường gặp

| Lỗi | Hậu quả | Cách làm tốt hơn |
|---|---|---|
| Sửa schema trực tiếp trên production | Repository không phản ánh trạng thái thực | Mọi thay đổi đi qua migration được review |
| Sửa migration đã áp dụng | Checksum và lịch sử môi trường lệch nhau | Tạo migration mới |
| Gộp DDL và DML rồi kỳ vọng ROLLBACK | Dữ liệu có thể đã commit trước khi script lỗi | Tách bước và thiết kế trạng thái trung gian |
| Xóa cột ngay trong cùng release đổi code | Phiên bản ứng dụng cũ có thể lỗi | Expand–migrate–contract |
| Dùng `IF NOT EXISTS` để che drift | Đối tượng tồn tại nhưng sai định nghĩa | Kiểm tra schema và migration history |
| Drop/create routine không kiểm tra quyền | Procedure có thể mất GRANT hoặc sai DEFINER | Kiểm tra security mode, definer và quyền sau deploy |
| Dùng seed data ghi đè dữ liệu do người dùng sửa | Mất thay đổi vận hành | Phân tách dữ liệu chuẩn và dữ liệu quản trị |
| Chạy DDL lớn không đo trước | Metadata lock, I/O cao và replication lag | Thử trên dữ liệu gần production và theo dõi |
| Chạy hai migration runner cùng lúc | Race condition và schema ở trạng thái khó đoán | Chỉ một tiến trình điều phối migration |
| Rollback bằng cách xóa migration history | Mất dấu trạng thái đã triển khai | Sửa bằng migration mới và ghi nhận rõ ràng |

## 14. Quy trình phát hành schema mẫu

Một release có thay đổi database có thể thực hiện theo trình tự:

1. Developer tạo migration DDL, routine hoặc reference data trong branch.
2. Reviewer kiểm tra tính tương thích, dữ liệu bị ảnh hưởng, quyền và thời gian DDL.
3. CI chạy migration từ database rỗng và nâng cấp từ schema phiên bản trước.
4. Staging chạy thử với dữ liệu đại diện, kiểm tra truy vấn và stored program.
5. Backup hoặc xác nhận điểm phục hồi trước thay đổi phá hủy.
6. Pipeline triển khai migration theo thứ tự trước khi phát hành code cần schema mới.
7. Theo dõi migration history, lỗi ứng dụng, lock, I/O và replica lag.
8. Chuyển code sang dùng cấu trúc mới, backfill và xác minh dữ liệu.
9. Ở release sau, loại bỏ cấu trúc cũ khi không còn client sử dụng.
10. Lưu kết quả phát hành và schema version cùng phiên bản ứng dụng.

Nếu cần triển khai nhiều service dùng chung database, xác định rõ một service hoặc pipeline sở hữu schema. Tránh để nhiều service tự chạy migration cạnh tranh trên cùng database mà không có cơ chế điều phối.

## 15. Ghi nhớ

- DDL, stored program và dữ liệu tham chiếu đều là tài sản cần version control.
- Dùng migration có version, thứ tự rõ ràng và lịch sử triển khai.
- Không sửa migration đã áp dụng; tạo file mới cho thay đổi tiếp theo.
- Phần lớn DDL MySQL gây implicit commit; atomic DDL không đồng nghĩa rollback được bằng transaction.
- Quản lý procedure, function, trigger và event như mã nguồn; kiểm tra delimiter, definer, security mode và GRANT.
- Dữ liệu tham chiếu nên có mã ổn định và migration idempotent; không trộn với dữ liệu nghiệp vụ.
- Dùng expand–migrate–contract để giữ tương thích trong lúc ứng dụng phát hành nhiều phiên bản.
- Online DDL vẫn có thể dùng tài nguyên và chờ metadata lock.
- Chuẩn bị backup, kiểm thử và forward fix cho thay đổi phá hủy.
- CI phải kiểm tra cả schema, routine, dữ liệu tham chiếu và đường nâng cấp từ phiên bản trước.

Version control cho database tạo ra lịch sử thay đổi có thể review và tái tạo. Khi migration được thiết kế theo thứ tự, stored program có quyền thực thi rõ ràng, dữ liệu tham chiếu có khóa ổn định và mỗi release được kiểm tra trên schema thực tế, quá trình phát triển MySQL sẽ dễ kiểm soát hơn giữa các môi trường.

## Tài liệu tham khảo

- [MySQL 8.0 Reference Manual: Statements That Cause an Implicit Commit](https://dev.mysql.com/doc/refman/8.0/en/implicit-commit.html)
- [MySQL 8.0 Reference Manual: Atomic Data Definition Statement Support](https://dev.mysql.com/doc/refman/8.0/en/atomic-ddl.html)
- [MySQL 8.0 Reference Manual: Online DDL](https://dev.mysql.com/doc/refman/8.0/en/innodb-online-ddl.html)
- [MySQL 8.0 Reference Manual: Stored Objects and DEFINER Security](https://dev.mysql.com/doc/refman/8.0/en/stored-objects-security.html)
- [MySQL 8.0 Reference Manual: Event Scheduler](https://dev.mysql.com/doc/refman/8.0/en/events.html)
- [Flyway Documentation: Versioned Migrations](https://documentation.red-gate.com/flyway/flyway-concepts/migrations/versioned-migrations)

