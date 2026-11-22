# Phân chia trách nhiệm giữa câu lệnh SQL và mã ứng dụng

Một ứng dụng có thể nhận yêu cầu từ người dùng, kiểm tra dữ liệu, tính toán, đọc và ghi cơ sở dữ liệu, gọi dịch vụ thanh toán, gửi email rồi trả kết quả. Những bước đó cùng tạo nên một use case, nhưng **không có nghĩa tất cả đều nên nằm trong một lớp**.

SQL và mã ứng dụng có thế mạnh khác nhau:

- **SQL/database** phù hợp với dữ liệu quan hệ: lọc, JOIN, tổng hợp, sắp xếp, cập nhật theo tập, ràng buộc toàn vẹn, transaction và xử lý đồng thời.
- **Mã ứng dụng** phù hợp với request/response, xác thực người dùng, điều phối use case, quy tắc domain gắn với sản phẩm, tích hợp dịch vụ ngoài, retry, giao diện và trình bày.
- **Hai lớp phối hợp** để bảo đảm quy tắc nghiệp vụ: ứng dụng giúp kiểm tra sớm và trả lỗi dễ hiểu; database bảo vệ các bất biến dữ liệu phải đúng với mọi đường ghi.

Ví dụ, khi người dùng đặt hàng, ứng dụng hiểu người dùng là ai, đơn hàng thuộc tenant nào, chương trình khuyến mãi nào đang áp dụng và cần gửi thông báo gì. Database bảo đảm đơn hàng, dòng hàng, số lượng tồn kho và sự kiện cần phát được ghi nhất quán. Nếu ứng dụng chỉ đọc tồn kho rồi trừ ở một lệnh riêng, hai request đồng thời có thể cùng bán một đơn vị hàng cuối cùng.

Bài học thuộc chương **SQL trong ứng dụng** của module **Database SQL**. Nội dung giải thích cách chọn việc nào đặt trong câu lệnh SQL, việc nào đặt trong code ứng dụng, cách phối hợp validation, authorization, transaction, ORM/JDBC, hiệu năng, kiểm thử và migration.

> Ví dụ Java/JDBC và SQL trong bài là mẫu kiến trúc. Cú pháp phân trang, kiểu dữ liệu, locking và tính năng riêng có thể khác giữa PostgreSQL, MySQL/MariaDB, SQL Server, Oracle và SQLite. Thử DDL/DML trên database riêng trước khi áp dụng vào dữ liệu thật.

## 1. Vì sao phải phân chia trách nhiệm?

Một ứng dụng thường có hai môi trường thực thi chính:

```text
Người dùng / API / Batch job
          |
          v
Mã ứng dụng
- nhận request
- xác thực và phân quyền
- kiểm tra đầu vào
- điều phối use case
- gọi dịch vụ ngoài
          |
          v
Database driver / connection
          |
          v
Cơ sở dữ liệu
- SQL và query plan
- ràng buộc dữ liệu
- transaction và locking
- truy vấn / cập nhật
- lưu trữ bền vững
```

Nếu mọi việc được đưa về ứng dụng, dữ liệu quan hệ có thể bị tải quá nhiều, mỗi hàng lại phát sinh một query và các bước cập nhật có thể không còn nguyên tử. Nếu mọi việc được đưa vào database, stored procedure có thể biến thành một ứng dụng thứ hai khó kiểm thử, khó tích hợp HTTP và khó triển khai theo vòng đời sản phẩm.

### 1.1. Hai thái cực đều gây vấn đề

| Cách làm | Hậu quả |
|---|---|
| Tải toàn bộ bảng về Java rồi lọc | Tốn mạng, bộ nhớ và thời gian |
| Lặp từng hàng rồi query riêng | N+1 queries, nhiều round trip |
| Tính cùng một quy tắc ở nhiều service | Kết quả không nhất quán |
| Chỉ validate ở giao diện | API khác hoặc batch có thể ghi dữ liệu sai |
| Đưa toàn bộ workflow vào procedure | Khó gọi HTTP, email, queue và quản lý retry |
| Dùng ORM nhưng không xem SQL sinh ra | Overfetch, N+1, query plan kém |
| Commit sau mỗi bước dữ liệu liên quan | Có thể để lại trạng thái nửa hoàn thành |
| Giữ transaction mở khi chờ dịch vụ ngoài | Khóa lâu và chiếm connection |

Không có quy tắc “SQL luôn nhanh hơn Java” hay “mọi business logic phải ở application”. Cần xem **loại công việc, dữ liệu, tính nhất quán, quyền và chi phí vận hành**.

## 2. SQL nên đảm nhận những công việc nào?

SQL được thiết kế để xử lý **tập dữ liệu có quan hệ**. Những công việc sau thường phù hợp với database.

### 2.1. Lọc dữ liệu gần nơi lưu trữ

Không nên tải mọi đơn hàng rồi lọc ở Java:

```java
// Không phù hợp khi bảng orders rất lớn.
List<Order> allOrders = orderRepository.findAll();

List<Order> drafts = allOrders.stream()
    .filter(o -> o.getTenantId() == authorizedTenantId)
    .filter(o -> o.getStatus() == OrderStatus.DRAFT)
    .toList();
```

Hãy để SQL trả đúng tập dữ liệu cần:

```sql
SELECT order_id, status, total_amount
FROM orders
WHERE tenant_id = ?
  AND status = ?
ORDER BY order_id;
```

Database có thể dùng index, thống kê và query optimizer. Ứng dụng chỉ nhận những hàng cần thiết.

Tenant ID trong ví dụ phải lấy từ context đã xác thực phía server, không mặc nhiên tin tenant ID tùy ý do client gửi.

### 2.2. JOIN dữ liệu quan hệ

Nếu màn hình cần tên khách hàng của từng đơn, dùng JOIN:

```sql
SELECT
    o.order_id,
    o.created_at,
    o.total_amount,
    c.customer_name
FROM orders AS o
JOIN customers AS c
  ON c.customer_id = o.customer_id
 AND c.tenant_id = o.tenant_id
WHERE o.tenant_id = ?
ORDER BY o.created_at DESC, o.order_id DESC;
```

Không nên tải danh sách đơn rồi gọi thêm một query lấy customer cho từng đơn. JOIN cho phép engine thực hiện phép kết hợp theo query plan.

### 2.3. Tổng hợp và tính toán trên tập dữ liệu

Ví dụ báo cáo doanh thu theo trạng thái:

```sql
SELECT
    status,
    COUNT(*) AS order_count,
    SUM(total_amount) AS total_amount
FROM orders
WHERE tenant_id = ?
  AND created_at >= ?
  AND created_at < ?
GROUP BY status
ORDER BY status;
```

Database phù hợp với:

- COUNT, SUM, AVG, MIN, MAX.
- GROUP BY và HAVING.
- JOIN, subquery và CTE.
- Window functions.
- Lọc theo ngày, trạng thái và khóa.
- Sắp xếp, phân trang và top-N.
- Cập nhật hàng loạt theo điều kiện.

Nếu tải hàng trăm nghìn bản ghi về Java chỉ để cộng tiền, ứng dụng đang làm lại công việc mà database có thể thực hiện gần dữ liệu hơn.

