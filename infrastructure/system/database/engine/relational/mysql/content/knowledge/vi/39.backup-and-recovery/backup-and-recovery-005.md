# Routine, trigger, event, user/grant và các thành phần cần sao lưu

Một bản sao lưu MySQL chỉ có giá trị khi có thể khôi phục được cả dữ liệu lẫn những thành phần làm cho ứng dụng hoạt động đúng. Ngoài bảng và dữ liệu, một hệ thống thường phụ thuộc vào stored procedure, function, trigger, event, view, tài khoản, role, quyền truy cập, cấu hình máy chủ, khóa mã hóa và binary log. Bỏ sót một trong các thành phần này có thể khiến máy chủ khôi phục xong nhưng ứng dụng vẫn lỗi, tác vụ định kỳ không chạy hoặc quyền truy cập thay đổi ngoài dự kiến.

Bài học tập trung vào MySQL 8.0 trở lên, tương thích với MySQL 8.4. Các ví dụ dùng `mysqldump`, SQL quản trị và quy trình khôi phục logic. Với bản sao lưu vật lý, hãy dùng công cụ phù hợp phiên bản và storage engine của máy chủ, đồng thời bảo toàn các thành phần mã hóa và cấu hình đi kèm.

## Mục tiêu

Sau bài học, bạn có thể:

- Phân biệt các loại đối tượng cần có trong một bản sao lưu MySQL.
- Chọn tùy chọn `mysqldump` để lưu routines, triggers và events.
- Sao lưu riêng định nghĩa tài khoản, quyền, role và default role.
- Nhận diện các phụ thuộc như `DEFINER`, `SQL SECURITY`, event scheduler, plugin và keyring.
- Lập thứ tự khôi phục, kiểm tra tính đầy đủ và chuẩn bị binary log cho phục hồi theo thời điểm.

## 1. Một bản sao lưu MySQL cần chứa những gì?

Hãy xem bản sao lưu như một tập hợp các lớp liên kết với nhau. Từng lớp có cách sao lưu và khôi phục khác nhau.

| Nhóm | Thành phần cần lưu | Rủi ro nếu thiếu |
|---|---|---|
| Cấu trúc và dữ liệu | Database, table, cột, kiểu dữ liệu, index, khóa, constraint, partition, dữ liệu | Không thể dựng lại trạng thái dữ liệu và cấu trúc ứng dụng |
| Đối tượng logic | View, procedure, function, trigger, event | Mất quy tắc nghiệp vụ, tác vụ tự động hoặc logic truy cập |
| Danh tính và bảo mật | User, host, authentication plugin, role, quyền, default role, yêu cầu TLS và trạng thái tài khoản | Người dùng không đăng nhập được hoặc được cấp sai quyền |
| Trạng thái phục hồi | Binary log, GTID, vị trí log tại thời điểm backup, metadata replication | Không thể phát lại thay đổi chính xác đến thời điểm cần khôi phục |
| Cấu hình máy chủ | File cấu hình, `server_id`, `event_scheduler`, binlog, plugin/component, charset và tham số liên quan | Máy chủ phục hồi có hành vi khác máy chủ nguồn |
| Bí mật và phụ thuộc ngoài | Keyring, khóa mã hóa, chứng thư TLS, thư viện UDF/plugin, script được event gọi | Đối tượng tồn tại nhưng không thể giải mã hoặc thực thi |

Không phải mọi thành phần đều nằm trong cùng một file dump. Logical dump thường lưu cấu trúc và dữ liệu SQL; tài khoản, cấu hình, binary log và khóa mã hóa cần được kiểm kê theo quy trình riêng hoặc dùng công cụ backup toàn instance có hỗ trợ chúng.

## 2. Stored procedure và function

Stored procedure và stored function lưu logic SQL bên trong database. Chúng có thể được ứng dụng gọi trực tiếp, được trigger gọi hoặc được event thực thi theo lịch. Vì vậy, chỉ dump bảng và dữ liệu sẽ không đủ nếu ứng dụng dựa vào stored program.

