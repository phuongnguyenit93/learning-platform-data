# FROM, bảng nguồn và phạm vi tên cột

Trong PostgreSQL, câu truy vấn `SELECT` không chỉ xác định **cột nào được trả về** mà còn phải xác định **dữ liệu đến từ đâu**. Mệnh đề **`FROM`** khai báo các nguồn dữ liệu mà truy vấn có thể sử dụng: bảng, view, kết quả truy vấn con, common table expression (CTE), danh sách giá trị, hàm trả tập hàng hoặc một tổ hợp `JOIN` của nhiều nguồn.

Khi truy vấn có một bảng, việc viết `SELECT customer_id FROM customers` có vẻ đơn giản. Nhưng khi có nhiều nguồn đều chứa cột `customer_id`, PostgreSQL phải biết bạn muốn cột của bảng nào. Khi nguồn được đặt bí danh `AS c`, tên bảng gốc có còn dùng để gọi cột được không? Khi có truy vấn con, alias của bảng ngoài có được nhìn thấy trong truy vấn bên trong không? Và vì sao alias `total` trong `SELECT` dùng được ở `ORDER BY` nhưng không dùng trực tiếp ở `WHERE`?

Những câu hỏi đó đều liên quan tới **phạm vi tên** (*name scope*) và **cách phân giải tên cột** (*column name resolution*). Hiểu rõ phạm vi này giúp viết SQL không nhập nhằng, tránh lỗi `column reference is ambiguous`, không vô tình nhân số dòng khi kết hợp bảng và không dựa vào những tên cột chỉ xuất hiện ở tầng kết quả.

Bài học này tập trung vào PostgreSQL, với các mục tiêu:

- Hiểu ý nghĩa của `FROM`, nguồn quan hệ và cách SQL hình thành tập hàng trung gian.
- Nhận diện **qualified column** như `o.order_id` và **unqualified column** như `order_id`.
- Dùng alias bảng, alias cột, tên schema và quy tắc `search_path` đúng cách.
- Phân biệt phạm vi tên trong `SELECT`, `WHERE`, `JOIN ON`, `GROUP BY`, `ORDER BY` và truy vấn con.
- Đọc nguồn từ bảng, view, `JOIN`, `VALUES`, subquery, CTE, `generate_series()` và `LATERAL`.
- Chẩn đoán lỗi tên bảng/cột, tránh `NATURAL JOIN` hoặc `SELECT *` gây bất ngờ và thiết kế truy vấn dễ bảo trì.

> **Phạm vi thực hành:** Các ví dụ tạo schema và chèn dữ liệu dưới đây dành cho database thử nghiệm, sử dụng PostgreSQL hiện đại. Không chạy phần tạo bảng trên database đang có đối tượng cùng tên hoặc dữ liệu cần giữ. Các truy vấn dùng tên schema `lesson_from` để phân biệt rõ nguồn và giảm phụ thuộc cấu hình phiên.

## 1. Cấu trúc một câu SELECT

Một câu truy vấn thông dụng:

```sql
SELECT c.customer_id, c.full_name
FROM lesson_from.customers AS c
WHERE c.city = 'Hà Nội'
ORDER BY c.full_name;
```

Các mệnh đề có nhiệm vụ riêng:

| Phần | Vai trò |
|---|---|
| `SELECT` | Xác định biểu thức hoặc cột cần đưa ra kết quả. |
| `FROM` | Cung cấp bảng nguồn và **phạm vi tên** để các mệnh đề truy vấn tham chiếu. |
| `JOIN ... ON/USING` | Xây dựng nguồn kết hợp và xác định quan hệ giữa các hàng. |
| `WHERE` | Lọc những hàng không thỏa điều kiện trước giai đoạn nhóm. |
| `GROUP BY` | Gom các hàng theo khóa nhóm khi truy vấn có tổng hợp. |
| `HAVING` | Lọc các nhóm sau khi tổng hợp. |
| `ORDER BY` | Sắp thứ tự hàng kết quả, có thể dùng alias ở danh sách `SELECT`. |
| `LIMIT/OFFSET` | Giới hạn/phân trang kết quả theo quy tắc tương ứng. |

Đây là **thứ tự trình bày cú pháp**, không hoàn toàn là thứ tự tư duy để hiểu dữ liệu. Một mô hình **xử lý logic** hữu ích:

```text
FROM (nguồn và JOIN)
        │
        ▼
WHERE (lọc hàng)
        │
        ▼
GROUP BY / tính nhóm
        │
        ▼
HAVING (lọc nhóm)
        │
        ▼
SELECT (tính cột đầu ra)
        │
        ▼
ORDER BY
        │
        ▼
LIMIT / OFFSET
```

Mô hình này giúp giải thích vì sao `WHERE` không tham chiếu được alias cột mới khai báo ở `SELECT`. **PostgreSQL optimizer không bắt buộc thực thi vật lý theo từng bước giống sơ đồ**: nó có thể đẩy điều kiện lọc, sắp xếp lại join và sử dụng chỉ mục miễn giữ đúng ngữ nghĩa truy vấn.

### SELECT có thể không cần FROM

Trong PostgreSQL:

```sql
SELECT 1 + 2 AS result;

SELECT current_date AS today;

SELECT current_user AS connected_role;
```

Các câu lệnh này hợp lệ dù không có `FROM`. Chúng tính biểu thức trong một ngữ cảnh không cần hàng từ một bảng nguồn, thông thường trả về một dòng. Không nên suy ra rằng **mọi `SELECT` đều bắt buộc phải đọc một bảng**.

## 2. Chuẩn bị dữ liệu ví dụ

Ta sử dụng một schema riêng và bốn bảng liên quan đến hệ thống bán hàng: **khách hàng, đơn hàng, sản phẩm, dòng sản phẩm trong đơn**.

Sơ đồ quan hệ:

```text
lesson_from.customers
  customer_id (PK)
  full_name
  city
       │
       │ 1 - nhiều
       ▼
lesson_from.orders
  order_id (PK)
  customer_id (FK)
  status
  ordered_at
       │
       │ 1 - nhiều
       ▼
lesson_from.order_items
  order_id (FK)
  product_id (FK)
  quantity
       ▲
       │ nhiều - 1
       │
lesson_from.products
  product_id (PK)
  product_name
  unit_price
```

### 2.1. Tạo schema và các bảng

```sql
CREATE SCHEMA IF NOT EXISTS lesson_from;

CREATE TABLE lesson_from.customers (
    customer_id BIGINT PRIMARY KEY,
    full_name TEXT NOT NULL,
    city TEXT NOT NULL
);

CREATE TABLE lesson_from.products (
    product_id BIGINT PRIMARY KEY,
    product_name TEXT NOT NULL,
    unit_price NUMERIC(12, 2) NOT NULL CHECK (unit_price >= 0)
);

CREATE TABLE lesson_from.orders (
    order_id BIGINT PRIMARY KEY,
    customer_id BIGINT NOT NULL
        REFERENCES lesson_from.customers(customer_id),
    status TEXT NOT NULL
        CHECK (status IN ('PENDING', 'PAID', 'CANCELLED')),
    ordered_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE lesson_from.order_items (
    order_id BIGINT NOT NULL
        REFERENCES lesson_from.orders(order_id),
    product_id BIGINT NOT NULL
        REFERENCES lesson_from.products(product_id),
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    PRIMARY KEY (order_id, product_id)
);
```

Các lệnh `CREATE TABLE` trên giả định những bảng đó chưa tồn tại. Đặt khóa ngoại để việc `JOIN` có ý nghĩa từ dữ liệu thật và để tránh vô tình tạo dòng sản phẩm của đơn không tồn tại.

### 2.2. Chèn dữ liệu mẫu

```sql
INSERT INTO lesson_from.customers(customer_id, full_name, city)
VALUES
    (1, 'An', 'Hà Nội'),
    (2, 'Bình', 'Đà Nẵng'),
    (3, 'Chi', 'TP. Hồ Chí Minh');

INSERT INTO lesson_from.products(product_id, product_name, unit_price)
VALUES
    (101, 'Bàn phím', 350000),
    (102, 'Chuột', 120000),
    (103, 'Tai nghe', 750000);

INSERT INTO lesson_from.orders(
    order_id, customer_id, status, ordered_at
)
VALUES
    (1001, 1, 'PAID',      TIMESTAMPTZ '2026-11-10 09:00:00+07'),
    (1002, 1, 'PENDING',   TIMESTAMPTZ '2026-11-11 14:00:00+07'),
    (1003, 2, 'PAID',      TIMESTAMPTZ '2026-11-12 10:00:00+07');

INSERT INTO lesson_from.order_items(order_id, product_id, quantity)
VALUES
    (1001, 101, 2),
    (1001, 102, 1),
    (1003, 102, 3);
```

Những dữ liệu này cho thấy:

- Khách hàng **An** có hai đơn, một đã thanh toán và một đang chờ.
- Khách hàng **Bình** có một đơn đã thanh toán.
- Khách hàng **Chi** chưa có đơn.
- Đơn **1001** có hai dòng sản phẩm; đơn **1002** chưa có dòng sản phẩm trong ví dụ.

Các tình huống có **không, một, hoặc nhiều hàng liên quan** rất quan trọng để hiểu `JOIN`, phạm vi tên và số lượng hàng kết quả.

## 3. FROM một bảng: nguồn cơ bản nhất

```sql
SELECT customer_id, full_name, city
FROM lesson_from.customers;
```

`FROM lesson_from.customers` đưa hàng của bảng `customers` vào ngữ cảnh truy vấn. Các cột `customer_id`, `full_name` và `city` trở thành tên có thể tham chiếu trong các biểu thức của truy vấn đó.

Muốn chỉ lấy khách hàng Hà Nội:

```sql
SELECT full_name
FROM lesson_from.customers
WHERE city = 'Hà Nội';
```

Ở ví dụ này, `city` và `full_name` không ghi tên bảng vì nguồn chỉ có một bảng, không có cột cùng tên từ nguồn khác gây nhập nhằng.

### Có cần SELECT mọi cột đã dùng trong WHERE không?

Không:

```sql
SELECT full_name
FROM lesson_from.customers
WHERE city = 'Đà Nẵng';
```

`city` có trong nguồn `FROM`, nên có thể dùng ở `WHERE` dù không nằm trong danh sách `SELECT`. Ngược lại, câu `SELECT` chỉ quyết định cột đầu ra, không giới hạn mọi cột có thể dùng để lọc.

