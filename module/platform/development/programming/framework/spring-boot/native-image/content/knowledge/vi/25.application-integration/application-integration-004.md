# JPA, Hibernate và các proxy, enhancement, metadata cần được kiểm chứng

> **Chương:** Tích hợp ứng dụng  
> **Module:** `SPRING_BOOT_NATIVE_IMAGE`  
> **Mục tiêu:** Phân biệt proxy của Spring AOP với proxy lazy loading của Hibernate; hiểu bytecode enhancement của entity; biết Spring Data JPA đóng góp ManagedTypes và RuntimeHints như thế nào; kiểm chứng dialect, repository, resource và driver trên đúng phiên bản Hibernate/Spring Boot/GraalVM trước khi phát hành native executable.

## 1. Vì sao JPA/Hibernate cần được kiểm chứng riêng?

Spring Boot có thể khởi tạo một ứng dụng JPA trên JVM mà không cần người phát triển khai báo thủ công mọi class hoặc method reflection. Hibernate và Spring Data thực hiện nhiều việc động trong quá trình khởi động và truy cập dữ liệu:

- Khám phá entity và mapping.
- Tạo EntityManagerFactory, metamodel và repository proxy.
- Tạo proxy cho association hoặc collection được lazy load.
- Nạp mapping XML, dialect, JDBC driver và service provider.
- Dùng reflection để khởi tạo entity, converter, listener, interceptor hoặc custom type.
- Có thể dùng bytecode enhancement để chèn interception vào entity class.

