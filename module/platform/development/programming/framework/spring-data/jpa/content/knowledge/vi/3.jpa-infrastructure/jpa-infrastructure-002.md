# Persistence unit, PersistenceContext và vòng đời tài nguyên trong Spring Data JPA

Tài liệu này giải thích cách JPA tổ chức cấu hình persistence, tạo và quản lý `EntityManagerFactory`, cấp phát `EntityManager`, gắn persistence context với transaction và giải phóng tài nguyên. Đây là phần hạ tầng quyết định entity được quản lý trong phạm vi nào, truy vấn dùng cấu hình database nào và khi nào kết nối được trả về connection pool.

Các ví dụ dùng namespace `jakarta.persistence` của Jakarta Persistence và Spring Framework 6 / Spring Boot 3 trở lên. Dự án Spring Boot 2 cũ thường dùng `javax.persistence`; không trộn hai namespace trong cùng một ứng dụng.

## 1. Bức tranh tổng thể

Các khái niệm liên quan nhưng không đồng nghĩa:

- **Persistence unit** là một đơn vị cấu hình logic của JPA: tập entity được quản lý, provider, nguồn kết nối, transaction type và các thiết lập mapping/cache/validation.
- **EntityManagerFactory (EMF)** là factory được tạo từ một persistence unit. Nó giữ metadata và hạ tầng của provider, rồi tạo các EntityManager.
- **EntityManager (EM)** là API làm việc với entity trong một persistence context. Nó thực hiện persist, find, merge, remove, query và flush.
- **Persistence context** là phạm vi quản lý các entity instance. Trong phạm vi đó, JPA theo dõi trạng thái entity, định danh và thay đổi cần đồng bộ xuống database.
- **Transaction** là ranh giới commit/rollback của các thao tác database. Persistence context và transaction thường gắn với nhau trong cách dùng phổ biến của Spring.
- **Connection** là kết nối vật lý hoặc logic tới database do DataSource/connection pool cung cấp. EntityManager không đồng nghĩa với một connection luôn được giữ mở suốt vòng đời của nó.

Luồng thường gặp trong một ứng dụng Spring:

`Application service → EntityManager proxy → EntityManager gắn với transaction → JPA provider → JDBC connection → Database`

Ở đây Spring quản lý transaction và vòng đời EntityManager thật. Code nghiệp vụ thường chỉ thấy một tham chiếu EntityManager được inject.

## 2. Persistence unit là gì?

Persistence unit là cấu hình đặt tên cho một tập hợp các lớp persistence và các thiết lập liên quan. Nó trả lời những câu hỏi như:

- Entity nào thuộc phạm vi quản lý của unit này?
- JPA provider nào sẽ triển khai Jakarta Persistence?
- Unit dùng DataSource/JDBC connection hay JTA?
- Mapping file, converter, listener, cache và validation được cấu hình ra sao?
- Schema generation và các thuộc tính riêng của provider được đặt như thế nào?

Một persistence unit thường tương ứng với một miền database hoặc một nhóm entity cần được quản lý bởi cùng cấu hình. Nó **không phải** là một transaction, một session, một schema hay một database name.

Một ứng dụng có thể có một persistence unit hoặc nhiều unit. Với một database và một tập entity thông thường, Spring Boot thường tự cấu hình một unit. Ứng dụng kết nối nhiều database, tách miền dữ liệu hoặc cần hai nhóm entity/provider độc lập có thể cần nhiều persistence unit và nhiều EntityManagerFactory.

### 2.1. Cấu hình bằng persistence.xml

Theo Jakarta Persistence, cấu hình chuẩn có thể được đặt trong file `META-INF/persistence.xml` bên trong classpath hoặc persistence archive. Ví dụ tối giản cho Java SE:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<persistence xmlns="https://jakarta.ee/xml/ns/persistence"
             version="3.1">
    <persistence-unit name="catalog"
                     transaction-type="RESOURCE_LOCAL">
        <provider>org.hibernate.jpa.HibernatePersistenceProvider</provider>
        <class>com.example.catalog.Product</class>
        <properties>
            <property name="jakarta.persistence.jdbc.url"
                      value="jdbc:postgresql://localhost:5432/catalog"/>
            <property name="jakarta.persistence.jdbc.user"
                      value="app"/>
            <property name="jakarta.persistence.jdbc.password"
                      value="change-me"/>
            <property name="jakarta.persistence.jdbc.driver"
                      value="org.postgresql.Driver"/>
        </properties>
    </persistence-unit>
