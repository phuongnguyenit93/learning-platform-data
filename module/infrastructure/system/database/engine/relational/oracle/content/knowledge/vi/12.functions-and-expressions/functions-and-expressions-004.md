# Nối chuỗi, padding và xử lý CHAR có khoảng trắng cuối trong Oracle

Khi ghép mã đơn hàng, tên người, địa chỉ hoặc tạo chuỗi hiển thị từ nhiều cột, bạn thường dùng toán tử nối chuỗi `||`, hàm `CONCAT` và các hàm đệm như `LPAD`/`RPAD`. Trong Oracle Database, kết quả có thể gây bất ngờ nếu một trong các cột là kiểu **`CHAR` cố định độ dài**. Oracle tự đệm khoảng trắng vào cuối giá trị `CHAR` để đủ độ dài khai báo; những khoảng trắng này có thể đi theo giá trị khi nối chuỗi, ảnh hưởng đến độ dài, so sánh và dữ liệu xuất ra.

Ví dụ, cột `CHAR(5)` lưu mã `'A'` thực tế có phần đệm tương đương `'A    '`. Khi nối với `'X'`, kết quả có thể là `'A    X'`. Cột `VARCHAR2(5)` lưu `'A'` không tự thêm bốn khoảng trắng, nên nối với `'X'` cho `'AX'`. Nếu chỉ nhìn giao diện SQL client, hai kết quả có thể trông gần giống nhau; cần dùng dấu bao, `LENGTH` và `DUMP` để quan sát chính xác.

Bài học này trình bày cách nối chuỗi và đệm dữ liệu đúng trong Oracle, phân biệt `CHAR` với `VARCHAR2`, nhận biết trailing spaces và lựa chọn cách chuẩn hóa phù hợp cho truy vấn, index, file xuất và ứng dụng Java.

Sau bài học, bạn có thể:

- Dùng `||` và `CONCAT` để ghép chuỗi, hiểu giới hạn của từng cách.
- Giải thích hành vi đặc biệt của `CHAR(n)`, `VARCHAR2(n)` và khoảng trắng cuối.
- Dùng `LENGTH`, `LENGTHB`, `DUMP`, `TRIM`, `LTRIM` và `RTRIM` để quan sát/làm sạch dữ liệu.
- Phân biệt blank-padded và nonpadded comparison khi so sánh `CHAR` với `VARCHAR2`.
- Dùng `LPAD`/`RPAD` để căn lề, tạo mã hiển thị và định dạng chuỗi có độ dài mục tiêu.
- Tránh lỗi khi nối `NULL`, số, ngày giờ hoặc dữ liệu do người dùng nhập.
- Thiết kế truy vấn và ứng dụng có quy tắc rõ ràng về trailing spaces, kiểu dữ liệu và index.

> Các ví dụ dùng tên bảng có tiền tố `LAB_` và phù hợp để thực hành trong schema riêng. Hành vi chi tiết về độ dài chuỗi còn phụ thuộc character set, byte/character length semantics, phiên bản Oracle và `MAX_STRING_SIZE`. Không dùng một bảng lab để ghi đè dữ liệu đang được ứng dụng sử dụng.

## 1. CHAR và VARCHAR2: hai cách lưu chuỗi khác nhau

### 1.1. CHAR là kiểu cố định độ dài

Khai báo:

```sql
code CHAR(5)
```

nghĩa là cột có độ dài cố định 5 đơn vị theo length semantics đã khai báo. Khi ghi giá trị ngắn hơn, Oracle **blank-pads** (đệm dấu cách ở cuối) để đạt độ dài cố định.

Ví dụ:

```sql
CREATE TABLE lab_char_codes (
    id          NUMBER PRIMARY KEY,
    fixed_code  CHAR(5),
    variable_code VARCHAR2(5)
);

INSERT INTO lab_char_codes (id, fixed_code, variable_code)
VALUES (1, 'A', 'A');

INSERT INTO lab_char_codes (id, fixed_code, variable_code)
VALUES (2, 'AB', 'AB');

COMMIT;
```

Về mặt nội dung:

| Cột | Giá trị được nhập | Cách lưu/biểu diễn logic |
| --- | --- | --- |
| `FIXED_CODE CHAR(5)` | `'A'` | `'A    '` (một ký tự A và bốn dấu cách đệm) |
| `VARIABLE_CODE VARCHAR2(5)` | `'A'` | `'A'` (không tự thêm dấu cách) |
| `FIXED_CODE CHAR(5)` | `'AB'` | `'AB   '` |
| `VARIABLE_CODE VARCHAR2(5)` | `'AB'` | `'AB'` |

`CHAR` phù hợp với những trường thực sự có độ dài cố định theo thiết kế, nhưng cần hiểu khoảng trắng đệm có thể ảnh hưởng đến phép nối, so sánh và dữ liệu xuất. `VARCHAR2` lưu chuỗi biến độ dài và thường phù hợp hơn với tên, mô tả, địa chỉ hoặc dữ liệu text có độ dài thay đổi.

### 1.2. VARCHAR2 không tự đệm đến độ dài khai báo

`VARCHAR2(5)` cho phép lưu chuỗi có độ dài tối đa theo giới hạn khai báo, nhưng nếu giá trị là `'A'` thì Oracle không thêm bốn dấu cách chỉ để đủ 5 ký tự. Nếu ứng dụng chủ động gửi `'A '`, dấu cách đó là nội dung thực tế và có thể được giữ.

Điều này tạo khác biệt quan trọng:

```sql
SELECT
    '[' || fixed_code || ']' AS fixed_visible,
    '[' || variable_code || ']' AS variable_visible,
    LENGTH(fixed_code) AS fixed_length,
    LENGTH(variable_code) AS variable_length,
    LENGTH(RTRIM(fixed_code)) AS fixed_trimmed_length
FROM lab_char_codes
ORDER BY id;
```

Với hàng đầu tiên, kết quả thường thể hiện:

| FIXED_VISIBLE | VARIABLE_VISIBLE | FIXED_LENGTH | VARIABLE_LENGTH | FIXED_TRIMMED_LENGTH |
| --- | --- | ---: | ---: | ---: |
| `[A    ]` | `[A]` | 5 | 1 | 1 |

Các dấu ngoặc vuông giúp nhìn ra khoảng trắng cuối. Nếu SQL client tự căn cột hoặc loại khoảng trắng khi hiển thị, hãy dựa vào hàm độ dài và dữ liệu dump thay vì chỉ nhìn màn hình.

### 1.3. CHAR(n BYTE) và CHAR(n CHAR)

Độ dài khai báo ký tự có thể dùng **byte semantics** hoặc **character semantics**:

```sql
CREATE TABLE lab_char_length_semantics (
    code_byte CHAR(5 BYTE),
    code_char CHAR(5 CHAR)
);
```

