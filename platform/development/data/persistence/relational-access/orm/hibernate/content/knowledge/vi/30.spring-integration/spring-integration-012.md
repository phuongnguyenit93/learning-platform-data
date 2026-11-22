# Phối hợp nhiều DataSource mà không giả định có một giao dịch chung

## 1. Vấn đề thực tế: hai database không tự chia sẻ một transaction

Một ứng dụng Spring Boot có thể truy cập nhiều nguồn dữ liệu quan hệ:

- Database `orders` lưu đơn hàng và dòng hàng.
- Database `billing` lưu hóa đơn và giao dịch thanh toán.
- Database `reporting` cung cấp báo cáo hoặc bản sao đọc.
- Database của một hệ thống cũ dùng schema và quyền truy cập riêng.

Việc khai báo hai `DataSource` trong cùng một Spring `ApplicationContext` **không** khiến chúng tự thuộc một giao dịch nguyên tử. Tương tự, việc một service có `@Transactional` không bảo đảm mọi repository được gọi từ service ấy cùng commit hoặc rollback.

Ví dụ nghiệp vụ:

```text
Yêu cầu: Tạo Order trong DB A, ghi BillingRecord trong DB B.

DB A (orders)                    DB B (billing)
  INSERT order                     INSERT billing_record
      |                                   |
      v                                   v
  commit A                             commit B

Câu hỏi: Nếu chỉ một trong hai commit thành công thì sao?
```

Nếu một transaction manager quản lý DB A và một transaction manager khác quản lý DB B, mỗi manager chỉ có thể commit/rollback tài nguyên của mình. DB B có thể commit trước rồi DB A rollback; hoặc DB A đã commit nhưng DB B lỗi. Đây là một dạng **dual write** cần thiết kế tính nhất quán, không chỉ là bài toán inject đúng bean.

Bài học này phân biệt cấu hình nhiều `DataSource`, giới hạn transaction cục bộ, các phương án phối hợp có/không có distributed transaction, và cách kiểm thử tình huống lỗi thật.

## 2. Những khái niệm phải tách biệt

| Khái niệm | Vai trò | Phạm vi thường gặp |
|---|---|---|
| `DataSource` | Cung cấp JDBC `Connection` | Một database/cluster hoặc endpoint |
| `Connection` | Thực thi SQL trong JDBC transaction | Connection riêng lẻ |
| `EntityManagerFactory` | Khởi tạo các JPA `EntityManager` cho một persistence unit | Metadata/mapping của một persistence unit |
| `EntityManager` | Quản lý persistence context và thao tác JPA | Unit of work/transaction |
| Hibernate `SessionFactory` | Implementation native tương ứng JPA factory | Một tập mapping/cache/service |
| `PlatformTransactionManager` | Abstraction của Spring quản lý begin/commit/rollback | Tài nguyên mà manager biết cách điều khiển |
| `JpaTransactionManager` | Transaction manager cho một JPA `EntityManagerFactory` | Thông thường là một local JPA transaction |
| `DataSourceTransactionManager` | Transaction manager JDBC trên một `DataSource` | Một local JDBC transaction |
| `JtaTransactionManager` | Spring adapter tới JTA coordinator | Có thể quản lý distributed transaction nếu XA được cấu hình thật |

Từ khóa dễ gây hiểu nhầm là “transaction”. Spring cung cấp một API thống nhất nhưng API ấy **không tự biến hai local transactions thành một distributed transaction**.

### 2.1. Ba tầng khác nhau

```text
Spring @Transactional
      |
      v
Spring PlatformTransactionManager
      |
      +-- JpaTransactionManager A --> EMF A --> DataSource A
      |
      +-- JpaTransactionManager B --> EMF B --> DataSource B

Không có đường nối commit nguyên tử giữa A và B
chỉ vì cả hai cùng nằm trong ApplicationContext.
```

Muốn atomic commit trên nhiều resources phải có kiến trúc đáp ứng yêu cầu đó, ví dụ **XA/JTA với transaction coordinator và resource managers hỗ trợ 2PC**, hoặc thay đổi thiết kế để chỉ cần một database transaction.

## 3. Những kiểu nhiều DataSource thường gặp

Không phải mọi bài toán có nhiều DataSource đều cần distributed transaction.

| Kiểu hệ thống | Ví dụ | Vấn đề chính |
|---|---|---|
| Hai DB độc lập cùng có ghi | Orders DB + Billing DB | Dual write, partial commit |
| DB ghi và read replica | Primary DB + replica | Replication lag, read-your-writes |
| DB nghiệp vụ và DB báo cáo | Orders DB + Analytics DB | Eventual consistency, projection |
| DB của hai bounded contexts | Catalog DB + Inventory DB | Không có FK/transaction chung |
| Hai schema trên cùng DBMS | `orders` schema + `accounting` schema | Có thể chung transaction **nếu dùng cùng connection/resource** |
| Nhiều tenant với DS riêng | Mỗi tenant dùng một database | Tenant isolation, routing, resource management |
| Một DB chính và một DB legacy | Ứng dụng mới + hệ thống cũ | Integration, reconciliation, idempotency |

Ví dụ orders/reporting thường phù hợp với outbox và xử lý bất đồng bộ. Ví dụ chuyển tiền giữa hai sổ cái có thể cần thiết kế consistency nghiêm ngặt hơn, và không nên coi một bản sao báo cáo là nguồn sự thật.

## 4. Local transaction gắn với một tài nguyên cụ thể

Một JDBC local transaction thực hiện các thao tác trên một connection:

```java
connection.setAutoCommit(false);
try {
    // INSERT và UPDATE trên chính connection này.
    connection.commit();
} catch (SQLException ex) {
    connection.rollback();
    throw ex;
}
```

Đoạn code minh họa JDBC thuần, không nên tự gọi `commit()`/`rollback()` trên connection mà Spring/Hibernate đang quản lý.

Nếu tạo hai connections từ hai DataSource:

```text
Connection A -> BEGIN / COMMIT / ROLLBACK A
Connection B -> BEGIN / COMMIT / ROLLBACK B
```

thì hai lời gọi commit độc lập. Khi commit A đã thành công, rollback B không thể tự hoàn tác giao dịch đã commit ở A.

Ngay cả **hai connection pools trỏ vào cùng một server database** cũng không tự có một local transaction chung. Điều quan trọng là transaction scope và connection/resource thực sự tham gia, không phải việc hai JDBC URL giống nhau.

## 5. @Transactional chọn transaction manager nào?

Với một persistence unit, code thường:

```java
@Service
public class OrderService {
    @Transactional
    public void createOrder(...) {
        // ...
    }
}
```

Spring có thể chọn default transaction manager được cấu hình cho application. Nhưng khi có nhiều managers, việc để mặc định có thể mơ hồ hoặc vô tình chọn sai manager.

Nên chỉ định rõ:

```java
@Transactional(transactionManager = "ordersTransactionManager")
public void createOrder(...) {
    // Chỉ định rõ transaction thuộc Orders persistence unit.
}
```

Và:

```java
@Transactional(transactionManager = "billingTransactionManager")
public void postBillingRecord(...) {
    // Transaction riêng của Billing persistence unit.
}
```

Tên managers là bean names do ứng dụng định nghĩa. `@Primary` có thể giúp Spring chọn một bean khi injection cần single candidate, nhưng **không** biến manager ấy thành coordinator cho các resources khác.

## 6. Rủi ro khi gọi hai repository từ một method

Giả sử:

```java
@Service
public class CheckoutService {
    private final OrderRepository orders;
    private final BillingService billing;

    public CheckoutService(
            OrderRepository orders,
            BillingService billing) {
        this.orders = orders;
        this.billing = billing;
    }

    @Transactional("ordersTransactionManager")
    public void checkout(CheckoutCommand command) {
        Order order = orders.save(Order.from(command));
        billing.recordInvoice(order.getId(), command.amount());

        // Sau đó có thể phát sinh exception.
        performFinalOrderValidation(order);
    }
}
```

Nếu `billing.recordInvoice()` được thực thi qua Spring proxy với `@Transactional("billingTransactionManager")`, một billing transaction riêng có thể bắt đầu và commit khi method ấy trả về.

