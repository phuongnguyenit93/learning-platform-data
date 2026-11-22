# Cấu trúc SELECT, FROM và tập kết quả

## 1. Một câu truy vấn SQL tạo ra tập kết quả như thế nào?

Khi cần đọc dữ liệu từ cơ sở dữ liệu quan hệ, câu lệnh phổ biến nhất là `SELECT`. Ở mức cơ bản, câu truy vấn trả lời hai câu hỏi:

- **`FROM`:** Dữ liệu đầu vào lấy từ bảng, view hoặc nguồn quan hệ nào?
- **`SELECT`:** Mỗi hàng đầu ra cần chứa những cột hay biểu thức nào?

Ví dụ:

~~~sql
SELECT product_id, product_name, unit_price
FROM products;
~~~

Câu lệnh yêu cầu lấy ba cột của bảng `products`. Giá trị trả về được gọi là **tập kết quả (result set)**: một kết quả dạng bảng gồm các hàng và cột. Mặc dù thường gọi là “tập”, kết quả SQL thông thường có thể chứa **hàng trùng nhau**. Ngoài ra, nếu không dùng `ORDER BY` thì **thứ tự hàng không được bảo đảm**.

Mô hình cơ bản:

~~~text
             Nguồn dữ liệu
           products (6 hàng)
                  │
                  ▼
       FROM xác định các hàng
                  │
                  ▼
       SELECT chọn/tính các cột
                  │
                  ▼
             TẬP KẾT QUẢ
       ┌────────────┬────────────┐
       │ product_id │ ...        │
       ├────────────┼────────────┤
       │ 1          │ ...        │
       │ 2          │ ...        │
       │ ...        │ ...        │
       └────────────┴────────────┘
~~~

Sơ đồ giúp hiểu **ý nghĩa logic** của câu truy vấn; nó không khẳng định DBMS buộc phải đọc từng hàng, rồi chọn từng cột theo đúng thứ tự vật lý đó. Bộ tối ưu của hệ quản trị có thể sử dụng chỉ mục, thay đổi kế hoạch đọc hoặc thực hiện nhiều phép toán cùng lúc nhưng vẫn phải bảo toàn kết quả theo ngữ nghĩa SQL.

### Cú pháp nền tảng

~~~sql
SELECT [DISTINCT] <danh_sach_cot_hoac_bieu_thuc>
FROM <nguon_du_lieu>;
~~~

Dấu `[ ]` trong mô tả cú pháp cho biết `DISTINCT` là phần **tùy chọn**, không phải ký tự gõ nguyên vào SQL. Dấu `<...>` là ký hiệu mô tả vị trí cần thay bằng tên cột hay bảng thật.

Trong thực tế, câu truy vấn còn có thể có `WHERE`, `GROUP BY`, `HAVING`, `ORDER BY` và giới hạn số hàng. Tuy nhiên, hiểu rõ `SELECT`, `FROM` và hình dạng kết quả là nền tảng để đọc các cấu trúc phức tạp hơn.

## 2. Tạo dữ liệu thực hành

Bài này sử dụng hai bảng nhỏ: `categories` (danh mục) và `products` (sản phẩm). Các ví dụ có thể dùng trên nhiều DBMS với cú pháp gần chuẩn SQL; phần nào có khác biệt giữa các hệ sẽ được chỉ rõ.

~~~sql
CREATE TABLE categories (
    category_id   INTEGER PRIMARY KEY,
    category_name VARCHAR(80) NOT NULL
);

CREATE TABLE products (
    product_id        INTEGER PRIMARY KEY,
    product_name      VARCHAR(100) NOT NULL,
    category_id       INTEGER NOT NULL,
    unit_price        DECIMAL(12, 2) NOT NULL,
    quantity_in_stock INTEGER NOT NULL,
    origin_country    VARCHAR(30),
    FOREIGN KEY (category_id)
        REFERENCES categories(category_id)
);

INSERT INTO categories (category_id, category_name) VALUES
    (10, 'Van phong pham'),
    (20, 'Thiet bi'),
    (30, 'Dich vu');

INSERT INTO products (
    product_id, product_name, category_id,
    unit_price, quantity_in_stock, origin_country
) VALUES
    (1, 'So tay',  10,  45000.00, 12, 'VN'),
    (2, 'But bi',  10,  12000.00, 50, 'VN'),
    (3, 'Ban phim',20, 750000.00,  4, 'CN'),
    (4, 'Chuot',   20, 250000.00,  0, NULL),
    (5, 'Cap USB', 20,  12000.00, 20, 'CN'),
    (6, 'Gia do',  20, 350000.00,  6, 'VN');
~~~

Bảng `categories` có ba hàng; danh mục `Dich vu` chưa có sản phẩm. Bảng `products` có sáu hàng; `But bi` và `Cap USB` cùng giá `12000`, còn `Chuot` chưa có thông tin `origin_country` (giá trị `NULL`).

Để nhìn dữ liệu theo thứ tự dự đoán được:

~~~sql
SELECT
    product_id,
    product_name,
    category_id,
    unit_price,
    quantity_in_stock,
    origin_country
FROM products
ORDER BY product_id;
~~~

Kết quả:

| product_id | product_name | category_id | unit_price | quantity_in_stock | origin_country |
| ---: | --- | ---: | ---: | ---: | --- |
| 1 | So tay | 10 | 45000.00 | 12 | VN |
| 2 | But bi | 10 | 12000.00 | 50 | VN |
| 3 | Ban phim | 20 | 750000.00 | 4 | CN |
| 4 | Chuot | 20 | 250000.00 | 0 | NULL |
| 5 | Cap USB | 20 | 12000.00 | 20 | CN |
| 6 | Gia do | 20 | 350000.00 | 6 | VN |

Bảng trên biểu diễn `NULL` bằng chữ để tiện quan sát; cách một công cụ SQL hiển thị `NULL` có thể khác. Việc sắp xếp ở đây do `ORDER BY product_id`, không phải vì các hàng luôn được lưu theo thứ tự khóa chính.

## 3. SELECT quyết định những gì xuất hiện ở đầu ra

### 3.1. Chọn cột: projection

Một phép **chiếu (projection)** lấy các thuộc tính mà truy vấn cần trả về. Trong SQL:

~~~sql
SELECT product_id, product_name
FROM products
ORDER BY product_id;
~~~

| product_id | product_name |
| ---: | --- |
| 1 | So tay |
| 2 | But bi |
| 3 | Ban phim |
| 4 | Chuot |
| 5 | Cap USB |
| 6 | Gia do |

Bảng nguồn có sáu cột nhưng kết quả chỉ có **hai cột**, do danh sách `SELECT` quyết định. Việc chọn ít cột có thể giảm lượng dữ liệu truyền và tránh đưa dữ liệu không cần thiết tới ứng dụng. DBMS cũng có thể tận dụng chỉ mục thích hợp để không phải đọc tất cả các cột từ bảng; lợi ích thực tế tùy kế hoạch truy vấn.

Thứ tự cột của kết quả được quyết định bởi thứ tự biểu thức trong danh sách `SELECT`:

~~~sql
SELECT product_name, product_id
FROM products
ORDER BY product_id;
~~~

Lúc này cột `product_name` đứng trước `product_id`. **Thứ tự cột** và **thứ tự hàng** là hai khái niệm khác nhau: danh sách `SELECT` đặt thứ tự cột, còn `ORDER BY` kiểm soát thứ tự hàng.

### 3.2. SELECT * và SELECT bảng.*

Ký hiệu `*` trong danh sách `SELECT` có nghĩa lấy các cột của nguồn dữ liệu theo quy tắc mở rộng cột của DBMS:

~~~sql
SELECT *
FROM products;
~~~

Lệnh này lấy tất cả các cột hiện có của `products`. Có thể dùng khi học hoặc thăm dò bảng, nhưng trong ứng dụng ổn định nên cân nhắc liệt kê rõ các cột cần thiết:

~~~sql
SELECT product_id, product_name, unit_price
FROM products;
~~~

Những lý do nên cẩn trọng với `SELECT *`:

- Khi bảng thêm hoặc xóa cột, hình dạng kết quả thay đổi; API, mapper hay bản xuất dữ liệu có thể bị ảnh hưởng.
- Truyền các cột lớn hoặc nhạy cảm mà consumer không cần làm tăng chi phí hoặc phạm vi lộ dữ liệu.
- Khi ghép nhiều bảng, tên cột như `category_id` có thể trùng nhau và khó truy cập bằng tên.
- Trình tối ưu có thể có ít cơ hội tận dụng chỉ mục bao phủ (covering index) nếu phải lấy mọi cột.

Trong truy vấn có nhiều nguồn, cú pháp `p.*` lấy mọi cột **thuộc nguồn có bí danh `p`**:

~~~sql
SELECT p.*, c.category_name
FROM products AS p
JOIN categories AS c
    ON c.category_id = p.category_id
ORDER BY p.product_id;
~~~

Kết quả có các cột của `products` rồi thêm `category_name`. `p.*` khác với toán tử nhân `*` trong một biểu thức số học.

### 3.3. Biểu thức trong danh sách SELECT

`SELECT` có thể tính một giá trị mới cho mỗi hàng đầu vào. Chẳng hạn, giá trị tồn kho bằng đơn giá nhân số lượng:

~~~sql
SELECT
    product_id,
    product_name,
    unit_price * quantity_in_stock AS inventory_value
FROM products
ORDER BY product_id;
~~~

| product_id | product_name | inventory_value |
| ---: | --- | ---: |
| 1 | So tay | 540000.00 |
| 2 | But bi | 600000.00 |
| 3 | Ban phim | 3000000.00 |
| 4 | Chuot | 0.00 |
| 5 | Cap USB | 240000.00 |
| 6 | Gia do | 2100000.00 |

