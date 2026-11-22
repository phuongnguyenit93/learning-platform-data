# COUNT(*), COUNT(cột) và COUNT(DISTINCT biểu thức)

Trong **Database SQL**, hàm `COUNT` trả lời câu hỏi “có bao nhiêu?”, nhưng cần xác định rõ **đang đếm dòng, đếm giá trị đã có hay đếm giá trị khác nhau**. Ba cách viết thường gặp:

```sql
COUNT(*)
COUNT(column_name)
COUNT(DISTINCT expression)
```

có thể trả kết quả **khác nhau trên cùng một bảng**, đặc biệt khi cột chứa `NULL`, dữ liệu bị lặp, truy vấn có `JOIN` hoặc `GROUP BY`. Nếu dùng nhầm, báo cáo có thể đếm một đơn hàng nhiều lần, bỏ qua khách hàng chưa có email, hoặc nhầm số lượt đăng ký với số người dùng duy nhất.

Bài học thuộc phần **Tổng hợp dữ liệu**: tập trung vào cơ chế đếm của SQL, cách đặt biểu thức trong `COUNT`, sử dụng cùng `WHERE`/`GROUP BY`/`HAVING`, xử lý `NULL`, đo đếm trên quan hệ nhiều bảng và những khác biệt quan trọng giữa các DBMS.

## 1. Ba kiểu COUNT khác nhau ở điều gì?

Hãy nhớ quy tắc cốt lõi:

| Biểu thức | Đối tượng được đếm | Bỏ qua `NULL`? | Loại giá trị trùng? |
| --- | --- | --- | --- |
| `COUNT(*)` | **Mọi dòng** của tập đầu vào sau lọc | Không loại dòng chỉ vì có cột `NULL` | Không |
| `COUNT(email)` | **Giá trị `email` khác `NULL`** trên các dòng | Có | Không |
| `COUNT(DISTINCT email)` | **Giá trị `email` khác `NULL` và khác nhau** | Có | Có |

Giả sử một truy vấn nhận được sáu dòng:

| Dòng | `email` |
| ---: | --- |
| 1 | `an@example.test` |
| 2 | `binh@example.test` |
| 3 | `an@example.test` |
| 4 | `NULL` |
| 5 | `chi@example.test` |
| 6 | `NULL` |

Ta có:

- `COUNT(*) = 6`: sáu dòng, bất kể nội dung `email`.
- `COUNT(email) = 4`: bốn dòng có email khác `NULL`; email của An xuất hiện hai lần nên vẫn được tính **hai**.
- `COUNT(DISTINCT email) = 3`: ba giá trị email khác nhau là `an@example.test`, `binh@example.test` và `chi@example.test`.

Sơ đồ suy luận:

```text
Tập kết quả:        an, binh, an, NULL, chi, NULL

COUNT(*)            6 dòng

COUNT(email)        an, binh, an, chi
                    4 giá trị không NULL

COUNT(DISTINCT ...) an, binh, chi
                    3 giá trị không NULL, không trùng
```

**Cụm “tập đầu vào” rất quan trọng:** `COUNT` không nhất thiết đếm toàn bảng vật lý. Nếu câu SQL có `WHERE`, `JOIN`, `GROUP BY` hoặc một subquery/CTE, nó đếm **những dòng đang được đưa vào phép tổng hợp tại vị trí đó**.

## 2. COUNT(*) đếm dòng, không cần một cột cụ thể

Cú pháp:

```sql
SELECT COUNT(*) AS total_rows
FROM customers;
```

`COUNT(*)` đếm số dòng `customers` mà câu truy vấn đọc được trong phạm vi ngữ nghĩa SQL và snapshot/giao dịch hiện tại. Một dòng mà **mọi cột cho phép NULL đều là NULL** vẫn được tính là **một dòng**.

Ví dụ:

```sql
SELECT COUNT(*) AS total_orders
FROM orders
WHERE status = 'PAID';
```

Câu này đếm **các dòng đơn hàng có `status = 'PAID'`**, không đếm số đơn hàng có trường email, tổng tiền hoặc ghi chú đã nhập.

### COUNT(*) khác SELECT *

Hai ký hiệu dấu sao xuất hiện ở hai ngữ cảnh khác nhau:

```sql
-- Trả danh sách tất cả các cột của các dòng:
SELECT *
FROM customers;

-- Trả một giá trị là số dòng:
SELECT COUNT(*)
FROM customers;
```

`COUNT(*)` không có nghĩa “đọc mọi giá trị trong mọi cột rồi cộng lại”. Dấu `*` ở đây là cú pháp **đếm dòng** của hàm tổng hợp. Không nên thay bằng một cột bất kỳ nếu cột đó có thể `NULL`.

### COUNT(1) có tương đương COUNT(*) không?

Trong SQL thông dụng, `COUNT(1)` cũng đếm mọi dòng vì literal `1` luôn khác `NULL`:

```sql
SELECT
    COUNT(*) AS row_count,
    COUNT(1) AS count_constant_one
FROM customers;
```

Hai giá trị bằng nhau trong trường hợp này. Trên những DBMS hiện đại, không có quy tắc chung rằng `COUNT(1)` nhanh hơn `COUNT(*)`. Hãy ưu tiên **`COUNT(*)` khi mục đích là đếm dòng**, vì nó thể hiện ý định rõ ràng và dễ đọc.

Ngược lại, `COUNT(NULL)` không đếm dòng nào vì biểu thức luôn trả `NULL`:

```sql
-- PostgreSQL:
SELECT
    COUNT(*) AS all_rows,
    COUNT(NULL::integer) AS no_non_null_values
FROM customers;
```

`::integer` là cú pháp ép kiểu PostgreSQL để biểu thức có kiểu rõ ràng. `COUNT(NULL::integer)` trả 0 dù bảng có nhiều dòng. Trong SQL đa hệ có thể dùng `COUNT(CAST(NULL AS INTEGER))`.

## 3. COUNT(cột) đếm các giá trị đã được cung cấp

Dạng:

```sql
SELECT COUNT(email) AS customers_with_email
FROM customers;
```

trả số dòng có `email IS NOT NULL`. Có thể hiểu gần như:

```sql
SELECT COUNT(*) AS customers_with_email
FROM customers
WHERE email IS NOT NULL;
```

Hai câu trên cho cùng một con số đối với một tập dòng không bị biến đổi khác, nhưng ý nghĩa khi đặt trong truy vấn phức tạp có thể khác nếu chuyển điều kiện lọc ra ngoài làm thay đổi các nhóm hoặc kết quả `JOIN`.

### Chuỗi rỗng, số 0 và FALSE đều khác NULL

Trong PostgreSQL, MySQL, SQLite và SQL Server, các giá trị sau **được tính** bởi `COUNT(column)` nếu chúng thuộc kiểu cột phù hợp:

| Giá trị cột | Có được COUNT(cột) đếm không? | Lý do |
| --- | --- | --- |
| `0` | Có | Số không vẫn là giá trị |
| `''` | Có | Chuỗi rỗng vẫn khác `NULL` ở các DBMS này |
| `' '` | Có | Chuỗi chứa một dấu cách |
| `FALSE` | Có | Giá trị boolean sai không phải `NULL` |
| `'NULL'` | Có | Chuỗi có bốn ký tự |
| `NULL` | Không | Không có giá trị |

**Lưu ý Oracle Database:** Oracle có cách xử lý chuỗi rỗng `''` như `NULL` trong nhiều ngữ cảnh kiểu ký tự. Vì thế, `COUNT(text_column)` trong Oracle có thể không đếm dữ liệu mà ứng dụng ở DBMS khác coi là chuỗi rỗng đã có. Phải xác nhận quy tắc của engine, không sao chép giả định từ PostgreSQL sang Oracle.

### Đếm giá trị có điều kiện “đã nhập thật”

Nếu yêu cầu nghiệp vụ là “email không `NULL`, không rỗng và không chỉ gồm khoảng trắng”, `COUNT(email)` chưa đủ trong các hệ phân biệt chuỗi rỗng với `NULL`. Có thể áp dụng một chính sách chuẩn hóa rõ ràng:

```sql
-- PostgreSQL:
SELECT COUNT(NULLIF(TRIM(email), '')) AS filled_email_count
FROM customers;
```

