# Inline view và phân tách các bước xử lý truy vấn trong Oracle

Khi một báo cáo cần nối nhiều bảng, lọc theo kết quả tổng hợp, chọn dòng mới nhất hoặc tính toán ở nhiều mức chi tiết, một câu `SELECT` duy nhất có thể trở nên khó đọc và dễ sai. Ta thường cần chia truy vấn thành những bước có ý nghĩa: tính tổng dòng hàng theo đơn, ghép kết quả với đơn hàng, tổng hợp theo khách hàng, rồi mới nối với danh mục khách hàng để trình bày.

Oracle SQL hỗ trợ cách tổ chức đó bằng **inline view** (truy vấn con trong mệnh đề `FROM`), **subquery factoring** với `WITH`/CTE, các truy vấn con ở những vị trí khác và hàm phân tích. Các kỹ thuật này giúp tách một bài toán lớn thành những tập kết quả trung gian có grain rõ ràng, dễ kiểm tra và tái sử dụng.

Điều quan trọng là hiểu ranh giới giữa các bước theo **ngữ nghĩa truy vấn**. Inline view không mặc nhiên là bảng tạm được ghi xuống đĩa, cũng không buộc Oracle phải thực thi vật lý đúng thứ tự ta viết. Optimizer có thể biến đổi hoặc gộp các query block khi vẫn giữ nguyên kết quả. Vì vậy, ta dùng cấu trúc truy vấn để diễn đạt ý định và kiểm chứng kết quả; khi cần biết cách chạy thực tế, hãy xem execution plan.

## 1. Inline view là gì?

**Inline view** là một câu `SELECT` được đặt trong mệnh đề `FROM` của một câu SQL khác. Kết quả của câu SELECT bên trong được dùng như một nguồn dòng (row source) để truy vấn bên ngoài đọc, lọc, nối hoặc tổng hợp tiếp.

Cú pháp tổng quát:

~~~sql
SELECT ...
FROM (
    SELECT ...
    FROM ...
    WHERE ...
    GROUP BY ...
) result_alias
WHERE ...;
~~~

Ví dụ, trước tiên tính tổng tiền theo khách hàng, sau đó chỉ hiển thị khách có tổng từ 200 trở lên:

~~~sql
SELECT
    customer_totals.customer_id,
    customer_totals.total_amount
FROM (
    SELECT
        customer_id,
        SUM(amount) AS total_amount
    FROM lab_jq_order
    WHERE order_status = 'PAID'
    GROUP BY customer_id
) customer_totals
WHERE customer_totals.total_amount >= 200
ORDER BY customer_totals.total_amount DESC;
~~~

Trong câu lệnh này:

- Câu SELECT bên trong tạo một dòng cho mỗi khách có đơn PAID, với tổng tiền tương ứng.
- `customer_totals` là bí danh của inline view.
- Câu SELECT bên ngoài đọc các cột do inline view trả về.
- `WHERE` bên ngoài có thể lọc `TOTAL_AMOUNT` vì lúc này nó đã là một cột của tập kết quả trung gian.

Đây là một cách diễn đạt tương đương về mục tiêu với `GROUP BY ... HAVING SUM(amount) >= 200`. Inline view đặc biệt hữu ích khi kết quả trung gian còn cần được JOIN với bảng khác, tính thêm biểu thức, hoặc dùng ở nhiều bước tiếp theo.

### 1.1. Inline view không phải bảng vật lý

Inline view chỉ là một **query block** trong câu SQL. Ta không cần `CREATE TABLE` để tạo nó, và kết quả không tự tồn tại sau khi câu SQL kết thúc.

| Đặc điểm | Inline view | Bảng vật lý |
|---|---|---|
| Cách tạo | Viết SELECT trong FROM | CREATE TABLE / INSERT |
| Có tên độc lập trong schema? | Không; có alias trong câu truy vấn | Có tên đối tượng |
| Lưu dữ liệu riêng? | Không mặc nhiên | Có segment hoặc cơ chế lưu trữ tương ứng |
| Tồn tại sau câu SELECT? | Không | Có |
| Có thể JOIN tiếp? | Có | Có |
| Có thể có index riêng? | Không tạo index trực tiếp trên inline view thông thường | Có thể tạo index theo thiết kế |
| Dùng để chia bước logic? | Có | Có, nhưng phải quản lý dữ liệu và vòng đời bảng |

Không nên gọi inline view là “bảng tạm” nếu điều đó khiến người đọc nghĩ Oracle luôn ghi dữ liệu trung gian xuống storage. Optimizer có thể gộp inline view vào truy vấn ngoài hoặc chọn một kế hoạch thực thi khác.

## 2. Chuẩn bị bộ dữ liệu bán hàng để thực hành

Ta dùng bốn bảng:

- `LAB_JQ_CUSTOMER`: khách hàng và cờ hoạt động.
- `LAB_JQ_ORDER`: đơn hàng, trạng thái và ngày tạo.
- `LAB_JQ_ORDER_ITEM`: các dòng sản phẩm trong từng đơn.
- `LAB_JQ_PAYMENT`: các lần thanh toán của đơn.

Bộ dữ liệu được thiết kế để có một đơn chứa nhiều dòng hàng và nhiều lần thanh toán. Đây là trường hợp quan trọng để thấy vì sao JOIN nhiều bảng chi tiết trực tiếp có thể nhân dòng và làm sai tổng.

### 2.1. Tạo bảng

Chạy trong schema lab thuộc PDB thực hành. Nếu các bảng cùng tên đã tồn tại, hãy chọn tên khác hoặc một schema lab mới; không ghi đè bảng đang được sử dụng.

~~~sql
CREATE TABLE lab_jq_customer (
    customer_id   NUMBER(5) PRIMARY KEY,
    customer_name VARCHAR2(60 CHAR) NOT NULL,
    active_flag   CHAR(1 CHAR) NOT NULL,
    CONSTRAINT ck_lab_jq_customer_active
      CHECK (active_flag IN ('Y', 'N'))
);

CREATE TABLE lab_jq_order (
    order_id     NUMBER(6) PRIMARY KEY,
    customer_id  NUMBER(5) NOT NULL,
    order_status VARCHAR2(20 CHAR) NOT NULL,
    order_date   DATE NOT NULL,
    CONSTRAINT fk_lab_jq_order_customer
      FOREIGN KEY (customer_id)
      REFERENCES lab_jq_customer (customer_id),
    CONSTRAINT ck_lab_jq_order_status
      CHECK (order_status IN ('PAID', 'CANCELLED', 'PENDING'))
);

CREATE TABLE lab_jq_order_item (
    order_id   NUMBER(6) NOT NULL,
    line_no    NUMBER(4) NOT NULL,
    product_code VARCHAR2(30 CHAR) NOT NULL,
    quantity   NUMBER(8,0) NOT NULL,
    unit_price NUMBER(12,2) NOT NULL,
    CONSTRAINT pk_lab_jq_order_item
      PRIMARY KEY (order_id, line_no),
    CONSTRAINT fk_lab_jq_item_order
      FOREIGN KEY (order_id)
      REFERENCES lab_jq_order (order_id),
    CONSTRAINT ck_lab_jq_item_quantity
      CHECK (quantity > 0),
    CONSTRAINT ck_lab_jq_item_price
      CHECK (unit_price >= 0)
);

