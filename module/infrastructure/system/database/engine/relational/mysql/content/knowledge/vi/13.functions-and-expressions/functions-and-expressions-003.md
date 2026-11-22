# CONCAT, CONCAT_WS và ảnh hưởng của NULL

MySQL cung cấp `CONCAT()` và `CONCAT_WS()` để ghép nhiều giá trị thành một chuỗi. Hai hàm có vẻ giống nhau nhưng xử lý `NULL` rất khác nhau: `CONCAT()` trả về `NULL` nếu bất kỳ đối số nào là `NULL`, trong khi `CONCAT_WS()` bỏ qua các đối số `NULL` nằm sau đối số phân cách. Đối số phân cách của `CONCAT_WS()` mà là `NULL` thì toàn bộ kết quả cũng là `NULL`.

Khác biệt này ảnh hưởng trực tiếp tới cách tạo tên đầy đủ, địa chỉ, mã hiển thị, chuỗi tìm kiếm và dữ liệu báo cáo. Trong module `DATABASE_MYSQL`, cần hiểu rõ cách ghép chuỗi, chuyển đổi kiểu, character set/collation và ý nghĩa của `NULL` để viết biểu thức SQL đúng nghiệp vụ và tránh dữ liệu đầu ra bất ngờ.

## Mục tiêu

Sau bài này, bạn có thể:

- Dùng `CONCAT()` để ghép các chuỗi và hiểu quy tắc lan truyền `NULL`.
- Dùng `CONCAT_WS()` với separator và hiểu cách bỏ qua đối số `NULL`.
- Phân biệt `NULL`, chuỗi rỗng và chuỗi chỉ chứa khoảng trắng.
- Kết hợp `NULLIF()`, `COALESCE()`, `IFNULL()` và `TRIM()` để chuẩn hóa dữ liệu trước khi ghép.
- Ghép chuỗi có số, ngày giờ và giá trị binary một cách có chủ đích.
- Nhận diện ảnh hưởng của character set/collation và độ dài kết quả.
- Tránh dùng biểu thức ghép chuỗi làm mất khả năng tận dụng index khi lọc dữ liệu.

## 1. CONCAT(): ghép các đối số

`CONCAT(str1, str2, ...)` nối các đối số theo đúng thứ tự và trả về một chuỗi. MySQL chuyển các đối số không phải chuỗi sang dạng chuỗi khi cần.

```sql
SELECT CONCAT('My', 'SQL') AS result;
-- MySQL

SELECT CONCAT('Order-', 2026, '-', 105) AS order_code;
-- Order-2026-105
```

Không có separator tự động giữa các đối số. Nếu cần dấu cách, dấu gạch ngang hoặc dấu phân cách khác, phải truyền nó như một đối số riêng:

```sql
SELECT CONCAT('Nguyen', ' ', 'An') AS full_name;
-- Nguyen An
```

### 1.1. CONCAT trả NULL nếu một đối số là NULL

Đây là quy tắc quan trọng nhất của `CONCAT()`:

```sql
SELECT
    CONCAT('A', 'B') AS both_present,
    CONCAT('A', NULL, 'B') AS one_null,
    CONCAT(NULL, NULL) AS all_null;
```

Kết quả:

| Biểu thức | Kết quả |
|---|---|
| `CONCAT('A', 'B')` | `'AB'` |
| `CONCAT('A', NULL, 'B')` | `NULL` |
| `CONCAT(NULL, NULL)` | `NULL` |

MySQL không tự bỏ qua đối số `NULL` trong `CONCAT()`. Chỉ một đối số `NULL` cũng khiến toàn bộ biểu thức thành `NULL`.

Ví dụ, một khách hàng chưa có tên đệm:

```sql
SELECT CONCAT(first_name, ' ', middle_name, ' ', last_name) AS full_name
FROM customer;
```

Nếu `middle_name` là `NULL`, `full_name` cũng thành `NULL`, dù `first_name` và `last_name` có giá trị. Nếu muốn bỏ qua phần thiếu, hãy cân nhắc `CONCAT_WS()`.

