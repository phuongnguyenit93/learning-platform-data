# Join, projection và truy vấn phức tạp trong Repository tùy biến với Querydsl

Querydsl giúp xây dựng truy vấn có kiểu dữ liệu kiểm tra được ngay trong Java. Với Spring Data JPA, Querydsl JPA tạo truy vấn dựa trên entity và thuộc tính Java, sau đó chuyển thành JPQL để JPA provider thực thi. Khi truy vấn cần nhiều JOIN, bộ lọc tùy chọn, DTO projection, GROUP BY/HAVING hoặc phân trang có count query riêng, custom repository fragment thường là nơi phù hợp để gom logic đó.

Bài này dùng ví dụ tìm kiếm đơn hàng theo khách hàng, trạng thái và khoảng ngày; trả DTO thay vì entity; tổng hợp doanh thu theo khách hàng; và phân trang kết quả. Trọng tâm là cách tổ chức repository, tạo Q-type, xây dựng predicate động, chọn JOIN phù hợp, ánh xạ DTO và tránh lỗi nhân hàng khi JOIN collection.

## 1. Querydsl JPA giải quyết vấn đề gì?

JPQL là ngôn ngữ truy vấn theo entity. Có thể viết query bằng chuỗi trong `@Query`, nhưng khi điều kiện thay đổi theo request, việc ghép chuỗi hoặc duy trì nhiều query gần giống nhau nhanh chóng trở nên khó kiểm soát.

Querydsl cung cấp DSL Java để biểu diễn các phần của truy vấn:

- Entity và thuộc tính được biểu diễn bằng các lớp Q-type được sinh từ mapping.
- Predicate được tạo bằng biểu thức có kiểu, chẳng hạn `order.status.eq(status)`.
- JOIN, GROUP BY, HAVING, ORDER BY, projection và giới hạn kết quả được viết theo cấu trúc truy vấn.
- Tham số giá trị được bind bởi provider; không cần nối input thành chuỗi JPQL/SQL.
- IDE và compiler có thể phát hiện nhiều lỗi sai tên thuộc tính hoặc sai kiểu trước khi chạy.

Với Querydsl JPA, query vẫn tuân theo ngữ nghĩa JPQL/JPA và được thực thi bởi provider như Hibernate. Querydsl không biến query thành SQL đặc thù database. Nếu cần SQL thuần, CTE hoặc tính năng riêng của database, cần cân nhắc Querydsl SQL hoặc native query.

## 2. Khi nào dùng QuerydslPredicateExecutor và khi nào cần custom repository?

Spring Data JPA cung cấp hai cách tích hợp thường gặp.

### 2.1. QuerydslPredicateExecutor cho truy vấn repository đơn giản

Repository có thể mở rộng `QuerydslPredicateExecutor`:

~~~java
public interface PurchaseOrderRepository
        extends JpaRepository<PurchaseOrder, Long>,
                QuerydslPredicateExecutor<PurchaseOrder> {
}
~~~

Sau đó tạo predicate và gọi:

~~~java
QPurchaseOrder order = QPurchaseOrder.purchaseOrder;

BooleanBuilder predicate = new BooleanBuilder();
predicate.and(order.status.eq(OrderStatus.PAID));

Iterable<PurchaseOrder> result =
        repository.findAll(predicate);
~~~

Cách này tiện khi cần tìm entity theo predicate và dùng các thao tác repository chuẩn. Tuy nhiên, các truy vấn cần DTO projection phức tạp, nhiều JOIN có điều kiện, GROUP BY/HAVING, count query tùy chỉnh hoặc quy tắc phân trang riêng thường cần quyền kiểm soát rõ hơn.

### 2.2. Custom repository fragment cho truy vấn phức tạp

Tạo interface fragment mô tả các use case:

~~~java
public interface PurchaseOrderQueryRepository {

    Page<OrderSummary> search(OrderSearchFilter filter, Pageable pageable);

    List<CustomerSpend> summarizePaidOrders(
            Instant from,
            Instant to,
            BigDecimal minimumSpend);
}
~~~

Repository chính kết hợp fragment đó:

~~~java
public interface PurchaseOrderRepository
        extends JpaRepository<PurchaseOrder, Long>,
                PurchaseOrderQueryRepository {
}
~~~

Spring Data ghép implementation fragment vào repository. Tên implementation theo convention là `PurchaseOrderQueryRepositoryImpl`:

~~~java
@Repository
public class PurchaseOrderQueryRepositoryImpl
        implements PurchaseOrderQueryRepository {

    private final JPAQueryFactory queryFactory;

    public PurchaseOrderQueryRepositoryImpl(
            JPAQueryFactory queryFactory) {
        this.queryFactory = queryFactory;
    }

    // Implement các phương thức truy vấn tại đây.
}
~~~

Đây là cách tổ chức phù hợp khi query có logic riêng nhưng vẫn muốn giữ API repository của Spring Data. Không cần đặt tất cả query phức tạp trong một service hoặc tạo một repository hoàn toàn tách khỏi Spring Data.

## 3. Cấu hình Querydsl JPA và sinh Q-type

Q-type như `QPurchaseOrder` và `QCustomer` được annotation processor sinh từ entity. Không tự viết hoặc chỉnh sửa các lớp Q được sinh.

Ví dụ dưới đây dùng Querydsl 5.1.0 với Jakarta Persistence, phù hợp với dự án Spring Boot 3/Jakarta. Nếu dự án dùng Spring Boot 2 hoặc JPA namespace `javax.persistence`, phải dùng artifact/classifier và phiên bản tương thích namespace đó. Hãy kiểm tra Spring Data JPA, Querydsl và JDK đang dùng trước khi sao chép cấu hình.

### 3.1. Maven

Dependency runtime/compile:

~~~xml
<properties>
    <querydsl.version>5.1.0</querydsl.version>
</properties>

<dependencies>
    <dependency>
        <groupId>com.querydsl</groupId>
        <artifactId>querydsl-jpa</artifactId>
        <version>${querydsl.version}</version>
        <classifier>jakarta</classifier>
    </dependency>
</dependencies>
~~~

Cấu hình annotation processor trong Maven Compiler Plugin:

~~~xml
<build>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-compiler-plugin</artifactId>
            <version>3.13.0</version>
            <configuration>
                <annotationProcessorPaths>
                    <path>
                        <groupId>com.querydsl</groupId>
                        <artifactId>querydsl-apt</artifactId>
                        <version>${querydsl.version}</version>
                        <classifier>jakarta</classifier>
                    </path>
                    <path>
                        <groupId>jakarta.persistence</groupId>
                        <artifactId>jakarta.persistence-api</artifactId>
                        <version>3.1.0</version>
                    </path>
                </annotationProcessorPaths>
            </configuration>
        </plugin>
    </plugins>
</build>
~~~

Trong dự án thực tế, dùng phiên bản Jakarta Persistence do Spring Boot dependency management quản lý để tránh lệch phiên bản API. Annotation processor cần nhìn thấy các annotation persistence mà entity đang sử dụng.

### 3.2. Gradle

Với Gradle, khai báo Querydsl JPA và annotation processor tương ứng:

~~~groovy
dependencies {
    implementation "com.querydsl:querydsl-jpa:5.1.0:jakarta"

    annotationProcessor "com.querydsl:querydsl-apt:5.1.0:jakarta"
    annotationProcessor "jakarta.persistence:jakarta.persistence-api:3.1.0"
}
~~~

Nếu project có test source dùng entity riêng, cấu hình annotation processor cho source set test theo nhu cầu.

### 3.3. Kiểm tra Q-type đã được sinh

Sau khi build, tìm các lớp Q trong thư mục generated sources, thường là:

- Maven: `target/generated-sources/annotations`.
- Gradle: `build/generated/sources/annotationProcessor/java/main`.

Ví dụ entity:

~~~java
@Entity
public class Customer {

    @Id
    private Long id;

    private String name;
}
~~~

Q-type được sinh có thể được sử dụng như sau:

~~~java
QCustomer customer = QCustomer.customer;

NumberPath<Long> idPath = customer.id;
StringPath namePath = customer.name;
~~~

Không sửa Q-type bằng tay. Nếu thiếu Q-type, kiểm tra annotation processor, classifier Jakarta/Javax, source set và việc entity có annotation JPA hợp lệ hay không.

## 4. Cấu hình JPAQueryFactory

`JPAQueryFactory` là điểm khởi đầu để tạo truy vấn Querydsl JPA. Có thể khai báo bean:

~~~java
@Configuration
public class QuerydslConfiguration {

    @Bean
    JPAQueryFactory jpaQueryFactory(EntityManager entityManager) {
        return new JPAQueryFactory(entityManager);
    }
}
~~~

Trong Spring, EntityManager được inject thường là proxy quản lý theo transaction. Querydsl dùng EntityManager đó khi thực thi query.

Custom repository implementation nhận factory qua constructor:

~~~java
@Repository
public class PurchaseOrderQueryRepositoryImpl
        implements PurchaseOrderQueryRepository {

    private final JPAQueryFactory queryFactory;

    public PurchaseOrderQueryRepositoryImpl(
            JPAQueryFactory queryFactory) {
        this.queryFactory = queryFactory;
    }
}
~~~

Không tự tạo EntityManager mới cho mỗi method và không giữ một EntityManager thủ công qua nhiều thread. Hãy để Spring quản lý persistence context và transaction.

## 5. Mô hình ví dụ

Ta dùng hai entity:

- `Customer` có `id`, `name` và quan hệ One-to-Many đến đơn hàng.
- `PurchaseOrder` có `id`, `status`, `createdAt`, `total` và Many-to-One đến customer.

### 5.1. Enum trạng thái

~~~java
public enum OrderStatus {
    NEW,
    PAID,
    CANCELLED,
    COMPLETED
}
~~~

### 5.2. Entity Customer

~~~java
@Entity
@Table(name = "customers")
public class Customer {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, length = 120)
    private String name;

    @OneToMany(mappedBy = "customer")
    private List<PurchaseOrder> orders = new ArrayList<>();

    protected Customer() {
    }

    public Customer(String name) {
        this.name = name;
    }

    public Long getId() {
        return id;
    }

    public String getName() {
        return name;
    }
}
~~~

### 5.3. Entity PurchaseOrder

~~~java
@Entity
@Table(name = "purchase_orders")
public class PurchaseOrder {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false)
    private OrderStatus status;

    @Column(nullable = false)
    private Instant createdAt;

    @Column(nullable = false, precision = 14, scale = 2)
    private BigDecimal total;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "customer_id", nullable = false)
    private Customer customer;

    protected PurchaseOrder() {
    }

    public PurchaseOrder(
            OrderStatus status,
            Instant createdAt,
            BigDecimal total,
            Customer customer) {
        this.status = status;
        this.createdAt = createdAt;
        this.total = total;
        this.customer = customer;
    }

    public Long getId() {
        return id;
    }

    public OrderStatus getStatus() {
        return status;
    }

    public Instant getCreatedAt() {
        return createdAt;
    }

    public BigDecimal getTotal() {
        return total;
    }

    public Customer getCustomer() {
        return customer;
    }
}
~~~

Các entity này là ví dụ tối giản. Một dự án có thể có constructor, auditing, tenant ID hoặc các trường bắt buộc khác; hãy điều chỉnh fixture và mapping theo mô hình thật.

## 6. Xây dựng DTO projection

