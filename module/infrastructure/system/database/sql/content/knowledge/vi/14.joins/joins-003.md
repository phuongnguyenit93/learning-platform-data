# LEFT JOIN, RIGHT JOIN và giữ lại hàng không khớp

Khi làm việc với cơ sở dữ liệu quan hệ, chúng ta thường cần ghép dữ liệu từ nhiều bảng. Chẳng hạn, một ứng dụng bán hàng có bảng **khách hàng** và bảng **đơn hàng**. Nếu chỉ muốn xem những đơn có khách hàng tương ứng, `INNER JOIN` thường là đủ. Nhưng nếu câu hỏi là **“Liệt kê tất cả khách hàng, kể cả người chưa đặt đơn nào”** hoặc **“Hiển thị mọi đơn hàng, kể cả đơn chưa được gắn với khách”**, phép nối chỉ lấy những hàng khớp sẽ bỏ sót thông tin quan trọng.

Đó là lý do SQL có **`LEFT JOIN`** và **`RIGHT JOIN`** — hai dạng **outer join** giúp giữ lại các hàng của một phía ngay cả khi không tìm thấy đối tác ở phía kia. Các cột của phía thiếu đối tác được điền bằng `NULL` trong kết quả. Đây là công cụ rất thường gặp trong báo cáo, đối soát dữ liệu, tìm bản ghi thiếu quan hệ và xây dựng danh sách cần hiện cả những mục có số lượng bằng 0.

Bài học này giải thích ý nghĩa của từng dạng nối, cách nhận biết hàng **không khớp**, sự khác nhau giữa đặt điều kiện trong `ON` và `WHERE`, ảnh hưởng của `NULL` và cách dùng outer join để thống kê chính xác. Ví dụ dùng PostgreSQL; cú pháp cơ bản của `LEFT JOIN` và `RIGHT JOIN` cũng được nhiều hệ quản trị quan hệ hỗ trợ.

## 1. Vì sao cần giữ hàng không khớp?

Giả sử hệ thống có bốn khách hàng: **An, Binh, Chi, Dung**. Chỉ ba người đầu có đơn; Dung chưa đặt đơn nào. Đồng thời, hệ thống có một đơn đang chờ xác định khách hàng, nên cột `customer_id` của đơn đó là `NULL`.

Có ít nhất ba nhu cầu khác nhau:

1. **Danh sách đơn đã có khách**: chỉ lấy những cặp khách–đơn khớp nhau.
2. **Danh sách đầy đủ khách**: giữ cả **Dung**, dù không có đơn.
3. **Danh sách đầy đủ đơn**: giữ cả đơn chưa xác định khách.

Mỗi câu hỏi chọn một tập hàng phải được **giữ lại**. Không thể đổi tên phép nối tùy ý mà không thay đổi kết quả.

| Phép nối | Hàng nào được giữ? | Hàng không khớp được thể hiện thế nào? |
|---|---|---|
| `INNER JOIN` | Chỉ các cặp hàng thỏa điều kiện `ON` | Hàng không khớp bị loại |
| `LEFT JOIN` | **Mọi hàng phía trái** và những hàng phía phải khớp | Nếu không khớp, cột phía phải là `NULL` |
| `RIGHT JOIN` | **Mọi hàng phía phải** và những hàng phía trái khớp | Nếu không khớp, cột phía trái là `NULL` |
| `FULL OUTER JOIN` | Hàng khớp và hàng không khớp ở **cả hai phía** | Phía thiếu đối tác là `NULL` |

**“Bên trái” và “bên phải” là vị trí bảng trong câu SQL**, không phải tên bảng, ý nghĩa bảng cha/con, khóa chính/khóa ngoại hay vị trí trên giao diện. Nếu đổi thứ tự hai bảng, phía được giữ cũng có thể thay đổi.

## 2. Tạo bộ dữ liệu mẫu có cả trường hợp khớp và không khớp

Thực hiện các lệnh sau trong một **cơ sở dữ liệu thực hành riêng**. Không chạy trên bảng chứa dữ liệu sản xuất.

```sql
CREATE TABLE customers (
    customer_id INTEGER PRIMARY KEY,
    customer_name VARCHAR(80) NOT NULL,
    city VARCHAR(40)
);

CREATE TABLE orders (
    order_id INTEGER PRIMARY KEY,
    customer_id INTEGER REFERENCES customers(customer_id),
    status VARCHAR(20) NOT NULL
        CHECK (status IN ('NEW', 'PAID', 'CANCELLED')),
    order_amount NUMERIC(12, 2) NOT NULL CHECK (order_amount >= 0)
);

INSERT INTO customers (customer_id, customer_name, city)
VALUES
    (1, 'An',   'Ha Noi'),
    (2, 'Binh', 'TP HCM'),
    (3, 'Chi',  'Da Nang'),
    (4, 'Dung', 'Ha Noi');

INSERT INTO orders (order_id, customer_id, status, order_amount)
VALUES
    (101, 1,    'PAID',      120000.00),
    (102, 1,    'NEW',        50000.00),
    (103, 2,    'PAID',      200000.00),
    (104, NULL, 'NEW',        80000.00),
    (105, 3,    'CANCELLED',  90000.00);
```

Chú ý thiết kế:

- `customers.customer_id` là **khóa chính**, không được `NULL`.
- `orders.order_id` là **khóa chính**, không được `NULL`.
- `orders.customer_id` là **khóa ngoại có thể `NULL`**: nếu có giá trị, nó phải tham chiếu khách tồn tại; nếu `NULL`, đơn được phép chưa gắn khách trong mô hình thực hành.
- Vì có khóa ngoại, ta không thể tùy tiện thêm một đơn với `customer_id = 999` khi khách 999 chưa tồn tại. Đơn 104 dùng `NULL` để minh họa tình huống chưa gắn khách mà vẫn tuân thủ ràng buộc.

**Bảng `customers`:**

| customer_id | customer_name | city |
|---:|---|---|
| 1 | An | Ha Noi |
| 2 | Binh | TP HCM |
| 3 | Chi | Da Nang |
| 4 | Dung | Ha Noi |

**Bảng `orders`:**

| order_id | customer_id | status | order_amount |
|---:|---:|---|---:|
| 101 | 1 | PAID | 120000.00 |
| 102 | 1 | NEW | 50000.00 |
| 103 | 2 | PAID | 200000.00 |
| 104 | `NULL` | NEW | 80000.00 |
| 105 | 3 | CANCELLED | 90000.00 |

Ta sẽ dùng cùng bộ dữ liệu xuyên suốt. Có **4 khách** và **5 đơn**:

- An có hai đơn: 101, 102.
- Binh có một đơn: 103.
- Chi có một đơn: 105.
- Dung **không có đơn**.
- Đơn 104 **không có mã khách được xác định**.

Điểm quan trọng là **không khớp có thể xảy ra từ cả hai phía**: một khách không có đơn và một đơn không có khách. Nhờ vậy, `LEFT JOIN` và `RIGHT JOIN` sẽ thể hiện rõ sự khác nhau.

