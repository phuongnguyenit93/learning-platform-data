# Truy vấn N+1 và truy vấn quá nhiều hàng từ ứng dụng trong PostgreSQL

Một ứng dụng có thể chậm dù **mỗi câu SQL riêng lẻ chạy rất nhanh**. Hai nguyên nhân thường bị bỏ qua là:

1. **N+1 queries:** ứng dụng lấy một danh sách bằng một query, rồi chạy thêm một query cho **mỗi phần tử** của danh sách.
2. **Overfetching:** ứng dụng yêu cầu PostgreSQL trả **quá nhiều dòng, quá nhiều cột hoặc quá nhiều dữ liệu lồng nhau**, sau đó mới lọc/cắt bỏ trong Java.

Ví dụ một trang hiển thị 50 đơn hàng và tên khách đặt đơn:

```text
SELECT 50 orders                    -> 1 query
for each order:
    SELECT customer WHERE id = ...  -> 50 queries
                                      ----------
                                      51 queries cho một trang
```

Một cách khác dùng JOIN có thể lấy đủ thông tin qua **một round trip**:

```sql
SELECT
    o.order_id,
    o.ordered_at,
    o.total_amount,
    c.customer_name
FROM orders AS o
JOIN customers AS c
  ON c.customer_id = o.customer_id
ORDER BY o.ordered_at DESC, o.order_id DESC
LIMIT 50;
```

Nhưng việc gộp mọi thứ vào một JOIN không phải giải pháp vạn năng. Nếu một đơn có 10 dòng sản phẩm, JOIN đơn với chi tiết có thể biến 50 đơn thành **500 dòng kết quả**, lặp lại thông tin đơn và khách trên mỗi dòng. Nếu JOIN thêm một quan hệ một-nhiều khác, số dòng có thể **nhân chéo** ngoài dự kiến.

Tương tự, một câu:

```sql
SELECT * FROM orders;
```

có thể chỉ là **một query**, nhưng nếu bảng có hàng triệu đơn cùng các cột JSONB/TEXT lớn thì lượng dữ liệu chuyển từ PostgreSQL tới ứng dụng vẫn rất lớn. Sau đó gọi `stream().limit(20)` trên danh sách đã tải không làm database bớt gửi dữ liệu.

**Tối ưu đúng là giảm cả số lượt truy cập lẫn lượng dữ liệu phải đọc, truyền, ánh xạ và lưu trong ứng dụng**, đồng thời giữ đúng nghiệp vụ và tính nhất quán.

## 1. Mục tiêu học tập

Sau bài này, bạn sẽ có thể:

- Nhận diện N+1 từ vòng lặp Java, ORM lazy loading, serializer và log SQL.
- Phân biệt **query count**, **round trips**, **rows returned**, **row width**, **bytes transferred** và thời gian thực thi.
- Viết các cách thay N+1 bằng **JOIN**, **batch fetch**, `IN`/`ANY`, truy vấn tổng hợp hoặc **projection**.
- Chọn chiến lược riêng cho quan hệ **many-to-one**, **one-to-many** và nhiều collection.
- Tránh tác động phụ của JOIN: lặp dòng cha, sai phân trang, cartesian multiplication và tổng hợp sai.
- Giới hạn dữ liệu ngay tại PostgreSQL bằng `WHERE`, `ORDER BY`, `LIMIT`, keyset pagination và chọn cột cần thiết.
- Hiểu JDBC `fetchSize`, cursor, streaming và lý do fetch theo lô **khác** giới hạn tổng số hàng.
- Đo bằng `EXPLAIN (ANALYZE, BUFFERS)`, `pg_stat_statements`, log ứng dụng, tracing và bộ đếm rows/bytes.
- Thiết kế index hỗ trợ query đã được gộp, không chỉ tối ưu từng query N+1.
- Xây dựng bài kiểm thử chống regression N+1 và overfetch.

## 2. Hai loại vấn đề: quá nhiều truy vấn và quá nhiều dữ liệu

| Khía cạnh | N+1 queries | Overfetching |
| --- | --- | --- |
| Dấu hiệu | Một request phát nhiều SQL giống nhau, khác giá trị bind | Một hoặc vài SQL trả nhiều dòng/cột/byte hơn màn hình cần |
| Ví dụ | 1 query lấy 100 đơn + 100 query lấy khách | Lấy 100.000 đơn rồi chỉ hiển thị 20 |
| Chi phí chủ đạo | Network round trips, parse/bind/execute, pool, server overhead | I/O, CPU, memory, truyền mạng, decode, object mapping, GC |
| Có thể xảy ra cùng lúc? | Có | Có |
| Biện pháp thường gặp | JOIN, batch fetch, eager fetch có chọn lọc, DataLoader | Projection, WHERE/LIMIT, pagination, stream, chỉ tải quan hệ cần thiết |
| Rủi ro khi sửa | JOIN một-nhiều nhân bản dòng; bộ nhớ tăng | Giới hạn sai khiến mất dữ liệu hoặc phân trang không ổn định |
| Đo lường | Queries per request, mẫu SQL lặp, thời gian round trip | Rows/bytes per request, heap/JVM memory, result set size, latency |

**Một query không tự động tốt hơn hai query.** Hai query đọc đúng 20 đơn và 80 dòng chi tiết có thể tốt hơn một JOIN trả 20 × 80 dòng do hai quan hệ độc lập. Mục tiêu là **tổng chi phí và tính đúng**, không phải tối thiểu hóa query count bằng mọi giá.

### 2.1. Tư duy tổng chi phí

Một mô hình khái niệm:

```text
Request latency ≈
    thời gian chờ connection pool
  + tổng round-trip/driver overhead
  + SQL planning/execution
  + transfer + decode result sets
  + object mapping / serialization
  + business processing
  + thời gian chờ khác
```

Không dùng công thức này như phép cộng chính xác khi query chạy song song hoặc có overlap. Nó minh họa vì sao query nhanh trong psql vẫn có thể chậm trong ứng dụng.

## 3. Tại sao N+1 xảy ra?

Giả sử màn hình danh sách đơn hiển thị tên khách:

```sql
SELECT order_id, customer_id, ordered_at, total_amount
FROM orders
ORDER BY ordered_at DESC
LIMIT 50;
```

Sau khi nhận 50 đơn, code gọi:

```sql
SELECT customer_id, customer_name
FROM customers
WHERE customer_id = 17;
```

và câu tương tự 49 lần nữa.

Đây là mô hình **1 + N**:

```text
1: tìm N đơn (parent entities)
N: tìm customer của từng đơn
=> 1 + N database queries trong trường hợp không có cache/batching
```

### 3.1. N+1 không nhất thiết luôn đúng N+1 query thực tế

Nếu 50 đơn thuộc cùng 5 khách, ORM first-level cache có thể giảm số lần load customer từ 50 xuống 5 trong những điều kiện phù hợp. Nếu cache đã có sẵn, số query còn ít hơn; nếu mỗi đơn có khách khác nhau, gần 50 queries.

Vì vậy N+1 là **mẫu truy cập dữ liệu gây số truy vấn tăng theo kích thước danh sách**, không phải cam kết mọi lần chạy chính xác N+1 statement.

### 3.2. Vấn đề thường nằm ở ranh giới repository/service/serializer

Code có thể trông gọn:

```java
List<Order> orders = orderRepository.findRecent(50);
for (Order order : orders) {
    System.out.println(order.getCustomer().getName());
}
```

Nếu `getCustomer()` kích hoạt ORM lazy loading khi customer chưa được nạp, vòng lặp có thể gây nhiều SELECT. Điều này vẫn xảy ra dù code **không hề viết SQL trực tiếp trong for loop**.

Tương tự:

- Mapper chuyển entity sang DTO rồi gọi `getItems()`.
- Jackson serializer duyệt quan hệ để tạo JSON.
- Template engine truy cập `order.customer.name`.
- Resolver GraphQL gọi data source theo từng parent.
- Service gọi repository lấy số đơn của từng khách.

**Phải quan sát SQL thực tế trong một request**, không kết luận query count chỉ từ hình dạng code Java.

## 4. Hiệu ứng round trip: vì sao nhiều query nhỏ vẫn đắt?

Giả sử lấy một customer theo ID chỉ tốn **0,3 ms tại server**. Với 100 customer queries, chưa tính bất kỳ thứ gì khác đã có nhiều lượt parse/bind/execute và truyền kết quả.

Nếu ứng dụng và database đi qua mạng với round-trip latency đáng kể, thực hiện 100 query tuần tự có thể khiến latency lớn hơn nhiều so với thời gian CPU của PostgreSQL cho từng query.

Ví dụ **giả định để hiểu tỷ lệ**, không phải benchmark:

```text
Một request cần 50 customer lookups tuần tự
Mỗi round trip giả định mất khoảng 4 ms
=> riêng 50 lượt round trip đã có thể gần 200 ms

Nếu gộp thành một batch query:
=> một lượt round trip cho 50 khách
=> chi phí khác như index access và transfer vẫn tồn tại
```

### 4.1. Tăng connection pool không chữa N+1

Thêm nhiều connection có thể xử lý thêm request đồng thời ở một mức nào đó, nhưng:

- Mỗi request vẫn phát nhiều query.
- Database có thể bị tăng concurrency và lock/cache pressure.
- Pool lớn có thể làm nhiều truy vấn tranh CPU/I/O hơn.
- Query tuần tự trong **cùng request** không tự song song chỉ vì pool rộng.

Tối ưu ưu tiên là **giảm truy vấn thừa** và giới hạn dữ liệu; sau đó mới sizing pool theo throughput thực.

### 4.2. N+1 ở cùng máy vẫn có chi phí

Nếu ứng dụng và PostgreSQL cùng host, network latency có thể thấp nhưng server vẫn phải tiếp nhận, parse/plan/bind/execute và gửi từng câu SQL. Pool, driver, mapping và context switching vẫn có chi phí.

## 5. Môi trường thực hành PostgreSQL

Ta dùng schema `app_fetch_lab`, chứa khách hàng, đơn và dòng sản phẩm. Những ví dụ sau chỉ nên chạy trong **database thử nghiệm** được phép tạo bảng/nạp dữ liệu.

### 5.1. Tạo schema

```sql
CREATE SCHEMA IF NOT EXISTS app_fetch_lab;
```

### 5.2. Bảng customers

```sql
CREATE TABLE app_fetch_lab.customers (
    customer_id INTEGER PRIMARY KEY,
    customer_name TEXT NOT NULL,
    region_code TEXT NOT NULL,
    email TEXT NOT NULL
);
```

### 5.3. Bảng orders

```sql
CREATE TABLE app_fetch_lab.orders (
    order_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    customer_id INTEGER NOT NULL
        REFERENCES app_fetch_lab.customers(customer_id),
    ordered_at TIMESTAMPTZ NOT NULL,
    status TEXT NOT NULL
        CHECK (status IN ('PAID', 'PENDING', 'CANCELLED')),
    total_amount NUMERIC(12, 2) NOT NULL CHECK (total_amount >= 0),
    note TEXT,
    extra_data JSONB NOT NULL DEFAULT '{}'::jsonb
);
```

### 5.4. Bảng order_items

```sql
CREATE TABLE app_fetch_lab.order_items (
    order_item_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    order_id BIGINT NOT NULL
        REFERENCES app_fetch_lab.orders(order_id),
    product_code TEXT NOT NULL,
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    unit_price NUMERIC(12, 2) NOT NULL CHECK (unit_price >= 0)
);
```

### 5.5. Nạp 1.000 khách

```sql
INSERT INTO app_fetch_lab.customers
    (customer_id, customer_name, region_code, email)
SELECT
    g.n,
    'Customer ' || g.n,
    CASE WHEN g.n % 3 = 0 THEN 'N'
         WHEN g.n % 3 = 1 THEN 'C'
         ELSE 'S'
    END,
    'customer' || g.n || '@example.test'
FROM generate_series(1, 1000) AS g(n);
```

### 5.6. Nạp 50.000 đơn

```sql
INSERT INTO app_fetch_lab.orders
    (customer_id, ordered_at, status, total_amount, note, extra_data)
SELECT
    (g.n % 1000) + 1,
    TIMESTAMPTZ '2026-01-01 00:00:00+00'
      + make_interval(mins => g.n),
    CASE WHEN g.n % 10 < 7 THEN 'PAID'
         WHEN g.n % 10 < 9 THEN 'PENDING'
         ELSE 'CANCELLED'
    END,
    (100 + g.n % 5000)::numeric(12, 2),
    repeat('Example note; ', 16),
    jsonb_build_object(
        'source', CASE WHEN g.n % 2 = 0 THEN 'web' ELSE 'app' END,
        'debugText', repeat('metadata-', 24)
    )
FROM generate_series(1, 50000) AS g(n);
```

