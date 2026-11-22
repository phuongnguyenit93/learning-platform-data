# Từ khóa, định danh, giá trị hằng và biểu thức trong SQL

## 1. Bốn thành phần tạo nên câu lệnh SQL

Một câu lệnh SQL không chỉ là chuỗi từ được đọc từ trái sang phải. Hệ quản trị cơ sở dữ liệu (DBMS) phân tích câu lệnh thành các **token**, kiểm tra cú pháp, giải quyết tên bảng/cột, xác định kiểu dữ liệu của các biểu thức rồi mới lập kế hoạch thực thi. Để đọc và viết SQL rõ ràng, trước tiên cần phân biệt bốn thành phần sau:

| Thành phần | Vai trò | Ví dụ |
| --- | --- | --- |
| **Từ khóa (keyword)** | Mang ý nghĩa ngữ pháp hoặc điều khiển cấu trúc câu lệnh | `SELECT`, `FROM`, `WHERE`, `AND`, `AS` |
| **Định danh (identifier)** | Đặt tên đối tượng hoặc tên tạm để tham chiếu | `products`, `unit_price`, `p`, `inventory_value` |
| **Giá trị hằng (literal)** | Biểu diễn giá trị được viết trực tiếp trong câu lệnh | `25`, `100.50`, `'SQL'`, `TRUE`, `DATE '2026-11-14'` |
| **Biểu thức (expression)** | Kết hợp giá trị, tham chiếu cột, toán tử, hàm… để tạo ra một giá trị hoặc kết quả điều kiện | `unit_price * stock_quantity`, `is_active = TRUE` |

Quan sát câu lệnh:

~~~sql
SELECT
    product_name,
    unit_price * stock_quantity AS inventory_value
FROM products
WHERE is_active = TRUE
  AND stock_quantity > 0
ORDER BY inventory_value DESC;
~~~

Ở đây:

- `SELECT`, `AS`, `FROM`, `WHERE`, `AND`, `ORDER BY`, `DESC` là các từ khóa.
- `product_name`, `unit_price`, `stock_quantity`, `inventory_value` và `products` là các định danh.
- `TRUE` và `0` là các giá trị hằng/giá trị được biểu diễn trực tiếp.
- `unit_price * stock_quantity`, `is_active = TRUE` và `stock_quantity > 0` là biểu thức.
- `*`, `=`, `>` là toán tử; dấu phẩy, dấu chấm và dấu ngoặc có vai trò phân tách hoặc nhóm cú pháp.

**Một token không luôn có một vai trò cố định trong mọi hệ SQL.** Một số từ khóa có thể được dùng làm tên trong ngữ cảnh cho phép; có từ khóa được dành riêng (reserved), có từ không được dành riêng. Quy tắc chính xác phụ thuộc hệ quản trị và phiên bản. Phân biệt đúng ngữ cảnh quan trọng hơn học thuộc một danh sách từ khóa cố định.

## 2. Dữ liệu mẫu cho các ví dụ

Bài sử dụng cú pháp tương thích PostgreSQL và phần lớn SQL tiêu chuẩn. Các khác biệt phổ biến với MySQL, SQL Server và SQLite được nêu ở những chỗ liên quan. Hãy tạo bảng và dữ liệu sau trong một cơ sở dữ liệu thực hành:

~~~sql
CREATE TABLE products (
    product_id       INTEGER PRIMARY KEY,
    product_name     VARCHAR(120) NOT NULL,
    unit_price       DECIMAL(12, 2) NOT NULL,
    stock_quantity   INTEGER NOT NULL,
    is_active        BOOLEAN NOT NULL,
    category         VARCHAR(50),
    created_on       DATE NOT NULL
);

INSERT INTO products (
    product_id, product_name, unit_price,
    stock_quantity, is_active, category, created_on
)
VALUES
    (1, 'O''Reilly SQL Guide', 450000.00, 4, TRUE, 'Sach',      DATE '2026-10-01'),
    (2, 'Ban phim',           900000.00, 0, TRUE, 'Phu kien', DATE '2026-10-15'),
    (3, 'Chuot',              350000.00, 8, FALSE, NULL,      DATE '2026-09-30'),
    (4, 'Man hinh',          3200000.00, 2, TRUE, 'Phu kien', DATE '2026-11-01');
~~~

