# Phân biệt điều kiện ON với điều kiện WHERE trong OUTER JOIN

Khi học SQL, một câu truy vấn `LEFT JOIN` có thể trông đúng nhưng lại **làm mất các dòng mà bạn muốn giữ**, chỉ vì điều kiện lọc được đặt ở `WHERE` thay vì `ON`. Ví dụ, bạn muốn thống kê **mọi khách hàng**, kể cả người chưa có đơn hàng đã xác nhận. Nếu viết điều kiện trạng thái của đơn trong `WHERE`, một số khách hàng có thể biến mất hoàn toàn khỏi báo cáo.

Bài học này tập trung vào sự khác biệt giữa **điều kiện ghép (`ON`)** và **điều kiện lọc kết quả (`WHERE`)** trong **`LEFT OUTER JOIN`, `RIGHT OUTER JOIN` và `FULL OUTER JOIN`**. Mục tiêu là hiểu *vì sao kết quả thay đổi*, biết cách chọn vị trí điều kiện theo yêu cầu nghiệp vụ và tránh những lỗi phổ biến khi thống kê, tìm bản ghi chưa có quan hệ hoặc ghép nhiều bảng.

Các ví dụ chính dùng **PostgreSQL** và một bộ dữ liệu tự chứa. Nguyên tắc logic áp dụng rộng rãi trong SQL, nhưng cú pháp `FULL OUTER JOIN`, hàm và cách tối ưu hóa có thể khác nhau giữa các hệ quản trị.

## 1. Hiểu lại JOIN trước khi so sánh ON và WHERE

`JOIN` kết hợp các dòng từ hai nguồn dữ liệu dựa trên điều kiện liên hệ. Ví dụ, bảng khách hàng và bảng đơn hàng có quan hệ qua khóa `customer_id`:

```sql
SELECT
    c.customer_id,
    c.customer_name,
    o.order_id
FROM customers AS c
JOIN orders AS o
    ON o.customer_id = c.customer_id;
```

Trong truy vấn này:

- `c` là bí danh của bảng khách hàng.
- `o` là bí danh của bảng đơn hàng.
- `ON o.customer_id = c.customer_id` xác định **hai dòng có khớp để ghép hay không**.
- `JOIN` không ghi rõ loại thường được hiểu là `INNER JOIN`.

Nếu một khách hàng có nhiều đơn, khách hàng đó xuất hiện **một lần trên mỗi đơn khớp**. Nếu khách hàng không có đơn, `INNER JOIN` không giữ khách hàng đó.

### 1.1. Ba loại OUTER JOIN

| Loại JOIN | Phía được giữ lại dù không tìm thấy dòng khớp | Dòng không khớp được biểu diễn thế nào |
|---|---|---|
| `LEFT [OUTER] JOIN` | Bảng bên **trái** | Cột phía phải được điền `NULL` |
| `RIGHT [OUTER] JOIN` | Bảng bên **phải** | Cột phía trái được điền `NULL` |
| `FULL [OUTER] JOIN` | **Cả hai** phía | Các cột ở phía không khớp được điền `NULL` |

Từ khóa `OUTER` có thể bỏ trong các cú pháp trên: `LEFT JOIN` và `LEFT OUTER JOIN` có cùng ý nghĩa.

**Phía “được giữ lại” không có nghĩa mọi dòng chắc chắn xuất hiện trong kết quả cuối cùng**. Nó có nghĩa là bước OUTER JOIN vẫn tạo dòng cho phía đó, **trước khi các điều kiện `WHERE` của cùng truy vấn được áp dụng**. Một `WHERE` không phù hợp có thể loại dòng vừa được bảo toàn.

### 1.2. Một JOIN có thể sinh nhiều dòng trên một thực thể

Nếu khách hàng A có ba đơn, `LEFT JOIN` vẫn có thể cho **ba dòng của A**. Phạm vi giữ dòng không đồng nghĩa với bảo đảm **mỗi khách hàng chỉ một dòng**. Nếu cần một dòng trên khách hàng, còn phải dùng `GROUP BY`, tiền tổng hợp hoặc kỹ thuật khác phù hợp.

## 2. Khác biệt cốt lõi: ON xác định khớp; WHERE lọc kết quả

Xét mẫu:

```sql
SELECT ...
FROM left_table AS l
LEFT JOIN right_table AS r
    ON l.id = r.left_id
   AND r.status = 'ACTIVE'
WHERE l.is_enabled = TRUE;
```

Diễn giải về **kết quả logic**:

1. Tìm các cặp dòng `l` và `r` đáp ứng điều kiện `ON`.
2. Với mỗi dòng bên trái chưa có cặp khớp, `LEFT JOIN` tạo một dòng **bảo toàn `l`**, điền `NULL` cho cột `r`.
3. `WHERE` lọc **toàn bộ các dòng đã tạo**; chỉ những dòng thỏa điều kiện ở `WHERE` mới được giữ.

Sơ đồ:

```text
       Bảng trái (L)                 Bảng phải (R)
            |                              |
            +----------- JOIN -------------+
                         |
                  Điều kiện ON
                         |
            Cặp khớp + các dòng L không khớp
                         |
                Bổ sung NULL phía R
                         |
                  Điều kiện WHERE
                         |
                     Kết quả
```

Đây là **mô hình thứ tự xử lý logic**, không phải lời khẳng định DBMS vật lý luôn thực hiện đúng theo thứ tự từng bước trên. Bộ tối ưu hóa có thể đổi kế hoạch thực thi nếu giữ nguyên ngữ nghĩa kết quả.

| Câu hỏi | `ON` | `WHERE` |
|---|---|---|
| Mục đích trong OUTER JOIN | Quy định cặp dòng nào được tính là **khớp** | Quy định dòng **sau khi JOIN** nào được trả về |
| `LEFT JOIN` có giữ bên trái khi bên phải không khớp điều kiện? | Có, theo quy tắc LEFT JOIN | Có thể **không**, nếu `WHERE` loại dòng `NULL` |
| Có thể chứa điều kiện trên bảng trái? | Có | Có |
| Có thể chứa điều kiện trên bảng phải? | Có | Có |
| Hai vị trí luôn hoán đổi được? | **Không** | **Không** |

Với `INNER JOIN`, chuyển một điều kiện thông thường từ `ON` sang `WHERE` thường vẫn cho tập kết quả tương đương trong nhiều trường hợp. Với **`OUTER JOIN`**, vị trí này **thay đổi ý nghĩa** vì bước tạo dòng không khớp.

## 3. Chuẩn bị bộ dữ liệu thực hành PostgreSQL

Tạo hai bảng và thêm dữ liệu minh họa. Các lệnh này dành cho **database thực hành**; thực hiện phần tạo bảng và nhập dữ liệu một lần, tránh trùng tên hoặc trùng khóa nếu chạy lại.

### 3.1. Bảng khách hàng

```sql
CREATE TABLE lesson182_customers (
    customer_id INTEGER PRIMARY KEY,
    customer_name VARCHAR(100) NOT NULL,
    city VARCHAR(80),
    is_active BOOLEAN NOT NULL
);

INSERT INTO lesson182_customers (
    customer_id,
    customer_name,
    city,
    is_active
)
VALUES
    (1, 'An',   'Hà Nội',       TRUE),
    (2, 'Bình', 'Đà Nẵng',      TRUE),
    (3, 'Chi',  'Huế',          FALSE),
    (4, 'Dũng', 'TP. HCM',      TRUE),
    (5, 'Hà',   'Hà Nội',       TRUE),
    (6, 'Lan',  'Cần Thơ',      FALSE);
```

### 3.2. Bảng đơn hàng

```sql
CREATE TABLE lesson182_orders (
    order_id INTEGER PRIMARY KEY,
    customer_id INTEGER NOT NULL
        REFERENCES lesson182_customers(customer_id),
    order_status VARCHAR(20) NOT NULL,
    order_amount NUMERIC(12, 2) NOT NULL,
    order_date DATE NOT NULL
);

INSERT INTO lesson182_orders (
    order_id,
    customer_id,
    order_status,
    order_amount,
    order_date
)
VALUES
    (101, 1, 'CONFIRMED', 120000.00, DATE '2026-11-14'),
    (102, 1, 'CANCELLED',  70000.00, DATE '2026-11-15'),
    (103, 2, 'PENDING',    80000.00, DATE '2026-11-14'),
    (104, 3, 'CONFIRMED', 200000.00, DATE '2026-11-13'),
    (105, 3, 'PENDING',    40000.00, DATE '2026-11-14'),
    (106, 5, 'CONFIRMED', 150000.00, DATE '2026-11-16'),
    (107, 5, 'CONFIRMED', 110000.00, DATE '2026-11-14');
```

Bảng mẫu có **6 khách hàng**, **7 đơn hàng**:

| Khách hàng | Mã khách | Đơn hàng | Có đơn `CONFIRMED`? |
|---|---:|---|---|
| An | 1 | 101 `CONFIRMED`, 102 `CANCELLED` | Có |
| Bình | 2 | 103 `PENDING` | **Không**, dù có đơn |
| Chi | 3 | 104 `CONFIRMED`, 105 `PENDING` | Có |
| Dũng | 4 | Không có đơn | Không |
| Hà | 5 | 106 `CONFIRMED`, 107 `CONFIRMED` | Có, hai đơn |
| Lan | 6 | Không có đơn | Không |

Điều khác biệt quan trọng nằm ở **Bình** và **Dũng**:

- Bình có đơn, nhưng **không có đơn `CONFIRMED`**.
- Dũng **không có bất kỳ đơn nào**.

