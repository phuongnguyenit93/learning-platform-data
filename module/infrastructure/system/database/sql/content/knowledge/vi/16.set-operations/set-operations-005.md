# Ngữ nghĩa bản sao với biến thể ALL khi được hỗ trợ

Trong toán học tập hợp, một phần tử hoặc **thuộc tập** hoặc **không thuộc tập**; việc viết phần tử đó ba lần không làm tập có thêm ba phần tử khác nhau. Tuy nhiên, trong SQL, kết quả truy vấn có thể chứa **nhiều hàng giống hệt nhau**. Ví dụ, một khách hàng mua cùng sản phẩm ba lần có thể tạo ba dòng mang cùng mã sản phẩm; điều này không nhất thiết là dữ liệu lỗi.

Sự khác nhau giữa **tập hợp** (*set*) và **đa tập** (*multiset* hay *bag*) quyết định kết quả của các phép toán tập hợp trong SQL:

- `UNION`, `INTERSECT` và `EXCEPT` theo mặc định thường có ngữ nghĩa **`DISTINCT`**: loại bản sao trùng trong kết quả.
- `UNION ALL` **giữ toàn bộ số lần xuất hiện** từ hai phía.
- `INTERSECT ALL` **giữ số bản sao chung**, theo số lần xuất hiện ít hơn giữa hai phía, trên hệ quản trị có hỗ trợ.
- `EXCEPT ALL` **trừ số bản sao** của phía phải khỏi phía trái nhưng không cho số lượng âm, trên hệ quản trị có hỗ trợ.

Đây không chỉ là chuyện tối ưu tốc độ. Thêm hoặc bỏ `ALL` có thể thay đổi **ý nghĩa báo cáo**, **số dòng đối soát** và **tổng tiền**.

Bài học thuộc chương **Phép toán tập hợp** của Database SQL. Phần thực hành sử dụng **PostgreSQL** vì hệ này hỗ trợ đầy đủ `UNION ALL`, `INTERSECT ALL` và `EXCEPT ALL`. Với SQL Server, SQLite và một số phiên bản hệ quản trị khác, cần xem khả năng hỗ trợ từng biến thể; bài có hướng mô phỏng các phép `ALL` bằng hàm cửa sổ khi cần.

## 1. Từ SET sang BAG: đếm số lần một hàng xuất hiện

Một tập hợp toán học có thể được viết là:

```text
A = {1, 2, 3}
B = {1, 2, 4}
```

Ở đây không có khái niệm “số 1 xuất hiện ba lần”. Nhưng một tập hàng SQL có thể được mô tả như sau:

```text
A = [1, 1, 1, 2, 2, 3, NULL, NULL]
B = [1, 1, 2, 2, 2, 4, NULL]
```

Ngoặc vuông ở đây chỉ là cách minh họa **đa tập**; không hàm ý SQL bảo đảm thứ tự của các hàng.

Ta định nghĩa **bội số** (*multiplicity*) của một giá trị `v` trong đa tập `A` là:

\[
m_A(v) = \text{số lần giá trị }v\text{ xuất hiện trong }A
\]

Với dữ liệu trên:

| Giá trị `v` | `m_A(v)` | `m_B(v)` |
| --- | ---: | ---: |
| 1 | 3 | 2 |
| 2 | 2 | 3 |
| 3 | 1 | 0 |
| 4 | 0 | 1 |
| `NULL` | 2 | 1 |
| **Tổng số hàng** | **8** | **7** |

Từ đây, mọi phép `ALL` đều có thể được giải thích bằng **phép tính trên số lần xuất hiện**, thay vì đoán kết quả từ tên toán tử.

### 1.1. Vì sao SQL giữ được nhiều hàng trùng nhau?

Trong mô hình quan hệ lý thuyết, quan hệ là một tập bộ giá trị. Trong SQL thực tế, nhiều phép truy vấn mặc định hoạt động theo ngữ nghĩa **bag**.

Ví dụ:

```sql
SELECT category
FROM products;
```

Nếu bảng có 50 sản phẩm thuộc `Books`, kết quả có thể chứa 50 hàng cùng giá trị `'Books'`. SQL **không** tự gộp chúng thành một dòng.

Nếu muốn danh sách **các nhóm sản phẩm khác nhau**, viết:

```sql
SELECT DISTINCT category
FROM products;
```

Đối với phép `SELECT` thông thường, `ALL` là mặc định về việc giữ bản sao; về ngữ nghĩa:

```sql
SELECT ALL category FROM products;
```

tương ứng cách giữ các hàng như `SELECT category FROM products`. Tuy nhiên, các **phép toán tập hợp** như `UNION` lại có mặc định loại trùng, nên phải đặc biệt chú ý vị trí từ khóa `ALL`.

### 1.2. “Hàng trùng” là trùng theo những cột nào?

Hai hàng được xem là bản sao của nhau trong phép toán tập hợp khi **toàn bộ các giá trị cột được chọn vào kết quả** tương đương theo ngữ nghĩa so sánh trùng của phép toán.

Ví dụ:

```text
SELECT product_id         → hai dòng có cùng product_id có thể trùng
SELECT product_id, price  → phải cùng cả product_id lẫn price
SELECT sale_id, product_id → sale_id riêng biệt có thể làm các hàng không trùng
```

Một dòng giao dịch có mã `sale_id` duy nhất có thể trở thành “bản sao” của giao dịch khác nếu câu truy vấn **không chọn cột sale_id**, chỉ chọn các thuộc tính giống nhau. Đó là một quyết định về **hình dạng kết quả**, không phải database đã xóa hoặc sửa giao dịch gốc.

## 2. Tạo hai đa tập mẫu trong PostgreSQL

Các ví dụ sau dùng bảng tạm, tồn tại trong phiên PostgreSQL hiện tại.

```sql
CREATE TEMP TABLE bag_a (
    row_id INTEGER PRIMARY KEY,
    value_key INTEGER
);

CREATE TEMP TABLE bag_b (
    row_id INTEGER PRIMARY KEY,
    value_key INTEGER
);

INSERT INTO bag_a (row_id, value_key) VALUES
    (1, 1),
    (2, 1),
    (3, 1),
    (4, 2),
    (5, 2),
    (6, 3),
    (7, NULL),
    (8, NULL);

INSERT INTO bag_b (row_id, value_key) VALUES
    (1, 1),
    (2, 1),
    (3, 2),
    (4, 2),
    (5, 2),
    (6, 4),
    (7, NULL);
```

Ở đây, `row_id` xác định duy nhất mỗi **dòng nguồn**, nhưng các phép toán tập hợp sẽ chỉ chọn `value_key` để cố ý cho phép bản sao.

Quan sát bội số của từng bảng:

```sql
SELECT value_key, COUNT(*) AS occurrences
FROM bag_a
GROUP BY value_key
ORDER BY value_key NULLS LAST;

SELECT value_key, COUNT(*) AS occurrences
FROM bag_b
GROUP BY value_key
ORDER BY value_key NULLS LAST;
```

Các bảng đếm sẽ khớp với bảng `m_A` và `m_B` ở phần trước. Dùng `COUNT(*)` vì cần đếm **cả những hàng có `value_key IS NULL`**.

**Chú ý:** `COUNT(value_key)` bỏ qua `NULL`. Nếu dùng nó để đếm bội số trong nhóm `NULL`, ta sẽ tính nhầm 0 thay vì 2 hoặc 1. Đây là lỗi quan trọng khi kiểm chứng biến thể `ALL`.

## 3. Bảng công thức cho mọi biến thể

Với mỗi giá trị hay bộ giá trị `v`, hai phía có số lần xuất hiện `m_A(v)` và `m_B(v)`. Những phép toán có ngữ nghĩa:

| Phép toán | Bội số của `v` trong kết quả |
| --- | --- |
| `A UNION ALL B` | \(m_A(v)+m_B(v)\) |
| `A UNION DISTINCT B` | \(1\) nếu `v` có ở ít nhất một phía, ngược lại \(0\) |
| `A INTERSECT ALL B` | \(\min(m_A(v),m_B(v))\) |
| `A INTERSECT DISTINCT B` | \(1\) nếu `v` có ở cả hai phía, ngược lại \(0\) |
| `A EXCEPT ALL B` | \(\max(m_A(v)-m_B(v),0)\) |
| `A EXCEPT DISTINCT B` | \(1\) nếu `v` có ở A và không có ở B, ngược lại \(0\) |

Trong bảng, `DISTINCT` có thể được ghi tường minh để đọc rõ. Với `UNION`, `INTERSECT` và `EXCEPT` trong PostgreSQL, nếu không ghi `ALL`, hành vi mặc định là loại bản sao như `DISTINCT`.

Áp dụng công thức lên dữ liệu mẫu:

| Giá trị | A | B | `UNION ALL` | `INTERSECT ALL` | `A EXCEPT ALL B` | `B EXCEPT ALL A` |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | 3 | 2 | 5 | 2 | 1 | 0 |
| 2 | 2 | 3 | 5 | 2 | 0 | 1 |
| 3 | 1 | 0 | 1 | 0 | 1 | 0 |
| 4 | 0 | 1 | 1 | 0 | 0 | 1 |
| `NULL` | 2 | 1 | 3 | 1 | 1 | 0 |
| **Tổng số hàng** | **8** | **7** | **15** | **5** | **3** | **2** |

Đây là “bảng đáp án” để đối chiếu với SQL ở các phần tiếp theo.

