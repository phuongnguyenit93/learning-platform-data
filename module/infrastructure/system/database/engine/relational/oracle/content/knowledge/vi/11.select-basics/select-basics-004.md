# IN, BETWEEN, LIKE và ký tự đại diện trong Oracle Database

Khi viết câu lệnh `SELECT` trên Oracle Database, phần `WHERE` quyết định những dòng nào được giữ lại. Bên cạnh các phép so sánh `=`, `<`, `>`, `<=` và `>=`, ba điều kiện rất phổ biến là **`IN`**, **`BETWEEN`** và **`LIKE`**:

- **`IN`** kiểm tra một giá trị có nằm trong một tập giá trị hoặc kết quả truy vấn con hay không.
- **`BETWEEN`** kiểm tra một giá trị có thuộc một khoảng **bao gồm cả hai đầu mút** hay không.
- **`LIKE`** so khớp chuỗi với một **mẫu (pattern)**, trong đó `%` và `_` là hai ký tự đại diện.

Một câu SQL ngắn có thể dẫn đến kết quả bất ngờ nếu không hiểu rõ `NULL`, ranh giới của khoảng ngày giờ, ký tự đại diện trong tên sản phẩm hoặc quy tắc so sánh chuỗi của Oracle. Bài học này giải thích cú pháp, cách kết hợp điều kiện, ví dụ có thể thực hành và những lưu ý để truy vấn đúng, an toàn, dễ bảo trì.

## 1. Vị trí của các điều kiện trong SELECT

Cấu trúc đơn giản:

```sql
SELECT column_1, column_2
FROM   table_name
WHERE  condition
ORDER  BY column_1;
```

`WHERE` nhận một **điều kiện**. Dòng chỉ được giữ lại khi điều kiện đánh giá là **TRUE**. SQL còn có trạng thái logic **FALSE** và **UNKNOWN**; các so sánh liên quan đến `NULL` thường cho UNKNOWN và bị loại khỏi kết quả `WHERE`.

Ví dụ đọc ngôn ngữ tự nhiên:

| Yêu cầu | Mẫu điều kiện |
| --- | --- |
| Chọn sản phẩm thuộc một trong ba nhóm | `category IN ('BOOK', 'TOY', 'FOOD')` |
| Chọn sản phẩm giá từ 100 đến 500 | `price BETWEEN 100 AND 500` |
| Tìm tên bắt đầu bằng “Laptop” | `product_name LIKE 'Laptop%'` |
| Tìm tên có chứa “USB” | `product_name LIKE '%USB%'` |
| Tìm mã chứa dấu gạch dưới thực sự | `sku LIKE '%\_%' ESCAPE '\'` |
| Chọn các nhóm còn lại | `category NOT IN ('BOOK', 'TOY')` |
| Giá nằm ngoài khoảng | `price NOT BETWEEN 100 AND 500` |
| Tên không khớp một mẫu | `product_name NOT LIKE 'Laptop%'` |

Các ví dụ `'BOOK'`, `'TOY'` chỉ là tên nhóm minh họa; truy vấn cụ thể phụ thuộc bảng đang dùng.

### 1.1. Dữ liệu mẫu dùng xuyên suốt bài

Tạo bảng thực hành trong schema được cấp quyền:

```sql
CREATE TABLE demo_products (
    product_id   NUMBER(10) PRIMARY KEY,
    product_name VARCHAR2(100) NOT NULL,
    category     VARCHAR2(30),
    sku          VARCHAR2(30),
    price        NUMBER(12,2),
    created_at   DATE NOT NULL
);
```

Thêm dữ liệu cố định để các câu truy vấn có thể đối chiếu kết quả:

```sql
INSERT INTO demo_products VALUES (
    1, 'Laptop Pro', 'ELECTRONICS', 'LP_01',
    25000000, TO_DATE('2026-11-14 09:15:00', 'YYYY-MM-DD HH24:MI:SS')
);

INSERT INTO demo_products VALUES (
    2, 'Laptop Air', 'ELECTRONICS', 'LA-02',
    18000000, TO_DATE('2026-11-15 17:30:00', 'YYYY-MM-DD HH24:MI:SS')
);

INSERT INTO demo_products VALUES (
    3, 'Mouse A_100', 'ACCESSORIES', 'MS_100',
    350000, DATE '2026-11-15'
);

INSERT INTO demo_products VALUES (
    4, 'Monitor 27%', 'ELECTRONICS', 'MN-27%',
    6000000, TO_DATE('2026-12-01 12:00:00', 'YYYY-MM-DD HH24:MI:SS')
);

INSERT INTO demo_products VALUES (
    5, 'Cable USB-C', 'ACCESSORIES', 'CB-05',
    190000, DATE '2026-12-05'
);

INSERT INTO demo_products VALUES (
    6, 'Notebook Basic', 'STATIONERY', 'NB-06',
    60000, DATE '2026-12-05'
);

INSERT INTO demo_products VALUES (
    7, 'Keyboard', NULL, 'KB-07',
    1200000, DATE '2026-12-10'
);

INSERT INTO demo_products VALUES (
    8, 'Adaptor 100%', 'ACCESSORIES', 'AD-08',
    NULL, DATE '2026-12-12'
);

INSERT INTO demo_products VALUES (
    9, 'Tablet', 'ELECTRONICS', 'TB-09',
    8500000, DATE '2027-01-01'
);

COMMIT;
```

Dữ liệu quan trọng để nhớ:

| ID | Tên sản phẩm | CATEGORY | PRICE | Ghi chú |
| ---: | --- | --- | ---: | --- |
| 1 | Laptop Pro | ELECTRONICS | 25.000.000 | SKU có dấu `_` |
| 2 | Laptop Air | ELECTRONICS | 18.000.000 | Tạo ngày 15/11 lúc 17:30 |
| 3 | Mouse A_100 | ACCESSORIES | 350.000 | Tên có `_` |
| 4 | Monitor 27% | ELECTRONICS | 6.000.000 | Tên có `%` |
| 5 | Cable USB-C | ACCESSORIES | 190.000 | Chứa “USB” |
| 6 | Notebook Basic | STATIONERY | 60.000 | Nhóm văn phòng phẩm |
| 7 | Keyboard | `NULL` | 1.200.000 | Nhóm chưa xác định |
| 8 | Adaptor 100% | ACCESSORIES | `NULL` | Giá chưa có |
| 9 | Tablet | ELECTRONICS | 8.500.000 | Tạo năm 2027 |

**Lưu ý:** giá trị tiền ở đây dùng `NUMBER(12,2)` để dễ thực hành với số thập phân. Oracle không lưu dấu phân tách hàng nghìn trong giá trị số; các dấu chấm trong bảng chỉ phục vụ trình bày.

## 2. IN: kiểm tra một giá trị thuộc tập hợp

### 2.1. Cú pháp và ý nghĩa

Cú pháp cơ bản:

```sql
expression IN (value_1, value_2, value_3, ...)
```

Với các giá trị so sánh khác `NULL` và tương thích kiểu, biểu thức:

```sql
category IN ('ELECTRONICS', 'ACCESSORIES')
```

có thể đọc là:

```sql
category = 'ELECTRONICS'
OR category = 'ACCESSORIES'
```

Cách viết bằng `IN` thường dễ đọc hơn chuỗi dài các phép so sánh `OR`.

Ví dụ:

```sql
SELECT product_id, product_name, category
FROM   demo_products
WHERE  category IN ('ELECTRONICS', 'ACCESSORIES')
ORDER  BY product_id;
```

Kết quả theo bảng mẫu gồm các ID **1, 2, 3, 4, 5, 8, 9**. Sản phẩm 6 thuộc `STATIONERY`, sản phẩm 7 có `CATEGORY=NULL` nên không được chọn.

### 2.2. IN với số

```sql
SELECT product_id, product_name, price
FROM   demo_products
WHERE  product_id IN (1, 3, 5, 9)
ORDER  BY product_id;
```

Kết quả là các sản phẩm có ID **1, 3, 5, 9**.

`IN` không yêu cầu danh sách phần tử phải được sắp xếp. Việc viết `IN (9, 1, 5, 3)` không làm cho kết quả xuất hiện theo thứ tự `9, 1, 5, 3`. **`ORDER BY` mới quyết định thứ tự hiển thị được bảo đảm trong câu SELECT.**

### 2.3. IN không phải kiểm tra một khoảng

Điều kiện:

```sql
WHERE product_id IN (1, 3, 5)
```

chỉ chọn đúng ba giá trị **1**, **3**, **5**, không tự chọn **2** hoặc **4**. Nếu muốn tìm mọi ID liên tục từ 1 đến 5, dùng:

```sql
WHERE product_id BETWEEN 1 AND 5
```

hoặc điều kiện tương đương:

```sql
WHERE product_id >= 1
  AND product_id <= 5
```

Tương tự, `IN ('A', 'B')` không có nghĩa tìm mọi chuỗi nằm theo thứ tự từ A đến B; nó chỉ kiểm tra hai giá trị được liệt kê.

### 2.4. Các phần tử phải tương thích kiểu dữ liệu

Nên dùng cùng kiểu dữ liệu với biểu thức so sánh:

```sql
-- PRODUCT_ID là NUMBER.
SELECT product_id
FROM   demo_products
WHERE  product_id IN (1, 2, 3);
```

Tránh viết danh sách chứa số ở dạng chuỗi rồi dựa vào **implicit conversion**:

```sql
-- Không khuyến nghị: so sánh NUMBER với chuỗi ký tự.
SELECT product_id
FROM   demo_products
WHERE  product_id IN ('1', '2', '3');
```

