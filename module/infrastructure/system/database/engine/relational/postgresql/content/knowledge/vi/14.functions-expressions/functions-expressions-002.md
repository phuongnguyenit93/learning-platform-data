# Hàm chuỗi, nối chuỗi và xử lý khoảng trắng trong PostgreSQL

Dữ liệu chuỗi có mặt trong gần như mọi ứng dụng: tên khách hàng, email, số điện thoại, địa chỉ, mã hàng, ghi chú, nhãn hiển thị và nội dung báo cáo. Tuy nhiên, dữ liệu thực tế thường không sạch như ví dụ trong giáo trình. Một tên có thể chứa khoảng trắng đầu/cuối, một email có chữ hoa và dấu cách, một trường có thể là `NULL` thay vì chuỗi rỗng, và một chuỗi tiếng Việt có thể chiếm nhiều byte hơn số ký tự người dùng nhìn thấy.

PostgreSQL có nhiều toán tử và hàm làm việc với chuỗi: **`||`**, **`concat()`**, **`concat_ws()`**, **`trim()`**, **`btrim()`**, **`ltrim()`**, **`rtrim()`**, **`length()`**, **`lower()`**, **`upper()`**, **`substring()`**, **`replace()`**, **`regexp_replace()`**, **`string_agg()`** và nhiều công cụ khác.

Bài thuộc chương **Hàm và biểu thức** của module PostgreSQL. Chúng ta sẽ học cách phối hợp các hàm đó để tạo chuỗi hiển thị, chuẩn hóa dữ liệu, phát hiện khoảng trắng bất thường, tách/ghép thành phần, tổng hợp nhiều hàng thành một chuỗi và thiết kế truy vấn có hiệu năng phù hợp. Mỗi ví dụ cũng làm rõ **ngữ nghĩa `NULL`**, sự khác biệt giữa chuỗi rỗng và giá trị thiếu, cũng như những bẫy khi làm việc với tiếng Việt và Unicode.

Mục tiêu quan trọng: **chuỗi hiển thị, khóa so sánh và dữ liệu gốc không nhất thiết là cùng một thứ**. Khi làm sạch hoặc ghép chuỗi, hãy xác định mục đích trước khi biến đổi giá trị.

## 1. Những kiểu chuỗi phổ biến trong PostgreSQL

PostgreSQL có các kiểu chuỗi cơ bản:

| Kiểu | Ý nghĩa | Tình huống |
|---|---|---|
| `text` | Chuỗi độ dài biến đổi, không đặt giới hạn độ dài trong khai báo | Tên, mô tả, nội dung |
| `varchar(n)` | Chuỗi độ dài biến đổi, giới hạn tối đa `n` ký tự | Dữ liệu cần một giới hạn ở schema |
| `varchar` | Chuỗi độ dài biến đổi không chỉ định giới hạn | Tương tự text trong nhiều trường hợp |
| `char(n)` / `character(n)` | Chuỗi độ dài cố định, được đệm dấu cách | Dữ liệu legacy hoặc giao thức thực sự cần độ dài cố định |

Ví dụ:

~~~sql
CREATE TABLE string_types_demo (
    description TEXT,
    short_code VARCHAR(20),
    fixed_code CHAR(5)
);
~~~

### 1.1. TEXT không có nghĩa là kém hiệu năng hơn VARCHAR

Trong PostgreSQL, `text` và `varchar</BT> không giới hạn thường có hành vi lưu trữ/hiệu năng tương đương cho nhiều ứng dụng. Không nên tự đặt `varchar(255)</BT> cho mọi cột chỉ vì thói quen từ một hệ quản trị khác.

Nếu nghiệp vụ thực sự yêu cầu giới hạn, có thể dùng `varchar(n)` hoặc constraint:

~~~sql
CREATE TABLE display_labels (
    label_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    label_text TEXT NOT NULL,
    CONSTRAINT chk_label_length
        CHECK (char_length(label_text) <= 120)
);
~~~

Giới hạn 120 ở đây là ví dụ nghiệp vụ, không phải giới hạn kỹ thuật mặc định của PostgreSQL.

### 1.2. Lưu ý CHAR(n) và dấu cách đệm

`char(n)` được đệm dấu cách tới độ dài khai báo và có những quy tắc đặc biệt khi so sánh/chuyển kiểu; dấu cách đệm cuối chuỗi thường không được xem giống dấu cách có ý nghĩa trong `text`.

Vì vậy, nếu ứng dụng cần giữ **chính xác văn bản người dùng nhập**, thường dùng `text</BT> hoặc `varchar</BT> phù hợp hơn `char(n)`. Đừng chọn `char(10)` chỉ để “căn đều mã”.

### 1.3. Chuỗi rỗng và NULL là hai giá trị khác nhau

~~~sql
SELECT
    ''::text IS NULL AS empty_is_null,
    NULL::text IS NULL AS null_is_null,
    char_length(''::text) AS empty_length;
~~~

Kết quả:

| empty_is_null | null_is_null | empty_length |
|---|---|---:|
| false | true | 0 |

Một chuỗi `''` có độ dài 0 nhưng **không phải NULL**. Một chuỗi `'   '` lại có ba ký tự dấu cách và cũng không phải NULL.

Nếu hệ thống cần phân biệt “không điền”, “cố ý để rỗng” và “chỉ có khoảng trắng”, phải thể hiện quy tắc đó trong API và schema, không dùng một hàm thay thế cho mọi trường hợp.

## 2. Nối chuỗi bằng toán tử ||

Toán tử **`||`** là cách nối chuỗi trực tiếp, thường dễ đọc với một số thành phần cố định:

~~~sql
SELECT
    'Postgre' || 'SQL' AS database_name,
    'Xin chào, ' || 'An' AS greeting;
~~~

Kết quả:

~~~text
database_name = PostgreSQL
greeting      = Xin chào, An
~~~

Nó giữ nguyên mọi ký tự trong các vế. PostgreSQL **không tự chèn khoảng trắng**:

~~~sql
SELECT 'Nguyễn' || 'Văn' || 'An' AS no_separator;
~~~

Kết quả là `NguyễnVănAn`.

Muốn có khoảng cách, phải thêm rõ:

~~~sql
SELECT
    'Nguyễn' || ' ' || 'Văn' || ' ' || 'An'
    AS full_name;
~~~

### 2.1. Dùng dấu phân cách có chủ đích

~~~sql
SELECT
    'ORD-' || '000123' AS order_code,
    'Hà Nội' || ', ' || 'Việt Nam' AS location_label,
    'key=' || 'value' AS pair_label;
~~~

Dấu cách trong `', '`, `' '` hoặc `' - '` chỉ là ký tự được yêu cầu nối; hàm không tự hiểu định dạng địa chỉ.

### 2.2. Nối giá trị không phải text

Nếu dữ liệu có kiểu số/ngày, hãy chọn cách chuyển sang chuỗi rõ ràng:

~~~sql
SELECT
    'Order #' || 123::text AS order_label,
    'Total: ' || 150000::text AS amount_label;
~~~

Có những overload toán tử cho phép ghép `text` với kiểu không phải chuỗi trong ngữ cảnh thích hợp, nhưng **ép kiểu rõ** thường dễ hiểu hơn khi viết ví dụ hoặc API SQL ổn định.

Muốn định dạng tiền, ngày hoặc timestamp có kiểm soát, dùng `to_char()</BT> hoặc tầng hiển thị thay vì mặc định ép thành `text`:

~~~sql
SELECT
    'Ngày: ' || to_char(
        DATE '2026-11-14',
        'DD/MM/YYYY'
    ) AS formatted_day;
~~~

### 2.3. NULL lan truyền qua ||

Điểm cực kỳ quan trọng:

~~~sql
SELECT
    'Xin chào ' || NULL::text AS greeting_with_null;
~~~

Kết quả là `NULL`, **không phải** chuỗi “Xin chào ”.

Tương tự:

~~~sql
SELECT
    'An' || ' ' || NULL::text AS full_name;
~~~

Toàn bộ biểu thức trả NULL.

Đây là điều thường làm hỏng nhãn hiển thị khi tên đệm, thành phố hoặc địa chỉ thứ hai là tùy chọn.

## 3. CONCAT(): nối nhiều giá trị và bỏ qua NULL

PostgreSQL có hàm `concat()</BT>:

~~~sql
SELECT
    concat('Postgre', 'SQL') AS db_name,
    concat('Order ', 123, ' - ', DATE '2026-11-14')
        AS order_description;
~~~

`concat()</BT> có thể nhận nhiều tham số và chuyển các giá trị thích hợp thành dạng chuỗi để ghép.

### 3.1. Khác biệt giữa CONCAT và ||

~~~sql
SELECT
    'Hello ' || NULL::text AS by_operator,
    concat('Hello ', NULL::text) AS by_function;
~~~

Ý nghĩa:

| Biểu thức | Kết quả |
|---|---|
| `'Hello ' || NULL::text` | NULL |
| `concat('Hello ', NULL::text)` | `'Hello '` |

Trong PostgreSQL, `concat()</BT> **bỏ qua các đối số NULL**. Trong khi đó, `||` thường trả NULL khi một toán hạng là NULL.

### 3.2. CONCAT không tự thêm dấu cách

~~~sql
SELECT concat('Nguyễn', 'Văn', 'An') AS result;
~~~

Kết quả vẫn là `NguyễnVănAn`.

Muốn có khoảng trắng:

~~~sql
SELECT concat('Nguyễn', ' ', 'Văn', ' ', 'An');
~~~

Hoặc dùng `concat_ws()</BT> ở phần kế tiếp khi có nhiều thành phần tùy chọn.

### 3.3. NULL và chuỗi rỗng trong CONCAT

Hàm bỏ qua `NULL` nhưng **chuỗi rỗng** vẫn là một đối số có giá trị, dù nó không tạo thêm ký tự:

~~~sql
SELECT
    concat('A', NULL::text, 'B') AS skip_null,
    concat('A', ''::text, 'B') AS empty_component;
~~~

Cả hai hiển thị `AB` nhưng dữ liệu đầu vào có ý nghĩa khác nhau. Nếu cần biết thành phần nào thực sự được người dùng nhập, đừng dùng nhãn đã ghép làm nguồn dữ liệu gốc.

### 3.4. Cẩn thận khi CONCAT che giấu thiếu dữ liệu

Nếu hệ thống bắt buộc có mã khách nhưng mã lại NULL, `concat('KH-', customer_code)` có thể tạo nhãn `KH-`. Nó **không báo rằng dữ liệu bắt buộc đang thiếu**.

Do đó, `concat()</BT> tốt cho trình bày, không thay thế `NOT NULL`, `CHECK` hoặc validation ứng dụng.

## 4. CONCAT_WS(): nối với dấu phân cách

`concat_ws(separator, value1, value2, ...)` là viết tắt của *concatenate with separator*.

~~~sql
SELECT concat_ws(
    ' ',
    'Nguyễn',
    'Văn',
    'An'
) AS full_name;
~~~

Kết quả: `Nguyễn Văn An`.

### 4.1. Tự chèn dấu phân cách giữa các đối số không NULL

~~~sql
SELECT
    concat_ws(', ', 'Hà Nội', 'Việt Nam')
        AS address_label,
    concat_ws(' / ', '2026', '11', '14')
        AS formatted_parts;
~~~

Kết quả tương ứng:

~~~text
Hà Nội, Việt Nam
2026 / 11 / 14
~~~

### 4.2. Bỏ qua NULL nhưng không tự bỏ chuỗi rỗng

~~~sql
SELECT
    concat_ws(' - ', 'A', NULL::text, 'C') AS skip_null,
    concat_ws(' - ', 'A', ''::text, 'C') AS keep_empty;
~~~

Kết quả:

| skip_null | keep_empty |
|---|---|
| `A - C` | `A -  - C` |

Điểm khác biệt:

- `NULL`: không góp một thành phần và không tạo dấu phân cách cho thành phần đó.
- `''`: vẫn là một thành phần **không NULL**, nên dấu phân cách xuất hiện trước/sau nó.

Nếu form gửi chuỗi rỗng cho trường không bắt buộc, cần quyết định chuyển nó thành NULL trước khi nối.

### 4.3. Kết hợp NULLIF để bỏ chuỗi rỗng

~~~sql
SELECT concat_ws(
    ', ',
    NULLIF(btrim(' 123 Nguyễn Huệ '), ''),
    NULLIF(btrim('   '), ''),
    NULLIF(btrim('TP. Hồ Chí Minh'), '')
) AS address_label;
~~~

Kết quả có ý nghĩa:

~~~text
123 Nguyễn Huệ, TP. Hồ Chí Minh
~~~

Mẫu hữu ích:

~~~sql
concat_ws(
    ', ',
    NULLIF(btrim(address_line1), ''),
    NULLIF(btrim(address_line2), ''),
    NULLIF(btrim(city), '')
)
~~~

Ví dụ trên chỉ chạy khi các cột `address_line1`, `address_line2`, `city` tồn tại trong truy vấn.

### 4.4. Separator là NULL

