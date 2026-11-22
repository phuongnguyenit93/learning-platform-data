# Ánh xạ kết quả join hoặc tổng hợp vào mô hình đọc riêng

Một truy vấn nghiệp vụ thường cần dữ liệu từ nhiều bảng hoặc cần các giá trị đã được tổng hợp. Ví dụ, màn hình danh sách đơn hàng có thể hiển thị tên khách hàng, số dòng hàng và tổng tiền; báo cáo khách hàng có thể hiển thị số đơn đã mua và tổng doanh thu. Những kết quả này không nhất thiết tương ứng với một entity duy nhất trong mô hình ghi.

Trong Spring Data R2DBC, có thể dùng `DatabaseClient` để thực hiện SQL join hoặc aggregate, sau đó ánh xạ từng hàng kết quả thành DTO/projection dành riêng cho việc đọc. Mô hình đọc này giúp API nhận đúng dữ liệu cần dùng mà không phải tạo một object graph entity lớn hoặc gọi nhiều repository liên tiếp.

Điểm cần chú ý là SQL join có thể trả nhiều hàng cho cùng một bản ghi cha, aggregate làm thay đổi hình dạng dữ liệu, và `LEFT JOIN` có thể tạo các cột null. Thiết kế DTO và mapping phải phản ánh đúng cardinality, alias cột, kiểu dữ liệu và ý nghĩa của từng giá trị.

## 1. Vì sao cần mô hình đọc riêng?

Entity thường phản ánh dữ liệu và quy tắc cập nhật của một aggregate. Trong khi đó, màn hình hoặc báo cáo thường cần một hình dạng dữ liệu khác:

- Danh sách đơn hàng cần mã đơn, tên khách hàng, trạng thái và tổng tiền.
- Trang chi tiết đơn hàng cần thông tin đơn cùng danh sách dòng hàng.
- Dashboard cần số đơn, doanh thu và giá trị trung bình theo ngày.
- Màn hình quản trị cần kết hợp dữ liệu từ nhiều aggregate nhưng chỉ đọc.

Nếu cố dùng entity cho tất cả các trường hợp, ứng dụng có thể phải tải nhiều thuộc tính không cần thiết, truy vấn lặp lại hoặc làm ranh giới aggregate trở nên mơ hồ. Một DTO đọc riêng cho phép định nghĩa rõ dữ liệu của từng use case.

Ví dụ:

```java
public record OrderSummary(
    Long orderId,
    String orderNo,
    String status,
    String customerName,
    BigDecimal totalAmount,
    Long lineCount
) {}
```

`OrderSummary` là mô hình đọc, không phải entity cần lưu vào một bảng. Nó kết hợp các trường từ `purchase_order`, `customer` và `order_line` để phục vụ màn hình danh sách.

## 2. Phân biệt entity, projection và read model

| Khái niệm | Mục đích | Ví dụ |
|---|---|---|
| Entity | Biểu diễn dữ liệu được ánh xạ tới bảng và tham gia thao tác ghi | `PurchaseOrder`, `Customer` |
| Projection | Chọn một tập trường từ kết quả truy vấn | `OrderSummary` chỉ có ID, trạng thái và tổng tiền |
| Read model | Hình dạng dữ liệu hoàn chỉnh cho một use case đọc | Đơn hàng kèm khách hàng, số dòng hàng và thống kê |

Projection thường là một DTO nhỏ; read model có thể chứa nhiều projection lồng nhau hoặc dữ liệu tổng hợp. Cả hai đều có thể được tạo trực tiếp từ SQL mà không cần được quản lý như entity.

Spring Data R2DBC không phải ORM có persistence context như JPA/Hibernate. Khi truy vấn join, không nên kỳ vọng framework tự động tải và ghép toàn bộ quan hệ entity theo object graph hoặc lazy loading. Hãy thể hiện rõ SQL và cách ánh xạ kết quả cần có.

## 3. Thiết kế DTO trước khi viết câu join

Trước hết xác định use case cần trả về những trường nào, mỗi trường đến từ bảng nào và có thể null hay không.

Giả sử có các bảng:

```sql
CREATE TABLE customer (
    id BIGINT PRIMARY KEY,
    display_name VARCHAR(200) NOT NULL
);

CREATE TABLE purchase_order (
    id BIGINT PRIMARY KEY,
    order_no VARCHAR(40) NOT NULL,
    customer_id BIGINT NOT NULL REFERENCES customer(id),
    status VARCHAR(30) NOT NULL,
    total_amount NUMERIC(19, 2) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL
);

CREATE TABLE order_line (
    id BIGINT PRIMARY KEY,
    order_id BIGINT NOT NULL REFERENCES purchase_order(id),
    product_id BIGINT NOT NULL,
    quantity INTEGER NOT NULL,
    unit_price NUMERIC(19, 2) NOT NULL
);
```

Với màn hình danh sách đơn hàng, DTO có thể là:

```java
public record OrderSummary(
    Long orderId,
    String orderNo,
    String status,
    String customerName,
    BigDecimal totalAmount,
    Long lineCount
) {}
```

Mỗi trường được xác định rõ:

