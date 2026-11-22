# Kết hợp điều kiện với AND, OR, NOT và dấu ngoặc trong SQL

Khi truy vấn dữ liệu, một điều kiện đơn như `price < 1000000` thường chưa diễn tả đủ yêu cầu. Ví dụ: “Lấy **sản phẩm đang bán** và **còn hàng**, thuộc **nhóm sách hoặc điện tử**, nhưng **không phải hàng ngừng kinh doanh**.” Để chuyển những yêu cầu như vậy thành SQL chính xác, ta dùng các toán tử logic **`AND`**, **`OR`**, **`NOT`** và **dấu ngoặc đơn `(...)`**.

Điểm quan trọng nhất là **những điều kiện được kết hợp theo quy tắc ưu tiên**, và SQL còn có giá trị logic **`UNKNOWN`** khi biểu thức liên quan đến `NULL`. Vì thế, một câu `WHERE` không đặt ngoặc đúng có thể lọc sai hàng, kể cả khi từng điều kiện thành phần đều được viết đúng.

Bài học này tập trung vào cách đọc, viết, kiểm tra và kết hợp điều kiện trong SQL, thông qua một bảng dữ liệu có thể tạo và chạy lại. Các ví dụ chủ yếu dùng cú pháp phổ biến, với cột `BOOLEAN` theo PostgreSQL; kiểu boolean và một số phép tối ưu có thể khác theo hệ quản trị.

## 1. Điều kiện SQL là một biểu thức logic

Một *điều kiện* (predicate) là biểu thức trả về kết quả logic được dùng để quyết định hàng nào được giữ. Những điều kiện đơn thường gặp:

| Loại điều kiện | Ví dụ | Ý nghĩa |
|---|---|---|
| So sánh bằng | `category = 'books'` | Danh mục là sách |
| So sánh lớn hơn | `price > 500000` | Giá trên 500.000 |
| So sánh nhỏ hơn hoặc bằng | `stock <= 5` | Tồn kho tối đa 5 |
| Không bằng | `status <> 'CANCELLED'` | Trạng thái khác “đã hủy” |
| Kiểm tra tập giá trị | `category IN ('books', 'electronics')` | Thuộc một trong hai danh mục |
| Kiểm tra khoảng | `price BETWEEN 100000 AND 500000` | Giá trong khoảng, bao gồm hai đầu |
| Kiểm tra mẫu chuỗi | `name LIKE 'SQL%'` | Tên bắt đầu bằng SQL (tùy quy tắc so sánh DBMS) |
| Kiểm tra thiếu giá trị | `stock IS NULL` | Chưa biết số lượng tồn kho |

SQL dùng các kết quả logic **`TRUE`**, **`FALSE`** và **`UNKNOWN`**. Trong `WHERE`, chỉ các hàng có kết quả **`TRUE`** được chọn; hàng cho `FALSE` hoặc `UNKNOWN` đều bị loại. `UNKNOWN` thường phát sinh khi so sánh với `NULL`, chẳng hạn `stock > 0` nếu `stock` chưa được xác định.

Về mặt ngữ nghĩa, ta có thể ghép các điều kiện đơn để tạo điều kiện phức tạp:

```text
Điều kiện A: category = 'books'
Điều kiện B: price < 1000000
Điều kiện C: stock > 0

A AND B       → Là sách VÀ giá dưới 1 triệu
A OR B        → Là sách HOẶC giá dưới 1 triệu (có thể cả hai)
NOT A         → Không thuộc nhóm sách, nếu category đã xác định
(A OR B) AND C → (Là sách hoặc giá rẻ) VÀ còn hàng
```

Trong ngôn ngữ tự nhiên, từ “hoặc” đôi khi được hiểu là “chỉ một trong hai”. Nhưng **`OR` trong SQL là OR bao hàm**: nếu cả A và B đều đúng, kết quả vẫn là `TRUE`.

## 2. Dữ liệu mẫu để chạy các truy vấn

Tạo bảng sản phẩm nhỏ trong PostgreSQL. Trường `stock` và `active` có thể `NULL` để quan sát rõ logic ba giá trị.

```sql
CREATE TEMP TABLE demo_products (
    product_id INTEGER PRIMARY KEY,
    product_name VARCHAR(80) NOT NULL,
    category VARCHAR(30) NOT NULL,
    price NUMERIC(12, 2) NOT NULL,
    stock INTEGER,
    active BOOLEAN
);

INSERT INTO demo_products
    (product_id, product_name, category, price, stock, active)
VALUES
    (1, 'Laptop',        'electronics', 25000000,  5,    TRUE),
    (2, 'Mouse',         'electronics',   350000,  0,    TRUE),
    (3, 'SQL Book',      'books',         200000, 12,    TRUE),
    (4, 'Java Course',   'courses',      1200000,  0,    TRUE),
    (5, 'Headphones',    'electronics',   800000,  7,   FALSE),
    (6, 'Database Book', 'books',        1500000,  0,   FALSE),
    (7, 'USB Cable',     'accessories',   180000, 15,    TRUE),
    (8, 'Monitor',       'electronics',  4500000,  3,    TRUE),
    (9, 'Adapter',       'accessories',   250000, NULL,  NULL);
```

| ID | Sản phẩm | Danh mục | Giá | Tồn kho | Đang bán |
|---:|---|---|---:|---:|---|
| 1 | Laptop | electronics | 25.000.000 | 5 | TRUE |
| 2 | Mouse | electronics | 350.000 | 0 | TRUE |
| 3 | SQL Book | books | 200.000 | 12 | TRUE |
| 4 | Java Course | courses | 1.200.000 | 0 | TRUE |
| 5 | Headphones | electronics | 800.000 | 7 | FALSE |
| 6 | Database Book | books | 1.500.000 | 0 | FALSE |
| 7 | USB Cable | accessories | 180.000 | 15 | TRUE |
| 8 | Monitor | electronics | 4.500.000 | 3 | TRUE |
| 9 | Adapter | accessories | 250.000 | NULL | NULL |

