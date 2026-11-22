# Cấu hình TransactionManager và liên kết với persistence unit

Spring Data JPA chỉ tham gia transaction đúng khi Spring biết **transaction manager nào điều khiển EntityManagerFactory nào**. Với một persistence unit, Spring Boot thường tự cấu hình toàn bộ chuỗi này. Khi ứng dụng có nhiều datasource hoặc nhiều persistence unit, cần khai báo rõ từng cặp repository, EntityManagerFactory và transaction manager để truy vấn và transaction đi vào đúng nơi.

Bài này tập trung vào mối liên kết đó trong Spring Boot 3.x, Spring Framework 6 và Jakarta Persistence.

## 1. Phân biệt bốn thành phần

| Thành phần | Vai trò | Ví dụ tên |
|---|---|---|
| DataSource | Cung cấp kết nối tới database | ordersDataSource |
| Persistence unit | Nhóm entity, mapping và cấu hình JPA được quản lý cùng nhau | orders |
| EntityManagerFactory | Tạo EntityManager cho một persistence unit | ordersEntityManagerFactory |
| PlatformTransactionManager | Bắt đầu, commit và rollback transaction cho persistence unit đó | ordersTransactionManager |

**DataSource** là lớp kết nối tới database. Nó chứa thông tin cần thiết để lấy JDBC connection, thường được cấu hình bằng URL, username, password và connection pool.

**Persistence unit** là khái niệm của JPA. Nó xác định tập entity và cấu hình persistence được quản lý như một đơn vị. Một persistence unit thường tương ứng với một database/schema và một nhóm entity có quan hệ nghiệp vụ với nhau. Trong Spring, có thể cấu hình persistence unit bằng Java configuration; không bắt buộc phải có file persistence.xml.

**EntityManagerFactory (EMF)** là đối tượng tạo EntityManager. Mỗi EMF gắn với một persistence unit cụ thể. EntityManager thực hiện các thao tác persist, find, merge, remove, query và quản lý persistence context.

**PlatformTransactionManager** là abstraction transaction của Spring. Với JPA, implementation thông dụng là JpaTransactionManager. Nó kết nối transaction của Spring với EntityManagerFactory tương ứng.

Mối liên kết cơ bản:

```text
DataSource
    |
    v
LocalContainerEntityManagerFactoryBean
    |  persistence unit: orders
    v
EntityManagerFactory
    |
    v
JpaTransactionManager
    |
    v
@Transactional service
    |
    v
Spring Data JPA repositories
```

Sơ đồ trên mô tả quan hệ cấu hình, không phải thứ tự mọi lời gọi runtime. Khi một service bắt đầu transaction, transaction manager sử dụng EMF của nó để lấy hoặc tạo EntityManager và gắn EntityManager đó với transaction hiện tại. Repository và EntityManager được inject trong phạm vi persistence unit sẽ tham gia transaction tương ứng.

## 2. JpaTransactionManager liên kết với EntityManagerFactory thế nào?

JpaTransactionManager là implementation của PlatformTransactionManager dành cho một EntityManagerFactory. Khi tạo bean, ta truyền đúng EMF vào constructor:

```java
@Bean
PlatformTransactionManager ordersTransactionManager(
        EntityManagerFactory ordersEntityManagerFactory) {
    return new JpaTransactionManager(ordersEntityManagerFactory);
}
```

Điểm cốt lõi nằm ở tham số EntityManagerFactory. JpaTransactionManager không tự dò repository hoặc tự chọn database dựa trên tên method. Nó quản lý transaction cho EMF được truyền vào.

Trong transaction, Spring gắn EntityManager tương ứng với EMF vào luồng thực thi hiện tại. Các thành phần như repository Spring Data JPA hoặc EntityManager được inject qua @PersistenceContext có thể tham gia cùng persistence context và transaction. Khi commit, thay đổi được flush xuống database rồi transaction được commit; khi rollback, transaction manager yêu cầu database rollback theo quy tắc transaction.