### FROM không quyết định thứ tự hàng

```sql
SELECT customer_id, full_name
FROM lesson_from.customers;
```

Không có `ORDER BY` thì **thứ tự hàng không được bảo đảm**, ngay cả khi các lần chạy thử thường trả theo `customer_id` hoặc vị trí lưu trữ. Muốn kết quả ổn định:

```sql
SELECT customer_id, full_name
FROM lesson_from.customers
ORDER BY customer_id;
```

Đây là quy tắc quan trọng khi phân trang hoặc so sánh kết quả giữa các lần thực thi.

## 4. Tên cột không đầy đủ và tên cột có tiền tố

Một cột có thể được gọi bằng:

| Dạng | Ví dụ | Khi nào phù hợp |
|---|---|---|
| **Không tiền tố** (*unqualified*) | `customer_id` | Chỉ khi tên cột xác định được duy nhất trong phạm vi truy vấn. |
| **Tên nguồn hoặc alias + cột** | `c.customer_id` | Rõ ràng khi có nhiều nguồn hoặc cần tăng độ dễ đọc. |
| **Schema + bảng + cột** | `lesson_from.customers.customer_id` | Có thể được phân giải trong một số ngữ cảnh khi bảng không có alias; thường dài và không nên trông cậy khi đã dùng alias. |

Ví dụ với một nguồn:

```sql
SELECT
    customers.customer_id,
    customers.full_name
FROM lesson_from.customers;
```

Tên `customers` là định danh của nguồn quan hệ khi chưa đặt alias. Khi truy vấn thêm bảng khác có `customer_id`, việc ghi rõ bảng/alias sẽ cần thiết hơn.

### Tên cột không có tiền tố không có nghĩa PostgreSQL đoán ngẫu nhiên

PostgreSQL phân giải tên dựa trên **phạm vi tên hợp lệ của truy vấn**. Nếu một tên cột không đủ thông tin và **có hơn một ứng viên**, hệ quản trị thường báo lỗi nhập nhằng, chứ không chọn ngẫu nhiên bảng đứng trước.

Nếu **không có ứng viên**, nó báo lỗi cột không tồn tại hoặc lỗi tham chiếu phạm vi tùy tình huống. Đó là lý do đặt alias nguồn là kỹ thuật cơ bản để tránh hiểu nhầm.

## 5. Alias bảng với AS

Alias đặt tên ngắn cho một nguồn dữ liệu trong phạm vi câu truy vấn.

```sql
SELECT
    c.customer_id,
    c.full_name
FROM lesson_from.customers AS c
WHERE c.city = 'Hà Nội';
```

Ở đây:

- `lesson_from.customers` là tên quan hệ thật.
- `c` là **bí danh của nguồn trong câu SQL hiện tại**.
- `c.customer_id` và `c.city` tham chiếu các cột của nguồn đã đặt alias `c`.

Từ khóa `AS` có thể bỏ khi đặt alias bảng:

```sql
SELECT c.full_name
FROM lesson_from.customers c;
```

Tuy nhiên, dùng `AS` tường minh giúp người mới nhận ra đâu là tên bảng và đâu là alias. Alias thường được đặt ngắn nhưng gợi nhớ như `c` cho customer, `o` cho order, `p` cho product.

### Sau khi có alias, dùng alias thay tên gốc

Ví dụ **không hợp lệ trong cùng phạm vi**:

```sql
-- Sai: bảng đã được đặt alias c nên tên nguồn customers
-- không còn dùng để tham chiếu cột trong query block này.
SELECT customers.full_name
FROM lesson_from.customers AS c;
```

Sửa:

```sql
SELECT c.full_name
FROM lesson_from.customers AS c;
```

Trong PostgreSQL, đặt alias có ý nghĩa **đổi tên nguồn đối với phần còn lại của query block**. Alias không đổi tên bảng thật trên disk, không ảnh hưởng những SQL khác và không tồn tại sau khi câu truy vấn kết thúc.

### Alias không nhất thiết dùng một ký tự

```sql
SELECT customer.full_name
FROM lesson_from.customers AS customer;
```

Trong truy vấn phức tạp, alias có ý nghĩa nghiệp vụ như `buyer`, `seller`, `manager` rõ hơn `a`/`b`. Ví dụ self-join cần phân biệt hai vai trò của **cùng một bảng** nên alias gần như bắt buộc.

## 6. Cột có tên trùng: ambiguous column

Hai bảng `customers` và `orders` đều có cột `customer_id`. Nếu đưa cả hai vào `FROM` qua `JOIN`, một tham chiếu không tiền tố có thể bị nhập nhằng.

Ví dụ:

```sql
-- Sai: customer_id tồn tại ở cả c và o.
SELECT customer_id
FROM lesson_from.customers AS c
JOIN lesson_from.orders AS o
  ON c.customer_id = o.customer_id;
```

PostgreSQL thường báo:

```text
ERROR:  column reference "customer_id" is ambiguous
```

SQLSTATE tương ứng là **`42702` — `ambiguous_column`**.

Sửa bằng cách xác định rõ bảng:

```sql
SELECT
    c.customer_id,
    c.full_name,
    o.order_id
FROM lesson_from.customers AS c
JOIN lesson_from.orders AS o
  ON o.customer_id = c.customer_id
ORDER BY c.customer_id, o.order_id;
```

Vì `c.customer_id` và `o.customer_id` trỏ tới hai cột vật lý khác nhau, việc dùng tiền tố làm rõ ý nghĩa. Trong một `INNER JOIN` với điều kiện bằng nhau, giá trị ở các hàng ghép được là bằng nhau, nhưng **cả hai cột vẫn tồn tại trong đầu vào** của truy vấn.

### Đừng dựa vào thứ tự FROM để chọn cột

Khi một tên cột xuất hiện ở hai nguồn, PostgreSQL không có quy tắc “ưu tiên bảng đứng đầu `FROM`”. Cần viết `c.customer_id` hoặc `o.customer_id`. Tương tự, các tên thường trùng như `id`, `status`, `name`, `created_at` nên được định danh tường minh khi có nhiều nguồn.

## 7. FROM với hai nguồn: CROSS JOIN và tích Descartes

Khi kết hợp hai bảng mà **không có điều kiện liên hệ**, mỗi hàng của nguồn bên trái có thể ghép với **mỗi hàng** của nguồn bên phải.

```sql
SELECT
    c.full_name,
    p.product_name
FROM lesson_from.customers AS c
CROSS JOIN lesson_from.products AS p
ORDER BY c.customer_id, p.product_id;
```

Với **3 khách hàng** và **3 sản phẩm**, phép kết hợp trên trả **9 hàng** trong ví dụ.

```text
customers: 3 hàng
     ×
products:  3 hàng
     │
     ▼
CROSS JOIN: 9 cặp hàng
```

Cú pháp phân tách bằng dấu phẩy:

```sql
SELECT c.full_name, p.product_name
FROM lesson_from.customers AS c,
     lesson_from.products AS p;
```

về cơ bản cũng tạo tích Descartes trong trường hợp hai nguồn độc lập. Nhưng **`CROSS JOIN` tường minh dễ đọc hơn** vì người xem biết phép nhân hàng là có chủ đích.

### Khi CROSS JOIN hữu ích?

- Tạo mọi tổ hợp sản phẩm – khu vực để xây bảng ma trận.
- Tạo khung báo cáo gồm mọi ngày và mọi nhóm.
- Dùng với một nguồn số nhỏ như `generate_series()` để sinh chuỗi dữ liệu.

### Khi CROSS JOIN nguy hiểm?

Nếu một bảng có 100.000 hàng và bảng kia 50.000 hàng, tích Descartes lý thuyết là **5 tỷ cặp**. Kết quả có thể tiêu thụ rất nhiều CPU, memory và I/O nếu thực sự phải tạo hoặc xử lý số hàng đó.

Một nguyên nhân phổ biến là viết `JOIN` nhưng quên `ON`/`USING` ở những cú pháp cho phép phép ghép không điều kiện. Hãy kiểm tra **row count** và quan hệ khóa trước khi kết hợp bảng lớn.

## 8. JOIN ... ON: kết hợp hàng theo điều kiện

`JOIN ... ON` tạo một nguồn kết hợp, trong đó điều kiện `ON` quyết định cặp hàng có phù hợp hay không.

```sql
SELECT
    o.order_id,
    c.full_name,
    o.status
FROM lesson_from.orders AS o
JOIN lesson_from.customers AS c
  ON o.customer_id = c.customer_id
ORDER BY o.order_id;
```

Kết quả dự kiến:

| order_id | full_name | status |
|---:|---|---|
| 1001 | An | PAID |
| 1002 | An | PENDING |
| 1003 | Bình | PAID |

Vì `orders.customer_id` là khóa ngoại tới `customers.customer_id` trong ví dụ, mỗi đơn có một khách hàng phù hợp. Đây là **INNER JOIN**, cú pháp `JOIN` đơn lẻ thường có nghĩa `INNER JOIN`.

### Phạm vi tên trong ON

Ở đoạn:

```sql
FROM lesson_from.orders AS o
JOIN lesson_from.customers AS c
  ON o.customer_id = c.customer_id
```

điều kiện `ON` có thể tham chiếu những cột hợp lệ của **hai toán hạng JOIN** (`o` và `c`). Alias `o`/`c` đã được khai báo trong mệnh đề `FROM`.

Không viết:

```sql
-- Sai: tên cột customer_id không đủ nguồn ở hai bên.
SELECT o.order_id
FROM lesson_from.orders AS o
JOIN lesson_from.customers AS c
  ON customer_id = customer_id;
```

Vì cùng tên ở hai bảng, cả hai vế điều kiện đều nhập nhằng. Viết rõ `o.customer_id = c.customer_id` không chỉ tránh lỗi mà còn giúp người đọc xác định quan hệ ghép.

## 9. INNER JOIN và LEFT JOIN: cùng tên cột nhưng tập hàng khác nhau

`INNER JOIN` chỉ giữ những cặp hàng ghép được. `LEFT JOIN` giữ tất cả hàng từ nguồn bên trái, ngay cả khi phía bên phải không có hàng phù hợp.

Ví dụ liệt kê **mọi khách hàng**, kể cả người chưa có đơn:

```sql
SELECT
    c.customer_id,
    c.full_name,
    o.order_id,
    o.status
FROM lesson_from.customers AS c
LEFT JOIN lesson_from.orders AS o
  ON o.customer_id = c.customer_id
ORDER BY c.customer_id, o.order_id;
```