- `CHAR(5 BYTE)` giới hạn độ dài theo số byte.
- `CHAR(5 CHAR)` giới hạn theo số ký tự theo semantics của Oracle.

Với character set nhiều byte, 5 ký tự có thể chiếm hơn 5 byte. Cần kiểm tra character set của database và cột trước khi chọn độ dài. Đừng giả định `LENGTH` và `LENGTHB` luôn trả cùng con số.

## 2. Quan sát khoảng trắng cuối bằng LENGTH và DUMP

### 2.1. LENGTH và LENGTHB

`LENGTH(expr)` trả số ký tự theo quy tắc của kiểu dữ liệu; với `CHAR`, phần blank-padding ở cuối được tính trong độ dài. `LENGTHB(expr)` trả số byte. Các hàm khác như `LENGTHC`, `LENGTH2` và `LENGTH4` có ý nghĩa riêng đối với Unicode code points/complete characters.

Ví dụ:

```sql
SELECT
    LENGTH(fixed_code) AS char_length,
    LENGTHB(fixed_code) AS char_bytes,
    LENGTH(variable_code) AS varchar_length,
    LENGTHB(variable_code) AS varchar_bytes
FROM lab_char_codes
WHERE id = 1;
```

Với ký tự ASCII `A` và khai báo 5 đơn vị, hai cột có thể cho kết quả 5 và 1 ở `LENGTH`; `LENGTHB` cũng thường là 5 và 1 nếu mỗi ký tự chiếm một byte. Với dữ liệu nhiều byte, hai hàm có thể khác nhau.

### 2.2. Dùng DUMP để xem biểu diễn

`DUMP(expr, return_format)` giúp quan sát kiểu nội bộ và mã byte của biểu thức. Ví dụ:

```sql
SELECT
    DUMP(fixed_code, 1016) AS fixed_dump,
    DUMP(variable_code, 1016) AS variable_dump
FROM lab_char_codes
WHERE id = 1;
```

Tham số `1016` yêu cầu hiển thị thông tin kiểu/độ dài và byte theo dạng hex. Với dữ liệu ASCII, dump của `CHAR(5)` thường cho thấy byte của A kèm các byte space ở cuối, còn `VARCHAR2` chỉ chứa byte A. Định dạng dump cụ thể phụ thuộc character set và kiểu dữ liệu.

**DUMP phục vụ chẩn đoán**, không phải cách chuẩn để ứng dụng xử lý chuỗi. Không viết logic nghiệp vụ dựa vào mã byte nội bộ nếu chỉ cần loại bỏ khoảng trắng.

### 2.3. Dấu cách cuối có thể do dữ liệu nhập, không chỉ CHAR

`VARCHAR2` không tự đệm, nhưng người dùng hoặc hệ thống nguồn vẫn có thể gửi chuỗi có khoảng trắng cuối:

```sql
INSERT INTO lab_char_codes (id, fixed_code, variable_code)
VALUES (3, 'B', 'B   ');

SELECT id,
       '[' || variable_code || ']' AS visible_value,
       LENGTH(variable_code) AS value_length,
       LENGTH(RTRIM(variable_code)) AS trimmed_length
FROM lab_char_codes
WHERE id = 3;
```

Ở đây `VARCHAR2` giữ những dấu cách mà nguồn đã gửi. Vì vậy, không thể kết luận “cột VARCHAR2 không bao giờ có trailing spaces”. Sự khác biệt là **Oracle không tự thêm padding cho VARCHAR2**.

## 3. Nối chuỗi bằng toán tử ||

### 3.1. Cú pháp cơ bản

Toán tử `||` nối hai biểu thức ký tự:

```sql
SELECT
    'Oracle' || ' Database' AS product_name,
    'DB-' || '2026' AS code
FROM dual;
```

Kết quả:

```text
Oracle Database
DB-2026
```

Có thể nối nhiều biểu thức liên tiếp:

```sql
SELECT
    first_name || ' ' || last_name AS full_name,
    country_code || '-' || phone_number AS phone_display
FROM lab_contacts;
```

Đây là cách dễ đọc khi tạo một chuỗi từ nhiều cột và dấu phân cách. Cần chú ý kiểu dữ liệu, NULL và khoảng trắng trong từng thành phần.

### 3.2. CHAR mang trailing spaces vào kết quả nối

Với bảng ở phần 1:

```sql
SELECT
    '[' || fixed_code || 'X]' AS char_concat,
    '[' || variable_code || 'X]' AS varchar_concat,
    '[' || RTRIM(fixed_code) || 'X]' AS trimmed_char_concat
FROM lab_char_codes
WHERE id = 1;
```

Kết quả minh họa:

| CHAR_CONCAT | VARCHAR_CONCAT | TRIMMED_CHAR_CONCAT |
| --- | --- | --- |
| `[A    X]` | `[AX]` | `[AX]` |

Oracle blank-pads giá trị `CHAR(5)` khi lưu/đọc theo ngữ nghĩa của kiểu. Khi nối, những dấu cách đó là một phần biểu diễn ký tự và có thể xuất hiện trước phần được nối thêm. `RTRIM` loại dấu cách cuối trước khi nối nếu nghiệp vụ không muốn giữ padding.

**Không dùng `RTRIM` một cách máy móc trên mọi cột.** Nếu dấu cách cuối là dữ liệu có ý nghĩa theo contract (ví dụ nội dung cố định hoặc dữ liệu mã hóa theo giao thức), việc trim sẽ làm thay đổi dữ liệu.

### 3.3. CONCAT: hàm nối hai chuỗi

Oracle cung cấp `CONCAT(char1, char2)`:

```sql
SELECT
    CONCAT('Oracle', ' Database') AS result_1,
    CONCAT(fixed_code, 'X') AS result_2
FROM lab_char_codes
WHERE id = 1;
```

`CONCAT` tương đương về mục đích với `char1 || char2`, nhưng hàm chỉ nhận **hai đối số**. Nếu muốn nối nhiều thành phần, phải lồng hàm:

```sql
SELECT CONCAT(CONCAT('DB', '-'), '2026')
FROM dual;
```

Với nhiều thành phần, `||` thường dễ đọc hơn:

```sql
SELECT 'DB' || '-' || '2026'
FROM dual;
```

### 3.4. NULL trong phép nối chuỗi của Oracle

Đối với toán tử nối chuỗi Oracle, một toán hạng `NULL` được xử lý theo quy tắc đặc biệt: nối `NULL` với một chuỗi khác thường cho ra chuỗi còn lại. Ví dụ:

```sql
SELECT
    'ABC' || CAST(NULL AS VARCHAR2(10)) AS left_value,
    CAST(NULL AS VARCHAR2(10)) || 'ABC' AS right_value,
    CAST(NULL AS VARCHAR2(10)) ||
        CAST(NULL AS VARCHAR2(10)) AS both_null
FROM dual;
```