CREATE TABLE lab_jq_payment (
    payment_id NUMBER(6) PRIMARY KEY,
    order_id   NUMBER(6) NOT NULL,
    paid_amount NUMBER(12,2) NOT NULL,
    paid_at    DATE NOT NULL,
    CONSTRAINT fk_lab_jq_payment_order
      FOREIGN KEY (order_id)
      REFERENCES lab_jq_order (order_id),
    CONSTRAINT ck_lab_jq_payment_amount
      CHECK (paid_amount >= 0)
);
~~~

Khóa chính của `LAB_JQ_ORDER_ITEM` là `(ORDER_ID, LINE_NO)`: mỗi đơn có thể có nhiều dòng, nhưng số dòng không trùng trong cùng một đơn. Bảng thanh toán dùng `PAYMENT_ID` vì một đơn có thể có nhiều lần thanh toán.

### 2.2. Chèn khách hàng và đơn hàng

~~~sql
INSERT INTO lab_jq_customer VALUES (1, 'An',   'Y');
INSERT INTO lab_jq_customer VALUES (2, 'Binh', 'Y');
INSERT INTO lab_jq_customer VALUES (3, 'Chi',  'N');
INSERT INTO lab_jq_customer VALUES (4, 'Dung', 'Y');

INSERT INTO lab_jq_order VALUES
  (101, 1, 'PAID',      DATE '2026-01-03');
INSERT INTO lab_jq_order VALUES
  (102, 1, 'PAID',      DATE '2026-01-10');
INSERT INTO lab_jq_order VALUES
  (103, 1, 'CANCELLED', DATE '2026-01-11');
INSERT INTO lab_jq_order VALUES
  (201, 2, 'PAID',      DATE '2026-01-04');
INSERT INTO lab_jq_order VALUES
  (202, 2, 'PAID',      DATE '2026-01-25');
INSERT INTO lab_jq_order VALUES
  (301, 3, 'PAID',      DATE '2026-01-15');
INSERT INTO lab_jq_order VALUES
  (401, 4, 'PENDING',   DATE '2026-01-20');
~~~

### 2.3. Chèn dòng hàng

~~~sql
-- Đơn 101 có hai dòng: 2 x 50 và 1 x 30, tổng 130.
INSERT INTO lab_jq_order_item VALUES (101, 1, 'SKU-A', 2, 50);
INSERT INTO lab_jq_order_item VALUES (101, 2, 'SKU-B', 1, 30);

INSERT INTO lab_jq_order_item VALUES (102, 1, 'SKU-C', 1, 80);
INSERT INTO lab_jq_order_item VALUES (103, 1, 'SKU-X', 1, 500);
INSERT INTO lab_jq_order_item VALUES (201, 1, 'SKU-D', 1, 100);
INSERT INTO lab_jq_order_item VALUES (202, 1, 'SKU-E', 3, 40);
INSERT INTO lab_jq_order_item VALUES (301, 1, 'SKU-F', 2, 150);
INSERT INTO lab_jq_order_item VALUES (401, 1, 'SKU-G', 1, 60);
~~~

### 2.4. Chèn lần thanh toán

~~~sql
-- Đơn 101 được thanh toán thành hai lần: 80 + 50 = 130.
INSERT INTO lab_jq_payment VALUES
  (1001, 101, 80, DATE '2026-01-03');
INSERT INTO lab_jq_payment VALUES
  (1002, 101, 50, DATE '2026-01-04');

INSERT INTO lab_jq_payment VALUES
  (1003, 102, 80, DATE '2026-01-10');
INSERT INTO lab_jq_payment VALUES
  (1004, 201, 100, DATE '2026-01-04');
INSERT INTO lab_jq_payment VALUES
  (1005, 202, 120, DATE '2026-01-25');
INSERT INTO lab_jq_payment VALUES
  (1006, 301, 300, DATE '2026-01-15');

COMMIT;
~~~

Đơn `101` có hai dòng hàng và hai lần thanh toán. Các đơn `102`, `201`, `202`, `301` có một dòng hàng và một lần thanh toán. Đơn `103` có dòng hàng nhưng đã hủy; đơn `401` đang chờ và chưa có thanh toán.

### 2.5. Kiểm tra dữ liệu nguồn

~~~sql
SELECT * FROM lab_jq_customer ORDER BY customer_id;
SELECT * FROM lab_jq_order ORDER BY order_id;
SELECT * FROM lab_jq_order_item ORDER BY order_id, line_no;
SELECT * FROM lab_jq_payment ORDER BY order_id, payment_id;
~~~

Tổng dòng hàng theo đơn tính bằng tay:

| ORDER_ID | Phép tính | ORDER_TOTAL |
|---:|---|---:|
| 101 | 2 × 50 + 1 × 30 | 130 |
| 102 | 1 × 80 | 80 |
| 103 | 1 × 500 | 500 |
| 201 | 1 × 100 | 100 |
| 202 | 3 × 40 | 120 |
| 301 | 2 × 150 | 300 |
| 401 | 1 × 60 | 60 |

Tổng thanh toán theo đơn:

| ORDER_ID | PAYMENT_ID | Các lần thanh toán | PAID_TOTAL |
|---:|---|---|---:|
| 101 | 1001, 1002 | 80 + 50 | 130 |
| 102 | 1003 | 80 | 80 |
| 201 | 1004 | 100 | 100 |
| 202 | 1005 | 120 | 120 |
| 301 | 1006 | 300 | 300 |

## 3. Bắt đầu bằng một inline view đơn giản

Giả sử cần tìm những khách có ít nhất hai đơn hàng. Ta phải đếm đơn theo từng khách trước, rồi mới lọc kết quả đếm.

~~~sql
SELECT
    customer_order_counts.customer_id,
    customer_order_counts.order_count
FROM (
    SELECT
        customer_id,
        COUNT(*) AS order_count
    FROM lab_jq_order
    GROUP BY customer_id
) customer_order_counts
WHERE customer_order_counts.order_count >= 2
ORDER BY customer_order_counts.customer_id;
~~~

Query block bên trong tạo tập trung gian:

| CUSTOMER_ID | ORDER_COUNT |
|---:|---:|
| 1 | 3 |
| 2 | 2 |
| 3 | 1 |
| 4 | 1 |

Query block bên ngoài lọc `ORDER_COUNT >= 2`, nên kết quả cuối có khách 1 và 2.

Ở ví dụ này, `HAVING COUNT(*) >= 2` có thể viết ngắn hơn:

~~~sql
SELECT customer_id, COUNT(*) AS order_count
FROM lab_jq_order
GROUP BY customer_id
HAVING COUNT(*) >= 2
ORDER BY customer_id;
~~~

Vậy tại sao vẫn dùng inline view? Vì sau khi đã tạo kết quả trung gian, ta có thể:

- JOIN nó với bảng khách hàng.
- Tính tiếp các biểu thức dựa trên số đếm/tổng.
- Lọc theo một cột aggregate như cột thông thường ở query ngoài.
- Kết hợp với một tập kết quả khác đã được tổng hợp.
- Tách các bước phức tạp thành những phần có thể chạy và kiểm tra riêng.

## 4. Inline view tính tổng dòng hàng theo từng đơn

`LAB_JQ_ORDER_ITEM` có grain là **một dòng sản phẩm trong một đơn**, còn báo cáo đơn hàng cần grain **một dòng cho mỗi đơn**. Inline view có thể chuyển mức chi tiết đó:

~~~sql
SELECT
    item_totals.order_id,
    item_totals.order_total
FROM (
    SELECT
        order_id,
        SUM(quantity * unit_price) AS order_total
    FROM lab_jq_order_item
    GROUP BY order_id
) item_totals
ORDER BY item_totals.order_id;
~~~

Kết quả:

| ORDER_ID | ORDER_TOTAL |
|---:|---:|
| 101 | 130 |
| 102 | 80 |
| 103 | 500 |
| 201 | 100 |
| 202 | 120 |
| 301 | 300 |
| 401 | 60 |

Ta đã chuyển từ nhiều dòng hàng sang một dòng tổng hợp cho mỗi đơn. Sau bước này, `ITEM_TOTALS.ORDER_ID` có tối đa một dòng cho mỗi đơn trong tập kết quả. Đây là **grain mới** của inline view.

### 4.1. Lọc đơn có tổng hàng lớn

Vì `ORDER_TOTAL` là kết quả aggregate trong query block bên trong, query bên ngoài có thể lọc nó:

~~~sql
SELECT
    item_totals.order_id,
    item_totals.order_total
FROM (
    SELECT order_id,
           SUM(quantity * unit_price) AS order_total
    FROM lab_jq_order_item
    GROUP BY order_id
) item_totals
WHERE item_totals.order_total >= 120
ORDER BY item_totals.order_total DESC;
~~~

Kết quả gồm đơn 103 (500), 301 (300), 101 (130), 202 (120). Nếu điều kiện cần áp dụng cho **từng dòng hàng**, phải đặt trong query block bên trong trước khi `GROUP BY`; nếu áp dụng cho **tổng của đơn**, đặt ở ngoài như ví dụ này.

## 5. Kết hợp inline view với JOIN

Yêu cầu: hiển thị mã đơn, khách hàng và tổng giá trị dòng hàng của từng đơn.

~~~sql
SELECT
    o.order_id,
    c.customer_name,
    item_totals.order_total
FROM lab_jq_order o
JOIN lab_jq_customer c
  ON c.customer_id = o.customer_id
JOIN (
    SELECT
        order_id,
        SUM(quantity * unit_price) AS order_total
    FROM lab_jq_order_item
    GROUP BY order_id
) item_totals
  ON item_totals.order_id = o.order_id
ORDER BY o.order_id;
~~~

Inline view `ITEM_TOTALS` được JOIN như một nguồn dòng thông thường. Nó chỉ cung cấp `ORDER_ID` và `ORDER_TOTAL`; bảng đơn hàng cung cấp trạng thái/ngày/khách; bảng khách hàng cung cấp tên.

Kết quả dự kiến:

| ORDER_ID | CUSTOMER_NAME | ORDER_TOTAL |
|---:|---|---:|
| 101 | An | 130 |
| 102 | An | 80 |
| 103 | An | 500 |
| 201 | Binh | 100 |
| 202 | Binh | 120 |
| 301 | Chi | 300 |
| 401 | Dung | 60 |

Đây là một cách chia bước hữu ích: **tổng hợp dòng hàng theo đơn trước**, rồi nối với thông tin đơn và khách. Nếu cần giữ đơn không có dòng hàng, đổi JOIN với inline view thành LEFT JOIN; khi đó `ORDER_TOTAL` có thể NULL và cần quyết định cách hiển thị.

## 6. Tách nhiều bước bằng các inline view lồng nhau

Yêu cầu báo cáo:

> Trong tháng 1/2026, liệt kê khách hàng đang hoạt động, số đơn đã thanh toán và tổng giá trị hàng của các đơn đó. Khách không có đơn PAID vẫn phải xuất hiện với số lượng và tổng bằng 0.

Ta chia thành ba bước:

1. Tính tổng dòng hàng theo từng đơn.
2. Lọc đơn PAID trong tháng 1, rồi tổng hợp số đơn và tổng giá trị theo khách.
3. LEFT JOIN kết quả đó với khách hàng đang hoạt động.

Truy vấn hoàn chỉnh bằng inline view lồng nhau:

~~~sql
SELECT
    c.customer_id,
    c.customer_name,
    NVL(monthly.paid_order_count, 0) AS paid_order_count,
    NVL(monthly.paid_order_total, 0) AS paid_order_total
FROM lab_jq_customer c
LEFT JOIN (
    SELECT
        o.customer_id,
        COUNT(*) AS paid_order_count,
        SUM(item_totals.order_total) AS paid_order_total
    FROM lab_jq_order o
    JOIN (
        SELECT
            order_id,
            SUM(quantity * unit_price) AS order_total
        FROM lab_jq_order_item
        GROUP BY order_id
    ) item_totals
      ON item_totals.order_id = o.order_id
    WHERE o.order_status = 'PAID'
      AND o.order_date >= DATE '2026-01-01'
      AND o.order_date <  DATE '2026-02-01'
    GROUP BY o.customer_id
) monthly
  ON monthly.customer_id = c.customer_id
WHERE c.active_flag = 'Y'
ORDER BY paid_order_total DESC, c.customer_id;
~~~

### 6.1. Kiểm tra bước 1: tổng dòng hàng theo đơn

Query block:

~~~sql
SELECT
    order_id,
    SUM(quantity * unit_price) AS order_total
FROM lab_jq_order_item
GROUP BY order_id;
~~~

Kết quả là một dòng cho mỗi `ORDER_ID`, như bảng ở phần 4. Đây là mức chi tiết cần thiết để cộng giá trị đơn mà không bị lặp theo từng dòng sản phẩm.

### 6.2. Kiểm tra bước 2: tổng hợp đơn PAID theo khách

~~~sql
SELECT
    o.customer_id,
    COUNT(*) AS paid_order_count,
    SUM(item_totals.order_total) AS paid_order_total
FROM lab_jq_order o
JOIN (
    SELECT order_id,
           SUM(quantity * unit_price) AS order_total
    FROM lab_jq_order_item
    GROUP BY order_id
) item_totals
  ON item_totals.order_id = o.order_id
WHERE o.order_status = 'PAID'
  AND o.order_date >= DATE '2026-01-01'
  AND o.order_date <  DATE '2026-02-01'
GROUP BY o.customer_id
ORDER BY o.customer_id;
~~~

Kết quả:

| CUSTOMER_ID | PAID_ORDER_COUNT | PAID_ORDER_TOTAL |
|---:|---:|---:|
| 1 | 2 | 210 |
| 2 | 2 | 220 |
| 3 | 1 | 300 |

Chi có đơn PAID nhưng đang inactive. Dung không có đơn PAID nên không xuất hiện trong tập tổng hợp này.

### 6.3. Kiểm tra bước 3: giữ mọi khách active

Query ngoài lấy `LAB_JQ_CUSTOMER` làm bảng trái và LEFT JOIN với kết quả tổng hợp:

| CUSTOMER_ID | CUSTOMER_NAME | PAID_ORDER_COUNT | PAID_ORDER_TOTAL |
|---:|---|---:|---:|
| 2 | Binh | 2 | 220 |
| 1 | An | 2 | 210 |
| 4 | Dung | 0 | 0 |

Chi bị loại bởi `WHERE c.active_flag = 'Y'`. Dung vẫn có mặt nhờ LEFT JOIN; hai cột tổng hợp bên phải là NULL nên `NVL` hiển thị 0.

Điều đáng chú ý là mỗi bước có một **grain riêng**:

| Bước | Grain | Một dòng đại diện cho |
|---|---|---|
| `ITEM_TOTALS` | `ORDER_ID` | Một đơn và tổng giá trị các dòng hàng |
| `MONTHLY` | `CUSTOMER_ID` | Một khách và số/tổng đơn PAID trong kỳ |
| Query ngoài | `CUSTOMER_ID` | Một khách active trong báo cáo, kể cả không có đơn |

Khi grain của mỗi bước được xác định, ta dễ kiểm tra việc JOIN có làm nhân dòng hay không.

## 7. Viết lại bằng WITH (CTE) để đặt tên từng bước

Một câu truy vấn lồng nhiều lớp có thể khó đọc vì phải đếm dấu ngoặc và tìm alias. Oracle hỗ trợ `WITH` để đặt tên cho các query block, thường gọi là **common table expression (CTE)** hoặc subquery factoring.

Truy vấn ở phần trước có thể viết lại:

~~~sql
WITH item_totals AS (
    SELECT
        order_id,
        SUM(quantity * unit_price) AS order_total
    FROM lab_jq_order_item
    GROUP BY order_id
),
monthly AS (
    SELECT
        o.customer_id,
        COUNT(*) AS paid_order_count,
        SUM(it.order_total) AS paid_order_total
    FROM lab_jq_order o
    JOIN item_totals it
      ON it.order_id = o.order_id
    WHERE o.order_status = 'PAID'
      AND o.order_date >= DATE '2026-01-01'
      AND o.order_date <  DATE '2026-02-01'
    GROUP BY o.customer_id
)
SELECT
    c.customer_id,
    c.customer_name,
    NVL(m.paid_order_count, 0) AS paid_order_count,
    NVL(m.paid_order_total, 0) AS paid_order_total
FROM lab_jq_customer c
LEFT JOIN monthly m
  ON m.customer_id = c.customer_id
WHERE c.active_flag = 'Y'
ORDER BY paid_order_total DESC, c.customer_id;
~~~

### 7.1. Cách đọc CTE

Các biểu thức sau `WITH` được khai báo theo tên:

- `ITEM_TOTALS`: tổng giá trị dòng hàng theo đơn.
- `MONTHLY`: tổng hợp các đơn PAID trong kỳ theo khách.

SELECT cuối sử dụng hai nguồn đó để trả báo cáo. Cách đặt tên cho từng bước giúp người đọc thấy cấu trúc nghiệp vụ mà không phải đi sâu qua nhiều lớp ngoặc.

### 7.2. Inline view và CTE khác nhau ra sao?

| Tiêu chí | Inline view | CTE (`WITH`) |
|---|---|---|
| Vị trí khai báo | Bên trong `FROM`/`JOIN` | Ở đầu câu SQL, sau `WITH` |
| Cách đặt tên | Alias ngay sau dấu ngoặc đóng | Tên CTE trong phần khai báo |
| Tái sử dụng trong cùng statement | Muốn dùng lại thường phải lặp query block | Có thể tham chiếu CTE nhiều lần theo phạm vi statement |
| Đọc truy vấn nhiều bước | Có thể lồng sâu | Thường dễ đặt tên từng bước |
| Lưu kết quả vật lý? | Không mặc nhiên | Không mặc nhiên |
| Bảo đảm materialize? | Không | Không |

CTE không phải bảng tạm vật lý chỉ vì có tên. Oracle có thể inline hoặc biến đổi CTE tùy optimizer và ngữ cảnh. Cú pháp `WITH` giúp tổ chức SQL; nó không mặc nhiên tạo một điểm lưu trữ hay buộc database tính CTE đúng một lần.

### 7.3. Dùng lại một CTE

Nếu một tập tổng hợp được tham chiếu nhiều lần trong cùng statement, CTE giúp tránh lặp lại phần mô tả:

~~~sql
WITH item_totals AS (
    SELECT order_id,
           SUM(quantity * unit_price) AS order_total
    FROM lab_jq_order_item
    GROUP BY order_id
)
SELECT
    (SELECT COUNT(*) FROM item_totals) AS orders_with_items,
    (SELECT SUM(order_total) FROM item_totals) AS all_item_total
FROM dual;
~~~

Ở đây `ITEM_TOTALS` được tham chiếu bởi hai scalar subquery trong cùng câu lệnh. Việc Oracle thực thi/biến đổi ra sao cần xem plan; không nên kết luận chắc chắn rằng CTE được tính vật lý đúng một lần chỉ vì nó được khai báo một lần.

## 8. Phân tách truy vấn để tránh nhân dòng khi JOIN nhiều bảng chi tiết

Đây là một trong những lý do quan trọng nhất để dùng inline view.

Đơn 101 có:

- Hai dòng hàng: 130 tổng cộng.
- Hai lần thanh toán: 130 tổng cộng.

Nếu JOIN trực tiếp bảng dòng hàng và bảng thanh toán theo `ORDER_ID`, mỗi dòng hàng sẽ ghép với mọi lần thanh toán của đơn:

~~~sql
SELECT
    o.order_id,
    SUM(i.quantity * i.unit_price) AS item_total,
    SUM(p.paid_amount) AS payment_total
FROM lab_jq_order o
JOIN lab_jq_order_item i
  ON i.order_id = o.order_id
JOIN lab_jq_payment p
  ON p.order_id = o.order_id
WHERE o.order_id = 101
GROUP BY o.order_id;
~~~

Đơn 101 có 2 item × 2 payment = **4 dòng trung gian**:

| ITEM | Giá trị dòng | PAYMENT | Giá trị thanh toán |
|---|---:|---|---:|
| SKU-A | 100 | Payment 1001 | 80 |
| SKU-A | 100 | Payment 1002 | 50 |
| SKU-B | 30 | Payment 1001 | 80 |
| SKU-B | 30 | Payment 1002 | 50 |

Kết quả sai:

| ORDER_ID | ITEM_TOTAL | PAYMENT_TOTAL |
|---:|---:|---:|
| 101 | 260 | 260 |

Tổng hàng thực là 130, tổng thanh toán thực là 130. Cả hai bị nhân đôi vì mỗi dòng hàng xuất hiện hai lần và mỗi payment xuất hiện hai lần.

### 8.1. Tổng hợp từng phía trước khi JOIN

Ta tạo hai tập trung gian, mỗi tập chỉ có một dòng cho mỗi đơn:

~~~sql
WITH item_totals AS (
    SELECT
        order_id,
        SUM(quantity * unit_price) AS item_total
    FROM lab_jq_order_item
    GROUP BY order_id
),
payment_totals AS (
    SELECT
        order_id,
        SUM(paid_amount) AS payment_total
    FROM lab_jq_payment
    GROUP BY order_id
)
SELECT
    o.order_id,
    it.item_total,
    NVL(pt.payment_total, 0) AS payment_total
FROM lab_jq_order o
LEFT JOIN item_totals it
  ON it.order_id = o.order_id
LEFT JOIN payment_totals pt
  ON pt.order_id = o.order_id
WHERE o.order_id = 101;
~~~

Kết quả:

| ORDER_ID | ITEM_TOTAL | PAYMENT_TOTAL |
|---:|---:|---:|
| 101 | 130 | 130 |

Mỗi inline view/CTE đã được tổng hợp về grain `ORDER_ID`, nên JOIN hai tập đó không còn nhân dòng theo số item và số payment.