Kết quả tìm kiếm danh sách không cần trả entity đầy đủ. Ta tạo DTO:

~~~java
public record OrderSummary(
        Long id,
        String customerName,
        OrderStatus status,
        Instant createdAt,
        BigDecimal total) {
}
~~~

Với Querydsl, có nhiều cách projection.

### 6.1. Projections.constructor

~~~java
.select(Projections.constructor(
        OrderSummary.class,
        order.id,
        customer.name,
        order.status,
        order.createdAt,
        order.total
))
~~~

Querydsl gọi constructor phù hợp. Cách này gọn, dùng được với record hoặc DTO có constructor tương ứng, nhưng việc khớp kiểu/thứ tự được xác nhận khi query được thực thi chứ không có Q-type DTO kiểm tra toàn bộ constructor tại compile time.

Thứ tự biểu thức phải khớp thứ tự tham số DTO. Nếu đổi kiểu hoặc thứ tự trường mà quên cập nhật projection, lỗi có thể xuất hiện khi chạy query.

### 6.2. Projections.bean và Projections.fields

`Projections.bean` ánh xạ theo tên property và cần setter hoặc cơ chế bean phù hợp:

~~~java
.select(Projections.bean(
        OrderSummaryBean.class,
        order.id.as("id"),
        customer.name.as("customerName"),
        order.status.as("status"),
        order.createdAt.as("createdAt"),
        order.total.as("total")
))
~~~

`Projections.fields` ánh xạ vào field theo tên:

~~~java
.select(Projections.fields(
        OrderSummaryFields.class,
        order.id.as("id"),
        customer.name.as("customerName"),
        order.status.as("status"),
        order.createdAt.as("createdAt"),
        order.total.as("total")
))
~~~

Hai cách này yêu cầu alias khớp tên property/field của DTO. Chúng thuận tiện với DTO mutable nhưng phụ thuộc quy tắc reflection và cấu trúc class. Không dùng chúng với DTO bất biến chỉ có constructor nếu không có field/setter tương ứng.

### 6.3. @QueryProjection để kiểm tra constructor mạnh hơn

Có thể annotate constructor DTO bằng `@QueryProjection`:

~~~java
public class OrderSummaryView {

    private final Long id;
    private final String customerName;
    private final OrderStatus status;
    private final Instant createdAt;
    private final BigDecimal total;

    @QueryProjection
    public OrderSummaryView(
            Long id,
            String customerName,
            OrderStatus status,
            Instant createdAt,
            BigDecimal total) {
        this.id = id;
        this.customerName = customerName;
        this.status = status;
        this.createdAt = createdAt;
        this.total = total;
    }

    public Long getId() {
        return id;
    }

    public String getCustomerName() {
        return customerName;
    }

    public OrderStatus getStatus() {
        return status;
    }

    public Instant getCreatedAt() {
        return createdAt;
    }

    public BigDecimal getTotal() {
        return total;
    }
}
~~~

Annotation processor sinh `QOrderSummaryView`. Query có thể viết:

~~~java
.select(new QOrderSummaryView(
        order.id,
        customer.name,
        order.status,
        order.createdAt,
        order.total
))
~~~

Cách này kiểm tra kiểu và thứ tự constructor ngay khi compile. Đổi lại, DTO phải phụ thuộc annotation Querydsl và cần annotation processor sinh Q DTO. Nếu muốn DTO không phụ thuộc Querydsl, dùng `Projections.constructor`.

## 7. JOIN trong Querydsl JPA

JOIN cho phép truy vấn theo quan hệ entity và chọn trường từ nhiều entity.

### 7.1. Inner join

~~~java
QPurchaseOrder order = QPurchaseOrder.purchaseOrder;
QCustomer customer = QCustomer.customer;

List<OrderSummary> result = queryFactory
        .select(Projections.constructor(
                OrderSummary.class,
                order.id,
                customer.name,
                order.status,
                order.createdAt,
                order.total
        ))
        .from(order)
        .join(order.customer, customer)
        .where(order.status.eq(OrderStatus.PAID))
        .fetch();
~~~

`join(order.customer, customer)` là inner join. Chỉ đơn hàng có customer phù hợp mới xuất hiện. Vì ví dụ entity đặt `optional = false`, đây là quan hệ bắt buộc.

### 7.2. Left join

Nếu quan hệ có thể null hoặc muốn giữ hàng bên trái khi không có bản ghi liên quan, dùng:

~~~java
.leftJoin(order.customer, customer)
~~~

Khi đó `customer.name` có thể null. DTO phải dùng kiểu tham chiếu chấp nhận null và caller cần xử lý trường hợp đó.

Đừng chuyển LEFT JOIN thành điều kiện WHERE trên bảng bên phải nếu vẫn muốn giữ hàng không có quan hệ. Ví dụ:

~~~java
.leftJoin(order.customer, customer)
.where(customer.name.containsIgnoreCase(keyword))
~~~

Điều kiện WHERE loại hàng mà `customer.name` là null, khiến kết quả có ngữ nghĩa gần như inner join. Nếu cần giữ hàng bên trái và giới hạn hàng bên phải, cân nhắc điều kiện trong `on(...)`:

~~~java
.leftJoin(order.customer, customer)
.on(customer.name.startsWithIgnoreCase(prefix))
~~~

Cần phân biệt điều kiện lọc entity gốc với điều kiện giới hạn hàng được ghép từ phía JOIN.

### 7.3. Join nhiều cấp

Querydsl cho phép nối qua nhiều quan hệ:

~~~java
QPurchaseOrder order = QPurchaseOrder.purchaseOrder;
QCustomer customer = QCustomer.customer;
QDepartment department = QDepartment.department;