### 1.2. Dùng COALESCE hoặc IFNULL khi muốn thay NULL

Nếu nghiệp vụ yêu cầu thay `NULL` bằng chuỗi mặc định, có thể xử lý trước khi ghép:

```sql
SELECT CONCAT(
    first_name,
    ' ',
    COALESCE(middle_name, ''),
    ' ',
    last_name
) AS full_name
FROM customer;
```

`COALESCE(value, fallback)` trả về đối số khác `NULL` đầu tiên. `IFNULL(value, fallback)` là hàm hai đối số, trả về `fallback` khi `value` là `NULL`.

```sql
SELECT
    CONCAT('Phone: ', IFNULL(phone, 'Chưa cung cấp')) AS phone_label,
    CONCAT('Note: ', COALESCE(note, '(không có ghi chú)')) AS note_label
FROM customer;
```

Việc thay `NULL` bằng chuỗi rỗng có thể tạo ra khoảng trắng thừa, ví dụ hai dấu cách liên tiếp khi tên đệm bị thiếu. Có thể dùng `TRIM()` để loại bỏ khoảng trắng ở hai đầu, hoặc dùng `CONCAT_WS()` để bỏ qua thành phần `NULL`.

## 2. CONCAT_WS(): ghép chuỗi có separator

`CONCAT_WS(separator, str1, str2, ...)` có nghĩa là “concatenate with separator”. MySQL chèn `separator` giữa các đối số giá trị được ghép.

```sql
SELECT CONCAT_WS('-', '2026', '11', '19') AS date_code;
-- 2026-11-19

SELECT CONCAT_WS(' ', 'Nguyen', 'Van', 'An') AS full_name;
-- Nguyen Van An
```

Không cần tự truyền separator ở giữa từng cặp đối số. Separator chỉ được truyền một lần ở vị trí đầu tiên.

### 2.1. CONCAT_WS bỏ qua đối số NULL phía sau separator

Khác với `CONCAT()`, `CONCAT_WS()` bỏ qua các đối số `NULL` sau đối số separator:

```sql
SELECT
    CONCAT_WS('-', 'A', NULL, 'B') AS skipped_null,
    CONCAT_WS('-', 'A', '', 'B') AS empty_value,
    CONCAT_WS('-', NULL, 'B') AS first_value_null;
```

Kết quả:

| Biểu thức | Kết quả | Giải thích |
|---|---|---|
| `CONCAT_WS('-', 'A', NULL, 'B')` | `'A-B'` | Đối số `NULL` bị bỏ qua, không tạo separator thừa |
| `CONCAT_WS('-', 'A', '', 'B')` | `'A--B'` | Chuỗi rỗng không phải `NULL`, vẫn chiếm một vị trí |
| `CONCAT_WS('-', NULL, 'B')` | `'B'` | `NULL` bị bỏ qua; chỉ còn một giá trị nên không có separator ở đầu |

Điểm cần nhớ: `CONCAT_WS()` bỏ qua `NULL`, không bỏ qua chuỗi rỗng (`''`). Nếu dữ liệu có cả `NULL` lẫn chuỗi rỗng, hãy chuẩn hóa chuỗi rỗng thành `NULL` trước khi ghép nếu nghiệp vụ xem chúng đều là “không có giá trị”.

### 2.2. Separator NULL làm toàn bộ kết quả NULL

Đối số đầu tiên là separator, không được xử lý giống các đối số giá trị phía sau:

```sql
SELECT CONCAT_WS(NULL, 'A', 'B') AS result;
-- NULL
```

Ngay cả khi mọi giá trị phía sau đều có dữ liệu, separator `NULL` vẫn làm kết quả thành `NULL`. Nếu separator được lấy từ một cột hoặc tham số có thể `NULL`, hãy bảo đảm nó có giá trị hoặc thay thế bằng separator mặc định:

```sql
SELECT CONCAT_WS(COALESCE(separator_text, ' '), first_name, last_name)
FROM customer_profile;
```

### 2.3. Khi tất cả đối số giá trị đều NULL

