# LOAD DATA INFILE so với LOAD DATA LOCAL INFILE

MySQL có thể nạp hàng loạt bản ghi từ tệp bằng câu lệnh `LOAD DATA`. Có hai cách đọc tệp: `LOAD DATA INFILE` để tiến trình MySQL đọc tệp trên máy chủ, và `LOAD DATA LOCAL INFILE` để chương trình client đọc tệp trên máy client rồi truyền nội dung qua kết nối tới máy chủ. Khác biệt về vị trí tệp kéo theo khác biệt về quyền, cấu hình, bảo mật và cách triển khai.

Với hệ thống MySQL, nhập dữ liệu không chỉ là đưa các dòng CSV vào bảng. Cần xác định nguồn tệp, charset, dấu phân cách, quy tắc escape, kiểu dữ liệu đích, quyền của tài khoản và cách xử lý bản ghi lỗi. Một quy trình an toàn thường nạp vào bảng staging, kiểm tra dữ liệu rồi mới chuyển vào bảng nghiệp vụ.

Bài học này dùng cú pháp MySQL 8.0. Một số tùy chọn client phụ thuộc connector và phiên bản; hãy kiểm tra tài liệu của đúng driver đang sử dụng.

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Phân biệt nơi đọc tệp của `INFILE` và `LOCAL INFILE`.
- Xác định quyền MySQL, cấu hình máy chủ và quyền hệ điều hành cần thiết.
- Chọn cách nạp phù hợp theo vị trí tệp, chính sách bảo mật và môi trường triển khai.
- Mô tả cấu trúc CSV/TSV bằng `FIELDS`, `LINES`, `CHARACTER SET` và `IGNORE`.
- Ánh xạ cột, chuẩn hóa giá trị và xử lý dữ liệu lỗi khi nhập.
- Thiết kế quy trình import có staging, kiểm tra, log và khả năng chạy lại.

## 1. Hai cách đọc tệp

### 1.1. `LOAD DATA INFILE`: máy chủ đọc tệp

Khi không có từ khóa `LOCAL`, MySQL Server mở và đọc tệp trên máy chủ. Đường dẫn trong câu lệnh được diễn giải theo filesystem của máy chủ, dưới quyền của tài khoản hệ điều hành chạy tiến trình `mysqld`.

Ví dụ:

```sql
LOAD DATA INFILE '/var/lib/mysql-files/orders.csv'
INTO TABLE staging_orders
CHARACTER SET utf8mb4
FIELDS TERMINATED BY ','
OPTIONALLY ENCLOSED BY '"'
ESCAPED BY '\\'
LINES TERMINATED BY '\r\n'
IGNORE 1 LINES;
```

Trong ví dụ, file phải tồn tại trên máy chạy MySQL, tài khoản hệ điều hành của MySQL phải đọc được file và đường dẫn phải tuân thủ cấu hình `secure_file_priv` nếu biến này được đặt.

Đây là lựa chọn phù hợp khi tệp đã được chuyển lên máy chủ qua một kênh triển khai được kiểm soát, chẳng hạn job ETL đặt gần database hoặc thư mục import riêng. Client không phải truyền toàn bộ nội dung file qua kết nối MySQL.

### 1.2. `LOAD DATA LOCAL INFILE`: client đọc tệp

Khi có từ khóa `LOCAL`, chương trình client đọc tệp trên máy đang chạy client rồi gửi nội dung tới MySQL Server qua kết nối. Đường dẫn được hiểu theo filesystem của máy client, không phải máy chủ database.

```sql
LOAD DATA LOCAL INFILE '/client/import/orders.csv'
INTO TABLE staging_orders
CHARACTER SET utf8mb4
FIELDS TERMINATED BY ','
OPTIONALLY ENCLOSED BY '"'
ESCAPED BY '\\'
LINES TERMINATED BY '\r\n'
IGNORE 1 LINES;
```

Tệp `/client/import/orders.csv` phải tồn tại và đọc được trên máy chạy ứng dụng hoặc công cụ import. Server nhận dữ liệu qua giao thức MySQL và dùng vùng lưu trữ tạm trong quá trình xử lý; vì vậy vẫn cần đủ dung lượng và I/O ở phía server.