Oracle có cơ chế chuyển kiểu ngầm nhưng nó có thể tạo lỗi `ORA-01722: invalid number` hoặc kết quả phụ thuộc cấu hình nếu giá trị đầu vào không phù hợp. Cách tốt nhất là truyền tham số đúng kiểu số.

### 2.5. IN với truy vấn con

`IN` không bắt buộc chứa danh sách literal. Nó có thể kiểm tra giá trị trong kết quả của một `SELECT` khác.

Giả sử có bảng liệt kê các sản phẩm được khuyến mại:

```sql
CREATE TABLE demo_promo_products (
    product_id NUMBER(10)
);

INSERT INTO demo_promo_products VALUES (1);
INSERT INTO demo_promo_products VALUES (3);
COMMIT;
```

Truy vấn:

```sql
SELECT p.product_id, p.product_name
FROM   demo_products p
WHERE  p.product_id IN (
         SELECT x.product_id
         FROM   demo_promo_products x
       )
ORDER  BY p.product_id;
```

Kết quả gồm sản phẩm **1** và **3**. Oracle kiểm tra `P.PRODUCT_ID` có khớp với một giá trị do subquery trả về không.

Trường hợp này thường dùng khi danh sách lọc nằm trong một bảng quan hệ, ví dụ bảng trạng thái, bảng nhóm người dùng, bảng quyền hoặc bảng kết quả xử lý nghiệp vụ.

### 2.6. IN với nhiều cột (tuple comparison)

Oracle cho phép so sánh một nhóm biểu thức với các nhóm giá trị tương ứng:

```sql
SELECT product_id, product_name, category, price
FROM   demo_products
WHERE  (category, price) IN (
         ('ELECTRONICS', 25000000),
         ('ACCESSORIES', 350000)
       )
ORDER BY product_id;
```

Truy vấn tìm đúng những **cặp** `(CATEGORY, PRICE)` phù hợp: theo bảng mẫu là sản phẩm **1** và **3**.

Không được hiểu tuple comparison như hai điều kiện độc lập:

```sql
WHERE category IN ('ELECTRONICS', 'ACCESSORIES')
  AND price IN (25000000, 350000)
```

Điều kiện thứ hai có thể chấp nhận các tổ hợp chéo không được liệt kê trong tập cặp ban đầu. Khi cần kiểm tra quan hệ giữa nhiều cột, tuple hoặc join thích hợp có ý nghĩa rõ ràng hơn.

### 2.7. Danh sách IN quá dài

Một câu `IN` chứa hàng nghìn literal sẽ khó đọc, khó bảo trì và có thể chạm **giới hạn số biểu thức** theo phiên bản/cú pháp Oracle. Trong Oracle 19c, giới hạn thường gặp của danh sách một cột là **1.000 biểu thức**, với lỗi `ORA-01795` khi vượt giới hạn đó.

Với dữ liệu lớn, cân nhắc:

- Đưa các giá trị vào một **bảng tạm/bảng staging** theo quy trình cho phép, rồi `JOIN` hoặc `IN (SELECT ...)`.
- Truyền tập giá trị qua API/collection được driver và database hỗ trợ.
- Chia lô xử lý theo yêu cầu nghiệp vụ và đánh giá kế hoạch truy vấn.

Không viết chuỗi SQL dài bất thường chỉ để tránh thiết kế một cách truyền danh sách ổn định.

## 3. NOT IN và bẫy NULL

### 3.1. NOT IN khi không có NULL

Khi tất cả giá trị đều khác `NULL`:

```sql
SELECT product_id, product_name, category
FROM   demo_products
WHERE  category NOT IN ('ELECTRONICS', 'ACCESSORIES')
ORDER  BY product_id;
```

Trong dữ liệu mẫu, sản phẩm **6** thuộc `STATIONERY` được chọn. Sản phẩm **7** có `CATEGORY=NULL` **không được chọn**, dù về mặt ngôn ngữ tự nhiên ta có thể nói nó “không thuộc hai nhóm trên”.

Đó là vì SQL không thể xác định `NULL` khác các giá trị so sánh theo logic hai giá trị đơn giản.

Nếu muốn lấy cả sản phẩm chưa có category, phải diễn đạt rõ:

```sql
SELECT product_id, product_name, category
FROM   demo_products
WHERE  category NOT IN ('ELECTRONICS', 'ACCESSORIES')
   OR  category IS NULL
ORDER  BY product_id;
```

Lúc này kết quả bao gồm **6** và **7**.

### 3.2. Vì sao NOT IN gặp NULL nguy hiểm?

Xét:

```sql
WHERE product_id NOT IN (1, 3, NULL)
```

Với một giá trị `PRODUCT_ID = 2`, điều kiện có thể hiểu tương đương với:

```text
2 <> 1 AND 2 <> 3 AND 2 <> NULL
TRUE   AND TRUE   AND UNKNOWN
           = UNKNOWN
```

`WHERE` chỉ chọn các dòng có điều kiện TRUE, nên giá trị **2** bị loại. Các giá trị khớp 1 hoặc 3 thì điều kiện FALSE. Vì vậy, với danh sách chứa `NULL` và các ID không-null của bảng mẫu, `NOT IN` **không trả về dòng nào**.

Đây là khác biệt rất quan trọng giữa:

```sql
-- Có thể không trả dòng nào vì danh sách chứa NULL.
SELECT product_id
FROM   demo_products
WHERE  product_id NOT IN (1, 3, NULL);
```

và mong muốn bằng ngôn ngữ tự nhiên “lấy mọi sản phẩm trừ 1 và 3”.

### 3.3. Bẫy khi dùng NOT IN với subquery

Giả sử bảng khuyến mại có một dòng `PRODUCT_ID=NULL`:

```sql
INSERT INTO demo_promo_products VALUES (NULL);
COMMIT;
```

Lúc này:

```sql
SELECT p.product_id, p.product_name
FROM   demo_products p
WHERE  p.product_id NOT IN (
         SELECT x.product_id
         FROM   demo_promo_products x
       )
ORDER BY p.product_id;
```

có thể trả về **0 dòng** mặc dù sản phẩm 2, 4, 5... không nằm trong chương trình khuyến mại. Một giá trị `NULL` trong kết quả subquery làm điều kiện `NOT IN` không thể chứng minh TRUE cho các giá trị còn lại.

**Đây là lỗi logic thường gặp trong ứng dụng thực tế:** thay đổi dữ liệu ở bảng con làm báo cáo bất ngờ không có kết quả.

### 3.4. Cách khắc phục: loại NULL hoặc dùng NOT EXISTS

Nếu sử dụng `NOT IN` và logic nghiệp vụ cho phép bỏ qua các giá trị `NULL` trong tập bị loại, hãy loại chúng **ngay trong subquery**:

```sql
SELECT p.product_id, p.product_name
FROM   demo_products p
WHERE  p.product_id NOT IN (
         SELECT x.product_id
         FROM   demo_promo_products x
         WHERE  x.product_id IS NOT NULL
       )
ORDER BY p.product_id;
```

Một cách khác, thường dễ diễn đạt quan hệ loại trừ hơn, là `NOT EXISTS`:

```sql
SELECT p.product_id, p.product_name
FROM   demo_products p
WHERE NOT EXISTS (
    SELECT 1
    FROM   demo_promo_products x
    WHERE  x.product_id = p.product_id
)
ORDER BY p.product_id;
```

Với bảng mẫu, truy vấn này chọn các sản phẩm **không có dòng khuyến mại khớp ID**, bất kể bảng khuyến mại có thêm dòng `NULL`.

`NOT EXISTS` kiểm tra có tồn tại một dòng subquery thỏa **điều kiện tương quan** hay không. Một dòng `x.product_id=NULL` không thỏa phép bằng với ID không-null của sản phẩm.

Hai cách trên không tự động tương đương trong mọi mô hình, đặc biệt khi **cột phía ngoài cũng nullable** hoặc có thêm các điều kiện phức tạp. Hãy xác định rõ cách nghiệp vụ muốn xử lý `NULL` ở cả hai phía.

### 3.5. Dùng IS NULL để tìm giá trị chưa biết

Sai:

```sql
-- Điều kiện này không bao giờ xác định TRUE với NULL.
SELECT *
FROM demo_products
WHERE category = NULL;
```

Đúng:

```sql
SELECT product_id, product_name
FROM demo_products
WHERE category IS NULL;
```

Muốn loại NULL:

```sql
WHERE category IS NOT NULL
```

Không đặt `NULL` vào `IN (NULL)` rồi chờ tìm được các dòng có giá trị null. `IS NULL` là điều kiện riêng phục vụ trường hợp đó.

## 4. BETWEEN: khoảng giá trị gồm cả hai đầu mút

### 4.1. Cú pháp

```sql
expression BETWEEN lower_bound AND upper_bound
```

Ý nghĩa đối với các giá trị không-null có thể so sánh:

```sql
expression >= lower_bound
AND expression <= upper_bound
```

**`BETWEEN` là inclusive (bao gồm cả đầu thấp lẫn đầu cao)**. Nếu giá là đúng 100 hoặc đúng 500 thì `price BETWEEN 100 AND 500` có thể chọn cả hai.

Ví dụ:

```sql
SELECT product_id, product_name, price
FROM   demo_products
WHERE  price BETWEEN 300000 AND 8000000
ORDER  BY price, product_id;
```

Theo dữ liệu mẫu, các ID phù hợp là **3** (350.000), **7** (1.200.000) và **4** (6.000.000). Sản phẩm 8 có `PRICE=NULL` nên không được chọn.

### 4.2. BETWEEN không tự hoán đổi đầu mút

Ví dụ:

```sql
WHERE price BETWEEN 8000000 AND 300000
```