Nếu separator có giá trị nhưng tất cả đối số giá trị phía sau đều `NULL`, `CONCAT_WS()` bỏ qua tất cả và trả về chuỗi rỗng:

```sql
SELECT CONCAT_WS(' ', NULL, NULL) AS result;
-- ''
```

Đây là khác biệt quan trọng so với `CONCAT(NULL, NULL)`, vốn trả `NULL`. Nếu ứng dụng cần phân biệt “không có thành phần nào” với “chuỗi đã ghép nhưng rỗng”, hãy kiểm tra các cột nguồn hoặc dùng biểu thức trả `NULL` tường minh khi tất cả thành phần đều thiếu.

## 3. So sánh CONCAT và CONCAT_WS

| Tình huống | `CONCAT()` | `CONCAT_WS()` |
|---|---|---|
| Ghép các giá trị có dữ liệu | Nối trực tiếp, không tự thêm separator | Nối và chèn separator giữa các giá trị |
| Một đối số giá trị là `NULL` | Toàn bộ kết quả là `NULL` | Bỏ qua đối số `NULL` |
| Separator là `NULL` | Không có khái niệm separator riêng | Toàn bộ kết quả là `NULL` |
| Đối số là chuỗi rỗng | Giữ chuỗi rỗng | Giữ chuỗi rỗng và vẫn tính vị trí separator |
| Tất cả đối số giá trị là `NULL` | Kết quả `NULL` | Kết quả chuỗi rỗng nếu separator khác `NULL` |
| Dùng điển hình | Ghép mã có cấu trúc cố định, tiền tố/hậu tố | Ghép tên, địa chỉ hoặc danh sách thành phần tùy chọn |

Chọn hàm theo semantics dữ liệu. Không dùng `CONCAT_WS()` chỉ vì cú pháp ngắn hơn nếu việc bỏ qua `NULL` làm mất thông tin. Ngược lại, không dùng `CONCAT()` cho các trường tùy chọn nếu chỉ một trường thiếu đã làm mất toàn bộ chuỗi kết quả.

## 4. Phân biệt NULL, chuỗi rỗng và khoảng trắng

Ba trạng thái sau không giống nhau:

| Giá trị | Ý nghĩa thường gặp | `CONCAT_WS('-', 'A', value, 'B')` |
|---|---|---|
| `NULL` | Không có/không biết giá trị | `A-B` |
| `''` | Có giá trị chuỗi nhưng độ dài bằng 0 | `A--B` |
| `'   '` | Chuỗi có chứa khoảng trắng | `A-   -B` |

Có thể chuẩn hóa dữ liệu trước khi ghép:

```sql
SELECT CONCAT_WS(' ',
    NULLIF(TRIM(first_name), ''),
    NULLIF(TRIM(middle_name), ''),
    NULLIF(TRIM(last_name), '')
) AS full_name
FROM customer;
```

Giải thích từng hàm:

- `TRIM(value)` loại bỏ khoảng trắng ở đầu và cuối chuỗi theo quy tắc của hàm.
- `NULLIF(value, '')` trả `NULL` nếu `value` bằng chuỗi rỗng; nếu khác thì trả `value`.
- `CONCAT_WS(' ', ...)` bỏ qua các thành phần `NULL` và chỉ chèn dấu cách giữa các thành phần còn lại.

Ví dụ, nếu `first_name='Nguyen'`, `middle_name='   '` và `last_name='An'`, biểu thức trên tạo `Nguyen An`, không tạo khoảng trắng kép. Nếu tất cả các trường đều `NULL` hoặc rỗng sau chuẩn hóa, kết quả của `CONCAT_WS()` là chuỗi rỗng. Nếu nghiệp vụ muốn kết quả `NULL` trong trường hợp đó, cần thêm điều kiện:

```sql
SELECT CASE
    WHEN NULLIF(TRIM(first_name), '') IS NULL
     AND NULLIF(TRIM(middle_name), '') IS NULL
     AND NULLIF(TRIM(last_name), '') IS NULL
    THEN NULL
    ELSE CONCAT_WS(' ',
        NULLIF(TRIM(first_name), ''),
        NULLIF(TRIM(middle_name), ''),
        NULLIF(TRIM(last_name), '')
    )
END AS full_name
FROM customer;
```