`concat_ws()</BT> yêu cầu separator có ý nghĩa. Trong PostgreSQL, separator bằng NULL khiến kết quả trả NULL; đừng coi nó như chuỗi rỗng một cách mặc định.

~~~sql
SELECT concat_ws(
    NULL::text,
    'A',
    'B'
) AS unknown_separator;
~~~

Nên chọn separator tường minh theo định dạng mong muốn.

### 4.5. Nếu mọi thành phần đều thiếu

Khi các thành phần phía sau separator đều NULL, bạn có thể nhận chuỗi rỗng thay vì một nhãn có ý nghĩa. Nếu muốn biểu diễn “không có nhãn” là NULL:

~~~sql
SELECT NULLIF(
    concat_ws(
        ', ',
        NULL::text,
        NULL::text
    ),
    ''
) AS optional_label;
~~~

Việc biến kết quả chuỗi rỗng thành NULL phải là **quy tắc nghiệp vụ có chủ đích**.

## 5. So sánh nhanh ||, CONCAT và CONCAT_WS

| Đặc điểm | `||` | `concat()` | `concat_ws()` |
|---|---|---|---|
| Mục đích | Ghép các toán hạng | Ghép nhiều tham số | Ghép với separator |
| Separator tự động | Không | Không | Có |
| NULL ở thành phần | Thường khiến kết quả NULL | Bỏ qua NULL | Bỏ qua NULL ở các thành phần |
| NULL ở separator | Không có tham số riêng | Không có tham số riêng | Kết quả NULL |
| Chuỗi rỗng | Giữ nguyên | Giữ nguyên | Thành phần rỗng vẫn ảnh hưởng separator |
| Ví dụ phù hợp | Prefix/suffix có cấu trúc | Ghép nhãn đơn giản | Tên/địa chỉ có thành phần tùy chọn |

### 5.1. Chọn cách nào?

- Dùng `||` khi từng phần là bắt buộc và muốn NULL lan truyền rõ.
- Dùng `concat()</BT> khi cần ghép nhiều phần và chủ đích bỏ qua NULL.
- Dùng `concat_ws()</BT> khi cần chèn dấu phân cách giữa những thành phần tùy chọn.

Ví dụ địa chỉ nhiều thành phần thường hợp với `concat_ws(', ', ...)`; mã SKU ghép thành phần bắt buộc có thể hợp với `||` cùng constraint trên các phần.

## 6. Khoảng trắng trong dữ liệu thực tế

“Ký tự trắng” không chỉ có một loại. Một số ví dụ:

| Loại | Ý nghĩa | Ví dụ |
|---|---|---|
| Space thông thường | Dấu cách U+0020 | Giữa hai từ |
| Tab | U+0009 | Văn bản sao chép từ bảng |
| Newline | LF hoặc CR/LF | Xuống dòng |
| Non-breaking space | U+00A0 | Nội dung HTML, văn bản copy |
| Các ký tự Unicode khác | Nhiều loại khoảng trắng và định dạng | Nội dung từ tài liệu bên ngoài |

Vì thế, câu “xóa khoảng trắng” cần được hiểu thành:

1. Chỉ bỏ dấu cách đầu/cuối?
2. Bỏ cả tab và xuống dòng ở đầu/cuối?
3. Gộp nhiều dấu trắng nội bộ thành một dấu cách?
4. Giữ các dấu xuống dòng có ý nghĩa trong nội dung?
5. Có xử lý non-breaking space không?
6. Có giữ nguyên ký tự Unicode trong tên người và địa chỉ không?

Những câu trả lời khác nhau tạo ra **các phép biến đổi khác nhau**.

### 6.1. Khoảng trắng đầu/cuối và giữa các từ

~~~text
"   Nguyễn   Văn An   "
 ^^^        ^^^     ^^^
 đầu      nội bộ    cuối
~~~

`trim()</BT> hoặc `btrim()</BT> thông thường xử lý **đầu/cuối**, không tự gộp các khoảng trắng giữa các từ.

## 7. TRIM(): loại ký tự ở hai đầu chuỗi

Cú pháp SQL chuẩn:

~~~sql
TRIM([LEADING | TRAILING | BOTH] [characters] FROM string)
~~~

Ví dụ cơ bản:

~~~sql
SELECT
    trim('   PostgreSQL   ') AS normalized;
~~~

Kết quả: `PostgreSQL`.

### 7.1. BOTH, LEADING, TRAILING

~~~sql
SELECT
    trim(BOTH FROM '  ABC  ') AS both_sides,
    trim(LEADING FROM '  ABC  ') AS left_only,
    trim(TRAILING FROM '  ABC  ') AS right_only;
~~~

Kết quả theo ý nghĩa:

| both_sides | left_only | right_only |
|---|---|---|
| `ABC` | `ABC  ` | `  ABC` |

Dấu cách trong cột hiển thị có thể không rõ nếu công cụ SQL tự định dạng; có thể kết hợp `quote_nullable()</BT> hoặc đo `length()</BT> để quan sát chính xác.

### 7.2. Chỉ định ký tự muốn bỏ

~~~sql
SELECT
    trim(BOTH '-' FROM '---ABC---') AS without_hyphens,
    trim(LEADING '0' FROM '000123') AS no_leading_zeroes;
~~~

Kết quả tương ứng `ABC` và `123`.

### 7.3. TRIM không tìm rồi xóa toàn bộ nội dung giữa chuỗi

~~~sql
SELECT trim(BOTH '-' FROM '--A-B--') AS result;
~~~

Kết quả là `A-B`, vì dấu `-` bên trong không nằm ở biên.

### 7.4. Chú ý khi xóa số 0 đầu mã định danh

Ví dụ:

~~~sql
SELECT trim(LEADING '0' FROM '000123') AS altered_code;
~~~

Kết quả `123`. Nếu `000123` là mã khách hàng mà số 0 đầu **có ý nghĩa**, thao tác này làm thay đổi định danh.

**Không trim ký tự chỉ để “làm sạch” nếu các ký tự đó thuộc dữ liệu nghiệp vụ.**

## 8. BTRIM(), LTRIM() và RTRIM()

PostgreSQL có ba hàm thường dùng:

- `btrim(text [, characters])`: loại ký tự ở cả hai đầu.
- `ltrim(text [, characters])`: loại ký tự ở đầu trái.
- `rtrim(text [, characters])`: loại ký tự ở đầu phải.

Ví dụ:

~~~sql
SELECT
    btrim('  ABC  ') AS trimmed,
    ltrim('  ABC  ') AS left_trimmed,
    rtrim('  ABC  ') AS right_trimmed;
~~~

### 8.1. Chỉ định tập ký tự

~~~sql
SELECT
    btrim('xy--Hello--yx', 'xy-') AS both,
    ltrim('00ABC00', '0') AS left_zeroes,
    rtrim('00ABC00', '0') AS right_zeroes;
~~~

Kết quả:

| both | left_zeroes | right_zeroes |
|---|---|---|
| `Hello` | `ABC00` | `00ABC` |

### 8.2. Đối số characters là tập ký tự, không phải chuỗi con cần tìm

Điểm dễ nhầm:

~~~sql
SELECT btrim('abcXYZcba', 'abc') AS result;
~~~

Kết quả `XYZ` vì mọi ký tự `a`, `b` hoặc `c` ở hai đầu đều bị loại liên tiếp.

Hàm **không yêu cầu đầu chuỗi phải có nguyên cụm “abc” theo đúng thứ tự**.

Nếu cần xóa một prefix/suffix cụ thể với điều kiện rõ, có thể dùng logic `starts_with()</BT>, `left()</BT>, `right()</BT>, `substring()</BT> hoặc regex phù hợp thay vì hiểu sai `trim(..., characters)`.

### 8.3. Ví dụ xóa dấu phân cách ở biên

~~~sql
SELECT
    btrim('///api/v1/customers///', '/') AS route_body;
~~~

Kết quả: `api/v1/customers`. Dấu `/` ở giữa được giữ.

Với URL/path thực, phải phân biệt slash có ý nghĩa cấu trúc trước khi chuẩn hóa. Một thao tác btrim không phải bộ parser URL.

## 9. TRIM mặc định không loại mọi loại khoảng trắng

Trong trường hợp thông thường, `trim()</BT>, `btrim()</BT>, `ltrim()</BT> và `rtrim()</BT> không truyền đối số tập ký tự sẽ loại **dấu cách thông thường** ở biên, không phải mặc định mọi ký tự Unicode được coi là whitespace.

Kiểm tra với tab:

~~~sql
SELECT
    char_length(E'\tABC\t') AS original_length,
    char_length(btrim(E'\tABC\t')) AS default_trim_length,
    char_length(btrim(E'\tABC\t', E' \t\n\r'))
        AS explicit_trim_length;
~~~

Ý nghĩa:

- Chuỗi ban đầu có tab ở hai đầu.
- `btrim(...)</BT> mặc định không nhất thiết bỏ tab.
- `btrim(..., E' \t\n\r')</BT> được yêu cầu loại space, tab, LF và CR ở biên.

### 9.1. E'' là escape string literal

Trong PostgreSQL:

~~~sql
SELECT
    E'\t' AS tab_character,
    E'\n' AS newline_character;
~~~

`E'...'` cho phép biểu diễn escape như `\t` và `\n` rõ ràng. Với dữ liệu nhập bên ngoài, nên truyền typed parameters thay vì tự xây literal có escape.

### 9.2. Dùng btrim với tập ký tự rõ ràng

~~~sql
SELECT
    btrim(
        E'\t \n  Xin chào \r\n ',
        E' \t\n\r'
    ) AS cleaned_edges;
~~~

Kết quả có ý nghĩa: `Xin chào`.

Nhưng nếu đây là nội dung văn bản nhiều dòng và xuống dòng đầu/cuối có ý nghĩa, việc loại bỏ chúng có thể không mong muốn. Không phải mọi `TEXT` đều là “một nhãn trên một dòng”.

## 10. Non-breaking space và khoảng trắng Unicode

Dữ liệu copy từ HTML, tài liệu văn phòng hoặc ứng dụng chat có thể chứa **non-breaking space (NBSP, U+00A0)**. Nó nhìn gần giống dấu cách thông thường nhưng là ký tự khác.

Trong database UTF-8, có thể tạo NBSP bằng:

~~~sql
SELECT chr(160) AS nbsp_character;
~~~

Một ví dụ:

~~~sql
SELECT
    char_length('A' || chr(160) || 'B') AS length_in_characters,
    octet_length('A' || chr(160) || 'B') AS length_in_bytes;
~~~

Trên database UTF-8, chuỗi có 3 ký tự nhưng NBSP chiếm nhiều byte hơn space ASCII.

### 10.1. Đổi NBSP sang space khi nghiệp vụ cho phép

~~~sql
SELECT
    replace(
        '  Nguyễn' || chr(160) || 'Văn  ',
        chr(160),
        ' '
    ) AS normalized_spaces;
~~~

Nếu muốn loại space ngoài biên sau khi thay:

~~~sql
SELECT
    btrim(
        replace(
            '  Nguyễn' || chr(160) || 'Văn  ',
            chr(160),
            ' '
        )
    ) AS display_name;
~~~

Kết quả: `Nguyễn Văn`.

### 10.2. Có cần thay toàn bộ Unicode whitespace?

Không phải lúc nào cũng vậy. Một số ký tự trắng có ý nghĩa trong ngôn ngữ, kiểu chữ hoặc định dạng; một số ký tự định dạng vô hình còn **không thuộc nhóm whitespace thông thường**.

Việc “xóa mọi ký tự không nhìn thấy” có thể làm hỏng văn bản quốc tế, tên riêng hoặc dữ liệu cần đối chiếu. Nên định nghĩa danh sách ký tự muốn chuẩn hóa theo từng trường: email, tên, địa chỉ, mô tả hoặc nội dung tự do.

### 10.3. Regex whitespace phụ thuộc tập ký tự và môi trường

PostgreSQL hỗ trợ POSIX character class như `[[:space:]]` trong regular expression. Tập ký tự được nhận diện có thể chịu ảnh hưởng của đặc tính ký tự/collation và phiên bản. **Đừng giả định regex này luôn xử lý tất cả ký tự Unicode hiếm** nếu chưa thống nhất chính sách dữ liệu.

Với NBSP đã biết, `replace(value, chr(160), ' ')` là một biến đổi tường minh, dễ hiểu hơn.

## 11. Gộp khoảng trắng giữa các từ bằng REGEXP_REPLACE

`trim</BT> chỉ xử lý biên, còn khoảng trắng nội bộ vẫn tồn tại:

~~~sql
SELECT btrim('  Trần   Thị   Bình  ') AS still_has_multiple_spaces;
~~~

Kết quả: `Trần   Thị   Bình`.

Muốn thay mỗi chuỗi liên tiếp các ký tự whitespace phù hợp bằng một dấu cách:

~~~sql
SELECT regexp_replace(
    '  Trần   Thị   Bình  ',
    '[[:space:]]+',
    ' ',
    'g'
) AS normalized_runs;
~~~

### 11.1. Vì sao dùng flag 'g'?

