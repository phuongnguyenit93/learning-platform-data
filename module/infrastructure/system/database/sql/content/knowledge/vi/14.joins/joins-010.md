# USING, NATURAL JOIN và rủi ro khi lược đồ thay đổi

Trong SQL, **JOIN** kết nối các hàng của hai nguồn dữ liệu theo một điều kiện phù hợp. Cách viết thường gặp nhất là **JOIN ... ON**, nơi chúng ta chỉ rõ hai cột nào phải bằng nhau. Ngoài ra, nhiều hệ quản trị còn hỗ trợ **JOIN ... USING** và **NATURAL JOIN**. Hai cách viết này có thể ngắn gọn hơn, đặc biệt khi các bảng có cột khóa trùng tên, nhưng chúng không hoàn toàn giống nhau về **cột đầu ra** và mức độ **phụ thuộc vào lược đồ**.

Ví dụ, nếu cả bảng **customers** và **orders** đều có cột **customer_id**, câu **JOIN ... USING (customer_id)** thể hiện rõ rằng hai bảng được ghép theo mã khách hàng. Còn **NATURAL JOIN** tự tìm **mọi cột trùng tên** của hai nguồn để làm điều kiện bằng nhau. Điều này nghe có vẻ thuận tiện, nhưng có thể gây lỗi khó phát hiện: **chỉ cần thêm một cột mới cùng tên vào hai bảng, điều kiện NATURAL JOIN có thể tự thay đổi dù câu SQL không thay đổi**.

Bài học thuộc chương **Kết nối bảng** của module **Database SQL**. Các ví dụ chính chạy trên **PostgreSQL 15 trở lên**, dùng bảng tạm để có thể học độc lập. Những khác biệt theo phương ngữ, đặc biệt với **MySQL, SQLite, Oracle và SQL Server**, được trình bày ở phần cuối.

## 1. Mục tiêu của bài học

Sau bài này, bạn có thể:

1. Phân biệt **ON**, **USING** và **NATURAL JOIN** về điều kiện ghép và danh sách cột trả về.
2. Viết **INNER, LEFT, RIGHT và FULL JOIN ... USING** khi có cột cùng tên.
3. Hiểu vì sao **SELECT \*** có thể trả ra các cột khác nhau giữa **ON** và **USING**.
4. Hiểu giá trị của cột khóa hợp nhất trong **OUTER JOIN ... USING**, kể cả hàng không ghép được.
5. Nhận diện cách **NULL**, quan hệ một-nhiều và điều kiện **WHERE** tác động đến số dòng kết quả.
6. Giải thích cơ chế **NATURAL JOIN** và chứng minh rủi ro khi **ALTER TABLE** làm xuất hiện cột trùng tên mới.
7. Biết cách thay NATURAL JOIN bằng **JOIN ... USING (danh sách khóa rõ ràng)** hoặc **JOIN ... ON** để bảo vệ ý nghĩa truy vấn.
8. Chọn cách JOIN có thể kiểm soát và bảo trì tốt khi hệ thống thay đổi lược đồ hoặc chuyển hệ quản trị.

## 2. Nhắc lại: JOIN tạo ra các cặp hàng thỏa điều kiện

Giả sử bảng **customers** lưu khách hàng, bảng **orders** lưu đơn hàng. Một khách có thể đặt nhiều đơn; có thể cũng có khách chưa đặt đơn nào. Mã liên kết là **customer_id**.

~~~text
customers                         orders
---------                         ------
customer_id   (PK) ◄───────────── customer_id
customer_name                       order_id (PK)
region                              order_status
                                    amount_vnd

Một khách hàng ──────── có thể có nhiều đơn hàng
~~~

Với **INNER JOIN**, chỉ các cặp hàng thỏa điều kiện nối mới được giữ:

~~~sql
SELECT
    c.customer_id,
    c.customer_name,
    o.order_id
FROM customers AS c
INNER JOIN orders AS o
    ON c.customer_id = o.customer_id;
~~~

Điều kiện sau từ khóa **ON** là:

~~~sql
c.customer_id = o.customer_id
~~~

Đây là phép so sánh rõ ràng giữa hai cột, không phụ thuộc chuyện hai cột có tên giống nhau hay không. Nếu bảng orders dùng tên **buyer_id** thay vì customer_id, ta vẫn có thể viết **ON c.customer_id = o.buyer_id**.

Trong khi đó, cú pháp:

~~~sql
INNER JOIN orders AS o USING (customer_id)
~~~

chỉ áp dụng khi **cả hai nguồn JOIN đều có một cột được đặt tên customer_id**. USING thể hiện một danh sách cột cùng tên sẽ được so sánh bằng nhau khi ghép.

**NATURAL JOIN** còn ngắn hơn:

~~~sql
NATURAL JOIN orders AS o
~~~

nhưng **không liệt kê cột ghép**. SQL tự chọn danh sách dựa trên **các tên cột hiện có** của hai nguồn. Vì vậy, NATURAL JOIN chỉ an toàn khi cơ chế tự chọn ấy thực sự là điều mà chúng ta muốn chấp nhận, kể cả sau khi schema thay đổi.

## 3. Chuẩn bị dữ liệu thực hành độc lập

Tạo hai bảng tạm **join_demo_customers** và **join_demo_orders** trong PostgreSQL. Để minh họa các loại JOIN, bảng orders cố ý chứa một đơn có customer_id không tồn tại và một đơn có customer_id NULL. Do đó ví dụ **không đặt FOREIGN KEY** ở bộ dữ liệu mẫu. Trong hệ thống thật, khóa ngoại thường được dùng để bảo vệ quan hệ này.

~~~sql
CREATE TEMP TABLE join_demo_customers (
    customer_id   INTEGER PRIMARY KEY,
    customer_name TEXT NOT NULL,
    region        TEXT NOT NULL
);

CREATE TEMP TABLE join_demo_orders (
    order_id     INTEGER PRIMARY KEY,
    customer_id  INTEGER,
    order_status TEXT NOT NULL,
    amount_vnd   NUMERIC(12, 2) NOT NULL
);

INSERT INTO join_demo_customers
    (customer_id, customer_name, region)
VALUES
    (1, 'An',   'Bac'),
    (2, 'Binh', 'Nam'),
    (3, 'Chi',  'Trung'),
    (4, 'Dung', 'Bac');

INSERT INTO join_demo_orders
    (order_id, customer_id, order_status, amount_vnd)
VALUES
    (101, 1,    'paid',    500000),
    (102, 1,    'pending', 200000),
    (103, 2,    'paid',    300000),
    (104, 99,   'paid',    400000),
    (105, NULL, 'pending', 100000);
~~~

Kiểm tra dữ liệu:

~~~sql
SELECT * FROM join_demo_customers ORDER BY customer_id;
SELECT * FROM join_demo_orders ORDER BY order_id;
~~~

Bảng khách hàng có **4 hàng**; bảng đơn hàng có **5 hàng**. Dữ liệu cố ý tạo các tình huống:

- Khách **1** có **hai** đơn: 101 và 102.
- Khách **2** có **một** đơn: 103.
- Khách **3** và **4** chưa có đơn.
- Đơn **104** tham chiếu customer_id **99**, không có khách tương ứng.
- Đơn **105** có customer_id **NULL**, nghĩa là chưa có mã khách để nối.

> Bảng tạm chỉ tồn tại trong phiên kết nối hiện tại. Nếu cần chạy lại CREATE TEMP TABLE trong cùng phiên, hãy xóa riêng các bảng tạm của bài hoặc mở phiên mới; không cần xóa bảng thật của hệ thống.

## 4. INNER JOIN: so sánh ON với USING

### 4.1. Viết bằng ON

~~~sql
SELECT
    c.customer_id,
    c.customer_name,
    o.order_id,
    o.amount_vnd
FROM join_demo_customers AS c
INNER JOIN join_demo_orders AS o
    ON c.customer_id = o.customer_id
ORDER BY o.order_id;
~~~

Kết quả:

| customer_id | customer_name | order_id | amount_vnd |
| ---: | --- | ---: | ---: |
| 1 | An | 101 | 500000 |
| 1 | An | 102 | 200000 |
| 2 | Binh | 103 | 300000 |

Chỉ ba đơn **101, 102, 103** ghép được với khách hàng. INNER JOIN không giữ hai đơn thiếu bản ghi khách tương ứng, cũng không giữ các khách chưa có đơn.

### 4.2. Viết bằng USING

~~~sql
SELECT
    customer_id,
    c.customer_name,
    o.order_id,
    o.amount_vnd
FROM join_demo_customers AS c
INNER JOIN join_demo_orders AS o
    USING (customer_id)
ORDER BY o.order_id;
~~~

Kết quả **giống truy vấn ON ở trên**. Cú pháp USING nói: “ghép hai nguồn theo **các cột cùng tên customer_id**”.

Trong PostgreSQL, khi dùng USING, bạn có thể tham chiếu **customer_id** không kèm alias vì cột này đã được hợp nhất trong **kết quả JOIN**. Đối với các cột còn lại có tên riêng, bạn vẫn có thể dùng alias **c.** và **o.** để giữ truy vấn dễ đọc.

### 4.3. Điểm khác biệt khi dùng SELECT *

Thử xem **tất cả cột** với ON:

~~~sql
SELECT *
FROM join_demo_customers AS c
JOIN join_demo_orders AS o
    ON c.customer_id = o.customer_id
ORDER BY o.order_id;
~~~

Danh sách cột đầu ra theo bảng mẫu gồm:

~~~text
customer_id | customer_name | region |
order_id | customer_id | order_status | amount_vnd
~~~

Có **hai cột mang tên customer_id**: một từ bảng customers, một từ bảng orders. Chúng có thể chứa giá trị bằng nhau ở các hàng đã ghép, nhưng vẫn là **hai cột riêng trong kết quả ON + SELECT \***.

Với USING:

~~~sql
SELECT *
FROM join_demo_customers AS c
JOIN join_demo_orders AS o
    USING (customer_id)
ORDER BY o.order_id;
~~~

Danh sách cột đầu ra sẽ gồm:

~~~text
customer_id | customer_name | region |
order_id | order_status | amount_vnd
~~~

**customer_id chỉ xuất hiện một lần** trong kết quả SELECT *.

Theo quy tắc PostgreSQL cho JOIN USING, thứ tự chung của danh sách cột khi SELECT * là:

1. Các cột được nêu trong **USING**, theo thứ tự đã liệt kê.
2. Những cột còn lại của nguồn **bên trái**.
3. Những cột còn lại của nguồn **bên phải**.

Trong ví dụ này customer_id được đưa lên đầu; các cột riêng của customers đi tiếp, rồi các cột riêng của orders.

**Lưu ý:** việc rút gọn cột trong kết quả JOIN không có nghĩa cơ sở dữ liệu xóa hoặc hợp nhất hai cột vật lý trong bảng gốc. Chỉ **cấu trúc kết quả JOIN** được quyết định khác đi.

### 4.4. Khi nên dùng ON thay vì USING

USING chỉ phù hợp khi cột ghép ở hai phía có **tên giống nhau** và cần quan hệ **bằng nhau**. ON linh hoạt hơn:

~~~sql
-- Nếu phía đơn hàng đặt tên là buyer_id:
FROM customers AS c
JOIN orders AS o
    ON c.customer_id = o.buyer_id
~~~

ON cũng cho phép nhiều điều kiện khác nhau:

~~~sql
FROM join_demo_customers AS c
JOIN join_demo_orders AS o
    ON c.customer_id = o.customer_id
   AND o.order_status = 'paid'
~~~

Điều kiện này ghép theo customer_id **và** chỉ xét đơn có trạng thái 'paid'. Có thể viết USING(customer_id) rồi lọc bằng WHERE với **INNER JOIN**, nhưng với **OUTER JOIN** vị trí ON/WHERE có thể đổi số hàng kết quả; chúng ta sẽ phân tích ở phần sau.

## 5. USING với nhiều cột khóa

USING nhận một danh sách gồm nhiều cột cùng tên:

~~~sql
USING (customer_id, fiscal_year)
~~~

Khi đó, hai hàng chỉ ghép với nhau nếu **customer_id bằng nhau và fiscal_year bằng nhau**. Đây là cách nối theo **khóa ghép**.

Ví dụ độc lập bằng CTE:

~~~sql
WITH targets(customer_id, fiscal_year, target_vnd) AS (
    VALUES
        (1, 2025, 2000000),
        (1, 2026, 3000000),
        (2, 2026, 1500000)
),
actuals(customer_id, fiscal_year, actual_vnd) AS (
    VALUES
        (1, 2026, 2500000),
        (2, 2026, 1800000),
        (2, 2025,  900000)
)
SELECT
    customer_id,
    fiscal_year,
    target_vnd,
    actual_vnd
FROM targets
JOIN actuals USING (customer_id, fiscal_year)
ORDER BY customer_id, fiscal_year;
~~~

Kết quả chỉ có **hai cặp**:

| customer_id | fiscal_year | target_vnd | actual_vnd |
| ---: | ---: | ---: | ---: |
| 1 | 2026 | 3000000 | 2500000 |
| 2 | 2026 | 1500000 | 1800000 |

Nếu chỉ USING(customer_id), dữ liệu của **nhiều năm** có thể ghép chéo giữa mục tiêu và thực tế của cùng khách, dẫn tới kết quả sai. Danh sách USING cần thể hiện **đủ các thành phần định danh quan hệ**.

Với khóa ghép, USING tương ứng về điều kiện ghép với:

~~~sql
ON targets.customer_id = actuals.customer_id
AND targets.fiscal_year = actuals.fiscal_year
~~~

Việc hai bảng cùng có một cột khác tên giống nhau, ví dụ **updated_at**, **không khiến USING(customer_id, fiscal_year) tự thêm updated_at vào điều kiện**. Đây là một ưu điểm bảo trì rất quan trọng so với NATURAL JOIN.

## 6. LEFT JOIN ... USING: giữ toàn bộ hàng phía trái

**LEFT JOIN** giữ mọi hàng từ nguồn bên trái, kể cả không tìm được hàng phù hợp ở nguồn bên phải. Với bảng mẫu, nếu đặt customers ở bên trái:

~~~sql
SELECT
    customer_id,
    c.customer_name,
    o.order_id,
    o.order_status
FROM join_demo_customers AS c
LEFT JOIN join_demo_orders AS o
    USING (customer_id)
ORDER BY customer_id, o.order_id NULLS LAST;
~~~

Kết quả:

| customer_id | customer_name | order_id | order_status |
| ---: | --- | ---: | --- |
| 1 | An | 101 | paid |
| 1 | An | 102 | pending |
| 2 | Binh | 103 | paid |
| 3 | Chi | NULL | NULL |
| 4 | Dung | NULL | NULL |

Đơn 104 và 105 không xuất hiện vì **orders là bảng bên phải** và không ghép được với khách bên trái. Khách 3, 4 vẫn có mặt, với các cột lấy từ orders là NULL.

### 6.1. Đếm đơn đúng khi dùng LEFT JOIN

~~~sql
SELECT
    customer_id,
    c.customer_name,
    COUNT(o.order_id) AS order_count,
    COALESCE(SUM(o.amount_vnd), 0) AS total_vnd
FROM join_demo_customers AS c
LEFT JOIN join_demo_orders AS o
    USING (customer_id)
GROUP BY customer_id, c.customer_name
ORDER BY customer_id;
~~~

Kết quả:

| customer_id | customer_name | order_count | total_vnd |
| ---: | --- | ---: | ---: |
| 1 | An | 2 | 700000 |
| 2 | Binh | 1 | 300000 |
| 3 | Chi | 0 | 0 |
| 4 | Dung | 0 | 0 |

