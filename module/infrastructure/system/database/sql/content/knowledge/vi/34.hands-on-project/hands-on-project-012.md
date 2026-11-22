# Đối chiếu cùng bài toán trên hai hệ quản trị

## 1. Mục tiêu: so sánh bằng một bài toán thật

Khi học nhiều hệ quản trị cơ sở dữ liệu, chỉ liệt kê cú pháp khác nhau là chưa đủ. Một câu lệnh có thể trông gần giống nhau nhưng khác về kiểu dữ liệu, transaction, collation, timezone, index hoặc hành vi sau lỗi.

Cách thực hành tốt hơn là lấy **một bài toán nghiệp vụ cố định**, triển khai trên hai hệ quản trị, rồi so sánh kết quả và các bảo đảm mà ứng dụng nhận được.

Bài học này dùng **PostgreSQL 15+** và **MySQL 8.0+ với InnoDB** để xây một hệ thống bán hàng nhỏ. Một khách hàng tạo đơn hàng; mỗi đơn có nhiều dòng sản phẩm; tồn kho giảm khi đơn được xác nhận.

Ta sẽ đối chiếu:

- Schema và kiểu dữ liệu.
- CRUD, JOIN, aggregate và phân trang.
- Generated ID và upsert.
- Transaction, row lock, isolation và deadlock.
- Tiền, Boolean, NULL, Unicode, JSON và ngày giờ.
- Index, query plan và migration.
- Java/JDBC, exception mapping và integration tests.

Mục tiêu không phải tìm một hệ quản trị thắng trong mọi tình huống. Mục tiêu là chứng minh rằng **cùng một nghiệp vụ có thể có những triển khai SQL khác nhau, và các khác biệt phải được hiểu trước khi đưa vào production**.

## 2. Bài toán nghiệp vụ và hợp đồng dữ liệu

Cửa hàng cần quản lý:

- Khách hàng có email và tên hiển thị.
- Sản phẩm có SKU duy nhất, tên và giá.
- Tồn kho hiện tại của từng sản phẩm.
- Đơn hàng thuộc về một khách hàng.
- Mỗi đơn có nhiều dòng sản phẩm.
- Mỗi dòng ghi lại số lượng và đơn giá tại thời điểm đặt hàng.
- Đơn hàng có trạng thái và thời điểm tạo.
- Khi xác nhận đơn, hệ thống phải trừ tồn kho; nếu không đủ hàng, toàn bộ thao tác xác nhận thất bại.

Các bất biến:

1. SKU là duy nhất.
2. Giá và tồn kho không âm; số lượng đặt phải lớn hơn 0.
3. Mỗi order phải tham chiếu customer tồn tại.
4. Mỗi order item phải tham chiếu order và product tồn tại.
5. Đơn giá trong order item là snapshot tại thời điểm đặt, không tự đổi khi giá catalog thay đổi.
6. Không được trừ tồn kho nếu số lượng không đủ.
7. Xác nhận đơn phải nguyên tử: trạng thái, tồn kho và các bước ghi liên quan thành công cùng nhau.
8. Tiền dùng số thập phân chính xác.
9. Thời điểm lưu trữ có quy ước timezone rõ.
10. Tên hiển thị hỗ trợ Unicode; mã kỹ thuật có quy tắc so sánh ổn định.

### 2.1. Mô hình quan hệ

```text
customers 1 -------- n orders
orders    1 -------- n order_items
products  1 -------- n order_items
products  1 -------- 1 inventory
```

| Bảng | Vai trò | Khóa chính |
| --- | --- | --- |
| customers | Khách hàng | customer_id |
| products | Danh mục sản phẩm | product_id |
| inventory | Tồn kho | product_id |
| orders | Đơn hàng | order_id |
| order_items | Chi tiết đơn | (order_id, product_id) |

Khóa ghép của order_items giả định một sản phẩm chỉ xuất hiện một lần trong một đơn. Nếu nghiệp vụ cho phép nhiều dòng cùng SKU với giá/discount khác nhau, hãy thêm order_item_id và thiết kế lại khóa.

## 3. Cố định phiên bản và cấu hình trước khi so sánh

Không so sánh một PostgreSQL mới với một MySQL cũ rồi kết luận khác biệt là bản chất của hai hệ quản trị.

PostgreSQL:

```sql
SELECT version();
SHOW server_encoding;
SHOW TimeZone;
SHOW transaction_isolation;
```

MySQL:

```sql
SELECT VERSION();
SELECT @@sql_mode;
SELECT @@character_set_server;
SELECT @@collation_server;
SELECT @@time_zone;
SELECT @@system_time_zone;
SELECT @@transaction_isolation;
```

Ghi nhận thêm:

- PostgreSQL JDBC driver và MySQL Connector/J version.
- Storage engine của bảng MySQL.
- Autocommit và isolation level.
- Charset/collation ở database, table và column.
- Timezone của JVM, session và server.
- SQL mode của MySQL.
- Statistics và cấu hình index.

Ví dụ giả định PostgreSQL 15+ và MySQL 8.0+ dùng InnoDB. Một số tính năng khác theo minor version hoặc cấu hình; hãy kiểm tra đúng môi trường thực tế.

## 4. Chọn kiểu dữ liệu theo ý nghĩa nghiệp vụ

| Ý nghĩa | PostgreSQL | MySQL |
| --- | --- | --- |
| ID tự tăng | BIGINT IDENTITY | BIGINT AUTO_INCREMENT |
| Chuỗi Unicode | VARCHAR/TEXT trong database UTF8 | VARCHAR/TEXT với utf8mb4 |
| Tiền | NUMERIC/DECIMAL | DECIMAL |
| Boolean | BOOLEAN thật | BOOLEAN alias TINYINT(1) |
| Thời điểm | TIMESTAMPTZ hoặc TIMESTAMP | TIMESTAMP hoặc DATETIME |
| JSON | JSON hoặc JSONB | JSON |
| Khóa ngoại | FOREIGN KEY | FOREIGN KEY với InnoDB |

Tên kiểu tương tự không đảm bảo semantics giống nhau. Ví dụ PostgreSQL BOOLEAN là kiểu riêng; MySQL BOOLEAN là alias của TINYINT(1). TIMESTAMPTZ PostgreSQL và DATETIME MySQL cũng có cách diễn giải khác nhau.

Trước khi viết DDL, hãy quyết định domain model:

- ID là số nguyên 64-bit.
- Giá là BigDecimal với precision/scale được quy định.
- Tên và email là Unicode text.
- Trạng thái đơn là vocabulary có giới hạn.
- created_at biểu diễn một instant UTC.
- Metadata linh hoạt có thể dùng JSON, nhưng dữ liệu cần JOIN/constraint vẫn nên là cột quan hệ.

## 5. DDL PostgreSQL

Tạo schema riêng:

```sql
CREATE SCHEMA shop;

CREATE TABLE shop.customers (
    customer_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    email VARCHAR(255) NOT NULL UNIQUE,
    full_name VARCHAR(200) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE shop.products (
    product_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    sku VARCHAR(64) NOT NULL UNIQUE,
    product_name VARCHAR(200) NOT NULL,
    unit_price NUMERIC(14,2) NOT NULL
        CHECK (unit_price >= 0),
    active BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE TABLE shop.inventory (
    product_id BIGINT PRIMARY KEY
        REFERENCES shop.products(product_id),
    quantity_on_hand INTEGER NOT NULL
        CHECK (quantity_on_hand >= 0),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE shop.orders (
    order_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    customer_id BIGINT NOT NULL
        REFERENCES shop.customers(customer_id),
    status VARCHAR(20) NOT NULL
        CHECK (status IN ('NEW', 'CONFIRMED', 'CANCELLED')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE shop.order_items (
    order_id BIGINT NOT NULL
        REFERENCES shop.orders(order_id) ON DELETE CASCADE,
    product_id BIGINT NOT NULL
        REFERENCES shop.products(product_id),
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    unit_price NUMERIC(14,2) NOT NULL CHECK (unit_price >= 0),
    PRIMARY KEY (order_id, product_id)
);
```

### 5.1. Schema là namespace riêng

PostgreSQL có database chứa nhiều schema. Có thể có shop.products và reporting.products cùng tên nhưng khác namespace.

Trong ứng dụng, schema-qualify bảng quan trọng để tránh phụ thuộc search_path ngoài ý muốn.

### 5.2. Identity

GENERATED ALWAYS AS IDENTITY yêu cầu database cấp giá trị. Khi cần nhập ID tường minh, dùng cú pháp phù hợp như OVERRIDING SYSTEM VALUE và chỉ làm trong quy trình import có kiểm soát.

