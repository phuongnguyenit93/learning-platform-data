# Truy vấn join và ghép kết quả thành cấu trúc dữ liệu mong muốn

Trong Spring Data Relational R2DBC, một truy vấn `JOIN` thường trả về nhiều hàng phẳng từ database. Ứng dụng có thể cần biến các hàng đó thành một cấu trúc Java khác, chẳng hạn một customer kèm danh sách order, một order kèm các dòng hàng, hoặc một DTO tổng hợp chứa thông tin từ nhiều bảng.

Phần SQL join và phần ghép kết quả là hai công việc riêng. Database chịu trách nhiệm kết hợp các bảng theo điều kiện `ON`, lọc, sắp xếp và tính toán. R2DBC driver phát từng hàng kết quả; Spring Data hoặc `DatabaseClient` ánh xạ các cột thành giá trị Java. Sau đó ứng dụng có thể nhóm các hàng và tạo cấu trúc lồng nhau bằng các toán tử Reactor.

Spring Data Relational R2DBC không cung cấp persistence context và cơ chế lazy loading/fetch join như JPA/Hibernate. Vì vậy, khi cần dữ liệu từ nhiều bảng, hãy chủ động viết truy vấn join hoặc dùng mô hình aggregate mapping phù hợp. Không nên kỳ vọng chỉ khai báo một object reference là framework tự tải quan hệ khi đọc entity.

## 1. Join kết hợp dữ liệu ở database

Giả sử hệ thống có hai bảng `customer` và `orders`:

```sql
CREATE TABLE customer (
    id BIGINT PRIMARY KEY,
    name VARCHAR(200) NOT NULL,
    email VARCHAR(200) NOT NULL
);

CREATE TABLE orders (
    id BIGINT PRIMARY KEY,
    customer_id BIGINT NOT NULL REFERENCES customer(id),
    order_number VARCHAR(40) NOT NULL,
    total_amount DECIMAL(18, 2) NOT NULL
);
```

Một customer có thể có nhiều order. Truy vấn join:

```sql
SELECT
    c.id AS customer_id,
    c.name AS customer_name,
    c.email AS customer_email,
    o.id AS order_id,
    o.order_number AS order_number,
    o.total_amount AS order_total
FROM customer c
LEFT JOIN orders o ON o.customer_id = c.id
ORDER BY c.id, o.id;
```

`LEFT JOIN` giữ customer ngay cả khi chưa có order. Với customer có ba order, kết quả có ba hàng chứa thông tin customer lặp lại và thông tin mỗi order khác nhau. Với customer chưa có order, kết quả vẫn có một hàng customer, còn các cột của `orders` là SQL `NULL`.

Ví dụ kết quả phẳng:

| customer_id | customer_name | order_id | order_number | order_total |
| ---: | --- | ---: | --- | ---: |
| 10 | Lan | 501 | ORD-501 | 120.00 |
| 10 | Lan | 502 | ORD-502 | 80.00 |
| 10 | Lan | 503 | ORD-503 | 45.00 |
| 11 | Minh | NULL | NULL | NULL |

Ứng dụng có thể cần kết quả dạng:

```json
[
  {
    "id": 10,
    "name": "Lan",
    "orders": [
      { "id": 501, "number": "ORD-501", "total": 120.00 },
      { "id": 502, "number": "ORD-502", "total": 80.00 },
      { "id": 503, "number": "ORD-503", "total": 45.00 }
    ]
  },
  {
    "id": 11,
    "name": "Minh",
    "orders": []
  }
]
```

Đây là cấu trúc lồng nhau được ứng dụng dựng từ nhiều hàng kết quả. SQL join không tự biến nhiều hàng thành một object có collection con.

## 2. Chọn đúng loại JOIN

Các loại join thường gặp:

| Loại join | Kết quả | Trường hợp thường dùng |
| --- | --- | --- |
| `INNER JOIN` | Chỉ giữ các hàng có cặp khớp ở cả hai phía | Chỉ lấy customer có order |
| `LEFT JOIN` | Giữ tất cả hàng bên trái; cột bên phải là NULL nếu không có cặp khớp | Lấy mọi customer và order nếu có |
| `RIGHT JOIN` | Giữ tất cả hàng bên phải; cột bên trái là NULL nếu không khớp | Ít gặp hơn; thường có thể đổi thứ tự bảng và dùng LEFT JOIN |
| `FULL OUTER JOIN` | Giữ hàng ở cả hai phía dù không có cặp khớp | Đối chiếu hai tập dữ liệu; hỗ trợ phụ thuộc database |
| `CROSS JOIN` | Tạo tích Descartes giữa hai tập hàng | Kết hợp mọi cặp khi thực sự cần |

