# NULL trong phép tính, nối chuỗi và hàm xử lý dữ liệu

Trong **Database SQL**, `NULL` xuất hiện khi một cột chưa có giá trị, thông tin chưa được ghi nhận hoặc một biểu thức không có kết quả xác định. Khi đưa `NULL` vào phép tính, ghép văn bản hoặc gọi hàm, kết quả có thể khác xa trực giác từ các ngôn ngữ lập trình thông thường. Hiểu đúng cách SQL xử lý `NULL` giúp tránh tính thiếu doanh thu, biến “chưa biết” thành 0, tạo nhãn hiển thị sai hoặc thống kê sai số dòng.

Bài này tập trung vào **giá trị được tạo ra từ biểu thức**: toán tử số học, phép nối chuỗi, hàm xử lý dữ liệu và hàm tổng hợp. Các khác biệt giữa PostgreSQL, MySQL/MariaDB, SQL Server, SQLite và Oracle Database được ghi rõ để không áp dụng nhầm cú pháp của một hệ vào hệ khác.

## 1. NULL là gì khi nằm trong biểu thức?

`NULL` trong SQL có nghĩa là **không có giá trị được biết hoặc được cung cấp trong ngữ cảnh đang xét**. Nó không đồng nghĩa với một giá trị số hay ký tự cụ thể.

| Giá trị | Diễn giải | Có giống `NULL` không? |
| --- | --- | --- |
| `NULL` | Không có giá trị SQL | Chính là `NULL` |
| `0` | Số không, đã biết | Không |
| `''` | Chuỗi rỗng trong đa số DBMS | Không, trừ cách xử lý đặc thù của Oracle đối với chuỗi rỗng |
| `'NULL'` | Chuỗi gồm bốn ký tự `N`, `U`, `L`, `L` | Không |
| `FALSE` | Giá trị logic sai | Không |
| `'không rõ'` | Một chuỗi văn bản mô tả | Không |

Ví dụ trên PostgreSQL:

```sql
SELECT
    NULL IS NULL AS missing_value,
    0 IS NULL AS zero_is_missing,
    '' IS NULL AS empty_text_is_missing,
    'NULL' IS NULL AS word_null_is_missing;
```

Chỉ biểu thức đầu tiên trả về `TRUE`. Với **Oracle Database**, chuỗi rỗng `''` hiện được xem như `NULL` trong các ngữ cảnh chuỗi ký tự; vì vậy kết quả liên quan chuỗi rỗng phải được diễn giải theo hệ đang dùng.

### “Không biết” khác “bằng nhau”

`NULL = NULL` không cho `TRUE`; phép so sánh thông thường với `NULL` trả về trạng thái logic **UNKNOWN**. Khi cần xác định một giá trị có thiếu hay không, dùng:

```sql
WHERE column_name IS NULL
WHERE column_name IS NOT NULL
```

Quy tắc này ảnh hưởng đến `CASE WHEN`, `WHERE` và các hàm điều kiện: nhánh `WHEN` chỉ được chọn khi điều kiện là `TRUE`, không phải `FALSE` hoặc `UNKNOWN`.

## 2. NULL lan truyền trong phép tính số học

Với các toán tử số học thông thường, nếu một toán hạng là `NULL` thì kết quả thường là `NULL`: không thể suy ra số kết quả khi thiếu một thành phần cần thiết.

```sql
-- Các ví dụ SQL đơn giản:
SELECT 10 + NULL AS addition_result;
SELECT 10 - NULL AS subtraction_result;
SELECT 10 * NULL AS multiplication_result;
SELECT 10 / NULL AS division_result;
```

Tất cả các cột trên đều có giá trị `NULL`. Tính chất này **không phải** quy luật toán học “NULL là số 0”; nó là quy tắc đánh giá dữ liệu thiếu trong SQL.

Chẳng hạn:

```sql
-- unit_price: đơn giá; quantity: số lượng
SELECT unit_price * quantity AS line_amount
FROM order_items;
```

Nếu `unit_price = 100` và `quantity = NULL`, số tiền không thể kết luận bằng 0 hay 100. Kết quả `line_amount` là `NULL`. Nhưng nếu `quantity = 0` và đơn giá 100, tích bằng **0** vì số lượng đã được biết là 0.

| `unit_price` | `quantity` | `unit_price * quantity` | Ý nghĩa |
| ---: | ---: | ---: | --- |
| 100 | 2 | 200 | Đủ dữ liệu để tính |
| 100 | 0 | 0 | Số lượng đã biết là 0 |
| 100 | `NULL` | `NULL` | Chưa biết số lượng |
| `NULL` | 2 | `NULL` | Chưa biết đơn giá |
| `NULL` | `NULL` | `NULL` | Thiếu cả hai giá trị |

**Đặc biệt:** `0 * NULL` cũng là `NULL`, không phải 0. SQL không áp dụng phép rút gọn đại số để coi giá trị thiếu là số 0.

### Thứ tự phép tính không làm NULL biến mất

```sql
SELECT
    (100 + NULL) * 2 AS first_result,
    100 + (NULL * 2) AS second_result;
```

Cả hai đều `NULL`. Tương tự, `ROUND(NULL, 2)` trong các DBMS thông dụng trả về `NULL`. Nhiều hàm số học và chuyển kiểu thông thường vẫn trả `NULL` nếu đầu vào bắt buộc bị thiếu:

```sql
-- PostgreSQL:
SELECT
    ABS(NULL::numeric) AS abs_missing,
    ROUND(NULL::numeric, 2) AS rounded_missing,
    CAST(NULL AS numeric(10, 2)) AS converted_missing;
```

