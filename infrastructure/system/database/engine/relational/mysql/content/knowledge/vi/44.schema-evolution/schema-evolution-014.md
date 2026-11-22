# Kiểm chứng dữ liệu, quyền truy cập và kế hoạch quay lui sau migration

Một migration schema chỉ được xem là hoàn tất khi cấu trúc mới đúng, dữ liệu vẫn bảo toàn ý nghĩa, ứng dụng truy cập được bằng đúng quyền và đội vận hành có cách khôi phục nếu phát hiện lỗi. Câu lệnh ALTER TABLE chạy thành công mới chứng minh MySQL đã thực hiện thay đổi cấu trúc; nó không chứng minh dữ liệu được chuyển đổi đúng, truy vấn ứng dụng vẫn tương thích hay quyền truy cập còn phù hợp.

Trong MySQL, nhiều câu lệnh DDL tự commit transaction hiện tại. Vì vậy, không thể coi một loạt ALTER TABLE, backfill và cập nhật ứng dụng là một transaction duy nhất để ROLLBACK khi có sự cố. Kế hoạch quay lui phải được thiết kế trước migration, gồm điểm kiểm tra, dữ liệu dự phòng, cách chuyển ứng dụng về phiên bản cũ và cách xử lý các bản ghi đã phát sinh sau khi cutover.

Bài học sử dụng MySQL 8.4, InnoDB và một quy trình migration triển khai theo từng giai đoạn. Các ví dụ cần được điều chỉnh theo kích thước bảng, workload, topology replication và yêu cầu nghiệp vụ thực tế.

## Mục tiêu

Sau bài học, bạn có thể:

- Xây dựng tiêu chí kiểm chứng cấu trúc, dữ liệu và hành vi ứng dụng trước/sau migration.
- Kiểm tra số lượng bản ghi, giá trị NULL, khóa trùng, dữ liệu mồ côi và kết quả backfill.
- Xác minh quyền của tài khoản migration và tài khoản ứng dụng theo nguyên tắc quyền tối thiểu.
- Hiểu vì sao DDL không thể được rollback như DML và phân biệt atomic DDL với transaction rollback.
- Thiết kế migration theo mô hình expand-contract để giữ tương thích giữa phiên bản ứng dụng cũ và mới.
- Lập kế hoạch rollback, backup/PITR, kiểm tra replica và tiêu chí dừng hoặc tiếp tục triển khai.

## 1. Xác định migration contract trước khi chạy

Mỗi migration cần một bản mô tả ngắn, có thể kiểm tra được. Bản mô tả này là hợp đồng giữa người viết migration, người triển khai, người kiểm thử và người trực vận hành.

| Nội dung | Câu hỏi cần trả lời |
|---|---|
| Mục tiêu | Schema hoặc hành vi dữ liệu nào sẽ thay đổi? Vì sao cần thay đổi? |
| Phạm vi | Database, bảng, cột, index, constraint, view, trigger hoặc routine nào bị ảnh hưởng? |
| Tương thích | Phiên bản ứng dụng hiện tại và phiên bản mới có cùng hoạt động trong giai đoạn chuyển tiếp không? |
| Dữ liệu | Dữ liệu cũ được chuyển đổi theo quy tắc nghiệp vụ nào? Giá trị nào được giữ nguyên, đổi hoặc loại bỏ? |
| Quyền | Tài khoản triển khai cần quyền gì? Tài khoản runtime cần quyền gì sau migration? |
| Tải và khóa | DDL có thể rebuild bảng, giữ metadata lock hoặc tạo tải lớn trong bao lâu? |
| Kiểm chứng | Những truy vấn, số liệu và luồng ứng dụng nào chứng minh migration thành công? |
| Rollback | Có thể chạy migration ngược không? Nếu không, dùng backup/PITR hoặc forward-fix như thế nào? |

Ghi lại phiên bản schema trước và sau, mã migration, checksum của file migration, thời điểm triển khai, người thực hiện và kết quả kiểm tra. Nếu dùng công cụ migration có bảng lịch sử, bảo đảm trạng thái migration trong bảng đó phản ánh đúng kết quả thực tế. Không đánh dấu migration hoàn tất chỉ vì công cụ đã gửi câu lệnh; cần kiểm tra database và ứng dụng sau khi chạy.

## 2. Kiểm tra trước migration

### 2.1. Ghi nhận trạng thái schema hiện tại

Lưu định nghĩa bảng và các đối tượng phụ thuộc trước khi thay đổi:

```sql
SHOW CREATE TABLE app_db.customers\G
SHOW CREATE VIEW app_db.customer_summary\G
SHOW TRIGGERS FROM app_db;
```

Có thể tra cứu metadata có cấu trúc trong INFORMATION_SCHEMA:

```sql
SELECT TABLE_NAME, ENGINE, TABLE_COLLATION
FROM information_schema.TABLES
WHERE TABLE_SCHEMA = 'app_db';

SELECT TABLE_NAME, COLUMN_NAME, COLUMN_TYPE,
       IS_NULLABLE, COLUMN_DEFAULT, EXTRA
FROM information_schema.COLUMNS
WHERE TABLE_SCHEMA = 'app_db'
ORDER BY TABLE_NAME, ORDINAL_POSITION;

SELECT TABLE_NAME, INDEX_NAME, NON_UNIQUE,
       SEQ_IN_INDEX, COLUMN_NAME
FROM information_schema.STATISTICS
WHERE TABLE_SCHEMA = 'app_db'
ORDER BY TABLE_NAME, INDEX_NAME, SEQ_IN_INDEX;
```

Đối chiếu cả index, foreign key, check constraint, trigger, view, stored procedure, function và event có liên quan. Một migration đổi tên hoặc xóa cột có thể làm hỏng view hay routine dù ALTER TABLE vẫn thành công. Lưu kết quả SHOW CREATE hoặc schema dump vào nơi quản lý phiên bản để có thể so sánh sau này.

