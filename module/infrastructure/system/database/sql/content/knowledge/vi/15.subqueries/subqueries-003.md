# EXISTS và NOT EXISTS cho kiểm tra tồn tại

Trong cơ sở dữ liệu quan hệ, có nhiều câu hỏi không cần biết **có bao nhiêu** bản ghi liên quan hay **giá trị cụ thể** của chúng. Ta chỉ cần biết **có ít nhất một bản ghi thỏa điều kiện hay không**:

- Khách hàng này **đã từng đặt đơn** chưa?
- Có **đơn đã thanh toán** nào của khách này không?
- Sản phẩm nào **chưa từng xuất hiện** trong đơn hàng?
- Khách nào có đơn nhưng **không có đơn đã thanh toán**?
- Một đơn có **ít nhất hai dòng sản phẩm** không?

Trong SQL, hai toán tử phục vụ trực tiếp nhu cầu đó là **`EXISTS`** và **`NOT EXISTS`**. Chúng thường xuất hiện cùng **truy vấn con (*subquery*)**, đặc biệt là truy vấn con có tương quan (*correlated subquery*) sử dụng giá trị của hàng từ truy vấn ngoài. Thay vì lấy dữ liệu từ truy vấn con để so sánh, `EXISTS` quan tâm **truy vấn con có trả về ít nhất một hàng hay không**.

Bài học này giải thích ý nghĩa, cú pháp, cách sử dụng theo nghiệp vụ, điểm khác với `JOIN`, `IN` và `NOT IN`, tác động của `NULL`, các lỗi dễ gặp và cách tư duy về hiệu năng. Ví dụ thực hành dùng PostgreSQL với cú pháp SQL phổ biến ở các hệ quản trị quan hệ khác.

## 1. EXISTS và NOT EXISTS kiểm tra điều gì?

**`EXISTS (subquery)`** có kết quả:

- **`TRUE`** nếu `subquery` trả về **ít nhất một hàng**.
- **`FALSE`** nếu `subquery` **không trả về hàng nào**.

**`NOT EXISTS (subquery)`** là phép phủ định:

- **`TRUE`** nếu `subquery` **không có hàng**.
- **`FALSE`** nếu `subquery` có **ít nhất một hàng**.

| Số hàng do truy vấn con trả về | `EXISTS (subquery)` | `NOT EXISTS (subquery)` |
|---:|---|---|
| 0 | `FALSE` | `TRUE` |
| 1 | `TRUE` | `FALSE` |
| 2 | `TRUE` | `FALSE` |
| 100 | `TRUE` | `FALSE` |

**Điểm quan trọng:** nội dung các giá trị trong hàng của truy vấn con **không quyết định kết quả `EXISTS`**. Một hàng chứa `NULL` vẫn là một hàng tồn tại.

Ví dụ trên PostgreSQL:

```sql
SELECT EXISTS (
    SELECT NULL
) AS has_a_row;
-- TRUE

SELECT EXISTS (
    SELECT 1 WHERE 1 = 0
) AS has_a_matching_row;
-- FALSE

SELECT NOT EXISTS (
    SELECT 1 WHERE 1 = 0
) AS no_matching_row;
-- TRUE
```

Ở câu đầu, truy vấn con trả **một hàng với giá trị `NULL`**, nên `EXISTS` là `TRUE`. Ở hai câu sau, điều kiện `1 = 0` khiến truy vấn con **không trả hàng nào**.

Khác với phép so sánh thông thường như `NULL = 5` (cho `UNKNOWN`), bản thân kết quả kiểm tra `EXISTS` và `NOT EXISTS` luôn là **`TRUE` hoặc `FALSE`**, vì chúng kiểm tra số lượng hàng có tồn tại hay không.

## 2. Cú pháp cơ bản và vị trí sử dụng

Hai mẫu thường gặp trong `WHERE`:

```sql
SELECT cot_can_hien_thi
FROM bang_ngoai AS a
WHERE EXISTS (
    SELECT 1
    FROM bang_lien_quan AS b
    WHERE b.khoa_ngoai = a.khoa_chinh
);
```

```sql
SELECT cot_can_hien_thi
FROM bang_ngoai AS a
WHERE NOT EXISTS (
    SELECT 1
    FROM bang_lien_quan AS b
    WHERE b.khoa_ngoai = a.khoa_chinh
);
```

Trong đó:

1. Truy vấn **ngoài** chọn các hàng cần hiển thị, ví dụ khách hàng.
2. Truy vấn **con** tìm các hàng có quan hệ với **hàng đang xét** ở truy vấn ngoài.
3. Biểu thức `b.khoa_ngoai = a.khoa_chinh` là **điều kiện tương quan**: dùng giá trị từ cả hai cấp truy vấn.
4. `EXISTS` giữ hàng ngoài khi tìm thấy ít nhất một hàng con khớp.
5. `NOT EXISTS` giữ hàng ngoài khi không tìm thấy hàng con nào khớp.

`EXISTS` cũng có thể xuất hiện trong `CASE WHEN`, điều kiện của `UPDATE`, `DELETE` và một số biểu thức khác theo cú pháp DBMS. Tuy nhiên, để học rõ nguyên lý, ta bắt đầu từ `SELECT ... WHERE`.

### Vì sao thường viết SELECT 1?

Trong truy vấn con phục vụ `EXISTS`, cách viết phổ biến là:

```sql
WHERE EXISTS (
    SELECT 1
    FROM orders AS o
    WHERE o.customer_id = c.customer_id
)
```

Số `1` không phải giá trị đem so với bất kỳ cột nào; nó **chỉ là biểu thức được chọn**. `EXISTS` kiểm tra **sự có mặt của hàng**, không đọc cột trong danh sách `SELECT` để quyết định đúng/sai.

Trong các truy vấn con đơn giản, `SELECT 1` và `SELECT *` thường cho **cùng kết quả `EXISTS`**:

```sql
WHERE EXISTS (
    SELECT *
    FROM orders AS o
    WHERE o.customer_id = c.customer_id
)
```

`SELECT 1` làm ý định rõ hơn: “tôi chỉ quan tâm có hàng hay không”. Đừng cho rằng `SELECT 1` bắt buộc để truy vấn nhanh hơn trong mọi DBMS; bộ tối ưu có thể xử lý hai cách tương đương. Ngoài ra, một số dạng truy vấn đặc biệt như tập hợp hoặc phép toán tập có thể đặt quy tắc riêng cho danh sách `SELECT`; bài học dùng dạng truy vấn con thông thường.

## 3. Tạo dữ liệu mẫu xuyên suốt

Ta dùng bốn bảng: **khách hàng**, **đơn hàng**, **sản phẩm** và **dòng sản phẩm trong đơn**. Chạy các lệnh sau trong **database thực hành riêng**, tránh thao tác trên dữ liệu sản xuất.

### 3.1. Định nghĩa bảng

```sql
CREATE TABLE customers (
    customer_id INTEGER PRIMARY KEY,
    customer_name VARCHAR(80) NOT NULL,
    city VARCHAR(40)
);

CREATE TABLE orders (
    order_id INTEGER PRIMARY KEY,
    customer_id INTEGER NOT NULL REFERENCES customers(customer_id),
    ordered_on DATE NOT NULL,
    status VARCHAR(20) NOT NULL
        CHECK (status IN ('NEW', 'PAID', 'CANCELLED'))
);

CREATE TABLE products (
    product_id INTEGER PRIMARY KEY,
    product_name VARCHAR(80) NOT NULL
);

CREATE TABLE order_items (
    order_id INTEGER NOT NULL REFERENCES orders(order_id),
    product_id INTEGER NOT NULL REFERENCES products(product_id),
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    PRIMARY KEY (order_id, product_id)
);
```

Quan hệ:

```text
customers (1) ───── (N) orders
                           |
                           | (1)
                           |
                           | (N)
                        order_items
                           |
                           | (N)
                           |
                           | (1)
                        products
```

Một khách có thể có nhiều đơn; một đơn có thể gồm nhiều dòng sản phẩm; một sản phẩm có thể xuất hiện trong nhiều đơn. Bài này giả sử mỗi sản phẩm chỉ xuất hiện một lần trong mỗi đơn, được thể hiện bằng khóa chính ghép `(order_id, product_id)`.

### 3.2. Nạp dữ liệu cố định

