# INNER JOIN theo khóa đơn, khóa ghép và điều kiện nhiều cột

Một hệ thống bán hàng thường lưu khách hàng, đơn hàng, sản phẩm và chi tiết đơn hàng trong các bảng riêng. Khi lập báo cáo, ứng dụng cần ghép thông tin khách hàng với đơn hàng, ghép từng dòng đơn hàng với sản phẩm, hoặc kiểm tra tồn kho của đúng sản phẩm tại đúng kho. Những thao tác này là công việc cốt lõi của `JOIN` trong MySQL.

`INNER JOIN` trả về các cặp hàng thỏa điều kiện nối. Điều kiện có thể dựa trên một khóa đơn, nhiều cột của khóa ghép hoặc nhiều điều kiện kết hợp bằng `AND`. Viết đúng toàn bộ điều kiện nối giúp kết quả phản ánh đúng quan hệ dữ liệu, tránh nhân bản hàng ngoài ý muốn và cho phép MySQL chọn index phù hợp.

## 1. INNER JOIN hoạt động như thế nào?

`INNER JOIN` kết hợp hàng từ hai bảng khi biểu thức `ON` đánh giá là `TRUE`. Nếu không có hàng tương ứng ở phía còn lại, hàng đó không xuất hiện trong kết quả.

Cú pháp cơ bản:

```sql
SELECT select_list
FROM table_a AS a
INNER JOIN table_b AS b
    ON join_condition;
```

`INNER` có thể được lược bỏ trong cú pháp `JOIN` thông thường:

```sql
SELECT select_list
FROM table_a AS a
JOIN table_b AS b
    ON join_condition;
```

Hai cách viết có cùng ý nghĩa. Nên dùng alias ngắn, nhất quán và luôn ghi rõ điều kiện nối để người đọc nhận ra cột thuộc bảng nào.

Ví dụ đơn giản: mỗi đơn hàng tham chiếu một khách hàng qua `orders.customer_id`:

```sql
SELECT
    o.id AS order_id,
    o.created_at,
    c.id AS customer_id,
    c.full_name
FROM orders AS o
INNER JOIN customers AS c
    ON c.id = o.customer_id;
```

MySQL ghép một hàng `orders` với hàng `customers` có `id` bằng `customer_id`. Đơn hàng có `customer_id` không khớp với khách hàng nào sẽ không xuất hiện trong kết quả INNER JOIN.

### 1.1. Điều kiện ON phải xác định quan hệ

Điều kiện `ON` mô tả cách hàng của hai bảng tương ứng với nhau. Thường đó là quan hệ giữa khóa ngoại ở bảng con và khóa chính hoặc unique key ở bảng cha:

```sql
ON orders.customer_id = customers.id
```

Không nối bảng chỉ vì hai cột có tên giống nhau. `customer_id`, `created_by` và `approved_by` có thể cùng là số nguyên nhưng mang ý nghĩa khác nhau. Hãy chọn đúng quan hệ nghiệp vụ.

### 1.2. INNER JOIN không bảo đảm mỗi hàng chỉ xuất hiện một lần

Một hàng bên trái có thể khớp với nhiều hàng bên phải. Khi đó kết quả chứa một hàng cho mỗi cặp khớp. Ví dụ một khách hàng có năm đơn hàng sẽ xuất hiện năm lần nếu truy vấn nối khách hàng với đơn hàng.

Đây là hành vi đúng của JOIN, không phải lỗi nhân bản của MySQL. Muốn một hàng cho mỗi khách hàng, cần xác định mục tiêu như tổng hợp đơn hàng, chọn đơn mới nhất hoặc kiểm tra tồn tại; không tùy tiện thêm `DISTINCT` để che việc nối sai.

## 2. Dựng bộ dữ liệu minh họa

Các ví dụ sau dùng mô hình rút gọn của một cửa hàng. Mỗi bảng có khóa rõ ràng và kiểu dữ liệu của các cột liên kết tương thích.