## 3. Bước đối chiếu: INNER JOIN chỉ lấy các cặp khớp

Trước khi dùng outer join, hãy xem phép nối trong:

```sql
SELECT
    c.customer_id,
    c.customer_name,
    o.order_id,
    o.status
FROM customers AS c
INNER JOIN orders AS o
    ON o.customer_id = c.customer_id
ORDER BY c.customer_id, o.order_id;
```

Kết quả:

| customer_id | customer_name | order_id | status |
|---:|---|---:|---|
| 1 | An | 101 | PAID |
| 1 | An | 102 | NEW |
| 2 | Binh | 103 | PAID |
| 3 | Chi | 105 | CANCELLED |

Chỉ có **4 hàng ghép thành công**:

- Khách **Dung** không xuất hiện vì không có đơn nào tham chiếu mã 4.
- Đơn **104** không xuất hiện vì không có `customer_id` nào để khớp với bảng khách.
- Khách **An** xuất hiện hai lần, vì có hai đơn hợp lệ.

Đừng đồng nhất “số hàng sau JOIN” với “số khách”. `JOIN` có thể tạo nhiều hàng cho một khách khi quan hệ là **một-nhiều**.

## 4. LEFT JOIN: giữ toàn bộ hàng bên trái

### 4.1. Cú pháp và ý nghĩa

```sql
SELECT ...
FROM bang_trai AS l
LEFT JOIN bang_phai AS r
    ON dieu_kien_ghep;
```

`LEFT JOIN` (cũng có thể viết `LEFT OUTER JOIN`) giữ tất cả hàng thuộc **`bang_trai`**:

- Nếu một hàng bên trái khớp **một** hàng bên phải, kết quả có một cặp.
- Nếu khớp **nhiều** hàng bên phải, kết quả có **nhiều** hàng ứng với cùng hàng trái.
- Nếu **không khớp bất kỳ** hàng bên phải nào, kết quả vẫn có **một hàng**, trong đó các cột thuộc phía phải là `NULL`.

Sơ đồ khái niệm:

```text
customers (trái)              orders (phải)
1 An   ─────────────────────── 101
    └───────────────────────── 102
2 Binh ─────────────────────── 103
3 Chi  ─────────────────────── 105
4 Dung ──────────────── không có đơn khớp
                             104 (không có customer_id)

LEFT JOIN giữ các khách 1, 2, 3, 4.
Dung → được giữ với các cột của orders = NULL.
Đơn 104 → không được giữ vì nằm ở phía phải và không khớp.
```

### 4.2. Ví dụ: hiển thị mọi khách và đơn của họ

```sql
SELECT
    c.customer_id,
    c.customer_name,
    o.order_id,
    o.status
FROM customers AS c
LEFT JOIN orders AS o
    ON o.customer_id = c.customer_id
ORDER BY c.customer_id, o.order_id;
```

| customer_id | customer_name | order_id | status |
|---:|---|---:|---|
| 1 | An | 101 | PAID |
| 1 | An | 102 | NEW |
| 2 | Binh | 103 | PAID |
| 3 | Chi | 105 | CANCELLED |
| 4 | Dung | `NULL` | `NULL` |

So với `INNER JOIN`, kết quả có thêm **một hàng của Dung**, dù khách này không có đơn. Ở hàng đó, `order_id` và `status` được điền `NULL` do không có hàng tương ứng từ bảng `orders`.

**Hai điều cần ghi nhớ:**

1. `LEFT JOIN` **không có nghĩa kết quả luôn có đúng số hàng của bảng trái**. An có hai đơn nên xuất hiện hai hàng. Phép nối chỉ cam kết **không bỏ hàng trái vì thiếu đối tác**, chứ không ngăn việc nhân hàng do nhiều đối tác.
2. `LEFT JOIN` **không giữ mọi hàng bên phải**. Đơn 104 không có khách nên không xuất hiện ở truy vấn trên. Nếu cần giữ mọi đơn, phải chọn phía được bảo toàn khác.

### 4.3. LEFT JOIN và thứ tự bảng

Trong biểu thức:

```sql
FROM customers AS c
LEFT JOIN orders AS o ON o.customer_id = c.customer_id
```

`customers` là phía trái và được giữ toàn bộ. Nhưng khi đảo thành:

```sql
FROM orders AS o
LEFT JOIN customers AS c ON c.customer_id = o.customer_id
```

thì **`orders` mới là phía trái**, nên mọi đơn được giữ, bao gồm đơn 104 chưa có khách. Hai câu SQL đều dùng từ khóa `LEFT JOIN` nhưng **không tương đương về tập hàng được giữ**.

## 5. RIGHT JOIN: giữ toàn bộ hàng bên phải

### 5.1. Cú pháp và ý nghĩa

```sql
SELECT ...
FROM bang_trai AS l
RIGHT JOIN bang_phai AS r
    ON dieu_kien_ghep;
```

`RIGHT JOIN` (cũng có thể viết `RIGHT OUTER JOIN`) giữ tất cả hàng thuộc **`bang_phai`**. Khi một hàng bên phải không có đối tác, các cột phía trái được bổ sung `NULL`.

Ví dụ: “Hiển thị **mọi đơn hàng**, kèm thông tin khách nếu có”:

```sql
SELECT
    o.order_id,
    o.customer_id AS order_customer_id,
    c.customer_name,
    o.status
FROM customers AS c
RIGHT JOIN orders AS o
    ON c.customer_id = o.customer_id
ORDER BY o.order_id;
```

Kết quả:

| order_id | order_customer_id | customer_name | status |
|---:|---:|---|---|
| 101 | 1 | An | PAID |
| 102 | 1 | An | NEW |
| 103 | 2 | Binh | PAID |
| 104 | `NULL` | `NULL` | NEW |
| 105 | 3 | Chi | CANCELLED |

Đơn **104** vẫn hiện diện do bảng `orders` nằm **bên phải** và được giữ lại. Trong hàng kết quả của đơn này, thông tin khách `c.customer_name` là `NULL` vì không có khách khớp. Khách **Dung** không xuất hiện vì nằm ở phía trái, không có đơn nào tham chiếu.

So sánh ngắn gọn:

| Câu SQL | Phía được giữ | Kết quả cần chú ý |
|---|---|---|
| `customers LEFT JOIN orders` | Mọi khách | Có Dung; không có đơn 104 |
| `customers RIGHT JOIN orders` | Mọi đơn | Có đơn 104; không có Dung |
| `orders LEFT JOIN customers` | Mọi đơn | Có đơn 104; không có Dung |

### 5.2. Có thể viết lại RIGHT JOIN thành LEFT JOIN

Với một phép nối hai bảng, ta có thể **đảo hai phía** để viết dạng `LEFT JOIN` dễ theo dõi hơn:

```sql
-- Cách A: RIGHT JOIN, giữ mọi đơn (bảng bên phải).
SELECT o.order_id, c.customer_name
FROM customers AS c
RIGHT JOIN orders AS o
    ON c.customer_id = o.customer_id
ORDER BY o.order_id;

-- Cách B: LEFT JOIN tương đương, giữ mọi đơn (bảng bên trái).
SELECT o.order_id, c.customer_name
FROM orders AS o
LEFT JOIN customers AS c
    ON c.customer_id = o.customer_id
ORDER BY o.order_id;
```

Cả hai đều trả các đơn 101, 102, 103, 104, 105; khách của đơn 104 là `NULL`. Đối với **một phép nối hai bảng** và điều kiện ghép tương ứng, chúng biểu đạt cùng quan hệ kết quả sau khi sắp lại thứ tự các cột chọn.

Trong truy vấn có **nhiều phép nối và điều kiện phức tạp**, không nên đảo thứ tự bảng máy móc vì vị trí ghép, cách nhóm các phép nối và mệnh đề lọc có thể ảnh hưởng ngữ nghĩa. Khi viết lại, cần giữ đúng điều kiện `ON` và phạm vi của các bộ lọc.

Vì `LEFT JOIN` được nhiều người đọc thuận mắt từ trái qua phải, có thể ưu tiên đặt **bảng bắt buộc giữ đủ hàng** ngay sau `FROM` rồi dùng `LEFT JOIN` để nối thông tin bổ sung. Tuy vậy, `RIGHT JOIN` vẫn là cú pháp hữu ích khi bảng cần giữ đủ hàng đã nằm ở phía phải trong cách trình bày.

## 6. Ba trạng thái của cặp ghép: khớp, không khớp và NULL

Điều kiện ghép điển hình:

```sql
ON c.customer_id = o.customer_id
```

Đối với những giá trị đã biết, hai ID bằng nhau thì điều kiện là `TRUE`. Nhưng với `NULL`, logic SQL có **ba giá trị**: `TRUE`, `FALSE` và `UNKNOWN`.

| Biểu thức | Kết quả logic |
|---|---|
| `1 = 1` | `TRUE` |
| `1 = 2` | `FALSE` |
| `1 = NULL` | `UNKNOWN` |
| `NULL = NULL` | `UNKNOWN` |
| `NULL IS NULL` | `TRUE` |

Trong `JOIN ... ON` thông thường, **chỉ cặp hàng có điều kiện `TRUE` được coi là khớp**. Điều kiện `FALSE` hoặc `UNKNOWN` không tạo cặp ghép. Vì vậy đơn 104 có `customer_id = NULL` không khớp khách nào bằng phép `=`.

### 6.1. NULL do dữ liệu gốc khác NULL do outer join bổ sung

Trong các ví dụ, có hai hiện tượng khác nhau:

- **`orders.customer_id` của đơn 104 vốn là `NULL` trong bảng nguồn**. Đây là dữ liệu “chưa có khách được xác định”.
- **`orders.order_id` trong hàng kết quả cho Dung khi dùng `customers LEFT JOIN orders` là `NULL` do phép nối bổ sung**. Đây là dấu hiệu không có bản ghi đơn phù hợp.

Phân biệt nguồn gốc `NULL` rất quan trọng khi giải thích báo cáo. Một ô thiếu giá trị **không phải lúc nào cũng có nghĩa không tồn tại bản ghi ở phía nối**: có thể bản ghi tồn tại nhưng chính cột đó được phép `NULL`.

### 6.2. Kiểm tra hàng không khớp bằng cột không thể NULL

Để xác định khách không có đơn, dùng:

```sql
SELECT
    c.customer_id,
    c.customer_name
FROM customers AS c
LEFT JOIN orders AS o
    ON o.customer_id = c.customer_id
WHERE o.order_id IS NULL
ORDER BY c.customer_id;
```

Kết quả: **khách 4 — Dung**.

`orders.order_id` là **khóa chính `NOT NULL`**, nên một đơn tồn tại thật không thể có `o.order_id = NULL`. Trong kết quả `LEFT JOIN`, giá trị đó bằng `NULL` chỉ khi **không có đơn khớp**.

Đối với phép nối từ đơn sang khách, tìm những đơn không có khách khớp:

```sql
SELECT o.order_id, o.customer_id, o.status
FROM customers AS c
RIGHT JOIN orders AS o
    ON c.customer_id = o.customer_id
WHERE c.customer_id IS NULL
ORDER BY o.order_id;
-- order_id: 104
```

Ở đây `c.customer_id` là **khóa chính không `NULL` của bảng khách**, nên việc nó bị `NULL` trong kết quả nối cho biết **không có khách khớp**.

Không thay điều kiện trên bằng một cột phía còn lại **vốn có thể `NULL` ngay cả khi hàng tồn tại**, nếu mục tiêu là nhận diện hàng hoàn toàn không khớp.

## 7. Bộ lọc trong ON và WHERE: khác nhau khi có outer join

Đây là điểm rất dễ tạo lỗi trong truy vấn có `LEFT JOIN` và `RIGHT JOIN`. Phép nối và bộ lọc hoạt động ở **hai giai đoạn logic**:

- **`ON`:** quyết định **những cặp hàng nào đủ điều kiện ghép**; phép outer join vẫn giữ phía được bảo toàn khi không có cặp ghép.
- **`WHERE`:** lọc **các hàng trong kết quả sau nối**; hàng chỉ được giữ khi điều kiện `WHERE` là `TRUE`. `FALSE` và `UNKNOWN` đều bị loại.

### 7.1. Bài toán: mọi khách, kèm đơn đã thanh toán nếu có

Đặt điều kiện trạng thái trong `ON`:

```sql
SELECT
    c.customer_id,
    c.customer_name,
    o.order_id,
    o.status
FROM customers AS c
LEFT JOIN orders AS o
    ON o.customer_id = c.customer_id
   AND o.status = 'PAID'
ORDER BY c.customer_id, o.order_id;
```

| customer_id | customer_name | order_id | status |
|---:|---|---:|---|
| 1 | An | 101 | PAID |
| 2 | Binh | 103 | PAID |
| 3 | Chi | `NULL` | `NULL` |
| 4 | Dung | `NULL` | `NULL` |

Ở đây **cả bốn khách đều được giữ**:

- An có đơn `PAID` 101; đơn `NEW` 102 không đủ điều kiện ghép.
- Binh có đơn `PAID` 103.
- Chi có đơn 105 nhưng trạng thái `CANCELLED`, nên **không có đơn `PAID` khớp điều kiện `ON`**; các cột đơn trong kết quả là `NULL`.
- Dung không có đơn nào, nên cũng có các cột đơn `NULL`.

**Chi vẫn xuất hiện** dù có đơn không phải `PAID`, bởi khách là phía trái được bảo toàn. Câu SQL này đáp ứng yêu cầu **“mọi khách, kèm đơn đã thanh toán nếu có”**.

