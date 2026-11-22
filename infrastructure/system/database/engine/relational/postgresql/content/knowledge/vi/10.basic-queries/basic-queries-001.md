# SELECT, danh sách cột, bí danh và biểu thức trong PostgreSQL

Khi làm việc với PostgreSQL, câu lệnh `SELECT` thường là điểm bắt đầu của mọi thao tác đọc dữ liệu: lấy danh sách sản phẩm, hiển thị một đơn hàng, tính giá bán sau giảm giá, trình bày nhãn dễ hiểu cho báo cáo hoặc biến dữ liệu thô thành kết quả mà ứng dụng Java có thể sử dụng. Muốn viết truy vấn tốt, không chỉ cần biết `SELECT * FROM ...` mà còn phải hiểu **danh sách biểu thức được chọn (*select list*)**, **tên cột đầu ra**, **bí danh (*alias*)** và cách PostgreSQL xác định kiểu của từng biểu thức.

Ví dụ, cùng một bảng có `unit_price`, `stock_quantity` và `discount_pct`, ta có thể trả về:

```sql
SELECT
    product_name AS product,
    unit_price AS listed_price,
    ROUND(
        unit_price * (1 - COALESCE(discount_pct, 0) / 100),
        2
    ) AS discounted_price,
    unit_price * stock_quantity AS inventory_value
FROM select_lab.products;
```

Truy vấn trên không tạo thêm bốn cột mới trong bảng. Nó **tạo bốn cột trong kết quả truy vấn**, trong đó hai cột là giá trị được tính từ các cột nguồn. Bài học này giúp phân biệt rõ dữ liệu đã lưu và giá trị chỉ tồn tại trong kết quả `SELECT`.

Mục tiêu sau bài học:

1. Viết đúng cú pháp `SELECT` với danh sách cột rõ ràng, `*` và biểu thức không cần `FROM`.
2. Hiểu cột nguồn, tên đầu ra và bí danh có hoặc không có `AS`.
3. Dùng biểu thức số học, văn bản, ngày tháng, boolean, hàm, `CASE`, `COALESCE` và ép kiểu.
4. Xử lý đúng `NULL`, kiểu dữ liệu và những biểu thức có thể gây lỗi.
5. Biết bí danh được phép tham chiếu ở `ORDER BY`, `GROUP BY` và vì sao không dùng trực tiếp trong `WHERE`.
6. Phân biệt `SELECT`, `DISTINCT`, biểu thức tổng hợp và những giới hạn của thứ tự hàng.
7. Đọc lỗi thường gặp và lựa chọn cách viết truy vấn ổn định cho ứng dụng thực tế.

Các ví dụ dùng PostgreSQL hiện đại và tập trung vào cú pháp SQL được hỗ trợ rộng rãi. Những tính năng đặc thù được ghi chú khi cần; hãy xác nhận phiên bản PostgreSQL Server nếu môi trường vận hành khác với máy học.

## 1. Hình dạng cơ bản của SELECT

Một câu `SELECT` đơn giản thường có dạng:

```sql
SELECT
    bieu_thuc_1 [AS bi_danh_1],
    bieu_thuc_2 [AS bi_danh_2],
    ...
FROM ten_schema.ten_bang
WHERE dieu_kien
ORDER BY cot_sap_xep
LIMIT so_hang;
```

Trong ví dụ khái quát này, các ký hiệu `[ ... ]` chỉ thành phần tùy chọn, dấu `...` là chỗ thay thế chứ không phải mã SQL hoàn chỉnh để chạy nguyên văn.

Các mệnh đề có vai trò khác nhau:

| Thành phần | Vai trò |
| --- | --- |
| `SELECT` | Xác định **những cột hoặc biểu thức** được trả về. |
| Danh sách biểu thức | Có thể gồm tên cột, hằng số, phép tính, lời gọi hàm, `CASE` hoặc các biểu thức khác. |
| `AS alias` | Đặt tên đầu ra cho biểu thức/cột, không tự đổi tên cột trong bảng. |
| `FROM` | Chỉ định nguồn các hàng, thường là bảng, view, phép JOIN hoặc truy vấn con. |
| `WHERE` | Lọc hàng dựa trên điều kiện trước khi tạo kết quả chọn cuối cùng theo ngữ nghĩa SQL. |
| `GROUP BY` | Gom các hàng thành nhóm khi dùng tổng hợp. |
| `HAVING` | Lọc các nhóm sau tổng hợp. |
| `ORDER BY` | Quy định cách sắp xếp hàng đầu ra. |
| `LIMIT` và `OFFSET` | Giới hạn/định vị một phần kết quả; thường dùng với `ORDER BY` ổn định. |

Chưa cần hiểu mọi mệnh đề để bắt đầu. Hãy tập trung vào **phần sau `SELECT` và trước `FROM`**: đó là danh sách biểu thức mà PostgreSQL sẽ đưa thành các cột đầu ra.

### 1.1. SELECT trả về một quan hệ kết quả

Truy vấn:

```sql
SELECT
    product_id,
    product_name,
    unit_price
FROM select_lab.products;
```

trả về một tập các hàng có **ba cột**, không nhất thiết là toàn bộ cột của bảng. Nếu bảng có thêm `created_at` hoặc `is_active`, chúng không tự xuất hiện trong kết quả trên.

**Số cột đầu ra** do danh sách `SELECT` quy định. **Số hàng đầu ra** do nguồn dữ liệu và các mệnh đề như `WHERE`, `GROUP BY`, `DISTINCT` hoặc `LIMIT` ảnh hưởng.

### 1.2. SQL không bảo đảm thứ tự hàng nếu thiếu ORDER BY

```sql
SELECT product_id, product_name
FROM select_lab.products;
```

có thể hiển thị theo thứ tự ID tăng dần trong một lần thử nhưng không có cam kết sẽ giữ nguyên. PostgreSQL có thể thay đổi kế hoạch quét, sử dụng index khác hoặc thực thi song song. Muốn kết quả có thứ tự cụ thể:

```sql
SELECT product_id, product_name
FROM select_lab.products
ORDER BY product_id;
```

Đừng nhầm **thứ tự các cột trong select list** (được xác định bởi cách viết) với **thứ tự các hàng** (cần `ORDER BY`).

## 2. Chuẩn bị dữ liệu thực hành

Để các ví dụ tự chứa, tạo schema `select_lab` và bảng `products`. Hãy chạy trên PostgreSQL lab riêng, không trên database production.

```sql
CREATE SCHEMA IF NOT EXISTS select_lab;

CREATE TABLE select_lab.products (
    product_id bigint PRIMARY KEY,
    sku text NOT NULL UNIQUE,
    product_name text NOT NULL,
    category_code text NOT NULL,
    unit_price numeric(12, 2) NOT NULL
        CHECK (unit_price >= 0),
    stock_quantity integer NOT NULL
        CHECK (stock_quantity >= 0),
    discount_pct numeric(5, 2)
        CHECK (discount_pct BETWEEN 0 AND 100),
    is_active boolean NOT NULL DEFAULT true,
    created_at date NOT NULL
);
```

Thêm dữ liệu:

```sql
INSERT INTO select_lab.products (
    product_id, sku, product_name, category_code,
    unit_price, stock_quantity, discount_pct,
    is_active, created_at
)
VALUES
    (101, 'BOOK-SQL', 'Sách SQL thực hành', 'books',
     180000.00, 12, 10.00, true, DATE '2026-10-01'),
    (102, 'BOOK-PG', 'PostgreSQL căn bản', 'books',
     240000.00, 5, NULL, true, DATE '2026-10-03'),
    (103, 'PEN-BLUE', 'Bút xanh', 'stationery',
     12000.00, 0, 0.00, true, DATE '2026-10-04'),
    (104, 'NOTE-A5', 'Sổ A5', 'stationery',
     45000.00, 20, 5.00, true, DATE '2026-10-05'),
    (105, 'BAG-01', 'Túi đựng sách', 'accessories',
     95000.00, 3, 15.00, false, DATE '2026-10-06'),
    (106, 'MUG-01', 'Cốc gốm', 'accessories',
     110000.00, 8, NULL, true, DATE '2026-10-07');
```

Tập dữ liệu ví dụ:

| ID | SKU | Tên sản phẩm | Nhóm | Giá | Tồn | Giảm (%) | Hoạt động |
| ---: | --- | --- | --- | ---: | ---: | ---: | --- |
| 101 | BOOK-SQL | Sách SQL thực hành | books | 180000 | 12 | 10 | true |
| 102 | BOOK-PG | PostgreSQL căn bản | books | 240000 | 5 | NULL | true |
| 103 | PEN-BLUE | Bút xanh | stationery | 12000 | 0 | 0 | true |
| 104 | NOTE-A5 | Sổ A5 | stationery | 45000 | 20 | 5 | true |
| 105 | BAG-01 | Túi đựng sách | accessories | 95000 | 3 | 15 | false |
| 106 | MUG-01 | Cốc gốm | accessories | 110000 | 8 | NULL | true |

Ở đây `discount_pct = NULL` nghĩa là chưa có giá trị phần trăm giảm được ghi nhận, **không mặc nhiên có nghĩa đang giảm 0%**. Khi thực hành tính giá, bài sẽ dùng một giả định nghiệp vụ minh họa rằng `NULL` được tạm coi là 0%; hệ thống thật cần quyết định ngữ nghĩa này.

Các câu `CREATE TABLE` và `INSERT` chỉ cần chạy một lần trên schema trống. Nếu lặp lại `INSERT` với cùng `product_id` hoặc `sku`, PostgreSQL sẽ báo vi phạm khóa chính/khóa duy nhất.

## 3. SELECT không bắt buộc có FROM

PostgreSQL cho phép `SELECT` chỉ gồm một hoặc nhiều biểu thức mà không lấy hàng từ một bảng.

```sql
SELECT 1;
```

```sql
SELECT
    10 + 20 AS sum_result,
    3 * 7 AS multiply_result,
    'Hello PostgreSQL' AS greeting;
```

Kết quả:

| sum_result | multiply_result | greeting |
| ---: | ---: | --- |
| 30 | 21 | Hello PostgreSQL |

Ví dụ khác:

```sql
SELECT
    CURRENT_DATE AS today,
    CURRENT_TIMESTAMP AS current_timestamp_value,
    100::numeric / 4 AS quarter_value;
```

Khi không có `FROM`, câu `SELECT` cơ bản trả về một hàng chứa kết quả các biểu thức. Giá trị ngày giờ phụ thuộc thời điểm và múi giờ phiên làm việc, vì vậy kết quả ở máy của bạn có thể khác ngày minh họa của người khác.

### Khi nào SELECT không FROM hữu ích?

- Kiểm tra cú pháp của hàm và phép toán.
- Thử ép kiểu, định dạng chuỗi hoặc phép toán ngày.
- Hỏi giá trị thiết lập phiên hiện tại:

```sql
SELECT
    current_database() AS database_name,
    current_user AS role_name,
    current_setting('server_version') AS server_version;
```

- Xây một dòng kết quả chứa tham số hoặc giá trị khởi tạo.

Không nên dùng `SELECT` như một cách thay thế cho các thao tác thay đổi bảng. Một biểu thức tính toán chỉ tạo **giá trị đầu ra**, không tự ghi dữ liệu trở lại bảng.

## 4. Danh sách cột: chọn rõ những gì cần trả về