Ví dụ dùng tên không dấu để người đọc dễ chép giữa các môi trường và giữ nguyên dữ liệu chữ có dấu nếu hệ quản trị, kết nối và kiểu dữ liệu hỗ trợ Unicode. Bảng có bốn sản phẩm: ba sản phẩm đang hoạt động, trong đó bàn phím đã hết hàng; sản phẩm Chuot đã ngừng hoạt động và có `category` là `NULL`.

## 3. Từ khóa: các từ mang ý nghĩa trong ngữ pháp SQL

### 3.1. Từ khóa và cú pháp

SQL sử dụng từ khóa để cho biết loại thao tác và vị trí các thành phần trong câu lệnh. Ví dụ:

~~~sql
SELECT product_id, product_name
FROM products
WHERE stock_quantity > 0
ORDER BY product_id;
~~~

`SELECT` bắt đầu một truy vấn; `FROM` xác định nguồn dữ liệu; `WHERE` giới hạn hàng; `ORDER BY` yêu cầu sắp xếp. Người viết có thể xuống dòng, thụt lề hoặc thêm khoảng trắng giữa các token ở những vị trí hợp lệ mà không đổi ý nghĩa:

~~~sql
select product_id, product_name from products
where stock_quantity > 0 order by product_id;
~~~

**Từ khóa SQL thường không phân biệt chữ hoa/chữ thường**, nhưng viết từ khóa bằng chữ hoa là quy ước giúp nhìn ra cấu trúc, không phải yêu cầu bắt buộc. Không thể chèn khoảng trắng vào giữa ký tự của một từ khóa để biến `SELECT` thành `SE LECT`.

Một số nhóm từ khóa thường gặp:

| Nhóm | Ví dụ | Mục đích |
| --- | --- | --- |
| Truy vấn | `SELECT`, `FROM`, `WHERE`, `JOIN`, `ON` | Lấy và kết hợp dữ liệu |
| Lọc/logic | `AND`, `OR`, `NOT`, `IN`, `BETWEEN`, `LIKE`, `IS NULL` | Tạo điều kiện |
| Phân nhóm/sắp xếp | `GROUP BY`, `HAVING`, `ORDER BY`, `ASC`, `DESC` | Gom nhóm và sắp xếp |
| Thao tác dữ liệu | `INSERT`, `UPDATE`, `DELETE`, `VALUES`, `SET` | Thay đổi dữ liệu |
| Định nghĩa đối tượng | `CREATE`, `TABLE`, `ALTER`, `DROP`, `PRIMARY KEY` | Tạo và thay đổi cấu trúc |
| Điều khiển biểu thức | `CASE`, `WHEN`, `THEN`, `ELSE`, `END`, `CAST` | Biểu đạt tính toán hoặc rẽ nhánh |

`ORDER BY`, `GROUP BY` và `IS NULL` là **cụm cú pháp** gồm nhiều token, không phải một token đơn lẻ.

### 3.2. Reserved keyword và tên đối tượng

Một từ được **dành riêng** không thể tùy tiện dùng làm tên bảng/cột không có dấu định danh; nhiều hệ SQL cũng có từ khóa không dành riêng và cho phép dùng làm tên ở một số vị trí. Ví dụ nên tránh:

~~~sql
-- Có thể gây lỗi cú pháp hoặc phụ thuộc hệ SQL:
CREATE TABLE order (
    select INTEGER
);
~~~

Thay bằng tên rõ nghĩa và ít xung đột hơn:

~~~sql
CREATE TABLE sales_orders (
    sales_order_id INTEGER PRIMARY KEY,
    selected_count INTEGER NOT NULL
);
~~~

Nếu cần giữ tên trùng từ khóa vì phải tương thích với schema đã tồn tại, có thể dùng định danh được bao bằng dấu trích dẫn phù hợp, như `"order"` trong SQL tiêu chuẩn/PostgreSQL. Tuy nhiên cách này buộc người dùng nhất quán với cách viết và đôi khi với cả chữ hoa/chữ thường của tên.

### 3.3. Khoảng trắng, chú thích và dấu kết thúc

SQL thường bỏ qua khoảng trắng thừa giữa token và hỗ trợ hai dạng chú thích thông dụng:

~~~sql
-- Lấy sản phẩm đang hoạt động và còn hàng
SELECT product_name, unit_price
FROM products /* bảng danh mục sản phẩm */
WHERE is_active = TRUE
  AND stock_quantity > 0;
~~~

