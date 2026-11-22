# Sai bean, sai nhóm Repository hoặc sai transaction manager

Khi một ứng dụng Spring Data R2DBC có nhiều cấu hình persistence, lỗi thường không nằm ở câu SQL mà ở việc Spring đang nối các thành phần với nhau sai cách. Repository có thể được tạo từ `R2dbcEntityTemplate` của database khác; một package repository có thể bị quét bởi cấu hình không đúng; Service có thể inject nhầm `ConnectionFactory`; hoặc `@Transactional` có thể chọn transaction manager không quản lý connection mà repository đang sử dụng.

Những lỗi này đôi khi không làm ứng dụng fail lúc khởi động. Một query đơn giản vẫn có thể chạy, nhưng dữ liệu xuất hiện từ database khác, transaction không rollback, hoặc một phần thao tác ghi được commit ngoài dự kiến. Vì vậy, khi chẩn đoán R2DBC, cần lần theo toàn bộ chuỗi liên kết: repository package → `R2dbcEntityOperations`/`R2dbcEntityTemplate` → `ConnectionFactory` → `ReactiveTransactionManager`.

Bài này trình bày cách nhận diện lỗi bean, lỗi nhóm repository và lỗi transaction manager; cách cấu hình rõ ràng khi có một hoặc nhiều database; cách xác nhận repository và transaction cùng dùng đúng connection factory; và cách kiểm thử để tránh lỗi cấu hình chỉ xuất hiện ở production.

## 1. Bản đồ các thành phần cần liên kết

Trong một ứng dụng Spring Data R2DBC, các thành phần chính có vai trò khác nhau:

| Thành phần | Vai trò | Lỗi khi liên kết sai |
|---|---|---|
| `ConnectionFactory` | Tạo connection tới một database/pool cụ thể | Kết nối nhầm database, sai credential hoặc pool |
| `DatabaseClient` | Thực thi SQL reactive qua `ConnectionFactory` | Query chạy trên nguồn dữ liệu khác dự kiến |
| `R2dbcEntityTemplate` | Mapping entity và thao tác persistence qua R2DBC | Mapping/dialect hoặc connection không đúng |
| `R2dbcEntityOperations` | Abstraction mà repository infrastructure dùng | Repository gắn nhầm template |
| `@EnableR2dbcRepositories` | Chọn package repository cần scan và bean operations/manager | Repository được tạo trong nhóm persistence sai |
| `ReactiveTransactionManager` | Quản lý transaction reactive | Transaction không bao phủ repository call |
| `@Transactional` | Đánh dấu phạm vi transaction | Chọn nhầm manager hoặc dùng sai kiểu transaction |

Một nhóm repository cần được hiểu như một cấu hình thống nhất:

```text
Repository package: orders.repository
          |
          v
R2dbcEntityOperations: ordersEntityTemplate
          |
          v
ConnectionFactory: ordersConnectionFactory
          |
          +------------------------------+
                                         |
                                         v
ReactiveTransactionManager: ordersTransactionManager
          |
          v
Same ConnectionFactory: ordersConnectionFactory
```

Điều kiện quan trọng là repository/template và transaction manager phải cùng dùng connection factory tương ứng khi chúng cần tham gia cùng một transaction. Chỉ có cùng database URL chưa đủ để bảo đảm chúng đang dùng cùng resource instance và cùng transaction context.

## 2. Nhận diện lỗi bean khi ứng dụng khởi động

Lỗi bean thường xuất hiện sớm dưới dạng exception trong quá trình tạo ApplicationContext. Đọc phần `Caused by` sâu nhất và bean đang được tạo, không chỉ nhìn dòng đầu tiên của stack trace.

### 2.1. NoSuchBeanDefinitionException

Ví dụ thông báo:

```text
NoSuchBeanDefinitionException:
No qualifying bean of type 'io.r2dbc.spi.ConnectionFactory' available
```

Nguyên nhân thường gặp:

- Chưa có R2DBC driver trong runtime classpath.
- Chưa khai báo `spring.r2dbc.url` hoặc cấu hình `ConnectionFactory`.
- Bean nằm trong profile không được kích hoạt.
- Lớp cấu hình không được component scan.
- Auto-configuration đã back off vì điều kiện không còn đúng.
- `@Qualifier` tham chiếu sai tên bean.
- Repository configuration yêu cầu bean `R2dbcEntityOperations` hoặc transaction manager chưa được đăng ký.

Cách xử lý:

1. Xác nhận dependency driver có trong runtime classpath.
2. Xác nhận URL bắt đầu bằng scheme R2DBC phù hợp, ví dụ `r2dbc:postgresql:`.
3. Kiểm tra profile và property source thực tế.
4. Kiểm tra package chứa `@Configuration` có được scan/import.
5. Kiểm tra bean name trong `@Qualifier`, `entityOperationsRef` và `transactionManagerRef`.
6. Nếu dùng nhiều database, khai báo tường minh từng bean thay vì chờ auto-configuration tự đoán.

### 2.2. NoUniqueBeanDefinitionException

Ví dụ:

```text
NoUniqueBeanDefinitionException:
expected single matching bean but found 2:
ordersConnectionFactory, billingConnectionFactory
```

Lỗi này xuất hiện khi một injection point cần một bean nhưng có nhiều ứng viên cùng kiểu.

Ví dụ không rõ ràng:

```java
@Service
class OrderLookupService {

    private final DatabaseClient databaseClient;

    OrderLookupService(DatabaseClient databaseClient) {
        this.databaseClient = databaseClient;
    }
}
```

Nếu có hai `DatabaseClient`, Spring không biết chọn bean nào. Chỉ định `@Qualifier`:

```java
@Service
class OrderLookupService {

    private final DatabaseClient databaseClient;

    OrderLookupService(
            @Qualifier("ordersDatabaseClient") DatabaseClient databaseClient) {
        this.databaseClient = databaseClient;
    }
}
```

`@Primary` có thể chỉ định ứng viên mặc định cho injection không có qualifier. Tuy nhiên, với cấu hình nhiều database, qualifier thường diễn đạt ý định rõ hơn. `@Primary` không tự chọn đúng repository group và không thay thế `entityOperationsRef`/`transactionManagerRef`.

### 2.3. Bean được tạo nhưng dùng nhầm cấu hình

Đây là trường hợp nguy hiểm hơn lỗi khởi động. Nếu một bean mặc định được đánh dấu `@Primary`, các injection không có qualifier có thể nhận database chính dù Service cần database phụ.

Ứng dụng vẫn chạy, query vẫn trả dữ liệu, nhưng dữ liệu có thể đến từ database sai. Hãy kiểm tra bean name và `ConnectionFactoryMetadata`, đồng thời dùng dữ liệu phân biệt trong integration test để xác nhận nguồn thật.

## 3. Phân biệt ba loại lỗi: bean, repository group và transaction manager

Ba nhóm lỗi có triệu chứng khác nhau:

| Triệu chứng | Nghi ngờ đầu tiên | Nơi cần kiểm tra |
|---|---|---|
| ApplicationContext không khởi động, thiếu bean | Bean chưa được đăng ký hoặc qualifier sai | Configuration, profile, component scan, dependency |
| ApplicationContext báo nhiều bean cùng kiểu | Injection không xác định | `@Qualifier`, `@Primary`, constructor injection |
| Repository query chạy trên database khác | Repository group/template gắn sai | `basePackages`, `entityOperationsRef`, template bean |
| Một số repository dùng đúng DB, một số dùng sai | Package scan chồng lấn hoặc nhóm cấu hình không rõ | Nhiều `@EnableR2dbcRepositories` và package boundary |
| `@Transactional` không rollback thao tác R2DBC | Manager không reactive hoặc không cùng ConnectionFactory | `ReactiveTransactionManager`, manager qualifier |
| Repository A rollback nhưng repository B vẫn commit | Hai repository dùng hai connection factory/transaction manager | Resource boundary và database grouping |
| Transaction không bao trùm query bên trong `flatMap` | Publisher bị subscribe riêng hoặc context bị tách | `subscribe()`, `block()`, pipeline composition |
| Lỗi chỉ xảy ra trong test slice | Test context không load đủ cấu hình | `@DataR2dbcTest`, `@Import`, dynamic properties |

Không thay đổi đồng thời nhiều lớp cấu hình khi chưa xác định lỗi nằm ở đâu. Kiểm tra từng mối liên kết theo thứ tự từ repository xuống connection factory rồi tới transaction manager.

## 4. Một database: cấu hình tối thiểu và cách xác nhận

Với một database, Spring Boot thường có thể auto-configure `ConnectionFactory`, `DatabaseClient`, `R2dbcEntityTemplate` và reactive transaction manager khi dependency/property phù hợp.

Ví dụ cấu hình:

```yaml
spring:
  r2dbc:
    url: r2dbc:postgresql://localhost:5432/store
    username: store_app
    password: ${DB_PASSWORD}
```

Repository:

```java
public interface CustomerRepository
        extends ReactiveCrudRepository<CustomerEntity, Long> {
}
```

Với cấu hình đơn giản, không cần khai báo `@EnableR2dbcRepositories` nếu Spring Boot đã scan repository trong package mặc định của ứng dụng. Nếu tự khai báo annotation, cần chắc chắn base package và các bean reference phù hợp.

### 4.1. Khi nào nên khai báo bean tường minh?

Khai báo tường minh có ích khi:

- Có nhiều `ConnectionFactory`.
- Có repository nằm ngoài package scan mặc định.
- Cần custom conversions/dialect.
- Cần nhiều nhóm repository độc lập.
- Muốn chỉ rõ transaction manager mà từng nhóm sử dụng.

Không nên tạo lại một `ConnectionFactory` mới trong từng bean chỉ để truyền cùng URL. Hãy inject cùng bean instance qua qualifier để template và transaction manager chia sẻ đúng resource.

## 5. Cấu hình nhiều database và nhiều nhóm Repository

Giả sử ứng dụng có hai database:

- `orders`: lưu khách hàng và đơn hàng.
- `billing`: lưu hóa đơn và thanh toán.

Tách package repository:

```text
com.example.app.orders.repository
  OrderRepository.java
  CustomerRepository.java

com.example.app.billing.repository
  InvoiceRepository.java
  PaymentRepository.java
```

Mỗi nhóm cần một bộ bean riêng:

```text
ordersRepository package
  -> ordersEntityTemplate
  -> ordersConnectionFactory
  -> ordersTransactionManager

billingRepository package
  -> billingEntityTemplate
  -> billingConnectionFactory
  -> billingTransactionManager
```

### 5.1. Cấu hình database orders