`inventory_value` là cột **tính ra trong kết quả truy vấn**, không cần là một cột lưu sẵn của bảng. Kiểu dữ liệu và cách hiển thị số chữ số thập phân tùy DBMS/client, nhưng giá trị số học ở đây như bảng trên.

Danh sách `SELECT` còn có thể chứa literal và lời gọi hàm:

~~~sql
SELECT
    product_id,
    product_name,
    'San pham' AS record_type,
    unit_price * 0.90 AS discounted_price
FROM products
ORDER BY product_id;
~~~

Giá trị `'San pham'` được lặp lại cho mỗi hàng đầu ra. `discounted_price` được tính theo từng sản phẩm. Nếu cần áp dụng quy tắc làm tròn đặc biệt cho tiền, phải xác định rõ kiểu dữ liệu và cách dùng hàm làm tròn phù hợp.

### 3.4. Bí danh cột với AS

`AS` đặt **bí danh (alias)** cho cột trong kết quả:

~~~sql
SELECT
    product_name AS name,
    unit_price AS price,
    quantity_in_stock AS stock
FROM products
ORDER BY product_id;
~~~

| name | price | stock |
| --- | ---: | ---: |
| So tay | 45000.00 | 12 |
| But bi | 12000.00 | 50 |
| Ban phim | 750000.00 | 4 |
| Chuot | 250000.00 | 0 |
| Cap USB | 12000.00 | 20 |
| Gia do | 350000.00 | 6 |

Alias **không đổi tên cột vật lý** trong bảng. Nó chỉ đặt tên cho biểu thức đầu ra trong phạm vi câu truy vấn. Nhiều hệ cho phép bỏ từ `AS` khi đặt alias, nhưng viết tường minh giúp dễ đọc.

Một số hệ hỗ trợ tên cột có dấu cách khi trích dẫn định danh:

~~~sql
SELECT product_name AS "Ten san pham"
FROM products;
~~~

Dấu ngoặc kép trích dẫn **định danh** theo SQL tiêu chuẩn; dấu nháy đơn dùng cho **chuỗi dữ liệu**. Cú pháp trích dẫn định danh có khác biệt giữa PostgreSQL, MySQL, SQL Server và các hệ khác.

## 4. FROM xác định nguồn hàng

### 4.1. Bảng là nguồn dữ liệu cơ bản

`FROM products` cho biết `products` là nguồn hàng. Nếu câu lệnh chọn trực tiếp các cột từ một bảng, không có bộ lọc, gom nhóm, `DISTINCT` hay phép kết hợp, số hàng kết quả thường bằng số hàng nguồn:

~~~sql
SELECT product_name
FROM products;
~~~

Với dữ liệu mẫu: **sáu hàng đầu ra**, một hàng cho mỗi sản phẩm. Dù chỉ chọn một cột, mỗi bản ghi nguồn vẫn đóng góp một dòng kết quả.

Có thể chọn từ bảng khác:

~~~sql
SELECT category_id, category_name
FROM categories
ORDER BY category_id;
~~~

| category_id | category_name |
| ---: | --- |
| 10 | Van phong pham |
| 20 | Thiet bi |
| 30 | Dich vu |

Từ khóa `FROM` không chỉ định “thứ tự đọc hàng”; DBMS tự chọn cách thực thi phù hợp.

### 4.2. Định danh đủ tên và bí danh bảng

Trong hệ quản trị có schema, bảng có thể được gọi bằng tên đầy đủ như `shop.products` thay vì `products`. Cách phân giải tên phụ thuộc DBMS và cấu hình schema/search path.

Đặt bí danh cho bảng giúp câu truy vấn ngắn gọn, nhất là khi có nhiều nguồn:

~~~sql
SELECT
    p.product_id,
    p.product_name,
    p.unit_price
FROM products AS p
ORDER BY p.product_id;
~~~

Ở đây `p` là bí danh của bảng `products` **trong phạm vi câu truy vấn**. `p.product_name` nghĩa là cột `product_name` thuộc nguồn `p`. Nó không đổi tên bảng thật.

Khi có nhiều bảng cùng chứa cột `category_id`, dùng tiền tố bí danh tránh nhập nhằng:

~~~sql
SELECT
    p.product_name,
    c.category_name
FROM products AS p
JOIN categories AS c
    ON c.category_id = p.category_id
ORDER BY p.product_id;
~~~

Kết quả:

| product_name | category_name |
| --- | --- |
| So tay | Van phong pham |
| But bi | Van phong pham |
| Ban phim | Thiet bi |
| Chuot | Thiet bi |
| Cap USB | Thiet bi |
| Gia do | Thiet bi |

`JOIN` kết hợp hàng dựa trên điều kiện trong `ON`. Ở đây mỗi sản phẩm có đúng một danh mục hợp lệ theo khóa ngoại, nên vẫn có sáu hàng. Khi nối các quan hệ một-nhiều, số hàng có thể tăng vì một hàng phía trái khớp nhiều hàng phía phải.

### 4.3. FROM có thể chứa nhiều nguồn