Mặc định, `regexp_replace</BT> thay lần khớp đầu tiên theo giao diện phổ biến; flag `'g'` yêu cầu thay **mọi lần khớp**.

~~~sql
SELECT
    regexp_replace('A   B   C', '[[:space:]]+', ' ')
        AS first_match_only,
    regexp_replace('A   B   C', '[[:space:]]+', ' ', 'g')
        AS all_matches;
~~~

Chỉ dạng có `'g'` đảm bảo các cụm whitespace trong toàn chuỗi được thay theo mục tiêu.

### 11.2. Kết hợp regex và trim

~~~sql
SELECT btrim(
    regexp_replace(
        '  Trần   Thị   Bình  ',
        '[[:space:]]+',
        ' ',
        'g'
    )
) AS normalized_full_name;
~~~

Kết quả: `Trần Thị Bình`.

Quy trình ý nghĩa:

1. Mỗi dãy whitespace được thay bằng một space.
2. Space đầu/cuối còn lại bị loại bởi `btrim</BT>.

### 11.3. Regex không phải lựa chọn mặc định cho mọi trường

Trong mô tả sản phẩm hoặc ghi chú nhiều đoạn, nhiều dấu xuống dòng có thể giúp giữ cấu trúc nội dung. Gộp toàn bộ whitespace về một space sẽ phá định dạng.

Mẫu regex này phù hợp hơn với **nhãn một dòng** có chính sách rõ ràng, không phải mọi cột `TEXT`.

## 12. LENGTH, CHAR_LENGTH và OCTET_LENGTH

Để biết một chuỗi dài bao nhiêu, cần phân biệt **số ký tự** và **số byte**.

~~~sql
SELECT
    length('PostgreSQL') AS length_1,
    char_length('PostgreSQL') AS length_2,
    octet_length('PostgreSQL') AS byte_length;
~~~

Với chuỗi ASCII `PostgreSQL`, cả ba là 10.

### 12.1. Với tiếng Việt, ký tự có thể chiếm nhiều byte

~~~sql
SELECT
    char_length('Việt') AS characters,
    octet_length('Việt') AS bytes,
    bit_length('Việt') AS bits;
~~~

Trong database UTF-8, chuỗi `Việt` theo dạng chữ `ệ` dựng sẵn thường có:

| characters | bytes | bits |
|---:|---:|---:|
| 4 | 6 | 48 |

`V`, `i`, `t` là các ký tự ASCII mỗi ký tự 1 byte; `ệ` là một ký tự Unicode có thể chiếm 3 byte trong UTF-8.

### 12.2. LENGTH và CHAR_LENGTH có ý nghĩa “số ký tự”

Trên cột `text</BT> hoặc `varchar</BT> thông thường:

~~~sql
SELECT
    length('Hà Nội') AS by_length,
    char_length('Hà Nội') AS by_char_length;
~~~

Cả hai đo độ dài theo ký tự của chuỗi, không theo số byte lưu trữ.

### 12.3. Một ký tự người dùng nhìn thấy có thể gồm nhiều code point

Unicode cho phép cùng một chữ có dấu được biểu diễn bằng:

- Một code point dựng sẵn.
- Một chữ cơ sở cộng một hoặc nhiều dấu kết hợp.

Ví dụ minh họa:

~~~sql
SELECT
    char_length('é') AS precomposed,
    char_length(U&'e\0301') AS combining_sequence;
~~~

Về mặt hiển thị, hai biểu diễn có thể giống nhau, nhưng số code point có thể là 1 và 2. `char_length()</BT> không phải bộ đếm “cụm chữ nhìn thấy” (*grapheme clusters*) hoàn chỉnh.

### 12.4. Giới hạn giao diện và byte payload

Nếu API cần giới hạn 120 ký tự nhập, `char_length()</BT> có thể phù hợp hơn `octet_length()` trong nhiều trường hợp; nhưng với Unicode phức tạp, “120 ký tự người dùng nhìn thấy” cần định nghĩa thêm ở ứng dụng.

Nếu hệ thống giới hạn số byte khi gửi giao thức ngoài, `octet_length()</BT> có ý nghĩa riêng. Không dùng hai hàm thay thế tùy tiện.

## 13. Phát hiện chuỗi rỗng và chuỗi chỉ có khoảng trắng

Ba trường hợp cơ bản:

~~~sql
SELECT
    NULL::text AS missing_value,
    ''::text AS empty_value,
    '   '::text AS whitespace_value;
~~~

### 13.1. Kiểm tra không rỗng sau trim

~~~sql
SELECT
    btrim('   ') = '' AS only_spaces,
    btrim('  An  ') = '' AS nonblank_name;
~~~

Kết quả: `true` và `false`.

### 13.2. NULLIF để chuyển chuỗi rỗng thành NULL

~~~sql
SELECT
    NULLIF(btrim('   '), '') AS missing_after_trim,
    NULLIF(btrim(' An '), '') AS name_after_trim;
~~~

Ý nghĩa:

- `NULLIF(btrim('   '), '')` trả NULL.
- `NULLIF(btrim(' An '), '')` trả `An`.

Đây là mẫu rất hữu ích trước khi `concat_ws()</BT>, trước khi đưa giá trị vào một cột optional, hoặc khi cần đánh dấu những trường người dùng không cung cấp thông tin có ý nghĩa.

### 13.3. NULLIF không tự chuẩn hóa mọi khoảng trắng Unicode

Nếu chuỗi chỉ gồm NBSP, `btrim</BT> mặc định có thể không loại ký tự đó. Chính sách chuẩn hóa cần xét rõ loại ký tự và nguồn dữ liệu.

### 13.4. Constraint cùng hàng

Ví dụ cột tên bắt buộc:

~~~sql
CREATE TABLE people_names (
    person_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    full_name TEXT NOT NULL,
    CONSTRAINT chk_full_name_not_blank
        CHECK (btrim(full_name) <> '')
);
~~~

Constraint này ngăn tên NULL bằng `NOT NULL` và ngăn chuỗi toàn dấu cách thông thường bằng `CHECK`. Nếu dữ liệu cần chặn tab hoặc NBSP ở biên, phải mở rộng rule đúng cách.

Ứng dụng vẫn nên kiểm tra trước và hiển thị thông báo như “Tên không được để trống”.

## 14. LOWER, UPPER và INITCAP

PostgreSQL hỗ trợ biến đổi chữ hoa/chữ thường:

~~~sql
SELECT
    lower('PostgreSQL') AS lower_case,
    upper('PostgreSQL') AS upper_case,
    initcap('hello world') AS title_case;
~~~

Với dữ liệu ASCII, kết quả thường là:

~~~text
postgresql
POSTGRESQL
Hello World
~~~

### 14.1. LOWER cho khóa so sánh

Khi muốn tìm email theo quy tắc so khớp không phân biệt hoa/thường do sản phẩm đặt ra:

~~~sql
SELECT lower(btrim('  An@Example.COM  ')) AS normalized_email_key;
~~~

Kết quả thường là `an@example.com`.

Nhưng lưu ý: địa chỉ email có những quy tắc thực tế phức tạp, và cách dùng chữ hoa/thường ở local part không thể áp dụng máy móc theo cùng một chuẩn cho tất cả hệ thống. **Phải xác định quy tắc canonical của sản phẩm** trước khi dùng `lower()</BT> làm khóa duy nhất.

### 14.2. LOWER/UPPER có thể phụ thuộc locale/collation

Việc biến đổi chữ có dấu và một số ngôn ngữ khác không luôn giống quy tắc ASCII. Kết quả có thể phụ thuộc cấu hình locale/collation và phiên bản PostgreSQL hay thư viện collation.

Đừng đưa ra giả định “một ký tự hoa luôn chuyển thành đúng một ký tự thường” trong mọi ngôn ngữ. Khi thiết kế khóa chuẩn hóa xuyên hệ thống, cần thống nhất Unicode, collation và cách ứng dụng xử lý.

### 14.3. INITCAP không phải bộ chuẩn hóa tên người tuyệt đối

~~~sql
SELECT initcap('nguyễn văn an') AS display_guess;
~~~

Hàm có thể hữu ích cho một số nhãn, nhưng tên riêng, từ viết tắt, tên công ty và ngôn ngữ khác nhau có quy tắc viết hoa phức tạp. Không tự sửa hàng loạt tên thật bằng `initcap()</BT> mà không có yêu cầu và chính sách rõ.

### 14.4. Không sửa dữ liệu gốc khi chỉ cần tìm kiếm

Có thể lưu tên người theo dạng đã xác minh và tạo khóa so sánh ở truy vấn/index. Biến đổi để **so sánh** không nhất thiết phải đồng nghĩa với ghi đè giá trị người dùng nhập.

## 15. Unicode normalization: hai chuỗi nhìn giống vẫn có thể khác

Hai biểu diễn của ký tự có dấu có thể hiển thị giống nhau nhưng chứa chuỗi code point khác nhau. Điều này ảnh hưởng:

- So sánh chuỗi.
- Tìm kiếm chính xác.
- Uniqueness.
- Tính độ dài.
- Hash/checksum.
- Đồng bộ giữa ứng dụng và database.

PostgreSQL cung cấp hàm `normalize()</BT> cho Unicode normalization trên database sử dụng encoding UTF-8, ở các phiên bản hỗ trợ.

~~~sql
SELECT
    normalize(U&'e\0301', NFC) AS normalized_nfc,
    normalize('é', NFD) AS normalized_nfd;
~~~

`NFC` hướng tới dạng kết hợp dựng sẵn khi có thể; `NFD` hướng tới dạng phân rã chuẩn.

### 15.1. NFC không phải xóa dấu tiếng Việt

Normalization không đồng nghĩa bỏ dấu. Các dạng Unicode normalization chuẩn **giữ ý nghĩa chữ có dấu** trong khi tổ chức lại cách biểu diễn code point.

Nếu muốn tìm kiếm không phân biệt dấu, đó là yêu cầu khác với normalization và cần thiết kế tìm kiếm/collation tương ứng.

### 15.2. Không áp dụng NFKC một cách mù quáng

Các dạng tương thích như `NFKC` có thể thay đổi cách biểu diễn của một số ký tự tương thích. Chúng hữu ích trong vài bài toán khóa so sánh, nhưng có thể làm mất khác biệt mà dữ liệu gốc cần giữ.

Hãy phân biệt:

~~~text
Raw text:
    dữ liệu được nhập hoặc hiển thị

Comparison key:
    dữ liệu đã chuẩn hóa theo quy tắc tìm kiếm/duy nhất
~~~

Không nhất thiết nên ghi đè raw text bằng comparison key.

## 16. SUBSTRING và SUBSTR: cắt một phần chuỗi

PostgreSQL hỗ trợ cú pháp:

~~~sql
SELECT
    substring('PostgreSQL' FROM 1 FOR 4) AS prefix,
    substring('PostgreSQL' FROM 5 FOR 3) AS middle;
~~~

Kết quả:

| prefix | middle |
|---|---|
| `Post` | `gre` |

### 16.1. Vị trí bắt đầu thường tính từ 1

Trong SQL ở PostgreSQL, vị trí ký tự đầu tiên là **1**, không phải 0 như chỉ số mảng của nhiều ngôn ngữ lập trình.

~~~sql
SELECT substr('ABCDEFG', 2, 3) AS fragment;
~~~

Kết quả `BCD`.

### 16.2. Cắt không đồng nghĩa validate mã

Giả sử mã hàng có dạng `SKU-12345`:

~~~sql
SELECT substring('SKU-12345' FROM 5) AS code_part;
~~~

Kết quả `12345`.

Nhưng nếu đầu vào là `WRONG-12345`, lấy substring từ vị trí cố định không chứng minh prefix hợp lệ. Nên kiểm tra cấu trúc mã nếu nó là dữ liệu quan trọng, thay vì chỉ cắt rồi tin kết quả.

### 16.3. Với Unicode, cắt ký tự khác cắt byte

`substring()</BT> trên `text` xử lý vị trí ký tự, không phải chọn các byte UTF-8 tùy tiện. Nhưng việc cắt theo code point vẫn có thể chia một grapheme cluster gồm chữ cơ sở và dấu kết hợp nếu không có xử lý Unicode thích hợp ở tầng trình bày.

## 17. LEFT và RIGHT: lấy đầu/cuối chuỗi

~~~sql
SELECT
    left('PostgreSQL', 4) AS first_four,
    right('PostgreSQL', 3) AS last_three;
~~~

Kết quả `Post` và `SQL`.

### 17.1. Tách phần hiển thị từ mã

~~~sql
SELECT
    left('ORD-2026-000123', 3) AS code_prefix,
    right('ORD-2026-000123', 6) AS serial;
~~~

Kết quả `ORD` và `000123`.

Nếu mã có độ dài hoặc cấu trúc không cố định, cắt đầu/cuối có thể sai. Với mã nghiệp vụ, nên có parser/constraint rõ.

### 17.2. Không dùng RIGHT để lấy “n chữ nhìn thấy” trong mọi ngôn ngữ

Nếu chuỗi chứa các tổ hợp Unicode nhiều code point, `right(text, n)` có thể cắt trên ranh giới code point nhưng không nhất thiết đúng ranh giới grapheme. Đây là cùng vấn đề như `substring()</BT>.

