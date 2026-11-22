# Khi nào cần phối hợp Spring Data JDBC với MyBatis?

Spring Data JDBC và MyBatis đều giúp ứng dụng Java làm việc với relational database, nhưng chúng giải quyết vấn đề ở hai mức khác nhau. Spring Data JDBC tập trung vào persistence của **aggregate**: ánh xạ domain object, lưu aggregate root cùng các thành phần được sở hữu và hỗ trợ các quy tắc như optimistic locking, lifecycle callbacks. MyBatis tập trung vào **SQL do developer kiểm soát**: mapper method, XML query, dynamic SQL, stored procedure và mapping kết quả vào DTO.

Một ứng dụng có thể dùng cả hai nếu mỗi công cụ đảm nhiệm phần việc phù hợp. Mô hình thường gặp là Spring Data JDBC quản lý ghi và vòng đời aggregate, còn MyBatis phục vụ truy vấn báo cáo, join phức tạp hoặc tích hợp với SQL legacy. Hai công cụ cũng có thể tham gia cùng một transaction nếu được cấu hình dùng chung DataSource và transaction manager của Spring.

Điều quan trọng là xác định rõ ai sở hữu từng đường đọc/ghi. Nếu cả hai framework cùng cập nhật một aggregate mà không thống nhất invariant, version, auditing và cache, ứng dụng có thể tạo ra dữ liệu không nhất quán dù từng câu SQL riêng lẻ đều chạy thành công.

## 1. Vai trò của từng công cụ

### 1.1. Spring Data JDBC quản lý aggregate

Spring Data JDBC tổ chức persistence quanh aggregate root. Repository cung cấp các thao tác CRUD, query derivation và SQL tùy chỉnh qua `@Query`. Khi lưu aggregate bằng `repository.save(root)`, framework hiểu mapping của aggregate và đồng bộ các phần được sở hữu theo mô hình Spring Data JDBC.

Ví dụ:

```java
@Table("purchase_orders")
public class PurchaseOrder {

    @Id
    private Long id;

    private String orderNumber;
    private OrderStatus status;

    @Version
    private Long version;

    public void confirm() {
        if (status != OrderStatus.PENDING) {
            throw new IllegalStateException(
                "Chỉ đơn PENDING mới được xác nhận"
            );
        }
        status = OrderStatus.CONFIRMED;
    }

    // Constructor và accessor phù hợp với mapping.
}
```

Repository:

```java
public interface PurchaseOrderRepository
        extends CrudRepository<PurchaseOrder, Long> {
}
```

Service có thể tải aggregate, gọi domain behavior rồi lưu:

```java
@Transactional
public void confirm(Long orderId) {
    PurchaseOrder order = orders.findById(orderId)
        .orElseThrow();

    order.confirm();
    orders.save(order);
}
```

Đường persistence này phù hợp khi cần bảo vệ invariant của aggregate và để Spring Data JDBC quản lý mapping, version và lifecycle tương ứng.

### 1.2. MyBatis kiểm soát SQL và mapping kết quả

MyBatis cho phép viết SQL trực tiếp trong annotation hoặc XML mapper. Nó phù hợp khi truy vấn có cấu trúc phức tạp, cần join nhiều bảng, window function, CTE, stored procedure hoặc mapping kết quả vào read model riêng.

Ví dụ một báo cáo cần tên khách hàng, số đơn và tổng tiền:

```sql
SELECT
    c.id AS customer_id,
    c.name AS customer_name,
    COUNT(o.id) AS order_count,
    COALESCE(SUM(o.total_amount), 0) AS total_amount
FROM customers c
LEFT JOIN purchase_orders o
    ON o.customer_id = c.id
GROUP BY c.id, c.name
ORDER BY total_amount DESC;
```

Đây là dạng truy vấn báo cáo có thể viết bằng MyBatis mapper và trả về DTO. Không cần dựng toàn bộ aggregate khách hàng cùng mọi đơn hàng chỉ để hiển thị một dòng thống kê.

### 1.3. Bảng phân vai

| Nhu cầu | Spring Data JDBC | MyBatis |
| --- | --- | --- |
| CRUD aggregate root | Phù hợp, có repository abstraction | Có thể làm bằng mapper nhưng phải tự quản lý nhiều chi tiết |
| Đồng bộ collection thuộc aggregate | Có mapping/persistence semantics của aggregate | Phải tự viết SQL cho từng thao tác |
| Query dẫn xuất đơn giản | Phù hợp | Có thể viết nhưng thường nhiều cấu hình hơn |
| SQL join/báo cáo phức tạp | Dùng được với SQL tùy chỉnh, nhưng mapping aggregate không phải lúc nào cũng phù hợp | Phù hợp với mapper/DTO |
| Dynamic SQL nhiều nhánh | Có thể cần custom repository | Có hỗ trợ dynamic SQL trong XML/annotation |
| Stored procedure và SQL legacy | Có thể gọi qua JDBC/custom code | Có mapper support thuận tiện |
| Lifecycle callbacks/auditing của aggregate | Có trên đường save/delete aggregate được hỗ trợ | Không tự chạy lifecycle callback của Spring Data JDBC |
| Kiểm soát từng câu SQL | Có qua query/custom repository | Là trọng tâm của MyBatis |