### 7.2. Chuyển điều kiện trạng thái sang WHERE

Xét câu gần giống:

```sql
SELECT
    c.customer_id,
    c.customer_name,
    o.order_id,
    o.status
FROM customers AS c
LEFT JOIN orders AS o
    ON o.customer_id = c.customer_id
WHERE o.status = 'PAID'
ORDER BY c.customer_id, o.order_id;
```

Kết quả chỉ còn:

| customer_id | customer_name | order_id | status |
|---:|---|---:|---|
| 1 | An | 101 | PAID |
| 2 | Binh | 103 | PAID |

Vì sao Chi và Dung biến mất?

1. Phép `LEFT JOIN` ban đầu ghép **mọi đơn** của từng khách và tạo hàng `NULL` cho Dung.
2. `WHERE o.status = 'PAID'` chỉ giữ những hàng có trạng thái `PAID`.
3. Với hàng của Chi, `'CANCELLED' = 'PAID'` là `FALSE`.
4. Với hàng bổ sung của Dung, `NULL = 'PAID'` là `UNKNOWN`.
5. `WHERE` loại cả `FALSE` lẫn `UNKNOWN`.

Với điều kiện `WHERE` này, lợi ích “giữ mọi khách” của `LEFT JOIN` đã bị loại bỏ đối với các khách không có đơn `PAID`. Truy vấn có tác dụng gần giống `INNER JOIN` kèm bộ lọc trạng thái cho yêu cầu hiện tại.

### 7.3. Thêm OR IS NULL vào WHERE có thay được lọc trong ON không?

Người mới học đôi khi thử:

```sql
SELECT
    c.customer_id,
    c.customer_name,
    o.order_id,
    o.status
FROM customers AS c
LEFT JOIN orders AS o
    ON o.customer_id = c.customer_id
WHERE o.status = 'PAID'
   OR o.order_id IS NULL
ORDER BY c.customer_id, o.order_id;
```

Kết quả: **An với 101; Binh với 103; Dung với `NULL`**. **Chi vẫn không xuất hiện**.

Chi **đã có một hàng ghép** với đơn 105. Vì thế `LEFT JOIN` không tạo thêm một hàng “không có đơn” cho Chi. Sau đó `WHERE` loại hàng `CANCELLED`. Điều kiện `OR o.order_id IS NULL` không thể tạo lại hàng đã bị loại.

Đây là minh chứng rằng:

```sql
LEFT JOIN ... ON key_equal AND condition_on_right
```

**không tương đương nói chung** với:

```sql
LEFT JOIN ... ON key_equal
WHERE condition_on_right OR right_key IS NULL
```

Khi muốn giữ **mọi hàng trái**, hãy để tiêu chí chọn đối tác bên phải trong `ON` hoặc tổng hợp/lọc phía phải trước rồi mới outer join.

### 7.4. Bộ lọc ở phía được bảo toàn

Giả sử chỉ muốn khách ở `Ha Noi`, nhưng vẫn giữ những khách ấy dù không có đơn:

```sql
SELECT
    c.customer_id,
    c.customer_name,
    o.order_id
FROM customers AS c
LEFT JOIN orders AS o
    ON o.customer_id = c.customer_id
WHERE c.city = 'Ha Noi'
ORDER BY c.customer_id, o.order_id;
```

Kết quả gồm **An** với đơn 101, 102 và **Dung** không có đơn. Điều kiện `WHERE c.city = 'Ha Noi'` chọn **những khách mà ta muốn giữ**; nó không phụ thuộc sự tồn tại của bản ghi phía phải.

Nếu đặt cùng điều kiện đó trong `ON` mà không thêm `WHERE`, các khách **không ở Ha Noi** vẫn được giữ với cột đơn `NULL`, vì khách là phía trái của `LEFT JOIN`. Đây lại là câu hỏi khác: “hiển thị mọi khách, chỉ nối đơn cho khách ở Ha Noi”.

## 8. RIGHT JOIN với ON và WHERE cũng cần phân biệt

Quy tắc hoàn toàn đối xứng: `RIGHT JOIN` giữ **phía phải**, nên điều kiện trong `WHERE` trên cột của **phía trái không được bảo toàn** có thể làm mất những hàng phải không khớp.

Yêu cầu: **“Mọi đơn, kèm tên khách tại Ha Noi nếu có.”** Có thể viết:

```sql
SELECT
    o.order_id,
    o.status,
    c.customer_name
FROM customers AS c
RIGHT JOIN orders AS o
    ON c.customer_id = o.customer_id
   AND c.city = 'Ha Noi'
ORDER BY o.order_id;
```

Kết quả:

| order_id | status | customer_name |
|---:|---|---|
| 101 | PAID | An |
| 102 | NEW | An |
| 103 | PAID | `NULL` |
| 104 | NEW | `NULL` |
| 105 | CANCELLED | `NULL` |

Mọi đơn đều được giữ:

- Đơn 101, 102 thuộc An ở Ha Noi, nên có tên khách.
- Đơn 103 thuộc Binh ở TP HCM và đơn 105 thuộc Chi ở Da Nang, **không thỏa điều kiện thành phố trong `ON`** nên cột khách được bổ sung `NULL`.
- Đơn 104 chưa xác định khách, nên không có đối tác.

Nếu chuyển `c.city = 'Ha Noi'` sang `WHERE`, chỉ còn đơn **101 và 102**. Các đơn khác bị loại vì thành phố không phải Ha Noi hoặc giá trị từ phía khách là `NULL`. Do đó **bảng phải được giữ ở giai đoạn nối không có nghĩa kết quả cuối cùng luôn giữ đủ các hàng đó sau `WHERE`**.

## 9. Tìm những bản ghi thiếu quan hệ: anti-join

Một nhu cầu phổ biến là tìm những hàng ở một phía **không có bất kỳ hàng nào khớp phía còn lại**. Mẫu này thường gọi là **anti-join**; nó có thể được diễn đạt bằng outer join kết hợp `IS NULL` hoặc bằng `NOT EXISTS`.

### 9.1. Tìm khách chưa đặt đơn

```sql
SELECT c.customer_id, c.customer_name
FROM customers AS c
LEFT JOIN orders AS o
    ON o.customer_id = c.customer_id
WHERE o.order_id IS NULL
ORDER BY c.customer_id;
-- Dung (customer_id = 4)
```

Ta chọn `o.order_id IS NULL` vì `order_id` là khóa chính `NOT NULL` của bảng **đối tác phía phải**. Đây là dấu hiệu tin cậy rằng hàng đơn **không tồn tại trong kết quả ghép**.

Một cách khác, thường dễ diễn đạt mục đích “không tồn tại”:

```sql
SELECT c.customer_id, c.customer_name
FROM customers AS c
WHERE NOT EXISTS (
    SELECT 1
    FROM orders AS o
    WHERE o.customer_id = c.customer_id
)
ORDER BY c.customer_id;
-- Dung
```