Hai tình huống sẽ giúp thấy vì sao điều kiện ở `ON` khác với điều kiện ở `WHERE` và vì sao thêm `OR order_id IS NULL` không phải lúc nào cũng sửa đúng.

## 4. LEFT JOIN không có bộ lọc trạng thái

Trước hết, nối khách hàng với tất cả đơn:

```sql
SELECT
    c.customer_id,
    c.customer_name,
    o.order_id,
    o.order_status
FROM lesson182_customers AS c
LEFT JOIN lesson182_orders AS o
    ON o.customer_id = c.customer_id
ORDER BY c.customer_id, o.order_id;
```

Kết quả có 9 dòng:

| customer_id | customer_name | order_id | order_status |
|---:|---|---:|---|
| 1 | An | 101 | CONFIRMED |
| 1 | An | 102 | CANCELLED |
| 2 | Bình | 103 | PENDING |
| 3 | Chi | 104 | CONFIRMED |
| 3 | Chi | 105 | PENDING |
| 4 | Dũng | `NULL` | `NULL` |
| 5 | Hà | 106 | CONFIRMED |
| 5 | Hà | 107 | CONFIRMED |
| 6 | Lan | `NULL` | `NULL` |

Vì sao có **9 dòng** thay vì 6 khách hàng?

- An có 2 đơn → 2 dòng.
- Bình có 1 đơn → 1 dòng.
- Chi có 2 đơn → 2 dòng.
- Dũng không có đơn → 1 dòng được bảo toàn.
- Hà có 2 đơn → 2 dòng.
- Lan không có đơn → 1 dòng được bảo toàn.

Tổng `2 + 1 + 2 + 1 + 2 + 1 = 9`.

Các `NULL` của Dũng và Lan ở cột đơn hàng do `LEFT JOIN` tự bổ sung, **không có nghĩa bảng `lesson182_orders` thực sự chứa những dòng đơn hàng với `order_id NULL`**.

## 5. Điều kiện bên phải ở ON: giữ mọi khách hàng

**Yêu cầu:** “Liệt kê **tất cả khách hàng**, kèm các đơn `CONFIRMED` nếu có; khách hàng không có đơn `CONFIRMED` vẫn phải hiện.”

Đặt điều kiện trạng thái vào **`ON`**:

```sql
SELECT
    c.customer_id,
    c.customer_name,
    o.order_id,
    o.order_status
FROM lesson182_customers AS c
LEFT JOIN lesson182_orders AS o
    ON o.customer_id = c.customer_id
   AND o.order_status = 'CONFIRMED'
ORDER BY c.customer_id, o.order_id;
```

Kết quả:

| customer_id | customer_name | order_id | order_status |
|---:|---|---:|---|
| 1 | An | 101 | CONFIRMED |
| 2 | Bình | `NULL` | `NULL` |
| 3 | Chi | 104 | CONFIRMED |
| 4 | Dũng | `NULL` | `NULL` |
| 5 | Hà | 106 | CONFIRMED |
| 5 | Hà | 107 | CONFIRMED |
| 6 | Lan | `NULL` | `NULL` |

Có **7 dòng**. Mọi khách hàng đều xuất hiện ít nhất một lần; Hà xuất hiện hai lần vì có hai đơn phù hợp.

Tại sao Bình vẫn có dòng dù bảng `orders` chứa đơn 103 của Bình? Vì **đơn 103 không khớp toàn bộ điều kiện `ON`**:

```sql
o.customer_id = c.customer_id
AND o.order_status = 'CONFIRMED'
```

Không có **đơn `CONFIRMED` nào của Bình**, nên với `LEFT JOIN`, Bình trở thành một dòng **không có kết quả bên phải phù hợp**. Điều này không có nghĩa Bình không có đơn nói chung.

Tương tự, đơn `CANCELLED` của An và đơn `PENDING` của Chi không được ghép trong kết quả này, vì điều kiện `ON` đang chọn **loại đơn được phép khớp**, không phải lọc khách hàng.

### 5.1. Cách hiểu đúng: lọc tập quan hệ ghép

Hãy đọc câu `ON ... AND o.order_status = 'CONFIRMED'` như sau:

> “Với mỗi khách hàng, tìm các đơn có cùng `customer_id` **và** trạng thái `CONFIRMED`. Nếu không có đơn như vậy, vẫn giữ khách hàng.”

Không đọc nó thành “xóa khỏi kết quả mọi khách hàng không có đơn `CONFIRMED`”, vì đó không phải cách `LEFT JOIN` xử lý phía được bảo toàn.

## 6. Cùng điều kiện đặt ở WHERE: khách hàng có thể biến mất

Giữ phép nối theo khóa, rồi lọc trạng thái **sau JOIN**:

```sql
SELECT
    c.customer_id,
    c.customer_name,
    o.order_id,
    o.order_status
FROM lesson182_customers AS c
LEFT JOIN lesson182_orders AS o
    ON o.customer_id = c.customer_id
WHERE o.order_status = 'CONFIRMED'
ORDER BY c.customer_id, o.order_id;
```

Kết quả:

| customer_id | customer_name | order_id | order_status |
|---:|---|---:|---|
| 1 | An | 101 | CONFIRMED |
| 3 | Chi | 104 | CONFIRMED |
| 5 | Hà | 106 | CONFIRMED |
| 5 | Hà | 107 | CONFIRMED |

Chỉ còn **4 dòng**, đại diện cho **3 khách hàng**.

Giải thích theo từng nhóm:

- Đơn của An ở trạng thái `CANCELLED` bị `WHERE` loại; An vẫn còn dòng `CONFIRMED`.
- Dòng `PENDING` của Bình bị loại; **Bình biến mất hoàn toàn**.
- Chi còn đơn 104 `CONFIRMED` nên vẫn xuất hiện.
- Dũng không có đơn; `o.order_status` trong dòng được bảo toàn là `NULL`. Phép so sánh `NULL = 'CONFIRMED'` cho **UNKNOWN**, nên dòng bị loại.
- Hà có hai dòng `CONFIRMED` nên giữ cả hai.
- Lan cũng bị loại vì cột `o.order_status` là `NULL`.

**`LEFT JOIN` vẫn chạy đúng**, nhưng `WHERE` khiến các dòng không thỏa trạng thái bị loại khỏi **kết quả cuối**. Với điều kiện chỉ chấp nhận giá trị không `NULL` ở phía phải, kết quả có thể tương đương một `INNER JOIN` về tập dòng.

### 6.1. Hai truy vấn trả lời hai câu hỏi khác nhau

| Yêu cầu nghiệp vụ | Điều kiện phù hợp |
|---|---|
| “Tất cả khách hàng và đơn `CONFIRMED` của họ, nếu có” | `LEFT JOIN ... ON ... AND o.order_status = 'CONFIRMED'` |
| “Chỉ các khách hàng–đơn hàng có trạng thái `CONFIRMED`” | `LEFT JOIN ... ON ... WHERE o.order_status = 'CONFIRMED'`, hoặc `INNER JOIN` phù hợp |
| “Chỉ khách hàng có ít nhất một đơn `CONFIRMED`” | `WHERE EXISTS (...)` thường rõ ý định và tránh lặp khách hàng |

Khác biệt giữa `ON` và `WHERE` không phải “cái nào tốt hơn” mà là **đang yêu cầu giữ hay loại đối tượng nào**.

## 7. Vì sao LEFT JOIN có thể bị biến thành INNER JOIN?

Một điều kiện được gọi là **null-rejecting** đối với phía phải nếu nó **không chấp nhận** dòng mà các cột phía phải đều là `NULL`.

Ví dụ:

```sql
WHERE o.order_status = 'CONFIRMED'
```

Với một dòng do `LEFT JOIN` bổ sung `NULL` cho phía `o`, điều kiện trên cho `UNKNOWN`, không phải `TRUE`. Do đó, dòng được giữ lại từ phía khách hàng nhưng không khớp đơn hàng **bị loại ở `WHERE`**.

Ví dụ khác:

```sql
WHERE o.order_amount > 100000
```

Nếu không có đơn phù hợp, `o.order_amount` là `NULL` và điều kiện cũng là `UNKNOWN`. Câu lệnh chỉ giữ những khách hàng có ít nhất một dòng đơn có số tiền vượt ngưỡng.

**Điểm cần phân biệt:** không phải mọi `WHERE` sau `LEFT JOIN` đều tự biến truy vấn thành `INNER JOIN`. Ví dụ:

```sql
WHERE o.order_id IS NULL
```

lại **chọn** các dòng không có khớp ở phía phải. Hoặc:

```sql
WHERE c.is_active = TRUE
```

chỉ lọc trạng thái của **bảng trái**, có thể vẫn giữ khách hàng không có đơn.

Khái niệm null-rejecting giúp giải thích **khi nào** một điều kiện trong `WHERE` loại bỏ các dòng không khớp.

## 8. NULL và logic ba giá trị quyết định kết quả lọc

SQL không dùng logic chỉ hai giá trị TRUE/FALSE trong mọi biểu thức so sánh. Khi dữ liệu có `NULL`, kết quả có thể là **UNKNOWN**.

| Biểu thức với `o.order_status = NULL` | Kết quả logic |
|---|---|
| `o.order_status = 'CONFIRMED'` | UNKNOWN |
| `o.order_status <> 'CONFIRMED'` | UNKNOWN |
| `o.order_status IS NULL` | TRUE |
| `o.order_status IS NOT NULL` | FALSE |

Mệnh đề `WHERE` **chỉ giữ những dòng có điều kiện TRUE**. FALSE và UNKNOWN đều bị loại.

### 8.1. Lỗi: dùng <> để tìm “không xác nhận” rồi mong giữ cả khách hàng chưa có đơn

