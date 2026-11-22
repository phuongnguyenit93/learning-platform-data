# CSV: delimiter, enclosure, escape, newline, charset và biểu diễn NULL

CSV thường được dùng để trao đổi dữ liệu giữa MySQL, Excel, hệ thống kế toán, ứng dụng web và các công cụ phân tích. Tuy nhiên, CSV không có một cách mã hóa duy nhất cho mọi hệ thống. Hai file cùng có đuôi `.csv` vẫn có thể khác nhau về dấu phân cách cột, dấu bao chuỗi, cách escape dấu nháy, kiểu xuống dòng, charset và cách biểu diễn giá trị `NULL`.

Trong MySQL, `LOAD DATA [LOCAL] INFILE` đọc file văn bản vào bảng với tốc độ cao. `SELECT ... INTO OUTFILE` ghi kết quả truy vấn ra file trên máy chủ. Hai câu lệnh dùng chung quy tắc `FIELDS` và `LINES`; muốn dữ liệu round-trip chính xác, cấu hình đọc và ghi phải khớp nhau. Bài học dùng MySQL 8.4 và minh họa một định dạng CSV có dấu phẩy, dấu nháy kép, escape bằng backslash, dòng CRLF và UTF-8.

## Mục tiêu

Sau bài học, bạn có thể:

- Phân biệt delimiter, enclosure, escape character và line terminator.
- Chọn đúng `FIELDS TERMINATED BY`, `ENCLOSED BY`, `ESCAPED BY` và `LINES TERMINATED BY`.
- Nạp file CSV có header, cột theo thứ tự khác bảng và dữ liệu cần chuyển đổi.
- Phân biệt `NULL`, chuỗi rỗng và chuỗi chữ `NULL`.
- Xử lý charset UTF-8/`utf8mb4`, BOM và newline giữa các hệ điều hành.
- Xuất CSV bằng `SELECT ... INTO OUTFILE`, kiểm tra cảnh báo và xử lý lỗi import an toàn.

## 1. CSV là một định dạng trao đổi có nhiều biến thể

CSV là viết tắt của *comma-separated values*, nhưng trên thực tế dấu phân cách không nhất thiết là dấu phẩy. Các công cụ ở nhiều quốc gia có thể dùng dấu chấm phẩy hoặc tab; file Windows thường dùng CRLF, trong khi file Linux thường dùng LF. Một số công cụ bao chuỗi bằng dấu nháy kép, một số không bao chuỗi nếu không cần thiết.

Ví dụ hai dòng sau có cùng ý nghĩa nhưng cách biểu diễn khác nhau:

```text
101,Nguyen Van A,125000
102,Tran Thi B,98000
```

```text
101;"Nguyen Van A";125000\r\n
102;"Tran Thi B";98000\r\n
```

Để MySQL đọc chính xác, cần xác định rõ các thành phần của file trước khi viết câu lệnh:

| Thành phần | Tên trong MySQL | Ví dụ | Ý nghĩa |
|---|---|---|---|
| Dấu phân cách cột | `FIELDS TERMINATED BY` | `','` hoặc `';'` | Kết thúc một trường và bắt đầu trường kế tiếp. |
| Dấu bao trường | `FIELDS ENCLOSED BY` | `'"'` | Đánh dấu phần đầu/cuối của giá trị, thường dùng cho chuỗi. |
| Dấu escape | `FIELDS ESCAPED BY` | `'\\'` trong SQL | Giúp biểu diễn dấu nháy, delimiter hoặc ký tự đặc biệt bên trong giá trị. |
| Dấu kết thúc dòng | `LINES TERMINATED BY` | `'\r\n'` hoặc `'\n'` | Đánh dấu kết thúc một bản ghi. |
| Charset file | `CHARACTER SET` | `utf8mb4` | Cho MySQL biết cách giải mã byte trong file. |
| Giá trị không có dữ liệu | Quy tắc `NULL` | `\N` hoặc `NULL` | Phân biệt giá trị SQL `NULL` với chuỗi rỗng. |

MySQL yêu cầu ký tự enclosure và escape nếu không rỗng phải là một ký tự; delimiter và line terminator có thể gồm nhiều ký tự. Các chuỗi định dạng trong `FIELDS`/`LINES` chỉ hỗ trợ ký tự ASCII. Tránh cấu hình delimiter trùng hoặc là tiền tố của enclosure/line terminator vì parser có thể không xác định được ranh giới.