### 5.3. Constraint

CHECK, NOT NULL, UNIQUE và FOREIGN KEY bảo vệ bất biến ở database. Validation Java vẫn cần thiết cho trải nghiệm API, nhưng database phải bảo vệ dữ liệu trước mọi writer.

## 6. DDL MySQL

Tạo database với charset/collation rõ:

```sql
CREATE DATABASE shop
    CHARACTER SET utf8mb4
    COLLATE utf8mb4_0900_ai_ci;

USE shop;
```

Tạo bảng trên InnoDB:

```sql
CREATE TABLE customers (
    customer_id BIGINT NOT NULL AUTO_INCREMENT,
    email VARCHAR(255) NOT NULL,
    full_name VARCHAR(200) NOT NULL,
    created_at TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    PRIMARY KEY (customer_id),
    UNIQUE KEY uq_customers_email (email)
) ENGINE = InnoDB;

CREATE TABLE products (
    product_id BIGINT NOT NULL AUTO_INCREMENT,
    sku VARCHAR(64) NOT NULL,
    product_name VARCHAR(200) NOT NULL,
    unit_price DECIMAL(14,2) NOT NULL,
    active BOOLEAN NOT NULL DEFAULT TRUE,
    PRIMARY KEY (product_id),
    UNIQUE KEY uq_products_sku (sku),
    CONSTRAINT ck_products_price CHECK (unit_price >= 0)
) ENGINE = InnoDB;

CREATE TABLE inventory (
    product_id BIGINT NOT NULL,
    quantity_on_hand INT NOT NULL,
    updated_at TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    PRIMARY KEY (product_id),
    CONSTRAINT fk_inventory_product
        FOREIGN KEY (product_id) REFERENCES products(product_id),
    CONSTRAINT ck_inventory_quantity CHECK (quantity_on_hand >= 0)
) ENGINE = InnoDB;

CREATE TABLE orders (
    order_id BIGINT NOT NULL AUTO_INCREMENT,
    customer_id BIGINT NOT NULL,
    status VARCHAR(20) NOT NULL,
    created_at TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    PRIMARY KEY (order_id),
    KEY ix_orders_customer_created (customer_id, created_at),
    CONSTRAINT fk_orders_customer
        FOREIGN KEY (customer_id) REFERENCES customers(customer_id),
    CONSTRAINT ck_orders_status
        CHECK (status IN ('NEW', 'CONFIRMED', 'CANCELLED'))
) ENGINE = InnoDB;

CREATE TABLE order_items (
    order_id BIGINT NOT NULL,
    product_id BIGINT NOT NULL,
    quantity INT NOT NULL,
    unit_price DECIMAL(14,2) NOT NULL,
    PRIMARY KEY (order_id, product_id),
    CONSTRAINT fk_items_order
        FOREIGN KEY (order_id) REFERENCES orders(order_id) ON DELETE CASCADE,
    CONSTRAINT fk_items_product
        FOREIGN KEY (product_id) REFERENCES products(product_id),
    CONSTRAINT ck_items_quantity CHECK (quantity > 0),
    CONSTRAINT ck_items_price CHECK (unit_price >= 0)
) ENGINE = InnoDB;
```

### 6.1. AUTO_INCREMENT

MySQL dùng AUTO_INCREMENT cho cột số tự tăng, khác cú pháp IDENTITY của PostgreSQL.

### 6.2. InnoDB là điều kiện quan trọng

Bài toán dùng transaction, foreign key và row-level locking. Hãy chỉ định InnoDB hoặc xác nhận engine mặc định. Không giả định mọi storage engine của MySQL có semantics giống InnoDB.

### 6.3. CHECK và version

MySQL trước 8.0.16 không thực thi CHECK constraint như MySQL 8.0.16+. Nếu cần bất biến này, xác nhận version thực tế và bổ sung validation/trigger phù hợp cho môi trường cũ.

### 6.4. Database và schema

Trong MySQL, DATABASE và SCHEMA thường là hai tên cho cùng khái niệm. PostgreSQL có database chứa nhiều schema. Khác biệt này ảnh hưởng migration và namespace.

## 7. Đối chiếu schema

| Chủ đề | PostgreSQL | MySQL | Điều cần kiểm thử |
| --- | --- | --- | --- |
| ID | IDENTITY | AUTO_INCREMENT | Generated key, explicit ID |
| Decimal | NUMERIC | DECIMAL | Precision, scale, rounding |
| Boolean | BOOLEAN | TINYINT(1) alias | true/false/null mapping |
| Unicode | Server encoding UTF8 | utf8mb4 | Emoji, combining marks |
| JSON | JSON/JSONB | JSON | Operators và index |
| Date-time | TIMESTAMPTZ/TIMESTAMP | TIMESTAMP/DATETIME | Session timezone, range |
| Namespace | Database + schema | Database/schema đồng nghĩa | Qualified names |
| CHECK | Được thực thi | Được thực thi từ 8.0.16+ | Version |
| Index | B-tree mặc định, nhiều loại khác | InnoDB B-tree và loại hỗ trợ | Plan/workload |

Cùng contract nghiệp vụ không có nghĩa phải dùng cùng DDL. Tạo hai migration riêng và giữ cùng ý nghĩa dữ liệu.

## 8. Nạp dữ liệu mẫu

PostgreSQL:

```sql
INSERT INTO shop.customers(email, full_name)
VALUES
    ('an@example.test', 'Nguyễn An'),
    ('binh@example.test', 'Trần Bình');

INSERT INTO shop.products(sku, product_name, unit_price)
VALUES
    ('KB-001', 'Bàn phím cơ', 1250000.00),
    ('MS-002', 'Chuột không dây', 450000.00);

INSERT INTO shop.inventory(product_id, quantity_on_hand)
SELECT product_id,
       CASE sku
           WHEN 'KB-001' THEN 10
           WHEN 'MS-002' THEN 25
       END
FROM shop.products;
```

MySQL:

```sql
INSERT INTO customers(email, full_name)
VALUES
    ('an@example.test', 'Nguyễn An'),
    ('binh@example.test', 'Trần Bình');

INSERT INTO products(sku, product_name, unit_price)
VALUES
    ('KB-001', 'Bàn phím cơ', 1250000.00),
    ('MS-002', 'Chuột không dây', 450000.00);

INSERT INTO inventory(product_id, quantity_on_hand)
SELECT product_id,
       CASE sku
           WHEN 'KB-001' THEN 10
           WHEN 'MS-002' THEN 25
       END
FROM products;
```

Dữ liệu giống nhau để phép đối chiếu có ý nghĩa. Dùng miền email giả dành cho test, không dùng dữ liệu cá nhân thật.

## 9. Bài toán 1: tìm sản phẩm theo SKU

PostgreSQL:

```sql
SELECT product_id, sku, product_name, unit_price
FROM shop.products
WHERE sku = ?;
```

MySQL:

```sql
SELECT product_id, sku, product_name, unit_price
FROM products
WHERE sku = ?;
```

JDBC:

```java
String sql = """
    SELECT product_id, sku, product_name, unit_price
    FROM products
    WHERE sku = ?
    """;

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setString(1, sku);

    try (ResultSet rs = ps.executeQuery()) {
        while (rs.next()) {
            long id = rs.getLong("product_id");
            String name = rs.getString("product_name");
            BigDecimal price = rs.getBigDecimal("unit_price");
        }
    }
}
```

Trong PostgreSQL, dùng shop.products nếu search_path không được quản lý rõ. Trong MySQL, dùng database đã chọn hoặc qualify database.products.

Cả hai schema có unique index trên SKU. Equality query có thể tận dụng index nếu kiểu bind và collation tương thích. Hãy xác nhận bằng EXPLAIN thay vì giả định.

## 10. Bài toán 2: lọc đơn theo khách và thời gian

Yêu cầu: lấy đơn của một khách trong khoảng thời gian, mới nhất trước.

PostgreSQL:

```sql
SELECT order_id, status, created_at
FROM shop.orders
WHERE customer_id = ?
  AND created_at >= ?
  AND created_at < ?
ORDER BY created_at DESC, order_id DESC;
```

MySQL:

```sql
SELECT order_id, status, created_at
FROM orders
WHERE customer_id = ?
  AND created_at >= ?
  AND created_at < ?
ORDER BY created_at DESC, order_id DESC;
```

Dùng khoảng nửa mở [start, end) để tránh lỗi biên khi precision timestamp khác nhau.

