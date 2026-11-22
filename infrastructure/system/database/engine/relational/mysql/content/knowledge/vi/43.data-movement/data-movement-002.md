# Xuất nhập bằng mysqldump và kiểm soát thứ tự đối tượng

## Mục tiêu

Sau bài học này, bạn có thể:

- Chọn phạm vi dump phù hợp: một database, nhiều database, một số bảng, chỉ cấu trúc hoặc chỉ dữ liệu.
- Tạo bản dump nhất quán cho workload InnoDB và hiểu giới hạn của `--single-transaction`.
- Xuất đầy đủ bảng, view, trigger, stored procedure, function và event.
- Phục hồi dump theo đúng database đích, quyền truy cập và thứ tự phụ thuộc giữa các đối tượng.
- Xử lý foreign key, `DEFINER`, character set, GTID và binary log metadata khi di chuyển dữ liệu.
- Kiểm chứng kết quả import bằng cấu trúc, dữ liệu, quyền và truy vấn nghiệp vụ.

## 1. Vai trò của mysqldump

`mysqldump` là tiện ích dòng lệnh của MySQL để xuất database thành một tệp SQL logic. Tệp này thường chứa các câu lệnh tạo schema, tạo bảng, chèn dữ liệu và tái tạo một số đối tượng database. Khi phục hồi, MySQL client đọc tệp SQL và thực thi các câu lệnh đó trên máy chủ đích.

Logical dump hữu ích khi:

- Di chuyển database giữa các máy chủ hoặc môi trường.
- Sao chép một schema nhỏ hoặc vừa để thử nghiệm.
- Xuất một số bảng để kiểm tra, trao đổi hoặc lưu trữ.
- Tạo bản dump có thể đọc và chỉnh sửa để phục hồi chọn lọc.
- Di chuyển giữa các phiên bản MySQL có hỗ trợ tương thích SQL phù hợp.

Dump logic có một số khác biệt so với physical backup. Nó tái tạo dữ liệu bằng SQL nên thường linh hoạt, nhưng với database lớn, thời gian export/import có thể dài do MySQL phải đọc từng hàng, tạo lại index và thực thi câu lệnh INSERT. Một bản dump thành công cũng chưa chứng minh có thể phục hồi đúng; phải kiểm tra import trên môi trường đích.

`mysqldump` là chương trình client. Nó kết nối tới MySQL Server bằng tài khoản được cấp quyền, đọc metadata và dữ liệu rồi ghi kết quả ra stdout hoặc tệp. Tệp dump không tự bao gồm mọi thứ của một máy chủ: cấu hình server, plugin, file cấu hình, khóa mã hóa, tài khoản hệ điều hành, log nhị phân và các thành phần hạ tầng cần được quản lý riêng.

## 2. Xác định phạm vi trước khi dump

Trước khi chạy lệnh, xác định chính xác những gì cần di chuyển:

- Database/schema và các bảng cần thiết.
- View và thứ tự phụ thuộc giữa các view.
- Trigger gắn với bảng.
- Stored procedure và stored function.
- Event Scheduler và các event đã định nghĩa.
- Tài khoản, role, quyền và đối tượng `DEFINER`.
- Character set, collation, SQL mode và timezone liên quan.
- GTID hoặc binary log coordinates nếu cần dựng replication hoặc PITR.

Không mặc định rằng dump một database sẽ bao gồm toàn bộ đối tượng mà ứng dụng sử dụng. `mysqldump` có các tùy chọn riêng cho routine và event; trigger được xuất mặc định trong các phiên bản hiện đại, nhưng có thể chỉ rõ `--triggers` để thể hiện ý định.

### 2.1. Các đối tượng và tùy chọn

| Đối tượng | Cách xuất |
|---|---|
| Table definition | Mặc định được xuất |
| Table data | Mặc định được xuất |
| View | Được xuất như định nghĩa view trong dump |
| Trigger | Được xuất mặc định; có thể chỉ rõ `--triggers` |
| Stored procedure/function | Cần `--routines` |
| Event | Cần `--events` |
| Tablespace metadata | Có thể bỏ bằng `--no-tablespaces` nếu không cần hoặc thiếu quyền đọc metadata tablespace |
| Tài khoản và quyền | Không xem dump ứng dụng thông thường là bản sao đầy đủ hệ thống account; phải có quy trình di chuyển user/role/grant riêng |

Với database ứng dụng, lệnh thường dùng là:

```bash
mysqldump \
  --host=db-source.example.internal \
  --user=backup_user \
  --password \
  --default-character-set=utf8mb4 \
  --single-transaction \
  --quick \
  --routines \
  --events \
  --triggers \
  --hex-blob \
  --databases sales_app \
  --result-file=sales_app.sql
```

`--password` không kèm giá trị để client hỏi mật khẩu tương tác. Không đặt mật khẩu trực tiếp trong command line, script được commit hoặc lịch sử shell. Dùng secret manager hoặc cơ chế xác thực được tổ chức phê duyệt khi tự động hóa.