Với `mysqldump`, cần bật `--routines` để xuất procedure và function:

```bash
mysqldump \
  --single-transaction \
  --routines \
  --databases sales_db \
  > sales_db.sql
```

`--routines` không được bật mặc định trong `mysqldump`. Nếu bỏ tùy chọn này, dump có thể chứa bảng và dữ liệu nhưng thiếu procedure/function. Khi kiểm tra một routine cụ thể, có thể dùng:

```sql
SHOW CREATE PROCEDURE sales_db.recalculate_order_total;
SHOW CREATE FUNCTION sales_db.normalize_phone;
```

Ngoài phần thân routine, hãy lưu ý các thuộc tính ảnh hưởng đến cách thực thi:

- `DEFINER`: tài khoản mà routine dùng làm ngữ cảnh định nghĩa.
- `SQL SECURITY DEFINER` hoặc `SQL SECURITY INVOKER`: xác định ngữ cảnh quyền khi chạy.
- `SQL_MODE`: chế độ SQL được lưu cùng routine và có thể ảnh hưởng cách diễn giải câu lệnh.
- Charset và collation của tham số, giá trị trả về và phần thân routine.

Khi khôi phục routine có `SQL SECURITY DEFINER`, tài khoản definer cần tồn tại và có các quyền cần thiết. Nếu definer không tồn tại hoặc quyền đã thay đổi, routine có thể được tạo nhưng lỗi khi chạy, hoặc việc tạo object phát sinh cảnh báo/lỗi tùy câu lệnh và phiên bản. Do đó, hãy kiểm kê definer và chuẩn bị tài khoản trước khi tạo lại các stored object.

## 3. Trigger

Trigger gắn với một bảng và tự chạy khi xảy ra sự kiện `INSERT`, `UPDATE` hoặc `DELETE`, ở thời điểm `BEFORE` hoặc `AFTER`. Trigger thường chứa quy tắc kiểm tra dữ liệu, ghi audit hoặc cập nhật bảng liên quan. Mất trigger có thể khiến dữ liệu sau khôi phục không còn tuân theo quy tắc cũ.

`mysqldump` xuất trigger theo mặc định. Có thể ghi rõ `--triggers` trong lệnh để thể hiện chủ đích và tránh nhầm lẫn khi đọc script backup:

```bash
mysqldump \
  --single-transaction \
  --routines \
  --triggers \
  --databases sales_db \
  > sales_db.sql
```

Nếu dùng `--skip-triggers`, trigger sẽ bị loại khỏi dump. Không dùng tùy chọn này nếu trigger là một phần của logic ứng dụng.

Kiểm tra định nghĩa trigger bằng:

```sql
SHOW CREATE TRIGGER sales_db.orders_audit_bu;

SELECT TRIGGER_SCHEMA,
       TRIGGER_NAME,
       EVENT_MANIPULATION,
       EVENT_OBJECT_TABLE,
       ACTION_TIMING,
       DEFINER
FROM information_schema.TRIGGERS
WHERE TRIGGER_SCHEMA = 'sales_db';
```

Trigger có thể phụ thuộc vào routine, bảng audit, tài khoản definer hoặc thứ tự thực thi với trigger khác trên cùng bảng. Khi phục hồi thủ công, hãy khôi phục các bảng phụ thuộc và tài khoản definer trước. Nếu nạp dữ liệu bằng các câu `INSERT` trong lúc trigger đã được tạo, trigger có thể chạy trên từng dòng và tạo thêm audit record hoặc side effect. Với quy trình nạp dữ liệu lớn, hãy xác định thứ tự tạo trigger phù hợp và kiểm tra tác động trước khi đưa hệ thống vào hoạt động.

## 4. Event và event scheduler