### 2.2. Đo dữ liệu và workload hiện tại

Lấy số liệu baseline trước khi thay đổi:

```sql
SELECT COUNT(*) AS total_rows,
       SUM(email IS NULL) AS email_nulls,
       COUNT(DISTINCT customer_id) AS distinct_ids
FROM app_db.customers;

SELECT status, COUNT(*) AS row_count
FROM app_db.customers
GROUP BY status
ORDER BY status;
```

Với bảng lớn, các truy vấn COUNT(*), COUNT(DISTINCT ...) hoặc checksum toàn bảng có thể đọc nhiều dữ liệu và tạo tải. Chạy trên replica phù hợp, theo từng khoảng khóa chính hoặc trong cửa sổ ít tải. Không chạy nhiều truy vấn quét toàn bảng đồng thời trên production chỉ để hoàn thành checklist.

Ghi nhận thêm các truy vấn quan trọng, độ trễ p95/p99, tỷ lệ lỗi, số kết nối, replication lag và mức sử dụng CPU/I/O. Sau migration, so sánh với baseline để phát hiện thay đổi hiệu năng hoặc lỗi truy vấn.

### 2.3. Kiểm tra điều kiện của dữ liệu cũ

Trước khi thêm NOT NULL, UNIQUE, CHECK hoặc foreign key, xác định dữ liệu hiện tại có thỏa điều kiện mới hay không.

Tìm giá trị thiếu:

```sql
SELECT COUNT(*) AS missing_email
FROM app_db.customers
WHERE email IS NULL OR TRIM(email) = '';
```

Tìm giá trị trùng trước khi thêm unique index:

```sql
SELECT normalized_email, COUNT(*) AS occurrences
FROM app_db.customers
GROUP BY normalized_email
HAVING COUNT(*) > 1;
```

Tìm bản ghi con không có bản ghi cha trước khi thêm foreign key:

```sql
SELECT o.customer_id, COUNT(*) AS orphan_orders
FROM app_db.orders AS o
LEFT JOIN app_db.customers AS c
  ON c.customer_id = o.customer_id
WHERE o.customer_id IS NOT NULL
  AND c.customer_id IS NULL
GROUP BY o.customer_id;
```

Nếu kết quả có dữ liệu vi phạm, cần thống nhất cách sửa với chủ sở hữu nghiệp vụ. Không tự chọn bản ghi để xóa hoặc gộp chỉ nhằm làm migration chạy qua. Lưu danh sách bản ghi bị ảnh hưởng và kết quả xử lý để có thể đối chiếu.

## 3. Kiểm chứng sau migration

Kiểm chứng nên chia thành ba lớp: cấu trúc, dữ liệu và hành vi. Mỗi lớp cần có kết quả kỳ vọng cụ thể.

### 3.1. Xác nhận cấu trúc mới

Sau DDL, đọc lại định nghĩa bảng:

```sql
SHOW CREATE TABLE app_db.customers\G

SELECT COLUMN_NAME, COLUMN_TYPE, IS_NULLABLE,
       COLUMN_DEFAULT, EXTRA
FROM information_schema.COLUMNS
WHERE TABLE_SCHEMA = 'app_db'
  AND TABLE_NAME = 'customers'
ORDER BY ORDINAL_POSITION;

SELECT INDEX_NAME, NON_UNIQUE, SEQ_IN_INDEX, COLUMN_NAME
FROM information_schema.STATISTICS
WHERE TABLE_SCHEMA = 'app_db'
  AND TABLE_NAME = 'customers'
ORDER BY INDEX_NAME, SEQ_IN_INDEX;
```

Kiểm tra tên, kiểu, độ dài, charset, collation, nullability, default, generated column, index và constraint. Không chỉ kiểm tra cột mới đã xuất hiện; hãy xác nhận index và constraint có đúng thứ tự cột, đúng tên và đúng thuộc tính.

### 3.2. Kiểm tra số lượng và tính đầy đủ

So sánh số lượng bản ghi trước và sau theo cùng điều kiện lọc và cùng mốc dữ liệu. Nếu ứng dụng vẫn ghi trong lúc kiểm tra, số lượng có thể thay đổi tự nhiên; khi đó cần dùng snapshot/cutoff nhất quán, tạm dừng ghi theo kế hoạch hoặc đối chiếu theo tập khóa đã chốt. Nếu migration không được phép thêm hoặc xóa hàng, số lượng tại cùng mốc phải bằng nhau. Nếu có chuyển đổi làm thay đổi số hàng, phải ghi rõ quy tắc và số lượng kỳ vọng.

Ví dụ kiểm tra cột mới đã được backfill:

```sql
SELECT COUNT(*) AS total_rows,
       SUM(status_v2 IS NULL) AS status_v2_nulls
FROM app_db.customers;
```

Kiểm tra phân bố giá trị mới:

```sql
SELECT status_v2, COUNT(*) AS row_count
FROM app_db.customers
GROUP BY status_v2
ORDER BY status_v2;
```

Đối chiếu theo từng khoảng primary key giúp khoanh vùng sai lệch:

```sql
SELECT
  FLOOR(customer_id / 10000) AS id_bucket,
  COUNT(*) AS row_count,
  SUM(status_v2 IS NULL) AS missing_count
FROM app_db.customers
GROUP BY FLOOR(customer_id / 10000)
ORDER BY id_bucket;
```

Chọn kích thước bucket phù hợp với phân bố khóa và kích thước bảng. Nếu khóa không liên tục, bucket theo khoảng có thể không đều; dùng điều kiện customer_id >= ... AND customer_id < ... khi cần kiểm tra một khoảng chính xác.

### 3.3. Kiểm tra giá trị bằng phép so sánh null-safe

