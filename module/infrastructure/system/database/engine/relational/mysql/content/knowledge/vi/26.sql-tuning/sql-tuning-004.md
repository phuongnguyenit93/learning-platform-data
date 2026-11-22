# Thiết kế composite index theo điều kiện lọc, JOIN và sắp xếp

Composite index (chỉ mục ghép) là một B-tree chứa nhiều cột theo một thứ tự xác định. Nó đặc biệt hữu ích khi truy vấn thường kết hợp nhiều điều kiện WHERE, nối bảng bằng JOIN và trả kết quả theo ORDER BY. Chọn đúng thứ tự cột giúp MySQL đi thẳng đến một vùng khóa nhỏ, giảm số hàng phải đọc và có thể tránh bước sắp xếp bổ sung.

Một composite index không đơn giản là gom mọi cột xuất hiện trong câu SQL vào cùng một index. B-tree sắp xếp theo thứ tự từ trái sang phải. Cột đầu tiên, các cột tiếp theo và vị trí của điều kiện range quyết định optimizer có thể tìm kiếm đến đâu. Nếu đặt sai thứ tự, index vẫn tồn tại nhưng có thể chỉ dùng được một phần, không hỗ trợ JOIN như mong muốn hoặc không đáp ứng ORDER BY.

Trong module **DATABASE_MYSQL**, thiết kế index cần cân bằng hiệu năng đọc, chi phí ghi, dung lượng lưu trữ và tính cạnh tranh khi nhiều transaction cùng cập nhật. Bài học này trình bày cách đọc workload, chọn thứ tự key part cho WHERE, JOIN và ORDER BY, kiểm chứng bằng EXPLAIN, rồi quyết định có nên mở rộng index thành covering index hay không.

## 1. Composite index hoạt động theo thứ tự cột

Giả sử có index:

```sql
CREATE INDEX idx_tenant_status_created
    ON orders (tenant_id, status, created_at);
```

B-tree được sắp xếp theo thứ tự:

1. tenant_id
2. Trong cùng tenant_id, sắp theo status
3. Trong cùng tenant_id và status, sắp theo created_at

Vì vậy, index này có thể hỗ trợ hiệu quả các điều kiện dựa trên leftmost prefix:

- tenant_id = ?
- tenant_id = ? AND status = ?
- tenant_id = ? AND status = ? AND created_at >= ?

Nhưng nó thường không tạo được một vùng tìm kiếm liên tục hiệu quả cho truy vấn chỉ lọc status hoặc chỉ lọc created_at vì key part đầu tiên tenant_id không được ràng buộc.

Ví dụ:

```sql
-- Có thể dùng leftmost prefix
SELECT *
FROM orders
WHERE tenant_id = 42;

-- Có thể dùng hai key part đầu
SELECT *
FROM orders
WHERE tenant_id = 42
  AND status = 'PAID';

-- Không có điều kiện trên key part đầu
SELECT *
FROM orders
WHERE status = 'PAID';
```

Truy vấn thứ ba vẫn có thể được phục vụ bằng full index scan, index skip scan trong một số phiên bản và điều kiện phù hợp, hoặc một index khác. Nhưng không nên thiết kế dựa trên giả định rằng mọi key part đều có thể được dùng độc lập.

### 1.1. Thứ tự cột là một phần của thiết kế

Hai index sau không tương đương:

```sql
CREATE INDEX idx_a ON orders (tenant_id, status, created_at);
CREATE INDEX idx_b ON orders (status, tenant_id, created_at);
```

Cả hai đều chứa ba cột, nhưng vùng khóa được tổ chức khác nhau. Nếu hầu hết truy vấn luôn lọc tenant_id trước, idx_a có thể phù hợp hơn. Nếu workload thường lọc status mà không có tenant_id, idx_b có thể hữu ích hơn cho những truy vấn đó.

Không có quy tắc rằng cột có cardinality cao nhất luôn phải đứng đầu. Hãy xem điều kiện truy vấn, các prefix được sử dụng, độ chọn lọc, số hàng theo tenant/status, JOIN và thứ tự sắp xếp cần phục vụ.

## 2. Bắt đầu từ workload thay vì từ danh sách cột

Trước khi tạo index, thu thập các truy vấn thực tế:

- Điều kiện WHERE nào xuất hiện thường xuyên?
- Điều kiện nào luôn đi cùng nhau?
- Cột nào được dùng để JOIN?
- Truy vấn có ORDER BY hoặc LIMIT không?
- Có GROUP BY, DISTINCT hoặc range theo thời gian không?
- Truy vấn đọc bao nhiêu hàng và trả về bao nhiêu hàng?
- Tần suất INSERT/UPDATE/DELETE của bảng là bao nhiêu?

Một index tốt thường phục vụ một nhóm truy vấn có cấu trúc tương tự. Một index quá rộng có thể giúp một truy vấn nhưng làm tăng dung lượng và chi phí bảo trì cho mọi thao tác ghi.