Ví dụ `INNER JOIN`:

```sql
SELECT c.id, c.name, o.id AS order_id
FROM customer c
INNER JOIN orders o ON o.customer_id = c.id;
```

Customer không có order sẽ không xuất hiện. Nếu response cần thể hiện customer với danh sách order rỗng, dùng `LEFT JOIN`.

### Đặt điều kiện ở `ON` hay `WHERE`

Với `LEFT JOIN`, vị trí đặt điều kiện có thể làm thay đổi ý nghĩa:

```sql
-- Giữ tất cả customer; chỉ nối các order đã thanh toán.
SELECT c.id, c.name, o.id AS order_id
FROM customer c
LEFT JOIN orders o
    ON o.customer_id = c.id
   AND o.status = 'PAID';
```

Ngược lại:

```sql
-- WHERE loại các hàng có o.status là NULL,
-- nên customer không có order bị loại khỏi kết quả.
SELECT c.id, c.name, o.id AS order_id
FROM customer c
LEFT JOIN orders o ON o.customer_id = c.id
WHERE o.status = 'PAID';
```

Điều kiện trên bảng bên phải trong `WHERE` có thể khiến `LEFT JOIN` hoạt động như `INNER JOIN` đối với điều kiện đó. Nếu mục tiêu là giữ hàng bên trái khi không có hàng phù hợp bên phải, hãy cân nhắc đặt điều kiện lọc bảng phải trong `ON`.

## 3. Dùng alias để ánh xạ hàng join rõ ràng

Khi join nhiều bảng, các bảng thường có cột trùng tên như `id`, `name`, `created_at`. Không nên chọn `SELECT *` rồi hy vọng mapper luôn phân biệt được các cột. Hãy liệt kê cột cần dùng và đặt alias duy nhất:

```sql
SELECT
    c.id AS customer_id,
    c.name AS customer_name,
    o.id AS order_id,
    o.order_number AS order_number
FROM customer c
LEFT JOIN orders o ON o.customer_id = c.id;
```

Alias giúp code mapping đọc đúng cột và tránh xung đột tên. Khi đọc bằng `Row`, dùng alias đã khai báo:

```java
row.get("customer_id", Long.class);
row.get("customer_name", String.class);
row.get("order_id", Long.class);
```

Tên alias trong SQL và tên dùng trong `row.get` phải nhất quán. Quy tắc chữ hoa/thường của alias có thể phụ thuộc database; nên dùng tên đơn giản, nhất quán và kiểm thử với driver thật.

## 4. Ánh xạ một hàng join thành DTO phẳng

`DatabaseClient` phù hợp với truy vấn join tùy chỉnh vì cho phép viết SQL và ánh xạ từng hàng trực tiếp. Trước tiên, tạo DTO đại diện cho một hàng join:

```java
public record CustomerOrderRow(
        Long customerId,
        String customerName,
        String customerEmail,
        Long orderId,
        String orderNumber,
        BigDecimal orderTotal
) {
}
```

Truy vấn và mapper:

```java
Flux<CustomerOrderRow> rows = databaseClient.sql("""
            SELECT
                c.id AS customer_id,
                c.name AS customer_name,
                c.email AS customer_email,
                o.id AS order_id,
                o.order_number AS order_number,
                o.total_amount AS order_total
            FROM customer c
            LEFT JOIN orders o ON o.customer_id = c.id
            ORDER BY c.id, o.id
            """)
        .map((row, metadata) -> new CustomerOrderRow(
                row.get("customer_id", Long.class),
                row.get("customer_name", String.class),
                row.get("customer_email", String.class),
                row.get("order_id", Long.class),
                row.get("order_number", String.class),
                row.get("order_total", BigDecimal.class)
        ))
        .all();
```

Mỗi hàng SQL tạo ra một `CustomerOrderRow`. Với `LEFT JOIN`, `orderId`, `orderNumber` và `orderTotal` có thể null nếu customer không có order. Vì vậy DTO phải cho phép các giá trị này null; không dùng primitive `long` cho cột có thể null.

Ở bước này, kết quả vẫn là một luồng hàng phẳng. Muốn có một `Customer` kèm `List<Order>`, cần nhóm các hàng theo `customerId`.

## 5. Ghép nhiều hàng thành một object có collection con

Khi join one-to-many, thông tin phía cha bị lặp trên mỗi hàng. Cách phổ biến là gom hàng theo ID cha, khởi tạo object cha ở lần gặp đầu tiên rồi thêm child vào collection tương ứng.