## 18. POSITION và STRPOS: tìm vị trí chuỗi con

~~~sql
SELECT
    position('gre' IN 'PostgreSQL') AS pos_1,
    strpos('PostgreSQL', 'gre') AS pos_2;
~~~

Cả hai trả vị trí bắt đầu **5**.

### 18.1. Khi không tìm thấy

~~~sql
SELECT
    position('XYZ' IN 'PostgreSQL') AS missing_pos;
~~~

Kết quả là `0`, không phải NULL.

Do đó:

~~~sql
SELECT
    strpos('alpha@example.com', '@') > 0
        AS contains_at_symbol;
~~~

trả true. Nhưng có ký tự @ **không chứng minh email hợp lệ**.

### 18.2. Tìm vị trí không phải tìm kiếm mờ

`strpos()</BT> tìm chuỗi con theo điều kiện tương ứng, không tự bỏ dấu, không tự đổi chữ hoa/thường và không tự sửa lỗi chính tả.

Nếu cần tìm kiếm linh hoạt, xem `ILIKE`, regex, full-text search hoặc trigram indexing tùy bài toán.

## 19. REPLACE: thay chuỗi con theo nghĩa literal

`replace(source, from, to)` thay các lần xuất hiện của **chuỗi con** `from` bằng `to`.

~~~sql
SELECT
    replace('a-b-c', '-', '/') AS changed_separator,
    replace('Hello Hello', 'Hello', 'Hi')
        AS changed_words;
~~~

Kết quả:

~~~text
a/b/c
Hi Hi
~~~

### 19.1. REPLACE không dùng regex

~~~sql
SELECT replace('a   b', '  ', ' ') AS result;
~~~

Đây chỉ là thay chuỗi hai dấu cách bằng một dấu cách theo literal. Nó không có khái niệm “mọi dãy whitespace bất kỳ độ dài” như regex.

### 19.2. Xóa một chuỗi con

~~~sql
SELECT
    replace('ABC-123-XYZ', '-', '') AS no_hyphens;
~~~

Kết quả `ABC123XYZ`.

Nếu dấu gạch là một phần nhận diện dữ liệu, việc xóa chúng sẽ thay đổi định danh. Chỉ dùng khi quy tắc chuẩn hóa cho phép.

### 19.3. Đổi ký tự NBSP

~~~sql
SELECT replace(
    'Hà' || chr(160) || 'Nội',
    chr(160),
    ' '
) AS normalized_city;
~~~

Kết quả hiển thị `Hà Nội`.

Cách này tường minh hơn việc trông chờ một regex chung nhận mọi loại ký tự trắng.

## 20. TRANSLATE: ánh xạ từng ký tự

`translate(source, from_characters, to_characters)` thay ký tự theo **vị trí tương ứng** giữa hai tập ký tự.

~~~sql
SELECT translate('abc', 'abc', 'xyz') AS mapped;
~~~

Kết quả `xyz`.

### 20.1. Khác REPLACE

~~~sql
SELECT
    replace('a-b-c', '-', '') AS by_replace,
    translate('a-b-c', '-', '') AS by_translate;
~~~

Cả hai có thể tạo `abc` khi loại ký tự `-`, nhưng tư duy khác:

- `replace</BT> tìm **chuỗi con**.
- `translate</BT> ánh xạ **từng ký tự**.

Nếu chuỗi đích ngắn hơn chuỗi nguồn trong `translate</BT>, những ký tự nguồn không có ký tự đối ứng có thể bị loại bỏ.

### 20.2. Không dùng TRANSLATE để chuyển ngữ tiếng Việt tổng quát

Bỏ dấu tiếng Việt không chỉ là vài ký tự ASCII tương ứng. Cần hiểu Unicode, chữ hoa/thường và các dạng tổ hợp. Hàm `translate</BT> đơn giản không thay thế một bộ xử lý ngôn ngữ đầy đủ.

## 21. REGEXP_REPLACE: thay theo mẫu

PostgreSQL hỗ trợ regular expression cho những quy tắc biến đổi phức tạp hơn `replace</BT>.

~~~sql
SELECT regexp_replace(
    'A---B----C',
    '-+',
    '-',
    'g'
) AS normalized_dashes;
~~~

Kết quả `A-B-C`.

### 21.1. Mẫu [[:space:]]+

~~~sql
SELECT btrim(
    regexp_replace(
        E'  Nguyễn \t Văn \n An  ',
        '[[:space:]]+',
        ' ',
        'g'
    )
) AS normalized_name;
~~~

Ý nghĩa: các dãy ký tự whitespace được regex nhận diện được thay bằng một space, sau đó xóa space ở hai đầu.

### 21.2. Mẫu chỉ dành cho dữ liệu một dòng

Nếu ghi chú chứa ba đoạn văn, gộp mọi newline thành space làm mất ngắt đoạn. Cần đặt quy tắc theo loại trường:

| Trường | Chính sách thường cân nhắc |
|---|---|
| Email | Trim biên và canonicalization theo chính sách |
| Tên hiển thị | Trim biên, gộp whitespace nếu được phép |
| Địa chỉ | Giữ những thành phần và ký tự có ý nghĩa |
| Mô tả nhiều dòng | Giữ newline có chủ đích |
| Mã SKU | Không tự sửa ký tự nếu là định danh |
| Nội dung HTML/Markdown | Dùng parser hoặc sanitizer thích hợp, không chỉ regex |

### 21.3. Regex replace không phải công cụ chống SQL injection

Xóa dấu nháy đơn hoặc dấu chấm phẩy khỏi chuỗi bằng regex **không phải cách an toàn để ghép SQL**. Các truy vấn nhận dữ liệu người dùng phải dùng typed parameters, như JDBC `PreparedStatement</BT>, và whitelist/quote identifier khi phải xây SQL động.

## 22. Tách chuỗi bằng SPLIT_PART

`split_part(source, delimiter, field_number)` trả một phần từ chuỗi, đếm phần từ vị trí 1.

~~~sql
SELECT
    split_part('A|B|C', '|', 1) AS first_part,
    split_part('A|B|C', '|', 2) AS second_part,
    split_part('A|B|C', '|', 3) AS third_part;
~~~

Kết quả: `A`, `B`, `C`.

### 22.1. Phần không tồn tại

~~~sql
SELECT split_part('A|B', '|', 3) AS missing_field;
~~~

Khi yêu cầu phần vượt số lượng thành phần hiện có, kết quả có thể là **chuỗi rỗng**. Không coi nó tương đương NULL nếu cần phân biệt lỗi cấu trúc.

### 22.2. Không dùng SPLIT_PART('@') như email parser đầy đủ

~~~sql
SELECT split_part('alice@example.com', '@', 2) AS apparent_domain;
~~~

Kết quả là `example.com` cho ví dụ đơn giản. Nhưng cú pháp email thực tế phức tạp; đây không phải bộ xác thực hoặc parser chuẩn cho mọi địa chỉ email hợp lệ.

### 22.3. Khi nào nên dùng?

- Tách mã dữ liệu có delimiter ổn định và được validate.
- Phân tích chuỗi log đơn giản theo hợp đồng rõ.
- Đọc một phần từ mã cấu trúc do hệ thống sinh.

Nếu dữ liệu chứa delimiter tự do trong nội dung, split đơn giản có thể làm hỏng cấu trúc. Dùng format và parser thích hợp như CSV/JSON thay vì ghép delimiter thủ công khi dữ liệu có thể chứa dấu phân cách.

## 23. STRING_TO_ARRAY và ARRAY_TO_STRING

Nếu cần tách một chuỗi thành mảng:

~~~sql
SELECT string_to_array('red,green,blue', ',') AS colors;
~~~

Kết quả là một mảng text gồm ba phần.

Ghép mảng thành chuỗi:

~~~sql
SELECT array_to_string(
    ARRAY['red', 'green', 'blue'],
    ', '
) AS color_label;
~~~

Kết quả: `red, green, blue`.

### 23.1. Mảng không giải quyết mọi trường hợp delimiter

Nếu một thành phần có dấu phẩy trong tên như `“Phường 1, Quận 5”`, ghép các phần bằng dấu phẩy rồi tách lại có thể mất ranh giới ban đầu.

Khi dữ liệu cần serialization an toàn, dùng JSON/array typed/CSV parser phù hợp; đừng tự chọn một delimiter rồi giả định nó không bao giờ xuất hiện trong dữ liệu.

### 23.2. NULL trong mảng

`array_to_string</BT> có hành vi riêng với phần tử NULL và đối số thay thế NULL tùy cách gọi. Khi cần hiển thị “không có dữ liệu” rõ ràng, nên thử trực tiếp mẫu dữ liệu thực và chọn chính sách tường minh thay vì giả định NULL giống chuỗi rỗng.

## 24. STRING_AGG: ghép nhiều hàng thành một chuỗi

Cho tới đây, các hàm chủ yếu nối giá trị **trong cùng một hàng**. `string_agg()</BT> là **aggregate**, có thể nối giá trị từ **nhiều hàng** trong cùng nhóm.

~~~sql
SELECT string_agg(name, ', ') AS names
FROM (
    VALUES ('An'), ('Bình'), ('Cường')
) AS people(name);
~~~

Kết quả có ý nghĩa là một chuỗi ba tên, nhưng nếu cần **thứ tự ổn định** phải thêm `ORDER BY` bên trong aggregate.

### 24.1. Sắp xếp trong STRING_AGG

~~~sql
SELECT string_agg(name, ', ' ORDER BY name) AS names
FROM (
    VALUES ('Bình'), ('An'), ('Cường')
) AS people(name);
~~~

Kết quả được ghép theo thứ tự sắp xếp đã nêu.

**Không giả định thứ tự truy xuất tự nhiên** là thứ tự nối chuỗi, kể cả khi query chạy vài lần đều ra cùng một thứ tự.

### 24.2. GROUP BY để tạo danh sách mỗi nhóm

~~~sql
SELECT
    category,
    string_agg(product_name, ' | ' ORDER BY product_name)
        AS product_names
FROM products
GROUP BY category
ORDER BY category;
~~~

Ví dụ này yêu cầu bảng `products</BT> có `category` và `product_name`; phần lab sau tạo một bảng phù hợp.

### 24.3. Bỏ giá trị trùng khi thực sự cần

~~~sql
SELECT string_agg(
    DISTINCT tag,
    ', ' ORDER BY tag
) AS unique_tags
FROM (
    VALUES ('sql'), ('postgres'), ('sql')
) AS t(tag);
~~~

Kết quả: `postgres, sql`.

Dùng `DISTINCT` chỉ khi những giá trị lặp không có ý nghĩa nghiệp vụ. Nếu danh sách cần cho biết một tag được gắn ba lần, loại trùng làm mất thông tin.

### 24.4. STRING_AGG bỏ qua giá trị NULL

~~~sql
SELECT string_agg(
    item,
    ' + ' ORDER BY item
) AS result
FROM (
    VALUES ('A'::text), (NULL::text), ('B'::text)
) AS t(item);
~~~

Kết quả: `A + B`. Các giá trị NULL không tạo thành phần hiển thị.

### 24.5. Tập không có giá trị hợp lệ

Nếu không có hàng hoặc tất cả biểu thức cần nối đều NULL, kết quả `string_agg</BT> thường là NULL, không phải chuỗi rỗng. Phân biệt điều này với `concat</BT> trên các đối số cùng hàng.

### 24.6. STRING_AGG không thích hợp cho mọi tập lớn

Ghép hàng trăm nghìn/millions giá trị vào một chuỗi làm tăng kích thước kết quả, có thể tốn bộ nhớ và khó tiêu thụ từ API. Nếu ứng dụng thực sự cần danh sách có cấu trúc, có thể dùng `array_agg</BT>, `json_agg</BT>, phân trang hoặc truy vấn các hàng riêng.

## 25. FORMAT: định dạng chuỗi theo mẫu

PostgreSQL có hàm:

~~~sql
format(format_string, arguments...)
~~~

Một ví dụ:

~~~sql
SELECT format(
    'Khách hàng: %s, đơn hàng: %s',
    'An',
    123
) AS message;
~~~

Kết quả: `Khách hàng: An, đơn hàng: 123`.

### 25.1. Những placeholder thường dùng

| Placeholder | Ý nghĩa |
|---|---|
| `%s` | Chèn giá trị như chuỗi |
| `%I` | Quote giá trị như **SQL identifier** |
| `%L` | Quote giá trị như **SQL literal** |
| `%%` | Ký tự phần trăm literal |

Ví dụ:

~~~sql
SELECT
    format('Hello %s', 'An') AS normal_text,
    format('Column name: %I', 'order total') AS sql_identifier,
    format('Literal: %L', 'O''Reilly') AS sql_literal,
    format('Progress: 90%%') AS literal_percent;
~~~

### 25.2. %I và %L phục vụ SQL động có kiểm soát