Không được hiểu là “từ 300.000 đến 8.000.000”. Với giá khác NULL, điều kiện yêu cầu cùng lúc:

```sql
price >= 8000000
AND price <= 300000
```

nên không có giá nào thỏa trong miền số thông thường.

Trong ứng dụng, nếu người dùng nhập hai đầu mút không đúng thứ tự, cần kiểm tra/chuẩn hóa chúng trước khi tạo truy vấn; Oracle không tự đảo để thành khoảng hợp lệ.

### 4.3. NOT BETWEEN

`NOT BETWEEN` dùng để tìm các giá trị **nằm ngoài khoảng**:

```sql
SELECT product_id, product_name, price
FROM   demo_products
WHERE  price NOT BETWEEN 300000 AND 8000000
ORDER  BY product_id;
```

Khi hai đầu mút hợp lệ và không-null, điều kiện tương đương:

```sql
price < 300000
OR price > 8000000
```

Trong dữ liệu mẫu, sản phẩm giá **60.000**, **190.000**, **8.500.000**, **18.000.000** và **25.000.000** phù hợp. Sản phẩm có `PRICE=NULL` vẫn không được chọn.

Nếu muốn tìm cả giá chưa nhập:

```sql
WHERE price NOT BETWEEN 300000 AND 8000000
   OR price IS NULL
```

### 4.4. BETWEEN với DATE: lỗi ở phần thời gian

Oracle `DATE` có cả **giờ, phút, giây**. Xét:

```sql
SELECT product_id, product_name, created_at
FROM   demo_products
WHERE  created_at BETWEEN DATE '2026-11-14'
                      AND DATE '2026-11-15'
ORDER  BY product_id;
```

Hai ANSI date literals nói trên tương ứng **00:00:00** ở đầu mỗi ngày. Điều kiện sẽ lấy:

- ID **1**, tạo ngày 14/11 lúc 09:15;
- ID **3**, tạo ngày 15/11 lúc 00:00.

Nhưng **không lấy ID 2**, tạo ngày 15/11 lúc **17:30**. Nếu mục tiêu là tìm mọi bản ghi trong cả hai ngày 14 và 15, cách viết `BETWEEN` trên **không đủ**.

### 4.5. Khoảng nửa mở cho ngày giờ

Đối với mốc thời gian, thường nên dùng:

```sql
SELECT product_id, product_name, created_at
FROM   demo_products
WHERE  created_at >= DATE '2026-11-14'
AND    created_at <  DATE '2026-11-16'
ORDER  BY product_id;
```

Kết quả đúng cho **toàn bộ hai ngày 14 và 15**, gồm ID **1, 2, 3**.

Gọi đây là **khoảng nửa mở** `[start, end)`:

- đầu bắt đầu: **có lấy** (`>=`);
- đầu kết thúc: **không lấy** (`<`).

Cách viết này áp dụng tốt cho `DATE` và cả `TIMESTAMP` có phần giây lẻ, miễn các đầu mút được tính theo đúng logic lịch/múi giờ của kiểu dữ liệu. Nó tránh mẹo dùng `23:59:59` vốn có thể bỏ sót `23:59:59.123456` của `TIMESTAMP`.

Ví dụ với cột `TIMESTAMP`:

```sql
WHERE event_time >= TIMESTAMP '2026-11-14 00:00:00'
  AND event_time <  TIMESTAMP '2026-11-16 00:00:00'
```

Nếu cột chứa dữ liệu với time zone, phải xác định rõ “ngày” theo múi giờ nào trước khi chọn hai đầu mút. Không thể giải quyết chênh lệch múi giờ chỉ bằng cách thay `BETWEEN` thành `>= / <`.

### 4.6. BETWEEN với chuỗi

Oracle cho phép so sánh những giá trị ký tự tương thích:

```sql
SELECT product_id, product_name
FROM   demo_products
WHERE  product_name BETWEEN 'L' AND 'M'
ORDER  BY product_name;
```

Tuy nhiên, **khoảng chuỗi dựa trên quy tắc so sánh ký tự/collation**, không phải khái niệm “tên bắt đầu bằng L hoặc M”. Ví dụ chuỗi `'Monitor 27%'` thường lớn hơn chuỗi `'M'` vì có thêm ký tự sau `M`, nên có thể **không thuộc** khoảng `'L'` đến `'M'` dù bắt đầu bằng M.

Khi muốn lọc **tiền tố ký tự**, `LIKE 'M%'` thường diễn đạt đúng hơn. Kết quả so sánh chuỗi còn chịu ảnh hưởng của collation/NLS và kiểu `CHAR` hay `VARCHAR2`; tránh sử dụng các khoảng chữ cái tùy ý nếu nghiệp vụ cần nhất quán đa ngôn ngữ.

### 4.7. BETWEEN với NULL

Khi một đầu mút hoặc biểu thức so sánh là `NULL`, điều kiện có thể cho UNKNOWN theo logic SQL:

```sql
SELECT product_id
FROM   demo_products
WHERE  price BETWEEN 0 AND NULL;
```

Không thể dùng `NULL` như ký hiệu cho “không giới hạn trên” trong `BETWEEN`. Với form tìm kiếm cho phép bỏ trống đầu trên, có thể viết điều kiện tường minh:

```sql
-- :min_price và :max_price là bind parameters.
SELECT product_id, product_name, price
FROM   demo_products
WHERE  (:min_price IS NULL OR price >= :min_price)
AND    (:max_price IS NULL OR price <= :max_price)
ORDER BY product_id;
```

Truy vấn này thể hiện ý nghĩa “bỏ qua một điều kiện nếu tham số giới hạn tương ứng không được nhập”. Việc tối ưu hóa thực tế phụ thuộc giá trị bind, thống kê và optimizer; với workload lớn có thể cân nhắc xây dựng điều kiện SQL phù hợp hơn từ ứng dụng bằng các tham số đã bind, không ghép dữ liệu người dùng trực tiếp vào SQL.

## 5. LIKE: so khớp mẫu chuỗi

### 5.1. Cú pháp cơ bản

```sql
character_expression LIKE pattern
```

Ví dụ:

```sql
SELECT product_id, product_name
FROM   demo_products
WHERE  product_name LIKE 'Laptop%'
ORDER  BY product_id;
```

Mẫu `'Laptop%'` nghĩa là chuỗi bắt đầu bằng `Laptop`, sau đó có thể có **0 hoặc nhiều ký tự**. Theo bảng mẫu, truy vấn chọn ID **1** và **2**.

`LIKE` không phải tìm kiếm ngữ nghĩa: nó so khớp **các ký tự theo pattern**, với quy tắc collation và biểu diễn ký tự được Oracle áp dụng.

### 5.2. Hai ký tự đại diện chính

| Ký tự | Ý nghĩa | Ví dụ mẫu | Khớp với |
| --- | --- | --- | --- |
| `%` | **0 hoặc nhiều** ký tự | `'Lap%'` | `Lap`, `Laptop`, `Laptop Pro` |
| `_` | **Đúng 1** ký tự | `'L_p'` | `Lap`, `Lip`; không khớp `Lp` hoặc `Loop` |

Lưu ý: ký tự `_` là dấu **gạch dưới (underscore)**, không phải dấu gạch ngang `-`. Trong `LIKE`, underscore mặc định mang nghĩa wildcard; nếu muốn tìm dấu gạch dưới thật, dùng `ESCAPE`.

Ví dụ:

```sql
SELECT product_id, product_name
FROM   demo_products
WHERE  product_name LIKE '%USB%'
ORDER  BY product_id;
```

Mẫu `'%USB%'` có nghĩa chuỗi **có chứa** `USB` ở vị trí bất kỳ. Với dữ liệu mẫu, sản phẩm **5 — Cable USB-C** được chọn.

### 5.3. Các mẫu cơ bản cần thuộc

| Pattern | Nghĩa thông thường |
| --- | --- |
| `'A%'` | Bắt đầu bằng A |
| `'%A'` | Kết thúc bằng A |
| `'%A%'` | Có chứa A ở bất kỳ vị trí nào |
| `'A_B'` | Bắt đầu A, có một ký tự bất kỳ, kết thúc B |
| `'A%B'` | Bắt đầu A và kết thúc B, giữa có thể có nhiều hoặc không có ký tự |
| `'____'` | Gồm đúng 4 ký tự theo ngữ nghĩa ký tự Oracle dùng cho kiểu/mẫu |
| `'A___%'` | Bắt đầu A, sau đó có ít nhất 3 ký tự bất kỳ |
| `'%'` | Bất kỳ chuỗi **không NULL**, bao gồm chuỗi độ dài 0 về mặt pattern |

Trong Oracle SQL hiện hành, chuỗi ký tự rỗng `''` của kiểu ký tự thông thường được xử lý như `NULL`; do đó `LIKE '%'` **không** phải cách chọn mọi dòng có cột NULL. Cần viết `IS NULL` nếu muốn xử lý dòng thiếu dữ liệu.

### 5.4. LIKE với mẫu bắt đầu và kết thúc

Tìm tên sản phẩm bắt đầu bằng Laptop:

```sql
SELECT product_id, product_name
FROM   demo_products
WHERE  product_name LIKE 'Laptop%';
```

Tìm mã SKU kết thúc bằng `-05`:

```sql
SELECT product_id, sku
FROM   demo_products
WHERE  sku LIKE '%-05';
```

Tìm tên sản phẩm chứa một cụm:

```sql
SELECT product_id, product_name
FROM   demo_products
WHERE  product_name LIKE '%book%';
```

Kết quả của ví dụ cuối có thể khác tùy **collation/cấu hình so khớp chữ hoa–chữ thường**. Với ngữ nghĩa phân biệt chữ hoa–thường thông thường, `Notebook Basic` có `book` viết thường nên phần `'%book%'` có thể khớp, còn `'%BOOK%'` thì không khớp nếu không có chế độ không phân biệt hoa–thường.

