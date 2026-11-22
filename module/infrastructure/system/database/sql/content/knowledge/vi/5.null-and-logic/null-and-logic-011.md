# Các trường hợp đặc biệt của NULL trong IN và NOT IN

Trong SQL, biểu thức `IN` và `NOT IN` giúp kiểm tra một giá trị có thuộc một tập giá trị hay không. Cú pháp nhìn đơn giản:

```sql
WHERE status IN ('ACTIVE', 'PENDING')

WHERE customer_id NOT IN (SELECT customer_id FROM blocked_customers)
```

Nhưng khi xuất hiện **`NULL`**, kết quả có thể khác trực giác. Đặc biệt, một truy vấn `NOT IN` có thể **không trả về hàng nào** dù rõ ràng vẫn có những giá trị không nằm trong danh sách. Đây là hệ quả của **logic ba giá trị (three-valued logic)** trong SQL.

Bài học tập trung vào các trường hợp đặc biệt của `NULL` với `IN` và `NOT IN`: giá trị bên trái là `NULL`, phần tử bên phải là `NULL`, truy vấn con trả về `NULL`, danh sách rỗng, và cách dùng `NOT EXISTS` khi cần kiểm tra sự không tồn tại. Các đoạn SQL minh họa sử dụng cú pháp phổ biến; ví dụ ép kiểu `NULL::integer` được ghi rõ là cú pháp PostgreSQL.

## 1. Ôn lại ý nghĩa của NULL và logic ba giá trị

`NULL` trong SQL biểu thị **không có giá trị xác định** tại thời điểm xét dữ liệu; tùy ngữ cảnh, đó có thể là thông tin chưa biết, chưa được nhập hoặc không áp dụng. Nó **không đồng nghĩa** với số `0`, chuỗi rỗng `''` hay từ `'NULL'` trong chuỗi ký tự.

Phần lớn phép so sánh thông thường với `NULL` không cho kết quả `TRUE` hay `FALSE` mà cho **`UNKNOWN`**. Trong kết quả truy vấn, giá trị logic `UNKNOWN` thường được biểu diễn bằng SQL `NULL`.

```sql
SELECT
    2 = 2       AS bang_nhau,       -- TRUE
    2 = 3       AS khac_nhau,      -- FALSE
    2 = NULL    AS so_sanh_null,   -- NULL/UNKNOWN
    NULL = NULL AS hai_null;       -- NULL/UNKNOWN
```

Vì vậy, không thể dùng `= NULL` để tìm giá trị thiếu:

```sql
-- Sai về mặt ý định: điều kiện không thể TRUE khi giá trị là NULL.
SELECT *
FROM customers
WHERE email = NULL;

-- Đúng: kiểm tra trạng thái có/không có giá trị.
SELECT *
FROM customers
WHERE email IS NULL;
```

SQL có **ba kết quả logic**, không chỉ hai:

| Giá trị logic | Ý nghĩa |
| --- | --- |
| `TRUE` | Điều kiện được thỏa mãn. |
| `FALSE` | Điều kiện không được thỏa mãn. |
| `UNKNOWN` | Không thể xác định đúng/sai từ các giá trị hiện có, thường do `NULL`. |

### 1.1. NOT không biến UNKNOWN thành TRUE

| `p` | `NOT p` |
| --- | --- |
| `TRUE` | `FALSE` |
| `FALSE` | `TRUE` |
| `UNKNOWN` | `UNKNOWN` |

Đây là chìa khóa để hiểu `NOT IN`: nếu `IN` có kết quả `UNKNOWN`, đặt `NOT` bên ngoài vẫn là `UNKNOWN`, **không phải `TRUE`**.

### 1.2. AND, OR với UNKNOWN

| `p` | `q` | `p OR q` | `p AND q` |
| --- | --- | --- | --- |
| `TRUE` | `UNKNOWN` | `TRUE` | `UNKNOWN` |
| `FALSE` | `UNKNOWN` | `UNKNOWN` | `FALSE` |
| `UNKNOWN` | `UNKNOWN` | `UNKNOWN` | `UNKNOWN` |

Điều này giải thích vì sao một phép so sánh chắc chắn đúng có thể quyết định kết quả `IN`, còn một phép so sánh chưa biết có thể khiến `NOT IN` không kết luận được.

### 1.3. WHERE chỉ giữ hàng có điều kiện TRUE

Với `SELECT ... WHERE predicate`, hàng chỉ được đưa vào kết quả nếu biểu thức `predicate` là **`TRUE`**. Cả `FALSE` lẫn `UNKNOWN` đều không thỏa điều kiện lọc.

```sql
SELECT 1 AS value
WHERE 2 NOT IN (1, NULL);
-- Không có hàng kết quả: điều kiện là UNKNOWN, không phải TRUE.
```

Một truy vấn “không trả về hàng” không nhất thiết có nghĩa phép so sánh trả về `FALSE`. Có thể nó đã trả về `UNKNOWN` và bị `WHERE` loại.

## 2. IN hoạt động như thế nào khi có NULL?

Với một danh sách hữu hạn không rỗng, ta có thể hiểu phép kiểm tra một giá trị `x` như sau:

```sql
x IN (a, b, c)
```

Tương đương về mặt logic với:

```sql
x = a OR x = b OR x = c
```

Đây là **cách giải thích ngữ nghĩa**, không phải lời hứa DBMS sẽ đánh giá từng phép so sánh theo đúng thứ tự hoặc dùng phép OR vật lý khi tối ưu truy vấn.

Ví dụ:

```sql
SELECT
    1 IN (1, 3)      AS a,  -- TRUE
    2 IN (1, 3)      AS b,  -- FALSE
    1 IN (1, NULL)   AS c,  -- TRUE
    2 IN (1, NULL)   AS d,  -- UNKNOWN/NULL
    NULL IN (1, 3)   AS e,  -- UNKNOWN/NULL
    NULL IN (NULL)   AS f;  -- UNKNOWN/NULL
```

