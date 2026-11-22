# Thay đổi schema

## DDL implicit commit và thiết kế chịu lỗi từng phần

Thay đổi schema MySQL thường được triển khai bằng các câu lệnh DDL như tạo bảng, thêm cột, đổi kiểu dữ liệu, tạo index hoặc thêm constraint. Khác với nhiều thao tác DML, phần lớn DDL quan trọng có thể gây implicit commit: transaction đang mở được commit trước khi câu lệnh chạy. Vì vậy, đặt nhiều câu DDL trong một transaction rồi gọi ROLLBACK không thể đưa schema trở lại trạng thái ban đầu.

Trong module **DATABASE_MYSQL**, bạn học cách làm chủ MySQL từ thiết kế bảng, kiểu dữ liệu, khóa và truy vấn SQL đến index, transaction và kiểm soát đồng thời. Bạn cũng thực hành đọc kế hoạch thực thi, tối ưu truy vấn, phân quyền, sao lưu và xử lý các vấn đề vận hành cơ sở dữ liệu quan hệ. Những kỹ năng này giúp bạn lập kế hoạch thay đổi schema mà vẫn giữ dữ liệu nhất quán, kiểm soát khóa metadata, giảm thời gian gián đoạn và khôi phục được khi một bước migration thất bại.

Bài này giải thích implicit commit, atomic DDL và giới hạn của chúng; sau đó xây dựng cách tổ chức migration nhiều bước để chịu được lỗi giữa chừng. Trọng tâm là ghi nhận trạng thái, kiểm tra điều kiện trước/sau mỗi DDL, triển khai theo mô hình expand-contract và chọn phương án sửa tiếp an toàn khi một phần migration đã hoàn tất.

### 1. DDL và implicit commit

DDL (Data Definition Language) thay đổi định nghĩa đối tượng database. Những câu lệnh thường gặp gồm:

- CREATE TABLE, ALTER TABLE, DROP TABLE.
- RENAME TABLE, TRUNCATE TABLE.
- CREATE INDEX, DROP INDEX.
- CREATE DATABASE, DROP DATABASE.
- Các thao tác tạo hoặc thay đổi view, routine, trigger và event.

Nhiều câu lệnh DDL trong MySQL gây implicit commit. Điều này có hai hệ quả:

1. Nếu session đang có transaction DML chưa commit, DDL có thể commit transaction đó trước khi thực hiện.
2. Nếu DDL thành công, ROLLBACK sau đó không hoàn tác DDL và cũng không khôi phục DML đã được implicit commit trước đó.

Ví dụ:

~~~sql
START TRANSACTION;

UPDATE accounts
SET balance = balance - 100
WHERE account_id = 10;

ALTER TABLE orders
  ADD COLUMN source_channel VARCHAR(30) NULL;

ROLLBACK;
~~~

Không được giả định câu ROLLBACK cuối sẽ hoàn tác cả câu UPDATE lẫn ALTER. DDL có thể đã commit transaction trước đó; schema mới vẫn tồn tại nếu ALTER thành công. Đây là lý do không nên trộn công việc DML nghiệp vụ chưa commit với DDL trong cùng một session.

#### 1.1. Những câu lệnh cần xem là ranh giới transaction

Bảng sau tóm tắt một số nhóm câu lệnh thường gây implicit commit. Danh sách đầy đủ có khác biệt theo phiên bản; hãy kiểm tra tài liệu đúng phiên bản trước khi thiết kế công cụ migration.

| Nhóm | Ví dụ | Lưu ý |
|---|---|---|
| Thay đổi database/table | CREATE DATABASE, ALTER DATABASE, DROP DATABASE, CREATE TABLE, ALTER TABLE, DROP TABLE | Thường commit transaction đang mở trước khi chạy |
| Đổi tên/xóa dữ liệu cấu trúc | RENAME TABLE, TRUNCATE TABLE | Không tương đương DELETE; không dùng ROLLBACK để khôi phục dữ liệu đã truncate |
| Index | CREATE INDEX, DROP INDEX | Thay đổi cấu trúc bảng và có thể cần metadata lock |
| Đối tượng lưu trữ SQL | Nhiều câu lệnh CREATE, ALTER, DROP cho view, routine, trigger, event | Kiểm tra danh sách implicit-commit của phiên bản |
| Quản lý quyền | GRANT, REVOKE, CREATE USER, ALTER USER, DROP USER | Là thay đổi bảo mật; không gộp với transaction nghiệp vụ |
| Quản trị transaction/session | START TRANSACTION, thay đổi autocommit từ 0 sang 1 | Có thể kết thúc transaction đang mở |