Không có quy tắc bắt buộc mọi ứng dụng phải dùng cả hai. Nếu Spring Data JDBC đã đáp ứng truy vấn và persistence của ứng dụng, thêm MyBatis sẽ làm tăng dependency, cấu hình và số cách truy cập dữ liệu cần bảo trì.

## 2. Những tình huống nên phối hợp

### 2.1. Aggregate write, báo cáo read

Đây là mô hình kết hợp phổ biến:

- Spring Data JDBC ghi và quản lý aggregate theo domain model.
- MyBatis đọc dữ liệu qua join, aggregate function và projection DTO.
- Hai phía cùng sử dụng một schema và có thể dùng chung transaction infrastructure khi cần.

Ví dụ ứng dụng bán hàng:

```text
                    Application Service
                            |
               +------------+------------+
               |                         |
       Spring Data JDBC                MyBatis
       Aggregate write              Reporting read
               |                         |
               +------------+------------+
                            |
                       DataSource
                            |
                         Database
```

DTO báo cáo:

```java
public class OrderSummary {

    private Long orderId;
    private String orderNumber;
    private String customerName;
    private BigDecimal totalAmount;

    public OrderSummary() {
    }

    public Long getOrderId() {
        return orderId;
    }

    public void setOrderId(Long orderId) {
        this.orderId = orderId;
    }

    public String getOrderNumber() {
        return orderNumber;
    }

    public void setOrderNumber(String orderNumber) {
        this.orderNumber = orderNumber;
    }

    public String getCustomerName() {
        return customerName;
    }

    public void setCustomerName(String customerName) {
        this.customerName = customerName;
    }

    public BigDecimal getTotalAmount() {
        return totalAmount;
    }

    public void setTotalAmount(BigDecimal totalAmount) {
        this.totalAmount = totalAmount;
    }
}
```

MyBatis mapper:

```java
@Mapper
public interface OrderReportMapper {

    @Select("""
        SELECT
            o.id AS order_id,
            o.order_number,
            c.name AS customer_name,
            o.total_amount
        FROM purchase_orders o
        JOIN customers c ON c.id = o.customer_id
        WHERE o.status = #{status}
        ORDER BY o.created_at DESC, o.id DESC
        """)
    List<OrderSummary> findSummaries(
        @Param("status") String status
    );
}
```

Service gọi mapper để lấy read model:

```java
@Service
public class OrderReportService {

    private final OrderReportMapper reports;

    public OrderReportService(OrderReportMapper reports) {
        this.reports = reports;
    }

    @Transactional(readOnly = true)
    public List<OrderSummary> findConfirmedOrders() {
        return reports.findSummaries("CONFIRMED");
    }
}
```

DTO chỉ chứa các cột cần cho màn hình/báo cáo. Nó không phải aggregate và không nên được đưa ngược vào `PurchaseOrderRepository.save`.

### 2.2. Truy vấn phức tạp hoặc database-specific

Nên cân nhắc MyBatis khi query cần:

- Common Table Expression (CTE), recursive query hoặc window function.
- Nhiều JOIN và phép tổng hợp với projection khác domain model.
- Dynamic WHERE, ORDER BY hoặc điều kiện tùy chọn phức tạp.
- Stored procedure hoặc function đặc thù database.
- SQL legacy đã được tối ưu và cần giữ nguyên.
- Mapping kết quả thành DTO, record hoặc cấu trúc báo cáo.

Spring Data JDBC vẫn có `@Query` và custom repository, vì vậy một câu SELECT đơn giản không phải lý do đủ để thêm MyBatis. MyBatis đáng cân nhắc khi số lượng SQL đặc thù và nhu cầu kiểm soát mapping trở thành một phần đáng kể của persistence layer.

### 2.3. Batch hoặc thao tác SQL có kiểm soát

MyBatis có thể phù hợp với batch insert/update, import hoặc thao tác trên bảng kỹ thuật mà không cần tải aggregate đầy đủ. Tuy nhiên, SQL trực tiếp trên bảng aggregate có thể bỏ qua domain behavior và lifecycle của Spring Data JDBC.

Nếu batch thay đổi dữ liệu thuộc aggregate, cần quyết định rõ cách giữ invariant, version, auditing và đồng bộ các bảng con. Đừng xem batch mapper là một đường tắt vô hại cho mọi thao tác ghi.

### 2.4. Tích hợp hệ thống legacy

Một hệ thống có thể đã có mapper XML, stored procedure hoặc quy ước SQL lâu năm. Không nhất thiết phải viết lại toàn bộ SQL đó để bắt đầu dùng Spring Data JDBC cho một phần domain mới.