```sql
INSERT INTO customers (customer_id, customer_name, city)
VALUES
    (1, 'An',   'Ha Noi'),
    (2, 'Binh', 'TP HCM'),
    (3, 'Chi',  'Ha Noi'),
    (4, 'Dung', 'Da Nang'),
    (5, 'Em',   'Ha Noi');

INSERT INTO orders (order_id, customer_id, ordered_on, status)
VALUES
    (101, 1, DATE '2025-03-01', 'PAID'),
    (102, 1, DATE '2025-03-02', 'NEW'),
    (103, 2, DATE '2025-03-03', 'PAID'),
    (104, 3, DATE '2025-03-04', 'CANCELLED'),
    (105, 3, DATE '2025-03-05', 'NEW'),
    (106, 5, DATE '2025-03-06', 'PAID');

INSERT INTO products (product_id, product_name)
VALUES
    (10, 'Sach SQL'),
    (20, 'But'),
    (30, 'Chuot'),
    (40, 'So tay');

INSERT INTO order_items (order_id, product_id, quantity)
VALUES
    (101, 10, 1),
    (101, 20, 2),
    (102, 30, 1),
    (103, 10, 2),
    (104, 20, 1),
    (105, 30, 1),
    (106, 10, 1),
    (106, 30, 1);
```

### 3.3. Đọc bộ dữ liệu

**Khách hàng:**

| customer_id | customer_name | city |
|---:|---|---|
| 1 | An | Ha Noi |
| 2 | Binh | TP HCM |
| 3 | Chi | Ha Noi |
| 4 | Dung | Da Nang |
| 5 | Em | Ha Noi |

**Đơn hàng:**

| order_id | customer_id | status | ordered_on |
|---:|---:|---|---|
| 101 | 1 | PAID | 2025-03-01 |
| 102 | 1 | NEW | 2025-03-02 |
| 103 | 2 | PAID | 2025-03-03 |
| 104 | 3 | CANCELLED | 2025-03-04 |
| 105 | 3 | NEW | 2025-03-05 |
| 106 | 5 | PAID | 2025-03-06 |

**Sản phẩm:**

| product_id | product_name | Đã xuất hiện trong đơn? |
|---:|---|---|
| 10 | Sach SQL | Có |
| 20 | But | Có |
| 30 | Chuot | Có |
| 40 | So tay | Chưa |

Có **5 khách, 6 đơn, 4 sản phẩm, 8 dòng sản phẩm**. Khách Dung **chưa có đơn nào**. Khách Chi có đơn `NEW` và `CANCELLED` nhưng **không có đơn `PAID`**. Sản phẩm So tay chưa xuất hiện trong `order_items`. Các điểm đó giúp kiểm tra chính xác ý nghĩa của `EXISTS` và `NOT EXISTS`.

## 4. EXISTS: tìm các hàng có ít nhất một bản ghi liên quan

### 4.1. Khách đã từng có đơn

```sql
SELECT c.customer_id, c.customer_name
FROM customers AS c
WHERE EXISTS (
    SELECT 1
    FROM orders AS o
    WHERE o.customer_id = c.customer_id
)
ORDER BY c.customer_id;
```

Kết quả:

| customer_id | customer_name |
|---:|---|
| 1 | An |
| 2 | Binh |
| 3 | Chi |
| 5 | Em |

Giải thích cách đọc:

1. Xét hàng ngoài của khách **An** (`customer_id = 1`).
2. Truy vấn con có điều kiện `o.customer_id = 1` và tìm thấy đơn 101, 102.
3. Vì có ít nhất một hàng, `EXISTS` là `TRUE`; An được giữ.
4. Với khách **Dung** (`customer_id = 4`), không tìm được đơn nào có `customer_id = 4`.
5. `EXISTS` là `FALSE`; Dung bị loại.

Đây là cách giải thích **theo logic**. Bộ tối ưu DBMS không nhất thiết chạy truy vấn con một lần cho từng khách; nó có thể biến đổi thành phép nối bán (*semi-join*) hoặc kế hoạch tương đương. Điều quan trọng là **ngữ nghĩa của kết quả**.

### 4.2. Có nhiều đơn vẫn chỉ trả một hàng khách

An có hai đơn, Chi cũng có hai đơn. Nhưng câu `EXISTS` ở trên vẫn trả **mỗi khách một lần**, vì truy vấn ngoài đang đọc **một hàng trên bảng `customers`**, còn `EXISTS` chỉ quyết định giữ hay loại hàng đó.

So sánh với `INNER JOIN`:

```sql
SELECT c.customer_id, c.customer_name
FROM customers AS c
JOIN orders AS o
    ON o.customer_id = c.customer_id
ORDER BY c.customer_id, o.order_id;
```

Kết quả có **6 hàng**:

```text
1 An
1 An
2 Binh
3 Chi
3 Chi
5 Em
```

`JOIN` tạo **một hàng cho mỗi cặp khớp**, nên khách có hai đơn xuất hiện hai lần. `EXISTS` không thêm các hàng đơn vào kết quả ngoài; nó chỉ lọc hàng khách.

Nếu chỉ cần kiểm tra tồn tại, `EXISTS` thường thể hiện ý định rõ hơn `JOIN` + `DISTINCT`. Nếu cần **hiển thị từng đơn** cùng khách, `JOIN` mới là lựa chọn phù hợp.

### 4.3. Thêm điều kiện trong truy vấn con

Yêu cầu: **khách có ít nhất một đơn đã thanh toán**:

```sql
SELECT c.customer_id, c.customer_name
FROM customers AS c
WHERE EXISTS (
    SELECT 1
    FROM orders AS o
    WHERE o.customer_id = c.customer_id
      AND o.status = 'PAID'
)
ORDER BY c.customer_id;
```

Kết quả: **An (1), Binh (2), Em (5)**.

Chú ý cả **điều kiện liên hệ với khách** lẫn **điều kiện trạng thái** đều nằm trong truy vấn con. `EXISTS` trả `TRUE` khi tồn tại **ít nhất một đơn của chính khách đó** và có `status = 'PAID'`. Những đơn `NEW` hoặc `CANCELLED` không làm điều kiện này đúng.

Thêm phạm vi ngày nếu cần:

```sql
SELECT c.customer_id, c.customer_name
FROM customers AS c
WHERE EXISTS (
    SELECT 1
    FROM orders AS o
    WHERE o.customer_id = c.customer_id
      AND o.status = 'PAID'
      AND o.ordered_on >= DATE '2025-03-01'
      AND o.ordered_on < DATE '2025-04-01'
)
ORDER BY c.customer_id;
```

Với dữ liệu mẫu, kết quả vẫn là **An, Binh, Em**. Dùng khoảng nửa mở (bao gồm ngày bắt đầu, không bao gồm mốc đầu tháng sau) giúp diễn đạt chính xác phạm vi khi chuyển sang cột thời gian có cả giờ, phút, giây.

## 5. NOT EXISTS: tìm hàng không có đối tác thỏa điều kiện

`NOT EXISTS` kiểm tra **truy vấn con không trả về bất kỳ hàng nào**. Đây là công cụ tự nhiên cho những yêu cầu bắt đầu bằng “chưa từng”, “không có”, “không tồn tại”.

### 5.1. Khách chưa từng có đơn

```sql
SELECT c.customer_id, c.customer_name
FROM customers AS c
WHERE NOT EXISTS (
    SELECT 1
    FROM orders AS o
    WHERE o.customer_id = c.customer_id
)
ORDER BY c.customer_id;
```

Kết quả chỉ có **Dung (4)**. Truy vấn con không tìm thấy hàng đơn nào của Dung, nên `NOT EXISTS` là `TRUE`.

Đối với An, dù chỉ cần một đơn cũng đủ để `EXISTS` đúng và `NOT EXISTS` sai. Truy vấn không cần đếm tất cả đơn của An mới biết An **không thuộc nhóm khách chưa đặt đơn**.

### 5.2. Khách chưa từng có đơn PAID

```sql
SELECT c.customer_id, c.customer_name
FROM customers AS c
WHERE NOT EXISTS (
    SELECT 1
    FROM orders AS o
    WHERE o.customer_id = c.customer_id
      AND o.status = 'PAID'
)
ORDER BY c.customer_id;
```

Kết quả: **Chi (3) và Dung (4)**.

- **Chi** đã có đơn, nhưng cả hai đơn đều không có trạng thái `PAID`.
- **Dung** chưa có bất kỳ đơn nào, nên đương nhiên không có đơn `PAID`.

