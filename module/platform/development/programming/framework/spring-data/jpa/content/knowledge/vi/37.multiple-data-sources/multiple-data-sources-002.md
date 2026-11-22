# Tách EntityManagerFactory, persistence unit và TransactionManager trong Spring Data JPA

Khi một ứng dụng cần làm việc với nhiều nguồn dữ liệu, chỉ khai báo thêm một `DataSource` là chưa đủ. Mỗi nhóm repository cần được gắn với đúng `EntityManagerFactory`, persistence unit và `PlatformTransactionManager`. Nếu cấu hình nhầm, repository có thể truy cập sai database, entity không được quản lý bởi persistence unit mong muốn hoặc transaction không bao phủ đúng thao tác.

Bài viết dùng Java 17+, Spring Boot 3.x, Spring Data JPA, Hibernate 6 và PostgreSQL trong ví dụ. Ta giả sử ứng dụng có hai database độc lập: `orders` lưu đơn hàng và `billing` lưu hóa đơn.

## 1. Phân biệt bốn thành phần

| Thành phần | Trách nhiệm | Ví dụ |
|---|---|---|
| `DataSource` | Cung cấp kết nối JDBC tới một nguồn dữ liệu | URL, username, password, connection pool của database orders |
| Persistence unit | Nhóm cấu hình JPA gồm entity, mapping, provider và tên logic | `orders` chứa các entity đơn hàng |
| `EntityManagerFactory` | Tạo `EntityManager` cho một persistence unit | `ordersEntityManagerFactory` |
| `PlatformTransactionManager` | Quản lý transaction cho một tài nguyên hoặc persistence unit | `ordersTransactionManager` |

Một persistence unit thường được triển khai bởi một `EntityManagerFactory`. EntityManager do factory tạo ra quản lý persistence context của nó. Hai factory riêng có thể dùng hai DataSource khác nhau, hoặc thậm chí cùng một database nhưng có entity scan và cấu hình riêng.

`@EnableJpaRepositories` liên kết package repository với các bean JPA tương ứng qua hai thuộc tính:

- `entityManagerFactoryRef`: bean factory mà repository sẽ dùng.
- `transactionManagerRef`: transaction manager mà repository dùng cho transaction của nó.

Tên bean và tên persistence unit là hai khái niệm khác nhau. `entityManagerFactoryRef` trỏ tới tên bean Spring; `@PersistenceContext(unitName = "...")` trỏ tới tên persistence unit được khai báo khi xây dựng factory.

## 2. Tổ chức package để tách repository và entity

Một cấu trúc dễ quản lý:

```text
com.example
├── orders
│   ├── domain
│   │   └── Order.java
│   ├── repository
│   │   └── OrderRepository.java
│   └── config
│       └── OrdersJpaConfig.java
├── billing
│   ├── domain
│   │   └── Invoice.java
│   ├── repository
│   │   └── InvoiceRepository.java
│   └── config
│       └── BillingJpaConfig.java
└── service
    ├── OrderService.java
    └── BillingService.java
```

Tách package giúp mỗi cấu hình chỉ quét repository và entity thuộc nguồn dữ liệu của nó. Tránh để hai cấu hình `@EnableJpaRepositories` cùng quét một package repository, vì một repository có thể bị đăng ký vào factory không mong muốn.

Entity ví dụ:

**Order.java**

```java
package com.example.orders.domain;

import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "orders")
public class Order {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    private String orderNumber;

    protected Order() {
    }

    public Order(String orderNumber) {
        this.orderNumber = orderNumber;
    }

    public Long getId() {
        return id;
    }

    public String getOrderNumber() {
        return orderNumber;
    }
}
```

**Invoice.java**

```java
package com.example.billing.domain;

import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "invoices")
public class Invoice {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    private String invoiceNumber;

    protected Invoice() {
    }

    public Invoice(String invoiceNumber) {
        this.invoiceNumber = invoiceNumber;
    }

    public Long getId() {
        return id;
    }

    public String getInvoiceNumber() {
        return invoiceNumber;
    }
}
```

Repository:

**OrderRepository.java**

```java
package com.example.orders.repository;

import com.example.orders.domain.Order;
import java.util.Optional;
import org.springframework.data.jpa.repository.JpaRepository;

public interface OrderRepository extends JpaRepository<Order, Long> {
    Optional<Order> findByOrderNumber(String orderNumber);
}
```

**InvoiceRepository.java**

```java
package com.example.billing.repository;

import com.example.billing.domain.Invoice;
import java.util.Optional;
import org.springframework.data.jpa.repository.JpaRepository;

public interface InvoiceRepository extends JpaRepository<Invoice, Long> {
    Optional<Invoice> findByInvoiceNumber(String invoiceNumber);
}
```