```text
CheckoutService.checkout()
  Orders transaction A begins
      |
      +-- orders.save()             (pending in A)
      |
      +-- billing.recordInvoice()
      |       Billing transaction B begins
      |       INSERT billing record
      |       COMMIT B
      |
      +-- performFinalOrderValidation() throws
      |
      ROLLBACK A

Kết quả:
  Orders DB: order không được commit
  Billing DB: billing record có thể đã commit
```

Đây là ví dụ **partial commit**. Spring không tự phát hiện rằng transaction B phải bị “uncommit” khi A rollback.

### 6.1. Chiều ngược lại cũng nguy hiểm

Nếu commit Orders trước rồi mới gọi Billing, Orders có thể đã được commit nhưng Billing thất bại. Vấn đề không biến mất chỉ bằng cách đổi thứ tự hai bước; thứ tự chỉ quyết định hệ thống phải xử lý kiểu partial failure nào.

## 7. Transaction propagation không phải distributed commit

Spring có các propagation modes như `REQUIRED`, `REQUIRES_NEW`, `MANDATORY` và `NESTED`.

- `REQUIRED` thường tham gia transaction hiện có **do đúng transaction manager đó quản lý**, hoặc bắt đầu transaction mới.
- `REQUIRES_NEW` yêu cầu transaction độc lập và có thể suspend transaction hiện tại **trong cùng hạ tầng transaction được chọn**.
- `NESTED` liên quan khả năng savepoint/transaction manager hỗ trợ.

Điều quan trọng: đổi propagation không khiến `ordersTransactionManager` điều khiển được `billingTransactionManager`.

Ví dụ:

```java
@Transactional(
    transactionManager = "billingTransactionManager",
    propagation = Propagation.REQUIRES_NEW)
public void writeBilling(...) {
    // Đây vẫn là transaction của Billing manager.
}
```

`REQUIRES_NEW` không phải cách “gom nhiều DB thành một transaction”. Nó thậm chí có thể khiến một công việc commit độc lập rõ ràng hơn, làm yêu cầu nhất quán đồng thời càng khó đạt.

### 7.1. Self-invocation có thể làm mất transaction boundary

Trong proxy-based Spring AOP, method `@Transactional` gọi trực tiếp qua `this.otherMethod()` trong cùng object có thể không đi qua proxy nên không kích hoạt interceptor như mong muốn.

Khi thiết kế nhiều transaction boundaries, nên dùng các Spring-managed services rõ ràng, gọi qua proxy và kiểm thử commit/rollback thật. Không chỉ nhìn thấy annotation rồi kết luận boundary đã được áp dụng.

## 8. Cấu hình hai DataSource riêng trong Spring Boot

Giả sử ứng dụng có hai persistence units:

```text
com.example.app
  ├── orders
  │    ├── entity
  │    ├── repository
  │    └── service
  ├── billing
  │    ├── entity
  │    ├── repository
  │    └── service
  └── config
       ├── OrdersJpaConfiguration
       └── BillingJpaConfiguration
```

Một cấu hình YAML ví dụ:

```yaml
app:
  datasource:
    orders:
      url: jdbc:postgresql://orders-db:5432/orders
      username: orders_app
      hikari:
        maximum-pool-size: 12
    billing:
      url: jdbc:postgresql://billing-db:5432/billing
      username: billing_app
      hikari:
        maximum-pool-size: 8

spring:
  jpa:
    open-in-view: false
```

Password của mỗi datasource nên được cung cấp từ secret manager/environment theo cách cấu hình production; ví dụ không ghi thông tin xác thực thật vào tài liệu hoặc git.

Khi tự cấu hình nhiều DataSource, nên rõ ràng về:

- Bean name cho DataSource.
- Bean name cho `EntityManagerFactory`.
- Entity package của mỗi persistence unit.
- Repository package của mỗi factory.
- Bean name cho transaction manager tương ứng.
- Migration và schema validation của mỗi database.

### 8.1. DataSourceProperties giúp xử lý URL

Một mẫu phổ biến của Spring Boot:

```java
@Bean("ordersDataSourceProperties")
@Primary
@ConfigurationProperties("app.datasource.orders")
DataSourceProperties ordersDataSourceProperties() {
    return new DataSourceProperties();
}

@Bean("ordersDataSource")
@Primary
@ConfigurationProperties("app.datasource.orders.hikari")
HikariDataSource ordersDataSource(
        @Qualifier("ordersDataSourceProperties")
        DataSourceProperties properties) {
    return properties.initializeDataSourceBuilder()
        .type(HikariDataSource.class)
        .build();
}
```

`DataSourceProperties` chuyển property `url` sang thông số phù hợp cho datasource implementation; phần Hikari-specific properties được bind riêng. Đây là mẫu minh họa cho Spring Boot và HikariCP, cần có imports/dependencies đúng của version dự án.

Billing DataSource tương tự:

```java
@Bean("billingDataSourceProperties")
@ConfigurationProperties("app.datasource.billing")
DataSourceProperties billingDataSourceProperties() {
    return new DataSourceProperties();
}

@Bean("billingDataSource")
@ConfigurationProperties("app.datasource.billing.hikari")
HikariDataSource billingDataSource(
        @Qualifier("billingDataSourceProperties")
        DataSourceProperties properties) {
    return properties.initializeDataSourceBuilder()
        .type(HikariDataSource.class)
        .build();
}
```

Hai method groups thuộc các `@Configuration` classes được đăng ký như Spring beans. Không đặt cả hai cùng tên bean `dataSource` hoặc dùng injection không có qualifier rồi hy vọng Spring tự hiểu DB nào dành cho repository nào.

## 9. Ánh xạ mỗi JPA persistence unit đến đúng DataSource

Với Spring Boot JPA có `EntityManagerFactoryBuilder` trong cấu hình phù hợp, một mẫu:

```java
@Configuration(proxyBeanMethods = false)
@EnableJpaRepositories(
    basePackages = "com.example.app.orders.repository",
    entityManagerFactoryRef = "ordersEntityManagerFactory",
    transactionManagerRef = "ordersTransactionManager")
class OrdersJpaConfiguration {

    @Bean("ordersEntityManagerFactory")
    @Primary
    LocalContainerEntityManagerFactoryBean ordersEntityManagerFactory(
            EntityManagerFactoryBuilder builder,
            @Qualifier("ordersDataSource") DataSource dataSource) {
        return builder
            .dataSource(dataSource)
            .packages("com.example.app.orders.entity")
            .persistenceUnit("ordersUnit")
            .build();
    }

    @Bean("ordersTransactionManager")
    @Primary
    PlatformTransactionManager ordersTransactionManager(
            @Qualifier("ordersEntityManagerFactory")
            EntityManagerFactory emf) {
        return new JpaTransactionManager(emf);
    }
}
```

Một cấu hình khác:

```java
@Configuration(proxyBeanMethods = false)
@EnableJpaRepositories(
    basePackages = "com.example.app.billing.repository",
    entityManagerFactoryRef = "billingEntityManagerFactory",
    transactionManagerRef = "billingTransactionManager")
class BillingJpaConfiguration {

    @Bean("billingEntityManagerFactory")
    LocalContainerEntityManagerFactoryBean billingEntityManagerFactory(
            EntityManagerFactoryBuilder builder,
            @Qualifier("billingDataSource") DataSource dataSource) {
        return builder
            .dataSource(dataSource)
            .packages("com.example.app.billing.entity")
            .persistenceUnit("billingUnit")
            .build();
    }

    @Bean("billingTransactionManager")
    PlatformTransactionManager billingTransactionManager(
            @Qualifier("billingEntityManagerFactory")
            EntityManagerFactory emf) {
        return new JpaTransactionManager(emf);
    }
}
```

Các đoạn code là cấu hình khung, giả định DataSource beans ở mục trước đã được định nghĩa và các imports Spring Boot/Spring ORM/Spring Data/Hikari tương thích. Khả năng Boot tự cung cấp `EntityManagerFactoryBuilder` phụ thuộc điều kiện auto-configuration và phiên bản. Nếu ứng dụng không có builder bean, phải cấu hình builder/EMF tường minh theo phiên bản đang dùng; không copy code mà bỏ qua condition report.

### 9.1. Vì sao cả factory và manager phải chỉ định rõ?

`entityManagerFactoryRef` cho repository biết persistence unit nào quản lý entity; `transactionManagerRef` cho repository biết transaction manager nào thực thi các transaction methods.