`--databases sales_app` khiến dump có các câu lệnh chọn/tạo database, do đó có thể phục hồi mà không cần chỉ định database ở cuối lệnh `mysql`. Nếu bỏ `--databases`, dump thường chỉ chứa các đối tượng và dữ liệu của schema đã chọn; lúc import cần chỉ rõ database đích.

### 2.2. Dump toàn bộ database hoặc một số bảng

Xuất toàn bộ database mà tài khoản có thể đọc:

```bash
mysqldump --host=db-source.example.internal \
  --user=backup_user --password \
  --single-transaction --routines --events --triggers \
  --all-databases \
  --result-file=all-databases.sql
```

`--all-databases` có thể bao gồm các schema hệ thống. Không dùng lệnh này như cách di chuyển account hoặc thay thế quy trình backup/restore toàn máy chủ mà chưa đánh giá phiên bản, quyền và các schema hệ thống. Đối với migration ứng dụng, thường nên chọn rõ database nghiệp vụ.

Xuất một số bảng trong một database:

```bash
mysqldump --host=db-source.example.internal \
  --user=backup_user --password \
  --single-transaction \
  sales_app \
  orders order_items customers \
  --result-file=sales-core.sql
```

Khi chỉ định tên database theo cú pháp `mysqldump db_name table_name ...`, không thêm `--databases`: tùy chọn đó khiến các đối số được hiểu là tên database. Dump chọn bảng không tạo database đích; hãy chuẩn bị schema đích và import theo đúng database đã chọn.

### 2.3. Chỉ xuất cấu trúc hoặc chỉ dữ liệu

Chỉ xuất cấu trúc:

```bash
mysqldump --host=db-source.example.internal \
  --user=backup_user --password \
  --no-data --routines --events --triggers \
  --databases sales_app \
  --result-file=sales-schema.sql
```

Chỉ xuất dữ liệu, không tạo table:

```bash
mysqldump --host=db-source.example.internal \
  --user=backup_user --password \
  --no-create-info --skip-triggers \
  --single-transaction --quick \
  sales_app \
  --result-file=sales-data.sql
```

Dump chỉ dữ liệu phù hợp khi schema đích đã được tạo và tương thích. Không chạy data-only dump vào database có cấu trúc khác mà chưa kiểm tra tên cột, thứ tự cột, kiểu dữ liệu, constraint và khóa.

## 3. Tính nhất quán khi export

### 3.1. `--single-transaction` với InnoDB

Với bảng InnoDB, `--single-transaction` yêu cầu `mysqldump` bắt đầu một transaction ở isolation level phù hợp để đọc một snapshot nhất quán. Các thay đổi được commit sau thời điểm snapshot không xuất hiện trong dump đó. Nhờ vậy, ứng dụng có thể tiếp tục đọc/ghi trong lúc export mà không cần khóa toàn bộ bảng trong suốt thời gian dump.

Ví dụ:

```bash
mysqldump --host=db-source.example.internal \
  --user=backup_user --password \
  --single-transaction --quick \
  --databases sales_app \
  --result-file=sales_app.sql
```

Điều kiện quan trọng:

- Tính nhất quán snapshot áp dụng cho transactional tables như InnoDB.
- Không thực hiện DDL đồng thời trong thời gian dump. Các lệnh `ALTER TABLE`, `CREATE TABLE`, `DROP TABLE`, `RENAME TABLE` hoặc `TRUNCATE TABLE` có thể làm dump thất bại hoặc không còn phản ánh một schema nhất quán.
- Bảng dùng MyISAM hoặc engine không hỗ trợ transaction không được bảo vệ bởi snapshot InnoDB; dữ liệu có thể thay đổi trong lúc dump.
- Snapshot dài có thể giữ lại phiên bản row cũ trong undo log, làm tăng áp lực lưu trữ và ảnh hưởng purge.

Vì vậy, hãy phối hợp lịch dump với quy trình schema migration và kiểm tra storage engine của các bảng trọng yếu.

### 3.2. `--lock-tables` và `--lock-all-tables`

`mysqldump` có các cơ chế khóa để giữ dữ liệu ổn định khi export. Tùy chọn `--lock-tables` khóa các bảng trong từng database trước khi dump database đó. Cơ chế này không tạo một snapshot nhất quán xuyên suốt nhiều database.

`--lock-all-tables` yêu cầu global read lock trong thời gian dump, ngăn các thao tác ghi có thể làm thay đổi dữ liệu trong lúc export. Điều này có thể ảnh hưởng lớn đến ứng dụng nếu dump lâu.

`--single-transaction` và `--lock-tables` không nên được kết hợp như hai cơ chế cùng lúc; khi dùng `--single-transaction`, tùy chọn lock tables bị vô hiệu hóa. Chọn chiến lược dựa trên engine, thời gian dump và mức chấp nhận gián đoạn ghi.