## 4. UNION và UNION ALL: ghép hàng rồi có loại bản sao hay không?

### 4.1. UNION mặc định loại bản sao

```sql
SELECT value_key FROM bag_a
UNION
SELECT value_key FROM bag_b
ORDER BY value_key NULLS LAST;
```

Kết quả gồm **5 giá trị khác nhau**:

```text
1
2
3
4
NULL
```

Dù `1` xuất hiện ba lần ở A và hai lần ở B, `UNION` mặc định chỉ giữ **một** `1`. Tương tự, cả ba hàng `NULL` của hai phía được gộp thành **một** hàng `NULL` trong phép loại trùng của set operator.

Cách ghi rõ:

```sql
SELECT value_key FROM bag_a
UNION DISTINCT
SELECT value_key FROM bag_b
ORDER BY value_key NULLS LAST;
```

### 4.2. UNION ALL giữ tất cả bản sao

```sql
SELECT value_key FROM bag_a
UNION ALL
SELECT value_key FROM bag_b
ORDER BY value_key NULLS LAST;
```

Kết quả có **15 hàng**:

```text
1     (5 lần)
2     (5 lần)
3     (1 lần)
4     (1 lần)
NULL  (3 lần)
```

`UNION ALL` không tự loại bản sao **bên trong A**, **bên trong B**, hoặc **giữa A và B**. Nó chỉ ghép các hàng từ hai kết quả theo ngữ nghĩa đa tập.

### 4.3. Tự kiểm chứng bằng COUNT(*)

Vì đọc 15 hàng lặp trên màn hình dễ nhầm, có thể đếm từng giá trị:

```sql
WITH combined AS (
    SELECT value_key FROM bag_a
    UNION ALL
    SELECT value_key FROM bag_b
)
SELECT value_key, COUNT(*) AS occurrences
FROM combined
GROUP BY value_key
ORDER BY value_key NULLS LAST;
```

Kết quả:

| `value_key` | `occurrences` |
| --- | ---: |
| 1 | 5 |
| 2 | 5 |
| 3 | 1 |
| 4 | 1 |
| `NULL` | 3 |

Thao tác kiểm chứng này không thay đổi ý nghĩa `UNION ALL`; nó chỉ **tổng hợp lại kết quả** để nhìn rõ bội số.

### 4.4. UNION ALL không phải JOIN

`UNION ALL` ghép các **hàng của hai truy vấn** với số cột tương ứng. Nó không ghép một hàng A với một hàng B theo khóa:

```text
UNION ALL: A rows + B rows  → xếp hai tập hàng vào cùng cấu trúc
JOIN:      A row × B row   → tạo cặp hàng phù hợp điều kiện nối
```

Nếu A có 3 hàng `1` và B có 2 hàng `1`:

- `UNION ALL` cho **5** hàng `1`.
- `INNER JOIN` trên điều kiện `A.value_key = B.value_key` có thể tạo **3 × 2 = 6** cặp hàng.
- `INTERSECT ALL` cho **min(3, 2) = 2** hàng `1`.

Ba phép toán trả lời ba câu hỏi khác nhau. Việc chúng cùng nhìn vào hai bảng không làm chúng thay thế cho nhau.

## 5. INTERSECT và INTERSECT ALL: phần chung theo ngữ nghĩa tập hoặc đa tập

`INTERSECT` dùng để chọn các hàng xuất hiện ở **cả hai phía**.

### 5.1. INTERSECT mặc định DISTINCT

```sql
SELECT value_key FROM bag_a
INTERSECT
SELECT value_key FROM bag_b
ORDER BY value_key NULLS LAST;
```

Kết quả:

```text
1
2
NULL
```

Có **3 hàng**, mỗi giá trị chỉ xuất hiện một lần. Giá trị `3` chỉ thuộc A; `4` chỉ thuộc B nên không nằm trong giao. Cả hai phía đều có `NULL` nên phép `INTERSECT` xem đó là một giá trị xuất hiện chung về mặt xử lý hàng trùng.

### 5.2. INTERSECT ALL giữ số bản sao chung

PostgreSQL hỗ trợ:

```sql
SELECT value_key FROM bag_a
INTERSECT ALL
SELECT value_key FROM bag_b
ORDER BY value_key NULLS LAST;
```

Kết quả có **5 hàng**:

```text
1     (2 lần)
2     (2 lần)
NULL  (1 lần)
```

Lý do:

- `1` có 3 bản sao ở A và 2 bản sao ở B → giữ **2**.
- `2` có 2 bản sao ở A và 3 bản sao ở B → giữ **2**.
- `NULL` có 2 bản sao ở A và 1 ở B → giữ **1**.
- `3`/`4` không nằm ở cả hai phía → giữ **0**.

Công thức:

\[
m_{A\ \mathrm{INTERSECT\ ALL}\ B}(v)
=\min(m_A(v),m_B(v))
\]

### 5.3. Kiểm chứng số lần xuất hiện

```sql
WITH common_rows AS (
    SELECT value_key FROM bag_a
    INTERSECT ALL
    SELECT value_key FROM bag_b
)
SELECT value_key, COUNT(*) AS occurrences
FROM common_rows
GROUP BY value_key
ORDER BY value_key NULLS LAST;
```

| `value_key` | Số hàng |
| --- | ---: |
| 1 | 2 |
| 2 | 2 |
| `NULL` | 1 |

**Không phải** `INTERSECT ALL` chọn tất cả các cặp hàng khớp như `JOIN`. Nó giữ **số bản sao tối đa có thể ghép một-một** giữa hai đa tập, tức là số nhỏ hơn của hai bội số.

### 5.4. Khi nào INTERSECT ALL có ý nghĩa?

Một ví dụ là đối chiếu hai tệp được phép chứa dòng trùng:

```text
Danh sách A: [SKU10, SKU10, SKU10, SKU20]
Danh sách B: [SKU10, SKU10, SKU20, SKU20]

INTERSECT DISTINCT: [SKU10, SKU20]
INTERSECT ALL:      [SKU10, SKU10, SKU20]
```

Nếu cần biết **có mã nào xuất hiện ở cả hai tệp**, `INTERSECT` là đủ. Nếu cần biết **bao nhiêu lần xuất hiện có thể đối chiếu** giữa hai tệp, `INTERSECT ALL` phù hợp hơn.

Tuy nhiên, đừng nhầm số lần xuất hiện của một SKU với **số lượng sản phẩm thực** trong kho. Nếu mỗi dòng còn có `quantity`, phải xác định mỗi dòng đại diện cho một đơn vị hay một giao dịch có số lượng riêng trước khi coi số bản sao là số lượng hàng hóa.

## 6. EXCEPT và EXCEPT ALL: trừ hàng theo sự tồn tại hay theo số bản sao

`EXCEPT` có hướng: `A EXCEPT B` hỏi những hàng ở A **không có trong B**. `EXCEPT ALL` hỏi còn **bao nhiêu bản sao của từng hàng** ở A sau khi trừ số bản sao của B.

### 6.1. EXCEPT mặc định DISTINCT

```sql
SELECT value_key FROM bag_a
EXCEPT
SELECT value_key FROM bag_b
ORDER BY value_key NULLS LAST;
```

Kết quả chỉ có:

```text
3
```

Tại sao `1` không còn, dù A có ba bản sao và B chỉ có hai? Vì `EXCEPT` **không có `ALL`** hoạt động theo tư duy tập hợp: chỉ cần `1` xuất hiện ở B, giá trị `1` bị loại **hoàn toàn** khỏi kết quả.

Tương tự, `2` và `NULL` xuất hiện ở B nên bị loại khỏi tập `A EXCEPT B`. Chỉ `3` có ở A mà không có ở B.

### 6.2. EXCEPT ALL trừ bội số, không trừ giá trị một cách tuyệt đối

```sql
SELECT value_key FROM bag_a
EXCEPT ALL
SELECT value_key FROM bag_b
ORDER BY value_key NULLS LAST;
```

Kết quả có **3 hàng**:

```text
1     (1 lần)
3     (1 lần)
NULL  (1 lần)
```

Giải thích:

- `1`: A có 3, B có 2 → còn `3 − 2 = 1`.
- `2`: A có 2, B có 3 → còn `max(2 − 3, 0) = 0`.
- `3`: A có 1, B không có → còn 1.
- `NULL`: A có 2, B có 1 → còn 1.

Công thức:

\[
m_{A\ \mathrm{EXCEPT\ ALL}\ B}(v)
=\max(m_A(v)-m_B(v),0)
\]

**EXCEPT ALL không tạo số bản sao âm.** Một phía B có 100 bản sao của `v` không thể làm phía A “còn −99 bản sao”; kết quả thấp nhất là 0.

### 6.3. Đảo vế cho kết quả khác

```sql
SELECT value_key FROM bag_b
EXCEPT ALL
SELECT value_key FROM bag_a
ORDER BY value_key NULLS LAST;
```

Kết quả:

```text
2
4
```

Vì B có nhiều hơn A một bản sao `2` và có một bản sao `4` mà A không có.

So sánh:

| Hướng | Kết quả của `EXCEPT ALL` |
| --- | --- |
| A trừ B | `[1, 3, NULL]` |
| B trừ A | `[2, 4]` |

`EXCEPT` và `EXCEPT ALL` **không có tính giao hoán**: đổi vị trí hai phía đổi ý nghĩa.

