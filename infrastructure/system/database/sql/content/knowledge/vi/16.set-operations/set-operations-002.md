# UNION và UNION ALL trong hợp nhất kết quả

Trong SQL, đôi khi dữ liệu cần hiển thị không nằm trong một bảng mà đến từ **nhiều truy vấn có cùng cấu trúc đầu ra**. Ví dụ, hệ thống nhận đơn qua website và tại cửa hàng; báo cáo muốn gộp các đơn từ cả hai kênh thành một danh sách. Một ứng dụng khác lưu sự kiện theo từng năm hoặc hợp nhất dữ liệu hiện hành với dữ liệu lịch sử. Khi đó, ta cần **ghép các hàng theo chiều dọc**: kết quả của truy vấn thứ hai được đặt tiếp dưới kết quả của truy vấn thứ nhất.

Hai toán tử quan trọng trong nhóm **phép toán tập hợp** (*set operations*) là:

- **`UNION ALL`**: giữ **tất cả các hàng** của các nhánh, bao gồm các hàng có giá trị trùng nhau.
- **`UNION`**, thường tương đương **`UNION DISTINCT`**: hợp nhất các nhánh rồi **loại các hàng trùng trên toàn bộ các cột được chọn**.

Điểm cần ghi nhớ: một **hàng trùng giá trị** không nhất thiết là **một giao dịch bị ghi trùng**. Hai đơn hàng độc lập có thể cùng ngày, cùng số tiền và cùng trạng thái. Dùng `UNION` cho báo cáo doanh thu có thể âm thầm bỏ một đơn hợp lệ, khiến `SUM` và `COUNT` sai; ngược lại, dùng `UNION ALL` khi thật sự cần một tập kết quả không có bản ghi lặp cũng không đạt yêu cầu. Lựa chọn phải dựa trên **ý nghĩa của một hàng và quy tắc nhận diện bản ghi**, không chỉ mong muốn số hàng ít hay nhiều.

Bài học thuộc chương **Phép toán tập hợp** trong Database SQL, trình bày cú pháp, quy tắc tương thích cột và kiểu dữ liệu, khử trùng, thứ tự kết quả, phân trang, hiệu năng, cách gắn nguồn dữ liệu và các lỗi báo cáo thường gặp. Ví dụ chính chạy trên **PostgreSQL** bằng bảng tạm; những chỗ khác biệt giữa PostgreSQL, MySQL, SQL Server, Oracle và SQLite được ghi rõ.

## 1. Hợp nhất theo hàng khác kết nối theo cột

Trước khi viết SQL, hãy xác định mục tiêu là **nối dọc** hay **nối ngang**.

```text
UNION / UNION ALL: thêm hàng

Kết quả A              Kết quả B             Hợp nhất
+------+-------+       +------+-------+     +------+-------+
| id   | amount|       | id   | amount|     | id   | amount|
+------+-------+       +------+-------+     +------+-------+
| 101  | 120   |       | 201  | 200   |     | 101  | 120   |
| 102  |  80   |       | 202  |  80   |     | 102  |  80   |
+------+-------+       +------+-------+     | 201  | 200   |
                                            | 202  |  80   |
                                            +------+-------+

JOIN: thêm cột dựa trên điều kiện liên hệ giữa các hàng

orders(order_id, customer_id)  JOIN  customers(customer_id, name)
                      ↓
            (order_id, customer_id, name)
```

`UNION`/`UNION ALL` không dùng `ON` để ghép hai hàng tương ứng theo khóa. Chúng **xếp chồng các tập kết quả có cấu trúc tương thích**. `JOIN` ngược lại, kết hợp hàng từ các nguồn theo điều kiện ghép và có thể làm **nhân số hàng** trong quan hệ một-nhiều.

| Câu hỏi | Công cụ thường phù hợp |
| --- | --- |
| Hợp nhất danh sách đơn website và đơn cửa hàng | `UNION ALL` hoặc `UNION`, tùy chính sách trùng |
| Bổ sung tên khách vào mỗi đơn | `JOIN` theo khóa khách |
| Tìm khách có đơn ở một trong hai nguồn | Có thể dùng `UNION` trên danh sách định danh khách |
| Tìm những khách xuất hiện ở cả hai nguồn | `INTERSECT` hoặc điều kiện `EXISTS`/JOIN phù hợp |
| Tìm khách chỉ xuất hiện ở nguồn A | `EXCEPT`/`MINUS` hoặc `NOT EXISTS` tùy DBMS |

Trong SQL, kết quả SELECT thường cho phép **các hàng trùng nhau** (*bag/multiset semantics*). Chính vì thế `UNION` và `UNION ALL` có hành vi khác nhau mà người viết báo cáo cần chủ động lựa chọn.

## 2. Bộ dữ liệu thực hành: đơn hàng từ hai kênh

Mở một phiên PostgreSQL và tạo hai bảng tạm độc lập:

```sql
CREATE TEMP TABLE demo_web_orders (
    web_order_id INTEGER PRIMARY KEY,
    customer_id INTEGER NOT NULL,
    order_date DATE NOT NULL,
    amount NUMERIC(12, 2) NOT NULL CHECK (amount >= 0),
    status TEXT NOT NULL
);

CREATE TEMP TABLE demo_store_orders (
    store_order_id INTEGER PRIMARY KEY,
    customer_id INTEGER NOT NULL,
    order_date DATE NOT NULL,
    amount NUMERIC(12, 2) NOT NULL CHECK (amount >= 0),
    status TEXT NOT NULL
);

INSERT INTO demo_web_orders
    (web_order_id, customer_id, order_date, amount, status)
VALUES
    (101, 1, DATE '2026-09-01', 120.00, 'PAID'),
    (102, 2, DATE '2026-09-02',  80.00, 'PAID'),
    (103, 3, DATE '2026-09-03',  60.00, 'CANCELED'),
    (104, 1, DATE '2026-09-04', 120.00, 'PAID');

INSERT INTO demo_store_orders
    (store_order_id, customer_id, order_date, amount, status)
VALUES
    (101, 4, DATE '2026-09-01', 120.00, 'PAID'),
    (202, 2, DATE '2026-09-02',  80.00, 'PAID'),
    (203, 5, DATE '2026-09-05', 200.00, 'PAID'),
    (204, 3, DATE '2026-09-06',   0.00, 'REFUNDED');
```

Dữ liệu minh họa:

| Kênh | ID riêng của kênh | customer_id | order_date | amount | status |
| --- | ---: | ---: | --- | ---: | --- |
| WEB | 101 | 1 | 2026-09-01 | 120.00 | PAID |
| WEB | 102 | 2 | 2026-09-02 | 80.00 | PAID |
| WEB | 103 | 3 | 2026-09-03 | 60.00 | CANCELED |
| WEB | 104 | 1 | 2026-09-04 | 120.00 | PAID |
| STORE | 101 | 4 | 2026-09-01 | 120.00 | PAID |
| STORE | 202 | 2 | 2026-09-02 | 80.00 | PAID |
| STORE | 203 | 5 | 2026-09-05 | 200.00 | PAID |
| STORE | 204 | 3 | 2026-09-06 | 0.00 | REFUNDED |

Hai chi tiết được sắp đặt có chủ đích:

1. **WEB 101 và STORE 101 là hai đơn khác nhau** nhưng có cùng số ID trong *phạm vi hai hệ thống*, cùng ngày và cùng số tiền. Không được coi `order_id = 101` là khóa duy nhất trên cả hai kênh.
2. **WEB 102 và STORE 202** cũng có cùng ngày, số tiền và trạng thái PAID dù ID khác nhau. Khi bỏ những cột nhận diện nguồn, hai đơn sẽ trông giống hệt nhau ở kết quả.

Các số liệu gốc dễ đối chiếu:

- WEB có **4 đơn**, gồm **3 PAID** với tổng tiền PAID **320.00** (`120 + 80 + 120`).
- STORE có **4 đơn**, gồm **3 PAID** với tổng tiền PAID **400.00** (`120 + 80 + 200`).
- Hai kênh có **8 đơn thật**, gồm **6 PAID** với tổng tiền PAID **720.00**.

Hai giá trị 120.00 hoặc 80.00 xuất hiện nhiều lần **không phải bằng chứng rằng có giao dịch trùng cần loại**. Mục tiêu khi hợp nhất nguồn là giữ được từng giao dịch hợp lệ.

## 3. UNION ALL: giữ nguyên toàn bộ hàng của hai truy vấn

Trước tiên, chỉ lấy các đơn có status PAID rồi hợp nhất:

```sql
SELECT order_date, amount, status
FROM demo_web_orders
WHERE status = 'PAID'

UNION ALL

SELECT order_date, amount, status
FROM demo_store_orders
WHERE status = 'PAID'

ORDER BY order_date, amount;
```

Kết quả gồm **6 hàng**, vì mỗi kênh có ba đơn PAID:

