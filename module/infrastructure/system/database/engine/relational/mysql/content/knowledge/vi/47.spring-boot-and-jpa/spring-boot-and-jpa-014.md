# Phân trang, native query, projection và kiểm soát N+1

Một API danh sách đơn hàng có thể chỉ trả về 20 dòng nhưng vẫn làm database chạy nhiều truy vấn, tải hàng nghìn entity và chiếm bộ nhớ lớn. Nguyên nhân thường nằm ở cách phân trang, cách lấy dữ liệu và cách JPA tải quan hệ giữa các entity. Spring Data JPA cung cấp `Pageable`, `Page`, `Slice`, projection và `@Query`; Hibernate cung cấp fetch join, entity graph và batch fetching để kiểm soát việc tải quan hệ.

Bài học dùng Spring Boot 3.x, Spring Data JPA 3.x, Hibernate 6 và MySQL 8.0/8.4. Các nguyên tắc vẫn áp dụng cho những phiên bản tương thích khác, nhưng cú pháp API, khả năng phân tích native SQL và hành vi provider cần được kiểm tra theo dependency thực tế.

## Mục tiêu

Sau bài học, bạn có thể:

- Phân trang bằng `Pageable`, chọn đúng giữa `Page`, `Slice` và `List`.
- Tạo native query có `countQuery` chính xác và bind tham số an toàn.
- Dùng interface projection và DTO projection để chỉ lấy cột cần thiết.
- Nhận biết N+1 query qua SQL log và Hibernate statistics.
- Chọn `JOIN FETCH`, `@EntityGraph`, batch fetching hoặc truy vấn DTO phù hợp.
- Tránh lỗi phân trang trên collection fetch join.
- Tối ưu offset pagination, keyset pagination và index MySQL theo thứ tự sắp xếp.

## 1. Bối cảnh: API danh sách đơn hàng

Giả sử hệ thống có ba bảng:

```sql
CREATE TABLE customers (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    full_name VARCHAR(150) NOT NULL,
    email VARCHAR(255) NOT NULL
) ENGINE=InnoDB;

CREATE TABLE purchase_orders (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    customer_id BIGINT NOT NULL,
    status VARCHAR(30) NOT NULL,
    total_amount DECIMAL(14,2) NOT NULL,
    created_at DATETIME(6) NOT NULL,
    CONSTRAINT fk_orders_customer
        FOREIGN KEY (customer_id) REFERENCES customers(id)
) ENGINE=InnoDB;

CREATE TABLE order_items (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    order_id BIGINT NOT NULL,
    product_name VARCHAR(200) NOT NULL,
    quantity INT NOT NULL,
    unit_price DECIMAL(14,2) NOT NULL,
    CONSTRAINT fk_items_order
        FOREIGN KEY (order_id) REFERENCES purchase_orders(id)
) ENGINE=InnoDB;
```

Một màn hình danh sách chỉ cần mã đơn, tên khách hàng, trạng thái, tổng tiền và thời điểm tạo. Trang chi tiết mới cần danh sách `order_items`. Nếu API danh sách tải toàn bộ entity rồi truy cập quan hệ từng dòng, ứng dụng có thể phát sinh N+1 query. Nếu API lấy tất cả đơn hàng rồi phân trang trong Java, cả database lẫn ứng dụng đều phải xử lý nhiều dữ liệu hơn mức cần thiết.

## 2. Phân trang bằng Spring Data JPA

### 2.1. Pageable và Page

Repository có thể nhận `Pageable` để Spring Data thêm giới hạn và offset vào truy vấn:

```java
public interface PurchaseOrderRepository
        extends JpaRepository<PurchaseOrder, Long> {

    Page<PurchaseOrder> findByStatus(
        String status,
        Pageable pageable
    );
}
```

Service tạo yêu cầu phân trang:

```java
Pageable pageable = PageRequest.of(
    0,
    20,
    Sort.by(
        Sort.Order.desc("createdAt"),
        Sort.Order.desc("id")
    )
);

Page<PurchaseOrder> page =
    purchaseOrderRepository.findByStatus("PAID", pageable);
```

`PageRequest.of()` dùng số trang bắt đầu từ 0. `Page` cung cấp dữ liệu trang hiện tại cùng metadata như `getTotalElements()`, `getTotalPages()`, `hasNext()` và `getNumber()`.

Với `Page`, Spring Data thường chạy thêm một truy vấn `COUNT` để tính tổng số dòng thỏa điều kiện. Truy vấn đếm có thể tốn kém với điều kiện lọc phức tạp, join nhiều bảng hoặc tập dữ liệu lớn. Chỉ dùng `Page` khi giao diện thật sự cần tổng số bản ghi hoặc tổng số trang.

### 2.2. Slice khi không cần tổng số trang

Nếu giao diện chỉ cần biết còn trang tiếp theo hay không, dùng `Slice`:

```java
public interface PurchaseOrderRepository
        extends JpaRepository<PurchaseOrder, Long> {

    Slice<PurchaseOrder> findByStatus(
        String status,
        Pageable pageable
    );
}
```

Spring Data lấy thêm một dòng để xác định có trang tiếp theo, thay vì phải tính tổng số dòng. `Slice` có `hasNext()` và `hasPrevious()`, nhưng không có `getTotalElements()` hay `getTotalPages()`.