Khách hàng **Chi** xuất hiện với `o.order_id` và `o.status` bằng `NULL` vì không có đơn phù hợp.

### Phạm vi cột sau LEFT JOIN

Các cột `o.*` **vẫn là tên hợp lệ** trong phần `SELECT` và `WHERE`, ngay cả khi hàng bên phải không ghép được và các giá trị của nó được mở rộng bằng `NULL`.

Sự tồn tại của **tên cột trong scope** khác với việc **mỗi hàng có giá trị non-null hay không**. Đây là điểm quan trọng khi đọc outer join.

### Đặt điều kiện ở ON khác đặt ở WHERE

Giả sử chỉ quan tâm đơn đã thanh toán, nhưng vẫn muốn giữ **mọi khách hàng**.

Đặt điều kiện trong `ON`:

```sql
SELECT c.full_name, o.order_id, o.status
FROM lesson_from.customers AS c
LEFT JOIN lesson_from.orders AS o
  ON o.customer_id = c.customer_id
 AND o.status = 'PAID'
ORDER BY c.customer_id, o.order_id;
```

Khách hàng không có đơn `PAID` vẫn có thể xuất hiện với cột đơn bằng `NULL`.

Đặt cùng điều kiện ở `WHERE`:

```sql
SELECT c.full_name, o.order_id, o.status
FROM lesson_from.customers AS c
LEFT JOIN lesson_from.orders AS o
  ON o.customer_id = c.customer_id
WHERE o.status = 'PAID'
ORDER BY c.customer_id, o.order_id;
```

Điều kiện `WHERE o.status = 'PAID'` loại các hàng có `o.status IS NULL`, vì biểu thức cho kết quả unknown chứ không phải true. Kết quả có thể giống **INNER JOIN đối với điều kiện này**, nên mất khách hàng không có đơn đã thanh toán.

**Bài học:** Scope tên cột của `o` là hợp lệ ở cả `ON` và `WHERE`, nhưng **ngữ nghĩa lọc hàng rất khác nhau** đối với outer join. Phân biệt tên có thể tham chiếu với nơi đặt điều kiện.

## 10. JOIN ... USING: cột khóa chung xuất hiện một lần

Khi hai nguồn có cùng tên cột khóa, PostgreSQL hỗ trợ `JOIN ... USING (column_name)` để viết điều kiện ghép bằng nhau gọn hơn:

```sql
SELECT
    customer_id,
    c.full_name,
    o.order_id
FROM lesson_from.customers AS c
JOIN lesson_from.orders AS o
USING (customer_id)
ORDER BY customer_id, o.order_id;
```

Ở đây `USING (customer_id)` tương ứng với điều kiện bằng nhau của `c.customer_id` và `o.customer_id`.

Điểm khác biệt quan trọng ở **cấu trúc đầu ra**:

- `JOIN ... ON` giữ cột khóa từ mỗi nguồn trong dạng `SELECT *`.
- `JOIN ... USING` tạo **một cột kết quả hợp nhất** cho mỗi tên nêu trong `USING`; vì vậy `SELECT *` không lặp lại hai bản của `customer_id`.

Ví dụ:

```sql
SELECT *
FROM lesson_from.customers AS c
JOIN lesson_from.orders AS o
USING (customer_id);
```

Cột `customer_id` trong kết quả `*` xuất hiện một lần, tiếp theo là những cột còn lại của hai nguồn theo quy tắc sắp xếp cột của `USING`.

### Khi nào USING phù hợp?

Khi hai bảng thực sự dùng **cùng tên khóa** và ý nghĩa phép ghép là so sánh bằng nhau. Nó giúp code ngắn và tránh lặp cột khóa trong `SELECT *`.

Khi hai bảng dùng tên khác (`orders.customer_id` so với `customers.id`), hoặc điều kiện ghép phức tạp như bất đẳng thức/thời gian, dùng `ON`.

### Không nhầm USING với SELECT c.*

Dù `USING` tạo cột khóa hợp nhất trong kết quả `SELECT *` của join, `c.*` vẫn là cách mở rộng các cột của nguồn `c`, còn `o.*` mở rộng nguồn `o`. Nếu chủ động chọn cả hai:

```sql
SELECT c.*, o.*
FROM lesson_from.customers AS c
JOIN lesson_from.orders AS o USING (customer_id);
```

bạn có thể vẫn có **hai cột kết quả cùng tên** `customer_id`, vì chính bạn yêu cầu toàn bộ cột từ hai nguồn. Đó không còn là kiểu xuất cột hợp nhất đơn thuần của `SELECT *` trên join.

## 11. NATURAL JOIN: ngắn nhưng phụ thuộc cấu trúc cột

PostgreSQL có `NATURAL JOIN`, tự ghép các cột **cùng tên** giữa hai nguồn thay vì phải viết `USING`:

```sql
-- Minh họa cú pháp, không khuyến khích trong truy vấn nghiệp vụ.
SELECT *
FROM lesson_from.customers
NATURAL JOIN lesson_from.orders;
```

Ở schema mẫu, cột chung có thể là `customer_id`, nên hành vi có thể giống `USING (customer_id)`. Nhưng nếu sau này cả hai bảng được thêm cột `status` hoặc `city` cùng tên, **NATURAL JOIN có thể tự thêm điều kiện ghép mới**, làm thay đổi số hàng kết quả dù code SQL không sửa.

Ngoài ra, nếu hai nguồn **không có cột chung**, `NATURAL JOIN` có thể mang ngữ nghĩa tương đương một phép kết hợp không có điều kiện bằng tên chung, dẫn tới số hàng tăng bất ngờ.

Với hệ thống cần bảo trì lâu dài, nên dùng **`JOIN ... ON`** hoặc **`JOIN ... USING (cột được chỉ định rõ)`**. SQL dài thêm một chút nhưng giải thích chính xác quan hệ giữa các bảng.

## 12. Alias cột trong SELECT không phải alias nguồn

`AS` có thể đặt **bí danh cột đầu ra**:

```sql
SELECT
    c.full_name AS customer_name,
    o.order_id AS number_of_order
FROM lesson_from.customers AS c
JOIN lesson_from.orders AS o
  ON c.customer_id = o.customer_id;
```

Phân biệt:

| Biểu thức | Thuộc loại alias nào? | Phạm vi |
|---|---|---|
| `FROM ... customers AS c` | **Table/source alias**. | Tên nguồn trong query block, dùng để gọi `c.full_name`. |
| `SELECT c.full_name AS customer_name` | **Output column alias**. | Tên cột kết quả, có thể dùng ở một số mệnh đề như `ORDER BY`. |
| `FROM (SELECT ...) AS q` | Alias của **nguồn truy vấn con**. | Cột của subquery được tham chiếu qua `q.column_name`. |

Alias cột không thêm một cột vật lý vào bảng; nó chỉ đặt tên cho **biểu thức đầu ra của truy vấn**.

### WHERE không dùng trực tiếp alias ở SELECT

Ví dụ sai:

```sql
-- Sai: display_name được định nghĩa trong SELECT list,
-- chưa phải tên cột nguồn cho WHERE ở cùng query block.
SELECT c.full_name AS display_name
FROM lesson_from.customers AS c
WHERE display_name = 'An';
```

Sửa bằng cách dùng cột nguồn:

```sql
SELECT c.full_name AS display_name
FROM lesson_from.customers AS c
WHERE c.full_name = 'An';
```

Hoặc tạo **query block ngoài** để alias trở thành cột của một nguồn truy vấn con:

```sql
SELECT q.display_name
FROM (
    SELECT c.full_name AS display_name
    FROM lesson_from.customers AS c
) AS q
WHERE q.display_name = 'An';
```

Ở truy vấn ngoài, `display_name` **đã là cột đầu ra của nguồn `q`**, nên `q.display_name` hợp lệ trong `WHERE` của truy vấn ngoài.

## 13. ORDER BY có thể sử dụng alias của SELECT

PostgreSQL cho phép:

```sql
SELECT
    c.full_name AS customer_name
FROM lesson_from.customers AS c
ORDER BY customer_name;
```

`customer_name` ở `ORDER BY` là **tên cột đầu ra** được khai báo trong `SELECT`. Đây là một ngoại lệ quan trọng so với `WHERE`.

Bạn cũng có thể viết:

```sql
SELECT c.full_name AS customer_name
FROM lesson_from.customers AS c
ORDER BY c.full_name;
```

Hai cách phù hợp ở ví dụ này.

### ORDER BY theo vị trí cột

```sql
SELECT c.customer_id, c.full_name
FROM lesson_from.customers AS c
ORDER BY 2, 1;
```

Số `2` và `1` là thứ tự biểu thức trong danh sách đầu ra: `full_name` trước rồi `customer_id`. Cú pháp có thể ngắn nhưng **dễ gãy khi người khác thêm, xóa hoặc đổi thứ tự cột `SELECT`**. Với code cần bảo trì, dùng tên cột/alias rõ ràng thường tốt hơn.

### Xung đột tên ở ORDER BY và GROUP BY

PostgreSQL có quy tắc phân giải khác nhau khi một tên đơn có thể là **tên cột nguồn** và **tên cột đầu ra**:

- `ORDER BY` thường ưu tiên cách hiểu **tên cột đầu ra**.
- `GROUP BY` có quy tắc ưu tiên **tên cột đầu vào** khi có sự nhập nhằng thích hợp.

Vì vậy, đừng đặt alias đầu ra trùng với một cột nguồn khác nếu điều đó có thể làm truy vấn khó hiểu. Viết biểu thức có tiền tố rõ ràng trong `GROUP BY` và `ORDER BY` là cách dễ đọc hơn.

## 14. GROUP BY, HAVING và phạm vi tên cột

Ví dụ đếm số đơn theo khách hàng:

```sql
SELECT
    o.customer_id,
    COUNT(*) AS order_count
FROM lesson_from.orders AS o
GROUP BY o.customer_id
ORDER BY order_count DESC, o.customer_id;
```

Trong đó:

- `o.customer_id` là cột nguồn có thể dùng trong `GROUP BY`.
- `COUNT(*)` là biểu thức aggregate của các hàng trong nhóm.
- `order_count` là tên đầu ra có thể dùng trong `ORDER BY`.

Nếu muốn lọc nhóm có ít nhất hai đơn:

```sql
SELECT
    o.customer_id,
    COUNT(*) AS order_count
FROM lesson_from.orders AS o
GROUP BY o.customer_id
HAVING COUNT(*) >= 2
ORDER BY order_count DESC;
```

