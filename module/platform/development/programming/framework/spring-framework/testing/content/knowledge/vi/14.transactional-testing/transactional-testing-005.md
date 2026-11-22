# Chọn transaction manager khi có nhiều nguồn dữ liệu

Một ứng dụng Spring có thể làm việc với nhiều database hoặc nhiều nguồn dữ liệu: database nghiệp vụ, database audit, kho báo cáo, hệ thống legacy hoặc một datasource chỉ đọc. Khi mỗi nguồn dữ liệu có transaction boundary riêng, ứng dụng thường có nhiều bean `PlatformTransactionManager`. Trong trường hợp đó, một annotation `@Transactional` không ghi rõ manager có thể chọn nhầm manager hoặc gây lỗi vì Spring không xác định được manager phù hợp.

Trong kiểm thử tích hợp, việc chọn đúng transaction manager còn quyết định dữ liệu nào được rollback sau test. Transaction test-managed chỉ điều khiển tài nguyên thuộc manager được chọn. Nếu test ghi sang datasource thứ hai qua một transaction manager khác, dữ liệu đó có thể vẫn commit dù transaction của test đã rollback. Vì vậy, test cần chỉ rõ manager khi có nhiều nguồn dữ liệu và cần hiểu ranh giới transaction của từng nguồn.

## 1. `PlatformTransactionManager` và nhiều datasource

Spring quản lý transaction thông qua abstraction `PlatformTransactionManager`. Mỗi transaction manager điều phối transaction cho một loại tài nguyên hoặc một nhóm tài nguyên cụ thể.

Các implementation thường gặp:

| Transaction manager | Tài nguyên được quản lý | Trường hợp sử dụng |
|---|---|---|
| `DataSourceTransactionManager` | Một JDBC `DataSource` | Ứng dụng dùng JDBC hoặc Spring JDBC |
| `JdbcTransactionManager` | Một JDBC `DataSource` | Biến thể JDBC transaction manager có hỗ trợ dịch exception nhất quán hơn trong Spring Framework hiện đại |
| `JpaTransactionManager` | Một JPA `EntityManagerFactory` | Ứng dụng dùng Spring Data JPA/Hibernate |
| `JtaTransactionManager` | Transaction được điều phối bởi JTA | Cần transaction phân tán giữa các XA resource được cấu hình phù hợp |

Một ứng dụng có hai datasource độc lập thường khai báo hai transaction manager tương ứng:

```text
OrdersRepository  ---> ordersDataSource  ---> ordersTransactionManager

AuditRepository   ---> auditDataSource   ---> auditTransactionManager
```

Mỗi manager biết cách bắt đầu, commit và rollback transaction cho resource mà nó quản lý. Việc có nhiều manager không tự động tạo một transaction chung bao trùm tất cả datasource.

### 1.1. Vì sao phải chọn manager rõ ràng?

Khi chỉ có một bean `PlatformTransactionManager`, Spring thường có thể dùng manager duy nhất làm mặc định. Khi có nhiều manager, một điểm cần quyết định là manager nào sẽ xử lý một phương thức `@Transactional` không chỉ định tên.

Ví dụ, service có hai phương thức:

```java
@Service
class OrderService {
    @Transactional
    public void placeOrder(CreateOrderCommand command) {
        // Ghi đơn hàng vào database nghiệp vụ.
    }
}

@Service
class AuditService {
    @Transactional
    public void recordOrderCreated(String orderId) {
        // Ghi audit vào database riêng.
    }
}
```

Nếu context có hai transaction manager và không có quy ước mặc định rõ ràng, annotation không có qualifier có thể không được resolve như mong muốn. Kể cả khi Spring chọn được một manager mặc định, `AuditService` vẫn cần manager gắn với audit datasource. Cách rõ ràng nhất là chỉ định manager trên các phương thức có transaction boundary riêng.

## 2. Khai báo nhiều transaction manager

Với JDBC, mỗi transaction manager cần nhận đúng datasource của nó. Dùng bean name và `@Qualifier` để tránh inject nhầm khi có nhiều bean cùng kiểu.

```java
@Configuration
class MultiDataSourceConfiguration {
    @Bean
    @ConfigurationProperties("app.datasource.orders")
    DataSourceProperties ordersDataSourceProperties() {
        return new DataSourceProperties();
    }

    @Bean
    @ConfigurationProperties("app.datasource.orders.hikari")
    HikariDataSource ordersDataSource(
            @Qualifier("ordersDataSourceProperties")
            DataSourceProperties properties) {
        return properties.initializeDataSourceBuilder()
                .type(HikariDataSource.class)
                .build();
    }

    @Bean
    @ConfigurationProperties("app.datasource.audit")
    DataSourceProperties auditDataSourceProperties() {
        return new DataSourceProperties();
    }

    @Bean
    @ConfigurationProperties("app.datasource.audit.hikari")
    HikariDataSource auditDataSource(
            @Qualifier("auditDataSourceProperties")
            DataSourceProperties properties) {
        return properties.initializeDataSourceBuilder()
                .type(HikariDataSource.class)
                .build();
    }

    @Bean(name = {"transactionManager", "ordersTransactionManager"})
    PlatformTransactionManager ordersTransactionManager(
            @Qualifier("ordersDataSource") DataSource dataSource) {
        return new DataSourceTransactionManager(dataSource);
    }

    @Bean("auditTransactionManager")
    PlatformTransactionManager auditTransactionManager(
            @Qualifier("auditDataSource") DataSource dataSource) {
        return new DataSourceTransactionManager(dataSource);
    }
}
```