### 2.3. List kết hợp Pageable

Nếu chỉ cần danh sách của trang hiện tại và không cần metadata:

```java
List<PurchaseOrder> findByStatus(
    String status,
    Pageable pageable
);
```

Spring Data vẫn áp dụng limit/offset theo `Pageable`, nhưng không cần truy vấn count để tạo đối tượng `Page`. Đây là lựa chọn phù hợp cho API chỉ trả về các hàng của trang hiện tại.

### 2.4. Chọn kiểu kết quả

| Kiểu trả về | Truy vấn dữ liệu | Truy vấn count | Metadata |
|---|---|---|---|
| `Page<T>` | Có | Thường có, đôi khi được tối ưu bỏ qua nếu có thể suy ra tổng | Tổng dòng, tổng trang, trang hiện tại |
| `Slice<T>` | Có, thường lấy thêm một dòng | Không | Có trang tiếp theo/trước đó |
| `List<T>` với `Pageable` | Có | Không | Chỉ có danh sách |

Không nên trả `Page` chỉ vì repository có phân trang. Hãy chọn theo nhu cầu của client. Với infinite scroll hoặc nút “Tải thêm”, `Slice` thường phù hợp hơn. Với báo cáo cần hiển thị “1–20 trong 12.450 kết quả”, `Page` có thể cần thiết.

### 2.5. Sắp xếp ổn định

Phân trang phải có thứ tự ổn định. Nếu chỉ sắp xếp theo `createdAt` mà nhiều đơn hàng có cùng thời điểm, thứ tự giữa các trang có thể thay đổi khi MySQL trả về các hàng đồng hạng. Thêm khóa duy nhất làm tie-breaker:

```java
Sort sort = Sort.by(
    Sort.Order.desc("createdAt"),
    Sort.Order.desc("id")
);
Pageable pageable = PageRequest.of(pageNumber, pageSize, sort);
```

Không dùng tên cột do client gửi trực tiếp làm `Sort` nếu chưa kiểm soát. Tên cột hoặc biểu thức SQL không phải giá trị bind parameter. Hãy ánh xạ một danh sách trường sắp xếp được cho phép sang `Sort` tương ứng; từ chối trường không hợp lệ.

Đặt giới hạn `pageSize` ở tầng API để tránh client yêu cầu hàng trăm nghìn dòng trong một trang. Kích thước tối đa nên dựa trên payload, latency và tải database thực tế.

## 3. Native query với phân trang

JPQL phù hợp với truy vấn theo entity và quan hệ. Khi cần dùng cú pháp riêng của MySQL, CTE, window function, hàm đặc thù hoặc tối ưu SQL cụ thể, có thể dùng native query.

### 3.1. Native query trả về Page

Ví dụ lấy đơn hàng theo trạng thái:

```java
public interface PurchaseOrderRepository
        extends JpaRepository<PurchaseOrder, Long> {

    @Query(
        value = """
            SELECT p.*
            FROM purchase_orders p
            WHERE p.status = :status
            ORDER BY p.created_at DESC, p.id DESC
            """,
        countQuery = """
            SELECT COUNT(*)
            FROM purchase_orders p
            WHERE p.status = :status
            """,
        nativeQuery = true
    )
    Page<PurchaseOrder> findPageByStatusNative(
        @Param("status") String status,
        Pageable pageable
    );
}
```

Spring Data áp dụng phân trang từ `Pageable` vào native query. `countQuery` mô tả chính xác tổng số hàng thỏa điều kiện, không có `ORDER BY`. Với query phức tạp, nên khai báo `countQuery` rõ ràng thay vì trông chờ framework tự suy ra. Vì câu SQL đã có `ORDER BY` cố định, truyền `Pageable` không kèm `Sort`, ví dụ `PageRequest.of(page, size, Sort.unsorted())`; nếu cần sort động, dùng danh sách sort được allowlist và kiểm tra SQL được sinh ra.

Nếu truy vấn có join làm một đơn hàng xuất hiện nhiều lần, count phải đếm đúng thực thể gốc:

```sql
SELECT COUNT(DISTINCT p.id)
FROM purchase_orders p
JOIN order_items i ON i.order_id = p.id
WHERE i.quantity >= 2;
```

Nếu dùng `COUNT(*)` trong trường hợp trên, tổng số có thể bị nhân lên theo số item. Count query phải phản ánh đúng điều kiện lọc và tính duy nhất của kết quả mà query dữ liệu trả về.

### 3.2. Native query có điều kiện lọc nhiều bảng

Ví dụ chỉ lấy đơn hàng có tên khách hàng khớp từ khóa:

```java
@Query(
    value = """
        SELECT p.*
        FROM purchase_orders p
        JOIN customers c ON c.id = p.customer_id
        WHERE p.status = :status
          AND c.full_name LIKE CONCAT('%', :keyword, '%')
        ORDER BY p.created_at DESC, p.id DESC
        """,
    countQuery = """
        SELECT COUNT(*)
        FROM purchase_orders p
        JOIN customers c ON c.id = p.customer_id
        WHERE p.status = :status
          AND c.full_name LIKE CONCAT('%', :keyword, '%')
        """,
    nativeQuery = true
)
Page<PurchaseOrder> searchByStatusAndCustomerName(
    @Param("status") String status,
    @Param("keyword") String keyword,
    Pageable pageable
);
```