Tránh:

```sql
-- Sai hoặc phụ thuộc tên nguồn ngoài ý muốn:
-- HAVING không phải nơi sử dụng alias SELECT như ORDER BY.
SELECT o.customer_id, COUNT(*) AS order_count
FROM lesson_from.orders AS o
GROUP BY o.customer_id
HAVING order_count >= 2;
```

Với `HAVING`, dùng lại aggregate `COUNT(*)` hoặc xây query ngoài:

```sql
SELECT q.customer_id, q.order_count
FROM (
    SELECT o.customer_id, COUNT(*) AS order_count
    FROM lesson_from.orders AS o
    GROUP BY o.customer_id
) AS q
WHERE q.order_count >= 2;
```

**Một cột của nguồn xuất hiện trong `FROM` vẫn có thể không được tham chiếu tùy ý sau `GROUP BY`**: nếu cột không thuộc khóa nhóm và không có quan hệ phụ thuộc hàm được PostgreSQL chấp nhận, cần tổng hợp giá trị đó thay vì chọn ngẫu nhiên một hàng trong nhóm.

## 15. Truy vấn với nhiều JOIN: scope và quan hệ giữa các nguồn

Muốn đọc đơn hàng cùng tên sản phẩm:

```sql
SELECT
    o.order_id,
    c.full_name,
    p.product_name,
    i.quantity
FROM lesson_from.orders AS o
JOIN lesson_from.customers AS c
  ON c.customer_id = o.customer_id
JOIN lesson_from.order_items AS i
  ON i.order_id = o.order_id
JOIN lesson_from.products AS p
  ON p.product_id = i.product_id
ORDER BY o.order_id, p.product_id;
```

Ở đây có bốn nguồn và bốn alias:

| Alias | Nguồn thật | Vai trò |
|---|---|---|
| `o` | `lesson_from.orders` | Đơn hàng. |
| `c` | `lesson_from.customers` | Khách đặt đơn. |
| `i` | `lesson_from.order_items` | Dòng sản phẩm của đơn. |
| `p` | `lesson_from.products` | Thông tin sản phẩm. |

Mỗi cột được viết với alias phù hợp. `i.product_id` và `p.product_id` cùng xuất hiện ở điều kiện ghép, nhưng chỉ một trong hai cần đưa vào `SELECT` nếu muốn ID sản phẩm.

### JOIN một-nhiều làm số dòng tăng

Đơn **1001** có hai dòng sản phẩm nên truy vấn trên trả **hai hàng cho đơn 1001**. Đây không phải lỗi trùng bản ghi: kết quả có **một hàng trên mỗi tổ hợp đơn – dòng sản phẩm**.

Nếu muốn **một hàng trên mỗi đơn**, phải thay đổi bài toán:

```sql
SELECT
    o.order_id,
    c.full_name,
    COUNT(i.product_id) AS distinct_product_lines
FROM lesson_from.orders AS o
JOIN lesson_from.customers AS c
  ON c.customer_id = o.customer_id
LEFT JOIN lesson_from.order_items AS i
  ON i.order_id = o.order_id
GROUP BY o.order_id, c.full_name
ORDER BY o.order_id;
```

`COUNT(i.product_id)` đếm số dòng có product ID non-null. Với bảng mẫu có khóa chính `(order_id, product_id)`, mỗi sản phẩm chỉ xuất hiện một lần trong một đơn. Đơn không có dòng sản phẩm vẫn được giữ nhờ `LEFT JOIN` và có count bằng 0.

**Không chữa mọi trường hợp tăng số dòng bằng `SELECT DISTINCT` một cách máy móc.** Trước hết phải xác định đơn vị hàng mong muốn: một hàng cho mỗi khách, mỗi đơn hay mỗi item.

## 16. Phạm vi từng ON và thứ tự khai báo JOIN

Xem một chuỗi join:

```sql
FROM lesson_from.orders AS o
JOIN lesson_from.order_items AS i
  ON i.order_id = o.order_id
JOIN lesson_from.products AS p
  ON p.product_id = i.product_id
```

`ON` của join thứ nhất có `o` và `i` là các toán hạng. Alias `p` chưa tham gia join đó; bạn không được dùng `p.product_id` ở `ON` của join thứ nhất như thể tất cả alias xuất hiện sau cùng đều đang hiện diện.

Ví dụ sai:

```sql
-- Sai: p chỉ được khai báo ở JOIN sau, nên không thuộc
-- phạm vi ON của JOIN đầu.
SELECT o.order_id
FROM lesson_from.orders AS o
JOIN lesson_from.order_items AS i
  ON p.product_id = i.product_id
JOIN lesson_from.products AS p
  ON p.product_id = i.product_id;
```

Sửa bằng cách đặt điều kiện ở join thích hợp, hoặc sắp lại join để bảng cần tham chiếu thực sự là một toán hạng của `ON`.

### Dấu phẩy và JOIN tường minh có độ ưu tiên khác nhau

PostgreSQL xử lý `JOIN` tường minh **liên kết chặt hơn** danh sách nguồn phân tách bởi dấu phẩy. Ví dụ khái niệm:

```sql
FROM a, b JOIN c ON ...
```

được hiểu theo cấu trúc gần với:

```text
a, (b JOIN c ON ...)
```

Do đó `ON` của `b JOIN c` không tự có quyền tham chiếu cột từ `a` theo cách người viết có thể tưởng. Để tránh lỗi phạm vi và làm rõ ý nghĩa, **ưu tiên viết `JOIN ... ON` tường minh** thay vì trộn dấu phẩy với join.

## 17. Tên schema của bảng và alias có quan hệ gì?

Một database PostgreSQL có nhiều **schema**, ví dụ:

```text
database shopdb
├── schema lesson_from
│   └── table customers
└── schema archive
    └── table customers
```

`lesson_from.customers` là tên quan hệ có **schema qualification**. Trong câu:

```sql
SELECT c.full_name
FROM lesson_from.customers AS c;
```

`lesson_from` giúp PostgreSQL chọn **bảng thật**; `c` là tên nguồn được dùng trong **query block**. Hai tầng tên này có mục đích khác nhau.

### search_path tác động tên bảng không đủ schema

Ví dụ:

```sql
SET search_path TO lesson_from, public;

SELECT customer_id, full_name
FROM customers;

RESET search_path;
```

Trong phiên có `search_path` như trên, `customers` có thể được phân giải tới `lesson_from.customers` nếu role có quyền và không có quy tắc tìm kiếm khác làm thay đổi kết quả.

Điểm quan trọng:

- **`search_path`** giải quyết **tên đối tượng** khi `FROM` chưa ghi schema.
- **Alias `c`/`o`** giải quyết **tên nguồn trong câu truy vấn**.
- **Tiền tố `c.customer_id`** giải quyết **cột của nguồn `c`**, không phải một đường dẫn filesystem hay một schema mới.

`SET search_path` không tự cấp quyền `SELECT` bảng hoặc `USAGE` schema. Trong migration/truy vấn nghiệp vụ cần tính xác định cao, dùng **tên `schema.table`** khi khai báo nguồn thường dễ kiểm tra hơn.

## 18. SELECT * và cách mở rộng cột nguồn

`SELECT *` yêu cầu toàn bộ những cột được xuất từ nguồn `FROM`:

```sql
SELECT *
FROM lesson_from.customers;
```

Với nhiều nguồn:

```sql
SELECT *
FROM lesson_from.customers AS c
JOIN lesson_from.orders AS o
  ON c.customer_id = o.customer_id;
```

Kết quả có thể chứa **hai cột cùng nhãn `customer_id`** khi dùng `JOIN ON`, vì cả hai nguồn đều có cột đó. Điều này gây bất tiện cho code chuyển một dòng SQL thành map theo tên cột hoặc DTO.

### Chọn toàn bộ cột của một nguồn

```sql
SELECT
    c.*,
    o.order_id,
    o.status
FROM lesson_from.customers AS c
JOIN lesson_from.orders AS o
  ON o.customer_id = c.customer_id;
```

`c.*` chỉ mở rộng các cột của nguồn `c`. Nó không có nghĩa “mọi cột trên database”.

### Vì sao không nên SELECT * trong API lâu dài?

1. Thêm cột vào schema có thể thay đổi shape của kết quả mà ứng dụng không chủ đích.
2. Có thể trả cột nhạy cảm hoặc cột payload lớn không cần thiết.
3. Cột cùng tên sau JOIN có thể khiến mapping mơ hồ.
4. Thứ tự vị trí cột thay đổi làm code dựa trên index cột dễ lỗi.
5. Truy vấn có thể đọc nhiều dữ liệu hơn nhu cầu.

Với API, ETL hoặc báo cáo quan trọng, **liệt kê cột cần dùng** và đặt output alias rõ thường an toàn hơn.

## 19. FROM với truy vấn con (derived table)

Nguồn của `FROM` có thể là **kết quả của một SELECT khác** đặt trong ngoặc:

```sql
SELECT
    c.full_name,
    summary.order_count
FROM lesson_from.customers AS c
JOIN (
    SELECT
        o.customer_id,
        COUNT(*) AS order_count
    FROM lesson_from.orders AS o
    GROUP BY o.customer_id
) AS summary
  ON summary.customer_id = c.customer_id
ORDER BY c.customer_id;
```

Truy vấn con tạo một nguồn có cột:

```text
summary
├── customer_id
└── order_count
```

Truy vấn ngoài có thể tham chiếu `summary.customer_id` và `summary.order_count`. Nó **không thể** tham chiếu trực tiếp alias `o` của truy vấn con:

```sql
-- Sai trong query block ngoài:
-- o chỉ được khai báo ở bên trong derived table summary.
SELECT o.customer_id
FROM (
    SELECT customer_id
    FROM lesson_from.orders AS o
) AS summary;
```

Sửa:

```sql
SELECT summary.customer_id
FROM (
    SELECT o.customer_id
    FROM lesson_from.orders AS o
) AS summary;
```

### Phạm vi tên là theo từng query block

```text
Query block ngoài
   ├── nguồn customers AS c
   └── nguồn (query con) AS summary
             │
             └── Query block trong
                   └── nguồn orders AS o

Ngoài thấy: c.*, summary.*
Trong thấy: o.* (và tên hợp lệ của phạm vi ngoài theo
             quy tắc tương quan/LATERAL tương ứng)
```