Không tự động chuyển mọi chuỗi rỗng thành `NULL` trong database nếu ứng dụng đang phân biệt hai trạng thái đó. Chuẩn hóa trong biểu thức chỉ nên áp dụng khi phù hợp với quy ước dữ liệu.

## 5. Ví dụ thực tế: tên đầy đủ và địa chỉ

### 5.1. Ghép tên người dùng

Giả sử bảng hồ sơ có tên và tên đệm tùy chọn:

```sql
CREATE TABLE customer_profile (
    customer_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    first_name VARCHAR(80) NULL,
    middle_name VARCHAR(80) NULL,
    last_name VARCHAR(80) NULL,
    phone VARCHAR(30) NULL,
    PRIMARY KEY (customer_id)
) ENGINE=InnoDB
  DEFAULT CHARSET=utf8mb4;

INSERT INTO customer_profile (first_name, middle_name, last_name, phone)
VALUES
    ('Nguyen', 'Van', 'An', '0900000001'),
    ('Tran', NULL, 'Binh', NULL),
    ('Le', '', 'Chi', '0900000003'),
    (NULL, NULL, 'Dung', '0900000004');
```

Ghép bằng `CONCAT()`:

```sql
SELECT
    customer_id,
    CONCAT(first_name, ' ', middle_name, ' ', last_name) AS full_name
FROM customer_profile;
```

Các hàng thiếu tên đệm hoặc tên sẽ cho `full_name = NULL`. Nếu muốn bỏ qua phần thiếu, dùng:

```sql
SELECT
    customer_id,
    CONCAT_WS(' ', first_name, middle_name, last_name) AS full_name
FROM customer_profile;
```

Hàng có `middle_name = ''` vẫn tạo hai dấu cách liền nhau. Dùng biểu thức chuẩn hóa ở phần 4 nếu chuỗi rỗng cần được xem như trường không có dữ liệu.

### 5.2. Ghép địa chỉ có thành phần tùy chọn

```sql
SELECT CONCAT_WS(', ',
    NULLIF(TRIM(street), ''),
    NULLIF(TRIM(ward), ''),
    NULLIF(TRIM(district), ''),
    NULLIF(TRIM(city), '')
) AS full_address
FROM customer_address;
```

Nếu `ward` chưa được cung cấp, địa chỉ vẫn được ghép từ đường, quận và thành phố mà không có dấu phẩy thừa ở vị trí của phường. Nếu mọi trường đều thiếu, kết quả là chuỗi rỗng; có thể bọc bằng `NULLIF(..., '')` nếu muốn trả `NULL`.

```sql
SELECT NULLIF(
    CONCAT_WS(', ',
        NULLIF(TRIM(street), ''),
        NULLIF(TRIM(ward), ''),
        NULLIF(TRIM(district), ''),
        NULLIF(TRIM(city), '')
    ),
    ''
) AS full_address
FROM customer_address;
```

## 6. Ghép số, ngày giờ và các kiểu dữ liệu khác

`CONCAT()` và `CONCAT_WS()` có thể nhận số hoặc giá trị ngày giờ; MySQL chuyển đổi chúng sang dạng chuỗi theo quy tắc chuyển kiểu. Với dữ liệu cần định dạng ổn định, hãy chuyển đổi tường minh trước khi ghép.

### 6.1. Tạo mã hiển thị từ số

```sql
SELECT CONCAT('ORD-', order_id) AS order_code
FROM orders;
```

Nếu cần số có độ rộng cố định:

```sql
SELECT CONCAT('ORD-', LPAD(CAST(order_id AS CHAR), 8, '0')) AS order_code
FROM orders;
```

