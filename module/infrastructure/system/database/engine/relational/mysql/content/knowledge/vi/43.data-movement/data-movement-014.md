# Chuyển từ hệ quản trị khác và xử lý khác biệt kiểu dữ liệu/ngữ nghĩa SQL

## Mục tiêu

Chuyển dữ liệu từ PostgreSQL, SQL Server, Oracle hoặc một hệ quản trị khác sang MySQL không chỉ là đổi cú pháp `CREATE TABLE` rồi nạp lại dữ liệu. Hai hệ thống có thể diễn giải cùng một kiểu dữ liệu, biểu thức SQL, giá trị rỗng, múi giờ, khóa tự tăng và ràng buộc theo những cách khác nhau. Nếu chỉ chuyển dữ liệu mà không chuyển đúng ngữ nghĩa, hệ thống mới có thể chạy nhưng trả kết quả khác, bỏ sót dữ liệu hoặc phát sinh lỗi khi ứng dụng hoạt động.

Bài học thuộc module **DATABASE_MYSQL**, bao quát thiết kế bảng, kiểu dữ liệu, khóa, SQL, index, transaction, kiểm soát đồng thời, đọc kế hoạch thực thi, tối ưu truy vấn và vận hành cơ sở dữ liệu quan hệ. Bài này hướng dẫn cách kiểm kê hệ thống nguồn, ánh xạ kiểu dữ liệu, chuyển đổi SQL, di chuyển dữ liệu theo giai đoạn và xác minh tính tương đương sau cutover.

Sau bài học, bạn có thể:

- Lập danh mục schema, dữ liệu, ràng buộc, routine, quyền và phụ thuộc của hệ thống nguồn.
- Xây dựng bảng ánh xạ kiểu dữ liệu và quy tắc chuyển đổi có kiểm chứng.
- Nhận diện khác biệt về `NULL`, chuỗi rỗng, collation, ngày giờ, số học và cú pháp SQL.
- Chọn cách nạp dữ liệu, đồng bộ thay đổi và chuyển ứng dụng sang MySQL.
- Đối chiếu số lượng, nội dung, quan hệ và hành vi nghiệp vụ trước khi đưa hệ thống mới vào sử dụng.

## 1. Bắt đầu bằng kiểm kê hệ thống nguồn

Trước khi viết DDL hoặc ETL, hãy xác định hệ thống đang có những gì và ứng dụng phụ thuộc vào hành vi nào. Chỉ kiểm kê bảng là chưa đủ: view, sequence, trigger, stored procedure, function, job, quyền, collation, timezone, isolation level và logic nằm trong ứng dụng đều có thể ảnh hưởng kết quả chuyển đổi.

Thu thập ít nhất các nhóm thông tin sau:

| Nhóm | Cần ghi nhận | Vì sao quan trọng |
|---|---|---|
| Nền tảng | Tên hệ quản trị, phiên bản, extension, encoding, timezone | Quyết định khả năng tương thích và cách trích xuất |
| Cấu trúc | Schema, bảng, cột, kiểu, default, generated column, partition | Là cơ sở lập DDL đích |
| Ràng buộc | Primary key, unique, foreign key, check, trigger | Giữ tính toàn vẹn và thứ tự nạp |
| Dữ liệu | Số hàng, kích thước, phân bố, giá trị NULL, min/max, dữ liệu bất thường | Ước lượng thời gian và phát hiện dữ liệu không ánh xạ được |
| SQL và ứng dụng | Query, view, procedure, function, ORM, migration script | Tìm cú pháp và ngữ nghĩa cần sửa |
| Vận hành | Backup, CDC, lịch batch, tài khoản, quyền, audit | Bảo đảm cutover và khôi phục |

Hãy xác định hệ thống nào là nguồn có thẩm quyền ghi trong giai đoạn di chuyển. Ghi lại các tích hợp bên ngoài như ETL, báo cáo, hàng đợi, dịch vụ thanh toán và job định kỳ. Một bảng có thể không được ứng dụng chính sử dụng trực tiếp nhưng vẫn là đầu vào cho một quy trình khác.

## 2. Lập bảng ánh xạ kiểu dữ liệu