`LOCAL` thuận tiện khi tệp nằm trên máy ETL, máy quản trị hoặc container chạy job, trong khi không muốn chép tệp lên host database. Đổi lại, dữ liệu đi qua mạng và cả client lẫn server đều phải cho phép khả năng LOCAL.

### 1.3. So sánh nhanh

| Tiêu chí | `LOAD DATA INFILE` | `LOAD DATA LOCAL INFILE` |
|---|---|---|
| Nơi mở tệp | Máy chủ MySQL | Máy chạy chương trình client |
| Nơi diễn giải đường dẫn | Filesystem của server | Filesystem của client |
| Ai đọc tệp | Tài khoản hệ điều hành chạy `mysqld` | Tài khoản hệ điều hành chạy client |
| Quyền MySQL đặc trưng | Cần quyền toàn cục `FILE` và quyền ghi bảng phù hợp | Không cần quyền `FILE`; cần quyền ghi bảng phù hợp |
| Cấu hình liên quan | `secure_file_priv`, quyền filesystem, chính sách OS | `local_infile` ở server và tùy chọn cho phép LOCAL ở client/connector |
| Luồng dữ liệu | Server đọc trực tiếp từ đĩa của server | Client gửi nội dung qua kết nối MySQL |
| Trường hợp thường dùng | File đã đặt trên host database trong thư mục import được kiểm soát | File nằm ở máy ETL, máy quản trị hoặc môi trường client |

`LOCAL` không có nghĩa là server không dùng đĩa. Server vẫn có thể dùng file tạm để nhận và xử lý nội dung được truyền đến. Ngược lại, `INFILE` không có nghĩa là client phải truy cập được filesystem của server.

## 2. Quyền và cấu hình cho `LOAD DATA INFILE`

### 2.1. Quyền MySQL

Với `LOAD DATA INFILE` không có `LOCAL`, tài khoản cần quyền `FILE` ở phạm vi toàn cục để server đọc file, cùng quyền `INSERT` trên bảng đích. `FILE` là quyền nhạy cảm vì cho phép các thao tác đọc/ghi tệp phía server trong phạm vi mà MySQL và hệ điều hành cho phép; không cấp quyền này cho tài khoản ứng dụng thông thường.

Ví dụ cấp quyền ghi vào bảng staging:

```sql
GRANT INSERT
  ON import_db.staging_orders
  TO 'etl_loader'@'10.20.1.15';

GRANT FILE
  ON *.*
  TO 'etl_server_loader'@'localhost';

GRANT INSERT
  ON import_db.staging_orders
  TO 'etl_server_loader'@'localhost';
```

Các câu lệnh minh họa hai account có nhiệm vụ khác nhau: tài khoản chạy `LOCAL` chỉ cần quyền ghi bảng; tài khoản dùng server-side `INFILE` cần cả `FILE` và quyền ghi bảng. Trong môi trường thật, chỉ cấp quyền đúng cho account thực sự thực hiện import và giới hạn host phù hợp. Nếu dùng `REPLACE` hoặc các biểu thức/đối tượng khác, rà soát thêm các quyền cần thiết theo câu lệnh và phiên bản.

### 2.2. `secure_file_priv`

`secure_file_priv` giới hạn các thao tác nhập/xuất tệp phía server:

```sql
SHOW GLOBAL VARIABLES LIKE 'secure_file_priv';
```

Giá trị thường được diễn giải như sau:

- Một đường dẫn thư mục: server giới hạn các thao tác file liên quan trong thư mục đó.
- `NULL`: server vô hiệu hóa các thao tác import/export file phía server thuộc phạm vi biến kiểm soát.
- Chuỗi rỗng: không áp dụng giới hạn thư mục từ biến này; cấu hình như vậy cần được đánh giá rất cẩn thận.

Trên các bản cài đặt phổ biến, thư mục dành riêng cho import/export thường được cấu hình khi khởi động MySQL, ví dụ `/var/lib/mysql-files`. Hãy xác minh giá trị thực tế thay vì giả định đường dẫn mặc định giống nhau ở mọi hệ điều hành hoặc package.

