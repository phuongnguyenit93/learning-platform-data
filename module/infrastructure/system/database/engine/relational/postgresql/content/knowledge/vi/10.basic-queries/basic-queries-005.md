# IN, BETWEEN, LIKE, ILIKE và điều kiện kết hợp trong PostgreSQL

Khi truy vấn một bảng, chúng ta hiếm khi muốn lấy mọi hàng. Một trang bán hàng có thể cần tìm sản phẩm thuộc **một trong nhiều danh mục**, có giá **trong khoảng ngân sách**, tên **chứa từ khóa**, vẫn **đang bán** và có **tồn kho**. PostgreSQL cung cấp những toán tử và biểu thức để diễn đạt các điều kiện lọc đó ngay trong SQL.

Bốn nhóm quan trọng của bài học là:

- `IN` và `NOT IN`: kiểm tra một giá trị có thuộc một tập giá trị hay không.
- `BETWEEN` và `NOT BETWEEN`: kiểm tra một giá trị có nằm trong khoảng giới hạn hay không.
- `LIKE`, `NOT LIKE`: tìm chuỗi theo mẫu, thường có phân biệt chữ hoa và chữ thường.
- `ILIKE`, `NOT ILIKE`: tìm chuỗi theo mẫu **không phân biệt hoa/thường** theo quy tắc xử lý ngôn ngữ/collation của PostgreSQL.

Các điều kiện được ghép bằng `AND`, `OR` và `NOT`, cùng dấu ngoặc để xác định logic ưu tiên.

Điều cần hiểu không chỉ là cú pháp. Một câu `WHERE` đúng cấu trúc vẫn có thể trả kết quả sai nếu bỏ qua cách SQL xử lý `NULL`, chọn sai ranh giới thời gian, nhầm ký tự đại diện trong `LIKE`, hoặc ghép `AND` và `OR` mà không dùng ngoặc.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Dùng `WHERE column IN (...)` để lọc theo nhiều giá trị và hiểu mối quan hệ với các phép so sánh `=`.
2. Sử dụng `BETWEEN` đúng với hai đầu mút **được bao gồm**, cũng như thiết kế khoảng thời gian **nửa mở** cho `TIMESTAMP/TIMESTAMPTZ`.
3. Dùng `LIKE` với `%`, `_` và `ESCAPE`; phân biệt tìm theo tiền tố, hậu tố và chuỗi con.
4. Dùng `ILIKE` để tìm gần đúng theo hoa/thường trong PostgreSQL, đồng thời không đánh đồng nó với tìm không dấu.
5. Viết điều kiện hỗn hợp bằng `AND`, `OR`, `NOT` và dấu ngoặc.
6. Hiểu logic ba giá trị `TRUE`, `FALSE`, `NULL` trong `WHERE`; tránh bẫy `NOT IN` có `NULL`.
7. Tạo truy vấn có tham số an toàn cho danh sách và chuỗi tìm kiếm do người dùng nhập.
8. Nhận diện tác động của mẫu tìm kiếm và chỉ mục đối với hiệu năng; dùng `EXPLAIN` để xem kế hoạch.
9. Thực hành trên một bảng PostgreSQL có dữ liệu cố định, để dễ so sánh kết quả.

Các lệnh tạo/xóa dữ liệu chỉ dành cho **database thử nghiệm riêng**. Không chạy nguyên khối tạo lại bảng trên môi trường đang chứa dữ liệu thật.

---

## 2. Vị trí của điều kiện lọc trong câu SELECT

Cấu trúc quen thuộc:

```sql
SELECT
    column_1,
    column_2
FROM schema_name.table_name
WHERE condition
ORDER BY column_1;
```

Trong đó:

- `FROM` chọn nguồn dữ liệu.
- `WHERE` giữ lại những hàng mà điều kiện đánh giá thành **TRUE**.
- `ORDER BY` sắp xếp tập kết quả cuối cùng theo yêu cầu.
- `LIMIT`, nếu có, giới hạn số hàng được trả về theo thứ tự xử lý phù hợp.

Ví dụ khái niệm:

```sql
SELECT sku, product_name, price
FROM query_filter_lab.products
WHERE status = 'ACTIVE'
ORDER BY price DESC;
```

Kết quả chỉ gồm các sản phẩm có trạng thái ACTIVE, sau đó được sắp xếp theo giá giảm dần.

**Không nên suy ra thứ tự kết quả khi không có `ORDER BY`.** PostgreSQL không hứa hẹn các hàng sẽ tự xuất hiện theo ID, thứ tự chèn hay thứ tự trên đĩa.

### 2.1. WHERE không giữ kết quả UNKNOWN

SQL sử dụng **logic ba giá trị**: `TRUE`, `FALSE` và `UNKNOWN` (thường được biểu diễn bằng `NULL` khi quan sát kết quả). Trong `WHERE`, **chỉ hàng có điều kiện TRUE mới được giữ**. Hàng có `FALSE` hoặc `NULL` đều bị loại.

Ví dụ:

```sql
SELECT
    5 > 3 AS condition_true,
    5 > 8 AS condition_false,
    NULL::INTEGER > 0 AS condition_unknown;
```

`NULL > 0` không phải `FALSE`, mà là `NULL`: PostgreSQL không có đủ thông tin để kết luận.

Điểm này ảnh hưởng đến `IN`, `BETWEEN`, `LIKE` và mọi điều kiện kết hợp. Các mục tiếp theo sẽ sử dụng ví dụ cụ thể.

---

## 3. Chuẩn bị dữ liệu thực hành

Tạo một bảng sản phẩm để minh họa mọi nhóm điều kiện. Dữ liệu dùng ngày giờ cố định, có nhiều category, tên sản phẩm với chữ hoa/thường khác nhau và một số cột có `NULL`.

> **Chỉ chạy trong database thực hành.** Lệnh `DROP TABLE` bên dưới xóa bảng `query_filter_lab.products` và mọi dữ liệu cũ của bảng đó, nếu đã tồn tại.

```sql
CREATE SCHEMA IF NOT EXISTS query_filter_lab;

DROP TABLE IF EXISTS query_filter_lab.products;

CREATE TABLE query_filter_lab.products (
    product_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    sku TEXT NOT NULL UNIQUE,
    product_name TEXT NOT NULL,
    category TEXT NOT NULL,
    price NUMERIC(12,2) NOT NULL
        CHECK (price >= 0),
    status TEXT NOT NULL
        CHECK (status IN ('ACTIVE', 'DRAFT', 'ARCHIVED')),
    stock_quantity INTEGER
        CHECK (stock_quantity >= 0),
    discount_pct INTEGER
        CHECK (discount_pct BETWEEN 0 AND 100),
    created_at TIMESTAMPTZ NOT NULL
);

INSERT INTO query_filter_lab.products (
    sku, product_name, category, price,
    status, stock_quantity, discount_pct, created_at
)
VALUES
    ('BOOK-PG-01',   'PostgreSQL căn bản',      'BOOK',
     120000, 'ACTIVE',   15, 10,   '2026-01-01 08:00:00+00'),

    ('BOOK-SQL-02',  'SQL nâng cao',            'BOOK',
     260000, 'ACTIVE',    2, NULL, '2026-01-15 10:00:00+00'),

    ('BOOK-JAVA-03', 'Lập trình Java',          'BOOK',
     200000, 'DRAFT',   NULL, 5,   '2026-02-01 09:30:00+00'),

    ('PEN-BLUE-01',  'Bút bi xanh',             'STATIONERY',
      12000, 'ACTIVE',  100, NULL, '2026-01-30 14:00:00+00'),

    ('PEN-RED-02',   'Bút mực đỏ',              'STATIONERY',
      25000, 'ACTIVE',    0, 0,    '2026-02-15 08:30:00+00'),

    ('NOTE-A5-01',   'Sổ A5',                   'STATIONERY',
      45000, 'DRAFT',    12, 15,  '2026-02-28 23:59:59+00'),

    ('MOUSE-WL-01',  'Chuột không dây',         'ACCESSORY',
     350000, 'ACTIVE',    8, 20,  '2026-03-01 00:00:00+00'),

    ('KB-MECH-01',   'Bàn phím cơ',             'ACCESSORY',
     950000, 'ARCHIVED',  1, NULL,'2026-03-15 10:00:00+00'),

    ('USB-C-01',     'Cáp USB-C',               'ACCESSORY',
      99000, 'ACTIVE',   25, 5,   '2026-03-20 12:00:00+00'),

    ('BOOK-PG-04',   'postgresql thực hành',    'BOOK',
     300000, 'ACTIVE',    0, NULL,'2026-03-31 23:59:59+00'),

    ('BOOK-PG-05',   'POSTGRESQL chuyên sâu',   'BOOK',
     500000, 'ACTIVE', NULL, NULL,'2026-04-01 00:00:00+00'),

    ('GIFT-NEW-01',  'Hộp quà 100% mới',        'GIFT',
      70000, 'DRAFT',     3, NULL,'2026-04-10 16:00:00+00'),

    ('PEN_BLUE_03',  'Bút chì 2B',              'STATIONERY',
       8000, 'ACTIVE',    7, NULL,'2026-02-20 09:00:00+00');
```

Kiểm tra:

```sql
SELECT
    product_id,
    sku,
    category,
    price,
    status,
    stock_quantity,
    discount_pct,
    created_at
FROM query_filter_lab.products
ORDER BY product_id;

SELECT COUNT(*) AS total_products
FROM query_filter_lab.products;
```

Nếu chưa có phiên khác thay đổi bảng, kết quả đếm là **13 hàng**.

Các giá trị `NULL` ở `stock_quantity` và `discount_pct` là chủ đích: chúng giúp thấy rõ hành vi của `NOT IN`, `BETWEEN` và điều kiện kết hợp khi thiếu dữ liệu.

### 3.1. Những cột được dùng trong bài

| Cột | Ý nghĩa | Điều cần nhớ |
| --- | --- | --- |
| `sku` | Mã sản phẩm | Có cả ký tự `-` và `_` |
| `product_name` | Tên hiển thị | Có các cách viết PostgreSQL/postgresql/POSTGRESQL |
| `category` | Danh mục | `BOOK`, `STATIONERY`, `ACCESSORY`, `GIFT` |
| `price` | Giá tiền | Kiểu `NUMERIC(12,2)` |
| `status` | Trạng thái | `ACTIVE`, `DRAFT`, `ARCHIVED` |
| `stock_quantity` | Tồn kho | Có thể `NULL`; 0 khác `NULL` |
| `discount_pct` | Phần trăm giảm giá | Có thể `NULL`; 0 khác `NULL` |
| `created_at` | Thời điểm tạo | `TIMESTAMPTZ` có múi giờ |

