# Hàm chuỗi: SUBSTR, INSTR, LENGTH, TRIM và REPLACE trong Oracle Database

Khi xử lý dữ liệu nghiệp vụ, chuỗi thường cần được tách, tìm vị trí, đo độ dài, chuẩn hóa khoảng trắng hoặc thay thế một phần nội dung. Oracle Database cung cấp nhiều hàm SQL cho những thao tác này. Năm hàm nền tảng cần nắm vững là **`SUBSTR`, `INSTR`, `LENGTH`, `TRIM` và `REPLACE`**.

Các hàm có thể kết hợp trong một câu `SELECT`, điều kiện `WHERE`, biểu thức tạo cột, câu `UPDATE` hoặc quy trình nạp dữ liệu. Tuy nhiên, hiểu cú pháp thôi chưa đủ: người viết SQL cần phân biệt **ký tự với byte**, vị trí bắt đầu với số lần xuất hiện, khoảng trắng thường với ký tự trắng đặc biệt, và chuỗi rỗng với `NULL` theo ngữ nghĩa Oracle.

Bài học sử dụng bảng dữ liệu minh họa về mã sản phẩm, email, tên file và chuỗi có dấu tiếng Việt. Các ví dụ hướng tới SQL thực tế, đồng thời giải thích cách tránh lỗi khi dữ liệu đến từ nhiều ứng dụng, encoding hoặc thiết lập NLS khác nhau.

## 1. Tổng quan năm hàm

| Hàm | Mục đích | Ví dụ ngắn | Kết quả |
|---|---|---|---|
| `SUBSTR(char, position [, length])` | Lấy một phần chuỗi theo vị trí | `SUBSTR('ORACLE', 2, 3)` | `RAC` |
| `INSTR(char, substring [, position [, occurrence]])` | Tìm vị trí xuất hiện của chuỗi con | `INSTR('A-B-C', '-', 2)` | `4` |
| `LENGTH(char)` | Đếm độ dài theo ký tự | `LENGTH('ORACLE')` | `6` |
| `TRIM([LEADING \| TRAILING \| BOTH] [trim_char] FROM char)` | Loại ký tự chỉ định ở đầu/cuối chuỗi | `TRIM('  SQL  ')` | `SQL` |
| `REPLACE(char, search_string [, replacement_string])` | Thay mọi lần xuất hiện của chuỗi con | `REPLACE('A-B-A', 'A', 'X')` | `X-B-X` |

Những điểm chung:

- Đây là các **hàm xử lý chuỗi ký tự**; chúng không tự xác thực ý nghĩa nghiệp vụ của chuỗi.
- Oracle có các biến thể theo byte hoặc đơn vị Unicode như `SUBSTRB`, `INSTRB`, `LENGTHB`, cùng các biến thể `C`, `2`, `4` trong một số nhóm hàm.
- Kết quả phụ thuộc kiểu dữ liệu đầu vào, character set và đôi khi cả quy tắc collation/NLS.
- Oracle hiện xử lý chuỗi ký tự độ dài bằng 0 như `NULL` trong SQL thông thường. Do đó `LENGTH('')` trả `NULL`, không phải 0.
- Nên dùng bind variable và kiểu dữ liệu phù hợp; không ghép chuỗi người dùng nhập trực tiếp vào SQL.

## 2. Chuẩn bị bảng thực hành

Tạo một bảng nhỏ trong schema lab:

```sql
CREATE TABLE string_lab (
    item_id       NUMBER(10) CONSTRAINT pk_string_lab PRIMARY KEY,
    product_code  VARCHAR2(40 CHAR),
    customer_name VARCHAR2(100 CHAR),
    email_address VARCHAR2(160 CHAR),
    file_name     VARCHAR2(160 CHAR),
    note_text     VARCHAR2(300 CHAR)
);

INSERT INTO string_lab VALUES (
    1,
    'PRD-2026-001',
    '  Nguyễn An  ',
    'an.nguyen@example.test',
    'invoice_2026_11.csv',
    'Oracle SQL string functions'
);

INSERT INTO string_lab VALUES (
    2,
    'PRD-2026-002',
    'Trần Bình',
    'binh.tran@example.test',
    'report.final.v2.xlsx',
    'Học SQL với dữ liệu tiếng Việt'
);

INSERT INTO string_lab VALUES (
    3,
    'SRV-DB-015',
    'Lê Chi',
    'chi@example.test',
    'README',
    'No file extension'
);

INSERT INTO string_lab VALUES (
    4,
    'PRD-2026-010',
    'Đỗ Dung',
    'dung@example.test',
    'archive.tar.gz',
    'Two dots in file name'
);

COMMIT;
```

Tên và email dùng miền `example.test` để minh họa, không phải địa chỉ liên hệ thật. Các chuỗi có dấu giúp quan sát sự khác nhau giữa số ký tự và số byte trong character set đa byte như AL32UTF8.

Xem dữ liệu:

```sql
SELECT item_id, product_code, customer_name, email_address, file_name
FROM string_lab
ORDER BY item_id;
```

## 3. SUBSTR — trích một phần chuỗi

### 3.1. Cú pháp và tham số

```sql
SUBSTR(char, position [, substring_length])
```

- `char`: chuỗi nguồn.
- `position`: vị trí bắt đầu, tính từ 1 ở đầu chuỗi.
- `substring_length`: số ký tự muốn lấy; nếu bỏ qua, Oracle lấy từ vị trí bắt đầu đến hết chuỗi.

Ví dụ:

```sql
SELECT SUBSTR('ORACLE DATABASE', 1, 6) AS part_1,
       SUBSTR('ORACLE DATABASE', 8, 8) AS part_2,
       SUBSTR('ORACLE DATABASE', 8) AS rest
FROM dual;
```

Kết quả:

| PART_1 | PART_2 | REST |
|---|---|---|
| `ORACLE` | `DATABASE` | `DATABASE` |

### 3.2. Vị trí dương, vị trí âm và vị trí 0

Oracle tính vị trí từ 1:

```sql
SELECT SUBSTR('DATABASE', 1, 4) AS from_start,
       SUBSTR('DATABASE', 5, 4) AS from_middle,
       SUBSTR('DATABASE', -4, 4) AS from_end,
       SUBSTR('DATABASE', -4) AS rest_from_end
FROM dual;
```

| Biểu thức | Kết quả | Giải thích |
|---|---|---|
| `SUBSTR('DATABASE', 1, 4)` | `DATA` | Bắt đầu tại ký tự đầu |
| `SUBSTR('DATABASE', 5, 4)` | `BASE` | Bắt đầu tại ký tự thứ 5 |
| `SUBSTR('DATABASE', -4, 4)` | `BASE` | Đếm vị trí bắt đầu từ cuối chuỗi |
| `SUBSTR('DATABASE', -4)` | `BASE` | Lấy từ vị trí thứ 4 tính từ cuối đến hết |
| `SUBSTR('DATABASE', 0, 4)` | `DATA` | Oracle xử lý position 0 như position 1 |

Quy tắc vị trí âm rất hữu ích khi cần lấy hậu tố mà không biết chính xác độ dài đầu chuỗi, chẳng hạn phần mở rộng file:

```sql
SELECT file_name,
       SUBSTR(file_name, -3) AS last_three_chars
FROM string_lab
ORDER BY item_id;
```

Nhưng cách lấy ba ký tự cuối **không tương đương** với lấy phần mở rộng file theo dấu chấm cuối cùng. Ví dụ `report.final.v2.xlsx` có phần mở rộng `xlsx`, còn ba ký tự cuối là `lsx`. Hãy dùng `INSTR` kết hợp `SUBSTR` khi cần phân tích delimiter.

### 3.3. Độ dài không hợp lệ hoặc vượt cuối chuỗi