- `TRIM(email)` bỏ khoảng trắng đầu/cuối theo quy tắc của hàm.
- `NULLIF(..., '')` chuyển chuỗi rỗng sau trim thành `NULL`.
- `COUNT(...)` không đếm các kết quả `NULL`.

Đó là **một định nghĩa riêng của nghiệp vụ về “đã nhập”**, không phải hành vi mặc định của `COUNT(email)`. Với email chứa ký tự Unicode, khoảng trắng đặc biệt hoặc chính sách chuẩn hóa khác, hàm `TRIM` tiêu chuẩn có thể không giải quyết toàn bộ; quy tắc dữ liệu cần được thiết kế ở tầng phù hợp.

## 4. COUNT(DISTINCT biểu thức) đếm giá trị duy nhất

Dạng:

```sql
SELECT COUNT(DISTINCT email) AS unique_email_count
FROM customers;
```

trả số lượng **giá trị kết quả khác `NULL` và khác nhau** của biểu thức `email`.

Điều kiện “khác nhau” chịu ảnh hưởng **kiểu dữ liệu và quy tắc so sánh/collation của DBMS**. Trong một cột chuỗi được so sánh không phân biệt hoa thường, `'Lan'` và `'lan'` có thể được coi là cùng một giá trị khi `DISTINCT`; trong môi trường phân biệt hoa thường, chúng có thể được coi là khác nhau.

### DISTINCT nằm bên trong COUNT, không phải một lệnh riêng

So sánh hai câu:

```sql
SELECT DISTINCT email
FROM customers;

SELECT COUNT(DISTINCT email)
FROM customers;
```

Câu đầu trả **danh sách các giá trị email khác nhau**, thường gồm một dòng `NULL` nếu có ít nhất một email `NULL`. Câu thứ hai trả **một con số**, và **không đếm giá trị `NULL`**.

Vì vậy, số dòng của:

```sql
SELECT DISTINCT email FROM customers;
```

có thể lớn hơn `COUNT(DISTINCT email)` đúng **một** khi có ít nhất một email `NULL`.

Có thể viết:

```sql
-- PostgreSQL:
SELECT
    COUNT(DISTINCT email) AS unique_known_emails,
    COUNT(DISTINCT email)
        + CASE WHEN COUNT(*) > COUNT(email) THEN 1 ELSE 0 END
        AS unique_values_including_one_null_bucket
FROM customers;
```

Cột thứ hai minh họa một phép đếm **bao gồm `NULL` như một nhóm riêng** theo định nghĩa nghiệp vụ, không phải thay đổi ngữ nghĩa của `COUNT(DISTINCT email)`. Tránh dùng cách này khi mục đích chỉ là đếm email hợp lệ.

### DISTINCT trên một biểu thức tính toán

Đối số không nhất thiết là tên cột. Có thể là một biểu thức:

```sql
-- PostgreSQL:
SELECT
    COUNT(DISTINCT LOWER(email)) AS distinct_lowercase_emails,
    COUNT(DISTINCT NULLIF(TRIM(email), '')) AS distinct_nonblank_emails
FROM customers;
```

`LOWER(email)` thay đổi giá trị **trước khi so distinct**. Nhưng `LOWER` không đồng nghĩa loại dấu, Unicode normalization hay chuẩn hóa email chính xác theo mọi nhà cung cấp. Chỉ nên áp dụng khi phù hợp chính sách nghiệp vụ.

`COUNT(DISTINCT expression)` cũng có thể đếm số **tháng khác nhau** có dữ liệu, nếu biểu thức chứa đủ cả năm và tháng thay vì chỉ số tháng:

```sql
-- PostgreSQL:
SELECT COUNT(DISTINCT DATE_TRUNC('month', created_at))
       AS months_with_orders
FROM orders;
```

Cách này đếm các mốc đầu tháng khác nhau của những giá trị `created_at` không `NULL`. Nếu chỉ `COUNT(DISTINCT EXTRACT(MONTH FROM created_at))`, số đếm tối đa thường là 12 và **gộp tháng 4 của nhiều năm** vào cùng một giá trị; đó không phải số tháng lịch khác nhau qua nhiều năm.

## 5. Ví dụ dữ liệu nhỏ để quan sát cả ba loại COUNT

Ví dụ dưới đây dành cho **PostgreSQL**, dùng một bảng học tập riêng. Chọn tên `sql_count_customers` để tránh nhầm với bảng khách hàng nghiệp vụ.

### 5.1. Tạo bảng

```sql
CREATE TABLE sql_count_customers (
    customer_id   INTEGER PRIMARY KEY,
    region        VARCHAR(20),
    email         VARCHAR(100),
    referral_code VARCHAR(20)
);

INSERT INTO sql_count_customers
    (customer_id, region, email, referral_code)
VALUES
    (1, 'Bắc',   'an@example.test',   'REF-A'),
    (2, 'Bắc',   'binh@example.test', NULL),
    (3, 'Nam',   'an@example.test',   'REF-A'),
    (4, 'Nam',   NULL,                'REF-B'),
    (5, 'Nam',   'chi@example.test',  NULL),
    (6, 'Trung', NULL,                'REF-B'),
    (7, 'Trung', 'dung@example.test', 'REF-C'),
    (8, NULL,    'dung@example.test', NULL);
```

Dữ liệu vừa tạo:

| customer_id | region | email | referral_code |
| ---: | --- | --- | --- |
| 1 | Bắc | an@example.test | REF-A |
| 2 | Bắc | binh@example.test | `NULL` |
| 3 | Nam | an@example.test | REF-A |
| 4 | Nam | `NULL` | REF-B |
| 5 | Nam | chi@example.test | `NULL` |
| 6 | Trung | `NULL` | REF-B |
| 7 | Trung | dung@example.test | REF-C |
| 8 | `NULL` | dung@example.test | `NULL` |

Dữ liệu học tập **cố ý cho email trùng** để quan sát `DISTINCT`. Trong ứng dụng thật, email có phải là khóa duy nhất hay không còn tùy chính sách nghiệp vụ; không suy diễn rằng một cột email ở mọi hệ thống đều được phép trùng.

### 5.2. Đếm toàn bảng

```sql
SELECT
    COUNT(*) AS all_customers,
    COUNT(region) AS customers_with_region,
    COUNT(email) AS customers_with_email,
    COUNT(DISTINCT email) AS different_emails,
    COUNT(referral_code) AS customers_with_referral,
    COUNT(DISTINCT referral_code) AS different_referral_codes,
    COUNT(DISTINCT region) AS different_known_regions
FROM sql_count_customers;
```

Kết quả:

| Cột kết quả | Giá trị | Vì sao? |
| --- | ---: | --- |
| `all_customers` | 8 | Có tám dòng |
| `customers_with_region` | 7 | Dòng 8 thiếu region |
| `customers_with_email` | 6 | Dòng 4 và 6 thiếu email |
| `different_emails` | 4 | an, binh, chi, dung |
| `customers_with_referral` | 5 | Dòng 1, 3, 4, 6, 7 có referral |
| `different_referral_codes` | 3 | REF-A, REF-B, REF-C |
| `different_known_regions` | 3 | Bắc, Nam, Trung |

Trên bộ dữ liệu này:

```text
COUNT(*)                = 8
COUNT(email)            = 6
COUNT(DISTINCT email)   = 4
```

Ba số **8, 6, 4** không mâu thuẫn: mỗi số trả lời một câu hỏi khác nhau.

## 6. WHERE áp dụng trước phép tổng hợp

`WHERE` chọn **những dòng đi vào phép đếm**. Ví dụ:

```sql
SELECT COUNT(*) AS customers_in_nam
FROM sql_count_customers
WHERE region = 'Nam';
```

Kết quả là **3** vì khu vực Nam có các dòng 3, 4, 5.

```sql
SELECT
    COUNT(*) AS rows_in_nam,
    COUNT(email) AS filled_emails_in_nam,
    COUNT(DISTINCT email) AS unique_emails_in_nam
FROM sql_count_customers
WHERE region = 'Nam';
```

Kết quả lần lượt **3, 2, 2**.

Điều kiện `WHERE region = 'Nam'` không mang nghĩa “cộng một biến điều kiện vào hàm đếm”; nó **loại các dòng khu vực khác khỏi toàn bộ tập đầu vào của truy vấn**.

### Đếm cột có NULL bằng WHERE

