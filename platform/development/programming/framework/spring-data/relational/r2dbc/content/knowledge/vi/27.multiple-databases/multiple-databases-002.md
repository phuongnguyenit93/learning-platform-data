# Gắn từng nhóm Repository với đúng R2dbcEntityOperations

Khi một ứng dụng Spring Data Relational R2DBC kết nối nhiều database, mỗi nhóm repository phải được gắn với đúng hạ tầng truy cập dữ liệu của database mà nó quản lý. Điểm cấu hình quyết định là thuộc tính **entityOperationsRef** của `@EnableR2dbcRepositories`.

`R2dbcEntityOperations` là abstraction mà repository infrastructure dùng để thực hiện thao tác entity. `R2dbcEntityTemplate` là implementation phổ biến của abstraction này. Mỗi template cần được tạo từ đúng `ConnectionFactory`; sau đó từng nhóm repository tham chiếu đến bean template tương ứng.

Ví dụ, repository quản lý đơn hàng phải dùng `ordersR2dbcEntityOperations`, còn repository quản lý thanh toán phải dùng `billingR2dbcEntityOperations`. Chỉ khai báo nhiều `ConnectionFactory` hoặc đánh dấu một bean `@Primary` không tự động định tuyến từng repository đến đúng database.

## 1. Vai trò của R2dbcEntityOperations

Trong Spring Data R2DBC, các thành phần chính có quan hệ như sau:

| Thành phần | Vai trò |
|---|---|
| `ConnectionFactory` | Cung cấp R2DBC Connection đến một database |
| `DatabaseClient` | Thực thi SQL và bind tham số trên ConnectionFactory |
| `R2dbcEntityOperations` | Abstraction cho thao tác entity như select, insert, update, delete |
| `R2dbcEntityTemplate` | Implementation của R2dbcEntityOperations, sử dụng mapping infrastructure của Spring Data |
| Repository factory | Tạo implementation cho các repository interface |
| `@EnableR2dbcRepositories` | Chỉ định nhóm repository được quét và entity operations bean mà nhóm đó sử dụng |

Khi Spring tạo repository, repository factory cần biết cách đọc và ghi entity. Bean `R2dbcEntityOperations` cung cấp đường đi đó.

Mô hình một database:

~~~text
OrdersRepository
       |
       v
ordersR2dbcEntityOperations
       |
       v
R2dbcEntityTemplate
       |
       v
ordersConnectionFactory
       |
       v
Orders database
~~~

Mô hình nhiều database:

~~~text
OrdersRepository                  BillingRepository
       |                                  |
       v                                  v
ordersR2dbcEntityOperations     billingR2dbcEntityOperations
       |                                  |
       v                                  v
R2dbcEntityTemplate              R2dbcEntityTemplate
       |                                  |
       v                                  v
ordersConnectionFactory          billingConnectionFactory
       |                                  |
       v                                  v
Orders database                  Billing database
~~~

Mỗi nhánh có `ConnectionFactory` và entity operations riêng. Việc gắn đúng nhánh được thực hiện ở cấu hình repository scanning.

## 2. Vì sao cần tách từng nhóm repository?

Giả sử ứng dụng có hai database:

- `orders_db` lưu đơn hàng, dòng hàng và trạng thái giao hàng.
- `billing_db` lưu hóa đơn, khoản thanh toán và giao dịch.

Có thể có hai repository:

~~~java
public interface OrderRepository
        extends ReactiveCrudRepository<Order, Long> {
}
~~~

~~~java
public interface InvoiceRepository
        extends ReactiveCrudRepository<Invoice, Long> {
}
~~~

Nếu cả hai nhóm được quét bởi cùng một `@EnableR2dbcRepositories` mặc định, chúng sẽ được tạo dựa trên cùng entity operations bean. Điều này có thể khiến repository truy cập nhầm database hoặc dùng mapping/transaction infrastructure không phù hợp.

Giải pháp là tách package repository theo database và khai báo mỗi nhóm trong một cấu hình riêng, với `entityOperationsRef` trỏ đến bean tương ứng.

## 3. Tổ chức package repository

Một cấu trúc dễ quản lý:

~~~text
com.example.application
|
+-- orders
|   +-- entity
|   |   +-- Order.java
|   |   +-- OrderLine.java
|   +-- repository
|   |   +-- OrderRepository.java
|   |   +-- OrderLineRepository.java
|   +-- config
|       +-- OrdersR2dbcConfiguration.java
|
+-- billing
|   +-- entity
|   |   +-- Invoice.java
|   |   +-- Payment.java
|   +-- repository
|   |   +-- InvoiceRepository.java
|   |   +-- PaymentRepository.java
|   +-- config
|       +-- BillingR2dbcConfiguration.java
|
+-- shared
    +-- config
~~~

Mỗi cấu hình chỉ quét package repository thuộc database của nó. Có thể dùng `basePackages` với tên package dạng chuỗi hoặc `basePackageClasses` với marker class.

Ví dụ marker:

~~~java
package com.example.application.orders.repository;

public interface OrdersRepositoryMarker {
}
~~~

`basePackageClasses` giúp tránh lỗi đánh máy package và vẫn hoạt động khi refactor package trong IDE.

## 4. Khai báo repository scanning với entityOperationsRef

Annotation `@EnableR2dbcRepositories` có thuộc tính `entityOperationsRef`. Thuộc tính này nhận **tên bean** cung cấp `R2dbcEntityOperations` cho những repository được quét.

Ví dụ:

~~~java
@Configuration
@EnableR2dbcRepositories(
    basePackageClasses = OrdersRepositoryMarker.class,
    entityOperationsRef = "ordersR2dbcEntityOperations"
)
public class OrdersRepositoryConfiguration {
}
~~~

Ở đây:

- `basePackageClasses` xác định package cần quét.
- `entityOperationsRef` trỏ đến bean tên `ordersR2dbcEntityOperations`.
- Tất cả repository được phát hiện trong phạm vi scan này được tạo với entity operations đã chỉ định.

Giá trị của `entityOperationsRef` phải khớp chính xác với tên bean. Đây là tham chiếu theo tên, không phải tên class và cũng không phải tên `ConnectionFactory`.

Nếu không chỉ định thuộc tính này, Spring Data R2DBC sử dụng tên entity operations mặc định theo cấu hình chuẩn, thường là `r2dbcEntityTemplate`. Khi có nhiều database, nên khai báo tường minh để tránh repository vô tình dùng template mặc định.

## 5. Cấu hình ConnectionFactory và R2dbcEntityOperations cho database thứ nhất

Ví dụ cấu hình database orders:

~~~java
@Configuration
@EnableR2dbcRepositories(
    basePackageClasses = OrdersRepositoryMarker.class,
    entityOperationsRef = "ordersR2dbcEntityOperations"
)
public class OrdersR2dbcConfiguration {

    @Bean("ordersConnectionFactory")
    public ConnectionFactory ordersConnectionFactory(
            OrdersDatabaseProperties properties) {
        return properties.connectionFactory();
    }

    @Bean("ordersR2dbcEntityOperations")
    public R2dbcEntityOperations ordersR2dbcEntityOperations(
            @Qualifier("ordersConnectionFactory")
            ConnectionFactory connectionFactory) {

        return new R2dbcEntityTemplate(connectionFactory);
    }
}
~~~

`OrdersDatabaseProperties` trong ví dụ đại diện cho cấu hình kết nối của ứng dụng. Có thể tạo `ConnectionFactory` từ URL và thông tin xác thực được nạp từ environment, secret store hoặc cấu hình ngoài. Không hard-code mật khẩu trong source code.

Điểm quan trọng:

1. Bean ConnectionFactory có tên riêng.
2. Tham số inject dùng `@Qualifier` để chọn đúng ConnectionFactory.
3. Template được tạo từ ConnectionFactory đã chọn.
4. Bean template có tên trùng với `entityOperationsRef`.

`R2dbcEntityTemplate` triển khai `R2dbcEntityOperations`, vì vậy có thể khai báo kiểu trả về bean là interface hoặc implementation. Dùng interface giúp thể hiện đúng contract mà repository infrastructure cần.

## 6. Cấu hình database thứ hai

Billing có cấu hình tương tự nhưng dùng package, connection factory và entity operations khác:

~~~java
@Configuration
@EnableR2dbcRepositories(
    basePackageClasses = BillingRepositoryMarker.class,
    entityOperationsRef = "billingR2dbcEntityOperations"
)
public class BillingR2dbcConfiguration {

    @Bean("billingConnectionFactory")
    public ConnectionFactory billingConnectionFactory(
            BillingDatabaseProperties properties) {
        return properties.connectionFactory();
    }

    @Bean("billingR2dbcEntityOperations")
    public R2dbcEntityOperations billingR2dbcEntityOperations(
            @Qualifier("billingConnectionFactory")
            ConnectionFactory connectionFactory) {

        return new R2dbcEntityTemplate(connectionFactory);
    }
}
~~~

Repository trong package billing được gắn với template billing:

~~~java
public interface InvoiceRepository
        extends ReactiveCrudRepository<Invoice, Long> {
}
~~~

Không cần thêm `@Qualifier` trên từng repository interface. Việc gắn được quyết định bởi phạm vi scan của `@EnableR2dbcRepositories` và `entityOperationsRef`.

## 7. Cấu hình hai nhóm trong một class hay hai class?

Có thể khai báo nhiều nhóm repository trong các configuration class riêng. Cách này thường dễ đọc và bảo trì:

- Mỗi class thể hiện một database boundary.
- ConnectionFactory và template có tên rõ ràng.
- Package scan được giới hạn riêng.
- Transaction manager tương ứng có thể được khai báo cùng cấu hình.

Cũng có thể đặt các bean ở một class cấu hình chung, miễn là mỗi `@EnableR2dbcRepositories` vẫn xác định đúng package và `entityOperationsRef`. Điều quan trọng là không để hai nhóm scan chồng lấn hoặc cùng dùng nhầm một operations bean.

Không nên đặt nhiều annotation scan giống nhau trên cùng package chỉ để “cho chắc”. Một repository interface không nên bị đăng ký bởi hai repository configuration khác nhau.

## 8. Dùng basePackages và basePackageClasses đúng cách

Hai cách khai báo phổ biến:

~~~java
@EnableR2dbcRepositories(
    basePackages = "com.example.application.orders.repository",
    entityOperationsRef = "ordersR2dbcEntityOperations"
)
~~~

Hoặc:

~~~java
@EnableR2dbcRepositories(
    basePackageClasses = OrdersRepositoryMarker.class,
    entityOperationsRef = "ordersR2dbcEntityOperations"
)
~~~

`basePackages` thuận tiện khi package được cấu hình bằng chuỗi. `basePackageClasses` an toàn hơn khi refactor vì compiler có thể kiểm tra class tham chiếu.

Nếu bỏ cả hai thuộc tính, Spring sẽ quét package của class cấu hình và các package con theo quy tắc component/repository scanning của annotation. Với ứng dụng nhiều database, không nên dựa vào phạm vi mặc định nếu nó có thể bao gồm repository của database khác.

Ví dụ cấu hình không tốt:

~~~java
@Configuration
@EnableR2dbcRepositories(
    basePackages = "com.example.application",
    entityOperationsRef = "ordersR2dbcEntityOperations"
)
public class OrdersR2dbcConfiguration {
}
~~~

Nếu package `com.example.application` chứa cả orders và billing repository, cả hai nhóm có thể bị đăng ký với operations của orders. Hãy thu hẹp scan đến package orders.

## 9. Vì sao @Primary không thay thế entityOperationsRef?

Khi Spring thấy nhiều bean cùng kiểu, `@Primary` giúp chọn một bean mặc định cho injection không có qualifier.

Ví dụ:

~~~java
@Bean
@Primary
ConnectionFactory ordersConnectionFactory() {
    // ...
}
~~~

Điều này hữu ích khi một số auto-configuration hoặc component cần một ConnectionFactory mặc định. Nhưng `@Primary` không thể diễn đạt rằng:

- OrderRepository dùng orders database.
- InvoiceRepository dùng billing database.

Việc đó phải được cấu hình ở repository infrastructure bằng `entityOperationsRef`.

Tương tự, nếu khai báo nhiều `R2dbcEntityOperations` và không chỉ định `entityOperationsRef`, việc chọn bean mặc định có thể phụ thuộc cấu hình và tạo ra liên kết không rõ ràng. Với nhiều database, luôn nên tham chiếu tường minh.

