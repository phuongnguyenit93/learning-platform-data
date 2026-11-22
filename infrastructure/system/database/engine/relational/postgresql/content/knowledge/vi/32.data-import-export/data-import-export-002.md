# Định dạng text, CSV, binary và lựa chọn mã hóa trong PostgreSQL

Nhập và xuất dữ liệu là một trong những công việc dễ gặp lỗi âm thầm nhất khi vận hành PostgreSQL. Một tệp trông có vẻ “chỉ gồm các dòng và cột” vẫn có thể chứa rất nhiều quy ước không hiển thị: dấu phân cách, ký tự xuống dòng trong dữ liệu, dấu nháy kép, giá trị NULL, chuỗi rỗng, mã hóa ký tự, byte order mark (BOM), cách viết số thập phân, thời gian và kiểu dữ liệu.

Ví dụ, hai chuỗi sau **không giống nhau**:

- Giá trị SQL `NULL`: không có giá trị.
- Chuỗi rỗng `''`: có giá trị kiểu text, nhưng độ dài bằng không.

Nếu xuất một bảng sang CSV rồi nạp lại mà không thống nhất quy tắc biểu diễn hai trường hợp trên, dữ liệu có thể thay đổi ý nghĩa dù không hề có thông báo lỗi.

PostgreSQL cung cấp lệnh **`COPY`** với ba định dạng dữ liệu phổ biến:

- **Text**: các trường phân cách bằng ký tự, mặc định tab; ký tự đặc biệt được escape theo quy tắc riêng của PostgreSQL.
- **CSV** (*Comma-Separated Values*): định dạng bảng bằng ký tự, hỗ trợ quote, delimiter, dòng mới trong trường và header; thuận tiện để trao đổi với Excel, BI, ứng dụng khác.
- **Binary**: dùng biểu diễn nhị phân theo định dạng COPY riêng của PostgreSQL; phù hợp một số luồng tải dữ liệu giữa các hệ PostgreSQL tương thích nhưng không phải file trao đổi phổ quát.

Bên cạnh định dạng, phải chọn **mã hóa (*encoding*)** phù hợp, thường là UTF-8 cho hệ thống mới. Format và encoding giải quyết hai câu hỏi khác nhau:

```text
                  Dữ liệu PostgreSQL
                          |
                   COPY / \copy
                          |
          +---------------+----------------+
          |               |                |
       FORMAT text     FORMAT csv      FORMAT binary
          |               |                |
   field/line escape  quote/delimiter   type-specific bytes
          |               |                |
          +---------------+----------------+
                          |
                Byte stream / file
                          |
           Khi có dữ liệu ký tự: encoding
           UTF-8, LATIN1, WIN1252, ...
```

Bài học này thuộc module **Database Engine Relational PostgreSQL**, chương **Nhập xuất dữ liệu**, với đề tài **“Định dạng text, CSV, binary và lựa chọn mã hóa”**. Nội dung tập trung vào cách chọn định dạng, cú pháp và semantics của `COPY`, phân biệt server-side/client-side, thiết kế file an toàn, xử lý Unicode và kiểm tra vòng khứ hồi dữ liệu.

---

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt **định dạng dữ liệu** và **mã hóa ký tự**.
2. Giải thích vai trò của `COPY FROM`, `COPY TO`, `COPY FROM STDIN`, `COPY TO STDOUT` và lệnh `\copy` của `psql`.
3. Biết vì sao file path trong `COPY ... FROM '/path'` nằm trên **máy chủ PostgreSQL**, còn trong `\copy ... FROM 'path'` thường là file phía **máy chạy psql**.
4. Chọn `FORMAT text`, `FORMAT csv` hoặc `FORMAT binary` theo mục tiêu.
5. Hiểu dấu phân cách, ký tự kết thúc dòng, backslash escapes và NULL marker của text format.
6. Hiểu CSV header, delimiter, quote, escape, trường chứa dấu phẩy hoặc xuống dòng.
7. Phân biệt `NULL`, chuỗi rỗng và chuỗi có ký tự literal đại diện cho NULL.
8. Sử dụng `HEADER`, `HEADER MATCH`, `NULL`, `QUOTE`, `ESCAPE`, `FORCE_QUOTE`, `FORCE_NULL`, `FORCE_NOT_NULL` khi phù hợp.
9. Hiểu binary COPY không phải định dạng “CSV nhanh” hay bản backup lâu dài.
10. Hiểu `server_encoding`, `client_encoding` và tùy chọn `ENCODING` của COPY.
11. Nhận biết byte order mark (BOM), file UTF-8/UTF-16/Windows code page và lỗi ký tự tiếng Việt.
12. Biết hạn chế của việc “đổi encoding” đối với dữ liệu vốn đã bị mojibake hoặc bị mất ký tự.
13. Thiết kế tệp CSV bảo toàn Unicode, timestamp, decimal, dấu quote và dòng mới.
14. Viết lab nhập qua bảng staging text, kiểm tra/chuẩn hóa rồi chuyển sang bảng typed.
15. Xử lý khi một bản ghi bị lỗi kiểu dữ liệu hoặc vi phạm constraint mà không nuốt lỗi.
16. Hiểu cách COPY tương tác với trigger, CHECK, FOREIGN KEY, RLS, transaction và WAL.
17. Phân biệt tốc độ ingest với độ an toàn, khả năng quan sát và phục hồi sau import.
18. Hiểu rủi ro CSV/Spreadsheet formula injection khi người khác mở file xuất bằng spreadsheet.
19. Sử dụng `psql \copy` và streaming COPY trong ứng dụng thay vì cấp quyền server file không cần thiết.
20. Thiết kế kiểm thử vòng khứ hồi (*round-trip*) cho text, CSV, binary và encoding.

**Phạm vi:** PostgreSQL hiện đại. Một số tùy chọn nâng cao của `COPY` (như xử lý lỗi nhập từng hàng hoặc kiểm tra header) phụ thuộc phiên bản. Luôn kiểm tra `SELECT version();` và tài liệu của phiên bản đang sử dụng trước khi đưa vào production. Các ví dụ dùng schema riêng trong database lab.

---

## 2. Tại sao định dạng nhập xuất là một phần của tính đúng dữ liệu?

Một giao dịch chuyển dữ liệu từ A sang B gồm ít nhất bốn giai đoạn:

```text
Giá trị nguồn
   |
   v
Serialize: biến giá trị thành byte
   |
   v
Truyền file / stdin / network
   |
   v
Parse & convert: byte thành giá trị đích
   |
   v
Kiểm tra kiểu dữ liệu và ràng buộc
   |
   v
Giá trị đích
```

Bất kỳ bước nào cũng có thể gây sai khác.

### 2.1. Lỗi phân tách cột

Dữ liệu `Hà Nội, Việt Nam` chứa dấu phẩy. Nếu file CSV không quote đúng, parser có thể hiểu là hai cột thay vì một.

### 2.2. Lỗi xuống dòng

Ghi chú gồm hai dòng có thể bị đọc như hai records nếu parser xử lý CSV theo từng dòng vật lý mà không nhận ra quoted field.

### 2.3. Lỗi NULL và chuỗi rỗng

Trong CSV mặc định của PostgreSQL, NULL có thể xuất thành một trường rỗng **không quote**, còn chuỗi rỗng được xuất dưới dạng `""`. Nếu công cụ khác không giữ sự khác biệt này, round-trip có thể biến NULL thành empty string hoặc ngược lại.

### 2.4. Lỗi mã hóa

Tên `Đặng Thị Hạnh` đúng trong Unicode có thể bị biến thành ký tự rác khi byte UTF-8 được đọc như một code page khác.

### 2.5. Lỗi kiểu dữ liệu

Chuỗi `1,25` có thể là số thập phân dùng dấu phẩy theo locale, nhưng cột `NUMERIC` trong PostgreSQL thông thường cần dạng phù hợp với cú pháp số được engine nhận, ví dụ `1.25`. CSV delimiter dùng dấu phẩy càng khiến cách ghi này dễ gây nhầm.

### 2.6. Lỗi thời gian

`2026-11-14 09:00` không có timezone rõ ràng; `2026-11-14T09:00:00+07:00` mô tả một thời điểm cụ thể. Nếu nạp vào `TIMESTAMPTZ` với session timezone khác, một giá trị không mang offset có thể mang ý nghĩa khác.

**Kết luận:** “COPY chạy không lỗi” chưa đủ chứng minh dữ liệu được nhập đúng về mặt nghiệp vụ.

---

## 3. COPY là gì?

`COPY` là câu lệnh PostgreSQL dùng để truyền nhiều hàng giữa một bảng/truy vấn và một luồng dữ liệu hoặc file.

### 3.1. Nhập dữ liệu

```sql
COPY schema_name.table_name (col1, col2, col3)
FROM '/server/path/data.csv'
WITH (FORMAT csv, HEADER true);
```

Ở đây file path được giải quyết trên **máy chủ PostgreSQL** và chỉ được phép trong những điều kiện quyền tương ứng.

### 3.2. Xuất dữ liệu

```sql
COPY schema_name.table_name (col1, col2)
TO '/server/path/export.csv'
WITH (FORMAT csv, HEADER true);
```

### 3.3. Xuất kết quả truy vấn

```sql
COPY (
    SELECT order_id, customer_name, amount
    FROM app.orders
    WHERE status = 'PAID'
    ORDER BY order_id
)
TO STDOUT
WITH (FORMAT csv, HEADER true);
```

### 3.4. STDIN và STDOUT

`STDIN` và `STDOUT` dùng giao thức truyền dữ liệu qua **kết nối client–server**, không có nghĩa server tự mở file trên laptop người dùng.

```sql
COPY app.orders (order_id, customer_name)
FROM STDIN
WITH (FORMAT csv, HEADER true);
```

Câu này cần một client hỗ trợ COPY protocol và cung cấp dữ liệu trên luồng STDIN tương ứng.

### 3.5. COPY không phải INSERT từng dòng

COPY thường giảm round trips và overhead so với hàng loạt INSERT đơn lẻ, phù hợp cho bulk load. Tuy nhiên, COPY vẫn phải tuân theo kiểu dữ liệu, nhiều constraints, trigger và transaction semantics của PostgreSQL.

### 3.6. Định dạng và nguồn dữ liệu là hai trục khác nhau

Bạn có thể dùng:

- CSV + server file.
- CSV + STDIN.
- Text + STDOUT.
- Binary + STDIN/STDOUT.

Không đồng nhất “CSV” với “client file” hoặc “binary” với “server file”.

---

## 4. COPY và \copy: sự khác biệt rất quan trọng

`\copy` là một **meta-command của `psql`**, không phải SQL PostgreSQL có thể gửi trực tiếp qua JDBC.

| Vấn đề | SQL `COPY ... FROM '/path'` | `psql \copy ... FROM 'path'` |
| --- | --- | --- |
| Ai mở file? | PostgreSQL server process | Máy/process chạy psql |
| File path nằm ở đâu? | Filesystem phía database server | Filesystem phía client psql |
| Kênh truyền | Server đọc/ghi file | Thông qua COPY STDIN/STDOUT |
| Quyền OS trên file | Quyền OS của server process | Quyền OS của process psql |
| Quyền DB đặc biệt | Có thể cần superuser hoặc predefined file roles | Thường không cần quyền đọc/ghi file của server |
| Cách dùng trong JDBC | SQL COPY protocol qua driver | Không gửi trực tiếp `\copy` |
| Mức phù hợp cho developer | Hạn chế khi database remote | Thường tiện hơn |

### 4.1. Ví dụ \copy nhập file ở máy cá nhân

Trong cửa sổ `psql`:

```text
\copy app.orders (order_id, customer_name, amount) FROM './orders.csv' WITH (FORMAT csv, HEADER true)
```

`./orders.csv` được hiểu theo môi trường chạy `psql`, không phải working directory của PostgreSQL server.

### 4.2. Ví dụ \copy xuất ra file local

```text
\copy (SELECT order_id, amount FROM app.orders ORDER BY order_id) TO './orders-export.csv' WITH (FORMAT csv, HEADER true)
```

### 4.3. Nếu psql chạy trong Docker/CI/server khác

“Client file” là **máy/process chạy psql**, có thể là container, CI runner hoặc bastion, không nhất thiết là máy laptop của developer. Cần xác định đúng filesystem và volume mounts.

### 4.4. SQL COPY server file có rủi ro quyền

Đọc/ghi file phía server liên quan tới các role đặc biệt như `pg_read_server_files`, `pg_write_server_files` hoặc superuser trong các trường hợp tương ứng. Đặc quyền này có thể vượt ranh giới dữ liệu SQL thông thường; không cấp cho role API chỉ để nhập một CSV.

### 4.5. COPY PROGRAM có quyền rất nhạy cảm

`COPY ... PROGRAM` cho phép gọi chương trình phía server trong những điều kiện đặc quyền phù hợp. Nó không phải đường vòng tiện lợi để đọc mọi file hay thực thi shell từ HTTP API. Không nối input người dùng vào một command string chạy phía server.

**Ưu tiên:** dùng `\copy`/COPY protocol từ một process chuyên nhập xuất có quyền tối thiểu khi chỉ cần thao tác file phía client.

---

## 5. So sánh ba định dạng chính

| Tiêu chí | Text | CSV | Binary |
| --- | --- | --- | --- |
| Dễ đọc bằng mắt | Có, nếu hiểu escape | Có | Không |
| Định dạng trường | Delimiter + backslash escapes | Delimiter + quoting/escaping | Binary theo kiểu dữ liệu |
| Delimiter mặc định | Tab | Dấu phẩy | Không có delimiter ký tự như text |
| NULL mặc định | `\N` | Trường rỗng không quote | Marker nhị phân cho NULL |
| Header | Không giống CSV HEADER | Có thể dùng HEADER | Không theo kiểu CSV header |
| Trường chứa xuống dòng | Escape theo quy tắc text | Cho phép newline nằm trong quoted field | Dữ liệu nhị phân theo field |
| Trao đổi với spreadsheet | Kém tiện | Rất phổ biến nhưng cần chống formula injection | Không phù hợp |
| Tương thích công cụ ngoài PostgreSQL | Cần parser theo quy tắc PostgreSQL | Cao nếu tuân thủ CSV dialect | Thấp |
| Tự kiểm tra bằng editor | Có | Có | Không |
| Mã hóa ký tự | Cần thống nhất encoding | Cần thống nhất encoding | Không phải file text |
| Khả năng trao đổi lâu dài | Khá, nếu ghi đầy đủ dialect | Thường tốt nhất khi có schema contract | Không phải lựa chọn archive |
| Tốc độ | Tùy kiểu và workload | Tùy quoting/parsing | Có thể nhanh khi đồng nhất hệ, nhưng không bảo đảm |
| Khuyến nghị mặc định | Khi dùng pipeline đặc thù PostgreSQL | Trao đổi dữ liệu có cấu trúc giữa hệ thống | Luồng COPY PostgreSQL tương thích và được kiểm soát |

