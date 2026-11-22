# Biểu thức chính quy và trích xuất mẫu trong PostgreSQL

## 1. Vì sao cần biểu thức chính quy trong SQL?

Một bảng PostgreSQL có thể lưu nhiều chuỗi văn bản: mã đơn hàng, email, log hệ thống, số điện thoại, tên tệp, nội dung mô tả hoặc chuỗi thuộc tính nhập từ hệ thống khác. Khi xử lý chúng, ta thường muốn:

- Tìm các chuỗi có **hình dạng** cụ thể: mã `INV-2026-0042`.
- Kiểm tra một chuỗi có **bắt đầu** bằng tiền tố và **kết thúc** bằng hậu tố hợp lệ.
- Trích riêng **năm** và **số thứ tự** từ mã hóa đơn.
- Lấy **nhiều mã** xuất hiện trong một đoạn văn bản.
- Thay những đoạn khớp mẫu bằng chuỗi khác.
- Tách danh sách nhãn hoặc log thành nhiều phần.
- Lọc dữ liệu nhập sai định dạng trước bước chuẩn hóa.

Nếu chỉ dùng phép bằng:

```sql
WHERE invoice_code = 'INV-2026-0042'
```

thì ta chỉ tìm một giá trị chính xác. Nếu dùng:

```sql
WHERE invoice_code LIKE 'INV-%'
```

thì ta biết chuỗi bắt đầu bằng `INV-`, nhưng **chưa xác định** phía sau có đúng bốn chữ số năm, dấu gạch nối và bốn chữ số thứ tự hay không.

Biểu thức chính quy (*regular expression*, viết tắt là **regex**) giúp mô tả mẫu đó:

```sql
WHERE invoice_code ~ '^INV-[0-9]{4}-[0-9]{4}$'
```

Ý nghĩa:

- `^`: đầu chuỗi.
- `INV-`: phần văn bản cố định.
- `[0-9]{4}`: đúng bốn chữ số ASCII.
- `-`: dấu gạch nối.
- `[0-9]{4}`: đúng bốn chữ số thứ hai.
- `$`: cuối chuỗi.

Vì có cả `^` và `$`, điều kiện yêu cầu **toàn bộ chuỗi** có đúng hình dạng đó; không chỉ chứa một đoạn khớp.

> **Ghi nhớ:** Regex là công cụ mô tả và trích xuất **hình dạng văn bản**, không tự kiểm chứng mọi quy tắc nghiệp vụ. Chuỗi `INV-9999-0000` khớp mẫu bốn chữ số năm, nhưng regex chưa thể kết luận đó là hóa đơn tồn tại hay năm nghiệp vụ hợp lệ.

Trong PostgreSQL, biểu thức chính quy được hỗ trợ trực tiếp qua các toán tử `~`, `~*`, `!~`, `!~*` và các hàm như `regexp_match`, `regexp_matches`, `regexp_replace` và `regexp_split_to_array`.

## 2. Mục tiêu bài học

Sau bài này, bạn có thể:

1. Phân biệt `LIKE`, `ILIKE`, `SIMILAR TO` và regex của PostgreSQL.
2. Dùng `~`, `~*`, `!~`, `!~*` để lọc văn bản.
3. Đọc và viết mẫu gồm anchor, character class, lượng từ, nhóm và lựa chọn.
4. Trích xuất **một lần khớp** với `regexp_match` và `substring(... FROM pattern)`.
5. Trích xuất **tất cả lần khớp** với `regexp_matches(..., 'g')`.
6. Thay thế bằng `regexp_replace`, có hoặc không có **capture groups**.
7. Tách chuỗi với `regexp_split_to_array` và `regexp_split_to_table`.
8. Xử lý `NULL`, dữ liệu không khớp và **hàng biến mất do set-returning function**.
9. Dùng những hàm regex bổ sung của PostgreSQL 15 trở lên khi phiên bản hỗ trợ.
10. Hiểu giới hạn về Unicode, collation, hiệu năng và input không đáng tin cậy.

## 3. Dữ liệu thực hành

Bài sử dụng schema `regex_lab` riêng. Hãy chạy những câu lệnh tạo bảng trong database **thử nghiệm**, không phải production.

### 3.1. Tạo bảng liên hệ

```sql
CREATE SCHEMA IF NOT EXISTS regex_lab;

CREATE TABLE regex_lab.contacts (
    contact_id bigint PRIMARY KEY,
    full_name text NOT NULL,
    email text,
    phone text,
    note text NOT NULL
);
```

Nạp sáu bản ghi:

```sql
INSERT INTO regex_lab.contacts
    (contact_id, full_name, email, phone, note)
VALUES
    (
        1, 'An', 'an@example.com', '090-123-4567',
        'INV-2026-0042; tag=SQL; tag=Java'
    ),
    (
        2, 'Bình', 'Binh@Example.COM', '+84 912 345 678',
        'INV-2026-0101; tag=PostgreSQL'
    ),
    (
        3, 'Chi', 'chi.example.com', 'abc',
        'Không tìm thấy mã hóa đơn'
    ),
    (
        4, 'Dung', NULL, NULL,
        'Mã lỗi #42 và #103'
    ),
    (
        5, 'Em', 'em+sales@example.org', '0912345678',
        'INV-2025-1234; tag=SQL; tag=SQL'
    ),
    (
        6, 'Phúc', 'phuc@sample.vn', '012-345-6789',
        'INV-2026-0200; liên hệ sau'
    );
```

Bảng cố ý chứa:

- Email viết hoa/thường khác nhau.
- Một email không có ký tự `@`.
- Giá trị `email` và `phone` là `NULL`.
- Số điện thoại có dấu gạch nối, khoảng trắng, dấu cộng và văn bản không hợp lệ.
- Nhiều mã hóa đơn, nhãn `tag=...` và mã lỗi bắt đầu bằng `#`.

**Lưu ý:** dữ liệu chỉ dùng để minh họa regex, không chứng minh số điện thoại hay email nào đã được xác minh thật. Chạy lại `INSERT` sau khi đã nạp dữ liệu sẽ gây lỗi khóa chính.

### 3.2. Tạo bảng log

```sql
CREATE TABLE regex_lab.logs (
    log_id bigint PRIMARY KEY,
    log_line text NOT NULL
);

INSERT INTO regex_lab.logs (log_id, log_line)
VALUES
    (101, 'INFO order=1001 amount=125.50'),
    (102, 'WARN order=1002 amount=0'),
    (103, 'ERROR code=E42 details=timeout'),
    (104, 'INFO order=1003 amount=78.25'),
    (105, 'DEBUG no order information');
```

Chúng ta sẽ trích:

- Mức log: `INFO`, `WARN`, `ERROR`.
- Mã `order=1001`.
- Số tiền `amount=125.50`.
- Mã lỗi `code=E42`.

## 4. `LIKE`, `ILIKE` và regex khác nhau ở đâu?

PostgreSQL có vài cơ chế khớp mẫu:

| Cơ chế | Mẫu ví dụ | Khả năng |
| --- | --- | --- |
| `=` | `email = 'an@example.com'` | So sánh giá trị bằng nhau |
| `LIKE` | `full_name LIKE 'A%'` | Tìm mẫu đơn giản với `%` và `_` |
| `ILIKE` | `full_name ILIKE 'a%'` | Tương tự LIKE, không phân biệt hoa/thường theo xử lý locale |
| `~` | `note ~ 'INV-[0-9]{4}'` | Regex, phân biệt hoa/thường |
| `~*` | `note ~* 'inv-[0-9]{4}'` | Regex, không phân biệt hoa/thường |
| `SIMILAR TO` | `code SIMILAR TO 'INV-[0-9]{4}-[0-9]{4}'` | Mẫu theo cú pháp SQL kết hợp LIKE/regex, thường yêu cầu khớp toàn chuỗi |
| `regexp_match` | `regexp_match(note, '(INV-[0-9]+)')` | Lấy dữ liệu của lần khớp đầu tiên |

### 4.1. `LIKE` dùng ký tự đại diện khác regex

Trong `LIKE`:

- `%`: không hoặc nhiều ký tự.
- `_`: đúng một ký tự.

```sql
SELECT
    'INV-2026-0042' LIKE 'INV-%' AS like_prefix,
    'INV-2026-0042' LIKE 'INV-____-____' AS like_fixed_width;
```

Cả hai biểu thức trả `TRUE`. Nhưng `_` có thể khớp chữ cái hoặc ký tự khác, không bắt buộc là chữ số.

Trong regex:

- `.`: một ký tự bất kỳ theo quy tắc regex.
- `.*`: không hoặc nhiều ký tự.
- `[0-9]`: một chữ số ASCII.
- `{4}`: đúng bốn lần.

```sql
SELECT
    'INV-2026-0042' ~ '^INV-[0-9]{4}-[0-9]{4}$'
        AS exact_shape,
    'INV-ABCD-WXYZ' ~ '^INV-[0-9]{4}-[0-9]{4}$'
        AS invalid_shape;
```

Kết quả: `TRUE` và `FALSE`.

**Đừng chuyển mẫu `LIKE 'A%'` thành regex `'A%'`.** Trong regex, ký tự `%` thông thường chỉ mang nghĩa dấu phần trăm; muốn mô tả “bắt đầu bằng A” thì dùng `'^A'`.

### 4.2. `SIMILAR TO` khớp toàn chuỗi

```sql
SELECT
    'INV-2026-0042'
        SIMILAR TO 'INV-[0-9]{4}-[0-9]{4}' AS similar_valid,
    'prefix INV-2026-0042 suffix'
        SIMILAR TO 'INV-[0-9]{4}-[0-9]{4}' AS similar_not_full;
```

`SIMILAR TO` kết hợp đặc điểm của SQL LIKE và regex, nhưng quy tắc khác các toán tử POSIX regex. Nó phù hợp trong một số ngữ cảnh SQL chuẩn; còn khi cần capture groups, thay thế hoặc trích xuất linh hoạt, các hàm regex chuyên dụng của PostgreSQL thường thuận tiện hơn.

## 5. Bốn toán tử so khớp regex trong PostgreSQL

| Toán tử | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| `~` | Khớp regex, phân biệt hoa/thường | `name ~ '^A'` |
| `~*` | Khớp regex, không phân biệt hoa/thường | `name ~* '^a'` |
| `!~` | Không khớp regex, phân biệt hoa/thường | `name !~ '^A'` |
| `!~*` | Không khớp regex, không phân biệt hoa/thường | `name !~* '^a'` |

### 5.1. `~`: tìm chuỗi chứa mẫu

```sql
SELECT contact_id, full_name, note
FROM regex_lab.contacts
WHERE note ~ 'INV-[0-9]{4}-[0-9]{4}'
ORDER BY contact_id;
```

Kết quả gồm `contact_id` **1, 2, 5, 6**, vì ghi chú của bốn liên hệ chứa một mã có dạng được mô tả.

Điểm dễ nhầm:

```sql
SELECT
    'abc INV-2026-0042 xyz' ~ 'INV-[0-9]{4}-[0-9]{4}'
        AS contains_pattern,
    'abc INV-2026-0042 xyz' ~ '^INV-[0-9]{4}-[0-9]{4}$'
        AS entire_string_matches;
```

- `contains_pattern` là `TRUE`.
- `entire_string_matches` là `FALSE`.

Không có anchor, regex có thể khớp **một đoạn bất kỳ trong chuỗi**. Có anchor `^` và `$`, nó yêu cầu mẫu bao phủ toàn bộ chuỗi trong chế độ thông thường.

### 5.2. `~*`: không phân biệt chữ hoa/thường

```sql
SELECT contact_id, full_name, email
FROM regex_lab.contacts
WHERE email ~* '@example\.com$'
ORDER BY contact_id;
```

Kết quả gồm liên hệ **1** và **2**:

- `an@example.com`
- `Binh@Example.COM`

`~*` cho phép so sánh khác case. `\.` là **dấu chấm theo nghĩa đen**; nếu viết `.` không escape, nó có thể khớp bất kỳ ký tự nào.