```sql
SELECT SUBSTR('ORACLE', 4, 20) AS beyond_end,
       SUBSTR('ORACLE', 4, 0) AS zero_length,
       SUBSTR('ORACLE', 4, -2) AS negative_length
FROM dual;
```

- Nếu độ dài vượt phần còn lại, hàm trả phần chuỗi còn lại.
- Nếu `substring_length` nhỏ hơn 1, `SUBSTR` trả `NULL`.
- Độ dài âm không có nghĩa là “lùi lại”; muốn bắt đầu từ cuối, dùng **position âm**, còn length vẫn phải dương.

Trong SQL, hàm trả `NULL` có thể khiến phép nối chuỗi hoặc điều kiện lọc cho kết quả khác dự kiến. Nếu đầu vào do người dùng cung cấp, nên kiểm tra vị trí và độ dài trước khi sử dụng.

### 3.4. Trích mã theo delimiter

Với mã `PRD-2026-001`:

```sql
SELECT product_code,
       SUBSTR(product_code, 1, 3) AS product_group,
       SUBSTR(product_code, 5, 4) AS product_year,
       SUBSTR(product_code, 10, 3) AS sequence_no
FROM string_lab
WHERE item_id = 1;
```

Kết quả minh họa:

| PRODUCT_GROUP | PRODUCT_YEAR | SEQUENCE_NO |
|---|---|---|
| `PRD` | `2026` | `001` |

Đây là cách phù hợp khi format mã cố định. Nếu delimiter hoặc độ dài từng phần thay đổi, không nên hardcode vị trí; hãy dùng `INSTR`, một bảng quy tắc parse hoặc hàm biểu thức chính quy phù hợp.

### 3.5. SUBSTR với chuỗi nhiều byte

`SUBSTR` đếm theo ký tự của bộ ký tự đầu vào, không phải số byte UTF-8. Ví dụ:

```sql
SELECT SUBSTR('Tiếng Việt', 1, 5) AS first_five_chars,
       LENGTH('Tiếng Việt') AS char_length,
       LENGTHB('Tiếng Việt') AS byte_length
FROM dual;
```

Trên database dùng AL32UTF8, ký tự có dấu có thể chiếm nhiều byte. `SUBSTR('Tiếng Việt', 1, 5)` vẫn lấy năm ký tự theo ngữ nghĩa ký tự, không cắt giữa byte của một mã UTF-8. Khi giao tiếp với hệ thống byte-oriented, cần phân biệt `SUBSTR` với `SUBSTRB`.

## 4. INSTR — tìm vị trí của chuỗi con

### 4.1. Cú pháp

```sql
INSTR(
    string,
    substring
    [, position
    [, occurrence]]
)
```

- `string`: chuỗi cần tìm bên trong.
- `substring`: chuỗi con cần tìm.
- `position`: vị trí bắt đầu tìm; mặc định là 1.
- `occurrence`: lần xuất hiện cần trả về; mặc định là 1.

Kết quả là **vị trí bắt đầu**, tính từ 1, của lần xuất hiện được yêu cầu. Nếu không tìm thấy, hàm trả **0**.

Ví dụ:

```sql
SELECT INSTR('ORACLE DATABASE', 'A') AS first_a,
       INSTR('ORACLE DATABASE', 'A', 1, 2) AS second_a,
       INSTR('ORACLE DATABASE', 'Z') AS missing_z
FROM dual;
```

| FIRST_A | SECOND_A | MISSING_Z |
|---:|---:|---:|
| 3 | 10 | 0 |

Kết quả thứ hai là 10 vì chữ `A` xuất hiện lần thứ hai ở vị trí 10 trong chuỗi nguồn.

### 4.2. Tìm delimiter

Lấy vị trí dấu `@` trong email:

```sql
SELECT email_address,
       INSTR(email_address, '@') AS at_position
FROM string_lab
ORDER BY item_id;
```

Lấy vị trí dấu chấm đầu tiên và cuối cùng trong tên file:

```sql
SELECT file_name,
       INSTR(file_name, '.') AS first_dot,
       INSTR(file_name, '.', -1) AS last_dot
FROM string_lab
ORDER BY item_id;
```

Với `archive.tar.gz`, dấu chấm đầu tiên và cuối cùng khác nhau. Đây là lý do nên xác định **occurrence** hoặc dùng position âm khi cần lấy extension theo dấu chấm cuối.

### 4.3. Position âm: tìm ngược từ cuối

Nếu `position` âm, Oracle đếm vị trí bắt đầu từ cuối chuỗi và tìm theo hướng ngược về đầu. Giá trị trả về vẫn là vị trí tính từ đầu chuỗi:

```sql
SELECT INSTR('ONE-TWO-THREE', '-', 1, 2) AS second_from_left,
       INSTR('ONE-TWO-THREE', '-', -1, 1) AS first_from_right,
       INSTR('ONE-TWO-THREE', '-', -1, 2) AS second_from_right
FROM dual;
```

| SECOND_FROM_LEFT | FIRST_FROM_RIGHT | SECOND_FROM_RIGHT |
|---:|---:|---:|
| 7 | 7 | 4 |

Với chuỗi `ONE-TWO-THREE`:

- Dấu gạch ngang thứ nhất ở vị trí 4.
- Dấu gạch ngang thứ hai ở vị trí 8? Hãy đếm chính xác: `O(1) N(2) E(3) -(4) T(5) W(6) O(7) -(8) T(9) H(10) R(11) E(12) E(13)`.
- Do đó biểu thức trả về vị trí tương ứng là 8 và 4.

Với ví dụ này, bảng kết quả cần đọc theo chuỗi ký tự và vị trí 1-based; không nhầm “lần thứ hai từ trái” với “vị trí bắt đầu từ cuối”.

### 4.4. INSTR không tìm thấy trả 0 — chú ý khi kết hợp SUBSTR

Một lỗi thường gặp:

```sql
SELECT SUBSTR(email_address, 1, INSTR(email_address, '@') - 1)
       AS email_user
FROM string_lab;
```

Nếu email không có `@`, `INSTR` trả 0; độ dài truyền vào `SUBSTR` trở thành -1, và kết quả là `NULL`. Điều này có thể vô tình làm dữ liệu sai trông giống dữ liệu thiếu. Nên kiểm tra delimiter trước:

```sql
SELECT email_address,
       CASE
           WHEN INSTR(email_address, '@') > 1
           THEN SUBSTR(
                    email_address,
                    1,
                    INSTR(email_address, '@') - 1
                )
           ELSE NULL
       END AS email_user
FROM string_lab;
```

Đây mới chỉ là cách tách phần trước `@`, **không phải kiểm tra email hợp lệ đầy đủ**. Một địa chỉ có nhiều ký tự `@`, dấu chấm sai vị trí hoặc domain không tồn tại vẫn cần quy tắc validation riêng.

### 4.5. INSTR và phân biệt hoa/thường

Trong cách so khớp thông thường, `INSTR` phân biệt chữ hoa và chữ thường:

```sql
SELECT INSTR('Oracle Database', 'oracle') AS lower_match,
       INSTR(LOWER('Oracle Database'), LOWER('ORACLE')) AS normalized_match
FROM dual;
```

Biểu thức đầu trả 0 trong quy tắc so khớp phân biệt case thông thường; biểu thức thứ hai tìm thấy vì hai phía được chuẩn hóa về chữ thường. Với ngôn ngữ có quy tắc chữ hoa/thường phức tạp, không tự dùng `LOWER` như một bộ chuẩn hóa ngôn ngữ hoàn chỉnh; cần xét collation/NLS và yêu cầu so sánh thực tế.

## 5. LENGTH — đếm độ dài chuỗi

### 5.1. LENGTH đếm ký tự

```sql
LENGTH(char)
```

Ví dụ:

```sql
SELECT LENGTH('ORACLE') AS length_ascii,
       LENGTH('Tiếng Việt') AS length_vietnamese,
       LENGTH('A B') AS length_with_space
FROM dual;
```