Không có một bảng chuyển đổi tự động nào đúng cho mọi hệ quản trị và mọi ứng dụng. Ánh xạ phải dựa trên miền giá trị thực tế, độ chính xác cần giữ và cách ứng dụng sử dụng dữ liệu.

Một số hướng ánh xạ thường gặp:

| Kiểu nguồn hoặc khái niệm | Kiểu MySQL có thể dùng | Điều cần xác minh |
|---|---|---|
| Số nguyên 16/32/64 bit | `SMALLINT`, `INT`, `BIGINT` | Miền giá trị, dấu âm/dương và nguy cơ tràn; không tự đổi sang `UNSIGNED` nếu nguồn cho phép số âm |
| Số thập phân chính xác | `DECIMAL(p,s)` | Giữ nguyên precision/scale; kiểm tra giá trị lớn nhất và số chữ số phần lẻ |
| Số thực gần đúng | `FLOAT`, `DOUBLE` | Chấp nhận sai số nhị phân hay cần chuyển sang `DECIMAL` |
| Boolean | `BOOLEAN` hoặc `TINYINT(1)` | Trong MySQL, `BOOLEAN` là alias của `TINYINT(1)`; kiểm tra dữ liệu có giá trị ngoài 0/1 không |
| Chuỗi Unicode | `VARCHAR`, `TEXT` với `utf8mb4` | Độ dài theo ký tự/byte, collation, ký tự ngoài BMP và giới hạn index |
| Ngày và thời điểm | `DATE`, `DATETIME(fsp)`, `TIMESTAMP(fsp)` | Múi giờ, độ chính xác phần giây và miền ngày hỗ trợ |
| UUID | `BINARY(16)` hoặc `CHAR(36)` | Thứ tự byte, cách chuẩn hóa, khả năng đọc và tương thích ứng dụng |
| Binary large object | `BLOB`, `MEDIUMBLOB`, `LONGBLOB` | Kích thước tối đa, encoding và cách truyền dữ liệu |
| JSON hoặc document | `JSON` hoặc bảng quan hệ | Cấu trúc, kiểu số, index và truy vấn trên từng thuộc tính |
| Array hoặc collection | Bảng con quan hệ hoặc `JSON` | Có cần join, ràng buộc từng phần tử và truy vấn theo phần tử không |

Chọn kiểu dựa trên dữ liệu và nghiệp vụ, không chỉ dựa trên tên kiểu nguồn. Ví dụ, cột `NUMBER` trong Oracle có thể đại diện cho số đếm, tiền tệ, tỷ lệ hoặc mã định danh; mỗi trường hợp có yêu cầu khác nhau.

### Số nguyên và số thập phân

Với tiền tệ hoặc số đo cần chính xác, ưu tiên `DECIMAL(p,s)` thay vì `FLOAT`/`DOUBLE`. Chọn `p` đủ lớn cho tổng số chữ số và `s` đủ lớn cho phần thập phân. Trước khi nạp, thống kê giá trị vượt giới hạn hoặc có scale lớn hơn đích; không âm thầm làm tròn.

Ví dụ, nếu nguồn lưu số tiền tối đa 12 chữ số tổng cộng và 2 chữ số thập phân, có thể dùng `DECIMAL(12,2)`. Nếu nguồn có nhiều chữ số hơn, cần tăng precision hoặc xác định quy tắc làm tròn được nghiệp vụ chấp thuận.

### Boolean, bit và giá trị mặc định

MySQL chấp nhận `BOOLEAN` như alias của `TINYINT(1)`, nhưng kiểu này không tự giới hạn dữ liệu chỉ còn 0 và 1. Nếu cần ràng buộc, dùng `CHECK` trên phiên bản hỗ trợ và kiểm tra dữ liệu lịch sử trước khi bật ràng buộc. Trong MySQL 8.0.16 trở lên, `CHECK` constraint được thực thi; các bản cũ hơn có thể chỉ phân tích cú pháp mà không thực thi.

Không chuyển cột bit hoặc boolean nguồn thành `TINYINT` mà chưa kiểm tra cách driver đọc/ghi. Xác minh các giá trị `true`, `false`, `NULL`, default và dữ liệu lỗi.