Ví dụ đặt tên manager của orders bằng cả `transactionManager` và `ordersTransactionManager`. Hai tên là alias của cùng một bean, vì vậy ứng dụng có một manager mặc định với tên truyền thống và vẫn có tên cụ thể để dùng trong annotation. Manager audit có tên riêng.

Các property có thể được cấu hình trong file ứng dụng:

```yaml
app:
  datasource:
    orders:
      url: jdbc:postgresql://localhost:5432/orders
      username: app
      password: secret
      driver-class-name: org.postgresql.Driver
    audit:
      url: jdbc:postgresql://localhost:5432/audit
      username: app
      password: secret
      driver-class-name: org.postgresql.Driver
```

Đây là ví dụ cấu hình minh họa. Trong dự án thật, datasource có thể được tạo từ `DataSourceBuilder`, `DataSourceProperties`, cấu hình Hikari riêng hoặc cơ chế của Spring Boot. Điều quan trọng là mỗi transaction manager phải nhận đúng datasource và các bean cần inject datasource phải dùng qualifier rõ ràng.

### 2.1. Đặt tên manager nhất quán

Tên bean là một phần của hợp đồng cấu hình. Chọn tên thể hiện resource hoặc bounded context:

- `ordersTransactionManager` cho transaction trên database đơn hàng.
- `auditTransactionManager` cho transaction trên database audit.
- `reportingTransactionManager` cho database báo cáo.

Tránh đặt tên chung như `manager1` hoặc `secondaryTx`. Tên rõ ràng giúp người đọc biết `@Transactional` đang điều khiển nguồn dữ liệu nào và giúp test chỉ định đúng manager.

Nếu muốn một manager là mặc định cho những nơi không chỉ định qualifier, có thể đặt tên bean đó là `transactionManager`, đánh dấu nó `@Primary` khi cần giải quyết injection theo type, hoặc cấu hình manager mặc định qua `TransactionManagementConfigurer`. Dù có manager mặc định, các service thuộc datasource khác vẫn nên chỉ rõ manager.

## 3. Chọn transaction manager bằng `@Transactional`

Spring `@Transactional` có thuộc tính `transactionManager` để chọn bean quản lý transaction. Thuộc tính `value` là alias của `transactionManager`, nên hai cách viết sau có ý nghĩa tương đương:

```java
@Transactional(transactionManager = "ordersTransactionManager")
public void placeOrder() {
    // Giao dịch trên orders database.
}
```

```java
@Transactional("ordersTransactionManager")
public void placeOrder() {
    // Giao dịch trên orders database.
}
```

Nếu bean được khai báo bằng `@Bean("ordersTransactionManager")`, tên đó có thể được dùng làm qualifier. Cách này áp dụng cho service transaction và cũng là cách chọn manager cho test-managed transaction.

### 3.1. Chỉ định manager ở cấp method

Khi một service có các thao tác trên nhiều datasource, đặt manager ngay trên method thể hiện transaction boundary:

```java
@Service
class OrderService {
    private final OrderRepository orders;

    OrderService(OrderRepository orders) {
        this.orders = orders;
    }

    @Transactional(transactionManager = "ordersTransactionManager")
    public Order create(CreateOrderCommand command) {
        return orders.save(new Order(command.customerId()));
    }
}

@Service
class AuditService {
    private final AuditRepository audits;

    AuditService(AuditRepository audits) {
        this.audits = audits;
    }

    @Transactional(transactionManager = "auditTransactionManager")
    public void record(String orderId) {
        audits.save(new AuditEntry(orderId, "ORDER_CREATED"));
    }
}
```

Việc chỉ định rõ manager làm cho ý định của từng service dễ đọc và tránh phụ thuộc vào manager mặc định của context.

### 3.2. Manager ở cấp class và override ở method

Có thể đặt manager chung trên class:

```java
@Service
@Transactional(transactionManager = "ordersTransactionManager")
class OrderService {
    public void create() {
        // Dùng ordersTransactionManager.
    }

    public void cancel() {
        // Cũng dùng ordersTransactionManager.
    }
}
```

Nếu một method cần manager khác, có thể khai báo annotation ở method đó:

```java
@Transactional(transactionManager = "auditTransactionManager")
public void recordAudit() {
    // Dùng auditTransactionManager.
}
```

Method-level transaction metadata ghi đè cấu hình ở class-level cho method tương ứng. Hãy hạn chế trộn nhiều datasource trong cùng một service nếu điều đó làm transaction boundary khó hiểu; tách service theo resource thường giúp ownership rõ ràng hơn.

## 4. Chọn manager mặc định cho annotation-driven transaction