Ví dụ bảng đơn hàng:

```sql
CREATE TABLE orders (
    order_id BIGINT UNSIGNED NOT NULL,
    tenant_id BIGINT UNSIGNED NOT NULL,
    customer_id BIGINT UNSIGNED NOT NULL,
    status VARCHAR(20) NOT NULL,
    created_at DATETIME NOT NULL,
    total_amount DECIMAL(12, 2) NOT NULL,
    PRIMARY KEY (order_id)
) ENGINE = InnoDB;
```

Một số workload:

| Truy vấn | Điều kiện chính | Mục tiêu |
|---|---|---|
| Danh sách đơn đang chờ của tenant | tenant_id, status | Lọc |
| Đơn của khách hàng theo thời gian | customer_id, created_at | Lọc và sắp xếp |
| Đơn hàng của tenant JOIN khách hàng | tenant_id, customer_id | Lọc và JOIN |
| Đơn mới nhất của tenant | tenant_id, created_at | Lọc, ORDER BY, LIMIT |
| Đếm đơn theo trạng thái | tenant_id, status | Lọc và GROUP BY |

Đừng cố tạo một index duy nhất để phục vụ tất cả nếu thứ tự cột và access pattern xung đột. Có thể cần một số index chuyên biệt, nhưng mỗi index phải có lợi ích đủ lớn để bù chi phí ghi.

## 3. Thiết kế key part cho điều kiện WHERE

Một nguyên tắc thực dụng là đặt các điều kiện equality phù hợp trước điều kiện range, sau đó mới xét cột phục vụ sắp xếp hoặc truy cập bổ sung.

Ví dụ:

```sql
SELECT order_id, created_at, total_amount
FROM orders
WHERE tenant_id = 42
  AND status = 'PENDING'
  AND created_at >= '2026-01-01'
  AND created_at <  '2026-02-01';
```

Index phù hợp:

```sql
CREATE INDEX idx_orders_tenant_status_created
    ON orders (tenant_id, status, created_at);
```

Optimizer có thể:

1. Tìm vùng tenant_id = 42.
2. Trong vùng đó, thu hẹp tiếp status = 'PENDING'.
3. Quét range created_at trong tháng cần lấy.

### 3.1. Equality trước, range sau

Các điều kiện equality thường cho phép B-tree tiếp tục xác định vùng hẹp qua nhiều key part. Khi gặp key part range, phần còn lại thường không thể tiếp tục thu hẹp một range duy nhất theo cách đơn giản.

Ví dụ index:

```sql
CREATE INDEX idx_tenant_status_date_amount
    ON orders (tenant_id, status, created_at, total_amount);
```

Truy vấn:

```sql
SELECT order_id
FROM orders
WHERE tenant_id = 42
  AND status = 'PENDING'
  AND created_at >= '2026-01-01'
  AND total_amount > 1000000;
```

Index có thể dùng tenant_id và status làm equality prefix, created_at làm range. total_amount nằm sau range nên thường không tạo thêm một ranh giới tìm kiếm độc lập để thu hẹp range. Tuy nhiên, tùy cấu trúc index và kế hoạch, điều kiện total_amount có thể được kiểm tra bằng Index Condition Pushdown (ICP), giảm số lần phải đọc clustered record.

ICP giúp lọc ứng viên ngay trên index entry khi có thể; nó không có nghĩa mọi key part phía sau range đều được dùng để định vị B-tree range như equality prefix.

### 3.2. Thứ tự giữa các cột equality

Nếu truy vấn luôn có cả tenant_id = ? và status = ?, cả hai thứ tự sau có thể sử dụng hai key part đầu:

- (tenant_id, status, created_at)
- (status, tenant_id, created_at)

Hãy chọn thứ tự dựa trên các truy vấn khác trong workload:

- Truy vấn có tenant_id nhưng không có status có cần được hỗ trợ không?
- Truy vấn có status toàn hệ thống có quan trọng không?
- Tenant có phân bố dữ liệu rất lệch không?
- Có cần phục vụ truy vấn JOIN hoặc ORDER BY khác không?
- Index nào cho phép tái sử dụng leftmost prefix nhiều nhất?

Độ chọn lọc của cột là một yếu tố, nhưng không phải yếu tố duy nhất. Cột equality đứng đầu phải phù hợp với các mẫu truy vấn cần phục vụ.

### 3.3. IN, IS NULL và điều kiện nhiều giá trị

Điều kiện IN có thể được optimizer xử lý thành nhiều range hoặc nhiều lần tra cứu:

```sql
SELECT order_id
FROM orders
WHERE tenant_id = 42
  AND status IN ('PENDING', 'PAID')
  AND created_at >= '2026-01-01';
```

Index (tenant_id, status, created_at) vẫn có thể hữu ích, nhưng nhiều giá trị status có thể tạo nhiều vùng tra cứu. Khi cần ORDER BY toàn cục theo created_at, nhiều range riêng có thể khiến optimizer phải merge hoặc sort kết quả.