Đây là một trong những nguyên tắc hữu ích nhất khi truy vấn lồng nhau: **alias không tự “rò” qua ranh giới truy vấn**. Truy vấn con phải xuất những cột cần dùng ra danh sách `SELECT` của chính nó.

## 20. Alias và danh sách tên cột cho derived table

PostgreSQL cho phép gán tên cột khi đặt alias nguồn:

```sql
SELECT
    q.buyer_id,
    q.total_orders
FROM (
    SELECT
        customer_id,
        COUNT(*)
    FROM lesson_from.orders
    GROUP BY customer_id
) AS q(buyer_id, total_orders);
```

Ở query block ngoài, nguồn `q` có hai tên cột nhìn thấy được:

- `buyer_id`: tương ứng cột đầu tiên của query con.
- `total_orders`: tương ứng biểu thức `COUNT(*)` thứ hai.

**Danh sách tên cột gắn với alias thay tên theo vị trí đầu ra của nguồn**, không đổi tên bảng/cột vật lý. Nếu chỉ cung cấp một phần danh sách, những cột còn lại có thể giữ tên đầu ra gốc theo quy tắc PostgreSQL.

Mẫu này hữu ích khi nguồn là `VALUES` hoặc table function không có tên cột phù hợp.

### Cột không được SELECT ở query con sẽ không xuất hiện bên ngoài

```sql
SELECT q.city
FROM (
    SELECT c.customer_id, c.full_name
    FROM lesson_from.customers AS c
) AS q;
```

Câu trên lỗi vì `q` **không có cột `city`**, dù bảng gốc `customers` có cột này. Muốn dùng `city` ở ngoài, phải đưa nó vào output của query con:

```sql
SELECT q.city
FROM (
    SELECT c.customer_id, c.full_name, c.city
    FROM lesson_from.customers AS c
) AS q;
```

## 21. FROM với VALUES: nguồn dữ liệu tạo ngay trong SQL

Một nguồn không nhất thiết là bảng lưu sẵn. `VALUES` tạo một tập hàng từ những biểu thức:

```sql
SELECT
    v.status_code,
    v.display_label
FROM (
    VALUES
        ('PAID', 'Đã thanh toán'),
        ('PENDING', 'Đang chờ'),
        ('CANCELLED', 'Đã hủy')
) AS v(status_code, display_label);
```

`v` là alias của nguồn `VALUES` và `status_code`/`display_label` là tên cột được đặt rõ. Không cần tạo bảng tra cứu để minh họa ba giá trị tạm thời.

### JOIN bảng thật với VALUES

```sql
SELECT
    o.order_id,
    names.display_label
FROM lesson_from.orders AS o
JOIN (
    VALUES
        ('PAID', 'Đã thanh toán'),
        ('PENDING', 'Đang chờ'),
        ('CANCELLED', 'Đã hủy')
) AS names(status_code, display_label)
  ON names.status_code = o.status
ORDER BY o.order_id;
```

Nguồn `names` cung cấp **ba hàng**, mỗi hàng là mã trạng thái kèm tên hiển thị. Ví dụ phù hợp với danh mục nhỏ trong SQL thử nghiệm.

Với hệ thống có bảng trạng thái cần quản trị/thay đổi và phân quyền, bảng reference thực có thể phù hợp hơn việc hard-code `VALUES` lặp lại ở nhiều truy vấn.

## 22. FROM với hàm trả tập hàng

PostgreSQL có **set-returning functions** (SRF) trả về nhiều hàng, có thể tham gia `FROM` như một nguồn.

Ví dụ tạo số từ 1 đến 5:

```sql
SELECT n.number
FROM generate_series(1, 5) AS n(number);
```

Nguồn `n` có một cột `number`. Kết quả gồm các số **1, 2, 3, 4, 5**.

### Sinh khung báo cáo theo ngày

```sql
SELECT g.report_day::date AS report_date
FROM generate_series(
    TIMESTAMP '2026-11-10 00:00:00',
    TIMESTAMP '2026-11-14 00:00:00',
    INTERVAL '1 day'
) AS g(report_day)
ORDER BY g.report_day;
```

Ở đây `generate_series` trả một tập timestamp liên tiếp; alias `g(report_day)` xác định tên nguồn và cột. Chú ý chuỗi ngày được tạo theo `timestamp without time zone`. Với lịch địa phương có DST hoặc định nghĩa instant chính xác, cần xem lại kiểu timestamp và time zone trước khi tính ngày.

### WITH ORDINALITY

Một table function có thể được gắn thêm số thứ tự do PostgreSQL cung cấp:

```sql
SELECT g.value, g.ordinal
FROM generate_series(10, 30, 10)
     WITH ORDINALITY AS g(value, ordinal)
ORDER BY g.ordinal;
```

Kết quả dự kiến:

| value | ordinal |
|---:|---:|
| 10 | 1 |
| 20 | 2 |
| 30 | 3 |

`WITH ORDINALITY` thêm một cột thứ tự bắt đầu từ 1 cho các hàng function trả ra. Nó không phải khóa chính nghiệp vụ và không thay thế điều kiện `ORDER BY` nếu bạn cần bảo đảm thứ tự hiển thị cuối.

### Hàm trả bảng có nhiều cột

Một function có thể được định nghĩa `RETURNS TABLE(...)` và trở thành nguồn gồm nhiều cột. Khi truy vấn:

```sql
SELECT f.column_a, f.column_b
FROM some_set_returning_function(...) AS f;
```

đây chỉ là **mẫu cú pháp**; function minh họa chưa được tạo trong bài. Cần dựa vào kiểu trả về thực của function để biết các cột `f` hỗ trợ.

## 23. WITH / CTE: đặt tên nguồn tạm trong một câu SQL

**Common Table Expression (CTE)** cho phép đặt tên một truy vấn trung gian bằng `WITH`, rồi sử dụng tên đó như một nguồn trong `FROM` của câu lệnh liên quan:

```sql
WITH customer_order_totals AS (
    SELECT
        o.customer_id,
        COUNT(*) AS order_count
    FROM lesson_from.orders AS o
    GROUP BY o.customer_id
)
SELECT
    c.full_name,
    COALESCE(t.order_count, 0) AS order_count
FROM lesson_from.customers AS c
LEFT JOIN customer_order_totals AS t
  ON t.customer_id = c.customer_id
ORDER BY c.customer_id;
```

Kết quả dự kiến:

| full_name | order_count |
|---|---:|
| An | 2 |
| Bình | 1 |
| Chi | 0 |

### Scope của CTE

CTE `customer_order_totals` là một **tên nguồn** được khai báo cho câu SQL này. Nó không tự tạo bảng vật lý tồn tại lâu dài trong schema.

CTE có cột `customer_id` và `order_count` vì đó là những cột `SELECT` bên trong CTE xuất ra. Truy vấn chính có thể đưa CTE vào `FROM` hoặc `JOIN` để dùng các cột này.

**Không thể dùng `t.order_count` ở truy vấn chính nếu chưa đưa nguồn CTE vào FROM với alias `t`.** Việc CTE tồn tại trong phần `WITH` không tự làm mọi cột của nó xuất hiện trong phạm vi cột của `SELECT` chính.

### CTE có thể đặt lại tên cột

```sql
WITH recent_orders(buyer_id, order_number) AS (
    SELECT o.customer_id, o.order_id
    FROM lesson_from.orders AS o
)
SELECT r.buyer_id, r.order_number
FROM recent_orders AS r
ORDER BY r.order_number;
```

Danh sách cột `(buyer_id, order_number)` thuộc tên CTE và xác định tên đầu ra cho nguồn `recent_orders`.

### CTE không phải lúc nào cũng được vật chất hóa thành bảng tạm

Trong PostgreSQL hiện đại, optimizer có quy tắc **inline/materialize CTE** tùy tính chất truy vấn, số lần tham chiếu và các lựa chọn như `MATERIALIZED`/`NOT MATERIALIZED`. Vì vậy, dùng CTE để tổ chức SQL **không đảm bảo** PostgreSQL sẽ tạo một bảng tạm vật lý và chạy nó đúng một lần.

CTE chủ yếu làm **tên nguồn và cấu trúc truy vấn rõ hơn**; hiệu năng phải được đo bằng execution plan thực tế.

## 24. Truy vấn con tương quan: nhìn thấy cột của query block ngoài

Trong một số ngữ cảnh, truy vấn con có thể tham chiếu cột của query block bao quanh. Đây gọi là **correlated subquery**.

Ví dụ tìm khách hàng có ít nhất một đơn:

```sql
SELECT
    c.customer_id,
    c.full_name
FROM lesson_from.customers AS c
WHERE EXISTS (
    SELECT 1
    FROM lesson_from.orders AS o
    WHERE o.customer_id = c.customer_id
)
ORDER BY c.customer_id;
```

Ở truy vấn con trong `EXISTS`:

- `o.customer_id` thuộc nguồn `orders AS o` **bên trong**.
- `c.customer_id` thuộc nguồn `customers AS c` **bên ngoài**.
- PostgreSQL cho phép tham chiếu `c.customer_id` ở ngữ cảnh tương quan này.

Sơ đồ phạm vi:

```text
OUTER QUERY
  FROM customers AS c
         │
         └───────── c.customer_id
                        │  tham chiếu từ trong
                        ▼
                 EXISTS subquery
                   FROM orders AS o
                   WHERE o.customer_id = c.customer_id
```

Trong dữ liệu ví dụ, khách hàng **An** và **Bình** có đơn, còn **Chi** không có.

### Khi tên cột của inner query trùng outer query

Nếu viết cột không tiền tố như `customer_id` bên trong truy vấn con:

```sql
SELECT c.full_name
FROM lesson_from.customers AS c
WHERE EXISTS (
    SELECT 1
    FROM lesson_from.orders AS o
    WHERE customer_id = c.customer_id
);
```

`customer_id` không tiền tố thường được phân giải ở **phạm vi trong** nếu nó xác định được ở đó, tức `o.customer_id` trong ví dụ. Nhưng khi có thêm nguồn nội bộ cùng tên, nó có thể trở nên nhập nhằng.

**Khuyến nghị:** Trong correlated subquery, dùng alias rõ `o.customer_id = c.customer_id` để tránh phụ thuộc vào cơ chế ưu tiên tên của query block trong/ngoài.

### Alias bên trong có thể che alias bên ngoài

Ví dụ dễ gây lỗi logic:

```sql
-- Không nên: dùng lại alias c trong inner query.
SELECT c.full_name
FROM lesson_from.customers AS c
WHERE EXISTS (
    SELECT 1
    FROM lesson_from.orders AS c
    WHERE c.customer_id = c.customer_id
);
```