Event là tác vụ SQL được MySQL thực thi theo lịch, ví dụ đóng kỳ, dọn dữ liệu cũ hoặc tổng hợp số liệu hằng ngày. Định nghĩa event gồm lịch chạy, thời điểm bắt đầu/kết thúc, trạng thái bật/tắt (`ENABLE`/`DISABLE` trong DDL; `ENABLED`/`DISABLED` khi xem qua `INFORMATION_SCHEMA.EVENTS`), definer và câu lệnh thực thi.

`mysqldump` không xuất event theo mặc định. Cần thêm `--events`:

```bash
mysqldump \
  --single-transaction \
  --routines \
  --triggers \
  --events \
  --databases sales_db \
  > sales_db.sql
```

Kiểm tra event và cấu hình scheduler:

```sql
SHOW CREATE EVENT sales_db.purge_expired_sessions;

SELECT EVENT_SCHEMA,
       EVENT_NAME,
       STATUS,
       DEFINER,
       TIME_ZONE,
       EVENT_DEFINITION
FROM information_schema.EVENTS
WHERE EVENT_SCHEMA = 'sales_db';

SHOW VARIABLES LIKE 'event_scheduler';
```

Có hai khái niệm riêng:

- **Định nghĩa event** được lưu trong database và được xuất bằng `--events`.
- **Event scheduler** là thành phần máy chủ quyết định có thực thi các event đã bật hay không. Trạng thái scheduler là cấu hình máy chủ, không được thay thế chỉ bằng việc dump schema.

Khi phục hồi hoặc diễn tập trên máy chủ thử nghiệm, nên tắt scheduler trước khi nạp dữ liệu và kiểm tra event:

```sql
SET GLOBAL event_scheduler = OFF;
```

Sau khi xác minh definer, lịch chạy, timezone, trạng thái event và các phụ thuộc, mới bật scheduler theo chính sách môi trường:

```sql
SET GLOBAL event_scheduler = ON;
```

Lệnh thay đổi biến toàn cục cần quyền quản trị thích hợp; nếu biến được đặt là `DISABLED` lúc khởi động, không thể bật nó bằng `SET GLOBAL`. Hãy kiểm tra file cấu hình và kế hoạch vận hành trước khi thay đổi. Trên môi trường production, tránh để hai máy chủ cùng chạy event nghiệp vụ sau khi clone hoặc restore nếu điều đó có thể gửi email, tạo thanh toán hoặc xử lý dữ liệu hai lần.

## 5. User, role và quyền truy cập

Database dump không đồng nghĩa với bản sao lưu đầy đủ danh tính và quyền truy cập. Tài khoản MySQL được xác định bởi cả user và host, ví dụ `'app_api'@'10.%'`; `'app_api'@'localhost'` là một tài khoản khác và có thể có quyền khác.

Thông tin cần kiểm kê cho mỗi tài khoản gồm:

- Tên user và host.
- Authentication plugin và thông tin xác thực được MySQL xuất qua câu lệnh quản trị.
- Yêu cầu TLS, giới hạn tài nguyên, thời hạn mật khẩu và trạng thái khóa tài khoản.
- Quyền global, database, table, column, routine và proxy nếu có.
- Role được cấp, role lồng nhau, `WITH ADMIN OPTION` và default role.
- Các role toàn máy chủ như `mandatory_roles`, cùng cấu hình `activate_all_roles_on_login`.

### 5.1. Xuất định nghĩa tài khoản

`SHOW CREATE USER` trả về câu lệnh tạo tài khoản cùng các thuộc tính xác thực và bảo mật mà MySQL quản lý:

```sql
SHOW CREATE USER 'app_api'@'10.%';
```

Đầu ra có thể chứa chuỗi xác thực nhạy cảm. Hãy lưu file xuất trong vùng được mã hóa, giới hạn quyền đọc và không dán vào ticket, log hoặc kho mã nguồn công khai.

### 5.2. Xuất quyền và role được cấp

