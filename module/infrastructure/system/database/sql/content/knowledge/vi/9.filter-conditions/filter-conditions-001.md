# Toán tử so sánh bằng, khác và thứ tự

Trong SQL, phần lớn câu hỏi dữ liệu đều bắt đầu bằng một điều kiện: “đơn hàng nào đã thanh toán?”, “sản phẩm nào có giá **ít nhất** 150.000 đồng?”, “nhân viên nào vào làm **trước** ngày 1/2?”, hoặc “bản ghi nào có trạng thái **khác** `CANCELLED`?”. Các điều kiện đó được biểu diễn bằng **toán tử so sánh** (*comparison operators*).

Nhóm toán tử cơ bản gồm **bằng (`=`), khác (`<>`), nhỏ hơn (`<`), nhỏ hơn hoặc bằng (`<=`), lớn hơn (`>`) và lớn hơn hoặc bằng (`>=`)**. Chúng thường xuất hiện trong `WHERE` để lọc hàng, trong `JOIN ... ON` để ghép dữ liệu, trong `HAVING` để lọc nhóm, và trong các biểu thức điều kiện khác. Để dùng đúng, cần quan tâm cả **kiểu dữ liệu**, **giá trị biên**, **`NULL`** và cách kết hợp nhiều điều kiện.

Bài học sử dụng bảng dữ liệu mẫu đơn giản, các câu SQL có thể chạy bằng PostgreSQL và phần giải thích những khác biệt cần lưu ý trên các hệ quản trị khác.

## 1. Khái niệm: điều kiện so sánh và kết quả logic

Một biểu thức so sánh thường có dạng:

```sql
gia_tri_hoac_cot TOAN_TU gia_tri_hoac_cot_khac
```

Ví dụ:

```sql
price = 180000
stock_qty > 0
listed_on < DATE '2025-02-01'
category <> 'BOOK'
```

Mỗi biểu thức trả về một kết quả logic. Với hai giá trị đều đã biết, kết quả thông thường là **`TRUE`** hoặc **`FALSE`**. Nếu một phía là **`NULL`**, so sánh thông thường có thể trả **`UNKNOWN`** (chưa xác định). `WHERE` chỉ giữ những hàng mà toàn bộ điều kiện là `TRUE`.

### Các toán tử cơ bản

| Toán tử SQL | Nghĩa | Ví dụ | Kết quả với các giá trị đã biết |
|---|---|---|---|
| `=` | Bằng | `10 = 10` | `TRUE` |
| `<>` | Khác | `10 <> 12` | `TRUE` |
| `<` | Nhỏ hơn | `10 < 12` | `TRUE` |
| `<=` | Nhỏ hơn hoặc bằng | `10 <= 10` | `TRUE` |
| `>` | Lớn hơn | `12 > 10` | `TRUE` |
| `>=` | Lớn hơn hoặc bằng | `10 >= 10` | `TRUE` |

**`=` là phép so sánh bằng trong SQL**, không phải phép gán trong các câu `SELECT` thông thường. Lập trình viên Java cần phân biệt: Java dùng `==` để so sánh các giá trị nguyên thủy, còn SQL dùng **`=`**. Toán tử bất đẳng chuẩn SQL là **`<>`**; PostgreSQL, MySQL và một số hệ khác còn hỗ trợ **`!=`** như cách viết mở rộng, nhưng `<>` dễ di chuyển giữa các DBMS hơn.

**Toán tử thứ tự (`<`, `<=`, `>`, `>=`)** so sánh quan hệ lớn/nhỏ giữa các giá trị. Đối với số, ý nghĩa khá trực quan; đối với ngày giờ là trước/sau; đối với chuỗi, thứ tự có thể phụ thuộc quy tắc đối chiếu ký tự (*collation*).

## 2. Tạo bộ dữ liệu mẫu để thực hành

Để mọi ví dụ có kết quả nhất quán, hãy tạo một bảng sản phẩm nhỏ trong **cơ sở dữ liệu học tập riêng**. Chạy một lần:

```sql
CREATE TABLE shop_items (
    item_id INTEGER PRIMARY KEY,
    sku VARCHAR(30) NOT NULL UNIQUE,
    item_name VARCHAR(100) NOT NULL,
    category VARCHAR(20) NOT NULL,
    price NUMERIC(12, 2) NOT NULL,
    stock_qty INTEGER NOT NULL,
    listed_on DATE NOT NULL,
    rating NUMERIC(3, 1)
);

INSERT INTO shop_items
    (item_id, sku, item_name, category, price, stock_qty, listed_on, rating)
VALUES
    (1, 'BOOK-SQL',  'SQL cơ bản',     'BOOK',       120000.00, 12, DATE '2025-01-10', 4.5),
    (2, 'BOOK-JAVA', 'Java nền tảng',  'BOOK',       180000.00,  0, DATE '2025-01-15', 4.8),
    (3, 'MOUSE-01',  'Chuột quang',    'DEVICE',     150000.00,  7, DATE '2025-02-01', 4.0),
    (4, 'KEY-01',    'Bàn phím',       'DEVICE',     350000.00,  3, DATE '2025-02-10', NULL),
    (5, 'NOTE-01',   'Sổ tay',         'STATIONERY',  25000.00, 50, DATE '2025-02-12', 4.2),
    (6, 'PEN-01',    'Bút',            'STATIONERY',  10000.00,  0, DATE '2025-03-01', NULL),
    (7, 'BOOK-DB',   'Thiết kế DB',    'BOOK',       180000.00,  5, DATE '2025-03-04', 4.6);
```