`LENGTH` trả số ký tự theo ngữ nghĩa character set; khoảng trắng ở giữa và khoảng trắng cuối chuỗi vẫn được tính. Với `VARCHAR2`, các ký tự trắng đã lưu là dữ liệu và được đếm.

### 5.2. LENGTHB đếm byte

```sql
SELECT LENGTH('ABC') AS chars_abc,
       LENGTHB('ABC') AS bytes_abc,
       LENGTH('Tiếng Việt') AS chars_vietnamese,
       LENGTHB('Tiếng Việt') AS bytes_vietnamese
FROM dual;
```

Trong database dùng AL32UTF8, chữ ASCII thường chiếm 1 byte, còn ký tự có dấu tiếng Việt có thể chiếm nhiều byte. Vì vậy `LENGTH` và `LENGTHB` có thể khác nhau.

| Hàm | Đếm theo | Khi nào quan tâm? |
|---|---|---|
| `LENGTH` | Ký tự | Giới hạn độ dài văn bản theo ký tự |
| `LENGTHB` | Byte | Giới hạn kích thước lưu/trao đổi byte |
| `LENGTHC` | Unicode complete characters | Khi cần cách đếm ký tự hoàn chỉnh theo ngữ nghĩa Unicode mà Oracle hỗ trợ |
| `LENGTH2` | UCS2 code points | Khi giao tiếp với hệ thống dùng đơn vị UCS-2 |
| `LENGTH4` | UCS4 code points | Khi cần đếm theo đơn vị UCS-4 |

Các biến thể `C`, `2`, `4` có mục đích chuyên biệt; phần lớn ứng dụng SQL thông thường nên bắt đầu bằng `LENGTH` và chỉ chọn biến thể khác khi hợp đồng encoding yêu cầu. Một số biến thể có hạn chế đối với `CLOB`/`NCLOB`; kiểm tra tài liệu Oracle cho kiểu LOB và phiên bản đang sử dụng.

### 5.3. CHAR và VARCHAR2 có thể cho độ dài khác dự kiến

`CHAR(n)` là kiểu độ dài cố định và được blank-pad theo quy tắc SQL; `VARCHAR2(n)` lưu chuỗi có độ dài thay đổi. Ví dụ:

```sql
SELECT LENGTH(CAST('SQL' AS CHAR(10))) AS char_length,
       LENGTH(CAST('SQL' AS VARCHAR2(10))) AS varchar_length
FROM dual;
```

Giá trị `CHAR(10)` có thể được đệm bằng khoảng trắng đến độ dài 10, trong khi `VARCHAR2` chỉ giữ ba ký tự `SQL`. Do đó khi kiểm tra dữ liệu legacy, hãy xác định kiểu cột trước khi kết luận chuỗi có “dư khoảng trắng”.

### 5.4. Chuỗi rỗng và NULL

Trong SQL Oracle, chuỗi ký tự độ dài bằng 0 được xem như `NULL`:

```sql
SELECT LENGTH('') AS empty_length,
       LENGTH(NULL) AS null_length,
       LENGTH(' ') AS one_blank_length
FROM dual;
```

Hai biểu thức đầu trả `NULL`; biểu thức cuối trả 1. Đây là điểm quan trọng khi viết:

```sql
WHERE LENGTH(product_code) = 0
```

Điều kiện này không tìm các chuỗi rỗng như trong một số hệ quản trị khác; dùng `IS NULL` để kiểm tra giá trị NULL:

```sql
WHERE product_code IS NULL
```

### 5.5. Độ dài chuỗi LOB

Với `CLOB`/`NCLOB`, `LENGTH` có thể trả số ký tự của nội dung LOB theo hỗ trợ Oracle. `LENGTHB` không phải lựa chọn tổng quát cho LOB trong môi trường character set đa byte. Nếu đang xử lý LOB lớn, xem `DBMS_LOB.GETLENGTH` và các API LOB thay vì cố chuyển toàn bộ nội dung thành `VARCHAR2`.

Ví dụ:

```sql
SELECT DBMS_LOB.GETLENGTH(document_body) AS document_length
FROM document_store
WHERE document_id = :document_id;
```

Đơn vị và ngữ nghĩa của độ dài phụ thuộc kiểu LOB; đối với CLOB, kết quả là số ký tự, còn BLOB là số byte.

## 6. TRIM — loại ký tự ở đầu hoặc cuối

### 6.1. Cú pháp

```sql
TRIM(
    [LEADING | TRAILING | BOTH]
    [trim_character]
    FROM source_string
)
```

- `BOTH`: loại ký tự ở cả đầu và cuối; đây là mặc định.
- `LEADING`: chỉ loại ở đầu.
- `TRAILING`: chỉ loại ở cuối.
- `trim_character`: một ký tự muốn loại; nếu bỏ qua, Oracle dùng khoảng trắng thông thường.

Ví dụ:

```sql
SELECT TRIM('  Oracle SQL  ') AS both_sides,
       TRIM(LEADING FROM '  Oracle SQL  ') AS leading_only,
       TRIM(TRAILING FROM '  Oracle SQL  ') AS trailing_only,
       TRIM(BOTH '-' FROM '---A-100---') AS hyphen_trimmed
FROM dual;
```

Kết quả:

| BOTH_SIDES | LEADING_ONLY | TRAILING_ONLY | HYPHEN_TRIMMED |
|---|---|---|---|
| `Oracle SQL` | `Oracle SQL  ` | `  Oracle SQL` | `A-100` |

`TRIM` chỉ loại ký tự ở biên. Nó không xóa ký tự tương tự ở giữa chuỗi: `TRIM('A-B-A')` không làm mất dấu gạch ngang ở giữa.

### 6.2. TRIM ký tự cụ thể

Ví dụ bỏ dấu `0` ở đầu và cuối mã:

```sql
SELECT TRIM(BOTH '0' FROM '0001234000') AS trimmed_code,
       TRIM(LEADING '0' FROM '0001234000') AS leading_zero_removed,
       TRIM(TRAILING '0' FROM '0001234000') AS trailing_zero_removed
FROM dual;
```

Kết quả lần lượt là `1234`, `1234000` và `0001234`. Điều này khác với `REPLACE`, vì `REPLACE` có thể xóa hoặc thay mọi lần xuất hiện ở cả giữa chuỗi.

Trong cú pháp SQL `TRIM`, ký tự trim được chỉ định là **một ký tự**; nếu muốn loại một tập nhiều ký tự khác nhau ở biên, xem `LTRIM`/`RTRIM`. Không viết `TRIM(BOTH 'abc' FROM ...)` với ý nghĩa “loại bất kỳ a, b hoặc c”; đây không phải cú pháp set như LTRIM/RTRIM.

### 6.3. TRIM không đồng nghĩa loại mọi whitespace

Mặc định, `TRIM` loại khoảng trắng thông thường (blank/space). Nó không tự động xóa mọi loại ký tự mà mắt người nhìn thấy như khoảng trắng, bao gồm tab, line feed, carriage return, non-breaking space hoặc các ký tự Unicode whitespace khác.

Ví dụ:

```sql
SELECT LENGTH(' A ') AS before_length,
       LENGTH(TRIM(' A ')) AS after_length,
       LENGTH('A' || CHR(9)) AS tab_length,
       LENGTH(TRIM('A' || CHR(9))) AS tab_after_trim
FROM dual;
```

Tab ở cuối không được mặc định coi như blank thông thường để `TRIM` loại bỏ. Nếu dữ liệu đến từ file hoặc hệ thống ngoài, cần xác định chính xác các ký tự cần chuẩn hóa.

Có thể loại tab/CR/LF ở biên bằng cách kết hợp hàm:

```sql
SELECT TRIM(
           BOTH CHR(9) FROM
           TRIM(
               BOTH CHR(10) FROM
               TRIM(BOTH CHR(13) FROM source_text)
           )
       ) AS normalized_edges
FROM imported_text;
```

Đây là ví dụ minh họa cho một số ký tự ASCII điều khiển; nó không phải bộ trim Unicode tổng quát và thứ tự lồng có thể quan trọng khi các ký tự xen kẽ nhau. Với NBSP, có thể xác định ký tự rõ ràng bằng biểu thức phù hợp character set, ví dụ `UNISTR('\00A0')`, rồi xử lý theo contract dữ liệu.

### 6.4. LTRIM và RTRIM khác TRIM thế nào?

`LTRIM` và `RTRIM` nhận một **set ký tự** để loại liên tiếp ở biên:

```sql
SELECT LTRIM('000ABC', '0') AS left_zero_removed,
       RTRIM('ABCxxx', 'x') AS right_x_removed,
       LTRIM('xyxyABC', 'xy') AS left_set_removed
FROM dual;
```

Trong ví dụ `LTRIM('xyxyABC', 'xy')`, Oracle loại các ký tự đầu thuộc tập `x` hoặc `y` cho tới khi gặp ký tự khác. Đây không phải tìm và loại đúng chuỗi con `'xy'` theo từng cặp.

| Hàm | Cách xử lý |
|---|---|
| `TRIM(BOTH 'x' FROM s)` | Loại một ký tự `x` ở hai biên |
| `LTRIM(s, 'xyz')` | Loại liên tiếp ký tự đầu thuộc tập `x`, `y`, `z` |
| `RTRIM(s, 'xyz')` | Loại liên tiếp ký tự cuối thuộc tập `x`, `y`, `z` |

Nếu yêu cầu là xóa một **chuỗi nhiều ký tự chính xác** ở đầu/cuối, cần kết hợp `SUBSTR`/`INSTR` hoặc một cách xử lý khác; không nhầm với tập ký tự của `LTRIM`/`RTRIM`.

## 7. REPLACE — thay thế mọi lần xuất hiện

### 7.1. Cú pháp

```sql
REPLACE(char, search_string [, replacement_string])
```

- `char`: chuỗi nguồn.
- `search_string`: chuỗi con cần tìm.
- `replacement_string`: chuỗi thay thế; nếu bỏ qua hoặc là NULL, các lần xuất hiện tìm thấy sẽ bị loại khỏi chuỗi.

Ví dụ:

```sql
SELECT REPLACE('A-B-A-B', 'A', 'X') AS replace_a,
       REPLACE('A-B-A-B', '-', '/') AS replace_delimiter,
       REPLACE('A-B-A-B', 'A') AS remove_a
FROM dual;
```

| REPLACE_A | REPLACE_DELIMITER | REMOVE_A |
|---|---|---|
| `X-B-X-B` | `A/B/A/B` | `-B--B` |

`REPLACE` thay **tất cả** lần xuất hiện của chuỗi con phù hợp, không chỉ lần đầu tiên. Nó không hỗ trợ tham số occurrence như `INSTR`.

### 7.2. Xóa hoặc chuẩn hóa delimiter

Ví dụ chuẩn hóa mã không còn dấu gạch:

```sql
SELECT product_code,
       REPLACE(product_code, '-', '') AS compact_code
FROM string_lab
ORDER BY item_id;
```

Hoặc thay nhiều ký tự cần xử lý bằng cách lồng hàm:

```sql
SELECT REPLACE(
           REPLACE(note_text, CHR(13), ' '),
           CHR(10),
           ' '
       ) AS one_line_note
FROM string_lab;
```

Lồng `REPLACE` có thể dễ đọc khi chỉ có vài quy tắc cố định. Nếu phải thay hàng chục mẫu hoặc dùng quy tắc pattern, hãy cân nhắc `REGEXP_REPLACE` hay quy trình chuẩn hóa riêng; regex có chi phí và cú pháp phức tạp hơn nên không cần dùng cho mọi trường hợp.

### 7.3. Phân biệt hoa/thường và ký tự thay thế

Ví dụ:

```sql
SELECT REPLACE('Oracle oracle ORACLE', 'oracle', 'DB')
       AS replace_lowercase
FROM dual;
```

Trong quy tắc so khớp thông thường, `REPLACE` phân biệt chữ hoa/thường. Nếu muốn chuẩn hóa case trước khi thay:

```sql
SELECT REPLACE(LOWER('Oracle oracle ORACLE'), 'oracle', 'db')
       AS normalized
FROM dual;
```

Kết quả không giữ nguyên cách viết hoa ban đầu; vì vậy chỉ áp dụng khi nghiệp vụ chấp nhận mất thông tin case. Các yêu cầu so sánh theo ngôn ngữ hoặc collation cụ thể cần được thiết kế và kiểm tra theo cấu hình Oracle.

### 7.4. NULL và chuỗi rỗng trong REPLACE

Oracle xem chuỗi rỗng là NULL, nên:

- Nếu chuỗi nguồn là NULL, kết quả là NULL.
- Nếu `search_string` là NULL, hàm trả chuỗi nguồn theo ngữ nghĩa Oracle.
- Nếu `replacement_string` là NULL hoặc chuỗi rỗng, các lần tìm thấy sẽ bị loại.

Ví dụ:

```sql
SELECT REPLACE('A-B-A', 'A', NULL) AS remove_a,
       REPLACE('A-B-A', NULL, 'X') AS null_search,
       REPLACE(NULL, 'A', 'X') AS null_source
FROM dual;
```

Không dùng `REPLACE(col, 'x', '')` để “ghi một chuỗi rỗng khác NULL” trong Oracle SQL thông thường; chuỗi rỗng và NULL có cùng cách xử lý ở đây. Nếu nghiệp vụ cần biểu diễn trạng thái “không có”, “chưa biết” và “chuỗi trống” riêng biệt, cần một cột trạng thái hoặc quy ước dữ liệu khác.

### 7.5. REPLACE không phải REGEXP_REPLACE

`REPLACE` tìm một chuỗi con literal. Ví dụ `REPLACE(phone, '-', '')` xóa dấu gạch ngang. Nó không hiểu pattern như “mọi chữ số” hoặc “mọi ký tự không phải chữ cái”.

Nếu yêu cầu phức tạp:

```sql
SELECT REGEXP_REPLACE('AB-123-CD', '[^A-Z]', '') AS letters_only
FROM dual;
```

thì `REGEXP_REPLACE` là hàm khác, sử dụng regular expression. Đừng dùng regex cho một phép thay literal đơn giản nếu `REPLACE` đã đủ rõ ràng.

## 8. Kết hợp INSTR và SUBSTR để tách trường

### 8.1. Lấy phần trước dấu @ trong email

```sql
SELECT email_address,
       SUBSTR(
           email_address,
           1,
           INSTR(email_address, '@') - 1
       ) AS local_part
FROM string_lab
WHERE INSTR(email_address, '@') > 1;
```

`INSTR` tìm dấu phân cách; `SUBSTR` lấy phần đứng trước nó. Điều kiện `WHERE` loại trường hợp thiếu dấu `@` hoặc dấu nằm ở vị trí đầu. Đây là ví dụ parse chuỗi, không phải quy tắc RFC để kiểm tra email.

### 8.2. Lấy domain sau @

```sql
SELECT email_address,
       SUBSTR(
           email_address,
           INSTR(email_address, '@') + 1
       ) AS domain_part
FROM string_lab
WHERE INSTR(email_address, '@') > 0;
```

### 8.3. Lấy phần mở rộng file theo dấu chấm cuối

```sql
SELECT file_name,
       CASE
           WHEN INSTR(file_name, '.', -1) > 0
           THEN SUBSTR(
                    file_name,
                    INSTR(file_name, '.', -1) + 1
                )
           ELSE NULL
       END AS extension
FROM string_lab
ORDER BY item_id;
```