Ví dụ ID `125` thành `ORD-00000125`. Đây là chuỗi hiển thị, không nên dùng chuỗi đã định dạng làm khóa số hoặc thay thế khóa chính. Nếu ID có thể vượt độ rộng dự kiến, kiểm tra hành vi `LPAD()` vì chuỗi dài hơn độ rộng đích có thể bị cắt.

### 6.2. Định dạng ngày giờ trước khi ghép

Không dựa vào biểu diễn ngầm định của ngày giờ nếu chuỗi đầu ra cần định dạng nhất quán:

```sql
SELECT CONCAT(
    'Created on ',
    DATE_FORMAT(created_at, '%Y-%m-%d %H:%i:%s')
) AS created_label
FROM orders;
```

`DATE_FORMAT()` quy định rõ cách hiển thị ngày giờ. Với cột `TIMESTAMP`, cần thống nhất session timezone trước khi định dạng vì giá trị được hiển thị theo múi giờ của session. Nếu đầu ra cần UTC, hãy thiết lập session UTC hoặc chuyển đổi có chủ đích.

### 6.3. Ép kiểu tường minh

Khi muốn kiểm soát kiểu chuỗi đầu vào, dùng `CAST()`:

```sql
SELECT CONCAT(
    'Amount: ',
    CAST(total_amount AS CHAR)
) AS amount_label
FROM orders;
```

Đối với số tiền, nếu cần dấu phân cách hàng nghìn hoặc định dạng theo locale, có thể dùng `FORMAT()` nhưng kết quả là chuỗi đã định dạng theo locale và không nên dùng để tính toán hoặc làm khóa. Hãy giữ giá trị số ở dạng số cho tới tầng trình bày nếu có thể.

## 7. Character set, collation và binary string

Kết quả của `CONCAT()`/`CONCAT_WS()` là chuỗi được tạo từ các đối số. Character set và collation của kết quả được MySQL xác định từ các đối số theo quy tắc tổng hợp charset/collation. Nếu các đối số có collation không tương thích hoặc có coercibility gây xung đột, biểu thức có thể phát sinh lỗi `Illegal mix of collations`.

Kiểm tra charset/collation của cột:

```sql
SHOW FULL COLUMNS FROM customer_profile;
```

Có thể xem metadata biểu thức:

```sql
SELECT
    CHARSET(CONCAT(first_name, last_name)) AS result_charset,
    COLLATION(CONCAT(first_name, last_name)) AS result_collation
FROM customer_profile
LIMIT 1;
```

Nếu cần thống nhất quy tắc so sánh, chuyển đổi hoặc áp collation tường minh:

```sql
SELECT CONCAT(
    first_name COLLATE utf8mb4_0900_ai_ci,
    ' ',
    last_name COLLATE utf8mb4_0900_ai_ci
) AS full_name
FROM customer_profile;
```

Tên collation phải tồn tại trên phiên bản MySQL đang dùng và charset của biểu thức phải tương thích. Không ép collation tùy tiện để làm biến mất lỗi; cần chọn quy tắc đúng với ngôn ngữ và nghiệp vụ.

Nếu có đối số là binary string, kết quả có thể được xử lý như binary string. Điều này ảnh hưởng so sánh, collation và cách client hiển thị dữ liệu. Không ghép dữ liệu BLOB tùy ý với chuỗi văn bản rồi giả định kết quả vẫn là văn bản UTF-8. Khi cần giải mã byte thành văn bản, hãy dùng `CONVERT(... USING charset)` sau khi biết encoding thật của dữ liệu.

## 8. CONCAT và điều kiện NULL trong biểu thức lớn

Khi `CONCAT()` được dùng bên trong một biểu thức khác, `NULL` tiếp tục lan truyền theo quy tắc của biểu thức đó.

Ví dụ:

```sql
SELECT
    CASE
        WHEN phone IS NULL THEN 'No phone'
        ELSE CONCAT('Phone: ', phone)
    END AS phone_label
FROM customer_profile;
```

Hoặc dùng `COALESCE()`:

```sql
SELECT CONCAT('Phone: ', COALESCE(phone, 'No phone')) AS phone_label
FROM customer_profile;
```