Đây là điểm cần suy luận kỹ: **“không có đơn PAID” không đồng nghĩa “có đơn nhưng đều chưa PAID”**. Khách không có đơn nào vẫn thỏa điều kiện phủ định.

### 5.3. Kết hợp EXISTS và NOT EXISTS để thể hiện điều kiện kép

Yêu cầu: **khách đã có ít nhất một đơn nhưng chưa có đơn nào PAID**.

```sql
SELECT c.customer_id, c.customer_name
FROM customers AS c
WHERE EXISTS (
    SELECT 1
    FROM orders AS o_any
    WHERE o_any.customer_id = c.customer_id
)
AND NOT EXISTS (
    SELECT 1
    FROM orders AS o_paid
    WHERE o_paid.customer_id = c.customer_id
      AND o_paid.status = 'PAID'
)
ORDER BY c.customer_id;
```

Kết quả chỉ có **Chi (3)**:

| Khách | Có bất kỳ đơn nào? | Có đơn PAID? | Được chọn? |
|---|---|---|---|
| An | Có | Có | Không |
| Binh | Có | Có | Không |
| Chi | Có | Không | **Có** |
| Dung | Không | Không | Không |
| Em | Có | Có | Không |

`EXISTS` thứ nhất loại Dung vì chưa có đơn. `NOT EXISTS` thứ hai loại An, Binh, Em vì đã có đơn thanh toán. Hai điều kiện kết hợp diễn đạt trực tiếp nghiệp vụ.

### 5.4. Phủ định “có đơn PAID” khác với “có đơn không PAID”

So sánh:

```sql
-- A: Có ít nhất một đơn KHÔNG PAID.
SELECT c.customer_id
FROM customers AS c
WHERE EXISTS (
    SELECT 1
    FROM orders AS o
    WHERE o.customer_id = c.customer_id
      AND o.status <> 'PAID'
)
ORDER BY c.customer_id;
-- 1, 3
```

```sql
-- B: Không có BẤT KỲ đơn PAID nào.
SELECT c.customer_id
FROM customers AS c
WHERE NOT EXISTS (
    SELECT 1
    FROM orders AS o
    WHERE o.customer_id = c.customer_id
      AND o.status = 'PAID'
)
ORDER BY c.customer_id;
-- 3, 4
```

Khách **An** có cả đơn `NEW` lẫn đơn `PAID`, nên thỏa câu A nhưng **không** thỏa câu B. Khách **Dung** không có đơn nào, nên không thỏa câu A nhưng **thỏa** câu B.

Do đó:

```text
EXISTS (đơn có trạng thái khác PAID)

KHÔNG tương đương với

NOT EXISTS (đơn có trạng thái PAID)
```

Đây là khác biệt giữa **“tồn tại ít nhất một phần tử không đạt”** và **“không tồn tại phần tử đạt”**. Khi dịch một câu phủ định trong yêu cầu nghiệp vụ sang SQL, hãy xác định chính xác điều kiện nào nằm **bên trong `NOT EXISTS`**.

## 6. EXISTS cho quan hệ nhiều bảng

Truy vấn con có thể chứa `JOIN` và bất kỳ bộ lọc nào cần thiết; `EXISTS` vẫn chỉ kiểm tra có hàng thỏa tất cả điều kiện hay không.

### 6.1. Khách từng đặt sản phẩm Sach SQL

Sản phẩm `product_id = 10` là **Sach SQL**. Để tìm khách từng có đơn chứa sản phẩm này:

```sql
SELECT c.customer_id, c.customer_name
FROM customers AS c
WHERE EXISTS (
    SELECT 1
    FROM orders AS o
    JOIN order_items AS oi
        ON oi.order_id = o.order_id
    WHERE o.customer_id = c.customer_id
      AND oi.product_id = 10
)
ORDER BY c.customer_id;
```

Kết quả: **An (1), Binh (2), Em (5)**.

Luồng suy luận: với từng khách, truy vấn con tìm một **cặp đơn–dòng đơn** thuộc khách đó và có `product_id = 10`. Nếu tồn tại ít nhất một cặp, khách được chọn. Truy vấn ngoài không bị nhân lên nếu một khách mua sản phẩm này trong nhiều đơn.

Muốn giới hạn thành **đã mua qua đơn PAID**, thêm:

```sql
AND o.status = 'PAID'
```

vào `WHERE` của truy vấn con. Với dữ liệu hiện tại, ba khách nêu trên vẫn thỏa vì những đơn chứa Sach SQL của họ đều `PAID`.

### 6.2. Đơn có chứa sản phẩm Chuot

```sql
SELECT o.order_id, o.customer_id, o.status
FROM orders AS o
WHERE EXISTS (
    SELECT 1
    FROM order_items AS oi
    WHERE oi.order_id = o.order_id
      AND oi.product_id = 30
)
ORDER BY o.order_id;
```

Kết quả gồm **102, 105, 106**. Một đơn chứa sản phẩm Chuot thì được giữ một lần, bất kể số lượng `quantity` trong dòng sản phẩm là bao nhiêu.

Nếu muốn lọc **đơn PAID chứa Chuot**, bổ sung `o.status = 'PAID'` ở truy vấn ngoài hoặc trong điều kiện tương quan thích hợp; với dữ liệu mẫu chỉ còn đơn **106**.

### 6.3. Sản phẩm chưa từng xuất hiện trong đơn

Đây là bài toán **không tồn tại bản ghi con**, sử dụng `NOT EXISTS`:

```sql
SELECT p.product_id, p.product_name
FROM products AS p
WHERE NOT EXISTS (
    SELECT 1
    FROM order_items AS oi
    WHERE oi.product_id = p.product_id
)
ORDER BY p.product_id;
```

Kết quả chỉ có **40 — So tay**. Sản phẩm 40 có mặt trong danh mục sản phẩm, nhưng không có hàng nào trong `order_items` tham chiếu nó.

Nếu yêu cầu là **“sản phẩm chưa từng nằm trong một đơn đã thanh toán”**, điều kiện phải xét thêm trạng thái đơn:

```sql
SELECT p.product_id, p.product_name
FROM products AS p
WHERE NOT EXISTS (
    SELECT 1
    FROM order_items AS oi
    JOIN orders AS o ON o.order_id = oi.order_id
    WHERE oi.product_id = p.product_id
      AND o.status = 'PAID'
)
ORDER BY p.product_id;
-- 40
```

Trong dữ liệu hiện tại, sản phẩm 10, 20 và 30 đều xuất hiện ở ít nhất một đơn `PAID`. Vì vậy kết quả vẫn là So tay. Trên dữ liệu khác, một sản phẩm chỉ xuất hiện ở đơn `NEW` hoặc `CANCELLED` sẽ thuộc kết quả của truy vấn thứ hai, nhưng không thuộc kết quả của truy vấn “chưa từng xuất hiện trong bất kỳ đơn nào”.

## 7. Phân biệt EXISTS, IN và JOIN

Ba cách viết có thể liên quan cùng một mối quan hệ nhưng **không phải lúc nào cũng trả cùng số hàng hoặc cùng ý nghĩa**.

### 7.1. EXISTS so với IN cho bài toán “đã có đơn”

`EXISTS`:

```sql
SELECT c.customer_id, c.customer_name
FROM customers AS c
WHERE EXISTS (
    SELECT 1
    FROM orders AS o
    WHERE o.customer_id = c.customer_id
)
ORDER BY c.customer_id;
```

`IN`:

```sql
SELECT c.customer_id, c.customer_name
FROM customers AS c
WHERE c.customer_id IN (
    SELECT o.customer_id
    FROM orders AS o
)
ORDER BY c.customer_id;
```

Với bộ dữ liệu này, cả hai trả **An, Binh, Chi, Em**. Chúng đều giải quyết một câu hỏi kiểu **“khách có khóa nằm trong tập mã khách từng đặt đơn hay không”**.

Khác nhau về cách diễn đạt:

- `EXISTS` kiểm tra **một tập hàng có thỏa điều kiện liên hệ hay không**, cho phép diễn đạt điều kiện nhiều cột, quan hệ qua nhiều bảng và bộ lọc bên trong một cách trực tiếp.
- `IN` kiểm tra **giá trị có thuộc một tập giá trị trả về** hay không; với ví dụ chỉ có một khóa `customer_id`, cú pháp ngắn gọn.
- `JOIN` **tạo cặp hàng** và có thể lặp khách khi có nhiều đơn.

