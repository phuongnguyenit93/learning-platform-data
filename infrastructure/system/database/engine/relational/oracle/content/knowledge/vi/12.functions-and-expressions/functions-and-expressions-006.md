# REGEXP_LIKE, REGEXP_SUBSTR, REGEXP_REPLACE và giới hạn sử dụng trong Oracle Database

Oracle Database cung cấp các biểu thức chính quy (*regular expressions*) để kiểm tra, trích xuất và biến đổi chuỗi. Ba thành phần thường dùng là:

- **`REGEXP_LIKE`**: điều kiện lọc một chuỗi có khớp mẫu hay không.
- **`REGEXP_SUBSTR`**: lấy phần chuỗi khớp với mẫu hoặc một nhóm bắt giữ trong mẫu.
- **`REGEXP_REPLACE`**: thay phần chuỗi khớp mẫu bằng nội dung khác.

Các hàm này hữu ích khi dữ liệu có cấu trúc không cố định hoàn toàn, chẳng hạn mã đơn hàng, số điện thoại, chuỗi log hoặc dữ liệu nhập từ nhiều hệ thống. Tuy nhiên, regex không phải công cụ thay thế cho mọi phép tìm kiếm. Với điều kiện đơn giản như tìm tiền tố, kiểm tra bằng `=` hoặc `LIKE` thường dễ đọc và có thể hiệu quả hơn. Biểu thức quá phức tạp cũng khó bảo trì, tốn CPU và có thể tạo ra kết quả ngoài ý muốn.

Bài học giải thích cú pháp Oracle, các thành phần pattern, tham số so khớp, nhóm bắt giữ, cách trích xuất/thay thế, giới hạn kỹ thuật, vấn đề `NULL`, hiệu năng và bảo mật. Các ví dụ hướng đến Oracle Database 19c trở lên, dùng SQL*Plus, SQLcl hoặc công cụ SQL tương thích.

## 1. Regex trong Oracle dùng để làm gì?

### 1.1. So sánh LIKE và REGEXP

`LIKE` phù hợp với hai wildcard cơ bản:

- `%`: không hoặc nhiều ký tự.
- `_`: đúng một ký tự.

Ví dụ:

```sql
SELECT product_name
FROM   demo_products
WHERE  product_name LIKE 'Laptop%';
```

Nếu cần kiểm tra một mã có đúng cấu trúc như ba chữ cái, dấu gạch ngang và bốn chữ số, `LIKE` có thể viết được nhưng khó diễn đạt chính xác. Regex làm việc này tự nhiên hơn:

```sql
SELECT product_code
FROM   demo_products
WHERE  REGEXP_LIKE(product_code, '^[[:alpha:]]{3}-[[:digit:]]{4}$');
```

Mẫu trên yêu cầu toàn bộ chuỗi có dạng:

```text
ABC-1234
```

Trong đó `^` đánh dấu đầu chuỗi, `$` đánh dấu cuối chuỗi, `[[:alpha:]]{3}` là ba chữ cái và `[[:digit:]]{4}` là bốn chữ số.

| Nhu cầu | Công cụ thường phù hợp |
| --- | --- |
| Bằng chính xác một giá trị | `=` |
| Thuộc danh sách giá trị | `IN` |
| Bắt đầu bằng tiền tố đơn giản | `LIKE 'ABC%'` |
| Chứa chuỗi đơn giản | `LIKE '%ABC%'` |
| Kiểm tra cấu trúc phức tạp | `REGEXP_LIKE` |
| Lấy một phần theo pattern | `REGEXP_SUBSTR` |
| Chuẩn hóa/thay một phần theo pattern | `REGEXP_REPLACE` |

Không nên dùng regex chỉ vì nó có vẻ mạnh hơn. Hãy chọn biểu thức đơn giản nhất diễn đạt đúng yêu cầu.

### 1.2. Ba chức năng giải quyết ba việc khác nhau

| Thành phần | Vai trò | Kết quả |
| --- | --- | --- |
| `REGEXP_LIKE(source, pattern, ...)` | Kiểm tra điều kiện | TRUE/FALSE/UNKNOWN trong ngữ cảnh SQL |
| `REGEXP_SUBSTR(source, pattern, ...)` | Tìm và trích xuất | Một chuỗi khớp hoặc `NULL` nếu không tìm thấy |
| `REGEXP_REPLACE(source, pattern, replacement, ...)` | Tìm và thay | Chuỗi đã được thay thế |

**`REGEXP_LIKE` là một điều kiện SQL**, thường xuất hiện trong `WHERE`, `CASE WHEN` hoặc `CHECK`. Nó không phải hàm trả về chuỗi giống `REGEXP_SUBSTR`.

## 2. Cú pháp REGEXP_LIKE

### 2.1. Cú pháp tổng quát

```sql
REGEXP_LIKE(
    source_char,
    pattern
    [, match_param]
)
```

- `source_char`: biểu thức ký tự cần kiểm tra, ví dụ một cột `VARCHAR2`.
- `pattern`: biểu thức chính quy cần khớp.
- `match_param`: tùy chọn điều khiển cách so khớp, chẳng hạn phân biệt hoa–thường hoặc xử lý ký tự xuống dòng.

Ví dụ:

```sql
SELECT employee_id, email
FROM   employees
WHERE  REGEXP_LIKE(email, '^[[:alnum:]_.+-]+@[[:alnum:].-]+\.[[:alpha:]]{2,}$', 'i');
```

Đây là **mẫu kiểm tra hình thức email đơn giản**, không phải bộ xác thực đầy đủ theo mọi tiêu chuẩn email. Nó có thể loại một số địa chỉ hợp lệ đặc biệt hoặc chấp nhận địa chỉ không thực sự tồn tại. Xác minh email thực tế thường cần thêm quy tắc nghiệp vụ và xác nhận ở hệ thống gửi/nhận thư.

### 2.2. Regex mặc định tìm ở bất kỳ vị trí nào

Nếu không có anchor `^` và `$`, Oracle có thể tìm một phần khớp ở bất kỳ vị trí nào trong chuỗi.

Ví dụ:

```sql
SELECT CASE
         WHEN REGEXP_LIKE('Order AB-2048 shipped',
                          '[[:alpha:]]{2}-[[:digit:]]{4}')
         THEN 'MATCH'
         ELSE 'NO MATCH'
       END AS result
FROM dual;
```

Kết quả là `MATCH`, vì chuỗi có chứa đoạn `AB-2048`.

Nếu muốn **toàn bộ chuỗi** phải có đúng định dạng, dùng anchor:

```sql
SELECT CASE
         WHEN REGEXP_LIKE('AB-2048',
                          '^[[:alpha:]]{2}-[[:digit:]]{4}$')
         THEN 'MATCH'
         ELSE 'NO MATCH'
       END AS result
FROM dual;
```

### 2.3. Phân biệt REGEXP_LIKE với LIKE

`LIKE` dùng `%` và `_` làm wildcard. Trong regex, ý nghĩa khác:

| Mục tiêu | LIKE | Regex |
| --- | --- | --- |
| Bất kỳ chuỗi ký tự | `%` | `.*` |
| Một ký tự bất kỳ | `_` | `.` |
| Bắt đầu chuỗi | Mẫu tiền tố như `'ABC%'` | `^` |
| Kết thúc chuỗi | Mẫu hậu tố như `'%XYZ'` | `$` |
| Một trong các chữ số | Không có cú pháp gọn tương đương | `[[:digit:]]` |
| Lặp 3 đến 5 lần | Không có quantifier | `{3,5}` |
| Một trong hai lựa chọn | Có thể dùng nhiều điều kiện | `(A|B)` |

Không mang pattern của LIKE sang REGEXP hoặc ngược lại. Ví dụ `REGEXP_LIKE(code, 'A%')` không có nghĩa giống `code LIKE 'A%'`: trong regex, `%` là ký tự phần trăm thông thường, còn `.*` mới biểu diễn phần đuôi tùy ý.

## 3. Thành phần cơ bản của pattern