Để kết quả dễ đọc và kiểm chứng, các truy vấn bên dưới thường kèm `ORDER BY product_id`. Nếu không có `ORDER BY`, SQL **không bảo đảm thứ tự trả về** dù dữ liệu được chèn theo thứ tự ID.

## 3. `AND`: đồng thời thỏa mãn các điều kiện

`A AND B` chỉ cho `TRUE` nếu **cả A và B đều là `TRUE`**. `AND` giúp thu hẹp kết quả theo nhiều yêu cầu bắt buộc.

Yêu cầu: “Lấy sản phẩm **đang bán và còn tồn kho**.”

```sql
SELECT product_id, product_name, stock
FROM demo_products
WHERE active = TRUE
  AND stock > 0
ORDER BY product_id;
```

**Kết quả:** ID **1, 3, 7, 8**.

- ID 1, 3, 7, 8: `active = TRUE` và `stock > 0` đều đúng.
- ID 2, 4: đang bán nhưng hết hàng (`stock = 0`).
- ID 5: còn hàng nhưng `active = FALSE`.
- ID 6: không đang bán và hết hàng.
- ID 9: `active` và `stock` đều là `NULL`; biểu thức không thành `TRUE` nên bị loại.

Có thể kết hợp nhiều hơn hai điều kiện:

```sql
-- Đang bán, còn hàng, thuộc điện tử, giá dưới 5 triệu.
SELECT product_id, product_name
FROM demo_products
WHERE active = TRUE
  AND stock > 0
  AND category = 'electronics'
  AND price < 5000000
ORDER BY product_id;
-- Chỉ có ID 8: Monitor.
```

`AND` có tính kết hợp về mặt logic: `(A AND B) AND C` tương đương `A AND (B AND C)` với các giá trị logic thông thường của SQL. Vì thế chuỗi toàn `AND` ít gây nhầm ưu tiên hơn việc trộn `AND` với `OR`.

Tuy nhiên, **đừng nhầm cú pháp điều kiện với thứ tự xử lý vật lý**. DBMS có thể tối ưu, đẩy, gộp hoặc sắp lại việc đánh giá biểu thức theo kế hoạch truy vấn; thứ tự viết các nhánh `AND` không bảo đảm được tính toán từ trên xuống dưới.

## 4. `OR`: thỏa mãn ít nhất một điều kiện

`A OR B` cho `TRUE` khi **ít nhất một trong A hoặc B là `TRUE`**. Nếu cả hai đúng, hàng vẫn được chọn **một lần** (một hàng nguồn không tự bị nhân đôi chỉ vì hai nhánh `OR` cùng đúng).

Yêu cầu: “Lấy **sách hoặc sản phẩm giá dưới 300.000**.”

```sql
SELECT product_id, product_name, category, price
FROM demo_products
WHERE category = 'books'
   OR price < 300000
ORDER BY product_id;
```

**Kết quả:** ID **3, 6, 7, 9**.

- ID 3: là sách **và** giá dưới 300.000.
- ID 6: là sách dù giá 1.500.000.
- ID 7, 9: không phải sách, nhưng giá dưới 300.000.
- ID 3 **không xuất hiện hai lần**, dù thỏa hai nhánh.

Một số điều kiện `OR` có thể rút gọn bằng `IN`:

```sql
-- Hai biểu thức dưới đây có cùng mục đích với category khác NULL.
WHERE category = 'books' OR category = 'electronics'

WHERE category IN ('books', 'electronics')
```

Trong một truy vấn hoàn chỉnh, chọn một dạng điều kiện cho mệnh đề `WHERE`; hai dòng trên chỉ minh họa cách viết tương đương, không phải ghép hai `WHERE` liên tiếp.

Với vài phép so sánh bằng trên **cùng một cột**, `IN` thường dễ đọc. Với các điều kiện khác nhau như “là sách **hoặc** giá rẻ”, `OR` vẫn là cách biểu diễn tự nhiên.

### `OR` có phải XOR?

Không. Nếu chỉ muốn “**đúng chính xác một trong hai điều kiện**”, phải biểu diễn thêm yêu cầu loại trừ tình huống cả hai đúng, ví dụ khi A và B là các điều kiện chắc chắn không `NULL`:

```sql
-- Chọn sản phẩm thuộc books hoặc giá dưới 300000, nhưng không đồng thời cả hai.
SELECT product_id, product_name
FROM demo_products
WHERE
      (category = 'books' AND price >= 300000)
   OR (category <> 'books' AND price < 300000)
ORDER BY product_id;
-- ID 6, 7, 9; ID 3 bị loại vì thỏa cả hai điều kiện.
```

Mẫu này sử dụng giả định `category` và `price` là `NOT NULL` trong bảng demo. Khi cột có thể `NULL`, cần xác định chính sách xử lý `UNKNOWN` trước khi xây phép loại trừ tương đương XOR.

## 5. `NOT`: phủ định một điều kiện

`NOT A` đảo `TRUE` thành `FALSE` và `FALSE` thành `TRUE`. Nếu A là `UNKNOWN`, `NOT A` **vẫn là `UNKNOWN`**.

Yêu cầu: “Lấy sản phẩm **không thuộc danh mục điện tử**.”

```sql
SELECT product_id, product_name, category
FROM demo_products
WHERE NOT (category = 'electronics')
ORDER BY product_id;
-- ID 3, 4, 6, 7, 9.
```

Trong bảng demo, `category NOT NULL`, nên có thể viết tương đương:

```sql
WHERE category <> 'electronics'
```

Việc dùng dấu ngoặc sau `NOT` giúp người đọc thấy **chính xác phần biểu thức nào bị phủ định**. Cách này đặc biệt quan trọng khi phủ định điều kiện ghép.

### 5.1. Phủ định một nhóm điều kiện

Yêu cầu: “Lấy sản phẩm **không đồng thời đang bán và còn hàng**.”

```sql
SELECT product_id, product_name, active, stock
FROM demo_products
WHERE NOT (active = TRUE AND stock > 0)
ORDER BY product_id;
-- ID 2, 4, 5, 6.
```