Định nghĩa response DTO:

```java
public record OrderView(
        Long id,
        String number,
        BigDecimal total
) {
}

public record CustomerWithOrders(
        Long id,
        String name,
        String email,
        List<OrderView> orders
) {
}
```

Để gom kết quả, có thể dùng builder nội bộ:

```java
private static final class CustomerBuilder {
    private final Long id;
    private final String name;
    private final String email;
    private final List<OrderView> orders = new ArrayList<>();

    private CustomerBuilder(Long id, String name, String email) {
        this.id = id;
        this.name = name;
        this.email = email;
    }

    private CustomerWithOrders build() {
        return new CustomerWithOrders(
                id, name, email, List.copyOf(orders)
        );
    }
}
```

Sau đó nhóm bằng `LinkedHashMap`:

```java
public Mono<List<CustomerWithOrders>> findCustomersWithOrders() {
    return queryCustomerOrderRows()
            .collect(
                    LinkedHashMap<Long, CustomerBuilder>::new,
                    (customers, row) -> {
                        CustomerBuilder customer = customers.computeIfAbsent(
                                row.customerId(),
                                id -> new CustomerBuilder(
                                        id,
                                        row.customerName(),
                                        row.customerEmail()
                                )
                        );

                        // LEFT JOIN tạo một hàng child NULL khi customer không có order.
                        if (row.orderId() != null) {
                            customer.orders.add(new OrderView(
                                    row.orderId(),
                                    row.orderNumber(),
                                    row.orderTotal()
                            ));
                        }
                    }
            )
            .map(customers -> customers.values().stream()
                    .map(CustomerBuilder::build)
                    .toList());
}
```

`queryCustomerOrderRows()` đại diện cho publisher `Flux<CustomerOrderRow>` ở phần trước. `collect` tiêu thụ toàn bộ hàng, dùng `customerId` làm khóa để bảo đảm mỗi customer chỉ có một builder. Mỗi order hợp lệ được thêm vào danh sách của customer. Nếu customer không có order, builder vẫn được tạo nhưng danh sách giữ rỗng.

`LinkedHashMap` giữ thứ tự gặp đầu tiên, hữu ích khi SQL đã có `ORDER BY`. Nếu không cần giữ thứ tự, có thể dùng `HashMap`. Việc nhóm dữ liệu trong ví dụ này cần giữ state trong bộ nhớ cho tới khi tất cả hàng đã được tiêu thụ, nên phù hợp với kết quả có kích thước giới hạn. Với tập dữ liệu lớn, nên phân trang hoặc nhóm theo từng phần thay vì gom toàn bộ vào một collection.

## 6. Vì sao phải kiểm tra child ID sau LEFT JOIN?

Với `LEFT JOIN`, các cột của bảng con đều null nếu không có hàng khớp. Để xác định child có tồn tại hay không, hãy kiểm tra cột khóa chính của child:

```java
if (row.orderId() != null) {
    // Có order; thêm vào danh sách.
}
```

Không nên kiểm tra một property nghiệp vụ có thể nullable:

```java
// Không đủ tin cậy nếu order_number có thể NULL.
if (row.orderNumber() != null) {
    // Có thể bỏ sót một order hợp lệ.
}
```

Khóa chính của một hàng tồn tại không thể SQL NULL. Vì vậy, alias của child ID là dấu hiệu đáng tin cậy để phân biệt hàng child thật với hàng null do outer join tạo ra.

Nếu response cần phân biệt “không có child” với “child có dữ liệu nhưng một số thuộc tính null”, hãy dùng child primary key làm điều kiện tạo object và giữ nguyên các property nullable.

## 7. Join nhiều cấp và tránh nhân bản child

Giả sử cấu trúc dữ liệu có ba cấp:

```text
Customer
  └── Orders
        └── OrderLines
```

Một truy vấn join cả ba bảng:

```sql
SELECT
    c.id AS customer_id,
    c.name AS customer_name,
    o.id AS order_id,
    o.order_number AS order_number,
    l.id AS line_id,
    l.product_name AS product_name,
    l.quantity AS quantity
FROM customer c
LEFT JOIN orders o ON o.customer_id = c.id
LEFT JOIN order_line l ON l.order_id = o.id
ORDER BY c.id, o.id, l.id;
```

Nếu một order có ba line, thông tin customer và order lặp lại ba lần. Nếu chỉ thêm một `OrderView` cho mỗi hàng, response sẽ có ba order trùng nhau. Cần nhóm theo customer ID, rồi nhóm tiếp theo order ID và chỉ thêm line mới theo line ID.