Một select list có thể chứa một hoặc nhiều mục, ngăn cách bằng dấu phẩy:

```sql
SELECT
    product_id,
    sku,
    product_name
FROM select_lab.products
ORDER BY product_id;
```

Bạn có thể đổi thứ tự cột:

```sql
SELECT
    product_name,
    product_id,
    sku
FROM select_lab.products
ORDER BY product_id;
```

Truy vấn thứ hai vẫn đọc các trường đó nhưng thứ tự cột trong kết quả là tên sản phẩm, ID, rồi SKU. Thứ tự cột trong bảng vật lý không bắt buộc là thứ tự đầu ra.

### 4.1. Một cột có thể được chọn nhiều lần

```sql
SELECT
    product_name,
    product_name AS display_name
FROM select_lab.products
WHERE product_id = 101;
```

Kết quả có hai cột chứa cùng một giá trị nhưng tên đầu ra khác nhau:

| product_name | display_name |
| --- | --- |
| Sách SQL thực hành | Sách SQL thực hành |

SQL cho phép các biểu thức trùng lặp trong select list. Tuy nhiên, lặp lại dữ liệu thường không cần thiết trừ khi phục vụ định dạng, so sánh hoặc một hợp đồng API cụ thể.

### 4.2. Dấu phẩy cuối và lỗi cú pháp

Ví dụ sai:

```sql
-- Sai: dấu phẩy cuối danh sách cột.
-- SELECT product_id, product_name,
-- FROM select_lab.products;
```

Đừng nhầm dấu phẩy phân cách **các biểu thức đầu ra** với dấu phẩy trong danh sách đối số của hàm:

```sql
SELECT
    ROUND(unit_price, 0) AS rounded_price,
    COALESCE(discount_pct, 0) AS effective_discount
FROM select_lab.products;
```

Trong `ROUND(unit_price, 0)`, dấu phẩy phân cách hai đối số hàm; còn dấu phẩy sau `AS rounded_price` phân cách hai biểu thức của select list.

## 5. SELECT *: khi nào tiện, khi nào nên tránh?

Ký hiệu `*` đại diện cho **toàn bộ cột của nguồn hàng** trong ngữ cảnh truy vấn.

```sql
SELECT *
FROM select_lab.products
ORDER BY product_id;
```

Với bảng lab, kết quả gồm chín cột đã khai báo: `product_id`, `sku`, `product_name`, `category_code`, `unit_price`, `stock_quantity`, `discount_pct`, `is_active` và `created_at`.

### 5.1. Ưu điểm

- Khám phá nhanh một bảng chưa quen trong môi trường học tập.
- Xem dữ liệu khi debug ngắn hạn.
- Kiểm tra nhanh kết quả sau khi thêm dữ liệu thử.

### 5.2. Hạn chế khi dùng trong ứng dụng thật

| Rủi ro | Tác động |
| --- | --- |
| Lấy cột không cần | Tăng lượng dữ liệu truyền, xử lý hoặc serialize. |
| Schema thay đổi | Thêm cột có thể khiến hình dạng kết quả `SELECT *` thay đổi. |
| Dữ liệu nhạy cảm | Vô tình đưa thông tin không cần thiết tới tầng ứng dụng/API. |
| Join nhiều bảng | Có thể tạo nhiều cột cùng tên, gây khó xử lý ResultSet/DTO. |
| Hợp đồng API không rõ | Khó biết dịch vụ nào đang phụ thuộc cột nào. |
| Dữ liệu JSONB/text lớn | Có thể đọc và truyền payload lớn dù màn hình chỉ cần ID/tên. |

Trong API và truy vấn chạy thường xuyên, nên viết các cột cần thiết:

```sql
SELECT product_id, sku, product_name, unit_price
FROM select_lab.products
WHERE is_active = true
ORDER BY product_id;
```

Sử dụng `SELECT *` khi debug không phải lỗi, nhưng đưa nó thành giao diện dữ liệu lâu dài thường làm truy vấn kém rõ và khó kiểm soát hơn.

### 5.3. table_alias.*

Khi dùng bí danh bảng, có thể chọn toàn bộ cột của một nguồn cụ thể:

```sql
SELECT p.*
FROM select_lab.products AS p
WHERE p.category_code = 'books';
```

`p.*` mở rộng thành các cột của nguồn `p`. Trong truy vấn có nhiều bảng, `p.*` giúp phân biệt với `*` lấy các cột thuộc tất cả nguồn hiện diện trong select list.

Tuy vậy, `p.*` vẫn mang hạn chế của wildcard khi schema bảng thay đổi. Nếu chỉ cần ba cột, viết rõ cả ba vẫn dễ bảo trì hơn.

## 6. Bí danh cột: AS đổi tên kết quả, không đổi schema

Bí danh của cột là tên do truy vấn đặt cho một biểu thức đầu ra.

```sql
SELECT
    product_id AS id,
    product_name AS name,
    unit_price AS price
FROM select_lab.products
WHERE product_id = 101;
```

Kết quả:

| id | name | price |
| ---: | --- | ---: |
| 101 | Sách SQL thực hành | 180000.00 |

Các tên `id`, `name` và `price` chỉ tồn tại trong kết quả truy vấn này. Bảng `select_lab.products` vẫn có tên cột gốc như `product_name` và `unit_price`.

### 6.1. Có thể bỏ AS, nhưng nên dùng khi đặt bí danh cột

Hai cách sau có thể tương đương:

```sql
SELECT product_name AS display_name
FROM select_lab.products;
```

```sql
SELECT product_name display_name
FROM select_lab.products;
```

Trong những câu đơn giản, PostgreSQL cho phép bỏ `AS`. Tuy nhiên, đặt `AS` rõ ràng thường giúp người đọc phân biệt **tên đầu ra** với phần tiếp theo của biểu thức, đặc biệt khi select list dài.

### 6.2. Bí danh cho biểu thức là thói quen tốt

```sql
SELECT
    product_id,
    unit_price * stock_quantity AS inventory_value
FROM select_lab.products;
```

Không có alias, PostgreSQL sẽ tự suy ra một tên đầu ra khi có thể hoặc hiển thị tên mặc định như `?column?` cho một số biểu thức. Tên tự sinh không nên được xem là hợp đồng ổn định cho Java DTO hoặc báo cáo.

### 6.3. Bí danh có dấu cách hoặc chữ hoa

Muốn đặt tên hiển thị bằng tiếng Việt:

```sql
SELECT
    product_name AS "Tên sản phẩm",
    unit_price AS "Giá niêm yết"
FROM select_lab.products
ORDER BY product_id;
```

Dấu nháy kép `"..."` bao quanh **identifier** của SQL. Nó cho phép bí danh có khoảng trắng, dấu tiếng Việt hoặc chữ hoa được giữ theo ý muốn.

Ngược lại:

```sql
SELECT product_name AS 'Tên sản phẩm'
FROM select_lab.products;
```

không phải cách đặt alias hợp lệ: dấu nháy đơn là ký hiệu của **chuỗi ký tự SQL**, không phải cách quote identifier.

Trong truy vấn phục vụ API, thường nên dùng alias kỹ thuật ổn định như `product_name` hoặc `discounted_price`; tên hiển thị bằng ngôn ngữ người dùng nên được quyết định ở tầng giao diện khi cần đa ngôn ngữ.

## 7. Phân biệt tên cột, bí danh bảng và schema

Một bảng có thể được tham chiếu bằng tên đầy đủ:

```sql
SELECT select_lab.products.product_name
FROM select_lab.products;
```

Nhưng cách này dài và không thuận tiện khi query phức tạp. Ta thường đặt **bí danh bảng**:

```sql
SELECT
    p.product_id,
    p.product_name,
    p.unit_price
FROM select_lab.products AS p
WHERE p.is_active = true;
```

Ở đây:

- `select_lab`: tên schema.
- `products`: tên bảng trong schema đó.
- `p`: bí danh của nguồn hàng trong truy vấn.
- `p.product_name`: cột `product_name` của nguồn `p`.
- `AS p`: đặt bí danh **bảng**, không phải bí danh cột.

Sau khi đặt alias bảng `p`, nên sử dụng `p.column_name` nhất quán trong các phần liên quan của query, đặc biệt với JOIN hoặc các tên cột dễ bị trùng.

### 7.1. Hai loại alias có phạm vi khác nhau

```sql
SELECT
    p.product_name AS display_name,
    p.unit_price AS price
FROM select_lab.products AS p;
```

`p` là tên dùng **để tham chiếu nguồn dữ liệu** trong query. `display_name` và `price` là **tên đầu ra**. Không nên nhầm rằng đặt `AS display_name` khiến biểu thức `p.display_name` trở thành một cột có sẵn.

### 7.2. Cột mơ hồ khi có nhiều nguồn

Ví dụ kết hợp bảng sản phẩm với bảng tra cứu danh mục tạo tại chỗ bằng `VALUES`:

```sql
SELECT
    p.product_id,
    p.product_name,
    c.category_label
FROM select_lab.products AS p
JOIN (
    VALUES
        ('books', 'Sách'),
        ('stationery', 'Văn phòng phẩm'),
        ('accessories', 'Phụ kiện')
) AS c(category_code, category_label)
    ON p.category_code = c.category_code
ORDER BY p.product_id;
```

`AS c(category_code, category_label)` đặt **tên cho nguồn bảng dẫn xuất** và các cột của nó. Cả `p` và `c` đều có `category_code`. Nếu viết:

```sql
-- Sai vì category_code xuất hiện ở cả p và c:
-- SELECT category_code
-- FROM select_lab.products AS p
-- JOIN (VALUES ('books', 'Sách')) AS c(category_code, category_label)
--   ON p.category_code = c.category_code;
```

PostgreSQL có thể báo `column reference "category_code" is ambiguous`. Cách sửa là ghi `p.category_code` hoặc `c.category_code` đúng ý định.

**Nguyên tắc:** dùng `table_alias.column_name` để tăng độ rõ ràng khi nhiều nguồn có khả năng chứa các cột cùng tên.

## 8. Identifier, chữ hoa/chữ thường và dấu nháy kép

PostgreSQL phân biệt:

1. **Identifier không quote**, ví dụ `product_name` hoặc `Product_Name`.
2. **Identifier có quote**, ví dụ `"Product_Name"` hoặc `"Tên sản phẩm"`.
3. **String literal**, ví dụ `'paid'` hay `'Sách'`.

Identifier không quote được PostgreSQL chuyển thành chữ thường trong quá trình phân tích cú pháp:

```sql
SELECT product_name
FROM select_lab.products;

SELECT PRODUCT_NAME
FROM select_lab.products;
```

Hai cách trên đều tìm cột `product_name` trong bảng lab.

Ngược lại:

```sql
-- Thường báo không có cột "Product_Name" trong bảng lab:
-- SELECT "Product_Name"
-- FROM select_lab.products;
```

Dấu nháy kép yêu cầu tìm identifier đúng chữ hoa/chữ thường và nội dung trong quote.

### 8.1. Đặt alias CamelCase

```sql
SELECT product_name AS "productName"
FROM select_lab.products;
```

Tên đầu ra đúng là `productName`. Còn:

```sql
SELECT product_name AS productName
FROM select_lab.products;
```

thường cho tên đầu ra `productname` do identifier không quote được gập xuống chữ thường.