Ngoài `secure_file_priv`, tài khoản hệ điều hành chạy `mysqld` phải có quyền đọc tệp và quyền đi qua các thư mục cha. SELinux, AppArmor hoặc chính sách bảo vệ hệ điều hành cũng có thể chặn truy cập dù quyền Unix/Windows có vẻ cho phép.

### 2.3. Cấu hình và quyền cho `LOCAL`

Server phải cho phép khả năng LOCAL qua biến `local_infile`; client hoặc connector cũng phải bật khả năng gửi file cục bộ. Kiểm tra phía server:

```sql
SHOW GLOBAL VARIABLES LIKE 'local_infile';
```

Nếu chính sách cho phép và cần bật, người quản trị có thể thay đổi biến bằng cơ chế cấu hình phù hợp với phiên bản, ví dụ:

```sql
SET GLOBAL local_infile = ON;
```

Thay đổi `GLOBAL` ảnh hưởng các kết nối mới và có thể không tồn tại sau khi restart nếu không cập nhật cấu hình khởi động. Việc thay đổi biến cần quyền quản trị phù hợp. Không bật LOCAL trên mọi server chỉ để một job import hoạt động; hãy giới hạn phạm vi client và môi trường được phép dùng nó.

Với MySQL command-line client, tùy chọn `--local-infile=1` cho phép client sử dụng LOCAL nếu client build và server đều hỗ trợ. Với ứng dụng, cần cấu hình tùy chọn tương ứng của connector đang dùng. Tên tùy chọn và mặc định khác nhau giữa Connector/J, Connector/Python, Connector/C và các driver khác.

## 3. Rủi ro bảo mật khi bật LOCAL

`LOAD DATA LOCAL INFILE` cho phép server yêu cầu client gửi một tệp từ máy client. Vì vậy, client bật LOCAL cần tin cậy server mà nó kết nối. Một server độc hại hoặc bị xâm nhập có thể lợi dụng khả năng này để yêu cầu client gửi tệp mà tiến trình client có quyền đọc, tùy hành vi của thư viện và cấu hình bảo vệ.

Các biện pháp giảm rủi ro:

- Chỉ bật LOCAL trong job hoặc kết nối thực sự cần import từ máy client.
- Dùng allowlist thư mục hoặc cơ chế giới hạn đường dẫn mà connector hỗ trợ; không cho phép đọc tệp tùy ý trên máy ứng dụng.
- Chỉ kết nối tới server có danh tính được xác minh; dùng TLS để bảo vệ đường truyền và xác thực endpoint theo chính sách tổ chức.
- Không bật LOCAL trong client dùng để kết nối tới server không đáng tin cậy.
- Dùng tài khoản import riêng, chỉ có quyền trên bảng staging cần thiết.
- Tắt lại khả năng LOCAL hoặc loại bỏ tùy chọn client khi job hoàn tất nếu quy trình không cần sử dụng thường xuyên.
- Ghi log nguồn file, người chạy, thời điểm, bảng đích, số dòng nạp và số cảnh báo.

TLS bảo vệ nội dung truyền trên mạng nhưng không ngăn một server mà client tin cậy yêu cầu đọc file cục bộ. Giới hạn quyền filesystem của tiến trình ETL vẫn rất quan trọng.

## 4. Định nghĩa định dạng dữ liệu đầu vào

`LOAD DATA` không tự đoán chính xác mọi định dạng CSV. Người vận hành cần mô tả cách file tách trường, bao trường và kết thúc dòng.

| Tùy chọn | Ý nghĩa | Ví dụ |
|---|---|---|
| `CHARACTER SET` | Charset dùng để diễn giải nội dung file | `CHARACTER SET utf8mb4` |
| `FIELDS TERMINATED BY` | Ký tự phân cách cột | `FIELDS TERMINATED BY ','` |
| `OPTIONALLY ENCLOSED BY` | Ký tự bao quanh trường, thường dùng cho text | `OPTIONALLY ENCLOSED BY '"'` |
| `ESCAPED BY` | Ký tự escape trong file | `ESCAPED BY '\\'` |
| `LINES TERMINATED BY` | Ký tự kết thúc mỗi dòng | `LINES TERMINATED BY '\r\n'` |
| `IGNORE n LINES` | Bỏ qua số dòng đầu, thường là header | `IGNORE 1 LINES` |