Một cấu trúc builder có thể dùng map lồng nhau:

```java
private static final class OrderBuilder {
    private final Long id;
    private final String number;
    private final Map<Long, OrderLineView> lines = new LinkedHashMap<>();

    private OrderBuilder(Long id, String number) {
        this.id = id;
        this.number = number;
    }
}

private static final class CustomerBuilder {
    private final Long id;
    private final String name;
    private final Map<Long, OrderBuilder> orders = new LinkedHashMap<>();

    private CustomerBuilder(Long id, String name) {
        this.id = id;
        this.name = name;
    }
}
```

Trong accumulator:

```java
CustomerBuilder customer = customers.computeIfAbsent(
        row.customerId(),
        id -> new CustomerBuilder(id, row.customerName())
);

if (row.orderId() != null) {
    OrderBuilder order = customer.orders.computeIfAbsent(
            row.orderId(),
            id -> new OrderBuilder(id, row.orderNumber())
    );

    if (row.lineId() != null) {
        order.lines.putIfAbsent(
                row.lineId(),
                new OrderLineView(
                        row.lineId(),
                        row.productName(),
                        row.quantity()
                )
        );
    }
}
```

`putIfAbsent` theo ID line ngăn một line bị thêm nhiều lần do join với một bảng con khác. Khi hoàn tất, duyệt map để dựng immutable DTO: mỗi customer chứa danh sách order, mỗi order chứa danh sách line.

Với nhiều quan hệ one-to-many cùng được join, số hàng trung gian có thể tăng theo tích số lượng phần tử của từng quan hệ. Ví dụ customer có 4 order và mỗi order có 5 line thì join tạo khoảng 20 hàng cho customer đó. Cần cân nhắc chi phí truyền dữ liệu và việc group trong bộ nhớ.

## 8. Join nhiều bảng nhưng chỉ cần DTO phẳng

Không phải truy vấn join nào cũng cần dựng object lồng nhau. Với màn hình danh sách hoặc báo cáo, DTO phẳng thường đơn giản và hiệu quả hơn:

```java
public record OrderSummary(
        Long orderId,
        String orderNumber,
        String customerName,
        BigDecimal totalAmount
) {
}
```

Truy vấn:

```java
Flux<OrderSummary> summaries = databaseClient.sql("""
            SELECT
                o.id AS order_id,
                o.order_number AS order_number,
                c.name AS customer_name,
                o.total_amount AS total_amount
            FROM orders o
            INNER JOIN customer c ON c.id = o.customer_id
            WHERE o.status = :status
            ORDER BY o.id DESC
            """)
        .bind("status", "PAID")
        .map((row, metadata) -> new OrderSummary(
                row.get("order_id", Long.class),
                row.get("order_number", String.class),
                row.get("customer_name", String.class),
                row.get("total_amount", BigDecimal.class)
        ))
        .all();
```

Ở đây mỗi hàng order tạo một `OrderSummary`. Không cần gom theo customer nếu response mong muốn là danh sách order kèm tên customer. Chọn DTO theo cấu trúc mà tầng API hoặc nghiệp vụ cần, không phải theo hình dạng entity của từng bảng.

## 9. Aggregate dữ liệu ngay trong SQL khi không cần collection con

Nếu mục tiêu là tổng hợp số liệu, nên để database thực hiện `COUNT`, `SUM`, `MIN`, `MAX` hoặc `GROUP BY` thay vì tải mọi hàng về rồi tự tính trong Java.

Ví dụ tổng số order và tổng tiền theo customer:

```sql
SELECT
    c.id AS customer_id,
    c.name AS customer_name,
    COUNT(o.id) AS order_count,
    COALESCE(SUM(o.total_amount), 0) AS total_spent
FROM customer c
LEFT JOIN orders o ON o.customer_id = c.id
GROUP BY c.id, c.name
ORDER BY c.id;
```

DTO:

```java
public record CustomerOrderStats(
        Long customerId,
        String customerName,
        Long orderCount,
        BigDecimal totalSpent
) {
}
```

Mapping:

```java
Flux<CustomerOrderStats> stats = databaseClient.sql(sql)
        .map((row, metadata) -> new CustomerOrderStats(
                row.get("customer_id", Long.class),
                row.get("customer_name", String.class),
                row.get("order_count", Long.class),
                row.get("total_spent", BigDecimal.class)
        ))
        .all();
```