### 2.4. Cập nhật nguyên tử

Ví dụ trừ tồn kho:

```sql
UPDATE inventory
SET available_qty = available_qty - ?
WHERE product_id = ?
  AND tenant_id = ?
  AND available_qty >= ?;
```

Ứng dụng bind số lượng, ID sản phẩm và tenant. Sau khi chạy, kiểm tra số hàng bị ảnh hưởng:

- 1 hàng: phép trừ thành công.
- 0 hàng: sản phẩm không tồn tại, không thuộc phạm vi hoặc không đủ tồn kho; phân biệt theo nghiệp vụ nếu cần.
- Nhiều hơn 1 hàng: điều kiện khóa/schema có thể không đúng như dự kiến.

Database đánh giá điều kiện và cập nhật trong một statement, giảm khoảng trống giữa “đã kiểm tra” và “đã thay đổi”.

### 2.5. Ràng buộc toàn vẹn

Những quy tắc phải đúng với **mọi writer** nên được bảo vệ trong schema:

```sql
CREATE TABLE order_items (
    order_id BIGINT NOT NULL,
    line_no INTEGER NOT NULL,
    product_id BIGINT NOT NULL,
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    unit_price NUMERIC(12,2) NOT NULL CHECK (unit_price >= 0),

    PRIMARY KEY (order_id, line_no),
    FOREIGN KEY (order_id) REFERENCES orders(order_id),
    FOREIGN KEY (product_id) REFERENCES products(product_id)
);
```

Constraint bảo vệ dữ liệu từ API web, mobile, batch import, job định kỳ, công cụ quản trị và script migration. Nếu chỉ validate ở Java, một đường ghi khác có thể bỏ qua.

## 3. Mã ứng dụng nên đảm nhận những công việc nào?

Ứng dụng hiểu **request, người dùng và hệ thống xung quanh**.

### 3.1. Tiếp nhận request và chuyển đổi dữ liệu

Ứng dụng thường chịu trách nhiệm:

- Parse HTTP, JSON, form và message.
- Kiểm tra kiểu, định dạng, độ dài và giới hạn request.
- Chuyển DTO thành command/domain input.
- Trả lỗi có cấu trúc cho client.
- Giữ tương thích API giữa các phiên bản.

Database không nên phải hiểu tên field của form, HTTP status code hay cách màn hình hiển thị lỗi.

### 3.2. Xác thực và điều phối authorization

Ứng dụng nhận identity đã xác thực từ session, token hoặc gateway rồi quyết định user có được phép thực hiện use case không.

```java
AuthenticatedUser user = authentication.currentUser();

long authorizedTenantId = user.tenantId();

orderService.cancelOrder(
    authorizedTenantId,
    user.userId(),
    request.orderId()
);
```

Không lấy tenant từ request rồi xem nó là bằng chứng quyền truy cập. Database có thể bổ sung RLS hoặc điều kiện tenant trong query, nhưng nguồn identity cần có hợp đồng đáng tin cậy.

### 3.3. Điều phối nhiều hệ thống

Một use case có thể gồm:

1. Tạo đơn.
2. Ghi nhận thanh toán.
3. Gửi message tới broker.
4. Gọi dịch vụ vận chuyển.
5. Gửi email.
6. Cập nhật trạng thái giao hàng.

Database có thể bảo đảm transaction cho các thay đổi **trong chính database đó**. Nó không thể tạo một transaction ACID thông thường bao trùm email, HTTP API và broker độc lập. Ứng dụng hoặc workflow engine nên điều phối các bước bên ngoài, retry, timeout, idempotency và compensation.

### 3.4. Trình bày và trải nghiệm

Định dạng tiền theo locale, dịch trạng thái thành nhãn UI, chọn ngôn ngữ, tạo response DTO, ẩn/hiện chức năng và ánh xạ lỗi DB sang thông báo người dùng thường thuộc application/presentation layer.

### 3.5. Logic cần thư viện hoặc môi trường bên ngoài

Ứng dụng phù hợp hơn để xử lý file, tạo PDF/ảnh, gửi thông báo, gọi API, mã hóa, thuật toán chuyên ngành, CAPTCHA, rate limit và workflow kéo dài.

Database vẫn giữ vai trò lưu trữ bền vững và thực hiện các phép biến đổi dữ liệu phù hợp.

## 4. Bảng quyết định: công việc đặt ở đâu?

| Loại công việc | Nơi thường phù hợp | Lý do |
|---|---|---|
| Lọc theo tenant/trạng thái | SQL | Giảm dữ liệu truyền, dùng index |
| JOIN customer/order | SQL | Dữ liệu quan hệ nằm trong DB |
| Tổng hợp doanh thu | SQL | Aggregate và window functions |
| PK, FK, UNIQUE, NOT NULL, CHECK | Database | Bảo vệ mọi đường ghi |
| Trừ tồn kho có điều kiện | SQL trong transaction | Atomic update và concurrency |
| Parse HTTP JSON | Ứng dụng | Thuộc giao thức/API |
| Validate định dạng request | Ứng dụng; DB bổ sung constraint | Trả lỗi sớm và giữ toàn vẹn |
| Xác thực user/token | Ứng dụng/identity provider | Có thông tin đăng nhập và session |
| Tenant row isolation | Ứng dụng + DB policy phù hợp | Cần authorization và bảo vệ dữ liệu |
| Gọi payment gateway | Ứng dụng | Tích hợp mạng và retry |
| Gửi email | Worker/ứng dụng | Không giữ transaction để gửi |
| Chuyển trạng thái | Domain/service + SQL | Use case và tính toàn vẹn phối hợp |
| Format ngày/tiền cho UI | Ứng dụng | Locale và presentation |
| Xử lý hàng triệu hàng theo tập | SQL/bulk API | Tránh vòng lặp nhiều round trip |
| Quy trình nhiều ngày | Workflow/application | Không giữ transaction DB lâu |

Bảng là điểm khởi đầu, không phải luật tuyệt đối. Một quy tắc có thể được kiểm tra ở ứng dụng để UX tốt và được bảo vệ ở database để mọi đường ghi tuân thủ.

## 5. Ba lớp kiểm tra: đầu vào, nghiệp vụ và database

```text
Request từ client
       |
       v
[1] Validation đầu vào
- kiểu dữ liệu
- định dạng
- kích thước
- field bắt buộc
       |
       v
[2] Authorization + nghiệp vụ
- user có quyền?
- tenant nào?
- trạng thái có cho phép?
- quy trình có hợp lệ?
       |
       v
[3] Database constraints + transaction
- FK / UNIQUE / CHECK
- atomic update
- locking / isolation
- ghi nhất quán
       |
       v
Kết quả được ánh xạ về API
```

### 5.1. Validation UX và constraint integrity khác nhau

Ví dụ quantity phải lớn hơn 0:

- API DTO kiểm tra sớm để trả lỗi dễ hiểu.
- Domain service kiểm tra số lượng theo chính sách sản phẩm.
- Database có CHECK để không đường ghi nào lưu số âm hoặc 0.

Đây không phải lặp vô nghĩa nếu mỗi lớp có mục tiêu rõ.

### 5.2. Unique constraint không thể thay bằng SELECT trước

