# Sao lưu và phục hồi

## Charset, collation, SQL mode và cấu hình cần đối chiếu sau restore

Khôi phục một bản backup MySQL thành công về mặt kỹ thuật chưa chắc đã tái tạo đúng môi trường của hệ thống nguồn. Dữ liệu có thể đã được nạp đủ nhưng ứng dụng vẫn hiển thị sai ký tự, truy vấn sắp xếp khác trước, câu lệnh bị từ chối hoặc các tác vụ định kỳ chạy sai thời điểm. Những khác biệt này thường đến từ charset, collation, SQL mode và các biến cấu hình của máy chủ đích.

Trong module `DATABASE_MYSQL`, bạn học cách làm chủ MySQL từ thiết kế bảng, kiểu dữ liệu, khóa và truy vấn SQL đến index, transaction và kiểm soát đồng thời. Bạn cũng thực hành đọc kế hoạch thực thi, tối ưu truy vấn, phân quyền, sao lưu và xử lý các vấn đề vận hành cơ sở dữ liệu quan hệ. Khi làm backup và recovery, các kỹ năng đó cần được áp dụng cả trước và sau khi nạp dữ liệu: phải biết cấu trúc nào được phục hồi, cấu hình nào không nằm trong bản dump, và khác biệt nào có thể làm thay đổi hành vi của ứng dụng.

Bài này tập trung vào việc lập baseline ở máy chủ nguồn, đối chiếu máy chủ đích và xác minh sau restore. Các ví dụ dùng cú pháp MySQL phổ biến; một số biến, collation và tính năng phụ thuộc phiên bản. Luôn kiểm tra phiên bản thực tế trước khi áp dụng.

### 1. Điều gì có thể thay đổi sau restore?

Một bản sao lưu logic như SQL dump thường chứa câu lệnh tạo database, table và dữ liệu; tùy công cụ và tùy chọn, nó có thể chứa thêm view, trigger, routine và event. Nó không tự động tái tạo toàn bộ cấu hình máy chủ như tệp `my.cnf` hoặc `my.ini`, biến khởi động, cấu hình replication, plugin hay chính sách vận hành của hệ điều hành.

Khi đối chiếu sau restore, hãy tách bốn lớp sau:

| Lớp | Nội dung cần kiểm tra | Hậu quả nếu khác nguồn |
|---|---|---|
| Kết nối | Charset và collation của client, connection, results | Ký tự gửi lên hoặc trả về có thể bị chuyển đổi sai; so sánh chuỗi literal có thể khác |
| Metadata schema | Charset/collation mặc định của database, table và từng column | Dữ liệu mới, phép so sánh, sắp xếp và unique index có thể hoạt động khác |
| Ngữ nghĩa SQL | `sql_mode`, chế độ tạo stored program, múi giờ phiên | Câu lệnh có thể lỗi, bị chuyển đổi dữ liệu hoặc chạy với quy tắc khác |
| Cấu hình máy chủ | Phiên bản, table-name case, storage engine, packet size, timezone, replication và event scheduler | Restore có thể thất bại hoặc ứng dụng và tác vụ nền hoạt động khác |

Không nên chỉ so sánh `character_set_server` hay `sql_mode` rồi kết luận hai máy chủ tương đương. Cần kiểm tra cả metadata của đối tượng đã phục hồi và trạng thái session mà ứng dụng sử dụng.

### 2. Charset và collation

**Character set** xác định cách mã hóa ký tự thành byte. **Collation** xác định cách so sánh và sắp xếp chuỗi trong một character set, bao gồm cách xử lý chữ hoa/chữ thường, dấu và một số quy tắc khoảng trắng.

Ví dụ, `utf8mb4` có thể biểu diễn đầy đủ các ký tự Unicode, kể cả emoji và ký tự ngoài Basic Multilingual Plane. Tên `utf8` trong nhiều phiên bản MySQL là alias của `utf8mb3`, chỉ hỗ trợ tối đa ba byte cho một ký tự; khi thiết kế mới, nên dùng tên `utf8mb4` một cách tường minh.

Tên collation thường thể hiện quy tắc so sánh:

- `ai_ci`: accent-insensitive và case-insensitive, tức thường bỏ qua khác biệt dấu và chữ hoa/chữ thường.
- `as_cs`: accent-sensitive và case-sensitive, tức phân biệt dấu và chữ hoa/chữ thường.
- Collation có hậu tố `_bin` dùng quy tắc so sánh nhị phân theo bộ ký tự tương ứng.
- Một số collation thuộc nhóm UCA 9.0, chẳng hạn `utf8mb4_0900_ai_ci`, chỉ có trên các phiên bản MySQL hỗ trợ chúng. Collation cũ và mới cũng có thể khác quy tắc xử lý khoảng trắng cuối chuỗi.

Collation ảnh hưởng trực tiếp đến `WHERE`, `ORDER BY`, `GROUP BY`, phép so sánh join và unique index. Hai mã khách hàng khác nhau về chữ hoa/chữ thường hoặc dấu có thể được xem là bằng nhau dưới collation không phân biệt các khác biệt đó. Vì vậy, đổi collation sau restore có thể làm thay đổi kết quả truy vấn hoặc khiến việc tạo unique index phát sinh duplicate.

#### 2.1. Chuỗi mặc định và phạm vi áp dụng

MySQL có charset/collation ở nhiều cấp:

1. **Server:** `character_set_server` và `collation_server` cung cấp mặc định khi tạo database mới nếu không chỉ định rõ.
2. **Database:** mỗi schema có charset/collation mặc định riêng; mặc định này được dùng khi tạo table mới trong schema nếu câu lệnh không ghi đè.
3. **Table:** table có charset/collation mặc định; các column chuỗi mới có thể kế thừa từ đây.
4. **Column:** column kiểu chuỗi có thể chỉ định charset/collation riêng. Đây là metadata trực tiếp chi phối cách so sánh dữ liệu của column đó.
5. **Connection:** các biến `character_set_client`, `character_set_connection`, `character_set_results` và `collation_connection` điều khiển việc MySQL tiếp nhận, diễn giải và trả chuỗi trong session.

Thay đổi charset mặc định của server hoặc database không tự chuyển đổi các column đã tồn tại. Muốn chuyển dữ liệu và metadata của table, cần một thao tác chuyển đổi tường minh và phải đánh giá ảnh hưởng trước.

#### 2.2. Ghi lại trạng thái charset/collation

Trên cả máy chủ nguồn và máy chủ đích, ghi lại thông tin phiên bản và các biến kết nối/server:

```sql
SELECT
  VERSION() AS mysql_version,
  @@version_comment AS version_comment,
  @@character_set_server AS character_set_server,
  @@collation_server AS collation_server,
  @@character_set_client AS character_set_client,
  @@character_set_connection AS character_set_connection,
  @@character_set_results AS character_set_results,
  @@collation_connection AS collation_connection;
```

Kiểm tra mặc định của database và định nghĩa table:

```sql
SHOW CREATE DATABASE appdb;
SHOW CREATE TABLE appdb.customers;

SELECT TABLE_NAME, ENGINE, TABLE_COLLATION
FROM INFORMATION_SCHEMA.TABLES
WHERE TABLE_SCHEMA = 'appdb'
  AND TABLE_TYPE = 'BASE TABLE'
ORDER BY TABLE_NAME;
```

Kiểm tra các column chuỗi có cấu hình riêng:

```sql
SELECT
  TABLE_NAME,
  COLUMN_NAME,
  CHARACTER_SET_NAME,
  COLLATION_NAME
FROM INFORMATION_SCHEMA.COLUMNS
WHERE TABLE_SCHEMA = 'appdb'
  AND CHARACTER_SET_NAME IS NOT NULL
ORDER BY TABLE_NAME, ORDINAL_POSITION;
```

Cuối cùng, xác minh collation được dump tham chiếu có tồn tại trên máy chủ đích:

```sql
SHOW CHARACTER SET LIKE 'utf8mb4';
SHOW COLLATION LIKE 'utf8mb4_0900_ai_ci';
```