## 3. Khai báo cấu hình cho database orders

Dùng `DataSourceProperties` để bind URL, username, password và driver. `initializeDataSourceBuilder()` xử lý khác biệt giữa thuộc tính `url` trong cấu hình và `jdbcUrl` của HikariCP.

**OrdersJpaConfig.java**

```java
package com.example.orders.config;

import com.example.orders.domain.Order;
import com.zaxxer.hikari.HikariDataSource;
import jakarta.persistence.EntityManagerFactory;
import javax.sql.DataSource;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.autoconfigure.jdbc.DataSourceProperties;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.orm.jpa.EntityManagerFactoryBuilder;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Primary;
import org.springframework.data.jpa.repository.config.EnableJpaRepositories;
import org.springframework.orm.jpa.JpaTransactionManager;
import org.springframework.orm.jpa.LocalContainerEntityManagerFactoryBean;
import org.springframework.transaction.PlatformTransactionManager;

@Configuration(proxyBeanMethods = false)
@EnableJpaRepositories(
    basePackages = "com.example.orders.repository",
    entityManagerFactoryRef = "ordersEntityManagerFactory",
    transactionManagerRef = "ordersTransactionManager"
)
public class OrdersJpaConfig {

    @Bean
    @Primary
    @ConfigurationProperties("app.datasource.orders")
    public DataSourceProperties ordersDataSourceProperties() {
        return new DataSourceProperties();
    }

    @Bean
    @Primary
    @ConfigurationProperties("app.datasource.orders.configuration")
    public HikariDataSource ordersDataSource(
            @Qualifier("ordersDataSourceProperties")
            DataSourceProperties properties) {
        return properties.initializeDataSourceBuilder()
            .type(HikariDataSource.class)
            .build();
    }

    @Bean
    @Primary
    public LocalContainerEntityManagerFactoryBean ordersEntityManagerFactory(
            EntityManagerFactoryBuilder builder,
            @Qualifier("ordersDataSource") DataSource dataSource) {
        return builder
            .dataSource(dataSource)
            .packages(Order.class)
            .persistenceUnit("orders")
            .build();
    }

    @Bean
    @Primary
    public PlatformTransactionManager ordersTransactionManager(
            @Qualifier("ordersEntityManagerFactory")
            EntityManagerFactory entityManagerFactory) {
        return new JpaTransactionManager(entityManagerFactory);
    }
}
```

Các điểm cần chú ý:

- `@EnableJpaRepositories` chỉ quét package repository orders.
- `packages(Order.class)` yêu cầu factory quét package chứa entity `Order`.
- `persistenceUnit("orders")` đặt tên persistence unit để có thể tham chiếu qua `@PersistenceContext(unitName = "orders")`.
- `ordersTransactionManager` được tạo từ đúng `ordersEntityManagerFactory`.
- `@Primary` giúp Spring Boot chọn nguồn dữ liệu mặc định khi một số auto-configuration cần một ứng viên chính. Nó không thay thế hai tham chiếu tường minh trong `@EnableJpaRepositories`.

Trong cấu hình này, `EntityManagerFactoryBuilder` là builder do Spring Boot JPA auto-configuration cung cấp. Đánh dấu DataSource orders là `@Primary` giúp auto-configuration có một DataSource chính khi ứng dụng có nhiều DataSource. Nếu dự án tự cấu hình JPA hoàn toàn hoặc không dùng builder auto-configured, có thể khởi tạo `LocalContainerEntityManagerFactoryBean` trực tiếp với DataSource, package scan, persistence unit name và `JpaVendorAdapter`.

## 4. Khai báo cấu hình cho database billing

Cấu hình thứ hai tương tự, nhưng dùng package entity/repository và bean name riêng. Không đánh dấu các bean billing là `@Primary` trong ví dụ vì orders được chọn làm mặc định.

**BillingJpaConfig.java**

