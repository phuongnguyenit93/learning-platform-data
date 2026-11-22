# Khai báo nhiều ConnectionFactory và đặt tên bean rõ ràng

## 1. Vì sao một ứng dụng cần nhiều ConnectionFactory?

Một ứng dụng Spring Data Relational R2DBC thường bắt đầu với một database và một ConnectionFactory. Khi ứng dụng chỉ truy cập một nguồn dữ liệu, Spring Boot có thể tự cấu hình các thành phần R2DBC dựa trên một bộ thuộc tính kết nối.

Trong hệ thống lớn hơn, một ứng dụng có thể cần truy cập nhiều database hoặc nhiều cụm database. Ví dụ:

- Database orders lưu đơn hàng và chi tiết đơn hàng.
- Database customers lưu hồ sơ khách hàng.
- Database audit lưu nhật ký nghiệp vụ.
- Database reporting phục vụ truy vấn báo cáo.
- Một database PostgreSQL và một database khác dùng driver riêng.
- Hai database cùng loại nhưng thuộc các môi trường hoặc bounded context khác nhau.

Với R2DBC, mỗi nguồn dữ liệu cần một ConnectionFactory tương ứng. ConnectionFactory chịu trách nhiệm tạo connection tới một database theo driver và cấu hình của nó.

Khi có nhiều ConnectionFactory, ứng dụng cần xác định rõ:

1. Repository nào sử dụng database nào.
2. R2dbcEntityTemplate nào gắn với ConnectionFactory nào.
3. DatabaseClient nào gửi SQL tới nguồn dữ liệu nào.
4. Transaction manager nào quản lý thao tác trên từng database.
5. Các bean được inject vào service phải được chọn tường minh như thế nào.

Nếu chỉ khai báo nhiều bean cùng kiểu ConnectionFactory mà không đặt tên và qualifier rõ ràng, Spring có thể không biết bean nào cần inject. Nguy hiểm hơn, code có thể chạy thành công nhưng thao tác nhầm database nếu một bean mặc định được chọn ngoài ý muốn.

Bài này tập trung vào cách khai báo nhiều ConnectionFactory, đặt tên bean nhất quán và nối từng nguồn dữ liệu với repository, template, DatabaseClient và transaction manager tương ứng.

## 2. Các thành phần cần có cho mỗi nguồn dữ liệu

Một nguồn dữ liệu R2DBC thường có các thành phần sau:

| Thành phần | Vai trò |
|---|---|
| ConnectionFactory | Tạo và quản lý việc lấy connection cho một database |
| DatabaseClient | Thực thi SQL reactive trên ConnectionFactory được gắn với nó |
| R2dbcEntityTemplate | Thực hiện thao tác entity dựa trên mapping metadata và ConnectionFactory |
| Repository configuration | Chỉ định package repository dùng R2dbcEntityTemplate nào |
| R2dbcTransactionManager | Quản lý transaction reactive trên ConnectionFactory tương ứng |
| TransactionalOperator | Cho phép bao bọc publisher trong transaction được chọn |

Một ứng dụng có hai database có thể tổ chức như sau:

~~~text
Orders database
  ordersConnectionFactory
       |
       +-- ordersDatabaseClient
       |
       +-- ordersEntityTemplate
       |       |
       |       +-- com.example.orders.repository
       |
       +-- ordersTransactionManager
       |
       +-- ordersTransactionalOperator


Audit database
  auditConnectionFactory
       |
       +-- auditDatabaseClient
       |
       +-- auditEntityTemplate
       |       |
       |       +-- com.example.audit.repository
       |
       +-- auditTransactionManager
       |
       +-- auditTransactionalOperator
~~~

Mỗi nhóm có tên riêng để thể hiện nguồn dữ liệu mà nó đại diện. Khi inject bean vào code, dùng qualifier tương ứng thay vì dựa vào thứ tự khai báo hoặc tên tham số.

## 3. Bean name và Qualifier khác nhau như thế nào?

### 3.1. Tên bean

Trong Spring, tên mặc định của bean được tạo bởi phương thức @Bean chính là tên phương thức đó.

Ví dụ:

~~~java
@Bean
ConnectionFactory ordersConnectionFactory() {
    // ...
}
~~~

Bean trên có tên ordersConnectionFactory.

Có thể chỉ định tên rõ ràng:

~~~java
@Bean("ordersConnectionFactory")
ConnectionFactory ordersConnectionFactory() {
    // ...
}
~~~

Khi ứng dụng có nhiều bean cùng kiểu, tên bean giúp nhận diện từng instance.

Nên dùng quy ước tên nhất quán theo nguồn dữ liệu, ví dụ:

- ordersConnectionFactory
- ordersDatabaseClient
- ordersEntityTemplate
- ordersTransactionManager
- auditConnectionFactory
- auditDatabaseClient
- auditEntityTemplate
- auditTransactionManager

Tên nhất quán giúp người đọc nhìn vào cấu hình hoặc constructor là biết bean đang kết nối tới database nào.

### 3.2. @Qualifier

@Qualifier chỉ định bean cụ thể khi có nhiều ứng viên cùng kiểu.

Ví dụ:

~~~java
@Service
public class AuditWriter {

    private final DatabaseClient databaseClient;

    public AuditWriter(
            @Qualifier("auditDatabaseClient")
            DatabaseClient databaseClient) {
        this.databaseClient = databaseClient;
    }
}
~~~

Nếu có hai bean DatabaseClient, Spring không thể tự chọn chỉ dựa vào kiểu. Qualifier chỉ rõ phải inject auditDatabaseClient.

Tương tự với ConnectionFactory:

~~~java
public OrdersService(
        @Qualifier("ordersConnectionFactory")
        ConnectionFactory connectionFactory) {
    this.connectionFactory = connectionFactory;
}
~~~

Hãy dùng qualifier ở những điểm inject có nhiều bean cùng kiểu. Không dựa vào tên biến Java như ordersConnectionFactory để thay thế @Qualifier trong mọi trường hợp.

### 3.3. @Primary

@Primary đánh dấu một bean làm ứng viên mặc định khi Spring phải chọn giữa nhiều bean cùng kiểu mà injection point không chỉ định qualifier.

Ví dụ:

~~~java
@Bean("ordersConnectionFactory")
@Primary
ConnectionFactory ordersConnectionFactory() {
    // ...
}
~~~

@Primary hữu ích khi ứng dụng có một database chính được dùng bởi phần lớn thành phần cũ, còn các nguồn khác chỉ được dùng ở một số module.

Tuy nhiên, @Primary không thay thế việc đặt tên và qualifier rõ ràng:

- Nó chỉ quyết định ứng viên mặc định cho một số điểm inject.
- Nó không tự định tuyến repository sang database mong muốn.
- Nó không tự chọn transaction manager cho mọi nghiệp vụ.
- Một service cần audit database vẫn phải dùng qualifier audit tương ứng.