Không có quy tắc tuyệt đối “`EXISTS` luôn nhanh hơn `IN`” hoặc ngược lại. Bộ tối ưu nhiều DBMS có thể biến đổi các cách viết hợp lệ thành kế hoạch tương tự. Chọn cách thể hiện rõ câu hỏi, sau đó kiểm tra hiệu năng trên dữ liệu thật khi cần.

### 7.2. Khi dùng JOIN, cần lưu ý hàng bị lặp

```sql
SELECT c.customer_id, c.customer_name
FROM customers AS c
JOIN orders AS o
    ON o.customer_id = c.customer_id
ORDER BY c.customer_id, o.order_id;
```

Có **6 hàng**, vì khách An và Chi mỗi người có hai đơn. Nếu ứng dụng chỉ cần **một hàng mỗi khách**, có thể viết `SELECT DISTINCT c.customer_id, c.customer_name`, nhưng `EXISTS` vốn diễn đạt đúng mục tiêu mà không sinh các cặp đơn–khách để hiển thị.

Khi yêu cầu thay đổi thành **“liệt kê từng đơn và tên khách”**, `JOIN` mới là lựa chọn tự nhiên vì cần dữ liệu của **cả hai phía** trong từng hàng kết quả.

### 7.3. Semi-join và anti-join về mặt khái niệm

Trong xử lý quan hệ:

- **Semi-join (nối bán):** giữ các hàng của một phía **có ít nhất một đối tác phù hợp**, nhưng không đưa ra từng cặp như join thông thường. `EXISTS` thường có ngữ nghĩa tương ứng.
- **Anti-join (nối loại trừ):** giữ các hàng của một phía **không có đối tác phù hợp**. `NOT EXISTS` thường có ngữ nghĩa tương ứng.

DBMS có thể chọn các toán tử hoặc kế hoạch thực thi mang tên *semi join*, *anti join*, *hash*, *nested loop*... Tuy nhiên, đó là **chi tiết kế hoạch**, không phải bảo đảm rằng truy vấn con được thực hiện từng hàng theo đúng từng bước của cách ta giải thích.

## 8. Vì sao NOT EXISTS thường an toàn hơn NOT IN khi có NULL?

Giả sử một bảng tạm chứa **mã khách cần loại trừ**, trong đó có cả giá trị `NULL`:

```sql
-- Một tập giá trị ví dụ độc lập, không cần tạo bảng mới:
SELECT candidate.customer_id
FROM (VALUES
    (1),
    (CAST(NULL AS INTEGER))
) AS candidate(customer_id);
```

Tập này gồm `1` và `NULL`.

### 8.1. Trường hợp NOT IN

```sql
SELECT c.customer_id, c.customer_name
FROM customers AS c
WHERE c.customer_id NOT IN (
    SELECT blocked.customer_id
    FROM (VALUES
        (1),
        (CAST(NULL AS INTEGER))
    ) AS blocked(customer_id)
)
ORDER BY c.customer_id;
```

Truy vấn trên **không trả hàng nào** trong PostgreSQL. Vì sao?

- Với khách 1, `1 NOT IN (1, NULL)` là `FALSE` do đã khớp phần tử 1.
- Với khách 2, các phép so sánh có thể xem theo logic `2 <> 1 AND 2 <> NULL`: vế thứ nhất `TRUE`, vế thứ hai `UNKNOWN`, nên toàn biểu thức `UNKNOWN`.
- `WHERE` chỉ giữ hàng có điều kiện `TRUE`, do đó những khách không bằng 1 cũng bị loại.

Điểm mấu chốt: khi tập giá trị của `NOT IN` chứa `NULL`, kết quả phủ định có thể là **`UNKNOWN`** chứ không phải `TRUE`, làm bỏ sót những hàng mà người viết tưởng là “không thuộc tập”.

### 8.2. Trường hợp NOT EXISTS

```sql
SELECT c.customer_id, c.customer_name
FROM customers AS c
WHERE NOT EXISTS (
    SELECT 1
    FROM (VALUES
        (1),
        (CAST(NULL AS INTEGER))
    ) AS blocked(customer_id)
    WHERE blocked.customer_id = c.customer_id
)
ORDER BY c.customer_id;
```

Kết quả: **Binh (2), Chi (3), Dung (4), Em (5)**.

Ở đây một hàng `blocked.customer_id = NULL` **không khớp** bất kỳ `c.customer_id` đã biết nào bằng dấu `=`. `NOT EXISTS` chỉ hỏi **có hàng blocked nào thực sự thỏa điều kiện tương quan không?** Với khách 2 đến 5, không có, nên họ được giữ.

**Chú ý về ý nghĩa:** Nếu mã ngoài hoặc mã trong có `NULL`, phải xác định thế nào là “khớp” theo nghiệp vụ. `NOT EXISTS` không tự coi hai `NULL` là bằng nhau; nếu yêu cầu muốn coi “đều thiếu” là một trường hợp khớp, cần dùng điều kiện null-safe phù hợp với DBMS, ví dụ `IS NOT DISTINCT FROM` ở PostgreSQL.

### 8.3. Có thể dùng NOT IN khi kiểm soát NULL không?

Có. Nếu cột trong truy vấn con được định nghĩa chắc chắn **`NOT NULL`**, và cách xử lý `NULL` ở giá trị ngoài đã được xác định, `NOT IN` có thể diễn đạt ý định một cách hợp lệ. Một cách khác là lọc rõ `NULL` trong tập con:

```sql
SELECT c.customer_id, c.customer_name
FROM customers AS c
WHERE c.customer_id NOT IN (
    SELECT blocked.customer_id
    FROM (VALUES
        (1),
        (CAST(NULL AS INTEGER))
    ) AS blocked(customer_id)
    WHERE blocked.customer_id IS NOT NULL
)
ORDER BY c.customer_id;
-- 2, 3, 4, 5
```

Với dữ liệu ngoài là khóa chính `NOT NULL`, kết quả đúng như ý định “loại khách 1”. Dù vậy, trong bài toán **không tồn tại hàng liên quan theo điều kiện ghép**, `NOT EXISTS` thường dễ mở rộng và giúp hạn chế lỗi liên quan `NULL`.

## 9. EXISTS với GROUP BY và HAVING khi cần kiểm tra ngưỡng

Khi chỉ hỏi “có ít nhất một đơn không?”, không cần dùng `COUNT(*)`. Nhưng đôi khi nghiệp vụ đòi hỏi **tồn tại một nhóm đạt ngưỡng**, ví dụ “khách có ít nhất hai đơn”.

### 9.1. Khách có ít nhất hai đơn

```sql
SELECT c.customer_id, c.customer_name
FROM customers AS c
WHERE EXISTS (
    SELECT 1
    FROM orders AS o
    WHERE o.customer_id = c.customer_id
    GROUP BY o.customer_id
    HAVING COUNT(*) >= 2
)
ORDER BY c.customer_id;
```

Kết quả: **An (1) và Chi (3)**. Trong truy vấn con:

1. `WHERE` giữ các đơn của khách đang xét.
2. `GROUP BY o.customer_id` tạo nhóm của khách đó nếu có ít nhất một đơn.
3. `HAVING COUNT(*) >= 2` giữ nhóm nếu có ít nhất hai đơn.
4. `EXISTS` là `TRUE` khi truy vấn con trả về nhóm thỏa điều kiện.

Nếu muốn khách có **ít nhất hai đơn PAID**, thêm `AND o.status = 'PAID'` vào `WHERE` của truy vấn con; bộ dữ liệu này **không có khách nào** có hai đơn `PAID`, nên kết quả rỗng.

### 9.2. Bẫy: EXISTS (SELECT COUNT(*)) không có nghĩa COUNT(*) > 0

Xét truy vấn:

```sql
-- Sai ý định nếu muốn tìm khách có đơn:
SELECT c.customer_id
FROM customers AS c
WHERE EXISTS (
    SELECT COUNT(*)
    FROM orders AS o
    WHERE o.customer_id = c.customer_id
)
ORDER BY c.customer_id;
```

Truy vấn này có thể trả **tất cả 5 khách, kể cả Dung**! Trong truy vấn con không có `GROUP BY`, `COUNT(*)` tổng hợp **toàn bộ tập hàng** thành **một hàng kết quả**, kể cả khi số hàng nguồn là 0; khi đó hàng kết quả chứa giá trị `0`. `EXISTS` vẫn thấy **một hàng**, nên trả `TRUE`.

