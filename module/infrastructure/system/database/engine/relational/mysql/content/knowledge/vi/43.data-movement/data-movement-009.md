# Đối chiếu bộ ký tự, collation, múi giờ và SQL mode giữa nguồn/đích

Di chuyển dữ liệu MySQL giữa hai môi trường có thể hoàn tất mà không báo lỗi nhưng kết quả vẫn khác nguồn. Ký tự có dấu bị biến dạng, chuỗi được sắp xếp theo thứ tự khác, giá trị thời gian lệch giờ hoặc câu lệnh trước đây chạy được lại bị từ chối sau restore. Những sai khác này thường bắt nguồn từ cấu hình phiên kết nối, schema, phiên bản MySQL hoặc SQL mode giữa source và destination.

Trước khi dump/import, hãy lập một bản kiểm kê cấu hình ở cả hai phía và so sánh theo từng lớp. Bốn nhóm cần kiểm tra là **character set**, **collation**, **time zone** và **SQL mode**. Chúng ảnh hưởng đến cách byte được diễn giải thành ký tự, cách so sánh/sắp xếp chuỗi, cách chuyển đổi giá trị thời gian và cách MySQL phân tích/thực thi SQL.

## 1. Vì sao cấu hình nguồn và đích phải tương thích?

Giả sử source dùng `utf8mb4` với collation `utf8mb4_0900_ai_ci`, còn destination dùng một phiên bản MySQL cũ không hỗ trợ collation đó. Nếu import nguyên DDL, câu `CREATE TABLE` có thể thất bại. Nếu người vận hành tự đổi sang collation khác để import được, các phép so sánh, `ORDER BY`, `GROUP BY` hoặc unique index có thể cho kết quả khác.

Tương tự, nếu ứng dụng ghi `2026-11-19 10:00:00` vào cột `TIMESTAMP` trong session có timezone `+07:00`, MySQL quy đổi giá trị theo UTC khi lưu. Nếu restore hoặc đọc bằng session `+00:00` mà không hiểu quy tắc này, thời gian hiển thị sẽ khác. Với `DATETIME`, MySQL lưu giá trị ngày giờ dạng lịch mà không tự chuyển đổi theo timezone session.

SQL mode cũng có thể làm dữ liệu import thất bại hoặc thay đổi cách câu lệnh được xử lý. Ví dụ, source cho phép dữ liệu ngày bằng 0 trong một mode cũ, còn destination bật `STRICT_TRANS_TABLES` và `NO_ZERO_DATE`; import có thể dừng khi gặp giá trị không hợp lệ. Một ứng dụng dựa vào phép chia cho 0 hoặc cách xử lý chuỗi escape cũ cũng có thể hoạt động khác khi mode thay đổi.

Không nên chỉ so sánh biến `character_set_server` hay `time_zone` rồi kết luận hai hệ thống tương thích. Cần kiểm tra cấu hình ở cấp server, database, table, column và connection, đồng thời xem metadata thực tế trong DDL và dữ liệu.

## 2. Kiểm kê character set ở source và destination

Character set xác định tập ký tự có thể biểu diễn và cách mã hóa ký tự thành byte. Trong MySQL, cấu hình có thể tồn tại ở nhiều lớp:

| Lớp | Biến/metadata thường kiểm tra | Ảnh hưởng |
|---|---|---|
| Server | `character_set_server` | Giá trị mặc định khi tạo database nếu không chỉ định khác. |
| Database | `character_set_database`, `INFORMATION_SCHEMA.SCHEMATA` | Giá trị mặc định cho table mới trong database. |
| Table | `INFORMATION_SCHEMA.TABLES.TABLE_COLLATION` và DDL | Mặc định cho column ký tự mới trong table. |
| Column | `INFORMATION_SCHEMA.COLUMNS.CHARACTER_SET_NAME` | Cách lưu và diễn giải dữ liệu của từng cột. |
| Connection | `character_set_client`, `character_set_connection`, `character_set_results` | Cách MySQL nhận câu lệnh, xử lý literal và trả kết quả cho client. |

Kiểm tra cấu hình server và session:

```sql
SHOW VARIABLES LIKE 'character_set%';
SHOW VARIABLES LIKE 'collation%';

SELECT
    @@GLOBAL.character_set_server AS global_server_charset,
    @@GLOBAL.collation_server AS global_server_collation,
    @@SESSION.character_set_client AS session_client_charset,
    @@SESSION.character_set_connection AS session_connection_charset,
    @@SESSION.character_set_results AS session_results_charset,
    @@SESSION.collation_connection AS session_connection_collation;
```

Kiểm tra database, table và column:

```sql
SELECT
    SCHEMA_NAME,
    DEFAULT_CHARACTER_SET_NAME,
    DEFAULT_COLLATION_NAME
FROM INFORMATION_SCHEMA.SCHEMATA
WHERE SCHEMA_NAME NOT IN ('mysql', 'sys', 'performance_schema', 'information_schema')
ORDER BY SCHEMA_NAME;

SELECT
    TABLE_SCHEMA,
    TABLE_NAME,
    TABLE_COLLATION
FROM INFORMATION_SCHEMA.TABLES
WHERE TABLE_TYPE = 'BASE TABLE'
  AND TABLE_SCHEMA NOT IN ('mysql', 'sys', 'performance_schema', 'information_schema')
ORDER BY TABLE_SCHEMA, TABLE_NAME;

SELECT
    TABLE_SCHEMA,
    TABLE_NAME,
    COLUMN_NAME,
    DATA_TYPE,
    CHARACTER_SET_NAME,
    COLLATION_NAME
FROM INFORMATION_SCHEMA.COLUMNS
WHERE CHARACTER_SET_NAME IS NOT NULL
  AND TABLE_SCHEMA NOT IN ('mysql', 'sys', 'performance_schema', 'information_schema')
ORDER BY TABLE_SCHEMA, TABLE_NAME, ORDINAL_POSITION;
```

Chạy cùng các truy vấn trên source và destination, xuất kết quả thành file rồi đối chiếu. Các giá trị mặc định có thể khác nhau dù DDL của từng column không đổi. `character_set_database` là biến session liên quan database mặc định hiện hành và đã bị deprecated trong các phiên bản MySQL mới; khi kiểm kê nên ưu tiên metadata `INFORMATION_SCHEMA.SCHEMATA` để biết chính xác default của từng schema.

### Chọn utf8mb4 có chủ đích

Với dữ liệu ứng dụng hiện đại, `utf8mb4` thường là lựa chọn phù hợp vì biểu diễn đầy đủ Unicode, bao gồm ký tự ngoài BMP và emoji. Không nên nhầm `utf8` với UTF-8 đầy đủ trong MySQL: tên `utf8` lịch sử thường là alias của `utf8mb3`, chỉ biểu diễn tối đa ba byte mỗi ký tự; `utf8mb3` đã deprecated trong các phiên bản mới.

Khi tạo schema mới, chỉ định rõ charset và collation:

```sql
CREATE DATABASE appdb
  CHARACTER SET utf8mb4
  COLLATE utf8mb4_0900_ai_ci;
```

Collation `utf8mb4_0900_ai_ci` là ví dụ cho MySQL 8.0 trở lên. Nếu destination là phiên bản cũ hơn, collation này có thể không tồn tại. Hãy chọn một collation được cả hai phiên bản hỗ trợ và phù hợp quy tắc so sánh của ứng dụng, hoặc nâng cấp destination trước khi import. Không thay thế tự động bằng `utf8mb4_general_ci` chỉ để bỏ lỗi DDL mà chưa đánh giá ảnh hưởng.

## 3. Kiểm tra collation và ngữ nghĩa so sánh

Collation xác định cách so sánh và sắp xếp chuỗi trong một character set. Các hậu tố thường gặp:

- `ai`: accent-insensitive, thường coi chữ có và không dấu tương đương trong so sánh.
- `as`: accent-sensitive, phân biệt dấu.
- `ci`: case-insensitive, thường không phân biệt chữ hoa và chữ thường.
- `cs`: case-sensitive, phân biệt hoa thường.
- `bin`: so sánh theo giá trị nhị phân/code unit thay vì quy tắc ngôn ngữ thông thường.

Ví dụ, dưới một collation không phân biệt hoa thường và dấu, các chuỗi `Cafe`, `café` và `CAFE` có thể được xem là tương đương. Điều này tác động trực tiếp đến `WHERE`, `JOIN`, `GROUP BY`, `ORDER BY` và unique index.

