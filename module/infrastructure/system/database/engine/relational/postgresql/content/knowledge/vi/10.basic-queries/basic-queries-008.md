# DISTINCT, DISTINCT ON và lựa chọn hàng đại diện trong PostgreSQL

Khi truy vấn dữ liệu quan hệ, kết quả thường có nhiều hàng trùng nhau ở **một số cột** nhưng vẫn là những bản ghi khác nhau. Ví dụ một khách hàng đặt nhiều đơn hàng, một sản phẩm nằm trong nhiều đơn, hoặc một tài khoản có nhiều lần đăng nhập. Bài toán đặt ra có thể là:

- Lấy **danh sách giá trị không trùng nhau**, chẳng hạn các trạng thái đơn hàng đã xuất hiện.
- Lấy **tổ hợp giá trị duy nhất**, chẳng hạn các cặp thành phố–trạng thái.
- Chọn **đúng một hàng đại diện trong mỗi nhóm**, chẳng hạn đơn mới nhất của từng khách hàng.
- Loại những hàng lặp do phép `JOIN` tạo ra mà không vô tình làm mất thông tin cần dùng.

PostgreSQL hỗ trợ cả **`DISTINCT`** theo chuẩn SQL và **`DISTINCT ON (...)`** là phần mở rộng đặc trưng của PostgreSQL. Chúng có tên gần giống nhau nhưng giải quyết hai bài toán khác nhau:

> **`DISTINCT` loại trùng trên toàn bộ tập biểu thức đang chọn; `DISTINCT ON` giữ một hàng đại diện cho mỗi giá trị hoặc tổ hợp giá trị được nêu trong ngoặc.**

Điểm then chốt của `DISTINCT ON` là **phải xác định thế nào là “hàng tốt nhất” bằng `ORDER BY`**. Nếu chỉ yêu cầu “mỗi khách hàng một hàng” mà không xác định “mới nhất”, “giá trị cao nhất” hoặc quy tắc khác, PostgreSQL không có cơ sở để biết nên giữ hàng nào.

Bài này xây dựng bộ dữ liệu mẫu và đi từng bước từ `DISTINCT` đến `DISTINCT ON`, `ROW_NUMBER()`, `GROUP BY`, cách xử lý `NULL`, tình huống `JOIN` và ảnh hưởng đến chỉ mục, hiệu năng.

## 1. Phân biệt hàng trùng với giá trị trùng

Xét bảng đơn hàng:

| order_id | customer_id | status | total |
| ---: | ---: | --- | ---: |
| 1001 | 1 | paid | 120.00 |
| 1002 | 1 | pending | 80.00 |
| 1003 | 1 | paid | 150.00 |
| 1004 | 2 | paid | 200.00 |

Ở đây:

- Có **bốn đơn hàng khác nhau** vì `order_id` khác nhau.
- Có **hai khách hàng khác nhau** vì `customer_id` chỉ gồm 1 và 2.
- Có **hai trạng thái khác nhau**: `paid` và `pending`.
- Có **ba cặp customer_id–status khác nhau**: (1, paid), (1, pending), (2, paid).

Do đó, “loại trùng” luôn cần trả lời câu hỏi **trùng theo những cột nào?**

~~~mermaid
flowchart TD
    A["Một truy vấn trả nhiều hàng"] --> B{"Mục tiêu thực sự?"}
    B -->|"Danh sách giá trị/tổ hợp duy nhất"| C["SELECT DISTINCT"]
    B -->|"Một hàng có đủ chi tiết trong mỗi nhóm"| D["DISTINCT ON + ORDER BY"]
    B -->|"Top N hoặc tính thứ hạng mỗi nhóm"| E["ROW_NUMBER / RANK"]
    B -->|"Số lượng, tổng, MAX, MIN theo nhóm"| F["GROUP BY + aggregate"]
    B -->|"Hàng lặp bất thường sau JOIN"| G["Xem lại khóa và điều kiện JOIN"]
~~~

**`DISTINCT` không tự phân biệt đâu là trùng dữ liệu xấu và đâu là nhiều bản ghi hợp lệ.** Hai đơn hàng cùng khách hàng hoàn toàn có thể là hai đơn khác nhau; việc chỉ lấy `DISTINCT customer_id` sẽ làm mất thông tin đơn hàng nếu bạn cần báo cáo từng đơn.

## 2. Chuẩn bị dữ liệu thực hành có thể tái lập

Để các ví dụ cho kết quả dự đoán được, dùng một database **riêng dành cho lab**, chẳng hạn `pg_distinct_lab`. Cảnh báo: script sau xóa schema `distinct_lab` nếu nó đã tồn tại. **Chỉ chạy khi chắc chắn đang ở database thực hành và schema đó không chứa dữ liệu cần giữ.**

### Tạo schema và bảng

~~~sql
-- CHỈ CHẠY TRONG DATABASE THỰC HÀNH.
DROP SCHEMA IF EXISTS distinct_lab CASCADE;
CREATE SCHEMA distinct_lab;

CREATE TABLE distinct_lab.customers (
    customer_id integer PRIMARY KEY,
    full_name text NOT NULL,
    city text NOT NULL
);

CREATE TABLE distinct_lab.orders (
    order_id integer PRIMARY KEY,
    customer_id integer NOT NULL
        REFERENCES distinct_lab.customers(customer_id),
    ordered_at timestamptz NOT NULL,
    status text NOT NULL
        CHECK (status IN ('paid', 'pending', 'cancelled')),
    total numeric(12, 2) NOT NULL
        CHECK (total >= 0)
);

CREATE TABLE distinct_lab.order_tags (
    order_id integer NOT NULL
        REFERENCES distinct_lab.orders(order_id),
    tag text NOT NULL,
    PRIMARY KEY (order_id, tag)
);
~~~

Ý nghĩa các bảng:

- `customers`: mỗi khách hàng có ID duy nhất, một thành phố và tên.
- `orders`: một khách hàng có thể có nhiều đơn; `order_id` duy nhất.
- `order_tags`: mỗi đơn có thể có nhiều nhãn, dùng để minh họa tình huống `JOIN` làm tăng số hàng.

### Nạp dữ liệu mẫu

~~~sql
INSERT INTO distinct_lab.customers
    (customer_id, full_name, city)
VALUES
    (1, 'An',   'HCM'),
    (2, 'Binh', 'HAN'),
    (3, 'Chi',  'HCM'),
    (4, 'Dung', 'DNG');

INSERT INTO distinct_lab.orders
    (order_id, customer_id, ordered_at, status, total)
VALUES
    (1001, 1, '2026-11-03 09:00:00+00', 'paid',      120.00),
    (1002, 1, '2026-11-06 10:00:00+00', 'pending',    80.00),
    (1003, 1, '2026-11-06 10:00:00+00', 'paid',      150.00),
    (1004, 2, '2026-11-01 08:00:00+00', 'paid',      200.00),
    (1005, 2, '2026-11-04 08:00:00+00', 'cancelled', 300.00),
    (1006, 3, '2026-11-02 12:00:00+00', 'paid',       50.00),
    (1007, 3, '2026-11-07 18:00:00+00', 'paid',       75.00);

INSERT INTO distinct_lab.order_tags (order_id, tag)
VALUES
    (1001, 'gift'),
    (1001, 'web'),
    (1002, 'app'),
    (1003, 'web'),
    (1004, 'web'),
    (1005, 'app'),
    (1006, 'gift'),
    (1007, 'web');
~~~

Điểm được cài đặt có chủ ý:

1. An (ID 1) có **ba đơn hàng**.
2. Hai đơn **1002 và 1003 cùng thời điểm**. Khi chọn đơn mới nhất cho An, cần quy tắc phân định hòa (*tie-breaker*).
3. Binh (ID 2) có hai đơn; đơn mới nhất có trạng thái `cancelled`.
4. Chi (ID 3) có hai đơn, trong đó 1007 mới nhất.
5. Dung (ID 4) **chưa có đơn**.
6. Đơn 1001 có **hai nhãn**, tạo hai dòng khi nối với `order_tags`.

Mọi mốc thời gian đều có offset `+00`. Có thể đặt múi giờ phiên để việc hiển thị thời gian nhất quán:

~~~sql
SET TIME ZONE 'UTC';
~~~

Để kiểm tra dữ liệu:

~~~sql
SELECT
    order_id,
    customer_id,
    ordered_at,
    status,
    total
FROM distinct_lab.orders
ORDER BY order_id;
~~~

Bộ dữ liệu là nền tảng cho các ví dụ tiếp theo. Không cần chạy thêm các thao tác cập nhật/xóa để học `DISTINCT`.

## 3. SELECT DISTINCT: loại trùng trên các biểu thức được SELECT

Cú pháp cơ bản:

~~~sql
SELECT DISTINCT expression_1, expression_2, ...
FROM some_table;
~~~

PostgreSQL tạo tập kết quả mà **không có hai hàng giống nhau trên toàn bộ các biểu thức được chọn**.

### Ví dụ 1: danh sách thành phố

~~~sql
SELECT DISTINCT city
FROM distinct_lab.customers
ORDER BY city;
~~~