Nếu một ứng dụng có nhiều manager nhưng nhiều service vẫn dùng `@Transactional` không qualifier, cần cấu hình manager mặc định rõ ràng.

### 4.1. Bean tên `transactionManager`

Một quy ước thông dụng là đặt tên manager mặc định là `transactionManager`. Các annotation không chỉ định manager có thể dùng bean theo tên quy ước này trong cơ chế transaction của Spring.

Trong ví dụ multi-datasource ở trên, `ordersTransactionManager` được khai báo với hai tên:

```java
@Bean(name = {"transactionManager", "ordersTransactionManager"})
PlatformTransactionManager ordersTransactionManager(
        @Qualifier("ordersDataSource") DataSource dataSource) {
    return new DataSourceTransactionManager(dataSource);
}
```

Những nơi cần manager mặc định có thể tiếp tục dùng `@Transactional`, còn service audit dùng tên cụ thể.

### 4.2. Dùng `@Primary`

`@Primary` đánh dấu bean được ưu tiên khi Spring phải resolve một dependency theo type và có nhiều candidate. Ví dụ:

```java
@Bean
@Primary
PlatformTransactionManager ordersTransactionManager(
        @Qualifier("ordersDataSource") DataSource dataSource) {
    return new DataSourceTransactionManager(dataSource);
}

@Bean
PlatformTransactionManager auditTransactionManager(
        @Qualifier("auditDataSource") DataSource dataSource) {
    return new DataSourceTransactionManager(dataSource);
}
```

`@Primary` hữu ích cho dependency injection theo type và có thể giúp việc resolve manager không qualifier chọn được một candidate ưu tiên. Tuy nhiên, tên bean mặc định và cơ chế cấu hình transaction của ứng dụng cần được hiểu rõ. Khi có nhiều manager, dùng qualifier trên những transaction boundary quan trọng vẫn là cách dễ đọc và ít mơ hồ nhất.

### 4.3. Dùng `TransactionManagementConfigurer`

Nếu muốn chỉ định manager mặc định cho annotation-driven transaction một cách tường minh, có thể triển khai `TransactionManagementConfigurer`:

```java
@Configuration
@EnableTransactionManagement
class DefaultTransactionConfiguration
        implements TransactionManagementConfigurer {

    private final PlatformTransactionManager defaultManager;

    DefaultTransactionConfiguration(
            @Qualifier("ordersTransactionManager")
            PlatformTransactionManager defaultManager) {
        this.defaultManager = defaultManager;
    }

    @Override
    public PlatformTransactionManager annotationDrivenTransactionManager() {
        return defaultManager;
    }
}
```

Ở đây, `ordersTransactionManager` được chọn làm manager mặc định cho annotation-driven transaction. Các method cần audit manager vẫn chỉ định qualifier riêng trong `@Transactional`.

`TransactionManagementConfigurer` thuộc cơ chế cấu hình transaction của Spring. Khi dùng Spring Boot, auto-configuration có thể đã bật transaction management; hãy đặt cấu hình này ở đúng vị trí và tránh đăng ký nhiều cấu hình mặc định cạnh tranh nhau.

## 5. Nhiều JPA datasource cần nhiều `EntityManagerFactory`

Nếu ứng dụng dùng JPA với hai datasource độc lập, thường cần một `EntityManagerFactory` và một `JpaTransactionManager` cho mỗi datasource. Chỉ tạo hai `DataSource` và hai `JpaTransactionManager` là chưa đủ nếu repository package chưa được gắn đúng factory và manager.

Ví dụ cấu hình hai nhóm repository:

```java
@Configuration
@EnableJpaRepositories(
        basePackages = "com.example.orders.repository",
        entityManagerFactoryRef = "ordersEntityManagerFactory",
        transactionManagerRef = "ordersTransactionManager")
class OrdersJpaConfiguration {
    @Bean
    LocalContainerEntityManagerFactoryBean ordersEntityManagerFactory(
            EntityManagerFactoryBuilder builder,
            @Qualifier("ordersDataSource") DataSource dataSource) {
        return builder
                .dataSource(dataSource)
                .packages(Order.class)
                .persistenceUnit("orders")
                .build();
    }

    @Bean
    PlatformTransactionManager ordersTransactionManager(
            @Qualifier("ordersEntityManagerFactory")
            EntityManagerFactory entityManagerFactory) {
        return new JpaTransactionManager(entityManagerFactory);
    }
}
```

Audit repository có cấu hình tương ứng:

```java
@Configuration
@EnableJpaRepositories(
        basePackages = "com.example.audit.repository",
        entityManagerFactoryRef = "auditEntityManagerFactory",
        transactionManagerRef = "auditTransactionManager")
class AuditJpaConfiguration {
    @Bean
    LocalContainerEntityManagerFactoryBean auditEntityManagerFactory(
            EntityManagerFactoryBuilder builder,
            @Qualifier("auditDataSource") DataSource dataSource) {
        return builder
                .dataSource(dataSource)
                .packages(AuditEntry.class)
                .persistenceUnit("audit")
                .build();
    }

    @Bean
    PlatformTransactionManager auditTransactionManager(
            @Qualifier("auditEntityManagerFactory")
            EntityManagerFactory entityManagerFactory) {
        return new JpaTransactionManager(entityManagerFactory);
    }
}
```