Kiểm tra các collation mà server hỗ trợ:

```sql
SHOW COLLATION WHERE Charset = 'utf8mb4';
```

Thử nghiệm quy tắc so sánh trước khi chuyển dữ liệu:

```sql
SELECT
    _utf8mb4'Cafe' COLLATE utf8mb4_0900_ai_ci =
    _utf8mb4'café' COLLATE utf8mb4_0900_ai_ci AS accent_case_insensitive,
    _utf8mb4'Cafe' COLLATE utf8mb4_0900_as_cs =
    _utf8mb4'café' COLLATE utf8mb4_0900_as_cs AS accent_case_sensitive;
```

Tên collation cụ thể phải có trên phiên bản server đang chạy. Khi thử nghiệm trên phiên bản cũ, thay bằng collation tương ứng được hỗ trợ và ghi rõ kết quả.

Một rủi ro lớn khi đổi collation là **trùng giá trị theo quy tắc mới**. Ví dụ, source dùng collation phân biệt hoa thường nên có thể chứa cả `UserA` và `usera`; destination dùng collation không phân biệt hoa thường có thể coi hai giá trị đó là một. Khi import vào unique index, hàng thứ hai có thể gây duplicate-key error. Tương tự, thay đổi quy tắc dấu hoặc khoảng trắng cuối chuỗi có thể ảnh hưởng so sánh và uniqueness.

Trước khi đổi collation cho cột có unique index, hãy tìm các nhóm giá trị có thể trở thành tương đương theo collation đích. Có thể tạo bản sao thử nghiệm và chạy truy vấn nhóm trên biểu thức ép collation:

```sql
SELECT
    username COLLATE utf8mb4_0900_ai_ci AS normalized_username,
    COUNT(*) AS row_count
FROM appdb.users
GROUP BY username COLLATE utf8mb4_0900_ai_ci
HAVING COUNT(*) > 1;
```

Thử nghiệm này phải dùng collation thực sự dự định áp dụng. Với dữ liệu lớn, cân nhắc tạo bảng staging và index thử để phát hiện xung đột trước khi đổi schema production.

## 4. Character set của connection và dữ liệu bị lỗi mã hóa

Ngay cả khi column dùng `utf8mb4`, dữ liệu vẫn có thể bị hỏng nếu client gửi byte theo charset khác hoặc MySQL diễn giải sai charset của literal. Các biến connection có vai trò riêng:

- `character_set_client`: charset mà client dùng để gửi câu lệnh.
- `character_set_connection`: charset MySQL dùng khi chuyển literal và xử lý biểu thức chuỗi trong câu lệnh.
- `character_set_results`: charset MySQL dùng khi gửi kết quả về client.
- `collation_connection`: collation áp dụng cho một số phép so sánh giữa literal/biểu thức trong connection.

Ứng dụng nên khai báo charset kết nối rõ ràng. Ví dụ với client command line:

```bash
mysql --default-character-set=utf8mb4 -h db.example.net -u app_user -p appdb
```

Hoặc thiết lập trong session khi cần kiểm tra:

```sql
SET NAMES utf8mb4 COLLATE utf8mb4_0900_ai_ci;
```

`SET NAMES` cập nhật các biến charset của connection tương ứng. Với ứng dụng, ưu tiên cấu hình charset trong driver/connection string để mỗi kết nối pool đều được khởi tạo đúng. Không chỉ chạy `SET NAMES` thủ công trong một session rồi cho rằng mọi connection của ứng dụng đều đã được cấu hình.

Khi dump/import, kiểm tra encoding của file bằng công cụ phù hợp và giữ nguyên byte. Không chuyển encoding bằng trình soạn thảo hoặc pipeline text nếu chưa xác định charset gốc. File dump có thể chứa chỉ thị charset; đọc phần đầu file và metadata công cụ tạo dump. Nếu import file UTF-8 nhưng client đọc file theo encoding hệ thống khác, dữ liệu có thể hỏng dù column đích dùng `utf8mb4`.

Các dấu hiệu mojibake như `Ã©` thay cho `é` thường cho thấy byte UTF-8 đã bị diễn giải như một charset khác rồi lưu lại. Đổi collation không sửa được byte đã hỏng. Cần xác định dữ liệu đang lưu byte nào, charset được khai báo ở từng lớp và nguồn tạo dữ liệu trước khi thực hiện chuyển đổi có kiểm soát.