Trong truy vấn con, alias `c` của `orders` che alias `c` của `customers` ở ngoài. Điều kiện trở thành tự so sánh cột với chính nó, không còn tương quan khách hàng. Câu SQL có thể chạy nhưng **kết quả sai nghiệp vụ**.

Giải pháp: **không tái sử dụng cùng alias cho hai vai trò khác nhau trong các query block lồng nhau**, nhất là khi cần correlated predicates.

## 25. Derived table và LATERAL: khác biệt về quyền nhìn cột bên ngoài

Đây là quy tắc quan trọng của PostgreSQL: một **truy vấn con trong `FROM`** thông thường **không được phép** trực tiếp tham chiếu những nguồn đứng trước trong cùng danh sách `FROM`, trừ khi bạn khai báo **`LATERAL`** phù hợp.

Ví dụ không hợp lệ:

```sql
-- Sai: derived table thông thường trong FROM
-- không có quyền nhìn c.customer_id như một nguồn LATERAL.
SELECT c.full_name, recent.order_id
FROM lesson_from.customers AS c
LEFT JOIN (
    SELECT o.order_id
    FROM lesson_from.orders AS o
    WHERE o.customer_id = c.customer_id
    ORDER BY o.ordered_at DESC
    LIMIT 1
) AS recent ON TRUE;
```

Mặc dù `c` xuất hiện ở `FROM` bên ngoài, derived table trong `FROM` cần `LATERAL` để tham chiếu nó.

### 25.1. Dùng LEFT JOIN LATERAL

```sql
SELECT
    c.customer_id,
    c.full_name,
    recent.order_id,
    recent.ordered_at
FROM lesson_from.customers AS c
LEFT JOIN LATERAL (
    SELECT o.order_id, o.ordered_at
    FROM lesson_from.orders AS o
    WHERE o.customer_id = c.customer_id
    ORDER BY o.ordered_at DESC, o.order_id DESC
    LIMIT 1
) AS recent ON TRUE
ORDER BY c.customer_id;
```

Kết quả dự kiến:

| customer_id | full_name | order_id |
|---:|---|---:|
| 1 | An | 1002 |
| 2 | Bình | 1003 |
| 3 | Chi | NULL |

Ý nghĩa:

1. Lấy từng hàng của nguồn `c`.
2. Truy vấn `LATERAL` có thể dùng `c.customer_id` làm tham số tương quan.
3. Lấy đơn mới nhất theo `ordered_at`, tách hòa bằng `order_id`.
4. `LEFT JOIN ... ON TRUE` vẫn giữ khách hàng không có đơn.

Đây là một mẫu truy vấn hữu ích khi cần **một kết quả phụ tối đa N hàng cho mỗi hàng nguồn**.

### 25.2. CROSS JOIN LATERAL

```sql
SELECT c.full_name, x.order_id
FROM lesson_from.customers AS c
CROSS JOIN LATERAL (
    SELECT o.order_id
    FROM lesson_from.orders AS o
    WHERE o.customer_id = c.customer_id
) AS x
ORDER BY c.customer_id, x.order_id;
```

Nếu truy vấn LATERAL không trả hàng cho khách hàng `Chi`, `CROSS JOIN LATERAL` không tạo hàng kết quả cho khách đó. `LEFT JOIN LATERAL` có thể giữ hàng bên trái với các giá trị phía phải bằng `NULL`.

### 25.3. Hàm trong FROM có thể tự tham chiếu cột nguồn trước

Với các **table functions**, PostgreSQL cho phép tham số hàm trong `FROM` tham chiếu các nguồn đứng trước; từ khóa `LATERAL` đối với function thường là **tùy chọn**.

Ví dụ:

```sql
SELECT
    o.order_id,
    g.step_no
FROM lesson_from.orders AS o
CROSS JOIN generate_series(1, o.order_id - 1000) AS g(step_no)
ORDER BY o.order_id, g.step_no;
```

`generate_series` dùng `o.order_id` ở nguồn phía trước. Truy vấn tạo số lượng hàng phụ thuộc từng đơn, và chỉ phù hợp làm ví dụ trong lab; không dùng biểu thức sinh dải lớn không giới hạn trên dữ liệu production.

**Quy tắc dễ nhớ:** `LATERAL` là thiết yếu khi derived subquery trong `FROM` cần nhìn sang nguồn đứng trước; với table function, PostgreSQL thường cho phép tham chiếu tham số theo cách này ngay cả khi không viết từ khóa.

## 26. JOIN alias có thể che tên nguồn con

PostgreSQL cho phép đặt alias lên **toàn bộ biểu thức JOIN**, không chỉ từng bảng:

```sql
SELECT j.customer_id, j.order_id
FROM (
    lesson_from.customers AS c
    JOIN lesson_from.orders AS o
      ON c.customer_id = o.customer_id
) AS j;
```

Trong trường hợp `JOIN ... ON` ở trên, nguồn `j` có thể xuất **hai cột `customer_id` cùng tên**. Tham chiếu `j.customer_id` có thể bị **ambiguous** vì cả hai cột của join đều có tên ấy.

Để dùng mẫu này an toàn, chọn rõ cột đầu ra bằng derived subquery:

```sql
SELECT j.customer_id, j.order_id
FROM (
    SELECT c.customer_id, o.order_id
    FROM lesson_from.customers AS c
    JOIN lesson_from.orders AS o
      ON c.customer_id = o.customer_id
) AS j;
```

### Quy tắc che tên của JOIN alias

Khi alias được áp dụng cho cả một join expression, alias có thể **che các tên nguồn bên trong join** đối với query block bên ngoài:

```text
(customers AS c JOIN orders AS o ON ...) AS j
                    │
                    ▼
Query block ngoài nhìn thấy nguồn j
Không mặc nhiên dùng c.column/o.column từ bên ngoài j
```

Đừng nhầm alias của một **toán hạng bảng** với alias của một **join expression** chứa nhiều bảng. Đặt alias sau cặp ngoặc của join có thể thay đổi tên nào được nhìn thấy tại mức truy vấn bao quanh.

## 27. FROM với view và materialized view

Một **view** là một đối tượng truy vấn có tên, cho phép sử dụng như một bảng nguồn:

```sql
CREATE VIEW lesson_from.paid_orders AS
SELECT
    o.order_id,
    o.customer_id,
    o.ordered_at
FROM lesson_from.orders AS o
WHERE o.status = 'PAID';
```

Sau đó:

```sql
SELECT v.order_id, v.customer_id
FROM lesson_from.paid_orders AS v
ORDER BY v.order_id;
```

Từ góc nhìn của truy vấn ngoài, `v` là một nguồn có ba cột `order_id`, `customer_id`, `ordered_at`, được định nghĩa bởi view. Nó **không** xuất cột `status` vì view không chọn cột đó.

### View và subquery khác nhau ở vòng đời

- **Derived table:** nguồn chỉ tồn tại trong câu SQL chứa nó.
- **CTE:** tên nguồn cho phạm vi câu SQL có `WITH`.
- **View:** object có tên tồn tại trong schema cho tới khi được thay đổi/xóa.
- **Materialized view:** lưu kết quả đã được vật chất hóa và cần quản lý việc refresh; không tự phản ánh mọi thay đổi của bảng gốc ngay lập tức.

Về **phạm vi tên cột trong truy vấn đọc**, các nguồn đều cung cấp **tập cột đầu ra** của chúng. Cách PostgreSQL tính toán/vật chất hóa dữ liệu ở bên dưới là vấn đề riêng.

### Không mặc định view cấp quyền truy cập như bảng gốc

Quyền đối với view, bảng gốc và ngữ nghĩa `security_invoker`/owner tùy cấu hình và phiên bản PostgreSQL. Một view có thể được dùng để thiết kế đường truy cập có kiểm soát, nhưng **không phải mọi view đều tự là ranh giới bảo mật đầy đủ**. Cần kiểm tra quyền và chính sách row-level security phù hợp.

## 28. Self-join: cùng một bảng xuất hiện hai lần

Một bảng có thể xuất hiện **hai lần** trong cùng `FROM` để diễn đạt hai vai trò khác nhau.

Ví dụ tìm những cặp khách hàng cùng thành phố:

```sql
SELECT
    left_customer.customer_id AS first_customer,
    right_customer.customer_id AS second_customer,
    left_customer.city
FROM lesson_from.customers AS left_customer
JOIN lesson_from.customers AS right_customer
  ON left_customer.city = right_customer.city
 AND left_customer.customer_id < right_customer.customer_id
ORDER BY first_customer, second_customer;
```

Trong dữ liệu mẫu hiện tại, mỗi khách ở một thành phố nên truy vấn có thể trả **0 hàng**. Điều đó là kết quả hợp lệ.

Hai nguồn cùng tham chiếu bảng `lesson_from.customers` nhưng dùng **hai alias riêng**:

```text
customers AS left_customer
customers AS right_customer
```

Điều kiện `left_customer.customer_id < right_customer.customer_id` giúp tránh cặp một khách với chính họ và tránh liệt kê đảo chiều A–B/B–A.

### Vì sao alias đặc biệt quan trọng với self-join?

Nếu cả hai nguồn chỉ dùng tên bảng `customers` mà không alias, tên nguồn không đủ phân biệt. PostgreSQL có thể báo trùng alias/table reference hoặc các lỗi về phân giải tên. Với self-join, nên đặt alias theo **vai trò nghiệp vụ**, ví dụ `employee`/`manager`, `current`/`previous`, `parent`/`child`.

## 29. Các lỗi về phạm vi tên thường gặp

| Lỗi PostgreSQL thường gặp | Mã SQLSTATE phổ biến | Nguyên nhân cần kiểm tra |
|---|---|---|
| `column reference "x" is ambiguous` | `42702` | Có nhiều cột tên `x` trong phạm vi hiện tại; thiếu prefix hoặc kết quả JOIN có tên trùng. |
| `column "x" does not exist` | `42703` | Tên cột sai, alias đầu ra dùng ở sai chỗ, hoặc query con không xuất cột đó. |
| `relation "x" does not exist` | `42P01` | Nguồn không tồn tại theo tên/schema/search_path, hoặc thiếu quyền/ngữ cảnh phù hợp. |
| `missing FROM-clause entry for table "x"` | `42P01` trong nhiều trường hợp | Alias/tên nguồn không có trong phạm vi truy vấn hoặc bị join alias/subquery che. |
| `invalid reference to FROM-clause entry for table "x"` | Tùy tình huống, thường liên quan phân giải nguồn | Có nguồn tên đó nhưng vị trí tham chiếu không hợp lệ, ví dụ thiếu `LATERAL`. |
| `table name "x" specified more than once` | Có thể là `42712` (`duplicate_alias`) | Dùng cùng tên nguồn/alias hai lần trong một query block. |