Có thể để MyBatis tiếp tục quản lý các query legacy trong phạm vi rõ ràng, đồng thời dùng Spring Data JDBC cho aggregate mới. Khi đó, cần quy định bảng nào và thao tác nào thuộc mỗi persistence path để tránh hai nơi cùng ghi cùng một dữ liệu mà không có hợp đồng chung.

## 3. Khi nào không cần thêm MyBatis?

Không nên thêm MyBatis chỉ vì muốn dùng một framework SQL khác. Các trường hợp sau thường chưa cần:

- Repository chỉ có CRUD cơ bản.
- Query có thể diễn đạt gọn bằng query derivation.
- Một vài câu SQL tùy chỉnh có thể quản lý tốt bằng `@Query`.
- Ứng dụng không có read/reporting query phức tạp.
- Đội ngũ chưa có nhu cầu duy trì thêm mapper XML, type handler và cấu hình.

Ví dụ:

```java
List<PurchaseOrder> findByStatus(OrderStatus status);

Optional<PurchaseOrder> findByOrderNumber(String orderNumber);
```

Những query đơn giản như trên phù hợp với Spring Data JDBC. Tạo MyBatis mapper cho mỗi method chỉ làm tăng số abstraction mà không đem lại lợi ích tương xứng.

## 4. Chia quyền sở hữu dữ liệu và đường ghi

Đây là quyết định quan trọng nhất khi hai công cụ cùng truy cập một database.

Một quy ước dễ duy trì là:

| Phần dữ liệu | Công cụ sở hữu ghi | Công cụ có thể đọc |
| --- | --- | --- |
| Aggregate purchase order | Spring Data JDBC | MyBatis cho report/read model |
| Aggregate customer | Spring Data JDBC | MyBatis cho report/read model |
| Bảng reporting/projection riêng | MyBatis hoặc pipeline chuyên biệt | MyBatis |
| Outbox/integration table | Repository hoặc mapper được quy định rõ | Worker/mapper |
| Bảng legacy chưa chuyển đổi | MyBatis theo ownership hiện tại | MyBatis; Spring Data JDBC chỉ khi có kế hoạch chuyển đổi |

MyBatis có thể đọc bảng aggregate mà Spring Data JDBC quản lý. Nhưng nếu MyBatis cập nhật trực tiếp bảng aggregate, nó không tự gọi domain method, không đồng bộ aggregate child và không chạy lifecycle callbacks của Spring Data JDBC.

### 4.1. Vì sao không nên có hai đường ghi tùy tiện?

Giả sử aggregate có quy tắc:

- Đơn hàng chỉ được xác nhận khi đang PENDING.
- Khi xác nhận phải ghi thời điểm xác nhận.
- Version tăng để phát hiện cập nhật đồng thời.
- Một số child row phải được đồng bộ theo aggregate.

Nếu mapper chạy:

```sql
UPDATE purchase_orders
SET status = 'CONFIRMED'
WHERE id = #{id};
```

thì câu SQL chỉ đổi cột status. Nó không tự gọi `order.confirm()`, không kiểm tra các invariant khác và không tự áp dụng cơ chế optimistic locking mà Spring Data JDBC dùng khi `save` aggregate có `@Version`.

Nếu thực sự cần direct update, phải thể hiện đầy đủ điều kiện và side effect trong SQL/transaction, ví dụ kiểm tra trạng thái cũ, tăng version, cập nhật audit fields và xử lý row count. Sau đó, aggregate đã tải trước đó cần được reload trước khi tiếp tục sử dụng hoặc lưu.

### 4.2. MyBatis read model không phải aggregate

DTO được MyBatis tạo từ JOIN có thể chứa trường lấy từ nhiều aggregate. Nó phục vụ một mục tiêu đọc cụ thể, không nhất thiết có invariant hoặc identity của domain aggregate.

Không nên nhận DTO báo cáo rồi chuyển thành entity Spring Data JDBC để save. Khi cần thay đổi nghiệp vụ, hãy tải aggregate root qua repository, gọi domain behavior và lưu bằng đường ghi được chọn.

## 5. Cấu hình MyBatis cùng Spring Data JDBC

Ứng dụng cần các dependency tương thích với phiên bản Spring Boot đang dùng:

- Spring Boot starter cho Spring Data JDBC.
- MyBatis Spring Boot Starter.
- JDBC driver cho database.
- Flyway hoặc Liquibase nếu ứng dụng dùng versioned schema migration.

Không nên tự chọn phiên bản starter một cách độc lập mà bỏ qua compatibility matrix của Spring Boot/MyBatis. Dùng dependency management/BOM phù hợp với nền tảng dự án.

### 5.1. Cấu trúc package

Ví dụ:

```text
com.example.shop
├── ShopApplication.java
├── domain
│   └── PurchaseOrder.java
├── repository
│   └── PurchaseOrderRepository.java
├── persistence
│   └── mybatis
│       ├── OrderReportMapper.java
│       └── OrderReportMapper.xml
└── service
    └── OrderService.java
```

Có thể đánh dấu mapper bằng `@Mapper` hoặc dùng `@MapperScan`:

```java
@SpringBootApplication
@MapperScan("com.example.shop.persistence.mybatis")
public class ShopApplication {
    public static void main(String[] args) {
        SpringApplication.run(ShopApplication.class, args);
    }
}
```

Nếu dùng `@MapperScan` cho package, các mapper trong package đó không cần lặp lại `@Mapper`. Chọn một cách rõ ràng và tránh scan trùng không cần thiết.

### 5.2. Cấu hình MyBatis

Ví dụ:

```yaml
mybatis:
  mapper-locations: classpath:/mapper/**/*.xml
  type-aliases-package: com.example.shop.persistence.mybatis.dto
  configuration:
    map-underscore-to-camel-case: true
    local-cache-scope: STATEMENT
```

Ý nghĩa:

- `mapper-locations` chỉ nơi chứa XML mapper.
- `type-aliases-package` chỉ package có các kiểu dùng trong mapper XML.
- `map-underscore-to-camel-case` ánh xạ cột `customer_name` thành property `customerName`.
- `local-cache-scope` điều chỉnh phạm vi local cache của MyBatis SqlSession.

Đây là ví dụ cấu hình; các property cụ thể cần khớp phiên bản MyBatis starter. Nếu mapper dùng annotation hoàn toàn, không cần cấu hình XML location.

### 5.3. Một DataSource dùng chung

Trong cấu hình phổ biến, Spring Boot tạo một DataSource được dùng bởi Spring Data JDBC và MyBatis auto-configuration. MyBatis-Spring sử dụng `SqlSessionTemplate` để quản lý SqlSession và tham gia transaction của Spring.

Không cần tự mở session hoặc commit thủ công trong mapper. Hãy để Spring quản lý lifecycle session và transaction.

Nếu ứng dụng khai báo nhiều DataSource, cần chỉ rõ mapper nào dùng SqlSessionFactory/DataSource nào và repository JDBC nào dùng DataSource nào. Việc hai datasource có cùng JDBC URL không có nghĩa chúng là cùng một transaction resource.

## 6. Dùng chung transaction giữa Spring Data JDBC và MyBatis

Hai framework có thể cùng tham gia một transaction cục bộ nếu:

1. Chúng sử dụng cùng một DataSource bean.
2. Transaction manager quản lý chính DataSource đó.
3. MyBatis được tích hợp qua MyBatis-Spring, thường là `SqlSessionTemplate`.
4. Repository và mapper được gọi trong cùng transaction context của Spring.

Ví dụ service lưu aggregate rồi ghi một outbox row bằng MyBatis:

```java
@Service
public class OrderApplicationService {

    private final PurchaseOrderRepository orders;
    private final OutboxMapper outbox;

    public OrderApplicationService(
        PurchaseOrderRepository orders,
        OutboxMapper outbox
    ) {
        this.orders = orders;
        this.outbox = outbox;
    }

    @Transactional
    public Long placeOrder(PlaceOrderCommand command) {
        PurchaseOrder order = PurchaseOrder.create(command);
        PurchaseOrder saved = orders.save(order);

        outbox.insert(
            "ORDER_PLACED",
            saved.getId().toString(),
            command.toEventPayload()
        );

        return saved.getId();
    }
}
```

MyBatis mapper:

```java
@Mapper
public interface OutboxMapper {

    @Insert("""
        INSERT INTO outbox_events
            (event_type, aggregate_id, payload, created_at)
        VALUES
            (#{eventType}, #{aggregateId}, #{payload}, CURRENT_TIMESTAMP)
        """)
    int insert(
        @Param("eventType") String eventType,
        @Param("aggregateId") String aggregateId,
        @Param("payload") String payload
    );
}
```

Nếu insert outbox thất bại và exception thoát khỏi method, transaction có thể rollback cả việc lưu order và outbox. Đây là lợi ích của việc hai công cụ cùng tham gia một transaction database.

Bảng outbox là một bảng riêng được MyBatis mapper quản lý trong ví dụ này. Worker sẽ đọc và phát sự kiện sau khi transaction commit; không gửi message ra broker trực tiếp trong callback transaction rồi giả định database rollback có thể thu hồi message.

### 6.1. Không gọi commit hoặc rollback thủ công

Khi dùng MyBatis-Spring, không gọi `SqlSession.commit()`, `rollback()` hoặc tự đóng session cho mapper call thông thường. `SqlSessionTemplate` quản lý session theo Spring transaction và đồng bộ việc commit/rollback với transaction manager.

Tự mở `SqlSession` bằng `SqlSessionFactory.openSession()` rồi commit thủ công có thể tạo một transaction độc lập, phá vỡ tính nguyên tử mà service đang mong đợi.

