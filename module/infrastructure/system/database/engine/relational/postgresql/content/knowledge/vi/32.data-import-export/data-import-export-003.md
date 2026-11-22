# Header, dấu phân cách, ký tự escape và biểu diễn NULL trong PostgreSQL

Trong chương **Nhập xuất dữ liệu** của module **Database Engine Relational PostgreSQL**, bài này tập trung vào bốn yếu tố quyết định một file CSV/TEXT có được đọc và xuất đúng nghĩa hay không: **header**, **delimiter (dấu phân cách)**, **quote/escape**, và **biểu diễn SQL NULL**.

Giả sử có file CSV:

~~~csv
id,customer_name,note
1,"An, Nguyễn","Gọi trước 9:00"
2,Bình,
3,Chi,""
4,Dũng,"Dòng một
Dòng hai"
~~~

Nhìn qua, bốn hàng dữ liệu dường như đơn giản. Nhưng nếu người nhập file không phân biệt **dấu phẩy trong ô và dấu phẩy phân cột**, **ô trống không có dấu nháy và chuỗi rỗng có dấu nháy**, hoặc **xuống dòng bên trong trường có quote và kết thúc một record**, các giá trị có thể bị dịch cột, biến thành NULL hoặc nhập thất bại.

PostgreSQL hỗ trợ các định dạng `text`, `csv` và `binary` qua `COPY`. Trong đó `text` và `csv` có những quy tắc khác nhau cho cả bốn yếu tố nói trên. **Không thể đổi `FORMAT text` thành `FORMAT csv` rồi giữ nguyên cách diễn giải escape/NULL mà kỳ vọng file vẫn có nghĩa như cũ.**

## 1. Mục tiêu học tập

Sau bài, bạn có thể:

1. Phân biệt PostgreSQL `COPY`, psql `\copy` và cách truyền dữ liệu qua `STDIN`/`STDOUT`.
2. Chọn đúng `FORMAT csv` hoặc `FORMAT text` cho một nguồn dữ liệu.
3. Giải thích `HEADER true`, `HEADER false` và `HEADER MATCH`, cùng hạn chế kiểm tra thứ tự cột.
4. Đặt `DELIMITER` tương thích file CSV dùng dấu phẩy, dấu chấm phẩy hoặc ký tự khác.
5. Nhận biết delimiter phải là **một ký tự một byte**, không phải một chuỗi tùy ý.
6. Phân biệt `QUOTE` (dấu bao trường) với `ESCAPE` (ký tự escape quote/escape trong CSV).
7. Hiểu quy tắc CSV mặc định: quote `"`, escape `"`, nên một dấu quote trong dữ liệu được viết thành `""`.
8. Đọc đúng giá trị có dấu phân cách, dấu quote, dấu xuống dòng hoặc khoảng trắng.
9. Phân biệt SQL `NULL` với chuỗi rỗng `''`, chuỗi `'NULL'` và chuỗi `'\N'`.
10. Giải thích vì sao CSV mặc định **ô không được quote và trống → NULL**, còn `""` → chuỗi rỗng.
11. Dùng `NULL '...'` để chọn biểu diễn NULL rõ ràng.
12. Dùng `FORCE_NULL` và `FORCE_NOT_NULL` trong `COPY FROM CSV` khi cần đổi cách diễn giải NULL.
13. Dùng `FORCE_QUOTE` trong `COPY TO CSV` mà không làm mất phân biệt NULL.
14. Hiểu escape trong `FORMAT text` qua backslash sequences: `\t`, `\n`, `\r`, `\\`, `\N`.
15. Biết header không tự mapping tên cột sang thứ tự khác: `COPY` vẫn nhập theo **thứ tự**.
16. Nhận diện lỗi `missing data for column`, `extra data after last expected column` và lỗi convert data type.
17. Xử lý CSV nhiều dòng, Unicode tiếng Việt, BOM, CRLF/LF và client encoding.
18. Thiết kế pipeline import vào staging table với mapping/validation/khả năng chạy lại.
19. Kiểm thử round-trip xuất→nhập để chắc chắn không đánh đồng NULL với empty string.
20. Áp dụng checklist nhận file từ đối tác mà không đoán delimiter, encoding và schema.

## 2. COPY và \copy: dữ liệu đi qua đâu?

### 2.1. COPY là câu lệnh SQL của server

~~~sql
COPY schema_name.table_name
FROM '/absolute/server/path/data.csv'
WITH (FORMAT csv, HEADER true);
~~~

Nếu ghi đường dẫn file trực tiếp trong `COPY`, **PostgreSQL server** đọc/ghi file trên máy chạy server theo quyền của hệ điều hành và role có quyền phù hợp. Nó **không** mặc nhiên đọc file đang nằm trên máy tính chạy psql hoặc IDE của bạn.

### 2.2. \copy là lệnh riêng của psql client

~~~text
\copy schema_name.table_name FROM 'data.csv' WITH (FORMAT csv, HEADER true)
~~~

`\copy` là **psql meta-command**, không phải SQL gửi nguyên văn từ Java/JDBC. Với `\copy`, psql mở file **trên máy client**, rồi truyền nội dung qua kết nối database bằng cơ chế `COPY ... FROM STDIN` hoặc lấy dữ liệu từ `COPY ... TO STDOUT`.

### 2.3. COPY ... FROM STDIN / TO STDOUT

~~~sql
COPY schema_name.table_name
FROM STDIN
WITH (FORMAT csv, HEADER true);
~~~

`STDIN` nghĩa server nhận các bytes trong **COPY protocol stream** từ client; `STDOUT` đưa bytes trở lại client. Công cụ psql, driver PostgreSQL hoặc ứng dụng ETL có thể quản lý stream này theo cách riêng.

### 2.4. Không dùng COPY PROGRAM tùy tiện

`COPY ... PROGRAM 'shell command'` thực thi chương trình theo môi trường/quyền của **server**, có nguy cơ cao khi command được ghép từ input không đáng tin. Nó không phải công cụ cần thiết cho bài header/CSV/NULL; ưu tiên `\copy` client-side hoặc API streaming với quyền tối thiểu.

### 2.5. Quyền thực thi

| Cách gọi | File nằm ở đâu? | Điểm quyền quan trọng |
| --- | --- | --- |
| `COPY ... FROM 'file'` | Phía database server | Quyền đọc file server và INSERT vào bảng |
| `COPY ... TO 'file'` | Phía database server | Quyền ghi file server và SELECT dữ liệu |
| `\copy ... FROM 'file'` | Phía psql client | Client đọc file, role DB có INSERT |
| `\copy ... TO 'file'` | Phía psql client | Client ghi file, role DB có SELECT |
| `COPY ... FROM STDIN` | Client truyền stream | Quyền INSERT, driver hỗ trợ protocol |
| `COPY ... TO STDOUT` | Server gửi stream | Quyền SELECT, driver hỗ trợ protocol |

Việc đọc/ghi server files có thể yêu cầu superuser hoặc các roles chuyên biệt như `pg_read_server_files`, `pg_write_server_files`. **Không cấp những roles rộng này chỉ để nhập một CSV từ laptop**.

## 3. Ba định dạng COPY và bốn yếu tố bài học

### 3.1. Bảng đối chiếu

| Thuộc tính | `FORMAT text` | `FORMAT csv` | `FORMAT binary` |
| --- | --- | --- | --- |
| Mặc định của COPY | **Có** | Không | Không |
| Dấu phân cách mặc định | Tab | Dấu phẩy `,` | Cấu trúc byte nhị phân |
| NULL mặc định | `\N` | Field trống **không quote** | Marker nhị phân |
| Quote/escape | Backslash escape theo COPY text | CSV QUOTE và ESCAPE | Không áp dụng |
| `HEADER` | Có ở PostgreSQL hiện đại, tùy cú pháp/version | Có | Không |
| `DELIMITER` | Có | Có | Không |
| `NULL '...'` | Có | Có | Không |
| `QUOTE`/`ESCAPE` | Không | Có | Không |
| Xem bằng text editor | Có, cần hiểu tab/backslash | Có, cần parser CSV | Không phù hợp |
| Tính tương thích giữa hệ thống | Theo quy ước PostgreSQL COPY text | Tốt khi đồng ý rõ dialect | Phụ thuộc kiểu/version/kiến trúc |

`FORMAT text` là **mặc định** nếu không ghi `FORMAT`. File thông thường được gọi “CSV” nhưng chạy `COPY FROM ...` không có `FORMAT csv` sẽ bị PostgreSQL diễn giải theo **TEXT**, dễ gây sai delimiter và NULL.

### 3.2. Cú pháp tổng quát cho CSV

~~~sql
COPY schema_name.table_name (col_a, col_b, col_c)
FROM STDIN
WITH (
    FORMAT csv,
    HEADER true,
    DELIMITER ',',
    QUOTE '"',
    ESCAPE '"',
    NULL ''
);
~~~

Các option trên mô tả **format contract**. Bạn không bắt buộc phải ghi các mặc định, nhưng với pipeline lâu dài, khai báo tường minh giúp người đọc biết chính xác file được diễn giải thế nào.

### 3.3. Cú pháp tổng quát cho TEXT

~~~sql
COPY schema_name.table_name (col_a, col_b, col_c)
FROM STDIN
WITH (
    FORMAT text,
    DELIMITER E'\t',
    NULL E'\\N'
);
~~~

`E'\t'` là một **SQL escape string** có ký tự tab. `E'\\N'` đại diện cho hai ký tự **backslash + N** trong SQL. Đây là phần xử lý **SQL string literal của lệnh COPY**, khác với việc `FORMAT text` sau đó diễn giải backslash trong **file data**.

### 3.4. Cột dữ liệu không nhất thiết trùng tên header

~~~sql
COPY my_table (customer_id, customer_name)
FROM STDIN
WITH (FORMAT csv, HEADER true);
~~~

`COPY FROM` ánh xạ **field số 1 → customer_id**, **field số 2 → customer_name**, không tự dò header names để quyết định cột. `HEADER true` chỉ bỏ qua hàng header trên input. Muốn kiểm tra tên/thứ tự header, dùng `HEADER MATCH` khi version hỗ trợ.

## 4. Bộ dữ liệu lab có thể chạy lại trong schema riêng

Chỉ thực hành trên database được phép tạo schema và nhập dữ liệu thử. Không dùng `TRUNCATE`, `DROP SCHEMA CASCADE` hoặc `COPY FROM` vào bảng production để thử delimiter.

### 4.1. Tạo schema

~~~sql
CREATE SCHEMA copy411;
~~~

Nếu schema `copy411` đã tồn tại từ lần thực hành trước, hãy dùng database lab mới hoặc tự đặt tên khác sau khi xác nhận dữ liệu có thể xử lý. Các examples bên dưới giả định schema được tạo mới.

### 4.2. Bảng khách hàng

~~~sql
CREATE TABLE copy411.contacts (
    contact_id integer PRIMARY KEY,
    full_name text NOT NULL,
    nickname text,
    note text,
    active boolean NOT NULL DEFAULT true,
    created_at date
);
~~~

`nickname` và `note` cho phép NULL để chúng ta phân biệt **NULL** với **chuỗi rỗng**. `full_name` không được NULL, còn `contact_id` là khóa chính để kiểm chứng thứ tự cột không bị lệch.

### 4.3. Thêm dữ liệu đa dạng

~~~sql
INSERT INTO copy411.contacts (
    contact_id, full_name, nickname, note, active, created_at
)
VALUES
    (1, 'An, Nguyễn', NULL, 'Có dấu phẩy, trong tên', true, DATE '2026-01-03'),
    (2, 'Bình "Bé"', '', 'Chuỗi rỗng khác NULL', false, DATE '2026-02-14'),
    (3, 'Chi', 'C', E'Dòng 1\nDòng 2', true, NULL),
    (4, 'Dũng', 'NULL', E'C:\\data\\report.csv', true, DATE '2026-03-20'),
    (5, 'Em', E'\\N', NULL, true, DATE '2026-04-01');
~~~

Các dòng dùng `E'...'` để biểu diễn backslash/newline một cách rõ ràng trong **SQL**, không phải một đoạn dữ liệu CSV. `E'Dòng 1\nDòng 2'` chứa newline thật; `E'C:\\data\\report.csv'` chứa các dấu backslash thật; `E'\\N'` tạo chuỗi literal `\N`.

### 4.4. Kiểm chứng NULL và chuỗi rỗng

~~~sql
SELECT
    contact_id,
    nickname,
    nickname IS NULL AS nickname_is_null,
    nickname = '' AS nickname_is_empty,
    length(nickname) AS nickname_length
FROM copy411.contacts
ORDER BY contact_id;
~~~

Với `contact_id=1`, `nickname IS NULL` là true. Với `contact_id=2`, `nickname = ''` là true. Với `contact_id=4`, nickname là chuỗi bốn ký tự `NULL`; với `contact_id=5`, nickname là **backslash và chữ N**, không phải SQL NULL.

### 4.5. Vì sao phải có dữ liệu “khó”?

Một bộ test chỉ gồm `1,An,A` không thể kiểm chứng quote, escape, NULL, newline hay Unicode. **Round-trip tốt phải có giá trị chứa delimiter, quote, backslash, newline, NULL, empty string, literal marker và tiếng Việt có dấu.**

## 5. HEADER: tiêu đề cột có những nhiệm vụ gì?

Một file CSV có header:

~~~csv
contact_id,full_name,nickname
1,An,
2,Bình,""
~~~

Hàng đầu `contact_id,full_name,nickname` là tên trường, không phải dữ liệu. Nếu PostgreSQL không được yêu cầu bỏ qua header, nó sẽ cố nhập chuỗi `contact_id` vào cột integer `contact_id` và phát sinh lỗi convert kiểu.

### 5.1. HEADER true

~~~sql
COPY copy411.contacts (
    contact_id, full_name, nickname
)
FROM STDIN
WITH (FORMAT csv, HEADER true);
~~~

Với `HEADER true`, PostgreSQL **bỏ qua** dòng header đầu tiên. Không được hiểu điều đó là server tự thay đổi mapping cột dựa trên nội dung header.

### 5.2. HEADER false

~~~sql
COPY copy411.contacts (
    contact_id, full_name, nickname
)
FROM STDIN
WITH (FORMAT csv, HEADER false);
~~~

Nếu file **không có header**, để `HEADER false` (mặc định). Nếu để `HEADER true` nhầm trên file không có header, PostgreSQL sẽ **bỏ dữ liệu dòng đầu** như thể đó là tiêu đề, có thể gây thiếu một record mà không báo lỗi.

### 5.3. HEADER MATCH

~~~sql
COPY copy411.contacts (
    contact_id, full_name, nickname
)
FROM STDIN
WITH (FORMAT csv, HEADER MATCH);
~~~

Với `HEADER MATCH`, PostgreSQL yêu cầu **số lượng và tên cột header trùng với danh sách cột thực tế theo đúng thứ tự**. Nếu không khớp, COPY báo lỗi. Đây là một lớp kiểm tra format hữu ích hơn việc chỉ bỏ dòng đầu.

### 5.4. HEADER MATCH không tự đảo cột

File:

~~~csv
full_name,contact_id,nickname
An,1,
~~~