| order_date | amount | status |
| --- | ---: | --- |
| 2026-09-01 | 120.00 | PAID |
| 2026-09-01 | 120.00 | PAID |
| 2026-09-02 | 80.00 | PAID |
| 2026-09-02 | 80.00 | PAID |
| 2026-09-04 | 120.00 | PAID |
| 2026-09-05 | 200.00 | PAID |

Hai cặp hàng trông giống nhau vẫn được giữ:

- Hai hàng `(2026-09-01, 120.00, PAID)` từ WEB 101 và STORE 101.
- Hai hàng `(2026-09-02, 80.00, PAID)` từ WEB 102 và STORE 202.

`UNION ALL` **không tự sinh giao dịch mới** và cũng không loại hàng trùng: nó giữ bội số từ mọi nhánh. Một nhánh trả hai hàng giống nhau thì cả hai vẫn có thể xuất hiện trong kết quả cuối.

### 3.1. Đếm hàng sau UNION ALL

```sql
WITH paid_orders AS (
    SELECT order_date, amount, status
    FROM demo_web_orders
    WHERE status = 'PAID'

    UNION ALL

    SELECT order_date, amount, status
    FROM demo_store_orders
    WHERE status = 'PAID'
)
SELECT
    COUNT(*) AS paid_order_count,
    SUM(amount) AS paid_total
FROM paid_orders;
```

Kết quả đúng theo **số hàng thực từ hai kênh**:

| paid_order_count | paid_total |
| ---: | ---: |
| 6 | 720.00 |

Với `UNION ALL`, số hàng kết quả bằng **tổng số hàng của các nhánh** (nếu không có toán tử lọc/giới hạn khác bên ngoài). Vì vậy, khi mỗi hàng nguồn thật sự đại diện cho một giao dịch hợp lệ, `UNION ALL` thường là lựa chọn phù hợp cho bước hợp nhất để tiếp tục tổng hợp.

## 4. UNION: loại các hàng trùng toàn bộ giá trị đã chọn

Thay `UNION ALL` bằng `UNION`:

```sql
SELECT order_date, amount, status
FROM demo_web_orders
WHERE status = 'PAID'

UNION

SELECT order_date, amount, status
FROM demo_store_orders
WHERE status = 'PAID'

ORDER BY order_date, amount;
```

Kết quả chỉ còn **4 hàng**:

| order_date | amount | status |
| --- | ---: | --- |
| 2026-09-01 | 120.00 | PAID |
| 2026-09-02 | 80.00 | PAID |
| 2026-09-04 | 120.00 | PAID |
| 2026-09-05 | 200.00 | PAID |

Tại sao? `UNION` xét **toàn bộ ba cột** `(order_date, amount, status)`; mỗi bộ giá trị chỉ được giữ một lần. Nó **không biết** hai bộ `(09-01, 120, PAID)` đến từ hai đơn độc lập và cũng không kiểm tra bảng có giao dịch trùng thật hay không.

Nếu tiếp tục tính:

```sql
WITH paid_rows AS (
    SELECT order_date, amount, status
    FROM demo_web_orders
    WHERE status = 'PAID'

    UNION

    SELECT order_date, amount, status
    FROM demo_store_orders
    WHERE status = 'PAID'
)
SELECT
    COUNT(*) AS number_of_rows,
    SUM(amount) AS sum_of_amount
FROM paid_rows;
```

Ta nhận **4 hàng** và **520.00**, thấp hơn số đúng 6 đơn và 720.00. Phần thiếu **200.00** đến từ việc gộp hai cặp giao dịch cùng thông tin đã chọn.

**UNION loại các hàng trùng ở hình dạng kết quả, không kiểm tra “bản ghi nghiệp vụ này đã tồn tại chưa”.**

### 4.1. UNION tương đương UNION DISTINCT

Trong những DBMS hỗ trợ cú pháp:

```sql
SELECT ...
UNION DISTINCT
SELECT ...
```

`UNION DISTINCT` diễn đạt rõ việc loại trùng, trong khi `UNION` mặc định đã có ý nghĩa loại trùng. Để giữ mọi hàng, phải ghi rõ **`UNION ALL`**. Khi viết SQL đa phương ngữ, `UNION` và `UNION ALL` là các dạng cốt lõi phổ biến nhất.

### 4.2. Một nhánh tự có hàng trùng thì sao?

UNION cũng loại các hàng trùng **xuất hiện trong chính một nhánh**, chứ không chỉ loại các bản sao giữa hai nhánh. Ví dụ:

```sql
SELECT 'A' AS source_label
UNION
SELECT 'A' AS source_label
UNION
SELECT 'B' AS source_label;
-- Hai giá trị A, B.
```

```sql
SELECT 'A' AS source_label
UNION ALL
SELECT 'A' AS source_label
UNION ALL
SELECT 'B' AS source_label;
-- Ba hàng A, A, B.
```

Vì vậy không được coi UNION như “chỉ tìm giao giữa hai bảng và bỏ bớt các bản trùng ở ranh giới”; phạm vi khử trùng của nó là **tập kết quả hợp nhất cuối cùng** theo các nhánh kết hợp.

## 5. Khử trùng dựa trên toàn bộ cột SELECT, không dựa trên khóa mặc định

Hãy xem sự thay đổi khi thêm cột `customer_id`:

```sql
SELECT customer_id, order_date, amount, status
FROM demo_web_orders
WHERE status = 'PAID'

UNION

SELECT customer_id, order_date, amount, status
FROM demo_store_orders
WHERE status = 'PAID'

ORDER BY order_date, amount, customer_id;
```

Lần này WEB 101 có customer_id 1, STORE 101 có customer_id 4, nên hai hàng **không còn trùng toàn bộ bốn cột**. Nhưng WEB 102 và STORE 202 đều có `customer_id = 2`, cùng ngày, amount và status, nên vẫn bị UNION gộp thành một hàng. Kết quả còn **5 hàng**.

Chỉ cần thêm hoặc bớt một cột trong SELECT, **quy tắc nhận diện hàng trùng của UNION đã đổi**. Đây là đặc điểm rất nguy hiểm nếu truy vấn lấy báo cáo dùng `UNION` rồi có người thay đổi danh sách cột sau này.

### 5.1. Tất cả giá trị bằng nhau mới được coi trùng

Với:

```text
(customer_id=1, order_date=2026-09-01, amount=120)
(customer_id=4, order_date=2026-09-01, amount=120)
```

hai hàng khác nhau vì `customer_id`. Nếu SELECT bỏ customer_id, hai hàng có thể trùng và bị gộp. SQL không tự dò khóa chính của bảng gốc để quyết định giữ hay bỏ.

### 5.2. ID của hai nguồn có thể trùng nhau

Nếu dùng:

```sql
SELECT
    web_order_id AS order_id,
    order_date,
    amount,
    status
FROM demo_web_orders
WHERE status = 'PAID'

UNION

SELECT
    store_order_id,
    order_date,
    amount,
    status
FROM demo_store_orders
WHERE status = 'PAID';
```

WEB 101 và STORE 101 vẫn có **cùng order_id, ngày, amount và status**, nên một hàng sẽ bị loại. Khóa `101` chỉ duy nhất **trong từng bảng**, không duy nhất trên toàn bộ hai hệ thống. Không nên suy luận rằng “đã chọn ID thì UNION sẽ không loại nhầm giao dịch”.

**Cách nhận diện nguồn phù hợp** thường là một khóa ghép như `(source_system, source_order_id)` hoặc một định danh toàn cục được tạo và quản lý có chủ đích.

## 6. Gắn nguồn dữ liệu để giữ danh tính mỗi bản ghi

Khi hợp nhất giao dịch từ hai kênh, cách an toàn và dễ truy vết là gắn **cột nguồn**:

```sql
SELECT
    'WEB'::TEXT AS source_system,
    web_order_id AS source_order_id,
    customer_id,
    order_date,
    amount,
    status
FROM demo_web_orders

UNION ALL

SELECT
    'STORE'::TEXT AS source_system,
    store_order_id AS source_order_id,
    customer_id,
    order_date,
    amount,
    status
FROM demo_store_orders

ORDER BY source_system, source_order_id;
```

Kết quả có **8 hàng** theo đúng số đơn thật, và hai ID 101 được phân biệt bởi:

```text
(WEB, 101)   -> đơn website
(STORE, 101) -> đơn cửa hàng
```

Cặp `(source_system, source_order_id)` giúp xác định giao dịch khi mỗi hệ thống cam kết ID của mình là duy nhất. Nếu dữ liệu có nhiều tenant, phiên bản hay loại sự kiện, khóa nghiệp vụ có thể cần thêm `tenant_id`, loại bản ghi hoặc phạm vi hợp lệ.

### 6.1. Khi nào UNION cũng giữ đủ tám hàng?

Nếu dùng `UNION` trên đủ các cột gồm `source_system` và ID duy nhất của nguồn, cả tám hàng cũng được giữ vì không còn hai hàng trùng **toàn bộ các cột**. Tuy nhiên, với nguồn đã đảm bảo khóa và không có yêu cầu loại hàng trùng, `UNION ALL` vẫn thể hiện rõ hơn ý định **hợp nhất mà không loại dữ liệu**, đồng thời tránh công đoạn khử trùng không cần thiết.

