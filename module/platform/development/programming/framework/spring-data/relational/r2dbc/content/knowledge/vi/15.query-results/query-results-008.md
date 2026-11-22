# Tổ chức mô hình đọc khi truy vấn không tương ứng với một bảng

## 1. Vì sao cần mô hình đọc riêng?

Trong ứng dụng dùng Spring Data Relational R2DBC, một entity thường đại diện cho dữ liệu được lưu trong một bảng hoặc một phần của aggregate. Các thao tác lưu và cập nhật cần một cấu trúc rõ ràng để Spring Data biết cách ánh xạ thuộc tính Java sang cột SQL.

Nhưng nhiều truy vấn phục vụ màn hình hoặc báo cáo không lấy dữ liệu từ một bảng duy nhất. Một trang chi tiết đơn hàng có thể cần tên khách hàng, ngày đặt, trạng thái, tên sản phẩm, số lượng và tổng tiền. Những dữ liệu đó nằm ở nhiều bảng và được kết hợp bằng JOIN, phép tổng hợp hoặc biểu thức tính toán.

Nếu cố ép kết quả truy vấn này vào một entity của một bảng, mô hình Java sẽ không còn phản ánh đúng cấu trúc dữ liệu. Một số thuộc tính không tồn tại trong bảng, một hàng SQL có thể lặp lại thông tin của cùng một đơn hàng, hoặc một phép tổng hợp không có ý nghĩa để lưu ngược vào entity.

Giải pháp là tổ chức **mô hình đọc (read model)** phù hợp với hình dạng kết quả truy vấn. Mô hình đọc thường là DTO, record hoặc projection chỉ chứa những dữ liệu mà một use case cần hiển thị hoặc xử lý.

Cách tổ chức này giúp tách ba khái niệm:

- **Entity/aggregate:** mô hình dữ liệu dùng để lưu và duy trì quy tắc nghiệp vụ.
- **Query:** câu SQL kết hợp, lọc hoặc tổng hợp dữ liệu theo nhu cầu.
- **Read model:** cấu trúc kết quả được trả về cho màn hình, API hoặc báo cáo.

Trong bài này, các ví dụ dùng Spring Data Relational R2DBC, Reactor và DatabaseClient.

## 2. Entity và read model có mục đích khác nhau

Giả sử hệ thống có các bảng:

~~~sql
CREATE TABLE customers (
    id BIGINT PRIMARY KEY,
    full_name VARCHAR(150) NOT NULL
);

CREATE TABLE orders (
    id BIGINT PRIMARY KEY,
    customer_id BIGINT NOT NULL,
    status VARCHAR(30) NOT NULL,
    created_at TIMESTAMP NOT NULL,
    CONSTRAINT fk_orders_customer
        FOREIGN KEY (customer_id) REFERENCES customers(id)
);

CREATE TABLE order_items (
    id BIGINT PRIMARY KEY,
    order_id BIGINT NOT NULL,
    product_name VARCHAR(200) NOT NULL,
    quantity INTEGER NOT NULL,
    unit_price DECIMAL(12, 2) NOT NULL,
    CONSTRAINT fk_order_items_order
        FOREIGN KEY (order_id) REFERENCES orders(id)
);
~~~

Entity Order có thể chỉ chứa dữ liệu thuộc bảng orders:

~~~java
@Table("orders")
public class Order {
    @Id
    private Long id;

    @Column("customer_id")
    private Long customerId;

    private String status;

    private Instant createdAt;
}
~~~

Entity này phù hợp với các thao tác lưu và cập nhật đơn hàng. Tuy nhiên, API màn hình quản trị có thể cần kết quả như:

- Mã đơn hàng.
- Tên khách hàng.
- Trạng thái đơn hàng.
- Tổng số dòng sản phẩm.
- Tổng số lượng sản phẩm.
- Tổng giá trị đơn hàng.

Không phải tất cả các thuộc tính trên đều là cột của bảng orders. Một số được lấy từ customers hoặc order_items; một số là kết quả COUNT, SUM.

Hãy tạo một read model riêng:

~~~java
public record OrderSummary(
    Long orderId,
    String customerName,
    String status,
    Instant createdAt,
    Long lineCount,
    Long totalQuantity,
    BigDecimal totalAmount
) {}
~~~

OrderSummary mô tả kết quả của một truy vấn cụ thể. Nó không cần có @Table hoặc @Id nếu chỉ dùng làm đối tượng đọc. Không nên gọi repository.save(orderSummary) như thể đây là entity có thể ghi xuống một bảng.

Một nguyên tắc hữu ích: **entity mô tả dữ liệu được quản lý trong mô hình lưu trữ; read model mô tả dữ liệu mà một thao tác đọc cần nhận được.**

## 3. Khi nào nên tạo read model?

Read model riêng hữu ích khi truy vấn có một hoặc nhiều đặc điểm sau:

- Kết hợp dữ liệu từ nhiều bảng bằng JOIN.
- Tính tổng, số lượng, trung bình, min/max hoặc các chỉ số khác.
- Chỉ lấy một tập con cột để hiển thị.
- Trả về tên hoặc nhãn đã được kết hợp từ nhiều thuộc tính.
- Có dữ liệu phân nhóm, thống kê hoặc báo cáo.
- Kết quả có cấu trúc khác với entity được lưu.
- Cần tránh tải toàn bộ aggregate chỉ để hiển thị một màn hình.
- Một hàng kết quả chứa dữ liệu tổng hợp từ nhiều bản ghi nguồn.

Ví dụ, trang dashboard có thể cần số đơn hàng theo trạng thái:

~~~sql
SELECT status, COUNT(*) AS order_count
FROM orders
GROUP BY status;
~~~

Kết quả không tương ứng với entity Order. Mỗi hàng đại diện cho một nhóm trạng thái chứ không phải một đơn hàng. Read model phù hợp:

