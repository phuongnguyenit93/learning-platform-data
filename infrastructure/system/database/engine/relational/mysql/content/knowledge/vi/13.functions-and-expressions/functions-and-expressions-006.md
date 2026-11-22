# TRIM, REPLACE, LPAD, RPAD và chuẩn hóa dữ liệu

Dữ liệu chuỗi thường đi vào hệ thống từ nhiều nguồn: biểu mẫu web, file CSV, API đối tác, hệ thống cũ hoặc thao tác nhập thủ công. Cùng một giá trị có thể xuất hiện với khoảng trắng thừa, dấu phân cách khác nhau, mã thiếu số 0 ở đầu hoặc định dạng không thống nhất. Nếu lưu nguyên trạng mà không có quy tắc chuẩn hóa, việc tìm kiếm, so sánh, loại trùng và xuất báo cáo sẽ khó kiểm soát.

MySQL cung cấp các hàm chuỗi đơn giản nhưng hữu ích để làm sạch và định dạng dữ liệu: `TRIM()` loại bỏ chuỗi ký tự ở đầu/cuối, `REPLACE()` thay thế mọi lần xuất hiện của một chuỗi con, `LPAD()` thêm ký tự vào bên trái và `RPAD()` thêm ký tự vào bên phải. Dùng đúng các hàm này giúp chuẩn hóa các quy tắc định dạng phổ biến ngay trong truy vấn hoặc bước nạp dữ liệu.

Các hàm trên không tự hiểu ý nghĩa nghiệp vụ của dữ liệu. Chúng không xác định một số điện thoại có hợp lệ hay một mã sản phẩm có đúng quy tắc hay không; chúng chỉ thực hiện phép biến đổi chuỗi được yêu cầu. Vì vậy, cần xác định quy tắc chuẩn hóa trước, xem trước kết quả và giữ lại dữ liệu nguồn khi việc biến đổi có thể làm mất thông tin.

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Dùng `TRIM()` để loại bỏ khoảng trắng hoặc chuỗi xác định ở đầu/cuối.
- Phân biệt `TRIM()` với việc xóa ký tự ở mọi vị trí trong chuỗi.
- Dùng `REPLACE()` để thay thế tất cả lần xuất hiện của một chuỗi con và hiểu tính phân biệt hoa/thường của hàm.
- Dùng `LPAD()` và `RPAD()` để tạo chuỗi có độ dài ký tự mong muốn.
- Phân biệt độ dài ký tự với độ dài byte khi xử lý dữ liệu đa byte.
- Xử lý `NULL` và tránh vô tình biến dữ liệu chưa biết thành chuỗi rỗng hoặc giá trị mặc định.
- Thiết kế quy trình chuẩn hóa dữ liệu có thể kiểm tra, lặp lại và khôi phục.
- Áp dụng các hàm chuỗi trong `SELECT` để xem trước và trong `UPDATE` để cập nhật dữ liệu có kiểm soát.

## 1. Bộ dữ liệu thực hành

Các ví dụ dùng bảng nhập dữ liệu khách hàng có thể chứa định dạng không đồng nhất. Hãy chạy trong database sandbox:

```sql
CREATE TABLE customer_import_text (
    import_id BIGINT UNSIGNED NOT NULL,
    raw_customer_code VARCHAR(30) NULL,
    raw_full_name VARCHAR(120) NULL,
    raw_phone VARCHAR(40) NULL,
    source_system VARCHAR(40) NOT NULL,
    PRIMARY KEY (import_id)
) ENGINE = InnoDB
  DEFAULT CHARACTER SET = utf8mb4;

INSERT INTO customer_import_text
    (import_id, raw_customer_code, raw_full_name, raw_phone, source_system)
VALUES
    (1, '  C-17  ', '  Nguyễn An  ', '090-123-4567', 'legacy_a'),
    (2, 'C-8', 'Trần  Bình', '(090) 222 3333', 'partner_b'),
    (3, '  C-105', 'Lê Chi ', '+84 912 345 678', 'partner_b'),
    (4, NULL, '  Phạm Dũng', NULL, 'legacy_a'),
    (5, 'SKU-0009', 'Đặng Hoa', '090.444.5555', 'manual');
```

Xem dữ liệu gốc:

```sql
SELECT
    import_id,
    raw_customer_code,
    raw_full_name,
    raw_phone,
    source_system
FROM customer_import_text
ORDER BY import_id;
```

Tên cột có tiền tố `raw_` nhắc rằng đây là giá trị nhận từ nguồn. Trong bài học, các phép biến đổi được tính thành cột kết quả để có thể so sánh trước/sau.

## 2. TRIM(): loại bỏ ký tự ở đầu và cuối

`TRIM()` loại bỏ khoảng trắng ở hai đầu chuỗi theo mặc định:

```sql
SELECT
    raw_full_name,
    TRIM(raw_full_name) AS clean_name
FROM customer_import_text;
```

Ví dụ, giá trị `'  Nguyễn An  '` trở thành `'Nguyễn An'`. Các khoảng trắng nằm giữa `Nguyễn` và `An` vẫn được giữ nguyên. `TRIM()` không tự gộp nhiều khoảng trắng nội bộ thành một khoảng trắng.

### 2.1. Chỉ định phía cần loại bỏ

MySQL hỗ trợ các hướng `BOTH`, `LEADING` và `TRAILING`:

```sql
SELECT
    TRIM(BOTH FROM '  MySQL  ') AS trim_both,
    TRIM(LEADING FROM '  MySQL  ') AS trim_leading,
    TRIM(TRAILING FROM '  MySQL  ') AS trim_trailing;
```

| Cú pháp | Kết quả với chuỗi `'  MySQL  '` |
|---|---|
| `TRIM(BOTH FROM str)` | `'MySQL'` |
| `TRIM(LEADING FROM str)` | `'MySQL  '` |
| `TRIM(TRAILING FROM str)` | `'  MySQL'` |

Nếu không chỉ định hướng, `TRIM(str)` tương đương loại bỏ khoảng trắng ở cả hai đầu.

### 2.2. Loại bỏ một chuỗi xác định

Bạn có thể chỉ định `remstr` để loại bỏ chuỗi con ở đầu, cuối hoặc cả hai đầu:

```sql
SELECT
    TRIM(LEADING '0' FROM '000045') AS without_leading_zeroes,
    TRIM(TRAILING '.' FROM 'report...') AS without_trailing_dots,
    TRIM(BOTH '-' FROM '---A-102---') AS without_outer_hyphens;
```

Kết quả lần lượt là `'45'`, `'report'` và `'A-102'`. Chuỗi `remstr` là chuỗi cần khớp ở rìa, không phải một tập ký tự tùy ý để xóa ở mọi vị trí. Ví dụ, `TRIM(BOTH '-' FROM 'A-102')` vẫn giữ dấu gạch nối ở giữa.

Có thể chỉ định chuỗi nhiều ký tự:

```sql
SELECT TRIM(BOTH 'ab' FROM 'ababHelloabab') AS result;
```

Kết quả là `'Hello'`. Nếu chỉ muốn loại ký tự ở một đầu, dùng `LEADING` hoặc `TRAILING` thay cho `BOTH`.

### 2.3. TRIM không phải hàm xóa mọi loại whitespace

Mặc định, `TRIM(str)` xử lý ký tự space thông thường ở hai đầu. Không nên giả định nó tự xóa tab, xuống dòng, carriage return hoặc non-breaking space. Các ký tự đó có thể xuất hiện khi nhập dữ liệu từ file hoặc copy từ trang web.

Có thể xử lý một số ký tự điều khiển ASCII bằng cách thay chúng thành space rồi trim:

```sql
SELECT
    TRIM(
        REPLACE(
            REPLACE(raw_full_name, CHAR(9), ' '),
            CHAR(10), ' '
        )
    ) AS cleaned_name
FROM customer_import_text;
```

`CHAR(9)` là tab ngang và `CHAR(10)` là line feed. Nếu dữ liệu có carriage return, có thể xử lý thêm `CHAR(13)`. Quy tắc này chỉ xử lý những ký tự được nêu; nó không phải bộ chuẩn hóa toàn bộ Unicode whitespace.

Với MySQL 8.0, `REGEXP_REPLACE()` có thể hỗ trợ quy tắc phức tạp hơn, chẳng hạn thay chuỗi whitespace liên tiếp bằng một space:

```sql
SELECT REGEXP_REPLACE(
    TRIM(raw_full_name),
    '[[:space:]]+',
    ' '
) AS normalized_name
FROM customer_import_text;
```

Hãy kiểm tra hành vi của regex trên bộ dữ liệu thực tế và phiên bản MySQL đang dùng. Không dùng một biểu thức regex chung nếu quy tắc nghiệp vụ cần phân biệt khoảng trắng có ý nghĩa.

## 3. REPLACE(): thay thế chuỗi con

`REPLACE(str, from_str, to_str)` trả về chuỗi trong đó mọi lần xuất hiện của `from_str` được thay bằng `to_str`:

```sql
SELECT
    raw_phone,
    REPLACE(raw_phone, '-', '') AS phone_without_hyphens
FROM customer_import_text;
```

Ví dụ `'090-123-4567'` trở thành `'0901234567'`. Hàm thay thế trên toàn chuỗi, không chỉ ở đầu hoặc cuối.

### 3.1. Thay nhiều loại dấu phân cách

Có thể lồng nhiều lần `REPLACE()` để bỏ các dấu phân cách đã biết:

```sql
SELECT
    raw_phone,
    REPLACE(
        REPLACE(
            REPLACE(
                REPLACE(TRIM(raw_phone), ' ', ''),
                '-', ''
            ),
            '(',
            ''
        ),
        ')',
        ''
    ) AS phone_without_common_separators
FROM customer_import_text;
```

Biểu thức trên loại bỏ space, dấu gạch nối và ngoặc tròn. Nó vẫn giữ dấu `+`, dấu chấm và các ký tự khác. Đây là chủ ý: chỉ xóa các dấu phân cách đã được xác định. Nếu hệ thống cần chuẩn hóa số điện thoại quốc tế, phải có quy tắc riêng về mã quốc gia, số 0 đầu và định dạng E.164; không xóa dấu cộng hoặc số 0 một cách tùy tiện.

### 3.2. REPLACE phân biệt hoa thường

Trong MySQL, `REPLACE()` thực hiện so khớp có phân biệt chữ hoa/chữ thường:

```sql
SELECT
    REPLACE('MySQL mysql MYSQL', 'mysql', 'DB') AS replaced_value;
```

Chỉ đoạn `mysql` viết thường được thay. Đừng suy luận hành vi của `REPLACE()` từ collation không phân biệt hoa thường của cột. Nếu cần chuẩn hóa hoa/thường, hãy xác định rõ quy tắc và dùng các hàm chuyển chữ như `LOWER()` hoặc `UPPER()` ở bước phù hợp; không đổi chữ hoa/thường của dữ liệu định danh nếu nghiệp vụ xem chúng là khác nhau.

### 3.3. REPLACE không phải tìm kiếm bằng biểu thức chính quy

`REPLACE()` tìm chuỗi con chính xác, không hiểu wildcard hay regex:

```sql
SELECT
    REPLACE('A-001-A-002', '-', '/') AS result,
    REPLACE('A-001-A-002', 'A-00', 'X') AS another_result;
```

Nếu cần mẫu linh hoạt, MySQL có các hàm regex như `REGEXP_REPLACE()` trong MySQL 8.0. Nhưng regex có thể khó đọc và tốn chi phí hơn; với một chuỗi con cố định, `REPLACE()` thường trực tiếp hơn.

### 3.4. Thay thế lặp lại và thứ tự biến đổi

Mỗi lần gọi `REPLACE()` thực hiện một lượt thay thế. Không phải mọi quy tắc đều được lặp tự động đến khi chuỗi ổn định. Ví dụ:

```sql
SELECT REPLACE('------', '--', '-') AS one_pass;
```

Một lượt có thể còn lại nhiều dấu gạch nối. Nếu mục tiêu là gộp một chuỗi dấu lặp bất kỳ thành một dấu, dùng regex hoặc quy trình lặp có giới hạn và kiểm thử rõ ràng. Thứ tự các lần thay thế lồng nhau cũng có thể làm thay đổi kết quả; hãy thử trên dữ liệu biên trước khi áp dụng.

## 4. LPAD(): đệm chuỗi ở bên trái

`LPAD(str, len, padstr)` tạo chuỗi có độ dài `len` ký tự bằng cách thêm `padstr` vào bên trái khi chuỗi ban đầu ngắn hơn:

```sql
SELECT
    LPAD('42', 5, '0') AS padded_number,
    LPAD('A7', 6, 'XY') AS padded_code;
```

Kết quả:

| Biểu thức | Kết quả |
|---|---|
| `LPAD('42', 5, '0')` | `'00042'` |
| `LPAD('A7', 6, 'XY')` | `'XYXYA7'` |

MySQL lặp chuỗi đệm khi cần và chỉ dùng phần cần thiết để đạt độ dài đích. Với `padstr` nhiều ký tự, phần cuối có thể bị cắt để vừa đủ độ dài.

### 4.1. Độ dài đích ngắn hơn chuỗi gốc

Nếu `str` dài hơn `len`, `LPAD()` trả về phần đầu của chuỗi đã bị cắt đến độ dài `len`:

```sql
SELECT LPAD('CUSTOMER-1024', 8, '0') AS shortened_code;
```

Kết quả là `'CUSTOMER'`. Đây là hành vi dễ gây mất dữ liệu nếu bạn nghĩ `LPAD()` chỉ thêm ký tự mà không bao giờ cắt chuỗi. Trước khi dùng trên dữ liệu thật, hãy bảo đảm độ dài đầu vào không vượt quá độ dài đích hoặc kiểm tra riêng trường hợp đó.

### 4.2. Dùng LPAD để chuẩn hóa mã có số 0 đầu

Nếu mã nghiệp vụ có độ dài cố định, ví dụ mã chi nhánh gồm năm ký tự số, có thể dùng:

```sql
SELECT
    branch_number,
    LPAD(CAST(branch_number AS CHAR), 5, '0') AS branch_code
FROM branch_source;
```

Tuy nhiên, nếu mã đã được lưu dưới dạng chuỗi và số 0 đầu có ý nghĩa, không nên chuyển sang kiểu số rồi chuyển lại chuỗi vì số 0 đầu sẽ mất. Hãy lưu mã định danh dưới dạng chuỗi và chỉ dùng `LPAD()` khi quy tắc nghiệp vụ xác định rõ độ dài và cách đệm.

## 5. RPAD(): đệm chuỗi ở bên phải

`RPAD(str, len, padstr)` tương tự `LPAD()` nhưng thêm ký tự vào bên phải:

```sql
SELECT
    RPAD('A7', 6, '.') AS display_code,
    RPAD('OK', 8, ' ') AS fixed_width_label;
```

Kết quả:

| Biểu thức | Kết quả |
|---|---|
| `RPAD('A7', 6, '.')` | `'A7....'` |
| `RPAD('OK', 8, ' ')` | `'OK      '` |

RPAD có thể hữu ích khi tạo chuỗi hiển thị có độ rộng cố định hoặc chuẩn bị dữ liệu xuất theo định dạng văn bản. Với hệ thống trao đổi dữ liệu hiện đại, CSV/JSON thường không cần đệm khoảng trắng; chỉ dùng khi định dạng đích yêu cầu.

Giống `LPAD()`, nếu chuỗi đầu vào dài hơn `len` thì kết quả bị cắt về độ dài đích. Không dùng `RPAD()` để “bảo đảm tối thiểu” mà bỏ qua khả năng cắt dữ liệu.

## 6. Độ dài ký tự và độ dài byte

MySQL xử lý chuỗi đa byte theo character set của giá trị. Với `LPAD()` và `RPAD()`, tham số `len` là số ký tự, không phải số byte. `CHAR_LENGTH()` cũng đếm ký tự, trong khi `LENGTH()` đếm byte.

```sql
SET NAMES utf8mb4;

SELECT
    'Mã😀' AS original_value,
    CHAR_LENGTH('Mã😀') AS character_count,
    LENGTH('Mã😀') AS byte_count,
    LPAD('Mã😀', 5, '0') AS padded_value,
    CHAR_LENGTH(LPAD('Mã😀', 5, '0')) AS padded_character_count,
    LENGTH(LPAD('Mã😀', 5, '0')) AS padded_byte_count;
```

Chuỗi `'Mã😀'` có ba code point theo cách đếm của MySQL với chuỗi này, nhưng số byte UTF-8 lớn hơn ba. Sau khi đệm đến năm ký tự, `CHAR_LENGTH()` trả về năm; `LENGTH()` phản ánh số byte thực tế theo encoding.