**Không có định dạng “nhanh nhất” cho mọi workload.** Cần đo trên cùng bảng, dữ liệu, indexing, network, hardware và transaction strategy.

---

## 6. Text format: cấu trúc cơ bản

Text format của PostgreSQL là dạng truyền thống: một hàng gồm nhiều trường, mặc định ngăn cách bằng **tab**. Dòng mới kết thúc record, và những ký tự có ý nghĩa đặc biệt được escape bằng backslash.

Ví dụ:

```sql
COPY (
    SELECT 101 AS id, 'Nguyễn An'::TEXT AS name
    UNION ALL
    SELECT 102, 'Lê Bình'
)
TO STDOUT
WITH (FORMAT text);
```

Về ý tưởng, nội dung gồm:

```text
101<TAB>Nguyễn An<NEWLINE>
102<TAB>Lê Bình<NEWLINE>
```

Đoạn `<TAB>` và `<NEWLINE>` là **ký hiệu minh họa**; trong luồng thực tế, chúng là các ký tự tương ứng.

### 6.1. Đổi delimiter

```sql
COPY app.simple_export
TO STDOUT
WITH (
    FORMAT text,
    DELIMITER '|'
);
```

Một delimiter phải phù hợp quy tắc của định dạng. Text COPY không tự biến thành CSV chỉ vì bạn dùng dấu phẩy hoặc dấu đứng.

### 6.2. Nếu dữ liệu chứa delimiter?

Text format escape delimiter theo quy tắc text. Một parser chỉ dùng `split('|')` mà không hiểu escape có thể làm sai dữ liệu.

### 6.3. Text format dùng backslash escapes

Các ký tự đặc biệt được biểu diễn theo những escape sequences, ví dụ:

| Ý nghĩa | Biểu diễn text COPY |
| --- | --- |
| Xuống dòng LF trong một trường | `\n` |
| Carriage return CR | `\r` |
| Tab | `\t` |
| Ký tự backslash literal | `\\` |
| NULL mặc định | `\N` |

Đây là **chuỗi ký tự trong file text COPY**, không phải escape của Java source hoặc SQL string literal.

### 6.4. Không tự viết parser text bằng split

Nếu trường chứa tab hoặc xuống dòng được escape, một parser viết vội có thể phân tách sai. Dùng chính PostgreSQL COPY parser hoặc parser tuân thủ dialect đã ghi rõ.

---

## 7. Text format: NULL và chuỗi rỗng

Giả sử:

```sql
SELECT
    NULL::TEXT AS a,
    ''::TEXT AS b,
    E'hello\\world'::TEXT AS c;
```

Khi xuất text format mặc định:

- NULL được ghi dưới dạng marker `\N`.
- Chuỗi rỗng là trường có độ dài 0.
- Backslash trong dữ liệu được escape.

### 7.1. Tùy chỉnh NULL marker

```sql
COPY app.some_table
TO STDOUT
WITH (
    FORMAT text,
    NULL 'NULL'
);
```

Cần cực kỳ cẩn thận: nếu dữ liệu thật là chuỗi `'NULL'`, encoding/escaping phải cho phép parser phân biệt trường chuỗi với marker khi round-trip. Dùng marker mặc định hoặc quy ước rõ thường an toàn hơn.

### 7.2. Text NULL marker không phải SQL keyword

Trong file:

```text
\N
```

là một marker theo định dạng COPY text. Trong SQL:

```sql
SELECT NULL;
```

là giá trị SQL NULL. Không lấy file marker chèn trực tiếp vào một lệnh INSERT mà không hiểu cú pháp.

### 7.3. Kiểm tra bằng IS NULL

Sau import:

```sql
SELECT
    COUNT(*) FILTER (WHERE note IS NULL) AS null_notes,
    COUNT(*) FILTER (WHERE note = '') AS empty_notes
FROM app.some_table;
```

Đây là cách kiểm tra ngữ nghĩa tốt hơn nhìn file bằng mắt.

### 7.4. Chuỗi chỉ có khoảng trắng không phải chuỗi rỗng

`' '` và `''` không giống nhau. Không TRIM mọi cột một cách âm thầm trong pipeline nhập xuất nếu không có chính sách dữ liệu tương ứng.

---

## 8. Text format: cẩn thận với dấu \ và kết thúc COPY STDIN

Trong nhiều ngữ cảnh `psql`, khi nhập dữ liệu trực tiếp cho `COPY FROM STDIN`, một dòng chỉ chứa `\.` được dùng để kết thúc luồng nhập. Đây là **giao ước của client/protocol tương ứng**, không phải một record dữ liệu bình thường mà mọi parser text file phải tự hiểu.

Ví dụ trong `psql`:

```text
COPY app.simple_import (id, value) FROM STDIN WITH (FORMAT text);
1	hello
2	world
\.
```

Hai dòng dữ liệu trên được ngăn cách bằng tab thật.

### 8.1. Đừng đưa dữ liệu tùy ý vào terminal mà không chuẩn bị escape

Nếu dữ liệu do người dùng nhập chứa backslashes, dấu tab hoặc xuống dòng, việc paste thủ công có thể thay đổi ý nghĩa. Với file lớn, ưu tiên `\copy FROM 'file'` hoặc COPY protocol từ code.

### 8.2. Không xem \. là delimiter của định dạng CSV nói chung

Trong file CSV bình thường, một field có giá trị `\.` có thể là dữ liệu hợp lệ. Ý nghĩa của marker kết thúc phải được hiểu theo **ngữ cảnh nhập qua STDIN/psql**, không theo cách parse CSV ở mọi hệ thống.

### 8.3. Mỗi dòng vật lý không luôn là một hàng CSV

Điểm này sẽ khác rõ khi chuyển sang CSV với quoted multiline fields. Không nên áp dụng quy tắc text COPY lên CSV.

---

## 9. CSV format: cấu trúc cơ bản

CSV của PostgreSQL là một dialect có delimiter, quote, escape, header và quy tắc NULL. Mặc định thường dùng:

- `DELIMITER ','`.
- `QUOTE '"'`.
- `ESCAPE '"'`.
- NULL biểu diễn bằng trường rỗng không quote.
- Chuỗi rỗng cần quote khi xuất để phân biệt với NULL theo mặc định.

Ví dụ:

```sql
COPY (
    SELECT 1 AS id, 'Hà Nội, Việt Nam' AS location
    UNION ALL
    SELECT 2, 'TP. Hồ Chí Minh'
)
TO STDOUT
WITH (
    FORMAT csv,
    HEADER true
);
```

Nội dung CSV có dạng:

```csv
id,location
1,"Hà Nội, Việt Nam"
2,TP. Hồ Chí Minh
```

### 9.1. Vì sao cần quote?

Tên `Hà Nội, Việt Nam` chứa dấu phẩy. Nếu không quote, parser sẽ đọc quá số cột mong đợi.

### 9.2. QUOTE khác SQL string quote

Trong SQL source, dấu nháy đơn `'...'` thường dùng để viết string literal. Trong file CSV, quote mặc định là dấu nháy kép `"` dùng để bảo vệ trường chứa delimiter/newline/quote.

### 9.3. CSV không tự có kiểu dữ liệu

Tất cả trường CSV được biểu diễn bằng ký tự. Khi nhập vào PostgreSQL, parser phải chuyển text thành kiểu đích như INTEGER, NUMERIC, TIMESTAMPTZ hoặc BOOLEAN.

### 9.4. CSV không tự mô tả schema đầy đủ

Một header `amount,ordered_at` không cho biết NUMERIC precision/scale, timezone policy, NULL semantics hoặc constraints. Với data exchange nghiêm túc cần kèm **schema contract**.

---

## 10. CSV: delimiter, quote và escape

Ví dụ trường chứa dấu phẩy:

```csv
external_id,buyer,note
E-001,"Nguyễn An","Giao tại Quận 1, TP.HCM"
```

Trường chứa dấu nháy kép:

```csv
external_id,buyer,note
E-002,"Lê Bình","Gói ""combo"" tháng 11"
```

Trường chứa dòng mới:

```csv
external_id,buyer,note
E-003,"Trần Cẩm","Dòng đầu
Dòng thứ hai"
```

### 10.1. Hai dấu nháy kép liên tiếp

Với `QUOTE '"'` và `ESCAPE '"'`, ký tự quote literal trong field được biểu diễn bằng hai dấu nháy:

```text
"Đặt ""combo"" hôm nay"
```

sẽ được parse thành:

```text
Đặt "combo" hôm nay
```

### 10.2. Một logical row có thể trải qua nhiều physical lines

Nếu CSV reader chỉ dùng `readLine()` rồi `split(",")`, nó sẽ làm hỏng ví dụ quoted newline. Nên dùng CSV parser có state machine hiểu quoted fields, hoặc PostgreSQL COPY parser.

### 10.3. Delimiter có thể đổi

```sql
COPY app.orders
TO STDOUT
WITH (
    FORMAT csv,
    DELIMITER ';',
    HEADER true
);
```

Dấu chấm phẩy đôi khi xuất hiện trong file do phần mềm spreadsheet theo locale tạo ra. Tuy nhiên, đổi delimiter không làm số thập phân `12,5` tự trở thành input NUMERIC hợp lệ.

### 10.4. CSV dialect phải được công bố

Khi truyền file giữa tổ chức, ghi rõ delimiter, quote, escape, newline, encoding, NULL marker, header, timezone, numeric format và cách xử lý công thức spreadsheet.

---

## 11. CSV: NULL, empty string và quoted values

Đây là một trong những quy tắc quan trọng nhất.

Giả sử một cột TEXT chứa ba giá trị:

1. `NULL`.
2. `''` (empty string).
3. `'NULL'` (chuỗi có bốn chữ cái).

Với CSV mặc định:

| Giá trị SQL | Biểu diễn trường CSV minh họa |
| --- | --- |
| `NULL` | Trường trống không quote |
| `''` | `""` |
| `'NULL'` | `NULL` |

### 11.1. Vì sao biểu diễn khác text format?

Text COPY mặc định dùng `\N` cho NULL. CSV mặc định dùng chuỗi rỗng không quote làm marker NULL, và quote empty string để giữ ngữ nghĩa.

### 11.2. Đừng đồng nhất mọi blank cell là NULL

Nếu spreadsheet xuất empty cell và empty string cùng thành trường trống, sự khác biệt ban đầu có thể đã mất. COPY không thể đoán lại thông tin mà file không ghi.

### 11.3. Đặt NULL marker tường minh

Để file dễ trao đổi trong pipeline riêng:

```sql
COPY app.some_table
TO STDOUT
WITH (
    FORMAT csv,
    HEADER true,
    NULL '\N'
);
```

Khi đó một trường `\N` không quote có thể đại diện SQL NULL; empty string không bắt buộc bị đồng nhất với null marker.

### 11.4. Marker cũng có thể xuất hiện trong dữ liệu thật

Nếu dữ liệu thực sự chứa chuỗi `\N`, parser/serializer phải dùng quoting phù hợp để phân biệt. Tốt nhất là luôn kiểm tra round-trip với cả NULL, chuỗi rỗng và literal marker.

---

## 12. CSV: FORCE_NULL, FORCE_NOT_NULL và FORCE_QUOTE

Các tùy chọn này giải quyết những trường hợp dễ mơ hồ.

### 12.1. FORCE_QUOTE dùng khi xuất CSV

```sql
COPY app.some_table
TO STDOUT
WITH (
    FORMAT csv,
    HEADER true,
    FORCE_QUOTE *
);
```

Tùy chọn này yêu cầu quote các giá trị **không NULL** theo quy tắc COPY. Nó không biến NULL thành chuỗi rỗng.

### 12.2. FORCE_NULL khi nhập CSV

`FORCE_NULL (col)` cho phép so sánh với NULL marker kể cả khi trường được quote trong những trường hợp phù hợp.

Nếu marker NULL là chuỗi rỗng, `""` thường là empty string; với FORCE_NULL trên cột đó, nó có thể được diễn giải thành NULL.

### 12.3. FORCE_NOT_NULL khi nhập CSV

`FORCE_NOT_NULL (col)` làm parser **không coi giá trị khớp NULL marker là NULL** ở những trường hợp tương ứng. Ví dụ, với NULL marker mặc định là trường trống, một trường trống không quote có thể được giữ thành empty string cho cột đã chỉ định.

### 12.4. Có thể phối hợp hai tùy chọn

Trong những phiên bản phù hợp, cả FORCE_NULL và FORCE_NOT_NULL có thể được dùng trên cùng cột để phân biệt cách diễn giải **quoted** và **unquoted** đối với NULL marker.

### 12.5. Chỉ áp dụng khi đã có contract rõ

Không bật FORCE_NULL/FORCE_NOT_NULL cho toàn bộ file một cách máy móc. Trước tiên phải quyết định:

- Một trường trống có nghĩa gì?
- `""` có nghĩa gì?
- Dữ liệu text có được phép chứa literal marker không?
- Cột số/ngày có được phép thiếu không?

### 12.6. Dùng staging text để giữ raw semantics

Khi nguồn dữ liệu không đáng tin hoặc thường thay đổi dialect, nhập vào các cột TEXT trong staging rồi chuẩn hóa rõ ràng sẽ an toàn hơn ép trực tiếp vào bảng production.

---

## 13. HEADER, HEADER MATCH và thứ tự cột

Một file CSV thường có header:

```csv
external_id,buyer,status,amount_text,order_time_text,note
E-1001,Nguyễn An,PAID,125000.50,2026-11-01T08:30:00+07:00,Đặt hàng
```

### 13.1. HEADER true

```sql
COPY app.stage_orders
FROM STDIN
WITH (
    FORMAT csv,
    HEADER true
);
```

Thông thường bỏ qua hàng header đầu tiên khi nhập CSV. Bản thân `HEADER true` không có nghĩa tự ánh xạ các trường theo tên trong file bất kể thứ tự.

### 13.2. Cần chỉ định danh sách cột

```sql
COPY app.stage_orders (
    external_id,
    buyer,
    status,
    amount_text,
    order_time_text,
    note
)
FROM STDIN
WITH (
    FORMAT csv,
    HEADER true
);
```

Danh sách cột cho biết **thứ tự dữ liệu sẽ đi vào cột nào**. Nếu file đổi vị trí hai cột mà importer không được cập nhật, nội dung có thể bị nạp sai dù header có tên đúng.

### 13.3. HEADER MATCH

Trên các phiên bản PostgreSQL hỗ trợ tùy chọn này, `HEADER MATCH` yêu cầu tên header phù hợp với các cột đích theo quy tắc COPY.

Ví dụ:

```sql
COPY app.stage_orders (
    external_id,
    buyer,
    status,
    amount_text,
    order_time_text,
    note
)
FROM STDIN
WITH (
    FORMAT csv,
    HEADER MATCH
);
```

**Không hiểu HEADER MATCH là tùy chọn tự reorder columns**; mục tiêu là kiểm tra header phù hợp với cột được COPY theo thứ tự kỳ vọng. Kiểm tra support trên phiên bản đang chạy.