Index gợi ý PostgreSQL:

```sql
CREATE INDEX orders_customer_created_idx
ON shop.orders(customer_id, created_at DESC, order_id DESC);
```

Index gợi ý MySQL:

```sql
CREATE INDEX ix_orders_customer_created
ON orders(customer_id, created_at DESC, order_id DESC);
```

Khả năng tận dụng index theo chiều sort và optimizer phụ thuộc version. Index cũ chỉ có hai cột vẫn có thể hữu ích; hãy đo workload thật.

Thêm order_id vào ORDER BY vì nhiều đơn có thể cùng created_at. Khóa tie-break giúp thứ tự xác định hơn.

## 11. Bài toán 3: phân trang

Cả PostgreSQL và MySQL đều hỗ trợ LIMIT/OFFSET:

PostgreSQL:

```sql
SELECT order_id, status, created_at
FROM shop.orders
ORDER BY created_at DESC, order_id DESC
LIMIT ? OFFSET ?;
```

MySQL:

```sql
SELECT order_id, status, created_at
FROM orders
ORDER BY created_at DESC, order_id DESC
LIMIT ? OFFSET ?;
```

JDBC bind pageSize và offset bằng setter số nguyên phù hợp.

### 11.1. Chi phí của trang sâu

Với offset lớn, database vẫn có thể phải đi qua nhiều hàng trước khi trả trang cần lấy. Với bảng lớn, keyset pagination thường phù hợp hơn.

### 11.2. Keyset pagination

Giả sử trang trước kết thúc ở lastCreatedAt và lastOrderId:

```sql
WHERE created_at < ?
   OR (created_at = ? AND order_id < ?)
ORDER BY created_at DESC, order_id DESC
LIMIT ?;
```

Predicate này dùng được trên cả hai hệ trong trường hợp cột NOT NULL và kiểu được bind đúng. Nếu created_at nullable, phải định nghĩa NULL ordering riêng; tốt hơn cột tạo đơn là NOT NULL.

### 11.3. Pagination và dữ liệu đồng thời

OFFSET có thể bỏ sót/lặp hàng khi dữ liệu thay đổi giữa các request. Keyset giảm một số vấn đề nhưng không tự tạo snapshot xuyên nhiều HTTP request. Xác định consistency requirement trước khi chọn.

## 12. Bài toán 4: lấy đơn và tổng tiền

Yêu cầu: hiển thị mỗi đơn với số dòng, tổng số lượng và tổng tiền.

Câu query gần như giống nhau:

```sql
SELECT
    o.order_id,
    o.status,
    COUNT(oi.product_id) AS line_count,
    COALESCE(SUM(oi.quantity), 0) AS total_quantity,
    COALESCE(SUM(oi.quantity * oi.unit_price), 0) AS total_amount
FROM orders o
LEFT JOIN order_items oi ON oi.order_id = o.order_id
WHERE o.customer_id = ?
GROUP BY o.order_id, o.status
ORDER BY o.order_id DESC;
```

PostgreSQL dùng shop.orders/shop.order_items hoặc schema qualification. MySQL dùng database hiện tại hoặc qualify tương ứng.

COUNT(oi.product_id) trả 0 cho đơn chưa có item; COUNT(*) có thể đếm hàng phía trái và trả 1 cho đơn rỗng.

Đọc total_amount bằng BigDecimal. Không chuyển sang double chỉ để tính hoặc format tiền.

PostgreSQL yêu cầu các cột SELECT không aggregate nằm trong GROUP BY hoặc được chứng minh phụ thuộc theo quy tắc của nó. MySQL với ONLY_FULL_GROUP_BY bật cũng kiểm tra GROUP BY/functional dependency. Đừng tắt mode chỉ để query thiếu nhóm chạy được.

## 13. Bài toán 5: tạo đơn và lấy ID vừa sinh

PostgreSQL có RETURNING:

```sql
INSERT INTO shop.orders(customer_id, status)
VALUES (?, 'NEW')
RETURNING order_id, created_at;
```

JDBC PostgreSQL:

```java
String sql = """
    INSERT INTO shop.orders(customer_id, status)
    VALUES (?, 'NEW')
    RETURNING order_id, created_at
    """;

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setLong(1, customerId);

    try (ResultSet rs = ps.executeQuery()) {
        if (rs.next()) {
            long orderId = rs.getLong("order_id");
            OffsetDateTime createdAt =
                rs.getObject("created_at", OffsetDateTime.class);
        }
    }
}
```

MySQL thường dùng generated keys qua JDBC:

```java
String sql = """
    INSERT INTO orders(customer_id, status)
    VALUES (?, 'NEW')
    """;

try (PreparedStatement ps = connection.prepareStatement(
        sql, Statement.RETURN_GENERATED_KEYS)) {

    ps.setLong(1, customerId);
    ps.executeUpdate();

    try (ResultSet keys = ps.getGeneratedKeys()) {
        if (keys.next()) {
            long orderId = keys.getLong(1);
        }
    }
}
```

Khác biệt thực hành:

- PostgreSQL RETURNING có thể trả nhiều cột trực tiếp từ INSERT/UPDATE/DELETE.
- MySQL Connector/J hỗ trợ getGeneratedKeys cho AUTO_INCREMENT.
- Không giả định cú pháp RETURNING PostgreSQL có trên mọi phiên bản MySQL.
- Nếu cần default value sau insert trong MySQL, query lại theo generated key trong cùng connection/transaction.

Không dùng SELECT MAX(order_id). Nhiều request có thể insert xen kẽ và MAX có thể trả ID của request khác.

## 14. Bài toán 6: UPSERT sản phẩm theo SKU

Yêu cầu: SKU chưa có thì insert; đã có thì cập nhật tên và giá.

PostgreSQL:

```sql
INSERT INTO shop.products(sku, product_name, unit_price, active)
VALUES (?, ?, ?, TRUE)
ON CONFLICT (sku)
DO UPDATE SET
    product_name = EXCLUDED.product_name,
    unit_price = EXCLUDED.unit_price;
```

MySQL:

```sql
INSERT INTO products(sku, product_name, unit_price, active)
VALUES (?, ?, ?, TRUE)
ON DUPLICATE KEY UPDATE
    product_name = ?,
    unit_price = ?;
```

JDBC MySQL bind lại các giá trị cho phần UPDATE:

```java
ps.setString(1, sku);
ps.setString(2, name);
ps.setBigDecimal(3, price);
ps.setString(4, name);
ps.setBigDecimal(5, price);
```

PostgreSQL cho phép chỉ rõ conflict target (sku) và dùng EXCLUDED để tham chiếu hàng đề xuất.

MySQL ON DUPLICATE KEY UPDATE được kích hoạt bởi conflict trên unique key/primary key; cú pháp không chỉ rõ conflict target theo cùng cách. Nếu bảng có nhiều unique key, phải hiểu key nào có thể kích hoạt update.

Một số ví dụ MySQL cũ dùng VALUES(column) trong phần update; cú pháp này đã deprecated trong MySQL 8.0.20. Dùng row alias theo version hoặc bind giá trị update rõ như ví dụ trên.

UPSERT không tự làm mọi nghiệp vụ idempotent. Nếu update là tăng tồn kho thêm 1, retry có thể cộng hai lần. Dùng request ID/idempotency key cho nghiệp vụ có side effect.

## 15. Bài toán 7: cập nhật tồn kho có điều kiện

Yêu cầu: trừ số lượng requested nếu tồn kho hiện tại đủ.

Câu UPDATE giống nhau:

```sql
UPDATE inventory
SET quantity_on_hand = quantity_on_hand - ?,
    updated_at = CURRENT_TIMESTAMP
WHERE product_id = ?
  AND quantity_on_hand >= ?;
```

JDBC:

```java
ps.setInt(1, requestedQuantity);
ps.setLong(2, productId);
ps.setInt(3, requestedQuantity);

int changed = ps.executeUpdate();

if (changed != 1) {
    throw new InsufficientInventoryException(productId);
}
```

### 15.1. Vì sao predicate nằm trong UPDATE?

Mẫu read-then-write ngây thơ:

1. SELECT quantity.
2. Java thấy đủ hàng.
3. Transaction khác cũng đọc thấy đủ.
4. Cả hai cùng trừ hàng.

Conditional UPDATE kiểm tra điều kiện và thay đổi trong một statement. Database điều phối khóa để không cho cả hai transaction cùng trừ vượt số lượng theo semantics của engine.

### 15.2. Một statement atomic chưa đủ cho toàn workflow