Vì vậy:

```text
EXISTS (SELECT COUNT(*) FROM ...)

KHÔNG đồng nghĩa với

COUNT(*) > 0
```

Để kiểm tra **có đơn hay không**, dùng `EXISTS (SELECT 1 FROM ... WHERE ...)`. Để kiểm tra **đếm từ ngưỡng nào đó**, dùng `GROUP BY ... HAVING COUNT(*) >= n` như ví dụ hoặc tính `COUNT` ở một truy vấn con riêng rồi so sánh có chủ đích.

## 10. NOT EXISTS và điều kiện “tất cả” (phủ định kép)

Ngoài việc kiểm tra “không có bản ghi phù hợp”, `NOT EXISTS` còn giúp diễn đạt câu hỏi khó hơn: **một khách đã mua tất cả các sản phẩm thuộc một tập yêu cầu chưa?**

Ý tưởng logic:

> Một khách đã mua **mọi sản phẩm cần thiết** nếu **không tồn tại** sản phẩm yêu cầu nào mà khách đó **chưa từng mua**.

Ví dụ tập cần kiểm tra gồm sản phẩm **10 (Sach SQL)** và **20 (But)**. Dùng **hai tầng `NOT EXISTS`**:

```sql
SELECT c.customer_id, c.customer_name
FROM customers AS c
WHERE NOT EXISTS (
    SELECT 1
    FROM products AS p
    WHERE p.product_id IN (10, 20)
      AND NOT EXISTS (
          SELECT 1
          FROM orders AS o
          JOIN order_items AS oi
              ON oi.order_id = o.order_id
          WHERE o.customer_id = c.customer_id
            AND oi.product_id = p.product_id
      )
)
ORDER BY c.customer_id;
```

Kết quả chỉ có **An (1)**:

- Với An, có đơn chứa cả sản phẩm 10 và 20. Không tồn tại sản phẩm yêu cầu nào mà An chưa đặt.
- Binh và Em có sản phẩm 10 nhưng chưa từng đặt sản phẩm 20.
- Chi có sản phẩm 20 nhưng chưa có sản phẩm 10.
- Dung chưa có đơn.

Giải thích cách đọc từ trong ra ngoài:

1. Với một khách `c` và một sản phẩm yêu cầu `p`, `NOT EXISTS` bên trong hỏi “khách này **chưa có** đơn chứa sản phẩm này phải không?”.
2. `NOT EXISTS` bên ngoài hỏi “**không có** sản phẩm yêu cầu nào bị thiếu, đúng không?”.
3. Chỉ khách nào **không thiếu bất kỳ sản phẩm yêu cầu nào** mới được chọn.

Kỹ thuật này thường được gọi là **relational division** hoặc biểu diễn mệnh đề **“với mọi”** bằng phủ định tồn tại. Nó hữu ích trong các câu hỏi như: nhân viên có đủ mọi chứng chỉ bắt buộc, học viên hoàn thành tất cả học phần yêu cầu, hoặc tài khoản được cấp đủ mọi quyền cần thiết.

**Trường hợp tập yêu cầu rỗng:** truy vấn con ngoài cùng không có hàng, nên `NOT EXISTS` là `TRUE` cho **mọi khách** (đúng theo logic “không có yêu cầu nào bị thiếu”). Nếu nghiệp vụ muốn trả rỗng khi không có sản phẩm yêu cầu, phải thêm một điều kiện yêu cầu **tập cần kiểm tra không rỗng**.

## 11. EXISTS trong CASE và trong các thao tác thay đổi dữ liệu

### 11.1. Hiển thị cờ tồn tại mà vẫn giữ mọi khách

Đôi khi không muốn loại khách khỏi kết quả, mà muốn thêm cột cho biết khách **có đơn PAID hay không**.

```sql
SELECT
    c.customer_id,
    c.customer_name,
    CASE
        WHEN EXISTS (
            SELECT 1
            FROM orders AS o
            WHERE o.customer_id = c.customer_id
              AND o.status = 'PAID'
        ) THEN 'YES'
        ELSE 'NO'
    END AS has_paid_order
FROM customers AS c
ORDER BY c.customer_id;
```

| customer_id | customer_name | has_paid_order |
|---:|---|---|
| 1 | An | YES |
| 2 | Binh | YES |
| 3 | Chi | NO |
| 4 | Dung | NO |
| 5 | Em | YES |

**Khác `WHERE EXISTS`:** tất cả khách được giữ, chỉ có giá trị của cột `has_paid_order` thay đổi. Dạng `CASE WHEN EXISTS ... THEN ... ELSE ... END` cũng dễ điều chỉnh để trả số `1/0` hoặc mô tả tiếng Việt theo nhu cầu.

### 11.2. UPDATE/DELETE có điều kiện tồn tại

Trong nhiều DBMS, `EXISTS` có thể xuất hiện trong điều kiện `WHERE` của `UPDATE` hoặc `DELETE`. Ví dụ ý tưởng nghiệp vụ: đánh dấu một khách là “đã có đơn” nếu tồn tại đơn liên quan.

Vì bảng `customers` trong bài **chưa có cột đánh dấu**, đoạn dưới chỉ minh họa một mô hình **giả định**, không chạy trực tiếp trên bảng mẫu:

```sql
-- Minh họa, giả sử customers có cột has_order.
UPDATE customers AS c
SET has_order = TRUE
WHERE EXISTS (
    SELECT 1
    FROM orders AS o
    WHERE o.customer_id = c.customer_id
);
```

Với `DELETE`, cần đặc biệt thận trọng: `NOT EXISTS` có thể chọn đúng các khách chưa có đơn, nhưng hành động xóa khách có thể không phù hợp với quy định lưu giữ dữ liệu hoặc gây mất thông tin khác. Khi thực hiện trên hệ thống thật, nên **dùng `SELECT` kiểm tra đúng tập hàng trước**, đảm bảo giao dịch, quyền truy cập, bản sao lưu và quy tắc nghiệp vụ. Không chạy câu xóa hàng loạt chỉ để thử ý tưởng.

## 12. Lỗi tương quan: quên nối truy vấn con với hàng ngoài

Một lỗi đặc biệt nguy hiểm là viết `EXISTS` mà **quên điều kiện tham chiếu khách ngoài**.

### 12.1. Truy vấn con không tương quan

```sql
-- Sai ý định nếu muốn khách nào có đơn PAID:
SELECT c.customer_id, c.customer_name
FROM customers AS c
WHERE EXISTS (
    SELECT 1
    FROM orders AS o
    WHERE o.status = 'PAID'
)
ORDER BY c.customer_id;
```

Truy vấn con **không nhắc tới `c.customer_id`**. Nó chỉ hỏi một câu hỏi chung cho toàn bộ database: “có bất kỳ đơn `PAID` nào hay không?”. Dữ liệu mẫu có đơn `PAID`, nên điều kiện là `TRUE` với **mọi khách**, kể cả Chi và Dung.

Kết quả sai ý định là **tất cả 5 khách**.

### 12.2. Truy vấn con có tương quan

Viết đúng:

```sql
SELECT c.customer_id, c.customer_name
FROM customers AS c
WHERE EXISTS (
    SELECT 1
    FROM orders AS o
    WHERE o.customer_id = c.customer_id
      AND o.status = 'PAID'
)
ORDER BY c.customer_id;
-- An, Binh, Em
```

Điều kiện `o.customer_id = c.customer_id` gắn kết truy vấn con với khách đang xét, từ đó trả lời đúng “**khách này** có đơn PAID không?”.

**Cần tránh đặt tên cột không có bí danh** khi hai cấp truy vấn có cột tên giống nhau. Ví dụ `WHERE customer_id = customer_id` có thể bị hiểu là tự so sánh cột ở cùng phạm vi, khiến điều kiện gần như luôn đúng với giá trị không `NULL`. Dùng bí danh rõ ràng `o.customer_id = c.customer_id` để tránh nhầm phạm vi tên.

### 12.3. NOT EXISTS không tương quan còn nguy hiểm hơn

```sql
-- Không phải: khách nào chưa có đơn PAID.
SELECT c.customer_id
FROM customers AS c
WHERE NOT EXISTS (
    SELECT 1
    FROM orders AS o
    WHERE o.status = 'PAID'
);
```