### 13.4. Khi file có extra columns

Nếu schema export thêm cột, importer cần một hợp đồng mới hoặc bước transform trung gian. Không nên silently ignore dữ liệu bổ sung nếu nó có thể làm sai mapping.

### 13.5. Khi header có BOM

Nếu BOM xuất hiện trước tên cột đầu tiên, công cụ có thể hiểu tên cột đó bắt đầu bằng ký tự đặc biệt thay vì `external_id`. HEADER MATCH có thể báo không khớp. Tốt nhất chuẩn hóa encoding/BOM ở bước nhập trước khi kiểm tra header.

---

## 14. CSV và dấu xuống dòng CRLF/LF

Các nền tảng khác nhau thường dùng:

- **LF** (`\n`) trên Unix/Linux.
- **CRLF** (`\r\n`) trên nhiều file Windows.
- **CR** riêng lẻ trong dữ liệu cũ.

### 14.1. CSV parser phải phân biệt newline của record và newline trong field

Ví dụ:

```csv
id,note
1,"Đơn đầu
Giao sau 17h"
2,"Không có ghi chú"
```

Từ góc nhìn vật lý có nhiều lines, nhưng chỉ có **hai data records** sau header.

### 14.2. Không chạy replace newline bừa bãi

Thay tất cả `\r\n` thành `\n` trong file thường có thể hữu ích khi biết chắc encoding/format, nhưng nếu công cụ xử lý phá cấu trúc quote hoặc BOM, dữ liệu vẫn có thể hỏng. Với CSV, dùng parser đúng dialect.

### 14.3. Định nghĩa newline policy khi export

Nếu consumer yêu cầu CRLF, có thể dùng các công cụ kiểm soát newline ở client hoặc những tùy chọn COPY được phiên bản PostgreSQL hỗ trợ cho mục tiêu tương ứng. Tránh giả định mọi phiên bản COPY có cùng option điều khiển dòng mới.

### 14.4. Một record không nhất thiết bằng một lệnh readLine

Với lập trình Java, nên dùng CSV parser streaming biết quản lý trạng thái quote, không chỉ BufferedReader.readLine()+String.split().

---

## 15. Binary COPY: định dạng của PostgreSQL, không phải CSV mã hóa

`FORMAT binary` serialize dữ liệu bằng định dạng binary COPY của PostgreSQL.

Ví dụ:

```sql
COPY app.orders
TO STDOUT
WITH (FORMAT binary);
```

Hoặc qua `psql`:

```text
\copy app.orders TO './orders.copybin' WITH (FORMAT binary)
```

### 15.1. Không thể mở bằng text editor để đọc trực tiếp

Tệp chứa bytes, header/flags và biểu diễn field theo quy tắc binary COPY. Các ký tự tiếng Việt không “được nhìn thấy rõ” như CSV.

### 15.2. Mục đích chính

- Truyền dữ liệu hiệu quả giữa client hỗ trợ binary COPY protocol và PostgreSQL.
- Một số tác vụ bulk transfer giữa các hệ PostgreSQL tương thích.
- Tránh một phần công đoạn convert kiểu sang text rồi parse lại.

### 15.3. Không phải format trao đổi phổ quát

Phần mềm spreadsheet, công cụ BI hoặc một database engine khác thường không hiểu PostgreSQL binary COPY file.

### 15.4. Không phải lựa chọn backup dài hạn

Định dạng binary COPY có các giới hạn tương thích phiên bản, kiến trúc, type representation và schema. Để backup/restore PostgreSQL, dùng công cụ chính thức như `pg_dump/pg_restore` hoặc physical backup phù hợp, không dùng binary COPY như bản sao đầy đủ có thể khôi phục toàn database.

### 15.5. Không bảo đảm nhanh nhất

Hiệu quả phụ thuộc CPU conversion, type mix, network, buffer, constraints, WAL và hardware. Binary có thể không cải thiện đáng kể khi bottleneck chủ yếu là index maintenance hoặc disk I/O.

---

## 16. Binary COPY: cấu trúc mức khái niệm

Ở mức khái quát, một binary COPY stream gồm:

```text
File signature / header
      |
      v
Format flags / extension area
      |
      v
Record 1:
    field count
    field 1 length + bytes
    field 2 length + bytes
    ...
      |
      v
Record 2 ...
      |
      v
End marker
```

Giá trị NULL có biểu diễn riêng, không dựa vào chuỗi ký tự `\N` hay trường CSV trống.

### 16.1. Format phụ thuộc binary send/receive của kiểu

Hai cột có cùng số bytes khi in text không nhất thiết có cùng biểu diễn binary. Binary COPY truyền dữ liệu theo các send/receive routines tương ứng với kiểu PostgreSQL.

### 16.2. Phải tương thích số cột và thứ tự

Không tự thêm cột vào bảng đích rồi lấy một binary file cũ nạp theo thứ tự ngầm mà kỳ vọng PostgreSQL đoán lại schema.

### 16.3. Kiểu dữ liệu phải phù hợp

Cùng giá trị hiển thị `100` nhưng INTEGER, BIGINT và NUMERIC có binary representations khác nhau. Nhập binary bytes của một kiểu vào cột kiểu khác có thể lỗi hoặc bị diễn giải không đúng.

### 16.4. Không tự sửa bytes trong binary COPY file

Mở file bằng editor rồi sửa vài bytes là thao tác rủi ro; cần hiểu binary format và type encodings. Nếu cần chỉnh dữ liệu, dùng CSV/text có schema hoặc chỉnh trong PostgreSQL.

### 16.5. Cross-version compatibility

Không dựa vào binary COPY để trao đổi lâu dài qua nhiều PostgreSQL major versions hay kiến trúc khác nhau nếu chưa thử nghiệm. Với việc chuyển dữ liệu bền vững, nên dùng logical dump/CSV với schema contract, hoặc một hệ serialization có phiên bản rõ ràng.

---

## 17. Lựa chọn định dạng theo use case

| Trường hợp | Gợi ý | Lý do |
| --- | --- | --- |
| Gửi danh sách đơn cho đối tác | CSV UTF-8 + schema contract | Dễ trao đổi |
| Nạp CSV từ nhà cung cấp | CSV vào staging TEXT | Có thể kiểm tra và chuẩn hóa |
| Export cho Excel | CSV UTF-8, kiểm tra BOM/locale/formula injection | Phổ biến nhưng có rủi ro diễn giải |
| Pipeline đơn giản nội bộ PostgreSQL | Text hoặc CSV | Dễ debug |
| COPY qua driver PostgreSQL với schema cố định | Benchmark text/CSV/binary | Phụ thuộc workload |
| Backup toàn database | pg_dump/pg_restore hoặc physical backup | Giữ schema/metadata phù hợp |
| Replication HA | Streaming/WAL replication | Không phải CSV import |
| CDC sang Kafka/warehouse | Logical decoding/connector chuyên dụng | Contract dữ liệu/sự kiện riêng |
| File hàng trăm triệu rows cần kiểm tra | CSV streaming + staging/chunking | Cân bằng throughput và observability |
| Dữ liệu nhiều nested JSON, binary blobs | Có thể cân nhắc JSON/Parquet/Avro ở tầng trao đổi | COPY CSV không phải giải pháp tối ưu cho mọi cấu trúc |

**Chọn theo consumer và contract trước, benchmark throughput sau.**

---

## 18. Encoding là gì?

**Character encoding** ánh xạ ký tự sang bytes.

Cùng một tên tiếng Việt có thể được biểu diễn bằng những chuỗi bytes khác nhau tùy encoding. Nếu decoder dùng sai encoding, dữ liệu có thể:

- Bị báo lỗi invalid byte sequence.
- Bị thay ký tự thành dấu hỏi hoặc ký tự thay thế.
- Bị “mojibake”: vẫn là text hợp lệ nhưng nhìn rác.
- Bị mất thông tin không thể phục hồi đầy đủ sau khi lưu sai.

### 18.1. Unicode và UTF-8

Unicode định nghĩa các ký tự/code points. UTF-8 là một cách encoding Unicode sang bytes, phổ biến trên web, hệ thống hiện đại và PostgreSQL databases.

### 18.2. UTF-16 không phải UTF-8

Một file có thể chứa Unicode nhưng được mã hóa UTF-16 little-endian/big-endian. Nếu đưa thẳng file đó vào COPY với encoding UTF8, parser có thể gặp NUL bytes/byte sequences không phù hợp.

### 18.3. Legacy encodings

Một nguồn cũ có thể dùng LATIN1, WIN1252 hoặc một mã hóa khác. Cần biết chính xác nguồn, không đoán chỉ vì file được tạo trên Windows.

### 18.4. UTF-8 là khuyến nghị mặc định cho hệ thống mới

Với nội dung tiếng Việt, Unicode UTF-8 giúp giữ chữ có dấu và giảm sự phụ thuộc code pages của máy dùng.

### 18.5. Encoding không quyết định delimiter

Một CSV UTF-8 vẫn có thể dùng dấu phẩy, dấu chấm phẩy hoặc tab làm delimiter. Encoding là cách bytes biểu diễn ký tự; format quyết định cách ký tự được tổ chức thành trường/hàng.

---

## 19. server_encoding và client_encoding

PostgreSQL có hai khái niệm cốt lõi:

- **`server_encoding`**: mã hóa ký tự của database lưu trữ dữ liệu.
- **`client_encoding`**: mã hóa dùng để giao tiếp giữa client và PostgreSQL trong giao thức text theo ngữ cảnh phù hợp.

Xem:

```sql
SHOW server_encoding;
SHOW client_encoding;
```

Hoặc:

```sql
SELECT
    current_setting('server_encoding') AS server_encoding,
    current_setting('client_encoding') AS client_encoding;
```

### 19.1. Hai giá trị có thể khác nhau

Ví dụ database UTF8 nhưng client giao tiếp bằng WIN1252/LATIN1 ở những tổ hợp được PostgreSQL hỗ trợ và dữ liệu có thể chuyển đổi.

### 19.2. PostgreSQL có thể chuyển đổi ký tự

Trong các đường truyền hỗ trợ encoding conversion, PostgreSQL chuyển giữa client encoding và server encoding. Không có nghĩa mọi ký tự Unicode có thể biểu diễn trong mọi legacy encoding.

### 19.3. Nếu ký tự không tồn tại trong encoding đích

Khi xuất Unicode sang encoding hạn chế, PostgreSQL có thể báo lỗi vì ký tự không có biểu diễn tương ứng. Đây là hành vi tốt hơn thay dữ liệu bằng ký tự sai mà không báo.

### 19.4. server_encoding không nên thay tùy tiện

Mã hóa của database được quyết định khi tạo database theo các quy tắc PostgreSQL. Không dùng một câu SET đơn giản để “chuyển server_encoding của bảng” khi đang có dữ liệu.

### 19.5. client_encoding ảnh hưởng cách bytes được hiểu

Nếu file UTF-8 nhưng COPY lại đọc theo client encoding khác mà không có chỉ định phù hợp, một số bytes có thể bị giải mã sai. Vì thế phải kiểm tra cả file bytes lẫn cấu hình giao tiếp.

---

## 20. COPY ENCODING option

COPY có tùy chọn khai báo encoding của dữ liệu text/CSV:

```sql
COPY app.some_table
FROM '/server/path/data.csv'
WITH (
    FORMAT csv,
    HEADER true,
    ENCODING 'UTF8'
);
```

Tùy chọn này làm rõ encoding của dữ liệu nguồn trong ngữ cảnh được PostgreSQL hỗ trợ.

### 20.1. Khi không chỉ định ENCODING

COPY dùng các quy tắc mặc định về encoding, có liên quan đến `client_encoding` trong những đường copy tương ứng, ngay cả khi file được PostgreSQL server đọc trực tiếp.

### 20.2. ENCODING không thay format

`ENCODING 'UTF8'` không biến file UTF-16 thành UTF-8 theo phép thuật và cũng không sửa CSV sai dấu quote. Nó xác định cách decode/encode bytes ở luồng phù hợp.

### 20.3. Lựa chọn rõ ràng giúp tái lập

Trong batch production, ghi rõ:

```sql
WITH (
    FORMAT csv,
    HEADER true,
    ENCODING 'UTF8'
)
```

có thể giúp tránh phụ thuộc settings ngoài ý muốn khi dùng phiên bản PostgreSQL hỗ trợ. Nhưng với `\copy` qua psql, cần xét cả quá trình psql đọc bytes, client/session encoding và đường truyền.

### 20.4. Binary format không phải “CSV chọn encoding khác”

Với binary COPY, nội dung là biểu diễn nhị phân kiểu PostgreSQL, không phải một dòng ký tự được chọn mã hóa UTF-8 hay LATIN1 như text/CSV. Không dựa vào ENCODING để chuyển đổi nội dung binary kiểu dữ liệu.

---

## 21. psql \encoding và SET client_encoding

Trong `psql`, có thể xem/đổi client encoding qua:

```text
\encoding
\encoding UTF8
```

Trong SQL session:

```sql
SET client_encoding TO 'UTF8';
SHOW client_encoding;
```

### 21.1. Thực hành với nguồn CSV UTF-8

Nếu file đã được xác nhận UTF-8 và client/driver sử dụng cùng encoding, luồng COPY dễ đoán hơn.

### 21.2. Đừng SET dựa trên phỏng đoán

Một file CP1252 sẽ không trở thành UTF-8 chỉ vì bạn chạy `SET client_encoding='UTF8'`. Bạn đang yêu cầu decoder đọc bytes như UTF-8; điều đó có thể tạo lỗi hoặc dữ liệu hỏng.

### 21.3. Path không quyết định encoding

Tên file `orders-utf8.csv` chỉ là nhãn. Encoding phải được xác nhận từ hệ thống tạo file, metadata đáng tin hoặc phép kiểm tra phù hợp; extension `.csv` không cho biết encoding.

### 21.4. Terminal font không phải database encoding

Nếu ký tự hiển thị sai trong terminal nhưng bytes/file/database đúng, lỗi có thể là font/terminal locale chứ không phải dữ liệu trong PostgreSQL. Phải phân biệt display issue với stored-data corruption.

### 21.5. Không bật client_encoding SQL_ASCII làm cách chữa lỗi

SQL_ASCII có những semantics đặc biệt về byte validation/conversion. Dùng nó để “cho qua” dữ liệu không rõ encoding có thể che mất sai lệch và khiến xử lý Unicode sau này khó khăn. Với hệ thống mới nên ưu tiên UTF8.

---

## 22. BOM: byte order mark và CSV UTF-8

**BOM** là một chuỗi bytes đặc biệt đôi khi được ghi ở đầu file.

Một số encoding/chuẩn file dùng BOM để chỉ endian hoặc xác định encoding; với UTF-8, BOM không cần thiết nhưng một số công cụ tạo file vẫn thêm.

### 22.1. Vì sao BOM gây vấn đề?

Giả sử file header mong đợi:

```text
external_id,buyer,status
```

Nếu đầu file có BOM, parser hoặc chương trình đọc raw text có thể nhận ký tự đặc biệt trước `external_id`.

### 22.2. Với HEADER true

Nếu importer chỉ bỏ qua hàng header, BOM nằm ở hàng bị bỏ có thể ít tác động hơn; tuy nhiên không nên dựa vào sự trùng hợp này, đặc biệt khi file không có header hoặc cần HEADER MATCH.

### 22.3. Với HEADER MATCH

BOM không được xử lý đúng có thể khiến tên cột đầu khác chuỗi mong đợi, gây lỗi.

### 22.4. UTF-8 có BOM hay không?

- Với pipeline machine-to-machine: thường chọn **UTF-8 không BOM**.
- Với consumer spreadsheet đặc thù: có thể cần BOM hoặc một cách mở/import được chỉ định để phần mềm nhận đúng UTF-8.

Không có câu trả lời duy nhất nếu consumer có yêu cầu riêng.

### 22.5. Không tự xóa ba bytes đầu

Chỉ bỏ BOM nếu đã xác nhận đó thực sự là BOM phù hợp. Xóa ba bytes đầu của một file không BOM có thể làm mất phần đầu dữ liệu.

---

## 23. Tiếng Việt Unicode: dấu, normalization và mojibake

Dữ liệu tiếng Việt có các dấu và nhiều ký tự ngoài ASCII.

Ví dụ:

```text
Nguyễn
Đặng
Thảo
Hòa
Thành phố Hồ Chí Minh
```

### 23.1. UTF-8 lưu được tiếng Việt

Một database UTF8 lưu các chuỗi này theo encoding chuẩn khi client gửi bytes hợp lệ và đường chuyển đổi đúng.

### 23.2. Unicode normalization

Một ký tự hiển thị có thể được biểu diễn bằng một code point dựng sẵn hoặc kết hợp base character với combining marks. Hai chuỗi nhìn giống nhau chưa chắc có cùng byte sequence.

### 23.3. PostgreSQL không tự chuẩn hóa mọi dữ liệu đầu vào

Nếu pipeline yêu cầu canonical Unicode normalization để so khớp tên hoặc tìm kiếm, cần có chính sách rõ và công cụ phù hợp, thay vì tưởng COPY CSV sẽ tự xử lý.

### 23.4. Mojibake

Ví dụ một chuỗi UTF-8 bị đọc như một encoding khác có thể tạo kết quả rác. Sau khi chuỗi sai được lưu vào database dưới dạng UTF-8 hợp lệ, việc đổi `client_encoding` sau đó **không tự khôi phục** văn bản gốc.

### 23.5. Cách xử lý

- Xác định bytes nguồn gốc.
- Xác định encoding đúng của nguồn.
- Tạo bản sao dữ liệu trước khi sửa.
- Thực hiện chuyển đổi có kiểm chứng.
- So sánh round-trip với các trường tiếng Việt và ký tự đặc biệt.
- Tránh chuỗi encode/decode lại nhiều lần mà không biết trạng thái hiện tại.

---

## 24. Charset của file và kiểu TEXT/VARCHAR

Một hiểu nhầm phổ biến là cột `VARCHAR(255)` cần file ở một encoding riêng khác với cột `TEXT`. Trong PostgreSQL, TEXT/VARCHAR sử dụng encoding database cho các giá trị lưu trữ, không có “encoding cho từng cột text” như một thuộc tính độc lập thông thường.

### 24.1. VARCHAR(n) giới hạn độ dài logic

Giới hạn `VARCHAR(n)` liên quan số ký tự theo quy tắc PostgreSQL, không đơn giản là số bytes UTF-8.

### 24.2. Một ký tự có thể nhiều bytes

Trong UTF-8, nhiều ký tự tiếng Việt dùng nhiều hơn một byte. Vì vậy, dung lượng file không thể tính bằng số ký tự nhân một cho mọi ngôn ngữ.

### 24.3. CHAR(n) còn có padding semantics

Khi nhập từ CSV, kiểu `CHAR(n)` có hành vi padding và so sánh đặc thù. Không chọn kiểu này chỉ để “khớp độ rộng cột trong file”.

### 24.4. Không dùng BYTEA cho văn bản chỉ để tránh encoding

`BYTEA` phù hợp bytes thực sự (ảnh, tệp nhị phân, dữ liệu raw), nhưng nếu nội dung là tên/địa chỉ cần tìm kiếm/sắp xếp như text, hãy giải quyết encoding đúng thay vì chuyển toàn bộ vào BYTEA.

---

## 25. Lab: tạo schema thực hành

Ta xây dựng một pipeline nhận file đơn hàng từ nhà cung cấp.

**Ý tưởng:**

```text
supplier-orders.csv (UTF-8)
            |
            | psql \copy / COPY FROM STDIN
            v
copyfmt_lab.stage_orders (toàn bộ các cột TEXT)
            |
            | validation / cast / business mapping
            v
copyfmt_lab.orders (kiểu mạnh và constraints)
            |
            | COPY SELECT TO STDOUT
            v
orders-export.csv / text / binary
```

> **Cảnh báo:** Lệnh `DROP SCHEMA ... CASCADE` sẽ xóa toàn bộ objects trong schema lab. Chỉ chạy trên database thử nghiệm được phép reset. Không dùng schema này nếu đang chứa dữ liệu thật.

```sql
DROP SCHEMA IF EXISTS copyfmt_lab CASCADE;
CREATE SCHEMA copyfmt_lab;
```

### 25.1. Tạo bảng staging

```sql
CREATE TABLE copyfmt_lab.stage_orders (
    external_id TEXT,
    buyer TEXT,
    status TEXT,
    amount_text TEXT,
    order_time_text TEXT,
    note TEXT
);
```

Ta cố ý chọn TEXT cho mọi cột để dễ giữ raw input và ghi nhận lỗi định dạng.

### 25.2. Tạo bảng đích có kiểu dữ liệu

```sql
CREATE TABLE copyfmt_lab.orders (
    order_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    external_id TEXT NOT NULL UNIQUE,
    buyer TEXT NOT NULL CHECK (BTRIM(buyer) <> ''),
    status TEXT NOT NULL
        CHECK (status IN ('PENDING','PAID','CANCELED')),
    amount NUMERIC(12,2) NOT NULL CHECK (amount >= 0),
    ordered_at TIMESTAMPTZ NOT NULL,
    note TEXT,
    imported_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
);
```

### 25.3. Đích có những ràng buộc nào?

- UNIQUE external_id: chống duplicate external orders theo contract.
- buyer không trống sau khi trim.
- status thuộc một tập hợp xác định.
- amount >= 0 và được lưu NUMERIC(12,2).
- ordered_at là TIMESTAMPTZ.
- note được phép NULL hoặc empty string.

### 25.4. Staging không mặc định đáng tin

Một dòng nằm trong staging chưa có nghĩa đã hợp lệ về nghiệp vụ. Không để API trực tiếp dùng staging như bảng orders chính thức.

---

## 26. Lab: file CSV có dấu tiếng Việt, quote và newline

Tạo một file UTF-8 tên `supplier-orders.csv` với nội dung:

```csv
external_id,buyer,status,amount_text,order_time_text,note
E-1001,"Nguyễn An",PAID,125000.50,2026-11-01T08:30:00+07:00,"Mua bộ ""combo"", giao nhanh"
E-1002,"Lê Bình",PENDING,0,2026-11-01T09:05:00+07:00,"Địa chỉ: Quận 1, TP.HCM"
E-1003,"Trần Cẩm",PAID,89000,2026-11-02T12:00:00+07:00,"Dòng đầu
Dòng thứ hai"
E-1004,"Phạm Duy",CANCELED,50000,2026-11-03T10:00:00+07:00,""
E-1005,"Hà My",PAID,30000,2026-11-04T16:30:00+07:00,\N
```

**Quy ước của file này:**

- `FORMAT csv`.
- Delimiter dấu phẩy.
- Quote/escape là dấu nháy kép.
- Header ở dòng đầu.
- Encoding UTF-8.
- NULL marker là `\N` **không quote**.
- `""` là empty string.
- Các timestamp có timezone offset.
- NUMERIC dùng dấu chấm thập phân.

### 26.1. Tại sao có năm records nhưng nhiều hơn sáu physical lines?

Record E-1003 có trường `note` chứa newline bên trong dấu quote. Parser CSV đúng phải đọc trọn field trước khi kết thúc record.

### 26.2. Tại sao E-1004 và E-1005 khác nhau?

- E-1004 note = empty string.
- E-1005 note = NULL.

### 26.3. Tại sao amount_text là TEXT?

Để mọi row ban đầu được giữ đúng như file và có thể kiểm tra trước khi cast sang NUMERIC. Đối với file dễ thay đổi, đây là một cách tách ingest khỏi validation.

### 26.4. Cảnh báo khi copy ví dụ vào editor

Markdown hiển thị ký tự `\N` là backslash và chữ N. Hãy đảm bảo editor không tự thay escape, quote hoặc mã hóa khi tạo file thật.

---

## 27. Lab: nạp CSV bằng psql \copy

Sau khi đã tạo file local ở máy chạy `psql`, sử dụng:

```text
\encoding UTF8
\copy copyfmt_lab.stage_orders (external_id, buyer, status, amount_text, order_time_text, note) FROM './supplier-orders.csv' WITH (FORMAT csv, HEADER true, NULL '\N')
```

### 27.1. Lệnh này chạy ở đâu?

Đây là `psql` meta-command. Nếu bạn dùng một GUI database tool không hỗ trợ `\copy`, cần dùng tính năng import của GUI hoặc COPY protocol tương ứng.

### 27.2. Kiểm tra kết quả

```sql
SELECT
    external_id,
    buyer,
    status,
    amount_text,
    order_time_text,
    note,
    note IS NULL AS note_is_null,
    LENGTH(note) AS note_length
FROM copyfmt_lab.stage_orders
ORDER BY external_id;
```

Kỳ vọng:

- 5 logical rows.
- E-1003 có newline trong note.
- E-1004 có note length = 0.
- E-1005 có `note IS NULL = true`.

### 27.3. Không tải được file?

Phân biệt:

- “No such file”: psql không thấy file local đúng path.
- “Permission denied”: quyền OS/DB.
- “invalid byte sequence”: file encoding không khớp.
- “extra data after last expected column”: CSV delimiter/quote/header sai.
- “missing data for column”: record có thiếu fields.

### 27.4. Đừng sửa data bằng cách đổi encoding mò mẫm

Nếu có lỗi UTF-8, xác nhận nguồn file là UTF-8 rồi mới đổi settings/chuyển mã. Một lỗi quote không được sửa bằng ENCODING.

---

## 28. Lab: tự nhập CSV qua COPY FROM STDIN

Nếu không tạo file, trong một `psql` session có thể gửi dữ liệu thủ công:

```text
COPY copyfmt_lab.stage_orders (external_id, buyer, status, amount_text, order_time_text, note)
FROM STDIN WITH (FORMAT csv, HEADER true, NULL '\N');
external_id,buyer,status,amount_text,order_time_text,note
E-2001,"Ngô Thu",PAID,75000,2026-11-05T09:00:00+07:00,"Thử STDIN"
\.
```

Ở đây `\.` kết thúc dữ liệu STDIN trong ngữ cảnh psql.

### 28.1. Khác với SQL statement đơn thuần

Nếu gửi câu `COPY ... FROM STDIN` qua JDBC PreparedStatement thông thường mà không cấp COPY data stream qua driver API, bạn sẽ không tự động có dữ liệu để PostgreSQL đọc.

### 28.2. Với file lớn

Dùng `\copy FROM 'file'` hoặc COPY protocol streaming; đừng paste hàng triệu rows vào console.

### 28.3. Thử lại lab

Nếu bạn chạy cả ví dụ file và STDIN, bảng staging sẽ có thêm E-2001. Khi làm các phép đếm mẫu, hãy phân biệt tập năm dòng gốc với dòng thử thêm.

---

## 29. Lab: kiểm tra raw data trước khi cast

Có thể kiểm tra:

```sql
SELECT
    COUNT(*) AS rows_in_staging,
    COUNT(*) FILTER (WHERE external_id IS NULL) AS missing_id,
    COUNT(*) FILTER (WHERE buyer IS NULL OR BTRIM(buyer) = '')
        AS invalid_buyer,
    COUNT(*) FILTER (
        WHERE status NOT IN ('PENDING','PAID','CANCELED')
           OR status IS NULL
    ) AS invalid_status,
    COUNT(*) FILTER (WHERE note IS NULL) AS null_notes,
    COUNT(*) FILTER (WHERE note = '') AS empty_notes
FROM copyfmt_lab.stage_orders;
```

### 29.1. Vì sao kiểm tra số hàng trước?

Đếm logical rows giúp phát hiện file thiếu hoặc thừa records. Nhưng phải so với manifest/source report đáng tin, không chỉ dựa vào kỳ vọng đọc bằng mắt.

### 29.2. Không dùng DISTINCT để che duplicate

Nếu external_id trùng, `SELECT DISTINCT` có thể làm mất bản ghi khác nội dung. Cần có chính sách dedup/idempotency rõ.

### 29.3. Kiểm tra các trường bắt buộc

Nếu external_id hoặc buyer thiếu, tùy hợp đồng business bạn có thể reject row, bổ sung dữ liệu từ nguồn khác hoặc từ chối toàn batch; không tự điền một giá trị giả.

### 29.4. Kiểm tra locale number

Trong file đã thống nhất dấu chấm thập phân, có thể kiểm tra sơ bộ `amount_text` bằng một regular expression:

```sql
SELECT external_id, amount_text
FROM copyfmt_lab.stage_orders
WHERE amount_text IS NULL
   OR amount_text !~ '^[0-9]+([.][0-9]{1,2})?$';
```

Regex chỉ là **một lớp kiểm tra cú pháp của contract trong ví dụ**, không thay được cast/precision/scale và không phù hợp cho mọi định dạng tiền tệ.

### 29.5. Thời gian và Unicode cần kiểm tra riêng

Một timestamp parse được chưa chắc đúng timezone nghiệp vụ. Một chuỗi tiếng Việt hiển thị được chưa chắc đã được normalize Unicode theo contract.

---

## 30. Lab: chuyển staging sang bảng typed

Sau khi xác nhận dữ liệu gốc đúng contract, chuyển sang bảng đích:

```sql
BEGIN;

INSERT INTO copyfmt_lab.orders (
    external_id,
    buyer,
    status,
    amount,
    ordered_at,
    note
)
SELECT
    external_id,
    buyer,
    status,
    amount_text::NUMERIC(12,2),
    order_time_text::TIMESTAMPTZ,
    note
FROM copyfmt_lab.stage_orders
WHERE external_id LIKE 'E-100%'
ON CONFLICT (external_id) DO NOTHING;

SELECT
    external_id,
    buyer,
    amount,
    ordered_at,
    note,
    note IS NULL AS note_is_null
FROM copyfmt_lab.orders
ORDER BY external_id;

ROLLBACK;
```