trong khi `COPY (contact_id, full_name, nickname)` yêu cầu contact_id trước, full_name sau:

- `HEADER true`: bỏ qua header, rồi nhập `An` vào integer `contact_id` → lỗi; trong trường hợp kiểu tương thích, dữ liệu có thể **bị tráo cột âm thầm**.
- `HEADER MATCH`: phát hiện header sai tên/thứ tự và báo lỗi sớm.
- **Không có chế độ mặc định tự map header “full_name” sang cột tương ứng**, bất kể nó nằm ở vị trí thứ mấy.

### 5.5. HEADER MATCH chỉ dùng ở chiều import

`HEADER MATCH` là tùy chọn cho `COPY FROM`. Khi export với `COPY TO`, dùng `HEADER true` nếu muốn phát ra dòng tên cột, không dùng MATCH.

### 5.6. HEADER trên TEXT và CSV

PostgreSQL hiện hành cho phép `HEADER` trên những định dạng text-based (`text` và `csv`) theo cú pháp tài liệu `COPY`. Trên hệ thống dùng **major version cũ**, cần đối chiếu đúng tài liệu/driver trước khi áp dụng các giá trị như `MATCH`. **`HEADER` không được hỗ trợ cho `FORMAT binary`**.

### 5.7. Header của COPY(query) TO

~~~sql
COPY (
    SELECT
        contact_id AS id,
        full_name AS display_name
    FROM copy411.contacts
    ORDER BY contact_id
)
TO STDOUT
WITH (FORMAT csv, HEADER true);
~~~

Header được tạo theo **tên cột output của query** (ở đây `id,display_name`), không nhất thiết theo tên vật lý của bảng gốc. Nếu sau đó import vào `COPY (contact_id, full_name) ... HEADER MATCH`, cần hiểu tên header đã được alias nên có thể **không khớp**.

### 5.8. Header không phải schema migration

Khi đối tác đổi thêm/bớt/đảo cột trong file, không chỉ sửa `HEADER true`. Hãy:

1. So sánh schema file với contract;
2. Chọn đúng column list hoặc staging mapping;
3. Dùng `HEADER MATCH` khi phù hợp;
4. Kiểm thử dữ liệu mẫu với kiểu, NULL và encoding;
5. Chốt version contract để lần nhập sau không đổi nghĩa.

## 6. DELIMITER: ký tự phân cách cột

PostgreSQL `COPY` hỗ trợ:

~~~sql
DELIMITER ','
DELIMITER ';'
DELIMITER '|'
DELIMITER E'\t'
~~~

`FORMAT csv` mặc định **dấu phẩy**. `FORMAT text` mặc định **tab**. `DELIMITER` phải là **một ký tự có độ dài một byte theo encoding liên quan**, không phải một chuỗi như `'||'` hoặc ký tự đa byte trong UTF-8.

### 6.1. CSV dùng dấu phẩy

~~~csv
contact_id,full_name,nickname
1,An,
2,Bình,""
~~~

~~~sql
COPY copy411.contacts(contact_id, full_name, nickname)
FROM STDIN WITH (FORMAT csv, HEADER true, DELIMITER ',');
~~~

### 6.2. CSV dùng dấu chấm phẩy

~~~csv
contact_id;full_name;nickname
1;An;
2;"Bình; Bé";""
~~~

~~~sql
COPY copy411.contacts(contact_id, full_name, nickname)
FROM STDIN WITH (FORMAT csv, HEADER true, DELIMITER ';');
~~~

Một hệ thống bảng tính có thể xuất CSV dùng `;` tùy locale. **CSV không phải luôn dùng dấu phẩy**, dù tên gọi chứa “comma-separated”. Phải kiểm tra file thật và contract của hệ thống tạo file.

### 6.3. Dấu phân cách nằm trong giá trị

Với `DELIMITER ','`:

~~~csv
1,"An, Nguyễn"
~~~

đúng là hai fields: `1` và `An, Nguyễn`. Dòng:

~~~csv
1,An, Nguyễn
~~~

có **ba fields**, không phải hai. Khi bảng chờ hai cột, `COPY FROM` có thể báo `extra data after last expected column`.

### 6.4. Delimiter không được đồng nhất với quote/escape

Trong CSV, delimiter, quote và escape có vai trò khác nhau; cấu hình phải thỏa các giới hạn được `COPY` hỗ trợ. Đừng chọn delimiter trùng quote/escape hoặc ký tự xuống dòng. Thông thường nên giữ cặp quote/escape mặc định và chọn delimiter theo file nguồn.

### 6.5. Dấu pipe không tự tránh nhu cầu quoting

~~~csv
id|name|note
1|"An|Bình"|"Có dấu | trong ghi chú"
~~~

Với `DELIMITER '|'`, những dữ liệu chứa `|` vẫn phải được quote đúng. Thay dấu phẩy bằng pipe **không** có nghĩa được bỏ hẳn quote/escape.

### 6.6. Dấu tab là ký tự thật