Trong hệ thống nhiều database, hãy ưu tiên inject tường minh. Chỉ dùng @Primary khi thực sự có một nguồn dữ liệu mặc định hợp lý cho ứng dụng.

## 4. Cấu hình thuộc tính cho nhiều database

Không nên viết URL, username và password trực tiếp trong mã cấu hình. Hãy đặt chúng trong externalized configuration và lấy bí mật từ biến môi trường hoặc secret manager.

Ví dụ application.yml:

~~~yaml
app:
  r2dbc:
    orders:
      url: r2dbc:postgresql://orders-host:5432/orders
    audit:
      url: r2dbc:postgresql://audit-host:5432/audit
~~~

Các URL trên chỉ minh họa hình dạng kết nối. Trong môi trường thật, hãy cung cấp giá trị từ cấu hình triển khai hoặc secret management; không commit credentials vào source control.

Biến môi trường có thể chứa URL R2DBC phù hợp với driver. Cú pháp chính xác và các tùy chọn kết nối phụ thuộc R2DBC driver.

Có thể inject từng URL bằng @Value:

~~~java
@Value("${app.r2dbc.orders.url}")
private String ordersUrl;
~~~

Trong dự án lớn, nên dùng @ConfigurationProperties để gom các thuộc tính của từng database thành kiểu cấu hình có cấu trúc. Cách này dễ validate, kiểm thử và bổ sung pool settings hơn việc rải nhiều @Value.

### 4.1. Một bộ thuộc tính spring.r2dbc không tự tạo nhiều nguồn dữ liệu

Các thuộc tính chuẩn spring.r2dbc.* của Spring Boot thường mô tả cấu hình một ConnectionFactory được auto-configure.

Nếu ứng dụng cần nhiều nguồn dữ liệu, hãy khai báo các nhóm thuộc tính riêng như app.r2dbc.orders và app.r2dbc.audit, sau đó tạo từng ConnectionFactory bean tương ứng.

Đừng giả định rằng chỉ cần thêm app.r2dbc.audit.url là Spring Boot tự tạo một ConnectionFactory thứ hai. Tên thuộc tính tùy chỉnh không có ý nghĩa tự động với Boot nếu bạn chưa viết cấu hình để đọc chúng.

### 4.2. Tự tạo ConnectionFactory từ URL

R2DBC SPI cung cấp ConnectionFactories để tạo ConnectionFactory từ URL:

~~~java
import io.r2dbc.spi.ConnectionFactories;
import io.r2dbc.spi.ConnectionFactory;

@Bean("ordersConnectionFactory")
ConnectionFactory ordersConnectionFactory(
        @Value("${app.r2dbc.orders.url}") String url) {

    return ConnectionFactories.get(url);
}
~~~

Bean thứ hai:

~~~java
@Bean("auditConnectionFactory")
ConnectionFactory auditConnectionFactory(
        @Value("${app.r2dbc.audit.url}") String url) {

    return ConnectionFactories.get(url);
}
~~~

Hai bean được tạo độc lập. Mỗi URL cần chỉ đúng driver, host, port, database và các tùy chọn xác thực phù hợp.

Nếu URL chứa thông tin nhạy cảm, hãy bảo đảm giá trị được lấy từ secret/configuration management và không bị ghi vào log hoặc commit vào source control.

### 4.3. Tạo ConnectionFactory từ ConnectionFactoryOptions

Khi cần cấu hình từng option riêng, có thể dùng ConnectionFactoryOptions:

~~~java
import io.r2dbc.spi.ConnectionFactory;
import io.r2dbc.spi.ConnectionFactoryOptions;
import io.r2dbc.spi.ConnectionFactories;

import static io.r2dbc.spi.ConnectionFactoryOptions.DATABASE;
import static io.r2dbc.spi.ConnectionFactoryOptions.DRIVER;
import static io.r2dbc.spi.ConnectionFactoryOptions.HOST;
import static io.r2dbc.spi.ConnectionFactoryOptions.PASSWORD;
import static io.r2dbc.spi.ConnectionFactoryOptions.PORT;
import static io.r2dbc.spi.ConnectionFactoryOptions.USER;

@Bean("ordersConnectionFactory")
ConnectionFactory ordersConnectionFactory(
        @Value("${app.r2dbc.orders.host}") String host,
        @Value("${app.r2dbc.orders.port}") int port,
        @Value("${app.r2dbc.orders.database}") String database,
        @Value("${app.r2dbc.orders.username}") String username,
        @Value("${app.r2dbc.orders.password}") String password) {

    ConnectionFactoryOptions options =
        ConnectionFactoryOptions.builder()
            .option(DRIVER, "postgresql")
            .option(HOST, host)
            .option(PORT, port)
            .option(DATABASE, database)
            .option(USER, username)
            .option(PASSWORD, password)
            .build();

    return ConnectionFactories.get(options);
}
~~~

Cách này phù hợp khi muốn validate hoặc biến đổi từng thuộc tính trước khi tạo factory. Tên driver và option được hỗ trợ tùy thuộc driver.

Không trộn option của hai database trong cùng một builder. Mỗi ConnectionFactory phải được tạo từ bộ options riêng.

## 5. Khai báo hai ConnectionFactory với bean name rõ ràng

Ví dụ cấu hình đầy đủ cho hai database cùng dùng PostgreSQL:

~~~java
@Configuration
public class R2dbcConnectionFactoryConfiguration {

    @Bean("ordersConnectionFactory")
    @Primary
    ConnectionFactory ordersConnectionFactory(
            @Value("${app.r2dbc.orders.url}") String url) {
        return ConnectionFactories.get(url);
    }

    @Bean("auditConnectionFactory")
    ConnectionFactory auditConnectionFactory(
            @Value("${app.r2dbc.audit.url}") String url) {
        return ConnectionFactories.get(url);
    }
}
~~~

Trong ví dụ này:

- ordersConnectionFactory là nguồn dữ liệu chính theo quy ước ứng dụng.
- auditConnectionFactory là nguồn dữ liệu phụ.
- @Primary khiến ordersConnectionFactory được chọn ở injection point không có qualifier khi cần chọn ConnectionFactory mặc định.
- Các cấu hình phía sau vẫn phải dùng qualifier để gắn đúng nguồn dữ liệu.

Nếu ứng dụng không có database mặc định, có thể bỏ @Primary và bắt buộc qualifier tại mọi điểm inject có nhiều ứng viên.

### 5.1. Không inject ConnectionFactory mơ hồ

Không nên viết:

~~~java
public DatabaseHealthService(ConnectionFactory connectionFactory) {
    this.connectionFactory = connectionFactory;
}
~~~