Có ngoại lệ quan trọng: CREATE TEMPORARY TABLE và DROP TEMPORARY TABLE không gây implicit commit như các câu lệnh tương ứng trên bảng thường. Tuy nhiên, thao tác tạo/xóa temporary table vẫn không được hoàn tác bằng ROLLBACK. Ngoại lệ này không làm cho DDL nói chung trở thành transactional.

#### 1.2. DDL atomic trong MySQL 8.0 không phải transaction DDL

MySQL 8.0 giới thiệu atomic DDL cho các thao tác được hỗ trợ. Với một câu DDL atomic và storage engine tương thích, MySQL phối hợp data dictionary, storage engine và binary log để câu lệnh hoàn tất như một đơn vị nguyên tử, kể cả khi máy chủ gặp sự cố trong lúc thực hiện.

Atomic DDL giải quyết tính toàn vẹn của **một thao tác DDL được hỗ trợ** khi có lỗi hoặc crash. Nó không có nghĩa:

- Có thể dùng ROLLBACK để hoàn tác DDL.
- Có thể gom nhiều câu DDL độc lập thành một transaction schema duy nhất.
- Mọi engine, mọi loại đối tượng và mọi thao tác DDL đều có cùng mức atomicity.
- Một migration gồm nhiều bước tự động quay lại trạng thái đầu nếu bước cuối thất bại.

Ví dụ migration gồm ADD COLUMN, UPDATE backfill và ADD INDEX vẫn có thể dừng sau khi hai bước đầu đã hoàn tất. Atomicity của từng câu lệnh không biến cả chuỗi thành một đơn vị all-or-nothing.

MySQL 5.7 không có cơ chế atomic DDL tổng quát như MySQL 8.0. Hành vi khi crash và khả năng phục hồi phụ thuộc thao tác, storage engine và phiên bản. Khi nâng cấp hoặc triển khai cùng một migration trên nhiều dòng phiên bản, phải kiểm thử riêng.

### 2. Vì sao migration có thể hoàn tất một phần?

Một migration thực tế thường gồm nhiều câu lệnh và nhiều giai đoạn:

1. Thêm cột hoặc bảng mới.
2. Cập nhật dữ liệu cũ.
3. Tạo index hoặc constraint.
4. Triển khai ứng dụng sử dụng schema mới.
5. Xóa cột hoặc bảng cũ ở một đợt phát hành sau.

Giả sử script chạy ba DDL. Câu thứ nhất thành công, câu thứ hai thành công, câu thứ ba bị lỗi do duplicate key. Khi đó schema có thể đã ở trạng thái trung gian. Nếu client mất kết nối ngay sau khi gửi DDL, kết quả còn có thể không rõ ràng với phía điều phối: server có thể đã hoàn tất lệnh dù client chưa nhận được phản hồi.

Các nguyên nhân thường gặp:

- DDL không tương thích với dữ liệu hiện có, ví dụ đổi cột sang NOT NULL trong khi vẫn có NULL.
- Thêm unique index nhưng dữ liệu có duplicate.
- Thiếu dung lượng tạm, tablespace hoặc disk.
- Metadata lock bị chặn bởi transaction dài hoặc truy vấn đang mở.
- DDL chạy lâu, vượt timeout ở proxy/client hoặc bị người vận hành hủy.
- Storage engine, thuật toán ALTER hoặc tính năng không được phiên bản hỗ trợ.
- Ứng dụng cũ vẫn đọc/ghi trong khi schema đang thay đổi.
- Một bước backfill dừng giữa các chunk hoặc bị chạy lặp sau retry.