Cách ngây thơ:

```java
if (!repository.existsByEmail(email)) {
    repository.save(user);
}
```

Hai request có thể cùng thấy email chưa tồn tại rồi cùng INSERT. Unique constraint/index ở database mới phân xử được tình huống đồng thời. Ứng dụng có thể kiểm tra trước để UX tốt hơn, nhưng vẫn phải xử lý unique violation sau khi ghi.

### 5.3. Không nhét mọi quy tắc vào CHECK

CHECK phù hợp với điều kiện cục bộ trên hàng:

```sql
CHECK (quantity > 0)
CHECK (total_amount >= 0)
CHECK (status IN ('DRAFT', 'PAID', 'CANCELLED'))
```

Quy tắc cần gọi dịch vụ ngoài, xem nhiều bảng hoặc điều phối workflow thường cần application service, transaction, FK/unique, trigger hoặc stored procedure tùy invariant. Không ép mọi domain rule vào CHECK thông thường.

## 6. Ví dụ end-to-end: đặt hàng

Use case: người dùng tạo đơn gồm nhiều sản phẩm.

### 6.1. Trách nhiệm của ứng dụng

1. Xác thực người dùng.
2. Lấy tenant từ security context.
3. Parse request, kiểm tra danh sách item không rỗng và số lượng dương.
4. Kiểm tra quyền mua và chính sách sản phẩm.
5. Lấy giá có thẩm quyền từ database hoặc pricing service.
6. Mở transaction.
7. Ghi đơn và dòng hàng, trừ tồn kho.
8. Ghi outbox event cùng transaction.
9. Commit.
10. Worker đọc outbox và gọi broker/payment/shipping.
11. Trả kết quả cho client.

### 6.2. Trách nhiệm của database

- Kiểm tra FK tới sản phẩm.
- Kiểm tra quantity dương và tiền không âm.
- Bảo đảm khóa đơn/dòng hàng duy nhất.
- Trừ tồn kho có điều kiện.
- Ghi order, order_items và outbox nguyên tử.
- Quản lý lock/MVCC theo transaction.
- Rollback toàn bộ thay đổi nếu một bước thất bại.

### 6.3. Sơ đồ

```text
HTTP POST /orders
      |
      v
Controller
  parse + validate request
      |
      v
Application service
  authenticate / authorize
  áp dụng domain policy
      |
      v
Transaction boundary
      |
      +--> INSERT orders
      |
      +--> UPDATE inventory
      |      WHERE available_qty >= quantity
      |
      +--> INSERT order_items
      |
      +--> INSERT outbox_events
      |
      v
COMMIT
      |
      v
Outbox worker
  publish event / call external service
      |
      v
Retry / update delivery state
```

### 6.4. Schema minh họa

```sql
CREATE TABLE products (
    product_id BIGINT PRIMARY KEY,
    tenant_id BIGINT NOT NULL,
    sku TEXT NOT NULL,
    unit_price NUMERIC(12,2) NOT NULL CHECK (unit_price >= 0),
    available_qty INTEGER NOT NULL CHECK (available_qty >= 0),
    UNIQUE (tenant_id, sku)
);

CREATE TABLE orders (
    order_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id BIGINT NOT NULL,
    customer_id BIGINT NOT NULL,
    status TEXT NOT NULL
        CHECK (status IN ('DRAFT', 'CONFIRMED', 'CANCELLED')),
    total_amount NUMERIC(14,2) NOT NULL CHECK (total_amount >= 0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE order_items (
    order_id BIGINT NOT NULL REFERENCES orders(order_id),
    line_no INTEGER NOT NULL,
    product_id BIGINT NOT NULL REFERENCES products(product_id),
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    unit_price NUMERIC(12,2) NOT NULL CHECK (unit_price >= 0),
    PRIMARY KEY (order_id, line_no)
);

CREATE TABLE outbox_events (
    event_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    aggregate_type TEXT NOT NULL,
    aggregate_id BIGINT NOT NULL,
    event_type TEXT NOT NULL,
    payload JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    published_at TIMESTAMPTZ
);
```

Đây là schema minh họa. Production cần ràng buộc tenant/customer phù hợp, index, quyền, retention và quy tắc snapshot giá.

### 6.5. Trừ tồn kho bằng statement có điều kiện

Không nên SELECT tồn kho ở Java rồi UPDATE riêng:

```java
int available = repository.findAvailable(productId);

if (available >= quantity) {
    repository.decrease(productId, quantity);
}
```

Một request khác có thể thay đổi tồn kho giữa hai bước. Hãy dùng:

```sql
UPDATE products
SET available_qty = available_qty - ?
WHERE product_id = ?
  AND tenant_id = ?
  AND available_qty >= ?;
```

JDBC:

```java
int changed;

try (PreparedStatement ps = connection.prepareStatement("""
        UPDATE products
        SET available_qty = available_qty - ?
        WHERE product_id = ?
          AND tenant_id = ?
          AND available_qty >= ?
        """)) {
    ps.setInt(1, quantity);
    ps.setLong(2, productId);
    ps.setLong(3, authorizedTenantId);
    ps.setInt(4, quantity);

    changed = ps.executeUpdate();
}

if (changed != 1) {
    throw new InsufficientInventoryException(productId);
}
```

Ứng dụng quyết định phản hồi khi không trừ được; database thực hiện phép trừ có điều kiện nguyên tử.

### 6.6. Ai quyết định giá đơn hàng?

Client nên gửi product ID và quantity, không được tự quyết định giá cuối cùng. Server lấy giá có thẩm quyền, áp dụng discount/tax theo domain policy và lưu **snapshot đơn giá** trong order_items. Nếu giá sản phẩm thay đổi ngày mai, đơn lịch sử vẫn giữ giá đã giao dịch.

Parameter binding chỉ bảo vệ cú pháp SQL; nó không chứng minh giá client gửi là đúng.

## 7. Transaction boundary nên đặt ở đâu?

Transaction thường được mở ở **application service/use case**, vì ứng dụng biết những thao tác DB nào phải cùng thành công.

```java
connection.setAutoCommit(false);

try {
    // INSERT order
    // UPDATE inventory
    // INSERT order_items
    // INSERT outbox_events

    connection.commit();
} catch (SQLException | RuntimeException ex) {
    connection.rollback();
    throw ex;
} finally {
    connection.setAutoCommit(true);
}
```

Đây là ví dụ rút gọn. Production nên dùng transaction manager/framework để quản lý connection, rollback, exception translation và trạng thái connection.

### 7.1. Nhóm các thay đổi phải cùng thành công

Ví dụ tạo order, order_items, trừ tồn kho và ghi outbox cần nằm trong cùng transaction nếu nghiệp vụ yêu cầu tất cả cùng thành công. Nếu một bước lỗi, rollback những thay đổi liên quan.

### 7.2. Không giữ transaction mở khi gọi HTTP

Một thiết kế dễ gây vấn đề:

```text
BEGIN;
INSERT order;
Gọi payment provider qua HTTP và chờ 20 giây;
INSERT payment result;
COMMIT;
```

Trong thời gian chờ, transaction có thể giữ lock và connection. Dịch vụ ngoài cũng có thể đã xử lý thanh toán nhưng response bị mất.