Dấu `::numeric` là cú pháp ép kiểu riêng của PostgreSQL. Trong SQL chung có thể viết `CAST(NULL AS DECIMAL(10, 2))`.

## 3. Phép chia và NULLIF: bảo vệ khỏi số chia bằng 0

`NULL` ở mẫu số tạo ra kết quả thiếu, còn **số chia thực sự bằng 0** có thể gây lỗi phép chia (hành vi cụ thể khác nhau giữa các DBMS). `NULLIF` giúp biểu diễn “mẫu số không hợp lệ thì không tính” mà không tự gán kết quả sai.

`NULLIF(a, b)` trả về:

- `NULL` nếu `a` và `b` bằng nhau theo phép so sánh SQL;
- giá trị của `a` nếu chúng không bằng nhau;
- `NULL` khi `a` vốn là `NULL`.

Ví dụ PostgreSQL:

```sql
SELECT
    100.0 / NULLIF(4, 0) AS amount_per_item,
    100.0 / NULLIF(0, 0) AS no_valid_divisor,
    100.0 / NULLIF(NULL::integer, 0) AS unknown_divisor;
```

Kết quả lần lượt là **25**, `NULL` và `NULL`. `NULLIF(0,0)` trả `NULL` để phép chia không thực hiện phép chia cho số không.

Trong bảng đơn hàng:

```sql
SELECT
    order_id,
    total_amount,
    item_count,
    total_amount / NULLIF(item_count, 0) AS average_per_item
FROM orders;
```

Khi `item_count` là 0 hoặc `NULL`, cột `average_per_item` là `NULL`. Đây là một chính sách tính toán: “không có mẫu số hợp lệ thì kết quả không xác định”. Nếu nghiệp vụ yêu cầu báo lỗi hoặc trạng thái riêng cho số lượng 0, hãy dùng `CASE` thay vì âm thầm coi cả hai trường hợp là giống nhau.

Lưu ý nếu tử số và mẫu số đều là **kiểu số nguyên**, một số DBMS có thể thực hiện chia số nguyên (ví dụ làm mất phần thập phân). Chuyển sang kiểu thập phân phù hợp khi cần kết quả có phần lẻ:

```sql
-- Cú pháp CAST có tính phổ biến:
SELECT CAST(5 AS DECIMAL(12, 2)) / NULLIF(2, 0) AS result;
```

## 4. COALESCE: giá trị thay thế khi dữ liệu thiếu

`COALESCE(value1, value2, ...)` là biểu thức SQL chuẩn trả về **đối số đầu tiên khác NULL**. Đây là cách phổ biến để cung cấp giá trị dự phòng có chủ đích.

```sql
SELECT
    COALESCE(NULL, 10) AS example_one,
    COALESCE(NULL, NULL, 25) AS example_two,
    COALESCE(0, 10) AS zero_is_not_missing,
    COALESCE('Đã nhập', 'Chưa nhập') AS text_value;
```

Kết quả tương ứng là 10, 25, 0 và `Đã nhập`. Vì **0 khác NULL**, `COALESCE(0, 10)` luôn giữ số 0.

### Đặt COALESCE đúng vị trí trong biểu thức

Ba cách viết dưới đây có ý nghĩa khác nhau:

```sql
SELECT
    COALESCE(unit_price * quantity, 0) AS total_a,
    COALESCE(unit_price, 0) * quantity AS total_b,
    COALESCE(unit_price, 0) * COALESCE(quantity, 0) AS total_c
FROM order_items;
```

| Cách viết | Khi `unit_price` hoặc `quantity` thiếu | Hệ quả nghiệp vụ |
| --- | --- | --- |
| `COALESCE(unit_price * quantity, 0)` | Kết quả `NULL` bị đổi thành 0 | Biến mọi phép tính không xác định thành 0 |
| `COALESCE(unit_price, 0) * quantity` | Chỉ đơn giá thiếu được thay 0; số lượng thiếu vẫn làm kết quả `NULL` | Có thể coi đơn giá chưa nhập là 0 |
| `COALESCE(unit_price, 0) * COALESCE(quantity, 0)` | Cả hai đầu vào thiếu đều thay 0 | Có thể che giấu dữ liệu chưa được nhập |

Cả ba đều là SQL hợp lệ, nhưng **không tương đương về ý nghĩa**. Với dữ liệu tài chính, thay đơn giá hoặc số lượng chưa biết bằng 0 có thể tạo số liệu tưởng như hợp lệ. Chỉ dùng `COALESCE` khi quy tắc nghiệp vụ thật sự xác định `NULL` mang giá trị mặc định đó.

Một tình huống hợp lý: nếu `discount_amount = NULL` được **quy ước rõ ràng** là “không có chiết khấu”, ta có thể viết:

```sql
SELECT
    unit_price * quantity - COALESCE(discount_amount, 0) AS net_amount
FROM order_items;
```

Nhưng đơn giá hoặc số lượng thiếu vẫn dẫn đến `NULL`, giúp giữ lại sự không chắc chắn của dữ liệu đầu vào.

### Các vấn đề kiểu dữ liệu của COALESCE

Các đối số cần tương thích với cách DBMS suy luận/chuyển kiểu. Ví dụ `COALESCE(price, 'không rõ')` có thể báo lỗi nếu `price` là số và chuỗi không chuyển được sang số. Với nhãn hiển thị, nên chủ động chuyển số thành văn bản:

```sql
-- PostgreSQL:
SELECT COALESCE(CAST(unit_price AS text), '(chưa có giá)') AS price_label
FROM order_items;
```

`text` là tên kiểu văn bản của PostgreSQL; DBMS khác có thể dùng `VARCHAR` hoặc cú pháp chuyển kiểu riêng. Cần kiểm tra kiểu và độ dài kết quả, nhất là khi kết hợp giá trị số, ngày và chuỗi.