Mã SQLSTATE chính xác tùy lỗi thực tế. Khi chẩn đoán bằng `psql`, có thể bật:

```text
\set VERBOSITY verbose
```

hoặc dùng `\errverbose` sau lỗi gần nhất để xem SQLSTATE và các trường chẩn đoán. Những lệnh bắt đầu bằng `\` là **meta-command của `psql`**, không phải câu SQL gửi qua JDBC.

### Lỗi cột không tồn tại nhưng bảng có cột đó

Ví dụ:

```sql
SELECT q.city
FROM (
    SELECT c.customer_id
    FROM lesson_from.customers AS c
) AS q;
```

Bảng gốc có `city` nhưng **nguồn `q` chỉ xuất `customer_id`**, nên `q.city` không tồn tại trong query block ngoài.

Hãy hỏi: “Cột này có nằm trong **tập cột đầu ra của nguồn hiện đang dùng** không?”, không chỉ hỏi “bảng gốc có cột đó không?”.

## 30. Lược đồ phân giải tên cột theo phạm vi

Một cách tiếp cận khi đọc query phức tạp:

```text
Tên trong một biểu thức SQL
          │
          ▼
Đây có phải tên bảng/nguồn?
          │
          ├── Có → tra query block + alias + schema/search_path
          │
          └── Tên cột
                   │
                   ▼
          Có tiền tố nguồn (o.id)?
              ├── Có → nguồn o có trong scope?
              │           │
              │           └── cột id được nguồn o xuất ra?
              │
              └── Không → trong phạm vi hiện tại
                          có đúng một cột phù hợp?
                             ├── Một → hợp lệ
                             ├── Nhiều → ambiguous
                             └── Không → xét outer scope nếu
                                         ngữ cảnh tương quan cho phép;
                                         nếu không thì lỗi
```

Sau khi xác định cột nguồn, cần xét **mệnh đề đang dùng**: `WHERE` không thể sử dụng alias đầu ra của cùng `SELECT` như `ORDER BY`; `ON` chỉ nhìn thấy các nguồn hợp lệ của join đang xét; derived subquery trong `FROM` cần `LATERAL` nếu muốn tham chiếu nguồn trước đó.

### Tên đầu ra và tên nguồn là hai lớp khác nhau

Ví dụ:

```sql
SELECT
    o.order_id AS id_for_display
FROM lesson_from.orders AS o
ORDER BY id_for_display;
```

- `o.order_id` là cột của nguồn `o`.
- `id_for_display` là tên cột kết quả.
- `ORDER BY` có thể dùng tên cột kết quả.
- `WHERE` cùng query block vẫn nên dùng `o.order_id`, không phải `id_for_display`.

Việc phân biệt **hai lớp tên** giải quyết phần lớn lỗi phạm vi alias ở SQL cơ bản.

## 31. Phân tích lỗi thực tế: vì sao truy vấn trả số hàng bất ngờ?

Một truy vấn:

```sql
SELECT
    o.order_id,
    p.product_name
FROM lesson_from.orders AS o
JOIN lesson_from.order_items AS i
  ON i.order_id = o.order_id
JOIN lesson_from.products AS p
  ON p.product_id = i.product_id;
```

Đơn 1001 có hai items nên xuất hiện **hai dòng**. Nếu API mong một hàng trên mỗi đơn, cần chọn cách khác:

- Tổng hợp items bằng `GROUP BY`/`json_agg`.
- Lấy đúng một item theo điều kiện nghiệp vụ với `LATERAL`.
- Chỉ cần kiểm tra “có item hay không” thì dùng `EXISTS`.

Ví dụ không nhân bản đơn khi chỉ hỏi có ít nhất một item:

```sql
SELECT o.order_id, o.status
FROM lesson_from.orders AS o
WHERE EXISTS (
    SELECT 1
    FROM lesson_from.order_items AS i
    WHERE i.order_id = o.order_id
)
ORDER BY o.order_id;
```

`EXISTS` kiểm tra có hàng phù hợp, không đưa mọi dòng item vào kết quả ngoài. Hiểu rõ **nguồn `FROM` đại diện cho mức chi tiết hàng nào** giúp tránh nhiều lỗi thống kê.

## 32. Phạm vi tên và SQL trong Java/JDBC

Khi ứng dụng Java gửi SQL, PostgreSQL vẫn áp dụng quy tắc scope/alias như trong `psql`.

Ví dụ `PreparedStatement`:

```java
String sql = """
    SELECT
        o.order_id,
        c.full_name,
        o.status
    FROM lesson_from.orders AS o
    JOIN lesson_from.customers AS c
      ON c.customer_id = o.customer_id
    WHERE o.status = ?
    ORDER BY o.order_id
    """;

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setString(1, "PAID");
    try (ResultSet rs = ps.executeQuery()) {
        while (rs.next()) {
            long orderId = rs.getLong("order_id");
            String customerName = rs.getString("full_name");
            String status = rs.getString("status");
            // Xử lý dòng kết quả.
        }
    }
}
```

Ví dụ dùng **Java text blocks** (Java hiện đại), giả định `connection` đã tồn tại và có quyền truy vấn. Placeholder `?` dùng để truyền **giá trị** như `'PAID'`, không thay thế tên bảng, schema hay alias.

### Không dùng ? cho tên bảng hoặc tên cột

Không hợp lệ theo ý tưởng truyền identifier:

```java
String badSql = "SELECT * FROM ?";
// ps.setString(1, "lesson_from.orders") KHÔNG biến ? thành tên bảng.
```

Placeholder JDBC đại diện cho **giá trị biểu thức**, không phải cú pháp định danh SQL. Nếu thật sự phải xây truy vấn động theo bảng/schema:

1. Chọn tên nguồn từ **danh sách được phép** do ứng dụng quản lý.
2. Quote identifier đúng theo quy tắc PostgreSQL khi tạo SQL.
3. Không nối tên bảng/schema trực tiếp từ input không đáng tin.
4. Dùng `?` cho các **giá trị** trong `WHERE`/`VALUES`.

### Tránh tên cột trùng trong ResultSet

```sql
SELECT c.customer_id, o.customer_id
FROM lesson_from.customers AS c
JOIN lesson_from.orders AS o
  ON o.customer_id = c.customer_id;
```

Kết quả có hai cột cùng label `customer_id`, làm `ResultSet.getLong("customer_id")` có thể không rõ ý định người viết. Nên dùng alias đầu ra khác nhau khi thật sự cần hai giá trị:

```sql
SELECT
    c.customer_id AS buyer_id,
    o.customer_id AS order_buyer_id
FROM lesson_from.customers AS c
JOIN lesson_from.orders AS o
  ON o.customer_id = c.customer_id;
```

Với API/DTO, đặt nhãn cột đầu ra **duy nhất và có nghĩa** sẽ giúp code dễ kiểm tra hơn.

## 33. Debug đúng connection: schema, role và search_path

Nếu một SQL chạy được trong `psql` nhưng fail trong ứng dụng, cần kiểm tra **môi trường của đúng connection**:

```sql
SELECT
    current_database() AS db_name,
    current_user AS role_name,
    current_schema() AS default_schema,
    current_schemas(true) AS effective_schema_path;

SHOW search_path;
```

Nguyên nhân thường gặp:

- Ứng dụng dùng role khác và thiếu `USAGE`/`SELECT`.
- `search_path` của connection pool khác phiên `psql`.
- Bảng thực nằm trong một schema không thuộc đường tìm kiếm.
- ORM hoặc migration đặt alias/tên bảng có dấu nháy kép, gây khác biệt chữ hoa/chữ thường.
- Query con không xuất cột mà SQL ngoài đang gọi.

**Đừng dùng việc query thành công trong tài khoản superuser làm bằng chứng rằng role ứng dụng cũng có quyền.** Cần dùng role và search path phù hợp với môi trường thực.

## 34. Tên có dấu nháy kép và chữ hoa/chữ thường

PostgreSQL chuẩn hóa **identifier không được đặt trong dấu nháy kép** về chữ thường:

```sql
SELECT c.full_name
FROM lesson_from.Customers AS c;
```

Trong ví dụ, `Customers` không quote được hiểu như `customers`, nên vẫn phù hợp.

Nhưng:

```sql
-- Không trỏ tới bảng customers chữ thường.
SELECT c.full_name
FROM lesson_from."Customers" AS c;
```

`"Customers"` là identifier phân biệt chữ hoa/chữ thường và khác `customers`. Nếu không có bảng thực tên `Customers`, PostgreSQL báo không tồn tại.

### Dấu nháy kép khác dấu nháy đơn

```sql
-- Đúng: chuỗi giá trị.
WHERE c.full_name = 'An'