`--` chú thích từ vị trí đó đến cuối dòng; `/* ... */` tạo chú thích dạng khối. Tính năng chú thích lồng nhau không đồng nhất giữa các hệ quản trị. Dấu chấm phẩy `;` thường phân tách hoặc kết thúc các câu lệnh trong script/SQL client; việc có bắt buộc đặt ở câu cuối hay không phụ thuộc công cụ và giao diện thực thi.

## 4. Định danh: tên bảng, cột, schema và bí danh

### 4.1. Định danh không trích dẫn và định danh trích dẫn

Định danh thường được dùng cho tên bảng, cột, schema, view, index, tên cột kết quả và bí danh (`alias`). Với tính di động cao giữa các hệ SQL, nên đặt tên không dấu theo mẫu chữ cái Latin, chữ số và dấu gạch dưới; bắt đầu bằng chữ cái, chẳng hạn:

~~~text
products
product_id
unit_price
created_on
~~~

Ví dụ sử dụng tên có ý nghĩa:

~~~sql
SELECT p.product_name AS name, p.unit_price AS price
FROM products AS p;
~~~

Trong câu lệnh này `products` là tên bảng, `p` là bí danh bảng, `p.product_name` là tham chiếu có định danh bảng/bí danh, `name` và `price` là bí danh cột kết quả. `AS` chỉ vai trò đặt bí danh; một số hệ hoặc vị trí cú pháp cho phép bỏ từ `AS`.

SQL tiêu chuẩn dùng dấu ngoặc kép để bao định danh cần giữ nguyên ký tự đặc biệt hoặc chữ hoa/chữ thường:

~~~sql
SELECT product_name AS "Product Name"
FROM products
ORDER BY "Product Name";
~~~

`"Product Name"` là **định danh có dấu cách**, không phải chuỗi ký tự. Trong PostgreSQL, định danh **không** trích dẫn được chuyển về chữ thường khi phân tích, còn định danh được trích dẫn giữ nguyên cách viết. Ở những DBMS khác, cách xử lý chữ hoa/chữ thường có thể khác theo hệ, collation hoặc cấu hình.

| Hệ quản trị | Cách trích dẫn định danh thường dùng |
| --- | --- |
| SQL tiêu chuẩn / PostgreSQL | `"Product Name"` |
| MySQL | Dấu backtick (ví dụ: `\`Product Name\``); có thể dùng dấu ngoặc kép khi bật chế độ tương ứng |
| SQL Server | `[Product Name]`; dấu ngoặc kép tùy cấu hình `QUOTED_IDENTIFIER` |
| SQLite | Hỗ trợ dấu ngoặc kép; một số dạng tương thích khác cũng được chấp nhận |

Không nên lạm dụng định danh có dấu cách hoặc trùng từ khóa vì việc trích dẫn liên tục khiến SQL khó bảo trì. Giới hạn độ dài và tập ký tự được phép của định danh cũng tùy DBMS.

### 4.2. Tên đầy đủ và vấn đề trùng tên

Khi truy vấn nhiều bảng, tên cột như `id`, `name` hay `created_on` có thể xuất hiện ở cả hai bên `JOIN`. Cần chỉ rõ bảng hoặc bí danh:

~~~sql
SELECT p.product_id, p.product_name
FROM products AS p
WHERE p.product_id = 1;
~~~

Với cơ sở dữ liệu có nhiều schema, tên đầy đủ có thể mang dạng `schema_name.table_name` hoặc `schema_name.table_name.column_name` tùy ngữ cảnh; một số DBMS hỗ trợ thêm tên database/catalog ở phía trước. Dấu chấm `.` ở đây giúp phân giải thành phần của tên, không phải một phần của chuỗi.

Trong SQL, bí danh của cột được tính tại danh sách `SELECT` **thường không thể dùng ngay trong `WHERE` cùng cấp truy vấn**:

~~~sql
-- Không di động, nhiều hệ sẽ từ chối vì alias chưa khả dụng trong WHERE:
SELECT unit_price * stock_quantity AS inventory_value
FROM products
WHERE inventory_value > 1000000;
~~~

Viết biểu thức trực tiếp trong điều kiện:

~~~sql
SELECT unit_price * stock_quantity AS inventory_value
FROM products
WHERE unit_price * stock_quantity > 1000000
ORDER BY inventory_value DESC;
~~~

Hoặc đưa phép tính vào subquery/CTE để lọc ở cấp truy vấn bên ngoài. Việc dùng alias trong `ORDER BY` được hỗ trợ rộng rãi; phạm vi alias ở `GROUP BY`/`HAVING` có khác biệt theo hệ quản trị, không nên tự suy diễn từ `ORDER BY`.