Vì toàn database có đơn `PAID`, `NOT EXISTS` là `FALSE` cho **mọi khách** → kết quả rỗng. Nếu toàn database không có đơn `PAID` nào, điều kiện thành `TRUE` cho **tất cả khách**. Hai kết quả cực đoan đó khác hẳn yêu cầu “khách nào chưa có đơn đã thanh toán”.

## 13. EXISTS khác COUNT(*) > 0 thế nào?

Với yêu cầu **có ít nhất một hàng**, cả hai dạng có thể trả cùng kết quả khi viết đúng:

```sql
-- Dạng 1: kiểm tra tồn tại.
SELECT c.customer_id
FROM customers AS c
WHERE EXISTS (
    SELECT 1
    FROM orders AS o
    WHERE o.customer_id = c.customer_id
);
```

```sql
-- Dạng 2: đếm rồi so sánh.
SELECT c.customer_id
FROM customers AS c
WHERE (
    SELECT COUNT(*)
    FROM orders AS o
    WHERE o.customer_id = c.customer_id
) > 0;
```

Ở dữ liệu mẫu, cả hai đều chọn **1, 2, 3, 5**. Tuy nhiên, chúng **diễn đạt mục đích khác nhau**:

- `EXISTS`: chỉ quan tâm việc **có ít nhất một hàng** thỏa điều kiện.
- `COUNT(*) > 0`: biểu diễn việc **tính số lượng rồi so ngưỡng 0**.

Trong nhiều trường hợp, DBMS có thể tối ưu `EXISTS` để dừng tìm kiếm sau khi xác nhận một hàng khớp, trong khi cách viết đếm nêu nhu cầu tổng hợp. Nhưng không nên khẳng định `EXISTS` **luôn** nhanh hơn: bộ tối ưu có thể biến đổi cả hai, hiệu năng phụ thuộc chỉ mục, phân bố dữ liệu, kích thước bảng và điều kiện lọc.

Khi chỉ cần câu trả lời **có/không**, ưu tiên `EXISTS` vì ý định rõ ràng. Khi cần **số lượng thực tế** (ví dụ hiển thị “khách có 3 đơn”), `COUNT(*)` là công cụ phù hợp.

### 13.1. LIMIT 1 có cần thiết trong EXISTS?

Một số người viết:

```sql
WHERE EXISTS (
    SELECT 1
    FROM orders AS o
    WHERE o.customer_id = c.customer_id
    LIMIT 1
)
```

Trong PostgreSQL, cách này thường **không cần thiết** vì `EXISTS` vốn chỉ kiểm tra có hàng hay không, và bộ tối ưu đã biết ngữ nghĩa đó. Không mặc định thêm `LIMIT 1` sẽ làm truy vấn nhanh hơn; có thể khiến SQL ít dễ chuyển phương ngữ hơn.

`ORDER BY` trong truy vấn con dành riêng cho `EXISTS` cũng thường **không có ý nghĩa đối với kết quả đúng/sai** vì thứ tự hàng không ảnh hưởng việc có tồn tại hàng. Chỉ thêm các mệnh đề đó khi chúng thực sự là một phần cần thiết của cấu trúc truy vấn phức tạp.

## 14. So sánh NOT EXISTS và LEFT JOIN ... IS NULL

Để tìm khách **không có đơn**, ta có thể dùng `LEFT JOIN` rồi kiểm tra khóa con là `NULL`:

```sql
SELECT c.customer_id, c.customer_name
FROM customers AS c
LEFT JOIN orders AS o
    ON o.customer_id = c.customer_id
WHERE o.order_id IS NULL
ORDER BY c.customer_id;
-- Dung
```

Đây là một cách diễn đạt **anti-join** tương đương về mục đích với:

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

Khi dùng `LEFT JOIN ... IS NULL`, hãy kiểm tra **cột phía phải chắc chắn không `NULL` ở bản ghi thật**, ví dụ `o.order_id` là khóa chính. Nếu thay bằng cột tùy chọn `o.note IS NULL`, một khách có đơn thật nhưng `note = NULL` vẫn có thể bị hiểu nhầm thành khách không có đơn.

### 14.1. Điều kiện lọc cần nằm trong ON

Yêu cầu: **khách không có đơn PAID**. Dạng `LEFT JOIN`:

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

Điều kiện `o.status = 'PAID'` nằm trong **`ON`** để chỉ các đơn `PAID` mới được xem là đối tác của khách. Nếu khách không có đơn `PAID` nào, `LEFT JOIN` tạo một hàng với `o.order_id = NULL`, rồi `WHERE` giữ hàng đó.

Nếu chuyển điều kiện thành:

```sql
-- Sai ý định:
SELECT c.customer_id, c.customer_name
FROM customers AS c
LEFT JOIN orders AS o
    ON o.customer_id = c.customer_id
WHERE o.status = 'PAID'
  AND o.order_id IS NULL;
```

thì hai điều kiện `WHERE` mâu thuẫn với nhau đối với những hàng ghép thật, còn hàng không có đơn thì `o.status = 'PAID'` trả `UNKNOWN`; kết quả không thể mô tả đúng tập khách thiếu đơn `PAID`.

`NOT EXISTS` trong trường hợp này thường dễ đọc hơn vì gói đầy đủ điều kiện loại trừ vào truy vấn con:

```sql
WHERE NOT EXISTS (
    SELECT 1
    FROM orders AS o
    WHERE o.customer_id = c.customer_id
      AND o.status = 'PAID'
)
```

### 14.2. Chọn cách nào?

| Nhu cầu | Cách thường rõ ràng |
|---|---|
| Chỉ kiểm tra **có quan hệ** | `EXISTS` |
| Chỉ kiểm tra **không có quan hệ** | `NOT EXISTS` |
| Muốn hiển thị cột từ **cả bảng cha và bảng con** | `JOIN` hoặc `LEFT JOIN` |
| Muốn giữ **mọi khách** kèm số đơn (bao gồm 0) | `LEFT JOIN` + `GROUP BY` + `COUNT(o.order_id)` |
| Tìm khách không có đơn thỏa nhiều điều kiện | `NOT EXISTS` hoặc `LEFT JOIN` với toàn bộ điều kiện chọn đối tác trong `ON` |

Cách viết tốt nhất dựa trên **ý nghĩa truy vấn và khả năng đọc hiểu**, không chỉ dựa vào số chữ trong SQL. Với mục tiêu kiểm tra tồn tại, hai toán tử `EXISTS`/`NOT EXISTS` diễn đạt rất trực tiếp.

## 15. Vấn đề NULL trong điều kiện bên trong EXISTS

`EXISTS` quan tâm **số hàng trả về**, nhưng **`WHERE` bên trong truy vấn con** vẫn dùng logic ba giá trị của SQL.

Giả sử một bản ghi có `o.customer_id = NULL`:

```sql
WHERE o.customer_id = c.customer_id
```

Khi `c.customer_id` là một số đã biết, phép so sánh với `NULL` trả **`UNKNOWN`**, nên hàng có `o.customer_id = NULL` **không vượt qua bộ lọc** của truy vấn con. Hàng đó sẽ không làm `EXISTS` thành `TRUE` cho khách nào.

Nếu bài toán muốn coi hai giá trị thiếu là khớp, đây là **một quy tắc nghiệp vụ bổ sung**, không phải hành vi của dấu `=`. Một số DBMS hỗ trợ phép so sánh null-safe, chẳng hạn:

```sql
-- PostgreSQL: chỉ dùng nếu nghiệp vụ coi hai NULL như một trường hợp khớp.
WHERE inner_value IS NOT DISTINCT FROM outer_value
```

Trong dữ liệu mẫu, các khóa chính `customer_id` luôn không `NULL`, nên không cần kỹ thuật đó.

Ngoài ra, nếu `orders.status` được phép `NULL`, điều kiện `o.status <> 'PAID'` **không chọn** những đơn có trạng thái `NULL` (vì kết quả là `UNKNOWN`). Khi viết câu hỏi “có đơn không phải PAID”, cần xác định có tính trạng thái thiếu vào nhóm đó hay không. Trong schema thực hành, `status` là `NOT NULL` để kết quả trạng thái được xác định rõ ràng.

## 16. Hiệu năng và chỉ mục cho EXISTS/NOT EXISTS

Với bảng nhỏ, bất kỳ cách viết hợp lệ nào có thể chạy rất nhanh. Với hàng triệu khách và đơn, cần để ý **điều kiện tương quan** và **chỉ mục**.

### 16.1. Chỉ mục trên cột dùng để tìm hàng liên quan