</persistence>
```

Giải thích:

- `name="catalog"` là tên persistence unit. Có thể dùng tên này trong `@PersistenceContext(unitName = "catalog")` hoặc `@PersistenceUnit(unitName = "catalog")`.
- `transaction-type="RESOURCE_LOCAL"` cho biết transaction được điều khiển qua API transaction cục bộ của EntityManager. Trong môi trường Jakarta EE có JTA, unit có thể dùng `JTA`.
- `provider` chỉ định implementation, ví dụ Hibernate. Khi chỉ dùng một provider mặc định, một số cấu hình có thể không cần ghi rõ mục này.
- `class` liệt kê entity được quản lý. Có thể khai báo thêm mapping file, jar, class converter hoặc listener tùy cấu hình.
- `properties` chứa thuộc tính chuẩn Jakarta Persistence hoặc thuộc tính riêng của provider. Các thuộc tính kết nối trong ví dụ phù hợp cho minh họa; ứng dụng thực tế nên lấy bí mật từ secret manager hoặc biến môi trường.

Trong Jakarta EE, container có thể cung cấp DataSource và transaction manager qua JNDI/JTA. Khi đó cấu hình kết nối và transaction khác với ví dụ Java SE ở trên.

### 2.2. Spring Boot thường không cần persistence.xml

Trong Spring Boot với Spring Data JPA, auto-configuration thường tạo DataSource, EntityManagerFactory và transaction manager dựa trên dependency, cấu hình datasource và các entity được scan. Hibernate thường là provider mặc định khi dùng starter JPA và không thay thế provider khác.

Ví dụ cấu hình:

```properties
spring.datasource.url=jdbc:postgresql://localhost:5432/catalog
spring.datasource.username=app
spring.datasource.password=${DB_PASSWORD}

spring.jpa.hibernate.ddl-auto=validate
spring.jpa.open-in-view=false
spring.jpa.properties.hibernate.format_sql=true
```

Các thiết lập thường gặp:

- `spring.datasource.*` cấu hình DataSource và kết nối database.
- `spring.jpa.hibernate.ddl-auto` điều khiển hành vi schema của Hibernate, ví dụ `validate`, `update`, `create` hoặc `create-drop`. Với production, cần chọn chính sách migration rõ ràng; không mặc định dùng `update`.
- `spring.jpa.properties.*` chuyển tiếp thuộc tính cho provider.
- `spring.jpa.open-in-view` điều khiển Open EntityManager in View trong ứng dụng web. Tắt nó thường giúp ranh giới truy cập dữ liệu rõ hơn và buộc service tải dữ liệu cần thiết trong transaction.

Spring Boot cũng tự tìm entity trong package phù hợp từ package của lớp cấu hình chính. Có thể dùng `@EntityScan` khi entity nằm ở package khác. Vì vậy, trong ứng dụng Boot thông thường không cần tự tạo `persistence.xml` chỉ để khai báo entity.

## 3. EntityManagerFactory: factory cấp phát EntityManager

### 3.1. Vai trò và đặc tính

EntityManagerFactory được tạo cho một persistence unit. Khi khởi tạo, provider xử lý metadata entity, mapping, query plan/cache phù hợp và cấu hình kết nối. EMF sau đó tạo EntityManager theo yêu cầu.

Các điểm quan trọng:

- **Nặng và tốn chi phí khởi tạo:** không tạo mới EMF cho mỗi request hoặc mỗi transaction.
- **Có thể dùng đồng thời:** EntityManagerFactory được thiết kế để chia sẻ giữa các thread trong ứng dụng.
- **Một unit thường có một EMF:** nếu có nhiều persistence unit thì thường có một EMF tương ứng cho mỗi unit.
- **Có vòng đời cấp ứng dụng:** Spring container thường tạo EMF khi khởi động context và đóng nó khi context shutdown.
- **Không phải connection pool:** EMF tạo EntityManager; DataSource/connection pool quản lý việc cấp phát connection tới database.

Trong Spring Boot, không nên tự gọi `close()` trên EMF do container quản lý. Hãy để Spring thực hiện lifecycle callback khi ứng dụng dừng.

### 3.2. Lấy EntityManagerFactory

Có thể inject EMF bằng `@PersistenceUnit`:

```java
import jakarta.persistence.EntityManagerFactory;
import jakarta.persistence.PersistenceUnit;
import org.springframework.stereotype.Component;

@Component
public class JpaInfrastructureInfo {
    @PersistenceUnit
    private EntityManagerFactory entityManagerFactory;