- `orderId`, `orderNo`, `status` và `totalAmount` lấy từ `purchase_order`.
- `customerName` lấy từ `customer`.
- `lineCount` là giá trị aggregate tính từ `order_line`.

Thiết kế DTO trước giúp câu SQL chỉ chọn những cột cần thiết và giúp mapping có hợp đồng rõ ràng. Nếu một trường có thể không tồn tại, chẳng hạn tên khách hàng từ một `LEFT JOIN`, kiểu dữ liệu và quy tắc null của DTO phải phản ánh điều đó.

## 4. Dùng INNER JOIN và LEFT JOIN đúng ý nghĩa

`INNER JOIN` chỉ trả hàng khi hai phía có bản ghi khớp. `LEFT JOIN` giữ tất cả hàng ở phía trái và trả các cột phía phải là null khi không có bản ghi tương ứng.

Ví dụ danh sách đơn hàng luôn có khách hàng hợp lệ:

```sql
SELECT o.id AS order_id,
       o.order_no,
       o.status,
       c.display_name AS customer_name,
       o.total_amount
FROM purchase_order o
INNER JOIN customer c ON c.id = o.customer_id
WHERE o.status = :status
ORDER BY o.created_at DESC, o.id DESC;
```

Nếu muốn giữ đơn hàng ngay cả khi thông tin khách hàng có thể bị thiếu hoặc quan hệ được phép null, dùng `LEFT JOIN`:

```sql
SELECT o.id AS order_id,
       o.order_no,
       o.status,
       c.display_name AS customer_name,
       o.total_amount
FROM purchase_order o
LEFT JOIN customer c ON c.id = o.customer_id
WHERE o.status = :status;
```

Với `LEFT JOIN`, `customer_name` có thể null. Nếu DTO dùng record, kiểu tham chiếu như `String` có thể nhận null; không nên dùng kiểu primitive cho cột có thể null. Cần quyết định ở tầng đọc liệu giữ null, thay bằng giá trị hiển thị mặc định hay loại hàng đó bằng điều kiện lọc.

Một lỗi thường gặp là đặt điều kiện của bảng bên phải trong `WHERE` sau `LEFT JOIN`:

```sql
-- Điều kiện này loại các hàng không có customer khớp,
-- khiến kết quả gần như INNER JOIN.
SELECT o.id, c.display_name
FROM purchase_order o
LEFT JOIN customer c ON c.id = o.customer_id
WHERE c.status = 'ACTIVE';
```

Nếu muốn giữ tất cả đơn hàng nhưng chỉ ghép khách hàng đang hoạt động, đặt điều kiện vào phần `ON`:

```sql
SELECT o.id, c.display_name
FROM purchase_order o
LEFT JOIN customer c
    ON c.id = o.customer_id
   AND c.status = 'ACTIVE';
```

Vị trí điều kiện có thể thay đổi kết quả đáng kể. Hãy xác định bảng nào là phía cần được giữ lại trước khi chọn loại join.

## 5. Ánh xạ kết quả join bằng DatabaseClient

`DatabaseClient` cho phép thực thi SQL và ánh xạ từng `Row` thành kiểu Java mong muốn. Ví dụ lấy danh sách đơn hàng cùng tên khách hàng:

```java
public Flux<OrderSummary> findOrderSummaries(String status) {
    return databaseClient.sql("""
            SELECT o.id AS order_id,
                   o.order_no,
                   o.status,
                   c.display_name AS customer_name,
                   o.total_amount,
                   COUNT(ol.id) AS line_count
            FROM purchase_order o
            JOIN customer c ON c.id = o.customer_id
            LEFT JOIN order_line ol ON ol.order_id = o.id
            WHERE o.status = :status
            GROUP BY o.id, o.order_no, o.status,
                     c.display_name, o.total_amount, o.created_at
            ORDER BY o.created_at DESC, o.id DESC
            """)
        .bind("status", status)
        .map((row, metadata) -> new OrderSummary(
            row.get("order_id", Long.class),
            row.get("order_no", String.class),
            row.get("status", String.class),
            row.get("customer_name", String.class),
            row.get("total_amount", BigDecimal.class),
            row.get("line_count", Long.class)
        ))
        .all();
}
```

Trong ví dụ:

1. `JOIN customer` lấy tên khách hàng.
2. `LEFT JOIN order_line` giữ cả đơn hàng chưa có dòng hàng.
3. `COUNT(ol.id)` đếm số dòng hàng có thật.
4. `GROUP BY` gom các hàng theo đơn hàng để trả một hàng tổng hợp cho mỗi đơn.
5. Alias như `order_id`, `customer_name` và `line_count` tạo tên cột ổn định cho mapper.
6. `map(...)` chuyển từng hàng kết quả thành `OrderSummary`.

`COUNT(ol.id)` được dùng thay vì `COUNT(*)` vì `LEFT JOIN` vẫn tạo một hàng kết quả với các cột `ol` là null khi đơn hàng chưa có dòng hàng. `COUNT(*)` sẽ đếm hàng null mở rộng đó thành 1, trong khi `COUNT(ol.id)` bỏ qua giá trị null và trả 0.