Câu:

```sql
SELECT COUNT(*)
FROM sql_count_customers
WHERE email IS NULL;
```

trả **2**: dòng 4 và 6. Nếu viết:

```sql
SELECT COUNT(email)
FROM sql_count_customers
WHERE email IS NULL;
```

thì kết quả là **0**, vì mọi dòng vượt qua `WHERE` đều có `email = NULL`, còn `COUNT(email)` không đếm giá trị `NULL`.

Để đếm **số giá trị thiếu** mà không lọc bỏ các dòng khác, có thể dùng:

```sql
SELECT
    COUNT(*) - COUNT(email) AS missing_email_rows
FROM sql_count_customers;
```

Công thức này đúng trên tập dòng đã chọn vì mỗi dòng hoặc có `email` khác `NULL` hoặc có `email IS NULL`.

## 7. GROUP BY tạo nhiều nhóm, mỗi nhóm có COUNT riêng

Khi dùng `GROUP BY region`, DBMS chia dữ liệu thành các nhóm theo `region` rồi tính `COUNT` **trên từng nhóm**.

```sql
-- PostgreSQL:
SELECT
    region,
    COUNT(*) AS total_rows,
    COUNT(email) AS emails_present,
    COUNT(DISTINCT email) AS unique_emails
FROM sql_count_customers
GROUP BY region
ORDER BY region NULLS LAST;
```

Kết quả (thứ tự các vùng có thể phụ thuộc collation):

| region | total_rows | emails_present | unique_emails |
| --- | ---: | ---: | ---: |
| Bắc | 2 | 2 | 2 |
| Nam | 3 | 2 | 2 |
| Trung | 2 | 1 | 1 |
| `NULL` | 1 | 1 | 1 |

Ở SQL, các dòng có `region IS NULL` được xếp chung vào **một nhóm `NULL`** của `GROUP BY`; điều này khác với phép so sánh `NULL = NULL` vốn cho trạng thái logic UNKNOWN.

### Một tổng đếm DISTINCT toàn bảng không bằng tổng DISTINCT các nhóm

Từ bảng trên, tổng `unique_emails` ở bốn nhóm là:

```text
2 + 2 + 1 + 1 = 6
```

Trong khi `COUNT(DISTINCT email)` của **toàn bảng** chỉ bằng **4**.

Lý do: một giá trị có thể xuất hiện ở **nhiều nhóm**. `an@example.test` nằm ở Bắc và Nam; `dung@example.test` nằm ở Trung và nhóm region `NULL`. Mỗi nhóm tính unique **trong phạm vi riêng của nó**; cộng các số unique giữa nhóm có thể đếm lại một đối tượng.

Đây là lỗi báo cáo phổ biến khi cộng “số khách hàng khác nhau theo khu vực” để suy ra “số khách hàng khác nhau toàn quốc”. Muốn có số toàn cục, phải `COUNT(DISTINCT ...)` trên **tập toàn cục**, không cộng các unique count nếu các nhóm không loại trừ nhau theo định danh.

### Có thể GROUP BY nhiều cột

```sql
SELECT
    region,
    referral_code,
    COUNT(*) AS row_count
FROM sql_count_customers
GROUP BY region, referral_code
ORDER BY region NULLS LAST, referral_code NULLS LAST;
```

Mỗi nhóm được xác định bằng **tổ hợp** `(region, referral_code)`. `COUNT(*)` trả số dòng trong tổ hợp đó. Đừng nhầm `GROUP BY region, referral_code` với một cú pháp `COUNT(DISTINCT region, referral_code)` — hai thao tác phục vụ mục tiêu khác nhau và khả năng dùng `DISTINCT` nhiều cột phụ thuộc dialect.

## 8. HAVING lọc nhóm sau khi COUNT đã được tính

`WHERE` không thể dùng trực tiếp các hàm tổng hợp của cùng cấp truy vấn để chọn nhóm, vì `WHERE` được áp dụng **trước** bước nhóm/tổng hợp. Khi cần chỉ giữ các nhóm có số dòng hoặc số giá trị đủ lớn, dùng `HAVING`.

```sql
SELECT
    region,
    COUNT(*) AS total_rows
FROM sql_count_customers
GROUP BY region
HAVING COUNT(*) >= 2
ORDER BY region;
```

Kết quả gồm Bắc (2), Nam (3) và Trung (2); nhóm region `NULL` có 1 dòng nên bị loại.

Có thể đặt `COUNT(DISTINCT ...)` trong `HAVING`:

```sql
SELECT
    region,
    COUNT(DISTINCT email) AS unique_emails
FROM sql_count_customers
GROUP BY region
HAVING COUNT(DISTINCT email) >= 2
ORDER BY region;
```

Kết quả gồm Bắc và Nam.

### WHERE và HAVING không hoán đổi tùy ý

```sql
SELECT
    region,
    COUNT(*) AS paid_row_count
FROM transactions
WHERE status = 'PAID'
GROUP BY region
HAVING COUNT(*) >= 10;
```

Câu SQL này:

1. Lọc ra các giao dịch đã thanh toán.
2. Nhóm theo region.
3. Đếm các dòng đã thanh toán trong từng nhóm.
4. Giữ những region có ít nhất 10 giao dịch đã thanh toán.

Nếu bỏ `WHERE`, `COUNT(*)` sẽ đếm cả trạng thái khác. Nếu nhầm `HAVING` với `WHERE`, ý nghĩa báo cáo có thể đổi hoàn toàn.

## 9. COUNT có điều kiện: FILTER và CASE WHEN

Đôi khi cần tính **nhiều số đếm có điều kiện trong cùng một dòng báo cáo** thay vì chạy nhiều truy vấn `WHERE` khác nhau.

### PostgreSQL: cú pháp FILTER

PostgreSQL hỗ trợ `FILTER (WHERE ...)` cho aggregate:

```sql
SELECT
    COUNT(*) AS all_customers,
    COUNT(*) FILTER (WHERE region = 'Nam') AS customers_in_nam,
    COUNT(*) FILTER (WHERE email IS NULL) AS missing_emails,
    COUNT(email) FILTER (WHERE region = 'Nam') AS filled_emails_in_nam,
    COUNT(DISTINCT email) FILTER (WHERE region = 'Nam')
        AS unique_emails_in_nam
FROM sql_count_customers;
```

Kết quả lần lượt là **8, 3, 2, 2, 2**.

`FILTER` chỉ lọc **đầu vào của hàm tổng hợp cụ thể**, chứ không loại các dòng khỏi toàn bộ câu truy vấn như `WHERE`. Do đó có thể đặt nhiều điều kiện trong một `SELECT`.

### Cách phổ biến hơn giữa các DBMS: COUNT(CASE WHEN ...)

Nhiều DBMS hỗ trợ biểu thức `CASE` ở trong `COUNT`:

```sql
SELECT
    COUNT(*) AS all_customers,
    COUNT(CASE WHEN region = 'Nam' THEN 1 END)
        AS customers_in_nam,
    COUNT(CASE WHEN email IS NULL THEN 1 END)
        AS missing_emails,
    COUNT(CASE WHEN region = 'Nam' THEN email END)
        AS filled_emails_in_nam,
    COUNT(DISTINCT CASE WHEN region = 'Nam' THEN email END)
        AS unique_emails_in_nam
FROM sql_count_customers;
```

Cách hoạt động:

- `CASE WHEN condition THEN 1 END` trả `1` nếu đúng, ngược lại trả `NULL` vì không có `ELSE`.
- `COUNT(...)` chỉ đếm giá trị khác `NULL`, nên hành vi tương đương một phép đếm có điều kiện.
- `THEN email` chỉ đếm những email đã có trong nhóm điều kiện; email `NULL` vẫn bị bỏ qua.
- `DISTINCT CASE WHEN ...` chỉ tính số email khác nhau giữa những dòng đáp ứng điều kiện.

**Lỗi rất dễ gặp:**

```sql
-- Sai nếu mục tiêu là chỉ đếm region = 'Nam':
SELECT COUNT(CASE WHEN region = 'Nam' THEN 1 ELSE 0 END)
FROM sql_count_customers;
```

Câu này trả **8**, không phải 3, vì cả `1` lẫn `0` đều khác `NULL`, nên cả tám dòng được đếm.