Nếu có nhiều bean ConnectionFactory và không có một ứng viên mặc định duy nhất, Spring có thể báo NoUniqueBeanDefinitionException.

Hãy viết:

~~~java
public DatabaseHealthService(
        @Qualifier("auditConnectionFactory")
        ConnectionFactory connectionFactory) {
    this.connectionFactory = connectionFactory;
}
~~~

Khi đọc code, qualifier cũng giúp xác định rõ thao tác đang hướng tới database nào.

## 6. Tạo DatabaseClient riêng cho từng ConnectionFactory

DatabaseClient gắn với một ConnectionFactory. Nếu tạo hai ConnectionFactory, nên tạo hai DatabaseClient có tên tương ứng.

~~~java
@Configuration
public class R2dbcClientConfiguration {

    @Bean("ordersDatabaseClient")
    DatabaseClient ordersDatabaseClient(
            @Qualifier("ordersConnectionFactory")
            ConnectionFactory connectionFactory) {

        return DatabaseClient.create(connectionFactory);
    }

    @Bean("auditDatabaseClient")
    DatabaseClient auditDatabaseClient(
            @Qualifier("auditConnectionFactory")
            ConnectionFactory connectionFactory) {

        return DatabaseClient.create(connectionFactory);
    }
}
~~~

Khi dùng trong service:

~~~java
@Repository
public class AuditSqlRepository {

    private final DatabaseClient databaseClient;

    public AuditSqlRepository(
            @Qualifier("auditDatabaseClient")
            DatabaseClient databaseClient) {
        this.databaseClient = databaseClient;
    }

    public Mono<Integer> record(Long orderId, String action) {
        return databaseClient.sql("""
                INSERT INTO audit_events(order_id, action)
                VALUES (:orderId, :action)
                """)
            .bind("orderId", orderId)
            .bind("action", action)
            .fetch()
            .rowsUpdated();
    }
}
~~~

Câu INSERT này được thực thi qua auditDatabaseClient, nên connection được lấy từ auditConnectionFactory.

Nếu inject nhầm ordersDatabaseClient, câu SQL sẽ được gửi tới database orders. Tên bean và qualifier rõ ràng giúp ngăn lỗi định tuyến như vậy.

### 6.1. DatabaseClient không tự biết database nghiệp vụ

DatabaseClient chỉ biết ConnectionFactory mà nó được tạo cùng. Nó không đọc tên package service hoặc tên bảng để tự chọn database.

Một DatabaseClient không thể tự động chuyển sang auditConnectionFactory chỉ vì câu SQL đang truy cập bảng audit_events. Việc định tuyến phải được cấu hình trong bean hoặc được code lựa chọn tường minh.

### 6.2. Dùng DatabaseClient trong cấu hình nhiều database

Với SQL trực tiếp, inject đúng DatabaseClient bằng qualifier. Tránh tạo DatabaseClient mới rải rác trong service bằng ConnectionFactory lấy từ bean mặc định, vì điều đó làm mất tính nhất quán về cấu hình dialect, mapping, logging và quan sát.

Nếu ứng dụng có quy tắc bind marker hoặc cấu hình SQL khác nhau giữa các driver, hãy tạo DatabaseClient tương ứng cho từng nguồn dữ liệu và giữ cấu hình tại một nơi.

## 7. Tạo R2dbcEntityTemplate riêng cho từng database

R2dbcEntityTemplate là abstraction entity mapping. Mỗi template cần gắn với ConnectionFactory của database mà nó quản lý.

Ví dụ:

~~~java
@Configuration
public class R2dbcTemplateConfiguration {

    @Bean("ordersEntityTemplate")
    R2dbcEntityTemplate ordersEntityTemplate(
            @Qualifier("ordersConnectionFactory")
            ConnectionFactory connectionFactory) {

        return new R2dbcEntityTemplate(connectionFactory);
    }

    @Bean("auditEntityTemplate")
    R2dbcEntityTemplate auditEntityTemplate(
            @Qualifier("auditConnectionFactory")
            ConnectionFactory connectionFactory) {

        return new R2dbcEntityTemplate(connectionFactory);
    }
}
~~~

Mỗi template có mapping context và dialect được thiết lập theo cấu hình tương ứng. Nếu database dùng converter tùy chỉnh, naming strategy hoặc mapping context riêng, cần cấu hình chúng cho template tương ứng thay vì giả định mọi template dùng chung một bộ chuyển đổi.

### 7.1. Inject đúng template trong service

~~~java
@Service
public class AuditQueryService {

    private final R2dbcEntityTemplate auditTemplate;

    public AuditQueryService(
            @Qualifier("auditEntityTemplate")
            R2dbcEntityTemplate auditTemplate) {
        this.auditTemplate = auditTemplate;
    }
}
~~~

Khi dùng template, các thao tác entity sẽ đi qua mapping metadata của template được inject. Nếu dùng sai template, SQL có thể được gửi tới database khác dù entity class giống nhau.

### 7.2. Template và DatabaseClient có vai trò khác nhau

| Thành phần | Tập trung vào |
|---|---|
| R2dbcEntityTemplate | Entity mapping, Criteria, Query, Insert/Update theo metadata |
| DatabaseClient | SQL trực tiếp, bind parameter và map kết quả |
| ConnectionFactory | Tạo connection cho nguồn dữ liệu |

Một ứng dụng có thể dùng cả template và DatabaseClient cho cùng database. Nếu dùng nhiều database, hãy đặt tên cả hai nhóm bean theo cùng quy ước để tránh nhầm lẫn.

## 8. Định tuyến repository bằng entityOperationsRef

Khai báo một repository interface kế thừa ReactiveCrudRepository chưa đủ để Spring biết nó phải dùng template nào khi ứng dụng có nhiều nguồn dữ liệu.

Spring Data R2DBC cung cấp @EnableR2dbcRepositories với thuộc tính entityOperationsRef. Thuộc tính này chỉ định bean R2dbcEntityOperations mà các repository được quét trong package tương ứng sẽ sử dụng.

Ví dụ cấu hình repository orders:

~~~java
@Configuration
@EnableR2dbcRepositories(
    basePackages = "com.example.orders.repository",
    entityOperationsRef = "ordersEntityTemplate"
)
public class OrdersRepositoryConfiguration {
}
~~~

Cấu hình repository audit:

~~~java
@Configuration
@EnableR2dbcRepositories(
    basePackages = "com.example.audit.repository",
    entityOperationsRef = "auditEntityTemplate"
)
public class AuditRepositoryConfiguration {
}
~~~

Như vậy:

- Repository trong com.example.orders.repository dùng ordersEntityTemplate.
- Repository trong com.example.audit.repository dùng auditEntityTemplate.

Tên trong entityOperationsRef phải khớp bean name đã khai báo. Nếu gõ sai tên hoặc bean không tồn tại, repository infrastructure không thể khởi tạo đúng.