Ví dụ dùng `COUNT` trả kiểu số nguyên lớn; kiểu Java cụ thể cần phù hợp với driver. Với PostgreSQL, `COUNT(*)` thường được ánh xạ thành `Long`. Với kiểu dữ liệu hoặc driver khác, hãy xác nhận kiểu trả về bằng integration test.

## 6. Dùng alias để tránh trùng tên cột

Khi join nhiều bảng, các bảng thường có những cột trùng tên như `id`, `status`, `created_at` hoặc `name`. Nếu không đặt alias, việc đọc `row.get("id")` có thể mơ hồ hoặc không đúng cột mong muốn.

Nên đặt alias theo ý nghĩa của DTO:

```sql
SELECT o.id AS order_id,
       c.id AS customer_id,
       o.status AS order_status,
       c.display_name AS customer_name
FROM purchase_order o
JOIN customer c ON c.id = o.customer_id;
```

Mapper tương ứng:

```java
public record OrderCustomerView(
    Long orderId,
    Long customerId,
    String orderStatus,
    String customerName
) {}
```

```java
.map((row, metadata) -> new OrderCustomerView(
    row.get("order_id", Long.class),
    row.get("customer_id", Long.class),
    row.get("order_status", String.class),
    row.get("customer_name", String.class)
))
```

Alias giúp SQL và Java mapping ít phụ thuộc vào tên cột vật lý, đồng thời làm rõ nguồn của từng giá trị. Khi đổi tên cột trong schema, chỉ cần cập nhật SQL ở lớp truy cập dữ liệu nếu alias công khai vẫn giữ nguyên.

## 7. Ánh xạ giá trị null từ LEFT JOIN

Với `LEFT JOIN`, các cột ở phía phải có thể null. Ví dụ một khách hàng có thể chưa từng đặt đơn:

```sql
SELECT c.id AS customer_id,
       c.display_name AS customer_name,
       o.id AS order_id,
       o.order_no
FROM customer c
LEFT JOIN purchase_order o ON o.customer_id = c.id;
```

DTO dạng một hàng join có thể biểu diễn `orderId` và `orderNo` nullable:

```java
public record CustomerOrderRow(
    Long customerId,
    String customerName,
    Long orderId,
    String orderNo
) {}
```

Khi ánh xạ, `row.get("order_id", Long.class)` có thể trả null nếu khách hàng chưa có đơn. Nếu muốn xây dựng danh sách đơn lồng trong khách hàng, hãy kiểm tra `orderId != null` trước khi tạo đối tượng con. Nếu tạo một `Order` với ID null, ứng dụng có thể vô tình biểu diễn một hàng con không tồn tại thành một object giả.

Không thay null bằng 0 hoặc chuỗi rỗng nếu những giá trị đó có ý nghĩa hợp lệ trong miền dữ liệu. Giữ null giúp phân biệt “không có bản ghi liên quan” với “có bản ghi nhưng giá trị bằng 0/rỗng”.

## 8. Ánh xạ kết quả tổng hợp bằng GROUP BY

Aggregate query trả các giá trị tính từ nhiều hàng, chẳng hạn `COUNT`, `SUM`, `AVG`, `MIN` và `MAX`. Kết quả thường phù hợp với DTO báo cáo hơn entity.

Ví dụ tổng hợp số đơn và doanh thu theo khách hàng:

```sql
SELECT c.id AS customer_id,
       c.display_name AS customer_name,
       COUNT(o.id) AS order_count,
       COALESCE(SUM(o.total_amount), 0) AS revenue,
       MAX(o.created_at) AS last_order_at
FROM customer c
LEFT JOIN purchase_order o
    ON o.customer_id = c.id
   AND o.status IN ('PAID', 'COMPLETED')
GROUP BY c.id, c.display_name
ORDER BY revenue DESC, c.id ASC;
```

DTO:

```java
public record CustomerOrderStats(
    Long customerId,
    String customerName,
    Long orderCount,
    BigDecimal revenue,
    OffsetDateTime lastOrderAt
) {}
```

Ánh xạ:

```java
public Flux<CustomerOrderStats> findCustomerStats() {
    return databaseClient.sql("""
            SELECT c.id AS customer_id,
                   c.display_name AS customer_name,
                   COUNT(o.id) AS order_count,
                   COALESCE(SUM(o.total_amount), 0) AS revenue,
                   MAX(o.created_at) AS last_order_at
            FROM customer c
            LEFT JOIN purchase_order o
                ON o.customer_id = c.id
               AND o.status IN ('PAID', 'COMPLETED')
            GROUP BY c.id, c.display_name
            ORDER BY revenue DESC, c.id ASC
            """)
        .map((row, metadata) -> new CustomerOrderStats(
            row.get("customer_id", Long.class),
            row.get("customer_name", String.class),
            row.get("order_count", Long.class),
            row.get("revenue", BigDecimal.class),
            row.get("last_order_at", OffsetDateTime.class)
        ))
        .all();
}
```

Các điểm cần chú ý:

- `COUNT(o.id)` trả 0 cho khách hàng chưa có đơn phù hợp.
- `SUM(...)` trên tập rỗng có thể trả null; `COALESCE` chuyển thành 0 nếu đó là quy tắc mong muốn.
- `MAX(o.created_at)` vẫn có thể null nếu chưa có đơn.
- `GROUP BY` phải bao gồm các cột không nằm trong aggregate và được chọn trực tiếp, theo quy tắc SQL của database.
- `revenue` là alias của biểu thức tổng hợp; khả năng dùng alias trong `ORDER BY` tùy SQL dialect nhưng được hỗ trợ ở các hệ quản trị phổ biến.