Hai cách trên có thể cho cùng kết quả trong ví dụ đơn giản, nhưng `CASE` phù hợp khi cần nhánh xử lý khác nhau cho từng trạng thái. Nếu cần phân biệt chuỗi rỗng với `NULL`, không chỉ kiểm tra `IS NULL`; hãy kiểm tra thêm `= ''` hoặc chuẩn hóa theo quy tắc nghiệp vụ.

### 8.1. Bọc CONCAT_WS để phân biệt không có dữ liệu

`CONCAT_WS()` trả chuỗi rỗng khi tất cả thành phần sau separator là `NULL`. Nếu muốn kết quả là `NULL` trong trường hợp không có thành phần nào, có thể dùng `NULLIF()`:

```sql
SELECT NULLIF(
    CONCAT_WS(' ', first_name, middle_name, last_name),
    ''
) AS full_name
FROM customer_profile;
```

Lưu ý: cách này chỉ biến chuỗi rỗng thành `NULL`; nếu đầu vào chứa các chuỗi chỉ có khoảng trắng thì kết quả có thể vẫn chứa khoảng trắng. Kết hợp `TRIM()` và `NULLIF()` trước khi ghép nếu muốn coi khoảng trắng là thiếu dữ liệu.

## 9. Dùng CONCAT trong SELECT, UPDATE và INSERT

### 9.1. Tạo cột hiển thị trong SELECT

```sql
SELECT
    customer_id,
    CONCAT_WS(' ',
        NULLIF(TRIM(first_name), ''),
        NULLIF(TRIM(middle_name), ''),
        NULLIF(TRIM(last_name), '')
    ) AS display_name
FROM customer_profile;
```

Alias `display_name` chỉ tồn tại trong kết quả truy vấn; nó không tạo cột vật lý trong bảng.

### 9.2. Cập nhật một cột từ các cột khác

Nếu bảng có cột `display_name` được lưu vật lý và nghiệp vụ yêu cầu đồng bộ:

```sql
ALTER TABLE customer_profile
    ADD COLUMN display_name VARCHAR(242) NULL;

UPDATE customer_profile
SET display_name = CONCAT_WS(' ',
    NULLIF(TRIM(first_name), ''),
    NULLIF(TRIM(middle_name), ''),
    NULLIF(TRIM(last_name), '')
)
WHERE customer_id = 101;
```

Trước khi chạy, kiểm tra hàng đích bằng `SELECT`. Nếu `display_name` phải luôn đồng bộ với tên thành phần, cân nhắc generated column thay vì duy trì thủ công ở nhiều câu lệnh. Nếu cập nhật theo batch, hãy đánh giá lock, transaction và khả năng ghi đè dữ liệu do request đồng thời.

### 9.3. INSERT từ kết quả ghép

```sql
INSERT INTO customer_search_snapshot (customer_id, search_label)
SELECT
    customer_id,
    CONCAT_WS(' ',
        NULLIF(TRIM(first_name), ''),
        NULLIF(TRIM(middle_name), ''),
        NULLIF(TRIM(last_name), '')
    )
FROM customer_profile;
```

Đây là ví dụ tạo snapshot dữ liệu hiển thị. Nếu nguồn thay đổi, snapshot không tự cập nhật; cần xác định rõ cơ chế đồng bộ hoặc dùng truy vấn/generated column khi phù hợp.

## 10. CONCAT trong WHERE và tác động tới index

Ghép cột trong `SELECT` thường chỉ tạo giá trị đầu ra. Nhưng nếu đặt biểu thức trên cột trong `WHERE`, MySQL có thể không sử dụng index thường của từng cột để tìm trực tiếp theo range.

Ví dụ:

```sql
SELECT customer_id
FROM customer_profile
WHERE CONCAT(first_name, ' ', last_name) = 'Nguyen An';
```

Nếu `first_name` và `last_name` có index riêng, biểu thức ghép không tự động tương đương một phép tìm kiếm trên một trong các index đó. Với bảng lớn, truy vấn có thể phải tính biểu thức cho nhiều hàng.

Các lựa chọn thiết kế:

- Nếu có thể, lọc trực tiếp theo các cột nguồn với điều kiện phù hợp.
- Nếu thường xuyên tìm theo biểu thức ghép, cân nhắc generated column lưu biểu thức và tạo index trên cột đó.
- Trên phiên bản hỗ trợ, đánh giá functional index cho biểu thức xác định và phù hợp với giới hạn index.

Ví dụ generated column:

```sql
ALTER TABLE customer_profile
    ADD COLUMN display_name_search VARCHAR(242)
        GENERATED ALWAYS AS (
            CONCAT_WS(' ',
                NULLIF(TRIM(first_name), ''),
                NULLIF(TRIM(middle_name), ''),
                NULLIF(TRIM(last_name), '')
            )
        ) STORED,
    ADD INDEX idx_customer_display_name (display_name_search);
```

Độ dài khai báo phải được tính theo độ dài tối đa của các cột nguồn và separator; ví dụ `VARCHAR(242)` đủ cho ba cột tối đa 80 ký tự và hai dấu cách, không phải công thức chung cho mọi schema. Trước khi thêm generated column/index, kiểm tra biểu thức được phép trong generated column, row size, index key length, DDL algorithm và dung lượng rebuild.

Sau khi tạo, truy vấn theo cột được index:

```sql
SELECT customer_id, display_name
FROM customer_profile
WHERE display_name_search = 'Nguyen An';
```

Kiểm tra access path bằng `EXPLAIN`; không giả định optimizer luôn chọn index nếu bảng nhỏ hoặc điều kiện có độ chọn lọc thấp.

## 11. Độ dài kết quả và dữ liệu lớn

Kết quả của `CONCAT()`/`CONCAT_WS()` có độ dài phụ thuộc các đối số. Kích thước dữ liệu đầu ra có thể lớn hơn nhiều so với từng đối số riêng lẻ. Khi ghép văn bản dài hoặc BLOB, hãy cân nhắc:

- Giới hạn gói dữ liệu `max_allowed_packet` ở client/server.
- Dung lượng bộ nhớ cần để tạo và truyền kết quả.
- Character set và số byte trên mỗi ký tự.
- Cách ứng dụng đọc kết quả và giới hạn của API/DTO.

Không dùng `CONCAT()` để ghép các payload lớn chỉ nhằm truyền chúng như một chuỗi duy nhất nếu có thể đọc các cột riêng hoặc stream dữ liệu phù hợp hơn. Với nội dung văn bản dài, cân nhắc `TEXT`/`LONGTEXT` và cách truy xuất theo nhu cầu.

## 12. Các lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| `CONCAT()` trả `NULL` dù phần lớn cột có dữ liệu | Có ít nhất một đối số `NULL` | Dùng `CONCAT_WS()` hoặc `COALESCE()` theo semantics mong muốn |
| `CONCAT_WS()` vẫn có dấu phân cách kép | Thành phần là chuỗi rỗng hoặc chỉ chứa khoảng trắng, không phải `NULL` | Dùng `NULLIF(TRIM(value), '')` trước khi ghép nếu phù hợp |
| `CONCAT_WS()` trả `NULL` | Separator là `NULL` | Dùng separator mặc định bằng `COALESCE()` hoặc sửa dữ liệu nguồn |
| Chuỗi ghép rỗng nhưng mong muốn NULL | Tất cả thành phần sau separator đều `NULL` | Dùng `NULLIF(result, '')` hoặc `CASE` |
| Lỗi `Illegal mix of collations` | Đối số có charset/collation không tương thích | Kiểm tra metadata và chuẩn hóa collation có chủ đích |
| Kết quả hiển thị sai ký tự | Charset của dữ liệu hoặc kết nối không đúng; dữ liệu binary bị hiểu như văn bản | Xác định encoding nguồn, chuyển đổi đúng charset và kiểm tra client connection |
| Truy vấn tìm theo chuỗi ghép chậm | Biểu thức trên cột làm mất khả năng dùng index thường | Dùng điều kiện trên cột nguồn hoặc generated/functional index phù hợp |
| Mã ghép số bị định dạng ngoài ý muốn | Dựa vào chuyển đổi kiểu ngầm định | Dùng `CAST()`, `LPAD()` hoặc `DATE_FORMAT()` theo yêu cầu |