Ví dụ với file CSV UTF-8 trên Windows, có header và kết thúc dòng CRLF:

```sql
LOAD DATA LOCAL INFILE '/client/import/customers.csv'
INTO TABLE staging_customers
CHARACTER SET utf8mb4
FIELDS TERMINATED BY ','
OPTIONALLY ENCLOSED BY '"'
ESCAPED BY '\\'
LINES TERMINATED BY '\r\n'
IGNORE 1 LINES
(customer_id, full_name, email, created_at);
```

Ví dụ này giả định file dùng backslash làm escape character. Nếu hệ thống tạo CSV theo quy tắc quote khác, chẳng hạn dùng hai dấu nháy kép liên tiếp để biểu diễn một dấu nháy bên trong trường, cần cấu hình `ENCLOSED BY`/`ESCAPED BY` tương ứng và kiểm thử bằng các dòng có dấu phẩy, dấu nháy và xuống dòng bên trong trường. Không giả định mọi file mang đuôi `.csv` đều có cùng dialect.

### 4.1. Charset và newline

`CHARACTER SET` mô tả charset của dữ liệu trong file. Nó không phải là cách đặt charset cho toàn bộ connection. Nếu file được xuất bằng UTF-8 nhưng được nạp như một charset khác, tên có dấu có thể bị lỗi hoặc biến thành ký tự không mong muốn.

Kiểm tra các đặc điểm của file trước khi import:

- Encoding thực tế: UTF-8, UTF-8 có BOM, Windows-1252 hoặc charset khác.
- Dấu phân cách: dấu phẩy, tab, dấu chấm phẩy hoặc ký tự khác.
- Quy tắc quote và escape.
- Newline là `\n` hay `\r\n`.
- Có header, dòng trống, ký tự NUL hoặc dấu phân cách ở cuối dòng hay không.

Nếu file có BOM hoặc dialect không được MySQL xử lý như mong đợi, hãy chuẩn hóa file ở bước ETL trước khi nạp. Không xóa hoặc thay thế byte đầu file một cách mù quáng; xác minh ảnh hưởng tới trường đầu tiên.

### 4.2. Header, cột bỏ qua và user variable

`IGNORE 1 LINES` bỏ qua một dòng đầu, thường là header. MySQL không tự ghép tên header với cột bảng; thứ tự trường vẫn cần được khai báo rõ.

Có thể đọc một trường vào user variable rồi chuyển đổi bằng `SET`:

```sql
LOAD DATA LOCAL INFILE '/client/import/orders.csv'
INTO TABLE staging_orders
CHARACTER SET utf8mb4
FIELDS TERMINATED BY ','
OPTIONALLY ENCLOSED BY '"'
ESCAPED BY '\\'
LINES TERMINATED BY '\r\n'
IGNORE 1 LINES
(order_id, customer_id, @raw_amount, @raw_created_at)
SET amount = NULLIF(TRIM(@raw_amount), ''),
    created_at = STR_TO_DATE(@raw_created_at, '%Y-%m-%d %H:%i:%s');
```

Trong ví dụ, dữ liệu đi vào `@raw_amount` và `@raw_created_at` trước, sau đó được chuyển đổi thành giá trị phù hợp với cột. Cột không xuất hiện trong danh sách có thể nhận default hoặc giá trị do `SET` gán. Cần bảo đảm danh sách trường khớp đúng thứ tự dữ liệu thực tế.

Nếu file có cột không cần dùng, có thể ánh xạ trường đó vào user variable rồi bỏ qua trong `SET`. Cách này giúp giữ nguyên thứ tự file mà không phải sửa file nguồn.

## 5. Xử lý bản ghi trùng và dữ liệu lỗi

### 5.1. `IGNORE` và `REPLACE`

`LOAD DATA` hỗ trợ lựa chọn xử lý khi bản ghi xung đột khóa duy nhất:

- `IGNORE`: bỏ qua bản ghi gây xung đột và tiếp tục xử lý các bản ghi khác. Điều này có thể khiến số dòng được nạp thấp hơn số dòng trong file.
- `REPLACE`: thay bản ghi đang tồn tại khi xảy ra xung đột khóa duy nhất. Hãy đánh giá tác động xóa/thay thế dữ liệu, khóa ngoại, trigger và các unique key khác trước khi dùng.