### 6.2. Giữ nguồn giúp tìm lỗi nạp dữ liệu

Khi phát hiện một giao dịch bất thường, `source_system` và `source_order_id` hỗ trợ tra về hệ thống gốc. Nếu bỏ nguồn trước khi tổng hợp, khó biết một dòng phát sinh từ website, cửa hàng hay đồng bộ lịch sử. Trong mô hình dữ liệu tích hợp, **provenance/lineage** thường quan trọng ngang với các cột số tiền hoặc thời điểm.

Không nên tạo một `order_id` chung bằng cách chỉ `CAST(id AS TEXT)`, vì hai hệ vẫn có thể dùng cùng chuỗi ID. Có thể xây dựng một khóa hiển thị như `WEB:101`, `STORE:101`, nhưng cột nguồn và cột ID riêng vẫn thường dễ kiểm tra và tạo ràng buộc hơn.

## 7. Quy tắc cốt lõi: các nhánh phải có số cột bằng nhau

SQL ghép các cột **theo vị trí**, không theo tên. Nếu nhánh đầu trả ba cột nhưng nhánh sau trả hai:

```sql
-- PostgreSQL: lỗi vì hai nhánh có số cột khác nhau.
SELECT web_order_id, order_date, amount
FROM demo_web_orders

UNION ALL

SELECT store_order_id, amount
FROM demo_store_orders;
```

Câu truy vấn không có một cấu trúc hàng thống nhất để hợp nhất. Nhánh hai phải cung cấp cùng **ba vị trí cột** tương ứng:

```sql
SELECT
    web_order_id AS source_order_id,
    order_date,
    amount
FROM demo_web_orders

UNION ALL

SELECT
    store_order_id,
    order_date,
    amount
FROM demo_store_orders;
```

Đây là yêu cầu về **số lượng cột**, nhưng chưa đủ để bảo đảm **đúng ý nghĩa dữ liệu**.

### 7.1. Ghép theo thứ tự: sai ý nghĩa mà SQL vẫn chạy

Hai cột số nguyên `customer_id` và `order_id` có thể bị đảo:

```sql
-- Sai logic, nhưng có thể không lỗi kiểu:
SELECT
    web_order_id AS source_order_id,
    customer_id
FROM demo_web_orders

UNION ALL

SELECT
    customer_id,        -- Sai vị trí: đây không phải order_id.
    store_order_id      -- Sai vị trí: đây không phải customer_id.
FROM demo_store_orders;
```

Vì cả hai vị trí đều có kiểu INTEGER, DBMS không nhất thiết phát hiện lỗi. Kết quả nhận hàng từ cửa hàng nhưng cột `source_order_id` lại chứa **ID khách**, còn cột thứ hai chứa **ID đơn**.

Hãy chủ động **liệt kê cùng cấu trúc cột theo cùng thứ tự và cùng ý nghĩa ở mọi nhánh**. Đặt alias rõ nghĩa ở nhánh đầu, sau đó đối chiếu từng vị trí của những nhánh còn lại.

### 7.2. Tránh SELECT * khi UNION các nguồn

```sql
-- Mong manh vì số cột và thứ tự của hai bảng có thể khác.
SELECT *
FROM demo_web_orders

UNION ALL

SELECT *
FROM demo_store_orders;
```

Hai bảng mẫu có số cột bằng nhau, nên câu này có thể chạy trên PostgreSQL. Nhưng nếu một bảng được thêm cột như `salesperson_id`, một bên có thêm cột nội bộ, hoặc thứ tự lưu trữ của cột khác nhau, UNION có thể lỗi hoặc ghép nhầm giá trị. Ngay cả khi cấu trúc hiện tại giống nhau, `SELECT *` làm **hợp đồng đầu ra phụ thuộc schema nguồn**.

Khi hợp nhất nguồn cho API, báo cáo hoặc bảng đích lâu dài, nên chọn cột tường minh và đặt alias theo **một schema kết quả thống nhất**.

## 8. Kiểu dữ liệu tương thích: không phải mọi cột đều có thể UNION

Mỗi **vị trí cột** ở các nhánh phải có **kiểu tương thích để DBMS xác định kiểu kết quả chung**. Những kiểu được phép chuyển đổi hoặc cách chuyển có thể khác nhau giữa các hệ quản trị.

Ví dụ hợp lệ trong PostgreSQL:

```sql
SELECT
    web_order_id::BIGINT AS source_order_id,
    amount::NUMERIC(14, 2) AS amount
FROM demo_web_orders

UNION ALL

SELECT
    store_order_id::BIGINT,
    amount::NUMERIC(14, 2)
FROM demo_store_orders;
```

Hai nhánh cùng chọn BIGINT và NUMERIC(14,2), giúp người đọc biết kiểu đầu ra mong đợi.

### 8.1. Trường hợp kiểu không tương thích

```sql
-- PostgreSQL: không thể tự hợp nhất DATE với NUMERIC
-- tại cùng vị trí theo phép UNION này.
SELECT order_date AS value
FROM demo_web_orders

UNION ALL

SELECT amount
FROM demo_store_orders;
```

DBMS phải giải quyết một cột kết quả duy nhất từ DATE và NUMERIC. Với những kiểu không có cách ép chung hợp lệ, truy vấn báo lỗi. Không nên “sửa” bằng cách ép cả hai sang TEXT khi **một nhánh là ngày, nhánh kia là số tiền**: câu SQL có thể chạy nhưng cột `value` không còn một ý nghĩa nghiệp vụ nhất quán.

### 8.2. Kiểu có thể chuyển ngầm vẫn cần chú ý

Một nhánh trả INTEGER, nhánh kia trả NUMERIC có thể khiến DBMS chọn kiểu số rộng hơn. Điều này không nhất thiết là lỗi, nhưng có thể ảnh hưởng cách driver ánh xạ kết quả, độ chính xác, việc so sánh và hiệu năng.

Đặc biệt với giá trị tiền, ngày, timestamp, timezone và mã định danh, hãy chọn kiểu chung theo **hợp đồng dữ liệu**, không dựa hoàn toàn vào chuyển kiểu ngầm.

```sql
SELECT
    'WEB'::TEXT AS source_system,
    web_order_id::BIGINT AS source_order_id,
    order_date::DATE AS order_date,
    amount::NUMERIC(14, 2) AS amount
FROM demo_web_orders

UNION ALL

SELECT
    'STORE'::TEXT,
    store_order_id::BIGINT,
    order_date::DATE,
    amount::NUMERIC(14, 2)
FROM demo_store_orders;
```

### 8.3. Bổ sung cột chỉ có ở một nguồn bằng NULL có kiểu

Giả sử hệ website có `coupon_code`, nhưng cửa hàng chưa có trường tương ứng. Một cấu trúc đầu ra thống nhất có thể viết:

```sql
-- Ví dụ khái niệm: giả định bảng web có coupon_code TEXT.
SELECT
    'WEB'::TEXT AS source_system,
    web_order_id AS source_order_id,
    coupon_code::TEXT AS coupon_code
FROM web_orders_with_coupons

UNION ALL

SELECT
    'STORE'::TEXT,
    store_order_id,
    NULL::TEXT AS coupon_code
FROM demo_store_orders;
```

`NULL::TEXT` cho biết cột không có dữ liệu ở nhánh STORE nhưng vẫn có kiểu văn bản. Trong SQL dùng lâu dài, nên giải thích NULL ở đây là **không có thông tin/cột không áp dụng**, khác với chuỗi rỗng hoặc mã coupon thực sự mang giá trị `'NULL'`.

Đoạn `web_orders_with_coupons` là **bảng giả định**, không nằm trong bộ dữ liệu tạm mục 2. Mục đích là minh họa cách thiết kế schema chung khi hai nguồn không có cùng trường.

### 8.4. Không ép mã định danh sang số chỉ để thống nhất kiểu

Nếu nguồn A có mã `'000123'` và nguồn B có mã `'123'`, ép cả hai về số nguyên sẽ khiến hai mã đều thành `123`. Điều đó có thể gây **trùng sai** khi dùng UNION, hoặc mất thông tin trong dữ liệu hợp nhất. Nếu số 0 đầu là một phần mã, giữ cột ở dạng văn bản và quy định chuẩn hóa theo chính sách định danh.

## 9. Tên cột kết quả: chủ yếu theo nhánh đầu

Khi hai nhánh đặt tên alias khác nhau ở cùng vị trí:

```sql
SELECT
    web_order_id AS source_order_id,
    amount AS order_amount
FROM demo_web_orders

UNION ALL

SELECT
    store_order_id AS store_id,
    amount AS store_total
FROM demo_store_orders;
```

Trong PostgreSQL và nhiều DBMS, **tên cột đầu ra** của phép UNION được xác định từ **nhánh SELECT đầu tiên**: `source_order_id`, `order_amount`. Alias `store_id`, `store_total` trong nhánh hai không tự đổi tên cột kết quả.