Không phải `FROM` lúc nào cũng là một bảng vật lý. Nguồn có thể là:

- Bảng thường hoặc view.
- Kết quả của một truy vấn con được đặt trong ngoặc, gọi là **derived table**.
- Các bảng được kết hợp bằng `JOIN`.
- Nguồn dữ liệu do các cấu trúc/hàm đặc thù DBMS cung cấp.

Ví dụ dùng một truy vấn con làm nguồn:

~~~sql
SELECT
    x.product_name,
    x.inventory_value
FROM (
    SELECT
        product_name,
        unit_price * quantity_in_stock AS inventory_value
    FROM products
) AS x
WHERE x.inventory_value >= 500000
ORDER BY x.inventory_value DESC, x.product_name;
~~~

| product_name | inventory_value |
| --- | ---: |
| Ban phim | 3000000.00 |
| Gia do | 2100000.00 |
| But bi | 600000.00 |
| So tay | 540000.00 |

Truy vấn bên trong tạo nguồn hai cột `product_name` và `inventory_value`. Truy vấn bên ngoài đọc nguồn đó bằng bí danh `x` rồi lọc/sắp xếp. Phần lớn DBMS yêu cầu bí danh cho derived table; cách viết và quy tắc có thể khác giữa các hệ.

### 4.4. CROSS JOIN tạo tích Descartes

Khi kết hợp hai bảng mà **không đặt điều kiện ghép**, có thể tạo ra tất cả cặp hàng:

~~~sql
SELECT
    p.product_name,
    c.category_name
FROM products AS p
CROSS JOIN categories AS c
ORDER BY p.product_id, c.category_id;
~~~

Bảng `products` có 6 hàng, bảng `categories` có 3 hàng. `CROSS JOIN` cho **6 × 3 = 18 hàng**, dù một sản phẩm chỉ thuộc một danh mục thật. Phép này hợp lệ khi muốn tạo mọi tổ hợp, nhưng thường không đúng nếu mục tiêu là ghép theo `category_id`.

So sánh với `JOIN ... ON p.category_id = c.category_id` ở mục trước chỉ trả 6 hàng. Sai sót quên điều kiện nối (ở dạng phép nối ngầm hoặc dùng sai `CROSS JOIN`) có thể làm số hàng tăng mạnh và gây sai dữ liệu. Để diễn đạt quan hệ, ưu tiên `JOIN ... ON` tường minh.

## 5. “Tập kết quả” chính xác gồm những gì?

Một result set không chỉ là các ô dữ liệu được hiển thị. Có thể nhìn nó qua các đặc tính:

| Thuộc tính | Ý nghĩa |
| --- | --- |
| **Số cột** | Phụ thuộc các mục trong danh sách `SELECT` sau khi mở rộng `*` |
| **Tên cột** | Từ tên cột gốc, alias hoặc tên do DBMS tạo cho biểu thức |
| **Kiểu cột** | Từ kiểu cột gốc và quy tắc suy diễn kiểu biểu thức |
| **Số hàng** | Phụ thuộc số hàng nguồn và các phép lọc, nối, nhóm, khử trùng hoặc tổng hợp |
| **Giá trị ô** | Có thể là dữ liệu gốc, kết quả tính toán hoặc `NULL` |
| **Thứ tự cột** | Theo thứ tự các biểu thức trong `SELECT` |
| **Thứ tự hàng** | Chỉ được bảo đảm khi có `ORDER BY` thích hợp ở truy vấn cuối |
| **Khả năng trùng hàng** | Mặc định được phép; `DISTINCT` mới loại hàng trùng của đầu ra |

### 5.1. SELECT không tự loại các hàng trùng

Một điểm khác với tập hợp trong toán học: SQL mặc định dùng ngữ nghĩa **đa tập (bag/multiset)** trong nhiều phép xử lý, tức là kết quả có thể lặp.

~~~sql
SELECT unit_price
FROM products
ORDER BY unit_price;
~~~

| unit_price |
| ---: |
| 12000.00 |
| 12000.00 |
| 45000.00 |
| 250000.00 |
| 350000.00 |
| 750000.00 |

Hai hàng `12000.00` đến từ `But bi` và `Cap USB`. Câu lệnh chỉ chọn cột `unit_price`, nên không còn nhìn thấy sản phẩm nào tạo ra hàng đó, nhưng cả hai hàng vẫn tồn tại.

Dùng `DISTINCT` nếu muốn mỗi giá trị chỉ xuất hiện một lần:

~~~sql
SELECT DISTINCT unit_price
FROM products
ORDER BY unit_price;
~~~

| unit_price |
| ---: |
| 12000.00 |
| 45000.00 |
| 250000.00 |
| 350000.00 |
| 750000.00 |

`DISTINCT` xét **toàn bộ các biểu thức trong danh sách `SELECT`**: nếu chọn hai cột, chỉ những hàng có cùng cặp giá trị mới được coi là trùng. `NULL` trong các phép loại trùng có quy tắc SQL riêng: các hàng có `NULL` tương ứng có thể bị gộp làm một hàng theo ngữ nghĩa `DISTINCT`, dù biểu thức `NULL = NULL` không trả `TRUE`.