Nếu join có thể tạo nhiều hàng cho một đơn hàng, dùng `COUNT(DISTINCT p.id)` và bảo đảm truy vấn dữ liệu cũng có semantics tương ứng. Với `LIKE '%keyword%'`, index B-tree thông thường thường không giúp tìm kiếm theo tiền tố bất kỳ; cần đánh giá full-text index hoặc giải pháp tìm kiếm khác nếu workload yêu cầu.

### 3.3. Sort với native query

Khả năng Spring Data tự viết lại native SQL để áp dụng `Sort` phụ thuộc độ phức tạp câu truy vấn và phiên bản Spring Data JPA. Không nên giả định mọi native query đều được thêm `ORDER BY` động chính xác. Cách an toàn là khai báo `ORDER BY` cố định trong SQL hoặc xây dựng các biến thể query từ danh sách cột sắp xếp đã allowlist.

Không nối trực tiếp chuỗi sort do người dùng gửi vào SQL:

```java
// Không an toàn: sortColumn lấy trực tiếp từ request.
String sql = "SELECT * FROM purchase_orders ORDER BY " + sortColumn;
```

Thay vào đó, ánh xạ trường hợp lệ:

```java
String orderBy = switch (requestedSort) {
    case "createdAt" -> "p.created_at";
    case "amount" -> "p.total_amount";
    case "id" -> "p.id";
    default -> throw new IllegalArgumentException("Unsupported sort");
};

String direction = descending ? "DESC" : "ASC";
String sql = """
    SELECT p.id, p.status, p.total_amount
    FROM purchase_orders p
    ORDER BY %s %s, p.id DESC
    """.formatted(orderBy, direction);
```

Đoạn minh họa chỉ ghép các token đã được chọn từ danh sách cố định; các giá trị dữ liệu vẫn phải bind bằng `PreparedStatement`. Với repository query tĩnh, ưu tiên nhiều phương thức/query rõ ràng hơn là ghép SQL động phức tạp.

## 4. Projection: chỉ lấy dữ liệu cần dùng

Entity biểu diễn trạng thái và quan hệ của domain. Một màn hình danh sách thường chỉ cần một phần nhỏ thuộc tính; tải cả entity có thể kéo theo persistence context, dirty checking và lazy association không cần thiết. Projection cho phép truy vấn trực tiếp dữ liệu phục vụ use case.

### 4.1. Interface projection

Định nghĩa interface:

```java
public interface OrderListRow {
    Long getId();
    String getStatus();
    BigDecimal getTotalAmount();
    LocalDateTime getCreatedAt();
    String getCustomerName();
}
```

Truy vấn JPQL dùng alias khớp với tên property:

```java
@Query(
    value = """
        SELECT p.id AS id,
               p.status AS status,
               p.totalAmount AS totalAmount,
               p.createdAt AS createdAt,
               c.fullName AS customerName
        FROM PurchaseOrder p
        JOIN p.customer c
        WHERE p.status = :status
        """,
    countQuery = """
        SELECT COUNT(p)
        FROM PurchaseOrder p
        WHERE p.status = :status
        """
)
Page<OrderListRow> findOrderRows(
    @Param("status") String status,
    Pageable pageable
);
```

Projection chỉ lấy các thuộc tính được chọn và trả về view dữ liệu phù hợp với màn hình. `Page` vẫn cần count query; nếu không cần tổng số, đổi sang `Slice<OrderListRow>` hoặc `List<OrderListRow>` có `Pageable`.

### 4.2. Interface projection với native SQL

Native query cần alias cột theo tên property projection:

```java
public interface NativeOrderRow {
    Long getId();
    String getStatus();
    BigDecimal getTotalAmount();
    LocalDateTime getCreatedAt();
    String getCustomerName();
}
```

```java
@Query(
    value = """
        SELECT p.id AS id,
               p.status AS status,
               p.total_amount AS totalAmount,
               p.created_at AS createdAt,
               c.full_name AS customerName
        FROM purchase_orders p
        JOIN customers c ON c.id = p.customer_id
        WHERE p.status = :status
        ORDER BY p.created_at DESC, p.id DESC
        """,
    countQuery = """
        SELECT COUNT(*)
        FROM purchase_orders p
        WHERE p.status = :status
        """,
    nativeQuery = true
)
Page<NativeOrderRow> findNativeOrderRows(
    @Param("status") String status,
    Pageable pageable
);
```

Alias như `totalAmount`, `createdAt`, `customerName` giúp ánh xạ kết quả SQL sang getter. Kiểm tra kiểu dữ liệu mà JDBC trả về cho các cột ngày giờ, số thập phân và giá trị nullable; mapping có thể phụ thuộc driver và kiểu cột.

### 4.3. DTO projection bằng record

Với DTO bất biến, Java record là lựa chọn gọn:

```java
public record OrderSummary(
    Long id,
    String status,
    BigDecimal totalAmount,
    LocalDateTime createdAt,
    String customerName
) {}
```