UPDATE tồn kho riêng lẻ có thể atomic, nhưng xác nhận đơn còn gồm kiểm tra order, cập nhật trạng thái và xử lý nhiều sản phẩm. Đặt toàn bộ workflow trong transaction.

## 16. Bài toán 8: xác nhận đơn trong một transaction

Workflow:

1. Bắt đầu transaction.
2. Đọc các dòng của đơn.
3. Trừ tồn kho có điều kiện cho từng sản phẩm.
4. Nếu một dòng không đủ hàng, rollback.
5. Cập nhật trạng thái đơn thành CONFIRMED.
6. Commit.

Pseudocode Java/JDBC:

```java
connection.setAutoCommit(false);

try {
    List<OrderLine> lines = loadOrderLines(connection, orderId);

    if (lines.isEmpty()) {
        throw new IllegalStateException("Order has no items");
    }

    for (OrderLine line : lines) {
        int changed = decrementInventory(
            connection,
            line.productId(),
            line.quantity()
        );

        if (changed != 1) {
            throw new InsufficientInventoryException(line.productId());
        }
    }

    int changed = confirmOrder(connection, orderId);

    if (changed != 1) {
        throw new IllegalStateException("Order cannot be confirmed");
    }

    connection.commit();
} catch (Exception ex) {
    connection.rollback();
    throw ex;
}
```

Đây là pseudocode minh họa. Production cần xử lý SQLException, transaction manager, restore autocommit theo đúng chủ sở hữu connection và phân loại lỗi retry.

### 16.1. Ngăn confirm cùng đơn hai lần

Có thể khóa hàng order:

```sql
SELECT order_id, status
FROM orders
WHERE order_id = ?
FOR UPDATE;
```

Sau khi lấy lock, kiểm tra status là NEW. PostgreSQL và InnoDB hỗ trợ locking read trong transaction.

Một lựa chọn bổ sung là cập nhật có điều kiện:

```sql
UPDATE orders
SET status = 'CONFIRMED'
WHERE order_id = ?
  AND status = 'NEW';
```

Kiểm tra update count bằng 1.

### 16.2. Thứ tự lock và deadlock

Nếu hai đơn chứa cùng sản phẩm theo thứ tự khác nhau, transaction có thể khóa product A rồi B, còn transaction kia khóa B rồi A. Deadlock có thể xảy ra.

Giảm rủi ro bằng cách xử lý product theo thứ tự ID tăng dần, giữ transaction ngắn và retry toàn transaction khi gặp lỗi deadlock phù hợp.

## 17. Isolation level: cùng tên không có nghĩa hoàn toàn giống nhau

PostgreSQL và MySQL InnoDB có READ UNCOMMITTED, READ COMMITTED, REPEATABLE READ và SERIALIZABLE. Tuy nhiên semantics thực tế và mặc định khác nhau.

- PostgreSQL mặc định thường là READ COMMITTED.
- MySQL InnoDB mặc định thường là REPEATABLE READ.
- Cấu hình server/session có thể thay đổi mặc định.
- Locking read và consistent read không nhất thiết nhìn cùng snapshot.

### 17.1. PostgreSQL READ COMMITTED

Mỗi statement trong transaction thường nhìn snapshot mới tại thời điểm statement bắt đầu. Hai SELECT liên tiếp có thể thấy dữ liệu transaction khác đã commit ở giữa.

### 17.2. PostgreSQL REPEATABLE READ

Dùng snapshot ổn định cho transaction theo semantics PostgreSQL. Một số xung đột ghi có thể dẫn đến serialization failure.

### 17.3. MySQL InnoDB REPEATABLE READ

Consistent read thông thường trong transaction dùng snapshot theo quy tắc InnoDB. Locking reads như SELECT ... FOR UPDATE có semantics khác và có thể dùng record/gap/next-key locks.

### 17.4. So sánh đúng loại đọc

Test riêng:

- Plain SELECT.
- SELECT FOR UPDATE.
- UPDATE có predicate.
- Range scan.
- Insert vào khoảng khóa.
- Hai transaction cùng sửa một hàng.

Đừng chỉ đổi isolation name rồi kết luận hai engine có behavior giống nhau.

## 18. Locking reads: SELECT FOR UPDATE

PostgreSQL:

```sql
BEGIN;

SELECT quantity_on_hand
FROM shop.inventory
WHERE product_id = ?
FOR UPDATE;

-- Kiểm tra và cập nhật trong cùng transaction

COMMIT;
```

MySQL InnoDB:

```sql
START TRANSACTION;

SELECT quantity_on_hand
FROM inventory
WHERE product_id = ?
FOR UPDATE;

-- Kiểm tra và cập nhật trong cùng transaction

COMMIT;
```

Row lock thường được giữ tới COMMIT/ROLLBACK. Không lấy lock rồi gọi API bên ngoài hoặc chờ người dùng trong khi transaction còn mở.

Phạm vi lock có thể khác. InnoDB có thể dùng record lock, gap lock hoặc next-key lock tùy isolation/index/query. PostgreSQL có các row-level lock modes và MVCC. Kế hoạch truy cập ảnh hưởng vùng phải khóa/chờ.

Nếu WHERE không có index phù hợp, engine có thể phải scan nhiều hàng và gây chờ rộng hơn dự kiến. Index là một phần của concurrency design.

## 19. Deadlock và retry

Deadlock là tình huống các transaction chờ nhau theo chu trình. Database thường phát hiện và hủy một transaction làm victim.

- PostgreSQL SQLSTATE 40P01: deadlock detected.
- PostgreSQL SQLSTATE 40001: serialization failure.
- MySQL/InnoDB thường trả error 1213 cho deadlock và 1205 cho lock wait timeout; SQLState/driver mapping cần kiểm tra.

### 19.1. Retry toàn transaction

Khi transaction bị rollback do deadlock, bắt đầu transaction mới và chạy lại toàn bộ logic. Không tiếp tục từ statement bị lỗi như thể các bước trước vẫn còn.

### 19.2. Chỉ retry lỗi phù hợp

Không retry validation error, foreign key violation hoặc insufficient inventory. Những lỗi này thường cần thay đổi input/trạng thái nghiệp vụ.

### 19.3. Idempotency khi mất phản hồi

Nếu client không biết COMMIT thành công hay không vì mất kết nối, retry có thể tạo đơn hai lần. Dùng request ID duy nhất hoặc idempotency key có unique constraint để truy vấn kết quả đã thực hiện.

## 20. Bài toán 9: NULL và optional filter

Yêu cầu: lọc khách theo email nhưng email có thể không được gửi.

Phải xác định null có nghĩa gì:

- Không gửi filter: bỏ điều kiện email.
- Tìm khách chưa có email: dùng IS NULL.
- Chuỗi rỗng: một giá trị riêng nếu DBMS phân biệt nó với NULL.

PostgreSQL và MySQL đều dùng SQL NULL semantics: email = NULL không tìm hàng có email NULL.

Optional filter có thể viết:

```sql
WHERE (? IS NULL OR email = ?)
```

Nếu bind NULL vào cả hai vị trí, vế đầu TRUE nên bỏ filter. Nếu bind email, vế đầu FALSE và vế thứ hai so sánh. Cần kiểm tra type inference của placeholder và query plan trên đúng driver/DBMS.

Tìm NULL rõ ràng:

```sql
WHERE email IS NULL
```

Không bind NULL vào email = ? rồi kỳ vọng tương đương.

PostgreSQL và MySQL đều phân biệt chuỗi rỗng với SQL NULL. Oracle SQL truyền thống có quy tắc khác; không suy rộng từ hai hệ này.

## 21. Bài toán 10: thời gian và timezone

Đơn hàng cần created_at là một instant.

PostgreSQL:

```sql
created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
```

MySQL:

```sql
created_at TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6)
```

### 21.1. PostgreSQL TIMESTAMPTZ

PostgreSQL lưu thời điểm theo semantics instant; hiển thị theo TimeZone của session. Nó không giữ tên timezone/offset ban đầu như thuộc tính riêng của giá trị.

### 21.2. MySQL TIMESTAMP

MySQL TIMESTAMP chuyển đổi giữa timezone session và UTC khi lưu/đọc theo quy tắc server. Giá trị hiển thị phụ thuộc session time_zone. Phạm vi hỗ trợ của TIMESTAMP có giới hạn theo version.

### 21.3. MySQL DATETIME

DATETIME lưu thành phần ngày giờ mà không chuyển timezone như TIMESTAMP. Nếu dùng DATETIME để lưu UTC, ứng dụng phải thống nhất quy ước UTC và không diễn giải nó như local time.