Kết quả:

| city |
| --- |
| DNG |
| HAN |
| HCM |

Khách hàng An và Chi đều sống tại HCM, nên `HCM` chỉ xuất hiện một lần.

### Ví dụ 2: danh sách trạng thái đơn hàng

~~~sql
SELECT DISTINCT status
FROM distinct_lab.orders
ORDER BY status;
~~~

Kết quả:

| status |
| --- |
| cancelled |
| paid |
| pending |

Mặc dù trạng thái `paid` xuất hiện nhiều lần, `DISTINCT` trả một giá trị `paid`.

### Ví dụ 3: DISTINCT trên tổ hợp hai cột

~~~sql
SELECT DISTINCT
    customer_id,
    status
FROM distinct_lab.orders
ORDER BY customer_id, status;
~~~

Kết quả:

| customer_id | status |
| ---: | --- |
| 1 | paid |
| 1 | pending |
| 2 | cancelled |
| 2 | paid |
| 3 | paid |

Với `customer_id = 1`, hai đơn `paid` được gộp thành **một cặp (1, paid)**, nhưng `(1, pending)` vẫn là hàng khác. Với khách hàng 2 có hai trạng thái khác nhau, vẫn có hai hàng.

**`DISTINCT` áp dụng cho toàn bộ danh sách biểu thức, không chỉ cột đầu tiên.** Câu:

~~~sql
SELECT DISTINCT customer_id, order_id
FROM distinct_lab.orders;
~~~

vẫn trả **bảy hàng**, bởi vì `order_id` là khóa chính và mỗi cặp `(customer_id, order_id)` duy nhất.

## 4. DISTINCT khác với UNIQUE ở mức schema

Hai từ dễ bị dùng thay cho nhau, nhưng chúng ở hai tầng:

- **`SELECT DISTINCT`:** biến đổi tập kết quả **của một truy vấn** bằng cách loại hàng trùng.
- **`UNIQUE` constraint / unique index:** ngăn các dữ liệu trùng không hợp lệ **được lưu vào bảng** theo quy tắc định nghĩa.

Ví dụ:

~~~sql
CREATE TABLE distinct_lab.accounts (
    account_id integer PRIMARY KEY,
    email text NOT NULL UNIQUE
);
~~~

`UNIQUE(email)` nhằm bảo vệ dữ liệu được ghi. Nó không tự có nghĩa câu truy vấn từ nhiều bảng không cần `DISTINCT`, và `SELECT DISTINCT email` không sửa được dữ liệu trùng đang tồn tại ở một bảng thiếu ràng buộc.

Một câu truy vấn:

~~~sql
SELECT DISTINCT customer_id
FROM distinct_lab.orders;
~~~

chỉ trả danh sách khách hàng đã từng có đơn. Nó **không xóa bớt bất kỳ đơn hàng nào khỏi bảng**.

Nếu một bảng có nhiều bản ghi trùng nghiệp vụ cần làm sạch, phải dùng quy trình kiểm tra, hợp nhất/xóa có kiểm soát và ràng buộc ngăn lỗi tái diễn. Không dùng `DISTINCT` như cách “sửa tận gốc” dữ liệu.

## 5. COUNT(DISTINCT ...): đếm giá trị khác nhau

Tương tự `SELECT DISTINCT`, hàm tổng hợp `COUNT` có thể dùng `DISTINCT`:

~~~sql
SELECT
    COUNT(*) AS total_orders,
    COUNT(DISTINCT customer_id) AS customers_with_orders,
    COUNT(DISTINCT status) AS distinct_statuses
FROM distinct_lab.orders;
~~~

Kết quả:

| total_orders | customers_with_orders | distinct_statuses |
| ---: | ---: | ---: |
| 7 | 3 | 3 |

Trong đó:

- `COUNT(*)` đếm mọi đơn.
- `COUNT(DISTINCT customer_id)` đếm số khách hàng có đơn (1, 2, 3).
- `COUNT(DISTINCT status)` đếm các trạng thái đã xuất hiện.

### NULL có được tính trong COUNT(DISTINCT ...) không?

Với **một biểu thức**, `COUNT(DISTINCT expression)` không đếm các giá trị SQL `NULL`. Trong khi đó, `SELECT DISTINCT expression` có thể trả **một hàng `NULL`** nếu nguồn có một hoặc nhiều `NULL`.

Ví dụ có thể chạy độc lập:

~~~sql
WITH sample(value) AS (
    VALUES
        (1),
        (1),
        (2),
        (NULL::integer),
        (NULL::integer)
)
SELECT
    COUNT(*) AS all_rows,
    COUNT(DISTINCT value) AS distinct_nonnull
FROM sample;
~~~

Kết quả `all_rows = 5`, `distinct_nonnull = 2`.

Còn:

~~~sql
WITH sample(value) AS (
    VALUES
        (1),
        (1),
        (2),
        (NULL::integer),
        (NULL::integer)
)
SELECT DISTINCT value
FROM sample
ORDER BY value NULLS LAST;
~~~

trả ba hàng: `1`, `2` và một hàng `NULL`.

Đây là quy tắc quan trọng khi thống kê dữ liệu nullable; **không thể lấy số hàng của `SELECT DISTINCT nullable_column` rồi mặc định nó luôn bằng `COUNT(DISTINCT nullable_column)`**.

## 6. DISTINCT và ORDER BY: hai trách nhiệm khác nhau

`DISTINCT` quyết định **hàng nào bị coi là trùng**. `ORDER BY` quyết định **thứ tự của những hàng cuối cùng được trả về**.

~~~sql
SELECT DISTINCT city
FROM distinct_lab.customers
ORDER BY city DESC;
~~~

Kết quả vẫn có ba thành phố, nhưng thứ tự là `HCM`, `HAN`, `DNG`.

Nếu không ghi `ORDER BY`, SQL **không cam kết thứ tự hàng**, ngay cả khi execution plan tình cờ có thao tác sắp xếp để loại trùng.

### ORDER BY của SELECT DISTINCT có giới hạn

Trong PostgreSQL, khi dùng `SELECT DISTINCT`, biểu thức của `ORDER BY` phải xuất hiện trong danh sách kết quả `SELECT`.

Câu sau không hợp lệ:

~~~sql
-- Ví dụ cố ý sai:
SELECT DISTINCT city
FROM distinct_lab.customers
ORDER BY full_name;
~~~

Lý do nghiệp vụ cũng dễ thấy: thành phố `HCM` có nhiều người khác nhau, vậy nếu chỉ trả một hàng HCM thì nên dùng tên người nào để quyết định vị trí sắp xếp?

Một cách hợp lệ:

~~~sql
SELECT DISTINCT city, full_name
FROM distinct_lab.customers
ORDER BY full_name;
~~~

Nhưng nó đã đổi **tiêu chí loại trùng**: mỗi cặp thành phố–tên là một hàng khác. Nếu mục tiêu là mỗi thành phố đúng một hàng và sắp theo tên của một **người đại diện**, cần xác định quy tắc chọn đại diện, chẳng hạn `DISTINCT ON` hoặc tổng hợp.

## 7. DISTINCT ON: giữ một hàng đại diện mỗi nhóm

`DISTINCT ON` là phần mở rộng đặc trưng của PostgreSQL:

~~~sql
SELECT DISTINCT ON (group_expression_1, ...)
    column_1, column_2, ...
FROM some_table
ORDER BY
    group_expression_1, ...,
    preferred_order_expression, ...;
~~~

Nó giữ **một hàng đầu tiên của mỗi nhóm** các hàng có cùng giá trị `DISTINCT ON (...)`, theo thứ tự mà PostgreSQL xét sau khi sắp xếp.

Với bộ dữ liệu đơn hàng, yêu cầu thường gặp là:

> “Mỗi khách hàng chỉ lấy một đơn hàng, ưu tiên đơn mới nhất. Nếu hai đơn có cùng thời gian, chọn đơn có ID lớn hơn.”

Ta có thể viết:

~~~sql
SELECT DISTINCT ON (customer_id)
    customer_id,
    order_id,
    ordered_at,
    status,
    total
FROM distinct_lab.orders
ORDER BY
    customer_id,
    ordered_at DESC,
    order_id DESC;
~~~

Kết quả:

| customer_id | order_id | ordered_at (UTC) | status | total |
| ---: | ---: | --- | --- | ---: |
| 1 | 1003 | 2026-11-06 10:00:00+00 | paid | 150.00 |
| 2 | 1005 | 2026-11-04 08:00:00+00 | cancelled | 300.00 |
| 3 | 1007 | 2026-11-07 18:00:00+00 | paid | 75.00 |

Diễn giải:

1. `DISTINCT ON (customer_id)` chia các hàng theo khách hàng.
2. `ORDER BY customer_id` đặt các hàng cùng khách hàng ở gần nhau, đáp ứng yêu cầu cú pháp `DISTINCT ON`.
3. `ordered_at DESC` đưa đơn mới hơn lên trước trong mỗi nhóm.
4. `order_id DESC` phá hòa khi hai đơn có cùng thời gian. Với An, đơn 1002 và 1003 cùng `ordered_at` nhưng **1003 được chọn**.
5. PostgreSQL giữ hàng đầu của mỗi nhóm theo thứ tự trên.