## 2. Quy tắc mặc định của MySQL

Nếu không chỉ định `FIELDS` và `LINES`, MySQL sử dụng tương đương cấu hình sau:

```sql
FIELDS TERMINATED BY '\t'
       ENCLOSED BY ''
       ESCAPED BY '\\'
LINES TERMINATED BY '\n'
       STARTING BY ''
```

Nghĩa là mặc định MySQL đọc file phân cách bằng tab, không có dấu bao chuỗi, dùng backslash làm escape và kết thúc dòng bằng LF. Đây không phải cấu hình CSV phổ biến trong Excel.

Trong SQL literal, backslash cũng là ký tự escape của MySQL. Vì vậy:

- `'\t'` biểu diễn ký tự tab.
- `'\n'` biểu diễn line feed (LF).
- `'\r'` biểu diễn carriage return (CR).
- `'\r\n'` biểu diễn cặp CRLF.
- `'\\'` biểu diễn một ký tự backslash thực tế.

Khi dùng `FIELDS ESCAPED BY '\\'`, file có thể dùng các chuỗi như `\t`, `\n`, `\r`, `\\` để biểu diễn ký tự đặc biệt. Riêng `\N` là quy ước biểu diễn SQL `NULL` trong cấu hình mặc định.

## 3. Đọc CSV bằng LOAD DATA

Giả sử file `orders.csv` được tạo từ một công cụ bảng tính, có header, dấu phẩy phân cách cột, dấu nháy kép bao chuỗi và CRLF kết thúc dòng:

```text
order_id,customer_name,amount,created_at,note
101,"Nguyễn Văn An",125000.00,2026-11-19 09:30:00,"Giao hàng, gọi trước"
102,"Trần Thị Bình",98000.00,2026-11-19 10:00:00,"Khách nói ""để chiều"""
103,"Lê Minh Châu",\N,2026-11-19 11:00:00,
```

Ví dụ nạp vào bảng staging:

```sql
CREATE TABLE orders_stage (
    order_id        VARCHAR(30),
    customer_name   VARCHAR(255),
    amount_text     VARCHAR(50),
    created_at_text VARCHAR(50),
    note            TEXT
) ENGINE = InnoDB;

LOAD DATA LOCAL INFILE '/data/orders.csv'
INTO TABLE orders_stage
CHARACTER SET utf8mb4
FIELDS TERMINATED BY ','
       OPTIONALLY ENCLOSED BY '"'
       ESCAPED BY '\\'
LINES TERMINATED BY '\r\n'
IGNORE 1 LINES
(order_id, customer_name, amount_text, created_at_text, note);
```

Giải thích:

- `LOCAL` yêu cầu chương trình client đọc file trên máy đang chạy client rồi gửi nội dung đến MySQL server.
- `CHARACTER SET utf8mb4` giải mã byte file theo UTF-8 và chuyển dữ liệu vào charset của các cột đích khi cần.
- `FIELDS TERMINATED BY ','` chọn dấu phẩy làm delimiter.
- `OPTIONALLY ENCLOSED BY '"'` cho phép trường chuỗi có thể được bao bởi dấu nháy kép. Với input, MySQL xử lý dấu bao khi xuất hiện dù có từ `OPTIONALLY` hay không; từ này chủ yếu quyết định cách xuất dữ liệu.
- `ESCAPED BY '\\'` dùng backslash để escape ký tự đặc biệt và nhận `\N` là `NULL`.
- `LINES TERMINATED BY '\r\n'` đọc file Windows có cặp CRLF.
- `IGNORE 1 LINES` bỏ qua dòng header.
- Danh sách cột cho biết thứ tự trường trong file; không cần trùng thứ tự cột trong bảng.

Nếu file được tạo trên Linux/macOS với LF, đổi thành:

```sql
LINES TERMINATED BY '\n'
```

Nếu file dùng CR đơn làm line terminator, chỉ định `LINES TERMINATED BY '\r'`. Không nên đoán newline dựa vào phần mở rộng file; hãy kiểm tra file nguồn hoặc xác nhận với hệ thống xuất dữ liệu.

### 3.1. Delimiter và enclosure