Hai references cần tương ứng cùng database. Nếu cấu hình sai, ứng dụng có thể:

- Báo `Not a managed type` vì repository dùng EMF không chứa entity.
- Không tìm thấy transaction manager được khai báo.
- Gặp transaction mismatch hoặc lỗi connection khi chạy query.
- Ghi nhầm database, đặc biệt khi hai DB có bảng tên giống nhau.

Đánh dấu một bean `@Primary` chỉ giúp một số injection/autoconfiguration chọn candidate mặc định; không chứng minh mapping repository đã đúng và không tạo transaction nguyên tử cho hai factories.

## 10. @PersistenceContext với hai EntityManagerFactory

Nếu dùng DAO thay vì chỉ repository:

```java
@Repository
public class CrossSourceReadDao {
    @PersistenceContext(unitName = "ordersUnit")
    private EntityManager ordersEm;

    @PersistenceContext(unitName = "billingUnit")
    private EntityManager billingEm;
}
```

Giá trị `unitName` phải khớp với persistence unit được cấu hình tương ứng; không nhầm bean name và persistence unit name nếu ứng dụng dùng cách đặt tên riêng.

Ở Spring, EntityManager được inject thường là shared proxy định tuyến tới persistence context đúng scope. EntityManager concrete không thread-safe và không được giữ như global singleton. Có **hai EntityManagers khác nhau** không có nghĩa chúng chia sẻ một persistence context hoặc một database transaction.

Với hai factories, entity cùng Java class name ở hai packages hoặc hai databases cũng không phải cùng một managed identity. Hibernate quản lý identity/cache theo persistence unit riêng.

## 11. Dùng đúng transaction manager trong từng service

Ví dụ:

```java
@Service
public class OrderWriteService {
    private final OrderRepository orders;

    public OrderWriteService(OrderRepository orders) {
        this.orders = orders;
    }

    @Transactional("ordersTransactionManager")
    public Long createOrder(CreateOrderCommand command) {
        Order order = Order.create(command);
        orders.save(order);
        return order.getId();
    }
}
```

Billing:

```java
@Service
public class BillingWriteService {
    private final BillingRecordRepository records;

    public BillingWriteService(BillingRecordRepository records) {
        this.records = records;
    }

    @Transactional("billingTransactionManager")
    public void createRecord(BillingCommand command) {
        records.save(BillingRecord.from(command));
    }
}
```

Mỗi service có local transaction đúng resource của mình. Đây là thiết kế tốt **nếu** nghiệp vụ chấp nhận rằng hai thao tác độc lập, hoặc nếu có workflow giải quyết trường hợp chỉ một trong hai thành công.

Nếu nghiệp vụ đòi hỏi atomicity trên hai DB, chỉ thêm hai annotation không đáp ứng yêu cầu ấy.

## 12. Tại sao JpaTransactionManager chỉ quản lý một EMF?

`JpaTransactionManager` gắn với một `EntityManagerFactory`. Nó mở/tham gia JPA transaction và ràng buộc EntityManager thích hợp với execution context của Spring.

Ví dụ:

```text
ordersTransactionManager
    |
    +-- ordersEntityManagerFactory
             |
             +-- ordersDataSource

billingTransactionManager
    |
    +-- billingEntityManagerFactory
             |
             +-- billingDataSource
```

Ngay cả khi cả hai managers đang có transaction active trong cùng một call stack, việc chúng cùng được Spring quản lý không tạo ra một coordinator chung để đảm bảo cả hai cùng commit hay cùng rollback.

Spring `TransactionSynchronizationManager` có thể giữ tài nguyên gắn với thread để một manager nhận diện transaction của nó; đây là coordination **trong process**, không phải một giao thức distributed atomic commit giữa các database.

## 13. Nếu dùng JDBC bên cạnh JPA thì sao?

Một `JpaTransactionManager` có thể phối hợp các lời gọi JDBC truy cập **cùng DataSource/connection transaction** khi cấu hình phù hợp với Spring transaction integration.

Ví dụ JPA repository và `JdbcTemplate` dùng cùng Orders DataSource:

```text
Orders @Transactional
     |
     +-- JPA EntityManager (Orders EMF)
     |
     +-- JdbcTemplate (Orders DataSource)
     |
     +-- Same local resource, khi được cấu hình và tham gia đúng
```

Điều này **khác** với:

```text
Orders @Transactional
     |
     +-- Orders EntityManager -> Orders DS
     |
     +-- Billing JdbcTemplate -> Billing DS
```

Nhánh Billing ở DataSource khác không đương nhiên tham gia transaction Orders. Nếu dùng JDBC ngoài cơ chế Spring transaction-aware hoặc lấy connection thủ công sai cách, còn có thể vô tình tự commit ngay cả trên cùng database.

**Cùng DBMS instance không đủ; phải cùng transaction resource thực và cấu hình transaction integration đúng.**

## 14. Bảng tình huống commit và rollback

Giả sử logic viết A rồi viết B:

| Sự kiện | DB A | DB B | Điều cần xử lý |
|---|---|---|---|
| A và B đều commit | Đã ghi | Đã ghi | Thành công |
| A rollback trước khi B chạy | Chưa ghi | Chưa ghi | Có thể retry toàn workflow |
| B commit, A rollback | Chưa ghi | Đã ghi | Dữ liệu dư/không nhất quán |
| A commit, B lỗi | Đã ghi | Chưa ghi | Dữ liệu thiếu/không nhất quán |
| Mất mạng trong lúc commit | Không rõ với caller | Có thể đã ghi/chưa ghi | Cần trạng thái kiểm chứng và idempotency |
| Service chết giữa hai bước | Tùy bước đã commit | Tùy bước đã commit | Cần durable recovery |

Trường hợp “không biết commit đã thành công chưa” rất quan trọng. Một timeout không chứng minh database rollback; câu commit có thể đã thành công nhưng client không nhận được response. Retry mù có thể tạo bản ghi trùng nếu không có idempotency key và unique constraint.

## 15. Vì sao commit tuần tự vẫn không atomic?

Một cách thường bị hiểu nhầm là tự mở hai transactions rồi commit liên tiếp:

```java
TransactionStatus txA = ordersManager.getTransaction(definition);
TransactionStatus txB = billingManager.getTransaction(definition);

try {
    writeOrders();
    writeBilling();
    billingManager.commit(txB);
    ordersManager.commit(txA);
} catch (RuntimeException ex) {
    // Không thể rollback transaction đã commit.
    throw ex;
}
```

Đây là **đoạn mô tả anti-pattern**, không phải code nên dùng nguyên trạng: nó còn thiếu xử lý rollback đầy đủ, trạng thái đã hoàn tất và lifecycle. Mục đích là chỉ ra lỗ hổng: sau khi `commit(txB)` thành công, nếu `commit(txA)` thất bại thì không còn cách rollback B bằng local transaction manager.

Các tiện ích “chained transaction manager” từng xuất hiện trong một số thư viện chỉ lần lượt commit/rollback nhiều managers, **không cung cấp atomicity kiểu 2-phase commit**. Một số API loại này còn bị deprecated; không được quảng bá như giải pháp đảm bảo giao dịch phân tán.

## 16. Phân loại yêu cầu nhất quán trước khi chọn giải pháp

| Yêu cầu nghiệp vụ | Tính nhất quán cần | Giải pháp thường xem xét |
|---|---|---|
| Ghi dữ liệu trong cùng một DB | Atomicity local | Một DataSource + transaction manager |
| Ghi Orders, cập nhật reporting sau vài giây | Eventual consistency | Transactional outbox + consumer idempotent |
| Đồng bộ hai hệ thống có bước có thể bù trừ | Workflow consistency | Saga với state, retry và compensation |
| Hai DB bắt buộc cùng commit/rollback | Distributed atomicity | XA/JTA/2PC nếu toàn bộ resources hỗ trợ |
| Gọi API thanh toán bên ngoài cùng ghi DB | Không có một SQL transaction bao phủ API | Workflow với idempotency, state và compensation |
| Đọc replica sau khi vừa ghi primary | Read-your-writes consistency | Route read tới primary hoặc cơ chế xác nhận replication |

Không phải trường hợp nào cũng cần XA. Nếu DB B chỉ là read model/phân tích, sự khác biệt tạm thời có thể là một đặc tính chấp nhận được. Nếu DB B giữ dữ liệu tài chính không được phép sai lệch, cần thiết kế invariant và failure recovery nghiêm ngặt hơn.