### 5.7. Nạp ba item cho mỗi đơn

Với bảng mới tạo, `order_id` lần lượt từ 1 tới 50.000. Dùng INSERT dựa vào ID đã có thay vì giả định về identity trong những lượt chạy lại:

```sql
INSERT INTO app_fetch_lab.order_items
    (order_id, product_code, quantity, unit_price)
SELECT
    o.order_id,
    'SKU-' || x.item_no,
    x.item_no,
    (15 * x.item_no)::numeric(12, 2)
FROM app_fetch_lab.orders AS o
CROSS JOIN generate_series(1, 3) AS x(item_no);
```

Nếu chạy đúng một lần trên schema trống: **50.000 đơn × 3 item = 150.000 item**.

### 5.8. Chỉ mục phục vụ bài lab

```sql
CREATE INDEX idx_app_orders_recent
ON app_fetch_lab.orders
    (ordered_at DESC, order_id DESC);

CREATE INDEX idx_app_orders_customer_recent
ON app_fetch_lab.orders
    (customer_id, ordered_at DESC, order_id DESC);

CREATE INDEX idx_app_items_order
ON app_fetch_lab.order_items (order_id);

ANALYZE app_fetch_lab.customers;
ANALYZE app_fetch_lab.orders;
ANALYZE app_fetch_lab.order_items;
```

PostgreSQL **không tự động tạo index ở cột FK phía bảng con** chỉ vì đã khai báo foreign key. Vì vậy index `order_items(order_id)` được tạo tường minh để các truy vấn lấy item của nhiều đơn có đường truy cập phù hợp.

### 5.9. Xác nhận dữ liệu

```sql
SELECT
    (SELECT count(*) FROM app_fetch_lab.customers)
        AS customer_count,
    (SELECT count(*) FROM app_fetch_lab.orders)
        AS order_count,
    (SELECT count(*) FROM app_fetch_lab.order_items)
        AS item_count;
```

Kỳ vọng lần chạy đầu trên schema trống: 1.000 / 50.000 / 150.000.

## 6. Thấy rõ N+1 bằng SQL: 1 + 20 truy vấn

Trang hiển thị 20 đơn mới nhất:

```sql
SELECT order_id, customer_id, ordered_at, total_amount
FROM app_fetch_lab.orders
ORDER BY ordered_at DESC, order_id DESC
LIMIT 20;
```

Giả sử Java lặp các hàng rồi với mỗi `customer_id` chạy:

```sql
SELECT customer_id, customer_name
FROM app_fetch_lab.customers
WHERE customer_id = 781;
```

Lặp lại câu SELECT customer với các ID khác.

### 6.1. Tổng số SQL

```text
N = số đơn trả về ở trang = 20
1 query lấy đơn
20 query lấy khách (nếu mỗi lookup thật sự ra database)
=> 21 query/request
```

Thay trang bằng 100 đơn:

```text
1 query danh sách + 100 customer queries
=> 101 query/request
```

Khi tăng page size, query count tăng gần tuyến tính với N. Nếu cùng endpoint phục vụ hàng trăm request, mức tăng load có thể rất lớn dù một SELECT PK đơn lẻ rất rẻ.

### 6.2. N+1 nhiều tầng

Một endpoint cũng có thể:

```text
1 query lấy 20 đơn
20 query lấy khách
20 query lấy items
20 query đếm payments
=> 61 queries/request
```

N+1 thường **cộng dồn theo mỗi quan hệ**. Với một tầng sâu hơn, như query sản phẩm cho từng item, số truy vấn có thể phát triển theo số item chứ không còn chỉ theo số đơn.

## 7. Cách sửa A: JOIN cho quan hệ many-to-one

Vì mỗi đơn tham chiếu đúng một customer, JOIN customers là cách phù hợp để lấy thông tin tên khách trong cùng query:

```sql
SELECT
    o.order_id,
    o.customer_id,
    o.ordered_at,
    o.total_amount,
    c.customer_name
FROM app_fetch_lab.orders AS o
JOIN app_fetch_lab.customers AS c
  ON c.customer_id = o.customer_id
ORDER BY o.ordered_at DESC, o.order_id DESC
LIMIT 20;
```

Trong schema lab, FK `orders.customer_id` là `NOT NULL` và tham chiếu khóa chính customers, nên mỗi order có **chính xác một** customer theo trạng thái dữ liệu hợp lệ. JOIN **không nhân số dòng order**.

### 7.1. Vì sao JOIN ở đây xử lý N+1?

- Một SQL gửi tới PostgreSQL.
- Database xử lý phép nối theo kế hoạch: Nested Loop/Hash Join/Merge Join hoặc phương án hợp lệ khác.
- Application nhận các cột cần hiển thị thay vì tự gọi customer repository 20 lần.
- Một round trip cho result set chính.

**Không có nghĩa database chỉ đọc đúng một row vật lý**; PostgreSQL vẫn cần scan/index, join và có thể đọc các page ở cả hai bảng. Lợi ích là đưa logic ghép quan hệ vào một query có thể tối ưu toàn cục và tránh nhiều lượt đi-về.

### 7.2. EXPLAIN trên JOIN

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT
    o.order_id,
    o.ordered_at,
    o.total_amount,
    c.customer_name
FROM app_fetch_lab.orders AS o
JOIN app_fetch_lab.customers AS c
  ON c.customer_id = o.customer_id
ORDER BY o.ordered_at DESC, o.order_id DESC
LIMIT 20;
```

Có thể thấy `Nested Loop` cùng index PK customer, hoặc `Hash Join` tùy thống kê/cost. **Không yêu cầu PostgreSQL phải chọn chính xác một loại join** để xem giải pháp là đúng.

### 7.3. LEFT JOIN nếu quan hệ là tùy chọn

Nếu một order có thể không có customer theo mô hình khác, dùng `LEFT JOIN` khi cần **giữ cả đơn thiếu customer**:

```sql
SELECT o.order_id, c.customer_name
FROM app_fetch_lab.orders AS o
LEFT JOIN app_fetch_lab.customers AS c
  ON c.customer_id = o.customer_id;
```

Không đổi JOIN thành LEFT JOIN chỉ vì “an toàn hơn” mà bỏ qua semantics: cần xem FK, NOT NULL và yêu cầu nghiệp vụ.

## 8. Cách sửa B: batch fetch qua ANY(array)

Không phải mọi nơi đều có thể sửa repository để JOIN một cách thuận lợi, đặc biệt khi dữ liệu được ghép theo nhiều bước hoặc dùng một lớp cache độc lập.

Thay vì query customer từng đơn, có thể:

1. Lấy 20 đơn.
2. Thu thập **các customer_id duy nhất**.
3. Gửi **một query** lấy các customer tương ứng.
4. Tạo map `customerId -> CustomerDTO` trong Java.
5. Ghép lại trong bộ nhớ.

Ví dụ SQL lấy khách theo danh sách:

```sql
SELECT
    customer_id,
    customer_name
FROM app_fetch_lab.customers
WHERE customer_id IN (781, 782, 783, 784);
```

Hoặc với PostgreSQL array:

```sql
SELECT
    customer_id,
    customer_name
FROM app_fetch_lab.customers
WHERE customer_id = ANY(ARRAY[781, 782, 783, 784]::integer[]);
```

### 8.1. Query count

```text
Trước: 1 query orders + 20 query customers = 21 queries
Sau:   1 query orders +  1 query customers =  2 queries
```

Số query không phụ thuộc trực tiếp vào số order khi danh sách IDs còn nằm trong một batch hợp lý.

### 8.2. ANY(array) trong JDBC

Với PostgreSQL JDBC driver, có thể bind một SQL array:

```java
List<Integer> customerIds = List.of(781, 782, 783, 784);

String sql = """
    SELECT customer_id, customer_name
    FROM app_fetch_lab.customers
    WHERE customer_id = ANY(?)
    """;

try (PreparedStatement ps = connection.prepareStatement(sql);
     java.sql.Array ids = connection.createArrayOf(
         "integer", customerIds.toArray())) {
    ps.setArray(1, ids);
    try (ResultSet rs = ps.executeQuery()) {
        while (rs.next()) {
            // Ghi customer vào Map<Integer, CustomerDto>.
        }
    }
}
```

Đoạn Java minh họa API driver. Trong mã thực tế, `java.sql.Array` có cách quản lý tài nguyên riêng (thường có thể gọi `free()` trong `finally`); không giả định nó có hỗ trợ try-with-resources như `AutoCloseable` trong mọi JDK/driver. Có thể viết:

```java
java.sql.Array ids =
    connection.createArrayOf("integer", customerIds.toArray());
try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setArray(1, ids);
    try (ResultSet rs = ps.executeQuery()) {
        while (rs.next()) {
            // Đọc dữ liệu.
        }
    }
} finally {
    ids.free();
}
```

**Chú ý:** với danh sách ID rỗng, ứng dụng thường bỏ qua query và dùng map rỗng; đừng tự dựng chuỗi `IN ()` không hợp lệ. Với danh sách cực lớn, cần chia batch hoặc dùng cách nạp tập ID phù hợp thay vì tạo array khổng lồ vô điều kiện.

### 8.3. Batching không đồng nghĩa giảm mọi chi phí

Một SELECT với `ANY` trên 50.000 IDs có thể tốn nhiều thời gian lập kế hoạch, CPU, bộ nhớ và I/O. Nếu ứng dụng đã lấy quá nhiều orders, batch fetch khách **không chữa được overfetch ban đầu**.

Thứ tự hợp lý: **giới hạn tập đơn cần xem trước**, rồi batch fetch các quan hệ tương ứng.

## 9. Batch fetching trong Java: ví dụ ánh xạ DTO

Giả sử repository đã có danh sách order gồm `customerId`.

```java
record OrderRow(
    long orderId,
    int customerId,
    java.math.BigDecimal totalAmount
) {}

record CustomerRow(int customerId, String customerName) {}

record OrderSummary(
    long orderId,
    String customerName,
    java.math.BigDecimal totalAmount
) {}

List<OrderRow> orders = findRecentOrders(connection, 20);

List<Integer> ids = orders.stream()
    .map(OrderRow::customerId)
    .distinct()
    .toList();

Map<Integer, CustomerRow> customersById =
    findCustomersByIds(connection, ids);

List<OrderSummary> summaries = orders.stream()
    .map(order -> {
        CustomerRow customer = customersById.get(order.customerId());
        if (customer == null) {
            throw new IllegalStateException(
                "Missing customer " + order.customerId()
            );
        }
        return new OrderSummary(
            order.orderId(),
            customer.customerName(),
            order.totalAmount()
        );
    })
    .toList();
```

Đây là **mẫu cấu trúc Java**, giả định các helper `findRecentOrders` và `findCustomersByIds` được triển khai bằng SQL parameterized, JDBC/transaction handling đúng. Nó nhấn mạnh:

- Có thể sử dụng `distinct()` để không hỏi lại cùng customer.
- Truy cập map trong Java không tạo SQL mới.
- Thiếu customer phải xử lý theo invariant nghiệp vụ; không lặng lẽ hiển thị tên sai.
- Giữ thứ tự `orders` khi tạo DTO, không phụ thuộc thứ tự trả về của `IN/ANY`.

### 9.1. Truyền thứ tự của danh sách IDs

Một query `WHERE id = ANY(...)` **không bảo đảm kết quả theo thứ tự ID đầu vào**. Trong hầu hết trường hợp nên map theo key như trên.

Nếu SQL phải giữ thứ tự yêu cầu, có thể dùng `unnest(... WITH ORDINALITY)` rồi JOIN:

```sql
WITH requested AS (
    SELECT id, ord
    FROM unnest(ARRAY[784, 781, 783]::integer[])
         WITH ORDINALITY AS u(id, ord)
)
SELECT
    c.customer_id,
    c.customer_name
FROM requested AS r
JOIN app_fetch_lab.customers AS c
  ON c.customer_id = r.id
ORDER BY r.ord;
```

Đây là một cách giữ thứ tự, không bắt buộc nếu application đã ghép lại theo map.

## 10. N+1 ở quan hệ one-to-many: mỗi đơn lại SELECT items

Trên màn hình đơn hàng:

```text
1 SELECT lấy 20 orders
20 SELECT lấy order_items WHERE order_id = ?
```

Một query item điển hình:

```sql
SELECT order_item_id, product_code, quantity, unit_price
FROM app_fetch_lab.order_items
WHERE order_id = 49999
ORDER BY order_item_id;
```

Với 20 đơn và mỗi đơn có ba item, N+1 là 21 SQL, nhưng chỉ cần **20 đơn + 60 item**. Có hai chiến lược thường phù hợp.

### 10.1. Một JOIN cho toàn bộ quan hệ

```sql
SELECT
    o.order_id,
    o.ordered_at,
    i.order_item_id,
    i.product_code,
    i.quantity