Delimiter phân chia các trường. Nếu giá trị chứa delimiter, newline hoặc ký tự enclosure, trường đó cần được bao đúng cách và escape theo quy tắc của file.

Ví dụ với dấu phẩy:

```text
101,"Nguyễn Văn An, cửa hàng 1",125000
```

Nếu không có enclosure, parser có thể hiểu tên khách hàng thành hai cột riêng. Với các trường không phải lúc nào cũng có dấu nháy, dùng `OPTIONALLY ENCLOSED BY '"'` cho câu lệnh xuất; khi đọc, MySQL vẫn nhận diện enclosure nếu có.

Với `ENCLOSED BY '"'`, dấu nháy kép bên trong giá trị có thể được biểu diễn bằng cách nhân đôi:

```text
"Khách nói ""để chiều"""
```

Kết quả sau khi đọc là:

```text
Khách nói "để chiều"
```

Hoặc file có thể escape dấu nháy bằng ký tự `ESCAPED BY`, ví dụ `\"` nếu escape là backslash. Cần xác nhận công cụ xuất CSV đang dùng cách nào; không đổi `ESCAPED BY` tùy ý giữa hai hệ thống.

### 3.2. ESCAPED BY và ký tự đặc biệt

Với backslash là escape character, MySQL nhận các chuỗi phổ biến:

| Trong file | Giá trị sau khi đọc |
|---|---|
| `\\` | Một ký tự backslash `\`. |
| `\t` | Tab. |
| `\n` | Line feed nằm trong giá trị. |
| `\r` | Carriage return nằm trong giá trị. |
| `\0` | Byte NUL. |
| `\N` | SQL `NULL`. |

Không nên đặt `ESCAPED BY ''` chỉ để loại bỏ backslash nếu file có thể chứa dấu nháy, delimiter, newline hoặc ký tự đặc biệt. Khi escape rỗng, MySQL không diễn giải escape sequence; dữ liệu có thể bị tách trường hoặc tách dòng sai. Nếu hệ thống nguồn dùng quy tắc khác, hãy điều chỉnh định dạng xuất ở nguồn hoặc chuẩn hóa file trước khi nạp.

## 4. Phân biệt NULL, chuỗi rỗng và chữ NULL

Đây là một trong những lỗi phổ biến nhất khi di chuyển dữ liệu. Ba giá trị sau không giống nhau:

| Biểu diễn | Ý nghĩa |
|---|---|
| `\N` | Giá trị SQL `NULL` khi `ESCAPED BY` là backslash. |
| Trường rỗng giữa hai delimiter, ví dụ `101,,125000` | Chuỗi rỗng đối với cột chuỗi; với cột số/ngày giờ, phép chuyển đổi có thể tạo giá trị mặc định hoặc warning tùy kiểu và SQL mode. |
| `NULL` hoặc `"NULL"` | Khi có `ENCLOSED BY`, từ `NULL` không được bao được đọc là SQL `NULL`; từ `NULL` được bao như `"NULL"` được đọc là chuỗi literal `NULL`. |

Với cấu hình mặc định, `NULL` được ghi ra file là `\N`, và khi nạp `\N` được hiểu là SQL `NULL` nếu escape character là backslash. Khi `FIELDS ENCLOSED BY` không rỗng, trường chứa chữ `NULL` không được bao cũng được hiểu là `NULL`; chữ `NULL` nằm trong dấu bao là chuỗi `'NULL'`.

Ví dụ ba trường khác nhau:

```text
101,\N,active
102,,active
103,"NULL",active
```

Trong ví dụ này, trường thứ hai lần lượt là SQL `NULL`, chuỗi rỗng và chuỗi ký tự `NULL`.

Khi `FIELDS ESCAPED BY ''`, MySQL ghi `NULL` thành chữ `NULL`, không phải `\N`. Với fixed-row format (cả `FIELDS TERMINATED BY` và `FIELDS ENCLOSED BY` đều rỗng), `NULL` được ghi thành chuỗi rỗng; lúc đó không thể phân biệt `NULL` với empty string khi đọc lại. Không dùng fixed-row format nếu cần bảo toàn sự khác nhau này.

**Nguyên tắc:** thống nhất sentinel `NULL` giữa bên xuất và bên nhập. Không tự động biến mọi trường rỗng thành `NULL` nếu nghiệp vụ cần phân biệt “không có giá trị” với “có giá trị nhưng rỗng”.

## 5. Charset và Unicode

Charset của file là cách diễn giải byte trên đĩa; charset của cột là cách lưu chuỗi trong MySQL. Hai khái niệm này độc lập. Với dữ liệu tiếng Việt, nên dùng UTF-8 và cột `utf8mb4` để giữ đầy đủ Unicode.

Kiểm tra charset/collation của bảng và cột:

```sql
SHOW CREATE TABLE orders_stage\G