```java
package com.example.billing.config;

import com.example.billing.domain.Invoice;
import com.zaxxer.hikari.HikariDataSource;
import jakarta.persistence.EntityManagerFactory;
import javax.sql.DataSource;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.autoconfigure.jdbc.DataSourceProperties;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.orm.jpa.EntityManagerFactoryBuilder;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.jpa.repository.config.EnableJpaRepositories;
import org.springframework.orm.jpa.JpaTransactionManager;
import org.springframework.orm.jpa.LocalContainerEntityManagerFactoryBean;
import org.springframework.transaction.PlatformTransactionManager;

@Configuration(proxyBeanMethods = false)
@EnableJpaRepositories(
    basePackages = "com.example.billing.repository",
    entityManagerFactoryRef = "billingEntityManagerFactory",
    transactionManagerRef = "billingTransactionManager"
)
public class BillingJpaConfig {

    @Bean
    @ConfigurationProperties("app.datasource.billing")
    public DataSourceProperties billingDataSourceProperties() {
        return new DataSourceProperties();
    }

    @Bean
    @ConfigurationProperties("app.datasource.billing.configuration")
    public HikariDataSource billingDataSource(
            @Qualifier("billingDataSourceProperties")
            DataSourceProperties properties) {
        return properties.initializeDataSourceBuilder()
            .type(HikariDataSource.class)
            .build();
    }

    @Bean
    public LocalContainerEntityManagerFactoryBean billingEntityManagerFactory(
            EntityManagerFactoryBuilder builder,
            @Qualifier("billingDataSource") DataSource dataSource) {
        return builder
            .dataSource(dataSource)
            .packages(Invoice.class)
            .persistenceUnit("billing")
            .build();
    }

    @Bean
    public PlatformTransactionManager billingTransactionManager(
            @Qualifier("billingEntityManagerFactory")
            EntityManagerFactory entityManagerFactory) {
        return new JpaTransactionManager(entityManagerFactory);
    }
}
```

Mỗi cấu hình có ba bean quan trọng: DataSource, EntityManagerFactory và TransactionManager. Đừng tái sử dụng transaction manager orders cho repository billing, vì manager đó gắn với factory orders.

## 5. Cấu hình connection trong application.yml

Ví dụ dùng hai PostgreSQL database:

```yaml
app:
  datasource:
    orders:
      url: jdbc:postgresql://localhost:5432/orders
      username: ${ORDERS_DB_USER}
      password: ${ORDERS_DB_PASSWORD}
      driver-class-name: org.postgresql.Driver
      configuration:
        maximum-pool-size: 10
        minimum-idle: 2

    billing:
      url: jdbc:postgresql://localhost:5432/billing
      username: ${BILLING_DB_USER}
      password: ${BILLING_DB_PASSWORD}
      driver-class-name: org.postgresql.Driver
      configuration:
        maximum-pool-size: 5
        minimum-idle: 1
```

Các biến môi trường chứa thông tin đăng nhập. Không commit mật khẩu thật vào repository. Nếu hai database dùng cùng server nhưng khác database/schema, URL và quyền kết nối vẫn cần được cấu hình riêng.

Có thể cấu hình JPA properties khác nhau cho từng persistence unit khi cần, ví dụ naming strategy, schema hoặc Hibernate batch size. Hãy đặt properties ở đúng factory; một cấu hình Hibernate toàn cục có thể không được áp dụng như mong muốn cho cả hai factory tự tạo.

## 6. Gắn service với đúng transaction manager

Service thao tác đơn hàng dùng transaction manager orders:

**OrderService.java**

```java
package com.example.service;

import com.example.orders.domain.Order;
import com.example.orders.repository.OrderRepository;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderService {

    private final OrderRepository repository;

    public OrderService(OrderRepository repository) {
        this.repository = repository;
    }

    @Transactional(transactionManager = "ordersTransactionManager")
    public Long create(String orderNumber) {
        return repository.save(new Order(orderNumber)).getId();
    }
}
```

Service thao tác hóa đơn dùng transaction manager billing:

**BillingService.java**

```java
package com.example.service;

import com.example.billing.domain.Invoice;
import com.example.billing.repository.InvoiceRepository;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class BillingService {

    private final InvoiceRepository repository;

    public BillingService(InvoiceRepository repository) {
        this.repository = repository;
    }

    @Transactional(transactionManager = "billingTransactionManager")
    public Long create(String invoiceNumber) {
        return repository.save(new Invoice(invoiceNumber)).getId();
    }
}
```

Khi chỉ định `transactionManager`, tên phải khớp bean TransactionManager đã khai báo. Nếu bỏ qua qualifier, Spring dùng manager mặc định theo quy tắc chọn bean, thường là bean `@Primary`; điều đó có thể khiến một service dùng nhầm transaction manager.

Có thể viết ngắn `@Transactional("ordersTransactionManager")`, vì thuộc tính `value` là alias cho tên transaction manager. Dùng dạng có tên thuộc tính giúp ý định rõ ràng hơn.

## 7. Tiêm EntityManager từ đúng persistence unit

Trong repository, Spring Data đã sử dụng factory được cấu hình qua `entityManagerFactoryRef`. Với DAO tùy biến cần `EntityManager` trực tiếp, khai báo unit name:

```java
package com.example.orders.repository;

import com.example.orders.domain.Order;
import jakarta.persistence.EntityManager;
import jakarta.persistence.PersistenceContext;
import java.util.List;
import org.springframework.stereotype.Repository;
import org.springframework.transaction.annotation.Transactional;

@Repository
public class OrderSearchDao {

    @PersistenceContext(unitName = "orders")
    private EntityManager entityManager;

    @Transactional(transactionManager = "ordersTransactionManager", readOnly = true)
    public List<Order> findRecent() {
        return entityManager.createQuery(
            "select o from Order o order by o.id desc",
            Order.class
        ).setMaxResults(20).getResultList();
    }
}
```

DAO billing có thể dùng `@PersistenceContext(unitName = "billing")`. Unit name phải khớp `persistenceUnit("billing")`, không phải tên bean `billingEntityManagerFactory`.

Không tự tạo `EntityManager` bằng cách gọi `entityManagerFactory.createEntityManager()` trong service thông thường rồi quên đóng nó. `@PersistenceContext` cung cấp proxy gắn với persistence context/transaction hiện tại và được container quản lý vòng đời.

Nếu cần tiêm factory trực tiếp, dùng qualifier:

```java
@Autowired
public OrderMaintenance(
        @Qualifier("ordersEntityManagerFactory")
        EntityManagerFactory entityManagerFactory) {
    this.entityManagerFactory = entityManagerFactory;
}
```

## 8. Transaction giữa hai database không tự động nguyên tử

Hai `JpaTransactionManager` quản lý hai tài nguyên riêng. Một phương thức service có `@Transactional("ordersTransactionManager")` chỉ tạo transaction cho persistence unit orders. Nếu phương thức đó gọi một service billing có transaction manager riêng, billing có thể mở và commit transaction độc lập.

Ví dụ tình huống:

1. Lưu đơn hàng trong transaction orders.
2. Gọi service billing để tạo hóa đơn; transaction billing commit.
3. Transaction orders gặp lỗi và rollback.

Kết quả có thể là hóa đơn đã tồn tại nhưng đơn hàng bị rollback. Việc đặt hai annotation `@Transactional` với hai manager khác nhau không tạo ra một distributed transaction nguyên tử.

Nếu nghiệp vụ yêu cầu cả hai database commit hoặc rollback cùng nhau, cần một giải pháp transaction phân tán thực sự, thường là JTA/XA với XA-capable DataSource và `JtaTransactionManager`. Cách này cần cấu hình coordinator, recovery log và vận hành phức tạp hơn.

Với nhiều hệ thống, transactional outbox và saga thường phù hợp hơn:

- Commit dữ liệu nghiệp vụ cùng bản ghi outbox trong database nguồn.
- Worker phát message hoặc gọi service ở database đích.
- Theo dõi trạng thái, retry và xử lý idempotent.
- Nếu bước sau thất bại, chạy hành động bù hoặc để quy trình tiếp tục retry theo chính sách.

Chọn giải pháp dựa trên yêu cầu nhất quán. Không giả định hai transaction manager cục bộ tạo ra atomic commit.

## 9. Kiểm thử wiring của nhiều persistence unit

Khi có nhiều DataSource, `@DataJpaTest` mặc định thường được thiết kế quanh một JPA slice và có thể không nạp đầy đủ hai factory cùng cấu hình riêng. Để kiểm tra toàn bộ wiring, dùng `@SpringBootTest` với hai database kiểm thử được cấu hình rõ ràng. Nếu cần xác minh hành vi đặc thù PostgreSQL, dùng Testcontainers PostgreSQL thay vì dựa vào H2.

Ví dụ integration test kiểm tra repository được gắn với hai transaction manager khác nhau:

**MultiDatabaseWiringTest.java**