Vì vậy, migration cần được thiết kế như một quy trình có trạng thái và có thể tiếp tục sau lỗi, thay vì giả định một file SQL luôn chạy từ đầu đến cuối.

### 3. Metadata lock và tác động vận hành

MySQL dùng metadata lock (MDL) để bảo vệ metadata của bảng và đối tượng trong lúc truy vấn hoặc DDL sử dụng chúng. DDL thường cần lấy lock tương thích phù hợp, có thể phải chờ các transaction đang giữ metadata lock kết thúc.

Một transaction đọc lâu nhưng chưa commit có thể khiến ALTER TABLE chờ. Khi DDL đang chờ lock, các truy vấn mới trên cùng bảng cũng có thể bị xếp hàng phía sau tùy thứ tự và loại lock, làm độ trễ ứng dụng tăng đột ngột.

#### 3.1. Quan sát lock đang chờ

Trên các phiên bản có Performance Schema metadata lock instrumentation:

~~~sql
SELECT
  OBJECT_TYPE,
  OBJECT_SCHEMA,
  OBJECT_NAME,
  LOCK_TYPE,
  LOCK_DURATION,
  LOCK_STATUS,
  OWNER_THREAD_ID
FROM performance_schema.metadata_locks
WHERE OBJECT_SCHEMA = 'appdb'
ORDER BY OBJECT_NAME, LOCK_STATUS;
~~~

Có thể xem thread và statement liên quan thông qua performance_schema.threads, events_statements_current hoặc view trong schema sys nếu đã cài đặt và được bật. Tên cột/view có thể khác theo phiên bản và quyền.

Trước DDL, kiểm tra transaction lâu:

~~~sql
SELECT
  trx_id,
  trx_started,
  trx_state,
  trx_mysql_thread_id,
  trx_query
FROM information_schema.innodb_trx
ORDER BY trx_started;
~~~

Đừng kết thúc session chỉ vì nó đang chạy lâu. Xác định chủ sở hữu, câu lệnh, tác động và cách kết thúc an toàn trước khi can thiệp.

#### 3.2. Dùng timeout có chủ đích

lock_wait_timeout điều khiển thời gian chờ metadata lock; innodb_lock_wait_timeout chủ yếu điều khiển thời gian chờ InnoDB row lock. Hai biến này không thay thế nhau.

Có thể đặt timeout ngắn ở session migration để DDL thất bại nhanh nếu không lấy được metadata lock:

~~~sql
SET SESSION lock_wait_timeout = 15;
ALTER TABLE appdb.orders
  ADD COLUMN source_channel VARCHAR(30) NULL;
~~~

Nếu DDL báo timeout, hãy điều tra blocker và thử lại trong cửa sổ phù hợp. Không tăng timeout vô hạn để che một transaction treo. Với DDL chạy lâu, cần theo dõi cả thời gian chờ lock, thời gian thực thi, disk I/O, temporary space và replication lag.

### 4. Chọn thuật toán ALTER và mức khóa

MySQL có các thuật toán DDL thường gặp:

| Algorithm | Đặc điểm tổng quát | Tác động cần đánh giá |
|---|---|---|
| INSTANT | Thay đổi metadata cho các thao tác được hỗ trợ | Thường nhanh, không rebuild toàn bộ dữ liệu; vẫn có yêu cầu metadata lock và giới hạn riêng |
| INPLACE | Storage engine thực hiện thay đổi mà không nhất thiết copy toàn bảng qua table mới | Có thể vẫn rebuild hoặc scan dữ liệu tùy thao tác; mức khóa thay đổi theo operation |
| COPY | Tạo bản sao bảng, chuyển dữ liệu rồi thay thế | Có thể tốn disk, I/O và thời gian; khả năng ghi đồng thời bị hạn chế hơn |

Khả năng dùng algorithm và lock phụ thuộc phiên bản, engine, cấu trúc bảng, loại cột/index và thao tác cụ thể. Tên INPLACE không đồng nghĩa không rebuild; LOCK=NONE không đồng nghĩa không có metadata lock ở đầu/cuối.