### 3.3. Vì sao cần `--quick`?

`--quick` yêu cầu client đọc từng hàng từ server và ghi ra ngay, thay vì tải toàn bộ kết quả của một bảng vào bộ nhớ client. Nó phù hợp với bảng lớn và được bật mặc định thông qua nhóm tùy chọn `--opt` trong các bản mysqldump hiện đại.

Nếu dùng `--skip-opt`, cần xem xét bật lại các tùy chọn cần thiết như `--quick`, `--extended-insert`, `--lock-tables` hoặc `--disable-keys` theo mục tiêu. Không tắt nhóm tùy chọn mặc định mà không hiểu các hành vi đi kèm.

## 4. Kiểm soát thứ tự đối tượng trong dump

Database không chỉ gồm bảng và dữ liệu. Các đối tượng có thể phụ thuộc vào nhau:

- Foreign key giữa các bảng.
- View tham chiếu bảng hoặc view khác.
- Trigger gắn với bảng và gọi stored function.
- Stored procedure/function tham chiếu bảng, view hoặc routine khác.
- Event gọi stored procedure hoặc cập nhật bảng.
- Đối tượng có `DEFINER` yêu cầu tài khoản tương ứng và quyền thích hợp.

Khi phục hồi, thứ tự tạo đối tượng cần phù hợp với dependency graph. Một quy trình rõ ràng thường chia thành các pha:

1. Tạo database, character set và collation.
2. Tạo các base table và constraint.
3. Nạp dữ liệu cho bảng.
4. Tạo view theo thứ tự phụ thuộc.
5. Tạo routine cần thiết.
6. Tạo trigger sau khi bảng và routine được tham chiếu đã sẵn sàng.
7. Tạo event sau khi procedure, bảng và tài khoản `DEFINER` đã được chuẩn bị.
8. Kiểm tra quyền, trạng thái event scheduler và ứng dụng.

Đây là thứ tự triển khai có kiểm soát, không phải cam kết rằng mọi tệp `mysqldump` đều được sắp xếp đúng theo danh sách này trong mọi phiên bản. Hãy kiểm tra cấu trúc dump thực tế. `mysqldump` có logic xử lý riêng cho view, trigger và các đối tượng liên quan; thứ tự câu lệnh trong tệp có thể khác một quy trình thủ công.

### 4.1. Base table và foreign key

Foreign key có thể tham chiếu bảng được tạo sau trong dump. Dump do `mysqldump` tạo thường có lệnh tắt kiểm tra foreign key trong lúc import và bật lại ở cuối tệp. Cơ chế này hỗ trợ nạp các bảng có quan hệ phụ thuộc hoặc vòng tham chiếu.

Ví dụ hai bảng có quan hệ:

```sql
CREATE TABLE customers (
  customer_id BIGINT PRIMARY KEY,
  name VARCHAR(200) NOT NULL
) ENGINE=InnoDB;

CREATE TABLE orders (
  order_id BIGINT PRIMARY KEY,
  customer_id BIGINT NOT NULL,
  created_at DATETIME NOT NULL,
  CONSTRAINT fk_orders_customer
    FOREIGN KEY (customer_id)
    REFERENCES customers(customer_id)
) ENGINE=InnoDB;
```

Trong mô hình này, `orders` phụ thuộc `customers`. Khi tạo schema thủ công, nên tạo bảng được tham chiếu trước. Khi import dump, cần kiểm tra cách file xử lý `FOREIGN_KEY_CHECKS`.

Lưu ý quan trọng: `SET FOREIGN_KEY_CHECKS=1` không quét lại toàn bộ dữ liệu đã nạp để xác minh các quan hệ trước đó. Nếu import khi kiểm tra foreign key bị tắt và dữ liệu có orphan rows, bật lại kiểm tra không tự sửa hoặc tự phát hiện toàn bộ vi phạm cũ. Hãy kiểm tra tính toàn vẹn dữ liệu sau import bằng truy vấn anti-join hoặc kiểm tra nghiệp vụ.

Ví dụ tìm đơn hàng không có khách hàng tương ứng:

```sql
SELECT o.order_id, o.customer_id
FROM orders AS o
LEFT JOIN customers AS c
  ON c.customer_id = o.customer_id
WHERE c.customer_id IS NULL;
```

### 4.2. View và dependency giữa view

View cần các bảng hoặc view mà nó tham chiếu tồn tại khi định nghĩa được tạo và khi truy vấn chạy. Nếu `v_order_summary` dùng `v_order_base`, phải tạo view nền trước view phụ thuộc.

Ví dụ:

```sql
CREATE VIEW v_order_base AS
SELECT order_id, customer_id, created_at
FROM orders;

CREATE VIEW v_order_summary AS
SELECT customer_id, COUNT(*) AS order_count
FROM v_order_base
GROUP BY customer_id;
```