Một thiết kế thường dễ vận hành hơn:

1. Transaction A ghi order ở trạng thái pending và outbox command.
2. Commit.
3. Worker gọi payment provider với idempotency key.
4. Transaction B ghi kết quả thanh toán.
5. Retry hoặc compensation theo state machine khi cần.

### 7.3. Transaction DB không bao gồm email hay broker

Rollback database không thể thu hồi email đã gửi hoặc message đã publish. Transactional outbox ghi sự kiện cần phát trong cùng transaction dữ liệu; worker phát sau commit. Consumer cần idempotency/deduplication vì outbox thường bảo đảm giao ít nhất một lần, không tự biến thành exactly-once.

## 8. Tránh N+1 queries và overfetch

Giả sử cần hiển thị 100 đơn cùng tên khách hàng.

Không nên:

```java
List<Order> orders = orderRepository.findRecentOrders(tenantId);

for (Order order : orders) {
    Customer customer =
        customerRepository.findById(order.getCustomerId());
    render(order, customer);
}
```

Nếu mỗi lần tìm customer là một query, tổng có thể là 1 + N truy vấn.

Dùng JOIN/projection:

```sql
SELECT
    o.order_id,
    o.created_at,
    o.total_amount,
    c.customer_name
FROM orders AS o
JOIN customers AS c
  ON c.customer_id = o.customer_id
 AND c.tenant_id = o.tenant_id
WHERE o.tenant_id = ?
ORDER BY o.created_at DESC, o.order_id DESC
FETCH FIRST 100 ROWS ONLY;
```

Cú pháp FETCH FIRST có trên nhiều DBMS hiện đại; PostgreSQL/MySQL thường dùng LIMIT. Chọn theo dialect.

### 8.1. Không tải mọi cột nếu chỉ cần vài cột

Thay vì:

```sql
SELECT *
FROM customers
WHERE tenant_id = ?;
```

hãy chọn đúng dữ liệu:

```sql
SELECT customer_id, customer_name
FROM customers
WHERE tenant_id = ?
ORDER BY customer_name;
```

Lợi ích gồm giảm dữ liệu truyền, bộ nhớ, serialization và nguy cơ đọc nhầm cột nhạy cảm. DTO/projection thường phù hợp với màn hình hoặc báo cáo hơn entity graph đầy đủ.

### 8.2. ORM fetch strategy cần được đo

JOIN fetch có thể làm lặp hàng cha; eager-load mọi quan hệ có thể tạo overfetch. Chọn dựa trên số hàng, loại quan hệ, pagination, payload, query plan và số query thực tế. Không sửa N+1 bằng cách tải toàn bộ graph trong mọi trường hợp.

## 9. ORM và SQL thuần: chọn theo tác vụ

ORM là công cụ ánh xạ object và quan hệ, không phải lý do để tránh SQL.

| Tác vụ | Cách thường phù hợp |
|---|---|
| CRUD đơn giản trên entity | ORM/repository |
| Query nghiệp vụ vừa phải | ORM query, JPQL, Criteria |
| Báo cáo aggregate phức tạp | SQL projection/native query |
| Bulk update/delete | SQL bulk statement hoặc API ORM phù hợp |
| Query cần tối ưu theo plan cụ thể | SQL có EXPLAIN |
| Nhiều thao tác DB cần cùng thành công | Transaction service + SQL/ORM |
| Cần portability cơ bản | ORM và SQL chuẩn trong phạm vi phù hợp |
| Dùng tính năng riêng DBMS | Native SQL được cô lập theo repository/dialect |

### 9.1. ORM vẫn sinh SQL

Dù code gọi:

```java
repository.findByTenantIdAndStatus(tenantId, status);
```

ORM vẫn tạo SQL. Cần hiểu query thực tế, lazy/eager loading, transaction, locking/version, N+1 và index.

### 9.2. Bulk DML và persistence context

Một câu UPDATE trực tiếp có thể không đồng bộ ngay các entity đang nằm trong persistence context của JPA/Hibernate. Khi dùng bulk DML:

- Flush thay đổi cần thiết trước khi chạy.
- Cân nhắc clear/refresh sau đó.
- Kiểm tra cache cấp hai và optimistic version.
- Đảm bảo transaction.
- Không để entity trong memory phản ánh trạng thái cũ.

## 10. Validation và quy tắc nghiệp vụ

Một trường quantity có thể được kiểm tra ở nhiều lớp nhưng mỗi lớp có mục tiêu khác nhau.

| Kiểm tra | Ứng dụng | Database |
|---|---|---|
| Request bắt buộc | Có, trả lỗi dễ hiểu | NOT NULL cho dữ liệu bắt buộc |
| Email đúng định dạng | Có | Có thể thêm constraint phù hợp |
| Số lượng dương | Có | CHECK |
| Email duy nhất | Có thể kiểm tra trước | UNIQUE là bảo đảm quyết định |
| Product tồn tại | Có thể kiểm tra để UX | FK |
| Product thuộc tenant | Authorization/domain | FK ghép, RLS hoặc điều kiện phù hợp |
| Chuyển trạng thái hợp lệ | Domain service | UPDATE có điều kiện/constraint phù hợp |
| Tổng tiền theo giá chính thức | Domain/service | Lưu snapshot và ràng buộc phù hợp |

### 10.1. Quy tắc cần đúng với mọi writer

Nếu một bất biến dữ liệu phải đúng dù ghi từ API, job hay công cụ quản trị, hãy bảo vệ tại database bằng constraint hoặc transaction phù hợp. Application vẫn kiểm tra trước để UX tốt.

### 10.2. Quy tắc phụ thuộc use case

Một quy tắc như “chỉ người quản lý được hủy đơn sau khi xác nhận” phụ thuộc identity, role, trạng thái và quy trình sản phẩm. Application service thường điều phối; SQL cập nhật có điều kiện để chống race; database có thể bổ sung policy hoặc trigger khi cần bảo vệ mọi đường ghi.

Không nên sao chép quy tắc theo cách mỗi service tự diễn giải khác nhau. Hãy có một định nghĩa domain rõ ràng và contract giữa các lớp.

## 11. Authorization: ứng dụng và database phối hợp

Ứng dụng biết user, role và use case. Database có thể bổ sung chính sách gần dữ liệu.

### 11.1. Tenant predicate trong SQL

```sql
SELECT order_id, status, total_amount
FROM orders
WHERE tenant_id = ?
  AND order_id = ?;
```

Tenant ID phải đến từ context đã xác thực. Nếu lấy từ request mà không kiểm tra, query vẫn có thể đọc tenant khác dù đã parameterize hoàn toàn.

### 11.2. Row-Level Security

PostgreSQL và một số DBMS có RLS/policy để giới hạn hàng theo role/context. Khi dùng cần xác định:

- Context tenant được thiết lập từ nguồn tin cậy.
- Connection pool reset context giữa requests.
- Owner/BYPASSRLS/security definer behavior được hiểu rõ.
- Policy áp đúng SELECT/INSERT/UPDATE/DELETE.
- Test bằng role thực tế, không dùng superuser.

RLS bổ sung lớp bảo vệ dữ liệu; nó không thay authentication và không sửa SQL injection.