```sql
CREATE TABLE customers (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    full_name VARCHAR(150) NOT NULL,
    PRIMARY KEY (id)
) ENGINE=InnoDB;

CREATE TABLE products (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    sku VARCHAR(40) NOT NULL,
    product_name VARCHAR(160) NOT NULL,
    PRIMARY KEY (id),
    UNIQUE KEY uq_products_sku (sku)
) ENGINE=InnoDB;

CREATE TABLE orders (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    customer_id BIGINT UNSIGNED NOT NULL,
    status VARCHAR(20) NOT NULL,
    created_at DATETIME NOT NULL,
    PRIMARY KEY (id),
    KEY idx_orders_customer_created (customer_id, created_at),
    CONSTRAINT fk_orders_customer
        FOREIGN KEY (customer_id) REFERENCES customers (id)
) ENGINE=InnoDB;

CREATE TABLE order_items (
    order_id BIGINT UNSIGNED NOT NULL,
    line_no INT UNSIGNED NOT NULL,
    product_id BIGINT UNSIGNED NOT NULL,
    warehouse_id BIGINT UNSIGNED NOT NULL,
    quantity INT UNSIGNED NOT NULL,
    unit_price DECIMAL(12,2) NOT NULL,
    created_at DATETIME NOT NULL,
    PRIMARY KEY (order_id, line_no),
    KEY idx_items_product (product_id),
    KEY idx_items_warehouse_product (warehouse_id, product_id),
    CONSTRAINT fk_items_order
        FOREIGN KEY (order_id) REFERENCES orders (id),
    CONSTRAINT fk_items_product
        FOREIGN KEY (product_id) REFERENCES products (id)
) ENGINE=InnoDB;

CREATE TABLE shipments (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    order_id BIGINT UNSIGNED NOT NULL,
    line_no INT UNSIGNED NOT NULL,
    shipped_quantity INT UNSIGNED NOT NULL,
    PRIMARY KEY (id),
    KEY idx_shipments_order_line (order_id, line_no),
    CONSTRAINT fk_shipments_item
        FOREIGN KEY (order_id, line_no)
        REFERENCES order_items (order_id, line_no)
) ENGINE=InnoDB;

CREATE TABLE warehouse_stock (
    warehouse_id BIGINT UNSIGNED NOT NULL,
    product_id BIGINT UNSIGNED NOT NULL,
    available_quantity INT UNSIGNED NOT NULL,
    PRIMARY KEY (warehouse_id, product_id),
    CONSTRAINT fk_stock_product
        FOREIGN KEY (product_id) REFERENCES products (id)
) ENGINE=InnoDB;

CREATE TABLE product_prices (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    product_id BIGINT UNSIGNED NOT NULL,
    region_code CHAR(2) NOT NULL,
    valid_from DATETIME NOT NULL,
    valid_to DATETIME NOT NULL,
    unit_price DECIMAL(12,2) NOT NULL,
    PRIMARY KEY (id),
    KEY idx_price_product_region_start
        (product_id, region_code, valid_from),
    CONSTRAINT fk_prices_product
        FOREIGN KEY (product_id) REFERENCES products (id)
) ENGINE=InnoDB;
```

Điểm cần chú ý:

- `orders.customer_id` tham chiếu một cột `customers.id`.
- `order_items` được định danh bằng khóa ghép `(order_id, line_no)`.
- `shipments` tham chiếu đồng thời cả hai cột của khóa ghép đó.
- `warehouse_stock` dùng khóa chính ghép `(warehouse_id, product_id)` vì mỗi sản phẩm có một số lượng tồn riêng tại từng kho.

Các ví dụ giả định bảng đã có dữ liệu hợp lệ. Khi chạy thực hành, hãy nạp dữ liệu cha trước dữ liệu con để foreign key được kiểm tra bình thường.

## 3. INNER JOIN theo khóa đơn

Khóa đơn là khóa chỉ gồm một cột. Ví dụ `customers.id` là primary key và `orders.customer_id` là foreign key tham chiếu đến nó.

```sql
SELECT
    o.id AS order_id,
    c.full_name AS customer_name,
    o.status,
    o.created_at
FROM orders AS o
INNER JOIN customers AS c
    ON c.id = o.customer_id
ORDER BY o.created_at DESC, o.id DESC;
```

Điều kiện nối dùng một cặp cột tương ứng. `c.id` là duy nhất nên mỗi đơn hàng khớp tối đa một khách hàng. Tuy nhiên, một khách hàng vẫn có thể khớp với nhiều đơn hàng khi truy vấn đi theo chiều ngược lại.

### 3.1. Nối nhiều bảng theo chuỗi quan hệ

Có thể nối đơn hàng với khách hàng và chi tiết đơn hàng:

```sql
SELECT
    o.id AS order_id,
    c.full_name,
    oi.line_no,
    p.sku,
    p.product_name,
    oi.quantity,
    oi.unit_price
FROM orders AS o
INNER JOIN customers AS c
    ON c.id = o.customer_id
INNER JOIN order_items AS oi
    ON oi.order_id = o.id
INNER JOIN products AS p
    ON p.id = oi.product_id
WHERE o.status = 'PAID'
ORDER BY o.id, oi.line_no;
```