Nếu dùng `CASE ... ELSE 0`, hãy dùng `SUM`:

```sql
SELECT
    SUM(CASE WHEN region = 'Nam' THEN 1 ELSE 0 END)
        AS customers_in_nam
FROM sql_count_customers;
```

Trên bảng có dòng, kết quả là 3. Nhưng khi **tập đầu vào hoàn toàn rỗng**, `SUM(...)` thường trả `NULL`, trong khi `COUNT(CASE WHEN ... THEN 1 END)` trả **0**. Nếu cần số 0 trong mọi trường hợp, có thể dùng `COALESCE(SUM(...), 0)` theo quy tắc engine.

### Đếm hai trạng thái độc lập trong một truy vấn

```sql
SELECT
    COUNT(*) FILTER (WHERE status = 'PAID') AS paid_count,
    COUNT(*) FILTER (WHERE status = 'CANCELLED') AS cancelled_count,
    COUNT(*) FILTER (WHERE status IS NULL) AS missing_status_count
FROM orders;
```

Đây là cú pháp **PostgreSQL**; ở SQL Server hay MySQL có thể viết các `COUNT(CASE...)` tương ứng. Khi đọc số liệu, nhớ rằng có thể còn các trạng thái khác ngoài hai trạng thái đã chỉ định, nên tổng các count có điều kiện **chưa chắc bằng** `COUNT(*)`.

## 10. COUNT và JOIN: vì sao dễ đếm sai đối tượng?

Khi `JOIN` các bảng có quan hệ **một-nhiều**, một dòng bảng cha có thể xuất hiện nhiều lần trong kết quả. `COUNT(*)` đếm **số dòng kết quả sau JOIN**, không mặc nhiên đếm số đối tượng cha.

Ví dụ: một đơn hàng có thể chứa nhiều dòng hàng.

### 10.1. Tạo dữ liệu thực hành PostgreSQL

```sql
CREATE TABLE sql_count_orders (
    order_id    INTEGER PRIMARY KEY,
    customer_id INTEGER NOT NULL
);

CREATE TABLE sql_count_items (
    item_id   INTEGER PRIMARY KEY,
    order_id  INTEGER NOT NULL
        REFERENCES sql_count_orders(order_id),
    sku       VARCHAR(30) NOT NULL
);

INSERT INTO sql_count_orders (order_id, customer_id)
VALUES
    (101, 1),
    (102, 1),
    (103, 3),
    (104, 5);

INSERT INTO sql_count_items (item_id, order_id, sku)
VALUES
    (1001, 101, 'SKU-A'),
    (1002, 101, 'SKU-B'),
    (1003, 102, 'SKU-A'),
    (1004, 102, 'SKU-C'),
    (1005, 104, 'SKU-C'),
    (1006, 104, 'SKU-D'),
    (1007, 104, 'SKU-D');
```

Có **4 đơn hàng**, **7 dòng hàng** và đơn hàng `103` chưa có dòng hàng.

### 10.2. LEFT JOIN giữ đơn hàng chưa có item

```sql
SELECT
    o.order_id,
    i.item_id,
    i.sku
FROM sql_count_orders AS o
LEFT JOIN sql_count_items AS i
    ON i.order_id = o.order_id
ORDER BY o.order_id, i.item_id;
```

Kết quả có **8 dòng**:

- Đơn 101 xuất hiện 2 dòng (2 item).
- Đơn 102 xuất hiện 2 dòng.
- Đơn 103 xuất hiện **1 dòng** với các cột của `i` là `NULL` do không có item.
- Đơn 104 xuất hiện 3 dòng.

Nếu viết:

```sql
SELECT
    COUNT(*) AS joined_rows,
    COUNT(o.order_id) AS order_ids_after_join,
    COUNT(i.item_id) AS actual_item_rows,
    COUNT(DISTINCT o.order_id) AS distinct_orders,
    COUNT(DISTINCT o.customer_id) AS distinct_customers
FROM sql_count_orders AS o
LEFT JOIN sql_count_items AS i
    ON i.order_id = o.order_id;
```

kết quả là:

| Cột | Kết quả | Ý nghĩa |
| --- | ---: | --- |
| `joined_rows` | 8 | Tất cả các dòng sau LEFT JOIN |
| `order_ids_after_join` | 8 | ID đơn hàng ở phía trái được lặp lại theo item |
| `actual_item_rows` | 7 | Item thật; dòng không có item có `i.item_id = NULL` |
| `distinct_orders` | 4 | Bốn đơn hàng riêng biệt |
| `distinct_customers` | 3 | Ba khách hàng có đơn hàng: 1, 3, 5 |

**Quy tắc dễ nhớ:** sau `LEFT JOIN`, `COUNT(*)` tính cả dòng “không tìm được bản ghi bên phải”; `COUNT(right_table.primary_key)` chỉ đếm những dòng thực sự có bản ghi bên phải nếu khóa chính đó không `NULL`; `COUNT(DISTINCT left_table.id)` đếm số đối tượng phía trái không trùng trong kết quả.

### 10.3. Đếm số item trên từng đơn hàng

```sql
SELECT
    o.order_id,
    COUNT(i.item_id) AS item_count,
    COUNT(DISTINCT i.sku) AS different_sku_count
FROM sql_count_orders AS o
LEFT JOIN sql_count_items AS i
    ON i.order_id = o.order_id
GROUP BY o.order_id
ORDER BY o.order_id;
```

Kết quả:

| order_id | item_count | different_sku_count |
| ---: | ---: | ---: |
| 101 | 2 | 2 |
| 102 | 2 | 2 |
| 103 | 0 | 0 |
| 104 | 3 | 2 |

Ở đơn 104 có hai item cùng `SKU-D`, nên `COUNT(i.item_id) = 3` nhưng `COUNT(DISTINCT i.sku) = 2`.

Nếu viết `COUNT(*)` thay `COUNT(i.item_id)` trong câu `LEFT JOIN`, đơn 103 sẽ cho **1** dù không có item. Đây là một trong những lỗi COUNT phổ biến nhất trong báo cáo cha-con.

### 10.4. INNER JOIN có thể làm mất đối tượng không có con

```sql
SELECT COUNT(DISTINCT o.order_id)
FROM sql_count_orders AS o
JOIN sql_count_items AS i
    ON i.order_id = o.order_id;
```

Kết quả chỉ còn **3** vì INNER JOIN loại đơn 103. Nếu yêu cầu là “bao nhiêu đơn hàng có ít nhất một item?”, số 3 là phù hợp. Nếu yêu cầu là “bao nhiêu đơn hàng tất cả?”, hãy đếm trên bảng `sql_count_orders` hoặc dùng LEFT JOIN phù hợp.

**Sửa việc đếm bằng DISTINCT không luôn đúng mọi mục tiêu.** `COUNT(DISTINCT order_id)` có thể che hiện tượng nhân dòng do JOIN, nhưng nếu yêu cầu là **đếm số item**, số bản ghi sự kiện hoặc tổng số lượng, phải chọn khóa/biểu thức tương ứng, không đặt `DISTINCT` tùy tiện.

### 10.5. JOIN nhiều quan hệ một-nhiều có thể tạo tích nhân

Giả sử mỗi đơn hàng có nhiều dòng hàng và nhiều dòng thanh toán. Nếu JOIN cả hai bảng con trực tiếp, một đơn có 3 items và 2 payments có thể sinh **6 dòng JOIN**. Khi đó:

```sql
-- Minh họa cấu trúc truy vấn, không chạy nếu chưa có bảng payments.
SELECT
    o.order_id,
    COUNT(i.item_id) AS item_rows_after_join,
    COUNT(p.payment_id) AS payment_rows_after_join
FROM orders AS o
LEFT JOIN order_items AS i ON i.order_id = o.order_id
LEFT JOIN payments AS p ON p.order_id = o.order_id
GROUP BY o.order_id;
```

có thể đếm **mỗi item hai lần** và **mỗi payment ba lần**. Nếu các ID duy nhất, `COUNT(DISTINCT i.item_id)` và `COUNT(DISTINCT p.payment_id)` có thể giải quyết **hai số lượng distinct**; tuy nhiên nếu cần `SUM(amount)` hoặc logic nhiều bảng phức tạp, phương án chắc chắn hơn thường là **tổng hợp từng bảng con trước rồi JOIN kết quả**:

```sql
WITH item_counts AS (
    SELECT order_id, COUNT(*) AS item_count
    FROM order_items
    GROUP BY order_id
),
payment_counts AS (
    SELECT order_id, COUNT(*) AS payment_count
    FROM payments
    GROUP BY order_id
)
SELECT
    o.order_id,
    COALESCE(i.item_count, 0) AS item_count,
    COALESCE(p.payment_count, 0) AS payment_count
FROM orders AS o
LEFT JOIN item_counts AS i ON i.order_id = o.order_id
LEFT JOIN payment_counts AS p ON p.order_id = o.order_id;
```

Mỗi CTE tạo **một dòng trên mỗi order_id**, rồi mới nối với bảng cha; tránh tích nhân do JOIN các bảng con trước khi đếm.

## 11. COUNT(DISTINCT) nhiều cột: cú pháp không hoàn toàn di động

Khi cần đếm **số tổ hợp khác nhau của hai cột**, ví dụ cặp `(region, referral_code)`, cần phân biệt **một biểu thức** với **nhiều biểu thức**.

Cú pháp `COUNT(DISTINCT expression)` thường hỗ trợ một biểu thức; các DBMS có thể mở rộng theo cách khác nhau:

| DBMS | Cách thường gặp để đếm tổ hợp nhiều cột |
| --- | --- |
| **PostgreSQL** | `COUNT(DISTINCT (col_a, col_b))` dùng **một biểu thức hàng (row value)**; có ngữ nghĩa `NULL` riêng cần lưu ý |
| **MySQL / MariaDB** | `COUNT(DISTINCT col_a, col_b)` là cú pháp **nhiều biểu thức** đặc thù; tổ hợp có thành phần `NULL` thường không được đếm |
| **SQL Server** | `COUNT(DISTINCT expression)` cho một biểu thức; dùng subquery `SELECT DISTINCT col_a, col_b` để đếm cặp |
| **SQLite** | `COUNT(DISTINCT expression)` cho một biểu thức; dùng subquery `SELECT DISTINCT col_a, col_b` |
| **Oracle Database** | Với nhu cầu đếm nhiều cột theo cú pháp nhất quán, dùng subquery `SELECT DISTINCT col_a, col_b` |

### Cách dễ chuyển giữa các hệ: SELECT DISTINCT trong subquery

Nếu muốn đếm **mọi tổ hợp `(region, referral_code)`, kể cả `NULL` như một giá trị nhóm riêng**, có thể viết:

```sql
SELECT COUNT(*) AS distinct_pairs
FROM (
    SELECT DISTINCT region, referral_code
    FROM sql_count_customers
) AS pairs;
```

Trong dữ liệu mẫu PostgreSQL, các cặp là:

```text
('Bắc',   'REF-A')
('Bắc',    NULL)
('Nam',   'REF-A')
('Nam',   'REF-B')
('Nam',    NULL)
('Trung', 'REF-B')
('Trung', 'REF-C')
(NULL,     NULL)
```

Kết quả `distinct_pairs = 8`. Câu này đếm **số dòng của tập các cặp duy nhất**, bao gồm cả những cặp chứa `NULL` theo quy tắc `DISTINCT` của SQL.

Nếu mục tiêu là **chỉ đếm các cặp đầy đủ hai giá trị**, đặt điều kiện loại `NULL` **trước khi DISTINCT**:

```sql
SELECT COUNT(*) AS distinct_complete_pairs
FROM (
    SELECT DISTINCT region, referral_code
    FROM sql_count_customers
    WHERE region IS NOT NULL
      AND referral_code IS NOT NULL
) AS pairs;
```

Kết quả bằng **5** trên dữ liệu mẫu: `(Bắc, REF-A)`, `(Nam, REF-A)`, `(Nam, REF-B)`, `(Trung, REF-B)`, `(Trung, REF-C)`.

Hai câu truy vấn này đều đúng, nhưng trả lời **hai định nghĩa khác nhau** về “tổ hợp hợp lệ”.

### PostgreSQL row expression và NULL

PostgreSQL cho phép một **biểu thức row** trong `COUNT(DISTINCT ...)`:

```sql
-- PostgreSQL:
SELECT COUNT(DISTINCT (region, referral_code)) AS distinct_pairs
FROM sql_count_customers;
```

Dấu ngoặc `(region, referral_code)` ở đây tạo một **giá trị hàng/composite**, không phải viết hai tham số rời như cú pháp MySQL. Một giá trị row có thành phần `NULL` vẫn có những đặc thù về cách được đánh giá là `NULL` và khi được tổng hợp, nên **không tự coi** `COUNT(DISTINCT (a,b))` tương đương `COUNT(DISTINCT a)` hoặc mặc định loại mọi row có thành phần `NULL`.

Khi học hoặc viết SQL đa hệ, cách rõ nhất là **subquery SELECT DISTINCT** kèm điều kiện `IS NOT NULL` nếu nghiệp vụ cần bộ khóa đầy đủ.

### MySQL/MariaDB có dạng nhiều đối số

```sql
-- MySQL / MariaDB:
SELECT COUNT(DISTINCT region, referral_code) AS complete_pairs
FROM sql_count_customers;
```

Trong MySQL/MariaDB, phép đếm tổ hợp nhiều đối số thường chỉ tính các bộ **không có thành phần `NULL`**. Vì vậy, ví dụ này có ý nghĩa gần với câu subquery **loại NULL ở cả hai cột**, không phải subquery đếm luôn nhóm NULL.

**Không mang nguyên cú pháp `COUNT(DISTINCT a, b)` sang PostgreSQL, SQL Server hay SQLite** rồi coi chúng có cùng ý nghĩa.

### Tránh nối chuỗi hai cột để giả lập bộ khóa

Cách sau không an toàn về ngữ nghĩa:

```sql
-- KHÔNG NÊN dùng để đếm cặp:
SELECT COUNT(DISTINCT col_a || col_b)
FROM some_table;
```

Ví dụ cặp `('ab','c')` và `('a','bc')` đều nối thành `'abc'`, nên bị đếm thành **một** dù là hai cặp khác nhau. Thêm dấu phân cách không giải quyết triệt để nếu dữ liệu có thể chứa chính dấu phân cách, hoặc khi `NULL` và collation làm thay đổi kết quả. Dùng `SELECT DISTINCT col_a, col_b` trong subquery để tôn trọng ranh giới và kiểu của từng cột.

## 12. COUNT(DISTINCT) bị ảnh hưởng bởi kiểu dữ liệu và collation

`DISTINCT` cần quyết định khi nào **hai kết quả biểu thức được coi là bằng nhau**. Một số yếu tố đáng chú ý:

- **Collation:** cách so sánh chuỗi có thể phân biệt hoặc không phân biệt hoa thường, dấu hoặc ký tự tương đương theo ngôn ngữ.
- **Kiểu dữ liệu:** số `1` và chuỗi `'1'` không nhất thiết được coi là cùng giá trị; hãy nhìn kiểu biểu thức sau chuyển đổi.
- **Chuẩn hóa văn bản:** `'Café'` và `'cafe'` có thể được xem giống hoặc khác nhau tùy collation/chính sách xử lý.
- **Biểu thức bên trong `COUNT`:** `LOWER(name)`, `TRIM(name)` hay `CAST(value AS ...)` làm biến đổi giá trị **trước** bước distinct.
- **NULL:** `COUNT(DISTINCT expression)` bỏ qua mọi dòng mà *kết quả biểu thức* là `NULL`.

Ví dụ:

```sql
-- PostgreSQL:
SELECT
    COUNT(DISTINCT email) AS raw_distinct,
    COUNT(DISTINCT LOWER(TRIM(email))) AS normalized_distinct
FROM sql_count_customers;
```

Trên bộ dữ liệu mẫu, các email đều viết thường và không có khoảng trắng thừa, nên hai số bằng nhau. Trên dữ liệu thật, chúng có thể khác nhau.

**Không nên dùng chuẩn hóa làm mất thông tin một cách tự động.** Với mã định danh nghiệp vụ cần phân biệt chữ hoa, `LOWER` có thể gộp các giá trị vốn khác nhau. Với tên người/địa danh có dấu, bỏ dấu hoặc so sánh không phân biệt dấu có thể phù hợp để tìm kiếm nhưng không nhất thiết phù hợp để **đếm số thực thể duy nhất**.