Ví dụ:

```sql
LOAD DATA LOCAL INFILE '/client/import/products.csv'
IGNORE INTO TABLE staging_products
FIELDS TERMINATED BY ','
LINES TERMINATED BY '\n';
```

Không dùng `IGNORE` như cách che mọi lỗi dữ liệu. Nó có thể bỏ qua xung đột và một số điều kiện dữ liệu không hợp lệ, khiến file import có vẻ thành công nhưng thiếu bản ghi. Hãy kiểm tra warnings và số lượng dòng sau mỗi lần nạp.

### 5.2. Kiểm tra warnings ngay sau import

Sau câu lệnh `LOAD DATA`, đọc thông tin kết quả mà client trả về và kiểm tra cảnh báo trong cùng session:

```sql
SHOW COUNT(*) WARNINGS;
SHOW WARNINGS LIMIT 50;
```

Đối chiếu số dòng trong file, số dòng được đọc, số dòng bị bỏ qua, số dòng thay thế và số warning. Warnings có thể phản ánh dữ liệu bị cắt do độ dài cột, chuyển đổi số/ngày không hợp lệ, charset sai hoặc duplicate key.

Chế độ SQL, phiên bản MySQL, storage engine và việc có dùng `LOCAL`, `IGNORE` hay `REPLACE` ảnh hưởng cách một số lỗi được báo cáo và xử lý. Hãy thử với một bản sao nhỏ có chứa dữ liệu biên trước khi import toàn bộ.

### 5.3. Kiểu dữ liệu và giá trị NULL

Không nên nạp dữ liệu nguồn trực tiếp vào kiểu cột quá chặt nếu file có thể chứa chuỗi rỗng, số định dạng sai hoặc ngày tháng không chuẩn. Bảng staging có thể dùng cột text để giữ nguyên giá trị nguồn, sau đó kiểm tra và chuyển đổi bằng SQL.

Một số quy tắc cần xác định rõ:

- Chuỗi rỗng `''` có nghĩa là giá trị rỗng hay phải chuyển thành `NULL`?
- Giá trị `\N` trong file có được dùng để biểu diễn SQL `NULL` không?
- Số thập phân dùng dấu chấm hay dấu phẩy?
- Ngày có định dạng `YYYY-MM-DD`, `DD/MM/YYYY` hay định dạng khác?
- Khoảng trắng đầu/cuối có ý nghĩa hay cần `TRIM()`?

Định dạng mặc định của MySQL dùng `\N` để biểu diễn `NULL` trong nhiều trường hợp. Khi dùng `ESCAPED BY` hoặc `ENCLOSED BY` tùy chỉnh, cần kiểm tra lại cách parser diễn giải `NULL`, chuỗi rỗng và ký tự escape.

## 6. Quy trình import an toàn bằng staging table

Với dữ liệu nghiệp vụ, không nên để file bên ngoài ghi trực tiếp vào bảng chính mà không qua kiểm tra. Bảng staging cho phép giữ dữ liệu đầu vào, xác định lỗi và kiểm soát thời điểm cập nhật bảng đích.

### 6.1. Tạo bảng staging

Ví dụ:

```sql
CREATE TABLE staging_orders (
  order_id_text VARCHAR(40),
  customer_id_text VARCHAR(40),
  amount_text VARCHAR(80),
  created_at_text VARCHAR(80),
  imported_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
) ENGINE = InnoDB;
```

Các cột text giữ lại nội dung nguồn để kiểm tra chuyển đổi. Với file lớn, hãy thêm batch identifier hoặc cột nguồn file nếu quy trình cần truy vết nhiều lần import; có thể truyền giá trị cố định bằng user variable/`SET`.

### 6.2. Nạp file và xác minh