FROM app_fetch_lab.orders AS o
LEFT JOIN app_fetch_lab.order_items AS i
  ON i.order_id = o.order_id
WHERE o.order_id IN (49996, 49997, 49998, 49999, 50000)
ORDER BY o.order_id, i.order_item_id;
```

Nếu mỗi order có ba item, JOIN sẽ trả **15 dòng** cho 5 orders. Java phải **group by order_id** để tái tạo cấu trúc parent–children.

### 10.2. Hai truy vấn: parent page rồi batch children

Query 1:

```sql
SELECT
    order_id,
    ordered_at,
    total_amount
FROM app_fetch_lab.orders
ORDER BY ordered_at DESC, order_id DESC
LIMIT 20;
```

Giả sử nhận các ID cụ thể, query 2:

```sql
SELECT
    order_id,
    order_item_id,
    product_code,
    quantity,
    unit_price
FROM app_fetch_lab.order_items
WHERE order_id = ANY(ARRAY[49981,49982,49983,49984,49985]::bigint[])
ORDER BY order_id, order_item_id;
```

Ở code thật, array chứa **toàn bộ IDs trang vừa được truy vấn**, không phải danh sách ví dụ cố định.

Tạo:

```text
Map<Long, List<OrderItemDto>>
    orderId -> tất cả items của đơn đó
```

Sau đó ghép mỗi order với danh sách của nó. Nếu một đơn không có items, dùng **danh sách rỗng** nếu nghiệp vụ cho phép, không hiểu là đơn không tồn tại.

### 10.3. Vì sao hai query đôi khi tốt hơn một JOIN?

- Có thể **phân trang đúng parent** trước.
- Không lặp lại mọi cột của đơn cho từng item.
- Có thể dùng projection hẹp cho hai loại entity.
- Giảm sự phức tạp khi ghép nhiều collection.
- Dễ kiểm soát số item có thể tải theo page.

Vì vậy cách sửa N+1 không nhất thiết phải gộp thành một SQL duy nhất.

## 11. Bẫy JOIN một-nhiều rồi LIMIT

Một câu SQL nguy hiểm:

```sql
SELECT
    o.order_id,
    o.ordered_at,
    i.order_item_id
FROM app_fetch_lab.orders AS o
LEFT JOIN app_fetch_lab.order_items AS i
  ON i.order_id = o.order_id
ORDER BY o.ordered_at DESC, o.order_id DESC
LIMIT 20;
```

Trong lab, mỗi order có ba items. Kết quả **20 dòng JOIN**, không phải **20 orders**. Chỉ khoảng bảy orders được phản ánh, trong đó order cuối có thể mới xuất hiện một phần items.

**`LIMIT` áp dụng lên số hàng sau JOIN**, không tự hiểu ý nghĩa “20 đơn hàng cha”.

### 11.1. Đúng: chọn parent page trước rồi JOIN

```sql
WITH page AS (
    SELECT
        order_id,
        ordered_at,
        total_amount
    FROM app_fetch_lab.orders
    ORDER BY ordered_at DESC, order_id DESC
    LIMIT 20
)
SELECT
    p.order_id,
    p.ordered_at,
    p.total_amount,
    i.order_item_id,
    i.product_code,
    i.quantity
FROM page AS p
LEFT JOIN app_fetch_lab.order_items AS i
  ON i.order_id = p.order_id
ORDER BY p.ordered_at DESC, p.order_id DESC, i.order_item_id;
```

Ở đây:

1. CTE `page` chọn **20 order IDs** trước.
2. JOIN items chỉ trên các order đó.
3. Output có thể nhiều hơn 20 hàng, nhưng đủ items thuộc 20 orders đã chọn.

**Tuy nhiên:** vẫn cần giới hạn số child rows nếu một order có hàng trăm nghìn items, và phải bảo đảm quy tắc phân trang/đọc snapshot phù hợp nghiệp vụ.

### 11.2. Sự khác nhau giữa số parent và số result rows

```text
20 orders × 3 items/order
=> 20 parent entities nhưng 60 joined rows
```

ORM có thể khử trùng lặp entity parent khi dựng object graph, nhưng lượng dữ liệu SQL truyền về vẫn phụ thuộc số joined rows và cách ORM xử lý. Đừng xem API trả 20 objects là bằng chứng PostgreSQL chỉ xuất 20 hàng.

## 12. Bẫy JOIN nhiều collection: cartesian multiplication

Giả sử mỗi order có:

- 3 items.
- 4 shipments.
- 5 payment attempts.

Nếu JOIN **ba quan hệ một-nhiều độc lập**:

```text
1 order × 3 items × 4 shipments × 5 payments
=> có thể tới 60 dòng cho một order
```

Với 20 orders, đầu ra có thể lên tới 1.200 dòng. Mỗi item, shipment và payment bị lặp theo các tổ hợp. Điều này có thể dẫn tới:

- Truyền nhiều dữ liệu trùng lặp.
- Tăng memory và object mapping.
- ORM cartesian product hoặc lỗi khi fetch nhiều bag collections.
- Tính `SUM` bị nhân sai nếu aggregate sau JOIN mà không chú ý grain.

### 12.1. Hướng xử lý

Chọn **parent page trước**, sau đó:

1. Batch load items cho các order IDs.
2. Batch load shipments.
3. Batch load payments.
4. Ghép theo `order_id`.

Tổng có thể là **1 + 3 = 4 SQL**, nhưng không nhân mọi collection thành một Cartesian-like result.

### 12.2. Cẩn trọng khi dùng DISTINCT

`DISTINCT` có thể giảm **các hàng giống hệt nhau** sau projection, nhưng không tự sửa được các giá trị khác nhau của item/shipment/payment và có thể tăng Sort/HashAggregate. Đừng dùng `DISTINCT` chỉ để che sai mô hình join.

## 13. Tổng hợp child ngay trong PostgreSQL

Khi API thật sự cần trả order cùng items, có thể dùng PostgreSQL JSON aggregation để **một hàng SQL đại diện một order**.

Ví dụ sau chỉ xét 20 đơn đã chọn:

```sql
WITH page AS (
    SELECT
        order_id,
        ordered_at,
        total_amount
    FROM app_fetch_lab.orders
    ORDER BY ordered_at DESC, order_id DESC
    LIMIT 20
)
SELECT
    p.order_id,
    p.ordered_at,
    p.total_amount,
    COALESCE(
        jsonb_agg(
            jsonb_build_object(
                'itemId', i.order_item_id,
                'sku', i.product_code,
                'quantity', i.quantity
            )
            ORDER BY i.order_item_id
        ) FILTER (WHERE i.order_item_id IS NOT NULL),
        '[]'::jsonb
    ) AS items
FROM page AS p
LEFT JOIN app_fetch_lab.order_items AS i
  ON i.order_id = p.order_id
GROUP BY p.order_id, p.ordered_at, p.total_amount
ORDER BY p.ordered_at DESC, p.order_id DESC;
```

Điểm cần hiểu:

- CTE giới hạn parent trước.
- `LEFT JOIN` giữ order không có item.
- `FILTER (WHERE i.order_item_id IS NOT NULL)` tránh tạo JSON phần tử “null item” do outer join.
- `COALESCE(..., '[]'::jsonb)` trả mảng rỗng cho đơn không có item.
- `ORDER BY` bên trong aggregate xác định thứ tự items; thứ tự output order được xác định riêng ở cuối.

### 13.1. JSON aggregation có miễn phí không?

Không. Database phải thực hiện JOIN/aggregate, tạo JSON, cấp bộ nhớ và có thể xử lý dữ liệu lớn. Cách này hợp khi API mong đợi JSON lồng nhau và tập child có giới hạn hợp lý. Nếu items quá nhiều, cần pagination hoặc endpoint riêng.

### 13.2. Tránh tính tổng tiền sai khi JOIN nhiều quan hệ

Nếu join items và payments đồng thời, `SUM(i.quantity * i.unit_price)` có thể bị nhân theo số payment rows. Một hướng phù hợp là **aggregate từng child relation theo order_id trước**, rồi join các kết quả tổng hợp theo order_id.

Ví dụ:

```sql
WITH item_totals AS (
    SELECT order_id,
           SUM(quantity * unit_price) AS subtotal
    FROM app_fetch_lab.order_items
    GROUP BY order_id
)
SELECT
    o.order_id,
    t.subtotal
FROM app_fetch_lab.orders AS o
JOIN item_totals AS t
  ON t.order_id = o.order_id
WHERE o.order_id = 50000;
```

Ở quy mô lớn, có thể giới hạn parent IDs trước để không aggregate mọi item toàn database.

## 14. LATERAL: một round trip, nhưng có thể có N inner executions

PostgreSQL hỗ trợ `LATERAL` để một subquery tham chiếu hàng từ relation bên ngoài.

Ví dụ lấy **hai item đầu** của từng order trong page:

```sql
WITH page AS (
    SELECT order_id, ordered_at
    FROM app_fetch_lab.orders
    ORDER BY ordered_at DESC, order_id DESC
    LIMIT 20
)
SELECT
    p.order_id,
    p.ordered_at,
    i.order_item_id,
    i.product_code
FROM page AS p
LEFT JOIN LATERAL (
    SELECT order_item_id, product_code
    FROM app_fetch_lab.order_items AS oi
    WHERE oi.order_id = p.order_id
    ORDER BY oi.order_item_id
    LIMIT 2
) AS i ON TRUE
ORDER BY p.ordered_at DESC, p.order_id DESC, i.order_item_id;
```

### 14.1. LATERAL có xóa toàn bộ N+1 work không?

Không nhất thiết. Truy vấn là **một SQL/round trip từ ứng dụng**, nhưng plan có thể chứa `Nested Loop` và chạy subquery bên trong **một lần cho mỗi parent**. Nếu có index phù hợp và mỗi inner query lấy hai hàng, nó có thể rất tốt.

Ngược lại, nếu mỗi lần inner subquery quét bảng lớn, việc lặp N lần có thể gây chi phí cao dù query count ở application là 1.

**Luôn xem `EXPLAIN (ANALYZE, BUFFERS)` và `loops` của inner plan**. Giảm database round trips không đồng nghĩa mọi thao tác bên trong server trở thành một lần.

### 14.2. Khi nào LATERAL hợp lý?

- Top K child rows **mỗi parent**.
- Query inner được hỗ trợ bởi index `(order_id, order_item_id)` hoặc index phù hợp.
- Danh sách parent đã bị giới hạn.
- Cần giữ semantics riêng cho mỗi parent thay vì trộn LIMIT toàn cục.

## 15. ORM JPA/Hibernate: lazy loading và N+1

Trong Java, một mapping điển hình:

```java
@Entity
class OrderEntity {
    @Id
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY)
    private CustomerEntity customer;

    @OneToMany(mappedBy = "order")
    private List<OrderItemEntity> items;
}
```

Đây là **mã minh họa mapping**, chưa bao gồm tên bảng/cột, getters/setters và các annotations cần thiết để khớp schema lab. Một dự án thật phải định nghĩa mapping chính xác.

Nếu service lấy list orders, sau đó chạm `order.getCustomer().getName()` hoặc `order.getItems().size()`, ORM có thể phát query cho từng entity/collection chưa được nạp.

### 15.1. Lazy không có nghĩa lỗi

Lazy loading là công cụ tránh tải quan hệ **khi không cần**. Nó trở thành N+1 khi code truy cập quan hệ của **một loạt entity** mà ORM không có chiến lược batch/join phù hợp.

Không sửa N+1 bằng cách chuyển **mọi quan hệ thành EAGER**. Việc đó có thể tạo overfetch cho các endpoint không cần quan hệ ấy, hoặc khiến SQL được phát theo các cách khó kiểm soát hơn.

### 15.2. JOIN FETCH cho quan hệ many-to-one

Với JPA/Hibernate khi entity mapping phù hợp:

```java
List<OrderEntity> orders = entityManager
    .createQuery("""
        select o
        from OrderEntity o
        join fetch o.customer
        order by o.orderedAt desc, o.id desc
        """, OrderEntity.class)
    .setMaxResults(20)
    .getResultList();