Nếu mục đích là đếm **người dùng duy nhất**, tốt nhất nên dùng **khóa định danh người dùng** có ngữ nghĩa đã xác định (ví dụ `user_id`) thay vì các trường có thể trùng hoặc thay đổi như tên hiển thị và email.

## 13. Tập rỗng, GROUP BY và kiểu kết quả COUNT

### Không có dòng nào khớp WHERE

```sql
SELECT
    COUNT(*) AS total,
    COUNT(email) AS known_email,
    COUNT(DISTINCT email) AS different_emails
FROM sql_count_customers
WHERE customer_id < 0;
```

Vì không có dòng nào có `customer_id < 0`, câu truy vấn tổng hợp **không có `GROUP BY`** trả **một dòng** với ba giá trị đều bằng **0**.

Đây là đặc điểm của `COUNT`. Trong khi đó các hàm như `SUM`, `AVG`, `MIN`, `MAX` trên tập rỗng thường trả `NULL`, không phải 0.

```sql
-- PostgreSQL:
SELECT
    COUNT(*) AS row_count,
    SUM(customer_id) AS sum_of_ids
FROM sql_count_customers
WHERE customer_id < 0;
```

Kết quả: `row_count = 0`, `sum_of_ids = NULL`.

### GROUP BY trên tập rỗng

```sql
SELECT region, COUNT(*) AS total
FROM sql_count_customers
WHERE customer_id < 0
GROUP BY region;
```

Câu này trả **0 dòng**, không phải một dòng có `region = NULL` và `total = 0`. Không có nhóm nào được tạo ra từ dữ liệu đã bị `WHERE` loại hết.

Phân biệt **một nhóm có dòng nhưng mọi email đều NULL** với **không có nhóm nào**:

- Có nhóm với 5 dòng, email đều `NULL`: `COUNT(*) = 5`, `COUNT(email) = 0`.
- Không có dòng nào thuộc nhóm: khi `GROUP BY` trực tiếp trên dữ liệu đó, nhóm thường **không xuất hiện**.

Khi muốn hiển thị cả những danh mục không có dữ liệu, hãy sử dụng bảng danh mục phía trái và `LEFT JOIN`, rồi đếm **khóa của dữ liệu phía phải**, không đếm `*`.

### Kiểu số trả về và giới hạn

`COUNT` trả số nguyên, nhưng **kiểu trả về** có khác biệt:

- **PostgreSQL:** `COUNT(*)` và `COUNT(expression)` trả `bigint`.
- **SQL Server:** `COUNT` có kiểu `int`, có giới hạn khoảng 2,1 tỷ; `COUNT_BIG` trả `bigint` khi cần số đếm lớn. Hành vi tràn `COUNT` có thể phụ thuộc thiết lập phiên.
- **MySQL/MariaDB:** `COUNT` trả kiểu số nguyên dung lượng lớn theo engine.
- **SQLite:** `COUNT` trả số nguyên, giới hạn theo cách biểu diễn integer của SQLite.
- **Oracle:** kết quả `COUNT` có kiểu số theo quy tắc Oracle (ví dụ `NUMBER`).

Khi đưa kết quả COUNT sang Java/JDBC hoặc API, nên dùng kiểu số đủ rộng như `long`/`Long` khi dữ liệu có khả năng lớn, nhất là nếu DBMS trả `bigint`.

## 14. COUNT(*) không luôn có độ phức tạp hằng số

Một câu `SELECT COUNT(*) FROM large_table` trông đơn giản, nhưng trên nhiều DBMS không có một con số “số dòng chính xác đang nhìn thấy” luôn sẵn để trả về ngay.

### Vì sao cần đọc dữ liệu hoặc chỉ mục?

Trong các DBMS có **MVCC (multiversion concurrency control)** như PostgreSQL, các transaction có thể nhìn thấy các snapshot khác nhau. Một dòng vừa được chèn hoặc xóa có thể **hiển thị với transaction này nhưng chưa hiển thị với transaction khác**. Vì thế, đếm chính xác số dòng theo snapshot thường phải kiểm tra số lượng dòng **được nhìn thấy** trong phạm vi truy vấn.

`COUNT(*)` có thể được tối ưu bằng index, index-only scan hoặc thống kê tùy engine và điều kiện, nhưng không nên coi nó luôn trả ngay từ metadata như `SELECT 42`.

### COUNT(DISTINCT) thường có chi phí bổ sung

`COUNT(DISTINCT email)` phải xác định các giá trị khác nhau. Engine có thể dùng:

- **Hash aggregate** để lưu các giá trị đã thấy.
- **Sort/unique aggregate** để sắp xếp hoặc loại trùng.
- Chỉ mục phù hợp với biểu thức và bộ lọc, nếu tối ưu được.
- Bộ nhớ tạm hoặc không gian trên đĩa khi tập distinct rất lớn.

Kế hoạch cụ thể tùy DBMS, thống kê, phân bố dữ liệu, số giá trị khác nhau và cách thực hiện truy vấn. Không khẳng định `COUNT(DISTINCT col)` luôn chậm hoặc luôn nhanh hơn `COUNT(*)` — hai phép đếm làm việc khác nhau, chi phí phụ thuộc ngữ cảnh.

### EXPLAIN trong PostgreSQL

```sql
EXPLAIN
SELECT COUNT(*)
FROM sql_count_customers;

EXPLAIN
SELECT COUNT(DISTINCT email)
FROM sql_count_customers;

EXPLAIN
SELECT region, COUNT(*)
FROM sql_count_customers
GROUP BY region;
```

Bảng học tập có tám dòng nên kế hoạch có thể chọn quét tuần tự, điều này bình thường. Trong bảng lớn, quan sát `EXPLAIN (ANALYZE, BUFFERS)` trên **các truy vấn SELECT** trong môi trường phù hợp để hiểu thời gian và số trang bộ nhớ được truy cập; `ANALYZE` sẽ **thực thi câu truy vấn**.

Đếm chính xác có thể chậm nếu có `JOIN` lớn, `WHERE` phức tạp hoặc `DISTINCT` trên biểu thức không được index hỗ trợ. Khi chỉ cần biết **có tồn tại ít nhất một dòng hay không**, `EXISTS` thường biểu đạt đúng ý hơn so với tính cả `COUNT(*)`:

```sql
-- PostgreSQL:
SELECT EXISTS (
    SELECT 1
    FROM sql_count_customers
    WHERE email = 'an@example.test'
) AS email_exists;
```

`EXISTS` chỉ cần xác định có ít nhất một dòng phù hợp; nhiều engine có thể dừng sớm. Nếu mục tiêu là **đếm đầy đủ**, vẫn dùng `COUNT`.

## 15. COUNT trong cửa sổ (window function): khi muốn giữ dòng chi tiết

`COUNT` cũng có thể xuất hiện với `OVER (...)` để trả số đếm **trên từng dòng chi tiết**, thay vì gom thành một dòng tổng hợp.

```sql
-- PostgreSQL:
SELECT
    customer_id,
    region,
    email,
    COUNT(*) OVER () AS total_rows_in_result,
    COUNT(*) OVER (PARTITION BY region) AS rows_in_region,
    COUNT(email) OVER (PARTITION BY region) AS filled_emails_in_region
FROM sql_count_customers
ORDER BY customer_id;
```

Ở ví dụ này:

- Vẫn có **tám dòng kết quả**, mỗi dòng ứng với một khách hàng.
- `COUNT(*) OVER ()` hiển thị giá trị 8 trên mỗi dòng (khi không có `WHERE`).
- `COUNT(*) OVER (PARTITION BY region)` hiển thị 2, 3, 2 hoặc 1 theo khu vực.
- `COUNT(email) OVER (PARTITION BY region)` đếm những email không `NULL` trong từng phân vùng.

**Không đồng nhất window COUNT với GROUP BY:** `GROUP BY` thường giảm nhiều dòng thành một dòng mỗi nhóm; `OVER` giữ các dòng chi tiết và bổ sung phép tính cửa sổ.

Cú pháp `COUNT(DISTINCT email) OVER (...)` **không được hỗ trợ giống nhau trên mọi DBMS** (ví dụ PostgreSQL không hỗ trợ `DISTINCT` trong aggregate dùng làm window function theo cú pháp trực tiếp này). Muốn thêm số email duy nhất theo vùng vào từng dòng, thường có thể tổng hợp ở subquery/CTE rồi `JOIN` lại.