### 5.3. `!~` và `!~*`

```sql
SELECT contact_id, full_name, note
FROM regex_lab.contacts
WHERE note !~ 'INV-[0-9]{4}-[0-9]{4}'
ORDER BY contact_id;
```

Trong dữ liệu mẫu, kết quả là **3** và **4** vì ghi chú của họ không chứa mã hóa đơn dạng này.

Đối với những giá trị `NULL`, biểu thức so regex thường cho `NULL`, kể cả khi dùng toán tử phủ định:

```sql
SELECT
    NULL::text ~ '^A' AS null_matches,
    NULL::text !~ '^A' AS null_does_not_match;
```

Cả hai đều là `NULL`, không phải FALSE hay TRUE. Trong `WHERE`, chỉ kết quả TRUE được giữ.

### 5.4. Tìm những hàng không khớp, kể cả NULL

Nếu yêu cầu nghiệp vụ là “email **không hợp mẫu hoặc chưa được cung cấp**”:

```sql
SELECT contact_id, full_name, email
FROM regex_lab.contacts
WHERE email IS NULL
   OR email !~* '^[^@[:space:]]+@[^@[:space:]]+$'
ORDER BY contact_id;
```

Trên bảng mẫu, truy vấn có thể trả liên hệ **3** và **4**: một địa chỉ thiếu `@`, một địa chỉ NULL.

Đây là **kiểm tra hình dạng rất sơ bộ**, chưa phải bộ xác thực email đầy đủ. Đặc biệt, không nên khẳng định “khớp regex” đồng nghĩa địa chỉ tồn tại hoặc nhận được thư.

## 6. Cú pháp regex cốt lõi: đọc mẫu từ trái sang phải

PostgreSQL sử dụng một engine biểu thức chính quy hỗ trợ cú pháp POSIX và các mở rộng **Advanced Regular Expressions (ARE)**. Nó không phải engine Java `java.util.regex`, JavaScript `RegExp` hay PCRE, dù nhiều ký hiệu giống nhau.

### 6.1. Ký tự thường và ký tự đặc biệt

| Mẫu | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| `abc` | Đúng chuỗi văn bản `abc` | Khớp `xabcx` |
| `.` | Một ký tự bất kỳ theo chế độ khớp | `a.c` có thể khớp `abc` |
| `^` | Đầu chuỗi, chịu ảnh hưởng một số chế độ newline | `^INV` |
| `$` | Cuối chuỗi, chịu ảnh hưởng một số chế độ newline | `[0-9]$` |
| `[abc]` | Một ký tự thuộc tập a, b, c | `[ABC]` |
| `[^abc]` | Một ký tự không thuộc tập a, b, c | `[^0-9]` |
| `[0-9]` | Một chữ số ASCII từ 0 đến 9 | `[0-9]{4}` |
| `(abc)` | Nhóm có capture | `(INV)-[0-9]+` |
| `a\|b` | Chọn một trong hai nhánh | `(INFO\|ERROR)` |
| `\` | Escape hoặc bắt đầu cú pháp regex mở rộng | `\.` để khớp dấu chấm |

Ở bảng Markdown, dấu `\|` được escape để hiển thị ký hiệu pipe; trong câu SQL thực tế, toán tử chọn nhánh là ký tự `|` không kèm escape.

Ví dụ lựa chọn:

```sql
SELECT
    'ERROR code=E42' ~ '^(INFO|WARN|ERROR)' AS supported_level,
    'TRACE details' ~ '^(INFO|WARN|ERROR)' AS unsupported_level;
```

Kết quả: `TRUE` và `FALSE`.

### 6.2. Character class: tập ký tự

```sql
SELECT
    'A7' ~ '^[A-Z][0-9]$' AS alpha_then_digit,
    'a7' ~ '^[A-Z][0-9]$' AS lowercase_not_allowed,
    'a7' ~* '^[A-Z][0-9]$' AS lowercase_allowed_with_casefold;
```

Mẫu `[A-Z]` biểu diễn dải chữ cái theo quy tắc xử lý của regex/collation; khi cần xác định đầu vào nghiêm ngặt ASCII, nên kiểm tra hành vi trong môi trường thực tế và định nghĩa rõ hợp đồng dữ liệu. Với tiếng Việt có dấu, `[A-Za-z]` **không phải** mô tả đầy đủ các ký tự chữ cái.

### 6.3. POSIX character classes

PostgreSQL hỗ trợ dạng lớp ký tự:

| Lớp | Ý nghĩa khái quát |
| --- | --- |
| `[[:digit:]]` | Ký tự chữ số theo lớp tương ứng |
| `[[:alpha:]]` | Ký tự chữ cái |
| `[[:alnum:]]` | Chữ cái hoặc chữ số |
| `[[:space:]]` | Ký tự khoảng trắng |
| `[[:lower:]]` | Chữ thường |
| `[[:upper:]]` | Chữ hoa |
| `[[:punct:]]` | Dấu câu |
| `[[:xdigit:]]` | Chữ số hệ thập lục phân |

Ví dụ:

```sql
SELECT
    'INV2026' ~ '^[[:alpha:]]+[[:digit:]]+$'
        AS letter_digit_sequence,
    'ABC-12' ~ '^[[:alnum:]]+$'
        AS alphanumeric_only,
    'ABC12' ~ '^[[:alnum:]]+$'
        AS alphanumeric_valid;