## 3. Ngày giờ, múi giờ và độ chính xác

Ngày giờ là nguồn lỗi thường gặp vì các hệ quản trị không luôn dùng cùng quy tắc lưu và hiển thị.

- `DATE` lưu ngày lịch, không chứa giờ.
- `DATETIME(fsp)` lưu ngày giờ theo giá trị được đưa vào, không tự chuyển theo timezone session.
- `TIMESTAMP(fsp)` chuyển đổi giữa timezone session và UTC khi lưu/đọc; miền giá trị nhỏ hơn `DATETIME` và phụ thuộc phiên bản.
- `fsp` từ 0 đến 6 quy định độ chính xác phần giây; cần chọn theo độ chính xác nguồn.

Nếu nguồn lưu thời điểm tuyệt đối kèm timezone, hãy chuẩn hóa theo UTC trong quá trình trích xuất hoặc ETL, rồi ghi rõ quy ước ở MySQL. Nếu nguồn lưu giờ địa phương không kèm timezone, không thể tự suy ra offset chính xác khi có giờ mùa hè hoặc thay đổi quy tắc timezone. Cần xác định timezone nghiệp vụ cho từng trường.

Ví dụ kiểm tra timezone trên MySQL:

```sql
SELECT @@GLOBAL.time_zone,
       @@SESSION.time_zone,
       NOW(),
       UTC_TIMESTAMP();
```

Không đổi mọi cột thời gian sang `TIMESTAMP` theo thói quen. Thời điểm sự kiện có thể phù hợp với UTC, còn giờ hẹn tại cửa hàng hoặc ngày sinh thường là giá trị lịch địa phương và có thể phù hợp hơn với `DATETIME` hoặc `DATE`. Ghi rõ quy tắc trong data dictionary.

## 4. Chuỗi, encoding, collation và NULL

MySQL hiện đại nên dùng `utf8mb4` cho dữ liệu Unicode. `utf8mb4` hỗ trợ đầy đủ Unicode, gồm ký tự ngoài BMP. Khi tạo schema hoặc bảng, khai báo charset và collation rõ ràng để tránh phụ thuộc mặc định của server:

```sql
CREATE DATABASE app_migrated
  CHARACTER SET utf8mb4
  COLLATE utf8mb4_0900_ai_ci;
```

`utf8mb4_0900_ai_ci` là collation có sẵn trên MySQL 8.0; nếu cần tương thích phiên bản khác, chọn collation được phiên bản đích hỗ trợ. Hậu tố `ai_ci` biểu thị so sánh không phân biệt dấu và không phân biệt hoa/thường. Nếu nghiệp vụ cần phân biệt, hãy chọn collation phù hợp và kiểm thử.

Collation ảnh hưởng so sánh, sắp xếp và unique index. Ví dụ, hai chuỗi khác chữ hoa/thường hoặc dấu có thể được xem là bằng nhau dưới collation không phân biệt. Một unique key hợp lệ ở nguồn có thể bị duplicate khi nạp sang MySQL. Trước khi tạo unique index, hãy tìm các nhóm giá trị có thể va chạm theo collation đích.

Phân biệt ba trạng thái:

- `NULL`: không có giá trị hoặc chưa biết theo mô hình dữ liệu.
- Chuỗi rỗng `''`: một giá trị chuỗi có độ dài bằng 0.
- Chuỗi chỉ chứa khoảng trắng: vẫn là một giá trị chuỗi; không tự `TRIM` nếu nghiệp vụ không yêu cầu.

Oracle xử lý chuỗi rỗng trong một số kiểu ký tự như `NULL`, trong khi MySQL phân biệt `''` với `NULL`. Khi chuyển từ Oracle, cần xác định cột nào đang dùng chuỗi rỗng mang ý nghĩa thiếu dữ liệu và chuyển đổi có chủ đích. Không áp dụng `NULLIF(column, '')` hàng loạt nếu chuỗi rỗng là giá trị hợp lệ.

Kiểm tra nullability, default và unique constraint. MySQL cho phép nhiều giá trị `NULL` trong unique index theo quy tắc của nó; nếu nguồn có cách xử lý khác, cần viết kiểm tra và constraint bổ sung.