Tra cứu dữ liệu:

```sql
SELECT item_id, category, price, stock_qty, listed_on, rating
FROM shop_items
ORDER BY item_id;
```

| item_id | category | price | stock_qty | listed_on | rating |
|---:|---|---:|---:|---|---:|
| 1 | BOOK | 120000.00 | 12 | 2025-01-10 | 4.5 |
| 2 | BOOK | 180000.00 | 0 | 2025-01-15 | 4.8 |
| 3 | DEVICE | 150000.00 | 7 | 2025-02-01 | 4.0 |
| 4 | DEVICE | 350000.00 | 3 | 2025-02-10 | `NULL` |
| 5 | STATIONERY | 25000.00 | 50 | 2025-02-12 | 4.2 |
| 6 | STATIONERY | 10000.00 | 0 | 2025-03-01 | `NULL` |
| 7 | BOOK | 180000.00 | 5 | 2025-03-04 | 4.6 |

Từ đây, các kết quả ví dụ giả sử bảng giữ nguyên **7 hàng ban đầu**. Những điều kiện dùng chuỗi sẽ dựa vào các mã danh mục in hoa cố định (`BOOK`, `DEVICE`, `STATIONERY`), tránh phụ thuộc những khác biệt đối chiếu dấu và chữ hoa/thường ở tên sản phẩm.

## 3. So sánh bằng: `=`

Toán tử `=` chọn giá trị **bằng với** một giá trị khác. Ví dụ tìm sản phẩm có giá chính xác 180.000 đồng:

```sql
SELECT item_id, item_name, price
FROM shop_items
WHERE price = 180000
ORDER BY item_id;
```

| item_id | item_name | price |
|---:|---|---:|
| 2 | Java nền tảng | 180000.00 |
| 7 | Thiết kế DB | 180000.00 |

Hai sản phẩm bằng giá đều được trả về. `WHERE price = 180000` không có nghĩa “chỉ lấy sản phẩm đầu tiên”. Truy vấn quan hệ trả về **tất cả** hàng đáp ứng điều kiện, trừ khi có giới hạn khác.

So sánh giá trị văn bản:

```sql
SELECT item_id, item_name, category
FROM shop_items
WHERE category = 'BOOK'
ORDER BY item_id;
```

Kết quả gồm **1, 2, 7**. Giá trị `'BOOK'` phải được đặt trong dấu nháy đơn vì đây là **chuỗi ký tự**. Nếu viết `WHERE category = BOOK` mà không có dấu nháy, DBMS có thể hiểu `BOOK` là tên cột/định danh và báo lỗi.

### 3.1. So sánh với hai cột

Hai vế của `=` không nhất thiết là “tên cột” và “hằng số”; có thể là hai cột:

```sql
-- Ví dụ cấu trúc điều kiện dùng khi đã có hai cột số:
WHERE paid_amount = expected_amount
```

Trong một `JOIN`, điều kiện bằng thường nối khóa ngoại với khóa chính:

```sql
-- Minh họa trên hai bảng giả định orders và customers:
SELECT o.order_id, c.full_name
FROM orders AS o
JOIN customers AS c
    ON o.customer_id = c.customer_id;
```

Ví dụ nối bảng là để nhận diện vị trí dùng toán tử, **không chạy trực tiếp trên bảng `shop_items`**, vì bộ dữ liệu thực hành hiện chỉ tạo bảng đó.

### 3.2. So sánh chuỗi và độ nhạy hoa/thường

So sánh `category = 'BOOK'` khác với “tên sản phẩm chứa chữ `book`”. **So sánh bằng** xét giá trị toàn phần theo quy tắc so sánh của kiểu và collation; **tìm mẫu chuỗi** là việc khác, thường dùng `LIKE` hoặc những khả năng tìm kiếm văn bản chuyên biệt.

Đối với chuỗi, chữ hoa/thường, dấu tiếng Việt, khoảng trắng và quy tắc sắp xếp **có thể** ảnh hưởng kết quả, tùy DBMS, collation và kiểu cột. Không mặc định mọi cơ sở dữ liệu đều xử lý `'book'` và `'BOOK'` như nhau. Với mã định danh nghiệp vụ như `category`, nên thống nhất giá trị lưu trữ ngay từ đầu.

## 4. So sánh khác: `<>`

Toán tử `<>` biểu diễn “khác với”. Ví dụ tìm các sản phẩm **không thuộc danh mục BOOK**:

```sql
SELECT item_id, category
FROM shop_items
WHERE category <> 'BOOK'
ORDER BY item_id;
```