Điều này cho thấy UNION ghép **vị trí**: cột số 1 của nhánh thứ hai đi vào cột số 1 của kết quả, dù hai alias khác nhau.

**Thói quen tốt:** chọn một danh sách alias có ý nghĩa chung (`source_order_id`, `order_date`, `amount`, `status`) rồi lặp lại cùng thứ tự ở các nhánh, thay vì dựa vào việc hệ quản trị tự khớp theo tên.

## 10. NULL và quy tắc nhận diện hàng trùng

Trong điều kiện so sánh thông thường:

```sql
NULL = NULL
```

cho kết quả **UNKNOWN**, không phải TRUE. Nhưng trong quá trình **loại hàng trùng** của `UNION`, các hàng có NULL ở cùng những vị trí tương ứng vẫn có thể được xem là **không phân biệt được** và chỉ giữ một bản. Đây là ngữ nghĩa khử trùng, không phải phép so sánh `=` đơn giản trong WHERE.

Ví dụ PostgreSQL:

```sql
SELECT NULL::TEXT AS label
UNION
SELECT NULL::TEXT AS label;
-- Một hàng với label = NULL.
```

```sql
SELECT NULL::TEXT AS label
UNION ALL
SELECT NULL::TEXT AS label;
-- Hai hàng, cả hai label = NULL.
```

Với hai cột, nếu giá trị không NULL giống nhau và các vị trí NULL tương ứng giống nhau, UNION có thể gộp hàng:

```sql
SELECT 1 AS event_id, NULL::TEXT AS note
UNION
SELECT 1 AS event_id, NULL::TEXT AS note;
-- Một hàng (1, NULL).
```

Nếu chỉ khác một cột xác định:

```sql
SELECT 1 AS event_id, NULL::TEXT AS note
UNION
SELECT 2 AS event_id, NULL::TEXT AS note;
-- Hai hàng vì event_id khác nhau.
```

### 10.1. NULL mang ý nghĩa gì khi nguồn không có cột?

Nếu một nguồn không có `coupon_code` và luôn điền NULL, nhiều bản ghi từ nguồn ấy vẫn có thể bị `UNION` gộp khi **mọi cột khác trong SELECT cũng giống nhau**. Bổ sung NULL để thống nhất cấu trúc là hợp lệ, nhưng không tự bảo đảm giữ nguyên từng sự kiện. Với dữ liệu giao dịch, thường vẫn cần `source_system` và định danh nguồn.

### 10.2. Kiểu, collation và biểu thức có thể ảnh hưởng trùng

Phép khử trùng cần xác định **hai giá trị có được xem là bằng nhau không** theo kiểu và quy tắc so sánh của DBMS. Chữ hoa/chữ thường, collation, khoảng trắng, kiểu dấu phẩy động, timezone hoặc cách chuẩn hóa chuỗi có thể làm những chuỗi trông tương tự được xem là giống hoặc khác. Một số kiểu như JSON nguyên bản trong PostgreSQL không có toán tử bình đẳng thích hợp để khử trùng bằng UNION, trong khi `jsonb` có các quy tắc so sánh riêng.

Do đó, với dữ liệu cần gộp theo **khóa nghiệp vụ**, không nên dựa vào việc “UNION có lẽ nhận ra bản ghi trùng” chỉ vì nội dung hiển thị gần giống nhau. Phải định nghĩa chính xác khóa, cách chuẩn hóa và quy tắc trùng.

## 11. Thứ tự kết quả: UNION không cam kết bên nào đứng trước

Một câu lệnh như:

```sql
SELECT web_order_id AS source_order_id
FROM demo_web_orders

UNION ALL

SELECT store_order_id
FROM demo_store_orders;
```

**Không cam kết** các hàng từ WEB luôn nằm trước STORE hoặc các ID luôn tăng/giảm. Dù một lần chạy có vẻ theo thứ tự “nhánh đầu rồi nhánh sau”, kế hoạch thực thi hoặc môi trường song song có thể thay đổi cách dữ liệu được cung cấp cho kết quả.

`UNION` cũng **không tự bảo đảm** kết quả được sắp xếp chỉ vì hệ quản trị có thể chọn một thuật toán Sort để khử trùng. Thứ tự đầu ra được cam kết khi có **`ORDER BY` cuối cùng** phù hợp.

### 11.1. ORDER BY sau toàn bộ phép hợp nhất

```sql
SELECT
    'WEB'::TEXT AS source_system,
    web_order_id AS source_order_id,
    order_date AS event_date,
    amount
FROM demo_web_orders

UNION ALL

SELECT
    'STORE'::TEXT,
    store_order_id,
    order_date,
    amount
FROM demo_store_orders

ORDER BY event_date DESC, source_system, source_order_id DESC;
```

`ORDER BY` cuối cùng sắp **toàn bộ tập kết quả của cả hai kênh**. Vì có cột nguồn và ID của nguồn ở phần khóa phụ, mỗi giao dịch có vị trí rõ hơn khi các ngày trùng nhau.

Khi phân trang, nên có khóa ORDER BY **đủ phân biệt tất cả hàng** — ví dụ `(event_date DESC, source_system ASC, source_order_id DESC)` nếu cặp `(source_system, source_order_id)` duy nhất. Không có thứ tự đủ phân biệt, các hàng cùng event_date có thể đổi vị trí giữa các lần chạy.

### 11.2. ORDER BY trong biểu thức UNION có giới hạn

Trong PostgreSQL, `ORDER BY` gắn trực tiếp vào kết quả của `UNION` thường tham chiếu **tên cột đầu ra hoặc vị trí cột**, không được tùy ý viết biểu thức phức tạp chưa có trong target list. Ví dụ có thể cần bao ngoài nếu muốn sắp theo biểu thức mới:

```sql
SELECT *
FROM (
    SELECT
        'WEB'::TEXT AS source_system,
        web_order_id AS source_order_id,
        order_date,
        amount
    FROM demo_web_orders

    UNION ALL

    SELECT
        'STORE'::TEXT,
        store_order_id,
        order_date,
        amount
    FROM demo_store_orders
) AS combined
ORDER BY ABS(combined.amount - 100) DESC,
         combined.source_system,
         combined.source_order_id;
```

Truy vấn ngoài được phép viết biểu thức ORDER BY theo các cột của `combined`. Nếu chỉ cần sắp theo cột đã được SELECT, thường không cần truy vấn ngoài.

## 12. LIMIT/OFFSET và TOP N trong hợp nhất kết quả

Nếu muốn lấy **năm đơn mới nhất trên cả hai kênh**, `LIMIT` phải áp dụng **sau khi đã hợp nhất**:

```sql
SELECT
    'WEB'::TEXT AS source_system,
    web_order_id AS source_order_id,
    order_date
FROM demo_web_orders

UNION ALL

SELECT
    'STORE'::TEXT,
    store_order_id,
    order_date
FROM demo_store_orders

ORDER BY order_date DESC, source_system, source_order_id DESC
LIMIT 5;
```

Đây là truy vấn PostgreSQL. `ORDER BY` quyết định năm hàng đứng đầu trong **toàn bộ 8 đơn**, chứ không chọn năm đơn từ mỗi nguồn.

### 12.1. Giới hạn từng nhánh là bài toán khác

Giả sử muốn lấy **hai đơn mới nhất của website và hai đơn mới nhất của cửa hàng**, tức mỗi nguồn tối đa hai:

```sql
(
    SELECT
        'WEB'::TEXT AS source_system,
        web_order_id AS source_order_id,
        order_date
    FROM demo_web_orders
    ORDER BY order_date DESC, web_order_id DESC
    LIMIT 2
)

UNION ALL

(
    SELECT
        'STORE'::TEXT AS source_system,
        store_order_id AS source_order_id,
        order_date
    FROM demo_store_orders
    ORDER BY order_date DESC, store_order_id DESC
    LIMIT 2
)

ORDER BY order_date DESC, source_system, source_order_id DESC;
```

Các dấu ngoặc quanh từng SELECT cho phép áp dụng ORDER BY/LIMIT **ở nhánh riêng** trong PostgreSQL. Kết quả chứa tối đa **4 hàng** — hai hàng của mỗi kênh — rồi mới được sắp chung.

So sánh hai mục đích:

- `UNION ALL ... ORDER BY ... LIMIT 2` sau toàn bộ câu: **hai đơn mới nhất toàn hệ thống**.
- `(SELECT ... LIMIT 2) UNION ALL (SELECT ... LIMIT 2)`: **hai đơn mới nhất mỗi nguồn**, tổng tối đa bốn.

Đừng đặt giới hạn sai cấp vì kết quả rất dễ **không có lỗi cú pháp nhưng sai yêu cầu nghiệp vụ**.

### 12.2. Đừng phân trang dựa trên thứ tự ngầm

Nếu chỉ:

```sql
... UNION ALL ... LIMIT 20 OFFSET 20
```