Khi thiết kế mapping Java, ORM hoặc serialization cần cột theo tên chính xác, việc quote alias có thể hữu ích. Nhưng nếu toàn bộ hệ thống dùng `snake_case` không quote, việc quản lý schema thường đơn giản hơn.

### 8.2. Keyword và tên khó đọc

Tên bảng/cột trùng từ khóa SQL hoặc có khoảng trắng bắt buộc phải được xử lý bằng quote phù hợp. Tuy nhiên, không nên cố tình đặt cột tên `"select"` hoặc `"Order ID"` nếu không có lý do rất cụ thể. Dùng tên rõ nghĩa, nhất quán và dễ viết giúp giảm lỗi truy vấn.

### 8.3. String literal không thay thế identifier

```sql
SELECT
    'product_name' AS literal_text,
    product_name AS column_value
FROM select_lab.products
WHERE product_id = 101;
```

Kết quả:

| literal_text | column_value |
| --- | --- |
| product_name | Sách SQL thực hành |

`'product_name'` là chuỗi cố định được trả cho mỗi hàng; `product_name` là tên cột được đọc từ bảng.

## 9. Biểu thức số học trong danh sách SELECT

Một **biểu thức** có thể kết hợp cột, hằng số, toán tử và hàm để tạo giá trị mới cho mỗi hàng.

Ví dụ lượng tiền hàng đang tồn theo giá niêm yết:

```sql
SELECT
    product_id,
    product_name,
    unit_price,
    stock_quantity,
    unit_price * stock_quantity AS inventory_value
FROM select_lab.products
ORDER BY product_id;
```

Với sản phẩm 101, `180000.00 * 12 = 2160000.00`. Với sản phẩm 103, số lượng tồn là 0 nên giá trị tồn tính theo công thức bằng 0.

### 9.1. Các toán tử thường dùng

| Toán tử | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| `+` | Cộng | `unit_price + 1000` |
| `-` | Trừ hoặc đổi dấu | `unit_price - 5000` |
| `*` | Nhân | `unit_price * stock_quantity` |
| `/` | Chia | `unit_price / 2` |
| `%` | Lấy phần dư với kiểu toán hạng phù hợp | `stock_quantity % 2` |
| `( )` | Quy định ưu tiên tính toán | `(unit_price + 1000) * 2` |

Phép nhân/chia thường có độ ưu tiên cao hơn cộng/trừ. Dùng ngoặc khi biểu thức nghiệp vụ có nhiều bước:

```sql
SELECT
    10 + 2 * 3 AS without_parentheses,
    (10 + 2) * 3 AS with_parentheses;
```

Kết quả: `16` và `36`.

### 9.2. Tính giá sau giảm giá

Giả định nghiệp vụ cho ví dụ: nếu `discount_pct` bằng SQL `NULL`, tạm tính như 0% giảm.

```sql
SELECT
    product_id,
    product_name,
    unit_price,
    discount_pct,
    ROUND(
        unit_price * (1 - COALESCE(discount_pct, 0) / 100),
        2
    ) AS discounted_price
FROM select_lab.products
ORDER BY product_id;
```

Kết quả ví dụ cho một số hàng:

| product_id | unit_price | discount_pct | discounted_price |
| ---: | ---: | ---: | ---: |
| 101 | 180000.00 | 10.00 | 162000.00 |
| 102 | 240000.00 | NULL | 240000.00 |
| 104 | 45000.00 | 5.00 | 42750.00 |
| 105 | 95000.00 | 15.00 | 80750.00 |

`COALESCE(discount_pct, 0)` chỉ quyết định giá trị **dùng trong phép tính**; nó không làm thay đổi cột `discount_pct` trong bảng.

Nếu nghiệp vụ hiểu NULL là “chưa đủ thông tin để tính giá”, **không nên mặc nhiên thay bằng 0**. Khi đó có thể trả `NULL` hoặc trạng thái cần bổ sung dữ liệu.

### 9.3. Chia số nguyên và chia số thập phân

PostgreSQL chọn kiểu kết quả dựa trên kiểu toán hạng:

```sql
SELECT
    1 / 2 AS integer_division,
    1.0 / 2 AS numeric_division,
    1::numeric / 2 AS explicit_numeric_division;
```

Kết quả theo ý nghĩa:

| integer_division | numeric_division | explicit_numeric_division |
| ---: | ---: | ---: |
| 0 | 0.5 | 0.5 |

Khi cả hai toán hạng là integer, `/` dùng phép chia số nguyên với kết quả bị cắt phần thập phân. Đừng tính tỷ lệ bằng `successful_count / total_count` nếu cả hai là integer mà mong có kết quả 0.75; hãy ép ít nhất một toán hạng sang kiểu thập phân thích hợp.

```sql
SELECT
    3::numeric / 4 AS success_ratio;
```

### 9.4. Chia cho 0

```sql
-- Không chạy nếu muốn tránh lỗi division by zero:
-- SELECT 100 / 0;
```

Nếu mẫu số có thể bằng 0, có thể dùng `NULLIF`:

```sql
SELECT
    100::numeric / NULLIF(0, 0) AS safe_result;
```

`NULLIF(0, 0)` trả SQL NULL, nên phép chia có kết quả NULL thay vì lỗi chia cho 0 trong trường hợp này. Cần quyết định tiếp liệu kết quả NULL nên hiển thị là “không xác định”, 0 hay thông báo nghiệp vụ khác.

## 10. Biểu thức và kiểu dữ liệu: PostgreSQL không bỏ qua type

Cột trong bảng có kiểu riêng, ví dụ:

- `product_id`: `bigint`.
- `sku`: `text`.
- `unit_price`: `numeric(12,2)`.
- `stock_quantity`: `integer`.
- `is_active`: `boolean`.
- `created_at`: `date`.

Khi kết hợp các cột, PostgreSQL xác định kiểu đầu ra dựa trên toán tử, hàm và ép kiểu.

### 10.1. Kiểm tra kiểu của biểu thức

```sql
SELECT
    pg_typeof(unit_price) AS price_type,
    pg_typeof(stock_quantity) AS stock_type,
    pg_typeof(unit_price * stock_quantity) AS value_type
FROM select_lab.products
WHERE product_id = 101;
```

`pg_typeof` trả kiểu PostgreSQL của biểu thức. Trong ví dụ, `unit_price * stock_quantity` có kiểu số thích hợp cho phép tính với `numeric`.

### 10.2. CAST và toán tử ::

PostgreSQL cho phép ép kiểu theo cú pháp tiêu chuẩn `CAST(... AS ...)`:

```sql
SELECT
    CAST(12 AS numeric) / 5 AS ratio,
    CAST('2026-10-01' AS date) AS sample_date;
```

Và cú pháp rút gọn phổ biến của PostgreSQL dùng `::`:

```sql
SELECT
    12::numeric / 5 AS ratio,
    '2026-10-01'::date AS sample_date;
```

Hai cách được dùng trong nhiều trường hợp tương đương; `CAST` là cách biểu đạt SQL chuẩn, còn `::` ngắn gọn và rất phổ biến trong PostgreSQL.

### 10.3. Không ép kiểu tùy tiện chỉ để “hết lỗi”

Ví dụ:

```sql
SELECT ('250000'::text)::numeric AS amount;
```

Cú pháp hợp lệ vì chuỗi có dạng số. Nhưng:

```sql
-- Chuỗi không phải số nên chuyển kiểu sẽ lỗi:
-- SELECT 'hai_tram'::numeric;
```

Nếu dữ liệu nhập không ổn định, nên xác thực và làm sạch ở điểm nhập dữ liệu. Việc dùng `::numeric` liên tục trên một cột text chứa tiền vừa tốn công chuyển đổi vừa có nguy cơ gặp giá trị sai định dạng.

### 10.4. Cột alias không tự quy định kiểu

```sql
SELECT unit_price AS price
FROM select_lab.products;
```

Bí danh `price` chỉ thay **tên đầu ra**, không biến `numeric` thành `text` hay `double precision`. Nếu cần kiểu khác, dùng biểu thức ép kiểu rõ ràng:

```sql
SELECT
    unit_price::text AS price_text,
    unit_price AS price_numeric
FROM select_lab.products;
```

Trong Java, kiểu dữ liệu trả về ảnh hưởng đến cách JDBC đọc giá trị, ví dụ `numeric` thường được xử lý phù hợp bằng `BigDecimal` khi tính tiền, thay vì chuyển số tiền sang chuỗi chỉ để hiển thị.

## 11. Chuỗi ký tự: nối, định dạng và biến đổi

Biểu thức đầu ra cũng có thể kết hợp dữ liệu văn bản.

### 11.1. Toán tử nối chuỗi ||

```sql
SELECT
    sku || ' - ' || product_name AS display_label
FROM select_lab.products
ORDER BY product_id;
```

Một hàng kết quả:

```text
BOOK-SQL - Sách SQL thực hành
```

`||` là toán tử nối chuỗi phổ biến trong PostgreSQL. Nếu một toán hạng cần nối là SQL NULL, kết quả nối theo cách này thường trở thành SQL NULL.

### 11.2. concat và concat_ws

```sql
SELECT
    concat(sku, ' - ', product_name) AS by_concat,
    concat_ws(' - ', sku, product_name, category_code)
        AS with_separator
FROM select_lab.products
WHERE product_id = 101;
```

`concat` chuyển các đối số thành văn bản và bỏ qua SQL NULL trong những trường hợp phù hợp. `concat_ws` dùng đối số đầu làm dấu phân cách và bỏ qua các đối số NULL. Điều này có thể thuận tiện hơn chuỗi các phép `||` khi dữ liệu có phần tùy chọn.

Tuy nhiên, **bỏ qua NULL** chỉ thích hợp nếu nghiệp vụ muốn loại một phần nhãn khi thiếu thông tin. Không dùng nó để che dữ liệu bắt buộc đang bị thiếu.

### 11.3. Một số hàm text phổ biến

```sql
SELECT
    product_name,
    upper(product_name) AS uppercase_name,
    lower(sku) AS lowercase_sku,
    length(product_name) AS name_length,
    trim('   PostgreSQL   ') AS trimmed_example
FROM select_lab.products
WHERE product_id = 101;
```

Lưu ý:

- `upper` và `lower` có hành vi xử lý ký tự tùy quy tắc locale/collation của môi trường.
- `length(text)` đo số ký tự theo ngữ nghĩa PostgreSQL, không phải luôn là số bytes của UTF-8.
- `trim` loại những ký tự ở đầu/cuối theo cách gọi được chọn, không tự chỉnh sửa giá trị đang lưu trong bảng.

### 11.4. Dấu nháy đơn trong string literal

Muốn chứa dấu `'` trong một chuỗi SQL, thường viết thành hai dấu liên tiếp:

```sql
SELECT 'It''s a PostgreSQL example' AS sample_text;
```

Đừng nhầm dấu nháy đơn cho string literal với dấu nháy kép bao identifier. Đặc biệt trong Java, đừng ghép trực tiếp đầu vào người dùng vào SQL; dùng parameter binding trong `PreparedStatement` hoặc API an toàn tương ứng của framework.

## 12. SQL NULL và kết quả biểu thức

`NULL` không phải một số 0, chuỗi rỗng hay giá trị “false”. Nó biểu diễn **không có giá trị SQL được biết** trong ngữ cảnh biểu thức đó.

### 12.1. Phép tính với NULL

```sql
SELECT
    100 + NULL::integer AS sum_with_null,
    'abc' || NULL::text AS text_with_null;
```