## 17. Giải pháp 1: thiết kế lại để dùng một transaction cục bộ

Nếu hai bảng thực sự thuộc cùng một aggregate và phải thay đổi nguyên tử, hãy cân nhắc đặt chúng trong **cùng database/persistence unit** nếu ranh giới hệ thống cho phép.

```text
Một DataSource
      |
      v
Một JDBC transaction
      |
      +-- UPDATE orders
      +-- INSERT order_audit
      +-- INSERT outbox_events
      |
      v
COMMIT tất cả hoặc ROLLBACK tất cả
```

Đây thường là cách đơn giản nhất để bảo đảm atomicity cho invariant cục bộ. Ví dụ Order và OutboxEvent nên được lưu bằng cùng Orders transaction để không bao giờ có Order commit mà thiếu outbox event.

Hai schema trong cùng DBMS có thể được truy cập bằng một connection và một local transaction **nếu DBMS/cấu hình thực sự cho phép**. Nhưng nếu vẫn tạo hai DataSources và hai managers độc lập, không nên mặc định chúng dùng chung transaction chỉ vì cùng host.

Chi phí của việc gộp DB phải được cân nhắc với ownership, scaling, security và bounded contexts. Không nên gộp mọi hệ thống chỉ để tránh thiết kế integration.

## 18. Giải pháp 2: Transactional Outbox cho một nguồn dữ liệu chính

Giả sử Orders DB là source of truth, còn Reporting DB là bản sao tổng hợp. Ta cần:

1. Ghi Order.
2. Ghi một thông điệp về Order trong **cùng Orders transaction**.
3. Sau commit, relay đọc thông điệp và cập nhật Reporting DB.

```text
           Orders DB (A)
        +------------------+
        | BEGIN TX A       |
        | INSERT orders    |
        | INSERT outbox    |
        | COMMIT TX A      |
        +------------------+
                 |
                 v
          Outbox relay
      polling / CDC / broker
                 |
                 v
           Reporting DB (B)
        +------------------+
        | BEGIN TX B       |
        | update projection|
        | INSERT inbox     |
        | COMMIT TX B      |
        +------------------+
```

Điểm mạnh: không có khoảng trống giữa việc commit Order và ghi **ý định tích hợp** vào outbox. Nếu relay lỗi, event vẫn còn trong DB A để xử lý lại. B có thể tạm thời chậm nhưng có khả năng bắt kịp.

Điểm cần nói rõ: Outbox **không** khiến hai DB commit cùng thời điểm; nó tạo một cơ chế reliable eventual consistency, với điều kiện relay, retry và consumer được triển khai đúng.

## 19. Một mô hình Outbox đơn giản

Ví dụ các bảng ở Orders DB:

```sql
CREATE TABLE orders (
    id BIGINT PRIMARY KEY,
    external_request_id VARCHAR(100) NOT NULL UNIQUE,
    status VARCHAR(32) NOT NULL
);

CREATE TABLE outbox_events (
    event_id UUID PRIMARY KEY,
    aggregate_type VARCHAR(60) NOT NULL,
    aggregate_id BIGINT NOT NULL,
    event_type VARCHAR(80) NOT NULL,
    payload TEXT NOT NULL,
    created_at TIMESTAMP NOT NULL,
    published_at TIMESTAMP NULL
);
```

SQL này minh họa mô hình trên DBMS có kiểu `UUID` tương thích, ví dụ PostgreSQL. Với DBMS khác, kiểu UUID và cú pháp timestamp có thể cần thay đổi. Thực tế nên có indexes phù hợp cho các sự kiện chưa publish và một chiến lược ordering/claim để nhiều relay workers không xử lý tranh nhau.

Một service ghi cả Order và OutboxEvent bằng **cùng repository/EMF của Orders DB**:

```java
@Service
public class PlaceOrderService {
    private final OrderRepository orders;
    private final OutboxRepository outbox;

    public PlaceOrderService(
            OrderRepository orders,
            OutboxRepository outbox) {
        this.orders = orders;
        this.outbox = outbox;
    }

    @Transactional("ordersTransactionManager")
    public Long placeOrder(CreateOrderCommand command) {
        Order order = Order.from(command);
        orders.save(order);

        OutboxEvent event = OutboxEvent.orderCreated(
            UUID.randomUUID(), order.getId(), command);
        outbox.save(event);

        return order.getId();
    }
}
```

Ví dụ giả định identifier của Order có thể sử dụng ở thời điểm tạo event theo generator đã cấu hình; nếu cần, flush để ID được cấp, nhưng `flush()` không phải commit. Outbox entity và repository phải thuộc Orders persistence unit. Nếu `outboxRepository` vô tình trỏ tới Billing EMF thì **không còn transactional outbox đúng nghĩa**.

### 19.1. Điều kiện bảo đảm outbox

Outbox chỉ giải quyết dual-write gap ở phía nguồn nếu:

- Entity nghiệp vụ và outbox row dùng cùng local transaction.
- Outbox record là bền vững, không chỉ event trong RAM.
- Relay retry khi thất bại, không đánh dấu thành công trước khi đích/broker xác nhận theo policy.
- Consumer xử lý event idempotent.
- Có monitoring cho backlog, tuổi event và lỗi retry.

Không sử dụng `@TransactionalEventListener(AFTER_COMMIT)` làm phương án thay thế trực tiếp cho durable outbox. Callback sau commit có thể không chạy nếu process chết ngay sau commit; một event in-memory có thể bị mất.

## 20. Relay có thể gửi trùng: at-least-once và idempotency

Một tình huống relay:

```text
1. Relay đọc event E từ outbox.
2. Relay gửi E tới đích.
3. Reporting DB xử lý và COMMIT.
4. Relay crash trước khi đánh dấu E đã publish.
5. Relay restart và gửi lại E.
```

Nếu đích không idempotent, một OrderCreated có thể cộng doanh thu hai lần. Vì vậy:

- Mỗi event cần `eventId` ổn định và duy nhất.
- Destination có unique constraint trên event ID đã xử lý.
- Business operation và ghi inbox/dedup marker phải nằm trong **cùng destination transaction**.
- Các lần gửi lại trả kết quả “đã xử lý” mà không thực hiện lại side effect.

```text
Outbox relay: at-least-once delivery
                   |
                   v
Destination consumer:
  BEGIN TX B
  check/claim event_id under unique constraint
  apply business projection
  persist processed event marker
  COMMIT TX B
```

“At-least-once delivery + idempotent consumption” thường cho hiệu ứng nghiệp vụ như chỉ áp dụng một lần, **không** có nghĩa network gửi đúng một lần.

## 21. Inbox pattern và xử lý duplicate

Ví dụ trong Reporting DB:

```sql
CREATE TABLE processed_events (
    event_id UUID PRIMARY KEY,
    processed_at TIMESTAMP NOT NULL
);

CREATE TABLE order_projection (
    order_id BIGINT PRIMARY KEY,
    status VARCHAR(32) NOT NULL,
    source_version BIGINT NOT NULL
);
```

Consumer minh họa:

```java
@Service
public class OrderProjectionConsumer {
    private final ProcessedEventRepository inbox;
    private final OrderProjectionRepository projections;

    public OrderProjectionConsumer(
            ProcessedEventRepository inbox,
            OrderProjectionRepository projections) {
        this.inbox = inbox;
        this.projections = projections;
    }

    @Transactional("reportingTransactionManager")
    public void handle(OrderChangedEvent event) {
        if (inbox.existsById(event.eventId())) {
            return;
        }

        projections.apply(event);
        inbox.save(new ProcessedEvent(event.eventId()));
    }
}
```

Đây là mẫu dễ hiểu, **chưa đủ để xử lý race giữa hai consumers** nếu chỉ tin vào `existsById()`. Hai consumers có thể cùng kiểm tra không tồn tại; phải có unique constraint ở database và chiến lược nhận duplicate-key, rollback/retry hoặc atomic insert/claim. Cách claim có thể dùng `INSERT ... ON CONFLICT DO NOTHING` hay tương đương theo DBMS, nhưng khi đó là SQL vendor-specific.