Với `archive.tar.gz`, kết quả là `gz`; với `report.final.v2.xlsx`, kết quả là `xlsx`; với `README`, không có dấu chấm nên kết quả `NULL`.

Nếu tên file là `.env`, cách này trả `env` dù một số hệ thống xem `.env` là tên file ẩn chứ không phải file có extension. Với `archive.`, kết quả có thể là chuỗi rỗng/NULL. Cần bổ sung quy tắc nghiệp vụ nếu muốn phân biệt những trường hợp đó.

### 8.4. Lấy phần đầu và phần cuối của mã

Với mã dạng `REGION-TYPE-SEQUENCE`, có thể lấy token đầu/cuối:

```sql
SELECT product_code,
       SUBSTR(product_code, 1, INSTR(product_code, '-') - 1)
           AS first_token,
       SUBSTR(product_code, INSTR(product_code, '-', -1) + 1)
           AS last_token
FROM string_lab
WHERE INSTR(product_code, '-') > 0;
```

Ví dụ này phù hợp khi có ít nhất một dấu gạch ngang. Nếu chuỗi có cấu trúc biến đổi hoặc delimiter có thể xuất hiện trong dữ liệu, nên kiểm tra số lần xuất hiện và định nghĩa contract trước khi parse.

### 8.5. Lấy token giữa hai delimiter

Giả sử chuỗi `A|B|C` và cần token thứ hai:

```sql
WITH source_data AS (
    SELECT 'A|B|C' AS text_value FROM dual
),
positions AS (
    SELECT text_value,
           INSTR(text_value, '|', 1, 1) AS first_delim,
           INSTR(text_value, '|', 1, 2) AS second_delim
    FROM source_data
)
SELECT SUBSTR(
           text_value,
           first_delim + 1,
           second_delim - first_delim - 1
       ) AS second_token
FROM positions
WHERE first_delim > 0
  AND second_delim > first_delim;
```

Kết quả là `B`. Việc tách token bằng `INSTR`/`SUBSTR` rất hữu ích với format đơn giản, delimiter rõ ràng. Nếu trường dữ liệu được quote và bản thân nó có thể chứa delimiter, ví dụ CSV có `"Nguyễn, An"`, cách tách này không đủ; phải dùng parser CSV hoặc external table access parameters phù hợp.

## 9. Làm sạch và chuẩn hóa dữ liệu chuỗi

### 9.1. Loại khoảng trắng ở hai biên

Dữ liệu từ form, file CSV hoặc copy/paste có thể có blank ở đầu/cuối:

```sql
SELECT customer_name,
       TRIM(customer_name) AS normalized_name
FROM string_lab
ORDER BY item_id;
```

Có thể dùng trong câu cập nhật:

```sql
UPDATE string_lab
SET customer_name = TRIM(customer_name)
WHERE customer_name IS NOT NULL;
```

Đây là DML thay đổi dữ liệu thật; chỉ thực hiện trên lab hoặc sau khi có chính sách kiểm tra, backup và transaction phù hợp. Không chạy update hàng loạt trên production chỉ vì nhìn thấy vài giá trị có blank.

### 9.2. Chuẩn hóa mã sản phẩm

Nếu quy ước mã không chứa dấu gạch và không có blank đầu/cuối:

```sql
SELECT item_id,
       REPLACE(TRIM(product_code), '-', '') AS canonical_code
FROM string_lab
ORDER BY item_id;
```

Nếu mã không phân biệt hoa/thường theo nghiệp vụ:

```sql
SELECT UPPER(REPLACE(TRIM(product_code), '-', ''))
       AS normalized_code
FROM string_lab;
```

Đừng tự động đổi case với tên người, nội dung tự do hoặc mã có phân biệt hoa/thường. Chuẩn hóa phải là một quy tắc nghiệp vụ được thống nhất ở mọi hệ thống.

### 9.3. Tách dữ liệu tốt và dữ liệu không hợp lệ

Ví dụ một cột mã bắt buộc có độ dài từ 5 đến 20 ký tự và phải có dấu gạch:

```sql
SELECT product_code,
       CASE
           WHEN product_code IS NULL THEN 'MISSING'
           WHEN LENGTH(TRIM(product_code)) < 5 THEN 'TOO_SHORT'
           WHEN LENGTH(TRIM(product_code)) > 20 THEN 'TOO_LONG'
           WHEN INSTR(product_code, '-') = 0 THEN 'NO_SEPARATOR'
           ELSE 'CANDIDATE'
       END AS validation_status
FROM string_lab;
```

Đây là kiểm tra hình thức đơn giản. Nó không chứng minh mã tồn tại trong danh mục hoặc đúng quy tắc từng loại sản phẩm. Các điều kiện nghiệp vụ quan trọng nên được enforce bằng constraint, foreign key hoặc logic validation có thể kiểm thử.

## 10. Character semantics, byte semantics và Unicode

### 10.1. BYTE và CHAR trong khai báo VARCHAR2

Khi khai báo:

```sql
CREATE TABLE name_byte_lab (
    name_value VARCHAR2(20 BYTE)
);

CREATE TABLE name_char_lab (
    name_value VARCHAR2(20 CHAR)
);
```

Hai cột đặt giới hạn khác nhau:

- `VARCHAR2(20 BYTE)` giới hạn kích thước theo byte.
- `VARCHAR2(20 CHAR)` giới hạn theo số ký tự (vẫn chịu giới hạn byte tối đa của kiểu và cấu hình database).

Trong AL32UTF8, một ký tự có thể chiếm từ 1 tới nhiều byte. Một chuỗi 20 ký tự tiếng Việt có dấu có thể không vừa giới hạn 20 byte, dù vừa giới hạn 20 CHAR.

### 10.2. Hàm xử lý ký tự và biến thể B/C/2/4

Oracle cung cấp các biến thể để xác định đơn vị thao tác:

| Nhóm | Theo ký tự | Theo byte | Theo Unicode complete character / UCS |
|---|---|---|---|
| Đếm | `LENGTH` | `LENGTHB` | `LENGTHC`, `LENGTH2`, `LENGTH4` |
| Tìm | `INSTR` | `INSTRB` | `INSTRC`, `INSTR2`, `INSTR4` |
| Cắt | `SUBSTR` | `SUBSTRB` | `SUBSTRC`, `SUBSTR2`, `SUBSTR4` |

Không trộn vị trí tính theo byte với vị trí tính theo ký tự. Ví dụ `INSTRB` có thể trả byte offset; đưa trực tiếp kết quả đó vào `SUBSTR` (đếm ký tự) sẽ sai khi chuỗi có ký tự đa byte. Nếu đã bắt đầu xử lý theo byte, cần giữ nhất quán mọi phép tính và phải đảm bảo không cắt giữa một mã ký tự.

### 10.3. Ví dụ so sánh

```sql
SELECT LENGTH('Đặng') AS char_count,
       LENGTHB('Đặng') AS byte_count,
       SUBSTR('Đặng', 1, 2) AS first_two_chars
FROM dual;
```

Kết quả byte cụ thể phụ thuộc database character set. Trên AL32UTF8, chữ tiếng Việt có dấu có thể chiếm nhiều byte; đừng ghi cứng số byte mong đợi nếu chưa xác nhận `NLS_CHARACTERSET`.

DBA có thể kiểm tra character set:

```sql
SELECT parameter, value
FROM nls_database_parameters
WHERE parameter IN (
    'NLS_CHARACTERSET',
    'NLS_NCHAR_CHARACTERSET'
)
ORDER BY parameter;
```

`NLS_CHARACTERSET` cho biết character set của database; `NLS_NCHAR_CHARACTERSET` liên quan kiểu NCHAR/NVARCHAR2/NCLOB. Không dùng `NLS_SESSION_PARAMETERS` để suy ra character set lưu trữ của database.