## 5. JSON, array, UUID và kiểu đặc thù

**JSON:** MySQL có kiểu `JSON` với kiểm tra tính hợp lệ và các hàm truy vấn JSON. Nhưng kiểu số, cách biểu diễn ngày, thứ tự thuộc tính và toán tử của hệ quản trị nguồn có thể khác. Nếu thuộc tính thường xuyên dùng để join, lọc hoặc ràng buộc, cân nhắc tách thành cột có kiểu rõ ràng hoặc generated column được index thay vì giữ toàn bộ trong JSON.

**Array:** MySQL không có kiểu array quan hệ tổng quát tương đương PostgreSQL. Nếu phần tử cần join, unique, foreign key hoặc lọc thường xuyên, chuyển thành bảng con với một hàng cho mỗi phần tử. Chỉ dùng JSON khi dữ liệu thực sự là document và truy vấn theo phần tử không phải đường truy cập chính.

**UUID:** `CHAR(36)` dễ đọc và tương thích, nhưng chiếm nhiều không gian hơn. `BINARY(16)` gọn hơn nhưng cần quy ước chuyển đổi thống nhất. Nếu dùng `UUID_TO_BIN()` và `BIN_TO_UUID()`, phải thống nhất tham số swap flag ở mọi ứng dụng và công cụ; sai quy ước sẽ làm UUID đọc ra khác thứ tự mong muốn.

**Sequence và identity:** PostgreSQL sequence, SQL Server `IDENTITY` hoặc Oracle sequence thường được chuyển sang `AUTO_INCREMENT` khi phù hợp. `AUTO_INCREMENT` không bảo đảm dãy liên tục và có thể có khoảng trống sau rollback hoặc lỗi. Nếu phải giữ ID nguồn, nạp ID tường minh rồi đặt giá trị tiếp theo phù hợp sau khi kiểm tra `MAX(id)`.

**Enum và domain:** không chuyển enum/domain nguồn sang `ENUM` MySQL một cách tự động. `VARCHAR` kèm `CHECK` hoặc bảng tham chiếu thường linh hoạt hơn khi danh sách giá trị thay đổi hoặc cần metadata.

## 6. Chuyển đổi ngữ nghĩa SQL

SQL cùng chuẩn vẫn có khác biệt theo sản phẩm, phiên bản và SQL mode. Hãy kiểm tra các truy vấn quan trọng thay vì chỉ sửa cú pháp cho hết lỗi.

| Chủ đề | Khác biệt thường gặp | Cách xử lý trong MySQL |
|---|---|---|
| Nối chuỗi | SQL Server thường dùng `+`; PostgreSQL/Oracle có `||`; MySQL mặc định dùng `||` như logical OR trừ khi bật SQL mode đặc biệt | Dùng `CONCAT()` hoặc `CONCAT_WS()` và kiểm tra hành vi với `NULL` |
| Giới hạn hàng | SQL Server có `TOP`, Oracle/PostgreSQL có cú pháp riêng | Dùng `LIMIT` và `OFFSET`, kèm `ORDER BY` ổn định |
| Upsert | PostgreSQL dùng `ON CONFLICT`; SQL Server/Oracle có cách khác | Dùng `INSERT ... ON DUPLICATE KEY UPDATE` và kiểm thử unique key kích hoạt |
| Hàm ngày giờ | Tên hàm, quy tắc cộng trừ và timezone khác nhau | Dùng hàm MySQL tương ứng; kiểm thử biên ngày, tháng và DST |
| Boolean | Có hệ thống có kiểu boolean độc lập | `BOOLEAN` là alias của `TINYINT(1)`; xác thực miền giá trị |
| Identifier | Cách quote tên bảng/cột khác nhau | Dùng backtick cho identifier trong MySQL; tránh phụ thuộc từ khóa hoặc chữ hoa/thường |
| `GROUP BY` | Một số hệ thống cho phép chọn cột không gom nhóm theo quy tắc riêng | Tuân thủ `ONLY_FULL_GROUP_BY` và xác định rõ aggregate |
| Phân trang | `OFFSET` lớn có thể tốn kém và thứ tự không ổn định nếu thiếu khóa sắp xếp | Dùng `ORDER BY` duy nhất; cân nhắc keyset pagination cho tập lớn |