JpaTransactionManager được thiết kế cho **một EntityManagerFactory**. Nếu có hai persistence unit, thông thường cần hai EMF và hai JpaTransactionManager riêng. Không tạo một JpaTransactionManager rồi kỳ vọng nó điều khiển mọi EMF trong ứng dụng.

Nếu dùng JDBC trực tiếp bên cạnh JPA, JpaTransactionManager có thể phối hợp truy cập JDBC trên cùng DataSource trong transaction khi JDBC code sử dụng cơ chế Spring như JdbcTemplate hoặc DataSourceUtils và dùng đúng DataSource mà EMF đang quản lý. Tự lấy connection trực tiếp từ một pool khác có thể khiến thao tác JDBC nằm ngoài transaction JPA.

## 3. Trường hợp thông thường: một datasource, một persistence unit

Với một ứng dụng Spring Boot dùng một database, cấu hình thường chỉ cần datasource và thuộc tính JPA:

```yaml
spring:
  datasource:
    url: jdbc:postgresql://localhost:5432/shop
    username: shop_app
    password: change-me
    driver-class-name: org.postgresql.Driver

  jpa:
    hibernate:
      ddl-auto: validate
    open-in-view: false
    properties:
      hibernate:
        format_sql: true
```

Khi có starter phù hợp và driver trong classpath, Spring Boot tự cấu hình DataSource, EntityManagerFactory, persistence unit mặc định, JpaTransactionManager và repository infrastructure. Với ứng dụng một persistence unit, thông thường không cần tự khai báo LocalContainerEntityManagerFactoryBean hoặc JpaTransactionManager.

Service có thể dùng @Transactional:

```java
@Service
public class OrderService {

    private final PurchaseOrderRepository orderRepository;

    public OrderService(PurchaseOrderRepository orderRepository) {
        this.orderRepository = orderRepository;
    }

    @Transactional
    public Long createOrder(PurchaseOrder order) {
        PurchaseOrder saved = orderRepository.save(order);
        return saved.getId();
    }

    @Transactional(readOnly = true)
    public Optional<PurchaseOrder> findOrder(Long id) {
        return orderRepository.findById(id);
    }
}
```

Do ứng dụng chỉ có một transaction manager phù hợp, @Transactional không cần chỉ rõ tên manager. Spring dùng transaction manager mặc định được cấu hình trong application context.

Trong ví dụ, ddl-auto=validate yêu cầu Hibernate kiểm tra schema hiện có có tương thích với mapping hay không. Với môi trường triển khai, nên quản lý thay đổi schema bằng migration có phiên bản như Flyway hoặc Liquibase; không dùng ddl-auto=update như cơ chế migration production.

## 4. Cấu hình thủ công một persistence unit

Khi cần kiểm soát rõ entity package, tên persistence unit, JPA provider hoặc thuộc tính Hibernate, có thể khai báo LocalContainerEntityManagerFactoryBean và JpaTransactionManager.

```java
@Configuration
@EnableTransactionManagement
@EnableJpaRepositories(
    basePackages = "com.example.orders.persistence.repository",
    entityManagerFactoryRef = "ordersEntityManagerFactory",
    transactionManagerRef = "ordersTransactionManager"
)
public class OrdersJpaConfiguration {

    @Bean(name = "ordersEntityManagerFactory")
    LocalContainerEntityManagerFactoryBean ordersEntityManagerFactory(
            @Qualifier("ordersDataSource") DataSource dataSource) {

        LocalContainerEntityManagerFactoryBean factory =
                new LocalContainerEntityManagerFactoryBean();

        factory.setDataSource(dataSource);
        factory.setPackagesToScan(
                "com.example.orders.persistence.entity"
        );
        factory.setPersistenceUnitName("orders");
        factory.setJpaVendorAdapter(new HibernateJpaVendorAdapter());
        factory.setJpaPropertyMap(Map.of(
                "hibernate.hbm2ddl.auto", "validate",
                "hibernate.format_sql", "true"
        ));

        return factory;
    }

    @Bean(name = "ordersTransactionManager")
    PlatformTransactionManager ordersTransactionManager(
            @Qualifier("ordersEntityManagerFactory")
            EntityManagerFactory entityManagerFactory) {

        return new JpaTransactionManager(entityManagerFactory);
    }
}
```