Các tên package, entity và cấu hình builder phụ thuộc ứng dụng. Mấu chốt là mỗi `@EnableJpaRepositories` trỏ đến đúng `entityManagerFactoryRef` và `transactionManagerRef`. Nếu repository package bị scan bởi hai cấu hình hoặc được gắn nhầm manager, test có thể truy cập sai database hoặc báo lỗi khi khởi tạo context.

### 5.1. `@Primary` cho JPA infrastructure

Nếu ứng dụng có nhiều `DataSource`, `EntityManagerFactory` hoặc `PlatformTransactionManager`, một số auto-configuration hoặc injection point cần biết bean mặc định. Có thể dùng `@Primary` cho nhóm chính, nhưng vẫn phải gắn qualifier tường minh ở các cấu hình phụ.

Không đánh dấu mọi bean là primary. Mỗi kiểu chỉ nên có một lựa chọn mặc định khi thật sự cần. Với repository thuộc datasource phụ, `entityManagerFactoryRef` và `transactionManagerRef` phải chỉ rõ bean phụ tương ứng.

## 6. Transaction manager trong test-managed transaction

Spring TestContext Framework có `TransactionalTestExecutionListener` để quản lý transaction cho test method hoặc test class được đánh dấu `@Transactional`. Test transaction thường bắt đầu trước khi test method chạy và rollback sau khi test hoàn tất theo mặc định.

Khi có nhiều manager, chọn manager cho test bằng thuộc tính `transactionManager` hoặc alias `value` của `@Transactional`:

```java
@SpringBootTest
@Transactional(transactionManager = "ordersTransactionManager")
class OrderRepositoryIntegrationTest {
    @Autowired
    private OrderRepository orders;

    @Test
    void createsOrderInsideOrdersTransaction() {
        orders.save(new Order("customer-42"));

        assertThat(orders.count()).isEqualTo(1);
    }
}
```

Test transaction được mở bằng `ordersTransactionManager`. Khi test kết thúc, Spring rollback transaction này theo mặc định, nên dữ liệu của test được hoàn tác nếu thao tác tham gia cùng transaction.

Với audit datasource:

```java
@SpringBootTest
@Transactional("auditTransactionManager")
class AuditRepositoryIntegrationTest {
    @Autowired
    private AuditRepository audits;

    @Test
    void storesAuditEntryInsideAuditTransaction() {
        audits.save(new AuditEntry("order-42", "CREATED"));

        assertThat(audits.count()).isEqualTo(1);
    }
}
```

Ở đây test transaction được quản lý bởi audit manager. Nếu test không chỉ định manager trong context có nhiều manager và Spring không thể chọn mặc định, test có thể thất bại khi bắt đầu transaction.

### 6.1. Annotation ở cấp class và method

Có thể đặt `@Transactional` ở cấp class để tất cả test method dùng cùng manager:

```java
@SpringBootTest
@Transactional(transactionManager = "ordersTransactionManager")
class OrderServiceIntegrationTest {
    @Test
    void createsOrder() {
    }

    @Test
    void cancelsOrder() {
    }
}
```

Method có thể override metadata ở class nếu cần một manager hoặc transaction attribute khác:

```java
@Test
@Transactional(transactionManager = "auditTransactionManager")
void recordsAuditEntry() {
    // Test-managed transaction dùng audit manager.
}
```

Hãy tránh đặt class-level manager chung nếu nhiều method trong class kiểm tra những datasource độc lập. Trong trường hợp đó, method-level annotation hoặc tách test class theo datasource giúp ranh giới rollback rõ ràng hơn.

## 7. Transaction test chỉ rollback resource của manager đã chọn

Đây là điểm quan trọng nhất khi kiểm thử nhiều datasource. Một test transaction dùng `ordersTransactionManager` chỉ quản lý transaction trên orders datasource. Nếu trong cùng test, code ghi vào audit datasource qua `auditTransactionManager`, transaction audit là một transaction khác.

Ví dụ:

```java
@Service
class OrderWorkflowService {
    private final OrderRepository orders;
    private final AuditService auditService;

    OrderWorkflowService(OrderRepository orders, AuditService auditService) {
        this.orders = orders;
        this.auditService = auditService;
    }

    @Transactional(transactionManager = "ordersTransactionManager")
    public Order createOrder(String customerId) {
        Order order = orders.save(new Order(customerId));
        auditService.record(order.id());
        return order;
    }
}

@Service
class AuditService {
    private final AuditRepository audits;

    AuditService(AuditRepository audits) {
        this.audits = audits;
    }

    @Transactional(transactionManager = "auditTransactionManager")
    public void record(String orderId) {
        audits.save(new AuditEntry(orderId, "ORDER_CREATED"));
    }
}
```

Nếu test được đánh dấu `@Transactional("ordersTransactionManager")`, thao tác tạo order có thể tham gia transaction test của orders. Lời gọi `AuditService.record()` sử dụng manager khác, nên nó mở transaction audit riêng và có thể commit độc lập. Khi transaction test của orders rollback, audit record vẫn có thể tồn tại.