### NULL và biểu thức

Trong SQL, so sánh với `NULL` bằng `= NULL` không cho kết quả true; dùng `IS NULL` hoặc `IS NOT NULL`. `NOT IN` có thể cho kết quả không mong đợi nếu tập con chứa `NULL`; xem xét `NOT EXISTS` khi chuyển truy vấn.

`CONCAT()` của MySQL trả `NULL` nếu một đối số là `NULL` trong chế độ thông thường. Nếu nguồn bỏ qua giá trị null khi nối chuỗi, dùng `CONCAT_WS()` hoặc `COALESCE()` theo đúng quy tắc mong muốn. Viết test cho trường hợp mọi cột đều có giá trị, một cột null và tất cả cột null.

### Upsert và REPLACE

MySQL hỗ trợ `INSERT ... ON DUPLICATE KEY UPDATE`, nhưng điều kiện kích hoạt là va chạm trên primary key hoặc unique key. Nếu bảng có nhiều unique index, cần kiểm tra xung đột nào sẽ kích hoạt nhánh update. Không thay mọi `MERGE` hoặc `ON CONFLICT` bằng cú pháp này mà chưa so sánh điều kiện match và số hàng bị ảnh hưởng.

Tránh dùng `REPLACE` như một upsert tổng quát: MySQL có thể xóa hàng cũ rồi chèn hàng mới, làm thay đổi hành vi trigger, foreign key, auto-increment và audit. `INSERT IGNORE` cũng không phải giải pháp an toàn mặc định vì có thể hạ một số lỗi thành warning và bỏ qua dữ liệu không hợp lệ.

### GROUP BY và chế độ SQL

MySQL có `ONLY_FULL_GROUP_BY` trong SQL mode mặc định của nhiều bản hiện đại. Truy vấn chọn cột không được aggregate và không phụ thuộc hàm vào cột group có thể bị từ chối. Đừng tắt mode chỉ để truy vấn cũ chạy được; sửa truy vấn bằng aggregate, thêm cột vào `GROUP BY` hoặc chọn một hàng rõ ràng bằng window function phù hợp.

Kiểm tra cấu hình:

```sql
SELECT @@GLOBAL.sql_mode, @@SESSION.sql_mode;
```

Chạy ứng dụng với strict mode trong môi trường kiểm thử. Strict mode giúp phát hiện giá trị vượt miền, chuỗi bị cắt hoặc dữ liệu ngày không hợp lệ thay vì âm thầm chuyển đổi.

## 7. Khóa, index, constraint và transaction

Chuyển dữ liệu cần giữ quan hệ giữa bảng. Nạp bảng cha trước bảng con nếu foreign key được bật; hoặc nạp vào staging rồi kiểm tra và tạo constraint sau khi dữ liệu đã sạch. Không tắt kiểm tra khóa ngoại mà không có bước xác minh lại.

MySQL InnoDB dùng clustered index theo primary key. Chọn kiểu khóa chính phù hợp với kích thước, tính duy nhất và đặc điểm ghi. Nếu nguồn dùng UUID ngẫu nhiên làm khóa, đánh giá ảnh hưởng đến locality và kích thước secondary index. Có thể giữ UUID nghiệp vụ ở unique key và dùng khóa thay thế số nguyên nếu thiết kế cho phép.

Index nguồn không nhất thiết chuyển nguyên xi sang MySQL. Khác biệt về collation, độ dài index, prefix, selectivity, optimizer và kiểu dữ liệu có thể làm hiệu quả thay đổi. Sau khi nạp dữ liệu đại diện, tạo index cần thiết và dùng `EXPLAIN` để kiểm tra truy vấn quan trọng.

DDL trong MySQL có thể gây implicit commit. Dù một số DDL là atomic ở các phiên bản hiện đại, không giả định rằng toàn bộ migration schema có thể rollback như transaction DML. Chia nhỏ migration, kiểm thử trên bản sao và chuẩn bị phương án phục hồi.