SHOW VARIABLES LIKE 'character_set_database';
SHOW VARIABLES LIKE 'character_set_server';
SHOW VARIABLES LIKE 'character_set_filesystem';
```

Chỉ định charset file khi nạp:

```sql
LOAD DATA LOCAL INFILE '/data/orders.csv'
INTO TABLE orders_stage
CHARACTER SET utf8mb4
FIELDS TERMINATED BY ','
       OPTIONALLY ENCLOSED BY '"'
       ESCAPED BY '\\'
LINES TERMINATED BY '\r\n'
IGNORE 1 LINES;
```

`SET NAMES` và `character_set_client` không quyết định charset của file đầu vào. `LOAD DATA` đọc toàn bộ trường trong file theo cùng một charset đã chỉ định, không tự đoán charset riêng cho từng cột. MySQL không hỗ trợ nạp trực tiếp file dùng charset `ucs2`, `utf16`, `utf16le` hoặc `utf32`; hãy chuyển đổi file sang charset phù hợp trước khi import.

Khi xuất file, chỉ định charset tương ứng:

```sql
SELECT order_id, customer_name, amount, created_at, note
INTO OUTFILE '/var/lib/mysql-files/orders.csv'
CHARACTER SET utf8mb4
FIELDS TERMINATED BY ','
       OPTIONALLY ENCLOSED BY '"'
       ESCAPED BY '\\'
LINES TERMINATED BY '\r\n'
FROM orders
ORDER BY order_id;
```

Nếu bỏ `CHARACTER SET` trong `SELECT ... INTO OUTFILE`, dữ liệu được ghi theo binary charset, nghĩa là không có chuyển đổi charset. Khi kết quả chứa các cột với nhiều charset khác nhau, file có thể khó hoặc không thể nạp lại chính xác. Vì vậy, nên chọn charset rõ ràng ở cả hai chiều.

### 5.1. BOM và lỗi ký tự tiếng Việt

Một số trình soạn thảo lưu UTF-8 kèm BOM (byte order mark) ở đầu file. BOM có thể bị đọc như một phần của tên cột đầu tiên hoặc giá trị đầu tiên, làm dữ liệu xuất hiện ký tự lạ như `ï»¿` hoặc khiến giá trị đầu tiên không khớp. Nếu gặp hiện tượng này, kiểm tra byte đầu file và xuất lại UTF-8 không BOM hoặc loại bỏ BOM trước khi chạy `LOAD DATA`.

Các dấu hiệu charset sai thường gặp:

- Chữ tiếng Việt biến thành `?` hoặc chuỗi ký tự mojibake.
- Import không lỗi nhưng giá trị đầu tiên của file có ký tự lạ.
- File xuất ra có nội dung đúng ở một máy nhưng sai khi mở bằng công cụ khác.

Hãy xác nhận charset nguồn, chỉ định `CHARACTER SET` phù hợp và kiểm tra charset/collation của cột đích trước khi nạp số lượng lớn.

## 6. Newline và dữ liệu nhiều dòng

Các hệ điều hành và ứng dụng có thể dùng cách xuống dòng khác nhau:

| Quy ước | Byte | Cách cấu hình |
|---|---|---|
| LF (Linux, Unix) | `0A` | `LINES TERMINATED BY '\n'` |
| CRLF (Windows) | `0D 0A` | `LINES TERMINATED BY '\r\n'` |
| CR (một số file macOS cũ) | `0D` | `LINES TERMINATED BY '\r'` |

Nếu chọn sai line terminator, MySQL có thể để lại `\r` ở cuối trường cuối cùng hoặc đọc nhiều bản ghi thành một dòng. Ví dụ file Windows đọc với `LINES TERMINATED BY '\n'` có thể giữ CR ở cuối giá trị cuối dòng. Ngược lại, file LF đọc với CRLF có thể không được tách dòng đúng.

CSV cho phép một trường chuỗi chứa newline nếu trường được bao bằng enclosure hợp lệ. Do đó, số dòng vật lý trong file có thể lớn hơn số bản ghi logic. Không dùng công cụ đếm dòng văn bản đơn giản để kết luận số hàng CSV khi file có trường nhiều dòng; hãy dùng parser CSV hoặc kiểm tra kết quả sau import.

## 7. Ánh xạ cột và làm sạch dữ liệu khi nạp

File CSV thường có thứ tự cột khác bảng, có cột thừa hoặc chứa dữ liệu cần chuẩn hóa. Dùng danh sách cột và user variable để kiểm soát việc ánh xạ.

Ví dụ file có thứ tự `customer_name, order_id, amount, created_at, note`, trong khi bảng đích có thứ tự khác:

```sql
LOAD DATA LOCAL INFILE '/data/orders.csv'
INTO TABLE orders
CHARACTER SET utf8mb4
FIELDS TERMINATED BY ','
       OPTIONALLY ENCLOSED BY '"'
       ESCAPED BY '\\'