### 8.2. Quy tắc grain trước khi nối

Trước mỗi JOIN, hãy trả lời:

1. Một dòng ở bảng trái đại diện cho điều gì?
2. Một dòng ở bảng phải đại diện cho điều gì?
3. Mỗi khóa JOIN có thể khớp bao nhiêu dòng ở mỗi phía?
4. Sau JOIN, một dòng trung gian đại diện cho điều gì?
5. Aggregate đang tính trên dòng gốc hay trên dòng đã bị nhân?

Nếu hai bảng đều có nhiều dòng cho một `ORDER_ID`, JOIN thô thường tạo tích số dòng giữa hai phía. Tổng hợp từng phía trước JOIN là một cách chuẩn để đưa cả hai về cùng grain. Không dùng `DISTINCT` để chữa lỗi fan-out sau khi đã nhân dòng; nó có thể che triệu chứng và làm mất các dòng hợp lệ.

## 9. Inline view kết hợp hàm phân tích: lấy N đơn mới nhất của mỗi khách

Một bài toán phổ biến: “Mỗi khách, lấy tối đa hai đơn PAID mới nhất.” `GROUP BY MAX(order_date)` chỉ cho biết ngày lớn nhất, nhưng không tự trả đầy đủ `ORDER_ID` của hai đơn mới nhất. Ta dùng `ROW_NUMBER()` trong inline view:

~~~sql
SELECT
    ranked.customer_id,
    ranked.order_id,
    ranked.order_date,
    ranked.order_status
FROM (
    SELECT
        o.customer_id,
        o.order_id,
        o.order_date,
        o.order_status,
        ROW_NUMBER() OVER (
            PARTITION BY o.customer_id
            ORDER BY o.order_date DESC, o.order_id DESC
        ) AS rn
    FROM lab_jq_order o
    WHERE o.order_status = 'PAID'
) ranked
WHERE ranked.rn <= 2
ORDER BY ranked.customer_id, ranked.rn;
~~~

Phân tích:

- Query block bên trong lọc đơn PAID.
- `PARTITION BY customer_id` đánh số độc lập cho từng khách.
- `ORDER BY order_date DESC, order_id DESC` xếp đơn mới nhất trước; `ORDER_ID` là tiêu chí phụ để thứ tự ổn định khi ngày bằng nhau.
- `ROW_NUMBER()` tạo `RN` cho từng dòng trong mỗi partition.
- Query block ngoài lọc `RN <= 2`.

Trong dataset, khách An có hai đơn PAID 101 và 102; Binh có 201 và 202; Chi có 301; Dung không có đơn PAID. Kết quả trả tối đa hai dòng cho mỗi khách có đơn phù hợp.

### 9.1. Vì sao cần inline view bên ngoài?

Trong cùng query block, không thể đặt `WHERE rn <= 2` để lọc alias `RN` vừa được tạo ở select list. `WHERE` được xử lý logic trước `SELECT`; hàm phân tích cũng được tính ở giai đoạn sau WHERE/GROUP BY/HAVING. Inline view tạo một query block bên trong có `RN` như một cột đầu ra; query ngoài có thể lọc nó như cột bình thường.

### 9.2. ROW_NUMBER, RANK và DENSE_RANK

| Hàm | Hành vi | Khi dùng |
|---|---|---|
| `ROW_NUMBER()` | Gán số duy nhất theo thứ tự, kể cả khi giá trị sort bằng nhau | Cần tối đa đúng N dòng mỗi nhóm |
| `RANK()` | Các dòng đồng hạng nhận cùng hạng; hạng kế tiếp có thể bị nhảy | Cần đồng hạng và khoảng hạng |
| `DENSE_RANK()` | Các dòng đồng hạng nhận cùng hạng; hạng kế tiếp không bị nhảy | Cần top N mức giá trị, giữ tất cả dòng đồng hạng |

Nếu yêu cầu là “lấy hai đơn mới nhất” thì `ROW_NUMBER() <= 2` là phù hợp. Nếu yêu cầu là “lấy tất cả đơn thuộc hai ngày mới nhất”, cần cân nhắc `DENSE_RANK()` theo ngày, vì nhiều đơn cùng ngày có thể cùng được giữ.

## 10. Phạm vi alias và cột của inline view

Inline view là một query block riêng, vì vậy alias và cột phải được hiểu theo phạm vi.

### 10.1. Đặt alias cho inline view

~~~sql
SELECT x.order_id, x.order_total
FROM (
    SELECT order_id,
           SUM(quantity * unit_price) AS order_total
    FROM lab_jq_order_item
    GROUP BY order_id
) x;
~~~

Alias `X` đại diện cho toàn bộ nguồn dòng bên trong. Dùng alias rõ ràng giúp tránh nhầm cột khi nhiều nguồn có tên giống nhau.

### 10.2. Đặt tên cột đầu ra

Các cột của inline view là những biểu thức trong SELECT bên trong. Biểu thức aggregate nên có alias:

~~~sql
SELECT totals.order_id, totals.order_total
FROM (
    SELECT order_id,
           SUM(quantity * unit_price) AS order_total
    FROM lab_jq_order_item
    GROUP BY order_id
) totals;
~~~

Nếu không đặt tên rõ cho biểu thức, việc tham chiếu ở query ngoài có thể khó đọc hoặc không hợp lệ tùy biểu thức và cú pháp. Hãy đặt alias cho các cột tính toán.

### 10.3. Không truy cập cột không được xuất ra

~~~sql
-- Không hợp lệ: query block bên ngoài không nhìn thấy QUANTITY.
SELECT totals.order_id, totals.quantity
FROM (
    SELECT order_id,
           SUM(quantity * unit_price) AS order_total
    FROM lab_jq_order_item
    GROUP BY order_id
) totals;
~~~

Query block bên trong chỉ xuất `ORDER_ID` và `ORDER_TOTAL`. `QUANTITY` không nằm trong giao diện cột của inline view; query ngoài không thể tham chiếu nó. Nếu cần dữ liệu đó, phải đưa biểu thức/cột phù hợp ra ngoài và xem lại grain.

### 10.4. Tránh tên cột mơ hồ

Khi hai nguồn đều có `ORDER_ID`, nên viết `o.order_id`, `it.order_id` thay vì chỉ `order_id`. Nếu không, Oracle có thể báo `ORA-00918: column ambiguously defined`. Tương tự, alias bảng ngoài và alias cột trong inline view nên có tên phản ánh ý nghĩa.

## 11. ORDER BY trong inline view và thứ tự kết quả cuối

Không nên dựa vào thứ tự dòng của inline view để suy ra thứ tự cuối của truy vấn ngoài. Muốn kết quả cuối được sắp xếp, hãy đặt `ORDER BY` ở query ngoài cùng:

~~~sql
SELECT x.order_id, x.order_total
FROM (
    SELECT order_id,
           SUM(quantity * unit_price) AS order_total
    FROM lab_jq_order_item
    GROUP BY order_id
) x
ORDER BY x.order_total DESC, x.order_id;
~~~

Thứ tự trong một query block bên trong không tự tạo bảo đảm thứ tự cho query block ngoài. Một trường hợp cần thứ tự trong bước trong là khi thứ tự được dùng để **xác định dòng cần chọn**, chẳng hạn `ROW_NUMBER()` hoặc cú pháp row limiting. Ngay cả khi đó, nếu muốn hiển thị kết quả cuối có thứ tự, vẫn nên có `ORDER BY` ở ngoài cùng.