### 5.5. LIKE với độ dài mẫu

Ví dụ:

```sql
-- Mẫu phải có chính xác 5 ký tự:
SELECT product_id, sku
FROM   demo_products
WHERE  sku LIKE '_____';
```

Đây là **5 underscore**. Mỗi underscore khớp một ký tự theo quy tắc của phép so khớp đang dùng.

Ví dụ khác:

```sql
-- SKU bắt đầu bằng hai ký tự LP, sau đó một ký tự bất kỳ,
-- rồi chính xác hai ký tự 01.
SELECT product_id, sku
FROM   demo_products
WHERE  sku LIKE 'LP_01';
```

`LP_01` ở đây sẽ khớp `LP_01`, nhưng cũng có thể khớp `LPX01` hoặc `LP-01`. Nếu ứng dụng thực sự cần dấu gạch dưới nằm giữa `LP` và `01`, phải escape như phần tiếp theo.

### 5.6. LIKE không mặc định hiểu biểu thức chính quy

Trong Oracle `LIKE`, các ký hiệu như `.`, `*`, `?`, `+`, `[A-Z]` không tự mang ý nghĩa regex giống nhiều ngôn ngữ lập trình.

Ví dụ:

```sql
WHERE product_name LIKE 'A.*'
```

không có nghĩa “tên bắt đầu bằng A rồi mọi thứ”. Nó tìm chuỗi có các ký tự `A`, dấu chấm `.` rồi dấu sao `*` theo đúng mẫu đó.

Khi cần biểu thức phức tạp như ký tự thuộc một tập, số lần lặp hoặc nhóm lựa chọn, Oracle có `REGEXP_LIKE`, nhưng đó là một cơ chế khác với `LIKE`, có cú pháp và chi phí riêng.

## 6. ESCAPE: tìm dấu % và _ theo nghĩa đen

### 6.1. Vì sao cần ESCAPE?

Bảng mẫu có:

- `Mouse A_100`: ký tự `_` là một phần của **tên thật**.
- `Monitor 27%` và `Adaptor 100%`: ký tự `%` là một phần của **tên thật**.
- `LP_01`: SKU có dấu gạch dưới thật.

Nếu viết:

```sql
WHERE product_name LIKE '%_%'
```

ta **không** tìm riêng các tên có underscore. Mẫu có `%`, sau đó `_` là một ký tự bất kỳ, rồi `%`, nên nó có thể khớp rất nhiều tên không rỗng.

Cách sửa: khai báo một ký tự **escape** để báo với Oracle rằng wildcard phía sau phải được hiểu như ký tự thường.

### 6.2. Cú pháp ESCAPE

```sql
character_expression LIKE pattern ESCAPE escape_character
```

Ví dụ chọn dấu gạch chéo ngược `\` làm ký tự escape:

```sql
SELECT product_id, product_name
FROM   demo_products
WHERE  product_name LIKE '%\_%' ESCAPE '\'
ORDER  BY product_id;
```

Trong chuỗi mẫu:

- `%` đầu: tùy ý bao nhiêu ký tự;
- `\_`: **một dấu underscore thật**;
- `%` cuối: tùy ý bao nhiêu ký tự.

Kết quả bảng mẫu: sản phẩm **3 — Mouse A_100**.

**Lưu ý riêng cho Oracle SQL:** ký tự `\` trong literal `'\'` là một dấu backslash thông thường của SQL; không phải cú pháp escape của ngôn ngữ Java. Nếu viết câu SQL đó bên trong chuỗi Java, bạn còn phải xử lý escaping của **chuỗi Java** theo quy tắc ngôn ngữ lập trình.

### 6.3. Tìm dấu phần trăm thật

```sql
SELECT product_id, product_name
FROM   demo_products
WHERE  product_name LIKE '%\%%' ESCAPE '\'
ORDER  BY product_id;
```

Mẫu `'%\%%'` tìm một dấu `%` thực ở bất kỳ vị trí nào. Với dữ liệu mẫu, kết quả là:

- **4 — Monitor 27%**
- **8 — Adaptor 100%**

Nếu không escape, ví dụ `LIKE 'Monitor 27%'` chỉ yêu cầu tiền tố `Monitor 27` và có thể khớp những chuỗi không thực sự chứa dấu phần trăm.

### 6.4. Tìm đúng tiền tố có underscore

```sql
SELECT product_id, sku
FROM   demo_products
WHERE  sku LIKE 'LP\_%' ESCAPE '\';
```

Mẫu có nghĩa **SKU bắt đầu bằng chuỗi literal `LP_`**. Với dữ liệu mẫu, chọn `LP_01`.

Nếu muốn so khớp đúng toàn bộ SKU, không cần `LIKE`:

```sql
SELECT product_id, sku
FROM   demo_products
WHERE  sku = 'LP_01';
```

Khi không cần wildcard, **`=` thường thể hiện rõ hơn một phép so khớp mẫu**, và dấu underscore không có ý nghĩa đặc biệt trong toán tử `=`.

### 6.5. Có thể chọn ký tự ESCAPE khác

Backslash không bắt buộc. Bạn có thể dùng một ký tự khác, ví dụ `!`:

```sql
SELECT product_id, product_name
FROM   demo_products
WHERE  product_name LIKE '%!%%' ESCAPE '!'
ORDER  BY product_id;
```

Trong mẫu này, `!%` là dấu phần trăm literal. Ví dụ tìm underscore:

```sql
SELECT product_id, product_name
FROM   demo_products
WHERE  product_name LIKE '%!_%' ESCAPE '!';
```

Ký tự khai báo trong `ESCAPE` phải phù hợp quy tắc **một ký tự escape** của Oracle. Không dùng chuỗi nhiều ký tự như `'AB'` làm escape marker. Nếu dữ liệu thực sự có chứa chính escape marker, cần escape **chính marker** khi xây dựng pattern.

### 6.6. Nếu pattern đến từ người dùng thì sao?

Giả sử một ô tìm kiếm cho phép người dùng nhập “tìm đúng chuỗi con”, không cho họ nhập wildcard. Nếu người dùng nhập `27%`, ứng dụng không được đưa thẳng vào:

```sql
WHERE product_name LIKE '%' || :search_text || '%'
```

và kỳ vọng dấu `%` được hiểu nguyên văn. Nếu `:search_text='27%'`, phần trăm do người dùng nhập vẫn có tác dụng wildcard.

Cần **escape trước những ký tự có ý nghĩa trong LIKE** của dữ liệu đầu vào: escape marker, `%` và `_`; sau đó thêm các wildcard `%` do **ứng dụng** chủ động tạo ở hai đầu và dùng mệnh đề `ESCAPE` nhất quán.

Một minh họa thuần SQL (giả định `:search_text` là chuỗi người dùng, dùng `!` làm escape marker):

```sql
SELECT product_id, product_name
FROM   demo_products
WHERE  product_name LIKE
       '%' ||
       REPLACE(
         REPLACE(
           REPLACE(:search_text, '!', '!!'),
           '%', '!%'
         ),
         '_', '!_'
       ) ||
       '%'
       ESCAPE '!';
```

Thứ tự rất quan trọng: **escape chính dấu `!` trước**, sau đó mới đến `%` và `_`; nếu đổi thứ tự, ứng dụng có thể escape cả marker vừa tạo theo cách không mong muốn.

Câu ví dụ còn cần xử lý các quy tắc so khớp chữ hoa–thường/Unicode, dữ liệu NULL và giới hạn đầu vào theo yêu cầu thực tế. **Bind variable vẫn cần thiết** để truyền input an toàn; escape wildcard không thay thế việc bind tham số chống SQL injection.

## 7. LIKE, chữ hoa–thường và quy tắc collation

### 7.1. Kết quả có thể phụ thuộc collation

Trong nhiều cấu hình so sánh kiểu binary, `LIKE` **phân biệt chữ hoa–chữ thường**:

```sql
SELECT product_id, product_name
FROM   demo_products
WHERE  product_name LIKE 'laptop%';
```

Với giá trị `Laptop Pro` và `Laptop Air`, mẫu viết thường `laptop%` có thể không khớp nếu so sánh đang phân biệt hoa–thường.

Tuy nhiên, không nên tuyên bố rằng `LIKE` **luôn** phân biệt hoa–thường trong mọi Oracle Database: từ các phiên bản hỗ trợ collation hiện đại, kết quả có thể chịu ảnh hưởng của cấu hình collation và các thiết lập NLS/đối tượng liên quan.

### 7.2. Một cách làm rõ chủ ý bỏ qua chữ hoa–thường

Cách phổ biến:

```sql
SELECT product_id, product_name
FROM   demo_products
WHERE  UPPER(product_name) LIKE UPPER('laptop%')
ORDER  BY product_id;
```

Đây là cách diễn đạt rõ “đưa cả hai vế về chữ hoa trước khi so khớp”. Nó thường phù hợp với dữ liệu ASCII đơn giản. Với tiếng Việt, Unicode và yêu cầu không phân biệt dấu, chỉ dùng `UPPER` có thể **không đủ**; cần xem collation và quy tắc ngôn ngữ được cấu hình.

Điểm liên quan đến hiệu năng: đặt hàm `UPPER` lên cột có thể làm Oracle khó dùng index thông thường trên chính cột theo cách của truy vấn gốc. Nếu truy vấn dạng này thường xuyên và dữ liệu lớn, có thể cân nhắc **function-based index** hoặc thiết kế collation/index phù hợp sau khi đo thực tế.