```sql
LOAD DATA LOCAL INFILE '/client/import/orders.csv'
INTO TABLE staging_orders
CHARACTER SET utf8mb4
FIELDS TERMINATED BY ','
OPTIONALLY ENCLOSED BY '"'
ESCAPED BY '\\'
LINES TERMINATED BY '\r\n'
IGNORE 1 LINES
(order_id_text, customer_id_text, amount_text, created_at_text);

SELECT COUNT(*) AS staged_rows
FROM staging_orders;

SELECT *
FROM staging_orders
WHERE order_id_text = ''
   OR customer_id_text = ''
   OR amount_text NOT REGEXP '^[0-9]+([.][0-9]{1,2})?$'
LIMIT 50;
```

Biểu thức chính quy chỉ là ví dụ cho số dương có tối đa hai chữ số thập phân. Nếu nghiệp vụ cho phép số âm, dấu phân cách hàng nghìn hoặc quy tắc làm tròn khác, cần điều chỉnh validation.

### 6.3. Chuyển dữ liệu hợp lệ vào bảng nghiệp vụ

Sau khi kiểm tra số dòng, duplicate, khóa ngoại và định dạng, chuyển dữ liệu hợp lệ bằng một câu SQL có kiểm soát:

```sql
START TRANSACTION;

INSERT INTO orders (order_id, customer_id, amount, created_at)
SELECT
  CAST(order_id_text AS UNSIGNED),
  CAST(customer_id_text AS UNSIGNED),
  CAST(amount_text AS DECIMAL(12, 2)),
  STR_TO_DATE(created_at_text, '%Y-%m-%d %H:%i:%s')
FROM staging_orders
WHERE order_id_text REGEXP '^[0-9]+$'
  AND customer_id_text REGEXP '^[0-9]+$'
  AND amount_text REGEXP '^[0-9]+([.][0-9]{1,2})?$'
  AND STR_TO_DATE(created_at_text, '%Y-%m-%d %H:%i:%s') IS NOT NULL;

COMMIT;
```

Đây là ví dụ khung; cần bổ sung điều kiện chống trùng, xác minh customer tồn tại và quy tắc cập nhật theo nghiệp vụ. Nếu câu lệnh thất bại, xử lý rollback theo quy trình của ứng dụng. Không xóa staging trước khi đã ghi nhận số liệu import và hoàn tất đối chiếu.

### 6.4. Chạy lại an toàn

Một job có thể bị chạy lại do timeout hoặc worker khởi động lại. Nếu không có cơ chế nhận diện lần import, dữ liệu có thể bị nhân đôi hoặc ghi đè sai. Có thể dùng `import_batch_id`, tên file kèm checksum, bảng audit import hoặc khóa duy nhất theo định danh nguồn.

Trước khi chạy lại, xác định lần import trước đã nạp đến đâu, câu lệnh đã commit hay chưa và dữ liệu staging còn tồn tại không. Thiết kế bước merge có tính idempotent theo nghiệp vụ; tránh dùng `REPLACE` rộng nếu không muốn xóa rồi chèn lại các bản ghi có liên quan.

## 7. Hiệu năng và vận hành

`LOAD DATA` thường hiệu quả hơn việc gửi từng câu `INSERT` riêng lẻ vì MySQL xử lý dữ liệu theo đường nạp hàng loạt. Tuy nhiên, tốc độ thực tế còn phụ thuộc kích thước file, index, constraint, trigger, storage, binlog, network và tải đồng thời.

### 7.1. Chọn server-side hay LOCAL theo vị trí file

- File đã nằm trên host database và có thể đặt trong thư mục được kiểm soát: cân nhắc `INFILE` để server đọc trực tiếp.
- File nằm trên máy ETL hoặc container: `LOCAL` thường đơn giản hơn, nhưng cần giới hạn quyền đọc file và bảo vệ kết nối.
- File rất lớn hoặc đường truyền client-server chậm: cân nhắc chuyển file tới vùng staging gần database bằng kênh truyền có kiểm soát rồi dùng `INFILE`, nếu chính sách hạ tầng cho phép.

Không nên chọn `INFILE` chỉ vì tránh truyền dữ liệu qua mạng nếu việc cấp quyền `FILE` và đưa file lên host database tạo ra rủi ro vận hành lớn hơn.

### 7.2. Import file lớn

Với file lớn, hãy:

- Đo tốc độ đọc file, network throughput, disk I/O và thời gian thực thi trên dữ liệu đại diện.
- Bảo đảm server có đủ dung lượng cho file tạm, binary log, redo/undo và dữ liệu đích.
- Kiểm tra tác động của index, unique constraint, foreign key và trigger.
- Chia file thành batch nếu có thể chấp nhận các batch commit riêng và cần khả năng tiếp tục.
- Theo dõi lock wait, replication lag và thời gian backup trong lúc import.
- Lưu số liệu rows loaded, skipped, replaced, warnings và thời gian xử lý.

Không tắt kiểm tra constraint hoặc trigger một cách tùy tiện để tăng tốc. Nếu cần tối ưu, hãy đánh giá trên bản sao môi trường, bảo đảm dữ liệu được xác thực trước khi constraint được bật lại và kiểm tra toàn bộ kết quả.

### 7.3. Transaction và tính toàn vẹn

Với bảng InnoDB, thao tác ghi dữ liệu có tính transactional theo khả năng của storage engine; có thể tổ chức import và bước merge trong transaction phù hợp. Với bảng nontransactional, lỗi giữa chừng có thể để lại một phần dữ liệu đã ghi. Các bước như tạo bảng hoặc thay đổi cấu trúc cũng có quy tắc commit riêng, vì vậy không nên giả định toàn bộ quy trình gồm tạo staging, load file, kiểm tra và merge là một transaction nguyên tử duy nhất.

Đối với dữ liệu quan trọng, ưu tiên InnoDB, import vào staging, kiểm tra trước khi merge và có backup/điểm khôi phục phù hợp. Hãy thử rollback, duplicate và lỗi chuyển đổi trong môi trường thử nghiệm trước khi triển khai.

## 8. Quy trình chẩn đoán lỗi

Khi câu lệnh `LOAD DATA` thất bại hoặc dữ liệu không đúng, kiểm tra theo thứ tự:

1. **Xác định vị trí file:** với `INFILE`, kiểm tra host database; với `LOCAL`, kiểm tra máy chạy client hoặc container.
2. **Kiểm tra quyền filesystem:** user chạy `mysqld` hay user chạy client có quyền đọc file? Thư mục cha có quyền traverse không?
3. **Kiểm tra quyền MySQL:** server-side cần `FILE` và quyền trên bảng; LOCAL cần quyền ghi bảng và khả năng LOCAL được bật.
4. **Kiểm tra cấu hình:** đọc `secure_file_priv` cho server-side và `local_infile` cho LOCAL; xác nhận tùy chọn connector.
5. **Kiểm tra dialect:** charset, BOM, delimiter, quote, escape, newline và header có khớp file không?
6. **Kiểm tra warnings:** chạy `SHOW WARNINGS` ngay sau import, đối chiếu số dòng file với số dòng được nạp.
7. **Kiểm tra bảng đích:** duplicate key, constraint, trigger, kiểu dữ liệu, độ dài cột và giá trị NULL.
8. **Kiểm tra tài nguyên:** dung lượng đĩa, temporary directory, network, I/O, binary log và replication lag.

Một số lỗi thường gặp:

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| `Access denied` khi dùng `INFILE` | Thiếu `FILE`, sai host/path hoặc `secure_file_priv` chặn | Kiểm tra grant, đường dẫn server và biến bảo vệ |
| Không tìm thấy file | File nằm trên client nhưng dùng `INFILE`, hoặc nằm trên server nhưng dùng `LOCAL` | Xác định rõ nơi chạy client và nơi chạy `mysqld` |
| LOCAL bị từ chối | `local_infile` ở server hoặc connector chưa bật | Kiểm tra chính sách, server variable và tùy chọn driver |
| Ký tự tiếng Việt bị lỗi | Charset khai báo không khớp hoặc file có BOM | Xác định encoding và nạp với charset đúng; chuẩn hóa file nếu cần |
| Cột cuối có ký tự lạ | Sai newline, ví dụ CRLF bị đọc như LF | Điều chỉnh `LINES TERMINATED BY` và kiểm tra dữ liệu mẫu |
| Số dòng nạp ít hơn file | Header, dòng lỗi, duplicate hoặc `IGNORE` | Đọc kết quả và warnings, kiểm tra từng nhóm bản ghi |
| Import chậm | Index/constraint/trigger, I/O, binlog hoặc network là nút thắt | Đo từng tầng và tối ưu bằng benchmark đại diện |