Oracle hỗ trợ chuẩn POSIX regular expressions và các hướng dẫn biểu thức chính quy Unicode, cùng một số phần mở rộng chịu ảnh hưởng từ Perl. Không nên mặc định mọi cú pháp của PCRE, Java hoặc JavaScript đều dùng được trong Oracle.

### 3.1. Anchor và ký tự bất kỳ

| Ký hiệu | Ý nghĩa |
| --- | --- |
| `^` | Đầu chuỗi; với chế độ nhiều dòng có thể khớp đầu dòng |
| `$` | Cuối chuỗi; với chế độ nhiều dòng có thể khớp cuối dòng |
| `.` | Một ký tự bất kỳ, trừ newline theo chế độ mặc định |
| `\` | Dùng để escape ký tự đặc biệt hoặc biểu diễn một số lớp ký tự theo cú pháp được hỗ trợ |

Ví dụ mã bắt đầu bằng `INV-`:

```sql
SELECT order_code
FROM   orders
WHERE  REGEXP_LIKE(order_code, '^INV-');
```

Ví dụ mã kết thúc bằng bốn chữ số:

```sql
SELECT order_code
FROM   orders
WHERE  REGEXP_LIKE(order_code, '[[:digit:]]{4}$');
```

### 3.2. Character class và bracket expression

Dùng dấu ngoặc vuông để chỉ một ký tự trong tập hợp:

| Pattern | Ý nghĩa |
| --- | --- |
| `[ABC]` | Một ký tự A, B hoặc C |
| `[A-Z]` | Một chữ cái trong dải A đến Z theo quy tắc so khớp áp dụng |
| `[0-9]` | Một chữ số ASCII từ 0 đến 9 |
| `[^0-9]` | Một ký tự không thuộc tập chữ số |
| `[[:digit:]]` | Một ký tự thuộc lớp chữ số POSIX |
| `[[:alpha:]]` | Một ký tự thuộc lớp chữ cái |
| `[[:alnum:]]` | Một ký tự chữ hoặc số |
| `[[:space:]]` | Một ký tự khoảng trắng |
| `[[:lower:]]` | Một ký tự chữ thường |
| `[[:upper:]]` | Một ký tự chữ hoa |

Ví dụ chỉ chấp nhận mã gồm chữ hoa và chữ số:

```sql
SELECT code
FROM   demo_codes
WHERE  REGEXP_LIKE(code, '^[[:upper:][:digit:]]+$');
```

Các POSIX character classes giúp diễn đạt ý nghĩa theo lớp ký tự. Với dữ liệu đa ngôn ngữ, kết quả còn phụ thuộc character set/collation và các quy tắc Unicode của môi trường; đừng coi mọi dải `A-Z` hoặc `0-9` là cách biểu diễn đầy đủ mọi chữ cái/chữ số trên thế giới.

### 3.3. Quantifier: số lần lặp

| Ký hiệu | Ý nghĩa |
| --- | --- |
| `*` | 0 hoặc nhiều lần |
| `+` | 1 hoặc nhiều lần |
| `?` | 0 hoặc 1 lần |
| `{m}` | Chính xác m lần |
| `{m,}` | Ít nhất m lần |
| `{m,n}` | Từ m đến n lần |

Ví dụ:

```sql
-- Một hoặc nhiều chữ số.
REGEXP_LIKE(code, '[[:digit:]]+')

-- Chính xác 8 chữ số.
REGEXP_LIKE(code, '^[[:digit:]]{8}$')

-- Từ 2 đến 4 chữ cái.
REGEXP_LIKE(code, '^[[:alpha:]]{2,4}$')
```

Quantifier áp dụng cho thành phần ngay trước nó. Nếu muốn lặp một nhóm, đặt nhóm trong ngoặc:

```sql
-- Một hoặc nhiều nhóm gồm hai chữ số.
REGEXP_LIKE(code, '^([[:digit:]]{2})+$')
```

### 3.4. Alternation và grouping

- `|` biểu diễn lựa chọn OR.
- `(...)` nhóm một phần pattern; nhóm có thể trở thành capture group khi trích xuất/thay thế.

Ví dụ mã bắt đầu bằng `INV` hoặc `CRN`, tiếp theo là dấu gạch ngang và sáu chữ số:

```sql
SELECT document_code
FROM   documents
WHERE  REGEXP_LIKE(
         document_code,
         '^(INV|CRN)-[[:digit:]]{6}$'
       );
```

Mẫu này chấp nhận `INV-123456` và `CRN-987654`, nhưng không chấp nhận `ABC-123456` hoặc `INV-123`.

### 3.5. Escape ký tự đặc biệt

Nếu muốn tìm dấu chấm thực sự, phải escape dấu chấm vì `.` trong regex đại diện cho một ký tự bất kỳ.

```sql
SELECT host_name
FROM   server_inventory
WHERE  REGEXP_LIKE(host_name, '\.example\.com$');
```

Mẫu này tìm chuỗi kết thúc bằng `.example.com`. Trong literal SQL của Oracle, dấu backslash không được xử lý theo kiểu escape chuỗi như trong Java; ở đây backslash là ký hiệu escape của regex.

Nếu pattern được viết bên trong chuỗi Java, JSON hoặc một lớp cấu hình khác, còn phải xử lý escaping theo cú pháp của lớp đó.

### 3.6. Greedy matching và phạm vi khớp

Quantifier thông thường có xu hướng lấy phần khớp dài nhất có thể trong ngữ cảnh pattern (greedy). Ví dụ:

```sql
SELECT REGEXP_SUBSTR(
         'A<one><two>B',
         '<.*>'
       ) AS matched_text
FROM dual;
```

Mẫu `<.*>` có thể lấy từ dấu `<` đầu tiên đến dấu `>` cuối cùng, cho kết quả `<one><two>`.

Nếu chỉ muốn lấy cụm ngắn đầu tiên, giới hạn pattern để không đi qua dấu `>`:

```sql
SELECT REGEXP_SUBSTR(
         'A<one><two>B',
         '<[^>]*>'
       ) AS first_tag
FROM dual;
```

Kết quả là `<one>`. Cách giới hạn miền ký tự thường rõ ràng và dễ kiểm soát hơn việc dựa vào một cú pháp non-greedy không chắc tương thích với mọi regex engine.

## 4. Tham số match_param

Oracle cho phép truyền chuỗi tùy chọn để thay đổi cách so khớp.

| Ký tự | Tác dụng |
| --- | --- |
| `'i'` | So khớp không phân biệt chữ hoa–chữ thường |
| `'c'` | So khớp phân biệt chữ hoa–chữ thường |
| `'n'` | Dấu chấm `.` khớp cả ký tự newline |
| `'m'` | `^` và `$` nhận biết ranh giới từng dòng trong chuỗi nhiều dòng |
| `'x'` | Bỏ qua khoảng trắng trong pattern theo chế độ extended matching |

### 4.1. i và c: hoa–thường

```sql
SELECT CASE
         WHEN REGEXP_LIKE('Oracle Database', '^oracle', 'i')
         THEN 'MATCH'
         ELSE 'NO MATCH'
       END AS insensitive_result
FROM dual;
```

Với `'i'`, chữ hoa–thường được bỏ qua cho việc so khớp.

Muốn phân biệt rõ:

```sql
SELECT CASE
         WHEN REGEXP_LIKE('Oracle Database', '^oracle', 'c')
         THEN 'MATCH'
         ELSE 'NO MATCH'
       END AS sensitive_result
FROM dual;
```

Trong nhiều tình huống mặc định là phân biệt hoa–thường, nhưng nên truyền rõ `'c'` hoặc `'i'` khi yêu cầu nghiệp vụ cần được thể hiện tường minh. Quy tắc collation cũng có thể ảnh hưởng so khớp.

### 4.2. n: dấu chấm khớp newline

Mặc định `.` không khớp ký tự xuống dòng. Thêm `'n'` để thay đổi:

```sql
SELECT CASE
         WHEN REGEXP_LIKE(
                'first line' || CHR(10) || 'second line',
                'first.*second',
                'n'
              )
         THEN 'MATCH'
         ELSE 'NO MATCH'
       END AS newline_result