Kiểu thời gian trong DTO cần khớp với kiểu cột và driver. Ví dụ PostgreSQL `TIMESTAMP WITH TIME ZONE` thường được ánh xạ với kiểu thời gian có offset hoặc kiểu được driver hỗ trợ. Không nên giả định mọi driver đều trả đúng cùng một lớp Java.

## 9. Tránh nhân bản số liệu khi join nhiều collection

Một lỗi aggregate phổ biến xuất hiện khi join đồng thời hai quan hệ one-to-many. Giả sử một đơn có 3 dòng hàng và 2 lần thanh toán. Khi join cả `order_line` và `payment`, một đơn có thể tạo ra 3 × 2 = 6 hàng kết quả.

Truy vấn sau có thể đếm và cộng sai:

```sql
SELECT o.id,
       COUNT(ol.id) AS line_count,
       SUM(p.amount) AS paid_amount
FROM purchase_order o
LEFT JOIN order_line ol ON ol.order_id = o.id
LEFT JOIN payment p ON p.order_id = o.id
GROUP BY o.id;
```

Mỗi dòng hàng bị lặp theo số lần thanh toán và mỗi khoản thanh toán bị lặp theo số dòng hàng. `COUNT(DISTINCT ol.id)` có thể sửa phép đếm, nhưng `SUM(DISTINCT p.amount)` không phải giải pháp tổng quát vì hai khoản thanh toán khác nhau có thể có cùng số tiền.

Một cách an toàn là tổng hợp từng collection riêng trước khi join:

```sql
WITH line_stats AS (
    SELECT order_id,
           COUNT(*) AS line_count
    FROM order_line
    GROUP BY order_id
), payment_stats AS (
    SELECT order_id,
           SUM(amount) AS paid_amount
    FROM payment
    WHERE status = 'SUCCESS'
    GROUP BY order_id
)
SELECT o.id AS order_id,
       o.order_no,
       COALESCE(ls.line_count, 0) AS line_count,
       COALESCE(ps.paid_amount, 0) AS paid_amount
FROM purchase_order o
LEFT JOIN line_stats ls ON ls.order_id = o.id
LEFT JOIN payment_stats ps ON ps.order_id = o.id;
```

Mỗi CTE tạo tối đa một hàng cho mỗi `order_id`, vì vậy khi ghép vào đơn hàng sẽ không nhân số liệu giữa hai collection. Cú pháp CTE được hỗ trợ ở các hệ quản trị hiện đại, nhưng cần kiểm tra dialect và execution plan của database đang dùng.

Một cách khác là chạy các truy vấn aggregate độc lập rồi ghép kết quả ở tầng ứng dụng. Hãy chọn theo khối lượng dữ liệu, số lần round trip và yêu cầu nhất quán.

## 10. Ánh xạ một kết quả join phẳng thành mô hình lồng nhau

Một truy vấn join one-to-many thường trả một hàng cho mỗi dòng con. Nếu API cần một object cha chứa danh sách con, ứng dụng phải nhóm các hàng theo ID cha.

Ví dụ DTO trung gian cho mỗi hàng SQL:

```java
public record OrderLineRow(
    Long orderId,
    String orderNo,
    String status,
    Long lineId,
    Long productId,
    Integer quantity,
    BigDecimal unitPrice
) {}
```

DTO cuối cùng:

```java
public record OrderDetail(
    Long orderId,
    String orderNo,
    String status,
    List<OrderLineView> lines
) {}

public record OrderLineView(
    Long lineId,
    Long productId,
    Integer quantity,
    BigDecimal unitPrice
) {}
```

Truy vấn:

```sql
SELECT o.id AS order_id,
       o.order_no,
       o.status,
       l.id AS line_id,
       l.product_id,
       l.quantity,
       l.unit_price
FROM purchase_order o
LEFT JOIN order_line l ON l.order_id = o.id
WHERE o.id = :orderId
ORDER BY l.id;
```

Có thể ánh xạ từng hàng rồi gom theo `orderId`. Ví dụ dưới đây dùng accumulator nội bộ để tránh tạo danh sách dòng hàng giả khi `LEFT JOIN` không tìm thấy dòng con:

```java
private static final class OrderAccumulator {
    final Long id;
    final String orderNo;
    final String status;
    final List<OrderLineView> lines = new ArrayList<>();

    OrderAccumulator(OrderLineRow row) {
        this.id = row.orderId();
        this.orderNo = row.orderNo();
        this.status = row.status();
    }

    OrderDetail toResult() {
        return new OrderDetail(id, orderNo, status, List.copyOf(lines));
    }
}

public Mono<OrderDetail> findOrderDetail(Long orderId) {
    return databaseClient.sql("""
            SELECT o.id AS order_id,
                   o.order_no,
                   o.status,
                   l.id AS line_id,
                   l.product_id,
                   l.quantity,
                   l.unit_price
            FROM purchase_order o
            LEFT JOIN order_line l ON l.order_id = o.id
            WHERE o.id = :orderId
            ORDER BY l.id
            """)
        .bind("orderId", orderId)
        .map((row, metadata) -> new OrderLineRow(
            row.get("order_id", Long.class),
            row.get("order_no", String.class),
            row.get("status", String.class),
            row.get("line_id", Long.class),
            row.get("product_id", Long.class),
            row.get("quantity", Integer.class),
            row.get("unit_price", BigDecimal.class)
        ))
        .all()
        .collectList()
        .flatMap(rows -> {
            if (rows.isEmpty()) {
                return Mono.empty();
            }

            OrderAccumulator order = new OrderAccumulator(rows.get(0));
            for (OrderLineRow row : rows) {
                if (row.lineId() != null) {
                    order.lines.add(new OrderLineView(
                        row.lineId(),
                        row.productId(),
                        row.quantity(),
                        row.unitPrice()
                    ));
                }
            }
            return Mono.just(order.toResult());
        });
}
```

Ví dụ này phù hợp khi chi tiết của một đơn hàng có kích thước giới hạn. `collectList()` giữ toàn bộ hàng của truy vấn trong bộ nhớ; không nên áp dụng cách gom toàn bộ cho một báo cáo lớn hoặc một truy vấn có thể trả hàng triệu dòng. Với tập dữ liệu lớn, hãy phân trang cha, streaming theo nhóm có thứ tự hoặc dùng aggregate/JSON projection phù hợp với database.

Nếu cần phân biệt đơn hàng không tồn tại với đơn hàng có 0 dòng hàng, cách ánh xạ trên xử lý được hai trường hợp: không có hàng kết quả thì trả `Mono.empty()`, còn có một hàng cha với `lineId == null` thì trả `OrderDetail` có danh sách `lines` rỗng.

## 11. Tránh N+1 query khi xây dựng read model

N+1 query xảy ra khi ứng dụng lấy một danh sách cha rồi gọi thêm một truy vấn cho từng bản ghi để lấy dữ liệu liên quan. Ví dụ:

1. Truy vấn lấy 50 đơn hàng.
2. Với mỗi đơn, gọi `customerRepository.findById(...)` để lấy tên khách hàng.
3. Với mỗi đơn, gọi `orderLineRepository.findByOrderId(...)` để lấy dòng hàng.

Số truy vấn có thể tăng từ 1 lên hàng chục hoặc hàng trăm. Một join có projection phù hợp thường giảm số round trip:

```sql
SELECT o.id AS order_id,
       o.order_no,
       c.display_name AS customer_name,
       o.total_amount
FROM purchase_order o
JOIN customer c ON c.id = o.customer_id
WHERE o.status = :status
ORDER BY o.created_at DESC, o.id DESC
LIMIT :limit;
```

Không phải lúc nào join cũng là lựa chọn tốt nhất. Nếu dữ liệu liên quan rất lớn hoặc có cardinality cao, có thể lấy trang ID cha trước rồi tải dữ liệu con theo một truy vấn `WHERE order_id IN (...)`. Cách này vẫn tránh N+1 mà không tạo một result set phẳng quá lớn.

## 12. Phân trang khi join one-to-many

Một lỗi quan trọng là đặt `LIMIT` trực tiếp lên result set sau join collection. Nếu một đơn có nhiều dòng hàng, `LIMIT 20` có thể chỉ trả về một phần dòng hàng của đơn cuối cùng hoặc chiếm hết trang bởi một vài đơn có nhiều dòng.

Nếu mục tiêu là phân trang theo đơn hàng, hãy phân trang tập đơn hàng trước rồi mới join các dòng hàng:

```sql
WITH order_page AS (
    SELECT id, order_no, status, created_at
    FROM purchase_order
    WHERE status = :status
    ORDER BY created_at DESC, id DESC
    LIMIT :pageSize OFFSET :offset
)
SELECT p.id AS order_id,
       p.order_no,
       p.status,
       l.id AS line_id,
       l.product_id,
       l.quantity
FROM order_page p
LEFT JOIN order_line l ON l.order_id = p.id
ORDER BY p.created_at DESC, p.id DESC, l.id ASC;
```

CTE `order_page` xác định chính xác tập đơn hàng của trang. Truy vấn ngoài mới lấy các dòng hàng của những đơn đó. Kết quả vẫn có thể nhiều hàng hơn `pageSize` vì mỗi đơn có nhiều dòng, nhưng không làm mất dòng hàng chỉ vì giới hạn trang được áp dụng sau join.

Nếu chỉ cần thông tin tổng hợp cho danh sách, hãy aggregate `order_line` trước hoặc join với subquery đã group theo `order_id`, để mỗi đơn chỉ còn một hàng kết quả. Khi dùng offset hoặc keyset pagination, thứ tự của tập cha phải ổn định và có khóa duy nhất làm tie-breaker.

## 13. Aggregate và các hàm thường dùng

Các hàm tổng hợp thường xuất hiện trong read model:

| Hàm | Ý nghĩa | Lưu ý |
|---|---|---|
| `COUNT(*)` | Đếm số hàng trong nhóm | Đếm cả hàng mở rộng từ `LEFT JOIN` |
| `COUNT(column)` | Đếm giá trị khác null | Phù hợp để đếm bản ghi con có thật sau `LEFT JOIN` |
| `COUNT(DISTINCT column)` | Đếm giá trị duy nhất | Có thể tốn tài nguyên; không sửa được mọi lỗi nhân bản dữ liệu |
| `SUM(column)` | Tổng các giá trị | Trả null khi không có giá trị; dùng `COALESCE` nếu muốn 0 |
| `AVG(column)` | Trung bình | Cần xác định quy tắc làm tròn và kiểu kết quả |
| `MIN` / `MAX` | Giá trị nhỏ nhất/lớn nhất | Có thể trả null khi nhóm không có giá trị |

Ví dụ báo cáo doanh thu theo ngày:

```sql
SELECT CAST(created_at AS DATE) AS order_day,
       COUNT(*) AS order_count,
       SUM(total_amount) AS revenue,
       AVG(total_amount) AS average_order_value
FROM purchase_order
WHERE status IN ('PAID', 'COMPLETED')
  AND created_at >= :fromTime
  AND created_at < :toTime
GROUP BY CAST(created_at AS DATE)
ORDER BY order_day ASC;
```

DTO:

```java
public record DailySales(
    LocalDate orderDay,
    Long orderCount,
    BigDecimal revenue,
    BigDecimal averageOrderValue
) {}
```

Khi ánh xạ aggregate, cần kiểm tra kiểu số mà driver trả về. Tiền nên dùng `BigDecimal`, không dùng `double` hoặc `float` cho phép tính cần độ chính xác thập phân. Nếu cần quy tắc làm tròn cụ thể, hãy xác định ở SQL hoặc tầng ứng dụng theo yêu cầu nghiệp vụ.

## 14. Dùng subquery hoặc CTE để tách bước tổng hợp

Khi truy vấn cần nhiều cấp tổng hợp, subquery hoặc CTE giúp tách logic thành từng phần dễ hiểu.

Ví dụ tổng hợp doanh thu theo khách hàng trước, rồi chỉ lấy khách hàng có doanh thu vượt ngưỡng:

```sql
WITH customer_revenue AS (
    SELECT customer_id,
           COUNT(*) AS order_count,
           SUM(total_amount) AS revenue
    FROM purchase_order
    WHERE status IN ('PAID', 'COMPLETED')
    GROUP BY customer_id
)
SELECT c.id AS customer_id,
       c.display_name AS customer_name,
       cr.order_count,
       cr.revenue
FROM customer_revenue cr
JOIN customer c ON c.id = cr.customer_id
WHERE cr.revenue >= :minimumRevenue
ORDER BY cr.revenue DESC, c.id ASC;
```

CTE làm rõ thứ tự tư duy: tổng hợp giao dịch trước, sau đó ghép tên khách hàng và lọc kết quả. Optimizer của database có thể inline hoặc materialize CTE tùy hệ quản trị và phiên bản; không nên giả định CTE luôn là một bảng tạm được lưu vật lý.

## 15. Khi nào nên dùng DatabaseClient và khi nào dùng Template?

`R2dbcEntityTemplate` phù hợp với thao tác entity theo mapping metadata: insert, select, update và delete theo `Query`/`Criteria`. API này thuận tiện khi truy vấn tập trung vào một entity và các thuộc tính của nó.

`DatabaseClient` phù hợp hơn khi cần:

- Join nhiều bảng và trả DTO riêng.
- Aggregate với `GROUP BY`, `HAVING`, CTE hoặc window function.
- Projection có biểu thức SQL hoặc alias tùy chỉnh.
- Dùng cú pháp đặc thù của một database.
- Kiểm soát chính xác cách ánh xạ từng cột trong `Row`.

Có thể đóng gói câu SQL trong một custom repository fragment để Service không phải biết chi tiết truy vấn. Nếu truy vấn chỉ dùng một lần trong một lớp nghiệp vụ, hãy cân nhắc đặt nó trong một lớp query repository riêng để giữ trách nhiệm rõ ràng.

Không nên chọn `R2dbcEntityTemplate` chỉ vì muốn tránh viết SQL nếu truy vấn join hoặc aggregate không được abstraction đó biểu diễn tự nhiên. Ngược lại, không cần dùng SQL thuần cho một thao tác CRUD đơn giản mà Repository đã hỗ trợ tốt.

## 16. Ánh xạ kiểu dữ liệu và xử lý giá trị đặc thù

Khi dùng `DatabaseClient`, mapper phải đọc đúng kiểu dữ liệu mà driver cung cấp. Một số trường hợp cần lưu ý:

- `BIGINT` thường ánh xạ sang `Long`.
- `INTEGER` thường ánh xạ sang `Integer`.
- `NUMERIC`/`DECIMAL` nên ánh xạ sang `BigDecimal`.
- `COUNT` thường trả kiểu số nguyên lớn, nhưng cần kiểm tra theo driver.
- Cột nullable từ `LEFT JOIN` phải được xử lý như giá trị có thể null.
- Timestamp có hoặc không có timezone cần kiểu Java tương ứng và quy ước timezone rõ ràng.
- JSON, array, enum và kiểu dữ liệu riêng phụ thuộc driver, converter hoặc cách truy vấn.