Quy tắc thực hành:

- Dùng `@Primary` chỉ để giải quyết một dependency mặc định thực sự cần thiết.
- Dùng `@Qualifier` để inject ConnectionFactory hoặc DatabaseClient cụ thể.
- Dùng `entityOperationsRef` để gắn repository group với template cụ thể.

## 10. Cấu hình DatabaseClient riêng cho từng database

Nếu ngoài repository còn cần SQL tùy chỉnh, hãy tạo DatabaseClient cho từng ConnectionFactory:

~~~java
@Bean("ordersDatabaseClient")
public DatabaseClient ordersDatabaseClient(
        @Qualifier("ordersConnectionFactory")
        ConnectionFactory connectionFactory) {

    return DatabaseClient.create(connectionFactory);
}

@Bean("billingDatabaseClient")
public DatabaseClient billingDatabaseClient(
        @Qualifier("billingConnectionFactory")
        ConnectionFactory connectionFactory) {

    return DatabaseClient.create(connectionFactory);
}
~~~

Inject bằng qualifier:

~~~java
public OrdersReadService(
        @Qualifier("ordersDatabaseClient")
        DatabaseClient databaseClient) {
    this.databaseClient = databaseClient;
}
~~~

Không inject `DatabaseClient` không qualifier khi có nhiều bean cùng kiểu. Spring có thể báo `NoUniqueBeanDefinitionException` hoặc chọn bean primary không đúng ý định.

`DatabaseClient` được tạo trực tiếp từ ConnectionFactory không tự trở thành repository entity operations. Nó là abstraction thực thi SQL. Nếu muốn repository dùng một database, vẫn cần cấu hình `R2dbcEntityOperations` và `entityOperationsRef`.

## 11. Gắn transaction manager đúng database

Mỗi ConnectionFactory thường cần một `R2dbcTransactionManager` riêng:

~~~java
@Bean("ordersTransactionManager")
public ReactiveTransactionManager ordersTransactionManager(
        @Qualifier("ordersConnectionFactory")
        ConnectionFactory connectionFactory) {

    return new R2dbcTransactionManager(connectionFactory);
}

@Bean("billingTransactionManager")
public ReactiveTransactionManager billingTransactionManager(
        @Qualifier("billingConnectionFactory")
        ConnectionFactory connectionFactory) {

    return new R2dbcTransactionManager(connectionFactory);
}
~~~

Khi service thao tác orders:

~~~java
@Transactional(transactionManager = "ordersTransactionManager")
public Mono<Order> createOrder(Order order) {
    return orderRepository.save(order);
}
~~~

Khi service thao tác billing:

~~~java
@Transactional(transactionManager = "billingTransactionManager")
public Mono<Invoice> createInvoice(Invoice invoice) {
    return invoiceRepository.save(invoice);
}
~~~

Transaction manager phải quản lý cùng ConnectionFactory mà repository sử dụng. Nếu dùng nhầm manager, repository có thể không tham gia transaction mà service mong muốn.

Nếu chỉ có một transaction manager hoặc muốn chọn manager mặc định, có thể dùng `@Primary` cho bean manager mặc định. Nhưng khi một service cần một database cụ thể, nên chỉ rõ `transactionManager` trong `@Transactional`.

## 12. Dùng TransactionalOperator theo từng database

Với programmatic transaction, tạo một operator cho mỗi manager:

~~~java
@Bean("ordersTransactionalOperator")
public TransactionalOperator ordersTransactionalOperator(
        @Qualifier("ordersTransactionManager")
        ReactiveTransactionManager transactionManager) {

    return TransactionalOperator.create(transactionManager);
}

@Bean("billingTransactionalOperator")
public TransactionalOperator billingTransactionalOperator(
        @Qualifier("billingTransactionManager")
        ReactiveTransactionManager transactionManager) {

    return TransactionalOperator.create(transactionManager);
}
~~~

Inject đúng operator:

~~~java
public OrdersService(
        OrderRepository orderRepository,
        @Qualifier("ordersTransactionalOperator")
        TransactionalOperator transactionalOperator) {
    this.orderRepository = orderRepository;
    this.transactionalOperator = transactionalOperator;
}
~~~

Sau đó:

~~~java
return transactionalOperator.transactional(
    orderRepository.save(order)
);
~~~

Không dùng một TransactionalOperator được tạo từ billing manager để bao một thao tác orders rồi kỳ vọng nó tự chọn đúng ConnectionFactory. Operator được gắn với transaction manager cụ thể.

## 13. Nhiều database không mặc định là một transaction phân tán

Một phương thức có thể gọi cả orders repository và billing repository, nhưng hai transaction manager độc lập không tự tạo thành một transaction nguyên tử trên hai database.

Ví dụ:

~~~java
public Mono<Void> createOrderAndInvoice(
        Order order,
        Invoice invoice) {

    return orderRepository.save(order)
        .flatMap(savedOrder ->
            invoiceRepository.save(invoice)
                .thenReturn(savedOrder)
        )
        .then();
}
~~~

Nếu phương thức này chỉ dùng một `@Transactional` với orders manager:

- Thao tác orders có thể tham gia transaction orders.
- Thao tác billing dùng ConnectionFactory khác nên không tự động tham gia transaction orders.
- Nếu billing thành công rồi orders rollback, hoặc ngược lại theo thứ tự thực thi, hai database có thể lệch trạng thái.

Nếu thật sự cần phối hợp nhiều database, phải chọn kiến trúc phù hợp:

- Saga với các bước và hành động bù trừ.
- Outbox/inbox để truyền sự kiện đáng tin cậy.
- Quy trình retry và reconciliation.
- Một transaction coordinator phân tán nếu toàn bộ công nghệ và driver hỗ trợ giải pháp đó.

Không giả định R2dbcTransactionManager đơn lẻ cung cấp atomic commit xuyên nhiều ConnectionFactory.

## 14. Mapping entity và converter theo database

Mỗi `R2dbcEntityTemplate` có mapping infrastructure và dialect tương ứng với database mà ConnectionFactory đại diện. Điều này quan trọng khi các database khác nhau về:

- Kiểu dữ liệu.
- Quy tắc identifier và quoting.
- Cách sinh ID.
- SQL dialect.
- Kiểu timestamp và UUID.
- Custom conversion.

Nếu hai database dùng cùng một entity class nhưng có schema hoặc kiểu cột khác nhau, cần xác định mapping nào được áp dụng cho từng template. Không nên giả định mọi converter hoặc naming rule tự động giống nhau.

Trong trường hợp cần custom conversion riêng, cấu hình mapping/conversion cho từng template một cách tường minh theo API của phiên bản Spring Data đang dùng. Tránh chia sẻ một converter có giả định database-specific cho tất cả database.

### Entity dùng chung hay entity riêng?

Nếu hai database lưu cùng một mô hình và cùng semantics cột, có thể dùng chung entity class. Nếu schema, lifecycle hoặc semantics khác nhau, entity riêng thường giúp tránh nhầm lẫn:

~~~text
orders_db.OrderRecord
billing_db.InvoiceRecord
~~~

Đừng dùng cùng một repository interface để truy cập hai database khác nhau. Tạo các repository riêng và gắn từng nhóm với operations bean tương ứng.

## 15. Cấu hình nhiều database trong Spring Boot

Spring Boot thường có thể tự cấu hình R2DBC infrastructure khi có một cấu hình kết nối mặc định. Khi ứng dụng có nhiều ConnectionFactory, cần khai báo bean riêng và tránh injection không rõ ràng.

Một cấu hình ngoài có thể phân tách theo namespace:

~~~yaml
app:
  r2dbc:
    orders:
      url: r2dbc:postgresql://orders-host:5432/orders_db
      username: orders_user
      password: ${ORDERS_DB_PASSWORD}
    billing:
      url: r2dbc:postgresql://billing-host:5432/billing_db
      username: billing_user
      password: ${BILLING_DB_PASSWORD}
~~~

Đây là ví dụ cấu trúc property; ứng dụng cần tạo `ConnectionFactory` tương ứng từ các property này bằng builder hoặc `ConnectionFactoryOptions`. Tên property không tự được Spring Boot hiểu là hai database chỉ vì chúng nằm dưới `app.r2dbc`.

Nếu giữ `spring.r2dbc.*` cho database mặc định và tạo database thứ hai bằng namespace tùy chỉnh, hãy chỉ rõ bean nào là mặc định và bean nào được dùng bởi từng repository configuration.