### 11.1. Giới hạn top-N toàn cục

Oracle 12c trở lên hỗ trợ row limiting clause:

~~~sql
SELECT order_id, order_total
FROM (
    SELECT order_id,
           SUM(quantity * unit_price) AS order_total
    FROM lab_jq_order_item
    GROUP BY order_id
)
ORDER BY order_total DESC, order_id
FETCH FIRST 3 ROWS ONLY;
~~~

Ở đây `FETCH FIRST 3 ROWS ONLY` giới hạn ba dòng của kết quả đã sắp xếp. Nếu dùng phiên bản Oracle cũ hơn chưa hỗ trợ cú pháp row limiting, có thể dùng inline view với `ROW_NUMBER()` hoặc mẫu `ROWNUM` phù hợp.

## 12. Inline view, scalar subquery và correlated subquery

Đều là truy vấn con nhưng vị trí và kết quả khác nhau:

| Loại | Vị trí | Kết quả thường dùng | Ví dụ mục tiêu |
|---|---|---|---|
| Inline view | `FROM` | Một tập dòng có nhiều cột | Tổng tiền theo đơn để JOIN |
| Scalar subquery | Trong biểu thức SELECT/WHERE | Một giá trị đơn (một cột, tối đa một dòng) | Tổng tiền của một khách |
| Correlated subquery | Bên trong query khác, tham chiếu query ngoài | Kết quả phụ thuộc từng dòng ngoài | Kiểm tra EXISTS theo khách |
| CTE | Sau `WITH` | Tập dòng có tên trong statement | Chia báo cáo thành các bước có tên |

### 12.1. Scalar subquery

~~~sql
SELECT
    c.customer_id,
    c.customer_name,
    (
        SELECT COUNT(*)
        FROM lab_jq_order o
        WHERE o.customer_id = c.customer_id
          AND o.order_status = 'PAID'
    ) AS paid_order_count
FROM lab_jq_customer c
WHERE c.active_flag = 'Y'
ORDER BY c.customer_id;
~~~

Subquery trong SELECT trả một giá trị đếm cho từng khách. Vì `COUNT(*)` luôn trả một giá trị, kể cả khi không có dòng phù hợp (giá trị 0), scalar subquery này đáp ứng điều kiện một giá trị.

Nếu scalar subquery trả nhiều hơn một dòng, Oracle có thể báo `ORA-01427: single-row subquery returns more than one row`. Nếu trả không có dòng, giá trị scalar là NULL (trừ trường hợp hàm aggregate như COUNT vẫn trả một dòng).

### 12.2. EXISTS

Nếu chỉ cần biết khách có đơn PAID hay không, không cần đếm hoặc lấy cột đơn:

~~~sql
SELECT
    c.customer_id,
    c.customer_name
FROM lab_jq_customer c
WHERE c.active_flag = 'Y'
  AND EXISTS (
      SELECT 1
      FROM lab_jq_order o
      WHERE o.customer_id = c.customer_id
        AND o.order_status = 'PAID'
  )
ORDER BY c.customer_id;
~~~

`EXISTS` kiểm tra sự tồn tại của ít nhất một dòng phù hợp. Đây là correlated subquery vì điều kiện bên trong tham chiếu `c.customer_id` của query ngoài. Không cần JOIN chỉ để kiểm tra tồn tại, bởi JOIN có thể trả nhiều dòng cho một khách.

## 13. Phân tách truy vấn theo CTE, inline view hay bảng tạm?

Chọn cấu trúc dựa trên cách dùng dữ liệu trung gian:

| Nhu cầu | Cách thường phù hợp | Lý do |
|---|---|---|
| Một bước trung gian ngắn, dùng một lần trong FROM | Inline view | Gần nơi sử dụng, gọn |
| Nhiều bước logic có tên hoặc cần tham chiếu lại | CTE (`WITH`) | Dễ đọc theo pipeline |
| Kết quả cần lưu lâu hơn một statement và tái sử dụng giữa nhiều câu | Bảng staging hoặc bảng tạm | Có vòng đời dữ liệu được quản lý |
| Cần một đối tượng truy vấn ổn định để nhiều ứng dụng dùng | View database | Đặt tên ở schema và phân quyền |
| Cần tính tổng hợp trước khi nối để tránh fan-out | Inline view hoặc CTE | Chuẩn hóa grain của từng phía |
| Cần lọc kết quả hàm phân tích | Inline view hoặc CTE | Alias analytic trở thành cột của query ngoài |

### 13.1. View database khác inline view

View được tạo bằng `CREATE VIEW` và tồn tại như một object trong schema:

~~~sql
CREATE OR REPLACE VIEW lab_v_order_totals AS
SELECT
    order_id,
    SUM(quantity * unit_price) AS order_total
FROM lab_jq_order_item
GROUP BY order_id;
~~~

Sau đó:

~~~sql
SELECT order_id, order_total
FROM lab_v_order_totals
WHERE order_total >= 120;
~~~

View có tên độc lập và có thể dùng trong nhiều statement. Inline view chỉ tồn tại trong câu SQL chứa nó. View thông thường cũng không có nghĩa dữ liệu được materialize; materialized view là loại đối tượng khác với cơ chế lưu và refresh riêng.

### 13.2. Global temporary table và staging table

Nếu kết quả trung gian lớn, cần kiểm tra thủ công, hoặc được sử dụng qua nhiều statement, một bảng tạm (ví dụ Global Temporary Table) có thể phù hợp. Tuy nhiên, nó cần DDL, quyền, quản lý transaction/session và chính sách dọn dữ liệu. Không nên tạo bảng vật lý chỉ để thay thế một inline view đơn giản mà không có nhu cầu vòng đời rõ ràng.

## 14. Optimizer và ranh giới query block

Inline view giúp người viết chia bài toán, nhưng Oracle không nhất thiết chạy tuần tự “tính hết SELECT trong ngoặc, ghi xuống đĩa, rồi mới chạy SELECT ngoài”.

Optimizer có thể áp dụng các biến đổi như:

- **View merging:** gộp inline view vào query block ngoài khi phép biến đổi hợp lệ.
- **Predicate pushing:** đẩy một số điều kiện từ ngoài vào trong để giảm dữ liệu phải xử lý.
- **Join transformation:** thay đổi thứ tự hoặc phương pháp JOIN.
- **Aggregation transformation:** biến đổi cách thực hiện tổng hợp khi vẫn giữ ngữ nghĩa.
- **Subquery unnesting:** chuyển một số truy vấn con thành cấu trúc join/semi-join tương đương.

Vì vậy:

1. Viết truy vấn theo ý nghĩa đúng và grain rõ.
2. Không giả định inline view tự động materialize.
3. Không đặt hint chỉ vì muốn ép Oracle thực hiện theo đúng thứ tự văn bản.
4. Xem execution plan và số dòng ước lượng/thực tế nếu cần tối ưu.

### 14.1. Hints như NO_MERGE

Oracle có một số optimizer hint như `NO_MERGE` để tác động đến việc gộp view trong những tình huống cụ thể. Hint là công cụ nâng cao, phụ thuộc phiên bản, query block và optimizer. Không nên dùng chỉ để “bảo vệ” ranh giới logic; hãy dùng sau khi có bằng chứng từ execution plan và đo lường trên workload đại diện.

