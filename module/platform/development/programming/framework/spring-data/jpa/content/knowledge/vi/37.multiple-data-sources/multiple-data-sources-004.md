# Chọn giao dịch theo tên TransactionManager

Khi một ứng dụng Spring Data JPA kết nối nhiều database, mỗi nhóm entity/repository có thể thuộc một persistence unit và một transaction manager riêng. Spring cần biết transaction manager nào sẽ điều khiển một phương thức service, nếu không ứng dụng có thể dùng nhầm transaction manager mặc định hoặc báo lỗi khi có nhiều bean cùng kiểu.

Có hai vị trí cần cấu hình rõ ràng:

- **@Transactional(transactionManager = "...")** chọn transaction manager cho ranh giới giao dịch của một phương thức hoặc lớp service.
- **@EnableJpaRepositories(transactionManagerRef = "...", entityManagerFactoryRef = "...")** gắn một nhóm repository với đúng transaction manager và EntityManagerFactory.

Hai cấu hình này phải trỏ tới cùng một persistence unit khi service thao tác trên repository tương ứng.

## 1. TransactionManager là gì?

Trong Spring, **TransactionManager** là abstraction quản lý ranh giới transaction. Với ứng dụng JPA theo mô hình imperative, kiểu thường dùng là **PlatformTransactionManager**. Lớp **JpaTransactionManager** triển khai abstraction này cho một **EntityManagerFactory**.

Một persistence unit JPA thường có chuỗi thành phần:

~~~text
DataSource
    |
    v
EntityManagerFactory
    |
    v
JpaTransactionManager
    |
    v
Nhóm repository và service sử dụng persistence unit đó
~~~

Nếu ứng dụng có database đơn, Spring Boot thường cấu hình sẵn một DataSource, EntityManagerFactory và transaction manager mặc định. Với nhiều database, ứng dụng thường cần cấu hình riêng từng bộ thành phần:

| Persistence unit | DataSource | EntityManagerFactory | TransactionManager |
|---|---|---|---|
| Orders | ordersDataSource | ordersEntityManagerFactory | ordersTransactionManager |
| Billing | billingDataSource | billingEntityManagerFactory | billingTransactionManager |
| Audit | auditDataSource | auditEntityManagerFactory | auditTransactionManager |

Một **JpaTransactionManager** quản lý transaction của một EntityManagerFactory. Nó không tự động điều phối transaction trên mọi EntityManagerFactory trong application context.

Không tạo thêm EntityManagerFactory chỉ để đổi tên transaction. Mỗi persistence unit nên tương ứng với phạm vi entity, datasource và cấu hình JPA thực sự cần được quản lý riêng.

## 2. Chọn transaction manager bằng @Transactional

Spring cung cấp hai thuộc tính tương đương trên annotation **@Transactional**:

- **value**: qualifier hoặc tên bean của transaction manager.
- **transactionManager**: alias của value, thường dễ đọc hơn khi cấu hình tường minh.

Ví dụ:

~~~java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderService {

    @Transactional(transactionManager = "ordersTransactionManager")
    public void createOrder() {
        // Các thao tác thuộc transaction của database Orders
    }
}
~~~

Có thể viết dạng rút gọn:

~~~java
@Transactional("ordersTransactionManager")
public void createOrder() {
    // ...
}
~~~

Spring tìm transaction manager theo tên bean hoặc qualifier tương ứng. Tên truyền vào phải khớp với bean đã đăng ký trong application context.

Ví dụ với hai nghiệp vụ khác nhau:

~~~java
@Service
public class OrderService {

    @Transactional("ordersTransactionManager")
    public void createOrder() {
        // Đọc và ghi entity của Orders database
    }
}

@Service
public class BillingService {

    @Transactional("billingTransactionManager")
    public void recordInvoice() {
        // Đọc và ghi entity của Billing database
    }
}
~~~

Khi gọi qua Spring proxy, mỗi phương thức dùng transaction manager đã chỉ định. Phương thức không khai báo qualifier sẽ dùng transaction manager mặc định mà hạ tầng Spring đã chọn.