```java
@Configuration
@EnableR2dbcRepositories(
        basePackages = "com.example.app.orders.repository",
        entityOperationsRef = "ordersEntityTemplate",
        transactionManagerRef = "ordersTransactionManager")
public class OrdersR2dbcConfiguration {

    @Bean
    @Primary
    ConnectionFactory ordersConnectionFactory(
            @Value("${app.r2dbc.orders.url}") String url) {
        return ConnectionFactories.get(url);
    }

    @Bean
    R2dbcEntityOperations ordersEntityTemplate(
            @Qualifier("ordersConnectionFactory")
            ConnectionFactory connectionFactory) {
        return new R2dbcEntityTemplate(connectionFactory);
    }

    @Bean
    ReactiveTransactionManager ordersTransactionManager(
            @Qualifier("ordersConnectionFactory")
            ConnectionFactory connectionFactory) {
        return new R2dbcTransactionManager(connectionFactory);
    }
}
```

`entityOperationsRef` là tên bean `R2dbcEntityOperations` mà nhóm repository sử dụng. `R2dbcEntityTemplate` triển khai abstraction này. `transactionManagerRef` là tên bean reactive transaction manager được cấu hình cho nhóm repository.

### 5.2. Cấu hình database billing

```java
@Configuration
@EnableR2dbcRepositories(
        basePackages = "com.example.app.billing.repository",
        entityOperationsRef = "billingEntityTemplate",
        transactionManagerRef = "billingTransactionManager")
public class BillingR2dbcConfiguration {

    @Bean
    ConnectionFactory billingConnectionFactory(
            @Value("${app.r2dbc.billing.url}") String url) {
        return ConnectionFactories.get(url);
    }

    @Bean
    R2dbcEntityOperations billingEntityTemplate(
            @Qualifier("billingConnectionFactory")
            ConnectionFactory connectionFactory) {
        return new R2dbcEntityTemplate(connectionFactory);
    }

    @Bean
    ReactiveTransactionManager billingTransactionManager(
            @Qualifier("billingConnectionFactory")
            ConnectionFactory connectionFactory) {
        return new R2dbcTransactionManager(connectionFactory);
    }
}
```

Các cấu hình dùng package riêng, template riêng, connection factory riêng và transaction manager riêng. Đánh dấu `ordersConnectionFactory` là `@Primary` chỉ giúp những injection đơn trị không qualifier có một lựa chọn mặc định; code trong cấu hình billing vẫn chỉ rõ `billingConnectionFactory`.

Trong ứng dụng thực tế, nên dùng property binding (`@ConfigurationProperties`) thay vì nhiều `@Value` khi cấu hình có nhiều thuộc tính như username, password, pool size, SSL và timeout. Đoạn code trên tập trung vào mối liên kết bean.

### 5.3. Không để package scan chồng lấn

Nếu cả hai `@EnableR2dbcRepositories` đều scan `com.example.app`, một repository có thể được phát hiện bởi nhiều cấu hình hoặc bị đăng ký sai operations. Hãy giới hạn package bằng package cụ thể hoặc marker class:

```java
@EnableR2dbcRepositories(
        basePackageClasses = OrdersRepositoryMarker.class,
        entityOperationsRef = "ordersEntityTemplate",
        transactionManagerRef = "ordersTransactionManager")
```

Tạo marker class trong package repository tương ứng. Cách này tránh phụ thuộc vào chuỗi package bị đổi khi refactor.

### 5.4. Không nhầm entityOperationsRef với transactionManagerRef

- `entityOperationsRef` chọn template/operations để tạo repository và thực hiện mapping/query.
- `transactionManagerRef` chọn reactive transaction manager cho repository infrastructure.

Hai tham chiếu có nhiệm vụ riêng. Cấu hình đúng template nhưng sai transaction manager vẫn có thể làm repository query chạy đúng database nhưng transaction không bao phủ như mong đợi.

## 6. Sai nhóm Repository do package scanning

`@EnableR2dbcRepositories` quyết định các interface repository nào được đăng ký bởi một cấu hình. Nếu package scan quá rộng, nhóm repository có thể bị gắn nhầm template.

### 6.1. Ví dụ cấu hình quá rộng

```java
@EnableR2dbcRepositories(
        basePackages = "com.example.app",
        entityOperationsRef = "ordersEntityTemplate")
class OrdersR2dbcConfiguration {
}
```

Nếu package `com.example.app` chứa cả `orders.repository` và `billing.repository`, cả hai nhóm có thể được xử lý bởi cấu hình orders. Khi billing repository được gọi, nó vẫn chạy nhưng đi qua template orders.

### 6.2. Tách package theo bounded context

```text
com.example.app
  orders
    domain
    service
    repository
  billing
    domain
    service
    repository
```

Mỗi cấu hình chỉ scan đúng package repository của mình. Đừng đặt interface repository trong package cha chung nếu hai database có mapping khác nhau.

### 6.3. Repository interface kế thừa repository dùng chung

Một base repository interface có thể được tái sử dụng qua generic type, nhưng cần chú ý nơi Spring scan interface đó. Nếu base interface không phải repository độc lập, có thể đánh dấu `@NoRepositoryBean` để Spring Data không tạo repository riêng cho interface nền.

```java
@NoRepositoryBean
public interface BaseReadRepository<T, ID>
        extends ReactiveCrudRepository<T, ID> {
}
```