### 6.4. Kiểm chứng với truy vấn tổng hợp

```sql
WITH leftover AS (
    SELECT value_key FROM bag_a
    EXCEPT ALL
    SELECT value_key FROM bag_b
)
SELECT value_key, COUNT(*) AS occurrences
FROM leftover
GROUP BY value_key
ORDER BY value_key NULLS LAST;
```

Kết quả:

| Giá trị | Số bản sao còn lại |
| --- | ---: |
| 1 | 1 |
| 3 | 1 |
| `NULL` | 1 |

### 6.5. EXCEPT ALL khác phản kết nối NOT EXISTS

Đây là khác biệt quan trọng trong chương SQL về phép toán tập hợp và kết nối bảng.

Giả sử A có **3** bản sao `1`; B có **2** bản sao `1`.

- `A EXCEPT ALL B` giữ **1** bản sao `1`.
- `A EXCEPT B` giữ **0** bản sao `1`.
- `WHERE NOT EXISTS` với điều kiện một hàng B có cùng `1` sẽ loại **mọi hàng A bằng 1** vì có ít nhất một hàng B khớp.

`NOT EXISTS` là câu hỏi “**có bất kỳ khớp nào không?**”, còn `EXCEPT ALL` là “**số bản sao còn lại sau khi trừ là bao nhiêu?**”.

Hai phép có thể trả kết quả khác nhau rõ rệt trên dữ liệu lặp. Không thay `EXCEPT ALL` bằng phản kết nối khi nghiệp vụ cần trừ **số lần**.

## 7. NULL được xem là gì trong phép toán tập hợp?

Trong điều kiện SQL thông thường:

```sql
SELECT NULL::integer = NULL::integer AS equals_null;
```

Kết quả là `NULL` (tương đương trạng thái `UNKNOWN`), không phải `TRUE`. Nhưng **quy tắc nhận diện hàng trùng của set operator khác với phép so sánh `=` trong `WHERE`**.

Trong PostgreSQL, các hàng chứa `NULL` ở cùng vị trí được xem là **không khác biệt** khi loại bản sao hoặc đối chiếu số bản sao cho phép toán tập hợp.

Với hai bảng mẫu:

| Phép toán trên `value_key` | Số hàng `NULL` trong kết quả |
| --- | ---: |
| `UNION` | 1 |
| `UNION ALL` | 3 |
| `INTERSECT` | 1 |
| `INTERSECT ALL` | 1 |
| `A EXCEPT B` | 0 |
| `A EXCEPT ALL B` | 1 |
| `B EXCEPT ALL A` | 0 |

Đây không phải là ngoại lệ tùy hứng. Khi một phép toán cần xác định **hàng nào trùng nhau**, nó dùng ngữ nghĩa loại trùng của SQL thay vì áp dụng bộ lọc `WHERE col = NULL`.

### 7.1. GROUP BY NULL để kiểm chứng số bản sao

```sql
SELECT value_key, COUNT(*) AS occurrences
FROM bag_a
GROUP BY value_key
ORDER BY value_key NULLS LAST;
```

`GROUP BY` gom các hàng có `value_key = NULL` vào **một nhóm** với `COUNT(*) = 2`. Cơ chế này tương thích với cách nhận diện tập bản sao khi giải thích `UNION`/`INTERSECT`/`EXCEPT`.

### 7.2. COUNT(DISTINCT col) không luôn bằng số hàng của SELECT DISTINCT col

Trong PostgreSQL:

```sql
SELECT COUNT(DISTINCT value_key) AS count_non_null_distinct
FROM bag_a;
-- 3: các giá trị 1, 2, 3

SELECT COUNT(*) AS count_distinct_rows
FROM (
    SELECT DISTINCT value_key FROM bag_a
) AS d;
-- 4: các hàng 1, 2, 3, NULL
```

`COUNT(DISTINCT value_key)` không đếm `NULL`, còn `SELECT DISTINCT value_key` có thể trả một hàng `NULL`. Khi xác minh kết quả các phép toán tập hợp, muốn đếm **số hàng** hãy đếm `COUNT(*)` trên subquery kết quả, không tự thay bằng `COUNT(DISTINCT col)` nếu cột có thể `NULL`.

### 7.3. Dùng IS NOT DISTINCT FROM trong phép so sánh khi mô phỏng

PostgreSQL cung cấp:

```sql
SELECT
    NULL::integer IS NOT DISTINCT FROM NULL::integer
        AS nulls_match;
-- TRUE
```

Biểu thức này hữu ích khi cần tự viết phép so sánh **cùng giá trị hoặc cùng `NULL`** trong một truy vấn mô phỏng `ALL`. Nhưng cú pháp và khả năng dùng trên từng DBMS khác nhau; phần mô phỏng sau có thêm dạng so sánh `NULL` bằng điều kiện tường minh.

## 8. Phép toán so sánh toàn bộ HÀNG, không chỉ một cột

Xét hai bộ giá trị:

```text
A: (customer_id=1, status='paid')
B: (customer_id=1, status='pending')
```

Nếu chọn chỉ `customer_id`, hai hàng được coi là cùng giá trị `1`. Nếu chọn cả `customer_id` và `status`, chúng là **hai hàng khác nhau** vì trạng thái khác nhau.

Ví dụ PostgreSQL:

```sql
WITH left_rows(customer_id, status) AS (
    VALUES
        (1, 'paid'::text),
        (1, 'paid'::text),
        (1, 'pending'::text),
        (2, 'paid'::text)
),
right_rows(customer_id, status) AS (
    VALUES
        (1, 'paid'::text),
        (1, 'cancelled'::text),
        (2, 'paid'::text)
)
SELECT customer_id, status FROM left_rows
INTERSECT ALL
SELECT customer_id, status FROM right_rows
ORDER BY customer_id, status;
```

Kết quả:

| `customer_id` | `status` | Số bản sao |
| ---: | --- | ---: |
| 1 | paid | 1 |
| 2 | paid | 1 |

`(1, pending)` không xuất hiện ở B, nên bị loại. `(1, paid)` xuất hiện hai lần ở A nhưng một lần ở B, nên giao đa tập chỉ giữ một bản sao.

### 8.1. Cột ID duy nhất có thể khiến bản sao “biến mất”

Nếu ta chọn cả `row_id` trong bảng `bag_a` và `bag_b`:

```sql
SELECT row_id, value_key FROM bag_a
UNION
SELECT row_id, value_key FROM bag_b;
```

phép loại trùng diễn ra trên cặp `(row_id, value_key)`, không chỉ `value_key`. Chỉ số `row_id` giống nhau ở hai bảng có thể tạo cặp trùng một cách tình cờ; ngược lại, hai dòng có `value_key` giống nhau nhưng `row_id` khác nhau vẫn là **hai hàng kết quả khác nhau**.

Bởi vậy, không thể nói chung chung “`UNION` loại mọi sản phẩm trùng” nếu truy vấn thực tế chọn thêm các cột làm các hàng không còn trùng. Hãy luôn ghi rõ **danh sách cột của phép toán**.

### 8.2. Số cột, kiểu dữ liệu và thứ tự tương ứng

Hai nhánh của một phép toán tập hợp phải có **số cột tương thích** và kiểu dữ liệu có thể được hệ quản trị giải quyết tương ứng theo từng vị trí.

```sql
-- Hợp lệ: cùng một cột kiểu INTEGER.
SELECT value_key FROM bag_a
UNION ALL
SELECT value_key FROM bag_b;
```

```sql
-- CỐ Ý SAI: hai cột so với một cột.
SELECT row_id, value_key FROM bag_a
UNION ALL
SELECT value_key FROM bag_b;
```

Câu thứ hai bị từ chối vì số cột không bằng nhau. Khả năng tự chuyển kiểu giữa hai nhánh phụ thuộc DBMS; chuyển ép kiểu có thể làm thay đổi khái niệm “hàng giống nhau”. Ví dụ, so sánh mã chuỗi `'001'` với số `1` không nên giao cho chuyển kiểu tự động khi hai mã có thể mang ý nghĩa nghiệp vụ khác nhau.

### 8.3. Tên cột kết quả thường lấy từ nhánh đầu

Trong PostgreSQL:

```sql
SELECT value_key AS item_code FROM bag_a
UNION ALL
SELECT value_key AS other_name FROM bag_b
ORDER BY item_code;
```

Tên cột của kết quả set operator lấy theo cấu trúc nhánh đầu; alias `other_name` ở nhánh thứ hai không làm đổi tên cột hợp nhất. Dùng alias nhất quán hoặc bọc biểu thức set trong CTE để dễ đọc và để API không phụ thuộc vào một nhánh được sửa về sau.

## 9. ALL thuộc toán tử nào? Vị trí rất quan trọng

So sánh:

```sql
SELECT DISTINCT value_key FROM bag_a
UNION ALL
SELECT value_key FROM bag_b;
```

với:

```sql
SELECT value_key FROM bag_a
UNION
SELECT value_key FROM bag_b;
```

Câu thứ nhất:

1. Loại bản sao **chỉ trong nhánh A** vì `SELECT DISTINCT`.
2. Giữ mọi bản sao của nhánh B.
3. Dùng `UNION ALL` để ghép hai đầu ra mà **không loại trùng giữa hai nhánh**.

Trên dữ liệu mẫu, A sau `DISTINCT` có 4 hàng (1,2,3,NULL); B có 7 hàng; kết quả `UNION ALL` có **11 hàng**.