Business projection và dedup marker phải commit trong cùng Reporting transaction. Nếu projection update thành công nhưng marker thất bại và transaction rollback, lần retry sẽ xử lý lại từ trạng thái trước; không rơi vào nửa chừng đã commit.

### 21.1. Ordering giữa các events

Với nhiều event trên cùng Order:

```text
OrderCreated (version=1)
OrderPaid    (version=2)
OrderShipped (version=3)
```

Nếu event 3 đến trước event 2, cập nhật projection mù có thể đưa trạng thái từ SHIPPED lùi về PAID. Cần:

- Sequence/aggregate version tăng đơn điệu.
- Partition/order routing theo aggregate ID khi dùng broker hỗ trợ.
- Consumer bỏ qua event cũ hoặc giữ event đến khi đủ predecessors.
- Reconciliation/snapshot khi event mất hoặc backlog không thể tự chữa.

Idempotency chặn duplicate; **ordering là vấn đề khác** và cần giải quyết riêng.

## 22. Outbox không đồng nghĩa khả năng đọc ngay dữ liệu ở DB B

Sau khi Orders transaction commit, Reporting DB có thể chưa nhận event:

```text
T0: Orders COMMIT
T1: API trả "Order accepted"
T2: Reporting vẫn chưa thấy Order
T3: Relay xử lý event
T4: Reporting COMMIT, projection xuất hiện
```

Nếu API yêu cầu đọc thấy Order ngay sau khi tạo, nên đọc từ Orders DB (source of truth) hoặc sử dụng cơ chế trả trạng thái pending/đọc lại có kiểm soát. Không bắt người dùng phụ thuộc vào một reporting projection eventually consistent mà không định nghĩa freshness.

Giao thức API có thể trả:

```json
{
  "orderId": 12345,
  "status": "ACCEPTED",
  "projectionStatus": "PENDING"
}
```

Đây là ví dụ response model, không phải lời hứa rằng Reporting đã cập nhật. Khi xây API, nên phân biệt “command đã được commit ở nguồn” với “mọi downstream views đã bắt kịp”.

## 23. Giải pháp 3: Saga cho nhiều bước nghiệp vụ

Outbox phù hợp để lan truyền thay đổi sang read model hoặc hệ thống nhận event. Với workflow nhiều bước tạo business effects ở nhiều bounded contexts, có thể cần **Saga**.

Ví dụ:

```text
1. Orders DB: tạo Order trạng thái PENDING
2. Inventory DB: reserve stock
3. Payment system: authorize payment
4. Orders DB: chuyển Order sang CONFIRMED
```

Nếu bước 3 thất bại:

```text
Payment authorization failed
           |
           v
Release inventory reservation
           |
           v
Mark Order CANCELLED
```

Đây là **compensation**, không phải database rollback xuyên nhiều hệ thống. Những bước đã commit không được “quay ngược thời gian”; hệ thống thực hiện thao tác nghiệp vụ mới để đạt trạng thái nhất quán theo policy.

### 23.1. Hai kiểu điều phối

| Kiểu | Mô tả | Rủi ro/điểm cần chú ý |
|---|---|---|
| Choreography | Các services phản ứng với events và tự kích hoạt bước tiếp | Dễ phân tán logic, khó quan sát toàn workflow |
| Orchestration | Một coordinator/state machine quyết định bước kế tiếp | Rõ tiến trình, nhưng cần triển khai orchestrator bền vững |

Saga cần state và correlation ID, timeout handling, retry, idempotency, compensation, dead-letter/manual intervention khi không thể tự phục hồi.

### 23.2. Compensation không luôn hoàn hảo

Nếu đã gửi email, giao hàng hoặc chuyển tiền, “hủy” không nhất thiết hoàn nguyên được side effect. Có thể chỉ thực hiện một hành động bù như hoàn tiền hoặc tạo bút toán điều chỉnh. Vì vậy, design Saga phải bắt đầu từ business semantics, không dùng từ “rollback” để mô tả mọi bù trừ.

## 24. Giải pháp 4: XA/JTA và two-phase commit

Khi nghiệp vụ **thực sự cần atomic commit across multiple transactional resources**, một lựa chọn là JTA transaction coordinator với XA-capable resources.

Two-phase commit (2PC) về ý tưởng:

```text
Application
     |
     v
JTA Transaction Coordinator
     |
     +-------------------------+
     |                         |
     v                         v
XA Resource A              XA Resource B
     |                         |
Phase 1: PREPARE           Phase 1: PREPARE
     |                         |
     +-----------+-------------+
                 |
          All prepared?
            /        \
           NO        YES
           |          |
           v          v
         ROLLBACK   Phase 2: COMMIT
                       both resources
```

Coordinator cần durable transaction log/recovery. Resource managers và drivers phải hỗ trợ XA đúng. JTA transaction manager của Spring chỉ là bridge tới coordinator; **đưa một `JtaTransactionManager` bean vào context không tự biến mọi `DataSource` thành XA resources**.

### 24.1. Cần gì để XA thực sự hoạt động?

- JTA-capable transaction coordinator, ví dụ một sản phẩm/implementation phù hợp.
- XADataSource/XAConnection hoặc resource adapter được cấu hình đúng.
- Cả hai DBMS/drivers hỗ trợ protocol và operational constraints.
- Recovery logs bền vững và khả năng xử lý in-doubt transactions.
- Configuration đúng cho connection pooling và enlistment.
- Integration tests về prepare, commit, crash và recovery.

XA có thể tăng latency, giữ locks lâu hơn, ảnh hưởng availability khi một resource không phản hồi, và phát sinh heuristic outcomes cần xử lý. Nó không biến HTTP call hoặc email thành resource XA nếu bên kia không hỗ trợ giao thức tương ứng.

### 24.2. Khi nào cân nhắc XA?

Chỉ khi invariant yêu cầu cả hai transactional resources cùng commit/rollback và kiến trúc, DBMS, vận hành chịu được chi phí. Nếu có thể đặt invariant trong một local DB transaction hoặc dùng outbox/eventual workflow, các phương án đó thường đơn giản hơn để vận hành.

## 25. Một số hiểu nhầm về XA/JTA

| Nhầm lẫn | Thực tế |
|---|---|
| Có `@Transactional` là đã có distributed transaction | Chỉ gắn transaction với manager được chọn |
| Hai `JpaTransactionManager` cùng chạy sẽ tự phối hợp | Không có atomic coordinator chung |
| Dùng `REQUIRES_NEW` cho DB B sẽ bảo vệ DB A | Nó tạo transaction khác, không chia sẻ commit |
| Một bean `JtaTransactionManager` đủ để XA | Resources phải XA-capable và enlisted, coordinator phải có recovery |
| 2PC không bao giờ xảy ra partial failure | Vẫn có lỗi chuẩn bị/commit, in-doubt/heuristic và recovery |
| Chained managers giống 2PC | Commit tuần tự không có prepare phase đảm bảo atomicity |
| Outbox là distributed transaction | Outbox cung cấp durable intent và eventual delivery, không simultaneous commit |
| Saga rollback tất cả như một SQL transaction | Saga dùng compensation và business state transitions |

## 26. Khi một DB chỉ dùng để đọc

Không phải service nào cần ghi vào cả hai DB. Ví dụ Orders DB có write workload, Analytics DB chỉ phục vụ báo cáo:

```java
@Service
public class OrderSummaryService {
    private final OrderRepository orders;
    private final ReportingRepository reporting;

    public OrderSummaryService(
            OrderRepository orders,
            ReportingRepository reporting) {
        this.orders = orders;
        this.reporting = reporting;
    }

    public OrderSummary getSummary(Long orderId) {
        OrderInfo order = orders.findSummary(orderId);
        ReportingInfo metrics = reporting.findMetrics(orderId);
        return new OrderSummary(order, metrics);
    }
}
```

Hai queries có thể thuộc hai local read transactions hoặc được gọi mà không có service-level write transaction, tùy repository/configuration. Nhưng kết quả không phải một **consistent snapshot cross-DB**: dữ liệu A có thể ở thời điểm T2, B vẫn ở T1.

Nếu UI cần một snapshot logic, có thể dùng:

- Projection có version/timestamp và hiển thị freshness.
- Cùng source of truth cho dữ liệu bắt buộc nhất quán.
- Chỉ báo trạng thái “đang đồng bộ”.
- Snapshot/reconciliation protocol theo nghiệp vụ.