### 11.3. Least privilege

Tách role theo mục tiêu:

- Read-only/report role.
- Application write role.
- Migration role.
- Routine owner role.
- Monitoring role.

Không dùng superuser hoặc DBA account cho request thông thường. Cấp đúng quyền schema/table/column/routine cần thiết để giảm phạm vi tác động khi ứng dụng có lỗi.

## 12. Stored procedure/function: khi nào phù hợp?

Stored routine có thể phù hợp khi:

- Nhiều ứng dụng dùng chung một thao tác dữ liệu phức tạp.
- Cần cập nhật nhiều hàng nguyên tử gần dữ liệu.
- Muốn một API database có quyền hạn rõ.
- Có phép xử lý set-based tránh nhiều round trip.
- Routine là contract ổn định trong hệ thống legacy.
- Cần đóng gói logic truy cập dữ liệu cho nhiều client.

Ví dụ thao tác chuyển trạng thái có điều kiện:

```sql
UPDATE orders
SET status = 'CANCELLED'
WHERE order_id = p_order_id
  AND tenant_id = p_authorized_tenant
  AND status = 'DRAFT';
```

Ứng dụng gọi routine, kiểm tra kết quả và điều phối thông báo.

### 12.1. Khi không nên đưa toàn bộ workflow vào procedure?

Không phù hợp nếu routine phải gọi nhiều HTTP API, gửi email, tạo file, chờ người dùng, điều phối workflow dài hoặc dùng thư viện chuyên ngành không có trong DB.

### 12.2. Stored procedure không tự động an toàn

Routine vẫn cần parameterization cho dynamic values, allowlist identifier, least privilege, validation, authorization, transaction và test. Đưa SQL vào procedure không tự ngăn injection nếu bên trong vẫn nối input vào dynamic SQL.

## 13. SQL injection là lỗi ở ranh giới ứng dụng/database

Sai:

```java
String sql =
    "SELECT * FROM users WHERE email = '" + email + "'";
```

Đầu vào không tin cậy bị ghép vào SQL text. Sửa:

```java
String sql = "SELECT user_id FROM users WHERE email = ?";

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setString(1, email);
}
```

Ứng dụng giữ cấu trúc query và bind value; database parse/execute theo cú pháp cố định.

### 13.1. Identifier không thể bind như value

Không dùng:

```sql
SELECT * FROM orders ORDER BY ?;
```

để mong tham số trở thành tên cột. Dùng allowlist:

```java
String sortColumn = switch (request.sort()) {
    case "created" -> "created_at";
    case "amount" -> "total_amount";
    case "id" -> "order_id";
    default -> throw new IllegalArgumentException("Unsupported sort");
};
```

Chỉ nối fragment cố định do code chọn; tenant, status, limit và giá trị khác vẫn bind.

### 13.2. Parameterization không phải authorization

Query có bind hoàn toàn vẫn có thể đọc nhầm tenant nếu điều kiện quyền sai. Chống injection và kiểm soát quyền là hai nhiệm vụ riêng.

## 14. Error handling: ánh xạ lỗi DB thành kết quả nghiệp vụ

| Lỗi DB | Cách xử lý ứng dụng thường gặp |
|---|---|
| Unique violation | Conflict “mã đã tồn tại” |
| FK violation | Quan hệ không tồn tại hoặc đối tượng đã bị xóa |
| CHECK violation | Validation hoặc bug ở đường ghi |
| Deadlock | Rollback, retry có giới hạn nếu idempotent |
| Serialization failure | Retry transaction theo policy |
| Timeout | Lỗi tạm thời, theo dõi query/lock |
| Connection failure | Retry/circuit breaker có giới hạn |
| Syntax error | Thường là bug query/migration |

Không trả raw SQL, schema, password hoặc connection details cho client. Ghi log correlation ID và mã lỗi, đồng thời redaction dữ liệu nhạy cảm.

### 14.1. Affected rows có ý nghĩa

Một UPDATE không có exception vẫn có thể tác động 0 hàng. Ứng dụng cần phân biệt không tồn tại, không có quyền, trạng thái đã đổi hoặc request cạnh tranh. Không suy “không lỗi SQL = use case thành công”.

## 15. Hiệu năng: đo trước khi chuyển logic giữa hai lớp

### 15.1. Round trip có thể đắt hơn phép tính nhỏ

500 query riêng có thể tốn nhiều thời gian mạng/driver/lock hơn một query set-based. Gộp truy vấn hoặc batch có thể giảm overhead.

### 15.2. CPU nặng có thể phù hợp ở ứng dụng

Xử lý ảnh, mã hóa, ML hoặc thuật toán cần thư viện chuyên dụng thường phù hợp với service/worker. Chỉ lấy dữ liệu cần và ghi kết quả theo transaction phù hợp.

### 15.3. SQL phù hợp với bulk update

```sql
UPDATE invoices
SET overdue = TRUE
WHERE due_at < CURRENT_TIMESTAMP
  AND paid_at IS NULL
  AND overdue = FALSE;
```

Một UPDATE set-based thường hợp lý hơn tải từng invoice về Java rồi update riêng. Với bảng rất lớn, cần xem index, batch, partition, lock duration và log.

### 15.4. Xem execution plan

- PostgreSQL: EXPLAIN và EXPLAIN ANALYZE.
- MySQL: EXPLAIN/EXPLAIN ANALYZE theo phiên bản.
- SQL Server: actual execution plan và STATISTICS IO/TIME.
- Oracle: execution plan và runtime statistics.
- SQLite: EXPLAIN QUERY PLAN.

Đánh giá query plan, số hàng, IO, lock wait, dữ liệu truyền và latency. Không tối ưu chỉ bằng cách đếm dòng Java hoặc số câu SQL.

## 16. Batch processing: set-based SQL hay vòng lặp ứng dụng?

Nếu cần đánh dấu hàng loạt khách hàng đủ điều kiện:

```sql
UPDATE customers
SET segment = 'LOYAL'
WHERE tenant_id = ?
  AND lifetime_value >= ?;
```

thường tốt hơn gọi UPDATE riêng cho từng ID nếu quy tắc có thể biểu diễn thành một tập.

Batch ở ứng dụng vẫn phù hợp khi mỗi hàng cần gọi API ngoài, có workflow khác nhau, cần xử lý theo chunk hoặc thuật toán không phù hợp SQL. Có thể dùng JDBC batch, bulk load hoặc staging table rồi dùng set-based SQL cho phần xử lý dữ liệu.

## 17. Schema migration và source of truth

Database schema là hợp đồng giữa các phiên bản ứng dụng. Migration cần được quản lý như code:

- Tạo/đổi bảng, cột, index và constraint.
- Backfill dữ liệu.
- Tương thích app cũ/mới trong giai đoạn deploy.
- Rollback/forward strategy.
- Kiểm tra lock và thời gian build index.
- Quyền migration tách khỏi request role.

Không chạy ALTER TABLE tùy tiện trong mỗi request.

### 17.1. Expand-and-contract

1. Expand: thêm cột/đối tượng mới tương thích app cũ.
2. Deploy app mới có thể đọc/ghi cấu trúc mới.
3. Backfill theo lô.
4. Chuyển đọc sang cột mới.
5. Contract: chỉ bỏ cột cũ khi app cũ không còn dùng.