`DISTINCT` có thể cần sắp xếp hoặc hash để loại trùng; không dùng nó một cách mặc định nhằm che lỗi `JOIN` gây nhân bản hàng.

### 5.2. Hàng không có thứ tự mặc định

Câu này:

~~~sql
SELECT product_id, product_name
FROM products;
~~~

không bảo đảm sản phẩm 1 đứng trước sản phẩm 2. Mặc dù một SQL client có thể hiển thị theo thứ tự chèn, theo khóa chính hoặc theo thứ tự index, DBMS có quyền chọn kế hoạch đọc khác và trả hàng theo trật tự khác.

Muốn sắp xếp ổn định:

~~~sql
SELECT product_id, product_name, unit_price
FROM products
ORDER BY unit_price ASC, product_id ASC;
~~~

Thứ tự sẽ là `But bi` (ID 2), `Cap USB` (ID 5), `So tay` (ID 1), `Chuot` (ID 4), `Gia do` (ID 6), `Ban phim` (ID 3). Hai sản phẩm cùng giá `12000.00` được phân định thêm bằng `product_id`.

Một `ORDER BY` chỉ trên cột giá có thể để các hàng bằng giá xuất hiện theo bất kỳ thứ tự nào. Để phân trang hoặc kiểm tra snapshot ổn định, cần tiêu chí phá hòa đủ xác định, thường là khóa chính.

Thứ tự bên trong một truy vấn con hoặc view cũng **không thay thế** `ORDER BY` của truy vấn ngoài khi muốn bảo đảm thứ tự kết quả cuối. Các hệ SQL có những quy tắc riêng về vị trí `ORDER BY` trong truy vấn con.

### 5.3. Result set có thể rỗng

~~~sql
SELECT product_id, product_name
FROM products
WHERE unit_price > 10000000;
~~~

Với dữ liệu mẫu, truy vấn trả **0 hàng** nhưng vẫn có hai cột `product_id` và `product_name` trong metadata kết quả. “Không có hàng khớp” không giống “truy vấn sai cú pháp”.

Ngược lại, một truy vấn dùng phép tổng hợp **không có `GROUP BY`** có thể trả **một hàng** ngay cả khi bộ dữ liệu đầu vào rỗng:

~~~sql
SELECT COUNT(*) AS matching_products
FROM products
WHERE unit_price > 10000000;
-- Một hàng, matching_products = 0.
~~~

Số hàng của result set phải được hiểu theo toàn bộ cấu trúc truy vấn, không chỉ theo số hàng của bảng nguồn.

### 5.4. Giá trị NULL trong tập kết quả

~~~sql
SELECT product_id, product_name, origin_country
FROM products
ORDER BY product_id;
~~~

`Chuot` có `origin_country = NULL`: đây là **giá trị chưa biết hoặc chưa có**, không đồng nghĩa với chuỗi rỗng `''` hay chữ `'NULL'`.

Các ứng dụng đọc result set cần xử lý `NULL` theo kiểu dữ liệu. Chẳng hạn, trong JDBC, `ResultSet.getString(...)` có thể trả `null` cho cột SQL `NULL`; các phương thức lấy kiểu nguyên thủy có thể cần kiểm tra `wasNull()` nếu sự khác biệt giữa `NULL` và `0` quan trọng.

### 5.5. Cột có alias không đồng nghĩa cột trong bảng đã đổi

~~~sql
SELECT
    product_name AS display_name
FROM products;
~~~

Truy vấn tạo cột kết quả tên `display_name`, nhưng không sinh cột `products.display_name` ở database. Muốn thay đổi lược đồ phải dùng DDL phù hợp như `ALTER TABLE`, và đó là một tác vụ khác với `SELECT`.

## 6. Phân biệt các bước logic của câu truy vấn

Cú pháp thường viết `SELECT` trước `FROM`, nhưng để **suy luận kết quả**, hãy hình dung `FROM` cung cấp tập hàng trước, rồi `WHERE` lọc hàng, sau đó `SELECT` quyết định giá trị/cột của các hàng còn lại.

Ví dụ:

~~~sql
SELECT
    product_name,
    unit_price * quantity_in_stock AS inventory_value
FROM products
WHERE category_id = 20
  AND quantity_in_stock > 0
ORDER BY inventory_value DESC, product_name;
~~~

Diễn giải:

1. `FROM products`: xét các hàng sản phẩm.
2. `WHERE category_id = 20 AND quantity_in_stock > 0`: giữ sản phẩm thuộc danh mục 20 và còn hàng.
3. `SELECT ...`: trả tên cùng giá trị tồn kho được tính cho mỗi hàng còn lại.
4. `ORDER BY ...`: sắp theo giá trị tồn kho giảm dần.

Kết quả:

| product_name | inventory_value |
| --- | ---: |
| Ban phim | 3000000.00 |
| Gia do | 2100000.00 |
| Cap USB | 240000.00 |