    public boolean isOpen() {
        return entityManagerFactory.isOpen();
    }
}
```

`@PersistenceUnit` dành cho EntityManagerFactory. Đây là lựa chọn khi cần tạo EntityManager thủ công, đọc metadata qua factory hoặc gọi API factory.

Nếu ứng dụng tự quản lý EntityManager bằng `createEntityManager()`, ứng dụng cũng phải tự quản lý transaction và đóng EntityManager. Trong Spring service thông thường, ưu tiên để Spring quản lý thay vì tự tạo.

### 3.3. Khi nào cần nhiều EntityManagerFactory?

Ví dụ hệ thống có database đơn hàng và database báo cáo độc lập. Mỗi nhóm entity cần DataSource, package scan và transaction manager riêng. Một cấu hình đại diện:

```java
@Configuration
@EnableJpaRepositories(
    basePackages = "com.example.orders.repository",
    entityManagerFactoryRef = "ordersEntityManagerFactory",
    transactionManagerRef = "ordersTransactionManager"
)
public class OrdersJpaConfig {

    @Bean
    public LocalContainerEntityManagerFactoryBean ordersEntityManagerFactory(
            @Qualifier("ordersDataSource") DataSource dataSource,
            JpaVendorAdapter vendorAdapter) {

        var factory = new LocalContainerEntityManagerFactoryBean();
        factory.setDataSource(dataSource);
        factory.setPackagesToScan("com.example.orders.domain");
        factory.setPersistenceUnitName("orders");
        factory.setJpaVendorAdapter(vendorAdapter);
        factory.setJpaPropertyMap(Map.of(
            "hibernate.hbm2ddl.auto", "validate"
        ));
        return factory;
    }

    @Bean
    public PlatformTransactionManager ordersTransactionManager(
            @Qualifier("ordersEntityManagerFactory")
            EntityManagerFactory entityManagerFactory) {
        return new JpaTransactionManager(entityManagerFactory);
    }
}
```

Đây là cấu hình minh họa phần JPA cho một unit; ứng dụng phải khai báo bean DataSource và JpaVendorAdapter tương ứng, cùng cấu hình cho unit còn lại. Khi có nhiều repository package, mỗi `@EnableJpaRepositories` cần trỏ đúng `entityManagerFactoryRef` và `transactionManagerRef`.

Có nhiều EMF không có nghĩa một `@Transactional` tự động bao trùm tất cả database. Chọn transaction manager bằng qualifier hoặc cấu hình mặc định rõ ràng. Nếu nghiệp vụ phải cập nhật nhiều database trong một giao dịch nguyên tử, cần thiết kế JTA/XA hoặc một chiến lược nhất quán phân tán phù hợp; hai local transaction manager riêng không tự tạo thành distributed transaction.

## 4. PersistenceContext và EntityManager

### 4.1. Persistence context

Persistence context là vùng mà JPA theo dõi các entity instance. Nó duy trì identity map: trong cùng một persistence context, một entity type và primary key thường tương ứng với một instance được quản lý.

Một entity có thể ở các trạng thái:

- **New / transient:** đối tượng Java mới tạo, chưa được persistence context quản lý.
- **Managed:** đang được persistence context quản lý; thay đổi có thể được phát hiện và ghi xuống database khi flush.
- **Detached:** từng được quản lý nhưng hiện không còn gắn với persistence context.
- **Removed:** được đánh dấu xóa; lệnh DELETE được đồng bộ khi flush.

Một số thao tác chính:

| API | Ý nghĩa |
|---|---|
| `persist(entity)` | Đưa entity mới vào trạng thái managed; INSERT thường được thực hiện khi flush hoặc theo chiến lược ID/provider |
| `find(Type.class, id)` | Tìm entity theo primary key; có thể lấy từ persistence context trước khi truy vấn database |
| `merge(entity)` | Sao chép trạng thái từ đối tượng truyền vào sang instance managed và trả về instance managed đó |
| `remove(entity)` | Đánh dấu entity managed để xóa |
| `detach(entity)` | Tách một entity khỏi persistence context |
| `clear()` | Tách tất cả entity khỏi persistence context |
| `refresh(entity)` | Nạp lại trạng thái từ database, ghi đè thay đổi chưa flush của entity |
| `flush()` | Đồng bộ thay đổi của persistence context xuống database trong transaction hiện tại |

Lưu ý đặc biệt về `merge`: object truyền vào không tự trở thành managed. Giá trị trả về mới là instance được quản lý. Nếu tiếp tục sửa object ban đầu, các thay đổi sau đó không tự động được dirty checking.

### 4.2. EntityManager

EntityManager là API làm việc với persistence context. Nó giữ trạng thái và không thread-safe. Không chia sẻ cùng một EntityManager thật cho nhiều thread đồng thời.

EntityManager thường cung cấp:

- CRUD và lifecycle operation cho entity.
- JPQL, Criteria API, native query và named query.
- Kiểm tra trạng thái managed/detached.
- Flush và clear persistence context.
- Truy cập transaction API trong chế độ RESOURCE_LOCAL.
- Truy cập metamodel và các tiện ích persistence.

EntityManager không nên được xem như một DAO stateless hoặc một singleton dùng chung. Trong ứng dụng Spring, tham chiếu được inject thường là proxy chia sẻ; proxy tìm EntityManager gắn với transaction hiện tại. EntityManager thật phía sau proxy vẫn có lifecycle riêng và không được dùng tùy tiện qua nhiều thread.

## 5. @PersistenceContext và @PersistenceUnit khác nhau thế nào?

Hai annotation này phục vụ hai mục đích khác nhau:

| Annotation | Đối tượng được inject | Mục đích |
|---|---|---|
| `@PersistenceContext` | EntityManager reference | Thực hiện thao tác với entity trong persistence context |
| `@PersistenceUnit` | EntityManagerFactory | Tạo EntityManager hoặc dùng API của factory |

Ví dụ:

```java
import jakarta.persistence.EntityManager;
import jakarta.persistence.PersistenceContext;
import org.springframework.stereotype.Repository;

