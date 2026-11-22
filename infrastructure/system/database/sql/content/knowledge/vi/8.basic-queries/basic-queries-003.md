# Tạo cột kết quả bằng hằng và biểu thức

Khi truy vấn dữ liệu bằng SQL, bạn không bắt buộc phải trả về nguyên xi các cột đang lưu trong bảng. Phần `SELECT` có thể tạo ra **cột kết quả mới** từ một hằng số, một phép tính, một phép nối chuỗi, một hàm hoặc một biểu thức điều kiện. Những cột này giúp biến dữ liệu nguồn thành thông tin dễ đọc ngay trong kết quả truy vấn.

Ví dụ, bảng chỉ lưu `unit_price` (đơn giá), `quantity` (số lượng) và `discount_rate` (tỷ lệ giảm giá); câu truy vấn có thể tính thêm `gross_amount` (thành tiền trước giảm giá), `discount_amount` (số tiền được giảm) và `net_amount` (thành tiền sau giảm giá). Các tên kết quả đó được tạo ngay khi `SELECT` chạy; chúng không tự động trở thành cột mới được lưu vào bảng.

Bài học nằm trong **Database SQL → Truy vấn cơ bản**, dùng chủ yếu cú pháp **PostgreSQL** để thực hành. Phần cuối chỉ ra những khác biệt cần lưu ý khi áp dụng trên MySQL, SQL Server, Oracle hoặc SQLite.

## 1. Một cột kết quả trong `SELECT` được tạo như thế nào?

Cấu trúc thông dụng:

```sql
SELECT
    expression_1 AS result_column_1,
    expression_2 AS result_column_2
FROM table_name;
```

Trong đó:

- `expression` là một biểu thức có thể tính được, ví dụ `unit_price * quantity`, `'online'` hoặc `quantity > 0`.
- `AS result_column` đặt **tên hiển thị/định danh đầu ra** cho biểu thức. Trong nhiều DBMS, từ khóa `AS` có thể được bỏ qua, nhưng viết rõ `AS` dễ đọc hơn.
- `FROM` cung cấp các hàng và cột nguồn. Mỗi hàng được xử lý sẽ tạo ra các giá trị tương ứng ở cột kết quả.
- Nếu biểu thức không dùng cột nguồn, nó có thể cho cùng một giá trị trên mọi hàng, chẳng hạn nhãn `'demo'`.

Ví dụ PostgreSQL không cần bảng nguồn:

```sql
SELECT 2 + 3 AS sum_result,
       10 * 4 AS multiplied_result,
       'SQL' AS topic_name;
```

Kết quả gồm **một hàng**:

| `sum_result` | `multiplied_result` | `topic_name` |
| ---: | ---: | --- |
| 5 | 40 | SQL |

Ở PostgreSQL, `SELECT` không có `FROM` vẫn có thể trả một hàng chứa các biểu thức. Một số hệ quản trị hoặc phiên bản có quy tắc khác (ví dụ Oracle đời cũ thường dùng `FROM DUAL`), nên ví dụ này cần được hiểu theo DBMS mục tiêu.

### Cột gốc và cột tính toán

Giả sử một hàng có:

```text
unit_price = 12.50
quantity   = 4
```

Khi viết:

```sql
SELECT unit_price,
       quantity,
       unit_price * quantity AS gross_amount
FROM line_items;
```

DBMS đọc hai giá trị nguồn và tính thêm một **giá trị kết quả** `gross_amount = 50.00` cho hàng đó. `gross_amount` chỉ tồn tại trong kết quả của câu lệnh. Muốn lưu kết quả một cách lâu dài cần có thiết kế riêng, ví dụ cột lưu, cột được tạo tự động (generated/computed column) hoặc một cơ chế khác của DBMS.

## 2. Tạo dữ liệu thực hành

Để các ví dụ tiếp theo dùng cùng dữ liệu, hãy mở một kết nối tới **PostgreSQL** và chạy khối sau trong database thử nghiệm. Bảng `lesson_line_items` là **bảng tạm** chỉ tồn tại trong phiên kết nối. Nếu đã tạo bảng cùng tên trong phiên đó, hãy dùng phiên mới hoặc chọn tên tạm khác trước khi chạy lại.

```sql
CREATE TEMP TABLE lesson_line_items (
    item_id       INTEGER PRIMARY KEY,
    product_name  TEXT NOT NULL,
    unit_price    NUMERIC(10, 2) NOT NULL,
    quantity      INTEGER NOT NULL,
    discount_rate NUMERIC(5, 2) NOT NULL,
    note          TEXT,
    order_date    DATE NOT NULL
);

INSERT INTO lesson_line_items
    (item_id, product_name, unit_price, quantity,
     discount_rate, note, order_date)
VALUES
    (1, 'Bút bi',     12.50, 4, 0.10, NULL,         DATE '2026-01-15'),
    (2, 'Sổ tay',     45.00, 2, 0.00, 'Hàng mới',    DATE '2026-01-16'),
    (3, 'Tẩy',         8.00, 0, 0.05, '',           DATE '2026-01-17'),
    (4, 'Bìa hồ sơ',  30.00, 3, 0.20, 'Khuyến mãi', DATE '2026-01-18');

SELECT * FROM lesson_line_items ORDER BY item_id;
```

Dữ liệu gồm bốn dòng sản phẩm. `discount_rate` lưu theo **tỷ lệ thập phân**: `0.10` nghĩa là giảm 10%, `0.20` nghĩa là giảm 20%, không phải 0,10% hay 0,20%.

Bảng thực hành có một dòng `quantity = 0` để minh họa sự khác nhau giữa kết quả phép tính bằng 0 và phép tính không xác định.

## 3. Tạo cột kết quả bằng hằng số

**Hằng (literal)** là giá trị viết trực tiếp trong SQL, không phải lấy từ một cột của bảng.