### 2.1. Tên bean và qualifier

Ví dụ khai báo bean:

~~~java
@Bean(name = "ordersTransactionManager")
PlatformTransactionManager ordersTransactionManager(
        @Qualifier("ordersEntityManagerFactory")
        EntityManagerFactory entityManagerFactory) {

    return new JpaTransactionManager(entityManagerFactory);
}
~~~

Tên bean ở đây là **ordersTransactionManager**. Annotation service có thể tham chiếu trực tiếp tên này.

Nếu dùng qualifier thay cho bean name, giá trị qualifier cũng có thể được dùng để phân giải transaction manager. Khi hệ thống có nhiều manager, đặt tên nhất quán giúp code dễ đọc và tránh chọn nhầm database.

### 2.2. Bật transaction annotation

Trong ứng dụng Spring Framework tự cấu hình, cần bật annotation-driven transaction management bằng **@EnableTransactionManagement** trên một configuration class:

~~~java
@Configuration
@EnableTransactionManagement
public class TransactionConfiguration {
}
~~~

Spring Boot thường tự cấu hình transaction management khi có hạ tầng phù hợp, nên ứng dụng Boot thông thường không cần thêm annotation này lần nữa. Nếu dùng Spring Framework thuần, hãy bật nó trong application context chứa các service cần được proxy.

## 3. Liên kết repository với đúng EntityManagerFactory và TransactionManager

Chỉ chọn transaction manager trên service là chưa đủ. Spring Data JPA còn phải biết repository interface thuộc persistence unit nào.

Dùng **@EnableJpaRepositories** với ba thuộc tính quan trọng:

- **basePackages**: package chứa repository interfaces cần đăng ký.
- **entityManagerFactoryRef**: tên EntityManagerFactory được dùng để tạo repository.
- **transactionManagerRef**: tên transaction manager mặc định cho repository đó.

Ví dụ cấu hình cho Orders:

~~~java
import javax.sql.DataSource;
import jakarta.persistence.EntityManagerFactory;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.jpa.repository.config.EnableJpaRepositories;
import org.springframework.orm.jpa.JpaTransactionManager;
import org.springframework.orm.jpa.LocalContainerEntityManagerFactoryBean;
import org.springframework.transaction.PlatformTransactionManager;

// Import EntityManagerFactoryBuilder từ package tương ứng với
// Spring Boot major version của dự án.
@Configuration
@EnableJpaRepositories(
    basePackages = "com.example.orders.repository",
    entityManagerFactoryRef = "ordersEntityManagerFactory",
    transactionManagerRef = "ordersTransactionManager"
)
public class OrdersJpaConfiguration {

    @Bean(name = "ordersEntityManagerFactory")
    LocalContainerEntityManagerFactoryBean ordersEntityManagerFactory(
            EntityManagerFactoryBuilder builder,
            @Qualifier("ordersDataSource") DataSource dataSource) {

        return builder
            .dataSource(dataSource)
            .packages("com.example.orders.entity")
            .persistenceUnit("orders")
            .build();
    }

    @Bean(name = "ordersTransactionManager")
    PlatformTransactionManager ordersTransactionManager(
            @Qualifier("ordersEntityManagerFactory")
            EntityManagerFactory entityManagerFactory) {

        return new JpaTransactionManager(entityManagerFactory);
    }
}
~~~

Cấu hình cho Billing dùng package, datasource, persistence unit và tên bean riêng:

~~~java
@Configuration
@EnableJpaRepositories(
    basePackages = "com.example.billing.repository",
    entityManagerFactoryRef = "billingEntityManagerFactory",
    transactionManagerRef = "billingTransactionManager"
)
public class BillingJpaConfiguration {

    @Bean(name = "billingEntityManagerFactory")
    LocalContainerEntityManagerFactoryBean billingEntityManagerFactory(
            EntityManagerFactoryBuilder builder,
            @Qualifier("billingDataSource") DataSource dataSource) {

        return builder
            .dataSource(dataSource)
            .packages("com.example.billing.entity")
            .persistenceUnit("billing")
            .build();
    }