@Repository
public class ProductRepositorySupport {

    @PersistenceContext
    private EntityManager entityManager;

    public Product findProduct(Long id) {
        return entityManager.find(Product.class, id);
    }
}
```

`@PersistenceContext` là cách tiêu chuẩn để yêu cầu container cấp một EntityManager reference. Trong Spring, framework hỗ trợ annotation này và thường inject shared EntityManager proxy. Proxy sẽ sử dụng EntityManager gắn với transaction hiện tại nếu có.

Có thể chỉ rõ unit khi ứng dụng có nhiều persistence unit:

```java
@PersistenceContext(unitName = "orders")
private EntityManager ordersEntityManager;

@PersistenceUnit(unitName = "orders")
private EntityManagerFactory ordersEntityManagerFactory;
```

Nếu chỉ có một EntityManagerFactory, thường có thể bỏ `unitName`. Khi có nhiều factory, khai báo unit name hoặc qualifier rõ ràng giúp tránh inject nhầm persistence context.

### 5.1. Shared EntityManager trong Spring

Trong ứng dụng Spring imperative, shared EntityManager proxy thường hoạt động như sau:

1. Service được gọi qua Spring proxy và transaction được mở bởi `@Transactional`.
2. `JpaTransactionManager` lấy một EntityManager từ EntityManagerFactory.
3. Spring gắn EntityManager với transaction hiện tại trong thread-bound transaction context.
4. Khi repository hoặc service gọi EntityManager proxy, proxy tìm và ủy quyền cho EntityManager đang gắn với transaction.
5. Khi transaction commit hoặc rollback, Spring kết thúc persistence context gắn với transaction và giải phóng tài nguyên liên quan.
6. Lần gọi tiếp theo trong transaction khác sẽ sử dụng EntityManager khác.

Nếu không có transaction đang hoạt động, shared proxy có thể tạo EntityManager tạm cho thao tác và đóng nó sau thao tác đó. Đây là một lý do truy cập lazy relation sau khi service trả về thường thất bại khi Open EntityManager in View bị tắt.

Không gọi `close()` trên EntityManager được inject bằng `@PersistenceContext`. Đó là reference do container/Spring quản lý; ứng dụng không sở hữu vòng đời của nó.

## 6. Transaction-scoped và extended persistence context

Persistence context có thể có phạm vi sống khác nhau. Cần phân biệt thời gian sống của persistence context với thời gian sống của EntityManager proxy hoặc của connection.

### 6.1. Transaction-scoped persistence context

Đây là mô hình phổ biến trong ứng dụng Spring Data JPA:

- Persistence context gắn với transaction đang hoạt động.
- Entity được load trong transaction sẽ được quản lý trong phạm vi context đó.
- Khi transaction commit hoặc rollback, context kết thúc và các entity được giữ trong context trở thành detached.
- Transaction tiếp theo thường dùng persistence context/EntityManager mới.

Ví dụ:

```java
@Service
public class ProductService {

    @PersistenceContext
    private EntityManager entityManager;