Các ví dụ PostgreSQL:

```sql
SELECT
    100             AS integer_constant,
    12.50           AS decimal_constant,
    'Xin chào'      AS text_constant,
    TRUE            AS boolean_constant,
    DATE '2026-01-15' AS date_constant,
    NULL::TEXT      AS missing_constant;
```

Những dạng phổ biến:

| Hằng | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| Số nguyên | `100`, `-5` | Giá trị số không có phần thập phân |
| Số thập phân | `12.50`, `0.25` | Giá trị số có phần thập phân; kiểu cụ thể phụ thuộc DBMS và ngữ cảnh |
| Chuỗi | `'Xin chào'` | Giá trị văn bản, dùng dấu nháy đơn |
| Boolean | `TRUE`, `FALSE` | Giá trị logic ở DBMS hỗ trợ kiểu boolean |
| Ngày | `DATE '2026-01-15'` | Literal ngày theo cú pháp được DBMS hỗ trợ |
| Giá trị thiếu | `NULL` | Giá trị không xác định/không có; đôi khi cần `CAST` để xác định kiểu |

Trong bài này, các hằng `TRUE`, `DATE '...'` và cú pháp ép kiểu `::` được trình bày theo PostgreSQL. Một số DBMS không có kiểu boolean SQL độc lập, hoặc sử dụng cú pháp ngày và cast khác.

### Hằng xuất hiện trên mọi hàng

```sql
SELECT item_id,
       product_name,
       'online' AS sales_channel,
       2026     AS report_year
FROM lesson_line_items
ORDER BY item_id;
```

Cột `sales_channel` có cùng giá trị `'online'` và `report_year` có cùng giá trị `2026` ở cả bốn hàng. Đây là cách thêm **nhãn cố định vào kết quả**, thường dùng để xác định nguồn, phiên bản báo cáo hoặc một tham số nghiệp vụ đã biết.

Điều này **không thêm** hai cột `sales_channel`, `report_year` vào bảng `lesson_line_items`.

### Hằng và biểu thức động khác nhau

`CURRENT_DATE` trong PostgreSQL là một biểu thức cung cấp ngày hiện tại theo ngữ cảnh DBMS; nó không phải literal `DATE '2026-01-15'` được viết cố định:

```sql
SELECT CURRENT_DATE AS query_date,
       DATE '2026-01-15' AS fixed_example_date;
```

Đừng nhầm “giá trị không lấy từ cột bảng” với “giá trị bất biến”. Các hàm thời gian hoặc hàm sinh số ngẫu nhiên có thể tạo giá trị phụ thuộc thời điểm/phiên/lần tính.

## 4. Tính cột số học bằng các toán tử

Một biểu thức số học có thể kết hợp cột nguồn, hằng số và toán tử:

| Toán tử | Mô tả | Ví dụ |
| --- | --- | --- |
| `+` | Cộng | `unit_price + 5` |
| `-` | Trừ | `unit_price - 5` |
| `*` | Nhân | `unit_price * quantity` |
| `/` | Chia | `unit_price / 2` |
| `%` | Chia lấy phần dư ở nhiều DBMS | `quantity % 2` |

Không phải hệ quản trị nào cũng dùng cùng một toán tử cho phép chia lấy dư hoặc các phép toán chuyên biệt. Ví dụ dưới đây được viết cho PostgreSQL.

### Thành tiền trước giảm giá

```sql
SELECT item_id,
       product_name,
       unit_price,
       quantity,
       unit_price * quantity AS gross_amount
FROM lesson_line_items
ORDER BY item_id;
```

| `item_id` | `product_name` | `unit_price` | `quantity` | `gross_amount` |
| ---: | --- | ---: | ---: | ---: |
| 1 | Bút bi | 12.50 | 4 | 50.00 |
| 2 | Sổ tay | 45.00 | 2 | 90.00 |
| 3 | Tẩy | 8.00 | 0 | 0.00 |
| 4 | Bìa hồ sơ | 30.00 | 3 | 90.00 |

Một phép tính không phải thêm vào bảng để được sử dụng trong `SELECT`. DBMS sẽ tạo giá trị cho từng hàng trả về.

### Thành tiền sau giảm giá

Vì tỷ lệ giảm giá được lưu dưới dạng số thập phân, thành tiền sau giảm giá được tính:

\[
\text{net\_amount}
=
\text{unit\_price}
\times
\text{quantity}
\times
(1-\text{discount\_rate})
\]

Trong SQL:

```sql
SELECT item_id,
       product_name,
       unit_price * quantity AS gross_amount,
       unit_price * quantity * discount_rate AS discount_amount,
       unit_price * quantity * (1 - discount_rate) AS net_amount
FROM lesson_line_items
ORDER BY item_id;
```

Kết quả theo dữ liệu mẫu:

| Sản phẩm | `gross_amount` | `discount_amount` | `net_amount` |
| --- | ---: | ---: | ---: |
| Bút bi | 50.00 | 5.0000 | 45.0000 |
| Sổ tay | 90.00 | 0.0000 | 90.0000 |
| Tẩy | 0.00 | 0.0000 | 0.0000 |
| Bìa hồ sơ | 90.00 | 18.0000 | 72.0000 |

Các cột tính từ `NUMERIC` có thể mang scale lớn hơn cột đầu vào; cách hiển thị số chữ số thập phân có thể thay đổi theo client hoặc kiểu kết quả. Khi cần làm tròn rõ ràng đến hai chữ số, bạn có thể dùng `ROUND`:

```sql
SELECT item_id,
       ROUND(
           unit_price * quantity * (1 - discount_rate),
           2
       ) AS net_amount
FROM lesson_line_items
ORDER BY item_id;
```