---

## 4. IN: kiểm tra giá trị thuộc một tập

Cú pháp:

```sql
expression IN (value_1, value_2, value_3, ...)
```

Nó gần với phép so sánh:

```sql
expression = value_1
OR expression = value_2
OR expression = value_3
```

Ví dụ tìm sản phẩm thuộc hai danh mục:

```sql
SELECT sku, product_name, category
FROM query_filter_lab.products
WHERE category IN ('BOOK', 'ACCESSORY')
ORDER BY category, sku;
```

Các hàng thuộc BOOK hoặc ACCESSORY được giữ, còn STATIONERY và GIFT bị loại.

### 4.1. IN giúp viết truy vấn ngắn và dễ mở rộng

Không dùng `IN`:

```sql
SELECT sku, status
FROM query_filter_lab.products
WHERE status = 'ACTIVE'
   OR status = 'DRAFT'
ORDER BY sku;
```

Tương đương cho dữ liệu không NULL:

```sql
SELECT sku, status
FROM query_filter_lab.products
WHERE status IN ('ACTIVE', 'DRAFT')
ORDER BY sku;
```

Cách dùng `IN` dễ đọc hơn khi có nhiều giá trị cùng một cột. Với các biểu thức phức tạp hoặc so sánh phụ thuộc từng trường khác nhau, `OR` vẫn có thể phù hợp hơn.

### 4.2. IN chỉ giữ các giá trị bằng nhau, không tìm chuỗi con

Ví dụ:

```sql
WHERE category IN ('BOOK', 'GIFT')
```

nghĩa là category phải **bằng** `BOOK` hoặc `GIFT`, không phải tên category có chứa một trong hai chuỗi.

`IN ('BOOK')` không giống `LIKE '%BOOK%'`. Cũng đừng dùng `IN` khi người dùng muốn tìm các từ khóa bên trong tên sản phẩm; khi đó `LIKE`/`ILIKE` có thể phù hợp.

### 4.3. NOT IN: lọc các giá trị không thuộc tập

```sql
SELECT sku, status
FROM query_filter_lab.products
WHERE status NOT IN ('DRAFT', 'ARCHIVED')
ORDER BY sku;
```

Vì `status` của bảng lab có `NOT NULL` và chỉ nhận ba trạng thái, câu này trả các sản phẩm ACTIVE.

Có thể hiểu theo ngữ nghĩa:

```sql
WHERE status <> 'DRAFT'
  AND status <> 'ARCHIVED'
```

Tuy nhiên, `NOT IN` có **bẫy NULL** sẽ được giải thích ngay sau đây.

### 4.4. IN với NULL: một giá trị không khớp có thể trả UNKNOWN

Xét biểu thức:

```sql
SELECT
    'BOOK' IN ('BOOK', NULL) AS case_match,
    'GIFT' IN ('BOOK', NULL) AS case_no_match,
    NULL::TEXT IN ('BOOK', 'GIFT') AS null_left;
```

Ý nghĩa:

| Biểu thức | Kết quả |
| --- | --- |
| `'BOOK' IN ('BOOK', NULL)` | `TRUE` vì có phần tử khớp |
| `'GIFT' IN ('BOOK', NULL)` | `NULL` vì không khớp `BOOK`, còn so sánh với `NULL` là unknown |
| `NULL IN ('BOOK', 'GIFT')` | `NULL` |

Trong `WHERE`, cả `FALSE` và `NULL` đều bị lọc ra. Nếu bạn tưởng `'GIFT' IN ('BOOK', NULL)` luôn trả FALSE thì nhiều điều kiện phủ định về sau sẽ sai.

### 4.5. Bẫy đặc biệt nguy hiểm: NOT IN có NULL ở bên phải

Truy vấn:

```sql
SELECT sku, discount_pct
FROM query_filter_lab.products
WHERE discount_pct NOT IN (0, 10, NULL)
ORDER BY sku;
```

Trong dữ liệu lab, truy vấn này **không trả hàng nào**.

Lý do:

- Với `discount_pct = 0` hoặc `10`, `IN` có giá trị TRUE, nên `NOT IN` là FALSE.
- Với các giá trị khác như `5`, `15`, `20`, không có phần tử số khớp, nhưng phần tử `NULL` khiến kết quả `IN` là UNKNOWN; phủ định UNKNOWN vẫn UNKNOWN.
- Với `discount_pct IS NULL`, kết quả cũng UNKNOWN.

Có thể thấy rõ:

```sql
SELECT
    5 NOT IN (0, 10, NULL) AS five_case,
    0 NOT IN (0, 10, NULL) AS zero_case,
    NULL::INTEGER NOT IN (0, 10) AS null_case;
```

Đừng coi `NULL` là một số hoặc giá trị bình thường trong danh sách. Muốn tìm các sản phẩm có mức giảm giá **được biết** và khác 0,10:

```sql
SELECT sku, discount_pct
FROM query_filter_lab.products
WHERE discount_pct IS NOT NULL
  AND discount_pct NOT IN (0, 10)
ORDER BY sku;
```

Kết quả của các hàng đã có mức giảm giá trong lab là:

| SKU | discount_pct |
| --- | ---: |
| `BOOK-JAVA-03` | 5 |
| `MOUSE-WL-01` | 20 |
| `NOTE-A5-01` | 15 |
| `USB-C-01` | 5 |

Nếu nghiệp vụ muốn **bao gồm cả sản phẩm chưa có discount**, cần nói rõ:

```sql
WHERE discount_pct IS NULL
   OR discount_pct NOT IN (0, 10)
```

Không có một cách xử lý NULL mặc định đúng cho mọi nghiệp vụ.

### 4.6. IN với subquery

Tập giá trị ở phía bên phải không nhất thiết phải viết cứng:

```sql
SELECT p.sku, p.product_name
FROM query_filter_lab.products AS p
WHERE p.category IN (
    SELECT c.category_code
    FROM (
        VALUES ('BOOK'), ('GIFT')
    ) AS c(category_code)
)
ORDER BY p.sku;
```

Đây là ví dụ subquery tự chứa. Trong ứng dụng thực tế, subquery có thể đọc một bảng category được cấp phép.

Với một tập giá trị lấy từ bảng, có thể cân nhắc `IN (SELECT ...)` hoặc `EXISTS` tùy ý nghĩa quan hệ, quy tắc NULL và kế hoạch thực thi.

Đặc biệt:

```sql
WHERE p.sku NOT IN (
    SELECT excluded_sku
    FROM some_exclusion_table
)
```

có nguy cơ bỏ hết các hàng không khớp nếu subquery trả **một hàng `NULL`**. Nếu muốn kiểm tra “không tồn tại hàng loại trừ trùng SKU”, mẫu `NOT EXISTS` thường diễn đạt trực tiếp hơn:

```sql
-- Mẫu cú pháp: some_exclusion_table là bảng minh họa chưa tạo.
WHERE NOT EXISTS (
    SELECT 1
    FROM some_exclusion_table AS e
    WHERE e.excluded_sku = p.sku
)
```

Cần tự xác định ý nghĩa khi một trong hai khóa có NULL. `NOT EXISTS` và `NOT IN` không hoàn toàn tương đương trong mọi trường hợp có NULL.

### 4.7. IN với một cặp cột

PostgreSQL có thể so sánh các tổ hợp giá trị bằng row constructor:

```sql
SELECT sku, category, status
FROM query_filter_lab.products
WHERE (category, status) IN (
    ('BOOK', 'ACTIVE'),
    ('GIFT', 'DRAFT')
)
ORDER BY sku;
```

Điều kiện giữ các sản phẩm BOOK đang ACTIVE và các sản phẩm GIFT đang DRAFT. Nó **khác**:

```sql
WHERE category IN ('BOOK', 'GIFT')
  AND status IN ('ACTIVE', 'DRAFT')
```

vì câu thứ hai cho phép thêm cả tổ hợp `BOOK + DRAFT` và `GIFT + ACTIVE`. Khi nhiều cột phải khớp **đúng cặp giá trị**, cần biểu diễn từng cặp đúng cách.

### 4.8. Danh sách động và mảng PostgreSQL

Trong PostgreSQL, khi ứng dụng truyền một danh sách có độ dài thay đổi, có thể dùng toán tử `= ANY(array)`:

```sql
SELECT sku, category
FROM query_filter_lab.products
WHERE category = ANY(ARRAY['BOOK', 'GIFT']::TEXT[])
ORDER BY sku;
```

Ý nghĩa với mảng giá trị không NULL tương tự `IN ('BOOK', 'GIFT')`.

Có thể dùng câu prepared statement:

```sql
PREPARE products_by_categories(TEXT[]) AS
SELECT sku, category
FROM query_filter_lab.products
WHERE category = ANY($1)
ORDER BY sku;

EXECUTE products_by_categories(
    ARRAY['BOOK', 'ACCESSORY']::TEXT[]
);

DEALLOCATE products_by_categories;
```

Một số điểm cần biết:

- `IN ()` với danh sách rỗng **không phải cú pháp SQL hợp lệ**. Ứng dụng phải xử lý danh sách rỗng riêng hoặc dùng cách truyền mảng.
- `= ANY('{}'::TEXT[])` trả FALSE cho những giá trị thông thường vì không có phần tử nào khớp.
- `= ANY` cũng có logic NULL khi mảng chứa NULL, không tự giải quyết `NOT IN`.
- Không ghép thủ công chuỗi SQL từ các giá trị client gửi. Dùng bind parameter và driver hỗ trợ kiểu mảng nếu cần.

---

## 5. BETWEEN: kiểm tra giá trị trong một khoảng

Cú pháp:

```sql
expression BETWEEN lower_bound AND upper_bound
```

Với trường hợp so sánh thông thường, nó tương đương:

```sql
expression >= lower_bound
AND expression <= upper_bound
```

**Cả hai đầu mút đều được bao gồm.**

### 5.1. BETWEEN với số

Tìm sản phẩm trong khoảng giá từ 100.000 đến 300.000, bao gồm cả hai mức:

```sql
SELECT sku, price
FROM query_filter_lab.products
WHERE price BETWEEN 100000 AND 300000
ORDER BY price, sku;
```

Những hàng có giá 120000, 200000, 260000 và **300000** đều có thể xuất hiện. Mức giá đúng bằng 300000 không bị loại.