    @Transactional
    public void rename(Long id, String newName) {
        Product product = entityManager.find(Product.class, id);
        if (product == null) {
            throw new IllegalArgumentException("Product not found");
        }

        product.setName(newName);
        // Dirty checking sẽ ghi thay đổi khi flush/commit.
    }
}
```

Trong transaction này, `product` là managed. Không cần gọi `save` chỉ để cập nhật thuộc tính của entity đang managed; dirty checking sẽ nhận biết thay đổi. Tuy nhiên, nếu entity đã detached hoặc được tạo mới, cần dùng thao tác phù hợp như merge/persist hoặc repository save.

### 6.2. Extended persistence context

Extended persistence context có thể tồn tại qua nhiều transaction và giữ entity managed giữa các transaction. Mô hình này thường gắn với thành phần có stateful lifecycle trong Jakarta EE.

Nó có thể hữu ích cho một quy trình nghiệp vụ nhiều bước cần giữ một nhóm entity managed lâu hơn một transaction. Tuy nhiên:

- Persistence context tồn tại lâu có thể giữ nhiều entity trong bộ nhớ.
- Entity state có thể cũ so với dữ liệu do transaction khác cập nhật.
- Cần xác định rõ thời điểm flush, đồng bộ và kết thúc context.
- Không nên đặt một EntityManager extended vào singleton service được gọi đồng thời bởi nhiều request.
- Trong Spring, hỗ trợ extended context và lifecycle phụ thuộc cách cấu hình, scope bean và provider; phải thiết kế owner có lifecycle rõ ràng thay vì mặc định dùng cho service stateless.

Đối với phần lớn REST API và service Spring, transaction-scoped persistence context là lựa chọn đơn giản và dễ kiểm soát hơn.

## 7. Vòng đời tài nguyên theo từng mô hình

### 7.1. EntityManager do Spring quản lý

Khi dùng `@PersistenceContext`:

- Spring tạo và quản lý EntityManagerFactory.
- Spring cung cấp EntityManager proxy cho bean.
- EntityManager thật được lấy và gắn với transaction khi cần.
- Transaction manager thực hiện commit/rollback.
- Spring đóng hoặc giải phóng EntityManager thật khi persistence context kết thúc.
- Code nghiệp vụ không gọi `close()` trên EntityManager proxy.

Đây là cách khuyến nghị cho Spring service và repository thông thường.

### 7.2. EntityManager do ứng dụng tự tạo

Khi gọi `entityManagerFactory.createEntityManager()`, ứng dụng sở hữu EntityManager được tạo ra và phải đóng nó. Với RESOURCE_LOCAL, ứng dụng còn phải bắt đầu, commit hoặc rollback transaction:

```java
EntityManager entityManager =
        entityManagerFactory.createEntityManager();
EntityTransaction transaction = entityManager.getTransaction();

try {
    transaction.begin();

    Product product = entityManager.find(Product.class, 1L);
    if (product != null) {
        product.setName("Updated name");
    }

    transaction.commit();
} catch (RuntimeException exception) {
    if (transaction.isActive()) {
        transaction.rollback();
    }
    throw exception;
} finally {
    entityManager.close();
}
```

Đây là ví dụ Java SE với RESOURCE_LOCAL, không phải mẫu cần dùng bên trong Spring service đã có `@Transactional`. Trong môi trường JTA hoặc container-managed transaction, transaction API khác và không nên gọi `EntityTransaction` theo cách này.

Quy tắc quan trọng: mọi EntityManager tự tạo phải được đóng trong `finally` hoặc cơ chế try/finally tương đương, kể cả khi query, flush hay commit ném exception.

### 7.3. EntityManagerFactory do ứng dụng quản lý

Trong Java SE, nếu ứng dụng tự tạo EMF bằng `Persistence.createEntityManagerFactory("catalog")`, ứng dụng phải gọi `close()` khi hoàn tất sử dụng. Trong Spring, nếu EMF được khai báo như bean hoặc do Boot auto-configure, để container đóng khi ApplicationContext dừng.

Không tạo EMF bên trong mỗi request. EMF là tài nguyên cấp ứng dụng; EntityManager là tài nguyên theo unit of work.

### 7.4. Connection và connection pool

EntityManager không nhất thiết giữ một JDBC connection từ lúc được tạo tới lúc bị đóng. Provider có thể lấy connection khi cần và trả về pool tùy transaction, provider và cấu hình connection handling.

Trong transaction, connection thường được giữ tới khi transaction kết thúc để bảo đảm tính nhất quán. Khi transaction kết thúc, connection được trả về pool thay vì đóng socket vật lý trong mọi trường hợp.

Vì vậy, cần theo dõi cả ba lifecycle riêng:

1. ApplicationContext / EntityManagerFactory.
2. EntityManager / persistence context.
3. JDBC connection / connection pool.

Đóng EntityManager đúng thời điểm giúp provider giải phóng persistence context và connection liên quan. Đóng EMF đúng thời điểm giúp giải phóng hạ tầng provider. Connection pool lại có cấu hình kích thước, timeout, idle lifetime và leak detection riêng.

## 8. Flush, commit và thời điểm dữ liệu được ghi

Flush và commit không phải một thao tác:

- **Flush** đồng bộ thay đổi đang được persistence context quản lý thành SQL INSERT/UPDATE/DELETE gửi tới database.
- **Commit** xác nhận transaction và làm thay đổi trở nên bền vững theo transaction semantics của database.
- **Rollback** hủy các thay đổi database chưa commit; nó không biến một transaction đã commit thành chưa commit.

JPA có hai flush mode thường gặp:

- `FlushModeType.AUTO`: provider phải bảo đảm query nhìn thấy các thay đổi liên quan cần thiết; provider có thể flush trước query.
- `FlushModeType.COMMIT`: provider có thể trì hoãn flush cho tới commit, nhưng ứng dụng không nên dựa vào việc mọi query sẽ thấy thay đổi chưa flush theo cách giống nhau.

Có thể gọi `entityManager.flush()` để yêu cầu đồng bộ sớm, ví dụ nhằm phát hiện constraint violation trước khi rời một đoạn xử lý. Flush không commit transaction; lỗi constraint có thể xuất hiện tại flush hoặc commit.

Ví dụ:

```java
@Transactional
public Long createProduct(String name) {
    Product product = new Product(name);
    entityManager.persist(product);
    entityManager.flush();

    // Sau flush, ID do database cấp thường đã có.
    // Transaction vẫn chưa commit tại dòng này.
    return product.getId();
}
```

Không cần gọi flush sau mỗi thay đổi. Gọi quá thường xuyên có thể làm tăng số lần round trip. Hãy để transaction commit flush tự động trừ khi có lý do cụ thể cần đồng bộ sớm.

## 9. Spring transaction và EntityManager

### 9.1. JpaTransactionManager

Trong ứng dụng Spring dùng một EntityManagerFactory cho một DataSource, `JpaTransactionManager` là transaction manager thường gặp. Nó:

- Bắt đầu transaction cho EntityManager.
- Gắn EntityManager với transaction hiện tại.
- Phối hợp với các thao tác JDBC cùng DataSource khi cấu hình phù hợp.
- Thực hiện commit hoặc rollback.
- Đóng/giải phóng EntityManager khi kết thúc transaction.

`@Transactional` thường được đặt ở service boundary để nhiều thao tác repository cùng tham gia một transaction:

```java
@Service
public class CheckoutService {