Nếu collation không tồn tại, import có thể dừng với lỗi `Unknown collation`. Ví dụ, một dump tạo từ MySQL 8.0 có thể chứa collation `utf8mb4_0900_ai_ci`, trong khi máy chủ MySQL 5.7 không nhận diện collation này. Cần chọn collation thay thế tương thích sau khi so sánh ngữ nghĩa; thay tên hàng loạt trong dump mà không kiểm tra có thể làm thay đổi quy tắc so sánh và tính duy nhất.

#### 2.3. Charset của kết nối khi import

Client phải gửi nội dung dump bằng charset phù hợp. Với dump UTF-8/utf8mb4, có thể chỉ định charset cho MySQL client:

```bash
mysql --default-character-set=utf8mb4 -u restore_user -p appdb < backup.sql
```

Trong một session SQL, có thể đặt charset kết nối bằng:

```sql
SET NAMES utf8mb4;
-- Nếu collation cụ thể được hỗ trợ và đã được chọn:
SET NAMES utf8mb4 COLLATE utf8mb4_0900_ai_ci;
```

`SET NAMES` đặt các biến charset của session liên quan đến client, connection và results; phiên bản có hỗ trợ cú pháp `COLLATE` sẽ đặt cả `collation_connection`. Lệnh này không đổi charset/collation đã lưu trong table và column. Nó cũng không thể sửa một file dump vốn đã bị mã hóa sai trước khi import.

Khi restore, hãy kiểm tra cách công cụ backup ghi charset trong file SQL. Nhiều bản dump có lệnh thiết lập session riêng; các lệnh đó cũng cần được xem xét nếu bạn đang chuyển giữa phiên bản MySQL khác nhau. Tránh để terminal, script hoặc công cụ trung gian chuyển mã file dump ngoài ý muốn.

#### 2.4. Đổi charset/collation có chủ đích

Nếu cần chuyển một table sang `utf8mb4`, cú pháp thường dùng là:

```sql
ALTER TABLE customers
  CONVERT TO CHARACTER SET utf8mb4
  COLLATE utf8mb4_0900_ai_ci;
```

Chỉ chạy ví dụ này khi máy chủ đích hỗ trợ collation đã chọn và bạn đã xác nhận quy tắc so sánh phù hợp với nghiệp vụ. `CONVERT TO CHARACTER SET` chuyển đổi dữ liệu và metadata của các column chuỗi trong table; thao tác có thể rebuild table, tốn thời gian và dung lượng, đồng thời có thể làm lộ ra xung đột unique key.

Trước khi chuyển đổi, hãy sao lưu, thử trên bản sao và tìm các giá trị có thể trở thành bằng nhau dưới collation mới. Ví dụ kiểm tra theo một collation cụ thể:

```sql
SELECT
  customer_code COLLATE utf8mb4_0900_ai_ci AS code_under_new_collation,
  COUNT(*) AS occurrences
FROM customers
GROUP BY customer_code COLLATE utf8mb4_0900_ai_ci
HAVING COUNT(*) > 1;
```

Kết quả cần được rà soát cùng quy tắc nghiệp vụ trước khi tạo lại unique index. Thay đổi collation có thể làm thay đổi thứ tự sắp xếp và kết quả so sánh ngay cả khi byte dữ liệu không đổi.

### 3. SQL mode và hành vi khi restore

`sql_mode` là tập hợp các chế độ điều khiển cách MySQL phân tích và thực thi SQL. Một số mode kiểm soát tính nghiêm ngặt của dữ liệu; mode khác thay đổi cú pháp hoặc quy tắc kiểm tra truy vấn.

Các mode thường cần chú ý:

- `STRICT_TRANS_TABLES` hoặc `STRICT_ALL_TABLES`: khiến nhiều giá trị sai kiểu, vượt miền hoặc bị cắt cụt trở thành lỗi thay vì chỉ được ép kiểu hoặc phát cảnh báo.
- `ONLY_FULL_GROUP_BY`: kiểm tra chặt các biểu thức trong truy vấn gom nhóm; một truy vấn từng chạy trên máy chủ cũ có thể bị từ chối.
- `ANSI_QUOTES`: dấu nháy kép được hiểu là dấu bao tên định danh, có thể làm hỏng câu SQL vốn dùng dấu nháy kép cho chuỗi.
- `NO_BACKSLASH_ESCAPES`: thay đổi cách xử lý dấu gạch chéo ngược trong literal chuỗi.
- `NO_ZERO_DATE` và `NO_ZERO_IN_DATE`: có thể ảnh hưởng việc chấp nhận ngày tháng có thành phần bằng 0; tình trạng hỗ trợ và cảnh báo phụ thuộc phiên bản.
- `NO_ENGINE_SUBSTITUTION`: ngăn MySQL âm thầm thay storage engine khi engine được yêu cầu không khả dụng.