**COUNT(o.order_id)** đếm những đơn thực sự ghép được. Nếu đổi thành **COUNT(*)**, khách 3 và 4 mỗi người có thể được đếm thành **1** vì LEFT JOIN tạo một hàng bổ sung với phía orders là NULL. **COALESCE(SUM(...), 0)** thay kết quả tổng NULL của nhóm không có đơn thành 0, theo quy ước báo cáo.

Việc dùng USING không thay đổi bản chất **một-nhiều**: khách 1 xuất hiện hai lần ở kết quả chi tiết do có hai đơn. Không nên thêm DISTINCT tùy ý để che số dòng tăng; cần xác định đó là số đơn hợp lệ hay lỗi ghép.

### 6.2. Khác biệt giữa lọc trong ON và lọc trong WHERE

Yêu cầu: **“Lấy tất cả khách, kèm các đơn đã thanh toán nếu có.”**

Viết bằng LEFT JOIN ON:

~~~sql
SELECT c.customer_id, c.customer_name, o.order_id, o.order_status
FROM join_demo_customers AS c
LEFT JOIN join_demo_orders AS o
    ON c.customer_id = o.customer_id
   AND o.order_status = 'paid'
ORDER BY c.customer_id, o.order_id NULLS LAST;
~~~

Kết quả giữ đủ **4 khách**: khách 1 có đơn 101; khách 2 có đơn 103; khách 3 và 4 có cột đơn NULL.

Truy vấn trông gần giống nhưng khác nghĩa:

~~~sql
SELECT c.customer_id, c.customer_name, o.order_id, o.order_status
FROM join_demo_customers AS c
LEFT JOIN join_demo_orders AS o
    USING (customer_id)
WHERE o.order_status = 'paid'
ORDER BY c.customer_id, o.order_id;
~~~

Kết quả chỉ còn khách **1 và 2**. **WHERE** loại các hàng có o.order_status NULL, làm mất khách chưa có đơn đã thanh toán. Khi cần bảo toàn toàn bộ phía trái, phải đặt điều kiện đúng chỗ hoặc thiết kế lại điều kiện rõ ràng.

**Cốt lõi:** USING xác định **các khóa bằng nhau**; ON có thể đồng thời chứa thêm điều kiện chỉ áp dụng lúc ghép. Không phải lúc nào chuyển điều kiện từ ON sang WHERE cũng giữ nguyên ý nghĩa của OUTER JOIN.

## 7. RIGHT và FULL JOIN ... USING: cột khóa hợp nhất

Với **RIGHT JOIN**, SQL giữ toàn bộ đơn hàng phía phải, kể cả không có khách khớp:

~~~sql
SELECT
    customer_id,
    c.customer_name,
    o.order_id
FROM join_demo_customers AS c
RIGHT JOIN join_demo_orders AS o
    USING (customer_id)
ORDER BY o.order_id;
~~~

Kết quả gồm đủ **5 đơn**:

| customer_id | customer_name | order_id |
| ---: | --- | ---: |
| 1 | An | 101 |
| 1 | An | 102 |
| 2 | Binh | 103 |
| 99 | NULL | 104 |
| NULL | NULL | 105 |

Chú ý đơn **104**: cột **customer_id hợp nhất của USING = 99**, dù không có khách tương ứng. Đây là giá trị từ **orders**, phía được RIGHT JOIN bảo toàn.

### 7.1. FULL JOIN giữ cả hai phía

~~~sql
SELECT
    customer_id,
    c.customer_id AS id_in_customers,
    o.customer_id AS id_in_orders,
    c.customer_name,
    o.order_id
FROM join_demo_customers AS c
FULL JOIN join_demo_orders AS o
    USING (customer_id)
ORDER BY customer_id NULLS LAST, o.order_id NULLS LAST;
~~~

Kết quả khái quát:

| customer_id (USING) | id_in_customers | id_in_orders | customer_name | order_id |
| ---: | ---: | ---: | --- | ---: |
| 1 | 1 | 1 | An | 101 |
| 1 | 1 | 1 | An | 102 |
| 2 | 2 | 2 | Binh | 103 |
| 3 | 3 | NULL | Chi | NULL |
| 4 | 4 | NULL | Dung | NULL |
| 99 | NULL | 99 | NULL | 104 |
| NULL | NULL | NULL | NULL | 105 |

**FULL JOIN có 7 hàng**: ba cặp ghép được, hai khách không có đơn và hai đơn không có khách hợp lệ.

Trong PostgreSQL, **cột customer_id không kèm alias** từ JOIN USING thể hiện **giá trị hợp nhất** của hai phía. Với FULL JOIN, có thể hình dung nó tương tự:

~~~sql
COALESCE(c.customer_id, o.customer_id)
~~~

Ở hàng chỉ có khách 3 hoặc 4, giá trị hợp nhất lấy từ customers. Ở đơn 104, nó lấy 99 từ orders. Ở đơn 105, cả hai phía đều không có customer_id xác định nên kết quả vẫn NULL.

**Điểm quan trọng khi chuyển đổi câu SQL:** không được tùy ý thay cột khóa hợp nhất bằng **c.customer_id** trong kết quả FULL/RIGHT JOIN, vì bạn có thể mất mã khóa của những hàng chỉ tồn tại ở phía phải.

### 7.2. Cột chung trong USING còn truy xuất riêng được không?

Trong PostgreSQL, ví dụ trên có thể đọc cả **c.customer_id** và **o.customer_id** bằng tên có alias, đồng thời đọc **customer_id** hợp nhất. Nhưng với **SELECT \*** trên toàn bộ kết quả JOIN USING, mỗi cột trong danh sách USING chỉ xuất hiện **một lần**.

Nếu muốn hiển thị **hai giá trị nguồn** để điều tra dữ liệu, hãy liệt kê tường minh chúng như truy vấn FULL JOIN. Nếu chỉ cần một khóa cho báo cáo, giá trị hợp nhất thường thuận tiện hơn.

Một số phương ngữ, chẳng hạn Oracle, có những giới hạn riêng về cách **qualify** cột liệt kê trong USING. Không dựa vào hành vi đặt alias của PostgreSQL để kết luận mọi hệ cho phép cùng cách tham chiếu.

## 8. NULL trong USING và ON

**USING(customer_id)** tương đương điều kiện bằng thông thường giữa hai cột customer_id. Nó **không coi NULL = NULL là TRUE**.

Ví dụ hai nguồn đều chứa một hàng có khóa NULL:

~~~sql
WITH left_side(k, left_label) AS (
    VALUES
        (1, 'L1'::TEXT),
        (NULL::INTEGER, 'L-missing'::TEXT)
),
right_side(k, right_label) AS (
    VALUES
        (1, 'R1'::TEXT),
        (NULL::INTEGER, 'R-missing'::TEXT)
)
SELECT
    k,
    l.left_label,
    r.right_label
FROM left_side AS l
FULL JOIN right_side AS r
    USING (k)
ORDER BY k NULLS LAST, l.left_label NULLS LAST;
~~~

Kết quả có **3 hàng**:

| k | left_label | right_label |
| --- | --- | --- |
| 1 | L1 | R1 |
| NULL | L-missing | NULL |
| NULL | NULL | R-missing |

Hai hàng có k NULL **không tự ghép với nhau**; FULL JOIN giữ mỗi hàng ở phía của nó.

Nếu nghiệp vụ **chủ động coi hai giá trị NULL là một khóa khớp**, PostgreSQL hỗ trợ điều kiện:

~~~sql
ON l.k IS NOT DISTINCT FROM r.k
~~~

Khi đó hai hàng khóa NULL có thể ghép với nhau. Đây **không phải** điều kiện mà USING tự sinh. Đừng coi hai NULL là cùng một khách hàng nếu NULL thực tế chỉ biểu thị **chưa xác định mã khách**.

**Cảnh báo:** nếu hai bảng có nhiều hàng khóa NULL, ghép bằng **IS NOT DISTINCT FROM** có thể tạo **nhiều cặp hàng** theo tích số lượng NULL ở hai phía. Việc biến NULL thành khóa ghép cần được xem xét rất cẩn thận.

## 9. NATURAL JOIN tự chọn tất cả cột trùng tên