Không đưa credential thật vào file cấu hình được commit. Dùng environment variable, secret manager hoặc cơ chế quản lý secret của môi trường triển khai.

## 16. Connection pool và tài nguyên riêng cho từng database

Mỗi ConnectionFactory có thể sử dụng pool riêng. Điều này giúp giới hạn số connection đến từng database:

~~~text
Orders pool                    Billing pool
  max 20                         max 10
    |                              |
    v                              v
ordersConnectionFactory       billingConnectionFactory
    |                              |
    v                              v
ordersR2dbcEntityOperations   billingR2dbcEntityOperations
~~~

Giới hạn pool cần dựa trên connection limit của database, số instance ứng dụng, mức tải và thời gian giữ connection. Không đặt tổng connection tối đa của tất cả instance vượt giới hạn database.

Một database chậm không nhất thiết phải làm cạn pool của database còn lại nếu chúng dùng pool riêng. Tuy nhiên, request ứng dụng có thể vẫn phụ thuộc cả hai database và phải xử lý timeout/failure phù hợp.

## 17. Tránh lỗi scan repository chồng lấn

Giả sử có:

~~~java
@EnableR2dbcRepositories(
    basePackages = "com.example.application",
    entityOperationsRef = "ordersR2dbcEntityOperations"
)
class OrdersConfiguration {
}
~~~

và:

~~~java
@EnableR2dbcRepositories(
    basePackages = "com.example.application.billing.repository",
    entityOperationsRef = "billingR2dbcEntityOperations"
)
class BillingConfiguration {
}
~~~

Package scan của orders bao trùm billing. Một repository billing có thể bị phát hiện bởi cả hai cấu hình hoặc đăng ký không như dự kiến. Hãy giới hạn package:

~~~java
@EnableR2dbcRepositories(
    basePackages = "com.example.application.orders.repository",
    entityOperationsRef = "ordersR2dbcEntityOperations"
)
~~~

~~~java
@EnableR2dbcRepositories(
    basePackages = "com.example.application.billing.repository",
    entityOperationsRef = "billingR2dbcEntityOperations"
)
~~~

Mỗi repository interface nên thuộc đúng một vùng scan.

## 18. Các lỗi cấu hình thường gặp

| Lỗi | Hậu quả | Cách xử lý |
|---|---|---|
| Không khai báo `entityOperationsRef` khi có nhiều template | Repository có thể dùng template mặc định hoặc bean không đúng | Tham chiếu tường minh theo tên bean |
| Gõ sai tên bean trong `entityOperationsRef` | Không tìm thấy entity operations bean | Đối chiếu chính xác tên bean |
| Template được tạo từ nhầm ConnectionFactory | Repository truy cập nhầm database | Dùng `@Qualifier` khi tạo template |
| Hai cấu hình quét cùng một package | Repository có thể bị đăng ký trùng hoặc gắn sai | Tách package scan |
| Quét toàn bộ package gốc | Repository của database khác bị thu vào | Dùng basePackageClasses hoặc package cụ thể |
| Chỉ dùng `@Primary` để định tuyến repository | Không gắn từng nhóm với database riêng | Dùng `entityOperationsRef` |
| Inject DatabaseClient không qualifier | `NoUniqueBeanDefinitionException` hoặc chọn sai bean primary | Dùng `@Qualifier` |
| Repository dùng đúng template nhưng transaction manager sai | Thao tác không tham gia transaction mong muốn | Chọn manager dùng cùng ConnectionFactory |
| Dùng một TransactionalOperator cho mọi database | Transaction được mở trên manager không đúng | Tạo operator riêng theo manager |
| Nghĩ hai transaction manager tạo transaction phân tán | Có thể commit một phần | Saga/outbox hoặc coordinator phù hợp |
| Cùng entity nhưng schema khác nhau mà không kiểm tra mapping | Sai cột hoặc sai conversion | Mapping/converter riêng hoặc entity riêng |
| Credential hard-code trong source | Rò rỉ thông tin kết nối | Dùng secret ngoài source |
| Pool của mọi database đặt quá lớn | Cạn connection ở database | Tính tổng pool theo số instance và giới hạn DB |