Mỗi dòng kết quả tương ứng một dòng chi tiết của một đơn hàng đã thanh toán. Tên khách hàng và thông tin sản phẩm được lặp lại trên các dòng chi tiết thuộc cùng đơn; đó là hệ quả tự nhiên của quan hệ một-nhiều.

### 3.2. Dùng alias để tránh tên cột mơ hồ

Khi nhiều bảng cùng có cột `id`, `created_at` hoặc `status`, hãy ghi rõ alias:

```sql
SELECT
    o.id AS order_id,
    c.id AS customer_id,
    o.status AS order_status
FROM orders AS o
JOIN customers AS c
    ON c.id = o.customer_id;
```

Viết `SELECT id` trong truy vấn nhiều bảng có thể gây lỗi cột không rõ nguồn. Dùng `o.id` hoặc `c.id` làm rõ ý định và giúp code ít bị lỗi khi schema thay đổi.

## 4. INNER JOIN theo khóa ghép

Khóa ghép (composite key) gồm từ hai cột trở lên. Giá trị của từng cột riêng lẻ có thể lặp lại, nhưng tổ hợp tất cả cột tạo nên khóa mới là duy nhất.

Trong `order_items`, primary key là `(order_id, line_no)`. Một đơn hàng có thể có dòng `line_no = 1`, và nhiều đơn hàng khác cũng có dòng số 1. Vì vậy, chỉ nối theo `line_no` là sai.

### 4.1. Nối đủ các cột của khóa ghép

`shipments` tham chiếu `order_items` qua cả `order_id` và `line_no`:

```sql
SELECT
    s.id AS shipment_id,
    s.order_id,
    s.line_no,
    oi.product_id,
    oi.quantity AS ordered_quantity,
    s.shipped_quantity
FROM shipments AS s
INNER JOIN order_items AS oi
    ON oi.order_id = s.order_id
   AND oi.line_no = s.line_no;
```

Điều kiện nối phải có cả hai cặp cột. Chỉ khi `order_id` và `line_no` cùng khớp, hàng shipment mới thuộc đúng dòng chi tiết.

### 4.2. Sai lầm: chỉ nối một phần khóa ghép

Truy vấn sau thiếu `order_id`:

```sql
-- SAI: line_no không duy nhất trên toàn bộ order_items.
SELECT
    s.id AS shipment_id,
    s.order_id,
    s.line_no,
    oi.order_id AS matched_order_id,
    oi.product_id
FROM shipments AS s
INNER JOIN order_items AS oi
    ON oi.line_no = s.line_no;
```

Nếu nhiều đơn hàng đều có dòng số `1`, một shipment của đơn hàng A có thể ghép với dòng số `1` của đơn hàng B, C và nhiều đơn khác. Kết quả bị nhân bản và có thể gán nhầm sản phẩm, số lượng hoặc doanh thu.

Không sửa lỗi này bằng `DISTINCT`. `DISTINCT` chỉ loại các hàng có toàn bộ cột hiển thị giống nhau; nó không khôi phục được quan hệ đúng nếu các cột ghép đã bị chọn sai. Cần sửa điều kiện `ON` để bao gồm toàn bộ khóa.

### 4.3. Khóa ghép có thứ tự cột

Khóa chính:

```sql
PRIMARY KEY (order_id, line_no)
```

định danh tổ hợp có thứ tự `(order_id, line_no)`. Trong điều kiện bằng, viết rõ từng cặp:

```sql
ON oi.order_id = s.order_id
AND oi.line_no = s.line_no
```

MySQL cũng hỗ trợ so sánh row constructor trong nhiều ngữ cảnh:

```sql
ON (oi.order_id, oi.line_no) = (s.order_id, s.line_no)
```

Tuy nhiên, cách viết từng cặp bằng `AND` thường dễ đọc, dễ mở rộng và thuận tiện hơn khi cần thêm điều kiện. Với truy vấn quan trọng, hãy kiểm tra `EXPLAIN` để xác nhận optimizer sử dụng index ghép như mong muốn.

## 5. INNER JOIN với điều kiện nhiều cột

Không phải mọi điều kiện nối nhiều cột đều là khóa ghép. Có thể nối theo một khóa, sau đó thêm điều kiện về trạng thái, thời gian, số lượng hoặc phạm vi dữ liệu.

Ví dụ kiểm tra sản phẩm được yêu cầu có đủ tồn kho ở đúng kho:

```sql
SELECT
    oi.order_id,
    oi.line_no,
    oi.product_id,
    oi.warehouse_id,
    oi.quantity AS requested_quantity,
    ws.available_quantity
FROM order_items AS oi
INNER JOIN warehouse_stock AS ws
    ON ws.warehouse_id = oi.warehouse_id
   AND ws.product_id = oi.product_id
   AND ws.available_quantity >= oi.quantity;
```

Ở đây có ba điều kiện:

1. `warehouse_id` phải khớp để chọn đúng kho.
2. `product_id` phải khớp để chọn đúng sản phẩm.
3. `available_quantity >= quantity` để chỉ lấy các dòng có đủ số lượng theo trạng thái tồn kho đang đọc.

Hai điều kiện đầu là khóa ghép của `warehouse_stock`. Điều kiện thứ ba là điều kiện nghiệp vụ bổ sung, không phải một phần của khóa. Tách rõ hai loại điều kiện giúp người đọc hiểu quan hệ dữ liệu và quy tắc lọc.

Lưu ý: truy vấn trên chỉ kiểm tra số lượng hiện tại. Nó không khóa hàng tồn kho và không tự bảo đảm hai giao dịch đồng thời không cùng bán vượt tồn. Nghiệp vụ trừ tồn cần transaction, khóa phù hợp hoặc câu lệnh cập nhật có điều kiện và kiểm tra số hàng bị ảnh hưởng.

### 5.1. Nối theo khóa và lọc thuộc tính

Ví dụ chỉ lấy đơn hàng đã thanh toán, được tạo trong khoảng thời gian và thuộc khách hàng cụ thể:

```sql
SELECT
    o.id,
    c.full_name,
    o.created_at,
    o.status
FROM orders AS o
INNER JOIN customers AS c
    ON c.id = o.customer_id
WHERE o.status = 'PAID'
  AND o.created_at >= '2026-01-01 00:00:00'
  AND o.created_at <  '2027-01-01 00:00:00'
  AND c.id = 120;
```

`ON` mô tả quan hệ nối giữa hai bảng; `WHERE` lọc các hàng của kết quả. Với `INNER JOIN`, điều kiện lọc thuần túy có thể cho kết quả tương đương nếu đặt trong `ON` hoặc `WHERE`, nhưng nên đặt điều kiện nối khóa ở `ON` và bộ lọc kết quả ở `WHERE` để ý định rõ ràng.

### 5.2. Nhiều điều kiện bằng và điều kiện phạm vi

Một truy vấn có thể kết hợp điều kiện bằng với điều kiện phạm vi:

```sql
SELECT
    oi.order_id,
    oi.line_no,
    p.product_name,
    oi.unit_price,
    pr.valid_from,
    pr.valid_to
FROM order_items AS oi
INNER JOIN products AS p
    ON p.id = oi.product_id
INNER JOIN product_prices AS pr
    ON pr.product_id = oi.product_id
   AND pr.region_code = 'VN'
   AND oi.created_at >= pr.valid_from
   AND oi.created_at <  pr.valid_to;
```

Ví dụ này giả định bảng `order_items` có `created_at` và bảng `product_prices` có khoảng hiệu lực không chồng lấn. Hai điều kiện đầu nối theo sản phẩm và vùng; hai điều kiện cuối tìm bản ghi giá có hiệu lực tại thời điểm đơn hàng. Nếu các khoảng thời gian bị chồng lấn, một dòng đơn hàng có thể khớp nhiều bản ghi giá và kết quả bị nhân bản. Cần có quy tắc dữ liệu hoặc quy trình kiểm tra để bảo đảm mỗi thời điểm chỉ khớp một mức giá.

### 5.3. Điều kiện OR và biểu thức phức tạp

Có thể viết điều kiện nhiều nhánh:

```sql
SELECT ...
FROM a
JOIN b
  ON (b.code = a.primary_code OR b.code = a.alternate_code);
```

Tuy nhiên, điều kiện `OR` trên nhiều cột có thể làm optimizer khó tận dụng một index đơn giản. Nếu truy vấn quan trọng, so sánh kế hoạch thực thi với cách viết tách nhánh bằng `UNION`/`UNION ALL` phù hợp. Chỉ dùng cách tách khi có thể giữ đúng ngữ nghĩa trùng lặp; `UNION` loại trùng còn `UNION ALL` giữ tất cả hàng.

## 6. NULL trong điều kiện JOIN

Phép so sánh bằng `=` với `NULL` không trả `TRUE`; nó trả `UNKNOWN`. Vì vậy, hai hàng có giá trị khóa nối `NULL` không khớp nhau bằng điều kiện `a.col = b.col`.