Khi thiết kế cột `VARCHAR(n)`, `n` là giới hạn ký tự. Khi kiểm tra kích thước truyền qua mạng, dung lượng lưu trữ hoặc giới hạn index, số byte cũng quan trọng. Không thay thế `CHAR_LENGTH()` bằng `LENGTH()` nếu câu hỏi nghiệp vụ là số ký tự.

## 7. NULL và chuỗi rỗng

Các hàm chuỗi trên trả về `NULL` nếu đối số cần thiết là `NULL`. Ví dụ:

```sql
SELECT
    TRIM(NULL) AS trim_null,
    REPLACE('ABC', NULL, 'X') AS replace_null_source,
    LPAD(NULL, 5, '0') AS lpad_null,
    RPAD('ABC', NULL, '0') AS rpad_null;
```

Kết quả các biểu thức là `NULL`. Điều này khác với chuỗi rỗng `''`:

```sql
SELECT
    TRIM('   ') AS trimmed_spaces,
    CHAR_LENGTH(TRIM('   ')) AS trimmed_length,
    CHAR_LENGTH('') AS empty_length,
    CHAR_LENGTH(NULL) AS null_length;
```

Sau `TRIM()`, chuỗi chỉ chứa space trở thành chuỗi rỗng có độ dài 0. `NULL` vẫn là giá trị chưa biết/không có, không đồng nghĩa chuỗi rỗng.

Nếu nghiệp vụ muốn thay `NULL` bằng chuỗi rỗng, hãy viết rõ:

```sql
SELECT TRIM(COALESCE(raw_full_name, '')) AS display_name
FROM customer_import_text;
```

Chỉ dùng `COALESCE()` khi quy tắc nghiệp vụ xác nhận giá trị thiếu được hiển thị như chuỗi rỗng. Nếu `NULL` biểu thị chưa thu thập được thông tin, giữ nguyên nó sẽ bảo toàn ý nghĩa tốt hơn.

## 8. Kết hợp các hàm để chuẩn hóa dữ liệu

Một bước chuẩn hóa có thể gồm nhiều phép biến đổi theo thứ tự: loại khoảng trắng ở rìa, loại dấu phân cách đã biết, sau đó đệm mã theo quy tắc. Ví dụ chuẩn hóa mã khách hàng:

```sql
SELECT
    import_id,
    raw_customer_code,
    TRIM(raw_customer_code) AS trimmed_code,
    REPLACE(TRIM(raw_customer_code), '-', '') AS code_without_hyphen
FROM customer_import_text
ORDER BY import_id;
```

Kết quả cho thấy từng bước biến đổi. Với mã `C-17`, việc loại dấu gạch nối tạo `C17`; với mã có tiền tố `SKU-`, loại dấu nối có thể không đúng quy tắc. Đừng áp dụng cùng một phép biến đổi cho các loại mã khác nhau nếu chúng có ý nghĩa khác nhau.

### 8.1. Chuẩn hóa số điện thoại theo quy tắc rõ ràng

Ví dụ dưới đây chỉ loại các dấu phân cách phổ biến, vẫn giữ dấu cộng và chữ số:

```sql
SELECT
    import_id,
    raw_phone,
    CASE
        WHEN raw_phone IS NULL THEN NULL
        ELSE REPLACE(
            REPLACE(
                REPLACE(
                    REPLACE(TRIM(raw_phone), ' ', ''),
                    '-', ''
                ),
                '(',
                ''
            ),
            ')',
            ''
        )
    END AS phone_compact
FROM customer_import_text
ORDER BY import_id;
```

Kết quả có thể biến `'090-123-4567'` thành `'0901234567'` và `'+84 912 345 678'` thành `'+84912345678'`. Đây mới là bước bỏ dấu phân cách, chưa phải xác thực số điện thoại hoặc chuyển đổi sang chuẩn quốc tế. Cần quy tắc riêng cho mã quốc gia, số nội địa, số máy lẻ và độ dài hợp lệ.

### 8.2. Chuẩn hóa mã định danh có độ dài cố định

Nếu nguồn gửi mã chi nhánh dạng số và nghiệp vụ yêu cầu đúng sáu ký tự:

```sql
SELECT
    branch_code_raw,
    LPAD(TRIM(branch_code_raw), 6, '0') AS branch_code_normalized
FROM branch_import;
```

Trước khi áp dụng, kiểm tra độ dài đầu vào:

```sql
SELECT branch_code_raw, CHAR_LENGTH(TRIM(branch_code_raw)) AS source_length
FROM branch_import
WHERE branch_code_raw IS NOT NULL
  AND CHAR_LENGTH(TRIM(branch_code_raw)) > 6;
```

Nếu có mã dài hơn sáu ký tự, `LPAD()` sẽ cắt phần cuối của chuỗi về sáu ký tự theo quy tắc của hàm. Các hàng đó cần được xử lý riêng, không đưa thẳng vào bước chuẩn hóa.

## 9. Chuẩn hóa dữ liệu không đồng nghĩa với chuẩn hóa quan hệ

Trong ngữ cảnh bài này, chuẩn hóa dữ liệu là làm cho cách biểu diễn chuỗi nhất quán: loại khoảng trắng không cần thiết, thống nhất dấu phân cách, định dạng mã hoặc tạo chuỗi hiển thị. Nó khác với chuẩn hóa cơ sở dữ liệu quan hệ (normalization) như 1NF, 2NF và 3NF, vốn tổ chức bảng để giảm dư thừa và bất thường cập nhật.

Một số nguyên tắc khi thiết kế quy tắc chuẩn hóa chuỗi:

- **Giữ dữ liệu gốc khi cần truy vết.** Lưu giá trị nhận từ nguồn trong cột raw hoặc bảng staging nếu cần audit và xử lý lại.
- **Tách chuẩn hóa khỏi xác thực.** Xóa dấu gạch nối không chứng minh mã sau biến đổi hợp lệ.
- **Định nghĩa quy tắc theo loại dữ liệu.** Tên người, email, số điện thoại, SKU và mã tài khoản không có cùng quy tắc.
- **Bảo đảm tính lặp lại.** Chạy lại cùng một quy trình không nên tiếp tục làm thay đổi giá trị đã chuẩn hóa ngoài dự kiến.
- **Không làm mất thông tin.** Cẩn thận với thao tác cắt chuỗi, bỏ số 0 đầu, bỏ dấu cộng hoặc xóa ký tự có ý nghĩa.
- **Xem xét Unicode.** `TRIM()` và `REPLACE()` không thay thế quy trình chuẩn hóa Unicode NFC/NFKC trong ứng dụng.

MySQL có thể so sánh chuỗi theo collation, nhưng quy tắc so sánh không đồng nghĩa với việc thay đổi byte hoặc chuẩn hóa dạng mã hóa Unicode đã lưu. Nếu cần chuẩn hóa canonical composition, compatibility form hoặc xử lý ký tự kết hợp, nên dùng thư viện Unicode phù hợp ở tầng ứng dụng và lưu kết quả theo một quy ước thống nhất.

## 10. Xem trước trước khi UPDATE

Không nên cập nhật dữ liệu hàng loạt ngay sau khi viết biểu thức. Trước tiên, chạy `SELECT` để xem giá trị cũ và mới:

```sql
SELECT
    import_id,
    raw_customer_code AS old_code,
    TRIM(raw_customer_code) AS proposed_code,
    CHAR_LENGTH(raw_customer_code) AS old_length,
    CHAR_LENGTH(TRIM(raw_customer_code)) AS new_length
FROM customer_import_text
ORDER BY import_id;
```

Tiếp theo, thống kê số hàng sẽ thay đổi:

```sql
SELECT COUNT(*) AS rows_to_change
FROM customer_import_text
WHERE raw_customer_code IS NOT NULL
  AND raw_customer_code <> TRIM(raw_customer_code);
```

Hãy kiểm tra thêm:

- Có hai giá trị nguồn khác nhau trở thành cùng một giá trị chuẩn hóa không?
- Kết quả có vượt hoặc bị cắt giới hạn cột đích không?
- Unique index có thể bị vi phạm sau chuẩn hóa không?
- Có ký tự nào bị xóa nhưng mang ý nghĩa nghiệp vụ không?
- Giá trị `NULL` có được giữ đúng ý nghĩa không?