Kết quả hai cột đầu là `ABC`; cột cuối là `NULL`. Điều này là ngoại lệ đáng nhớ so với nhiều phép toán số học, trong đó toán hạng NULL thường làm kết quả thành NULL.

Vì Oracle hiện xem `''` như `NULL` đối với giá trị ký tự thông thường:

```sql
SELECT
    'A' || '' AS a_with_empty,
    '' || 'B' AS empty_with_b,
    CONCAT('', 'C') AS concat_empty
FROM dual;
```

Các kết quả tương ứng là `A`, `B` và `C`. Nếu cần biểu diễn một trường trống khác với NULL, không thể dựa vào `''` trong `VARCHAR2` của Oracle để lưu trạng thái riêng.

> Oracle có ghi chú rằng hành vi nối chuỗi rỗng/NULL có thể thay đổi trong tương lai. Đối với mã lâu dài, không dùng đặc tính này làm nền tảng duy nhất cho logic nghiệp vụ; chuẩn hóa dữ liệu đầu vào và xử lý NULL rõ ràng.

### 3.5. Nối tên có NULL mà không tạo dấu cách thừa

Mẫu đơn giản:

```sql
SELECT TRIM(first_name || ' ' || last_name) AS full_name
FROM lab_contacts;
```

Với `FIRST_NAME='An'` và `LAST_NAME='Nguyen'`, kết quả là `An Nguyen`. Nếu một bên NULL, phép nối của Oracle bỏ qua thành phần NULL và `TRIM` loại dấu cách ở đầu/cuối. Nếu cả hai NULL, biểu thức giữa hai thành phần vẫn có thể tạo một dấu cách; `TRIM` làm kết quả trở thành chuỗi rỗng và Oracle xem như NULL.

Nếu cần kiểm soát dấu phân cách rõ ràng hơn, có thể viết:

```sql
SELECT CASE
         WHEN first_name IS NULL THEN last_name
         WHEN last_name IS NULL THEN first_name
         ELSE first_name || ' ' || last_name
       END AS full_name
FROM lab_contacts;
```

Mẫu CASE diễn đạt trực tiếp quy tắc chỉ thêm khoảng trắng khi cả hai thành phần đều có giá trị. Nếu chuỗi đầu vào có thể chứa khoảng trắng cuối, cần quyết định có trim từng thành phần trước khi nối hay không.

### 3.6. Nối số và ngày: tránh implicit conversion

Oracle có thể chuyển số hoặc ngày thành chuỗi khi nối với text:

```sql
SELECT 'Amount=' || total_amount
FROM invoices;
```

Kết quả hiển thị có thể phụ thuộc NLS session đối với số; ngày tháng cũng có thể phụ thuộc định dạng ngày mặc định. Để output ổn định, hãy chuyển đổi rõ:

```sql
SELECT
    'Amount=' ||
    TO_CHAR(
        total_amount,
        'FM999G999G990D00',
        'NLS_NUMERIC_CHARACTERS=''.,'''
    ) AS amount_text,
    'Created=' ||
    TO_CHAR(created_at, 'YYYY-MM-DD HH24:MI:SS') AS created_text
FROM invoices;
```

Ở đây NUMBER và DATE được chuyển thành text bằng format model tường minh. Nếu yêu cầu định dạng khác, hãy thay format/NLS parameter theo hợp đồng xuất dữ liệu. **Không ghép dữ liệu người dùng trực tiếp vào câu SQL**; dùng bind variables để tránh SQL injection và lỗi chuyển kiểu.

## 4. So sánh CHAR và VARCHAR2: blank-padded và nonpadded semantics

Đây là phần quan trọng khi điều tra vì sao hai chuỗi nhìn giống nhau nhưng phép so sánh cho kết quả khác.

### 4.1. Blank-padded comparison

Oracle dùng **blank-padded comparison semantics** khi cả hai toán hạng thuộc những kiểu như `CHAR`, `NCHAR`, text literal hoặc giá trị trả về bởi hàm `USER` theo quy tắc SQL tương ứng. Oracle đệm dấu cách vào toán hạng ngắn hơn cho đến khi hai toán hạng có độ dài bằng nhau rồi mới so sánh.

Ví dụ:

```sql
SELECT
    CASE WHEN CAST('A' AS CHAR(5)) = 'A'
         THEN 'EQUAL' ELSE 'NOT EQUAL' END AS char_to_literal
FROM dual;
```

Kết quả là `EQUAL` vì phép so sánh blank-padded có thể so sánh `'A    '` với `'A'` sau khi đệm bên ngắn hơn.

### 4.2. Nonpadded comparison

Nếu **một trong hai toán hạng là `VARCHAR2` hoặc `NVARCHAR2`**, Oracle dùng **nonpadded comparison semantics**. Hai chuỗi được so sánh theo nội dung/độ dài thực tế; không tự đệm khoảng trắng để cân bằng độ dài.

Ví dụ:

```sql
WITH values_to_compare AS (
    SELECT CAST('A' AS CHAR(5)) AS fixed_value,
           CAST('A' AS VARCHAR2(5)) AS variable_value
    FROM dual
)
SELECT
    CASE WHEN fixed_value = 'A'
         THEN 'EQUAL' ELSE 'NOT EQUAL' END AS char_vs_literal,
    CASE WHEN fixed_value = variable_value
         THEN 'EQUAL' ELSE 'NOT EQUAL' END AS char_vs_varchar
FROM values_to_compare;
```

Kết quả theo các quy tắc so sánh trên:

| CHAR_VS_LITERAL | CHAR_VS_VARCHAR |
| --- | --- |
| EQUAL | NOT EQUAL |

Ở biểu thức thứ nhất, literal `'A'` là text literal có semantics blank-padded cùng CHAR. Ở biểu thức thứ hai, một bên là VARCHAR2 nên so sánh không đệm; `CHAR(5)` có phần trailing spaces còn VARCHAR2 chỉ chứa `A`.

### 4.3. Bảng quy tắc cần nhớ

| Hai toán hạng | Ngữ nghĩa so sánh |
| --- | --- |
| `CHAR` với `CHAR` | Blank-padded |
| `CHAR` với text literal | Blank-padded |
| `NCHAR` với `NCHAR` hoặc literal theo quy tắc tương ứng | Blank-padded |
| `VARCHAR2` với `VARCHAR2` | Nonpadded |
| `CHAR` với `VARCHAR2` | Nonpadded |
| `NCHAR` với `NVARCHAR2` | Nonpadded |
| Một toán hạng là `VARCHAR2`/`NVARCHAR2` | Nonpadded |