Hai biểu thức đều trả SQL NULL. Không thể cộng 100 với một giá trị chưa biết rồi khẳng định kết quả là 100; cũng không thể tự suy ra phần chuỗi bị thiếu phải là chuỗi rỗng.

Ví dụ:

```sql
SELECT
    product_id,
    unit_price,
    discount_pct,
    unit_price * (1 - discount_pct / 100)
        AS raw_discounted_price
FROM select_lab.products
ORDER BY product_id;
```

Ở các hàng có `discount_pct IS NULL`, giá trị `raw_discounted_price` là NULL. Đây là hành vi đúng theo SQL, dù màn hình có thể muốn hiển thị cách khác.

### 12.2. COALESCE: giá trị dự phòng

`COALESCE` trả giá trị đầu tiên **khác SQL NULL** trong danh sách đối số:

```sql
SELECT
    product_id,
    discount_pct,
    COALESCE(discount_pct, 0) AS discount_for_calculation
FROM select_lab.products
ORDER BY product_id;
```

Điều kiện quan trọng: các đối số phải có kiểu dữ liệu tương thích theo quy tắc giải kiểu của PostgreSQL. Không nên trộn tùy tiện `numeric` với một chuỗi văn bản mô tả rồi mong tự chuyển kiểu:

```sql
SELECT
    COALESCE(discount_pct::text, 'Chưa khai báo')
        AS discount_display
FROM select_lab.products
ORDER BY product_id;
```

Ở đây ép sang `text` có chủ đích vì kết quả phục vụ **hiển thị**, không dùng để tính toán số học nữa.

### 12.3. NULLIF

`NULLIF(a, b)` trả SQL NULL nếu hai biểu thức bằng nhau theo điều kiện phù hợp, ngược lại trả giá trị của đối số đầu.

```sql
SELECT
    NULLIF(0, 0) AS result_when_equal,
    NULLIF(7, 0) AS result_when_different;
```

Ứng dụng thường thấy là bảo vệ phép chia khỏi mẫu số bằng 0:

```sql
SELECT
    25::numeric / NULLIF(5, 0) AS normal_division,
    25::numeric / NULLIF(0, 0) AS undefined_division;
```

### 12.4. IS NULL và IS NOT NULL

Muốn tìm các sản phẩm chưa ghi nhận giảm giá:

```sql
SELECT product_id, product_name
FROM select_lab.products
WHERE discount_pct IS NULL
ORDER BY product_id;
```

Không dùng:

```sql
-- Sai về mặt ngữ nghĩa mong đợi:
-- WHERE discount_pct = NULL
```

Trong SQL, phép so sánh `= NULL` thường trả trạng thái logic chưa biết (*UNKNOWN*), không phải `TRUE`. `WHERE` chỉ giữ hàng khi điều kiện là `TRUE`.

### 12.5. IS DISTINCT FROM

PostgreSQL hỗ trợ phép so sánh an toàn khi có NULL:

```sql
SELECT
    NULL::integer IS DISTINCT FROM 0 AS null_differs_from_zero,
    NULL::integer IS DISTINCT FROM NULL::integer AS two_nulls_distinct,
    5 IS NOT DISTINCT FROM 5 AS equal_values;
```

`IS DISTINCT FROM` coi NULL như một giá trị có thể phân biệt trong ngữ nghĩa so sánh, nên hữu ích khi cần đối chiếu hai cột mà không muốn kết quả UNKNOWN.

## 13. CASE: tạo cột phân loại từ điều kiện

`CASE` cho phép chọn một giá trị đầu ra dựa trên điều kiện.

### 13.1. CASE WHEN ... THEN ... ELSE

```sql
SELECT
    product_id,
    product_name,
    stock_quantity,
    CASE
        WHEN stock_quantity = 0 THEN 'Hết hàng'
        WHEN stock_quantity < 5 THEN 'Sắp hết'
        ELSE 'Còn hàng'
    END AS stock_status
FROM select_lab.products
ORDER BY product_id;
```

Kết quả ví dụ:

| product_id | stock_quantity | stock_status |
| ---: | ---: | --- |
| 101 | 12 | Còn hàng |
| 102 | 5 | Còn hàng |
| 103 | 0 | Hết hàng |
| 104 | 20 | Còn hàng |
| 105 | 3 | Sắp hết |
| 106 | 8 | Còn hàng |

Các nhánh được xem theo thứ tự. Nếu `stock_quantity = 0` đã khớp nhánh đầu, kết quả cho hàng đó là `'Hết hàng'`, không phải `'Sắp hết'`. Đây là lý do nên đặt điều kiện đặc biệt trước điều kiện rộng hơn.

### 13.2. Simple CASE

```sql
SELECT
    category_code,
    CASE category_code
        WHEN 'books' THEN 'Sách'
        WHEN 'stationery' THEN 'Văn phòng phẩm'
        WHEN 'accessories' THEN 'Phụ kiện'
        ELSE 'Khác'
    END AS category_name
FROM select_lab.products
ORDER BY product_id;
```

`CASE expression WHEN value` phù hợp với việc ánh xạ một giá trị sang các kết quả theo phép so sánh. `CASE WHEN condition` linh hoạt hơn khi so sánh khoảng, nhiều cột hoặc điều kiện boolean.

### 13.3. CASE không thay thế bảng tra cứu trong mọi trường hợp

Nếu danh mục thay đổi thường xuyên, việc hard-code hàng chục mã trong `CASE` của mỗi báo cáo rất khó bảo trì. Một bảng `categories` với `category_code` và tên hiển thị có thể tốt hơn. `CASE` thích hợp khi ánh xạ nhỏ, ổn định hoặc phục vụ một biểu thức đầu ra cụ thể.

### 13.4. Kiểu của các nhánh CASE

Các biểu thức `THEN` và `ELSE` cần có kiểu kết quả mà PostgreSQL có thể giải được. Ví dụ:

```sql
SELECT
    CASE WHEN true THEN 100 ELSE 0 END AS numeric_result;
```

Không nên dùng nhánh trả một số `numeric` và nhánh khác trả chuỗi tùy ý `'unknown'` nếu muốn kết quả vẫn là số. Có thể trả `NULL` khi thiếu giá trị hoặc ép toàn bộ sang `text` ở tầng hiển thị.

## 14. Biểu thức boolean cũng là cột đầu ra

Một biểu thức điều kiện không nhất thiết chỉ xuất hiện trong `WHERE`; nó có thể được chọn để hiển thị trạng thái:

```sql
SELECT
    product_id,
    product_name,
    stock_quantity > 0 AS in_stock,
    is_active AND stock_quantity > 0 AS available_for_sale
FROM select_lab.products
ORDER BY product_id;
```

Kết quả gồm các cột boolean, thuận tiện khi application cần biết sản phẩm có thể bán không.

### 14.1. Toán tử so sánh

Các toán tử thông dụng:

| Biểu thức | Ý nghĩa |
| --- | --- |
| `unit_price > 100000` | Giá lớn hơn 100000. |
| `stock_quantity >= 5` | Tồn kho ít nhất 5. |
| `is_active = true` | Sản phẩm đang hoạt động. |
| `category_code <> 'books'` | Danh mục không phải books. |
| `unit_price BETWEEN 50000 AND 200000` | Giá nằm trong khoảng, bao gồm hai đầu. |
| `category_code IN ('books', 'stationery')` | Danh mục thuộc danh sách. |
| `product_name ILIKE '%sql%'` | Tên chứa “sql”, không phân biệt hoa/thường theo ngữ nghĩa ILIKE. |

`!=` cũng được PostgreSQL hỗ trợ cho “khác”, nhưng `<>` là cách viết chuẩn SQL thường gặp.

### 14.2. AND, OR và dấu ngoặc

```sql
SELECT
    product_name,
    is_active,
    stock_quantity,
    is_active AND stock_quantity > 0 AS available
FROM select_lab.products;
```

Khi logic phức tạp, dùng ngoặc để thể hiện ý định:

```sql
SELECT
    product_id,
    (
        is_active
        AND (
            category_code = 'books'
            OR stock_quantity >= 10
        )
    ) AS highlighted
FROM select_lab.products;
```

Trong SQL có logic ba trạng thái `TRUE`, `FALSE` và `UNKNOWN`. Một số phép kết hợp với NULL có thể trả UNKNOWN; không nên giả định boolean luôn chỉ có hai giá trị nếu cột hoặc biểu thức cho phép NULL.

## 15. Biểu thức ngày và thời gian

PostgreSQL hỗ trợ nhiều kiểu thời gian như `date`, `timestamp` và `timestamptz`. Trong bảng lab, `created_at` là `date` nên không có giờ/phút.

### 15.1. Cộng ngày

```sql
SELECT
    product_id,
    created_at,
    created_at + 30 AS review_date
FROM select_lab.products
ORDER BY product_id;
```

Với `date + integer`, kết quả là ngày sau số ngày tương ứng. Điều này khác với việc cộng một chuỗi ký tự bất kỳ vào date.

### 15.2. Lấy năm và tháng

```sql
SELECT
    product_id,
    created_at,
    EXTRACT(YEAR FROM created_at)::integer AS created_year,
    EXTRACT(MONTH FROM created_at)::integer AS created_month
FROM select_lab.products;
```

`EXTRACT` trả giá trị số biểu diễn một thành phần thời gian. Nếu muốn nhóm theo tháng, thường nên giữ biểu diễn năm–tháng đầy đủ thay vì chỉ chọn số tháng 1–12 (vì tháng 10 của nhiều năm khác nhau có thể bị gộp).

```sql
SELECT
    product_id,
    date_trunc('month', created_at::timestamp) AS month_start
FROM select_lab.products;
```

### 15.3. Định dạng ngày thành text

```sql
SELECT
    product_id,
    to_char(created_at::timestamp, 'DD/MM/YYYY')
        AS created_date_label
FROM select_lab.products
ORDER BY product_id;
```

`to_char` ở đây phục vụ **định dạng hiển thị**; cột `created_date_label` là text, không phải kiểu `date`. Nếu cần lọc khoảng ngày hoặc so sánh theo thời gian, tốt hơn là giữ cột gốc `date`/`timestamptz` và chỉ định dạng ở lớp hiển thị.

### 15.4. Tránh nhầm múi giờ

Với `timestamptz`, cách hiển thị phụ thuộc cấu hình `TimeZone` của session. Nếu bài toán báo cáo cần “ngày theo giờ Việt Nam”, phải xác định múi giờ nghiệp vụ trước khi cắt timestamp thành ngày. Bảng lab dùng `date` nên không tự mang thông tin múi giờ.

## 16. Những hàm thường gặp trong SELECT

Một select list có thể kết hợp nhiều loại hàm:

```sql
SELECT
    product_id,
    length(product_name) AS name_chars,
    upper(sku) AS sku_upper,
    ROUND(unit_price * 1.05, 2) AS example_adjusted_price,
    COALESCE(discount_pct, 0) AS discount_for_math,
    CURRENT_DATE - created_at AS age_days
FROM select_lab.products
ORDER BY product_id;
```

Trong ví dụ này:

- `length` cho số ký tự của tên.
- `upper` tạo phiên bản chữ hoa.
- `ROUND` làm tròn một biểu thức số.
- `COALESCE` chọn giá trị dự phòng cho NULL.
- `CURRENT_DATE - created_at` trả số ngày theo phép toán `date - date`.