Không nên viết `NOT active = TRUE AND stock > 0` rồi tự cho rằng toàn bộ điều kiện bị đảo. `NOT` có mức ưu tiên riêng và phạm vi tác động phụ thuộc cách phân tích biểu thức. Viết `NOT (...)` là rõ ràng nhất.

Đặc biệt, ID 9 có `active IS NULL` và `stock IS NULL` nên `active = TRUE AND stock > 0` là `UNKNOWN`, phủ định vẫn `UNKNOWN`: **ID 9 không xuất hiện**. Phủ định không có nghĩa là lấy tất cả những hàng chưa được chọn bởi điều kiện gốc nếu có `NULL`.

### 5.2. `NOT` với toán tử chuyên biệt

SQL còn có các cách phủ định gần với ngôn ngữ tự nhiên:

```sql
-- Không thuộc hai danh mục được liệt kê.
SELECT product_id FROM demo_products
WHERE category NOT IN ('books', 'courses');

-- Tên không bắt đầu bằng chữ M, theo quy tắc LIKE của DBMS.
SELECT product_id FROM demo_products
WHERE product_name NOT LIKE 'M%';

-- Giá không nằm trong khoảng 300000 đến 1000000.
SELECT product_id FROM demo_products
WHERE price NOT BETWEEN 300000 AND 1000000;
```

Cần chú ý `NOT IN` nếu danh sách hoặc truy vấn con chứa `NULL`; phần logic ba giá trị phía dưới giải thích vì sao kết quả có thể bất ngờ. Không nên suy ra rằng mọi phép phủ định sẽ bao gồm các hàng có giá trị thiếu.

## 6. Dấu ngoặc và thứ tự ưu tiên: lý do phổ biến nhất gây lọc sai

Trong các biểu thức logic SQL thường dùng, thứ tự ưu tiên là:

| Mức ưu tiên (cao → thấp) | Toán tử | Ví dụ |
|---:|---|---|
| 1 | `NOT` | `NOT A` |
| 2 | `AND` | `A AND B` |
| 3 | `OR` | `A OR B` |

Các phép so sánh như `=`, `>`, `<` hoặc các predicate như `IN`, `LIKE` có quy tắc cú pháp riêng để tạo điều kiện A/B trước khi kết hợp logic. Các chi tiết về ưu tiên của toán tử đặc biệt có thể khác giữa DBMS; cách an toàn nhất khi trộn nhiều điều kiện là **dùng dấu ngoặc để biểu đạt ý định**.

Với các điều kiện A, B, C:

```sql
A OR B AND C
```

sẽ được hiểu là:

```sql
A OR (B AND C)
```

chứ **không phải**:

```sql
(A OR B) AND C
```

Hai biểu thức này có thể cho tập kết quả khác nhau.

### 6.1. Ví dụ thay đổi dấu ngoặc làm thay đổi kết quả

Yêu cầu: “Lấy hàng **thuộc sách hoặc điện tử**, và **giá dưới một triệu**.”

Cách viết đúng:

```sql
SELECT product_id, product_name, category, price
FROM demo_products
WHERE (category = 'books' OR category = 'electronics')
  AND price < 1000000
ORDER BY product_id;
-- ID 2 (Mouse), 3 (SQL Book), 5 (Headphones).
```

Nếu bỏ dấu ngoặc:

```sql
SELECT product_id, product_name, category, price
FROM demo_products
WHERE category = 'books'
   OR category = 'electronics' AND price < 1000000
ORDER BY product_id;
-- ID 2, 3, 5, 6.
```

Vì `AND` ưu tiên hơn `OR`, biểu thức không có ngoặc được hiểu là:

```sql
category = 'books'
OR (category = 'electronics' AND price < 1000000)
```

Do đó ID 6 (`Database Book`) được lấy dù giá 1.500.000: chỉ cần là sách đã đủ thỏa nhánh đầu. Trong khi đó, cách viết có ngoặc áp ngưỡng giá cho **cả sách lẫn điện tử**.

Đây là một lỗi nghiệp vụ điển hình: truy vấn **vẫn chạy thành công**, nhưng trả về tập dữ liệu sai.

### 6.2. Viết điều kiện theo từng nhóm nghiệp vụ

Yêu cầu phức tạp hơn:

> Lấy sản phẩm đang bán, còn hàng và thuộc nhóm sách **hoặc** điện tử, với giá không quá 5 triệu.

Có thể dịch rõ thành bốn điều kiện:

```text
A = active = TRUE
B = stock > 0
C = category = 'books' OR category = 'electronics'
D = price <= 5000000

Kết hợp: A AND B AND (C) AND D
```

SQL:

```sql
SELECT product_id, product_name, category, price, stock
FROM demo_products
WHERE active = TRUE
  AND stock > 0
  AND (category = 'books' OR category = 'electronics')
  AND price <= 5000000
ORDER BY product_id;
-- ID 3 (SQL Book) và 8 (Monitor).
```

ID 1 (`Laptop`) có hàng và đang bán nhưng giá quá 5 triệu; ID 5 (`Headphones`) có hàng, giá hợp lệ nhưng không còn đang bán; ID 7 thuộc nhóm phụ kiện nên bị loại.

Khi viết điều kiện dài, nên **nhóm từng mệnh đề theo ý nghĩa**: phạm vi đối tượng, trạng thái, điều kiện “một trong các lựa chọn”, điều kiện loại trừ và khoảng giá trị. Cách này làm câu lệnh dễ kiểm tra khi thay đổi yêu cầu.

### 6.3. Ngoặc lồng nhau

Có thể lồng nhiều tầng khi cần:

```sql
SELECT product_id, product_name
FROM demo_products
WHERE (active = TRUE AND stock > 0)
  AND (
         (category = 'books' AND price <= 500000)
      OR (category = 'electronics' AND price <= 5000000)
  )
ORDER BY product_id;
-- ID 3 và 8.
```

Nhánh thứ nhất áp ngưỡng 500.000 cho sách; nhánh thứ hai áp ngưỡng 5 triệu cho điện tử. Dấu ngoặc giúp tránh vô tình để `stock > 0` chỉ áp dụng cho một nhánh.