Giả sử cần sinh một câu lệnh minh họa:

~~~sql
SELECT format(
    'SELECT %I FROM %I WHERE %I = %L',
    'display_name',
    'customers',
    'customer_id',
    'CUST-001'
) AS sql_preview;
~~~

`%I` quote tên bảng/cột đúng cú pháp identifier. `%L` quote dữ liệu theo cú pháp literal.

**Quan trọng:** Việc có hàm format không có nghĩa mọi SQL động đều an toàn theo nghiệp vụ. Tên bảng/cột phải được phép theo whitelist; dữ liệu người dùng trong truy vấn ứng dụng nên truyền bằng **typed parameters** thay vì nối SQL văn bản.

### 25.3. %s không thay thế %I hoặc %L

Sai về ngữ cảnh identifier/literal:

~~~sql
-- Chỉ minh họa ý tưởng nguy hiểm:
-- format('SELECT %s FROM customers', user_supplied_column)
~~~

`%s` không tự quote tên cột hay literal theo quy tắc SQL. Trong mã PL/pgSQL có SQL động, dùng `format('%I', identifier)` và `EXECUTE ... USING</BT> cho các giá trị parameter ở chỗ thích hợp.

### 25.4. Không dùng FORMAT để xử lý tất cả nhu cầu giao diện

Định dạng tiền tệ, số hoặc ngày có yêu cầu locale riêng. `format()</BT> tiện để ghép mẫu, nhưng không phải giải pháp đầy đủ cho i18n, pluralization hoặc định dạng tiền theo từng quốc gia. Tầng ứng dụng có thể thích hợp hơn cho thông điệp hiển thị người dùng.

## 26. REPEAT, LPAD và RPAD

Một số hàm tạo chuỗi với độ dài có kiểm soát.

### 26.1. REPEAT

~~~sql
SELECT
    repeat('*', 5) AS five_stars,
    repeat('ab', 3) AS repeated_pair;
~~~

Kết quả:

~~~text
*****
ababab
~~~

Không tạo chuỗi cực lớn theo dữ liệu người dùng không được giới hạn, vì có thể tiêu tốn bộ nhớ.

### 26.2. LPAD

~~~sql
SELECT
    lpad('7', 3, '0') AS padded_number,
    lpad('42', 5, '0') AS padded_code;
~~~

Kết quả: `007` và `00042`.

### 26.3. RPAD

~~~sql
SELECT
    rpad('AB', 5, '.') AS right_padded;
~~~

Kết quả: `AB...`.

### 26.4. LPAD/RPAD có thể cắt bớt chuỗi

Nếu độ dài mong muốn **ngắn hơn** giá trị đầu vào, hàm padding có thể **rút ngắn** chuỗi thay vì báo lỗi độ dài.

~~~sql
SELECT lpad('123456', 4, '0') AS shortened;
~~~

Không dùng `lpad</BT>/`rpad</BT> thay cho validation độ dài của mã quan trọng. Nếu mã dài quá giới hạn, ứng dụng/schema thường nên từ chối thay vì âm thầm cắt ký tự.

## 27. OVERLAY: thay một vùng theo vị trí

PostgreSQL hỗ trợ cú pháp:

~~~sql
SELECT overlay(
    'PostgreSQL'
    PLACING 'gres'
    FROM 5
    FOR 3
) AS example;
~~~

Biểu thức minh họa việc thay một đoạn ở vị trí được chỉ định. Có thể dùng `overlay()</BT> khi nội dung có định dạng vị trí cố định.

### 27.1. Cần phân biệt với replace

- `replace()</BT>: thay theo chuỗi con xuất hiện.
- `overlay()</BT>: thay theo **vị trí ký tự** được chỉ định.

Với dữ liệu có cấu trúc thay đổi, chỉ số vị trí dễ sai. Không dùng overlay để sửa nội dung tùy ý khi cần một parser theo định dạng.

## 28. Đếm và tìm khoảng trắng bất thường

Một công việc thực tế: xác định những hàng cần làm sạch mà chưa sửa dữ liệu.

### 28.1. So sánh chuỗi với bản đã trim

~~~sql
SELECT
    raw_value,
    btrim(raw_value) AS trimmed_value
FROM (
    VALUES
        ('  An  '::text),
        ('Bình'::text),
        (E'\tCường\t'::text)
) AS t(raw_value)
WHERE raw_value IS DISTINCT FROM btrim(raw_value);
~~~

Câu SQL này phát hiện trường hợp khác biệt sau khi `btrim</BT> mặc định. Nhưng tab có thể chưa bị bỏ; phải chọn tập ký tự đúng mục tiêu.

### 28.2. Phát hiện dấu cách ở hai đầu

~~~sql
SELECT raw_value
FROM (
    VALUES
        ('  An'::text),
        ('Bình'::text),
        ('Cường  '::text)
) AS t(raw_value)
WHERE raw_value <> btrim(raw_value);
~~~

Kết quả gồm các hàng bị thay đổi khi trim.

### 28.3. Phát hiện nhiều dấu trắng liên tiếp

~~~sql
SELECT raw_value
FROM (
    VALUES
        ('Nguyễn   Văn An'::text),
        ('Trần Thị Bình'::text)
) AS t(raw_value)
WHERE raw_value ~ '[[:space:]]{2,}';
~~~

Regex ở đây tìm dãy ít nhất hai ký tự thuộc lớp whitespace được nhận diện. Khi dùng trên dữ liệu Unicode thực, cần kiểm tra chính sách ký tự.

### 28.4. Quan sát độ dài trước/sau

~~~sql
SELECT
    raw_value,
    char_length(raw_value) AS length_before,
    char_length(btrim(raw_value)) AS length_after
FROM (
    VALUES
        ('  An  '::text),
        ('Bình'::text)
) AS t(raw_value);
~~~

Kiểu đo độ dài có thể giúp phát hiện dữ liệu có space ẩn trong khi công cụ SQL hiển thị không rõ.

## 29. Lab PostgreSQL: lưu dữ liệu chuỗi chưa chuẩn hóa

Thực hành trong **database PostgreSQL thử nghiệm** có quyền tạo schema. Không chạy trên production. Nếu schema `string_lab</BT> đã tồn tại, dùng database hoặc tên schema khác thay vì xóa dữ liệu có sẵn.

### 29.1. Tạo schema

~~~sql
CREATE SCHEMA string_lab;
~~~

### 29.2. Tạo bảng liên hệ

~~~sql
CREATE TABLE string_lab.contacts (
    contact_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    display_name TEXT,
    email_raw TEXT,
    city TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
~~~

Ở đây, `display_name</BT> và `email_raw</BT> cố ý cho phép NULL/rỗng để quan sát xử lý chuỗi. Một bảng production có thể cần constraints chặt hơn, nhưng không nên tự sửa dữ liệu người dùng ngay khi nhập nếu chưa xác định quy tắc.

### 29.3. Thêm dữ liệu mẫu

~~~sql
INSERT INTO string_lab.contacts (
    display_name,
    email_raw,
    city
)
VALUES
    ('  Nguyễn Văn An  ', '  An@Example.COM  ', 'Hà Nội'),
    (E'\tTrần   Thị Bình  \t', 'binh@example.com  ', 'Đà Nẵng'),
    ('', '  ', NULL),
    (NULL, NULL, 'Huế');
~~~

Dữ liệu cố ý chứa:

- Space đầu/cuối.
- Tab ở biên.
- Nhiều dấu cách giữa các từ.
- Email có chữ hoa.
- Chuỗi rỗng.
- Giá trị NULL.

### 29.4. Xem dữ liệu gốc và độ dài

~~~sql
SELECT
    contact_id,
    display_name,
    char_length(display_name) AS name_length,
    octet_length(display_name) AS name_bytes,
    email_raw,
    city
FROM string_lab.contacts
ORDER BY contact_id;
~~~

Với hàng NULL, các hàm đo độ dài của biểu thức NULL thường trả NULL. Với tiếng Việt, số byte có thể lớn hơn số ký tự.

### 29.5. Chỉ trim dấu cách thông thường

~~~sql
SELECT
    contact_id,
    btrim(display_name) AS trim_spaces_only,
    btrim(email_raw) AS clean_email_edges
FROM string_lab.contacts
ORDER BY contact_id;
~~~

Hàng tên có tab đầu/cuối có thể vẫn giữ tab vì `btrim()</BT> mặc định không loại mọi whitespace.

### 29.6. Trim space, tab, CR, LF

~~~sql
SELECT
    contact_id,
    btrim(
        display_name,
        E' \t\r\n'
    ) AS trimmed_edges
FROM string_lab.contacts
ORDER BY contact_id;
~~~

Câu này chỉ loại những ký tự thuộc tập nêu rõ ở **hai đầu** chuỗi. Nhiều dấu cách giữa “Trần”, “Thị”, “Bình” vẫn còn.

### 29.7. Chuẩn hóa tên một dòng

~~~sql
SELECT
    contact_id,
    NULLIF(
        btrim(
            regexp_replace(
                display_name,
                '[[:space:]]+',
                ' ',
                'g'
            )
        ),
        ''
    ) AS normalized_name
FROM string_lab.contacts
ORDER BY contact_id;
~~~

Mục tiêu của ví dụ:

- Gộp các chuỗi whitespace được regex nhận diện.
- Bỏ space ngoài biên.
- Biến chuỗi rỗng sau chuẩn hóa thành NULL.

Đây là **biểu thức đọc thử**, chưa UPDATE dữ liệu gốc.

### 29.8. Chuẩn hóa khóa email đơn giản

~~~sql
SELECT
    contact_id,
    email_raw,
    lower(
        NULLIF(btrim(email_raw), '')
    ) AS email_key
FROM string_lab.contacts
ORDER BY contact_id;
~~~

Hàng đầu có khóa `an@example.com`, hàng thứ hai là `binh@example.com`, các hàng rỗng/NULL có thể cho khóa NULL.

Đây là ví dụ normalization theo chính sách đơn giản, không phải bộ xác minh quyền sở hữu email hay một thuật toán canonicalization hoàn chỉnh cho mọi hệ thống thư điện tử.

### 29.9. Tạo nhãn liên hệ có phần tùy chọn

~~~sql
SELECT
    contact_id,
    NULLIF(
        concat_ws(
            ' | ',
            NULLIF(
                btrim(
                    regexp_replace(
                        display_name,
                        '[[:space:]]+',
                        ' ',
                        'g'
                    )
                ),
                ''
            ),
            NULLIF(btrim(city), '')
        ),
        ''
    ) AS contact_label
FROM string_lab.contacts
ORDER BY contact_id;
~~~

Nhãn có thể là:

~~~text
Nguyễn Văn An | Hà Nội
Trần Thị Bình | Đà Nẵng
NULL
Huế
~~~

Hàng thứ ba không có thành phần có ý nghĩa nên cuối cùng trả NULL. Hàng thứ tư có thành phố nhưng thiếu tên, nên nhãn chỉ còn `Huế`.

Nếu nghiệp vụ **bắt buộc có tên khách hàng**, việc concat bỏ qua NULL không thay validation; một hàng chỉ có thành phố có thể là dữ liệu thiếu cần xử lý.

## 30. Lab: tìm kiếm với khóa chuẩn hóa

Một nhu cầu phổ biến: tìm email mà không phân biệt chữ hoa/thường hoặc space ngoài biên theo chính sách đơn giản.

~~~sql
SELECT
    contact_id,
    email_raw
FROM string_lab.contacts
WHERE lower(btrim(email_raw))
      = lower(btrim(' an@example.com '));
~~~

Kết quả dự kiến là liên hệ của An.

### 30.1. Hàm trong WHERE và index

Nếu có rất nhiều liên hệ, truy vấn:

~~~sql
WHERE lower(btrim(email_raw)) = 'an@example.com'
~~~

áp dụng một biểu thức trên cột. B-tree index thông thường trên `email_raw` không nhất thiết giúp điều kiện biểu thức này hiệu quả tương tự điều kiện so sánh trực tiếp với cột.

PostgreSQL hỗ trợ **expression index**:

~~~sql
CREATE INDEX idx_contacts_normalized_email
ON string_lab.contacts (lower(btrim(email_raw)));
~~~

Sau đó:

~~~sql
SELECT
    contact_id,
    email_raw
FROM string_lab.contacts
WHERE lower(btrim(email_raw)) = 'an@example.com';
~~~

Planner có thể cân nhắc index phù hợp tùy kích thước bảng, thống kê và độ chọn lọc. Với bảng lab chỉ có vài hàng, sequential scan vẫn là lựa chọn bình thường.

### 30.2. Expression index cho UNIQUE khi nghiệp vụ cho phép

Nếu email canonical phải duy nhất với một phạm vi xác định, có thể dùng unique index trên biểu thức sau khi **đã quyết định quy tắc và làm sạch dữ liệu trùng**.

Ví dụ cú pháp minh họa:

~~~sql
CREATE UNIQUE INDEX uq_contacts_email_key
ON string_lab.contacts (lower(btrim(email_raw)))
WHERE NULLIF(btrim(email_raw), '') IS NOT NULL;
~~~