Đây chỉ là **giá trị cột kết quả**. PostgreSQL không thay `unit_price` trong bảng bằng giá nhân 1.05, không cập nhật `sku` thành chữ hoa và không gán `discount_pct = 0` trong dữ liệu.

### 16.1. Một hàm có thể trả giá trị theo phiên

```sql
SELECT
    current_database() AS database_name,
    current_schema() AS schema_name,
    current_user AS username;
```

Những hàm này phản ánh ngữ cảnh connection và có thể hữu ích khi debug môi trường. Không nên hard-code chúng như giá trị bất biến cho toàn bộ hệ thống.

### 16.2. Hàm không nhất thiết “thuần đọc”

Không phải mọi biểu thức được dùng trong `SELECT` đều vô hại. PostgreSQL có các hàm thay đổi trạng thái, ví dụ hàm lấy số sequence tiếp theo, hoặc các hàm do người dùng tạo có thể có side effect. Một câu bắt đầu bằng `SELECT` cũng có thể kết hợp khóa hàng trong những cấu trúc SQL thích hợp.

Vì vậy, đừng đánh giá độ an toàn của truy vấn chỉ bằng việc nó bắt đầu bằng từ khóa `SELECT`. Hãy xem hàm được gọi, quyền của role và hiệu ứng thực tế trước khi chạy trên môi trường quan trọng.

## 17. WHERE lọc theo biểu thức, nhưng không dùng trực tiếp alias đầu ra

`WHERE` chọn các hàng thỏa điều kiện trước khi trả dữ liệu cuối cùng theo ngữ nghĩa truy vấn.

```sql
SELECT
    product_id,
    product_name,
    unit_price
FROM select_lab.products
WHERE unit_price >= 100000
ORDER BY product_id;
```

PostgreSQL giữ các hàng có `unit_price >= 100000` và không cần tạo các hàng kết quả cho sản phẩm không thỏa điều kiện đó.

### 17.1. Lọc bằng phép tính trực tiếp

```sql
SELECT
    product_id,
    product_name,
    unit_price * stock_quantity AS inventory_value
FROM select_lab.products
WHERE unit_price * stock_quantity > 1000000
ORDER BY inventory_value DESC;
```

Biểu thức `unit_price * stock_quantity` xuất hiện ở cả select list và `WHERE`. Đây là cách viết hợp lệ.

### 17.2. Vì sao WHERE inventory_value không hoạt động?

Ví dụ sai:

```sql
-- Sai: WHERE không tham chiếu trực tiếp alias của select list cùng cấp.
-- SELECT
--     product_id,
--     unit_price * stock_quantity AS inventory_value
-- FROM select_lab.products
-- WHERE inventory_value > 1000000;
```

`inventory_value` là tên đầu ra do `SELECT` tạo. `WHERE` của cùng cấp truy vấn **không nhìn thấy bí danh đó** để dùng như cột nguồn.

Lý do được giải thích bằng thứ tự xử lý logic thường dùng:

```text
FROM / JOIN
     |
     v
WHERE
     |
     v
GROUP BY / HAVING (nếu có)
     |
     v
SELECT: tạo cột đầu ra và alias
     |
     v
DISTINCT (nếu có)
     |
     v
ORDER BY
     |
     v
LIMIT / OFFSET
```

Đây là **mô hình lý giải ngữ nghĩa**, không phải lịch trình vật lý cố định mà PostgreSQL bắt buộc thực hiện từng bước trong engine. Bộ tối ưu có thể biến đổi hoặc đẩy điều kiện khi vẫn giữ kết quả SQL đúng.

### 17.3. Cách sửa: lặp biểu thức rõ ràng

```sql
SELECT
    product_id,
    unit_price * stock_quantity AS inventory_value
FROM select_lab.products
WHERE unit_price * stock_quantity > 1000000;
```

Đây là cách đơn giản khi biểu thức ngắn.

### 17.4. Cách sửa: truy vấn con

Khi biểu thức dài, có thể tạo nó ở cấp truy vấn con rồi lọc ở cấp ngoài:

```sql
SELECT
    x.product_id,
    x.product_name,
    x.inventory_value
FROM (
    SELECT
        product_id,
        product_name,
        unit_price * stock_quantity AS inventory_value
    FROM select_lab.products
) AS x
WHERE x.inventory_value > 1000000
ORDER BY x.inventory_value DESC;
```

Ở cấp ngoài, `x.inventory_value` là **cột đầu ra của nguồn bảng dẫn xuất `x`**, nên `WHERE` được phép tham chiếu.

### 17.5. Cách sửa: CTE

```sql
WITH product_values AS (
    SELECT
        product_id,
        product_name,
        unit_price * stock_quantity AS inventory_value
    FROM select_lab.products
)
SELECT
    product_id,
    product_name,
    inventory_value
FROM product_values
WHERE inventory_value > 1000000
ORDER BY inventory_value DESC;
```

CTE (*Common Table Expression*) giúp đặt tên kết quả trung gian. PostgreSQL có thể tối ưu hoặc materialize CTE tùy phiên bản, cấu trúc và gợi ý liên quan; **không nên dùng CTE chỉ vì tin rằng nó luôn chạy nhanh hơn lặp biểu thức**. Nó trước hết giúp tổ chức câu SQL rõ nghĩa.

## 18. ORDER BY dùng được alias của SELECT

Khác với `WHERE`, `ORDER BY` thường có thể tham chiếu trực tiếp **tên đầu ra**:

```sql
SELECT
    product_id,
    product_name,
    unit_price * stock_quantity AS inventory_value
FROM select_lab.products
ORDER BY inventory_value DESC, product_id ASC;
```

`inventory_value` là alias tạo trong select list; PostgreSQL cho phép dùng làm khóa sắp xếp trong `ORDER BY`.

### 18.1. ORDER BY cột gốc không được chọn

Trong nhiều trường hợp, bạn cũng có thể sắp xếp theo cột nguồn không nằm trong danh sách đầu ra:

```sql
SELECT
    product_id,
    product_name
FROM select_lab.products
ORDER BY created_at DESC, product_id;
```

Không cần bắt buộc thêm `created_at` vào kết quả nếu ứng dụng chỉ cần ID/tên. Nhưng một số dạng `DISTINCT`, kết hợp tập hợp hoặc biểu thức phức tạp có ràng buộc khác về `ORDER BY`, nên phải kiểm tra ngữ nghĩa truy vấn cụ thể.

### 18.2. ORDER BY theo vị trí

PostgreSQL cho phép:

```sql
SELECT
    product_name,
    unit_price
FROM select_lab.products
ORDER BY 2 DESC;
```

`2` ở đây chỉ **cột đầu ra thứ hai**, tức `unit_price`. Cách này ngắn nhưng dễ gây lỗi nếu ai đó đổi thứ tự select list. Trong code bảo trì lâu dài, thường nên viết:

```sql
ORDER BY unit_price DESC
```

hoặc alias rõ ràng.

### 18.3. Tên alias trùng cột gốc

Khi một tên có thể là **cột nguồn** lẫn **alias đầu ra**, PostgreSQL có các quy tắc phân giải riêng theo từng mệnh đề. Trong những tình huống mơ hồ, `ORDER BY` thường ưu tiên tên cột đầu ra đơn giản, trong khi `GROUP BY` có thể ưu tiên cột đầu vào. Đây là một lý do quan trọng để tránh đặt alias trùng tên cột có ý nghĩa khác.

Ví dụ dùng alias riêng không mơ hồ:

```sql
SELECT
    product_name,
    unit_price * stock_quantity AS stock_value
FROM select_lab.products
ORDER BY stock_value DESC;
```

Nếu cần sắp xếp theo một biểu thức đầy đủ, có thể ghi biểu thức trực tiếp để loại bỏ nghi ngờ về tên nào được phân giải.

## 19. DISTINCT và tên biểu thức đầu ra

Mặc định `SELECT` không tự xóa những hàng trùng nhau về giá trị đầu ra. Muốn nhận danh sách nhóm sản phẩm không lặp:

```sql
SELECT DISTINCT category_code
FROM select_lab.products
ORDER BY category_code;
```

Kết quả:

```text
accessories
books
stationery
```

Trong cú pháp:

```sql
SELECT DISTINCT
    category_code,
    is_active
FROM select_lab.products;
```

`DISTINCT` xét **toàn bộ bộ giá trị của các biểu thức được chọn**, không chỉ cột đầu tiên. Nếu cùng category có sản phẩm active và inactive, hai bộ giá trị có thể vẫn là hai hàng riêng.

### 19.1. SELECT ALL là mặc định

```sql
SELECT ALL category_code
FROM select_lab.products;
```

`ALL` biểu thị giữ các hàng trùng về giá trị đầu ra; khi bỏ `ALL`, hành vi thông thường cũng tương đương. Vì thế, thường viết ngắn:

```sql
SELECT category_code
FROM select_lab.products;
```

### 19.2. DISTINCT ON của PostgreSQL

PostgreSQL có mở rộng `DISTINCT ON` để chọn một hàng đại diện cho mỗi nhóm khóa:

```sql
SELECT DISTINCT ON (category_code)
    category_code,
    product_id,
    product_name,
    unit_price
FROM select_lab.products
ORDER BY category_code, unit_price DESC, product_id;
```

Ý định: với mỗi `category_code`, chọn một sản phẩm có `unit_price` cao nhất theo thứ tự đã quy định. `DISTINCT ON` giữ hàng đầu tiên trong mỗi nhóm dựa trên `ORDER BY`. Các biểu thức `DISTINCT ON` phải khớp với những biểu thức ngoài cùng bên trái của `ORDER BY` theo yêu cầu PostgreSQL.

**Quan trọng:** không có `ORDER BY` phù hợp thì hàng nào đại diện cho mỗi nhóm có thể không xác định. `DISTINCT ON` là tính năng PostgreSQL đặc thù, không nên giả định mọi DBMS SQL đều hỗ trợ cùng cú pháp.

## 20. Biểu thức tổng hợp trong SELECT

Một select list không chỉ gồm biểu thức trên từng hàng; nó còn có thể chứa các **hàm tổng hợp** (*aggregate functions*) như `COUNT`, `SUM`, `AVG`, `MIN` và `MAX`.

```sql
SELECT
    COUNT(*) AS product_count,
    SUM(stock_quantity) AS total_stock,
    AVG(unit_price) AS average_price,
    MAX(unit_price) AS highest_price
FROM select_lab.products;
```

Truy vấn này trả về **một hàng tổng hợp** cho tập đầu vào, thay vì một hàng trên mỗi sản phẩm.

### 20.1. COUNT(*) và COUNT(column) khác nhau

```sql
SELECT
    COUNT(*) AS all_products,
    COUNT(discount_pct) AS products_with_discount_recorded
FROM select_lab.products;
```

`COUNT(*)` đếm mọi hàng. `COUNT(discount_pct)` chỉ đếm các hàng có `discount_pct` khác SQL NULL. Trong dữ liệu mẫu có 6 sản phẩm, nhưng chỉ 4 hàng có giá trị giảm giá được ghi nhận (bao gồm giá trị `0`).

Không nên xem `COUNT(discount_pct)` là số sản phẩm “đang được giảm giá”: giá trị bằng 0 vẫn được đếm. Nếu muốn đếm sản phẩm có phần trăm giảm **lớn hơn 0**, cần điều kiện phù hợp.

### 20.2. GROUP BY và select list