## 5. Kiểm kê timezone và hiểu TIMESTAMP/DATETIME

MySQL có timezone toàn cục và timezone theo session. Kiểm tra:

```sql
SELECT
    @@GLOBAL.time_zone AS global_time_zone,
    @@SESSION.time_zone AS session_time_zone,
    @@system_time_zone AS system_time_zone,
    NOW() AS session_now,
    UTC_TIMESTAMP() AS utc_now;

SHOW VARIABLES LIKE 'time_zone';
```

Hai kiểu dữ liệu thời gian quan trọng có hành vi khác nhau:

| Kiểu | Cách lưu và đọc | Khi di chuyển dữ liệu |
|---|---|---|
| `TIMESTAMP` | MySQL chuyển giá trị từ timezone session sang UTC khi lưu và từ UTC sang timezone session khi đọc. | Cần kiểm soát timezone của session import và session ứng dụng; nếu session khác nhau, giá trị hiển thị có thể khác dù instant được giữ nguyên. |
| `DATETIME` | Lưu trực tiếp giá trị ngày giờ như được cung cấp, không tự chuyển theo timezone session. | Phải biết giá trị biểu diễn UTC hay giờ địa phương theo quy ước nghiệp vụ; không tự động cộng/trừ timezone khi dump/import. |

Ví dụ:

```sql
SET time_zone = '+07:00';

CREATE TEMPORARY TABLE time_demo (
    created_at_ts TIMESTAMP,
    created_at_dt DATETIME
);

INSERT INTO time_demo VALUES
    ('2026-11-19 10:00:00', '2026-11-19 10:00:00');

SELECT * FROM time_demo;

SET time_zone = '+00:00';
SELECT * FROM time_demo;
```

`created_at_ts` sẽ được hiển thị theo timezone session hiện tại, còn `created_at_dt` giữ nguyên chuỗi ngày giờ đã lưu. Đây là khác biệt quan trọng khi import dump từ môi trường `+07:00` sang môi trường `+00:00`.

Nếu cột `DATETIME` được ứng dụng quy ước lưu UTC, hãy giữ nguyên giá trị và tiếp tục diễn giải là UTC ở destination. Nếu cột `DATETIME` lưu giờ địa phương, cần ghi rõ timezone vùng nghiệp vụ và xử lý quy đổi trong ứng dụng; bản thân kiểu `DATETIME` không chứa thông tin timezone. Không thể khôi phục chính xác timezone ban đầu chỉ từ giá trị `DATETIME` không kèm metadata.

### Named time zone và CONVERT_TZ

MySQL hỗ trợ timezone offset như `'+00:00'`, `'+07:00'` và tên vùng như `'Asia/Ho_Chi_Minh'`. Tên vùng cần có timezone tables được nạp trong MySQL. Kiểm tra:

```sql
SELECT CONVERT_TZ(
    '2026-11-19 10:00:00',
    '+07:00',
    '+00:00'
) AS utc_value;

SELECT CONVERT_TZ(
    '2026-11-19 10:00:00',
    'Asia/Ho_Chi_Minh',
    '+00:00'
) AS named_zone_value;
```

Nếu kết quả dùng tên vùng là `NULL`, kiểm tra timezone tables trên server và nạp dữ liệu timezone theo quy trình của hệ điều hành/MySQL. Quy tắc DST của named zone có thể thay đổi theo bản cập nhật tzdata; nếu ứng dụng phụ thuộc vào thời điểm lịch sử hoặc lịch tương lai, cần đồng bộ dữ liệu timezone ở source và destination.

`NOW()` trả về thời gian theo session timezone; `UTC_TIMESTAMP()` trả về UTC. `CURRENT_TIMESTAMP` tương tự `NOW()`. `SYSDATE()` có hành vi lấy thời gian thực tại lúc hàm được thực thi và có thể khác `NOW()` trong cùng statement; cần chú ý nếu dữ liệu phụ thuộc hàm này.

## 6. Đối chiếu SQL mode

SQL mode thay đổi cách MySQL phân tích và xác thực câu lệnh. Kiểm tra global và session ở cả source và destination:

```sql
SELECT
    @@GLOBAL.sql_mode AS global_sql_mode,
    @@SESSION.sql_mode AS session_sql_mode;

SHOW VARIABLES LIKE 'sql_mode';
```