mà không có ORDER BY cuối, “trang thứ hai” không có nghĩa ổn định. Cần chọn thứ tự có khóa phụ duy nhất. Dù ORDER BY đầy đủ, phân trang OFFSET qua nhiều lần gọi vẫn có thể lặp/bỏ sót khi dữ liệu thay đổi giữa các trang; khi danh sách lớn và được cập nhật liên tục, có thể cân nhắc **keyset pagination** trên các khóa kết quả có nguồn và ID.

## 13. Đặt UNION trong CTE để tổng hợp dữ liệu đa nguồn

Một mẫu điển hình là tạo một quan hệ logic chung rồi tổng hợp:

```sql
WITH unified_orders AS (
    SELECT
        'WEB'::TEXT AS source_system,
        web_order_id AS source_order_id,
        customer_id,
        order_date,
        amount,
        status
    FROM demo_web_orders

    UNION ALL

    SELECT
        'STORE'::TEXT,
        store_order_id,
        customer_id,
        order_date,
        amount,
        status
    FROM demo_store_orders
)
SELECT
    source_system,
    COUNT(*) AS all_orders,
    COUNT(*) FILTER (WHERE status = 'PAID') AS paid_orders,
    SUM(amount) FILTER (WHERE status = 'PAID') AS paid_amount
FROM unified_orders
GROUP BY source_system
ORDER BY source_system;
```

Kết quả:

| source_system | all_orders | paid_orders | paid_amount |
| --- | ---: | ---: | ---: |
| STORE | 4 | 3 | 400.00 |
| WEB | 4 | 3 | 320.00 |

Trong PostgreSQL, `FILTER (WHERE ...)` là cách ngắn gọn để tổng hợp có điều kiện. Ở DBMS không hỗ trợ FILTER, có thể dùng CASE:

```sql
SUM(CASE WHEN status = 'PAID' THEN 1 ELSE 0 END)
```

để đếm PAID và:

```sql
SUM(CASE WHEN status = 'PAID' THEN amount ELSE 0 END)
```

để cộng số tiền PAID, khi đã quyết định ý nghĩa của 0/NULL phù hợp với dữ liệu. Cú pháp CASE có tính phổ biến cao hơn giữa các phương ngữ.

### 13.1. Tổng hợp toàn hệ thống

```sql
WITH unified_orders AS (
    SELECT amount, status FROM demo_web_orders
    UNION ALL
    SELECT amount, status FROM demo_store_orders
)
SELECT
    COUNT(*) AS all_orders,
    COUNT(*) FILTER (WHERE status = 'PAID') AS paid_orders,
    SUM(amount) FILTER (WHERE status = 'PAID') AS paid_amount
FROM unified_orders;
```

Kết quả **8 đơn**, **6 PAID**, **720.00** tiền PAID. Ở đây `UNION ALL` được dùng vì từng hàng hai nguồn là một đơn thực, và nghiệp vụ không yêu cầu loại bỏ các giao dịch có cùng amount/status.

### 13.2. WHERE ngoài so với WHERE từng nhánh

Có thể lọc status PAID **sau hợp nhất**:

```sql
WITH unified_orders AS (
    SELECT amount, status FROM demo_web_orders
    UNION ALL
    SELECT amount, status FROM demo_store_orders
)
SELECT COUNT(*) AS paid_orders
FROM unified_orders
WHERE status = 'PAID';
```

Hoặc đặt điều kiện giống nhau ở **cả hai nhánh**:

```sql
SELECT amount, status
FROM demo_web_orders
WHERE status = 'PAID'

UNION ALL

SELECT amount, status
FROM demo_store_orders
WHERE status = 'PAID';
```

Khi điều kiện giống nhau, việc lọc trước hay sau có thể tương đương về tập hàng của `UNION ALL`. Bộ tối ưu thường có khả năng đẩy điều kiện xuống nguồn, nhưng không nên giả định một kế hoạch vật lý cố định. Nếu điều kiện thực tế của WEB và STORE **khác nhau** do chính sách trạng thái, phải nêu rõ ở từng nguồn và bảo đảm chỉ số chung vẫn đo cùng khái niệm.

## 14. UNION ALL sau khi tổng hợp từng nhánh

Đôi khi hệ thống không cần chuyển hết chi tiết hai bảng về một kết quả trung gian; chỉ cần **tổng số đơn và tổng tiền PAID của mỗi kênh**.

```sql
WITH per_source AS (
    SELECT
        'WEB'::TEXT AS source_system,
        COUNT(*) FILTER (WHERE status = 'PAID') AS paid_count,
        SUM(amount) FILTER (WHERE status = 'PAID') AS paid_amount
    FROM demo_web_orders

    UNION ALL

    SELECT
        'STORE'::TEXT,
        COUNT(*) FILTER (WHERE status = 'PAID'),
        SUM(amount) FILTER (WHERE status = 'PAID')
    FROM demo_store_orders
)
SELECT
    SUM(paid_count) AS paid_count,
    SUM(paid_amount) AS paid_amount
FROM per_source;
```

Kết quả vẫn là **6 đơn PAID**, **720.00**.

### 14.1. Vì sao vẫn dùng UNION ALL cho các chỉ số đã tổng hợp?

Giả sử hai kênh tình cờ đều có `paid_count = 3` và `paid_amount = 320.00`. Nếu UNION chỉ chọn **hai cột số liệu** mà không có nguồn, một hàng tổng hợp có thể bị loại vì trùng hoàn toàn, khiến phép SUM ngoài **chỉ cộng một kênh**.

Kể cả khi có `source_system`, các nhánh đã có một chỉ số độc lập cho mỗi nguồn; `UNION ALL` vẫn diễn đạt đúng yêu cầu giữ mọi chỉ số nguồn. Không cần làm một phép DISTINCT trên kết quả tổng hợp rồi hy vọng nó không ảnh hưởng tổng cộng.

### 14.2. Những điều kiện cần thống nhất trước khi cộng

Hai bảng có thể có cách gọi trạng thái, đơn vị tiền hoặc thời điểm khác nhau. Ví dụ:

- WEB dùng `'PAID'`, STORE dùng `'SUCCESS'` cho việc thanh toán đã hoàn tất.
- WEB lưu tiền bằng đồng, STORE lưu tiền bằng đơn vị nhỏ hơn hoặc ngoại tệ.
- Một nguồn ghi doanh thu khi tạo đơn, nguồn kia khi hoàn tất thanh toán.
- Một nguồn chứa cả yêu cầu thanh toán bị hủy và sự kiện hoàn tiền.

UNION không tự biết các giá trị này có cùng ý nghĩa. Phải **chuẩn hóa trạng thái, đơn vị tiền, thời điểm ghi nhận, mã nguồn và chính sách loại trùng** trước khi hợp nhất KPI. Truy vấn chạy hợp lệ chưa chứng minh số tiền cộng được với nhau.

## 15. UNION không phải công cụ khử trùng theo khóa nghiệp vụ

Đây là sự khác biệt quan trọng giữa **loại hàng trùng giá trị** và **chọn một bản đại diện cho thực thể có cùng khóa**.

Giả sử một nguồn có hai phiên bản của đơn 101:

```text
order_id   updated_at            amount   status
101        2026-09-01 09:00      120      PENDING
101        2026-09-01 10:00      120      PAID
```

Hai hàng **không trùng toàn bộ các cột** vì updated_at và status khác nhau. `UNION` vẫn giữ cả hai, mặc dù báo cáo trạng thái hiện hành chỉ muốn **một phiên bản mới nhất cho order_id = 101**.

Ngược lại, hai giao dịch khác nhau có cùng các thuộc tính hiển thị lại có thể bị UNION gộp. Vì thế, không dùng UNION như một phép “deduplicate by order_id” nếu chưa xác định rõ các cột và quy tắc chọn bản ghi.

### 15.1. Hợp nhất trước, rồi chọn bản ghi mới nhất theo khóa

Giả sử có hai bảng lịch sử cùng kiểu đầu ra, `orders_current_feed` và `orders_backfill_feed`, mỗi bảng có:

```text
source_system, source_order_id, updated_at, status, amount, ingestion_id
```

Mẫu SQL PostgreSQL:

```sql
WITH all_versions AS (
    SELECT
        source_system,
        source_order_id,
        updated_at,
        status,
        amount,
        ingestion_id
    FROM orders_current_feed

    UNION ALL

    SELECT
        source_system,
        source_order_id,
        updated_at,
        status,
        amount,
        ingestion_id
    FROM orders_backfill_feed
),
ranked AS (
    SELECT
        *,
        ROW_NUMBER() OVER (
            PARTITION BY source_system, source_order_id
            ORDER BY updated_at DESC, ingestion_id DESC
        ) AS rn
    FROM all_versions
)
SELECT
    source_system,
    source_order_id,
    updated_at,
    status,
    amount
FROM ranked
WHERE rn = 1;
```

**Đây là ví dụ mô hình giả định**, không phải bảng tạm đã tạo ở mục 2. `ROW_NUMBER()` chọn **một hàng** cho mỗi khóa `(source_system, source_order_id)` theo thời điểm cập nhật và khóa phụ `ingestion_id`.