FROM dual;
```

`CHR(10)` tạo line feed. Khi dùng `'n'`, dấu chấm có thể đi qua ký tự newline theo quy tắc của Oracle.

### 4.3. m: anchor theo từng dòng

`m` thay đổi cách `^` và `$` hoạt động trên chuỗi nhiều dòng:

```sql
SELECT CASE
         WHEN REGEXP_LIKE(
                'header' || CHR(10) || 'ERROR: disk full',
                '^ERROR:',
                'm'
              )
         THEN 'FOUND'
         ELSE 'NOT FOUND'
       END AS multiline_result
FROM dual;
```

Với chế độ nhiều dòng, `^ERROR:` có thể khớp đầu dòng thứ hai, không chỉ đầu toàn bộ chuỗi.

Phân biệt:

- `m` điều khiển ý nghĩa đầu/cuối dòng của anchor.
- `n` điều khiển việc dấu chấm `.` có khớp newline hay không.

Hai tham số này không thay thế nhau.

### 4.4. x: bỏ qua khoảng trắng trong pattern

Chế độ `x` giúp pattern dài dễ đọc hơn bằng cách bỏ qua khoảng trắng trong pattern:

```sql
SELECT CASE
         WHEN REGEXP_LIKE(
                'INV-123456',
                '^ [[:alpha:]]{3} - [[:digit:]]{6} $',
                'x'
              )
         THEN 'MATCH'
         ELSE 'NO MATCH'
       END AS extended_result
FROM dual;
```

Khi dùng `x`, cần chú ý khoảng trắng trong pattern không còn được hiểu đơn giản là ký tự cần khớp. Nếu thật sự muốn khớp một dấu cách, hãy mô tả rõ bằng lớp ký tự hoặc cách viết pattern phù hợp, ví dụ `[[:space:]]`.

### 4.5. Kết hợp tham số

Có thể kết hợp các ký tự match parameter:

```sql
REGEXP_LIKE(log_message, '^error:.*timeout', 'in')
```

Mẫu này không phân biệt hoa–thường và cho dấu chấm khớp newline. Dùng chuỗi tham số ngắn, có chủ ý và ghi chú khi pattern cần giải thích cho người bảo trì.

## 5. REGEXP_SUBSTR: trích xuất phần chuỗi khớp mẫu

### 5.1. Cú pháp

```sql
REGEXP_SUBSTR(
    source_char,
    pattern
    [, position
       [, occurrence
          [, match_param
             [, subexpr]
          ]
       ]
    ]
)
```

| Tham số | Ý nghĩa |
| --- | --- |
| `source_char` | Chuỗi nguồn |
| `pattern` | Pattern cần tìm |
| `position` | Vị trí bắt đầu tìm, mặc định 1 |
| `occurrence` | Lần xuất hiện cần lấy, mặc định 1 |
| `match_param` | Tham số so khớp như `i`, `c`, `n`, `m`, `x` |
| `subexpr` | Nhóm bắt giữ cần trả về; 0 là toàn bộ match, 1–9 là nhóm tương ứng |

Nếu không tìm thấy phần khớp, hàm trả `NULL`. Vị trí `position` được tính theo ký tự theo ngữ nghĩa của hàm, không nên tự đổi thành byte offset.

### 5.2. Trích xuất lần xuất hiện đầu tiên

```sql
SELECT REGEXP_SUBSTR(
         'Order AB-2048 shipped',
         '[[:alpha:]]+-[[:digit:]]+'
       ) AS order_code
FROM dual;
```

Kết quả:

```text
AB-2048
```

Không chỉ dùng được với literal; thường áp dụng trực tiếp cho cột:

```sql
SELECT log_id,
       REGEXP_SUBSTR(message, '[[:alpha:]]+-[[:digit:]]+') AS order_code
FROM   application_logs;
```

### 5.3. Lấy lần xuất hiện thứ n

```sql
SELECT REGEXP_SUBSTR(
         'red,green,blue,yellow',
         '[^,]+',
         1,
         3
       ) AS third_item
FROM dual;
```

Kết quả là `blue`.

Ở đây:

- `position = 1`: bắt đầu từ ký tự đầu.
- `occurrence = 3`: lấy lần khớp thứ ba.
- `[^,]+`: một hoặc nhiều ký tự không phải dấu phẩy.

Hàm tìm occurrence tiếp theo sau phần khớp trước đó, không chỉ dịch vị trí bắt đầu đi một ký tự. Điều này giúp tách các token liên tiếp.

**Lưu ý:** pattern `[^,]+` bỏ qua token rỗng. Với chuỗi `red,,blue`, lần khớp thứ hai là `blue`, không phải một chuỗi rỗng nằm giữa hai dấu phẩy. Nếu cần bảo toàn trường rỗng trong dữ liệu CSV, phải thiết kế cách tách phù hợp hơn, không dựa vào `[^,]+` một cách máy móc.

### 5.4. Trích xuất capture group bằng subexpr

Giả sử chuỗi là `Order AB-2048 shipped` và muốn lấy riêng phần số:

```sql
SELECT REGEXP_SUBSTR(
         'Order AB-2048 shipped',
         '([[:alpha:]]+)-([[:digit:]]+)',
         1,
         1,
         'c',
         2
       ) AS order_number
FROM dual;
```

Kết quả là `2048`.

Pattern có hai nhóm:

1. `([[:alpha:]]+)`: phần chữ `AB`.
2. `([[:digit:]]+)`: phần số `2048`.

`subexpr = 2` yêu cầu hàm trả về nhóm thứ hai, thay vì toàn bộ đoạn `AB-2048`. Giá trị mặc định `subexpr = 0` trả về toàn bộ match.

### 5.5. Lấy nhiều trường từ cùng một chuỗi

Ví dụ phân tích mã `INV-2026-00125`:

```sql
SELECT
    REGEXP_SUBSTR(
      'INV-2026-00125',
      '^([[:alpha:]]+)-([[:digit:]]{4})-([[:digit:]]+)$',
      1, 1, 'c', 1
    ) AS document_type,
    REGEXP_SUBSTR(
      'INV-2026-00125',
      '^([[:alpha:]]+)-([[:digit:]]{4})-([[:digit:]]+)$',
      1, 1, 'c', 2
    ) AS document_year,
    REGEXP_SUBSTR(
      'INV-2026-00125',
      '^([[:alpha:]]+)-([[:digit:]]{4})-([[:digit:]]+)$',
      1, 1, 'c', 3
    ) AS document_sequence
FROM dual;
```

Kết quả khái niệm:

| DOCUMENT_TYPE | DOCUMENT_YEAR | DOCUMENT_SEQUENCE |
| --- | --- | --- |
| INV | 2026 | 00125 |

Giá trị sequence được trả về dưới dạng chuỗi, nhờ đó giữ được số 0 ở đầu. Nếu chuyển sang NUMBER, `00125` sẽ trở thành số 125 và mất cách biểu diễn ban đầu.

### 5.6. Dùng REGEXP_SUBSTR để tách token

Với chuỗi các từ cách nhau bởi một hoặc nhiều khoảng trắng:

```sql
SELECT REGEXP_SUBSTR(
         'Oracle   Database SQL',
         '[^[:space:]]+',
         1,
         2
       ) AS second_word
FROM dual;
```

Kết quả là `Database`.

Với dữ liệu phân tách bằng dấu phẩy:

```sql
SELECT REGEXP_SUBSTR(
         'A12,B34,C56',
         '[^,]+',
         1,
         LEVEL
       ) AS token
FROM dual
CONNECT BY REGEXP_SUBSTR(
             'A12,B34,C56',
             '[^,]+',
             1,
             LEVEL
           ) IS NOT NULL;