### 30.1. Tại sao BEGIN/ROLLBACK?

Ví dụ cho phép quan sát kết quả trong transaction mà không giữ dữ liệu sau thử nghiệm. Khi thực sự nhập batch production, cần COMMIT theo quy trình được kiểm soát và lưu audit metadata.

### 30.2. Cast có thể thất bại

Nếu amount_text có `12,50` hoặc order_time_text có chuỗi ngày không hợp lệ, câu INSERT có thể thất bại. Đó là lý do staging và validation tách riêng.

### 30.3. ON CONFLICT DO NOTHING có ý nghĩa gì?

Với unique external_id, câu này bỏ qua row đã tồn tại. Nhưng nếu nguồn có bản ghi ID giống nhau mà amount khác, im lặng bỏ qua có thể che mất dữ liệu cần đối soát.

### 30.4. Chiến lược production

- Nạp vào staging theo batch_id/source_file.
- Validate và ghi rejected rows với mã lỗi.
- Dedup theo business key rõ.
- Chuyển đổi trong transaction.
- Kiểm tra số hàng accepted/rejected.
- COMMIT khi đạt chính sách chất lượng.
- Lưu manifest, checksum và thời gian nguồn.
- Chỉ sau COMMIT mới thông báo import thành công.

### 30.5. Không nhầm raw staging với nguồn sự thật

Staging nên có retention và bảo vệ PII theo chính sách, không trở thành một bảng public vì “chỉ là tệp nhập”.

---

## 31. Lab: export CSV đúng schema contract

Nếu bảng đích đã có dữ liệu được COMMIT, có thể xuất:

```text
\copy (SELECT external_id, buyer, status, amount, ordered_at, note FROM copyfmt_lab.orders ORDER BY external_id) TO './orders-export.csv' WITH (FORMAT csv, HEADER true, NULL '\N')
```

### 31.1. Thứ tự cột có chủ đích

Không dùng `SELECT *` cho contract trao đổi lâu dài. Thêm cột mới vào bảng sẽ thay output nếu phụ thuộc SELECT *.

### 31.2. ORDER BY có cần?

COPY query không tự bảo đảm thứ tự kết quả nếu SELECT không ORDER BY. Với dữ liệu snapshot đối soát cần kết quả có thứ tự ổn định, ORDER BY theo khóa tường minh giúp dễ diff.

### 31.3. Mã hóa

Xác nhận file UTF-8 qua `\encoding UTF8`/session settings và quy trình tạo file. Nếu sử dụng SQL COPY và phiên bản hỗ trợ, có thể chỉ định ENCODING 'UTF8'.

### 31.4. NULL marker

Dùng `NULL '\N'` đồng bộ với importer của ví dụ, thay vì dựa vào default CSV empty marker.

### 31.5. Dữ liệu nhạy cảm

Không export unit cost, PII hoặc thông tin nội bộ chỉ vì source table có cột đó. Chọn đúng columns và role đọc phù hợp.

---

## 32. Lab: export text và binary để so sánh

### 32.1. Xuất text

```text
\copy (SELECT external_id, buyer, amount FROM copyfmt_lab.orders ORDER BY external_id) TO './orders-export.txt' WITH (FORMAT text)
```

### 32.2. Xuất binary

```text
\copy (SELECT external_id, buyer, amount FROM copyfmt_lab.orders ORDER BY external_id) TO './orders-export.copybin' WITH (FORMAT binary)
```

### 32.3. So sánh file

- File text có thể đọc bằng editor nhưng phải hiểu tab/backslash escapes.
- File binary không nên đọc như text.
- File CSV có header và quoting; thuận tiện cho consumer ngoài PostgreSQL.
- Kiểm tra kích thước bytes nhưng không suy từ kích thước file rằng truy vấn/ingest nhanh hơn.

### 32.4. Nhập lại binary có điều kiện

Một tệp binary COPY chỉ có thể nạp lại vào đối tượng có danh sách cột và kiểu tương ứng theo binary format được hỗ trợ:

```text
\copy copyfmt_lab.binary_target (external_id, buyer, amount) FROM './orders-export.copybin' WITH (FORMAT binary)
```

Bảng `binary_target` trong ví dụ là **placeholder**: phải tạo bảng có kiểu/column order tương thích trước khi chạy. Không dùng nhầm bảng stage_orders với tất cả cột TEXT nếu binary source có NUMERIC.

### 32.5. Không benchmark bằng file rỗng

Muốn đo FORMAT text/csv/binary, phải có dữ liệu đích thật và chạy query trong điều kiện thống nhất. Nếu chưa COMMIT từ lab trước, bảng orders có thể rỗng.

---

## 33. Một phép thử round-trip

Giả sử dữ liệu ban đầu có các trường:

```text
NULL
empty string
text with comma
text with "double quote"
text with tab
text with newline
text with backslash
Vietnamese characters
emoji
UTC timestamp
NUMERIC decimal
```

Một test đúng cần:

1. Tạo dữ liệu gốc trong PostgreSQL hoặc file nguồn đã biết.
2. Export bằng format/encoding được chỉ định.
3. Import vào bảng mới có schema tương ứng.
4. So sánh bằng SQL với semantics phù hợp.
5. Đảm bảo NULL vẫn NULL, empty vẫn empty.
6. Kiểm tra lengths, ký tự và dấu.
7. Kiểm tra timestamp là cùng instant, không chỉ cùng chuỗi hiển thị.
8. Kiểm tra numeric không mất precision.
9. Kiểm tra số record.
10. Kiểm tra file checksum nếu mục tiêu là truyền bytes nguyên vẹn.

### 33.1. Dữ liệu NULL/empty

```sql
SELECT
    COUNT(*) FILTER (WHERE note IS NULL) AS null_count,
    COUNT(*) FILTER (WHERE note = '') AS empty_count
FROM copyfmt_lab.orders;
```

### 33.2. Hash không thay semantic equality

Hai file có checksum khác nhau có thể chứa cùng dữ liệu nhưng khác newline/quote/order. Ngược lại, cùng checksum chỉ chứng minh bytes giống nhau, không chứng minh mapping vào table đúng kiểu.

### 33.3. So sánh bảng

Với cùng schema và khóa unique, có thể dùng FULL OUTER JOIN theo business key để kiểm tra missing/mismatched rows. Cẩn thận khi so sánh NULL:

```sql
a.note IS DISTINCT FROM b.note
```

là cách so sánh có semantics rõ với NULL.

---

## 34. COPY và quyền truy cập

### 34.1. COPY FROM table

Role cần các quyền thích hợp để INSERT vào table/cột được target, cùng schema access theo quy tắc PostgreSQL.

### 34.2. COPY TO table/query

Role cần quyền SELECT tương ứng, giống như một truy vấn đọc dữ liệu phù hợp.

### 34.3. COPY server-side file

Đọc/ghi file server cần đặc quyền phù hợp và OS permissions; đây là một trust boundary nhạy cảm. Không cấp role file-level chỉ vì một worker cần import.

### 34.4. \copy client-side

`psql \copy` có thể tránh nhu cầu cấp quyền read/write filesystem phía server, nhưng role SQL vẫn cần SELECT/INSERT phù hợp trên bảng.

### 34.5. COPY TO có thể làm lộ nhiều dữ liệu

Một role có quyền SELECT bảng nhạy cảm có thể xuất toàn bộ table qua COPY TO STDOUT. COPY không phải lỗ hổng tự thân; đây là hậu quả của SELECT grant quá rộng. Cần least privilege và data egress controls.

### 34.6. Quyền ở file system client

Dù server chỉ gửi kết quả, file xuất nằm trên máy psql hoặc application. Ai được phép đọc file đó? File có cần mã hóa, retention, audit hay xóa sau xử lý? Database grants không kiểm soát được mọi bản sao bên ngoài.

---

## 35. COPY và Row-Level Security (RLS)

RLS có ý nghĩa đặc biệt với bulk operations.

### 35.1. COPY FROM với bảng có RLS

PostgreSQL tài liệu hóa rằng `COPY FROM` **không hỗ trợ nhập trực tiếp vào bảng có RLS** trong các ngữ cảnh tương ứng; nếu cần nạp dữ liệu và áp dụng policies, có thể cần dùng câu `INSERT` hoặc kiến trúc staging/privileged controlled import phù hợp.

Không giả định một COPY FROM do role bị RLS giới hạn sẽ tự kiểm tra policies giống mọi INSERT thông thường.

### 35.2. COPY TO và RLS

Khi COPY TO đọc dữ liệu theo cơ chế SQL phù hợp, chính sách RLS có thể giới hạn những hàng xuất ra theo quyền role và object. Nhưng role là table owner, superuser hoặc có BYPASSRLS có những quy tắc đặc biệt.

### 35.3. Tại sao staging có ích?

Một import service có thể nạp vào staging trong schema chuyên dụng, validate và chuyển vào bảng tenant theo đường DML được kiểm soát. Cần rõ role nào có quyền chuyển dữ liệu và constraints/policies được thực thi ở bước nào.

### 35.4. Đừng dùng account owner để lách RLS mà quên scope

Nếu importer chạy dưới owner bypass RLS, có thể nhập dữ liệu vượt tenant policy. Điều này có thể cần cho ETL đặc biệt nhưng phải được kiểm soát theo quy trình, chứ không phải mặc định của API.

### 35.5. Test bằng role thật

Không chỉ thử COPY từ superuser rồi kết luận mọi role application có cùng permissions.

---

## 36. COPY và constraints, triggers, indexes

### 36.1. Constraints vẫn quan trọng

Khi COPY FROM nhập vào bảng typed, PostgreSQL kiểm tra nhiều ràng buộc như NOT NULL, CHECK, UNIQUE/PK, FK theo cơ chế tương ứng.

### 36.2. Triggers

COPY FROM có thể kích hoạt triggers trên bảng đích theo quy tắc PostgreSQL. Điều này có thể tạo side effects hoặc làm chậm bulk load. Không dựa vào câu “COPY bỏ qua mọi triggers”.

### 36.3. Index maintenance

COPY nạp vào bảng có indexes phải duy trì các indexes. Nhiều indexes lớn có thể giảm throughput nạp. Trong một số workflow rebuild/reload được kiểm soát, người vận hành có thể nạp dữ liệu trước rồi xây index sau, nhưng phải cân nhắc downtime/constraints/availability và tính toàn vẹn.

### 36.4. GENERATED và identity columns

PostgreSQL có quy tắc về generated/identity columns khi COPY FROM. Ví dụ, COPY FROM có thể sử dụng giá trị identity được cung cấp trong input thay vì luôn tự sinh theo default trong các trường hợp hỗ trợ. Vì vậy phải xác định rõ danh sách cột và contract, không nạp identity tùy tiện vào bảng production.

### 36.5. Trigger/constraint không thay validation nguồn

Một chuỗi ngày parse hợp lệ nhưng business day sai, hoặc amount đúng NUMERIC nhưng sai đơn vị tiền tệ, có thể vượt qua constraints thông thường. Cần kiểm tra nghiệp vụ ở tầng staging.

---

## 37. Transaction semantics khi COPY FROM lỗi

Một COPY FROM thường là một SQL statement trong transaction. Nếu COPY thất bại vì dữ liệu sai hoặc constraint, statement không được commit thành công.

### 37.1. Ví dụ lỗi

```csv
external_id,buyer,status,amount,ordered_at
E-01,An,PAID,100,2026-11-01T08:00:00+07:00
E-02,Bình,PAID,not-a-number,2026-11-01T08:10:00+07:00
```

Nếu nhập trực tiếp vào cột NUMERIC, record E-02 sẽ gây lỗi chuyển kiểu.

### 37.2. Không có trạng thái “nhập thành công một nửa” cho statement bị hủy

Các thay đổi của statement COPY bị hủy không được commit như một nửa transaction. Tuy nhiên, các tuple đã được ghi vật lý trước lúc gặp lỗi có thể để lại dead space và cần VACUUM/maintenance thích hợp để thu hồi; điều đó không làm chúng trở thành dữ liệu hợp lệ có thể đọc.

### 37.3. Transaction lớn có ảnh hưởng WAL/storage

Một import rất lớn có thể tạo WAL và bloat/locks, gây áp lực I/O, replication lag hoặc dung lượng. Cần thiết kế batch/transaction scope và giám sát.

### 37.4. Nhiều COPY statements trong cùng transaction

Nếu một batch được chia thành nhiều COPY statements bên trong một transaction, toàn transaction vẫn phụ thuộc COMMIT cuối cùng. Nếu mỗi chunk commit riêng, các chunk trước đã commit sẽ không tự rollback khi chunk sau thất bại.

### 37.5. Lựa chọn all-or-nothing hoặc partial acceptance

- **All-or-nothing:** phù hợp dữ liệu phải nhất quán theo batch.
- **Partial acceptance:** cần bảng rejected rows/accepted rows và hợp đồng nghiệp vụ rõ; không phải cứ import lỗi là âm thầm bỏ qua.

---

## 38. Xử lý lỗi khi nạp: staging và chính sách reject

Một số phiên bản PostgreSQL mới có tùy chọn COPY để bỏ qua một số lỗi chuyển đổi trên từng hàng trong các định dạng phù hợp. Nhưng phạm vi hỗ trợ và loại lỗi được bỏ qua phụ thuộc phiên bản và tùy chọn. Không xem đó là cơ chế tự động “bỏ qua mọi constraint error”.

### 38.1. Mẫu ổn định

1. Nạp raw bytes/text vào staging có schema rõ.
2. Kiểm tra số hàng và file manifest.
3. Validate columns và business key.
4. Chuyển từng tập accepted vào bảng typed.
5. Ghi rejected data và reason.
6. Quyết định commit/rollback theo SLA.
7. Phát thống kê accepted/rejected.
8. Quản lý retry/idempotency.

### 38.2. Nếu dùng ON_ERROR trên phiên bản có hỗ trợ

Các tùy chọn như `ON_ERROR ignore` có thể có trên PostgreSQL mới với phạm vi định dạng phù hợp. Phải kiểm tra tài liệu phiên bản trước khi sử dụng và hiểu những lỗi nào được bỏ qua, những lỗi nào vẫn làm toàn statement thất bại.

### 38.3. Không mất record lỗi

Nếu nghiệp vụ yêu cầu điều tra đầy đủ, một số record bị bỏ qua phải có dấu vết. Đừng chỉ nhận câu “COPY hoàn tất” rồi quên số hàng thực nhập.

### 38.4. Quan sát lỗi có cấu trúc

Ghi source_file, batch_id, row_number/logical record identifier, column, error_code và sample redacted. Không lưu nguyên token/PII/secret vào logs nếu không cần.

### 38.5. Không parse message bất ổn làm hợp đồng

Với lỗi từ PostgreSQL, SQLSTATE và các error fields hữu ích cho phân loại; không dựa vào chuỗi thông điệp có thể thay đổi theo phiên bản và ngôn ngữ.