Một cách viết dài tương đương:

```sql
WHERE price >= 100000
  AND price <= 300000
```

Dạng dài hữu ích khi hai bên cần toán tử khác nhau, ví dụ `>=` ở đầu dưới và `<` ở đầu trên.

### 5.2. NOT BETWEEN

```sql
SELECT sku, price
FROM query_filter_lab.products
WHERE price NOT BETWEEN 100000 AND 300000
ORDER BY price, sku;
```

Điều kiện giữ các sản phẩm có giá **nhỏ hơn 100000 hoặc lớn hơn 300000**, với điều kiện giá được biết và phép so sánh cho kết quả xác định.

Tương đương về logic ở trường hợp thông thường:

```sql
WHERE price < 100000
   OR price > 300000
```

Nếu `price` là NULL, kết quả của cả `BETWEEN` và `NOT BETWEEN` thường là UNKNOWN, do đó không được giữ trong WHERE.

### 5.3. Hai đầu mút không tự đổi chỗ

```sql
SELECT 200 BETWEEN 300 AND 100 AS reversed_bounds;
```

Kết quả là FALSE, vì 200 không thể đồng thời lớn hơn hoặc bằng 300 và nhỏ hơn hoặc bằng 100.

PostgreSQL có cú pháp `BETWEEN SYMMETRIC` cho phép xử lý hai đầu mút không theo thứ tự, nhưng khi xây ứng dụng, thường nên **xác thực min/max của người dùng** thay vì âm thầm đổi nghĩa:

```sql
SELECT 200 BETWEEN SYMMETRIC 300 AND 100 AS symmetric_case;
```

Kết quả là TRUE. Chỉ dùng khi nghiệp vụ thực sự muốn chấp nhận hai đầu mút theo bất kỳ thứ tự nào.

### 5.4. BETWEEN với ngày DATE

Nếu cột là `DATE`:

```sql
-- Ví dụ cú pháp cho một bảng có cột order_date kiểu DATE.
WHERE order_date BETWEEN DATE '2026-03-01'
                     AND DATE '2026-03-31'
```

Ngày 31/03 được tính vào khoảng. Điều này thuận tiện khi mỗi giá trị chứa **ngày**, không chứa thời gian.

Nhưng với `TIMESTAMP` hoặc `TIMESTAMPTZ`, cần cẩn thận.

### 5.5. Bẫy thời gian: BETWEEN với TIMESTAMPTZ

Bảng lab có `created_at TIMESTAMPTZ`. Nếu muốn lấy mọi hàng trong **tháng 03/2026 theo UTC**, cách an toàn và rõ nghĩa là khoảng **nửa mở**:

```sql
SELECT sku, created_at
FROM query_filter_lab.products
WHERE created_at >= TIMESTAMPTZ '2026-03-01 00:00:00+00'
  AND created_at <  TIMESTAMPTZ '2026-04-01 00:00:00+00'
ORDER BY created_at, sku;
```

Câu này giữ các hàng từ đúng đầu ngày 01/03 tới trước đầu ngày 01/04, bất kể timestamp có phần giây nhỏ đến mức nào.

Các SKU có thời điểm thuộc tháng 03/2026 UTC trong lab:

| SKU | Thời điểm đã khai báo theo UTC |
| --- | --- |
| `MOUSE-WL-01` | 2026-03-01 00:00:00+00 |
| `KB-MECH-01` | 2026-03-15 10:00:00+00 |
| `USB-C-01` | 2026-03-20 12:00:00+00 |
| `BOOK-PG-04` | 2026-03-31 23:59:59+00 |

Hàng `BOOK-PG-05` có `created_at = 2026-04-01 00:00:00+00` nên bị loại.

Không nên viết:

```sql
-- Không bao phủ mọi thời điểm của ngày 31/03:
WHERE created_at BETWEEN '2026-03-01'
                     AND '2026-03-31'
```

Với kiểu timestamp, một ngày được chuyển sang timestamp thường đại diện đầu ngày (00:00:00) theo quy tắc timezone hiện hành. Phần lớn thời điểm của ngày 31/03 sẽ không được tính vào giới hạn cuối.

Cũng không nên sửa bằng cách thêm `23:59:59` rồi cho rằng đã bao gồm mọi thời điểm: PostgreSQL có thể lưu chính xác tới microsecond; các thời điểm có phần lẻ sau giây 59 vẫn có thể bị bỏ sót.

**Quy tắc thực hành cho timestamp:** ưu tiên `start <= time AND time < next_boundary` khi lọc theo ngày, tháng hoặc một khoảng lịch.

### 5.6. Múi giờ là một phần của yêu cầu

Khi yêu cầu “tháng 03 theo giờ Việt Nam”, mốc tháng phải được xác định theo múi giờ mong muốn, không tùy tiện lấy tháng UTC hoặc timezone session:

```sql
SELECT sku, created_at
FROM query_filter_lab.products
WHERE created_at >= TIMESTAMPTZ '2026-03-01 00:00:00+07'
  AND created_at <  TIMESTAMPTZ '2026-04-01 00:00:00+07'
ORDER BY created_at;
```

So với UTC, mốc này lệch 7 giờ. Ở những khu vực có daylight saving time, cần tính các mốc theo **múi giờ khu vực** phù hợp, không mặc định một offset cố định cho cả năm.

Việc cast cột `created_at::DATE` cũng có thể phụ thuộc timezone của session. Thêm biểu thức lên cột còn có thể ảnh hưởng cách index thông thường được sử dụng. Với truy vấn khoảng thời gian, ranh giới rõ ràng thường dễ kiểm soát hơn.

### 5.7. BETWEEN với TEXT

`BETWEEN` cũng có thể dùng với văn bản:

```sql
SELECT 'M'::TEXT BETWEEN 'A' AND 'Z' AS example_text_range;
```

Tuy nhiên, so sánh text phụ thuộc **collation và quy tắc sắp xếp**, không tự đồng nghĩa “chữ cái trong bảng alphabet” theo mọi ngôn ngữ. Không dùng khoảng text để thay kiểm tra prefix hay format SKU mà chưa hiểu collation.

Nếu muốn tìm mã bắt đầu bằng `BOOK-`, `LIKE 'BOOK-%'` biểu đạt ý định dễ hiểu hơn so với tự xây một khoảng chữ.

### 5.8. BETWEEN với NULL

```sql
SELECT
    NULL::INTEGER BETWEEN 1 AND 10 AS unknown_value,
    5 BETWEEN NULL::INTEGER AND 10 AS unknown_lower,
    5 NOT BETWEEN 1 AND NULL::INTEGER AS unknown_upper;
```

Các trường hợp này có thể trả NULL nếu không có phép so sánh thành phần nào đủ để kết luận FALSE/TRUE theo logic ba giá trị. Không nên coi `BETWEEN` là “sai” cho mọi trường hợp có NULL rồi dùng `NOT BETWEEN` để tìm giá trị thiếu.

Muốn lọc giá trị thiếu:

```sql
SELECT sku
FROM query_filter_lab.products
WHERE discount_pct IS NULL
ORDER BY sku;
```

Nếu muốn giá trị giảm giá nằm trong khoảng 5..20 hoặc chưa có giảm giá:

```sql
SELECT sku, discount_pct
FROM query_filter_lab.products
WHERE discount_pct BETWEEN 5 AND 20
   OR discount_pct IS NULL
ORDER BY sku;
```

Ý nghĩa điều kiện phải được quyết định theo nghiệp vụ, không theo cảm giác về từ “không nằm trong khoảng”.

---

## 6. LIKE: tìm chuỗi theo mẫu

Toán tử `LIKE` so sánh chuỗi với **mẫu (pattern)**.

Cú pháp:

```sql
text_expression LIKE pattern
```

Hai ký tự đại diện quan trọng nhất:

| Ký tự | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| `%` | Khớp **0 hoặc nhiều** ký tự | `'SQL%'`: bắt đầu bằng SQL |
| `_` | Khớp **đúng một** ký tự | `'A_C'`: A, một ký tự, C |

Những ký tự khác trong pattern thường là ký tự cần khớp theo ngữ nghĩa so sánh hiện hành. Mẫu `LIKE` thông thường phải khớp **toàn bộ chuỗi**, nên nếu chỉ muốn tìm một phần chuỗi ở giữa, bạn cần dùng `%` ở hai phía.

### 6.1. Tìm theo tiền tố

Tìm SKU bắt đầu bằng `BOOK-`:

```sql
SELECT sku, product_name
FROM query_filter_lab.products
WHERE sku LIKE 'BOOK-%'
ORDER BY sku;
```

Pattern `'BOOK-%'` nghĩa là:

- Phần đầu phải là `BOOK-`.
- Sau đó có thể có **0 hoặc nhiều ký tự**.

Dấu `-` ở đây là dấu gạch nối thông thường, **không phải wildcard** của LIKE.

### 6.2. Tìm theo hậu tố

```sql
SELECT sku
FROM query_filter_lab.products
WHERE sku LIKE '%-01'
ORDER BY sku;
```

Các SKU kết thúc bằng `-01` được giữ. Pattern có dấu `%` ở đầu cho phép nhiều ký tự trước đoạn hậu tố.

### 6.3. Tìm chuỗi con

```sql
SELECT sku, product_name
FROM query_filter_lab.products
WHERE product_name LIKE '%SQL%'
ORDER BY sku;
```

Câu này tìm chuỗi con viết đúng chữ hoa/thường là `SQL` trong tên sản phẩm theo quy tắc so sánh hiện hành. Nó có thể khớp `'PostgreSQL căn bản'` và `'SQL nâng cao'`, nhưng không nhất thiết khớp `'postgresql thực hành'` hay `'POSTGRESQL chuyên sâu'` vì cách viết hoa/thường khác.

Muốn tìm không phân biệt hoa/thường, dùng `ILIKE` trong phần tiếp theo.

### 6.4. Pattern bắt đầu và kết thúc

| Pattern | Nghĩa thông thường |
| --- | --- |
| `'SQL%'` | Bắt đầu bằng SQL |
| `'%SQL'` | Kết thúc bằng SQL |
| `'%SQL%'` | Chứa SQL ở bất kỳ vị trí nào |
| `'SQL'` | Khớp chính xác toàn chuỗi SQL |
| `'A_C'` | A, đúng một ký tự, rồi C |
| `'A__C'` | A, đúng hai ký tự, rồi C |
| `'%'` | Mọi chuỗi không NULL, kể cả chuỗi rỗng |
| `'_'` | Chuỗi gồm đúng một ký tự |
| `'__'` | Chuỗi gồm đúng hai ký tự |