Trong MySQL, toán tử <=> so sánh hai giá trị theo cách xử lý NULL an toàn: NULL <=> NULL là đúng. Nó hữu ích khi so sánh giá trị cũ và giá trị mới sau backfill.

Giả sử status_v2 phải tương ứng với ánh xạ từ status:

```sql
SELECT customer_id, status, status_v2
FROM app_db.customers
WHERE NOT (
  status_v2 <=> CASE status
    WHEN 'A' THEN 'ACTIVE'
    WHEN 'I' THEN 'INACTIVE'
    WHEN 'P' THEN 'PENDING'
    ELSE 'UNKNOWN'
  END
)
LIMIT 100;
```

Kết quả mong đợi là không có dòng nào, trừ các trường hợp ngoại lệ đã được quy định trước. Nếu phép ánh xạ có xử lý đặc biệt cho NULL, chuỗi rỗng hoặc mã không hợp lệ, phải thể hiện rõ trong CASE và tiêu chí kiểm chứng.

Với chuyển đổi số hoặc ngày giờ, kiểm tra cả số lượng giá trị không chuyển đổi được và độ lệch. Ví dụ, khi đổi amount_text sang DECIMAL, không chỉ xác nhận không còn chuỗi rỗng; cần xác nhận độ chính xác, dấu thập phân, làm tròn và giới hạn nghiệp vụ.

### 3.4. Kiểm tra constraint và dữ liệu tham chiếu

Sau khi thêm constraint, xác nhận constraint hiện diện:

```sql
SELECT CONSTRAINT_NAME, CONSTRAINT_TYPE
FROM information_schema.TABLE_CONSTRAINTS
WHERE CONSTRAINT_SCHEMA = 'app_db'
  AND TABLE_NAME = 'orders';

SELECT CONSTRAINT_NAME, COLUMN_NAME,
       REFERENCED_TABLE_NAME, REFERENCED_COLUMN_NAME
FROM information_schema.KEY_COLUMN_USAGE
WHERE TABLE_SCHEMA = 'app_db'
  AND TABLE_NAME = 'orders';
```

Thử các thao tác hợp lệ và không hợp lệ trong môi trường kiểm thử để xác nhận constraint được thực thi như mong muốn. Với check constraint, MySQL thực thi kiểm tra từ MySQL 8.0.16 trở lên; kiểm tra đúng phiên bản và định nghĩa constraint trên máy chủ thực tế.

Không dùng SET foreign_key_checks = 0 như cách thay thế cho kiểm chứng. Khi tắt kiểm tra foreign key, MySQL không xác minh lại các hàng đã nạp khi bật lại biến. Nếu đã nạp dữ liệu khi tắt kiểm tra, cần tự chạy truy vấn tìm bản ghi mồ côi trước khi coi dữ liệu là hợp lệ.

### 3.5. Kiểm tra replica và hiệu năng

Nếu hệ thống dùng asynchronous replication, xác nhận DDL và dữ liệu đã áp dụng trên các replica cần thiết trước khi chuyển traffic đọc hoặc thực hiện bước contract tiếp theo. Kiểm tra:

```sql
SHOW REPLICA STATUS\G
```

Đối với Group Replication, dùng trạng thái thành viên và các bảng Performance Schema của recovery/applier để kiểm tra; SHOW REPLICA STATUS không phải phép kiểm tra tổng quát cho channel nội bộ của Group Replication. Không đánh giá replica chỉ dựa vào một con số lag; cần xác nhận truy vấn đọc trên replica trả về schema và dữ liệu tương ứng với source.

Chạy lại các truy vấn trọng yếu và kiểm tra EXPLAIN/EXPLAIN ANALYZE trong môi trường phù hợp. So sánh thời gian, số hàng ước lượng/thực tế và index được chọn. EXPLAIN ANALYZE thực thi truy vấn thật, nên chỉ dùng với truy vấn đọc có giới hạn và môi trường đã đánh giá tải.

## 4. Kiểm tra quyền truy cập sau migration

Thay đổi schema thường kéo theo thay đổi quyền. Ví dụ, ứng dụng cần đọc cột mới, tài khoản báo cáo cần truy cập view mới hoặc routine được tạo với một DEFINER khác. Migration có thể thành công trong khi ứng dụng lỗi Access denied vì tài khoản runtime không có quyền trên đối tượng mới.

### 4.1. Tách tài khoản migration và runtime

Nên dùng các tài khoản có vai trò riêng:

| Tài khoản | Quyền điển hình |
|---|---|
| Migration/deployment | Chỉ các quyền DDL cần cho thay đổi cụ thể như ALTER, CREATE, INDEX; quyền DML nếu phải backfill. Quyền cần thiết còn tùy thao tác và đối tượng được tạo. |
| Ứng dụng runtime | Chỉ quyền DML trên bảng/view cần dùng như SELECT, INSERT, UPDATE, DELETE. |
| Báo cáo/analytics | Thường chỉ SELECT trên view hoặc bảng được phép đọc. |
| Backup/restore | Quyền cần thiết cho công cụ backup, export hoặc restore; không dùng làm tài khoản ứng dụng. |

Không cấp ALL PRIVILEGES ON *.* cho tài khoản migration hoặc runtime chỉ để tránh lỗi quyền. Xác định quyền tối thiểu theo từng câu lệnh và đối tượng mà migration thực sự sử dụng. Nếu cần tạo trigger, routine, view hoặc foreign key, kiểm tra thêm quyền đặc thù tương ứng theo tài liệu MySQL của phiên bản triển khai.

### 4.2. Kiểm tra đúng tài khoản và quyền đã cấp

MySQL xác định tài khoản theo cặp user/host. Cùng username nhưng host khác có thể có bộ quyền khác nhau. Trong kết nối ứng dụng, kiểm tra:

```sql
SELECT USER() AS connection_identity,
       CURRENT_USER() AS privilege_account,
       CURRENT_ROLE() AS active_roles;

SHOW GRANTS;
```

USER() cho biết danh tính kết nối mà client gửi; CURRENT_USER() cho biết tài khoản MySQL được dùng để kiểm tra quyền. CURRENT_ROLE() cho biết các role đang active trong phiên. Khi kiểm tra tài khoản cụ thể từ phiên quản trị:

```sql
SHOW GRANTS FOR 'app_runtime'@'10.20.30.%';
SHOW GRANTS FOR 'report_reader'@'10.20.40.%';
```

Nếu quyền được cấp thông qua role, xác nhận role đã được cấp và đang active theo default role hoặc SET ROLE. Một role được cấp nhưng không active có thể không đóng góp quyền vào phiên hiện tại. Không chỉ nhìn tên role trong SHOW GRANTS; hãy kiểm tra CURRENT_ROLE() trên kết nối ứng dụng thực tế.

### 4.3. Kiểm tra quyền trên đối tượng mới

Sau khi tạo bảng hoặc view mới, cấp đúng quyền cho đúng tài khoản:

```sql
GRANT SELECT ON app_db.customer_summary
TO 'report_reader'@'10.20.40.%';

GRANT SELECT, INSERT, UPDATE ON app_db.customer_preferences
TO 'app_runtime'@'10.20.30.%';
```

Ví dụ trên chỉ minh họa phạm vi quyền. Không cấp INSERT hoặc UPDATE nếu ứng dụng chỉ cần đọc. Khi dùng view, kiểm tra SQL SECURITY DEFINER hay SQL SECURITY INVOKER, tài khoản DEFINER có tồn tại và có quyền cần thiết hay không. Một view chạy dưới quyền definer có thể hoạt động khác view chạy dưới quyền invoker.

Nếu migration đổi tên bảng/cột hoặc thay view, kiểm tra các đối tượng phụ thuộc: trigger, stored routine, event, view khác và tài khoản báo cáo. Quyền trên bảng cũ không tự động có nghĩa tài khoản đã có quyền trên đối tượng mới.

### 4.4. Kiểm thử bằng đúng tài khoản runtime

Không xác nhận quyền chỉ bằng tài khoản DBA. Kết nối bằng chính tài khoản ứng dụng hoặc một tài khoản kiểm thử có cùng grants/roles, rồi chạy các thao tác quan trọng:

```sql
-- Kiểm tra truy vấn ứng dụng cần thực hiện.
SELECT customer_id, status_v2
FROM app_db.customers
WHERE customer_id = 1001;

-- Kiểm tra quyền ghi nếu ứng dụng có cập nhật.
UPDATE app_db.customer_preferences
SET preference_value = 'email'
WHERE customer_id = 1001;
```

Trong môi trường kiểm thử, dùng transaction và rollback cho thao tác DML khi có thể. Không chạy câu lệnh ghi thử trên production nếu chưa có dữ liệu kiểm thử và quy trình hoàn nguyên rõ ràng. Kiểm tra cả các luồng bị từ chối theo thiết kế, ví dụ tài khoản báo cáo không thể ghi vào bảng nghiệp vụ.

## 5. Hiểu giới hạn rollback của DDL trong MySQL

### 5.1. DDL thường implicit commit

Nhiều câu lệnh DDL như ALTER TABLE, CREATE TABLE, DROP TABLE, CREATE INDEX và DROP INDEX gây implicit commit. Điều đó có nghĩa transaction đang mở có thể được commit trước khi DDL chạy; sau đó không thể dùng ROLLBACK để đảo ngược thay đổi schema như đối với DML.

Ví dụ:

```sql
START TRANSACTION;

UPDATE app_db.customers
SET status = 'I'
WHERE customer_id = 1001;

ALTER TABLE app_db.customers
  ADD COLUMN migrated_at DATETIME NULL;

ROLLBACK;
```

Không được giả định câu ROLLBACK ở cuối sẽ hoàn tác cả ALTER TABLE và câu UPDATE trước đó. DDL gây implicit commit nên transaction có thể đã được commit trước khi DDL thực thi. Hãy tách migration schema và transaction dữ liệu thành các bước có kế hoạch riêng.

### 5.2. Atomic DDL không phải transaction rollback

MySQL hỗ trợ atomic DDL cho nhiều thao tác trên các storage engine được hỗ trợ. Atomic DDL giúp thao tác DDL được thực hiện theo cơ chế crash-safe: nếu máy chủ gặp sự cố trong lúc DDL, MySQL phục hồi trạng thái để thao tác được hoàn tất hoặc được rollback ở mức nội bộ.

Điều này không có nghĩa người dùng có thể gọi ROLLBACK sau khi ALTER TABLE thành công để quay về schema cũ. Atomic DDL bảo vệ tính toàn vẹn khi thực thi DDL; nó không biến DDL thành một phần của transaction nghiệp vụ có thể rollback tùy ý.

### 5.3. Online DDL vẫn có thể ảnh hưởng production

Một số thao tác ALTER TABLE hỗ trợ ALGORITHM=INSTANT, ALGORITHM=INPLACE hoặc LOCK=NONE; phạm vi hỗ trợ phụ thuộc loại thay đổi, phiên bản MySQL và storage engine. INSTANT tránh rebuild bảng cho các thao tác được hỗ trợ, nhưng không phải mọi thay đổi đều có thể dùng. INPLACE không nhất thiết có nghĩa là không rebuild hoặc không tốn I/O.

Ví dụ yêu cầu MySQL dùng instant algorithm nếu thao tác hỗ trợ:

```sql
ALTER TABLE app_db.customers
  ADD COLUMN migrated_at DATETIME NULL,
  ALGORITHM=INSTANT;
```