`Chuot` thuộc danh mục 20 nhưng tồn kho bằng 0 nên không xuất hiện.

Nếu có `GROUP BY`, `HAVING` và các hàm tổng hợp, số hàng đầu ra có thể thay đổi: một nhóm hàng đầu vào trở thành một hàng kết quả. Đây là **mô hình xử lý logic**, không phải thứ tự thao tác vật lý bắt buộc của DBMS.

### 6.1. Một alias của SELECT thường chưa dùng được trong WHERE cùng cấp

Đoạn sau không hợp lệ trong nhiều DBMS vì `inventory_value` là alias khai báo tại danh sách `SELECT` cùng cấp:

~~~sql
-- Dễ gây lỗi / không di động:
SELECT unit_price * quantity_in_stock AS inventory_value
FROM products
WHERE inventory_value > 500000;
~~~

Viết lại bằng chính biểu thức:

~~~sql
SELECT
    product_name,
    unit_price * quantity_in_stock AS inventory_value
FROM products
WHERE unit_price * quantity_in_stock > 500000
ORDER BY inventory_value DESC;
~~~

Hoặc đặt `SELECT` tính toán vào truy vấn con như mục 4.3 rồi lọc ở câu truy vấn bên ngoài. Việc dùng alias trong `ORDER BY` được hỗ trợ rộng rãi; đừng suy ra vì `ORDER BY` dùng được nên `WHERE` cũng dùng được.

### 6.2. FROM ảnh hưởng số hàng khi JOIN và GROUP BY

Khi `FROM` có `JOIN`, mỗi hàng bên trái có thể khớp không, một hoặc nhiều hàng bên phải. Khi dùng `GROUP BY`, các hàng của cùng nhóm được gom để tính tổng hợp. Ví dụ đếm sản phẩm theo danh mục, kể cả danh mục rỗng:

~~~sql
SELECT
    c.category_id,
    c.category_name,
    COUNT(p.product_id) AS product_count
FROM categories AS c
LEFT JOIN products AS p
    ON p.category_id = c.category_id
GROUP BY c.category_id, c.category_name
ORDER BY c.category_id;
~~~

| category_id | category_name | product_count |
| ---: | --- | ---: |
| 10 | Van phong pham | 2 |
| 20 | Thiet bi | 4 |
| 30 | Dich vu | 0 |

`LEFT JOIN` giữ cả danh mục chưa có sản phẩm. Với nhóm `Dich vu`, `p.product_id` là `NULL` nên `COUNT(p.product_id)` trả 0. Nếu dùng `COUNT(*)`, hàng giả do `LEFT JOIN` sinh ra vẫn được tính và danh mục rỗng sẽ có kết quả 1. Do đó phải chọn đúng biểu thức trong danh sách `SELECT` theo ý nghĩa cần thống kê.

## 7. SELECT không có FROM: có khả thi không?

Đôi khi muốn tính một biểu thức mà không đọc dữ liệu từ bảng:

~~~sql
SELECT 2 + 3 AS total;
~~~

PostgreSQL, MySQL, SQLite và SQL Server hỗ trợ dạng truy vấn hằng số không có `FROM`. Về mặt kết quả, câu lệnh trả một cột tên `total` và một hàng giá trị `5`.

Tuy nhiên, **khả năng bỏ `FROM` phụ thuộc DBMS và phiên bản**. Trong các phiên bản Oracle truyền thống, thường viết:

~~~sql
SELECT 2 + 3 AS total
FROM DUAL;
~~~

`DUAL` là bảng đặc biệt dùng để chọn biểu thức theo quy ước Oracle. Những phiên bản Oracle mới có thể hỗ trợ cú pháp không cần `FROM` ở các ngữ cảnh nhất định. Không nên dùng dạng này như một quy tắc di động tuyệt đối.

Khi đã viết `FROM products`, một literal trong `SELECT` sẽ được lặp cho **mỗi hàng của nguồn**:

~~~sql
SELECT
    product_id,
    'OK' AS status_label
FROM products
ORDER BY product_id;
~~~

Truy vấn này trả **sáu hàng** với `status_label` đều là `OK`, không phải một hàng duy nhất. Vì vậy, sự có mặt của nguồn dữ liệu quyết định số hàng cần xử lý trước khi các phép khác tác động.

## 8. Liên hệ với ứng dụng và metadata result set

Một SQL client thường hiển thị result set dưới dạng lưới. Ứng dụng có thể đọc cùng kết quả qua driver. Ví dụ JDBC:

~~~java
String sql = """
    SELECT product_id, product_name, unit_price
    FROM products
    ORDER BY product_id
    """;

try (PreparedStatement statement = connection.prepareStatement(sql);
     ResultSet resultSet = statement.executeQuery()) {

    while (resultSet.next()) {
        int id = resultSet.getInt("product_id");
        String name = resultSet.getString("product_name");
        java.math.BigDecimal price = resultSet.getBigDecimal("unit_price");

        System.out.println(id + " - " + name + " - " + price);
    }
}
~~~

