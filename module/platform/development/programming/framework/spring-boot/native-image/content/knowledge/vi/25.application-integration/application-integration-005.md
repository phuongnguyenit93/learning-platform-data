# Spring Data repository và thông tin kiểu của mô hình dữ liệu

## 1. Vì sao repository và domain type cần được xem xét khi build native?

Spring Data giúp ứng dụng Spring Boot truy cập dữ liệu thông qua repository interface, domain model và các abstraction như `CrudRepository`, `JpaRepository` hoặc `MongoRepository`. Trên JVM, Spring Data và persistence provider có thể dùng metadata, reflection, proxy và cơ chế introspection để tạo repository implementation, ánh xạ entity, gọi constructor, đọc/ghi property hoặc chuyển đổi kiểu dữ liệu.

GraalVM Native Image phân tích tập class có thể truy cập ở build time. Những đường truy cập động mà framework hoặc persistence provider sử dụng phải được Spring AOT, Spring Data AOT hoặc reachability metadata của dependency mô tả phù hợp. Vì vậy, một repository hoạt động trên JVM chưa tự chứng minh toàn bộ query, entity mapping và projection hoạt động trên native executable.

Trong module **SPRING_BOOT_NATIVE_IMAGE**, cần hiểu ba phần liên kết với nhau:

- **Repository metadata:** interface repository, domain type, identifier type, query method và cấu hình repository.
- **Domain model type information:** constructor, property, identifier, association, projection, generic type và conversion metadata.
- **Persistence integration:** JPA/Hibernate, Spring Data JDBC, MongoDB hoặc module Spring Data khác, mỗi module có cách mapping và yêu cầu runtime riêng.

Bài học tập trung vào cách khai báo model/repository rõ ràng, tận dụng AOT support sẵn có, xác định các đường truy cập động còn lại và kiểm thử chúng trên native executable.

## 2. Repository interface mô tả contract truy cập dữ liệu

Ví dụ Spring Data JPA:

```java
public interface OrderRepository
        extends JpaRepository<Order, UUID> {

    Optional<Order> findByOrderNumber(String orderNumber);

    List<Order> findByStatusAndCreatedAtAfter(
            OrderStatus status, Instant createdAfter);
}
```

Interface khai báo:

- Domain type: `Order`.
- Identifier type: `UUID`.
- Các thao tác CRUD kế thừa từ `JpaRepository`.
- Query method được Spring Data phân tích từ tên method.

Spring Data tạo implementation/proxy cho repository dựa trên repository infrastructure. Ứng dụng thường inject interface vào service:

```java
@Service
class OrderQueryService {

    private final OrderRepository orders;

    OrderQueryService(OrderRepository orders) {
        this.orders = orders;
    }

    Optional<Order> find(String number) {
        return orders.findByOrderNumber(number);
    }
}
```

Không tự tạo implementation cho repository chỉ để native build chạy được. Trước tiên cần xác nhận Spring Boot/Spring Data version và persistence module đang dùng có AOT/native support tương ứng. Framework có thể đã cung cấp các contribution và metadata cần thiết.

## 3. Generic type của repository mang thông tin gì?

Các repository Spring Data thường khai báo domain type và identifier type qua generic parameters:

```java
JpaRepository<Order, UUID>
```

Hai tham số có ý nghĩa:

- `Order`: loại entity/domain object mà repository đọc và ghi.
- `UUID`: loại identifier của entity.

Spring Data dùng thông tin này để xác định metadata mapping, thao tác CRUD và chuyển đổi identifier. Nếu dùng raw type hoặc generic wrapper quá phức tạp, framework có thể khó suy ra type information cần thiết.

Nên khai báo repository cụ thể:

```java
public interface CustomerRepository
        extends JpaRepository<Customer, Long> {
}
```

Tránh raw repository:

```java
@SuppressWarnings("rawtypes")
interface GenericRepository extends JpaRepository {
}
```