**NATURAL JOIN** tự phát hiện những cột có **tên giống nhau ở hai nguồn**, rồi dùng chúng làm các điều kiện bằng nhau. Có thể hiểu về mặt ý tưởng:

~~~text
A NATURAL JOIN B
    ≈
A JOIN B USING (mọi tên cột chung của A và B)
~~~

Tập cột chung được xác định từ **lược đồ tại thời điểm truy vấn được phân tích**, không phải từ một danh sách khóa đã cố định trong câu SQL.

Trong bộ dữ liệu mẫu ban đầu:

~~~text
join_demo_customers:
    customer_id, customer_name, region

join_demo_orders:
    order_id, customer_id, order_status, amount_vnd

Cột chung theo tên:
    customer_id
~~~

Vì vậy, ban đầu hai truy vấn sau có cùng điều kiện ghép:

~~~sql
SELECT customer_id, customer_name, order_id
FROM join_demo_customers
NATURAL JOIN join_demo_orders
ORDER BY order_id;
~~~

~~~sql
SELECT customer_id, customer_name, order_id
FROM join_demo_customers
JOIN join_demo_orders USING (customer_id)
ORDER BY order_id;
~~~

Cả hai trả các đơn **101, 102, 103**. Nhưng sự tương đương này **chỉ đang đúng vì hiện tại hai bảng chỉ có một cột chung theo tên**.

### 9.1. NATURAL INNER, LEFT, RIGHT và FULL

Trong những hệ hỗ trợ, có thể viết các biến thể như:

~~~sql
-- PostgreSQL:
SELECT * FROM join_demo_customers NATURAL JOIN join_demo_orders;
SELECT * FROM join_demo_customers NATURAL LEFT JOIN join_demo_orders;
SELECT * FROM join_demo_customers NATURAL FULL JOIN join_demo_orders;
~~~

**NATURAL JOIN** không kèm từ LEFT/RIGHT/FULL thường được hiểu là **NATURAL INNER JOIN**. Phần **NATURAL** chỉ nói cách xác định cột ghép; các từ **INNER/LEFT/RIGHT/FULL** vẫn quyết định hàng nào được giữ khi không khớp.

Không viết **NATURAL JOIN ... ON** hoặc **NATURAL JOIN ... USING** để bổ sung khóa: hai kiểu cú pháp này là những lựa chọn xác định điều kiện ghép **khác nhau**, không phải các phần ghép nối cùng nhau.

### 9.2. NATURAL JOIN có thể ghép theo những cột không phải khóa

Tên giống nhau **không đảm bảo ý nghĩa giống nhau**. Ví dụ cả khách hàng và đơn hàng đều có cột **region**:

- **customers.region** có thể là khu vực đăng ký của khách.
- **orders.region** có thể là khu vực giao hàng của đơn.

Nếu dùng NATURAL JOIN, SQL có thể yêu cầu **cả customer_id bằng nhau lẫn region bằng nhau**, dù khách có quyền đặt đơn giao sang khu vực khác. Như vậy, dữ liệu hợp lệ có thể bị loại khỏi báo cáo.

**USING(customer_id)** hoặc **ON c.customer_id = o.customer_id** nêu chính xác quan hệ khách-đơn, không kéo theo một cột region chỉ vì trùng tên.

## 10. Thí nghiệm ALTER TABLE: NATURAL JOIN âm thầm đổi nghĩa

Đây là tình huống then chốt của bài. Để không làm thay đổi hai bảng tạm chính đang được dùng cho các ví dụ khác, ta tạo **một cặp bảng riêng**.

### 10.1. Lược đồ ban đầu

~~~sql
CREATE TEMP TABLE natural_demo_customers (
    customer_id   INTEGER PRIMARY KEY,
    customer_name TEXT NOT NULL
);

CREATE TEMP TABLE natural_demo_orders (
    order_id    INTEGER PRIMARY KEY,
    customer_id INTEGER NOT NULL,
    amount_vnd  NUMERIC(12, 2) NOT NULL
);

INSERT INTO natural_demo_customers
    (customer_id, customer_name)
VALUES
    (1, 'An'),
    (2, 'Binh');

INSERT INTO natural_demo_orders
    (order_id, customer_id, amount_vnd)
VALUES
    (201, 1, 100000),
    (202, 1, 200000),
    (203, 2, 300000);
~~~

Trước khi thay đổi lược đồ, chỉ có **customer_id** là cột chung:

~~~sql
SELECT
    customer_id,
    customer_name,
    order_id,
    amount_vnd
FROM natural_demo_customers
NATURAL JOIN natural_demo_orders
ORDER BY order_id;
~~~

Kết quả:

| customer_id | customer_name | order_id | amount_vnd |
| ---: | --- | ---: | ---: |
| 1 | An | 201 | 100000 |
| 1 | An | 202 | 200000 |
| 2 | Binh | 203 | 300000 |

Đến đây, NATURAL JOIN có vẻ rất thuận tiện và đúng.

### 10.2. Một thay đổi lược đồ tưởng như không liên quan

Giả sử đội phát triển muốn lưu một chỉ tiêu tạm thời về **giá trị giao dịch kỳ vọng của khách**, và vô tình đặt tên nó là **amount_vnd**, trùng tên cột tiền thực tế của orders:

~~~sql
ALTER TABLE natural_demo_customers
ADD COLUMN amount_vnd NUMERIC(12, 2);
~~~

Cột mới vừa thêm chưa có giá trị ở hai khách hiện tại, nên mặc định cả hai đều **NULL**. Không có dòng đơn hàng nào thay đổi, và câu truy vấn NATURAL JOIN cũng **không thay đổi một ký tự**.

Nhưng bây giờ hai bảng có **hai cột trùng tên**:

~~~text
natural_demo_customers:
    customer_id, customer_name, amount_vnd

natural_demo_orders:
    order_id, customer_id, amount_vnd

Các cột chung mới:
    customer_id, amount_vnd
~~~

Khi chạy lại đúng truy vấn NATURAL JOIN trước đó:

~~~sql
SELECT
    customer_id,
    customer_name,
    order_id,
    amount_vnd
FROM natural_demo_customers
NATURAL JOIN natural_demo_orders
ORDER BY order_id;
~~~

**Kết quả giờ là 0 dòng.** Vì NATURAL JOIN hiện tương đương:

~~~sql
SELECT
    c.customer_id,
    c.customer_name,
    o.order_id,
    o.amount_vnd
FROM natural_demo_customers AS c
JOIN natural_demo_orders AS o
    ON c.customer_id = o.customer_id
   AND c.amount_vnd = o.amount_vnd
ORDER BY o.order_id;
~~~

Trong bảng customers, c.amount_vnd là NULL; phép so sánh **NULL = 100000**, **NULL = 200000**, **NULL = 300000** đều UNKNOWN, nên không có cặp hàng được giữ bởi INNER JOIN. Kết quả âm thầm đổi từ **3 đơn** thành **0 đơn**, dù dữ liệu đơn và ý định truy vấn không thay đổi.

**Đây là rủi ro lược đồ thay đổi (schema evolution/schema drift) của NATURAL JOIN:** tập cột ghép được quyết định lại từ toàn bộ tên cột hiện có mỗi khi truy vấn được phân tích.

### 10.3. USING và ON vẫn ổn định sau ALTER TABLE

Chạy truy vấn xác định khóa một cách tường minh:

~~~sql
SELECT
    customer_id,
    c.customer_name,
    o.order_id,
    o.amount_vnd
FROM natural_demo_customers AS c
JOIN natural_demo_orders AS o
    USING (customer_id)
ORDER BY o.order_id;
~~~

Kết quả **vẫn là 201, 202, 203**. Câu USING chỉ yêu cầu customer_id khớp; cột amount_vnd mới không tự được thêm vào điều kiện.

Tương tự, câu JOIN ON sau không đổi ý nghĩa:

~~~sql
SELECT
    c.customer_id,
    c.customer_name,
    o.order_id,
    o.amount_vnd
FROM natural_demo_customers AS c
JOIN natural_demo_orders AS o
    ON c.customer_id = o.customer_id