### 6.2. Điều gì xảy ra nếu dùng hai DataSource?

Một `PlatformTransactionManager` thông thường quản lý một transaction resource cục bộ. Nếu Spring Data JDBC dùng DataSource A và MyBatis dùng DataSource B, `@Transactional` gắn với manager của A không tự động làm transaction của B commit/rollback cùng lúc.

Nếu cả hai database phải thay đổi nguyên tử, cần giải pháp transaction phân tán phù hợp hoặc thiết kế lại use case bằng outbox/saga và xử lý eventual consistency. Không giả định một annotation `@Transactional` thông thường tự bao trùm nhiều database.

### 6.3. Transaction read-only

Có thể dùng `@Transactional(readOnly = true)` khi service chỉ đọc qua cả repository và mapper:

```java
@Transactional(readOnly = true)
public OrderDetailsView loadOrder(Long id) {
    PurchaseOrder order = orders.findById(id).orElseThrow();
    List<OrderLineView> lines = reports.findLines(id);

    return OrderDetailsView.from(order, lines);
}
```

Cờ read-only là hint cho transaction manager/driver/database và không phải lớp authorization tuyệt đối. Không dùng transaction read-only cho use case có thao tác ghi.

## 7. Phân biệt converter của Spring Data JDBC và TypeHandler của MyBatis

Hai framework có cơ chế chuyển đổi kiểu riêng:

| Cơ chế | Phạm vi |
| --- | --- |
| Spring Data custom converters | Chuyển đổi giữa property/domain type và kiểu dữ liệu relational/JDBC khi Spring Data JDBC đọc/ghi. |
| MyBatis TypeHandler | Chuyển đổi giữa Java type và JDBC type trong parameter/result mapping của MyBatis. |

Nếu cùng một enum được Spring Data JDBC lưu bằng mã `A` nhưng MyBatis đọc bằng tên enum `ACTIVE`, hai đường truy cập có thể diễn giải cùng cột khác nhau.

Ví dụ MyBatis TypeHandler:

```java
@MappedTypes(CustomerStatus.class)
@MappedJdbcTypes(JdbcType.VARCHAR)
public class CustomerStatusTypeHandler
        extends BaseTypeHandler<CustomerStatus> {

    @Override
    public void setNonNullParameter(
            PreparedStatement ps,
            int index,
            CustomerStatus value,
            JdbcType jdbcType
    ) throws SQLException {
        ps.setString(index, switch (value) {
            case ACTIVE -> "A";
            case INACTIVE -> "I";
        });
    }

    @Override
    public CustomerStatus getNullableResult(
            ResultSet rs,
            String columnName
    ) throws SQLException {
        return parse(rs.getString(columnName));
    }

    @Override
    public CustomerStatus getNullableResult(
            ResultSet rs,
            int columnIndex
    ) throws SQLException {
        return parse(rs.getString(columnIndex));
    }

    @Override
    public CustomerStatus getNullableResult(
            CallableStatement cs,
            int columnIndex
    ) throws SQLException {
        return parse(cs.getString(columnIndex));
    }

    private CustomerStatus parse(String value) {
        if (value == null) {
            return null;
        }

        return switch (value) {
            case "A" -> CustomerStatus.ACTIVE;
            case "I" -> CustomerStatus.INACTIVE;
            default -> throw new IllegalArgumentException(
                "Unknown customer status: " + value
            );
        };
    }
}
```

Đây là ví dụ minh họa TypeHandler; cần đăng ký handler với MyBatis configuration hoặc khai báo trực tiếp trong mapper. Converter của Spring Data JDBC không tự động được MyBatis sử dụng, và TypeHandler của MyBatis cũng không tự áp dụng cho repository Spring Data JDBC.

Hãy có test cho cả hai đường mapping nếu chúng cùng truy cập một cột có format đặc biệt.

## 8. Dynamic SQL và parameter binding trong MyBatis

MyBatis hữu ích khi query thay đổi theo các filter đầu vào. XML mapper hỗ trợ `<if>`, `<where>`, `<choose>`, `<foreach>` và các cấu trúc dynamic SQL khác.

Ví dụ:

```xml
<mapper namespace="com.example.shop.persistence.mybatis.OrderReportMapper">

    <select id="search" resultType="com.example.shop.persistence.mybatis.dto.OrderSummary">
        SELECT
            o.id AS order_id,
            o.order_number,
            c.name AS customer_name,
            o.total_amount
        FROM purchase_orders o
        JOIN customers c ON c.id = o.customer_id

        <where>
            <if test="status != null">
                AND o.status = #{status}
            </if>

            <if test="customerId != null">
                AND c.id = #{customerId}
            </if>

            <if test="minTotal != null">
                AND o.total_amount >= #{minTotal}
            </if>

            <if test="maxTotal != null">
                AND o.total_amount <= #{maxTotal}
            </if>
        </where>

        ORDER BY o.created_at DESC, o.id DESC
    </select>
</mapper>
```