**Không phải `DISTINCT ON` tự hiểu khái niệm “mới nhất”.** Kết quả mới nhất đến từ `ORDER BY` bạn đã thiết kế.

## 8. Tại sao ORDER BY quyết định tính đúng của DISTINCT ON?

Một câu chỉ nêu:

~~~sql
-- Không có quy tắc chọn hàng đại diện ổn định:
SELECT DISTINCT ON (customer_id)
    customer_id, order_id, status
FROM distinct_lab.orders;
~~~

vẫn có thể được PostgreSQL chấp nhận, nhưng **không xác định hàng nào của từng khách hàng được giữ**. Kết quả không được bảo đảm theo thời gian, order_id hay thứ tự chèn.

Nó không có nghĩa “chọn hàng đầu tiên từng được insert”; dữ liệu trong bảng quan hệ không có thứ tự vật lý được cam kết. Execution plan, index, thống kê, VACUUM hoặc thay đổi phiên bản có thể dẫn tới một hàng đại diện khác.

### Thiếu tie-breaker cũng có thể không ổn định

~~~sql
SELECT DISTINCT ON (customer_id)
    customer_id, order_id, ordered_at
FROM distinct_lab.orders
ORDER BY customer_id, ordered_at DESC;
~~~

Với An, đơn 1002 và 1003 có cùng timestamp. Chỉ `ordered_at DESC` **không quy định rõ phải chọn 1002 hay 1003**.

Khi nghiệp vụ cần kết quả lặp lại được, hãy bổ sung một biểu thức cuối cùng có thể phá hòa duy nhất:

~~~sql
ORDER BY
    customer_id,
    ordered_at DESC,
    order_id DESC;
~~~

Ở đây `order_id` là khóa chính, vì vậy khi ghép với customer và thời điểm, thứ tự so sánh có đủ thông tin chọn một hàng ổn định.

### Nếu cần đơn cũ nhất?

Đổi chiều của biểu thức ưu tiên:

~~~sql
SELECT DISTINCT ON (customer_id)
    customer_id, order_id, ordered_at
FROM distinct_lab.orders
ORDER BY
    customer_id,
    ordered_at ASC,
    order_id ASC;
~~~

Kết quả:

| customer_id | order_id cũ nhất |
| ---: | ---: |
| 1 | 1001 |
| 2 | 1004 |
| 3 | 1006 |

Một thay đổi ở `ORDER BY` đã đổi ý nghĩa của “hàng đại diện”, dù tiêu chí nhóm `customer_id` không đổi.

## 9. Quy tắc leftmost ORDER BY của DISTINCT ON

PostgreSQL yêu cầu các biểu thức trong `DISTINCT ON (...)` **khớp với các biểu thức ở phía trái của `ORDER BY`**. Các khóa sắp xếp bổ sung có thể đặt sau đó để chọn hàng ưu tiên trong nhóm.

Hợp lệ:

~~~sql
SELECT DISTINCT ON (customer_id)
    customer_id, order_id, ordered_at
FROM distinct_lab.orders
ORDER BY customer_id, ordered_at DESC, order_id DESC;
~~~

Không hợp lệ:

~~~sql
-- Ví dụ cố ý sai do ORDER BY không bắt đầu
-- bằng biểu thức nhóm customer_id:
SELECT DISTINCT ON (customer_id)
    customer_id, order_id, ordered_at
FROM distinct_lab.orders
ORDER BY ordered_at DESC, customer_id;
~~~

Lỗi điển hình:

~~~text
SELECT DISTINCT ON expressions must match initial ORDER BY expressions
~~~

Với nhiều cột nhóm:

~~~sql
SELECT DISTINCT ON (customer_id, status)
    customer_id,
    status,
    order_id,
    ordered_at
FROM distinct_lab.orders
ORDER BY
    customer_id,
    status,
    ordered_at DESC,
    order_id DESC;
~~~

Truy vấn chọn **một đơn mới nhất cho từng cặp customer–status**, không phải một đơn cho từng khách hàng. Ví dụ An có hai nhóm `paid` và `pending` nên có thể xuất hiện **hai hàng**.

Quy tắc dễ nhớ: **nhóm ở đầu, ưu tiên phía sau**.

## 10. DISTINCT ON theo một cột không có nghĩa chỉ được SELECT một cột

Khác với `DISTINCT`, `DISTINCT ON (customer_id)` không dùng toàn bộ cột `SELECT` để quyết định các hàng cùng nhóm.

~~~sql
SELECT DISTINCT ON (customer_id)
    customer_id,
    order_id,
    status,
    total
FROM distinct_lab.orders
ORDER BY customer_id, total DESC, order_id DESC;
~~~

Nó chọn **đơn có giá trị `total` lớn nhất** của mỗi khách hàng, dù các đơn có status và order_id khác nhau.

Kết quả với dữ liệu mẫu:

| customer_id | order_id | status | total |
| ---: | ---: | --- | ---: |
| 1 | 1003 | paid | 150.00 |
| 2 | 1005 | cancelled | 300.00 |
| 3 | 1007 | paid | 75.00 |

Ở đây Binh có đơn bị hủy nhưng giá trị 300.00 cao nhất. **Nếu nghiệp vụ chỉ muốn đơn đã thanh toán**, phải lọc trạng thái trước khi chọn đại diện, không chỉ sắp xếp total.

### Lọc trước, rồi chọn hàng đại diện

~~~sql
SELECT DISTINCT ON (customer_id)
    customer_id,
    order_id,
    ordered_at,
    total
FROM distinct_lab.orders
WHERE status = 'paid'
ORDER BY customer_id, ordered_at DESC, order_id DESC;
~~~

Kết quả:

| customer_id | order_id paid mới nhất |
| ---: | ---: |
| 1 | 1003 |
| 2 | 1004 |
| 3 | 1007 |

Binh được chọn đơn 1004 vì đơn mới hơn 1005 là `cancelled` và **đã bị lọc trước khi xét `DISTINCT ON`**.

So sánh hai yêu cầu:

- **“Đơn mới nhất của mỗi khách hàng, rồi chỉ hiện nếu trạng thái paid”**: trước tiên chọn mới nhất mọi trạng thái, sau đó lọc kết quả đại diện. Binh **không xuất hiện** vì đơn mới nhất là cancelled.
- **“Đơn paid mới nhất của mỗi khách hàng”**: lọc `paid` trước, sau đó chọn mới nhất. Binh **xuất hiện** với đơn 1004.

Hai câu này có ngữ nghĩa khác nhau dù cùng chứa cụm từ “mới nhất” và “paid”.

## 11. Lọc sau khi chọn đại diện bằng subquery

Muốn chọn đơn mới nhất bất kể trạng thái, sau đó chỉ giữ những đại diện có trạng thái `paid`:

~~~sql
SELECT
    latest.customer_id,
    latest.order_id,
    latest.status,
    latest.ordered_at
FROM (
    SELECT DISTINCT ON (customer_id)
        customer_id,
        order_id,
        status,
        ordered_at
    FROM distinct_lab.orders
    ORDER BY
        customer_id,
        ordered_at DESC,
        order_id DESC
) AS latest
WHERE latest.status = 'paid'
ORDER BY latest.customer_id;
~~~

Kết quả có An với 1003 và Chi với 1007; **Binh bị loại** vì đại diện 1005 có trạng thái cancelled.

Câu này khác với `WHERE status = 'paid'` **bên trong** truy vấn `DISTINCT ON`. Khi viết SQL, thứ tự xử lý logic của việc lọc và chọn hàng đại diện phải khớp câu hỏi nghiệp vụ.

## 12. SELECT DISTINCT ON và thứ tự hiển thị cuối cùng

Do quy tắc `ORDER BY` phải bắt đầu bằng biểu thức nhóm, kết quả trực tiếp của `DISTINCT ON (customer_id)` thường được sắp theo `customer_id`, không phải toàn cục theo thời gian mới nhất.

Giả sử muốn “mỗi khách hàng một đơn mới nhất, sau đó hiển thị toàn bộ danh sách theo thời điểm đơn mới nhất giảm dần”. Hãy dùng truy vấn ngoài:

~~~sql
SELECT
    recent.customer_id,
    recent.order_id,
    recent.ordered_at,
    recent.status
FROM (
    SELECT DISTINCT ON (customer_id)
        customer_id,
        order_id,
        ordered_at,
        status
    FROM distinct_lab.orders
    ORDER BY
        customer_id,
        ordered_at DESC,
        order_id DESC
) AS recent
ORDER BY
    recent.ordered_at DESC,
    recent.order_id DESC;
~~~

Thứ tự mong đợi là Chi (1007), An (1003), Binh (1005) theo mốc thời gian đã seed.

**Hai loại thứ tự khác nhau:**

1. `ORDER BY` **bên trong**: chọn hàng đại diện của mỗi nhóm.
2. `ORDER BY` **bên ngoài**: trình bày các hàng đại diện theo thứ tự người dùng muốn xem.

Nếu cần phân trang:

~~~sql
SELECT *
FROM (
    SELECT DISTINCT ON (customer_id)
        customer_id,
        order_id,
        ordered_at
    FROM distinct_lab.orders
    ORDER BY customer_id, ordered_at DESC, order_id DESC
) AS recent
ORDER BY ordered_at DESC, order_id DESC
LIMIT 2;
~~~

`LIMIT 2` được áp dụng **sau khi** đã chọn một hàng mỗi khách hàng và sắp thứ tự ở truy vấn ngoài, không phải lấy hai đơn bất kỳ trước rồi mới loại trùng.

## 13. DISTINCT ON cùng LEFT JOIN: giữ nhóm chưa có bản ghi con

Nếu bắt đầu từ bảng `orders`, khách hàng Dung không xuất hiện vì chưa có đơn. Nhưng bài toán có thể yêu cầu:

> “Hiển thị tất cả khách hàng, kèm đơn mới nhất nếu có.”

Dùng `LEFT JOIN` từ `customers`:

~~~sql
SELECT DISTINCT ON (c.customer_id)
    c.customer_id,
    c.full_name,
    o.order_id,
    o.ordered_at,
    o.status
FROM distinct_lab.customers AS c
LEFT JOIN distinct_lab.orders AS o
    ON o.customer_id = c.customer_id
ORDER BY
    c.customer_id,
    o.ordered_at DESC NULLS LAST,
    o.order_id DESC NULLS LAST;
~~~

Kết quả:

| customer_id | full_name | order_id | status |
| ---: | --- | ---: | --- |
| 1 | An | 1003 | paid |
| 2 | Binh | 1005 | cancelled |
| 3 | Chi | 1007 | paid |
| 4 | Dung | NULL | NULL |

`LEFT JOIN` tạo một hàng với các cột phía `orders` bằng `NULL` cho Dung. Vì nhóm `customer_id = 4` vẫn có một hàng, `DISTINCT ON` giữ đại diện đó.

### Vì sao đặt NULLS LAST?

Trong PostgreSQL, khi sắp `DESC`, mặc định các giá trị `NULL` thường được xếp **trước** nếu không chỉ rõ. Nếu `ordered_at` cho phép `NULL` ở một đơn thật, câu `ORDER BY ordered_at DESC` có thể vô tình ưu tiên đơn không có thời gian.

Viết:

~~~sql
ORDER BY
    c.customer_id,
    o.ordered_at DESC NULLS LAST,
    o.order_id DESC NULLS LAST;
~~~

để xác định “ưu tiên thời gian mới nhất đã biết, đẩy giá trị thiếu xuống cuối”.

Trong schema ví dụ, `orders.ordered_at` khai báo `NOT NULL`; trường hợp NULL của Dung đến từ **phép nối ngoài**, không phải một đơn có thời gian thiếu.

### Lọc đơn paid mà vẫn giữ khách hàng không có đơn paid

~~~sql
SELECT DISTINCT ON (c.customer_id)
    c.customer_id,
    c.full_name,
    o.order_id,
    o.ordered_at
FROM distinct_lab.customers AS c
LEFT JOIN distinct_lab.orders AS o
    ON o.customer_id = c.customer_id
   AND o.status = 'paid'
ORDER BY
    c.customer_id,
    o.ordered_at DESC NULLS LAST,
    o.order_id DESC NULLS LAST;
~~~

Binh lấy 1004; Dung vẫn có hàng `NULL`. Đặt `o.status = 'paid'` trong `WHERE` thay vì `ON` sẽ loại các khách hàng không có đơn paid, khiến ý nghĩa `LEFT JOIN` thay đổi.

## 14. DISTINCT ON với NULL trong khóa nhóm

`DISTINCT ON` nhóm các hàng có cùng biểu thức được chọn. Đối với mục đích loại trùng, các giá trị SQL `NULL` trong biểu thức khóa được xem thuộc **cùng một nhóm**.

Ví dụ:

~~~sql
WITH sample(customer_id, note, created_at) AS (
    VALUES
        (1, 'A', timestamp '2026-11-01 10:00'),
        (1, 'B', timestamp '2026-11-02 10:00'),
        (NULL::integer, 'Unassigned A', timestamp '2026-11-01 10:00'),
        (NULL::integer, 'Unassigned B', timestamp '2026-11-03 10:00')
)
SELECT DISTINCT ON (customer_id)
    customer_id, note, created_at
FROM sample
ORDER BY customer_id NULLS LAST, created_at DESC, note;
~~~

Kết quả gồm hai hàng:

| customer_id | note |
| --- | --- |
| 1 | B |
| NULL | Unassigned B |

Hai hàng có `customer_id IS NULL` được xem là cùng một nhóm cho `DISTINCT ON (customer_id)`; hàng có timestamp mới hơn được giữ.

Không nên nhầm quy tắc loại trùng `NULL` với biểu thức so sánh trong `WHERE`: điều kiện `customer_id = NULL` **không đúng cách** để tìm giá trị NULL; phải dùng `IS NULL`.

## 15. Chọn đại diện theo nhiều tiêu chí ưu tiên

“Đại diện” không nhất thiết là hàng mới nhất. Quy tắc có thể là:

- Ưu tiên đơn `paid`, sau đó đơn mới nhất.
- Ưu tiên bản ghi có số tiền lớn nhất, rồi ID nhỏ nhất.
- Ưu tiên địa chỉ mặc định, sau đó lần cập nhật gần nhất.
- Ưu tiên hàng có dữ liệu đầy đủ, rồi hàng mới hơn.

### Ví dụ: ưu tiên trạng thái paid, rồi thời gian mới nhất

~~~sql
SELECT DISTINCT ON (customer_id)
    customer_id,
    order_id,
    status,
    ordered_at
FROM distinct_lab.orders
ORDER BY
    customer_id,
    (status = 'paid') DESC,
    ordered_at DESC,
    order_id DESC;
~~~

Biểu thức Boolean `status = 'paid'` là `true` hoặc `false` vì cột `status` không NULL. PostgreSQL sắp `true` sau `false` theo thứ tự tăng, nên `DESC` đưa `true` lên trước trong mỗi nhóm.

Trong bộ dữ liệu:

- An: chọn đơn 1003 vì `paid` và mới hơn đơn paid 1001.
- Binh: chọn đơn 1004 (`paid`) **dù** đơn 1005 (`cancelled`) mới hơn.
- Chi: chọn 1007.

Đó là ý nghĩa “ưu tiên paid”, **không phải** “chọn đơn mới nhất bất kể trạng thái”.

### Ví dụ: ưu tiên số tiền cao nhất nhưng vẫn có tie-breaker

~~~sql
SELECT DISTINCT ON (customer_id)
    customer_id,
    order_id,
    total
FROM distinct_lab.orders
ORDER BY
    customer_id,
    total DESC,
    order_id DESC;
~~~

Nếu hai đơn cùng `total`, đơn có ID lớn hơn được chọn. Việc thêm `order_id` làm quy tắc rõ ràng, không phụ thuộc vào thứ tự vật lý hay kế hoạch thực thi.

### Ví dụ: ưu tiên theo biểu thức CASE

~~~sql
SELECT DISTINCT ON (customer_id)
    customer_id,
    order_id,
    status,
    ordered_at
FROM distinct_lab.orders
ORDER BY
    customer_id,
    CASE status
        WHEN 'paid' THEN 1
        WHEN 'pending' THEN 2
        ELSE 3
    END,
    ordered_at DESC,
    order_id DESC;
~~~

`CASE` giúp thể hiện thứ bậc nghiệp vụ khi không thể mô tả chỉ bằng `ASC`/`DESC` trên một cột.

## 16. DISTINCT ON so với GROUP BY và MAX()

Một lỗi rất phổ biến là muốn “lấy đơn mới nhất” nhưng lại viết:

~~~sql
SELECT
    customer_id,
    MAX(ordered_at) AS latest_time
FROM distinct_lab.orders
GROUP BY customer_id;
~~~

Câu SQL này **đúng**, nhưng nó trả **thời gian mới nhất**, không trả toàn bộ hàng đơn hàng tương ứng. Muốn lấy thêm `order_id`, `status` hoặc `total`, cần một chiến lược chọn hàng.

### Không thể SELECT cột bất kỳ ngoài GROUP BY

Câu sau không hợp lệ theo các quy tắc nhóm thông thường vì `order_id` không được tổng hợp hay được xác định hợp lệ bởi nhóm:

~~~sql
-- Ví dụ cố ý sai:
SELECT
    customer_id,
    order_id,
    MAX(ordered_at)
FROM distinct_lab.orders
GROUP BY customer_id;
~~~

PostgreSQL không thể tự biết nên lấy `order_id` nào nếu một khách hàng có nhiều đơn.

### JOIN lại với MAX có thể trả nhiều hàng

Một kỹ thuật thường gặp:

~~~sql
WITH latest_times AS (
    SELECT
        customer_id,
        MAX(ordered_at) AS latest_time
    FROM distinct_lab.orders
    GROUP BY customer_id
)
SELECT o.customer_id, o.order_id, o.ordered_at
FROM distinct_lab.orders AS o
JOIN latest_times AS lt
    ON lt.customer_id = o.customer_id
   AND lt.latest_time = o.ordered_at