`ROUND(..., 2)` nói rõ quy tắc giữ hai chữ số sau dấu thập phân của kết quả truy vấn trong PostgreSQL. Nó không tự thay đổi giá trị `unit_price` hay `discount_rate` đã lưu.

### Thứ tự ưu tiên phép toán và dấu ngoặc

Cũng như toán học, phép nhân/chia thường có ưu tiên cao hơn cộng/trừ:

```sql
SELECT 10 + 2 * 3     AS without_parentheses, -- 16
       (10 + 2) * 3   AS with_parentheses;    -- 36
```

Khi biểu thức dài hoặc có quy tắc nghiệp vụ, hãy dùng dấu ngoặc để người đọc không phải đoán thứ tự:

```sql
-- Giá sau giảm giá: giảm một phần của tổng tiền
SELECT unit_price * quantity * (1 - discount_rate) AS net_amount
FROM lesson_line_items;
```

Số học SQL còn chịu ảnh hưởng của **kiểu dữ liệu**; không thể chỉ dựa vào dấu ngoặc để bảo đảm một phép chia có phần thập phân.

## 5. Kiểu dữ liệu ảnh hưởng kết quả biểu thức

### Phép chia số nguyên so với số thập phân

PostgreSQL thực hiện phép chia hai số nguyên theo kiểu số nguyên trong ví dụ này:

```sql
SELECT 5 / 2 AS integer_division; -- 2
```

Nếu muốn kết quả `2.5`, ép ít nhất một toán hạng sang kiểu thập phân trước khi chia:

```sql
SELECT 5::NUMERIC / 2 AS decimal_division,
       CAST(5 AS NUMERIC) / 2 AS decimal_division_standard_cast;
```

Cú pháp `::NUMERIC` là kiểu ép nhanh của PostgreSQL; `CAST(... AS NUMERIC)` gần với SQL chuẩn và thường dễ chuyển hệ hơn.

Đặt `CAST` **sau** một phép chia đã mất phần lẻ không khôi phục được dữ liệu:

```sql
SELECT (5 / 2)::NUMERIC AS cast_too_late;  -- 2, không phải 2.5
```

### Chuỗi số và số thật khác nhau

`'25'` là literal chuỗi, còn `25` là literal số. Một số DBMS tự chuyển kiểu khi so sánh/tính toán; một số từ chối hoặc cho hành vi khác.

Để thể hiện ý định chuyển đổi rõ ràng:

```sql
SELECT CAST('25' AS INTEGER) + 5 AS converted_sum;
```

Nếu chuỗi không phải biểu diễn số hợp lệ (ví dụ `'hai mươi lăm'`), phép cast có thể gây lỗi. Hãy xác thực dữ liệu trước khi chuyển đổi trong ứng dụng hoặc pipeline nhập dữ liệu.

### Số chính xác và số dấu phẩy động

`NUMERIC`/`DECIMAL` được dùng cho các phép tính thập phân chính xác trong giới hạn DBMS. `REAL`/`DOUBLE PRECISION` là kiểu dấu phẩy động gần đúng, nhiều phân số thập phân không được biểu diễn chính xác tuyệt đối.

```sql
-- PostgreSQL: phép tính tiền minh họa bằng NUMERIC
SELECT ROUND(12.50::NUMERIC * 4, 2) AS monetary_result;
```

Với số tiền và phép tính cần chính xác đến đơn vị nhỏ nhất, nên xác định thống nhất kiểu decimal và quy tắc làm tròn thay vì dùng floating point nhị phân tùy ý.

## 6. Tạo cột văn bản bằng phép nối chuỗi

Cột kết quả cũng có thể là chuỗi được tạo từ nhiều phần.

Trong PostgreSQL, toán tử `||` nối hai chuỗi:

```sql
SELECT product_name || ' - Mã ' || item_id::TEXT AS product_label
FROM lesson_line_items
ORDER BY item_id;
```

Ví dụ đầu ra:

```text
Bút bi - Mã 1
Sổ tay - Mã 2
Tẩy - Mã 3
Bìa hồ sơ - Mã 4
```

Lưu ý `item_id` là số nguyên. Trong ví dụ, `item_id::TEXT` chuyển nó thành chuỗi trước khi nối. Một số DBMS có thể tự ép kiểu số thành chuỗi, nhưng ép rõ ràng giúp tránh phụ thuộc vào quy tắc chuyển kiểu ngầm.

### Kết hợp hàm chuỗi

`TRIM` bỏ khoảng trắng đầu/cuối theo quy tắc DBMS; `UPPER` chuyển sang chữ hoa; `LOWER` chuyển sang chữ thường.

```sql
SELECT item_id,
       UPPER(product_name) AS uppercase_name,
       LOWER(product_name) AS lowercase_name,
       '[' || TRIM(product_name) || ']' AS bracketed_name
FROM lesson_line_items
ORDER BY item_id;
```

Kết quả chữ hoa/chữ thường có thể phụ thuộc locale/collation và khả năng xử lý Unicode của DBMS. Với tên tiếng Việt, không nên coi cách xử lý Unicode ở mọi môi trường luôn giống hệt nhau.

### Nối chuỗi có `NULL`

Trong PostgreSQL, toán tử `||` trả `NULL` nếu một toán hạng là `NULL`:

```sql
SELECT 'Ghi chú: ' || NULL::TEXT AS result_with_null;
```

Muốn thay `NULL` bằng một nhãn mặc định, dùng `COALESCE`:

```sql
SELECT item_id,
       'Ghi chú: ' ||
       COALESCE(NULLIF(TRIM(note), ''), 'Không có')
           AS note_label
FROM lesson_line_items
ORDER BY item_id;
```

Giải thích:

1. `TRIM(note)` loại khoảng trắng đầu/cuối.
2. `NULLIF(..., '')` biến chuỗi rỗng thành `NULL`.
3. `COALESCE(..., 'Không có')` dùng nhãn mặc định nếu giá trị là `NULL`.
4. `||` ghép nhãn vào chuỗi kết quả.