Ví dụ giả định bean DataSource có tên ordersDataSource đã được cấu hình ở nơi khác. Các import quan trọng thuộc những package sau:

- org.springframework.context.annotation cho @Configuration, @Bean.
- org.springframework.data.jpa.repository.config cho @EnableJpaRepositories.
- org.springframework.orm.jpa cho LocalContainerEntityManagerFactoryBean và JpaTransactionManager.
- org.springframework.orm.jpa.vendor cho HibernateJpaVendorAdapter.
- jakarta.persistence cho EntityManagerFactory và các annotation JPA.
- javax.sql cho DataSource.
- org.springframework.beans.factory.annotation cho @Qualifier.

Có bốn cấu hình cần hiểu:

1. **setDataSource** chỉ ra database connection source mà persistence unit sử dụng.
2. **setPackagesToScan** xác định các package chứa entity được đưa vào persistence unit này. Không quét tràn sang entity của persistence unit khác.
3. **setPersistenceUnitName("orders")** đặt tên persistence unit để các điểm inject JPA có thể tham chiếu.
4. **new JpaTransactionManager(entityManagerFactory)** liên kết transaction manager với chính EMF vừa khai báo.

@EnableJpaRepositories cũng có hai tham chiếu quan trọng. entityManagerFactoryRef là tên bean Spring cung cấp EntityManagerFactory; transactionManagerRef là tên bean Spring quản lý transaction cho repository đó. Repository trong package đã chỉ định sẽ dùng đúng cặp này.

Nếu cấu hình bằng Spring Boot, hãy cân nhắc để Boot tự tạo bean khi không có nhu cầu đặc biệt. Khi tự khai báo EMF hoặc transaction manager, một số auto-configuration tương ứng sẽ lùi lại theo điều kiện bean. Tránh vừa cấu hình thủ công vừa vô tình giữ các bean mặc định không mong muốn.

## 5. Persistence unit name, bean name và transaction manager name

Ba loại tên này thường được đặt giống nhau cho dễ đọc, nhưng chúng có ý nghĩa khác nhau:

| Tên | Thuộc về | Được tham chiếu bởi |
|---|---|---|
| orders | JPA persistence unit | @PersistenceContext(unitName = "orders"), @PersistenceUnit(unitName = "orders") |
| ordersEntityManagerFactory | Spring bean | @Qualifier và entityManagerFactoryRef |
| ordersTransactionManager | Spring bean | transactionManagerRef và @Transactional(transactionManager = "ordersTransactionManager") |

**persistence unit name không phải bean name của EntityManagerFactory.** Trong ví dụ, hai tên được đặt gần nhau để người đọc dễ liên hệ, nhưng chúng là hai định danh khác nhau. Đổi bean name không tự đổi persistence unit name và ngược lại.

Tương tự, transactionManagerRef nhận tên bean Spring của transaction manager. Nó không nhận tên persistence unit.

Có thể hình dung các tham chiếu:

```text
@PersistenceContext(unitName = "orders")
                |
                v
       persistence unit "orders"
                |
                v
ordersEntityManagerFactory (Spring bean)
                |
                v
ordersTransactionManager (Spring bean)
                |
                v
@Transactional(transactionManager = "ordersTransactionManager")
```

Trong code, có thể inject EntityManager của persistence unit cụ thể:

```java
@Repository
public class OrderLookup {

    @PersistenceContext(unitName = "orders")
    private EntityManager entityManager;

    public PurchaseOrder find(Long id) {
        return entityManager.find(PurchaseOrder.class, id);
    }
}
```