Một số mode có thể làm thay đổi hành vi khi import:

| Mode | Tác động cần đánh giá |
|---|---|
| `STRICT_TRANS_TABLES` | Từ chối hoặc xử lý nghiêm giá trị không hợp lệ cho transactional table thay vì âm thầm chuyển thành giá trị mặc định trong nhiều trường hợp. |
| `STRICT_ALL_TABLES` | Áp dụng kiểm tra nghiêm cho nhiều storage engine hơn; cách xử lý một số lỗi ở nontransactional table có thể khác. |
| `NO_ZERO_DATE`, `NO_ZERO_IN_DATE` | Ảnh hưởng việc chấp nhận ngày `0000-00-00` hoặc thành phần ngày bằng 0; hành vi còn phụ thuộc strict mode và phiên bản. Các mode này đã deprecated trong MySQL 8.0. |
| `ONLY_FULL_GROUP_BY` | Từ chối một số truy vấn nhóm có cột không được gom nhóm hoặc không phụ thuộc hàm vào cột nhóm. |
| `ANSI_QUOTES` | Dùng dấu nháy kép cho identifier thay vì string literal. |
| `NO_BACKSLASH_ESCAPES` | Thay đổi cách dấu gạch chéo ngược được xử lý trong string literal. |
| `ERROR_FOR_DIVISION_BY_ZERO` | Ảnh hưởng việc xử lý phép chia cho 0, đặc biệt khi kết hợp strict mode. |
| `PAD_CHAR_TO_FULL_LENGTH` | Ảnh hưởng cách đọc giá trị `CHAR`; mode này đã deprecated trong MySQL 8.0. |

Không nên sao chép toàn bộ `sql_mode` từ source sang destination mà không kiểm tra phiên bản. Một số mode đã deprecated, bị loại bỏ hoặc có hành vi thay đổi theo phiên bản. Hãy so sánh danh sách mode, phân loại mode bắt buộc cho ứng dụng và kiểm thử các câu lệnh có liên quan.

Có thể thiết lập session trong một phiên thử nghiệm:

```sql
SET SESSION sql_mode =
  'STRICT_TRANS_TABLES,ERROR_FOR_DIVISION_BY_ZERO,NO_ENGINE_SUBSTITUTION';
```

`SET SESSION` chỉ ảnh hưởng connection hiện tại. `SET GLOBAL sql_mode` thay đổi giá trị mặc định cho các session mới và thường cần quyền quản trị; nó không tự thay đổi session đang mở. Với cấu hình bền vững qua restart, quản lý trong file cấu hình server hoặc cơ chế cấu hình được tổ chức sử dụng. Không thay global mode trên production chỉ để làm một lần import chạy qua nếu chưa hiểu tác động đến ứng dụng khác.

Stored procedure, function, trigger và event có thể lưu SQL mode tại thời điểm object được tạo. Vì vậy, thay `@@SESSION.sql_mode` ngay trước import dữ liệu không đảm bảo các stored object được tạo sau đó sẽ có cùng hành vi như source. Hãy kiểm tra `SHOW CREATE PROCEDURE`, `SHOW CREATE FUNCTION`, `SHOW CREATE TRIGGER`, `SHOW CREATE EVENT` và thử hành vi của object sau restore.

## 7. Tạo bảng kiểm kê source/destination

Một bảng so sánh giúp review trước migration:

| Hạng mục | Source | Destination | Quyết định |
|---|---|---|---|
| MySQL version | 8.0.x | 8.4.x | Xác nhận cú pháp, collation và SQL mode tương thích. |
| Server charset/collation | `utf8mb4` / `utf8mb4_0900_ai_ci` | `utf8mb4` / collation tương thích | Giữ DDL theo yêu cầu hoặc chuyển đổi có kiểm thử. |
| Database/table/column charset | Metadata thực tế | Metadata thực tế | Tìm column có charset riêng hoặc table chưa được chuẩn hóa. |
| Connection charset | `utf8mb4` | `utf8mb4` | Cấu hình trong driver và kiểm tra từng connection pool. |
| Time zone | `+07:00` | `+00:00` | Kiểm soát session import; phân biệt TIMESTAMP với DATETIME. |
| SQL mode | Danh sách mode thực tế | Danh sách mode thực tế | Kiểm thử dữ liệu và câu lệnh có thể bị ảnh hưởng. |
| Named timezone tables | Có/không | Có/không | Nạp và cập nhật nếu dùng tên vùng. |

