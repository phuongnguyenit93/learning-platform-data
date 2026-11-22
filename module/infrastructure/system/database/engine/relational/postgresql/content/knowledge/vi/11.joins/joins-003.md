# CROSS JOIN và tích Descartes trong PostgreSQL

Khi viết SQL, phần lớn chúng ta nghĩ đến việc **ghép các hàng có quan hệ với nhau**: đơn hàng liên kết khách hàng bằng `customer_id`, sản phẩm liên kết dòng hàng bằng `product_id`. Tuy nhiên, có một phép kết hợp khác: **lấy mọi hàng ở tập bên trái ghép với mọi hàng ở tập bên phải**, bất kể chúng có khóa liên quan hay không. Phép toán đó là **tích Descartes** (*Cartesian product*), được PostgreSQL biểu diễn tường minh bằng `CROSS JOIN`.

Ví dụ, một cửa hàng có **2 màu** và **3 kích cỡ**, cần liệt kê mọi biến thể màu–cỡ. Tích Descartes tạo ra **2 × 3 = 6** tổ hợp. Đây là cách dùng đúng của `CROSS JOIN`. Nhưng nếu vô tình bỏ điều kiện nối giữa **100.000 đơn hàng** và **50.000 khách hàng**, số cặp có thể lên tới **5 tỷ hàng** trước khi xét các phép xử lý tiếp theo. Cùng một phép toán, nhưng mục đích và tác động rất khác nhau.

Bài học thuộc chương **Kết hợp dữ liệu** của PostgreSQL. Bạn sẽ hiểu cơ sở toán học của `CROSS JOIN`, phân biệt với `INNER JOIN` và `LEFT JOIN`, thực hành tạo tổ hợp, xây bộ khung báo cáo, sử dụng `generate_series` và `LATERAL`, nhận diện lỗi làm nhân số hàng, và dự đoán chi phí thực thi trước khi chạy truy vấn lớn.

## 1. Tích Descartes là gì?

Giả sử có hai tập dữ liệu:

~~~text
Tập màu A                Tập kích cỡ B
+----------+             +-----------+
| Đỏ       |             | S         |
| Xanh     |             | M         |
+----------+             | L         |
                         +-----------+
~~~

Tích Descartes `A × B` gồm mọi cặp:

~~~text
+----------+-----------+
| Màu      | Kích cỡ   |
+----------+-----------+
| Đỏ       | S         |
| Đỏ       | M         |
| Đỏ       | L         |
| Xanh     | S         |
| Xanh     | M         |
| Xanh     | L         |
+----------+-----------+
~~~

Mỗi hàng của A được ghép với **toàn bộ** hàng của B.

Trong SQL:

~~~sql
SELECT
    c.color_name,
    s.size_code
FROM colors AS c
CROSS JOIN sizes AS s;
~~~

Cú pháp này **không có `ON`** vì PostgreSQL không được yêu cầu tìm cặp hàng khớp một điều kiện nào.

### 1.1. Công thức số hàng

Nếu A có `m` hàng và B có `n` hàng, kết quả tích Descartes có:

\[
|A \times B| = m \times n
\]

Ví dụ:

| Số hàng A | Số hàng B | Số hàng CROSS JOIN |
|---:|---:|---:|
| 2 | 3 | 6 |
| 5 | 10 | 50 |
| 100 | 1.000 | 100.000 |
| 1.000 | 1.000 | 1.000.000 |
| 100.000 | 50.000 | 5.000.000.000 |

Công thức áp dụng cho **kết quả CROSS JOIN thuần túy**, trước những bộ lọc, phép tổng hợp, `DISTINCT` hoặc `LIMIT` có thể xuất hiện ở phần khác của truy vấn.

### 1.2. Không phải phép cộng số hàng

Hai bảng có 10 và 20 hàng không tạo 30 hàng khi CROSS JOIN mà tạo **200 hàng**. Sai sót này thường dẫn tới đánh giá thiếu bộ nhớ, CPU hoặc kích thước kết quả.

### 1.3. Số cột của kết quả

Nếu A có 2 cột và B có 3 cột, `SELECT *` từ `A CROSS JOIN B` có thể xuất 5 cột. Nhưng tên cột ở hai bảng có thể bị trùng; kết quả có thể khó đọc và gây rắc rối khi client ánh xạ tên cột.

Nên chọn cột tường minh và đặt alias:

~~~sql
SELECT
    a.id AS left_id,
    a.name AS left_name,
    b.id AS right_id,
    b.code AS right_code
FROM table_a AS a
CROSS JOIN table_b AS b;
~~~

Đoạn trên minh họa cấu trúc và chỉ chạy khi hai bảng tương ứng đã tồn tại.

## 2. PostgreSQL thực hiện CROSS JOIN như thế nào về mặt ngữ nghĩa?

Xem câu SQL:

~~~sql
SELECT a.value AS a_value, b.value AS b_value
FROM (VALUES ('A'), ('B')) AS a(value)
CROSS JOIN (VALUES (1), (2), (3)) AS b(value)
ORDER BY a.value, b.value;
~~~

Kết quả:

| a_value | b_value |
|---|---:|
| A | 1 |
| A | 2 |
| A | 3 |
| B | 1 |
| B | 2 |
| B | 3 |

Mỗi hàng bên trái được kết hợp với mọi hàng bên phải. Thứ tự trong bảng kết quả trên do `ORDER BY` quy định, **không phải do CROSS JOIN mặc định đảm bảo**.

### 2.1. CROSS JOIN không có điều kiện ghép

Với `INNER JOIN`, thường có điều kiện:

~~~sql
FROM orders AS o
INNER JOIN customers AS c
    ON c.customer_id = o.customer_id
~~~

Với `CROSS JOIN`:

~~~sql
FROM colors AS c
CROSS JOIN sizes AS s
~~~

không cần khóa, không có yêu cầu bằng nhau. Mọi cặp được hình thành về mặt logic.

### 2.2. Tích Descartes là tập các cặp, SQL còn có bản ghi lặp

Đại số quan hệ thường mô tả quan hệ như **tập**. SQL trong thực tế thường dùng **ngữ nghĩa đa tập** (*bag semantics*): trừ khi có `DISTINCT` hoặc cơ chế duy nhất thích hợp, các hàng trùng không tự bị loại bỏ.

Ví dụ:

~~~sql
SELECT a.label, b.number_value
FROM (VALUES ('A'), ('A')) AS a(label)
CROSS JOIN (VALUES (1), (2)) AS b(number_value);
~~~

Kết quả có bốn hàng, gồm hai bản sao của `(A,1)` và hai bản sao của `(A,2)`. PostgreSQL không coi hai hàng có cùng giá trị là một hàng duy nhất chỉ vì đang CROSS JOIN.

**Đừng dùng `DISTINCT` để che giấu lỗi dữ liệu trùng mà chưa hiểu yêu cầu nghiệp vụ.**

### 2.3. NULL không tự ngăn một cặp

~~~sql
SELECT a.value AS left_value, b.value AS right_value
FROM (VALUES (NULL::INTEGER), (1)) AS a(value)
CROSS JOIN (VALUES ('x'::TEXT), ('y'::TEXT)) AS b(value);
~~~

Có **4 hàng** dù một giá trị bên trái là `NULL`. CROSS JOIN không yêu cầu so sánh bằng nhau nên không loại bỏ hàng chỉ vì nó chứa NULL.

Khi thêm điều kiện như `WHERE a.value = b.value`, ngữ nghĩa ba giá trị của SQL mới ảnh hưởng hàng nào được giữ; nhưng ở ví dụ trên hai bên không có kiểu so sánh thích hợp để dùng điều kiện đó.

## 3. Nếu một bảng rỗng thì sao?

Giả sử A có 4 hàng và B không có hàng nào:

\[
|A \times B| = 4 \times 0 = 0
\]

Bạn có thể kiểm tra:

~~~sql
SELECT a.id, b.code
FROM (VALUES (1), (2), (3), (4)) AS a(id)
CROSS JOIN (
    SELECT code
    FROM (VALUES ('X')) AS x(code)
    WHERE FALSE
) AS b;
~~~

Kết quả **0 hàng**.

Điểm này quan trọng khi một bên là bảng cấu hình hoặc tập giá trị từ truy vấn con. Nếu truy vấn con không trả hàng, **toàn bộ kết quả CROSS JOIN biến mất**, dù bảng chính vẫn có dữ liệu.

### 3.1. Khác với LEFT JOIN

Nếu cần giữ mọi hàng từ A ngay cả khi B rỗng, có thể dùng phép nối ngoài thích hợp:

~~~sql
SELECT a.id, b.code
FROM (VALUES (1), (2)) AS a(id)
LEFT JOIN (
    SELECT code
    FROM (VALUES ('X')) AS x(code)
    WHERE FALSE
) AS b ON TRUE;
~~~