```sql
SELECT
    c.customer_id,
    c.customer_name,
    o.order_id,
    o.order_status
FROM lesson182_customers AS c
LEFT JOIN lesson182_orders AS o
    ON o.customer_id = c.customer_id
WHERE o.order_status <> 'CONFIRMED'
ORDER BY c.customer_id, o.order_id;
```

Truy vấn trên lấy các dòng `CANCELLED` và `PENDING`; nó **không lấy Dũng và Lan** (không có đơn) vì `NULL <> 'CONFIRMED'` không phải TRUE.

Nếu thật sự muốn lấy cả các khách hàng không có đơn, bạn phải định nghĩa lại yêu cầu và viết rõ cách xử lý `NULL`. Nhưng thêm `OR o.order_id IS NULL` không phải luôn đúng cho những câu hỏi liên quan đến **không có đơn theo một trạng thái**; phần kế tiếp giải thích lý do.

## 9. Bẫy OR ... IS NULL: không thay thế được điều kiện ON

Khi thấy câu `WHERE o.order_status = 'CONFIRMED'` làm mất khách hàng không có đơn, nhiều người thử:

```sql
SELECT
    c.customer_id,
    c.customer_name,
    o.order_id,
    o.order_status
FROM lesson182_customers AS c
LEFT JOIN lesson182_orders AS o
    ON o.customer_id = c.customer_id
WHERE o.order_status = 'CONFIRMED'
   OR o.order_id IS NULL
ORDER BY c.customer_id, o.order_id;
```

Kết quả:

| Khách hàng | Đơn |
|---|---|
| An | 101 `CONFIRMED` |
| Chi | 104 `CONFIRMED` |
| Dũng | `NULL` |
| Hà | 106 và 107 `CONFIRMED` |
| Lan | `NULL` |

**Bình vẫn biến mất**, dù báo cáo mong tất cả khách hàng.

Vì sao? Bình có **đơn `PENDING`** nên phép `LEFT JOIN` theo khóa **đã tìm được một dòng khớp**. Do có dòng đơn, hệ quản trị **không tạo một dòng `o.order_id NULL` thay thế** cho Bình. Ở `WHERE`:

- `o.order_status = 'CONFIRMED'` là FALSE.
- `o.order_id IS NULL` là FALSE.
- FALSE `OR` FALSE là FALSE.

Bình bị loại.

Muốn “tất cả khách hàng và chỉ các đơn `CONFIRMED`, nếu có”, phải tạo quan hệ ghép đúng ngay trong `ON`:

```sql
LEFT JOIN lesson182_orders AS o
    ON o.customer_id = c.customer_id
   AND o.order_status = 'CONFIRMED'
```

Đây là khác biệt quan trọng giữa:

- **Không có bất kỳ đơn hàng nào**: Dũng, Lan.
- **Có đơn hàng nhưng không có đơn phù hợp bộ lọc**: Bình.

Một `WHERE ... OR o.order_id IS NULL` sau JOIN **không tái tạo được** dòng `NULL` cho khách hàng có đơn nhưng chỉ có đơn không đạt điều kiện.

## 10. Điều kiện trên bảng trái: đặt ở ON và WHERE cũng khác nhau

Cho đến giờ, điều kiện đang nằm trên bảng phải `orders`. Nếu điều kiện thuộc **bảng trái** `customers`, đặt tại `ON` hay `WHERE` cũng không thể hoán đổi tùy ý.

### 10.1. Lọc khách hàng còn hoạt động trong WHERE

**Yêu cầu:** “Chỉ lấy khách hàng đang hoạt động; với mỗi người, hiển thị đơn của họ nếu có.”

```sql
SELECT
    c.customer_id,
    c.customer_name,
    c.is_active,
    o.order_id
FROM lesson182_customers AS c
LEFT JOIN lesson182_orders AS o
    ON o.customer_id = c.customer_id
WHERE c.is_active = TRUE
ORDER BY c.customer_id, o.order_id;
```

Kết quả chỉ có khách hàng **An, Bình, Dũng, Hà**. Chi và Lan bị loại vì không còn hoạt động. Dũng vẫn có một dòng với `o.order_id NULL`, vì `WHERE` chỉ lọc theo **cột của phía được giữ lại**.

### 10.2. Đặt cùng điều kiện bên trái vào ON

```sql
SELECT
    c.customer_id,
    c.customer_name,
    c.is_active,
    o.order_id
FROM lesson182_customers AS c
LEFT JOIN lesson182_orders AS o
    ON o.customer_id = c.customer_id
   AND c.is_active = TRUE
ORDER BY c.customer_id, o.order_id;
```

Bây giờ **mọi khách hàng vẫn xuất hiện**, kể cả Chi và Lan.

Giải thích: với Chi, `c.is_active = TRUE` là FALSE, nên **không có đơn nào được tính là khớp**, mặc dù Chi thực sự có đơn 104 và 105. Do `LEFT JOIN` bảo toàn bảng trái, truy vấn vẫn trả Chi với `o.order_id NULL`.

Đây là quy tắc tổng quát:

- Điều kiện bên trái ở `ON` quyết định **khách hàng nào được phép ghép với đơn**.
- Điều kiện bên trái ở `WHERE` quyết định **khách hàng nào được phép còn trong kết quả**.

Nếu mục tiêu chỉ lấy khách hàng đang hoạt động, dùng `WHERE c.is_active = TRUE`. Nếu mục tiêu giữ tất cả khách hàng nhưng **chỉ gắn đơn cho khách đang hoạt động**, đặt vào `ON` có thể đúng.

### 10.3. Kết hợp cả hai loại điều kiện

**Yêu cầu:** “Khách hàng đang hoạt động, gồm cả người chưa có đơn xác nhận; chỉ gắn đơn `CONFIRMED`.”

```sql
SELECT
    c.customer_id,
    c.customer_name,
    o.order_id,
    o.order_status
FROM lesson182_customers AS c
LEFT JOIN lesson182_orders AS o
    ON o.customer_id = c.customer_id
   AND o.order_status = 'CONFIRMED'
WHERE c.is_active = TRUE
ORDER BY c.customer_id, o.order_id;
```

Lúc này:

- `ON` lọc **đơn nào được ghép**.
- `WHERE` lọc **khách hàng nào được giữ trong báo cáo**.

Kết quả có An (đơn 101), Bình (đơn `NULL`), Dũng (đơn `NULL`), Hà (đơn 106, 107).

## 11. Lọc theo ngày cùng với trạng thái: vẫn đặt theo mục tiêu bảo toàn

Giả sử cần báo cáo **mọi khách hàng** và đơn `CONFIRMED` phát sinh **ngày 14/11/2026**.

```sql
SELECT
    c.customer_id,
    c.customer_name,
    o.order_id,
    o.order_status,
    o.order_date
FROM lesson182_customers AS c
LEFT JOIN lesson182_orders AS o
    ON o.customer_id = c.customer_id
   AND o.order_status = 'CONFIRMED'
   AND o.order_date = DATE '2026-11-14'
ORDER BY c.customer_id, o.order_id;
```

Kết quả: An có đơn 101, Hà có đơn 107, còn **Bình, Chi, Dũng, Lan** đều xuất hiện với các cột đơn hàng `NULL`.

Đặc biệt, Chi có đơn `CONFIRMED` vào **ngày 13/11**, nhưng không có đơn `CONFIRMED` ngày **14/11**. Vì thế trong truy vấn này, Chi được giữ với phía đơn hàng `NULL`. Điều đó không có nghĩa Chi không có đơn trong cơ sở dữ liệu.

Nếu chuyển điều kiện ngày và trạng thái sang `WHERE`:

```sql
SELECT
    c.customer_id,
    c.customer_name,
    o.order_id
FROM lesson182_customers AS c
LEFT JOIN lesson182_orders AS o
    ON o.customer_id = c.customer_id
WHERE o.order_status = 'CONFIRMED'
  AND o.order_date = DATE '2026-11-14'
ORDER BY c.customer_id, o.order_id;
```

chỉ có **An 101** và **Hà 107**. Những khách không có đơn đúng trạng thái/ngày bị loại.

Với cột chứa cả ngày và giờ như `TIMESTAMP` hoặc `TIMESTAMPTZ`, nên lọc theo khoảng nửa mở `>= start AND < end`, đồng thời xác định múi giờ nghiệp vụ. Vị trí đặt hai điều kiện **vẫn tuân theo quy tắc ON/WHERE**:

```sql
-- Ví dụ giả định orders có cột created_at TIMESTAMPTZ.
LEFT JOIN orders AS o
    ON o.customer_id = c.customer_id
   AND o.created_at >= TIMESTAMPTZ '2026-11-14 00:00:00+07'
   AND o.created_at <  TIMESTAMPTZ '2026-11-15 00:00:00+07'
```

Đoạn sau là **minh họa thiết kế**, không chạy trực tiếp với bảng `lesson182_orders` của bài vì bảng mẫu chỉ có `order_date DATE`.

## 12. OUTER JOIN và GROUP BY: đếm đúng cả nhóm bằng 0

Một mục tiêu báo cáo thường là **một dòng trên một khách hàng**, với số đơn đã xác nhận, kể cả số đơn bằng 0.

### 12.1. Cách đặt điều kiện trong ON

```sql
SELECT
    c.customer_id,
    c.customer_name,
    COUNT(o.order_id) AS confirmed_order_count,
    COALESCE(SUM(o.order_amount), 0) AS confirmed_amount
FROM lesson182_customers AS c
LEFT JOIN lesson182_orders AS o
    ON o.customer_id = c.customer_id
   AND o.order_status = 'CONFIRMED'
GROUP BY c.customer_id, c.customer_name
ORDER BY c.customer_id;
```