### COUNT(*) OVER() kết hợp LIMIT/OFFSET

Một mẫu hay gặp là:

```sql
-- PostgreSQL:
SELECT
    customer_id,
    email,
    COUNT(*) OVER () AS total_filtered_rows
FROM sql_count_customers
WHERE region = 'Nam'
ORDER BY customer_id
LIMIT 2 OFFSET 0;
```

Có thể trả hai dòng đầu khu vực Nam, nhưng `total_filtered_rows` ở mỗi dòng là **3**, không phải 2: hàm cửa sổ tính trên tập sau `WHERE` và trước khi `LIMIT/OFFSET` cắt trang ở lớp truy vấn này.

Tuy nhiên, nếu `OFFSET` vượt quá cuối tập và trang trả **0 dòng**, sẽ không có dòng nào để mang theo `total_filtered_rows`. Nếu API luôn cần tổng dù trang rỗng, có thể cần truy vấn COUNT riêng hoặc chiến lược khác.

Ngoài ra, tính tổng qua window có thể khiến DBMS phải xử lý nhiều dòng hơn so với một truy vấn chỉ lấy trang đầu; xem execution plan trên dữ liệu lớn.

## 16. Khác biệt cú pháp theo hệ quản trị

Phần lớn các DBMS hỗ trợ ba dạng cơ bản:

```sql
COUNT(*)
COUNT(column_name)
COUNT(DISTINCT expression)
```

Nhưng cú pháp mở rộng và quy tắc giá trị cần chú ý:

| DBMS | Điểm cần nhớ |
| --- | --- |
| **PostgreSQL** | `COUNT` trả `bigint`; có `FILTER (WHERE ...)`, aggregate `OVER` và biểu thức row `COUNT(DISTINCT (a,b))`; `DISTINCT` trong window COUNT không hỗ trợ trực tiếp |
| **MySQL/MariaDB** | Hỗ trợ `COUNT(DISTINCT a,b)` để đếm tổ hợp nhiều biểu thức không `NULL`; quy tắc so sánh chuỗi phụ thuộc collation |
| **SQL Server** | Có `COUNT_BIG` khi số dòng rất lớn; `COUNT(DISTINCT expression)` cho một biểu thức; đếm nhiều cột thường dùng subquery `SELECT DISTINCT` |
| **SQLite** | `COUNT(*)` và `COUNT(x)`; `COUNT(DISTINCT x)` cho một biểu thức; muốn đếm cặp dùng subquery |
| **Oracle Database** | Có `COUNT(*)`/`COUNT(expr)`/`COUNT(DISTINCT expr)`; chuỗi rỗng thường được xem là `NULL`, ảnh hưởng COUNT trên cột text |

### SQL Server: COUNT_BIG

```sql
-- SQL Server:
SELECT
    COUNT(*) AS row_count_int,
    COUNT_BIG(*) AS row_count_bigint
FROM dbo.customers;
```

Khi hệ thống có khả năng nhiều hơn giới hạn `int`, `COUNT_BIG` biểu thị chủ đích dùng kiểu trả về lớn hơn.

### MySQL/MariaDB: nhiều biểu thức với DISTINCT

```sql
-- MySQL / MariaDB:
SELECT COUNT(DISTINCT region, referral_code) AS complete_unique_pairs
FROM sql_count_customers;
```

Không giả định câu này đếm nhóm có giá trị `NULL` như một cặp hợp lệ; nó mang ngữ nghĩa của dạng multi-expression do engine cung cấp. SQL Server và SQLite không nhận cú pháp này như cách đếm bộ hai cột.

### SQLite: subquery cho nhiều cột

```sql
-- SQLite:
SELECT COUNT(*) AS distinct_pairs
FROM (
    SELECT DISTINCT region, referral_code
    FROM sql_count_customers
) AS pairs;
```

Cách này thể hiện rõ ranh giới của từng cột. Nếu không muốn tính các cặp có `NULL`, thêm điều kiện `WHERE region IS NOT NULL AND referral_code IS NOT NULL` bên trong subquery.

### Oracle: NULL và chuỗi rỗng

```sql
-- Oracle (cần FROM DUAL trong nhiều phiên bản):
SELECT COUNT(*) AS total_rows
FROM some_table;
```

Trong Oracle, các cột `VARCHAR2` chứa chuỗi rỗng thường được xử lý như `NULL`. Vì vậy, một hệ thống di chuyển dữ liệu từ PostgreSQL/SQL Server có nhiều `''` sang Oracle có thể thấy `COUNT(text_column)` khác đi. Không đổi công thức COUNT để “sửa” số liệu trước khi hiểu chính xác dữ liệu và quy tắc engine.

## 17. Thiết kế báo cáo COUNT theo đúng câu hỏi nghiệp vụ

Một yêu cầu “bao nhiêu khách hàng?” có thể có nhiều cách hiểu:

| Câu hỏi nghiệp vụ | Gợi ý biểu thức | Điều cần xác định |
| --- | --- | --- |
| Có bao nhiêu bản ghi khách hàng? | `COUNT(*)` từ bảng khách hàng | Một dòng có thực sự tương ứng một khách hàng không? |
| Có bao nhiêu bản ghi đã nhập email? | `COUNT(email)` | Chuỗi rỗng hoặc khoảng trắng có được coi “đã nhập” không? |
| Có bao nhiêu email khác nhau? | `COUNT(DISTINCT email)` | So sánh hoa/thường, chuẩn hóa và collation thế nào? |
| Có bao nhiêu khách hàng **duy nhất** mua hàng? | `COUNT(DISTINCT customer_id)` từ đơn hàng | `customer_id` có đại diện đúng một khách hàng không? |
| Có bao nhiêu đơn hàng có item? | `COUNT(DISTINCT o.order_id)` sau INNER JOIN item, hoặc `EXISTS` | Muốn đơn có ít nhất một item hay tổng số item? |
| Có bao nhiêu item trong một đơn hàng, kể cả đơn rỗng? | `COUNT(i.item_id)` trên LEFT JOIN rồi `GROUP BY order_id` | Khóa item có `NOT NULL` không? |
| Có bao nhiêu trạng thái chưa được nhập? | `COUNT(*) - COUNT(status)` hoặc `COUNT(CASE WHEN status IS NULL THEN 1 END)` | Có cần coi chuỗi rỗng là thiếu không? |
| Có bao nhiêu cặp tenant–mã dự án khác nhau? | Subquery `SELECT DISTINCT tenant_id, project_code` rồi `COUNT(*)` | Có tính bộ có thành phần `NULL` không? |

Nếu cột đếm thuộc bảng con của một `LEFT JOIN`, chọn `COUNT(child.primary_key)` khi muốn **đếm bản ghi con thực sự tồn tại**, không dùng `COUNT(*)` theo phản xạ.

Nếu đang đếm “thực thể duy nhất”, hãy dùng **khóa định danh đúng nghiệp vụ**. `DISTINCT` là cơ chế loại trùng giá trị, không phải công cụ tự biết hai dòng nào đại diện cùng một người, một sản phẩm hay một giao dịch.

## 18. Bài thực hành tự luyện trên PostgreSQL

Các bài dưới đây dùng hai bộ bảng `sql_count_customers` và `sql_count_orders`/`sql_count_items` ở mục 5 và 10. Nếu đã xóa bảng, hãy tạo lại trước khi thực hành.

### Bài 1 — Phân biệt ba kiểu đếm

Trên `sql_count_customers`, dự đoán kết quả:

```sql
SELECT
    COUNT(*) AS a,
    COUNT(email) AS b,
    COUNT(DISTINCT email) AS c
FROM sql_count_customers;
```

Giải thích ba con số bằng danh sách dòng và giá trị đã cung cấp.

### Bài 2 — Đếm những người chưa có email

Viết **hai cách** đếm khách hàng có `email IS NULL`: một cách dùng `WHERE`, một cách chỉ dùng hai hàm `COUNT` trên toàn bộ bảng.

### Bài 3 — Đếm theo vùng

Viết truy vấn trả `region`, số dòng, số email khác `NULL` và số email khác nhau. Giải thích vì sao cộng số email distinct theo vùng có thể lớn hơn số email distinct toàn bảng.