### 2.1. Có phần tử khớp: kết quả TRUE

```text
1 IN (1, NULL)

⇔ (1 = 1) OR (1 = NULL)
⇔ TRUE OR UNKNOWN
⇔ TRUE
```

`NULL` trong danh sách **không làm mất kết quả khớp đã biết**. Nếu có ít nhất một phép so sánh cho `TRUE`, `IN` trả `TRUE`.

### 2.2. Không có phần tử khớp, nhưng có NULL: kết quả UNKNOWN

```text
2 IN (1, NULL)

⇔ (2 = 1) OR (2 = NULL)
⇔ FALSE OR UNKNOWN
⇔ UNKNOWN
```

Kết quả **không phải `FALSE`** vì giá trị `NULL` chưa biết; SQL không thể kết luận chắc chắn rằng `2` không thuộc tập giá trị đó.

### 2.3. Giá trị bên trái là NULL

```text
NULL IN (1, 3)

⇔ (NULL = 1) OR (NULL = 3)
⇔ UNKNOWN OR UNKNOWN
⇔ UNKNOWN
```

Ngay cả:

```sql
SELECT NULL IN (NULL);
-- UNKNOWN/NULL, không phải TRUE.
```

Lý do là `NULL = NULL` cũng cho `UNKNOWN`. Nếu mục tiêu là tìm các hàng mà một cột đang thiếu giá trị, hãy dùng `IS NULL`, không dùng `IN (NULL)`.

### 2.4. Bảng kết quả tổng hợp cho IN

| Giá trị `x` | `x IN (1, 3)` | `x IN (1, NULL)` | Diễn giải |
| --- | --- | --- | --- |
| `1` | `TRUE` | `TRUE` | Có phần tử khớp. |
| `2` | `FALSE` | `UNKNOWN` | Không khớp; danh sách thứ hai chứa `NULL`. |
| `NULL` | `UNKNOWN` | `UNKNOWN` | Bên trái không có giá trị xác định. |

**Hệ quả khi lọc dữ liệu:** `WHERE x IN (1, NULL)` chỉ lấy các hàng mà `x = 1`; nó **không lấy hàng có `x IS NULL`**.

Nếu muốn chọn cả mã `1` và giá trị thiếu:

```sql
SELECT *
FROM sample_data
WHERE x = 1 OR x IS NULL;
```

Điều kiện `OR x IS NULL` biểu diễn rõ ý định nghiệp vụ hơn là đặt `NULL` vào danh sách `IN`.

## 3. NOT IN và “bẫy NULL”

`NOT IN` thường được đọc thành “không thuộc tập hợp”. Với danh sách không rỗng:

```sql
x NOT IN (a, b, c)
```

Tương đương về ngữ nghĩa với:

```sql
x <> a AND x <> b AND x <> c
```

Và cũng tương đương:

```sql
NOT (x IN (a, b, c))
```

**Phép AND là nguyên nhân tạo bẫy `NULL`**: một điều kiện `UNKNOWN` không tự biến thành `TRUE`.

### 3.1. Ví dụ đơn giản

```sql
SELECT
    1 NOT IN (1, 3)     AS a,  -- FALSE
    2 NOT IN (1, 3)     AS b,  -- TRUE
    1 NOT IN (1, NULL)  AS c,  -- FALSE
    2 NOT IN (1, NULL)  AS d,  -- UNKNOWN/NULL
    NULL NOT IN (1, 3)  AS e,  -- UNKNOWN/NULL
    NULL NOT IN (NULL)  AS f;  -- UNKNOWN/NULL
```

Xét riêng:

```text
2 NOT IN (1, NULL)

⇔ (2 <> 1) AND (2 <> NULL)
⇔ TRUE AND UNKNOWN
⇔ UNKNOWN
```

Con số `2` khác `1`, nhưng SQL **không thể xác nhận nó khác giá trị chưa biết `NULL`**. Vì thế biểu thức không cho `TRUE` và không qua được `WHERE`.

### 3.2. Bảng so sánh IN và NOT IN

| Giá trị `x` | `x IN (1, NULL)` | `x NOT IN (1, NULL)` |
| --- | --- | --- |
| `1` | `TRUE` | `FALSE` |
| `2` | `UNKNOWN` | `UNKNOWN` |
| `NULL` | `UNKNOWN` | `UNKNOWN` |

Khi danh sách có `NULL`, một giá trị `x` xác định và không khớp phần tử nào **cũng không tạo kết quả TRUE cho `NOT IN`**.

Trong một danh sách không rỗng có ít nhất một `NULL`:

- Nếu `x` khớp một giá trị đã biết, `x NOT IN (...)` là `FALSE`.
- Nếu không có giá trị đã biết nào khớp, `x NOT IN (...)` thường là `UNKNOWN`, bao gồm trường hợp `x` là `NULL`.
- Do đó **`WHERE x NOT IN (..., NULL)` có thể không trả về hàng nào**.

Điều này không chỉ xảy ra với `NULL` được viết trực tiếp; `NULL` đến từ **truy vấn con** còn nguy hiểm hơn vì dữ liệu có thể thay đổi theo thời gian.

## 4. Ví dụ thực tế: NOT IN với truy vấn con chứa NULL

Giả sử ứng dụng có bảng khách hàng và bảng đơn hàng. Cột `orders.customer_id` có thể là `NULL` do bản ghi đang chờ đối soát với một khách hàng.

Để tự chạy thử, tạo hai bảng mẫu:

```sql
CREATE TABLE customers (
    customer_id INTEGER PRIMARY KEY,
    full_name VARCHAR(100) NOT NULL
);

CREATE TABLE orders (
    order_id INTEGER PRIMARY KEY,
    customer_id INTEGER NULL
);

INSERT INTO customers (customer_id, full_name)
VALUES
    (1, 'An'),
    (2, 'Bình'),
    (3, 'Chi'),
    (4, 'Dung');

INSERT INTO orders (order_id, customer_id)
VALUES
    (101, 1),
    (102, 3),
    (103, NULL);
```