Kết quả là **3, 4, 5, 6**. Danh mục của mỗi hàng đều có giá trị rõ ràng (cột `category` là `NOT NULL`), nên phép so sánh trả về `TRUE` hoặc `FALSE`.

Tìm sản phẩm có giá **khác** 180.000:

```sql
SELECT item_id, price
FROM shop_items
WHERE price <> 180000
ORDER BY item_id;
```

Kết quả gồm **1, 3, 4, 5, 6**. Sản phẩm 2 và 7 bị loại vì giá bằng 180.000.

Cách viết `price != 180000` cũng được PostgreSQL chấp nhận, nhưng trong tài liệu học SQL nên ưu tiên **`<>`** theo ký hiệu chuẩn. Đừng nhầm `<>` với `NOT IN` hoặc `NOT LIKE`: các toán tử sau phục vụ kiểm tra tập giá trị hay mẫu chuỗi.

### 4.1. `<>` không có nghĩa “bao gồm NULL”

Đây là một trong những lỗi thường gặp nhất. Cột `rating` của sản phẩm 4 và 6 có `NULL` (chưa có điểm đánh giá). Xét:

```sql
SELECT item_id, rating
FROM shop_items
WHERE rating <> 4.5
ORDER BY item_id;
```

Kết quả: **2, 3, 5, 7**. Sản phẩm 1 bị loại vì điểm bằng 4.5. Sản phẩm **4 và 6 cũng không xuất hiện**, vì `NULL <> 4.5` có kết quả **`UNKNOWN`**, không phải `TRUE`.

Nếu ý định là “không có điểm 4.5, kể cả chưa được đánh giá”, cần nói rõ:

```sql
SELECT item_id, rating
FROM shop_items
WHERE rating <> 4.5
   OR rating IS NULL
ORDER BY item_id;
-- 2, 3, 4, 5, 6, 7
```

Ngược lại, nếu người dùng chỉ muốn những sản phẩm **đã được đánh giá** với số điểm khác 4.5, điều kiện `rating <> 4.5` ban đầu là hợp lý. Hai cách viết phục vụ **hai ý nghĩa nghiệp vụ khác nhau**.

## 5. So sánh thứ tự: `<`, `<=`, `>` và `>=`

Bốn toán tử này là nền tảng của điều kiện khoảng giá trị, mốc thời gian và ngưỡng nghiệp vụ:

| Điều kiện | Ý nghĩa với `price` | ID thỏa trên dữ liệu mẫu |
|---|---|---|
| `price < 150000` | Rẻ hơn 150.000, **không tính bằng** | 1, 5, 6 |
| `price <= 150000` | Không đắt hơn 150.000, **có tính bằng** | 1, 3, 5, 6 |
| `price > 150000` | Đắt hơn 150.000, **không tính bằng** | 2, 4, 7 |
| `price >= 150000` | Ít nhất 150.000, **có tính bằng** | 2, 3, 4, 7 |

Hàng có giá **đúng 150.000** (sản phẩm 3) là cách dễ nhất để phân biệt `<` với `<=` và `>` với `>=`. Dấu **`=`** gắn kèm làm cho **giá trị biên** được tính vào kết quả.

Ví dụ: “sản phẩm có giá từ 150.000 đồng trở lên”:

```sql
SELECT item_id, item_name, price
FROM shop_items
WHERE price >= 150000
ORDER BY price, item_id;
```

Kết quả có các ID **3, 2, 7, 4** theo thứ tự giá tăng dần rồi ID. Ở đây `WHERE` quyết định hàng nào được giữ; `ORDER BY` quyết định thứ tự hiển thị.

### 5.1. Kết hợp hai điều kiện tạo khoảng giá

“Giá từ 150.000 đến 180.000, tính cả hai đầu” có thể viết:

```sql
SELECT item_id, price
FROM shop_items
WHERE price >= 150000
  AND price <= 180000
ORDER BY price, item_id;
```

Kết quả:

| item_id | price |
|---:|---:|
| 3 | 150000.00 |
| 2 | 180000.00 |
| 7 | 180000.00 |

Một cách viết tương đương cho các giá trị đã biết là:

```sql
WHERE price BETWEEN 150000 AND 180000
```

**`BETWEEN` bao gồm cả hai biên** trong điều kiện thông thường: tương đương `price >= 150000 AND price <= 180000`. Nếu muốn **lớn hơn 150.000 nhưng nhỏ hơn 180.000**, phải dùng `>` và `<`; với dữ liệu hiện tại, khoảng mở đó không chứa sản phẩm nào.

Khi dùng thời gian có cả giờ phút giây, nhiều hệ thống thích khoảng **nửa mở** (bao gồm mốc đầu, không bao gồm mốc cuối), ví dụ `timestamp >= start_time AND timestamp < next_day`. Cách này tránh bỏ sót các thời điểm nằm trong ngày khi không thể biểu diễn chính xác “giây cuối cùng”.

### 5.2. So sánh số lượng tồn kho

Tìm sản phẩm **còn hàng**:

```sql
SELECT item_id, stock_qty
FROM shop_items
WHERE stock_qty > 0
ORDER BY item_id;
-- 1, 3, 4, 5, 7
```

Tìm sản phẩm **hết hàng**:

```sql
SELECT item_id, stock_qty
FROM shop_items
WHERE stock_qty = 0
ORDER BY item_id;
-- 2, 6
```

Nếu chỉ muốn xem sản phẩm có số lượng tồn **ít hơn 5**, điều kiện `stock_qty < 5` trả về **2, 4, 6** vì tồn kho bằng 0 cũng nhỏ hơn 5. Nếu muốn “sắp hết hàng nhưng vẫn còn ít nhất một sản phẩm”, phải viết `stock_qty > 0 AND stock_qty < 5`; kết quả chỉ còn **4**.

Từ “dưới 5”, “không quá 5”, “ít nhất 5” và “trên 5” tương ứng với bốn điều kiện khác nhau. Trước khi viết truy vấn, hãy xác định rõ **giá trị bằng ngưỡng có được chấp nhận hay không**.

## 6. Kiểu dữ liệu quyết định cách so sánh

### 6.1. Số nguyên, số thập phân và độ chính xác

Trong ví dụ, `stock_qty` là `INTEGER`, `price` là `NUMERIC(12,2)`. So sánh `price = 180000` là so sánh giá trị **số**, không phải so sánh từng ký tự.

Một số tình huống cần lưu ý:

- `'100'` và `'20'` là **chuỗi**. Thứ tự của chuỗi không nhất thiết giống thứ tự của số 100 và 20. Cần lưu số lượng/giá tiền bằng kiểu số thích hợp.
- Kiểu số thực dấu phẩy động (`REAL`, `DOUBLE PRECISION`) có thể chứa sai số biểu diễn nhị phân. Khi so sánh bằng các **kết quả tính toán dấu phẩy động**, không nên giả định mọi kết quả sẽ bằng chính xác một hằng thập phân.
- Tiền tệ và các giá trị yêu cầu độ chính xác thập phân thường phù hợp với `NUMERIC`/`DECIMAL` cùng quy tắc làm tròn rõ ràng.
- Việc ép kiểu ngầm từ chuỗi sang số có thể khác nhau giữa DBMS hoặc bị từ chối. Tránh trông chờ `WHERE price = '180000'` luôn hoạt động như nhau; nên dùng tham số đúng kiểu số.

Ví dụ so sánh số nguyên với số nguyên:

```sql
SELECT item_id
FROM shop_items
WHERE stock_qty >= 10
ORDER BY item_id;
-- 1, 5
```

### 6.2. Ngày và thời điểm

Vì `listed_on` là `DATE`, có thể so sánh trực tiếp với literal ngày cùng kiểu:

```sql
SELECT item_id, listed_on
FROM shop_items
WHERE listed_on < DATE '2025-02-01'
ORDER BY listed_on, item_id;
-- 1 (2025-01-10), 2 (2025-01-15)
```

**“Trước ngày 1/2”** dùng `< DATE '2025-02-01'`, nên bản ghi đúng ngày 1/2 (sản phẩm 3) không được chọn. **“Từ ngày 1/2 trở đi”** dùng `>= DATE '2025-02-01'`, nên bao gồm sản phẩm 3 và các bản ghi sau đó.

Với cột thời điểm chứa giờ phút giây, cần nắm rõ kiểu `TIMESTAMP`, `TIMESTAMP WITH TIME ZONE` và cách diễn giải múi giờ của DBMS/ứng dụng. Đừng dùng so sánh chuỗi theo định dạng ngày địa phương, chẳng hạn `'01/02/2025'`, để thay thế một giá trị `DATE` hoặc `TIMESTAMP` được chuẩn hóa.

Ví dụ lọc trọn tháng 2 bằng cột `DATE`:

```sql
SELECT item_id, listed_on
FROM shop_items
WHERE listed_on >= DATE '2025-02-01'
  AND listed_on < DATE '2025-03-01'
ORDER BY listed_on, item_id;
-- 3, 4, 5
```

Cách viết **`>=` mốc đầu và `<` mốc đầu tháng tiếp theo** diễn đạt phạm vi rõ ràng, cũng hữu ích khi chuyển sang kiểu timestamp.

### 6.3. Chuỗi ký tự: thứ tự từ điển phụ thuộc collation

Với cột văn bản, các toán tử thứ tự cũng có thể dùng:

```sql
SELECT item_id, sku
FROM shop_items
WHERE sku >= 'M'
ORDER BY sku, item_id;
```

Nhưng thứ tự ký tự **không phải quy tắc số học**. Kết quả phụ thuộc cách DBMS và **collation** đối chiếu chuỗi, ví dụ phân biệt chữ hoa/thường, dấu và các ký tự Unicode. Không sử dụng so sánh văn bản để thay thế so sánh số hoặc ngày chỉ vì giá trị đang được lưu trong `VARCHAR`.