ORDER BY o.customer_id, o.order_id;
~~~

Với khách hàng An, hai đơn 1002 và 1003 **cùng thời điểm mới nhất** nên truy vấn trả **cả hai**. Nếu bài toán cần “một hàng duy nhất”, phép JOIN với `MAX` chưa giải quyết tie-breaker.

`DISTINCT ON` có lợi thế viết ngắn gọn:

~~~sql
SELECT DISTINCT ON (customer_id)
    customer_id, order_id, ordered_at, status
FROM distinct_lab.orders
ORDER BY customer_id, ordered_at DESC, order_id DESC;
~~~

Tuy nhiên, nếu nghiệp vụ cần **tất cả các hàng đồng hạng nhất**, cách JOIN với `MAX` hoặc window function như `RANK()` lại phù hợp hơn `DISTINCT ON`.

## 17. DISTINCT ON so với ROW_NUMBER()

`ROW_NUMBER()` là hàm cửa sổ (*window function*) gán số thứ tự cho các hàng trong mỗi nhóm được xác định bởi `PARTITION BY` và `ORDER BY`.

Truy vấn tương đương với “mỗi khách hàng, lấy đơn mới nhất và ID lớn nhất khi hòa”:

~~~sql
WITH ranked_orders AS (
    SELECT
        o.customer_id,
        o.order_id,
        o.ordered_at,
        o.status,
        o.total,
        ROW_NUMBER() OVER (
            PARTITION BY o.customer_id
            ORDER BY o.ordered_at DESC, o.order_id DESC
        ) AS rn
    FROM distinct_lab.orders AS o
)
SELECT
    customer_id,
    order_id,
    ordered_at,
    status,
    total
FROM ranked_orders
WHERE rn = 1
ORDER BY customer_id;
~~~

Kết quả giống `DISTINCT ON`: đơn 1003, 1005 và 1007.

### Tại sao cần CTE hoặc subquery?

Window function được tính ở giai đoạn truy vấn không cho dùng trực tiếp trong `WHERE` của cùng SELECT. Vì thế mẫu:

~~~sql
-- Ví dụ cố ý sai:
SELECT *
FROM distinct_lab.orders
WHERE ROW_NUMBER() OVER (
    PARTITION BY customer_id
    ORDER BY ordered_at DESC
) = 1;
~~~

không hợp lệ. Ta phải tính `ROW_NUMBER()` ở truy vấn trong rồi lọc `rn = 1` ở truy vấn ngoài.

### Khi nào dùng ROW_NUMBER thay DISTINCT ON?

- Muốn **top 2, top 3, top N** trong mỗi nhóm (`WHERE rn <= N`).
- Muốn giữ cột xếp hạng để giải thích kết quả.
- Muốn viết SQL có tính di động hơn giữa các DBMS hỗ trợ window functions.
- Muốn kết hợp nhiều loại xếp hạng trong một truy vấn.

Ví dụ lấy **hai đơn mới nhất của mỗi khách hàng**:

~~~sql
WITH ranked_orders AS (
    SELECT
        customer_id,
        order_id,
        ordered_at,
        ROW_NUMBER() OVER (
            PARTITION BY customer_id
            ORDER BY ordered_at DESC, order_id DESC
        ) AS rn
    FROM distinct_lab.orders
)
SELECT customer_id, order_id, ordered_at
FROM ranked_orders
WHERE rn <= 2
ORDER BY customer_id, rn;
~~~

`DISTINCT ON` chỉ giữ một hàng đại diện mỗi nhóm; không dùng nó trực tiếp để lấy hai hàng mỗi nhóm.

### RANK và DENSE_RANK giữ các hàng đồng hạng

Nếu yêu cầu “lấy **mọi đơn có thời gian mới nhất** cho từng khách hàng”, dùng `RANK()`:

~~~sql
WITH ranked AS (
    SELECT
        customer_id,
        order_id,
        ordered_at,
        RANK() OVER (
            PARTITION BY customer_id
            ORDER BY ordered_at DESC
        ) AS time_rank
    FROM distinct_lab.orders
)
SELECT customer_id, order_id, ordered_at
FROM ranked
WHERE time_rank = 1
ORDER BY customer_id, order_id;
~~~

Với An, truy vấn trả cả **1002 và 1003** vì cùng `ordered_at` cao nhất. Nếu thêm `order_id DESC` vào `ORDER BY` của `RANK()`, hai hàng không còn đồng hạng theo toàn bộ tiêu chí, nên cần lựa chọn tiêu chí phù hợp câu hỏi.

## 18. DISTINCT ON và LATERAL: chọn hàng mới nhất cho mỗi cha

Khi đã có danh sách khách hàng và muốn tìm đúng một đơn gần nhất cho **mỗi khách hàng**, một cách khác là `LEFT JOIN LATERAL`:

~~~sql
SELECT
    c.customer_id,
    c.full_name,
    recent.order_id,
    recent.ordered_at,
    recent.status
FROM distinct_lab.customers AS c
LEFT JOIN LATERAL (
    SELECT
        o.order_id,
        o.ordered_at,
        o.status
    FROM distinct_lab.orders AS o
    WHERE o.customer_id = c.customer_id
    ORDER BY o.ordered_at DESC, o.order_id DESC
    LIMIT 1
) AS recent ON TRUE
ORDER BY c.customer_id;
~~~

Kết quả gồm bốn khách hàng, Dung có các cột đơn hàng bằng `NULL`.

`LATERAL` cho phép truy vấn trong dùng `c.customer_id` từ hàng khách hàng hiện tại. Với chỉ mục phù hợp, PostgreSQL có thể tìm một đơn mới nhất cho **từng** khách hàng hiệu quả, đặc biệt khi danh sách khách hàng đầu vào nhỏ so với tổng số đơn rất lớn.

Nhưng nó không mặc nhiên nhanh hơn `DISTINCT ON`:

- Nếu chọn gần như toàn bộ khách hàng, nhiều lần index lookup có thể không lợi hơn một lượt quét/sắp dữ liệu.
- Nếu chỉ có vài khách hàng được lọc, `LATERAL ... LIMIT 1` có thể là lựa chọn tốt.
- Kế hoạch thực tế phụ thuộc index, thống kê và phân bố dữ liệu.

Hãy dùng `EXPLAIN (ANALYZE, BUFFERS)` trên truy vấn chỉ đọc với dữ liệu đại diện để so sánh thay vì chọn một cú pháp chỉ vì “nghe nhanh hơn”.

## 19. DISTINCT sau JOIN: khi nào đúng, khi nào che lỗi?

Giả sử muốn lấy danh sách khách hàng đã đặt ít nhất một đơn. Một cách:

~~~sql
SELECT DISTINCT
    c.customer_id,
    c.full_name
FROM distinct_lab.customers AS c
JOIN distinct_lab.orders AS o
    ON o.customer_id = c.customer_id
ORDER BY c.customer_id;
~~~

Truy vấn trả An, Binh, Chi. Do `JOIN` tạo một hàng cho **mỗi đơn**, `DISTINCT` loại các lần lặp của khách hàng.

Nhưng có thể diễn đạt ý nghĩa “khách hàng có ít nhất một đơn” rõ hơn bằng `EXISTS`:

~~~sql
SELECT
    c.customer_id,
    c.full_name
FROM distinct_lab.customers AS c
WHERE EXISTS (
    SELECT 1
    FROM distinct_lab.orders AS o
    WHERE o.customer_id = c.customer_id
)
ORDER BY c.customer_id;
~~~

`EXISTS` thể hiện trực tiếp một điều kiện tồn tại; trong nhiều trường hợp planner có thể dùng kế hoạch semi-join phù hợp mà không cần sinh toàn bộ tập hàng JOIN rồi loại trùng.

### Trường hợp JOIN order_tags nhân hàng

~~~sql
SELECT
    o.order_id,
    o.customer_id,
    t.tag
FROM distinct_lab.orders AS o
JOIN distinct_lab.order_tags AS t
    ON t.order_id = o.order_id
WHERE o.order_id = 1001
ORDER BY t.tag;
~~~

Đơn 1001 xuất hiện **hai hàng** vì có hai tag `gift` và `web`. Đây **không phải dữ liệu trùng sai**: mỗi hàng mô tả một liên kết đơn–tag khác nhau.

Nếu chỉ muốn danh sách đơn có ít nhất một tag:

~~~sql
SELECT DISTINCT o.order_id
FROM distinct_lab.orders AS o
JOIN distinct_lab.order_tags AS t
    ON t.order_id = o.order_id
ORDER BY o.order_id;
~~~

hoặc dùng `EXISTS`:

~~~sql
SELECT o.order_id
FROM distinct_lab.orders AS o
WHERE EXISTS (
    SELECT 1
    FROM distinct_lab.order_tags AS t
    WHERE t.order_id = o.order_id
)
ORDER BY o.order_id;
~~~