~~~java
public record OrderStatusCount(
    String status,
    Long orderCount
) {}
~~~

Tương tự, truy vấn doanh thu theo ngày có thể trả về:

~~~java
public record DailyRevenue(
    LocalDate orderDate,
    BigDecimal revenue
) {}
~~~

Không nên tạo entity giả cho mọi hình dạng kết quả SQL. Hãy tạo kiểu đọc nhỏ, rõ mục đích và chỉ chứa các trường cần thiết.

## 4. Các dạng mô hình đọc thường gặp

### 4.1. DTO class

DTO (Data Transfer Object) là lớp mang dữ liệu giữa tầng truy cập dữ liệu và tầng ứng dụng/API.

~~~java
public class CustomerOrderView {
    private final Long orderId;
    private final String customerName;
    private final String status;

    public CustomerOrderView(
            Long orderId,
            String customerName,
            String status) {
        this.orderId = orderId;
        this.customerName = customerName;
        this.status = status;
    }

    public Long getOrderId() {
        return orderId;
    }

    public String getCustomerName() {
        return customerName;
    }

    public String getStatus() {
        return status;
    }
}
~~~

DTO class hữu ích khi cần constructor, validation hoặc logic trình bày đơn giản. Nếu dữ liệu chỉ cần mang các giá trị bất biến, Java record thường ngắn gọn hơn.

### 4.2. Java record

Record phù hợp với read model vì các thành phần được khai báo rõ ràng, constructor canonical được tạo tự động và dữ liệu có tính bất biến theo thiết kế.

~~~java
public record CustomerOrderView(
    Long orderId,
    String customerName,
    String status
) {}
~~~

Record không phải entity chỉ vì nó chứa các trường giống entity. Nó có thể được tạo trực tiếp từ kết quả SQL và trả về từ service.

### 4.3. Projection interface

Projection interface mô tả tập thuộc tính cần đọc thông qua getter:

~~~java
public interface CustomerNameView {
    Long getId();
    String getFullName();
}
~~~

Trong các repository method và cơ chế projection được Spring Data Relational hỗ trợ, projection giúp giới hạn dữ liệu theo các thuộc tính cần thiết. Với interface projection, Spring Data có thể tạo proxy để cung cấp các getter dựa trên kết quả truy vấn.

Projection phù hợp với các trường hợp đơn giản, nhất là khi dữ liệu đọc vẫn bám sát thuộc tính của entity. Tuy nhiên, với JOIN phức tạp, biểu thức tính toán, alias đặc biệt hoặc kết quả tổng hợp, DTO/record tường minh thường dễ kiểm soát hơn.

Khả năng áp dụng interface projection và cách ánh xạ kết quả tùy thuộc loại query và phiên bản Spring Data. Hãy xác nhận method signature và tài liệu của phiên bản đang dùng. Đừng giả định mọi projection của Spring Data JPA đều có hành vi tương tự trong R2DBC.

### 4.4. Read model có cấu trúc lồng nhau

Một API có thể cần dữ liệu dạng:

~~~text
OrderDetail
  orderId
  customer
    customerId
    customerName
  items
    - productName
      quantity
      unitPrice
  totalAmount
~~~

Có thể mô hình hóa bằng các record lồng nhau:

~~~java
public record CustomerSummary(
    Long customerId,
    String customerName
) {}

public record OrderItemView(
    String productName,
    Integer quantity,
    BigDecimal unitPrice
) {}

public record OrderDetailView(
    Long orderId,
    String status,
    CustomerSummary customer,
    List<OrderItemView> items,
    BigDecimal totalAmount
) {}
~~~

Một câu JOIN phẳng thường trả về nhiều hàng cho một đơn hàng có nhiều sản phẩm. Database không tự động biến các hàng phẳng đó thành một object graph lồng nhau theo ý muốn. Ứng dụng cần nhóm các hàng theo orderId rồi tạo danh sách items, hoặc dùng truy vấn tổng hợp/JSON phù hợp với database.

Đây là điểm khác biệt giữa mapping một entity và tổ chức một read model tổng hợp.

## 5. Chọn công cụ truy vấn phù hợp

Spring Data R2DBC cung cấp nhiều cách thực hiện truy vấn. Không phải mọi truy vấn đều cần cùng một abstraction.

| Công cụ | Phù hợp khi | Kết quả thường gặp |
|---|---|---|
| Derived query trong repository | Điều kiện lọc đơn giản trên entity | Entity hoặc kiểu projection được hỗ trợ |
| @Query trên repository | SQL tĩnh, có tham số, truy vấn tương đối gọn | Entity hoặc DTO/projection phù hợp với mapping |
| R2dbcEntityTemplate | Truy vấn dựa trên mapping metadata, Criteria và thao tác entity | Entity và các kiểu được API hỗ trợ |
| DatabaseClient | JOIN, aggregate, alias, SQL đặc thù hoặc cần kiểm soát Row mapping | DTO/record hoặc kiểu kết quả tùy chỉnh |
| Database view | Truy vấn dùng lại nhiều nơi, schema đọc ổn định | Read model từ view |
| Materialized view | Báo cáo nặng, có thể chấp nhận dữ liệu được làm mới theo chu kỳ | Read model đã được tính trước |

Hãy bắt đầu từ độ phức tạp của truy vấn và hình dạng kết quả. Repository method rất phù hợp cho CRUD và truy vấn entity thông thường. Khi kết quả là một tập dữ liệu tổng hợp không tương ứng với entity, DatabaseClient thường cho phép kiểm soát SQL và ánh xạ rõ ràng.

## 6. Dùng @Query để trả về kiểu đọc

Với câu SQL tương đối tĩnh, repository có thể khai báo @Query và trả về kiểu kết quả phù hợp.

Ví dụ:

~~~java
public interface OrderRepository
        extends ReactiveCrudRepository<Order, Long> {

    @Query("""
        SELECT
            o.id AS order_id,
            c.full_name AS customer_name,
            o.status AS status
        FROM orders o
        JOIN customers c ON c.id = o.customer_id
        WHERE o.id = :orderId
        """)
    Mono<OrderCustomerRow> findOrderCustomer(
        @Param("orderId") Long orderId
    );
}
~~~

Kiểu kết quả:

~~~java
public record OrderCustomerRow(
    Long orderId,
    String customerName,
    String status
) {}
~~~

Đây là cách khai báo có ý nghĩa khi mapping infrastructure của phiên bản Spring Data đang dùng hỗ trợ DTO projection cho query đó. Tên alias cần được đặt sao cho mapping có thể liên hệ với property/constructor parameter. Với các kiểu projection hoặc constructor mapping phức tạp, hãy kiểm tra tài liệu và thử trên đúng driver/database.

Nếu query có nhiều phép tổng hợp, kiểu dữ liệu đặc thù hoặc cần xử lý null tỉ mỉ, ánh xạ tường minh bằng DatabaseClient giúp nhìn thấy rõ từng cột và kiểu Java.

## 7. Dùng DatabaseClient để ánh xạ JOIN thành DTO

### 7.1. Câu SQL trả về một hàng cho mỗi đơn hàng

Ví dụ cần màn hình tổng hợp đơn hàng, gồm tên khách hàng và tổng giá trị:

~~~sql
SELECT
    o.id AS order_id,
    c.full_name AS customer_name,
    o.status AS status,
    o.created_at AS created_at,
    COUNT(oi.id) AS line_count,
    COALESCE(SUM(oi.quantity), 0) AS total_quantity,
    COALESCE(SUM(oi.quantity * oi.unit_price), 0) AS total_amount
FROM orders o
JOIN customers c
    ON c.id = o.customer_id
LEFT JOIN order_items oi
    ON oi.order_id = o.id
WHERE o.id = :orderId
GROUP BY
    o.id,
    c.full_name,
    o.status,
    o.created_at
~~~

Ý nghĩa:

- JOIN customers để lấy tên khách hàng.
- LEFT JOIN order_items để vẫn giữ đơn hàng chưa có dòng chi tiết.
- COUNT đếm số dòng sản phẩm.
- SUM tính tổng số lượng và tổng tiền.
- COALESCE chuyển kết quả tổng hợp NULL thành 0 khi không có dòng chi tiết.
- GROUP BY tạo một hàng kết quả cho mỗi đơn hàng.

Read model:

~~~java
public record OrderSummary(
    Long orderId,
    String customerName,
    String status,
    LocalDateTime createdAt,
    Long lineCount,
    Long totalQuantity,
    BigDecimal totalAmount
) {}
~~~

Kiểu createdAt cần phù hợp với kiểu timestamp và driver thực tế. Ví dụ này dùng LocalDateTime để minh họa; nếu schema lưu thời điểm có múi giờ, hãy chọn kiểu Java và quy ước thời gian tương ứng.

### 7.2. Ánh xạ Row bằng DatabaseClient

~~~java
@Repository
public class OrderReadRepository {

    private final DatabaseClient databaseClient;

    public OrderReadRepository(DatabaseClient databaseClient) {
        this.databaseClient = databaseClient;
    }

    public Mono<OrderSummary> findSummary(Long orderId) {
        return databaseClient.sql("""
                SELECT
                    o.id AS order_id,
                    c.full_name AS customer_name,
                    o.status AS status,
                    o.created_at AS created_at,
                    COUNT(oi.id) AS line_count,
                    COALESCE(SUM(oi.quantity), 0) AS total_quantity,
                    COALESCE(
                        SUM(oi.quantity * oi.unit_price),
                        0
                    ) AS total_amount
                FROM orders o
                JOIN customers c
                    ON c.id = o.customer_id
                LEFT JOIN order_items oi
                    ON oi.order_id = o.id
                WHERE o.id = :orderId
                GROUP BY
                    o.id,
                    c.full_name,
                    o.status,
                    o.created_at
                """)
            .bind("orderId", orderId)
            .map((row, metadata) -> new OrderSummary(
                row.get("order_id", Long.class),
                row.get("customer_name", String.class),
                row.get("status", String.class),
                row.get("created_at", LocalDateTime.class),
                row.get("line_count", Long.class),
                row.get("total_quantity", Long.class),
                row.get("total_amount", BigDecimal.class)
            ))
            .one();
    }
}
~~~

DatabaseClient thực thi câu SQL khi publisher được subscribe. .bind("orderId", orderId) liên kết giá trị với placeholder. .map() nhận Row và metadata để tạo OrderSummary. .one() trả về Mono vì truy vấn theo một ID và kết quả mong đợi tối đa một hàng.

Cần kiểm tra kiểu dữ liệu mà driver trả về cho các biểu thức tổng hợp. Ví dụ COUNT thường trả về kiểu số nguyên lớn, còn SUM trên DECIMAL thường trả về BigDecimal, nhưng chi tiết phụ thuộc hệ quản trị và driver. Nếu kiểu không khớp, hãy chuyển đổi có kiểm soát hoặc dùng CAST trong SQL.

### 7.3. Alias là hợp đồng giữa SQL và read model

Tên alias như order_id, customer_name, total_amount là tên cột kết quả mà Row mapper sử dụng. Chúng không nhất thiết giống tên cột gốc.

Hãy đặt alias rõ ràng:

| Biểu thức SQL | Alias | Property trong read model |
|---|---|---|
| o.id | order_id | orderId |
| c.full_name | customer_name | customerName |
| COUNT(oi.id) | line_count | lineCount |
| SUM(...) | total_amount | totalAmount |

Khi map thủ công, chuỗi trong row.get() phải khớp alias mà câu SQL trả về. Nếu đổi alias trong SQL mà quên sửa mapper, lỗi có thể chỉ xuất hiện lúc chạy.