`NOT EXISTS` chỉ kiểm tra xem có hàng tương ứng hay không, không tạo các hàng nhân lên do một khách có nhiều đơn. Nó đặc biệt hữu ích trong truy vấn kiểm tra quan hệ và với dữ liệu có khóa phụ có thể `NULL`.

### 9.2. Tìm khách chưa có đơn PAID

Khách **Chi** có đơn nhưng chưa có đơn `PAID`; **Dung** chưa có đơn nào. Muốn lấy **cả hai**, điều kiện xác định đơn đủ điều kiện phải nằm trong `ON`:

```sql
SELECT c.customer_id, c.customer_name
FROM customers AS c
LEFT JOIN orders AS o
    ON o.customer_id = c.customer_id
   AND o.status = 'PAID'
WHERE o.order_id IS NULL
ORDER BY c.customer_id;
-- Chi, Dung
```

Lưu ý sự khác nhau giữa:

- **Không có đơn nào** → chỉ **Dung**.
- **Không có đơn đã thanh toán** → **Chi và Dung**.

Chúng là hai ý nghĩa nghiệp vụ khác nhau. `LEFT JOIN` cho phép biểu diễn cả hai bằng cách thay **điều kiện ghép**.

### 9.3. Tìm đơn chưa có khách khớp

Để tìm các đơn có khách thiếu, dùng `RIGHT JOIN` hoặc viết lại thành `LEFT JOIN`:

```sql
-- RIGHT JOIN: giữ mọi đơn ở phía phải.
SELECT o.order_id, o.customer_id
FROM customers AS c
RIGHT JOIN orders AS o
    ON c.customer_id = o.customer_id
WHERE c.customer_id IS NULL
ORDER BY o.order_id;
-- 104

-- Cách viết tương đương bằng LEFT JOIN:
SELECT o.order_id, o.customer_id
FROM orders AS o
LEFT JOIN customers AS c
    ON c.customer_id = o.customer_id
WHERE c.customer_id IS NULL
ORDER BY o.order_id;
-- 104
```

Trong dữ liệu này, đơn 104 có `orders.customer_id = NULL`. Ở một hệ thống nhập liệu chưa áp khóa ngoại, một mã khách **không tồn tại** cũng có thể gây “không khớp”. Khi đã có khóa ngoại hợp lệ như ví dụ, giá trị mã khách **không `NULL` nhưng không tồn tại** thường bị DBMS từ chối ngay khi ghi.

### 9.4. Cẩn thận với NOT IN khi tập con chứa NULL

Một truy vấn trông giống anti-join:

```sql
SELECT customer_id, customer_name
FROM customers
WHERE customer_id NOT IN (
    SELECT customer_id
    FROM orders
);
```

Nhưng truy vấn con chứa một `customer_id = NULL` của đơn 104. Biểu thức `NOT IN` có thể trả `UNKNOWN` cho khách không trùng bất kỳ ID đã biết nào, khiến khách **Dung không được chọn**.

Với nhu cầu “không tồn tại bản ghi liên quan”, `NOT EXISTS` thường làm ý định rõ ràng và tránh bẫy `NULL` này. Nếu dùng `NOT IN`, phải hiểu rõ giá trị `NULL` ở cả hai phía và điều kiện lọc của truy vấn con.

## 10. Tổng hợp qua LEFT JOIN: COUNT(*), COUNT(cột) và SUM

Khi giữ tất cả khách và tính số đơn, `LEFT JOIN` rất phù hợp. Tuy nhiên, cần chọn hàm tổng hợp theo đúng **mỗi hàng kết quả đại diện cho gì**.

### 10.1. COUNT(*) có thể khiến khách không có đơn được đếm là 1

```sql
SELECT
    c.customer_id,
    c.customer_name,
    COUNT(*) AS joined_rows,
    COUNT(o.order_id) AS order_count
FROM customers AS c
LEFT JOIN orders AS o
    ON o.customer_id = c.customer_id
GROUP BY c.customer_id, c.customer_name
ORDER BY c.customer_id;
```

| customer_id | customer_name | joined_rows | order_count |
|---:|---|---:|---:|
| 1 | An | 2 | 2 |
| 2 | Binh | 1 | 1 |
| 3 | Chi | 1 | 1 |
| 4 | Dung | 1 | 0 |

`COUNT(*)` đếm mọi hàng **sau outer join**. Dung vẫn có một hàng bổ sung với cột đơn `NULL`, nên `COUNT(*) = 1`.

`COUNT(o.order_id)` chỉ đếm các giá trị `o.order_id` **khác `NULL`**, nên trả **0** cho Dung. Vì `orders.order_id` là khóa chính `NOT NULL`, nó phản ánh đúng số đơn được nối trong ví dụ.

Khi muốn **mỗi khách một hàng với số đơn đúng, kể cả 0**, truy vấn có thể viết gọn:

```sql
SELECT
    c.customer_id,
    c.customer_name,
    COUNT(o.order_id) AS order_count
FROM customers AS c
LEFT JOIN orders AS o ON o.customer_id = c.customer_id
GROUP BY c.customer_id, c.customer_name
ORDER BY c.customer_id;
```

### 10.2. SUM qua outer join và COALESCE

Muốn tổng giá trị đơn của mỗi khách:

```sql
SELECT
    c.customer_id,
    c.customer_name,
    COALESCE(SUM(o.order_amount), 0) AS total_order_amount
FROM customers AS c
LEFT JOIN orders AS o ON o.customer_id = c.customer_id
GROUP BY c.customer_id, c.customer_name
ORDER BY c.customer_id;
```

| customer_id | customer_name | total_order_amount |
|---:|---|---:|
| 1 | An | 170000.00 |
| 2 | Binh | 200000.00 |
| 3 | Chi | 90000.00 |
| 4 | Dung | 0 |

Giải thích:

- An: 120.000 + 50.000 = **170.000**.
- Binh: **200.000**.
- Chi: **90.000**.
- Dung: không có đơn khớp, nên `SUM(o.order_amount)` trả `NULL`; `COALESCE(..., 0)` hiển thị 0.

Tổng trong báo cáo khách này là **460.000**, không phải tổng 540.000 của cả bảng `orders`, vì đơn 104 không gắn với khách nên **không xuất hiện trong phép `customers LEFT JOIN orders`**. Nếu nghiệp vụ cần đối soát **mọi đơn**, phải tính đến cả đơn chưa có khách thay vì chỉ dựa trên danh sách khách.

Chú ý: truy vấn trên cộng **mọi trạng thái**, kể cả `NEW` và `CANCELLED`. Nếu yêu cầu là tổng tiền đơn **`PAID`**, điều kiện trạng thái cần được áp đúng phạm vi:

```sql
SELECT
    c.customer_id,
    c.customer_name,
    COALESCE(SUM(o.order_amount), 0) AS paid_amount
FROM customers AS c
LEFT JOIN orders AS o
    ON o.customer_id = c.customer_id
   AND o.status = 'PAID'
GROUP BY c.customer_id, c.customer_name
ORDER BY c.customer_id;
```