`COUNT(o.id)` trả `0` cho customer không có order trong trường hợp `LEFT JOIN`; `COUNT(*)` có thể trả `1` vì hàng customer vẫn tồn tại sau outer join. Đây là lý do cần đếm cột khóa của bảng con khi muốn đếm số child.

`COALESCE` thay SQL NULL của `SUM` bằng `0` trong trường hợp không có order. Kiểu trả về của aggregate phụ thuộc database và kiểu cột; mapper phải dùng kiểu Java tương thích. Nếu database trả numeric với precision khác, cần kiểm tra conversion thực tế.

## 10. Dùng `@Query` trong repository cho join

Có thể khai báo join SQL ngay trong repository bằng `@Query` nếu câu lệnh ổn định và muốn repository sở hữu query:

```java
public interface CustomerReadRepository
        extends Repository<Customer, Long> {

    @Query("""
           SELECT
               c.id AS customer_id,
               c.name AS customer_name,
               o.id AS order_id,
               o.order_number AS order_number
           FROM customer c
           LEFT JOIN orders o ON o.customer_id = c.id
           WHERE c.id = :customerId
           ORDER BY o.id
           """)
    Flux<CustomerOrderRow> findCustomerOrders(
            @Param("customerId") Long customerId
    );
}
```

Khả năng projection/interface hoặc DTO mapping của `@Query` phụ thuộc phiên bản Spring Data R2DBC và kiểu projection được hỗ trợ. Nếu cần kiểm soát chắc chắn việc lấy alias và chuyển kiểu từng cột, `DatabaseClient` với `.map((row, metadata) -> ...)` thường dễ nhìn thấy hơn.

Một cách khác là repository trả `Flux<CustomerOrderRow>` phẳng rồi service nhóm thành `CustomerWithOrders`. Không nên kỳ vọng một derived query method tự suy ra join nhiều bảng chỉ từ tên property; query derivation phù hợp với điều kiện trên entity mapping, còn join tùy chỉnh thường cần SQL tường minh.

## 11. `R2dbcEntityTemplate` và quan hệ aggregate

Spring Data Relational mô hình hóa quan hệ theo aggregate, với aggregate root và các đối tượng thuộc aggregate. Annotation như `@MappedCollection` có thể mô tả một số quan hệ thuộc aggregate để Spring Data lưu/đọc theo mapping được hỗ trợ.

Ví dụ mô hình một aggregate có danh sách dòng hàng:

```java
@Table("purchase_order")
public class PurchaseOrder {

    @Id
    private Long id;

    private String orderNumber;

    @MappedCollection(idColumn = "order_id")
    private List<PurchaseOrderLine> lines;
}
```

`@MappedCollection` mô tả các phần tử thuộc aggregate và cột tham chiếu tới root. Đây là mapping aggregate của Spring Data Relational, không phải một cơ chế lazy relationship/fetch join giống JPA. Khi cần một DTO join tùy chỉnh, nhiều bảng độc lập, projection báo cáo hoặc điều khiển chính xác SQL, `DatabaseClient`/`@Query` vẫn là lựa chọn phù hợp.

Không nên đặt `@MappedCollection` chỉ vì muốn join tùy ý. Hãy dùng nó khi mô hình dữ liệu thực sự thể hiện aggregate root và các phần tử thuộc aggregate theo quy tắc Spring Data Relational.

## 12. Tránh N+1 query khi ghép dữ liệu

Một cách dễ viết nhưng tốn kém là lấy danh sách customer rồi với mỗi customer lại gọi repository để lấy order:

```java
return customerRepository.findAll()
        .flatMap(customer -> orderRepository.findByCustomerId(customer.getId())
                .collectList()
                .map(orders -> new CustomerWithOrders(
                        customer.getId(),
                        customer.getName(),
                        customer.getEmail(),
                        orders
                )));
```

Nếu có N customer, code có thể tạo một truy vấn đọc customer và N truy vấn đọc order. Đây là vấn đề N+1 query. Với số lượng lớn, số round-trip tăng và latency bị cộng dồn.

### Cách 1: Join trong một truy vấn

Dùng `LEFT JOIN` để lấy customer và order trong cùng một result set, sau đó group bằng ID như các ví dụ trước. Cách này giảm số round-trip nhưng có thể lặp dữ liệu cha trên mỗi hàng con.

### Cách 2: Hai truy vấn theo batch

Nếu không muốn join tạo quá nhiều hàng lặp, có thể:

1. Lấy một tập customer (thường là một trang).
2. Lấy toàn bộ order có `customer_id` thuộc tập ID đó bằng một truy vấn `IN`.
3. Group order theo `customer_id` trong Java.
4. Ghép danh sách order vào từng customer.