Ví dụ:

```sql
SELECT
    a.id,
    b.id
FROM table_a AS a
INNER JOIN table_b AS b
    ON b.external_code = a.external_code;
```

Nếu `a.external_code` hoặc `b.external_code` là `NULL`, cặp hàng đó không thỏa điều kiện bằng. Đây thường là hành vi đúng với khóa ngoại tùy chọn: không có giá trị tham chiếu thì không có hàng cha để nối.

Nếu nghiệp vụ thực sự coi hai giá trị `NULL` là tương đương, MySQL hỗ trợ toán tử null-safe equality `<=>`:

```sql
SELECT a.id, b.id
FROM table_a AS a
INNER JOIN table_b AS b
    ON a.external_code <=> b.external_code;
```

Với `<=>`, `NULL <=> NULL` là `TRUE`. Cần dùng có chủ đích vì nhiều hàng có `NULL` ở hai bảng có thể ghép chéo với nhau và tạo fan-out lớn. Không dùng `<=>` để che dữ liệu thiếu khóa hoặc thay thế quy tắc foreign key.

Đối với khóa ghép, nếu một thành phần `NULL`, điều kiện nối bằng `=` trên thành phần đó không thể là `TRUE`; cả tổ hợp không khớp. Nếu cần so sánh null-safe cho từng thành phần, viết rõ từng cặp `<=>` và xác nhận nghiệp vụ chấp nhận việc NULL khớp NULL.

## 7. INNER JOIN với USING và những cách viết nên thận trọng

Khi hai bảng có cột cùng tên và cần nối bằng các cột đó, MySQL hỗ trợ `USING`:

```sql
SELECT order_id, line_no, shipped_quantity
FROM shipments
INNER JOIN order_items
USING (order_id, line_no);
```

`USING (order_id, line_no)` tương đương điều kiện bằng trên cả hai cột cùng tên. Trong danh sách cột kết quả, các cột dùng chung được trình bày như một cột chung thay vì hai cột riêng biệt.

Chỉ dùng `USING` khi tên cột giống nhau và ý nghĩa thực sự tương ứng. Nếu tên cột khác nhau, cần thêm biểu thức hoặc muốn thể hiện rõ từng phía, dùng `ON`.

Tránh `NATURAL JOIN` trong schema nghiệp vụ. Nó tự nối theo tất cả cột cùng tên ở hai bảng; khi một migration thêm cột trùng tên, quan hệ nối có thể thay đổi mà câu SQL không đổi. Điều này khó phát hiện và dễ làm sai kết quả.

## 8. Nhiều-nhiều và hiện tượng fan-out

Một khách hàng có nhiều đơn hàng, một đơn hàng có nhiều dòng chi tiết và một sản phẩm có thể xuất hiện trong nhiều đơn. Khi nối các bảng một-nhiều liên tiếp, số hàng kết quả tăng theo số quan hệ.

Ví dụ:

```sql
SELECT
    c.id AS customer_id,
    c.full_name,
    o.id AS order_id,
    oi.line_no,
    p.product_name
FROM customers AS c
JOIN orders AS o
    ON o.customer_id = c.id
JOIN order_items AS oi
    ON oi.order_id = o.id
JOIN products AS p
    ON p.id = oi.product_id;
```

Một khách hàng có 3 đơn, mỗi đơn có 4 dòng sẽ tạo tối đa 12 hàng kết quả cho khách hàng đó. Nếu nối thêm bảng shipment có nhiều lần giao cho mỗi dòng đơn hàng, kết quả còn có thể tăng thêm.

Khi tính tổng tiền đơn hàng sau khi nối với bảng shipment, cần kiểm tra mức chi tiết (grain) của kết quả. Nếu một dòng order item có ba shipment, `oi.quantity * oi.unit_price` có thể bị lặp ba lần trong phép `SUM`.

Các cách xử lý tùy mục tiêu:

- Tổng hợp shipment về một hàng cho mỗi `(order_id, line_no)` trước khi nối.
- Tính tổng tiền order item ở cấp dòng đơn hàng trước khi nối bảng chi tiết giao hàng.
- Dùng `EXISTS` nếu chỉ cần biết có shipment hay không, không cần lấy từng hàng shipment.
- Xác định rõ khóa duy nhất của tập kết quả và không dùng `DISTINCT` để che join thiếu điều kiện.

## 9. Index cho INNER JOIN theo nhiều cột

### 9.1. Index trên khóa đơn

Với join:

```sql
ON c.id = o.customer_id
```