Kết quả gồm hai hàng, `b.code</BT> là `NULL`. Đây **không phải cùng ngữ nghĩa** với CROSS JOIN.

### 3.2. Trường hợp một bảng đúng một hàng

Nếu A có 100 hàng và B đúng một hàng, CROSS JOIN có 100 hàng. Đây là một cách có chủ đích để gắn **một giá trị chung** vào từng hàng A, chẳng hạn giá trị cấu hình, tổng hợp hoặc tham số.

Nhưng phải chắc chắn truy vấn B **thực sự trả đúng một hàng**, nếu không toàn bộ phép tính có thể nhân đôi hoặc biến mất.

## 4. Cú pháp CROSS JOIN trong PostgreSQL

Dạng chuẩn:

~~~sql
SELECT ...
FROM table_a AS a
CROSS JOIN table_b AS b;
~~~

Với nhiều bảng:

~~~sql
SELECT ...
FROM table_a AS a
CROSS JOIN table_b AS b
CROSS JOIN table_c AS c;
~~~

Nếu có lần lượt `m`, `n`, `p` hàng thì tích đầy đủ có `m × n × p` hàng.

### 4.1. CROSS JOIN không có ON và USING

Sai:

~~~sql
-- Không phải cú pháp CROSS JOIN hợp lệ:
-- FROM orders o CROSS JOIN customers c
-- ON o.customer_id = c.customer_id
~~~

Nếu muốn ghép theo điều kiện, dùng:

~~~sql
FROM orders AS o
JOIN customers AS c
    ON o.customer_id = c.customer_id
~~~

hoặc dùng CROSS JOIN rồi lọc trong `WHERE` khi có lý do rõ ràng; tuy nhiên cú pháp `INNER JOIN ... ON ...` thể hiện quan hệ dữ liệu rõ hơn.

### 4.2. Có thể CROSS JOIN với subquery

~~~sql
SELECT a.product_code, b.discount_rate
FROM (VALUES ('P01'), ('P02')) AS a(product_code)
CROSS JOIN (
    SELECT 0.10::NUMERIC AS discount_rate
) AS b;
~~~

Kết quả gồm hai sản phẩm, mỗi sản phẩm được ghép với một giá trị 0.10.

### 4.3. Có thể CROSS JOIN với VALUES

~~~sql
SELECT d.day_code, s.slot_time
FROM (VALUES ('MON'), ('TUE')) AS d(day_code)
CROSS JOIN (
    VALUES (TIME '09:00'), (TIME '14:00')
) AS s(slot_time)
ORDER BY d.day_code, s.slot_time;
~~~

Đây là cách gọn để tạo một tập giá trị nhỏ, thường dùng trong demo, báo cáo hoặc mô hình tham số.

### 4.4. Dùng alias để tránh nhầm cột

~~~sql
SELECT
    a.id AS source_id,
    b.id AS target_id
FROM source_table AS a
CROSS JOIN target_table AS b;
~~~

Không dùng `SELECT id` không có tên bảng khi cả hai bảng đều chứa cột `id`, vì PostgreSQL có thể báo cột mơ hồ.

## 5. CROSS JOIN và cú pháp liệt kê bảng bằng dấu phẩy

PostgreSQL hỗ trợ:

~~~sql
SELECT a.value, b.value
FROM (VALUES (1), (2)) AS a(value),
     (VALUES ('x'), ('y')) AS b(value);
~~~

Trong ví dụ hai nguồn không có điều kiện, cách này tạo tích Descartes tương tự:

~~~sql
SELECT a.value, b.value
FROM (VALUES (1), (2)) AS a(value)
CROSS JOIN (VALUES ('x'), ('y')) AS b(value);
~~~

### 5.1. Vì sao nên ưu tiên CROSS JOIN tường minh?

- Người đọc biết **chủ đích là tạo mọi tổ hợp**, không phải quên điều kiện JOIN.
- Dễ phân biệt với các quan hệ nối bằng khóa.
- Dễ kiểm soát nhóm phép nối và tránh hiểu sai thứ tự gắn `ON`.
- Hỗ trợ code review khi phát hiện số hàng tăng mạnh.

### 5.2. Thứ tự kết hợp với JOIN khác nhau

Trong cú pháp SQL, `JOIN` tường minh có mức kết hợp khác với dấu phẩy trong `FROM`. Một câu kiểu:

~~~sql
-- Chỉ minh họa cú pháp có thể gây lỗi tham chiếu:
-- FROM a, b JOIN c ON c.key = a.key
~~~

có thể không hợp lệ vì điều kiện `ON` của `b JOIN c` không nhìn thấy `a` theo cách người viết tưởng.

Cách dễ hiểu hơn là nhóm quan hệ rõ ràng bằng JOIN tường minh và điều kiện đi kèm đúng phép nối:

~~~sql
FROM a
JOIN c ON c.key = a.key
CROSS JOIN b
~~~

Đây là ví dụ cấu trúc, chỉ chạy khi các bảng và cột tồn tại.

### 5.3. Không đánh đồng NATURAL JOIN với CROSS JOIN

`NATURAL JOIN` là một kiểu JOIN dựa vào các tên cột trùng nhau, **không phải từ đồng nghĩa** của CROSS JOIN. Vì schema có thể thay đổi và tạo thêm cột trùng tên, NATURAL JOIN thường khó đọc và có thể làm thay đổi ý nghĩa query ngoài ý muốn. Với quan hệ nghiệp vụ nên viết rõ `ON` hoặc `USING` phù hợp.

## 6. CROSS JOIN và INNER JOIN ON TRUE

Với hai nguồn độc lập, những dạng sau tương đương về mặt hàng kết quả:

~~~sql
SELECT a.id, b.code
FROM (VALUES (1), (2)) AS a(id)
CROSS JOIN (VALUES ('X'), ('Y')) AS b(code);
~~~

~~~sql
SELECT a.id, b.code
FROM (VALUES (1), (2)) AS a(id)
INNER JOIN (VALUES ('X'), ('Y')) AS b(code)
    ON TRUE;
~~~

Điều kiện `ON TRUE` đúng với **mọi cặp**, nên INNER JOIN không loại bỏ cặp nào.

### 6.1. Nhưng lựa chọn cú pháp truyền tải chủ đích

- `CROSS JOIN`: chủ đích tạo mọi cặp.
- `INNER JOIN ... ON TRUE`: điều kiện nối luôn đúng, có thể được dùng trong SQL sinh tự động hoặc một số mẫu đặc thù.
- `INNER JOIN ... ON condition`: chỉ giữ cặp thỏa điều kiện, thường là mối quan hệ dữ liệu.

Ưu tiên `CROSS JOIN` khi cần tổ hợp toàn phần.

### 6.2. LEFT JOIN ON TRUE không phải lúc nào cũng giống

Nếu bảng bên phải có ít nhất một hàng, `LEFT JOIN ... ON TRUE` có thể tạo mọi cặp như CROSS JOIN. Nhưng nếu bảng bên phải rỗng, LEFT JOIN vẫn giữ các hàng bên trái với cột bên phải NULL, còn CROSS JOIN trả 0 hàng.

Do đó không thể thay hai phép nối cho nhau một cách tổng quát.

## 7. CROSS JOIN kết hợp WHERE: tích rồi lọc

Xét:

~~~sql
SELECT a.id, b.id
FROM (VALUES (1), (2)) AS a(id)
CROSS JOIN (VALUES (1), (3)) AS b(id)
WHERE a.id = b.id;
~~~

Tích ban đầu có bốn cặp:

~~~text
(1,1)
(1,3)
(2,1)
(2,3)
~~~

Sau điều kiện `WHERE a.id = b.id`, còn một cặp `(1,1)`.

Một cách viết khác:

~~~sql
SELECT a.id, b.id
FROM (VALUES (1), (2)) AS a(id)
JOIN (VALUES (1), (3)) AS b(id)
    ON a.id = b.id;
~~~

Hai truy vấn có cùng kết quả cho tình huống INNER JOIN thông thường.

### 7.1. Về logic, SELECT đi qua các giai đoạn

Một mô hình khái niệm:

~~~text
FROM / JOIN
    |
    v
WHERE
    |
    v
GROUP BY / HAVING
    |
    v
SELECT
    |
    v
ORDER BY / LIMIT
~~~

Tuy nhiên đây là **mô hình ngữ nghĩa**, không phải mô tả bắt buộc về thứ tự vật lý PostgreSQL sẽ tạo và lưu mọi hàng. Planner có thể đẩy bộ lọc, đổi thứ tự join và chọn thuật toán khác nếu giữ đúng semantics.

### 7.2. Vì sao JOIN ON biểu đạt ý nghĩa tốt hơn?

Khi hai bảng có quan hệ thực sự:

~~~sql
SELECT
    o.order_id,
    c.customer_name
FROM orders AS o
JOIN customers AS c
    ON c.customer_id = o.customer_id;
~~~

đọc dễ hơn:

~~~sql
SELECT
    o.order_id,
    c.customer_name
FROM orders AS o
CROSS JOIN customers AS c
WHERE c.customer_id = o.customer_id;
~~~

PostgreSQL có thể tối ưu hai dạng tương tự trong nhiều trường hợp, nhưng cú pháp đầu mô tả đúng **ý định kết hợp theo khóa** và giảm rủi ro ai đó xóa nhầm điều kiện WHERE.

### 7.3. Các điều kiện ở WHERE có thể làm giảm số cặp

Nếu mỗi bảng có một bộ lọc riêng:

~~~sql
SELECT a.id, b.code
FROM table_a AS a
CROSS JOIN table_b AS b
WHERE a.active = TRUE
  AND b.enabled = TRUE;
~~~

Kết quả logic là tích Descartes của tập hàng **active** với tập hàng **enabled**. Planner thường có thể áp dụng bộ lọc phù hợp trước khi nối về mặt vật lý.

Không kết luận PostgreSQL chắc chắn tạo tất cả `|A| × |B|` hàng trong RAM rồi mới lọc; phải xem kế hoạch thực thi.

## 8. Lab: tạo dữ liệu mẫu màu và kích cỡ

Các lệnh trong phần này dành cho **database PostgreSQL thử nghiệm** có quyền CREATE SCHEMA. Không chạy trên production. Nếu schema `cross_join_lab` đã tồn tại từ lần thực hành trước, dùng database khác hoặc tên schema khác; không xóa dữ liệu thật.

### 8.1. Tạo schema

~~~sql
CREATE SCHEMA cross_join_lab;
~~~

### 8.2. Tạo hai bảng dimension

~~~sql
CREATE TABLE cross_join_lab.colors (
    color_id INTEGER PRIMARY KEY,
    color_name TEXT NOT NULL UNIQUE
);

CREATE TABLE cross_join_lab.sizes (
    size_code TEXT PRIMARY KEY,
    sort_rank INTEGER NOT NULL UNIQUE
);
~~~

### 8.3. Chèn dữ liệu

~~~sql
INSERT INTO cross_join_lab.colors (color_id, color_name)
VALUES
    (1, 'Đỏ'),
    (2, 'Xanh');

INSERT INTO cross_join_lab.sizes (size_code, sort_rank)
VALUES
    ('S', 1),
    ('M', 2),
    ('L', 3);
~~~

Số hàng:

~~~sql
SELECT COUNT(*) AS color_count
FROM cross_join_lab.colors;

SELECT COUNT(*) AS size_count
FROM cross_join_lab.sizes;
~~~

Dự kiến lần lượt là 2 và 3.

### 8.4. Tạo mọi tổ hợp

~~~sql
SELECT
    c.color_id,
    c.color_name,
    s.size_code
FROM cross_join_lab.colors AS c
CROSS JOIN cross_join_lab.sizes AS s
ORDER BY c.color_id, s.sort_rank;
~~~

Kết quả:

| color_id | color_name | size_code |
|---:|---|---|
| 1 | Đỏ | S |
| 1 | Đỏ | M |
| 1 | Đỏ | L |
| 2 | Xanh | S |
| 2 | Xanh | M |
| 2 | Xanh | L |

### 8.5. Kiểm tra số hàng của tích

~~~sql
SELECT COUNT(*) AS combination_count
FROM cross_join_lab.colors AS c
CROSS JOIN cross_join_lab.sizes AS s;
~~~

Dự kiến `6`.

Bạn cũng có thể so sánh:

~~~sql
SELECT
    (SELECT COUNT(*) FROM cross_join_lab.colors)
    *
    (SELECT COUNT(*) FROM cross_join_lab.sizes)
    AS expected_combinations;
~~~

Hai kết quả phải bằng nhau khi đang xét CROSS JOIN thuần túy và dữ liệu không đổi giữa những lần đọc theo ngữ nghĩa snapshot tương ứng.

### 8.6. Không giả định thứ tự nếu bỏ ORDER BY

~~~sql
SELECT c.color_name, s.size_code
FROM cross_join_lab.colors AS c
CROSS JOIN cross_join_lab.sizes AS s;
~~~

PostgreSQL có thể trả các hàng theo một thứ tự cụ thể trong một lần thử, nhưng **SQL không đảm bảo thứ tự đầu ra** nếu không có `ORDER BY`. Đừng viết test dựa trên thứ tự tình cờ.

## 9. CROSS JOIN trong nghiệp vụ: tạo biến thể sản phẩm

Bài toán “màu × kích cỡ” là một ứng dụng tự nhiên, nhưng cần phân biệt:

- **Tập biến thể có thể tạo**: mọi tổ hợp lý thuyết.
- **Tập biến thể thật sự được bán**: một tập con có quy tắc.
- **SKU đã đăng ký**: những biến thể đã tồn tại và được quản lý như entity độc lập.
- **Tồn kho**: số lượng ở một địa điểm và thời điểm cụ thể.

### 9.1. Tạo danh sách biến thể tiềm năng

~~~sql
SELECT
    c.color_name,
    s.size_code
FROM cross_join_lab.colors AS c
CROSS JOIN cross_join_lab.sizes AS s
ORDER BY c.color_id, s.sort_rank;
~~~

Câu SQL tạo **mọi tổ hợp**, không tự xác nhận chúng có thể sản xuất hoặc đã có giá bán.

### 9.2. Loại những tổ hợp không hợp lệ

Giả sử kích cỡ L chỉ có ở màu Đỏ:

~~~sql
SELECT
    c.color_name,
    s.size_code
FROM cross_join_lab.colors AS c
CROSS JOIN cross_join_lab.sizes AS s
WHERE s.size_code <> 'L'
   OR c.color_name = 'Đỏ'
ORDER BY c.color_id, s.sort_rank;
~~~

Kết quả có 5 tổ hợp: ba kích cỡ màu Đỏ và hai kích cỡ S/M màu Xanh.

Với hệ thống thật, không nên hard-code mọi ngoại lệ trong WHERE. Có thể cần bảng cấu hình các biến thể được phép hoặc bảng product_variants có các khóa/ràng buộc phù hợp.

### 9.3. Không dùng CROSS JOIN để giả vờ đã có entity

Nếu ứng dụng cần SKU, barcode, tồn kho hoặc giá riêng cho biến thể, việc chỉ hiển thị tích Descartes không tạo dữ liệu đó. Cần mô hình bảng biến thể và quy trình đăng ký phù hợp.

CROSS JOIN giải quyết **sinh tổ hợp**, không thay thế lifecycle của dữ liệu nghiệp vụ.

## 10. Tạo bộ khung báo cáo: ngày × cửa hàng

Một tình huống quan trọng: cần báo cáo **mỗi cửa hàng, mỗi ngày** trong khoảng, kể cả khi không phát sinh giao dịch.

Nếu chỉ nhóm bảng giao dịch, những ngày không có giao dịch sẽ **không xuất hiện**. Ta có thể dùng CROSS JOIN để dựng bộ khung kết quả đầy đủ rồi LEFT JOIN dữ liệu thật.

### 10.1. Tạo bảng cửa hàng và doanh thu ngày

~~~sql
CREATE TABLE cross_join_lab.stores (
    store_id INTEGER PRIMARY KEY,
    store_name TEXT NOT NULL
);

CREATE TABLE cross_join_lab.daily_sales (
    store_id INTEGER NOT NULL
        REFERENCES cross_join_lab.stores(store_id),
    sale_day DATE NOT NULL,
    revenue NUMERIC(14, 2) NOT NULL
        CHECK (revenue >= 0),
    PRIMARY KEY (store_id, sale_day)
);

INSERT INTO cross_join_lab.stores (store_id, store_name)
VALUES
    (1, 'Hà Nội'),
    (2, 'Đà Nẵng');

INSERT INTO cross_join_lab.daily_sales (
    store_id, sale_day, revenue
)
VALUES
    (1, DATE '2026-11-14', 1000000.00),
    (2, DATE '2026-11-15', 1500000.00);
~~~

Dữ liệu có hai cửa hàng và hai ngày:

~~~text
Hà Nội:   14/11 có doanh thu, 15/11 không có bản ghi
Đà Nẵng: 14/11 không có bản ghi, 15/11 có doanh thu
~~~

### 10.2. Tạo tập ngày bằng VALUES

~~~sql
SELECT d.sale_day
FROM (
    VALUES
        (DATE '2026-11-14'),
        (DATE '2026-11-15')
) AS d(sale_day);
~~~

### 10.3. CROSS JOIN để tạo mọi cặp cửa hàng–ngày

~~~sql
SELECT
    s.store_id,
    s.store_name,
    d.sale_day
FROM cross_join_lab.stores AS s
CROSS JOIN (
    VALUES
        (DATE '2026-11-14'),
        (DATE '2026-11-15')
) AS d(sale_day)
ORDER BY s.store_id, d.sale_day;
~~~

Bộ khung có **2 × 2 = 4** hàng, kể cả hai ô chưa có doanh thu.

### 10.4. LEFT JOIN và COALESCE để điền dữ liệu

~~~sql
SELECT
    s.store_name,
    d.sale_day,
    COALESCE(ds.revenue, 0::NUMERIC) AS revenue
FROM cross_join_lab.stores AS s
CROSS JOIN (
    VALUES
        (DATE '2026-11-14'),
        (DATE '2026-11-15')
) AS d(sale_day)
LEFT JOIN cross_join_lab.daily_sales AS ds
    ON ds.store_id = s.store_id
   AND ds.sale_day = d.sale_day
ORDER BY s.store_id, d.sale_day;
~~~

Kết quả:

| store_name | sale_day | revenue |
|---|---|---:|
| Hà Nội | 2026-11-14 | 1.000.000 |
| Hà Nội | 2026-11-15 | 0 |
| Đà Nẵng | 2026-11-14 | 0 |
| Đà Nẵng | 2026-11-15 | 1.500.000 |

Đây là **mẫu tạo khung dữ liệu đầy đủ** (*data scaffolding / densification*) thường dùng trong dashboard và báo cáo.

### 10.5. COALESCE 0 có phải luôn đúng?

Không. **Không có bản ghi** có thể nghĩa là “doanh thu bằng 0” hoặc “chưa nhận dữ liệu”. Nếu chưa có dữ liệu vì ETL lỗi, việc đổi NULL thành 0 có thể che giấu sự cố.

Phải xác định nghiệp vụ:

- Nếu chắc chắn không có giao dịch = 0, `COALESCE` phù hợp.
- Nếu thiếu bản ghi có thể là dữ liệu chưa sẵn sàng, nên giữ NULL hoặc thêm cờ `data_available`.

CROSS JOIN tạo ô chưa có dữ liệu; **ý nghĩa của ô trống** là quyết định nghiệp vụ riêng.

## 11. Bẫy WHERE sau LEFT JOIN

Khi đã dựng khung bằng CROSS JOIN và LEFT JOIN, một điều kiện đặt sai chỗ có thể làm mất những hàng cần giữ.

Ví dụ:

~~~sql
SELECT
    s.store_name,
    d.sale_day,
    ds.revenue
FROM cross_join_lab.stores AS s
CROSS JOIN (
    VALUES
        (DATE '2026-11-14'),
        (DATE '2026-11-15')
) AS d(sale_day)
LEFT JOIN cross_join_lab.daily_sales AS ds
    ON ds.store_id = s.store_id
   AND ds.sale_day = d.sale_day
WHERE ds.revenue > 0;
~~~

Các hàng không khớp có `ds.revenue IS NULL`, nên `WHERE ds.revenue > 0` không giữ chúng. Kết quả không còn đủ mọi cặp cửa hàng–ngày.

### 11.1. Nếu chỉ muốn nối bản ghi doanh thu dương

Có thể chuyển điều kiện sang `ON`:

~~~sql
LEFT JOIN cross_join_lab.daily_sales AS ds
    ON ds.store_id = s.store_id
   AND ds.sale_day = d.sale_day
   AND ds.revenue > 0
~~~

Lúc này những hàng của bộ khung vẫn được giữ, nhưng cột doanh thu không khớp sẽ là NULL.

**Không chuyển điều kiện giữa WHERE và ON một cách cơ học**: với outer join, kết quả có thể khác về ngữ nghĩa.

### 11.2. Kết hợp CROSS JOIN và LEFT JOIN có chủ đích

Trong truy vấn báo cáo:

~~~text
CROSS JOIN:
    Xác định những tổ hợp PHẢI xuất hiện.

LEFT JOIN:
    Ghép dữ liệu thực tế CÓ THỂ tồn tại.

WHERE / ON:
    Xác định bộ lọc đối tượng và loại dữ liệu cần giữ.
~~~

Phân tách các vai trò này giúp truy vấn dễ đọc hơn.

## 12. generate_series() và CROSS JOIN

PostgreSQL có hàm `generate_series` để sinh dãy số hoặc mốc thời gian. Đây là công cụ rất hợp với CROSS JOIN khi cần dựng lịch hoặc ma trận giá trị.

### 12.1. Sinh dãy số

~~~sql
SELECT g.n
FROM generate_series(1, 5) AS g(n);
~~~

Kết quả gồm 1, 2, 3, 4, 5.

### 12.2. Ghép mỗi màu với các số thứ tự

~~~sql
SELECT
    c.color_name,
    g.n
FROM cross_join_lab.colors AS c
CROSS JOIN generate_series(1, 3) AS g(n)
ORDER BY c.color_id, g.n;
~~~

Hai màu và ba số tạo **6 hàng**.

### 12.3. Sinh ngày kết hợp khung giờ

~~~sql
SELECT
    g.day_start::DATE AS schedule_day,
    slot.slot_time
FROM generate_series(
    TIMESTAMP '2026-11-14 00:00:00',
    TIMESTAMP '2026-11-16 00:00:00',
    INTERVAL '1 day'
) AS g(day_start)
CROSS JOIN (
    VALUES
        (TIME '09:00:00'),
        (TIME '14:00:00')
) AS slot(slot_time)
ORDER BY schedule_day, slot.slot_time;
~~~

Tập ngày gồm 14, 15, 16 tháng 11. Mỗi ngày có hai khung giờ 09:00 và 14:00, nên kết quả có **3 × 2 = 6 hàng**.

### 12.4. generate_series thường bao gồm đầu mút cuối

Trong ví dụ trên, mốc `2026-11-16 00:00` xuất hiện vì `generate_series` đi theo bước và có thể gồm endpoint nếu khớp.

Nếu báo cáo muốn khoảng ngày `[2026-11-14, 2026-11-16)`, bạn phải tính mốc cuối phù hợp hoặc thêm điều kiện lọc để không tạo ngày 16 ngoài ý định.

### 12.5. Lịch theo timezone và DST

Nếu sinh **instant** theo ngày tại một vùng có daylight saving time, cần hiểu liệu bước một ngày được áp dụng theo lịch địa phương hay một duration tuyệt đối, và phiên bản PostgreSQL có hỗ trợ biến thể hàm nhận timezone hay không.

Ví dụ ở trên dùng `timestamp without time zone` để sinh nhãn ngày địa phương cho bài lab, **không phải lịch thông báo instant đa quốc gia**. Với lịch có DST, nên mô hình timezone và chuyển đổi mốc ngày rõ ràng.

## 13. CROSS JOIN với nhiều chiều

Giả sử báo cáo có:

- 2 cửa hàng.
- 3 loại sản phẩm.
- 7 ngày.

Số ô dữ liệu:

\[
2 \times 3 \times 7 = 42
\]

Một truy vấn minh họa:

~~~sql
SELECT
    s.store_name,
    p.category_code,
    d.day_start::DATE AS report_day
FROM cross_join_lab.stores AS s
CROSS JOIN (
    VALUES ('BOOK'), ('TOY'), ('GIFT')
) AS p(category_code)
CROSS JOIN generate_series(
    TIMESTAMP '2026-11-14 00:00:00',
    TIMESTAMP '2026-11-20 00:00:00',
    INTERVAL '1 day'
) AS d(day_start)
ORDER BY s.store_id, p.category_code, report_day;
~~~

Kết quả có 42 hàng nếu bảng cửa hàng giữ đúng 2 hàng.

### 13.1. Số hàng tăng theo tích các chiều

Với nhiều dimension:

\[
N = n_1 \times n_2 \times \cdots \times n_k
\]

Một dimension có 0 hàng khiến toàn bộ tích có 0 hàng. Một dimension lớn hơn gấp đôi khiến kết quả toàn bộ lớn gấp đôi, khi những phần khác không đổi.

### 13.2. Ví dụ bùng nổ số tổ hợp

~~~text
100 cửa hàng
× 10.000 sản phẩm
× 365 ngày
= 365.000.000 tổ hợp
~~~

365 triệu hàng có thể vượt xa nhu cầu dashboard. Chỉ tạo những tổ hợp được nghiệp vụ cần: chẳng hạn chỉ sản phẩm đang bán tại từng cửa hàng, chỉ ngày trong kỳ báo cáo cần quan sát, và chỉ những tổ hợp được phép.

### 13.3. Không tự động đồng nhất mọi tổ hợp với hợp lệ

Tích `cửa hàng × sản phẩm` có thể sinh ra sản phẩm mà cửa hàng đó không bán. Nếu báo cáo cần mọi cặp **được phép**, cần bảng liên kết store-product hoặc một bộ lọc được quản lý đúng.

Một mô hình hợp lý có thể dùng `stores JOIN store_products</BT> để xác định tổ hợp hợp lệ, rồi `CROSS JOIN dates</BT> để trải từng tổ hợp qua mọi ngày.

## 14. Lọc sớm để kiểm soát tập đầu vào

Giả sử chỉ cần cửa hàng đang hoạt động và loại sản phẩm được bật:

~~~sql
SELECT
    s.store_id,
    p.product_id
FROM (
    SELECT store_id
    FROM stores
    WHERE active = TRUE
) AS s
CROSS JOIN (
    SELECT product_id
    FROM products
    WHERE enabled = TRUE
) AS p;
~~~

Đây là ví dụ cấu trúc, chỉ chạy nếu bảng và cột tồn tại.

### 14.1. Vì sao lọc chiều trước khi ghép?

Nếu bảng cửa hàng có 1.000 hàng nhưng chỉ 50 active và bảng sản phẩm có 100.000 hàng nhưng chỉ 200 enabled:

~~~text
Không lọc: 1.000 × 100.000 = 100.000.000 hàng

Tập cần thiết: 50 × 200 = 10.000 hàng
~~~

Giảm tập đầu vào về mặt logic trước khi tạo tổ hợp có thể làm workload nhỏ hơn rất nhiều.

### 14.2. Planner có thể đẩy WHERE xuống

Hai truy vấn sau thường cùng ý nghĩa:

~~~sql
SELECT s.store_id, p.product_id
FROM stores AS s
CROSS JOIN products AS p
WHERE s.active = TRUE
  AND p.enabled = TRUE;
~~~

~~~sql
SELECT s.store_id, p.product_id
FROM (
    SELECT store_id
    FROM stores
    WHERE active = TRUE
) AS s
CROSS JOIN (
    SELECT product_id
    FROM products
    WHERE enabled = TRUE
) AS p;
~~~

PostgreSQL planner có thể nhận diện bộ lọc chỉ phụ thuộc một nguồn và áp dụng sớm. Dạng viết thứ hai làm rõ tập cần dùng, nhưng không có nghĩa mọi subquery sẽ được vật lý hóa.

Để biết thực tế server thực hiện gì, cần xem `EXPLAIN`.

### 14.3. CTE không mặc định là một hàng rào vật lý

~~~sql
WITH active_stores AS (
    SELECT store_id
    FROM stores
    WHERE active
),
enabled_products AS (
    SELECT product_id
    FROM products
    WHERE enabled
)
SELECT s.store_id, p.product_id
FROM active_stores AS s
CROSS JOIN enabled_products AS p;
~~~

CTE giúp tổ chức SQL, nhưng PostgreSQL có thể inline hoặc materialize tùy ngữ cảnh, phiên bản và chỉ dẫn. Không dựa vào việc “viết WITH” để khẳng định nó luôn tạo bảng tạm và ngăn mọi tối ưu.

## 15. CROSS JOIN và lỗi thiếu điều kiện JOIN

Đây là nguy cơ thực tế quan trọng nhất.

Giả sử có:

~~~text
customers: 5.000 hàng
orders:   80.000 hàng
~~~

Mục tiêu là ghép đơn hàng với khách sở hữu.

**Đúng:**

~~~sql
SELECT
    o.order_id,
    c.customer_name
FROM orders AS o
JOIN customers AS c
    ON c.customer_id = o.customer_id;
~~~

Nếu mỗi order trỏ đúng một customer, kết quả thường gần **80.000 hàng**.

**Sai do quên điều kiện:**

~~~sql
SELECT
    o.order_id,
    c.customer_name
FROM orders AS o
CROSS JOIN customers AS c;
~~~

Số cặp là:

\[
80.000 \times 5.000 = 400.000.000
\]

Nếu người viết dùng cú pháp dấu phẩy:

~~~sql
SELECT
    o.order_id,
    c.customer_name
FROM orders AS o,
     customers AS c;
~~~

mà quên `WHERE o.customer_id = c.customer_id`, lỗi vẫn tạo tích Descartes.

### 15.1. Dấu hiệu của lỗi cartesian product

- Một đơn hàng xuất hiện kèm nhiều khách hàng không liên quan.
- Số dòng tăng từ hàng nghìn lên hàng triệu.
- Tổng doanh thu bị nhân lên nhiều lần.
- Query trả kết quả rất chậm hoặc tiêu thụ tài nguyên bất thường.
- `EXPLAIN</BT> dự báo cardinality của join tăng rất lớn.
- Báo cáo chỉ đúng khi có bộ lọc cực hẹp nhưng sai với phạm vi rộng.