Sử dụng trực tiếp SQL:

```sql
SELECT
    'SQL' LIKE 'SQL' AS exact_match,
    'SQL nâng cao' LIKE 'SQL%' AS prefix_match,
    'PostgreSQL' LIKE '%SQL' AS suffix_match,
    'ABC' LIKE 'A_C' AS one_character_match,
    'AC' LIKE 'A_C' AS too_short;
```

Các cột đầu tiên, thứ hai, thứ ba và thứ tư đều trả TRUE; `'AC' LIKE 'A_C'` trả FALSE vì thiếu một ký tự cho wildcard `_`.

### 6.5. Wildcard _ không phải dấu gạch dưới literal

Trong bảng lab có SKU:

```text
PEN_BLUE_03
```

Nếu dùng:

```sql
SELECT sku
FROM query_filter_lab.products
WHERE sku LIKE 'PEN_%'
ORDER BY sku;
```

Ký tự `_` trong pattern là **wildcard một ký tự**, nên pattern có thể khớp mã bắt đầu bằng `PEN-...` hoặc `PEN_...`, không chỉ mã chứa dấu gạch dưới thật.

Muốn khớp dấu `_` như một ký tự literal, cần **escape** nó.

---

## 7. ESCAPE: tìm literal % và _

Khi dữ liệu cần tìm thực sự chứa dấu phần trăm hoặc dấu gạch dưới, bạn phải phân biệt wildcard với ký tự dữ liệu.

PostgreSQL hỗ trợ:

```sql
expression LIKE pattern ESCAPE '!'
```

Trong ví dụ, `!` được chọn làm **ký tự escape**. Đặt `!` trước `%` hoặc `_` để hiểu chúng là ký tự literal.

### 7.1. Tìm SKU có dấu gạch dưới ở vị trí xác định

```sql
SELECT sku
FROM query_filter_lab.products
WHERE sku LIKE 'PEN!_%' ESCAPE '!'
ORDER BY sku;
```

Giải nghĩa:

- `PEN`: ba ký tự literal.
- `!_`: **dấu gạch dưới thật**.
- `%`: phần còn lại tùy ý.

Trong dữ liệu mẫu, pattern này khớp `PEN_BLUE_03` mà không tự khớp các mã `PEN-BLUE-01` và `PEN-RED-02`.

### 7.2. Tìm tên chứa dấu % thật

Tên `'Hộp quà 100% mới'` có dấu phần trăm literal. Truy vấn:

```sql
SELECT sku, product_name
FROM query_filter_lab.products
WHERE product_name LIKE '%100!%%' ESCAPE '!';
```

Giải nghĩa pattern:

```text
%      : phần đầu bất kỳ
100    : chuỗi chữ số 100
!%     : ký tự % literal
%      : phần sau bất kỳ
```

Truy vấn có thể khớp sản phẩm `GIFT-NEW-01`.

### 7.3. Nếu ký tự escape cũng xuất hiện trong dữ liệu

Khi chọn `!` làm escape, nếu người dùng muốn tìm chính ký tự `!` thì phải escape nó thành `!!` trong pattern. Ví dụ một hàm xây dựng pattern tìm chuỗi con literal thường xử lý theo thứ tự:

1. `!` thành `!!`.
2. `%` thành `!%`.
3. `_` thành `!_`.
4. Thêm `%` ở đầu/cuối **nếu ứng dụng muốn tìm chuỗi con**.

Quy tắc này khác với escape dấu nháy đơn trong SQL string. Khi dùng bind parameter, driver xử lý an toàn việc đưa literal vào SQL; nhưng **wildcard của LIKE vẫn là cú pháp pattern**, nên vẫn cần escape pattern nếu không muốn người dùng nhập wildcard.

### 7.4. Vì sao ví dụ không dùng backslash mặc định?

PostgreSQL thường dùng dấu gạch chéo ngược làm ký tự escape mặc định của LIKE trong những trường hợp thông thường. Nhưng dấu `\` còn liên quan tới cách biểu diễn chuỗi và thiết lập `standard_conforming_strings`; người học dễ nhầm giữa escape của **SQL string literal** và escape của **LIKE pattern**.

Dùng `ESCAPE '!'` làm quy tắc tường minh giúp dễ phân biệt:

```sql
WHERE product_name LIKE '%100!%%' ESCAPE '!'
```

Nếu chọn một escape khác hoặc không muốn escape pattern, cần xác định quy tắc đồng nhất trong ứng dụng.

---

## 8. ILIKE: tìm kiếm không phân biệt chữ hoa/thường

`ILIKE` là toán tử PostgreSQL hỗ trợ so khớp pattern tương tự LIKE, nhưng **không phân biệt hoa/thường theo quy tắc ngôn ngữ/collation có hiệu lực**.

Ví dụ:

```sql
SELECT sku, product_name
FROM query_filter_lab.products
WHERE product_name ILIKE 'postgresql%'
ORDER BY sku;
```

Trong dữ liệu mẫu, các tên bắt đầu bằng PostgreSQL với cách viết hoa/thường khác nhau có thể đều khớp:

| SKU | Tên |
| --- | --- |
| `BOOK-PG-01` | PostgreSQL căn bản |
| `BOOK-PG-04` | postgresql thực hành |
| `BOOK-PG-05` | POSTGRESQL chuyên sâu |

Với `LIKE 'postgresql%'` ở ngữ cảnh so khớp phân biệt hoa/thường thông thường, chỉ tên bắt đầu bằng `postgresql` chữ thường được khớp.

### 8.1. ILIKE vẫn dùng % và _

```sql
SELECT sku, product_name
FROM query_filter_lab.products
WHERE product_name ILIKE '%sql%'
ORDER BY sku;
```

Pattern `'%sql%'` tìm chuỗi con `sql` không phân biệt hoa/thường. Nó khớp các biến thể có SQL trong tên.

Tương tự:

```sql
SELECT sku
FROM query_filter_lab.products
WHERE sku ILIKE 'pen!_%' ESCAPE '!';
```

Có thể khớp tiền tố literal `PEN_` bất kể chữ hoa/thường theo quy tắc ILIKE.

### 8.2. ILIKE khác với tìm không dấu

Không phân biệt hoa/thường **không đồng nghĩa** bỏ dấu tiếng Việt hay tự chuyển mọi biến thể Unicode về cùng ký tự.

Ví dụ:

- `'Bút'` và `'bút'` có thể được xem là cùng chuỗi theo ILIKE trong collation thích hợp.
- `'Bút'` và `'But'` **không tự được xem là tương đương chỉ vì dùng ILIKE**.

Nếu sản phẩm cần tìm không dấu hoặc khớp biến thể Unicode, có thể phải thiết kế normalize, extension phù hợp như `unaccent`, hoặc một search index riêng. Việc normalize phải nhất quán giữa dữ liệu, truy vấn và chính sách ngôn ngữ; `ILIKE` một mình không giải quyết toàn bộ tìm kiếm văn bản tự nhiên.

### 8.3. LIKE so với ILIKE

| Tiêu chí | LIKE | ILIKE |
| --- | --- | --- |
| Mục đích | So khớp chuỗi theo pattern | So khớp pattern không phân biệt hoa/thường theo locale |
| `%` và `_` | Có | Có |
| `ESCAPE` | Có | Có |
| Chỉ tìm tiền tố/hậu tố/chuỗi con | Có, nhờ cách đặt wildcard | Có |
| Phân biệt hoa/thường | Thông thường có | Thông thường không |
| Chuẩn hóa bỏ dấu tiếng Việt | Không tự có | Không tự có |
| Cú pháp PostgreSQL | Hỗ trợ | PostgreSQL-specific |
| Hiệu năng khi bắt đầu bằng `%` | Thường khó tận dụng B-tree prefix thông thường | Tương tự, thường cần thiết kế index phù hợp |

### 8.4. NOT LIKE và NOT ILIKE

```sql
SELECT sku, product_name
FROM query_filter_lab.products
WHERE product_name NOT ILIKE '%postgresql%'
ORDER BY sku;
```

Câu này giữ những tên **không khớp** pattern `'%postgresql%'`, với điều kiện giá trị có kết quả so sánh xác định.

Nếu `product_name IS NULL`, `NOT ILIKE` cũng không tự coi nó là “không chứa chữ” — kết quả so sánh có thể là UNKNOWN. Nếu nghiệp vụ muốn bao gồm giá trị thiếu:

```sql
-- Dạng tổng quát nếu cột name cho phép NULL.
WHERE product_name IS NULL
   OR product_name NOT ILIKE '%postgresql%'
```

Trong bảng lab, `product_name` có `NOT NULL` nên nhánh bổ sung không cần thiết.

---

## 9. Kết hợp AND, OR và NOT

Khi một bộ lọc có nhiều điều kiện, dùng các toán tử logic.

| Toán tử | Ý nghĩa |
| --- | --- |
| `AND` | Các điều kiện liên quan phải thỏa |
| `OR` | Ít nhất một điều kiện phải thỏa |
| `NOT` | Đảo giá trị logic của điều kiện, nhưng UNKNOWN vẫn UNKNOWN |

### 9.1. AND: đồng thời thỏa nhiều điều kiện

Lấy sản phẩm BOOK đang ACTIVE và giá không vượt 300000:

```sql
SELECT sku, product_name, category, price, status
FROM query_filter_lab.products
WHERE category = 'BOOK'
  AND status = 'ACTIVE'
  AND price <= 300000
ORDER BY price, sku;
```

Các SKU phù hợp trong lab: `BOOK-PG-01`, `BOOK-SQL-02` và `BOOK-PG-04`. `BOOK-JAVA-03` bị loại vì trạng thái DRAFT; `BOOK-PG-05` bị loại vì giá 500000.

### 9.2. OR: chỉ cần một điều kiện đúng

```sql
SELECT sku, category
FROM query_filter_lab.products
WHERE category = 'BOOK'
   OR category = 'GIFT'
ORDER BY sku;
```

Trong tình huống cùng một cột so sánh bằng với nhiều giá trị, dạng `category IN ('BOOK','GIFT')` thường ngắn hơn.

Tuy nhiên, `OR` cần thiết nếu điều kiện khác cột hoặc khác toán tử:

```sql
SELECT sku, status, price
FROM query_filter_lab.products
WHERE status = 'ARCHIVED'
   OR price < 10000