**Đừng thêm `DISTINCT` một cách phản xạ vào truy vấn khi hàng bị nhân.** Trước tiên hãy kiểm tra loại quan hệ (1:N, N:M), điều kiện `JOIN` và đơn vị kết quả mong muốn. Một điều kiện JOIN sai có thể sinh tích Descartes lớn; `DISTINCT` không biến truy vấn sai thành đúng về nghiệp vụ.

## 20. DISTINCT ON với biểu thức chuẩn hóa

Đôi khi các giá trị cần loại trùng khác nhau về chữ hoa/chữ thường hoặc khoảng trắng. Ví dụ email `' An@Example.test '` và `'an@example.test'` có thể được coi là cùng một khóa chuẩn hóa theo quy tắc ứng dụng.

Một demo độc lập:

~~~sql
WITH contacts(contact_id, email, created_at) AS (
    VALUES
        (1, ' An@Example.test ', timestamp '2026-11-01 08:00'),
        (2, 'an@example.test',   timestamp '2026-11-02 08:00'),
        (3, 'Binh@example.test', timestamp '2026-11-01 10:00')
)
SELECT DISTINCT ON (lower(trim(email)))
    contact_id,
    email,
    lower(trim(email)) AS normalized_email,
    created_at
FROM contacts
ORDER BY
    lower(trim(email)),
    created_at DESC,
    contact_id DESC;
~~~

Kết quả chọn contact ID 2 cho email của An và contact ID 3 cho Binh.

Các điểm quan trọng:

- `DISTINCT ON` nhóm theo **biểu thức `lower(trim(email))`**, không chỉ theo chuỗi gốc.
- `ORDER BY` bắt đầu bằng đúng biểu thức nhóm đó.
- Timestamp và contact_id xác định đại diện khi có nhiều hàng cùng khóa chuẩn hóa.
- Kết quả vẫn giữ được email gốc của **hàng đại diện**, không biến mọi email thành chuỗi chuẩn hóa.

Trong hệ thống thật, quy tắc xác định email trùng có thể phức tạp hơn việc `lower(trim())`: Unicode, collation, chuẩn hóa tên miền và chính sách định danh của ứng dụng phải được thống nhất. Không sử dụng một biểu thức normalization đơn giản để tự gộp tài khoản production mà chưa xác nhận nghiệp vụ.

## 21. DISTINCT và collation, kiểu dữ liệu

Định nghĩa “hai giá trị bằng nhau” phụ thuộc **kiểu dữ liệu** và quy tắc so sánh có liên quan.

Ví dụ:

- Với số nguyên, giá trị 1 và 1 được coi là trùng.
- Với text, so sánh có thể chịu ảnh hưởng quy tắc collation; các collation không xác định (*nondeterministic collation*) có thể có ngữ nghĩa bằng nhau khác so với so sánh byte.
- Với timestamp, hai giá trị có cùng thời điểm tuyệt đối có thể được xem bằng nhau dù văn bản đầu vào biểu diễn múi giờ khác nhau khi kiểu là `timestamptz`.
- Với `NULL`, `DISTINCT` cho một nhóm NULL trong kết quả.

Hãy xem mục tiêu là **giá trị logic** hay **biểu diễn văn bản**. Ví dụ khi muốn loại trùng thời điểm, nên giữ kiểu `timestamptz` và không ép sang chuỗi đã format rồi loại trùng theo chuỗi, vì cách trình bày có thể phụ thuộc TimeZone hoặc DateStyle.

### Có phải mọi kiểu dữ liệu đều dùng DISTINCT được?

`DISTINCT` cần khả năng xác định tính bằng nhau của các biểu thức đầu ra. Phần lớn kiểu phổ biến như integer, text, date, timestamp và uuid có cơ chế phù hợp. Một số kiểu dữ liệu hoặc biểu thức có thể thiếu toán tử so sánh cần thiết; ví dụ kiểu `json` lịch sử không có toán tử bằng thông thường như `jsonb`.

Với dữ liệu JSON cần so sánh giá trị, cân nhắc dùng `jsonb` khi đúng ngữ nghĩa, nhưng chú ý `jsonb` có quy tắc chuẩn hóa khác với `json` (ví dụ thứ tự khóa object không được giữ như văn bản gốc).

Không nên ép kiểu tùy ý chỉ để cho `DISTINCT` chạy nếu điều đó làm thay đổi ý nghĩa dữ liệu.

## 22. DISTINCT ON không phải lựa chọn hàng ngẫu nhiên

Đôi khi bài toán là “mỗi nhóm lấy một hàng bất kỳ”. Có thể viết `DISTINCT ON (group_key)` mà không `ORDER BY`, nhưng đó không phải một **random sampling** đáng tin cậy.

PostgreSQL có thể giữ một hàng phụ thuộc kế hoạch, cách đọc dữ liệu và thứ tự nội bộ; nó không phân bố ngẫu nhiên theo quy tắc đã định. Nếu cần lấy mẫu ngẫu nhiên có kiểm soát, phải định nghĩa phương pháp sampling riêng và lưu seed/quy trình khi cần tái lập.

Ngược lại, nếu **bất kỳ hàng nào đều hợp lệ**, truy vấn không xác định đại diện có thể phù hợp về mặt kết quả nhưng kém ổn định khi sau này yêu cầu thay đổi hoặc khi test snapshot. Nên mô tả rõ hợp đồng kết quả và thêm một quy tắc lựa chọn ổn định khi có thể.

## 23. DISTINCT và LIMIT: không thay thế nhau

`LIMIT` giới hạn **số hàng**, còn `DISTINCT` giới hạn **các giá trị/tổ hợp lặp lại**.

~~~sql
SELECT DISTINCT customer_id
FROM distinct_lab.orders
ORDER BY customer_id
LIMIT 2;
~~~

Truy vấn trả hai giá trị customer_id đầu theo thứ tự: 1 và 2. Nó **không** có nghĩa “mỗi khách hàng lấy hai đơn”.

Muốn “hai đơn mới nhất **cho từng khách hàng**”, dùng `ROW_NUMBER()` với `PARTITION BY customer_id` như ở mục 17.

Muốn “mỗi khách hàng một đơn mới nhất, rồi lấy hai hàng đại diện mới nhất toàn hệ thống”, dùng `DISTINCT ON` trong subquery và `LIMIT 2` ở truy vấn ngoài như mục 12.

Phân biệt các bước giúp tránh một lỗi phổ biến: đặt `LIMIT` trong subquery **trước khi nhóm** làm mất các ứng viên của khách hàng khác.

## 24. Query plan và chi phí của DISTINCT

Khi loại trùng, PostgreSQL phải xác định những hàng nào có cùng khóa. Kế hoạch có thể dùng những cơ chế như:

- **Sort + Unique:** sắp theo biểu thức cần loại trùng, rồi giữ mỗi nhóm một hàng.
- **HashAggregate:** nhóm các giá trị vào cấu trúc hash để loại trùng khi kế hoạch và kiểu dữ liệu cho phép.
- **Index scan theo thứ tự phù hợp:** tận dụng dữ liệu đã có thứ tự để giảm nhu cầu sort.
- **Parallel/aggregate tùy trường hợp:** planner có thể chọn các biến thể khác theo kích thước dữ liệu và cấu hình.

Không có một kế hoạch cố định cho mọi truy vấn `DISTINCT`. Số hàng, kiểu dữ liệu, memory budget và index ảnh hưởng chi phí.

### Quan sát bằng EXPLAIN

~~~sql
EXPLAIN
SELECT DISTINCT customer_id
FROM distinct_lab.orders;
~~~

Và:

~~~sql
EXPLAIN
SELECT DISTINCT ON (customer_id)
    customer_id, order_id, ordered_at
FROM distinct_lab.orders
ORDER BY customer_id, ordered_at DESC, order_id DESC;
~~~

Kế hoạch thứ hai thường có thao tác phù hợp với việc tạo thứ tự và giữ một hàng mỗi nhóm. Nếu nguồn đã cung cấp thứ tự phù hợp nhờ index, planner có thể tránh một phần sort.

Muốn xem số liệu thực thi:

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT DISTINCT ON (customer_id)
    customer_id, order_id, ordered_at
FROM distinct_lab.orders
ORDER BY customer_id, ordered_at DESC, order_id DESC;
~~~

Với `SELECT` trên bộ dữ liệu lab, đây là cách quan sát tương đối an toàn. Nhưng `EXPLAIN ANALYZE` **thực thi câu SQL**, nên không dùng trên câu `UPDATE`/`DELETE` của dữ liệu thật chỉ để “xem kế hoạch” nếu chưa chuẩn bị transaction/rollback và phạm vi an toàn.

### Thêm chỉ mục cho truy vấn mới nhất theo khách hàng

~~~sql
CREATE INDEX idx_orders_customer_recent
ON distinct_lab.orders (
    customer_id,
    ordered_at DESC,
    order_id DESC
);
~~~

Thứ tự khóa index trùng với:

~~~sql
ORDER BY customer_id, ordered_at DESC, order_id DESC
~~~

Đây là một dạng index có thể hữu ích cho việc lấy hàng theo `customer_id` và thứ tự mới nhất. Đặc biệt khi bảng lớn, planner có thể tận dụng index để giảm chi phí sắp xếp và truy cập.