Câu thứ hai dùng `UNION` loại bản sao ở **toàn bộ kết quả của hai nhánh** và chỉ còn **5 hàng**.

Việc đặt `DISTINCT` ở một `SELECT` bên trong và việc đặt `ALL`/`DISTINCT` của set operator là **hai lựa chọn ở hai cấp khác nhau**.

### 9.1. ALL không tự thay đổi các phép tổng hợp bên trong

```sql
SELECT customer_id, SUM(amount) AS total
FROM sales_a
GROUP BY customer_id

UNION ALL

SELECT customer_id, SUM(amount) AS total
FROM sales_b
GROUP BY customer_id;
```

Nếu một khách xuất hiện ở cả hai bảng nguồn, kết quả có **hai hàng tổng theo khách** (một cho A, một cho B), không tự cộng chúng thành một tổng. `UNION ALL` chỉ ghép hai tập kết quả đã tổng hợp.

Muốn tổng chung mỗi khách:

```sql
WITH combined AS (
    SELECT customer_id, amount FROM sales_a
    UNION ALL
    SELECT customer_id, amount FROM sales_b
)
SELECT customer_id, SUM(amount) AS total_amount
FROM combined
GROUP BY customer_id;
```

Đây là một mẫu đúng khi **mọi dòng giao dịch của hai nguồn đều cần đóng góp**. Nếu hai nguồn có thể chứa **cùng giao dịch bị sao chép**, cộng như vậy sẽ đếm hai lần; lúc đó cần khóa nghiệp vụ hoặc quy tắc khử trùng ở **cấp giao dịch**, không tự đổi `UNION ALL` thành `UNION` trên danh sách cột không phản ánh chính xác định danh giao dịch.

## 10. Thứ tự ưu tiên toán tử và dấu ngoặc

Khi phối hợp `UNION`, `INTERSECT` và `EXCEPT`, dấu ngoặc có thể thay đổi kết quả. Trong PostgreSQL:

- `INTERSECT` có độ ưu tiên cao hơn `UNION` và `EXCEPT`.
- `UNION` và `EXCEPT` được kết hợp từ trái sang phải nếu không có dấu ngoặc thay đổi cấu trúc.
- Các từ khóa `ALL`/`DISTINCT` thuộc về **toán tử ngay sau hoặc ngay trước** theo đúng cú pháp set operator, không tự áp dụng cho cả câu phức tạp.

### 10.1. Ví dụ kết quả khác nhau theo dấu ngoặc

Với giá trị `1`:

- A có 3 bản sao.
- B có 2 bản sao.

Xét một câu viết không có dấu ngoặc:

```sql
SELECT value_key FROM bag_a WHERE value_key = 1
UNION ALL
SELECT value_key FROM bag_b WHERE value_key = 1
INTERSECT
SELECT value_key FROM bag_b WHERE value_key = 1;
```

Trong PostgreSQL, `INTERSECT` ưu tiên hơn, nên ý nghĩa là:

```text
A(1)
UNION ALL
(
    B(1) INTERSECT B(1)
)
```

`B(1) INTERSECT B(1)` theo mặc định `DISTINCT` chỉ còn **một** hàng `1`. Vì vậy kết quả chung có **3 + 1 = 4 hàng `1`**.

Nếu cố ý muốn giao sau khi ghép A và B, cần nhóm vế trái:

```sql
WITH combined AS (
    SELECT value_key FROM bag_a WHERE value_key = 1
    UNION ALL
    SELECT value_key FROM bag_b WHERE value_key = 1
),
common AS (
    SELECT value_key FROM combined
    INTERSECT
    SELECT value_key FROM bag_b WHERE value_key = 1
)
SELECT value_key
FROM common;
```

Kết quả chỉ có **một** hàng `1`: phép `INTERSECT` mặc định loại bản sao của giao.

### 10.2. CTE giúp nhìn thấy các cấp rõ hơn

Với truy vấn nhiều phép toán, đặt tên từng kết quả trung gian:

```sql
WITH
a_values AS (
    SELECT value_key FROM bag_a
),
b_values AS (
    SELECT value_key FROM bag_b
),
common_with_duplicates AS (
    SELECT value_key FROM a_values
    INTERSECT ALL
    SELECT value_key FROM b_values
)
SELECT value_key, COUNT(*) AS occurrences
FROM common_with_duplicates
GROUP BY value_key
ORDER BY value_key NULLS LAST;
```

CTE truyền đạt ý nghĩa tốt hơn một chuỗi dài `UNION`/`INTERSECT`/`EXCEPT` không có dấu ngoặc, nhất là khi một toán tử có `ALL` còn toán tử khác mặc định `DISTINCT`.

### 10.3. EXCEPT ALL không giao hoán và không kết hợp tùy tiện

Ta đã biết:

```text
A EXCEPT ALL B ≠ B EXCEPT ALL A
```

Nó cũng không có tính kết hợp tổng quát:

```text
(A EXCEPT ALL B) EXCEPT ALL C
có thể khác
A EXCEPT ALL (B EXCEPT ALL C)
```

Ví dụ chỉ xét một giá trị `v` với số lần A=2, B=2, C=1:

```text
(A - B) - C = max(max(2-2,0)-1,0) = 0
A - (B - C) = max(2-max(2-1,0),0) = 1
```

Đừng tự đổi vị trí dấu ngoặc của `EXCEPT ALL` trong một truy vấn đối soát mà không xét lại số bản sao.

## 11. ORDER BY và LIMIT áp dụng cho kết quả nào?

Các phép toán tập hợp tạo một kết quả logic; thứ tự hàng cuối cùng **không được bảo đảm** nếu không có `ORDER BY` ở cấp mong muốn.

### 11.1. ORDER BY ở cuối sắp xếp toàn bộ kết quả

```sql
SELECT value_key FROM bag_a
UNION ALL
SELECT value_key FROM bag_b
ORDER BY value_key DESC NULLS LAST;
```

`ORDER BY` ở cuối áp dụng cho **kết quả hợp nhất**, không chỉ bảng `bag_b`. Đừng giả định `UNION ALL` luôn đưa tất cả hàng A trước B theo thứ tự chèn. Cơ chế thực thi có thể thay đổi cách các hàng được phát ra.

Với PostgreSQL, `ORDER BY` đặt trực tiếp ở cuối một biểu thức set operator thường phải tham chiếu **tên cột đầu ra** hoặc vị trí cột, thay vì biểu thức tính mới không có trong danh sách chọn. Nếu cần sắp theo biểu thức phức tạp, bọc kết quả set trong một subquery:

```sql
SELECT value_key
FROM (
    SELECT value_key FROM bag_a
    UNION ALL
    SELECT value_key FROM bag_b
) AS u
ORDER BY
    CASE WHEN value_key IS NULL THEN 1 ELSE 0 END,
    value_key;
```

### 11.2. LIMIT cuối cùng giới hạn toàn bộ kết quả

```sql
SELECT value_key FROM bag_a
UNION ALL
SELECT value_key FROM bag_b
ORDER BY value_key NULLS LAST
LIMIT 5;
```

Truy vấn này lấy **tối đa 5 hàng của kết quả hợp nhất**. Nó không có nghĩa “lấy 5 hàng từ A và 5 hàng từ B”.

Nếu cần lấy một số hàng riêng ở mỗi nguồn trước khi ghép, bọc từng nhánh:

```sql
SELECT value_key
FROM (
    SELECT value_key
    FROM bag_a
    ORDER BY row_id
    LIMIT 3
) AS first_three_a

UNION ALL

SELECT value_key
FROM (
    SELECT value_key
    FROM bag_b
    ORDER BY row_id
    LIMIT 2
) AS first_two_b;
```

Sau đó, nếu cần một thứ tự cuối cùng rõ ràng, phải thêm `ORDER BY` cho **biểu thức set ngoài cùng** hoặc bọc nó trong truy vấn ngoài. Việc `ORDER BY` ở mỗi subquery giới hạn nhánh không tự bảo đảm thứ tự trình bày cuối cùng.

### 11.3. Không dùng LIMIT để “thử nhanh” ngữ nghĩa bản sao

Nếu chưa biết thứ tự, `LIMIT 10` có thể cho cảm giác các bản sao xuất hiện ít hoặc nhiều hơn thực tế vì ta chỉ xem một phần kết quả. Khi học set operator, hãy:

1. Đếm đầu vào theo giá trị.
2. Dự đoán bội số theo công thức.
3. Chạy toàn bộ biểu thức set.
4. Đếm `COUNT(*)` và `GROUP BY` trên kết quả.
5. Chỉ thêm `LIMIT` khi đã hiểu yêu cầu hiển thị.

## 12. Ví dụ nghiệp vụ: ghép và đối soát hai nguồn giao dịch

Giả sử một hệ thống nhận hai tệp chứa danh sách giao dịch theo **mã tham chiếu**. Cùng một mã có thể xuất hiện nhiều lần do nhiều sự kiện hợp lệ, hoặc do nhập trùng.

Chúng ta tạo một bộ dữ liệu riêng, không lẫn với `bag_a`/`bag_b`:

```sql
CREATE TEMP TABLE import_a (
    source_row INTEGER PRIMARY KEY,
    reference_code TEXT NOT NULL
);

CREATE TEMP TABLE import_b (
    source_row INTEGER PRIMARY KEY,
    reference_code TEXT NOT NULL
);

INSERT INTO import_a VALUES
    (1, 'INV-A'),
    (2, 'INV-A'),
    (3, 'INV-A'),
    (4, 'INV-B'),
    (5, 'INV-C');

INSERT INTO import_b VALUES
    (1, 'INV-A'),
    (2, 'INV-A'),
    (3, 'INV-B'),
    (4, 'INV-B'),
    (5, 'INV-D');
```

Đếm đầu vào:

| Mã | Số lần ở A | Số lần ở B |
| --- | ---: | ---: |
| INV-A | 3 | 2 |
| INV-B | 1 | 2 |
| INV-C | 1 | 0 |
| INV-D | 0 | 1 |

### 12.1. Mã có ở cả hai tệp

```sql
SELECT reference_code FROM import_a
INTERSECT
SELECT reference_code FROM import_b
ORDER BY reference_code;
```

Kết quả chỉ có **INV-A** và **INV-B**.

Nếu hỏi **số hàng có thể đối chiếu theo từng mã**:

```sql
WITH matched AS (
    SELECT reference_code FROM import_a
    INTERSECT ALL
    SELECT reference_code FROM import_b
)
SELECT reference_code, COUNT(*) AS matched_occurrences
FROM matched
GROUP BY reference_code
ORDER BY reference_code;
```

Kết quả:

| Mã | `matched_occurrences` |
| --- | ---: |
| INV-A | 2 |
| INV-B | 1 |

### 12.2. Các bản sao còn thiếu ở B

```sql
WITH leftover AS (
    SELECT reference_code FROM import_a
    EXCEPT ALL
    SELECT reference_code FROM import_b
)
SELECT reference_code, COUNT(*) AS missing_in_b
FROM leftover
GROUP BY reference_code
ORDER BY reference_code;
```

Kết quả:

| Mã | Số lần A nhiều hơn B |
| --- | ---: |
| INV-A | 1 |
| INV-C | 1 |

Đây là một **đối soát theo số lần xuất hiện**. Trong khi đó, `EXCEPT` thông thường chỉ cho `INV-C`, vì `INV-A` vẫn có mặt trong B và do vậy không phải một mã hoàn toàn vắng mặt.

### 12.3. Các bản sao dư ở B

```sql
WITH leftover AS (
    SELECT reference_code FROM import_b
    EXCEPT ALL
    SELECT reference_code FROM import_a
)
SELECT reference_code, COUNT(*) AS extra_in_b
FROM leftover
GROUP BY reference_code
ORDER BY reference_code;
```

Kết quả:

| Mã | Số lần B nhiều hơn A |
| --- | ---: |
| INV-B | 1 |
| INV-D | 1 |

Hai chiều đối soát giúp phân biệt **A đang thiếu ở B** và **B có thêm so với A**. Nếu chỉ chạy một chiều `EXCEPT ALL`, thông tin chênh lệch chiều kia sẽ bị bỏ sót.

### 12.4. Số lần xuất hiện không tự thay thế khóa giao dịch

Giả sử `INV-A` đại diện cho **một hóa đơn duy nhất**, còn ba dòng A thực chất là ba lần gửi lại do lỗi mạng. Khi đó cần chuẩn hóa/deduplicate theo **khóa hóa đơn** trước khi coi số lần xuất hiện là số giao dịch.

Ngược lại, nếu mỗi lần xuất hiện của `INV-A` đại diện cho một sự kiện riêng cần đối soát, `EXCEPT ALL` có thể diễn đạt phần chênh lệch số lượng đúng hơn `EXCEPT`.

Vì vậy, trước khi chọn `ALL`, phải trả lời:

> “Hai hàng giống nhau là **hai sự kiện hợp lệ**, hay là **một sự kiện bị lặp không mong muốn**?”

Không có toán tử nào tự biết câu trả lời nghiệp vụ.

## 13. Khi không hỗ trợ INTERSECT ALL hoặc EXCEPT ALL, mô phỏng thế nào?

Một số hệ quản trị hỗ trợ `UNION ALL` nhưng không hỗ trợ đầy đủ `INTERSECT ALL` và `EXCEPT ALL` trong phiên bản đang chạy. Có thể mô phỏng dựa trên **đánh số từng bản sao theo giá trị**.

Ý tưởng:

1. Chia mỗi bảng thành các nhóm theo giá trị cần so sánh.
2. Đánh số bản sao của từng giá trị bằng `ROW_NUMBER()`: 1, 2, 3, ...
3. Ghép từng bản sao phía A với bản sao **cùng giá trị và cùng số thứ tự** phía B.
4. Những bản sao được ghép chính là giao đa tập; những bản sao A không ghép được chính là hiệu đa tập A trừ B.

### 13.1. Đánh số các bản sao

```sql
WITH
a_numbered AS (
    SELECT
        row_id,
        value_key,
        ROW_NUMBER() OVER (
            PARTITION BY value_key
            ORDER BY row_id
        ) AS occurrence_no
    FROM bag_a
),
b_numbered AS (
    SELECT
        row_id,
        value_key,
        ROW_NUMBER() OVER (
            PARTITION BY value_key
            ORDER BY row_id
        ) AS occurrence_no
    FROM bag_b
)
SELECT *
FROM a_numbered
ORDER BY value_key NULLS LAST, occurrence_no;
```

Với `value_key = 1`, A được đánh số `1,2,3`; B được đánh số `1,2`. Với `value_key = NULL`, A có `1,2`; B có `1`.

Thứ tự `row_id` ở đây chỉ dùng để **chọn một cách đánh số ổn định cho các bản sao tương đương**. Với mô phỏng phép toán chỉ trả `value_key`, bản sao nào mang số 1 hoặc 2 không ảnh hưởng kết quả đa tập. Nếu cần biết chính xác **dòng nguồn nào còn lại**, nghiệp vụ phải quy định cách ghép theo thứ tự, khóa hoặc thuộc tính khác, không chỉ theo giá trị trùng.

### 13.2. Mô phỏng INTERSECT ALL bằng INNER JOIN trên lần xuất hiện

```sql
WITH
a_numbered AS (
    SELECT
        value_key,
        ROW_NUMBER() OVER (
            PARTITION BY value_key ORDER BY row_id
        ) AS occurrence_no
    FROM bag_a
),
b_numbered AS (
    SELECT
        value_key,
        ROW_NUMBER() OVER (
            PARTITION BY value_key ORDER BY row_id
        ) AS occurrence_no
    FROM bag_b
)
SELECT a.value_key
FROM a_numbered AS a
JOIN b_numbered AS b
    ON a.occurrence_no = b.occurrence_no
   AND (
       a.value_key = b.value_key
       OR (a.value_key IS NULL AND b.value_key IS NULL)
   )
ORDER BY a.value_key NULLS LAST;
```

Kết quả: hai hàng `1`, hai hàng `2` và một hàng `NULL` — tương đương `INTERSECT ALL` ở ví dụ.

Tại sao điều kiện `NULL` được viết tường minh? Vì `a.value_key = b.value_key` không khớp khi cả hai `NULL`. Trong PostgreSQL có thể viết gọn:

```sql
AND a.value_key IS NOT DISTINCT FROM b.value_key
```

Đó là cách so sánh hai giá trị **không khác nhau, kể cả cùng `NULL`**. Cú pháp NULL-safe cần được điều chỉnh phù hợp DBMS khi chuyển hệ.

### 13.3. Mô phỏng EXCEPT ALL bằng LEFT JOIN và giữ bản sao chưa ghép

```sql
WITH
a_numbered AS (
    SELECT
        value_key,
        ROW_NUMBER() OVER (
            PARTITION BY value_key ORDER BY row_id
        ) AS occurrence_no
    FROM bag_a
),
b_numbered AS (
    SELECT
        value_key,
        ROW_NUMBER() OVER (
            PARTITION BY value_key ORDER BY row_id
        ) AS occurrence_no
    FROM bag_b
)
SELECT a.value_key
FROM a_numbered AS a
LEFT JOIN b_numbered AS b
    ON a.occurrence_no = b.occurrence_no
   AND (
       a.value_key = b.value_key
       OR (a.value_key IS NULL AND b.value_key IS NULL)
   )
WHERE b.occurrence_no IS NULL
ORDER BY a.value_key NULLS LAST;
```

Kết quả: `1`, `3` và `NULL` — tương đương `A EXCEPT ALL B`.

Điểm cần đọc:

- Hai bản sao `1` ở A có `occurrence_no = 1, 2` được ghép với B và bị loại.
- Bản sao `1` thứ ba ở A có `occurrence_no = 3` không tìm thấy phía B, nên được giữ.
- B có ba bản sao `2`; A chỉ có hai nên cả hai bản sao A đều ghép được, không còn `2` nào.
- `3` chỉ có ở A nên được giữ.
- Với `NULL`, một trong hai bản sao A được ghép với bản sao B; bản sao còn lại được giữ.

Vì `ROW_NUMBER()` luôn sinh số thứ tự không `NULL`, điều kiện `WHERE b.occurrence_no IS NULL` là dấu hiệu **không có hàng phải khớp**, tránh nhầm với `b.value_key IS NULL` vốn có thể là giá trị dữ liệu thật.

### 13.4. Lợi ích và giới hạn của cách mô phỏng

Ưu điểm:

- Áp dụng trên DBMS có window function và cú pháp JOIN thông thường.
- Biểu diễn rõ việc ghép bản sao một-một.
- Cho phép giữ metadata `row_id` của bản sao A khi cần, **sau khi quy định rõ cách ghép**.

Giới hạn:

- Có thể tốn sắp xếp/phân vùng để tính `ROW_NUMBER`.
- Với nhiều cột, phải so sánh **toàn bộ bộ giá trị**, bao gồm quy tắc `NULL` cho từng cột.
- Nếu kiểu dữ liệu có collation hoặc quy tắc so sánh đặc biệt, cách đánh số, nhóm và điều kiện ghép phải cùng ngữ nghĩa với phép set operator mong muốn.
- Không nên coi đây luôn là cách thay thế có cùng hiệu năng hay mọi chi tiết ngữ nghĩa với phép `ALL` gốc ở từng engine.

Khi DBMS hỗ trợ `EXCEPT ALL`/`INTERSECT ALL` trực tiếp và thỏa nhu cầu, cú pháp gốc thường **rõ nghĩa hơn**.

## 14. Mô phỏng bằng bảng đếm: công thức ở cấp bội số

Một cách khác là **đếm trước**, sau đó tính công thức min/max. Đây là cách dễ kiểm chứng bằng mắt, hữu ích cho báo cáo chênh lệch.

```sql
WITH
count_a AS (
    SELECT value_key, COUNT(*) AS count_a
    FROM bag_a
    GROUP BY value_key
),
count_b AS (
    SELECT value_key, COUNT(*) AS count_b
    FROM bag_b
    GROUP BY value_key
),
counts AS (
    SELECT
        a.value_key,
        a.count_a,
        COALESCE(b.count_b, 0) AS count_b
    FROM count_a AS a
    LEFT JOIN count_b AS b
      ON a.value_key IS NOT DISTINCT FROM b.value_key
)
SELECT
    value_key,
    count_a,
    count_b,
    LEAST(count_a, count_b) AS intersect_all_count,
    GREATEST(count_a - count_b, 0) AS except_all_count
FROM counts
ORDER BY value_key NULLS LAST;
```

Kết quả chỉ liệt kê các giá trị có trong A:

| Giá trị | A | B | `min(A,B)` | `max(A-B,0)` |
| --- | ---: | ---: | ---: | ---: |
| 1 | 3 | 2 | 2 | 1 |
| 2 | 2 | 3 | 2 | 0 |
| 3 | 1 | 0 | 0 | 1 |
| `NULL` | 2 | 1 | 1 | 1 |

Giá trị `4` không có ở A nên không xuất hiện trong `count_a`; nó không ảnh hưởng đến `A EXCEPT ALL B` hay `A INTERSECT ALL B`. Nếu muốn báo cáo **mọi giá trị của A lẫn B và cả chênh lệch hai chiều**, có thể dùng `FULL OUTER JOIN` trên hai bảng đếm với phép so sánh NULL-safe.

### 14.1. Đếm chênh lệch khác với trả lại các hàng

Truy vấn trên trả **mỗi giá trị một dòng kèm số bản sao**. Nó chưa trả lại các hàng lặp như `EXCEPT ALL`. Nếu cần kết quả đa tập, phải tái tạo số hàng theo `except_all_count`, ví dụ dùng `generate_series` trong PostgreSQL:

```sql
WITH
count_a AS (
    SELECT value_key, COUNT(*) AS count_a
    FROM bag_a GROUP BY value_key
),
count_b AS (
    SELECT value_key, COUNT(*) AS count_b
    FROM bag_b GROUP BY value_key
),
remaining AS (
    SELECT
        a.value_key,
        GREATEST(a.count_a - COALESCE(b.count_b, 0), 0)
            AS copies_left
    FROM count_a AS a
    LEFT JOIN count_b AS b
      ON a.value_key IS NOT DISTINCT FROM b.value_key
)
SELECT r.value_key
FROM remaining AS r
CROSS JOIN LATERAL generate_series(1::bigint, r.copies_left) AS g(n)
ORDER BY r.value_key NULLS LAST;
```

Đây là minh họa PostgreSQL. Với kết quả có hàng triệu bản sao, việc **mở rộng** thành từng hàng vật lý có thể tốn tài nguyên; nếu mục đích chỉ là báo cáo số lượng thiếu/dư, giữ bảng `value_key, copies_left` là đủ và thường hữu ích hơn.

## 15. Khác biệt giữa tập rỗng và tập có bản sao

Khi một phía không có hàng, các biến thể `ALL` vẫn thể hiện khác biệt:

Giả sử A có `[1,1,2]` và E là tập rỗng.

| Phép toán | Kết quả |
| --- | --- |
| `A UNION ALL E` | `[1,1,2]` |
| `A UNION E` | `[1,2]` |
| `A INTERSECT ALL E` | Rỗng |
| `A INTERSECT E` | Rỗng |
| `A EXCEPT ALL E` | `[1,1,2]` |
| `A EXCEPT E` | `[1,2]` |

**Điểm bất ngờ:** `UNION` và `EXCEPT` mặc định `DISTINCT` vẫn loại bản sao **nội bộ của A**, kể cả khi vế còn lại rỗng. Không thể kết luận rằng “vế phải rỗng thì `EXCEPT` giữ nguyên mọi bản sao của A”; điều đó chỉ đúng với `EXCEPT ALL`.

Ví dụ PostgreSQL:

```sql
WITH empty_values(value_key) AS (
    SELECT NULL::integer WHERE FALSE
)
SELECT value_key FROM bag_a
EXCEPT ALL
SELECT value_key FROM empty_values;
```

Kết quả có đúng **8 hàng**, bảo toàn bội số của bag A.

Nếu đổi thành `EXCEPT`, kết quả còn **4 hàng khác nhau**: `1,2,3,NULL`.

## 16. ALL khi kết hợp hơn hai nguồn

Bài toán thường có ba tệp, ba bảng hoặc ba kỳ dữ liệu.

### 16.1. Ghép ba nguồn bằng UNION ALL

```sql
WITH
source_a(value_key) AS (
    VALUES (1), (1), (2)
),
source_b(value_key) AS (
    VALUES (1), (3)
),
source_c(value_key) AS (
    VALUES (2), (2), (4)
)
SELECT value_key FROM source_a
UNION ALL
SELECT value_key FROM source_b
UNION ALL
SELECT value_key FROM source_c
ORDER BY value_key;
```

Kết quả:

```text
1, 1, 1, 2, 2, 2, 3, 4
```

Bội số của từng giá trị bằng **tổng bội số của các nguồn**. Nếu mọi nguồn thực sự độc lập, `UNION ALL` rất tự nhiên. Nếu các nguồn có thể gửi lại cùng sự kiện, phải có chiến lược đối soát định danh sự kiện.

### 16.2. Giao nhiều nguồn

Với ba đa tập A, B, C, số bản sao chung của một giá trị là:

\[
m_{\mathrm{INTERSECT\ ALL}}(v)
=\min(m_A(v),m_B(v),m_C(v))
\]

Có thể viết các phép `INTERSECT ALL` nối tiếp trên hệ hỗ trợ; vẫn cần dấu ngoặc khi câu truy vấn có thêm toán tử khác để đảm bảo đúng ý nghĩa.

### 16.3. Trừ nhiều nguồn cần xác định hướng

Nếu mục tiêu là “bản sao A còn lại sau khi trừ cả B và C”, có thể cần:

```text
(A EXCEPT ALL B) EXCEPT ALL C
```

Về bội số, tương đương:

\[
\max(m_A(v)-m_B(v)-m_C(v),0)
\]

Nhưng **không tương đương tổng quát** với:

```text
A EXCEPT ALL (B EXCEPT ALL C)
```

Vì thế, trong bài toán đối soát nhiều nguồn, nên mô tả rõ *trừ dần những nguồn nào khỏi nguồn nào* trước khi ghép toán tử.

## 17. Vấn đề hiệu năng: ALL có phải lúc nào cũng nhanh hơn DISTINCT?

`UNION ALL` thường có lợi thế khi chỉ cần ghép kết quả vì không cần công việc **loại bản sao toàn cục** như `UNION DISTINCT`. Tuy nhiên, không nên kết luận mọi biểu thức có `ALL` luôn nhanh hơn mọi biểu thức `DISTINCT`.

### 17.1. UNION ALL và UNION DISTINCT

Về mặt logic:

- `UNION ALL` ghép đầu ra và giữ tất cả hàng.
- `UNION DISTINCT` phải bảo đảm các hàng trùng chỉ xuất hiện một lần, nên thường cần một cơ chế như sort/unique hoặc hash aggregate, tùy optimizer.

Ví dụ:

```sql
EXPLAIN
SELECT value_key FROM bag_a
UNION ALL
SELECT value_key FROM bag_b;
```

và:

```sql
EXPLAIN
SELECT value_key FROM bag_a
UNION
SELECT value_key FROM bag_b;
```

PostgreSQL có thể hiển thị kế hoạch khác nhau cho hai câu. Trên dữ liệu vài hàng, khác biệt thời gian có thể rất nhỏ; trên tập lớn, chi phí loại trùng có thể đáng kể.

### 17.2. INTERSECT ALL và EXCEPT ALL vẫn phải quản lý bội số

`INTERSECT ALL` không chỉ ghép hàng; nó phải xác định **giá trị nào xuất hiện ở cả hai phía và số lần bao nhiêu**. `EXCEPT ALL` cũng phải tính chênh lệch bội số. Vì vậy, chúng có thể cần hash/sort, đếm hoặc cấu trúc trung gian.