Không dùng `@Transactional(readOnly = true)` trên một manager để khẳng định hai DB được đọc trong cùng một snapshot.

## 27. Primary và read replica: DataSource routing không xóa replication lag

Một kiến trúc thường gặp:

```text
                  Primary DB
                     |
           asynchronous replication
                     |
                     v
                  Read Replica

Write DataSource -> Primary
Read DataSource  -> Replica
```

Nếu ứng dụng ghi rồi ngay lập tức đọc replica:

```text
T0: UPDATE Primary COMMIT
T1: Replica chưa replay WAL/binlog
T2: SELECT Replica trả state cũ
T3: Replica bắt kịp
```

Đây là replication lag, không phải bug của `@Transactional`. Để bảo đảm read-your-writes, có thể:

- Route read sau write tới primary trong một khoảng/flow rõ ràng.
- Dùng database-specific replication position/LSN wait nếu cần.
- Trả snapshot ở response từ write result thay vì đọc lại replica ngay.
- Chấp nhận eventual consistency và hiển thị freshness policy.

`@Transactional(readOnly=true)` chỉ là transaction hint/semantics của framework, không tự định tuyến tới replica trong mọi cấu hình. Cần routing logic cụ thể và kiểm thử.

## 28. AbstractRoutingDataSource: hữu ích nhưng có giới hạn

Spring cung cấp `AbstractRoutingDataSource` để chọn target DataSource dựa trên một lookup key:

```java
public final class TenantRoutingDataSource
        extends AbstractRoutingDataSource {

    @Override
    protected Object determineCurrentLookupKey() {
        return TenantContext.currentTenantKey();
    }
}
```

Đây là đoạn khung minh họa; `TenantContext` và target mappings do ứng dụng xây dựng. Không lấy tenant ID từ request không đáng tin.

Điểm quan trọng: routing thường được quyết định **khi lấy JDBC connection**, và transaction manager có thể giữ/bind connection đó đến khi kết thúc transaction. Nếu đổi routing key giữa một transaction, không có bảo đảm connection sẽ tự chuyển sang DB khác:

```text
BEGIN transaction
   |
getConnection() -> route to DB A -> connection A bound
   |
change routing key to B
   |
reuse bound connection A (không nhất thiết route lại)
```

Do đó `AbstractRoutingDataSource` là công cụ chọn kết nối, **không phải** coordinator thực hiện distributed transaction. Cần đặc biệt cẩn thận với routing theo `readOnly` transaction flag vì thời điểm quyết định route và thời điểm transaction state được gắn vào thread có thể khác theo cấu hình.

## 29. Không tự map @ManyToOne giữa hai persistence units

Giả sử `Order` nằm ở Orders EMF, `Invoice` nằm ở Billing EMF:

```text
Orders persistence unit:
  Order(id, status, ...)

Billing persistence unit:
  Invoice(id, orderId, amount, ...)
```

Không nên khai báo quan hệ JPA xuyên hai EMFs như:

```java
// Anti-pattern: Invoice không thuộc cùng persistence unit.
@ManyToOne
private Invoice invoice;
```

nếu Invoice chỉ được quản lý ở factory khác. Hibernate mapping của Orders EMF không có metadata/transaction cho Invoice bên Billing; association mapping kiểu đó thường không hợp lệ hoặc không đúng kiến trúc.

Thay vào đó, lưu identifier/value:

```java
@Entity
public class Order {
    @Id
    private Long id;

    private Long billingRecordId;
}
```

Hoặc giữ một external reference rõ ràng ở Billing:

```java
@Entity
public class BillingRecord {
    @Id
    private Long id;

    @Column(nullable = false)
    private Long orderId;
}
```

Service/query layer có thể kết hợp DTO từ hai repositories. Referential integrity cross-DB không được database bảo đảm như FK trong một database, nên cần idempotency, validation và reconciliation phù hợp.

## 30. Không query JOIN hai DB qua JPA như một database

HQL/JPQL query dựa trên mapping của một `EntityManagerFactory`. Nếu `Customer` ở Customer DB và `Order` ở Orders DB, không thể giả định một JPQL:

```hql
select o, c
from Order o
join Customer c on c.id = o.customerId
```

sẽ thực hiện distributed join giữa hai independent persistence units. Hibernate không tự phát truy vấn qua hai JDBC connections rồi ghép kết quả thành một JPQL join.

Các phương án:

- Thực hiện hai queries và join DTO trong application với size limits.
- Tạo read model/materialized projection ở một database.
- Dùng data warehouse/reporting pipeline cho phân tích lớn.
- Sử dụng federated database feature nếu DBMS hỗ trợ và chấp nhận coupling/consistency/performance, nhưng đó không phải JPQL cross-EMF thông thường.

Không tải toàn bộ hai bảng vào memory chỉ để join; phải giới hạn kết quả/phân trang hoặc thay đổi mô hình dữ liệu.

## 31. Quản lý schema migration riêng cho từng DataSource

Mỗi database có schema lifecycle độc lập:

```text
Orders DataSource
  -> Orders Flyway/Liquibase migrations
  -> Orders EntityManagerFactory validates schema

Billing DataSource
  -> Billing Flyway/Liquibase migrations
  -> Billing EntityManagerFactory validates schema
```

Spring Boot auto-configuration mặc định của schema initializer/migration tool có thể chọn DataSource phù hợp theo điều kiện, không tự suy ra rằng cả hai databases đều đã được migrate. Khi cấu hình nhiều DataSources, cần định nghĩa migration strategy cho từng database và dependencies giữa migration beans với EMF beans.

Ví dụ hai thư mục:

```text
db/migration/orders/
    V001__create_orders.sql
    V002__create_outbox.sql

db/migration/billing/
    V001__create_billing_records.sql
    V002__create_processed_events.sql
```

Nếu dùng Flyway riêng, hãy tạo hai Flyway configurations được bind đến hai DataSources và bảo đảm chạy migration trước khi Hibernate `validate`. Cách cấu hình bean initialization/depends-on phụ thuộc Spring Boot/Flyway version; không mặc định một `spring.flyway.*` sẽ tự migrate mọi custom DataSource.

**Không dùng `ddl-auto=update` trên cả hai production databases để chữa các lỗi migration**, vì có thể làm schema drift và khiến hệ thống mất kiểm soát version.

## 32. Pool sizing và áp lực kết nối khi có nhiều DB

Nếu một application instance có:

```text
Orders Hikari pool: 12 connections
Billing Hikari pool: 8 connections
Reporting Hikari pool: 10 connections
```

thì tổng giới hạn lý thuyết là 30 concurrent connections từ instance tới các resources, phân bổ theo từng pool. Khi có 10 application instances, khả năng tổng connection pressure tăng đáng kể. Cần xét riêng max connections của từng DBMS và traffic distribution.

Một request vừa giữ Orders connection vừa chờ Billing connection có thể tăng thời gian transaction và lock contention. Để giảm rủi ro:

- Không gọi API/network chậm khi giữ DB transaction nếu có thể tránh.
- Giới hạn timeout, pool wait và connection acquisition phù hợp.
- Theo dõi active/idle/pending connection metrics theo pool name.
- Dùng outbox/async workflow cho integration không cần synchronous response.
- Chia bounded contexts và retry theo trạng thái thay vì giữ nhiều transactions lâu.

**Pool size lớn không tạo tính nguyên tử**; nó chỉ thay đổi khả năng chạy đồng thời và áp lực database.

## 33. Security và tenant isolation trên từng nguồn dữ liệu

Hai DataSources thường có credentials khác nhau và ranh giới quyền khác nhau:

| Resource | Quyền tối thiểu ví dụ |
|---|---|
| Orders DB application user | Đọc/ghi các bảng Orders cần thiết |
| Billing DB user | Đọc/ghi bảng Billing liên quan |
| Reporting DB user | Read-only nếu chỉ phục vụ báo cáo |

Không đưa cùng một superuser credential vào mọi pool để “đỡ cấu hình”. Việc tách quyền giúp giới hạn thiệt hại khi một repository hoặc query bị lỗi.

Với multi-tenancy:

- Tenant context phải đến từ authentication/session context đáng tin cậy.
- Đường query ở **mỗi DB** phải giới hạn dữ liệu theo tenant, hoặc sử dụng database isolation/RLS được cấu hình đúng.
- Khi event qua outbox/broker, tenant ID phải là dữ liệu được kiểm chứng, không nhận mù từ message không đáng tin.
- Connection/session context dùng cho RLS phải được reset đúng khi trả pool.
- Không ghi credentials hoặc PII nhạy cảm vào event payload/logs khi không cần thiết.

Một transaction manager đúng không tự giải quyết lỗi cross-tenant authorization.

## 34. Second-level cache cũng tách theo factory

Mỗi `EntityManagerFactory`/Hibernate `SessionFactory` có entity metadata và cache infrastructure riêng. Nếu Orders và Billing dùng hai factories:

```text
Orders EMF:
   PersistenceContext A
   Hibernate L2/query cache regions A

Billing EMF:
   PersistenceContext B
   Hibernate L2/query cache regions B
```

Không giả định cập nhật entity bên Orders DB sẽ tự invalidated cache của một Billing read model, hoặc một Spring `@Cacheable` method được làm mới khi một DB thay đổi.

Khi đồng bộ qua outbox:

- Consumer cập nhật Billing DB cần có consistency policy cho Billing cache.
- Một event replay phải idempotent cả về dữ liệu lẫn invalidation.
- Cache TTL không thay thế recovery khi đồng bộ lỗi.
- Nếu dữ liệu nhạy cảm, stale cache có thể gây sai quyền truy cập hoặc số tiền.

Khi dùng native SQL/JDBC ngoài Hibernate, cache synchronization cần được tính riêng.

## 35. Monitoring phải phản ánh từng DB và cả workflow

Không chỉ đo một API p95 chung. Nên quan sát:

| Metric | Vai trò |
|---|---|
| Connection pool active/idle/pending của từng DS | Phát hiện nghẽn pool |
| DB query latency, error rate theo resource | Phát hiện DB nào chậm |
| Transaction commit/rollback count theo manager | Phân biệt lỗi A/B |
| Deadlocks/lock wait theo database | Đánh giá contention |
| Outbox pending count và oldest pending age | Phát hiện relay backlog |
| Relay publish attempts/failures/retries | Phát hiện delivery issue |
| Inbox duplicates/skipped events | Đo replay/idempotency |
| Saga pending/failed/compensating states | Phát hiện workflow mắc kẹt |
| Projection lag theo aggregate/event version | Đo eventual-consistency delay |
| Reconciliation mismatches | Phát hiện dữ liệu trôi lệch |

Trace nên mang correlation ID, order ID và event ID để theo dõi một logical workflow qua các transactions. Tránh dùng raw payload hoặc user credentials làm log fields; metrics labels phải có cardinality có kiểm soát.

### 35.1. Đừng giả định một transaction span là một DB transaction

Distributed tracing có thể nối nhiều spans theo cùng trace ID, nhưng trace ID chỉ là quan hệ quan sát, không phải transaction coordinator. Một trace chứa “Orders commit” và “Billing commit” vẫn có thể có partial commit nếu một bước lỗi.

## 36. Failure handling: timeout không có nghĩa rollback

Khi gọi DB B:

```text
Client gửi INSERT/COMMIT
          |
          v
Database có thể đã commit
          |
     response bị mất
          |
          v
Client thấy timeout
```

Nếu retry tạo BillingRecord mới bằng ID tự sinh, có thể tạo duplicate. Do đó:

- Mỗi logical command nên có stable idempotency key.
- Có unique constraint ở destination.
- Retry phải kiểm tra outcome hoặc thực thi lệnh idempotent.
- Phân biệt “definitely failed” với “unknown outcome”.
- Không chạy compensation mù nếu không biết bước trước đã thành công.

Ví dụ cột:

```sql
CREATE TABLE billing_records (
    id BIGINT PRIMARY KEY,
    source_order_id BIGINT NOT NULL,
    request_key VARCHAR(120) NOT NULL UNIQUE,
    amount NUMERIC(19, 2) NOT NULL
);
```

Nếu command bị gửi lại với cùng request_key, destination phải có behavior chống trùng theo contract. Cơ chế upsert có thể giúp nhưng là SQL vendor-specific và cần bảo đảm giá trị retry không làm thay đổi dữ liệu trái ý muốn.

## 37. Reconciliation không phải chỉ là thao tác sửa lỗi thủ công

Trong hệ thống eventual consistency, retry và idempotency xử lý nhiều lỗi tạm thời nhưng không đảm bảo dữ liệu sẽ luôn tự đồng bộ trong mọi tình huống:

- Event không thể deserialize sau thay đổi schema.
- Consumer bị tắt quá lâu.
- Message poison liên tục làm failure.
- Bug cũ đã ghi projection sai.
- Retry bị dừng sau số lần tối đa.
- Một out-of-band writer không phát event.

Cần quy trình reconciliation:

1. Xác định source of truth.
2. Đối chiếu theo aggregate ID và source version/checksum.
3. Phát hiện missing/outdated destination rows.
4. Tái phát event hoặc rebuild projection có kiểm soát.
5. Ghi lại kết quả, tránh tạo tác dụng phụ trùng.
6. Cảnh báo khi chênh lệch vượt freshness/correctness SLO.

Một hệ thống có thể chạy bình thường hàng tháng nhưng vẫn cần reconciliation để xử lý lỗi hiếm mà retry không giải quyết.

## 38. Kiểm thử integration với hai DB thật

Một test chỉ dùng H2 mặc định hoặc chỉ có Orders DB không thể chứng minh boundary giữa hai transactions. Nên kiểm thử bằng đúng DBMS/version mà mỗi DataSource dùng, ví dụ hai PostgreSQL containers.

Khung Testcontainers:

```java
@Testcontainers
@SpringBootTest
class TwoDatabaseIntegrationTest {

    @Container
    static PostgreSQLContainer<?> orders =
        new PostgreSQLContainer<>("postgres:16-alpine")
            .withDatabaseName("orders_test");

    @Container
    static PostgreSQLContainer<?> billing =
        new PostgreSQLContainer<>("postgres:16-alpine")
            .withDatabaseName("billing_test");

    @DynamicPropertySource
    static void databaseProperties(DynamicPropertyRegistry registry) {
        registry.add("app.datasource.orders.url", orders::getJdbcUrl);
        registry.add("app.datasource.orders.username", orders::getUsername);
        registry.add("app.datasource.orders.password", orders::getPassword);

        registry.add("app.datasource.billing.url", billing::getJdbcUrl);
        registry.add("app.datasource.billing.username", billing::getUsername);
        registry.add("app.datasource.billing.password", billing::getPassword);
    }

    // Inject các services/repositories.
    // Test commit/rollback riêng từng DB và outbox recovery.
}
```

Ví dụ giả định ứng dụng có dependencies JUnit 5, Spring Boot Test, Testcontainers và Docker runtime; cần imports/test methods/fixtures thật để chạy. Mỗi container có schema migrations của riêng nó. Nếu production dùng hai DBMS khác nhau, test nên dùng đúng từng loại, không ép cả hai thành PostgreSQL vì tiện.

### 38.1. Không bọc test trong một @Transactional chung

Nếu test method có `@Transactional("ordersTransactionManager")` và Spring Test tự rollback cuối test, điều đó **không chứng minh** Billing transaction rollback. Nó có thể che vấn đề partial commit hoặc làm quan sát sai thời điểm.

Với integration test commit/rollback:

- Gọi service qua Spring proxy.
- Để service tạo và hoàn tất transactions thực.
- Đọc lại database bằng transactions/connections độc lập.
- Cleanup fixture rõ ràng giữa tests.

## 39. Ma trận fault-injection cần kiểm thử

| Kịch bản | Điều muốn chứng minh |
|---|---|
| Orders INSERT lỗi trước commit | Không phát durable outbox event |
| Outbox INSERT lỗi | Order và outbox cùng rollback ở Orders DB |
| Orders commit thành công, Billing DB down | Event còn, relay retry, không mất Order |
| Relay gửi thành công rồi crash trước mark | Có duplicate delivery nhưng consumer idempotent |
| Consumer lỗi giữa projection và inbox save | Cả hai cùng rollback trong Billing transaction |
| Hai consumers nhận cùng event | Unique constraint ngăn double effect |
| Event đến sai thứ tự | Projection không lùi version |
| DB B phục hồi sau downtime dài | Backlog được xử lý và reconciliation chính xác |
| Client timeout sau destination commit | Retry bằng request key không tạo duplicate |
| Orders/read replica lag | API read-your-writes theo contract |
| Transaction manager/EMF bị bind sai | Test phát hiện không ghi nhầm database |
| Một migration chỉ chạy trên DB A | Test phát hiện thiếu schema DB B |