Các phép so sánh còn có thể chịu ảnh hưởng bởi collation/NLS trên các phiên bản và cột có khai báo collation riêng. Bảng này giải thích **quy tắc padding độ dài**; nó không thay thế quy tắc collation về chữ hoa/thường và dấu.

### 4.4. So sánh trong JOIN cũng chịu ảnh hưởng kiểu dữ liệu

Giả sử bảng A có khóa `CHAR(10)` và bảng B có khóa `VARCHAR2(10)`. Nếu giá trị nhìn thấy cùng là `'X'`, một bên có thể chứa padding cuối còn bên kia không có. Phép join giữa CHAR và VARCHAR2 dùng nonpadded semantics, nên có thể không match như mong muốn.

Truy vấn chẩn đoán:

```sql
SELECT
    a.code_char,
    b.code_varchar,
    LENGTH(a.code_char) AS char_len,
    LENGTH(b.code_varchar) AS varchar_len
FROM lab_char_table a
JOIN lab_varchar_table b
  ON a.code_char = b.code_varchar;
```

Nếu đây là thiết kế dữ liệu cần ghép nối lâu dài, giải pháp tốt hơn thường là **thống nhất datatype và quy tắc chuẩn hóa ở schema**, không phải bọc mọi join trong hàm trim mà không xét index và nghiệp vụ.

### 4.5. Khi nào nên RTRIM trước khi so sánh?

Nếu dữ liệu nguồn có padding và mục tiêu nghiệp vụ là bỏ qua dấu cách cuối:

```sql
SELECT a.id, b.id
FROM lab_char_table a
JOIN lab_varchar_table b
  ON RTRIM(a.code_char) = RTRIM(b.code_varchar);
```

Điều kiện này chuẩn hóa cả hai phía bằng cách bỏ trailing spaces. Nhưng phải hiểu rằng:

- Nó coi `'A'` và `'A '` là cùng nội dung sau trim.
- Nó có thể làm Oracle khó dùng index B-tree thông thường trên cột nếu không có index phù hợp cho biểu thức.
- Nó có thể gộp những giá trị mà contract nguồn muốn giữ phân biệt.

Nếu quy tắc trim là chính sách cố định và truy vấn thường xuyên, cân nhắc lưu dữ liệu đã chuẩn hóa khi ghi hoặc tạo function-based index thích hợp sau khi đo execution plan.

## 5. TRIM, LTRIM và RTRIM

### 5.1. TRIM bỏ khoảng trắng ở hai đầu

`TRIM(expr)` mặc định loại bỏ blank spaces ở **đầu và cuối**:

```sql
SELECT
    '[' || TRIM('   Oracle   ') || ']' AS trimmed,
    LENGTH(TRIM('   Oracle   ')) AS trimmed_length
FROM dual;
```

Kết quả `[Oracle]` và độ dài 6.

Có thể chỉ định hướng:

```sql
SELECT
    '[' || TRIM(LEADING 'x' FROM 'xxxABxx') || ']' AS leading_trim,
    '[' || TRIM(TRAILING 'x' FROM 'xxxABxx') || ']' AS trailing_trim,
    '[' || TRIM(BOTH 'x' FROM 'xxxABxx') || ']' AS both_trim
FROM dual;
```

Kết quả lần lượt là `[ABxx]`, `[xxxAB]` và `[AB]`.

### 5.2. LTRIM và RTRIM

- `LTRIM(expr)` loại bỏ các blank spaces ở bên trái.
- `RTRIM(expr)` loại bỏ các blank spaces ở bên phải.
- Có thể cung cấp bộ ký tự cần loại bỏ, ví dụ `RTRIM(expr, 'x')`.

Ví dụ:

```sql
SELECT
    '[' || LTRIM('   ABC   ') || ']' AS left_trim,
    '[' || RTRIM('   ABC   ') || ']' AS right_trim,
    '[' || RTRIM('ABCxxx', 'x') || ']' AS trim_x
FROM dual;
```

Kết quả:

| LEFT_TRIM | RIGHT_TRIM | TRIM_X |
| --- | --- | --- |
| `[ABC   ]` | `[   ABC]` | `[ABC]` |

### 5.3. TRIM mặc định không có nghĩa là xóa mọi whitespace

Khoảng trắng có thể bao gồm:

- Space thông thường.
- Tab (`CHR(9)`).
- Line feed (`CHR(10)`).
- Carriage return (`CHR(13)`).
- Nonbreaking space và các ký tự Unicode spacing khác.

`TRIM(expr)` mặc định xử lý blank space theo quy tắc Oracle; không được mặc định nó loại bỏ tất cả các ký tự whitespace trên. Đối số trim character của hàm `TRIM` là **một ký tự**, không phải một tập nhiều ký tự. Ví dụ dữ liệu copy từ Excel hoặc web có thể chứa tab/Unicode space mà `TRIM` thông thường không loại bỏ.

Nếu cần xử lý tab/CR/LF, hãy thay từng loại ký tự điều khiển trước rồi trim:

```sql
SELECT TRIM(
         REPLACE(
           REPLACE(
             REPLACE(raw_text, CHR(9), ' '),
             CHR(10), ' '
           ),
           CHR(13), ' '
         )
       ) AS normalized_text
FROM lab_import_text;
```

Khi cần xử lý Unicode whitespace đầy đủ, phải xác định tập ký tự đầu vào và thử với character set/Oracle version thực tế; không dùng một biểu thức trim ngắn rồi tuyên bố đã chuẩn hóa mọi whitespace.

### 5.4. Làm sạch trước khi lưu hay chỉ khi hiển thị?

Có hai chính sách khác nhau:

1. **Chuẩn hóa khi nhập:** lưu dữ liệu đã trim theo contract; những truy vấn sau đơn giản và dễ dùng index hơn.
2. **Chuẩn hóa khi hiển thị/tìm kiếm:** giữ nguyên dữ liệu gốc, áp dụng trim trong biểu thức truy vấn.

Nếu dữ liệu gốc có giá trị pháp lý/audit, ví dụ nội dung được gửi từ đối tác, việc thay đổi whitespace khi ghi có thể làm mất bằng chứng đầu vào. Trong trường hợp đó, lưu raw value và một cột normalized riêng có thể phù hợp hơn.

## 6. LPAD và RPAD: đệm chuỗi theo độ dài mục tiêu

### 6.1. Cú pháp

`LPAD(expr1, n, expr2)` đệm vào **bên trái**; `RPAD(expr1, n, expr2)` đệm vào **bên phải** để tạo kết quả có độ dài mục tiêu `n`. Nếu bỏ `expr2`, Oracle dùng khoảng trắng.

Ví dụ:

```sql
SELECT
    LPAD('42', 6, '0') AS padded_left,
    RPAD('42', 6, '0') AS padded_right,
    LPAD('DB', 6) AS padded_spaces
FROM dual;
```