Nếu truy vấn thường xuyên kiểm tra “khách này có đơn PAID không?”, một chỉ mục phù hợp trên bảng `orders` có thể giúp DBMS tìm nhanh theo mã khách và trạng thái:

```sql
CREATE INDEX idx_orders_customer_status
ON orders (customer_id, status);
```

Với truy vấn kiểm tra sản phẩm đã từng có dòng đơn:

```sql
CREATE INDEX idx_order_items_product
ON order_items (product_id);
```

Trong bộ dữ liệu mẫu, `order_items` có khóa chính `(order_id, product_id)`. Chỉ mục phục vụ khóa chính thường bắt đầu bằng `order_id`, nên truy vấn tìm theo **`product_id` riêng lẻ** có thể hưởng lợi từ chỉ mục bổ sung. Không cần tạo các chỉ mục này chỉ vì bảng học tập có vài hàng; trong hệ thống thật phải cân nhắc hiệu năng đọc, chi phí ghi và dung lượng.

### 16.2. DBMS có thể tối ưu thành semi-join hoặc anti-join

Một truy vấn tương quan **không có nghĩa DBMS chắc chắn chạy truy vấn con một lần cho từng hàng**. PostgreSQL và nhiều bộ tối ưu khác có thể biến đổi thành kế hoạch `Nested Loop`, `Hash Semi Join`, `Hash Anti Join` hoặc dạng tương đương, tùy điều kiện và thống kê.

Với PostgreSQL, có thể quan sát kế hoạch:

```sql
EXPLAIN
SELECT c.customer_id
FROM customers AS c
WHERE EXISTS (
    SELECT 1
    FROM orders AS o
    WHERE o.customer_id = c.customer_id
      AND o.status = 'PAID'
);
```

Để có số đo thời gian thực thi, có `EXPLAIN ANALYZE`, nhưng nó **thực sự chạy câu lệnh** và cần sử dụng thận trọng với truy vấn làm thay đổi dữ liệu. Kế hoạch tốt hay xấu phụ thuộc dữ liệu đại diện, kích thước bảng, chỉ mục, tỷ lệ khớp và môi trường thực thi.

### 16.3. Đừng tối ưu sai mục tiêu

Những thói quen nên tránh:

- Thêm `COUNT(*)` chỉ để biết tồn tại, khiến ý định truy vấn kém rõ.
- Thêm `DISTINCT` trong một `SELECT` con chỉ phục vụ `EXISTS` khi không có lý do ngữ nghĩa.
- Thêm `ORDER BY` để “lấy hàng đầu tiên” trong khi `EXISTS` không cần biết thứ tự.
- Giả định `NOT EXISTS` luôn nhanh hơn `LEFT JOIN ... IS NULL` hoặc `NOT IN` trên mọi DBMS và tập dữ liệu.
- Viết điều kiện tương quan bằng biểu thức không cần thiết trên cột, làm DBMS khó tận dụng chỉ mục hoặc buộc phải tính giá trị cho nhiều hàng.

Ưu tiên **đúng nghiệp vụ, rõ điều kiện, có chỉ mục phù hợp và đo đạc** trước khi kết luận về hiệu năng.

## 17. Những lỗi thường gặp

### Lỗi 1 — Quên điều kiện tương quan

`WHERE EXISTS (SELECT 1 FROM orders WHERE status = 'PAID')` kiểm tra có đơn PAID **ở bất kỳ khách nào**, không kiểm tra cho khách đang xét. Thêm điều kiện `o.customer_id = c.customer_id`.

### Lỗi 2 — Nghĩ SELECT 1 có nghĩa “đếm một”

`SELECT 1` không đếm hàng. Nó chỉ tạo một giá trị trong mỗi hàng của truy vấn con; `EXISTS` kiểm tra có **hàng nào** được trả về hay không.

### Lỗi 3 — Dùng EXISTS (SELECT COUNT(*)) để thử có hàng

Truy vấn con tổng hợp `COUNT(*)` không `GROUP BY` vẫn có thể trả **một hàng với giá trị 0** khi đầu vào rỗng, khiến `EXISTS` thành `TRUE`. Dùng `SELECT 1 FROM ... WHERE ...` hoặc so `COUNT(*) > 0` ở vị trí thích hợp.

### Lỗi 4 — Đánh đồng NOT EXISTS (PAID) với EXISTS (khác PAID)

Khách có cả đơn `PAID` và `NEW` là phản ví dụ; khách không có đơn nào cũng làm hai điều kiện khác nhau. Xác định đúng phủ định đang áp lên **điều kiện tồn tại nào**.

### Lỗi 5 — Dùng NOT IN khi truy vấn con có NULL

`NOT IN` có thể cho `UNKNOWN` khi tập con chứa `NULL`. `NOT EXISTS` kiểm tra hàng khớp nên thường thuận lợi hơn trong bài toán “không có quan hệ”.

### Lỗi 6 — Dùng JOIN chỉ để kiểm tra có ít nhất một quan hệ

`JOIN` có thể tạo nhiều hàng cho một khách có nhiều đơn; `EXISTS` giữ khách một lần theo grain của bảng ngoài. Đừng thêm `DISTINCT` vào cuối một truy vấn sai grain mà không hiểu nguyên nhân.

### Lỗi 7 — Nghĩ NOT EXISTS (đơn PAID) loại khách chưa từng có đơn

Khách không có đơn nào vẫn thỏa “không có đơn PAID”. Nếu chỉ muốn khách **có đơn nhưng chưa PAID**, phải thêm một điều kiện `EXISTS` riêng để yêu cầu có ít nhất một đơn.

### Lỗi 8 — Không phân biệt hàng NULL với truy vấn con rỗng

`SELECT NULL` trả một hàng, nên `EXISTS` là `TRUE`. `SELECT 1 WHERE 1 = 0` không trả hàng, nên `EXISTS` là `FALSE`. Giá trị của cột kết quả không quyết định tồn tại.

### Lỗi 9 — Cố dùng EXISTS để trả về dữ liệu chi tiết từ bảng con

`EXISTS` chỉ quyết định điều kiện. Nếu muốn hiện `order_id`, `ordered_on` hoặc các dòng sản phẩm khớp, cần `JOIN`, một truy vấn con trả giá trị phù hợp hoặc kỹ thuật khác. `SELECT 1` bên trong `EXISTS` không tạo cột đầu ra cho truy vấn ngoài.

### Lỗi 10 — Cho rằng EXISTS luôn nhanh hơn mọi lựa chọn

Bộ tối ưu có thể thực thi `EXISTS`, `IN`, `JOIN` và các biến thể bằng nhiều kế hoạch khác nhau. Tối ưu cần dựa trên kích thước bảng, chỉ mục, điều kiện chọn và phép đo thực tế.

## 18. Bài tập thực hành

Hãy sử dụng đúng bộ dữ liệu ở mục 3. Trước khi chạy SQL, hãy viết ra danh sách ID bạn nghĩ sẽ xuất hiện và lý do.

### Bài 1 — Khách có ít nhất một đơn

Viết truy vấn dùng `EXISTS` để tìm khách đã đặt đơn.

```sql
SELECT c.customer_id, c.customer_name
FROM customers AS c
WHERE EXISTS (
    SELECT 1
    FROM orders AS o
    WHERE o.customer_id = c.customer_id
)
ORDER BY c.customer_id;
```

**Đáp án:** **1 An, 2 Binh, 3 Chi, 5 Em**. Khách 4 Dung không có đơn.

### Bài 2 — Khách không có đơn

Viết truy vấn chỉ dùng `NOT EXISTS`, không dùng `LEFT JOIN`:

```sql
SELECT c.customer_id, c.customer_name
FROM customers AS c
WHERE NOT EXISTS (
    SELECT 1
    FROM orders AS o
    WHERE o.customer_id = c.customer_id
)
ORDER BY c.customer_id;
```

**Đáp án:** **4 Dung**. Giải thích vì sao khách An có hai đơn nhưng chỉ cần tìm thấy một đơn là đủ để loại An.

### Bài 3 — Có đơn nhưng chưa thanh toán

Yêu cầu: khách có **ít nhất một đơn**, nhưng **không có đơn `PAID` nào**. Sử dụng một `EXISTS` và một `NOT EXISTS`:

```sql
SELECT c.customer_id, c.customer_name
FROM customers AS c
WHERE EXISTS (
    SELECT 1
    FROM orders AS o
    WHERE o.customer_id = c.customer_id
)
AND NOT EXISTS (
    SELECT 1
    FROM orders AS o
    WHERE o.customer_id = c.customer_id
      AND o.status = 'PAID'
)
ORDER BY c.customer_id;
```