Điều này không phải lỗi của Spring. Hai transaction manager cục bộ không tự phối hợp commit/rollback như một transaction phân tán. Test cần dự đoán đúng dữ liệu nào sẽ được rollback và cleanup những dữ liệu đã commit ở nguồn khác.

### 7.1. Không giả định `@Transactional` test bao trùm mọi datasource

Một annotation trên test method không tự động bao trùm mọi manager trong context. Nó chọn một manager. Các repository thuộc datasource khác có thể dùng transaction riêng, hoặc chạy theo chế độ không có transaction tương ứng tùy cấu hình.

Khi test workflow nhiều datasource, hãy xác định rõ:

- Lệnh ghi nào dùng manager orders?
- Lệnh ghi nào dùng manager audit?
- Transaction của service có tham gia transaction test hay mở transaction riêng?
- Dữ liệu nào rollback cùng test và dữ liệu nào đã commit độc lập?
- Cần cleanup datasource phụ bằng cách nào?

Nếu cần một transaction nguyên tử bao trùm nhiều XA datasource, cần cấu hình JTA transaction manager và XA-capable resource phù hợp. Hai `DataSourceTransactionManager` hoặc hai `JpaTransactionManager` độc lập không cung cấp atomic commit xuyên datasource.

## 8. Propagation khi test gọi service có manager khác

Propagation quyết định cách một phương thức transactional tham gia hoặc tạo transaction. `REQUIRED` là mặc định: method tham gia transaction hiện có của cùng transaction manager hoặc tạo transaction mới nếu chưa có.

Điểm cần chú ý là transaction hiện có phải thuộc manager mà method đang dùng. Một transaction orders không tự trở thành transaction hiện có cho audit manager.

| Test transaction | Service transaction | Hành vi thường gặp |
|---|---|---|
| `ordersTransactionManager` | `ordersTransactionManager`, `REQUIRED` | Service tham gia transaction test |
| `ordersTransactionManager` | `auditTransactionManager`, `REQUIRED` | Audit manager mở transaction riêng nếu cần |
| `auditTransactionManager` | `auditTransactionManager`, `REQUIRED` | Service audit tham gia transaction test |
| Không có test transaction | `ordersTransactionManager`, `REQUIRED` | Service mở transaction orders riêng |
| `ordersTransactionManager` | `ordersTransactionManager`, `REQUIRES_NEW` | Service tạm ngưng transaction test và mở transaction orders mới |

`REQUIRES_NEW` trên cùng manager có thể commit độc lập với transaction test bên ngoài. Dữ liệu đó có thể vẫn tồn tại sau rollback của test transaction. Khi dùng propagation này, test phải cleanup hoặc kiểm tra commit behavior một cách chủ đích.

Các propagation `NESTED`, `SUPPORTS`, `NOT_SUPPORTED`, `MANDATORY` và `NEVER` cũng có ý nghĩa riêng. Đừng dùng propagation để giải quyết lỗi chọn manager; trước tiên hãy bảo đảm đúng manager được chỉ định.

## 9. Kiểm tra rollback và commit trong test

Mặc định, test-managed transaction được rollback sau test. Có thể điều khiển bằng `@Rollback` hoặc `@Commit`:

```java
@Test
@Transactional("ordersTransactionManager")
@Rollback
void rollsBackOrderAfterTest() {
    orders.save(new Order("customer-42"));
}
```

`@Rollback` mặc định là `true`. Có thể dùng `@Commit` hoặc `@Rollback(false)` để commit transaction test khi cần kiểm tra hành vi commit:

```java
@Test
@Transactional("ordersTransactionManager")
@Commit
void commitsOrderAfterTest() {
    orders.save(new Order("customer-42"));
}
```

Test commit sẽ để lại dữ liệu trong database. Cần dùng dữ liệu có định danh riêng và cleanup rõ ràng để các lần chạy không ảnh hưởng nhau.

### 9.1. Kiểm tra dữ liệu sau khi transaction kết thúc

`@BeforeTransaction` và `@AfterTransaction` cho phép chạy callback trước khi test transaction bắt đầu hoặc sau khi nó kết thúc. Chúng hữu ích khi cần kiểm tra trạng thái đã commit hoặc đã rollback từ bên ngoài transaction test:

```java
@SpringBootTest
@Transactional("ordersTransactionManager")
class OrderRollbackTest {
    @Autowired
    private OrderRepository orders;

    private String orderId;

    @Test
    void rollsBackCreatedOrder() {
        Order order = orders.save(new Order("customer-42"));
        orderId = order.id();

        assertThat(orders.findById(orderId)).isPresent();
    }

    @AfterTransaction
    void verifiesOrderWasRolledBack() {
        assertThat(orders.findById(orderId)).isEmpty();
    }
}
```

Ví dụ giả định repository đọc dữ liệu qua transaction mới hoặc cơ chế phù hợp sau khi test transaction đã rollback. Nếu repository method tự mở transaction read-only, callback có thể đọc trạng thái đã commit từ database. Với JPA, hãy chú ý persistence context và cache; không dùng một entity đang được quản lý trong transaction đã kết thúc làm bằng chứng cho dữ liệu đã rollback.