JPQL dùng constructor expression:

```java
@Query(
    value = """
        SELECT new com.example.orders.OrderSummary(
            p.id,
            p.status,
            p.totalAmount,
            p.createdAt,
            c.fullName
        )
        FROM PurchaseOrder p
        JOIN p.customer c
        WHERE p.status = :status
        """,
    countQuery = """
        SELECT COUNT(p)
        FROM PurchaseOrder p
        WHERE p.status = :status
        """
)
Page<OrderSummary> findSummaries(
    @Param("status") String status,
    Pageable pageable
);
```

Tên lớp trong constructor expression phải là fully qualified class name. Thứ tự và kiểu tham số phải khớp constructor của record/DTO. Cách này rõ ràng và không phụ thuộc tên alias như interface projection.

### 4.4. DTO projection từ native query

Native SQL trả về cột theo JDBC result set. Việc ánh xạ trực tiếp sang DTO/record phụ thuộc khả năng mapping constructor của Spring Data và cấu trúc kết quả. Với mapping không khớp thứ tự/tên/kiểu cột, dùng `@SqlResultSetMapping`/`@ConstructorResult` hoặc lấy interface projection rồi chuyển sang DTO trong service.

Không giả định một native query có thể map bất kỳ kết quả SQL nào vào record chỉ vì tên cột giống tên component. Kiểm thử mapping trên phiên bản Spring Data JPA và Connector/J thực tế.

### 4.5. Khi nào dùng projection?

| Tình huống | Lựa chọn |
|---|---|
| Màn hình danh sách chỉ hiển thị vài cột | Interface hoặc DTO projection |
| Cần dữ liệu bất biến để trả API | DTO/record projection |
| Cần cập nhật entity và dùng lifecycle/domain behavior | Entity |
| Query MySQL đặc thù hoặc CTE/window function | Native query + projection |
| Cần tổng số trang | `Page<Projection>` và count query đúng |
| Chỉ cần “còn dữ liệu nữa không” | `Slice<Projection>` |

Projection không tự động loại bỏ mọi N+1. Nếu projection trả về entity hoặc nested association rồi service tiếp tục truy cập lazy relation, N+1 vẫn có thể xuất hiện. Với danh sách, ưu tiên projection phẳng chứa đúng dữ liệu cần trả về.

## 5. N+1 query là gì?

N+1 xảy ra khi ứng dụng chạy một truy vấn để lấy N entity gốc, sau đó phát sinh thêm một truy vấn cho từng entity khi truy cập quan hệ lazy. Ví dụ lấy 50 đơn hàng bằng một query, rồi gọi `order.getCustomer().getFullName()` cho từng hàng có thể tạo thêm 50 query nếu customer chưa được tải.

### 5.1. Ví dụ entity

```java
@Entity
@Table(name = "purchase_orders")
public class PurchaseOrder {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "customer_id", nullable = false)
    private Customer customer;

    @OneToMany(mappedBy = "purchaseOrder", fetch = FetchType.LAZY)
    private List<OrderItem> items = new ArrayList<>();
}
```

```java
@Entity
@Table(name = "customers")
public class Customer {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    private String fullName;
}
```

Lấy danh sách:

```java
List<PurchaseOrder> orders =
    purchaseOrderRepository.findByStatus("PAID");

for (PurchaseOrder order : orders) {
    // Có thể kích hoạt một SELECT riêng cho từng customer.
    log.info("Customer: {}", order.getCustomer().getFullName());
}
```

Nếu có 50 đơn hàng thuộc 50 khách hàng khác nhau, có thể xuất hiện 1 query lấy đơn hàng và 50 query lấy customer. Nếu nhiều đơn hàng cùng một customer, persistence context có thể giảm số lần tải thực tế, nhưng không nên dựa vào điều đó để thiết kế.

N+1 cũng có thể xảy ra với collection:

```java
for (PurchaseOrder order : orders) {
    int itemCount = order.getItems().size();
    log.info("Order {} has {} items", order.getId(), itemCount);
}
```

Hibernate có thể chạy thêm một query cho collection của mỗi đơn hàng. Việc serialize entity trực tiếp ra JSON cũng có thể vô tình truy cập lazy relation và kích hoạt N+1.

### 5.2. Phát hiện N+1

Bật log SQL trong môi trường phát triển:

```yaml
spring:
  jpa:
    show-sql: false

logging:
  level:
    org.hibernate.SQL: DEBUG
    org.hibernate.orm.jdbc.bind: TRACE
```

Bind logging có thể ghi dữ liệu nhạy cảm; chỉ bật có kiểm soát ở môi trường phát triển/test và che thông tin trước khi chia sẻ log. `spring.jpa.show-sql` không cần bật nếu đã cấu hình logger Hibernate.

Có thể bật Hibernate statistics trong môi trường kiểm thử:

```yaml
spring:
  jpa:
    properties:
      hibernate:
        generate_statistics: true
```

Đọc số prepared statement trong test:

```java
SessionFactory sessionFactory =
    entityManagerFactory.unwrap(SessionFactory.class);

Statistics statistics = sessionFactory.getStatistics();
statistics.clear();

// Gọi service/repository cần kiểm tra.
orderService.getOrderList();

long statementCount = statistics.getPrepareStatementCount();
assertThat(statementCount).isLessThanOrEqualTo(3);
```