Trong các hệ thống khác nhau, `'a' = 'A'` có thể có hành vi khác tùy kiểu và collation; độ dài, dấu và chuẩn hóa Unicode cũng có thể ảnh hưởng. Để lọc mã SKU hoặc danh mục, nên dùng quy ước lưu trữ nhất quán và hiểu cấu hình đối chiếu đang áp dụng.

## 7. NULL và logic ba giá trị trong điều kiện lọc

Giả sử `rating` chưa có giá trị cho một số sản phẩm. Xét:

```sql
SELECT item_id, rating
FROM shop_items
WHERE rating >= 4.5
ORDER BY item_id;
```

Kết quả là **1, 2, 7**. Các giá trị 4.5, 4.8, 4.6 thỏa điều kiện; 4.0 và 4.2 không thỏa. Hai hàng có `rating = NULL` (4 và 6) **không được chọn**, vì so sánh với `NULL` trả về **`UNKNOWN`**.

| Biểu thức | Kết quả |
|---|---|
| `4.5 = 4.5` | `TRUE` |
| `4.0 >= 4.5` | `FALSE` |
| `NULL >= 4.5` | `UNKNOWN` |
| `NULL = NULL` | `UNKNOWN` |
| `NULL <> 4.5` | `UNKNOWN` |
| `NULL IS NULL` | `TRUE` |

Trong `WHERE`, **chỉ hàng có điều kiện `TRUE` được giữ**. Cả `FALSE` và `UNKNOWN` đều bị loại.

### 7.1. Cách kiểm tra NULL đúng

Không viết:

```sql
-- Sai mục đích: không chọn được các hàng có giá trị NULL.
SELECT item_id
FROM shop_items
WHERE rating = NULL;
```

Thay vào đó:

```sql
SELECT item_id
FROM shop_items
WHERE rating IS NULL
ORDER BY item_id;
-- 4, 6
```

Để chọn sản phẩm đã có điểm đánh giá:

```sql
SELECT item_id
FROM shop_items
WHERE rating IS NOT NULL
ORDER BY item_id;
-- 1, 2, 3, 5, 7
```

**`NULL` khác 0**. Sản phẩm có điểm đánh giá bằng 0 (nếu tồn tại) vẫn là sản phẩm có điểm đã biết; sản phẩm `rating IS NULL` là chưa có điểm hoặc chưa xác định điểm.

### 7.2. Phép so sánh nhận biết NULL ở cả hai phía

PostgreSQL và một số hệ khác hỗ trợ:

```sql
-- PostgreSQL:
SELECT item_id
FROM shop_items
WHERE rating IS DISTINCT FROM 4.5
ORDER BY item_id;
-- 2, 3, 4, 5, 6, 7
```

`IS DISTINCT FROM` xử lý `NULL` như một trường hợp so sánh riêng: hai `NULL` được xem như **không khác nhau** trong phép này; một `NULL` và một giá trị đã biết thì **khác nhau**. Kết quả của phép này không là `UNKNOWN`. `IS NOT DISTINCT FROM` là dạng phủ định, hữu ích khi cần so sánh null-safe.

Không tự thay mọi `<>` bằng `IS DISTINCT FROM`. Nếu yêu cầu nghiệp vụ là **“điểm đã biết và khác 4.5”**, phép `<>` ban đầu là đúng. Chỉ thêm `NULL` vào tập kết quả khi điều đó có chủ đích.

## 8. Kết hợp toán tử so sánh bằng AND, OR và NOT

Một điều kiện lọc thường gồm nhiều phép so sánh. **`AND`** yêu cầu đồng thời thỏa các điều kiện; **`OR`** cho phép thỏa ít nhất một điều kiện; **`NOT`** phủ định kết quả logic.

Ví dụ “sản phẩm còn hàng, giá dưới 200.000”:

```sql
SELECT item_id, item_name, stock_qty, price
FROM shop_items
WHERE stock_qty > 0
  AND price < 200000
ORDER BY item_id;
-- 1, 3, 5, 7
```

Ví dụ “sản phẩm thuộc danh mục BOOK hoặc DEVICE”:

```sql
SELECT item_id, category
FROM shop_items
WHERE category = 'BOOK'
   OR category = 'DEVICE'
ORDER BY item_id;
-- 1, 2, 3, 4, 7
```

Khi chỉ so sánh một cột với một tập giá trị cố định, có thể dùng `IN`:

```sql
WHERE category IN ('BOOK', 'DEVICE')
```

Câu này tương đương với `category = 'BOOK' OR category = 'DEVICE'` đối với những giá trị danh mục đã biết.

### 8.1. Dùng ngoặc để biểu đạt đúng ưu tiên

SQL thông thường đánh giá **`NOT` trước `AND`, `AND` trước `OR`**. Vì vậy:

```sql
-- Không giống yêu cầu “hai loại hàng và đều phải còn kho”:
WHERE category = 'BOOK'
   OR category = 'DEVICE' AND stock_qty > 0
```

Biểu thức trên được hiểu gần như:

```sql
WHERE category = 'BOOK'
   OR (category = 'DEVICE' AND stock_qty > 0)
```