Muốn tổng hợp theo danh mục:

```sql
SELECT
    category_code,
    COUNT(*) AS product_count,
    SUM(stock_quantity) AS stock_total
FROM select_lab.products
GROUP BY category_code
ORDER BY category_code;
```

Một lỗi thường gặp:

```sql
-- Sai: product_name không được nhóm hoặc tổng hợp.
-- SELECT category_code, product_name, COUNT(*)
-- FROM select_lab.products
-- GROUP BY category_code;
```

Khi query có `GROUP BY`, những cột trong select list không được tổng hợp thường cần thuộc khóa nhóm hoặc thỏa điều kiện phụ thuộc hàm mà PostgreSQL có thể xác định theo quy tắc của nó. Không thể tùy tiện thêm `product_name` nếu mỗi nhóm có nhiều sản phẩm khác tên.

### 20.3. GROUP BY dùng alias được không?

PostgreSQL cho phép tham chiếu một bí danh đầu ra đơn giản trong `GROUP BY` ở những tình huống không mơ hồ:

```sql
SELECT
    category_code AS category_label,
    COUNT(*) AS product_count
FROM select_lab.products
GROUP BY category_label
ORDER BY category_label;
```

Ở đây `category_label` không phải cột nguồn của bảng, nên PostgreSQL có thể diễn giải như bí danh của `category_code`. Tuy nhiên, khi alias trùng tên cột đầu vào, `GROUP BY` có những quy tắc phân giải khác với `ORDER BY` và có thể tạo kết quả ngoài ý định.

Để rõ ràng và dễ chuyển hệ quản trị:

```sql
SELECT
    category_code AS category_label,
    COUNT(*) AS product_count
FROM select_lab.products
GROUP BY category_code
ORDER BY category_label;
```

là cách viết thường dễ đọc hơn. Không giả định alias `SELECT` được tham chiếu tự do trong mọi biểu thức `GROUP BY`, `WHERE` hoặc `HAVING`.

### 20.4. HAVING

Ví dụ chỉ lấy những danh mục có từ 2 sản phẩm trở lên:

```sql
SELECT
    category_code,
    COUNT(*) AS product_count
FROM select_lab.products
GROUP BY category_code
HAVING COUNT(*) >= 2
ORDER BY product_count DESC, category_code;
```

`HAVING` lọc **nhóm**. Không dùng trực tiếp alias `product_count` trong `HAVING` của cùng cấp truy vấn như thể nó là cột nguồn; lặp biểu thức aggregate hoặc dùng CTE/truy vấn con nếu muốn tái sử dụng ở cấp ngoài.

## 21. Biểu thức SELECT trong truy vấn có JOIN

Khi kết hợp nhiều nguồn, select list vẫn tạo một tập cột đầu ra duy nhất:

```sql
SELECT
    p.product_id AS id,
    p.product_name AS name,
    c.category_label AS category,
    ROUND(
        p.unit_price * (1 - COALESCE(p.discount_pct, 0) / 100),
        2
    ) AS final_price
FROM select_lab.products AS p
JOIN (
    VALUES
        ('books', 'Sách'),
        ('stationery', 'Văn phòng phẩm'),
        ('accessories', 'Phụ kiện')
) AS c(category_code, category_label)
    ON c.category_code = p.category_code
WHERE p.is_active
ORDER BY p.product_id;
```

Mỗi mục trong select list có thể lấy từ một nguồn hoặc dùng nhiều nguồn trong cùng biểu thức. Bí danh bảng `p` và `c` được dùng để chỉ rõ cột nào thuộc nguồn nào.

Điểm quan trọng:

- Không phải cột xuất hiện trong `SELECT` mới được dùng trong `ON` hoặc `WHERE`; các mệnh đề này tham chiếu cột nguồn trong phạm vi phù hợp.
- Biểu thức `final_price` chỉ là giá đầu ra, không sửa `unit_price`.
- Nếu JOIN làm một sản phẩm khớp nhiều hàng ở nguồn bên phải, sản phẩm có thể xuất hiện nhiều lần. `SELECT DISTINCT` đôi khi che triệu chứng, nhưng phải xem lại khóa và điều kiện JOIN để xử lý đúng nguyên nhân.

### 21.1. Chọn p.* và thêm cột tính toán

```sql
SELECT
    p.*,
    p.unit_price * p.stock_quantity AS inventory_value
FROM select_lab.products AS p;
```

Kết quả gồm toàn bộ cột của `p` cộng thêm một cột tính toán `inventory_value` ở cuối. Cú pháp hợp lệ, nhưng nếu output dùng trong DTO cố định thì nên cân nhắc danh sách cột tường minh.

## 22. SELECT với biểu thức phụ thuộc dữ liệu lồng nhau

PostgreSQL còn hỗ trợ kiểu dữ liệu như `jsonb` và array. Một select list có thể trích xuất dữ liệu từ những kiểu này.

Ví dụ chỉ để minh họa, không cần thay đổi bảng lab:

```sql
SELECT
    '{"status":"paid","customer":{"name":"Lan"}}'::jsonb
        ->> 'status' AS status_text,
    '{"status":"paid","customer":{"name":"Lan"}}'::jsonb
        #>> '{customer,name}' AS customer_name;
```

Toán tử `->>` trả text của key; `#>>` trả text theo path nhiều cấp. Đó vẫn là những **biểu thức trong select list**, tương tự phép toán số hoặc gọi hàm.

Tuy nhiên, không nên biến toàn bộ thiết kế quan hệ thành một cột JSONB chỉ vì `SELECT` có thể trích xuất key. Các trường thường dùng để JOIN, kiểm tra foreign key, unique, tính tiền và cập nhật độc lập có thể phù hợp hơn với cột/bảng quan hệ thông thường.

## 23. Biểu thức, bộ tối ưu và chi phí thực thi

PostgreSQL xác định kế hoạch thực thi bằng optimizer. Khi xem một `SELECT` dài, không nên suy ra rằng engine luôn tính các biểu thức theo thứ tự từng dòng văn bản rồi mới đọc bảng.

### 23.1. Ngữ nghĩa logic khác lịch trình vật lý

Ví dụ:

```sql
SELECT
    product_name,
    unit_price * stock_quantity AS inventory_value
FROM select_lab.products
WHERE category_code = 'books'
ORDER BY inventory_value DESC;
```

Về ý nghĩa, truy vấn lấy các sản phẩm thuộc nhóm books, tính `inventory_value`, sau đó sắp xếp kết quả. Nhưng PostgreSQL có thể chọn cách quét dữ liệu, đẩy điều kiện, tính biểu thức hoặc sắp xếp phù hợp với kế hoạch. SQL đảm bảo kết quả theo ngữ nghĩa truy vấn, không cam kết một thứ tự thao tác vật lý dễ mô phỏng từ trên xuống.

### 23.2. EXPLAIN

```sql
EXPLAIN
SELECT
    product_id,
    unit_price * stock_quantity AS inventory_value
FROM select_lab.products
WHERE category_code = 'books';
```

`EXPLAIN` hiển thị kế hoạch ước lượng. Nếu cần đo thực tế trong môi trường được phép:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT
    product_id,
    unit_price * stock_quantity AS inventory_value
FROM select_lab.products
WHERE category_code = 'books';
```

`EXPLAIN ANALYZE` **thực sự chạy truy vấn**. Với `SELECT` chỉ đọc thông thường có thể chấp nhận được trong lab, nhưng một `SELECT` phức tạp, chứa hàm có side effect hoặc truy vấn tốn tài nguyên vẫn có rủi ro. Đừng dùng `ANALYZE` không kiểm soát lên workload production.

### 23.3. Không tối ưu khi chưa đo

Một biểu thức ngắn như `unit_price * stock_quantity` thường không phải nút thắt lớn so với quét hàng triệu dòng, JOIN không có index phù hợp hoặc truyền toàn bộ JSON document qua mạng. Trước khi thêm cột dữ liệu dẫn xuất để “tránh tính lại”:

1. Đo độ trễ truy vấn.
2. Kiểm tra `WHERE` có dùng index phù hợp không.
3. Xem số hàng đọc và số hàng trả.
4. Đánh giá chi phí network, serialize và phía ứng dụng.
5. Cân nhắc tính toán trong SQL so với trong ứng dụng dựa trên workload thật.

Phi chuẩn hóa bằng cách lưu thêm cột tính toán có thể tăng chi phí đồng bộ và rủi ro sai dữ liệu; không nên thực hiện chỉ vì một biểu thức xuất hiện trong `SELECT`.

## 24. Sắp xếp và giới hạn kết quả một cách ổn định

Trong ứng dụng, `SELECT` thường kết hợp `ORDER BY` và `LIMIT`:

```sql
SELECT
    product_id,
    product_name,
    unit_price AS price
FROM select_lab.products
WHERE is_active
ORDER BY price DESC, product_id
LIMIT 3;
```

Kết quả gồm tối đa ba sản phẩm đang hoạt động có giá lớn nhất, với `product_id` làm tiêu chí phụ khi giá trùng nhau.

### 24.1. Vì sao LIMIT không ORDER BY dễ sai?

```sql
SELECT product_id, product_name
FROM select_lab.products
LIMIT 3;
```

Query này chỉ yêu cầu **ba hàng bất kỳ** được PostgreSQL trả theo kế hoạch hiện hành; nó không bảo đảm ba ID nhỏ nhất hoặc ba sản phẩm mới nhất.

Nếu ứng dụng muốn “ba sản phẩm mới nhất”:

```sql
SELECT product_id, product_name, created_at
FROM select_lab.products
ORDER BY created_at DESC, product_id DESC
LIMIT 3;
```

Thứ tự phụ theo `product_id` giúp kết quả có tính xác định khi nhiều sản phẩm cùng ngày tạo.

### 24.2. ORDER BY NULLS FIRST/LAST

Nếu sắp xếp theo cột có NULL như `discount_pct`:

```sql
SELECT product_id, discount_pct
FROM select_lab.products
ORDER BY discount_pct DESC NULLS LAST, product_id;
```

`NULLS LAST` yêu cầu các hàng có NULL nằm cuối theo cột sắp xếp đó. Cú pháp này quan trọng khi “thiếu giảm giá” không được xen giữa các mức phần trăm giảm cụ thể.

## 25. SELECT không tự lưu dữ liệu dẫn xuất

Ví dụ:

```sql
SELECT
    product_id,
    ROUND(unit_price * 1.1, 2) AS new_price
FROM select_lab.products
WHERE product_id = 101;
```

Đây là **tính thử giá mới trong kết quả**. Bảng vẫn giữ `unit_price = 180000.00` cho sản phẩm 101.

Muốn thực sự thay đổi cột `unit_price` trong dữ liệu, cần một thao tác DML như `UPDATE` cùng điều kiện, transaction và quyền phù hợp. Bài học này không thực hiện thao tác đó vì đang tập trung vào **truy vấn đọc, biểu diễn cột và tính toán**.

Tương tự:

```sql
SELECT
    product_name AS "Tên hiển thị",
    stock_quantity > 0 AS is_in_stock