Trong một số hệ, biểu thức ở các nhánh không được chọn vẫn có thể bị kiểm tra kiểu hoặc tối ưu hóa trước khi chạy. Không dùng `COALESCE` như một cơ chế che mọi lỗi cú pháp/chuyển kiểu; nó chuyên xử lý **giá trị NULL**.

## 5. CASE: phân biệt NULL với 0 và các trạng thái khác

`CASE` phù hợp khi đầu ra phụ thuộc nhiều điều kiện, không chỉ cần một giá trị dự phòng.

```sql
SELECT
    order_id,
    CASE
        WHEN quantity IS NULL THEN 'Chưa biết số lượng'
        WHEN quantity = 0 THEN 'Số lượng bằng 0'
        WHEN quantity > 0 THEN 'Có số lượng'
        ELSE 'Số lượng âm hoặc ngoài phạm vi'
    END AS quantity_status
FROM order_items;
```

Thứ tự các nhánh quan trọng: `WHEN quantity IS NULL` giúp diễn đạt riêng trạng thái thiếu. Nếu không có nhánh nào đúng và không có `ELSE`, `CASE` trả về `NULL`.

Không viết:

```sql
-- SAI về ý nghĩa: quantity = NULL không trả TRUE
CASE WHEN quantity = NULL THEN 'Thiếu' ELSE 'Có' END
```

Hãy viết `quantity IS NULL`.

### COALESCE, NULLIF và CASE giải quyết ba bài toán khác nhau

| Biểu thức | Công dụng chính | Ví dụ |
| --- | --- | --- |
| `COALESCE(x, y)` | Chọn giá trị dự phòng khi `x` thiếu | `COALESCE(note_text, '(không có ghi chú)')` |
| `NULLIF(x, y)` | Biến một giá trị cụ thể thành `NULL` khi bằng `y` | `NULLIF(item_count, 0)` |
| `CASE WHEN ... THEN ... ELSE ... END` | Phân nhánh theo điều kiện nghiệp vụ | Phân biệt số lượng chưa biết, bằng 0 và dương |

Các biểu thức có thể phối hợp:

```sql
SELECT
    CASE
        WHEN item_count IS NULL THEN 'Chưa nhập số lượng'
        WHEN item_count = 0 THEN 'Không thể tính giá mỗi món'
        ELSE 'Có thể tính'
    END AS status,
    total_amount / NULLIF(item_count, 0) AS amount_per_item
FROM orders;
```

Cột `status` giữ nguyên lý do không tính được; cột số `amount_per_item` vẫn biểu diễn dữ liệu không có kết quả bằng `NULL`.

## 6. NULL trong nối chuỗi: không phải DBMS nào cũng giống nhau

Giả sử cần tạo họ tên đầy đủ:

`first_name = 'An'`, `last_name = NULL`.

Vấn đề là khi nối chuỗi với một giá trị thiếu, hệ quản trị **có thể trả `NULL` hoặc bỏ qua đối số thiếu**, tùy toán tử/hàm và DBMS.

### Toán tử nối chuỗi `||`

Trong SQL tiêu chuẩn và trong PostgreSQL/SQLite, toán tử `||` nối văn bản; nếu một toán hạng là `NULL`, toàn bộ biểu thức thường trả `NULL`.

```sql
-- PostgreSQL / SQLite:
SELECT 'Xin chào ' || 'An' AS full_message;
SELECT 'Xin chào ' || NULL AS message_with_null;
```

Biểu thức thứ hai trả `NULL` trong hai DBMS này.

Để tạo chuỗi hiển thị có chủ đích, dùng `COALESCE`:

```sql
-- PostgreSQL / SQLite:
SELECT 'Xin chào ' || COALESCE(NULL, '(chưa có tên)') AS message;
```

Kết quả là `Xin chào (chưa có tên)`. Đây là lựa chọn trình bày; không có nghĩa giá trị trong bảng đã được điền tên mặc định.

**Oracle Database có quy tắc khác:** Oracle hiện xử lý chuỗi rỗng như `NULL`; phép `'||'` với một chuỗi khác `NULL` thường trả về chuỗi còn lại (`'A' || NULL` trả `'A'`), thay vì bắt buộc trả `NULL` như PostgreSQL. Không dùng hành vi Oracle để suy luận về PostgreSQL/SQLite.

### Hàm CONCAT và CONCAT_WS

`CONCAT` không có cùng quy tắc `NULL` ở mọi hệ. Bảng sau thể hiện hành vi phổ biến đối với các bản DBMS hiện đại:

| DBMS | Ví dụ nối chuỗi | Cách xử lý khi một đối số là `NULL` |
| --- | --- | --- |
| **PostgreSQL** | `CONCAT('A', NULL, 'B')` | Bỏ qua giá trị `NULL`; kết quả `AB` |
| **MySQL / MariaDB** | `CONCAT('A', NULL, 'B')` | Toàn bộ kết quả là `NULL` |
| **SQL Server** | `CONCAT('A', NULL, 'B')` | Chuyển `NULL` thành chuỗi rỗng; kết quả `AB` |
| **SQLite** | `'A' || NULL || 'B'` | Kết quả `NULL`; hàm `concat()` chỉ có ở các phiên bản SQLite hỗ trợ hàm này và có cách bỏ qua `NULL` riêng |
| **Oracle Database** | `'A' || NULL || 'B'` | Thường trả `AB` theo ngữ nghĩa nối chuỗi Oracle hiện hành |