## 7. Bảng chân trị của `AND`, `OR` và `NOT`

Trong logic hai giá trị, biểu thức chỉ có `TRUE` và `FALSE`. SQL dùng **logic ba giá trị** khi một điều kiện không thể được xác định do `NULL`: `TRUE` (T), `FALSE` (F), `UNKNOWN` (U).

### 7.1. Hai toán tử kết hợp

| A | B | `A AND B` | `A OR B` |
|---|---|---|---|
| T | T | T | T |
| T | F | F | T |
| T | U | U | T |
| F | T | F | T |
| F | F | F | F |
| F | U | F | U |
| U | T | U | T |
| U | F | F | U |
| U | U | U | U |

Các trường hợp quan trọng:

- `FALSE AND UNKNOWN = FALSE`: đã có một điều kiện sai, toàn biểu thức `AND` không thể đúng.
- `TRUE OR UNKNOWN = TRUE`: đã có một điều kiện đúng, toàn biểu thức `OR` chắc chắn đúng.
- `TRUE AND UNKNOWN = UNKNOWN`: điều kiện còn lại chưa biết nên không kết luận được.
- `FALSE OR UNKNOWN = UNKNOWN`: điều kiện còn lại chưa biết nên không kết luận được.

### 7.2. Phủ định

| A | `NOT A` |
|---|---|
| T | F |
| F | T |
| U | U |

`NOT UNKNOWN` vẫn là `UNKNOWN`. Đây là lý do phép phủ định một câu `WHERE` không luôn tạo ra toàn bộ phần bù của tập hàng đã chọn.

### 7.3. SQL `NULL` và kết quả `UNKNOWN`

Ví dụ PostgreSQL:

```sql
SELECT
    (NULL::INTEGER > 0) AS comparison_result,
    (TRUE AND (NULL::INTEGER > 0)) AS and_result,
    (TRUE OR  (NULL::INTEGER > 0)) AS or_result,
    NOT (NULL::INTEGER > 0) AS not_result;
```

Phép `NULL > 0` có kết quả logic `UNKNOWN`, được PostgreSQL biểu diễn bằng `NULL` kiểu boolean trong kết quả truy vấn. Trong bốn cột trên, `comparison_result`, `and_result` và `not_result` đều là `NULL`; `or_result` là `TRUE`.

Nếu một biểu thức ở `SELECT` cho `UNKNOWN`, nó vẫn có thể xuất hiện dưới dạng ô `NULL`; nhưng khi cùng biểu thức được dùng trong `WHERE`, hàng không được giữ nếu kết quả không là `TRUE`.

## 8. Xử lý `NULL` rõ ràng khi kết hợp điều kiện

Bảng mẫu có ID 9 với `stock` và `active` đều `NULL`. Thử xem nó đi qua các biểu thức khác nhau như thế nào:

| Điều kiện `WHERE` | ID 9 có được chọn? | Vì sao |
|---|---|---|
| `stock > 0` | Không | `UNKNOWN` |
| `NOT (stock > 0)` | Không | `NOT UNKNOWN = UNKNOWN` |
| `stock IS NULL` | Có | `TRUE` |
| `stock > 0 OR stock IS NULL` | Có | `UNKNOWN OR TRUE = TRUE` |
| `active = TRUE` | Không | `UNKNOWN` |
| `NOT (active = TRUE)` | Không | `UNKNOWN` |
| `active IS NOT TRUE` | Có | `TRUE` vì giá trị không phải `TRUE`, bao gồm `NULL` |
| `active = TRUE OR active IS NULL` | Có | Có nhánh `TRUE` |

### 8.1. Muốn lấy cả dữ liệu chưa xác định thì nói rõ

Yêu cầu: “Lấy sản phẩm **còn hàng hoặc chưa ghi nhận tồn kho**.”

```sql
SELECT product_id, product_name, stock
FROM demo_products
WHERE stock > 0
   OR stock IS NULL
ORDER BY product_id;
-- ID 1, 3, 5, 7, 8, 9.
```

Nếu chỉ dùng `NOT (stock = 0)`, ID 9 sẽ không được chọn vì `NULL = 0` là `UNKNOWN`, và `NOT UNKNOWN` vẫn là `UNKNOWN`.

### 8.2. `IS TRUE`, `IS FALSE`, `IS UNKNOWN`

Một số DBMS như PostgreSQL hỗ trợ kiểu boolean và các phép kiểm tra truth value:

```sql
-- PostgreSQL: chỉ hàng có active thực sự TRUE.
SELECT product_id FROM demo_products
WHERE active IS TRUE;

-- PostgreSQL: bao gồm FALSE và NULL.
SELECT product_id FROM demo_products
WHERE active IS NOT TRUE
ORDER BY product_id;
-- ID 5, 6, 9.
```

So sánh với:

```sql
SELECT product_id FROM demo_products
WHERE NOT (active = TRUE)
ORDER BY product_id;
-- Chỉ ID 5, 6; ID 9 là UNKNOWN và bị loại.
```

Với dữ liệu trạng thái ba mức “đang bán/không bán/chưa rõ”, việc dùng `IS NOT TRUE` cần được quyết định **có chủ đích**. Không nên để một hàng chưa được xác nhận hoạt động tự động bị coi như hàng đã ngừng bán nếu điều đó ảnh hưởng đến quy trình nghiệp vụ.

### 8.3. `COALESCE` không chỉ là mẹo cú pháp

`COALESCE(stock, 0)` thay `NULL` bằng `0` khi tính biểu thức:

```sql
SELECT product_id
FROM demo_products
WHERE COALESCE(stock, 0) > 0;
```

Cách này tiện nếu nghiệp vụ **quy ước rõ** “không có thông tin tồn kho” được xem như bằng không để quyết định hiển thị. Nhưng `NULL` (“chưa biết”) và `0` (“đã biết là hết”) không có cùng ngữ nghĩa; ép giống nhau có thể che mất vấn đề dữ liệu. Đồng thời, áp dụng hàm lên cột có thể ảnh hưởng khả năng sử dụng chỉ mục thông thường; cần đo kế hoạch truy vấn nếu dữ liệu lớn.