    @Bean(name = "billingTransactionManager")
    PlatformTransactionManager billingTransactionManager(
            @Qualifier("billingEntityManagerFactory")
            EntityManagerFactory entityManagerFactory) {

        return new JpaTransactionManager(entityManagerFactory);
    }
}
~~~

Các bean **ordersDataSource** và **billingDataSource** phải được khai báo và cấu hình riêng. Mỗi DataSource trỏ tới database/schema mong muốn. Ví dụ trên tập trung vào liên kết JPA; nó giả định ứng dụng đã cung cấp hai DataSource và Spring Boot có EntityManagerFactoryBuilder.

Trong Spring Boot 3, EntityManagerFactoryBuilder thường nằm trong package **org.springframework.boot.orm.jpa**. Ở các major version mới hơn, hãy kiểm tra package của API trong phiên bản đang dùng. Dùng builder do Boot cung cấp giúp giữ các tùy chỉnh JPA/vendor mà Boot đã cấu hình. Nếu tự tạo EntityManagerFactory hoàn toàn, phải tự cung cấp các thuộc tính provider, dialect, naming strategy, packages và các cấu hình cần thiết.

### 3.1. Vì sao phải cấu hình cả hai ref?

Hai thuộc tính giải quyết hai nhiệm vụ khác nhau:

| Thuộc tính | Câu hỏi được trả lời |
|---|---|
| entityManagerFactoryRef | Repository sử dụng persistence context và entity mapping nào? |
| transactionManagerRef | Repository dùng transaction manager nào khi tự mở transaction? |

Nếu bỏ **entityManagerFactoryRef**, Spring Data JPA thường tìm bean tên **entityManagerFactory**. Nếu bỏ **transactionManagerRef**, repository infrastructure thường dùng manager mặc định có tên **transactionManager** hoặc manager đơn phù hợp trong application context.

Các mặc định này thuận tiện với ứng dụng một database. Trong cấu hình nhiều persistence unit, nên khai báo rõ cả hai ref để tránh repository vô tình gắn với bộ thành phần mặc định.

### 3.2. Tách package repository và entity

Một cấu trúc package dễ quản lý:

~~~text
com.example
  orders
    entity
    repository
    service
  billing
    entity
    repository
    service
  config
    OrdersJpaConfiguration
    BillingJpaConfiguration
~~~

Mỗi **@EnableJpaRepositories** nên quét đúng package repository của nó. Không để hai cấu hình cùng quét một repository interface, vì repository có thể bị đăng ký trùng hoặc gắn nhầm EntityManagerFactory.

Tương tự, mỗi EntityManagerFactory nên scan đúng các entity thuộc persistence unit tương ứng. Không đưa entity của database Orders vào persistence unit Billing chỉ vì hai nhóm entity cùng nằm trong package cha rộng.

## 4. Dùng đúng manager ở service boundary

Sau khi repository được liên kết, service cũng cần chọn cùng transaction manager:

~~~java
@Service
public class OrderApplicationService {

    private final OrderRepository orders;

    public OrderApplicationService(OrderRepository orders) {
        this.orders = orders;
    }

    @Transactional(transactionManager = "ordersTransactionManager")
    public Long placeOrder(Order order) {
        Order saved = orders.save(order);
        return saved.getId();
    }
}
~~~

Ở đây:

1. Spring proxy nhận lời gọi placeOrder.
2. Transaction interceptor chọn ordersTransactionManager.
3. JpaTransactionManager mở hoặc tham gia transaction của ordersEntityManagerFactory.
4. OrderRepository sử dụng EntityManagerFactory đã gắn trong OrdersJpaConfiguration.
5. Khi phương thức kết thúc, transaction manager commit nếu không có lỗi rollback.

Nếu service dùng **billingTransactionManager** nhưng repository được cấu hình với **ordersTransactionManager**, hai thành phần đang nói về hai transaction context khác nhau. Repository có thể tự mở transaction riêng theo manager của nó; transaction của service không tự động bao phủ thao tác đó.