### 10.4. Unicode code point không luôn bằng ký tự người dùng nhìn thấy

Một chữ hiển thị có thể được biểu diễn bằng một code point hoặc tổ hợp nhiều code point (ví dụ chữ và dấu kết hợp). Các hàm `LENGTH`/`SUBSTR` làm việc theo quy tắc đơn vị ký tự mà Oracle hỗ trợ, không phải lúc nào cũng tương đương số “grapheme cluster” mà người dùng nhìn thấy trên màn hình.

Với dữ liệu Unicode phức tạp, nếu yêu cầu không được cắt giữa một cụm ký tự hiển thị, cần xử lý ở tầng Unicode-aware application (ví dụ Java với thư viện phù hợp) và kiểm thử dữ liệu thực tế. Không giả định `SUBSTR` luôn tương đương “lấy N ký tự người dùng nhìn thấy”.

## 11. NULL, khoảng trắng và phép so sánh

### 11.1. TRIM không biến NULL thành chuỗi có dữ liệu

`TRIM(NULL)` trả NULL; `TRIM('   ')` trả chuỗi rỗng, mà Oracle SQL xem là NULL. Do đó:

```sql
SELECT CASE
           WHEN TRIM(customer_name) IS NULL THEN 'EMPTY_OR_BLANK'
           ELSE 'HAS_TEXT'
       END AS name_state
FROM string_lab;
```

có thể nhận diện chuỗi chỉ gồm blank thông thường và giá trị NULL như cùng một nhóm. Nếu nghiệp vụ phải phân biệt “chưa nhập” với “đã nhập nhưng toàn khoảng trắng”, cần ghi nhận riêng trạng thái nguồn trước khi chuẩn hóa.

### 11.2. So sánh CHAR và VARCHAR2

Oracle có quy tắc so sánh blank-padded cho một số phép so sánh giữa hai giá trị kiểu CHAR, và nonpadded semantics trong các trường hợp có VARCHAR2/NVARCHAR2. Vì vậy, dữ liệu CHAR có thể so sánh bằng với chuỗi ngắn hơn trong một tình huống mà người viết không mong đợi.

Khi cần chuẩn hóa dữ liệu đầu vào, hãy dùng kiểu dữ liệu đúng, ràng buộc độ dài và quy tắc trim rõ ràng. Không dùng `TRIM` ở mọi phép so sánh một cách máy móc vì có thể thay đổi ý nghĩa của mã mà khoảng trắng là ký tự hợp lệ.

### 11.3. Hàm trả NULL và điều kiện WHERE

Ví dụ:

```sql
SELECT item_id
FROM string_lab
WHERE INSTR(product_code, 'XYZ') = 0;
```

Điều kiện này tìm những chuỗi không chứa `XYZ`. Nếu `product_code` là NULL, `INSTR` cũng trả NULL và biểu thức `NULL = 0` không phải TRUE; hàng không được trả về. Nếu muốn đưa cả giá trị NULL vào nhóm “không chứa XYZ”, viết rõ:

```sql
SELECT item_id
FROM string_lab
WHERE product_code IS NULL
   OR INSTR(product_code, 'XYZ') = 0;
```

Đây là logic SQL ba giá trị: TRUE, FALSE, UNKNOWN. Hãy kiểm tra NULL tường minh khi hàm chuỗi tham gia điều kiện lọc.

## 12. Hiệu năng: dùng hàm trên cột trong WHERE

### 12.1. Hàm bao quanh cột có thể làm index thông thường khó được dùng

Giả sử có B-tree index:

```sql
CREATE INDEX ix_string_lab_code
ON string_lab(product_code);
```

Điều kiện:

```sql
SELECT *
FROM string_lab
WHERE TRIM(product_code) = 'PRD-2026-001';
```

đang áp dụng `TRIM` lên giá trị cột. Index thông thường trên `product_code` lưu giá trị gốc, không trực tiếp lưu `TRIM(product_code)`. Vì thế optimizer có thể không dùng index đó cho phép so sánh này, hoặc chọn một plan khác tùy statistics và cost.

Nếu dữ liệu luôn cần được trim, cân nhắc chuẩn hóa ngay lúc nhập hoặc tạo **function-based index** khi thực sự cần:

```sql
CREATE INDEX ix_string_lab_trim_code
ON string_lab(TRIM(product_code));
```

Sau đó điều kiện tương thích biểu thức index có thể sử dụng index theo plan. Việc tạo index cần quyền, không gian và đánh giá chi phí DML; không tạo hàng loạt function-based index chỉ để sửa từng câu SQL.

### 12.2. Function-based index và NULL

Ví dụ index chuẩn hóa case:

```sql
CREATE INDEX ix_string_lab_email_lower
ON string_lab(LOWER(email_address));

SELECT item_id
FROM string_lab
WHERE LOWER(email_address) = LOWER(:email);
```

Oracle có thể sử dụng function-based index nếu biểu thức, statistics, tính chọn lọc và cost phù hợp. Với index expression có kết quả NULL, hành vi lưu/index phụ thuộc cấu trúc và loại index; cần xem tài liệu và execution plan thực tế.

### 12.3. INSTR và LIKE

Điều kiện:

```sql
WHERE INSTR(product_code, '2026') > 0
```

tìm chuỗi con ở bất kỳ vị trí nào. Một B-tree index thông thường không thuận lợi cho việc tìm substring ở mọi vị trí.

Nếu nghiệp vụ chỉ cần prefix:

```sql
WHERE product_code LIKE 'PRD-2026%'
```

có thể phù hợp hơn với B-tree index trong cấu hình/điều kiện collation thích hợp. Không có bảo đảm mọi truy vấn LIKE đều dùng index; ký tự wildcard ở đầu như `LIKE '%2026%'` thường khiến B-tree khó hỗ trợ range scan.

Nếu yêu cầu tìm kiếm toàn văn hoặc token phức tạp, cân nhắc Oracle Text hoặc cấu trúc search riêng thay vì lồng nhiều `INSTR` trên bảng lớn.

### 12.4. Đo execution plan thay vì đoán

```sql
EXPLAIN PLAN FOR
SELECT item_id
FROM string_lab
WHERE TRIM(product_code) = 'PRD-2026-001';

SELECT *
FROM TABLE(DBMS_XPLAN.DISPLAY);
```

`EXPLAIN PLAN` cho biết kế hoạch dự kiến; khi cần đánh giá thực thi, sử dụng thống kê thực tế như `DBMS_XPLAN.DISPLAY_CURSOR` theo quyền và chính sách môi trường. Dữ liệu lab ít hàng có thể khiến full table scan là lựa chọn đúng và rẻ hơn index.

## 13. Dùng hàm chuỗi trong UPDATE, INSERT và MERGE

### 13.1. Chuẩn hóa trước khi lưu

Một quy trình nạp mã:

```sql
INSERT INTO product_catalog (
    product_code,
    product_name
)
SELECT UPPER(REPLACE(TRIM(raw_code), ' ', '')),
       TRIM(raw_name)
FROM product_import_stage
WHERE raw_code IS NOT NULL;
```

Ví dụ này loại blank ở hai biên, xóa khoảng trắng thông thường ở mọi vị trí của mã và chuẩn hóa chữ hoa. Chỉ đúng nếu contract sản phẩm quy định khoảng trắng trong mã không có ý nghĩa. Không áp dụng cùng logic cho tên người, địa chỉ hoặc văn bản tự do.

### 13.2. Cập nhật có điều kiện

```sql
UPDATE string_lab
SET email_address = LOWER(TRIM(email_address))
WHERE email_address IS NOT NULL;
```

Việc chuyển email về chữ thường có thể phù hợp với chính sách ứng dụng, nhưng phải hiểu quy tắc định danh của hệ thống và collation. Một số phần của email theo chuẩn kỹ thuật có ngữ nghĩa case khác nhau; nhiều hệ thống nghiệp vụ chọn so sánh không phân biệt case theo chính sách riêng. Không tự đổi dữ liệu lịch sử nếu chưa thống nhất.