```

Ví dụ này minh họa cách sinh nhiều dòng từ các occurrence. Với bảng dữ liệu lớn, cần xem xét chi phí đánh giá lại biểu thức và chọn giải pháp tách chuỗi phù hợp với kiến trúc ứng dụng.

### 5.7. REGEXP_SUBSTR trả NULL trong những trường hợp nào?

Một số tình huống:

- Không có phần nào của source khớp pattern.
- Source là `NULL`.
- `position` bắt đầu sau phạm vi chuỗi có thể tìm.
- `occurrence` yêu cầu lớn hơn số lần xuất hiện thực tế.

Khi kết quả là `NULL`, không thể tự kết luận chuỗi nguồn ban đầu là NULL. Có thể source vẫn có dữ liệu nhưng pattern không khớp.

## 6. REGEXP_REPLACE: thay thế theo pattern

### 6.1. Cú pháp

```sql
REGEXP_REPLACE(
    source_char,
    pattern
    [, replace_string
       [, position
          [, occurrence
             [, match_param]
          ]
       ]
    ]
)
```

- `source_char`: chuỗi đầu vào.
- `pattern`: phần cần tìm.
- `replace_string`: chuỗi thay thế; có thể chứa backreference.
- `position`: vị trí bắt đầu tìm, mặc định 1.
- `occurrence`: lần khớp cần thay; **0 nghĩa là thay tất cả**, mặc định là 0.
- `match_param`: tham số so khớp như `i`, `c`, `n`, `m`, `x`.

Nếu không tìm thấy match, hàm trả lại chuỗi nguồn theo kết quả tương ứng; không có nghĩa toàn bộ source bị xóa.

### 6.2. Chuẩn hóa nhiều khoảng trắng

```sql
SELECT REGEXP_REPLACE(
         'Oracle     Database   SQL',
         '[[:space:]]+',
         ' '
       ) AS normalized_text
FROM dual;
```

Kết quả:

```text
Oracle Database SQL
```

Nếu muốn loại cả khoảng trắng đầu/cuối, kết hợp `TRIM`:

```sql
SELECT TRIM(
         REGEXP_REPLACE(
           '   Oracle     Database   SQL   ',
           '[[:space:]]+',
           ' '
         )
       ) AS normalized_text
FROM dual;
```

`TRIM` loại khoảng trắng ở hai đầu sau khi regex gom các chuỗi khoảng trắng liên tiếp thành một dấu cách.

### 6.3. Loại bỏ ký tự không phải chữ số

Ví dụ chuẩn hóa số điện thoại về chuỗi chỉ còn chữ số:

```sql
SELECT REGEXP_REPLACE(
         '+84 (912) 345-678',
         '[^[:digit:]]',
         ''
       ) AS digits_only
FROM dual;
```

Kết quả minh họa là `84912345678`.

Đây chỉ là bước **chuẩn hóa ký tự**, chưa chứng minh số điện thoại hợp lệ, có mã quốc gia đúng hoặc đang hoạt động. Việc xác thực số điện thoại cần quy tắc riêng theo quốc gia và nghiệp vụ.

### 6.4. Chỉ thay lần xuất hiện thứ n

Với `occurrence` bằng 0, Oracle thay tất cả match:

```sql
SELECT REGEXP_REPLACE(
         'a1 b2 c3',
         '[[:digit:]]',
         '#'
       ) AS replace_all
FROM dual;
```

Kết quả `a# b# c#`.

Chỉ thay occurrence thứ hai:

```sql
SELECT REGEXP_REPLACE(
         'a1 b2 c3',
         '[[:digit:]]',
         '#',
         1,
         2
       ) AS replace_second
FROM dual;
```

Kết quả `a1 b# c3`. Các chữ số khác được giữ nguyên.

### 6.5. Dùng capture group để đổi thứ tự thành phần

Giả sử tên được lưu theo dạng `Smith, John` và muốn chuyển thành `John Smith`:

```sql
SELECT REGEXP_REPLACE(
         'Smith, John',
         '^([^,]+),[[:space:]]*(.+)$',
         '\2 \1'
       ) AS display_name
FROM dual;
```

Pattern có:

- `([^,]+)`: nhóm 1, mọi ký tự trước dấu phẩy.
- `,`: dấu phẩy literal.
- `[[:space:]]*`: 0 hoặc nhiều khoảng trắng.
- `(.+)`: nhóm 2, phần tên còn lại.
- `'\2 \1'`: thay bằng nhóm 2, một dấu cách, rồi nhóm 1.

Kết quả `John Smith`.

Backreference trong chuỗi thay thế của Oracle dùng dạng `\1` đến `\9` cho các nhóm bắt giữ tương ứng. Đừng tự động dùng cú pháp `$1` từ một số regex engine khác.

### 6.6. Che một phần chuỗi

Ví dụ che các ký tự đầu của mã thẻ, giữ lại bốn ký tự cuối:

```sql
SELECT REGEXP_REPLACE(
         '1234567890123456',
         '^([[:digit:]]{12})([[:digit:]]{4})$',
         '************\2'
       ) AS masked_value
FROM dual;
```

Kết quả:

```text
************3456
```

Đây chỉ là minh họa biến đổi chuỗi. Che dữ liệu ở kết quả truy vấn không thay thế chính sách bảo vệ dữ liệu, quyền truy cập, mã hóa, audit hoặc kiểm soát việc lưu trữ bản gốc.

### 6.7. Xóa toàn bộ phần khớp

Nếu `replace_string` là chuỗi rỗng theo ngữ nghĩa Oracle, các phần khớp có thể bị loại bỏ. Ví dụ:

```sql
SELECT REGEXP_REPLACE(
         'INV-2026-00125',
         '[^[:alnum:]-]',
         ''
       ) AS cleaned_code
FROM dual;
```

Ở đây replacement rỗng được dùng để bỏ các ký tự không thuộc chữ/số/dấu gạch ngang. Oracle xem chuỗi rỗng thông thường `''` là `NULL`, nên cần hiểu đúng ngữ nghĩa chuỗi rỗng của Oracle khi thiết kế biểu thức.

## 7. Capture groups và backreferences

### 7.1. Capture group là gì?

Nhóm bắt giữ là phần pattern được đặt trong cặp ngoặc tròn `(...)`. Oracle có thể dùng nhóm này để:

- Trả riêng một phần qua tham số `subexpr` của `REGEXP_SUBSTR`.
- Tham chiếu lại nội dung nhóm trong chuỗi thay thế của `REGEXP_REPLACE`.

Ví dụ pattern:

```text
^([[:alpha:]]{3})-([[:digit:]]{4})$
```

Có hai nhóm:

| Nhóm | Nội dung |
| ---: | --- |
| 1 | Ba chữ cái đầu |
| 2 | Bốn chữ số cuối |

### 7.2. Trích nhóm và thay nhóm

```sql
SELECT
    REGEXP_SUBSTR('ABC-1234',
                  '^([[:alpha:]]{3})-([[:digit:]]{4})$',
                  1, 1, 'c', 1) AS prefix,
    REGEXP_SUBSTR('ABC-1234',
                  '^([[:alpha:]]{3})-([[:digit:]]{4})$',
                  1, 1, 'c', 2) AS sequence_no,
    REGEXP_REPLACE('ABC-1234',
                   '^([[:alpha:]]{3})-([[:digit:]]{4})$',
                   '\2/\1') AS rearranged
FROM dual;
```

Kết quả:

| PREFIX | SEQUENCE_NO | REARRANGED |
| --- | --- | --- |
| ABC | 1234 | 1234/ABC |

### 7.3. Giới hạn nhóm

`REGEXP_SUBSTR` có tham số `subexpr` từ 0 đến 9; 0 trả toàn bộ match và các số dương chọn nhóm bắt giữ tương ứng. Khi thiết kế pattern dùng nhiều nhóm, hãy đánh số và ghi chú rõ. Chuỗi thay thế `REGEXP_REPLACE` hỗ trợ backreference theo giới hạn Oracle quy định, thông dụng là `\1` đến `\9`.