### 15.2. GROUP BY có thể che sai số hàng

Ví dụ:

~~~sql
SELECT SUM(o.amount)
FROM orders AS o
CROSS JOIN customers AS c;
~~~

Nếu customers có 5.000 hàng, mỗi order bị lặp 5.000 lần nên tổng tiền bị nhân 5.000, giả sử các điều kiện khác không thay đổi.

Thêm `DISTINCT</BT> vào giá trị tiền không phải cách sửa đúng: các đơn khác nhau có thể có cùng amount, khi đó DISTINCT còn làm sai kết quả theo một cách khác.

**Phải sửa quan hệ JOIN**, không vá bằng DISTINCT hoặc GROUP BY cho qua.

## 16. Tự CROSS JOIN một bảng: mọi cặp đối tượng

Đôi khi cần tạo mọi cặp giữa các hàng của **cùng một bảng**.

~~~sql
SELECT
    a.color_name AS color_a,
    b.color_name AS color_b
FROM cross_join_lab.colors AS a
CROSS JOIN cross_join_lab.colors AS b
ORDER BY a.color_id, b.color_id;
~~~

Với 2 màu, kết quả gồm:

~~~text
Đỏ  - Đỏ
Đỏ  - Xanh
Xanh - Đỏ
Xanh - Xanh
~~~

### 16.1. Loại cặp của một đối tượng với chính nó

~~~sql
SELECT
    a.color_name AS color_a,
    b.color_name AS color_b
FROM cross_join_lab.colors AS a
CROSS JOIN cross_join_lab.colors AS b
WHERE a.color_id <> b.color_id;
~~~

Với 2 màu, còn hai cặp có hướng: Đỏ–Xanh và Xanh–Đỏ.

Với `n` hàng có khóa khác nhau, số cặp có hướng khác chính nó là:

\[
n(n-1)
\]

### 16.2. Tạo cặp không phân biệt thứ tự

~~~sql
SELECT
    a.color_name AS first_color,
    b.color_name AS second_color
FROM cross_join_lab.colors AS a
CROSS JOIN cross_join_lab.colors AS b
WHERE a.color_id < b.color_id;
~~~

Điều kiện `a.color_id < b.color_id` loại cặp cùng ID và loại một trong hai thứ tự đối xứng. Số cặp là:

\[
\frac{n(n-1)}{2}
\]

Mẫu này hữu ích khi liệt kê các cặp sản phẩm để so sánh, cặp phòng để đánh giá quan hệ hoặc cặp người để xây danh sách đề xuất. Với tập rất lớn, phép sinh cặp có thể nhanh chóng trở nên tốn kém.

### 16.3. Không dùng cặp mọi người khi chỉ cần quan hệ đã biết

Nếu hệ thống có hàng triệu người nhưng chỉ muốn các cặp đã kết bạn, việc CROSS JOIN mọi người với mọi người là quá lớn. Nên dùng bảng quan hệ `friendships</BT> hoặc kỹ thuật truy vấn theo dữ liệu liên kết thực có.