IS NULL có thể được dùng trong điều kiện tìm kiếm trên index. Tuy nhiên, hãy xác nhận hành vi bằng EXPLAIN thay vì xem NULL như một giá trị equality thông thường trong mọi ngữ cảnh.

### 3.4. Tránh làm điều kiện mất tính sargable

Một điều kiện sargable cho phép optimizer dùng index để tìm vùng dữ liệu thích hợp.

Ví dụ không thuận lợi:

```sql
SELECT order_id
FROM orders
WHERE DATE(created_at) = '2026-01-15';
```

Việc áp dụng hàm lên cột có thể ngăn range access trực tiếp trên index created_at. Viết lại thành khoảng thời gian:

```sql
SELECT order_id
FROM orders
WHERE created_at >= '2026-01-15 00:00:00'
  AND created_at <  '2026-01-16 00:00:00';
```

Giữ kiểu dữ liệu tham số tương thích với kiểu cột; tránh ép kiểu ngầm hoặc chuyển đổi cột trong biểu thức khi không cần thiết.

## 4. Thiết kế composite index cho JOIN

Với nested-loop join, MySQL thường đọc một hàng từ bảng ngoài rồi tra cứu các hàng tương ứng ở bảng trong. Index trên cột JOIN của bảng trong giúp tránh quét toàn bộ bảng trong cho mỗi hàng ngoài.

Ví dụ:

```sql
CREATE TABLE customers (
    customer_id BIGINT UNSIGNED NOT NULL,
    tenant_id BIGINT UNSIGNED NOT NULL,
    customer_name VARCHAR(150) NOT NULL,
    PRIMARY KEY (customer_id),
    KEY idx_customers_tenant (tenant_id)
) ENGINE = InnoDB;

CREATE TABLE orders (
    order_id BIGINT UNSIGNED NOT NULL,
    tenant_id BIGINT UNSIGNED NOT NULL,
    customer_id BIGINT UNSIGNED NOT NULL,
    status VARCHAR(20) NOT NULL,
    created_at DATETIME NOT NULL,
    total_amount DECIMAL(12, 2) NOT NULL,
    PRIMARY KEY (order_id),
    KEY idx_orders_tenant_status_created (
        tenant_id,
        status,
        created_at
    ),
    KEY idx_orders_customer_created (
        customer_id,
        created_at
    )
) ENGINE = InnoDB;
```

Truy vấn:

```sql
SELECT
    o.order_id,
    o.created_at,
    c.customer_name
FROM orders AS o
JOIN customers AS c
    ON c.customer_id = o.customer_id
WHERE o.tenant_id = 42
  AND o.status = 'PAID'
  AND o.created_at >= '2026-01-01'
  AND o.created_at <  '2026-02-01'
ORDER BY o.created_at DESC;
```

Optimizer có thể lọc orders bằng idx_orders_tenant_status_created rồi tra cứu customers bằng PRIMARY KEY(customer_id). Nếu kế hoạch chọn customers làm bảng ngoài, index và điều kiện trên orders có thể được sử dụng theo cách khác. Hãy đọc thứ tự JOIN trong EXPLAIN.

### 4.1. Index cho bảng trong của JOIN

Ví dụ hai bảng:

```sql
CREATE TABLE order_items (
    item_id BIGINT UNSIGNED NOT NULL,
    order_id BIGINT UNSIGNED NOT NULL,
    product_id BIGINT UNSIGNED NOT NULL,
    quantity INT NOT NULL,
    PRIMARY KEY (item_id)
) ENGINE = InnoDB;
```

```sql
SELECT
    o.order_id,
    i.product_id,
    i.quantity
FROM orders AS o
JOIN order_items AS i
    ON i.order_id = o.order_id
WHERE o.tenant_id = 42
  AND o.status = 'PAID';
```

Nếu optimizer lọc orders trước rồi tra cứu order_items cho từng order_id, index:

```sql
CREATE INDEX idx_items_order_product
    ON order_items (order_id, product_id);
```

có thể hỗ trợ lookup theo order_id. Nếu truy vấn còn lọc product_id trong cùng lần tra cứu, key part thứ hai có thể hữu ích.

Ngược lại, nếu product_id là điều kiện rất chọn lọc và optimizer bắt đầu từ order_items để tìm orders, index:

```sql
CREATE INDEX idx_items_product_order
    ON order_items (product_id, order_id);
```

có thể phù hợp hơn. Hai index này không thay thế nhau vì leftmost prefix khác nhau.

### 4.2. JOIN nhiều cột

Nếu điều kiện JOIN gồm nhiều cột:

```sql
CREATE TABLE tenant_orders (
    order_id BIGINT UNSIGNED NOT NULL,
    tenant_id BIGINT UNSIGNED NOT NULL,
    customer_id BIGINT UNSIGNED NOT NULL,
    PRIMARY KEY (order_id),
    KEY idx_orders_tenant_customer (tenant_id, customer_id)
) ENGINE = InnoDB;

CREATE TABLE tenant_customers (
    customer_row_id BIGINT UNSIGNED NOT NULL,
    tenant_id BIGINT UNSIGNED NOT NULL,
    customer_id BIGINT UNSIGNED NOT NULL,
    customer_name VARCHAR(150) NOT NULL,
    PRIMARY KEY (customer_row_id),
    UNIQUE KEY uq_tenant_customer (tenant_id, customer_id)
) ENGINE = InnoDB;
```

```sql
SELECT *
FROM tenant_orders AS o
JOIN tenant_customers AS c
  ON c.tenant_id = o.tenant_id
 AND c.customer_id = o.customer_id
WHERE o.tenant_id = 42;
```

UNIQUE KEY uq_tenant_customer chính là composite index trên bảng được tra cứu. Nó vừa bảo đảm customer_id không trùng trong cùng tenant, vừa hỗ trợ lookup theo hai cột JOIN. Nếu cặp (tenant_id, customer_id) đã là PRIMARY KEY hoặc UNIQUE KEY thì không cần tạo thêm index trùng lặp. Luôn kiểm tra index hiện có trước khi thêm.

### 4.3. Chọn thứ tự theo bảng driving

Không có một thứ tự cột JOIN đúng cho mọi kế hoạch. Hãy xác định:

1. Bảng nào có khả năng trở thành bảng ngoài (driving/outer table)?
2. Điều kiện nào lọc bảng ngoài xuống ít hàng nhất?
3. Với mỗi hàng ngoài, bảng trong được tra cứu theo những cột nào?
4. Có điều kiện bổ sung trên bảng trong không?
5. Truy vấn có thể được optimizer đổi thứ tự JOIN không?

Index của bảng trong thường bắt đầu bằng các cột dùng để tra cứu từ bảng ngoài. Nếu có thêm điều kiện equality trên bảng trong, cân nhắc đưa chúng vào các key part tiếp theo.

Không tạo index trên mọi cột JOIN theo phản xạ. Primary key, unique key hoặc index ghép hiện có có thể đã đáp ứng lookup.

## 5. Kết hợp WHERE, JOIN và ORDER BY trong một index

Đây là trường hợp cần cân bằng nhiều mục tiêu. Một index có thể:

- Thu hẹp tập hàng theo WHERE.
- Hỗ trợ lookup/JOIN.
- Trả hàng theo thứ tự ORDER BY.
- Có thể bao phủ một phần hoặc toàn bộ cột SELECT.

Ví dụ truy vấn danh sách đơn hàng mới nhất của một tenant:

```sql
SELECT
    order_id,
    customer_id,
    created_at,
    total_amount
FROM orders
WHERE tenant_id = 42
  AND status = 'PAID'
  AND created_at >= '2026-01-01'
  AND created_at <  '2026-02-01'
ORDER BY created_at DESC, order_id DESC
LIMIT 50;
```

Index đề xuất cho MySQL 8.0:

```sql
CREATE INDEX idx_orders_tenant_status_created_id
    ON orders (
        tenant_id,
        status,
        created_at DESC,
        order_id DESC
    );
```

Phân tích thứ tự:

1. tenant_id được cố định bằng equality.
2. status được cố định bằng equality.
3. created_at giới hạn range và là cột sắp xếp đầu tiên.
4. order_id là tie-breaker để thứ tự kết quả ổn định.

Với hai key part đầu đã được cố định, B-tree có thể quét vùng thời gian theo thứ tự phù hợp. LIMIT 50 giúp dừng sớm sau khi tìm đủ hàng nếu kế hoạch sử dụng index order.

MySQL 8.0 hỗ trợ descending index key part. Với index tăng dần, B-tree cũng có thể được quét ngược khi toàn bộ hướng sắp xếp phù hợp. Khi ORDER BY trộn ASC và DESC, khai báo hướng index tương ứng có thể cần thiết để tránh sort.

### 5.1. Vì sao cột range và ORDER BY cần được cân nhắc cùng nhau?

Một index có thể dùng equality prefix rồi quét range. Nếu ORDER BY bắt đầu từ cột range và tiếp tục theo các key part kế tiếp, index có thể cung cấp thứ tự mong muốn.

Nhưng nếu truy vấn có:

```sql
WHERE tenant_id = 42
  AND status IN ('PAID', 'PENDING')
ORDER BY created_at DESC;
```

index (tenant_id, status, created_at) tạo các vùng theo từng status. Thứ tự created_at trong từng vùng không tự động trở thành một thứ tự toàn cục giữa nhiều status. Optimizer có thể cần merge hoặc sort.

Nếu ORDER BY created_at toàn cục là mục tiêu chính, index (tenant_id, created_at) có thể phù hợp hơn, nhưng khi đó status trở thành điều kiện lọc sau khi đọc. Cần benchmark hai phương án trên phân bố dữ liệu thật.