```

Vì `o.customer` là quan hệ nhiều-đến-một, fetch join thường không làm **nhân số row parent** theo kiểu collection. Tuy nhiên, cần xét mapping, predicates, authorization và query thực tế.

### 15.3. Collection fetch join với pagination là tình huống nguy hiểm

Ví dụ:

```java
entityManager.createQuery("""
    select o
    from OrderEntity o
    left join fetch o.items
    order by o.orderedAt desc
    """, OrderEntity.class)
    .setMaxResults(20)
    .getResultList();
```

Với collection one-to-many, một parent có nhiều joined rows. Một số ORM/framework có thể cảnh báo, giới hạn trong bộ nhớ hoặc xử lý cách khác để không cắt sai collection. Điều đó có thể dẫn tới **tải rất nhiều rows dù API chỉ trả 20 orders**.

**Thiết kế đáng tin hơn:** page parent IDs trước, sau đó batch-load items theo các IDs đó; hoặc dùng native SQL chọn parent page trước JOIN như mục 11.

### 15.4. Entity graph và fetch profiles

JPA entity graph/fetch plan có thể cho phép endpoint chọn quan hệ cần nạp mà không sửa mapping mặc định cho mọi use case. Tuy nhiên, nó **không đảm bảo query count bằng 1**; phải xem SQL thực tế do provider phát.

### 15.5. Batch fetching

Hibernate có những cơ chế batch fetching, ví dụ cấu hình batch size cho lazy associations. Khi nhiều entity chờ khởi tạo quan hệ, ORM có thể nạp một nhóm ID trong một query thay vì một query/ID.

Không tự kết luận chỉ cần tăng `batch_size` là giải quyết hết:

- Cần truy cập association trong session phù hợp.
- Batch size có thể làm nhiều query dạng `WHERE id IN (...)`.
- Bộ nhớ và số IDs tăng.
- Dữ liệu không cần thiết vẫn có thể bị nạp.
- Hành vi phụ thuộc provider, version, fetch plan và mapping.

**Đo query count thực tế** sau khi thay cấu hình.

## 16. DTO projection: chỉ lấy cột mà API cần

Một màn hình danh sách thường cần:

```text
orderId, orderedAt, totalAmount, customerName
```

Nó không cần:

```text
order.note, order.extra_data, customer.email,
mọi dòng items, mọi entity tracking metadata
```

Truy vấn hẹp:

```sql
SELECT
    o.order_id,
    o.ordered_at,
    o.total_amount,
    c.customer_name
FROM app_fetch_lab.orders AS o
JOIN app_fetch_lab.customers AS c
  ON c.customer_id = o.customer_id
ORDER BY o.ordered_at DESC, o.order_id DESC
LIMIT 20;
```

Trong JPA có thể dùng DTO projection phù hợp:

```java
List<OrderSummaryDto> result = entityManager
    .createQuery("""
        select new com.example.dto.OrderSummaryDto(
            o.id,
            o.orderedAt,
            o.totalAmount,
            c.name
        )
        from OrderEntity o
        join o.customer c
        order by o.orderedAt desc, o.id desc
        """, OrderSummaryDto.class)
    .setMaxResults(20)
    .getResultList();
```

Ví dụ JPQL giả định DTO constructor và tên field phù hợp; không thể chạy nguyên văn khi chưa định nghĩa các class.

### 16.1. DTO projection có những lợi ích nào?

- PostgreSQL có thể không cần lấy các cột lớn không dùng.
- Giảm lượng dữ liệu truyền.
- Giảm object allocation và persistence-context tracking.
- JSON serializer không vô tình duyệt các association lazy.
- Contract API rõ hơn và ít nguy cơ lộ dữ liệu nhạy cảm.

Không phải mọi projection đều làm query thành Index Only Scan; điều đó còn phụ thuộc index và MVCC/visibility map.

## 17. Overfetching: SELECT * và dữ liệu rộng

Trong lab, `orders` có `note` và `extra_data`. Màn hình danh sách chỉ cần số đơn, thời gian, tổng tiền.

**Không phù hợp cho danh sách:**

```sql
SELECT *
FROM app_fetch_lab.orders
ORDER BY ordered_at DESC
LIMIT 20;
```

**Phù hợp hơn:**

```sql
SELECT order_id, ordered_at, total_amount
FROM app_fetch_lab.orders
ORDER BY ordered_at DESC, order_id DESC
LIMIT 20;
```

Ngay cả khi cùng số hàng, SELECT * có thể:

- Mang thêm TEXT/JSONB.
- Tăng width của hàng đầu ra.
- Buộc đọc/giải mã dữ liệu TOAST nếu cột lớn được lấy.
- Tăng network payload.
- Tăng memory của ResultSet/DTO và JSON response.

### 17.1. Đọc width trong EXPLAIN

```sql
EXPLAIN
SELECT *
FROM app_fetch_lab.orders
WHERE customer_id = 42;

EXPLAIN
SELECT order_id, total_amount
FROM app_fetch_lab.orders
WHERE customer_id = 42;
```

Xem `width=...` của những node xuất output. `width` là **độ rộng trung bình ước lượng theo byte**, không phải tổng byte truyền trên network và không bảo đảm bằng kích thước JSON cuối cùng.

### 17.2. SELECT * còn gây coupling với schema

Thêm cột mới vào bảng có thể làm query SELECT * bắt đầu kéo thêm dữ liệu không cần. API được map theo thứ tự cột còn có thể gặp lỗi nếu phụ thuộc cấu trúc không ổn định.

Projection tường minh vừa giúp hiệu năng, vừa giúp contract rõ ràng.

## 18. Overfetching: lấy tất cả rồi cắt trong Java

Mẫu sai:

```java
List<Order> allOrders = orderRepository.findAll();

List<Order> page = allOrders.stream()
    .sorted(comparing(Order::getOrderedAt).reversed())
    .limit(20)
    .toList();
```

Nếu `findAll()` tải 50.000 hàng:

- PostgreSQL đã xử lý và gửi 50.000 hàng.
- JDBC/ORM đã giải mã và ánh xạ 50.000 objects.
- Java mới chọn 20 hàng.
- Việc limit trong stream **không giảm số hàng database đã trả**.

**Đúng về kiến trúc:**

```sql
SELECT order_id, ordered_at, total_amount
FROM app_fetch_lab.orders
ORDER BY ordered_at DESC, order_id DESC
LIMIT 20;
```

### 18.1. Điều kiện lọc cũng phải đẩy về database

Sai:

```java
List<Order> all = orderRepository.findAll();
List<Order> paid = all.stream()
    .filter(o -> o.getStatus() == OrderStatus.PAID)
    .toList();
```

Tốt hơn:

```sql
SELECT order_id, ordered_at, total_amount
FROM app_fetch_lab.orders
WHERE status = 'PAID'
ORDER BY ordered_at DESC, order_id DESC
LIMIT 20;
```

PostgreSQL có thể dùng thống kê, chỉ mục và tối ưu hóa để lọc sớm, giảm số hàng cần trả.

### 18.2. Không đẩy mọi thứ vào SQL bằng mọi giá

Một số logic nghiệp vụ không biểu diễn thuận lợi trong SQL, hoặc cần dùng API bên ngoài. Khi đó vẫn nên **giới hạn tập candidates từ database** rồi xử lý phần còn lại tại Java.

Quan trọng là phân định rõ **điều kiện nào giảm dữ liệu sớm được mà vẫn giữ đúng nghĩa nghiệp vụ**.

## 19. Pagination ở database: LIMIT và OFFSET

Phân trang truyền thống:

```sql
SELECT
    order_id,
    ordered_at,
    total_amount
FROM app_fetch_lab.orders
ORDER BY ordered_at DESC, order_id DESC
LIMIT 20 OFFSET 0;
```

Trang sau:

```sql
SELECT
    order_id,
    ordered_at,
    total_amount
FROM app_fetch_lab.orders
ORDER BY ordered_at DESC, order_id DESC
LIMIT 20 OFFSET 20;
```

PostgreSQL chỉ trả tối đa 20 hàng cho từng query, không phải cả bảng.

### 19.1. Vì sao ORDER BY cần key ổn định?

Nếu chỉ:

```sql
ORDER BY ordered_at DESC
```

hai đơn trùng timestamp có thể không có thứ tự tương đối ổn định. Thêm `order_id DESC`, vì order_id unique, để tạo total order cho pagination.

Không dựa vào thứ tự vật lý heap mặc định; không có `ORDER BY` thì thứ tự output không được bảo đảm.

### 19.2. OFFSET sâu vẫn tốn kém

```sql
SELECT order_id, ordered_at
FROM app_fetch_lab.orders
ORDER BY ordered_at DESC, order_id DESC
OFFSET 40000
LIMIT 20;
```

Executor thường phải đi qua nhiều hàng đủ điều kiện để bỏ qua 40.000 hàng rồi trả 20. Index có thứ tự có thể giúp, nhưng chi phí trang sâu vẫn tăng theo offset.

### 19.3. Concurrent inserts làm trang có thể bị dịch

Nếu người dùng xem trang 1 rồi một đơn mới được thêm trước khi xem trang 2, `OFFSET` có thể khiến một hàng bị lặp hoặc bị bỏ giữa các trang (tùy dữ liệu và thời điểm snapshot).

Nếu ứng dụng cần duyệt ổn định một danh sách đang thay đổi, cân nhắc keyset pagination hoặc snapshot/export phù hợp.

## 20. Keyset pagination: đi tiếp từ khóa cuối trang

Trang đầu:

```sql
SELECT order_id, ordered_at, total_amount
FROM app_fetch_lab.orders
ORDER BY ordered_at DESC, order_id DESC
LIMIT 20;
```

Ứng dụng giữ cặp khóa của **hàng cuối trang**:

```text
last_ordered_at = 2026-02-01T12:00:00Z
last_order_id   = 45678
```

Trang tiếp:

```sql
SELECT order_id, ordered_at, total_amount
FROM app_fetch_lab.orders
WHERE (ordered_at, order_id)
    < (TIMESTAMPTZ '2026-02-01 12:00:00+00', 45678)
ORDER BY ordered_at DESC, order_id DESC
LIMIT 20;
```

Với hai cột NOT NULL và cùng sort DESC, so sánh bộ `(ordered_at, order_id) < (...)` biểu diễn việc lấy những hàng **đứng sau** cặp khóa cuối cùng.

### 20.1. Index đi kèm

```sql
CREATE INDEX idx_app_orders_keyset
ON app_fetch_lab.orders (ordered_at DESC, order_id DESC);
```

Trong lab đã có một index tương đương `idx_app_orders_recent`; **không tạo thêm index trùng trên production** chỉ vì có ví dụ mới. PostgreSQL có thể dùng index đã tồn tại.

### 20.2. Khi có bộ lọc

Ví dụ riêng từng customer:

```sql
SELECT order_id, ordered_at, total_amount
FROM app_fetch_lab.orders
WHERE customer_id = 42
  AND (ordered_at, order_id)
      < (TIMESTAMPTZ '2026-02-01 12:00:00+00', 45678)
ORDER BY ordered_at DESC, order_id DESC
LIMIT 20;
```

Index `(customer_id, ordered_at DESC, order_id DESC)` đã tạo trong lab hỗ trợ hướng truy cập này.

**Chú ý:** thời điểm/ID ở đây chỉ minh họa. Ứng dụng phải lấy cursor đúng từ trang vừa trả. Không tự hardcode mốc không thuộc tập dữ liệu rồi kết luận trang tiếp không có dữ liệu.

### 20.3. Keyset không tạo snapshot toàn request chain

Nếu hàng cũ bị xóa hoặc khóa sắp xếp thay đổi trong khi người dùng phân trang, tập kết quả vẫn có thể thay đổi. Keyset giảm vấn đề dịch offset khi thêm hàng mới ở đầu, nhưng không tự bảo đảm “một snapshot bất biến” qua nhiều HTTP requests.

## 21. Count query: có cần COUNT(*) cho mọi trang?

Một API pagination thường gọi:

```sql
SELECT COUNT(*)
FROM app_fetch_lab.orders
WHERE status = 'PAID';
```

và query lấy 20 hàng của trang.

Đây là **hai query có mục đích khác nhau**, không phải N+1. Nhưng trên bảng rất lớn, COUNT(*) có thể cần xem xét lượng dữ liệu, MVCC và index/visibility; PostgreSQL không tự luôn trả số đếm chính xác O(1) từ metadata của bảng.

### 21.1. Khi UI không cần tổng số trang

Có thể lấy `pageSize+1` hàng:

```sql
SELECT
    order_id,
    ordered_at,
    total_amount