Đừng tạo pattern có quá nhiều nhóm không cần thiết. Nhóm lồng nhau có thể khiến việc đếm thứ tự trở nên khó hiểu và làm tăng chi phí bảo trì.

## 8. Các ví dụ thực tế theo bài toán dữ liệu

### 8.1. Kiểm tra mã nhân viên

Yêu cầu: mã nhân viên có tiền tố `EMP-`, theo sau bởi sáu chữ số:

```sql
SELECT employee_id, employee_code
FROM   employees
WHERE  REGEXP_LIKE(
         employee_code,
         '^EMP-[[:digit:]]{6}$'
       );
```

Regex kiểm tra cấu trúc chuỗi, nhưng không xác nhận mã có tồn tại trong hệ thống nhân sự hoặc được cấp cho nhân viên đang hoạt động.

### 8.2. Tách mã đơn hàng thành loại và số

Dữ liệu ví dụ: `SO-2026-000123`.

```sql
SELECT
    REGEXP_SUBSTR(order_code,
                  '^([[:alpha:]]+)-([[:digit:]]{4})-([[:digit:]]+)$',
                  1, 1, 'i', 1) AS order_type,
    REGEXP_SUBSTR(order_code,
                  '^([[:alpha:]]+)-([[:digit:]]{4})-([[:digit:]]+)$',
                  1, 1, 'i', 2) AS order_year,
    REGEXP_SUBSTR(order_code,
                  '^([[:alpha:]]+)-([[:digit:]]{4})-([[:digit:]]+)$',
                  1, 1, 'i', 3) AS order_sequence
FROM   sales_orders;
```

Việc giữ sequence ở dạng chuỗi giúp bảo toàn số 0 đầu. Nếu cần tính toán số học, chuyển đổi riêng và chỉ khi dữ liệu đảm bảo hợp lệ.

### 8.3. Chuẩn hóa khoảng trắng trong tên

```sql
SELECT customer_id,
       TRIM(
         REGEXP_REPLACE(
           customer_name,
           '[[:space:]]+',
           ' '
         )
       ) AS normalized_name
FROM   customers;
```

Đây là biểu thức đọc dữ liệu. Nếu cần cập nhật dữ liệu thật, nên xem trước kết quả, sao lưu hoặc có transaction/quy trình kiểm soát thích hợp rồi mới chạy `UPDATE`.

### 8.4. Phát hiện chuỗi có ký tự ngoài tập cho phép

Ví dụ mã chỉ cho phép chữ cái, chữ số và dấu gạch ngang:

```sql
SELECT product_code
FROM   products
WHERE  REGEXP_LIKE(product_code, '[^[:alnum:]-]');
```

Mẫu phủ định trong bracket expression tìm **ít nhất một ký tự không thuộc tập cho phép**. Có thể dùng nó để tìm dữ liệu nghi vấn trước khi chuẩn hóa.

Muốn kiểm tra cả chuỗi chỉ gồm ký tự được phép, dùng anchor và dấu cộng:

```sql
WHERE REGEXP_LIKE(product_code, '^[[:alnum:]-]+$')
```

Cần xác định rõ có cho phép chuỗi rỗng hay không. Với pattern dùng `+`, ít nhất một ký tự phải khớp; nếu muốn cho phép rỗng, quantifier `*` có ý nghĩa khác.

### 8.5. Tìm dòng log chứa ERROR hoặc FATAL

```sql
SELECT log_id, log_message
FROM   application_logs
WHERE  REGEXP_LIKE(
         log_message,
         '(^|[[:space:]])(ERROR|FATAL)(:|[[:space:]])',
         'i'
       );
```

Mẫu này tìm các từ trạng thái trong ngữ cảnh khoảng trắng/dấu phân cách nhất định. Nó hữu ích hơn tìm chuỗi `'%ERROR%'` nếu không muốn khớp một từ dài vô tình chứa chữ ERROR. Quy tắc thực tế phải phù hợp định dạng log của ứng dụng.

### 8.6. Chuẩn hóa dấu phân cách

Giả sử dữ liệu có thể dùng dấu chấm phẩy, dấu phẩy hoặc nhiều khoảng trắng để phân cách:

```sql
SELECT REGEXP_REPLACE(
         'A12;   B34, C56',
         '[;,][[:space:]]*',
         ','
       ) AS normalized_list
FROM dual;
```

Kết quả `A12, B34, C56`. Ví dụ này chỉ chuẩn hóa chuỗi; nó không phải parser CSV đầy đủ. CSV thực tế có thể cho phép dấu phẩy bên trong trường được quote, escape quote và newline trong field, nên cần parser CSV đúng chuẩn thay vì regex đơn giản.

## 9. Giới hạn kỹ thuật của Oracle regular expressions

### 9.1. Pattern tối đa 512 byte

Oracle giới hạn **regular expression pattern tối đa 512 byte**. Đây là giới hạn theo byte, không nhất thiết bằng 512 ký tự, đặc biệt với pattern chứa ký tự đa byte.

Hệ quả:

- Pattern rất dài có thể bị từ chối dù số ký tự nhìn thấy không quá lớn.
- Pattern sinh động từ cấu hình hoặc người dùng cần được giới hạn kích thước.
- Một regex khổng lồ thường là dấu hiệu nên chia logic, dùng bảng cấu hình hoặc chuyển phần xử lý sang tầng phù hợp hơn.

Đừng cố nhồi toàn bộ từ điển nghiệp vụ, danh sách mã hoặc hàng trăm lựa chọn vào một pattern. Với danh sách giá trị, dùng `IN` hoặc bảng tham chiếu; với quy tắc lớn, cân nhắc mô hình dữ liệu riêng.

### 9.2. Không phải toàn bộ PCRE, Java Pattern hay JavaScript RegExp

Oracle triển khai regex theo chuẩn POSIX và hướng dẫn Unicode, có một số phần mở rộng. Nó không đồng nghĩa với toàn bộ engine PCRE hoặc engine regex của Java.

Không nên sao chép nguyên xi những cú pháp nâng cao như lookaround, named capture group, inline flag hoặc cú pháp riêng của engine khác mà không xác nhận Oracle phiên bản mục tiêu hỗ trợ. Với Oracle, tham số `match_param` là cách tiêu chuẩn để điều khiển một số chế độ như `i`, `c`, `n`, `m`, `x`.

Nếu cần một pattern có tính di động giữa nhiều engine, hãy giữ trong tập cú pháp chung, kiểm thử trên đúng Oracle Database release và đối chiếu tài liệu chính thức.

### 9.3. Giới hạn về nhóm bắt giữ

`REGEXP_SUBSTR` cho phép chọn `subexpr` trong phạm vi 0–9; backreference trong replacement của `REGEXP_REPLACE` cũng có giới hạn theo các nhóm được Oracle hỗ trợ. Không nên thiết kế regex với hàng chục nhóm rồi kỳ vọng trích xuất/thay thế tùy ý.

Nếu cần parse cấu trúc phức tạp với nhiều trường, có thể:

- Dùng nhiều biểu thức nhỏ, dễ kiểm tra.
- Dùng `JSON_VALUE`/`JSON_TABLE` nếu nguồn là JSON.
- Dùng `XMLTABLE` nếu nguồn là XML.
- Dùng parser chuyên dụng ở tầng ứng dụng nếu dữ liệu có grammar phức tạp.

### 9.4. Regex không thay thế parser định dạng

Một regex có thể kiểm tra hình thức `2026-02-31` theo mẫu `YYYY-MM-DD` nhưng ngày này **không tồn tại** trong lịch Gregorian. Regex nhận diện chuỗi có cấu trúc; việc chuyển sang DATE/TIMESTAMP cần xác minh giá trị lịch thực.

Tương tự:

- Regex email không chứng minh hộp thư tồn tại.
- Regex số điện thoại không chứng minh số đang hoạt động.
- Regex JSON thô không thay thế parser JSON.
- Regex CSV không xử lý đầy đủ quoted field và newline.
- Regex XML không thay thế parser XML.