Nếu kiểu Java không khớp kiểu mà driver hỗ trợ, `row.get(column, TargetType.class)` có thể trả lỗi chuyển đổi. Khi cần chuyển đổi phức tạp, có thể dùng converter hoặc đọc kiểu nguồn rồi chuyển đổi có kiểm soát. Không nên ép kiểu tùy tiện mà không kiểm tra dữ liệu null và độ chính xác.

Với aggregate, alias nên ổn định và duy nhất. Tránh chọn hai cột cùng tên mà không alias vì mapper có thể đọc nhầm hoặc khó bảo trì khi thêm join mới.

## 17. Bảo mật và tính đúng đắn của SQL tùy chỉnh

Khi xây dựng truy vấn join hoặc aggregate từ request, mọi giá trị như trạng thái, tenant ID, thời gian và ngưỡng doanh thu cần bind parameter:

```java
databaseClient.sql("""
        SELECT customer_id, SUM(total_amount) AS revenue
        FROM purchase_order
        WHERE status = :status
          AND created_at >= :fromTime
        GROUP BY customer_id
        HAVING SUM(total_amount) >= :minimumRevenue
        """)
    .bind("status", status)
    .bind("fromTime", fromTime)
    .bind("minimumRevenue", minimumRevenue);
```

Không nối trực tiếp giá trị người dùng vào SQL. Tên bảng, tên cột, hướng sort và biểu thức SQL không thể được bind như một giá trị; nếu chúng cần thay đổi, hãy dùng allow-list cố định trong code.

Ngoài SQL injection, cần bảo đảm điều kiện phạm vi dữ liệu luôn được áp dụng. Ví dụ, truy vấn multi-tenant phải lọc theo tenant đã được xác thực ở phía server, không chỉ dựa vào tenant ID client tự gửi. Một câu join đúng cú pháp nhưng thiếu điều kiện tenant có thể trả dữ liệu của khách hàng khác.

## 18. Hiệu năng và index cho truy vấn join/aggregate

Join và aggregate có thể đọc nhiều hàng, nên cần xem xét index và execution plan:

- Index trên foreign key dùng để join, ví dụ `purchase_order.customer_id` và `order_line.order_id`.
- Index trên cột filter như `status`, `created_at` hoặc `tenant_id` tùy độ chọn lọc và workload.
- Index ghép có thứ tự phù hợp với điều kiện lọc và sắp xếp.
- Chỉ chọn các cột cần thiết, tránh `SELECT *` trong read model.
- Aggregate dữ liệu trước khi join nếu join nhiều collection có thể nhân bản hàng.
- Phân trang tập cha trước khi join collection one-to-many.
- Đo chi phí `COUNT(DISTINCT ...)`, `GROUP BY`, sort và CTE trên dữ liệu gần thực tế.

Với PostgreSQL, `EXPLAIN (ANALYZE, BUFFERS)` giúp xem số hàng thực tế, thời gian và buffer được đọc. Cần lưu ý `ANALYZE` thực sự thực thi truy vấn. Với database khác, dùng công cụ execution plan tương ứng.

Không phải cứ thêm index là truy vấn sẽ nhanh hơn. Index làm tăng chi phí ghi và dung lượng lưu trữ; optimizer có thể chọn scan nếu bảng nhỏ hoặc điều kiện không đủ chọn lọc. Hãy dựa vào số liệu đo được.

## 19. Tính nhất quán khi chạy nhiều truy vấn để ghép read model

Đôi khi ứng dụng lấy trang đơn hàng bằng một truy vấn, rồi lấy thống kê hoặc dữ liệu con bằng truy vấn thứ hai theo danh sách ID. Cách này tránh N+1, nhưng dữ liệu giữa các truy vấn có thể thay đổi nếu một transaction khác cập nhật trong lúc đó.

Nếu read model cần phản ánh cùng một snapshot, hãy xem xét isolation level và transaction phù hợp. Trong reactive transaction, các publisher cần được ghép trong cùng chuỗi và sử dụng cùng transaction manager/`ConnectionFactory`. Không gọi `subscribe()` hoặc `block()` giữa các bước.

Không nên giữ transaction mở trong khi ứng dụng chờ người dùng hoặc gọi dịch vụ bên ngoài. Với dashboard có thể chấp nhận dữ liệu gần đúng hoặc trễ nhẹ, một read model tổng hợp được cập nhật định kỳ hoặc bất đồng bộ có thể phù hợp hơn việc giữ transaction dài.

## 20. Read model vật lý và CQRS

Read model không nhất thiết chỉ được tạo bằng một câu SELECT. Khi join và aggregate quá tốn kém nhưng được gọi thường xuyên, có thể lưu kết quả vào một bảng hoặc materialized view riêng.

Ví dụ bảng thống kê khách hàng:

```sql
CREATE TABLE customer_order_stats (
    customer_id BIGINT PRIMARY KEY REFERENCES customer(id),
    order_count BIGINT NOT NULL,
    total_revenue NUMERIC(19, 2) NOT NULL,
    last_order_at TIMESTAMP WITH TIME ZONE
);
```