Danh sách mode mặc định thay đổi theo phiên bản và cấu hình. Không nên chép nguyên `sql_mode` từ một máy chủ khác mà chưa kiểm tra ứng dụng và dữ liệu.

#### 3.1. Đối chiếu global và session

```sql
SELECT
  @@GLOBAL.sql_mode AS global_sql_mode,
  @@SESSION.sql_mode AS session_sql_mode;
```

`GLOBAL` là mặc định áp dụng cho các session mới; `SESSION` là chế độ của kết nối hiện tại. Thay đổi global không tự sửa session đang mở. Vì vậy, một ứng dụng dùng connection pool có thể tiếp tục chạy với session cũ sau khi cấu hình global đã đổi; cần quản lý vòng đời và khởi tạo lại kết nối đúng cách.

Trong một phiên restore thử nghiệm, hãy ghi nhận `@@SESSION.sql_mode` trước khi import và xem dump có câu lệnh thay đổi mode hay không. Nếu dữ liệu cũ chỉ import được khi nới lỏng một mode, hãy xác định chính xác các giá trị vi phạm và lý do chúng tồn tại. Chỉ thay đổi mode trong session restore có kiểm soát khi có quyết định rõ ràng; không tắt strict mode toàn cục để che lỗi dữ liệu. Sau import, kiểm tra warning, lỗi và dữ liệu bị ép kiểu, rồi chạy ứng dụng dưới mode mục tiêu của môi trường đích.

#### 3.2. SQL mode được lưu cùng stored program

MySQL lưu `sql_mode` có hiệu lực tại thời điểm tạo stored procedure, function, trigger và event; khi thực thi, đối tượng có thể dùng mode đã lưu đó thay vì mode hiện tại của session gọi nó. Do đó, chỉ so sánh `@@GLOBAL.sql_mode` sau restore là chưa đủ.

Kiểm tra metadata của routine, trigger và event:

```sql
SELECT ROUTINE_NAME, ROUTINE_TYPE, SQL_MODE
FROM INFORMATION_SCHEMA.ROUTINES
WHERE ROUTINE_SCHEMA = 'appdb';

SELECT TRIGGER_NAME, SQL_MODE
FROM INFORMATION_SCHEMA.TRIGGERS
WHERE TRIGGER_SCHEMA = 'appdb';

SELECT EVENT_NAME, STATUS, SQL_MODE
FROM INFORMATION_SCHEMA.EVENTS
WHERE EVENT_SCHEMA = 'appdb';
```

Với đối tượng quan trọng, lưu cả định nghĩa bằng `SHOW CREATE PROCEDURE`, `SHOW CREATE FUNCTION`, `SHOW CREATE TRIGGER` hoặc `SHOW CREATE EVENT`. Khi tạo lại đối tượng từ dump, session tạo đối tượng có thể quyết định `sql_mode` được lưu. Hãy thiết lập và xác minh mode theo baseline mong muốn trước khi chạy phần DDL này.

### 4. Các cấu hình máy chủ cần đối chiếu

Charset và SQL mode là hai nhóm quan trọng, nhưng không phải toàn bộ cấu hình có thể ảnh hưởng kết quả phục hồi. Hãy ghi baseline nguồn và so sánh với máy chủ đích theo mục tiêu triển khai.