Không thể suy ra rằng thêm `ALL` luôn loại bỏ toàn bộ công việc so sánh hoặc phân loại hàng. Lợi ích thực tế phụ thuộc số bản sao, kích thước và kiểu dữ liệu, kế hoạch và tài nguyên.

### 17.3. Kiểm tra kế hoạch với EXPLAIN

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT value_key FROM bag_a
EXCEPT ALL
SELECT value_key FROM bag_b;
```

Trong PostgreSQL, `EXPLAIN ANALYZE` thực sự chạy truy vấn để đo thời gian và số hàng. Với `SELECT` đọc bảng tạm như ví dụ, điều đó phù hợp cho thực hành; với câu lệnh thay đổi dữ liệu, không dùng `EXPLAIN ANALYZE` tùy tiện trên production.

Các yếu tố cần quan sát: số hàng đầu vào, số hàng sau phép toán, sort/hash, bộ nhớ, I/O và thời gian. Đừng đổi `EXCEPT ALL` thành `EXCEPT` chỉ vì thấy một kế hoạch nhanh hơn — như đã chứng minh, hai phép có thể trả **kết quả nghiệp vụ khác nhau**.

### 17.4. Tránh mở rộng bản sao khi chỉ cần bảng số lượng

Trong hệ thống đối soát, thay vì trả hàng triệu dòng từ `EXCEPT ALL`, đôi khi báo cáo **mỗi mã và số lần dư/thiếu** đã đủ:

```text
reference_code | count_a | count_b | missing_in_b | extra_in_b
---------------+---------+---------+--------------+-----------
INV-A          | 3       | 2       | 1            | 0
INV-B          | 1       | 2       | 0            | 1
INV-C          | 1       | 0       | 1            | 0
INV-D          | 0       | 1       | 0            | 1
```

Việc giữ bội số trong một bảng tổng hợp có thể dễ truyền qua API, dễ lưu log và ít tốn dung lượng hơn việc tạo một hàng mới cho mỗi bản sao còn lại. Chỉ “nở” kết quả khi nghiệp vụ thực sự yêu cầu từng dòng riêng.

## 18. Mức hỗ trợ của các DBMS: không mặc định có mọi ALL

Cần phân biệt tính phổ biến của `UNION ALL` với tình trạng hỗ trợ `INTERSECT ALL`/`EXCEPT ALL`.

| Hệ quản trị | `UNION ALL` | `INTERSECT ALL` / `EXCEPT ALL` | Ghi chú |
| --- | --- | --- | --- |
| **PostgreSQL** | Có | Có | Hỗ trợ trực tiếp cả ba biến thể `ALL`; ví dụ của bài dùng PostgreSQL |
| **SQL Server** | Có | Không theo cú pháp T-SQL thông dụng | `INTERSECT`/`EXCEPT` hoạt động theo ngữ nghĩa loại trùng; có thể mô phỏng `ALL` bằng window function |
| **SQLite** | Có | Không hỗ trợ trực tiếp trong cú pháp set operator thông dụng | `UNION ALL` có, `INTERSECT`/`EXCEPT` loại trùng |
| **MySQL** | Có | Phụ thuộc phiên bản | Dòng MySQL 8.0.31+ bổ sung `INTERSECT`/`EXCEPT`; kiểm tra hỗ trợ từng biến thể `ALL` trên phiên bản thực tế |
| **Oracle Database** | Có | Phụ thuộc phiên bản/cú pháp | Nhiều phiên bản dùng `MINUS` cho hiệu tập; các phiên bản mới có thêm biến thể `ALL` và tên toán tử tương ứng |
| **Các hệ phân tích khác** | Thường có | Rất khác nhau | Xem tài liệu của đúng engine/phiên bản, không suy từ SQL chuẩn |

Ví dụ, một câu PostgreSQL:

```sql
SELECT value_key FROM bag_a
EXCEPT ALL
SELECT value_key FROM bag_b;
```

có thể không chạy nguyên dạng trên SQL Server hoặc SQLite. Khi ấy cần lựa chọn: **mô phỏng bội số** bằng `ROW_NUMBER`/bảng đếm như phần 13–14, hoặc **đổi yêu cầu** sang `EXCEPT DISTINCT` nếu nghiệp vụ thực sự chỉ quan tâm những giá trị vắng mặt hoàn toàn.

Không được thay `EXCEPT ALL` bằng `EXCEPT` rồi coi kết quả là tương đương chỉ để câu truy vấn tương thích với hệ quản trị.

### 18.1. Từ khóa khác nhau không đồng nghĩa ngữ nghĩa khác nhau

Trong Oracle truyền thống, `MINUS` thường được dùng với ý nghĩa hiệu tập phân biệt, tương ứng `EXCEPT DISTINCT` trong nhiều hệ khác. Phiên bản và cú pháp mở rộng có thể cung cấp `MINUS ALL`/`EXCEPT ALL`, nhưng cần kiểm tra tài liệu của phiên bản hiện có.

Tên toán tử chỉ là một phần; cần xác định **ngữ nghĩa bản sao**, kiểu dữ liệu được hỗ trợ và thứ tự ưu tiên khi phối hợp với phép khác.

## 19. Các lỗi thường gặp và hướng xử lý

| Lỗi hoặc giả định dễ gặp | Hậu quả | Cách suy luận đúng |
| --- | --- | --- |
| “`UNION` chỉ ghép hai bảng.” | Mất các hàng có bộ giá trị trùng | `UNION` mặc định loại bản sao; dùng `UNION ALL` khi cần giữ tất cả |
| “`INTERSECT ALL` giống JOIN.” | Dự đoán số hàng thành tích bội số hai phía | `INTERSECT ALL` dùng **min**, JOIN có thể nhân **m_A × m_B** |
| “`EXCEPT ALL` loại mọi giá trị có trong B.” | Bỏ sót bản sao dư ở A | `EXCEPT ALL` trừ bội số bằng **max(A−B,0)** |
| “`EXCEPT` và `EXCEPT ALL` chỉ khác hiệu năng.” | Kết quả đối soát khác nhau | Phân biệt hiệu tập với trừ bản sao |
| “`NOT EXISTS` là EXCEPT ALL.” | Mất mọi hàng A có ít nhất một khớp B | Anti join kiểm tra tồn tại, không trừ số lần |
| “NULL không thể trùng NULL.” | Dự đoán sai số bản sao ở set operator | Trong phép nhận diện hàng trùng, các vị trí `NULL` được xử lý như không khác nhau |
| “COUNT(col) đếm toàn bộ bản sao.” | Bỏ các hàng có `col IS NULL` | Dùng `COUNT(*)` khi đếm hàng |
| “SELECT DISTINCT ở A làm UNION ALL trở thành UNION.” | Vẫn còn bản sao từ B và trùng giữa hai nhánh | `DISTINCT` ở nhánh chỉ ảnh hưởng nhánh đó |
| “Chỉ cần giống mã sản phẩm là hai hàng trùng.” | Các cột khác trong SELECT vẫn có thể khác | Xét toàn bộ cột của hàng đầu ra |
| “Có ALL thì kết quả theo thứ tự A rồi B.” | Dựa vào thứ tự không được bảo đảm | Dùng `ORDER BY` khi cần |
| “LIMIT cuối cùng giới hạn từng nhánh.” | Thiếu hoặc sai số hàng từng nguồn | Bọc từng nhánh nếu muốn LIMIT riêng |
| “EXCEPT ALL hỗ trợ trên mọi DBMS.” | Lỗi cú pháp hoặc đổi ngữ nghĩa tùy tiện | Kiểm tra engine/phiên bản; mô phỏng nếu cần |
| “UNION DISTINCT luôn tốt vì loại dữ liệu trùng.” | Có thể xóa các giao dịch hợp lệ giống nhau | Xác định grain/khóa nghiệp vụ trước khi deduplicate |
| “Cộng mọi số bản sao từ nhiều cấp tổng hợp là đúng.” | Có thể đếm chồng lấp | Chọn một cấp phân hoạch hoặc tổng nguồn rõ ràng |

## 20. Bài tập thực hành có đáp án

Các bài dưới đây dùng `bag_a` và `bag_b` ở phần 2, trừ khi ghi rõ dùng bảng `import_a`/`import_b`.

### Bài 1 — UNION DISTINCT có bao nhiêu hàng?

```sql
SELECT value_key FROM bag_a
UNION
SELECT value_key FROM bag_b;
```

**Đáp án:** **5 hàng** chứa `1, 2, 3, 4, NULL`. Mỗi giá trị chỉ xuất hiện một lần trong kết quả.

### Bài 2 — UNION ALL có bao nhiêu hàng và bao nhiêu NULL?

```sql
SELECT value_key FROM bag_a
UNION ALL
SELECT value_key FROM bag_b;
```

**Đáp án:** **15 hàng**, trong đó có **3 hàng `NULL`**; bội số của `1` là 5 và `2` là 5.

### Bài 3 — INTERSECT khác INTERSECT ALL thế nào?

```sql
SELECT value_key FROM bag_a
INTERSECT
SELECT value_key FROM bag_b;
```

và:

```sql
SELECT value_key FROM bag_a
INTERSECT ALL
SELECT value_key FROM bag_b;
```

**Đáp án:** `INTERSECT` trả **3 hàng**: `1, 2, NULL`. `INTERSECT ALL` trả **5 hàng**: hai `1`, hai `2`, một `NULL`.

### Bài 4 — EXCEPT A trừ B có giữ số 1 không?

```sql
SELECT value_key FROM bag_a
EXCEPT
SELECT value_key FROM bag_b;
```

**Đáp án:** Không. `EXCEPT` mặc định `DISTINCT` loại toàn bộ giá trị `1` vì B có `1`. Kết quả chỉ có **3**.

### Bài 5 — EXCEPT ALL A trừ B còn lại những gì?

```sql
SELECT value_key FROM bag_a
EXCEPT ALL
SELECT value_key FROM bag_b;
```

**Đáp án:** `[1, 3, NULL]`, mỗi giá trị xuất hiện một lần. Tổng **3 hàng**.

### Bài 6 — Đảo vế của EXCEPT ALL

```sql
SELECT value_key FROM bag_b
EXCEPT ALL
SELECT value_key FROM bag_a;
```

**Đáp án:** `[2, 4]`, tổng **2 hàng**. `EXCEPT ALL` không giao hoán.

### Bài 7 — Nếu cả hai phía đều có rất nhiều bản sao?

Giả sử A có 8 bản sao `'X'` và B có 5 bản sao `'X'`. Hãy dự đoán bội số của `'X'` trong sáu biến thể.

| Phép | Số bản sao `X` |
| --- | ---: |
| `UNION ALL` | 13 |
| `UNION` | 1 |
| `INTERSECT ALL` | 5 |
| `INTERSECT` | 1 |
| `A EXCEPT ALL B` | 3 |
| `A EXCEPT B` | 0 |

**Giải thích:** Lần lượt áp dụng tổng, điều kiện tồn tại và `min/max` từ bảng công thức ở phần 3.

### Bài 8 — COUNT(DISTINCT) với NULL

```sql
SELECT COUNT(DISTINCT value_key) FROM bag_a;
```

và:

```sql
SELECT COUNT(*)
FROM (SELECT DISTINCT value_key FROM bag_a) AS d;
```

**Đáp án:** Truy vấn đầu trả **3** vì `COUNT(DISTINCT col)` bỏ qua `NULL`. Truy vấn sau trả **4** vì tập `SELECT DISTINCT value_key` có hàng `NULL`.

### Bài 9 — SELECT DISTINCT trước UNION ALL

```sql
SELECT DISTINCT value_key FROM bag_a
UNION ALL
SELECT value_key FROM bag_b;
```

**Đáp án:** **11 hàng** (A sau distinct có 4 hàng; B có 7 hàng). `UNION ALL` không loại trùng giữa hai nhánh.

### Bài 10 — INTERSECT ALL hay JOIN cho dữ liệu lặp?

A có ba hàng `1`; B có hai hàng `1`. `INNER JOIN` trên phép bằng tạo bao nhiêu cặp, còn `INTERSECT ALL` tạo bao nhiêu hàng `1`?

**Đáp án:** JOIN có thể tạo **6 cặp**, `INTERSECT ALL` tạo **2 hàng**. JOIN nhân số lần khớp; giao đa tập lấy số bản sao chung tối đa.

### Bài 11 — Đối soát hai tệp có mã lặp

Theo bảng `import_a`/`import_b`:

- A: INV-A×3, INV-B×1, INV-C×1.
- B: INV-A×2, INV-B×2, INV-D×1.

Hãy dự đoán kết quả `A EXCEPT ALL B` và `B EXCEPT ALL A`.

**Đáp án:** A trừ B còn `INV-A×1` và `INV-C×1`. B trừ A còn `INV-B×1` và `INV-D×1`.

### Bài 12 — Thiếu ALL thì chuyện gì xảy ra?

Một hệ quản trị chỉ hỗ trợ `EXCEPT` mặc định `DISTINCT`. Nhà phân tích đổi câu `A EXCEPT ALL B` thành `A EXCEPT B` để chạy được. Có bảo toàn đúng đối soát không?

**Đáp án:** Không. Với dữ liệu mẫu, `A EXCEPT ALL B` giữ cả bản sao dư của `1` và `NULL`, trong khi `A EXCEPT B` chỉ giữ `3`. Cần mô phỏng bội số bằng `ROW_NUMBER` hoặc bảng đếm nếu yêu cầu thật sự là trừ số lần xuất hiện.

### Bài 13 — Thêm cột ID vào phép toán

Hai giao dịch khác nhau có cùng `product_code` nhưng `sale_id` khác nhau. So sánh:

```sql
SELECT product_code FROM source_a
UNION
SELECT product_code FROM source_b;
```

với:

```sql
SELECT sale_id, product_code FROM source_a
UNION
SELECT sale_id, product_code FROM source_b;
```

**Đáp án:** Câu đầu loại trùng theo **mã sản phẩm**. Câu sau loại trùng theo **cặp ID giao dịch–mã sản phẩm**, nên có thể giữ nhiều hàng hơn. Các tên bảng ở bài là minh họa, không thuộc bộ dữ liệu tạm đầu bài.

### Bài 14 — Kiểm chứng EXCEPT ALL bằng GROUP BY

Hãy viết truy vấn đếm số bản sao còn lại theo `value_key`.

**Đáp án:**

```sql
WITH diff AS (
    SELECT value_key FROM bag_a
    EXCEPT ALL
    SELECT value_key FROM bag_b
)
SELECT value_key, COUNT(*) AS copies_left
FROM diff
GROUP BY value_key
ORDER BY value_key NULLS LAST;
```

Kết quả: `1 → 1`, `3 → 1`, `NULL → 1`.

### Bài 15 — Tính số bản sao khi vế phải rỗng

Giả sử A = `[1,1,2]`, B = rỗng.

**Đáp án:** `A EXCEPT ALL B = [1,1,2]`; `A EXCEPT B = [1,2]`. `DISTINCT` vẫn loại bản sao trong A dù B không có hàng nào.

### Bài 16 — Kết hợp toán tử có dấu ngoặc

A có ba bản sao `1`, B có hai bản sao `1`. Tính số hàng cho:

```text
A UNION ALL (B INTERSECT B)
```

và:

```text
(A UNION ALL B) INTERSECT B
```

trong đó `INTERSECT` không có `ALL`.

**Đáp án:** Biểu thức đầu có **4** bản sao `1` (A có 3 và `B INTERSECT B` chỉ có 1). Biểu thức sau có **1** bản sao `1` vì phép `INTERSECT` cuối loại trùng. Thứ tự ưu tiên và dấu ngoặc làm thay đổi kết quả.

## 21. Checklist suy luận trước khi dùng ALL

Khi cần ghép, đối chiếu hoặc trừ kết quả SQL, hãy trả lời những câu hỏi sau:

1. **Một hàng kết quả đại diện cho gì?** Một giao dịch, một mã định danh hay một tổ hợp giá trị?
2. **Hàng giống nhau có được phép đại diện cho nhiều sự kiện thật không?** Nếu có, `DISTINCT` có thể xóa dữ liệu có ý nghĩa.
3. **So sánh những cột nào?** Các phép set operator xét toàn bộ cột được chọn, theo từng vị trí tương ứng.
4. **Muốn sự tồn tại hay muốn số lần xuất hiện?** Chỉ có/không có → `DISTINCT`; cần bội số → xem `ALL`.
5. **Phép toán đúng là ghép, lấy chung hay trừ?** `UNION`, `INTERSECT` và `EXCEPT` có mục tiêu khác nhau.
6. **Nếu dùng ALL, áp dụng công thức nào?** `UNION ALL: A+B`; `INTERSECT ALL: min(A,B)`; `EXCEPT ALL: max(A−B,0)`.
7. **Có `NULL` trong dữ liệu không?** Nhận diện bản sao của set operator khác điều kiện `= NULL`; dùng `COUNT(*)` khi đếm.
8. **Thứ tự phép toán và dấu ngoặc đã rõ chưa?** `INTERSECT` có thể được áp dụng trước `UNION`/`EXCEPT`; với `EXCEPT ALL`, dấu ngoặc đặc biệt quan trọng.
9. **Có đang cộng/tổng hợp trước hoặc sau phép set không?** `UNION ALL` của các tổng theo khách không tự cộng thành một hàng trên mỗi khách.
10. **Có cần thứ tự kết quả không?** `ORDER BY` ở cấp cuối; `LIMIT` không thay thế thứ tự.
11. **DBMS và phiên bản có hỗ trợ biến thể cần dùng không?** Nếu không, mô phỏng theo bội số hoặc giải thích thay đổi nghiệp vụ; đừng tự đổi sang `DISTINCT`.
12. **Đã đối chiếu bằng dữ liệu có 0, 1 và nhiều bản sao chưa?** Chọn cả trường hợp A nhiều hơn B, B nhiều hơn A và `NULL`.

Cốt lõi của bài học là **SQL có thể xử lý các hàng như một đa tập, trong đó số lần xuất hiện là một phần của thông tin**. `UNION ALL` giữ tổng số bản sao, `INTERSECT ALL` giữ phần chung theo bội số nhỏ nhất, còn `EXCEPT ALL` giữ phần dư sau khi trừ bội số. Hiểu chính xác điều này giúp bạn tránh làm mất các sự kiện hợp lệ, đối soát chênh lệch đúng số lần và lựa chọn phép toán tập hợp phù hợp với hệ quản trị đang dùng.