Hãy dùng đúng công cụ cho ngữ nghĩa dữ liệu.

### 9.5. Character set, Unicode và collation

Các biểu thức như `[[:alpha:]]`, `[[:digit:]]` và các phép so khớp không phân biệt hoa–thường cần được hiểu trong bối cảnh character set, collation và các quy tắc Unicode của Oracle. Một pattern được kiểm thử với dữ liệu ASCII có thể không phản ánh đúng kết quả trên tiếng Việt có dấu, ký tự kết hợp hoặc supplementary characters.

Với dữ liệu đa ngôn ngữ:

- Xác định chuẩn hóa Unicode của dữ liệu nguồn.
- Kiểm thử chữ hoa–thường và dấu tiếng Việt.
- Không dùng dải ASCII `A-Z` như đại diện cho mọi chữ cái.
- Đọc tài liệu về collation và regular expression của đúng release.

## 10. NULL và kiểu dữ liệu nguồn

### 10.1. REGEXP_LIKE với NULL

Nếu `source_char` là `NULL`, điều kiện regex không trở thành TRUE. Trong `WHERE`, dòng có source NULL không được chọn:

```sql
SELECT customer_id, email
FROM   customers
WHERE  REGEXP_LIKE(email, '^[^@]+@[^@]+$');
```

Nếu muốn phân loại riêng email chưa có:

```sql
SELECT customer_id,
       CASE
         WHEN email IS NULL THEN 'MISSING'
         WHEN REGEXP_LIKE(email, '^[^@]+@[^@]+$') THEN 'SHAPE_OK'
         ELSE 'INVALID_SHAPE'
       END AS email_status
FROM customers;
```

`SHAPE_OK` chỉ nói chuỗi phù hợp mẫu đơn giản, không phải email đã được xác minh.

### 10.2. REGEXP_SUBSTR không tìm thấy match

```sql
SELECT REGEXP_SUBSTR(
         'ABC-123',
         '[[:alpha:]]{4}'
       ) AS extracted_value
FROM dual;
```

Kết quả là `NULL` vì không có đoạn gồm bốn chữ cái liên tiếp theo pattern. Phải phân biệt trường hợp này với source vốn là NULL nếu cần thống kê chất lượng dữ liệu.

### 10.3. REGEXP_REPLACE và NULL

Nếu source là NULL, kết quả thường vẫn là NULL theo ngữ nghĩa SQL. Không nên dùng regex để thay thế cơ chế xử lý NULL; hãy viết `CASE`, `NVL` hoặc `COALESCE` khi nghiệp vụ cần giá trị mặc định.

Oracle xử lý chuỗi rỗng `''` của kiểu ký tự như `NULL` trong SQL. Vì vậy, kiểm tra chuỗi rỗng và NULL thường cần được thiết kế theo cùng chính sách dữ liệu.

### 10.4. Dùng với CLOB và dữ liệu dài

Các regex functions có thể làm việc với những kiểu ký tự được Oracle hỗ trợ, bao gồm một số kiểu LOB. Tuy nhiên, kiểu trả về, giới hạn pattern, chuyển đổi character set và chi phí xử lý cần xem theo chữ ký hàm của phiên bản đang dùng. Không mặc định rằng pattern 512 byte có nghĩa source cũng chỉ được dài 512 byte; giới hạn pattern và độ dài source là hai vấn đề khác nhau.

Với CLOB rất lớn, chạy regex trên toàn bộ nội dung có thể tốn CPU và I/O. Nếu chỉ cần tìm một đoạn ngắn, cân nhắc vị trí/độ dài phù hợp, chia xử lý hoặc dùng công cụ tìm kiếm văn bản phù hợp.

## 11. Hiệu năng và cách sử dụng có trách nhiệm

### 11.1. Regex thường tốn chi phí hơn điều kiện đơn giản

So sánh:

```sql
WHERE status = 'ACTIVE'
```

với:

```sql
WHERE REGEXP_LIKE(status, '^ACTIVE$')
```

Hai điều kiện có thể biểu diễn cùng ý định trong dữ liệu đơn giản, nhưng regex thêm công việc phân tích và so khớp pattern. Hãy dùng phép bằng khi yêu cầu chỉ là bằng chính xác.

Tương tự:

```sql
WHERE product_code LIKE 'ABC%'
```

thường là lựa chọn dễ tối ưu hơn so với regex tương đương:

```sql
WHERE REGEXP_LIKE(product_code, '^ABC')
```

Đừng giả định Oracle sẽ biến mọi regex thành phép range scan giống LIKE.

### 11.2. Tránh pattern quá rộng

Pattern không có anchor hoặc bắt đầu bằng wildcard có thể phải kiểm tra nhiều vị trí trong chuỗi. Ví dụ `.*ERROR.*` có thể viết đơn giản hơn bằng `REGEXP_LIKE(message, 'ERROR')` vì regex không bắt buộc phải khớp toàn chuỗi.

Pattern dài với nhiều nhánh lồng nhau, quantifier và backtracking có thể làm tăng chi phí. Hãy viết pattern theo cấu trúc dữ liệu thực tế và đo với số dòng, độ dài chuỗi và concurrency tương tự production.

### 11.3. Không chạy REGEXP_REPLACE trên toàn bảng để xem thử

Một câu:

```sql
UPDATE customer_data
SET    phone = REGEXP_REPLACE(phone, '[^[:digit:]]', '');
```

có thể sửa hàng loạt dữ liệu. Trước khi thực hiện:

1. Dùng `SELECT` để xem giá trị trước/sau.
2. Đếm số dòng bị ảnh hưởng.
3. Kiểm tra trường hợp NULL, chuỗi rỗng, dữ liệu Unicode và giá trị đặc biệt.
4. Xác nhận chính sách nghiệp vụ về định dạng.
5. Thực hiện theo quy trình transaction/backup/deployment của môi trường.
6. Kiểm tra kết quả sau khi cập nhật.

Ví dụ xem trước:

```sql
SELECT customer_id,
       phone AS original_phone,
       REGEXP_REPLACE(phone, '[^[:digit:]]', '') AS normalized_phone
FROM   customer_data
WHERE  phone IS NOT NULL;
```

Không dùng `COMMIT` tự động trong script biến đổi trước khi có bước xác nhận phù hợp.

### 11.4. Đọc execution plan và đo thực tế

Có thể xem kế hoạch ước lượng:

```sql
EXPLAIN PLAN FOR
SELECT customer_id
FROM   customers
WHERE  REGEXP_LIKE(email, '@example\.com$');

SELECT *
FROM TABLE(DBMS_XPLAN.DISPLAY);
```

`EXPLAIN PLAN` chỉ cho biết kế hoạch ước lượng. Khi điều tra truy vấn đã chạy, cần xem cursor plan và số liệu runtime phù hợp, đồng thời đối chiếu thống kê, số dòng thực tế, CPU và wait events.

Không có kết luận chung rằng regex luôn chậm hoặc luôn không dùng index. Cần đánh giá câu SQL, dữ liệu, index, optimizer và phiên bản Oracle cụ thể.

### 11.5. Cân nhắc giải pháp khác

| Bài toán | Giải pháp nên cân nhắc |
| --- | --- |
| Bằng hoặc khác một giá trị | `=`, `<>` |
| Tiền tố đơn giản | `LIKE 'ABC%'` |
| Tập giá trị lớn | Bảng tham chiếu, staging table, join |
| Tách dữ liệu CSV thật | Parser CSV chuyên dụng |
| Đọc JSON | `JSON_VALUE`, `JSON_TABLE` |
| Đọc XML | `XMLTABLE` |
| Tìm kiếm văn bản toàn văn | Oracle Text hoặc giải pháp search phù hợp |
| Kiểm tra ngày tháng thực | `TO_DATE`/`TO_TIMESTAMP` với format rõ và xử lý lỗi |
| Quy tắc nghiệp vụ phức tạp | Validation ở tầng nghiệp vụ kết hợp constraint cần thiết |