Nếu thao tác không hỗ trợ algorithm đã yêu cầu, MySQL sẽ báo lỗi thay vì âm thầm chọn một algorithm khác. Điều này hữu ích để tránh bất ngờ về rebuild, nhưng cần thử trước trên phiên bản và schema tương ứng.

Ngay cả online DDL vẫn cần metadata lock ở các giai đoạn nhất định. Transaction dài hoặc truy vấn đang giữ metadata lock có thể khiến DDL chờ; một DDL chờ lâu cũng có thể làm các truy vấn mới xếp hàng phía sau. Trước khi migration, kiểm tra transaction dài, process list và metadata lock:

```sql
SELECT *
FROM performance_schema.metadata_locks
WHERE OBJECT_SCHEMA = 'app_db'
  AND OBJECT_NAME = 'customers';

SHOW FULL PROCESSLIST;
```

Không hủy session hoặc kill query chỉ dựa trên thời gian chạy. Xác định chủ sở hữu, transaction và tác động đến ứng dụng trước khi can thiệp. Với bảng lớn, thử DDL trên bản sao có kích thước gần production và đo thời gian, I/O, lock, dung lượng tạm và replication lag.

## 6. Thiết kế migration theo expand-contract

Expand-contract chia một thay đổi lớn thành nhiều bước nhỏ, giữ ứng dụng cũ và mới cùng hoạt động trong giai đoạn chuyển tiếp. Đây là cách giảm rủi ro khi cần đổi tên cột, thay định dạng dữ liệu hoặc chuyển logic đọc/ghi.

Giả sử cột status hiện lưu mã ngắn A, I, P; phiên bản ứng dụng mới cần cột status_v2 với giá trị ACTIVE, INACTIVE, PENDING.

### Giai đoạn 1: Expand

Thêm cột mới có thể null để ứng dụng cũ vẫn hoạt động:

```sql
ALTER TABLE app_db.customers
  ADD COLUMN status_v2 VARCHAR(20) NULL,
  ALGORITHM=INSTANT;
```

Kiểm tra cấu trúc và cấp quyền cho tài khoản runtime nếu quyền được giới hạn theo cột hoặc theo view. Chưa xóa cột cũ; phiên bản ứng dụng hiện tại vẫn tiếp tục đọc/ghi status.

### Giai đoạn 2: Dual-write và backfill

Triển khai phiên bản ứng dụng có thể ghi đồng thời status và status_v2, hoặc dùng một cơ chế đồng bộ tạm thời đã được kiểm thử. Chỉ bật dual-write sau khi cột mới tồn tại trên tất cả máy chủ có thể phục vụ traffic. Trong giai đoạn rolling deployment, mọi phiên bản hoặc job còn ghi status phải được nâng cấp để ghi cả hai cột, hoặc phải được drain trước khi dựa vào status_v2; nếu writer cũ chỉ cập nhật status, giá trị mới có thể bị lệch so với status_v2.

Backfill theo từng batch dựa trên khóa chính để giới hạn transaction và lock:

```sql
UPDATE app_db.customers
SET status_v2 = CASE status
  WHEN 'A' THEN 'ACTIVE'
  WHEN 'I' THEN 'INACTIVE'
  WHEN 'P' THEN 'PENDING'
  ELSE 'UNKNOWN'
END
WHERE customer_id > 0
  AND customer_id <= 10000
  AND status_v2 IS NULL;
```

Lặp lại với các khoảng customer_id tiếp theo. Kích thước batch phải dựa trên thời gian transaction, tải I/O, lock contention và replication lag. Không chạy một UPDATE toàn bảng trong transaction lớn nếu chưa đo tác động.

Nếu ứng dụng vẫn có thể thay đổi status trong lúc backfill, dual-write phải được triển khai trước hoặc backfill phải có cơ chế tránh ghi đè giá trị mới hơn. Ghi nhận checkpoint của batch đã hoàn tất để có thể tiếp tục sau khi job bị gián đoạn.

### Giai đoạn 3: Validate

Kiểm tra số lượng và ánh xạ:

```sql
SELECT COUNT(*) AS total_rows,
       SUM(status_v2 IS NULL) AS missing_status
FROM app_db.customers;

SELECT COUNT(*) AS mismatched_rows
FROM app_db.customers
WHERE NOT (
  status_v2 <=> CASE status
    WHEN 'A' THEN 'ACTIVE'
    WHEN 'I' THEN 'INACTIVE'
    WHEN 'P' THEN 'PENDING'
    ELSE 'UNKNOWN'
  END
);
```

Kết quả mong đợi là missing_status = 0 và mismatched_rows = 0, nếu đó là quy tắc nghiệp vụ đã thống nhất. Kiểm tra thêm phân bố từng trạng thái, dữ liệu ngoài miền cho phép và các truy vấn ứng dụng mới.

### Giai đoạn 4: Switch

Triển khai phiên bản ứng dụng đọc status_v2. Giữ dual-write trong thời gian quan sát để có thể chuyển ứng dụng về đọc cột cũ nếu phát hiện lỗi. Theo dõi lỗi, latency, tỷ lệ giá trị null và khác biệt giữa hai cột.

Chỉ chuyển traffic hoàn toàn sau khi mọi instance ứng dụng đã tương thích và mọi replica cần phục vụ đọc đã áp dụng migration. Nếu dùng nhiều phiên bản ứng dụng trong quá trình rolling deployment, phải bảo đảm phiên bản cũ không ghi đè dữ liệu của phiên bản mới.

### Giai đoạn 5: Contract

Sau thời gian quan sát đủ dài và xác nhận không còn ứng dụng nào phụ thuộc cột cũ, mới thực hiện bước contract:

```sql
-- Ghi lại đầy đủ DEFAULT, COMMENT, CHARACTER SET và COLLATE hiện có nếu có.
ALTER TABLE app_db.customers
  MODIFY COLUMN status_v2 VARCHAR(20) NOT NULL;

-- Chỉ thực hiện ở migration riêng sau khi đã xác minh không còn consumer.
ALTER TABLE app_db.customers
  DROP COLUMN status;
```

Đây là bước có rủi ro cao hơn vì DROP COLUMN làm mất dữ liệu cũ. Không gộp bước contract vào cùng lần triển khai với bước expand. Lưu backup/schema snapshot và xác nhận rollback path trước khi xóa cột.

## 7. Lập kế hoạch rollback theo từng giai đoạn

Rollback phải trả lời hai câu hỏi: làm thế nào đưa ứng dụng về trạng thái hoạt động an toàn, và làm thế nào bảo toàn các dữ liệu đã phát sinh sau migration. Chỉ đảo ngược DDL không giải quyết được câu hỏi thứ hai.

### 7.1. Phân loại khả năng quay lui

| Loại thay đổi | Khả năng quay lui | Cách xử lý |
|---|---|---|
| Thêm cột nullable chưa dùng | Thường dễ | Dừng ứng dụng mới; có thể giữ cột hoặc drop sau khi xác nhận không có dữ liệu cần giữ. |
| Thêm index | Thường có thể | Drop index nếu ảnh hưởng hiệu năng hoặc kế hoạch triển khai; kiểm tra truy vấn phụ thuộc. |
| Backfill cột mới | Có thể nếu cột cũ còn nguyên | Chuyển ứng dụng về cột cũ; giữ cột mới để điều tra hoặc xóa sau. |
| Đổi kiểu dữ liệu có mất độ chính xác | Có thể không đảo ngược | Cần bản sao dữ liệu gốc hoặc phục hồi/PITR. |
| Xóa cột/bảng | Không thể khôi phục bằng DDL ngược | Restore backup/PITR hoặc lấy dữ liệu từ bản sao khác. |
| Gộp/xóa bản ghi trùng | Có thể mất thông tin | Lưu mapping và bản ghi nguồn trước khi gộp; khôi phục theo quy tắc nghiệp vụ. |

Một migration ngược chỉ an toàn nếu dữ liệu được tạo sau migration vẫn có thể biểu diễn đầy đủ trong schema cũ. Ví dụ, nếu status_v2 có giá trị mới mà status cũ không có mã tương ứng, chuyển ngược sẽ làm mất ý nghĩa dữ liệu.

### 7.2. Chuẩn bị backup và điểm phục hồi

Trước migration có rủi ro, bảo đảm có backup đã kiểm tra khả năng restore. Ghi nhận:

- Thời điểm backup và phạm vi database/table.
- Binary log file/position hoặc GTID metadata tương ứng.
- Thời gian lưu binary log đủ cho PITR.
- Nơi lưu backup, quyền truy cập và khả năng giải mã nếu backup được mã hóa.
- Thời gian dự kiến để restore và kiểm chứng.

Không chỉ kiểm tra file backup tồn tại. Thực hiện restore thử trên môi trường cô lập và kiểm tra dữ liệu, schema, tài khoản/privilege cần thiết. Backup chưa từng restore thử không phải bằng chứng chắc chắn rằng hệ thống có thể phục hồi đúng hạn.

Với PITR, khôi phục backup lên instance riêng rồi phát lại binary log đến trước giao dịch gây lỗi. Không restore đè production ngay khi chưa xác định phạm vi dữ liệu cần giữ. Nếu ứng dụng tiếp tục ghi sau migration, việc quay về snapshot cũ sẽ làm mất các giao dịch hợp lệ phát sinh sau thời điểm snapshot trừ khi chúng được replay hoặc reconcile.

### 7.3. Rollback ứng dụng và schema

Trong mô hình expand-contract:

1. Nếu ứng dụng mới lỗi trước khi contract, chuyển traffic về phiên bản cũ và cho ứng dụng tiếp tục đọc cột cũ.
2. Giữ dual-write nếu cần duy trì đồng bộ hai cột trong thời gian rollback.
3. Kiểm tra các bản ghi được tạo/cập nhật sau cutover; xác nhận cột cũ vẫn có giá trị tương đương.
4. Nếu cột mới chứa dữ liệu không biểu diễn được ở schema cũ, không rollback ứng dụng một cách mù quáng; thực hiện mapping hoặc forward-fix.
5. Chỉ drop cột mới sau khi đã xác nhận không cần điều tra hoặc khôi phục.

Nếu migration đã xóa hoặc ghi đè dữ liệu không thể khôi phục bằng logic ngược, dừng ghi theo kế hoạch sự cố, restore vào môi trường riêng, replay log đến điểm an toàn và đối chiếu các giao dịch sau điểm đó. Quyết định cutover lại cần có người chịu trách nhiệm dữ liệu nghiệp vụ xác nhận.

### 7.4. Forward-fix có thể an toàn hơn rollback

Không phải lỗi nào cũng nên quay về schema cũ. Nếu DDL đã hoàn tất, dữ liệu mới đã được ghi và schema mới vẫn có thể hỗ trợ ứng dụng, một migration sửa tiếp (forward-fix) thường giảm rủi ro mất dữ liệu. Ví dụ, thêm index còn thiếu, sửa mapping backfill hoặc cấp quyền còn thiếu có thể xử lý trực tiếp mà không phải khôi phục toàn bộ database.

Chọn rollback khi có một đường quay lui đã kiểm chứng và dữ liệu sau migration có thể được bảo toàn. Chọn forward-fix khi schema hiện tại vẫn là nền tảng an toàn và lỗi có thể được sửa bằng thay đổi bổ sung. Ghi lại quyết định, người phê duyệt và các bước kiểm tra trước khi thực hiện.