### 8.1. Tách package repository

Nên tổ chức package rõ ràng:

~~~text
com.example
  orders
    domain
    repository
    service
  audit
    domain
    repository
    service
  config
    OrdersRepositoryConfiguration
    AuditRepositoryConfiguration
    R2dbcConnectionFactoryConfiguration
    R2dbcTemplateConfiguration
~~~

Hai package repository không nên chồng lấn. Nếu cùng một repository interface bị quét bởi hai cấu hình @EnableR2dbcRepositories, việc đăng ký bean có thể xung đột hoặc repository bị gắn với template không như mong đợi.

Mỗi repository interface nên thuộc một package được định tuyến tới một entityOperationsRef cụ thể.

### 8.2. Không dùng entityOperationsRef để chọn transaction manager

entityOperationsRef chọn R2dbcEntityOperations cho repository. Nó không phải thuộc tính để chọn transaction manager.

Transaction manager được chọn ở ranh giới transaction, ví dụ qua @Transactional(transactionManager = "...") hoặc TransactionalOperator được tạo từ manager tương ứng.

Hai việc này có liên quan nhưng độc lập:

- Repository routing xác định database/template dùng để truy cập entity.
- Transaction routing xác định transaction manager quản lý publisher.

Hãy cấu hình cả hai rõ ràng.

## 9. Khai báo R2dbcTransactionManager riêng cho từng database

Mỗi ConnectionFactory cần một reactive transaction manager nếu ứng dụng muốn quản lý transaction độc lập trên database đó.

Ví dụ:

~~~java
@Configuration
public class R2dbcTransactionConfiguration {

    @Bean("ordersTransactionManager")
    ReactiveTransactionManager ordersTransactionManager(
            @Qualifier("ordersConnectionFactory")
            ConnectionFactory connectionFactory) {

        return new R2dbcTransactionManager(connectionFactory);
    }

    @Bean("auditTransactionManager")
    ReactiveTransactionManager auditTransactionManager(
            @Qualifier("auditConnectionFactory")
            ConnectionFactory connectionFactory) {

        return new R2dbcTransactionManager(connectionFactory);
    }
}
~~~

R2dbcTransactionManager quản lý transaction reactive trên ConnectionFactory được truyền vào constructor.

Tên bean phải rõ ràng để service chọn đúng transaction manager.

### 9.1. Chọn transaction manager bằng @Transactional

Ví dụ một nghiệp vụ chỉ cập nhật orders database:

~~~java
@Service
public class OrderService {

    private final OrderRepository orderRepository;

    public OrderService(OrderRepository orderRepository) {
        this.orderRepository = orderRepository;
    }

    @Transactional(transactionManager = "ordersTransactionManager")
    public Mono<Order> confirm(Long orderId) {
        return orderRepository.findById(orderId)
            .switchIfEmpty(Mono.error(
                new OrderNotFoundException(orderId)
            ))
            .flatMap(order -> {
                order.setStatus("CONFIRMED");
                return orderRepository.save(order);
            });
    }
}
~~~

transactionManager chỉ định bean manager mà Spring dùng cho transaction của phương thức reactive.

Nếu bỏ tên manager trong ứng dụng có nhiều transaction manager, Spring có thể không tìm được một manager duy nhất hoặc chọn manager mặc định theo cấu hình. Với nhiều database, nên chỉ định rõ manager tại ranh giới nghiệp vụ.

### 9.2. Chọn TransactionalOperator bằng qualifier

Có thể tạo TransactionalOperator riêng:

~~~java
@Configuration
public class TransactionalOperatorConfiguration {

    @Bean("ordersTransactionalOperator")
    TransactionalOperator ordersTransactionalOperator(
            @Qualifier("ordersTransactionManager")
            ReactiveTransactionManager transactionManager) {

        return TransactionalOperator.create(transactionManager);
    }

    @Bean("auditTransactionalOperator")
    TransactionalOperator auditTransactionalOperator(
            @Qualifier("auditTransactionManager")
            ReactiveTransactionManager transactionManager) {

        return TransactionalOperator.create(transactionManager);
    }
}
~~~

Inject operator phù hợp:

~~~java
public AuditService(
        @Qualifier("auditTransactionalOperator")
        TransactionalOperator transactionalOperator) {
    this.transactionalOperator = transactionalOperator;
}
~~~

Sau đó:

~~~java
public Mono<Void> recordAudit(Long orderId) {
    return transactionalOperator.transactional(
        auditRepository.save(new AuditEvent(orderId, "ORDER_CONFIRMED"))
            .then()
    );
}
~~~

TransactionalOperator giúp thể hiện rõ transaction bao quanh publisher nào. Cần bảo đảm các repository trong publisher dùng đúng ConnectionFactory tương ứng.

## 10. Cấu hình hoàn chỉnh theo từng database

Một cách tổ chức dễ theo dõi là chia cấu hình thành các lớp riêng cho mỗi nguồn dữ liệu.

### 10.1. Orders database

~~~java
@Configuration
@EnableR2dbcRepositories(
    basePackages = "com.example.orders.repository",
    entityOperationsRef = "ordersEntityTemplate"
)
public class OrdersR2dbcConfiguration {

    @Bean("ordersConnectionFactory")
    @Primary
    ConnectionFactory ordersConnectionFactory(
            @Value("${app.r2dbc.orders.url}") String url) {
        return ConnectionFactories.get(url);
    }

    @Bean("ordersDatabaseClient")
    DatabaseClient ordersDatabaseClient(
            @Qualifier("ordersConnectionFactory")
            ConnectionFactory connectionFactory) {
        return DatabaseClient.create(connectionFactory);
    }

    @Bean("ordersEntityTemplate")
    R2dbcEntityTemplate ordersEntityTemplate(
            @Qualifier("ordersConnectionFactory")
            ConnectionFactory connectionFactory) {
        return new R2dbcEntityTemplate(connectionFactory);
    }

    @Bean("ordersTransactionManager")
    ReactiveTransactionManager ordersTransactionManager(
            @Qualifier("ordersConnectionFactory")
            ConnectionFactory connectionFactory) {
        return new R2dbcTransactionManager(connectionFactory);
    }

    @Bean("ordersTransactionalOperator")
    TransactionalOperator ordersTransactionalOperator(
            @Qualifier("ordersTransactionManager")
            ReactiveTransactionManager transactionManager) {
        return TransactionalOperator.create(transactionManager);
    }
}
~~~

### 10.2. Audit database

~~~java
@Configuration
@EnableR2dbcRepositories(
    basePackages = "com.example.audit.repository",
    entityOperationsRef = "auditEntityTemplate"
)
public class AuditR2dbcConfiguration {