---

## 39. Hiệu năng: text, CSV hay binary nhanh hơn?

Không có thứ tự cố định cho mọi workload.

### 39.1. Chi phí text

- Format/parse giá trị thành ký tự.
- Escape delimiter/backslash.
- Chuyển encoding khi cần.

### 39.2. Chi phí CSV

- Quote/escape fields.
- Tìm delimiter và xử lý multiline fields.
- Chuyển kiểu giá trị sau khi parse.

### 39.3. Chi phí binary

- Serialize/deserialize theo binary type routines.
- Định dạng file không mang overhead ký tự quote/delimiter.
- Không tương thích rộng với tool khác, schema khắt khe hơn.

### 39.4. Bottlenecks khác format

- Network latency/bandwidth.
- WAL generation.
- Index maintenance.
- FK/trigger checks.
- Disk throughput.
- Autovacuum/dirty buffers.
- Replication lag.
- Transaction length.
- CPU conversion.
- Client buffering/streaming.

### 39.5. Kích thước file không bằng thời gian tải

Binary có thể nhỏ hơn hoặc lớn hơn CSV tùy types/values. Một file nhỏ hơn chưa chắc import nhanh hơn nếu có nhiều indexes hoặc network không phải bottleneck.

### 39.6. Benchmark đúng cách

- Cùng dữ liệu và schema.
- Cùng indexes/constraints.
- Cùng transaction strategy.
- Cùng server/client/network.
- Nhiều lần đo.
- Cần warm-up và phân biệt cache nóng/lạnh.
- Đo throughput rows/s, MB/s, CPU, WAL bytes, latency và replication lag.
- Kiểm tra round-trip correctness trước khi so tốc độ.

---

## 40. Tối ưu import lớn an toàn

### 40.1. Dùng COPY thay hàng triệu INSERT nhỏ

Trong nhiều tình huống bulk ingest, COPY sẽ giảm overhead so với mỗi hàng là một INSERT riêng qua network.

### 40.2. Chỉ nạp các cột cần thiết

```sql
COPY app.orders (external_id, buyer, amount)
FROM STDIN
WITH (FORMAT csv);
```

Những cột không có trong danh sách COPY sẽ nhận default hoặc NULL theo schema/constraints, tùy trường hợp.

### 40.3. Staging để tách raw và typed

Nếu dữ liệu nguồn thường xuyên lỗi, staging giúp tránh COPY trực tiếp vào bảng nghiệp vụ quan trọng và cho phép kiểm tra trước.

### 40.4. Chunk theo mục tiêu vận hành

Rất nhiều rows trong một transaction có thể làm tăng thời gian giữ lock/tài nguyên và khó rollback khi cuối batch lỗi. Chia chunks có thể giúp observability/retry nhưng cũng tạo vấn đề partial commits và idempotency.

### 40.5. Kiểm soát indexes

Index giúp query nhưng tăng chi phí ghi. Với initial load lớn trên bảng mới, có thể cân nhắc kế hoạch tạo index sau bulk load. Trên bảng đang phục vụ production, không được drop indexes/constraints tùy tiện chỉ để tăng tốc.

### 40.6. ANALYZE sau bulk load

Sau khi nạp lượng lớn dữ liệu:

```sql
ANALYZE copyfmt_lab.orders;
```

giúp planner có thống kê phù hợp hơn. Autovacuum/autoanalyze có thể xử lý trong nhiều hệ thống, nhưng job nạp lớn đôi khi cần phối hợp timing với query workload.

---

## 41. WAL, replication và import

COPY FROM là thao tác ghi dữ liệu PostgreSQL, vì thế thường tạo WAL theo durability/configuration của bảng/cluster và có thể ảnh hưởng sao chép.

### 41.1. Không nghĩ COPY “bỏ qua WAL”

Copy dữ liệu vào bảng logged thông thường chịu cơ chế WAL của PostgreSQL. Những ngoại lệ tối ưu liên quan chế độ hoặc loại bảng có điều kiện riêng, không phải mặc định bỏ WAL.

### 41.2. Replication lag

Bulk load có thể làm standby/consumer trễ nếu write volume lớn hoặc apply chậm. Theo dõi WAL và replication metrics trước, trong và sau batch.

### 41.3. UNLOGGED tables

Một staging table UNLOGGED có thể giảm WAL ở một số trường hợp, nhưng dữ liệu có những giới hạn về crash recovery và physical replication. Không chọn UNLOGGED cho dữ liệu cần bền vững chỉ vì import nhanh hơn.

### 41.4. COPY FREEZE

PostgreSQL có tùy chọn `FREEZE` trong những điều kiện cụ thể, chẳng hạn bảng được tạo/truncate trong transaction phù hợp và các điều kiện snapshot; có nhiều giới hạn. Đây là tối ưu chuyên biệt, **không** bật đại trà trên bảng production hoặc dùng để “bỏ qua VACUUM mãi mãi”.

### 41.5. Durability là quyết định nghiệp vụ

Không đặt `synchronous_commit = off`, dùng UNLOGGED hoặc chỉnh fsync chỉ vì một benchmark nếu không hiểu khả năng mất dữ liệu sau crash và yêu cầu recovery.

---

## 42. CSV injection khi file được mở bằng spreadsheet

Đây là rủi ro an toàn thông tin quan trọng khi export CSV.

Một trường text do người dùng kiểm soát có thể bắt đầu bằng:

```text
=SUM(1,2)
+1+2
-1+2
@some_expression
```

Một số phần mềm spreadsheet có thể diễn giải các chuỗi này như công thức thay vì text thuần, tùy phiên bản/cấu hình/cách mở file.

### 42.1. COPY chỉ serialize dữ liệu

PostgreSQL COPY CSV đảm bảo quoting theo CSV dialect, **không mặc nhiên đảm bảo spreadsheet sẽ xem mọi cell là dữ liệu text vô hại**.

### 42.2. CSV quote không đủ ngăn formula execution

Bao một trường trong dấu nháy kép CSV không có nghĩa phần mềm spreadsheet sẽ không diễn giải phần nội dung như công thức.

### 42.3. Chính sách export an toàn

Nếu người dùng cuối mở file bằng spreadsheet, cần thiết kế một output format/method an toàn:

- Chọn định dạng có phân loại ô là text khi có thể.
- Neutralize các giá trị không đáng tin theo yêu cầu bảo mật của phần mềm consumer.
- Kiểm thử với ứng dụng spreadsheet thật và dữ liệu adversarial.
- Ghi rõ tác động khi escape/prefix ký tự vào giá trị.
- Không biến đổi dữ liệu âm thầm nếu file được dùng cho round-trip máy–máy.

### 42.4. Tách hai hợp đồng export

Một file CSV phục vụ **machine ingestion** có thể cần bảo toàn byte/giá trị chính xác. Một file phục vụ **người mở bằng spreadsheet** có thể cần lớp biến đổi riêng để không kích hoạt công thức.

---

## 43. Lựa chọn số, tiền và thời gian trong file xuất

### 43.1. Số thập phân

Với dữ liệu tiền tệ:

```text
125000.50
```

là dạng văn bản thuận tiện cho PostgreSQL NUMERIC. Không thêm dấu ngăn cách hàng nghìn tùy locale nếu importer không có contract.

### 43.2. Không dùng FLOAT cho tiền chỉ để file nhỏ

Nếu hệ thống dùng `NUMERIC(12,2)` vì cần chính xác đến cent/đồng theo policy, một bước export/import không nên chuyển qua floating point không kiểm soát.

### 43.3. Timestamp với timezone

Ví dụ:

```text
2026-11-01T08:30:00+07:00
```

mô tả một thời điểm rõ hơn chuỗi không offset. Với TIMESTAMPTZ, PostgreSQL lưu instant theo semantics kiểu dữ liệu; cách hiển thị khi export còn chịu timezone/session formatting.

### 43.4. DateStyle

Khi dùng các chuỗi ngày không phải ISO rõ ràng, cài đặt `DateStyle` có thể ảnh hưởng cách parse/hiển thị. Đối với export portable, nên chọn định dạng ISO rõ ràng.

### 43.5. Dữ liệu boolean

PostgreSQL chấp nhận một số dạng boolean input, nhưng contract export nên chọn một dạng ổn định như `true/false`, không nhờ consumer tự hiểu `Y/N` hay `1/0` nếu chưa thống nhất.

### 43.6. Locale của spreadsheet

Nếu một ứng dụng spreadsheet mở CSV dùng dấu phẩy làm delimiter nhưng cũng dùng dấu phẩy làm thập phân, có thể có hành vi nhập số khác mong đợi. Đây là lý do cần hướng dẫn import cho consumer và không xem CSV là self-describing.

---

## 44. Encoding và conversion khi hệ thống nguồn dùng mã cũ

Giả sử nhà cung cấp gửi file với encoding WIN1252.

### 44.1. Xác minh nguồn

Cần có metadata hoặc cam kết của nhà cung cấp. Không đoán WIN1252 chỉ vì file có extension CSV.

### 44.2. Chuyển mã trước khi nạp

Có thể dùng một công cụ conversion phù hợp để chuyển file sang UTF-8, sau đó kiểm tra bằng các mẫu dữ liệu có ký tự ngoài ASCII. Trong ứng dụng Java, dùng decoder charset tương ứng và encoder UTF-8 theo pipeline streaming có kiểm soát.

### 44.3. Không thay bytes rồi giữ nhãn cũ

Một file đã chuyển UTF-8 nhưng producer vẫn báo WIN1252 sẽ gây lỗi ở consumer tiếp theo. Metadata phải đi cùng bytes thật.

### 44.4. Conversion không sửa sai logic

Nếu số `1,25` cần thành `1.25`, đó là **normalization dữ liệu**, không phải chuyển encoding. Tương tự, đổi từ local timestamp sang UTC không phải encoding conversion.

### 44.5. Đối với dữ liệu tiếng Việt legacy

Một số hệ thống cũ có các bảng mã hoặc quy tắc lưu chữ Việt không tương đương charset chuyển đổi đơn giản. Cần tài liệu nguồn và bộ mapping đáng tin, tránh chuyển đổi tùy ý.

### 44.6. Kiểm tra canary strings

Một file test nên có:

```text
Đặng Thị Hạnh
Nguyễn Ánh
Trần Quốc Bảo
Tôi đến Thành phố Hồ Chí Minh.
```

để đối chiếu trước/sau conversion và tránh chỉ thử dữ liệu ASCII vốn có thể trông đúng trong nhiều encodings.

---

## 45. Java/JDBC: streaming COPY thay vì gửi \copy

Trong Java, `\copy` không phải câu SQL trực tiếp để đưa vào `PreparedStatement`. PostgreSQL JDBC driver có API chuyên dụng cho COPY protocol.

Ví dụ dùng các lớp của PostgreSQL JDBC driver (đây là ví dụ minh họa, cần thêm dependency pgjdbc phù hợp):

```java
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.sql.Connection;
import org.postgresql.PGConnection;
import org.postgresql.copy.CopyManager;

public class CopyImportExample {
    public static long importCsv(
            Connection connection,
            Path file
    ) throws Exception {
        CopyManager manager = connection
                .unwrap(PGConnection.class)
                .getCopyAPI();

        String sql = """
            COPY copyfmt_lab.stage_orders
                (external_id, buyer, status,
                 amount_text, order_time_text, note)
            FROM STDIN
            WITH (
                FORMAT csv,
                HEADER true,
                NULL '\\N'
            )
            """;

        try (InputStream in = Files.newInputStream(file)) {
            return manager.copyIn(sql, in);
        }
    }
}
```

### 45.1. Vì sao dùng InputStream?

Driver có thể truyền bytes qua COPY protocol thay vì biến file thành hàng triệu chuỗi INSERT. Nó cũng tránh việc cấp quyền đọc file phía PostgreSQL server chỉ vì ứng dụng có file local.

### 45.2. Encoding phải được kiểm soát

Khi copy bytes trực tiếp, phải đảm bảo file encoding khớp COPY/session expectation. Đừng gọi InputStream là “Unicode” nếu chưa biết bytes thật.

### 45.3. Nếu muốn transform từng row ở Java

Bạn có thể dùng CSV parser streaming với charset decoder xác định, validate và sau đó tạo COPY data stream chuẩn. Nhưng phải xử lý delimiter/quote/newline/NULL thật, không nối chuỗi thủ công vô điều kiện.

### 45.4. Không ghép tên bảng từ input tùy ý

COPY statement trong ví dụ là một SQL template do ứng dụng kiểm soát. Nếu tên schema/table động, phải có allowlist và quoting identifier đúng, tránh SQL injection.

### 45.5. Quản lý transaction

`copyIn` không tự có nghĩa toàn bộ nghiệp vụ đã COMMIT. Nếu connection `autoCommit=false`, caller phải commit/rollback theo contract; nếu file hỏng, xử lý SQLSTATE, rollback và báo lỗi phù hợp.

---

## 46. Java export CSV qua COPY protocol

Một ứng dụng có thể xuất COPY TO STDOUT thành stream, ví dụ dùng pgjdbc CopyManager:

```java
import java.io.OutputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.sql.Connection;
import org.postgresql.PGConnection;
import org.postgresql.copy.CopyManager;

public class CopyExportExample {
    public static void exportCsv(
            Connection connection,
            Path target
    ) throws Exception {
        CopyManager manager = connection
                .unwrap(PGConnection.class)
                .getCopyAPI();

        String sql = """
            COPY (
                SELECT external_id, buyer, status,
                       amount, ordered_at, note
                FROM copyfmt_lab.orders
                ORDER BY external_id
            )
            TO STDOUT
            WITH (
                FORMAT csv,
                HEADER true,
                NULL '\\N'
            )
            """;

        try (OutputStream out = Files.newOutputStream(target)) {
            manager.copyOut(sql, out);
        }
    }
}
```

### 46.1. Điểm mạnh

- Streaming, không phải gọi `getString()` cho từng hàng theo kiểu ResultSet rồi tự join dấu phẩy.
- PostgreSQL thực hiện quoting theo CSV dialect.
- Có thể kết hợp với output file/object storage theo pipeline ứng dụng.

### 46.2. Bảo mật file đầu ra

File local có thể chứa PII. Đặt quyền filesystem, đường dẫn, mã hóa và retention phù hợp. Không xuất vào thư mục public của web server chỉ vì dễ tải xuống.

### 46.3. Điều kiện truy vấn

Ứng dụng vẫn phải có SELECT privileges phù hợp. Nếu bảng dùng RLS, kiểm thử theo role thực tế và ngữ cảnh quyền.

### 46.4. Lỗi giữa chừng

Nếu connection đứt giữa lúc export, file có thể **chưa hoàn chỉnh**. Không công bố file thành công trước khi COPY protocol hoàn tất, file được flush/close và kiểm tra manifest/checksum theo yêu cầu. Khi cần, ghi ra temporary path rồi đổi tên atomically theo khả năng filesystem.

---

## 47. COPY qua pgAdmin/GUI/ETL tools