Nếu view được tạo với `SQL SECURITY DEFINER`, tài khoản `DEFINER` phải tồn tại và có quyền phù hợp. Nếu không thể giữ nguyên definer, phải đánh giá có thể chuyển sang `SQL SECURITY INVOKER` hay cần tạo lại tài khoản và grant tương ứng. Không xóa `DEFINER` hàng loạt mà chưa hiểu thay đổi ngữ nghĩa bảo mật.

### 4.3. Trigger và stored routine

Trigger gắn với một bảng cụ thể, nên bảng phải tồn tại trước khi tạo trigger. Trigger có thể gọi stored function; routine cần tồn tại và có quyền phù hợp. Khi nạp dữ liệu, việc tạo trigger sau dữ liệu giúp tránh trigger chạy lại trên từng INSERT của quá trình restore.

`mysqldump` xuất trigger mặc định sau phần dữ liệu của bảng trong cấu trúc dump thông thường. Routine và event cần các tùy chọn `--routines` và `--events`. Hãy xem cuối tệp dump để xác nhận các phần này có mặt.

Routine có thể chứa SQL mode, character set và collation được lưu khi tạo. Khi chuyển sang server có SQL mode hoặc collation khác, hãy kiểm tra định nghĩa và hành vi của routine thay vì chỉ xác nhận câu lệnh `CREATE PROCEDURE` thành công.

### 4.4. Event Scheduler

Event có thể tự chạy theo lịch khi Event Scheduler được bật. Trong quá trình phục hồi, event được import có thể ở trạng thái `ENABLED` và bắt đầu chạy khi scheduler hoạt động. Điều này có thể gây ghi dữ liệu ngoài dự kiến nếu event chạy trên database đích trước khi kiểm tra hoàn tất.

Trong migration, hãy xem xét giữ `event_scheduler=OFF` trên máy đích trong quá trình import. Sau khi kiểm tra event, `DEFINER`, lịch chạy và tác động nghiệp vụ, mới bật scheduler theo kế hoạch.

Kiểm tra:

```sql
SHOW VARIABLES LIKE 'event_scheduler';

SELECT EVENT_SCHEMA, EVENT_NAME, STATUS, DEFINER
FROM information_schema.EVENTS
WHERE EVENT_SCHEMA = 'sales_app';
```

## 5. Xuất và nhập routine, trigger, event

Một lệnh dump đầy đủ đối tượng ứng dụng thường dùng:

```bash
mysqldump --host=db-source.example.internal \
  --user=backup_user --password \
  --single-transaction --quick \
  --routines --events --triggers \
  --hex-blob \
  --databases sales_app \
  --result-file=sales_app_full.sql
```

Khi cần kiểm tra nội dung, tìm các câu lệnh như:

- `CREATE TABLE` — cấu trúc bảng.
- `INSERT INTO` hoặc `REPLACE INTO` — dữ liệu.
- `CREATE VIEW` — view.
- `CREATE TRIGGER` — trigger.
- `CREATE PROCEDURE` / `CREATE FUNCTION` — routine.
- `CREATE EVENT` — event.

Dump có thể chứa `DELIMITER` để MySQL client hiểu định nghĩa routine hoặc trigger có nhiều dấu chấm phẩy. `DELIMITER` là lệnh của client, không phải câu SQL server thông thường. Dùng MySQL client để import tệp dump nguyên bản; không tách file bằng cách chia theo dấu `;` đơn giản vì sẽ phá vỡ routine và trigger.

## 6. Phục hồi dump vào máy chủ đích

### 6.1. Import dump có `--databases`

Nếu dump được tạo bằng `--databases sales_app`, tệp chứa lệnh chọn/tạo database. Import bằng:

```bash
mysql --host=db-target.example.internal \
  --user=restore_user --password \
  < sales_app_full.sql
```

Tài khoản restore cần quyền tạo database/schema, bảng, view, trigger, routine, event và ghi dữ liệu tương ứng. Nếu có `DEFINER`, tài khoản có thể cần quyền quản trị phù hợp theo phiên bản và cấu hình bảo mật.

### 6.2. Import dump không có `--databases`

Nếu dump không chứa câu lệnh tạo/chọn database, tạo database đích trước:

```sql
CREATE DATABASE sales_app
  CHARACTER SET utf8mb4
  COLLATE utf8mb4_0900_ai_ci;
```

Sau đó import vào schema đã chọn:

```bash
mysql --host=db-target.example.internal \
  --user=restore_user --password \
  sales_app < sales_app.sql
```

Chỉ định character set và collation phù hợp với nguồn hoặc mục tiêu migration đã được kiểm tra. Không tự đổi collation trong lúc import nếu ứng dụng có phụ thuộc vào quy tắc so sánh, sắp xếp hoặc unique key.

### 6.3. Import từ MySQL client tương tác

Trong MySQL client:

```sql
CREATE DATABASE sales_app;
USE sales_app;
SOURCE /backup/sales_app.sql;
```