Một quy ước tốt là dùng snake_case cho alias SQL và camelCase cho property Java. Việc chuyển đổi giữa hai dạng nên được thực hiện có chủ đích trong mapping, không dựa vào suy đoán.

## 8. JOIN một-nhiều và việc gom hàng thành cấu trúc lồng nhau

### 8.1. Vì sao JOIN tạo ra nhiều hàng?

Giả sử một đơn hàng có ba sản phẩm. Query:

~~~sql
SELECT
    o.id AS order_id,
    o.status,
    oi.id AS item_id,
    oi.product_name,
    oi.quantity,
    oi.unit_price
FROM orders o
LEFT JOIN order_items oi
    ON oi.order_id = o.id
WHERE o.id = :orderId
ORDER BY oi.id
~~~

có thể trả về ba hàng. Mỗi hàng lặp lại order_id và status, nhưng có item_id và dữ liệu sản phẩm khác nhau.

Nếu map trực tiếp mỗi hàng thành OrderDetailView có List<OrderItemView>, bạn sẽ nhận ba object đơn hàng riêng biệt thay vì một đơn hàng chứa ba item. Mapping từng Row không tự động gom các hàng thành một aggregate lồng nhau.

### 8.2. Tách kiểu hàng phẳng và kiểu kết quả cuối

Tạo một kiểu nội bộ cho mỗi hàng:

~~~java
public record OrderItemRow(
    Long orderId,
    String status,
    Long itemId,
    String productName,
    Integer quantity,
    BigDecimal unitPrice
) {}
~~~

Sau đó tạo read model cuối:

~~~java
public record OrderItemView(
    String productName,
    Integer quantity,
    BigDecimal unitPrice
) {}

public record OrderDetailView(
    Long orderId,
    String status,
    List<OrderItemView> items
) {}
~~~

Query trả về Flux<OrderItemRow>. Tầng đọc gom các hàng theo orderId rồi dựng một OrderDetailView. Việc tách hai kiểu giúp phân biệt dữ liệu trung gian phẳng với cấu trúc mà API cần trả.

### 8.3. Gom hàng trong reactive pipeline

Với một đơn hàng cụ thể, có thể thu thập các hàng của đơn đó rồi tạo DTO:

~~~java
public Mono<OrderDetailView> findDetail(Long orderId) {
    return loadOrderItemRows(orderId)
        .collectList()
        .map(rows -> {
            if (rows.isEmpty()) {
                return null;
            }

            OrderItemRow first = rows.get(0);

            List<OrderItemView> items = rows.stream()
                .filter(row -> row.itemId() != null)
                .map(row -> new OrderItemView(
                    row.productName(),
                    row.quantity(),
                    row.unitPrice()
                ))
                .toList();

            return new OrderDetailView(
                first.orderId(),
                first.status(),
                items
            );
        })
        .flatMap(detail -> detail == null
            ? Mono.empty()
            : Mono.just(detail));
}
~~~

Đây là ví dụ minh họa việc gom hàng cho một orderId. Trong code thực tế, cần quyết định rõ trường hợp không có đơn hàng và tránh dùng null làm tín hiệu nội bộ nếu có thể. Có thể trả Mono.empty() hoặc phát lỗi nghiệp vụ ngay từ query/flow phù hợp.

Vì một đơn hàng có thể có nhiều dòng, collectList() giữ toàn bộ các dòng trong bộ nhớ. Cách này hợp lý khi số dòng bị giới hạn theo nghiệp vụ. Với tập kết quả lớn, hãy dùng phân trang, giới hạn hoặc cách tổng hợp phù hợp.

### 8.4. Gom nhiều đơn hàng trong một truy vấn

Nếu đọc nhiều đơn hàng và mỗi đơn hàng có nhiều item, có thể gom hàng theo orderId bằng một map có thứ tự. Ví dụ dưới đây minh họa cấu trúc xử lý:

~~~java
return loadRowsForCustomer(customerId)
    .collect(
        LinkedHashMap<Long, List<OrderItemRow>>::new,
        (grouped, row) -> grouped
            .computeIfAbsent(row.orderId(), key -> new ArrayList<>())
            .add(row)
    )
    .flatMapMany(grouped -> Flux.fromIterable(grouped.values()))
    .map(this::toOrderDetail);
~~~

Đoạn code trên là phác thảo cách nhóm theo khóa; trong Java thực tế, hãy khai báo Supplier<Map<Long, List<OrderItemRow>>> hoặc dùng lambda khởi tạo map đúng cú pháp, rồi triển khai toOrderDetail để tạo DTO. Cần xác định cách xử lý hàng có item_id NULL do LEFT JOIN.

Một lựa chọn khác là tách truy vấn cha và truy vấn con theo batch, nhưng cần tránh N+1: không chạy thêm một truy vấn riêng cho từng đơn hàng. Hãy tải các item cho một tập orderId trong một truy vấn rồi nhóm trong bộ nhớ.

## 9. Phân biệt LEFT JOIN, NULL và giá trị mặc định

Với LEFT JOIN, cột của bảng bên phải có thể là NULL khi không có bản ghi phù hợp.

Ví dụ:

~~~sql
SELECT
    o.id AS order_id,
    c.full_name AS customer_name
FROM orders o
LEFT JOIN customers c
    ON c.id = o.customer_id
~~~

Nếu không có khách hàng phù hợp, customer_name có thể là NULL. Read model cần cho phép trường đó null hoặc query cần định nghĩa fallback:

~~~sql
COALESCE(c.full_name, 'Unknown customer') AS customer_name
~~~

Chỉ dùng COALESCE khi giá trị thay thế có ý nghĩa nghiệp vụ. Không biến NULL thành chuỗi rỗng hoặc số 0 một cách tùy tiện vì có thể che giấu dữ liệu thiếu.

Khi đọc Row:

~~~java
String customerName = row.get("customer_name", String.class);
~~~