    @Bean("auditConnectionFactory")
    ConnectionFactory auditConnectionFactory(
            @Value("${app.r2dbc.audit.url}") String url) {
        return ConnectionFactories.get(url);
    }

    @Bean("auditDatabaseClient")
    DatabaseClient auditDatabaseClient(
            @Qualifier("auditConnectionFactory")
            ConnectionFactory connectionFactory) {
        return DatabaseClient.create(connectionFactory);
    }

    @Bean("auditEntityTemplate")
    R2dbcEntityTemplate auditEntityTemplate(
            @Qualifier("auditConnectionFactory")
            ConnectionFactory connectionFactory) {
        return new R2dbcEntityTemplate(connectionFactory);
    }

    @Bean("auditTransactionManager")
    ReactiveTransactionManager auditTransactionManager(
            @Qualifier("auditConnectionFactory")
            ConnectionFactory connectionFactory) {
        return new R2dbcTransactionManager(connectionFactory);
    }

    @Bean("auditTransactionalOperator")
    TransactionalOperator auditTransactionalOperator(
            @Qualifier("auditTransactionManager")
            ReactiveTransactionManager transactionManager) {
        return TransactionalOperator.create(transactionManager);
    }
}
~~~

Ví dụ trên giả định cả hai nguồn dùng driver tương thích với URL đã cấu hình và dùng mapping mặc định. Nếu hai database có driver, dialect, converter hoặc pool configuration khác nhau, hãy điều chỉnh từng bean tương ứng.

Nếu đặt hai lớp cấu hình ở package được component scan, Spring sẽ phát hiện cả hai. Nếu ứng dụng tự cấu hình scan, hãy bảo đảm các lớp configuration này được import hoặc nằm trong phạm vi scan.

## 11. Cấu hình Spring Boot khi có nhiều ConnectionFactory

Spring Boot có thể tự cấu hình một số thành phần R2DBC khi ứng dụng có một ConnectionFactory phù hợp và không có bean tùy chỉnh làm điều kiện auto-configuration thay đổi.

Khi ứng dụng tự khai báo nhiều ConnectionFactory, không nên dựa vào auto-configuration một nguồn dữ liệu để tự suy luận tất cả template và repository. Hãy khai báo tường minh các bean cần cho từng nguồn:

- ConnectionFactory.
- DatabaseClient nếu cần SQL trực tiếp.
- R2dbcEntityTemplate cho repository/entity operations.
- Repository scanning riêng.
- Reactive transaction manager.
- TransactionalOperator nếu dùng programmatic transaction.

Các điều kiện auto-configuration và bean mặc định có thể khác theo phiên bản Spring Boot. Hãy kiểm tra điều kiện bean của phiên bản ứng dụng, đặc biệt khi thêm ConnectionFactory bean tùy chỉnh.

### 11.1. Không tạo hai bean mặc định cùng tên

Nếu auto-configuration đã tạo bean mặc định như connectionFactory hoặc r2dbcEntityTemplate, đừng khai báo một bean khác cùng tên với ý định ghi đè ngầm.

Hãy chọn một chiến lược nhất quán:

- Dùng auto-configuration cho nguồn dữ liệu chính và khai báo nguồn phụ với tên riêng, nếu phiên bản và điều kiện auto-configuration cho phép.
- Hoặc tự cấu hình tất cả nguồn dữ liệu với tên riêng và định tuyến repository rõ ràng.

Không phụ thuộc vào việc bean override được bật hay không. Bean overriding có thể bị tắt và việc ghi đè ngầm khiến cấu hình khó hiểu.

### 11.2. Kiểm tra auto-configured DatabaseClient

Nếu có nhiều ConnectionFactory, injection một DatabaseClient mặc định có thể trở nên mơ hồ hoặc không còn phù hợp với điều kiện auto-configuration.

Hãy tạo DatabaseClient riêng cho từng ConnectionFactory và inject bằng qualifier. Điều này làm rõ database mà SQL trực tiếp sẽ sử dụng.

### 11.3. Cấu hình schema initialization và migration

Có nhiều database nghĩa là có nhiều schema cần được tạo hoặc cập nhật. Một migration tool có thể cần một cấu hình connection riêng cho từng database.

Không giả định migration chạy cho database chính cũng sẽ chạy cho database phụ. Hãy khai báo migration location, datasource/connection và thứ tự triển khai rõ ràng theo công cụ mà dự án dùng.

Ứng dụng chỉ nên khởi động repository sau khi schema tương ứng sẵn sàng. Nếu database phụ không khả dụng, hãy quyết định rõ ứng dụng có thể hoạt động ở chế độ suy giảm hay phải fail-fast.

## 12. Connection pool cho từng ConnectionFactory

Trong môi trường production, ứng dụng thường dùng connection pool thay vì tạo kết nối vật lý mới cho từng thao tác.

R2DBC Pool cung cấp ConnectionPool bao bọc ConnectionFactory:

~~~java
ConnectionPoolConfiguration poolConfiguration =
    ConnectionPoolConfiguration.builder(connectionFactory)
        .initialSize(2)
        .maxSize(10)
        .build();

ConnectionPool pool = new ConnectionPool(poolConfiguration);
~~~

Ví dụ chỉ minh họa cấu trúc tạo pool. Cần có dependency R2DBC Pool và cấu hình timeout, validation, idle time, max life phù hợp với phiên bản thư viện.

Với nhiều database, mỗi pool có giới hạn riêng:

- orders pool có max size riêng.
- audit pool có max size riêng.
- Tổng connection có thể mở tới tất cả database là tổng giới hạn của các pool.
- Tăng pool size ở một database không tự giải quyết thiếu connection ở database khác.

Nếu khai báo pool dưới dạng bean, hãy quản lý vòng đời đóng pool khi ứng dụng dừng theo API của phiên bản R2DBC Pool đang dùng. Không tạo pool mới cho từng request hoặc mỗi lần gọi service.

### 12.1. Tính tổng connection

Giả sử:

| Database | Max pool size |
|---|---:|
| Orders | 20 |
| Audit | 8 |
| Reporting | 12 |
| Tổng | 40 |

Một instance ứng dụng có thể mở tối đa khoảng 40 connection qua ba pool khi tất cả đạt giới hạn. Nếu chạy 4 instance, tổng số connection tiềm năng tới database có thể cao hơn nhiều.

Hãy tính giới hạn dựa trên số instance, giới hạn connection của database, số ứng dụng khác và workload thực tế.

### 12.2. Không chia sẻ một pool cho hai database khác nhau

ConnectionPool bao bọc một ConnectionFactory cụ thể. Nếu hai database có URL hoặc credentials khác nhau, cần hai factory và hai pool riêng.

Không lấy một pool rồi đổi database theo request. Database/session state trên connection có thể bị rò rỉ giữa các request và gây sai dữ liệu hoặc vấn đề bảo mật.