Raw type làm mất thông tin compile-time, giảm type safety và khiến việc suy luận domain/id type khó hơn. Khi xây generic base repository cho nhiều aggregate, giữ generic signature rõ ràng và xác minh repository scanning/AOT của Spring Data version đang dùng.

## 4. Domain model và constructor được dùng để tạo entity

Spring Data cần tạo object khi đọc dữ liệu. Tùy persistence module và mapping strategy, framework có thể dùng constructor, persistence constructor, property accessor hoặc cơ chế riêng của provider.

Ví dụ entity JPA:

```java
@Entity
@Table(name = "orders")
public class Order {

    @Id
    private UUID id;

    @Column(nullable = false, unique = true)
    private String orderNumber;

    @Enumerated(EnumType.STRING)
    private OrderStatus status;

    protected Order() {
        // Constructor cho JPA theo yêu cầu entity model
    }

    public Order(String orderNumber, OrderStatus status) {
        this.id = UUID.randomUUID();
        this.orderNumber = orderNumber;
        this.status = status;
    }

    public UUID getId() {
        return id;
    }

    public String getOrderNumber() {
        return orderNumber;
    }

    public OrderStatus getStatus() {
        return status;
    }
}
```

Với JPA, entity cần tuân thủ yêu cầu của Jakarta Persistence về constructor và entity class; chi tiết còn phụ thuộc mapping access strategy. Không mặc định mọi Spring Data module đều tạo object theo cùng quy tắc JPA.

Với Spring Data JDBC hoặc MongoDB, Spring Data mapping infrastructure có thể dùng constructor phù hợp, kể cả constructor được đánh dấu. Hãy đọc quy tắc của module đang dùng thay vì sao chép entity JPA sang module khác.

## 5. Persistence constructor và @PersistenceCreator

Spring Data Commons cung cấp `@PersistenceCreator` để chỉ rõ constructor hoặc factory method được dùng khi materialize object từ dữ liệu trong các trường hợp có nhiều lựa chọn.

Ví dụ immutable model:

```java
public class Customer {

    private final Long id;
    private final String email;
    private final String displayName;

    @PersistenceCreator
    public Customer(
            Long id,
            String email,
            String displayName) {
        this.id = id;
        this.email = email;
        this.displayName = displayName;
    }

    public Long getId() {
        return id;
    }

    public String getEmail() {
        return email;
    }

    public String getDisplayName() {
        return displayName;
    }
}
```

Annotation này thuộc package `org.springframework.data.annotation`. Nó giúp Spring Data xác định constructor mapping. Nó không phải RuntimeHints và không tự đăng ký constructor cho mọi reflection/JNI use case.

Với JPA entity, phải tuân thủ yêu cầu của JPA provider trước; không dùng `@PersistenceCreator` để thay thế constructor bắt buộc của entity nếu provider yêu cầu no-arg constructor. Với JDBC/MongoDB mapping, persistence creator có vai trò rõ hơn trong quá trình materialization của Spring Data.

## 6. Property names và access strategy

Spring Data mapping cần biết cách liên kết cột/document field với property của domain object. Ví dụ:

```java
@Table("customers")
public class CustomerRecord {

    @Id
    private Long id;

    @Column("email_address")
    private String email;

    // constructor/accessors
}
```

Với Spring Data JDBC, annotation mapping và naming strategy xác định cách property tương ứng với cột. Với JPA, `@Column`, `@Access` và vị trí annotation trên field/property ảnh hưởng access strategy. Với MongoDB, `@Field` và mapping context xác định tên document field.

Đừng trộn annotation của các module mà không hiểu semantics. `jakarta.persistence.Column` và `org.springframework.data.relational.core.mapping.Column` là hai annotation khác nhau, dành cho các persistence model khác nhau.

Trong Native Image, framework cần có đủ type/property metadata cho mapping. Spring Data AOT và provider integration có thể xử lý phần lớn trường hợp chuẩn; custom accessor hoặc property discovery bằng reflection cần được kiểm tra cụ thể.