LINES TERMINATED BY '\r\n'
IGNORE 1 LINES
(@customer_name, @order_id, @amount, @created_at, @note)
SET customer_name = TRIM(@customer_name),
    order_id = CAST(@order_id AS UNSIGNED),
    amount = NULLIF(@amount, ''),
    created_at = STR_TO_DATE(@created_at, '%Y-%m-%d %H:%i:%s'),
    note = @note;
```

Trong ví dụ:

- `@customer_name` và các biến còn lại nhận giá trị theo thứ tự trong file.
- `TRIM()` loại bỏ khoảng trắng thừa ở hai đầu tên khách hàng.
- `CAST()` chuyển mã đơn hàng sang số nguyên không dấu.
- `NULLIF(@amount, '')` đổi trường số rỗng thành SQL `NULL`.
- `STR_TO_DATE()` chuyển chuỗi ngày giờ theo định dạng đã biết thành giá trị `DATETIME`.
- `@note` được giữ nguyên; nếu trường trong file là `\N` và escape là backslash, MySQL nhận nó là `NULL`.

Không nên nạp trực tiếp dữ liệu không đáng tin cậy vào bảng nghiệp vụ có nhiều ràng buộc. Với import quan trọng, dùng bảng staging có cột `VARCHAR` để giữ dữ liệu thô, kiểm tra lỗi định dạng, sau đó mới `INSERT ... SELECT` sang bảng thật với các phép chuyển đổi tường minh.

### 7.1. Ví dụ pipeline staging

```sql
-- 1. Nạp file vào bảng staging với cột văn bản.
LOAD DATA LOCAL INFILE '/data/orders.csv'
INTO TABLE orders_stage
CHARACTER SET utf8mb4
FIELDS TERMINATED BY ','
       OPTIONALLY ENCLOSED BY '"'
       ESCAPED BY '\\'
LINES TERMINATED BY '\r\n'
IGNORE 1 LINES
(order_id, customer_name, amount_text, created_at_text, note);

-- 2. Kiểm tra các dòng có dữ liệu bắt buộc bị thiếu.
SELECT *
FROM orders_stage
WHERE order_id IS NULL
   OR customer_name IS NULL
   OR amount_text = ''
   OR created_at_text = '';

-- 3. Kiểm tra chuỗi ngày giờ không chuyển đổi được.
SELECT created_at_text
FROM orders_stage
WHERE created_at_text IS NOT NULL
  AND STR_TO_DATE(created_at_text, '%Y-%m-%d %H:%i:%s') IS NULL;

-- 4. Chỉ nạp các dòng hợp lệ vào bảng nghiệp vụ.
INSERT INTO orders (order_id, customer_name, amount, created_at, note)
SELECT CAST(order_id AS UNSIGNED),
       TRIM(customer_name),
       CAST(NULLIF(amount_text, '') AS DECIMAL(12,2)),
       STR_TO_DATE(created_at_text, '%Y-%m-%d %H:%i:%s'),
       note
FROM orders_stage
WHERE order_id REGEXP '^[0-9]+$'
  AND customer_name IS NOT NULL
  AND STR_TO_DATE(created_at_text, '%Y-%m-%d %H:%i:%s') IS NOT NULL;