### 8.4. Bẫy `NOT IN` với `NULL`

Xem câu lệnh sau:

```sql
-- Thường trả về 0 dòng trong ví dụ vì danh sách có NULL.
SELECT product_id, category
FROM demo_products
WHERE category NOT IN ('books', NULL);
```

Vì `x NOT IN ('books', NULL)` tương đương về logic với `x <> 'books' AND x <> NULL`, mọi giá trị khác `'books'` cho `TRUE AND UNKNOWN = UNKNOWN`, còn `'books'` cho `FALSE`. Trong `WHERE`, cả `FALSE` lẫn `UNKNOWN` đều không được chọn.

Nếu chỉ muốn loại sách, hãy dùng:

```sql
SELECT product_id, category
FROM demo_products
WHERE category <> 'books';
```

Với điều kiện phủ định kết quả từ truy vấn con, thường nên cân nhắc `NOT EXISTS` cùng điều kiện liên kết thích hợp, đặc biệt khi tập bên phải có thể chứa `NULL`. `NOT EXISTS` không tự bảo đảm đúng nghiệp vụ nếu điều kiện liên kết/giá trị thiếu chưa được xác định rõ.

## 9. Biến đổi logic với `AND`, `OR`, `NOT`

Biết các quy tắc tương đương giúp làm gọn điều kiện và tránh lỗi khi thêm nhánh mới.

### 9.1. Luật De Morgan

Với các biểu thức logic A và B, kể cả `UNKNOWN` theo logic SQL:

```text
NOT (A AND B)  ≡  (NOT A) OR  (NOT B)

NOT (A OR B)   ≡  (NOT A) AND (NOT B)
```

Ví dụ “không đồng thời đang bán và còn hàng”:

```sql
WHERE NOT (active = TRUE AND stock > 0)
```

có thể viết tương đương:

```sql
WHERE NOT (active = TRUE)
   OR NOT (stock > 0)
```

Hai biểu thức vẫn cho `UNKNOWN` trong trường hợp thích hợp: **luật De Morgan không tự biến logic ba giá trị thành logic hai giá trị**.

Ví dụ “không phải sách và cũng không phải điện tử”:

```sql
WHERE NOT (
    category = 'books' OR category = 'electronics'
)
```

tương đương với:

```sql
WHERE category <> 'books'
  AND category <> 'electronics'
```

Vì `category` trong bảng demo là `NOT NULL`, hai cách đều dễ hiểu. Nếu `category` có thể `NULL` thì cả hai cách mặc định loại hàng `NULL`; muốn bao gồm “chưa xác định danh mục” cần thêm nhánh `OR category IS NULL` với dấu ngoặc phù hợp.

### 9.2. Phân phối `AND` và `OR`

```text
A AND (B OR C)  ≡  (A AND B) OR (A AND C)

A OR (B AND C)  ≡  (A OR B) AND (A OR C)
```

Quy tắc thứ nhất rất hữu ích khi yêu cầu có một điều kiện chung:

```sql
WHERE active = TRUE
  AND (category = 'books' OR category = 'electronics')
```

có cùng ý nghĩa với:

```sql
WHERE (active = TRUE AND category = 'books')
   OR (active = TRUE AND category = 'electronics')
```

Nên ưu tiên dạng dễ đọc và phản ánh đúng nghiệp vụ; không có lý do phải phân phối biểu thức chỉ để làm nó dài hơn. Bộ tối ưu truy vấn có thể tự thực hiện nhiều phép biến đổi tương đương.

### 9.3. Rút gọn theo tập giá trị và điều kiện chung

Khi các nhánh `OR` đều so sánh bằng với **cùng một cột**, `IN` thường rõ hơn:

```sql
-- Thay vì viết ba nhánh OR:
WHERE category = 'books'
   OR category = 'electronics'
   OR category = 'accessories'

-- Có thể biểu diễn:
WHERE category IN ('books', 'electronics', 'accessories')
```

Với các điều kiện lặp:

```sql
WHERE (active = TRUE AND price < 500000)
   OR (active = TRUE AND stock > 10)
```

có thể nhóm thành:

```sql
WHERE active = TRUE
  AND (price < 500000 OR stock > 10)
```

Điều kiện chung đặt ngoài ngoặc giúp bảo đảm cả hai lựa chọn đều chịu quy tắc `active = TRUE`. Với `NULL`, các phép tương đương này vẫn theo ngữ nghĩa logic SQL; tuy nhiên phải cẩn thận nếu biểu thức chứa hàm có tác dụng phụ hoặc có thể gây lỗi do ép kiểu.

## 10. Không dựa vào “short-circuit” để bảo vệ biểu thức có thể lỗi

Trong một số ngôn ngữ lập trình, `A AND B` có thể ngừng tính B khi A đã sai, hoặc `A OR B` ngừng tính B khi A đã đúng. Trong SQL, **không nên dựa vào thứ tự đánh giá từng điều kiện**: bộ tối ưu có quyền sắp xếp lại hoặc chuyển đổi biểu thức tùy kế hoạch.

Ví dụ cột văn bản `raw_amount` có giá trị `'ABC'`; truy vấn sau trông như kiểm tra chuỗi số trước khi ép kiểu:

```sql
-- Không nên mặc định điều kiện thứ nhất sẽ bảo vệ điều kiện ép kiểu:
SELECT *
FROM imported_rows
WHERE raw_amount ~ '^[0-9]+$'
  AND raw_amount::INTEGER > 100;
```

Trong PostgreSQL, phép ép kiểu `'ABC'::INTEGER` có thể gây lỗi nếu biểu thức được đánh giá trên dữ liệu không hợp lệ. Không nên lấy thứ tự hai điều kiện `AND` làm bảo đảm an toàn. Với dữ liệu nhập không đáng tin cậy, dùng kiểu dữ liệu đúng ngay từ đầu hoặc một chiến lược chuyển đổi an toàn được DBMS hỗ trợ (ví dụ `CASE`/hàm xử lý lỗi phù hợp), rồi lọc trên giá trị đã được chuẩn hóa.