| Cấu hình | Vì sao cần kiểm tra | Lưu ý khi restore |
|---|---|---|
| `VERSION()` và `version_comment` | Khác biệt cú pháp, collation, kiểu dữ liệu và tính năng | Xác minh cả chiều nâng cấp/hạ cấp; không giả định dump từ phiên bản mới chạy nguyên vẹn trên phiên bản cũ |
| `lower_case_table_names` | Quy tắc lưu và so sánh tên database/table | Đặc biệt quan trọng khi chuyển giữa Windows và Linux; trên MySQL 8.0, giá trị được cố định khi khởi tạo data directory |
| `default_storage_engine` và engine từng table | Table có thể phụ thuộc InnoDB hoặc engine/plugin cụ thể | Kiểm tra engine thực tế trong `INFORMATION_SCHEMA.TABLES`, không chỉ xem mặc định server |
| `time_zone` và `system_time_zone` | Ảnh hưởng cách diễn giải và hiển thị `TIMESTAMP` theo session | Chuẩn hóa UTC cho quy trình dump/restore và kiểm thử múi giờ ứng dụng; `DATETIME` không tự chuyển đổi theo session timezone |
| `max_allowed_packet` | Gói dữ liệu lớn có thể làm import thất bại | Kiểm tra khi dump có BLOB, JSON hoặc hàng lớn; điều chỉnh có kiểm soát ở client/server nếu cần |
| `transaction_isolation` và `autocommit` | Có thể làm thay đổi hành vi transaction của ứng dụng | Tên biến có thể khác giữa các phiên bản; kiểm tra bằng `SHOW VARIABLES` và kiểm thử workload |
| `innodb_page_size` | Ảnh hưởng định dạng trang InnoDB và một số giới hạn vật lý | Được chọn khi khởi tạo instance; đặc biệt cần đối chiếu khi dùng physical backup hoặc yêu cầu tương thích vật lý. Logical dump không nhất thiết phải có cùng page size |
| `event_scheduler` | Event được restore có thể bắt đầu chạy theo lịch | Giữ scheduler ở trạng thái phù hợp trong giai đoạn xác minh; chỉ bật khi dữ liệu và lịch chạy đã sẵn sàng |
| `server_id`, `log_bin`, `gtid_mode` | Ảnh hưởng replication và phục hồi theo binlog | Nếu máy đích tham gia replication, cấu hình định danh và GTID phải theo topology; không sao chép nguyên cấu hình định danh của nguồn một cách máy móc |

Hai biến cần đặc biệt chú ý khi chuyển hệ điều hành là `lower_case_table_names` và tên đối tượng. Chế độ phân biệt hoa thường trên nguồn có thể tạo ra hai table mà máy đích không thể phân biệt. Hãy kiểm tra các tên có khác nhau chỉ bởi chữ hoa/chữ thường trước khi restore. Với MySQL 8.0, cần chọn `lower_case_table_names` đúng trước khi khởi tạo data directory; không thể đổi tùy ý sau khi đã tạo dữ liệu.

`innodb_page_size` cũng là cấu hình khởi tạo. Nếu dùng logical backup, table được tạo lại qua SQL và có thể phục hồi trên instance có page size khác khi các điều kiện khác tương thích. Với physical backup, phải tuân theo giới hạn tương thích của công cụ và phiên bản; không suy luận khả năng phục hồi vật lý từ việc logical dump đã import được.

Để kiểm tra nhanh một số biến trên máy chủ đích:

```sql
SHOW VARIABLES WHERE Variable_name IN (
  'lower_case_table_names',
  'default_storage_engine',
  'time_zone',
  'system_time_zone',
  'max_allowed_packet',
  'innodb_page_size',
  'event_scheduler',
  'server_id',
  'log_bin',
  'gtid_mode'
);

SHOW VARIABLES LIKE 'transaction_isolation';
SHOW VARIABLES LIKE 'tx_isolation';
```

Một số biến chỉ có trên một số phiên bản hoặc yêu cầu quyền đọc phù hợp. Nếu biến không tồn tại, hãy ghi rõ khác biệt phiên bản thay vì coi đó là giá trị bằng nhau.

### 5. Quy trình đối chiếu trước và sau restore

Một quy trình có thể lặp lại giúp tránh phụ thuộc vào trí nhớ của người vận hành.

**Bước 1 — Ghi baseline từ nguồn.** Lưu phiên bản MySQL, biến charset/collation, global và session SQL mode, múi giờ, `lower_case_table_names`, engine, packet size và các cấu hình liên quan replication/event. Lưu `SHOW CREATE DATABASE` và `SHOW CREATE TABLE` cho schema quan trọng; xuất metadata của routine, trigger và event.