Lệnh `SOURCE` là lệnh client, nên chỉ dùng trong MySQL command-line client tương tác. Với file lớn hoặc quy trình tự động, gọi `mysql < file.sql` thường dễ ghi nhận exit code và log hơn.

### 6.4. Nén dump

Có thể nén tệp dump để tiết kiệm dung lượng:

```bash
mysqldump --host=db-source.example.internal \
  --user=backup_user --password \
  --single-transaction --quick \
  --routines --events --triggers \
  --databases sales_app \
  | gzip > sales_app.sql.gz
```

Import:

```bash
gzip -dc sales_app.sql.gz \
  | mysql --host=db-target.example.internal \
          --user=restore_user --password
```

Với pipeline, phải kiểm tra cả exit code của `mysqldump`, `gzip` và `mysql`. Trong shell hỗ trợ `pipefail`, bật chế độ này để lỗi ở đầu pipeline không bị che bởi lệnh cuối. Không xem việc tệp `.gz` được tạo là bằng chứng dump đã hoàn tất thành công.

## 7. Quyền, DEFINER và bảo mật khi di chuyển

### 7.1. Quyền của tài khoản dump

Tùy phạm vi và phiên bản MySQL, `mysqldump` có thể cần quyền đọc dữ liệu, đọc metadata, xem view/trigger/routine/event và lấy thông tin tablespace hoặc binary log. Một số tùy chọn như `--single-transaction`, `--lock-all-tables`, `--source-data` có yêu cầu quyền khác nhau.

Nguyên tắc vận hành:

- Dùng tài khoản dump riêng, chỉ cấp quyền cần thiết cho schema và đối tượng được xuất.
- Kiểm tra tài liệu của phiên bản client/server để cấp đúng quyền, không cấp `SUPER` hoặc quyền quản trị rộng theo thói quen.
- Nếu không cần tablespace metadata, cân nhắc `--no-tablespaces` để tránh quyền `PROCESS` trong một số môi trường.
- Tài khoản import cần quyền tạo và nạp các đối tượng thực tế có trong dump.
- Bảo vệ tệp dump vì nó có thể chứa dữ liệu cá nhân, bí mật ứng dụng hoặc thông tin kinh doanh.

### 7.2. `DEFINER` của view, routine, trigger và event

Các đối tượng lưu trữ có thể được tạo với một tài khoản `DEFINER`. Ví dụ:

```sql
CREATE DEFINER='report_user'@'%' VIEW v_sales_report AS
SELECT order_id, customer_id, total_amount
FROM orders;
```

Nếu máy đích không có tài khoản `report_user`@`%`, việc tạo đối tượng hoặc thực thi nó có thể phát sinh lỗi quyền, tùy phiên bản và loại đối tượng. Ngay cả khi tạo được, một definer có quyền quá rộng cũng có thể tạo ra rủi ro bảo mật.

Trước migration:

1. Liệt kê `DEFINER` của view, routine, trigger và event.
2. Xác định tài khoản tương ứng có tồn tại ở đích hay không.
3. Tạo account và grant tối thiểu cần thiết, hoặc thiết kế lại đối tượng sang `SQL SECURITY INVOKER` nếu phù hợp.
4. Kiểm tra quyền của definer trên schema và bảng liên quan.
5. Thử thực thi đối tượng bằng tài khoản ứng dụng thực tế.

Không thay thế mọi `DEFINER` bằng tài khoản root hoặc tài khoản import. Làm vậy có thể khiến routine chạy với quyền cao hơn dự kiến.

### 7.3. Tài khoản và quyền người dùng

Dump một schema ứng dụng không đồng nghĩa đã di chuyển các tài khoản và quyền truy cập của hệ thống. Hãy quản lý account/role bằng quy trình riêng, chẳng hạn lưu `SHOW CREATE USER` và `SHOW GRANTS` cho từng user/role cần di chuyển, sau đó review và áp dụng trên môi trường đích.

Không sao chép mù quáng toàn bộ schema `mysql` giữa các phiên bản khác nhau. Cấu trúc hệ thống và data dictionary có thể thay đổi; dùng quy trình nâng cấp và quản lý account được MySQL hỗ trợ.

## 8. GTID và binary log metadata

Nếu mục tiêu chỉ là di chuyển một database độc lập, không nhất thiết phải đưa GTID history vào dump. Nếu mục tiêu là dựng replica hoặc tiếp tục PITR, phải lập kế hoạch riêng cho GTID và binary log.

### 8.1. `--set-gtid-purged`

`mysqldump` có tùy chọn `--set-gtid-purged` để kiểm soát việc ghi câu lệnh liên quan đến `GTID_PURGED` vào dump. Các chế độ thường gặp gồm `OFF`, `ON`, `AUTO` và `COMMENTED`; hành vi mặc định phụ thuộc phiên bản client.