-- Đúng: tên cột có chữ hoa, nếu cột thật được tạo với tên đó.
SELECT c."FullName" FROM some_schema.some_table AS c;
```

Hai đoạn trên minh họa cú pháp, không phải hai câu SQL tự chạy độc lập trên dữ liệu mẫu. Khi đặt tên bảng/cột, dùng chữ thường và dấu gạch dưới thường làm SQL dễ bảo trì hơn.

### Identifier trong tên cột và schema không phải chuỗi literal

`lesson_from.customers` và `c.customer_id` là những thành phần định danh. `'lesson_from.customers'` chỉ là một chuỗi văn bản; PostgreSQL không tự chuyển nó thành quan hệ trong `FROM` khi bạn đặt ở vị trí tên bảng.

## 35. Những hiểu nhầm cần tránh

**“SELECT đứng trước FROM nên alias trong SELECT phải dùng được ở WHERE.”** Không. Scope alias đầu ra khác với cột nguồn; dùng cột thật ở `WHERE` hoặc tạo query ngoài.

**“JOIN hai bảng có cùng customer_id thì SELECT customer_id tự chọn bảng đầu.”** Không. Với `JOIN ... ON`, tên không tiền tố thường nhập nhằng; dùng `c.customer_id` hoặc `o.customer_id`.

**“Alias bảng chỉ là cách viết tắt, vẫn gọi được tên gốc.”** Không trong cùng query block sau khi đặt alias: tên nguồn cần dùng là alias.

**“Mọi SELECT phải có FROM.”** Không. PostgreSQL hỗ trợ `SELECT` tính biểu thức không cần bảng nguồn.

**“JOIN làm kết quả trùng nên cứ thêm DISTINCT.”** Không. JOIN một-nhiều tạo nhiều hàng đúng theo quan hệ; cần xác định mức chi tiết và phép tổng hợp mong muốn.

**“LEFT JOIN rồi WHERE cột bên phải thì vẫn luôn giữ mọi hàng bên trái.”** Không. Điều kiện `WHERE` có thể loại hàng mở rộng bằng `NULL`.

**“USING và ON giống hệt nhau trong SELECT *.”** Không. `USING` tạo cột khóa kết quả hợp nhất; `ON` giữ các cột từ từng nguồn.

**“NATURAL JOIN luôn thuận tiện hơn USING.”** Không. Nó có thể tự thay điều kiện khi schema xuất hiện cột cùng tên mới.

**“Cột có trong bảng gốc thì truy vấn ngoài derived table luôn dùng được.”** Không. Query ngoài chỉ thấy các cột do nguồn derived table **xuất ra**.

**“Alias trong truy vấn con tự có hiệu lực ở truy vấn ngoài.”** Không. Query block tạo phạm vi riêng.

**“Truy vấn con nào cũng tham chiếu được mọi bảng ngoài.”** Không. Correlated subquery ở `WHERE` có quy tắc khác derived subquery trong `FROM`; ở dạng sau thường cần `LATERAL`.

**“CTE luôn tạo bảng tạm vật lý.”** Không. PostgreSQL có thể inline/materialize tùy đặc điểm truy vấn và phiên bản.

**“SQL dùng tên bảng không ghi schema luôn tìm trong public.”** Không. Cần xem `search_path` và quyền.

**“Thêm table alias sẽ cấp quyền truy cập bảng.”** Không. Alias chỉ đổi tên nguồn trong câu SQL; phân quyền PostgreSQL vẫn được kiểm tra riêng.

**“SELECT * ổn định cho mọi API.”** Không. Thêm cột hoặc thay JOIN có thể đổi shape, tạo label trùng và làm lộ trường không cần thiết.

**“ORDER BY 1 luôn rõ nghĩa.”** Không. Sắp theo vị trí cột có thể thay đổi khi danh sách `SELECT` được chỉnh sửa.

**“Placeholder JDBC ? dùng được cho tên schema hoặc bảng.”** Không. Placeholder dành cho giá trị; identifier động cần được chọn/quote một cách có kiểm soát.

## 36. Bài tập thực hành

### Bài 1 — Xác định nguồn FROM

Cho:

```sql
SELECT c.full_name, o.order_id
FROM lesson_from.customers AS c
JOIN lesson_from.orders AS o
  ON c.customer_id = o.customer_id;
```

Hãy chỉ ra bảng thật, alias của từng bảng, cột khóa ghép, cột đầu ra và số hàng dự kiến theo dữ liệu mẫu.

### Bài 2 — Sửa ambiguous column

Câu truy vấn:

```sql
SELECT customer_id, order_id
FROM lesson_from.customers AS c
JOIN lesson_from.orders AS o
  ON c.customer_id = o.customer_id;
```

Hãy sửa để không còn nhập nhằng. Vì sao PostgreSQL không tự ưu tiên `customer_id` của bảng đứng bên trái?

### Bài 3 — Tìm lỗi alias bảng

```sql
SELECT customers.full_name
FROM lesson_from.customers AS c;
```

Giải thích tại sao tên `customers` không còn là tham chiếu hợp lệ trong query block này. Viết lại truy vấn đúng.

### Bài 4 — Cột SELECT alias trong WHERE

```sql
SELECT c.full_name AS display_name
FROM lesson_from.customers AS c
WHERE display_name LIKE 'A%';
```

Hãy sửa theo **hai cách**: dùng `c.full_name` trực tiếp trong `WHERE` hoặc bọc truy vấn con có alias `q`. Khi nào `display_name` trở thành cột nguồn hợp lệ?

### Bài 5 — Hiểu row multiplication

Một đơn có ba item, một đơn khác có một item. Dự đoán số dòng:

```sql
SELECT o.order_id, i.product_id
FROM lesson_from.orders AS o
JOIN lesson_from.order_items AS i
  ON o.order_id = i.order_id;
```

Viết truy vấn muốn **một dòng cho mỗi đơn** cùng số lượng dòng sản phẩm, kể cả đơn chưa có item.

### Bài 6 — LEFT JOIN và WHERE

Viết hai truy vấn để phân biệt:

1. **Mọi khách hàng**, cùng đơn `PAID` nếu có.
2. **Chỉ khách hàng có đơn `PAID`**.

Giải thích vị trí điều kiện `o.status = 'PAID'` trong `ON` so với `WHERE` và ảnh hưởng tới khách **Chi**.

### Bài 7 — USING và NATURAL JOIN

So sánh:

```sql
FROM lesson_from.customers AS c
JOIN lesson_from.orders AS o
  ON c.customer_id = o.customer_id
```

với:

```sql
FROM lesson_from.customers AS c
JOIN lesson_from.orders AS o
USING (customer_id)
```

Hãy mô tả sự khác nhau khi `SELECT *`. Nếu bảng được thêm cột mới cùng tên, vì sao `NATURAL JOIN` có thể thay đổi hành vi bất ngờ?

### Bài 8 — Derived table và output scope

```sql
SELECT q.full_name, q.city
FROM (
    SELECT c.full_name
    FROM lesson_from.customers AS c
) AS q;
```

Hãy chỉ ra lỗi và viết lại query con để nguồn `q` xuất đủ hai cột. Tại sao `city` tồn tại ở bảng gốc chưa đủ?

### Bài 9 — CTE

Tạo CTE `paid_order_count` đếm số đơn `PAID` của mỗi khách. Dùng `LEFT JOIN` để trả **mọi khách** và số đơn đã thanh toán, kể cả người có 0 đơn. Dùng `COALESCE` để thay `NULL` bằng 0 và giải thích alias nào thuộc CTE, alias nào thuộc query chính.

### Bài 10 — Correlated subquery

Viết `EXISTS` để lấy khách hàng có ít nhất một đơn `PENDING`. Phải dùng `c.customer_id` ở query ngoài và `o.customer_id` ở query trong. Nếu đặt cùng alias `c` cho `orders` bên trong, điều gì có thể xảy ra?

### Bài 11 — LATERAL

Viết `LEFT JOIN LATERAL` lấy đơn mới nhất cho mỗi khách theo `ordered_at` và tách hòa bằng `order_id`. Vì sao derived table trong `FROM` cần `LATERAL` để dùng `c.customer_id`? Khách không có đơn được hiển thị như thế nào?

### Bài 12 — VALUES và generate_series()

Tạo một nguồn `VALUES` có các cặp mã trạng thái/nhãn hiển thị; dùng `JOIN` với bảng `orders`. Sau đó dùng `generate_series(1,3) WITH ORDINALITY`, đặt alias cho **cột giá trị** và **cột thứ tự**.

### Bài 13 — Chẩn đoán search_path

Giả sử `SELECT * FROM customers` báo `relation does not exist`, nhưng `SELECT * FROM lesson_from.customers` chạy được. Hãy liệt kê các lệnh kiểm tra `SHOW search_path`, `current_schema()`, `current_schemas(true)`, cùng các quyền liên quan. Tại sao việc bảng tồn tại không đồng nghĩa tên ngắn chắc chắn phân giải được?

### Bài 14 — SQL trong JDBC

Viết một `PreparedStatement` lấy các đơn theo `status = ?`, dùng alias nguồn `o`/`c` và output alias khác tên để tránh label trùng. Giải thích vì sao không được dùng `?` thay tên bảng hoặc schema lấy từ HTTP request.

### Bài 15 — Kiểm tra phạm vi của ON

Cho:

```sql
FROM lesson_from.orders AS o
JOIN lesson_from.order_items AS i
  ON p.product_id = i.product_id
JOIN lesson_from.products AS p
  ON p.product_id = i.product_id
```

Hãy giải thích vì sao `p.product_id` trong `ON` đầu tiên không hợp lệ và viết lại điều kiện ghép đúng.

### Bài 16 — Sử dụng GROUP BY và ORDER BY alias

Viết truy vấn trả `customer_id`, số đơn với tên đầu ra `order_count`, sắp từ số đơn nhiều xuống ít. Sau đó thêm điều kiện giữ những khách có ít nhất hai đơn. Hãy giải thích tại sao `ORDER BY order_count` hợp lệ nhưng `HAVING order_count >= 2` không phải cách tham chiếu alias đầu ra nên dùng trong cùng query block.

## Kết luận

**`FROM` quyết định những nguồn dữ liệu nào tham gia truy vấn và những tên cột nào có thể được sử dụng trong query block.** Nguồn có thể là bảng/view, kết quả `JOIN`, `VALUES`, derived table, CTE hoặc hàm trả tập hàng. Khi có nhiều nguồn, alias giúp ghi rõ vai trò như `c.full_name`, `o.order_id` và ngăn lỗi `ambiguous_column`.

Cần phân biệt **ba tầng tên**: tên đối tượng ở schema được tìm qua `search_path` hoặc `schema.table`, alias nguồn được tạo trong `FROM`, và alias cột đầu ra được tạo ở `SELECT`. Các alias này **không có phạm vi giống nhau**. `WHERE` và `ON` tham chiếu cột nguồn hợp lệ; `ORDER BY` có thể dùng alias đầu ra; truy vấn ngoài chỉ thấy các cột mà derived table/CTE xuất ra. Correlated subquery có thể nhìn thấy cột phạm vi ngoài theo quy tắc của nó, còn derived table trong `FROM` thường cần **`LATERAL`** nếu muốn nhìn những nguồn xuất hiện trước.

Khi thiết kế SQL PostgreSQL có nhiều bảng, hãy **chọn mức chi tiết hàng kết quả**, ghi điều kiện `JOIN` tường minh, cân nhắc `LEFT JOIN` cùng vị trí đặt filter, hạn chế `NATURAL JOIN` và `SELECT *` trong API lâu dài, đồng thời đặt tên đầu ra duy nhất. Hiểu đúng **nguồn, alias và phạm vi tên cột** là nền tảng để xây truy vấn chính xác, dễ bảo trì và ít lỗi khi lược đồ dữ liệu phát triển.