Đây là ý tưởng kiểm thử; cần cô lập dữ liệu và reset statistics trước mỗi test. Các câu lệnh setup, count query, flush hoặc truy vấn phụ có thể làm thay đổi số đếm. Hãy kiểm tra log SQL để biết query nào tạo ra số lần truy cập, không chỉ dựa vào một ngưỡng tổng.

## 6. Cách kiểm soát N+1

Không có một chiến lược fetch phù hợp cho mọi trường hợp. Chọn theo quan hệ cần đọc, kích thước trang và mục đích truy vấn.

### 6.1. JOIN FETCH cho quan hệ to-one

Nếu danh sách cần customer của mỗi order, có thể fetch join quan hệ `ManyToOne`:

```java
@Query("""
    SELECT p
    FROM PurchaseOrder p
    JOIN FETCH p.customer
    WHERE p.status = :status
    """)
List<PurchaseOrder> findWithCustomerByStatus(
    @Param("status") String status
);
```

Truy vấn thường lấy order và customer trong một SQL thay vì tải customer riêng từng lần. `JOIN FETCH` không tạo một association mới trong kết quả JPQL; nó yêu cầu provider tải association cùng entity gốc.

Với quan hệ to-one, fetch join thường phù hợp cho danh sách có phân trang vì mỗi order chỉ liên kết một customer. Tuy vậy, kiểm tra SQL sinh ra, count query và dữ liệu thực tế, đặc biệt khi có thêm join khác.

### 6.2. @EntityGraph

Có thể khai báo fetch plan ngay trên repository:

```java
@EntityGraph(attributePaths = "customer")
Page<PurchaseOrder> findByStatus(
    String status,
    Pageable pageable
);
```

`@EntityGraph` cho biết association nào cần được tải trong truy vấn đó, không buộc phải viết JPQL fetch join. Đây là cách gọn khi cần thêm một hoặc vài quan hệ to-one. Kiểm tra SQL do Hibernate tạo và bảo đảm truy vấn count không bị biến thành join dư thừa.

Không thêm collection lớn vào EntityGraph của một truy vấn phân trang mà không đánh giá. EntityGraph có thể khiến provider phải fetch collection; rủi ro phân trang trên collection tương tự fetch join.

### 6.3. Vì sao collection JOIN FETCH nguy hiểm với pagination?

Giả sử một order có 10 items. Khi join fetch collection, kết quả SQL có thể có 10 hàng cho cùng một order. Nếu đặt `LIMIT 20` ở SQL, giới hạn đó áp dụng lên hàng join, không phải 20 order duy nhất. Hibernate có thể phải lấy nhiều hàng rồi loại trùng và phân trang trong bộ nhớ.

Ví dụ không nên dùng cho trang danh sách:

```java
@Query("""
    SELECT DISTINCT p
    FROM PurchaseOrder p
    LEFT JOIN FETCH p.items
    WHERE p.status = :status
    """)
Page<PurchaseOrder> findPageWithItems(
    @Param("status") String status,
    Pageable pageable
);
```

Hibernate 6 có thể phát cảnh báo `HHH90003004` khi pagination được áp dụng trên collection fetch và thực hiện phân trang trong bộ nhớ. Bật fail-fast ở môi trường phát triển/test để không bỏ qua lỗi thiết kế:

```yaml
spring:
  jpa:
    properties:
      hibernate:
        query:
          fail_on_pagination_over_collection_fetch: true
```

Không dùng `DISTINCT` như cách chữa lỗi này. `DISTINCT` có thể loại hàng trùng ở cấp entity/result semantics, nhưng không làm cho SQL `LIMIT/OFFSET` phân trang theo số entity gốc.

### 6.4. Hai bước: phân trang ID rồi tải association

Khi trang cần cả collection, một cách an toàn hơn là:

1. Truy vấn trang ID của entity gốc với filter, sort và pagination.
2. Truy vấn thứ hai lấy entity/association cho danh sách ID đó.
3. Sắp xếp lại kết quả theo thứ tự ID của trang đầu tiên vì `IN (...)` không bảo đảm giữ thứ tự.

Repository:

```java
@Query(
    value = """
        SELECT p.id
        FROM PurchaseOrder p
        WHERE p.status = :status
        """,
    countQuery = """
        SELECT COUNT(p)
        FROM PurchaseOrder p
        WHERE p.status = :status
        """
)
Page<Long> findPageIdsByStatus(
    @Param("status") String status,
    Pageable pageable
);

@Query("""
    SELECT DISTINCT p
    FROM PurchaseOrder p
    JOIN FETCH p.customer
    LEFT JOIN FETCH p.items
    WHERE p.id IN :ids
    """)
List<PurchaseOrder> findWithCustomerAndItemsByIdIn(
    @Param("ids") Collection<Long> ids
);
```

Service:

```java
Page<Long> idPage =
    repository.findPageIdsByStatus("PAID", pageable);

if (idPage.isEmpty()) {
    return new PageImpl<>(
        List.of(),
        pageable,
        idPage.getTotalElements()
    );
}

List<Long> orderedIds = idPage.getContent();
List<PurchaseOrder> loaded =
    repository.findWithCustomerAndItemsByIdIn(orderedIds);

Map<Long, PurchaseOrder> byId = loaded.stream()
    .collect(Collectors.toMap(
        PurchaseOrder::getId,
        Function.identity()
    ));

List<PurchaseOrder> ordered = orderedIds.stream()
    .map(byId::get)
    .filter(Objects::nonNull)
    .toList();

Page<PurchaseOrder> result = new PageImpl<>(
    ordered,
    pageable,
    idPage.getTotalElements()
);
```

Query đầu phân trang trên order gốc, query thứ hai tải association cho tối đa các ID của trang. Với collection có rất nhiều item, query thứ hai vẫn có thể tạo kết quả lớn; cân nhắc tải item riêng bằng query DTO theo `order_id IN (...)` hoặc dùng batch fetching.

Hai query cần có semantics nhất quán phù hợp. Nếu dữ liệu có thể thay đổi giữa hai lần đọc, chạy trong transaction với isolation phù hợp hoặc chấp nhận rằng association có thể phản ánh thời điểm khác. Với ứng dụng đọc nhiều, cần cân nhắc chi phí giữ snapshot dài.

### 6.5. Batch fetching

Nếu không muốn join nhiều quan hệ trong một query, có thể yêu cầu Hibernate tải lazy association theo nhóm.

Đặt trên association:

```java
@OneToMany(mappedBy = "purchaseOrder", fetch = FetchType.LAZY)
@BatchSize(size = 50)
private List<OrderItem> items = new ArrayList<>();
```

Hoặc cấu hình mặc định:

```yaml
spring:
  jpa:
    properties:
      hibernate:
        default_batch_fetch_size: 50
```

Thay vì chạy một query cho từng collection, Hibernate có thể gom các khóa cần tải vào một truy vấn `IN (...)` theo batch. Batch fetching giảm số round-trip nhưng vẫn tải entity/collection và có thể tải nhiều dữ liệu hơn projection. Chọn batch size dựa trên kích thước trang, số association và giới hạn bind parameter của database.

### 6.6. Projection thường là lựa chọn tốt cho màn hình danh sách

Nếu danh sách chỉ cần tên khách hàng và vài trường của order, projection phẳng thường đơn giản và tiết kiệm hơn tải entity rồi fetch association:

```java
@Query("""
    SELECT new com.example.orders.OrderSummary(
        p.id, p.status, p.totalAmount, p.createdAt, c.fullName
    )
    FROM PurchaseOrder p
    JOIN p.customer c
    WHERE p.status = :status
    """)
Slice<OrderSummary> findOrderSummaries(
    @Param("status") String status,
    Pageable pageable
);
```

Projection không đưa entity vào persistence context theo cách truy vấn entity thông thường. Nó phù hợp cho read model và API list. Với use case cần thay đổi entity hoặc áp dụng domain behavior, tiếp tục dùng entity và fetch plan có chủ đích.

## 7. Phân trang sâu và keyset pagination

### 7.1. Offset pagination

Spring Data `Pageable` thường dùng offset pagination, tương đương:

```sql
SELECT id, status, created_at
FROM purchase_orders
WHERE status = 'PAID'
ORDER BY created_at DESC, id DESC
LIMIT 20 OFFSET 100000;
```

Khi offset lớn, MySQL vẫn phải tìm và bỏ qua nhiều hàng trước khi trả về 20 hàng cuối. Truy vấn có thể chậm dần ở các trang sâu. Dữ liệu được thêm/xóa giữa hai request cũng có thể khiến người dùng thấy hàng lặp hoặc bị bỏ qua nếu thứ tự không ổn định.

### 7.2. Keyset/seek pagination

Keyset pagination dùng giá trị của hàng cuối trang trước làm điểm bắt đầu trang kế tiếp. Với sort `created_at DESC, id DESC`:

```sql
SELECT id, status, created_at
FROM purchase_orders
WHERE status = 'PAID'
  AND (
      created_at < :lastCreatedAt
      OR (created_at = :lastCreatedAt AND id < :lastId)
  )
ORDER BY created_at DESC, id DESC
LIMIT 20;
```

Khóa `id` là tie-breaker để thứ tự duy nhất. Cần bảo đảm `lastCreatedAt` và `lastId` lấy từ hàng cuối trang trước. Nếu sort có cột nullable, phải định nghĩa rõ thứ tự NULL và điều kiện seek tương ứng.

Ví dụ repository native query:

```java
@Query(value = """
    SELECT p.id AS id,
           p.status AS status,
           p.created_at AS createdAt
    FROM purchase_orders p
    WHERE p.status = :status
      AND (
          p.created_at < :lastCreatedAt
          OR (p.created_at = :lastCreatedAt AND p.id < :lastId)
      )
    ORDER BY p.created_at DESC, p.id DESC
    LIMIT :pageSize
    """, nativeQuery = true)
List<NativeOrderCursorRow> findNextOrderRows(
    @Param("status") String status,
    @Param("lastCreatedAt") LocalDateTime lastCreatedAt,
    @Param("lastId") Long lastId,
    @Param("pageSize") int pageSize
);
```