## 12. Bảo mật khi pattern đến từ người dùng

### 12.1. Bind variable ngăn SQL injection nhưng không biến pattern thành literal

Ví dụ:

```sql
SELECT customer_id, email
FROM   customers
WHERE  REGEXP_LIKE(email, :pattern);
```

Bind variable giúp truyền pattern như dữ liệu, giảm nguy cơ người dùng chèn cú pháp SQL vào câu lệnh. Tuy nhiên, giá trị `:pattern` vẫn được Oracle diễn giải như **regex pattern**. Người dùng có thể chủ động cung cấp pattern rất rộng hoặc phức tạp, làm truy vấn tốn tài nguyên hoặc tìm được dữ liệu rộng hơn dự định.

Nếu chức năng chỉ cho phép tìm một chuỗi literal, cần escape các metacharacters regex trước khi đặt vào pattern. Bind và escape giải quyết hai vấn đề khác nhau.

### 12.2. Giới hạn pattern động

Nếu cho người dùng nhập regex:

- Giới hạn độ dài pattern.
- Xác định tập cú pháp được phép.
- Không cho phép mọi người dùng truy vấn nguồn dữ liệu không được phép.
- Đặt giới hạn thời gian/tài nguyên ở tầng ứng dụng và database theo chính sách.
- Kiểm thử pattern với dữ liệu dài và nhiều dòng.
- Ghi nhận lỗi pattern không hợp lệ theo cách không làm lộ thông tin nhạy cảm.

Giới hạn 512 byte của Oracle là giới hạn kỹ thuật, **không phải mức đầu vào an toàn mặc định**. Một pattern ngắn vẫn có thể tốn tài nguyên tùy nội dung và dữ liệu được so khớp.

### 12.3. Không xem regex validation là ranh giới bảo mật

Ví dụ kiểm tra mã:

```sql
CHECK (REGEXP_LIKE(account_code, '^[[:alnum:]-]+$'))
```

có thể bảo đảm hình thức ký tự của cột, nhưng không thay thế kiểm tra quyền truy cập, xác thực danh tính, chống SQL injection, phân quyền theo hàng hoặc kiểm soát dữ liệu nhạy cảm.

Đối với dữ liệu quan trọng, kết hợp kiểm tra đầu vào với constraint, quyền database và logic nghiệp vụ ở đúng tầng.

## 13. Lỗi thường gặp và cách xử lý

| Dấu hiệu | Nguyên nhân có thể | Hướng kiểm tra |
| --- | --- | --- |
| Pattern không khớp dù chuỗi có vẻ đúng | Thiếu/nhầm anchor, escape sai, hoa–thường, ký tự ẩn | Xem dữ liệu thô, pattern, match_param |
| REGEXP_LIKE trả quá nhiều dòng | Pattern không có anchor hoặc quantifier quá rộng | Xác định cần match substring hay toàn chuỗi |
| REGEXP_SUBSTR trả NULL | Không có occurrence tương ứng hoặc source NULL | Kiểm tra số lần khớp, position, occurrence |
| REGEXP_SUBSTR lấy cả đoạn dài | Dùng `.*` greedy quá rộng | Giới hạn lớp ký tự, anchor hoặc cấu trúc nhóm |
| REGEXP_REPLACE thay mọi lần | `occurrence=0` hoặc mặc định | Truyền occurrence dương nếu chỉ muốn thay lần cụ thể |
| Nhóm trích xuất sai | Đếm nhầm capture group | Đánh số `(...)` từ trái sang phải, kiểm tra subexpr |
| Dấu chấm không khớp newline | Chưa dùng match parameter `n` | Thêm `'n'` khi yêu cầu cho phép |
| Anchor không nhận từng dòng | Chưa bật multiline mode | Dùng `'m'` |
| Pattern quá dài | Vượt giới hạn 512 byte | Rút gọn hoặc chia logic |
| Regex chạy chậm | Pattern rộng/phức tạp, source lớn, nhiều dòng | Đo plan/runtime; cân nhắc LIKE, index hoặc parser khác |
| Lỗi khi sao chép regex từ Java | Khác engine và escaping | Kiểm tra cú pháp Oracle, SQL literal và lớp chuỗi trung gian |
| Chữ tiếng Việt khớp không như mong đợi | Character set, Unicode, collation, normalization | Kiểm thử dữ liệu thực và quy tắc ngôn ngữ |

### 13.1. Kiểm tra pattern từng phần

Thay vì viết một regex dài ngay từ đầu, thử từng đoạn:

```sql
SELECT
    CASE WHEN REGEXP_LIKE('INV-2026-00125', '^INV-')
         THEN 'Y' ELSE 'N' END AS prefix_ok,
    CASE WHEN REGEXP_LIKE('INV-2026-00125', '[[:digit:]]{4}')
         THEN 'Y' ELSE 'N' END AS year_present,
    CASE WHEN REGEXP_LIKE('INV-2026-00125',
                          '^INV-[[:digit:]]{4}-[[:digit:]]+$')
         THEN 'Y' ELSE 'N' END AS full_pattern_ok
FROM dual;
```

Cách này giúp xác định pattern sai ở đâu. Với dữ liệu nhiều định dạng, lưu test cases cho cả giá trị hợp lệ, không hợp lệ, NULL, chuỗi rỗng, ký tự Unicode và độ dài biên.

### 13.2. Kiểm tra pattern không hợp lệ

Pattern sai cú pháp có thể gây lỗi regex trong lúc thực thi. Khi pattern được xây dựng động, cần xác nhận đầu vào theo chính sách trước khi chạy truy vấn trên khối lượng dữ liệu lớn.

Không nên bắt mọi lỗi rồi trả về “không tìm thấy” mà không ghi nhận nguyên nhân; lỗi cú pháp pattern khác với kết quả hợp lệ không có match.

## 14. Bài thực hành tổng hợp

Các ví dụ sau dùng literal và dữ liệu giả lập, không thay đổi bảng nghiệp vụ.

### Bài 1 — REGEXP_LIKE kiểm tra mã

```sql
SELECT CASE
         WHEN REGEXP_LIKE('EMP-123456',
                          '^EMP-[[:digit:]]{6}$')
         THEN 'VALID SHAPE'
         ELSE 'INVALID SHAPE'
       END AS result
FROM dual;
```

**Kỳ vọng:** `VALID SHAPE`.

Thử thay chuỗi thành `EMP-12345X` và `XEMP-123456` để quan sát tác dụng của lớp chữ số và anchor.

### Bài 2 — REGEXP_LIKE không phân biệt hoa–thường

```sql
SELECT CASE
         WHEN REGEXP_LIKE('Oracle Database',
                          '^ORACLE',
                          'i')
         THEN 'MATCH'
         ELSE 'NO MATCH'
       END AS result
FROM dual;
```

**Kỳ vọng:** `MATCH`.

### Bài 3 — REGEXP_SUBSTR lấy token thứ hai

```sql
SELECT REGEXP_SUBSTR(
         'alpha,beta,gamma',
         '[^,]+',
         1,
         2
       ) AS token
FROM dual;
```

**Kỳ vọng:** `beta`.

### Bài 4 — REGEXP_SUBSTR lấy capture group

```sql
SELECT REGEXP_SUBSTR(
         'INV-2026-00125',
         '^(INV)-([[:digit:]]{4})-([[:digit:]]+)$',
         1, 1, 'c', 3
       ) AS sequence_no
FROM dual;
```

**Kỳ vọng:** `00125`, được giữ dưới dạng chuỗi.

### Bài 5 — REGEXP_REPLACE gom khoảng trắng

```sql
SELECT TRIM(
         REGEXP_REPLACE(
           '  Oracle     SQL   Regex  ',
           '[[:space:]]+',
           ' '
         )
       ) AS cleaned_text
FROM dual;
```

**Kỳ vọng:** `Oracle SQL Regex`.

### Bài 6 — REGEXP_REPLACE chỉ thay lần thứ hai