Không phải mọi công cụ đều dùng \copy giống psql.

### 47.1. GUI import có thể tự parse CSV

Một GUI có thể đọc file phía client, parse CSV rồi gửi INSERT hoặc COPY protocol. Điều này ảnh hưởng option tương thích, đường lỗi, streaming và encoding.

### 47.2. Không dùng GUI default cho batch định kỳ mà không kiểm tra

Khi một người dùng chọn nhầm delimiter, header hoặc encoding, dữ liệu có thể nhập sai. Với production pipeline, sử dụng cấu hình versioned và tự động hóa có khả năng tái lập.

### 47.3. ETL tool có thể đổi kiểu trước PostgreSQL

Ví dụ nó có thể đọc leading zeros của mã bưu chính thành số rồi xuất lại không còn số 0 đầu. Đây không phải lỗi COPY; dữ liệu đã thay đổi ở upstream parser.

### 47.4. Xác minh schema bằng SQL sau nhập

Đếm, so business keys, null/empty, amount và timezone. GUI báo “Success” chưa đủ.

### 47.5. Log cấu hình import

Ghi format, delimiter, encoding, null marker, source URI, file checksum, batch_id, versions và row counts để điều tra các import khác nhau về sau.

---

## 48. CSV export cho Excel và BI: những quyết định riêng

### 48.1. Encoding

UTF-8 là lựa chọn tốt, nhưng người mở file bằng một spreadsheet có thể phải chọn UTF-8 khi import. Một số phiên bản/luồng mở file dựa vào BOM, locale hoặc thiết lập của hệ điều hành.

### 48.2. Header

Có header giúp người đọc, nhưng cần tránh trùng tên cột hoặc tên thay đổi không kiểm soát.

### 48.3. Số 0 ở đầu

Mã như `001234` có thể bị spreadsheet tự ép kiểu thành số và mất hai số 0. Cần cột text hoặc hướng dẫn import schema.

### 48.4. Ngày/tháng

`01/02/2026` có thể bị hiểu là ngày 1 tháng 2 hoặc ngày 2 tháng 1. Dùng ISO 8601 rõ ràng và/hoặc import type mapping.

### 48.5. Text bắt đầu bằng ký tự công thức

Cần có lớp neutralization theo consumer nếu có input không tin cậy. Quoting CSV không tự đảm bảo không chạy công thức.

### 48.6. Dữ liệu nhiều dòng

Spreadsheet có thể hiển thị một cell nhiều dòng, nhưng phần mềm xử lý CSV kém có thể chia thành nhiều rows. Kiểm thử với consumer thật.

---

## 49. Quy trình ingest an toàn end-to-end

Một quy trình production có thể thiết kế:

```text
Supplier
   |
   | upload file
   v
Object storage / inbound area
   |
   +-- authenticate source
   +-- checksum + file size + scan
   +-- encoding/dialect detection using trusted contract
   v
Staging loader (dedicated DB role)
   |
   | COPY CSV UTF-8 -> raw staging
   v
Validation
   |
   +-- schema/header check
   +-- raw row count
   +-- parse/constraint/business rules
   +-- dedup/idempotency
   +-- rejected data tracking
   v
Typed application tables
   |
   +-- transaction commit
   +-- audit result
   v
Downstream consumers
```

### 49.1. Ai có quyền nạp?

Loader dùng role chuyên biệt với INSERT vào staging và chỉ những thao tác chuyển typed data được cấp. Không dùng superuser hoặc role có quyền đọc toàn database.

### 49.2. Kiểm tra file trước khi COPY

Cần giới hạn file size, số cột, header, delimiter, encoding, nguồn file, row count giới hạn và các trường nguy hiểm cho downstream.

### 49.3. Giữ raw để điều tra, nhưng có retention

Nếu cần audit/retry, giữ file nguồn hoặc staging raw theo thời hạn rõ và quyền truy cập phù hợp. Không giữ PII vô thời hạn chỉ vì thuận tiện.

### 49.4. Rejected rows phải có contract

Nếu cho phép partial import, mỗi row bị loại nên có định danh và lý do. Không để một lần import lại tạo duplicate nghiệp vụ vì batch trước đã partial commit.

### 49.5. Lưu provenance

Ghi:

- Source system.
- File name/path identifier (không nhất thiết là đường dẫn nhạy cảm).
- Checksum.
- Encoding/dialect version.
- Schema contract version.
- Import batch ID.
- Started/completed timestamps.
- Accepted/rejected counts.
- Status/transaction outcome.

---

## 50. Cách nhận biết lỗi từ thông báo PostgreSQL

Một số nhóm lỗi:

| Triệu chứng | Nguyên nhân có thể | Hướng kiểm tra |
| --- | --- | --- |
| `invalid byte sequence for encoding "UTF8"` | File không UTF-8 hoặc bytes hỏng | Xác minh file bytes/encoding |
| `extra data after last expected column` | Delimiter/quote sai, dư fields | Kiểm tra CSV dialect và header |
| `missing data for column` | Thiếu fields trong record | Kiểm tra quoting/newline/column count |
| `invalid input syntax for type numeric` | Số không đúng cú pháp | Import staging TEXT rồi chuẩn hóa |
| `invalid input syntax for type timestamp...` | Ngày sai format | ISO/timezone/DateStyle |
| `null value ... violates not-null constraint` | NULL marker/blank value | NULL vs empty policies |
| `duplicate key value violates unique constraint` | Key đã tồn tại | Business key/dedup strategy |
| `permission denied for table` | Thiếu GRANT trên table | Role permissions |
| `permission denied for schema` | Thiếu USAGE | Schema privileges |
| `could not open file ...` | Server/client path hoặc OS permission | Phân biệt COPY và \copy |
| Import xong thấy dấu tiếng Việt rác | Decoding sai ở upstream | Raw file/encoding/terminal |
| Export thiếu rows | Query filter, RLS hoặc snapshot | Quyền và WHERE |
| COPY binary không nạp được | Schema/types không tương thích | Kiểm tra order/types/version |

### 50.1. SQLSTATE tốt hơn parse thông điệp

Khi phát hiện lỗi qua driver, nên sử dụng SQLSTATE và error metadata để phân loại kỹ thuật, không dựa vào một substring câu chữ.

### 50.2. Một lỗi có thể có nhiều nguyên nhân

Một file bị lỗi quote có thể dẫn tới thông báo “extra columns”. Đừng chỉ tăng số cột của table để làm lỗi biến mất; cần tìm nguyên nhân ở file format.

### 50.3. Dữ liệu nhập hợp lệ không đồng nghĩa chất lượng dữ liệu tốt

CSV có thể qua parser nhưng bị trộn tenant IDs, số tiền nhầm đơn vị hoặc thời gian sai timezone. Cần kiểm tra nghiệp vụ riêng.

---

## 51. Tình huống A: bên thứ ba gửi CSV Windows

**Bối cảnh:** Supplier gửi `products.csv` tạo bằng một phiên bản Excel cũ; file có dấu chấm phẩy, dấu tiếng Việt và số thập phân dùng dấu phẩy.

### 51.1. Không import ngay với default CSV

Default COPY delimiter là dấu phẩy; có thể làm lệch cột hoàn toàn.

### 51.2. Xác minh encoding

File có thể ở WIN1252 hoặc một encoding khác, nhưng không đoán theo tên hệ điều hành. Cần thông tin từ supplier hoặc sample bytes.

### 51.3. Chuẩn hóa dữ liệu

Quy trình:

- Decode bằng encoding nguồn đã xác nhận.
- Parse với delimiter `;` và quote rules chính xác.
- Chuyển number theo locale supplier sang canonical numeric string.
- Chuyển timestamp/timezone theo policy.
- Xuất thành CSV UTF-8 chuẩn, dùng delimiter/NULL marker của pipeline.
- Import staging rồi validate.

### 51.4. Giữ file gốc

Nếu số tiền bị chuyển sai, có thể đối chiếu lại với raw bytes nguồn; đừng chỉ giữ file đã normalize mà không có provenance.

---

## 52. Tình huống B: ghi chú chứa nhiều dòng và quote

**Bối cảnh:** App ghi chú đơn hàng chứa:

```text
Giao cho "chị Hà"
Gọi trước 15 phút, số nội bộ 123.
```

Một export tự ghép:

```text
order_id + "," + note + "\n"
```

có thể làm hỏng file vì note chứa dấu phẩy, quote và newline.

### 52.1. Dùng COPY CSV

`COPY (SELECT ...) TO STDOUT WITH (FORMAT csv)` xử lý quoting theo dialect PostgreSQL.

### 52.2. Đừng dùng String.split(",") ở consumer

Consumer phải parse CSV đúng quoted field semantics.

### 52.3. Round-trip

Sau import, so:

```sql
source.note IS NOT DISTINCT FROM imported.note
```

để kiểm tra NULL và text values theo semantics phù hợp.

### 52.4. Ứng dụng spreadsheet có thể hiển thị xuống dòng trong cell

Điều đó không có nghĩa file chứa hai records; cần phân biệt physical lines và logical CSV records.

---

## 53. Tình huống C: binary COPY giữa hai PostgreSQL versions

**Bối cảnh:** Một team xuất binary COPY trên một cluster rồi định nạp vào cluster khác đang có khác biệt về phiên bản/extension/types.

### 53.1. Rủi ro

- Column order khác.
- INTEGER/BIGINT/NUMERIC types khác.
- User-defined type có binary protocol riêng.
- Kiểu dữ liệu hoặc format thay đổi giữa versions.
- Tệp không chứa đủ schema/metadata để tự khôi phục.

### 53.2. Hướng xử lý

Nếu là migration dữ liệu lâu dài, ưu tiên `pg_dump/pg_restore` hoặc CSV/text có contract rõ. Nếu vẫn dùng binary COPY, chỉ dùng sau khi test đầy đủ tương thích trên cặp môi trường thực tế và có plan rollback.

### 53.3. Không coi binary COPY là backup

Một binary export SELECT chỉ chứa các rows/cột bạn chọn, không mang toàn bộ indexes, constraints, grants, functions và những metadata cần phục hồi database.

---

## 54. Tình huống D: Unicode nhìn đúng trên nguồn, sai sau nhập

**Bối cảnh:** File CSV mở trong editor đúng tên tiếng Việt, nhưng PostgreSQL lưu ký tự rác.

### 54.1. Điều tra từng lớp

1. Xác nhận encoding thật của file.
2. Xác nhận công cụ đọc file dùng charset nào.
3. Kiểm tra `client_encoding` ở session.
4. Kiểm tra `server_encoding`.
5. Kiểm tra copy option ENCODING nếu có.
6. Kiểm tra phép chuyển đổi trước COPY.
7. Kiểm tra hiển thị của SQL client, font và terminal.
8. So raw values và exports bằng công cụ đã biết UTF-8.

### 54.2. Nếu bytes đã bị hỏng trước khi đến PostgreSQL

Không thể sửa bằng ALTER DATABASE hoặc SET client_encoding một cách đơn giản. Phải khôi phục từ file gốc hoặc thực hiện conversion có kiểm chứng.

### 54.3. Kiểm tra sample Unicode

Dùng những tên có ký tự dấu nặng, dấu hỏi, `Đ/đ`, emoji và combining marks để phát hiện lỗi thay vì chỉ thử ASCII.

---

## 55. Những hiểu nhầm thường gặp

| Hiểu nhầm | Thực tế |
| --- | --- |
| “CSV có nghĩa luôn dùng dấu phẩy.” | Có thể thay delimiter; cần contract |
| “CSV = UTF-8.” | CSV là format, encoding là trục khác |
| “File mở được bằng editor nghĩa UTF-8.” | Editor có thể tự đoán hoặc thay encoding |
| “UTF-16 là UTF-8 vì đều Unicode.” | Hai cách serialize khác nhau |
| “Đổi client_encoding sẽ sửa chữ đã hỏng.” | Không nếu dữ liệu đã bị mojibake/lost |
| “BOM luôn phải có.” | UTF-8 không cần BOM; consumer có thể yêu cầu |
| “BOM không ảnh hưởng header.” | Có thể ảnh hưởng HEADER MATCH |
| “COPY là lệnh của psql.” | COPY là SQL PostgreSQL |
| “\copy là SQL dùng trong JDBC.” | \copy là psql meta-command |
| “COPY FROM '/path' đọc file laptop.” | Server-side path |
| “\copy đọc file phía PostgreSQL server.” | Client-side process path |
| “COPY FROM STDIN tự đọc mọi file.” | Cần client gửi stream |
| “COPY server file chỉ cần table INSERT.” | Cần file-level privileges và OS access |
| “COPY PROGRAM là cách mở file tiện.” | Quyền nhạy cảm, nguy cơ command execution |
| “Text COPY dùng dấu phẩy mặc định.” | Mặc định tab |
| “Text COPY không escape backslash.” | Có quy tắc escape riêng |
| “\N là SQL NULL syntax.” | Là file marker theo text/CSV contract |
| “CSV NULL và empty string luôn giống nhau.” | Có thể phân biệt qua quoting/marker |
| “FORCE_QUOTE khiến NULL thành empty.” | Không |
| “HEADER true tự map cột theo tên.” | Chủ yếu xử lý header; phải giữ column order |
| “HEADER MATCH tự reorder columns.” | Kiểm tra tên/thứ tự theo contract |
| “Mỗi dòng vật lý CSV là một record.” | Quoted field có thể chứa newline |
| “split(',') đủ để parse CSV.” | Không hiểu quoted comma/newline |
| “Đổi delimiter sửa sai số 1,25.” | Numeric normalization là việc khác |
| “DATE/TIMESTAMP từ CSV không phụ thuộc timezone.” | Có thể phụ thuộc input/DateStyle/session |
| “Binary COPY là tệp CSV nén.” | Là format binary riêng |
| “Binary luôn nhanh hơn CSV.” | Phụ thuộc workload |
| “Binary COPY là backup PostgreSQL.” | Không lưu đủ schema/ACL/metadata |
| “Binary copy portable qua mọi version/type.” | Không bảo đảm |
| “COPY bỏ qua constraints và triggers.” | Không theo mặc định |
| “COPY không sinh WAL.” | Thường sinh WAL trên bảng logged |
| “COPY lỗi có thể commit nửa statement.” | Statement lỗi không được commit nửa |
| “COPY lỗi không tốn disk.” | Tuples chết có thể gây disk space cho tới VACUUM |
| “ON_ERROR ignore bỏ qua mọi lỗi.” | Chỉ những loại lỗi được hỗ trợ theo phiên bản |
| “COPY FROM tự tuân RLS giống INSERT.” | COPY FROM có hạn chế với RLS |
| “COPY TO qua role owner bảo đảm tenant filtering.” | Owner có thể bypass RLS |
| “Có INSERT table là đủ quyền sequence mọi nơi.” | Sequence/default cần xét riêng |
| “Import thành công là đúng nghiệp vụ.” | Vẫn cần validation/counts/timezones |
| “Staging có TEXT nên tất cả dữ liệu đều sạch.” | TEXT chỉ tránh một số lỗi parse type |
| “ON CONFLICT DO NOTHING luôn là dedup đúng.” | Có thể che conflict dữ liệu |
| “Excel đọc chuỗi =... như text an toàn nếu có CSV quote.” | Có rủi ro formula injection |
| “Export file đầy đủ khi COPY bắt đầu.” | Kết nối có thể lỗi giữa chừng |
| “Rows/s tăng nghĩa batch an toàn hơn.” | Còn consistency, WAL, replication, recovery |
| “SQL_ASCII là cách chữa encoding.” | Có thể che validation/hỏng Unicode |
| “Tài khoản admin nên dùng nhập file.” | Ưu tiên role import tối thiểu |
| “COPY nhanh nhất là drop constraints.” | Có rủi ro correctness và downtime |