### 17.2. Default phải có nguồn sự thật

Nếu DB default tạo giá trị, ứng dụng nên hiểu hành vi đó. Nếu Java, ORM annotation, DB default và batch script định nghĩa khác nhau, dữ liệu có thể không nhất quán. Hãy quy định rõ nguồn authoritative và test cả các đường ghi.

## 18. Cấu trúc lớp ứng dụng

Một cấu trúc thường gặp:

```text
Controller / API adapter
        |
        v
Application service / use case
        |
        +--> Domain model / policy
        |
        +--> Repository / DAO
                  |
                  v
             JDBC / ORM
                  |
                  v
               Database
```

### 18.1. Controller

Controller parse request, xác thực đầu vào cơ bản và gọi use case. Không nên chứa SQL dài, transaction, retry, mapping DB error và tích hợp API ngoài cùng lúc.

### 18.2. Repository/DAO

Repository giữ chi tiết truy cập dữ liệu và cung cấp API theo domain:

```java
Optional<OrderSummary> findSummary(
    long authorizedTenantId,
    long orderId
);

int markAsPaid(
    long authorizedTenantId,
    long orderId,
    Instant paidAt
);
```

Bên trong có thể dùng ORM hoặc SQL thuần. Controller không cần biết tên bảng hay dialect.

### 18.3. Application service

```java
@Transactional
public OrderResult confirmOrder(
        AuthenticatedUser user,
        ConfirmOrderCommand command) {

    Order order = orderRepository
        .findForUpdate(user.tenantId(), command.orderId())
        .orElseThrow(OrderNotFoundException::new);

    orderPolicy.assertCanConfirm(user, order);

    inventoryRepository.reserve(
        user.tenantId(),
        order.items()
    );

    order.confirm(clock.instant());

    outboxRepository.add(
        OrderConfirmedEvent.from(order)
    );

    return OrderResult.from(order);
}
```

Đây là pseudocode. Các repository cần dùng cùng transaction context; việc gọi dịch vụ ngoài nên được xử lý sau commit qua outbox/worker.

## 19. Portability giữa các DBMS

SQL chuẩn giúp giảm khác biệt, nhưng mỗi DBMS có dialect, type, transaction và tính năng riêng.

| Khác biệt | Ví dụ |
|---|---|
| Phân trang | LIMIT/OFFSET, OFFSET/FETCH, TOP |
| Tự sinh ID | IDENTITY, SERIAL, sequence |
| JSON | jsonb, native JSON, NVARCHAR + ISJSON, CLOB + IS JSON |
| Upsert | ON CONFLICT, ON DUPLICATE KEY, MERGE |
| Returning | RETURNING, OUTPUT, generated keys |
| Locking | FOR UPDATE và biến thể |
| Boolean | BOOLEAN hoặc quy ước số/bit |
| DDL transaction | Khả năng rollback DDL khác nhau |

Có thể dùng ORM cho CRUD cơ bản; native SQL cần được cô lập trong repository/dialect adapter và test trên DBMS thật dùng production. Không chỉ test bằng H2 nếu production chạy PostgreSQL/MySQL.

Portability không yêu cầu tránh mọi SQL riêng của DBMS. Cần biết chỗ nào phụ thuộc dialect và kiểm thử nó.

## 20. Khi nào đặt logic trong database nhiều hơn?

Database là nơi tự nhiên khi:

- Nhiều ứng dụng ghi cùng schema.
- Invariant phải đúng với mọi writer.
- Một thao tác set-based lớn.
- Cần cập nhật nhiều hàng nguyên tử.
- Stored procedure là contract ổn định giữa nhiều client.
- Cần giới hạn quyền bằng routine/view/RLS.
- Dữ liệu không nên rời DB vì chính sách hoặc kích thước.

Ví dụ ngân hàng có thể dùng stored procedure để chuyển khoản giữa hai tài khoản trong một transaction, kiểm tra số dư và ghi ledger. Application vẫn xác thực người dùng, MFA, hạn mức sản phẩm, thông báo và workflow.

## 21. Khi nào đặt logic trong ứng dụng nhiều hơn?

Ứng dụng phù hợp khi:

- Quy tắc phụ thuộc request, identity hoặc UX.
- Cần phối hợp nhiều dịch vụ.
- Workflow kéo dài và có retry/compensation.
- Cần thư viện ngôn ngữ chuyên dụng.
- Logic thay đổi theo product và cần deploy độc lập.
- Cần unit test domain logic mà không khởi động DB.

Nhưng application vẫn nên dùng SQL để thao tác dữ liệu theo tập, và database vẫn cần constraint để bảo vệ dữ liệu.

## 22. Không biến database thành service bus

Tránh thiết kế trigger/procedure trực tiếp gửi HTTP, email hoặc chờ workflow nhiều giờ. Side effect ngoài DB khó rollback cùng transaction. Với thông báo và broker, outbox + worker thường dễ vận hành hơn.

Ngược lại, cũng không biến application thành client gửi từng SELECT nhỏ. SQL nên đảm nhận truy vấn và thao tác tập dữ liệu.

## 23. Kiểm thử theo lớp

### 23.1. Unit test

Kiểm tra domain/application logic mà không cần DB:

- Quy tắc chuyển trạng thái.
- Discount/tax policy.
- Validation.
- Authorization policy.
- Retry/idempotency decision.
- Mapping lỗi sang API response.

Mock repository không chứng minh SQL thật đúng.

### 23.2. Integration test

Dùng DBMS tương thích production để kiểm tra:

- SQL syntax và mapping kiểu.
- Constraint.
- Transaction rollback.
- Locking/concurrency.
- RLS/permissions.
- Stored procedure/trigger.
- Query count và N+1.

### 23.3. Concurrency test

Các tình huống cần thử:

- Hai request cùng mua đơn vị tồn kho cuối.
- Hai request tạo cùng email.
- Hai request cùng chuyển trạng thái.
- Hai request cập nhật document cùng version.
- Retry sau timeout khi không biết request trước đã commit chưa.

Mock repository khó mô phỏng đầy đủ locking và isolation; cần DB thật và transaction đồng thời.

## 24. Ví dụ báo cáo doanh thu

Yêu cầu: doanh thu theo ngày trong một tháng.

Không nên tải từng hóa đơn về Java rồi cộng nếu dữ liệu lớn:

```java
List<Invoice> invoices =
    invoiceRepository.findByTenantAndMonth(tenantId, month);

Map<LocalDate, BigDecimal> totals = new HashMap<>();

for (Invoice invoice : invoices) {
    totals.merge(
        invoice.getIssuedAt().toLocalDate(),
        invoice.getTotalAmount(),
        BigDecimal::add
    );
}
```

SQL có thể tổng hợp:

```sql
SELECT
    CAST(issued_at AS DATE) AS invoice_day,
    SUM(total_amount) AS revenue
FROM invoices
WHERE tenant_id = ?
  AND issued_at >= ?
  AND issued_at < ?
  AND status = 'ISSUED'
GROUP BY CAST(issued_at AS DATE)
ORDER BY invoice_day;
```