### 5.2. ORDER BY có cột chưa được cố định

Giả sử index:

```sql
CREATE INDEX idx_tenant_status_created
    ON orders (tenant_id, status, created_at);
```

Truy vấn:

```sql
SELECT order_id
FROM orders
WHERE tenant_id = 42
ORDER BY created_at DESC;
```

Vì status nằm giữa tenant_id và created_at nhưng không được cố định, index không cung cấp thứ tự created_at toàn cục cho tenant. Các hàng được nhóm theo status trước, rồi mới theo created_at trong từng nhóm.

Một index khác có thể phù hợp hơn:

```sql
CREATE INDEX idx_tenant_created
    ON orders (tenant_id, created_at DESC);
```

Không thể chỉ nhìn thấy cột ORDER BY có mặt trong index rồi kết luận MySQL sẽ tránh filesort. Thứ tự các key part trước nó cũng quan trọng.

## 6. Covering index: khi nào nên thêm cột SELECT?

Covering index là index chứa đủ các cột cần thiết cho một truy vấn để engine có thể trả kết quả mà không cần đọc clustered record cho từng hàng, khi điều kiện và access path cho phép.

Ví dụ truy vấn:

```sql
SELECT order_id, created_at, total_amount
FROM orders
WHERE tenant_id = 42
  AND status = 'PAID'
ORDER BY created_at DESC
LIMIT 50;
```

Index lọc và sắp xếp:

```sql
CREATE INDEX idx_orders_tenant_status_created
    ON orders (tenant_id, status, created_at DESC);
```

Index này có thể cần đọc clustered record để lấy total_amount. Nếu truy vấn rất thường xuyên và 50 lần lookup clustered record là chi phí đáng kể, có thể thử index mở rộng:

```sql
CREATE INDEX idx_orders_tenant_status_created_amount
    ON orders (
        tenant_id,
        status,
        created_at DESC,
        total_amount
    );
```

Tuy nhiên, nếu cần ORDER BY created_at DESC, order_id DESC thì total_amount đứng trước order_id trong index có thể làm mất thứ tự tie-breaker mong muốn. Khi đó có thể cân nhắc:

```sql
CREATE INDEX idx_orders_tenant_status_created_id_amount
    ON orders (
        tenant_id,
        status,
        created_at DESC,
        order_id DESC,
        total_amount
    );
```

Đây là index lớn hơn. Không nên thêm mọi cột SELECT vào index chỉ để đạt covering. Cần cân nhắc:

- Số truy vấn được hưởng lợi và tần suất của chúng.
- Kích thước các cột được thêm.
- Tần suất INSERT/UPDATE/DELETE.
- Chi phí buffer pool và I/O.
- Việc thay đổi cột có làm index phải bảo trì nhiều hơn không.

Trong InnoDB, secondary index tự mang theo primary key để định vị hàng. Tuy nhiên, nếu cần điều khiển hướng sắp xếp hoặc vị trí tie-breaker, có thể phải khai báo primary key column tường minh trong index.

## 7. Thứ tự ASC/DESC và tính ổn định của kết quả

MySQL 8.0 hỗ trợ descending index. Ví dụ:

```sql
CREATE INDEX idx_orders_recent
    ON orders (
        tenant_id ASC,
        created_at DESC,
        order_id DESC
    );
```

Truy vấn:

```sql
SELECT order_id, created_at
FROM orders
WHERE tenant_id = 42
ORDER BY created_at DESC, order_id DESC
LIMIT 100;
```

Index có thể phục vụ lọc tenant và thứ tự mới nhất. order_id giúp xác định thứ tự ổn định khi nhiều hàng có cùng created_at.

Nếu chỉ ORDER BY created_at nhưng nhiều hàng có cùng timestamp, thứ tự giữa các hàng đó không được đảm bảo. Khi phân trang bằng LIMIT/OFFSET hoặc keyset pagination, nên thêm tie-breaker duy nhất như order_id để tránh kết quả thay đổi khó dự đoán.

Với MySQL trước 8.0, cú pháp DESC trong index có thể được chấp nhận nhưng key part được lưu theo hướng tăng dần và không tạo descending index vật lý như MySQL 8.0. Kiểm tra phiên bản đích trước khi dựa vào mixed-direction index.

## 8. Composite index và GROUP BY

Index có thể hỗ trợ GROUP BY nếu thứ tự key part phù hợp với cách nhóm và các điều kiện lọc phía trước. Ví dụ:

```sql
SELECT tenant_id, status, COUNT(*)
FROM orders
WHERE tenant_id = 42
GROUP BY tenant_id, status;
```

Index (tenant_id, status) có thể hỗ trợ lọc tenant và đọc các nhóm status theo thứ tự index. Nhưng nếu GROUP BY theo status toàn bảng mà index bắt đầu bằng tenant_id, index có thể không giúp tạo thứ tự nhóm toàn cục.