Với dữ liệu demo hiện tại, mỗi email có ý nghĩa là khác nhau; các hàng rỗng/NULL nằm ngoài predicate.

**Không tự tạo unique index trên production trước khi khảo sát duplicates, chính sách email, tenant scope và soft deletion.** Khi ứng dụng thật có nhiều tenant, có thể cần thêm `tenant_id` vào khóa duy nhất.

### 30.3. Lower/trim cần chính sách nhất quán ở lúc ghi và lúc đọc

Nếu backend chuẩn hóa bằng một thư viện Unicode khác trong khi database dùng `lower(btrim())`, hai lớp có thể ra khóa khác nhau. Cần chọn một hợp đồng canonicalization có phiên bản và kiểm thử.

## 31. Lab: ghép danh sách sản phẩm bằng STRING_AGG

Tạo bảng:

~~~sql
CREATE TABLE string_lab.products (
    product_id INTEGER PRIMARY KEY,
    category TEXT NOT NULL,
    product_name TEXT NOT NULL,
    tags TEXT[]
);

INSERT INTO string_lab.products (
    product_id,
    category,
    product_name,
    tags
)
VALUES
    (1, 'Book', 'PostgreSQL căn bản', ARRAY['sql', 'database']),
    (2, 'Book', 'SQL thực hành', ARRAY['sql', 'practice']),
    (3, 'Toy',  'Xếp hình', ARRAY['gift', 'creative']),
    (4, 'Toy',  'Bộ chữ cái', ARRAY['gift', 'education']),
    (5, 'Book', 'Tối ưu truy vấn', ARRAY[]::TEXT[]);
~~~

### 31.1. Danh sách sản phẩm theo danh mục

~~~sql
SELECT
    category,
    COUNT(*) AS product_count,
    string_agg(
        product_name,
        ' | ' ORDER BY product_name
    ) AS product_names
FROM string_lab.products
GROUP BY category
ORDER BY category;
~~~

Nhờ `ORDER BY product_name` bên trong `string_agg</BT>, thứ tự chuỗi nối có ý nghĩa được xác định theo collation đang áp dụng.

### 31.2. Danh sách tag duy nhất theo danh mục

~~~sql
SELECT
    p.category,
    string_agg(
        DISTINCT t.tag,
        ', ' ORDER BY t.tag
    ) AS tags
FROM string_lab.products AS p
CROSS JOIN LATERAL unnest(p.tags) AS t(tag)
GROUP BY p.category
ORDER BY p.category;
~~~

`unnest(p.tags)` tạo một hàng cho mỗi tag. `string_agg(DISTINCT ...)` loại tag trùng trong category.

### 31.3. CROSS JOIN LATERAL có thể bỏ sản phẩm không tag

Sản phẩm `Tối ưu truy vấn` có mảng tag rỗng nên không xuất hiện trong kết quả `CROSS JOIN LATERAL unnest(tags)` ở cấp dòng.

Nếu cần giữ cả sản phẩm không tag:

~~~sql
SELECT
    p.product_id,
    p.product_name,
    t.tag
FROM string_lab.products AS p
LEFT JOIN LATERAL unnest(p.tags) AS t(tag)
    ON TRUE
ORDER BY p.product_id, t.tag NULLS LAST;
~~~

Mỗi sản phẩm vẫn có ít nhất một hàng kết quả; sản phẩm không tag có `tag IS NULL`.

### 31.4. Đừng tổng hợp một danh sách quá lớn nếu client cần cấu trúc

Với hàng triệu sản phẩm, một chuỗi `string_agg</BT> có thể tốn tài nguyên và khó sử dụng. Nếu API cần một danh sách có trường riêng, dùng JSON/array có cấu trúc hoặc phân trang có thể phù hợp hơn việc nối thành văn bản.

## 32. LIKE, ILIKE và tìm kiếm chuỗi

Dù chủ đề trọng tâm là **hàm chuỗi/nối chuỗi/xử lý khoảng trắng**, các phép so khớp thường đi kèm chuẩn hóa.

### 32.1. LIKE

~~~sql
SELECT
    'PostgreSQL' LIKE 'Post%' AS starts_with_post,
    'PostgreSQL' LIKE '%SQL' AS ends_with_sql;
~~~

`%` khớp với chuỗi ký tự bất kỳ (kể cả rỗng), `_` khớp một ký tự theo semantics của LIKE.

### 32.2. ILIKE

PostgreSQL cung cấp `ILIKE` để so khớp mẫu không phân biệt chữ hoa/thường theo quy tắc locale/collation liên quan.

~~~sql
SELECT
    'PostgreSQL' ILIKE 'post%' AS case_insensitive_match;
~~~

Dùng `ILIKE` khi yêu cầu tìm kiếm kiểu pattern, không cần biến cả cột thành chữ thường chỉ để kiểm tra một mẫu.

### 32.3. starts_with

~~~sql
SELECT starts_with('PostgreSQL', 'Post') AS has_prefix;
~~~

Hàm trả boolean. Nó khác với việc dùng `LIKE 'Post%'</BT> khi cần biết một prefix literal, đặc biệt nếu prefix từ đầu vào có thể chứa ký tự wildcard như `%` hoặc `_`.

### 32.4. ILIKE không tự bỏ dấu

So khớp không phân biệt hoa/thường không đồng nghĩa với bỏ dấu tiếng Việt. Nếu muốn tìm “Da Nang” tương ứng “Đà Nẵng”, cần một chính sách search chuyên biệt, có thể dựa trên extension `unaccent`, collation thích hợp hoặc search engine.

## 33. Extension UNACCENT: khi cần tìm kiếm không dấu

PostgreSQL có module mở rộng `unaccent`, nếu cài đặt và quyền cho phép.

Trên **database thử nghiệm**, người có quyền phù hợp có thể chạy:

~~~sql
CREATE EXTENSION IF NOT EXISTS unaccent;
~~~

Ví dụ:

~~~sql
SELECT unaccent('Đà Nẵng') AS without_accents;
~~~

Mục đích là chuyển văn bản có dấu sang một dạng thuận tiện hơn cho một số cách tìm kiếm.

### 33.1. Không coi unaccent là chuẩn hóa an toàn cho mọi dữ liệu

“Không dấu” có thể làm nhiều từ/tên khác nhau trở nên trùng. Đây có thể là hành vi mong muốn cho search, nhưng **không nên tự ghi đè họ tên thật, địa chỉ hoặc pháp danh** bằng bản bỏ dấu.

Nếu cần tìm kiếm không dấu:

~~~text
Dữ liệu hiển thị: "Đà Nẵng"
Khóa tìm kiếm:   dạng đã xử lý theo policy
~~~

Hãy giữ dữ liệu gốc và tách chính sách search key khỏi display value.

### 33.2. Extension và quyền triển khai

`CREATE EXTENSION` có thể yêu cầu quyền phù hợp và module được cung cấp trong bản cài PostgreSQL. Không dùng nó nếu môi trường không cho phép hoặc chưa có kế hoạch vận hành. Trong hệ thống lớn, cần đánh giá ảnh hưởng tới index và cách truy vấn thực thi.

## 34. Collation ảnh hưởng so sánh và sắp xếp

Chuỗi không chỉ là byte; kết quả so sánh và sắp xếp có thể chịu ảnh hưởng **collation**.

~~~sql
SELECT
    product_name
FROM string_lab.products
ORDER BY product_name;
~~~

Thứ tự phụ thuộc quy tắc collation áp dụng cho biểu thức. Không nên mặc định mọi database sẽ sắp tên tiếng Việt theo một quy tắc giống nhau.

### 34.1. Phân biệt ba yêu cầu

1. **Byte equality:** hai chuỗi có biểu diễn byte giống nhau không?
2. **Search equivalence:** hai chuỗi được xem là khớp theo quy tắc tìm kiếm không?
3. **Display order:** sắp xếp theo chữ cái/locale nào?

Các yêu cầu này có thể cần công cụ khác nhau. `lower()</BT>, Unicode normalization, collation và unaccent không hoàn toàn thay thế lẫn nhau.

### 34.2. Collation và uniqueness

Nếu tạo unique index trên khóa chuỗi, ngữ nghĩa so khớp phải phù hợp hợp đồng sản phẩm. Một collation không xác định đúng có thể khiến hai chuỗi “trông giống nhau” vẫn được coi khác hoặc ngược lại.

Không thay collation của dữ liệu production chỉ để thay đổi kết quả sort mà chưa xem tác động đến index/unique constraints.

## 35. Làm sạch dữ liệu trong SELECT hay UPDATE?

Có hai cách:

### 35.1. Làm sạch khi đọc

~~~sql
SELECT
    contact_id,
    NULLIF(btrim(display_name), '') AS display_name_clean
FROM string_lab.contacts;
~~~

Ưu điểm:

- Không thay đổi giá trị gốc.
- Có thể so sánh trước/sau.
- Phù hợp khi đang kiểm tra rule.

Nhược điểm:

- Mỗi query cần dùng biểu thức nhất quán.
- Tìm kiếm/index trên giá trị gốc có thể không khớp với khóa làm sạch.
- Nhiều API có thể tự định nghĩa biểu thức khác nhau.

### 35.2. Chuẩn hóa khi ghi

Ứng dụng có thể canonicalize đầu vào trước INSERT/UPDATE hoặc duy trì cột khóa chuẩn hóa theo quy tắc đã được thống nhất.

Ưu điểm:

- Dữ liệu được lưu nhất quán hơn theo hợp đồng.
- Truy vấn đọc đơn giản hơn.
- Có thể đặt constraint/unique trực tiếp lên khóa chuẩn hóa.

Rủi ro:

- Có thể mất nguyên dạng người dùng nhập nếu ghi đè.
- Quy tắc normalize thay đổi theo phiên bản.
- Không thể dễ dàng hoàn tác nếu đã xóa ký tự có ý nghĩa.

### 35.3. Dữ liệu raw và normalized key

Một thiết kế có thể lưu hai thành phần:

~~~text
display_name_raw    = chuỗi người dùng xác nhận
display_name_search = khóa phục vụ tìm kiếm
~~~

Nhưng nếu lưu cả hai, cần cơ chế đồng bộ, migration và test bảo đảm search key được tạo từ raw theo chính sách hiện tại.

Không tạo một cột chuẩn hóa dư thừa chỉ vì có thể; cân nhắc expression index hoặc generated column phù hợp với phiên bản PostgreSQL và tính chất của hàm được sử dụng.

## 36. Không gộp khoảng trắng trong mọi loại trường

Một chính sách “gộp nhiều space thành một” có vẻ tốt nhưng có thể gây hại:

### 36.1. Tên riêng

Có thể gộp lỗi nhập `'Nguyễn   Văn An'` thành `'Nguyễn Văn An'`, nhưng phải cân nhắc tên trong ngôn ngữ khác, biệt danh hoặc biểu diễn có dấu kết hợp.

### 36.2. Mã định danh

`'AB  123'` có thể khác `'AB 123'` nếu mã đã được phát hành với khoảng trắng có ý nghĩa. Không được thay đổi mã trên hợp đồng/invoice chỉ để đẹp.

### 36.3. Ghi chú nhiều dòng

~~~text
Dòng 1

Dòng 3
~~~

Hai dấu xuống dòng có thể phân đoạn nội dung. Đưa mọi whitespace về một space sẽ xóa cấu trúc.

### 36.4. Văn bản pháp lý hoặc tài liệu ký số

Một sự thay đổi ký tự, kể cả dấu cách, có thể làm thay đổi hash/chữ ký. Nếu cần so sánh bản ký số, **không chuẩn hóa nội dung đã được ký** trước khi xác minh.

### 36.5. Chuỗi bảo mật

Không nên tự trim/mutate mật khẩu, token hay secret theo cùng quy tắc như tên hiển thị. Khoảng trắng có thể là ký tự hợp lệ của bí mật. Việc thay đổi trước khi xác thực có thể làm sai hợp đồng bảo mật.

## 37. Nối chuỗi trong SQL khác cấu trúc dữ liệu

Một nhãn:

~~~sql
SELECT concat_ws(
    ' | ',
    'ORD-001',
    'An',
    'Đã giao'
) AS order_label;
~~~

thích hợp để hiển thị. Nhưng nếu API cần phân tích lại nó:

~~~text
ORD-001 | An | Đã giao
~~~

sẽ có vấn đề nếu tên hoặc trạng thái chứa dấu `|`.

### 37.1. Đừng dùng nhãn ghép làm định dạng trao đổi có cấu trúc

Tốt hơn là trả các trường riêng:

~~~json
{
  "orderCode": "ORD-001",
  "customerName": "An",
  "status": "delivered"
}
~~~

Tầng hiển thị có thể tạo chuỗi theo ngôn ngữ người dùng và định dạng giao diện phù hợp.

### 37.2. Khi cần kết quả tổng hợp có cấu trúc