Do đó, hãy giữ ba tên nhất quán: repository package, EntityManagerFactory và transaction manager.

## 5. Transaction mặc định khi có nhiều manager

Khi không chỉ định manager trên **@Transactional**, Spring cần chọn manager mặc định.

Trong cấu hình đơn giản, bean có tên **transactionManager** thường là tên mặc định được tìm. Có thể cấu hình rõ default manager bằng **TransactionManagementConfigurer** nếu ứng dụng có nhiều manager và muốn xác định một manager cho annotation không có qualifier.

**@Primary** hữu ích khi Spring cần chọn một bean ưu tiên trong các điểm inject theo type. Tuy nhiên, @Primary không thay thế việc gắn repository package với đúng EntityManagerFactory và transaction manager bằng các thuộc tính ref.

Ví dụ một điểm inject cần manager cụ thể:

~~~java
@Service
public class OrderMaintenanceService {

    private final PlatformTransactionManager transactionManager;

    public OrderMaintenanceService(
            @Qualifier("ordersTransactionManager")
            PlatformTransactionManager transactionManager) {
        this.transactionManager = transactionManager;
    }
}
~~~

Đừng nhầm **@Qualifier** trong constructor injection với **transactionManager** trong @Transactional:

- @Qualifier chọn bean được inject vào một field/constructor parameter.
- @Transactional(transactionManager = "...") chọn manager điều khiển transaction của phương thức.

Chúng có thể dùng cùng một tên, nhưng áp dụng ở hai cơ chế khác nhau.

## 6. Propagation khi có nhiều transaction manager

Mặc định, **@Transactional** dùng **Propagation.REQUIRED**. Nếu đã có transaction tương ứng với manager được chọn, phương thức tham gia transaction đó; nếu chưa có, manager sẽ mở transaction mới.

Khi hai phương thức dùng hai transaction manager khác nhau, chúng không tự động chia sẻ một transaction chỉ vì được gọi trong cùng call stack.

Ví dụ:

~~~java
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
    public void checkout(Order order) {
        orders.save(order);
        billing.createInvoice(order);
    }
}

@Service
public class BillingService {

    private final InvoiceRepository invoices;

    public BillingService(InvoiceRepository invoices) {
        this.invoices = invoices;
    }

    @Transactional("billingTransactionManager")
    public void createInvoice(Order order) {
        invoices.save(Invoice.from(order));
    }
}
~~~

Trong luồng này:

1. checkout mở transaction Orders.
2. createInvoice được gọi qua proxy BillingService.
3. BillingService chọn Billing transaction manager và mở transaction Billing riêng nếu chưa có transaction tương ứng.
4. Billing transaction có thể commit khi createInvoice kết thúc.
5. Sau đó, transaction Orders mới tiếp tục và commit khi checkout hoàn tất.

Nếu bước sau đó làm transaction Orders rollback, invoice đã commit ở Billing không tự động rollback theo. Đây là hai transaction độc lập.

### 6.1. REQUIRED và REQUIRES_NEW không tạo transaction phân tán

**REQUIRED** chỉ tham gia transaction mà manager tương ứng quản lý. Khi manager khác được chọn, nó không tự biến hai local transaction thành một transaction nguyên tử.

**REQUIRES_NEW** yêu cầu manager được chọn mở transaction mới và tạm ngưng transaction hiện có do cùng manager quản lý. Nó không biến hai database thành một đơn vị commit/rollback chung.

Nếu cần đảm bảo hai database cùng commit hoặc cùng rollback, phải có cơ chế điều phối phù hợp:

- **JTA/XA** có thể điều phối transaction phân tán khi các resource, driver và transaction manager hỗ trợ XA. Cần cấu hình và vận hành transaction coordinator phù hợp.
- **Saga** chia nghiệp vụ thành các bước local transaction, có hành động bù khi một bước sau thất bại.
- **Transactional outbox** ghi sự kiện vào cùng database/transaction với dữ liệu nghiệp vụ, sau đó một tiến trình phát sự kiện để hệ thống khác xử lý.