Đây là query trang tiếp theo; trang đầu cần một query riêng không có điều kiện seek. Native query tự viết `LIMIT` nên không truyền thêm `Pageable` để tránh áp dụng limit/offset lần thứ hai. Validate `pageSize` ở tầng service và giữ giá trị trong giới hạn cho phép.

Keyset pagination phù hợp cho nút “Tải thêm”, batch job và luồng dữ liệu tiến về phía trước. Nó không tự cung cấp tổng số trang. Nếu ứng dụng cần nhảy thẳng đến trang số 5.000, offset pagination vẫn có thể phù hợp hơn dù chi phí tăng.

### 7.3. Index cho phân trang MySQL

Với truy vấn lọc theo `status` và sắp xếp `created_at DESC, id DESC`, có thể đánh giá composite index:

```sql
CREATE INDEX idx_orders_status_created_id
ON purchase_orders (status, created_at DESC, id DESC);
```

Thứ tự cột index phải phù hợp với điều kiện lọc và thứ tự sort. Kiểm tra kế hoạch:

```sql
EXPLAIN ANALYZE
SELECT id, status, created_at
FROM purchase_orders
WHERE status = 'PAID'
ORDER BY created_at DESC, id DESC
LIMIT 20;
```

Không tạo index chỉ vì một truy vấn có `ORDER BY`. Index tăng chi phí ghi và dung lượng lưu trữ. Đo workload đọc/ghi, cardinality, độ chọn lọc của status và kế hoạch thực thi trước khi quyết định.

## 8. DTO tại tầng service và API

Không nên serialize entity trực tiếp trong controller. Entity có thể chứa lazy proxy, vòng tham chiếu hai chiều, trường nội bộ và association chưa được tải. Truy cập getter trong quá trình serialize có thể kích hoạt query ngoài dự kiến hoặc gây lỗi `LazyInitializationException`.

Chuyển projection/DTO thành response model trong service:

```java
public record OrderListResponse(
    Long id,
    String status,
    BigDecimal totalAmount,
    LocalDateTime createdAt,
    String customerName
) {}

public Page<OrderListResponse> getOrders(
        String status,
        Pageable pageable) {

    return repository.findOrderRows(status, pageable)
        .map(row -> new OrderListResponse(
            row.getId(),
            row.getStatus(),
            row.getTotalAmount(),
            row.getCreatedAt(),
            row.getCustomerName()
        ));
}
```

API chỉ nhận các tham số trang và sort đã được kiểm soát:

```java
@GetMapping("/orders")
public Page<OrderListResponse> listOrders(
        @RequestParam String status,
        @RequestParam(defaultValue = "0") int page,
        @RequestParam(defaultValue = "20") int size) {

    int safeSize = Math.min(Math.max(size, 1), 100);
    Pageable pageable = PageRequest.of(
        Math.max(page, 0),
        safeSize,
        Sort.by(
            Sort.Order.desc("createdAt"),
            Sort.Order.desc("id")
        )
    );
    return orderService.getOrders(status, pageable);
}
```

Đoạn controller là ví dụ; cần xử lý tham số sai và định dạng lỗi theo chuẩn API của ứng dụng. Nếu repository query có sort cố định hoặc native SQL, không truyền sort tùy ý từ request vào.

## 9. Open Session in View và ranh giới tải dữ liệu

Trong ứng dụng web, Open Session in View (OSIV) có thể giữ persistence context mở đến khi response được render. Khi đó, lazy association có thể bị tải trong lúc serialize response, khiến N+1 xuất hiện ở tầng web dù service đã kết thúc.

Có thể tắt OSIV để buộc ứng dụng xác định rõ dữ liệu cần tải trong transaction/service:

```yaml
spring:
  jpa:
    open-in-view: false
```

Tắt OSIV không tự sửa N+1. Nếu service trả entity có lazy association chưa tải, controller/serializer có thể gặp `LazyInitializationException`. Hãy dùng projection/DTO hoặc fetch plan rõ ràng trong service transaction. Đây là cách làm lộ sớm các quan hệ mà use case cần thay vì để chúng được tải ngầm trong quá trình serialize.

## 10. Các lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| API trang đầu chạy hai query | `Page` chạy query dữ liệu và count | Dùng `Slice` hoặc `List` nếu không cần tổng số. |
| Tổng số phần tử lớn hơn thực tế | `countQuery` đếm hàng join thay vì entity gốc | Dùng `COUNT(DISTINCT root.id)` khi join nhân bản hàng. |
| Native query không phân trang đúng | SQL phức tạp không được rewrite như kỳ vọng hoặc có LIMIT tự viết | Khai báo `countQuery`, kiểm tra SQL thực tế; tránh kết hợp hai cơ chế limit. |
| Sort native query không hoạt động | Framework không rewrite được ORDER BY động | Dùng ORDER BY cố định hoặc allowlist cột sort. |
| N+1 khi đọc customer | Lazy association được truy cập trong vòng lặp | Projection, to-one fetch join, EntityGraph hoặc batch fetching. |
| N+1 khi serialize JSON | Serializer truy cập lazy association | Trả DTO/projection, tắt OSIV và tải dữ liệu trong service. |
| Trang thiếu order hoặc lặp order | Collection fetch join làm nhân bản hàng; thứ tự không duy nhất | Tránh phân trang collection fetch; sort thêm khóa duy nhất. |
| Hibernate tải toàn bộ bảng khi phân trang | Pagination trên collection fetch join bị thực hiện trong memory | Bật `fail_on_pagination_over_collection_fetch`, dùng hai bước ID hoặc projection. |
| Trang sâu rất chậm | Offset lớn | Cân nhắc keyset pagination và composite index. |
| Projection trả về null | Alias không khớp getter hoặc kiểu cột không tương thích | Đặt alias rõ ràng và kiểm tra mapping JDBC. |
| LazyInitializationException sau khi tắt OSIV | Service trả entity còn association chưa tải | Tải đúng fetch plan hoặc map DTO trong transaction. |