Repository cụ thể kế thừa base interface và nằm trong đúng package scan. Không dùng một interface base được scan như repository concrete khi chưa có domain type phù hợp.

### 6.4. Kiểm tra repository bean đã được đăng ký ở đâu

Khi nghi ngờ repository thuộc sai nhóm, kiểm tra:

- Bean name và bean definition của repository.
- Cấu hình `@EnableR2dbcRepositories` nào scan package đó.
- `entityOperationsRef` được gán cho repository factory.
- Template đó inject `ConnectionFactory` nào.
- Các package có bị scan lặp hay không.

Không chỉ nhìn tên repository bean. Tên interface không cho biết database mà nó thực sự dùng.

## 7. Sai ConnectionFactory giữa Template và TransactionManager

Đây là một nguyên nhân phổ biến khiến transaction không hoạt động dù `@Transactional` đã được khai báo.

Ví dụ cấu hình sai:

```java
@Bean
R2dbcEntityOperations ordersEntityTemplate() {
    ConnectionFactory factory = ConnectionFactories.get(ordersUrl);
    return new R2dbcEntityTemplate(factory);
}

@Bean
ReactiveTransactionManager ordersTransactionManager() {
    ConnectionFactory factory = ConnectionFactories.get(ordersUrl);
    return new R2dbcTransactionManager(factory);
}
```

Hai bean tạo hai `ConnectionFactory` instance riêng. Dù cùng URL, chúng có thể là hai pool/connection resource khác nhau. Transaction manager bind connection theo resource mà nó quản lý; thao tác repository qua template khác có thể không tham gia cùng transaction.

Cấu hình đúng là tạo một bean rồi inject lại:

```java
@Bean
ConnectionFactory ordersConnectionFactory() {
    return ConnectionFactories.get(ordersUrl);
}

@Bean
R2dbcEntityOperations ordersEntityTemplate(
        @Qualifier("ordersConnectionFactory") ConnectionFactory factory) {
    return new R2dbcEntityTemplate(factory);
}

@Bean
ReactiveTransactionManager ordersTransactionManager(
        @Qualifier("ordersConnectionFactory") ConnectionFactory factory) {
    return new R2dbcTransactionManager(factory);
}
```

Template và transaction manager dùng cùng bean `ordersConnectionFactory`. Nếu dùng pool, hãy bảo đảm cả hai cùng tham chiếu đúng pooled `ConnectionFactory` đã được cấu hình, không một bên dùng factory gốc và bên kia dùng pool wrapper khác.

## 8. Chọn đúng transaction manager

Spring có nhiều loại transaction manager. Không phải manager nào cũng quản lý được R2DBC connection.

| Transaction manager | Resource chính | Phù hợp với |
|---|---|---|
| `R2dbcTransactionManager` | R2DBC `ConnectionFactory` | Reactive R2DBC operations |
| `DataSourceTransactionManager` | JDBC `DataSource` | JDBC transaction imperative |
| `JpaTransactionManager` | JPA `EntityManagerFactory` | JPA transaction |
| `ReactiveMongoTransactionManager` | Reactive MongoDB database factory | Reactive MongoDB transaction |
| `ReactiveTransactionManager` | Interface reactive | Abstraction cho reactive transaction manager |

Nếu repository dùng R2DBC nhưng `@Transactional` chọn `DataSourceTransactionManager`, transaction JDBC đó không tự quản lý R2DBC connection. Hai resource có thể cùng trỏ một database server nhưng vẫn là hai connection/transaction khác nhau.

### 8.1. Cấu hình R2dbcTransactionManager

```java
@Bean
ReactiveTransactionManager ordersTransactionManager(
        @Qualifier("ordersConnectionFactory") ConnectionFactory factory) {
    return new R2dbcTransactionManager(factory);
}
```

Manager này phải dùng cùng `ConnectionFactory` với `R2dbcEntityTemplate`/Repository của nhóm orders.

### 8.2. Chỉ định manager ở @Transactional

Khi có nhiều transaction manager, hãy chỉ định tên bean:

```java
@Transactional(transactionManager = "ordersTransactionManager")
public Mono<OrderEntity> createOrder(OrderCommand command) {
    return inventoryRepository.reserve(command.items())
            .then(orderRepository.save(toOrder(command)));
}
```

Nếu không chỉ định, Spring cần phân giải manager mặc định theo cấu hình bean/`@Primary` và cách transaction infrastructure được đăng ký. Trong ứng dụng nhiều manager, không nên dựa vào việc chọn mặc định nếu nghiệp vụ yêu cầu database cụ thể.

### 8.3. Chọn manager bằng qualifier trong annotation

`@Transactional` hỗ trợ thuộc tính `transactionManager` (và alias `value` ở các phiên bản Spring tương ứng) để chọn manager theo bean name/qualifier. Dùng tên chính xác đã đăng ký trong ApplicationContext. Tên class hoặc tên database URL không thay thế bean name.

## 9. Phân biệt reactive transaction và imperative transaction

R2DBC là reactive. Transaction được quản lý theo reactive pipeline và Reactor Context, không dựa vào việc một thread giữ connection suốt method.

### 9.1. Method trả về Mono/Flux

```java
@Transactional(transactionManager = "ordersTransactionManager")
public Mono<OrderEntity> createOrder(OrderEntity order) {
    return orderRepository.save(order);
}
```