Tương tự, thứ tự hai nhánh `OR` **không phải** cam kết rằng nhánh thứ hai sẽ không thực thi nếu nhánh đầu đúng. Câu SQL diễn đạt kết quả logic; cách thực thi là trách nhiệm của bộ tối ưu trong phạm vi ngữ nghĩa được DBMS bảo đảm.

## 11. Kết hợp điều kiện trong `WHERE`, `HAVING` và `JOIN ON`

Cùng các toán tử `AND`, `OR`, `NOT` có thể xuất hiện trong nhiều phần của truy vấn, nhưng **đối tượng được lọc khác nhau**.

### 11.1. `WHERE` lọc từng hàng

```sql
SELECT product_id, product_name
FROM demo_products
WHERE (category = 'books' OR category = 'electronics')
  AND active = TRUE
ORDER BY product_id;
-- ID 1, 2, 3, 8.
```

`WHERE` loại các hàng không thỏa điều kiện **trước** khi kết quả được gom nhóm ở trường hợp có tổng hợp.

### 11.2. `HAVING` lọc nhóm sau khi tổng hợp

Yêu cầu: “Lấy các danh mục có ít nhất hai sản phẩm, đồng thời có ít nhất một sản phẩm tồn kho lớn hơn 0.”

```sql
SELECT
    category,
    COUNT(*) AS product_count,
    SUM(CASE WHEN stock > 0 THEN 1 ELSE 0 END) AS in_stock_count
FROM demo_products
GROUP BY category
HAVING COUNT(*) >= 2
   AND SUM(CASE WHEN stock > 0 THEN 1 ELSE 0 END) >= 1
ORDER BY category;
```

Kết quả có `accessories`, `books` và `electronics`; `courses` chỉ có một sản phẩm nên không đạt điều kiện `COUNT(*) >= 2`. `CASE WHEN stock > 0` trong biểu thức tổng hợp chỉ tính 1 khi điều kiện là `TRUE`; hàng có `stock NULL` đi vào nhánh `ELSE 0`.

Việc viết `HAVING COUNT(*) >= 2 OR ...` sẽ thay đổi ý nghĩa, vì chỉ cần thỏa một trong hai tiêu chí.

### 11.3. `JOIN ON` xác định điều kiện khớp bảng

Ví dụ một bảng `product_promotions` có `product_id`, `valid_from` và `active`. Khi muốn ghép khuyến mãi **đang hiệu lực** với sản phẩm, có thể kết hợp các điều kiện ngay trong `ON`:

```sql
-- Minh họa: giả sử product_promotions đã tồn tại.
SELECT p.product_id, p.product_name, promo.promotion_id
FROM demo_products AS p
LEFT JOIN product_promotions AS promo
  ON promo.product_id = p.product_id
 AND promo.active = TRUE
 AND promo.valid_from <= CURRENT_DATE;
```

Với `LEFT JOIN`, các sản phẩm không có khuyến mãi phù hợp vẫn có thể hiện diện, còn cột bên bảng khuyến mãi là `NULL`. Nếu chuyển `promo.active = TRUE` sang `WHERE`, các hàng không khớp có thể bị loại, làm kết quả khác đi. Cần hiểu **lọc cặp hàng trong `ON`** và **lọc kết quả trong `WHERE`** khi dùng outer join; toán tử logic giống nhau nhưng vị trí áp dụng không giống nhau.

## 12. Trường hợp ứng dụng: quyền truy cập và điều kiện tìm kiếm

### 12.1. Bộ lọc quyền truy cập cần ngoặc chính xác

Giả sử hệ thống chỉ cho xem những tài liệu **thuộc tenant hiện tại**, đồng thời tài liệu phải **công khai hoặc do người dùng tạo**.

Cách viết đúng:

```sql
-- Dùng tham số :tenant_id và :user_id do ứng dụng bind.
SELECT document_id, title
FROM documents
WHERE tenant_id = :tenant_id
  AND (
       visibility = 'PUBLIC'
       OR created_by = :user_id
  );
```

Bỏ ngoặc:

```sql
WHERE tenant_id = :tenant_id
  AND visibility = 'PUBLIC'
   OR created_by = :user_id
```

sẽ được hiểu là:

```sql
(tenant_id = :tenant_id AND visibility = 'PUBLIC')
OR created_by = :user_id
```

Nhánh `created_by = :user_id` lúc này **không còn bị giới hạn bởi tenant** trong biểu thức. Nếu ID người dùng không được ràng buộc với tenant theo một cơ chế khác, truy vấn có thể trả dữ liệu ngoài phạm vi mong muốn. Đây là lý do các điều kiện về phạm vi truy cập nên được nhóm rõ ràng và được áp cho **mọi nhánh** của biểu thức `OR`.

Chỉ có truy vấn đúng ngoặc chưa đủ thay thế phân quyền đầy đủ; ứng dụng vẫn phải ràng buộc các tham số với danh tính và quyền của người yêu cầu.

### 12.2. Bộ lọc tìm kiếm tùy chọn

Giả sử người dùng có thể chọn một trong hai nhóm sản phẩm, chỉ lấy mặt hàng đang bán và lọc theo giá tối đa:

```sql
SELECT product_id, product_name, category, price
FROM demo_products
WHERE active = TRUE
  AND category IN ('books', 'electronics')
  AND price <= 2000000
ORDER BY product_id;
-- ID 2, 3.
```

Khi xây câu SQL động, phải bảo đảm mỗi nhóm điều kiện `OR` được đặt trong ngoặc trước khi nối với bộ lọc bắt buộc bằng `AND`. Giá trị người dùng nhập phải truyền qua tham số truy vấn (*parameter binding*) phù hợp, không nối trực tiếp chuỗi SQL thô, để tránh lỗi cú pháp và nguy cơ SQL injection.

### 12.3. Phủ định một ngoại lệ mà không thay đổi quy tắc chính