Kết quả:

| Khách hàng | confirmed_order_count | confirmed_amount |
|---|---:|---:|
| An | 1 | 120.000 |
| Bình | 0 | 0 |
| Chi | 1 | 200.000 |
| Dũng | 0 | 0 |
| Hà | 2 | 260.000 |
| Lan | 0 | 0 |

Đây là dạng hữu ích khi lập danh sách đủ khách hàng, có số đếm và số tiền theo **những đơn đủ điều kiện**.

- `COUNT(o.order_id)` không đếm dòng không có đơn khớp vì `o.order_id IS NULL`.
- `SUM(o.order_amount)` bỏ qua `NULL`. Với khách hàng không có đơn khớp, kết quả `SUM` của nhóm có thể là `NULL`, nên `COALESCE(..., 0)` dùng để **hiển thị số 0 theo quy ước báo cáo**.
- Một khách hàng có nhiều đơn `CONFIRMED` sẽ có nhiều dòng trung gian; `GROUP BY` gom thành một dòng khách hàng.

### 12.2. Vì sao COUNT(*) không phải số đơn?

```sql
SELECT
    c.customer_id,
    COUNT(*) AS joined_row_count,
    COUNT(o.order_id) AS confirmed_order_count
FROM lesson182_customers AS c
LEFT JOIN lesson182_orders AS o
    ON o.customer_id = c.customer_id
   AND o.order_status = 'CONFIRMED'
GROUP BY c.customer_id
ORDER BY c.customer_id;
```

Với Bình, Dũng và Lan:

- `COUNT(*) = 1` do `LEFT JOIN` giữ một dòng khách hàng không khớp.
- `COUNT(o.order_id) = 0` do mã đơn phía phải là `NULL`.

Vì thế nếu muốn đếm thực thể con **không NULL**, hãy chọn khóa của thực thể đó như `COUNT(o.order_id)` (miễn là JOIN khác chưa làm nhân dòng). `COUNT(*)` luôn đếm **số dòng kết quả đầu vào nhóm**, không tự hiểu “số đơn hàng”.

### 12.3. Dùng tổng hợp có điều kiện thay cho điều kiện trong ON

Có thể giữ `LEFT JOIN` với **tất cả đơn**, rồi tính riêng số đơn `CONFIRMED`:

```sql
SELECT
    c.customer_id,
    c.customer_name,
    COUNT(o.order_id) FILTER (
        WHERE o.order_status = 'CONFIRMED'
    ) AS confirmed_order_count,
    COALESCE(
        SUM(o.order_amount) FILTER (
            WHERE o.order_status = 'CONFIRMED'
        ),
        0
    ) AS confirmed_amount
FROM lesson182_customers AS c
LEFT JOIN lesson182_orders AS o
    ON o.customer_id = c.customer_id
GROUP BY c.customer_id, c.customer_name
ORDER BY c.customer_id;
```

Đây là cú pháp PostgreSQL hỗ trợ `FILTER` trên hàm tổng hợp. **`FILTER` ở đây chỉ lọc giá trị đưa vào từng phép tổng hợp**, không loại khách hàng khỏi toàn bộ tập `GROUP BY`. Vì vậy vẫn giữ được nhóm với số đếm 0.

Một cách dễ chuyển sang nhiều DBMS hơn là dùng `CASE`:

```sql
SELECT
    c.customer_id,
    c.customer_name,
    SUM(
        CASE
            WHEN o.order_status = 'CONFIRMED' THEN 1
            ELSE 0
        END
    ) AS confirmed_order_count
FROM lesson182_customers AS c
LEFT JOIN lesson182_orders AS o
    ON o.customer_id = c.customer_id
GROUP BY c.customer_id, c.customer_name
ORDER BY c.customer_id;
```

Với dữ liệu hiện tại chỉ nối khách hàng–đơn hàng, cách trên cho các số đếm đúng. Tuy nhiên, nếu sau này nối thêm bảng `order_items`, mỗi đơn có thể bị nhân theo số dòng sản phẩm: `SUM(CASE ... THEN 1 ELSE 0 END)` sẽ **đếm lặp đơn**. Khi đó phải xét lại grain, dùng `COUNT(DISTINCT o.order_id)` cho yêu cầu đếm đơn duy nhất hoặc tổng hợp bảng con trước khi nối.

### 12.4. Tại sao không dùng WHERE để lọc rồi đếm?

```sql
SELECT
    c.customer_id,
    c.customer_name,
    COUNT(o.order_id) AS confirmed_order_count
FROM lesson182_customers AS c
LEFT JOIN lesson182_orders AS o
    ON o.customer_id = c.customer_id
WHERE o.order_status = 'CONFIRMED'
GROUP BY c.customer_id, c.customer_name;
```

Bình, Dũng và Lan **không có nhóm trong kết quả**, chứ không phải có nhóm với số đếm 0. `COALESCE(COUNT(...), 0)` cũng không tự “tạo lại” những nhóm đã bị `WHERE` loại.

## 13. Tìm khách hàng không có đơn hàng: anti-join

Một ứng dụng thường gặp của `LEFT JOIN` là tìm dòng phía trái **không có bản ghi bên phải tương ứng**.

### 13.1. Khách hàng chưa từng có đơn

```sql
SELECT
    c.customer_id,
    c.customer_name
FROM lesson182_customers AS c
LEFT JOIN lesson182_orders AS o
    ON o.customer_id = c.customer_id
WHERE o.order_id IS NULL
ORDER BY c.customer_id;
```

Kết quả: **Dũng** và **Lan**.

Giải thích:

1. `LEFT JOIN` cố tìm mọi đơn theo `customer_id`.
2. Khách không có bất kỳ đơn nào sẽ có dòng `o.order_id NULL`.
3. `WHERE o.order_id IS NULL` chọn những dòng đó.

Đây thường được gọi là **anti-join pattern** với `LEFT JOIN ... IS NULL`.

Nên dùng `o.order_id` (khóa chính **NOT NULL**) làm cột kiểm tra. Nếu dùng một cột phía phải vốn được phép `NULL`, một dòng đã khớp thật nhưng trường dữ liệu đó `NULL` cũng có thể bị nhầm là “không có bản ghi”.

### 13.2. Khách hàng không có đơn CONFIRMED

Đây là một câu hỏi **khác** với “chưa từng có đơn”. Bình phải được lấy vì chỉ có đơn `PENDING`.

```sql
SELECT
    c.customer_id,
    c.customer_name
FROM lesson182_customers AS c
LEFT JOIN lesson182_orders AS o
    ON o.customer_id = c.customer_id
   AND o.order_status = 'CONFIRMED'
WHERE o.order_id IS NULL
ORDER BY c.customer_id;
```

Kết quả: **Bình, Dũng, Lan**.

Nếu đặt điều kiện `o.order_status = 'CONFIRMED'` ở `WHERE` bên cạnh `o.order_id IS NULL`, logic sẽ không biểu đạt đúng yêu cầu:

```sql
-- Không trả về nhóm không có đơn CONFIRMED.
WHERE o.order_status = 'CONFIRMED'
  AND o.order_id IS NULL
```

Một dòng `o.order_id IS NULL` do `LEFT JOIN` tạo không thể đồng thời có `o.order_status = 'CONFIRMED'` là TRUE.

### 13.3. NOT EXISTS thường diễn đạt rõ anti-join

Cùng câu hỏi “khách hàng không có đơn `CONFIRMED`” có thể viết:

```sql
SELECT
    c.customer_id,
    c.customer_name
FROM lesson182_customers AS c
WHERE NOT EXISTS (
    SELECT 1
    FROM lesson182_orders AS o
    WHERE o.customer_id = c.customer_id
      AND o.order_status = 'CONFIRMED'
)
ORDER BY c.customer_id;
```

Kết quả vẫn là **Bình, Dũng, Lan**.

`NOT EXISTS` hỏi trực tiếp “**không có bản ghi nào đáp ứng điều kiện liên hệ và trạng thái này**”. Nó tránh phải tạo và kiểm tra một dòng `NULL` của `LEFT JOIN` ở tầng câu truy vấn ngoài; đồng thời phù hợp khi chỉ cần thông tin khách hàng, không cần lấy cột của đơn.

## 14. Khi chỉ muốn khách hàng có đơn: EXISTS và INNER JOIN

**Yêu cầu:** “Liệt kê mỗi khách hàng có ít nhất một đơn `CONFIRMED` đúng một lần.”

Có thể dùng `EXISTS`:

```sql
SELECT
    c.customer_id,
    c.customer_name
FROM lesson182_customers AS c
WHERE EXISTS (
    SELECT 1
    FROM lesson182_orders AS o
    WHERE o.customer_id = c.customer_id
      AND o.order_status = 'CONFIRMED'
)
ORDER BY c.customer_id;
```

Kết quả: **An, Chi, Hà** — mỗi người một dòng.

Nếu dùng `INNER JOIN`:

```sql
SELECT
    c.customer_id,
    c.customer_name
FROM lesson182_customers AS c
INNER JOIN lesson182_orders AS o
    ON o.customer_id = c.customer_id
   AND o.order_status = 'CONFIRMED'
ORDER BY c.customer_id;
```

thì **Hà xuất hiện hai lần** vì có hai đơn `CONFIRMED`. Để loại trùng, có thể dùng `SELECT DISTINCT c.customer_id, c.customer_name`; tuy nhiên, khi mục đích chỉ kiểm tra **có tồn tại đơn phù hợp hay không**, `EXISTS` thường diễn đạt ý định rõ ràng hơn.