ORDER BY o.order_id;
~~~

Nếu SELECT * sau khi hai bảng đều có **amount_vnd**, JOIN USING sẽ **giữ cả hai cột amount_vnd không thuộc USING**, có thể gây trùng tên cột đầu ra. Vì vậy, **JOIN USING bảo vệ điều kiện ghép nhưng không tự bảo vệ cấu trúc SELECT \***. Lựa chọn bền vững là **liệt kê các cột kết quả cụ thể, có alias khi cần**.

### 10.4. Sửa tạm dữ liệu không phải cách sửa lỗi thiết kế

Nếu cập nhật c.amount_vnd = 100000 cho khách 1:

~~~sql
UPDATE natural_demo_customers
SET amount_vnd = 100000
WHERE customer_id = 1;
~~~

NATURAL JOIN có thể bắt đầu trả đơn **201**, nhưng đơn **202** vẫn bị loại vì amount_vnd của đơn 202 là 200000. Đây không phải cách khôi phục truy vấn, vì **giá trị kỳ vọng theo khách và tiền từng đơn là hai khái niệm khác nhau**, chỉ tình cờ mang cùng tên cột.

Sửa đúng là thay NATURAL JOIN bằng điều kiện khóa rõ ràng, chẳng hạn **USING(customer_id)** hoặc **ON c.customer_id = o.customer_id**, và xem xét đặt tên cột theo đúng nghĩa để giảm khả năng hiểu nhầm.

## 11. NATURAL JOIN khi không có tên cột chung: nguy cơ tích Descartes

Một tình huống khác xảy ra khi hai bảng **không có cột cùng tên**. Khi đó, NATURAL JOIN có **danh sách điều kiện ghép rỗng** và trong PostgreSQL, **NATURAL INNER JOIN** sẽ cho kết quả giống **CROSS JOIN**.

Ví dụ độc lập bằng CTE:

~~~sql
WITH colors(color) AS (
    VALUES ('red'::TEXT), ('blue'::TEXT)
),
shapes(shape) AS (
    VALUES ('circle'::TEXT),
           ('square'::TEXT),
           ('triangle'::TEXT)
)
SELECT color, shape
FROM colors
NATURAL JOIN shapes
ORDER BY color, shape;
~~~

Hai nguồn có **2 màu** và **3 hình** nhưng không có cột trùng tên. Kết quả có **2 × 3 = 6 dòng**:

~~~text
blue  circle
blue  square
blue  triangle
red   circle
red   square
red   triangle
~~~

Truy vấn chạy hợp lệ nhưng có thể nhân số dòng khổng lồ nếu cả hai bảng lớn. Điều nguy hiểm là nếu một ngày một cột cùng tên xuất hiện ở cả hai phía, chính NATURAL JOIN ấy **đột nhiên bắt đầu lọc theo cột mới**, làm kết quả giảm hoặc biến mất.

**NATURAL JOIN không đảm bảo tồn tại khóa liên kết hợp lý.** Nó chỉ dựa trên **tên cột trùng nhau**; khi không có tên trùng, phép nối không có điều kiện chọn cặp nào cả.

## 12. NATURAL JOIN còn có thể đổi cấu trúc kết quả SELECT *

Khi một cột mới xuất hiện ở cả hai phía, không chỉ **điều kiện ghép** mà cả **danh sách cột đầu ra** cũng có thể đổi.

Trước khi thêm amount_vnd vào natural_demo_customers:

~~~text
SELECT * FROM natural_demo_customers NATURAL JOIN natural_demo_orders

customer_id | customer_name | order_id | amount_vnd
~~~

Sau khi thêm amount_vnd vào customers, cột ấy trở thành **cột chung của NATURAL JOIN** và được hợp nhất trong kết quả:

~~~text
customer_id | amount_vnd | customer_name | order_id
~~~

Trong PostgreSQL, các cột chung được đưa lên đầu theo thứ tự quy tắc của NATURAL JOIN, rồi đến các cột riêng của từng nguồn. Điều này có thể làm **thay đổi vị trí cột**, số lượng bản ghi và thậm chí ý nghĩa của tên cột mà ứng dụng đang đọc từ kết quả.

Ứng dụng có thể bị ảnh hưởng nếu:

- Đọc cột theo **vị trí** thay vì tên.
- Dùng SELECT * để tạo file CSV theo một cấu trúc cố định.
- Ánh xạ trực tiếp kết quả vào DTO hoặc cấu trúc dữ liệu theo thứ tự cột.
- Dùng NATURAL JOIN trong **VIEW**, báo cáo hoặc truy vấn tạo bảng trung gian.
- Dựa vào tên cột mà không kiểm soát sự xuất hiện của các tên trùng.

**Kết luận thực tế:** tránh kết hợp **NATURAL JOIN + SELECT \*** trong các truy vấn quan trọng. Khi truy vấn là hợp đồng dữ liệu với ứng dụng, nên cố định rõ **khóa JOIN và các cột SELECT**, kèm alias có nghĩa.

## 13. Rủi ro khi hai bảng có cùng tên cột nhưng khác nghĩa

Không phải mọi cột chung tên đều là khóa liên kết. Một số tên thường được lặp lại giữa nhiều bảng:

| Tên cột | Ví dụ nghĩa ở bảng A | Ví dụ nghĩa ở bảng B | Nguy cơ với NATURAL JOIN |
| --- | --- | --- | --- |
| **status** | Trạng thái khách hàng | Trạng thái đơn hàng | Chỉ ghép khi hai trạng thái tình cờ bằng nhau |
| **created_at** | Thời điểm tạo khách | Thời điểm tạo đơn | Gần như không khớp, dù mã khách đúng |
| **region** | Khu vực cư trú khách | Khu vực giao hàng | Loại đơn giao khác khu vực cư trú |
| **amount_vnd** | Hạn mức hoặc giá trị kỳ vọng của khách | Số tiền một đơn | Điều kiện so sánh tiền không có ý nghĩa quan hệ |
| **source** | Kênh thu hút khách | Kênh đặt hàng | Loại đơn từ kênh khác |
| **id** | ID khách hàng | ID đơn hàng | Ghép hai ID thuộc hai miền định danh khác nhau |
| **updated_at** | Lần cập nhật hồ sơ | Lần cập nhật đơn | Kết quả biến đổi theo dữ liệu vận hành |

Đặc biệt, tên cột phổ biến như **id** hoặc **status** rất dễ xuất hiện ở nhiều bảng. Dùng NATURAL JOIN giữa những bảng đó không có nghĩa hệ thống tự suy ra khóa ngoại. SQL không đọc ý định nghiệp vụ từ cấu trúc PRIMARY KEY/FOREIGN KEY để quyết định NATURAL JOIN; nó dựa vào **tên cột trùng**.

Khi một tên cột chung có kiểu dữ liệu không so sánh được với nhau, hệ quản trị có thể **báo lỗi kiểu/toán tử** thay vì trả kết quả. Việc thêm một cột có thể dẫn tới **lỗi rõ ràng** hoặc **thay đổi kết quả âm thầm**; cả hai đều là rủi ro bảo trì.

## 14. USING có rủi ro gì khi lược đồ thay đổi?

**USING an toàn hơn NATURAL JOIN về việc chọn khóa** vì danh sách khóa được ghi tường minh. Tuy nhiên, USING không loại bỏ mọi rủi ro do schema evolution:

1. Nếu **đổi tên hoặc xóa** một cột nằm trong USING, truy vấn sẽ báo lỗi vì không tìm thấy khóa đã khai báo.
2. Nếu thay đổi **kiểu dữ liệu** hoặc quy tắc so sánh của khóa, JOIN có thể thất bại hoặc có kết quả khác.
3. Nếu thêm cột trùng tên **không nằm trong USING**, điều kiện ghép không đổi, nhưng **SELECT \*** có thể có hai cột cùng tên.
4. Nếu các khóa được xem là bằng nhau nhưng có **NULL**, phép bằng thông thường vẫn không ghép hai NULL.
5. Khi dùng **LEFT/RIGHT/FULL JOIN**, cần hiểu cột hợp nhất để không lấy nhầm giá trị chỉ từ một phía.
6. Với **JOIN nhiều bảng**, cột cùng tên không được qualify trong SELECT có thể mơ hồ nếu không nằm trong danh sách cột đã hợp nhất hoặc không đủ ngữ cảnh.