Nếu yêu cầu XA thật, cần thêm test coordinator crash sau prepare, crash giữa commit phase và recovery. Nếu dùng Saga, cần test compensation failures và quá trình tiếp tục retry từ durable saga state.

## 40. Một bảng quyết định ngắn gọn

| Nhu cầu | Chọn ban đầu | Không được giả định |
|---|---|---|
| Hai thao tác cùng một database và cần atomic | Một DS/transaction manager | Hai pools cùng URL mặc nhiên cùng tx |
| Hai DB độc lập chỉ ghi riêng | Hai local TMs | Một `@Transactional` bao cả hai |
| Orders -> Reporting | Outbox + consumer idempotent | Reporting thấy ngay khi Orders commit |
| Cross-service workflow có bù trừ | Saga | Compensation giống rollback DB |
| Cần cả hai DB commit/rollback cùng nhau | XA/JTA nếu resources hỗ trợ | Chỉ đổi Spring annotation là đủ |
| Read từ replica | Routing + lag policy | `readOnly=true` tự bảo đảm fresh read |
| Nhiều tenant databases | Routing/EMF strategy + tenant isolation | Routing key đổi giữa tx sẽ đổi connection |
| Query join hai nguồn | Read model hoặc service aggregation | JPA join tự chạy trên hai EMFs |
| Đồng bộ sau lỗi lâu dài | Retry + inbox + reconciliation | Có outbox là luôn đồng bộ ngay |

## 41. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân thường gặp | Hướng xử lý |
|---|---|---|
| `NoUniqueBeanDefinitionException` | Hai DS/TM/EMF beans cùng type không có qualifier/default | Đặt bean names, `@Qualifier`/`@Primary`, chọn manager tường minh |
| `Not a managed type` | Repository dùng sai EMF hoặc sai entity packages | Kiểm tra `entityManagerFactoryRef` và `packages(...)` |
| Repository ghi nhầm DB | Scan/transaction manager ref sai | Phân package và binding rõ, integration test |
| Chỉ một DB rollback | Hai local transactions độc lập | Chọn outbox/saga/XA hoặc một DB |
| `@Transactional` không có hiệu lực | Self-invocation hoặc bean không qua Spring proxy | Thiết kế service boundary đúng |
| Dùng `REQUIRES_NEW` nhưng vẫn partial commit | REQUIRES_NEW không phải 2PC | Định nghĩa consistency architecture |
| Outbox event bị gửi hai lần | Relay crash trước mark | Consumer idempotent/inbox unique |
| Event out-of-order | Parallel consumers, broker order không đảm bảo | Aggregate version/partitioning |
| Reporting thiếu dữ liệu | Relay lỗi, backlog hoặc schema mismatch | Monitoring, retry, reconciliation |
| Thấy state cũ sau write | Replica lag hoặc cache stale | Route to primary hoặc freshness policy |
| Migration chỉ chạy một DB | Boot auto-init chọn một DataSource | Cấu hình migrations riêng |
| Routing key đổi nhưng query vẫn vào DB cũ | Connection đã bind trong tx | Chốt route trước acquisition, test |
| Pool timeout | Giữ nhiều connections, sizing không phù hợp | Giới hạn tx duration, metrics, tune |
| Cross-tenant leak | Thiếu tenant predicate/routing validation | Trusted context và DB permissions |
| Đọc bằng hai DB không đồng nhất | Không có distributed snapshot | Phiên bản/freshness/read model |
| Cấu hình JTA nhưng vẫn không atomic | DataSources không XA-enlisted hoặc recovery sai | Kiểm chứng XA coordinator/resources thực |

## 42. Quy trình thiết kế trước khi viết code

**Bước 1 — Vẽ ranh giới dữ liệu.** Những entity/bảng thuộc DB nào, bounded context nào sở hữu?

**Bước 2 — Liệt kê tính nhất quán cần có.** Bước nào bắt buộc atomic? Bước nào có thể eventual? Đọc lại sau ghi cần freshness nào?

**Bước 3 — Chọn transaction scope nhỏ nhất giữ đúng invariant.** Nếu có thể gom thay đổi quan trọng vào một local DB transaction, thường đơn giản nhất.

**Bước 4 — Xác định integration protocol.** Outbox cho durable change events, Saga cho workflow nhiều bước, XA/JTA nếu cần atomic distributed commit và hạ tầng hỗ trợ.

**Bước 5 — Cấu hình bean boundaries.** Mỗi DS/EMF/TM có tên rõ; repositories được gắn đúng factory và manager; không rely vào default mơ hồ.

**Bước 6 — Quy định idempotency và ordering.** Stable request/event IDs, unique constraints, aggregate versions, retry và compensation.

**Bước 7 — Xác định source of truth và khả năng phục hồi.** Reconciliation, dead-letter, replay, manual intervention, backlog monitoring.

**Bước 8 — Quản lý schema/migrations riêng.** Không để một initializer vô tình chỉ migrate default DS.

**Bước 9 — Kiểm thử failure thật.** Hai DB instances, forced rollback, timeout sau commit, duplicate deliveries, failover, restart.

**Bước 10 — Quan sát vận hành.** Per-resource pool/transaction metrics, tracing/correlation IDs, outbox age và consistency lag.

## 43. Sơ đồ lựa chọn transaction strategy

```text
          Cần ghi hoặc đọc nhiều DataSource?
                       |
                       v
           Các thay đổi có bắt buộc atomic?
                /                 \
              KHÔNG                CÓ
               |                   |
               v                   v
       Có thể eventual?     Có thể dùng chung
           /   \            một DB transaction?
         CÓ    KHÔNG            /     \
          |      |             CÓ      KHÔNG
          v      v              |         |
      Outbox/  Xác định         v         v
      Saga/    freshness    Một DataSource  Các resources
      read     hoặc workflow transaction   hỗ trợ XA/2PC?
      model       |                         /     \
                  |                       CÓ      KHÔNG
                  |                        |         |
                  |                        v         v
                  |                   JTA/XA với   Đổi kiến trúc/
                  |                   recovery     thiết kế business
                  |                                compensation
                  +-------------+----------------------+
                                |
                                v
                     Idempotency, retry, tests
                                |
                                v
                     Monitoring + reconciliation
```

## 44. Tổng kết

Trong Spring Boot tích hợp Hibernate/JPA, **nhiều DataSource không mặc nhiên cùng một transaction**. Mỗi DataSource có thể đi với một `EntityManagerFactory` và `JpaTransactionManager` riêng. `@Transactional` chỉ điều khiển tài nguyên của transaction manager được chọn, không tự phối hợp nguyên tử giữa hai database. `@Primary`, `@Qualifier` và `@EnableJpaRepositories` giúp chọn đúng bean, nhưng không giải quyết bài toán dual write.

Khi dữ liệu của hai DB cần đồng bộ, hãy xác định rõ consistency contract. Nếu cùng một invariant cần atomicity, ưu tiên một local transaction khi kiến trúc cho phép, hoặc cân nhắc XA/JTA/2PC nếu thật sự cần distributed atomic commit và toàn bộ resources hỗ trợ. Nếu có thể chấp nhận eventual consistency, transactional outbox, idempotent inbox, retry và reconciliation là các công cụ quan trọng. Với quy trình nhiều bước, Saga cung cấp compensation và durable workflow state, **không phải** rollback xuyên các hệ thống.

Phối hợp nhiều nguồn dữ liệu còn liên quan tới read replica lag, routing key, schema migrations, cache, tenant isolation, pool sizing và observability. Kiểm thử phải dùng các database/transactions thực sự độc lập và chủ động gây lỗi tại các thời điểm commit, gửi event, consumer và recovery.

**Nguyên tắc cuối cùng:** hãy ghi rõ tài nguyên nào sở hữu transaction nào, trạng thái nào có thể tạm thời bất đồng bộ, và hệ thống phục hồi ra sao nếu chỉ một bước thành công. Đó mới là cách dùng nhiều DataSource an toàn, thay vì kỳ vọng một annotation tạo ra giao dịch chung.