## 17. CROSS JOIN với hàm trả nhiều hàng

PostgreSQL cho phép **set-returning functions** xuất hiện trong `FROM`, ví dụ `generate_series</BT> hoặc `unnest</BT>.

~~~sql
SELECT
    c.color_name,
    series.n
FROM cross_join_lab.colors AS c
CROSS JOIN generate_series(1, 3) AS series(n);
~~~

Khi hàm không phụ thuộc hàng bên trái, nó hoạt động như một nguồn hàng độc lập và số hàng bằng `colors_count × 3`.

### 17.1. unnest với mảng cố định

~~~sql
SELECT
    c.color_name,
    u.tag
FROM cross_join_lab.colors AS c
CROSS JOIN unnest(
    ARRAY['featured', 'clearance']::TEXT[]
) AS u(tag)
ORDER BY c.color_id, u.tag;
~~~

Mỗi màu ghép với hai tag, tạo 4 hàng.

### 17.2. Hàm không trả hàng cũng làm kết quả rỗng

~~~sql
SELECT
    c.color_name,
    u.tag
FROM cross_join_lab.colors AS c
CROSS JOIN unnest(ARRAY[]::TEXT[]) AS u(tag);
~~~

Vì `unnest</BT> trên mảng rỗng không trả hàng, toàn bộ CROSS JOIN không có hàng. Đây là hệ quả trực tiếp của công thức nhân với 0.

## 18. CROSS JOIN LATERAL: nguồn bên phải phụ thuộc từng hàng bên trái

Một phép CROSS JOIN thông thường giữa hai tập độc lập có số hàng `m × n`. Nhưng đôi khi nguồn bên phải cần **dùng giá trị của mỗi hàng bên trái** để tạo số hàng khác nhau.

PostgreSQL hỗ trợ `LATERAL</BT>:

~~~sql
SELECT
    c.color_id,
    c.color_name,
    g.n
FROM cross_join_lab.colors AS c
CROSS JOIN LATERAL generate_series(
    1,
    c.color_id
) AS g(n)
ORDER BY c.color_id, g.n;
~~~

Với dữ liệu:

~~~text
color_id = 1 (Đỏ)  -> generate_series(1,1): 1 hàng
color_id = 2 (Xanh)-> generate_series(1,2): 2 hàng
~~~

Kết quả có **3 hàng** chứ không phải `2 × một hằng số n`.

### 18.1. Vì sao cần LATERAL?

Trong một subquery hoặc function ở `FROM`, `LATERAL` cho phép nguồn bên phải tham chiếu cột từ nguồn bên trái đã xuất hiện trước đó.

Mẫu khái niệm:

~~~text
For each row LEFT:
    evaluate RIGHT using values from LEFT
    emit every row returned by RIGHT
~~~

Số hàng được tính:

\[
N = \sum_{\text{mỗi hàng }a \in A} |\text{right}(a)|
\]

Đây là tổng số hàng bên phải sinh ra theo từng hàng trái, không nhất thiết là tích của hai cardinalities cố định.

### 18.2. Với function trong FROM, LATERAL có thể được ngầm hiểu

Trong PostgreSQL, một số function ở `FROM` có thể tham chiếu cột của nguồn trước đó mà không ghi từ khóa `LATERAL` tường minh.

Tuy nhiên, ghi rõ `CROSS JOIN LATERAL` giúp người đọc thấy sự phụ thuộc và tránh nhầm một nguồn độc lập với nguồn tính cho từng hàng.

## 19. CROSS JOIN LATERAL với mảng theo từng hàng

Tạo bảng đơn hàng có danh sách tag:

~~~sql
CREATE TABLE cross_join_lab.order_tags (
    order_id INTEGER PRIMARY KEY,
    tags TEXT[]
);

INSERT INTO cross_join_lab.order_tags (order_id, tags)
VALUES
    (101, ARRAY['new', 'priority']),
    (102, ARRAY['gift']),
    (103, ARRAY[]::TEXT[]);
~~~

Lấy mỗi tag thành một hàng:

~~~sql
SELECT
    o.order_id,
    t.tag
FROM cross_join_lab.order_tags AS o
CROSS JOIN LATERAL unnest(o.tags) AS t(tag)
ORDER BY o.order_id, t.tag;
~~~

Kết quả:

| order_id | tag |
|---:|---|
| 101 | new |
| 101 | priority |
| 102 | gift |

Đơn 103 có mảng rỗng nên không xuất hiện.

### 19.1. Muốn giữ cả đơn có mảng rỗng

Dùng `LEFT JOIN LATERAL ... ON TRUE`:

~~~sql
SELECT
    o.order_id,
    t.tag
FROM cross_join_lab.order_tags AS o
LEFT JOIN LATERAL unnest(o.tags) AS t(tag)
    ON TRUE
ORDER BY o.order_id, t.tag NULLS LAST;
~~~

Kết quả có thêm đơn 103 với `tag IS NULL`. Đây là khác biệt quan trọng giữa **CROSS JOIN LATERAL** và **LEFT JOIN LATERAL** khi nguồn bên phải có thể trả 0 hàng.

### 19.2. Tránh nhân dữ liệu ngoài ý muốn khi unnest

Nếu một hàng có mảng 100 phần tử và query ghép thêm một mảng 50 phần tử bằng CROSS JOIN, bạn có thể tạo 5.000 cặp cho một hàng cha. Nếu mục đích là ghép **theo vị trí tương ứng** giữa hai mảng, CROSS JOIN hai unnest là sai; cần kỹ thuật giữ vị trí như `WITH ORDINALITY` hoặc hàm nhiều mảng theo semantics phù hợp.

## 20. CROSS JOIN hay LATERAL subquery để chọn dữ liệu liên quan?

Giả sử muốn lấy **hai đơn mới nhất của từng khách**. Câu hỏi này không yêu cầu mọi cặp khách–đơn; nó yêu cầu một tập con phụ thuộc khách hiện tại.

Một hướng PostgreSQL:

~~~sql
SELECT
    c.customer_id,
    latest.order_id,
    latest.created_at
FROM customers AS c
CROSS JOIN LATERAL (
    SELECT o.order_id, o.created_at
    FROM orders AS o
    WHERE o.customer_id = c.customer_id
    ORDER BY o.created_at DESC, o.order_id DESC
    LIMIT 2
) AS latest;
~~~

Ví dụ này giả định bảng `customers</BT> và `orders</BT> tương ứng đã tồn tại.

Mỗi khách sinh tối đa 2 hàng. Khách không có đơn sẽ không xuất hiện vì là **CROSS JOIN LATERAL**.

Nếu muốn giữ khách không có đơn:

~~~sql
SELECT
    c.customer_id,
    latest.order_id,
    latest.created_at
FROM customers AS c
LEFT JOIN LATERAL (
    SELECT o.order_id, o.created_at
    FROM orders AS o
    WHERE o.customer_id = c.customer_id
    ORDER BY o.created_at DESC, o.order_id DESC
    LIMIT 2
) AS latest
    ON TRUE;
~~~

### 20.1. Vì sao không tự CROSS JOIN toàn bộ orders?

Lấy tất cả `customers × orders` rồi lọc/đánh số để tìm hai đơn mới nhất có thể tạo một lượng cặp không cần thiết. LATERAL subquery có điều kiện theo khách thể hiện nhu cầu rõ hơn.

Với index phù hợp như `orders(customer_id, created_at DESC, order_id DESC)`, truy vấn top-N theo khách có thể hiệu quả; vẫn cần EXPLAIN trên dữ liệu thật.

### 20.2. Cẩn thận với số lần thực thi nguồn phụ thuộc

Nếu outer relation có 1 triệu khách, nguồn LATERAL có thể phải được tính theo từng hàng hoặc có cách thực thi khác do planner chọn. Đừng coi LATERAL luôn nhanh chỉ vì mỗi bên trả ít hàng; đánh giá bằng kế hoạch và số lần lặp thực tế.

## 21. CROSS JOIN để gắn một hàng tổng hợp