Kiểm tra isolation level, locking và deadlock. Một ứng dụng chuyển từ hệ quản trị có mức isolation mặc định khác có thể nhìn thấy dữ liệu hoặc chờ khóa khác đi. Xác định mức isolation cần thiết và kiểm thử các transaction cạnh tranh trước cutover.

## 8. Thiết kế pipeline di chuyển dữ liệu

Với hệ thống nhỏ có thể export/import trong một cửa sổ bảo trì. Với hệ thống lớn hoặc cần downtime ngắn, thường dùng nạp đầy đủ ban đầu kết hợp Change Data Capture (CDC) để đồng bộ các thay đổi phát sinh trong lúc nạp.

Quy trình tổng quát:

1. **Chuẩn bị schema đích:** tạo database, charset, collation, bảng, kiểu dữ liệu, khóa và ràng buộc theo mapping đã duyệt.
2. **Trích xuất nhất quán:** lấy snapshot tại một thời điểm xác định; ghi lại log position, LSN, SCN hoặc checkpoint tương ứng của công cụ nguồn.
3. **Nạp dữ liệu ban đầu:** dùng dump/import, bulk load, ETL hoặc công cụ di chuyển phù hợp; nạp vào staging nếu cần làm sạch hoặc biến đổi.
4. **Đồng bộ thay đổi:** chạy CDC hoặc cơ chế delta để chuyển insert, update, delete theo đúng thứ tự và checkpoint.
5. **Xác minh:** so sánh số hàng, checksum chuẩn hóa, khóa, quan hệ và các chỉ số nghiệp vụ.
6. **Diễn tập cutover:** đo thời gian dừng ghi, thời gian delta cuối, kiểm tra ứng dụng và quy trình quay lui.
7. **Cutover:** dừng hoặc khóa ghi ở nguồn, áp dụng hết thay đổi còn lại, xác minh điểm đồng bộ rồi chuyển endpoint ứng dụng.
8. **Theo dõi sau chuyển đổi:** kiểm tra lỗi, latency, dữ liệu mới, truy vấn chậm và kết quả nghiệp vụ.

CDC là khái niệm chung; cách lấy log và đảm bảo thứ tự phụ thuộc hệ quản trị nguồn và công cụ. Kiểm tra công cụ có ghi nhận DDL hay không, xử lý truncate/partition ra sao, giữ transaction lớn như thế nào và có thể tiếp tục từ checkpoint sau khi restart hay không.

## 9. Nạp dữ liệu và xử lý staging

Không nên đưa dữ liệu chưa kiểm tra thẳng vào bảng production. Bảng staging cho phép giữ nguyên dữ liệu trích xuất, phát hiện lỗi và áp dụng mapping có thể lặp lại.

Ví dụ bảng đích:

```sql
CREATE TABLE customers (
  customer_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  source_system VARCHAR(32) NOT NULL,
  source_customer_id VARCHAR(128) NOT NULL,
  email VARCHAR(320) NULL,
  created_at DATETIME(6) NOT NULL,
  PRIMARY KEY (customer_id),
  UNIQUE KEY uq_customer_source (source_system, source_customer_id)
) ENGINE = InnoDB
  DEFAULT CHARACTER SET utf8mb4
  COLLATE utf8mb4_0900_ai_ci;
```

Khóa unique theo `(source_system, source_customer_id)` giúp giữ lại định danh nguồn ngay cả khi khóa nội bộ MySQL khác khóa nguồn. Nếu email được dùng để nhận diện duy nhất, phải quyết định quy tắc hoa/thường và collation trước khi tạo unique index.

Với file CSV đã được kiểm tra encoding và delimiter, `LOAD DATA` có thể nạp nhanh vào staging:

```sql
LOAD DATA LOCAL INFILE 'customers.csv'
INTO TABLE stg_customers
CHARACTER SET utf8mb4
FIELDS TERMINATED BY ','
OPTIONALLY ENCLOSED BY '"'
LINES TERMINATED BY '\n'
IGNORE 1 LINES;
```

`LOCAL` đọc file từ phía client và phụ thuộc cấu hình client/server; chỉ bật khi chính sách bảo mật cho phép. Định dạng CSV cần quy định rõ cách biểu diễn `NULL`, chuỗi rỗng, dấu xuống dòng, dấu phân cách và escape. Kiểm tra warning sau khi nạp và đối chiếu số hàng thực tế; không bỏ qua warning do truncation hoặc chuyển đổi kiểu.