Để tránh kết quả không ổn định, thứ tự `ORDER BY updated_at DESC, ingestion_id DESC` cần đủ phân biệt trong mỗi nhóm, hoặc phải có quy tắc giải quyết các bản ghi trùng thời điểm/khóa. Nếu cần giữ lịch sử thay đổi, **không được áp dụng `rn = 1` một cách máy móc** vì điều đó bỏ đi các phiên bản hợp lệ.

### 15.2. Dùng DISTINCT ON của PostgreSQL khi phù hợp

PostgreSQL còn có cú pháp riêng `DISTINCT ON (keys)` để chọn một hàng theo khóa khi kết hợp với ORDER BY phù hợp:

```sql
SELECT DISTINCT ON (source_system, source_order_id)
    source_system,
    source_order_id,
    updated_at,
    status,
    amount
FROM all_versions
ORDER BY
    source_system,
    source_order_id,
    updated_at DESC,
    ingestion_id DESC;
```

Ví dụ này giả định `all_versions` là một CTE/bảng nguồn được định nghĩa ở **cùng câu truy vấn**, không phải một đối tượng tự tồn tại trong database. `DISTINCT ON` không phải cú pháp SQL chuẩn có mặt ở mọi hệ; `ROW_NUMBER()` thường dễ diễn đạt hơn trong SQL đa phương ngữ.

Quan trọng là **quy tắc loại trùng theo khóa và phiên bản được viết tường minh**, chứ không phó thác cho UNION loại các hàng có giá trị giống nhau.

## 16. UNION so với các phép toán tập hợp khác

Trong nhóm set operations:

| Toán tử | Câu hỏi | Ngữ nghĩa cơ bản |
| --- | --- | --- |
| `UNION` | Những hàng nào xuất hiện ở **ít nhất một** nguồn, mỗi giá trị một lần? | Hợp nhất và khử trùng toàn hàng |
| `UNION ALL` | Những hàng nào xuất hiện ở các nguồn, giữ **mọi lần xuất hiện**? | Hợp nhất giữ bội số |
| `INTERSECT` | Những hàng nào xuất hiện ở **cả hai** kết quả? | Lấy phần chung |
| `EXCEPT` (Oracle thường dùng `MINUS` ở các phiên bản liên quan) | Những hàng nào ở kết quả A mà **không** ở B? | Lấy phần chênh |

Ví dụ đơn giản trong PostgreSQL:

```sql
SELECT 1 AS x
UNION
SELECT 2 AS x;
-- 1, 2
```

```sql
SELECT 1 AS x
INTERSECT
SELECT 1 AS x;
-- 1
```

```sql
SELECT 1 AS x
EXCEPT
SELECT 1 AS x;
-- Không có hàng.
```

Các toán tử này cùng có yêu cầu tương thích cấu trúc cột, nhưng mục đích khác nhau. `UNION` **không phải** phép nối quan hệ theo khóa, và `UNION ALL` **không có nghĩa** chỉ chọn những hàng có mặt ở cả hai nguồn.

### 16.1. Dấu ngoặc và thứ tự kết hợp

Khi trộn nhiều toán tử, nên dùng **dấu ngoặc** để thể hiện nhóm:

```sql
(
    SELECT customer_id FROM demo_web_orders
    UNION
    SELECT customer_id FROM demo_store_orders
)
INTERSECT
SELECT customer_id FROM demo_web_orders;
```

Trong nhiều phương ngữ, `INTERSECT` có độ ưu tiên khác `UNION`/`EXCEPT`; vì vậy không dựa vào trí nhớ về thứ tự ưu tiên khi truy vấn phức tạp. Viết dấu ngoặc giúp biểu thị rõ tập nào được hợp nhất, tập nào được giao hoặc trừ.

### 16.2. Kết hợp UNION và UNION ALL trong cùng câu

```sql
SELECT 1 AS x
UNION ALL
SELECT 1 AS x
UNION
SELECT 2 AS x;
```

Kết quả phụ thuộc **cấu trúc kết hợp và quy tắc DISTINCT tại vị trí UNION**; khi cần bảo toàn bội số ở một phần nhưng loại trùng ở phần khác, nên tách thành CTE hoặc dùng dấu ngoặc để thể hiện mục tiêu chính xác.

**Đừng coi chỉ cần có UNION ALL ở một đoạn là toàn bộ truy vấn cuối không loại trùng**, hoặc chỉ cần có UNION ở một đoạn là tất cả thao tác sau đó luôn khử trùng — mỗi toán tử áp dụng vào những đầu vào mà cú pháp xác định.

## 17. Hiệu năng: vì sao UNION ALL thường ít công việc hơn UNION?

Về ngữ nghĩa, UNION ALL có thể **ghép/append** các hàng của các nhánh mà không cần xác định hàng nào trùng. UNION phải làm thêm **bước khử trùng** trên những cột kết quả, thường bằng một trong các nhóm kỹ thuật:

- Sắp xếp (*Sort*) các hàng rồi loại các nhóm trùng;
- Băm (*Hash*) các khóa hàng để xác định giá trị phân biệt;
- Biến đổi kế hoạch khác của bộ tối ưu, tùy dữ liệu và DBMS.

Với dữ liệu lớn hoặc hàng rộng, việc kiểm tra trùng có thể cần thêm CPU, bộ nhớ, thao tác sort/hash và có thể sử dụng đĩa tạm khi thiếu bộ nhớ.

**Không kết luận `UNION ALL` luôn nhanh hơn trong mọi câu truy vấn cụ thể.** Bộ tối ưu có nhiều cách cải thiện, và tổng thời gian còn tùy nguồn, JOIN, WHERE, số hàng, chỉ mục và việc truyền dữ liệu. Nhưng nếu nghiệp vụ **cần giữ mọi hàng**, thêm UNION DISTINCT là một bước không có ích về ngữ nghĩa và có thể tạo chi phí.

### 17.1. Đọc EXPLAIN trên PostgreSQL

```sql
EXPLAIN
SELECT order_date, amount, status
FROM demo_web_orders
UNION ALL
SELECT order_date, amount, status
FROM demo_store_orders;
```

```sql
EXPLAIN
SELECT order_date, amount, status
FROM demo_web_orders
UNION
SELECT order_date, amount, status
FROM demo_store_orders;
```

Trong PostgreSQL, có thể thấy kế hoạch kiểu **Append** cho UNION ALL, còn UNION có thể thêm **HashAggregate** hoặc **Sort/Unique** để loại trùng. Kế hoạch cụ thể thay đổi theo phiên bản, số hàng, kiểu cột và ước lượng chi phí; không phải lúc nào cũng hiện đúng các tên node này.

Khi muốn đo thực thi SELECT:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT
    'WEB'::TEXT AS source_system,
    web_order_id AS source_order_id,
    amount
FROM demo_web_orders
UNION ALL
SELECT
    'STORE'::TEXT,
    store_order_id,
    amount
FROM demo_store_orders;
```

`EXPLAIN ANALYZE` **thực sự chạy truy vấn SELECT** và báo số hàng, thời gian và buffer; hãy đo trên dữ liệu đại diện. Hai bảng mẫu chỉ có vài hàng, vì vậy không đủ để kết luận hiệu năng khi chạy trên hàng chục triệu giao dịch.

### 17.2. Chọn đúng cột giúp giảm chi phí khử trùng

Nếu UNION phải so sánh mọi cột đầu ra, việc mang theo cột JSON hoặc văn bản rất lớn có thể làm tăng chi phí, hoặc một số kiểu không hỗ trợ phép so sánh bằng cần thiết để khử trùng. Đừng dùng `SELECT *` chỉ vì muốn “gộp đủ dữ liệu”; hãy chọn những cột đúng hợp đồng.

Tuy nhiên, **bỏ cột có thể làm thay đổi nghĩa của UNION**: khi ít cột hơn, nhiều hàng trở nên giống nhau và bị loại. Nếu KPI cần bản ghi giao dịch, phải giữ **định danh đúng** hoặc dùng UNION ALL và xử lý dedup theo khóa.

### 17.3. Chỉ mục không thay thế quy tắc nghiệp vụ

Một chỉ mục trên `order_date` có thể giúp lọc và sắp xếp các nhánh; chỉ mục trên ID giúp truy tìm bản ghi nguồn. Nhưng chỉ mục **không khiến UNION tự biết** hai đơn giống số tiền có phải cùng một giao dịch hay không. Những lựa chọn về khử trùng thuộc về **ngữ nghĩa đầu ra**, không phải bài toán tối ưu của index.

## 18. Đối chiếu cú pháp theo hệ quản trị

Hai dạng `UNION` và `UNION ALL` rất phổ biến trong SQL, nhưng tên kiểu, cú pháp giới hạn hàng và một số quy tắc ORDER BY khác nhau:

| DBMS | Hợp nhất | Gợi ý cú pháp theo hệ |
| --- | --- | --- |
| **PostgreSQL** | `UNION`, `UNION ALL` | Có `::type`, `LIMIT`/`FETCH`; ORDER BY cuối có giới hạn biểu thức khi trực tiếp theo set op |
| **MySQL** | `UNION`, `UNION ALL` | Thường dùng `LIMIT`; có dạng `UNION DISTINCT`; chú ý tên cột, kiểu suy luận và collation |
| **SQL Server** | `UNION`, `UNION ALL` | Dùng `CAST`/`CONVERT`, `TOP` hoặc `OFFSET ... FETCH` với ORDER BY; không dùng `LIMIT` như PostgreSQL |
| **Oracle Database** | `UNION`, `UNION ALL` | Dùng kiểu `NUMBER`, `VARCHAR2`, `DATE`; row-limiting bằng `FETCH FIRST` ở phiên bản hỗ trợ; việc chuyển kiểu qua nhóm kiểu có quy tắc riêng |
| **SQLite** | `UNION`, `UNION ALL` | Kiểu động; vẫn phải khớp số cột; quy tắc so sánh/affinity có đặc thù |

Ví dụ SQL Server:

```sql
SELECT
    CAST('WEB' AS VARCHAR(10)) AS source_system,
    web_order_id AS source_order_id,
    order_date,
    amount