Nó sẽ giữ cả sản phẩm BOOK hết hàng (ID 2). Nếu mục tiêu là **cả BOOK lẫn DEVICE đều phải còn hàng**, hãy đặt ngoặc:

```sql
SELECT item_id, category, stock_qty
FROM shop_items
WHERE (category = 'BOOK' OR category = 'DEVICE')
  AND stock_qty > 0
ORDER BY item_id;
-- 1, 3, 4, 7
```

Dùng ngoặc ngay khi điều kiện có cả `AND` và `OR` giúp người đọc xác nhận ý định nghiệp vụ, kể cả khi đã biết thứ tự ưu tiên toán tử.

### 8.2. NOT không tự biến UNKNOWN thành TRUE

Với một sản phẩm chưa có điểm:

```sql
WHERE NOT (rating = 4.5)
```

`rating = 4.5` cho `UNKNOWN`; `NOT UNKNOWN` vẫn là `UNKNOWN`. Do đó, điều kiện trên **không chọn** hai sản phẩm có `rating IS NULL`. Nếu muốn bao gồm cả sản phẩm chưa có điểm, sử dụng `rating <> 4.5 OR rating IS NULL` hoặc phép so sánh null-safe phù hợp.

## 9. So sánh trong WHERE, JOIN ON và HAVING

Toán tử so sánh giữ cùng ý nghĩa cơ bản nhưng được áp dụng ở những giai đoạn logic khác nhau của truy vấn:

| Vị trí | Mục đích | Ví dụ |
|---|---|---|
| `WHERE` | Lọc hàng trước khi tổng hợp | `WHERE price >= 150000` |
| `JOIN ... ON` | Quy định cặp hàng nào được ghép | `ON o.customer_id = c.customer_id` |
| `HAVING` | Lọc các **nhóm** sau `GROUP BY` | `HAVING COUNT(*) >= 2` |
| `CASE WHEN` | Quyết định nhánh theo điều kiện | `WHEN stock_qty = 0 THEN 'OUT'` |

Với bảng hiện tại, có thể lọc **những danh mục có ít nhất hai sản phẩm**:

```sql
SELECT category, COUNT(*) AS item_count
FROM shop_items
GROUP BY category
HAVING COUNT(*) >= 2
ORDER BY category;
```

Cả ba danh mục đều thỏa: `BOOK` có 3 sản phẩm, `DEVICE` có 2, `STATIONERY` có 2. `HAVING COUNT(*) >= 2` so sánh giá trị tổng hợp của từng **nhóm**, còn `WHERE price >= 150000` lọc từng **hàng**.

Khi dùng `LEFT JOIN`, điều kiện so sánh đặt trong `ON` hay `WHERE` có thể làm thay đổi việc giữ hàng không có đối tác: `ON` quyết định điều kiện ghép; `WHERE` lọc **kết quả sau khi nối**. Nếu cột phía phải bằng `NULL` do không có hàng khớp, một điều kiện so sánh trong `WHERE` có thể thành `UNKNOWN` và loại hàng đó. Vì thế phải đặt điều kiện theo đúng mục đích giữ hay loại dữ liệu.

## 10. `<` và `>` để lọc khác với ORDER BY để sắp xếp

Người mới học dễ nhầm **so sánh thứ tự** với **sắp xếp kết quả**:

- `WHERE price > 150000`: quyết định **hàng nào được giữ**, không bảo đảm thứ tự các hàng.
- `ORDER BY price DESC`: quyết định **thứ tự hàng được hiển thị**; nếu không có `WHERE` thì không loại hàng nào chỉ vì giá.

Ví dụ tìm các sản phẩm có giá từ 150.000 trở lên và xếp giá giảm dần:

```sql
SELECT item_id, item_name, price
FROM shop_items
WHERE price >= 150000
ORDER BY price DESC, item_id ASC;
```

| item_id | item_name | price |
|---:|---|---:|
| 4 | Bàn phím | 350000.00 |
| 2 | Java nền tảng | 180000.00 |
| 7 | Thiết kế DB | 180000.00 |
| 3 | Chuột quang | 150000.00 |

Hai sản phẩm có giá 180.000 bằng nhau. `ORDER BY price DESC, item_id ASC` quy định thêm **khóa phụ** để thứ tự giữa chúng có thể dự đoán được. Nếu chỉ `ORDER BY price DESC` thì thứ tự của hai hàng bằng giá **không được bảo đảm**. Không dùng thứ tự mà `SELECT` tình cờ trả về khi thiếu `ORDER BY` để suy luận lớn/nhỏ.

Đối với `NULL` trong sắp xếp, vị trí đầu/cuối tùy DBMS và kiểu `ASC`/`DESC`. PostgreSQL hỗ trợ `NULLS FIRST` và `NULLS LAST` để chỉ rõ, ví dụ:

```sql
SELECT item_id, rating
FROM shop_items
ORDER BY rating DESC NULLS LAST, item_id ASC;
```

Cách đặt `NULL` khi **sắp xếp** khác với kết quả `UNKNOWN` khi **so sánh trong `WHERE`**; đừng trộn hai quy tắc này.