Với reactive return type và reactive transaction manager, transaction được gắn vào subscription của publisher. Việc thực thi xảy ra khi publisher được subscribe.

### 9.2. Dùng TransactionalOperator cho transaction tường minh

```java
@Bean
TransactionalOperator ordersTransactionalOperator(
        @Qualifier("ordersTransactionManager")
        ReactiveTransactionManager transactionManager) {
    return TransactionalOperator.create(transactionManager);
}
```

Sử dụng:

```java
public Mono<OrderEntity> createOrder(OrderEntity order) {
    return orderRepository.save(order)
            .as(ordersTransactionalOperator::transactional);
}
```

`TransactionalOperator` phù hợp khi muốn xác định transaction boundary trong pipeline, ví dụ cho một đoạn publisher cụ thể. Phải chọn đúng operator gắn với manager của database đang thao tác.

### 9.3. Không dùng TransactionTemplate imperative cho R2DBC

`TransactionTemplate` thuộc mô hình imperative `PlatformTransactionManager`. Với R2DBC, dùng annotation `@Transactional` cùng reactive manager hoặc `TransactionalOperator`. Không dùng `block()` để ép reactive repository chạy bên trong JDBC transaction.

### 9.4. Publisher phải nằm trong transaction boundary

Tránh tạo subscription rời:

```java
@Transactional(transactionManager = "ordersTransactionManager")
public Mono<Void> createOrder(OrderEntity order) {
    orderRepository.save(order).subscribe(); // Sai: subscription tách rời
    return Mono.empty();
}
```

Thay bằng composition:

```java
@Transactional(transactionManager = "ordersTransactionManager")
public Mono<Void> createOrder(OrderEntity order) {
    return orderRepository.save(order).then();
}
```

Khi tự `subscribe()`, transaction interceptor có thể hoàn tất publisher được trả về trước khi thao tác ghi rời hoàn thành. Subscription mới cũng không nhất thiết dùng cùng transaction context.

## 10. Một transaction manager chỉ quản lý resource của nó

Nếu ứng dụng có orders và billing trên hai `ConnectionFactory`, một `R2dbcTransactionManager` không tự tạo transaction nguyên tử bao trùm cả hai database.

Ví dụ:

```java
@Transactional(transactionManager = "ordersTransactionManager")
public Mono<Void> createOrderAndInvoice(OrderCommand command) {
    return orderRepository.save(toOrder(command))
            .flatMap(order -> invoiceRepository.save(toInvoice(order)))
            .then();
}
```

Nếu `orderRepository` thuộc orders database và `invoiceRepository` thuộc billing database, transaction manager orders chỉ quản lý connection orders. Invoice có thể chạy qua connection khác và commit độc lập. Nếu bước invoice lỗi, thao tác order không nhất thiết rollback cùng nó.

### 10.1. Chọn thiết kế cho nghiệp vụ xuyên database

Các lựa chọn thường gặp:

- **Tách nghiệp vụ:** transaction độc lập cho từng database nếu nghiệp vụ cho phép.
- **Saga/compensation:** mỗi bước commit riêng, bước sau lỗi thì thực hiện hành động bù.
- **Transactional outbox:** ghi sự kiện vào cùng transaction với dữ liệu chính, sau đó consumer xử lý database/dịch vụ khác.
- **Distributed transaction:** chỉ khi nền tảng và driver/database hỗ trợ đầy đủ cơ chế phù hợp; không giả định R2DBC cung cấp XA hai pha phổ quát.

Không đặt một `@Transactional` duy nhất quanh hai repository và cho rằng nó bảo đảm atomicity xuyên database. Viết integration test cố ý làm database thứ hai thất bại và xác nhận trạng thái thực tế.

## 11. Kết hợp JDBC và R2DBC trong cùng ứng dụng

Một ứng dụng có thể dùng JDBC cho migration hoặc một module legacy và R2DBC cho runtime reactive. Điều này tạo ra hai loại resource:

```text
JDBC DataSource -> DataSourceTransactionManager

R2DBC ConnectionFactory -> R2dbcTransactionManager
```

Một transaction manager không tự quản lý cả hai. Nếu method dùng JDBC repository và R2DBC repository trong cùng `@Transactional`, cần biết manager nào được chọn và resource nào tham gia.

### 11.1. Migration JDBC không có nghĩa runtime transaction dùng JDBC

Flyway/Liquibase có thể dùng JDBC để áp dụng DDL trong khi application repository chạy R2DBC. Đây là hai giai đoạn khác nhau; việc migration thành công qua JDBC không làm R2DBC repository tham gia JDBC transaction.

### 11.2. Không dùng @Primary để che giấu thiết kế transaction

Nếu có cả `PlatformTransactionManager` và `ReactiveTransactionManager`, đánh dấu một bean `@Primary` có thể giải quyết một số injection mặc định nhưng không làm hai loại transaction manager thay thế nhau. Hãy chỉ định manager đúng tại ranh giới nghiệp vụ và kiểm tra kiểu return của method.

## 12. Cấu hình bean phụ thuộc nhau một cách rõ ràng

Khi nhiều database, tên bean cần phản ánh vai trò và nhóm dữ liệu. Một quy ước hữu ích:

| Vai trò | Orders | Billing |
|---|---|---|
| `ConnectionFactory` | `ordersConnectionFactory` | `billingConnectionFactory` |
| `DatabaseClient` | `ordersDatabaseClient` | `billingDatabaseClient` |
| `R2dbcEntityOperations` | `ordersEntityTemplate` | `billingEntityTemplate` |
| Transaction manager | `ordersTransactionManager` | `billingTransactionManager` |
| Repository package | `orders.repository` | `billing.repository` |

Ví dụ bean `DatabaseClient`:

```java
@Bean
DatabaseClient ordersDatabaseClient(
        @Qualifier("ordersConnectionFactory") ConnectionFactory factory) {
    return DatabaseClient.create(factory);
}
```

Nếu `R2dbcEntityTemplate` được tạo trực tiếp từ `ConnectionFactory`, không nhất thiết phải khai báo `DatabaseClient` riêng nếu không có nơi nào cần inject nó. Tránh tạo bean trùng lặp không cần thiết.

### 12.1. Dùng @ConfigurationProperties cho cấu hình nhiều database

Thay vì hard-code URL và credential:

```yaml
app:
  r2dbc:
    orders:
      url: ${ORDERS_R2DBC_URL}
    billing:
      url: ${BILLING_R2DBC_URL}
```

Trong hệ thống thật, cấu hình còn có thể gồm username, password, pool options, SSL và timeout. Đưa chúng vào một configuration properties class cho mỗi database để kiểm tra validation và giảm sai sót do property name.

Không ghi password vào source code hoặc log cấu hình. Dùng secret store/environment injection theo nền tảng triển khai.

### 12.2. Tránh bean method gọi trực tiếp method khác khi không rõ proxy semantics

Trong `@Configuration` đầy đủ, Spring có thể intercept lời gọi giữa các `@Bean` method để trả singleton bean. Với lite configuration hoặc method được gọi như Java thông thường, có thể vô tình tạo instance mới. Cách rõ ràng nhất là inject dependency qua tham số method:

```java
@Bean
R2dbcEntityOperations ordersEntityTemplate(
        @Qualifier("ordersConnectionFactory") ConnectionFactory factory) {
    return new R2dbcEntityTemplate(factory);
}
```

Không gọi `ordersConnectionFactory()` trực tiếp để lấy instance khi có thể inject bean qua tham số.

## 13. Chẩn đoán từ triệu chứng cụ thể

### 13.1. Repository không được tạo

Kiểm tra:

1. Interface có kế thừa `ReactiveCrudRepository` hoặc repository abstraction phù hợp không?
2. Package có nằm trong `basePackages`/`basePackageClasses` không?
3. Có `@NoRepositoryBean` đặt nhầm trên repository concrete không?
4. `entityOperationsRef` có trỏ tới bean tồn tại và đúng kiểu không?
5. Có cấu hình repository khác scan trùng package không?
6. ApplicationContext có loại trừ repository auto-configuration không?

### 13.2. Repository hoạt động nhưng query sai database

Kiểm tra lần lượt:

1. Repository thuộc package nào?
2. Cấu hình `@EnableR2dbcRepositories` nào scan package đó?
3. `entityOperationsRef` đang chọn template nào?
4. Template inject `ConnectionFactory` bean nào?
5. URL/metadata của factory đó trỏ tới database nào?
6. Có `@Primary` khiến service khác dùng nhầm factory không?

Tạo một fixture chỉ tồn tại ở database A và một fixture khác chỉ tồn tại ở database B. Query qua từng repository để xác nhận nguồn dữ liệu thực tế.

### 13.3. @Transactional không rollback

Kiểm tra:

1. Method trả về `Mono`/`Flux` hay đang thực thi imperative?
2. Manager được chọn có phải `ReactiveTransactionManager` không?
3. Manager có dùng cùng `ConnectionFactory` với repository không?
4. `@Transactional` có chỉ rõ manager khi có nhiều manager không?
5. Có `subscribe()`/`block()` hoặc callback tách khỏi pipeline không?
6. Có `onErrorResume` nuốt lỗi trước transaction boundary không?
7. Các thao tác có thực sự cùng một database/resource không?
8. Test có đọc trạng thái cuối từ transaction/connection độc lập không?

### 13.4. Transaction chỉ hoạt động với một repository

Nếu hai repository thuộc hai nhóm database, chúng có thể dùng hai transaction manager. Một manager không quản lý connection của nhóm còn lại. Xác định rõ liệu nghiệp vụ cần một database transaction hay quy trình xuyên database có compensation/outbox.

### 13.5. Lỗi chỉ xuất hiện trong test

Test slice như `@DataR2dbcTest` có thể chỉ tạo một phần ApplicationContext hoặc thay thế cấu hình datasource theo profile. Kiểm tra:

- `@Import` các cấu hình persistence cần thiết.
- `@DynamicPropertySource` có cung cấp đúng URL cho từng factory.
- Test có load đúng repository group.
- Migration/schema có được áp dụng vào đúng database.
- Test transaction manager có cùng factory với repository.

Không sửa production config chỉ để làm test slice hoạt động nếu test context chưa import đúng cấu hình.

## 14. Công cụ quan sát bean và auto-configuration

Khi không rõ Spring đã tạo những bean nào, kiểm tra ApplicationContext thay vì suy đoán.

### 14.1. Liệt kê bean theo type

Có thể dùng một diagnostic component tạm thời hoặc breakpoint:

```java
@Component
class PersistenceBeanDiagnostics implements ApplicationRunner {

    private final ApplicationContext context;

    PersistenceBeanDiagnostics(ApplicationContext context) {
        this.context = context;
    }

    @Override
    public void run(ApplicationArguments args) {
        context.getBeansOfType(ConnectionFactory.class)
                .forEach((name, bean) ->
                        log.info("ConnectionFactory bean: {} -> {}",
                                name, bean.getMetadata().getName()));

        context.getBeansOfType(R2dbcEntityOperations.class)
                .forEach((name, bean) ->
                        log.info("R2dbcEntityOperations bean: {} -> {}",
                                name, bean.getClass().getName()));

        context.getBeansOfType(ReactiveTransactionManager.class)
                .forEach((name, bean) ->
                        log.info("ReactiveTransactionManager bean: {} -> {}",
                                name, bean.getClass().getName()));
    }
}
```

Đây là ví dụ chẩn đoán; cần import các type và logger theo dự án. Tránh log connection URL có password hoặc object `toString()` chứa credential. Có thể bỏ component sau khi điều tra hoặc giới hạn trong profile debug.

### 14.2. Spring Boot condition evaluation report

Khởi động với `--debug` để xem điều kiện auto-configuration nào match hoặc back off. Điều này hữu ích khi một bean mặc định không được tạo vì ứng dụng đã khai báo bean cùng loại hoặc thiếu dependency/property.

Nếu Actuator được bật, endpoint `beans` và `conditions` có thể giúp quan sát ApplicationContext/auto-configuration. Bảo vệ endpoint bằng security và chỉ expose trong môi trường phù hợp; không công khai thông tin bean nội bộ ra Internet.

### 14.3. Kiểm tra dependency tree

Nếu lỗi xuất hiện sau khi nâng version, kiểm tra dependency tree để phát hiện nhiều version của R2DBC SPI, driver, Spring Data hoặc pool. Dùng BOM của Spring Boot hoặc dependency management nhất quán. Không override một thư viện nền chỉ để sửa compile error mà chưa xác nhận runtime compatibility.

## 15. Kiểm thử cấu hình nhiều Repository group

Mỗi nhóm repository nên có integration test chứng minh nó đi tới đúng database và đúng transaction manager.

### 15.1. Test nguồn dữ liệu của từng nhóm

Tạo một hàng marker trong mỗi database:

- Orders DB có order code `ORD-ONLY-ORDERS`.
- Billing DB có invoice number `INV-ONLY-BILLING`.

Gọi repository tương ứng và xác nhận chỉ database đúng có thể trả hàng. Không dùng cùng fixture value ở cả hai database vì sẽ khó phát hiện gắn nhầm template.

### 15.2. Test transaction rollback của từng nhóm

Với orders:

1. Bắt đầu transaction bằng `ordersTransactionManager`.
2. Thực hiện một ghi hợp lệ.
3. Phát lỗi ở bước tiếp theo.
4. Đọc lại qua một subscription/transaction độc lập.
5. Xác nhận cả hai thay đổi được rollback theo contract.

Lặp lại tương tự cho billing với manager riêng. Test này xác nhận mỗi manager gắn đúng factory.

### 15.3. Test không vô tình trộn hai database

Gọi một service thực hiện thao tác orders và billing rồi cố ý làm bước thứ hai thất bại. Xác nhận trạng thái thực tế phù hợp với thiết kế: nếu không có distributed transaction, không giả định cả hai database rollback cùng nhau. Nếu dùng outbox/saga, kiểm tra event hoặc compensation tương ứng.

### 15.4. Test transaction manager được chọn

Có thể inject manager theo qualifier vào `TransactionalOperator` cho test và xác nhận thao tác được quản lý bởi đúng resource. Đừng chỉ kiểm tra annotation có tên đúng; hãy xác nhận dữ liệu cuối và rollback behavior.

## 16. Tương tác với Spring Data R2DBC auditing và custom conversions

Khi có nhiều `R2dbcEntityTemplate`, mỗi template có thể cần mapping/conversion configuration riêng nếu database dùng schema hoặc kiểu dữ liệu khác nhau.

### 16.1. Auditing provider

`@EnableR2dbcAuditing` cần được cấu hình trong application context phù hợp. Nếu nhiều repository group cùng dùng auditor, có thể dùng chung `ReactiveAuditorAware` khi actor semantics giống nhau. Nếu mỗi group có chính sách khác nhau, xác định rõ provider/callback và phạm vi cấu hình; tránh để hai cấu hình auditing cạnh tranh hoặc bean reference mơ hồ.

### 16.2. Custom conversions

Một `R2dbcCustomConversions` hoặc mapping context được gắn với template có thể quyết định cách map enum, JSON hoặc value object. Khi nhiều database có kiểu native khác nhau, không mặc định một converter dùng tốt cho mọi driver. Test mapping qua repository của từng group.

### 16.3. Dialect

`R2dbcEntityTemplate` cần dialect phù hợp với `ConnectionFactory`. Khi cấu hình nhiều database, không dùng một dialect cố định cho tất cả nếu hệ quản trị khác nhau. Xác nhận SQL được tạo theo đúng driver/database group.

## 17. Những lỗi thường gặp

### Chỉ thêm @Primary rồi cho rằng repository đã dùng đúng database

`@Primary` giải quyết injection mặc định, không chọn repository package hoặc `entityOperationsRef`. Cấu hình rõ từng nhóm.