List<Tuple> rows = queryFactory
        .select(order.id, customer.name, department.name)
        .from(order)
        .join(order.customer, customer)
        .join(customer.department, department)
        .fetch();
~~~

Mỗi alias Q-type cần đại diện cho một đường đi trong query. Nếu cùng một entity type được JOIN hai lần với hai vai trò khác nhau, tạo alias riêng bằng constructor của Q-type, ví dụ `new QCustomer("buyer")` và `new QCustomer("approver")`.

## 8. Fetch join khác JOIN thông thường

JOIN thông thường dùng để lọc hoặc lấy biểu thức từ entity liên quan. Fetch join yêu cầu provider tải association cùng entity gốc:

~~~java
List<PurchaseOrder> orders = queryFactory
        .selectFrom(order)
        .join(order.customer, customer).fetchJoin()
        .where(order.status.eq(OrderStatus.PAID))
        .fetch();
~~~

Fetch join hữu ích khi caller cần entity PurchaseOrder cùng Customer trong persistence context. Nó có thể tránh N+1 khi truy cập quan hệ ToOne.

Khi chỉ cần DTO, thường dùng JOIN thông thường và chọn các biểu thức DTO. Không thêm `fetchJoin()` vào query DTO với kỳ vọng giảm cột; fetch join là chỉ dẫn tải association của entity được chọn, không phải cơ chế projection.

### 8.1. Fetch join collection và phân trang

Fetch join một collection ToMany có thể nhân hàng SQL. Nếu một customer có 10 đơn hàng, JOIN collection có thể tạo 10 hàng cho cùng customer. Kết hợp fetch join collection với offset/limit có thể làm phân trang sai cấp entity hoặc buộc Hibernate lấy nhiều hàng rồi phân trang trong memory, tùy provider/version.

Các quy tắc:

- Fetch join ToOne thường ít gây nhân hàng hơn nếu quan hệ thực sự duy nhất.
- Tránh phân trang trực tiếp trên query fetch join collection.
- Dùng DTO projection khi chỉ cần trường từ nhiều bảng.
- Nếu cần entity root và collection, phân trang ID root trước, sau đó fetch collection cho nhóm ID đó.
- Kiểm tra log và cảnh báo Hibernate; không bỏ qua cảnh báo phân trang collection fetch.

## 9. Predicate động bằng BooleanBuilder

Bộ lọc tìm kiếm thường có các trường tùy chọn. Không cần tạo một query riêng cho từng tổ hợp; xây dựng predicate từ những điều kiện thực sự được cung cấp.

DTO bộ lọc:

~~~java
public record OrderSearchFilter(
        OrderStatus status,
        String customerName,
        Instant createdFrom,
        Instant createdTo,
        BigDecimal minimumTotal) {
}
~~~

Hàm tạo predicate:

~~~java
private BooleanBuilder buildPredicate(OrderSearchFilter filter) {
    QPurchaseOrder order = QPurchaseOrder.purchaseOrder;
    QCustomer customer = QCustomer.customer;

    BooleanBuilder where = new BooleanBuilder();

    if (filter.status() != null) {
        where.and(order.status.eq(filter.status()));
    }

    if (filter.customerName() != null
            && !filter.customerName().isBlank()) {
        where.and(customer.name.containsIgnoreCase(
                filter.customerName().trim()));
    }

    if (filter.createdFrom() != null) {
        where.and(order.createdAt.goe(filter.createdFrom()));
    }

    if (filter.createdTo() != null) {
        where.and(order.createdAt.lt(filter.createdTo()));
    }

    if (filter.minimumTotal() != null) {
        where.and(order.total.goe(filter.minimumTotal()));
    }

    return where;
}
~~~

Predicate dùng khoảng thời gian nửa mở: `createdAt >= from` và `createdAt < to`. Cách này giúp chia các khoảng liền nhau mà không đếm trùng thời điểm ở biên.

Trong implementation query, JOIN customer được khai báo nếu predicate hoặc projection cần trường customer. Không nên thêm JOIN tùy tiện khi không cần, vì nó có thể ảnh hưởng số hàng và kế hoạch thực thi.

### 9.1. Predicate bắt buộc và điều kiện tùy chọn

Nếu ứng dụng multi-tenant, tenant ID là điều kiện bảo mật bắt buộc, không được xem như một filter tùy chọn:

~~~java
where.and(order.tenantId.eq(currentTenantId));
~~~

Lấy tenant từ ngữ cảnh xác thực đáng tin cậy, không tin một tenant ID tùy ý do client truyền lên. Hãy luôn thêm predicate tenant vào query trước khi thêm các điều kiện tìm kiếm tùy chọn.

### 9.2. Không nối input thành chuỗi query

Querydsl bind các giá trị qua biểu thức. Tránh tự dựng JPQL/SQL bằng cách ghép chuỗi từ keyword hoặc filter. Tên cột và đường dẫn sort vẫn là cấu trúc query, không phải bind parameter; nếu cho client chọn sort, ánh xạ qua whitelist thuộc tính đã hỗ trợ.

## 10. Hoàn chỉnh custom repository search với DTO và Pageable

Ta triển khai `search` trong `PurchaseOrderQueryRepositoryImpl`. Ví dụ dùng thứ tự mặc định theo thời gian giảm dần và ID giảm dần để ổn định các hàng có cùng thời điểm.