Bảng này có thể được cập nhật:

- Trong cùng transaction với thao tác ghi nếu cần đồng bộ tức thời và chi phí tính toán phù hợp.
- Bất đồng bộ qua event/outbox nếu chấp nhận độ trễ và cần tách workload đọc/ghi.
- Theo lịch bằng job tổng hợp lại từ dữ liệu nguồn.
- Bằng materialized view và cơ chế refresh nếu database hỗ trợ.

Đây là một dạng tách mô hình đọc/ghi thường gặp trong CQRS. Cần xác định rõ dữ liệu nguồn nào là nguồn sự thật, độ trễ cho phép, cách xử lý event bị lặp hoặc mất, và cách rebuild read model khi có sai lệch.

Không nên tạo bảng tổng hợp chỉ để tối ưu một truy vấn chưa được đo. Read model vật lý làm tăng công việc đồng bộ, lưu trữ và vận hành. Trước hết hãy tối ưu SQL, index và projection; chỉ tách read model khi workload chứng minh cần thiết.

## 21. Kiểm thử mapping join và aggregate

Unit test có thể kiểm tra logic chuyển đổi nếu mapper được tách riêng, nhưng integration test cần xác nhận SQL và kiểu dữ liệu trên driver thực tế.

Nên kiểm tra các trường hợp:

- `INNER JOIN` loại hàng không có quan hệ; `LEFT JOIN` giữ hàng cha theo đúng yêu cầu.
- Các cột trùng tên được alias và ánh xạ đúng.
- Quan hệ one-to-many tạo đúng số dòng con, không bị trùng.
- Cha không có con tạo danh sách rỗng thay vì object con có ID null.
- `COUNT`, `SUM`, `AVG`, `MIN`, `MAX` trả giá trị và kiểu dữ liệu mong muốn.
- `COALESCE` xử lý tập rỗng đúng quy tắc nghiệp vụ.
- Join nhiều collection không làm nhân bản tổng hoặc số lượng.
- Phân trang áp dụng cho tập cha trước khi ghép collection.
- Điều kiện tenant và authorization scope luôn được áp dụng.
- Transaction giữ tính nhất quán khi ghép nhiều truy vấn.

Nếu dùng Testcontainers, hãy chạy test với cùng hệ quản trị dự kiến triển khai. H2 có thể không phản ánh đầy đủ cú pháp, kiểu dữ liệu, aggregate hoặc hành vi driver của PostgreSQL, SQL Server hay Oracle.

## 22. Quy trình xây dựng read model từ join hoặc aggregate

Có thể thực hiện theo trình tự sau:

**Bước 1 — Xác định use case đọc.** Ghi rõ màn hình hoặc báo cáo cần dữ liệu gì, filter nào, thứ tự nào và có cần phân trang hay không.

**Bước 2 — Thiết kế DTO/read model.** Xác định từng trường, kiểu dữ liệu, khả năng null và nguồn dữ liệu.

**Bước 3 — Chọn loại join.** Dùng `INNER JOIN` khi cần bản ghi khớp ở cả hai phía; dùng `LEFT JOIN` khi phải giữ hàng phía trái kể cả khi thiếu quan hệ.

**Bước 4 — Viết SQL có alias rõ ràng.** Chọn đúng cột, đặt alias duy nhất và bind mọi giá trị đầu vào.

**Bước 5 — Xác định cardinality.** Kiểm tra quan hệ one-to-one, one-to-many và many-to-many; tránh nhân bản hàng khi join nhiều collection.

**Bước 6 — Xây dựng aggregate hoặc nhóm hàng.** Dùng `GROUP BY`, subquery/CTE hoặc gom hàng phẳng thành DTO lồng nhau tùy hình dạng kết quả.

**Bước 7 — Ánh xạ bằng DatabaseClient.** Đọc đúng kiểu cột, xử lý null và trả `Mono`/`Flux` phù hợp.

**Bước 8 — Tối ưu truy vấn.** Kiểm tra index, execution plan, giới hạn dữ liệu và tránh N+1.

**Bước 9 — Kiểm thử trên database thật.** Xác nhận mapping, aggregate, pagination, transaction và phạm vi dữ liệu.

## 23. Kết luận

Kết quả join hoặc tổng hợp thường phục vụ một use case đọc cụ thể và không cần được ép thành entity của một bảng. Hãy thiết kế DTO/read model theo dữ liệu thực sự cần trả về, dùng alias để ánh xạ rõ ràng, xử lý null của `LEFT JOIN`, và hiểu cardinality để tránh nhân bản số liệu khi ghép nhiều collection.

Trong Spring Data R2DBC, `DatabaseClient` là lựa chọn phù hợp để thực hiện SQL join, `GROUP BY`, CTE và projection tùy chỉnh rồi ánh xạ `Row` thành DTO. Với kết quả one-to-many, có thể gom các hàng phẳng thành mô hình lồng nhau khi kích thước được giới hạn; với dữ liệu lớn, hãy phân trang tập cha hoặc tổng hợp ở database. Kết hợp SQL đúng, mapping rõ ràng, index phù hợp và integration test trên driver thật giúp read model phản ánh chính xác dữ liệu mà màn hình hoặc báo cáo cần.