Mapper interface tương ứng:

```java
@Mapper
public interface OrderReportMapper {

    List<OrderSummary> search(
        @Param("status") String status,
        @Param("customerId") Long customerId,
        @Param("minTotal") BigDecimal minTotal,
        @Param("maxTotal") BigDecimal maxTotal
    );
}
```

Các giá trị dùng `#{...}` được bind qua PreparedStatement. Không thay bằng cơ chế string substitution của MyBatis cho dữ liệu request.

String substitution chèn chuỗi trực tiếp vào SQL và có thể gây SQL injection nếu nhận input không tin cậy. Nó chỉ nên được dùng cho identifier/fragment đã được kiểm soát chặt, ví dụ chọn tên cột từ allowlist ở code. Không cho người dùng gửi trực tiếp tên cột hoặc đoạn ORDER BY tùy ý.

## 9. Mapping kết quả: aggregate hay DTO?

Spring Data JDBC repository thường trả về aggregate đã được ánh xạ theo metadata domain. MyBatis thường trả về DTO hoặc projection phù hợp với query.

Ví dụ báo cáo không cần toàn bộ aggregate:

```java
public class CustomerSalesSummary {
    private Long customerId;
    private String customerName;
    private Long completedOrders;
    private BigDecimal revenue;

    // No-args constructor, getters và setters.
}
```

MyBatis query có thể trả DTO này trực tiếp. Nó không cần tạo một `Customer` aggregate với collection đơn hàng chỉ để tính doanh thu.

Hãy chọn kiểu trả về theo mục đích:

- Aggregate khi cần thay đổi domain state và bảo vệ invariant.
- DTO/projection khi chỉ cần đọc một hình dạng dữ liệu phục vụ màn hình, API hoặc báo cáo.
- Một read model riêng khi query/reporting có vòng đời và schema khác domain write model.

## 10. Cache khi hai framework cùng truy cập dữ liệu

MyBatis có local cache theo SqlSession và có thể có second-level cache theo mapper namespace nếu được bật. Spring Data JDBC không tự thông báo cho MyBatis cache rằng một aggregate vừa được cập nhật qua repository.

Vì vậy, nếu mapper bật cache cho dữ liệu mà Spring Data JDBC cũng có thể thay đổi, kết quả cache có thể cũ.

Một số nguyên tắc:

- Tránh bật second-level cache cho mapper đọc các bảng thường xuyên được ghi qua Spring Data JDBC nếu không có chiến lược invalidation.
- Xem xét `localCacheScope=STATEMENT` khi cần giới hạn local cache theo statement.
- Dùng `useCache="false"` cho query không nên dùng second-level cache khi phù hợp.
- Nếu bắt buộc cache dữ liệu dùng chung, thiết kế invalidation/refresh rõ ràng sau các thao tác ghi.
- Không coi cache của một framework tự đồng bộ với persistence context/cache của framework còn lại.

Nếu một transaction vừa cập nhật qua Spring Data JDBC rồi gọi lại cùng mapper query, hãy chú ý local cache của MyBatis có thể giữ kết quả trước đó trong phạm vi SqlSession. Thiết lập cache phù hợp và integration test thứ tự đọc/ghi thực tế.

## 11. Tác động tới lifecycle, auditing và optimistic locking

Spring Data JDBC có thể áp dụng entity callbacks và auditing trong đường save aggregate. MyBatis không chạy các callback đó khi thực thi SQL mapper.

Ví dụ MyBatis UPDATE:

```java
@Update("""
    UPDATE purchase_orders
    SET status = #{status}
    WHERE id = #{id}
    """)
int updateStatus(
    @Param("id") Long id,
    @Param("status") String status
);
```

Câu lệnh này không tự động:

- Gọi domain method của `PurchaseOrder`.
- Kiểm tra invariant của aggregate.
- Tăng cột version theo quy tắc optimistic locking của Spring Data JDBC.
- Cập nhật `@LastModifiedDate` hoặc `@LastModifiedBy`.
- Đồng bộ các child row được aggregate sở hữu.
- Phát entity callback hoặc lifecycle event của Spring Data JDBC.

Nếu MyBatis cần cập nhật bảng aggregate, phải đưa các quy tắc cần thiết vào SQL và application service. Ví dụ optimistic locking cần điều kiện version cũ và tăng version trong cùng statement:

```sql
UPDATE purchase_orders
SET status = :newStatus,
    version = version + 1,
    last_modified_at = :modifiedAt
WHERE id = :id
  AND status = :expectedStatus
  AND version = :expectedVersion;
```

Sau đó kiểm tra row count để phát hiện conflict. Đây là một đường ghi riêng cần được tài liệu hóa và kiểm thử, không tự động tương đương với `repository.save`.

Nếu có thể, giữ MyBatis ở read path và dùng Spring Data JDBC làm owner của aggregate write path.