FROM select_lab.products;
```

không tạo hai cột vật lý `"Tên hiển thị"` và `is_in_stock` trong bảng. Tên và giá trị chỉ thuộc tập kết quả của câu truy vấn.

### 25.1. Alias không thay thế migration

Nếu ứng dụng đổi quy ước tên từ `product_name` sang `display_name`, alias có thể giúp tương thích ở **một truy vấn**:

```sql
SELECT product_name AS display_name
FROM select_lab.products;
```

Nhưng các câu SQL khác vẫn phải tham chiếu `product_name`, trừ khi dùng view, thay đổi schema hoặc một tầng ánh xạ khác được thiết kế riêng.

## 26. Những lỗi thường gặp khi viết SELECT

### Lỗi 1: nhầm dấu quote

```sql
-- Đúng:
SELECT product_name AS "Tên sản phẩm"
FROM select_lab.products;

-- Sai nếu muốn lấy cột:
-- SELECT 'product_name' FROM select_lab.products;
-- Biểu thức trên hợp lệ nhưng trả chuỗi hằng, không trả giá trị cột.
```

**Phân tích:** dấu `'` bao string literal; dấu `"` bao identifier. Sai kiểu quote có thể gây lỗi cú pháp hoặc âm thầm trả sai thông tin.

### Lỗi 2: dùng alias trong WHERE

```sql
-- Sai:
-- SELECT unit_price * stock_quantity AS stock_value
-- FROM select_lab.products
-- WHERE stock_value > 1000000;
```

**Cách sửa:** lặp biểu thức trong `WHERE` hoặc dùng truy vấn con/CTE để biến alias thành cột nguồn của cấp truy vấn ngoài.

### Lỗi 3: nhầm alias cột với alias bảng

```sql
-- Sai: display_name không phải cột của nguồn p.
-- SELECT p.product_name AS display_name, p.display_name
-- FROM select_lab.products AS p;
```

**Cách sửa:** tham chiếu `p.product_name` khi cần cột nguồn; `display_name` chỉ là tên đầu ra.

### Lỗi 4: tính phần trăm bằng integer division

```sql
SELECT 1 / 4 AS wrong_ratio,
       1::numeric / 4 AS correct_ratio;
```

Kết quả khác nhau: `0` so với `0.25`. Chú ý kiểu toán hạng khi tính tỷ lệ.

### Lỗi 5: biểu thức với NULL cho kết quả không mong đợi

```sql
SELECT
    product_id,
    unit_price * (1 - discount_pct / 100)
        AS price_after_discount
FROM select_lab.products;
```

Với discount NULL, giá sau giảm cũng NULL. **Nếu** nghiệp vụ cho phép coi NULL như 0%, dùng `COALESCE(discount_pct, 0)`.

### Lỗi 6: phép toán chia cho 0

```sql
-- Có thể lỗi nếu số lượng bằng 0:
-- SELECT unit_price / stock_quantity FROM select_lab.products;

-- An toàn hơn theo ngữ nghĩa "không xác định nếu bằng 0":
SELECT
    product_id,
    unit_price / NULLIF(stock_quantity, 0) AS ratio_value
FROM select_lab.products;
```

Ở ví dụ này, cột `ratio_value` chỉ minh họa kỹ thuật tránh chia cho 0; **không phải chỉ số nghiệp vụ “giá trên mỗi tồn kho” được khuyến nghị**.

### Lỗi 7: không dùng ORDER BY mà kỳ vọng thứ tự cố định

```sql
-- Không bảo đảm chọn 3 sản phẩm có ID nhỏ nhất:
SELECT product_id FROM select_lab.products LIMIT 3;

-- Đúng nếu muốn 3 ID nhỏ nhất:
SELECT product_id
FROM select_lab.products
ORDER BY product_id
LIMIT 3;
```

### Lỗi 8: SELECT * trong hợp đồng API

`SELECT *` có thể trả cột mới sau migration, làm thay đổi hình dạng response hoặc vô tình chuyển dữ liệu không cần thiết. Viết danh sách cột tường minh cho truy vấn API quan trọng.

### Lỗi 9: tên cột mơ hồ trong JOIN

Nếu cả hai bảng có `category_code`, viết `SELECT category_code` dễ báo ambiguous. Dùng `p.category_code` hoặc `c.category_code`.

### Lỗi 10: GROUP BY thiếu cột/biểu thức phù hợp

```sql
-- Không hợp lệ trong dữ liệu ví dụ:
-- SELECT category_code, product_name, COUNT(*)
-- FROM select_lab.products
-- GROUP BY category_code;
```

Một nhóm có thể có nhiều tên sản phẩm; PostgreSQL không thể chọn tùy ý một tên mà không có quy tắc. Hãy thêm khóa nhóm thích hợp hoặc dùng aggregate có chủ đích, không dùng `DISTINCT` để che lỗi ngữ nghĩa.

### Lỗi 11: coi alias là cột đã lưu

`SELECT unit_price * 2 AS new_price` không cập nhật database. Chỉ có kết quả trả ra mang tên `new_price`.

### Lỗi 12: dùng COALESCE làm sai nghiệp vụ

`COALESCE(discount_pct, 0)` có thể đúng nếu NULL nghĩa là chưa có giảm giá. Nhưng nếu NULL nghĩa là dữ liệu cần xác minh, thay bằng 0 sẽ che vấn đề. Hàm SQL không tự xác định định nghĩa nghiệp vụ.

### Lỗi 13: dùng hàm định dạng ngày để lọc dữ liệu

Thay vì:

```sql
-- Có thể khiến tìm kiếm/sắp xếp theo ngày kém thuận tiện:
-- WHERE to_char(created_at::timestamp, 'YYYY-MM') = '2026-10'
```

nên cân nhắc lọc theo khoảng ngày:

```sql
SELECT product_id, product_name
FROM select_lab.products
WHERE created_at >= DATE '2026-10-01'
  AND created_at < DATE '2026-11-01';
```

Giữ cột ngày ở kiểu gốc giúp so sánh rõ và thường tạo điều kiện tốt hơn cho index phù hợp.

### Lỗi 14: SELECT DISTINCT để “sửa” JOIN bị nhân hàng

Nếu JOIN tạo hai hàng cho một sản phẩm vì bên phải có hai bản ghi cùng khóa ghép, `DISTINCT` có thể loại trùng một số kết quả nhưng không bảo đảm sửa đúng logic. Cần kiểm tra cardinality của quan hệ và điều kiện JOIN.

## 27. Một truy vấn đầy đủ kết hợp nhiều kỹ thuật

Giả sử cần trả danh sách sản phẩm đang bán, kèm mã, tên, giá gốc, giá sau giảm, giá trị tồn kho và nhãn trạng thái:

```sql
SELECT
    p.product_id AS id,
    p.sku AS product_code,
    p.product_name AS display_name,
    p.unit_price AS listed_price,
    ROUND(
        p.unit_price
            * (1 - COALESCE(p.discount_pct, 0) / 100),
        2
    ) AS selling_price,
    p.unit_price * p.stock_quantity AS inventory_value,
    CASE
        WHEN p.stock_quantity = 0 THEN 'Hết hàng'
        WHEN p.stock_quantity < 5 THEN 'Sắp hết'
        ELSE 'Còn hàng'
    END AS stock_label,
    p.created_at + 30 AS review_date
FROM select_lab.products AS p
WHERE p.is_active
ORDER BY selling_price DESC, p.product_id
LIMIT 20;
```

Đọc từ bên trong:

1. `FROM select_lab.products AS p` khai báo nguồn `p`.
2. `WHERE p.is_active` chọn sản phẩm đang hoạt động.
3. Select list tạo tám cột đầu ra, trong đó `selling_price`, `inventory_value`, `stock_label` và `review_date` là biểu thức dẫn xuất.
4. `COALESCE` áp dụng giả định rằng giảm giá NULL được xem là 0% trong phép tính.
5. `CASE` tạo nhãn tồn kho theo các mốc nghiệp vụ.
6. `ORDER BY selling_price DESC, p.product_id` sắp xếp theo alias giá bán và ID phụ.
7. `LIMIT 20` trả tối đa 20 hàng.

Nếu sản phẩm bị ngừng bán có `is_active = false`, nó bị loại ở `WHERE` dù có giá trị tồn hoặc giá bán hợp lệ.

### 27.1. Biến điều kiện giá dẫn xuất thành CTE

Nếu nghiệp vụ chỉ hiển thị sản phẩm có giá bán sau giảm ít nhất 100000:

```sql
WITH priced_products AS (
    SELECT
        p.product_id,
        p.product_name,
        p.is_active,
        ROUND(
            p.unit_price
                * (1 - COALESCE(p.discount_pct, 0) / 100),
            2
        ) AS selling_price
    FROM select_lab.products AS p
)
SELECT
    product_id,
    product_name,
    selling_price
FROM priced_products
WHERE is_active
  AND selling_price >= 100000
ORDER BY selling_price DESC, product_id;
```

Ở truy vấn ngoài, `selling_price` là một cột của nguồn `priced_products` nên dùng được trong `WHERE`. CTE giúp tránh viết lặp biểu thức dài ở cùng cấp truy vấn.

### 27.2. Hợp đồng tên cột cho Java

Với JDBC:

```sql
SELECT
    product_id AS product_id,
    product_name AS product_name,
    unit_price AS unit_price,
    ROUND(
        unit_price * (1 - COALESCE(discount_pct, 0) / 100),
        2
    ) AS selling_price
FROM select_lab.products
WHERE product_id = 101;
```

Các alias như `product_id` và `selling_price` làm tên cột kết quả rõ ràng khi mapping vào DTO. Tuy nhiên, ứng dụng Java vẫn phải sử dụng kiểu phù hợp: đối với số tiền `numeric`, `BigDecimal` thường phù hợp hơn `double` nếu muốn tránh sai lệch dấu chấm động.

## 28. Bài tập thực hành

Hãy giải các bài theo thứ tự trong schema `select_lab`. Những bài dưới đây chỉ dùng `SELECT` nên không thay đổi dữ liệu đã tạo. Bạn có thể so sánh lời giải ở phần sau.

### Bài 1. Chọn đúng ba cột

Viết câu SQL trả `product_id`, `product_name` và `unit_price` của tất cả sản phẩm, có thứ tự ID tăng dần. Không sử dụng `*`.

### Bài 2. Đặt alias

Trả ba cột đầu ra mang tên `id`, `name` và `listed_price` từ những cột tương ứng của bảng.

### Bài 3. Tính giá trị tồn kho

Trả `product_id`, `product_name` và `inventory_value = unit_price * stock_quantity`. Chỉ lấy sản phẩm có giá trị tồn kho trên 500000, sắp xếp giảm dần theo giá trị tồn.

### Bài 4. Chia số nguyên

Dự đoán kết quả:

```sql
SELECT
    3 / 4 AS a,
    3.0 / 4 AS b,
    3::numeric / 4 AS c;
```

Giải thích tại sao `a` khác `b` và `c`.

### Bài 5. Tính giá sau giảm

Trả `product_id`, `product_name` và `selling_price` sau khi áp dụng `discount_pct`. Trong bài tập này, quy ước NULL là 0%. Làm tròn hai chữ số thập phân.

### Bài 6. Tạo nhãn tình trạng tồn kho

Trả `product_id`, `stock_quantity` và `stock_label` theo quy tắc:

- Tồn 0: `Hết hàng`.
- Tồn từ 1 đến 4: `Sắp hết`.
- Tồn từ 5 trở lên: `Còn hàng`.

### Bài 7. Tách NULL và số 0

Viết hai truy vấn: một truy vấn tìm sản phẩm có `discount_pct IS NULL`, một truy vấn tìm sản phẩm có `discount_pct = 0`. Dự đoán hai danh sách có trùng nhau không.