```

Kết quả lần lượt là `TRUE`, `FALSE` và `TRUE` trong môi trường thông dụng.

Lớp `[[:alpha:]]` và hành vi casefold có thể phụ thuộc locale/collation và cách PostgreSQL hỗ trợ Unicode. Không dùng regex ASCII đơn giản để kiểm chứng tên người đa ngôn ngữ.

### 6.4. Dấu gạch ngang, dấu chấm và dấu ngoặc vuông

Một số ký tự có ý nghĩa đặc biệt trong regex cần được xử lý cẩn thận.

- Dấu chấm theo nghĩa đen: `\.`.
- Dấu ngoặc mở vuông theo nghĩa đen thường cần `\[`.
- Dấu gạch ngang trong `[...]` có thể tạo **khoảng**; đặt ở vị trí không gây hiểu nhầm hoặc escape.

Ví dụ:

```sql
SELECT
    'a.b' ~ '^a\.b$' AS literal_dot,
    'axb' ~ '^a\.b$' AS not_literal_dot,
    'a-b' ~ '^a[-]b$' AS literal_hyphen;
```

Kết quả: `TRUE`, `FALSE`, `TRUE`.

**Chú ý hai tầng cú pháp:** regex được viết **trong một literal SQL**. Cách escape dấu nháy đơn của SQL và cách escape ký tự trong regex là hai vấn đề khác nhau.

## 7. Quantifier: số lần lặp của một phần mẫu

| Quantifier | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| `*` | 0 hoặc nhiều lần | `a*` |
| `+` | 1 hoặc nhiều lần | `a+` |
| `?` | 0 hoặc 1 lần | `a?` |
| `{n}` | Đúng n lần | `[0-9]{4}` |
| `{n,}` | Ít nhất n lần | `[0-9]{2,}` |
| `{n,m}` | Từ n đến m lần | `[0-9]{2,5}` |

### 7.1. Phân biệt `*` và `+`

```sql
SELECT
    '' ~ '^a*$' AS empty_matches_star,
    '' ~ '^a+$' AS empty_matches_plus,
    'aaa' ~ '^a+$' AS repeated_a;
```

Kết quả:

- `a*` chấp nhận **chuỗi rỗng**.
- `a+` yêu cầu ít nhất một ký tự `a`.
- `aaa` khớp `a+`.

Điều này quan trọng khi validate cột bắt buộc phải có ít nhất một ký tự hợp lệ.

### 7.2. Mã chuẩn gồm năm chữ số

```sql
SELECT
    '00123' ~ '^[0-9]{5}$' AS valid_code,
    '123' ~ '^[0-9]{5}$' AS too_short,
    '123456' ~ '^[0-9]{5}$' AS too_long;
```

Kết quả: `TRUE`, `FALSE`, `FALSE`.

Nếu code bắt buộc **khác 00000**, regex trên chưa đủ: nó chỉ kiểm tra hình dạng, chưa kiểm tra miền giá trị. Có thể thêm điều kiện nghiệp vụ riêng hoặc parse thành kiểu thích hợp nếu cần.

### 7.3. Greedy và non-greedy

Nhiều quantifier trong PostgreSQL ARE mặc định có xu hướng **greedy**: cố chọn phần khớp dài nhất thỏa quy tắc.

```sql
SELECT
    substring('<a>first</a><b>second</b>' FROM '<.*>')
        AS greedy_fragment,
    substring('<a>first</a><b>second</b>' FROM '<.*?>')
        AS nongreedy_fragment;
```

Trong regex ARE, `.*?` là dạng **non-greedy**, thường dừng ở dấu `>` đầu tiên thay vì kéo đến dấu `>` cuối.

Dù hỗ trợ quantifier non-greedy, **không nên dùng regex tùy tiện để parse HTML/XML có cấu trúc lồng nhau**. Với HTML/XML/JSON, hãy dùng công cụ xử lý cấu trúc phù hợp để tránh lỗi với dấu quote, escape và nội dung lồng.

## 8. Anchor: khớp đầu và cuối

### 8.1. Mẫu có và không có anchor

```sql
SELECT
    'abcINV-2026-0042xyz'
        ~ 'INV-[0-9]{4}-[0-9]{4}' AS found_inside,
    'abcINV-2026-0042xyz'
        ~ '^INV-[0-9]{4}-[0-9]{4}$' AS valid_whole_value;
```

Kết quả `TRUE` và `FALSE`.

Khi kiểm tra **định dạng toàn cột** như mã đơn hàng, thường nên dùng `^...$`. Khi tìm **một mã nằm trong ghi chú dài**, thường không đặt anchor ở cả hai đầu.

### 8.2. Mốc đầu dòng khác đầu chuỗi theo chế độ newline

Một chuỗi log có nhiều dòng:

```text
INFO start
ERROR failed
INFO end
```

Nếu mục tiêu là tìm dòng bắt đầu bằng `ERROR`, bạn cần hiểu **chế độ xử lý newline** của engine. PostgreSQL cung cấp các flag điều khiển hành vi anchor và dấu chấm với ký tự newline (trình bày ở phần 15).

Không mặc định mọi engine regex đều coi `^` và `$` là đầu/cuối từng dòng trong một chuỗi nhiều dòng. Phải xác định chế độ cần dùng.

### 8.3. Giới hạn khi dùng anchor để validate

```sql
SELECT 'test@example.com' ~ '^[^@[:space:]]+@[^@[:space:]]+$';
```

Mẫu này chỉ bảo đảm có một `@` và không có dấu cách ở hai phần. Nó vẫn chấp nhận nhiều chuỗi không phải địa chỉ email thực tế. **Regex đơn giản là một bước lọc hình dạng, không phải trình xác thực email toàn diện**.

## 9. Group và lựa chọn: nền tảng của trích xuất mẫu

Dấu ngoặc đơn `(...)` trong regex có hai vai trò:

1. Nhóm các thành phần để áp dụng `|` hoặc quantifier.
2. **Capture** phần văn bản khớp, giúp hàm trích xuất lấy ra từng thành phần.

### 9.1. Nhóm các mức log

```sql
SELECT log_id, log_line
FROM regex_lab.logs
WHERE log_line ~ '^(INFO|WARN|ERROR)[[:space:]]'
ORDER BY log_id;
```

Kết quả gồm log **101, 102, 103, 104**; log 105 bắt đầu bằng DEBUG nên không khớp.

### 9.2. Nhóm các thành phần mã hóa đơn

Mẫu:

```regex
^([A-Z]+)-([0-9]{4})-([0-9]{4})$
```

có ba capture group:

| Nhóm | Mẫu | Ví dụ |
| --- | --- | --- |
| 1 | `([A-Z]+)` | `INV` |
| 2 | `([0-9]{4})` | `2026` |
| 3 | `([0-9]{4})` | `0042` |

Ví dụ:

```sql
SELECT regexp_match(
    'INV-2026-0042',
    '^([A-Z]+)-([0-9]{4})-([0-9]{4})$'
) AS captured_parts;
```

Kết quả là một **mảng text**:

```text
{INV,2026,0042}
```

Trong PostgreSQL, chỉ số của array thường bắt đầu từ **1**, không phải 0.

### 9.3. Nhóm không capture

Một số nhóm chỉ dùng để lựa chọn, không cần lấy ra. Trong PostgreSQL ARE, có thể dùng dạng **non-capturing group** `(?:...)`:

```sql
SELECT regexp_match(
    'WARN order=1002',
    '^(?:INFO|WARN|ERROR)[[:space:]]order=([0-9]+)'
) AS only_order_id;
```

Kết quả dự kiến là mảng chứa `1002`, vì phần `(?:INFO|WARN|ERROR)` không tạo capture group.

Đây là cách tránh tình trạng phải nhớ chỉ số group thay đổi chỉ vì thêm một cặp ngoặc để nhóm cú pháp.

## 10. `regexp_match`: trích xuất lần khớp đầu tiên

`regexp_match(string, pattern [, flags])` trả:

- Một **`text[]`** chứa các capture group nếu có khớp.
- `NULL` nếu không có khớp.
- Nếu regex **không có capture group**, mảng thường chứa **toàn bộ đoạn khớp**.

Hàm này trả **một giá trị cho mỗi hàng đầu vào**, nên thuận tiện cho SELECT bình thường.

### 10.1. Trích mã hóa đơn trong ghi chú

```sql
SELECT
    contact_id,
    full_name,
    regexp_match(
        note,
        '(INV-[0-9]{4}-[0-9]{4})'
    ) AS invoice_match
FROM regex_lab.contacts
ORDER BY contact_id;
```

Kết quả về mặt nội dung:

| contact_id | invoice_match |
| ---: | --- |
| 1 | `{INV-2026-0042}` |
| 2 | `{INV-2026-0101}` |
| 3 | NULL |
| 4 | NULL |
| 5 | `{INV-2025-1234}` |
| 6 | `{INV-2026-0200}` |

Các hàng 3 và 4 **vẫn còn trong kết quả**, chỉ có cột trích xuất là NULL.

### 10.2. Trích năm và số thứ tự

```sql
SELECT
    contact_id,
    (regexp_match(
        note,
        'INV-([0-9]{4})-([0-9]{4})'
    ))[1] AS invoice_year,
    (regexp_match(
        note,
        'INV-([0-9]{4})-([0-9]{4})'
    ))[2] AS invoice_sequence
FROM regex_lab.contacts
ORDER BY contact_id;
```

Ví dụ liên hệ 1:

```text
invoice_year     = 2026
invoice_sequence = 0042
```

Các giá trị này là **text**, vì được trích từ chuỗi. Giữ `0042` ở dạng text có ý nghĩa nếu mã hóa đơn cần bảo toàn **số 0 ở đầu**. Cast sang số nguyên sẽ biến `0042` thành `42` và mất định dạng mã gốc.

### 10.3. Tránh gọi regex lặp lại bằng LATERAL

Nếu muốn lấy nhiều group, có thể thực hiện một lần trích cho mỗi hàng:

```sql
SELECT
    c.contact_id,
    c.full_name,
    m.parts[1] AS invoice_year,
    m.parts[2] AS invoice_sequence
FROM regex_lab.contacts AS c
CROSS JOIN LATERAL (
    SELECT regexp_match(
        c.note,
        'INV-([0-9]{4})-([0-9]{4})'
    ) AS parts
) AS m
ORDER BY c.contact_id;
```

`regexp_match` là hàm trả **một mảng hoặc NULL**, nên subquery scalar này có một hàng cho mỗi liên hệ ngay cả khi không khớp; cột `parts` khi đó là NULL.

Ưu điểm là SQL rõ ràng và có thể tái sử dụng `m.parts[1]`/`m.parts[2]` mà không viết lại pattern dài.

### 10.4. Khi không có nhóm capture

```sql
SELECT
    regexp_match(
        'x=123',
        '[0-9]+'
    ) AS whole_match_without_groups,
    regexp_match(
        'x=123',
        'x=([0-9]+)'
    ) AS group_only;
```

Cả hai đều có phần tử `123` trong ví dụ này, nhưng khác lý do:

- Pattern đầu không có nhóm → mảng chứa **toàn đoạn khớp** `123`.
- Pattern thứ hai có nhóm → mảng chứa **nội dung group** `123`, không phải toàn đoạn `x=123`.

Nếu muốn lấy cả prefix lẫn giá trị, dùng hai group:

```sql
SELECT regexp_match(
    'x=123',
    '([[:alpha:]]+)=([0-9]+)'
);
```

Kết quả `{x,123}`.

## 11. `substring(text FROM pattern)`: một cách trích xuất ngắn

PostgreSQL cho phép dạng:

```sql
substring(string FROM pattern)
```

với **pattern là POSIX regular expression**.

### 11.1. Lấy mã nằm trong chuỗi

```sql
SELECT
    substring(
        'Thông báo: INV-2026-0042 đã tạo',
        'INV-[0-9]{4}-[0-9]{4}'
    ) AS invoice_code;
```

Kết quả:

```text
INV-2026-0042
```

Nếu không có đoạn khớp, kết quả là `NULL`.

### 11.2. Capturing parentheses thay đổi phần substring trả về

```sql
SELECT
    substring(
        'INV-2026-0042',
        'INV-([0-9]{4})-[0-9]{4}'
    ) AS extracted_year;
```

Kết quả là `2026`, vì khi mẫu chứa capturing parentheses, dạng `substring(... FROM pattern)` thường trả **phần khớp của capturing group đầu tiên**.

Đây là khác biệt so với ví dụ trước, nơi không có group và hàm trả toàn bộ đoạn khớp.

### 11.3. Khi nào dùng `substring`, khi nào dùng `regexp_match`?

| Nhu cầu | Gợi ý |
| --- | --- |
| Trích một đoạn duy nhất theo mẫu đơn giản | `substring(... FROM regex)` |
| Trích một group cụ thể | `substring` nếu group đầu phù hợp; `regexp_match` nếu cần rõ ràng hơn |
| Trích nhiều group cùng lúc | `regexp_match` |
| Trích tất cả lần xuất hiện | `regexp_matches(..., 'g')` hoặc hàm phù hợp |
| Cần kiểm tra chỉ khớp/không khớp | `~`/`~*` hoặc `regexp_like` |

Trong ứng dụng có nhiều thành phần cần bóc tách, `regexp_match` thường dễ đọc hơn việc thêm nhiều `substring` riêng lẻ.

## 12. `regexp_matches`: nhiều kết quả và khác biệt quan trọng với `regexp_match`

Tên hai hàm rất giống nhưng **cardinality** khác nhau:

- `regexp_match`: trả **một mảng hoặc NULL** cho mỗi lần gọi.
- `regexp_matches`: trả **tập hàng** (*set of text[]*). Nếu **không có match**, nó trả **0 hàng**; nếu có flag `g`, mỗi lần match tạo một hàng.

### 12.1. Một lần khớp, không có `g`

```sql
SELECT *
FROM regexp_matches(
    'tag=SQL; tag=Java',
    'tag=([[:alpha:]]+)'
);
```

Vì không có `g`, thường chỉ trả phần khớp đầu tiên:

```text
{SQL}
```

### 12.2. Tất cả lần khớp với flag `g`

```sql
SELECT *
FROM regexp_matches(
    'tag=SQL; tag=Java',
    'tag=([[:alpha:]]+)',
    'g'
);
```

Kết quả hai hàng:

```text
{SQL}
{Java}
```

`g` là **global matching**: tìm các lần khớp tiếp theo, không chỉ lần đầu.

### 12.3. Trích mọi nhãn của các liên hệ

```sql
SELECT
    c.contact_id,
    c.full_name,
    m.parts[1] AS tag
FROM regex_lab.contacts AS c
CROSS JOIN LATERAL regexp_matches(
    c.note,
    'tag=([[:alpha:]]+)',
    'g'
) AS m(parts)
ORDER BY c.contact_id, tag;
```

Kết quả nội dung:

| contact_id | full_name | tag |
| ---: | --- | --- |
| 1 | An | Java |
| 1 | An | SQL |
| 2 | Bình | PostgreSQL |
| 5 | Em | SQL |
| 5 | Em | SQL |

Những liên hệ không chứa `tag=...` **không có hàng** trong kết quả của `CROSS JOIN LATERAL`. Liên hệ 5 có `tag=SQL` hai lần nên tạo hai hàng.

Chú ý `ORDER BY c.contact_id, tag` sắp theo giá trị tag, **không giữ thứ tự xuất hiện trong note**. Nếu cần đúng thứ tự xuất hiện, cần giải pháp thu thập vị trí hoặc sử dụng ordinality theo cấu trúc hàm với kiểm chứng thứ tự phù hợp.

### 12.4. Không có match → 0 hàng, không phải NULL row

```sql
SELECT *
FROM regexp_matches(
    'không có nhãn',
    'tag=([[:alpha:]]+)',
    'g'
);
```

Kết quả là **0 hàng**.

Nếu sử dụng hàm này trong ngữ cảnh làm thay đổi số hàng, bạn có thể vô tình bỏ cả bản ghi nguồn. Đó là khác biệt thiết kế quan trọng so với `regexp_match`.

### 12.5. Giữ mọi liên hệ bằng `LEFT JOIN LATERAL`

```sql
SELECT
    c.contact_id,
    c.full_name,
    m.parts[1] AS tag
FROM regex_lab.contacts AS c
LEFT JOIN LATERAL regexp_matches(
    c.note,
    'tag=([[:alpha:]]+)',
    'g'
) AS m(parts)
    ON TRUE
ORDER BY c.contact_id, tag NULLS LAST;
```

Với `LEFT JOIN LATERAL`, những liên hệ không có nhãn vẫn hiện **một hàng với `tag NULL`**.

So sánh:

| Cách JOIN | Khi một liên hệ không có match |
| --- | --- |
| `CROSS JOIN LATERAL regexp_matches` | Liên hệ biến mất |
| `LEFT JOIN LATERAL regexp_matches ... ON TRUE` | Liên hệ được giữ, cột match NULL |

**Đây là bẫy rất phổ biến khi trích regex trên nhiều hàng**. Hãy chọn kiểu JOIN theo yêu cầu có cần giữ bản ghi không khớp hay không.

## 13. Từ match sang các hàng cấu trúc hóa

Trích xuất regex thường là bước đầu của quá trình chuyển log text thành dữ liệu có cấu trúc.

### 13.1. Lấy các cặp `key=value` trong log

```sql
SELECT
    l.log_id,
    m.parts[1] AS key,
    m.parts[2] AS value
FROM regex_lab.logs AS l
CROSS JOIN LATERAL regexp_matches(
    l.log_line,
    '([[:alpha:]_]+)=([[:alnum:]._-]+)',
    'g'
) AS m(parts)
ORDER BY l.log_id, key;
```

Ví dụ log 101:

```text
INFO order=1001 amount=125.50
```

được trích thành:

| log_id | key | value |
| ---: | --- | --- |
| 101 | amount | 125.50 |
| 101 | order | 1001 |

Đây là một dạng **key-value extraction**. Nó không hỗ trợ đầy đủ mọi giá trị có khoảng trắng hoặc dấu escape. Muốn parse log sản xuất an toàn, tốt nhất thiết kế log **có cấu trúc ngay từ đầu**, ví dụ JSON, thay vì cố gắng bao quát mọi biến thể bằng một regex.

### 13.2. Trích mã lỗi dạng `#42`, `#103`

```sql
SELECT
    c.contact_id,
    m.parts[1] AS error_number_text
FROM regex_lab.contacts AS c
CROSS JOIN LATERAL regexp_matches(
    c.note,
    '#([0-9]+)',
    'g'
) AS m(parts)
ORDER BY c.contact_id, error_number_text;
```

Liên hệ 4 có hai mã lỗi:

```text
42
103
```

Vì `error_number_text` là text, thứ tự sắp theo tên có thể cho `103` trước `42`. Nếu cần thứ tự **số học**, có thể ép thành integer sau khi đã xác nhận miền giá trị an toàn.

### 13.3. Tránh cast dữ liệu không kiểm soát

Nếu mẫu `[0-9]+` khớp một chuỗi rất dài, cast sang `integer` có thể gây `integer out of range`.

Ví dụ chỉ cho tối đa 9 chữ số ASCII, nên nằm trong phạm vi số nguyên 32-bit dương:

```sql
SELECT
    c.contact_id,
    m.parts[1]::integer AS error_number
FROM regex_lab.contacts AS c
CROSS JOIN LATERAL regexp_matches(
    c.note,
    '#([0-9]{1,9})([^0-9]|$)',
    'g'
) AS m(parts)
ORDER BY c.contact_id, error_number;
```

Mẫu này yêu cầu sau các chữ số có ký tự không phải số hoặc cuối chuỗi, tránh chọn một tiền tố từ chuỗi số quá dài trong nhiều trường hợp thông thường.

**Tuy nhiên**, xác thực bằng regex và cast vẫn là một phần của bài toán nhập dữ liệu: nếu yêu cầu nghiêm ngặt, cần kiểm tra chính sách về số 0 đầu, dấu, giới hạn giá trị và thông báo lỗi. Trong schema chuẩn hóa, kiểu số và `CHECK` thường đáng tin cậy hơn việc luôn parse lại chuỗi thô ở mọi truy vấn.

## 14. `regexp_replace`: tìm và thay thế theo mẫu

Cú pháp cơ bản:

```sql
regexp_replace(source, pattern, replacement)
regexp_replace(source, pattern, replacement, flags)
```

Hàm trả về chuỗi đã thay thế. Điểm quan trọng: **không có flag `g` thường chỉ thay lần khớp đầu tiên**; với `g` thì thay tất cả lần khớp không chồng lấn được tìm thấy.

### 14.1. Thay lần đầu tiên

```sql
SELECT regexp_replace(
    'A   B    C',
    '[[:space:]]+',
    ' '
) AS only_first_group;
```

Kết quả về mặt nội dung:

```text
A B    C
```

Chỉ nhóm khoảng trắng đầu tiên được thay.

### 14.2. Thay tất cả với `g`

```sql
SELECT regexp_replace(
    'A   B    C',
    '[[:space:]]+',
    ' ',
    'g'
) AS normalized_spacing;
```

Kết quả:

```text
A B C
```

Đây là thao tác thường dùng để chuẩn hóa dấu cách trong chuỗi nhập từ người dùng. Nhưng lưu ý `[[:space:]]+` có thể khớp cả tab hoặc newline; nếu cần giữ xuống dòng, phải thiết kế mẫu hẹp hơn.

### 14.3. Chuẩn hóa số điện thoại thành chuỗi chỉ gồm chữ số

```sql
SELECT
    contact_id,
    phone,
    regexp_replace(
        phone,
        '[^0-9]',
        '',
        'g'
    ) AS digits_only
FROM regex_lab.contacts
ORDER BY contact_id;
```

Ví dụ:

| phone | digits_only |
| --- | --- |
| `090-123-4567` | `0901234567` |
| `+84 912 345 678` | `84912345678` |
| `abc` | chuỗi rỗng |
| NULL | NULL |
| `0912345678` | `0912345678` |

**Cảnh báo:** “giữ lại chữ số” không đồng nghĩa với **xác minh số điện thoại**. Ký hiệu mã quốc gia, số 0 đầu và quy tắc độ dài còn phụ thuộc quốc gia, nhà mạng và hệ thống. Đừng tự biến mọi chuỗi chứa chữ số thành một số điện thoại được xác thực.

### 14.4. Tránh dùng hàm biến đổi làm mất dữ liệu gốc

Ví dụ câu lệnh:

```sql
UPDATE regex_lab.contacts
SET phone = regexp_replace(phone, '[^0-9]', '', 'g');
```

sẽ **ghi đè giá trị gốc** nếu thực thi. Trong bài thực hành, nên dùng `SELECT` để quan sát kết quả thay vì thay toàn bảng.

Nếu ứng dụng thực sự cần chuẩn hóa dữ liệu, nên:

- Lưu bản gốc nếu cần phục vụ đối soát/audit.
- Xác định cấu trúc mục tiêu rõ.
- Kiểm tra trường hợp NULL, chuỗi rỗng và chuỗi không hợp lệ.
- Chạy migration có kiểm soát và có phương án rollback.

### 14.5. Capture group trong chuỗi thay thế

Trong replacement của `regexp_replace`, bạn có thể tham chiếu các group bằng `\1`, `\2`, v.v. và dùng `\&` cho toàn đoạn khớp.

Ví dụ đổi dấu phân cách mã:

```sql
SELECT regexp_replace(
    'INV-2026-0042',
    '^([A-Z]+)-([0-9]{4})-([0-9]{4})$',
    '\1/\2/\3'
) AS reformatted_invoice;
```

Kết quả:

```text
INV/2026/0042
```

Ví dụ che một phần token:

```sql
SELECT regexp_replace(
    'TOKEN-12345678',
    '^(TOKEN-)[0-9]{4}([0-9]{4})$',
    '\1****\2'
) AS masked_token;
```

Kết quả:

```text
TOKEN-****5678
```

**Không coi regex che bớt ký tự là biện pháp bảo mật toàn diện.** Không được log hoặc truyền dữ liệu nhạy cảm theo cách có thể làm lộ chuỗi gốc ở những tầng khác; cần chính sách redaction và kiểm soát truy cập riêng.

### 14.6. Thay thế với phân biệt case

```sql
SELECT
    regexp_replace(
        'sql SQL Sql',
        'sql',
        'PostgreSQL',
        'g'
    ) AS case_sensitive_replacement,
    regexp_replace(
        'sql SQL Sql',
        'sql',
        'PostgreSQL',
        'gi'
    ) AS case_insensitive_replacement;
```

Trong ví dụ này:

- `g`: thay tất cả lần khớp chữ thường `sql`.
- `gi`: thay tất cả lần khớp không phân biệt hoa/thường.

Thứ tự các ký tự flag nhìn chung không quan trọng đối với chức năng cần dùng, nhưng nên thống nhất cách viết trong dự án.

## 15. Flags: thay đổi hành vi regex

Nhiều hàm regex nhận tham số `flags` dạng text.

Những flag đáng chú ý:

| Flag | Ý nghĩa thực hành |
| --- | --- |
| `i` | Không phân biệt hoa/thường |
| `c` | Phân biệt hoa/thường |
| `g` | Global: áp dụng cho các hàm hỗ trợ nhiều match/thay thế nhiều lần |
| `n` | Chế độ xử lý newline nhạy hơn |
| `p` | Một biến thể chế độ newline |
| `w` | Một biến thể chế độ newline theo quy tắc riêng |
| `s` | Chế độ không nhạy với newline theo cách PostgreSQL định nghĩa |
| `x` | Cú pháp expanded: cho phép cách trình bày pattern dễ đọc hơn, với các quy tắc riêng |

**Lưu ý:** không phải mọi hàm nhận mọi flag. Đặc biệt, flag **`g` không dùng để lấy “tất cả” từ `regexp_match`** vì hàm đó chỉ trả một mảng; muốn global extraction dùng `regexp_matches(...,'g')`.

### 15.1. Flag `i`

```sql
SELECT regexp_match(
    'ERROR code=E42',
    '^error',
    'i'
) AS case_insensitive_match;
```

Kết quả là mảng có đoạn `ERROR`, dù pattern dùng chữ thường.

### 15.2. Flag `x` cho pattern dễ đọc

Một regex dài có thể khó kiểm tra:

```sql
SELECT regexp_match(
    'INV-2026-0042',
    '^
      ([A-Z]+)       # Loại mã
      -
      ([0-9]{4})     # Năm
      -
      ([0-9]{4})     # Số thứ tự
    $',
    'x'
) AS readable_match;
```

Trong chế độ expanded, khoảng trắng dùng để trình bày và các phần chú thích theo cú pháp được xử lý khác so với regex thông thường. Vì thế, nếu muốn khớp một **dấu cách thật** trong pattern expanded, hãy biểu diễn nó tường minh, ví dụ `[[:space:]]` hoặc escape thích hợp.

Với regex dùng trong code review, tách cấu trúc mẫu và chú thích có thể giúp nhận ra thiếu anchor hoặc sai capture group.

### 15.3. Newline và anchors

Với chuỗi nhiều dòng:

```sql
SELECT
    'INFO start' || chr(10) || 'ERROR failed'
        ~ '^ERROR' AS default_anchor,
    regexp_match(
        'INFO start' || chr(10) || 'ERROR failed',
        '^ERROR',
        'n'
    ) AS newline_sensitive_match;
```

Flag `n` thay đổi cách PostgreSQL xử lý newline đối với một số cấu trúc như anchor. Tùy yêu cầu, nó có thể cho phép `^` khớp ở đầu một dòng trong văn bản nhiều dòng.

Không dịch trực tiếp flag từ JavaScript/PCRE sang PostgreSQL theo tên quen thuộc như `m`/`s` mà không kiểm tra: **bộ flag và quy tắc newline của PostgreSQL có định nghĩa riêng**.

### 15.4. Kiểm tra phiên bản khi dùng flag nâng cao

`SHOW server_version;` cho biết phiên bản PostgreSQL. Những chức năng mới và khả năng kết hợp với collation có thể phụ thuộc phiên bản, build và locale. Với ứng dụng cần độ ổn định cao, hãy kiểm tra mẫu trên phiên bản database thực tế và lưu test regression cho những trường hợp biên.

## 16. Escape ở hai tầng: SQL string và regex

Đây là nguồn gây nhiều nhầm lẫn khi copy pattern giữa ứng dụng và PostgreSQL.

### 16.1. SQL sử dụng dấu nháy đơn

Ví dụ muốn tìm dấu nháy đơn:

```sql
SELECT
    'It''s OK' ~ '''' AS contains_apostrophe;
```

Trong một literal SQL chuẩn, muốn viết dấu `'` bên trong chuỗi thì dùng `''`.

Cú pháp regex lại có quy tắc **backslash** để escape các metacharacter như dấu chấm.

### 16.2. `standard_conforming_strings`

Kiểm tra:

```sql
SHOW standard_conforming_strings;
```

Trong cài đặt PostgreSQL hiện đại, giá trị thông thường là `on`. Khi đó literal thông thường như:

```sql
'\d+'
```

giữ nguyên ký tự backslash để engine regex diễn giải `\d` theo cú pháp ARE.

Ví dụ:

```sql
SELECT 'code=123' ~ '\d+' AS contains_digits;
```

Nếu dùng **escape string literal** dạng `E'...'`, bạn phải escape backslash ở **tầng SQL**:

```sql
SELECT
    'code=123' ~ E'\\d+' AS contains_digits;
```

Hai dạng có thể cho cùng ý nghĩa regex khi `standard_conforming_strings = on`.

**Khuyến nghị cho người mới:** ưu tiên `[0-9]` hoặc `[[:digit:]]` trong các ví dụ SQL đơn giản nếu chưa quen số lượng backslash. Với dự án thực tế, hiểu rõ cả hai tầng escaping để không vô tình đổi pattern.

### 16.3. Backslash trong Java/JDBC còn thêm một tầng

Trong Java, code nguồn:

```java
String regex = "\\d+";
```

tạo một chuỗi chứa các ký tự `\d+` khi chạy. Nếu được truyền như một bind parameter:

```java
String sql = "SELECT ? ~ ?";
```

thì SQL driver sẽ gửi giá trị regex đúng theo cơ chế parameter binding, không cần tự viết một literal SQL chứa nhiều tầng dấu nháy và backslash.

Không nối trực tiếp input người dùng vào chuỗi SQL để “giải quyết” vấn đề escaping; điều đó gây rủi ro SQL injection.

## 17. `regexp_split_to_array`: tách chuỗi thành mảng

Hàm:

```sql
regexp_split_to_array(source, pattern [, flags])
```

sử dụng regex làm **dấu phân cách** rồi trả về `text[]`.

### 17.1. Tách bằng dấu phẩy hoặc chấm phẩy

```sql
SELECT regexp_split_to_array(
    'SQL, Java; PostgreSQL',
    '[[:space:]]*[,;][[:space:]]*'
) AS tokens;
```

Kết quả:

```text
{SQL,Java,PostgreSQL}
```

Pattern được hiểu:

- `[,;]`: dấu phẩy hoặc dấu chấm phẩy.
- `[[:space:]]*`: khoảng trắng tùy chọn hai bên dấu phân cách.

### 17.2. Các phần tử rỗng

```sql
SELECT regexp_split_to_array(
    'A,,B',
    ','
) AS tokens_with_empty_piece;
```

Kết quả có một **phần tử chuỗi rỗng** ở giữa vì hai dấu phân cách liên tiếp không chứa nội dung.

Đừng mặc định hàm split tự xóa mọi phần tử rỗng. Nếu dữ liệu đầu vào cho phép dấu phân cách lặp, hãy xác định có cần giữ dấu hiệu ô trống hay loại bỏ nó sau khi tách.

### 17.3. Số phần tử trong mảng

```sql
SELECT cardinality(
    regexp_split_to_array(
        'SQL, Java; PostgreSQL',
        '[[:space:]]*[,;][[:space:]]*'
    )
) AS token_count;
```

Kết quả là `3`.

Khi muốn lưu dữ liệu nhiều nhãn, thường nên cân nhắc một bảng quan hệ một-nhiều thay vì dùng text phân cách bằng dấu phẩy trong một cột. Regex split hữu ích cho dữ liệu nhập/chuyển đổi, không thay thế thiết kế quan hệ phù hợp.

## 18. `regexp_split_to_table`: tách chuỗi thành nhiều hàng

`regexp_split_to_table` có chức năng tương tự split to array, nhưng trả **tập hàng text**.

### 18.1. Ví dụ cơ bản

```sql
SELECT token
FROM regexp_split_to_table(
    'SQL, Java; PostgreSQL',
    '[[:space:]]*[,;][[:space:]]*'
) AS s(token);
```

Kết quả ba hàng:

```text
SQL
Java
PostgreSQL
```

### 18.2. Dùng `CROSS JOIN LATERAL` với bảng nguồn

```sql
WITH raw_tags(contact_id, tags) AS (
    VALUES
        (1, 'SQL, Java'),
        (2, 'PostgreSQL, SQL'),
        (3, '')
)
SELECT
    r.contact_id,
    x.tag
FROM raw_tags AS r
CROSS JOIN LATERAL regexp_split_to_table(
    r.tags,
    '[[:space:]]*,[[:space:]]*'
) AS x(tag)
WHERE x.tag <> ''
ORDER BY r.contact_id, x.tag;
```

Kết quả là các nhãn không rỗng của liên hệ 1 và 2. Liên hệ 3 không có nhãn hợp lệ nên không xuất hiện sau lọc `WHERE x.tag <> ''`.

Nếu muốn **giữ cả liên hệ không có nhãn**, dùng `LEFT JOIN LATERAL ... ON TRUE` và cân nhắc cách lọc phần tử rỗng mà không loại cả hàng trái.

### 18.3. Giữ vị trí phần tử bằng `WITH ORDINALITY`

```sql
SELECT
    x.position,
    x.tag
FROM regexp_split_to_table(
    'SQL, Java; PostgreSQL',
    '[[:space:]]*[,;][[:space:]]*'
) WITH ORDINALITY AS x(tag, position)
ORDER BY x.position;
```

`WITH ORDINALITY` thêm số thứ tự cho các phần tử được sinh ra, hữu ích nếu dữ liệu nhập có thứ tự cần giữ.

Đây là một khả năng của set-returning function trong PostgreSQL, không phải regex tự động phân tích giá trị “quan trọng nhất”.

## 19. Các hàm bổ sung trên PostgreSQL 15 trở lên

PostgreSQL 15 đưa thêm các hàm regex phù hợp với nhiều cách sử dụng thực tế. Nếu server dùng phiên bản cũ hơn, một số hàm bên dưới có thể không tồn tại.

Kiểm tra:

```sql
SHOW server_version;
```

### 19.1. `regexp_like`: trả boolean

```sql
SELECT regexp_like(
    'INV-2026-0042',
    '^INV-[0-9]{4}-[0-9]{4}$'
) AS valid_invoice_shape;
```

Trả `TRUE` với chuỗi hợp mẫu.

Có thể truyền flag:

```sql
SELECT regexp_like(
    'inv-2026-0042',
    '^INV-[0-9]{4}-[0-9]{4}$',
    'i'
) AS valid_ignoring_case;
```

Hàm tiện khi muốn API dạng `regexp_like(text, pattern, flags)`, nhưng với PostgreSQL lâu đời, toán tử `~`/`~*` vẫn rất phổ biến.

### 19.2. `regexp_count`: đếm số lần khớp

```sql
SELECT regexp_count(
    'tag=SQL; tag=Java; tag=SQL',
    'tag=[[:alpha:]]+'
) AS tags_count;
```

Kết quả `3`.

`regexp_count` đếm số đoạn khớp theo quy tắc hàm, khác với số token sau một phép split nếu chuỗi có dữ liệu không đúng định dạng.

### 19.3. `regexp_instr`: tìm vị trí đoạn khớp

```sql
SELECT regexp_instr(
    'abc123xyz',
    '[0-9]+'
) AS first_digit_group_position;
```

Kết quả là `4` vì nhóm chữ số đầu tiên bắt đầu ở ký tự thứ tư (PostgreSQL dùng vị trí ký tự **1-based** cho hàm này).

Khi không tìm thấy mẫu, hàm trả vị trí 0 theo ngữ nghĩa của `regexp_instr`, không phải một mảng NULL như `regexp_match`.

### 19.4. `regexp_substr`: trả đoạn khớp

```sql
SELECT regexp_substr(
    'ref=INV-2026-0042; ok',
    'INV-[0-9]{4}-[0-9]{4}'
) AS invoice_code;
```

Kết quả `INV-2026-0042`.

Hàm này trả một đoạn text thay vì mảng; có thể thuận tiện cho logic cần duy nhất đoạn khớp.

### 19.5. Lấy capture group bằng tham số `subexpr`

Trên PostgreSQL hỗ trợ chữ ký đầy đủ, `regexp_substr` có thể lấy một group cụ thể qua tham số thứ sáu:

```sql
SELECT regexp_substr(
    'INV-2026-0042',
    '^([A-Z]+)-([0-9]{4})-([0-9]{4})$',
    1,  -- Vị trí bắt đầu tìm
    1,  -- Lần khớp thứ nhất
    '', -- Flags
    3   -- Capture group thứ ba
) AS invoice_sequence;
```

Kết quả `0042`.

Cách dùng này hữu ích khi chỉ cần một capture group. Với nhiều group đồng thời, `regexp_match` có thể gọn hơn.

### 19.6. Không nhầm vị trí và số lần khớp

| Hàm | Ý nghĩa kết quả |
| --- | --- |
| `regexp_like` | Boolean: có khớp không? |
| `regexp_count` | Có bao nhiêu lần khớp? |
| `regexp_instr` | Match xuất hiện tại vị trí ký tự nào? |
| `regexp_substr` | Đoạn text nào khớp? |
| `regexp_match` | Mảng text của capture groups của lần khớp đầu |
| `regexp_matches` | Tập mảng text của một/nhiều lần khớp |

Đừng thay đổi tên hàm chỉ vì cú pháp trông tương tự: kiểu kết quả và số hàng trả về có thể khác nhau đáng kể.

## 20. Trích thông tin log hoàn chỉnh

Dữ liệu log dạng text thường có nhiều trường. Ta có thể bóc tách từng phần bằng regex, nhưng nên xem đây là **bước chuyển đổi dữ liệu không cấu trúc**, không phải cách định nghĩa log tốt nhất.

### 20.1. Lấy mức log

```sql
SELECT
    log_id,
    (regexp_match(
        log_line,
        '^(INFO|WARN|ERROR|DEBUG)[[:space:]]'
    ))[1] AS log_level
FROM regex_lab.logs
ORDER BY log_id;
```

Với năm dòng mẫu, kết quả lần lượt: INFO, WARN, ERROR, INFO, DEBUG.

### 20.2. Lấy mã đơn

```sql
SELECT
    log_id,
    (regexp_match(
        log_line,
        'order=([0-9]+)'
    ))[1] AS order_id_text
FROM regex_lab.logs
ORDER BY log_id;
```

Các log 101, 102 và 104 có mã đơn; 103 và 105 trả NULL.

### 20.3. Lấy số tiền

```sql
SELECT
    log_id,
    (regexp_match(
        log_line,
        'amount=([0-9]+(?:\.[0-9]+)?)'
    ))[1] AS amount_text
FROM regex_lab.logs
ORDER BY log_id;
```

Giải thích pattern:

- `amount=`: tiền tố cố định.
- `[0-9]+`: ít nhất một chữ số ở phần nguyên.
- `(?:\.[0-9]+)?`: phần thập phân tùy chọn; dùng `(?:...)` vì không cần capture group thứ hai.
- Capture ngoài lấy giá trị số, ví dụ `125.50` hoặc `0`.

**Cần kiểm soát điểm kết thúc của mẫu** nếu log có đầu vào không đáng tin: regex trên có thể khớp tiền tố của chuỗi dài hơn nhưng không hợp lệ, như `amount=12.34.56`. Với log có định dạng chặt, hãy đặt ranh giới token hoặc dùng parser có cấu trúc.

### 20.4. Trích nhiều trường trong một SELECT

```sql
SELECT
    l.log_id,
    (regexp_match(
        l.log_line,
        '^(INFO|WARN|ERROR|DEBUG)'
    ))[1] AS log_level,
    (regexp_match(
        l.log_line,
        'order=([0-9]+)'
    ))[1] AS order_id_text,
    (regexp_match(
        l.log_line,
        'amount=([0-9]+(?:\.[0-9]+)?)'
    ))[1] AS amount_text,
    (regexp_match(
        l.log_line,
        'code=([[:alnum:]]+)'
    ))[1] AS error_code
FROM regex_lab.logs AS l
ORDER BY l.log_id;
```

Kết quả mô tả:

| log_id | log_level | order_id_text | amount_text | error_code |
| ---: | --- | --- | --- | --- |
| 101 | INFO | 1001 | 125.50 | NULL |
| 102 | WARN | 1002 | 0 | NULL |
| 103 | ERROR | NULL | NULL | E42 |
| 104 | INFO | 1003 | 78.25 | NULL |
| 105 | DEBUG | NULL | NULL | NULL |

Khi dữ liệu đã được tách rõ trường, những bước sau có thể chuyển kiểu, tạo bảng sự kiện chuẩn hóa và thêm ràng buộc. Với log sản xuất quy mô lớn, nên cân nhắc **ghi JSON structured logs từ nguồn** để tránh chi phí regex lặp lại.

## 21. Chuẩn hóa dữ liệu: regex chỉ là một lớp xử lý

### 21.1. Email: regex không thay được xác minh thực tế

Có thể kiểm tra hình dạng sơ bộ:

```sql
SELECT
    contact_id,
    email,
    email ~* '^[^@[:space:]]+@[^@[:space:]]+\.[^@[:space:]]+$'
        AS basic_email_shape
FROM regex_lab.contacts
ORDER BY contact_id;
```

Đây là mẫu để phát hiện một số đầu vào sai rõ ràng; nó **không** bao quát đầy đủ cú pháp email theo tiêu chuẩn và không kiểm tra DNS, hộp thư, khả năng nhận thư hoặc chính sách domain.

Với đăng ký tài khoản, hãy kết hợp:

- Validation ở API/ứng dụng.
- Quy tắc chuẩn hóa được doanh nghiệp xác định.
- Kiểm tra độ dài và dữ liệu nguy hiểm.
- Gửi email xác nhận nếu cần chứng minh khả năng nhận thư.
- Ràng buộc unique phù hợp với chính sách danh tính.

### 21.2. Mã đơn: nên lưu dữ liệu chuẩn hóa

Nếu mã đơn luôn là:

```text
INV-YYYY-NNNN
```

bạn có thể chọn:

- Một cột text `invoice_code` với `CHECK` regex để bảo vệ hình dạng.
- Các cột `invoice_year` và `sequence` theo kiểu số, cùng cơ chế tạo mã hiển thị.
- Hoặc kết hợp hai cách có ràng buộc nhất quán.

Ví dụ:

```sql
CREATE TABLE regex_lab.invoices (
    invoice_code text PRIMARY KEY,
    created_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT chk_invoice_code_format
        CHECK (
            invoice_code ~ '^INV-[0-9]{4}-[0-9]{4}$'
        )
);
```

Câu này từ chối chuỗi không đúng định dạng, chẳng hạn `INV-26-42`. Nhưng nó **không** kiểm tra ngày/năm nghiệp vụ, khả năng trùng theo quy tắc phát hành hay tính liên tục của số thứ tự.

### 21.3. Vì sao vẫn cần `NOT NULL` và `CHECK` riêng?

Một ràng buộc:

```sql
CHECK (email ~ '...')
```

có thể cho một giá trị `NULL` đi qua vì điều kiện CHECK chỉ từ chối **FALSE**, trong khi biểu thức với NULL thường cho UNKNOWN.

Nếu cột bắt buộc có email:

```sql
CREATE TABLE regex_lab.required_emails (
    user_id bigint PRIMARY KEY,
    email text NOT NULL,
    CONSTRAINT chk_required_email_basic_shape
        CHECK (
            email ~* '^[^@[:space:]]+@[^@[:space:]]+\.[^@[:space:]]+$'
        )
);
```

`NOT NULL` yêu cầu có giá trị; `CHECK` kiểm tra hình dạng. Hai ràng buộc giải quyết **hai quy tắc khác nhau**.

### 21.4. Tránh làm mất dấu và Unicode

Một cách “làm sạch” nguy hiểm:

```sql
regexp_replace(full_name, '[^A-Za-z ]', '', 'g')
```

có thể **xóa chữ cái có dấu tiếng Việt** như `Đ`, `ă`, `ê`. Khi xử lý tên người hoặc nội dung quốc tế, không nên mặc định `A-Z` là toàn bộ bảng chữ cái.

Nếu muốn chuẩn hóa tên người, cần quy tắc Unicode, normalization và nghiệp vụ được thiết kế cẩn trọng; regex ASCII đơn giản thường không phù hợp.

## 22. Unicode, locale và collation ảnh hưởng ra sao?

### 22.1. UTF-8 lưu ký tự, regex mô tả mẫu

Nếu database dùng `UTF8`, PostgreSQL có thể lưu nhiều ngôn ngữ cùng lúc. Nhưng regex `[A-Za-z]` không tự hiểu mọi ký tự Unicode là chữ Latin có dấu hoặc chữ từ các hệ chữ khác.

`[[:alpha:]]` thường hữu ích hơn khi yêu cầu khớp một lớp chữ cái theo hệ thống, nhưng kết quả cụ thể cần được kiểm tra với locale/collation và phiên bản của PostgreSQL.

Kiểm tra:

```sql
SHOW server_encoding;
SHOW lc_collate;
SHOW lc_ctype;
```

### 22.2. Case-insensitive không đồng nghĩa accent-insensitive

```sql
SELECT
    'Bình' ~* 'bình' AS case_insensitive,
    'Bình' ~* 'binh' AS accent_automatically_removed;
```

Trong nhiều cấu hình thông thường, biểu thức đầu khớp và biểu thức thứ hai không khớp. Đừng coi `~*` là cách bỏ dấu tiếng Việt.

Nếu sản phẩm cần tìm `binh` để khớp `Bình`, phải xác định chính sách xử lý dấu/normalization và cân nhắc công cụ phù hợp; có thể cần chuẩn hóa vào cột tìm kiếm, sử dụng extension/thuật toán search được kiểm tra riêng.

### 22.3. Unicode normalization và biểu diễn kết hợp

Các ký tự trông giống nhau có thể có dãy code point khác nhau, ví dụ `é` dạng dựng sẵn và `e` cộng combining acute.

```sql
SELECT
    U&'\00E9' COLLATE "C" =
      U&'e\0301' COLLATE "C" AS equal_before,
    normalize(U&'\00E9', NFC) COLLATE "C" =
      normalize(U&'e\0301', NFC) COLLATE "C" AS equal_after_nfc;
```

Với UTF8:

- `equal_before` là FALSE theo `"C"`.
- `equal_after_nfc` là TRUE vì hai biểu diễn đã được chuẩn hóa về NFC.

Regex, `substring` và `length` có thể xử lý số code point theo cách khác với **số ký tự hiển thị mà người dùng cảm nhận**. Nếu đầu vào dùng nhiều dấu kết hợp, nên làm rõ chính sách normalization trước khi validate theo số ký tự.

### 22.4. Nondeterministic collation và regex

PostgreSQL hỗ trợ nondeterministic ICU collations cho một số quy tắc so sánh khác byte. Tuy nhiên, **regex và một số thao tác pattern matching không được hỗ trợ giống nhau với nondeterministic collations** trên các phiên bản hiện đại; bạn có thể gặp lỗi thay vì nhận kết quả như với collation deterministic.

Cần kiểm tra kiểu collation của cột, phiên bản PostgreSQL và toán tử sử dụng. Nếu mục tiêu là lọc bằng regex, có thể cần làm việc trên một biểu thức có **collation deterministic** phù hợp, ví dụ một cột text được xử lý/chuẩn hóa riêng, thay vì dựa vào collation không phân biệt case/dấu cho mọi thao tác.

Không ép tất cả query sang `COLLATE "C"` một cách máy móc: điều đó có thể làm thay đổi ngữ nghĩa phân biệt chữ hoa và ký tự quốc tế. Hãy chọn quy tắc theo yêu cầu dữ liệu.

## 23. Regex và tính chính xác của kiểu dữ liệu

### 23.1. Không dùng regex để thay thế kiểu số/ngày

Một chuỗi:

```text
2026-02-31
```

khớp mẫu:

```sql
'^[0-9]{4}-[0-9]{2}-[0-9]{2}$'
```

nhưng **ngày 31/02 không tồn tại**.

Nếu dữ liệu thực sự là ngày, nên lưu `date` trong bảng, kiểm tra/conversion bằng logic phù hợp và xử lý lỗi nhập một cách rõ ràng.

Tương tự:

- Tiền: `numeric(p,s)`.
- Số lượng: `integer`/`bigint`.
- Thời điểm: `timestamptz`.
- Trạng thái có tập giá trị cố định: `CHECK` hoặc bảng tham chiếu.

Regex phù hợp để **nhận biết cấu trúc đầu vào text** trước khi chuyển sang kiểu chuẩn, không thay thế ràng buộc kiểu dữ liệu.

### 23.2. Sau khi trích xuất nên kiểm tra giới hạn trước cast

Ví dụ dữ liệu `amount=125.50` được trích thành text; trước khi cast sang `numeric(12,2)` cần xác định:

- Có dấu âm không?
- Có cho phép phân cách hàng nghìn không?
- Có mấy chữ số thập phân?
- Giá trị có vượt precision/scale không?
- Đơn vị tiền là gì?
- Tỷ giá và quy tắc làm tròn ra sao?

Không nghĩ rằng `regexp_match` trả chuỗi khớp nghĩa là phép cast tiếp theo chắc chắn an toàn.

## 24. Hiệu năng: regex có thể đắt hơn so sánh đơn giản

Regex mạnh vì diễn đạt được nhiều mẫu, nhưng cũng có chi phí:

- Engine phải duyệt mẫu trên các chuỗi văn bản.
- Mẫu có nhánh/lặp phức tạp có thể cần xử lý đáng kể.
- Với nhiều triệu hàng, áp regex cho mọi hàng làm tăng CPU.
- Kết hợp global extraction có thể tạo nhiều hàng trung gian.
- Pattern không có phần chọn lọc tốt có thể khiến PostgreSQL quét phần lớn bảng.

### 24.1. Không thay phép bằng bằng regex khi không cần

Không nên:

```sql
SELECT *
FROM regex_lab.contacts
WHERE email ~ '^an@example\.com$';
```

nếu nghiệp vụ chỉ cần so sánh đúng một email và case/collation đã được xác định. Phép bằng:

```sql
WHERE email = 'an@example.com'
```

thường rõ nghĩa và có thể dễ được B-tree index hỗ trợ hơn.

Regex phù hợp khi **điều kiện mang tính mẫu**, ví dụ mã có cấu trúc hoặc log chứa một token cần trích.

### 24.2. Dùng `LIKE` cho tiền tố đơn giản

Nếu muốn tìm ghi chú bắt đầu `INV-`:

```sql
WHERE note LIKE 'INV-%'
```

thường dễ hiểu hơn:

```sql
WHERE note ~ '^INV-'
```

Tùy collation và operator class, B-tree index có thể hỗ trợ prefix search `LIKE 'prefix%'`. Regex có anchor đơn giản đôi khi cũng có thể được tối ưu, nhưng **không được giả định mọi regex đều sử dụng B-tree**.

### 24.3. `pg_trgm` có thể hỗ trợ regex search

PostgreSQL có extension `pg_trgm` giúp tìm kiếm dựa trên trigram, bao gồm một số điều kiện `LIKE`, `ILIKE` và regex `~`/`~*`.

Nếu môi trường cho phép tạo extension:

```sql
CREATE EXTENSION IF NOT EXISTS pg_trgm;

CREATE INDEX idx_contacts_note_trgm
ON regex_lab.contacts
USING gin (note gin_trgm_ops);
```

Một truy vấn có thể được hưởng lợi:

```sql
SELECT contact_id, note
FROM regex_lab.contacts
WHERE note ~ 'INV-[0-9]{4}-[0-9]{4}';
```

Nhưng hiệu quả phụ thuộc:

- Mẫu có **trigram hữu ích** để trích từ regex hay không.
- Độ chọn lọc.
- Số hàng và phân bố giá trị.
- Chi phí duy trì GIN index.
- Kế hoạch của PostgreSQL.

Các mẫu cực kỳ rộng hoặc ít phần chuỗi xác định có thể không có nhiều trigram hiệu quả; index vẫn có thể không được dùng.

### 24.4. Đo bằng `EXPLAIN`

```sql
EXPLAIN
SELECT contact_id, note
FROM regex_lab.contacts
WHERE note ~ 'INV-[0-9]{4}-[0-9]{4}';
```

Với bảng mẫu chỉ có sáu hàng, PostgreSQL rất có thể chọn `Seq Scan`; điều đó không chứng minh regex hoặc index sai.

Trên dữ liệu thực, cân nhắc:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT contact_id, note
FROM regex_lab.contacts
WHERE note ~ 'INV-[0-9]{4}-[0-9]{4}';
```

`EXPLAIN ANALYZE` sẽ thực thi câu SELECT. Nếu đo câu ghi như `UPDATE` hoặc `DELETE`, nó có thể gây tác động, nên chỉ thực hiện theo quy trình kiểm soát.

### 24.5. Chuyển dữ liệu text về cột có cấu trúc

Nếu hàng triệu truy vấn phải trích `order_id` từ `log_line`, có thể có lợi hơn khi ghi log có cấu trúc hoặc nạp trước vào cột:

```text
log_id | log_level | order_id | amount | message
```

Thay vì lặp `regexp_match` trong mọi SELECT, ứng dụng có thể truy vấn/index trực tiếp `order_id`. Đây thường là cải thiện mô hình dữ liệu, không chỉ tối ưu regex.

## 25. An toàn: SQL injection và regex không đáng tin cậy là hai rủi ro khác nhau

### 25.1. Bind parameters để tránh SQL injection

Không nối input trực tiếp:

```java
// Không an toàn:
String sql =
    "SELECT contact_id FROM regex_lab.contacts " +
    "WHERE note ~ '" + userPattern + "'";
```

Nếu `userPattern` chứa dấu nháy hoặc nội dung SQL độc hại, câu lệnh có thể bị thay đổi ý nghĩa hoặc lỗi.

Dùng `PreparedStatement`:

```java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;

public class ContactRegexSearch {
    public void search(Connection conn, String pattern)
            throws SQLException {
        String sql =
            "SELECT contact_id, note " +
            "FROM regex_lab.contacts " +
            "WHERE note ~ ? " +
            "ORDER BY contact_id";

        try (PreparedStatement stmt = conn.prepareStatement(sql)) {
            stmt.setString(1, pattern);

            try (ResultSet rs = stmt.executeQuery()) {
                while (rs.next()) {
                    long id = rs.getLong("contact_id");
                    String note = rs.getString("note");
                    System.out.println(id + ": " + note);
                }
            }
        }
    }
}
```

Ở đây `?` được bind như **giá trị regex**, không phải tự ghép thành cú pháp SQL. Điều đó giải quyết **SQL injection**, nhưng chưa giải quyết hết rủi ro từ một regex độc hại hoặc quá phức tạp.

### 25.2. Regex gây tiêu tốn CPU (*Regular Expression DoS*)

Một mẫu regex với nhiều nhánh và lặp phức tạp có thể khiến engine xử lý rất lâu trên chuỗi đầu vào được chọn khéo léo.

Vì vậy, nếu cho người dùng tự nhập regex để tìm trên bảng lớn:

- Giới hạn độ dài của regex.
- Giới hạn kích thước text được so khớp khi hợp lý.
- Giới hạn số hàng và thời gian query.
- Thiết kế các mẫu được phép thay vì cho quyền tùy ý khi có thể.
- Dùng `statement_timeout` ở mức ứng dụng/session/transaction theo chính sách.
- Theo dõi những query tiêu tốn CPU bất thường.
- Phân quyền dữ liệu để không cho regex quét những bảng nhạy cảm hoặc rất lớn ngoài nhu cầu.

Ví dụ một transaction có giới hạn thời gian minh họa:

```sql
BEGIN;

SET LOCAL statement_timeout = '2s';

SELECT contact_id
FROM regex_lab.contacts
WHERE note ~ 'INV-[0-9]{4}-[0-9]{4}';

COMMIT;
```

`SET LOCAL` chỉ áp dụng trong transaction. Nếu query bị timeout và transaction ở trạng thái lỗi, cần `ROLLBACK` trước khi tiếp tục. Timeout là một **hàng rào an toàn**, không thay thế kiểm soát mẫu và khối lượng dữ liệu.

### 25.3. Đừng xem regex input là code JavaScript/PCRE

PostgreSQL regex không hỗ trợ tất cả cú pháp của những engine khác. Một mẫu hợp lệ trong JavaScript/PCRE có thể:

- Cho kết quả khác.
- Không được hỗ trợ.
- Bị diễn giải khác ở chế độ escape.
- Có chi phí thực thi khác.

Nếu ứng dụng hỗ trợ regex do người dùng cung cấp, phải **định nghĩa dialect regex** được chấp nhận. Không nói chung chung “hỗ trợ mọi regex”.

### 25.4. Không lộ dữ liệu nhạy cảm qua extraction

Regex có thể tìm và trích email, mã định danh, token, số điện thoại. Đừng tự động đổ kết quả ra log/debug hoặc gửi về API khi người gọi không có quyền.

Ví dụ trích số thẻ hay token từ văn bản nhạy cảm còn tạo thêm bản sao thông tin, khiến phạm vi kiểm soát truy cập và lưu giữ dữ liệu mở rộng. Nếu nhu cầu thực tế chỉ là kiểm tra **có/không**, dùng boolean match thay vì trả toàn bộ đoạn nhạy cảm.

## 26. Lỗi thường gặp với regex PostgreSQL

| Hiện tượng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| `LIKE 'A%'` được đổi thành `~ 'A%'` và không khớp | `%` không phải wildcard regex | Dùng `'^A'` hoặc giữ LIKE |
| Dấu chấm khớp ký tự bất kỳ | `.` là metacharacter | Dùng `\.` cho dấu chấm thật |
| Regex khớp một phần chuỗi không hợp lệ | Thiếu `^` và `$` | Anchor toàn chuỗi khi validate |
| Một mã dài hơn mong muốn vẫn khớp | Mẫu không có ranh giới token | Thêm anchor/boundary phù hợp |
| `regexp_match` chỉ lấy một match | Hàm được thiết kế cho lần khớp đầu | Dùng `regexp_matches(...,'g')` |
| `regexp_matches` khiến mất hàng nguồn | Hàm set-returning trả 0 hàng khi không khớp | `LEFT JOIN LATERAL` hoặc `regexp_match` |
| `regexp_match` trả mảng thay vì text | Kiểu kết quả là `text[]` | Lấy `[1]`, `[2]` hoặc dùng regexp_substr |
| Chỉ số group bị lệch | Thêm capturing parentheses mới | Dùng `(?:...)` khi không cần capture |
| `regexp_replace` chỉ thay một chỗ | Chưa dùng flag `g` | Dùng `'g'` để thay tất cả |
| `regexp_replace` làm mất dấu trong tên | Mẫu chỉ chấp nhận ASCII | Thiết kế Unicode-aware |
| `~*` không tìm đúng chữ bỏ dấu | Không tự bỏ accent | Cần chiến lược normalization/search |
| `CHECK (text ~ pattern)` cho NULL lọt qua | CHECK không từ chối UNKNOWN | Thêm `NOT NULL` nếu bắt buộc |
| `email !~ regex` không thấy email NULL | `NULL !~ regex` là NULL | `IS NULL OR email !~ regex` |
| Tách `A,,B` có phần tử rỗng | Hai dấu phân cách liên tiếp | Định nghĩa cách xử lý empty tokens |
| `regexp_substr` không tồn tại | Phiên bản PostgreSQL cũ | Dùng substring/regexp_match hoặc nâng cấp |
| Tự ghép regex vào SQL | SQL injection | PreparedStatement/bind |
| Query regex chậm | Quét toàn bảng/mẫu phức tạp | Lọc trước, index phù hợp, EXPLAIN |
| Dùng B-tree như bảo đảm cho mọi regex | Regex không phải phép so sánh phạm vi đơn giản | Cân nhắc `pg_trgm` và đo |
| Kết quả khác Java Regex | Khác dialect/escape/locale | Test trên PostgreSQL thực tế |
| Nondeterministic ICU collation gây lỗi regex | Giới hạn hỗ trợ pattern matching | Kiểm tra collation và dùng quy tắc deterministic phù hợp |
| Regex parse ngày “đúng” nhưng date cast lỗi | Regex chỉ kiểm tra hình dạng | Validate ngày và dùng kiểu `date` |
| Regex phát hiện tiền xong ép integer bị overflow | Đầu vào lớn hơn miền kiểu | Kiểm tra range, dùng numeric/bigint hợp lý |
| Regex chạy lâu với input lạ | Mẫu phức tạp/input lớn | Giới hạn độ dài, timeout, quyền, giám sát |

## 27. Bài tập thực hành có gợi ý và đáp án

Các bài tập dùng bảng `regex_lab.contacts` và `regex_lab.logs` ở phần đầu.

### Bài 1. Tìm ghi chú có mã hóa đơn

```sql
SELECT contact_id, note
FROM regex_lab.contacts
WHERE note ~ 'INV-[0-9]{4}-[0-9]{4}'
ORDER BY contact_id;
```

**Đáp án:** liên hệ 1, 2, 5 và 6.

### Bài 2. Kiểm tra một mã có đúng định dạng toàn chuỗi

```sql
SELECT
    'INV-2026-0042' ~ '^INV-[0-9]{4}-[0-9]{4}$'
        AS correct_code,
    'prefix INV-2026-0042' ~ '^INV-[0-9]{4}-[0-9]{4}$'
        AS incorrect_code;
```

**Đáp án:** `TRUE` và `FALSE`. Anchor làm khác biệt.

### Bài 3. Tìm email kết thúc bằng example.com, không phân biệt case

```sql
SELECT contact_id, email
FROM regex_lab.contacts
WHERE email ~* '@example\.com$'
ORDER BY contact_id;
```

**Đáp án:** liên hệ 1 và 2.

### Bài 4. Tìm email thiếu hoặc không khớp hình dạng đơn giản

```sql
SELECT contact_id, email
FROM regex_lab.contacts
WHERE email IS NULL
   OR email !~* '^[^@[:space:]]+@[^@[:space:]]+$'
ORDER BY contact_id;
```

**Đáp án:** liên hệ 3 và 4. Đây chỉ là kiểm tra hình dạng, không xác minh email thật.

### Bài 5. Trích năm hóa đơn từ ghi chú

```sql
SELECT
    contact_id,
    (regexp_match(
        note,
        'INV-([0-9]{4})-[0-9]{4}'
    ))[1] AS invoice_year
FROM regex_lab.contacts
ORDER BY contact_id;
```

**Đáp án:** liên hệ 1 → 2026; 2 → 2026; 5 → 2025; 6 → 2026; hai liên hệ không có mã trả NULL.

### Bài 6. Trích toàn mã hóa đơn bằng `substring`

```sql
SELECT
    contact_id,
    substring(
        note FROM 'INV-[0-9]{4}-[0-9]{4}'
    ) AS invoice_code
FROM regex_lab.contacts
ORDER BY contact_id;
```

**Đáp án:** các mã đã biết ở bốn liên hệ; những hàng không khớp vẫn hiện với kết quả NULL.

### Bài 7. Trích hai nhóm của một mã hóa đơn

```sql
SELECT
    regexp_match(
        'INV-2026-0042',
        '^INV-([0-9]{4})-([0-9]{4})$'
    ) AS groups;
```

**Đáp án:** mảng `{2026,0042}`. Nhóm 1 là năm, nhóm 2 là thứ tự.

### Bài 8. Tìm tất cả nhãn trong một chuỗi

```sql
SELECT *
FROM regexp_matches(
    'tag=SQL; tag=Java; tag=SQL',
    'tag=([[:alpha:]]+)',
    'g'
);
```

**Đáp án:** ba hàng chứa các mảng `{SQL}`, `{Java}`, `{SQL}`. Hai nhãn SQL được giữ vì có hai lần khớp.

### Bài 9. Tại sao dùng `regexp_matches` lại làm mất liên hệ không có nhãn?

**Đáp án:** vì đó là **set-returning function**: không khớp → trả **0 hàng**. Khi dùng `CROSS JOIN LATERAL`, bản ghi nguồn không có kết quả bên phải bị loại. Nếu muốn giữ, dùng `LEFT JOIN LATERAL ... ON TRUE` hoặc `regexp_match` cho một lần khớp.

### Bài 10. Lấy hai mã lỗi trong ghi chú của Dung

```sql
SELECT m.parts[1] AS error_id
FROM regex_lab.contacts AS c
CROSS JOIN LATERAL regexp_matches(
    c.note,
    '#([0-9]+)',
    'g'
) AS m(parts)
WHERE c.contact_id = 4;
```

**Đáp án:** hai giá trị text `42` và `103`.

### Bài 11. Chuẩn hóa khoảng trắng

```sql
SELECT regexp_replace(
    'A   B     C',
    '[[:space:]]+',
    ' ',
    'g'
);
```

**Đáp án:** `A B C`.

### Bài 12. Bỏ dấu gạch nối, dấu cách và dấu cộng khỏi phone

```sql
SELECT
    contact_id,
    regexp_replace(phone, '[^0-9]', '', 'g') AS digits_only
FROM regex_lab.contacts
ORDER BY contact_id;
```

**Đáp án:** các chuỗi chỉ gồm chữ số; `phone NULL` vẫn thành NULL. **Không** kết luận mọi kết quả là số điện thoại hợp lệ.

### Bài 13. Đổi định dạng mã hóa đơn bằng backreference

```sql
SELECT regexp_replace(
    'INV-2026-0042',
    '^([A-Z]+)-([0-9]{4})-([0-9]{4})$',
    '\1/\2/\3'
);
```

**Đáp án:** `INV/2026/0042`.

### Bài 14. Tách một danh sách thành mảng

```sql
SELECT regexp_split_to_array(
    'SQL, Java; PostgreSQL',
    '[[:space:]]*[,;][[:space:]]*'
);
```

**Đáp án:** `{SQL,Java,PostgreSQL}`.

### Bài 15. Tách danh sách thành hàng có vị trí

```sql
SELECT x.position, x.tag
FROM regexp_split_to_table(
    'SQL, Java; PostgreSQL',
    '[[:space:]]*[,;][[:space:]]*'
) WITH ORDINALITY AS x(tag, position)
ORDER BY x.position;
```

**Đáp án:** `(1,SQL)`, `(2,Java)`, `(3,PostgreSQL)`.

### Bài 16. Tìm mọi log bắt đầu bằng INFO hoặc WARN

```sql
SELECT log_id, log_line
FROM regex_lab.logs
WHERE log_line ~ '^(INFO|WARN)[[:space:]]'
ORDER BY log_id;
```

**Đáp án:** log 101, 102 và 104.

### Bài 17. Trích mã đơn từ log

```sql
SELECT
    log_id,
    (regexp_match(
        log_line, 'order=([0-9]+)'
    ))[1] AS order_id_text
FROM regex_lab.logs
ORDER BY log_id;
```

**Đáp án:** 101 → 1001; 102 → 1002; 104 → 1003; các log khác có `order_id_text NULL`.

### Bài 18. Trích số tiền từ log

```sql
SELECT
    log_id,
    (regexp_match(
        log_line,
        'amount=([0-9]+(?:\.[0-9]+)?)'
    ))[1] AS amount_text
FROM regex_lab.logs
ORDER BY log_id;
```

**Đáp án:** 101 → 125.50; 102 → 0; 104 → 78.25; log còn lại NULL. Kết quả là text.

### Bài 19. Đếm số nhãn bằng `regexp_count`

*Yêu cầu PostgreSQL 15 trở lên.*

```sql
SELECT regexp_count(
    'tag=SQL; tag=Java; tag=SQL',
    'tag=[[:alpha:]]+'
) AS total_tags;
```

**Đáp án:** `3`.

### Bài 20. Trích lần khớp bằng `regexp_substr`

*Yêu cầu PostgreSQL 15 trở lên.*

```sql
SELECT regexp_substr(
    'ref INV-2026-0042 done',
    'INV-[0-9]{4}-[0-9]{4}'
);
```

**Đáp án:** `INV-2026-0042`.

### Bài 21. Vì sao `CHECK (col ~ pattern)` chưa buộc col có giá trị?

**Đáp án:** nếu col là NULL, biểu thức regex trả UNKNOWN. PostgreSQL `CHECK` không từ chối UNKNOWN; muốn cột bắt buộc có giá trị, thêm `NOT NULL`.

### Bài 22. Phân biệt `'g'` và `'i'`

```sql
SELECT
    regexp_replace('sql SQL Sql', 'sql', 'X', 'g')
        AS only_same_case,
    regexp_replace('sql SQL Sql', 'sql', 'X', 'gi')
        AS all_cases;
```

**Đáp án:** `'g'` thay mọi lần khớp theo case mặc định; `'gi'` vừa global vừa không phân biệt case.

### Bài 23. Tại sao không nên dùng `[A-Za-z]+` để xác minh họ tên tiếng Việt?

**Đáp án:** nhiều chữ cái tiếng Việt có dấu nằm ngoài dải ASCII `A-Z`/`a-z`. Mẫu có thể loại dữ liệu hợp lệ hoặc làm mất dấu nếu dùng để thay thế. Cần chiến lược Unicode/locale và nghiệp vụ thích hợp.

### Bài 24. Vì sao regex không thay thế kiểu `date`?

```sql
SELECT '2026-02-31' ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}$'
    AS correct_shape;