Kết quả:

| PADDED_LEFT | PADDED_RIGHT | PADDED_SPACES |
| --- | --- | --- |
| `000042` | `420000` | `    DB` |

### 6.2. Độ dài mục tiêu nhỏ hơn chuỗi gốc

Nếu `expr1` dài hơn `n`, kết quả chỉ giữ phần vừa với độ dài mục tiêu; vì vậy không dùng LPAD/RPAD như một hàm kiểm tra dữ liệu mà không xác minh độ dài đầu vào:

```sql
SELECT
    LPAD('ABCDEFG', 4, '0') AS lpad_short,
    RPAD('ABCDEFG', 4, '0') AS rpad_short
FROM dual;
```

Kết quả minh họa là `ABCD` cho LPAD và `ABCD` cho RPAD khi chuỗi gốc dài hơn độ dài đích. Cả hai đều không phải cơ chế tự báo lỗi khi dữ liệu bị cắt.

### 6.3. Đệm mã hiển thị, không biến nó thành số

Nếu mã đơn hàng cần hiển thị sáu chữ số:

```sql
SELECT LPAD(TO_CHAR(order_id), 6, '0') AS display_order_id
FROM lab_ctas_orders;
```

Giá trị `42` hiển thị thành `000042`. Đây là **chuỗi trình bày**, không phải số 42 có thêm số 0 ở đầu. Không chuyển chuỗi mã đã đệm trở lại NUMBER nếu các số 0 đầu có ý nghĩa trong mã nghiệp vụ.

Với giá trị âm, số lớn hơn độ dài, NULL hoặc dữ liệu không hợp lệ, cần quy định rõ cách hiển thị:

```sql
SELECT
    LPAD(TO_CHAR(42, 'FM9999990'), 8, '0') AS positive_code,
    LPAD(TO_CHAR(-42, 'FM9999990'), 8, '0') AS negative_code
FROM dual;
```

Format model số có thể tạo dấu âm và ký tự khác; LPAD chỉ đệm cho đủ chiều dài, không tự hiểu quy tắc mã nghiệp vụ. Hãy kiểm thử giới hạn lớn nhất và dấu âm nếu chúng có thể xuất hiện.

### 6.4. Padding với nhiều ký tự

`expr2` có thể chứa chuỗi nhiều ký tự; Oracle lặp nội dung đó để tạo phần đệm và chỉ dùng phần cần thiết để đạt độ dài yêu cầu:

```sql
SELECT
    LPAD('7', 8, 'ab') AS pattern_left,
    RPAD('7', 8, 'ab') AS pattern_right
FROM dual;
```

Ví dụ minh họa cho thấy phần đệm được ghép lặp cho đến độ dài mục tiêu. Nếu `expr2` là NULL hoặc chuỗi rỗng, không nên kỳ vọng Oracle có thể tạo phần đệm; kết quả có thể là NULL theo ngữ nghĩa của đối số. Hãy bảo đảm pad string có nội dung nếu yêu cầu kết quả bắt buộc.

### 6.5. Độ dài hiển thị và ký tự nhiều byte

Đối số `n` của LPAD/RPAD được mô tả theo **display length**; với bộ ký tự nhiều byte, độ dài hiển thị có thể khác số byte và một số cách đếm ký tự. Vì vậy:

- Không dùng `LENGTHB` thay thế máy móc cho `n`.
- Kiểm thử ký tự Unicode và ký tự ghép dấu trong character set thực tế.
- Xác định giới hạn cột đích theo BYTE hay CHAR.
- Tránh cắt giữa một chuỗi mã hóa/biểu diễn ký tự không hoàn chỉnh.

## 7. CHAR và padding trong UNION, DISTINCT, GROUP BY, UNIQUE

### 7.1. Không nên dùng CHAR để ép mọi chuỗi có cùng độ dài

`CHAR(n)` thường phù hợp với trường có chiều dài thực sự cố định, chẳng hạn một mã theo chuẩn luôn có đúng n ký tự. Nếu dữ liệu độ dài thay đổi, dùng `VARCHAR2` và chuẩn hóa theo yêu cầu sẽ tránh nhiều vấn đề padding.

Ví dụ mã vùng `'VN'` trong `CHAR(5)` có thể được lưu với ba dấu cách cuối. Khi ghép vào chuỗi địa chỉ, các dấu cách đó có thể đi theo kết quả:

```sql
SELECT '[' || country_code || '-' || city_name || ']'
FROM lab_address;
```

Nếu không muốn dấu cách trước dấu gạch nối, cần trim đúng phía:

```sql
SELECT '[' || RTRIM(country_code) || '-' || city_name || ']'
FROM lab_address;
```

### 7.2. DISTINCT và GROUP BY không phải cách làm sạch trailing spaces

Các phép gom nhóm/loại trùng chịu ảnh hưởng kiểu dữ liệu và quy tắc so sánh. Không nên dùng `DISTINCT` để thay cho chuẩn hóa dữ liệu. Nếu một bảng có cả CHAR và VARCHAR2, hãy kiểm tra kiểu biểu thức thực tế trước khi giải thích vì sao hai giá trị được xem là trùng hay khác.

Một cách quan sát an toàn là truy vấn cả giá trị hiển thị, độ dài và kiểu:

```sql
SELECT
    '[' || code_value || ']' AS shown_value,
    LENGTH(code_value) AS char_length,
    LENGTHB(code_value) AS byte_length,
    DUMP(code_value, 1016) AS internal_dump
FROM lab_mixed_codes;
```

Sau đó thiết kế phép chuẩn hóa tường minh như `RTRIM(code_value)` hoặc một biểu thức collation phù hợp nếu đó là quy tắc nghiệp vụ.

### 7.3. UNIQUE và trailing spaces

Với cột `CHAR`, Oracle blank-pads đến độ dài khai báo nên những chuỗi chỉ khác nhau ở phần thiếu padding thường trở thành cùng giá trị logic. Với `VARCHAR2`, trailing spaces được lưu như nội dung và so sánh theo nonpadded semantics trong phép so sánh thông thường.

Ví dụ khái niệm:

```sql
CREATE TABLE lab_unique_char (
    code CHAR(5) UNIQUE
);

CREATE TABLE lab_unique_varchar (
    code VARCHAR2(5) UNIQUE
);
```

Trong bảng `LAB_UNIQUE_CHAR`, giá trị `'A'` và một giá trị được nhập như `'A '` có thể cùng biểu diễn sau padding, dẫn đến vi phạm uniqueness. Trong `LAB_UNIQUE_VARCHAR`, `'A'` và `'A '` là hai chuỗi có độ dài khác nhau và có thể cùng tồn tại dưới UNIQUE nếu không có collation/constraint khác làm chúng tương đương.