ORDER BY sku;
```

Câu trên giữ `KB-MECH-01` vì ARCHIVED và `PEN_BLUE_03` vì giá 8000.

### 9.3. Dấu ngoặc quyết định ý nghĩa của bộ lọc

Giả sử yêu cầu:

> Chỉ lấy sản phẩm ACTIVE, đồng thời là BOOK **hoặc** có giá dưới 20000.

Viết đúng:

```sql
SELECT sku, category, status, price
FROM query_filter_lab.products
WHERE status = 'ACTIVE'
  AND (
      category = 'BOOK'
      OR price < 20000
  )
ORDER BY sku;
```

Nếu bỏ ngoặc:

```sql
SELECT sku, category, status, price
FROM query_filter_lab.products
WHERE status = 'ACTIVE'
  AND category = 'BOOK'
  OR price < 20000
ORDER BY sku;
```

SQL ưu tiên `AND` cao hơn `OR`, nên câu không ngoặc được hiểu là:

```sql
WHERE (status = 'ACTIVE' AND category = 'BOOK')
   OR price < 20000
```

Bất kỳ sản phẩm có giá dưới 20000 đều được chấp nhận ở nhánh sau, **ngay cả khi không ACTIVE**.

Với dữ liệu mẫu, các sản phẩm dưới 20000 đều ACTIVE, nên hai câu có thể tình cờ cho cùng tập ở một thời điểm. Đó không phải bảo đảm logic tương đương. Nếu sau này thêm một sản phẩm DRAFT giá 5000, câu thiếu ngoặc sẽ đưa nó vào sai yêu cầu.

**Thói quen tốt:** khi trộn `AND` và `OR`, luôn dùng ngoặc để biểu diễn ý định nghiệp vụ.

### 9.4. Mức ưu tiên của toán tử logic

Với các biểu thức logic thông thường:

1. `NOT` có ưu tiên cao hơn.
2. `AND` tiếp theo.
3. `OR` có ưu tiên thấp hơn.

Ví dụ:

```sql
WHERE NOT (status = 'ARCHIVED' OR price < 10000)
```

khác với:

```sql
WHERE NOT status = 'ARCHIVED'
   OR price < 10000
```

Câu đầu từ chối cả ARCHIVED lẫn giá dưới 10000. Câu thứ hai có thể giữ một hàng giá dưới 10000 dù những điều kiện khác không thỏa, vì nó có nhánh OR.

Khi có `BETWEEN lower AND upper`, chữ `AND` trong cú pháp BETWEEN là một phần của biểu thức khoảng, không phải phép AND tách biệt giữa hai filter. Dù PostgreSQL phân tích cú pháp đúng, thêm ngoặc quanh các điều kiện phức tạp sẽ giúp người đọc tránh hiểu nhầm.

### 9.5. NOT và dấu ngoặc

Nếu muốn loại mọi sản phẩm BOOK hoặc GIFT:

```sql
SELECT sku, category
FROM query_filter_lab.products
WHERE NOT (category IN ('BOOK', 'GIFT'))
ORDER BY sku;
```

Tương đương với `category NOT IN ('BOOK','GIFT')` trên dữ liệu không NULL. Nhưng với tập có NULL, mọi biểu thức phủ định vẫn cần xử lý logic ba giá trị như đã trình bày.

Nếu muốn loại chỉ những sản phẩm vừa ACTIVE vừa BOOK:

```sql
WHERE NOT (
    status = 'ACTIVE'
    AND category = 'BOOK'
)
```

Điều này tương đương theo logic ba giá trị với:

```sql
WHERE status <> 'ACTIVE'
   OR category <> 'BOOK'
```

Không nên đổi thành `status <> 'ACTIVE' AND category <> 'BOOK'`, vì câu sau loại rộng hơn nhiều.

---

## 10. Logic ba giá trị khi kết hợp điều kiện

Đây là bảng rút gọn quan trọng:

| A | B | `A AND B` | `A OR B` |
| --- | --- | --- | --- |
| TRUE | TRUE | TRUE | TRUE |
| TRUE | FALSE | FALSE | TRUE |
| TRUE | NULL | NULL | TRUE |
| FALSE | FALSE | FALSE | FALSE |
| FALSE | NULL | FALSE | NULL |
| NULL | NULL | NULL | NULL |

Với `NOT`:

| A | `NOT A` |
| --- | --- |
| TRUE | FALSE |
| FALSE | TRUE |
| NULL | NULL |

Điều đó lý giải vì sao:

```sql
WHERE stock_quantity > 0
```

không giữ các hàng có tồn kho NULL, và:

```sql
WHERE NOT (stock_quantity > 0)
```

cũng **không giữ** các hàng có tồn kho NULL. Trên những hàng đó, điều kiện là UNKNOWN và phép NOT không đổi UNKNOWN thành TRUE.

### 10.1. IS NULL và IS NOT NULL

Muốn tìm các sản phẩm chưa xác định tồn kho:

```sql
SELECT sku, stock_quantity
FROM query_filter_lab.products
WHERE stock_quantity IS NULL
ORDER BY sku;
```

Theo dữ liệu mẫu, `BOOK-JAVA-03` và `BOOK-PG-05` có tồn kho NULL.

Muốn tìm sản phẩm có tồn kho là 0:

```sql
SELECT sku, stock_quantity
FROM query_filter_lab.products
WHERE stock_quantity = 0
ORDER BY sku;
```

Theo dữ liệu mẫu, `BOOK-PG-04` và `PEN-RED-02` có stock = 0.

Hai câu tìm **hai trạng thái khác nhau**:

- `0`: biết chắc hết tồn theo quy ước dữ liệu.
- `NULL`: tồn kho chưa được ghi nhận/không xác định theo mô hình.

### 10.2. Phối hợp OR để bao gồm NULL có chủ đích

Nếu nghiệp vụ muốn “sản phẩm có tồn kho hoặc tồn kho chưa được cập nhật”:

```sql
SELECT sku, stock_quantity
FROM query_filter_lab.products
WHERE stock_quantity > 0
   OR stock_quantity IS NULL
ORDER BY sku;
```

Các sản phẩm có stock = 0 bị loại. Các sản phẩm stock NULL được giữ vì nhánh `IS NULL` trả TRUE.

Nếu nghiệp vụ chỉ muốn “chắc chắn còn hàng”, dùng:

```sql
WHERE stock_quantity > 0
```

Không có một quy tắc “NULL nghĩa là 0” mặc định của PostgreSQL. Việc dùng `COALESCE(stock_quantity, 0)` để coi NULL là hết hàng phải là quyết định nghiệp vụ.

### 10.3. IS DISTINCT FROM: so sánh có định nghĩa với NULL

PostgreSQL hỗ trợ:

```sql
a IS DISTINCT FROM b
```

So sánh này trả TRUE/FALSE, kể cả khi một trong hai giá trị là NULL. Nó coi hai NULL là không khác nhau.

Ví dụ:

```sql
SELECT
    NULL::INTEGER IS DISTINCT FROM 0 AS null_vs_zero,
    NULL::INTEGER IS DISTINCT FROM NULL::INTEGER AS two_nulls,
    5 IS DISTINCT FROM 0 AS five_vs_zero;
```

Kết quả lần lượt TRUE, FALSE, TRUE.

Đây là công cụ hữu ích khi muốn so sánh an toàn với NULL, nhưng không phải cách thay thế mọi danh sách `NOT IN` một cách máy móc. Luôn xác định “không có dữ liệu” có được coi là một giá trị khác hay không.

---

## 11. Ghép IN, BETWEEN, ILIKE và các điều kiện khác

### 11.1. Truy vấn đúng một bộ lọc sản phẩm

Giả sử yêu cầu:

> Lấy sản phẩm đang bán, thuộc BOOK hoặc ACCESSORY, giá trong 100000..400000, sắp xếp theo giá tăng dần.

```sql
SELECT sku, product_name, category, price
FROM query_filter_lab.products
WHERE status = 'ACTIVE'
  AND category IN ('BOOK', 'ACCESSORY')
  AND price BETWEEN 100000 AND 400000
ORDER BY price ASC, sku ASC;
```

Kết quả của dữ liệu mẫu:

| SKU | Danh mục | Giá |
| --- | --- | ---: |
| `BOOK-PG-01` | BOOK | 120000 |
| `BOOK-SQL-02` | BOOK | 260000 |
| `BOOK-PG-04` | BOOK | 300000 |
| `MOUSE-WL-01` | ACCESSORY | 350000 |

Các hàng như `BOOK-JAVA-03` (DRAFT), `BOOK-PG-05` (giá 500000) và `KB-MECH-01` (ARCHIVED) bị loại bởi các điều kiện tương ứng.

### 11.2. Thêm điều kiện tên theo ILIKE

Giả sử yêu cầu chỉ lấy sản phẩm ACTIVE có tên bắt đầu bằng `PostgreSQL` hoặc `SQL`, không phân biệt hoa/thường:

```sql
SELECT sku, product_name, status
FROM query_filter_lab.products
WHERE status = 'ACTIVE'
  AND (
      product_name ILIKE 'postgresql%'
      OR product_name ILIKE 'sql%'
  )
ORDER BY sku;
```

Kết quả có thể gồm `BOOK-PG-01`, `BOOK-PG-04`, `BOOK-PG-05` và `BOOK-SQL-02`.

Đừng viết:

```sql
WHERE status = 'ACTIVE'
  AND product_name ILIKE 'postgresql%'
  OR product_name ILIKE 'sql%'
```

nếu ý định yêu cầu **mọi sản phẩm đều ACTIVE**, vì nhóm SQL ở nhánh cuối sẽ không còn chịu điều kiện ACTIVE. Dùng ngoặc để tránh lỗi khi dữ liệu thay đổi.

### 11.3. Bộ lọc có điều kiện NULL

Giả sử yêu cầu:

> ACTIVE, thuộc BOOK hoặc STATIONERY, giá từ 10000 tới 300000 và tồn kho lớn hơn 0 **hoặc chưa xác định**.

```sql
SELECT
    sku, category, status, price, stock_quantity
FROM query_filter_lab.products
WHERE status = 'ACTIVE'
  AND category IN ('BOOK', 'STATIONERY')
  AND price BETWEEN 10000 AND 300000
  AND (
      stock_quantity > 0
      OR stock_quantity IS NULL
  )