Ví dụ truy vấn thứ hai:

```java
Flux<Order> findByCustomerIdIn(Collection<Long> customerIds);
```

Service có thể thu thập ID của trang customer, gọi một truy vấn batch và group kết quả thành `Map<Long, List<Order>>`. Cách này thường có số round-trip cố định theo số loại quan hệ thay vì một truy vấn cho từng customer.

Nếu danh sách ID lớn, cần lưu ý giới hạn số bind parameter của database/driver. Có thể chia thành các batch nhỏ hoặc dùng cơ chế array/table parameter đặc thù của database.

### Cách 3: Giữ N+1 khi tập dữ liệu thực sự nhỏ

Với một vài customer đã biết và số lượng nhỏ, N+1 có thể đủ đơn giản và chấp nhận được. Nếu dùng `flatMap` song song, cần giới hạn concurrency để không tạo quá nhiều truy vấn đồng thời. Không nên mặc định tăng concurrency sẽ làm truy vấn nhanh hơn; nó có thể gây áp lực lên connection pool và database.

## 13. Phân trang khi join one-to-many

Phân trang trực tiếp trên kết quả join one-to-many có thể làm sai ý nghĩa trang. Ví dụ một customer có 10 order sẽ tạo 10 hàng join. Nếu đặt `LIMIT 10`, database có thể trả 10 hàng của cùng một customer thay vì 10 customer.

Nếu mục tiêu là phân trang customer, hãy phân trang tập root trước rồi mới lấy child:

```sql
SELECT c.id, c.name, c.email
FROM customer c
WHERE c.status = :status
ORDER BY c.id
LIMIT :pageSize OFFSET :offset;
```

Sau đó lấy order cho các customer ID của trang:

```sql
SELECT o.id, o.customer_id, o.order_number, o.total_amount
FROM orders o
WHERE o.customer_id IN (:customerIds)
ORDER BY o.customer_id, o.id;
```

`IN (:customerIds)` là cách viết minh họa ở tầng query API; cách mở rộng collection thành tham số SQL phụ thuộc `DatabaseClient`, Spring Data và driver. Khi dùng derived repository method như `findByCustomerIdIn`, framework xử lý collection theo query derivation được hỗ trợ.

Ghép các order vào customer trong bộ nhớ theo `customer_id`. Tổng số customer cho pagination cần đếm ở tập root:

```sql
SELECT COUNT(*)
FROM customer c
WHERE c.status = :status;
```

Nếu đếm trên join one-to-many, cần dùng `COUNT(DISTINCT c.id)` để tránh đếm một customer nhiều lần. Cần giữ nhất quán thứ tự và điều kiện lọc giữa truy vấn trang root, truy vấn child và truy vấn count.

Nếu dữ liệu thay đổi giữa hai truy vấn, trang root và child có thể phản ánh hai thời điểm khác nhau. Khi yêu cầu nhất quán snapshot, cân nhắc thực hiện hai truy vấn trong cùng transaction với isolation level phù hợp với database.

## 14. Null, kiểu dữ liệu và mapping cột trong join

Kết quả join có thể chứa SQL NULL ngay cả khi cột gốc được khai báo `NOT NULL`, vì outer join tạo giá trị null cho phía không có hàng khớp. Do đó:

- Dùng wrapper như `Long`, `Integer`, `Boolean` cho cột có thể null; không dùng primitive nếu cần giữ SQL NULL.
- Kiểm tra child primary key trước khi tạo object con.
- Đọc kiểu Java tương thích với codec driver và kiểu SQL.
- Đặt alias duy nhất cho các cột trùng tên.
- Không giả định thứ tự cột trong `SELECT *` ổn định khi schema thay đổi.

Ví dụ một hàng join có `order_id = null` nhưng `customer_id` luôn có giá trị. Mapper vẫn tạo `CustomerOrderRow`, còn bước group chỉ tạo order khi `orderId` khác null.

Nếu SQL có phép `COALESCE`, `CASE`, `COUNT` hoặc phép tính, kiểu trả về có thể khác kiểu cột gốc. Hãy kiểm tra kiểu thực tế trong `RowMetadata`/driver và dùng kiểu Java phù hợp.

## 15. Mapping join với `Row` và `RowMetadata`

Trong `DatabaseClient`, callback mapping nhận `Row` và `RowMetadata`:

```java
.map((row, metadata) -> {
    Long customerId = row.get("customer_id", Long.class);
    String customerName = row.get("customer_name", String.class);
    Long orderId = row.get("order_id", Long.class);

    return new CustomerOrderRow(
            customerId,
            customerName,
            row.get("customer_email", String.class),
            orderId,
            row.get("order_number", String.class),
            row.get("order_total", BigDecimal.class)
    );
})
```

`RowMetadata` cung cấp thông tin về các cột của result set, hữu ích khi cần mapping động hoặc kiểm tra tên/kiểu cột. Với DTO cố định, đọc cột theo alias tường minh thường dễ bảo trì hơn.

Không giữ `Row` để dùng sau callback mapping. Hãy chuyển dữ liệu cần thiết thành DTO/value object trong phạm vi mapping; vòng đời `Row` thuộc quá trình tiêu thụ result của driver.

## 16. Dùng JSON aggregation khi database hỗ trợ

Một số database cung cấp hàm aggregate JSON để biến nhiều hàng con thành một JSON array ngay trong SQL. Ví dụ PostgreSQL có `json_agg`/`jsonb_agg` và `json_build_object`/`jsonb_build_object`:

```sql
SELECT
    c.id,
    c.name,
    COALESCE(
        jsonb_agg(
            jsonb_build_object(
                'id', o.id,
                'number', o.order_number,
                'total', o.total_amount
            )
        ) FILTER (WHERE o.id IS NOT NULL),
        '[]'::jsonb
    ) AS orders_json
FROM customer c
LEFT JOIN orders o ON o.customer_id = c.id
GROUP BY c.id, c.name
ORDER BY c.id;
```

Truy vấn này trả một hàng cho mỗi customer, trong đó `orders_json` là JSON array. `FILTER (WHERE o.id IS NOT NULL)` tránh tạo phần tử JSON giả chứa các field null do outer join. `COALESCE` trả array rỗng khi không có order.

Ở ứng dụng, có thể đọc cột JSON qua kiểu mà driver hỗ trợ, ví dụ `Json` của PostgreSQL R2DBC driver, rồi dùng Jackson chuyển thành `List<OrderView>`. Cách này giảm việc group nhiều hàng trong Java nhưng tăng phụ thuộc vào hàm JSON riêng của database và yêu cầu converter/codec phù hợp.

Chỉ nên dùng JSON aggregation khi database hỗ trợ, cấu trúc response phù hợp và đội ngũ chấp nhận SQL đặc thù. Với truy vấn cần di chuyển giữa nhiều database, group DTO từ result rows có thể dễ chuyển đổi hơn.

## 17. Transaction khi ghép kết quả từ nhiều truy vấn

Nếu dữ liệu được lấy bằng một join query, database trả các hàng trong một câu lệnh. Nếu dùng nhiều truy vấn (ví dụ trang customer rồi lấy orders), các truy vấn có thể quan sát dữ liệu ở những thời điểm khác nhau.

Khi nghiệp vụ yêu cầu dữ liệu nhất quán, có thể đặt các publisher trong reactive transaction:

```java
@Transactional(readOnly = true)
public Mono<List<CustomerWithOrders>> findPageWithOrders(...) {
    // 1. Đọc trang customer.
    // 2. Lấy customer IDs.
    // 3. Đọc orders theo tập IDs.
    // 4. Group và ghép DTO.
}
```

`readOnly = true` là gợi ý/metadata transaction theo khả năng của transaction manager và driver; không nên xem nó là bảo đảm database sẽ cấm mọi lệnh ghi. Nếu cần snapshot nhất quán qua nhiều câu lệnh, hãy chọn isolation level phù hợp với database. Reactive transaction cần publisher được nối liền và cùng transaction context; tự gọi `subscribe()` riêng sẽ phá vỡ cách phối hợp này.

## 18. Những lỗi thường gặp

| Biểu hiện | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Cột bị đọc nhầm sau join | Nhiều bảng có cột cùng tên như `id` hoặc `name` | Liệt kê cột và đặt alias duy nhất |
| Customer không có order bị mất | Dùng `INNER JOIN` trong khi cần giữ customer | Dùng `LEFT JOIN` |
| Customer không có order bị loại dù đã LEFT JOIN | Điều kiện bảng con đặt trong `WHERE` | Chuyển điều kiện phù hợp vào `ON` |
| Tạo child giả toàn null | Không kiểm tra child ID trước khi tạo object | Kiểm tra khóa chính child khác null |
| Parent xuất hiện nhiều lần | Mỗi hàng join được ánh xạ thành một parent độc lập | Group theo parent ID |
| Order bị lặp nhiều lần khi join thêm line | Join nhiều quan hệ one-to-many tạo row multiplication | Group theo từng cấp và deduplicate bằng child ID |
| Trang chỉ chứa một parent dù page size lớn | LIMIT áp dụng lên hàng join thay vì parent | Phân trang root trước, lấy child theo tập ID |
| Số lượng parent bị đếm dư | `COUNT(*)` trên join one-to-many | Đếm root hoặc dùng `COUNT(DISTINCT root.id)` |
| Nhiều truy vấn chậm dần theo số parent | N+1 query do gọi repository child trong từng parent | Dùng join hoặc batch query `IN` |
| Mapper lỗi kiểu | SQL expression/aggregate trả kiểu khác dự kiến | Kiểm tra RowMetadata và kiểu driver |
| Object đang giữ không phản ánh dữ liệu join/update mới | Entity không được đồng bộ tự động | Tạo DTO mới hoặc đọc lại dữ liệu |