### 7.3. Không đánh đồng LIKE với LIKEC, LIKE2, LIKE4

Oracle còn có những điều kiện so khớp liên quan tới Unicode như `LIKEC`, `LIKE2` và `LIKE4` trong các phiên bản hỗ trợ. Chúng khác nhau ở cách xét ký tự theo đơn vị mã hóa/Unicode. Với bài học SELECT cơ bản, `LIKE` và `%`/`_` là trọng tâm; nếu hệ thống cần so khớp chính xác trên các chuỗi đa ngôn ngữ có supplementary characters, nên tra cứu phần *Pattern-matching Conditions* của đúng phiên bản Oracle.

Không nên tự khẳng định một underscore luôn tương ứng với một **byte**: Oracle xử lý mẫu theo ngữ nghĩa ký tự, và chuỗi Unicode có thể sử dụng nhiều byte cho một ký tự.

### 7.4. CHAR và VARCHAR2 có thể khác nhau

Cột `CHAR(n)` có ngữ nghĩa đệm khoảng trắng ở cuối, trong khi `VARCHAR2` có độ dài biến thiên. Điều này có thể ảnh hưởng cách so sánh và so khớp, đặc biệt khi chuyển đổi ngầm hoặc viết mẫu có dấu cách.

Đừng giả định:

```sql
CHAR_column LIKE 'ABC'
```

hoàn toàn tương đương với:

```sql
VARCHAR2_column LIKE 'ABC'
```

trong mọi thiết kế, vì dữ liệu `CHAR` có thể chứa khoảng trắng đệm. Khi có kết quả bất ngờ, kiểm tra **kiểu cột**, độ dài thực, quy tắc so sánh và chuỗi mẫu.

## 8. NULL và logic ba giá trị trong IN, BETWEEN, LIKE

### 8.1. Tại sao WHERE loại dòng UNKNOWN?

SQL sử dụng ba kết quả logic trong những điều kiện phù hợp:

| Trạng thái | Nghĩa | Dòng có được giữ bởi WHERE không? |
| --- | --- | --- |
| TRUE | Điều kiện đúng | **Có** |
| FALSE | Điều kiện sai | Không |
| UNKNOWN | Không xác định, thường vì `NULL` | **Không** |

Xét `demo_products`:

- `CATEGORY=NULL` ở ID 7.
- `PRICE=NULL` ở ID 8.

Ví dụ:

```sql
SELECT product_id, product_name
FROM   demo_products
WHERE  price BETWEEN 100000 AND 1000000;
```

Dòng 8 có giá NULL nên điều kiện không TRUE. Nó không được chọn.

### 8.2. NULL với các điều kiện

| Điều kiện | Nếu biểu thức bên trái là NULL (trong ví dụ thông thường) |
| --- | --- |
| `category IN ('A','B')` | UNKNOWN |
| `category NOT IN ('A','B')` | UNKNOWN |
| `price BETWEEN 1 AND 10` | UNKNOWN |
| `price NOT BETWEEN 1 AND 10` | UNKNOWN |
| `product_name LIKE 'A%'` | UNKNOWN |
| `product_name NOT LIKE 'A%'` | UNKNOWN |
| `category IS NULL` | TRUE |
| `category IS NOT NULL` | FALSE |

Không suy luận “không đúng A thì chắc đúng NOT A” khi `NULL` tham gia. `NOT UNKNOWN` vẫn là UNKNOWN.

### 8.3. OR, AND và dấu ngoặc

Ví dụ tìm sản phẩm thuộc ELECTRONICS hoặc chưa được phân nhóm, đồng thời có giá trên 1.000.000:

```sql
SELECT product_id, product_name, category, price
FROM   demo_products
WHERE  (category = 'ELECTRONICS' OR category IS NULL)
AND    price > 1000000
ORDER  BY product_id;
```

Dấu ngoặc nhóm **điều kiện category** trước khi kết hợp với điều kiện price. Không có dấu ngoặc, thứ tự ưu tiên toán tử `AND` và `OR` có thể tạo nghĩa khác.

So sánh:

```sql
-- Có dấu ngoặc: áp dụng điều kiện giá cho cả 2 nhóm.
WHERE (category = 'ELECTRONICS' OR category IS NULL)
  AND price > 1000000

-- Không có dấu ngoặc: có thể được hiểu:
WHERE category = 'ELECTRONICS'
   OR (category IS NULL AND price > 1000000)
```

Ở ví dụ thứ hai, mọi sản phẩm ELECTRONICS có thể được nhận bất kể giá. **Viết dấu ngoặc theo ý định nghiệp vụ**, không dựa vào việc nhớ thuộc lòng độ ưu tiên của `AND`/`OR`.

### 8.4. Đừng chuyển NULL thành giá trị giả chỉ để né logic SQL

Có thể dùng `NVL(column, fallback)` trong một số tình huống, nhưng phải hiểu ý nghĩa dữ liệu. Ví dụ:

```sql
WHERE NVL(price, 0) BETWEEN 0 AND 1000000
```

sẽ coi `PRICE=NULL` như số **0**. Điều này có thể sai nếu NULL có nghĩa “chưa biết giá”, không phải “miễn phí”.

Nếu nghiệp vụ muốn bao gồm các giá chưa biết, thường rõ ràng hơn:

```sql
WHERE price BETWEEN 0 AND 1000000
   OR price IS NULL
```

Lúc đó logic hiển thị đúng quyết định của người viết truy vấn.

## 9. Kết hợp IN, BETWEEN và LIKE trong truy vấn thực tế

### 9.1. Ví dụ tìm sản phẩm theo ba tiêu chí

Yêu cầu:

- thuộc nhóm ELECTRONICS hoặc ACCESSORIES;
- giá từ 200.000 đến 10.000.000, kể cả hai đầu mút;
- tên chứa ký tự `o` theo kiểu so khớp hiện tại.

```sql
SELECT product_id,
       product_name,
       category,
       price
FROM   demo_products
WHERE  category IN ('ELECTRONICS', 'ACCESSORIES')
AND    price BETWEEN 200000 AND 10000000
AND    product_name LIKE '%o%'
ORDER  BY price DESC, product_id;
```

Câu SQL kết hợp **kiểm tra tập giá trị**, **kiểm tra khoảng** và **so khớp mẫu**.

Ở môi trường có collation khác nhau, kết quả điều kiện `LIKE '%o%'` có thể khác nếu liên quan chữ hoa–chữ thường. Khi kết quả nghiệp vụ cần rõ ràng, kiểm soát collation/cách chuẩn hóa chuỗi.

### 9.2. Tìm sản phẩm theo tiền tố hoặc SKU

```sql
SELECT product_id, product_name, sku
FROM   demo_products
WHERE  product_name LIKE 'Laptop%'
   OR  sku LIKE 'LP\_%' ESCAPE '\'
ORDER BY product_id;
```

Dấu ngoặc có thể cần nếu thêm điều kiện khác:

```sql
SELECT product_id, product_name, sku, price
FROM   demo_products
WHERE  (product_name LIKE 'Laptop%'
        OR sku LIKE 'LP\_%' ESCAPE '\')
AND    price IS NOT NULL
ORDER BY product_id;
```

Không viết `product_name LIKE 'Laptop%' OR sku LIKE ... AND price ...` mà không xem lại thứ tự nhóm điều kiện.

### 9.3. Bộ lọc thời gian và nhóm sản phẩm

```sql
SELECT product_id,
       product_name,
       category,
       created_at
FROM   demo_products
WHERE  category IN ('ELECTRONICS', 'ACCESSORIES')
AND    created_at >= DATE '2026-11-14'
AND    created_at <  DATE '2026-12-01'
ORDER  BY created_at, product_id;
```

Đây là một dạng lọc phổ biến cho báo cáo tháng hoặc khoảng ngày: `IN` cho nhóm, khoảng nửa mở cho timestamp/date.

Trong chương trình Java hoặc API, nên bind mốc `DATE`/`TIMESTAMP` theo kiểu dữ liệu thay vì ghép chuỗi và dựa vào `NLS_DATE_FORMAT`.

### 9.4. Tìm sản phẩm không có nhóm hoặc nhóm nằm ngoài danh sách

```sql
SELECT product_id, product_name, category
FROM   demo_products
WHERE  category IS NULL
   OR  category NOT IN ('ELECTRONICS', 'ACCESSORIES')
ORDER BY product_id;
```

Cách viết này cố ý xử lý NULL. Nếu loại bỏ `IS NULL`, ID 7 không còn trong kết quả.

### 9.5. Chuyển câu hỏi thành điều kiện đúng

| Câu hỏi nghiệp vụ | Gợi ý viết điều kiện |
| --- | --- |
| Giá đúng một trong ba mức khuyến mại | `price IN (99000, 199000, 299000)` |
| Giá nằm trong đoạn [100.000, 500.000] | `price BETWEEN 100000 AND 500000` |
| Giá lớn hơn 100.000 nhưng nhỏ hơn 500.000 (không gồm hai đầu) | `price > 100000 AND price < 500000` |
| Ngày trong toàn bộ tháng 11/2026 | `created_at >= DATE '2026-11-01' AND created_at < DATE '2026-12-01'` |
| Tên bắt đầu bằng “Cable” | `product_name LIKE 'Cable%'` |
| Tên chứa chuỗi “USB” | `product_name LIKE '%USB%'` |
| Tên có ký tự phần trăm thực | `product_name LIKE '%\%%' ESCAPE '\'` |
| Nhóm không thuộc A/B, kể cả chưa phân nhóm | `category NOT IN ('A','B') OR category IS NULL` |

## 10. Hiệu năng: điều kiện lọc và khả năng sử dụng index

### 10.1. IN và index