Dữ liệu:

**`customers`**

| customer_id | full_name |
| ---: | --- |
| 1 | An |
| 2 | Bình |
| 3 | Chi |
| 4 | Dung |

**`orders`**

| order_id | customer_id |
| ---: | ---: |
| 101 | 1 |
| 102 | 3 |
| 103 | `NULL` |

Muốn tìm “khách hàng chưa có đơn hàng”, người mới học thường viết:

```sql
SELECT c.customer_id, c.full_name
FROM customers AS c
WHERE c.customer_id NOT IN (
    SELECT o.customer_id
    FROM orders AS o
)
ORDER BY c.customer_id;
```

Có vẻ kết quả phải là **Bình (2)** và **Dung (4)**. Nhưng truy vấn trên **không trả về hàng nào** vì truy vấn con trả tập giá trị `(1, 3, NULL)`.

Xét khách hàng Bình:

```text
2 NOT IN (1, 3, NULL)

⇔ 2 <> 1 AND 2 <> 3 AND 2 <> NULL
⇔ TRUE AND TRUE AND UNKNOWN
⇔ UNKNOWN
```

Khách hàng Dung cũng tương tự. Khách hàng An và Chi thì có giá trị khớp, nên `NOT IN` trả `FALSE`. Không có khách hàng nào thỏa `TRUE`.

### 4.1. Điều gì xảy ra với IN ở cùng truy vấn?

```sql
SELECT c.customer_id, c.full_name
FROM customers AS c
WHERE c.customer_id IN (
    SELECT o.customer_id
    FROM orders AS o
)
ORDER BY c.customer_id;
```

Kết quả:

| customer_id | full_name |
| ---: | --- |
| 1 | An |
| 3 | Chi |

`IN` vẫn tìm được các giá trị **khớp thật** là `1` và `3`. Đối với `2`, `4`, kết quả biểu thức có thể là `UNKNOWN`, nhưng mục tiêu của `WHERE` là chỉ lấy những hàng đúng; vì vậy các hàng không khớp bị loại như mong đợi.

### 4.2. Tình huống phát sinh trong hệ thống thật

Ban đầu, nếu `orders.customer_id` chỉ có `1` và `3`, truy vấn `NOT IN` có thể trả chính xác `2` và `4`. Sau đó một bản ghi `orders` có `customer_id = NULL` được nhập, truy vấn **đột ngột trả rỗng**.

Như vậy, hành vi phụ thuộc không chỉ vào những giá trị được tham chiếu mà còn vào việc truy vấn con **có bất kỳ `NULL` nào hay không**.

Đối với các truy vấn kiểm tra sự không tồn tại, phải quyết định rõ `NULL` trong dữ liệu con có ý nghĩa gì trước khi chọn cách viết.

## 5. Hai cách diễn đạt “không tồn tại”: lọc NULL hoặc NOT EXISTS

### 5.1. Cách 1: loại NULL khỏi truy vấn con

Vì `customers.customer_id` là khóa chính nên luôn khác `NULL`. Trong ví dụ, ta có thể lọc các mã khách hàng chưa xác định khỏi tập so sánh:

```sql
SELECT c.customer_id, c.full_name
FROM customers AS c
WHERE c.customer_id NOT IN (
    SELECT o.customer_id
    FROM orders AS o
    WHERE o.customer_id IS NOT NULL
)
ORDER BY c.customer_id;
```

Kết quả:

| customer_id | full_name |
| ---: | --- |
| 2 | Bình |
| 4 | Dung |

Tập bên phải trở thành `(1, 3)`. Vì bên trái là khóa chính `NOT NULL`, `2 NOT IN (1, 3)` và `4 NOT IN (1, 3)` đều trả `TRUE`.

**Điều kiện áp dụng:** Cách này phù hợp nếu giá trị `NULL` ở bảng con thực sự cần được **bỏ qua** và biểu thức bên trái được biết là **không `NULL`**. Nếu cột bên trái cũng có thể `NULL`, cần làm rõ cách xử lý riêng.

### 5.2. Cách 2: dùng NOT EXISTS

`NOT EXISTS` kiểm tra **không có hàng nào** trong truy vấn con thỏa điều kiện tương quan:

```sql
SELECT c.customer_id, c.full_name
FROM customers AS c
WHERE NOT EXISTS (
    SELECT 1
    FROM orders AS o
    WHERE o.customer_id = c.customer_id
)
ORDER BY c.customer_id;
```

Cũng trả:

| customer_id | full_name |
| ---: | --- |
| 2 | Bình |
| 4 | Dung |

Với mỗi khách hàng, truy vấn con hỏi “có bất kỳ đơn hàng nào có mã khách hàng bằng mã hiện tại không?”. Nếu có ít nhất một hàng khớp, `EXISTS` là `TRUE` và `NOT EXISTS` là `FALSE`; nếu không có hàng nào khớp, `EXISTS` là `FALSE` và `NOT EXISTS` là `TRUE`.

`EXISTS` **không quan tâm giá trị được chọn là gì**, chỉ quan tâm truy vấn con có hàng hay không. Vì vậy viết `SELECT 1`, `SELECT NULL` hoặc chọn một cột đều có cùng ý nghĩa về sự tồn tại của hàng, miễn các phần khác của truy vấn không thay đổi.

### 5.3. Vì sao NOT EXISTS không bị NULL trong dữ liệu con làm “nhiễm độc”?

Với khách hàng Bình, điều kiện tương quan là:

```sql
o.customer_id = 2
```

Đối chiếu từng hàng đơn hàng:

- `1 = 2` → `FALSE`.
- `3 = 2` → `FALSE`.
- `NULL = 2` → `UNKNOWN`.

Không điều kiện nào là `TRUE` nên truy vấn con **không trả hàng**, `EXISTS` là `FALSE` và `NOT EXISTS` là `TRUE`.

Khác biệt chính nằm ở phép kiểm tra:

- `NOT IN` yêu cầu **mọi so sánh với tập giá trị** đều được xác nhận là không bằng nhau.
- `NOT EXISTS` chỉ yêu cầu **không tìm được hàng nào thỏa điều kiện khớp**.

Khi mục đích nghiệp vụ là “không có bản ghi liên quan”, `NOT EXISTS` thường thể hiện trực tiếp ý định hơn.

## 6. NOT EXISTS không luôn tương đương NOT IN

Đừng thay mọi `NOT IN` bằng `NOT EXISTS` một cách máy móc. Hai biểu thức có thể khác nhau khi **cột bên trái là `NULL`**, khi **cột bên phải có `NULL`**, hoặc khi **truy vấn con rỗng**.

Giả sử có bảng:

```sql
CREATE TABLE requests (
    request_id INTEGER PRIMARY KEY,
    referred_customer_id INTEGER NULL
);

INSERT INTO requests (request_id, referred_customer_id)
VALUES
    (201, 1),
    (202, 2),
    (203, NULL);
```

Để tìm yêu cầu không tham chiếu khách hàng có đơn, có thể viết:

```sql
SELECT r.request_id
FROM requests AS r
WHERE NOT EXISTS (
    SELECT 1
    FROM orders AS o
    WHERE o.customer_id = r.referred_customer_id
)
ORDER BY r.request_id;
```

Kết quả là `202` **và `203`**:

- Yêu cầu `202` tham chiếu khách hàng `2`, không có đơn.
- Yêu cầu `203` có `referred_customer_id = NULL`; phép so sánh với mọi mã đơn hàng đều không `TRUE`, nên không tìm thấy bản ghi khớp.

Nếu nghiệp vụ chỉ muốn những yêu cầu **có mã khách hàng xác định nhưng chưa có đơn**, thêm điều kiện:

```sql
SELECT r.request_id
FROM requests AS r
WHERE r.referred_customer_id IS NOT NULL
  AND NOT EXISTS (
      SELECT 1
      FROM orders AS o
      WHERE o.customer_id = r.referred_customer_id
  )
ORDER BY r.request_id;
-- Chỉ trả request_id = 202.
```

### 6.1. Khi muốn coi hai NULL là “khớp”

Theo phép bằng thông thường, `NULL = NULL` cho `UNKNOWN`, nên một truy vấn `NOT EXISTS` dùng `=` **không coi hai giá trị thiếu là một cặp khớp**.

Nếu **quy tắc nghiệp vụ thật sự** yêu cầu xem hai `NULL` tương đương khi ghép dữ liệu, một số hệ quản trị hỗ trợ phép so sánh có ngữ nghĩa như sau:

```sql
-- PostgreSQL: coi NULL và NULL là không khác nhau.
SELECT
    NULL IS NOT DISTINCT FROM NULL AS null_khop_null,
    10 IS NOT DISTINCT FROM NULL   AS so_khac_null;
-- TRUE, FALSE
```

Có thể áp dụng trong truy vấn tương quan:

```sql
-- PostgreSQL: xem hai NULL là khớp nhau theo quy tắc này.
SELECT r.request_id
FROM requests AS r
WHERE NOT EXISTS (
    SELECT 1
    FROM orders AS o
    WHERE o.customer_id IS NOT DISTINCT FROM r.referred_customer_id
)
ORDER BY r.request_id;
```

Vì bảng `orders` mẫu có một hàng `customer_id = NULL`, yêu cầu `203` sẽ được xem là **có một hàng khớp** và không xuất hiện trong kết quả `NOT EXISTS` này.

Đó là **một quyết định ngữ nghĩa khác**: không phải mặc định mọi `NULL` đại diện cùng một khách hàng. Chỉ dùng so sánh kiểu này khi có lý do nghiệp vụ rõ ràng. Cú pháp hỗ trợ khác nhau giữa các DBMS; ví dụ MySQL có toán tử so sánh null-safe `<=>`.

### 6.2. Khi nào có thể xem NOT IN và NOT EXISTS là tương đương?

Với tập giá trị so sánh đơn cột và điều kiện bằng thông thường, hai cách viết thường cho cùng tập hàng khi:

1. Giá trị bên trái **không bao giờ `NULL`**.
2. Các giá trị bên phải **không bao giờ `NULL`**, do ràng buộc `NOT NULL` hoặc đã lọc hợp lệ.
3. Điều kiện truy vấn con mô tả đúng phép so sánh `=` với cùng tập dữ liệu.

Khi các giả định ấy không chắc chắn, phải phân tích các trường hợp cụ thể. Việc thêm `IS NOT NULL` vào cả hai bên là một **lựa chọn nghiệp vụ**, không phải “vá lỗi” đúng trong mọi tình huống.

## 7. Trường hợp đặc biệt: truy vấn con rỗng

Một ngoại lệ rất quan trọng: **`IN` và `NOT IN` với truy vấn con không có hàng** có kết quả xác định, ngay cả khi giá trị bên trái là `NULL`.

Theo ngữ nghĩa SQL:

- `x IN (tập rỗng)` → `FALSE`.
- `x NOT IN (tập rỗng)` → `TRUE`.

Ví dụ trên PostgreSQL:

```sql
SELECT
    5 IN (
        SELECT o.customer_id
        FROM orders AS o
        WHERE 1 = 0
    ) AS in_empty,
    5 NOT IN (
        SELECT o.customer_id
        FROM orders AS o
        WHERE 1 = 0
    ) AS not_in_empty;

-- in_empty = FALSE
-- not_in_empty = TRUE
```

Ngay cả giá trị bên trái `NULL`:

```sql
-- PostgreSQL: ép NULL về kiểu integer để minh họa rõ.
SELECT
    NULL::integer IN (
        SELECT customer_id FROM orders WHERE 1 = 0
    ) AS null_in_empty,
    NULL::integer NOT IN (
        SELECT customer_id FROM orders WHERE 1 = 0
    ) AS null_not_in_empty;

-- null_in_empty     = FALSE
-- null_not_in_empty = TRUE
```