PostgreSQL hỗ trợ aggregate như `json_agg()</BT>, `jsonb_agg()</BT> hoặc `array_agg()</BT>. Nếu một report thực sự cần danh sách để máy xử lý, những kiểu có cấu trúc thường thích hợp hơn `string_agg()</BT>.

### 37.3. Khi nào dùng string_agg?

- Chuỗi mô tả cho báo cáo văn bản.
- Danh sách nhãn ngắn trong một cột hiển thị.
- Export một trường định dạng theo hợp đồng rõ.
- Hiển thị tags ngắn trên trang danh sách.

Với danh sách có thể rất dài, cần chiến lược giới hạn kích thước hoặc trả cấu trúc/phân trang.

## 38. Làm việc với SQL động và bảo mật

Khi viết ứng dụng, nối chuỗi để tạo SQL từ dữ liệu người dùng có thể gây **SQL injection**.

Sai:

~~~java
String sql = "SELECT * FROM customers WHERE email = '"
           + emailFromUser + "'";
~~~

Nếu dữ liệu có dấu nháy đơn hoặc nội dung có chủ đích xấu, câu SQL có thể bị hỏng hoặc thay đổi ý nghĩa.

### 38.1. Dùng PreparedStatement với tham số

~~~java
String sql = """
    SELECT contact_id, display_name, email_raw
    FROM string_lab.contacts
    WHERE lower(btrim(email_raw)) = lower(btrim(?))
    """;

try (var statement = connection.prepareStatement(sql)) {
    statement.setString(1, emailFromUser);
    try (var rs = statement.executeQuery()) {
        while (rs.next()) {
            long id = rs.getLong("contact_id");
            String name = rs.getString("display_name");
            // Xử lý kết quả phù hợp.
        }
    }
}
~~~

Đây là đoạn minh họa Java/JDBC giả định `connection` đã được khởi tạo và `emailFromUser` là một chuỗi nhận từ API.

`PreparedStatement` giúp truyền giá trị như dữ liệu, không ghép nội dung đó thành cú pháp SQL.

### 38.2. Identifier không phải parameter dữ liệu

Không thể dùng placeholder `?</BT> thay trực tiếp tên bảng hoặc cột trong mọi vị trí SQL. Nếu thực sự cần SQL động theo tên cột:

- Dùng whitelist các tên cột được phép.
- Xây SQL tại lớp đáng tin.
- Quote identifier đúng cách khi dùng SQL động trong PostgreSQL/PL/pgSQL.
- Không lấy một identifier tùy ý từ người dùng rồi nối bằng `%s`.

### 38.3. TRIM hoặc REPLACE không chống injection

Xóa dấu `'` khỏi giá trị không phải phương pháp bảo mật, và còn có thể làm hỏng tên người như `O'Reilly`. Cách đúng là parameterized query, không thay đổi dữ liệu để né cú pháp SQL.

## 39. Regex và hiệu năng truy vấn

Các biểu thức xử lý chuỗi có chi phí CPU và có thể ảnh hưởng việc sử dụng index.

### 39.1. Hàm trên cột trong WHERE

~~~sql
SELECT
    contact_id,
    display_name
FROM string_lab.contacts
WHERE lower(btrim(email_raw)) = 'an@example.com';
~~~

Nếu bảng lớn, PostgreSQL có thể cần tính biểu thức trên nhiều hàng nếu không có index phù hợp.

Expression index:

~~~sql
CREATE INDEX idx_contacts_email_search
ON string_lab.contacts (lower(btrim(email_raw)));
~~~

Trong lab đã có thể tạo index tương tự ở phần trước. Không tạo nhiều index trùng lặp trên production chỉ vì xuất hiện ở các ví dụ khác nhau.

### 39.2. B-tree không giúp mọi LIKE/ILIKE

Điều kiện tìm kiếm `LIKE 'abc%'` có thể có những khả năng tối ưu nhất định tùy collation và operator class/index, nhưng `ILIKE '%abc%'` hoặc regex chứa wildcard đầu chuỗi thường không tự tận dụng B-tree thông thường như equality.

PostgreSQL có extension **`pg_trgm`** hỗ trợ chỉ mục trigram cho một số mẫu tìm kiếm:

~~~sql
-- Chỉ khi môi trường thử nghiệm cho phép và có nhu cầu:
-- CREATE EXTENSION IF NOT EXISTS pg_trgm;
-- CREATE INDEX idx_contacts_name_trgm
-- ON string_lab.contacts
-- USING gin (display_name gin_trgm_ops);
~~~

Không mặc định tạo trigram index cho mọi cột text. Index bổ sung tốn dung lượng và chi phí bảo trì khi INSERT/UPDATE; cần đo workload.

### 39.3. Dùng EXPLAIN

~~~sql
EXPLAIN
SELECT contact_id
FROM string_lab.contacts
WHERE lower(btrim(email_raw)) = 'an@example.com';
~~~

`EXPLAIN` cho kế hoạch dự kiến. Khi dữ liệu thử nghiệm đủ an toàn:

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT contact_id
FROM string_lab.contacts
WHERE lower(btrim(email_raw)) = 'an@example.com';
~~~

`EXPLAIN ANALYZE` thực sự chạy SELECT để đo thời gian/hàng. Với DML, nó cũng thực thi thao tác ghi nếu không rollback phù hợp.

### 39.4. Chuẩn hóa một lần hay mỗi lần đọc?

Nếu dữ liệu chỉ vài trăm hàng, viết `lower(btrim())` trực tiếp có thể đủ. Với bảng lớn và truy vấn lặp nhiều, expression index hoặc thiết kế search key có thể hữu ích. Hãy xem tính đúng trước, đo hiệu năng sau và tránh chuẩn hóa sai quy tắc chỉ vì muốn tận dụng index.

## 40. PostgreSQL regex không thay bộ parse chuyên dụng

Một số người dùng regex để parse:

- Email theo mọi trường hợp hợp lệ.
- Địa chỉ bưu chính quốc tế.
- HTML.
- JSON.
- CSV có dấu nháy và ký tự escape.
- Chuỗi có cấu trúc lồng nhau.

Đây là những định dạng có grammar hoặc quy tắc phức tạp. Regex có thể giúp **tìm mẫu đơn giản** hoặc **chuẩn hóa một trường đã biết**, nhưng không nên tự thay một parser chuyên dụng cho mọi format.

### 40.1. Ví dụ với CSV

~~~text
"Nguyễn, Văn An",Hà Nội
~~~

Nếu chỉ `split_part(line, ',', 1)`, phần đầu sẽ là một chuỗi không hoàn chỉnh. CSV cho phép dấu phẩy bên trong field được quote, nên cần CSV parser hoặc `COPY ... CSV` phù hợp.

### 40.2. Ví dụ với JSON

~~~json
{"fullName":"Nguyễn Văn An","city":"Hà Nội"}
~~~

Không cần cắt chuỗi bằng dấu `:` và `,` để lấy thuộc tính. PostgreSQL có kiểu `json/jsonb` và các toán tử truy cập cấu trúc, nếu dữ liệu thật sự có format JSON.

## 41. Chuẩn hóa dữ liệu để đối chiếu và deduplication

Giả sử database có các tên:

~~~text
" Nguyễn Văn An"
"Nguyễn Văn An "
"Nguyễn   Văn An"
"NGUYỄN VĂN AN"
~~~

Có thể muốn coi chúng tương tự khi tìm kiếm, nhưng **không có nghĩa chắc chắn là cùng một người**.

### 41.1. Tạo comparison key để gợi ý trùng

~~~sql
SELECT
    display_name,
    lower(
        btrim(
            regexp_replace(
                display_name,
                '[[:space:]]+',
                ' ',
                'g'
            )
        )
    ) AS comparison_key
FROM string_lab.contacts;
~~~

Đây là khóa so sánh **đơn giản**, không phải định danh người thật. Hai người có cùng tên vẫn có thể là hai người khác nhau.

### 41.2. Dedupe cần nhiều trường và quy tắc

Khi phát hiện trùng khách hàng, có thể cần so thêm:

- Mã khách hệ thống.
- Email đã xác minh.
- Số điện thoại đã xác minh.
- Nguồn dữ liệu.
- Tenant.
- Lịch sử merge.
- Quy tắc đồng ý/quyền xử lý dữ liệu.

Không tự `DELETE</BT> bản ghi chỉ vì `lower(btrim(name))` bằng nhau.

### 41.3. Unicode normalization và case sensitivity

Nếu phải đồng bộ dữ liệu giữa Java, PostgreSQL và một search service, cần phiên bản hóa quy tắc normalization/collation để các lớp cùng hiểu equivalence. Một index unique chỉ đúng theo semantics của biểu thức/collation đang dùng ở database.

## 42. Các lỗi thường gặp về nối chuỗi

### 42.1. Dùng || với trường optional

~~~sql
SELECT 'An' || ' - ' || NULL::text;
~~~

Kết quả NULL. Nếu cần bỏ qua thành phần thiếu, dùng `concat_ws</BT> và quy tắc `NULLIF</BT> phù hợp.

### 42.2. Nghĩ CONCAT tự thêm space

~~~sql
SELECT concat('Nguyễn', 'Văn', 'An');
~~~

Kết quả dính liền. Cần chèn separator hoặc dùng `concat_ws(' ', ...)`.

### 42.3. Nghĩ CONCAT_WS bỏ chuỗi rỗng

`concat_ws('-', 'A', '', 'B')` vẫn có một phần tử rỗng và có thể tạo `A--B`. Muốn bỏ, dùng `NULLIF(btrim(value),'')`.

### 42.4. Nghĩ TRIM xóa nhiều space giữa các từ

`btrim('  A   B  ')` trả `A   B`. Muốn gộp nội bộ, dùng quy tắc regex phù hợp.

### 42.5. Nghĩ TRIM mặc định xóa tab và NBSP

Không. Phải biết tập ký tự được loại và quy tắc Unicode.

### 42.6. Nghĩ btrim(text, 'abc') xóa nguyên chuỗi 'abc'

Không. Nó loại bất kỳ ký tự `a`, `b`, `c` ở biên.

### 42.7. Nghĩ REPLACE hiểu regex

Không. `replace</BT> dùng chuỗi literal; regex có `regexp_replace</BT>.

### 42.8. Quên flag g trong regexp_replace

Có thể chỉ thay lần khớp đầu, để lại các cụm whitespace khác.

### 42.9. Dùng LENGTH để đo byte

`char_length</BT> đo ký tự; `octet_length</BT> đo byte.

### 42.10. Tưởng một grapheme luôn là một ký tự

Một chữ có dấu kết hợp có thể có nhiều code point; `char_length</BT> không phải bộ đếm grapheme hoàn chỉnh.

### 42.11. Dùng LOWER cho mọi tên và mã

Có thể làm mất kiểu viết hoa có ý nghĩa, gây sai mã định danh hoặc văn bản pháp lý.

### 42.12. Dùng INITCAP để sửa mọi tên riêng

Không có một quy tắc viết hoa chung cho mọi ngôn ngữ và biệt danh.

### 42.13. Lấy substring từ vị trí cố định mà không validate format

Có thể cắt sai mã không đúng cấu trúc hoặc bị đổi độ dài.

### 42.14. Dùng split_part cho dữ liệu CSV phức tạp

CSV có quote/escape; tách dấu phẩy thủ công có thể sai.

### 42.15. Không đặt ORDER BY trong STRING_AGG

Thứ tự nối chuỗi không được bảo đảm theo ý định.

### 42.16. Dùng DISTINCT để che dữ liệu trùng

Loại trùng có thể làm mất thông tin số lần xuất hiện; cần biết yêu cầu.

### 42.17. Coi string_agg trên tập rỗng là chuỗi rỗng

Aggregate này có thể trả NULL, khác với một số cách nối chuỗi trên cùng hàng.

### 42.18. Dùng %s để chèn tên bảng tùy ý vào SQL

`%s</BT> không quote identifier; phải whitelist và quote đúng khi làm SQL động.

### 42.19. Dùng REPLACE để “chống SQL injection”

Không. Dùng prepared statements, quyền tối thiểu và xử lý SQL động có kiểm soát.

### 42.20. Cho rằng expression index chắc chắn luôn được dùng

Planner dựa trên thống kê và chi phí. Với bảng nhỏ, sequential scan có thể tốt hơn.

### 42.21. Tưởng chuẩn hóa whitespace không bao giờ mất dữ liệu

Khoảng trắng có thể thuộc bí mật, định dạng nhiều dòng hoặc nội dung có ký số.

### 42.22. Dùng nhãn đã ghép làm dữ liệu nguồn để tách ngược

Dấu phân cách có thể xuất hiện trong thành phần gốc; nên lưu/trả dữ liệu có cấu trúc.

## 43. Bài tập thực hành

### Bài 1 — Nối chuỗi đơn giản