---

## 56. Bài tập thực hành

### Bài 1 — Format hay encoding?

Giải thích sự khác nhau giữa CSV và UTF-8. Một file có thể là CSV mã hóa UTF-16 không?

### Bài 2 — COPY vs \copy

Cho biết file được mở ở đâu khi chạy `COPY FROM '/tmp/data.csv'` và `\copy FROM './data.csv'`. Vì sao hai path có thể trỏ tới hai máy khác nhau?

### Bài 3 — STDIN/STDOUT

Viết lệnh COPY một bảng vào STDOUT theo CSV và một lệnh COPY từ STDIN. Client phải làm gì ở mỗi trường hợp?

### Bài 4 — Text default

Text COPY dùng delimiter và NULL marker mặc định nào? Khi nào nên dùng text thay CSV?

### Bài 5 — Text escapes

Biểu diễn trường chứa tab, newline và backslash trong text format. Vì sao split theo tab không đủ?

### Bài 6 — CSV quoted comma

Viết một CSV record có buyer bằng `Hà Nội, Việt Nam` nhưng vẫn chỉ chứa một trường buyer.

### Bài 7 — CSV quotes

Biểu diễn note `Đặt "combo"` với QUOTE/ESCAPE mặc định.

### Bài 8 — Multiline field

Tạo CSV với note hai dòng rồi kiểm tra sau import số logical rows và giá trị note.

### Bài 9 — NULL vs empty

Viết ba trường hợp NULL, `''` và `'NULL'` trong CSV mặc định, sau đó dùng SQL kiểm tra IS NULL và LENGTH.

### Bài 10 — Custom NULL marker

Dùng `NULL '\N'` để xuất dữ liệu, nhập lại và chứng minh empty string không bị đổi thành NULL.

### Bài 11 — FORCE_QUOTE

Xuất một bảng CSV với FORCE_QUOTE *. Kết quả NULL có thành empty string không?

### Bài 12 — FORCE_NULL/FORCE_NOT_NULL

Giải thích hai tùy chọn ảnh hưởng cách parse quoted/unquoted NULL marker như thế nào.

### Bài 13 — HEADER true

Nhập CSV có header và danh sách cột tường minh. Nếu header đổi thứ tự mà importer không đổi, nguy cơ gì xảy ra?

### Bài 14 — HEADER MATCH

Nếu PostgreSQL version hỗ trợ, thử HEADER MATCH với header đúng rồi với một tên cột sai. Tùy chọn có tự reorder không?

### Bài 15 — Delimiter semicolon

Viết COPY CSV dùng DELIMITER ';'. Trong trường hợp nào spreadsheet xuất CSV theo dấu chấm phẩy?

### Bài 16 — CRLF/LF

Giải thích tại sao số physical lines có thể khác số CSV records. Viết test cho quoted multiline field.

### Bài 17 — Binary format

So sánh khả năng đọc bằng mắt và tính portable của text, CSV, binary. Vì sao binary COPY không phải bản backup?

### Bài 18 — Binary types

Một file binary xuất cột INTEGER có thể nạp thẳng vào cột NUMERIC mà không cần kiểm tra không? Vì sao?

### Bài 19 — Đo kích thước

Export cùng dữ liệu bằng text, CSV và binary; so sánh byte sizes. Số bytes ít hơn có bảo đảm import nhanh hơn không?

### Bài 20 — server/client encoding

Chạy SHOW server_encoding và SHOW client_encoding. Chúng diễn đạt hai điều gì khác nhau?

### Bài 21 — UTF-8

Tạo file CSV UTF-8 gồm tên `Đặng Thị Hạnh` và `Nguyễn Ánh` rồi import. Làm sao xác minh dấu tiếng Việt còn đúng?

### Bài 22 — UTF-16

Một file UTF-16 đưa vào COPY với ENCODING UTF8 có thể gây lỗi gì? Làm sao chuyển mã đúng mà không mất dữ liệu?

### Bài 23 — BOM

Một CSV UTF-8 có BOM làm HEADER MATCH thất bại ở tên cột đầu tiên. Đề xuất cách xử lý an toàn.

### Bài 24 — Mojibake

Nếu database đã lưu text Unicode bị giải mã sai từ đầu, tại sao SET client_encoding không phải cách tự động sửa?

### Bài 25 — SQL_ASCII

Vì sao không nên dùng SQL_ASCII để bỏ qua lỗi invalid UTF-8 khi import hệ thống có dữ liệu đa ngôn ngữ?

### Bài 26 — File staging

Tạo `copyfmt_lab.stage_orders` với các cột TEXT. Vì sao không nạp ngay vào bảng typed khi nguồn dữ liệu thường lỗi?

### Bài 27 — CSV lab

Tạo file supplier-orders.csv theo ví dụ, chạy \copy vào staging và đếm số logical rows.

### Bài 28 — NULL/empty lab

Với E-1004 và E-1005, kiểm tra note IS NULL và LENGTH(note). Nêu giá trị kỳ vọng.

### Bài 29 — Cast NUMERIC

Thêm một row amount_text=`'12,50'` vào staging. Vì sao cast NUMERIC trong SELECT có thể thất bại? Thiết kế normalization theo locale.

### Bài 30 — Timestamp

So sánh `2026-11-01T08:30:00+07:00` với chuỗi không offset. Làm sao giữ cùng instant khi xuất/nhập giữa hai sessions timezone khác nhau?

### Bài 31 — ON CONFLICT

Nếu hai dòng cùng external_id nhưng amount khác, ON CONFLICT DO NOTHING có đủ để đảm bảo correctness không? Đề xuất cách kiểm tra conflict.

### Bài 32 — Round-trip

Tạo test có NULL, empty, comma, quote, newline, tab, backslash, Unicode và timestamp; export rồi import lại và so với IS DISTINCT FROM.

### Bài 33 — Permissions

Vì sao một role có INSERT trên table chưa chắc có quyền COPY FROM server-side file? Khi nào \copy tiện hơn?

### Bài 34 — RLS

Giải thích hạn chế COPY FROM trên bảng có RLS. Một application multi-tenant nên thiết kế import như thế nào?

### Bài 35 — Constraint failure

Nạp một file có row cuối vi phạm CHECK. Điều gì xảy ra với statement COPY và disk space của tuples đã nạp trước lỗi?

### Bài 36 — Triggers/indexes

Một bảng có 10 indexes và nhiều triggers. Vì sao COPY có thể chậm dù parser CSV nhanh?

### Bài 37 — WAL/replication

Bulk load có thể làm replication lag tăng như thế nào? Cần giám sát những chỉ số gì?

### Bài 38 — UNLOGGED staging

Khi nào UNLOGGED staging hữu ích và giới hạn crash recovery/replication của nó là gì?

### Bài 39 — COPY FREEZE

Tìm tài liệu phiên bản và nêu điều kiện cần có để dùng COPY FREEZE. Vì sao không bật đại trà?

### Bài 40 — CSV injection

Một note bắt đầu bằng dấu = hoặc + được export và mở bằng spreadsheet. Vì sao CSV quoting không đảm bảo an toàn? Nêu chính sách bảo vệ phù hợp.

### Bài 41 — Leading zeros

Mã `001234` bị Excel biến thành 1234. Đây là vấn đề encoding, PostgreSQL COPY hay import type inference của spreadsheet?

### Bài 42 — JDBC CopyManager

Viết code Java dùng CopyManager.copyIn(sql, InputStream) để streaming CSV từ file. Vì sao không gọi `\copy` trong PreparedStatement?

### Bài 43 — Java export

Dùng CopyManager.copyOut(sql, OutputStream) tạo CSV. Nếu kết nối bị lỗi giữa chừng, file cần được công bố như thế nào?

### Bài 44 — Import audit

Thiết kế bảng batch log có source_file, checksum, encoding, format options, row_count, accepted_count, rejected_count và status.

### Bài 45 — Error handling

Một CSV có “extra data after last expected column”. Liệt kê các nguyên nhân có thể và cách điều tra mà không mở rộng schema bừa bãi.

### Bài 46 — Production architecture

Một hệ thống PostgreSQL nhận 20GB CSV/ngày từ nhiều nhà cung cấp, có Unicode/Excel legacy, nhiều tenants, HA standby và dashboard. Thiết kế pipeline an toàn gồm file ingestion, encoding normalization, staging, constraints, batching, idempotency, audit, bảo mật, WAL/replication monitoring, schema contract và rollback.

---

## 57. Checklist trước khi nhập/xuất dữ liệu production

| Câu hỏi | Điều cần xác nhận |
| --- | --- |
| File dùng format nào? | Text, CSV hay binary |
| Encoding nào? | UTF-8 hoặc encoding nguồn đã xác minh |
| Có BOM không? | Kiểm tra/chuẩn hóa đúng |
| Delimiter nào? | Tab/comma/semicolon/khác |
| Quote và escape? | Dialect được công bố |
| Newline? | LF/CRLF, quoted multiline |
| Có header? | true/false/MATCH theo version |
| Thứ tự cột đúng? | Column list cố định |
| Có schema contract? | Names/types/null/timezone |
| NULL marker là gì? | \N/empty/custom |
| Empty string có giữ nguyên? | Test với NULL |
| Literal NULL marker xử lý đúng? | Quoting/escaping |
| Có Unicode tiếng Việt? | Test canary strings |
| Có Unicode normalization policy? | Nếu cần so khớp |
| Có timestamp offset? | ISO 8601/timezone |
| Numeric có dấu chấm? | Không lệ thuộc locale bất ngờ |
| Có leading zeros? | Giữ dưới dạng TEXT |
| Có CSV formula injection risk? | Spreadsheet export policy |
| File path nằm ở máy nào? | COPY server vs \copy client |
| Có quyền OS phù hợp? | Server/client filesystem |
| Có dùng role file đặc quyền không cần? | Tránh |
| COPY protocol được hỗ trợ? | psql/JDBC/GUI |
| Có giới hạn file size? | Quota/validation |
| Có checksum? | Source integrity |
| Có staging không? | Raw data và validation |
| Cột typed đúng? | NUMERIC, TIMESTAMPTZ |
| Có CHECK/UNIQUE/FK? | Data invariants |
| Có trigger? | Side effects/performance |
| Có RLS? | COPY FROM hạn chế, role thật |
| Có quyền SELECT/INSERT đúng? | Least privilege |
| Có dữ liệu nhạy cảm trong export? | Column/scope review |
| Có thứ tự deterministic? | ORDER BY nếu cần |
| Có idempotency? | Không nhân đôi |
| Có duplicate policy? | Không silent data loss |
| Có partial acceptance policy? | Rejected rows và số lượng |
| Có SQLSTATE/error log? | Chẩn đoán có cấu trúc |
| Có transaction boundary? | COMMIT/ROLLBACK rõ |
| Có thử failure cuối file? | Statement atomicity |
| Có giám sát WAL? | Disk/replication lag |
| Có autovacuum/ANALYZE plan? | Stats/bloat |
| Có giới hạn duration/load? | Availability |
| Có round-trip tests? | Null/empty/Unicode/quote |
| Có kiểm thử consumer thực? | Excel/BI/Java |
| Có metadata file format version? | Có thể tái lập |
| Có đảm bảo file hoàn chỉnh trước publish? | Temp path/checksum |
| Có retention và encryption? | File và staging |
| Có backup/restore strategy? | Không dùng binary COPY làm full backup |

---

## 58. Kết luận

**Định dạng text, CSV, binary và lựa chọn mã hóa** là chủ đề vừa liên quan đến cú pháp PostgreSQL, vừa liên quan trực tiếp đến độ đúng của dữ liệu khi đi qua hệ thống khác.

Những nguyên tắc cần ghi nhớ:

1. **Format và encoding là hai khái niệm khác nhau.** CSV/text xác định cấu trúc fields/rows; UTF-8 hay một code page khác xác định bytes biểu diễn ký tự.
2. **COPY và \copy khác nơi mở file.** SQL COPY server-side truy cập filesystem database server; `psql \copy` truyền file phía client bằng COPY protocol.
3. **Text format là dialect riêng của PostgreSQL.** Mặc định tab, có backslash escaping và NULL marker `\N`.
4. **CSV thuận tiện cho trao đổi nhưng có nhiều quy tắc.** Delimiter, quote, escape, header, NULL marker và multiline fields phải nhất quán.
5. **NULL không giống chuỗi rỗng.** Với CSV mặc định, giá trị này có thể phân biệt nhờ quoted/unquoted fields; cần thử round-trip.
6. **Binary COPY có thể hữu ích cho luồng PostgreSQL chuyên dụng nhưng không là định dạng archive/backup phổ quát.**
7. **UTF-8 thường là lựa chọn an toàn cho hệ thống mới.** Nhưng phải xác minh nguồn, xử lý BOM và tránh đoán encoding chỉ từ đuôi file.
8. **Mã hóa đúng không tự chuẩn hóa dữ liệu.** Numeric locale, timezone, leading zeros và Unicode normalization là những contract khác.
9. **COPY vẫn chịu transaction, constraints, triggers và WAL.** Một bulk load nhanh chưa chắc an toàn nếu không có kiểm tra dữ liệu/permission/replication.
10. **Staging giúp tách ingest khỏi validation.** Đặc biệt khi nhà cung cấp có dữ liệu không sạch, nhập TEXT rồi chuyển typed với chính sách reject rõ ràng.
11. **Xuất CSV cho spreadsheet có rủi ro formula injection.** CSV quote không tự bảo đảm ứng dụng spreadsheet sẽ đọc cell như text an toàn.
12. **Kiểm thử dữ liệu thật và consumer thật.** Đo round-trip correctness trước khi tối ưu throughput; chỉ công bố file hoặc transaction thành công khi toàn bộ luồng đã hoàn tất.

Một pipeline nhập xuất PostgreSQL đáng tin cậy không chỉ chuyển được nhiều hàng nhanh, mà còn **giữ nguyên ý nghĩa của từng giá trị, có thể giải thích nguồn gốc của bytes, phân biệt rõ NULL với empty string, bảo vệ Unicode, không làm lộ dữ liệu và có cơ chế phục hồi khi file hoặc kết nối bị lỗi**.