```

Điều kiện kiểm tra ở ví dụ chỉ minh họa. Trong hệ thống thật, cần xác định quy tắc nghiệp vụ cho giá trị âm, độ chính xác tiền tệ, múi giờ, ngày không hợp lệ, khóa trùng và trường bắt buộc. Lưu lại các dòng bị loại vào bảng lỗi để có thể sửa và nạp lại.

## 8. Xuất CSV bằng SELECT ... INTO OUTFILE

`SELECT ... INTO OUTFILE` ghi kết quả truy vấn thành file trên máy chủ MySQL, không phải máy client. Ví dụ:

MySQL ghi ký tự enclosure bên trong giá trị bằng cách đặt ký tự `ESCAPED BY` trước nó. Với backslash, dấu nháy kép bên trong trường được xuất thành `\"`. Một số thư viện CSV theo RFC 4180 thường dùng cách nhân đôi dấu nháy (`""`) thay vì backslash. MySQL có thể đọc dạng nhân đôi khi trường bắt đầu bằng enclosure, nhưng định dạng xuất của MySQL không nhất thiết giống định dạng của mọi ứng dụng. Nếu cần trao đổi với một hệ thống cụ thể, hãy thử file thực tế bằng parser của hệ thống đó.

```sql
SELECT order_id, customer_name, amount, created_at, note
INTO OUTFILE '/var/lib/mysql-files/orders-export.csv'
CHARACTER SET utf8mb4
FIELDS TERMINATED BY ','
       OPTIONALLY ENCLOSED BY '"'
       ESCAPED BY '\\'
LINES TERMINATED BY '\r\n'
FROM orders
ORDER BY order_id;
```

Các yêu cầu cần nhớ:

- Tài khoản cần quyền `FILE`.
- Đường dẫn là đường dẫn trên máy chủ chạy `mysqld`.
- Nếu `secure_file_priv` được đặt thành một thư mục, file phải nằm trong thư mục đó.
- File đích không được tồn tại; MySQL không ghi đè file có sẵn.
- File được tạo dưới tài khoản hệ điều hành chạy `mysqld`; quyền truy cập file cần được quản lý riêng.

Kiểm tra cấu hình:

```sql
SHOW VARIABLES LIKE 'secure_file_priv';
```

Nếu `secure_file_priv` trả về `NULL`, thao tác import/export file phía server bị vô hiệu hóa. Nếu trả về một đường dẫn, chỉ dùng thư mục đó. Không mở rộng quyền file hoặc đặt biến thành thư mục dùng chung chỉ để làm cho một lệnh export chạy được.

Nếu muốn tạo file trên máy client, có thể chạy truy vấn bằng client và chuyển stdout ra file ở máy client, ví dụ `mysql -e "SELECT ..." > result.txt`. Tuy nhiên, cách này cần xử lý header, escape và định dạng đầu ra riêng; nó không tự động tương đương với `SELECT ... INTO OUTFILE`.

## 9. LOCAL và quyền truy cập file

Hai dạng `LOAD DATA` có nơi đọc file và yêu cầu bảo mật khác nhau:

| Câu lệnh | File nằm ở đâu? | Quyền/chú ý |
|---|---|---|
| `LOAD DATA INFILE` | Máy chủ MySQL | Cần quyền `FILE`; chịu giới hạn của `secure_file_priv`; file phải đọc được bởi tài khoản hệ điều hành chạy MySQL. |
| `LOAD DATA LOCAL INFILE` | Máy client đang kết nối | Client đọc file và gửi lên server; không cần quyền `FILE`, nhưng cả client lẫn server phải cho phép `LOCAL`. |
| `SELECT ... INTO OUTFILE` | Máy chủ MySQL | Cần quyền `FILE`; chịu giới hạn `secure_file_priv`; file đích không được tồn tại. |

Kiểm tra biến phía server:

```sql
SHOW VARIABLES LIKE 'local_infile';
SHOW VARIABLES LIKE 'secure_file_priv';
```

`LOAD DATA LOCAL INFILE` chỉ hoạt động khi server và client đều cho phép. Nếu `local_infile` bị tắt, câu lệnh LOCAL sẽ báo lỗi. Vì client gửi file qua kết nối, LOCAL có thể chậm hơn server đọc file trực tiếp và server cần đủ dung lượng thư mục tạm để lưu bản sao file trong lúc xử lý.