FROM dbo.web_orders

UNION ALL

SELECT
    CAST('STORE' AS VARCHAR(10)),
    store_order_id,
    order_date,
    amount
FROM dbo.store_orders

ORDER BY order_date DESC, source_system, source_order_id DESC;
```

`dbo.web_orders` và `dbo.store_orders` là **bảng giả định của SQL Server**, không phải bảng tạm PostgreSQL ở mục 2. Cú pháp CAST cột nguồn, alias và ORDER BY phù hợp với T-SQL trong trường hợp này.

Ví dụ Oracle:

```sql
SELECT 'WEB' AS source_system,
       web_order_id AS source_order_id,
       order_date,
       amount
FROM web_orders
UNION ALL
SELECT 'STORE',
       store_order_id,
       order_date,
       amount
FROM store_orders
ORDER BY order_date DESC, source_system, source_order_id DESC;
```

Để chạy ví dụ Oracle, các bảng và kiểu cột tương ứng phải được tạo ở Oracle. Khi chuyển dữ liệu giữa hệ, phải kiểm soát **DATE có chứa giờ hay không, timezone, kiểu số và quy tắc chuỗi/NULL**, không chỉ đổi tên bảng.

### 18.1. Giới hạn ở cuối UNION theo từng hệ

Nếu muốn 10 hàng sau hợp nhất và sắp xếp:

- PostgreSQL/MySQL/SQLite thường sử dụng `ORDER BY ... LIMIT 10`.
- Oracle hiện đại có thể sử dụng `ORDER BY ... FETCH FIRST 10 ROWS ONLY`.
- SQL Server thường dùng `ORDER BY ... OFFSET 0 ROWS FETCH NEXT 10 ROWS ONLY`, hoặc cấu trúc query phù hợp với `TOP (10)`.

`TOP (10)` không thể đơn giản thêm vào **ngoài cùng** một câu UNION trong mọi hình thức T-SQL; nếu cần TOP trên toàn bộ kết quả, có thể bọc UNION trong CTE hoặc derived table rồi đặt SELECT TOP ở ngoài để mục đích rõ ràng. Tương tự, khi muốn mỗi nhánh có giới hạn riêng, cần xem quy tắc ngoặc và subquery của DBMS đích.

### 18.2. Tương thích kiểu không giống nhau giữa DBMS

PostgreSQL, SQL Server, Oracle, MySQL và SQLite có mức độ ép kiểu ngầm khác nhau. Một số phép UNION giữa kiểu văn bản và số có thể bị từ chối ở hệ này nhưng được suy diễn ở hệ khác. Nếu dữ liệu có **mã định danh, tiền, ngày và trạng thái**, việc CAST tường minh ở mỗi nhánh giúp tránh một số sai lệch, nhưng vẫn cần kiểm tra **khả năng chuyển đổi thật và mất thông tin**.

## 19. Rủi ro dữ liệu và bảo mật khi hợp nhất nhiều nguồn

Vì UNION làm dữ liệu từ các nguồn xuất hiện trong cùng một kết quả, ứng dụng phải giữ các quy tắc bảo mật và ngữ nghĩa nhất quán:

1. **Phạm vi truy cập:** mỗi nhánh phải lọc theo quyền truy cập/tenant cần thiết. `UNION ALL` của một nhánh có điều kiện phân quyền và một nhánh quên điều kiện có thể làm lộ dữ liệu.
2. **Định danh nguồn:** nên có `source_system`, `tenant_id` nếu cần và `source_record_id`, tránh nhầm ID trùng giữa hệ.
3. **Tiền tệ và đơn vị:** không cộng VND với USD hoặc đồng với xu nếu chưa có quy tắc chuyển đổi và thời điểm tỷ giá.
4. **Trạng thái nghiệp vụ:** PAID, COMPLETED, SETTLED, REFUNDED có thể không tương đương; chuẩn hóa trước khi tổng hợp KPI.
5. **Dữ liệu NULL hoặc thiếu cột:** điền NULL có kiểu, phân biệt không áp dụng với chưa biết và với giá trị bằng 0.
6. **Trùng lặp do đồng bộ:** nếu cùng một giao dịch được nạp từ hai pipeline, phải chọn chính sách dedup dựa trên **khóa gốc và phiên bản**, không trên toàn bộ cột tình cờ bằng nhau.

### 19.1. Mẫu phân quyền theo nhánh

```sql
-- Minh họa: giả định cả hai bảng đều có tenant_id.
SELECT
    'WEB' AS source_system,
    web_order_id AS source_order_id,
    tenant_id,
    amount
FROM web_orders
WHERE tenant_id = :authorized_tenant_id

UNION ALL

SELECT
    'STORE',
    store_order_id,
    tenant_id,
    amount