**Bước 2 — Xác minh khả năng tương thích.** So sánh phiên bản nguồn/đích, kiểm tra collation có sẵn, storage engine và plugin cần thiết. Xác định trước các khác biệt không thể thay đổi sau khi khởi tạo instance như `lower_case_table_names` và `innodb_page_size`.

**Bước 3 — Chuẩn bị instance đích.** Cấu hình biến máy chủ theo thiết kế đích, tạo database với charset/collation đã thống nhất, chuẩn bị tài khoản restore và dung lượng lưu trữ. Nếu dump có event, cân nhắc giữ `event_scheduler` ở trạng thái tắt trong thời gian nạp và xác minh.

**Bước 4 — Import với charset và session phù hợp.** Dùng MySQL client với `--default-character-set` phù hợp nội dung dump. Kiểm tra các câu lệnh `SET NAMES`, `SET SQL_MODE` và `SET TIME_ZONE` có trong file. Ghi lại mọi lỗi và warning; không bỏ qua lỗi import giữa chừng.

**Bước 5 — Đối chiếu metadata sau import.** Chạy lại các truy vấn ở phần charset/collation, xem `SHOW CREATE DATABASE`, `SHOW CREATE TABLE`, kiểm tra column-level collation, storage engine và SQL mode lưu cùng stored program. Xác nhận các đối tượng quan trọng đã được tạo đầy đủ.

**Bước 6 — Kiểm tra dữ liệu và hành vi.** So sánh số lượng hàng, các tổng kiểm soát nghiệp vụ và mẫu dữ liệu với nguồn. Kiểm thử chuỗi có dấu, chữ hoa/thường, ký tự ngoài BMP, giá trị gần nhau ở unique key, ngày giờ, transaction và các truy vấn `GROUP BY`. Chạy kiểm thử ứng dụng bằng session có charset, collation, timezone và SQL mode như môi trường production.

**Bước 7 — Bật các tác vụ nền.** Sau khi xác nhận dữ liệu và quyền, bật event scheduler nếu cần; cấu hình replication/binlog theo topology; theo dõi log và kiểm tra các job đầu tiên. Ghi lại những khác biệt đã được chấp nhận và người chịu trách nhiệm.

### 6. Một số lỗi thường gặp sau restore

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| `Unknown collation` khi import | Dump tham chiếu collation không có trên phiên bản đích | Kiểm tra phiên bản và danh sách collation; chọn phương án tương thích sau khi kiểm thử quy tắc so sánh |
| Tiếng Việt hoặc emoji bị lỗi | Charset của file, client, connection hoặc column không khớp | Kiểm tra byte của dump, `--default-character-set`, `SET NAMES` và metadata column; xác định dữ liệu hỏng ở bước nào |
| Import lỗi ngày bằng 0 hoặc giá trị ngoài miền | SQL mode đích nghiêm ngặt hơn nguồn | Xem câu lệnh và dữ liệu vi phạm; quyết định sửa dữ liệu hoặc dùng session restore có kiểm soát, rồi kiểm thử lại dưới mode mục tiêu |
| Truy vấn `GROUP BY` bị từ chối | `ONLY_FULL_GROUP_BY` khác với nguồn | Sửa truy vấn cho xác định rõ giá trị tổng hợp hoặc biểu thức nhóm; không vội tắt mode toàn cục |
| Unique index tạo không thành công sau đổi collation | Các chuỗi trước đây khác nhau nay được collation xem là bằng nhau | Tìm và xử lý xung đột theo quy tắc nghiệp vụ trước khi tạo index |
| Tên table không tìm thấy sau khi chuyển hệ điều hành | `lower_case_table_names` hoặc tên có khác biệt hoa/thường | So sánh metadata tên đối tượng và cấu hình khởi tạo; xử lý xung đột tên trước khi chuyển |
| Timestamp hiển thị lệch giờ | Session timezone hoặc timezone tables khác nhau | Kiểm tra `@@time_zone`, `@@system_time_zone`, cấu hình ứng dụng và cách dump/restore diễn giải timestamp |
| Event chạy quá sớm hoặc không chạy | `event_scheduler` hoặc trạng thái event khác kỳ vọng | Kiểm tra `INFORMATION_SCHEMA.EVENTS`, trạng thái scheduler và lịch chạy trước khi kích hoạt |