`NULLIF` và `COALESCE` ở đây **chỉ ảnh hưởng biểu thức đầu ra**, không tự sửa cột `note` trong bảng.

Một số hệ quản trị khác dùng `CONCAT`, `+` hoặc quy tắc nối chuỗi khác. PostgreSQL cũng có hàm `CONCAT` nhưng cách nó xử lý `NULL` có thể khác toán tử `||`; cần chọn theo hành vi mong muốn.

## 7. Tạo cột logic bằng phép so sánh

Biểu thức trong `SELECT` có thể trả về kết quả đúng/sai. Ví dụ PostgreSQL:

```sql
SELECT item_id,
       product_name,
       quantity,
       quantity > 0      AS has_quantity,
       discount_rate > 0 AS has_discount
FROM lesson_line_items
ORDER BY item_id;
```

| Sản phẩm | `quantity` | `has_quantity` | `has_discount` |
| --- | ---: | --- | --- |
| Bút bi | 4 | true | true |
| Sổ tay | 2 | true | false |
| Tẩy | 0 | false | true |
| Bìa hồ sơ | 3 | true | true |

Những cột này giúp biểu diễn quy tắc đơn giản mà không thay đổi dữ liệu nguồn. PostgreSQL có kiểu `BOOLEAN` riêng; một số DBMS thể hiện kết quả so sánh bằng kiểu số hoặc cách biểu diễn khác.

### Kết quả logic khi có `NULL`

Một biểu thức như `note = 'Hàng mới'` trả kết quả **UNKNOWN** khi `note` là `NULL`:

```sql
SELECT item_id,
       note,
       note = 'Hàng mới' AS is_new_note,
       note IS NULL      AS note_missing
FROM lesson_line_items
ORDER BY item_id;
```

Trong PostgreSQL, `UNKNOWN` được hiển thị là `NULL` ở cột boolean. Nếu cần kiểm tra giá trị thiếu, dùng `IS NULL` hoặc `IS NOT NULL`; không dùng `= NULL`.

Không nên tự chuyển mọi kết quả logic `NULL` thành `FALSE` khi hai trạng thái có ý nghĩa khác nhau trong nghiệp vụ.

## 8. Dùng `CASE` để tạo cột theo điều kiện

Một phép toán đơn giản không đủ diễn tả mọi quy tắc nghiệp vụ. Biểu thức `CASE` giúp lựa chọn giá trị dựa trên điều kiện:

```sql
SELECT item_id,
       product_name,
       quantity,
       CASE
           WHEN quantity = 0 THEN 'Không có số lượng'
           WHEN quantity < 3 THEN 'Số lượng ít'
           ELSE 'Số lượng đủ'
       END AS quantity_status
FROM lesson_line_items
ORDER BY item_id;
```

Kết quả:

| Sản phẩm | Số lượng | `quantity_status` |
| --- | ---: | --- |
| Bút bi | 4 | Số lượng đủ |
| Sổ tay | 2 | Số lượng ít |
| Tẩy | 0 | Không có số lượng |
| Bìa hồ sơ | 3 | Số lượng đủ |

Cú pháp tổng quát:

```sql
CASE
    WHEN condition_1 THEN result_1
    WHEN condition_2 THEN result_2
    ELSE default_result
END
```

Các nhánh được xét theo thứ tự logic của `CASE`; nhánh phù hợp đầu tiên quyết định giá trị kết quả. Nếu không có nhánh nào phù hợp và không viết `ELSE`, kết quả là `NULL`.

Các kết quả `THEN`/`ELSE` phải có kiểu tương thích theo cơ chế suy luận kiểu của DBMS. Trong ví dụ trên, mọi kết quả là văn bản.

### Phân loại mức giảm giá

```sql
SELECT product_name,
       discount_rate,
       CASE
           WHEN discount_rate = 0 THEN 'Không giảm'
           WHEN discount_rate < 0.15 THEN 'Giảm nhẹ'
           ELSE 'Giảm nhiều'
       END AS discount_group
FROM lesson_line_items
ORDER BY item_id;
```

Các ngưỡng `0.15`, `0` chỉ là **quy tắc minh họa**. Khi xây dựng báo cáo thật, cần thống nhất cách phân loại tỷ lệ với người sở hữu yêu cầu nghiệp vụ.

### Có thể kết hợp `CASE` với phép tính

```sql
SELECT item_id,
       CASE
           WHEN quantity = 0 THEN 0::NUMERIC
           ELSE unit_price * quantity * (1 - discount_rate)
       END AS calculated_amount
FROM lesson_line_items;
```

Ở đây `CASE` trả một **giá trị số**, không phải nhãn chuỗi. Ví dụ bảo đảm một quy tắc riêng cho hàng không có số lượng; nhưng trong dữ liệu mẫu, phép nhân với `quantity = 0` vốn cũng cho 0. Điều quan trọng là `CASE` diễn đạt quy tắc nghiệp vụ khi cần phân nhánh.

Đừng phụ thuộc `CASE` để che giấu mọi lỗi của biểu thức có hằng bất hợp lệ: trình tối ưu có thể xử lý một số biểu thức hằng trước khi chọn nhánh. Với phép chia, cần bảo vệ mẫu số hoặc kiểm tra điều kiện phù hợp.

## 9. Tạo cột ngày tháng và dùng hàm

Giá trị ngày cũng có thể dùng trong biểu thức.

Trong PostgreSQL, cộng một số nguyên vào `DATE` làm dịch số ngày:

```sql
SELECT item_id,
       order_date,
       order_date + 7 AS review_date
FROM lesson_line_items
ORDER BY item_id;
```