Khi đã xác định rõ yêu cầu, có thể yêu cầu MySQL dùng thuật toán và lock mong muốn:

~~~sql
ALTER TABLE appdb.orders
  ADD COLUMN source_channel VARCHAR(30) NULL,
  ALGORITHM=INSTANT;
~~~

Nếu operation không hỗ trợ INSTANT, câu lệnh sẽ báo lỗi thay vì tự chọn một thuật toán khác. Đây là hành vi có ích khi bạn muốn tránh bất ngờ do fallback. Chỉ dùng tùy chọn mà phiên bản đích hỗ trợ.

Đối với thao tác có thể dùng online DDL:

~~~sql
ALTER TABLE appdb.orders
  ADD INDEX idx_orders_created_at (created_at),
  ALGORITHM=INPLACE,
  LOCK=NONE;
~~~

Ví dụ này chỉ hợp lệ nếu loại index và cấu trúc bảng hỗ trợ tổ hợp algorithm/lock đó. Nếu không, MySQL trả lỗi. Ngay cả khi DML được phép tiếp tục, DDL vẫn cần metadata lock ở một số pha và có thể tạo tải I/O đáng kể.

Trước khi triển khai:

- Kiểm tra tài liệu phiên bản và engine.
- Thử trên bản sao có kích thước, phân bố dữ liệu và workload gần production.
- Dùng EXPLAIN cho truy vấn sau thay đổi và đo kế hoạch thực thi.
- Ước lượng dung lượng disk, thời gian scan/rebuild và replication lag.
- Đặt lock timeout và lịch triển khai.
- Chuẩn bị phương án dừng, tiếp tục hoặc sửa tiến dựa trên trạng thái thực tế.

### 5. Thiết kế migration có thể tiếp tục sau lỗi

Một migration chịu lỗi từng phần phải biết đã làm đến đâu và kiểm tra trạng thái database trước khi thực hiện lại. Không dựa duy nhất vào việc một script đã chạy hết hay chưa.

#### 5.1. Migration journal

Tạo bảng theo dõi migration trong schema quản trị:

~~~sql
CREATE TABLE IF NOT EXISTS ops.schema_migrations (
  migration_id VARCHAR(150) NOT NULL,
  checksum CHAR(64) NOT NULL,
  state VARCHAR(20) NOT NULL,
  started_at TIMESTAMP(6) NULL,
  completed_at TIMESTAMP(6) NULL,
  last_key BIGINT NULL,
  rows_processed BIGINT NOT NULL DEFAULT 0,
  error_message TEXT NULL,
  PRIMARY KEY (migration_id)
) ENGINE=InnoDB;
~~~

Các trạng thái có thể gồm PENDING, RUNNING, FAILED, VERIFYING và APPLIED. Tùy công cụ, có thể dùng bảng journal do framework quản lý; không tạo thêm một cơ chế cạnh tranh nếu dự án đã có migration runner chuẩn.

Ý nghĩa của các trường:

- migration_id: định danh duy nhất và có thứ tự.
- checksum: phát hiện nội dung migration bị sửa sau khi đã chạy.
- state: trạng thái hiện tại.
- started_at, completed_at: thời điểm bắt đầu và kết thúc.
- last_key, rows_processed: checkpoint cho backfill theo chunk.
- error_message: lỗi cuối cùng đã ghi nhận.

Ghi trạng thái RUNNING trước khi chạy DDL, sau đó thực hiện từng bước và kiểm tra metadata. Chỉ chuyển sang APPLIED khi postcondition đạt. Vì DDL có implicit commit, việc cập nhật journal không nằm trong cùng transaction nguyên tử với DDL; cần đối chiếu journal với schema thật khi khởi động lại.

#### 5.2. Precondition và postcondition

Mỗi bước nên định nghĩa:

- **Precondition:** schema/dữ liệu cần có trước khi chạy.
- **Action:** một thao tác DDL hoặc một chunk DML có phạm vi rõ.
- **Postcondition:** bằng chứng xác nhận thao tác đã hoàn tất.
- **Recovery:** hành động nếu postcondition không đạt hoặc kết quả chưa rõ.