giá trị có thể là null. Nếu dùng kiểu nguyên thủy như long hoặc int trong DTO, không thể biểu diễn null. Với dữ liệu có thể thiếu, hãy dùng Long, Integer hoặc kiểu tham chiếu phù hợp.

Một số điểm cần chú ý:

- COUNT trên tập rỗng trả về 0.
- SUM có thể trả về NULL nếu không có hàng phù hợp.
- LEFT JOIN có thể tạo một hàng với các cột bên phải là NULL.
- COUNT(*) đếm cả hàng kết quả do LEFT JOIN tạo ra; COUNT(oi.id) chỉ đếm các item có ID.
- COALESCE chỉ nên dùng khi 0 hoặc giá trị thay thế thực sự đúng với ý nghĩa dữ liệu.

## 10. Đọc dữ liệu tổng hợp và kiểu số

Các biểu thức aggregate thường có kiểu trả về khác kiểu cột đầu vào. Hãy xác định kiểu theo database và driver.

Ví dụ:

~~~sql
SELECT
    COUNT(*) AS order_count,
    SUM(total_amount) AS revenue,
    AVG(total_amount) AS average_amount
FROM orders
WHERE created_at >= :fromTime
~~~

Read model:

~~~java
public record RevenueStatistics(
    Long orderCount,
    BigDecimal revenue,
    BigDecimal averageAmount
) {}
~~~

Nếu không có hàng phù hợp:

- COUNT(*) vẫn thường trả về 0.
- SUM và AVG có thể trả về NULL.
- Có thể dùng COALESCE nếu nghiệp vụ muốn biểu diễn không có dữ liệu bằng 0.

~~~sql
SELECT
    COUNT(*) AS order_count,
    COALESCE(SUM(total_amount), 0) AS revenue,
    COALESCE(AVG(total_amount), 0) AS average_amount
FROM orders
WHERE created_at >= :fromTime
~~~

Cần chú ý độ chính xác và scale của DECIMAL. Không chuyển tổng tiền sang double chỉ để tiện tính toán. Hãy giữ BigDecimal cho số tiền và quy định scale/rounding theo nghiệp vụ.

## 11. R2dbcEntityTemplate và DatabaseClient trong mô hình đọc

### 11.1. R2dbcEntityTemplate

R2dbcEntityTemplate làm việc với entity mapping metadata và cung cấp API thao tác dữ liệu theo kiểu Spring Data Relational. Nó phù hợp khi truy vấn vẫn gắn với entity, cần Criteria, Query, update/delete theo mapping hoặc muốn dùng mapping context.

Ví dụ khái niệm:

~~~java
Query query = Query.query(
    Criteria.where("status").is("PAID")
);

return r2dbcEntityTemplate.select(query, Order.class);
~~~

API cụ thể có thể khác theo phiên bản Spring Data. Hãy đối chiếu chữ ký phương thức của phiên bản đang dùng.

Nếu kết quả cần JOIN nhiều bảng, GROUP BY hoặc cấu trúc DTO không phải entity, DatabaseClient thường dễ kiểm soát hơn vì bạn viết SQL và Row mapping tường minh.

### 11.2. DatabaseClient

DatabaseClient cung cấp API reactive ở mức SQL. Bạn kiểm soát:

- Câu SELECT và JOIN.
- Alias của cột kết quả.
- Bind parameter.
- Cách map Row sang DTO.
- Kiểu trả về Mono hoặc Flux.

Ví dụ:

~~~java
return databaseClient.sql("""
        SELECT id AS customer_id, full_name
        FROM customers
        WHERE active = :active
        """)
    .bind("active", true)
    .map((row, metadata) -> new CustomerNameViewImpl(
        row.get("customer_id", Long.class),
        row.get("full_name", String.class)
    ))
    .all();
~~~

DatabaseClient phù hợp với read model tùy chỉnh vì code mapping thể hiện trực tiếp cấu trúc kết quả. Hãy dùng bind cho mọi giá trị đầu vào, không nối chuỗi dữ liệu vào SQL.

## 12. Dùng database view hoặc materialized view

Khi một truy vấn đọc phức tạp được nhiều màn hình hoặc nhiều service dùng lại, có thể đưa logic vào database view.

Ví dụ:

~~~sql
CREATE VIEW order_summary_view AS
SELECT
    o.id AS order_id,
    c.full_name AS customer_name,
    o.status,
    o.created_at,
    COALESCE(SUM(oi.quantity * oi.unit_price), 0) AS total_amount
FROM orders o
JOIN customers c
    ON c.id = o.customer_id
LEFT JOIN order_items oi
    ON oi.order_id = o.id
GROUP BY
    o.id,
    c.full_name,
    o.status,
    o.created_at;
~~~

Ứng dụng có thể đọc view bằng SQL:

~~~sql
SELECT order_id, customer_name, status, created_at, total_amount
FROM order_summary_view
WHERE order_id = :orderId
~~~

View thường biểu diễn truy vấn được định nghĩa; dữ liệu được tính khi view được truy vấn, tùy database và cách tối ưu. Materialized view lưu kết quả đã tính và cần được refresh theo cơ chế của hệ quản trị.

So sánh:

| Cách | Đặc điểm | Cần cân nhắc |
|---|---|---|
| Query trực tiếp trong ứng dụng | Logic SQL nằm gần use case | Có thể lặp lại query nếu nhiều nơi dùng |
| Database view | Đặt logic đọc dùng chung trong schema | Phải quản lý version và quyền truy cập view |
| Materialized view | Đọc nhanh từ dữ liệu đã tính trước | Dữ liệu có thể cũ cho đến lần refresh |
| Bảng read model riêng | Dữ liệu được cập nhật theo cơ chế ứng dụng/event | Phức tạp hơn, cần xử lý đồng bộ và tính nhất quán |

Không nên tạo materialized view chỉ vì một truy vấn JOIN. Hãy dựa vào tần suất đọc, chi phí tính toán, yêu cầu độ mới của dữ liệu và khả năng vận hành.