| `item_id` | `order_date` | `review_date` |
| ---: | --- | --- |
| 1 | 2026-01-15 | 2026-01-22 |
| 2 | 2026-01-16 | 2026-01-23 |
| 3 | 2026-01-17 | 2026-01-24 |
| 4 | 2026-01-18 | 2026-01-25 |

`review_date` là ngày tính từ `order_date`; nó không tự trở thành một cột mới trong bảng.

### Tính khoảng cách ngày

```sql
SELECT item_id,
       order_date,
       DATE '2026-01-31' - order_date AS days_until_end_of_month
FROM lesson_line_items
ORDER BY item_id;
```

Với PostgreSQL, phép trừ hai `DATE` cho số ngày chênh lệch. Những DBMS khác có thể yêu cầu `DATEDIFF`, `INTERVAL` hoặc cú pháp riêng; vì vậy không nên chuyển nguyên câu này sang hệ khác mà không kiểm tra.

### Hàm như một biểu thức

Ngoài toán tử, phần `SELECT` nhận giá trị từ hàm. Ví dụ:

```sql
SELECT item_id,
       LENGTH(product_name)      AS name_length,
       ROUND(unit_price, 0)      AS rounded_price,
       ABS(quantity - 3)         AS distance_from_three
FROM lesson_line_items
ORDER BY item_id;
```

- `LENGTH` đếm độ dài chuỗi theo quy tắc DBMS.
- `ROUND` làm tròn số ở độ chính xác mong muốn.
- `ABS` lấy giá trị tuyệt đối.

Hàm có thể nhận cột hoặc biểu thức làm đối số; kết quả có thể được đặt alias giống hằng số và phép toán.

## 10. Đặt tên cột kết quả bằng `AS`

Alias giúp đặt tên dễ hiểu hơn cho một biểu thức:

```sql
SELECT
    product_name AS display_name,
    unit_price * quantity AS gross_amount,
    ROUND(unit_price * quantity * (1 - discount_rate), 2)
        AS net_amount
FROM lesson_line_items
ORDER BY item_id;
```

Tên `display_name`, `gross_amount` và `net_amount` thuộc **kết quả truy vấn**. Đặt alias không đổi tên `product_name` hoặc tạo thêm cột trong bảng.

### Khi bỏ `AS`

Trong PostgreSQL, có thể viết:

```sql
SELECT unit_price * quantity gross_amount
FROM lesson_line_items;
```

Nhưng cách này dễ bị đọc nhầm ở biểu thức dài. Nên dùng `AS` để phân biệt ranh giới giữa biểu thức và tên đầu ra.

### Alias chứa dấu cách hoặc chữ hoa

Có thể dùng identifier có dấu nháy kép trong PostgreSQL:

```sql
SELECT product_name AS "Tên sản phẩm",
       unit_price * quantity AS "Thành tiền"
FROM lesson_line_items;
```

Tên có dấu cách được hỗ trợ khi đặt trong dấu nháy đúng quy tắc DBMS; tuy nhiên, trong ứng dụng và API, tên ổn định dạng `snake_case` như `product_name` và `gross_amount` thường dễ dùng hơn.

Dấu nháy đơn `'Tên sản phẩm'` chỉ **giá trị chuỗi**, không phải cách đặt tên cột chuẩn. Dấu nháy identifier khác nhau giữa DBMS (ví dụ MySQL thường dùng backtick, SQL Server còn hỗ trợ `[Tên cột]`).

### Tránh tên đầu ra trùng nhau

```sql
SELECT item_id AS id,
       quantity AS id
FROM lesson_line_items;
```

Câu trên có thể được một DBMS cho phép và tạo hai cột cùng nhãn `id`, gây khó khăn cho trình đọc kết quả, mapping đối tượng và sử dụng trong truy vấn ngoài. Hãy đặt alias duy nhất và có nghĩa, chẳng hạn `item_id`, `ordered_quantity`.

## 11. Alias được dùng ở đâu trong câu truy vấn?

Một điểm quan trọng: alias đầu ra trong `SELECT` **không tự động có hiệu lực ở mọi mệnh đề của cùng khối truy vấn**.

Ví dụ PostgreSQL:

```sql
-- Hợp lệ: ORDER BY có thể dùng alias kết quả
SELECT product_name,
       unit_price * quantity AS gross_amount
FROM lesson_line_items
ORDER BY gross_amount DESC, product_name;
```

Ngược lại:

```sql
-- Không hợp lệ trong PostgreSQL:
-- WHERE không thể tham chiếu alias vừa khai báo ở SELECT
SELECT product_name,
       unit_price * quantity AS gross_amount
FROM lesson_line_items
WHERE gross_amount > 50;
```

Lý do là `WHERE` lọc các hàng nguồn trong cùng khối truy vấn; `gross_amount` là tên của một biểu thức đầu ra. Cách viết đúng là lặp lại biểu thức nguồn:

```sql
SELECT product_name,
       unit_price * quantity AS gross_amount
FROM lesson_line_items
WHERE unit_price * quantity > 50
ORDER BY gross_amount DESC;
```

Hoặc đưa cột tính toán vào một **khối truy vấn con**, rồi dùng alias như cột nguồn của khối ngoài:

```sql
SELECT calculated.product_name,
       calculated.gross_amount
FROM (
    SELECT product_name,
           unit_price * quantity AS gross_amount
    FROM lesson_line_items
) AS calculated
WHERE calculated.gross_amount > 50
ORDER BY calculated.gross_amount DESC;
```

Khối trong tạo cột `gross_amount`. Khối ngoài nhìn thấy nó như cột của bảng dẫn xuất `calculated`, nên `WHERE calculated.gross_amount > 50` hợp lệ.

### Dùng CTE để đặt tên cho kết quả trung gian