## 8. Kiểm soát tiến độ và điều kiện dừng migration

Migration production nên có các điểm kiểm soát rõ ràng. Ví dụ:

| Điểm kiểm tra | Tiếp tục khi | Dừng/điều tra khi |
|---|---|---|
| Trước DDL | Backup/restore đã kiểm chứng; replica khỏe; không có transaction dài gây lock | Backup không dùng được, replication lag cao, metadata lock bất thường |
| Sau DDL | Schema đúng; thời gian và lock trong giới hạn | DDL thất bại, ứng dụng bị block, replica SQL thread dừng |
| Sau backfill | Số dòng và mapping khớp; lỗi dữ liệu trong ngưỡng đã định | Có mismatch, null ngoài dự kiến, duplicate hoặc dữ liệu mồ côi |
| Sau cấp quyền | Runtime account chạy được luồng hợp lệ và bị chặn ở luồng không được phép | Access denied, role không active, quyền vượt phạm vi |
| Sau cutover | Error rate và latency trong ngưỡng; replica bắt kịp | Lỗi tăng, truy vấn chậm, dữ liệu đọc khác source |
| Trước contract | Không còn consumer cũ; rollback window đã kết thúc; backup mới sẵn sàng | Còn phiên bản cũ hoặc job phụ thuộc cột cũ |

Đặt ngưỡng số cụ thể cho hệ thống, chẳng hạn replication lag tối đa, error rate, latency và thời gian lock. Không dùng các giá trị ví dụ chung cho mọi workload. Khi một điều kiện dừng bị chạm, tạm dừng giai đoạn tiếp theo, giữ lại log và trạng thái hiện tại để điều tra.

## 9. Ghi nhận migration và bằng chứng kiểm chứng

Một migration có thể chạy lại hoặc tiếp tục sau gián đoạn chỉ khi biết bước nào đã hoàn tất. Ghi nhận tối thiểu:

- Migration ID, checksum và phiên bản ứng dụng.
- Thời điểm bắt đầu/kết thúc từng giai đoạn.
- DDL đã chạy và kết quả.
- Số dòng trước/sau, số dòng backfill, số lỗi và số bản ghi bị loại.
- GTID hoặc binlog coordinates ở các mốc cần thiết.
- Quyền trước/sau và tài khoản đã kiểm thử.
- Trạng thái replica, lỗi và lag.
- Người thực hiện, người xác nhận và quyết định rollback/forward-fix nếu có.

Ví dụ một bảng lịch sử migration đơn giản:

```sql
CREATE TABLE IF NOT EXISTS ops_schema_migrations (
    migration_id VARCHAR(120) NOT NULL PRIMARY KEY,
    checksum     CHAR(64) NOT NULL,
    started_at   DATETIME NOT NULL,
    finished_at  DATETIME NULL,
    status       ENUM('RUNNING', 'SUCCEEDED', 'FAILED', 'ROLLED_BACK')
                 NOT NULL,
    applied_by   VARCHAR(255) NOT NULL,
    notes        TEXT NULL
) ENGINE = InnoDB;
```

Bảng ví dụ này chỉ là nhật ký vận hành; không thay thế công cụ migration hoặc hệ thống audit. Cập nhật trạng thái sau khi đã xác minh database, không đánh dấu SUCCEEDED nếu bước kiểm chứng dữ liệu hoặc quyền chưa đạt.

## 10. Quy trình thực hành: migration có thể quay lui

Giả sử cần thêm status_v2 vào customers và chuyển ứng dụng từ status sang cột mới.

### Trước khi triển khai

1. Lưu SHOW CREATE TABLE, index, constraint, trigger, view và grants liên quan.
2. Ghi baseline số dòng, phân bố status, giá trị null và truy vấn ứng dụng quan trọng.
3. Xác nhận backup đã restore thử; ghi GTID/binlog metadata và thời gian lưu log.
4. Kiểm tra transaction dài, metadata lock, replication health và dung lượng đĩa.
5. Chuẩn bị phiên bản ứng dụng có dual-write và kế hoạch chuyển về cột cũ.

### Trong khi triển khai

1. Thêm cột nullable bằng DDL đã thử trên phiên bản MySQL tương ứng.
2. Đọc lại SHOW CREATE TABLE và kiểm tra metadata.
3. Cấp quyền cần thiết cho tài khoản runtime; kiểm tra grants và role active.
4. Triển khai dual-write, sau đó backfill theo batch có checkpoint.
5. Kiểm tra null count, mapping, phân bố dữ liệu, khóa trùng và replica lag.
6. Chuyển ứng dụng đọc cột mới theo từng nhóm traffic; theo dõi lỗi và latency.

### Sau khi triển khai

1. Chạy smoke test bằng tài khoản runtime thực tế.
2. Đối chiếu dữ liệu source/replica và các truy vấn nghiệp vụ.
3. Giữ cột cũ và dual-write trong rollback window đã thống nhất.
4. Khi hết rollback window, xác nhận không còn consumer cũ và tạo backup/snapshot phù hợp.
5. Thực hiện contract trong một migration riêng; kiểm tra lại schema, quyền và ứng dụng.
6. Lưu kết quả migration và bằng chứng kiểm chứng vào hệ thống quản lý thay đổi.