## 13. Chọn đúng repository và database trong service

Sau khi định tuyến repository, service có thể inject repository theo package/module tương ứng.

Orders repository:

~~~java
package com.example.orders.repository;

public interface OrderRepository
        extends ReactiveCrudRepository<Order, Long> {
}
~~~

Audit repository:

~~~java
package com.example.audit.repository;

public interface AuditRepository
        extends ReactiveCrudRepository<AuditEvent, Long> {
}
~~~

Service nghiệp vụ orders:

~~~java
@Service
public class OrderService {

    private final OrderRepository orderRepository;

    public OrderService(OrderRepository orderRepository) {
        this.orderRepository = orderRepository;
    }

    @Transactional(transactionManager = "ordersTransactionManager")
    public Mono<Order> confirm(Long orderId) {
        return orderRepository.findById(orderId)
            .switchIfEmpty(Mono.error(
                new OrderNotFoundException(orderId)
            ))
            .flatMap(order -> {
                order.setStatus("CONFIRMED");
                return orderRepository.save(order);
            });
    }
}
~~~

Service audit:

~~~java
@Service
public class AuditService {

    private final AuditRepository auditRepository;

    public AuditService(AuditRepository auditRepository) {
        this.auditRepository = auditRepository;
    }

    @Transactional(transactionManager = "auditTransactionManager")
    public Mono<AuditEvent> record(Long orderId, String action) {
        return auditRepository.save(
            new AuditEvent(orderId, action)
        );
    }
}
~~~

Mỗi service chọn transaction manager tương ứng với database mà repository của nó sử dụng.

## 14. Một service dùng nhiều database có tạo được một transaction chung không?

Đây là điểm đặc biệt quan trọng.

Giả sử một use case cần:

1. Cập nhật đơn hàng trong orders database.
2. Ghi audit event trong audit database.

Hai database có hai ConnectionFactory và hai R2dbcTransactionManager riêng. Một @Transactional chỉ chọn một transaction manager tại một thời điểm. Nó không tự động tạo transaction phân tán bao trùm cả hai nguồn dữ liệu.

Ví dụ sau không bảo đảm tính nguyên tử giữa hai database:

~~~java
@Transactional(transactionManager = "ordersTransactionManager")
public Mono<Order> confirmAndAudit(Long orderId) {
    return orderRepository.findById(orderId)
        .flatMap(order -> {
            order.setStatus("CONFIRMED");

            return orderRepository.save(order)
                .flatMap(saved ->
                    auditRepository.save(
                        new AuditEvent(saved.getId(), "CONFIRMED")
                    ).thenReturn(saved)
                );
        });
}
~~~

Transaction được chọn là ordersTransactionManager. AuditRepository được định tuyến sang audit database, nhưng điều đó không tự khiến audit thao tác tham gia cùng transaction orders. Audit có thể chạy ngoài transaction đã chọn hoặc theo cơ chế transaction khác tùy cấu hình.

Có thể tạo hai transaction riêng trong một pipeline, nhưng chúng vẫn là hai transaction độc lập. Nếu transaction orders commit rồi transaction audit thất bại, dữ liệu orders không tự rollback theo audit.

### 14.1. Không nhầm nhiều transaction manager với distributed transaction

Khai báo nhiều R2dbcTransactionManager chỉ tạo khả năng quản lý transaction độc lập trên từng ConnectionFactory.

Nó không tự cung cấp:

- Một commit nguyên tử trên nhiều database.
- Rollback tất cả database nếu một database lỗi.
- Điều phối hai connection theo giao thức commit phân tán.
- Khôi phục tự động một side effect đã commit ở database khác.

Không nên gắn hai manager vào cùng một annotation rồi kỳ vọng Spring tự phối hợp chúng thành một transaction toàn cục.

### 14.2. Transactional outbox

Nếu cập nhật order và ghi nhận việc cần phát audit/message phải nguyên tử, có thể lưu outbox record cùng orders transaction:

~~~java
@Transactional(transactionManager = "ordersTransactionManager")
public Mono<Order> confirmOrder(Long orderId) {
    return orderRepository.findById(orderId)
        .switchIfEmpty(Mono.error(new OrderNotFoundException(orderId)))
        .flatMap(order -> {
            order.setStatus("CONFIRMED");

            return orderRepository.save(order)
                .flatMap(saved ->
                    outboxRepository.save(
                        OutboxEvent.orderConfirmed(saved.getId())
                    ).thenReturn(saved)
                );
        });
}
~~~

Sau khi transaction orders commit, worker đọc outbox và ghi sang audit database hoặc gửi message. Worker cần xử lý retry, idempotency và trạng thái gửi.

Outbox bảo đảm thay đổi order và yêu cầu xử lý tiếp theo được ghi cùng một database transaction. Nó không tạo transaction phân tán; nó cung cấp một cơ chế bền vững để tiếp tục xử lý sau commit.

### 14.3. Saga và hành động bù

Với quy trình nghiệp vụ nhiều bước trên nhiều database, có thể dùng saga:

1. Ghi trạng thái ban đầu ở orders database.
2. Gửi command hoặc event để audit/reporting xử lý.
3. Nhận xác nhận từ bước tiếp theo.
4. Tiến tới trạng thái cuối.
5. Nếu bước sau thất bại, chạy hành động bù phù hợp.

Hành động bù là logic nghiệp vụ, không phải rollback ACID. Cần thiết kế trạng thái, retry, idempotency và khả năng xử lý sự kiện đến trễ.

## 15. Khi cần truy vấn dữ liệu từ hai database

Một SQL JOIN thông thường chỉ chạy trong database mà connection đang kết nối tới. DatabaseClient gắn với ordersConnectionFactory không tự JOIN được bảng trong audit database ở một server khác.

Nếu cần kết hợp dữ liệu từ hai database, có một số lựa chọn:

- Đọc từng nguồn bằng DatabaseClient/repository riêng rồi ghép trong reactive pipeline.
- Đồng bộ dữ liệu cần truy vấn sang một reporting database.
- Dùng database federation hoặc foreign data wrapper nếu hệ quản trị hỗ trợ và được quản trị phù hợp.
- Xây dựng read model tổng hợp được cập nhật bất đồng bộ.

Ví dụ ghép hai nguồn bằng reactive pipeline:

~~~java
public Mono<OrderAuditView> loadOrderAndAudit(Long orderId) {
    Mono<Order> order =
        orderRepository.findById(orderId);

    Mono<List<AuditEvent>> events =
        auditRepository.findByOrderId(orderId)
            .collectList();

    return Mono.zip(order, events)
        .map(tuple -> new OrderAuditView(
            tuple.getT1(),
            tuple.getT2()
        ));
}
~~~