FROM app_fetch_lab.orders
WHERE status = 'PAID'
ORDER BY ordered_at DESC, order_id DESC
LIMIT 21;
```

Nếu cần hiển thị 20 hàng, sự tồn tại hàng thứ 21 cho biết còn trang tiếp theo theo snapshot của query đó. Khi API không cần total count, cách này có thể tránh một COUNT(*) đắt.

### 21.2. Khi cần COUNT chính xác

Nếu nghiệp vụ đòi tổng số bản ghi tại một mốc nhìn nhất quán, vẫn phải tính hoặc có chiến lược đếm phù hợp. Đừng thay số chính xác bằng ước lượng từ catalog mà không thông báo rõ semantics.

## 22. JDBC fetchSize: giới hạn kích thước batch, không phải tổng số hàng

JDBC hỗ trợ:

```java
preparedStatement.setFetchSize(500);
```

Giá trị này là **gợi ý cho driver về số hàng lấy mỗi lần fetch**, không tương đương:

```sql
LIMIT 500
```

Nếu query trả 2 triệu hàng:

- `LIMIT 500` làm database trả tối đa 500 hàng theo logic query.
- `fetchSize=500` có thể giúp driver lấy dữ liệu **theo nhiều batch** thay vì buffer toàn bộ, nhưng cuối cùng ứng dụng vẫn có thể đọc đủ 2 triệu hàng nếu lặp hết ResultSet.

### 22.1. PostgreSQL JDBC cursor-based fetching

Với PgJDBC trong cấu hình phù hợp, để driver có thể dùng cursor/fetch theo batch, thường cần:

- Connection có `autoCommit=false`.
- Statement phù hợp với chế độ fetch/cursor của driver.
- `setFetchSize(n)` với n dương.
- Duyệt ResultSet trong khi transaction còn hoạt động.

Ví dụ:

```java
boolean previousAutoCommit = connection.getAutoCommit();
connection.setAutoCommit(false);

try (PreparedStatement ps = connection.prepareStatement("""
        SELECT order_id, ordered_at, total_amount
        FROM app_fetch_lab.orders
        WHERE status = ?
        ORDER BY order_id
        """)) {
    ps.setString(1, "PAID");
    ps.setFetchSize(500);

    try (ResultSet rs = ps.executeQuery()) {
        while (rs.next()) {
            long orderId = rs.getLong("order_id");
            // Xử lý tuần tự, không add tất cả vào một List khổng lồ.
        }
    }
    connection.commit();
} catch (SQLException ex) {
    connection.rollback();
    throw ex;
} finally {
    connection.setAutoCommit(previousAutoCommit);
}
```

Đoạn code giả định `connection` đã tồn tại và code nằm trong method ném hoặc xử lý `SQLException`. Trong môi trường connection pool/transaction manager, không được tự thay autoCommit trái với contract framework.

### 22.2. Giữ cursor/transaction quá lâu cũng nguy hiểm

Streaming một ResultSet qua transaction kéo dài hàng giờ có thể:

- Giữ connection, làm pool cạn.
- Giữ snapshot/resource, ảnh hưởng VACUUM trong một số tình huống.
- Tạo backpressure khó xử lý.
- Khi client đọc chậm, query/transaction không thể hoàn tất.

Với dữ liệu xuất rất lớn, có thể thiết kế **batch theo keyset**, background export và ghi dần ra file/stream bên ngoài transaction dài nếu yêu cầu cho phép.

### 22.3. Fetch size không sửa SELECT *

Nếu query lấy 100 cột nhưng UI chỉ dùng ba, fetch theo batch vẫn đọc và gửi 100 cột cho mỗi row. Nên dùng cả **projection** và **batching/pagination**.

## 23. Streaming và giới hạn ứng dụng khác gì giới hạn SQL?

Một API có thể trả dữ liệu streaming:

```text
PostgreSQL -> JDBC fetch batches -> ứng dụng ghi dần HTTP stream
```

Mô hình này giúp không phải giữ mọi row trong Java heap cùng lúc, nhưng:

- Không giảm tổng số rows xử lý nếu vẫn duyệt hết.
- Không tự giảm tổng network traffic giữa DB và ứng dụng.
- Kết nối DB có thể bị giữ suốt thời gian streaming.
- Client chậm hoặc ngắt kết nối cần xử lý hủy/cancel, đóng tài nguyên.

**Streaming giải quyết memory footprint**, còn `WHERE`, projection, pagination và business filters giải quyết **khối lượng dữ liệu thực sự cần lấy**.

### 23.1. Batch API thay vì trả hàng trăm nghìn rows trên một request

Với endpoint người dùng cuối, thường nên:

- Giới hạn `page_size` tối đa.
- Dùng keyset cho trang sâu.
- Chỉ trả trường cần thiết.
- Cân nhắc endpoint download/export riêng cho dữ liệu lớn.
- Có quota, deadline và cơ chế cancel.

Không cho client truyền `limit=1000000000` không kiểm soát chỉ vì SQL hỗ trợ LIMIT.

## 24. EXISTS thay vì tải collection để chỉ kiểm tra có hay không

Một anti-pattern:

```java
List<OrderItem> items = itemRepository.findByOrderId(orderId);
boolean hasItems = !items.isEmpty();
```

Nếu chỉ cần kiểm tra có item:

```sql
SELECT EXISTS (
    SELECT 1
    FROM app_fetch_lab.order_items
    WHERE order_id = 50000
) AS has_items;
```

PostgreSQL có thể dừng khi tìm được bằng chứng tồn tại, không cần trả tất cả item rows.

### 24.1. Dùng COUNT khi cần số lượng, không chỉ sự tồn tại

```sql
SELECT COUNT(*) AS item_count
FROM app_fetch_lab.order_items
WHERE order_id = 50000;
```

COUNT trả đúng số lượng theo snapshot, nhưng cần duyệt các rows/index entries phù hợp để tính. Nếu boolean là yêu cầu nghiệp vụ, `EXISTS` thường phù hợp hơn.

### 24.2. Tránh N+1 COUNT

Sai:

```text
1 SELECT 20 orders
20 SELECT COUNT(*) WHERE order_id = ?
```

Tốt hơn: aggregate counts cho các IDs đã chọn:

```sql
SELECT
    order_id,
    COUNT(*) AS item_count
FROM app_fetch_lab.order_items
WHERE order_id = ANY(ARRAY[49998,49999,50000]::bigint[])
GROUP BY order_id;
```

Nếu một order không có item, nó có thể **không xuất hiện trong GROUP BY result**. Khi ghép tại Java, mặc định count 0 cho những order IDs không có group.

## 25. Thay N+1 aggregate bằng GROUP BY hoặc correlated query đúng chỗ

Ví dụ dashboard 20 khách cần số đơn và tổng tiền:

**Sai về pattern:**

```text
SELECT 20 customers
for each customer:
    SELECT COUNT(*), SUM(total_amount)
    FROM orders WHERE customer_id = ?
```

**Một query tổng hợp:**

```sql
SELECT
    c.customer_id,
    c.customer_name,
    COUNT(o.order_id) AS order_count,
    COALESCE(SUM(o.total_amount), 0) AS total_amount
FROM app_fetch_lab.customers AS c
LEFT JOIN app_fetch_lab.orders AS o
  ON o.customer_id = c.customer_id
WHERE c.customer_id BETWEEN 1 AND 20
GROUP BY c.customer_id, c.customer_name
ORDER BY c.customer_id;
```

Chú ý `COUNT(o.order_id)` chứ không phải `COUNT(*)` với LEFT JOIN, vì một customer không có order vẫn có **một row NULL phía order** trong join result, làm COUNT(*) trả 1 không đúng.

### 25.1. Tránh aggregate toàn bảng khi chỉ cần 20 khách

Một query tổng hợp 50.000 orders cho mọi customer rồi mới lọc 20 khách có thể xử lý nhiều dữ liệu thừa. Nếu biết tập customer IDs cần hiển thị, hãy lọc sớm khi có thể.

### 25.2. Correlated subquery là N+1 không?

```sql
SELECT
    c.customer_id,
    (SELECT COUNT(*)
     FROM app_fetch_lab.orders AS o
     WHERE o.customer_id = c.customer_id) AS order_count
FROM app_fetch_lab.customers AS c
WHERE c.customer_id BETWEEN 1 AND 20;
```

Đây là **một câu SQL**, không phải 21 network round trips. Nhưng PostgreSQL có thể thực thi subquery nhiều lần (*SubPlan loops*), tùy kế hoạch. Với index customer_id và ít parents có thể hợp lý; với nhiều parents có thể chậm.

**Cần phân biệt application-level N+1 và server-side repeated work.** Xem `EXPLAIN ANALYZE`, số loops và buffers để chọn query shape.

## 26. Lựa chọn index sau khi sửa N+1

Khi ứng dụng chuyển 20 queries:

```sql
SELECT * FROM app_fetch_lab.order_items WHERE order_id = ?;
```

sang một batch query:

```sql
SELECT order_id, product_code, quantity
FROM app_fetch_lab.order_items
WHERE order_id = ANY(?);
```

chỉ mục:

```sql
CREATE INDEX idx_example_items_order
ON app_fetch_lab.order_items(order_id);
```

có thể hữu ích. Trong lab đã có `idx_app_items_order` nên **không cần tạo thêm một index cùng key**.

### 26.1. Index cho ORDER BY và LIMIT

Một query page:

```sql
SELECT order_id, ordered_at, total_amount
FROM app_fetch_lab.orders
WHERE customer_id = 42
ORDER BY ordered_at DESC, order_id DESC
LIMIT 20;
```

phù hợp với index:

```sql
ON app_fetch_lab.orders
    (customer_id, ordered_at DESC, order_id DESC)
```

đã tạo trong lab. Index giúp tìm và lấy page sớm, thay vì chuyển cả danh sách sang Java để sort/cắt.

### 26.2. INCLUDE/covering index khi thực sự có lợi

Nếu màn hình luôn lấy `total_amount` cùng key page, có thể cân nhắc:

```sql
CREATE INDEX idx_example_orders_cover
ON app_fetch_lab.orders
    (customer_id, ordered_at DESC, order_id DESC)
INCLUDE (total_amount);
```

Đây là **đề xuất để đo**, không phải bắt buộc. Chỉ mục rộng tăng dung lượng và chi phí ghi; Index Only Scan còn phụ thuộc visibility map. Không tạo chồng index trùng mà không đánh giá tác động.

### 26.3. Query gộp có thể cần index khác query cũ

Một query JOIN/GROUP BY/batch có access pattern khác nhiều truy vấn theo PK trước đây. Sau khi sửa N+1, **đọc plan của SQL mới** và tối ưu index cho workload mới, thay vì cho rằng các index tối ưu query cũ sẽ luôn đủ.

## 27. EXPLAIN (ANALYZE, BUFFERS): đo từng query, nhưng chưa đủ cho N+1

Đo một câu SQL:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT
    customer_id,
    customer_name
FROM app_fetch_lab.customers
WHERE customer_id = 781;
```

Bạn có thể thấy Index Scan chỉ mất một phần nhỏ mili giây. Điều đó **không bác bỏ N+1**, vì:

- Mỗi SELECT được thực thi nhiều lần từ application.
- EXPLAIN đo lần chạy hiện tại bên trong server, không cộng mọi network round trips và object mapping.
- Thời gian request còn gồm connection pool/driver/serialization.

### 27.1. Đo query gộp

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT
    o.order_id,
    o.ordered_at,
    o.total_amount,
    c.customer_name
FROM app_fetch_lab.orders AS o
JOIN app_fetch_lab.customers AS c
  ON c.customer_id = o.customer_id
ORDER BY o.ordered_at DESC, o.order_id DESC
LIMIT 20;
```

Quan sát:

- `Seq Scan`, `Index Scan`, `Nested Loop` hoặc `Hash Join`.
- `rows` ước tính và `actual rows`.
- `loops` của inner scan.
- `Buffers: shared hit/read`.
- `Execution Time`.

**Số rows của SQL gộp có thể lớn hơn rows ở một query con**, nhưng tổng application latency vẫn giảm vì ít round trips.

### 27.2. Đọc width và Rows Removed

Với overfetch, xem:

- `width` ước tính mỗi row.
- `actual rows` của các node.
- `Rows Removed by Filter`.
- Sort Method/memory/temp disk nếu SQL sort tập lớn.

Nếu chỉ cần 20 row mà kế hoạch đang xử lý hàng chục nghìn row, xem có thể đẩy filter/limit hoặc dùng index để trả sớm hay không.

### 27.3. EXPLAIN ANALYZE có overhead

Nó thực thi query và đo thông tin. Với query nặng, cần chạy trên môi trường phù hợp. Không phát hàng nghìn lệnh EXPLAIN ANALYZE production chỉ để gom mẫu; hãy kết hợp thống kê hệ thống và tracing có sampling.

## 28. pg_stat_statements: phát hiện SQL chạy rất nhiều lần

Extension `pg_stat_statements` có thể thống kê các câu lệnh SQL đã thực thi theo dạng normalized query.

Khi được admin cấu hình đúng, một query quan sát:

```sql
SELECT
    query,
    calls,
    total_exec_time,
    mean_exec_time,
    rows