`@BeforeTransaction` có thể tạo dữ liệu nền trước khi transaction test bắt đầu. `@AfterTransaction` phù hợp để xác nhận dữ liệu sau commit/rollback hoặc dọn dữ liệu đã commit từ một manager khác.

### 9.2. `TestTransaction`

Spring Test cung cấp `TestTransaction` để kiểm soát test-managed transaction trong lúc test đang chạy:

```java
@Test
@Transactional("ordersTransactionManager")
void commitsCurrentTestTransactionExplicitly() {
    orders.save(new Order("customer-42"));

    TestTransaction.flagForCommit();
    TestTransaction.end();

    assertThat(TestTransaction.isActive()).isFalse();
}
```

`TestTransaction` thao tác trên transaction test-managed hiện tại, tức transaction đã được chọn qua annotation của test. Nó không nhận tên manager ở mỗi lời gọi. Nếu test cần một transaction khác, hãy dùng `TransactionTemplate` hoặc transaction API với manager tương ứng.

Sau `TestTransaction.end()`, có thể bắt đầu một transaction test mới bằng `TestTransaction.start()` nếu cấu hình test cho phép và cần tiếp tục kiểm tra trong một transaction mới. Hãy phân biệt rõ transaction đã kết thúc với persistence context hoặc entity reference còn nằm trong field của test.

## 10. Dùng `TransactionTemplate` khi cần điều khiển manager tường minh

Khi một test cần tạo transaction cho nhiều manager hoặc cần kiểm soát commit/rollback theo từng resource, `TransactionTemplate` là lựa chọn tường minh:

```java
@SpringBootTest
class MultiDatabaseTransactionTest {
    @Autowired
    @Qualifier("ordersTransactionManager")
    private PlatformTransactionManager ordersManager;

    @Autowired
    @Qualifier("auditTransactionManager")
    private PlatformTransactionManager auditManager;

    @Autowired
    private OrderRepository orders;

    @Autowired
    private AuditRepository audits;

    @Test
    void controlsEachLocalTransactionSeparately() {
        TransactionTemplate ordersTx = new TransactionTemplate(ordersManager);
        TransactionTemplate auditTx = new TransactionTemplate(auditManager);

        ordersTx.executeWithoutResult(status -> {
            orders.save(new Order("customer-42"));
            status.setRollbackOnly();
        });

        auditTx.executeWithoutResult(status -> {
            audits.save(new AuditEntry("order-42", "TEST_EVENT"));
            status.setRollbackOnly();
        });

        // Mỗi template đã rollback transaction thuộc manager tương ứng.
    }
}
```

Ví dụ tạo hai transaction cục bộ và đánh dấu rollback độc lập. Đây không phải một transaction nguyên tử chung; nếu một transaction commit còn transaction kia thất bại, dữ liệu có thể ở trạng thái không đồng nhất. `TransactionTemplate` phù hợp để test điều khiển từng manager, không thay thế JTA khi cần distributed transaction.

Nếu chỉ muốn xác nhận test-managed transaction chọn đúng manager, dùng `@Transactional("...TransactionManager")` sẽ đơn giản hơn. Chỉ chuyển sang `TransactionTemplate` khi test cần điều khiển nhiều transaction boundary hoặc cần commit/rollback chủ động.

## 11. `@DataJpaTest` với nhiều datasource

`@DataJpaTest` mặc định tập trung vào một persistence setup và thường cấu hình transaction test tự động. Khi ứng dụng có nhiều `EntityManagerFactory` và transaction manager, test slice cần biết repository package nào gắn với manager nào.

Có thể dùng `@Import` để nạp cấu hình JPA bổ sung và chỉ định manager trên test:

```java
@DataJpaTest
@Import(MultiJpaTestConfiguration.class)
@Transactional("auditTransactionManager")
class AuditRepositoryTest {
    @Autowired
    private AuditRepository audits;
}
```

Tùy cấu hình Spring Boot và cách khai báo datasource, test slice có thể cần `@AutoConfigureTestDatabase(replace = Replace.NONE)` để giữ datasource được cấu hình thay vì thay bằng embedded database. Khi có nhiều datasource, cần xác định datasource nào là primary và cấu hình repository/EntityManagerFactory riêng cho datasource còn lại.

Không giả định `@DataJpaTest` tự động tạo test transaction cho tất cả `JpaTransactionManager`. Chọn manager cụ thể bằng annotation test và xác nhận repository đang dùng đúng `EntityManagerFactory`.

Nếu mục tiêu là kiểm tra cấu hình nhiều datasource, nhiều entity manager và wiring đầy đủ, `@SpringBootTest` có thể phù hợp hơn slice test. Nếu chỉ kiểm tra repository thuộc một persistence unit, giữ test context hẹp bằng cấu hình import cụ thể.

## 12. Test transaction với JDBC và `JdbcTemplate`

Khi dùng nhiều JDBC datasource, mỗi `JdbcTemplate` cần được tạo từ đúng datasource:

```java
@Configuration
class JdbcTemplateConfiguration {
    @Bean
    JdbcTemplate ordersJdbcTemplate(
            @Qualifier("ordersDataSource") DataSource dataSource) {
        return new JdbcTemplate(dataSource);
    }

    @Bean
    JdbcTemplate auditJdbcTemplate(
            @Qualifier("auditDataSource") DataSource dataSource) {
        return new JdbcTemplate(dataSource);
    }
}
```

Khi test dùng `@Transactional("ordersTransactionManager")`, các thao tác JDBC qua `ordersJdbcTemplate` có thể tham gia transaction test nếu sử dụng cùng datasource và transaction-aware connection lookup của Spring. Các thao tác qua `auditJdbcTemplate` không tự tham gia transaction orders.

Để kiểm tra manager thực sự gắn với datasource nào, có thể thực hiện insert bằng template tương ứng rồi đọc lại sau rollback trong một transaction khác. Không chỉ kiểm tra tên bean hoặc số lượng manager; hành vi lưu và rollback trên đúng database là bằng chứng trực tiếp hơn.

## 13. Giao dịch xuyên nhiều datasource và JTA

Hai local transaction manager độc lập không cung cấp atomicity xuyên datasource. Ví dụ, service commit order vào database A rồi ghi audit vào database B. Nếu database B lỗi sau khi A đã commit, hệ thống có thể có order nhưng thiếu audit record.

Nếu nghiệp vụ thật sự yêu cầu một transaction nguyên tử giữa nhiều resource XA, cần transaction coordinator JTA và datasource/driver hỗ trợ XA. `JtaTransactionManager` tham gia điều phối transaction phân tán; mỗi resource cần được đăng ký với coordinator phù hợp.

Không phải mọi ứng dụng đều cần XA. Nhiều hệ thống dùng outbox pattern, saga hoặc eventual consistency để phối hợp dữ liệu giữa database và message broker. Khi kiểm thử, hãy kiểm tra cơ chế thực tế của ứng dụng:

- Với XA/JTA: kiểm tra commit và rollback toàn cục bằng môi trường hỗ trợ XA.
- Với outbox: xác nhận business record và outbox record được commit cùng transaction của database tương ứng, sau đó kiểm tra publisher xử lý outbox.
- Với saga: kiểm tra các bước thành công và compensation khi một bước sau thất bại.
- Với hai local transaction độc lập: xác nhận rõ kết quả có thể tồn tại một phần và cleanup dữ liệu test theo từng nguồn.

Một test transaction trên một manager không chứng minh atomicity của workflow nhiều datasource. Test phải chạy qua transaction coordinator hoặc cơ chế phối hợp mà production sử dụng.

## 14. Chẩn đoán lỗi chọn transaction manager

### 14.1. `NoUniqueBeanDefinitionException`

Lỗi này thường xuất hiện khi Spring cần một `PlatformTransactionManager` nhưng có nhiều bean cùng kiểu và không có lựa chọn mặc định rõ ràng.

Cách xử lý:

- Chỉ định `@Transactional(transactionManager = "...TransactionManager")` tại service hoặc test.
- Đặt tên bean mặc định `transactionManager` nếu có một manager chính.
- Dùng `@Primary` cho lựa chọn mặc định khi phù hợp với injection theo type.
- Dùng `TransactionManagementConfigurer` khi muốn cấu hình manager mặc định cho annotation-driven transaction.

Không thêm `@Primary` tùy tiện nếu các service thuộc datasource khác cần manager riêng. Qualifier trên transaction boundary thường thể hiện đúng ý định hơn.

### 14.2. Không tìm thấy bean theo qualifier

Nếu lỗi nói không tìm thấy manager có tên hoặc qualifier đã chỉ định, kiểm tra tên bean trong `@Bean`, `@Component` hoặc cấu hình auto-configuration. Tên trong `@Transactional` phải khớp với bean name hoặc qualifier được đăng ký.

Ví dụ, `@Transactional("auditTxManager")` sẽ không tự khớp với bean tên `auditTransactionManager` nếu không có alias hoặc qualifier tương ứng.

### 14.3. Repository dùng sai datasource

Nếu test transaction rollback nhưng dữ liệu vẫn còn, có thể repository đang dùng manager khác hoặc thao tác ghi chạy trong transaction riêng. Kiểm tra `entityManagerFactoryRef`, `transactionManagerRef`, qualifier datasource và manager trên service.

Với JPA, kiểm tra repository package được gắn đúng persistence unit. Với JDBC, kiểm tra `JdbcTemplate` được tạo từ datasource nào.

### 14.4. Test rollback một database nhưng database khác vẫn có dữ liệu

Đây thường là hành vi đúng khi hai nguồn dùng manager độc lập. Xác định manager của từng thao tác và cleanup nguồn đã commit. Không tăng mức rollback hoặc thêm `@DirtiesContext` với kỳ vọng nó sẽ hoàn tác transaction của manager khác.

### 14.5. Service không tham gia transaction test