Kết quả: **An 120.000; Binh 200.000; Chi 0; Dung 0**. Điều kiện `o.status = 'PAID'` nằm trong `ON` để vẫn giữ mọi khách.

### 10.3. JOIN có thể làm nhân hàng

Trong bộ dữ liệu mẫu, An có hai đơn nên `LEFT JOIN` tạo hai hàng cho An. Nếu sau này nối thêm một bảng `order_items` có nhiều sản phẩm trong mỗi đơn, kết quả có thể tăng lên thành **một hàng mỗi dòng sản phẩm**, không còn một hàng mỗi đơn.

Khi đó:

- `COUNT(o.order_id)` có thể **đếm lặp** mỗi đơn theo số dòng sản phẩm.
- `SUM(o.order_amount)` có thể **cộng lặp** toàn bộ tiền đơn theo số dòng.
- `COUNT(DISTINCT o.order_id)` có thể xử lý nhu cầu **đếm số đơn duy nhất**.
- Để cộng tiền đơn chính xác, thường nên **tổng hợp các nhánh một-nhiều về đúng mức chi tiết** trước khi nối, hoặc chỉ cộng trên một tập một hàng mỗi đơn.

**Không dùng `SUM(DISTINCT order_amount)` để chữa mọi lỗi nhân tiền.** Hai đơn khác nhau có thể cùng tổng tiền; `SUM(DISTINCT ...)` sẽ loại một giá trị tiền lặp dù đó là hai đơn hợp lệ.

## 11. FULL OUTER JOIN: đối chiếu cả hai phía không khớp

Mặc dù trọng tâm là `LEFT JOIN` và `RIGHT JOIN`, `FULL OUTER JOIN` giúp làm rõ bức tranh:

```sql
SELECT
    c.customer_id,
    c.customer_name,
    o.order_id,
    o.status
FROM customers AS c
FULL OUTER JOIN orders AS o
    ON c.customer_id = o.customer_id
ORDER BY c.customer_id NULLS LAST, o.order_id;
```

Kết quả với PostgreSQL:

| customer_id | customer_name | order_id | status |
|---:|---|---:|---|
| 1 | An | 101 | PAID |
| 1 | An | 102 | NEW |
| 2 | Binh | 103 | PAID |
| 3 | Chi | 105 | CANCELLED |
| 4 | Dung | `NULL` | `NULL` |
| `NULL` | `NULL` | 104 | NEW |

Có **6 hàng**:

- **4** cặp có khách và đơn khớp.
- **1** khách không có đơn (Dung).
- **1** đơn không có khách (104).

`FULL OUTER JOIN` giữ cả **hàng trái không khớp** lẫn **hàng phải không khớp**. Nó hữu ích trong đối soát hai tập dữ liệu — ví dụ danh sách chứng từ bên hệ thống A và hệ thống B — để xem những mục chỉ có ở A, chỉ có ở B hoặc có ở cả hai.

Một phép `LEFT JOIN` riêng lẻ chỉ giữ trọn **phía trái**; một phép `RIGHT JOIN` riêng lẻ chỉ giữ trọn **phía phải**. `FULL OUTER JOIN` giữ trọn **cả hai**.

Không phải mọi DBMS đều hỗ trợ `FULL OUTER JOIN` trực tiếp. Ví dụ PostgreSQL và SQL Server có hỗ trợ; MySQL thường cần mô phỏng bằng phép nối và `UNION ALL` với điều kiện loại các hàng đã khớp. Khi mô phỏng, phải xử lý **hàng trùng hợp lệ** và điều kiện không khớp cẩn thận; không nên mặc định một `UNION` thông thường tương đương với mọi tình huống dữ liệu.

## 12. LEFT JOIN và RIGHT JOIN có “giữ nguyên” thứ tự dữ liệu không?

Không. Từ **“giữ”** trong outer join nghĩa là **không bỏ mất hàng của phía được bảo toàn vì thiếu đối tác**, không có nghĩa bảo toàn **thứ tự vật lý** trong bảng.

Ví dụ:

```sql
SELECT c.customer_name, o.order_id
FROM customers AS c
LEFT JOIN orders AS o ON o.customer_id = c.customer_id;
```

Không có `ORDER BY` nên SQL **không bảo đảm thứ tự các hàng được trả về**, dù khi thử dữ liệu nhỏ có thể thấy chúng gần giống thứ tự chèn.

Nếu cần sắp theo khách và đơn:

```sql
SELECT c.customer_id, c.customer_name, o.order_id
FROM customers AS c
LEFT JOIN orders AS o ON o.customer_id = c.customer_id
ORDER BY c.customer_id, o.order_id;
```

Nếu muốn đơn mới trước mà vẫn giữ khách không có đơn, hãy dùng tiêu chí sắp xếp tường minh và xác định cách xử lý `NULL` theo DBMS. Trong PostgreSQL có thể dùng `NULLS FIRST`/`NULLS LAST`. `ORDER BY` chỉ sắp thứ tự kết quả, **không thay đổi phía được giữ của phép nối**.

## 13. Khi nào nên dùng LEFT JOIN, RIGHT JOIN, INNER JOIN hoặc NOT EXISTS?

Trước khi viết truy vấn, hãy quyết định **đối tượng nào phải xuất hiện dù không có dữ liệu liên quan**.

| Yêu cầu nghiệp vụ | Cách viết phù hợp | Lý do |
|---|---|---|
| Chỉ các cặp khách–đơn đã gắn nhau | `INNER JOIN` | Không cần hàng thiếu đối tác |
| **Tất cả khách**, có đơn thì hiện | `customers LEFT JOIN orders` | Giữ mọi khách, kể cả Dung |
| **Tất cả đơn**, có khách thì hiện | `customers RIGHT JOIN orders` hoặc `orders LEFT JOIN customers` | Giữ mọi đơn, kể cả 104 |
| Khách **không có đơn** | `LEFT JOIN ... WHERE o.order_id IS NULL` hoặc `NOT EXISTS` | Kiểm tra không tồn tại quan hệ |
| Khách **không có đơn PAID** | `LEFT JOIN` lọc `PAID` trong `ON` rồi `WHERE o.order_id IS NULL` | Phân biệt không có đơn PAID với không có đơn nào |
| Mọi khách và số đơn, kể cả 0 | `LEFT JOIN` + `COUNT(o.order_id)` + `GROUP BY` | Tránh `COUNT(*) = 1` cho khách chưa có đơn |
| Mọi khách và tổng tiền PAID, kể cả 0 | `LEFT JOIN` với `status = 'PAID'` trong `ON`, rồi `COALESCE(SUM(...), 0)` | Giữ khách không phát sinh đơn PAID |
| Đối soát mục chỉ có ở mỗi phía | `FULL OUTER JOIN` nếu DBMS hỗ trợ | Giữ hai phía không khớp |