### Bảng quyết định nhanh

| Bạn muốn | Cấu trúc thường phù hợp |
|---|---|
| Tất cả khách hàng, kèm đơn phù hợp nếu có | `LEFT JOIN ... ON ... AND o.filter` |
| Chỉ những cặp khách hàng–đơn phù hợp | `INNER JOIN ... ON ... AND o.filter` |
| Mỗi khách hàng có ít nhất một đơn phù hợp | `WHERE EXISTS (...)` |
| Khách hàng không có đơn phù hợp | `WHERE NOT EXISTS (...)` hoặc `LEFT JOIN ... ON ... AND o.filter WHERE o.order_id IS NULL` |

## 15. RIGHT OUTER JOIN: phía phải mới là phía được giữ

`RIGHT JOIN` bảo toàn **bảng nằm bên phải**. Có thể hiểu nó bằng cách đổi thứ tự hai bảng và dùng `LEFT JOIN`, nhưng khi đọc truy vấn sẵn có cần xác định rõ bên nào được giữ.

Giả sử yêu cầu: “Hiển thị **tất cả đơn hàng**, gắn thông tin khách hàng **chỉ khi khách hàng đang hoạt động**.”

```sql
SELECT
    o.order_id,
    o.customer_id AS order_customer_id,
    c.customer_name,
    c.is_active
FROM lesson182_customers AS c
RIGHT JOIN lesson182_orders AS o
    ON o.customer_id = c.customer_id
   AND c.is_active = TRUE
ORDER BY o.order_id;
```

Kết quả có **cả 7 đơn**. Các đơn 104 và 105 của **Chi** có phần `c.customer_name` và `c.is_active` là `NULL` trong kết quả nối, vì Chi không thỏa `c.is_active = TRUE` trong `ON`. Nhưng `o.order_id` vẫn hiện vì **orders là bảng được RIGHT JOIN bảo toàn**.

Nếu chuyển điều kiện sang `WHERE`:

```sql
SELECT
    o.order_id,
    o.customer_id AS order_customer_id,
    c.customer_name
FROM lesson182_customers AS c
RIGHT JOIN lesson182_orders AS o
    ON o.customer_id = c.customer_id
WHERE c.is_active = TRUE
ORDER BY o.order_id;
```

Các đơn 104 và 105 **bị loại**, vì khách hàng Chi không hoạt động. Trong dữ liệu mẫu, chỉ còn 5 đơn của các khách hàng hoạt động.

Với `RIGHT JOIN`:

- Điều kiện đặt ở `ON` ảnh hưởng **dòng phía trái nào được ghép**, nhưng vẫn giữ đơn hàng bên phải.
- Điều kiện null-rejecting trên bảng trái ở `WHERE` có thể loại các dòng bên phải đã được bảo toàn.

### 15.1. Viết lại bằng LEFT JOIN để dễ đọc

Truy vấn `RIGHT JOIN` ở trên có thể viết lại theo kiểu thường dễ theo dõi hơn:

```sql
SELECT
    o.order_id,
    o.customer_id AS order_customer_id,
    c.customer_name,
    c.is_active
FROM lesson182_orders AS o
LEFT JOIN lesson182_customers AS c
    ON c.customer_id = o.customer_id
   AND c.is_active = TRUE
ORDER BY o.order_id;
```

Ở đây **orders** được đặt bên trái nên quan hệ “giữ tất cả đơn” trở nên trực quan. Cú pháp `RIGHT JOIN` không sai, nhưng bạn nên chọn chiều JOIN làm nổi bật thực thể mà báo cáo cần bảo toàn.

## 16. FULL OUTER JOIN: điều kiện ON không loại cả hai phía

`FULL OUTER JOIN` giữ **dòng không khớp từ cả hai phía**. Vì thế, sự khác biệt giữa `ON` và `WHERE` còn có một tình huống dễ gây bất ngờ: **điều kiện ON làm một cặp không khớp nhưng mỗi phía có thể xuất hiện riêng như một dòng không khớp**.

Dùng tập dữ liệu nhỏ, độc lập với bảng khách hàng/đơn hàng:

```sql
WITH a (id, a_label) AS (
    VALUES
        (1, 'A1'),
        (2, 'A2'),
        (3, 'A3')
),
b (id, b_status) AS (
    VALUES
        (2, 'READY'),
        (3, 'PENDING'),
        (4, 'READY')
)
SELECT
    a.id AS a_id,
    a.a_label,
    b.id AS b_id,
    b.b_status
FROM a
FULL OUTER JOIN b
    ON a.id = b.id
ORDER BY COALESCE(a.id, b.id), a.id NULLS LAST;
```

Ở trường hợp chỉ nối theo `id`, kết quả gồm:

| a_id | a_label | b_id | b_status |
|---:|---|---:|---|
| 1 | A1 | `NULL` | `NULL` |
| 2 | A2 | 2 | READY |
| 3 | A3 | 3 | PENDING |
| `NULL` | `NULL` | 4 | READY |

Hai dòng có cùng `id` là 2 và 3 được ghép; `A1` và `B4` tồn tại riêng.

### 16.1. Thêm điều kiện phía phải vào ON

```sql
WITH a (id, a_label) AS (
    VALUES (1, 'A1'), (2, 'A2'), (3, 'A3')
),
b (id, b_status) AS (
    VALUES (2, 'READY'), (3, 'PENDING'), (4, 'READY')
)
SELECT
    a.id AS a_id,
    a.a_label,
    b.id AS b_id,
    b.b_status
FROM a
FULL OUTER JOIN b
    ON a.id = b.id
   AND b.b_status = 'READY'
ORDER BY COALESCE(a.id, b.id), a.id NULLS LAST;
```

Kết quả:

| a_id | a_label | b_id | b_status |
|---:|---|---:|---|
| 1 | A1 | `NULL` | `NULL` |
| 2 | A2 | 2 | READY |
| 3 | A3 | `NULL` | `NULL` |
| `NULL` | `NULL` | 3 | PENDING |
| `NULL` | `NULL` | 4 | READY |

Điểm đặc biệt: **`A3` và `B3` không còn ghép được với nhau** vì `B3` có trạng thái `PENDING`, không thỏa điều kiện `ON`. Nhưng `FULL OUTER JOIN` vẫn giữ **cả hai dòng này**, mỗi dòng ở một phía, nên xuất hiện **hai dòng riêng cùng mang id 3 ở những cột khác nhau**.

Điều kiện `ON b.b_status = 'READY'` **không có nghĩa loại `B3` khỏi kết quả FULL JOIN**. Nó chỉ nói rằng `B3` không được xem là **khớp với `A3`**, còn `FULL JOIN` vẫn bảo toàn `B3`.

### 16.2. Đặt trạng thái vào WHERE

```sql
WITH a (id, a_label) AS (
    VALUES (1, 'A1'), (2, 'A2'), (3, 'A3')
),
b (id, b_status) AS (
    VALUES (2, 'READY'), (3, 'PENDING'), (4, 'READY')
)
SELECT
    a.id AS a_id,
    a.a_label,
    b.id AS b_id,
    b.b_status
FROM a
FULL OUTER JOIN b
    ON a.id = b.id
WHERE b.b_status = 'READY'
ORDER BY COALESCE(a.id, b.id);
```

Kết quả chỉ còn:

| a_id | a_label | b_id | b_status |
|---:|---|---:|---|
| 2 | A2 | 2 | READY |
| `NULL` | `NULL` | 4 | READY |

`WHERE` đã **lọc toàn bộ dòng kết quả**. Dòng `A1` không có `b.b_status`, dòng `A3–B3` có `PENDING`, nên đều bị loại.

### 16.3. Nếu muốn FULL JOIN với một tập B đã lọc

Đôi khi yêu cầu là: “Giữ mọi dòng A, đồng thời chỉ xét các dòng B có trạng thái `READY`; những dòng B `PENDING` không tham gia báo cáo ngay từ đầu.”

Khi đó hãy lọc B **trước khi tham gia JOIN**, ví dụ bằng truy vấn con:

```sql
WITH a (id, a_label) AS (
    VALUES (1, 'A1'), (2, 'A2'), (3, 'A3')
),
b (id, b_status) AS (
    VALUES (2, 'READY'), (3, 'PENDING'), (4, 'READY')
)
SELECT
    a.id AS a_id,
    a.a_label,
    b_ready.id AS b_id,
    b_ready.b_status
FROM a
FULL OUTER JOIN (
    SELECT id, b_status
    FROM b
    WHERE b_status = 'READY'
) AS b_ready
    ON a.id = b_ready.id
ORDER BY COALESCE(a.id, b_ready.id), a.id NULLS LAST;
```

Ở đây `B3` `PENDING` **không thuộc nguồn B đã lọc**, nên không còn hiện độc lập. Kết quả có `A1`, `A2–B2`, `A3`, `B4` — bốn dòng.

**Đừng dùng điều kiện `ON` của FULL JOIN như cách để loại bỏ hoàn toàn những dòng không đủ điều kiện của một bên**, bởi FULL JOIN còn bảo toàn những dòng không khớp ở chính bên đó.

## 17. Lọc trước nguồn JOIN bằng CTE hoặc subquery

Khi điều kiện trở nên phức tạp, viết tập dữ liệu bên phải đã lọc trước có thể làm ý định dễ đọc:

```sql
WITH confirmed_orders AS (
    SELECT
        order_id,
        customer_id,
        order_amount,
        order_date
    FROM lesson182_orders
    WHERE order_status = 'CONFIRMED'
)
SELECT
    c.customer_id,
    c.customer_name,
    o.order_id,
    o.order_amount
FROM lesson182_customers AS c
LEFT JOIN confirmed_orders AS o
    ON o.customer_id = c.customer_id
ORDER BY c.customer_id, o.order_id;
```