Khi cột dùng trong `IN` có index phù hợp, Oracle Optimizer **có thể** cân nhắc index-based access, `INLIST ITERATOR` hoặc các chiến lược khác tùy:

- số lượng phần tử trong danh sách;
- tính chọn lọc của các giá trị;
- kích thước bảng;
- thống kê đối tượng;
- có join, filter, bind và các điều kiện khác;
- cost model và phiên bản Oracle.

Không có quy tắc “`IN` chắc chắn nhanh hơn `OR`” cho mọi truy vấn. Trong nhiều trường hợp, optimizer có thể biến đổi các biểu thức logic tương đương sang kế hoạch gần giống nhau.

### 10.2. BETWEEN và index range scan

Điều kiện:

```sql
WHERE price BETWEEN 300000 AND 8000000
```

có thể phù hợp với **index range scan** nếu có B-tree index trên `PRICE` và optimizer đánh giá chi phí hợp lý.

Ngược lại:

```sql
WHERE ROUND(price / 1000) BETWEEN 300 AND 8000
```

đặt phép toán/hàm lên cột và có thể hạn chế khả năng dùng index thông thường theo cùng cách. Khi cần hiệu năng ổn định, ưu tiên so sánh trên cột gốc với biên được tính đúng, hoặc cân nhắc function-based index có chủ đích.

**Không tự động thêm index chỉ để một query có `BETWEEN` chạy được.** Index chiếm storage và có chi phí khi ghi dữ liệu; nên dựa trên workload thực tế.

### 10.3. LIKE với tiền tố so với wildcard ở đầu

Hai mẫu sau khác nhau về khả năng tìm đường truy cập hiệu quả:

```sql
-- Có tiền tố cố định.
WHERE product_name LIKE 'Laptop%'

-- Wildcard ở đầu.
WHERE product_name LIKE '%top%'
```

Với một B-tree index phù hợp, mẫu có **tiền tố cố định** thường thuận lợi hơn cho các phép tìm kiếm theo dải khóa. Mẫu bắt đầu bằng `%` thường không thể tận dụng hiệu quả cách tìm kiếm tiền tố đó và có thể phải xem nhiều giá trị hơn.

Kết quả cụ thể vẫn phụ thuộc collation, chức năng trên cột, thống kê, selectivity và optimizer. Nếu ứng dụng cần tìm “chứa chuỗi bất kỳ” trên dữ liệu lớn, cân nhắc giải pháp tìm kiếm văn bản như **Oracle Text** hoặc thiết kế chỉ mục phù hợp với nhu cầu truy vấn.

### 10.4. UPPER, LOWER và function-based index

Ví dụ:

```sql
WHERE UPPER(product_name) LIKE 'LAPTOP%'
```

việc áp dụng `UPPER` vào cột có thể ảnh hưởng khả năng dùng B-tree index được tạo trên `PRODUCT_NAME` gốc. Với workload phù hợp, một **function-based index** là phương án có thể đánh giá:

```sql
-- Minh họa DDL; chỉ tạo trong môi trường được phép và có nhu cầu.
CREATE INDEX idx_demo_products_upper_name
ON demo_products (UPPER(product_name));
```

Cần xem kế hoạch thực tế và các yêu cầu về collation/ngôn ngữ; index có tồn tại không bảo đảm optimizer sẽ chọn nó.

### 10.5. Tránh ép cột NUMBER hoặc DATE về chuỗi chỉ để dùng LIKE

Ví dụ không khuyến nghị:

```sql
WHERE TO_CHAR(product_id) LIKE '1%'
```

hoặc:

```sql
WHERE TO_CHAR(created_at, 'DD/MM/YYYY') LIKE '14/11/%'
```

Truy vấn như vậy thay đổi bản chất từ so sánh **NUMBER/DATE** sang so khớp **VARCHAR2** và có thể ảnh hưởng index, format, NLS và kết quả.

Nếu mục tiêu là lọc theo ID cụ thể, dùng số và `IN`. Nếu mục tiêu là lọc ngày, dùng `DATE`/`TIMESTAMP` với khoảng thời gian chính xác. Chỉ dùng `LIKE` trên biểu diễn ký tự khi **đúng mục tiêu nghiệp vụ là tìm chuỗi**.

### 10.6. Xem execution plan

Trong môi trường thực hành, có thể giải thích một truy vấn:

```sql
EXPLAIN PLAN FOR
SELECT product_id, product_name
FROM   demo_products
WHERE  product_name LIKE 'Laptop%';

SELECT *
FROM   TABLE(DBMS_XPLAN.DISPLAY);
```

Đây là **estimated execution plan**, không tự phản ánh toàn bộ số liệu đã thực thi thật. Với chẩn đoán hiệu năng thực tế, DBA có thể dùng các công cụ/plan của cursor đã chạy và số liệu thống kê phù hợp.

Không suy rằng có `TABLE ACCESS FULL` là sai hoặc kém hiệu quả trong mọi trường hợp; với bảng nhỏ, full scan đôi khi hợp lý hơn index scan.

## 11. Bind variables, ứng dụng Java và tìm kiếm an toàn

### 11.1. Không ghép trực tiếp dữ liệu người dùng vào SQL

Không khuyến nghị:

```java
String sql = "SELECT product_id FROM demo_products " +
             "WHERE product_name LIKE '%" + userInput + "%'";
```

Dữ liệu người dùng được ghép thẳng vào SQL text có thể tạo lỗi cú pháp hoặc tạo điều kiện SQL injection. Ngoài ra, nếu user nhập `%` hoặc `_`, ứng dụng có thể vô tình hiểu đó là wildcard.

Cách viết tổng quát:

```java
String sql =
    "SELECT product_id, product_name " +
    "FROM demo_products " +
    "WHERE product_name LIKE ?";

try (java.sql.PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setString(1, "Laptop%");
    try (java.sql.ResultSet rs = ps.executeQuery()) {
        while (rs.next()) {
            System.out.println(rs.getLong("product_id"));
        }
    }
}
```

Giả định biến `connection` đã là JDBC connection hợp lệ. Câu SQL dùng `?` placeholder và giá trị truyền qua bind, không ghép trực tiếp vào SQL. Trong ví dụ, dấu `%` là wildcard **được ứng dụng chủ động đặt**.

### 11.2. Bind cho IN nhiều giá trị

Một bind parameter thông thường không tự biến chuỗi `'1,3,5'` thành danh sách ba phần tử trong `IN`:

```sql
-- Không đồng nghĩa với IN (1, 3, 5):
WHERE product_id IN (:ids)
```

Nếu `:ids` chỉ được bind như một chuỗi `'1,3,5'`, đó là **một giá trị**, không phải ba giá trị số riêng biệt.

Với số lượng phần tử ít và đã biết, có thể dùng:

```sql
WHERE product_id IN (:id1, :id2, :id3)
```

Với Java/JDBC, có thể tạo đúng số placeholder từ **số phần tử được ứng dụng xác định**, sau đó bind từng giá trị:

```java
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.util.Collections;
import java.util.List;

List<Long> ids = List.of(1L, 3L, 5L);

if (!ids.isEmpty()) {
    String placeholders =
        String.join(", ", Collections.nCopies(ids.size(), "?"));

    String sql = "SELECT product_id, product_name " +
                 "FROM demo_products WHERE product_id IN (" +
                 placeholders + ")";

    try (PreparedStatement ps = connection.prepareStatement(sql)) {
        for (int i = 0; i < ids.size(); i++) {
            ps.setLong(i + 1, ids.get(i));
        }

        try (ResultSet rs = ps.executeQuery()) {
            while (rs.next()) {
                System.out.println(rs.getString("product_name"));
            }
        }
    }
}
```

Đoạn mã minh họa dùng `List.of` (Java 9 trở lên), không xử lý trường hợp danh sách quá dài; ứng dụng thực tế phải có chiến lược phù hợp với phiên bản Oracle và giới hạn hệ thống.

Nếu `ids` rỗng, không tạo `IN ()` vì đây không phải cú pháp SQL phù hợp trong Oracle. Có thể trả kết quả rỗng ở tầng ứng dụng nếu nghiệp vụ xác định “không có ID được chọn nghĩa là không lấy dòng nào”, hoặc tạo điều kiện hợp lệ khác có chủ đích.

### 11.3. ESCAPE LIKE input từ ô tìm kiếm

Nếu muốn tìm chuỗi literal người dùng gõ vào, nên thực hiện cả hai việc:

1. Dùng **bind variable** để tránh trộn input với cấu trúc SQL.
2. **Escape wildcard** cho `%`, `_` và escape marker, rồi mới thêm `%` do ứng dụng tạo.

Với dữ liệu tiếng Việt, còn cần thống nhất cách so khớp **hoa–thường, dấu và Unicode**. Bind an toàn không tự giải quyết ngữ nghĩa collation.

### 11.4. Bind cho BETWEEN và ngày giờ

Ví dụ truy vấn theo khoảng giá:

```sql
SELECT product_id, product_name, price
FROM   demo_products
WHERE  price BETWEEN :min_price AND :max_price;
```

Hai bind nên có kiểu số tương ứng.

Với ngày giờ, nên dùng typed date/timestamp bind nếu driver hỗ trợ và ứng dụng cần dữ liệu thời gian, thay vì đưa chuỗi `'15/11/2026'` vào `BETWEEN` rồi phụ thuộc vào `NLS_DATE_FORMAT` của session.

## 12. Chẩn đoán khi truy vấn trả kết quả khác dự kiến

### 12.1. IN không trả dòng cho một giá trị nhìn có vẻ giống nhau

Có thể do:

- kiểu NUMBER so với VARCHAR2 và chuyển đổi ngầm;
- khoảng trắng, dấu không nhìn thấy hoặc `CHAR` padding;
- chữ hoa–chữ thường hoặc collation;
- dữ liệu đang là `NULL`;
- kết nối nhầm schema/PDB hoặc sai bảng.

Bắt đầu bằng cách xem **kiểu cột** và các giá trị thực tế; không tự thêm `UPPER`/`TRIM` vào mọi truy vấn nếu chưa hiểu dữ liệu.

### 12.2. NOT IN trả về 0 dòng

Kiểm tra **subquery có trả `NULL` không**:

```sql
SELECT COUNT(*) AS null_count
FROM   demo_promo_products
WHERE  product_id IS NULL;
```

Nếu có, cần quyết định xem `NULL` là dữ liệu lỗi hay cần bị bỏ qua trong tập loại trừ. Thường có thể dùng `NOT EXISTS` hoặc lọc `IS NOT NULL` ở subquery khi đúng ý nghĩa nghiệp vụ.

### 12.3. BETWEEN không lấy hết ngày kết thúc

Xem kiểu cột `DATE`/`TIMESTAMP` và phần giờ/giây lẻ. Đầu trên viết `DATE '2026-11-15'` chỉ là **00:00:00** đầu ngày 15, không đại diện cho cuối ngày đó.

Dùng khoảng nửa mở đến **đầu ngày 16** để lấy trọn ngày 15 trong ví dụ.

### 12.4. LIKE chọn quá nhiều hàng vì ký tự %

Người dùng cần tìm `'100%'` nhưng ứng dụng chạy:

```sql
WHERE product_name LIKE '%100%%'
```

Mẫu trên tìm `100` rồi cho phép bất kỳ chuỗi phía sau, không bắt buộc có ký tự phần trăm thật.

Sửa thành:

```sql
WHERE product_name LIKE '%100\%%' ESCAPE '\'
```

Nếu pattern đến từ input động, thực hiện escaping ở tầng ứng dụng hoặc trong SQL một cách có kiểm soát như mục 6.6.

### 12.5. LIKE với underscore trả kết quả rộng

Mẫu:

```sql
WHERE sku LIKE 'LP_01'
```

khớp cả các SKU mà ký tự thứ ba không phải dấu gạch dưới. Cách viết cần literal underscore:

```sql
WHERE sku LIKE 'LP\_01' ESCAPE '\'
```

Nếu chỉ tìm đúng một SKU cụ thể, dùng `sku = 'LP_01'` sẽ đơn giản hơn.

### 12.6. LIKE không khớp khác biệt chữ hoa hoặc dấu

Kiểm tra collation/NLS, kiểu cột, định dạng Unicode và yêu cầu nghiệp vụ. Có thể dùng `UPPER` trong nhiều trường hợp đơn giản, nhưng không giả định nó giải quyết toàn bộ tìm kiếm tiếng Việt không phân biệt dấu.

### 12.7. WHERE có AND và OR lấy thừa hàng

Ví dụ:

```sql
WHERE category = 'ELECTRONICS'
   OR category = 'ACCESSORIES'
  AND price > 1000000
```

Tại đây `AND` có độ ưu tiên cao hơn `OR`. Nếu muốn áp dụng giá cho **cả hai nhóm**, cần:

```sql
WHERE category IN ('ELECTRONICS', 'ACCESSORIES')
AND   price > 1000000
```

hoặc đặt ngoặc tương ứng.

### 12.8. ORA-01722, ORA-018xx hoặc lỗi ESCAPE

Một số nhóm nguyên nhân:

| Dấu hiệu | Có thể kiểm tra |
| --- | --- |
| `ORA-01722: invalid number` | Có so sánh số với chuỗi không phải số hoặc implicit conversion không? |
| `ORA-01861`, các lỗi `ORA-018xx` | Có truyền chuỗi ngày giờ không đúng format/session NLS không? |
| Lỗi liên quan `ESCAPE` | Escape marker có đúng một ký tự? Pattern có escape chuỗi đúng quy tắc không? |
| `ORA-01795` với IN list lớn ở release áp dụng | Danh sách biểu thức vượt giới hạn? Có thể chuyển sang bảng/subquery/collection không? |
| SQL không trả dòng dù dữ liệu tồn tại | `NULL`, kiểu dữ liệu, collation, dấu ngoặc, schema/PDB có đúng không? |

Không nên sửa bằng cách xóa `WHERE` hoặc chuyển toàn bộ dữ liệu về chuỗi. Cần xác định nguyên nhân ở từng tầng: kiểu dữ liệu, điều kiện, session và quyền truy cập.

## 13. Bài thực hành tổng hợp

Phần này dùng bảng `DEMO_PRODUCTS` và `DEMO_PROMO_PRODUCTS` đã tạo phía trên. Mỗi truy vấn chỉ đọc dữ liệu. Nếu chưa tạo bảng mẫu, cần tạo trong schema thực hành trước.

### Bài 1 — IN trên nhóm

Yêu cầu: lấy tất cả sản phẩm thuộc ELECTRONICS hoặc ACCESSORIES, sắp theo ID tăng dần.

```sql
SELECT product_id, product_name, category
FROM   demo_products
WHERE  category IN ('ELECTRONICS', 'ACCESSORIES')
ORDER BY product_id;
```

**Kết quả mong đợi:** ID 1, 2, 3, 4, 5, 8, 9.

### Bài 2 — NOT IN và NULL

Yêu cầu: lấy sản phẩm không thuộc ELECTRONICS/ACCESSORIES **và** các sản phẩm chưa có nhóm.

```sql
SELECT product_id, product_name, category
FROM   demo_products
WHERE  category NOT IN ('ELECTRONICS', 'ACCESSORIES')
   OR  category IS NULL
ORDER BY product_id;
```

**Kết quả mong đợi:** ID 6 và 7. Đây là minh họa cho việc `NOT IN` không tự bao gồm NULL.

### Bài 3 — BETWEEN trên giá

Yêu cầu: giá từ 300.000 đến 8.000.000, bao gồm hai đầu.

```sql
SELECT product_id, product_name, price
FROM   demo_products
WHERE  price BETWEEN 300000 AND 8000000
ORDER BY price, product_id;
```

**Kết quả mong đợi:** ID 3, 7, 4 theo giá tăng dần.

### Bài 4 — Khoảng ngày giờ

Yêu cầu: các sản phẩm được tạo trong hai ngày 14 và 15/11/2026, kể cả lúc 17:30 ngày 15.

```sql
SELECT product_id,
       product_name,
       TO_CHAR(created_at, 'YYYY-MM-DD HH24:MI:SS') AS created_text
FROM   demo_products
WHERE  created_at >= DATE '2026-11-14'
AND    created_at <  DATE '2026-11-16'
ORDER  BY created_at, product_id;
```

**Kết quả mong đợi:** ID 1, 3, 2 theo thời gian tăng dần.

### Bài 5 — LIKE với tiền tố

Yêu cầu: tên bắt đầu bằng `Laptop`.

```sql
SELECT product_id, product_name
FROM   demo_products
WHERE  product_name LIKE 'Laptop%'
ORDER BY product_id;
```

**Kết quả mong đợi:** ID 1, 2.

### Bài 6 — LIKE với chuỗi chứa bên trong

Yêu cầu: tìm tên chứa `USB`.

```sql
SELECT product_id, product_name
FROM   demo_products
WHERE  product_name LIKE '%USB%'
ORDER BY product_id;
```

**Kết quả mong đợi:** ID 5.

### Bài 7 — ESCAPE dấu underscore

Yêu cầu: tìm SKU bắt đầu bằng chính chuỗi `LP_`.

```sql
SELECT product_id, sku
FROM   demo_products
WHERE  sku LIKE 'LP\_%' ESCAPE '\'
ORDER BY product_id;
```

**Kết quả mong đợi:** ID 1.

### Bài 8 — ESCAPE dấu phần trăm

Yêu cầu: tìm mọi tên có dấu phần trăm thật.

```sql
SELECT product_id, product_name
FROM   demo_products
WHERE  product_name LIKE '%\%%' ESCAPE '\'
ORDER BY product_id;
```

**Kết quả mong đợi:** ID 4, 8.

### Bài 9 — NOT IN với subquery có NULL

Trong `DEMO_PROMO_PRODUCTS`, nếu đã thêm `NULL` ở mục 3.3, chạy:

```sql
SELECT product_id
FROM   demo_products
WHERE  product_id NOT IN (
         SELECT product_id FROM demo_promo_products
       );
```

**Kỳ vọng:** không có dòng. Đây là đặc tính ba giá trị, không phải khẳng định mọi sản phẩm đều thuộc danh sách khuyến mại.

Thử viết lại:

```sql
SELECT p.product_id
FROM   demo_products p
WHERE NOT EXISTS (
    SELECT 1
    FROM   demo_promo_products x
    WHERE  x.product_id = p.product_id
)
ORDER BY p.product_id;
```

**Kỳ vọng:** mọi sản phẩm trừ 1 và 3; cụ thể ID 2, 4, 5, 6, 7, 8, 9.

### Bài 10 — Kết hợp ba điều kiện

Yêu cầu: chỉ lấy sản phẩm thuộc nhóm ELECTRONICS hoặc ACCESSORIES, giá trong khoảng 300.000 đến 10.000.000 và tên chứa `o` theo cấu hình so khớp hiện tại.

```sql
SELECT product_id, product_name, category, price
FROM   demo_products
WHERE  category IN ('ELECTRONICS', 'ACCESSORIES')
AND    price BETWEEN 300000 AND 10000000
AND    product_name LIKE '%o%'
ORDER  BY product_id;
```