## 11. Quy trình tối ưu một API danh sách

1. Viết rõ các trường API thực sự cần trả về và filter/sort được hỗ trợ.
2. Chọn `Page`, `Slice` hay `List` theo nhu cầu metadata.
3. Dùng projection nếu chỉ cần một phần cột; dùng entity khi cần domain behavior.
4. Nếu dùng native SQL, khai báo `countQuery` và bind mọi giá trị đầu vào.
5. Xác định association nào cần tải; ưu tiên fetch to-one hoặc DTO join rõ ràng.
6. Tránh collection fetch join trên query có pagination.
7. Bật SQL log/statistics trong test để đếm query và phát hiện N+1.
8. Chạy `EXPLAIN ANALYZE` trên truy vấn MySQL với dữ liệu gần production.
9. Đánh giá offset hay keyset pagination và tạo index theo filter/sort nếu có bằng chứng.
10. Kiểm thử API bằng dữ liệu có nhiều đơn hàng, nhiều khách hàng và nhiều items; so sánh query count, latency và kết quả phân trang.

## 12. Bài tập tự kiểm tra

1. Khác biệt quan trọng nhất giữa `Page` và `Slice` là gì?
2. Vì sao `Page` có thể làm API chậm dù truy vấn lấy 20 hàng rất nhanh?
3. Khi native query join sang bảng con, vì sao count query có thể cần `COUNT(DISTINCT p.id)`?
4. Interface projection cần alias cột như thế nào để map sang getter?
5. N+1 xảy ra như thế nào khi truy cập `order.getCustomer()` trong vòng lặp?
6. Vì sao collection `JOIN FETCH` không phù hợp với pagination trực tiếp?
7. Khi nào nên dùng `@BatchSize` thay cho fetch join?
8. Vì sao keyset pagination cần một thứ tự duy nhất và ổn định?
9. Tắt OSIV có tự động loại bỏ N+1 không?
10. Với query lọc `status` và sort `created_at, id`, cần kiểm tra điều gì trước khi tạo composite index?

**Gợi ý đáp án:** (1) `Page` thường chạy count query và có tổng số; `Slice` chỉ xác định có trang tiếp theo. (2) Count query có thể tốn kém hơn query lấy trang, nhất là với join/filter phức tạp. (3) Join có thể tạo nhiều hàng cho cùng một parent; count phải đếm parent duy nhất. (4) Alias phải khớp tên property/getter của projection, ví dụ `customerName` cho `getCustomerName()`. (5) Query lấy danh sách là query đầu, mỗi lazy customer chưa tải có thể tạo query tiếp theo. (6) Join nhân bản hàng parent nên SQL limit áp dụng trên hàng join; Hibernate có thể phân trang trong bộ nhớ. (7) Khi cần tải nhiều lazy association theo nhóm và muốn tránh join lớn hoặc Cartesian product. (8) Nếu sort không duy nhất, hàng có cùng giá trị sort có thể bị lặp hoặc bỏ sót giữa các trang. (9) Không; nó chỉ làm lộ ranh giới lazy loading, ứng dụng vẫn phải chọn fetch plan hoặc projection. (10) Độ chọn lọc, cardinality, thứ tự cột index, workload ghi và `EXPLAIN ANALYZE`.

## Tài liệu tham khảo

- [Spring Data JPA Reference: Paging, Iterating Large Results, Sorting](https://docs.spring.io/spring-data/jpa/reference/repositories/query-methods-details.html)
- [Spring Data JPA Reference: Projections](https://docs.spring.io/spring-data/jpa/reference/repositories/projections.html)
- [Spring Data JPA Reference: Declaring Query Methods](https://docs.spring.io/spring-data/jpa/reference/jpa/query-methods.html)
- [Hibernate ORM User Guide: Fetching](https://docs.jboss.org/hibernate/orm/6.6/userguide/html_single/Hibernate_User_Guide.html#fetching)
- [Hibernate ORM User Guide: Batch fetching](https://docs.jboss.org/hibernate/orm/6.6/userguide/html_single/Hibernate_User_Guide.html#batch-fetching)
- [MySQL 8.4 Reference Manual: EXPLAIN](https://dev.mysql.com/doc/refman/8.4/en/explain.html)
- [MySQL 8.4 Reference Manual: Multiple-Column Indexes](https://dev.mysql.com/doc/refman/8.4/en/multiple-column-indexes.html)