**Nhưng index không tự bảo đảm chỉ đọc một hàng cho mỗi nhóm.** Một kế hoạch `DISTINCT ON` có thể vẫn phải duyệt nhiều phần tử index/nguồn để xác định tất cả nhóm. Nếu chỉ lấy một đơn cho một số ít khách hàng cụ thể, cách `LATERAL ... LIMIT 1` có thể dùng index hiệu quả hơn.

Sau khi tạo index, bảng chỉ có bảy hàng có thể vẫn dùng `Seq Scan + Sort` vì PostgreSQL ước lượng quét tuần tự rẻ hơn. Đây không phải bằng chứng index bị lỗi; benchmark nên dùng dữ liệu và độ chọn lọc đại diện.

## 25. Khi nào dùng DISTINCT ON, khi nào dùng ROW_NUMBER hoặc GROUP BY?

| Nhu cầu | Gợi ý | Lý do |
| --- | --- | --- |
| Danh sách thành phố khác nhau | `SELECT DISTINCT city` | Chỉ cần giá trị duy nhất |
| Đếm số khách hàng có đơn | `COUNT(DISTINCT customer_id)` | Cần một giá trị tổng hợp |
| Tổng doanh thu mỗi khách hàng | `GROUP BY customer_id` + `SUM` | Cần tính toán trên toàn nhóm |
| Một đơn mới nhất mỗi khách hàng | `DISTINCT ON (customer_id)` | Trả hàng đại diện đầy đủ, cú pháp ngắn |
| Top ba đơn mới nhất mỗi khách hàng | `ROW_NUMBER() ... rn <= 3` | Cần nhiều hàng theo thứ hạng |
| Tất cả các đơn có thời điểm mới nhất, kể cả hòa | `RANK() = 1` hoặc JOIN với `MAX` | Không được loại những hàng đồng hạng |
| Khách hàng có ít nhất một đơn | `EXISTS` | Diễn đạt điều kiện tồn tại trực tiếp |
| Một đơn mới nhất cho ít khách hàng đã lọc | `LEFT JOIN LATERAL (... LIMIT 1)` | Có thể tận dụng index lookup cho từng cha |
| Đơn mới nhất theo mỗi cặp customer–status | `DISTINCT ON (customer_id, status)` | Nhóm theo tổ hợp |
| Xóa dữ liệu trùng đã lưu | Migration/cleanup + constraint | `DISTINCT` không sửa bảng |

**Chọn công cụ dựa trên hình dạng kết quả mong muốn**, không dựa vào câu nào ít ký tự nhất. Một aggregate có thể đơn giản hơn nếu chỉ cần số lượng; một window function có thể phù hợp hơn nếu cần xếp hạng nhiều hàng; `DISTINCT ON` tiện khi muốn giữ nguyên các cột của một hàng đại diện.

## 26. Những lỗi thường gặp

### Lỗi 1: Nghĩ DISTINCT chỉ áp dụng cho cột đầu

~~~sql
SELECT DISTINCT customer_id, order_id
FROM distinct_lab.orders;
~~~

Vì mỗi `order_id` duy nhất, truy vấn vẫn trả bảy hàng. Nếu cần khách hàng duy nhất, chỉ chọn `customer_id` hoặc dùng cách tổng hợp thích hợp.

### Lỗi 2: Dùng DISTINCT để sửa JOIN bị nhân hàng

Nếu một khách hàng có nhiều đơn hoặc một đơn nhiều tag, nhiều hàng sau JOIN có thể là dữ liệu hợp lệ. Kiểm tra lại số lượng quan hệ và điều kiện JOIN trước khi loại trùng.

### Lỗi 3: Dùng DISTINCT ON không ORDER BY rồi gọi đó là “mới nhất”

Không có cơ sở để xác định mới nhất. Cần `ORDER BY group_key, created_at DESC, unique_id DESC`.

### Lỗi 4: Thiếu khóa phá hòa

Hai đơn cùng `ordered_at` có thể dẫn đến kết quả đại diện không ổn định. Thêm `order_id` hoặc một khóa cuối có tính duy nhất.

### Lỗi 5: Đặt ORDER BY khác quy tắc leftmost

`DISTINCT ON (customer_id)` mà `ORDER BY ordered_at DESC, customer_id` gây lỗi cú pháp. Phải bắt đầu bằng biểu thức nhóm.

### Lỗi 6: Lọc paid ở sai tầng

Lọc `WHERE status='paid'` trước `DISTINCT ON` nghĩa là “đơn paid mới nhất”. Lọc sau khi chọn đại diện nghĩa là “đơn mới nhất có tình cờ paid hay không”. Hai yêu cầu khác nhau.

### Lỗi 7: Dùng MAX(timestamp) rồi chọn order_id tùy ý

`MAX(ordered_at)` cho một giá trị thời gian, không tự gắn với một `order_id` duy nhất. Nếu nhiều đơn trùng thời gian, JOIN lại với MAX có thể trả nhiều hàng.

### Lỗi 8: Hiểu NULL như giá trị luôn khác nhau

`SELECT DISTINCT` và `DISTINCT ON` có quy tắc gộp các giá trị NULL cho việc loại trùng, còn `COUNT(DISTINCT single_expression)` bỏ qua NULL.

### Lỗi 9: Không dùng NULLS LAST khi DESC trên cột nullable

PostgreSQL mặc định `DESC` ưu tiên `NULL` trước. Một giá trị thời gian thiếu có thể bị chọn thay thời gian mới nhất hợp lệ.

### Lỗi 10: Chỉ nhìn kết quả được sắp mà không có ORDER BY ngoài

Thứ tự bên trong nhằm chọn đại diện, không tự đáp ứng yêu cầu “hiển thị đại diện mới nhất toàn hệ thống”. Dùng query ngoài với `ORDER BY` riêng.

### Lỗi 11: Dùng DISTINCT để xóa trùng khỏi bảng

`SELECT DISTINCT` chỉ thay đổi kết quả truy vấn. Dữ liệu gốc vẫn còn; muốn sửa phải có quy trình cleanup và ràng buộc duy nhất.

### Lỗi 12: Giả định DISTINCT ON là chuẩn SQL trên mọi DBMS

`DISTINCT ON` là cú pháp PostgreSQL; chuyển sang một DBMS khác có thể cần `ROW_NUMBER()` hoặc phương án tương đương.

### Lỗi 13: Cho rằng có index thì DISTINCT ON luôn O(số nhóm)

Không nhất thiết. PostgreSQL có thể vẫn đọc nhiều hàng/index entries; hãy xem `EXPLAIN` và số hàng thực tế.

### Lỗi 14: Chọn đại diện rồi nghĩ dữ liệu luôn là mới nhất về sau

Một truy vấn diễn ra trên snapshot phù hợp với mức isolation và thời điểm thực thi. Một transaction khác có thể chèn đơn mới sau đó; `DISTINCT ON` không tạo “view sống” tự cập nhật ở phía client.

## 27. Thực hành có đáp án

Các bài dưới đây dựa vào dữ liệu mục 2, không yêu cầu sửa dữ liệu.

### Bài 1: Các thành phố không trùng

Viết query lấy danh sách city từ bảng khách hàng.

~~~sql
SELECT DISTINCT city
FROM distinct_lab.customers
ORDER BY city;
~~~

**Đáp án:** DNG, HAN, HCM.

### Bài 2: Khách hàng nào từng đặt đơn?

~~~sql
SELECT DISTINCT customer_id
FROM distinct_lab.orders
ORDER BY customer_id;
~~~

**Đáp án:** 1, 2, 3. Dung (ID 4) chưa có đơn nên không xuất hiện.

### Bài 3: Đếm số khách hàng có đơn

~~~sql
SELECT COUNT(DISTINCT customer_id) AS customer_count
FROM distinct_lab.orders;
~~~

**Đáp án:** `3`.

### Bài 4: Lấy đơn mới nhất của mỗi khách hàng

~~~sql
SELECT DISTINCT ON (customer_id)
    customer_id, order_id, ordered_at
FROM distinct_lab.orders
ORDER BY customer_id, ordered_at DESC, order_id DESC;
~~~

**Đáp án:** `(1,1003)`, `(2,1005)`, `(3,1007)`.

### Bài 5: Chọn đơn paid mới nhất

~~~sql
SELECT DISTINCT ON (customer_id)
    customer_id, order_id, status
FROM distinct_lab.orders
WHERE status = 'paid'
ORDER BY customer_id, ordered_at DESC, order_id DESC;
~~~

**Đáp án:** `(1,1003,paid)`, `(2,1004,paid)`, `(3,1007,paid)`.

### Bài 6: Lấy tất cả khách hàng, kể cả chưa có đơn

~~~sql
SELECT DISTINCT ON (c.customer_id)
    c.customer_id,
    c.full_name,
    o.order_id
FROM distinct_lab.customers AS c
LEFT JOIN distinct_lab.orders AS o
    ON o.customer_id = c.customer_id
ORDER BY
    c.customer_id,
    o.ordered_at DESC NULLS LAST,
    o.order_id DESC NULLS LAST;