Với `DELIMITER E'\t'`, PostgreSQL mong **tab byte/character thực**, không phải hai ký tự `\` và `t` trong file. Khi xem bằng text editor, tab có thể hiển thị như nhiều khoảng trắng; không thay bằng spaces tùy tiện.

### 6.7. Tránh tự suy delimiter theo một dòng

Nếu field chứa dấu phẩy trong quote, đếm dấu phẩy thủ công sẽ sai số cột. Hãy dùng **parser CSV thực sự** hoặc kiểm tra bằng `COPY`/staging, không đoán rằng ký tự xuất hiện nhiều nhất trong file nhất định là delimiter.

## 7. QUOTE và ESCAPE trong FORMAT CSV

Với `FORMAT csv`, mặc định:

~~~sql
QUOTE '"',
ESCAPE '"'
~~~

`QUOTE` là ký tự bao một trường; `ESCAPE` là ký tự đặt trước quote/escape characters bên trong giá trị. Khi `QUOTE` và `ESCAPE` đều là dấu nháy kép, cách viết literal quote trong field thường là **hai dấu nháy kép liên tiếp**.

### 7.1. Dấu phẩy trong field

~~~csv
id,name
1,"An, Nguyễn"
~~~

Giá trị `name` là `An, Nguyễn`, không bị tách thành hai cột.

### 7.2. Dấu nháy kép trong field

Giá trị gốc:

~~~text
Bình "Bé"
~~~

CSV biểu diễn:

~~~csv
2,"Bình ""Bé"""
~~~

Parser hiểu `""` bên trong vùng quote là **một dấu quote thật**. Dấu quote ở đầu/cuối chỉ bao trường, không trở thành một phần của chuỗi.

### 7.3. Cùng có dấu phẩy và quote

Giá trị:

~~~text
Nguyễn "An, Bé"
~~~

CSV:

~~~csv
3,"Nguyễn ""An, Bé"""
~~~

Hai dấu quote bên trong là escape cho một ký tự quote của dữ liệu; dấu phẩy bên trong vùng quote **không phân cột**.

### 7.4. QUOTE khác ESCAPE

~~~sql
WITH (
    FORMAT csv,
    DELIMITER ',',
    QUOTE '"',
    ESCAPE '"'
)
~~~

Đây là cặp mặc định. PostgreSQL có thể dùng một escape character khác do người tạo file thống nhất, ví dụ `ESCAPE E'\\'`, nhưng **không nên đổi tùy tiện**: một CSV thông thường dùng double quote doubling; nếu bạn cấu hình khác file nguồn, parser sẽ diễn giải khác.

### 7.5. QUOTE/ESCAPE chỉ dành cho CSV

Không đặt `QUOTE '"'` hay `ESCAPE '"'` trong `FORMAT text`. TEXT dùng **backslash escaping** theo quy tắc riêng. Với binary, các option kiểu CSV không có ý nghĩa.

### 7.6. Field có xuống dòng thật

~~~csv
id,note
1,"Dòng một
Dòng hai"
~~~

Đây có thể là **một record CSV** gồm hai fields, dù nó chiếm **ba dòng vật lý** tính cả header. Parser CSV biết rằng newline bên trong vùng quote là nội dung trường, không tự kết thúc record.

Không đọc file CSV bằng `split('\n')` rồi `split(',')` nếu nguồn cho phép quoted newlines.

### 7.7. Có nên FORCE_QUOTE mọi thứ?

`FORCE_QUOTE` ở `COPY TO CSV` buộc các giá trị **không NULL** được quote, giúp dễ đọc một số file và hạn chế sự mơ hồ với string có ký tự đặc biệt. Nhưng **NULL vẫn không được quote**, vì PostgreSQL phải giữ khả năng biểu diễn NULL tách khỏi chuỗi trùng marker.

~~~sql
COPY copy411.contacts
TO STDOUT
WITH (FORMAT csv, HEADER true, FORCE_QUOTE *);
~~~

### 7.8. Quote không phải escape của SQL

Trong:

~~~sql
QUOTE '"'
~~~

SQL literal `'"'` chứa ký tự double quote. Trong CSV data:

~~~csv
"Bình ""Bé"""
~~~

các ký tự quote là **cú pháp của file CSV**. Đừng nhầm SQL string escaping với escaping của CSV content.

## 8. SQL NULL và chuỗi rỗng: khác nhau về dữ liệu

PostgreSQL phân biệt:

| Giá trị trong database | Ý nghĩa |
| --- | --- |
| `NULL` | Không có giá trị SQL, trạng thái unknown/missing |
| `''::text` | Chuỗi có độ dài 0, **không phải NULL** |
| `'NULL'::text` | Chuỗi bốn ký tự N-U-L-L |
| `E'\\N'::text` | Chuỗi hai ký tự backslash và N |
| `' '::text` | Chuỗi chứa một dấu cách |
| `'""'::text` | Chuỗi chứa hai dấu nháy kép thật |

### 8.1. Kiểm tra trực tiếp

~~~sql
SELECT
    NULL::text IS NULL AS sql_null,
    ''::text IS NULL AS empty_is_null,
    length(''::text) AS empty_length,
    length('NULL'::text) AS marker_word_length,
    length(E'\\N'::text) AS backslash_n_length,
    length(' '::text) AS one_space_length;
~~~

Kỳ vọng: `sql_null=true`, `empty_is_null=false`, `empty_length=0`, `marker_word_length=4`, `backslash_n_length=2`, `one_space_length=1`.

### 8.2. SQL NULL không phải literal 'NULL'

~~~sql
SELECT
    NULL::text = ''::text AS null_equals_empty,
    NULL::text = 'NULL'::text AS null_equals_word,
    NULL::text IS DISTINCT FROM ''::text AS null_distinct_from_empty;
~~~

Hai phép `=` với NULL trả kết quả SQL NULL (unknown), không phải true. `IS DISTINCT FROM` có semantics xác định để so sánh cả với NULL; dùng nó khi kiểm tra round-trip hoặc phát hiện thay đổi có nullable values.

### 8.3. Độ dài 0 không là thiếu field

CSV:

~~~csv
1,An,""
~~~

có **ba fields**, trong đó field thứ ba là **chuỗi rỗng được quote**, không phải field biến mất. Nếu input chỉ:

~~~csv
1,An
~~~

thì nó **thiếu field thứ ba** đối với `COPY` chờ ba cột và sẽ báo lỗi cấu trúc.

### 8.4. Dấu cách không bị trim tự động

~~~csv
1,"  An  "," "
~~~

Những spaces bên trong giá trị có ý nghĩa; `'  An  '` khác `'An'`. PostgreSQL CSV không tự trim nội dung chỉ vì người xem thấy khoảng trắng “dư”. Nếu nghiệp vụ cần trim, xử lý ở staging/transform với quy tắc công khai.

## 9. Biểu diễn NULL mặc định trong FORMAT CSV

**Quy tắc cần nhớ nhất của CSV PostgreSQL:** với mặc định `NULL ''`:

- **Field trống không quote** → SQL `NULL`.
- **Field trống có quote** `""` → chuỗi rỗng `''`.

### 9.1. Bảng ví dụ

Giả sử cột đang nhập có kiểu `text`:

| Nội dung field trong CSV | PostgreSQL đọc thành |
| --- | --- |
| *(trống, không quote)* | SQL NULL |
| `""` | Chuỗi rỗng `''` |
| `" "` | Chuỗi một dấu cách |
| `NULL` | Chuỗi `'NULL'` |
| `"NULL"` | Chuỗi `'NULL'` |
| `\N` | Chuỗi `E'\\N'` |
| `"\N"` | Chuỗi `E'\\N'` |
| `"An, Nguyễn"` | Chuỗi `'An, Nguyễn'` |

Đây là **CSV mặc định**; bảng sẽ thay đổi nếu chỉ định `NULL 'NULL'`, `FORCE_NULL` hoặc `FORCE_NOT_NULL`.

### 9.2. CSV tối giản từ STDIN trong psql

~~~sql
CREATE TABLE copy411.null_demo (
    id integer PRIMARY KEY,
    val text
);

COPY copy411.null_demo (id, val)
FROM STDIN
WITH (FORMAT csv, HEADER true);
id,val
1,
2,""
3,NULL
4,"NULL"
5," "
6,\N
\.
~~~

Đây là **script đặc thù cho psql khi nhập inline data bằng COPY FROM STDIN**. Các dòng `id,val` đến `\.` là **CSV payload**, không phải câu SQL; `\.` kết thúc input stream trong psql.

Nếu chạy qua GUI/JDBC không hỗ trợ inline COPY data theo cách này, dùng `\copy` của psql với file hoặc streaming API của driver. Không dán khối dữ liệu vào một SQL editor bất kỳ rồi kỳ vọng nó là SQL bình thường.

### 9.3. Đọc kết quả

~~~sql
SELECT
    id,
    val,
    val IS NULL AS is_null,
    length(val) AS char_count
FROM copy411.null_demo
ORDER BY id;
~~~

| id | is_null | `val` về ngữ nghĩa |
| --- | --- | --- |
| 1 | true | SQL NULL |
| 2 | false | Chuỗi rỗng |
| 3 | false | Chuỗi `NULL` |
| 4 | false | Chuỗi `NULL` |
| 5 | false | Một dấu cách |
| 6 | false | Chuỗi `\N` |

Với CSV mặc định, chuỗi `\N` **không phải NULL marker**. Đây là khác biệt lớn so với COPY TEXT mặc định.

### 9.4. Khi xuất CSV, PostgreSQL giữ khác biệt

Nếu cột `val` là SQL NULL, `COPY TO CSV` xuất **field không quote và trống**. Nếu `val` là chuỗi rỗng, nó xuất `""` để người nhập có thể phân biệt.

~~~sql
COPY (
    SELECT id, val
    FROM copy411.null_demo
    ORDER BY id
)
TO STDOUT
WITH (FORMAT csv, HEADER true);
~~~

Khi round-trip với cùng format/NULL options, PostgreSQL có đủ thông tin để giữ khác biệt giữa NULL và empty string.

### 9.5. Vì sao “mọi ô rỗng là NULL” rất nguy hiểm?

Trong form, người dùng có thể chủ ý **xóa nội dung text thành chuỗi rỗng**; trong nghiệp vụ khác, SQL NULL nghĩa “chưa biết” hoặc “không áp dụng”. Nếu import tự đổi `""` thành NULL, các query như:

~~~sql
WHERE val IS NULL
WHERE val = ''
~~~

sẽ cho kết quả khác, ảnh hưởng validation, unique constraints, reporting, business logic và JSON output.

## 10. NULL '...': chọn null marker riêng

PostgreSQL cho phép:

~~~sql
NULL 'NULL'
NULL '\N'
NULL 'N/A'
NULL ''
~~~

`NULL` trong danh sách `COPY` là **option chọn chuỗi trong file đại diện cho SQL NULL**, không phải cú pháp SQL `IS NULL`.

### 10.1. CSV dùng NULL 'NULL'

~~~sql
COPY copy411.null_demo(id, val)
FROM STDIN
WITH (
    FORMAT csv,
    HEADER true,
    NULL 'NULL'
);
id,val
11,NULL
12,"NULL"
13,
14,""
\.
~~~

Vì NULL marker giờ là `NULL`:

| id | Field trong file | Kết quả |
| --- | --- | --- |
| 11 | `NULL` không quote | SQL NULL |
| 12 | `"NULL"` có quote | Chuỗi `'NULL'` |
| 13 | trống không quote | Chuỗi rỗng (vì không khớp marker `NULL`) |
| 14 | `""` có quote | Chuỗi rỗng |

**Đặt NULL 'NULL' làm thay đổi semantics của field trống**. Không thể đổi marker mà không điều chỉnh hợp đồng của file.

### 10.2. CSV chứa literal NULL marker

Nếu giá trị dữ liệu thật sự là chuỗi `NULL`, PostgreSQL `COPY TO CSV WITH (NULL 'NULL')` sẽ **quote nó** thành `"NULL"` để không nhầm với SQL NULL không quote.

### 10.3. Cần tránh marker xuất hiện tự nhiên

Chọn `NULL 'N/A'` có thể dễ đọc nhưng dữ liệu thật cũng có thể chứa text `N/A`. Trong CSV, quoting đúng giúp phân biệt. Trong TEXT, cần escaping đúng. Với các hệ thống bên ngoài không tuân thủ quoting, một marker “thân thiện” có thể gây mất mát nghĩa nếu cùng xuất hiện như dữ liệu thật.

### 10.4. Không khuyên tự thay NULL thành chuỗi trước export

~~~sql
-- Có nguy cơ nhập lại sai nghĩa nếu N/A là dữ liệu thật:
SELECT COALESCE(nickname, 'N/A') FROM copy411.contacts;
~~~

Đây là **biến đổi dữ liệu**, không chỉ thay cách serialize. Nếu muốn giữ SQL NULL, ưu tiên `COPY ... NULL 'N/A'` và bảo đảm parser tương thích, hoặc ghi rõ schema hợp đồng.

### 10.5. Cùng options khi nhập và xuất

~~~sql
COPY copy411.contacts
TO STDOUT
WITH (
    FORMAT csv,
    HEADER true,
    NULL 'NULL'
);
~~~

Khi nhập lại cần dùng `NULL 'NULL'`, cùng DELIMITER/QUOTE/ESCAPE và thứ tự cột. Dùng khác marker có thể biến các SQL NULL thành chuỗi text hoặc ngược lại.

## 11. FORCE_NOT_NULL: bảo toàn field trống thành chuỗi rỗng

`FORCE_NOT_NULL` là tùy chọn **chỉ dùng cho `COPY FROM` với `FORMAT csv`**. Nó ngăn PostgreSQL so sánh giá trị ở cột được chọn với NULL marker.

### 11.1. Với CSV mặc định

~~~sql
CREATE TABLE copy411.force_not_null_demo (
    id integer PRIMARY KEY,
    note text
);

COPY copy411.force_not_null_demo (id, note)
FROM STDIN
WITH (
    FORMAT csv,
    HEADER true,
    FORCE_NOT_NULL (note)
);
id,note
1,
2,""
3,NULL
\.
~~~

Vì `note` không được so sánh với marker trống mặc định:

- id 1: chuỗi rỗng, **không NULL**;
- id 2: chuỗi rỗng, **không NULL**;
- id 3: chuỗi `NULL` như text thông thường.

### 11.2. Khi nào có ích?

Một nguồn CSV có quy ước field trống **luôn** là chuỗi rỗng hoặc empty string có nghĩa riêng, không phải unknown. `FORCE_NOT_NULL (note)` có thể phản ánh đúng quy ước ấy.

### 11.3. Không áp dụng bừa cho cột số/ngày

Nếu field trống được FORCE_NOT_NULL vào cột `integer` hoặc `date`, PostgreSQL sẽ thử parse chuỗi rỗng như số/ngày và có thể báo `invalid input syntax`. `FORCE_NOT_NULL` **không biến chuỗi rỗng thành giá trị mặc định 0 hoặc ngày trống**.

### 11.4. Có thể áp dụng nhiều cột hoặc *

~~~sql
FORCE_NOT_NULL (note, nickname)
FORCE_NOT_NULL *
~~~

Chỉ dùng `*` khi mọi cột có quy ước phù hợp. Tránh dùng trên các cột numeric/boolean/date không cho phép chuỗi rỗng.

### 11.5. FORCE_NOT_NULL khác NOT NULL constraint

`FORCE_NOT_NULL` là **cách giải mã CSV**, không phải constraint SQL. Nó có thể tạo text empty string, còn `NOT NULL` constraint chỉ cấm SQL NULL. Muốn cấm chuỗi rỗng, dùng thêm CHECK/validation theo nghiệp vụ.

## 12. FORCE_NULL: coi cả quoted marker là SQL NULL

`FORCE_NULL` cũng chỉ dùng trong `COPY FROM CSV`. Nó làm PostgreSQL so sánh **cả giá trị được quote** với NULL marker và chuyển thành SQL NULL khi khớp.

### 12.1. Mẫu với NULL 'NULL'

~~~sql
CREATE TABLE copy411.force_null_demo (
    id integer PRIMARY KEY,
    note text
);

COPY copy411.force_null_demo (id, note)
FROM STDIN
WITH (
    FORMAT csv,
    HEADER true,
    NULL 'NULL',
    FORCE_NULL (note)
);
id,note
1,NULL
2,"NULL"
3,
4,""
\.
~~~

Kỳ vọng:

- id 1: `NULL` không quote → SQL NULL;
- id 2: `"NULL"` có quote → SQL NULL **vì FORCE_NULL**;
- id 3: trống không quote → chuỗi rỗng;
- id 4: `""` → chuỗi rỗng.

Không nên dùng `FORCE_NULL` trên một cột có thể chứa **giá trị text thật đúng bằng marker**, nếu cần giữ dữ liệu ấy.

### 12.2. Với marker mặc định là chuỗi trống

Nếu `NULL ''`, `FORCE_NULL (note)` làm cả:

~~~csv
,
,""
~~~

ở field `note` được giải mã thành SQL NULL khi trường được chọn và quote-status khớp option. Khi đó **không còn phân biệt SQL NULL và chuỗi rỗng** ở những field này theo input đã nhận.

### 12.3. Không dùng FORCE_NULL như trim/normalization

`FORCE_NULL` chỉ so khớp **chuỗi marker** theo quy tắc CSV. Nó không tự trim spaces, xóa dấu tiếng Việt, đổi text `'null'` sang `'NULL'`, hay coi mọi chuỗi `'N/A'` là NULL nếu marker không phải N/A.

### 12.4. Cần dùng cột chỉ định

Nếu yêu cầu chỉ liên quan tới `note`, dùng `FORCE_NULL(note)`, không thay đổi semantics của toàn bộ file bằng `FORCE_NULL *`.

## 13. Kết hợp FORCE_NULL và FORCE_NOT_NULL

PostgreSQL cho phép dùng hai option **trên cùng một cột**; khi đó:

- NULL marker **được quote** → SQL NULL (do `FORCE_NULL`);
- NULL marker **không quote** → giá trị text thường (do `FORCE_NOT_NULL`).

### 13.1. Lab đảo quy ước quote

~~~sql
CREATE TABLE copy411.force_both_demo (
    id integer PRIMARY KEY,
    note text
);

COPY copy411.force_both_demo (id, note)
FROM STDIN
WITH (
    FORMAT csv,
    HEADER true,
    NULL 'NULL',
    FORCE_NULL (note),
    FORCE_NOT_NULL (note)
);
id,note
1,NULL
2,"NULL"
3,
4,""
\.
~~~

Kỳ vọng:

| id | Field | Giá trị trong DB |
| --- | --- | --- |
| 1 | `NULL` không quote | Text `'NULL'` |
| 2 | `"NULL"` có quote | SQL NULL |
| 3 | Trống không quote | Text `''` |
| 4 | `""` có quote | Text `''` |

### 13.2. Khi nào cần hai option cùng lúc?

Đây là trường hợp đặc biệt nếu file nguồn có quy ước “**quoted sentinel means NULL**” ngược với CSV PostgreSQL mặc định. Đối với pipeline thông thường, nên chuẩn hóa nguồn về quy tắc rõ, tránh tổ hợp khó hiểu nếu không cần.

### 13.3. Lưu ý tính nhất quán round-trip

Nếu nhập với cả `FORCE_NULL` và `FORCE_NOT_NULL`, nhưng xuất bằng quy tắc COPY CSV thông thường, file xuất **có thể có cách quote khác** file gốc dù dữ liệu bên trong đúng. Với các hệ thống đòi byte-for-byte preservation, cần lưu raw file hoặc canonical serialization riêng.

## 14. FORCE_QUOTE: khi xuất CSV

`FORCE_QUOTE` chỉ dùng trong **`COPY TO` với `FORMAT csv`**, tác động lên những **giá trị không NULL** của các cột được chỉ định.

### 14.1. Ví dụ

~~~sql
COPY (
    SELECT contact_id, full_name, nickname
    FROM copy411.contacts
    ORDER BY contact_id
)
TO STDOUT
WITH (
    FORMAT csv,
    HEADER true,
    FORCE_QUOTE *
);
~~~

Với `FORCE_QUOTE *`, các giá trị non-NULL thường được bao bởi `"..."`, kể cả khi chúng không chứa delimiter/quote/newline. Nhưng **SQL NULL vẫn phải được xuất không quote** theo NULL marker để giữ đúng nghĩa.

### 14.2. Chọn một số cột

~~~sql
COPY copy411.contacts (
    contact_id, full_name, nickname
)
TO STDOUT
WITH (
    FORMAT csv,
    HEADER true,
    FORCE_QUOTE (full_name, nickname)
);
~~~

### 14.3. FORCE_QUOTE không phải mã hóa hay bảo vệ dữ liệu

Quoting giúp parser nhận diện field boundaries. Nó **không** mã hóa dữ liệu nhạy cảm, không chống một ứng dụng bảng tính tự thực thi công thức và không tự bảo vệ khỏi SQL injection.

### 14.4. Khi xuất text như CSV để mở Excel

Excel hoặc chương trình bảng tính có thể tự suy kiểu, bỏ leading zeros của mã hàng, chuyển ngày theo locale hoặc diễn giải field bắt đầu bằng `=` như công thức. `FORCE_QUOTE` không bảo đảm chương trình bảng tính luôn xử lý field như text an toàn. Cần cân nhắc chính sách xuất cho spreadsheet users, import-as-text và biện pháp chống CSV formula injection theo threat model.

## 15. Ma trận tổng hợp cách giải mã NULL trong CSV

Giả sử kiểu cột là `text`:

| CSV field | `NULL ''` mặc định | `NULL 'NULL'` | `NULL 'NULL', FORCE_NULL` | `NULL 'NULL', FORCE_NOT_NULL` | Kết hợp cả hai |
| --- | --- | --- | --- | --- | --- |
| Trống không quote | SQL NULL | `''` | `''` | `''` | `''` |
| `""` | `''` | `''` | `''` | `''` | `''` |
| `NULL` không quote | `'NULL'` | SQL NULL | SQL NULL | `'NULL'` | `'NULL'` |
| `"NULL"` có quote | `'NULL'` | `'NULL'` | SQL NULL | `'NULL'` | SQL NULL |

*Giả định `FORCE_NULL`/`FORCE_NOT_NULL` được áp dụng cho chính cột đang xét. Nếu chỉ định cột khác, hành vi của cột này không đổi.*

### 15.1. Đây là bước thiết kế, không phải việc tùy hứng sau lỗi

Chọn NULL marker và FORCE options trước khi import dựa trên **data contract**. Nếu bạn tùy đổi marker sau mỗi lần lỗi, dữ liệu cùng loại có thể có cách giải mã không nhất quán giữa các batches.

### 15.2. Phân biệt NULL và DEFAULT

SQL NULL **khác** default của cột. Nếu file cung cấp NULL marker cho cột có default, PostgreSQL thường nhập SQL NULL (rồi áp constraints), **không** tự thay bằng default.

Nếu cột **không nằm trong column list** của `COPY FROM`, PostgreSQL có thể áp default của cột cho các rows được nhập. Các phiên bản mới còn có `DEFAULT '...'` option để nhận marker riêng cho default khi import, nhưng đó là cơ chế khác NULL.

### 15.3. Không dùng marker chuỗi rỗng cho cột bắt buộc nếu nguồn không chuẩn

Một cột `NOT NULL` gặp CSV field trống không quote dưới mặc định `NULL ''` sẽ vi phạm NOT NULL. Đây có thể là lỗi nguồn hợp lý. Đừng vội dùng `FORCE_NOT_NULL` để “qua được lỗi” nếu thực chất nghiệp vụ yêu cầu giá trị không được trống.

## 16. FORMAT TEXT: không phải CSV bỏ dấu nháy

`FORMAT text` là định dạng mặc định của PostgreSQL COPY. Mỗi row thường nằm trên một dòng vật lý, các fields phân cách mặc định bởi **tab**. Những ký tự điều khiển và ký tự đặc biệt được viết bằng **backslash sequences**.

### 16.1. Mặc định

~~~sql
COPY copy411.contacts
TO STDOUT
WITH (FORMAT text);
~~~

File TEXT sẽ không có CSV quoting semantics; PostgreSQL dùng `\N` cho SQL NULL, và các ký tự đặc biệt được escape theo quy tắc text.

### 16.2. TEXT có DELIMITER tùy chọn

Để dễ nhìn trong tài liệu, ta dùng ký tự pipe `|` thay tab:

~~~sql
COPY copy411.contacts(contact_id, full_name, nickname, note)
TO STDOUT
WITH (
    FORMAT text,
    DELIMITER '|',
    NULL E'\\N'
);
~~~

Khi một giá trị chứa `|`, COPY TEXT có thể biểu diễn ký tự đó dưới dạng `\|` để không nhầm với delimiter. **Không dùng CSV double quote để che dấu pipe trong TEXT**; đó là cơ chế khác.

### 16.3. Bảng escape của COPY TEXT

| Dữ liệu cần biểu diễn | Trong file TEXT | Ý nghĩa khi COPY FROM TEXT |
| --- | --- | --- |
| Newline thật | `\n` | Ký tự line feed |
| Carriage return | `\r` | Ký tự carriage return |
| Tab | `\t` | Ký tự tab |
| Backslash | `\\` | Một backslash |
| Backspace | `\b` | Ký tự backspace |
| Form feed | `\f` | Ký tự form feed |
| Vertical tab | `\v` | Ký tự vertical tab |
| Ký tự delimiter `|` khi DELIMITER là `|` | `\|` | Một `|` trong field |
| Octal/hex escape | Theo cú pháp COPY TEXT | Một ký tự/byte hợp lệ theo encoding |

Những ký hiệu `\n`, `\t` và `\\` trong bảng là **các ký tự backslash thật trong file**, không phải chỉ dẫn phải gõ Enter hoặc Tab vào giữa record.

### 16.4. Ví dụ COPY TEXT inline với pipe

~~~sql
CREATE TABLE copy411.text_demo (
    id integer PRIMARY KEY,
    name text,
    note text
);

COPY copy411.text_demo (id, name, note)
FROM STDIN
WITH (FORMAT text, DELIMITER '|', NULL E'\\N');
1|An|Hello\nWorld
2|Bình|\N
3|Chi|\\N
4|Dũng|a\|b
5|Em|C:\\temp\\report.txt
\.
~~~

Chạy khối này trong **psql** theo cơ chế inline data. Không xem những dòng `1|An|...` là câu SQL.

### 16.5. Kết quả

~~~sql
SELECT
    id,
    name,
    note,
    note IS NULL AS is_null,
    position(E'\n' IN note) > 0 AS contains_newline
FROM copy411.text_demo
ORDER BY id;
~~~

- id 1: note là hai dòng, newline được giải mã từ `\n`.
- id 2: note là SQL NULL theo marker `\N`.
- id 3: note là chuỗi literal `\N`, vì file chứa `\\N`.
- id 4: note là `a|b`, không bị tách cột.
- id 5: note là `C:\temp\report.txt`, không bị tự đổi `\t`/`\r` vì backslash đã được escape.

### 16.6. TEXT NULL được nhận diện trước khi bỏ escape

Đây là quy tắc quan trọng:

~~~text
Field \N  → so khớp NULL marker trước → SQL NULL
Field \\N → không trùng marker \N → xử lý escape → text \N
~~~

Ngược lại, nếu dùng một parser thủ công “unescape trước rồi so NULL marker”, hai field có thể bị xem là cùng nghĩa, làm **mất dữ liệu thật**.

### 16.7. Dữ liệu không được quote theo CSV

Một field TEXT có giá trị:

~~~text
"An, Nguyễn"
~~~

Nếu file thực sự chứa các dấu double quote, COPY TEXT sẽ **lưu chúng như ký tự dữ liệu** (trừ những tương tác escape khác), không tự bỏ chúng như CSV parser. Ngược lại, CSV quoted value dùng quote như cú pháp file.

### 16.8. Vì sao E-string của SQL và escape TEXT dễ lẫn?

Khi viết SQL:

~~~sql
NULL E'\\N'
~~~

PostgreSQL parse `E'\\N'` thành **chuỗi gồm backslash và N**, dùng làm option NULL. Sau đó, khi COPY đọc file TEXT:

~~~text
\N
~~~

parser nhận marker đó là SQL NULL. Đây là **hai lớp phân tích khác nhau**:

1. SQL parser xử lý câu `COPY WITH (...)`.
2. COPY TEXT parser xử lý file payload.

Không vì SQL cần `E'\\N'` mà nghĩ file phải viết `\\N` để biểu diễn NULL: **file mặc định dùng `\N`**.

### 16.9. NUL byte và dữ liệu nhị phân

PostgreSQL `text` không lưu ký tự NUL `\0` trong giá trị text thông thường. Nếu cần nhúng bytes bất kỳ, phải xem kiểu `bytea` và cách encode của nguồn; đừng coi COPY TEXT/CSV là định dạng vận chuyển tùy ý mọi byte kể cả NUL.

## 17. CSV khác TEXT khi gặp backslash

Giả sử file có field:

~~~text
C:\temp\new
~~~

### 17.1. Trong CSV mặc định

~~~csv
1,C:\temp\new
~~~

Backslash không mang nghĩa đặc biệt như trong TEXT, nên nội dung đọc là chuỗi `C:\temp\new`.

### 17.2. Trong TEXT mặc định

~~~text
1|C:\temp\new
~~~

Nếu format text đang dùng `DELIMITER '|'`, `\t` trong `\temp` được nhận diện thành tab, `\n` trong `\new` thành newline. Nội dung **không còn là đường dẫn ban đầu**.

### 17.3. Cách viết đúng cho TEXT

~~~text
1|C:\\temp\\new
~~~

Mỗi backslash dữ liệu được viết `\\`. Khi COPY FROM TEXT, nó trở về một backslash trong string thật.

### 17.4. Vì sao không đổi FORMAT theo đuôi file?

Tên file `data.txt` không có nghĩa nó dùng PostgreSQL COPY TEXT. Một file `data.csv` cũng có thể dùng delimiter `;`, hoặc chứa quote/backslash theo dialect riêng. Format **phải đến từ hợp đồng serialization**, không suy từ phần mở rộng.

## 18. Ký hiệu \. và kết thúc COPY FROM STDIN

Trong psql, khi đang nhập inline data cho:

~~~sql
COPY copy411.null_demo (id, val)
FROM STDIN
WITH (FORMAT csv);
~~~

psql cần biết khi nào hết dữ liệu. Dòng:

~~~text
\.
~~~

được dùng làm **end-of-data marker** trong inline `COPY FROM STDIN`.

### 18.1. CSV và trường hợp literal \.

Nếu dữ liệu thật là chuỗi `\.` nằm một mình trên record, nó có thể bị nhầm với marker kết thúc khi nhập bằng inline psql. Trong CSV, một cách thể hiện cho field text ấy là quoted:

~~~csv
"\."
~~~

Tuy nhiên, khi nhập qua inline psql, vẫn phải biết cách psql đọc marker/line; nên dùng file stream đúng chuẩn hoặc test rõ tình huống này.

### 18.2. Thay đổi theo PostgreSQL major version

Tài liệu PostgreSQL hiện hành nêu khác biệt lịch sử: **trước PostgreSQL 18**, dạng unquoted `\.` trên một dòng có thể được nhận diện như end marker ngay cả khi đọc CSV từ file riêng. **PostgreSQL 18** điều chỉnh điều này đối với CSV file; psql inline `COPY FROM STDIN` vẫn cần marker `\.`. Khi có dữ liệu thực tế chứa `\.` đứng riêng dòng, kiểm thử trên **đúng major version**.

### 18.3. Không đưa \. vào file CSV theo thói quen

Với `\copy ... FROM 'file.csv'`, kết thúc file thường đã xác định end-of-input; không tự chèn dòng `\.` vào file dữ liệu vì có thể tạo thêm record hoặc thay nghĩa trên các version khác nhau. Hãy để producer/consumer dùng đúng protocol/cú pháp tương ứng.

## 19. CSV nhiều dòng, dấu CRLF/LF và “số dòng”

### 19.1. Một record có thể chiếm nhiều dòng vật lý

~~~csv
id,note
1,"Dòng 1
Dòng 2"
2,"Dòng 3"
~~~

File trên có **hai records dữ liệu**, nhưng người đọc bằng text editor có thể thấy **bốn dòng vật lý** gồm header. Không lấy số newline bytes rồi trừ 1 để kết luận số records CSV.

### 19.2. Khi nào xuống dòng kết thúc record?

Trong CSV, newline **ngoài vùng quoted field** thường đánh dấu kết thúc record. Newline **bên trong quoted field** là một phần giá trị. Parser phải theo dõi trạng thái quote/escape qua nhiều dòng.

### 19.3. COPY TEXT thường dùng \n escape

COPY TEXT được thiết kế theo một row mỗi dòng; newline dữ liệu nên được biểu diễn bằng `\n` thay vì newline vật lý nằm giữa field. PostgreSQL khuyến nghị serialize carriage return/newline thành `\r`/`\n` để tăng tính di động.

### 19.4. File line ending

Các kiểu thường gặp:

- Unix LF: byte `0A`;
- Windows CRLF: bytes `0D 0A`;
- Một số file cũ CR: byte `0D`.

PostgreSQL có thể đọc những kiểu line endings được hỗ trợ, nhưng **trộn nhiều kiểu không nhất quán** có thể gây lỗi, đặc biệt khi file chứa newline không được quote/escape đúng.

### 19.5. Dữ liệu nhiều dòng có thể gây misleading line number

Thông báo lỗi `COPY ... line N` thường quy về vị trí trong input stream, không nhất thiết là “record số N trừ header” khi records trải qua nhiều dòng vật lý. Khi debug CSV multiline, cần parser-aware record tracking.

### 19.6. Khoảng trắng ngoài quote

CSV:

~~~csv
1, "An"
~~~

có một dấu cách trước `"`. Đừng giả định parser sẽ bỏ dấu cách rồi coi field như `"An"`. PostgreSQL CSV coi các ký tự là có ý nghĩa; whitespace bên cạnh vùng quoted field có thể được hiểu khác với điều producer kỳ vọng. Nếu nguồn hay pad spaces, dùng preprocess có quy tắc, không sửa tay vô điều kiện.