Khi điều tra, hãy xem SQL trước: join type, điều kiện `ON`/`WHERE`, alias và thứ tự. Sau đó kiểm tra số hàng trả về, mapping từng hàng, logic group và cardinality cuối cùng. Phần lớn lỗi dựng cấu trúc lồng nhau xuất phát từ một trong các bước này.

## 19. Quy trình thiết kế truy vấn join

Một cách làm có hệ thống:

1. Xác định cấu trúc đầu ra mong muốn: DTO phẳng, parent-child, thống kê hay JSON document.
2. Xác định quan hệ giữa bảng và cardinality: one-to-one, one-to-many hay many-to-many.
3. Chọn `INNER JOIN` hoặc outer join theo yêu cầu giữ hàng không có quan hệ.
4. Liệt kê cột cần dùng và đặt alias duy nhất.
5. Thêm điều kiện lọc, thứ tự và giới hạn ở đúng cấp dữ liệu.
6. Ánh xạ mỗi hàng sang một DTO phẳng với kiểu nullable phù hợp.
7. Nếu cần cấu trúc lồng nhau, group theo ID ở từng cấp và bỏ qua child null từ outer join.
8. Nếu có nhiều quan hệ one-to-many, kiểm tra row multiplication và deduplicate theo ID child.
9. Nếu cần pagination, phân trang root trước rồi mới lấy child hoặc dùng chiến lược SQL phù hợp.
10. Kiểm thử với dữ liệu có parent không child, một child, nhiều child, child nullable và nhiều cấp quan hệ.
11. Đo số truy vấn và số hàng truyền về để phát hiện N+1 hoặc kết quả join phình lớn.

## 20. Ghi nhớ

- SQL `JOIN` kết hợp bảng và trả result set phẳng; việc dựng object lồng nhau thường do ứng dụng thực hiện sau khi ánh xạ từng hàng.
- R2DBC không có JPA persistence context/lazy relationship loading; hãy chủ động viết join hoặc query batch khi cần dữ liệu liên quan.
- Dùng alias duy nhất cho các cột trùng tên và đọc theo alias trong `Row`.
- `LEFT JOIN` giữ parent không có child; kiểm tra child primary key để tránh tạo object con giả từ các cột NULL.
- Với one-to-many, group theo parent ID để gom child; với nhiều cấp, group theo từng ID và deduplicate child.
- DTO phẳng phù hợp với danh sách/báo cáo; aggregate SQL phù hợp khi chỉ cần thống kê; nested DTO phù hợp với response có cấu trúc cha-con.
- `COUNT(child.id)` thường đúng hơn `COUNT(*)` khi đếm child qua LEFT JOIN; count parent sau join cần `COUNT(DISTINCT parent.id)`.
- Tránh N+1 bằng join hoặc batch query `IN`; giới hạn batch khi danh sách ID lớn.
- Phân trang trên parent trước khi nối child để không cắt một parent thành nhiều trang do các hàng join.
- `@Query`, `DatabaseClient` và `R2dbcEntityTemplate` cho phép chọn mức kiểm soát SQL/mapping phù hợp; `@MappedCollection` mô tả aggregate mapping chứ không phải lazy fetch join.
- Kiểm thử với database/driver thật để xác nhận alias, kiểu dữ liệu, null, cardinality và hiệu năng.

Khi cần ghép dữ liệu từ nhiều bảng trong Spring Data R2DBC, hãy quyết định trước cấu trúc kết quả rồi thiết kế SQL và bước mapping tương ứng. Database nên làm phần join, lọc và aggregate mà nó xử lý tốt; ứng dụng chịu trách nhiệm nhóm các hàng thành DTO hoặc aggregate có hình dạng đúng với nhu cầu sử dụng.