**SQL Server:** toán tử `+` thường dùng cho nối chuỗi, nhưng khi một toán hạng là `NULL`, kết quả là `NULL` với `CONCAT_NULL_YIELDS_NULL = ON` (thiết lập này luôn bật trên SQL Server 2017 trở lên). Hàm `CONCAT` của SQL Server lại xem các đối số `NULL` như chuỗi rỗng. Vì vậy ngay trong cùng SQL Server, `'A' + NULL` và `CONCAT('A', NULL)` có thể khác nhau.

**MySQL:** hàm `CONCAT_WS(separator, arg1, arg2, ...)` bỏ qua các đối số `NULL` và nối các giá trị còn lại bằng separator. Nhưng **separator là `NULL` thì kết quả của MySQL là `NULL`**. Các chuỗi rỗng vẫn được coi là giá trị và có thể tạo dấu phân cách dư.

```sql
-- PostgreSQL:
SELECT
    'A' || NULL AS operator_result,
    CONCAT('A', NULL, 'B') AS concat_result,
    CONCAT_WS(' ', 'Nguyễn', NULL, 'An') AS full_name;

-- MySQL / MariaDB:
SELECT
    CONCAT('A', NULL, 'B') AS concat_result,
    CONCAT_WS(' ', 'Nguyễn', NULL, 'An') AS full_name;
```

Không nên viết công thức ghép tên mà không kiểm tra quy tắc của DBMS và **độ khác biệt giữa NULL với chuỗi rỗng**.

### Ghép tên hoặc nhãn hiển thị mà không có dấu cách thừa

Với PostgreSQL, `CONCAT_WS(' ', first_name, last_name)` thường thuận tiện hơn `first_name || ' ' || last_name` khi một trong hai thành phần là `NULL`:

```sql
-- PostgreSQL:
SELECT
    CONCAT_WS(' ', first_name, last_name) AS display_name
FROM customers;
```

Hàm bỏ qua đối số `NULL` khi nối. Tuy nhiên, nếu một thành phần là `''` hoặc chỉ chứa khoảng trắng, dữ liệu vẫn có thể gây khoảng trắng thừa. Có thể chuẩn hóa giá trị trắng trước khi hiển thị:

```sql
-- PostgreSQL:
SELECT
    NULLIF(
        CONCAT_WS(
            ' ',
            NULLIF(TRIM(first_name), ''),
            NULLIF(TRIM(last_name), '')
        ),
        ''
    ) AS display_name
FROM customers;
```

Ở đây `TRIM` loại khoảng trắng đầu/cuối, `NULLIF(..., '')` đổi chuỗi rỗng sau khi trim thành `NULL`, `CONCAT_WS` bỏ qua thành phần thiếu và `NULLIF` cuối cùng biến kết quả rỗng thành `NULL` khi cả hai tên không có. Đây là **quy tắc xây dựng nhãn ví dụ**, không phải quyết định rằng tên trong database phải bị sửa hay xóa khoảng trắng.

## 7. NULL trong các hàm xử lý chuỗi, số, ngày

Nhiều hàm thông thường là **strict / NULL-propagating**: đầu vào cần thiết là `NULL` thì đầu ra là `NULL`. Tuy vậy, có các ngoại lệ quan trọng như `COALESCE`, `CONCAT` theo DBMS và các hàm tổng hợp.

Ví dụ PostgreSQL:

```sql
SELECT
    UPPER(NULL::text) AS upper_missing,
    LOWER(NULL::text) AS lower_missing,
    TRIM(NULL::text) AS trimmed_missing,
    LENGTH(NULL::text) AS length_missing,
    ROUND(NULL::numeric, 2) AS rounded_missing,
    CAST(NULL AS date) AS date_missing;
```

Các kết quả trên đều `NULL`. Một chuỗi `'NULL'` lại là dữ liệu văn bản bình thường:

```sql
SELECT
    UPPER('null') AS upper_text,
    LENGTH('NULL') AS text_length;
```

Kết quả tương ứng là `NULL` **dưới dạng chuỗi bốn ký tự** và số `4`; không được nhầm biểu diễn chữ “NULL” trên màn hình kết quả với giá trị SQL `NULL`. Trong client SQL, hãy xem công cụ hiển thị hai loại giá trị thế nào.

### Dùng kết hợp NULLIF và COALESCE để làm sạch dữ liệu đầu vào

Giả sử người dùng có thể gửi ghi chú rỗng hoặc chỉ gồm dấu cách, còn ứng dụng muốn hiển thị “Không có ghi chú”:

```sql
-- PostgreSQL và các hệ hỗ trợ cú pháp TRIM thông dụng:
SELECT
    COALESCE(NULLIF(TRIM(note_text), ''), '(không có ghi chú)') AS note_label
FROM order_items;
```

Diễn tiến:

1. `TRIM(note_text)` bỏ khoảng trắng đầu/cuối khi `note_text` khác `NULL`.
2. `NULLIF(..., '')` chuyển chuỗi rỗng sau trim thành `NULL`.
3. `COALESCE(..., '(không có ghi chú)')` tạo nhãn dự phòng.

Công thức này biểu diễn **quy tắc ứng dụng**: đối xử ghi chú trắng như thiếu. Nếu khoảng trắng là dữ liệu có ý nghĩa, đừng áp dụng công thức.

**Lưu ý Oracle:** vì Oracle coi chuỗi rỗng như `NULL` trong nhiều ngữ cảnh kiểu ký tự, cách kiểm tra `''` và kiểu kết quả có thể khác; cần xem lại quy tắc khi chuyển truy vấn giữa DBMS.

### Hàm xử lý lỗi chuyển đổi có thể trả NULL vì lý do khác