@PersistenceContext yêu cầu Spring cung cấp EntityManager proxy phù hợp với persistence unit được chỉ định. Proxy này tham gia EntityManager gắn với transaction hiện hành khi có transaction phù hợp. Không tự tạo EntityManager bằng createEntityManager() cho mỗi thao tác nghiệp vụ thông thường, vì việc đó tách vòng đời persistence context khỏi cơ chế quản lý transaction của Spring.

Nếu inject EntityManagerFactory trực tiếp, có thể dùng @PersistenceUnit(unitName = "orders") hoặc inject bean bằng @Qualifier("ordersEntityManagerFactory"). Cách thứ hai tham chiếu bean name; cách thứ nhất tham chiếu persistence unit name.

## 6. Trường hợp nhiều datasource hoặc nhiều persistence unit

Giả sử ứng dụng có hai vùng dữ liệu độc lập:

- Orders lưu khách hàng, đơn hàng và dòng hàng.
- Billing lưu hóa đơn và thông tin thanh toán.

Mỗi vùng có datasource, entity package, persistence unit, EntityManagerFactory, transaction manager và repository package riêng.

```text
ordersDataSource
    |
ordersEntityManagerFactory (unit: orders)
    |
ordersTransactionManager
    |
com.example.orders.persistence.repository

billingDataSource
    |
billingEntityManagerFactory (unit: billing)
    |
billingTransactionManager
    |
com.example.billing.persistence.repository
```

Cấu hình repository cho Orders:

```java
@Configuration
@EnableTransactionManagement
@EnableJpaRepositories(
    basePackages = "com.example.orders.persistence.repository",
    entityManagerFactoryRef = "ordersEntityManagerFactory",
    transactionManagerRef = "ordersTransactionManager"
)
public class OrdersJpaConfiguration {

    @Bean(name = "ordersEntityManagerFactory")
    LocalContainerEntityManagerFactoryBean ordersEntityManagerFactory(
            @Qualifier("ordersDataSource") DataSource dataSource) {

        LocalContainerEntityManagerFactoryBean factory =
                new LocalContainerEntityManagerFactoryBean();
        factory.setDataSource(dataSource);
        factory.setPackagesToScan(
                "com.example.orders.persistence.entity"
        );
        factory.setPersistenceUnitName("orders");
        factory.setJpaVendorAdapter(new HibernateJpaVendorAdapter());
        factory.setJpaPropertyMap(Map.of(
                "hibernate.hbm2ddl.auto", "validate"
        ));
        return factory;
    }

    @Bean(name = "ordersTransactionManager")
    PlatformTransactionManager ordersTransactionManager(
            @Qualifier("ordersEntityManagerFactory")
            EntityManagerFactory entityManagerFactory) {
        return new JpaTransactionManager(entityManagerFactory);
    }
}
```

Billing có cấu hình tương tự nhưng tham chiếu các bean và package riêng:

```java
@Configuration
@EnableJpaRepositories(
    basePackages = "com.example.billing.persistence.repository",
    entityManagerFactoryRef = "billingEntityManagerFactory",
    transactionManagerRef = "billingTransactionManager"
)
public class BillingJpaConfiguration {

    @Bean(name = "billingEntityManagerFactory")
    LocalContainerEntityManagerFactoryBean billingEntityManagerFactory(
            @Qualifier("billingDataSource") DataSource dataSource) {

        LocalContainerEntityManagerFactoryBean factory =
                new LocalContainerEntityManagerFactoryBean();
        factory.setDataSource(dataSource);
        factory.setPackagesToScan(
                "com.example.billing.persistence.entity"
        );
        factory.setPersistenceUnitName("billing");
        factory.setJpaVendorAdapter(new HibernateJpaVendorAdapter());
        factory.setJpaPropertyMap(Map.of(
                "hibernate.hbm2ddl.auto", "validate"
        ));
        return factory;
    }

    @Bean(name = "billingTransactionManager")
    PlatformTransactionManager billingTransactionManager(
            @Qualifier("billingEntityManagerFactory")
            EntityManagerFactory entityManagerFactory) {
        return new JpaTransactionManager(entityManagerFactory);
    }
}
```