`ResultSet` của JDBC cho phép ứng dụng **duyệt các hàng nhận được**. Việc ứng dụng gọi `next()` lần lượt không có nghĩa SQL phải thực thi ở DBMS bằng một vòng lặp theo đúng thứ tự đó; đây là cách driver cung cấp kết quả cho chương trình.

Ngoài giá trị, driver còn có **metadata** như số cột, nhãn cột và kiểu dữ liệu. Trong JDBC, `ResultSetMetaData` cung cấp các thông tin này; `getColumnLabel` thường phản ánh alias trong danh sách `SELECT`, còn `getColumnName` và hành vi ánh xạ tên gốc có thể phụ thuộc driver.

Đây là lý do ứng dụng nên giữ một **hợp đồng kết quả** rõ ràng:

- Liệt kê các cột cần dùng; kiểm soát alias mà mapper hoặc API trông đợi.
- Kiểm soát thứ tự hàng bằng `ORDER BY` nếu ứng dụng cần nó.
- Xử lý trường hợp 0 hàng và giá trị `NULL`.
- Không dựa vào vị trí cột của `SELECT *` khi lược đồ còn thay đổi.
- Khi có đầu vào người dùng, dùng tham số hóa (`PreparedStatement`), không nối chuỗi dữ liệu vào cú pháp SQL.

### Khi nào dùng một SELECT đơn giản?

Một truy vấn `SELECT ... FROM ...` là phù hợp để lấy dữ liệu từ một bảng hoặc view khi không cần lọc/ghép phức tạp. Hãy bổ sung `WHERE` khi chỉ muốn một phần hàng, `JOIN` khi cần kết hợp quan hệ, `GROUP BY` khi cần kết quả theo nhóm, `ORDER BY` khi cần trật tự xác định. Những mệnh đề này bổ sung cho cấu trúc cơ bản chứ không thay thế vai trò của `SELECT` và `FROM`.

## 9. Lỗi và hiểu nhầm thường gặp

| Cách nghĩ hoặc cách viết | Vấn đề | Hướng xử lý |
| --- | --- | --- |
| “`SELECT` đọc theo thứ tự cột trong bảng” | Danh sách `SELECT` quyết định cột và thứ tự cột kết quả | Liệt kê cột theo nhu cầu |
| “`FROM products` luôn trả hàng theo `product_id`” | Không có thứ tự hàng mặc định | Thêm `ORDER BY product_id` |
| “Chọn một cột thì kết quả luôn không trùng” | SQL cho phép hàng trùng theo mặc định | Dùng `DISTINCT` khi thực sự cần giá trị duy nhất |
| “`SELECT *` luôn an toàn cho API” | Cột đầu ra thay đổi khi schema thay đổi | Chọn cột và alias tường minh |
| “Alias `SELECT` dùng ở bất cứ đâu” | `WHERE` cùng cấp thường không nhận alias của danh sách `SELECT` | Lặp biểu thức hoặc dùng truy vấn con |
| “Mỗi JOIN chỉ thêm cột” | JOIN có thể tăng, giảm hoặc giữ số hàng | Kiểm tra điều kiện ghép và quan hệ một-nhiều |
| “Result set trống là lỗi SQL” | Một truy vấn hợp lệ có thể trả 0 hàng | Ứng dụng xử lý danh sách rỗng |
| “Dữ liệu `NULL` giống chuỗi rỗng” | `NULL` có logic và ý nghĩa riêng | Dùng `IS NULL`, tránh so sánh `= NULL` |
| “`SELECT DISTINCT` sửa được mọi duplicate” | Có thể che lỗi JOIN và làm tốn chi phí | Tìm đúng nguyên nhân trùng và xác định yêu cầu |
| “`ORDER BY` trong view bảo đảm thứ tự truy vấn ngoài” | Thứ tự đầu ra cuối không được bảo đảm như vậy | Sắp xếp ở câu truy vấn cuối |
| “Dùng dấu nháy đơn để đặt alias có khoảng trắng” | Dấu nháy đơn thường biểu diễn literal chuỗi | Dùng cú pháp trích dẫn định danh của DBMS |

Có thể ghi nhớ câu hỏi trước mỗi truy vấn: **Nguồn có bao nhiêu hàng? Danh sách `SELECT` tạo những cột gì? Có phép nào làm thay đổi số hàng hoặc thứ tự không?**

## 10. Bài tập tự thực hành

Các bài dưới đây sử dụng dữ liệu mẫu ở mục 2. Khi yêu cầu kết quả có thứ tự, hãy sử dụng `ORDER BY` để việc kiểm tra không phụ thuộc kế hoạch thực thi.

### Bài 1 — Chọn đúng ba cột

Viết truy vấn hiển thị `product_id`, `product_name` và `quantity_in_stock` theo thứ tự ID tăng dần.

~~~sql
SELECT
    product_id,
    product_name,
    quantity_in_stock