Một số DBMS có hàm chuyển kiểu “thử chuyển”, chẳng hạn `TRY_CAST` trong SQL Server, trả `NULL` khi phép chuyển đổi thất bại ở một số trường hợp. Kết quả `NULL` khi ấy có thể là **dữ liệu đầu vào thiếu** hoặc **dữ liệu sai định dạng**. Nếu nghiệp vụ cần phân biệt, hãy lưu riêng trạng thái lỗi và giá trị ban đầu thay vì cho rằng mọi `NULL` đều cùng một nguyên nhân.

## 8. Các hàm tổng hợp không lan truyền NULL như phép cộng từng dòng

Một khác biệt rất quan trọng: các hàm tổng hợp `SUM`, `AVG`, `MIN`, `MAX` và `COUNT(expression)` thông thường **bỏ qua giá trị `NULL` trong tập đầu vào**. Riêng `COUNT(*)` đếm số dòng, kể cả dòng có cột `NULL`.

Giả sử cột `quantity` chứa:

```text
2
NULL
3
0
5
```

Kết quả:

| Biểu thức | Kết quả | Giải thích |
| --- | ---: | --- |
| `COUNT(*)` | 5 | Có 5 dòng |
| `COUNT(quantity)` | 4 | Có 4 giá trị quantity khác `NULL` |
| `SUM(quantity)` | 10 | Tổng của 2, 3, 0, 5 |
| `AVG(quantity)` | 2,5 | Chia cho 4 giá trị đã biết |
| `AVG(COALESCE(quantity, 0))` | 2 | Thiếu được đổi thành 0, rồi chia cho 5 dòng |
| `MIN(quantity)` | 0 | Bỏ qua `NULL`, lấy giá trị nhỏ nhất |
| `MAX(quantity)` | 5 | Bỏ qua `NULL`, lấy giá trị lớn nhất |

`AVG(COALESCE(quantity, 0))` **khác về nghiệp vụ** so với `AVG(quantity)`. Công thức đầu ngầm giả định thông tin chưa nhập có giá trị 0, kéo trung bình xuống. Không đưa `COALESCE` vào hàm tổng hợp theo thói quen.

### Khi không còn giá trị nào để tổng hợp

Nếu một nhóm/dataset không có giá trị khác `NULL`:

- `COUNT(expression)` trả `0`.
- `SUM(expression)`, `AVG(expression)`, `MIN(expression)` và `MAX(expression)` thường trả `NULL`.
- Trên tập rỗng, một truy vấn tổng hợp không có `GROUP BY` vẫn thường tạo một dòng kết quả với `COUNT(*) = 0` và `SUM(...) = NULL`.

Ví dụ PostgreSQL:

```sql
SELECT
    COUNT(*) AS matched_rows,
    COUNT(quantity) AS known_quantities,
    SUM(quantity) AS sum_of_known_quantities
FROM order_items
WHERE order_id = -1;
```

Khi không có `order_id = -1`, `matched_rows` bằng 0 và `sum_of_known_quantities` là `NULL`. Nếu báo cáo yêu cầu tổng bằng 0 cho tập không có dòng, có thể viết `COALESCE(SUM(quantity), 0)`. Lưu ý phép thay thế này chỉ diễn ra **sau khi tổng hợp**; nó không tự đồng nghĩa với việc coi từng dòng thiếu quantity là 0.

### Cộng từng biểu thức khác cộng từng cột

Hai công thức này có thể ra số khác nhau:

```sql
SELECT
    SUM(unit_price * quantity) AS sum_of_valid_line_amounts,
    SUM(unit_price) * SUM(quantity) AS product_of_sums
FROM order_items;
```

`SUM(unit_price * quantity)` chỉ cộng những **tích có đủ hai toán hạng**. `SUM(unit_price) * SUM(quantity)` cộng giá và số lượng trên hai tập giá trị không `NULL` có thể khác nhau, sau đó nhân hai tổng; nó **không phải công thức tổng tiền đơn hàng**.

Nếu cần biết bao nhiêu dòng chưa đủ dữ liệu để tính tổng, ghi thêm số lượng dòng thiếu thay vì chỉ xem `SUM`:

```sql
SELECT
    COUNT(*) AS total_rows,
    COUNT(unit_price * quantity) AS calculable_rows,
    COUNT(*) - COUNT(unit_price * quantity) AS incomplete_rows,
    SUM(unit_price * quantity) AS known_amount
FROM order_items;
```

Như vậy báo cáo vừa cho tổng của các dòng tính được, vừa cho biết số dòng chưa thể tính.

## 9. Sự khác biệt giữa COUNT, phép toán và hàm nhiều tham số

Quy tắc “hễ có `NULL` là kết quả `NULL`” **không thể áp cho mọi hàm SQL**. Phải phân biệt:

| Loại | Ví dụ | Quy tắc điển hình |
| --- | --- | --- |
| Phép tính trên một dòng | `price * qty` | Nếu toán hạng cần thiết thiếu, kết quả `NULL` |
| Hàm số học/chuỗi thông thường | `ROUND(price, 2)`, `UPPER(name)` | Thường trả `NULL` khi đầu vào bắt buộc là `NULL` |
| Hàm lấy giá trị dự phòng | `COALESCE(x, y)` | Chọn đối số đầu tiên khác `NULL` |
| Hàm tạo NULL theo điều kiện | `NULLIF(x, 0)` | Trả `NULL` nếu bằng giá trị so sánh |
| Biểu thức điều kiện | `CASE WHEN ... THEN ...` | Chọn nhánh thỏa điều kiện |
| Hàm nối chuỗi | `CONCAT(...)` | **Phụ thuộc DBMS**; không giả định mọi hệ bỏ qua `NULL` |
| Hàm tổng hợp | `SUM(x)`, `AVG(x)` | Bỏ qua giá trị `NULL` |
| Hàm đếm | `COUNT(*)` / `COUNT(x)` | Đếm mọi dòng / đếm giá trị khác `NULL` |