## 12. Migration và schema ownership

Cả Spring Data JDBC và MyBatis cùng làm việc trên schema relational, vì vậy cần một nguồn sự thật cho DDL.

Thông thường:

- Flyway hoặc Liquibase quản lý versioned schema migration.
- Spring Data JDBC mapping mô tả bảng/column mà aggregate sử dụng.
- MyBatis mapper tham chiếu các bảng/cột tương ứng trong SQL.
- Migration cập nhật schema và mapper/domain code trong cùng thay đổi được review.

Không nên để Spring SQL initialization, Flyway, Liquibase và MyBatis mapper cùng tạo/sửa một bảng theo các quy trình độc lập. Một thay đổi tên cột có thể làm repository mapping vẫn đúng nhưng XML mapper lỗi, hoặc ngược lại.

Khi đổi schema:

1. Thêm migration tương thích.
2. Cập nhật mapping Spring Data JDBC.
3. Cập nhật mapper SQL/MyBatis result mapping.
4. Chạy test cả hai đường đọc/ghi.
5. Triển khai theo chiến lược expand-and-contract nếu nhiều phiên bản ứng dụng cùng chạy.

## 13. Kiểm thử ứng dụng dùng chung hai persistence framework

Test nên chạy qua đúng cấu hình ứng dụng, vì lỗi thường nằm ở integration: mapper scan, SqlSessionTemplate, DataSource, transaction manager, type handler hoặc schema.

### 13.1. Test đọc MyBatis và ghi Spring Data JDBC

Ví dụ integration test:

```java
@SpringBootTest
class OrderPersistenceIntegrationTest {

    @Autowired
    PurchaseOrderRepository orders;

    @Autowired
    OrderReportMapper reports;

    @Test
    void springDataWriteIsVisibleToMyBatisRead() {
        PurchaseOrder saved = orders.save(
            PurchaseOrder.create("PO-MIXED-001")
        );

        List<OrderSummary> summaries =
            reports.findByOrderNumber("PO-MIXED-001");

        assertThat(summaries).hasSize(1);
        assertThat(summaries.get(0).getOrderNumber())
            .isEqualTo("PO-MIXED-001");
    }
}
```

Test cần schema và mapper phù hợp. Nếu dùng transaction test bao ngoài, cần hiểu dữ liệu được đọc trên cùng transaction/connection hay từ transaction khác. Đối với kiểm thử commit thật, có thể để service hoàn tất transaction rồi truy vấn ở transaction mới.

### 13.2. Test cùng transaction rollback

Một test quan trọng xác nhận ghi qua hai framework cùng rollback:

```java
@Service
public class MixedPersistenceService {

    private final PurchaseOrderRepository orders;
    private final OutboxMapper outbox;

    public MixedPersistenceService(
        PurchaseOrderRepository orders,
        OutboxMapper outbox
    ) {
        this.orders = orders;
        this.outbox = outbox;
    }

    @Transactional
    public void createThenFail() {
        PurchaseOrder saved = orders.save(
            PurchaseOrder.create("PO-ROLLBACK-MIXED")
        );

        outbox.insert(
            "ORDER_CREATED",
            saved.getId().toString(),
            "{}"
        );

        throw new IllegalStateException("Test rollback");
    }
}
```

Test gọi service và xác nhận sau khi transaction kết thúc:

- Không có order `PO-ROLLBACK-MIXED`.
- Không có outbox event tương ứng.

Nếu chỉ một thay đổi rollback, hãy kiểm tra hai framework có dùng cùng DataSource instance, transaction manager và MyBatis-Spring integration hay không.

### 13.3. Test type mapping hai chiều

Nếu enum/date/JSON/UUID có custom conversion, test riêng:

- Spring Data JDBC converter ghi đúng format.
- Spring Data JDBC đọc đúng format.
- MyBatis TypeHandler ghi đúng format.
- MyBatis TypeHandler đọc đúng format.
- Dữ liệu legacy được cả hai đường đọc hiểu nếu yêu cầu tương thích.

Không giả định custom converter đăng ký trong Spring Data JDBC được MyBatis sử dụng.

### 13.4. Dùng đúng database engine

H2 có thể hữu ích cho test nhanh, nhưng không thay thế hoàn toàn PostgreSQL/MySQL/SQL Server production. Dynamic SQL, type handler, JSON, stored procedure, CTE và kiểu dữ liệu vendor-specific nên được kiểm thử trên database tương ứng, thường qua Testcontainers.