GROUP BY, DISTINCT và ORDER BY có các quy tắc tối ưu riêng. Hãy kiểm tra Extra, JSON/TREE plan và số hàng thực tế thay vì cho rằng composite index tự động loại bỏ temporary table hoặc filesort.

## 9. Index Merge không thay thế thiết kế composite index

MySQL có thể dùng Index Merge để kết hợp nhiều index đơn lẻ trong một số truy vấn:

```sql
CREATE INDEX idx_orders_tenant ON orders (tenant_id);
CREATE INDEX idx_orders_status ON orders (status);

SELECT order_id
FROM orders
WHERE tenant_id = 42
  AND status = 'PENDING';
```

Optimizer có thể cân nhắc intersect các tập row ID từ hai index. Nhưng Index Merge có chi phí kết hợp và truy cập dữ liệu riêng. Một composite index:

```sql
CREATE INDEX idx_orders_tenant_status
    ON orders (tenant_id, status);
```

thường cho phép tìm trực tiếp vùng kết hợp và có thể hiệu quả hơn.

Không phải mọi truy vấn đều tốt hơn với composite index; index đơn lẻ có thể được tái sử dụng bởi nhiều workload khác. Hãy so sánh EXPLAIN và benchmark.

## 10. Đọc EXPLAIN để xác nhận composite index

Trước khi thêm index, ghi nhận plan:

```sql
EXPLAIN FORMAT = JSON
SELECT
    order_id,
    customer_id,
    created_at,
    total_amount
FROM orders
WHERE tenant_id = 42
  AND status = 'PAID'
  AND created_at >= '2026-01-01'
  AND created_at <  '2026-02-01'
ORDER BY created_at DESC, order_id DESC
LIMIT 50;
```

Các điểm cần xem:

| Trường | Câu hỏi |
|---|---|
| access_type / type | Có dùng range/ref hay đang full scan? |
| possible_keys | Index nào có thể dùng? |
| key | Optimizer thực sự chọn index nào? |
| key_len | Bao nhiêu key part được sử dụng? |
| rows | Ước lượng số hàng cần đọc là bao nhiêu? |
| filtered | Còn bao nhiêu phần trăm hàng sau điều kiện bổ sung? |
| Extra | Có Using filesort, Using temporary, Using index condition hay Using index không? |
| cost_info | Chi phí ước lượng của optimizer thay đổi ra sao? |

key_len có thể giúp suy ra phần nào của composite index được dùng để lookup, nhưng cần xét kiểu dữ liệu, NULLability và charset. Nó không cho biết đầy đủ mọi điều kiện đã được kiểm tra bằng ICP hoặc WHERE.

Sau khi tạo index, đọc lại plan:

```sql
CREATE INDEX idx_orders_tenant_status_created_id
    ON orders (
        tenant_id,
        status,
        created_at DESC,
        order_id DESC
    );

EXPLAIN FORMAT = JSON
SELECT
    order_id,
    customer_id,
    created_at,
    total_amount
FROM orders
WHERE tenant_id = 42
  AND status = 'PAID'
  AND created_at >= '2026-01-01'
  AND created_at <  '2026-02-01'
ORDER BY created_at DESC, order_id DESC
LIMIT 50;
```

Trên MySQL 8.0.18 trở lên, EXPLAIN ANALYZE có thể thực thi SELECT và hiển thị actual rows, loops và thời gian iterator:

```sql
EXPLAIN ANALYZE
SELECT
    order_id,
    customer_id,
    created_at,
    total_amount
FROM orders
WHERE tenant_id = 42
  AND status = 'PAID'
  AND created_at >= '2026-01-01'
  AND created_at <  '2026-02-01'
ORDER BY created_at DESC, order_id DESC
LIMIT 50;
```

EXPLAIN ANALYZE chạy truy vấn thật. Chỉ dùng với truy vấn SELECT phù hợp và đánh giá tác động trước khi chạy trên production.

## 11. Một index có thể phục vụ nhiều truy vấn, nhưng không phải mọi truy vấn

Index (tenant_id, status, created_at) có thể phục vụ:

- WHERE tenant_id = ?
- WHERE tenant_id = ? AND status = ?
- WHERE tenant_id = ? AND status = ? AND created_at >= ?
- WHERE tenant_id = ? AND status = ? ORDER BY created_at

Nhưng nó không phải lựa chọn tốt cho mọi mẫu:

- WHERE status = ? nếu không có tenant_id.
- WHERE created_at >= ? nếu không có hai key part đầu.
- WHERE tenant_id = ? ORDER BY created_at nếu status không được cố định.
- ORDER BY created_at toàn cục không có điều kiện tenant_id.

Một index ghép dài có thể bao phủ nhiều prefix, nhưng thêm key part cũng làm index lớn hơn và tăng chi phí ghi. Thiết kế nên hướng đến nhóm truy vấn quan trọng có thể tái sử dụng prefix.