```java
package com.example;

import static org.assertj.core.api.Assertions.assertThat;

import com.example.billing.domain.Invoice;
import com.example.billing.repository.InvoiceRepository;
import com.example.orders.domain.Order;
import com.example.orders.repository.OrderRepository;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.support.TransactionTemplate;

@SpringBootTest
class MultiDatabaseWiringTest {

    @Autowired
    private OrderRepository orderRepository;

    @Autowired
    private InvoiceRepository invoiceRepository;

    private final TransactionTemplate ordersTransaction;
    private final TransactionTemplate billingTransaction;

    @Autowired
    MultiDatabaseWiringTest(
            @Qualifier("ordersTransactionManager")
            PlatformTransactionManager ordersManager,
            @Qualifier("billingTransactionManager")
            PlatformTransactionManager billingManager) {
        this.ordersTransaction = new TransactionTemplate(ordersManager);
        this.billingTransaction = new TransactionTemplate(billingManager);
    }

    @Test
    void repositoriesUseTheirOwnPersistenceUnits() {
        Long orderId = ordersTransaction.execute(status ->
            orderRepository.save(new Order("ORD-TEST-001")).getId()
        );

        Long invoiceId = billingTransaction.execute(status ->
            invoiceRepository.save(new Invoice("INV-TEST-001")).getId()
        );

        boolean orderExists = ordersTransaction.execute(status ->
            orderRepository.findById(orderId).isPresent()
        );

        boolean invoiceExists = billingTransaction.execute(status ->
            invoiceRepository.findById(invoiceId).isPresent()
        );

        assertThat(orderId).isNotNull();
        assertThat(invoiceId).isNotNull();
        assertThat(orderExists).isTrue();
        assertThat(invoiceExists).isTrue();
    }
}
```

Test này cần hai database kiểm thử đã được khởi tạo schema và cấu hình trong test profile. Trong dự án thực tế, hãy dùng dữ liệu định danh duy nhất hoặc dọn dữ liệu sau test để tránh phụ thuộc thứ tự chạy. Nếu repository bị gắn nhầm factory hoặc transaction manager, test thường sẽ lỗi khi persist/query entity không thuộc persistence unit đó, hoặc dữ liệu xuất hiện ở nguồn không mong muốn.

Có thể kiểm tra thêm:

- `ordersEntityManagerFactory` và `billingEntityManagerFactory` là hai factory riêng.
- Mỗi factory chỉ quản lý entity package dự kiến.
- Mỗi repository package được quét đúng một lần.
- `@Transactional` ở service chọn đúng manager.
- Rollback trên orders không được hiểu là rollback tự động transaction billing.
- Migration/schema được áp dụng riêng cho từng database.

## 10. Lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách khắc phục |
|---|---|---|
| `NoUniqueBeanDefinitionException` cho DataSource hoặc EntityManagerFactory | Có nhiều bean cùng kiểu nhưng thiếu qualifier/primary | Dùng `@Qualifier` tại điểm tiêm và chọn `@Primary` cho mặc định nếu cần |
| Repository dùng nhầm database | `entityManagerFactoryRef` hoặc package scan cấu hình sai | Đặt ref tường minh và tách package repository |
| `Not a managed type` | Entity không nằm trong package scan của factory | Dùng `.packages(EntityClass.class)` hoặc khai báo package chính xác |
| Không tìm thấy persistence unit | `@PersistenceContext(unitName)` không khớp tên factory | Đối chiếu với `.persistenceUnit("...")` |
| Transaction không rollback dữ liệu như mong đợi | Service dùng sai transaction manager hoặc đang thao tác qua resource khác | Đặt `@Transactional(transactionManager = "...")` đúng resource |
| Boot không tạo được JPA builder mặc định | Nhiều DataSource và không có ứng viên chính hoặc auto-configuration bị loại | Chọn DataSource chính hoặc tự cấu hình builder/factory |
| Hai repository config cùng đăng ký một repository | Package scan bị chồng lấn | Giới hạn `basePackages` cho từng `@EnableJpaRepositories` |
| Test chạy được với H2 nhưng fail production | Dialect, schema, sequence, type hoặc SQL khác nhau | Test với đúng database family bằng Testcontainers |

## 11. Checklist khi triển khai

1. Xác định mỗi nguồn dữ liệu có DataSource, persistence unit, EntityManagerFactory và TransactionManager nào.
2. Tách package entity và repository theo nguồn dữ liệu.
3. Cấu hình `@EnableJpaRepositories` với `entityManagerFactoryRef` và `transactionManagerRef` tường minh.
4. Đặt persistence unit name và dùng đúng tên trong `@PersistenceContext(unitName)`.
5. Dùng qualifier khi inject bean cùng kiểu; chỉ dùng `@Primary` cho mặc định có chủ đích.
6. Gắn `@Transactional` của service với đúng transaction manager.
7. Quản lý schema/migration và connection pool riêng cho từng database.
8. Kiểm thử repository wiring trên các database tương ứng.
9. Nếu một nghiệp vụ chạm nhiều database, thiết kế rõ consistency model: JTA/XA, outbox hoặc saga.

Một DataSource cung cấp kết nối; persistence unit xác định nhóm mapping JPA; EntityManagerFactory tạo EntityManager; TransactionManager điều khiển transaction của resource tương ứng. Khi các liên kết này được khai báo tường minh, Spring Data JPA có thể vận hành nhiều nguồn dữ liệu với ranh giới repository và transaction dễ kiểm tra.