## 5. Giá trị hằng: viết một giá trị trực tiếp trong SQL

Giá trị hằng là nội dung dữ liệu được ghi ngay trong câu SQL, khác với **định danh** (tên chỉ tới một cột/đối tượng) và **tham số truy vấn** (giá trị được truyền khi thực thi).

### 5.1. Chuỗi ký tự

Trong SQL tiêu chuẩn, chuỗi nằm trong **dấu nháy đơn**:

~~~sql
SELECT product_id, product_name
FROM products
WHERE category = 'Phu kien';
~~~

Hai dấu nháy đơn liên tiếp trong literal biểu diễn **một dấu nháy đơn** trong dữ liệu:

~~~sql
SELECT product_id
FROM products
WHERE product_name = 'O''Reilly SQL Guide';
~~~

Chuỗi `'O''Reilly SQL Guide'` có giá trị thực là `O'Reilly SQL Guide`. Cách dùng backslash để escape chuỗi là tính năng phụ thuộc hệ DB và cấu hình; để SQL di động, ưu tiên quy tắc nhân đôi nháy đơn hoặc tốt hơn là dùng tham số khi giá trị đến từ ứng dụng. Trong ngữ cảnh thông thường, `"Phu kien"` là một **định danh được trích dẫn**, không phải literal chuỗi.

### 5.2. Số nguyên, số thập phân và số dạng khoa học

~~~sql
SELECT
    42 AS integer_value,
    19.95 AS decimal_value,
    1.25e3 AS scientific_notation,
    -7 AS negative_number;
~~~

Với `-7`, dấu trừ thường được hiểu là toán tử đơn ngôi áp vào số `7`. Kiểu suy luận cho một numeric literal và quy tắc tính chính xác có thể khác theo DBMS; ví dụ trong phép chia số nguyên, một số hệ giữ kết quả dạng số nguyên trong khi hệ khác chuyển kiểu. Đối với tiền tệ, ưu tiên cột `DECIMAL(p, s)`/`NUMERIC(p, s)` phù hợp thay vì trông cậy vào phép tính `FLOAT`/dấu phẩy động có thể làm tròn nhị phân.

### 5.3. Giá trị luận lý, NULL và ngày/giờ

~~~sql
SELECT product_name
FROM products
WHERE is_active = TRUE
  AND created_on >= DATE '2026-10-01';
~~~

- `TRUE` và `FALSE` là giá trị luận lý khi DBMS hỗ trợ kiểu boolean và cú pháp tương ứng.
- `NULL` biểu thị **không có giá trị được biết**, không phải số `0`, chuỗi rỗng `''` hay chữ `'NULL'`.
- `DATE '2026-10-01'` là cú pháp typed literal theo SQL tiêu chuẩn; ví dụ khác gồm `TIME '09:30:00'` và `TIMESTAMP '2026-10-01 09:30:00'`. Hỗ trợ các dạng typed literal và diễn giải múi giờ tùy hệ quản trị.

Trong PostgreSQL, `TRUE` và kiểu `BOOLEAN` sử dụng trực tiếp như trên; SQL Server truyền thống thường dùng cột `BIT` với giá trị `1`/`0` thay vì boolean literal tương ứng. Với ứng dụng cần chạy trên nhiều DBMS, cần kiểm tra dialect hoặc để driver/framework tạo cú pháp phù hợp.

Để đổi kiểu rõ ràng, dùng `CAST`:

~~~sql
SELECT
    CAST('125.50' AS DECIMAL(10, 2)) AS amount,
    CAST('2026-11-14' AS DATE) AS selected_date;
~~~

Kết quả của `CAST` phụ thuộc tính hợp lệ của dữ liệu và khả năng chuyển kiểu; một literal chuỗi ngày viết theo định dạng rõ ràng thường ít phụ thuộc thiết lập vùng hơn dạng như `'14/11/26'`. Một số DBMS hỗ trợ thêm literal nhị phân, hexadecimal, interval hoặc cú pháp riêng; không mặc định chúng đều di động.

### 5.4. Literal và tham số không giống nhau

Câu SQL sau có literal cố định:

~~~sql
SELECT product_id, product_name
FROM products
WHERE product_id = 1;
~~~