ORDER BY sku;
```

Theo dữ liệu mẫu, kết quả gồm `BOOK-PG-01`, `BOOK-SQL-02`, `PEN-BLUE-01`. Những hàng stock 0 bị loại; `BOOK-PG-05` có stock NULL nhưng giá vượt 300000 nên cũng bị loại.

Bỏ ngoặc ở phần tồn kho sẽ thay đổi ngữ nghĩa. Khi đó `OR stock_quantity IS NULL` có thể cho phép những hàng không đáp ứng status, category hoặc price.

### 11.4. Truy vấn OR có nhóm nghiệp vụ khác nhau

Giả sử yêu cầu:

- Nhóm 1: tất cả BOOK đang ACTIVE;
- Hoặc nhóm 2: sản phẩm DRAFT có giá dưới 50000.

```sql
SELECT sku, category, status, price
FROM query_filter_lab.products
WHERE (
    category = 'BOOK'
    AND status = 'ACTIVE'
)
OR (
    status = 'DRAFT'
    AND price < 50000
)
ORDER BY sku;
```

Với lab, nhóm thứ hai gồm `NOTE-A5-01` (DRAFT, giá 45000). `BOOK-JAVA-03` có status DRAFT nhưng giá 200000 nên không thuộc nhóm thứ hai.

Đây là một cách biểu diễn **hai trường hợp nghiệp vụ độc lập**, rõ ràng hơn việc trộn dài một dãy AND/OR không có ngoặc.

### 11.5. Nhiều mẫu LIKE có thể viết thế nào?

Nếu muốn tên bắt đầu bằng một trong hai từ khóa:

```sql
WHERE product_name ILIKE 'postgresql%'
   OR product_name ILIKE 'sql%'
```

Với PostgreSQL, một số toán tử pattern còn có thể dùng với `ANY` trên mảng:

```sql
SELECT sku, product_name
FROM query_filter_lab.products
WHERE product_name ILIKE ANY (
    ARRAY['postgresql%', 'sql%']::TEXT[]
)
ORDER BY sku;
```

Điều này giúp diễn đạt tập pattern rõ hơn khi số lượng mẫu thay đổi. Tuy nhiên, `ILIKE ANY` vẫn áp dụng wildcard trong từng phần tử; không xem các phần tử là chuỗi literal nếu người dùng nhập `%` hoặc `_` mà chưa escape.

---

## 12. Lọc ở WHERE và lọc ở HAVING có giống nhau không?

Với truy vấn cơ bản, `WHERE` áp dụng điều kiện lên **hàng đầu vào** trước khi nhóm, còn `HAVING` áp dụng điều kiện lên **nhóm kết quả** sau tổng hợp.

Ví dụ:

```sql
SELECT
    category,
    COUNT(*) AS active_count,
    MIN(price) AS min_price,
    MAX(price) AS max_price
FROM query_filter_lab.products
WHERE status = 'ACTIVE'
  AND category IN ('BOOK', 'ACCESSORY')
GROUP BY category
HAVING COUNT(*) >= 2
ORDER BY category;
```

Giải thích:

1. `WHERE` chỉ giữ những sản phẩm ACTIVE thuộc BOOK hoặc ACCESSORY.
2. `GROUP BY category` gom các hàng còn lại theo category.
3. `HAVING COUNT(*) >= 2` giữ nhóm có ít nhất hai sản phẩm.
4. `ORDER BY` sắp xếp các nhóm.

Không đặt `COUNT(*) >= 2` trực tiếp vào `WHERE` của cùng một SELECT vì `WHERE` không phải nơi kiểm tra giá trị tổng hợp của nhóm.

Đây là một mở rộng hữu ích: `IN`, `BETWEEN` hay `LIKE` cũng có thể xuất hiện trong `HAVING` nếu biểu thức và ngữ nghĩa nhóm phù hợp, nhưng bài này tập trung vào lọc hàng bằng WHERE.

---

## 13. An toàn SQL khi điều kiện đến từ người dùng

Một API tìm kiếm thường nhận dữ liệu:

```text
?categories=BOOK,ACCESSORY
&minPrice=100000
&maxPrice=400000
&name=postgresql
```

Không nên nối trực tiếp các giá trị đó vào chuỗi SQL. Ví dụ rủi ro:

```text
sql = "SELECT ... WHERE product_name ILIKE '%" + userInput + "%'";
```

Nếu `userInput` chứa dấu quote hoặc cấu trúc SQL khác, có thể gây lỗi hoặc tạo nguy cơ SQL injection.

Dùng **parameterized query** với driver phù hợp. Ngoài ra, cần xử lý pattern của LIKE/ILIKE đúng ý định người dùng.

### 13.1. Bind parameter không tự vô hiệu hóa wildcard

Giả sử ứng dụng tạo:

```sql
WHERE product_name ILIKE $1
```

và truyền `$1 = '%sql%'`. Đây là tham số pattern hợp lệ. Nếu người dùng nhập một dấu `%` và ứng dụng đặt nó làm pattern, dấu đó vẫn có tác dụng “khớp mọi chuỗi”.

Đây **không phải SQL injection**, vì dữ liệu đã được bind. Nhưng nếu nghiệp vụ muốn tìm **chuỗi literal**, có thể tạo một bộ lọc rộng hơn mong muốn và làm truy vấn tốn tài nguyên.

Hai yêu cầu khác nhau:

- **Cho phép người dùng viết pattern:** `%` và `_` có ý nghĩa wildcard.
- **Tìm chính xác nội dung người dùng gõ:** cần escape wildcard trước khi thêm các dấu `%` do ứng dụng chủ động tạo.

### 13.2. Ví dụ Java JDBC tìm chuỗi con literal

Ví dụ code Java (độc lập với bảng sản phẩm trong lab):

```java
import java.sql.PreparedStatement;
import java.sql.ResultSet;

// Người dùng gõ chuỗi cần tìm như nội dung literal, không phải LIKE pattern.
String input = userInput;

// Dùng dấu ! làm escape cho ILIKE.
String escaped = input
        .replace("!", "!!")
        .replace("%", "!%")
        .replace("_", "!_");

// Chỉ hai dấu % bên ngoài là wildcard do ứng dụng chủ động thêm.
String pattern = "%" + escaped + "%";

String sql = """
    SELECT sku, product_name
    FROM query_filter_lab.products
    WHERE product_name ILIKE ? ESCAPE '!'
    ORDER BY sku
    """;

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setString(1, pattern);

    try (ResultSet rs = ps.executeQuery()) {
        while (rs.next()) {
            String sku = rs.getString("sku");
            String name = rs.getString("product_name");
            // Xử lý kết quả theo ứng dụng.
        }
    }
}
```

Mục tiêu:

- SQL và dữ liệu người dùng được **tách riêng** qua PreparedStatement.
- `%` và `_` người dùng gõ được escape thành ký tự literal.
- Dấu `%` do ứng dụng thêm ở hai bên có nghĩa tìm chuỗi con.

Nếu bạn **muốn cho phép người dùng nhập wildcard**, không escape chúng như ví dụ; nhưng phải thiết kế giới hạn độ dài pattern, phân trang, timeout và kiểm soát tải truy vấn phù hợp.

### 13.3. Danh sách IN do người dùng gửi

Không ghép:

```text
"WHERE category IN (" + rawCategoryList + ")"
```

vì đầu vào có thể chứa ký tự phá cú pháp và khiến logic không an toàn.

Các hướng thường dùng:

- Tạo số lượng placeholder cố định/tùy số phần tử, sau đó bind từng giá trị bằng driver.
- Dùng mảng PostgreSQL và `= ANY($1::TEXT[])` khi driver hỗ trợ.
- Xác thực số lượng phần tử tối đa và tập category hợp lệ.
- Xử lý danh sách rỗng theo ngữ nghĩa ứng dụng (không có category → không có kết quả, hay bỏ filter?).
- Không cho client tự điền tên cột, toán tử hay SQL fragment nếu không có whitelist.

Giá trị data có thể bind; **định danh bảng/cột** phải được lựa chọn từ danh sách cho phép, không cố bind chúng như literal dữ liệu.

### 13.4. Tham số khoảng giá

Mẫu SQL:

```sql
SELECT sku, price
FROM query_filter_lab.products
WHERE price >= $1
  AND price <= $2
ORDER BY price;
```

Khi ứng dụng dùng prepared statement, `$1` và `$2` được bind bằng kiểu decimal tương thích, ví dụ Java `BigDecimal`. Trước khi chạy, ứng dụng cần:

1. Xác thực min và max là số hợp lệ.
2. Bảo đảm min không lớn hơn max theo hợp đồng API.
3. Kiểm soát tiền tệ và đơn vị nếu lọc theo giá.
4. Không dùng `double` làm giá trị tiền nếu ứng dụng cần độ chính xác decimal.

---

## 14. Hiệu năng và index cho các điều kiện lọc

Viết câu WHERE đúng chưa đủ nếu bảng có hàng triệu bản ghi. Một điều kiện có thể rất chọn lọc, hoặc buộc PostgreSQL kiểm tra nhiều hàng.

### 14.1. IN và BETWEEN thường có cơ hội dùng B-tree

Ví dụ các truy vấn:

```sql
WHERE category IN ('BOOK', 'GIFT')
```

và:

```sql
WHERE price BETWEEN 100000 AND 300000
```

thường là ứng viên tốt cho B-tree index nếu dữ liệu, tính chọn lọc và thống kê phù hợp.

Trên bảng lab có thể tạo:

```sql
CREATE INDEX idx_products_category
ON query_filter_lab.products (category);

CREATE INDEX idx_products_price
ON query_filter_lab.products (price);