Ví dụ sau khi cả hai bảng natural_demo_* có amount_vnd:

~~~sql
-- Khóa ghép vẫn chỉ là customer_id.
SELECT
    customer_id,
    c.customer_name,
    c.amount_vnd AS expected_amount_vnd,
    o.amount_vnd AS order_amount_vnd
FROM natural_demo_customers AS c
JOIN natural_demo_orders AS o
    USING (customer_id)
ORDER BY o.order_id;
~~~

Cách này giữ **hai giá trị có nghĩa khác nhau** ở hai cột đầu ra được đặt alias rõ ràng. Nếu chỉ viết SELECT * hoặc SELECT amount_vnd không qualify, có thể gặp trường hợp dư cột hoặc tên mơ hồ.

Đối với báo cáo quan trọng, **JOIN ON với điều kiện rõ và SELECT liệt kê cột** thường là lựa chọn dễ đọc nhất; **JOIN USING** là lựa chọn gọn và hợp lý khi tên khóa được chuẩn hóa, còn **NATURAL JOIN** nên được xem là cú pháp cần cân nhắc rất kỹ.

## 15. Một số tình huống JOIN nhiều bảng

### 15.1. USING không tự ghép mọi cột chung trong chuỗi JOIN

Giả sử ba bảng đều có **customer_id**, nhưng bảng thứ ba còn chứa cột **region**. Muốn ghép chỉ theo customer_id, bạn có thể viết:

~~~sql
-- Minh họa cú pháp; nguồn third_source là bảng giả định.
SELECT c.customer_id, c.customer_name, o.order_id, t.some_value
FROM customers AS c
JOIN orders AS o USING (customer_id)
JOIN third_source AS t USING (customer_id);
~~~

Mỗi USING chỉ nêu rõ khóa dùng tại bước JOIN tương ứng. Cột region của third_source **không được tự thêm vào điều kiện** chỉ vì trùng tên với một nguồn trước đó.

Ngược lại, NATURAL JOIN tại một bước nối nhiều nguồn có thể xét **các tên cột chung của hai toán hạng JOIN hiện tại**, mà một toán hạng có thể đã là **kết quả ghép của nhiều bảng**. Điều này càng khiến điều kiện nối khó được nhận ra bằng mắt khi truy vấn dài.

### 15.2. Dùng alias và ngoặc khi cần làm rõ cấu trúc

SQL kết hợp nhiều JOIN theo cấu trúc cú pháp xác định; thứ tự, loại JOIN và vị trí điều kiện ON có thể ảnh hưởng kết quả, nhất là khi có OUTER JOIN. Một ví dụ dễ bảo trì:

~~~sql
SELECT
    o.order_id,
    c.customer_name
FROM join_demo_orders AS o
LEFT JOIN join_demo_customers AS c
    ON o.customer_id = c.customer_id
ORDER BY o.order_id;
~~~

Alias **o**, **c** giúp phân biệt cột nguồn ngay cả khi tên trùng. Khi có ba bảng trở lên, việc viết rõ **ON từng cặp quan hệ** thường giúp đọc và kiểm tra yêu cầu nghiệp vụ tốt hơn so với để NATURAL JOIN tự chọn khóa.

### 15.3. Không dùng DISTINCT để che lỗi ghép

Một khách có thể có nhiều đơn, nên JOIN tạo ra nhiều dòng là **đúng**. Nếu thấy kết quả số dòng tăng:

- Xác định đó là **quan hệ một-nhiều hợp lệ** hay do thiếu cột trong khóa JOIN.
- Kiểm tra tính duy nhất của khóa phía bảng được ghép.
- Kiểm tra tình huống NATURAL JOIN không có cột chung gây CROSS JOIN.
- Chỉ dùng **DISTINCT** khi mục tiêu thực sự là **loại hàng trùng của tập kết quả**.

DISTINCT có thể làm kết quả trông gọn hơn mà không sửa nguyên nhân quan hệ sai, đồng thời che khuất lỗi tính tổng doanh thu do nhân bản hàng.

## 16. Giám sát thay đổi lược đồ để bảo vệ các truy vấn JOIN

Trong dự án có migration, mỗi lần thay đổi bảng nên xem xét tác động lên các truy vấn phụ thuộc.

### 16.1. Trước khi đổi schema, liệt kê những cột có thể gây xung đột

Với PostgreSQL, có thể xem cột của hai bảng tạm bằng INFORMATION_SCHEMA:

~~~sql
SELECT
    table_name,
    column_name,
    ordinal_position,
    data_type
FROM information_schema.columns
WHERE table_schema LIKE 'pg_temp_%'
  AND table_name IN ('join_demo_customers', 'join_demo_orders')
ORDER BY table_name, ordinal_position;
~~~

Tùy phiên/namespace và khả năng hiển thị metadata của kết nối, cách tìm bảng tạm có thể khác nhau. Với bảng thực tế trong schema **public**, thay điều kiện table_schema phù hợp với schema của dự án.

Để liệt kê **những tên cột chung** giữa hai bảng đã biết trên PostgreSQL, có thể dùng CTE đọc INFORMATION_SCHEMA:

~~~sql
WITH left_columns AS (
    SELECT column_name
    FROM information_schema.columns
    WHERE table_schema = 'public'
      AND table_name = 'customers'
),
right_columns AS (
    SELECT column_name
    FROM information_schema.columns
    WHERE table_schema = 'public'
      AND table_name = 'orders'
)
SELECT l.column_name
FROM left_columns AS l
JOIN right_columns AS r USING (column_name)
ORDER BY l.column_name;
~~~

Đây là **truy vấn minh họa cho hai bảng thật giả định trong public**. Không chạy nó để kiểm tra bộ bảng tạm mà quên đổi tên schema. Với các truy vấn NATURAL JOIN, một cột mới xuất hiện trong danh sách này có thể đồng nghĩa với **điều kiện JOIN mới ngoài dự kiến**.

### 16.2. Một quy trình migration nên có

1. **Xác định những truy vấn JOIN đang dùng**: mã ứng dụng, VIEW, báo cáo, ETL và truy vấn định kỳ.
2. **Tìm NATURAL JOIN và SELECT \*** ở những vị trí nhạy cảm, vì chúng phụ thuộc nhiều hơn vào tên/cấu trúc cột.
3. **Ghi rõ khóa quan hệ mong muốn** trước và sau thay đổi: customer_id, (customer_id, fiscal_year), hay khóa ghép khác.
4. **Chạy truy vấn trên schema mới với dữ liệu đại diện**: so số hàng ghép được, số hàng không ghép được, tổng số tiền và danh sách cột đầu ra.
5. **Thay NATURAL JOIN bằng USING/ON** nếu cột chung phát sinh không đúng vai trò khóa.
6. **Liệt kê cột SELECT và đặt alias** để giao diện nhận một cấu trúc kết quả có kiểm soát.
7. **Kiểm tra khóa ngoại và ràng buộc duy nhất** nếu có: chúng giúp bảo vệ dữ liệu, nhưng không tự sửa một NATURAL JOIN có điều kiện sai.

**Không nên xem việc truy vấn vẫn chạy không lỗi là bằng chứng dữ liệu đúng.** Trong thí nghiệm phần 10, NATURAL JOIN vẫn hợp lệ nhưng trả **0 dòng thay vì 3**, đủ gây sai báo cáo nếu không đối chiếu với dữ liệu nguồn.

## 17. Khác biệt giữa các phương ngữ SQL