Một thói quen hữu ích là viết yêu cầu thành câu:

> “Tôi phải giữ **mọi hàng của bảng nào**? Nếu không có đối tác, tôi muốn hiển thị một hàng có `NULL`, hay loại hàng đó?”

Nếu trả lời được, bạn sẽ xác định được thứ tự bảng và dạng `JOIN` trước khi bắt đầu điều chỉnh điều kiện lọc.

## 14. Lưu ý khác biệt giữa các hệ quản trị

Cú pháp outer join cơ bản được dùng khá rộng rãi:

```sql
-- Dạng tiêu chuẩn dễ đọc:
SELECT ...
FROM a
LEFT OUTER JOIN b ON a.id = b.a_id;

SELECT ...
FROM a
RIGHT OUTER JOIN b ON a.id = b.a_id;
```

**`OUTER` là từ khóa tùy chọn** trong các hệ hỗ trợ cú pháp này: `LEFT JOIN` và `LEFT OUTER JOIN` diễn đạt cùng loại phép nối; tương tự cho `RIGHT JOIN`.

| DBMS | LEFT JOIN | RIGHT JOIN | FULL OUTER JOIN | Ghi chú |
|---|---|---|---|---|
| PostgreSQL | Có | Có | Có | Hỗ trợ `NULLS FIRST/LAST` khi sắp xếp |
| MySQL | Có | Có | Không có cú pháp `FULL OUTER JOIN` trực tiếp phổ biến | Có thể viết lại `RIGHT JOIN` thành `LEFT JOIN` |
| SQL Server | Có | Có | Có | Cú pháp phân trang và quản lý kết quả có khác PostgreSQL |
| Oracle Database | Có | Có | Có | Cần lưu ý khác biệt về chuỗi rỗng và `NULL` |
| SQLite hiện đại | Có | Có từ phiên bản 3.39.0 | Có từ phiên bản 3.39.0 | Phiên bản SQLite cũ không hỗ trợ hai dạng sau |

Nếu phải hỗ trợ **nhiều DBMS hoặc phiên bản cũ**, viết truy vấn bằng `LEFT JOIN` với bảng cần bảo toàn ở bên trái thường giúp giảm một số phụ thuộc vào `RIGHT JOIN`. Nhưng điều đó không có nghĩa được phép thay `RIGHT JOIN` bằng `LEFT JOIN` mà **không đảo đúng hai phía**.

Về mặt cú pháp, bạn có thể gặp:

```sql
FROM customers c
LEFT JOIN orders o
    ON c.customer_id = o.customer_id
```

hoặc:

```sql
FROM customers c
LEFT JOIN orders o
    USING (customer_id)
```

`USING (customer_id)` tiện khi hai phía có **cùng tên cột khóa** và DBMS hỗ trợ, nhưng nó có quy tắc riêng về cột khóa xuất hiện trong kết quả, đặc biệt khi `SELECT *`. Đối với người mới học, `ON c.customer_id = o.customer_id` thường làm điều kiện ghép minh bạch hơn. Tránh `NATURAL JOIN` khi không chủ động muốn tự ghép theo mọi cột trùng tên: việc thêm một cột trùng tên vào schema có thể làm thay đổi quan hệ ghép không mong muốn.

## 15. Những lỗi thường gặp

### Lỗi 1 — Nghĩ LEFT JOIN chỉ sinh đúng một hàng cho mỗi hàng trái

Nếu một khách có ba đơn, một hàng khách có thể ghép thành **ba hàng kết quả**. `LEFT JOIN` giữ mọi khách, nhưng không tự loại bớt các đối tác hợp lệ.

### Lỗi 2 — Đổi LEFT thành RIGHT mà không chú ý vị trí bảng

`customers LEFT JOIN orders` giữ khách. `customers RIGHT JOIN orders` giữ đơn. Không phải đổi từ khóa là chỉ đảo thứ tự hiển thị; **tập hàng được bảo toàn đã thay đổi**.

### Lỗi 3 — Đặt điều kiện lọc bên phải trong WHERE rồi làm mất hàng trái

`WHERE o.status = 'PAID'` loại hàng có `o.status = NULL` do outer join, khiến khách chưa có đơn PAID biến mất. Nếu yêu cầu giữ mọi khách, thường đặt tiêu chí chọn đơn trong `ON`.

### Lỗi 4 — Thêm OR o.order_id IS NULL và tưởng đã phục hồi mọi khách

Khách Chi có đơn `CANCELLED` nên phép nối cơ bản đã khớp; không có hàng đơn `NULL` bổ sung cho Chi. `WHERE o.status = 'PAID' OR o.order_id IS NULL` vẫn loại Chi. Bộ lọc trong `ON` mới giữ đúng ý nghĩa “mọi khách, đơn PAID nếu có”.

### Lỗi 5 — Kiểm tra cột có thể NULL để kết luận không có đối tác

Một cột như `o.note` hoặc `o.rating` có thể `NULL` ở **đơn có thật**. `WHERE o.note IS NULL` không đồng nghĩa “khách không có đơn”. Hãy kiểm tra cột phía phải **bắt buộc không `NULL` khi bản ghi tồn tại**, thường là khóa chính `o.order_id`.

### Lỗi 6 — Dùng COUNT(*) để đếm đơn trên LEFT JOIN

Khách Dung chưa có đơn vẫn được biểu diễn bằng **một hàng outer join**, nên `COUNT(*) = 1`. Để đếm đơn, dùng `COUNT(o.order_id)` với khóa không `NULL` của đơn.

### Lỗi 7 — Không xem xét NULL khi dùng = hoặc NOT IN

`NULL = NULL` không cho `TRUE` trong điều kiện ghép thông thường. `NOT IN` với tập con có `NULL` cũng có thể làm mất những hàng cần tìm. Với bài toán không tồn tại liên kết, `NOT EXISTS` thường dễ suy luận hơn.

### Lỗi 8 — Dùng DISTINCT che lỗi JOIN nhân hàng

`SELECT DISTINCT` có thể xóa các hàng trùng ở **các cột được chọn**, nhưng không nhất thiết sửa phép tổng hợp tiền hoặc số lượng. Hai đơn hợp lệ có thể cùng số tiền; tổng hợp đúng grain trước khi nối thường an toàn hơn.

### Lỗi 9 — Hiểu “giữ mọi hàng” là giữ luôn thứ tự ban đầu

Outer join không cam kết thứ tự kết quả. Khi cần thứ tự ổn định, dùng `ORDER BY` với các khóa phân định rõ ràng.

### Lỗi 10 — Dùng COALESCE để che dấu dữ liệu thiếu

`COALESCE(SUM(amount), 0)` có thể hữu ích để hiển thị tổng 0 cho khách không có đơn, nhưng **giá trị `NULL` và 0 không luôn cùng nghĩa**. Trong hệ thống thật, phải quyết định điều gì là chưa biết, không áp dụng hay số 0 thật trước khi thay thế.

## 16. Bài tập thực hành