## 20. Encoding tiếng Việt, BOM và code point

Một CSV đúng delimiter/quote vẫn có thể nhập sai tiếng Việt nếu encoding không thống nhất.

### 20.1. UTF-8

Với dữ liệu như:

~~~csv
id,name
1,Nguyễn Văn An
2,Trần Thị Bình
~~~

hãy thống nhất producer xuất **UTF-8** và PostgreSQL/client đọc đúng encoding đó.

### 20.2. ENCODING trong COPY

PostgreSQL hiện hành hỗ trợ:

~~~sql
COPY copy411.contacts (
    contact_id, full_name, nickname
)
FROM STDIN
WITH (
    FORMAT csv,
    HEADER true,
    ENCODING 'UTF8'
);
~~~

`ENCODING` xác định cách giải mã/ghi bytes của file/stream. Nếu không đặt, COPY dùng client encoding theo semantics PostgreSQL. Chú ý support và options theo major version khi làm việc trên hệ thống cũ.

### 20.3. Kiểm tra database và client encoding

~~~sql
SHOW server_encoding;
SHOW client_encoding;
~~~

Database encoding và client encoding khác nhau vẫn có thể kết nối đúng nhờ conversion, nhưng phải bảo đảm các ký tự của file được khai báo chính xác. Nếu bytes nguồn thực sự là Windows-1258 hoặc UTF-16 mà bị gán nhầm UTF-8, file có thể lỗi hoặc thành mojibake.

### 20.4. BOM

Một số phần mềm ghi UTF-8 **BOM** ở đầu file. BOM có thể xuất hiện dưới dạng ký tự Unicode `U+FEFF` ở header hoặc field đầu nếu pipeline không xử lý tương ứng, làm tên header đầu tiên trở thành `\uFEFFid` thay vì `id`.

Không mặc định rằng mọi server/tool đều tự loại BOM theo cách bạn muốn. Khi `HEADER MATCH` báo lỗi dù nhìn file “giống nhau”, hãy kiểm tra bytes đầu và quy ước BOM, rồi chuẩn hóa đầu vào trong pipeline được kiểm soát.

### 20.5. Unicode normalization

Hai chuỗi tiếng Việt nhìn giống nhau có thể có cách mã hóa Unicode khác (ví dụ ký tự dựng sẵn và ký tự kết hợp). COPY **không phải bộ chuẩn hóa Unicode**. Nếu nghiệp vụ cần so khớp chuỗi ổn định, chuẩn hóa Unicode theo quy tắc có phiên bản và kiểm chứng, không kỳ vọng CSV import tự chuyển tất cả tên.

### 20.6. Không chọn delimiter đa byte

PostgreSQL yêu cầu `DELIMITER` là ký tự **một byte**. Dù file dùng UTF-8 và dữ liệu có tiếng Việt, bạn không thể chọn `'。'` hoặc một ký tự tiếng Việt đa byte làm delimiter trong COPY như một chuỗi bất kỳ.

### 20.7. Kiểm tra DateStyle và định dạng ngày

~~~sql
SET DateStyle = ISO;
~~~

Khi export/import dữ liệu ngày giờ, DateStyle và timezone có thể ảnh hưởng biểu diễn. Với file trao đổi, ưu tiên định dạng ISO và timestamp có timezone khi nghiệp vụ yêu cầu; không dựa vào cách bảng tính locale hiển thị `03/04/2026` để suy ngay đó là ngày 3/4 hay 4/3.

### 20.8. CSV là chuỗi, kiểu dữ liệu được parse sau

Một field CSV `"000123"` vẫn là text payload khi parser CSV giải mã; nếu đích là `integer`, PostgreSQL sẽ convert thành `123` và mất leading zeros theo **kiểu cột**. Với mã khách hàng/SKU, dùng `text` hoặc `varchar` thay vì integer nếu số 0 đầu có ý nghĩa.

## 21. Xuất file CSV bằng \copy trong psql

Giả sử bạn mở psql trên máy client, có quyền `SELECT` bảng lab và muốn tạo một file để đưa cho hệ thống khác.

### 21.1. Export có header và quy tắc rõ

~~~text
\copy (SELECT contact_id, full_name, nickname, note, active, created_at FROM copy411.contacts ORDER BY contact_id) TO 'contacts_export.csv' WITH (FORMAT csv, HEADER true, DELIMITER ',', NULL '')
~~~

Đây là **một lệnh psql meta-command**, không kết thúc bằng dấu `;` theo cú pháp một câu SQL thông thường. Tùy phiên bản psql, cú pháp `\copy` và quoting đường dẫn có quy tắc riêng; với đường dẫn thực, kiểm tra psql help và hệ điều hành.

### 21.2. Tại sao thêm ORDER BY?

`COPY table TO` không bảo đảm thứ tự các rows là thứ tự ID nếu không có một query với `ORDER BY`. Khi cần file reproducible để so sánh giữa lần export, dùng `COPY (SELECT ... ORDER BY ...) TO` với bộ tie-breakers xác định.

### 21.3. Chọn column list rõ

Nếu bảng được thêm cột mới sau migration, `COPY table TO` không có column list có thể thay số lượng/cấu trúc fields. Chọn và ghi rõ column list trong integration contract giúp giảm rủi ro thay schema ngầm.

### 21.4. Chỉ export dữ liệu được phép

~~~text
\copy (SELECT contact_id, full_name FROM copy411.contacts WHERE active = true ORDER BY contact_id) TO 'contacts_active.csv' WITH (FORMAT csv, HEADER true)
~~~

Query quyết định các rows/cột được xuất. Đừng mặc định một app role được `SELECT` mọi cột trong bảng; áp dụng grants/RLS và minimization cho file gửi ra ngoài.

### 21.5. File nằm trên máy client

Với `\copy ... TO 'contacts_export.csv'`, tên file tương đối được hiểu theo môi trường/cwd của **psql client**. Server không tạo file này trong data directory. Nếu chạy psql trên máy khác, file nằm ở máy ấy, không tự xuất hiện trên laptop của bạn.

### 21.6. Nếu cần server-side COPY