```sql
WITH priced_items AS (
    SELECT item_id,
           product_name,
           unit_price * quantity AS gross_amount,
           ROUND(unit_price * quantity * (1 - discount_rate), 2)
               AS net_amount
    FROM lesson_line_items
)
SELECT product_name,
       gross_amount,
       net_amount,
       gross_amount - net_amount AS saved_amount
FROM priced_items
WHERE net_amount >= 50
ORDER BY net_amount DESC;
```

CTE `priced_items` giúp biểu thức dài chỉ được viết một lần trong phần logic của truy vấn. Tên `gross_amount`, `net_amount` trong `SELECT` ngoài là những cột đã được CTE công bố. Chúng vẫn là dữ liệu kết quả của câu truy vấn, không tự được lưu vào `lesson_line_items`.

Các DBMS có một số ngoại lệ về alias trong `GROUP BY`, `HAVING` hoặc những mệnh đề khác. Trong PostgreSQL, có thể dùng alias đầu ra ở `ORDER BY` và một số cách dùng ở `GROUP BY`, nhưng không ở `WHERE`; nên tránh dựa vào ngoại lệ khi muốn SQL dễ di chuyển.

## 12. Một biểu thức mới được tính cho từng hàng hay cho cả bảng?

Không phải biểu thức nào trong `SELECT` cũng có cùng cấp độ tính toán.

### Biểu thức theo hàng

```sql
SELECT item_id,
       unit_price * quantity AS gross_amount
FROM lesson_line_items
ORDER BY item_id;
```

`gross_amount` được xác định từ các cột của **từng hàng**. Nếu bảng có bốn hàng, câu truy vấn không lọc thì có bốn hàng kết quả.

### Biểu thức tổng hợp

```sql
SELECT SUM(unit_price * quantity) AS total_gross_amount
FROM lesson_line_items;
```

`SUM` cộng các giá trị `unit_price * quantity` trên **nhiều hàng**; với dữ liệu mẫu, tổng là `50 + 90 + 0 + 90 = 230`.

Khi dùng `SUM` mà không có `GROUP BY`, câu truy vấn trả một hàng tổng hợp. Không thể tùy ý đặt cả một cột nguồn không tổng hợp cùng `SUM(...)` trong `SELECT` vì cột đó không xác định cho hàng kết quả tổng hợp.

Ví dụ gom theo nhóm ngày:

```sql
SELECT order_date,
       SUM(unit_price * quantity) AS daily_gross_amount
FROM lesson_line_items
GROUP BY order_date
ORDER BY order_date;
```

Mỗi ngày là một nhóm. Cột `daily_gross_amount` là kết quả của `SUM` trên các dòng thuộc cùng ngày, khác với biểu thức tính trên từng hàng.

### Tổng hợp có điều kiện ngay trong biểu thức

```sql
SELECT
    SUM(CASE
            WHEN quantity > 0 THEN unit_price * quantity
            ELSE 0::NUMERIC
        END) AS positive_quantity_total
FROM lesson_line_items;
```

`CASE` quyết định đóng góp của từng hàng, rồi `SUM` cộng các đóng góp. Đây là ví dụ kết hợp nhiều lớp biểu thức; vẫn cần hiểu cách truy vấn nhóm hàng trước khi sử dụng trong báo cáo.

## 13. Một số điều kiện biên: `NULL`, chia cho 0 và overflow

### Biểu thức chứa `NULL`

Trong biểu thức số học thông thường, nếu một toán hạng là `NULL`, kết quả thường là `NULL`:

```sql
SELECT 10::NUMERIC + NULL::NUMERIC AS unknown_sum;
```

Đây không phải số `10` hay `0`. `NULL` có nghĩa giá trị không xác định/không có, không phải số 0.

Nếu chính sách dữ liệu cho phép thay giá trị thiếu bằng 0, có thể viết:

```sql
SELECT item_id,
       COALESCE(unit_price, 0) * quantity AS gross_amount
FROM lesson_line_items;
```

Trong bảng thực hành, `unit_price` có ràng buộc `NOT NULL` nên phép `COALESCE` ở đây chỉ minh họa cú pháp. Ở bảng khác, việc thay giá trị thiếu bằng 0 phải dựa trên ý nghĩa nghiệp vụ.

### Bảo vệ phép chia cho 0

Ví dụ tính trung bình tiền trên số lượng đơn vị trong một dòng:

```sql
SELECT item_id,
       unit_price * quantity
           / NULLIF(quantity, 0) AS amount_per_unit
FROM lesson_line_items
ORDER BY item_id;
```

`NULLIF(quantity, 0)` trả `NULL` khi `quantity = 0`; do đó hàng `Tẩy` có `amount_per_unit = NULL` thay vì gây lỗi chia cho 0 trong PostgreSQL. Với những hàng có `quantity > 0`, kết quả bằng đơn giá ở dữ liệu mẫu.

Dù câu truy vấn tránh được lỗi, cần hiểu **`NULL` của tỷ lệ** biểu thị phép tính không xác định; không mặc định nó là 0. Có thể dùng `CASE` để thêm trạng thái giải thích:

```sql
SELECT item_id,
       CASE
           WHEN quantity = 0 THEN 'Không xác định'
           ELSE 'Hợp lệ'
       END AS calculation_status,
       unit_price * quantity / NULLIF(quantity, 0) AS amount_per_unit
FROM lesson_line_items;
```

### Tràn số và mất phần thập phân

Một phép cộng/nhân có thể vượt phạm vi kiểu trung gian trước khi gán vào kết quả. Trong PostgreSQL:

```sql
-- Có nguy cơ lỗi tràn số nguyên 32 bit
-- SELECT 2147483647::INTEGER + 1::INTEGER;

-- Nâng kiểu toán hạng trước khi cộng
SELECT 2147483647::BIGINT + 1::BIGINT AS safe_result;
```