| Hệ quản trị | JOIN ... USING | NATURAL JOIN | Ghi chú |
| --- | --- | --- | --- |
| **PostgreSQL 15+** | Có | Có | USING hợp nhất cột chung trong đầu ra; hỗ trợ INNER/OUTER JOIN và GROUPING/NULL theo quy tắc PostgreSQL |
| **MySQL 8.0** | Có | Có | Có các biến thể NATURAL INNER/LEFT/RIGHT; cần chú ý thứ tự và giá trị cột chung ở OUTER JOIN |
| **SQLite** | Có | Có | Hỗ trợ USING/NATURAL; FULL/RIGHT JOIN chỉ có ở các phiên bản SQLite mới hơn |
| **Oracle Database** | Có | Có | Có giới hạn riêng về qualify cột được liệt kê trong USING; cần xem cú pháp theo phiên bản |
| **SQL Server** | **Không hỗ trợ cú pháp USING** theo dạng PostgreSQL | **Không hỗ trợ NATURAL JOIN** | Dùng JOIN ... ON với điều kiện rõ ràng |

### 17.1. PostgreSQL

~~~sql
SELECT customer_id, c.customer_name, o.order_id
FROM join_demo_customers AS c
JOIN join_demo_orders AS o USING (customer_id);
~~~

Khi cần cột chung chỉ xuất hiện một lần, USING rất tiện. Khi muốn bảo toàn cả hai phía và phân biệt mã nguồn, liệt kê các cột có alias.

### 17.2. MySQL

Cú pháp sau có cùng ý tưởng trên MySQL:

~~~sql
SELECT customer_id, c.customer_name, o.order_id
FROM customers AS c
JOIN orders AS o USING (customer_id);
~~~

MySQL cũng hỗ trợ NATURAL JOIN, nhưng rủi ro tự mở rộng danh sách khóa theo tên cột vẫn tồn tại. MySQL có các quy tắc về **coalesced column** ở USING/NATURAL OUTER JOIN; không nên tự suy luận giá trị cột hợp nhất bằng cách luôn lấy một bên.

### 17.3. SQLite

SQLite hỗ trợ:

~~~sql
SELECT customer_id, c.customer_name, o.order_id
FROM customers AS c
JOIN orders AS o USING (customer_id);
~~~

và NATURAL JOIN, nhưng khả năng RIGHT/FULL JOIN phụ thuộc phiên bản; RIGHT và FULL OUTER JOIN được bổ sung từ **SQLite 3.39.0**. Nếu cần chạy trên SQLite cũ, phải xác định phiên bản trước khi dùng những loại OUTER JOIN này.

### 17.4. Oracle Database

Oracle có **JOIN ... USING** và **NATURAL JOIN**, nhưng khi tham chiếu cột trong danh sách USING, Oracle có quy định riêng về việc không qualify tên cột bằng alias trong một số ngữ cảnh. Vì thế, câu PostgreSQL chọn đồng thời **c.customer_id**, **o.customer_id** trong một JOIN USING không nên được sao chép nguyên văn sang Oracle. Có thể dùng **JOIN ... ON** khi cần cả hai cột nguồn.

### 17.5. SQL Server

SQL Server không dùng:

~~~sql
-- Không hợp lệ trên SQL Server:
FROM dbo.customers AS c
JOIN dbo.orders AS o USING (customer_id)
~~~

Thay bằng:

~~~sql
SELECT
    c.customer_id,
    c.customer_name,
    o.order_id
FROM dbo.customers AS c
JOIN dbo.orders AS o
    ON c.customer_id = o.customer_id;
~~~

Nếu muốn một cột khóa hợp nhất ở FULL JOIN, có thể chủ động dùng:

~~~sql
SELECT
    COALESCE(c.customer_id, o.customer_id) AS customer_id,
    c.customer_name,
    o.order_id
FROM dbo.customers AS c
FULL OUTER JOIN dbo.orders AS o
    ON c.customer_id = o.customer_id;
~~~

Đây là cách viết **rõ điều kiện ghép và cột kết quả**, phù hợp với SQL Server.

## 18. Chọn ON, USING hay NATURAL JOIN trong dự án

| Tiêu chí | JOIN ... ON | JOIN ... USING | NATURAL JOIN |
| --- | --- | --- | --- |
| Chỉ rõ cột ghép trong câu SQL | Có | Có | **Không** |
| Yêu cầu hai cột khóa cùng tên | Không | Có | Tự chọn mọi cột cùng tên |
| Ghép theo điều kiện khác dấu bằng | Có | Không trực tiếp | Không trực tiếp |
| Có thể chứa điều kiện lọc ở bước ghép OUTER JOIN | Có | Không trong danh sách USING | Không trong danh sách tự động |
| SELECT * hợp nhất các cột khóa | Không | Có, với cột trong USING | Có, với mọi cột cùng tên |
| Thêm cột mới cùng tên có thể đổi điều kiện JOIN | Không, nếu ON giữ nguyên | Không, nếu USING giữ nguyên | **Có** |
| Có thể gây thay đổi cấu trúc SELECT * khi schema đổi | Có | Có | **Có, kể cả danh sách cột bị hợp nhất** |
| Dễ di chuyển sang SQL Server | Có | Phải đổi sang ON | Phải đổi sang ON |
| Mức kiểm soát ý nghĩa khóa ghép | Cao | Cao khi tên khóa được chuẩn hóa | Thấp, phụ thuộc schema |

**Gợi ý lựa chọn:**

- **Dùng ON** khi cột khóa khác tên, có điều kiện phức hợp hoặc muốn thể hiện rõ điều kiện ghép trong OUTER JOIN.
- **Dùng USING** khi hai nguồn có **cùng tên khóa** và mối quan hệ đơn giản là **so sánh bằng**. Viết danh sách USING đầy đủ, rõ ràng.
- **Tránh NATURAL JOIN trong truy vấn sản xuất quan trọng** nếu không có lý do đặc biệt và cơ chế kiểm soát schema chặt chẽ. Cách viết ngắn không bù được rủi ro một cột mới làm câu truy vấn âm thầm đổi nghĩa.
- **Liệt kê cột SELECT** trong hợp đồng dữ liệu ổn định; không phụ thuộc SELECT * trên các nguồn thường xuyên thay đổi.

## 19. Những lỗi thường gặp

| Lỗi hoặc hiểu nhầm | Vì sao sai | Hướng khắc phục |
| --- | --- | --- |
| Nghĩ USING giống ON về danh sách cột SELECT * | ON giữ hai cột khóa, USING thường hợp nhất thành một | Xem rõ projection và đặt alias |
| Dùng USING khi hai tên khóa khác nhau | USING yêu cầu cột cùng tên | Dùng ON với hai tên cột cụ thể |
| Dùng USING(customer_id) khi thực tế khóa gồm customer_id và fiscal_year | Ghép nhầm dữ liệu các năm | Dùng USING(customer_id, fiscal_year) |
| Nghĩ NATURAL JOIN sẽ tự tìm FOREIGN KEY | NATURAL chỉ dựa vào tên cột chung | Viết khóa rõ bằng ON/USING |
| Thêm cột region/created_at vào hai bảng rồi NATURAL JOIN mất dòng | Điều kiện JOIN tự mở rộng theo cột mới | Thay NATURAL bằng ON/USING |
| NATURAL JOIN không có cột chung trả rất nhiều dòng | Điều kiện ghép rỗng dẫn tới tích Descartes | Xác định khóa thực và dùng JOIN rõ ràng |
| Lấy c.customer_id trong RIGHT/FULL JOIN và coi là khóa chung | Có thể NULL với hàng chỉ tồn tại phía phải | Dùng cột hợp nhất của USING hoặc COALESCE trên ON |
| Đợi NULL ở hai phía tự khớp trong USING | NULL = NULL không TRUE | Xác định quy tắc NULL, cân nhắc IS NOT DISTINCT FROM trong ON |
| LEFT JOIN rồi WHERE lọc cột bên phải | Có thể loại hàng phía trái không khớp | Đặt điều kiện trong ON nếu muốn giữ toàn bộ phía trái |
| COUNT(*) để đếm số đơn sau LEFT JOIN | Khách không có đơn vẫn có một hàng kết quả | COUNT(o.order_id) |
| Cộng doanh thu sau JOIN mà không hiểu quan hệ một-nhiều | Hàng có thể nhân lên | Kiểm tra khóa và cấp tổng hợp |
| Dùng DISTINCT để che nhân hàng do sai khóa | Kết quả trông gọn nhưng quan hệ vẫn sai | Sửa điều kiện JOIN, không che bằng DISTINCT |
| Giữ SELECT * làm hợp đồng trả về dữ liệu | Cột mới hoặc NATURAL/USING có thể đổi cấu trúc | Chọn cột tường minh và alias rõ |
| Dùng USING/NATURAL nguyên văn trên SQL Server | SQL Server không hỗ trợ hai cú pháp này | Dùng JOIN ... ON |