Hãy kiểm tra trên phiên bản, kiểu cột và collation thật trước khi áp dụng cho mã định danh. Nếu nghiệp vụ muốn bỏ qua trailing spaces, nên chuẩn hóa khi nhập hoặc thiết kế constraint/index trên biểu thức phù hợp; đừng dựa vào việc người dùng nhập đúng độ dài.

## 8. Kiểu dữ liệu lớn và giới hạn nối chuỗi

### 8.1. VARCHAR2 có giới hạn kích thước

Kết quả nối chuỗi thông thường có kiểu và giới hạn phụ thuộc các toán hạng, cấu hình Oracle và ngữ cảnh SQL/PLSQL. Trong SQL, giới hạn VARCHAR2 truyền thống là 4000 byte với `MAX_STRING_SIZE=STANDARD`; chế độ `EXTENDED` hỗ trợ giới hạn lớn hơn (tối đa 32767 byte cho VARCHAR2 SQL trong điều kiện hỗ trợ). PL/SQL VARCHAR2 cũng có giới hạn riêng.

Vì vậy, khi ghép nhiều cột text:

```sql
SELECT first_part || second_part || third_part
FROM lab_large_text;
```

không được giả định kết quả luôn chứa được tổng kích thước không giới hạn. Có thể gặp lỗi vượt độ dài hoặc phải dùng LOB phù hợp. Giới hạn cụ thể phụ thuộc version, `MAX_STRING_SIZE` và kiểu trả về; kiểm tra trước khi thiết kế pipeline dữ liệu lớn.

### 8.2. CLOB và nối chuỗi lớn

Khi cần ghép nội dung dài, các biểu thức có `CLOB` có thể tạo kết quả LOB theo quy tắc kiểu dữ liệu của Oracle. Tuy nhiên cần cân nhắc:

- Kích thước nội dung và bộ nhớ/temporary LOB.
- Chi phí sao chép dữ liệu lớn qua nhiều phép nối.
- Chuyển đổi giữa CLOB và VARCHAR2.
- API/driver đọc kết quả dưới dạng LOB stream hay String.
- Việc trim/format toàn bộ CLOB có thể tốn tài nguyên.

Ví dụ thao tác với CLOB trong SQL:

```sql
SELECT description_clob || TO_CLOB(CHR(10)) || detail_clob
FROM lab_documents;
```

Khi làm việc với nội dung lớn, hãy thử nghiệm trên kích thước gần thực tế và cân nhắc API LOB của driver thay vì đưa toàn bộ nội dung vào một VARCHAR2 trung gian.

### 8.3. Nối nhiều hàng: LISTAGG không giống || thông thường

`||` nối biểu thức trong **một hàng**. Khi muốn gộp nhiều hàng thành một chuỗi, Oracle có `LISTAGG`:

```sql
SELECT customer_id,
       LISTAGG(status, ', ')
           WITHIN GROUP (ORDER BY order_id) AS status_list
FROM lab_ctas_orders
GROUP BY customer_id;
```

`LISTAGG` có giới hạn độ dài và có thể phát sinh `ORA-01489` nếu kết quả vượt giới hạn trong cấu hình/ngữ cảnh tương ứng; các phiên bản mới có tùy chọn xử lý overflow. Không dùng vòng nối chuỗi thủ công hoặc `LISTAGG` cho dữ liệu lớn mà chưa xem xét giới hạn, thứ tự và chính sách cắt/tràn.

## 9. Nối chuỗi an toàn trong ứng dụng Java/JDBC

### 9.1. Phân biệt dữ liệu với câu lệnh SQL

Trong Java, toán tử `+` nối String. Trong SQL Oracle, `||` nối biểu thức ký tự. Nhưng không được dùng việc nối chuỗi ở tầng Java để ghép dữ liệu người dùng trực tiếp vào SQL:

```java
// Không an toàn: userInput được ghép thẳng vào câu SQL.
String sql = "SELECT id FROM customers WHERE name = '" + userInput + "'";
```

Hãy dùng bind:

```java
String sql = "SELECT id FROM customers WHERE name = ?";

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setString(1, userInput);
    try (ResultSet rs = ps.executeQuery()) {
        while (rs.next()) {
            long id = rs.getLong("id");
            // Xử lý kết quả.
        }
    }
}
```

Bind variables tách dữ liệu khỏi cú pháp SQL, giảm nguy cơ SQL injection và tránh lỗi quote/escape. Tuy nhiên, kiểu bind và trailing spaces vẫn cần phù hợp với kiểu cột `CHAR`/`VARCHAR2`.

### 9.2. CHAR trong JDBC

Một cột `CHAR(n)` có padding; khi lấy dữ liệu qua JDBC, driver có thể trả chuỗi chứa các khoảng trắng cuối tùy kiểu truy xuất/driver và API được dùng. Nếu ứng dụng cần mã logic không có padding, hãy chuẩn hóa có chủ đích:

```java
String code = rs.getString("FIXED_CODE");
String normalizedCode = code == null ? null : code.stripTrailing();
```

`stripTrailing()` là API Java hiện đại loại bỏ whitespace ở cuối theo quy tắc Java; nếu dự án dùng Java cũ hơn, có thể cần cách khác. Hãy kiểm tra xem contract muốn bỏ **mọi Unicode whitespace** hay chỉ dấu cách ASCII. Đừng tự trim mọi chuỗi trả về từ database: trailing spaces có thể là dữ liệu có ý nghĩa ở một số trường.

Nếu bind một `VARCHAR2` vào predicate so sánh với cột `CHAR`, quy tắc nonpadded semantics có thể khiến kết quả khác mong đợi. Kiểm thử bằng đúng Oracle JDBC driver và bind type thực tế; tránh dựa vào kết quả chạy trong SQL worksheet với literal rồi suy rộng sang PreparedStatement.

### 9.3. Định dạng số/ngày trước khi nối

Nếu muốn tạo mã hoặc thông báo:

```java
String display = "Order " + orderId + " created at " + createdAt;
```

Java sẽ gọi cơ chế chuyển đối tượng thành chuỗi của Java; kết quả không nhất thiết theo format SQL của Oracle. Ngược lại, trong SQL:

```sql
SELECT 'Order ' || order_id || ' created at ' || created_at
FROM orders;
```

Oracle chuyển số/ngày theo ngữ cảnh NLS của session. Nếu output phải ổn định giữa các máy, dùng `TO_CHAR` với format rõ trong SQL hoặc format bằng Java theo locale đã chọn ở tầng trình bày.