`SHOW GRANTS` trả về các câu lệnh thể hiện quyền và role đã cấp cho tài khoản:

```sql
SHOW GRANTS FOR 'app_api'@'10.%';
```

Nếu có role, cần bảo đảm role đó cũng được tạo và cấp quyền trước khi áp dụng grant cho tài khoản. Có thể kiểm tra quyền mở rộng từ một role cụ thể bằng `SHOW GRANTS ... USING`:

```sql
SHOW GRANTS FOR 'app_api'@'10.%'
USING 'r_app_runtime'@'%';
```

### 5.3. Lưu default role và cấu hình role toàn máy chủ

Việc cấp role và việc chọn role mặc định là hai thao tác riêng. Hãy lưu cả câu lệnh `SET DEFAULT ROLE` của tài khoản. Có thể kiểm kê default role trên MySQL 8.0 bằng bảng hệ thống `mysql.default_roles`:

```sql
SELECT USER,
       HOST,
       DEFAULT_ROLE_USER,
       DEFAULT_ROLE_HOST
FROM mysql.default_roles
ORDER BY USER, HOST, DEFAULT_ROLE_USER, DEFAULT_ROLE_HOST;

SHOW VARIABLES LIKE 'activate_all_roles_on_login';
SHOW VARIABLES LIKE 'mandatory_roles';
```

Các bảng trong schema `mysql` là chi tiết triển khai nội bộ; ưu tiên giao diện quản trị như `SHOW CREATE USER`, `SHOW GRANTS` và các câu lệnh `CREATE USER`, `CREATE ROLE`, `GRANT`, `SET DEFAULT ROLE` để tái tạo chính sách. Dùng truy vấn bảng hệ thống như một bước kiểm kê có kiểm soát, không sửa trực tiếp các grant table.

Một quy trình xuất thủ công cho một tài khoản có thể ghi lại các đầu ra sau trong một file bảo mật:

```text
SHOW CREATE USER 'app_api'@'10.%';
SHOW GRANTS FOR 'app_api'@'10.%';
SET DEFAULT ROLE 'r_app_runtime'@'%' TO 'app_api'@'10.%';
```

Hai dòng `SHOW` là câu lệnh kiểm tra để quản trị viên lưu đầu ra. Dòng `SET DEFAULT ROLE` là câu lệnh khôi phục mẫu; thay role và tài khoản bằng giá trị thực đã kiểm kê. Với nhiều tài khoản và role, nên tự động hóa việc xuất/khôi phục bằng quy trình đã kiểm thử hoặc dùng MySQL Shell dump utilities có hỗ trợ xuất user, thay vì chép thủ công từng grant.

### 5.4. Khôi phục tài khoản theo thứ tự

Thứ tự an toàn thường là:

1. Tạo role cần thiết.
2. Tạo user bằng câu lệnh tương đương đầu ra `SHOW CREATE USER`.
3. Cấp quyền đối tượng cho role.
4. Cấp role cho role khác và cho user.
5. Cấu hình default role.
6. Kiểm tra `SHOW GRANTS`, `CURRENT_ROLE()` khi đăng nhập thử và thử các thao tác đại diện.

Nếu object có `DEFINER`, hãy tạo các tài khoản definer cần thiết trước khi phục hồi procedure, function, view, trigger và event. Không cấp thêm quyền quản trị rộng chỉ để làm cho restore chạy qua; hãy xác định chính xác quyền cần có của từng definer.

## 6. Những thành phần ngoài schema cần sao lưu

### 6.1. Cấu hình máy chủ

Lưu các file cấu hình và giá trị quan trọng như `my.cnf` hoặc file cấu hình tương đương, `server_id`, `log_bin`, `binlog_format`, `gtid_mode`, `event_scheduler`, cấu hình TLS, plugin/component và tham số InnoDB. Ghi lại phiên bản MySQL, phiên bản plugin và topology source/replica để có thể dựng lại môi trường tương thích.