Các bean ordersDataSource và billingDataSource phải được khai báo riêng, thường bằng @ConfigurationProperties với hai prefix khác nhau. Có thể dùng DataSourceProperties để khởi tạo từng pool. Khi inject một DataSource vào factory, luôn dùng @Qualifier để tránh Spring chọn nhầm datasource.

Ví dụ property:

```yaml
app:
  datasource:
    orders:
      url: jdbc:postgresql://localhost:5432/orders
      username: orders_app
      password: change-me
      driver-class-name: org.postgresql.Driver
    billing:
      url: jdbc:postgresql://localhost:5432/billing
      username: billing_app
      password: change-me
      driver-class-name: org.postgresql.Driver
```

Tên property trên chỉ là prefix tùy chỉnh của ứng dụng; cần có bean cấu hình bind chúng vào DataSource thực tế. Không thể chỉ thêm hai nhóm property rồi mong Spring Boot tự suy ra hai persistence unit. Với nhiều datasource, ứng dụng phải khai báo cách tạo DataSource, EMF, transaction manager và repository tương ứng.

Khi có nhiều @EnableJpaRepositories, mỗi cấu hình cần có package repository riêng. Nếu hai cấu hình cùng quét một package, repository có thể bị đăng ký trùng hoặc gắn sai EMF. Entity package cũng nên được tách rõ, tránh một entity vô tình thuộc cả hai persistence unit nếu không có chủ đích.

## 7. Chọn transaction manager cho service

Với nhiều transaction manager, một @Transactional không ghi rõ manager có thể không còn đủ thông tin để chọn đúng transaction. Hãy chỉ định tên bean:

```java
@Service
public class OrderService {

    @Transactional(transactionManager = "ordersTransactionManager")
    public void confirmOrder(Long orderId) {
        // Đọc và cập nhật entity thuộc persistence unit Orders.
    }
}
```

Với nghiệp vụ Billing:

```java
@Service
public class BillingService {

    @Transactional(transactionManager = "billingTransactionManager")
    public void issueInvoice(Long orderId) {
        // Thao tác repository thuộc persistence unit Billing.
    }
}
```

Thuộc tính transactionManager của @Transactional nhận qualifier/tên bean transaction manager; thuộc tính value là alias của nó. Nếu ứng dụng chỉ có một transaction manager, có thể bỏ qua thuộc tính này. Khi có nhiều manager, có thể đánh dấu một manager là @Primary để làm mặc định cho các injection cần một lựa chọn duy nhất, nhưng với service nghiệp vụ thuộc một persistence unit cụ thể, ghi rõ manager giúp quan hệ dễ kiểm tra hơn.

Không nhầm hai việc sau:

- @EnableJpaRepositories(transactionManagerRef = "...") gắn repository package với transaction manager mặc định của repository đó.
- @Transactional(transactionManager = "...") chọn transaction manager cho phương thức service đang chạy.

Cấu hình repository không tự thay thế việc chọn manager cho service. Hãy giữ hai tham chiếu nhất quán.

## 8. Một transaction có thể bao phủ nhiều persistence unit không?

Hai JpaTransactionManager riêng biệt không tự tạo thành một transaction nguyên tử chung. Nếu service gọi repository Orders rồi repository Billing, mỗi repository có thể tham gia transaction do manager riêng điều khiển. Việc một thao tác thành công còn thao tác kia thất bại có thể để lại dữ liệu ở hai trạng thái khác nhau.