Yêu cầu: “Sản phẩm đang bán, còn hàng, **trừ khi** thuộc nhóm phụ kiện hoặc có giá trên 5 triệu.”

Nếu ý nghĩa là loại cả hai trường hợp ngoại lệ, biểu thức là:

```sql
SELECT product_id, product_name
FROM demo_products
WHERE active = TRUE
  AND stock > 0
  AND NOT (
       category = 'accessories'
       OR price > 5000000
  )
ORDER BY product_id;
-- ID 3 và 8.
```

Bằng luật De Morgan, biểu thức loại trừ có thể viết:

```sql
AND category <> 'accessories'
AND price <= 5000000
```

Tuy nhiên, dùng `NOT (...)` thường bám sát yêu cầu “không thuộc một trong những ngoại lệ” hơn, đặc biệt khi nhóm ngoại lệ còn có nhiều tiêu chí.

## 13. Hiệu năng: biểu thức đúng trước, tối ưu sau

Thêm `AND`/`OR`/`NOT` không tự làm truy vấn nhanh hoặc chậm theo một công thức cố định. DBMS lựa chọn kế hoạch truy vấn dựa trên chỉ mục, thống kê, độ chọn lọc, kích thước bảng và các phép kết nối.

Một số nguyên tắc:

1. **Điều kiện có tính chọn lọc cao** có thể giúp giảm số hàng, nhưng thứ tự viết `AND` không phải thứ tự thực thi bảo đảm. Đừng đảo dòng chỉ vì nghĩ SQL đọc từ trên xuống.
2. **`OR` qua nhiều cột** đôi khi khiến DBMS dùng nhiều chỉ mục kết hợp, quét bảng hoặc chuyển kế hoạch khác. Tùy hệ, có thể cân nhắc `UNION`/`UNION ALL` cho những trường hợp thích hợp, nhưng phải xử lý đúng trùng hàng và kết quả tập hợp trước khi thay đổi.
3. **`NOT` và `<>`** có thể cho tập kết quả lớn; hiệu quả chỉ mục phụ thuộc phân bố dữ liệu và chiến lược tối ưu. Không có quy tắc rằng `NOT` luôn làm mất khả năng dùng chỉ mục.
4. **Hàm trên cột** như `LOWER(name)` hay `COALESCE(stock, 0)` có thể cần chỉ mục biểu thức hoặc cơ chế riêng nếu truy vấn thường xuyên dùng hàm đó.
5. **Dấu ngoặc** trước hết bảo vệ ngữ nghĩa. Một bộ tối ưu tốt có thể nhận ra các biểu thức tương đương; đặt ngoặc không tự làm truy vấn “nặng” một cách có ý nghĩa.

Ví dụ PostgreSQL:

```sql
EXPLAIN
SELECT product_id, product_name
FROM demo_products
WHERE active = TRUE
  AND (category = 'books' OR category = 'electronics')
  AND price < 1000000;
```

`EXPLAIN` hiển thị kế hoạch dự kiến. Trong bảng demo chỉ 9 hàng, quét bảng có thể là lựa chọn hoàn toàn hợp lý. Không dùng kết quả bảng thử cực nhỏ để kết luận rằng một chỉ mục hoặc cách viết điều kiện tối ưu cho hàng triệu bản ghi.

## 14. Phương pháp dịch yêu cầu tiếng Việt thành điều kiện SQL

Có thể thực hiện theo trình tự:

1. **Chia yêu cầu thành các mệnh đề đơn**: ví dụ “đang bán” → `active = TRUE`; “còn hàng” → `stock > 0`; “sách” → `category = 'books'`.
2. **Xác định nhóm “đồng thời”** để nối bằng `AND`.
3. **Xác định nhóm “ít nhất một”** để nối bằng `OR`.
4. **Xác định phần bị loại trừ** và đặt nguyên phần đó vào `NOT (...)`, hoặc dùng phép so sánh phủ định thích hợp.
5. **Đặt ngoặc bao quanh các nhóm `OR`** khi còn có các điều kiện `AND` bên ngoài.
6. **Xác định cách xử lý `NULL`**: thiếu dữ liệu bị loại, được chấp nhận hay cần được hiển thị riêng?
7. **Dùng dữ liệu biên để tự suy luận kết quả**, đặc biệt các hàng chỉ đúng một nhánh, đúng cả hai nhánh, có `NULL` và ở sát ngưỡng giá trị.

Ví dụ yêu cầu:

> Chọn sản phẩm còn hoạt động, thuộc nhóm điện tử **hoặc** sách, có giá dưới 2 triệu, nhưng loại các sản phẩm hết hàng **trừ khi** tồn kho chưa được ghi nhận.

Phân tích:

```text
A = active = TRUE
B = category = 'electronics' OR category = 'books'
C = price < 2000000
D = stock > 0 OR stock IS NULL

Điều kiện tổng: A AND (B) AND C AND (D)
```

SQL:

```sql
SELECT product_id, product_name
FROM demo_products
WHERE active = TRUE
  AND (category = 'electronics' OR category = 'books')
  AND price < 2000000
  AND (stock > 0 OR stock IS NULL)
ORDER BY product_id;
-- ID 3 (SQL Book).
```

ID 2 là điện tử đang bán, giá đủ thấp nhưng `stock = 0` nên bị loại. ID 6 là sách giá dưới 2 triệu nhưng `active = FALSE` nên bị loại. Trong dữ liệu mẫu, ID 9 có `stock IS NULL` nhưng không thuộc hai danh mục và cũng chưa biết `active`, nên không được chọn.

## 15. Sai lầm thường gặp