Không sao chép nguyên file cấu hình từ máy chủ này sang máy chủ khác mà không rà soát các giá trị định danh và đường dẫn. Ví dụ, `server_id`, thư mục dữ liệu, socket, vị trí log và cấu hình replication phải phù hợp với máy chủ đích.

### 6.2. Keyring, khóa mã hóa và chứng thư

Nếu dùng mã hóa tablespace, redo log hoặc backup, cần bảo toàn keyring và khóa tương ứng. File dữ liệu mã hóa mà không có khóa phù hợp có thể không khôi phục được. Chứng thư và private key TLS cũng cần được lưu an toàn nếu ứng dụng hoặc replication yêu cầu chúng.

Khóa mã hóa và file backup dữ liệu phải được kiểm soát truy cập độc lập. Lưu bản sao khóa ở vị trí bảo vệ riêng, có quy trình phục hồi quyền truy cập và kiểm tra khả năng giải mã định kỳ. Không đặt khóa và bản backup duy nhất trong cùng một vị trí có cùng rủi ro mất mát.

### 6.3. Plugin, component và UDF

Một routine hoặc event có thể gọi user-defined function (UDF), plugin hoặc component. Dump SQL chỉ giữ định nghĩa SQL; nó không đóng gói thư viện nhị phân, file cấu hình hoặc dependency của hệ điều hành. Hãy lưu tên, phiên bản, nguồn cài đặt, checksum và hướng dẫn cài đặt lại các thành phần ngoài này.

### 6.4. Binary log và metadata replication

Binary log lưu các thay đổi đã được ghi nhận trên máy chủ và có thể được phát lại sau một full backup để phục hồi đến một thời điểm. Nếu cần point-in-time recovery (PITR), phải lưu liên tục binary log từ mốc backup, đồng thời ghi nhận vị trí log hoặc GTID tương ứng với bản backup.

Một số lệnh kiểm tra:

```sql
SHOW VARIABLES LIKE 'log_bin';
SHOW VARIABLES LIKE 'gtid_mode';
SHOW BINARY LOGS;
SELECT @@GLOBAL.gtid_executed;
```

`SHOW BINARY LOGS` cần quyền phù hợp. Hãy đưa việc xoay vòng, sao chép ra nơi lưu trữ an toàn và chính sách purge binary log vào quy trình backup. Không xóa log trước khi bản sao ngoài máy chủ đã được xác nhận và khoảng thời gian PITR cần thiết đã được đáp ứng.

Khi khôi phục, dùng `mysqlbinlog` để đọc log từ đúng mốc đã lưu và phát lại đến thời điểm mục tiêu. Cần đối chiếu GTID hoặc vị trí log để tránh bỏ sót hoặc phát lại giao dịch ngoài ý muốn. Không phát lại binary log một cách tùy tiện trên máy chủ đã có dữ liệu mới.

## 7. Tạo logical backup với mysqldump

Ví dụ sau sao lưu một database ứng dụng cùng routines, triggers và events:

```bash
mysqldump \
  --host=db01.example.internal \
  --user=backup_operator \
  --password \
  --single-transaction \
  --routines \
  --triggers \
  --events \
  --hex-blob \
  --databases sales_db \
  > sales_db_full.sql
```

`--password` không kèm giá trị để chương trình hỏi mật khẩu tương tác. Trong automation, hãy dùng cơ chế quản lý credential phù hợp như login path hoặc secret manager; tránh ghi mật khẩu trực tiếp vào command line, script hoặc lịch sử shell.

| Tùy chọn | Tác dụng |
|---|---|
| `--single-transaction` | Tạo consistent snapshot cho các bảng transactional như InnoDB mà không khóa toàn bộ bảng trong suốt dump |
| `--routines` | Xuất procedure và function |
| `--triggers` | Xuất trigger; đây là mặc định của `mysqldump`, nhưng ghi rõ giúp lệnh dễ kiểm tra |
| `--events` | Xuất event; cần chỉ định rõ |
| `--hex-blob` | Biểu diễn dữ liệu nhị phân theo dạng hex trong dump |
| `--databases sales_db` | Xuất database được nêu, gồm cả câu lệnh tạo/chọn database |