Giá trị trong bảng chỉ minh họa cách ghi nhận; phải thay bằng kết quả kiểm kê thật. Cũng cần ghi phiên bản client (`mysqldump`, `mysql` hoặc connector), vì công cụ có thể thêm chỉ thị session vào dump và có hành vi khác giữa phiên bản.

## 8. Quy trình kiểm tra trước khi dump/import

### Bước 1: Chụp cấu hình nguồn

Chạy các truy vấn kiểm kê charset, collation, timezone và SQL mode. Lưu output kèm thời điểm, phiên bản MySQL, `server_uuid` và tên schema. Xuất DDL bằng `SHOW CREATE DATABASE`, `SHOW CREATE TABLE` và kiểm tra stored object nếu chúng nằm trong phạm vi di chuyển.

```sql
SHOW CREATE DATABASE appdb;
SHOW CREATE TABLE appdb.users;
SHOW CREATE PROCEDURE appdb.refresh_summary;
```

### Bước 2: Kiểm tra khả năng tương thích của đích

Trên destination, kiểm tra phiên bản, charset/collation hỗ trợ, SQL mode, timezone tables, giới hạn kiểu dữ liệu và các tính năng DDL. Nếu destination cũ hơn source, đặc biệt chú ý collation mới, kiểu dữ liệu hoặc cú pháp không được hỗ trợ. Nếu destination mới hơn, kiểm tra các thay đổi về default mode và quy tắc so sánh.

### Bước 3: Chạy thử trên schema staging

Import bản sao dữ liệu vào một schema hoặc instance thử nghiệm. Kiểm tra lỗi charset/collation, duplicate key, invalid date, truncation, warning và số lượng hàng. Chạy truy vấn đại diện cho ứng dụng để so sánh kết quả `WHERE`, `JOIN`, `GROUP BY`, `ORDER BY` và phép so sánh ngày giờ.

### Bước 4: Đặt session import rõ ràng

Với dump được tạo bằng `mysqldump`, xem phần đầu file để hiểu các chỉ thị session được ghi. `mysqldump` có tùy chọn `--tz-utc` (thường được bật mặc định trong các bản hiện đại) để đặt timezone UTC khi dump; kiểm tra hành vi của đúng phiên bản và không dùng `--skip-tz-utc` nếu chưa hiểu tác động đến `TIMESTAMP`. Nếu import bằng client, xác định charset file và đặt connection charset tương ứng. Không để môi trường terminal quyết định ngầm encoding.

### Bước 5: Đối soát sau import

So sánh DDL, số hàng, checksum hoặc tổng hợp nghiệp vụ. Kiểm tra lại `INFORMATION_SCHEMA.COLUMNS`, table collation, timezone session và SQL mode. Kiểm tra riêng các bảng có unique index trên cột chuỗi, các cột `TIMESTAMP`/`DATETIME`, stored object và dữ liệu có ký tự ngoài ASCII.

## 9. Ví dụ cấu hình import có kiểm soát

Giả sử dump UTF-8 của source được tạo theo chuẩn UTC và destination dùng `utf8mb4`. Một lần import có thể được thực hiện như sau:

```bash
mysql --default-character-set=utf8mb4 \
  --host=restore-db.internal \
  --user=restore_user \
  -p appdb < appdb.sql
```

Sau khi kết nối, có thể xác nhận session:

```sql
SELECT
    @@SESSION.character_set_client,
    @@SESSION.character_set_connection,
    @@SESSION.character_set_results,
    @@SESSION.time_zone,
    @@SESSION.sql_mode;
```

Nếu cần chuẩn hóa timezone của session cho thao tác import dữ liệu `TIMESTAMP`, có thể dùng:

```sql
SET SESSION time_zone = '+00:00';
```

Không tự động chạy `ALTER DATABASE ... CHARACTER SET` hoặc `ALTER TABLE ... CONVERT TO CHARACTER SET` ngay trước import để ép mọi dữ liệu về một cấu hình. Những lệnh này có thể rebuild table, thay đổi collation của column, phát sinh duplicate key, tăng dung lượng tạm và khóa/ảnh hưởng workload. Hãy thử trên bản sao, xử lý xung đột và lập kế hoạch downtime/online DDL phù hợp.