Không giả định hai annotation @Transactional trên hai manager sẽ cung cấp atomic commit xuyên database.

## 7. Dùng TransactionTemplate khi cần chọn manager bằng code

Ngoài annotation, Spring cho phép tạo **TransactionTemplate** với manager được inject tường minh. Cách này hữu ích khi ranh giới transaction phụ thuộc nhánh xử lý hoặc cần viết code điều phối rõ ràng.

~~~java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.stereotype.Service;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.support.TransactionTemplate;

@Service
public class OrderImportService {

    private final TransactionTemplate ordersTransaction;

    public OrderImportService(
            @Qualifier("ordersTransactionManager")
            PlatformTransactionManager transactionManager) {
        this.ordersTransaction = new TransactionTemplate(transactionManager);
    }

    public void importOrder(Order order) {
        ordersTransaction.executeWithoutResult(status -> {
            // Thao tác với Orders database trong transaction này
        });
    }
}
~~~

Có thể tạo một TransactionTemplate khác từ **billingTransactionManager** nếu cần chạy transaction Billing riêng. Cần nhớ rằng mỗi template chỉ điều khiển transaction của manager được truyền vào.

Đối với nghiệp vụ thông thường, **@Transactional** ở service boundary thường dễ đọc và dễ kiểm tra hơn. Dùng TransactionTemplate khi cần điều khiển transaction bằng code hoặc có nhiều đoạn transaction tuần tự trong cùng một phương thức.

## 8. Kiểm thử chọn đúng transaction manager

Test nhiều database cần xác nhận repository và service thực sự dùng đúng manager.

### 8.1. Test theo persistence unit

Có thể đánh dấu test:

~~~java
@SpringBootTest
@Transactional("ordersTransactionManager")
class OrderRepositoryIntegrationTest {

    @Autowired
    private OrderRepository orders;

    @Test
    void savesOrderInOrdersDatabase() {
        // Lưu và đọc lại Order trong Orders persistence unit
    }
}
~~~

Khi test kết thúc, transaction Orders được rollback theo test transaction nếu test không yêu cầu commit. Test này không tự rollback transaction của Billing manager.

### 8.2. Dùng TransactionTemplate để kiểm tra rollback riêng

Một test có thể gọi TransactionTemplate với manager cụ thể và ném exception để xác nhận dữ liệu trong database đó được rollback:

~~~java
TransactionTemplate tx = new TransactionTemplate(ordersTransactionManager);

assertThrows(RuntimeException.class, () ->
    tx.executeWithoutResult(status -> {
        orders.save(order);
        throw new RuntimeException("force rollback");
    })
);
~~~

Sau đó đọc lại bằng một transaction mới để xác nhận bản ghi không được commit. Tránh đọc lại bằng persistence context cũ vì cache cấp một có thể giữ trạng thái entity trong bộ nhớ.

### 8.3. Kiểm thử nhiều database

Nên có test riêng cho từng persistence unit:

- Kiểm tra repository Orders ghi vào Orders database.
- Kiểm tra repository Billing ghi vào Billing database.
- Kiểm tra mỗi service chọn đúng manager.
- Kiểm tra rollback của manager này không bị nhầm là rollback của manager khác.
- Kiểm tra migration/schema và entity scan riêng cho từng database.
- Kiểm tra trường hợp một nghiệp vụ gọi hai manager và xác nhận rõ hành vi khi một bước thất bại.

Có thể dùng Testcontainers để chạy database tương ứng production. Dữ liệu kiểm thử nên có business key riêng và cleanup phù hợp cho từng database.

## 9. Lỗi thường gặp