| Sai lầm | Hậu quả | Cách sửa |
|---|---|---|
| `A OR B AND C` khi muốn `(A OR B) AND C` | Điều kiện C chỉ áp lên nhánh B | Đặt ngoặc theo nhóm nghiệp vụ |
| `NOT A AND B` khi muốn `NOT (A AND B)` | Phủ định sai phạm vi, tập kết quả khác | Đặt `NOT (...)` quanh cả nhóm |
| Tưởng `OR` chỉ cho đúng một nhánh | Loại sai hàng thỏa cả A và B | Hiểu `OR` bao hàm; viết XOR riêng khi cần |
| Dùng `= NULL` hoặc `<> NULL` | Biểu thức thường cho `UNKNOWN` | `IS NULL` hoặc `IS NOT NULL` |
| Dùng `NOT (stock > 0)` để chọn cả tồn kho thiếu | `NULL` vẫn bị loại | Thêm `OR stock IS NULL` nếu nghiệp vụ muốn |
| Dùng `NOT IN` với tập chứa `NULL` | Có thể không trả những dòng tưởng là “không thuộc” | Kiểm soát `NULL` hoặc dùng `NOT EXISTS` phù hợp |
| Dựa vào thứ tự đánh giá `AND` để tránh ép kiểu lỗi | DBMS có thể sắp lại biểu thức | Chuẩn hóa/chuyển kiểu an toàn riêng |
| Viết `OR` quyền truy cập ngoài ngoặc phạm vi tenant | Một nhánh không bị ràng buộc bởi điều kiện phạm vi | Đặt điều kiện phạm vi ngoài nhóm `(...)` |
| Nhầm điều kiện `ON` của `LEFT JOIN` với `WHERE` | Vô tình loại hàng không khớp bên phải | Xem rõ mục tiêu ghép hay lọc hàng cuối |
| Dùng `COALESCE` tùy tiện để biến `NULL` thành 0 | Che mất ý nghĩa “chưa biết” | Quy định rõ ngữ nghĩa dữ liệu thiếu |
| Không dùng `ORDER BY` nhưng trông đợi thứ tự cố định | Kết quả có thể đổi thứ tự giữa các lần chạy | Thêm `ORDER BY` và khóa phụ khi cần |

## 16. Bài tập tự luyện

### Bài 1. Kiểm tra thứ tự ưu tiên

Với bảng mẫu, truy vấn sau chọn những sản phẩm nào?

```sql
SELECT product_id
FROM demo_products
WHERE category = 'books'
   OR category = 'electronics' AND price < 1000000
ORDER BY product_id;
```

**Đáp án:** ID **2, 3, 5, 6**. Vì `AND` ưu tiên hơn `OR`, mọi sách đều được chọn (ID 3, 6), còn điện tử chỉ được chọn nếu giá dưới một triệu (ID 2, 5). Nếu muốn giới hạn giá cho cả hai danh mục, phải dùng `(category = 'books' OR category = 'electronics') AND price < 1000000`, khi đó còn ID **2, 3, 5**.

### Bài 2. Phủ định và `NULL`

```sql
SELECT product_id
FROM demo_products
WHERE NOT (stock > 0)
ORDER BY product_id;
```

**Đáp án:** ID **2, 4, 6**, vì các hàng đó có `stock = 0` nên `stock > 0` là `FALSE` và phủ định thành `TRUE`. ID 9 có `stock NULL` nên `NOT (stock > 0)` vẫn là `UNKNOWN` và bị loại. Muốn thêm ID 9, dùng `stock <= 0 OR stock IS NULL`.

### Bài 3. Dùng `AND`/`OR` có ngoặc

Yêu cầu: “Đang bán, còn hàng, và thuộc sách hoặc phụ kiện.”

**Đáp án:**

```sql
SELECT product_id, product_name
FROM demo_products
WHERE active = TRUE
  AND stock > 0
  AND (category = 'books' OR category = 'accessories')
ORDER BY product_id;
-- ID 3 (SQL Book) và 7 (USB Cable).
```

### Bài 4. Dùng luật De Morgan

Viết lại `NOT (category = 'books' OR price > 1000000)` mà không dùng `NOT` bên ngoài nhóm.

**Đáp án** trong trường hợp `category` và `price` đều `NOT NULL`:

```sql
category <> 'books'
AND price <= 1000000
```

Ngữ nghĩa tương đương khi các biểu thức có `UNKNOWN` theo logic SQL, nhưng nếu mục tiêu muốn nhận các dòng chứa giá trị `NULL`, cần thêm chính sách xử lý riêng bằng `IS NULL`.

### Bài 5. Bắt lỗi điều kiện phạm vi

```sql
WHERE tenant_id = :tenant_id
  AND status = 'PUBLIC'
   OR owner_id = :user_id
```

**Hỏi:** vì sao câu này có thể sai và sửa như thế nào?

**Đáp án:** `OR owner_id = :user_id` nằm ngoài điều kiện tenant theo thứ tự ưu tiên. Nếu cả hai lựa chọn phải thuộc tenant hiện tại, viết:

```sql
WHERE tenant_id = :tenant_id
  AND (status = 'PUBLIC' OR owner_id = :user_id)
```

Phân quyền trong ứng dụng còn phải kiểm tra tham số tenant/user thực sự được phép sử dụng; dấu ngoặc chỉ bảo đảm biểu thức SQL diễn đạt đúng phạm vi mong muốn.

## Kết luận

`AND` nối các yêu cầu **đồng thời**, `OR` nối các lựa chọn mà **ít nhất một** cần đúng, `NOT` phủ định một điều kiện hoặc nhóm điều kiện. Khi trộn toán tử, **`NOT` ưu tiên hơn `AND`, và `AND` ưu tiên hơn `OR`**, vì vậy dấu ngoặc là công cụ thiết yếu để câu SQL diễn đạt đúng nghiệp vụ.

Điều kiện SQL hoạt động theo **logic ba giá trị**: `NULL` có thể dẫn đến `UNKNOWN`, và `WHERE` chỉ giữ các hàng có điều kiện `TRUE`. Để viết bộ lọc đáng tin cậy, hãy nhóm biểu thức theo ý nghĩa, xác định cách xử lý dữ liệu thiếu, kiểm tra các trường hợp biên và không dựa vào thứ tự thực thi ngầm của các nhánh logic. Những thói quen này giúp truy vấn dễ đọc, dễ bảo trì và tránh lỗi kết quả âm thầm trong ứng dụng thực tế.