Ứng dụng bind tenant/date và định dạng kết quả. Nếu doanh thu phụ thuộc thuế, tỷ giá hoặc phí theo thời điểm, cần domain rule có version và lưu snapshot các thành phần lịch sử.

## 25. Logging và observability

Ứng dụng thường biết request ID, user/tenant đã xác thực, use case và kết quả nghiệp vụ. Database/driver biết statement, duration, rows affected, lock wait, plan và SQLSTATE. Có thể kết hợp bằng trace/correlation ID.

Không log bind values không giới hạn: chúng có thể chứa PII, token hoặc dữ liệu thanh toán. Cấu hình redaction, phân quyền log, retention và không ghi password/access token.

Query log không nhất thiết biết “ai phê duyệt hoàn tiền và lý do gì”. Application cần audit event có actor, reason và request ID; database có thể lưu audit cùng transaction khi cần tính nhất quán.

## 26. Sai lầm thường gặp

| Sai lầm | Hậu quả | Hướng đúng |
|---|---|---|
| Tải toàn bảng về app để lọc | Overfetch, tốn memory/network | Lọc tại SQL |
| Lặp từng hàng và gọi query | N+1 | JOIN, batch hoặc set-based SQL |
| Chỉ validate ở UI | API/job khác ghi sai | Validate ở server và constraint DB |
| Chỉ SELECT trước khi INSERT | Race condition | UNIQUE constraint/index |
| Tính một quy tắc ở nhiều nơi | Không nhất quán | Source of truth và contract |
| Đưa mọi workflow vào procedure | Khó tích hợp và vận hành | DB xử lý dữ liệu; app điều phối |
| Đưa mọi aggregate về Java | Tốn round trip | SQL aggregate |
| Dùng ORM mà không xem SQL | N+1, query kém | Log/EXPLAIN và integration test |
| Native SQL khắp nơi | Khó đổi dialect | Repository/dialect adapter |
| Giữ transaction khi gọi HTTP | Lock và connection lâu | Outbox/worker |
| Tin giá/tenant từ client | Sai nghiệp vụ, lộ dữ liệu | Lấy từ nguồn có thẩm quyền |
| App account quá quyền | Blast radius lớn | Least privilege |
| Không kiểm tra affected rows | Coi 0 hàng là thành công | Xử lý kết quả DML |
| Nuốt constraint violation | API và dữ liệu lệch | Rollback và map lỗi |
| Coi PreparedStatement là authorization | Vẫn đọc hàng trái quyền | Tenant/ownership checks |
| Trigger gọi dịch vụ ngoài | Side effect khó rollback | Outbox + worker |
| Không test concurrency | Race condition ở production | Integration test đồng thời |
| Chỉ test H2 | Khác dialect/transaction | Test DBMS thật |
| Sửa schema trong request | Migration không kiểm soát | Pipeline migration |

## 27. Quy trình quyết định đặt logic ở đâu

Khi có một đoạn logic mới, hãy đi qua các câu hỏi:

1. **Có xử lý tập dữ liệu quan hệ không?** Nếu là lọc, JOIN, aggregate, bulk DML, sort hoặc pagination, bắt đầu từ SQL.
2. **Có phải invariant dữ liệu cho mọi writer không?** Nếu có, tìm constraint/index/FK/transaction hoặc policy DB phù hợp.
3. **Có phụ thuộc identity, request hoặc dịch vụ ngoài không?** Nếu có, đặt orchestration/authorization ở application service.
4. **Nhiều thao tác DB phải cùng thành công không?** Đặt transaction boundary ở use case và nhóm chúng trong cùng transaction.
5. **Có gọi dịch vụ ngoài hoặc chờ lâu không?** Không giữ transaction DB mở; dùng outbox, queue, workflow và idempotency khi phù hợp.
6. **Có SQL structure động không?** Bind giá trị, allowlist identifier/keyword; không nhận raw SQL từ client.
7. **Có bằng chứng hiệu năng không?** Xem plan, query count, rows transferred, lock wait và latency.
8. **Có thể kiểm thử và triển khai độc lập không?** Tách domain unit test, SQL integration test và schema migration.

## 28. Bài tập thực hành có đáp án

### Bài 1. Lọc dữ liệu ở đâu?

**Tình huống:** bảng orders có 5 triệu hàng; màn hình chỉ cần 20 đơn DRAFT của tenant hiện tại.

**Đáp án:** lọc và phân trang ở SQL với WHERE tenant/status, ORDER BY và LIMIT/FETCH. Bind tham số; ứng dụng chỉ nhận 20 hàng.

### Bài 2. Validation quantity

**Yêu cầu:** số lượng không được bằng 0 hoặc âm.

**Đáp án:** ứng dụng validate để trả lỗi dễ hiểu; database đặt CHECK(quantity > 0) để mọi đường ghi tuân thủ.

### Bài 3. Chống email trùng đồng thời

**Tình huống:** hai request cùng gọi existsByEmail rồi INSERT.

**Đáp án:** UNIQUE constraint/index. Ứng dụng vẫn có thể kiểm tra trước nhưng phải xử lý unique violation sau khi ghi.

### Bài 4. Tính tổng doanh thu

**Tình huống:** cần tổng theo tenant và tháng từ hàng triệu hóa đơn.

**Đáp án:** SQL dùng SUM, GROUP BY và khoảng ngày; ứng dụng bind tenant/date và định dạng kết quả.

### Bài 5. Gửi email xác nhận

**Hỏi:** có nên giữ transaction DB mở trong lúc gửi email?

**Đáp án:** thường không. Ghi đơn và outbox event trong transaction, commit rồi worker gửi email với retry/idempotency.

### Bài 6. Trừ tồn kho

**Hỏi:** SELECT tồn kho ở Java rồi UPDATE riêng hay UPDATE có điều kiện?

**Đáp án:** UPDATE nguyên tử với WHERE available_qty >= quantity; kiểm tra affected rows trong transaction.

### Bài 7. N+1 query

**Tình huống:** 100 đơn, mỗi đơn gọi một query lấy khách hàng.

**Đáp án:** JOIN/projection hoặc batch fetch phù hợp; kiểm tra query count, không eager-load mọi quan hệ.

### Bài 8. Quy tắc hủy đơn

**Hỏi:** chỉ đơn DRAFT mới được hủy, đặt ở đâu?

**Đáp án:** domain/service xác định use case; SQL UPDATE có predicate status để chống race; constraint/trigger nếu cần bảo vệ mọi đường ghi.

### Bài 9. Tenant ID từ request

**Tình huống:** SQL bind tenant ID nhưng lấy từ JSON client.

**Đáp án:** chưa đủ. Lấy tenant từ context đã xác thực phía server và áp authorization/RLS phù hợp.

### Bài 10. ORM query chậm

**Hỏi:** có nên bỏ ORM ngay?

**Đáp án:** xem SQL sinh ra, N+1, fetch strategy, index và plan trước. Có thể dùng projection/native SQL cho query cụ thể.

### Bài 11. Stored procedure gọi API thanh toán

**Hỏi:** có nên để procedure gọi HTTP payment provider?

**Đáp án:** thường không. Application/worker điều phối external API; DB routine có thể thực hiện thao tác dữ liệu nguyên tử.