Cả một số hàm như `GREATEST` và `LEAST` cũng có khác biệt theo DBMS về `NULL`: PostgreSQL thường bỏ qua đối số `NULL` và chỉ trả `NULL` khi không có đối số hợp lệ; một số hệ khác trả `NULL` nếu **bất kỳ** đối số nào là `NULL`. Do đó không tự dùng `GREATEST`/`LEAST` thay cho logic nghiệp vụ đa hệ nếu chưa biết quy tắc phiên bản đang chạy.

### Hàm thay thế NULL theo từng DBMS

SQL chuẩn có `COALESCE`; các DBMS còn cung cấp tên riêng:

| Hệ quản trị | Hàm/thành phần thường gặp | Ghi chú |
| --- | --- | --- |
| PostgreSQL | `COALESCE(x, y)`, `NULLIF(x, y)` | Dùng trực tiếp cú pháp chuẩn; `ISNULL` không phải hàm SQL Server ở PostgreSQL |
| MySQL / MariaDB | `IFNULL(x, y)`, `COALESCE(...)` | `IFNULL` có hai đối số |
| SQL Server | `ISNULL(x, y)`, `COALESCE(...)` | `ISNULL` và `COALESCE` có khác biệt về suy luận kiểu và nullability metadata |
| SQLite | `IFNULL(x, y)`, `COALESCE(...)` | `IFNULL` có hai đối số |
| Oracle Database | `NVL(x, y)`, `COALESCE(...)` | `NVL` có quy tắc chuyển kiểu/đánh giá khác `COALESCE` trong một số trường hợp |

Ví dụ:

```sql
-- Dễ chuyển giữa nhiều hệ:
SELECT COALESCE(discount_amount, 0) AS discount_to_display
FROM order_items;

-- MySQL / MariaDB / SQLite:
SELECT IFNULL(discount_amount, 0) AS discount_to_display
FROM order_items;

-- SQL Server:
SELECT ISNULL(discount_amount, 0) AS discount_to_display
FROM order_items;

-- Oracle:
SELECT NVL(discount_amount, 0) AS discount_to_display
FROM order_items;
```

Khi viết nội dung hoặc ứng dụng dùng đa DBMS, `COALESCE` thường là điểm bắt đầu hợp lý vì thuộc SQL chuẩn. Tuy nhiên, **không khẳng định** các hàm riêng hoàn toàn tương đương về **kiểu trả về, khả năng nhận NULL và cách đánh giá biểu thức**.

## 10. Thực hành đầy đủ với PostgreSQL

Ví dụ sử dụng PostgreSQL để quan sát chính xác `NULL` trong phép tính, hàm và nối chuỗi. Chạy trong **database thực hành**, sử dụng tên bảng riêng `sql_null_lab`. Không dùng những câu lệnh xóa bảng trong một database chứa dữ liệu cần giữ.

### 10.1. Tạo dữ liệu minh họa

```sql
CREATE TABLE sql_null_lab (
    item_id        INTEGER PRIMARY KEY,
    unit_price     NUMERIC(10, 2),
    quantity       INTEGER,
    discount_amount NUMERIC(10, 2),
    note_text      VARCHAR(100)
);

INSERT INTO sql_null_lab
    (item_id, unit_price, quantity, discount_amount, note_text)
VALUES
    (1, 100.00, 2,    10.00, 'giao nhanh'),
    (2,  80.00, NULL,  5.00, NULL),
    (3,  NULL,  3,    NULL,  'hàng tặng'),
    (4,  50.00, 0,     0.00, ''),
    (5,  20.00, 5,    NULL,  NULL);
```

Bảng có năm dòng:

| item_id | unit_price | quantity | discount_amount | note_text |
| ---: | ---: | ---: | ---: | --- |
| 1 | 100 | 2 | 10 | giao nhanh |
| 2 | 80 | `NULL` | 5 | `NULL` |
| 3 | `NULL` | 3 | `NULL` | hàng tặng |
| 4 | 50 | 0 | 0 | chuỗi rỗng |
| 5 | 20 | 5 | `NULL` | `NULL` |

### 10.2. Quan sát phép tính và giá trị dự phòng

```sql
SELECT
    item_id,
    unit_price,
    quantity,
    unit_price * quantity AS gross_amount,
    discount_amount,
    unit_price * quantity
        - COALESCE(discount_amount, 0) AS net_amount
FROM sql_null_lab
ORDER BY item_id;
```

Ở dòng 1, `gross_amount = 200` và `net_amount = 190`. Dòng 2 thiếu quantity và dòng 3 thiếu đơn giá nên hai kết quả tiền đều `NULL`. Dòng 4 có quantity bằng 0 nên kết quả bằng 0, trong khi dòng 5 có tổng trước giảm giá 100 và `COALESCE(discount_amount, 0)` cho tổng sau giảm giá 100.

Trong ví dụ này, **chỉ riêng chiết khấu `NULL` được quy ước bằng 0**. Không quy ước lại số lượng/đơn giá còn thiếu.

### 10.3. Phân biệt thiếu giá trị và số không

```sql
SELECT
    item_id,
    CASE
        WHEN quantity IS NULL THEN 'Chưa biết'
        WHEN quantity = 0 THEN 'Bằng không'
        ELSE 'Đã biết'
    END AS quantity_status,
    discount_amount / NULLIF(quantity, 0) AS discount_per_item
FROM sql_null_lab
ORDER BY item_id;
```