## 7. Query derivation và query khai báo

Spring Data có thể tạo query từ tên method:

```java
List<Order> findByStatusAndCreatedAtAfter(
        OrderStatus status, Instant time);
```

Hoặc query được khai báo:

```java
@Query("""
       select o from Order o
       where o.customerId = :customerId
       order by o.createdAt desc
       """)
List<Order> findRecentByCustomer(
        @Param("customerId") UUID customerId);
```

Query derivation được phân tích từ repository method metadata. Query annotation được xử lý bởi Spring Data module tương ứng. Native compatibility còn phụ thuộc query parser, persistence provider, mapping metadata và type conversion.

Nếu query dùng tên property sai, vấn đề thường là query/model mismatch chứ không phải Native Image. Trước khi thêm hints, chạy repository integration test trên JVM và kiểm tra query được tạo đúng.

## 8. Projection và DTO query

Spring Data projection có thể dùng interface hoặc class/record để trả về một phần dữ liệu:

```java
public interface OrderSummary {
    UUID getId();
    String getOrderNumber();
    OrderStatus getStatus();
}
```

Projection interface có thể được triển khai thông qua proxy hoặc cơ chế mapping tùy module/query. DTO projection có thể dùng constructor:

```java
public record OrderSummaryDto(
        UUID id,
        String orderNumber,
        OrderStatus status) {
}
```

Khi dùng projection trong native, kiểm thử đúng đường đi production. Nếu interface projection tạo proxy, cần xác nhận Spring Data AOT/provider đã xử lý proxy metadata. Nếu DTO projection cần constructor mapping, xác minh constructor và parameter metadata theo cách framework thực tế sử dụng.

Không suy ra rằng mọi interface projection đều cần tự đăng ký JDK proxy hint. Spring Data có thể tự cung cấp metadata phù hợp; chỉ bổ sung hints khi có bằng chứng thiếu và xác định đúng interface combination.

## 9. Association và nested type

Entity có thể chứa association hoặc nested object:

```java
@Entity
class OrderLine {

    @Id
    private UUID id;

    @ManyToOne(fetch = FetchType.LAZY)
    private Order order;

    private String sku;
    private int quantity;
}
```

Với JPA, association có thể dùng proxy/lazy loading của provider. Native compatibility cần xem xét Hibernate version, enhancement/proxy strategy, entity metadata và cách application truy cập association.

Với Spring Data JDBC, aggregate reference có semantics khác JPA association; JDBC không dùng lazy-loading proxy như Hibernate theo cùng cách. Với MongoDB, nested document mapping lại có quy tắc khác.

Khi điều tra native issue, xác định module và provider cụ thể. Một lỗi lazy proxy của Hibernate không nên được xử lý bằng cách áp dụng hướng dẫn cho Spring Data JDBC.

## 10. Spring Data AOT và repository infrastructure

Spring Data và Spring Boot cung cấp AOT support để chuẩn bị một số metadata cần cho repository và mapping. Mức hỗ trợ phụ thuộc Spring Boot, Spring Data module, provider và version.

Trong pipeline AOT, framework có thể phân tích repository configuration và đóng góp metadata/generated initialization cho các thành phần được hỗ trợ. Điều này giúp giảm phụ thuộc vào việc quét/khám phá động khi native process chạy.

Cần xác minh trong dự án:

- Repository interface có được phát hiện qua repository scanning không?
- Đúng Spring Data module được bật không?
- Domain type và identifier type có rõ ràng không?
- Query methods được parse/validate không?
- Entity mapping metadata có được chuẩn bị đúng không?
- Provider version có hỗ trợ Native Image không?
- Custom converter, projection hoặc repository fragment có cần metadata bổ sung không?

Không giả định chỉ vì application AOT chạy thành công là mọi repository đã được kiểm thử. Cần chạy query và mapping thật trên native executable.

## 11. Repository fragment và custom implementation