Truy vấn này có cùng tập dòng mong muốn với việc đặt:

```sql
LEFT JOIN lesson182_orders AS o
    ON o.customer_id = c.customer_id
   AND o.order_status = 'CONFIRMED'
```

Ưu điểm của cách CTE là biểu đạt rõ “**bảng đơn đã được lọc thành chỉ còn đơn CONFIRMED**” trước khi ghép, đồng thời dễ dùng lại các bước xử lý phức tạp.

Tuy nhiên, **CTE không mặc định luôn nhanh hơn**. Tùy DBMS và phiên bản, nó có thể được tối ưu, nội tuyến hoặc vật hóa. Hãy ưu tiên tính đúng và khả năng đọc trước, rồi xem kế hoạch thực thi khi cần tối ưu.

### 17.1. Khi chỉ cần một dòng con, ON không giới hạn số dòng

Nếu một khách hàng có hai đơn `CONFIRMED`, điều kiện trong `ON` vẫn ghép **cả hai đơn**. Nó không tự chọn “đơn mới nhất”.

Ví dụ yêu cầu: “Mỗi khách hàng một dòng, kèm tổng đơn đã xác nhận.” Hãy tổng hợp phía đơn trước:

```sql
WITH confirmed_summary AS (
    SELECT
        customer_id,
        COUNT(*) AS confirmed_count,
        SUM(order_amount) AS confirmed_amount
    FROM lesson182_orders
    WHERE order_status = 'CONFIRMED'
    GROUP BY customer_id
)
SELECT
    c.customer_id,
    c.customer_name,
    COALESCE(s.confirmed_count, 0) AS confirmed_count,
    COALESCE(s.confirmed_amount, 0) AS confirmed_amount
FROM lesson182_customers AS c
LEFT JOIN confirmed_summary AS s
    ON s.customer_id = c.customer_id
ORDER BY c.customer_id;
```

`confirmed_summary` có **tối đa một dòng trên mỗi khách hàng**. Vì vậy, khi `LEFT JOIN` vào `customers`, kết quả vẫn có đúng một dòng trên một khách hàng.

Nếu cần “đơn mới nhất”, có thể dùng `ROW_NUMBER()` hoặc kỹ thuật lấy dòng đầu tiên theo nhóm theo DBMS, nhưng phải định nghĩa cách giải quyết các đơn **trùng thời điểm**; chỉ thay điều kiện `ON` không tự chọn duy nhất một dòng.

## 18. JOIN ba bảng: WHERE có thể loại phía được bảo toàn ở bước trước

Trong truy vấn có nhiều JOIN, vị trí điều kiện và loại JOIN kế tiếp càng quan trọng.

Giả sử có:

- `customers`: mọi khách hàng.
- `orders`: đơn hàng, có thể không có.
- `order_items`: chi tiết đơn, có thể không có.

Nếu muốn giữ mọi khách hàng, một lựa chọn là:

```sql
-- Ví dụ thiết kế; bảng order_items chưa được tạo trong dữ liệu mẫu.
SELECT
    c.customer_id,
    o.order_id,
    i.item_id
FROM customers AS c
LEFT JOIN orders AS o
    ON o.customer_id = c.customer_id
LEFT JOIN order_items AS i
    ON i.order_id = o.order_id;
```

Hai `LEFT JOIN` liên tiếp có thể tiếp tục bảo toàn khách hàng không có đơn và đơn không có chi tiết.

Nhưng nếu thay JOIN cuối bằng `INNER JOIN`:

```sql
SELECT
    c.customer_id,
    o.order_id,
    i.item_id
FROM customers AS c
LEFT JOIN orders AS o
    ON o.customer_id = c.customer_id
INNER JOIN order_items AS i
    ON i.order_id = o.order_id;
```

thì khách hàng không có đơn sẽ không có `o.order_id` để ghép với chi tiết, nên **có thể biến mất** khỏi kết quả. Ngay cả đơn đã tồn tại nhưng chưa có chi tiết cũng bị loại.

**Một `LEFT JOIN` ở đầu chuỗi không tự bảo đảm các dòng bên trái được giữ đến hết toàn bộ câu truy vấn.** Hãy xét ảnh hưởng của cả các JOIN sau và `WHERE`.

### 18.1. Đặt ngoặc khi ghép một nhóm bảng bên phải

Nếu nghiệp vụ là “giữ mọi khách hàng, gắn **những đơn đã có chi tiết** nếu có”, có thể ghép `orders` với `order_items` trước rồi dùng `LEFT JOIN` cả nhóm vào khách hàng:

```sql
-- Ví dụ thiết kế; cần có bảng customers, orders và order_items.
SELECT
    c.customer_id,
    o.order_id,
    i.item_id
FROM customers AS c
LEFT JOIN (
    orders AS o
    INNER JOIN order_items AS i
        ON i.order_id = o.order_id
)
    ON o.customer_id = c.customer_id;
```

Cách này đặt `INNER JOIN` **bên trong nhóm nguồn bên phải**, rồi dùng `LEFT JOIN` để bảo toàn khách hàng. Tùy DBMS và yêu cầu, có thể diễn đạt bằng CTE để dễ đọc hơn.

Các đoạn trong phần này **minh họa ý nghĩa cấu trúc**, không chạy trực tiếp trên hai bảng `lesson182_customers` và `lesson182_orders` vì chưa có bảng chi tiết.

## 19. ON, WHERE và phép so sánh với NULL trong khóa JOIN

Nếu khóa liên hệ có thể `NULL`, phép so sánh thông thường:

```sql
ON l.optional_key = r.optional_key
```

**không** coi `NULL = NULL` là một cặp khớp. Hai giá trị `NULL` trong SQL có thể đại diện cho hai thông tin chưa biết khác nhau.

PostgreSQL có toán tử so sánh có xét `NULL`:

```sql
ON l.optional_key IS NOT DISTINCT FROM r.optional_key
```

Cách này coi hai `NULL` là “không khác nhau” trong phép so sánh. Nhưng **không tự động đúng cho mọi phép nối quan hệ**. Hai dòng đều thiếu mã khách hàng không có nghĩa thuộc cùng khách hàng; dùng phép nối null-safe mà không xét nghiệp vụ có thể tạo ghép sai.

### 19.1. Đừng dùng COALESCE tùy tiện để ghép khóa

```sql
-- Có thể ghép nhầm các dòng NULL với nhau hoặc với khóa thật 0.
ON COALESCE(l.customer_id, 0) = COALESCE(r.customer_id, 0)
```

Nếu `0` là một khóa hợp lệ, dòng có `NULL` có thể bị ghép nhầm với dòng có khóa `0`. Nếu cả hai bên `NULL`, chúng cũng có thể bị ghép mặc dù không cùng thực thể.

Khi khóa ngoại biểu diễn một quan hệ thật, thường nên để phép so sánh khóa theo mô hình dữ liệu đã thiết kế và dùng `LEFT JOIN` để thể hiện sự thiếu quan hệ. Không thay các khóa thiếu bằng giá trị giả chỉ để “làm khớp” nhiều hơn.

## 20. Khi nào chuyển điều kiện ON xuống WHERE là an toàn?

Với `INNER JOIN`, hai dạng sau thường có cùng ý nghĩa nếu các điều kiện thuần SQL không tạo ngữ nghĩa phụ đặc biệt:

```sql
SELECT ...
FROM a
INNER JOIN b
    ON a.id = b.a_id
   AND b.status = 'ACTIVE';
```

```sql
SELECT ...
FROM a
INNER JOIN b
    ON a.id = b.a_id
WHERE b.status = 'ACTIVE';
```

Cả hai đều chỉ trả các cặp khớp cả quan hệ khóa và trạng thái. Vì không có bước bảo toàn dòng không khớp, việc chuyển điều kiện thường không làm thay đổi tập dòng.

Nhưng với `LEFT JOIN`:

```sql
SELECT ...
FROM a
LEFT JOIN b
    ON a.id = b.a_id
   AND b.status = 'ACTIVE';
```

khác với:

```sql
SELECT ...
FROM a
LEFT JOIN b
    ON a.id = b.a_id
WHERE b.status = 'ACTIVE';
```

Trong dạng đầu, mọi dòng `a` vẫn được bảo toàn. Trong dạng sau, dòng `a` không có `b` đang hoạt động có thể biến mất.

Có một số phép chuyển đổi điều kiện mà optimizer **vẫn có thể thực hiện một cách hợp lệ** khi đã phân tích ngữ nghĩa và ràng buộc dữ liệu, nhưng người viết truy vấn không nên tự hoán đổi điều kiện giữa `ON` và `WHERE` của OUTER JOIN nếu chưa chứng minh chúng tương đương với yêu cầu nghiệp vụ.

## 21. Hiệu năng và chỉ mục: ưu tiên đúng ngữ nghĩa trước

Một ngộ nhận thường gặp: “Điều kiện ở `WHERE` luôn nhanh hơn `ON`” hoặc ngược lại. Không có quy tắc chung như vậy.

Các DBMS có bộ tối ưu hóa có thể:

- Đẩy bộ lọc xuống bước đọc bảng khi phép biến đổi không làm thay đổi kết quả.
- Chọn `Hash Join`, `Merge Join` hoặc `Nested Loop` tùy hệ quản trị và thống kê.
- Dùng chỉ mục trên khóa nối như `orders.customer_id`.
- Dùng chỉ mục kết hợp trên `(customer_id, order_status)` hoặc `(order_status, customer_id)` tùy nhu cầu truy vấn.
- Rút gọn một `LEFT JOIN` thành kế hoạch tương tự `INNER JOIN` khi `WHERE` chắc chắn loại mọi dòng không khớp.