`discount_per_item` của dòng 1 là 5; dòng 2 thiếu quantity, dòng 3 và 5 thiếu discount, dòng 4 có số chia 0 nên đều có `NULL`. Cột `quantity_status` cho biết **vì sao** một số dòng chưa thể tính hoặc thuộc trạng thái riêng.

### 10.4. Nối chuỗi và xử lý ghi chú

```sql
-- PostgreSQL: || lan truyền NULL; CONCAT bỏ qua NULL.
SELECT
    item_id,
    'Ghi chú: ' || note_text AS using_operator,
    CONCAT('Ghi chú: ', note_text) AS using_concat,
    COALESCE(NULLIF(TRIM(note_text), ''), '(không có ghi chú)') AS note_label
FROM sql_null_lab
ORDER BY item_id;
```

Ở dòng 2 và 5, `using_operator` là `NULL` vì `note_text` thiếu, còn `using_concat` chỉ còn phần nhãn `Ghi chú: `. `note_label` hiển thị văn bản dự phòng. Ở dòng 4, `note_text` là chuỗi rỗng, không phải `NULL` trong PostgreSQL; công thức dùng `NULLIF(TRIM(...), '')` để xử lý chuỗi rỗng như “không có ghi chú” **theo quy tắc hiển thị đã chọn**.

### 10.5. Tổng hợp: khác biệt giữa bỏ qua NULL và thay bằng 0

```sql
SELECT
    COUNT(*) AS total_rows,
    COUNT(quantity) AS known_quantity_rows,
    COUNT(note_text) AS non_null_note_rows,
    SUM(quantity) AS total_known_quantity,
    AVG(quantity::numeric) AS avg_known_quantity,
    AVG(COALESCE(quantity, 0)::numeric) AS avg_when_missing_is_zero
FROM sql_null_lab;
```

Với năm dòng mẫu: `COUNT(*) = 5`, `COUNT(quantity) = 4`, `COUNT(note_text) = 3` (chuỗi rỗng vẫn được đếm vì không phải `NULL`), `SUM(quantity) = 10`, `AVG(quantity) = 2.5`, và `AVG(COALESCE(quantity, 0)) = 2.0`.

Dấu `::numeric` là cách ép kiểu của PostgreSQL để biểu diễn phép tính rõ ràng. Nếu cần SQL chuẩn hơn trong hệ khác, thay bằng `CAST(quantity AS DECIMAL(...))` với kiểu thích hợp.

### 10.6. Đếm số dòng chưa đủ dữ liệu để tính tiền

```sql
SELECT
    COUNT(*) AS all_lines,
    COUNT(unit_price * quantity) AS calculable_lines,
    COUNT(*) - COUNT(unit_price * quantity) AS incomplete_lines,
    SUM(unit_price * quantity) AS known_gross_amount
FROM sql_null_lab;
```

Bảng có **5** dòng, **3** dòng tính được tích (1, 4, 5), **2** dòng thiếu dữ liệu (2, 3), tổng tiền trước giảm giá của các dòng tính được là **300**. Đây **chưa phải** tổng chính xác của mọi dòng nếu các dòng thiếu vẫn cần được bổ sung.

### 10.7. Dọn bảng thực hành khi không cần nữa

```sql
-- Chỉ chạy nếu sql_null_lab là bảng thử mà chính bạn vừa tạo:
DROP TABLE sql_null_lab;
```

## 11. NULL trong WHERE, GROUP BY và cách đọc kết quả báo cáo

Một điều kiện số học cũng có thể cho `UNKNOWN`:

```sql
-- PostgreSQL và các DBMS có ngữ nghĩa logic SQL thông dụng:
SELECT *
FROM order_items
WHERE unit_price * quantity > 100;
```

Nếu `unit_price` hoặc `quantity` thiếu thì biểu thức so sánh không cho `TRUE`; dòng đó không được `WHERE` chọn. Điều này **không chứng minh** tích của dòng đó nhỏ hơn hoặc bằng 100.

Nếu nghiệp vụ muốn tìm cả các dòng có tổng tiền chưa biết để xử lý, cần nói rõ:

```sql
SELECT *
FROM order_items
WHERE unit_price * quantity > 100
   OR unit_price IS NULL
   OR quantity IS NULL;
```

`GROUP BY` lại có quy tắc riêng: các giá trị `NULL` thuộc cùng một nhóm khi nhóm theo cột, trong khi `COUNT(column)` trong nhóm đó vẫn không đếm giá trị `NULL` của chính cột. Ví dụ:

```sql
SELECT note_text, COUNT(*) AS rows_in_group
FROM order_items
GROUP BY note_text;
```

Dòng nhóm `note_text = NULL` có thể chứa nhiều dòng nguồn. Điều này không mâu thuẫn với việc `NULL = NULL` cho `UNKNOWN`: SQL định nghĩa việc gom nhóm khác với phép so sánh bằng thông thường trong một điều kiện.

Khi tạo báo cáo, nên hiển thị riêng **số dòng tổng**, **số dòng hợp lệ** và **số dòng thiếu dữ liệu**, để không khiến người đọc hiểu nhầm một tổng đã bỏ qua `NULL` là số liệu hoàn chỉnh.

## 12. Các sai lầm phổ biến khi sử dụng NULL trong biểu thức