Hơn nữa, `ROUND` hoặc `CAST` không biến một phép tính vốn sai/nguy cơ tràn thành đúng chỉ bằng cách đặt ở cuối biểu thức. Hãy chọn kiểu cho cả toán hạng và kết quả dựa vào phạm vi giá trị thực tế.

## 14. Giữ kết quả truy vấn dễ đọc và dễ bảo trì

Khi tạo nhiều cột từ biểu thức, một số nguyên tắc có ích:

1. **Đặt alias có nghĩa.** `gross_amount` rõ hơn `col3`; `has_discount` rõ hơn `flag`.
2. **Làm rõ đơn vị và tỷ lệ.** `discount_rate = 0.10` nghĩa là 10% nếu dữ liệu quy định theo phân số; đừng viết công thức như thể đó là số 10.
3. **Dùng dấu ngoặc cho công thức nghiệp vụ.** `unit_price * quantity * (1 - discount_rate)` thể hiện phần giảm giá.
4. **Ép kiểu trước phép tính khi cần.** `5::NUMERIC / 2` giữ phần lẻ, trong khi `5 / 2` bị chia nguyên ở PostgreSQL.
5. **Xử lý `NULL` theo nghĩa dữ liệu.** `COALESCE` chỉ nên dùng khi giá trị mặc định được phép.
6. **Tách biểu thức dài qua CTE khi cần tái sử dụng.** Tên trung gian giúp dễ kiểm tra công thức và giảm lặp.
7. **Dùng `ORDER BY` khi cần thứ tự kết quả.** Không có `ORDER BY`, thứ tự hàng không được bảo đảm.

### Cột tính toán trong `SELECT` khác với cột lưu trữ

| Cách dùng | Kết quả | Dữ liệu bảng gốc |
| --- | --- | --- |
| `SELECT unit_price * quantity AS amount` | Tạo cột kết quả của câu truy vấn | Không đổi |
| `SELECT ... FROM (SELECT ...) AS x` | Cho phép truy vấn ngoài dùng cột kết quả trung gian | Không đổi |
| `WITH x AS (...) SELECT ... FROM x` | Đặt tên cho kết quả trung gian trong phạm vi một câu SQL | Không đổi |
| `CREATE VIEW ...` | Lưu định nghĩa truy vấn để dùng lại; tùy DBMS có đặc điểm riêng | Không tự đồng nghĩa lưu vật lý từng giá trị kết quả |
| `ALTER TABLE ... ADD ...` hoặc cột generated | Thay đổi cấu trúc bảng theo cú pháp và khả năng DBMS | Có thay đổi schema, cần quản trị riêng |

Trong phạm vi bài này, ta **chỉ tạo cột kết quả truy vấn**, không thay đổi schema hoặc lưu giá trị tính toán lâu dài.

### Lưu ý hiệu năng

Cơ sở dữ liệu thường phải đánh giá biểu thức của các hàng được trả về. Với dữ liệu lớn, hàm phức tạp và phép tính lặp có thể tốn tài nguyên. Biểu thức trên cột trong điều kiện `WHERE` cũng có thể ảnh hưởng khả năng dùng index, tùy DBMS và index đã tạo.

Tuy nhiên, không nên bỏ biểu thức chỉ vì lo ngại chung chung. Hãy thiết kế rõ ngữ nghĩa trước, sau đó kiểm tra kế hoạch truy vấn/hiệu năng trên dữ liệu thực tế khi cần.

## 15. Khác biệt cú pháp theo hệ quản trị

| Chủ đề | PostgreSQL | Những khác biệt thường gặp |
| --- | --- | --- |
| `SELECT` không có `FROM` | Hỗ trợ `SELECT 2 + 3` | Một số phiên bản Oracle đời cũ yêu cầu `FROM DUAL` |
| Nối chuỗi | `a || b` | SQL Server thường dùng `+` hoặc `CONCAT`; MySQL có `CONCAT` và `||` có ngữ nghĩa phụ thuộc cấu hình |
| Ép kiểu | `value::NUMERIC` hoặc `CAST(value AS NUMERIC)` | `CAST` thường dễ di chuyển hơn; kiểu đích có tên/giới hạn khác nhau |
| Boolean trong `SELECT` | `quantity > 0 AS has_quantity` | DBMS không có cùng kiểu boolean hoặc không cho biểu thức điều kiện xuất trực tiếp trong `SELECT` có thể cần `CASE` |
| Ngày + số ngày | `order_date + 7` | DBMS khác có thể dùng `DATEADD`, `INTERVAL` hoặc hàm riêng |
| Hàm làm tròn | `ROUND(numeric, 2)` | Quy tắc chọn kiểu đối số, rounding và kết quả có thể khác |
| Alias với khoảng trắng | `AS "Thành tiền"` | MySQL thường dùng backtick; SQL Server hỗ trợ dấu ngoặc vuông |
| `NULL` khi nối chuỗi | `a || NULL` thường trả `NULL` | `CONCAT` và các hệ quản trị có thể xử lý `NULL` khác nhau |

Nếu học trên một hệ cụ thể, hãy giữ nguyên **ý nghĩa phép tính** và thay cú pháp theo hệ đó; không giả định mọi ví dụ PostgreSQL đều chạy nguyên bản ở nơi khác.

## 16. Bài tập tự luyện

Các bài dưới đây dùng **bảng tạm `lesson_line_items`** đã tạo ở mục 2 trên PostgreSQL. Hãy thử viết câu `SELECT` trước khi mở gợi ý.

### Bài 1. Thêm hai cột hằng

Viết một câu truy vấn trả về `item_id`, `product_name` và hai cột kết quả:

- `data_source` luôn có giá trị `'practice'`.
- `report_version` luôn có giá trị số `1`.

Sắp xếp theo `item_id` tăng dần.