Một aggregate không có `GROUP BY` thường trả **một hàng**, kể cả tập đầu vào rỗng (các hàm như `MAX</BT> trả NULL). Vì vậy có thể dùng CROSS JOIN để đưa một giá trị tổng hợp vào mỗi hàng.

Ví dụ với dữ liệu lab:

~~~sql
SELECT
    c.color_name,
    totals.size_count
FROM cross_join_lab.colors AS c
CROSS JOIN (
    SELECT COUNT(*) AS size_count
    FROM cross_join_lab.sizes
) AS totals
ORDER BY c.color_id;
~~~

Bảng `totals` có một hàng với `size_count = 3`, nên kết quả có hai hàng.

### 21.1. Phân biệt scalar aggregate với truy vấn 0 hàng

~~~sql
SELECT COUNT(*)
FROM cross_join_lab.sizes
WHERE FALSE;
~~~

Trả một hàng, giá trị 0.

Nhưng:

~~~sql
SELECT size_code
FROM cross_join_lab.sizes
WHERE FALSE;
~~~

Trả 0 hàng.

Nếu CROSS JOIN với trường hợp thứ hai, **toàn bộ kết quả rỗng**. Trước khi dùng CROSS JOIN để gắn “một dòng cấu hình”, phải hiểu truy vấn đó có bảo đảm trả đúng một hàng không.

### 21.2. Window function có thể phù hợp hơn

Nếu mục tiêu là gắn tổng số hàng của chính kết quả vào mỗi hàng, có thể dùng:

~~~sql
SELECT
    c.color_name,
    COUNT(*) OVER () AS total_colors
FROM cross_join_lab.colors AS c
ORDER BY c.color_id;
~~~

Không cần CROSS JOIN một subquery tổng hợp cho trường hợp này. Chọn công cụ biểu đạt đúng mục tiêu và xem chi phí thực tế.

## 22. CROSS JOIN với nhiều nguồn dữ liệu quan hệ

Không phải mọi chiều nên CROSS JOIN thẳng với mọi chiều khác. Cần phân biệt **chiều độc lập** và **quan hệ phụ thuộc**.

Giả sử:

~~~text
stores
store_products (chỉ những sản phẩm được bán tại cửa hàng)
products
calendar_days
~~~

Nếu cần doanh thu/khả năng hiển thị theo từng ngày cho các cặp cửa hàng–sản phẩm hợp lệ, logic thường là:

~~~sql
SELECT
    sp.store_id,
    sp.product_id,
    d.day_start::DATE AS report_day
FROM store_products AS sp
CROSS JOIN generate_series(
    TIMESTAMP '2026-11-14',
    TIMESTAMP '2026-11-20',
    INTERVAL '1 day'
) AS d(day_start);
~~~

Ví dụ giả định bảng `store_products</BT> có những cặp hợp lệ.

Không nên tự:

~~~sql
FROM stores CROSS JOIN products CROSS JOIN calendar_days
~~~

nếu không phải mọi cửa hàng đều bán mọi sản phẩm. Phép nhân này có thể tạo dữ liệu **không có ý nghĩa nghiệp vụ** và gây bùng nổ số hàng.

### 22.1. Phân tích cardinality theo từng bước

~~~text
1. stores JOIN store_products:
   2.500 cặp store-product hợp lệ

2. CROSS JOIN 7 ngày:
   2.500 × 7 = 17.500 hàng

So với:
   100 stores × 10.000 products × 7 ngày
   = 7.000.000 hàng
~~~

Thiết kế nguồn đầu vào đúng quan hệ có thể giảm tập cần xử lý hàng trăm lần.

## 23. EXPLAIN: nhìn chi phí thay vì đoán

PostgreSQL có thể dùng:

~~~sql
EXPLAIN
SELECT
    c.color_name,
    s.size_code
FROM cross_join_lab.colors AS c
CROSS JOIN cross_join_lab.sizes AS s;
~~~

`EXPLAIN</BT> hiển thị kế hoạch dự kiến, gồm chi phí và ước lượng hàng. Nó không chạy toàn bộ SELECT như `EXPLAIN ANALYZE</BT>.

### 23.1. EXPLAIN ANALYZE cho tập lab nhỏ

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT
    c.color_name,
    s.size_code
FROM cross_join_lab.colors AS c
CROSS JOIN cross_join_lab.sizes AS s
ORDER BY c.color_id, s.sort_rank;
~~~

Cần xem:

- **Plan node** (Nested Loop, Sort hoặc những node khác).
- **rows** ước lượng và thực tế.
- **loops** số lần node con được chạy.
- **Execution Time**.
- **Buffers** được sử dụng trong phạm vi thống kê.

Không mặc định mỗi CROSS JOIN luôn được thực hiện bằng một thuật toán vật lý duy nhất. Kế hoạch có thể khác tùy dữ liệu, index, điều kiện và phiên bản PostgreSQL.

### 23.2. Nested Loop thường dễ hình dung

Một cách thực thi khả dĩ:

~~~text
For each row c in colors:
    For each row s in sizes:
        emit (c, s)
~~~

Đây là mô hình gần với Nested Loop khi không có điều kiện nối. Nhưng planner có thể thêm materialize, sort hoặc chọn cách thực thi khác phù hợp; **câu lệnh SQL quy định kết quả logic**, không bắt buộc mọi chi tiết vật lý.

### 23.3. EXPLAIN ANALYZE thực sự chạy truy vấn

Khi dùng:

~~~sql
EXPLAIN (ANALYZE, BUFFERS) SELECT ...;
~~~

PostgreSQL thực sự thực thi SELECT để đo thời gian và hàng thực tế. Với câu `INSERT</BT>, `UPDATE</BT> hoặc `DELETE</BT>, `EXPLAIN ANALYZE` cũng thực hiện thay đổi dữ liệu nếu không được rollback thích hợp.

Không chạy một CROSS JOIN dự kiến sinh hàng tỷ cặp chỉ để xem “nó chậm đến mức nào”. Hãy dùng **EXPLAIN không ANALYZE** để kiểm tra kế hoạch ban đầu.

## 24. Planner có thể đổi thứ tự JOIN

Về mặt đại số, với những INNER JOIN/CROSS JOIN phù hợp, optimizer có thể biến đổi cách kết hợp để giảm chi phí mà giữ cùng kết quả logic.

Ví dụ:

~~~sql
SELECT ...
FROM a
CROSS JOIN b
JOIN c ON c.id = a.c_id;
~~~

Không nhất thiết PostgreSQL phải vật lý hóa toàn bộ `a × b` trước rồi mới nối với c. Planner có thể xem xét cách đẩy điều kiện và sắp xếp join thích hợp.

### 24.1. Không suy đoán thứ tự vật lý từ thứ tự FROM

SQL viết:

~~~sql
FROM a CROSS JOIN b CROSS JOIN c
~~~

không cam kết vòng lặp thực thi luôn theo thứ tự a→b→c.

### 24.2. Các giới hạn lập kế hoạch

PostgreSQL có các tham số ảnh hưởng việc gộp/đổi thứ tự join, như `join_collapse_limit` và `from_collapse_limit`. Các truy vấn cực nhiều bảng có thể ảnh hưởng chi phí tối ưu hóa.

Bài học này không yêu cầu chỉnh các tham số đó. Khi gặp truy vấn nhiều JOIN, trước tiên hãy đảm bảo quan hệ đúng, bộ lọc rõ và thống kê cập nhật rồi mới xem xét cấu hình planner.

### 24.3. Cardinality estimates quan trọng

Nếu planner đánh giá sai số hàng sau bộ lọc hoặc phép nối, nó có thể chọn kế hoạch kém phù hợp. Có thể cần:

- `ANALYZE` để cập nhật thống kê.
- Index phù hợp cho các bộ lọc hoặc quan hệ khác trong query.
- Giảm dữ liệu đầu vào theo nghiệp vụ.
- Viết lại truy vấn để tránh tổ hợp không cần thiết.
- Kiểm tra correlations/extended statistics khi phù hợp.

Nhưng **không có index thần kỳ** biến việc thực sự cần xuất 500 triệu tổ hợp thành công việc nhỏ như vài nghìn hàng.

## 25. Cardinality explosion: nguy cơ thực tế

Giả sử hai bảng có:

~~~text
A: 100.000 hàng
B: 100.000 hàng
~~~

Tích Descartes có **10.000.000.000** cặp.

Nếu mỗi hàng kết quả chứa nhiều cột, riêng quá trình truyền hàng tới ứng dụng đã có thể tốn thời gian và băng thông khổng lồ. Nếu thêm `ORDER BY</BT>, `DISTINCT</BT> hoặc tổng hợp, query có thể cần thêm CPU, bộ nhớ xử lý và tệp tạm.

### 25.1. LIMIT không phải phương pháp chống nổ an toàn

~~~sql
SELECT ...
FROM big_table_a
CROSS JOIN big_table_b
LIMIT 100;
~~~

Với một số kế hoạch đơn giản, PostgreSQL có thể dừng sớm sau 100 hàng. Tuy nhiên, nếu có `ORDER BY` yêu cầu xét rất nhiều hàng, `DISTINCT`, aggregate hoặc những thao tác khác, LIMIT **không bảo đảm** query chỉ làm công việc tương ứng 100 cặp.

Ngoài ra, LIMIT không sửa sai logic nếu mục đích ban đầu phải là JOIN theo khóa.

### 25.2. COUNT(*) không biến mọi tích lớn thành rẻ

~~~sql
SELECT COUNT(*)
FROM big_table_a
CROSS JOIN big_table_b;
~~~

Kết quả logic chỉ có một hàng, nhưng server có thể phải xử lý khối lượng lớn để tính theo kế hoạch. Đừng coi “chỉ lấy COUNT” chắc chắn không tốn tài nguyên.

Nếu chỉ muốn **dự đoán số tổ hợp độc lập**, có thể dùng số hàng từng nguồn và phép nhân, nhưng tính `COUNT(*)` trên từng bảng lớn cũng cần đánh giá chi phí.

### 25.3. Sử dụng ước lượng trước

Một phép tính ngoài truy vấn:

~~~text
Expected combinations =
    count_of_filtered_left
    × count_of_filtered_right
~~~

Với nhiều chiều:

~~~text
Expected combinations =
    n1 × n2 × n3 × ... × nk
~~~

Cần đặt ngưỡng hợp lý cho report/job và xác định xem **người dùng thật sự cần mọi tổ hợp hay không** trước khi chạy.

## 26. Cách dự báo số hàng an toàn bằng SQL

Với bộ lab nhỏ:

~~~sql
SELECT
    c.n_colors,
    s.n_sizes,
    c.n_colors * s.n_sizes AS expected_pairs
FROM (
    SELECT COUNT(*)::NUMERIC AS n_colors
    FROM cross_join_lab.colors
) AS c
CROSS JOIN (
    SELECT COUNT(*)::NUMERIC AS n_sizes
    FROM cross_join_lab.sizes
) AS s;
~~~

Hai subquery aggregate mỗi bên trả một hàng; CROSS JOIN lúc này chỉ tạo **một hàng** chứa số liệu.

Dùng `NUMERIC` cho phép nhân giúp tránh tràn kiểu số nguyên trong những phép dự báo rất lớn. Tuy nhiên, cách tính này vẫn cần quét/đếm dữ liệu từng nguồn; đối với bảng cực lớn có thể dùng thống kê ước lượng hoặc công cụ quan sát khác tùy mục đích.

### 26.1. Số lượng sau WHERE mới là đầu vào thực tế

Nếu chỉ cần sản phẩm đang active:

~~~sql
SELECT COUNT(*)
FROM products
WHERE active = TRUE;
~~~

Hãy dự báo bằng **tập đã lọc theo nghiệp vụ**, không mặc định sử dụng toàn bộ bảng nếu query thực tế chỉ xét một tập nhỏ.

### 26.2. Khi có LATERAL, phép nhân hai số cố định không đủ

Với:

~~~sql
SELECT c.color_id, g.n
FROM cross_join_lab.colors AS c
CROSS JOIN LATERAL generate_series(1, c.color_id) AS g(n);
~~~

mỗi hàng có số kết quả bên phải khác nhau. Số hàng tổng là **tổng kích thước đầu ra theo từng hàng**, không đơn giản là số hàng colors nhân một số hàng cố định của generate_series.

## 27. CROSS JOIN và bộ nhớ, CPU, I/O

Khi kết quả lớn, chi phí có thể xuất hiện ở nhiều tầng:

| Tầng | Rủi ro |
|---|---|
| CPU | Xử lý nhiều cặp, biểu thức và điều kiện lọc |
| Memory | Sort, hash, aggregate và trạng thái query |
| Temporary files | Phép sắp xếp/tổng hợp vượt bộ nhớ xử lý |
| Disk I/O | Quét nhiều trang input hoặc ghi tệp tạm |
| Network | Truyền lượng kết quả lớn tới client |
| Application | Parse hàng triệu record, OOM ở client |
| Database concurrency | Query chiếm tài nguyên làm chậm workload khác |

Không thể giải quyết mọi trường hợp bằng cách tăng `work_mem`. Nếu query thực sự sinh dữ liệu không cần thiết, **giảm số tổ hợp** là ưu tiên quan trọng.

### 27.1. Kéo dữ liệu về ứng dụng rồi nhân ở đó còn tệ hơn?

Không có quy tắc tuyệt đối. Sinh tổ hợp ngay tại database có thể giúp lọc và kết hợp với dữ liệu thực hiệu quả, nhưng nếu bạn tải toàn bộ kết quả hàng tỷ cặp về API thì vẫn có vấn đề lớn.

Một hệ thống có thể cần:

- Chia nhỏ báo cáo theo ngày/địa điểm.
- Phân trang có khóa ổn định.
- Xử lý theo batch.
- Chỉ tạo tổ hợp đủ điều kiện.
- Tổng hợp sớm tại nơi thích hợp.
- Lưu một bảng chuẩn hóa các tổ hợp được phép thay vì sinh toàn bộ mỗi lần.

Cách chọn dựa trên nhu cầu nghiệp vụ, workload và phép đo.

## 28. CROSS JOIN với dữ liệu có thể trùng

Giả sử một dimension chứa hai hàng cùng tên:

~~~sql
SELECT a.label, b.slot
FROM (VALUES ('A'), ('A')) AS a(label)
CROSS JOIN (VALUES (1), (2)) AS b(slot);
~~~

Kết quả gồm 4 hàng, dù chỉ có 2 giá trị cặp phân biệt.

### 28.1. UNIQUE trên dimension có thể giúp mô hình rõ hơn

Nếu màu phải là danh mục duy nhất, một cột `color_name UNIQUE` hoặc khóa nghiệp vụ phù hợp có thể ngăn dữ liệu trùng. Trong lab, bảng `cross_join_lab.colors` đã có `UNIQUE(color_name)`.

### 28.2. DISTINCT chỉ nên dùng khi bài toán yêu cầu tập phân biệt

~~~sql
SELECT DISTINCT a.label, b.slot
FROM (VALUES ('A'), ('A')) AS a(label)
CROSS JOIN (VALUES (1), (2)) AS b(slot);
~~~

Kết quả còn 2 hàng, nhưng PostgreSQL vẫn cần xử lý ngữ nghĩa loại trùng, có thể tốn chi phí. Nếu mục đích thực là một danh mục duy nhất, xử lý dữ liệu nguồn hoặc dùng query sinh dimension phân biệt rõ ràng thường đáng cân nhắc hơn.

## 29. Tương tác với aggregate và tính KPI

Một phép CROSS JOIN ngoài ý muốn có thể biến KPI đúng thành sai.

Giả sử đơn hàng có doanh thu:

~~~text
Order 1: 100
Order 2: 200
Tổng thực: 300
~~~

Nếu vô tình CROSS JOIN với 3 vùng:

~~~text
Order 1 × 3 vùng -> 100 xuất hiện 3 lần
Order 2 × 3 vùng -> 200 xuất hiện 3 lần
Tổng sau CROSS JOIN: 900
~~~

Dù câu `SUM(amount)` chỉ trả một hàng, kết quả đã bị nhân.

### 29.1. Đặt câu hỏi “một hàng nghĩa là gì?”

Trước mỗi JOIN trong báo cáo, xác định:

- Một hàng của từng bảng biểu diễn cái gì?
- Quan hệ dự kiến là 1:1, 1:N hay N:M?
- Số hàng sau JOIN có được phép tăng không?
- Có cần khử trùng theo một khóa xác định không?
- CROSS JOIN có thật sự cần mọi tổ hợp không?

Đây là cách tránh lỗi “fanout” trong BI khi join dữ liệu mà không hiểu cardinality.

### 29.2. COUNT(*) và COUNT(DISTINCT key) khác nhau

Sau CROSS JOIN, `COUNT(*)` đếm số **cặp**. `COUNT(DISTINCT order_id)` đếm số order ID phân biệt nếu key hiện diện, nhưng điều đó không sửa tất cả aggregate khác.

Đừng áp dụng `COUNT(DISTINCT ...)` như một bản vá chung cho mô hình JOIN sai.

## 30. CROSS JOIN có thể phù hợp với thử nghiệm tổ hợp

Một số bài toán không phải dữ liệu nghiệp vụ:

- Tạo tập tham số để test nhiều cấu hình.
- Tạo ma trận hệ điều hành × trình duyệt × phiên bản.
- Tạo bộ tổ hợp số/ngày/khung giờ.
- Tạo ma trận giả thuyết “mỗi chính sách × mỗi phân khúc”.
- Liệt kê những cặp cần đánh giá trước khi kiểm tra điều kiện.

Ví dụ tạo ma trận môi trường kiểm thử:

~~~sql
SELECT
    os.os_name,
    browser.browser_name,
    viewport.viewport_name
FROM (VALUES ('Windows'), ('Linux')) AS os(os_name)
CROSS JOIN (
    VALUES ('Chrome'), ('Firefox')
) AS browser(browser_name)
CROSS JOIN (
    VALUES ('Desktop'), ('Mobile')
) AS viewport(viewport_name)
ORDER BY os.os_name, browser.browser_name, viewport.viewport_name;
~~~

Số tổ hợp: `2 × 2 × 2 = 8`.

Khi số chiều tăng, cần dùng rule loại tổ hợp không được hỗ trợ (ví dụ một trình duyệt không có trên hệ điều hành) trước khi chuyển tổ hợp thành test case thật.

## 31. CROSS JOIN không đồng nghĩa “mọi thứ đều tồn tại”

Khi sinh ma trận sản phẩm × màu × kích cỡ, không nên gắn nhãn “SKU hiện có” cho tất cả cặp nếu chưa có bản ghi SKU.

Tương tự, ma trận cửa hàng × ngày không chứng minh có dữ liệu doanh thu từng ngày; nó chỉ xác định **những ô báo cáo muốn xuất hiện**.

Phân biệt:

~~~text
Tổ hợp khả dĩ về toán học
            |
            v
Tổ hợp hợp lệ theo nghiệp vụ
            |
            v
Tổ hợp đã được đăng ký trong dữ liệu
            |
            v
Tổ hợp đang có trạng thái/giá trị thực tế
~~~

CROSS JOIN chỉ trực tiếp giải quyết tầng đầu; các tầng sau cần constraints, JOIN hoặc dữ liệu quan hệ thực.

## 32. Tenant và bảo mật khi tạo mọi tổ hợp

Trong hệ thống đa tenant, tự ghép tất cả users với tất cả stores hoặc tất cả products có thể tạo các cặp **không được phép** theo chính sách phân quyền.

~~~sql
-- Sai về nghiệp vụ nếu mọi user không được truy cập mọi store:
-- SELECT *
-- FROM users CROSS JOIN stores;
~~~

Ngay cả khi PostgreSQL bảo vệ các bảng bằng RLS, việc tạo tổ hợp chỉ từ những hàng người dùng có quyền đọc vẫn không tự chứng minh **mọi cặp giữa các hàng đó** đều là cặp được phép theo business policy.

Hãy xác định tập quan hệ hợp lệ qua bảng mapping, owner/tenant key và authorization.

### 32.1. CROSS JOIN không thay JOIN theo tenant_id

Nếu khách hàng thuộc tenant A và đơn hàng thuộc tenant B nhưng truy vấn chỉ CROSS JOIN hai bảng rồi thêm bộ lọc thiếu tenant, có thể sinh cặp sai.

Nên dùng điều kiện nối/tenant-aware keys phù hợp:

~~~sql
SELECT
    o.order_id,
    c.customer_id
FROM orders AS o
JOIN customers AS c
    ON c.customer_id = o.customer_id
   AND c.tenant_id = o.tenant_id;
~~~

Đây là cấu trúc minh họa; phải xem mô hình khóa và quyền thật của hệ thống. Không dùng CROSS JOIN để tránh phải viết điều kiện quan hệ.

## 33. Quy trình thiết kế một CROSS JOIN an toàn

Trước khi chạy trên dữ liệu lớn:

1. **Nêu lý do phải có mọi cặp.** Nếu muốn ghép theo khóa, dùng INNER/LEFT JOIN thay vì CROSS JOIN.
2. **Định nghĩa granularity** của từng nguồn: một hàng là gì?
3. **Đếm hoặc ước lượng kích thước từng nguồn sau bộ lọc**.
4. **Nhân số hàng các chiều** để dự báo kết quả.
5. **Kiểm tra nguồn có thể rỗng hay trả nhiều hơn một hàng ngoài dự kiến**.
6. **Phân biệt tổ hợp toán học với tổ hợp hợp lệ theo nghiệp vụ**.
7. **Lọc dimension và quan hệ hợp lệ trước khi sinh ma trận quá lớn**.
8. **Nếu cần lấp ô thiếu**, dùng CROSS JOIN bộ khung rồi LEFT JOIN dữ liệu thật.
9. **Nếu nguồn phụ thuộc hàng bên trái**, xem CROSS JOIN LATERAL hoặc LEFT JOIN LATERAL.
10. **Dùng EXPLAIN trước** nếu quy mô có nguy cơ lớn.
11. **Kiểm tra aggregate và fanout**, đặc biệt SUM/COUNT sau JOIN.
12. **Kiểm soát CPU, I/O, memory và kích thước response**, không coi LIMIT là cách cứu mọi truy vấn.
13. **Đặt ORDER BY** nếu người dùng cần thứ tự cố định.
14. **Kiểm tra quyền/tenant** trước khi sinh hoặc trả tổ hợp.
15. **Viết test cardinality** cho những query quan trọng.

Một JOIN đúng là JOIN vừa trả đúng **hàng có ý nghĩa**, vừa có chi phí phù hợp với workload.

## 34. Những lỗi thường gặp

### 34.1. “CROSS JOIN có thể tự tìm khóa chung”

Không. Nó tạo mọi cặp bất kể khóa.

### 34.2. “Có 100 hàng và 200 hàng nên CROSS JOIN ra 300 hàng”

Không. Kết quả có 20.000 cặp.

### 34.3. “CROSS JOIN luôn trả ít nhất số hàng của bảng trái”

Không. Nếu bảng phải rỗng, kết quả bằng 0.

### 34.4. “NULL làm hàng bị loại khỏi CROSS JOIN”

Không. NULL không tự làm mất cặp; điều kiện lọc mới có thể làm điều đó.

### 34.5. “CROSS JOIN có thể viết ON như INNER JOIN”

Không. `CROSS JOIN` không dùng `ON`/`USING` trực tiếp.

### 34.6. “INNER JOIN ON TRUE và LEFT JOIN ON TRUE luôn giống CROSS JOIN”

INNER JOIN ON TRUE phù hợp tương đương khi không có yếu tố khác. LEFT JOIN ON TRUE khác khi bên phải rỗng.

### 34.7. “Viết dấu phẩy trong FROM luôn dễ đọc hơn”

Không. Cú pháp tường minh giúp phân biệt chủ đích tạo mọi cặp với lỗi quên điều kiện.

### 34.8. “WHERE sau CROSS JOIN buộc DB tạo đủ mọi cặp trong RAM”

Không nhất thiết. Planner có thể đẩy bộ lọc và đổi kế hoạch.

### 34.9. “LIMIT 10 chắc chắn chỉ xử lý 10 cặp”

Không. ORDER BY, DISTINCT, aggregate hoặc kế hoạch khác có thể xử lý nhiều hơn.

### 34.10. “DISTINCT sẽ sửa lỗi quên điều kiện JOIN”

Không. DISTINCT có thể che số hàng trùng nhưng không khôi phục quan hệ đúng.

### 34.11. “Không có dòng giao dịch thì báo cáo phải bỏ ngày đó”

Không phải lúc nào cũng đúng. CROSS JOIN tạo bộ khung ngày × đối tượng, rồi LEFT JOIN để giữ ngày thiếu.

### 34.12. “COALESCE NULL thành 0 luôn chính xác”

Không. Thiếu bản ghi có thể nghĩa là chưa có dữ liệu, không phải giá trị 0.

### 34.13. “CROSS JOIN LATERAL luôn có số hàng m × n”

Không. Nguồn bên phải có thể trả số hàng khác nhau cho từng hàng bên trái.

### 34.14. “Bảng phải rỗng thì CROSS JOIN LATERAL vẫn giữ bảng trái”

Không. Cần `LEFT JOIN LATERAL ... ON TRUE` nếu muốn giữ hàng trái khi hàm trả 0 hàng.

### 34.15. “Có index là CROSS JOIN hàng tỷ cặp sẽ rẻ”

Không. Nếu thực sự cần xuất khối lượng tổ hợp đó, chi phí xử lý/đưa dữ liệu ra vẫn rất lớn.

### 34.16. “ORDER BY không cần vì PostgreSQL luôn đi từ hàng đầu của bảng trái”

Không. Thứ tự trả kết quả không được bảo đảm nếu thiếu ORDER BY.

### 34.17. “Tích cửa hàng × sản phẩm là tập sản phẩm có bán”

Không, trừ khi nghiệp vụ cho phép mọi cặp. Cần bảng liên kết hoặc lọc phù hợp.

## 35. Bài tập thực hành

### Bài 1 — Dự đoán kết quả

A có 4 hàng và B có 7 hàng. `A CROSS JOIN B` có bao nhiêu hàng?

**Gợi ý:** 4 × 7 = 28.

### Bài 2 — Bên phải rỗng

A có 10 hàng, B có 0 hàng. CROSS JOIN trả gì?

**Đáp án:** 0 hàng, không phải 10 hàng có NULL.

### Bài 3 — Tạo tổ hợp màu × cỡ

Dùng `cross_join_lab.colors` và `cross_join_lab.sizes` để hiển thị 6 biến thể.

~~~sql
SELECT
    c.color_name,
    s.size_code
FROM cross_join_lab.colors AS c
CROSS JOIN cross_join_lab.sizes AS s
ORDER BY c.color_id, s.sort_rank;
~~~

### Bài 4 — Không có ORDER BY

Nếu bỏ `ORDER BY` khỏi bài 3, bạn có thể bảo đảm hàng “Đỏ–S” xuất hiện đầu tiên không?

**Gợi ý:** Không.

### Bài 5 — NULL

Bên trái có một hàng `NULL` và một hàng `1`, bên phải có hai hàng. CROSS JOIN có bao nhiêu hàng?

**Gợi ý:** 2 × 2 = 4.

### Bài 6 — Viết lại JOIN theo khóa

Một query sai:

~~~sql
SELECT o.order_id, c.customer_name
FROM orders AS o
CROSS JOIN customers AS c;
~~~

Hãy viết lại theo `o.customer_id = c.customer_id`.

**Đáp án gợi ý:**

~~~sql
SELECT o.order_id, c.customer_name
FROM orders AS o
JOIN customers AS c
    ON c.customer_id = o.customer_id;
~~~

### Bài 7 — INNER JOIN ON TRUE

Khi nào `INNER JOIN b ON TRUE` tương đương `CROSS JOIN b`?

**Gợi ý:** Khi xét hai nguồn và điều kiện luôn đúng, về kết quả tập cặp.

### Bài 8 — Bộ khung báo cáo

Có 5 cửa hàng và 7 ngày. Hỏi bộ khung có bao nhiêu hàng trước LEFT JOIN doanh thu?

**Gợi ý:** 35.

### Bài 9 — Ngày không có doanh thu

Vì sao chỉ `GROUP BY sale_day</BT> trên bảng giao dịch không thể hiển thị ngày không có bản ghi?

**Gợi ý:** Không có hàng nguồn cho ngày đó; cần tập ngày riêng và LEFT JOIN.

### Bài 10 — WHERE trên LEFT JOIN

Trong truy vấn tạo cửa hàng × ngày, thêm `WHERE ds.revenue > 0` làm gì với hàng không có giao dịch?

**Gợi ý:** Hàng có ds.revenue NULL bị loại.

### Bài 11 — generate_series

Sinh ba ngày 14–16/11/2026 và hai giờ 09:00, 14:00. Kết quả có bao nhiêu hàng?

**Đáp án:** 3 × 2 = 6.

### Bài 12 — Ba chiều

20 cửa hàng, 500 sản phẩm, 30 ngày. Có bao nhiêu tổ hợp?

**Gợi ý:** 20 × 500 × 30 = 300.000.

### Bài 13 — Tổ hợp không hợp lệ

Nếu mỗi cửa hàng chỉ bán 10 sản phẩm trong 500 sản phẩm có sẵn, nên CROSS JOIN thẳng 20 × 500 hay dùng bảng store_products trước?

**Gợi ý:** Dùng các cặp store-product hợp lệ trước, rồi trải ngày.

### Bài 14 — Self CROSS JOIN

Với 5 người, số cặp có hướng khác nhau khi dùng điều kiện `a.id <> b.id` là bao nhiêu?

**Gợi ý:** 5 × 4 = 20.

### Bài 15 — Cặp không có thứ tự

Với 5 người, `a.id < b.id` sinh bao nhiêu cặp?

**Gợi ý:** 5 × 4 / 2 = 10.

### Bài 16 — LATERAL theo hàng

Màu có color_id 1 và 2; `CROSS JOIN LATERAL generate_series(1,color_id)` trả bao nhiêu hàng?

**Gợi ý:** 1 + 2 = 3.

### Bài 17 — LATERAL với mảng rỗng

Một đơn có tags rỗng. Nó có xuất hiện khi dùng `CROSS JOIN LATERAL unnest(tags)` không?

**Gợi ý:** Không; dùng LEFT JOIN LATERAL ON TRUE nếu cần giữ đơn.

### Bài 18 — Tính số lượng trước khi chạy

Hai bảng có 80.000 và 50.000 hàng. Tích Descartes có bao nhiêu cặp?

**Gợi ý:** 4.000.000.000; đây là mức cần cân nhắc rất kỹ trước khi thực thi.

### Bài 19 — LIMIT

Vì sao `ORDER BY ... LIMIT 20` trên một CROSS JOIN lớn vẫn có thể đắt?

**Gợi ý:** Server có thể phải xét rất nhiều cặp để tìm 20 hàng đầu theo điều kiện sắp xếp.

### Bài 20 — Tổng sai

Bạn tính SUM(order.amount) sau khi CROSS JOIN orders với 3 dòng category. Tổng tiền có thể bị sai thế nào?

**Gợi ý:** Mỗi order bị lặp ba lần nên SUM bị nhân ba nếu không có bộ lọc/quan hệ khác.

### Bài 21 — DISTINCT

Vì sao `SUM(DISTINCT amount)` không phải cách sửa đúng của bài 20?

**Gợi ý:** Hai đơn khác nhau có thể có cùng giá trị amount, khiến DISTINCT loại nhầm dữ liệu hợp lệ.

### Bài 22 — EXPLAIN

Bạn sắp chạy CROSS JOIN hai bảng lớn. Nên dùng `EXPLAIN` hay `EXPLAIN ANALYZE` trước để tránh vô tình tạo khối lượng thực thi khổng lồ?

**Gợi ý:** `EXPLAIN` không ANALYZE trước; chỉ thực thi đo khi đã đánh giá an toàn.

### Bài 23 — Đọc alias

Viết query CROSS JOIN hai bảng đều có `id`, và trả tên khác nhau để không mơ hồ.

**Gợi ý:** `SELECT a.id AS left_id, b.id AS right_id ...`.

### Bài 24 — Data scaffolding

Nếu không có bản ghi doanh thu, bạn có nên luôn `COALESCE(revenue,0)` không?

**Gợi ý:** Chỉ khi nghiệp vụ đảm bảo không có bản ghi nghĩa là 0; thiếu nguồn ETL có thể phải giữ NULL.

### Bài 25 — An toàn đa tenant

Tại sao việc CROSS JOIN mọi users với mọi stores có thể tạo cặp không hợp lệ dù từng user/store tồn tại?

**Gợi ý:** Quan hệ được phép giữa user và store không nhất thiết là mọi cặp; cần mapping/authorization.

## 36. Bảng ghi nhớ nhanh

| Câu hỏi | Trả lời |
|---|---|
| CROSS JOIN tạo gì? | Mọi cặp giữa hai nguồn |
| Công thức số hàng? | `m × n` |
| Ba nguồn? | `m × n × p` |
| Một bên rỗng? | Kết quả rỗng |
| NULL có ngăn cặp không? | Không |
| Hàng trùng có bị loại tự động không? | Không |
| CROSS JOIN có ON không? | Không |
| INNER JOIN ON TRUE tương đương? | Có về cặp hàng |
| Dấu phẩy trong FROM có thể tạo tích? | Có nếu không có điều kiện liên hệ |
| LEFT JOIN ON TRUE luôn tương đương? | Không, khác khi bên phải rỗng |
| CROSS JOIN có bảo đảm thứ tự? | Không |
| Muốn thứ tự cố định? | Dùng ORDER BY |
| Muốn ghép theo khóa? | INNER/LEFT JOIN ON phù hợp |
| Muốn mọi ngày × cửa hàng? | CROSS JOIN date dimension |
| Muốn điền dữ liệu có thể thiếu? | LEFT JOIN dữ liệu thực vào bộ khung |
| Muốn sinh ngày/số? | generate_series |
| Muốn nguồn phải phụ thuộc hàng trái? | CROSS JOIN LATERAL |
| Muốn giữ hàng trái nếu LATERAL trả 0? | LEFT JOIN LATERAL ON TRUE |
| Muốn cặp không phân biệt thứ tự? | Self CROSS JOIN với `a.id < b.id` |
| CROSS JOIN lớn có rủi ro gì? | Cardinality explosion, CPU/I/O/memory/network |
| LIMIT có đảm bảo xử lý ít cặp? | Không |
| WHERE có luôn thực thi sau khi materialize tích? | Không, planner có thể tối ưu |
| EXPLAIN có chạy SELECT đầy đủ? | Không |
| EXPLAIN ANALYZE có chạy? | Có |
| DISTINCT có sửa lỗi quên ON không? | Không |
| Một hàng dimension có thể là 0/1/n? | Có, phải hiểu nguồn đầu vào |
| Tổ hợp có luôn hợp lệ nghiệp vụ? | Không |
| Cần kiểm tra gì trước CROSS JOIN lớn? | Kích thước, mục tiêu, bộ lọc, EXPLAIN và tải |

---

## Kết luận

**`CROSS JOIN` là cách viết tường minh của tích Descartes trong PostgreSQL**: mỗi hàng bên trái kết hợp với mỗi hàng bên phải. Với hai nguồn có `m` và `n` hàng, kết quả có `m × n` hàng trước những phép lọc/tổng hợp tiếp theo. Đây là công cụ hữu ích khi cần sinh **mọi tổ hợp độc lập**, như màu × kích cỡ, ngày × khung giờ, tập cấu hình test hoặc bộ khung ngày × cửa hàng cho báo cáo.

Tuy nhiên, **cùng phép nhân hàng có thể là lỗi nghiêm trọng** nếu thực ra dữ liệu cần nối bằng khóa. CROSS JOIN không tự hiểu quan hệ, không loại bỏ NULL hay bản ghi trùng và không bảo đảm thứ tự kết quả. Khi số nguồn hoặc số hàng lớn, cardinality có thể bùng nổ và kéo theo CPU, memory, I/O, network cũng như lỗi tổng hợp KPI. `LIMIT` hoặc `DISTINCT` không phải thuốc chữa cho điều kiện JOIN bị thiếu.

Hãy dùng `INNER JOIN ... ON ...` khi cần quan hệ theo khóa; dùng **CROSS JOIN** khi thật sự cần mọi cặp; dùng **LEFT JOIN** để giữ bộ khung thiếu dữ liệu; và dùng **LATERAL** khi nguồn bên phải phụ thuộc từng hàng bên trái. Trước khi chạy truy vấn lớn, dự báo số tổ hợp, xác định tập đầu vào hợp lệ và xem `EXPLAIN`. Hiểu đúng tích Descartes giúp bạn vừa khai thác được sức mạnh sinh tổ hợp của PostgreSQL, vừa tránh những truy vấn trả hàng triệu bản ghi sai hoặc gây tải không cần thiết.