## 10. Những lỗi và tình huống thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra/khắc phục |
| --- | --- | --- |
| Chuỗi nối có khoảng trắng giữa các thành phần | Cột nguồn là CHAR và mang padding | Kiểm tra `LENGTH`; dùng `RTRIM` nếu contract cho phép |
| Kết quả hiển thị trông giống nhau nhưng so sánh không bằng | Một bên CHAR, bên kia VARCHAR2; nonpadded semantics | Kiểm tra datatype, độ dài và `DUMP`; chuẩn hóa hai phía |
| `LENGTH(CHAR_col)` lớn hơn số ký tự nhập | CHAR được blank-pad đến độ dài cố định | Dùng `RTRIM` khi muốn đo độ dài nội dung không tính padding |
| VARCHAR2 có khoảng trắng cuối | Nguồn nhập đã gửi trailing spaces | Kiểm tra `LENGTH`/`DUMP`; quyết định trim ở biên nhập |
| LPAD làm mất ký tự đầu/cuối | Chuỗi gốc dài hơn độ dài mục tiêu | Kiểm tra độ dài trước khi pad; không dùng LPAD như validation |
| Mã có số 0 đầu bị mất | Chuyển chuỗi mã sang NUMBER | Giữ mã là VARCHAR2; chỉ dùng NUMBER cho số thực sự |
| Nối số/ngày hiển thị khác giữa session | Implicit conversion phụ thuộc NLS | Dùng `TO_CHAR` format model rõ ràng |
| Chuỗi dài gây lỗi | Kết quả vượt giới hạn VARCHAR2/SQL/PLSQL | Kiểm tra `MAX_STRING_SIZE`, datatype và cân nhắc CLOB |
| Kết quả CLOB nối chậm | Sao chép LOB lớn hoặc chuyển kiểu nhiều lần | Dùng LOB APIs/streaming và thử trên kích thước thật |
| JOIN giữa mã CHAR và VARCHAR2 thiếu hàng | Padding ở CHAR và nonpadded comparison | Đồng bộ datatype hoặc chuẩn hóa đúng quy tắc |
| UNIQUE cho phép/không cho phép giá trị tưởng giống nhau | Khác biệt CHAR/VARCHAR2, trailing spaces và collation | Thử trên đúng schema; thiết kế constraint theo identity |
| Trim không loại tab/newline | TRIM mặc định xử lý blank space, không phải mọi whitespace | Chuẩn hóa ký tự điều khiển/Unicode theo contract |

### 10.1. Quy trình chẩn đoán

```text
Kết quả nối/so sánh có khoảng trắng bất ngờ
                    │
                    ▼
             Xác định datatype
             CHAR hay VARCHAR2?
                    │
                    ▼
        LENGTH / LENGTHB / DUMP
         Có trailing spaces không?
                    │
                    ▼
       Xác định nguồn tạo khoảng trắng
       CHAR padding hay dữ liệu nhập?
                    │
                    ▼
     Chọn chuẩn hóa: RTRIM / TRIM / giữ nguyên
                    │
                    ▼
      Kiểm tra comparison semantics và index
                    │
                    ▼
       Thử lại bằng đúng bind type/client
```

Khi truy vấn đúng với literal nhưng sai với ứng dụng, kiểm tra **kiểu bind**, driver và datatype của cột. Không vội sửa bằng cách trim toàn bộ dữ liệu hoặc thay đổi datatype production.

## 11. Bài thực hành tổng hợp

Các bước dưới đây chạy trên schema lab riêng. Nếu các bảng `LAB_CHAR_CODES` đã tồn tại, dùng tên mới hoặc bỏ qua bước tạo; không xóa bảng có dữ liệu cần giữ.

### Bước 1 — Tạo CHAR và VARCHAR2

```sql
CREATE TABLE lab_concat_types (
    id NUMBER PRIMARY KEY,
    code_char CHAR(5),
    code_varchar VARCHAR2(5)
);

INSERT INTO lab_concat_types VALUES (1, 'A', 'A');
INSERT INTO lab_concat_types VALUES (2, 'AB', 'AB');
INSERT INTO lab_concat_types VALUES (3, 'A', 'A ');

COMMIT;
```

### Bước 2 — Quan sát giá trị và độ dài

```sql
SELECT id,
       '[' || code_char || ']' AS char_shown,
       '[' || code_varchar || ']' AS varchar_shown,
       LENGTH(code_char) AS char_len,
       LENGTH(code_varchar) AS varchar_len,
       LENGTH(RTRIM(code_char)) AS char_rtrim_len,
       LENGTH(RTRIM(code_varchar)) AS varchar_rtrim_len
FROM lab_concat_types
ORDER BY id;
```

Trả lời:

1. Vì sao `CODE_CHAR` luôn có độ dài 5 trong ví dụ?
2. Hàng 3 có `CODE_VARCHAR` dài 2 hay 1? Dấu cách đó được tạo bởi Oracle hay bởi câu INSERT?
3. `RTRIM` làm thay đổi giá trị logic nào?

### Bước 3 — So sánh hai kiểu dữ liệu

```sql
SELECT id,
       CASE WHEN code_char = 'A'
            THEN 'MATCH' ELSE 'NO MATCH' END AS char_vs_literal,
       CASE WHEN code_char = code_varchar
            THEN 'MATCH' ELSE 'NO MATCH' END AS char_vs_varchar
FROM lab_concat_types
ORDER BY id;
```

Giải thích sự khác biệt giữa blank-padded và nonpadded semantics. Hãy thử thêm điều kiện `RTRIM(code_char) = RTRIM(code_varchar)` và xem hàng nào được ghép/so khớp.

### Bước 4 — Nối và đệm

```sql
SELECT
    id,
    '[' || code_char || 'X]' AS concat_char,
    '[' || code_varchar || 'X]' AS concat_varchar,
    '[' || RTRIM(code_char) || 'X]' AS concat_trimmed,
    LPAD(TO_CHAR(id), 5, '0') AS padded_id,
    RPAD(code_varchar, 5, '.') AS padded_display
FROM lab_concat_types
ORDER BY id;
```

Kiểm tra vị trí dấu chấm và khoảng trắng. Giải thích vì sao `LPAD`/`RPAD` chỉ phục vụ biểu diễn và không thay đổi datatype nguồn.

### Bước 5 — Nối NULL và NULLIF

```sql
SELECT
    'X' || CAST(NULL AS VARCHAR2(10)) AS x_null,
    CAST(NULL AS VARCHAR2(10)) || 'Y' AS null_y,
    CAST(NULL AS VARCHAR2(10)) ||
        CAST(NULL AS VARCHAR2(10)) AS null_null,
    NULLIF('A', 'A') AS nullif_equal,
    NULLIF('A', 'B') AS nullif_different
FROM dual;
```

Kết quả mong đợi: `X`, `Y`, `NULL`, `NULL` và `A`. Nêu điểm nào là quy tắc riêng của phép nối chuỗi, điểm nào do hàm `NULLIF`.