## 10. Các lỗi thường gặp khi chuyển môi trường

| Triệu chứng | Nguyên nhân có thể | Cách điều tra/xử lý |
|---|---|---|
| Import báo unknown collation | Destination không hỗ trợ collation trong DDL | Kiểm tra `SHOW COLLATION`, phiên bản; chọn collation tương thích sau khi đánh giá ngữ nghĩa. |
| Ký tự tiếng Việt thành `?` hoặc chuỗi mojibake | Charset client/file/column không khớp hoặc byte đã bị chuyển đổi sai | Xác định byte gốc, charset của dump, connection và column; không sửa bằng cách đổi collation đơn thuần. |
| Duplicate key khi import | Collation đích coi hai chuỗi khác nhau ở nguồn là tương đương | Tìm nhóm xung đột theo collation đích, làm sạch dữ liệu hoặc chọn quy tắc phù hợp. |
| Thời gian TIMESTAMP lệch đúng vài giờ | Timezone session khi ghi/đọc khác nhau | Đối chiếu `@@time_zone`, `@@system_time_zone`, UTC và tùy chọn timezone của dump. |
| DATETIME bị quy đổi sai | Ứng dụng hoặc script tự cộng/trừ timezone dù MySQL không chuyển DATETIME | Xác định quy ước UTC/giờ địa phương và bỏ bước chuyển đổi không phù hợp. |
| Import thất bại vì ngày bằng 0 | SQL mode destination nghiêm hơn hoặc phiên bản mới thay đổi hành vi | Tìm dữ liệu không hợp lệ; sửa theo quy tắc nghiệp vụ trước khi import. |
| Query GROUP BY lỗi sau restore | Destination bật `ONLY_FULL_GROUP_BY` | Sửa SQL cho xác định hoặc đánh giá mode theo chính sách ứng dụng. |
| Stored routine chạy khác | SQL mode được lưu tại thời điểm tạo object | Kiểm tra DDL và SQL mode của object; tạo lại có kiểm soát sau khi kiểm thử. |
| `CONVERT_TZ` trả NULL với tên vùng | Timezone tables chưa được nạp hoặc tên vùng không có | Nạp/cập nhật timezone tables và kiểm tra lại. |
| Kết quả ORDER BY khác | Collation hoặc phiên bản Unicode collation khác | So sánh collation, kiểm thử dữ liệu đại diện và xác nhận thứ tự mong muốn. |

## 11. Checklist nghiệm thu dữ liệu sau migration

- [ ] Đã ghi lại phiên bản MySQL, client tool và `server_uuid` của source/destination.
- [ ] Charset server, database, table, column và connection đã được kiểm kê.
- [ ] Collation đích tồn tại và có ngữ nghĩa so sánh phù hợp với ứng dụng.
- [ ] Unique index đã được kiểm tra xung đột theo collation đích.
- [ ] Dump file được xác nhận encoding; driver/client import dùng charset phù hợp.
- [ ] Timezone global/session/system đã được ghi lại; named timezone tables sẵn sàng nếu cần.
- [ ] Quy ước `TIMESTAMP` và `DATETIME` được xác nhận, đặc biệt với cột lưu giờ địa phương.
- [ ] SQL mode source/destination đã được so sánh và các mode ảnh hưởng đã được kiểm thử.
- [ ] Stored routine, function, trigger và event đã được kiểm tra SQL mode lưu kèm.
- [ ] Đã thử import staging, đối chiếu số hàng, DDL, warning và truy vấn nghiệp vụ.
- [ ] Đã kiểm tra dữ liệu Unicode, ngày giờ, unique key và kết quả sắp xếp sau restore.

Một migration dữ liệu thành công phải giữ được cả giá trị và ý nghĩa của giá trị. Character set bảo toàn ký tự, collation bảo toàn quy tắc so sánh, timezone bảo toàn thời điểm theo quy ước nghiệp vụ, còn SQL mode bảo toàn cách câu lệnh và dữ liệu được chấp nhận. Hãy kiểm kê bốn nhóm này ở source và destination, thử import trên môi trường staging và đối soát kết quả trước khi chuyển tải production.