~~~java
@Repository
public class PurchaseOrderQueryRepositoryImpl
        implements PurchaseOrderQueryRepository {

    private final JPAQueryFactory queryFactory;

    public PurchaseOrderQueryRepositoryImpl(
            JPAQueryFactory queryFactory) {
        this.queryFactory = queryFactory;
    }

    @Override
    public Page<OrderSummary> search(
            OrderSearchFilter filter,
            Pageable pageable) {

        QPurchaseOrder order = QPurchaseOrder.purchaseOrder;
        QCustomer customer = QCustomer.customer;

        BooleanBuilder where = buildPredicate(filter);

        List<OrderSummary> content = queryFactory
                .select(Projections.constructor(
                        OrderSummary.class,
                        order.id,
                        customer.name,
                        order.status,
                        order.createdAt,
                        order.total
                ))
                .from(order)
                .leftJoin(order.customer, customer)
                .where(where)
                .orderBy(order.createdAt.desc(), order.id.desc())
                .offset(pageable.getOffset())
                .limit(pageable.getPageSize())
                .fetch();

        Long count = queryFactory
                .select(order.id.count())
                .from(order)
                .leftJoin(order.customer, customer)
                .where(where)
                .fetchOne();

        long total = count == null ? 0L : count;

        return new PageImpl<>(content, pageable, total);
    }

    private BooleanBuilder buildPredicate(OrderSearchFilter filter) {
        QPurchaseOrder order = QPurchaseOrder.purchaseOrder;
        QCustomer customer = QCustomer.customer;

        BooleanBuilder where = new BooleanBuilder();

        if (filter.status() != null) {
            where.and(order.status.eq(filter.status()));
        }

        if (filter.customerName() != null
                && !filter.customerName().isBlank()) {
            where.and(customer.name.containsIgnoreCase(
                    filter.customerName().trim()));
        }

        if (filter.createdFrom() != null) {
            where.and(order.createdAt.goe(filter.createdFrom()));
        }

        if (filter.createdTo() != null) {
            where.and(order.createdAt.lt(filter.createdTo()));
        }

        if (filter.minimumTotal() != null) {
            where.and(order.total.goe(filter.minimumTotal()));
        }

        return where;
    }
}
~~~

Đây là ví dụ cho quan hệ ToOne. Query content và count cùng dùng một predicate để tránh tổng số kết quả không khớp nội dung trang.

Các phần quan trọng:

- `select(Projections.constructor(...))` trả DTO.
- `leftJoin` giữ đơn hàng khi customer có thể vắng mặt.
- `where(where)` áp dụng cùng bộ lọc động.
- `orderBy` có ID làm tie-breaker để phân trang ổn định.
- `offset` và `limit` áp dụng từ `Pageable`.
- Count query chỉ đếm đơn hàng, không cần SELECT các cột DTO.
- `PageImpl` kết hợp content, pageable và tổng số hàng.

Để giữ ví dụ tập trung, code đang dùng sort cố định. Nếu muốn hỗ trợ `pageable.getSort()`, phải ánh xạ từng property được phép sang Q-path tương ứng; không truyền tên cột tùy ý từ request vào query.

## 11. Xử lý Sort bằng whitelist

Không nên bỏ qua Sort trong Pageable mà không thông báo cho caller. Có hai lựa chọn: quy định repository chỉ hỗ trợ một sort cố định, hoặc hỗ trợ một tập sort đã định nghĩa.

Ví dụ mapper đơn giản:

~~~java
private OrderSpecifier<?>[] toOrderSpecifiers(
        Sort sort,
        QPurchaseOrder order,
        QCustomer customer) {

    if (sort.isUnsorted()) {
        return new OrderSpecifier<?>[] {
                order.createdAt.desc(),
                order.id.desc()
        };
    }

    List<OrderSpecifier<?>> result = new ArrayList<>();

    for (Sort.Order item : sort) {
        boolean ascending = item.isAscending();

        switch (item.getProperty()) {
            case "id" -> result.add(
                    ascending ? order.id.asc() : order.id.desc());

            case "createdAt" -> result.add(
                    ascending
                            ? order.createdAt.asc()
                            : order.createdAt.desc());

            case "total" -> result.add(
                    ascending ? order.total.asc() : order.total.desc());

            case "customerName" -> result.add(
                    ascending ? customer.name.asc()
                              : customer.name.desc());

            default -> throw new IllegalArgumentException(
                    "Unsupported sort property: " + item.getProperty());
        }
    }

    return result.toArray(OrderSpecifier[]::new);
}
~~~

Ý tưởng quan trọng là chỉ cho phép sort theo property được định nghĩa. Trong production, hãy bảo đảm thứ tự cuối có tie-breaker duy nhất như ID, kể cả khi client gửi một sort khác. Nếu sort đã có ID thì không thêm lần nữa.

Nếu không muốn hỗ trợ dynamic sort, hãy từ chối Sort không được hỗ trợ hoặc ghi rõ hợp đồng rằng query dùng thứ tự cố định. Đừng âm thầm trả thứ tự khác với yêu cầu của client.

## 12. JOIN collection: duplicate rows và count distinct

JOIN ToMany là nơi query phức tạp thường sai.

Giả sử thêm OrderLine và một đơn hàng có nhiều dòng hàng. Query:

~~~java
.from(order)
.join(order.lines, line)
.where(line.productName.containsIgnoreCase(keyword))
~~~

có thể tạo nhiều hàng cho cùng một order nếu nhiều dòng hàng cùng khớp. Nếu SELECT DTO có một hàng cho mỗi line, kết quả lặp order là đúng theo grain của query. Nếu use case cần một hàng cho mỗi order, phải xử lý trùng.

### 12.1. Dùng exists/subquery khi chỉ cần kiểm tra có dòng hàng phù hợp

Nếu chỉ muốn lấy đơn hàng có ít nhất một dòng thỏa điều kiện, biểu diễn bằng EXISTS có thể tránh nhân hàng ở query chính:

~~~java
QOrderLine line = QOrderLine.orderLine;

BooleanExpression hasMatchingLine =
        JPAExpressions
                .selectOne()
                .from(line)
                .where(
                        line.purchaseOrder.eq(order),
                        line.productName.containsIgnoreCase(keyword)
                )
                .exists();