## 20. Bài tập thực hành

Sử dụng bảng tạm **join_demo_customers** và **join_demo_orders** ở phần 3. Một số bài dùng thêm bảng natural_demo_* ở phần 10.

1. Viết INNER JOIN bằng **ON c.customer_id = o.customer_id**, liệt kê customer_id, customer_name, order_id. Dự đoán số dòng.
2. Viết lại bài 1 bằng **USING(customer_id)**. So sánh kết quả.
3. Chạy **SELECT \*** với JOIN ON và JOIN USING. Ghi lại số cột đầu ra và vị trí customer_id.
4. Viết **LEFT JOIN USING(customer_id)** từ customers sang orders. Xác định khách nào có order_id NULL.
5. Sau LEFT JOIN, tính **COUNT(o.order_id)** và **COUNT(*)** theo customer_id. Tại sao hai cách đếm khác nhau ở khách chưa có đơn?
6. Viết **RIGHT JOIN USING(customer_id)** để giữ đủ năm đơn. Giải thích giá trị customer_id hợp nhất của đơn 104.
7. Viết **FULL JOIN USING(customer_id)**. Phân loại số dòng ghép được, dòng chỉ có khách và dòng chỉ có đơn.
8. Dùng CTE với hai phía đều có khóa NULL để so sánh **USING(k)** và **ON l.k IS NOT DISTINCT FROM r.k**.
9. Lấy tất cả khách và đơn **paid** nếu có, vẫn giữ khách chưa có đơn paid. So sánh khi đặt order_status = 'paid' trong ON với WHERE.
10. Dùng hai CTE có **customer_id** và **fiscal_year**, ghép bằng **USING(customer_id, fiscal_year)**. Sau đó chỉ ghép theo customer_id và quan sát những cặp năm bị ghép sai.
11. Chạy NATURAL JOIN trên bảng customers/orders mẫu ban đầu. Có bao nhiêu cột chung? Kết quả có bao nhiêu dòng?
12. Tạo hai bảng natural_demo_* của phần 10. Ghi lại kết quả NATURAL JOIN **trước** khi thêm amount_vnd vào bảng khách.
13. Thực hiện **ALTER TABLE ... ADD COLUMN amount_vnd** cho natural_demo_customers, rồi chạy lại NATURAL JOIN y hệt. Giải thích tại sao không có dòng nào.
14. Thay NATURAL JOIN của bài 13 bằng **USING(customer_id)**. Kết quả có phục hồi thành ba đơn không?
15. So sánh danh sách cột của SELECT * NATURAL JOIN **trước và sau** khi thêm cột amount_vnd cùng tên.
16. Tạo hai CTE có cột hoàn toàn khác tên rồi NATURAL JOIN. Dự đoán và giải thích số dòng của kết quả.
17. Giả sử customers có region đăng ký, orders có region giao hàng. Giải thích vì sao NATURAL JOIN có thể loại đơn giao sang vùng khác.
18. Viết truy vấn dùng INFORMATION_SCHEMA để liệt kê cột chung của hai bảng nghiệp vụ bất kỳ trong hệ thống thực hành.
19. Trình bày vì sao **JOIN USING** giúp giữ ổn định điều kiện nối khi thêm một cột trùng tên không nằm trong USING, nhưng **SELECT \*** vẫn có thể thay đổi.
20. Chuyển một truy vấn USING và một truy vấn NATURAL JOIN sang **SQL Server** bằng ON với khóa được lựa chọn rõ ràng.

### Câu hỏi tự kiểm tra

**Câu 1:** JOIN ... USING(customer_id) có tự động thêm điều kiện bằng nhau trên cột created_at nếu cả hai bảng cùng có cột đó không?

**Đáp án:** **Không.** USING chỉ dùng cột được nêu trong danh sách, tức customer_id.

**Câu 2:** NATURAL JOIN tự chọn những cột nào?

**Đáp án:** **Mọi cột trùng tên của hai toán hạng JOIN tại thời điểm phân tích truy vấn**, bất kể chúng có phải khóa nghiệp vụ hay không.

**Câu 3:** Khi dùng SELECT * với JOIN ON c.id = o.id, hai cột id có được hợp nhất tự động không?

**Đáp án:** **Không.** ON giữ các cột của cả hai phía. USING(id) hoặc NATURAL JOIN thường hợp nhất các cột chung tương ứng trong projection của JOIN.

**Câu 4:** NATURAL JOIN không tìm được cột trùng tên thì có báo lỗi không?

**Đáp án:** Không nhất thiết. Trong PostgreSQL, NATURAL INNER JOIN khi không có cột chung hoạt động như **CROSS JOIN**, tạo mọi cặp hàng.

**Câu 5:** Tại sao thêm amount_vnd vào natural_demo_customers có thể làm NATURAL JOIN đang đúng trả 0 dòng?

**Đáp án:** Vì NATURAL JOIN tự thêm điều kiện **c.amount_vnd = o.amount_vnd**. Cột mới của khách là NULL, nên các phép so sánh bằng không TRUE.

**Câu 6:** Trong RIGHT JOIN USING(customer_id), đơn hàng có customer_id = 99 mà không có khách khớp thì cột customer_id hợp nhất là NULL hay 99?

**Đáp án:** **99**, vì RIGHT JOIN giữ phía orders và khóa hợp nhất lấy giá trị ở phía có dữ liệu.

**Câu 7:** NULL của hai khóa trong USING có tự ghép được với nhau không?

**Đáp án:** **Không.** Điều kiện bằng thông thường với NULL cho UNKNOWN. Cần quy tắc NULL rõ ràng nếu muốn xem hai NULL là khớp.

**Câu 8:** Có thể dùng JOIN ... USING trong SQL Server nguyên văn như PostgreSQL không?

**Đáp án:** **Không.** SQL Server dùng JOIN ... ON để xác định điều kiện ghép tương ứng.

## 21. Ghi nhớ cốt lõi

**JOIN ... USING** cho phép chỉ rõ **các cột cùng tên** được dùng để ghép bằng nhau, đồng thời trình bày **một cột hợp nhất** cho mỗi tên trong danh sách USING ở đầu ra của JOIN. **JOIN ... ON** linh hoạt hơn, hỗ trợ cột khác tên và điều kiện phức tạp, nhưng SELECT * giữ cả các cột khóa từ hai phía.

**NATURAL JOIN tự chọn toàn bộ cột trùng tên**, không dựa trên FOREIGN KEY hay ý nghĩa nghiệp vụ. Vì vậy, chỉ cần một **ALTER TABLE thêm cột trùng tên**, điều kiện JOIN và cả cấu trúc SELECT * có thể đổi mà câu SQL không đổi. Nếu không có cột chung, NATURAL INNER JOIN có thể trở thành **CROSS JOIN**; nếu cột mới có NULL hoặc khác nghĩa, truy vấn có thể làm mất hàng hợp lệ.

Để xây dựng SQL bền vững trước thay đổi lược đồ, hãy **nêu rõ khóa JOIN bằng ON hoặc USING**, **liệt kê các cột đầu ra và đặt alias có ý nghĩa**, hiểu **NULL và OUTER JOIN**, đồng thời kiểm tra những báo cáo phụ thuộc sau mỗi migration. Cú pháp ngắn chỉ thực sự có ích khi nó còn **diễn đạt chính xác quan hệ dữ liệu**.