~~~sql
COPY (
    SELECT contact_id, full_name
    FROM copy411.contacts
    ORDER BY contact_id
)
TO '/approved/server/export/contacts.csv'
WITH (FORMAT csv, HEADER true);
~~~

Lệnh này tạo file phía **server** và yêu cầu quyền tương ứng. Nó không phải cách phù hợp cho role ứng dụng quyền thấp chỉ muốn tải CSV. Dùng `STDOUT`/`\copy` hoặc streaming API nếu cần client-side download.

## 22. Nhập CSV bằng \copy và bảo toàn semantics

Giả sử file `contacts_export.csv` được xuất theo cấu trúc 6 cột của `copy411.contacts`.

### 22.1. Tạo bảng đích riêng

~~~sql
CREATE TABLE copy411.contacts_roundtrip (
    LIKE copy411.contacts INCLUDING ALL
);
~~~

Trong lab, bảng gốc có các constraints/default phù hợp để copy bằng `LIKE ... INCLUDING ALL`. Trên production, việc clone bảng có constraints/indexes/defaults không thay thế schema migration hoặc compatibility review.

### 22.2. Import bằng đúng options

~~~text
\copy copy411.contacts_roundtrip (contact_id, full_name, nickname, note, active, created_at) FROM 'contacts_export.csv' WITH (FORMAT csv, HEADER MATCH, DELIMITER ',', NULL '')
~~~

Nếu PostgreSQL/psql version hỗ trợ `HEADER MATCH` và file header đúng thứ tự, COPY kiểm tra header trước khi nhập các rows. Nếu file không có header hoặc source có tên alias khác, điều chỉnh hợp đồng thay vì tự tắt kiểm tra một cách mù quáng.

### 22.3. Kiểm tra số rows

~~~sql
SELECT
    (SELECT COUNT(*) FROM copy411.contacts) AS source_rows,
    (SELECT COUNT(*) FROM copy411.contacts_roundtrip) AS target_rows;
~~~

Hai số bằng nhau là một **điều kiện cần**, không phải bằng chứng dữ liệu tương đương. Hai rows có thể bị tráo `nickname`/`note` nếu cùng kiểu text và header bị bỏ qua bằng `HEADER true`.

### 22.4. So sánh có cả NULL

~~~sql
SELECT
    s.contact_id,
    s.full_name AS original_name,
    t.full_name AS reimported_name,
    s.nickname IS NOT DISTINCT FROM t.nickname
        AS nickname_equal_including_null,
    s.note IS NOT DISTINCT FROM t.note
        AS note_equal_including_null,
    s.active IS NOT DISTINCT FROM t.active
        AS active_equal_including_null,
    s.created_at IS NOT DISTINCT FROM t.created_at
        AS date_equal_including_null
FROM copy411.contacts AS s
FULL OUTER JOIN copy411.contacts_roundtrip AS t
    ON s.contact_id = t.contact_id
ORDER BY COALESCE(s.contact_id, t.contact_id);
~~~

Để kiểm chứng đầy đủ nên so tất cả cột, xác định rows thiếu/thừa và dùng các phép so sánh **NULL-safe**.

### 22.5. Dùng EXCEPT để kiểm tra tập dữ liệu

~~~sql
(
    SELECT *
    FROM copy411.contacts
    EXCEPT
    SELECT *
    FROM copy411.contacts_roundtrip
)
UNION ALL
(
    SELECT *
    FROM copy411.contacts_roundtrip
    EXCEPT
    SELECT *
    FROM copy411.contacts
);
~~~

Nếu schema và dữ liệu giống nhau theo semantics `EXCEPT` thì kết quả rỗng. Trong bảng không có khóa duy nhất hoặc có duplicate rows, `EXCEPT` mặc định loại duplicate; khi cần kiểm tra multiplicity dùng `EXCEPT ALL` hoặc so counts theo khóa/group.

### 22.6. Hash không thay thế kiểm chứng logic

Checksum/hash của bytes file giúp phát hiện thay đổi file trên đường truyền, nhưng hai CSV files có thể khác bytes mà **cùng dữ liệu** (khác line endings/quoting), hoặc cùng bytes nhưng import với **khác NULL/DELIMITER options** cho kết quả khác. Cần cả checksum của artifact lẫn kiểm chứng schema/parsed values.

## 23. COPY FROM STDIN với inline CSV và giới hạn thực hành

Nếu bạn chạy psql trực tiếp, có thể tạo bảng và nhập inline data:

~~~sql
CREATE TABLE copy411.inline_contacts (
    id integer PRIMARY KEY,
    name text,
    note text
);

COPY copy411.inline_contacts(id, name, note)
FROM STDIN
WITH (FORMAT csv, HEADER true, DELIMITER ',');
id,name,note
1,"An, Nguyễn","Có dấu phẩy, trong ô"
2,"Bình ""Bé""","Có dấu quote"
3,Chi,
4,Dũng,""
\.
~~~

### 23.1. Kỳ vọng

| id | name | note |
| --- | --- | --- |
| 1 | `An, Nguyễn` | `Có dấu phẩy, trong ô` |
| 2 | `Bình "Bé"` | `Có dấu quote` |
| 3 | `Chi` | SQL NULL |
| 4 | `Dũng` | Chuỗi rỗng |

### 23.2. Tại sao cần \.?

Trong inline psql, `\.` báo client kết thúc việc gửi các dòng CSV cho `COPY FROM STDIN`. Nếu bạn đặt code này trong Java/JDBC, driver phải cấp dữ liệu bằng **COPY protocol API**; `\.` không phải tự động là một lệnh SQL gửi được ở mọi API.

### 23.3. INSERT qua SQL vs COPY input

Với một lượng dữ liệu rất nhỏ, lệnh `INSERT INTO ... VALUES (...)` thường dễ kiểm soát. Với hàng trăm nghìn rows từ file, `COPY` có thể giảm overhead/throughput hơn, nhưng cần hợp đồng delimiter/NULL/schema và kiểm soát quyền/transaction.

### 23.4. Không gửi file CSV như một statement SQL

`COPY ... FROM STDIN` chỉ mở chế độ truyền dữ liệu. Driver phải chuyển qua protocol COPY, không phải cứ thực thi chuỗi SQL rồi gửi thêm `INSERT` hay text payload theo cách ad hoc. Với Java PostgreSQL JDBC, xem `CopyManager`/`PGConnection` APIs, xử lý streams, encoding và lỗi theo tài liệu driver.

## 24. Dùng staging table để tách parse khỏi business validation

Đối với file nhận từ nguồn bên ngoài, không nên nhập thẳng vào bảng nghiệp vụ nếu chưa biết chắc schema, delimiter, NULL và data quality.

### 24.1. Pipeline gợi ý

~~~text
Nguồn CSV/TSV
  |
  +-- Kiểm tra metadata: checksum, encoding, version, schema
  |
  +-- Parse CSV/TEXT theo contract cố định
  |
  +-- COPY vào staging với các cột text
  |
  +-- Validate tên, kiểu, ngày, NULL/empty
  |
  +-- Lưu rejected rows và nguyên nhân
  |
  +-- INSERT ... SELECT đã chuyển kiểu vào bảng đích
  |
  +-- Đối chiếu accepted/rejected và xác nhận batch
~~~

### 24.2. Bảng staging

~~~sql
CREATE TABLE copy411.contact_stage (
    import_row_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    contact_id_text text,
    full_name_text text,
    nickname_text text,
    note_text text,
    active_text text,
    created_at_text text,
    imported_at timestamptz NOT NULL DEFAULT clock_timestamp()
);
~~~

Với staging tất cả fields dữ liệu ban đầu là text, những giá trị `'not-a-date'` có thể được lưu như dữ liệu tạm (thay vì làm COPY chấm dứt ngay khi input parser của date lỗi), **nhưng** lỗi cấu trúc CSV, encoding hoặc quoting vẫn có thể khiến COPY fail.

### 24.3. Explicit column list cho staging

~~~text
\copy copy411.contact_stage (contact_id_text, full_name_text, nickname_text, note_text, active_text, created_at_text) FROM 'contacts_export.csv' WITH (FORMAT csv, HEADER true, DELIMITER ',', NULL '')
~~~

Ở đây file xuất có header `contact_id,full_name,...` nhưng column list staging mang hậu tố `_text`. Vì vậy **`HEADER true`** chỉ bỏ header; `HEADER MATCH` sẽ **không khớp** tên. Đây là một lựa chọn có chủ đích khi dùng staging. Nếu muốn MATCH, dùng staging với tên cột hợp đồng hoặc một bước kiểm tra header độc lập.

### 24.4. Kiểm tra dữ liệu đầu vào

~~~sql
SELECT
    import_row_id,
    contact_id_text,
    full_name_text,
    created_at_text,
    nickname_text IS NULL AS nickname_missing,
    nickname_text = '' AS nickname_empty
FROM copy411.contact_stage
ORDER BY import_row_id
LIMIT 20;
~~~

### 24.5. Lỗi ngày không nên được silently coerced

Nếu input ngày có thể là `DD/MM/YYYY` hoặc `MM/DD/YYYY`, không chỉ gọi `created_at_text::date` rồi hi vọng DateStyle đúng. Thiết kế quy tắc parse định dạng cụ thể, validate số/ngày, ghi rejected rows và giữ raw input để điều tra.

### 24.6. Tách dữ liệu gốc với dữ liệu chuẩn hóa

Staging nên giữ raw field đủ để điều tra: ví dụ `nickname_text IS NULL` vs `nickname_text=''` cần được bảo toàn. Nếu ngay khi nhận file bạn đã `COALESCE(nickname_text,'')`, thông tin về nguồn NULL sẽ bị mất.

### 24.7. Đối chiếu counts

~~~sql
SELECT COUNT(*) AS staged_rows
FROM copy411.contact_stage;
~~~

Kết hợp:

~~~text
total source data records
  = parsed/staged records + rejected parse records

staged records
  = accepted transform rows + rejected validation rows
~~~

Lưu ý với CSV có quoted multiline, “source data records” **không** nhất thiết bằng “số physical lines trừ một header”.

### 24.8. Kiểm soát trùng lặp

Nếu nhập lại cùng file, tránh `INSERT` tạo duplicate hoặc overwrite dữ liệu hiện có theo cách vô ý. Dùng batch ID/file checksum, staging partition, unique keys, transaction, `ON CONFLICT` logic được review và kiểm chứng accepted/rejected trước khi công bố kết quả.

## 25. Các lỗi thường gặp khi HEADER/DELIMITER sai

### 25.1. invalid input syntax for type integer

~~~text
ERROR: invalid input syntax for type integer: "contact_id"
~~~

Nguyên nhân thường gặp: file có header nhưng `HEADER true` chưa bật. PostgreSQL cố parse tên cột thành integer.

**Khắc phục:** xác nhận file có header, dùng `HEADER true` hoặc `HEADER MATCH` phù hợp.

### 25.2. extra data after last expected column

~~~text
ERROR: extra data after last expected column
~~~

Nguyên nhân có thể: delimiter trong field không được quote, sai DELIMITER, parser chọn nhầm format hoặc có thêm cột trong file.

**Khắc phục:** xác minh mỗi record có đúng field count, dùng parser CSV, đối chiếu schema contract và xem quoted delimiter/newline.

### 25.3. missing data for column

~~~text
ERROR: missing data for column "note"
~~~

Một record có ít fields hơn expected, ví dụ thiếu dấu phân cách cuối. Đừng nhầm **field trống** với **field không tồn tại**:

~~~csv
1,An,
~~~

có ba fields; còn:

~~~csv
1,An
~~~

chỉ có hai fields.

### 25.4. unterminated CSV quoted field

~~~csv
1,"An
~~~

File kết thúc mà quote chưa được đóng (hoặc quote/escape bị sai), PostgreSQL không thể xác định điểm kết thúc field/record.

### 25.5. Header sai mà không lỗi

Nếu hai cột đều text và file đổi thứ tự nhưng nhập bằng `HEADER true`, PostgreSQL có thể nhập thành công mà **giá trị rơi sai cột**. Đây là lỗi data quality nguy hiểm hơn một syntax error.

### 25.6. CSV dùng semicolon nhưng import bằng comma

~~~csv
id;name;note
1;An;Hello
~~~

Nếu parser mong delimiter comma, mỗi dòng có thể chỉ được xem là **một field**, dẫn tới missing columns hoặc conversion error.

### 25.7. NULL thành chuỗi rỗng

Nếu import với `FORCE_NOT_NULL` không đúng contract, field trống không quote sẽ thành `''` thay vì SQL NULL. Query `IS NULL` có thể đột ngột trả ít records hơn.

### 25.8. Chuỗi rỗng thành NULL

Nếu dùng `FORCE_NULL` với marker trống trên cột text có empty string hợp lệ, quoted `""` cũng chuyển thành NULL và mất nghĩa riêng.

### 25.9. \N bị hiểu sai

Nếu file thực sự là COPY TEXT nhưng bạn import bằng CSV, `\N` không có nghĩa SQL NULL theo CSV default. Ngược lại, nếu file CSV chứa backslashes đường dẫn nhưng import bằng TEXT, các sequences như `\t` hoặc `\n` có thể bị đổi thành tab/newline.

### 25.10. Lỗi encoding tiếng Việt

Nếu UTF-8 bytes được đọc bằng encoding khác hoặc file có BOM ảnh hưởng header name, `HEADER MATCH` có thể lỗi hoặc dữ liệu tên bị hỏng. Kiểm tra encoding/file bytes, không sửa SQL delimiter để chữa sai encoding.

## 26. COPY FROM có bỏ qua dòng lỗi được không?

**Mặc định**, khi `COPY FROM` gặp lỗi, statement sẽ thất bại. PostgreSQL hiện hành có tùy chọn điều khiển lỗi chuyển đổi kiểu:

~~~sql
ON_ERROR stop
ON_ERROR ignore
~~~

Các phiên bản PostgreSQL trước khi có tính năng này không chấp nhận cú pháp tương ứng. **Đối chiếu major version** trước khi sử dụng `ON_ERROR`, `REJECT_LIMIT` và `LOG_VERBOSITY`.

### 26.1. ON_ERROR ignore có phạm vi hẹp

Theo tài liệu PostgreSQL hiện hành, `ON_ERROR ignore` được hỗ trợ cho `COPY FROM` định dạng `text`/`csv` để **bỏ qua hàng có lỗi chuyển đổi giá trị cột sang kiểu dữ liệu đích**.

Không nên suy ra nó bỏ qua được **mọi lỗi**:

- Cấu trúc CSV sai quote/delimiter có thể làm parser không xác định record.
- Constraint violation có semantics riêng, không phải cứ là conversion error.
- Permission error, lỗi file, lỗi encoding hoặc server error không biến thành một row reject thông thường.
- Triggers có thể phát sinh lỗi nghiệp vụ ngoài phạm vi xử lý conversion.

### 26.2. REJECT_LIMIT

~~~sql
COPY copy411.contacts (
    contact_id,
    full_name,
    nickname,
    note,
    active,
    created_at
)
FROM STDIN
WITH (
    FORMAT csv,
    HEADER true,
    ON_ERROR ignore,
    REJECT_LIMIT 5
);
~~~