Kiểm tra service có gọi qua Spring proxy hay không. Self-invocation trong cùng bean có thể không đi qua transactional proxy. Kiểm tra manager trên method, propagation và việc test đang dùng cùng manager hay không.

### 14.6. Test context không khởi tạo do cấu hình JPA nhiều nguồn

Kiểm tra mỗi `@EnableJpaRepositories` có package, `entityManagerFactoryRef` và `transactionManagerRef` đúng. Kiểm tra bean name không trùng, `@Primary` hợp lý và mỗi factory dùng đúng datasource/entity package.

## 15. Quy trình chọn manager cho một integration test

Khi test có nhiều datasource, hãy xác định lần lượt:

1. Test đang đọc/ghi vào repository hoặc `JdbcTemplate` nào?
2. Repository đó được gắn với datasource và `EntityManagerFactory` nào?
3. Transaction manager nào điều phối resource đó?
4. Test cần transaction rollback hay cần commit để kiểm tra hành vi sau commit?
5. Service được gọi có dùng manager cùng tên hay mở transaction trên manager khác?
6. Có tác dụng phụ nào đã commit ngoài transaction test không?
7. Cần cleanup dữ liệu ở datasource phụ hoặc tài nguyên ngoài bằng cách nào?
8. Nếu workflow cần atomicity giữa nhiều datasource, production đang dùng JTA/XA, outbox hay saga?

Sau đó ghi manager rõ ràng trên `@Transactional` của test:

```java
@SpringBootTest
@Transactional(transactionManager = "ordersTransactionManager")
class OrderWorkflowIntegrationTest {
    // Test transaction được quản lý bởi orders manager.
}
```

Nếu test cần manager khác, dùng một test class riêng hoặc method-level annotation để chỉ rõ ranh giới. Tránh gom nhiều kịch bản có manager khác nhau vào một class rồi dựa vào manager mặc định.

## 16. Ví dụ tổng hợp: kiểm tra rollback trên đúng nguồn dữ liệu

Giả sử ứng dụng có hai repository: `OrderRepository` dùng orders database và `AuditRepository` dùng audit database. Mỗi repository có transaction manager riêng.

```java
@SpringBootTest
class MultiDatabaseIntegrationTest {
    @Autowired
    private OrderRepository orders;

    @Autowired
    private AuditRepository audits;

    @Test
    @Transactional("ordersTransactionManager")
    void rollsBackOrdersDatabaseTransaction() {
        Order order = orders.save(new Order("customer-42"));

        assertThat(orders.findById(order.id())).isPresent();
    }

    @Test
    @Transactional("auditTransactionManager")
    void rollsBackAuditDatabaseTransaction() {
        AuditEntry entry = audits.save(
                new AuditEntry("order-42", "TEST_EVENT"));

        assertThat(audits.findById(entry.id())).isPresent();
    }
}
```

Mỗi method chọn manager tương ứng. Spring rollback transaction của manager đó sau test. Nếu test cần xác nhận dữ liệu đã biến mất sau rollback, có thể dùng `@AfterTransaction` hoặc một transaction mới để đọc lại dữ liệu.

Với workflow ghi cả hai datasource, hãy viết test riêng để chứng minh ranh giới thực tế. Nếu audit manager commit độc lập, test phải xóa audit record sau khi kiểm tra. Nếu production dùng outbox hoặc JTA, test phải chạy qua cơ chế đó và xác nhận trạng thái cuối theo đúng hợp đồng.

## 17. Nguyên tắc cần nhớ

- Mỗi `PlatformTransactionManager` quản lý transaction cho resource hoặc nhóm resource được cấu hình với nó.
- Đặt tên manager rõ ràng và dùng `@Qualifier` khi inject datasource hoặc manager cùng kiểu.
- `@Transactional` có thể chọn manager bằng `transactionManager` hoặc alias `value`.
- Khi có nhiều manager, xác định manager mặc định bằng bean name `transactionManager`, `@Primary` phù hợp hoặc `TransactionManagementConfigurer`.
- Với nhiều JPA datasource, gắn đúng `EntityManagerFactory` và `transactionManager` vào từng repository package.
- Test-managed transaction dùng manager được chọn trên `@Transactional` của test và mặc định rollback sau method.
- Rollback của một manager chỉ áp dụng cho transaction/resource do manager đó quản lý; datasource khác có thể đã commit độc lập.
- `REQUIRED` chỉ tham gia transaction hiện có của cùng manager; transaction của manager khác không tự được chia sẻ.
- Dùng `TransactionTemplate` khi cần điều khiển riêng nhiều transaction manager; dùng JTA/XA nếu nghiệp vụ cần atomic transaction phân tán và hạ tầng hỗ trợ.
- Kiểm tra dữ liệu sau transaction bằng callback hoặc transaction mới, và cleanup riêng những nguồn đã commit.

Khi có nhiều nguồn dữ liệu, việc chọn transaction manager là một phần của hợp đồng kiểm thử. Ghi rõ manager trên test và service giúp xác định chính xác resource nào được commit hoặc rollback, tránh để dữ liệu test rò rỉ giữa các lần chạy và làm rõ giới hạn nhất quán của workflow nhiều database.