Ví dụ tìm mã chuẩn hóa bị trùng:

```sql
SELECT
    TRIM(raw_customer_code) AS normalized_code,
    COUNT(*) AS row_count
FROM customer_import_text
WHERE raw_customer_code IS NOT NULL
GROUP BY TRIM(raw_customer_code)
HAVING COUNT(*) > 1;
```

Đối với các phép biến đổi phức tạp, nên tạo bảng staging hoặc cột chuẩn hóa riêng để kiểm tra và đối soát trước khi thay thế dữ liệu gốc.

## 11. Cập nhật dữ liệu có kiểm soát

Sau khi xem trước và xác nhận quy tắc, có thể cập nhật một cột đích riêng. Ví dụ:

```sql
ALTER TABLE customer_import_text
    ADD COLUMN normalized_customer_code VARCHAR(30) NULL;

UPDATE customer_import_text
SET normalized_customer_code = TRIM(raw_customer_code)
WHERE raw_customer_code IS NOT NULL;
```

Nếu muốn cập nhật trực tiếp cột nguồn, hãy sao lưu hoặc giữ bản raw ở nơi khác trước. Với InnoDB, có thể thử một nhóm nhỏ trong transaction:

```sql
START TRANSACTION;

UPDATE customer_import_text
SET raw_customer_code = TRIM(raw_customer_code)
WHERE raw_customer_code IS NOT NULL
  AND raw_customer_code <> TRIM(raw_customer_code);

SELECT import_id, raw_customer_code
FROM customer_import_text
ORDER BY import_id;

-- Sau khi kiểm tra kết quả:
ROLLBACK;
-- Chỉ thay ROLLBACK bằng COMMIT khi kết quả đã được xác nhận.
```

Đoạn trên là bài thực hành thử nghiệm; `ROLLBACK` hoàn tác thay đổi dữ liệu InnoDB trong transaction. Trên production, cần kế hoạch sao lưu, giới hạn phạm vi cập nhật, kiểm tra số hàng bị tác động và cân nhắc khóa/replication. Không chạy `UPDATE` không có `WHERE` chỉ vì muốn chuẩn hóa toàn bảng; nếu thật sự cần toàn bộ bảng, hãy xác định rõ phạm vi và chia lô khi thích hợp.

### 11.1. Tính lặp lại và idempotency

Một phép chuẩn hóa tốt thường có tính idempotent: áp dụng nhiều lần cho giá trị đã chuẩn hóa không làm thay đổi kết quả nữa. Ví dụ:

```sql
SELECT
    TRIM(TRIM('  MySQL  ')) AS repeated_trim,
    REPLACE(REPLACE('A-B', '-', ''), '-', '') AS repeated_replace;
```

Tuy nhiên, không phải mọi chuỗi lệnh `REPLACE()` lồng nhau đều tự tạo được dạng chuẩn cuối cùng. Nếu thay thế một chuỗi tạo ra chuỗi con mới phù hợp với lần thay thế trước, thứ tự xử lý có thể ảnh hưởng kết quả. Hãy viết quy tắc sao cho rõ, thử chạy hai lần trên cùng dữ liệu và so sánh kết quả.

## 12. Collation, so sánh và chuẩn hóa chuỗi

Collation quyết định cách MySQL so sánh và sắp xếp chuỗi. Ví dụ, collation không phân biệt hoa thường có thể xem `'abc'` và `'ABC'` là bằng nhau trong phép so sánh, nhưng điều đó không có nghĩa dữ liệu được lưu tự động chuyển thành chữ thường.

`REPLACE()` có quy tắc so khớp phân biệt hoa thường. Vì vậy, một truy vấn so sánh cột theo collation không phân biệt hoa thường có thể cho kết quả khác với phép thay thế chuỗi con:

```sql
SELECT
    'ABC' = 'abc' AS collation_comparison,
    REPLACE('ABC', 'abc', 'X') AS replace_result;
```

Kết quả của phép so sánh literal phụ thuộc collation kết nối/literal; phép `REPLACE()` vẫn so khớp phân biệt hoa thường và không thay `ABC` bằng `X` trong ví dụ này. Khi cần kết quả nhất quán, hãy chỉ rõ collation hoặc chuẩn hóa giá trị theo quy tắc ứng dụng trước khi so sánh.