- `OFF`: không đưa câu lệnh thiết lập GTID_PURGED vào dump.
- `ON`: ghi GTID set đã thực thi theo hành vi của tùy chọn; khi import có thể thay đổi GTID history của server đích và yêu cầu điều kiện phù hợp.
- `AUTO`: để client quyết định theo trạng thái GTID của server nguồn; khi GTID được bật, câu lệnh có thể mang theo tập GTID của toàn server chứ không chỉ các transaction thuộc database đang dump.
- `COMMENTED`: xuất thông tin câu lệnh dưới dạng comment để tham khảo, không tự thực thi khi import.

Không dùng `--set-gtid-purged=ON` một cách máy móc khi import vào máy chủ đã có lịch sử GTID. GTID set được xuất có thể bao gồm transaction ngoài phạm vi database đang dump, tùy phiên bản và cách dùng tùy chọn. Hãy kiểm tra nội dung dump, GTID set trên nguồn và đích, và quy trình dựng replica trước khi import.

### 8.2. `--source-data` và tọa độ binary log

Nếu cần ghi lại binary log file/position tại thời điểm dump để cấu hình replication theo file/position, có thể dùng `--source-data`. Tên tùy chọn cũ `--master-data` đã được thay thế bằng thuật ngữ source trong các phiên bản mới; dùng tên phù hợp với client.

Ví dụ:

```bash
mysqldump --host=db-source.example.internal \
  --user=backup_user --password \
  --single-transaction \
  --source-data=2 \
  --databases sales_app \
  --result-file=sales_app_with_position.sql
```

`--source-data=2` ghi câu lệnh tọa độ dưới dạng comment để người vận hành xem và sử dụng có kiểm soát. Tùy chọn này có thể cần global read lock ngắn để lấy tọa độ đồng bộ với snapshot; hãy đọc yêu cầu quyền và tác động khóa của phiên bản client. Nếu dùng GTID auto-position, cách cấu hình replica khác và thường không cần nhập file/position thủ công.

Không coi một câu lệnh tọa độ trong dump là đủ để tạo replica. Cần tài khoản replication, network/TLS, GTID history hoặc file/position hợp lệ, binlog còn tồn tại và quy trình start replica.

## 9. Khác biệt phiên bản và tương thích

Khi dump từ MySQL 8.4 và import vào một phiên bản cũ hơn, cú pháp, collation, kiểu dữ liệu, metadata hoặc tính năng có thể không được hỗ trợ. Ngược lại, dump từ phiên bản cũ sang phiên bản mới có thể gặp thay đổi từ khóa, default value, SQL mode và hành vi hệ thống.

Trước migration:

- Ghi lại phiên bản server nguồn, client `mysqldump` và server đích.
- Dùng client tương thích với server nguồn; tránh dùng một binary rất cũ để dump server mới.
- Kiểm tra collation như `utf8mb4_0900_ai_ci`, có thể không tồn tại trên các phiên bản MySQL cũ hơn.
- Kiểm tra kiểu dữ liệu, generated column, invisible index, expression default, check constraint và các tính năng theo phiên bản.
- Thử import vào server đích cùng phiên bản/cấu hình dự kiến.
- Đọc lỗi và warning của MySQL client; không bỏ qua lỗi chỉ vì phần lớn bảng đã được tạo.

Nếu migration cần đổi engine, collation hoặc cấu trúc schema, hãy tách thay đổi đó thành kế hoạch riêng và kiểm tra dữ liệu sau chuyển đổi.

## 10. Kiểm chứng dump và kết quả import

### 10.1. Kiểm tra dump sau export

Sau khi chạy `mysqldump`, xác minh:

- Exit code của lệnh bằng 0.
- Tệp tồn tại, dung lượng hợp lý và không bị cắt cụt.
- Tệp có phần đầu chứa thông tin phiên bản, SQL mode hoặc lệnh thiết lập session phù hợp.
- Có đủ `CREATE TABLE`, dữ liệu và các đối tượng yêu cầu.
- Các database/tables đúng phạm vi, không thiếu bảng hoặc vô tình xuất thêm schema hệ thống.
- Nếu dùng GTID hoặc source-data, kiểm tra nội dung tương ứng và xác nhận giá trị hợp lệ.
- Có checksum lưu cùng manifest để phát hiện thay đổi tệp sau khi tạo.

Ví dụ kiểm tra nhanh trên Linux:

```bash
test -s sales_app_full.sql
grep -E 'CREATE TABLE|CREATE VIEW|CREATE TRIGGER|CREATE PROCEDURE|CREATE FUNCTION|CREATE EVENT' \
  sales_app_full.sql | head -n 40
sha256sum sales_app_full.sql > sales_app_full.sql.sha256
```

Kiểm tra bằng `grep` chỉ là bước rà soát sơ bộ. Routine và trigger có thể chứa delimiter hoặc comment; không dùng grep làm parser SQL hoặc bằng chứng đầy đủ rằng mọi đối tượng đã được xuất.

### 10.2. Kiểm tra sau import

Trên máy đích:

```sql
SHOW DATABASES LIKE 'sales_app';

SELECT TABLE_NAME, TABLE_TYPE, ENGINE
FROM information_schema.TABLES
WHERE TABLE_SCHEMA = 'sales_app'
ORDER BY TABLE_TYPE, TABLE_NAME;

SELECT ROUTINE_NAME, ROUTINE_TYPE, DEFINER
FROM information_schema.ROUTINES
WHERE ROUTINE_SCHEMA = 'sales_app';

SELECT TRIGGER_NAME, EVENT_OBJECT_TABLE, DEFINER
FROM information_schema.TRIGGERS
WHERE TRIGGER_SCHEMA = 'sales_app';

SELECT EVENT_NAME, STATUS, DEFINER
FROM information_schema.EVENTS
WHERE EVENT_SCHEMA = 'sales_app';
```

Đối chiếu:

- Số bảng, view và đối tượng routine/trigger/event với nguồn.
- Engine, charset, collation, index, primary key, foreign key và partition nếu có.
- Số lượng hàng hoặc aggregate nghiệp vụ của các bảng trọng yếu.
- Tính hợp lệ của foreign key và dữ liệu tham chiếu.
- Quyền của tài khoản ứng dụng, `DEFINER` và SQL SECURITY.
- Các truy vấn quan trọng, transaction ghi thử và luồng tích hợp.

Không chỉ so sánh `COUNT(*)`. Một bảng có cùng số hàng vẫn có thể chứa giá trị khác, thiếu index hoặc sai quan hệ. Với bảng quan trọng, so sánh checksum/aggregate theo khóa hoặc chạy đối soát nghiệp vụ.

## 11. Xử lý lỗi import thường gặp

| Lỗi hoặc biểu hiện | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| `Unknown collation` | Server đích không hỗ trợ collation trong dump | Chọn phiên bản đích tương thích hoặc lập kế hoạch chuyển collation có kiểm thử |
| `Access denied` khi tạo view/routine/trigger | Tài khoản import thiếu quyền hoặc `DEFINER` không hợp lệ | Kiểm tra user, grant, definer và yêu cầu quyền của phiên bản |
| `Table doesn't exist` khi tạo view/trigger | Đối tượng phụ thuộc chưa được tạo hoặc dump thiếu bảng/routine | Kiểm tra dependency và thứ tự import; xác minh phạm vi dump |
| Duplicate key | Dữ liệu đã tồn tại, import lặp hoặc schema đích không sạch | Kiểm tra dữ liệu đích và chiến lược import; không dùng `--replace`/`--force` để che lỗi |
| Foreign key constraint fails | Dữ liệu tham chiếu thiếu, thứ tự nạp sai hoặc nguồn có orphan rows | Kiểm tra FK, parent/child rows và dữ liệu trước khi bật lại kiểm tra |
| `DEFINER` does not exist hoặc thiếu quyền | Account được tham chiếu chưa được tạo trên đích | Tạo account và quyền tối thiểu hoặc review lại security context |
| `max_allowed_packet` hoặc lỗi packet lớn | Một dòng INSERT/BLOB lớn vượt giới hạn client/server | Điều chỉnh giới hạn phù hợp ở cả client và server, hoặc dump/import theo cách phù hợp |
| Import dừng giữa chừng | Lỗi SQL, mất kết nối, hết dung lượng hoặc process bị ngắt | Xem exit code/log, xác định câu lệnh cuối cùng thành công và phục hồi lại theo kế hoạch sạch/tiếp tục có kiểm soát |
| Event chạy ngoài dự kiến | Event Scheduler bật trong lúc import hoặc ngay sau import | Tắt scheduler trong giai đoạn phục hồi, review event rồi bật lại có kiểm soát |

Tránh dùng `mysql --force` để import dump production như một biện pháp mặc định. Tùy chọn này tiếp tục sau lỗi SQL, có thể tạo ra một database chỉ được phục hồi một phần mà người vận hành tưởng là thành công.

## 12. Quy trình migration mẫu

Một quy trình chuyển database ứng dụng có thể tổ chức theo các bước sau:

1. **Khảo sát nguồn:** ghi nhận phiên bản MySQL, database, engine, dung lượng, object count, charset/collation, account, definer, event và GTID.
2. **Chuẩn bị đích:** cài phiên bản được hỗ trợ, cấu hình charset/collation, dung lượng, tài khoản import, account ứng dụng và quyền cần thiết.
3. **Kiểm tra tương thích:** dump thử, import vào staging, rà soát lỗi cú pháp, collation, routine, trigger, event và definer.
4. **Chốt dữ liệu:** chọn `--single-transaction` cho InnoDB hoặc phương án khóa phù hợp; kiểm soát DDL trong lúc dump.
5. **Export:** chạy dump với đủ đối tượng, ghi log và exit code, checksum tệp, bảo vệ tệp và chuyển sang kho lưu trữ an toàn.
6. **Import:** tắt event scheduler nếu cần, tạo schema và import bằng MySQL client; theo dõi log và dung lượng.
7. **Kiểm tra:** so sánh cấu trúc, dữ liệu, FK, object, quyền, truy vấn và luồng ứng dụng.
8. **Đồng bộ phần thay đổi cuối:** nếu hệ thống vẫn nhận ghi trong thời gian dump, cần một chiến lược cutover rõ ràng như dừng ghi ngắn, replication hoặc CDC. Một snapshot dump không tự mang các thay đổi phát sinh sau thời điểm snapshot.
9. **Cutover:** chuyển endpoint, xác minh kết nối, theo dõi lỗi và có kế hoạch quay lui dựa trên trạng thái ghi thực tế.
10. **Kết thúc:** xác nhận backup, retention, lịch backup mới và runbook phục hồi của máy chủ đích.