Chỉ bật LOCAL khi cần, kết nối tới server đáng tin cậy và sử dụng TLS theo chính sách hệ thống. Một client có thể bị server không đáng tin cậy yêu cầu gửi file cục bộ; vì vậy không nên bật LOCAL rộng rãi cho các môi trường kết nối tùy ý.

Một điểm dễ bỏ sót: `LOAD DATA LOCAL` không kèm `REPLACE` có hiệu lực tương tự `IGNORE`. Các dòng trùng khóa có thể bị bỏ qua và lỗi chuyển đổi dữ liệu có thể trở thành warning thay vì dừng toàn bộ thao tác. Nếu cần kiểm soát chặt chẽ, nạp vào staging, đọc warnings và xác minh số dòng trước khi đưa dữ liệu vào bảng nghiệp vụ.

## 10. Kiểm tra warnings và kết quả import

Ngay sau `LOAD DATA`, kiểm tra kết quả trả về và warnings:

```sql
SHOW COUNT(*) WARNINGS;
SHOW WARNINGS LIMIT 50;
```

Các warning có thể cho biết:

- Giá trị số không hợp lệ hoặc bị cắt cụt.
- Ngày giờ không chuyển đổi được.
- Giá trị `NULL` được nạp vào cột `NOT NULL`.
- Dữ liệu quá dài so với kích thước cột.
- Dòng trùng khóa bị bỏ qua khi dùng `IGNORE` hoặc `LOCAL`.

Không chỉ kiểm tra câu lệnh có chạy thành công hay không. Hãy đối chiếu số dòng đọc, số dòng được nạp, số dòng cảnh báo và số dòng bị bỏ qua. Với dữ liệu quan trọng, lưu bản file gốc, thời điểm import, câu lệnh đã dùng và kết quả kiểm tra để có thể kiểm toán hoặc nạp lại.

## 11. Các lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Mỗi dòng thành một trường duy nhất | Chọn sai delimiter, thường là tab thay vì dấu phẩy | Khai báo đúng `FIELDS TERMINATED BY`. |
| Giá trị cuối dòng có ký tự `\r` | Đọc CRLF bằng `LINES TERMINATED BY '\n'` | Dùng `LINES TERMINATED BY '\r\n'`. |
| Tiếng Việt thành ký tự lạ | Charset file và charset import không khớp | Xác nhận nguồn, dùng UTF-8/`utf8mb4` và chỉ định `CHARACTER SET`. |
| Cột đầu tiên có `ï»¿` | File có UTF-8 BOM | Xuất UTF-8 không BOM hoặc loại bỏ BOM trước khi nạp. |
| Cột bị lệch | Header chưa bỏ, thứ tự cột sai hoặc delimiter/enclosure sai | Dùng `IGNORE 1 LINES`, chỉ định danh sách cột và kiểm tra dialect. |
| Dấu phẩy trong tên bị tách cột | Trường không được bao đúng cách | Dùng enclosure phù hợp và xác minh cách escape quote. |
| Chuỗi `NULL` thành SQL NULL ngoài ý muốn | Có enclosure nhưng trường chữ NULL không được bao | Bao chuỗi literal bằng enclosure; thống nhất sentinel NULL. |
| Empty string biến thành NULL | File dùng sentinel không phân biệt hoặc chuyển đổi qua `NULLIF` | Giữ riêng empty string và `\N`; không chuẩn hóa quá mức. |
| Không đọc được file | Sai vị trí file, quyền hệ điều hành hoặc `secure_file_priv` | Xác định file nằm ở client hay server và kiểm tra đúng quyền. |
| LOCAL bị từ chối | Client hoặc server không cho phép LOCAL | Kiểm tra `local_infile` và cấu hình client; chỉ bật khi phù hợp bảo mật. |
| Import báo duplicate key | File có khóa trùng với dữ liệu hiện tại | Chọn rõ chính sách lỗi, `IGNORE` hay `REPLACE`; không dùng mặc định tùy tiện. |
| Import hoàn tất nhưng thiếu hàng | `LOCAL`/`IGNORE` bỏ qua dòng lỗi hoặc trùng khóa | Đọc warnings, đối chiếu số dòng và nạp lại từ staging sau khi sửa. |

## 12. Quy trình chuẩn khi nhận một file CSV mới