Ví dụ: xác nhận đơn hàng trong Orders và phát hành hóa đơn trong Billing. Nếu hai thao tác phải commit hoặc rollback đồng thời trên nhiều resource, cần thiết kế transaction phân tán phù hợp, thường là JTA với transaction manager và resource được cấu hình hỗ trợ. Không thể đạt atomicity chỉ bằng cách đặt hai annotation @Transactional khác tên hoặc gọi hai JpaTransactionManager nối tiếp nhau.

Nếu nghiệp vụ cho phép nhất quán cuối cùng, có thể thiết kế quy trình tách bước, outbox, retry và xử lý bù. Lựa chọn phụ thuộc yêu cầu nghiệp vụ, khả năng của database và hạ tầng transaction. Không thêm JTA chỉ vì ứng dụng có hai database nếu các nghiệp vụ không cần transaction phân tán.

Nếu hai EMF cùng sử dụng một DataSource, mỗi EMF vẫn có persistence context và transaction manager riêng. Dùng chung một database connection source không làm cho hai persistence unit tự động trở thành một persistence context hay một transaction JPA duy nhất.

## 9. Luồng thực thi khi gọi @Transactional

Với một service method được gọi từ bean khác qua Spring proxy, luồng khái quát như sau:

1. Proxy đọc metadata của @Transactional, bao gồm propagation, isolation, readOnly và transaction manager được chọn.
2. Transaction manager bắt đầu transaction mới hoặc tham gia transaction đang tồn tại theo propagation.
3. JpaTransactionManager lấy hoặc tạo EntityManager cho EMF mà nó quản lý, sau đó gắn nó với transaction hiện tại.
4. Service gọi repository hoặc EntityManager. Các thao tác persistence tham gia cùng persistence context phù hợp.
5. Khi method kết thúc bình thường, transaction manager flush thay đổi cần thiết và commit.
6. Nếu có exception thuộc chính sách rollback, transaction manager rollback. Mặc định Spring rollback với RuntimeException và Error; checked exception không tự động rollback nếu không cấu hình rollbackFor phù hợp.

Ví dụ khai báo rollback cho checked exception:

```java
@Transactional(
    transactionManager = "ordersTransactionManager",
    rollbackFor = OrderRejectedException.class
)
public void confirmOrder(Long orderId) throws OrderRejectedException {
    // Kiểm tra điều kiện và thay đổi trạng thái đơn.
}
```

@Transactional hoạt động thông qua proxy. Gọi một method transactional khác trong cùng object bằng this.method() thường không đi qua proxy, vì vậy không tạo transaction boundary mới như nhiều người mong đợi. Đặt ranh giới transaction ở service method được gọi từ bean khác hoặc dùng cơ chế phù hợp của Spring.

Propagation như REQUIRED, REQUIRES_NEW và MANDATORY quyết định cách method tham gia transaction đang có. Isolation được chuyển xuống transaction/database khi được hỗ trợ. readOnly là gợi ý cho transaction manager/provider và có thể giúp tối ưu đọc; không nên coi nó là cơ chế phân quyền cấm ghi tuyệt đối.

## 10. Kiểm thử cấu hình

Khi kiểm tra cấu hình một persistence unit, cần xác nhận:

- Application context khởi động được và tạo đúng DataSource, EntityManagerFactory, transaction manager.
- Entity được đưa vào đúng persistence unit.
- Repository package dùng đúng entityManagerFactoryRef và transactionManagerRef.
- Service method chọn đúng transaction manager.
- EntityManager được inject bằng đúng unitName nếu có nhiều persistence unit.
- Rollback thực sự hoàn tác dữ liệu khi nghiệp vụ phát sinh exception.
- JDBC access, nếu có, sử dụng cùng DataSource và cơ chế Spring transaction-aware.

Với ứng dụng một persistence unit, @DataJpaTest thường phù hợp để kiểm tra mapping và repository. Với nhiều persistence unit, cần import các cấu hình liên quan và xác nhận từng repository truy cập đúng database. Khi dùng PostgreSQL hoặc database khác trong production, nên có integration test với cùng loại database, ví dụ qua Testcontainers; H2 có thể khác về dialect, constraint, locking và native SQL.