Trong PostgreSQL, có thể tạo chỉ mục ví dụ:

```sql
CREATE INDEX lesson182_orders_customer_status_idx
    ON lesson182_orders (customer_id, order_status);
```

Và xem kế hoạch:

```sql
EXPLAIN
SELECT
    c.customer_id,
    o.order_id
FROM lesson182_customers AS c
LEFT JOIN lesson182_orders AS o
    ON o.customer_id = c.customer_id
   AND o.order_status = 'CONFIRMED';
```

Với bảng mẫu chỉ có vài dòng, DBMS có thể chọn quét bảng thay vì dùng chỉ mục; điều này bình thường. **Đừng chuyển điều kiện giữa `ON` và `WHERE` chỉ để thử tăng tốc nếu việc chuyển làm đổi tập kết quả.** Hãy giữ đúng ý nghĩa báo cáo trước, sau đó đo trên dữ liệu thực tế và xem kế hoạch thực thi.

### 21.1. Điều kiện được áp dụng trước GROUP BY hay sau GROUP BY?

`WHERE` lọc dòng **trước khi tạo nhóm**. `HAVING` lọc **các nhóm sau khi tổng hợp**. Cùng yêu cầu “liệt kê mọi khách hàng, số đơn đã xác nhận” thường không cần `HAVING` vì muốn giữ cả nhóm bằng 0.

```sql
SELECT
    c.customer_id,
    COUNT(o.order_id) AS confirmed_order_count
FROM lesson182_customers AS c
LEFT JOIN lesson182_orders AS o
    ON o.customer_id = c.customer_id
   AND o.order_status = 'CONFIRMED'
GROUP BY c.customer_id
HAVING COUNT(o.order_id) > 0;
```

Lệnh này có ý nghĩa “**chỉ giữ nhóm có ít nhất một đơn đã xác nhận**”, nên loại các nhóm bằng 0. Nó có thể đúng khi báo cáo chỉ cần khách hàng có đơn; không đúng khi yêu cầu giữ mọi khách hàng.

## 22. Những lỗi thường gặp khi dùng OUTER JOIN

### Lỗi 1: Lọc cột bảng phải ở WHERE rồi mất khách hàng không khớp

```sql
-- Không giữ khách hàng chỉ có đơn khác trạng thái hoặc không có đơn.
LEFT JOIN lesson182_orders AS o
    ON o.customer_id = c.customer_id
WHERE o.order_status = 'CONFIRMED'
```

Nếu mục tiêu là “mọi khách hàng, đơn xác nhận nếu có”:

```sql
LEFT JOIN lesson182_orders AS o
    ON o.customer_id = c.customer_id
   AND o.order_status = 'CONFIRMED'
```

### Lỗi 2: Thêm OR order_id IS NULL rồi nghĩ đã bảo toàn mọi khách hàng

Dạng `WHERE o.order_status = 'CONFIRMED' OR o.order_id IS NULL` vẫn **loại Bình**, vì Bình có đơn `PENDING` và `LEFT JOIN` theo khóa không sinh dòng đơn `NULL` cho Bình.

### Lỗi 3: Lọc bảng trái trong ON nhưng tưởng đã loại bảng trái

```sql
LEFT JOIN lesson182_orders AS o
    ON o.customer_id = c.customer_id
   AND c.is_active = TRUE
```

Khách hàng không hoạt động vẫn hiện do `LEFT JOIN` bảo toàn bảng trái, nhưng đơn của họ có thể không được ghép. Nếu muốn **chỉ có khách hàng hoạt động**, dùng `WHERE c.is_active = TRUE`.

### Lỗi 4: Đếm COUNT(*) như số bản ghi con

Khách hàng không có đơn vẫn tạo một dòng sau `LEFT JOIN`, nên `COUNT(*)` bằng 1 thay vì 0. Dùng `COUNT(o.order_id)` nếu đang đếm đơn và dữ liệu không bị nhân bởi JOIN khác.

### Lỗi 5: Nghĩ FULL JOIN + ON filter loại dữ liệu bên phải không đủ điều kiện

Trong `FULL OUTER JOIN`, một dòng bên phải không thỏa điều kiện `ON` có thể được giữ lại **như dòng không khớp**. Nếu muốn bỏ hoàn toàn các dòng đó khỏi nguồn, hãy lọc nguồn phải **trước khi FULL JOIN** hoặc xác định rõ bộ lọc kết quả.

### Lỗi 6: Dùng WHERE o.status <> 'CONFIRMED' để tìm cả khách chưa có đơn

Với `NULL`, phép `<>` cho `UNKNOWN` nên dòng không khớp bị loại. Nếu muốn tìm khách **không có đơn CONFIRMED**, dùng `NOT EXISTS` hoặc `LEFT JOIN ... ON status='CONFIRMED' WHERE o.order_id IS NULL`.

### Lỗi 7: Đổi RIGHT JOIN thành LEFT JOIN nhưng quên đổi thứ tự bảng

`LEFT` và `RIGHT` quy định **bên nào được bảo toàn**. Không thể chỉ thay từ `RIGHT` thành `LEFT` rồi mặc nhiên coi tương đương. Muốn đổi chiều tương đương, cần đảo vị trí nguồn cùng điều kiện liên hệ thích hợp.

### Lỗi 8: Tiếp tục INNER JOIN sau LEFT JOIN rồi làm mất dữ liệu

Một `INNER JOIN` phía sau có thể chỉ giữ những dòng đã có quan hệ cần thiết, qua đó loại bỏ những dòng `NULL` của JOIN trước. Hãy xem toàn bộ chuỗi JOIN, không chỉ câu `LEFT JOIN` đầu tiên.

### Lỗi 9: Dùng cột nullable của bảng phải để nhận diện “không khớp”

`WHERE o.optional_note IS NULL` có thể lấy cả **đơn hàng đã khớp nhưng trường ghi chú chưa nhập**. Dùng khóa chính phía phải `o.order_id IS NULL` nếu mục tiêu là tìm **không có dòng khớp**.

### Lỗi 10: Không đặt ngoặc khi kết hợp AND và OR

`AND` có độ ưu tiên cao hơn `OR`:

```sql
-- Dễ hiểu sai:
WHERE c.is_active = TRUE
   OR c.city = 'Hà Nội'
  AND o.order_status = 'CONFIRMED'
```

Nó được hiểu như `c.is_active = TRUE OR (c.city = 'Hà Nội' AND o.order_status = 'CONFIRMED')`, không phải `(c.is_active = TRUE OR c.city = 'Hà Nội') AND o.order_status = 'CONFIRMED'`.

Dùng ngoặc thể hiện đúng điều kiện lọc khách hàng, rồi chọn có nên đặt điều kiện đơn hàng trong `ON` hay `WHERE` theo yêu cầu bảo toàn.

## 23. Bài tập thực hành kèm lời giải

Các bài từ 1 đến 9 dùng bảng `lesson182_customers` và `lesson182_orders`. Bài 10 dùng dữ liệu CTE `a`/`b` độc lập.

### Bài 1. Dự đoán số dòng của LEFT JOIN

```sql
SELECT COUNT(*) AS joined_rows
FROM lesson182_customers AS c
LEFT JOIN lesson182_orders AS o
    ON o.customer_id = c.customer_id;
```

**Đáp án:** **9 dòng**. Có 7 đơn khớp khách hàng và 2 khách hàng không có đơn (Dũng, Lan), mỗi người được giữ thêm một dòng `NULL`.

### Bài 2. ON và WHERE khác nhau bao nhiêu khách hàng?

Truy vấn A:

```sql
SELECT COUNT(DISTINCT c.customer_id) AS customer_count
FROM lesson182_customers AS c
LEFT JOIN lesson182_orders AS o
    ON o.customer_id = c.customer_id
   AND o.order_status = 'CONFIRMED';
```

Truy vấn B:

```sql
SELECT COUNT(DISTINCT c.customer_id) AS customer_count
FROM lesson182_customers AS c
LEFT JOIN lesson182_orders AS o
    ON o.customer_id = c.customer_id
WHERE o.order_status = 'CONFIRMED';
```

**Đáp án:** A = **6**, B = **3**. A giữ đủ khách hàng và chỉ giới hạn đơn phù hợp; B chỉ giữ khách có đơn `CONFIRMED` (An, Chi, Hà).

### Bài 3. Liệt kê mọi khách hàng và số đơn CONFIRMED

**Yêu cầu:** Một dòng mỗi khách hàng, bao gồm nhóm có 0 đơn.

```sql
SELECT
    c.customer_id,
    c.customer_name,
    COUNT(o.order_id) AS confirmed_count
FROM lesson182_customers AS c
LEFT JOIN lesson182_orders AS o
    ON o.customer_id = c.customer_id
   AND o.order_status = 'CONFIRMED'
GROUP BY c.customer_id, c.customer_name
ORDER BY c.customer_id;
```

**Đáp án:** theo thứ tự khách hàng: **1, 0, 1, 0, 2, 0**.

### Bài 4. Những khách hàng không có bất kỳ đơn nào

```sql
SELECT c.customer_id, c.customer_name
FROM lesson182_customers AS c
LEFT JOIN lesson182_orders AS o
    ON o.customer_id = c.customer_id
WHERE o.order_id IS NULL
ORDER BY c.customer_id;
```

**Đáp án:** **Dũng** và **Lan**.

### Bài 5. Những khách hàng không có đơn CONFIRMED