## 11. Chọn điều kiện theo ngôn ngữ nghiệp vụ

Một yêu cầu viết bằng tiếng Việt có thể tương ứng với nhiều toán tử; quan trọng nhất là xác định **biên** và cách xử lý giá trị thiếu.

| Yêu cầu | Điều kiện gợi ý | Ghi chú |
|---|---|---|
| Giá **đúng** 180.000 | `price = 180000` | Bằng chính xác |
| Giá **khác** 180.000 | `price <> 180000` | Không tự bao gồm `NULL` |
| Giá **dưới** 150.000 | `price < 150000` | Không tính bằng |
| Giá **tối đa** 150.000 | `price <= 150000` | Có tính bằng |
| Giá **trên** 150.000 | `price > 150000` | Không tính bằng |
| Giá **ít nhất** 150.000 | `price >= 150000` | Có tính bằng |
| Tồn kho **từ 1 đến 4** | `stock_qty >= 1 AND stock_qty <= 4` | Hai đầu đều được tính |
| Niêm yết **trước** 1/2/2025 | `listed_on < DATE '2025-02-01'` | Không gồm ngày 1/2 |
| Niêm yết **trong tháng 2/2025** | `listed_on >= DATE '2025-02-01' AND listed_on < DATE '2025-03-01'` | Khoảng nửa mở |
| Chưa có đánh giá | `rating IS NULL` | Không dùng `rating = NULL` |
| Đánh giá đã biết và khác 4.5 | `rating <> 4.5` | Loại hàng `NULL` |
| Đánh giá khác 4.5 **hoặc chưa có** | `rating <> 4.5 OR rating IS NULL` | Chỉ khi nghiệp vụ yêu cầu |

Trong ứng dụng, giá trị đem so sánh thường đến từ người dùng. **Không nối trực tiếp chuỗi đầu vào** vào SQL, ví dụ ghép văn bản tạo `WHERE price > ...`. Dùng **prepared statement/truy vấn có tham số** để DBMS xử lý giá trị theo kiểu dữ liệu, đồng thời hạn chế SQL injection.

Ví dụ JDBC (ý tưởng, giả sử đã có đối tượng `connection`):

```java
String sql = """
    SELECT item_id, item_name, price
    FROM shop_items
    WHERE price >= ?
    ORDER BY price, item_id
    """;

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setBigDecimal(1, new BigDecimal("150000.00"));
    try (ResultSet rs = ps.executeQuery()) {
        while (rs.next()) {
            System.out.println(rs.getInt("item_id") + ": " +
                rs.getString("item_name"));
        }
    }
}
```

Đây là một đoạn minh họa vị trí tham số `?`; để biên dịch thành chương trình hoàn chỉnh cần import các lớp JDBC/`BigDecimal` và chuẩn bị `Connection`. Trong ứng dụng Java/Spring, có thể sử dụng JDBC, JdbcTemplate hoặc ORM tương ứng; các công cụ này cuối cùng vẫn cần diễn đạt điều kiện so sánh rõ ràng.

## 12. Lỗi thường gặp khi dùng toán tử so sánh

### Lỗi 1 — Nhầm `=` với `==` hoặc `<>` với `!=`

**SQL tiêu chuẩn dùng `=` và `<>`**. Một số DBMS hỗ trợ `!=`, nhưng không nên giả định `==` là toán tử bằng hợp lệ ở mọi hệ. Đừng chuyển cú pháp so sánh từ Java sang SQL một cách máy móc.

### Lỗi 2 — Bỏ sót giá trị biên

“Ít nhất 5” nghĩa là `>= 5`, không phải `> 5`. “Dưới 5” nghĩa là `< 5`, không phải `<= 5`. Hãy kiểm tra một hàng có giá trị **đúng bằng ngưỡng** để phát hiện sai khác.

### Lỗi 3 — Dùng `= NULL` hoặc nghĩ `<>` chọn luôn NULL

So sánh thông thường với `NULL` sinh `UNKNOWN`. Dùng `IS NULL`/`IS NOT NULL` và quyết định rõ có cần đưa hàng thiếu dữ liệu vào kết quả hay không.

### Lỗi 4 — Đem giá trị số hoặc ngày lưu dưới dạng chuỗi ra so sánh

Nếu `price` là `VARCHAR`, so sánh thứ tự có thể là thứ tự chuỗi thay vì số. Nếu `listed_on` là văn bản không thống nhất định dạng, điều kiện trước/sau ngày có thể sai. Nên thiết kế cột đúng kiểu; nếu buộc phải chuyển kiểu, kiểm tra và làm sạch dữ liệu trước.

### Lỗi 5 — So sánh số thực dấu phẩy động bằng dấu bằng tuyệt đối

Nhiều phép tính kiểu `FLOAT`/`DOUBLE` không biểu diễn chính xác mọi phân số thập phân. Khi cần giá trị chính xác như tiền, dùng `NUMERIC`/`DECIMAL`. Với dữ liệu đo lường, có thể cần tiêu chí **sai số cho phép**, chẳng hạn `ABS(x - target) < epsilon` nếu nghiệp vụ phù hợp.