## 13. Read model và CQRS

CQRS (Command Query Responsibility Segregation) là cách tổ chức tách mô hình xử lý lệnh ghi khỏi mô hình truy vấn đọc. Trong hệ thống đơn giản, việc dùng một DTO cho truy vấn JOIN không đồng nghĩa toàn bộ ứng dụng đã áp dụng CQRS.

Có thể phân biệt các mức:

- **Read DTO cục bộ:** một query method trả về DTO phục vụ một use case.
- **Read repository riêng:** một lớp chỉ tập trung truy vấn và tạo read model.
- **Database view/read schema:** nhiều use case dùng chung một cấu trúc đọc.
- **CQRS đầy đủ:** command model và query model được tổ chức độc lập, có thể có cơ chế đồng bộ riêng.

Không cần áp dụng CQRS đầy đủ chỉ để xử lý một màn hình cần JOIN. Hãy bắt đầu bằng DTO và read repository; chỉ tách hạ tầng đọc riêng khi có lý do về hiệu năng, khả năng mở rộng hoặc tổ chức nghiệp vụ.

Nếu read model được cập nhật bất đồng bộ từ event hoặc projection worker, cần xác định độ trễ nhất quán. Người dùng có thể vừa cập nhật đơn hàng nhưng dashboard chưa phản ánh ngay. Đây là đặc điểm của kiến trúc eventual consistency, cần được xử lý trong thiết kế trải nghiệm và nghiệp vụ.

## 14. Phân trang và thứ tự trong truy vấn đọc tổng hợp

Read model thường phục vụ danh sách và báo cáo. Khi query có JOIN một-nhiều, phân trang trực tiếp trên các hàng JOIN có thể làm một đơn hàng bị chia qua nhiều trang hoặc bị lặp.

Ví dụ, nếu mỗi đơn hàng có nhiều item, LIMIT 20 trên kết quả JOIN có nghĩa là giới hạn 20 hàng kết hợp, không phải 20 đơn hàng.

Một cách phổ biến là phân trang danh sách ID của bảng cha trước, sau đó tải dữ liệu cần thiết cho tập ID đó:

~~~sql
SELECT
    o.id,
    o.created_at
FROM orders o
WHERE o.customer_id = :customerId
ORDER BY o.created_at DESC, o.id DESC
LIMIT :limit OFFSET :offset
~~~

Sau đó tải các dữ liệu liên quan cho tập orderId trong một truy vấn khác hoặc một truy vấn tổng hợp phù hợp.

Luôn thêm tiêu chí sắp xếp ổn định, ví dụ created_at cùng id làm tie-breaker. Nếu chỉ sort theo thời gian và nhiều hàng có cùng timestamp, thứ tự giữa các trang có thể không ổn định.

Với dữ liệu lớn, cân nhắc keyset pagination:

~~~sql
SELECT id, created_at, status
FROM orders
WHERE customer_id = :customerId
  AND (
      created_at < :lastCreatedAt
      OR (created_at = :lastCreatedAt AND id < :lastId)
  )
ORDER BY created_at DESC, id DESC
LIMIT :limit
~~~

Keyset pagination cần lưu cursor của hàng cuối trang trước và có index phù hợp. Nó tránh chi phí offset lớn và giảm vấn đề dịch chuyển trang khi dữ liệu mới được thêm, nhưng không cung cấp số trang tổng như offset pagination.

## 15. Tránh N+1 khi tạo read model

Một cách làm kém hiệu quả là đọc danh sách đơn hàng rồi với mỗi đơn hàng lại gọi repository để lấy tên khách hàng hoặc item.

Ví dụ:

~~~java
return orderRepository.findAll()
    .flatMap(order ->
        customerRepository.findById(order.getCustomerId())
            .map(customer -> toView(order, customer))
    );
~~~

Nếu có N đơn hàng, code có thể tạo thêm N truy vấn khách hàng. Đây là vấn đề N+1 query.

Có thể giải quyết bằng nhiều cách:

- Dùng JOIN để lấy dữ liệu liên quan trong một truy vấn.
- Tải danh sách ID liên quan theo batch rồi ghép trong bộ nhớ.
- Dùng view nếu logic được nhiều use case chia sẻ.
- Thiết kế aggregate/read model phù hợp với mẫu truy vấn phổ biến.

JOIN không phải lúc nào cũng tốt hơn mọi truy vấn riêng. Với quan hệ một-nhiều lớn, JOIN có thể nhân số hàng và lặp dữ liệu cha. Hãy so sánh kế hoạch thực thi và số byte truyền về, không chỉ đếm số câu SQL.

Trong reactive pipeline, flatMap có thể tạo nhiều truy vấn đồng thời. Dù concurrency được giới hạn, N+1 vẫn là N+1. Hãy sửa hình dạng truy vấn hoặc batch dữ liệu trước khi chỉ điều chỉnh concurrency.

## 16. Hiệu năng và chỉ mục cho truy vấn đọc

Read model thường kết hợp nhiều bảng và phép lọc. Hãy xem xét:

- Index trên foreign key dùng trong JOIN.
- Index trên cột lọc như customer_id, status hoặc created_at.
- Composite index theo thứ tự cột phù hợp với điều kiện lọc và sắp xếp.
- Chỉ chọn cột cần dùng thay vì SELECT *.
- Tránh tính toán hoặc chuyển đổi không cần thiết trên cột lọc nếu làm mất khả năng dùng index.
- Dùng EXPLAIN/EXPLAIN ANALYZE theo database để xem execution plan.
- Kiểm tra số hàng thực tế, cardinality và chi phí sort/aggregate.

Ví dụ, truy vấn lọc theo customer_id rồi sắp xếp created_at và id có thể cần xem xét index:

~~~sql
CREATE INDEX ix_orders_customer_created_id
ON orders(customer_id, created_at DESC, id DESC);
~~~