Hai publisher có thể được subscribe đồng thời bởi Mono.zip. Mỗi repository sử dụng template/ConnectionFactory riêng đã được định tuyến.

Nếu yêu cầu dữ liệu nhất quán tại cùng một thời điểm trên hai database, việc đọc đồng thời không tự cung cấp snapshot phân tán. Hãy xác định mức độ nhất quán nghiệp vụ cần thiết và chấp nhận hoặc giải quyết độ lệch dữ liệu.

### 15.1. Không giả định một repository có thể dùng hai template tùy từng method

Một repository interface được đăng ký với một entityOperationsRef. Nếu các method cần truy cập hai database, hãy tách repository theo nguồn dữ liệu hoặc dùng hai component truy cập dữ liệu riêng.

Không cố định tuyến một method dựa trên tham số database name trong repository nếu hạ tầng không được thiết kế cho việc đó. Tách repository giúp mỗi interface có một nguồn dữ liệu xác định.

## 16. Mapping context, converter và auditing khi có nhiều template

Mỗi R2dbcEntityTemplate có cấu hình mapping và conversion liên quan. Khi hai database dùng schema hoặc kiểu dữ liệu khác nhau, có thể cần cấu hình riêng:

- Naming strategy.
- Custom converters.
- Mapping context.
- Dialect.
- Auditing configuration.
- Entity type và schema tương ứng.

Ví dụ, orders database lưu trạng thái bằng mã chuỗi trong khi audit database lưu mã số. Không nên giả định converter của template này tự áp dụng cho template khác.

Hãy đặt converter theo nguồn dữ liệu và đăng ký trong R2dbcCustomConversions tương ứng. Khi dùng cấu hình tự động, kiểm tra template đang dùng conversion service nào.

### 16.1. Auditing theo từng nguồn dữ liệu

Nếu cả hai database cần auditing, hãy xác định cách callback/auditing được đăng ký cho từng mapping context và loại entity. Không chỉ bật một cấu hình rồi giả định mọi template tùy chỉnh đều sử dụng cùng auditor và mapping context nếu bạn đã tự tạo chúng.

Auditor có thể dùng reactive security context chung, nhưng các trường auditing và schema vẫn cần tương thích ở từng database.

### 16.2. Naming strategy và table mapping

Cùng một lớp Java có thể được dùng ở hai database nhưng bảng/cột khác nhau. Tuy nhiên, việc dùng chung entity cho nhiều schema khác nhau có thể làm mapping khó hiểu.

Nếu cấu trúc khác nhau, hãy cân nhắc tách entity hoặc cấu hình mapping riêng thay vì dựa vào một bộ @Table/@Column duy nhất cho cả hai schema.

## 17. Kiểm thử cấu hình nhiều database

Cấu hình nhiều ConnectionFactory cần được kiểm tra bằng integration test với database thực tế hoặc container tương ứng.

### 17.1. Kiểm tra bean wiring

Có thể kiểm tra ApplicationContext có đủ bean và đúng tên:

~~~java
assertThat(context.getBean("ordersConnectionFactory"))
    .isInstanceOf(ConnectionFactory.class);

assertThat(context.getBean("auditConnectionFactory"))
    .isInstanceOf(ConnectionFactory.class);
~~~

Đây chỉ là kiểm tra wiring. Nó chưa chứng minh hai bean kết nối tới hai database khác nhau.

### 17.2. Kiểm tra repository routing

Tạo dữ liệu có dấu hiệu phân biệt trong mỗi database:

- Orders database có một Order ID cụ thể.
- Audit database có một AuditEvent ID riêng.

Gọi từng repository và xác nhận nó chỉ nhìn thấy dữ liệu từ nguồn đã cấu hình. Điều này giúp phát hiện repository package bị scan nhầm hoặc entityOperationsRef sai.

### 17.3. Kiểm tra DatabaseClient routing

Dùng mỗi DatabaseClient thực hiện một truy vấn xác nhận tên database/schema hoặc đọc một bảng chỉ tồn tại trong nguồn tương ứng.

Không chỉ kiểm tra bean được inject. Hãy xác nhận SQL thực sự được gửi tới database dự định.

### 17.4. Kiểm tra transaction manager

Thực hiện một thao tác ghi rồi phát lỗi trong cùng publisher. Xác nhận transaction manager tương ứng rollback dữ liệu trên đúng database.

Kiểm tra thêm rằng transaction của orders không vô tình được coi là transaction của audit. Hai nguồn dữ liệu cần có test riêng.

### 17.5. Kiểm tra migration và startup

Trong môi trường test, xác nhận:

- Schema orders đã được tạo.
- Schema audit đã được tạo.
- Repository tương ứng khởi tạo được.
- Cả hai ConnectionFactory có thể kết nối.
- Một database không khả dụng được xử lý theo chính sách startup đã chọn.
- Không có bean injection mơ hồ.

## 18. Các lỗi thường gặp

| Lỗi hoặc nhầm lẫn | Nguyên nhân | Cách xử lý |
|---|---|---|
| NoUniqueBeanDefinitionException cho ConnectionFactory | Có nhiều bean cùng kiểu nhưng injection không có qualifier/primary | Dùng @Qualifier hoặc một @Primary có chủ đích |
| Repository truy vấn nhầm database | Repository package gắn sai entityOperationsRef | Kiểm tra @EnableR2dbcRepositories và tên template |
| Không tìm thấy bean trong entityOperationsRef | Tên bean không khớp hoặc template chưa được tạo | Đồng bộ bean name và cấu hình |
| Hai cấu hình quét cùng package | Repository bị đăng ký trùng hoặc định tuyến không rõ | Tách package repository không chồng lấn |
| DatabaseClient dùng sai nguồn | Inject bean mặc định hoặc tạo client từ factory sai | Tạo client riêng và dùng qualifier |
| @Transactional dùng sai manager | Không chỉ định transaction manager khi có nhiều manager | Chọn tên manager rõ ràng |
| Nghĩ entityOperationsRef chọn transaction manager | Nhầm routing repository với routing transaction | Cấu hình hai việc độc lập |
| Nghĩ hai manager tạo transaction phân tán | Mỗi manager quản lý một ConnectionFactory | Dùng outbox/saga hoặc giải pháp phân tán được thiết kế riêng |
| Boot tự tạo mọi ConnectionFactory từ app.r2dbc.* | Thuộc tính tùy chỉnh chưa được bind/configure | Viết cấu hình tạo từng bean |
| Bean auto-config và bean thủ công trùng tên | Dựa vào override ngầm | Chọn chiến lược auto-config hoặc custom rõ ràng |
| Dùng một pool cho nhiều database | ConnectionFactory không tương ứng nguồn dữ liệu | Tạo pool riêng cho từng factory |
| Migration chỉ chạy database chính | Chỉ cấu hình một nguồn migration | Cấu hình migration riêng cho từng database |
| Một repository cần truy cập hai database | Repository chỉ gắn một entityOperationsRef | Tách repository hoặc query component theo nguồn |
| JOIN trực tiếp giữa hai database khác server | Một connection chỉ chạy SQL trong phạm vi database/dialect của nó | Ghép reactive result hoặc xây read model/federation |
| Converter của database này áp dụng nhầm database khác | Mapping/conversion configuration không được tách rõ | Cấu hình converter cho từng template |