Không dùng `SET NAMES` để chữa dữ liệu đã bị ghi sai mã hóa. Lệnh đó chỉ điều khiển cách session trao đổi chuỗi từ thời điểm được chạy. Nếu dữ liệu trong table đã bị biến thành chuỗi ký tự sai, cần xác định chính xác encoding ban đầu và lập kế hoạch chuyển đổi dữ liệu có backup, thử nghiệm và đối chiếu.

### 7. Checklist xác minh

Trước khi bàn giao một database vừa restore, hãy xác nhận các mục sau:

- [ ] Phiên bản MySQL và các tính năng cần thiết tương thích với nguồn.
- [ ] Charset/collation server, database, table, column và connection đã được ghi nhận và đối chiếu.
- [ ] Các collation được tham chiếu trong DDL tồn tại trên máy chủ đích.
- [ ] Các quy tắc so sánh chuỗi, unique index và thứ tự sắp xếp đã được kiểm thử.
- [ ] Global/session `sql_mode` đúng thiết kế; routine, trigger và event có mode lưu phù hợp.
- [ ] `lower_case_table_names`, storage engine, timezone, packet size và các biến liên quan đã được kiểm tra.
- [ ] Các cấu hình replication, GTID, event scheduler và tác vụ nền được kích hoạt đúng thời điểm.
- [ ] Không còn lỗi hoặc warning import chưa được giải thích; số lượng hàng và tổng kiểm soát nghiệp vụ khớp.
- [ ] Ứng dụng đã được thử bằng cấu hình kết nối thực tế và các truy vấn quan trọng cho kết quả mong đợi.
- [ ] Baseline nguồn, khác biệt được chấp nhận và kết quả kiểm thử đã được lưu lại.

### 8. Bài tập thực hành

Một hệ thống đang chạy MySQL 8.0 với database `sales` dùng `utf8mb4`, một số table dùng `utf8mb4_0900_ai_ci`, SQL mode có `STRICT_TRANS_TABLES` và `ONLY_FULL_GROUP_BY`. Đội vận hành cần phục hồi logical dump sang một máy chủ mới có phiên bản và cấu hình khác.

1. Viết các câu lệnh để ghi lại phiên bản, charset/collation server, session charset, global/session SQL mode và timezone trên cả nguồn lẫn đích.
2. Truy vấn `INFORMATION_SCHEMA` để liệt kê table và column có collation riêng trong schema `sales`.
3. Nếu máy chủ đích không hỗ trợ `utf8mb4_0900_ai_ci`, bạn cần xác minh những đặc tính nào trước khi chọn collation thay thế?
4. Giải thích vì sao một unique index có thể thất bại sau khi đổi từ collation phân biệt dấu sang collation không phân biệt dấu.
5. Một stored procedure hoạt động khác sau restore dù `@@GLOBAL.sql_mode` trên hai máy chủ giống nhau. Hãy kiểm tra metadata nào để tìm nguyên nhân.
6. Vì sao không nên tắt strict mode toàn cục chỉ để import một dump có dữ liệu ngày tháng không hợp lệ?
7. Lập danh sách cấu hình cần chốt trước khi chuyển database từ Windows sang Linux, đặc biệt với tên table có chữ hoa/thường.

### 9. Nguyên tắc vận hành

Một lần restore chỉ được xem là hoàn tất khi cả dữ liệu, metadata và hành vi ứng dụng đều được xác minh. Hãy lưu baseline cấu hình cùng backup, so sánh theo từng lớp, kiểm thử những khác biệt có thể làm đổi kết quả truy vấn và ghi nhận quyết định chuyển đổi. Charset quyết định cách biểu diễn ký tự; collation quyết định cách so sánh; SQL mode quyết định nhiều quy tắc thực thi; các biến máy chủ và session hoàn thiện môi trường mà ứng dụng thực sự chạy. Đối chiếu đầy đủ các lớp này giúp bản phục hồi tái tạo được hành vi mong đợi và giảm rủi ro phát hiện sai lệch sau khi đưa hệ thống trở lại phục vụ.