Có thể kiểm tra cấu hình runtime bằng cách xem bean names và loại bean trong ApplicationContext. Khi cần chẩn đoán sâu, bật log transaction của Spring và SQL của Hibernate ở môi trường phát triển. Không bật log SQL/parameter nhạy cảm tràn lan trong production.

## 11. Lỗi thường gặp và cách xử lý

| Biểu hiện | Nguyên nhân có thể | Cách kiểm tra |
|---|---|---|
| No qualifying bean of type PlatformTransactionManager | Chưa khai báo manager hoặc auto-configuration đã lùi lại | Kiểm tra bean transaction manager và điều kiện cấu hình JPA |
| NoUniqueBeanDefinitionException | Có nhiều transaction manager hoặc EntityManagerFactory nhưng injection không chỉ rõ | Dùng @Qualifier, chỉ định transactionManager hoặc cấu hình @Primary có chủ đích |
| Repository truy cập nhầm database | entityManagerFactoryRef hoặc DataSource qualifier sai | Kiểm tra package scan và chuỗi bean repository → EMF → DataSource |
| Transaction không bao phủ thao tác JPA | Service chọn manager của persistence unit khác | Đối chiếu transactionManagerRef, @Transactional và EMF |
| No EntityManager with actual transaction available | Gọi thao tác yêu cầu transaction nhưng không có transaction phù hợp | Kiểm tra transaction annotation, proxy call và manager được chọn |
| Entity không được tìm thấy hoặc mapping thiếu | Entity package không nằm trong packagesToScan của EMF | Kiểm tra package scan và persistence unit |
| @PersistenceContext inject sai unit | unitName không khớp persistence unit đã đặt | Đối chiếu setPersistenceUnitName với unitName |
| Dữ liệu Orders đã commit nhưng Billing lỗi | Hai local transaction manager độc lập | Thiết kế JTA hoặc quy trình nhất quán cuối cùng theo yêu cầu |

Khi gặp lỗi, hãy lần theo chuỗi tham chiếu từ repository đến DataSource. Phần lớn lỗi cấu hình nhiều persistence unit bắt nguồn từ một trong ba điểm: package scan sai, bean reference sai hoặc service chọn nhầm transaction manager.

## 12. Checklist thiết kế trước khi thêm persistence unit

Trước khi tạo persistence unit thứ hai, trả lời được các câu hỏi:

1. Có thật sự cần tách entity và persistence context không, hay chỉ cần thêm repository trong persistence unit hiện tại?
2. Entity package và repository package của từng unit là gì?
3. Mỗi unit sử dụng DataSource nào và bean name nào?
4. Persistence unit name, EntityManagerFactory bean name và transaction manager bean name là gì?
5. Repository được gắn đúng entityManagerFactoryRef và transactionManagerRef chưa?
6. Service nào phải chỉ định transactionManager?
7. Nghiệp vụ có cần một transaction nguyên tử xuyên nhiều database không?
8. Integration test đã xác minh đúng database, rollback và mapping chưa?

Tạo thêm persistence unit làm tăng số cấu hình và ranh giới transaction cần quản lý. Chỉ nên tách khi có ranh giới dữ liệu, schema, database hoặc yêu cầu quản trị rõ ràng.

**Quy tắc ghi nhớ:** persistence unit xác định nhóm entity và cấu hình JPA; EntityManagerFactory đại diện cho persistence unit trong runtime; JpaTransactionManager quản lý transaction cho đúng EntityManagerFactory; repository được nối vào cặp EMF/transaction manager bằng @EnableJpaRepositories; service chọn transaction manager bằng @Transactional khi ứng dụng có nhiều manager. Khi năm mối liên hệ này nhất quán, EntityManager và repository sẽ tham gia đúng persistence context và transaction.