Index cụ thể phải dựa trên workload và khả năng của hệ quản trị. Index làm tăng chi phí ghi và dung lượng lưu trữ. Không tạo chỉ mục chỉ dựa vào tên cột xuất hiện trong SQL mà không xem kế hoạch truy vấn.

## 17. Tổ chức code theo write repository và read repository

Một cách tổ chức dễ hiểu là tách repository entity và lớp truy vấn tùy chỉnh:

~~~text
order/
  domain/
    Order.java
    OrderItem.java
  repository/
    OrderRepository.java
  query/
    OrderReadRepository.java
    OrderSummary.java
    OrderDetailView.java
  service/
    OrderService.java
~~~

OrderRepository quản lý thao tác entity/aggregate:

~~~java
public interface OrderRepository
        extends ReactiveCrudRepository<Order, Long> {
    Flux<Order> findByCustomerId(Long customerId);
}
~~~

OrderReadRepository quản lý truy vấn JOIN, thống kê hoặc read model:

~~~java
public interface OrderReadRepository {
    Mono<OrderSummary> findSummary(Long orderId);
    Flux<OrderSummary> findSummaries(Long customerId);
}
~~~

Implementation của OrderReadRepository có thể dùng DatabaseClient. Service phối hợp khi use case cần cả đọc và ghi:

~~~java
@Service
public class OrderService {

    private final OrderRepository orderRepository;
    private final OrderReadRepository orderReadRepository;

    public OrderService(
            OrderRepository orderRepository,
            OrderReadRepository orderReadRepository) {
        this.orderRepository = orderRepository;
        this.orderReadRepository = orderReadRepository;
    }

    public Mono<OrderSummary> getSummary(Long orderId) {
        return orderReadRepository.findSummary(orderId);
    }
}
~~~

Không bắt buộc phải tách thành hai package hoặc hai bean cho mọi dự án. Điểm quan trọng là không làm entity trở nên méo mó chỉ để chứa dữ liệu của một query tổng hợp. Khi số lượng query tăng, tách read repository giúp dễ tìm kiếm, kiểm thử và tối ưu SQL.

## 18. Kiểm thử read model

Một read model cần được kiểm tra ở cả cấp mapping và cấp truy vấn.

### 18.1. Kiểm tra mapping

Với mapper tách riêng, có thể kiểm tra:

- Alias SQL có khớp tên cột mà mapper đọc không.
- Giá trị null có được xử lý đúng không.
- Kiểu số aggregate có tương thích không.
- Timestamp có đúng kiểu và múi giờ không.
- Một LEFT JOIN không có bản ghi con có tạo kết quả đúng không.

### 18.2. Integration test với database thật

Dùng R2DBC driver và database tương ứng để kiểm tra:

- Query JOIN trả về đúng số hàng.
- GROUP BY và aggregate cho kết quả mong đợi.
- Trạng thái không có item trả về 0 hoặc null theo thiết kế.
- Tham số bind hoạt động đúng.
- Pagination không lặp hoặc bỏ sót hàng.
- Kiểu dữ liệu và conversion hoạt động như môi trường triển khai.

H2 hoặc database giả lập có thể không tái hiện đầy đủ hành vi của PostgreSQL, MySQL hoặc SQL Server. Với SQL phụ thuộc dialect, nên có integration test trên đúng hệ quản trị mục tiêu.

### 18.3. Kiểm thử dữ liệu biên

Ví dụ dữ liệu nên bao gồm:

- Đơn hàng không có item.
- Đơn hàng có nhiều item.
- Khách hàng bị thiếu nếu quan hệ cho phép LEFT JOIN.
- Giá trị tổng tiền có phần thập phân.
- Trường nullable.
- Nhiều đơn hàng có cùng timestamp.
- Một tập kết quả rỗng.

## 19. Những lỗi thường gặp

| Lỗi hoặc nhầm lẫn | Hệ quả | Cách xử lý |
|---|---|---|
| Dùng entity của một bảng để chứa mọi cột JOIN | Entity không còn phản ánh schema | Tạo DTO/record riêng |
| Nghĩ JOIN tự tạo object lồng nhau | Mỗi Row vẫn là một hàng phẳng | Gom theo khóa hoặc dùng query tổng hợp |
| Dùng @MappedCollection cho mọi kết quả JOIN | Nhầm aggregate mapping với read projection | Dùng DTO/mapper cho kết quả truy vấn |
| SELECT * trong query nhiều bảng | Trùng tên cột và dữ liệu thừa | Chọn cột cần thiết, đặt alias rõ ràng |
| Alias không khớp row.get() | Mapping nhận null hoặc lỗi lúc chạy | Đồng bộ alias SQL và mapper |
| COUNT(*) sau LEFT JOIN để đếm item | Có thể đếm cả hàng cha không có item | Dùng COUNT(item.id) |
| SUM trả về NULL nhưng DTO mong 0 | Kết quả không đúng kỳ vọng | Dùng COALESCE khi nghiệp vụ yêu cầu |
| Dùng double cho tiền | Có thể phát sinh sai số dấu phẩy động | Dùng BigDecimal/DECIMAL |
| N+1 query khi tạo DTO | Tăng số round trip và độ trễ | JOIN hoặc batch truy vấn |
| Phân trang trực tiếp trên JOIN một-nhiều | Một entity cha bị chia qua nhiều trang | Phân trang ID cha trước |
| Gom mọi kết quả bằng collectList() | Tăng bộ nhớ theo kích thước dữ liệu | Giới hạn, phân trang hoặc streaming |
| Tạo materialized view quá sớm | Tăng độ phức tạp đồng bộ và refresh | Bắt đầu bằng query/DTO, đo hiệu năng trước |
| Cho rằng DTO có thể save như entity | Không có mapping/lifecycle lưu trữ phù hợp | Dùng DTO chỉ cho đọc hoặc ánh xạ sang command/entity riêng |