Điều này luyện kết hợp ba phép lọc. Với so khớp phân biệt chữ hoa–thường thông thường, các kết quả phù hợp từ bảng mẫu gồm **3 (Mouse A_100)** và **4 (Monitor 27%)**. Nếu collation thay đổi, cần đối chiếu ngữ nghĩa mẫu chữ hoa–thường trước khi đánh giá.

### Bài 11 — Quan sát kiểu dữ liệu

```sql
SELECT column_name, data_type, data_length
FROM   user_tab_columns
WHERE  table_name = 'DEMO_PRODUCTS'
ORDER BY column_id;
```

Đối chiếu để hiểu vì sao `PRICE` nên dùng so sánh số, `CREATED_AT` nên dùng khoảng DATE và `PRODUCT_NAME` mới là cột thích hợp cho `LIKE`.

### Bài 12 — Dọn dữ liệu thực hành

Chỉ thực hiện khi xác nhận đây là các bảng demo do bạn tạo và không chứa dữ liệu cần lưu:

```sql
-- THAO TÁC PHÁ HỦY, chỉ dành cho schema học tập.
DROP TABLE demo_promo_products PURGE;
DROP TABLE demo_products PURGE;
```

`DROP TABLE ... PURGE` xóa đối tượng và bỏ qua recycle bin tương ứng. Đây là DDL, không xem `ROLLBACK` là cách hoàn tác đáng tin cậy. Không chạy trên bảng sản xuất.

## 14. Những nhầm lẫn cần tránh

**“`IN (1,3,5)` nghĩa là từ 1 đến 5.”**  
Không. Nó chỉ kiểm tra đúng các giá trị 1, 3, 5. Nếu cần khoảng, dùng `BETWEEN 1 AND 5` hoặc `>=`/`<=`.

**“Thứ tự giá trị trong IN quyết định thứ tự kết quả.”**  
Không. Chỉ `ORDER BY` mới đảm bảo thứ tự kết quả SELECT theo yêu cầu.

**“`NOT IN ('A','B')` sẽ lấy cả NULL.”**  
Không. Với giá trị NULL, điều kiện không được đánh giá TRUE. Nếu nghiệp vụ muốn chọn NULL, thêm `OR column IS NULL`.

**“`NOT IN` luôn an toàn khi dùng subquery.”**  
Không. Một `NULL` trong tập subquery có thể khiến toàn bộ truy vấn loại trừ không trả hàng nào. Cân nhắc `NOT EXISTS` hoặc lọc NULL có chủ đích.

**“`BETWEEN` không gồm hai đầu mút.”**  
Sai. `BETWEEN` bao gồm cả đầu thấp và đầu cao.

**“`BETWEEN DATE '2026-11-14' AND DATE '2026-11-15'` lấy trọn hai ngày.”**  
Không. Đầu trên chỉ là đầu ngày 15; các thời điểm sau nửa đêm ngày 15 sẽ nằm ngoài khoảng.

**“`LIKE 'A_B'` tìm dấu gạch dưới.”**  
Không. `_` là một wildcard khớp đúng một ký tự. Dùng `ESCAPE` hoặc toán tử `=` khi muốn underscore thật.

**“`LIKE '100%'` nghĩa là chuỗi có dấu phần trăm.”**  
Không. `%` là wildcard. Phải escape nếu muốn dấu phần trăm literal.

**“`LIKE` luôn không phân biệt hoa–thường.”**  
Không. Điều đó phụ thuộc ngữ nghĩa so khớp/collation của môi trường.

**“Dùng `TO_CHAR` cho mọi cột thì lọc sẽ dễ hơn.”**  
Không. Nó có thể gây chuyển đổi kiểu, phụ thuộc format và ảnh hưởng khả năng dùng index. Nên lọc theo kiểu dữ liệu gốc.

**“`LIKE '%'` chọn tất cả dòng, kể cả cột NULL.”**  
Không. NULL khiến điều kiện không TRUE. Muốn chọn cả NULL cần biểu diễn rõ trong SQL.

## 15. Câu hỏi tự kiểm tra

1. Trong Oracle, `price IN (100, 200, 300)` tương đương ý tưởng nào: tập ba giá trị hay khoảng 100–300?
2. `price BETWEEN 100 AND 300` có lấy các giá 100 và 300 không?
3. Nếu giá không xác định (`NULL`), `price NOT BETWEEN 100 AND 300` có tự chọn nó không?
4. Với chuỗi `'Laptop Pro'`, mẫu `'Laptop%'` có khớp không?
5. Mẫu `'LP_01'` trong `LIKE` có bắt buộc ký tự thứ ba là dấu underscore không?
6. Viết điều kiện `LIKE` tìm tên có dấu phần trăm thực ở vị trí bất kỳ.
7. Vì sao `NOT IN (1, 3, NULL)` thường không trả về các ID khác 1 và 3?
8. Trong bảng có nhiều dữ liệu, tại sao `LIKE 'Lap%'` thường thuận lợi hơn `LIKE '%Lap%'` cho B-tree index thông thường?
9. Một cột `DATE` có các mốc lúc 09:15 ngày 14 và 17:30 ngày 15. Vì sao khoảng `BETWEEN DATE '2026-11-14' AND DATE '2026-11-15'` bỏ sót mốc 17:30?
10. Câu `WHERE category = 'A' OR category = 'B' AND price > 100` có áp dụng điều kiện giá cho nhóm A không?
11. Nếu người dùng nhập `'12%'` vào ô tìm kiếm “tìm chuỗi con đúng nguyên văn”, cần xử lý ký tự nào trước khi thêm wildcard từ ứng dụng?
12. Có thể bind một chuỗi `'1,3,5'` vào một `:ids` để Oracle tự hiểu `IN (:ids)` như danh sách ba ID không?
13. Sản phẩm có `CATEGORY=NULL` có được chọn bởi `category IN ('ELECTRONICS','ACCESSORIES')` không?
14. Nếu mục tiêu lấy toàn bộ tháng 11/2026, nên dùng khoảng thời gian như thế nào?
15. Khi muốn tìm đúng SKU `'LP_01'` và không cần wildcard, nên dùng `=` hay `LIKE`?

**Gợi ý đáp án:**

1. Tập ba giá trị 100, 200, 300.
2. Có, vì hai đầu mút được bao gồm.
3. Không; cần `OR price IS NULL` nếu nghiệp vụ muốn chọn giá chưa biết.
4. Có, vì `%` có thể khớp mọi phần đuôi.
5. Không; `_` khớp một ký tự bất kỳ.
6. `product_name LIKE '%\%%' ESCAPE '\'`.
7. Vì `NULL` khiến những so sánh loại trừ còn lại thành UNKNOWN theo logic ba giá trị.
8. Mẫu có tiền tố cố định thuận lợi hơn cho tìm kiếm dải khóa; mẫu bắt đầu bằng `%` thường không giúp xác định điểm bắt đầu trong B-tree theo cách đó.
9. `DATE '2026-11-15'` là thời điểm 00:00 ngày 15, không phải cuối ngày 15.
10. Không; `AND` có ưu tiên cao hơn `OR`. Cần dùng dấu ngoặc hoặc `IN`.
11. Escape marker, `%` và `_`; sau đó bind pattern đã xây dựng an toàn.
12. Không, đó thường là một bind value chứ không phải danh sách đã tách.
13. Không, điều kiện là UNKNOWN đối với NULL.
14. `created_at >= DATE '2026-11-01' AND created_at < DATE '2026-12-01'`.
15. `sku = 'LP_01'`.

## 16. Tài liệu Oracle tham khảo

- [Oracle Database SQL Language Reference — IN Condition](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/IN-Condition.html): cú pháp danh sách và subquery, hành vi của `IN`/`NOT IN`.
- [Oracle Database SQL Language Reference — BETWEEN Condition](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/BETWEEN-Condition.html): điều kiện khoảng và hai đầu mút.
- [Oracle Database SQL Language Reference — Pattern-matching Conditions](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/Pattern-matching-Conditions.html): `LIKE`, `%`, `_`, `ESCAPE` và các biến thể Unicode.
- [Oracle Database SQL Language Reference — NULL Conditions](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/Null-Conditions.html): `IS NULL` và `IS NOT NULL`.
- [Oracle Database SQL Language Reference — EXISTS Condition](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/EXISTS-Condition.html): kiểm tra sự tồn tại của dòng trong truy vấn con.
- [Oracle Database SQL Language Reference — Logical Conditions](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/Logical-Conditions.html): `AND`, `OR`, `NOT` và logic ba giá trị.
- [Oracle Database SQL Language Reference — Data Type Comparison Rules](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/Data-Type-Comparison-Rules.html): so sánh số, ký tự, ngày giờ và quy tắc chuyển đổi.
- [Oracle Database SQL Tuning Guide](https://docs.oracle.com/en/database/oracle/oracle-database/19/tgsql/): optimizer, access paths, index và cách phân tích kế hoạch truy vấn.
- [Oracle Database SQL Language Reference — SELECT](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/SELECT.html): cấu trúc `SELECT`, `WHERE` và `ORDER BY`.

Khi chọn giữa `IN`, `BETWEEN` và `LIKE`, hãy xuất phát từ **ý nghĩa câu hỏi**: kiểm tra một **tập giá trị**, một **khoảng có ranh giới**, hay một **mẫu chuỗi**. Luôn xác định cách xử lý **`NULL`**, dùng `ESCAPE` nếu `%`/`_` là ký tự dữ liệu, sử dụng **khoảng nửa mở cho ngày giờ** và truyền giá trị từ ứng dụng qua **bind variables**. Những thói quen này giúp truy vấn Oracle đúng nghĩa nghiệp vụ, dễ đọc và giảm lỗi giữa các môi trường.