## 19. Kiểm thử repository được gắn đúng database

Nên có integration test cho từng repository group và kiểm tra database đích thực tế.

Một cách kiểm thử:

1. Khởi tạo hai database hoặc hai schema có thể phân biệt.
2. Tạo bảng customer hoặc record với cùng tên nhưng dữ liệu khác nhau ở mỗi database.
3. Gọi repository thuộc package orders.
4. Xác nhận dữ liệu được đọc/ghi trong orders database.
5. Gọi repository thuộc package billing.
6. Xác nhận dữ liệu được đọc/ghi trong billing database.
7. Kiểm tra repository không ghi nhầm sang database còn lại.
8. Kiểm tra transaction manager tương ứng rollback đúng database.
9. Kiểm tra DatabaseClient dùng qualifier cũng truy cập đúng ConnectionFactory.

Có thể dùng Testcontainers để tạo database thật theo driver tương ứng. Test chỉ mock repository không chứng minh được `entityOperationsRef` đã gắn đúng ConnectionFactory.

### Kiểm tra khi khởi động ứng dụng

Khi context khởi động, có thể xác nhận các bean:

- `ordersConnectionFactory`.
- `billingConnectionFactory`.
- `ordersR2dbcEntityOperations`.
- `billingR2dbcEntityOperations`.
- `ordersTransactionManager`.
- `billingTransactionManager`.

Nếu có bean trùng tên hoặc tham chiếu sai, ứng dụng thường lỗi ngay khi khởi động hoặc khi repository factory được tạo. Hãy giữ tên bean nhất quán và tránh phụ thuộc vào bean mặc định không rõ ràng.

## 20. Quy trình cấu hình từng repository group

Khi thêm một database mới, có thể làm theo trình tự:

1. Tạo package riêng cho entity và repository của database.
2. Tạo `ConnectionFactory` có tên riêng.
3. Tạo `R2dbcEntityOperations`/`R2dbcEntityTemplate` từ ConnectionFactory đó.
4. Tạo cấu hình `@EnableR2dbcRepositories` với package scan riêng.
5. Đặt `entityOperationsRef` bằng đúng tên bean template.
6. Tạo transaction manager dùng cùng ConnectionFactory.
7. Nếu cần, tạo `TransactionalOperator` riêng cho transaction manager đó.
8. Tạo DatabaseClient riêng nếu có SQL tùy chỉnh và inject bằng qualifier.
9. Xác định mapping/converter/dialect phù hợp database.
10. Cấu hình pool, credentials và migration riêng.
11. Kiểm tra package scan không chồng lấn.
12. Viết integration test chứng minh repository truy cập đúng database.

Mỗi nhóm repository cần một đường cấu hình rõ ràng từ package scan đến entity operations, rồi đến ConnectionFactory. Khi đường này minh bạch, việc thêm database mới không làm thay đổi ngầm nơi lưu dữ liệu của repository cũ.

## 21. Ghi nhớ

- `R2dbcEntityOperations` là abstraction cho thao tác entity; `R2dbcEntityTemplate` là implementation thường dùng.
- Mỗi template cần được tạo từ đúng ConnectionFactory.
- `@EnableR2dbcRepositories(entityOperationsRef = "...")` gắn một nhóm repository với bean entity operations theo tên.
- Tách repository package theo database và bảo đảm các phạm vi scan không chồng lấn.
- Dùng `basePackageClasses` hoặc `basePackages` để xác định rõ nhóm repository.
- `@Primary` chỉ giải quyết lựa chọn bean mặc định khi injection mơ hồ; nó không thay thế entityOperationsRef.
- Dùng `@Qualifier` khi inject ConnectionFactory, DatabaseClient và transaction manager cụ thể.
- Mỗi database thường cần transaction manager và TransactionalOperator riêng dùng cùng ConnectionFactory với repository.
- Một transaction manager R2DBC không tự tạo atomic transaction xuyên nhiều ConnectionFactory.
- Mapping, dialect, converter, schema và connection pool cần phù hợp từng database.
- Không hard-code credential và không để một repository bị quét bởi nhiều cấu hình.
- Kiểm thử bằng database/driver thực tế để chứng minh từng repository group đọc và ghi đúng database.