### Bài 12. Constraint bị vi phạm

**Tình huống:** DB trả lỗi FK nhưng API vẫn trả thành công.

**Đáp án:** rollback transaction và ánh xạ lỗi phù hợp. Không nuốt exception rồi coi như ghi thành công.

### Bài 13. ORDER BY động

**Tình huống:** client gửi tên cột sort.

**Đáp án:** bind không thay identifier. Dùng allowlist mapping sang tên cột cố định; bind các giá trị còn lại.

### Bài 14. Báo cáo nhiều tenant

**Tình huống:** query GROUP BY tenant trả số liệu mọi tenant cho một tenant xem.

**Đáp án:** giới hạn tenant theo authorization hoặc chỉ cho role báo cáo đặc quyền. SQL hợp lệ không tự có quyền đúng.

### Bài 15. Bulk update với ORM

**Tình huống:** JPQL bulk UPDATE nhưng entity vẫn nằm trong persistence context.

**Đáp án:** bulk DML có thể không đồng bộ entity trong memory. Flush trước nếu cần, clear/refresh sau và kiểm tra version/cache.

### Bài 16. Đổi schema khi deploy

**Tình huống:** app mới yêu cầu cột mới nhưng app cũ vẫn đang chạy.

**Đáp án:** expand-and-contract: thêm cấu trúc tương thích, deploy, backfill, chuyển đọc/ghi, rồi mới bỏ cấu trúc cũ.

### Bài 17. Tính phí vận chuyển

**Tình huống:** phí phụ thuộc địa chỉ, vùng giao và API đối tác.

**Đáp án:** application service điều phối chính sách/API; SQL lưu snapshot phí và dữ liệu cần audit.

### Bài 18. Đánh dấu hàng triệu bản ghi hết hạn

**Hỏi:** tải về Java rồi update từng hàng hay UPDATE set-based?

**Đáp án:** thường dùng SQL UPDATE theo predicate; chia batch/partition nếu cần kiểm soát lock/log.

### Bài 19. Kiểm tra quyền user

**Tình huống:** controller kiểm tra role operator nhưng repository chỉ tìm order_id.

**Đáp án:** role cấp chức năng chưa chứng minh user sở hữu order. Cần object-level authorization và tenant/owner predicate.

### Bài 20. Test chỉ dùng mock

**Hỏi:** mock repository có chứng minh FK/locking/SQL đúng không?

**Đáp án:** không. Cần integration test với DBMS tương thích production.

### Bài 21. Khi nào dùng stored procedure?

**Tình huống:** nhiều ứng dụng cần thao tác chuyển tiền hai tài khoản cùng transaction.

**Đáp án:** procedure có thể là API dữ liệu phù hợp nếu quyền, input, transaction và audit rõ. Ứng dụng vẫn xác thực và điều phối workflow.

### Bài 22. OFFSET sâu

**Tình huống:** trang 100.000 chậm.

**Đáp án:** kiểm tra plan/index và cân nhắc keyset pagination với khóa sắp xếp ổn định. Không cần chuyển toàn bộ phân trang sang Java.

### Bài 23. Giá sản phẩm do client gửi

**Tình huống:** client gửi product_id, quantity và unit_price; SQL bind cả ba.

**Đáp án:** bind ngăn injection nhưng không xác nhận giá đúng. Server lấy giá có thẩm quyền và lưu snapshot.

### Bài 24. Ghi audit cùng trạng thái

**Tình huống:** audit phải tồn tại cùng thay đổi trạng thái đơn.

**Đáp án:** ghi audit row trong cùng transaction với UPDATE; application cung cấp actor/reason đã xác thực.

### Bài 25. Tác vụ nhiều giờ

**Tình huống:** import 10 triệu dòng, mỗi dòng cần kiểm tra API ngoài.

**Đáp án:** worker điều phối chunk, retry và trạng thái; staging/bulk SQL xử lý phần load/validate phù hợp. Không giữ một transaction mở nhiều giờ nếu có thể checkpoint.

### Bài 26. Tổng giỏ hàng

**Hỏi:** nên tính ở Java hay SQL?

**Đáp án:** SQL phù hợp aggregate trên các dòng lưu trong DB; domain service phù hợp pricing/discount phức tạp. Xác định source of truth, snapshot và transaction.

## 29. Tài liệu chính thức để tra cứu

Cú pháp và hành vi transaction khác theo DBMS/phiên bản. Các tài liệu sau là điểm bắt đầu:

- **Java JDBC — Prepared Statements:** https://docs.oracle.com/javase/tutorial/jdbc/basics/prepared.html
- **Java JDBC — Transactions:** https://docs.oracle.com/javase/tutorial/jdbc/basics/transactions.html
- **Spring — Declarative Transaction Management:** https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative.html
- **Spring JDBC — JdbcTemplate:** https://docs.spring.io/spring-framework/reference/data-access/jdbc/core.html
- **PostgreSQL — Transactions:** https://www.postgresql.org/docs/current/tutorial-transactions.html
- **PostgreSQL — Constraints:** https://www.postgresql.org/docs/current/ddl-constraints.html
- **PostgreSQL — EXPLAIN:** https://www.postgresql.org/docs/current/sql-explain.html
- **MySQL — InnoDB Transaction Model:** https://dev.mysql.com/doc/refman/8.4/en/innodb-transaction-model.html
- **SQL Server — Transactions:** https://learn.microsoft.com/en-us/sql/t-sql/language-elements/transactions-transact-sql
- **Oracle — Managing Transactions:** https://docs.oracle.com/en/database/oracle/oracle-database/19/lnpls/transaction-processing-and-control.html
- **SQLite — Transactions:** https://www.sqlite.org/lang_transaction.html
- **OWASP — SQL Injection Prevention:** https://cheatsheetseries.owasp.org/cheatsheets/SQL_Injection_Prevention_Cheat_Sheet.html

## Kết luận

**SQL và mã ứng dụng nên phối hợp theo thế mạnh và ranh giới nhất quán.**

- Đặt lọc, JOIN, aggregate, bulk DML, constraint và cập nhật nguyên tử ở database khi dữ liệu quan hệ và tính toàn vẹn cần được bảo vệ tại đó.
- Đặt xác thực, authorization theo use case, điều phối workflow, giao tiếp bên ngoài, xử lý request và trình bày ở ứng dụng.
- Dùng transaction ở application service để nhóm những thay đổi DB phải cùng thành công; database thực thi atomicity, khóa và constraint.
- Dùng parameterized SQL, allowlist cho cấu trúc động và least privilege; ORM/stored procedure không tự bảo đảm an toàn.
- Đo query plan, số round trip, dữ liệu truyền, lock và latency trước khi chuyển logic giữa hai lớp.

Nguyên tắc thực tế: **ứng dụng quyết định người dùng muốn thực hiện use case nào và điều phối toàn bộ quy trình; database bảo đảm dữ liệu được đọc, kết hợp và thay đổi đúng theo các quy tắc toàn vẹn trong transaction.** Khi mỗi lớp có trách nhiệm rõ, hệ thống dễ kiểm thử, dễ vận hành và ít gặp lỗi dữ liệu hơn.