## 13. Bài thực hành

Thực hiện trong database lab riêng:

1. Chạy `CONCAT('A', 'B')`, `CONCAT('A', NULL, 'B')` và ghi lại kết quả.
2. Chạy `CONCAT_WS('-', 'A', NULL, 'B')`, `CONCAT_WS('-', 'A', '', 'B')` và giải thích vì sao hai kết quả khác nhau.
3. Thử separator `NULL` và xác nhận toàn bộ kết quả `CONCAT_WS()` trở thành `NULL`.
4. Thử `CONCAT_WS(' ', NULL, NULL)` rồi so sánh với `CONCAT(NULL, NULL)`.
5. Dùng bảng `customer_profile` tạo tên đầy đủ bằng `CONCAT()` và `CONCAT_WS()`; xác định hàng nào bị ảnh hưởng bởi `NULL`.
6. Chuẩn hóa tên bằng `NULLIF(TRIM(column), '')`, kiểm tra dữ liệu có chuỗi rỗng và chỉ có khoảng trắng.
7. Ghép địa chỉ từ các thành phần tùy chọn; thử trường hợp thiếu phường, quận hoặc thành phố.
8. Tạo mã hiển thị từ ID bằng `CONCAT()`, `CAST()` và `LPAD()`; kiểm tra khi ID dài hơn độ rộng mong muốn.
9. Dùng `DATE_FORMAT()` trước khi ghép ngày giờ; kiểm tra kết quả với session timezone phù hợp nếu cột là `TIMESTAMP`.
10. Xem `CHARSET()` và `COLLATION()` của biểu thức ghép; thử các cột có collation khác nhau trong lab và xử lý xung đột đúng cách.
11. So sánh `EXPLAIN` của điều kiện `CONCAT(first_name, ' ', last_name) = ...` với truy vấn trên generated column được index.
12. Viết một truy vấn JDBC dùng `PreparedStatement` để truyền separator và các giá trị; không ghép trực tiếp dữ liệu người dùng vào SQL.

Bạn hoàn thành bài khi dự đoán đúng kết quả với `NULL`, chuỗi rỗng và separator, tạo được tên/địa chỉ không có dấu phân cách thừa, đồng thời biết khi nào biểu thức ghép ảnh hưởng tới index và kiểu dữ liệu đầu ra.

## 14. Nguyên tắc cần ghi nhớ

- `CONCAT()` trả `NULL` nếu bất kỳ đối số nào là `NULL`.
- `CONCAT_WS(separator, ...)` bỏ qua đối số giá trị `NULL`, nhưng separator `NULL` làm kết quả `NULL`.
- `CONCAT_WS()` không bỏ qua chuỗi rỗng hoặc chuỗi chỉ chứa khoảng trắng.
- Khi cần coi rỗng/blank như thiếu dữ liệu, cân nhắc `NULLIF(TRIM(value), '')` trước khi ghép.
- Dùng `COALESCE()`/`IFNULL()` khi muốn thay `NULL` bằng giá trị cụ thể; hiểu rằng chuỗi thay thế sẽ xuất hiện trong kết quả.
- Nếu tất cả đối số giá trị của `CONCAT_WS()` là `NULL`, kết quả là chuỗi rỗng; dùng `NULLIF()`/`CASE` nếu cần `NULL`.
- Dùng `DATE_FORMAT()` và `CAST()` để kiểm soát định dạng số/ngày giờ trước khi ghép.
- Kiểm tra charset/collation khi ghép các cột từ nhiều nguồn; cẩn thận với binary string.
- Dùng generated column hoặc functional index khi phải tìm kiếm lặp lại theo biểu thức ghép và phiên bản hỗ trợ.
- Không dùng chuỗi hiển thị đã ghép làm thay thế khóa chính hoặc dữ liệu số gốc.