**Đáp án:** **3 Chi**. Dung cũng chưa từng thanh toán nhưng không thỏa điều kiện đã có đơn.

### Bài 4 — Đơn có sản phẩm Chuot

Yêu cầu: lấy những đơn chứa `product_id = 30` mà **không dùng `JOIN` ở truy vấn ngoài**:

```sql
SELECT o.order_id, o.status
FROM orders AS o
WHERE EXISTS (
    SELECT 1
    FROM order_items AS oi
    WHERE oi.order_id = o.order_id
      AND oi.product_id = 30
)
ORDER BY o.order_id;
```

**Đáp án:** đơn **102, 105, 106**. Nếu thêm điều kiện `o.status = 'PAID'` ở truy vấn ngoài, chỉ còn **106**.

### Bài 5 — Sản phẩm chưa được đặt

Viết `NOT EXISTS` để tìm sản phẩm chưa có dòng đơn nào:

```sql
SELECT p.product_id, p.product_name
FROM products AS p
WHERE NOT EXISTS (
    SELECT 1
    FROM order_items AS oi
    WHERE oi.product_id = p.product_id
)
ORDER BY p.product_id;
```

**Đáp án:** **40 So tay**.

### Bài 6 — So sánh NOT IN chứa NULL

Giả sử tập loại trừ gồm mã khách 1 và `NULL`. Hãy dự đoán khác biệt giữa:

```sql
-- A
SELECT c.customer_id
FROM customers AS c
WHERE c.customer_id NOT IN (
    SELECT x.customer_id
    FROM (VALUES (1), (CAST(NULL AS INTEGER))) AS x(customer_id)
);

-- B
SELECT c.customer_id
FROM customers AS c
WHERE NOT EXISTS (
    SELECT 1
    FROM (VALUES (1), (CAST(NULL AS INTEGER))) AS x(customer_id)
    WHERE x.customer_id = c.customer_id
)
ORDER BY c.customer_id;
```

**Đáp án:** A **không trả hàng nào**; B trả **2, 3, 4, 5**. Hãy giải thích bằng `UNKNOWN` trong `NOT IN` và cách `NOT EXISTS` chỉ quan tâm hàng thực sự thỏa điều kiện.

### Bài 7 — Khách có từ hai đơn

Kết hợp `EXISTS`, `GROUP BY` và `HAVING COUNT(*) >= 2`:

```sql
SELECT c.customer_id, c.customer_name
FROM customers AS c
WHERE EXISTS (
    SELECT 1
    FROM orders AS o
    WHERE o.customer_id = c.customer_id
    GROUP BY o.customer_id
    HAVING COUNT(*) >= 2
)
ORDER BY c.customer_id;
```

**Đáp án:** **An và Chi**. Thử đổi thành `HAVING COUNT(*) >= 3`; tập kết quả sẽ rỗng.

### Bài 8 — Tìm lỗi quên tương quan

Một người viết:

```sql
SELECT c.customer_id
FROM customers AS c
WHERE NOT EXISTS (
    SELECT 1
    FROM orders AS o
    WHERE o.status = 'PAID'
);
```

Người đó muốn tìm khách chưa có đơn `PAID`. Hãy giải thích vì sao truy vấn rỗng trên dữ liệu mẫu, rồi sửa bằng cách bổ sung `o.customer_id = c.customer_id`.

**Đáp án sau khi sửa:** **Chi và Dung**.

### Bài 9 — Mọi sản phẩm trong tập yêu cầu

Viết truy vấn dùng **`NOT EXISTS` lồng `NOT EXISTS`** để tìm khách đã có đơn chứa **cả sản phẩm 10 và 20**. Bạn có thể dùng mẫu ở mục 10.

**Đáp án:** chỉ có **An**. Hãy tự giải thích theo câu “không tồn tại sản phẩm bắt buộc nào mà An chưa từng đặt”.

### Bài 10 — Hiển thị cờ thay vì lọc hàng

Yêu cầu: hiển thị **đầy đủ năm khách**, thêm cột `has_paid_order` bằng `'YES'` nếu tồn tại đơn `PAID`, ngược lại `'NO'`. Dùng `CASE WHEN EXISTS (...)`.

**Đáp án:** An YES; Binh YES; Chi NO; Dung NO; Em YES. Khác với `WHERE EXISTS`, câu này **không loại khách** mà chỉ tính thêm thông tin.

## 19. Tự xác định nên dùng EXISTS hay NOT EXISTS

| Câu hỏi nghiệp vụ | Biểu thức phù hợp | Cần chú ý |
|---|---|---|
| Khách **đã từng có đơn** chưa? | `EXISTS (đơn của khách)` | Mỗi khách vẫn một hàng nếu bảng ngoài là `customers` |
| Khách **chưa từng có đơn**? | `NOT EXISTS (đơn của khách)` | Khách không có đối tác được giữ |
| Khách **có đơn PAID**? | `EXISTS (đơn của khách AND status = 'PAID')` | Điều kiện trạng thái nằm trong subquery |
| Khách **không có đơn PAID**? | `NOT EXISTS (đơn của khách AND status = 'PAID')` | Bao gồm khách chưa có đơn nào |
| Khách **có đơn nhưng không có đơn PAID**? | `EXISTS (bất kỳ đơn) AND NOT EXISTS (đơn PAID)` | Hai điều kiện riêng |
| Sản phẩm **chưa xuất hiện trong bất kỳ đơn nào**? | `NOT EXISTS (dòng đơn tham chiếu sản phẩm)` | Dùng đúng quan hệ khóa |
| Đơn **có ít nhất một sản phẩm loại X**? | `EXISTS (dòng đơn sản phẩm X)` | Không làm nhân các hàng đơn |
| Khách có **ít nhất hai đơn**? | `EXISTS (nhóm đơn của khách HAVING COUNT(*) >= 2)` | Kiểm tra ngưỡng nên dùng tổng hợp phù hợp |
| Khách mua **mọi sản phẩm yêu cầu**? | `NOT EXISTS (sản phẩm yêu cầu mà NOT EXISTS (đơn chứa sản phẩm đó))` | Phủ định kép; cân nhắc tập yêu cầu rỗng |
| Hiển thị cờ có đơn PAID trên **mọi khách**? | `CASE WHEN EXISTS (...) THEN ... ELSE ... END` | Không lọc bỏ khách |

## Kết luận

**`EXISTS`** và **`NOT EXISTS`** là hai công cụ quan trọng của SQL để trả lời câu hỏi **“có hàng liên quan thỏa điều kiện hay không?”**:

- `EXISTS (subquery)` là `TRUE` khi truy vấn con có **ít nhất một hàng**.
- `NOT EXISTS (subquery)` là `TRUE` khi truy vấn con **không có hàng nào**.
- Với **truy vấn con có tương quan**, điều kiện như `o.customer_id = c.customer_id` bảo đảm câu hỏi tồn tại được đánh giá theo **đúng khách hoặc đối tượng đang xét**.
- `EXISTS` khác `JOIN` ở chỗ nó **lọc hàng ngoài**, không tạo một hàng kết quả mới cho từng bản ghi liên quan.
- `NOT EXISTS` thường trực quan và ít gặp bẫy `NULL` hơn `NOT IN` trong các bài toán kiểm tra không có quan hệ.
- Viết `EXISTS (SELECT 1 FROM ...)` khi chỉ cần biết có hàng; đừng vô tình thay bằng `EXISTS (SELECT COUNT(*))`, vì truy vấn con tổng hợp có thể luôn trả một hàng.
- Khi kết hợp nhiều `EXISTS`, `NOT EXISTS`, `GROUP BY` và `HAVING`, cần diễn đạt chính xác câu hỏi “**có ít nhất một**”, “**không có bất kỳ**” và “**có tất cả**”.

Thói quen quan trọng nhất là đọc truy vấn theo câu tự nhiên: **“Với mỗi hàng ở truy vấn ngoài, có tồn tại (hoặc không tồn tại) hàng nào ở truy vấn con thỏa toàn bộ điều kiện liên hệ hay không?”** Nếu có thể nói rõ câu đó, bạn thường có thể viết điều kiện kiểm tra tồn tại vừa đúng nghiệp vụ, vừa dễ đọc và dễ bảo trì.