Ở ứng dụng, khi giá trị được nhập hoặc thay đổi, nên truyền **tham số ràng buộc** thay vì ghép trực tiếp chuỗi SQL:

~~~java
// JDBC PreparedStatement: dấu ? là placeholder cho một giá trị.
String sql = "SELECT product_id, product_name FROM products WHERE product_id = ?";
try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setInt(1, requestedProductId);
    try (ResultSet rs = ps.executeQuery()) {
        while (rs.next()) {
            System.out.println(rs.getString("product_name"));
        }
    }
}
~~~

Prepared statement giúp phân biệt **cú pháp** SQL với **dữ liệu đầu vào**, hỗ trợ xử lý kiểu và ngăn SQL injection khi giá trị được bind đúng. Placeholder thường dùng cho **giá trị**, không thay trực tiếp tên bảng/cột, từ khóa hay hướng `ASC`/`DESC`. Nếu ứng dụng buộc phải thay đổi tên cột hoặc bảng động, hãy chọn từ danh sách tên hợp lệ được kiểm soát, và trích dẫn định danh theo API của DBMS thay vì nối nguyên dữ liệu đầu vào vào câu SQL.

## 6. Biểu thức: từ giá trị đầu vào đến giá trị kết quả

**Biểu thức** có thể đơn giản là một literal (`100`), một tham chiếu cột (`unit_price`) hoặc phức tạp như một phép nhân, lời gọi hàm hay cấu trúc `CASE`. Tùy kiểu dữ liệu và ngữ cảnh, biểu thức cho ra giá trị số, chuỗi, ngày/giờ, luận lý hoặc `NULL`. Một điều kiện trong `WHERE` là biểu thức được diễn giải theo logic SQL.

### 6.1. Biểu thức số học

~~~sql
SELECT
    product_id,
    product_name,
    unit_price,
    stock_quantity,
    unit_price * stock_quantity AS inventory_value,
    unit_price * 0.90 AS discounted_price
FROM products
WHERE is_active = TRUE
ORDER BY product_id;
~~~

Các toán tử số học phổ biến gồm `+`, `-`, `*` và `/` (phép lấy dư `%` không có cú pháp thống nhất ở mọi hệ). Phép nhân và chia thường có độ ưu tiên cao hơn cộng và trừ; dấu ngoặc xác định phép tính khi cần:

~~~sql
SELECT
    10 + 2 * 3 AS a,
    (10 + 2) * 3 AS b;
-- a = 16, b = 36
~~~

Lưu ý kiểu số và làm tròn trong tính toán: `1 / 2` có thể cho kết quả khác nhau giữa các DBMS nếu hai toán hạng là số nguyên; với PostgreSQL, dùng `1.0 / 2` hoặc cast kiểu numeric để biểu đạt ý định nhận kết quả thập phân. Phép chia cho `0` thường gây lỗi, nên phải xử lý theo quy tắc nghiệp vụ, ví dụ dùng `NULLIF(denominator, 0)` khi muốn mẫu số bằng 0 tạo ra `NULL`.

### 6.2. Biểu thức so sánh, kiểm tra tập và mẫu chuỗi

| Toán tử/cú pháp | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| `=`, `<>` | Bằng, khác | `category <> 'Sach'` |
| `>`, `>=`, `<`, `<=` | So sánh thứ tự | `unit_price >= 500000` |
| `BETWEEN ... AND ...` | Khoảng đóng, gồm cả hai đầu mút | `unit_price BETWEEN 100000 AND 1000000` |
| `IN (...)` | Có bằng một trong các giá trị | `category IN ('Sach', 'Phu kien')` |
| `LIKE` | Khớp mẫu văn bản | `product_name LIKE 'Ban%'` |
| `IS NULL`, `IS NOT NULL` | Kiểm tra giá trị thiếu | `category IS NULL` |

Ví dụ:

~~~sql
SELECT product_id, product_name
FROM products
WHERE unit_price BETWEEN 400000 AND 1000000
  AND product_name LIKE 'B%';
~~~

Trong `LIKE`, `%` khớp chuỗi ký tự bất kỳ (kể cả rỗng), `_` khớp đúng một ký tự theo các quy tắc xử lý ký tự của DBMS. Cách so khớp chữ hoa/chữ thường và dấu tiếng Việt phụ thuộc collation hoặc toán tử của từng hệ. Ví dụ `LIKE 'B%'` với dữ liệu mẫu chọn sản phẩm Ban phim.