## 10. Xác minh dữ liệu và ngữ nghĩa

Không có một phép đếm duy nhất đủ chứng minh migration đúng. Dùng nhiều lớp kiểm tra:

| Kiểm tra | Ví dụ | Phát hiện |
|---|---|---|
| Số lượng | `COUNT(*)` theo bảng và phân vùng | Thiếu hoặc thừa hàng |
| Miền giá trị | `MIN`, `MAX`, `SUM`, phân vị | Tràn số, sai scale, giá trị bị cắt |
| NULL và chuỗi rỗng | Đếm `IS NULL`, `= ''`, độ dài chuỗi | Quy tắc thiếu dữ liệu bị đổi |
| Khóa duy nhất | `GROUP BY key HAVING COUNT(*) > 1` | Va chạm do collation hoặc mapping |
| Quan hệ | Anti-join giữa bảng con và bảng cha | Foreign key bị mồ côi |
| Thời gian | Min/max, mẫu quanh DST và ranh giới ngày | Sai timezone hoặc precision |
| Nội dung | Hash trên serialization chuẩn hóa theo lô | Khác biệt giá trị sau chuyển đổi |
| Nghiệp vụ | Tổng tiền, số đơn theo trạng thái, số dư, số lượng tồn | Sai lệch dù số hàng khớp |

Ví dụ kiểm tra khóa trùng theo collation đích:

```sql
SELECT email, COUNT(*) AS duplicate_count
FROM customers
WHERE email IS NOT NULL
GROUP BY email
HAVING COUNT(*) > 1;
```

Ví dụ kiểm tra bản ghi con không có bản ghi cha:

```sql
SELECT o.customer_id
FROM orders AS o
LEFT JOIN customers AS c
  ON c.customer_id = o.customer_id
WHERE c.customer_id IS NULL;
```

Hash cần được tính trên biểu diễn chuẩn hóa giống nhau ở hai phía: quy định timezone, encoding, thứ tự cột, cách biểu diễn NULL, decimal và chuỗi. Chia dữ liệu thành lô để tìm phạm vi sai lệch. Hash không thay thế kiểm tra nghiệp vụ hoặc ràng buộc.

## 11. Cutover và phương án quay lui

Cutover cần có tiêu chí rõ ràng trước khi bắt đầu. Một runbook tốt chỉ ra ai có quyền dừng ghi, ai xác nhận checkpoint CDC, ai kiểm tra dữ liệu và ai quyết định chuyển endpoint.

Trình tự thường dùng:

1. Thông báo cửa sổ bảo trì và ngừng các writer vào nguồn theo kế hoạch.
2. Chờ transaction đang chạy kết thúc; ghi lại checkpoint cuối cùng của nguồn.
3. Áp dụng toàn bộ delta/CDC đến checkpoint đó trên MySQL.
4. Chạy kiểm tra nhanh về số hàng, khóa, tổng nghiệp vụ và trạng thái replication/CDC.
5. Chuyển ứng dụng sang endpoint MySQL, mở writer theo thứ tự và theo dõi lỗi.
6. Giữ nguồn cũ ở trạng thái chỉ đọc hoặc cô lập ghi trong thời gian xác nhận.

Rollback không đơn giản là đổi endpoint trở lại. Sau khi ứng dụng đã ghi dữ liệu mới lên MySQL, nguồn cũ sẽ thiếu những transaction đó. Muốn quay lui mà không mất dữ liệu, phải có kế hoạch reverse replication/CDC, đối soát và chuyển đổi ngược đã được diễn tập. Nếu không có đường đồng bộ ngược, quyết định rollback cần xác định rõ phần dữ liệu mới sẽ được bảo toàn như thế nào.

Đặt tiêu chí go/no-go, ví dụ: không có lỗi dữ liệu nghiêm trọng, chênh lệch kiểm tra bằng 0 hoặc nằm trong ngưỡng đã phê duyệt, thời gian cutover dưới RTO, và các luồng ghi/đọc quan trọng đã qua smoke test.