```sql
SELECT REGEXP_REPLACE(
         'a1 b2 c3',
         '[[:digit:]]',
         '#',
         1,
         2
       ) AS result
FROM dual;
```

**Kỳ vọng:** `a1 b# c3`.

### Bài 7 — Dùng backreference đổi thứ tự

```sql
SELECT REGEXP_REPLACE(
         'Nguyen, An',
         '^([^,]+),[[:space:]]*(.+)$',
         '\2 \1'
       ) AS full_name
FROM dual;
```

**Kỳ vọng:** `An Nguyen`.

### Bài 8 — Dấu chấm và newline

```sql
SELECT
    CASE WHEN REGEXP_LIKE(
                    'line1' || CHR(10) || 'line2',
                    'line1.*line2'
                  )
         THEN 'MATCH' ELSE 'NO MATCH' END AS default_mode,
    CASE WHEN REGEXP_LIKE(
                    'line1' || CHR(10) || 'line2',
                    'line1.*line2',
                    'n'
                  )
         THEN 'MATCH' ELSE 'NO MATCH' END AS dot_matches_newline
FROM dual;
```

**Kỳ vọng:** mặc định không khớp theo cách dùng dấu chấm qua newline; chế độ `n` cho phép khớp.

### Bài 9 — Kiểm tra ký tự ngoài tập cho phép

```sql
SELECT CASE
         WHEN REGEXP_LIKE('AB-1234', '^[[:alnum:]-]+$')
         THEN 'ONLY_ALLOWED_CHARS'
         ELSE 'HAS_OTHER_CHAR'
       END AS result
FROM dual;
```

**Kỳ vọng:** `ONLY_ALLOWED_CHARS`.

### Bài 10 — Thử giới hạn pattern

Tạo một pattern dài có chủ đích trong môi trường thử nghiệm và quan sát giới hạn 512 byte. Không cần thực hiện trên production; mục tiêu là hiểu rằng giới hạn tính theo byte và pattern đa byte có thể đạt ngưỡng sớm hơn số ký tự nhìn thấy.

## 15. Checklist trước khi đưa regex vào hệ thống

| Câu hỏi | Việc cần xác nhận |
| --- | --- |
| Có thực sự cần regex? | Nếu chỉ cần bằng, tiền tố hoặc khoảng đơn giản, dùng toán tử cơ bản |
| Match một phần hay toàn bộ? | Chọn có/không có `^` và `$` |
| Hoa–thường có quan trọng? | Xác định `i` hoặc `c` và collation |
| Chuỗi có newline? | Xác định `n` và `m` |
| Có cần trích xuất nhóm? | Đánh số capture groups, kiểm tra `subexpr` |
| Thay một hay mọi occurrence? | Chọn `occurrence` rõ ràng cho `REGEXP_REPLACE` |
| Có dữ liệu NULL? | Xử lý riêng `NULL` và kết quả không tìm thấy |
| Có Unicode/tiếng Việt? | Kiểm thử character set, normalization, collation |
| Pattern có quá dài? | Giữ dưới giới hạn 512 byte |
| Pattern do user nhập? | Bind, giới hạn cú pháp/độ dài, escape khi cần literal |
| Có thể dùng LIKE hoặc parser chuyên dụng? | Chọn công cụ phù hợp dữ liệu |
| Đã đo hiệu năng? | Kiểm tra execution plan và runtime với dữ liệu đại diện |

## 16. Câu hỏi tự kiểm tra

1. `REGEXP_LIKE` trả về chuỗi hay là một điều kiện SQL?
2. Pattern `'ABC'` có bắt buộc toàn bộ chuỗi bằng ABC không? Muốn bắt buộc toàn chuỗi cần thêm gì?
3. Trong regex Oracle, ký hiệu nào biểu diễn một ký tự bất kỳ? Ký hiệu nào biểu diễn 0 hoặc nhiều ký tự?
4. Vì sao `LIKE 'A%'` và `REGEXP_LIKE(col, 'A%')` không tương đương?
5. Tham số `'i'` và `'c'` khác nhau thế nào?
6. Khi nào cần `'n'` và khi nào cần `'m'`?
7. Trong `REGEXP_SUBSTR`, `occurrence=3` có ý nghĩa gì?
8. Tham số `subexpr=0` trả về gì? `subexpr=2` trả về gì?
9. Trong `REGEXP_REPLACE`, `occurrence=0` có nghĩa gì?
10. Backreference trong replacement của Oracle thường viết `\1` hay `$1`?
11. Pattern tối đa bao nhiêu byte theo giới hạn Oracle thường gặp?
12. Regex kiểm tra `2026-02-31` có thể nhận chuỗi đúng hình thức không? Vì sao nó chưa đủ xác nhận ngày hợp lệ?
13. Bind variable có biến pattern do người dùng nhập thành literal text không?
14. Khi chỉ cần tìm tiền tố `ABC`, vì sao `LIKE 'ABC%'` thường đáng cân nhắc hơn regex?
15. Tại sao không nên dùng regex đơn giản để parse mọi file CSV hoặc xác thực email đầy đủ?

**Gợi ý đáp án:**

1. Là điều kiện SQL, thường dùng trong `WHERE`.
2. Không; không có anchor thì có thể khớp một phần. Dùng `^ABC$`.
3. `.` là một ký tự; `.*` là không hoặc nhiều ký tự.
4. Trong LIKE, `%` là wildcard; trong regex, `%` là ký tự phần trăm literal.
5. `i` không phân biệt hoa–thường; `c` phân biệt.
6. `n` cho dấu chấm khớp newline; `m` làm anchor hoạt động theo từng dòng.
7. Lấy phần khớp thứ ba.
8. 0 trả toàn bộ match; 2 trả nhóm bắt giữ thứ hai.
9. Thay tất cả occurrence.
10. `\1` đến `\9` theo cú pháp Oracle.
11. 512 byte.
12. Có thể đúng hình thức regex nhưng ngày không tồn tại theo lịch; cần chuyển đổi/kiểm tra ngày thực.
13. Không; bind ngăn trộn vào SQL syntax nhưng pattern vẫn được diễn giải như regex. Muốn tìm literal cần escape metacharacters.
14. LIKE đơn giản, dễ hiểu và thường có cơ hội dùng đường truy cập index phù hợp hơn.
15. CSV và email có grammar/quy tắc nghiệp vụ rộng hơn một pattern đơn giản; parser hoặc validation chuyên dụng phù hợp hơn.

## 17. Tài liệu Oracle tham khảo

- [Oracle Database SQL Language Reference — Regular Expression Support](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/Regular-Expression-Support.html): nền tảng POSIX, Unicode và các quy tắc regex của Oracle.
- [Oracle Database SQL Language Reference — REGEXP_LIKE](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/REGEXP_LIKE.html): cú pháp điều kiện và tham số so khớp.
- [Oracle Database SQL Language Reference — REGEXP_SUBSTR](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/REGEXP_SUBSTR.html): vị trí, occurrence và capture group.
- [Oracle Database SQL Language Reference — REGEXP_REPLACE](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/REGEXP_REPLACE.html): thay thế theo pattern và backreference.
- [Oracle Database Globalization Support Guide](https://docs.oracle.com/en/database/oracle/oracle-database/19/nlspg/): Unicode, character set và các quy tắc ngôn ngữ.
- [Oracle Database SQL Tuning Guide](https://docs.oracle.com/en/database/oracle/oracle-database/19/tgsql/): đánh giá kế hoạch thực thi và hiệu năng câu SQL.

Khi sử dụng regex trong Oracle, hãy xác định rõ **mục tiêu là kiểm tra, trích xuất hay thay thế**; viết pattern có anchor khi cần kiểm tra toàn chuỗi; chọn tham số match phù hợp; quản lý capture group; và nhớ giới hạn 512 byte. Dùng regex cho dữ liệu thực sự cần so khớp mẫu, còn các phép lọc đơn giản nên giữ bằng toán tử SQL cơ bản để câu lệnh dễ đọc, dễ tối ưu và dễ bảo trì.