FROM store_orders
WHERE tenant_id = :authorized_tenant_id;
```

Các tên bảng và placeholder `:authorized_tenant_id` chỉ là **mẫu SQL minh họa**; cú pháp tham số thực tế phụ thuộc driver/ORM/DBMS. Điều kiện lọc theo tenant phải được thực thi phía server và kết hợp với cơ chế phân quyền thích hợp, không chỉ dựa vào client cung cấp tenant_id đúng.

**UNION không phải một cơ chế phân quyền.** Nó chỉ kết hợp dữ liệu của những truy vấn đã được viết. Cần đảm bảo từng nhánh lấy đúng những hàng mà người gọi được phép xem.

## 20. Những lỗi thường gặp khi dùng UNION và UNION ALL

| Ngộ nhận hoặc lỗi | Vì sao sai? | Cách xử lý |
| --- | --- | --- |
| `UNION` và `UNION ALL` cho cùng số hàng | UNION loại hàng trùng; ALL giữ mọi lần xuất hiện | Xác định có cần khử trùng thật sự không |
| UNION loại trùng theo PRIMARY KEY nguồn | UNION không tự đọc khóa; nó so sánh **toàn bộ cột kết quả** | Giữ khóa nguồn, hoặc xử lý dedup theo khóa nghiệp vụ |
| Hai đơn cùng amount/ngày là một đơn | Hai giao dịch độc lập có thể có thông tin hiển thị giống nhau | Giữ nguồn và định danh giao dịch |
| UNION luôn giữ một ID đơn ở hai hệ riêng biệt | ID có thể trùng giữa nguồn | Dùng khóa `(source, source_id)` |
| `UNION ALL` tự loại giao dịch sync bị nạp hai lần | ALL giữ mọi hàng và bội số | Dedup theo khóa gốc và quy tắc phiên bản |
| Hai nhánh có cùng **tên** cột là đủ | Ghép theo **vị trí**, số cột và kiểu phải tương thích | Liệt kê cột đúng thứ tự ở mọi nhánh |
| `SELECT *` luôn phù hợp khi hai bảng trông giống nhau | Schema đổi hoặc thứ tự khác có thể hỏng/sai | Chọn cột tường minh |
| UNION giữa DATE và NUMERIC chỉ cần CAST cả hai sang TEXT | Có thể làm mất ngữ nghĩa cột | Thiết kế schema đầu ra đúng ý nghĩa |
| Alias ở nhánh hai đặt lại tên cột cuối | Tên kết quả thường theo nhánh đầu | Đặt alias thống nhất từ SELECT đầu |
| UNION tự sắp hàng hoặc giữ nhánh A trước B | Không có cam kết thứ tự nếu thiếu ORDER BY cuối | ORDER BY rõ ràng với khóa phụ |
| `LIMIT 5` sau UNION lấy 5 mỗi nguồn | Nó lấy 5 cho kết quả cuối | Giới hạn từng nhánh trong subquery/ngoặc khi cần |
| UNION xử lý NULL giống WHERE `NULL = NULL` | Loại trùng của set operation có quy tắc NULL riêng | Kiểm tra bội số và NULL với ví dụ cụ thể |
| Dùng UNION cho KPI để “cho sạch” | Có thể làm mất giao dịch hợp lệ và giảm tổng tiền | Thường dùng UNION ALL cho sự kiện độc lập |
| UNION ALL phải chậm hơn do trả nhiều hàng | DISTINCT của UNION có thể tốn sort/hash; cần đo | Dùng đúng ngữ nghĩa, EXPLAIN khi tối ưu |
| Chỉ dùng UNION để sửa dữ liệu nhập trùng theo order_id | Cùng order_id nhưng status khác vẫn còn nhiều phiên bản | ROW_NUMBER/DISTINCT ON theo khóa và thứ tự |
| Chỉ một nhánh lọc tenant là đủ | Nhánh còn lại vẫn có thể lộ dữ liệu | Áp dụng phân quyền ở mọi nguồn |

## 21. Bài tập thực hành

Sử dụng hai bảng tạm `demo_web_orders` và `demo_store_orders` ở mục 2. Hãy **dự đoán số hàng và số tiền trước khi chạy**.

### Bài 1 — UNION ALL cơ bản

Viết một câu SQL ghép các đơn PAID của hai kênh, chỉ trả `order_date`, `amount`, `status` bằng `UNION ALL`. Sắp theo ngày tăng dần và amount tăng dần. Có bao nhiêu hàng? Những giá trị nào xuất hiện hai lần?

Gợi ý: **6 hàng**; cặp `(09-01, 120, PAID)` và `(09-02, 80, PAID)` xuất hiện hai lần.

### Bài 2 — Đổi thành UNION

Thay `UNION ALL` ở bài 1 bằng `UNION`. Có bao nhiêu hàng và tổng amount là bao nhiêu? Vì sao kết quả **4 hàng, 520.00** không phải số đơn/doanh thu thật của hai kênh?

### Bài 3 — Thêm cột customer_id

Truy vấn UNION ở bài 2 nay thêm `customer_id` vào cả hai nhánh. Hai cặp hàng nào vẫn giống nhau hay khác nhau? Vì sao số hàng tăng từ **4** lên **5**? Hãy giải thích dựa trên quy tắc loại trùng toàn bộ cột, không dựa trên khóa chính của bảng nguồn.

### Bài 4 — Khóa ID trùng giữa hai nguồn

WEB 101 và STORE 101 cùng số ID. Viết truy vấn ghép `order_id`, `order_date`, `amount`, `status` bằng UNION và dự đoán điều xảy ra với hai đơn 101. Sau đó bổ sung `source_system` bằng hai giá trị `'WEB'`, `'STORE'` để giữ được hai danh tính.

### Bài 5 — Lập schema kết quả chung

Hãy dùng `UNION ALL` tạo sáu cột sau theo đúng thứ tự:

```text
source_system, source_order_id, customer_id, order_date, amount, status
```

Viết đầy đủ alias ở nhánh đầu, tương ứng cột trong nhánh sau, sắp theo `order_date DESC`, rồi theo nguồn và ID. Vì sao không dùng `SELECT *`?

### Bài 6 — Sai thứ tự cột

Một lập trình viên viết nhánh WEB: `(web_order_id, customer_id)` nhưng nhánh STORE: `(customer_id, store_order_id)`. Tại sao truy vấn có thể chạy mà cột đầu ra mang dữ liệu sai ý nghĩa? Sửa lại đúng thứ tự và đưa ra một trường hợp lỗi có thể xảy ra ở tầng API nếu không sửa.

### Bài 7 — NULL và khử trùng

So sánh:

```sql
SELECT NULL::TEXT AS note
UNION
SELECT NULL::TEXT AS note;
```

với:

```sql
SELECT NULL::TEXT AS note
UNION ALL
SELECT NULL::TEXT AS note;
```

Số hàng khác nhau thế nào? Vì sao không thể giải thích hành vi UNION bằng cách nói đơn giản `NULL = NULL` trả TRUE?

### Bài 8 — LIMIT sau UNION so với LIMIT từng nhánh

Viết truy vấn lấy **3 đơn mới nhất toàn hệ thống**. Sau đó viết một truy vấn khác lấy **2 đơn mới nhất của mỗi kênh**, kết hợp kết quả và sắp xếp chung. Vì sao đây là hai yêu cầu khác nhau? Những khóa ORDER BY nào cần thêm để tránh đổi thứ tự khi có ngày trùng?

### Bài 9 — COUNT, SUM sau UNION ALL

Tạo CTE hợp nhất toàn bộ hai bảng bằng UNION ALL rồi trả `all_orders`, `paid_orders`, `paid_amount`. Kết quả phải là **8, 6, 720.00**. Viết thêm báo cáo GROUP BY `source_system` để đối chiếu WEB = **4/3/320** và STORE = **4/3/400**.

### Bài 10 — Dữ liệu trùng thật do đồng bộ

Một đơn được nạp từ hai feed với cùng `(source_system, source_order_id)` nhưng `updated_at` và `status` khác nhau. Nếu chỉ muốn phiên bản mới nhất, vì sao cả UNION và UNION ALL đều không tự giải quyết bài toán? Thiết kế `UNION ALL` trước, sau đó `ROW_NUMBER() OVER (PARTITION BY ... ORDER BY updated_at DESC, ingestion_id DESC)` và lọc `rn=1`.

### Bài 11 — Hợp nhất số liệu đã GROUP BY

Giả sử hai nhánh đã tính `paid_count`, `paid_amount`. Viết `UNION ALL` hai hàng tổng theo nguồn, rồi SELECT ngoài SUM các cột ấy. Điều gì xảy ra nếu hai nguồn có số liệu giống hệt nhau và bạn đổi thành UNION nhưng **không mang source_system**?

### Bài 12 — Chuyển phương ngữ

Hãy viết câu UNION ALL trên một schema đơn hàng tương đương trong PostgreSQL, SQL Server và Oracle. So sánh cách CAST nhãn nguồn, kiểu số và cách lấy tối đa 10 hàng sau ORDER BY. Tại sao không thể chép nguyên `LIMIT 10` của PostgreSQL sang SQL Server?

### Bài 13 — Bài toán phân quyền

Một API dùng UNION ALL của `tenant_web_orders` và `tenant_store_orders` nhưng chỉ nhánh WEB có điều kiện `WHERE tenant_id = ?`. Điều gì có thể xảy ra? Viết lại thành truy vấn áp dụng điều kiện tenant cho **cả hai nhánh**, với tham số do backend xác định theo quyền của người dùng.

### Bài 14 — Phân biệt UNION và JOIN

Muốn ghép `order_id` từ đơn hàng với `customer_name` từ bảng khách, công cụ nào phù hợp? Muốn gộp danh sách đơn từ hai bảng cùng cấu trúc, công cụ nào phù hợp? Nếu JOIN một đơn với ba dòng sản phẩm, bội số có gì khác so với UNION ALL ba sự kiện riêng biệt?

## 22. Tổng kết: hợp nhất đúng nghĩa trước khi tối ưu

```text
Nguồn A                  Nguồn B
    |                        |
    +-- Chuẩn hóa schema ----+
            |
            v
   Cùng số cột, cùng thứ tự,
   cùng ý nghĩa và kiểu phù hợp
            |
            v
  Mục tiêu có cần giữ mọi bản ghi?
            |
            +---- CÓ ----> UNION ALL
            |              |
            |              +-- Giữ source + source_id
            |              +-- GROUP BY/SUM/COUNT đúng grain
            |
            +---- KHÔNG --> Xác định rõ khái niệm "trùng"
                           |
                           +-- Trùng toàn bộ cột kết quả?
                           |        -> UNION
                           |
                           +-- Trùng theo khóa, nhiều phiên bản?
                                    -> UNION ALL rồi
                                       ROW_NUMBER/logic dedup
            |
            v
    ORDER BY/LIMIT ở đúng cấp,
    phân quyền từng nhánh và
    đo kế hoạch khi cần tối ưu
```

**`UNION ALL` bảo toàn mọi hàng; `UNION` khử trùng dựa trên toàn bộ các cột đầu ra.** Hai toán tử không tự biết một hàng có phải là giao dịch thật hay bản sao lỗi. Nếu bài toán là hợp nhất sự kiện hoặc giao dịch độc lập từ nhiều nguồn, `UNION ALL` kết hợp với **định danh nguồn** thường là điểm xuất phát rõ ràng. Nếu bài toán là lấy tập giá trị duy nhất, `UNION` có thể phù hợp; nếu muốn một phiên bản theo khóa nghiệp vụ, cần một bước chọn bản ghi có quy tắc riêng.

Khi xây dựng câu SQL, hãy **đồng nhất số cột, vị trí, kiểu và ý nghĩa của từng nhánh**, không dựa vào `SELECT *` hay thứ tự ngầm, và phân biệt hợp nhất hàng với JOIN. Trước khi dùng kết quả để đếm hoặc cộng tiền, xác định một hàng là **một giao dịch, một khách, một phiên bản hay chỉ một tổ hợp giá trị**. Chỉ khi bội số và ý nghĩa dữ liệu đúng, việc tối ưu UNION hay UNION ALL mới tạo ra kết quả đáng tin cậy.