Tại sao không trả `UNKNOWN`? Vì **không có bất kỳ hàng bên phải nào để thực hiện so sánh gây `UNKNOWN`**. Xét theo lượng từ logic, không có phần tử nào thỏa “có một phần tử bằng x” nên `IN` sai; đồng thời không có phần tử nào vi phạm “mọi phần tử đều khác x” nên `NOT IN` đúng.

### 7.1. Đừng nhầm tập rỗng với tập chỉ có NULL

| Tập bên phải | `2 IN (...)` | `2 NOT IN (...)` |
| --- | --- | --- |
| Không có hàng | `FALSE` | `TRUE` |
| Một hàng mang `NULL` | `UNKNOWN` | `UNKNOWN` |
| Hai hàng `1` và `3` | `FALSE` | `TRUE` |
| Hai hàng `1` và `NULL` | `UNKNOWN` | `UNKNOWN` |
| Một hàng `2` và một hàng `NULL` | `TRUE` | `FALSE` |

**Tập rỗng** và **tập chứa một giá trị thiếu** là hai trường hợp hoàn toàn khác nhau.

### 7.2. IN () không phải cú pháp thay thế cho tập rỗng

Viết `WHERE id IN ()` thường **không hợp lệ về cú pháp** trong các DBMS thông dụng như PostgreSQL. Đó không phải cách minh họa tập rỗng một cách di động.

Khi ứng dụng tạo truy vấn có danh sách tham số tùy biến, cần xử lý **danh sách rỗng ở tầng ứng dụng/trình tạo SQL** (ví dụ dùng điều kiện `FALSE` cho yêu cầu `IN` rỗng, hoặc `TRUE` cho yêu cầu `NOT IN` rỗng khi đó thật sự là ý nghĩa nghiệp vụ). Đừng tự ghép ra câu lệnh `IN ()` rồi giả định mọi DBMS xử lý được.

## 8. IN và NOT IN với danh sách từ tham số ứng dụng

Một ứng dụng thường nhận danh sách lọc từ giao diện:

```text
selectedStatuses = ["ACTIVE", "PENDING"]
```

Rồi gửi câu truy vấn tương ứng bằng **tham số ràng buộc** thay vì nối chuỗi SQL tùy tiện:

```sql
-- Minh họa SQL sau khi trình điều khiển/ORM bung danh sách
SELECT *
FROM tasks
WHERE status IN (?, ?);
```

Có ba tình huống cần xử lý riêng:

### 8.1. Danh sách chứa NULL

Nếu ứng dụng đưa ra:

```text
selectedStatuses = ["ACTIVE", NULL]
```

Thì điều kiện tương đương:

```sql
WHERE status IN ('ACTIVE', NULL)
```

**Không lấy những hàng có `status IS NULL`.** Nếu người dùng chọn cả “ACTIVE” và “Chưa có trạng thái”, truy vấn cần mô tả rõ:

```sql
SELECT *
FROM tasks
WHERE status = 'ACTIVE'
   OR status IS NULL;
```

Với danh sách nhiều giá trị, ứng dụng có thể **tách các giá trị có thực và cờ chọn NULL**: dùng `IN` cho các giá trị không `NULL`, và thêm `OR status IS NULL` nếu muốn lấy hàng thiếu trạng thái.

### 8.2. Danh sách loại trừ chứa NULL

`WHERE status NOT IN ('CANCELLED', NULL)` có thể không lấy được cả các trạng thái khác `CANCELLED`.

Nếu người dùng muốn **loại bỏ CANCELLED và loại luôn hàng thiếu trạng thái**, có thể viết:

```sql
WHERE status IS NOT NULL
  AND status NOT IN ('CANCELLED')
```

Nếu muốn **loại bỏ CANCELLED nhưng vẫn giữ hàng thiếu trạng thái**, ý định khác:

```sql
WHERE status IS NULL
   OR status NOT IN ('CANCELLED')
```

Với từng yêu cầu, hãy chọn điều kiện phù hợp thay vì cho `NULL` vào `NOT IN` rồi mong nó được diễn giải như một phần tử bình thường.

### 8.3. Danh sách rỗng

Nếu người dùng chưa chọn bất kỳ trạng thái nào, ứng dụng phải quyết định đó là:

- **Không áp dụng bộ lọc** → bỏ điều kiện lọc, trả những hàng khác tùy điều kiện.
- **Không chọn trạng thái nào nên không có hàng** → tạo một điều kiện luôn `FALSE`.
- **Danh sách loại trừ rỗng** → xét về tập hợp là không loại giá trị nào, nhưng có thể còn quy tắc riêng đối với `NULL`.

Các ý nghĩa nghiệp vụ này **không tương đương**. Việc xử lý danh sách rỗng cần được thiết kế ở cấp API/trình xây dựng truy vấn.

## 9. Truy vấn con, EXISTS, và quy tắc chọn hàng

`IN`/`NOT IN` với truy vấn con kiểm tra **giá trị**, còn `EXISTS`/`NOT EXISTS` kiểm tra **sự tồn tại của hàng**.

```sql
-- Kiểm tra giá trị customer_id có nằm trong tập được trả về không.
SELECT c.customer_id
FROM customers AS c
WHERE c.customer_id IN (
    SELECT o.customer_id
    FROM orders AS o
);

-- Kiểm tra tồn tại ít nhất một hàng orders phù hợp.
SELECT c.customer_id
FROM customers AS c
WHERE EXISTS (
    SELECT 1
    FROM orders AS o
    WHERE o.customer_id = c.customer_id
);
```

Với cột `customers.customer_id` là khóa chính không `NULL` trong ví dụ, hai truy vấn đều trả khách hàng có đơn (`1` và `3`). Tuy nhiên, cách suy luận khác nhau:

- `IN`: chỉ cần **một giá trị khớp** thì là `TRUE`; nếu không khớp nhưng có so sánh `UNKNOWN`, kết quả có thể `UNKNOWN`.
- `EXISTS`: nếu truy vấn con có **ít nhất một hàng**, trả `TRUE`; nếu không có hàng, trả `FALSE`. Bản thân `EXISTS` không có kết quả `UNKNOWN`.
- `NOT IN`: chỉ `TRUE` khi có thể xác định giá trị không bằng **mọi phần tử** trong tập.
- `NOT EXISTS`: trả `TRUE` khi **không có hàng phù hợp**, kể cả khi một số phép so sánh trong điều kiện con là `UNKNOWN` và vì thế không tạo hàng khớp.

### 9.1. EXISTS không kiểm tra giá trị được SELECT

```sql
SELECT EXISTS (
    SELECT NULL
);
-- TRUE: truy vấn con có một hàng, dù giá trị được chọn là NULL.
```

```sql
SELECT EXISTS (
    SELECT NULL
    WHERE 1 = 0
);
-- FALSE: truy vấn con không có hàng.
```

Không nên nhầm `EXISTS (SELECT NULL)` với `NULL IN (...)`. Một bên hỏi **có hàng hay không**, bên kia hỏi **giá trị có khớp theo phép so sánh SQL hay không**.

### 9.2. Không cần dựa vào thứ tự hoặc số lần xuất hiện

Với `IN` và `EXISTS` trong kiểm tra sự tồn tại, số lần giá trị khớp xuất hiện không làm đổi tính đúng/sai; một giá trị `1` lặp nhiều lần vẫn chỉ cung cấp bằng chứng “có ít nhất một bản ghi khớp”.

Không cần dùng `ORDER BY` trong truy vấn con chỉ nhằm kiểm tra thuộc tập hoặc sự tồn tại. Thứ tự các hàng không quyết định ý nghĩa của `IN`, `NOT IN` hay `EXISTS`.

## 10. Trường hợp nâng cao: IN/NOT IN với nhiều cột

Một số DBMS, trong đó có PostgreSQL, hỗ trợ so sánh **bộ giá trị (row value)**:

```sql
SELECT (1, 2) IN ((1, 2), (3, 4));
-- TRUE
```

Với so sánh hai bộ giá trị bằng `=`, nếu có **ít nhất một cặp thành phần chắc chắn khác nhau**, cả phép bằng có thể được xác định là `FALSE`; nếu các thành phần đã biết đều bằng nhau nhưng còn thành phần `NULL` chưa xác định, kết quả có thể `UNKNOWN`.

Ví dụ trên PostgreSQL:

```sql
SELECT
    (3, 8) IN ((3, NULL))     AS a,
    (9, 8) IN ((3, NULL))     AS b,
    (3, 8) NOT IN ((3, NULL)) AS c,
    (9, 8) NOT IN ((3, NULL)) AS d;

-- a = NULL/UNKNOWN
-- b = FALSE
-- c = NULL/UNKNOWN
-- d = TRUE
```

Giải thích:

- `(3, 8) = (3, NULL)`: thành phần đầu khớp, thành phần sau không thể biết → `UNKNOWN`.
- `(9, 8) = (3, NULL)`: thành phần đầu chắc chắn khác (`9 <> 3`) → `FALSE` dù thành phần sau chứa `NULL`.
- Phủ định hai kết quả trên lần lượt thành `UNKNOWN` và `TRUE`.

Vì thế không thể áp dụng máy móc câu “hễ danh sách `NOT IN` có `NULL` thì luôn không có hàng” cho **mọi phép so sánh bộ giá trị**. Điều đó đúng với bẫy thường gặp của **một cột và danh sách vô hướng**; với nhiều cột, một thành phần đã chắc chắn khác có thể khiến cả bộ so sánh là `FALSE`.

Khi làm việc với khóa ghép có trường được phép `NULL`, cần phân tích riêng ngữ nghĩa row comparison và cách xác định “hai khóa có khớp” theo nghiệp vụ.

## 11. NULL trong CASE, CHECK và điều kiện JOIN liên quan tới IN

Những trường hợp này giúp nhận ra vì sao `UNKNOWN` có thể dẫn tới kết quả ngoài dự kiến.

### 11.1. CASE WHEN coi UNKNOWN giống nhánh không được chọn

```sql
SELECT CASE
    WHEN 2 NOT IN (1, NULL) THEN 'khong thuoc'
    WHEN 2 IN (1, NULL) THEN 'thuoc'
    ELSE 'chua xac dinh'
END AS ket_luan;

-- chua xac dinh
```

Cả hai điều kiện `WHEN` đều `UNKNOWN` nên không điều kiện nào được chọn; truy vấn đi vào `ELSE`.

Có thể kiểm tra cụ thể trạng thái bằng các phép kiểm tra logic được hỗ trợ trong DBMS, hoặc viết rõ `IS NULL` cho dữ liệu đầu vào tùy yêu cầu.

### 11.2. CHECK không loại UNKNOWN theo cách WHERE làm

Trong SQL, ràng buộc `CHECK` từ chối hàng khi điều kiện là **`FALSE`**; điều kiện `TRUE` hoặc `UNKNOWN` thường được chấp nhận. Điều này khác `WHERE`, vốn chỉ giữ `TRUE`.

Ví dụ trên PostgreSQL:

```sql
CREATE TABLE sample_checks (
    value INTEGER,
    CONSTRAINT value_allowed CHECK (value IN (1, 2))
);

INSERT INTO sample_checks (value) VALUES (1);    -- Thành công
INSERT INTO sample_checks (value) VALUES (NULL); -- Thành công
-- INSERT ... VALUES (3);                       -- Vi phạm CHECK
```

Nếu cột bắt buộc có giá trị, cần thêm `NOT NULL`. Tương tự, một `CHECK` dùng `NOT IN (..., NULL)` thường không biểu thị đúng mục tiêu hạn chế giá trị.

### 11.3. JOIN cũng không coi UNKNOWN là khớp

Khi viết:

```sql
SELECT *
FROM requests AS r
JOIN orders AS o
  ON r.referred_customer_id = o.customer_id;
```

Các hàng có `NULL` ở cả hai cột cũng **không tự ghép với nhau** bằng `=`. Trong điều kiện ghép thông thường, chỉ cặp có điều kiện `TRUE` mới khớp; `UNKNOWN` không tạo cặp hàng.

Đây là cùng nguyên tắc logic khiến `IN (NULL)` không tìm ra dữ liệu có `NULL`.

## 12. Cách kiểm tra và phòng tránh lỗi

Khi một truy vấn `NOT IN` trả ít hàng hơn dự kiến, đặc biệt trả rỗng, hãy lần lượt kiểm tra nguồn dữ liệu và ý nghĩa nghiệp vụ.

### 12.1. Xác định truy vấn con có NULL không

```sql
SELECT
    COUNT(*) AS total_rows,
    SUM(CASE WHEN customer_id IS NULL THEN 1 ELSE 0 END)
        AS null_customer_ids
FROM orders;
```

Trong dữ liệu mẫu:

| total_rows | null_customer_ids |
| ---: | ---: |
| 3 | 1 |

Từ đó biết được truy vấn `SELECT customer_id FROM orders` chứa một `NULL`. Một phép `NOT IN` không lọc phần tử này có nguy cơ trả `UNKNOWN` cho mọi giá trị bên trái chưa có phần tử khớp chắc chắn.

### 12.2. Kiểm tra cột bên trái có thể NULL không

Nếu cột bên trái là `PRIMARY KEY` hoặc có ràng buộc `NOT NULL`, ta có cơ sở để loại đi một trường hợp bất định. Nếu cột bên trái có thể `NULL`, phải quyết định:

- Giá trị thiếu cần loại khỏi kết quả?
- Giá trị thiếu cần giữ lại?
- Hay thiếu giá trị phải được xử lý như một nhóm nghiệp vụ riêng?

Không có một công thức `NOT IN` nào đúng cho mọi câu trả lời.

### 12.3. Dùng ràng buộc dữ liệu khi nghiệp vụ cho phép

Nếu mỗi đơn hàng **bắt buộc** thuộc một khách hàng đã biết, có thể thiết kế:

```sql
CREATE TABLE strict_orders (
    order_id INTEGER PRIMARY KEY,
    customer_id INTEGER NOT NULL
        REFERENCES customers(customer_id)
);
```

Ràng buộc `NOT NULL` giúp loại khả năng xuất hiện `NULL` trong cột dùng làm khóa tham chiếu. Nhưng **không tự thêm `NOT NULL`** nếu nghiệp vụ thật sự cần ghi nhận đơn hàng chưa xác định khách hàng.

### 12.4. Chọn truy vấn theo ý nghĩa

| Mục đích | Cách viết thường thích hợp |
| --- | --- |
| Tìm những hàng có mã nằm trong danh sách xác định, không có `NULL` | `WHERE id IN (...)` |
| Tìm mã nằm trong danh sách, đồng thời lấy cả hàng có mã thiếu | `WHERE id IN (...) OR id IS NULL` |
| Loại trừ một danh sách mã được bảo đảm không có `NULL`; cột trái cũng không `NULL` | `WHERE id NOT IN (...)` |
| Tìm những hàng **không có** bản ghi tương ứng ở bảng khác | `WHERE NOT EXISTS (SELECT 1 ... WHERE inner.id = outer.id)` |
| Muốn giữ hàng có khóa ngoài `NULL` khi không có bản ghi khớp | `NOT EXISTS` với `=`, nếu đó là ý nghĩa nghiệp vụ |
| Muốn loại hàng có khóa ngoài `NULL` khỏi kết quả “không có bản ghi khớp” | Thêm `outer.id IS NOT NULL AND NOT EXISTS (...)` |
| Muốn coi hai `NULL` là tương đương | So sánh null-safe theo hỗ trợ của DBMS, ví dụ PostgreSQL `IS NOT DISTINCT FROM` |
| Truy vấn con `NOT IN` có thể trả `NULL` nhưng cần bỏ qua chúng | Lọc `IS NOT NULL` ở truy vấn con, đồng thời xét ngữ nghĩa cột trái |

### 12.5. Kiểm tra kế hoạch thực thi sau khi chọn ngữ nghĩa đúng

`NOT IN`, `NOT EXISTS` và cách dùng phép nối ngoài để tìm hàng không khớp có thể được DBMS tối ưu khác nhau theo dữ liệu, chỉ mục và thống kê. **Không có quy tắc phổ quát “`NOT EXISTS` luôn nhanh hơn `NOT IN`”**.

Ưu tiên thứ nhất là diễn đạt **đúng kết quả khi có `NULL`**. Sau đó, với dữ liệu thực tế, xem kế hoạch truy vấn (ví dụ `EXPLAIN` trên PostgreSQL), chỉ mục liên quan và khối lượng dữ liệu để tối ưu nếu cần.

## 13. Bài tập thực hành và lời giải

Hãy thử dự đoán giá trị logic trước khi chạy SQL. Ở bảng đáp án, `UNKNOWN` tương ứng giá trị SQL `NULL` khi hiển thị một biểu thức Boolean.

### Bài 1. Đánh giá từng biểu thức

| Biểu thức | Kết quả |
| --- | --- |
| `3 IN (1, 3, NULL)` | `TRUE` |
| `3 NOT IN (1, 3, NULL)` | `FALSE` |
| `4 IN (1, 3, NULL)` | `UNKNOWN` |
| `4 NOT IN (1, 3, NULL)` | `UNKNOWN` |
| `NULL IN (1, 3)` | `UNKNOWN` |
| `NULL NOT IN (1, 3)` | `UNKNOWN` |
| `4 NOT IN (1, 3)` | `TRUE` |

Tự chạy:

```sql
SELECT
    3 IN (1, 3, NULL)     AS q1,
    3 NOT IN (1, 3, NULL) AS q2,
    4 IN (1, 3, NULL)     AS q3,
    4 NOT IN (1, 3, NULL) AS q4,
    NULL IN (1, 3)        AS q5,
    NULL NOT IN (1, 3)    AS q6,
    4 NOT IN (1, 3)       AS q7;
```

### Bài 2. Vì sao NOT IN trả rỗng?

Cho bảng `orders` có `customer_id = 1`, `customer_id = 3` và một hàng `customer_id = NULL`. Hỏi truy vấn:

```sql
SELECT customer_id
FROM customers
WHERE customer_id NOT IN (
    SELECT customer_id
    FROM orders
);
```

**Đáp án:** Không trả hàng nào. Mã `1` và `3` có giá trị khớp, nên `NOT IN` là `FALSE`; mã `2` và `4` không khớp mã đã biết nhưng gặp `NULL` nên `NOT IN` là `UNKNOWN`. `WHERE` loại cả `FALSE` và `UNKNOWN`.

### Bài 3. Viết lại truy vấn tìm khách hàng chưa có đơn

**Lời giải bằng `NOT EXISTS`:**

```sql
SELECT c.customer_id, c.full_name
FROM customers AS c
WHERE NOT EXISTS (
    SELECT 1
    FROM orders AS o
    WHERE o.customer_id = c.customer_id
)
ORDER BY c.customer_id;
```

**Kết quả:** Bình (`2`) và Dung (`4`).

**Lời giải bằng `NOT IN` sau khi lọc `NULL`:**

```sql
SELECT c.customer_id, c.full_name
FROM customers AS c
WHERE c.customer_id NOT IN (
    SELECT o.customer_id
    FROM orders AS o
    WHERE o.customer_id IS NOT NULL
)
ORDER BY c.customer_id;
```

Hai truy vấn cho cùng kết quả trong dữ liệu mẫu, vì khóa chính `customers.customer_id` không thể `NULL`.

### Bài 4. Một truy vấn con rỗng trả gì?

```sql
SELECT
    9 IN (
        SELECT customer_id FROM orders WHERE 1 = 0
    ) AS a,
    9 NOT IN (
        SELECT customer_id FROM orders WHERE 1 = 0
    ) AS b;
```

**Đáp án:** `a = FALSE` và `b = TRUE`. Một truy vấn con **không có hàng** khác với truy vấn con **có một hàng `NULL`**.

### Bài 5. Chọn điều kiện cho trạng thái chưa xác định

Giả sử bảng `tasks` có cột `status` có thể `NULL`. Viết điều kiện cho ba yêu cầu:

1. Lấy hàng có trạng thái `'NEW'` hoặc chưa có trạng thái.
2. Lấy hàng có trạng thái xác định và khác `'CANCELLED'`.
3. Lấy hàng khác `'CANCELLED'`, **kể cả** hàng chưa có trạng thái.

**Lời giải:**

```sql
-- 1. NEW hoặc NULL
WHERE status = 'NEW' OR status IS NULL

-- 2. Có giá trị và không phải CANCELLED
WHERE status IS NOT NULL AND status <> 'CANCELLED'

-- 3. Không phải CANCELLED, giữ cả NULL
WHERE status <> 'CANCELLED' OR status IS NULL
```

### Bài 6. Lý giải sự khác biệt khi cột bên trái là NULL

Với một hàng `requests.referred_customer_id = NULL` và một bảng `orders` có dữ liệu, xét:

```sql
-- Biểu thức A
WHERE referred_customer_id NOT IN (
    SELECT customer_id FROM orders
)

-- Biểu thức B (tương quan với hàng requests hiện tại)
WHERE NOT EXISTS (
    SELECT 1
    FROM orders AS o
    WHERE o.customer_id = requests.referred_customer_id
)
```

**Đáp án:** Nếu truy vấn con `A` không rỗng, `A` cho `UNKNOWN` với giá trị trái `NULL` và bị loại khỏi `WHERE`. Trong `B`, mọi phép so sánh bằng với `NULL` đều không `TRUE`, không tìm thấy hàng khớp, nên `NOT EXISTS` trả `TRUE` và hàng được giữ. Đây là lý do phải xác định rõ cách xử lý `NULL` ở **bên trái** khi viết lại truy vấn.

## 14. Những nguyên tắc cần giữ khi đọc IN và NOT IN

- `NULL` không so sánh bằng `TRUE` hoặc `FALSE` với toán tử `=`, `<>` thông thường; so sánh có thể thành `UNKNOWN`.
- `IN` có phần tử khớp chắc chắn thì là `TRUE`, ngay cả khi danh sách có `NULL`. Nếu không khớp và có khả năng so sánh `UNKNOWN`, kết quả có thể `UNKNOWN`.
- `NOT IN` là phủ định logic của `IN`; `NOT UNKNOWN` vẫn là `UNKNOWN`. Với danh sách vô hướng không rỗng chứa `NULL`, giá trị không khớp phần tử đã biết thường **không qua được `WHERE`**.
- `NOT EXISTS` hỏi “có hàng khớp hay không” nên là lựa chọn rõ ràng khi tìm bản ghi **không có quan hệ tương ứng**, nhưng vẫn phải xác định cách xử lý khóa `NULL` ở bảng ngoài.
- **Truy vấn con rỗng** tạo `IN = FALSE` và `NOT IN = TRUE`, kể cả với giá trị bên trái `NULL`; nó không giống tập chỉ chứa `NULL`.
- `IS NULL`, `IS NOT NULL` và phép so sánh null-safe khi cần là công cụ phù hợp để diễn đạt ý định về dữ liệu thiếu. Quyết định lấy hay loại hàng `NULL` phải xuất phát từ yêu cầu nghiệp vụ.

Nắm vững ba giá trị `TRUE`, `FALSE`, `UNKNOWN` sẽ giúp bạn đọc đúng kết quả của `IN` và `NOT IN`, phát hiện bẫy truy vấn con có `NULL` và viết điều kiện SQL nhất quán với dữ liệu thực tế.