    private final OrderRepository orderRepository;
    private final InventoryRepository inventoryRepository;

    public CheckoutService(
            OrderRepository orderRepository,
            InventoryRepository inventoryRepository) {
        this.orderRepository = orderRepository;
        this.inventoryRepository = inventoryRepository;
    }

    @Transactional
    public void checkout(Order order) {
        orderRepository.save(order);
        inventoryRepository.reserve(order.getItems());
    }
}
```

Nếu `reserve` ném runtime exception và exception được truyền ra khỏi transaction boundary, transaction mặc định sẽ rollback theo quy tắc rollback của Spring. Quy tắc rollback có thể cấu hình thêm cho checked exception bằng `rollbackFor`.

### 9.2. Transaction propagation

Khi một phương thức transactional gọi phương thức transactional khác, propagation quyết định chúng dùng transaction nào:

- `REQUIRED` (mặc định): tham gia transaction hiện tại; nếu chưa có thì tạo mới.
- `REQUIRES_NEW`: tạm treo transaction hiện tại và tạo transaction mới.
- `SUPPORTS`: tham gia nếu có; nếu không thì chạy không có transaction.
- `MANDATORY`: yêu cầu phải có transaction hiện tại.
- `NOT_SUPPORTED`: chạy không có transaction và treo transaction hiện tại nếu có.
- `NEVER`: yêu cầu không có transaction.
- `NESTED`: dùng nested transaction/savepoint nếu transaction manager hỗ trợ.

Propagation ảnh hưởng tới thời điểm persistence context được gắn và kết thúc. Đặc biệt, `REQUIRES_NEW` có thể tạo EntityManager/transaction mới trong khi context ngoài đang bị treo. Không dùng propagation chỉ để sửa một lỗi lazy loading mà chưa hiểu ranh giới dữ liệu.

### 9.3. Thread-bound và async

Trong cách dùng imperative phổ biến, Spring gắn transaction và EntityManager với thread hiện tại. Không truyền EntityManager hoặc entity proxy đang managed sang thread khác, `@Async`, executor hoặc callback chạy sau khi transaction đã kết thúc rồi mong chúng tiếp tục hoạt động.

Với tác vụ bất đồng bộ, hãy truyền ID hoặc dữ liệu cần thiết, sau đó mở transaction mới trong thread xử lý. Nếu cần nhiều transaction, hãy đặt ranh giới transaction rõ ràng ở mỗi bước.

JPA/JDBC là blocking. `@Transactional` của JPA không tự trở thành reactive transaction và không nên dùng EntityManager trong reactive event loop như một API non-blocking.

## 10. Open EntityManager in View (OSIV)

Open EntityManager in View là cơ chế giữ EntityManager mở trong suốt vòng đời một HTTP request, thường qua filter/interceptor. Mục đích lịch sử là cho phép view hoặc serialization truy cập lazy relation sau khi service transaction đã kết thúc.

Ưu điểm là giảm lỗi lazy loading xuất hiện ở tầng web. Nhược điểm:

- SQL có thể phát sinh trong lúc serialize response, ngoài service transaction.
- N+1 query có thể bị che khuất và khó quan sát.
- Tầng trình bày vô tình phụ thuộc vào persistence layer.
- Request giữ EntityManager lâu hơn transaction nghiệp vụ.
- Việc tải dữ liệu không còn tập trung tại service boundary.

Một cách thiết kế dễ kiểm soát là tắt OSIV và tải dữ liệu cần thiết trong transaction service bằng projection, DTO, fetch join hoặc entity graph. Sau khi service trả về, trả DTO đã hoàn chỉnh thay vì serialize entity graph có lazy relation.

OSIV không đồng nghĩa với extended persistence context. OSIV thường giữ EntityManager cho vòng đời HTTP request; extended persistence context là một loại persistence context có scope dài hơn transaction theo semantics của JPA.

## 11. Nhiều persistence unit và chọn đúng context

Trong ứng dụng có nhiều database hoặc nhiều nhóm entity, cần kiểm soát ba ánh xạ:

1. Repository package nào dùng EntityManagerFactory nào.
2. Entity package nào được factory quản lý.
3. Transactional service dùng transaction manager nào.

Một repository được scan dưới cấu hình factory sai có thể dẫn đến lỗi entity không được quản lý, query sai database hoặc transaction không bao trùm thao tác mong muốn.

Ví dụ dùng tên unit:

```java
@PersistenceContext(unitName = "orders")
private EntityManager ordersEntityManager;
```

Và transaction manager cụ thể:

```java
@Transactional("ordersTransactionManager")
public void updateOrder(...) {
    // Các thao tác dùng orders persistence unit.
}
```

Tên qualifier phải trùng với bean transaction manager thực tế. Nếu dùng nhiều transaction manager, đừng dựa vào việc Spring tự đoán đúng database theo tên repository.

Một transaction local trên database A và một transaction local trên database B là hai transaction độc lập. Nếu bước thứ hai thất bại sau khi bước thứ nhất đã commit, dữ liệu có thể lệch. Các lựa chọn gồm JTA/XA khi phù hợp, saga/outbox hoặc quy trình bù trừ nghiệp vụ.

## 12. Kiểm soát bộ nhớ và hiệu năng

Persistence context giữ các entity managed và snapshot cần cho dirty checking. Vì vậy:

- Transaction quá dài có thể giữ nhiều entity trong bộ nhớ và giữ connection lâu.
- Nạp hàng chục nghìn entity rồi giữ tất cả managed có thể tăng chi phí dirty checking.
- Batch insert/update cần cân nhắc flush và clear theo lô.
- `clear()` tách tất cả entity; sau đó các tham chiếu cũ trở thành detached. Không tiếp tục sửa chúng và mong dirty checking ghi dữ liệu.
- Không gọi `clear()` tùy tiện giữa logic cần giữ entity managed.
- EntityManagerFactory nên được tái sử dụng; tạo EMF lặp lại gây tốn metadata, cache và tài nguyên provider.
- Connection pool cần được cấu hình theo tải thực tế; tăng số connection không tự động làm database nhanh hơn.

Ví dụ xử lý batch theo lô:

```java
@Transactional
public void importProducts(List<ProductInput> inputs) {
    int batchSize = 50;

    for (int i = 0; i < inputs.size(); i++) {
        entityManager.persist(new Product(inputs.get(i).name()));

        if ((i + 1) % batchSize == 0) {
            entityManager.flush();
            entityManager.clear();
        }
    }
}
```

Sau `clear()`, các entity vừa persist không còn managed trong persistence context, nhưng các SQL đã flush vẫn nằm trong transaction và chưa commit cho tới khi transaction hoàn tất. Kích thước batch tối ưu phụ thuộc database, JDBC driver, provider và cấu hình batching.

## 13. Lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân có thể | Hướng kiểm tra |
|---|---|---|
| `No EntityManager with actual transaction available` | Code cần transaction nhưng đang chạy ngoài transaction hoặc dùng sai transaction manager | Kiểm tra `@Transactional`, proxy boundary, propagation và transaction manager |
| `LazyInitializationException` | Truy cập lazy relation khi persistence context đã đóng | Tải quan hệ trong service transaction, dùng DTO/projection hoặc fetch plan phù hợp |
| `Not an entity` / `Unknown entity` | Entity không nằm trong package scan hoặc persistence unit sai | Kiểm tra `@Entity`, `@EntityScan`, `packagesToScan`, unit name và mapping |
| Entity thay đổi nhưng database không cập nhật | Entity detached, không nằm trong persistence context hoặc transaction rollback | Kiểm tra trạng thái entity, cách merge/save và transaction outcome |
| `EntityManager is closed` | Dùng reference đã đóng hoặc tự đóng EntityManager do container quản lý | Không gọi close trên injected EntityManager; kiểm tra lifecycle tự quản lý |
| Lỗi inject sai EntityManagerFactory | Nhiều persistence unit nhưng thiếu `unitName` hoặc repository ref sai | Kiểm tra cấu hình EMF, `@EnableJpaRepositories` và qualifier |
| Connection pool cạn | Transaction dài, leak, truy vấn chậm hoặc pool quá nhỏ so với tải | Kiểm tra transaction duration, slow query, pool metrics và leak detection |
| Bộ nhớ tăng khi import dữ liệu | Persistence context tích lũy quá nhiều entity managed | Chia batch, flush/clear đúng chỗ và tránh transaction quá lớn |
| SQL chạy sau khi service đã trả về | OSIV hoặc lazy loading ở tầng web | Tắt OSIV và hoàn tất dữ liệu response tại service boundary |

Một số lỗi có thể xuất hiện tại flush hoặc commit chứ không phải tại dòng gọi `persist`. Hãy đọc root cause trong exception chain và kiểm tra SQL/transaction log để xác định thời điểm thực tế.

## 14. Quy trình debug một vấn đề lifecycle

Khi nghi ngờ EntityManager hoặc connection bị giữ quá lâu, kiểm tra theo thứ tự:

1. Xác định persistence unit và EntityManagerFactory mà repository/service đang dùng.
2. Xác định transaction manager được áp dụng cho phương thức.
3. Xác định phương thức có thực sự chạy qua Spring proxy hay bị self-invocation bỏ qua.
4. Xem transaction bắt đầu/kết thúc ở đâu, propagation nào được dùng và có exception khiến rollback hay không.
5. Xác định EntityManager là injected shared proxy hay do code gọi `createEntityManager()`.
6. Tìm các lời gọi `close()`, `clear()`, `flush()` và các tác vụ async sử dụng entity sau transaction.
7. Kiểm tra OSIV, lazy loading và query phát sinh ở tầng controller/serializer.
8. Quan sát connection pool, thời gian giữ connection, slow query và transaction duration.

Đừng kết luận connection leak chỉ từ việc EntityManager proxy vẫn tồn tại trong field của singleton service. Proxy có thể sống cùng bean, còn EntityManager thật được resolve theo transaction và được giải phóng theo lifecycle tương ứng.

## 15. Checklist thiết kế

- [ ] Mỗi persistence unit có tên, nhóm entity, DataSource và provider được xác định rõ.
- [ ] EntityManagerFactory được tạo một lần cho mỗi unit và do Spring container quản lý.
- [ ] Code nghiệp vụ dùng `@PersistenceContext` để nhận EntityManager reference.
- [ ] Chỉ dùng `@PersistenceUnit` khi cần EntityManagerFactory hoặc phải tự tạo EntityManager.
- [ ] EntityManager tự tạo luôn được đóng; EntityManager được inject không bị đóng thủ công.
- [ ] Transaction boundary nằm ở service layer và chọn đúng transaction manager.
- [ ] Không chia sẻ EntityManager thật hoặc entity managed qua nhiều thread.
- [ ] Persistence context mặc định có scope transaction; extended context chỉ dùng khi lifecycle owner được thiết kế rõ.
- [ ] Flush được dùng có chủ đích; không nhầm flush với commit.
- [ ] OSIV được cân nhắc rõ; dữ liệu response được tải trong transaction khi có thể.
- [ ] Nhiều persistence unit có repository scan, EMF và transaction manager mapping chính xác.
- [ ] Connection pool, transaction duration, query count và persistence context size được theo dõi.

## 16. Kết luận

Persistence unit định nghĩa phạm vi cấu hình JPA. EntityManagerFactory được tạo từ unit và là factory dùng chung cấp ứng dụng. EntityManager làm việc với persistence context, thường có scope theo transaction trong ứng dụng Spring. `@PersistenceContext` cung cấp EntityManager reference do Spring quản lý; `@PersistenceUnit` cung cấp EntityManagerFactory.

Trong Spring Data JPA thông thường, hãy để Spring quản lý EMF, EntityManager và transaction thông qua `@Transactional`. Tự tạo và đóng EntityManager chỉ khi thực sự chọn mô hình application-managed. Hiểu rõ các lifecycle riêng của persistence unit, factory, persistence context, transaction và connection giúp tránh lazy loading lỗi, rò rỉ tài nguyên, transaction không nhất quán và các truy vấn phát sinh ngoài dự kiến.