### 21.4. JDBC mapping

Với PostgreSQL TIMESTAMPTZ, OffsetDateTime thường là mapping phù hợp theo driver.

Với MySQL Connector/J, kiểm tra mapping Timestamp, LocalDateTime, OffsetDateTime, serverTimezone và cấu hình driver của phiên bản đang dùng. Không giả định hai driver xử lý mọi java.time giống nhau.

### 21.5. Kiểm thử timezone

Insert một instant cố định, ví dụ 2026-11-14T02:00:00Z, rồi đọc ở session UTC và Asia/Ho_Chi_Minh. So sánh instant theo contract. Test mốc gần nửa đêm, precision microseconds và DST nếu hệ thống phục vụ vùng có DST.

## 22. Bài toán 11: Boolean

PostgreSQL có kiểu BOOLEAN thật:

```sql
active BOOLEAN NOT NULL DEFAULT TRUE
```

MySQL BOOLEAN là alias của TINYINT(1). Giá trị lưu thường là 0/1, nhưng TINYINT(1) không tự tạo constraint chỉ nhận 0 và 1.

JDBC dùng setBoolean/getBoolean cho mapping đã kiểm thử. Với cột nullable, primitive boolean không thể giữ SQL NULL; dùng wasNull hoặc Boolean wrapper.

Không bind chuỗi "true"/"false" như VARCHAR cho cột Boolean. Dùng setter typed.

## 23. Bài toán 12: JSON metadata cho đơn hàng

Metadata ví dụ:

```json
{
  "channel": "mobile",
  "campaign": "summer",
  "gift": true
}
```

PostgreSQL:

```sql
ALTER TABLE shop.orders
ADD COLUMN metadata JSONB;
```

MySQL:

```sql
ALTER TABLE orders
ADD COLUMN metadata JSON;
```

### 23.1. PostgreSQL JSONB

JSONB lưu dữ liệu ở dạng binary representation phù hợp cho thao tác/index JSON; không giữ nguyên whitespace hoặc thứ tự key như JSON text ban đầu.

```sql
SELECT order_id
FROM shop.orders
WHERE metadata ->> 'channel' = 'mobile';
```

### 23.2. MySQL JSON

MySQL có kiểu JSON native, xác thực JSON khi ghi và cung cấp JSON functions:

```sql
SELECT order_id
FROM orders
WHERE JSON_UNQUOTE(JSON_EXTRACT(metadata, '$.channel')) = 'mobile';
```

### 23.3. Index JSON

PostgreSQL có GIN index cho nhiều truy vấn JSONB và expression index cho key cụ thể. MySQL thường dùng generated column hoặc functional index phù hợp biểu thức JSON, tùy version/query.

Không copy index JSON của PostgreSQL sang MySQL. Thiết kế theo operator/query thực tế.

Nếu một field thường xuyên JOIN, filter, sort, unique hoặc có constraint nghiệp vụ, cân nhắc cột quan hệ riêng. JSON phù hợp metadata linh hoạt, không thay schema cho mọi dữ liệu.

## 24. Bài toán 13: tạo index và đọc query plan

Query cần tối ưu:

```sql
SELECT order_id, status, created_at
FROM orders
WHERE customer_id = ?
  AND created_at >= ?
ORDER BY created_at DESC, order_id DESC
LIMIT 50;
```

Index tổng hợp gợi ý:

```sql
CREATE INDEX ix_orders_customer_created
ON orders(customer_id, created_at DESC, order_id DESC);
```

PostgreSQL cần qualify bảng:

```sql
CREATE INDEX orders_customer_created_idx
ON shop.orders(customer_id, created_at DESC, order_id DESC);
```

### 24.1. PostgreSQL EXPLAIN

```sql
EXPLAIN
SELECT order_id, status, created_at
FROM shop.orders
WHERE customer_id = 10
  AND created_at >= TIMESTAMPTZ '2026-01-01 00:00:00+00'
ORDER BY created_at DESC, order_id DESC
LIMIT 50;
```

EXPLAIN ANALYZE thực thi query để đo thời gian và số hàng thực tế. Không chạy tùy tiện trên statement ghi dữ liệu nếu không hiểu tác động; DML có thể thực sự thay đổi dữ liệu nếu không được rollback an toàn.

### 24.2. MySQL EXPLAIN

```sql
EXPLAIN
SELECT order_id, status, created_at
FROM orders
WHERE customer_id = 10
  AND created_at >= '2026-01-01 00:00:00'
ORDER BY created_at DESC, order_id DESC
LIMIT 50;
```

MySQL 8.0.18+ có EXPLAIN ANALYZE cho query được hỗ trợ; lệnh thực thi SELECT và báo thông tin runtime theo format MySQL.

### 24.3. So sánh điều gì?

- Estimated rows và actual rows.
- Index được chọn.
- Số hàng phải đọc.
- Sort/filesort.
- Filter còn lại.
- Loop count.
- I/O và thời gian.
- Index-only/covering access nếu có.

Một bảng chỉ có 100 hàng có thể full scan nhanh hơn index scan. Dùng dữ liệu và phân bố đại diện, cập nhật statistics rồi mới so sánh.

## 25. Index tổng hợp và thứ tự cột

Index (customer_id, created_at) thường hữu ích khi query lọc customer_id và khoảng created_at. Index (created_at, customer_id) có thể không phục vụ cùng workload hiệu quả như index trên.

### 25.1. Leftmost prefix trong MySQL

Composite B-tree index MySQL thường hữu ích theo leftmost prefix. Index (a,b,c) có thể phục vụ điều kiện bắt đầu từ a hoặc a và b, nhưng không tự động tối ưu query chỉ lọc c.

### 25.2. PostgreSQL multicolumn index

PostgreSQL B-tree multicolumn index cũng hiệu quả nhất khi điều kiện hạn chế các cột đầu. Planner có thêm lựa chọn bitmap/index scan, nhưng thứ tự cột vẫn quan trọng.

### 25.3. Partial index PostgreSQL

PostgreSQL hỗ trợ partial index:

```sql
CREATE INDEX orders_new_customer_idx
ON shop.orders(customer_id, created_at)
WHERE status = 'NEW';
```

MySQL không có partial index cùng cú pháp/tính năng tổng quát. Có thể cân nhắc generated column, composite index hoặc thiết kế khác.

### 25.4. Index có chi phí ghi

Mỗi index thêm storage và chi phí INSERT/UPDATE/DELETE. Không tạo index cho mọi cột chỉ vì có thể filter theo cột đó.

## 26. DDL và migration: khác biệt có ảnh hưởng trực tiếp

PostgreSQL hỗ trợ transactional DDL cho nhiều thao tác schema thông thường:

```sql
BEGIN;

ALTER TABLE shop.products
ADD COLUMN description TEXT;

ROLLBACK;
```

Trong trường hợp thông thường, cột vừa thêm được rollback.

MySQL có nhiều DDL gây implicit commit. MySQL 8.0 có atomic DDL cho nhiều thao tác được hỗ trợ, nhưng điều đó không biến ALTER TABLE thành DDL có thể rollback theo transaction người dùng.

### 26.1. Migration runner không xóa khác biệt engine

Framework có thể mở transaction quanh migration, nhưng MySQL server vẫn implicit commit với DDL tương ứng.

### 26.2. Tách migration theo dialect

- PostgreSQL: nhiều DDL transactional; CREATE INDEX CONCURRENTLY là ngoại lệ không chạy trong transaction block.
- MySQL: DDL có implicit commit; kiểm tra algorithm/lock, version và trạng thái sau lỗi.

### 26.3. Recovery

Nếu migration MySQL chạy ALTER TABLE rồi lỗi ở bước index, kiểm tra schema thực tế trước khi chạy lại. Không giả định rollback đã xóa cột.

## 27. Namespace, quote và identifier

PostgreSQL:

```sql
SELECT *
FROM shop.products;
```

MySQL:

```sql
SELECT *
FROM shop.products;
```

Cú pháp nhìn giống nhau nhưng ý nghĩa namespace khác: PostgreSQL shop là schema trong database; MySQL shop thường là database/schema được chọn.

PostgreSQL quote identifier bằng dấu nháy kép:

```sql
SELECT "productName"
FROM shop.products;
```

MySQL dùng backtick:

```sql
SELECT \`productName\`
FROM products;
```

MySQL có thể dùng double quote cho identifier khi bật ANSI_QUOTES; không giả định mặc định.