`customers.id` là primary key nên đã có index. Bảng `orders` cũng nên có index bắt đầu bằng `customer_id` để tìm các đơn theo khách hàng:

```sql
CREATE INDEX idx_orders_customer_created
ON orders (customer_id, created_at);
```

Index này có thể hỗ trợ điều kiện theo `customer_id`, và có thể hỗ trợ thứ tự/lọc tiếp theo trên `created_at` khi truy vấn phù hợp với leftmost prefix.

### 9.2. Index ghép và quy tắc leftmost prefix

Với khóa ghép `(order_id, line_no)`, primary key của `order_items` tạo index theo thứ tự đó. Index có thể hỗ trợ tra cứu theo:

- `order_id`.
- Cả `order_id` và `line_no`.

Index này không được tổ chức để tra cứu trực tiếp chỉ theo `line_no` như một tiền tố độc lập. Nếu truy vấn thường xuyên tìm theo `line_no` riêng, cần xem xét index khác và đo chi phí/lợi ích.

Thứ tự cột trong index ghép quan trọng. Ví dụ:

```sql
KEY idx_warehouse_product (warehouse_id, product_id)
```

phù hợp với điều kiện nối có `warehouse_id` và `product_id`, đồng thời có thể hỗ trợ tra cứu theo `warehouse_id` ở tiền tố. Nó không phải index tối ưu cho truy vấn chỉ lọc `product_id`.

### 9.3. Kiểu dữ liệu và collation phải tương thích

Hai cột nối nên có kiểu dữ liệu tương thích để tránh chuyển đổi không cần thiết. Với số nguyên, kiểm tra `INT`/`BIGINT` và `SIGNED`/`UNSIGNED`; với chuỗi, kiểm tra character set và collation. Chuyển đổi ngầm có thể làm so sánh phức tạp hơn và khiến index không được sử dụng hiệu quả.

Ví dụ, không nên nối một cột `BIGINT UNSIGNED` với cột chuỗi chứa số rồi dựa vào ép kiểu ngầm. Hãy chuẩn hóa schema và kiểu dữ liệu ở cả hai phía.

### 9.4. Index không phải lúc nào cũng được chọn

Optimizer chọn kế hoạch dựa trên chi phí ước lượng, số hàng, độ chọn lọc, thống kê và kích thước dữ liệu. Với bảng nhỏ hoặc điều kiện trả về phần lớn hàng, quét bảng có thể rẻ hơn dùng index. Hãy kiểm tra `EXPLAIN` thay vì kết luận chỉ dựa trên việc đã tạo index.

## 10. Đọc kế hoạch thực thi JOIN

Ví dụ:

```sql
EXPLAIN
SELECT
    o.id,
    c.full_name,
    o.created_at
FROM orders AS o
INNER JOIN customers AS c
    ON c.id = o.customer_id
WHERE o.customer_id = 120
  AND o.created_at >= '2026-01-01 00:00:00';
```

Các cột trong `EXPLAIN` dạng truyền thống cần chú ý:

| Cột | Ý nghĩa khi phân tích JOIN |
|---|---|
| `table` | Bảng được truy cập ở bước đó |
| `type` | Kiểu truy cập như `const`, `eq_ref`, `ref`, `range`, `index`, `ALL` |
| `possible_keys` | Các index optimizer xem là ứng viên |
| `key` | Index thực tế được chọn, nếu có |
| `key_len` | Độ dài phần index được sử dụng |
| `ref` | Giá trị/cột được dùng để tra cứu index |
| `rows` | Số hàng ước lượng cần đọc |
| `filtered` | Tỷ lệ phần trăm hàng ước lượng còn lại sau điều kiện lọc |
| `Extra` | Thông tin bổ sung như `Using where`, `Using index`, `Using temporary` |

Với join theo khóa duy nhất, `eq_ref` có thể xuất hiện khi mỗi tổ hợp hàng từ các bảng trước chỉ tìm được tối đa một hàng ở bảng hiện tại qua primary/unique index. `ref` thường xuất hiện khi tra cứu theo index không unique. `ALL` cho biết full table scan; điều đó không tự động có nghĩa kế hoạch sai nếu bảng nhỏ hoặc truy vấn cần phần lớn dữ liệu.

MySQL 8.0 hỗ trợ dạng cây dễ đọc hơn:

```sql
EXPLAIN FORMAT=TREE
SELECT ...;
```

Từ MySQL 8.0.18, `EXPLAIN ANALYZE` thực thi câu SELECT và trả thời gian/số hàng thực tế của iterator:

```sql
EXPLAIN ANALYZE
SELECT
    o.id,
    c.full_name
FROM orders AS o
JOIN customers AS c
    ON c.id = o.customer_id
WHERE o.customer_id = 120;
```

`EXPLAIN ANALYZE` thực sự chạy câu truy vấn. Chỉ dùng với truy vấn đọc có thể thực thi an toàn và dữ liệu phù hợp; không coi nó là lệnh chỉ đọc metadata. So sánh actual rows với estimates để phát hiện thống kê sai hoặc giả định về độ chọn lọc không đúng.

## 11. Thứ tự JOIN và optimizer

Trong câu SQL, người viết đặt bảng theo một thứ tự, nhưng MySQL có thể chọn thứ tự truy cập khác cho INNER JOIN dựa trên chi phí. Vì INNER JOIN có tính chất kết hợp trong điều kiện thông thường, optimizer có thể sắp xếp lại các phép nối để giảm số hàng trung gian.

Không cần cố viết bảng nhỏ nhất đầu tiên để ép kế hoạch. Hãy viết quan hệ rõ ràng, tạo index hợp lý, cập nhật thống kê khi cần và đọc kế hoạch thực thi. Nếu cần kiểm soát join order trong trường hợp đặc biệt, MySQL có optimizer hints và các tùy chọn liên quan, nhưng chỉ dùng sau khi đã đo và xác định lý do cụ thể.

Điều kiện nối thiếu hoặc quá rộng làm số hàng trung gian tăng mạnh. Ví dụ nối `orders` với `order_items` mà thiếu `oi.order_id = o.id` có thể tạo tích Descartes hoặc fan-out gần như toàn bộ bảng. Luôn kiểm tra số hàng ước lượng và actual rows ở từng bước khi truy vấn chậm.

## 12. ON và WHERE trong INNER JOIN

Với INNER JOIN, điều kiện nối và điều kiện lọc có thể được optimizer xử lý tương đương về kết quả nếu được kết hợp đúng logic. Dù vậy, nên phân chia rõ:

```sql
SELECT ...
FROM orders AS o
JOIN customers AS c
    ON c.id = o.customer_id
WHERE o.status = 'PAID';
```

- `ON`: quan hệ giữa `orders` và `customers`.
- `WHERE`: chỉ giữ đơn hàng đã thanh toán.

Đừng áp dụng kết luận này một cách máy móc cho `LEFT JOIN` hoặc `RIGHT JOIN`. Với outer join, chuyển điều kiện từ `ON` sang `WHERE` có thể loại các hàng không khớp và làm thay đổi kết quả. Bài học này tập trung vào INNER JOIN, nhưng cần nhớ khác biệt để tránh mang thói quen sai sang outer join.

## 13. Dùng INNER JOIN hay EXISTS?

Nếu cần lấy cột của bảng bên phải, dùng JOIN. Nếu chỉ cần kiểm tra có ít nhất một hàng liên quan, `EXISTS` thường diễn đạt đúng mục tiêu hơn và không nhân bản hàng bên trái.

Ví dụ lấy khách hàng có ít nhất một đơn hàng đã thanh toán:

```sql
SELECT
    c.id,
    c.full_name
FROM customers AS c
WHERE EXISTS (
    SELECT 1
    FROM orders AS o
    WHERE o.customer_id = c.id
      AND o.status = 'PAID'
);
```

Nếu viết INNER JOIN trực tiếp:

```sql
SELECT
    c.id,
    c.full_name
FROM customers AS c
JOIN orders AS o
    ON o.customer_id = c.id
WHERE o.status = 'PAID';
```

khách hàng có nhiều đơn đã thanh toán sẽ xuất hiện nhiều lần. Có thể thêm `DISTINCT`, nhưng `EXISTS` mô tả chính xác ý định kiểm tra tồn tại và tránh fan-out không cần thiết.

## 14. Quy trình thiết kế và kiểm tra INNER JOIN

Khi viết truy vấn nối nhiều bảng, làm theo trình tự:

1. **Xác định grain của kết quả:** một hàng đại diện cho khách hàng, đơn hàng, dòng đơn hàng hay shipment?
2. **Xác định quan hệ:** bảng nào là cha, bảng nào là con; cột nào là PK, UNIQUE hoặc FK?
3. **Liệt kê toàn bộ cột khóa:** nếu khóa ghép có hai hoặc nhiều cột, không bỏ sót thành phần.
4. **Kiểm tra kiểu dữ liệu:** kích thước, signedness, charset và collation phải tương thích.
5. **Viết JOIN rõ ràng:** dùng alias và `ON` với từng cặp cột; đặt điều kiện nghiệp vụ bổ sung có chủ đích.
6. **Kiểm tra NULL và cardinality:** xác định cột nullable, quan hệ một-một, một-nhiều hay nhiều-nhiều.
7. **Đối chiếu kết quả:** kiểm tra một số khóa cụ thể bằng truy vấn độc lập hoặc dữ liệu mẫu đã biết.
8. **Đọc EXPLAIN:** xem index, join order, rows estimate và điều kiện lọc.
9. **Đo khi cần:** dùng `EXPLAIN ANALYZE` trên truy vấn đọc an toàn và dữ liệu đại diện.
10. **Kiểm tra nghiệp vụ:** bảo đảm tổng tiền, số lượng và số hàng không bị nhân do fan-out.

## 15. Các lỗi thường gặp

| Lỗi | Hậu quả | Cách khắc phục |
|---|---|---|
| Nối khóa ghép bằng một cột | Khớp nhầm hàng và nhân bản kết quả | Đưa tất cả thành phần khóa vào `ON` |
| Bỏ điều kiện nối giữa hai bảng | Tạo tích Descartes hoặc fan-out rất lớn | Kiểm tra từng cặp khóa và `EXPLAIN` |
| Dùng cột cùng tên nhưng sai ý nghĩa | Ghép nhầm quan hệ nghiệp vụ | Xác định PK/FK và ngữ nghĩa cột trước khi nối |
| Dùng `DISTINCT` để che join sai | Che triệu chứng nhưng không sửa quan hệ | Sửa điều kiện nối hoặc thay bằng EXISTS/aggregation |
| Không hiểu NULL | Mong hai NULL khớp nhau bằng `=` | Dùng `IS NULL` hoặc `<=>` chỉ khi nghiệp vụ yêu cầu |
| Nối nhiều bảng một-nhiều rồi SUM | Tổng bị nhân theo số hàng ở bảng con khác | Tổng hợp theo đúng grain trước khi nối |
| Kiểu cột nối khác nhau | Ép kiểu, sai kết quả hoặc giảm khả năng dùng index | Chuẩn hóa kiểu dữ liệu và collation |
| Tạo index sai thứ tự cột | Truy vấn không dùng được leftmost prefix mong muốn | Thiết kế index theo mẫu lọc/nối thực tế |
| Giả định optimizer luôn dùng index | Chẩn đoán sai hiệu năng | Đọc `EXPLAIN`, estimates và actual rows |

## 16. Checklist trước khi đưa JOIN vào production

- Kết quả cần một hàng cho đối tượng nào (grain)?
- Các cột nối có phản ánh đúng quan hệ PK/FK hoặc unique key không?
- Nếu là khóa ghép, đã đưa đủ mọi cột vào điều kiện nối chưa?
- Các cột nối có kiểu, signedness, charset và collation tương thích không?
- Có cột nullable khiến điều kiện `=` không khớp như dự kiến không?
- Một hàng bên trái có thể khớp nhiều hàng bên phải không? Đó có phải kết quả mong muốn không?
- Các điều kiện lọc bổ sung có được đặt đúng vị trí và đúng ý nghĩa không?
- Có thể dùng `EXISTS` nếu chỉ cần kiểm tra sự tồn tại không?
- Index có hỗ trợ thứ tự cột trong điều kiện nối không?
- `EXPLAIN` cho thấy kế hoạch và số hàng ước lượng hợp lý không?
- Tổng hợp có bị nhân bản do nối nhiều quan hệ một-nhiều không?
- Đã kiểm tra kết quả với các khóa cụ thể và dữ liệu biên chưa?

## Kết luận

`INNER JOIN` ghép các hàng khi điều kiện `ON` đúng. Với khóa đơn, nối cột foreign key đến primary/unique key tương ứng. Với khóa ghép, phải nối đầy đủ mọi thành phần; bỏ một cột có thể tạo kết quả sai và fan-out lớn. Điều kiện nhiều cột có thể kết hợp khóa, phạm vi và quy tắc nghiệp vụ, nhưng cần phân biệt điều kiện nhận diện hàng với điều kiện lọc. Thiết kế index ghép theo leftmost prefix, xử lý NULL và cardinality có chủ đích, rồi dùng `EXPLAIN`/`EXPLAIN ANALYZE` để xác minh kế hoạch. Làm rõ grain của kết quả và quan hệ dữ liệu ngay từ đầu giúp truy vấn MySQL chính xác, dễ bảo trì và có hiệu năng ổn định.