| Triệu chứng | Nguyên nhân | Cách xử lý |
|---|---|---|
| No qualifying bean of type PlatformTransactionManager | Có nhiều manager hoặc không có manager mặc định phù hợp | Chỉ định tên bằng @Transactional hoặc cấu hình default manager |
| Không tìm thấy transaction manager theo tên | Tên trong annotation không khớp bean name/qualifier | Kiểm tra tên bean và qualifier |
| Repository dùng nhầm database | Thiếu hoặc sai entityManagerFactoryRef | Gắn repository package với đúng EntityManagerFactory |
| Repository tự mở transaction khác service | transactionManagerRef khác manager mà service chọn | Đồng bộ hai ref và qualifier |
| Entity không được tìm thấy | EntityManagerFactory scan sai package | Sửa packages(...) hoặc packagesToScan |
| Repository bị đăng ký trùng | Hai @EnableJpaRepositories quét chồng package | Tách basePackages rõ ràng |
| Rollback một database nhưng database kia vẫn có dữ liệu | Hai local transaction độc lập | Dùng JTA/XA hoặc thiết kế outbox/saga |
| @Transactional không có hiệu lực | Gọi self-invocation hoặc gọi object không qua proxy | Đặt ranh giới ở Spring bean và gọi qua proxy |
| @Primary không giải quyết được repository mapping | @Primary chỉ hỗ trợ chọn bean ưu tiên theo type | Cấu hình entityManagerFactoryRef và transactionManagerRef |
| Test rollback không xóa dữ liệu database còn lại | Test chỉ chạy transaction của một manager | Xác định rõ manager cho từng test và cleanup |
| Spring Boot mất cấu hình JPA sau khi tự tạo EMF | Custom EMF không giữ các thuộc tính auto-configured | Dùng EntityManagerFactoryBuilder và bind JPA properties phù hợp |

## 10. Checklist cấu hình nhiều TransactionManager

- [ ] Mỗi persistence unit có DataSource phù hợp.
- [ ] Mỗi nhóm entity có EntityManagerFactory đúng.
- [ ] Mỗi EntityManagerFactory có JpaTransactionManager tương ứng.
- [ ] Tên bean transaction manager được đặt rõ ràng và nhất quán.
- [ ] Mỗi nhóm repository có basePackages riêng.
- [ ] entityManagerFactoryRef trỏ đúng EntityManagerFactory.
- [ ] transactionManagerRef trỏ đúng transaction manager.
- [ ] Service dùng @Transactional với đúng tên manager.
- [ ] Default transaction manager được xác định rõ cho annotation không có qualifier.
- [ ] @Qualifier trong dependency injection không bị nhầm với thuộc tính @Transactional.
- [ ] Đã hiểu transaction độc lập khi một phương thức gọi nhiều manager.
- [ ] Nếu cần atomic commit xuyên database, đã chọn JTA/XA hoặc thiết kế saga/outbox phù hợp.
- [ ] Integration test xác nhận đúng database, transaction và rollback behavior.

## 11. Ghi nhớ

Dùng **@Transactional(transactionManager = "ordersTransactionManager")** để chọn transaction manager cho service method. Dùng **@EnableJpaRepositories(entityManagerFactoryRef = "...", transactionManagerRef = "...")** để gắn nhóm repository với đúng persistence unit.

Một transaction manager JPA thường quản lý một EntityManagerFactory. Khi một nghiệp vụ sử dụng nhiều manager, các local transaction là độc lập và không tự động rollback/commit nguyên tử cùng nhau. Hãy đặt transaction boundary rõ ràng, đặt tên bean nhất quán và kiểm thử rollback trên từng database.

## Tài liệu tham khảo

- [Spring Framework — Using @Transactional and multiple transaction managers](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html)
- [Spring Data JPA — Repository configuration and transaction-manager-ref](https://docs.spring.io/spring-data/jpa/reference/repositories/create-instances.html)
- [Spring Data JPA — EnableJpaRepositories API](https://docs.spring.io/spring-data/jpa/reference/api/java/org/springframework/data/jpa/repository/config/EnableJpaRepositories.html)
- [Spring Boot — Using multiple EntityManagerFactories](https://docs.spring.io/spring-boot/how-to/data-access.html)