`REJECT_LIMIT` giới hạn số lỗi chuyển đổi được chấp nhận khi dùng `ON_ERROR ignore`. Nếu lỗi vượt giới hạn, lệnh COPY thất bại. Trên PostgreSQL versions không có option này, cần staging/validation/driver-level reject flow thay thế.

### 26.3. LOG_VERBOSITY

Tài liệu hiện hành cho phép lựa chọn mức thông báo liên quan rows bị bỏ qua, chẳng hạn `default`, `verbose`, `silent`. `verbose` có thể cho biết line/column gặp conversion error; `silent` giảm thông báo. Đây là **tùy chọn quan sát**, không phải công cụ kiểm chứng dữ liệu đầu vào.

### 26.4. Vì sao không bật ignore vô hạn?

Nếu nguồn có 100.000 records nhưng chỉ 40.000 được nhập do kiểu ngày sai, một lệnh COPY hoàn tất mà không có đối soát sẽ tạo **bảng thiếu dữ liệu**. Hãy:

1. Định nghĩa reject budget;
2. Lưu rejects/raw rows hoặc tạo báo cáo;
3. So sánh source record count với accepted/rejected;
4. Không công bố batch nếu tỷ lệ lỗi vượt ngưỡng;
5. Sửa nguồn/transform theo quy trình thay vì bỏ qua âm thầm.

### 26.5. Khi lỗi COPY giữa chừng

Nếu `COPY FROM` dừng do lỗi, những rows đã được xử lý trong statement bị rollback về ngữ nghĩa transaction; tuy nhiên chúng có thể để lại dead tuples cần VACUUM reclaim dung lượng tùy tình huống. Đừng kết luận bảng đã sạch hoàn toàn về **disk usage** chỉ vì query sau rollback không nhìn thấy rows.

### 26.6. Cần phân biệt error class

| Loại lỗi | Ví dụ | Giải pháp thường phù hợp |
| --- | --- | --- |
| Parse CSV | Quote chưa đóng | Sửa/loại file không hợp lệ |
| Số field | Thiếu/dư cột | Đối chiếu HEADER/DELIMITER/column list |
| Encoding | Bytes không giải mã được | Xác nhận encoding/đổi encoding đúng |
| Chuyển kiểu | `'abc'` vào integer | Staging text, validation; có thể dùng ON_ERROR theo version |
| Constraint | Duplicate key, NOT NULL | Sửa dữ liệu/model, dedup/merge có kiểm soát |
| Trigger | RAISE EXCEPTION từ trigger | Review business rules |
| Quyền | permission denied | Cấp INSERT/SELECT đúng mức hoặc dùng \copy |
| Hệ thống | Disk full/timeout | Runbook vận hành, transaction/retry |

## 27. COPY FROM và triggers, constraints, RLS

### 27.1. Trigger INSERT có thể được kích hoạt

`COPY FROM` sẽ kích hoạt các triggers/check constraints phù hợp của bảng đích, theo semantics PostgreSQL. Một row-level BEFORE INSERT trigger có thể chuẩn hóa dữ liệu và một AFTER trigger có thể ghi audit; đây cũng là một nguồn chi phí khi nạp file lớn.

### 27.2. COPY FROM không thực thi rules như kỳ vọng mọi người

Theo tài liệu PostgreSQL, `COPY FROM` kích hoạt triggers và check constraints nhưng không gọi rules như một lệnh INSERT được rewrite bình thường. Nếu hệ thống cũ dựa vào query rewrite rules cho việc insert, cần kiểm chứng rõ trước khi dùng COPY thay cho INSERT.

### 27.3. RLS

`COPY TO` có liên quan tới SELECT policies cho dữ liệu đọc. Với `COPY FROM` vào bảng bật Row-Level Security, PostgreSQL hiện hành có giới hạn được mô tả trong tài liệu: **không hỗ trợ COPY FROM cho bảng bật RLS**, nên cần dùng các lệnh INSERT phù hợp nếu phải áp policies. Đừng disable RLS trong sản xuất chỉ để nhập nhanh.

### 27.4. NOT NULL / CHECK / UNIQUE vẫn quan trọng

Các rules serialize/parse NULL không thay business constraints:

~~~sql
CREATE TABLE copy411.required_demo (
    code text PRIMARY KEY,
    note text NOT NULL
);
~~~

Nếu CSV default có note field trống không quote, PostgreSQL đọc thành SQL NULL và cột NOT NULL sẽ từ chối. Nếu dùng FORCE_NOT_NULL, có thể nhập chuỗi rỗng `''`, nhưng vẫn cần CHECK nếu nghiệp vụ không cho phép text rỗng.

### 27.5. COPY và identity columns

Nếu cột identity được chỉ định trong column list của `COPY FROM`, PostgreSQL có semantics nhập giá trị được cung cấp thay vì mặc nhiên sinh mới, theo tài liệu COPY. Khi import dữ liệu có IDs từ nguồn ngoài, xác định chính sách tránh trùng khóa, tránh lệch sequence và quyền trước khi chạy.

### 27.6. Đừng loại bỏ constraints để giảm lỗi import

Một file có lỗi dữ liệu cần staging và sửa nguồn. Việc tắt trigger/check hoặc nới schema constraints để COPY “thành công” có thể khiến dữ liệu production vi phạm invariants, gây lỗi khó sửa hơn về sau.

## 28. Bảo mật file CSV và dữ liệu xuất

### 28.1. CSV không mã hóa dữ liệu

File có `FORMAT csv` dễ đọc bằng text editor; nếu nó chứa email, số điện thoại, địa chỉ hoặc dữ liệu khách hàng, cần kiểm soát nơi lưu, truyền và quyền truy cập. `QUOTE` hay `FORCE_QUOTE` không phải encryption.

### 28.2. CSV formula injection

Một trường user-generated text có thể bắt đầu bằng các ký tự mà một số chương trình bảng tính diễn giải là công thức, chẳng hạn `=`, `+`, `-`, `@` hoặc các trường hợp có whitespace/control characters.

Ví dụ dữ liệu trong DB:

~~~text
=1+1
~~~

Khi được export thành CSV rồi mở trong một spreadsheet, phần mềm có thể **diễn giải thành công thức** thay vì text đơn thuần, tùy ứng dụng/cấu hình.

`FORCE_QUOTE` **không phải cơ chế bảo đảm chống formula injection**: spreadsheet có thể vẫn parse giá trị sau khi bỏ CSV quotes. Với export hướng tới bảng tính, sử dụng một phương án neutralization theo security policy và test trên đúng ứng dụng đích, hoặc xuất định dạng có explicit text types thay vì CSV thô.

### 28.3. Đừng dùng escaping CSV để chống SQL injection

SQL query/connection APIs phải dùng placeholders/prepared statements. CSV quoting chỉ giúp parser CSV nhận field boundaries; một field được quote đúng CSV vẫn có thể là dữ liệu nguy hiểm nếu ứng dụng sau đó ghép nó vào câu SQL.

### 28.4. Không cấp quyền đọc file server rộng cho app

Nếu ứng dụng chỉ muốn nhận file, dùng `COPY ... TO STDOUT` hoặc API export được bảo vệ, không cấp `pg_read_server_files`/superuser hoặc cho phép tùy chọn path server.

### 28.5. PII trong file test

Trong bài lab, dùng tên giả. Khi debug sản phẩm thật, không gửi raw CSV chứa thông tin cá nhân qua kênh support/log không được phép; có thể tạo file sanitized tái hiện quote/NULL lỗi mà không giữ PII.

### 28.6. Quyền với đường dẫn \copy

`\copy` đọc/ghi file của **tài khoản hệ điều hành chạy psql**. Việc database user có quyền INSERT/SELECT không chứng minh client có quyền đọc/ghi đúng đường dẫn file; cả hai lớp quyền đều cần được kiểm tra.

## 29. Các điểm khác biệt giữa PostgreSQL và chương trình bảng tính

| Vấn đề | PostgreSQL COPY CSV | Spreadsheet có thể xử lý |
| --- | --- | --- |
| NULL vs empty | Phân biệt unquoted empty với `""` theo mặc định | Có thể gộp hai trường hợp khi mở/lưu |
| Kiểu dữ liệu | Parse theo kiểu cột bảng | Có thể tự suy kiểu theo locale |
| Leading zeros | Giữ nếu cột text | Có thể bỏ nếu coi là số |
| Date | Theo PostgreSQL input functions/DateStyle | Có thể tự đổi day/month |
| Quotes | CSV grammar rõ | Có thể export với dialect riêng |
| Line endings | CSV multiline được hỗ trợ | Có thể sửa line breaks khi save lại |
| Delimiter | Cấu hình rõ một ký tự một byte | Có thể theo locale `,`/`;` |
| Formula-like text | COPY chỉ serialize dữ liệu | Có thể diễn giải như công thức |
| Encoding | ENCODING/client encoding | Có thể thêm BOM hoặc xuất encoding khác |

**Không coi việc mở và lưu lại CSV bằng phần mềm bảng tính là một bước “vô hại”**. Sau save lại, cần đối chiếu data contract, nhất là NULL, leading zeros, date, embedded newline và encoding.

## 30. Chọn định dạng xuất/nhập phù hợp

### 30.1. CSV phù hợp khi

- Trao đổi với Excel/BI/ETL/các hệ thống có CSV parser;
- Cần header để hệ thống nhận biết cột;
- Có thống nhất delimiter, quote/escape và NULL marker;
- Cần text-based, dễ inspect/log metadata;
- Producer/consumer chấp nhận quoted multiline records.

### 30.2. TEXT phù hợp khi

- Pipeline nội bộ PostgreSQL hoặc hệ thống hiểu rõ COPY TEXT rules;
- Muốn escape backslash/newline/tab theo định dạng COPY;
- Sử dụng mặc định `\N` biểu diễn NULL;
- Không phụ thuộc quoting CSV;
- File cần một row mỗi physical line với escaped newlines.

### 30.3. Binary phù hợp khi

- Producer và consumer đều PostgreSQL-compatible, đã kiểm tra type/version;
- Muốn hiệu năng truyền dữ liệu và chấp nhận thấp hơn về tính portable/human-readable;
- Không cần HEADER/DELIMITER/NULL string/QUOTE/ESCAPE như định dạng text.

### 30.4. Dữ liệu phân cấp hoặc schema tiến hóa

Nếu dữ liệu có JSON objects lồng nhau, nhiều loại records/optional fields hoặc schema evolution phức tạp, có thể cân nhắc JSON Lines, Parquet hoặc một giao thức có schema. `COPY CSV` vẫn có thể đưa JSON thành một field text nếu quote đúng, nhưng điều đó không tự xử lý versioning/schema validation.

### 30.5. Ưu tiên hợp đồng, không chỉ tên định dạng

Một hợp đồng file nên ghi:

~~~yaml
format: csv
header: true
header_validation: match
delimiter: ","
quote: '"'
escape: '"'
null_marker: ""
encoding: UTF8
column_order:
  - contact_id
  - full_name
  - nickname
  - note
  - active
  - created_at
date_format: ISO_8601
newline_policy: LF_or_CRLF
version: "1"
~~~

Đây là **mẫu tài liệu hợp đồng**, không phải YAML tự động được PostgreSQL COPY đọc. Đồng thời cần định nghĩa rõ cách phân biệt **NULL** và **empty string**, chính sách cho embedded newlines, cột nào bắt buộc và cách báo lỗi/reject rows.

## 31. Sơ đồ quyết định import file

~~~mermaid
flowchart TD
    A["Nhận file từ nguồn ngoài"] --> B{"Biết format contract?"}
    B -->|Không| C["Xác minh producer: CSV hay TEXT, delimiter, encoding, NULL"]
    C --> B
    B -->|Có| D{"File text-based?"}
    D -->|Không| E["Đánh giá binary/schema/version riêng"]
    D -->|Có| F{"CSV hay COPY TEXT?"}
    F -->|CSV| G["Chọn HEADER / DELIMITER / QUOTE / ESCAPE / NULL"]
    F -->|TEXT| H["Chọn DELIMITER và backslash/NULL rules"]
    G --> I["Kiểm tra header, row count, encoding"]
    H --> I
    I --> J["COPY vào staging và validate"]
    J --> K{"Accepted/rejected đạt yêu cầu?"}
    K -->|Không| L["Dừng công bố, sửa nguồn/mapping"]
    K -->|Có| M["Nạp bảng đích theo transaction/idempotency"]
    M --> N["Đối chiếu NULL/empty, số rows và dữ liệu mẫu"]
~~~

### 31.1. Vai trò của HEADER MATCH

`HEADER MATCH` chặn một số lỗi schema/column order, nhưng nó **không** kiểm tra cột `amount` có luôn là giá trị dương, email có hợp lệ, ngày không tương lai hoặc business key có trùng hay không. Các kiểm tra đó thuộc validation/constraints.

### 31.2. Vai trò của FORCE options

`FORCE_NULL`/`FORCE_NOT_NULL` thay đổi **cách parse field**. Chúng không là công cụ tự động sửa data quality hay thay `NOT NULL`/`CHECK`.

### 31.3. Vai trò của round-trip

Round-trip giúp kiểm tra serialization đối với dữ liệu thử có delimiter, quote, newline và NULL. Nó không thay authorization, kiểm thử load lớn, concurrency hoặc đối soát nghiệp vụ.

## 32. Bài tập cơ bản: HEADER và DELIMITER

Các bài tập dưới đây dùng schema `copy411` và những bảng lab đã tạo. Một số bài có file inline `COPY FROM STDIN` với `\.`: chỉ chạy trực tiếp trong **psql** hoặc một công cụ có hỗ trợ tương đương. Nếu dùng GUI/JDBC, tạo file có nội dung tương ứng hoặc API COPY streaming. Không chạy lên bảng nghiệp vụ production. Bài tập mang tính suy luận có thể thực hiện bằng giấy trước khi thử SQL.

### Bài 1 — COPY mặc định là định dạng nào?

~~~sql
COPY copy411.contacts TO STDOUT;
~~~

**Câu hỏi:** PostgreSQL dùng `FORMAT csv` hay `FORMAT text` nếu không ghi FORMAT? Dấu phân cách và NULL marker mặc định là gì?

**Đáp án:** TEXT, tab, `\N`.

### Bài 2 — CSV mặc định

~~~sql
COPY copy411.contacts
TO STDOUT WITH (FORMAT csv);
~~~

**Câu hỏi:** delimiter, quote, escape, NULL marker mặc định của CSV là gì?

**Đáp án:** dấu phẩy; quote/escape đều double quote; NULL là field trống không quote.

### Bài 3 — Header có hay không?

Một file:

~~~csv
id,name
1,An
2,Bình
~~~

**Câu hỏi:** nếu COPY FROM không có `HEADER true`, điều gì xảy ra khi cột id là integer?

### Bài 4 — Bỏ nhầm dòng dữ liệu đầu tiên

File không có header:

~~~csv
1,An
2,Bình
~~~

Nhưng import dùng `HEADER true`. **Câu hỏi:** server sẽ xử lý dòng `1,An` thế nào? Có nhất thiết báo lỗi không?