### 6.3. Logic ba giá trị: TRUE, FALSE, UNKNOWN

SQL khác logic boolean hai giá trị trong nhiều ngôn ngữ lập trình: phép so sánh với `NULL` thường cho **UNKNOWN**, thay vì `TRUE` hoặc `FALSE`. Đặc biệt:

~~~sql
-- Không dùng dấu = để tìm NULL:
SELECT product_id
FROM products
WHERE category = NULL;  -- Không chọn hàng nào trong SQL thông thường

-- Dùng IS NULL:
SELECT product_id, product_name
FROM products
WHERE category IS NULL; -- product_id = 3
~~~

Bảng rút gọn minh họa phép logic ba giá trị:

| A | B | `A AND B` | `A OR B` |
| --- | --- | --- | --- |
| TRUE | UNKNOWN | UNKNOWN | TRUE |
| FALSE | UNKNOWN | FALSE | UNKNOWN |
| UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN |

`NOT UNKNOWN` vẫn là `UNKNOWN`. `WHERE` chỉ giữ các hàng có biểu thức điều kiện là **TRUE**; hàng có điều kiện FALSE hoặc UNKNOWN đều bị loại. Vì thế:

~~~sql
SELECT product_id, product_name
FROM products
WHERE category <> 'Phu kien';
~~~

Truy vấn chỉ chọn sản phẩm có `category` đã biết và khác `Phu kien` (trên dữ liệu mẫu là sản phẩm 1); nó **không** chọn sản phẩm 3 có `category = NULL`. Muốn giữ cả sản phẩm chưa phân loại, viết rõ:

~~~sql
WHERE category <> 'Phu kien' OR category IS NULL
~~~

Thận trọng với `NOT IN` khi danh sách hoặc subquery có thể chứa `NULL`: kết quả có thể trở thành UNKNOWN trên các hàng tưởng là đủ điều kiện. Với truy vấn chống tồn tại, `NOT EXISTS` cùng điều kiện tương quan rõ ràng thường dễ suy luận hơn.

### 6.4. Ưu tiên toán tử và dấu ngoặc

Trong biểu thức luận lý thông dụng, thứ tự ưu tiên thường là `NOT` → `AND` → `OR`; các phép so sánh tạo điều kiện trước khi các toán tử logic kết hợp chúng. Tuy nhiên các toán tử khác nhau, đặc biệt toán tử đặc thù DBMS, có thứ tự ưu tiên riêng. **Đặt dấu ngoặc khi có thể gây hiểu nhầm**:

~~~sql
-- Chọn sản phẩm đang hoạt động và (thuộc nhóm Sach hoặc có giá >= 2 triệu):
SELECT product_id, product_name
FROM products
WHERE is_active = TRUE
  AND (category = 'Sach' OR unit_price >= 2000000);
~~~

Nếu bỏ ngoặc thành `is_active = TRUE AND category = 'Sach' OR unit_price >= 2000000`, một sản phẩm không còn hoạt động nhưng có giá cao vẫn có thể được chọn vì phép `OR` nằm ngoài điều kiện `is_active`. Dấu ngoặc vừa chống lỗi logic vừa làm ý nghĩa nghiệp vụ rõ ràng.

### 6.5. Hàm, CASE, COALESCE và phép nối chuỗi

Hàm SQL là thành phần của biểu thức: nhận đối số, tính kết quả theo kiểu và quy tắc của hàm.

~~~sql
SELECT
    product_name,
    UPPER(product_name) AS uppercase_name,
    COALESCE(category, 'Chua phan loai') AS category_display,
    CASE
        WHEN is_active = FALSE THEN 'Ngung kinh doanh'
        WHEN stock_quantity = 0 THEN 'Het hang'
        ELSE 'Con hang'
    END AS sale_status
FROM products
ORDER BY product_id;
~~~

- `UPPER(expression)` chuyển chữ cái sang chữ hoa theo khả năng xử lý ký tự/collation của DBMS.
- `COALESCE(a, b, ...)` trả giá trị đầu tiên **khác NULL**, nên có thể thay `NULL` bằng nhãn hiển thị.
- `CASE WHEN ... THEN ... ELSE ... END` tạo biểu thức điều kiện; nhánh đầu tiên có điều kiện TRUE được chọn, còn nhánh `ELSE` áp dụng khi không có nhánh nào thỏa. Nếu thiếu `ELSE`, kết quả khi không nhánh nào thỏa là `NULL`.
- Phép nối chuỗi chuẩn SQL dùng `||`, ví dụ `'Ma ' || CAST(product_id AS VARCHAR(20))`; SQL Server thường dùng `+`, MySQL có `CONCAT()` và `||` có thể mang nghĩa logic OR tùy chế độ. Đây là ví dụ điển hình cho sự khác nhau giữa dialects.