### Hai cấu hình scan cùng package

Repository có thể bị đăng ký lặp hoặc gắn sai operations. Giới hạn `basePackages`/`basePackageClasses` không chồng lấn.

### Template và transaction manager tạo ConnectionFactory riêng

Dù cùng URL, hai instance/pool riêng có thể không chia sẻ transaction resource. Inject cùng bean factory vào cả hai.

### Dùng JpaTransactionManager hoặc DataSourceTransactionManager cho R2DBC repository

Manager imperative không quản lý R2DBC connection. Dùng `R2dbcTransactionManager` hoặc reactive manager phù hợp.

### Không chỉ định transactionManager khi có nhiều manager

Spring có thể chọn manager mặc định không đúng ý định. Dùng `@Transactional(transactionManager = "...")` hoặc `TransactionalOperator` được tạo từ manager cụ thể.

### Nghĩ một transaction bao trùm nhiều ConnectionFactory

Một R2DBC manager quản lý resource của nó. Hai database cần thiết kế distributed workflow như outbox/saga nếu cần phối hợp.

### Dùng @Transactional nhưng gọi subscribe bên trong

Subscription rời có thể chạy ngoài transaction context. Trả và kết hợp publisher bằng `flatMap`, `then` hoặc operator tương ứng.

### Dùng TransactionTemplate với reactive repository

Đây là abstraction imperative. Dùng `TransactionalOperator` hoặc annotation reactive.

### Chỉ kiểm tra bean tồn tại mà không kiểm tra nguồn dữ liệu

Bean có thể đúng type nhưng trỏ sai database. Kiểm tra metadata, URL an toàn và fixture phân biệt từng database.

### Cấu hình test slice khác production

Test có thể chỉ load một template/manager hoặc dùng property sai. Import cấu hình và cấp dynamic properties cho từng group.

## 18. Quy trình chẩn đoán có hệ thống

Khi phát hiện repository hoặc transaction chạy sai, đi theo thứ tự sau:

1. Đọc exception đầy đủ, xác định lỗi xảy ra lúc tạo context, tạo repository hay thực thi query.
2. Liệt kê các bean `ConnectionFactory`, `R2dbcEntityOperations` và `ReactiveTransactionManager` theo tên.
3. Xác định package repository đang lỗi và cấu hình `@EnableR2dbcRepositories` scan package đó.
4. Kiểm tra `entityOperationsRef` trỏ tới template đúng.
5. Kiểm tra template inject đúng `ConnectionFactory` bean.
6. Kiểm tra repository group không bị package scan khác bao phủ.
7. Xác định manager được chọn bởi `@Transactional` hoặc `TransactionalOperator`.
8. Xác nhận manager dùng cùng `ConnectionFactory` với template/repository.
9. Kiểm tra publisher không bị tách bằng `subscribe()`/`block()` và lỗi không bị nuốt trước transaction boundary.
10. Chạy integration test bằng fixture chỉ tồn tại trong database cần kiểm tra.
11. Cố ý tạo lỗi giữa transaction và xác nhận trạng thái cuối từ connection độc lập.
12. Nếu có nhiều database, xác định rõ nghiệp vụ có yêu cầu atomicity xuyên database hay không.

## 19. Checklist cấu hình và vận hành

- [ ] Mỗi `ConnectionFactory` có bean name rõ ràng.
- [ ] Mọi injection có nhiều ứng viên dùng `@Qualifier` hoặc một `@Primary` được chọn có chủ đích.
- [ ] Mỗi nhóm repository có package scan riêng, không chồng lấn.
- [ ] `entityOperationsRef` trỏ đúng `R2dbcEntityTemplate`/`R2dbcEntityOperations`.
- [ ] Template dùng đúng `ConnectionFactory` của database group.
- [ ] Transaction manager dùng cùng bean `ConnectionFactory` với template.
- [ ] `transactionManagerRef` được khai báo rõ cho từng repository group khi cần.
- [ ] `@Transactional` chỉ định manager đúng khi có nhiều manager.
- [ ] R2DBC repository dùng reactive transaction manager, không nhầm JDBC/JPA manager.
- [ ] Transactional publisher không bị tách bởi nested `subscribe()` hoặc `block()`.
- [ ] `TransactionalOperator` được tạo từ manager đúng database.
- [ ] Nghiệp vụ xuyên nhiều database có outbox/saga/compensation hoặc thiết kế phù hợp.
- [ ] Test chứng minh từng repository group truy cập đúng database.
- [ ] Test rollback xác nhận trạng thái cuối trên database thật.
- [ ] Test context nạp đúng cấu hình, profile, property và migration.
- [ ] Diagnostic log không làm lộ password hoặc credential.

Khi chẩn đoán R2DBC, đừng dừng ở việc thấy một bean tồn tại hoặc một query chạy thành công. Hãy xác nhận repository được scan vào đúng nhóm, nhóm đó dùng đúng `R2dbcEntityTemplate`, template và transaction manager cùng tham chiếu một `ConnectionFactory`, và transaction được gắn vào đúng reactive pipeline. Với nhiều database, mỗi nhóm cần cấu hình tường minh; còn nghiệp vụ xuyên database cần một thiết kế phối hợp riêng. Các integration test kiểm tra nguồn dữ liệu và rollback là bằng chứng đáng tin cậy nhất để phát hiện cấu hình sai trước khi phát hành.