**Đáp án:** bỏ như header, có nguy cơ mất dòng mà không báo lỗi.

### Bài 5 — HEADER MATCH

File có header:

~~~csv
name,id
An,1
~~~

COPY chỉ định `(id,name)` và `HEADER MATCH`. **Câu hỏi:** PostgreSQL có tự đảo fields theo tên không?

**Đáp án:** không; sẽ báo lỗi mismatch header names/order.

### Bài 6 — HEADER true nhưng sai mapping

Hai cột cùng kiểu text: `first_name`, `last_name`. File thay thứ tự header thành `last_name,first_name` nhưng dùng `HEADER true`.

**Bài tập:** mô tả lỗi âm thầm có thể xảy ra, và tại sao `HEADER MATCH` hoặc contract check quan trọng.

### Bài 7 — Header của COPY(query)

~~~sql
COPY (
    SELECT contact_id AS id, full_name AS display_name
    FROM copy411.contacts
) TO STDOUT
WITH (FORMAT csv, HEADER true);
~~~

**Câu hỏi:** tên header sẽ là `contact_id,full_name` hay `id,display_name`?

### Bài 8 — Có HEADER trên binary không?

Một người đề xuất:

~~~sql
COPY copy411.contacts TO STDOUT
WITH (FORMAT binary, HEADER true);
~~~

**Câu hỏi:** HEADER có ý nghĩa với binary không?

**Đáp án:** không được hỗ trợ.

### Bài 9 — Delimiter semicolon

File:

~~~csv
id;name;note
1;An;Hello
2;"Bình; Bé";"Có ; trong ô"
~~~

**Bài tập:** viết `COPY FROM` đúng với `DELIMITER ';'`, `HEADER true`.

### Bài 10 — Pipe không thay quote

File:

~~~text
1|An|A|B
~~~

Đích có ba cột và delimiter `|`. **Câu hỏi:** có mấy fields? Cần viết field thứ ba chứa `A|B` thế nào theo CSV?

**Đáp án:** dòng hiện tại có bốn fields; sửa thành `1|An|"A|B"`.

### Bài 11 — Delimiter nhiều ký tự

Một producer xuất `id||name||note` rồi muốn dùng `DELIMITER '||'`.

**Câu hỏi:** PostgreSQL COPY có chấp nhận delimiter này không? Gợi ý giải pháp.

**Đáp án:** không; cần preprocess/producer đổi thành delimiter một byte hoặc dùng parser riêng chuyển định dạng.

### Bài 12 — Tab vs spaces

Một người nhìn TSV bằng editor rồi thay tab bằng bốn spaces để “dễ căn cột”.

**Bài tập:** giải thích tại sao `DELIMITER E'\t'` không còn parse đúng.

### Bài 13 — Dấu phẩy trong chuỗi

File:

~~~csv
1,"An, Nguyễn",active
~~~

**Câu hỏi:** có mấy fields? Nếu bỏ quote quanh tên sẽ thành mấy fields?

### Bài 14 — Sai số field

Phân biệt:

~~~csv
1,An,
1,An
~~~

với column list `(id,name,note)`.

**Câu hỏi:** cái nào là field trống, cái nào là thiếu field?

### Bài 15 — Có nên suy delimiter bằng đếm dấu phẩy?

File có giá trị quoted `"An, Nguyễn"`. Nếu cứ `split(',')`, bản ghi được tách sai thế nào? Viết pseudocode mức cao cho parser cần theo dõi quote state.

## 33. Bài tập trung cấp: QUOTE, ESCAPE và multiline

### Bài 16 — Escape dấu nháy kép

Giá trị thật:

~~~text
Bình "Bé"
~~~

**Bài tập:** ghi CSV field đúng với quote/escape mặc định.

**Đáp án:** `"Bình ""Bé"""`.

### Bài 17 — Có dấu quote và delimiter

Giá trị thật:

~~~text
Nguyễn "An, Bé"
~~~

**Bài tập:** ghi CSV field đúng, giải thích dấu quote nào là outer quote, dấu nào là escape.

### Bài 18 — CSV multiline

~~~csv
id,note
1,"Dòng 1
Dòng 2"
2,OK
~~~

**Câu hỏi:** có mấy records dữ liệu? Tại sao số physical lines không bằng số records?

### Bài 19 — CSV backslash

Một field trong CSV default chứa:

~~~text
C:\temp\new
~~~

**Câu hỏi:** backslash có tự biến thành tab/newline như TEXT không?

**Đáp án:** không; CSV mặc định không dùng backslash escaping kiểu COPY TEXT.

### Bài 20 — COPY TEXT backslash

Muốn lưu literal path `C:\temp\new` với `FORMAT text` và delimiter `|`.

**Bài tập:** viết field TEXT escaped.

**Đáp án:** `C:\\temp\\new`.

### Bài 21 — TEXT delimiter bên trong giá trị

Với `DELIMITER '|'`, một field thật có text `A|B`. **Bài tập:** viết field trong COPY TEXT.

**Đáp án:** `A\|B`.

### Bài 22 — TEXT newline

Ghi field chứa hai dòng `Hello` và `World` bằng COPY TEXT.

**Câu hỏi:** dùng newline vật lý trong field hay `\n` escape?

**Đáp án:** `Hello\nWorld` trong file TEXT.

### Bài 23 — TEXT literal \N

Phân biệt hai TEXT fields:

~~~text
\N
\\N
~~~

**Câu hỏi:** cái nào là SQL NULL, cái nào là chuỗi hai ký tự `\N` theo mặc định?

### Bài 24 — CSV literal \N

Một CSV default chứa field không quote `\N`.

**Câu hỏi:** có trở thành SQL NULL không?

**Đáp án:** không; đó là text literal `\N`.

### Bài 25 — QUOTE và ESCAPE khác nhau

Một producer dùng quote `"` nhưng escape ký tự quote bằng backslash. Người nhận để `ESCAPE '"'`.

**Bài tập:** xác định vì sao parser có thể hiểu sai và cần agreement gì giữa hai bên.

### Bài 26 — FORCE_QUOTE

`COPY TO CSV WITH (FORCE_QUOTE *)` trên các values `NULL`, `''`, `'abc'`.

**Câu hỏi:** NULL có được quote không? Vì sao PostgreSQL phải giữ phân biệt?

**Đáp án:** NULL không quote; non-NULL values được quote.

### Bài 27 — Dấu cách

So:

~~~csv
"  An  "
  An
~~~

**Câu hỏi:** PostgreSQL có tự trim thành `An` không? Nếu producer thêm whitespace cạnh dấu quote, rủi ro gì?

### Bài 28 — File line ending

Một CSV có nơi dùng CRLF, nơi dùng LF và có field chứa newline không được quote.

**Bài tập:** giải thích vì sao parser có thể lỗi và cách chuẩn hóa line-ending/quoted multiline theo contract.

### Bài 29 — \. trong inline psql

Khi dùng `COPY FROM STDIN` nhập inline trong psql, dòng nào kết thúc stream? Dữ liệu CSV literal `\.` đứng riêng dòng cần được xử lý thế nào?

### Bài 30 — Khác biệt version

Một file CSV có field `\.` đứng riêng dòng được xuất từ PostgreSQL 18 nhưng nhập vào PostgreSQL 16.

**Bài tập:** xác định compatibility risk về end marker, cách kiểm tra version và test round-trip.

## 34. Bài tập nâng cao: NULL, empty và FORCE options

### Bài 31 — NULL và empty string

CSV default:

~~~csv
id,note
1,
2,""
~~~

**Câu hỏi:** giá trị `note` ở hai rows trong PostgreSQL là gì?

**Đáp án:** row 1 SQL NULL; row 2 chuỗi rỗng.

### Bài 32 — Giá trị text 'NULL'

CSV default có field `NULL` không quote.

**Câu hỏi:** có thành SQL NULL không?

**Đáp án:** không; chỉ là chuỗi `'NULL'`.

### Bài 33 — NULL 'NULL'

Với `NULL 'NULL'`, phân biệt:

~~~csv
1,NULL
2,"NULL"
~~~

**Đáp án:** row 1 SQL NULL, row 2 text `'NULL'` nếu không dùng FORCE_NULL.

### Bài 34 — NULL marker trùng dữ liệu thật

Một producer chọn `NULL 'N/A'` nhưng business có mô tả sản phẩm literal `N/A`.

**Bài tập:** producer cần quote field nào, và consumer cần giữ options gì để không mất nghĩa?

### Bài 35 — FORCE_NOT_NULL

Field trống không quote trong cột `note text` với `FORCE_NOT_NULL(note)`.

**Câu hỏi:** giá trị DB là SQL NULL hay `''`?

**Đáp án:** `''`.

### Bài 36 — FORCE_NOT_NULL với integer

Field trống không quote vào cột integer, dùng `FORCE_NOT_NULL`.

**Câu hỏi:** có tự trở thành 0 không?

**Đáp án:** không; chuỗi rỗng không phải số nguyên hợp lệ, có thể báo conversion error.

### Bài 37 — FORCE_NULL với quoted empty

`NULL ''` và `FORCE_NULL(note)` được sử dụng; field là `""`.

**Câu hỏi:** PostgreSQL import giá trị gì?

**Đáp án:** SQL NULL.

### Bài 38 — FORCE_NULL với quoted 'NULL'

`NULL 'NULL'` và `FORCE_NULL(note)`; field là `"NULL"`.

**Đáp án:** SQL NULL.

### Bài 39 — FORCE_NOT_NULL và FORCE_NULL cùng cột

`NULL 'NULL'`, `FORCE_NULL(note)` và `FORCE_NOT_NULL(note)`:

~~~csv
1,NULL
2,"NULL"
~~~

**Câu hỏi:** row nào thành text, row nào thành SQL NULL?

**Đáp án:** row 1 text `'NULL'`, row 2 SQL NULL.

### Bài 40 — NULL khác DEFAULT

Một cột `status text DEFAULT 'pending' NOT NULL`.

**Câu hỏi:** nếu nhập field trống không quote vào status với CSV default, nó có tự thành pending không? Nếu bỏ hẳn cột status khỏi COPY column list thì sao?

**Đáp án:** NULL marker nhập SQL NULL (có thể vi phạm NOT NULL); nếu cột không nằm trong column list, default có thể được áp dụng.

## 35. Bài tập tổng hợp: pipeline và vận hành

### Bài 41 — Round-trip dữ liệu đa dạng

Xuất `copy411.contacts` bằng `\copy ... FORMAT csv, HEADER true`, rồi nhập vào bảng `contacts_roundtrip`. So sánh các cột chứa:

- NULL;
- Chuỗi rỗng;
- Dấu phẩy;
- Dấu quote;
- Newline;
- Backslash;
- Unicode tiếng Việt;
- Date.

**Yêu cầu:** dùng `IS NOT DISTINCT FROM` hoặc `EXCEPT ALL` phù hợp để xác minh. Giải thích vì sao chỉ so row count chưa đủ.

### Bài 42 — Header alias vs MATCH

Export query đổi `contact_id AS id` và `full_name AS name`, nhưng import vào column list `(contact_id, full_name)` với HEADER MATCH.

**Câu hỏi:** vì sao lỗi? Cách sửa: export header theo target contract, đổi staging names, hoặc kiểm tra header độc lập rồi dùng mapping.

### Bài 43 — Staging với tên cột _text

File header là `contact_id,full_name,...`, staging columns là `contact_id_text,full_name_text,...`.

**Bài tập:** chọn `HEADER true` hay `HEADER MATCH` cho thao tác COPY vào staging? Làm sao vẫn kiểm tra header contract ngoài COPY?

### Bài 44 — Lỗi kiểu ngày

CSV có `created_at=32/13/2026`, bảng đích là `date`.

**Bài tập:** giải thích tại sao không nên tùy tăng DateStyle hoặc ON_ERROR ignore không giới hạn; đề xuất staging text và rejected report.

### Bài 45 — Bản ghi nhiều dòng

File chứa 1.000 records CSV, nhưng đếm newline được 1.100 vì notes nhiều dòng.

**Câu hỏi:** làm sao xác định số CSV records đúng, không dùng split newline?

### Bài 46 — CSV formula injection

Một field bắt đầu bằng `=1+1`, sẽ được mở trong spreadsheet.

**Câu hỏi:** `FORCE_QUOTE *` đã đủ ngăn ứng dụng đích hiểu thành công thức chưa? Biện pháp nào cần kiểm tra?

**Đáp án:** không đủ; cần neutralization/import-as-text hoặc format có kiểu text theo policy của ứng dụng đích.

### Bài 47 — COPY server file vs \copy client file

Developer chạy:

~~~sql
COPY copy411.contacts FROM 'C:\Users\Me\contacts.csv'
WITH (FORMAT csv, HEADER true);
~~~

và server PostgreSQL thực tế chạy trên Linux remote.

**Bài tập:** giải thích vì sao server không thấy file laptop; chọn `\copy` từ client hoặc `COPY FROM STDIN` qua driver.

### Bài 48 — Không được quyền COPY server file

App role có INSERT trên bảng nhưng không có `pg_read_server_files`.

**Câu hỏi:** có nên cấp role file-server rộng chỉ để nhập CSV từ ứng dụng không? Phương án thay thế?

**Đáp án:** không; dùng `STDIN`/`\copy` hoặc import API có scope quyền đúng.

### Bài 49 — ON_ERROR ignore

File có 100 rows; 20 rows sai kiểu ngày. Một nhóm muốn bật `ON_ERROR ignore` rồi xem import không báo lỗi fatal là thành công.

**Bài tập:** lập bảng accepted/rejected, reject limit, đối chiếu source count, báo cáo nguyên nhân và threshold công bố. Phân biệt conversion error với constraint/CSV parser errors.

### Bài 50 — Capstone: tích hợp dữ liệu đối tác

Một đối tác gửi hàng ngày file:

~~~csv
customer_code;full_name;nickname;note;joined_at
000123;"Nguyễn, An";;"Ghi chú ""VIP""";2026-01-31
000124;Bình;"";"Dòng 1
Dòng 2";2026-02-01
000125;Chi;NULL;C:\sales\new;2026-02-02
~~~

Hợp đồng thực tế do đối tác xác nhận:

- `FORMAT csv`, `DELIMITER ';'`, `QUOTE '"'`, `ESCAPE '"'`;
- File UTF-8, có header;
- Đối tác muốn **nickname trống không quote = SQL NULL**;
- `""` = chuỗi rỗng;
- `NULL` không quote là **text literal 'NULL'**;
- `customer_code` là text, phải giữ số 0 đầu;
- Ghi chú có thể chứa quote, delimiter, newline và backslash;
- joined_at dùng ISO date;
- Không được mất dữ liệu hoặc nhập trùng lô khi retry.

**Yêu cầu nộp:**