## 11. Lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| DDL chạy thành công nhưng ứng dụng lỗi | Tài khoản runtime thiếu quyền hoặc ứng dụng chưa tương thích schema | Kiểm tra CURRENT_USER(), CURRENT_ROLE(), SHOW GRANTS và smoke test bằng tài khoản ứng dụng. |
| Không rollback được ALTER TABLE | DDL đã implicit commit | Dùng migration ngược có kiểm soát, forward-fix hoặc backup/PITR. |
| Migration bị chờ lâu | Transaction khác đang giữ metadata lock | Xác định session giữ lock và xử lý theo chủ sở hữu/workload. |
| Backfill thiếu hoặc sai dữ liệu | Batch bị bỏ sót, mapping sai hoặc dual-write chưa đồng bộ | Dùng checkpoint, null count, phép so sánh null-safe và kiểm tra theo khoảng khóa. |
| Thêm unique index thất bại | Dữ liệu hiện có bị trùng | Báo cáo duplicate, thống nhất cách xử lý nghiệp vụ rồi mới tạo index. |
| Thêm foreign key thất bại | Có orphan rows hoặc kiểu/collation khóa không tương thích | Tìm và xử lý dữ liệu mồ côi; so sánh kiểu cột và index hai phía. |
| Replica chậm sau DDL/backfill | DDL hoặc batch tạo tải lớn | Giảm batch, điều tiết tốc độ, chờ replica bắt kịp trước giai đoạn tiếp theo. |
| Rollback ứng dụng nhưng dữ liệu mới không đọc được | Cột mới chứa giá trị không biểu diễn trong schema cũ | Mapping ngược có kiểm soát hoặc forward-fix; không drop cột mới. |
| Migration chạy lại tạo lỗi | Script không idempotent hoặc trạng thái migration không rõ | Kiểm tra schema và migration journal trước khi chạy lại; viết bước kiểm tra trạng thái rõ ràng. |

## 12. Checklist triển khai

- [ ] Migration ID, checksum và mục tiêu đã được ghi nhận.
- [ ] Schema, index, constraint, trigger, view và routine phụ thuộc đã được kiểm tra.
- [ ] Baseline dữ liệu và workload đã được lưu.
- [ ] Dữ liệu cũ thỏa điều kiện mới hoặc có kế hoạch làm sạch được phê duyệt.
- [ ] Backup đã restore thử; PITR và binary log retention đáp ứng yêu cầu.
- [ ] DDL đã được thử trên phiên bản và schema tương ứng; algorithm/lock đã được đánh giá.
- [ ] Tài khoản migration và runtime có quyền tối thiểu phù hợp.
- [ ] Đã thử quyền bằng tài khoản runtime thực tế, bao gồm role active.
- [ ] Backfill có batch, checkpoint, retry và cách đối chiếu.
- [ ] Tiêu chí dừng migration và người quyết định đã rõ.
- [ ] Ứng dụng cũ/mới tương thích trong giai đoạn expand-contract.
- [ ] Rollback hoặc forward-fix đã được viết và diễn tập.
- [ ] Sau migration đã kiểm tra schema, dữ liệu, quyền, replica và hiệu năng.
- [ ] Bằng chứng và trạng thái migration đã được lưu.

## 13. Bài tập tự kiểm tra

1. Vì sao ROLLBACK không thể hoàn tác một câu ALTER TABLE đã thành công?
2. Atomic DDL khác gì transaction rollback?
3. Trước khi thêm unique index vào cột email, cần kiểm tra dữ liệu nào?
4. Vì sao cần thử quyền bằng đúng tài khoản runtime thay vì tài khoản DBA?
5. Trong expand-contract, tại sao chưa nên drop cột cũ ngay sau khi ứng dụng mới bắt đầu đọc cột mới?
6. Nếu cột mới chứa giá trị không thể biểu diễn trong schema cũ, rollback ứng dụng cần xử lý thế nào?
7. Vì sao bật lại foreign_key_checks không tự kiểm tra lại các bản ghi đã nạp khi tắt kiểm tra?
8. Khi DDL chờ metadata lock, cần điều tra những gì trước khi kill session?

**Gợi ý đáp án:** (1) DDL thường gây implicit commit; thay đổi schema đã được commit độc lập. (2) Atomic DDL bảo đảm thao tác DDL crash-safe ở mức nội bộ, còn transaction rollback cho phép hoàn tác các thay đổi transactional chưa commit. (3) Các nhóm giá trị trùng sau chuẩn hóa, bao gồm khác biệt hoa/thường, khoảng trắng và quy tắc collation. (4) DBA có quyền rộng nên không phản ánh quyền thực tế của ứng dụng; cần kiểm tra đúng user/host và role active. (5) Phiên bản ứng dụng cũ, job hoặc báo cáo có thể còn phụ thuộc cột cũ; giữ cột giúp rollback. (6) Mapping ngược có kiểm soát hoặc forward-fix; không xóa dữ liệu mới chỉ để ép rollback. (7) MySQL không tự quét lại các hàng cũ khi bật biến; phải tự tìm orphan rows. (8) Xác định transaction giữ metadata lock, chủ sở hữu, truy vấn đang chạy và tác động của việc kill đến dữ liệu/nghiệp vụ.

## Tài liệu tham khảo

- [MySQL 8.4 Reference Manual: Implicit Commit](https://dev.mysql.com/doc/refman/8.4/en/implicit-commit.html)
- [MySQL 8.4 Reference Manual: Atomic Data Definition Statement Support](https://dev.mysql.com/doc/refman/8.4/en/atomic-ddl.html)
- [MySQL 8.4 Reference Manual: Online DDL](https://dev.mysql.com/doc/refman/8.4/en/innodb-online-ddl.html)
- [MySQL 8.4 Reference Manual: Metadata Locking](https://dev.mysql.com/doc/refman/8.4/en/metadata-locking.html)
- [MySQL 8.4 Reference Manual: The INFORMATION_SCHEMA COLUMNS Table](https://dev.mysql.com/doc/refman/8.4/en/information-schema-columns-table.html)
- [MySQL 8.4 Reference Manual: Privileges Provided by MySQL](https://dev.mysql.com/doc/refman/8.4/en/privileges-provided.html)
- [MySQL 8.4 Reference Manual: Foreign Key Constraints](https://dev.mysql.com/doc/refman/8.4/en/create-table-foreign-keys.html)