## 19. Quy trình khai báo nhiều ConnectionFactory

Khi thêm database thứ hai hoặc thứ ba, hãy làm theo trình tự:

1. Xác định mục đích và quyền sở hữu dữ liệu của từng database.
2. Đặt prefix cấu hình riêng cho từng nguồn, ví dụ app.r2dbc.orders và app.r2dbc.audit.
3. Tạo một ConnectionFactory bean cho mỗi database.
4. Đặt tên bean theo nguồn dữ liệu và dùng qualifier ở mọi điểm inject mơ hồ.
5. Chỉ dùng @Primary nếu thực sự có một nguồn mặc định.
6. Tạo DatabaseClient riêng nếu nguồn đó cần SQL trực tiếp.
7. Tạo R2dbcEntityTemplate riêng cho repository/entity mapping.
8. Tách package repository theo nguồn dữ liệu.
9. Dùng @EnableR2dbcRepositories với basePackages và entityOperationsRef tương ứng cho từng package.
10. Tạo R2dbcTransactionManager riêng cho mỗi ConnectionFactory.
11. Chọn transaction manager rõ ràng bằng @Transactional hoặc TransactionalOperator.
12. Cấu hình pool, timeout, converter, dialect và auditing riêng khi cần.
13. Cấu hình migration cho từng schema.
14. Kiểm thử repository, client, transaction và routing bằng database thực tế.
15. Nếu một use case ghi nhiều database, thiết kế outbox/saga thay vì giả định có một transaction nguyên tử.

## 20. Bài tập tự kiểm tra

### Bài 1: Đặt tên bean

Ứng dụng có orders và audit database. Hãy đặt tên cho hai ConnectionFactory và hai R2dbcEntityTemplate.

Gợi ý:

~~~text
ordersConnectionFactory
ordersEntityTemplate
auditConnectionFactory
auditEntityTemplate
~~~

### Bài 2: Giải quyết injection mơ hồ

Constructor cần audit ConnectionFactory nhưng ứng dụng có hai bean cùng kiểu. Cần thêm gì?

Gợi ý:

~~~java
public AuditService(
    @Qualifier("auditConnectionFactory")
    ConnectionFactory connectionFactory
) {
    this.connectionFactory = connectionFactory;
}
~~~

### Bài 3: Định tuyến repository

Repository trong package com.example.audit.repository cần dùng auditEntityTemplate. Hãy khai báo annotation.

Gợi ý:

~~~java
@EnableR2dbcRepositories(
    basePackages = "com.example.audit.repository",
    entityOperationsRef = "auditEntityTemplate"
)
~~~

### Bài 4: Chọn transaction manager

Một method chỉ cập nhật orders database. Hãy chỉ định transaction manager.

Gợi ý:

~~~java
@Transactional(transactionManager = "ordersTransactionManager")
public Mono<Order> updateOrder(Long id) {
    // ...
}
~~~

### Bài 5: Hai database và một transaction

Một service cập nhật orders rồi ghi audit bằng hai repository. @Transactional của ordersTransactionManager có bảo đảm cả hai database rollback cùng nhau không?

Gợi ý: Không. Manager đó quản lý transaction trên ConnectionFactory của orders. Audit database có transaction độc lập hoặc không tham gia transaction đó. Dùng outbox/saga nếu cần phối hợp đáng tin cậy.

### Bài 6: DatabaseClient

Một câu SQL INSERT vào audit_events cần chạy trên audit database. Service nên inject bean nào?

Gợi ý: auditDatabaseClient với @Qualifier("auditDatabaseClient").

### Bài 7: Primary

Nếu ordersConnectionFactory được đánh dấu @Primary, có thể bỏ mọi @Qualifier trong ứng dụng không?

Gợi ý: Không. @Primary chỉ chọn ứng viên mặc định ở injection point không chỉ định qualifier. Các thao tác audit vẫn cần chọn audit bean rõ ràng.

### Bài 8: Migration

Ứng dụng thêm audit database nhưng migration chỉ chạy cho orders database. Điều gì cần làm?

Gợi ý: Cấu hình migration riêng cho audit database và xác nhận schema audit sẵn sàng trước khi repository hoạt động.

## 21. Ghi nhớ

- Mỗi database R2DBC cần một ConnectionFactory riêng.
- Đặt tên bean theo nguồn dữ liệu, ví dụ ordersConnectionFactory và auditConnectionFactory.
- Dùng @Qualifier để inject đúng bean khi có nhiều ứng viên cùng kiểu.
- @Primary chỉ cung cấp ứng viên mặc định; không thay thế định tuyến repository và transaction.
- Tạo DatabaseClient riêng cho từng ConnectionFactory nếu cần SQL trực tiếp.
- Tạo R2dbcEntityTemplate riêng cho từng nguồn dữ liệu.
- Dùng @EnableR2dbcRepositories với basePackages và entityOperationsRef để gắn repository package với đúng template.
- entityOperationsRef không chọn transaction manager.
- Tạo R2dbcTransactionManager riêng cho từng ConnectionFactory.
- Chỉ định transaction manager bằng @Transactional(transactionManager = "...") hoặc TransactionalOperator tương ứng.
- Cấu hình converter, dialect, auditing, pool và migration theo từng database khi cần.
- Một transaction manager không tự quản lý nhiều database; nhiều manager cũng không tự tạo distributed transaction.
- Với use case cần phối hợp nhiều database, cân nhắc outbox, saga và idempotency.
- Một DatabaseClient chỉ truy vấn nguồn dữ liệu mà ConnectionFactory của nó kết nối tới; JOIN hai database độc lập cần giải pháp khác.
- Kiểm thử bean wiring, repository routing, SQL routing và rollback trên từng database.

Khi khai báo nhiều ConnectionFactory, hãy đặt tên rõ ràng và nối từng nguồn dữ liệu với DatabaseClient, R2dbcEntityTemplate, repository package và transaction manager tương ứng. Qualifier giúp chọn đúng bean, entityOperationsRef giúp định tuyến repository, còn transaction manager xác định phạm vi commit/rollback. Ba quyết định này cần được cấu hình riêng và kiểm thử cùng nhau để tránh thao tác nhầm database hoặc hiểu sai tính nguyên tử giữa nhiều nguồn dữ liệu.