List<OrderSummary> result = queryFactory
        .select(Projections.constructor(
                OrderSummary.class,
                order.id,
                customer.name,
                order.status,
                order.createdAt,
                order.total
        ))
        .from(order)
        .leftJoin(order.customer, customer)
        .where(hasMatchingLine)
        .fetch();
~~~

Query chính vẫn có một hàng cho mỗi order nếu các JOIN còn lại không nhân hàng. Đây thường là cách phù hợp khi quan hệ con chỉ dùng để lọc sự tồn tại.

### 12.2. Count query phải đếm đúng grain

Nếu content query JOIN collection và có nhiều hàng cho một order, `order.id.count()` đếm số hàng join, không phải số order duy nhất.

Có thể dùng:

~~~java
.select(order.id.countDistinct())
~~~

Tuy nhiên, chỉ thay count thành distinct là chưa đủ nếu content query vẫn trả duplicate DTO. Cần quyết định rõ kết quả muốn một hàng cho mỗi order hay một hàng cho mỗi order-line, rồi thiết kế SELECT và count theo cùng grain.

### 12.3. Phân trang hai bước cho collection

Khi cần Page<Order> và dữ liệu collection:

1. Query ID của các order duy nhất theo filter, order và pageable.
2. Query DTO/entity cùng collection cho danh sách ID vừa lấy.
3. Count số order duy nhất bằng count distinct hoặc query phù hợp.
4. Giữ thứ tự ID của bước đầu khi dựng kết quả cuối, vì `IN (...)` không tự bảo đảm thứ tự.

Cách này tránh phân trang trực tiếp trên hàng JOIN bị nhân. Với DTO đơn giản, có thể chỉ cần bước một lấy ID và bước hai lấy các trường liên quan.

## 13. GROUP BY, HAVING và projection tổng hợp

Querydsl hỗ trợ aggregate expression và grouping trong JPQL.

Ví dụ cần thống kê số đơn hàng đã thanh toán và tổng chi tiêu theo khách hàng.

DTO:

~~~java
public record CustomerSpend(
        Long customerId,
        String customerName,
        Long orderCount,
        BigDecimal totalSpent) {
}
~~~

Query:

~~~java
@Override
public List<CustomerSpend> summarizePaidOrders(
        Instant from,
        Instant to,
        BigDecimal minimumSpend) {

    QPurchaseOrder order = QPurchaseOrder.purchaseOrder;
    QCustomer customer = QCustomer.customer;

    NumberExpression<Long> orderCount = order.id.count();
    NumberExpression<BigDecimal> totalSpent = order.total.sum();

    return queryFactory
            .select(Projections.constructor(
                    CustomerSpend.class,
                    customer.id,
                    customer.name,
                    orderCount,
                    totalSpent
            ))
            .from(order)
            .join(order.customer, customer)
            .where(
                    order.status.eq(OrderStatus.PAID),
                    order.createdAt.goe(from),
                    order.createdAt.lt(to)
            )
            .groupBy(customer.id, customer.name)
            .having(totalSpent.goe(minimumSpend))
            .orderBy(totalSpent.desc(), customer.id.asc())
            .fetch();
}
~~~

Giải thích:

- `count()` trả số đơn hàng theo từng nhóm.
- `sum()` cộng tổng tiền đơn hàng.
- `groupBy(customer.id, customer.name)` tạo một nhóm cho mỗi customer.
- `having(...)` lọc sau khi đã tổng hợp.
- `orderBy(totalSpent.desc(), customer.id.asc())` sắp xếp theo tổng chi tiêu, dùng ID làm tie-breaker.

`WHERE` lọc các hàng trước khi nhóm; `HAVING` lọc nhóm sau aggregate. Không đặt điều kiện tổng tiền nhóm vào WHERE.

Ví dụ dùng inner join nên chỉ khách hàng có đơn PAID trong khoảng thời gian mới xuất hiện. Nếu cần bao gồm khách hàng chưa có đơn, bắt đầu query từ Customer và LEFT JOIN orders với điều kiện trạng thái/ngày trong `on(...)`, rồi xử lý giá trị aggregate null.

### 13.1. Cẩn thận aggregate khi JOIN nhiều collection

Nếu query cùng lúc JOIN order và lines, mỗi order có nhiều line. Khi đó `sum(order.total)` có thể bị cộng lặp theo số dòng hàng. `count(order.id)` cũng có thể đếm trùng.

Cần xác định grain trước khi aggregate:

- Tổng tiền theo order: tránh JOIN ToMany hoặc dùng subquery phù hợp.
- Tổng tiền theo line: sum biểu thức của line.
- Số order: count distinct order ID khi JOIN có thể nhân hàng.
- Tổng theo customer từ nhiều bảng: cân nhắc tổng hợp từng nguồn riêng rồi kết hợp kết quả.

Không sửa số liệu sai bằng cách thêm distinct một cách máy móc. `SUM(DISTINCT order.total)` cũng không đúng nếu hai đơn hàng khác nhau có cùng tổng tiền; nó loại các giá trị tiền trùng chứ không loại các order trùng.

## 14. Querydsl GroupBy transform và khi nào nên dùng

Querydsl có `GroupBy` result transformer để gom các hàng phẳng thành cấu trúc object lồng nhau trong Java. Nó hữu ích khi muốn tạo DTO có collection con từ kết quả JOIN.

Ví dụ khái niệm:

~~~java
Map<Long, CustomerOrdersDto> grouped = queryFactory
        .from(order)
        .join(order.customer, customer)
        .transform(
                GroupBy.groupBy(customer.id).as(
                        Projections.constructor(
                                CustomerOrdersDto.class,
                                customer.id,
                                customer.name,
                                GroupBy.list(
                                        Projections.constructor(
                                                OrderItemDto.class,
                                                order.id,
                                                order.total
                                        )
                                )
                        )
                )
        );