FROM pg_stat_statements
ORDER BY calls DESC
LIMIT 20;
```

Tên view và các cột trên phù hợp với các phiên bản PostgreSQL hiện đại có extension tương ứng. Nếu extension chưa được bật/cấp quyền, query sẽ không chạy; không tự kích hoạt `shared_preload_libraries` hoặc restart production chỉ vì bài lab.

### 28.1. N+1 có dấu vết gì?

Một query normalized:

```sql
SELECT customer_id, customer_name
FROM customers
WHERE customer_id = $1
```

có thể có:

- `calls` rất cao so với số request.
- `mean_exec_time` thấp.
- `total_exec_time` đáng kể vì số lần nhiều.

Đây là **tín hiệu**, chưa đủ chứng minh N+1. Cùng query theo PK có thể được gọi nhiều lần bởi các request hợp lệ và nhiều người dùng khác nhau.

### 28.2. Vì sao pg_stat_statements không tự biết “một HTTP request”?

View tổng hợp theo câu lệnh ở cấp database/role/query identity, **không tự biết** `requestId`, user journey hoặc vòng lặp Java nào tạo truy vấn.

Để chứng minh N+1, cần kết hợp với:

- Instrumentation JDBC/ORM.
- Trace span hoặc request ID.
- Query count per request.
- SQL template + bind values được xử lý an toàn.
- Endpoint và kích thước N của kết quả chính.

### 28.3. Cần đọc tổng runtime và calls cùng nhau

Một query có mean 0,2 ms và calls 1 triệu có thể là vấn đề workload đáng kể dù từng lần nhanh. Ngược lại, một query 500 ms chạy mỗi ngày một lần có thể ít ảnh hưởng hơn endpoint thường xuyên.

Tối ưu theo **tổng tải và yêu cầu latency**, không chỉ “top slowest query”.

## 29. App tracing và SQL logging: cách bắt N+1 thật

Một hệ thống nên có thông tin:

```text
HTTP GET /orders?pageSize=20   request_id=abc
  db.query SELECT orders...      1 lần
  db.query SELECT customer...   20 lần
  mapper/serialization...
```

Từ đó:

1. Đếm SQL theo request.
2. Gom theo SQL template thay vì coi ID khác nhau là query khác nhau.
3. So query count với page size.
4. Phân loại query phát từ controller/service/mapper/serializer.
5. Đo latency và số rows/bytes.

### 29.1. Log bind parameters một cách an toàn

Không log plaintext các tham số nhạy cảm như token, email cá nhân, thẻ thanh toán hoặc payload dữ liệu khách hàng chỉ để debug N+1. Có thể log:

- SQL fingerprint/template.
- Loại tham số.
- Số lượng IDs trong batch.
- Query duration.
- Request correlation ID.
- Row count và byte estimate phù hợp.

### 29.2. Sampling và overhead

Ghi mọi SQL kèm stack trace trên production có thể tạo tải/log volume và rủi ro dữ liệu. Dùng tracing/sampling hoặc chế độ debug có thời hạn, phù hợp chính sách bảo mật.

### 29.3. Hibernate statistics

Với ORM, có thể sử dụng cơ chế statistics/log SQL hoặc metrics ở repository/session để đếm:

- Query execution count.
- Entity/collection fetch count.
- Lazy loading phát sinh.
- Query cache hits/misses nếu có.

Không nhầm **entity fetch count** với **SQL statement count** trong mọi provider. Một query có thể load nhiều entity; batch fetching thay đổi mối quan hệ đó.

## 30. Đo lượng dữ liệu: rows, columns và bytes

Ứng dụng không nên chỉ đo SQL duration. Một endpoint trả 20 items nhưng DB gửi 50.000 rows có thể tốn network/GC lớn.

### 30.1. Các đơn vị cần phân biệt

| Chỉ số | Ý nghĩa |
| --- | --- |
| Queries/request | Số SQL statements phát ra |
| Round trips/request | Số lượt tương tác client–DB; có thể khác queries vì protocol/batching |
| Rows returned từ DB | Số row đến driver, kể cả join rows bị map lại |
| Selected columns | Những giá trị SQL thực sự được trả |
| Estimated row width | Ước lượng byte/row trong plan |
| Network bytes | Dữ liệu truyền thực qua protocol và payload |
| Application objects allocated | Đối tượng được mapper tạo |
| API response bytes | Dữ liệu HTTP trả client |
| Heap allocation/GC | Chi phí bộ nhớ Java |

### 30.2. Đừng dùng API JSON size làm đại diện duy nhất

Một ORM có thể tải 50.000 orders rồi trả JSON của 20 orders. HTTP response nhỏ nhưng PostgreSQL đã gửi 50.000 rows cho ứng dụng.

Tương tự, ORM có thể khử trùng lặp 600 joined rows thành 20 parent objects. JSON response chỉ 20 parents, nhưng JDBC vẫn nhận nhiều row kết quả.

### 30.3. Ước lượng dữ liệu truyền

Lấy một ví dụ giả định:

```text
100.000 rows × 500 bytes/row ≈ 50 MB dữ liệu thô
20 rows × 80 bytes/row ≈ 1,6 KB dữ liệu thô
```

Đây là so sánh thô, chưa tính protocol, encoding, text/binary representation, null bitmap, nén, TLS và object overhead. Con số thực đo ở driver/network có thể khác nhiều, nhưng tỷ lệ cho thấy tại sao overfetch có thể nguy hiểm.

## 31. Tránh SELECT nhiều hàng rồi tính trong Java nếu SQL làm được

Ví dụ ứng dụng chỉ muốn tổng doanh thu các đơn PAID:

**Không cần tải mọi đơn về Java:**

```sql
SELECT
    COUNT(*) AS paid_orders,
    COALESCE(SUM(total_amount), 0) AS revenue
FROM app_fetch_lab.orders
WHERE status = 'PAID';
```

Database trả **một hàng kết quả** thay vì hàng chục nghìn rows. Tuy nhiên, PostgreSQL vẫn có thể phải scan/index để tính toán; giảm data transfer không làm công việc server bằng 0.

### 31.1. Tổng hợp theo khách

```sql
SELECT
    customer_id,
    COUNT(*) AS order_count,
    SUM(total_amount) AS revenue
FROM app_fetch_lab.orders
WHERE status = 'PAID'
GROUP BY customer_id
ORDER BY revenue DESC, customer_id
LIMIT 10;
```

Tập đầu ra chỉ tối đa 10 hàng, nhưng truy vấn có thể phải tổng hợp rất nhiều đơn. Đây là trường hợp **server-side processing thay application-side overfetch**; cần index/aggregation strategy theo workload.

### 31.2. Không tối ưu sai nghiệp vụ

Nếu ứng dụng cần tính thuế bằng một service ngoài hoặc một hàm Java đặc biệt, có thể không chuyển toàn bộ sang SUM thuần SQL được. Nhưng vẫn nên lọc đúng phạm vi thời gian, khách, trạng thái và chọn các cột cần thiết trước khi chuyển dữ liệu ra ngoài DB.

## 32. Filtering ở DB và quyền dữ liệu

Một query không nên tải mọi tenant rồi lọc trong Java:

```java
List<Order> all = repository.findAll();
List<Order> tenantOrders = all.stream()
    .filter(o -> o.getTenantId().equals(currentTenant))
    .toList();
```

Ngoài overfetch, cách này có thể làm dữ liệu của tenant khác vào tiến trình ứng dụng, tăng rủi ro truy cập và logging.

Thiết kế phù hợp hơn:

```sql
SELECT
    order_id,
    ordered_at,
    total_amount
FROM tenant_orders
WHERE tenant_id = $1
ORDER BY ordered_at DESC, order_id DESC
LIMIT 20;
```

Đây là SQL minh họa một schema multi-tenant chưa tạo trong lab.

### 32.1. Index không thay thế authorization

Thêm `tenant_id` vào index giúp truy vấn nhanh hơn, nhưng không đảm bảo an toàn. Cần xác thực, phân quyền, row-level security khi phù hợp và kiểm tra tenant predicate nhất quán.

### 32.2. Giới hạn row ở database nhưng vẫn cần kiểm tra input

Ngay cả khi có `LIMIT ?`, client không nên được yêu cầu LIMIT cực lớn. Ứng dụng cần validation min/max page size theo API contract.

## 33. Bộ nhớ, GC và ORM persistence context

Khi ORM tải hàng trăm nghìn entity:

- Mỗi entity có object overhead.
- Có thể có proxy, collection wrappers, dirty checking state.
- Persistence context giữ tham chiếu tới entities trong session.
- GC phải xử lý nhiều đối tượng và có thể tăng pause time.

Projection và pagination thường giảm footprint hơn một entity graph lớn.

### 33.1. Khi thực sự phải xử lý khối lượng lớn

Một batch job có thể cần duyệt toàn bộ dữ liệu. Khi đó:

1. Chia batch theo primary key hoặc mốc thời gian ổn định.
2. Giới hạn cột và số hàng mỗi batch.
3. Commit/clear persistence context theo chiến lược framework.
4. Dùng idempotency và checkpoint để retry sau crash.
5. Tránh giữ transaction hoặc DB connection quá lâu.

Đừng gọi `findAll()` rồi giữ một danh sách hàng triệu entity trong memory chỉ vì “job sẽ xử lý hết”.

### 33.2. Cursor và ORM streams vẫn có giới hạn

Một ORM stream có thể dựa trên ResultSet/cursor hoặc một cơ chế khác; hành vi phải xác nhận theo provider. Ngay cả khi stream, nếu code `collect(toList())` toàn bộ, bạn vẫn có thể tạo memory footprint khổng lồ.

## 34. N+1 trong GraphQL và các resolver

Một GraphQL query:

```graphql
query {
  orders(first: 20) {
    id
    customer {
      name
    }
  }
}
```

có thể khiến resolver `customer` được gọi 20 lần. Nếu mỗi resolver gọi database, ta có N+1.

### 34.1. DataLoader/batching

Thay vì load từng customer:

```text
load(781)
load(782)
load(783)
...
```

một batch loader gom IDs trong cùng phạm vi request:

```sql
SELECT customer_id, customer_name
FROM app_fetch_lab.customers
WHERE customer_id = ANY(?);
```

Sau đó map kết quả về đúng thứ tự các khóa được yêu cầu.

### 34.2. Phải giữ cache scope phù hợp

DataLoader cache thường nên được thiết kế theo **request/user/security scope** phù hợp. Không tạo global cache chứa dữ liệu tenant khác mà thiếu phân quyền và invalidation.

### 34.3. GraphQL còn có overfetch không?

Có. Dù GraphQL client chỉ yêu cầu `customer.name`, resolver backend vẫn có thể gọi ORM `findAll()` hoặc SELECT * rồi tải toàn bộ quan hệ. Việc client chọn trường **không tự bảo đảm database chỉ đọc đúng trường ấy**; resolver phải sử dụng projection/fetch plan phù hợp.

## 35. Cache: giảm N+1 hay che vấn đề?

Cache customer theo ID có thể làm một số lookup không chạm DB:

```text
request: 20 orders
lookup customer #1 -> cache hit
lookup customer #2 -> cache miss -> SQL
...
```

Nhưng khi cache lạnh, N+1 lại xuất hiện. Không nên coi “p95 hiện tại ổn vì cache nóng” là bằng chứng cách truy cập dữ liệu hiệu quả.

### 35.1. Các rủi ro cache

- Invalidation khi customer đổi tên.
- Memory usage và eviction.
- Cache stampede khi nhiều request cùng miss.
- Stale reads nếu nghiệp vụ đòi nhất quán mạnh.
- Phạm vi quyền/tenant và key design.

Cache là một công cụ hữu ích khi có lý do rõ ràng, **không thay thế việc thiết kế data access giảm round trips**.

### 35.2. Query caching không tự ghép quan hệ

ORM query cache, entity cache và JDBC statement cache là các cơ chế khác nhau. Một prepared statement được cache không làm 20 lần EXECUTE tự động biến thành một query batch.

## 36. Batch size: chọn theo dữ liệu và giới hạn thực

Giả sử cần lấy customer cho 10.000 orders. Ta không nhất thiết phải gửi 10.000 IDs một lần nếu:

- Parameter/array trở nên lớn.
- Truy vấn mất nhiều memory/planning time.
- Result set chứa dữ liệu rộng.
- Connection/transaction có thời gian giới hạn.
- Application có SLA theo batch nhỏ hơn.

Có thể chia IDs thành các batch như 200–1.000, nhưng **không có con số chung tối ưu**.

### 36.1. Đừng tạo 10.000 query một ID

Mẫu chia batch:

```text
uniqueCustomerIds = distinct(ids)
for each chunk of B IDs:
    SELECT ... WHERE id = ANY(chunk)