~~~

**Đáp án:** An 1003, Binh 1005, Chi 1007, Dung NULL.

### Bài 7: Vì sao An có thể nhận 1002 nếu thiếu order_id DESC?

**Đáp án:** 1002 và 1003 có cùng thời điểm. `ORDER BY customer_id, ordered_at DESC` không phân định hai hàng; PostgreSQL không cam kết chọn một hàng cụ thể. Thêm `order_id DESC` để chọn 1003.

### Bài 8: Chọn đơn tiền cao nhất cho từng khách hàng

~~~sql
SELECT DISTINCT ON (customer_id)
    customer_id, order_id, total
FROM distinct_lab.orders
ORDER BY customer_id, total DESC, order_id DESC;
~~~

**Đáp án:** An 1003 (150.00), Binh 1005 (300.00), Chi 1007 (75.00).

### Bài 9: Mỗi khách hàng và trạng thái, một đơn mới nhất

~~~sql
SELECT DISTINCT ON (customer_id, status)
    customer_id, status, order_id, ordered_at
FROM distinct_lab.orders
ORDER BY
    customer_id,
    status,
    ordered_at DESC,
    order_id DESC;
~~~

**Đáp án:** Năm nhóm: (1, paid) 1003; (1, pending) 1002; (2, cancelled) 1005; (2, paid) 1004; (3, paid) 1007.

### Bài 10: Hai đơn mới nhất mỗi khách hàng

~~~sql
WITH ranked AS (
    SELECT
        customer_id,
        order_id,
        ROW_NUMBER() OVER (
            PARTITION BY customer_id
            ORDER BY ordered_at DESC, order_id DESC
        ) AS rn
    FROM distinct_lab.orders
)
SELECT customer_id, order_id, rn
FROM ranked
WHERE rn <= 2
ORDER BY customer_id, rn;
~~~

**Đáp án:** An 1003 và 1002; Binh 1005 và 1004; Chi 1007 và 1006.

### Bài 11: Lấy mọi đơn đồng thời gian mới nhất

~~~sql
WITH ranked AS (
    SELECT
        customer_id,
        order_id,
        RANK() OVER (
            PARTITION BY customer_id
            ORDER BY ordered_at DESC
        ) AS rnk
    FROM distinct_lab.orders
)
SELECT customer_id, order_id
FROM ranked
WHERE rnk = 1
ORDER BY customer_id, order_id;
~~~

**Đáp án:** An có **1002 và 1003**; Binh có 1005; Chi có 1007. Đó là bài toán **mọi hàng đồng hạng**, không phải `DISTINCT ON` một hàng.

### Bài 12: Vì sao JOIN ra hai dòng cho đơn 1001?

~~~sql
SELECT o.order_id, t.tag
FROM distinct_lab.orders AS o
JOIN distinct_lab.order_tags AS t
    ON t.order_id = o.order_id
WHERE o.order_id = 1001
ORDER BY t.tag;
~~~

**Đáp án:** Vì 1001 có hai tag `gift` và `web`. Đây là hai liên kết khác nhau, không phải hai đơn hàng bị lưu trùng. Nếu chỉ muốn kiểm tra đơn có tag, dùng `EXISTS`; nếu muốn danh sách tag, giữ cả hai dòng.

### Bài 13: Chọn đại diện rồi sắp theo thời gian toàn cục

~~~sql
SELECT customer_id, order_id, ordered_at
FROM (
    SELECT DISTINCT ON (customer_id)
        customer_id, order_id, ordered_at
    FROM distinct_lab.orders
    ORDER BY customer_id, ordered_at DESC, order_id DESC
) AS latest
ORDER BY ordered_at DESC, order_id DESC;
~~~

**Đáp án:** Thứ tự đại diện là Chi 1007, An 1003, Binh 1005.

## 28. Quy trình chọn kỹ thuật trong dự án thật

Khi nhận yêu cầu “loại trùng”, “lấy bản ghi mới nhất” hoặc “mỗi nhóm chỉ một hàng”, hãy làm theo trình tự:

1. **Xác định đơn vị kết quả:** khách hàng, đơn hàng, sản phẩm, hay một cặp khóa?
2. **Xác định cần cột nào:** chỉ khóa nhóm hay đầy đủ cột của một bản ghi đại diện?
3. **Xác định nhóm:** một cột hay tổ hợp nhiều cột, có chuẩn hóa chữ/giá trị NULL không?
4. **Xác định quy tắc ưu tiên:** mới nhất, giá trị cao nhất, trạng thái ưu tiên, hay một chuỗi tiêu chí?
5. **Thêm tie-breaker có tính duy nhất:** ID hoặc một khóa có thể phân định các hàng đồng hạng.
6. **Xác định thứ tự lọc:** lọc ứng viên trước chọn đại diện hay lọc đại diện sau khi chọn?
7. **Xác định có cần nhóm rỗng:** nếu có, bắt đầu từ bảng cha và dùng `LEFT JOIN` hoặc `LATERAL`.
8. **Xác định số hàng mỗi nhóm:** một hàng dùng `DISTINCT ON`/`ROW_NUMBER=1`; nhiều hàng dùng window function; mọi hàng đồng hạng dùng `RANK`.
9. **Xem lại JOIN:** nhiều hàng có thể do quan hệ 1:N hợp lệ, không phải dữ liệu trùng cần che.
10. **Quan sát kế hoạch:** thử chỉ mục đúng thứ tự, so sánh `EXPLAIN` trên dữ liệu đại diện.
11. **Kiểm chứng bằng dữ liệu biên:** nhóm không có hàng, cùng timestamp, NULL, nhóm có một hàng, dữ liệu nhiều trạng thái.
12. **Ghi rõ hợp đồng kết quả:** để người đọc SQL hiểu “hàng đại diện” được chọn theo quy tắc nào.

Một truy vấn `DISTINCT ON` ngắn nhưng thiếu quy tắc ưu tiên có thể trả một hàng hợp lệ về mặt cú pháp mà **sai về nghiệp vụ**. Độ tin cậy đến từ cách định nghĩa nhóm và thứ tự lựa chọn.

## 29. Tài liệu tham khảo chính thức

- [PostgreSQL — SELECT](https://www.postgresql.org/docs/current/sql-select.html): cú pháp `DISTINCT`, `DISTINCT ON` và quy tắc `ORDER BY`.
- [PostgreSQL — Window Functions](https://www.postgresql.org/docs/current/tutorial-window.html): giới thiệu `ROW_NUMBER`, `RANK` và `PARTITION BY`.
- [PostgreSQL — Window Function Reference](https://www.postgresql.org/docs/current/functions-window.html): danh sách và ngữ nghĩa các hàm cửa sổ.
- [PostgreSQL — EXPLAIN](https://www.postgresql.org/docs/current/sql-explain.html): cách đọc và đo execution plan.
- [PostgreSQL — Indexes and ORDER BY](https://www.postgresql.org/docs/current/indexes-ordering.html): liên hệ giữa B-tree index và thứ tự truy vấn.

Khi chạy trên một major version cụ thể, nên đọc tài liệu tương ứng với phiên bản server đang dùng, vì cú pháp và khả năng tối ưu có thể thay đổi qua các phiên bản.

## 30. Tổng kết

| Công cụ | Loại kết quả | Điểm cần nhớ |
| --- | --- | --- |
| `SELECT DISTINCT` | Mỗi tổ hợp biểu thức được chọn xuất hiện một lần | Toàn bộ cột/biểu thức trong SELECT quyết định trùng |
| `COUNT(DISTINCT x)` | Một số lượng giá trị `x` khác nhau | Bỏ qua NULL khi x là một biểu thức |
| `DISTINCT ON (key)` | Một **hàng đại diện** cho mỗi khóa nhóm | `ORDER BY` bắt đầu bằng khóa nhóm và phải có tiêu chí ưu tiên |
| `GROUP BY` + aggregate | Một hàng tổng hợp cho mỗi nhóm | Không tự xác định toàn bộ hàng gốc của `MAX`/`MIN` |
| `ROW_NUMBER()` | Mỗi hàng có thứ hạng tuần tự trong nhóm | Dùng được cho top N và lọc `rn = 1` |
| `RANK()` | Các hàng đồng hạng có cùng thứ hạng | Phù hợp khi muốn giữ tất cả hàng đạt hạng nhất |
| `EXISTS` | Chỉ kiểm tra tồn tại quan hệ | Tránh tạo nhiều hàng JOIN chỉ để rồi loại trùng |

**`DISTINCT` trả những giá trị duy nhất; `DISTINCT ON` trả hàng đại diện; `GROUP BY` trả số liệu tổng hợp; hàm cửa sổ trả thứ hạng.**

Trong PostgreSQL, để chọn đại diện đáng tin cậy, hãy luôn làm rõ **nhóm theo gì, ưu tiên hàng nào, xử lý hòa như thế nào và lọc trước hay sau khi chọn**. Khi bốn điều này được định nghĩa rõ, câu SQL vừa dễ đọc vừa cho kết quả nhất quán với yêu cầu nghiệp vụ.