Ví dụ trước khi thêm cột:

~~~sql
SELECT COLUMN_NAME, COLUMN_TYPE, IS_NULLABLE, COLUMN_DEFAULT
FROM information_schema.columns
WHERE table_schema = 'appdb'
  AND table_name = 'orders'
  AND column_name = 'source_channel';
~~~

Nếu chưa có cột, migration có thể thêm. Nếu cột đã có, không nên chỉ bỏ qua vì tên trùng: hãy xác minh kiểu, nullability, default, collation và ý nghĩa có đúng với migration mong đợi không. Cột cùng tên nhưng định nghĩa khác là drift cần điều tra.

Sau DDL, đọc lại metadata hoặc SHOW CREATE TABLE để xác nhận postcondition. Nếu client timeout, kết nối lại và kiểm tra schema trước khi quyết định chạy lại. Không giả định timeout đồng nghĩa server chưa thực hiện lệnh.

#### 5.3. Idempotency có kiểm soát

Một bước idempotent có thể được chạy lại mà không gây sai trạng thái. Nhưng IF NOT EXISTS không tự chứng minh đối tượng hiện hữu có định nghĩa đúng.

Ví dụ:

~~~sql
CREATE TABLE IF NOT EXISTS appdb.order_audit (
  audit_id BIGINT NOT NULL AUTO_INCREMENT,
  order_id BIGINT NOT NULL,
  changed_at TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  PRIMARY KEY (audit_id),
  KEY idx_order_audit_order_id (order_id)
) ENGINE=InnoDB;
~~~

Nếu table đã tồn tại với cột hoặc index khác, câu lệnh có thể không báo lỗi nhưng schema vẫn không đúng kỳ vọng. Vì vậy, idempotency cần gồm cả bước kiểm tra cấu trúc và dữ liệu, không chỉ thêm IF NOT EXISTS.

Với DML backfill, dùng điều kiện có thể chạy lặp an toàn, ví dụ chỉ cập nhật hàng còn NULL. Nếu có thể, lưu checkpoint theo khóa chính và tiến lên sau mỗi chunk đã commit.

### 6. Expand-contract: thay đổi tương thích nhiều phiên bản ứng dụng

Expand-contract giảm rủi ro khi schema và ứng dụng không thể được triển khai đồng thời. Thay đổi được chia thành giai đoạn mở rộng tương thích, chuyển ứng dụng, rồi mới thu hẹp/xóa cấu trúc cũ.

Ví dụ cần thay orders.customer_name bằng orders.customer_display_name.

#### Giai đoạn 1 — Expand

Thêm cột mới, giữ cột cũ:

~~~sql
ALTER TABLE appdb.orders
  ADD COLUMN customer_display_name VARCHAR(200) NULL;
~~~

Triển khai ứng dụng có thể đọc cả hai cột và ghi đồng bộ vào cột mới. Nếu nhiều phiên bản ứng dụng chạy song song, phiên bản cũ vẫn phải hoạt động được với schema mở rộng.

#### Giai đoạn 2 — Backfill

Điền dữ liệu cũ theo chunk khóa chính:

~~~sql
UPDATE appdb.orders
SET customer_display_name = customer_name
WHERE order_id > 0
  AND order_id <= 10000
  AND customer_display_name IS NULL;
~~~

Sau mỗi chunk, commit và ghi checkpoint. Chọn batch size theo tải, thời gian lock và replication lag; không chạy một UPDATE khổng lồ nếu bảng lớn. Câu lệnh phải được thiết kế để chạy lại an toàn nếu tiến trình dừng sau khi commit nhưng trước khi ghi checkpoint.

#### Giai đoạn 3 — Verify và switch

Đối chiếu số hàng còn NULL, giá trị khác nhau và quy tắc nghiệp vụ. Sau khi dữ liệu mới đã đầy đủ, triển khai ứng dụng đọc cột mới. Theo dõi lỗi và giữ cột cũ trong khoảng thời gian rollback đã định.

#### Giai đoạn 4 — Contract

Chỉ sau khi mọi phiên bản ứng dụng cũ đã được loại bỏ và không còn job phụ thuộc cột cũ, mới xóa cột:

~~~sql
ALTER TABLE appdb.orders
  DROP COLUMN customer_name;
~~~

DROP COLUMN là bước phá hủy thông tin schema và có thể làm mất dữ liệu cũ. Hãy xác nhận backup, consumer, báo cáo, stored program và truy vấn ad-hoc không còn phụ thuộc trước khi chạy.

Mô hình này áp dụng cho đổi tên cột, thay kiểu dữ liệu, tách bảng, chuyển quan hệ và thêm constraint. Với thay đổi không tương thích, cần có versioning ở API hoặc một khoảng chuyển đổi có kiểm soát.

### 7. Backfill chịu lỗi và giới hạn transaction

Backfill là DML, vì vậy có thể chia thành transaction nhỏ. Mỗi chunk nên có phạm vi khóa ổn định, điều kiện idempotent và checkpoint.

Ví dụ dùng khóa tăng dần:

~~~sql
START TRANSACTION;

UPDATE appdb.orders
SET normalized_status = UPPER(status)
WHERE order_id > 100000
  AND order_id <= 110000
  AND normalized_status IS NULL;

COMMIT;
~~~

Sau khi commit, cập nhật last_key=110000 trong journal. Nếu tiến trình dừng trước khi cập nhật checkpoint, chunk có thể chạy lại; điều kiện normalized_status IS NULL giúp tránh ghi đè giá trị đã được xử lý. Nếu dữ liệu nguồn có thể thay đổi đồng thời, cần xác định quy tắc ưu tiên giữa ứng dụng và backfill.

Nguyên tắc:

- Chia chunk theo primary key hoặc key ổn định có index.
- Giới hạn số hàng và thời gian mỗi transaction.
- Commit thường xuyên để giảm undo/redo pressure và thời gian giữ row lock.
- Theo dõi replica lag, buffer pool, disk I/O và thời gian truy vấn.
- Lưu checkpoint sau khi chunk commit.
- Có cách phát hiện và xử lý hàng bị bỏ qua hoặc thay đổi trong lúc backfill.
- Dùng giới hạn tốc độ hoặc tạm dừng nếu tải production vượt ngưỡng.

Nếu khóa không liên tục, đừng giả định last_key + 1 luôn tồn tại. Hãy dùng truy vấn lấy batch kế tiếp theo thứ tự khóa, lưu giá trị khóa cuối thực tế và xử lý trường hợp không còn hàng.

### 8. Migration nhiều bước và điều phối đồng thời

Hai migration runner chạy cùng lúc có thể cùng kiểm tra trạng thái “chưa tồn tại” rồi cùng thực hiện DDL. Điều này dễ tạo lỗi duplicate object, lock contention hoặc trạng thái journal không nhất quán.

Giải pháp điều phối có thể gồm:

- Chỉ một pipeline được quyền chạy migration trên một schema.
- Dùng named lock như GET_LOCK() nếu các runner cùng kết nối đến một MySQL instance và cùng tuân theo giao thức lock.
- Dùng cơ chế lease/lock của hệ thống triển khai khi có nhiều môi trường hoặc nhiều endpoint.
- Ghi migration ID và checksum để phát hiện chạy sai thứ tự hoặc nội dung đã thay đổi.

Ví dụ named lock trong một session:

~~~sql
SELECT GET_LOCK('appdb_schema_migration', 10) AS lock_acquired;
-- Chỉ tiếp tục khi kết quả là 1.

-- Chạy migration và kiểm tra postcondition.

SELECT RELEASE_LOCK('appdb_schema_migration');
~~~

Named lock gắn với session và được giải phóng khi session kết thúc. Nó không tự đồng bộ các runner nếu chúng kết nối đến các MySQL instance khác nhau, cũng không thay thế lock metadata của DDL. Luôn xử lý trường hợp lấy lock timeout hoặc mất kết nối trước khi thực hiện thay đổi.

### 9. Phục hồi khi migration thất bại từng phần

Khi một bước thất bại, không chạy lại toàn bộ file ngay lập tức. Hãy tái dựng trạng thái thật của schema và dữ liệu trước.