```

**Đáp án:** có thể trả TRUE vì hình dạng đúng, nhưng 31/02 không phải ngày lịch hợp lệ. Phải xác minh/parse bằng logic ngày phù hợp và lưu `date` nếu dữ liệu là ngày.

### Bài 25. Query regex nào nên cân nhắc `pg_trgm`?

Giả sử bảng có hàng triệu ghi chú và người dùng thường tìm những đoạn mã `INV-YYYY-NNNN` nằm giữa chuỗi.

**Gợi ý:** cân nhắc GIN trigram index trên cột tìm kiếm, xem pattern có những phần cố định đủ chọn lọc và đo `EXPLAIN (ANALYZE, BUFFERS)`. Không mặc định index sẽ giúp mọi regex, đặc biệt mẫu chỉ có wildcard hoặc không có trigram hữu ích.

### Bài 26. Regex do người dùng cung cấp đã bind parameter thì hoàn toàn an toàn chưa?

**Đáp án:** chưa. Bind parameter ngăn SQL injection, nhưng input regex vẫn có thể quá dài, có cấu trúc rất tốn CPU hoặc dùng để quét dữ liệu ngoài nhu cầu. Cần giới hạn mẫu, phạm vi tìm kiếm, timeout và quyền truy cập.

## 28. Checklist thực hành khi đưa regex vào ứng dụng

Trước khi đưa một regex vào migration, API hoặc báo cáo, hãy tự hỏi:

| Câu hỏi | Điều cần xác nhận |
| --- | --- |
| Muốn so khớp toàn chuỗi hay một đoạn con? | `^...$` hay mẫu không anchor |
| Chỉ cần tiền tố đơn giản? | `LIKE` có thể rõ hơn regex |
| Phải phân biệt case không? | `~` / `~*` hoặc flag `i` |
| Có trường hợp `NULL`? | Tránh quên UNKNOWN trong WHERE/CHECK |
| Muốn một match hay tất cả? | `regexp_match` so với `regexp_matches(...,'g')` |
| Muốn giữ hàng không khớp? | `regexp_match` hoặc `LEFT JOIN LATERAL` |
| Mẫu có nhiều capture group? | Kiểm soát thứ tự `[1]`, `[2]` |
| Có nhóm chỉ để áp lượng từ/lựa chọn? | Dùng `(?:...)` khi phù hợp |
| Có ký tự regex đặc biệt theo nghĩa đen? | Escape dấu chấm, ngoặc, ký tự cần thiết |
| Có lẫn tầng escape SQL và regex? | Xem `standard_conforming_strings` / `E'...'` |
| Có xử lý Unicode/tiếng Việt? | Không coi `[A-Za-z]` là toàn bộ chữ cái |
| Có cần bỏ dấu? | `~*` không tự làm việc đó |
| Cần parse số hoặc ngày sau match? | Kiểm tra miền giá trị, không chỉ hình dạng |
| Có dùng phiên bản PostgreSQL dưới 15? | Kiểm tra `regexp_like/count/instr/substr` |
| Có dùng nondeterministic collation? | Kiểm tra khả năng hỗ trợ regex |
| Input regex do người dùng nhập? | Bind parameter, giới hạn độ phức tạp, timeout |
| Query trên nhiều triệu hàng? | Lọc trước, cân nhắc `pg_trgm`, đo `EXPLAIN` |
| Cần trích thông tin thường xuyên? | Có thể nên lưu cột có cấu trúc |
| Regex có trích dữ liệu nhạy cảm? | Giới hạn quyền, masking, logging |
| Đã có test trường hợp biên? | Chuỗi rỗng, NULL, ký tự có dấu, dấu escape, match lặp |

## 29. Tổng kết

**Biểu thức chính quy và trích xuất mẫu** trong PostgreSQL giúp làm việc với những chuỗi có cấu trúc một phần: mã đơn, log, nhãn, văn bản nhập từ hệ thống khác.

Những ý quan trọng nhất:

1. **`~` và `~*`** kiểm tra chuỗi có khớp regex hay không; `!~` và `!~*` kiểm tra phủ định. Các toán tử này **không tự yêu cầu khớp toàn chuỗi** nếu không có anchor.
2. **`^`, `$`, character class và quantifier** giúp mô tả cấu trúc, ví dụ `^INV-[0-9]{4}-[0-9]{4}$`.
3. **Capture group `(...)`** cho phép lấy từng thành phần; nhóm `(?:...)` phục vụ gom cú pháp mà không tạo capture.
4. **`regexp_match`** trả một mảng `text[]` hoặc NULL; **`regexp_matches`** là set-returning function và flag `g` tạo một hàng cho mỗi lần khớp.
5. **`LEFT JOIN LATERAL`** rất quan trọng khi muốn trích nhiều match mà **vẫn giữ các hàng nguồn không khớp**.
6. **`substring(... FROM pattern)`** và `regexp_substr` phù hợp để lấy một đoạn khớp; `regexp_substr`, `regexp_count`, `regexp_instr` và `regexp_like` cần kiểm tra phiên bản PostgreSQL 15+.
7. **`regexp_replace`** thay thế đoạn khớp; flag `g` thay nhiều lần, backreference `\1`/`\2` tái sử dụng capture groups trong replacement.
8. **`regexp_split_to_array` và `regexp_split_to_table`** biến chuỗi có dấu phân cách thành mảng hoặc các hàng.
9. **Regex không phải validator nghiệp vụ hoàn chỉnh**: đúng hình dạng email không chứng minh email tồn tại; đúng mẫu ngày không chứng minh ngày hợp lệ; đúng chuỗi số không bảo đảm giá trị nằm trong giới hạn của kiểu.
10. **SQL escaping và regex escaping là hai tầng khác nhau**. Dùng prepared statement/bind parameter để truyền mẫu một cách an toàn, thay vì nối input vào SQL.
11. **Unicode, locale và collation** có thể ảnh hưởng các lớp ký tự và case-insensitive matching; `~*` không tự bỏ dấu tiếng Việt.
12. **Hiệu năng và bảo mật** cần được kiểm soát khi regex chạy trên nhiều dữ liệu hoặc nhận pattern từ người dùng. Có thể dùng `pg_trgm` cho một số workload, nhưng vẫn phải đo.

Một quy trình dễ áp dụng:

```text
Văn bản đầu vào
       |
       v
Xác định mục tiêu:
  Có khớp?  -> ~ / ~*
  Một match? -> regexp_match / substring
  Nhiều match? -> regexp_matches(..., 'g')
  Thay thế? -> regexp_replace
  Tách token? -> regexp_split_to_array / regexp_split_to_table
       |
       v
Xử lý NULL, dữ liệu không khớp, Unicode
       |
       v
Kiểm tra quy tắc nghiệp vụ và chuyển kiểu
       |
       v
Lưu dữ liệu có cấu trúc / truy vấn / báo cáo
```

**Quy tắc dễ nhớ:** dùng regex để **nhận diện và tách mẫu văn bản**, dùng **kiểu dữ liệu và ràng buộc PostgreSQL** để bảo vệ ý nghĩa của dữ liệu, và dùng **JOIN/NULL handling đúng** để không làm sai số hàng khi trích nhiều kết quả.