Với GraalVM Native Image, compiler phân tích reachability ở build time. Reflection, resource, serialization và dynamic proxy cần được nhận diện hoặc khai báo metadata trước khi executable được tạo. Classpath cũng được cố định tại build time. Spring AOT sinh mã khởi tạo, bytecode và hints, nhưng từng integration vẫn phải được kiểm tra theo cách mà thư viện đó tạo object và truy cập dữ liệu. [Spring Boot — Introducing GraalVM Native Images](https://docs.spring.io/spring-boot/reference/packaging/native-image/introducing-graalvm-native-images.html)

Một ứng dụng có thể build native thành công nhưng vẫn gặp lỗi khi:

- Hibernate khởi tạo EntityManagerFactory.
- Một association lazy được truy cập lần đầu.
- Một repository method dùng projection hoặc query tùy biến.
- Một entity listener hoặc converter được nạp bằng tên class.
- Một mapping/resource chỉ được đọc ở nhánh nghiệp vụ chưa chạy trong test.
- Một JDBC driver hoặc dialect khác với môi trường build.

Vì vậy, cần kiểm tra riêng **bean proxy, Hibernate proxy, entity enhancement, AOT metadata và hành vi database**. Chúng liên quan nhau nhưng không phải một cơ chế duy nhất.

## 2. Phân biệt bốn cơ chế thường bị gọi chung là proxy hoặc enhancement

| Cơ chế | Ai tạo/quản lý? | Mục đích | Kiểm tra ở đâu? |
|---|---|---|---|
| Spring AOP proxy | Spring Framework | Áp dụng transaction, cache, security, aspect cho Spring bean | Bean type, advisor và AOT-generated proxy |
| Hibernate lazy proxy/collection wrapper | Hibernate ORM | Trì hoãn tải entity association hoặc collection | Entity mapping, persistence context, native runtime |
| Hibernate bytecode enhancement | Hibernate build plugin/enhancer | Chèn interception vào entity để lazy attribute loading, dirty tracking hoặc association management | Class bytecode sau compile/enhance |
| Spring Data JPA AOT output | Spring Data và Spring AOT | Chuẩn bị ManagedTypes, repository metadata, accessor bytecode, query implementation và runtime hints | AOT output và repository tests |

**Spring AOT tạo được proxy cho Spring bean không có nghĩa Hibernate entity proxy đã được xử lý.** Spring AOP proxy thường bao quanh service/repository bean. Hibernate proxy đại diện cho một entity chưa được tải hoặc một collection chưa được khởi tạo. Bytecode enhancement sửa class entity trong build. Spring Data AOT lại chuẩn bị thông tin và code cho persistence layer.

Khi một lỗi xuất hiện, trước tiên hãy xác định đúng cơ chế đang thất bại. Thêm reflection hint cho entity không tự sửa lỗi `LazyInitializationException`; bật Hibernate enhancement cũng không tự bổ sung resource XML hoặc JDBC driver vào native image.

## 3. Hibernate proxy và lazy loading hoạt động thế nào?

Hibernate quản lý một đồ thị entity có thể lớn. Nếu mỗi lần đọc một entity đều tải đệ quy toàn bộ association, ứng dụng sẽ tốn bộ nhớ và có thể tạo nhiều round trip đến database. Hibernate dùng lazy fetching để chỉ tải association khi cần.

Ví dụ:

```java
@Entity
@Table(name = "purchase_order")
public class PurchaseOrder {

    @Id
    @GeneratedValue
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "customer_id")
    private Customer customer;

    @OneToMany(mappedBy = "order", fetch = FetchType.LAZY)
    private List<OrderLine> lines = new ArrayList<>();

    protected PurchaseOrder() {
    }

    public Long getId() {
        return id;
    }

    public Customer getCustomer() {
        return customer;
    }

    public List<OrderLine> getLines() {
        return lines;
    }
}
```

Khi tải `PurchaseOrder`, Hibernate có thể chưa tải `Customer` và các `OrderLine`. Thay vào đó, Hibernate cung cấp proxy hoặc collection wrapper. Khi code truy cập trạng thái chưa tải, Hibernate dùng persistence context để lấy dữ liệu rồi tiếp tục lời gọi.

```java
PurchaseOrder order = entityManager.find(PurchaseOrder.class, orderId);

// Association có thể vẫn chưa được tải.
boolean customerLoaded = entityManagerFactory
        .getPersistenceUnitUtil()
        .isLoaded(order, "customer");

// Lời gọi lấy dữ liệu customer có thể kích hoạt SQL.
String customerName = order.getCustomer().getName();
```

Có thể kiểm tra collection:

```java
boolean linesLoaded = entityManagerFactory
        .getPersistenceUnitUtil()
        .isLoaded(order, "lines");
```

Hibernate cũng cung cấp `Hibernate.isInitialized(...)` để kiểm tra proxy/collection theo API riêng của Hibernate. [Hibernate ORM — Proxies and Lazy Fetching](https://docs.hibernate.org/stable/core/introduction/html_single/#proxies-and-lazy-fetching)

### 3.1. Proxy chỉ tải được khi persistence context còn hoạt động

Lazy proxy thường cần một persistence context/session đang mở để truy vấn database. Nếu transaction và persistence context kết thúc trước khi association được truy cập, Hibernate có thể ném `LazyInitializationException`.

Ví dụ:

```java
PurchaseOrder order = repository.findById(orderId).orElseThrow();

// Transaction kết thúc và persistence context đã đóng.
// Lời gọi lazy sau đây có thể thất bại.
String customerName = order.getCustomer().getName();
```

Đây là vấn đề vòng đời persistence context, không phải lỗi reachability metadata của Native Image. Native executable vẫn phải tuân theo cùng quy tắc lazy loading như JVM.

Cách xử lý nên là tải đúng dữ liệu cần dùng trong transaction, chuyển thành DTO khi persistence context còn mở và trả DTO qua API. Không nên mở rộng transaction một cách vô hạn chỉ để serializer có thể đi qua toàn bộ entity graph.

### 3.2. Lazy loading có thể gây N+1 query

Giả sử một trang hiển thị 50 đơn hàng và mỗi đơn hàng cần tên khách hàng. Nếu query ban đầu chỉ tải đơn hàng, sau đó code gọi `getCustomer()` lần lượt, Hibernate có thể phát sinh một query cho mỗi khách hàng. Đây là N+1 query.

Native Image không loại bỏ chi phí này. Startup nhanh hơn không làm các round trip database biến mất. Hãy kiểm tra số câu SQL và fetch plan trên native runtime giống như khi chạy JVM.

Các cách điều khiển fetch thường dùng:

- JPQL/HQL `join fetch` khi cần một tập association cụ thể.
- JPA `EntityGraph` cho fetch plan theo use case.
- DTO projection khi chỉ cần một số field.
- Batch fetching khi phù hợp với hình dạng dữ liệu.
- Query riêng cho màn hình hoặc báo cáo có đồ thị dữ liệu lớn.

Ví dụ repository:

```java
public interface PurchaseOrderRepository
        extends JpaRepository<PurchaseOrder, Long> {

    @Override
    @EntityGraph(attributePaths = {"customer", "lines"})
    Optional<PurchaseOrder> findById(Long id);
}
```

Service chuyển entity sang DTO trong transaction:

```java
@Service
public class PurchaseOrderQueryService {

    private final PurchaseOrderRepository repository;

    public PurchaseOrderQueryService(PurchaseOrderRepository repository) {
        this.repository = repository;
    }

    @Transactional(readOnly = true)
    public PurchaseOrderView getDetails(Long id) {
        PurchaseOrder order = repository.findById(id)
                .orElseThrow();

        return new PurchaseOrderView(
                order.getId(),
                order.getCustomer().getName(),
                order.getLines().stream()
                        .map(line -> new OrderLineView(
                                line.getProductCode(),
                                line.getQuantity()))
                        .toList());
    }
}
```

Test cần xác nhận fetch plan thật sự tải đủ association và không phát sinh truy vấn ngoài dự kiến. `@EntityGraph` là chỉ dẫn cho JPA provider; hãy kiểm tra SQL và trạng thái loaded trên phiên bản Hibernate thực tế.

## 4. Proxy entity và giới hạn của class

Hibernate thường dùng bytecode proxying để đại diện cho entity chưa tải. Một class entity `final` hoặc method `final` có thể giới hạn khả năng tạo subclass proxy và interception. Kiểu association polymorphic cũng có thêm vấn đề vì proxy có thể chưa biết concrete subtype tại thời điểm được tạo.

Các nguyên tắc thiết kế:

- Tuân thủ yêu cầu entity class của Jakarta Persistence và Hibernate phiên bản đang dùng.
- Không khai báo entity `final` nếu mapping cần class-based lazy proxy.
- Giữ constructor không tham số ở mức truy cập được theo yêu cầu JPA, trừ khi bytecode enhancer và phiên bản provider có hỗ trợ cụ thể.
- Không giả định `instanceof` hoặc cast trên proxy polymorphic luôn cho kết quả như entity đã khởi tạo.
- Dùng `PersistenceUnitUtil.isLoaded` hoặc API Hibernate để kiểm tra trạng thái thay vì suy luận từ class name.
- Test `getReference`, `find`, lazy association và collection trên executable native.

Hibernate 6.2 đã đánh dấu annotation `@Proxy` là deprecated; không dùng cấu hình cũ này như giải pháp chung cho native image. Với entity class final, Hibernate có thể không tạo được proxy class theo cách thông thường. [Hibernate ORM User Guide — Entity Proxies](https://docs.hibernate.org/orm/6.6/userguide/html_single/#entity-proxy)

## 5. Bytecode enhancement của Hibernate giải quyết việc gì?

Bytecode enhancement là bước biến đổi bytecode entity class để Hibernate có thể chèn interception vào các field hoặc method. Nó không giống Spring AOT code generation và cũng không đồng nghĩa với GraalVM Native Image compilation.

Hibernate bytecode enhancer hỗ trợ những khả năng chính:

- **Attribute-level lazy fetching:** trì hoãn tải basic attribute có `@Basic(fetch = LAZY)` và một số lazy association không polymorphic.
- **Dirty tracking bằng interception:** ghi nhận thay đổi khi field được cập nhật, thay vì chỉ so sánh snapshot khi flush.
- **Association management:** hỗ trợ đồng bộ một số thao tác ở hai đầu association theo tính năng enhancer được bật.

Ví dụ basic attribute có thể tốn kém:

```java
@Entity
public class DocumentRecord {

    @Id
    @GeneratedValue
    private Long id;

    private String title;

    @Basic(fetch = FetchType.LAZY)
    @Lob
    private String fullText;

    protected DocumentRecord() {
    }

    public Long getId() {
        return id;
    }

    public String getTitle() {
        return title;
    }

    public String getFullText() {
        return fullText;
    }
}
```

Nếu không có bytecode enhancement, Hibernate có thể bỏ qua yêu cầu lazy loading của basic attribute và tải `fullText` cùng entity. Khi class được enhance đúng, Hibernate có thể intercept lần truy cập field để tải nội dung muộn hơn.

Hibernate mặc định có thể tải các lazy fields thuộc cùng fetch group trong một query khi một field trong group được truy cập. `@LazyGroup` cho phép chia các field thành nhóm tải độc lập khi use case cần. [Hibernate ORM — Using the Bytecode Enhancer](https://docs.hibernate.org/stable/core/introduction/html_single/#using-the-bytecode-enhancer)

### 5.1. Enhancement không loại bỏ mọi proxy

Interception có thể thực hiện lazy loading cho một số association không polymorphic mà không cần một proxy object riêng. Nếu association polymorphic và target type có subclass, Hibernate vẫn cần proxy để đại diện cho concrete type chưa biết.

Vì vậy:

- Bật enhancer không có nghĩa tất cả lazy association đều không còn proxy.
- Không bật enhancer không đồng nghĩa Hibernate không thể lazy load association entity thông thường.
- Enhancement không thay thế RuntimeHints hoặc metadata của Hibernate/GraalVM.
- Spring AOT không tự bật Hibernate enhancement cho entity classes.

Hãy xác định tính năng nào thực sự cần enhancer trước khi thêm plugin vào build. Nếu chỉ dùng lazy association thông thường, cần kiểm tra Hibernate native support và proxy path; nếu dùng lazy basic attribute, cần xác minh bytecode enhancement đã chạy.

### 5.2. Trade-off của interception-based dirty tracking

Dirty tracking bằng interception có thể giảm chi phí giữ và so sánh snapshot. Tuy nhiên, Hibernate lưu ý cách này có thể kém chính xác hơn snapshot-based dirty checking trong một số tình huống.

Ví dụ, interceptor nhận biết việc thay toàn bộ mảng:

```java
document.setImage(new byte[] {1, 2, 3});
```

Nhưng nếu code sửa trực tiếp một phần tử bên trong mảng hiện có:

```java
document.getImage()[0] = 9;
```

interceptor có thể không quan sát được thao tác sửa nội dung bên trong array. Khi bật enhancement, hãy kiểm tra cách ứng dụng cập nhật collection, array và mutable value type; đừng mặc định mọi mutation đều được ghi nhận giống nhau.
## 6. Bật bytecode enhancement trong build

Nếu ứng dụng cần lazy basic attribute hoặc dirty tracking bằng interception, hãy bật Hibernate enhancer ở build time và xác minh phiên bản plugin khớp với Hibernate ORM.

### 6.1. Gradle

Ví dụ với Hibernate ORM 7.x:

```groovy
plugins {
    id "org.hibernate.orm" version "<hibernate-version>"
}

hibernate {
    enhancement {}
}
```

Block `enhancement {}` là cấu hình cần thiết để bật enhancement. Không viết `hibernate { enhancement }` như một lời gọi property đơn lẻ; Gradle có thể hiểu đó là getter và không thực hiện cấu hình enhancement. Hibernate đã ghi rõ khác biệt này trong tài liệu hiện hành. [Hibernate ORM — Bytecode Enhancer](https://docs.hibernate.org/stable/core/introduction/html_single/#using-the-bytecode-enhancer)

Dùng version plugin đồng bộ với `hibernate-core` mà Spring Boot BOM đã resolve, theo tài liệu của Hibernate major version đang dùng. Nếu plugin version không khớp, build có thể lỗi hoặc enhancer có thể áp dụng hành vi khác với runtime provider.

### 6.2. Maven

Với Hibernate ORM 7.x, Maven plugin đã được viết lại và dùng tọa độ plugin mới:

```xml
<plugin>
    <groupId>org.hibernate.orm</groupId>
    <artifactId>hibernate-maven-plugin</artifactId>
    <version><!-- version khớp Hibernate ORM --></version>
    <executions>
        <execution>
            <goals>
                <goal>enhance</goal>
            </goals>
        </execution>
    </executions>
</plugin>
```

Hibernate 6.x dùng tọa độ plugin Maven khác. Hãy lấy đúng groupId, artifactId và cấu hình từ tài liệu của Hibernate version đang được Spring Boot quản lý; không trộn cấu hình plugin 6.x với Hibernate 7.x. [Hibernate ORM 7.0 Migration Guide — Maven Enhancement Plugin](https://docs.hibernate.org/orm/7.0/migration-guide/)

### 6.3. Xác minh class đã được enhance

Không chỉ nhìn vào build log. Hãy xác nhận:

1. Task/goal enhancement thực sự chạy sau khi entity được compile.
2. Output classes/JAR chứa bytecode đã enhance.
3. Enhancement được áp dụng cho source set và module có entity thật.
4. Không có bước đóng gói nào thay bằng class file chưa enhance.
5. Runtime Hibernate dùng cùng major/minor line đã được kiểm tra với enhancer.

Có thể dùng `javap -p` để xem bytecode và interface/method được enhancer thêm vào, nhưng tên thành phần nội bộ có thể thay đổi theo phiên bản. Cách kiểm tra hành vi đáng tin cậy hơn là test lazy basic attribute và dirty tracking bằng Hibernate runtime.

## 7. Spring Data JPA AOT chuẩn bị entity và repository như thế nào?

Spring Data cần biết tập domain type được quản lý. Trên JVM, ứng dụng có thể dựa vào classpath scanning lúc khởi động. Trong native image, classpath scanning runtime không thể được dùng theo cách linh hoạt như JVM, vì vậy Spring Data sử dụng `ManagedTypes` để ghi nhận entity/type đã được phát hiện trong AOT processing.

Tài liệu Spring Data khuyến nghị annotate domain types bằng annotation store-specific như `@Entity` để hỗ trợ entity scanning sớm và bảo đảm type được đưa vào `ManagedTypes`. [Spring Data JPA — Ahead of Time Optimizations](https://docs.spring.io/spring-data/jpa/reference/jpa/aot.html)

Ví dụ:

```java
@Entity
@Table(name = "customer")
public class Customer {

    @Id
    @GeneratedValue
    private Long id;

    private String name;

    protected Customer() {
    }
}
```

Nếu entity nằm ngoài package scan mặc định, cấu hình rõ vùng quét:

```java
@SpringBootApplication
@EntityScan(basePackageClasses = {
        Customer.class,
        PurchaseOrder.class
})
@EnableJpaRepositories(basePackageClasses = PurchaseOrderRepository.class)
public class PaymentApplication {
}
```

Với cấu hình nhiều persistence unit, mapping đặc thù hoặc entity được cung cấp qua module riêng, hãy kiểm tra `PersistenceManagedTypes` và `PersistenceUnitInfo` mà AOT collector sử dụng. Spring Data JPA có thể dùng bean `PersistenceManagedTypes` nếu có; nếu cơ chế discovery không đủ cho ứng dụng, tài liệu cung cấp tùy chọn `spring.aot.jpa.repositories.use-entitymanager=true` để sử dụng trực tiếp EntityManagerFactory trong quá trình thu thập metadata.

### 7.1. RuntimeHints do Spring Data đóng góp

Trong AOT processing, Spring Data có thể đóng góp hints cho:

- `ManagedTypes` và tập entity được phát hiện.
- Reflection cho entity, repository return type và Spring Data annotation.
- Repository fragments.
- Querydsl `Q` classes.
- Auditing và một số integration khác.

Vì vậy, không nên thêm reflection hints rộng cho tất cả entity theo thói quen trước khi kiểm tra hints mà Spring Data đã tạo. Hãy bổ sung RuntimeHints khi có custom type, converter, listener, mapping hoặc đường truy cập động mà framework không thể suy ra.

### 7.2. AOT repository không đồng nghĩa với mọi repository đều được sinh code

Spring Data JPA có thể tạo implementation AOT cho một số query methods đã biết tại build time, chẳng hạn derived query, query được annotate và named query. Tính năng này giúp chuyển việc phân tích query từ runtime sang build time.

Tuy nhiên, không phải mọi repository method đều đủ điều kiện. Các method có implementation fragment, dynamic projection, một số kiểu collection tùy biến hoặc `ScrollPosition` có thể nằm ngoài phạm vi được hỗ trợ của version cụ thể. AOT repository là chi tiết triển khai nội bộ; code ứng dụng không nên tham chiếu trực tiếp generated class. [Spring Data JPA — AOT Repositories and Limitations](https://docs.spring.io/spring-data/jpa/reference/jpa/aot.html)

## 8. Metadata cần kiểm tra trong native image

Với JPA/Hibernate, metadata thường liên quan tới nhiều nhóm khác nhau:

| Nhóm | Ví dụ | Cần xác minh |
|---|---|---|
| Reflection | Entity constructor, field, converter, listener, custom type | Member cần dùng có được giữ cho đúng thao tác không |
| Dynamic proxy | Hibernate entity/collection proxy, JDK proxy do integration tạo | Proxy/interface set và cơ chế tạo proxy có tương thích không |
| Resource | `orm.xml`, mapping XML, template SQL hoặc file cấu hình được nạp động | Resource pattern có được đưa vào image không |
| Service/provider | JDBC driver, Hibernate Integrator, dialect hoặc provider được nạp qua service mechanism | Provider có trên runtime classpath và được Native Image nhận diện không |
| Serialization | Java serialization trong custom type/cache/integration | Type serialization metadata có đủ không |
| Repository AOT | Query metadata, generated repository fragment, type accessor | AOT output được build và đưa vào artifact cuối không |

### 8.1. Reflection hints

Spring Data JPA đóng góp hints cho các entity và repository type mà nó nhận diện được. Nếu ứng dụng có custom code dùng reflection để khởi tạo converter hoặc listener bằng tên class, hãy đăng ký đúng type/member đó qua `RuntimeHintsRegistrar`.

Ví dụ minh họa cho một custom converter được nạp động:

```java
public class PaymentRuntimeHints implements RuntimeHintsRegistrar {

    @Override
    public void registerHints(RuntimeHints hints, ClassLoader classLoader) {
        hints.reflection().registerType(
                CurrencyCodeConverter.class,
                MemberCategory.INVOKE_PUBLIC_CONSTRUCTORS);
    }
}
```

Đăng ký registrar:

```java
@Configuration(proxyBeanMethods = false)
@ImportRuntimeHints(PaymentRuntimeHints.class)
class PaymentNativeConfiguration {
}
```

Ví dụ chỉ cần khi converter thực sự được khởi tạo bằng đường động mà static analysis/AOT không nhận diện. Nếu converter đã được khai báo trong cấu hình Spring/JPA mà framework đã sinh hints, không thêm khai báo trùng lặp.

### 8.2. Resource hints

Nếu ứng dụng đọc mapping XML hoặc file SQL theo đường dẫn được lấy từ property, hãy khai báo resource pattern tương ứng. Ví dụ:

```java
public class PaymentResourceHints implements RuntimeHintsRegistrar {

    @Override
    public void registerHints(RuntimeHints hints, ClassLoader classLoader) {
        hints.resources().registerPattern("META-INF/orm-custom.xml");
        hints.resources().registerPattern("sql/payment/*.sql");
    }
}
```

Đăng ký resource hint chỉ giải quyết việc file được đóng gói và có thể đọc trong native image. Nó không xác nhận mapping XML hợp lệ, entity được scan đúng hoặc SQL tương thích với database. Hãy test cả việc tìm resource lẫn việc Hibernate thực sự nạp và sử dụng nó.

Đối với `META-INF/services` và provider được nạp bằng `ServiceLoader`, kiểm tra cơ chế service loading được hỗ trợ bởi GraalVM và dependency thực tế. Đừng mặc định mọi file trong JAR đều được đưa vào native executable chỉ vì nó có mặt trên JVM classpath.

### 8.3. Hibernate native extension

Hibernate phát hành module `hibernate-graalvm` để hỗ trợ biên dịch Hibernate ORM thành GraalVM Native Image. Tài liệu Hibernate hiện mô tả module này là **experimental**. Vì vậy:

- Chỉ thêm module nếu tài liệu của Hibernate version đang dùng và Spring Boot integration yêu cầu.
- Đồng bộ version với Hibernate ORM; không thêm một version tùy ý.
- Kiểm tra module có nằm trong dependency graph native build cuối cùng.
- Đọc release notes để biết phạm vi hỗ trợ và giới hạn.
- Không xem dependency này là bảo đảm mọi custom type, proxy, dialect hoặc driver đều hoạt động.

[Hibernate ORM — Integration Modules](https://docs.hibernate.org/stable/orm/quickstart/html_single/)

## 9. Phiên bản Spring Boot, Spring Framework và Hibernate phải đồng bộ

Native compatibility phụ thuộc vào tổ hợp version, không chỉ version của Hibernate.

Spring Framework 6.2 yêu cầu Hibernate ORM 6.5 trở lên cho GraalVM Native Image support. Đây là yêu cầu của dòng Spring Framework 6.2; không nên suy ra nó là mức version tối thiểu hoặc version khuyến nghị cho mọi dòng Spring Boot hiện tại. Hibernate ORM 6.5 đã hết vòng đời hỗ trợ, nên không dùng thông tin baseline này làm lý do pin một bản 6.5 mới cho ứng dụng hiện nay. [Spring Framework 6.x Upgrade Guide — Spring Framework 6.2](https://github.com/spring-projects/spring-framework/wiki/Upgrading-to-Spring-Framework-6.x)

Quy trình chọn version:

1. Chọn Spring Boot release phù hợp với Java và GraalVM toolchain.
2. Dùng Spring Boot BOM/dependency management để chọn Spring Framework, Spring Data JPA và Hibernate ORM tương thích.
3. Kiểm tra Hibernate ORM release compatibility matrix cho dòng Spring Boot đó.
4. Nếu dùng Hibernate enhancer hoặc `hibernate-graalvm`, chọn đúng version tương ứng với Hibernate ORM.
5. Kiểm tra JDBC driver, dialect extension và các integration module khác có hỗ trợ native image.
6. Ghi lại toàn bộ version đã resolve trong build report.

Không override riêng `hibernate-core` để thử sửa native build khi chưa xác định vấn đề là proxy, enhancer, service loading hay metadata. Việc nâng một dependency riêng lẻ có thể tạo tổ hợp Spring Data/Hibernate không được kiểm thử.

## 10. Dialect và database configuration trong AOT

Spring Data JPA AOT có thể khởi tạo một Hibernate instance in-memory để thu thập metadata mà không truy cập database thật. Tập managed type được xác định từ AOT metadata collector. Một số quyết định như database dialect có thể được cố định trong ứng dụng đã xử lý AOT.

Điều này quan trọng khi pipeline build và môi trường chạy dùng database khác nhau. Nếu build dùng H2 nhưng production dùng PostgreSQL, không nên mặc định dialect được phát hiện lúc build sẽ tự thay đổi theo JDBC URL runtime.

Khi cần kết quả xác định, cấu hình dialect rõ ràng bằng property phù hợp với version Hibernate:

```yaml
spring:
  jpa:
    database-platform: org.hibernate.dialect.PostgreSQLDialect
```

Dùng dialect thuộc Hibernate ORM đã được Spring Boot quản lý. Nếu dùng dialect tùy chỉnh, kiểm tra class và metadata của dialect trong native executable.

Cần phân biệt hai giai đoạn:

- **AOT processing:** thu thập bean/entity/repository metadata; Spring Data JPA có thể dùng Hibernate in-memory và không cần kết nối database.
- **Ứng dụng native chạy thật:** tạo datasource, kết nối database, thực thi DDL validation/migration và query theo cấu hình runtime.

Nếu build pipeline cần kết nối database để thực hiện một plugin hoặc migration tùy chỉnh, đó là bước riêng của pipeline, không phải yêu cầu mặc định của Spring Data JPA AOT.

## 11. Kiểm tra JDBC driver, dialect và mapping resource

Một ứng dụng có entity metadata đầy đủ vẫn có thể lỗi nếu JDBC driver hoặc resource cần thiết không có trong native artifact.

Kiểm tra các điểm sau:

- JDBC driver version tương thích với Java, GraalVM và database server.
- Driver được đưa vào runtime classpath, không chỉ compile classpath.
- Driver có native-image reachability metadata hoặc hướng dẫn cấu hình chính thức.
- Custom dialect và type contributor có constructor/service provider cần thiết.
- Mapping XML, `persistence.xml`, `orm.xml` và file cấu hình được nạp động có resource hint phù hợp.
- SQL migration/resource được đóng gói đúng trong JAR hoặc container image.
- TLS provider, charset và native library mà driver phụ thuộc có sẵn trong image/runtime OS.
- Database URL, credentials và pool configuration được cung cấp ở runtime theo môi trường triển khai.

Không nên thêm reflection/resource hints cho toàn bộ package của driver khi chưa có lỗi hoặc tài liệu yêu cầu. Bắt đầu bằng dependency documentation và reachability metadata của đúng version driver; chỉ bổ sung custom hints cho phần chưa được xử lý.

## 12. Kiểm thử JPA/Hibernate trên JVM, AOT và native executable

Một bài test chỉ xác nhận Spring context khởi động chưa đủ. Cần thực thi query, proxy, enhancement và transaction trên đúng binary native.

### 12.1. Unit và integration tests trên JVM

Kiểm tra:

- Entity mapping, identifier generation, relationship ownership và cascade.
- Repository derived query, `@Query`, projection, pagination và sorting.
- Converter, entity listener, callback, custom type và auditing.
- Transaction rollback/commit và optimistic locking.
- EntityGraph/join fetch và số lượng SQL.
- Lazy association và collection.
- Lazy basic attribute nếu đã bật enhancement.

Những test này xác minh logic JPA/Hibernate nhưng chưa chứng minh native metadata đã đầy đủ.

### 12.2. Kiểm tra AOT output

Chạy Spring AOT theo build profile của ứng dụng. Kiểm tra:

- ManagedTypes chứa đủ entity.
- Repository metadata/generated implementation xuất hiện cho các method đủ điều kiện.
- Reflection hints có các type tùy biến cần thiết.
- Resource hints có mapping/resource được nạp động.
- Generated proxy bytecode và JDK proxy metadata phù hợp với Spring bean cần proxy.
- Hibernate integration metadata có trong artifact native build.

Đường dẫn AOT output phụ thuộc Spring Boot/build tool version. Với các dòng Spring Boot 3.x thường gặp, Maven tạo output dưới `target/spring-aot/main/`, còn Gradle thường dùng `build/generated/aotSources`, `build/generated/aotClasses` và `build/generated/aotResources`. Hãy dùng log/task output của đúng plugin thay vì hard-code đường dẫn cho mọi version.

### 12.3. Native integration tests với database thật

Chạy native executable kết nối tới cùng loại database và JDBC driver mà production sử dụng. Có thể dùng Testcontainers hoặc database test riêng, miễn là test thực thi binary native chứ không chỉ test JVM.

Các case nên có:

| Case | Hành động | Điều cần chứng minh |
|---|---|---|
| JPA bootstrap | Khởi tạo EntityManagerFactory | Hibernate, dialect và driver khởi tạo được |
| Persist/load | Lưu, flush, clear, đọc lại entity | Entity metadata và constructor hoạt động |
| Lazy to-one | Đọc entity, kiểm tra loaded, truy cập association trong transaction | Hibernate proxy/interception hoạt động |
| Lazy collection | Truy cập collection trong transaction | Collection wrapper và fetch path hoạt động |
| Detached access | Truy cập lazy association sau khi persistence context đóng | Ứng dụng xử lý đúng `LazyInitializationException` |
| EntityGraph | Query với graph và kiểm tra association | Fetch plan và query đúng |
| Repository query | Chạy derived query và `@Query` | Repository AOT/runtime hoạt động |
| Projection | Đọc interface/DTO projection | Constructor/accessor metadata phù hợp |
| Custom converter/listener | Lưu và tải type tùy biến | Reflection/instantiation path hoạt động |
| Mapping resource | Nạp XML/custom mapping | Resource có mặt và Hibernate dùng được |
| Transaction | Commit/rollback và optimistic lock | Transaction integration hoạt động |
| Enhancement | Đọc lazy basic field và cập nhật mutable field | Entity bytecode đã enhance và semantics đúng |

### 12.4. Test lazy loading và enhancement bằng trạng thái loaded

Ví dụ integration test:

```java
@Test
@Transactional
void loadsCustomerOnlyWhenRequested() {
    PurchaseOrder order = entityManager.find(
            PurchaseOrder.class, existingOrderId);

    PersistenceUnitUtil util = entityManagerFactory
            .getPersistenceUnitUtil();

    assertThat(util.isLoaded(order, "customer")).isFalse();

    String customerName = order.getCustomer().getName();

    assertThat(customerName).isNotBlank();
    assertThat(util.isLoaded(order, "customer")).isTrue();
}
```

Kỳ vọng cụ thể phụ thuộc mapping, query và Hibernate version. Nếu test dùng `join fetch` hoặc EntityGraph, association đã được tải từ đầu và assertion ban đầu phải thay đổi theo fetch plan.

Với lazy basic attribute, test cần xác nhận enhancer đã chạy và provider hỗ trợ use case. Không dùng một test đơn lẻ trên JVM làm bằng chứng rằng native executable có đủ metadata.

### 12.5. Kiểm tra SQL và hiệu năng

Bên cạnh correctness, ghi nhận:

- Số query cho một request.
- Query phát sinh khi truy cập lazy association.
- Query count trước và sau khi dùng EntityGraph/join fetch.
- Kết quả dirty tracking sau flush.
- Thời gian khởi tạo EntityManagerFactory.
- Startup time, RSS và memory khi xử lý workload đại diện.

Không so sánh chỉ startup time. Native image có thể khởi động nhanh hơn nhưng query plan, số round trip hoặc pool sizing vẫn quyết định phần lớn latency của API dữ liệu.

## 13. Các lỗi thường gặp và cách chẩn đoán

| Triệu chứng | Nguyên nhân có thể | Cần kiểm tra |
|---|---|---|
| EntityManagerFactory không khởi tạo trong native | Hibernate version, provider, driver hoặc metadata không tương thích | Dependency tree, Hibernate logs, native metadata |
| `ClassNotFoundException` cho entity/converter | Type không nằm trong managed set hoặc classpath | `@EntityScan`, `PersistenceManagedTypes`, dependency graph |
| `NoSuchMethodException` khi tạo entity | Constructor/metadata hoặc enhancer khác với runtime expectation | Entity constructor, generated bytecode và reflection hints |
| Lazy association lỗi trong native | Hibernate proxy/interception path hoặc metadata thiếu | Hibernate version, proxy support, transaction scope |
| `LazyInitializationException` | Persistence context đã đóng trước khi truy cập | Transaction boundary và DTO mapping |
| `ClassCastException`/proxy type không như dự kiến | Giả định concrete class thay cho proxy/interface | Entity inheritance, proxy strategy và polymorphic association |
| Lazy basic field luôn được tải ngay | Bytecode enhancement chưa chạy hoặc `@Basic(fetch=LAZY)` không được hỗ trợ trong cấu hình | Gradle/Maven enhancer task, output classes và query log |
| Dirty tracking bỏ sót thay đổi | Mutable object bị sửa bên trong thay vì thay reference | Enhancement mode và cách cập nhật value |
| Repository method lỗi chỉ ở native | AOT repository không hỗ trợ method pattern hoặc hint thiếu | Spring Data version, query type và AOT output |
| Mapping XML không tìm thấy | Resource không được đóng gói hoặc resource pattern thiếu | JAR contents và resource hints |
| Dialect sai khi chạy production | Dialect đã được quyết định/freeze ở AOT build | Build-time properties và database target |
| Chỉ lỗi với một JDBC driver | Driver version hoặc reachability metadata không phù hợp | Driver compatibility và native-image documentation |

Không chữa mọi lỗi Hibernate bằng cách thêm `allDeclaredMethods` cho toàn bộ package. Hãy xác định lỗi nằm ở Spring proxy, Hibernate proxy, enhancement, managed type, resource, service loading hay database integration.

## 14. Quy trình kiểm chứng trước khi phát hành

1. **Resolve version:** ghi lại Spring Boot, Spring Framework, Spring Data JPA, Hibernate ORM, Hibernate enhancer, JDBC driver và GraalVM.
2. **Kiểm tra compatibility:** dùng BOM và compatibility matrix của đúng release; không override riêng Hibernate nếu chưa có lý do.
3. **Xác định persistence model:** liệt kê entity, embeddable, converter, listener, custom type, repository và mapping resource.
4. **Kiểm tra lazy behavior:** xác định association nào dùng proxy, field nào cần bytecode enhancement và fetch plan của từng use case.
5. **Chạy enhancer nếu cần:** xác nhận plugin thực sự biến đổi entity bytecode và version khớp Hibernate runtime.
6. **Chạy Spring AOT:** xác nhận ManagedTypes, repository metadata, reflection/resource hints được sinh.
7. **Kiểm tra artifact:** xác minh JDBC driver, mapping XML, migration resource và native metadata có trong native build input.
8. **Build native:** dùng toolchain và cấu hình giống pipeline phát hành.
9. **Chạy integration test native:** thực hiện persist/load, lazy access, repository query, converter, transaction và migration.
10. **Kiểm tra SQL/performance:** xác nhận không có N+1 ngoài dự kiến và số query phù hợp.
11. **Ghi baseline:** lưu version, AOT settings, native build args, database/driver và kết quả test để so sánh khi nâng cấp.

## 15. Checklist JPA/Hibernate Native Image

- [ ] Spring Boot, Spring Framework, Spring Data JPA, Hibernate và GraalVM nằm trong tổ hợp version được hỗ trợ.
- [ ] Không override Hibernate ORM ngoài BOM nếu chưa kiểm tra compatibility.
- [ ] Entity được phát hiện trong ManagedTypes/AOT output.
- [ ] `@EntityScan` hoặc cấu hình persistence unit bao phủ đủ entity package.
- [ ] Converter, listener, custom type và entity callback được kiểm tra.
- [ ] Đã phân biệt Spring AOP proxy với Hibernate lazy proxy.
- [ ] Entity class đáp ứng yêu cầu proxy/subclass của mapping đang dùng.
- [ ] Lazy association được test trong transaction và sau khi persistence context đóng.
- [ ] Fetch plan tránh N+1 query và được kiểm tra trên native runtime.
- [ ] Nếu dùng lazy basic attribute, bytecode enhancer đã thực sự chạy.
- [ ] Enhancement plugin version khớp Hibernate ORM.
- [ ] Dirty tracking đã được kiểm tra với mutable values, array và collection.
- [ ] Spring Data repository AOT chỉ được kỳ vọng cho method pattern được hỗ trợ.
- [ ] Reflection/resource hints tùy biến đã được kiểm tra; không khai báo rộng trùng hints framework.
- [ ] Mapping XML và resource nạp động có mặt trong native image.
- [ ] JDBC driver và dialect tương thích với GraalVM/native runtime.
- [ ] Dialect/build-time settings khớp database mục tiêu.
- [ ] Hibernate native extension (nếu dùng) được kiểm tra theo version và trạng thái hỗ trợ.
- [ ] Native executable đã chạy integration tests với database thực tế hoặc Testcontainers.
- [ ] SQL count, transaction, lazy loading và query semantics đã được xác nhận.

## 16. Ghi nhớ

Trong Spring Boot Native Image, JPA/Hibernate cần được kiểm chứng ở nhiều lớp. Spring AOT chuẩn bị bean definitions, repository metadata và runtime hints. Hibernate quản lý entity proxy, collection lazy loading và bytecode enhancement. GraalVM cần metadata cho những đường truy cập động mà phân tích tĩnh không suy ra được.

Hãy phân biệt rõ ba việc: **proxy lazy loading**, **bytecode enhancement** và **metadata native image**. Enhancement có thể hỗ trợ lazy basic attribute và dirty tracking nhưng không loại bỏ mọi proxy. Spring Data JPA đóng góp ManagedTypes và hints nhưng không thay thế test của JDBC driver, dialect, mapping resource hoặc Hibernate runtime. Bằng chứng cuối cùng phải đến từ integration test chạy trên chính native executable với database và dependency version mà ứng dụng sẽ phát hành.

### Tài liệu tham khảo

- [Spring Boot — Introducing GraalVM Native Images](https://docs.spring.io/spring-boot/reference/packaging/native-image/introducing-graalvm-native-images.html)
- [Spring Framework — Ahead-of-Time Optimizations](https://docs.spring.io/spring-framework/reference/core/aot.html)
- [Spring Data JPA — Ahead of Time Optimizations](https://docs.spring.io/spring-data/jpa/reference/jpa/aot.html)
- [Spring Framework 6.x Upgrade Guide — Hibernate requirement for native image](https://github.com/spring-projects/spring-framework/wiki/Upgrading-to-Spring-Framework-6.x)
- [Hibernate ORM — Proxies and Lazy Fetching](https://docs.hibernate.org/stable/core/introduction/html_single/#proxies-and-lazy-fetching)
- [Hibernate ORM — Bytecode Enhancer](https://docs.hibernate.org/stable/core/introduction/html_single/#using-the-bytecode-enhancer)
- [Hibernate ORM — Entity Proxy User Guide](https://docs.hibernate.org/orm/6.6/userguide/html_single/#entity-proxy)
- [Hibernate ORM — Integration Modules](https://docs.hibernate.org/stable/orm/quickstart/html_single/)
- [GraalVM Native Image — Reachability Metadata](https://www.graalvm.org/latest/reference-manual/native-image/metadata/)