### 13.3. Không tạo câu SQL bằng nối chuỗi người dùng nhập

Không viết:

```sql
-- Mẫu nguy hiểm khi giá trị đến từ input:
sql_text := 'SELECT ... WHERE name = ''' || user_input || '''';
```

Dùng bind parameter:

```sql
SELECT item_id
FROM string_lab
WHERE customer_name = :name;
```

Các hàm `TRIM`/`REPLACE` không thay thế cơ chế chống SQL injection. Nếu cần chuẩn hóa input, làm ở tầng dữ liệu phù hợp rồi bind giá trị; không nối chuỗi SQL động chỉ vì đang xử lý văn bản.

## 14. Kết hợp với các hàm khác khi bài toán vượt quá năm hàm cơ bản

| Nhu cầu | Hàm/cơ chế có thể phù hợp |
|---|---|
| Tìm pattern phức tạp | `REGEXP_INSTR`, `REGEXP_SUBSTR` |
| Thay theo biểu thức chính quy | `REGEXP_REPLACE` |
| Đổi hoa/thường | `UPPER`, `LOWER`, `INITCAP` |
| Nối chuỗi | `||`, `CONCAT` |
| Tách/đọc LOB lớn | `DBMS_LOB` và API LOB |
| Chuyển kiểu số/ngày thành văn bản rõ định dạng | `TO_CHAR` với format mask |
| Chuẩn hóa Unicode | Quy trình Unicode-aware tại ứng dụng hoặc công cụ được thiết kế phù hợp |
| Parse JSON | JSON SQL functions, không tự cắt chuỗi JSON bằng SUBSTR |

Không dùng `SUBSTR` để parse JSON/XML hoặc CSV phức tạp nếu Oracle đã có parser chuyên dụng. Việc cắt chuỗi theo dấu phẩy sẽ sai khi giá trị có dấu phẩy được quote; việc cắt JSON theo dấu ngoặc sẽ sai khi nội dung string có escape.

## 15. Ví dụ tổng hợp: chuẩn hóa và tách mã nhập liệu

Giả sử hệ thống nhận chuỗi mã dạng:

```text
  prd-2026-001
PRD-2026-002
srv-db-015
invalidcode
```

Ta muốn:

1. Loại khoảng trắng đầu/cuối.
2. Chuẩn hóa chữ hoa.
3. Kiểm tra có ít nhất hai dấu gạch nối.
4. Lấy nhóm, năm và số thứ tự với format mã sản phẩm.

```sql
WITH normalized AS (
    SELECT item_id,
           UPPER(TRIM(product_code)) AS code
    FROM string_lab
),
positions AS (
    SELECT item_id,
           code,
           INSTR(code, '-', 1, 1) AS dash_1,
           INSTR(code, '-', 1, 2) AS dash_2
    FROM normalized
)
SELECT item_id,
       code,
       CASE
           WHEN dash_1 > 1
            AND dash_2 > dash_1 + 1
            AND INSTR(code, '-', 1, 3) = 0
           THEN SUBSTR(code, 1, dash_1 - 1)
       END AS code_group,
       CASE
           WHEN dash_2 > dash_1 + 1
           THEN SUBSTR(code, dash_1 + 1, dash_2 - dash_1 - 1)
       END AS code_year,
       CASE
           WHEN dash_2 > 0
            AND INSTR(code, '-', 1, 3) = 0
           THEN SUBSTR(code, dash_2 + 1)
       END AS sequence_no,
       CASE
           WHEN dash_1 > 1
            AND dash_2 > dash_1 + 1
            AND INSTR(code, '-', 1, 3) = 0
           THEN 'STRUCTURE_OK'
           ELSE 'INVALID_STRUCTURE'
       END AS validation_result
FROM positions
ORDER BY item_id;
```

Đây là kiểm tra cấu trúc sơ bộ. Nếu năm phải đúng bốn chữ số, sequence phải ba chữ số và nhóm chỉ được chứa ký tự A–Z, cần thêm validation cụ thể. Với format pattern phức tạp, `REGEXP_LIKE` có thể diễn đạt dễ đọc hơn:

```sql
SELECT product_code
FROM string_lab
WHERE REGEXP_LIKE(
    UPPER(TRIM(product_code)),
    '^[A-Z]{3}-[0-9]{4}-[0-9]{3}$'
);
```

`REGEXP_LIKE` chỉ xác nhận pattern; nó không chứng minh mã tồn tại trong danh mục, năm có ý nghĩa nghiệp vụ hoặc số thứ tự chưa được sử dụng. Ràng buộc duy nhất và tham chiếu danh mục vẫn cần được thiết kế riêng.

## 16. Các lỗi và bẫy thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| `SUBSTR` trả NULL | Length nhỏ hơn 1, nguồn NULL/rỗng hoặc vị trí không tạo ra đoạn hợp lệ | Kiểm tra position, length và NULL trước khi cắt |
| `SUBSTR` lấy sai ký tự tiếng Việt | Dùng biến thể theo byte hoặc nhầm byte offset với character offset | Dùng `SUBSTR` theo ký tự, xác định character set |
| `INSTR` trả 0 | Không tìm thấy substring | Kiểm tra delimiter trước khi trừ vị trí hoặc truyền length vào SUBSTR |
| `INSTR` không tìm thấy chữ hoa/thường như mong muốn | So khớp phân biệt case theo ngữ cảnh | Chuẩn hóa hai phía hoặc chọn collation phù hợp |
| `LENGTH` không bằng LENGTHB | Ký tự đa byte | Phân biệt giới hạn ký tự và byte |
| `LENGTH('')` không trả 0 | Oracle xem chuỗi rỗng là NULL | Dùng `IS NULL` và quy ước trạng thái dữ liệu |
| `TRIM` không xóa tab/line break | Default trim chỉ xử lý blank thông thường | Xử lý các control characters cụ thể |
| `TRIM(BOTH 'abc' FROM ...)` lỗi | trim_character của TRIM là một ký tự, không phải set | Dùng LTRIM/RTRIM hoặc logic riêng |
| `REPLACE` xóa nhiều chỗ hơn mong muốn | REPLACE thay tất cả lần xuất hiện | Chọn pattern/logic đúng; không giả định chỉ thay lần đầu |
| `REPLACE` không đổi chữ hoa | So khớp case khác với dữ liệu | Chuẩn hóa case nếu nghiệp vụ cho phép |
| Query chậm sau khi bọc cột bằng TRIM/LOWER | Index thường không khớp biểu thức | Chuẩn hóa dữ liệu, function-based index, xem plan |
| Tách CSV bằng INSTR/SUBSTR bị sai | Giá trị có delimiter nằm trong quoted field hoặc newline | Dùng CSV parser/external table đúng format |
| Kết quả khác giữa môi trường | NLS, character set, collation hoặc kiểu cột khác | Kiểm tra DDL và tham số môi trường |

## 17. Bài thực hành có hướng dẫn

Thực hiện trong schema lab. Nếu đã tạo bảng `STRING_LAB` ở đầu bài, dùng lại; nếu không, chạy phần chuẩn bị trước.

### Bài 1 — SUBSTR và vị trí âm

Chạy:

```sql
SELECT SUBSTR('DATABASE', 1, 4) AS a,
       SUBSTR('DATABASE', 5) AS b,
       SUBSTR('DATABASE', -4) AS c,
       SUBSTR('DATABASE', 0, 3) AS d
FROM dual;
```

Ghi kết quả và giải thích vị trí 0, vị trí âm. Thử length bằng 0 và -1 để quan sát NULL.

### Bài 2 — INSTR và occurrence