Quy trình xử lý:

1. **Dừng tiến trình tiếp theo.** Không để pipeline tiếp tục triển khai ứng dụng hoặc chạy migration phụ thuộc.
2. **Lưu bằng chứng.** Ghi lỗi MySQL, migration ID, checksum, thời điểm, server version và output đã chạy.
3. **Đọc journal.** Xem bước cuối cùng được ghi là RUNNING/FAILED/VERIFYING; không coi journal là nguồn duy nhất.
4. **Đọc schema thật.** Dùng SHOW CREATE TABLE, INFORMATION_SCHEMA.COLUMNS, STATISTICS, TABLE_CONSTRAINTS và các metadata liên quan.
5. **Đối chiếu dữ liệu.** Kiểm tra backfill đã chạy đến đâu, số hàng còn lại và các bất biến nghiệp vụ.
6. **Phân loại trạng thái.** Xác định DDL chưa chạy, đã chạy hoàn tất, chạy một phần theo khả năng của operation/engine, hoặc kết quả không rõ do client mất kết nối.
7. **Chọn recovery.** Tiếp tục từ bước còn thiếu, sửa tiến bằng migration mới, hoặc restore nếu có yêu cầu quay lại và đã có kế hoạch phù hợp.
8. **Xác minh sau sửa.** Chạy lại postcondition, kiểm tra ứng dụng, replication và journal trước khi mở pipeline.

#### 9.1. Ưu tiên forward-fix khi schema đã mở rộng

Với migration additive như thêm cột nullable hoặc tạo bảng mới, cách an toàn thường là sửa nguyên nhân rồi tiếp tục từ trạng thái hiện tại. Ví dụ, nếu thêm cột thành công nhưng tạo index thất bại do thiếu dung lượng, giữ cột, giải phóng dung lượng theo quy trình, đánh giá tải rồi tạo index lại sau khi xác minh index chưa tồn tại.

Không xóa cột mới chỉ để “trả về như cũ” nếu ứng dụng hoặc backfill đã bắt đầu sử dụng nó. Rollback schema có thể làm mất dữ liệu mới đã ghi vào cột đó.

#### 9.2. Khi cần rollback hoặc restore

Rollback DDL thường là một migration mới có tác dụng ngược, không phải câu ROLLBACK của transaction. Ví dụ, có thể drop một index vừa thêm nếu chắc chắn không có ứng dụng phụ thuộc và thao tác không ảnh hưởng hiệu năng ngoài dự kiến. Nhưng xóa cột đã nhận dữ liệu mới có thể làm mất thông tin.

Restore backup là phương án phục hồi dữ liệu có phạm vi lớn, thường cần downtime hoặc một kế hoạch chuyển đổi khác. Trước khi restore, phải xác định RPO/RTO, các giao dịch phát sinh sau backup và cách đưa hệ thống trở lại trạng thái nhất quán. Không xem restore như thao tác undo nhanh cho một câu ALTER.

### 10. Ví dụ migration có journal và kiểm tra postcondition

Giả sử cần thêm cột source_channel cho bảng orders. Migration runner nên thực hiện theo logic sau:

1. Tính checksum của file migration và tìm migration_id trong journal.
2. Nếu migration đã APPLIED với checksum khớp, kết thúc thành công.
3. Nếu cùng ID nhưng checksum khác, dừng và yêu cầu điều tra.
4. Đánh dấu RUNNING, ghi thời điểm bắt đầu.
5. Kiểm tra cột chưa có hoặc đã có đúng định nghĩa mong đợi.
6. Chạy DDL nếu cần.
7. Đọc lại metadata và xác nhận kiểu/nullability/default.
8. Chỉ đánh dấu APPLIED khi postcondition đạt; nếu không, ghi FAILED cùng lỗi và giữ schema để điều tra.

Truy vấn postcondition:

~~~sql
SELECT
  COLUMN_NAME,
  COLUMN_TYPE,
  IS_NULLABLE,
  COLUMN_DEFAULT