Viết SQL tạo `PostgreSQL` từ hai chuỗi `Postgre</BT> và `SQL`.

**Gợi ý:**

~~~sql
SELECT 'Postgre' || 'SQL';
~~~

### Bài 2 — Nối tên có khoảng trắng

Tạo `Nguyễn Văn An` từ ba chuỗi riêng.

**Gợi ý:**

~~~sql
SELECT concat_ws(' ', 'Nguyễn', 'Văn', 'An');
~~~

### Bài 3 — NULL trong ||

Dự đoán:

~~~sql
SELECT 'A' || NULL::text;
~~~

**Gợi ý:** NULL.

### Bài 4 — NULL trong CONCAT

Dự đoán:

~~~sql
SELECT concat('A', NULL::text, 'B');
~~~

**Gợi ý:** `AB`.

### Bài 5 — Chuỗi rỗng trong CONCAT_WS

Tại sao:

~~~sql
SELECT concat_ws('-', 'A', '', 'B');
~~~

có thể trả `A--B`?

**Gợi ý:** Chuỗi rỗng là thành phần không NULL.

### Bài 6 — Bỏ thành phần rỗng

Sửa bài 5 để chỉ trả `A-B` khi thành phần giữa rỗng.

**Gợi ý:**

~~~sql
SELECT concat_ws('-', 'A', NULLIF('', ''), 'B');
~~~

### Bài 7 — Trim hai đầu

~~~sql
SELECT btrim('   Hà Nội   ');
~~~

Kết quả?

**Gợi ý:** `Hà Nội`.

### Bài 8 — Trim trái và phải

Viết hai biểu thức chỉ bỏ space trái và chỉ bỏ space phải.

**Gợi ý:** `ltrim(text)</BT> và `rtrim(text)`.

### Bài 9 — Tập ký tự của BTRIM

Kết quả:

~~~sql
SELECT btrim('abcXYZcba', 'abc');
~~~

**Gợi ý:** `XYZ`, vì loại bất kỳ ký tự a/b/c ở biên.

### Bài 10 — Tab ở đầu

Vì sao `btrim(E'\tAn\t')` không có nghĩa chắc chắn đã loại tab?

**Gợi ý:** Trim mặc định chủ yếu là space; chỉ định `E' \t\n\r'` nếu đó là tập ký tự muốn bỏ.

### Bài 11 — NBSP

Viết SQL thay NBSP thành space thông thường.

~~~sql
SELECT replace('Hà' || chr(160) || 'Nội', chr(160), ' ');
~~~

### Bài 12 — Gộp nhiều space

Biến `'  Trần   Thị  Bình  '` thành `'Trần Thị Bình'`.

**Gợi ý:** Kết hợp `regexp_replace(..., '[[:space:]]+', ' ', 'g')` và `btrim()</BT>.

### Bài 13 — Độ dài tiếng Việt

Vì sao `char_length('Việt')` có thể nhỏ hơn `octet_length('Việt')`?

**Gợi ý:** Một ký tự Unicode có thể chiếm nhiều byte UTF-8.

### Bài 14 — Chuỗi rỗng hay NULL

Sự khác nhau giữa `''</BT> và `NULL</BT> là gì?

**Gợi ý:** Chuỗi rỗng là giá trị có độ dài 0; NULL biểu thị thiếu/chưa biết.

### Bài 15 — NULLIF sau trim

Dự đoán:

~~~sql
SELECT NULLIF(btrim('   '), '');
~~~

**Gợi ý:** NULL.

### Bài 16 — Chuẩn hóa khóa email

Viết biểu thức biến `'  An@Example.COM  '` thành dạng chữ thường không space biên.

**Gợi ý:**

~~~sql
SELECT lower(btrim('  An@Example.COM  '));
~~~

### Bài 17 — SUBSTRING

Lấy bốn ký tự đầu từ `PostgreSQL`.

~~~sql
SELECT substring('PostgreSQL' FROM 1 FOR 4);
~~~

### Bài 18 — LEFT và RIGHT

Lấy prefix `ORD` và serial `000123` từ mã `ORD-2026-000123`.

**Gợi ý:** `left(code,3)` và `right(code,6)`.

### Bài 19 — STRPOS

Tìm vị trí `gre` trong `PostgreSQL`.

**Gợi ý:** Vị trí 5.

### Bài 20 — REPLACE

Biến `a-b-c` thành `a/b/c`.

~~~sql
SELECT replace('a-b-c', '-', '/');
~~~

### Bài 21 — TRANSLATE

Dùng `translate</BT> đổi lần lượt `a,b,c` thành `x,y,z`.

**Gợi ý:**

~~~sql
SELECT translate('abc', 'abc', 'xyz');
~~~

### Bài 22 — REGEXP_REPLACE toàn chuỗi

Kết quả khác nhau giữa có và không có flag `'g'` ở mẫu `'A   B   C'`?

**Gợi ý:** Có `g` sẽ thay mọi nhóm whitespace được khớp.

### Bài 23 — SPLIT_PART

Lấy phần thứ hai của `BOOK|001|VN`.

~~~sql
SELECT split_part('BOOK|001|VN', '|', 2);
~~~

**Gợi ý:** `001`.

### Bài 24 — ARRAY_TO_STRING

Ghép mảng `{red,green,blue}` với separator `', '`.

**Gợi ý:**

~~~sql
SELECT array_to_string(
    ARRAY['red', 'green', 'blue'],
    ', '
);
~~~

### Bài 25 — STRING_AGG

Tạo danh sách tên sản phẩm theo category từ `string_lab.products`.

**Gợi ý:** `string_agg(product_name, ', ' ORDER BY product_name)</BT> với `GROUP BY category`.

### Bài 26 — STRING_AGG và NULL

Vì sao một hàng tag NULL không tạo `', NULL'` trong danh sách được ghép?

**Gợi ý:** `string_agg</BT> bỏ qua biểu thức giá trị NULL.

### Bài 27 — DISTINCT trong STRING_AGG

Nếu danh mục có tag sql, practice, sql và chỉ muốn danh sách tag khác nhau, dùng gì?

**Gợi ý:** `string_agg(DISTINCT tag, ', ' ORDER BY tag)`.

### Bài 28 — FORMAT

Khi tạo câu SQL động trong PL/pgSQL, placeholder nào dùng cho identifier và literal?

**Gợi ý:** `%I` và `%L`; giá trị dữ liệu ưu tiên `EXECUTE ... USING</BT> khi phù hợp.

### Bài 29 — LPAD

Biến mã `42` thành `00042`.

~~~sql
SELECT lpad('42', 5, '0');
~~~

### Bài 30 — Rủi ro cắt mã

Vì sao không được dùng `lpad('123456',4,'0')` như một phép kiểm tra độ dài hợp lệ?

**Gợi ý:** Hàm có thể rút ngắn chuỗi, làm mất ký tự mà không báo lỗi validation.

### Bài 31 — Index biểu thức

Truy vấn thường dùng:

~~~sql
WHERE lower(btrim(email_raw)) = 'an@example.com'
~~~

Hãy đề xuất một index phù hợp.

**Gợi ý:**

~~~sql
CREATE INDEX idx_contacts_email_key_example
ON string_lab.contacts (lower(btrim(email_raw)));
~~~

Nếu đã tạo index tương tự trong lab, không cần tạo thêm một index trùng lặp khi triển khai thật.

### Bài 32 — Bảo vệ SQL khỏi injection

Vì sao không được ghép `emailFromUser` vào SQL bằng `+` hoặc `||`?

**Gợi ý:** Dữ liệu có thể thay đổi cú pháp SQL; dùng PreparedStatement/parameterized query.

### Bài 33 — Chuỗi hiển thị khác dữ liệu cấu trúc

Vì sao không nên lưu `'ORD-001 | An | Đã giao'` làm nguồn chính rồi tách lại khi cần?

**Gợi ý:** Dấu phân cách có thể xuất hiện trong dữ liệu gốc và làm mất cấu trúc; lưu từng trường riêng.

### Bài 34 — Tên người và normalization

Có nên tự `initcap(lower(full_name))` và ghi đè toàn bộ tên khách không?

**Gợi ý:** Không mặc định. Quy tắc tên riêng/ngôn ngữ phức tạp; cần chính sách và khả năng bảo toàn dữ liệu gốc.

### Bài 35 — Tìm kiếm không dấu

`lower()</BT> có đảm bảo “Da Nang” khớp “Đà Nẵng” không?

**Gợi ý:** Không. Bỏ dấu là yêu cầu khác, có thể cần unaccent/collation/search layer.

## 44. Bảng ghi nhớ nhanh

| Nhu cầu | PostgreSQL |
|---|---|
| Nối hai chuỗi bắt buộc | `a || b` |
| Nối nhiều phần, bỏ qua NULL | `concat(a,b,c)` |
| Nối bằng dấu phân cách | `concat_ws(', ',a,b,c)` |
| Loại chuỗi rỗng khỏi concat_ws | `NULLIF(btrim(value),'')` |
| Bỏ space ở hai đầu | `trim(value)` hoặc `btrim(value)` |
| Bỏ space đầu trái | `ltrim(value)` |
| Bỏ space cuối phải | `rtrim(value)` |
| Bỏ ký tự theo tập đã chọn | `btrim(value, characters)` |
| Bỏ space/tab/newline ở biên | `btrim(value,E' \t\n\r')` |
| Gộp dãy whitespace nội bộ | `regexp_replace(value,'[[:space:]]+',' ','g')` |
| Thay NBSP thành space | `replace(value,chr(160),' ')` |
| Số ký tự | `char_length(value)` |
| Số byte | `octet_length(value)` |
| Độ dài bit | `bit_length(value)` |
| Chữ thường | `lower(value)` |
| Chữ hoa | `upper(value)` |
| Title case đơn giản | `initcap(value)` |
| Unicode NFC | `normalize(value,NFC)` |
| Cắt chuỗi | `substring(value FROM start FOR count)` |
| Lấy n ký tự đầu | `left(value,n)` |
| Lấy n ký tự cuối | `right(value,n)` |
| Vị trí chuỗi con | `strpos(value,substring)` |
| Thay chuỗi literal | `replace(value,from,to)` |
| Ánh xạ từng ký tự | `translate(value,from_chars,to_chars)` |
| Thay theo regex | `regexp_replace(value,pattern,replacement,'g')` |
| Lấy phần theo delimiter | `split_part(value,delimiter,n)` |
| Tách thành mảng | `string_to_array(value,delimiter)` |
| Ghép mảng | `array_to_string(array,delimiter)` |
| Ghép nhiều hàng | `string_agg(value,separator ORDER BY value)` |
| Ghép nhiều hàng không trùng | `string_agg(DISTINCT value,separator ORDER BY value)` |
| Tạo thông điệp theo mẫu | `format('Hello %s',value)` |
| Quote identifier trong SQL động | `format('%I',identifier)` |
| Quote literal trong SQL động | `format('%L',value)` |
| Đệm trái | `lpad(value,n,pad)` |
| Đệm phải | `rpad(value,n,pad)` |
| Lặp chuỗi | `repeat(value,n)` |
| Tìm prefix literal | `starts_with(value,prefix)` |
| Tìm kiếm pattern không phân biệt case | `ILIKE` |
| Index theo lower/trim | Expression index trên `lower(btrim(column))` |
| Truyền dữ liệu vào SQL an toàn | Typed parameters/PreparedStatement |

---

## Kết luận

PostgreSQL cung cấp một bộ công cụ phong phú để **nối chuỗi, biến đổi chuỗi và xử lý khoảng trắng**. Toán tử **`||`** nối trực tiếp nhưng có hành vi lan truyền `NULL`; **`concat()`** bỏ qua các thành phần NULL; **`concat_ws()`** thêm separator giữa các thành phần không NULL nhưng không tự bỏ chuỗi rỗng. Kết hợp **`NULLIF(btrim(value),'')`** giúp phân biệt các thành phần tùy chọn khi tạo nhãn hiển thị.

Nhóm **`trim/btrim/ltrim/rtrim`** xử lý ký tự ở biên, còn **`regexp_replace`** thích hợp khi cần thay các chuỗi whitespace nội bộ theo mẫu. Với tiếng Việt và Unicode, cần phân biệt **ký tự, byte, code point, ký tự nhìn thấy, NBSP và normalization**, không giả định mọi dấu trắng hoặc ký tự có dấu đều có cách lưu giống ASCII.

Các hàm **`substring`**, **`left/right`**, **`position/strpos`**, **`replace/translate`**, **`split_part`** và **`string_agg`** hỗ trợ nhiều nhu cầu xử lý chuỗi khác nhau, nhưng không thay thế schema, parser định dạng hay validation nghiệp vụ. Khi truy vấn bảng lớn, có thể dùng **expression index** cho khóa được chuẩn hóa; khi nhận dữ liệu người dùng, phải dùng **parameterized SQL** thay vì ghép chuỗi để tạo truy vấn.

Nguyên tắc cuối cùng là: **giữ nguyên dữ liệu có ý nghĩa, chỉ chuẩn hóa theo quy tắc đã được định nghĩa và luôn phân biệt chuỗi hiển thị với dữ liệu nguồn**. Làm được điều đó giúp PostgreSQL xử lý văn bản chính xác hơn, tránh lỗi NULL, khoảng trắng ẩn, mất ký tự Unicode và những sai lệch khó phát hiện trong tìm kiếm hoặc báo cáo.