## 12. Những lỗi thiết kế thường gặp

| Sai lầm | Hệ quả | Cách xử lý |
|---|---|---|
| Đưa mọi cột WHERE vào index theo thứ tự tùy ý | Optimizer chỉ dùng được một phần key | Xét equality, range và leftmost prefix |
| Luôn đặt cột cardinality cao nhất đầu tiên | Bỏ qua mẫu truy vấn và khả năng tái sử dụng prefix | Chọn theo workload thực tế |
| Đặt cột range trước các equality cần thiết | Key part sau range ít có tác dụng thu hẹp lookup | Đặt equality phù hợp trước range |
| Đặt cột ORDER BY sau key part không được cố định | Index không cung cấp thứ tự toàn cục mong muốn | Cố định hoặc loại bỏ key part đứng trước |
| Chỉ tạo index trên bảng ngoài của JOIN | Lookup lặp ở bảng trong vẫn có thể quét rộng | Index cột JOIN trên bảng được tra cứu |
| Tạo cả (a,b) và (b,a) mà không có workload chứng minh | Tăng dung lượng và chi phí ghi | Kiểm tra truy vấn nào cần từng leftmost prefix |
| Thêm toàn bộ cột SELECT để cover | Index lớn, tăng write amplification | Đo lợi ích của covering index |
| Nghĩ Index Merge luôn tương đương composite index | Tốn chi phí kết hợp row ID | So sánh plan và benchmark |
| Nghĩ có cột ORDER BY trong index là tránh được filesort | Thứ tự key part phía trước có thể phá thứ tự | Kiểm tra toàn bộ thứ tự index |
| Bỏ tie-breaker khi dùng LIMIT | Thứ tự giữa hàng trùng giá trị không ổn định | Thêm khóa duy nhất vào ORDER BY |
| Không đo sau khi tạo index | Index có thể không được dùng hoặc plan xấu hơn | EXPLAIN, EXPLAIN ANALYZE và workload test |

## 13. Quy trình thiết kế composite index

Thực hiện theo các bước:

1. **Chọn truy vấn đại diện.** Dùng truy vấn có tần suất hoặc tác động lớn, không thiết kế dựa trên một câu lệnh hiếm.
2. **Tách điều kiện.** Phân loại equality, IN, IS NULL, range, JOIN, ORDER BY và GROUP BY.
3. **Xác định bảng driving.** Với JOIN, xác định bảng ngoài và lookup trên bảng trong theo plan hiện tại.
4. **Chọn equality prefix.** Đặt các cột equality cần thiết ở đầu, xét khả năng phục vụ những truy vấn có ít điều kiện hơn.
5. **Đặt range hợp lý.** Range thường đứng sau các equality key part mà truy vấn có thể dùng.
6. **Xét thứ tự sắp xếp.** Đặt cột ORDER BY tiếp theo nếu các key part đứng trước đã được cố định và thứ tự tương thích.
7. **Xét covering sau cùng.** Chỉ thêm cột SELECT khi lợi ích giảm clustered lookup đủ lớn.
8. **Kiểm tra index trùng/lồng nhau.** Tái sử dụng index hiện có nếu leftmost prefix đã đáp ứng.
9. **Đọc EXPLAIN.** Kiểm tra key, key_len, rows, filtered, Extra và join order.
10. **Benchmark.** So sánh latency, throughput, rows examined, CPU/I/O và chi phí DML.
11. **Theo dõi production.** Kiểm tra index usage, dung lượng, lock wait và plan regression sau triển khai.

## 14. Đánh giá chi phí ghi và vòng đời index

Mỗi secondary index bổ sung cần được duy trì khi INSERT, DELETE và khi các cột trong index thay đổi. Composite index dài hơn làm tăng kích thước B-tree và có thể giảm số entry nằm trong một page.

Trước khi thêm index, cân nhắc:

- Bảng có tốc độ ghi cao hay thấp?
- Các cột trong index có thường xuyên thay đổi không?
- Index có trùng hoặc bao phủ bởi index khác không?
- Có thể thay hai index đơn bằng một composite index mà vẫn giữ workload khác không?
- Index có làm tăng thời gian import, update hoặc delete đáng kể không?
- Dung lượng index có phù hợp buffer pool và storage không?

Không xóa index chỉ dựa trên một khoảng quan sát ngắn. Index có thể phục vụ truy vấn định kỳ, báo cáo, ràng buộc hoặc luồng nghiệp vụ ít xảy ra nhưng quan trọng.

## 15. Ví dụ tổng hợp: lọc, JOIN và sắp xếp

Yêu cầu: lấy 50 đơn hàng PAID mới nhất của tenant, hiển thị tên khách hàng.

```sql
SELECT
    o.order_id,
    o.created_at,
    o.total_amount,
    c.customer_name
FROM orders AS o
JOIN customers AS c
    ON c.customer_id = o.customer_id
WHERE o.tenant_id = 42
  AND o.status = 'PAID'
ORDER BY o.created_at DESC, o.order_id DESC
LIMIT 50;
```