CREATE INDEX idx_products_status_category_price
ON query_filter_lab.products (status, category, price);
```

Index tổng hợp trên `(status, category, price)` có thể phù hợp với những câu truy vấn thường lọc status bằng dấu `=`, category bằng `IN` và price theo khoảng. Tuy nhiên, hiệu quả phụ thuộc phân bố dữ liệu và cách planner lựa chọn.

**Không có quy tắc “thấy WHERE là chắc chắn index scan”.** Bảng 13 hàng trong lab có thể được PostgreSQL quét tuần tự vì rẻ hơn việc dùng index. Đó là lựa chọn hợp lý, không phải dấu hiệu index bị hỏng.

### 14.2. LIKE theo tiền tố và theo chuỗi con khác nhau

So sánh:

```sql
WHERE sku LIKE 'BOOK-%'
```

với:

```sql
WHERE sku LIKE '%BOOK%'
```

Mẫu đầu có một **tiền tố xác định**. Trong những điều kiện collation và operator class phù hợp, PostgreSQL có thể khai thác B-tree để tìm vùng tiền tố.

Mẫu thứ hai bắt đầu bằng `%`, tức có thể có bất kỳ nội dung nào trước BOOK. B-tree thông thường khó thu hẹp thành một khoảng prefix đơn giản.

Với cột text và những collation không mặc định hỗ trợ tối ưu pattern tiền tố theo B-tree, có thể xem xét operator class `text_pattern_ops`:

```sql
CREATE INDEX idx_products_sku_pattern
ON query_filter_lab.products (sku text_pattern_ops);
```

Đây là ví dụ index cho pattern prefix trên cột `sku TEXT`. Nó không tự biến mọi `ILIKE '%keyword%'` thành truy vấn nhanh, và không thay index/constraint UNIQUE hiện có của cột SKU.

### 14.3. ILIKE và hàm LOWER

Một cách thay thế tìm không phân biệt hoa/thường là:

```sql
WHERE lower(product_name) LIKE 'postgresql%'
```

Trên một số cấu hình, có thể xây expression index phù hợp cho biểu thức `lower(product_name)` và pattern prefix. Nhưng index B-tree thông thường chỉ trên `product_name` có thể không được dùng hiệu quả nếu truy vấn luôn áp dụng hàm `lower` lên cột.

Cần xem:

- Mức độ chọn lọc thực tế.
- Collation và luật so sánh chuỗi.
- Pattern có tiền tố cố định hay bắt đầu bằng `%`.
- Query planner có dùng index thực tế hay không.
- Chi phí bảo trì index khi INSERT/UPDATE.

Không tự áp dụng hàm `LOWER` cho mọi search nếu yêu cầu search cần xử lý dấu tiếng Việt, Unicode normalization hoặc thứ tự ngôn ngữ tinh vi hơn.

### 14.4. pg_trgm cho tìm chuỗi con

PostgreSQL có extension `pg_trgm` hỗ trợ index cho tìm kiếm dựa trên trigram, hữu ích với nhiều pattern `LIKE`/`ILIKE`, nhất là khi chứa chuỗi con và dữ liệu đủ lớn.

**Phần này là tùy chọn nâng cao; không cần chạy để hoàn thành lab cơ bản.** Trên database thử nghiệm và khi được phép cài extension:

```sql
CREATE EXTENSION IF NOT EXISTS pg_trgm;

CREATE INDEX idx_products_name_trgm
ON query_filter_lab.products
USING GIN (product_name gin_trgm_ops);
```

Sau đó ví dụ:

```sql
SELECT sku, product_name
FROM query_filter_lab.products
WHERE product_name ILIKE '%postgresql%';
```

có thể được planner cân nhắc dùng trigram index khi dữ liệu và thống kê phù hợp.

Giới hạn:

- Pattern quá ngắn hoặc không tạo đủ trigram hữu ích có thể không lọc tốt.
- Index tăng dung lượng và chi phí ghi/cập nhật.
- Truy vấn trên bảng cực nhỏ có thể vẫn dùng sequential scan.
- Hỗ trợ/trợ giúp extension phụ thuộc quyền và môi trường quản lý database.
- Trigram index không tự thay bài toán full-text search theo ngôn ngữ tự nhiên hoặc tìm không dấu.

Đừng chạy `CREATE EXTENSION` trên production nếu chưa có quyền và kế hoạch vận hành thích hợp.

### 14.5. Dùng EXPLAIN để kiểm tra

Trên lab có thể dùng:

```sql
EXPLAIN
SELECT sku, price
FROM query_filter_lab.products
WHERE status = 'ACTIVE'
  AND category IN ('BOOK', 'ACCESSORY')
  AND price BETWEEN 100000 AND 400000
ORDER BY price;
```

Để quan sát thời gian thực thi và buffer của **một SELECT**:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT sku, product_name
FROM query_filter_lab.products
WHERE product_name ILIKE '%postgresql%';
```

`EXPLAIN ANALYZE` **thực thi truy vấn**. Với những câu `INSERT`/`UPDATE`/`DELETE`, không chạy nó một cách tùy tiện trên production vì có thể thay đổi dữ liệu. Ở đây ta chỉ dùng `SELECT` để quan sát.

Cần phân biệt thời gian trên lab 13 hàng với một bảng có hàng triệu hàng; planner có thể chọn kế hoạch khác theo kích thước và thống kê.

### 14.6. Điều kiện OR và index

Một truy vấn:

```sql
WHERE category = 'BOOK'
   OR price < 20000
```

có thể dùng những chiến lược khác nhau: quét bảng, bitmap kết hợp các index hoặc các kế hoạch khác tùy dữ liệu. Không thể kết luận OR luôn chậm hoặc luôn vô hiệu hóa index.

Chỉ tạo index sau khi biết truy vấn quan trọng, độ chọn lọc, tần suất ghi và kế hoạch thực tế. Quá nhiều index có thể làm INSERT/UPDATE tốn thêm chi phí.

---

## 15. Các tình huống dễ nhầm trong PostgreSQL

### 15.1. IN không giống ILIKE ANY

```sql
WHERE category IN ('BOOK', 'GIFT')
```

là so sánh bằng với tập giá trị.

```sql
WHERE product_name ILIKE ANY (
    ARRAY['post%', 'sql%']::TEXT[]
)
```

là so khớp một **tập pattern**.

Nếu danh sách người dùng gửi là tên category chính xác, nên dùng IN hoặc `= ANY`. Nếu danh sách là mẫu text được cho phép, dùng ILIKE ANY có thể phù hợp nhưng cần hiểu wildcard.

### 15.2. BETWEEN bao gồm đầu cuối, nhưng nửa mở thường phù hợp timestamp

```sql
price BETWEEN 100 AND 200
```

bao gồm đúng 100 và 200.

```sql
created_at >= start_time
AND created_at < end_time
```

thích hợp khi mô tả một khoảng thời gian bắt đầu tại đầu mốc và kết thúc ngay trước mốc sau.

Không tự thay `< end_time` bằng `<= end_time` nếu end_time là đầu ngày/tháng tiếp theo.

### 15.3. LIKE không phải regex

Trong LIKE, `%` và `_` là wildcard chủ yếu. Các cú pháp regex như `.*`, `[0-9]` hay `^...$` không có nghĩa tương tự nếu được đưa vào LIKE như chuỗi pattern thông thường.

PostgreSQL còn có toán tử regex như `~` và `~*`, hoặc `SIMILAR TO`, nhưng đó là **cơ chế so khớp khác**. Không trộn cú pháp của chúng với LIKE.

Ví dụ nếu muốn mã có một chữ số cuối, `LIKE` chỉ biết `_` đại diện cho một ký tự bất kỳ; nó không tự kiểm tra ký tự đó là số. Khi yêu cầu format phức tạp, regex hoặc constraint phù hợp có thể diễn đạt chính xác hơn.

### 15.4. ILIKE không phải công cụ full-text search

`ILIKE '%postgresql%'` hữu ích để tìm chuỗi con. Nó không tự:

- Tách từ theo ngôn ngữ.
- Tìm từ đồng nghĩa.
- Hiểu dấu tiếng Việt theo ý muốn.
- Xếp hạng tài liệu theo độ liên quan.
- Hỗ trợ tìm mờ theo lỗi chính tả như một hệ thống search hoàn chỉnh.

Với dữ liệu bài viết/văn bản lớn, có thể cần PostgreSQL full-text search, `pg_trgm`, normalize hoặc hệ thống search chuyên dụng tùy bài toán.

### 15.5. NULL không bằng chuỗi rỗng

```sql
WHERE product_name = ''
```

tìm chuỗi rỗng, **không tìm NULL**.

```sql
WHERE product_name IS NULL
```

tìm giá trị NULL.

Tương tự:

```sql
WHERE product_name LIKE '%'
```

khớp những chuỗi không NULL (bao gồm chuỗi rỗng), nhưng không khớp NULL theo WHERE.

### 15.6. NULL không được kiểm tra bằng = NULL

Không dùng:

```sql
WHERE discount_pct = NULL
```

vì kết quả so sánh với NULL là UNKNOWN, không xác định bằng một giá trị SQL. Dùng:

```sql
WHERE discount_pct IS NULL
```

và ngược lại `IS NOT NULL`.

### 15.7. Giá trị cố định và kiểu dữ liệu

Nếu cột `price` là `NUMERIC`, hãy bind giá trị numeric. Nếu cột `created_at` là `TIMESTAMPTZ`, hãy bind timestamp có timezone/instant phù hợp.

Việc tự động chuyển kiểu giữa text, timestamp, numeric và các literal có thể hoạt động trong nhiều truy vấn, nhưng **không nên dựa vào chuyển đổi mơ hồ** khi có định dạng theo locale hoặc múi giờ.

Đối với số tiền, đừng parse qua floating point nhị phân nếu yêu cầu decimal chính xác.

---

## 16. Bộ câu hỏi kiểm tra nhanh bằng SQL

Chạy các câu này trên bảng lab để tự quan sát sự khác biệt:

### 16.1. IN và NOT IN

```sql
SELECT sku
FROM query_filter_lab.products
WHERE category IN ('BOOK', 'GIFT')
ORDER BY sku;

SELECT sku
FROM query_filter_lab.products
WHERE status NOT IN ('DRAFT', 'ARCHIVED')
ORDER BY sku;
```

### 16.2. BETWEEN

```sql
SELECT sku, price
FROM query_filter_lab.products
WHERE price BETWEEN 100000 AND 300000
ORDER BY price, sku;

SELECT sku, price
FROM query_filter_lab.products
WHERE price NOT BETWEEN 100000 AND 300000
ORDER BY price, sku;
```

### 16.3. LIKE so với ILIKE

```sql
SELECT sku, product_name
FROM query_filter_lab.products
WHERE product_name LIKE 'postgresql%'
ORDER BY sku;

SELECT sku, product_name
FROM query_filter_lab.products
WHERE product_name ILIKE 'postgresql%'
ORDER BY sku;
```

### 16.4. ESCAPE

```sql
SELECT sku
FROM query_filter_lab.products
WHERE sku LIKE 'PEN!_%' ESCAPE '!';

SELECT sku, product_name
FROM query_filter_lab.products
WHERE product_name LIKE '%100!%%' ESCAPE '!';
```

### 16.5. AND, OR, ngoặc

```sql
SELECT sku, category, status, price
FROM query_filter_lab.products
WHERE status = 'ACTIVE'
  AND (
      category = 'BOOK'
      OR price < 20000
  )
ORDER BY sku;
```