### Lỗi 6 — Quên ngoặc khi trộn AND và OR

`a = 1 OR b = 2 AND c > 0` không giống `(a = 1 OR b = 2) AND c > 0`. Viết ngoặc khi cần ý nghĩa nhóm điều kiện rõ ràng.

### Lỗi 7 — Cho rằng WHERE có tác dụng sắp xếp

`WHERE price > 100000` chỉ lọc. Dùng `ORDER BY` nếu cần thứ tự hiển thị; thêm khóa phụ khi có các hàng bằng nhau.

### Lỗi 8 — Tin vào ép kiểu ngầm hoặc quy tắc collation mặc định

DBMS khác nhau có thể xử lý `'10' = 10` hoặc `'A' = 'a'` khác nhau. Nên dùng kiểu dữ liệu phù hợp và biết rõ collation nếu yêu cầu so sánh văn bản là quan trọng.

## 13. Bài tập tự thực hành

Hãy dự đoán kết quả trên bảng `shop_items` **trước khi chạy SQL**.

### Bài 1 — Bằng và khác

```sql
SELECT item_id FROM shop_items
WHERE price = 180000
ORDER BY item_id;

SELECT item_id FROM shop_items
WHERE category <> 'DEVICE'
ORDER BY item_id;
```

**Đáp án:** truy vấn đầu trả **2, 7**; truy vấn sau trả **1, 2, 5, 6, 7**.

### Bài 2 — Giá trị biên

```sql
SELECT item_id FROM shop_items
WHERE price > 120000 AND price <= 180000
ORDER BY item_id;
```

**Đáp án:** **2, 3, 7**. Sản phẩm 1 có giá đúng 120.000 nên không thỏa `> 120000`; giá 180.000 vẫn được tính do `<= 180000`.

### Bài 3 — Kết hợp tồn kho và danh mục

Yêu cầu: tìm sản phẩm thuộc **BOOK hoặc DEVICE**, **còn hàng**, giá **không quá 180.000**. Viết câu truy vấn rồi đối chiếu:

```sql
SELECT item_id, category, price, stock_qty
FROM shop_items
WHERE category IN ('BOOK', 'DEVICE')
  AND stock_qty > 0
  AND price <= 180000
ORDER BY item_id;
```

**Đáp án:** **1, 3, 7**. Sản phẩm 2 hết hàng; sản phẩm 4 có giá 350.000.

### Bài 4 — Ngày niêm yết

```sql
SELECT item_id FROM shop_items
WHERE listed_on >= DATE '2025-02-01'
  AND listed_on < DATE '2025-03-01'
ORDER BY item_id;
```

**Đáp án:** **3, 4, 5**. Ngày 1/2 được tính, ngày 1/3 không được tính.

### Bài 5 — Giá trị NULL

So sánh hai truy vấn:

```sql
-- A: chỉ điểm đã biết, khác 4.5
SELECT item_id FROM shop_items
WHERE rating <> 4.5
ORDER BY item_id;

-- B: khác 4.5 hoặc chưa có điểm
SELECT item_id FROM shop_items
WHERE rating <> 4.5 OR rating IS NULL
ORDER BY item_id;
```

**Đáp án:** A trả **2, 3, 5, 7**; B trả **2, 3, 4, 5, 6, 7**. Giải thích bằng logic ba giá trị: so sánh với `NULL` cho `UNKNOWN`, nên cần `IS NULL` nếu muốn bao gồm trường hợp thiếu dữ liệu.

### Bài 6 — So sánh và sắp xếp

Viết truy vấn lấy sản phẩm **giá từ 120.000 trở lên**, hiển thị theo **giá giảm dần**, nếu bằng giá thì theo **ID tăng dần**.

```sql
SELECT item_id, item_name, price
FROM shop_items
WHERE price >= 120000
ORDER BY price DESC, item_id ASC;
```

**Đáp án theo ID:** **4, 2, 7, 3, 1**. Nếu bỏ `ORDER BY`, vẫn có thể nhận đủ các hàng thỏa điều kiện nhưng **không được dựa vào thứ tự** của chúng.

## Kết luận

Nhóm toán tử so sánh **`=`, `<>`, `<`, `<=`, `>`, `>=`** là nền tảng để chuyển câu hỏi nghiệp vụ thành điều kiện SQL. `=` kiểm tra bằng, `<>` kiểm tra khác, còn bốn toán tử thứ tự xác định mối quan hệ lớn/nhỏ và việc có hay không bao gồm giá trị biên.

Để câu truy vấn đúng, hãy xác định **kiểu dữ liệu của các giá trị được so sánh**, xem xét **`NULL` và logic ba giá trị**, dùng ngoặc khi kết hợp `AND`/`OR`, và tách bạch **`WHERE` dùng để lọc** với **`ORDER BY` dùng để sắp xếp**. Các thói quen này giúp truy vấn dễ đọc, dự đoán được kết quả và tránh lỗi ở những trường hợp biên rất thường gặp trong hệ thống thực tế.