Không chuyển lưu lượng ghi sang đích trước khi hoàn tất đồng bộ phần dữ liệu phát sinh sau snapshot. Nếu nguồn tiếp tục nhận giao dịch, dữ liệu đích có thể bị thiếu những thay đổi mới dù dump ban đầu hợp lệ.

## 13. Tình huống thực hành

Một ứng dụng bán hàng có schema `sales_app` gồm các bảng `customers`, `orders`, `order_items`, một số view báo cáo, trigger cập nhật audit, procedure tổng hợp doanh thu và event đóng đơn hết hạn. Nguồn chạy MySQL 8.0; đích là một máy chủ mới cùng phiên bản. Ứng dụng vẫn có giao dịch trong giờ làm việc.

Hãy lập kế hoạch migration:

1. Kiểm kê các bảng, engine, foreign key, view, trigger, routine, event và `DEFINER`.
2. Chọn `--single-transaction --quick` nếu toàn bộ bảng nghiệp vụ là InnoDB; thống nhất không chạy DDL trong cửa sổ export.
3. Dump với `--routines --events --triggers --hex-blob` và chỉ định rõ database.
4. Kiểm tra dump có đầy đủ các đối tượng, lưu checksum và bảo vệ tệp.
5. Chuẩn bị account `DEFINER` và quyền ở đích; giữ Event Scheduler tắt trong lúc import.
6. Import vào schema đích, kiểm tra số bảng, view, routine, trigger và event.
7. Đối soát số lượng đơn hàng, tổng doanh thu theo ngày, khóa ngoại và dữ liệu audit.
8. Thiết kế cách đồng bộ các giao dịch phát sinh sau snapshot, sau đó dừng ghi ngắn để hoàn tất phần cuối và cutover.
9. Bật event scheduler sau khi xác nhận event không chạy lặp hoặc gây tác động ngoài dự kiến.
10. Kiểm tra ứng dụng với account thực tế, theo dõi log và xác nhận backup của đích.

**Câu hỏi tự kiểm tra:**

1. `--single-transaction` bảo đảm nhất quán cho engine nào? Vì sao DDL đồng thời vẫn là rủi ro?
2. `--routines` và `--events` bổ sung những đối tượng nào vào dump?
3. Vì sao trigger thường được tạo sau khi dữ liệu bảng đã được nạp?
4. Tắt rồi bật lại `FOREIGN_KEY_CHECKS` có xác minh lại các hàng đã nạp hay không?
5. `DEFINER` ảnh hưởng thế nào đến bảo mật của view và routine?
6. Vì sao phải giữ Event Scheduler tắt trong một số quy trình restore?
7. Khi dump có `--databases`, cách import khác gì dump chỉ có tên bảng/schema?
8. Vì sao một dump nhất quán vẫn có thể làm dữ liệu đích bị thiếu giao dịch khi nguồn tiếp tục nhận ghi?

## Kết luận

`mysqldump` giúp xuất database thành SQL logic linh hoạt để di chuyển và phục hồi. Một quy trình đáng tin cần chọn đúng phạm vi và tùy chọn đối tượng, tạo snapshot phù hợp với storage engine, kiểm soát DDL và dependency, xử lý `DEFINER`/quyền/event, rồi kiểm chứng dữ liệu sau import. Với hệ thống vẫn tiếp tục ghi, phải có bước đồng bộ phần thay đổi sau snapshot trước khi cutover.

## Tài liệu tham khảo

- [MySQL 8.4 Reference Manual — mysqldump: A Database Backup Program](https://dev.mysql.com/doc/refman/8.4/en/mysqldump.html)
- [MySQL 8.4 Reference Manual — mysqldump Options](https://dev.mysql.com/doc/refman/8.4/en/mysqldump-options.html)
- [MySQL 8.4 Reference Manual — mysqldump and Transactional Tables](https://dev.mysql.com/doc/refman/8.4/en/mysqldump.html#mysqldump-transactional-tables)
- [MySQL 8.4 Reference Manual — Stored Objects](https://dev.mysql.com/doc/refman/8.4/en/stored-objects.html)