Hàm tổng hợp như `COUNT(*)`, `SUM(unit_price)` hoặc `AVG(unit_price)` được sử dụng trong ngữ cảnh nhóm/truy vấn thích hợp; hàm cửa sổ như `ROW_NUMBER() OVER (...)` có quy tắc vị trí riêng. Không phải biểu thức bất kỳ nào cũng hợp lệ tại mọi vị trí trong câu SQL.

## 7. Kiểu dữ liệu và ngữ cảnh quyết định cách hiểu biểu thức

Cùng một ký hiệu có thể mang ý nghĩa khác tùy kiểu dữ liệu và dialect:

~~~sql
SELECT
    5 + 2 AS arithmetic_sum,
    '5' || '2' AS text_concatenation;
~~~

Ở hệ hỗ trợ toán tử `||` theo chuẩn, biểu thức đầu trả về số `7`, biểu thức thứ hai trả về chuỗi `'52'`. Đừng nhầm toán tử với cách nối chuỗi trong một ngôn ngữ khác.

Một số phép toán chuyển kiểu ngầm giữa chuỗi và số có thể được DBMS chấp nhận nhưng cũng có thể bị từ chối hoặc phụ thuộc cấu hình. Thay vì viết `'10' + 5` và trông đợi hệ tự hiểu ý định, dùng `CAST('10' AS INTEGER) + 5` khi muốn tính số học.

Khi biểu thức có `NULL`, phép tính số học thường trả `NULL`: chẳng hạn `unit_price * NULL` không cho số `0`. Nếu dữ liệu đầu vào có thể `NULL`, cần xác định ý nghĩa nghiệp vụ trước khi dùng `COALESCE(..., 0)`, bởi “chưa biết” và “thực sự bằng 0” không tương đương.

Cần nhớ thêm rằng một câu truy vấn thường trải qua các giai đoạn logic như xác định nguồn dữ liệu (`FROM`), lọc hàng (`WHERE`), nhóm (`GROUP BY`), lọc nhóm (`HAVING`), tạo kết quả (`SELECT`) và sắp xếp (`ORDER BY`). Đây là mô hình để suy luận tính hợp lệ của cột và biểu thức, **không phải** một chuỗi thao tác vật lý mà trình tối ưu SQL luôn thực hiện nguyên thứ tự đó.

## 8. Các lỗi thường gặp khi kết hợp bốn thành phần

| Cách viết dễ sai | Vấn đề | Cách viết phù hợp |
| --- | --- | --- |
| `WHERE category = "Sach"` | Dấu ngoặc kép thường chỉ định danh, không phải literal | `WHERE category = 'Sach'` |
| `WHERE category = NULL` | So sánh với NULL không cho TRUE | `WHERE category IS NULL` |
| `WHERE category = 'NULL'` | Đang so với chuỗi gồm 4 ký tự, không phải NULL | `IS NULL` nếu cần tìm giá trị thiếu |
| `SELECT unit_price stock_quantity` | Có thể bị hiểu `stock_quantity` là alias thay vì phép tính | `SELECT unit_price * stock_quantity` |
| `WHERE is_active = TRUE AND category = 'Sach' OR stock_quantity > 0` | `OR` có thể mở rộng tập kết quả ngoài ý định | Thêm ngoặc quanh nhóm điều kiện mong muốn |
| `WHERE inventory_value > 0` khi alias mới khai báo tại `SELECT` | Alias không khả dụng ở `WHERE` cùng cấp trong SQL thông thường | Lặp biểu thức hoặc đặt vào subquery/CTE |
| Ghép chuỗi tạo SQL từ ô nhập người dùng | Có nguy cơ SQL injection và sai kiểu/escape | Dùng parameter binding |
| Dùng tên cột `order` không trích dẫn | Dễ trùng từ khóa reserved | Chọn tên khác hoặc trích dẫn đúng theo dialect |

**Quy tắc đọc câu lệnh:** xác định từ khóa để thấy cấu trúc; xác định định danh để biết đang tham chiếu đối tượng nào; đọc literal để biết giá trị cố định; cuối cùng phân tích kiểu dữ liệu và ưu tiên toán tử để hiểu biểu thức.