Dùng lowercase ASCII snake_case cho schema/table/column. Tránh identifier có dấu, khoảng trắng, từ khóa hoặc mixed-case cần quote liên tục.

PreparedStatement bind giá trị, không bind identifier. Dynamic table/column cần whitelist code cố định và quoting theo dialect.

## 28. SQL mode của MySQL và tính nghiêm ngặt

SQL mode ảnh hưởng cách xử lý dữ liệu và cú pháp. Ví dụ ONLY_FULL_GROUP_BY, strict mode và ANSI_QUOTES.

```sql
SELECT @@sql_mode;
```

Không dựa vào môi trường developer đang chạy mode dễ dãi nếu production bật strict mode.

Nếu insert giá trị quá dài hoặc sai kiểu, sửa validation/schema/input thay vì hạ SQL mode để database âm thầm cắt hoặc chuyển kiểu ngoài ý muốn.

PostgreSQL có quy tắc type/constraint khác; không có một biến SQL mode tương đương toàn bộ MySQL.

## 29. JDBC: dùng chung API, tách SQL dialect

Java có thể dùng cùng kiểu JDBC cho hai DBMS:

```java
try (PreparedStatement ps = connection.prepareStatement(
        "SELECT product_id, product_name, unit_price FROM products WHERE sku = ?")) {

    ps.setString(1, sku);

    try (ResultSet rs = ps.executeQuery()) {
        if (rs.next()) {
            long id = rs.getLong("product_id");
            String name = rs.getString("product_name");
            BigDecimal price = rs.getBigDecimal("unit_price");
        }
    }
}
```

Nhưng connection URL, driver, schema qualification và một số query khác nhau.

PostgreSQL JDBC URL:

```text
jdbc:postgresql://localhost:5432/shopdb
```

MySQL Connector/J URL:

```text
jdbc:mysql://localhost:3306/shop
```

Cấu hình timezone, TLS, credentials và pool properties theo môi trường; không hardcode mật khẩu vào source.

### 29.1. Kiểu tiền

Dùng BigDecimal và setBigDecimal cho NUMERIC/DECIMAL. Đọc bằng getBigDecimal. Không dùng double cho giá/tiền.

### 29.2. Kiểu thời gian

Dùng OffsetDateTime/Instant theo contract domain, rồi viết mapper riêng nếu driver/DBMS khác nhau. Không để default timezone của máy quyết định nghiệp vụ.

### 29.3. Boolean

Dùng setBoolean/getBoolean sau khi xác nhận mapping. Cột nullable cần Boolean wrapper hoặc wasNull.

### 29.4. Generated keys

PostgreSQL có thể dùng RETURNING. MySQL thường dùng Statement.RETURN_GENERATED_KEYS và getGeneratedKeys.

### 29.5. Exception mapping

Cả hai driver ném SQLException, nhưng SQLState/vendor code/message có thể khác. Map lỗi constraint, deadlock và connection theo loại lỗi; tránh parse message text làm hợp đồng.

## 30. Repository pattern và dialect boundary

Không rải nhánh if database ở khắp business service. Có thể tách interface:

```java
interface OrderRepository {
    long createOrder(long customerId);
    List<OrderSummary> findOrders(long customerId);
    boolean reserveInventory(long productId, int quantity);
}
```

Hai implementation:

- PostgresOrderRepository: RETURNING, schema qualification và cú pháp PostgreSQL khi hữu ích.
- MySqlOrderRepository: generated keys, database qualification và cú pháp MySQL.

Business service chỉ gọi interface và quản lý transaction qua abstraction phù hợp.

### 30.1. Khi nào dùng SQL chung?

CRUD đơn giản, filter, JOIN và phần lớn transaction DML có thể dùng chung SQL nếu schema/types thống nhất.

### 30.2. Khi nào tách dialect?

- Upsert.
- Generated key retrieval.
- JSON operators/index.
- DDL/migration.
- Date/time functions.
- Locking/optimizer hints.
- Full-text search.
- Specialized index.
- Pagination phức tạp.

### 30.3. Không tạo abstraction quá sớm

Một interface chung cho mọi SQL feature có thể che khác biệt quan trọng. Tách theo use case; giữ dialect-specific SQL ở nơi có thể kiểm thử.

## 31. Kiểm thử cùng một contract trên hai database

Hai implementation phải chạy cùng test cases và cùng dữ liệu fixture.

Ví dụ các hành vi cần xác nhận:

- Tạo order cho customer tồn tại.
- Từ chối customer không tồn tại.
- Lưu chính xác decimal.
- Lọc thời gian theo khoảng nửa mở.
- Không oversell tồn kho.
- Rollback khi xác nhận đơn thất bại giữa chừng.
- Generated ID được trả đúng.
- Upsert SKU theo contract.
- Unicode round-trip không bị biến dạng.

Có thể xây abstract contract test hoặc test factory để chạy cùng assertions trên hai repository.

### 31.1. Chạy trên database thật

- PostgreSQL container + PostgreSQL JDBC driver.
- MySQL container + MySQL Connector/J.
- Cùng seed data.
- Cùng assertions nghiệp vụ.
- Cùng timezone và isolation assumptions được ghi rõ.
- Pin version trong CI.

Mock JDBC có thể xác minh setter được gọi, nhưng không tái tạo đầy đủ SQL dialect, lock, transaction, collation và query plan.

### 31.2. Test concurrency

Tạo hai transaction cùng đặt sản phẩm gần hết hàng. Xác nhận tổng quantity thành công không vượt tồn kho ban đầu.

Dùng barrier/latch để điều phối cạnh tranh có kiểm soát; không dùng sleep ngẫu nhiên làm cơ chế đồng bộ.

## 32. Test case: không bán vượt tồn kho

Giả sử còn 5 sản phẩm. Hai request đồng thời đều muốn mua 4.

Kết quả hợp lệ:

- Một request thành công và một request thất bại; hoặc
- Một request xử lý trước, request sau thấy tồn kho còn 1 và thất bại.

Kết quả không hợp lệ: cả hai thành công và tồn kho âm hoặc order tổng cộng 8.

SQL:

```sql
UPDATE inventory
SET quantity_on_hand = quantity_on_hand - 4
WHERE product_id = 1
  AND quantity_on_hand >= 4;
```

Mỗi transaction kiểm tra update count. Chỉ một transaction có thể giảm từ 5 xuống 1; transaction còn lại sau khi chờ sẽ không còn thỏa điều kiện.

Test cả rollback: nếu tồn kho đã giảm nhưng cập nhật order status thất bại, rollback phải khôi phục tồn kho trong cùng transaction.

Ghi nhận thời gian chờ, deadlock và timeout. Test đúng không chỉ là cuối cùng tồn kho không âm mà còn phải biết ứng dụng xử lý retry/failed request ra sao.

## 33. Test case: tiền chính xác

Tạo sản phẩm giá 0.10 và số lượng 3:

```sql
SELECT unit_price * 3
FROM products
WHERE sku = 'TEST-DECIMAL';
```

Kết quả kỳ vọng là 0.30 theo NUMERIC/DECIMAL.

Java:

```java
BigDecimal expected = new BigDecimal("0.30");
BigDecimal actual = rs.getBigDecimal(1);

assertEquals(0, expected.compareTo(actual));
```

Dùng compareTo để so sánh giá trị số nếu scale có thể khác. Nếu scale là một phần của contract, assert thêm scale riêng.

## 34. Test case: Unicode và collation

Seed hai giá trị:

- Nguyễn An
- Nguyen An

Test riêng:

- Round-trip giữ nguyên chuỗi.
- Equality theo collation được chọn.
- Search không dấu theo chính sách sản phẩm.
- Unique constraint có/không cho phép cả hai.
- ORDER BY theo locale.
- JDBC đọc lại không mojibake.

Không kỳ vọng PostgreSQL và MySQL trả cùng equality/sort chỉ vì hai cột đều VARCHAR. Ghi rõ charset/collation và semantics cần thiết.

## 35. Test case: NULL và empty string

Chạy các giá trị:

| Input | Ý nghĩa cần xác nhận |
| --- | --- |
| Java null | SQL NULL |
| Chuỗi rỗng | Giá trị rỗng |
| Một dấu cách | Giá trị có khoảng trắng |
| Chuỗi NULL | Literal text |
| Unicode text | Giá trị text |
| NFD string | Dạng Unicode phân rã |

PostgreSQL và MySQL phân biệt chuỗi rỗng với NULL. Test contract để tránh ứng dụng vô tình gộp hai trạng thái.

## 36. Test case: date/time