## 12. Lỗi chuyển đổi thường gặp

- **Cắt hoặc làm tròn số:** precision/scale đích quá nhỏ. Thống kê miền giá trị và kiểm tra warning trước khi nạp production.
- **Sai timezone:** thời điểm bị dịch giờ hoặc mất độ chính xác. Chuẩn hóa UTC và xác định rõ trường nào là giờ địa phương.
- **Va chạm unique sau đổi collation:** chuỗi trước đây khác nhau nhưng collation đích xem là bằng nhau. Kiểm tra duplicate trước khi tạo unique index.
- **Đổi chuỗi rỗng thành NULL hoặc ngược lại:** số liệu thiếu dữ liệu thay đổi. Lập quy tắc cho từng cột và thống kê riêng.
- **Dùng sai semantics của `CONCAT`, `NULL`, `NOT IN` hoặc `GROUP BY`:** truy vấn chạy nhưng kết quả khác. Viết test đối chiếu trên bộ dữ liệu biên.
- **Mất sequence/identity:** ID tiếp theo trùng hoặc nhảy sai. Nạp ID nguồn có kiểm soát và đặt lại giá trị AUTO_INCREMENT.
- **CDC thiếu delete hoặc DDL:** bảng đích không phản ánh nguồn. Kiểm tra khả năng capture của công cụ và xử lý DDL riêng.
- **Nạp sai thứ tự quan hệ:** foreign key thất bại hoặc dữ liệu mồ côi. Nạp theo dependency graph và xác minh sau cùng.
- **Cutover khi delta chưa hết:** MySQL thiếu transaction cuối. Chốt checkpoint, đợi apply xong và xác nhận trước khi mở ghi.
- **Quay lui sau khi đã ghi đích:** dữ liệu mới không có ở nguồn cũ. Diễn tập reverse sync hoặc quy trình bảo toàn dữ liệu trước cutover.

## 13. Bài tập thực hành

Giả sử bạn cần chuyển một ứng dụng bán hàng từ PostgreSQL hoặc SQL Server sang MySQL:

1. Kiểm kê bảng khách hàng, đơn hàng, chi tiết đơn, kiểu dữ liệu, primary/foreign key, view và truy vấn quan trọng.
2. Tạo bảng mapping cho ID, decimal, boolean, timestamp, text, UUID và JSON; ghi rõ quy tắc cho NULL, chuỗi rỗng, timezone và collation.
3. Tạo schema MySQL với InnoDB, `utf8mb4`, khóa và constraint phù hợp.
4. Nạp một tập dữ liệu mẫu vào staging, xử lý các giá trị vượt miền và ghi lại mọi warning.
5. Chuyển các truy vấn có `TOP`, `||`, `+`, upsert, `GROUP BY` hoặc hàm ngày giờ sang SQL MySQL; viết test cho dữ liệu biên.
6. Đối chiếu số hàng, tổng tiền, số đơn theo trạng thái, khóa trùng, foreign key và thời điểm.
7. Diễn tập nạp đầy đủ cộng delta/CDC, chốt checkpoint và chuyển ứng dụng sang MySQL trong môi trường thử nghiệm.
8. Thử quy trình quay lui và xác định cách bảo toàn các giao dịch phát sinh sau cutover.

**Tiêu chí hoàn thành:** schema MySQL phản ánh đúng miền dữ liệu; truy vấn nghiệp vụ trả kết quả tương đương theo quy tắc đã thống nhất; không có dữ liệu bị cắt hoặc chuyển đổi âm thầm; và nhóm vận hành có thể thực hiện cutover, xác minh và quay lui theo runbook.

## Kết luận

Di chuyển sang MySQL là quá trình chuyển cả dữ liệu lẫn ngữ nghĩa mà ứng dụng đang dựa vào. Hãy kiểm kê hệ thống nguồn, ánh xạ kiểu theo miền giá trị, xử lý rõ timezone, collation, NULL và SQL mode, rồi chuyển dữ liệu theo snapshot và delta có checkpoint. Chỉ cutover khi các kiểm tra dữ liệu và nghiệp vụ đạt yêu cầu, đồng thời đã diễn tập cách bảo toàn dữ liệu nếu cần quay lui.