Spring Data cho phép bổ sung repository fragment:

```java
public interface OrderSearch {
    List<Order> search(OrderCriteria criteria);
}

class OrderSearchImpl implements OrderSearch {

    @Override
    public List<Order> search(OrderCriteria criteria) {
        // Custom implementation
        return List.of();
    }
}

public interface OrderRepository
        extends JpaRepository<Order, UUID>, OrderSearch {
}
```

Custom fragment là code ứng dụng nên có thể chứa logic động riêng. Nếu implementation dùng reflection, resource, proxy hoặc thư viện ngoài, các yêu cầu native tương ứng vẫn cần được kiểm tra.

Đặt implementation theo naming/registration convention mà Spring Data version yêu cầu. Nếu fragment không được phát hiện, trước hết kiểm tra repository configuration và naming/scan; không kết luận ngay là thiếu hints.

## 12. Custom converters và type conversion

Spring Data mapping có thể dùng converter để chuyển kiểu giữa domain model và store representation. Ví dụ Spring Data MongoDB:

```java
@WritingConverter
class MoneyWriteConverter
        implements Converter<Money, Document> {

    @Override
    public Document convert(Money source) {
        return new Document()
                .append("amount", source.amount())
                .append("currency", source.currency());
    }
}
```

Ví dụ minh họa; kiểu source/target và registration phụ thuộc store module. Converter thường là bean hoặc được đăng ký qua custom conversions của module.

Trong native, test converter theo hai chiều nếu ứng dụng đọc/ghi dữ liệu. Nếu converter dùng reflection để đọc field, load class theo tên hoặc tạo object động, xác định metadata cần thiết. Converter thuần gọi accessor/constructor đã biết thường dễ phân tích hơn.

Không dùng converter chỉ để che lỗi mapping annotation. Giữ domain type và store type rõ ràng, kiểm thử dữ liệu cũ/mới và null semantics.

## 13. Identifier type và custom ID conversion

Identifier có thể là `Long`, `UUID`, String hoặc kiểu value object. Ví dụ:

```java
public record OrderId(UUID value) {
}
```

Nếu repository dùng value object làm ID, cần xác định Spring Data module/provider có hỗ trợ mapping/conversion trực tiếp hay cần converter. Kiểu ID phải tương thích với store representation và query parameter binding.

Test các trường hợp:

- Tạo entity mới và sinh ID.
- Đọc entity bằng ID.
- Query method nhận ID.
- Serialize/deserialize ID qua API.
- Mapping ID giữa domain và database.
- Null/invalid ID và conversion failure.

Native Image không thay đổi semantics của UUID hay Long, nhưng các custom converter/type metadata có thể đi qua framework infrastructure. Kiểm tra trên native nếu ID dùng constructor/reflection hoặc custom conversion.

## 14. Repository bootstrap và profile

Repository scanning có thể được cấu hình bằng `@EnableJpaRepositories`, `@EnableJdbcRepositories` hoặc auto-configuration của Spring Boot. Profile/condition có thể quyết định repository infrastructure, datasource và provider bean nào được tạo.

Ví dụ:

```java
@Configuration(proxyBeanMethods = false)
@EnableJpaRepositories(
        basePackageClasses = OrderRepository.class)
class JpaRepositoryConfiguration {
}
```

Khi dùng explicit repository configuration, bảo đảm package/type được đưa vào AOT ApplicationContext. Nếu ứng dụng có nhiều store module cùng lúc, cần cấu hình rõ repository nào thuộc module nào để tránh ambiguity.

Structural properties/profile được dùng để quyết định repository infrastructure phải cố định khi Spring AOT phân tích context. Runtime URL/credential có thể thay đổi nếu bean graph vẫn ổn định và datasource/client hỗ trợ cấu hình runtime.

## 15. Reflection hints: chỉ bổ sung khi framework chưa bao phủ

Nếu một custom mapping path dùng reflection ngoài support mặc định, có thể đăng ký RuntimeHints cho type/member đã biết:

```java
final class DomainMappingHints
        implements RuntimeHintsRegistrar {

    @Override
    public void registerHints(
            RuntimeHints hints,
            ClassLoader classLoader) {

        hints.reflection().registerType(
                ExternalPayload.class,
                MemberCategory.INVOKE_PUBLIC_CONSTRUCTORS,
                MemberCategory.INVOKE_PUBLIC_METHODS
        );
    }
}
```

Gắn registrar:

```java
@Configuration(proxyBeanMethods = false)
@ImportRuntimeHints(DomainMappingHints.class)
class DomainNativeConfiguration {
}
```

Đây là ví dụ cho custom reflection path. Không tự thêm hints cho mọi JPA entity hoặc repository chỉ vì chúng là domain types. Spring Data, Spring Framework và persistence provider có thể đã đóng góp metadata.

Khi cần hints, đăng ký chính xác constructor/method/field được truy cập. Kiểm tra bằng `RuntimeHintsPredicates` rồi xác minh AOT đã thu thập registrar và native runtime thực sự dùng đường mapping đó.

## 16. Kiểm thử repository trên JVM trước

Bắt đầu bằng repository integration tests trên JVM để xác nhận query và mapping đúng:

```java
@DataJpaTest
class OrderRepositoryTest {

    @Autowired
    OrderRepository orders;

    @Test
    void findsOrderByNumber() {
        Order order = new Order(
                "ORD-1001", OrderStatus.CREATED);

        orders.save(order);

        assertThat(orders.findByOrderNumber("ORD-1001"))
                .isPresent()
                .get()
                .extracting(Order::getStatus)
                .isEqualTo(OrderStatus.CREATED);
    }
}
```

Test này xác minh repository và mapping với test database/provider được cấu hình. Cần thêm fixture cho query derivation, custom query, projection, association, ID conversion và converter nếu ứng dụng sử dụng.

JVM test giúp phân biệt lỗi nghiệp vụ/query với lỗi Native Image. Nếu test đã fail trên JVM, xử lý mapping/query trước khi điều tra hints.

## 17. Native integration test cho repository và model

Sau khi JVM tests pass, chọn native scenarios có rủi ro:

- Khởi tạo ApplicationContext và repository proxy.
- Persist entity rồi đọc lại.
- Query method derived và query annotation.
- DTO/interface projection.
- Custom converter hai chiều.
- Constructor mapping cho immutable model.
- Association/lazy access nếu dùng JPA.
- Identifier value object.
- Repository fragment/custom implementation.

Có thể chạy native test task nếu plugin hỗ trợ hoặc khởi chạy native application và gọi endpoint black-box. Cần dùng database/container tương thích và cùng schema/fixtures với JVM test.

Không chỉ kiểm tra bean repository tồn tại. Gọi method thực tế và xác minh kết quả đọc/ghi. Một context startup pass không chứng minh entity materialization hoặc query execution hoạt động.

## 18. Chẩn đoán lỗi repository/model trên native

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Repository bean không được tạo | Scan/configuration/profile sai | Kiểm tra repository scanning và AOT inputs |
| Query method lỗi khi startup | Derived query/property name sai | Kiểm tra domain property và query parser trên JVM |
| Entity không materialize | Constructor/property mapping không phù hợp | Kiểm tra persistence constructor và mapping strategy |
| Projection lỗi trên native | Proxy/constructor/type metadata thiếu hoặc query không trả đúng shape | Kiểm tra projection implementation và native path |
| Custom converter không chạy | Converter chưa đăng ký đúng store module | Kiểm tra custom conversions/configuration |
| Lazy association lỗi | Provider proxy/enhancement hoặc access ngoài transaction | Kiểm tra Hibernate/provider version và transaction boundary |
| JVM pass, native thiếu member | Reflection path chưa được metadata bao phủ | Kiểm tra provider metadata, hints và native trace |
| ID conversion sai | Converter/type mapping không nhất quán | Test store representation và query parameter |
| Native không kết nối database | Driver/library/URL/credential/runtime environment | Kiểm tra JDBC driver, ABI, config và container |