1. Định nghĩa bảng staging và bảng đích.
2. Viết `\copy`/`COPY FROM STDIN` đúng delimiter/header/encoding.
3. Nêu rõ NULL marker nên dùng theo hợp đồng và có cần FORCE options không.
4. Giải thích ba trường hợp nickname ở các rows.
5. Giải thích tại sao CSV backslash trong `C:\sales\new` không cần escape kiểu COPY TEXT.
6. Kiểm tra quoted newline để không đếm sai records.
7. Đảm bảo `customer_code` không chuyển thành integer.
8. Đối chiếu schema/header, có thể dùng `HEADER MATCH` khi column list trùng hợp đồng.
9. Validate ngày, chuỗi bắt buộc, duplicates và lỗi bất thường.
10. Có import batch ID/checksum, accepted/rejected report, transaction và idempotency.
11. Kiểm tra round-trip giữa CSV → staging → bảng đích → CSV export.
12. Đề xuất kiểm soát PII và formula injection nếu file được mở bằng phần mềm bảng tính.

**Mục tiêu quan trọng:** không chỉ làm cho COPY “không báo lỗi”, mà phải chứng minh cả **cấu trúc và ý nghĩa các giá trị** được giữ đúng qua nhập–xuất.

## 36. Checklist trước khi nhận file

### 36.1. Cấu trúc file

- [ ] Đã xác nhận `FORMAT csv` hay `FORMAT text`; không suy chỉ từ tên đuôi file.
- [ ] Đã xác định có header hay không.
- [ ] Nếu có header, đã quyết định `HEADER true` hoặc `HEADER MATCH`.
- [ ] Nếu dùng MATCH, tên và thứ tự cột trùng danh sách COPY.
- [ ] Đã kiểm tra số cột của mọi record, không chỉ header.
- [ ] Đã chốt column list, thứ tự và kiểu dữ liệu đích.
- [ ] Đã xác nhận delimiter chỉ một ký tự một byte.
- [ ] Đã xác nhận dấu phân cách `,`, `;`, `|` hay tab.
- [ ] Không parse quoted CSV bằng split(',')/split('\n').
- [ ] Đã xác định liệu có embedded newline hoặc delimiter trong text.

### 36.2. Quote và escape

- [ ] Với CSV, đã xác nhận QUOTE và ESCAPE.
- [ ] Nếu dùng mặc định, embedded `"` được viết thành `""`.
- [ ] Đã kiểm thử fields chứa quote và delimiter cùng lúc.
- [ ] Đã kiểm thử CSV nhiều dòng với quote mở/đóng đúng.
- [ ] Với TEXT, đã dùng backslash escapes đúng, không mang CSV quote rules sang.
- [ ] Đã kiểm tra các đường dẫn chứa backslash trong TEXT.
- [ ] Đã kiểm tra trường hợp literal `\N` và marker `\N` trong TEXT.
- [ ] Đã kiểm tra end-of-data `\.` nếu nhập inline psql hoặc dùng phiên bản cũ.

### 36.3. NULL và chuỗi rỗng

- [ ] Đã ghi rõ SQL NULL khác `''`, khác `'NULL'` và khác literal `'\N'`.
- [ ] Biết CSV mặc định unquoted empty = NULL, quoted `""` = empty.
- [ ] Biết TEXT mặc định `\N` = SQL NULL, `\\N` = literal `\N`.
- [ ] Đã chọn `NULL '...'` theo hợp đồng, không đổi tùy tiện.
- [ ] Đã kiểm tra dữ liệu thật có trùng null marker không.
- [ ] Chỉ dùng `FORCE_NULL` hoặc `FORCE_NOT_NULL` trên cột cần thiết.
- [ ] Không dùng FORCE_NOT_NULL để bỏ qua lỗi NOT NULL nghiệp vụ.
- [ ] Biết `FORCE_QUOTE` không quote SQL NULL.
- [ ] Đã kiểm tra NULL-safe round-trip hoặc output canonical.
- [ ] Không tự `COALESCE` NULL thành text trước export khi phải bảo toàn ý nghĩa.

### 36.4. Encoding, loại dữ liệu và an toàn

- [ ] Encoding nguồn và `ENCODING`/client encoding nhất quán.
- [ ] Đã kiểm tra BOM nếu HEADER MATCH lỗi bất thường.
- [ ] Đã kiểm tra LF/CRLF và newline trong quoted CSV.
- [ ] Đã xác định chuẩn ngày/giờ/decimal và locale.
- [ ] Mã có leading zeros được lưu kiểu text khi cần.
- [ ] Có cơ chế chặn/neutralize CSV formula injection nếu mở bằng spreadsheet.
- [ ] Dữ liệu PII được quản lý quyền và retention phù hợp.
- [ ] Không cấp quyền server files rộng chỉ để nhập CSV từ client.
- [ ] Đã phân biệt `COPY` server-side và `\copy` client-side.

### 36.5. Vận hành import

- [ ] Import vào staging nếu nguồn không hoàn toàn đáng tin.
- [ ] Có schema/version/checksum/import batch ID.
- [ ] Có negative tests cho delimiter sai, header sai, quote lỗi, NULL/empty.
- [ ] Có báo cáo accepted/rejected và đối chiếu tổng records.
- [ ] Nếu dùng ON_ERROR ignore, đã xem version và giới hạn phạm vi conversion errors.
- [ ] Không bỏ qua lỗi constraint/trigger mà không điều tra.
- [ ] Có transaction/rollback/idempotency cho batch import.
- [ ] Có retry policy tránh nhập trùng dữ liệu.
- [ ] Đã kiểm tra trigger/check/RLS của bảng đích.
- [ ] Có kế hoạch quan sát performance và disk/WAL khi COPY lớn.
- [ ] Đã test export→import→so sánh dữ liệu thật bằng NULL-safe checks.

## 37. Câu hỏi thường gặp

### 37.1. COPY CSV có bắt buộc dấu phẩy không?

Không. CSV mặc định dùng dấu phẩy nhưng có thể chỉ định `DELIMITER ';'` hoặc một ký tự một byte khác. Producer và consumer phải thống nhất delimiter.

### 37.2. HEADER true có tự map cột theo tên không?

Không. Nó chỉ bỏ qua header khi nhập. `HEADER MATCH` kiểm tra tên/thứ tự, nhưng cũng không tự reorder fields.

### 37.3. Tại sao field trống vào PostgreSQL thành NULL?

Đó là quy tắc CSV mặc định với `NULL ''` cho **unquoted empty field**. Muốn chuỗi rỗng, producer có thể ghi `""`; hoặc consumer dùng `FORCE_NOT_NULL` theo hợp đồng rõ.

### 37.4. Dấu `""` trong CSV có nghĩa text '""' không?

Không ở mặc định: nó là **quoted empty string**, được giải mã thành `''`. Muốn một chuỗi thực có hai dấu quote, phải escape/quote theo quy tắc CSV, ví dụ `""""""` là một CSV field có hai dấu quote dữ liệu.

### 37.5. Vì sao CSV mặc định không coi \N là NULL?

Vì CSV mặc định lấy **field trống không quote** làm marker NULL. `\N` là marker NULL mặc định của **COPY TEXT**, không phải CSV.

### 37.6. Tôi đổi NULL marker thành 'NULL' thì field trống thành gì?

Với CSV và cột text không có FORCE options, field trống không quote không còn khớp marker `NULL`, nên được nhập thành chuỗi rỗng, không phải SQL NULL.

### 37.7. Tôi muốn cả "NULL" được xem là NULL?

Dùng `NULL 'NULL'` và `FORCE_NULL(cột)` khi phù hợp. Nhưng hãy xác nhận không có text thật `'NULL'` cần giữ, vì quoted marker cũng bị chuyển thành SQL NULL.

### 37.8. Tôi muốn field trống không bao giờ thành NULL?

Với CSV, `FORCE_NOT_NULL(cột)` có thể dùng cho những cột text mà contract quy định trống là chuỗi rỗng. Đừng áp cho cột số/ngày mà không có quy tắc xử lý.

### 37.9. FORCE_QUOTE có giúp nhập chính xác hơn không?

Nó chỉ tác động khi **xuất CSV**, buộc non-NULL values được quote; không sửa input mapping hay constraint. SQL NULL vẫn không quote.

### 37.10. Vì sao COPY TEXT không dùng QUOTE?

Vì TEXT format dùng **backslash escaping**, không theo cơ chế quoted field của CSV. Muốn CSV quoting hãy chọn `FORMAT csv`.

### 37.11. CSV có thể chứa xuống dòng trong một ô không?

Có, khi field được quote đúng. Vì vậy không dùng số physical lines để suy số records.

### 37.12. Trong psql có nên dùng COPY hay \copy?

Nếu file nằm trên máy chạy psql và role không có quyền truy cập server file, `\copy` thường thuận tiện hơn. `COPY ... FROM '/server/file'` đọc từ máy chạy PostgreSQL server.

### 37.13. Tại sao nhập file trên laptop vào server remote bị báo không thấy file?

Vì `COPY FROM 'path'` là server-side. Dùng `\copy` của psql hoặc `COPY FROM STDIN` qua driver để truyền bytes từ client.

### 37.14. HEADER MATCH có luôn tồn tại trên mọi PostgreSQL không?

Không nên giả định; kiểm tra tài liệu đúng major version. `HEADER MATCH` là tính năng kiểm tra tên/thứ tự, chỉ dùng cho `COPY FROM` trên những formats có hỗ trợ.

### 37.15. Có thể bật ON_ERROR ignore để không bao giờ lỗi import?

Không. Nó chủ yếu giải quyết lỗi **chuyển đổi kiểu dữ liệu cột** ở các phiên bản hỗ trợ; lỗi syntax CSV, quyền, constraints hoặc các lỗi hệ thống vẫn có thể làm COPY thất bại.

### 37.16. COPY có làm chạy trigger không?

`COPY FROM` kích hoạt những triggers/check constraints phù hợp trên bảng đích. Nó có thể làm imports lớn chậm hơn hoặc bị từ chối do business rules. Không tùy tiện disable triggers để "cho qua" lỗi dữ liệu.

### 37.17. Sao mở và save CSV trong Excel lại mất số 0 đầu?

Spreadsheet có thể tự coi mã dạng số và chuyển text `000123` thành số 123. Nếu mã cần giữ leading zeros, dùng kiểu text và hướng dẫn import-as-text/format phù hợp.

### 37.18. Vì sao CRC/hash file giống nhau mà kết quả import khác?

Cùng một file bytes nhưng `FORMAT`, `DELIMITER`, `NULL`, `ENCODING`, column list hoặc kiểu cột đích khác sẽ cho kết quả khác. Checksum bảo vệ bytes, không bảo vệ semantics của parser.

## 38. Tài liệu PostgreSQL chính thức

Tài liệu PostgreSQL có thể khác giữa các major versions; đặc biệt với `HEADER MATCH`, `DEFAULT`, `ON_ERROR`, `REJECT_LIMIT`, xử lý `\.` trong CSV và `ENCODING` option, hãy chọn **đúng phiên bản đang vận hành**.

- [COPY](https://www.postgresql.org/docs/current/sql-copy.html): nguồn chính cho `FORMAT`, `DELIMITER`, `NULL`, `HEADER`, `QUOTE`, `ESCAPE`, FORCE options, TEXT/CSV/BINARY parsing, lỗi và quyền.
- [psql](https://www.postgresql.org/docs/current/app-psql.html): cách dùng `\copy`, client-side file paths, meta-commands và scripting.
- [PostgreSQL Protocol: COPY Operations](https://www.postgresql.org/docs/current/protocol-flow.html#PROTOCOL-COPY): `COPY IN`/`COPY OUT` streams cho clients và drivers.
- [Character Set Support](https://www.postgresql.org/docs/current/multibyte.html): server/client encoding, chuyển đổi và Unicode.
- [Data Types](https://www.postgresql.org/docs/current/datatype.html): cách PostgreSQL nhận các kiểu integer, date, text, boolean, timestamp và conversion.
- [Date/Time Input](https://www.postgresql.org/docs/current/datatype-datetime.html): chuỗi ngày giờ, DateStyle, timezone.
- [String Functions](https://www.postgresql.org/docs/current/functions-string.html): `length`, `btrim` và chức năng chuỗi khi validation.
- [Comparisons](https://www.postgresql.org/docs/current/functions-comparison.html): `IS NULL`, `IS DISTINCT FROM` và NULL semantics.
- [CREATE TABLE](https://www.postgresql.org/docs/current/sql-createtable.html): column defaults, NOT NULL/CHECK/UNIQUE và kiểu dữ liệu.
- [INSERT](https://www.postgresql.org/docs/current/sql-insert.html): lựa chọn thay thế COPY khi cần transform/upsert/RLS.
- [Row Security Policies](https://www.postgresql.org/docs/current/ddl-rowsecurity.html): bảo vệ dữ liệu qua RLS và các giới hạn COPY FROM.
- [Monitoring Progress](https://www.postgresql.org/docs/current/progress-reporting.html#COPY-PROGRESS-REPORTING): `pg_stat_progress_copy` khi COPY dữ liệu lớn.
- [VACUUM](https://www.postgresql.org/docs/current/sql-vacuum.html): reclaim dead tuples sau imports thất bại và quản lý dung lượng.
- [Roles and Privileges](https://www.postgresql.org/docs/current/user-manag.html): quyền SELECT/INSERT, file server permissions và nguyên tắc phân quyền.

## 39. Tổng kết

Một file có header đẹp vẫn có thể nhập sai nếu **thứ tự cột**, **dấu phân cách**, **quy tắc quote/escape** hoặc **NULL marker** không đồng nhất giữa hai phía.

| Yếu tố | Quy tắc nhớ nhanh |
| --- | --- |
| **HEADER true** | Bỏ hàng header khi nhập; xuất tên cột khi export |
| **HEADER MATCH** | Kiểm tra tên và thứ tự header khi COPY FROM, **không reorder** |
| **DELIMITER** | Một ký tự một byte; TEXT mặc định tab, CSV mặc định dấu phẩy |
| **CSV QUOTE** | Mặc định double quote bao field chứa delimiter/quote/newline... |
| **CSV ESCAPE** | Mặc định double quote; literal `"` trong dữ liệu thành `""` |
| **TEXT escape** | Backslash sequences `\n`, `\t`, `\r`, `\\`... |
| **TEXT NULL** | Mặc định `\N` |
| **CSV NULL** | Mặc định **field trống không quote** |
| **CSV empty string** | Mặc định `""` |
| **FORCE_NULL** | Cả quoted marker cũng có thể thành NULL |
| **FORCE_NOT_NULL** | Marker trên cột được chọn không bị coi là NULL |
| **FORCE_QUOTE** | Chỉ export CSV, không quote SQL NULL |
| **\copy** | psql đọc/ghi file phía client |
| **COPY 'path'** | PostgreSQL server đọc/ghi file phía server |

**Khi nhập CSV/TEXT, câu hỏi quan trọng không chỉ là “lệnh COPY có chạy thành công không?” mà là “mỗi giá trị đã được giải mã đúng ý nghĩa chưa?”** Để trả lời, hãy chốt format contract, kiểm tra header/schema, dùng parser đúng, giữ nguyên khác biệt NULL–empty string, nạp staging khi nguồn chưa chắc sạch và thực hiện round-trip với dữ liệu có quote, delimiter, newline, backslash, tiếng Việt và giá trị trống. Đó là nền tảng của một quy trình nhập–xuất PostgreSQL **đúng dữ liệu, an toàn và có thể kiểm chứng**.