FROM products
ORDER BY product_id;
~~~

Kết quả có **6 hàng và 3 cột**. Giá trị tồn kho lần lượt theo ID là `12, 50, 4, 0, 20, 6`.

### Bài 2 — Tạo cột tính toán và đặt alias

Trả tên sản phẩm và giá trị tồn kho (đơn giá × số lượng), đặt tên đầu ra `inventory_value`; sắp giảm dần theo giá trị tồn kho, khi hòa thì theo ID tăng dần.

~~~sql
SELECT
    product_name,
    unit_price * quantity_in_stock AS inventory_value
FROM products
ORDER BY inventory_value DESC, product_id ASC;
~~~

Với dữ liệu mẫu, thứ tự tên là `Ban phim`, `Gia do`, `But bi`, `So tay`, `Cap USB`, `Chuot`.

### Bài 3 — Phân biệt SELECT với SELECT DISTINCT

Hai truy vấn có trả cùng số hàng không?

~~~sql
SELECT unit_price
FROM products;

SELECT DISTINCT unit_price
FROM products;
~~~

**Đáp án:** không. Truy vấn đầu trả **6 hàng**; truy vấn `DISTINCT` trả **5 hàng** vì hai sản phẩm có giá `12000.00`. Không truy vấn nào bảo đảm thứ tự hàng do không có `ORDER BY`.

### Bài 4 — Lọc nguồn trước khi tạo kết quả

Lấy tên và giá của các sản phẩm danh mục 20 còn hàng, sắp theo `product_id` tăng dần.

~~~sql
SELECT product_name, unit_price
FROM products
WHERE category_id = 20
  AND quantity_in_stock > 0
ORDER BY product_id;
~~~

Kết quả có **3 hàng**: `Ban phim`, `Cap USB`, `Gia do`. `Chuot` bị loại vì `quantity_in_stock = 0`.

### Bài 5 — JOIN trả thêm thông tin từ nguồn khác

Trả `product_id`, tên sản phẩm, tên danh mục của mọi sản phẩm theo ID tăng dần.

~~~sql
SELECT
    p.product_id,
    p.product_name,
    c.category_name
FROM products AS p
JOIN categories AS c
    ON c.category_id = p.category_id
ORDER BY p.product_id;
~~~

Kết quả có **6 hàng và 3 cột**. Hãy giải thích vì sao thêm bảng `categories` không tạo 18 hàng: điều kiện `ON` chỉ giữ cặp hàng có mã danh mục khớp, khác với `CROSS JOIN`.

### Bài 6 — Dự đoán số hàng

Từ dữ liệu mẫu, dự đoán số hàng cho từng câu lệnh:

~~~sql
-- A
SELECT product_name FROM products;

-- B
SELECT DISTINCT category_id FROM products;

-- C
SELECT p.product_id, c.category_id
FROM products AS p CROSS JOIN categories AS c;

-- D
SELECT product_id FROM products WHERE unit_price > 10000000;

-- E
SELECT COUNT(*) AS n FROM products WHERE unit_price > 10000000;
~~~

**Đáp án:** A = 6, B = 2, C = 18, D = 0, E = 1 hàng chứa giá trị `n = 0`. B có hai mã danh mục xuất hiện trong `products` là `10` và `20`; `30` nằm trong `categories` nhưng không xuất hiện trong bảng sản phẩm.

### Bài 7 — Tìm lỗi trong câu truy vấn

Đoạn sau có vấn đề gì?

~~~sql
SELECT
    product_name,
    unit_price * quantity_in_stock AS inventory_value
FROM products
WHERE inventory_value > 1000000;
~~~

**Gợi ý:** alias `inventory_value` thường chưa khả dụng trong `WHERE` cùng cấp. Viết lại:

~~~sql
SELECT
    product_name,
    unit_price * quantity_in_stock AS inventory_value
FROM products
WHERE unit_price * quantity_in_stock > 1000000
ORDER BY product_id;
~~~

Kết quả: `Ban phim` và `Gia do`.

## 11. Kết luận

`FROM` xác định **nguồn các hàng** mà truy vấn làm việc; `SELECT` xác định **các cột và biểu thức** được công bố trong mỗi hàng kết quả. Result set có cấu trúc cột rõ ràng, có thể chứa `NULL` và các hàng trùng nhau, và không có thứ tự hàng bảo đảm khi thiếu `ORDER BY`. Các phép `WHERE`, `JOIN`, `DISTINCT`, `GROUP BY` hoặc tổng hợp có thể làm số hàng đầu ra thay đổi so với nguồn.

Khi xây dựng câu truy vấn đầu tiên, nên chọn **cột tường minh**, đặt alias có ý nghĩa, xác định đúng nguồn `FROM`, kiểm tra dự kiến số hàng và thêm `ORDER BY` nếu kết quả cần thứ tự ổn định. Nắm chắc những điểm này giúp đọc đúng SQL phức tạp và thiết kế hợp đồng dữ liệu đáng tin cậy với ứng dụng.