merge results into map
```

Số query xấp xỉ `ceil(U/B)` với `U` là số IDs duy nhất, cộng query lấy orders.

### 36.2. Đừng tăng batch size vô hạn

Một batch cực lớn có thể tạo độ trễ đầu tiên cao, memory spike và khó kiểm soát timeout. Nếu endpoint chỉ cần 20 orders thì điều quan trọng là **không tải 10.000 orders từ đầu**, hơn là tối ưu kỹ thuật batch fetch 10.000 khách.

## 37. Tính nhất quán khi dùng hai query thay một JOIN

Một JOIN trong một SQL statement dùng **một snapshot statement** theo quy tắc MVCC. Khi tách thành:

1. SELECT page orders.
2. SELECT customers/items theo IDs.

hai statement trong `READ COMMITTED` có thể thấy **hai trạng thái committed khác nhau** nếu có transaction đồng thời cập nhật giữa hai bước.

### 37.1. Ví dụ trạng thái đổi giữa hai query

```text
T1: SELECT orders (trả customer_id=42)
T2: UPDATE customer_name của #42; COMMIT
T1: SELECT customers WHERE id=42 (nhìn tên mới)
```

Không nhất thiết sai; nhiều màn hình chấp nhận đọc trạng thái mới nhất theo từng statement. Nhưng báo cáo tài chính hoặc snapshot export có thể cần sự nhất quán hơn.

### 37.2. Chọn chiến lược

- **Một JOIN statement:** các quan hệ được đọc theo snapshot của statement đó.
- **Transaction REPEATABLE READ:** khi cần snapshot ổn định qua nhiều SELECT trong cùng transaction, xét trade-offs của PostgreSQL và thời gian transaction.
- **Read model/denormalization:** khi cần endpoint rất ổn định và tải lớn, có thể duy trì projection đã materialize/cập nhật theo workflow.

Không giữ transaction đọc dài hàng chục phút chỉ để tránh một chênh lệch tên khách không quan trọng; transaction dài có thể ảnh hưởng VACUUM và resource.

### 37.3. Authorization giữa hai bước

Tập ID của parent đã lấy phải thuộc phạm vi người dùng được phép xem. Query batch children cũng cần bảo đảm không vô tình trả dữ liệu của parent ngoài phạm vi, đặc biệt khi ID có thể do client cung cấp.

## 38. Query timeout và cancellation

Một endpoint N+1 không nên được “chữa” bằng cách tăng timeout vô hạn. Nhưng việc đặt giới hạn giúp giảm hậu quả:

```sql
BEGIN;
SET LOCAL statement_timeout = '5s';

SELECT order_id, total_amount
FROM app_fetch_lab.orders
WHERE customer_id = 42
ORDER BY ordered_at DESC
LIMIT 20;

COMMIT;
```

Timeout trong ví dụ chỉ là minh họa; ngưỡng phải theo SLA và workload.

### 38.1. Timeout mỗi query khác timeout toàn request

Nếu ứng dụng chạy 100 queries, mỗi query dưới 5 giây, tổng request vẫn có thể rất chậm. `statement_timeout` giới hạn mỗi statement ở PostgreSQL, **không phải ngân sách thời gian tổng cho mọi truy vấn của request**.

Cần timeout ở tầng request/client, cancellation và metrics để phát hiện số query thừa.

### 38.2. Đừng chờ database khi client đã hủy request

Ứng dụng nên có cơ chế đóng ResultSet/Statement, hủy công việc phù hợp và giải phóng connection khi request không còn cần kết quả. Không để một export bị hủy tiếp tục tải hàng triệu hàng vô ích.

## 39. Khi nào một truy vấn lớn tốt hơn nhiều truy vấn nhỏ?

**Thường tốt hơn** khi:

- Dữ liệu có quan hệ many-to-one.
- Kết quả cần là một page nhỏ và projection hẹp.
- Join có cardinality kiểm soát được.
- SQL có thể lọc và sort sớm.
- Index và thống kê phù hợp.

**Có thể không tốt hơn** khi:

- JOIN nhiều one-to-many collections tạo tổ hợp quá lớn.
- Một bên chứa TEXT/JSONB rất rộng bị lặp trên mỗi joined row.
- Query monolithic khiến planner phải sort/aggregate lượng dữ liệu khổng lồ.
- Mỗi collection cần pagination hoặc top-K độc lập.
- Các miền dữ liệu dùng cơ chế bảo mật/snapshot khác nhau.

Một phương án **2–4 batch queries** với tập parent đã bị giới hạn thường là giải pháp thực dụng.

### 39.1. Đừng đếm query mà bỏ qua bytes

So sánh hai phương án:

```text
Phương án A:
  1 SQL
  200.000 joined rows
  nhiều parent fields bị lặp

Phương án B:
  3 SQL
  100 parent rows
  300 item rows
  150 shipment rows
```

B có thể hiệu quả hơn A dù số SQL nhiều hơn. Cần đo thực tế thay vì đặt “query count = 1” làm mục tiêu duy nhất.

## 40. Quy trình sửa N+1 trên một endpoint

Một quy trình có thể áp dụng:

1. **Tái hiện request cụ thể** với page size và dữ liệu đại diện.
2. **Ghi query count**, các SQL templates và thời gian toàn request.
3. **Tìm query lặp theo ID** (customer, items, status, counts...).
4. **Xác định ai kích hoạt**: controller, service, lazy association, mapper, serializer.
5. **Xác định màn hình thật sự cần gì**, bao nhiêu parent/children và cột nào.
6. **Giới hạn parent page từ SQL**, không tải toàn bảng.
7. **Chọn cách fetch quan hệ**: JOIN cho many-to-one; batch fetching/CTE page + JOIN cho one-to-many.
8. **Kiểm tra cardinality**: một-to-một, nhiều-to-một hay một-to-nhiều, có nhiều collection không?
9. **Tránh JOIN làm sai pagination hoặc aggregate**.
10. **Dùng DTO projection** và bỏ cột/payload không cần.
11. **Đo query gộp** bằng EXPLAIN ANALYZE, Buffers và số hàng trả.
12. **Đánh giá index** cho WHERE/JOIN/ORDER BY mới.
13. **Đo lại app latency**, query count, rows/bytes, memory/GC, throughput.
14. **Kiểm tra tính đúng**: thứ tự, parent không có children, tổng tiền, quyền tenant, snapshot.
15. **Thêm regression test** để không vô tình quay lại N+1.

## 41. Kiểm thử chống N+1

Một bài test chỉ kiểm tra HTTP 200 và JSON đúng chưa đủ. Endpoint có thể trả đúng nhưng thực hiện 101 SQL cho một trang.

### 41.1. Ý tưởng test query count

```text
Arrange:
  tạo 50 orders, mỗi order có customer/items phù hợp
  reset query counter trong phạm vi request

Act:
  gọi endpoint GET /orders?limit=20

Assert:
  kết quả đúng 20 orders và tên khách/items đúng
  số SQL statements không tăng tuyến tính theo page size