Dùng instant cố định, ví dụ 2026-11-14T02:00:00Z, rồi:

1. Insert từ Java.
2. Đọc ở session timezone UTC.
3. Đọc ở session timezone Asia/Ho_Chi_Minh.
4. So sánh instant theo contract.
5. Kiểm tra boundary query [start, end).
6. Test precision microseconds và rounding/truncation của driver.

PostgreSQL TIMESTAMPTZ và MySQL TIMESTAMP/DATETIME không thể coi là hoàn toàn tương đương. Test session timezone lẫn driver configuration.

## 37. Test case: upsert và retry

Gửi cùng SKU hai lần với cùng payload:

- Lần đầu insert.
- Lần hai update theo contract.

Kiểm tra một hàng duy nhất tồn tại và dữ liệu đúng.

Sau đó test request lặp có side effect, ví dụ tăng inventory hoặc tạo order. UPSERT theo unique key không thay thế idempotency key cho nghiệp vụ có thể bị retry.

## 38. Test case: lỗi và constraint

Cố tình tạo lỗi trong database test:

- Insert email duplicate.
- Insert order tham chiếu customer không tồn tại.
- Insert quantity âm.
- Insert giá âm.
- Update tồn kho không đủ.
- Insert NULL vào NOT NULL.

Ghi nhận:

- SQLState.
- Vendor error code.
- Constraint name nếu driver cung cấp.
- Transaction còn usable không.
- Có cần rollback toàn transaction không.
- Lỗi có thể retry không.

Không assert toàn bộ message text vì message có thể thay đổi theo version/ngôn ngữ.

## 39. Ma trận đối chiếu theo bài toán

| Bài toán | PostgreSQL | MySQL 8.0+/InnoDB | Điểm cần kiểm thử |
| --- | --- | --- | --- |
| Tạo ID | IDENTITY | AUTO_INCREMENT | Generated key |
| Tìm SKU | Equality + schema | Equality + database | Collation/index |
| Tổng tiền | NUMERIC | DECIMAL | BigDecimal/scale |
| Boolean | BOOLEAN | TINYINT(1) alias | Null/mapping |
| Ngày giờ | TIMESTAMPTZ | TIMESTAMP/DATETIME | Timezone/precision |
| JSON | JSONB/JSON | JSON | Operators/index |
| Upsert | ON CONFLICT | ON DUPLICATE KEY UPDATE | Conflict target |
| Lấy ID insert | RETURNING | getGeneratedKeys | JDBC driver |
| Lock row | FOR UPDATE | FOR UPDATE | Isolation/lock scope |
| DDL rollback | Nhiều DDL transactional | Nhiều DDL implicit commit | Migration recovery |
| Unicode | UTF8 + collation | utf8mb4 + collation | Equality/sort |
| Partial index | Có | Không cùng tính năng/cú pháp | Thiết kế thay thế |
| Namespace | Database/schema | Database/schema đồng nghĩa | Qualified names |

## 40. Quy trình thực hành từ đầu đến cuối

1. Ghi rõ DBMS/version/driver.
2. Viết hợp đồng nghiệp vụ và bất biến.
3. Chọn kiểu dữ liệu theo ý nghĩa.
4. Tạo DDL riêng cho từng hệ quản trị.
5. Nạp cùng fixture.
6. Viết query với cùng kết quả kỳ vọng.
7. Bind parameter qua JDBC.
8. Test NULL, Unicode, decimal và timestamp.
9. Test transaction và hai request đồng thời.
10. Thêm index dựa trên workload.
11. So sánh EXPLAIN/query plan.
12. Thử migration và xử lý lỗi trong database test.
13. Chạy cùng contract test suite trên cả hai.
14. Ghi lại điểm khác biệt cần giữ trong dialect layer.

Bảng ghi kết quả thực nghiệm:

| Hạng mục | PostgreSQL | MySQL | Kết luận |
| --- | --- | --- | --- |
| Phiên bản | Điền khi chạy | Điền khi chạy | Có thể tái lập |
| DDL | Kết quả thực tế | Kết quả thực tế | Dialect |
| Transaction | Kết quả thực tế | Kết quả thực tế | Atomicity |
| Unicode | Kết quả thực tế | Kết quả thực tế | Charset/collation |
| Query plan | Kết quả thực tế | Kết quả thực tế | Index/optimizer |
| JDBC mapping | Kết quả thực tế | Kết quả thực tế | Driver |
| Concurrency | Kết quả thực tế | Kết quả thực tế | Lock/isolation |

Không điền số liệu benchmark giả. Đo trên cùng máy, cùng dữ liệu, cùng workload và ghi rõ cấu hình.

## 41. Những sai lầm khi đối chiếu hai hệ quản trị

**Chỉ so sánh cú pháp mà không so sánh semantics.** Hai câu SQL có thể trông giống nhau nhưng timezone, collation, NULL hoặc transaction behavior khác.

**Dùng cùng DDL cho cả hai.** Schema cần giữ cùng contract, nhưng identity, JSON, namespace và timestamp có thể cần dialect riêng.

**Chỉ test happy path.** Cần test constraint violation, deadlock, rollback, Unicode normalization, NULL và mất kết nối sau commit.

**Dùng dữ liệu quá nhỏ để kết luận hiệu năng.** Index có thể không được chọn trên vài chục hàng. Cần dữ liệu và phân bố đại diện.

**Dùng một transaction giả định cho mọi DDL.** PostgreSQL và MySQL khác nhau về transactional DDL/implicit commit. Migration runner không xóa khác biệt đó.

**Chuyển mọi khác biệt vào service layer.** Business service không nên chứa SQL dialect rải rác. Tách repository/dialect có chủ đích.

**Chỉ kiểm thử một driver.** JDBC là API chung nhưng mapping, generated keys, timezone và error codes phụ thuộc driver/version.

## 42. Khi nào dùng một hệ quản trị và khi nào cần hỗ trợ cả hai?

Chọn database dựa trên yêu cầu sản phẩm và năng lực vận hành:

- Hệ sinh thái và kỹ năng đội ngũ.
- Dạng truy vấn và extension cần dùng.
- Workload đọc/ghi và concurrency.
- Yêu cầu HA, backup, replication và recovery.
- Khả năng vận hành, monitoring và migration.
- Chi phí hosting/licensing.
- Tích hợp, tooling và cloud platform.
- Yêu cầu portability và chiến lược thay đổi tương lai.

Nếu chỉ triển khai một DBMS, tối ưu cho semantics của hệ đó thường đơn giản hơn.

Nếu sản phẩm phải hỗ trợ hai DBMS, xác định contract chung, viết dialect riêng cho phần khác biệt và chạy integration/contract tests trên cả hai. Đừng ép mọi tính năng thành SQL portable nếu điều đó làm mất correctness hoặc hiệu năng.

## 43. Checklist trước khi kết luận hai hệ quản trị tương đương

- [ ] Cùng schema contract và constraints nghiệp vụ.
- [ ] Cùng dữ liệu fixture và kết quả kỳ vọng.
- [ ] Kiểu tiền chính xác và mapping BigDecimal.
- [ ] Boolean và NULL giữ đúng ý nghĩa.
- [ ] Timezone/precision được định nghĩa và test.
- [ ] Charset/collation và Unicode behavior được test.
- [ ] Generated keys được lấy đúng cách.
- [ ] Upsert không gây side effect khi retry.
- [ ] Transaction rollback toàn nghiệp vụ khi có lỗi.
- [ ] Concurrency không oversell hoặc double-confirm.
- [ ] Isolation và lock behavior được hiểu.
- [ ] Index/query plan được đo trên dữ liệu đại diện.
- [ ] Migration recovery phù hợp transactional DDL.
- [ ] JDBC driver/version được pin và test.
- [ ] SQLState/vendor error được map có chủ đích.
- [ ] Không dựa vào tính năng chưa hỗ trợ ở version production.

## 44. Bài tập thực hành có lời giải

Các bài tập dùng cùng bài toán cửa hàng. Chạy trên database test riêng và ghi lại version/driver.

### Bài 1. Tạo bảng products trên hai DBMS

**Yêu cầu:** Tạo product ID tự tăng, SKU unique, giá không âm.

**Đáp án:** PostgreSQL dùng IDENTITY và NUMERIC; MySQL dùng AUTO_INCREMENT, DECIMAL, InnoDB và CHECK trên version thực thi CHECK.

### Bài 2. Vì sao MySQL cần InnoDB?

**Đáp án:** Bài toán dùng transaction, foreign key và row locking. Không giả định engine khác có semantics tương tự.