### Bài 2. Tính thành tiền sau giảm giá

Trả về `product_name`, `gross_amount` và `net_amount`:

- `gross_amount = unit_price * quantity`;
- `net_amount = gross_amount * (1 - discount_rate)`;
- Làm tròn `net_amount` về hai chữ số thập phân.

Có thể viết trực tiếp công thức dài trong `SELECT`.

### Bài 3. Tạo mã hiển thị sản phẩm

Trả về `product_name` và `product_label` theo mẫu:

```text
Bút bi (ID: 1)
Sổ tay (ID: 2)
```

Dùng toán tử nối chuỗi và ép `item_id` thành chuỗi.

### Bài 4. Phân loại số lượng

Trả về `product_name` và `quantity_status` theo quy tắc:

- `quantity = 0`: `'Hết số lượng'`;
- `quantity < 3` nhưng lớn hơn 0: `'Ít'`;
- Còn lại: `'Đủ'`.

Dùng `CASE`.

### Bài 5. Lọc theo cột tính toán

Lọc sản phẩm có `net_amount >= 70`, sắp xếp theo `net_amount` giảm dần. Hãy làm hai cách: lặp lại biểu thức trong `WHERE` và dùng CTE `priced_items`.

### Bài 6. Tạo ngày hẹn kiểm tra

Trả về `product_name`, `order_date` và `review_date` bằng `order_date + 14`. Giải thích tại sao `review_date` không có trong cấu trúc bảng.

### Bài 7. Phân biệt `NULL` với chuỗi rỗng

Tạo cột `note_display`:

- Khi `note` là `NULL` hoặc chỉ chứa chuỗi rỗng/khoảng trắng, hiển thị `'Không có ghi chú'`.
- Các trường hợp khác giữ nội dung đã bỏ khoảng trắng đầu/cuối.

Dùng `TRIM`, `NULLIF` và `COALESCE`.

### Bài 8. Tổng hợp biểu thức

Tính `SUM(unit_price * quantity)` và `SUM(ROUND(unit_price * quantity * (1 - discount_rate), 2))` trên cả bảng. Mô tả sự khác nhau giữa phép tính của từng hàng và phép tổng hợp.

## 17. Gợi ý đáp án

**Bài 1:**

```sql
SELECT item_id,
       product_name,
       'practice' AS data_source,
       1 AS report_version
FROM lesson_line_items
ORDER BY item_id;
```

**Bài 2:**

```sql
SELECT product_name,
       unit_price * quantity AS gross_amount,
       ROUND(unit_price * quantity * (1 - discount_rate), 2)
           AS net_amount
FROM lesson_line_items
ORDER BY item_id;
```

Các giá trị `net_amount` là `45.00`, `90.00`, `0.00`, `72.00` theo thứ tự `item_id`.

**Bài 3:**

```sql
SELECT product_name,
       product_name || ' (ID: ' || item_id::TEXT || ')'
           AS product_label
FROM lesson_line_items
ORDER BY item_id;
```

**Bài 4:**

```sql
SELECT product_name,
       CASE
           WHEN quantity = 0 THEN 'Hết số lượng'
           WHEN quantity < 3 THEN 'Ít'
           ELSE 'Đủ'
       END AS quantity_status
FROM lesson_line_items
ORDER BY item_id;
```

**Bài 5, cách lặp biểu thức:**

```sql
SELECT product_name,
       ROUND(unit_price * quantity * (1 - discount_rate), 2)
           AS net_amount
FROM lesson_line_items
WHERE ROUND(unit_price * quantity * (1 - discount_rate), 2) >= 70
ORDER BY net_amount DESC;
```

**Bài 5, cách dùng CTE:**

```sql
WITH priced_items AS (
    SELECT product_name,
           ROUND(unit_price * quantity * (1 - discount_rate), 2)
               AS net_amount
    FROM lesson_line_items
)
SELECT product_name, net_amount
FROM priced_items
WHERE net_amount >= 70
ORDER BY net_amount DESC;
```

Hai sản phẩm thỏa điều kiện là `Sổ tay` (`90.00`) và `Bìa hồ sơ` (`72.00`).

**Bài 6:**

```sql
SELECT product_name,
       order_date,
       order_date + 14 AS review_date
FROM lesson_line_items
ORDER BY item_id;
```

`review_date` là một **cột kết quả tính toán** trong `SELECT`, không phải cột được thêm vào bảng.

**Bài 7:**

```sql
SELECT item_id,
       COALESCE(
           NULLIF(TRIM(note), ''),
           'Không có ghi chú'
       ) AS note_display
FROM lesson_line_items
ORDER BY item_id;
```

**Bài 8:**

```sql
SELECT SUM(unit_price * quantity) AS total_gross_amount,
       SUM(
           ROUND(unit_price * quantity * (1 - discount_rate), 2)
       ) AS total_net_amount
FROM lesson_line_items;
```

Kết quả theo dữ liệu mẫu: `total_gross_amount = 230.00`, `total_net_amount = 207.00`. Biểu thức nhân được đánh giá theo từng hàng; `SUM` cộng các giá trị đó trên toàn bộ các hàng phù hợp. Nếu phép tính có nhiều dòng và phải làm tròn, cần phân biệt yêu cầu “làm tròn từng dòng rồi cộng” với “cộng trước rồi làm tròn” vì hai cách có thể cho kết quả khác nhau.

Khi đọc một câu `SELECT`, hãy hỏi: **cột nào lấy trực tiếp từ bảng, cột nào dùng hằng, cột nào tính từ biểu thức, mỗi biểu thức có kiểu dữ liệu gì, và alias kết quả được dùng ở phạm vi nào?** Trả lời được năm điều đó, bạn sẽ tạo được các cột kết quả có ý nghĩa mà vẫn giữ nguyên dữ liệu nguồn.