### Bài 8. Dùng alias trong ORDER BY

Trả `sku`, `product_name` và `unit_price AS price`; sắp xếp `price` giảm dần, nếu cùng giá thì `sku` tăng dần.

### Bài 9. Dùng CTE để lọc theo biểu thức đã đặt tên

Tạo `WITH priced AS (...)` có cột `selling_price` rồi lấy các sản phẩm giá bán sau giảm lớn hơn hoặc bằng 100000. Không dùng alias của select list trong `WHERE` cùng cấp.

### Bài 10. Đếm các nhóm

Viết query trả `category_code`, số sản phẩm và tổng số lượng tồn theo từng danh mục, sắp xếp theo tên danh mục.

### Bài 11. DISTINCT

Lấy danh sách `category_code` không trùng. Sau đó thử `SELECT DISTINCT category_code, is_active` và giải thích vì sao số hàng có thể khác.

### Bài 12. Chọn sản phẩm giá cao nhất mỗi danh mục

Dùng `DISTINCT ON (category_code)` để lấy `category_code`, `product_id`, `product_name` và `unit_price` của sản phẩm có giá niêm yết lớn nhất trong mỗi danh mục.

### Bài 13. Tìm lỗi alias

Vì sao truy vấn này sai?

```sql
-- Không chạy nguyên mẫu:
-- SELECT unit_price * stock_quantity AS stock_value
-- FROM select_lab.products
-- WHERE stock_value > 100000;
```

Nêu hai cách sửa khác nhau.

### Bài 14. Tạo nhãn hiển thị

Trả một cột `display_label` có dạng `SKU - Tên sản phẩm`. Dùng ít nhất một cách `||` hoặc `concat_ws`.

### Bài 15. Cột ngày mới

Trả `product_id`, `created_at` và `review_date` bằng ngày tạo cộng 30 ngày. Chỉ lấy các sản phẩm tạo trong tháng 10/2026.

### Bài 16. Kiểu dữ liệu của kết quả

Dùng `pg_typeof` để tìm kiểu kết quả của `unit_price * stock_quantity`. Sau đó thử ép kiểu `unit_price::text` và giải thích tác động đến tính toán số.

## 29. Gợi ý lời giải

### Đáp án bài 1

```sql
SELECT product_id, product_name, unit_price
FROM select_lab.products
ORDER BY product_id;
```

### Đáp án bài 2

```sql
SELECT
    product_id AS id,
    product_name AS name,
    unit_price AS listed_price
FROM select_lab.products;
```

### Đáp án bài 3

```sql
SELECT
    product_id,
    product_name,
    unit_price * stock_quantity AS inventory_value
FROM select_lab.products
WHERE unit_price * stock_quantity > 500000
ORDER BY inventory_value DESC, product_id;
```

Đặc biệt, không thể thay biểu thức trong `WHERE` bằng alias `inventory_value` của cùng cấp truy vấn.

### Đáp án bài 4

`a = 0` vì phép chia hai số nguyên; `b = 0.75` và `c = 0.75` vì ít nhất một toán hạng thuộc kiểu thập phân tương ứng.

### Đáp án bài 5

```sql
SELECT
    product_id,
    product_name,
    ROUND(
        unit_price * (1 - COALESCE(discount_pct, 0) / 100),
        2
    ) AS selling_price
FROM select_lab.products
ORDER BY product_id;
```

### Đáp án bài 6

```sql
SELECT
    product_id,
    stock_quantity,
    CASE
        WHEN stock_quantity = 0 THEN 'Hết hàng'
        WHEN stock_quantity < 5 THEN 'Sắp hết'
        ELSE 'Còn hàng'
    END AS stock_label
FROM select_lab.products
ORDER BY product_id;
```

### Đáp án bài 7

```sql
SELECT product_id, product_name
FROM select_lab.products
WHERE discount_pct IS NULL
ORDER BY product_id;

SELECT product_id, product_name
FROM select_lab.products
WHERE discount_pct = 0
ORDER BY product_id;
```

Trên dữ liệu mẫu, NULL thuộc sản phẩm 102 và 106; số 0 thuộc sản phẩm 103. Chúng khác nhau về ý nghĩa và không trùng nhau theo hai điều kiện này.

### Đáp án bài 8

```sql
SELECT
    sku,
    product_name,
    unit_price AS price
FROM select_lab.products
ORDER BY price DESC, sku ASC;
```

### Đáp án bài 9

```sql
WITH priced AS (
    SELECT
        product_id,
        product_name,
        ROUND(
            unit_price * (1 - COALESCE(discount_pct, 0) / 100),
            2
        ) AS selling_price
    FROM select_lab.products
)
SELECT product_id, product_name, selling_price
FROM priced
WHERE selling_price >= 100000
ORDER BY selling_price DESC, product_id;
```

### Đáp án bài 10

```sql
SELECT
    category_code,
    COUNT(*) AS product_count,
    SUM(stock_quantity) AS total_stock
FROM select_lab.products
GROUP BY category_code
ORDER BY category_code;
```

### Đáp án bài 11

```sql
SELECT DISTINCT category_code
FROM select_lab.products
ORDER BY category_code;

SELECT DISTINCT category_code, is_active
FROM select_lab.products
ORDER BY category_code, is_active;
```

Truy vấn đầu có ba danh mục; truy vấn sau có thêm phân biệt theo trạng thái hoạt động. Nhóm accessories có cả sản phẩm active và inactive, vì vậy có thể có thêm một bộ giá trị.

### Đáp án bài 12

```sql
SELECT DISTINCT ON (category_code)
    category_code,
    product_id,
    product_name,
    unit_price
FROM select_lab.products
ORDER BY category_code, unit_price DESC, product_id;
```

`ORDER BY` quy định sản phẩm nào được giữ trong mỗi nhóm `category_code`.

### Đáp án bài 13

`WHERE` không tham chiếu trực tiếp alias đầu ra của `SELECT` cùng cấp. Hai cách sửa:

```sql
-- Lặp biểu thức.
SELECT unit_price * stock_quantity AS stock_value
FROM select_lab.products
WHERE unit_price * stock_quantity > 100000;
```

```sql
-- Tạo cột nguồn ở cấp truy vấn ngoài.
SELECT x.stock_value
FROM (
    SELECT unit_price * stock_quantity AS stock_value
    FROM select_lab.products
) AS x
WHERE x.stock_value > 100000;
```

### Đáp án bài 14

```sql
SELECT sku || ' - ' || product_name AS display_label
FROM select_lab.products
ORDER BY product_id;
```

Hoặc:

```sql
SELECT concat_ws(' - ', sku, product_name) AS display_label
FROM select_lab.products
ORDER BY product_id;
```

### Đáp án bài 15

```sql
SELECT
    product_id,
    created_at,
    created_at + 30 AS review_date
FROM select_lab.products
WHERE created_at >= DATE '2026-10-01'
  AND created_at < DATE '2026-11-01'
ORDER BY created_at, product_id;
```

### Đáp án bài 16

```sql
SELECT
    pg_typeof(unit_price * stock_quantity) AS computed_type,
    unit_price::text AS price_text,
    unit_price AS price_numeric
FROM select_lab.products
WHERE product_id = 101;
```

`price_text` là `text` phù hợp cho hiển thị; nếu muốn tiếp tục tính toán thập phân, dùng `numeric` gốc thay vì chuyển qua chuỗi rồi ép kiểu ngược lại.

## 30. Checklist khi viết SELECT cho ứng dụng

Trước khi đưa câu truy vấn vào Java service, migration hoặc báo cáo:

1. **Chọn đúng cột:** chỉ trả các trường cần dùng; không mặc định `SELECT *` cho API.
2. **Đặt alias rõ:** biểu thức tính toán và cột dùng để mapping có tên đầu ra dễ hiểu, nhất quán.
3. **Phân biệt cột nguồn và alias:** `table_alias.column` ở nguồn khác `AS output_alias`.
4. **Hiểu kiểu dữ liệu:** tránh chia integer ngoài ý định, dùng `numeric` thích hợp với tiền.
5. **Xử lý NULL theo nghiệp vụ:** `COALESCE`, `NULLIF` và `IS NULL` không được dùng chỉ để che dữ liệu thiếu.
6. **Lọc đúng cấp:** `WHERE` không dùng trực tiếp alias `SELECT` cùng cấp; cân nhắc CTE/truy vấn con nếu cần.
7. **Giữ kết quả có thứ tự:** dùng `ORDER BY` với khóa phụ khi phân trang hoặc `LIMIT`.
8. **Dùng hàm và biểu thức có mục đích:** mỗi cột dẫn xuất phải có định nghĩa rõ, không làm thay đổi dữ liệu gốc.
9. **Cẩn trọng JOIN và GROUP BY:** tránh cột mơ hồ, nhân hàng ngoài ý định và chọn cột không thuộc nhóm.
10. **Xem quyền và dữ liệu nhạy cảm:** `SELECT` có thể trả nhiều thông tin hơn mong đợi; các hàm trong `SELECT` không phải luôn thuần đọc.
11. **Đo khi cần tối ưu:** dùng `EXPLAIN` và dữ liệu đại diện, không đưa thêm cột vật lý chỉ vì phép tính trông dài.
12. **Thử với dữ liệu biên:** NULL, tồn kho bằng 0, chuỗi có dấu nháy, giá bằng 0, sản phẩm inactive và các trường hợp không có hàng.

## 31. Tổng kết

Trọng tâm của `SELECT` là **quy định kết quả cần nhận**, không phải sao chép nguyên trạng bảng:

- **Danh sách cột** quyết định cột và thứ tự cột đầu ra; `SELECT *` hữu ích để khám phá nhưng thường nên tránh trong hợp đồng dữ liệu dài hạn.
- **Bí danh cột `AS ...`** đặt tên cho một cột hoặc biểu thức trong kết quả; bí danh bảng trong `FROM` giúp tham chiếu nguồn, đặc biệt khi có JOIN.
- **Biểu thức** có thể là phép tính, phép nối chuỗi, hàm, boolean, xử lý ngày, `CASE`, `COALESCE`, `NULLIF` hoặc ép kiểu; PostgreSQL xác định kiểu kết quả theo ngữ nghĩa biểu thức.
- **NULL khác 0 và chuỗi rỗng**; cách thay thế hoặc hiển thị NULL phải dựa trên chính sách nghiệp vụ.
- **Alias đầu ra dùng được ở `ORDER BY`** và một số trường hợp `GROUP BY` trong PostgreSQL, nhưng không dùng trực tiếp trong `WHERE` cùng cấp. Khi cần lọc theo biểu thức phức tạp có tên, dùng truy vấn con/CTE hoặc viết lại biểu thức.
- **`SELECT` không cập nhật bảng** chỉ vì chọn một biểu thức mang tên `new_price` hay `stock_value`.
- **Thứ tự hàng không được bảo đảm khi thiếu `ORDER BY`**, kể cả khi có `LIMIT`.

Nắm vững select list, alias và biểu thức giúp bạn viết SQL rõ ràng, đọc được kế hoạch truy vấn và xây dựng dữ liệu đầu ra ổn định cho ứng dụng PostgreSQL. Đây cũng là nền tảng để học tiếp các chủ đề `WHERE`, `JOIN`, aggregation, subquery, CTE và tối ưu truy vấn.