FROM information_schema.columns
WHERE table_schema = 'appdb'
  AND table_name = 'orders'
  AND column_name = 'source_channel';
~~~

Runner phải so sánh kết quả với định nghĩa mong đợi, không chỉ kiểm tra truy vấn trả về một dòng. Nếu cột tồn tại nhưng sai kiểu hoặc sai nullability, đánh dấu drift và dừng để có migration sửa chữa rõ ràng.

Một migration tiếp theo có thể tạo index:

~~~sql
SELECT
  INDEX_NAME,
  NON_UNIQUE,
  SEQ_IN_INDEX,
  COLUMN_NAME
FROM information_schema.statistics
WHERE table_schema = 'appdb'
  AND table_name = 'orders'
  AND index_name = 'idx_orders_source_channel';
~~~

Nếu index chưa tồn tại, kiểm tra dữ liệu và khả năng DDL trước khi tạo. Nếu đã tồn tại, xác minh thứ tự cột, uniqueness và loại index đúng mong muốn. Không coi tên index trùng là bằng chứng index đúng.

### 11. Checklist trước khi triển khai DDL

- [ ] Đã xác định phiên bản MySQL, storage engine và khả năng atomic/online DDL của operation.
- [ ] Đã kiểm tra schema hiện tại, dữ liệu NULL/duplicate và các constraint liên quan.
- [ ] Đã xác định DDL implicit commit và không dựa vào ROLLBACK để undo.
- [ ] Đã kiểm tra transaction dài và metadata lock blocker.
- [ ] Đã chọn algorithm/lock phù hợp và thử trên dữ liệu gần production.
- [ ] Đã ước lượng disk, I/O, thời gian rebuild và replication lag.
- [ ] Đã có migration ID, checksum, journal và postcondition.
- [ ] Đã thiết kế bước có thể retry hoặc recovery sau timeout/disconnect.
- [ ] Ứng dụng cũ và mới tương thích với schema trong giai đoạn chuyển tiếp.
- [ ] Có backup, phương án forward-fix/restore và người chịu trách nhiệm.
- [ ] Đã kiểm tra ứng dụng, dữ liệu và replication sau khi DDL hoàn tất.

### 12. Bài tập thực hành

Một migration cần thêm customer_display_name vào bảng orders, backfill từ customer_name, tạo index và triển khai ứng dụng đọc cột mới. Script chạy được hai bước đầu nhưng bị ngắt kết nối trước khi tạo index. Khi kiểm tra lại, cột mới tồn tại và đã có dữ liệu ở một phần bảng.

1. Vì sao ROLLBACK không thể đưa schema và dữ liệu về trạng thái trước migration?
2. Bạn cần truy vấn metadata nào để xác minh cột đã được tạo đúng kiểu, nullability và default?
3. Thiết kế checkpoint theo primary key để backfill có thể chạy lại sau khi tiến trình dừng.
4. Làm thế nào xác định index đã tồn tại nhưng có định nghĩa sai?
5. Vì sao triển khai ứng dụng đọc cột mới trước khi backfill hoàn tất có thể gây lỗi?
6. Hãy mô tả các giai đoạn expand, backfill, verify, switch và contract.
7. Nếu client timeout sau khi gửi ALTER TABLE, bạn xác định kết quả lệnh bằng cách nào trước khi retry?
8. Khi nào nên forward-fix, khi nào cần restore backup?

### 13. Nguyên tắc vận hành

Hãy coi mỗi DDL là một ranh giới commit và mỗi migration nhiều bước là một quy trình có thể dừng giữa chừng. Atomic DDL bảo vệ một số thao tác đơn lẻ trong phạm vi được hỗ trợ; nó không cung cấp transaction bao trùm toàn bộ thay đổi schema. Thiết kế precondition, action, postcondition, journal và checkpoint để biết trạng thái thật sau lỗi. Dùng expand-contract để ứng dụng cũ và mới cùng hoạt động trong giai đoạn chuyển tiếp. Khi sự cố xảy ra, đọc lại metadata và dữ liệu trước khi retry, forward-fix hoặc restore; không dựa vào giả định rằng script chạy lại từ đầu sẽ an toàn.