`--single-transaction` không tạo snapshot nhất quán cho các bảng không dùng transactional engine như MyISAM. Nó cũng không bảo vệ dump trước các thay đổi DDL đồng thời như `ALTER TABLE`, `DROP TABLE`, `RENAME TABLE` hoặc `TRUNCATE TABLE`. Trong thời gian backup, cần có quy trình kiểm soát thay đổi schema. Nếu database có bảng không transactional hoặc yêu cầu snapshot nhất quán trên nhiều engine, hãy chọn phương án khóa hoặc backup phù hợp và đánh giá tác động downtime.

Để dump nhiều database, có thể dùng `--databases db1 db2`. `--all-databases` tạo dump toàn bộ database, bao gồm schema hệ thống `mysql`. Việc có dump schema `mysql` không có nghĩa nên phục hồi trực tiếp các bảng hệ thống sang phiên bản khác. Các bảng này gắn với phiên bản và cấu trúc nội bộ của máy chủ; với migration, nên tái tạo user và grant qua câu lệnh quản trị đã xuất, rồi dùng quy trình nâng cấp/chuyển đổi được hỗ trợ.

## 8. Logical backup và physical backup

| Tiêu chí | Logical backup | Physical backup |
|---|---|---|
| Dạng lưu | Câu lệnh SQL và dữ liệu có thể nạp lại | File dữ liệu, tablespace, redo và các file liên quan theo công cụ |
| Công cụ ví dụ | `mysqldump`, MySQL Shell dump utilities | MySQL Enterprise Backup, Percona XtraBackup hoặc công cụ tương thích |
| Phạm vi | Có thể chọn database, bảng và đối tượng | Thường phù hợp để sao lưu/khôi phục toàn instance hoặc phạm vi vật lý được hỗ trợ |
| Tính linh hoạt | Dễ chuyển dữ liệu và chọn lọc object | Thường phục hồi nhanh hơn với dữ liệu lớn, phụ thuộc chặt vào phiên bản và định dạng |
| Phụ thuộc cần giữ | User/grant, cấu hình, binary log và key vẫn cần được xử lý riêng | Cần keyring, cấu hình, binary log và quy trình prepare/restore tương ứng |

Một physical backup toàn instance thường chứa cả dữ liệu hệ thống, vì vậy có thể mang theo grant table của máy chủ nguồn. Tuy nhiên, không nên coi đó là cách chuyển user giữa các phiên bản MySQL khác nhau. Khi restore sang máy chủ khác hoặc nâng cấp phiên bản, phải theo hướng dẫn tương thích của công cụ và phiên bản đích, sau đó kiểm tra user, role, plugin xác thực và quyền.

MySQL Shell dump utilities là lựa chọn logical backup khác. Khi chọn công cụ, hãy kiểm tra rõ phiên bản hỗ trợ, phạm vi schema/instance và tùy chọn có xuất user hay không. Không giả định mọi công cụ dump đều tự động lưu user, grant, default role hoặc file cấu hình máy chủ.

## 9. Thứ tự khôi phục đề xuất

Một trình tự khôi phục có kiểm soát giúp tránh object thiếu definer, event chạy quá sớm hoặc quyền bị cấp sai:

1. **Chuẩn bị máy chủ đích:** cài phiên bản tương thích, cấu hình storage, charset, plugin/component, TLS và keyring. Xác minh khóa giải mã trước khi nạp dữ liệu.
2. **Tắt tác vụ tự động:** giữ `event_scheduler` ở trạng thái `OFF` trong môi trường restore/diễn tập; cô lập máy chủ khỏi các tích hợp có side effect.
3. **Khôi phục danh tính:** tạo user và role cần thiết, gồm các tài khoản `DEFINER`. Cấp quyền tối thiểu cần cho quá trình restore.
4. **Khôi phục schema và dữ liệu:** nạp database, table, view và dữ liệu theo kế hoạch; xác nhận charset, collation, index, constraint và partition.
5. **Khôi phục stored object:** kiểm tra procedure, function, trigger và event; bảo đảm `DEFINER`, `SQL SECURITY`, SQL mode và phụ thuộc đã đúng.
6. **Khôi phục quyền:** áp dụng grants, role membership, default role và cấu hình bảo mật toàn máy chủ; kiểm tra các tài khoản đại diện.
7. **Phục hồi theo thời điểm:** nếu cần, phát lại binary log từ mốc backup đến thời điểm mục tiêu bằng `mysqlbinlog` theo kế hoạch đã xác minh.
8. **Kiểm tra trước khi mở dịch vụ:** xác nhận dữ liệu, object, quyền, event, log và ứng dụng; chỉ bật scheduler và kết nối traffic khi đã duyệt.

Thứ tự cụ thể có thể thay đổi theo công cụ backup. Ví dụ, một dump tự chứa có thể tạo database và object theo thứ tự riêng. Hãy đọc và thử quy trình restore thực tế trên môi trường cô lập trước khi áp dụng cho production.

## 10. Checklist kiểm tra tính đầy đủ

Sau khi tạo backup, đừng chỉ kiểm tra file có tồn tại. Hãy xác nhận từng nhóm đối tượng:

| Kiểm tra | Cách xác nhận |
|---|---|
| Bảng và dữ liệu | Kiểm tra danh sách schema/table, row count đại diện, dung lượng và checksum nếu có |
| Routine | Đối chiếu `information_schema.ROUTINES` hoặc `SHOW CREATE PROCEDURE/FUNCTION` |
| Trigger | Đối chiếu `information_schema.TRIGGERS`, timing, event manipulation và definer |
| Event | Đối chiếu `information_schema.EVENTS`, status, schedule, timezone và definer |
| User/grant | Đối chiếu danh sách user/host, `SHOW CREATE USER`, `SHOW GRANTS` và default role |
| Cấu hình | Lưu phiên bản, file cấu hình, biến quan trọng, plugin và topology |
| Khóa và chứng thư | Xác nhận bản sao có thể truy cập, giải mã và được bảo vệ |
| PITR | Xác nhận binary log liên tục từ mốc backup và có vị trí/GTID để bắt đầu phát lại |
| Khả năng khôi phục | Restore thử trên máy chủ riêng, chạy kiểm tra dữ liệu và thao tác ứng dụng |

Một backup chỉ được xem là đáng tin sau khi đã thử restore. Lưu manifest cùng backup, gồm thời điểm tạo, phiên bản MySQL, danh sách database, tùy chọn dump, vị trí binary log/GTID, checksum, nơi lưu và kết quả lần restore thử gần nhất. Theo dõi cả RPO (mức mất dữ liệu tối đa chấp nhận được) và RTO (thời gian tối đa để khôi phục dịch vụ).

## 11. Lỗi thường gặp