### Bài 3. Tìm SKU bằng PreparedStatement

**Đáp án:** Cả hai dùng WHERE sku = ? và setString(1, sku). Tên bảng/schema qualification tùy hệ quản trị.

### Bài 4. Tính tổng đơn

**Đáp án:** Dùng SUM(quantity * unit_price), đọc bằng BigDecimal. Dùng LEFT JOIN nếu muốn hiển thị cả đơn chưa có dòng.

### Bài 5. Vì sao dùng DECIMAL/NUMERIC cho tiền?

**Đáp án:** Hai kiểu lưu số thập phân chính xác theo precision/scale; float/double có sai số biểu diễn nhị phân.

### Bài 6. Lấy ID vừa insert ở PostgreSQL

**Đáp án:** Dùng INSERT ... RETURNING order_id và đọc ResultSet.

### Bài 7. Lấy ID vừa insert ở MySQL JDBC

**Đáp án:** Chuẩn bị statement với Statement.RETURN_GENERATED_KEYS, executeUpdate rồi gọi getGeneratedKeys.

### Bài 8. Vì sao không dùng SELECT MAX(order_id)?

**Đáp án:** Hai transaction đồng thời có thể insert xen kẽ; MAX có thể trả ID của request khác.

### Bài 9. Upsert theo SKU ở PostgreSQL

**Đáp án:** ON CONFLICT (sku) DO UPDATE và dùng EXCLUDED để tham chiếu hàng đề xuất.

### Bài 10. Upsert theo SKU ở MySQL

**Đáp án:** ON DUPLICATE KEY UPDATE. MySQL kích hoạt theo unique/primary key conflict; không chỉ định target theo cùng cú pháp PostgreSQL.

### Bài 11. Cách giảm oversell

**Đáp án:** UPDATE tồn kho với điều kiện quantity_on_hand >= requested, kiểm tra affected rows và đặt trong transaction cùng workflow xác nhận đơn.

### Bài 12. Vì sao SELECT rồi UPDATE riêng có rủi ro?

**Đáp án:** Hai transaction có thể cùng đọc một số lượng đủ trước khi transaction kia trừ hàng. Cần locking read hoặc conditional atomic update.

### Bài 13. Hai transaction confirm cùng một order

**Đáp án:** Khóa hàng order bằng SELECT FOR UPDATE hoặc UPDATE có điều kiện status = NEW; kiểm tra affected rows để chỉ một lần chuyển trạng thái thành công.

### Bài 14. PostgreSQL và MySQL mặc định isolation giống nhau không?

**Đáp án:** Không. PostgreSQL thường mặc định READ COMMITTED; InnoDB thường mặc định REPEATABLE READ. Cấu hình có thể thay đổi.

### Bài 15. Deadlock xảy ra thì retry thế nào?

**Đáp án:** Rollback và chạy lại toàn bộ transaction với giới hạn retry/backoff. Không chỉ chạy lại statement bị lỗi.

### Bài 16. MySQL DDL có rollback như PostgreSQL không?

**Đáp án:** Nhiều DDL MySQL gây implicit commit. Atomic DDL không đồng nghĩa DDL transactional. Thiết kế migration riêng và kiểm tra trạng thái sau lỗi.

### Bài 17. PostgreSQL TIMESTAMPTZ có lưu timezone name không?

**Đáp án:** Không. Nó lưu instant; session timezone ảnh hưởng cách hiển thị. Muốn giữ timezone gốc, lưu riêng zone ID nếu nghiệp vụ cần.

### Bài 18. MySQL TIMESTAMP và DATETIME khác nhau thế nào?

**Đáp án:** TIMESTAMP chuyển đổi theo timezone session khi lưu/đọc; DATETIME giữ thành phần ngày giờ và không tự chuyển đổi timezone theo cùng cách.

### Bài 19. MySQL BOOLEAN là kiểu riêng như PostgreSQL không?

**Đáp án:** Không. BOOLEAN là alias của TINYINT(1). Cần validation/constraint nếu chỉ chấp nhận 0/1.

### Bài 20. utf8mb4 có cần thiết cho emoji trong MySQL không?

**Đáp án:** Có, utf8mb4 hỗ trợ đầy đủ code point ngoài BMP; utf8mb3 không đủ.

### Bài 21. PostgreSQL JSONB và MySQL JSON giống nhau hoàn toàn không?

**Đáp án:** Không. Kiểu lưu trữ, operator, indexing và query syntax khác; cần repository/dialect riêng cho truy vấn JSON.

### Bài 22. Cùng index có cùng query plan không?

**Đáp án:** Không. Optimizer, statistics, data distribution và implementation khác nhau. So sánh EXPLAIN trên workload giống nhau.

### Bài 23. Vì sao MySQL index composite cần chú ý leftmost prefix?

**Đáp án:** B-tree composite index thường hữu ích bắt đầu từ các cột bên trái; thứ tự cột phải khớp pattern truy vấn.

### Bài 24. PostgreSQL có partial index, MySQL có cùng cú pháp không?

**Đáp án:** Không có partial index cùng cú pháp/tính năng tổng quát; cân nhắc composite index, generated column hoặc thiết kế khác.

### Bài 25. Có thể dùng cùng SQL cho CRUD cơ bản không?

**Đáp án:** Nhiều query có thể dùng chung, nhưng schema qualification, generated key, upsert, JSON, DDL và date functions thường cần dialect.

### Bài 26. Vì sao không tắt ONLY_FULL_GROUP_BY?

**Đáp án:** Nó giúp phát hiện query GROUP BY không xác định. Sửa query để aggregate/group đúng thay vì hạ SQL mode che lỗi.

### Bài 27. Một test contract nên chạy trên hai DBMS thế nào?

**Đáp án:** Dùng cùng fixture và assertions nghiệp vụ, nhưng tạo database/container và driver riêng cho mỗi hệ. Ghi rõ version/config.

### Bài 28. Vì sao test concurrency cần barrier/latch?

**Đáp án:** Để điều phối hai transaction thực sự chạy chồng lấn có kiểm soát. Sleep ngẫu nhiên không đảm bảo tái hiện race condition.

### Bài 29. Khi client mất kết nối ngay sau COMMIT, có nên retry insert order ngay?

**Đáp án:** Không retry mù quáng. Dùng idempotency key/operation ID và kiểm tra trạng thái đã commit trước khi tạo lại.

### Bài 30. Điều kiện để kết luận hai database tương đương về nghiệp vụ?

**Đáp án:** Cùng contract, cùng kết quả và constraint, transaction/concurrency đúng, mapping kiểu dữ liệu chính xác, migration recovery rõ và integration tests chạy trên đúng version/driver.

## 45. Kết luận

Đối chiếu hai hệ quản trị phải bắt đầu từ cùng một bài toán và cùng hợp đồng nghiệp vụ. Với ví dụ cửa hàng, PostgreSQL và MySQL đều có thể quản lý khách hàng, sản phẩm, đơn hàng, chi tiết đơn và tồn kho; nhưng cách tạo ID, namespace, kiểu Boolean, JSON, timestamp, upsert, generated keys và DDL transaction có khác biệt.

Những điều cần giữ trong thực hành:

- Thiết kế contract và bất biến trước khi viết DDL.
- Giữ schema tương đương về ý nghĩa, nhưng cho phép migration riêng theo dialect.
- Dùng NUMERIC/DECIMAL và BigDecimal cho tiền.
- Chọn timestamp theo semantics timezone; test với đúng driver/session.
- Dùng conditional UPDATE hoặc locking trong transaction để bảo vệ tồn kho.
- Hiểu isolation mặc định và deadlock behavior thay vì giả định hai engine giống nhau.
- Dùng RETURNING ở PostgreSQL và generated keys phù hợp ở MySQL.
- Viết upsert theo cú pháp riêng và thiết kế idempotency cho retry.
- Đo query plan bằng dữ liệu đại diện, không suy ra hiệu năng từ cú pháp.
- Chạy cùng contract tests trên cả hai DBMS và kiểm tra migration failure/recovery.

**Một phép đối chiếu có giá trị phải trả lời được: cùng input và cùng trạng thái ban đầu, hai hệ quản trị có bảo đảm cùng kết quả nghiệp vụ trong cả trường hợp thành công, lỗi và cạnh tranh đồng thời hay không?** Khi câu trả lời được chứng minh bằng schema, query, transaction, execution plan và integration tests, bạn mới có cơ sở để lựa chọn database hoặc hỗ trợ nhiều hệ quản trị một cách đáng tin cậy.