1. Xác định delimiter, enclosure, escape, line terminator và charset từ hệ thống xuất file.
2. Kiểm tra file có header, BOM, trường chứa delimiter, quote hoặc newline bên trong hay không.
3. Xác định quy ước `NULL`: `\N`, chữ `NULL`, empty string hay một sentinel riêng.
4. Tạo bảng staging hoặc xác định rõ danh sách cột và chuyển đổi dữ liệu.
5. Chọn `LOAD DATA INFILE` nếu file nằm trên server và có quyền phù hợp; chọn LOCAL nếu file nằm trên client và chính sách cho phép.
6. Chạy thử với một bản sao nhỏ, kiểm tra kết quả và warnings.
7. Đối chiếu số dòng, khóa trùng, giá trị bắt buộc và kiểu dữ liệu.
8. Nạp dữ liệu hợp lệ vào bảng nghiệp vụ và lưu bản gốc cùng nhật ký import.

Với export, chỉ định rõ charset và `FIELDS`/`LINES`; bảo đảm nơi nhận dùng đúng dialect để đọc. Nếu cần tương thích tuyệt đối với một chuẩn CSV cụ thể hoặc nhiều ứng dụng bên ngoài, hãy kiểm tra bằng parser CSV của ứng dụng đích thay vì giả định mọi công cụ đều hiểu giống MySQL.

## 13. Bài tập tự kiểm tra

1. File được tạo trên Windows có CRLF. Nếu dùng `LINES TERMINATED BY '\n'`, hiện tượng nào có thể xảy ra ở trường cuối dòng?
2. Vì sao `LOAD DATA LOCAL INFILE` không cần quyền `FILE`, nhưng lại cần client và server cùng cho phép LOCAL?
3. Với `FIELDS ESCAPED BY '\\'`, chuỗi nào biểu diễn SQL `NULL`? Chuỗi nào biểu diễn empty string?
4. Khi có `FIELDS ENCLOSED BY '"'`, sự khác nhau giữa `NULL` và `"NULL"` là gì?
5. Vì sao `CHARACTER SET utf8mb4` trong `LOAD DATA` quan trọng hơn `SET NAMES utf8mb4` đối với byte của file?
6. Tại sao `LOAD DATA LOCAL` có thể bỏ qua một số dòng lỗi thay vì dừng ngay?
7. Khi file có thứ tự cột khác bảng, cần dùng phần nào của câu lệnh `LOAD DATA`?
8. Vì sao `SELECT ... INTO OUTFILE` không ghi file trực tiếp về máy client?

**Gợi ý đáp án:** (1) Ký tự CR có thể còn ở cuối trường cuối dòng. (2) Client đọc file và gửi nội dung qua kết nối; LOCAL phải được cho phép ở cả hai đầu. (3) `\N` là SQL `NULL`; trường rỗng là empty string đối với cột chuỗi. (4) `NULL` không được bao là SQL `NULL`, còn `"NULL"` là chuỗi literal. (5) `LOAD DATA` diễn giải byte file theo `CHARACTER SET`; `SET NAMES` không ảnh hưởng charset file. (6) LOCAL có hiệu lực như IGNORE khi không dùng REPLACE, nên lỗi chuyển đổi trở thành warnings và quá trình tiếp tục. (7) Danh sách cột và user variable theo đúng thứ tự trường trong file. (8) OUTFILE luôn tạo file trên filesystem của máy chủ; muốn ghi ở client cần dùng client command hoặc công cụ xuất dữ liệu khác.

## Tài liệu tham khảo

- [MySQL 8.4 Reference Manual: LOAD DATA Statement](https://dev.mysql.com/doc/refman/8.4/en/load-data.html)
- [MySQL 8.4 Reference Manual: SELECT ... INTO Statement](https://dev.mysql.com/doc/refman/8.4/en/select-into.html)
- [MySQL 8.4 Reference Manual: Security Considerations for LOAD DATA LOCAL](https://dev.mysql.com/doc/refman/8.4/en/load-data-local-security.html)
- [MySQL 8.4 Reference Manual: Character Sets and Collations](https://dev.mysql.com/doc/refman/8.4/en/charset.html)
- [MySQL 8.4 Reference Manual: Server System Variables (secure_file_priv, local_infile)](https://dev.mysql.com/doc/refman/8.4/en/server-system-variables.html)