## 9. Thực hành tự kiểm tra

Sử dụng bảng `products` ở mục 2, chưa sửa dữ liệu.

### Bài 1 — Nhận dạng thành phần

Trong câu SQL dưới đây, hãy tìm ít nhất bốn từ khóa, bốn định danh, hai giá trị hằng và hai biểu thức:

~~~sql
SELECT product_name, unit_price * 2 AS doubled_price
FROM products
WHERE category = 'Phu kien' AND is_active = TRUE;
~~~

**Gợi ý đáp án:** từ khóa gồm `SELECT`, `AS`, `FROM`, `WHERE`, `AND`; định danh gồm `product_name`, `unit_price`, `doubled_price`, `products`, `category`, `is_active`; literal gồm `2`, `'Phu kien'`, `TRUE`; biểu thức gồm `unit_price * 2` và `category = 'Phu kien'`.

### Bài 2 — Viết biểu thức được đặt bí danh

Lấy tên sản phẩm, giá gốc, giá sau giảm 10% của những sản phẩm còn hoạt động và còn hàng. Sắp theo giá sau giảm từ cao đến thấp, khi bằng giá thì theo `product_id` tăng dần.

~~~sql
SELECT
    product_name,
    unit_price,
    unit_price * 0.90 AS sale_price
FROM products
WHERE is_active = TRUE
  AND stock_quantity > 0
ORDER BY sale_price DESC, product_id ASC;
~~~

Với dữ liệu mẫu, kết quả theo thứ tự là Man hinh (2.880.000) rồi O'Reilly SQL Guide (405.000). Câu truy vấn dùng từ khóa để xác định mệnh đề, định danh để gọi cột, literal cho giá trị giảm giá và biểu thức để tính `sale_price`.

### Bài 3 — Phân biệt chuỗi và định danh

Vì sao `WHERE product_name = 'Ban phim'` và `WHERE product_name = "Ban phim"` không tương đương trong SQL tiêu chuẩn? Trả lời: dấu nháy đơn chứa dữ liệu chuỗi; dấu ngoặc kép trích dẫn **tên cột/đối tượng**. Nếu không có cột tên `Ban phim`, cách thứ hai thường gây lỗi phân giải tên.

### Bài 4 — Giải thích NULL và ưu tiên logic

Dự đoán câu truy vấn sau có lấy sản phẩm Chuot hay không:

~~~sql
SELECT product_id
FROM products
WHERE category <> 'Sach' OR is_active = FALSE;
~~~

**Đáp án:** có. Với Chuot, `category <> 'Sach'` cho UNKNOWN, còn `is_active = FALSE` cho TRUE; `UNKNOWN OR TRUE` là TRUE. Nếu bỏ vế `OR is_active = FALSE`, Chuot sẽ không được chọn vì `WHERE` loại UNKNOWN.

### Bài 5 — Tham số và định danh động

Ứng dụng nhận một mã sản phẩm do người dùng nhập. Hãy nêu cách tìm theo mã đó mà không nối đầu vào trực tiếp thành SQL, và giải thích vì sao không thể dùng `?` để thay tên bảng trong lệnh `FROM ?`.

**Gợi ý:** viết `WHERE product_id = ?` rồi bind mã bằng prepared statement (chọn API setter theo kiểu cột). Placeholder đại diện cho **giá trị dữ liệu** trong một biểu thức; cấu trúc và định danh của truy vấn phải được phân tích trước khi binding, nên tên bảng/cột động cần được ứng dụng lựa chọn từ danh sách cho phép.

## 10. Ghi nhớ

Một câu SQL dễ hiểu khi người viết phân biệt rành mạch **từ khóa** (cấu trúc câu lệnh), **định danh** (tên đối tượng/cột), **giá trị hằng** (dữ liệu ghi trực tiếp) và **biểu thức** (quy tắc tính toán hoặc lọc). Dấu nháy đơn dành cho chuỗi, dấu ngoặc kép tiêu chuẩn dành cho định danh, còn `NULL` cần được xử lý theo logic ba giá trị. Đối với truy vấn trong ứng dụng, hãy bind giá trị bằng tham số và chỉ cho phép các định danh động đã được kiểm soát. Cuối cùng, luôn xét kiểu dữ liệu, dấu ngoặc và dialect của hệ quản trị trước khi kết luận ý nghĩa một biểu thức.