Index có thể dùng:

```sql
CREATE INDEX idx_orders_tenant_status_created_id
    ON orders (
        tenant_id,
        status,
        created_at DESC,
        order_id DESC
    );
```

customers đã có PRIMARY KEY(customer_id), nên lookup khách hàng theo customer_id có index unique sẵn. Không cần tạo thêm index customer_id trùng lặp trên customers.

Kế hoạch kỳ vọng về mặt logic:

1. Dùng equality prefix tenant_id và status để tìm vùng đơn hàng.
2. Quét theo created_at DESC, order_id DESC.
3. Dừng khi đủ 50 hàng.
4. Với mỗi hàng, tra cứu customer bằng PRIMARY KEY.

Đây là giả thuyết thiết kế, không phải cam kết optimizer sẽ luôn chọn đúng plan này. Nếu tenant có quá nhiều đơn PAID hoặc phần lớn hàng bị lọc sau đó, plan khác có thể rẻ hơn. Dùng EXPLAIN và benchmark để xác nhận.

Nếu truy vấn rất quan trọng và lookup clustered record trên orders là chi phí lớn, có thể thử covering index sau khi đo. Nhưng thêm total_amount hoặc customer_id làm tăng index size; cần giữ order_id ở vị trí phù hợp nếu nó là tie-breaker cho ORDER BY.

## 16. Checklist trước khi đưa composite index vào production

- Truy vấn mục tiêu và tham số đại diện đã được xác định.
- Đã phân loại equality, range, JOIN và ORDER BY.
- Thứ tự key part tuân theo leftmost prefix của workload.
- Cột range không đứng trước equality key part cần thiết.
- Cột ORDER BY không bị một key part biến thiên phía trước làm phá thứ tự.
- Index trên bảng trong của JOIN hỗ trợ lookup từ bảng ngoài.
- Đã kiểm tra PRIMARY/UNIQUE/index hiện có để tránh trùng.
- Đã đánh giá covering index và chi phí kích thước.
- EXPLAIN cho thấy access path phù hợp.
- EXPLAIN ANALYZE hoặc benchmark xác nhận actual rows và thời gian cải thiện.
- Đã đo chi phí INSERT/UPDATE/DELETE và dung lượng index.
- Có kế hoạch theo dõi plan regression sau triển khai.

## 17. Ghi nhớ

- Composite index là B-tree nhiều cột; thứ tự key part quyết định khả năng dùng leftmost prefix.
- Đặt các điều kiện equality phù hợp trước range; key part sau range thường không tiếp tục thu hẹp lookup theo cách đơn giản.
- Thứ tự giữa các cột equality phải dựa trên workload, selectivity và khả năng tái sử dụng prefix.
- Với nested-loop JOIN, index trên bảng trong cần hỗ trợ lookup theo các cột nối từ bảng ngoài.
- Nếu JOIN nhiều cột, cân nhắc composite index theo đúng các key part được dùng để tra cứu.
- ORDER BY có thể dùng index khi key part đứng trước đã được cố định và thứ tự cột/hướng ASC-DESC tương thích.
- IN trên nhiều giá trị có thể tạo nhiều range; index không chắc cung cấp thứ tự toàn cục cho cột phía sau.
- Covering index giảm clustered lookup nhưng làm index lớn và tăng chi phí ghi.
- Index Merge không mặc nhiên tốt bằng composite index phù hợp.
- EXPLAIN cho biết access path ước lượng; EXPLAIN ANALYZE trên SELECT giúp so sánh actual rows, loops và thời gian.
- Mỗi index cần được đánh giá theo cả workload đọc lẫn INSERT/UPDATE/DELETE.
- Thiết kế index là giả thuyết cần được xác nhận bằng dữ liệu và benchmark.

Thiết kế composite index hiệu quả bắt đầu từ câu truy vấn và thứ tự truy cập thực tế. Hãy phối hợp điều kiện lọc, cột JOIN và thứ tự sắp xếp trong cùng một B-tree khi chúng có chung access pattern; sau đó xác nhận bằng execution plan và benchmark trước khi triển khai rộng.

## Tài liệu tham khảo

- MySQL 8.0 Reference Manual — Multiple-Column Indexes: https://dev.mysql.com/doc/refman/8.0/en/multiple-column-indexes.html
- MySQL 8.0 Reference Manual — ORDER BY Optimization: https://dev.mysql.com/doc/refman/8.0/en/order-by-optimization.html
- MySQL 8.0 Reference Manual — Index Condition Pushdown Optimization: https://dev.mysql.com/doc/refman/8.0/en/index-condition-pushdown-optimization.html
- MySQL 8.0 Reference Manual — EXPLAIN Output Format: https://dev.mysql.com/doc/refman/8.0/en/explain-output.html