~~~

Đoạn code minh họa ý tưởng grouping trong Querydsl; constructor và kiểu collection DTO phải được điều chỉnh theo projection/transformer mà phiên bản Querydsl đang dùng. Transformer gom dữ liệu đã fetch vào bộ nhớ Java, không thay thế GROUP BY của database. Nếu query trả về hàng triệu dòng, grouping phía JVM vẫn có thể tiêu tốn nhiều heap.

Dùng SQL/JPQL aggregate khi có thể để database tính toán. Dùng GroupBy transform khi cần dựng cấu trúc object từ một tập kết quả đã được giới hạn hợp lý và lợi ích về số query đáng kể.

## 15. Subquery và truy vấn phức tạp

Querydsl JPA hỗ trợ subquery thông qua `JPAExpressions`. Ví dụ lấy đơn hàng có tổng tiền cao hơn trung bình đơn hàng trong cùng trạng thái:

~~~java
QPurchaseOrder order = QPurchaseOrder.purchaseOrder;
QPurchaseOrder other = new QPurchaseOrder("other");

JPQLQuery<BigDecimal> averageForStatus =
        JPAExpressions
                .select(other.total.avg())
                .from(other)
                .where(other.status.eq(order.status));

List<PurchaseOrder> aboveAverage = queryFactory
        .selectFrom(order)
        .where(order.total.gt(averageForStatus))
        .fetch();
~~~

Subquery tương quan tham chiếu alias bên ngoài (`order.status`). Dùng alias khác cho entity bên trong để tránh nhầm đường dẫn.

Subquery giúp giữ logic trong một truy vấn, nhưng không phải lúc nào cũng nhanh hơn JOIN. Kiểm tra execution plan, index và cardinality trên database thực tế.

## 16. Tối ưu query và tránh các lỗi hiệu năng

### 16.1. Chỉ JOIN khi cần

JOIN thêm bảng có thể tăng chi phí và nhân hàng. Chỉ khai báo JOIN nếu dùng thuộc tính bảng đó trong projection, predicate, grouping hoặc order.

### 16.2. Chọn đúng loại JOIN

- `join(...)`: chỉ giữ hàng có association phù hợp.
- `leftJoin(...)`: giữ hàng bên trái dù không có association.
- `on(...)`: giới hạn hàng ghép ở phía JOIN.
- `fetchJoin()`: tải association của entity được chọn, không phải cách tối ưu DTO.

### 16.3. Tránh N+1

Nếu trả entity rồi truy cập quan hệ lazy trong vòng lặp, có thể phát thêm một query cho mỗi entity. Dùng DTO projection với JOIN tường minh hoặc fetch plan phù hợp khi cần entity.

### 16.4. Index theo predicate và JOIN

Với query tìm theo status, createdAt và customer_id, đánh giá index phù hợp theo workload, chẳng hạn index kết hợp `(status, created_at)` hoặc index cho FK `customer_id`. Thứ tự cột trong composite index cần dựa vào selectivity và query pattern; không áp dụng một index mẫu cho mọi database.

### 16.5. Không fetch join collection khi phân trang

Dùng hai bước: page ID trước, sau đó load projection/entity cho ID. Cách này làm rõ số entity mỗi trang và tránh limit trên hàng join bị nhân.

### 16.6. Đo query thật

Bật SQL logging trong môi trường phát triển, dùng Hibernate Statistics hoặc datasource proxy để đếm query, rồi chạy `EXPLAIN` trên database. Querydsl DSL dễ đọc không đảm bảo SQL sinh ra luôn tối ưu.

## 17. Kiểm thử custom repository

Kiểm thử cần xác nhận cả nội dung DTO, predicate động, JOIN, aggregate và count query.

Ví dụ với `@DataJpaTest`:

~~~java
@DataJpaTest
class PurchaseOrderQueryRepositoryTest {

    @Autowired
    private TestEntityManager entityManager;

    @Autowired
    private PurchaseOrderRepository orders;

    @Test
    void searchFiltersAndProjectsOrders() {
        Customer customer = new Customer("An Nguyen");
        entityManager.persist(customer);

        entityManager.persist(new PurchaseOrder(
                OrderStatus.PAID,
                Instant.parse("2026-02-10T10:00:00Z"),
                new BigDecimal("120.00"),
                customer
        ));

        entityManager.persist(new PurchaseOrder(
                OrderStatus.CANCELLED,
                Instant.parse("2026-02-11T10:00:00Z"),
                new BigDecimal("80.00"),
                customer
        ));

        entityManager.flush();
        entityManager.clear();

        OrderSearchFilter filter = new OrderSearchFilter(
                OrderStatus.PAID,
                "An",
                Instant.parse("2026-02-01T00:00:00Z"),
                Instant.parse("2026-03-01T00:00:00Z"),
                new BigDecimal("100.00")
        );

        Page<OrderSummary> page = orders.search(
                filter,
                PageRequest.of(0, 10)
        );

        assertThat(page.getContent()).hasSize(1);
        assertThat(page.getTotalElements()).isEqualTo(1);

        OrderSummary summary = page.getContent().get(0);
        assertThat(summary.customerName()).isEqualTo("An Nguyen");
        assertThat(summary.status()).isEqualTo(OrderStatus.PAID);
        assertThat(summary.total())
                .isEqualByComparingTo("120.00");
    }
}
~~~

Test giả định entity và constructors tương ứng với phần mô hình. `flush()` ghi fixture xuống database, `clear()` buộc query lấy dữ liệu từ database thay vì dựa vào persistence context còn managed.

Nên bổ sung test cho:

- Không truyền filter tùy chọn và kết quả có đúng phạm vi.
- Customer null nếu mapping cho phép.
- Tên khách hàng không khớp.
- Ngày đúng tại `from` và đúng tại `to` để kiểm tra khoảng nửa mở.
- Nhiều order có cùng createdAt để kiểm tra tie-breaker ID.
- Page thứ hai không lặp hàng.
- JOIN ToMany có nhiều dòng khớp để kiểm tra duplicate và count distinct.
- GROUP BY/HAVING với khách hàng có nhiều đơn và tổng tiền bằng ngưỡng.
- Sort property không được hỗ trợ bị từ chối.

Với aggregate, fixture nên có hai đơn hàng khác nhau cùng tổng tiền để phát hiện lỗi dùng `SUM(DISTINCT ...)` không đúng ngữ nghĩa.

## 18. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Không tìm thấy Q-type | Annotation processor chưa chạy hoặc sai Jakarta/Javax classifier | Kiểm tra Querydsl APT và generated sources |
| Repository không nhận custom fragment | Sai tên implementation hoặc fragment chưa được extend | Dùng tên `FragmentNameImpl` và extend fragment interface |
| DTO projection lỗi constructor | Sai thứ tự hoặc kiểu tham số | Đối chiếu constructor; cân nhắc `@QueryProjection` |
| Projection bean không có giá trị | Alias không khớp property/setter | Dùng alias đúng hoặc constructor projection |
| Hàng gốc bị lặp | JOIN ToMany tạo nhiều hàng | Dùng EXISTS, distinct phù hợp hoặc xác định grain DTO |
| Tổng count lớn hơn số entity | Count trên hàng JOIN thay vì entity duy nhất | Dùng count distinct và count query cùng ngữ nghĩa |
| Tổng tiền bị nhân lên | JOIN nhiều collection trước aggregate | Aggregate theo grain đúng hoặc tách subquery |
| LEFT JOIN lại loại hàng null | Predicate bảng phải đặt trong WHERE | Đưa điều kiện ghép vào ON khi cần giữ hàng trái |
| Phân trang collection fetch sai | Limit áp dụng lên hàng JOIN hoặc provider phân trang trong memory | Page ID trước rồi fetch dữ liệu chi tiết |
| Sort không đúng | Pageable sort bị bỏ qua hoặc ánh xạ sai | Dùng whitelist sort và tie-breaker ổn định |
| Query chậm dù DSL gọn | JOIN thừa, thiếu index hoặc cardinality lớn | Xem SQL và execution plan |
| Querydsl dùng sai namespace | Querydsl artifact Javax trong ứng dụng Jakarta hoặc ngược lại | Chọn classifier và phiên bản tương thích |

## 19. Checklist thiết kế custom Querydsl repository

- [ ] Chỉ dùng QuerydslPredicateExecutor cho truy vấn đơn giản phù hợp.
- [ ] Dùng repository fragment cho JOIN/projection/grouping phức tạp.
- [ ] Q-type được sinh tự động bởi annotation processor.
- [ ] Querydsl artifact dùng đúng Jakarta/Javax namespace.
- [ ] JPAQueryFactory nhận EntityManager do Spring quản lý.
- [ ] Predicate động được ghép từ filter hợp lệ.
- [ ] Tenant/owner predicate bắt buộc được thêm từ server context.
- [ ] Chọn inner join, left join và on đúng ngữ nghĩa.
- [ ] DTO projection có constructor/alias khớp.
- [ ] Dùng @QueryProjection nếu muốn kiểm tra constructor ở compile time.
- [ ] Không dùng fetch join chỉ để lấy một vài cột DTO.
- [ ] Count query đếm đúng grain kết quả.
- [ ] JOIN ToMany không làm lặp DTO hoặc sai tổng.
- [ ] GROUP BY/HAVING không bị đặt nhầm thành WHERE.
- [ ] Pageable có thứ tự ổn định và sort được whitelist.
- [ ] Không phân trang trực tiếp trên fetch join collection.
- [ ] Test cả trường hợp null, filter rỗng, duplicate và trang tiếp theo.
- [ ] Đo SQL, số query và execution plan trên database mục tiêu.

## 20. Tài liệu tham khảo

- [Spring Data JPA — Querydsl Extension](https://docs.spring.io/spring-data/jpa/reference/repositories/core-extensions.html#core.extensions.querydsl) — tích hợp Querydsl và QuerydslPredicateExecutor.
- [Spring Data JPA — Custom Repository Implementations](https://docs.spring.io/spring-data/jpa/reference/repositories/custom-implementations.html) — repository fragments và quy ước implementation.
- [Querydsl Reference Guide](https://querydsl.com/static/querydsl/latest/reference/html_single/) — JPAQueryFactory, joins, predicates, projections, grouping và subquery.
- [Querydsl JPA API](https://querydsl.com/static/querydsl/latest/apidocs/com/querydsl/jpa/impl/JPAQueryFactory.html) — tạo truy vấn JPA từ factory.
- [Jakarta Persistence Specification](https://jakarta.ee/specifications/persistence/) — JPQL, joins, fetch joins, grouping và pagination semantics.
- [Hibernate ORM User Guide](https://docs.hibernate.org/orm/current/userguide/html_single/Hibernate_User_Guide.html) — fetching, pagination, query execution và persistence context.

Custom Querydsl repository giúp giữ truy vấn phức tạp trong một nơi có cấu trúc và kiểm tra kiểu. Hãy dùng Q-type cho predicate, JOIN đúng quan hệ, DTO projection cho dữ liệu đọc, và count query phản ánh đúng số đối tượng mà caller muốn phân trang. Với JOIN collection và aggregate, xác định grain của kết quả trước khi viết query; sau đó kiểm chứng SQL, số hàng và execution plan bằng integration test.