## 14. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân | Hướng xử lý |
| --- | --- | --- |
| Mapper không được inject | Thiếu `@Mapper`/`@MapperScan` hoặc package scan sai. | Cấu hình mapper scanning rõ ràng. |
| Mapper và repository không rollback cùng nhau | Khác DataSource hoặc transaction manager; MyBatis không dùng Spring-managed session. | Dùng MyBatis-Spring/SqlSessionTemplate và chung transaction resource. |
| Gọi mapper commit riêng | Tự mở SqlSession hoặc gọi commit thủ công. | Để SqlSessionTemplate và Spring transaction quản lý. |
| Báo cáo trả dữ liệu cũ | Cache MyBatis chưa được invalidation sau khi Spring Data JDBC ghi. | Điều chỉnh local/second-level cache hoặc tắt cache cho query đó. |
| Aggregate thiếu child sau mapper update | MyBatis chỉ chạy SQL được viết, không đồng bộ aggregate. | Giữ aggregate write ở Spring Data JDBC hoặc tự quản lý toàn bộ invariant. |
| LastModified không đổi sau mapper UPDATE | MyBatis không chạy auditing callback Spring Data JDBC. | Cập nhật audit columns trong SQL hoặc trigger. |
| Optimistic locking bị bỏ qua | Mapper UPDATE không kiểm tra và tăng version. | Thêm version predicate, increment và kiểm tra row count. |
| Enum đọc khác nhau giữa hai framework | Spring converter và MyBatis TypeHandler có mapping riêng. | Định nghĩa/test hai chiều cho cả hai. |
| SQL XML không tìm thấy resource | `mapper-locations` sai hoặc XML không được đóng gói vào classpath. | Kiểm tra resource path trong artifact. |
| Sort động gây SQL injection | Dùng string substitution với input không được kiểm soát. | Dùng allowlist identifier; bind value bằng `#{...}`. |
| Test H2 pass nhưng production fail | Khác biệt dialect, type hoặc stored procedure. | Integration test với database production tương ứng. |
| Hai framework cùng ghi một aggregate | Ownership và invariant không được phân định. | Chọn một write path hoặc định nghĩa rõ direct SQL contract. |

## 15. Quy trình quyết định có nên phối hợp hay không

Trước khi thêm MyBatis vào ứng dụng Spring Data JDBC, hãy trả lời:

1. Query hiện tại có thể diễn đạt gọn bằng derived query hoặc `@Query` không?
2. Có nhu cầu thật sự về SQL phức tạp, dynamic SQL, stored procedure, legacy mapper hoặc DTO projection không?
3. Phần nào là aggregate write model và phần nào là read/reporting model?
4. Framework nào sở hữu thao tác ghi trên từng bảng/aggregate?
5. Nếu cả hai cùng tham gia một use case, chúng có dùng chung DataSource và transaction manager không?
6. Có converter/TypeHandler nào cần đồng bộ giữa hai framework không?
7. MyBatis cache có thể trả dữ liệu cũ sau khi Spring Data JDBC ghi không?
8. Direct SQL có cần tự cập nhật version, auditing hoặc child rows không?
9. Migration có cập nhật đồng thời mapping và mapper SQL không?
10. Integration test có chạy trên database tương ứng với production không?

Nếu lợi ích của SQL control/read model rõ ràng và ownership có thể phân định, phối hợp hai framework là hợp lý. Nếu chỉ cần CRUD và một vài query đơn giản, Spring Data JDBC thường đã đủ.

> **Spring Data JDBC phù hợp để quản lý aggregate và vòng đời ghi; MyBatis phù hợp khi cần kiểm soát SQL, dynamic query, legacy integration hoặc read model phức tạp.** Hãy phối hợp chúng khi mỗi công cụ có vai trò rõ ràng, chia quyền sở hữu đường ghi, dùng chung DataSource/transaction manager khi cần atomicity và kiểm thử cả mapping lẫn cache. Một database có thể được truy cập bởi cả hai framework, nhưng mỗi aggregate nên có quy tắc ghi nhất quán.

### Tài liệu tham khảo

- [Spring Data Relational — Spring Data JDBC](https://docs.spring.io/spring-data/relational/reference/jdbc.html): aggregate persistence, repository và mapping trong Spring Data JDBC.
- [Spring Data JDBC — Query Methods](https://docs.spring.io/spring-data/relational/reference/jdbc/query-methods.html): query derivation và SQL tùy chỉnh.
- [MyBatis — Java API](https://mybatis.org/mybatis-3/java-api.html): mapper, SqlSession và cách sử dụng MyBatis.
- [MyBatis — Mapper XML Files](https://mybatis.org/mybatis-3/sqlmap-xml.html): result mapping, dynamic SQL và mapper XML.
- [MyBatis-Spring — SqlSessionTemplate](https://mybatis.org/spring/sqlsession.html): tích hợp SqlSession với Spring transaction và quản lý session.
- [MyBatis-Spring — Transactions](https://mybatis.org/spring/transactions.html): tham gia transaction do Spring quản lý.
- [MyBatis Spring Boot Starter](https://mybatis.org/spring-boot-starter/mybatis-spring-boot-autoconfigure/): auto-configuration, mapper scanning và cấu hình MyBatis trong Spring Boot.
- [Spring Framework — Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction.html): transaction manager và declarative transaction.