| Sai lầm | Vì sao sai hoặc nguy hiểm | Cách tiếp cận phù hợp |
| --- | --- | --- |
| Nghĩ `100 + NULL = 100` | `NULL` không phải 0 | Chỉ dùng `COALESCE(..., 0)` nếu được nghiệp vụ cho phép |
| Nghĩ `0 * NULL = 0` | SQL vẫn trả `NULL` trong phép nhân thông thường | Phân biệt thiếu dữ liệu với số không |
| Dùng `AVG(COALESCE(score, 0))` theo thói quen | Thêm các giá trị 0 vào mẫu thống kê | Dùng `AVG(score)` hoặc ghi rõ quy tắc thiếu = 0 |
| Coi `SUM(x)` của tập rỗng là 0 | Tổng hợp thông thường trả `NULL` | `COALESCE(SUM(x), 0)` nếu báo cáo cần 0 |
| Dùng `COUNT(*)` để đếm dữ liệu đã nhập của một cột | `COUNT(*)` đếm mọi dòng | Dùng `COUNT(column)` |
| Dùng `= NULL` để lọc | So sánh với NULL cho UNKNOWN | `IS NULL` hoặc `IS NOT NULL` |
| Ghép chuỗi bằng `||` rồi mất cả nhãn | Một toán hạng `NULL` làm kết quả `NULL` trong nhiều DBMS | Dùng `COALESCE` hoặc hàm nối chuỗi phù hợp hệ |
| Giả định `CONCAT` của MySQL bỏ qua NULL như PostgreSQL | MySQL `CONCAT` trả `NULL` nếu có đối số NULL | Dùng `CONCAT_WS` hoặc `COALESCE` theo nhu cầu |
| Dùng `COALESCE` thay thế mọi dữ liệu thiếu bằng chuỗi “N/A” trong cột số | Có thể làm lỗi kiểu dữ liệu hoặc phá nghĩa tính toán | Giữ dữ liệu gốc có kiểu đúng; tạo nhãn hiển thị riêng |
| Dùng `NULLIF(x, 0)` rồi không ghi trạng thái | Không phân biệt được mẫu số thiếu với mẫu số bằng 0 | Kết hợp `CASE` và cột trạng thái riêng |
| Cho rằng chuỗi rỗng luôn khác NULL | Oracle có quy tắc đặc thù | Kiểm tra DBMS, phiên bản và kiểu dữ liệu |

## 13. Bài tập tự luyện

**Bài 1 — Giá trị của phép tính.** Hãy xác định kết quả theo SQL thông thường của:

```sql
SELECT 7 + NULL;
SELECT 0 * NULL;
SELECT 15 / NULL;
SELECT COALESCE(NULL, 0) + 5;
SELECT NULLIF(0, 0);
```

Giải thích vì sao ba kết quả đầu không phải những số bình thường.

**Bài 2 — Lấy dữ liệu dự phòng có chủ đích.** Bảng `invoice_lines` có `quantity`, `unit_price` và `discount_amount`, trong đó chỉ `discount_amount = NULL` được quy ước bằng 0. Hãy viết biểu thức tính thành tiền. Khi quantity thiếu, kết quả phải vẫn là `NULL`.

**Bài 3 — Tránh chia cho 0.** Có `total_amount` và `item_count`. Viết biểu thức tính trung bình tiền mỗi món, trả `NULL` khi `item_count` bằng 0 hoặc thiếu. Viết thêm một `CASE` để phân biệt hai lý do.

**Bài 4 — Hàm tổng hợp.** Cho `score` gồm `10, NULL, 20, 0`. Tính `COUNT(*)`, `COUNT(score)`, `SUM(score)`, `AVG(score)` và `AVG(COALESCE(score,0))`. Đâu là trung bình của các điểm đã ghi nhận?

**Bài 5 — Chuỗi NULL.** Với `first_name = 'Lan'`, `last_name = NULL`, dự đoán kết quả của `first_name || ' ' || last_name` trên PostgreSQL. Viết phương án cho phép hiển thị `Lan` mà không thêm khoảng trắng cuối.

**Bài 6 — So sánh DBMS.** Giải thích sự khác biệt giữa `CONCAT('A', NULL, 'B')` trên PostgreSQL và MySQL; nêu hàm nào thường phù hợp để nối các thành phần tên có thể thiếu trong MySQL.

### Gợi ý lời giải

1. Ba kết quả đầu là `NULL`; `COALESCE(NULL,0) + 5` bằng 5; `NULLIF(0,0)` là `NULL`. `NULL` biểu diễn giá trị chưa biết, không phải 0.
2. `unit_price * quantity - COALESCE(discount_amount, 0)`.
3. `CAST(total_amount AS DECIMAL(12,2)) / NULLIF(item_count, 0)` và trạng thái `CASE WHEN item_count IS NULL THEN 'Thiếu' WHEN item_count = 0 THEN 'Bằng 0' ELSE 'Hợp lệ' END`.
4. `COUNT(*) = 4`; `COUNT(score) = 3`; `SUM(score) = 30`; `AVG(score) = 10`; `AVG(COALESCE(score,0)) = 7.5`. `AVG(score)` phản ánh trung bình của các điểm đã biết.
5. Trên PostgreSQL, toán tử `||` trả `NULL`. Dùng `CONCAT_WS(' ', first_name, last_name)` để được `Lan`; với chuỗi rỗng cần xử lý thêm nếu không muốn dấu cách thừa.
6. PostgreSQL `CONCAT` bỏ qua `NULL`, trả `AB`; MySQL `CONCAT` trả `NULL`. Trong MySQL, `CONCAT_WS(' ', first_name, last_name)` có thể bỏ qua thành phần `NULL`.

Điểm cần ghi nhớ khi viết SQL là **NULL giữ lại thông tin “chưa xác định” trong phép tính, nhưng các hàm có quy tắc xử lý khác nhau**. Chỉ thay thế NULL khi nghiệp vụ quy định giá trị dự phòng, kiểm tra riêng quy tắc nối chuỗi của DBMS và luôn cho biết số lượng dữ liệu thiếu khi trình bày kết quả tổng hợp.