- **Thiếu `--routines`:** bảng và dữ liệu có mặt nhưng procedure/function biến mất. Bổ sung tùy chọn và kiểm tra số lượng routine sau restore.
- **Thiếu `--events`:** event không được xuất, nên tác vụ định kỳ không chạy. Kiểm tra `information_schema.EVENTS` và `event_scheduler`.
- **Tắt trigger ngoài ý muốn:** dump dùng `--skip-triggers`, khiến quy tắc audit hoặc kiểm tra dữ liệu bị mất. Xác nhận tùy chọn thực tế và số lượng trigger.
- **Chỉ backup schema ứng dụng:** user, role và grants không được tái tạo. Xuất danh tính và quyền riêng, hoặc dùng công cụ đã xác nhận có hỗ trợ user export.
- **Definer không tồn tại:** routine, view, trigger hoặc event lỗi khi thực thi. Tạo đúng tài khoản definer và quyền trước khi bật ứng dụng.
- **Event chạy ngay sau restore:** event có thể gửi thông báo hoặc sửa dữ liệu trong lúc kiểm tra. Tắt scheduler, rà soát event rồi mới bật lại.
- **Mất keyring hoặc chứng thư:** file dữ liệu mã hóa có thể không đọc được hoặc kết nối TLS thất bại. Thử khôi phục khóa trên môi trường riêng.
- **Không giữ binary log:** chỉ khôi phục được đến mốc full backup, không thể phát lại giao dịch đến thời điểm gần nhất.
- **Tin vào file dump mà chưa restore thử:** file có thể bị cắt, thiếu quyền đọc, lỗi charset hoặc thiếu dependency. Lên lịch restore diễn tập và đo thời gian thực tế.

## 12. Bài tập tự kiểm tra

1. Một lệnh `mysqldump` có `--triggers` nhưng không có `--routines` và `--events`. Những loại object nào có nguy cơ bị thiếu?
2. Vì sao `SHOW CREATE USER` và `SHOW GRANTS` cần được lưu cùng với dump schema ứng dụng?
3. Một event đã được dump và restore thành công nhưng không chạy. Hãy nêu các thông tin cần kiểm tra.
4. Vì sao cần tạo tài khoản `DEFINER` trước khi khôi phục procedure, trigger hoặc event?
5. Máy chủ dùng InnoDB và cần phục hồi đến 10:35 sáng sau khi backup lúc 02:00. Ngoài full backup, cần lưu gì và cần ghi lại metadata nào?
6. Khi clone production sang môi trường kiểm thử, vì sao nên tắt event scheduler và rà soát user, plugin, chứng thư cùng các tích hợp ngoài?

**Gợi ý đáp án:** (1) Procedure/function và event có thể bị thiếu; trigger vẫn được xuất vì có `--triggers`. (2) Dump schema ứng dụng không đảm bảo xuất user, phương thức xác thực, role và toàn bộ quyền; hai lệnh quản trị giúp tái tạo danh tính và chính sách truy cập. (3) Kiểm tra event có tồn tại và đang `ENABLED`, scheduler có `ON`, thời gian/timezone, definer và quyền của definer. (4) Stored object có thể chạy theo ngữ cảnh definer; tài khoản thiếu hoặc quyền thiếu gây lỗi lúc thực thi. (5) Cần binary log liên tục từ mốc backup, cùng GTID hoặc vị trí log để phát lại đúng đến 10:35. (6) Tránh tác vụ tự động chạy gây side effect, đồng thời bảo đảm môi trường đích có đúng danh tính, dependency và bí mật cần thiết.

## Tài liệu tham khảo

- [MySQL 8.4 Reference Manual: mysqldump](https://dev.mysql.com/doc/refman/8.4/en/mysqldump.html)
- [MySQL 8.4 Reference Manual: mysqldump and Stored Programs](https://dev.mysql.com/doc/refman/8.4/en/mysqldump-stored-programs.html)
- [MySQL 8.4 Reference Manual: SHOW CREATE USER](https://dev.mysql.com/doc/refman/8.4/en/show-create-user.html)
- [MySQL 8.4 Reference Manual: SHOW GRANTS](https://dev.mysql.com/doc/refman/8.4/en/show-grants.html)
- [MySQL 8.4 Reference Manual: Event Scheduler Configuration](https://dev.mysql.com/doc/refman/8.4/en/events-configuration.html)
- [MySQL 8.4 Reference Manual: Point-in-Time Recovery](https://dev.mysql.com/doc/refman/8.4/en/point-in-time-recovery.html)
- [MySQL 8.4 Reference Manual: Backup and Recovery](https://dev.mysql.com/doc/refman/8.4/en/backup-and-recovery.html)