### Bài 4 — Chọn đúng COUNT sau LEFT JOIN

Dùng `sql_count_orders` và `sql_count_items`, hãy dự đoán:

```sql
SELECT
    COUNT(*) AS a,
    COUNT(o.order_id) AS b,
    COUNT(i.item_id) AS c,
    COUNT(DISTINCT o.order_id) AS d
FROM sql_count_orders AS o
LEFT JOIN sql_count_items AS i
    ON i.order_id = o.order_id;
```

Vì sao cả `a` lẫn `b` đều không đại diện cho **số đơn hàng riêng biệt** trong ví dụ này?

### Bài 5 — Đơn không có item

Viết câu SQL tìm các đơn có **0 dòng hàng**, không làm mất đơn hàng vì INNER JOIN. Có thể dùng `LEFT JOIN + GROUP BY + HAVING COUNT(i.item_id) = 0` hoặc `NOT EXISTS`.

### Bài 6 — COUNT(DISTINCT) nhiều cột

Đếm hai kiểu tổ hợp trên `sql_count_customers`:

1. Tổng số cặp `(region, referral_code)` khác nhau, **tính cả cặp có NULL**.
2. Số cặp **đầy đủ cả hai giá trị** khác nhau.

Viết SQL di động bằng subquery và chỉ rõ lý do hai số khác nhau.

### Bài 7 — COUNT có điều kiện

Viết truy vấn trả cùng lúc số khách hàng vùng Nam, số khách hàng có email `NULL` và số email unique ở vùng Nam. Thử hai cách `FILTER` (PostgreSQL) và `COUNT(CASE WHEN ...)`. Điều gì xảy ra nếu thêm `ELSE 0` vào `COUNT(CASE ...)`?

### Bài 8 — Đếm ngày hoạt động

Bảng `events` có `occurred_at TIMESTAMP` có thể `NULL`. Yêu cầu là **số ngày lịch khác nhau** có sự kiện, theo ngày giờ đã lưu trong cột. Viết truy vấn PostgreSQL và giải thích vì sao `COUNT(DISTINCT EXTRACT(DAY FROM occurred_at))` không đúng khi dữ liệu trải qua nhiều tháng.

### Bài 9 — Đánh giá COUNT và hiệu năng

Một dashboard có hai chỉ số: “có ít nhất một giao dịch lỗi?” và “có chính xác bao nhiêu giao dịch lỗi?”. Chọn `EXISTS` hay `COUNT(*)` cho từng câu hỏi và giải thích. Nếu bảng lớn, kế hoạch truy vấn có thể khác thế nào?

### Gợi ý đáp án

**Bài 1:** `a=8`, `b=6`, `c=4`. `COUNT(*)` đếm dòng; `COUNT(email)` không đếm hai dòng `NULL`; `COUNT(DISTINCT email)` loại thêm hai lần lặp của các email đã biết.

**Bài 2:**

```sql
SELECT COUNT(*) AS missing_emails
FROM sql_count_customers
WHERE email IS NULL;

SELECT COUNT(*) - COUNT(email) AS missing_emails
FROM sql_count_customers;
```

Cả hai trả **2**.

**Bài 3:**

```sql
SELECT
    region,
    COUNT(*) AS rows_in_region,
    COUNT(email) AS emails_present,
    COUNT(DISTINCT email) AS unique_emails
FROM sql_count_customers
GROUP BY region;
```

Một email có thể xuất hiện trong nhiều vùng; mỗi vùng tính riêng, nhưng toàn bảng chỉ tính giá trị đó một lần.

**Bài 4:** `a=8`, `b=8`, `c=7`, `d=4`. Sau LEFT JOIN, các đơn có nhiều item sinh nhiều dòng, còn đơn không có item vẫn sinh một dòng với phần `i` là `NULL`.

**Bài 5:**

```sql
SELECT o.order_id
FROM sql_count_orders AS o
LEFT JOIN sql_count_items AS i
    ON i.order_id = o.order_id
GROUP BY o.order_id
HAVING COUNT(i.item_id) = 0;
```

Kết quả **order_id = 103**.

**Bài 6:**

```sql
-- Tính cả các cặp có thành phần NULL:
SELECT COUNT(*)
FROM (
    SELECT DISTINCT region, referral_code
    FROM sql_count_customers
) AS pairs;

-- Chỉ tính cặp đủ cả hai giá trị:
SELECT COUNT(*)
FROM (
    SELECT DISTINCT region, referral_code
    FROM sql_count_customers
    WHERE region IS NOT NULL AND referral_code IS NOT NULL
) AS pairs;
```

Hai kết quả lần lượt **8** và **5**.

**Bài 7:** Cách PostgreSQL:

```sql
SELECT
    COUNT(*) FILTER (WHERE region = 'Nam') AS nam_rows,
    COUNT(*) FILTER (WHERE email IS NULL) AS missing_emails,
    COUNT(DISTINCT email) FILTER (WHERE region = 'Nam') AS nam_unique_emails
FROM sql_count_customers;
```

Kết quả **3, 2, 2**. Nếu `COUNT(CASE WHEN ... THEN 1 END)` được đổi thành `COUNT(CASE WHEN ... THEN 1 ELSE 0 END)`, cả dòng không thỏa điều kiện cũng trả giá trị khác `NULL` và bị đếm.

**Bài 8:**

```sql
-- PostgreSQL: đếm ngày lịch được biểu diễn trong TIMESTAMP.
SELECT COUNT(DISTINCT occurred_at::date) AS days_with_events
FROM events;
```

`EXTRACT(DAY FROM occurred_at)` chỉ trả số ngày trong tháng như `1` đến `31`, nên sẽ gộp ngày 5 của nhiều tháng.

**Bài 9:** Dùng `EXISTS` cho câu hỏi có tồn tại giao dịch lỗi, `COUNT(*)` cho yêu cầu số lượng chính xác. `EXISTS` có thể dừng khi tìm được dòng phù hợp; `COUNT(*)` phải bảo đảm kết quả đếm đúng các dòng mà truy vấn nhìn thấy.

### Dọn dữ liệu thực hành

Chỉ chạy khi đã học xong và chắc chắn các bảng đều do **chính bạn tạo** trong database thử:

```sql
DROP TABLE sql_count_items;
DROP TABLE sql_count_orders;
DROP TABLE sql_count_customers;
```

Xóa bảng item trước bảng order vì item có khóa ngoại tham chiếu order. Không dùng câu lệnh `DROP` trên database thật hoặc bảng dùng chung.

## 19. Tổng kết: chọn COUNT theo câu hỏi cần trả lời

Trước khi viết một phép đếm, hãy tự xác định:

1. **Đơn vị cần đếm là gì?** Dòng SQL, email đã nhập, người dùng duy nhất, đơn hàng hay item?
2. **`NULL` có ý nghĩa gì?** Một giá trị thiếu có được tính không, và chuỗi rỗng có được xem là thiếu không?
3. **Giá trị trùng có phải cùng đối tượng không?** Nếu cần “duy nhất”, chọn biểu thức/khóa định danh đúng nghiệp vụ.
4. **Tập đầu vào được tạo thế nào?** `WHERE`, `GROUP BY` và `JOIN` có đang làm tăng/giảm số dòng không?
5. **Phạm vi đếm là toàn cục hay từng nhóm?** Không cộng các `COUNT(DISTINCT ...)` của nhiều nhóm nếu một đối tượng có thể xuất hiện ở nhiều nhóm.
6. **Có cần tính nhiều điều kiện trong một truy vấn không?** Sử dụng `FILTER` ở DBMS hỗ trợ hoặc `COUNT(CASE WHEN ... THEN ... END)`.
7. **Dữ liệu lớn hay có thay đổi đồng thời không?** Xem chi phí truy vấn và snapshot, đừng coi COUNT luôn miễn phí hay bất biến theo thời gian.

**Quy tắc nhớ nhanh:** `COUNT(*)` đếm **dòng**; `COUNT(cột)` đếm **giá trị khác `NULL`**; `COUNT(DISTINCT biểu thức)` đếm **giá trị khác `NULL` và không trùng**. Khi kết quả bất ngờ, trước tiên hãy kiểm tra tập dòng **sau JOIN/WHERE**, chính sách `NULL` và cách xác định một giá trị là “giống nhau”.