Một inline view có aggregate, analytic hoặc row limiting có thể có những giới hạn biến đổi riêng; không suy luận rằng mọi inline view đều được gộp hoặc mọi inline view đều được giữ nguyên như một bước vật lý.

### 14.2. Xem execution plan

~~~sql
EXPLAIN PLAN FOR
SELECT
    c.customer_id,
    c.customer_name,
    NVL(monthly.paid_order_count, 0) AS paid_order_count,
    NVL(monthly.paid_order_total, 0) AS paid_order_total
FROM lab_jq_customer c
LEFT JOIN (
    SELECT
        o.customer_id,
        COUNT(*) AS paid_order_count,
        SUM(item_totals.order_total) AS paid_order_total
    FROM lab_jq_order o
    JOIN (
        SELECT order_id,
               SUM(quantity * unit_price) AS order_total
        FROM lab_jq_order_item
        GROUP BY order_id
    ) item_totals
      ON item_totals.order_id = o.order_id
    WHERE o.order_status = 'PAID'
      AND o.order_date >= DATE '2026-01-01'
      AND o.order_date < DATE '2026-02-01'
    GROUP BY o.customer_id
) monthly
  ON monthly.customer_id = c.customer_id
WHERE c.active_flag = 'Y';

SELECT *
FROM TABLE(DBMS_XPLAN.DISPLAY);
~~~

`EXPLAIN PLAN` cho biết kế hoạch ước lượng trong ngữ cảnh phân tích. Khi có quyền và truy vấn đã chạy, `DBMS_XPLAN.DISPLAY_CURSOR` có thể giúp xem cursor thực thi và thống kê thực tế nếu đã thu thập phù hợp. Trên dataset nhỏ, full table scan có thể hoàn toàn hợp lý; không đánh giá hiệu năng chỉ bằng tên operation hoặc chi phí ước lượng.

## 15. Cách kiểm tra từng bước trung gian

Một lợi thế lớn của việc tách truy vấn là có thể chạy riêng từng query block để tìm lỗi.

### 15.1. Kiểm tra tổng theo đơn

~~~sql
SELECT order_id,
       SUM(quantity * unit_price) AS order_total
FROM lab_jq_order_item
GROUP BY order_id
ORDER BY order_id;
~~~

Đối chiếu với bảng tính tay ở phần 2.5. Nếu đơn 101 không ra 130, lỗi nằm ở dữ liệu dòng hàng hoặc biểu thức tính tiền, chưa liên quan đến khách hàng hay tháng báo cáo.

### 15.2. Kiểm tra đơn PAID trong kỳ

~~~sql
SELECT order_id, customer_id, order_date
FROM lab_jq_order
WHERE order_status = 'PAID'
  AND order_date >= DATE '2026-01-01'
  AND order_date < DATE '2026-02-01'
ORDER BY order_id;
~~~

Kết quả gồm 101, 102, 201, 202 và 301. Nếu đơn 401 xuất hiện, điều kiện trạng thái hoặc dữ liệu nguồn không đúng giả định.

### 15.3. Kiểm tra tổng hợp theo khách

~~~sql
SELECT
    o.customer_id,
    COUNT(*) AS paid_order_count,
    SUM(it.order_total) AS paid_order_total
FROM lab_jq_order o
JOIN (
    SELECT order_id,
           SUM(quantity * unit_price) AS order_total
    FROM lab_jq_order_item
    GROUP BY order_id
) it
  ON it.order_id = o.order_id
WHERE o.order_status = 'PAID'
  AND o.order_date >= DATE '2026-01-01'
  AND o.order_date < DATE '2026-02-01'
GROUP BY o.customer_id
ORDER BY o.customer_id;
~~~

Kết quả phải là An 2/210, Binh 2/220, Chi 1/300. Nếu tổng bị nhân, hãy kiểm tra grain của inline view và cardinality JOIN.

### 15.4. Kiểm tra kết quả cuối

~~~sql
SELECT
    c.customer_id,
    c.customer_name,
    NVL(m.paid_order_count, 0) AS paid_order_count,
    NVL(m.paid_order_total, 0) AS paid_order_total
FROM lab_jq_customer c
LEFT JOIN (
    SELECT
        o.customer_id,
        COUNT(*) AS paid_order_count,
        SUM(it.order_total) AS paid_order_total
    FROM lab_jq_order o
    JOIN (
        SELECT order_id,
               SUM(quantity * unit_price) AS order_total
        FROM lab_jq_order_item
        GROUP BY order_id
    ) it
      ON it.order_id = o.order_id
    WHERE o.order_status = 'PAID'
      AND o.order_date >= DATE '2026-01-01'
      AND o.order_date < DATE '2026-02-01'
    GROUP BY o.customer_id
) m
  ON m.customer_id = c.customer_id
WHERE c.active_flag = 'Y'
ORDER BY paid_order_total DESC, c.customer_id;
~~~

Kết quả:

| CUSTOMER_ID | CUSTOMER_NAME | PAID_ORDER_COUNT | PAID_ORDER_TOTAL |
|---:|---|---:|---:|
| 2 | Binh | 2 | 220 |
| 1 | An | 2 | 210 |
| 4 | Dung | 0 | 0 |

Nếu truy vấn trung gian đúng nhưng kết quả cuối sai, hãy kiểm tra LEFT JOIN, điều kiện active và cách xử lý NULL ở query ngoài.

## 16. Những lỗi thường gặp khi viết inline view

| Dấu hiệu | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| `ORA-00904: invalid identifier` | Query ngoài tham chiếu cột không được query trong xuất ra, hoặc dùng alias sai phạm vi | Kiểm tra select list bên trong và alias của inline view |
| `ORA-00918: column ambiguously defined` | Hai nguồn có cột trùng tên nhưng không chỉ rõ alias | Viết `o.order_id`, `it.order_id` và đặt tên cột đầu ra rõ |
| `ORA-00979: not a GROUP BY expression` | Cột trong SELECT không được nhóm hoặc aggregate phù hợp | Xác định grain và sửa GROUP BY |
| `ORA-01427` | Scalar subquery trả nhiều dòng | Chuyển sang JOIN/inline view hoặc bảo đảm subquery chỉ trả một dòng |
| Tổng bị nhân đôi | JOIN hai bảng chi tiết nhiều dòng theo cùng khóa | Tổng hợp từng phía về cùng grain trước JOIN |
| Khách không có đơn biến mất | Dùng INNER JOIN hoặc lọc cột bên phải trong WHERE sau LEFT JOIN | Dùng LEFT JOIN và đặt predicate phù hợp trong ON |
| Lấy top-N sai | Dùng ROWNUM ở sai query block hoặc thiếu thứ tự phụ | Dùng ROW_NUMBER trong inline view và lọc ở ngoài |
| Kết quả cuối không có thứ tự | Chỉ ORDER BY bên trong hoặc không ORDER BY ngoài cùng | Đặt ORDER BY ở query cuối |
| Truy vấn chậm hơn kỳ vọng | View transformation, join order, statistics hoặc fan-out không như dự đoán | Đọc plan và cardinality, đo trên dữ liệu đại diện |

## 17. Một số nguyên tắc khi chia truy vấn thành nhiều bước

### 17.1. Mỗi bước nên có một mục đích

Tên query block nên mô tả kết quả nó tạo ra, ví dụ:

- `ITEM_TOTALS`: tổng dòng hàng theo đơn.
- `PAYMENT_TOTALS`: tổng thanh toán theo đơn.
- `MONTHLY_CUSTOMER_TOTALS`: tổng theo khách trong kỳ.
- `LATEST_ORDERS`: các đơn được đánh số theo độ mới.

Tránh alias chung chung như `A`, `B`, `X1` trong một truy vấn nhiều tầng, vì người đọc phải lần ngược để hiểu ý nghĩa.

### 17.2. Ghi rõ grain đầu vào và đầu ra

Trước mỗi query block, hãy tự nói thành lời:

> “Sau bước này, một dòng đại diện cho một đơn hàng.”

hoặc:

> “Sau bước này, một dòng đại diện cho một khách hàng trong một tháng.”

Nếu không xác định được grain, rất dễ JOIN sai mức chi tiết và nhân dòng.

### 17.3. Đặt điều kiện đúng tầng

- Điều kiện trên từng dòng nguồn thường ở WHERE bên trong.
- Điều kiện trên nhóm aggregate có thể ở HAVING của query block tạo nhóm, hoặc WHERE của query block ngoài khi aggregate đã trở thành cột đầu ra.
- Điều kiện giữ bản ghi không khớp ở bảng trái cần xem xét cẩn thận khi dùng LEFT JOIN.
- Điều kiện trên hàm phân tích như `ROW_NUMBER()` phải được lọc ở query block ngoài.

### 17.4. Chọn inline view hay CTE theo khả năng đọc

Inline view thích hợp cho một bước nhỏ gần JOIN đang dùng. Khi có nhiều bước liên tiếp hoặc cần tái sử dụng một tập trung gian, CTE thường dễ theo dõi hơn. Không có quy tắc rằng CTE luôn nhanh hơn inline view hoặc ngược lại; hãy giữ cấu trúc dễ hiểu trước rồi đo plan khi có vấn đề hiệu năng.

### 17.5. Không chia quá nhỏ

Chia truy vấn thành nhiều query block có thể làm ý định rõ hơn, nhưng không cần bọc mọi biểu thức đơn giản vào một inline view. Mỗi tầng nên giải quyết một khác biệt về grain, thứ tự xử lý, phép tổng hợp, analytic hoặc tái sử dụng. Nếu một inline view chỉ đổi tên cột mà không giúp rõ logic, có thể không cần tách.

## 18. Bài tập thực hành

### Bài 1 — Tổng hợp dòng hàng theo đơn

Viết inline view trả về `ORDER_ID` và `ORDER_TOTAL` từ `LAB_JQ_ORDER_ITEM`. Chỉ giữ đơn có tổng giá trị từ 120 trở lên ở query ngoài.

**Đáp án định hướng:** tổng hợp theo `ORDER_ID` bên trong; lọc `ORDER_TOTAL >= 120` ở query ngoài.

### Bài 2 — Lấy khách có ít nhất hai đơn PAID

Tạo inline view đếm số đơn PAID theo khách, sau đó JOIN với `LAB_JQ_CUSTOMER` để hiển thị tên khách.

**Đáp án định hướng:** `GROUP BY customer_id` trong inline view; điều kiện `COUNT(*) >= 2` ở query ngoài hoặc HAVING bên trong; JOIN với customer.

### Bài 3 — Tránh fan-out

Đơn 101 có hai dòng hàng và hai payment. Chạy JOIN trực tiếp hai bảng chi tiết rồi so sánh tổng với kết quả thực tế. Sau đó viết hai inline view riêng, mỗi view tổng hợp theo order_id trước JOIN.

**Kết quả mong đợi cho đơn 101:** item total 130, payment total 130. JOIN thô làm cả hai tổng thành 260 do 2 × 2 dòng trung gian.

### Bài 4 — Hai đơn mới nhất cho mỗi khách

Dùng `ROW_NUMBER()` partition theo customer_id, sắp xếp ngày giảm dần và order_id giảm dần; query ngoài lọc `RN <= 2`.

**Câu hỏi:** Nếu hai đơn có cùng ngày, tại sao cần thêm order_id vào ORDER BY của analytic?

**Định hướng:** để thứ tự xác định, tránh kết quả thay đổi giữa các lần chạy khi có giá trị ngày bằng nhau.

### Bài 5 — So sánh inline view và CTE

Viết lại truy vấn báo cáo ở phần 6 bằng `WITH item_totals AS (...), monthly AS (...)`. Đối chiếu số dòng và tổng tiền với truy vấn inline view.

**Kết quả mong đợi:** Binh 2 đơn/220; An 2 đơn/210; Dung 0/0.

### Bài 6 — Lọc kết quả analytic

Viết truy vấn tìm đơn có giá trị dòng hàng cao nhất của từng khách. Dùng inline view để tính `ROW_NUMBER()` theo `customer_id`, sắp xếp tổng đơn giảm dần, rồi lọc `RN = 1`.

**Câu hỏi:** Vì sao không đặt `WHERE rn = 1` trong cùng query block với biểu thức `ROW_NUMBER()`?

**Định hướng:** WHERE được xử lý logic trước select-list analytic alias; query ngoài nhìn thấy RN như một cột đầu ra và lọc được.

### Bài 7 — Nhận diện grain

Với từng tập sau, hãy mô tả một dòng đại diện cho điều gì:

1. `LAB_JQ_ORDER_ITEM` trước aggregate.
2. Inline view tổng hợp `SUM(quantity * unit_price) GROUP BY order_id`.
3. Inline view tổng hợp số đơn và tổng tiền theo `customer_id`.
4. Kết quả cuối LEFT JOIN với customer.

**Định hướng:** lần lượt là dòng hàng; đơn hàng; khách hàng trong kỳ; khách hàng active trong báo cáo.

## 19. Quy trình thiết kế một truy vấn nhiều bước

Khi gặp bài toán báo cáo phức tạp, hãy đi theo chuỗi sau:

~~~text
YÊU CẦU NGHIỆP VỤ
        |
        v
Xác định dòng kết quả cuối đại diện cho gì?
        |
        v
Xác định bảng nguồn và quan hệ JOIN
        |
        v
Xác định grain của từng bảng chi tiết
        |
        v
Có nhiều bảng con cùng nhiều dòng trên một khóa?
        |
       Có
        |
        v
Tổng hợp từng phía về cùng grain trước JOIN
        |
        v
Tạo các bước bằng inline view hoặc CTE
        |
        v
JOIN các tập trung gian theo khóa rõ ràng
        |
        v
Áp dụng lọc dòng, lọc nhóm và analytic đúng tầng
        |
        v
Kiểm tra từng bước, số dòng và tổng hợp
        |
        v
Đối chiếu kết quả cuối và xem execution plan khi cần
~~~

Inline view và CTE là cách tổ chức câu SQL thành những **query block có ý nghĩa**. Chúng giúp ta chuyển đổi grain, tổng hợp trước khi JOIN, lọc kết quả aggregate hoặc analytic ở query ngoài, và kiểm tra từng phần của một báo cáo. Hãy bắt đầu từ câu hỏi “một dòng ở bước này đại diện cho điều gì?”, đặt alias rõ ràng, kiểm soát cardinality của JOIN và chỉ tổng hợp sau khi đã hiểu tập dòng đầu vào. Khi đó, truy vấn nhiều bước trong Oracle sẽ dễ đọc, dễ kiểm chứng và ít mắc lỗi nhân dòng hơn.