```sql
SELECT c.customer_id, c.customer_name
FROM lesson182_customers AS c
LEFT JOIN lesson182_orders AS o
    ON o.customer_id = c.customer_id
   AND o.order_status = 'CONFIRMED'
WHERE o.order_id IS NULL
ORDER BY c.customer_id;
```

**Đáp án:** **Bình, Dũng, Lan**. Bình có đơn `PENDING` nhưng không có đơn `CONFIRMED`, vì thế phải xuất hiện trong kết quả.

### Bài 6. Chỉ khách hàng còn hoạt động và đơn CONFIRMED nếu có

```sql
SELECT
    c.customer_id,
    c.customer_name,
    o.order_id
FROM lesson182_customers AS c
LEFT JOIN lesson182_orders AS o
    ON o.customer_id = c.customer_id
   AND o.order_status = 'CONFIRMED'
WHERE c.is_active = TRUE
ORDER BY c.customer_id, o.order_id;
```

**Đáp án:** An–101, Bình–`NULL`, Dũng–`NULL`, Hà–106 và Hà–107. Chi và Lan không hoạt động nên bị `WHERE` loại.

### Bài 7. Lọc đơn CONFIRMED ngày 14/11 nhưng giữ mọi khách hàng

```sql
SELECT
    c.customer_id,
    c.customer_name,
    o.order_id
FROM lesson182_customers AS c
LEFT JOIN lesson182_orders AS o
    ON o.customer_id = c.customer_id
   AND o.order_status = 'CONFIRMED'
   AND o.order_date = DATE '2026-11-14'
ORDER BY c.customer_id, o.order_id;
```

**Đáp án:** An có đơn 101, Hà có đơn 107; Bình, Chi, Dũng, Lan vẫn có dòng với `o.order_id NULL`. Có đúng **6 dòng**, vì mỗi khách hàng có nhiều nhất một đơn phù hợp ngày này trong dữ liệu mẫu.

### Bài 8. Vì sao WHERE + OR IS NULL không sửa đúng?

```sql
SELECT
    c.customer_id,
    c.customer_name
FROM lesson182_customers AS c
LEFT JOIN lesson182_orders AS o
    ON o.customer_id = c.customer_id
WHERE o.order_status = 'CONFIRMED'
   OR o.order_id IS NULL;
```

**Đáp án:** Bình **không xuất hiện**. Bình có đơn 103 nên `LEFT JOIN` không tạo dòng có `o.order_id NULL`; nhưng đơn 103 không phải `CONFIRMED`. Muốn mọi khách hàng, đặt điều kiện `o.order_status = 'CONFIRMED'` vào `ON`.

### Bài 9. Viết lại RIGHT JOIN bằng LEFT JOIN

Truy vấn gốc:

```sql
SELECT
    o.order_id,
    c.customer_name
FROM lesson182_customers AS c
RIGHT JOIN lesson182_orders AS o
    ON c.customer_id = o.customer_id
   AND c.is_active = TRUE
ORDER BY o.order_id;
```

**Một lời giải tương đương:**

```sql
SELECT
    o.order_id,
    c.customer_name
FROM lesson182_orders AS o
LEFT JOIN lesson182_customers AS c
    ON c.customer_id = o.customer_id
   AND c.is_active = TRUE
ORDER BY o.order_id;
```

**Giải thích:** Đặt `orders` ở phía trái của `LEFT JOIN` để bảo toàn mọi đơn; đơn của Chi vẫn xuất hiện nhưng không ghép tên Chi vì `is_active = FALSE`.

### Bài 10. FULL OUTER JOIN có thể sinh hai dòng cùng khóa không?

Giả sử A có dòng `(id=3, 'A3')`, B có dòng `(id=3, status='PENDING')`. Chạy:

```sql
WITH a (id, label) AS (
    VALUES (3, 'A3')
),
b (id, status) AS (
    VALUES (3, 'PENDING')
)
SELECT
    a.id AS a_id,
    a.label,
    b.id AS b_id,
    b.status
FROM a
FULL JOIN b
    ON a.id = b.id
   AND b.status = 'READY';
```

**Đáp án:** Có **2 dòng không khớp**: một dòng chứa A3 với các cột B là `NULL` và một dòng chứa B3 `PENDING` với các cột A là `NULL`. Hai dòng có cùng **giá trị id 3** nhưng không ghép với nhau vì điều kiện `ON` loại cặp khớp; `FULL JOIN` bảo toàn mỗi phía riêng rẽ.

### Bài 11. So sánh hai cách giữ mọi khách hàng

Hãy xác định liệu hai truy vấn sau có cùng kết quả về **số đơn CONFIRMED trên từng khách hàng** hay không.

**Truy vấn A:**

```sql
SELECT
    c.customer_id,
    COUNT(o.order_id) AS confirmed_count
FROM lesson182_customers AS c
LEFT JOIN lesson182_orders AS o
    ON o.customer_id = c.customer_id
   AND o.order_status = 'CONFIRMED'
GROUP BY c.customer_id
ORDER BY c.customer_id;
```

**Truy vấn B:**

```sql
SELECT
    c.customer_id,
    COUNT(o.order_id) FILTER (
        WHERE o.order_status = 'CONFIRMED'
    ) AS confirmed_count
FROM lesson182_customers AS c
LEFT JOIN lesson182_orders AS o
    ON o.customer_id = c.customer_id
GROUP BY c.customer_id
ORDER BY c.customer_id;
```

**Đáp án:** **Có**, với số liệu và yêu cầu đếm đơn hiện tại, hai truy vấn trả số đơn `CONFIRMED` là **1, 0, 1, 0, 2, 0**. Truy vấn A chỉ ghép đơn đủ điều kiện; truy vấn B ghép mọi đơn rồi lọc đầu vào riêng của `COUNT`. Lưu ý `FILTER` là cú pháp PostgreSQL, không phải DBMS nào cũng hỗ trợ.

### Bài 12. Chọn vị trí điều kiện theo yêu cầu

Cho ba yêu cầu:

1. Chỉ trả khách hàng tại `Hà Nội`, kèm mọi đơn nếu có.
2. Giữ **mọi khách hàng**, chỉ ghép đơn `PENDING` nếu có.
3. Chỉ trả khách hàng có ít nhất một đơn `PENDING`, mỗi khách hàng một lần.

**Gợi ý lời giải:**

1. `WHERE c.city = 'Hà Nội'` sau `LEFT JOIN` vì cần **lọc khách hàng**.
2. `LEFT JOIN orders AS o ON o.customer_id = c.customer_id AND o.order_status = 'PENDING'` vì cần **giữ mọi khách hàng**.
3. `WHERE EXISTS (SELECT 1 FROM orders AS o WHERE o.customer_id = c.customer_id AND o.order_status = 'PENDING')` vì chỉ cần kiểm tra **sự tồn tại** của đơn thỏa trạng thái và tránh trùng khách hàng.

Trong ví dụ thực hành, Hà Nội có **An** và **Hà**; khách có đơn `PENDING` là **Bình** và **Chi**.

## 24. Bảng ghi nhớ nhanh

| Mục tiêu | Vị trí điều kiện hoặc mẫu truy vấn |
|---|---|
| Giữ mọi dòng bên trái, chỉ ghép dữ liệu bên phải đủ điều kiện | `LEFT JOIN r ON key_match AND r.filter` |
| Lọc những dòng **cuối cùng** theo thuộc tính bên phải | `WHERE r.filter`, hiểu rằng dòng không khớp có thể bị loại |
| Chỉ lấy một phần dòng bên trái | `WHERE l.filter` |
| Giữ mọi dòng bên trái nhưng hạn chế **khả năng ghép** theo thuộc tính bên trái | `ON key_match AND l.filter` |
| Tìm dòng trái không có bất kỳ dòng phải | `LEFT JOIN ... ON key_match WHERE r.not_null_id IS NULL` hoặc `NOT EXISTS` |
| Tìm dòng trái không có dòng phải **thỏa một điều kiện** | `LEFT JOIN ... ON key_match AND r.filter WHERE r.not_null_id IS NULL` hoặc `NOT EXISTS` |
| Đếm bản ghi con sau LEFT JOIN | `COUNT(r.primary_key)` nếu chưa bị nhân dòng bởi JOIN khác |
| Giữ đủ nhóm và đếm bản ghi con có điều kiện | Lọc trong `ON` rồi `GROUP BY`, hoặc dùng aggregate `FILTER`/`CASE` phù hợp |
| Bảo toàn mọi dòng bên phải | `RIGHT JOIN` hoặc đảo thứ tự nguồn dùng `LEFT JOIN` |
| FULL JOIN nhưng muốn bỏ bớt một nguồn trước khi nối | Lọc nguồn bằng CTE/subquery **trước** `FULL JOIN` |
| INNER JOIN với điều kiện thêm | Điều kiện ở `ON` hoặc `WHERE` thường tương đương về tập dòng; OUTER JOIN thì không |

**Nguyên tắc cuối cùng:** Trong OUTER JOIN, điều kiện `ON` trả lời **“hai dòng có khớp với nhau hay không?”**, còn `WHERE` trả lời **“dòng kết quả sau khi ghép có được giữ lại hay không?”**. Nếu muốn **giữ tất cả thực thể ở phía được bảo toàn** nhưng chỉ lấy bản ghi liên quan đạt tiêu chí, thường đặt tiêu chí của bản ghi liên quan vào `ON` hoặc lọc nguồn liên quan trước JOIN. Nếu muốn **loại chính những thực thể không đạt điều kiện**, đặt bộ lọc tương ứng ở `WHERE` hoặc dùng `EXISTS`/`NOT EXISTS` để biểu đạt mục đích rõ ràng.