### Bước 6 — Kiểm tra DUMP và so sánh index

```sql
SELECT id,
       DUMP(code_char, 1016) AS char_dump,
       DUMP(code_varchar, 1016) AS varchar_dump
FROM lab_concat_types
ORDER BY id;
```

Đối chiếu byte của hàng 1 và hàng 3. Nếu cần tìm mã sau chuẩn hóa, thử plan với điều kiện trực tiếp và điều kiện có `RTRIM` trên dữ liệu đủ lớn ở môi trường test; không suy ra kết luận hiệu năng từ ba hàng.

### Bước 7 — Viết quy tắc dữ liệu cho ứng dụng

Giả sử ứng dụng nhận một mã sản phẩm từ REST API. Hãy xác định:

- Mã có độ dài cố định hay biến đổi? Nếu cố định, có nên dùng CHAR hay vẫn dùng VARCHAR2 kèm validation?
- Dấu cách đầu/cuối có bị cấm, được trim hay có ý nghĩa?
- Mã có phân biệt chữ hoa/thường không?
- Khi hiển thị, có cần LPAD số 0 hoặc dấu phân cách không?
- Khi ghi vào Oracle, driver bind datatype nào?
- Khi JOIN sang bảng khác, datatype và quy tắc chuẩn hóa có giống nhau không?

Một contract rõ ràng ở API/schema thường giải quyết tận gốc vấn đề hơn là thêm `RTRIM` vào mọi truy vấn.

## 12. Nguyên tắc thực hành tốt

1. **Chọn datatype theo bản chất dữ liệu.** Dùng `CHAR` khi độ dài thực sự cố định; dùng `VARCHAR2` cho nội dung biến độ dài.
2. **Hiểu trailing spaces trước khi nối hoặc so sánh.** CHAR tự blank-pad; VARCHAR2 chỉ giữ khoảng trắng do nguồn gửi.
3. **Đo bằng hàm, không chỉ nhìn màn hình.** Dùng `LENGTH`, `LENGTHB` và `DUMP` để xác định padding và biểu diễn.
4. **Chỉ trim khi contract cho phép.** `RTRIM` phù hợp loại padding cuối; `TRIM` loại hai đầu; không giả định trim mặc định xử lý mọi Unicode whitespace.
5. **Dùng LPAD/RPAD cho định dạng hiển thị.** Kiểm tra chuỗi dài hơn mục tiêu để tránh cắt mất dữ liệu; giữ mã định danh ở kiểu ký tự nếu số 0 đầu có ý nghĩa.
6. **Chuyển số/ngày thành text tường minh.** Dùng `TO_CHAR` với format/NLS rõ ràng thay implicit conversion trong phép nối.
7. **Dùng bind variables.** Không ghép dữ liệu người dùng vào SQL bằng toán tử nối chuỗi ở Java hoặc PL/SQL dynamic SQL.
8. **Đồng bộ kiểu dữ liệu giữa các khóa JOIN.** CHAR và VARCHAR2 có semantics so sánh khác nhau; chuẩn hóa ở schema thay vì chữa cháy từng query.
9. **Kiểm tra index sau khi bọc cột trong hàm.** `RTRIM(column)` có thể cần function-based index hoặc cột chuẩn hóa nếu được chứng minh cần thiết.
10. **Dùng CLOB cho nội dung dài khi phù hợp.** Đừng giả định phép nối VARCHAR2 có kích thước không giới hạn.

## 13. Câu hỏi tự kiểm tra

1. Một cột `CHAR(8)` nhận giá trị `'DB'`. `LENGTH(column)` thường trả bao nhiêu? Vì sao?
2. Một cột `VARCHAR2(8)` nhận `'DB  '`. Oracle có tự bỏ hai dấu cách cuối không?
3. Nối `CHAR(5)` chứa `'A'` với `'X'` có thể tạo chuỗi nào? Vì sao cần `RTRIM` trong một số trường hợp?
4. `CONCAT` nhận tối đa bao nhiêu đối số? Khi cần nối năm thành phần, vì sao `||` dễ đọc hơn?
5. Kết quả của `NULL || 'ABC'` và `NULL || NULL` theo quy tắc nối chuỗi Oracle hiện hành là gì?
6. Vì sao `CHAR(5) = 'A'` có thể TRUE nhưng `CHAR(5) = VARCHAR2('A')` có thể FALSE?
7. `RTRIM` và `TRIM` khác nhau ở phía nào của chuỗi?
8. Vì sao `TRIM` mặc định không bảo đảm loại tab hoặc mọi Unicode whitespace?
9. `LPAD('12345', 3, '0')` có an toàn để kiểm tra mã dài tối đa 3 ký tự không? Vì sao?
10. Khi nối NUMBER hoặc DATE thành text trong SQL, cần tránh implicit conversion như thế nào?
11. Vì sao dùng `RTRIM(column)` trong WHERE/JOIN có thể ảnh hưởng khả năng sử dụng index thông thường?
12. Nếu ứng dụng Java dùng `PreparedStatement.setString` để so sánh với cột CHAR, tại sao phải thử bằng đúng driver và kiểu bind thực tế?

## 14. Mô hình ghi nhớ

```text
CHAR(n)
  → độ dài cố định
  → tự blank-pad
  → trailing spaces có thể đi theo phép nối

VARCHAR2(n)
  → độ dài biến đổi
  → không tự padding
  → vẫn có thể giữ trailing spaces do nguồn nhập

|| / CONCAT
  → nối hai biểu thức ký tự
  → NULL + chuỗi: thường trả chuỗi còn lại theo Oracle
  → CHAR padding vẫn cần chú ý

TRIM / LTRIM / RTRIM
  → chuẩn hóa khoảng trắng theo đúng phía
  → mặc định không phải bộ lọc mọi Unicode whitespace

LPAD / RPAD
  → tạo chuỗi trình bày theo độ dài mục tiêu
  → kiểm tra nguy cơ cắt khi đầu vào dài hơn n

CHAR vs VARCHAR2 comparison
  → blank-padded nếu cả hai toán hạng thuộc nhóm CHAR/literal phù hợp
  → nonpadded nếu một bên là VARCHAR2/NVARCHAR2
```

Khi nối hoặc xử lý dữ liệu ký tự trong Oracle, hãy luôn biết **kiểu dữ liệu thực, khoảng trắng nào là nội dung và khoảng trắng nào là padding**, cũng như quy tắc so sánh của hai toán hạng. Dùng `||`, `CONCAT`, `TRIM`, `RTRIM`, `LPAD` và `RPAD` đúng mục đích sẽ giúp chuỗi hiển thị chính xác, truy vấn JOIN ổn định và ứng dụng tránh những lỗi tinh vi do CHAR có khoảng trắng cuối.