Không mặc định mọi lỗi repository native đều là thiếu reflection. Query sai, transaction boundary, schema mismatch, driver thiếu hoặc datasource không sẵn sàng cũng có thể gây lỗi.

## 19. Ma trận bằng chứng cho Spring Data integration

Để biết phần nào đã được xác minh, lập bảng theo module thực tế:

| Capability | JVM test | AOT/build | Native runtime |
|---|---|---|---|
| Repository discovery | Context/repository test | AOT processing | Repository bean được tạo |
| Derived query | Repository test | Native build | Gọi query và assert result |
| Entity constructor mapping | Persist/read test | AOT/native metadata | Materialize entity |
| Projection | Projection test | Native build | Query projection |
| Custom converter | Read/write test | Native build | Convert hai chiều |
| Association/lazy loading | Provider integration test | Native build | Truy cập trong transaction |
| Custom repository fragment | Fragment test | AOT processing | Gọi implementation |
| ID conversion | CRUD/query test | Native build | Save/find bằng domain ID |

Đánh dấu `N/A` nếu module không sử dụng capability. Bảng phải phản ánh đúng Spring Data module: không đưa JPA lazy loading vào dự án JDBC nếu không có cơ chế tương ứng.

## 20. Bài thực hành: kiểm tra OrderRepository trên native

**Bối cảnh:** Spring Boot dùng Spring Data JPA, entity `Order`, ID kiểu UUID, query method theo order number, projection `OrderSummary` và một converter cho value object `OrderId`.

**Bước 1 — Khai báo domain model.** Tạo entity với mapping rõ ràng, constructor phù hợp JPA và accessor cần thiết.

**Bước 2 — Khai báo repository.** Dùng `JpaRepository<Order, UUID>`, thêm query method và custom query cần thiết.

**Bước 3 — Thêm projection/converter.** Tạo DTO/interface projection và converter ID nếu module yêu cầu; đăng ký converter đúng cơ chế.

**Bước 4 — Viết JVM repository tests.** Test save/find, query derivation, projection, ID conversion và transaction behavior.

**Bước 5 — Chạy Spring AOT.** Cố định profile, datasource/provider và structural properties; xác nhận repository configuration được xử lý.

**Bước 6 — Build native.** Dùng Spring Boot/Native Build Tools version tương thích; chỉ thêm RuntimeHints nếu xác định được custom access còn thiếu.

**Bước 7 — Chạy native integration.** Dùng cùng database schema và fixture, gọi các repository method và xác minh entity/projection được materialize đúng.

**Bước 8 — Chạy container test.** Cấp database endpoint, credentials test và network đúng; xác nhận repository behavior trên runtime image đích.

Tiêu chí hoàn thành: repository được phát hiện; query/mapping đúng trên JVM; AOT/native build thành công; native executable thực hiện được CRUD/query/projection/conversion được chọn; kết quả được kiểm tra trong môi trường runtime tương đương triển khai.

## 21. Kết luận

Spring Data repository và domain model cung cấp metadata quan trọng để Spring Data xác định cách tạo repository, truy vấn store, materialize entity, chuyển đổi identifier và xây projection. Trong Spring Boot Native Image, hãy giữ generic type, constructor, property mapping và repository configuration rõ ràng; tận dụng AOT/native support chính thức của Spring Data và persistence provider trước khi tự thêm hints.

Kiểm thử theo từng lớp: JVM repository tests để xác nhận query/mapping, Spring AOT để xác nhận context/repository configuration được xử lý, native integration để xác minh CRUD/query/projection/converter thực sự hoạt động. Luôn phân biệt yêu cầu của JPA, JDBC và MongoDB; một cách mapping hoặc proxy không áp dụng đồng nhất cho mọi Spring Data module.