## 9. Bài thực hành

Một nhóm ETL chạy trong container riêng, tạo file `customers.csv` có 2 triệu dòng. MySQL chạy trên một máy chủ khác. File chứa tên tiếng Việt, cột ngày giờ, trường email có thể rỗng và header ở dòng đầu. Tài khoản ETL hiện chỉ có quyền `INSERT` trên `import_db.staging_customers`.

Hãy thiết kế hai phương án nhập và giải thích lựa chọn:

1. Nếu dùng `LOAD DATA LOCAL INFILE`, cần bật những khả năng nào ở server và connector? Tệp được đọc ở đâu và truyền qua đường nào?
2. Nếu dùng `LOAD DATA INFILE`, cần chuyển file đến đâu, quyền MySQL và quyền hệ điều hành nào cần có?
3. Vì sao tài khoản ETL không nên được cấp `FILE` chỉ để import từ container?
4. Viết câu lệnh `LOAD DATA` có `CHARACTER SET utf8mb4`, delimiter, quote, escape, newline và bỏ qua header.
5. Làm thế nào chuyển email rỗng thành `NULL`, parse ngày giờ và phát hiện bản ghi lỗi?
6. Cần kiểm tra những gì sau khi load để biết đủ 2 triệu dòng đã được xử lý đúng?
7. Thiết kế cơ chế batch identifier và chạy lại an toàn nếu container bị dừng giữa chừng.
8. Nêu các biện pháp hạn chế rủi ro khi bật LOCAL, đặc biệt nếu client kết nối tới nhiều server khác nhau.

Một phương án tốt phải xác định được vị trí file, quyền của từng thành phần, cấu hình LOCAL, định dạng dữ liệu và cách đối chiếu kết quả. Hãy thử trước với một file nhỏ có dấu tiếng Việt, dấu phẩy trong trường text, chuỗi rỗng, ngày không hợp lệ và dòng trùng khóa.

## 10. Những nhầm lẫn thường gặp

- **Cho rằng `INFILE` đọc file trên máy chạy câu lệnh SQL:** nếu không có `LOCAL`, server đọc file trên host database.
- **Cho rằng `LOCAL` không cần cấu hình server:** server và client/connector đều phải cho phép khả năng LOCAL.
- **Cấp `FILE` cho mọi tài khoản ETL:** quyền này có phạm vi toàn cục và ảnh hưởng đến các thao tác file phía server; chỉ cấp khi thực sự dùng server-side import.
- **Cho rằng `secure_file_priv` giới hạn thư mục trên client:** biến này kiểm soát thao tác file phía server, không thay thế allowlist đường dẫn trong ứng dụng client.
- **Giả định mọi CSV đều dùng cùng quy tắc quote/escape:** phải kiểm tra dialect thực tế của file xuất.
- **Bỏ qua warnings vì câu lệnh đã chạy xong:** câu lệnh có thể nạp ít dòng hơn dự kiến hoặc chuyển đổi dữ liệu không như mong muốn.
- **Import thẳng vào bảng chính:** staging giúp phát hiện dữ liệu lỗi, duplicate và sai định dạng trước khi cập nhật dữ liệu nghiệp vụ.
- **Dùng `IGNORE` để che lỗi:** bỏ qua bản ghi có thể làm thiếu dữ liệu mà không xử lý nguyên nhân.

## Kết luận

`LOAD DATA INFILE` để MySQL Server đọc tệp trên máy chủ, thường cần quyền `FILE`, quyền filesystem phù hợp và tuân thủ `secure_file_priv`. `LOAD DATA LOCAL INFILE` để client đọc tệp trên máy client rồi gửi nội dung tới server; nó cần sự cho phép của cả server lẫn connector và phải được kiểm soát vì có thể khiến client gửi tệp cục bộ theo yêu cầu từ server. Dù chọn cách nào, cần mô tả chính xác charset và dialect, kiểm tra warnings, dùng staging cho dữ liệu nghiệp vụ và ghi nhận kết quả import để có thể đối chiếu hoặc chạy lại an toàn.