## 20. Quy trình thiết kế mô hình đọc

Khi một truy vấn không tương ứng với một bảng, hãy đi theo các bước:

1. Xác định use case đọc: màn hình, API, báo cáo hay thống kê.
2. Liệt kê chính xác các trường đầu ra cần có.
3. Xác định trường nào đến từ bảng nào, trường nào là biểu thức hoặc aggregate.
4. Quyết định kết quả là một hàng, nhiều hàng phẳng hay cấu trúc lồng nhau.
5. Tạo DTO, record hoặc projection có tên thể hiện mục đích.
6. Chọn derived query, @Query, R2dbcEntityTemplate hay DatabaseClient theo độ phức tạp.
7. Viết SQL với alias ổn định, chọn đúng cột và bind mọi giá trị đầu vào.
8. Ánh xạ Row sang kiểu đọc, xử lý null và kiểu aggregate rõ ràng.
9. Nếu có quan hệ một-nhiều, xác định cách nhóm hàng và giới hạn bộ nhớ.
10. Kiểm tra N+1, pagination, index và execution plan.
11. Viết integration test với database/driver thực tế.
12. Giữ read model độc lập với entity ghi nếu hai cấu trúc có mục đích khác nhau.

## 21. Bài tập tự kiểm tra

### Bài 1: Chọn kiểu kết quả

Một truy vấn JOIN customers và orders trả về orderId, customerName và status. Có nên ánh xạ trực tiếp vào entity Customer không?

Gợi ý: Không. Đây là kết quả của một use case đọc, nên tạo DTO/record như OrderCustomerView.

### Bài 2: Aggregate theo trạng thái

Truy vấn đếm số đơn hàng theo status trả về nhiều hàng. Hãy khai báo read model.

Gợi ý:

~~~java
public record OrderStatusCount(
    String status,
    Long orderCount
) {}
~~~

### Bài 3: LEFT JOIN không có dòng con

Một đơn hàng chưa có item. Vì sao COUNT(oi.id) phù hợp hơn COUNT(*) khi đếm item sau LEFT JOIN?

Gợi ý: LEFT JOIN vẫn tạo một hàng cho đơn hàng cha. COUNT(*) đếm hàng đó, còn COUNT(oi.id) bỏ qua giá trị NULL ở phía item.

### Bài 4: JOIN một-nhiều

Một đơn hàng có năm item. Query JOIN trả về năm hàng. Làm thế nào tạo một OrderDetailView chứa một danh sách năm item?

Gợi ý: Map mỗi Row thành kiểu trung gian phẳng, nhóm theo orderId rồi tạo DTO cha với List item. Hoặc dùng truy vấn tổng hợp phù hợp với database.

### Bài 5: Phân trang

Bạn muốn phân trang 20 đơn hàng, mỗi đơn có thể có nhiều item. Vì sao LIMIT 20 trực tiếp trên JOIN có thể sai?

Gợi ý: LIMIT áp dụng cho hàng JOIN, không phải số đơn hàng duy nhất. Hãy phân trang ID đơn hàng trước, rồi tải các item cho tập ID đó.

### Bài 6: Chọn công cụ

Một truy vấn báo cáo dùng JOIN ba bảng, GROUP BY và SUM. Bạn nên chọn derived query hay DatabaseClient?

Gợi ý: DatabaseClient thường phù hợp vì cho phép kiểm soát SQL, alias, kiểu dữ liệu và Row mapping. @Query cũng có thể dùng nếu query tĩnh và mapping projection được hỗ trợ rõ ràng.

### Bài 7: Phân biệt read model và CQRS

Một service có một record DTO trả về từ query JOIN. Như vậy đã áp dụng CQRS đầy đủ chưa?

Gợi ý: Chưa. Đó là một read model. CQRS đầy đủ còn tách trách nhiệm xử lý command/query và có thể có mô hình lưu trữ hoặc cơ chế đồng bộ riêng.

## 22. Ghi nhớ

- Một truy vấn JOIN hoặc aggregate không nhất thiết trả về một entity của bảng.
- Entity/aggregate phục vụ lưu trữ và quy tắc nghiệp vụ; DTO, record hoặc projection mô tả kết quả đọc.
- Dùng projection cho kết quả đơn giản; dùng DTO/record rõ ràng cho JOIN, aggregate và cấu trúc tùy chỉnh.
- DatabaseClient phù hợp khi cần kiểm soát SQL, alias, bind và Row mapping.
- Alias SQL là hợp đồng giữa truy vấn và mapper; phải đồng bộ với tên cột được đọc.
- JOIN một-nhiều tạo nhiều hàng phẳng; muốn có object lồng nhau cần nhóm hoặc tổng hợp rõ ràng.
- LEFT JOIN có thể tạo NULL; COUNT, SUM và COALESCE cần được dùng đúng ngữ nghĩa.
- Dùng BigDecimal cho giá trị tiền và kiểm tra kiểu aggregate theo database/driver.
- Tránh N+1 bằng JOIN hoặc batch query; phân trang bảng cha trước khi mở rộng quan hệ một-nhiều.
- View và materialized view hữu ích khi logic đọc được dùng lại hoặc cần tối ưu, nhưng có chi phí quản lý và độ mới dữ liệu.
- Một read DTO không đồng nghĩa với CQRS đầy đủ.
- Kiểm thử mapping, null, aggregate, pagination và SQL trên database/driver thực tế.

Khi kết quả truy vấn có hình dạng khác với bảng lưu trữ, hãy thiết kế read model theo nhu cầu sử dụng của dữ liệu. Giữ entity đúng với vai trò lưu trữ, viết query trả về các cột cần thiết và ánh xạ chúng thành DTO hoặc record rõ ràng. Cách tổ chức đó giúp truy vấn JOIN và báo cáo dễ đọc, dễ kiểm thử và dễ tối ưu trong ứng dụng Spring Data Relational R2DBC.