Sau khi chạy, thử thêm một sản phẩm DRAFT giá 5000 **trong transaction lab** và so sánh với câu không có ngoặc:

```sql
BEGIN;

INSERT INTO query_filter_lab.products (
    sku, product_name, category, price, status,
    stock_quantity, discount_pct, created_at
)
VALUES (
    'TMP-DRAFT-01', 'Hàng thử giá rẻ', 'GIFT',
    5000, 'DRAFT', 0, NULL,
    '2026-02-15 00:00:00+00'
);

SELECT sku
FROM query_filter_lab.products
WHERE status = 'ACTIVE'
  AND (category = 'BOOK' OR price < 20000)
ORDER BY sku;

SELECT sku
FROM query_filter_lab.products
WHERE status = 'ACTIVE'
  AND category = 'BOOK'
  OR price < 20000
ORDER BY sku;

ROLLBACK;
```

Trong transaction lab, câu **không ngoặc** sẽ nhận `TMP-DRAFT-01` vì giá rẻ, trong khi câu **có ngoặc** loại nó vì status khác ACTIVE. `ROLLBACK` giúp trả bảng về trạng thái cũ sau thử nghiệm.

---

## 17. Bài tập tự luyện

### Bài 1 — Lọc tập category

Viết câu SELECT trả `sku, product_name, category` cho các sản phẩm thuộc `STATIONERY` hoặc `GIFT`. Sử dụng `IN`, sau đó viết cách tương đương bằng `OR`.

Câu hỏi: nếu truyền danh sách category rỗng từ ứng dụng, bạn sẽ xử lý như thế nào mà không sinh ra SQL `IN ()` sai cú pháp?

### Bài 2 — Mức giá có ranh giới rõ

Tìm sản phẩm giá từ 25000 đến 300000, **bao gồm hai đầu mút**.

So sánh kết quả giữa:

```sql
price BETWEEN 25000 AND 300000
```

và:

```sql
price >= 25000 AND price <= 300000
```

Tại sao `BOOK-PG-04` giá 300000 được giữ?

### Bài 3 — NOT IN với NULL

Dự đoán:

```sql
SELECT sku, discount_pct
FROM query_filter_lab.products
WHERE discount_pct NOT IN (0, 10, NULL)
ORDER BY sku;
```

Tại sao không có hàng nào trong dữ liệu lab? Viết truy vấn tìm các discount đã biết khác 0 và 10. Sau đó sửa để **bao gồm cả discount NULL** khi nghiệp vụ yêu cầu.

### Bài 4 — Tìm kiếm với LIKE

Viết pattern tìm:

1. SKU bắt đầu `BOOK-`.
2. SKU kết thúc `-01`.
3. Tên chứa `SQL` với đúng cách viết hoa/thường.
4. Tên chứa `SQL` không phân biệt hoa/thường.
5. SKU bắt đầu bằng ký tự literal `PEN_`.

Giải thích tại sao trường hợp 5 cần `ESCAPE`.

### Bài 5 — Dấu phần trăm literal

Tìm sản phẩm có tên chứa chuỗi `100%` bằng `LIKE`. Không được để `%` trong chuỗi `100%` hoạt động như wildcard.

Gợi ý: dùng `ESCAPE '!'`, phân biệt `!%` với `%`.

### Bài 6 — Lọc theo thời gian

Viết câu truy vấn lấy mọi sản phẩm được tạo trong tháng 03/2026 theo **UTC**, không bỏ sót các timestamp có phần lẻ giây.

Giải thích vì sao:

```sql
created_at BETWEEN '2026-03-01' AND '2026-03-31'
```

không phải cách tốt để lấy trọn ngày cuối tháng với TIMESTAMPTZ.

### Bài 7 — AND/OR không ngoặc

Yêu cầu:

> Sản phẩm ACTIVE và (BOOK hoặc giá dưới 20000).

Viết truy vấn có ngoặc. Sau đó viết truy vấn bỏ ngoặc và giải thích ví dụ sản phẩm DRAFT giá 5000 có thể lọt vào câu thứ hai như thế nào.

### Bài 8 — Điều kiện tồn kho NULL

Tìm:

1. Sản phẩm có stock **chắc chắn lớn hơn 0**.
2. Sản phẩm có stock bằng 0.
3. Sản phẩm chưa rõ stock (NULL).
4. Sản phẩm stock lớn hơn 0 **hoặc NULL**.

Vì sao `NOT (stock_quantity > 0)` không tương đương với “hết hàng hoặc chưa biết tồn kho”?

### Bài 9 — Nhiều điều kiện hỗn hợp

Viết truy vấn trả SKU và giá của sản phẩm:

- ACTIVE.
- Category là BOOK hoặc ACCESSORY.
- Giá từ 100000 tới 400000.
- Tên chứa `SQL`, không phân biệt hoa/thường.

Sắp xếp giá tăng rồi SKU tăng. Đếm số hàng và lý giải vì sao một số sản phẩm bị loại.

### Bài 10 — IN trên hai cột

Viết truy vấn chỉ lấy các cặp:

- `category = BOOK` và `status = ACTIVE`.
- `category = GIFT` và `status = DRAFT`.

So sánh việc dùng:

```sql
(category, status) IN (
    ('BOOK', 'ACTIVE'),
    ('GIFT', 'DRAFT')
)
```

với việc tách thành:

```sql
category IN ('BOOK','GIFT')
AND status IN ('ACTIVE','DRAFT')
```

Vì sao cách thứ hai chấp nhận thêm những tổ hợp không được yêu cầu?

### Bài 11 — Chuỗi do người dùng nhập

Ứng dụng nhận từ khóa `100%` để tìm đúng chuỗi literal trong tên sản phẩm.

Hãy trình bày:

1. Vì sao nên dùng PreparedStatement thay vì ghép chuỗi SQL.
2. Vì sao bind parameter **không tự làm `%` mất nghĩa wildcard**.
3. Cách escape `%`, `_` và ký tự escape do ứng dụng chọn.
4. Cách thêm dấu `%` ngoài cùng khi muốn tìm chuỗi con.

### Bài 12 — Chọn index theo workload

Một bảng lớn có ba truy vấn phổ biến:

1. `WHERE category IN (...) AND price BETWEEN ...`.
2. `WHERE sku LIKE 'BOOK-%'`.
3. `WHERE product_name ILIKE '%postgresql%'`.

Hãy đề xuất index B-tree/composite, operator class pattern hoặc trigram index đáng cân nhắc. Giải thích vì sao không nên hứa planner chắc chắn dùng index trước khi quan sát `EXPLAIN` trên dữ liệu thực tế.

---

## 18. Checklist viết bộ lọc đúng và dễ bảo trì

| Câu hỏi | Điều cần kiểm tra |
| --- | --- |
| Bộ lọc là tập giá trị chính xác? | Dùng `IN` hoặc `= ANY`, không nhầm với LIKE. |
| Có thể có NULL trong danh sách/subquery không? | Đặc biệt cẩn thận với `NOT IN`. |
| Cột được lọc có nullable không? | Dùng `IS NULL`/`IS NOT NULL` nếu cần. |
| Khoảng số có gồm hai đầu không? | `BETWEEN` gồm cả hai đầu; xác thực min/max. |
| Khoảng thời gian có chứa giờ/phút/giây không? | Ưu tiên khoảng nửa mở `>= start AND < end`. |
| Múi giờ của khoảng là gì? | Chọn mốc UTC/giờ địa phương rõ ràng. |
| Cần tìm tiền tố, hậu tố hay chuỗi con? | Đặt `%` đúng vị trí trong pattern. |
| Có ký tự `%` hoặc `_` literal trong từ khóa? | Dùng `ESCAPE` và escape pattern đúng. |
| Có cần không phân biệt hoa/thường không? | Cân nhắc `ILIKE`. |
| Có cần tìm không dấu Unicode không? | ILIKE không tự giải quyết; cần normalize/search riêng. |
| Có trộn AND và OR không? | Dùng ngoặc biểu đạt từng nhóm nghiệp vụ. |
| Có dùng NOT với điều kiện nullable không? | UNKNOWN vẫn UNKNOWN; không tự gồm NULL. |
| Dữ liệu lọc lấy từ request? | Bind parameter, whitelist identifier, giới hạn độ dài/list. |
| Có phân trang không? | Chọn `ORDER BY` ổn định, kết hợp LIMIT/OFFSET hoặc keyset phù hợp. |
| Có query chậm không? | Xem `EXPLAIN (ANALYZE, BUFFERS)` trên SELECT thử nghiệm. |
| Có nên tạo index mới không? | Cân nhắc selectivity, collation, pattern, chi phí ghi. |
| Có kiểm thử dữ liệu biên không? | Giá bằng min/max, NULL, chuỗi rỗng, case, ký tự %/_ và mốc tháng. |

## Kết luận

`IN`, `BETWEEN`, `LIKE` và `ILIKE` là những công cụ nền tảng để lọc dữ liệu PostgreSQL:

- **`IN`** diễn đạt tập giá trị chính xác; đặc biệt tránh hiểu sai `NOT IN` khi danh sách hoặc subquery chứa `NULL`.
- **`BETWEEN`** gồm cả hai đầu mút; khi lọc `TIMESTAMP/TIMESTAMPTZ` theo ngày hoặc tháng, thường nên dùng khoảng **nửa mở** để tránh bỏ sót thời điểm cuối kỳ.
- **`LIKE`** tìm chuỗi bằng pattern với `%` và `_`; dùng `ESCAPE` khi cần tìm chính các ký tự đại diện ấy.
- **`ILIKE`** giúp tìm không phân biệt chữ hoa/thường theo quy tắc PostgreSQL, nhưng không tự giải quyết tìm không dấu hoặc full-text search.
- **`AND`, `OR`, `NOT`** cần được ghép có chủ đích, dùng dấu ngoặc và hiểu logic `NULL` để không trả sai kết quả.
- Khi dữ liệu lớn, **index và kế hoạch truy vấn** mới quyết định cách PostgreSQL thực thi, không chỉ hình thức ngắn gọn của câu SQL.

Một bộ lọc tốt phải đúng ý nghĩa nghiệp vụ, xử lý rõ ràng giá trị thiếu, an toàn với dữ liệu người dùng và có khả năng quan sát hiệu năng. Những nguyên tắc đó giúp bạn xây dựng các trang danh sách, báo cáo và API tìm kiếm chính xác, dễ mở rộng và dễ bảo trì trong PostgreSQL.