Hãy sử dụng hai bảng `customers` và `orders` ở mục 2. Thử dự đoán kết quả **trước khi chạy SQL**.

### Bài 1 — Phân biệt LEFT và RIGHT

Xét:

```sql
-- A
SELECT c.customer_id, o.order_id
FROM customers c
LEFT JOIN orders o ON o.customer_id = c.customer_id
ORDER BY c.customer_id, o.order_id;

-- B
SELECT c.customer_id, o.order_id
FROM customers c
RIGHT JOIN orders o ON o.customer_id = c.customer_id
ORDER BY o.order_id;
```

**Đáp án:** A có **5 hàng**, chứa khách Dung với `order_id = NULL`, không chứa đơn 104. B cũng có **5 hàng**, nhưng chứa đơn 104 với `c.customer_id = NULL` và không có Dung. Số hàng bằng nhau trong ví dụ **không có nghĩa nội dung hai kết quả bằng nhau**.

### Bài 2 — Tìm khách chưa có đơn

Viết `LEFT JOIN` kết hợp `IS NULL` để tìm khách không có bất kỳ đơn nào:

```sql
SELECT c.customer_id, c.customer_name
FROM customers c
LEFT JOIN orders o ON o.customer_id = c.customer_id
WHERE o.order_id IS NULL;
```

**Đáp án:** **Dung**. Hãy viết lại bằng `NOT EXISTS` và giải thích vì sao truy vấn con chứa `NULL` không gây bẫy như `NOT IN`.

### Bài 3 — Đếm đơn, bao gồm 0

Yêu cầu một hàng cho mỗi khách, có `order_count`:

```sql
SELECT
    c.customer_id,
    c.customer_name,
    COUNT(o.order_id) AS order_count
FROM customers c
LEFT JOIN orders o ON o.customer_id = c.customer_id
GROUP BY c.customer_id, c.customer_name
ORDER BY c.customer_id;
```

**Đáp án:** An **2**, Binh **1**, Chi **1**, Dung **0**. Nếu đổi `COUNT(o.order_id)` thành `COUNT(*)`, kết quả của Dung thay đổi như thế nào và vì sao?

### Bài 4 — Mọi khách và số đơn PAID

Yêu cầu mỗi khách một hàng, kể cả chưa có đơn `PAID`. Câu SQL:

```sql
SELECT
    c.customer_id,
    c.customer_name,
    COUNT(o.order_id) AS paid_orders
FROM customers c
LEFT JOIN orders o
    ON o.customer_id = c.customer_id
   AND o.status = 'PAID'
GROUP BY c.customer_id, c.customer_name
ORDER BY c.customer_id;
```

**Đáp án:** An **1**, Binh **1**, Chi **0**, Dung **0**. Vì sao đặt `o.status = 'PAID'` trong `WHERE` làm hai khách cuối biến mất?

### Bài 5 — Khách chưa có đơn PAID khác khách chưa có đơn

Viết hai truy vấn để tìm:

1. Khách không có đơn nào.
2. Khách không có đơn `PAID`.

**Đáp án:** câu 1 trả **Dung**; câu 2 trả **Chi và Dung**. Với câu 2, dùng điều kiện trạng thái trong `ON` cùng `WHERE o.order_id IS NULL`, hoặc `NOT EXISTS` với điều kiện `o.status = 'PAID'`.

### Bài 6 — Mọi đơn và thông tin khách nếu có

Viết một câu `RIGHT JOIN` và một câu `LEFT JOIN` đảo hai bảng để giữ **mọi đơn**:

```sql
-- RIGHT JOIN
SELECT o.order_id, c.customer_name
FROM customers c
RIGHT JOIN orders o ON c.customer_id = o.customer_id
ORDER BY o.order_id;

-- LEFT JOIN tương đương
SELECT o.order_id, c.customer_name
FROM orders o
LEFT JOIN customers c ON c.customer_id = o.customer_id
ORDER BY o.order_id;
```

**Đáp án:** cả hai đều trả đơn **101–105**; riêng đơn **104** có tên khách là `NULL`.

### Bài 7 — Đọc kết quả tổng tiền

Giả sử báo cáo từ `customers LEFT JOIN orders` có tổng số tiền 460.000, nhưng:

```sql
SELECT SUM(order_amount) AS all_order_amount
FROM orders;
```

trả **540.000**. Hãy tìm **80.000** chênh lệch và giải thích: đơn **104** không thuộc khách nào, nên không được đưa vào truy vấn bắt đầu từ khách và chỉ giữ khách; nhưng vẫn có trong bảng đơn khi tính tổng toàn bộ.

### Bài 8 — Đối chiếu cả hai phía bằng FULL OUTER JOIN

```sql
SELECT
    c.customer_id,
    c.customer_name,
    o.order_id
FROM customers c
FULL OUTER JOIN orders o
    ON o.customer_id = c.customer_id
ORDER BY c.customer_id NULLS LAST, o.order_id;
```

**Đáp án:** có **6 hàng**: bốn hàng khớp, một hàng cho Dung không có đơn và một hàng cho đơn 104 không có khách. Khi học trên DBMS không hỗ trợ `FULL OUTER JOIN` trực tiếp, hãy tìm hiểu cách mô phỏng phù hợp với hệ đó thay vì sao chép nguyên cú pháp PostgreSQL.

## Kết luận

`LEFT JOIN` và `RIGHT JOIN` mở rộng khả năng ghép bảng khi **một phía có hàng không khớp**:

- **`LEFT JOIN`** giữ mọi hàng của **bảng trái** và bổ sung `NULL` cho cột bảng phải nếu không có đối tác.
- **`RIGHT JOIN`** giữ mọi hàng của **bảng phải** và bổ sung `NULL` cho cột bảng trái nếu không có đối tác.
- `RIGHT JOIN` giữa hai bảng thường có thể viết lại thành `LEFT JOIN` bằng cách **đảo đúng vị trí hai bảng**.
- Điều kiện **`ON`** quyết định cặp hàng nào ghép được; điều kiện **`WHERE`** lọc kết quả sau nối và có thể làm mất những hàng outer join vừa giữ lại.
- Để tìm hàng không khớp, dùng cột khóa không `NULL` của phía đối tác với `IS NULL`, hoặc cân nhắc `NOT EXISTS`.
- Khi thống kê, `COUNT(*)` đếm các hàng kết quả sau nối, còn `COUNT(right_primary_key)` giúp đếm bản ghi bên phải thật sự tồn tại. Phải chú ý nguy cơ **nhân hàng** khi quan hệ một-nhiều.

Kỹ năng quan trọng nhất là xác định ngay từ yêu cầu nghiệp vụ: **“Bảng nào phải được giữ lại đầy đủ, kể cả khi không có dữ liệu tương ứng?”** Khi biết câu trả lời, bạn có thể chọn hướng outer join, đặt điều kiện lọc đúng vị trí và giải thích kết quả có `NULL` một cách chính xác.