```sql
SELECT INSTR('A-B-C-D', '-', 1, 1) AS first_delimiter,
       INSTR('A-B-C-D', '-', 1, 3) AS third_delimiter,
       INSTR('A-B-C-D', '-', -1, 2) AS second_from_right,
       INSTR('A-B-C-D', 'X') AS not_found
FROM dual;
```

Vẽ vị trí từng ký tự, xác định kết quả theo 1-based index. Thử `position` âm và `occurrence` khác nhau để không nhầm hướng tìm với số lần xuất hiện.

### Bài 3 — Đếm ký tự và byte

```sql
SELECT LENGTH('ABC') AS ascii_chars,
       LENGTHB('ABC') AS ascii_bytes,
       LENGTH('Đặng') AS viet_chars,
       LENGTHB('Đặng') AS viet_bytes
FROM dual;
```

Kiểm tra database character set, giải thích vì sao kết quả byte phụ thuộc encoding.

### Bài 4 — TRIM, LTRIM, RTRIM

```sql
SELECT TRIM('  00123  ') AS default_trim,
       TRIM(LEADING '0' FROM '000123') AS trim_leading_zero,
       TRIM(TRAILING '-' FROM 'ABC---') AS trim_trailing,
       LTRIM('xyxyABC', 'xy') AS trim_character_set
FROM dual;
```

Giải thích vì sao `LTRIM` với set `'xy'` loại từng ký tự thuộc set chứ không tìm đúng chuỗi con `'xy'`. Thử tab bằng `CHR(9)`.

### Bài 5 — REPLACE

```sql
SELECT REPLACE('A-B-A-B', 'A', 'X') AS replace_all,
       REPLACE('A-B-A-B', '-') AS remove_delimiter,
       REPLACE('Oracle ORACLE oracle', 'oracle', 'DB') AS case_result
FROM dual;
```

Ghi lại số lần thay và lý do chữ hoa/thường có thể không được thay đồng thời.

### Bài 6 — Tách email và tên file

```sql
SELECT email_address,
       SUBSTR(email_address, 1, INSTR(email_address, '@') - 1)
           AS local_part,
       SUBSTR(email_address, INSTR(email_address, '@') + 1)
           AS domain_part
FROM string_lab
WHERE INSTR(email_address, '@') > 0;

SELECT file_name,
       CASE
           WHEN INSTR(file_name, '.', -1) > 0
           THEN SUBSTR(file_name, INSTR(file_name, '.', -1) + 1)
       END AS extension
FROM string_lab;
```

Thêm các trường hợp thiếu dấu `@`, tên file không có dấu chấm, `.env` và `archive.` để xác định chính sách parse.

### Bài 7 — Chuẩn hóa mã có điều kiện

```sql
SELECT product_code,
       UPPER(REPLACE(TRIM(product_code), '-', '')) AS normalized_code,
       LENGTH(TRIM(product_code)) AS code_chars
FROM string_lab;
```

Đưa ra quy tắc nào là xử lý kỹ thuật và quy tắc nào cần quyết định nghiệp vụ. Không update bảng thật trước khi xác nhận cách chuẩn hóa không làm hai mã khác nhau trở thành cùng một mã.

### Bài 8 — Đánh giá index và function-based index

Tạo index trên `product_code`, chạy truy vấn equality thông thường và truy vấn `TRIM(product_code)`. Dùng `DBMS_XPLAN` để quan sát plan. Sau đó trong lab tạo function-based index trên `TRIM(product_code)` và xem optimizer có chọn không.

Ghi lại:

- DDL/index expression.
- Plan trước và sau.
- Số hàng trong bảng và statistics.
- Vì sao optimizer có thể vẫn chọn full table scan trên bảng nhỏ.

Không kết luận function-based index luôn cải thiện tốc độ; nó làm tăng dung lượng và chi phí DML.

## 18. Quy tắc thực hành khi viết SQL xử lý chuỗi

1. **Xác định kiểu cột trước khi xử lý.** CHAR, VARCHAR2, NCHAR, NVARCHAR2, CLOB và NCLOB có khác biệt về padding, character set và giới hạn.
2. **Chọn đơn vị nhất quán.** Dùng LENGTH/SUBSTR/INSTR theo ký tự cho text; chỉ dùng biến thể B khi hợp đồng byte yêu cầu.
3. **Kiểm tra INSTR trước khi tính SUBSTR.** INSTR không tìm thấy trả 0, có thể tạo length âm.
4. **Quy định rõ trim.** Blank, tab, newline và NBSP không phải cùng một ký tự.
5. **Hiểu NULL.** Oracle xem chuỗi rỗng là NULL; kết quả hàm NULL tác động tới WHERE và phép nối.
6. **Không nhầm REPLACE với regex.** Literal thay chuỗi dùng REPLACE; pattern dùng REGEXP_REPLACE khi thật sự cần.
7. **Tránh implicit conversion.** Dữ liệu số/ngày chuyển sang chuỗi phải có format mask và quy tắc NLS rõ.
8. **Không làm mất dữ liệu có ý nghĩa.** Không trim/xóa dấu/case-fold tùy tiện nếu ký tự là một phần của mã hoặc tên.
9. **Đánh giá index.** Hàm trên cột có thể cần function-based index hoặc chuẩn hóa trước khi lưu.
10. **Dùng bind variable.** Hàm chuỗi không thay thế parameter binding và bảo vệ SQL injection.
11. **Tách parse với validation.** Tách được token không chứng minh token hợp lệ về nghiệp vụ.
12. **Kiểm thử với Unicode và dữ liệu biên.** Bao gồm chuỗi rỗng, NULL, delimiter thiếu/lặp, ký tự đa byte, control characters và chuỗi rất dài.

## 19. Câu hỏi tự kiểm tra

1. `SUBSTR` tính position từ 0 hay 1? Oracle xử lý position 0 như thế nào?
2. Position âm trong `SUBSTR` khác length âm ở điểm nào?
3. `INSTR` trả về gì khi không tìm thấy chuỗi con? Vì sao phải kiểm tra trước khi lấy substring theo delimiter?
4. Tham số `occurrence` trong `INSTR` có ý nghĩa gì? Position âm thay đổi hướng tìm như thế nào?
5. `LENGTH` và `LENGTHB` khác nhau ra sao với AL32UTF8?
6. Vì sao `LENGTH('')` trả NULL nhưng `LENGTH(' ')` trả 1?
7. `CHAR(10)` và `VARCHAR2(10)` có thể khác nhau thế nào khi đếm độ dài?
8. `TRIM` mặc định loại ký tự nào? Vì sao tab hoặc NBSP có thể còn lại?
9. `TRIM` khác `LTRIM`/`RTRIM` khi xử lý một tập ký tự ra sao?
10. `REPLACE` thay lần đầu hay mọi lần xuất hiện? Nếu replacement là NULL thì điều gì xảy ra?
11. Khi nào nên dùng `REGEXP_REPLACE` thay vì `REPLACE`?
12. Vì sao `TRIM(column)` trong WHERE có thể làm index thông thường khó được sử dụng?
13. Làm thế nào tách phần trước/sau dấu @ mà không tạo lỗi khi delimiter thiếu?
14. Vì sao không nên parse CSV có quoted delimiter chỉ bằng `SUBSTR` và `INSTR`?
15. Những khác biệt nào giữa ký tự Unicode và grapheme cluster cần lưu ý khi cắt chuỗi?

Nắm vững năm hàm này giúp giải quyết phần lớn thao tác chuỗi thường gặp trong SQL: **`SUBSTR` để cắt, `INSTR` để tìm, `LENGTH` để đo, `TRIM` để xử lý biên và `REPLACE` để thay thế**. Khi đưa chúng vào hệ thống thật, hãy kiểm tra character set, byte semantics, NULL, delimiter và execution plan; chính những chi tiết đó quyết định dữ liệu được xử lý đúng và hiệu năng có phù hợp hay không.