```

Không nhất thiết ép luôn đúng **1 query**. Nếu giải pháp dùng parent page + batch children + batch customers, test có thể chấp nhận **3 queries** và xem đó là contract hợp lý.

### 41.2. Test nhiều kích thước trang

Chạy cùng endpoint với N = 1, 10, 20, 50.

| N | Mẫu N+1 | Mẫu batch 2 query |
| ---: | ---: | ---: |
| 1 | 2 | 2 |
| 10 | 11 | 2 |
| 20 | 21 | 2 |
| 50 | 51 | 2 |

Đây là bảng lý tưởng hóa khi mỗi parent tạo đúng một lookup DB và batch luôn trong một query. ORM cache, số customer IDs duy nhất, nhiều collection hoặc batch size cụ thể có thể làm số thực khác; test cần tập dữ liệu đại diện.

### 41.3. Test overfetch

Ngoài query count:

- Xác minh query trả đúng page size (trừ JOIN rows có kiểm soát).
- Không SELECT * nếu API chỉ cần vài cột.
- Không load toàn collection khi chỉ cần COUNT/EXISTS.
- Dữ liệu item dài và parent có nhiều child để test row multiplication.
- Kiểm tra memory/time với dataset lớn.

### 41.4. Test không bị cache che

Một ORM session có sẵn entity cache có thể khiến test N+1 “đậu” khi cache nóng. Cần setup tạo dữ liệu, clear persistence context hoặc kiểm soát cache phù hợp để quan sát hành vi DB khi cache lạnh.

## 42. Benchmark một bản sửa N+1 đúng cách

**Trước sửa:**

```text
Request: GET /orders?limit=50
SQL:      1 order query + 50 customer queries
Rows:     50 orders + 50 customer rows
Mapping:  50 orders + 50 customers
```

**Sau sửa bằng JOIN:**

```text
Request: GET /orders?limit=50
SQL:      1 join query
Rows:     50 joined rows (many-to-one)
Mapping:  50 DTOs
```

Kết quả dự kiến là giảm round trips, nhưng **phải đo**:

- P50/P95/P99 request latency.
- SQL count/request.
- DB execution time, CPU, buffers.
- Rows and bytes from DB.
- Connection pool wait.
- JVM allocation/GC.
- Tải concurrent và throughput.

### 42.1. Benchmark trong môi trường đại diện

Một query trong lab 50.000 orders có thể đủ để hiểu cơ chế, nhưng không chứng minh latency ở production khi có:

- Hàng trăm triệu records.
- Phân bố khách hàng lệch.
- Một số order có hàng nghìn items.
- Network qua vùng triển khai khác.
- Pool saturation, CPU/I/O contention.
- VACUUM, bloat, statistics khác.

Đo trên staging/profiling environment phù hợp rồi rollout có quan sát.

### 42.2. Đánh giá cả rủi ro regression

Khi đổi fetch strategy:

- Có trả thiếu orders không?
- Có duplicate orders/items không?
- Có sai tổng tiền do JOIN fan-out không?
- Có giảm/đổi isolation semantics không?
- Có trả dữ liệu tenant khác không?
- Có làm quá tải database bằng một query khổng lồ không?

Hiệu năng tăng nhưng kết quả sai không được xem là tối ưu thành công.

## 43. Các lỗi hiểu nhầm thường gặp

| Hiểu nhầm | Thực tế |
| --- | --- |
| Mỗi SQL chạy 0,5 ms nên không thể N+1 | Hàng trăm round trips và mapping vẫn rất tốn |
| N+1 chỉ xảy ra khi viết SQL trong vòng for | Lazy ORM, mapper, serializer, GraphQL resolver có thể kích hoạt |
| EAGER mọi association là cách chữa N+1 | Có thể gây overfetch và query khó kiểm soát |
| JOIN mọi collection thành một query luôn nhanh | Có thể nhân rows và phá pagination |
| LEFT JOIN + LIMIT 20 nghĩa 20 parent rows | LIMIT áp dụng trên joined result rows |
| DISTINCT sẽ sửa mọi cartesian join | Có thể không loại duplicate theo identity và gây sort lớn |
| Batch fetch không cần giới hạn parent | Batch IDs quá lớn vẫn là overfetch |
| WHERE id IN (...) luôn trả theo thứ tự IDs | Không có ORDER BY thì thứ tự không bảo đảm |
| Có fetchSize=500 thì SQL chỉ trả tối đa 500 hàng | Fetch size là batch hint, không phải LIMIT |
| Stream ResultSet nghĩa DB không gửi nhiều dữ liệu | Nếu đọc hết vẫn truyền đủ rows |
| Dùng SELECT * rồi serializer bỏ bớt field là đủ | Cột rộng đã được fetch từ DB |
| LIMIT trong Java Stream giúp database đọc ít hơn | Java limit áp sau khi dữ liệu đã được lấy |
| Query count thấp nghĩa hiệu năng chắc tốt | Một JOIN có thể trả hàng triệu rows |
| HTTP response nhỏ nghĩa DB payload nhỏ | ORM có thể tải rất nhiều rows rồi loại |
| COUNT(*) là metadata trả O(1) trong PostgreSQL | Count chính xác có chi phí đọc phù hợp MVCC |
| EXISTS và COUNT(*) giống nhau khi chỉ cần boolean | EXISTS có thể dừng khi tìm thấy một hàng |
| Query gộp không còn repeated inner work | Correlated subquery/LATERAL có thể loops=N trong plan |
| Index trên FK tự có ở mọi bảng con | PostgreSQL không tự tạo index referencing FK column |
| Cache nóng nghĩa thiết kế không N+1 | Cold cache có thể tái hiện |
| pg_stat_statements tự chỉ ra request nào N+1 | Cần request tracing/query count |
| Một JOIN và hai batch queries có snapshot như nhau | Hai statements ở READ COMMITTED có thể thấy commit khác nhau |
| Keyset đảm bảo snapshot vĩnh viễn | Nó không ngăn concurrent deletes/updates |
| Tăng pool/timeout là giải pháp N+1 | Có thể làm database quá tải mà không giảm query thừa |
| Cải thiện EXPLAIN của một query là xong | Cần đo toàn request, DB bytes, rows và mapping |

## 44. Bài tập thực hành PostgreSQL và Java

Các bài SQL sử dụng schema `app_fetch_lab`. Với bài Java/JPA, có thể viết pseudocode hoặc dùng project học tập có driver và entity mapping tương ứng.

1. **Khái niệm:** giải thích N+1 trong endpoint trả 50 đơn và tên khách, nêu số SQL lý tưởng hóa.
2. **Đếm truy vấn:** nếu một trang có 30 orders và mỗi order gọi 1 SELECT customer, tính số queries; nếu còn gọi SELECT items từng order, tổng tăng ra sao?
3. **Dữ liệu lab:** tạo ba bảng customers/orders/order_items và nạp dữ liệu theo script.
4. **N+1 many-to-one:** viết SELECT 20 orders và một SELECT customer theo ID; chỉ ra bước nào lặp trong Java.
5. **JOIN:** viết một SQL lấy 20 orders với customer_name mà không phát N queries.
6. **Cardinality:** vì sao JOIN many-to-one không nhân order rows khi FK hợp lệ và customer_id unique?
7. **EXPLAIN:** đo JOIN bằng EXPLAIN ANALYZE BUFFERS; quan sát Index Scan/Hash Join/Nested Loop và loops.
8. **Batch IDs:** dùng `WHERE customer_id = ANY(ARRAY[...]::integer[])` để lấy nhiều customers một lần.
9. **Distinct IDs:** vì sao nên deduplicate customer IDs trước khi batch fetch?
10. **Thứ tự:** vì sao kết quả IN/ANY không có ORDER BY không đảm bảo giữ thứ tự danh sách IDs?
11. **Map DTO:** tạo pseudocode Java dùng `Map<Integer,CustomerDto>` để ghép orders và customers.
12. **One-to-many:** viết cách N+1 lấy items cho 20 orders; thay bằng batch SELECT theo order IDs.
13. **LIMIT sau JOIN:** chạy JOIN orders/items rồi LIMIT 20. Vì sao không chắc có 20 orders?
14. **Parent page CTE:** chọn 20 orders trong CTE trước rồi JOIN items; so số parent và số joined rows.
15. **Missing children:** bảo đảm một order không có item vẫn xuất hiện trong kết quả với danh sách rỗng.
16. **JOIN fan-out:** nếu một order có 3 items, 4 shipments và 5 payments, output JOIN có thể có bao nhiêu rows?
17. **Nhiều collections:** đề xuất chiến lược 1 parent page + 3 batch queries và giải thích vì sao có thể tốt hơn một JOIN.
18. **JSON aggregation:** dùng jsonb_agg + FILTER + COALESCE để gom items của 20 orders thành một cột JSON cho mỗi order.
19. **LATERAL:** viết query lấy top 2 items/order, xem loops của inner plan; vì sao một SQL vẫn có repeated work?
20. **Aggregate counts:** thay 20 SELECT COUNT(*) theo order bằng một GROUP BY order_id cho page IDs.
21. **COUNT(*) LEFT JOIN:** vì sao COUNT(*) có thể trả 1 cho customer không có order? Dùng COUNT(o.order_id).
22. **EXISTS:** viết câu kiểm tra order 50000 có item không mà không tải collection.
23. **Projection:** so SELECT * với SELECT order_id, ordered_at, total_amount; đọc width trong EXPLAIN.
24. **TOAST:** vì sao lấy cột note/extra_data lớn không cần thiết có thể tăng data transfer?
25. **Filter tại DB:** thay Java findAll().filter(PAID) bằng SQL WHERE status='PAID'.
26. **Pagination:** viết LIMIT 20 OFFSET 20 có ORDER BY hai cột; giải thích tác dụng tie-breaker.
27. **Offset sâu:** đo OFFSET 40000 LIMIT 20, so với page đầu.
28. **Keyset:** viết query trang tiếp dùng tuple `(ordered_at,order_id)<(cursorTime,cursorId)`.
29. **Index:** giải thích tác dụng index `(customer_id,ordered_at DESC,order_id DESC)` cho danh sách một khách.
30. **Total count:** khi UI chỉ cần “còn trang tiếp?”, dùng LIMIT pageSize+1 và giải thích trade-off.
31. **Fetch size:** phân biệt JDBC `setFetchSize(500)` và SQL `LIMIT 500`.
32. **PgJDBC streaming:** phác họa một ResultSet fetch theo batch với autoCommit=false và đóng transaction đúng cách.
33. **GC:** tại sao 100.000 ORM entities có thể tạo heap/GC pressure dù JSON response nhỏ?
34. **Lazy loading:** xác định chỗ `order.getCustomer().getName()` có thể phát SQL ngoài ý muốn.
35. **EAGER:** vì sao đổi mọi association thành eager không phải phương án tối ưu phổ quát?
36. **JOIN FETCH:** giải thích sự khác nhau khi fetch many-to-one và one-to-many collection có pagination.
37. **DTO:** viết một JPQL constructor projection cho OrderSummaryDto.
38. **Batch size:** một danh sách có 2.300 distinct IDs, batch size 500; ước lượng số batch queries cần.
39. **GraphQL:** dùng DataLoader gom 20 resolver customer thành một batch query; vì sao loader cache cần request scope?
40. **Cache lạnh:** viết test chứng minh query count không tăng tuyến tính khi cache ORM chưa nóng.
41. **pg_stat_statements:** tìm query có calls cao, mean_exec_time thấp; vì sao chưa đủ kết luận N+1?
42. **Tracing:** đề xuất các trường request_id, query template, duration, row_count mà không log dữ liệu nhạy cảm.
43. **Rows vs API objects:** giải thích vì sao ORM trả 20 Orders có thể đã đọc 60 joined rows.
44. **Consistency:** hai batch queries ở READ COMMITTED có thể thấy hai snapshots khác nhau thế nào?
45. **Timeout:** vì sao statement_timeout 5s không bảo đảm request gồm 100 SQL hoàn tất dưới 5s?
46. **Regression test:** thử N=1,10,20,50 và lập bảng query count trước/sau batch fetch.
47. **Benchmark:** đo trước/sau theo P95 latency, SQL count, rows/bytes, BUFFERS, connection pool wait và JVM allocations.
48. **Nghiệp vụ multi-tenant:** giải thích vì sao không được tải mọi tenant rồi filter trên Java; đề xuất WHERE tenant_id và quyền tương ứng.
49. **Sửa endpoint tổng hợp:** trả Top 10 khách doanh thu cao; thay fetch toàn bộ orders sang GROUP BY + ORDER BY + LIMIT.
50. **Thiết kế hoàn chỉnh:** tạo kiến trúc GET /orders?limit=20 có customerName, itemCount và ba item đầu; chọn các query, khóa/cột, page strategy và giới hạn child rõ ràng.

## 45. Checklist review một endpoint truy cập PostgreSQL

Trước khi duyệt PR thêm endpoint hoặc thay đổi ORM mapping, hãy tự hỏi:

1. Endpoint phát **bao nhiêu SQL statements** cho N=1, 20, 100?
2. Có query template lặp theo parent ID không?
3. Lazy loading có được kích hoạt ở mapper/serializer không?
4. Có thể dùng JOIN cho many-to-one không?
5. Với one-to-many, có batch fetch theo parent IDs không?
6. Có collection fetch join với pagination gây lỗi/tải dư không?
7. Có JOIN nhiều collections khiến nhân số rows không?
8. Query parent có LIMIT rõ ràng ở PostgreSQL không?
9. ORDER BY có tie-breaker unique không?
10. Trang sâu có nên keyset thay OFFSET không?
11. Có dùng `SELECT *` hoặc entity đầy đủ chỉ để lấy vài fields không?
12. Có tải collection chỉ để COUNT/EXISTS không?
13. Cột TEXT/JSONB có thực sự cần ở response không?
14. JDBC fetch size/stream có bị nhầm với giới hạn hàng không?
15. Cursor và transaction có bị giữ quá lâu không?
16. Index có hỗ trợ WHERE/JOIN/ORDER BY của SQL mới không?
17. `EXPLAIN (ANALYZE, BUFFERS)` có hiện loops, rows, temp I/O bất thường không?
18. Có đo **rows và bytes** từ database thay vì chỉ JSON response size không?
19. Có rủi ro chênh snapshot khi tách thành nhiều query không?
20. Có giữ đúng tenant/authorization khi batch fetch không?
21. Có regression test với cache lạnh và nhiều parent khác nhau không?
22. Có đo latency/throughput/memory sau thay đổi trên dữ liệu đại diện không?

## 46. Tổng kết

Hai lỗi hiệu năng này có thể xuất hiện độc lập hoặc kết hợp:

```text
N+1 QUERIES
  1 query lấy parent list
  N query tìm related data cho từng parent
  -> nhiều round trips, overhead và pool pressure

Khắc phục:
  JOIN cho many-to-one
  batch fetch các IDs cho one-to-many
  tổng hợp theo group/EXISTS khi chỉ cần con số/boolean
  theo dõi actual query count trong request

OVERFETCHING
  SELECT * / findAll()
  filter + sort + limit trong Java
  JOIN nhiều collections nhân bản rows
  -> network bytes, mapping, heap memory, GC tăng

Khắc phục:
  WHERE, ORDER BY, LIMIT, keyset ngay ở PostgreSQL
  DTO projection chọn cột cần
  page parent trước khi join children
  fetch theo batch/stream khi cần xử lý dữ liệu lớn
  đo rows/width/bytes, không chỉ SQL count
```

Những nguyên tắc quan trọng nhất:

- **N+1 là bài toán ứng dụng–database**, không phải lỗi nhìn thấy từ một kế hoạch EXPLAIN đơn lẻ. Một query nhỏ chạy hàng trăm lần vẫn có thể làm endpoint chậm.
- **Giảm N+1 không có nghĩa mọi endpoint phải có đúng một SQL.** Một JOIN hợp lý cho many-to-one; hai hoặc vài batch queries có thể tốt hơn khi có nhiều one-to-many collections.
- **Phân trang parent trước khi JOIN children.** `LIMIT` sau JOIN giới hạn joined rows, không bảo đảm số parent cần hiển thị.
- **Tránh overfetch ngay trong SQL:** chỉ lấy cột cần thiết, chỉ lấy rows cần thiết, lọc/sort sớm ở PostgreSQL và chọn pagination phù hợp.
- **JDBC fetchSize/stream không tương đương LIMIT.** Chúng chủ yếu kiểm soát cách lấy và giữ dữ liệu trong ứng dụng, không làm giảm tổng số hàng phải xử lý khi bạn đọc hết.
- **Dùng EXPLAIN để hiểu từng SQL, dùng tracing/pg_stat_statements để hiểu tần suất và chi phí toàn workload.** Quan sát query count/request, total rows, network bytes, server buffers, JVM memory và P95/P99 latency.
- **Không tối ưu đánh đổi tính đúng:** tránh duplicate rows, sai COUNT/SUM, thiếu items, pagination sai, rò dữ liệu tenant và thay đổi snapshot không được chấp nhận.
- **Thêm test chống N+1 và overfetch với dữ liệu đại diện** để vấn đề không quay lại khi thay mapper, ORM association hay serializer.

Tóm lại, truy vấn tốt là truy vấn **lấy đúng dữ liệu cần thiết, trong số lượt tương tác hợp lý, với phạm vi hàng/cột và quan hệ được kiểm soát**. Khi kết hợp thiết kế SQL, truy cập dữ liệu Java và đo đạc thực tế, PostgreSQL có thể phục vụ endpoint nhanh hơn mà không tạo gánh nặng query thừa hoặc dữ liệu dư.