Không dùng `TRIM()` hoặc `REPLACE()` như một cách thay thế cho unique constraint. Hai request đồng thời vẫn có thể tạo giá trị trùng sau chuẩn hóa. Nếu giá trị chuẩn hóa phải duy nhất, cần lưu kết quả chuẩn hóa ở cột phù hợp và bảo vệ bằng unique index theo collation đã chọn.

## 13. Những lỗi thường gặp

- Nghĩ `TRIM()` xóa mọi khoảng trắng ở mọi vị trí; hàm mặc định chỉ loại space ở hai đầu.
- Dùng `TRIM()` để xóa dấu phân cách nằm giữa chuỗi; cần dùng `REPLACE()` nếu quy tắc yêu cầu.
- Coi `remstr` của `TRIM()` là tập ký tự; nó là chuỗi cần loại ở rìa.
- Giả định `TRIM()` tự xử lý tab, xuống dòng và mọi Unicode whitespace.
- Nghĩ `REPLACE()` hỗ trợ regex hoặc tìm kiếm không phân biệt hoa thường.
- Lồng nhiều `REPLACE()` mà không kiểm tra thứ tự và kết quả trung gian.
- Dùng `LPAD()`/`RPAD()` với độ dài đích nhỏ hơn chuỗi nguồn, vô tình cắt dữ liệu.
- Nhầm `len` trong `LPAD()`/`RPAD()` là số byte thay vì số ký tự.
- Chuyển mã định danh sang số rồi làm mất số 0 ở đầu.
- Đổi `NULL` thành chuỗi rỗng mà không xác định ý nghĩa nghiệp vụ.
- Cập nhật trực tiếp dữ liệu nguồn mà không xem trước, sao lưu hoặc kiểm tra duplicate.
- Cho rằng collation không phân biệt hoa thường sẽ tự chuyển chuỗi đã lưu thành chữ thường.
- Dùng các hàm chuỗi để xác thực dữ liệu thay cho quy tắc nghiệp vụ và constraint phù hợp.

## 14. Checklist chuẩn hóa dữ liệu chuỗi

- Đã xác định mục tiêu: loại khoảng trắng, thay dấu phân cách, tạo mã có độ dài cố định hay định dạng hiển thị.
- Đã xác định chính xác ký tự hoặc chuỗi con cần xử lý và vị trí được phép biến đổi.
- Đã kiểm tra `NULL`, chuỗi rỗng và chuỗi chỉ chứa whitespace.
- Đã kiểm tra ký tự đa byte bằng `CHAR_LENGTH()` và `LENGTH()` khi cần.
- Đã xác minh `REPLACE()` phân biệt hoa thường và không phải regex.
- Đã bảo đảm `LPAD()`/`RPAD()` không cắt chuỗi đầu vào ngoài ý muốn.
- Đã xem trước giá trị cũ/mới bằng `SELECT` và thống kê số hàng bị ảnh hưởng.
- Đã tìm giá trị trùng sau chuẩn hóa trước khi tạo hoặc duy trì unique constraint.
- Đã giữ dữ liệu raw hoặc có bản sao lưu để truy vết và khôi phục.
- Đã thử quy trình hai lần để xác nhận tính lặp lại.
- Đã cập nhật trong phạm vi có kiểm soát và xác minh số hàng sau thay đổi.
- Đã xử lý chuẩn hóa Unicode ở tầng phù hợp nếu cần NFC/NFKC hoặc quy tắc ngoài phạm vi các hàm SQL này.

`TRIM()`, `REPLACE()`, `LPAD()` và `RPAD()` là các công cụ cơ bản để làm sạch và định dạng chuỗi trong MySQL. `TRIM()` xử lý rìa chuỗi, `REPLACE()` thay chuỗi con ở mọi vị trí, còn `LPAD()`/`RPAD()` tạo độ dài ký tự theo yêu cầu và có thể cắt chuỗi nếu độ dài đích nhỏ hơn đầu vào. Khi kết hợp chúng thành quy trình chuẩn hóa, hãy xác định quy tắc theo từng loại dữ liệu, giữ giá trị nguồn khi cần, xem trước kết quả và kiểm tra duplicate trước khi cập nhật hàng loạt.
