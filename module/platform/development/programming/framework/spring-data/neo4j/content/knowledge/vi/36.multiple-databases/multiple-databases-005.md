# Dùng nhiều Driver hoặc transaction manager khi kết nối nhiều hệ thống

## Mục tiêu bài học

Sau bài này, bạn có thể:

- Phân biệt nhiều database trong cùng một Neo4j server với nhiều Neo4j server hoặc endpoint độc lập.
- Quyết định khi nào dùng một `Driver` với `DatabaseSelectionProvider`, khi nào cần nhiều `Driver`.
- Khai báo nhiều bean `Driver`, `Neo4jClient`, `Neo4jTemplate` và `Neo4jTransactionManager` có tên riêng.
- Gắn từng nhóm repository vào đúng template, mapping context và transaction manager.
- Chọn transaction manager bằng `@Transactional` và tránh inject nhầm bean khi có nhiều đối tượng cùng kiểu.
- Hiểu giới hạn atomicity khi một nghiệp vụ ghi vào nhiều database hoặc nhiều hệ thống.
- Nhận biết cấu hình tương ứng cho reactive repository.

## 1. Xác định đúng bài toán trước khi tạo nhiều Driver

Một ứng dụng có thể truy cập nhiều graph database theo các cách khác nhau. Cần phân biệt ba tình huống:

| Tình huống | Cấu hình thường phù hợp |
| --- | --- |
| Nhiều database có tên khác nhau trên cùng một Neo4j server | Một `Driver`; chọn database bằng `spring.data.neo4j.database` hoặc `DatabaseSelectionProvider` |
| Nhiều Neo4j server, cluster, endpoint hoặc bộ thông tin xác thực độc lập | Mỗi endpoint cần một `Driver` riêng; mỗi nhóm repository gắn với client, template và transaction manager tương ứng |
| Neo4j cùng một hệ quản trị khác như PostgreSQL hoặc MongoDB | Dùng transaction manager riêng cho từng công nghệ; xác định rõ ranh giới giao dịch và cách phối hợp |

Không nên tạo thêm Driver chỉ vì một Neo4j server có nhiều database. Driver kết nối tới server/cluster; tên database được chọn ở cấp session hoặc transaction.

Ngược lại, nếu ứng dụng kết nối tới hai Neo4j endpoint độc lập, ví dụ một server chứa catalog và một server chứa dữ liệu đơn hàng, hai Driver giúp mỗi kết nối có URI, credential, pool và vòng đời riêng.

## 2. Khi nào dùng một Driver với nhiều database?

Neo4j hỗ trợ nhiều database trong cùng một DBMS. Nếu toàn bộ repository và template trong ứng dụng dùng một database cố định, có thể cấu hình trong Spring Boot:

```yaml
spring:
  neo4j:
    uri: bolt://neo4j.internal:7687
    authentication:
      username: app
      password: ${NEO4J_PASSWORD}
  data:
    neo4j:
      database: catalog
```

Với cấu hình này, các repository và template của SDN dùng database `catalog`. SDN không tự tạo database; database phải được provision trước bằng công cụ quản trị hoặc migration.

Nếu cần chọn database theo tenant hoặc theo request, có thể cung cấp `DatabaseSelectionProvider` imperative hoặc `ReactiveDatabaseSelectionProvider` reactive. Provider trả về `DatabaseSelection` tương ứng với database cần dùng.

Ví dụ provider chọn database cố định:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.neo4j.core.DatabaseSelection;
import org.springframework.data.neo4j.core.DatabaseSelectionProvider;

@Configuration
class CatalogDatabaseSelectionConfiguration {

    @Bean
    DatabaseSelectionProvider catalogDatabaseSelectionProvider() {
        return () -> DatabaseSelection.byName("catalog");
    }
}
```

Trong cấu hình client và transaction manager tùy chỉnh, cần dùng cùng một provider:

```java
@Bean("catalogClient")
Neo4jClient catalogClient(
        @Qualifier("sharedDriver") Driver driver,
        @Qualifier("catalogDatabaseSelectionProvider")
        DatabaseSelectionProvider selectionProvider) {

    return Neo4jClient.with(driver)
        .withDatabaseSelectionProvider(selectionProvider)
        .build();
}

@Bean("catalogTransactionManager")
Neo4jTransactionManager catalogTransactionManager(
        @Qualifier("sharedDriver") Driver driver,
        @Qualifier("catalogDatabaseSelectionProvider")
        DatabaseSelectionProvider selectionProvider) {

    return new Neo4jTransactionManager(driver, selectionProvider);
}
```

Nếu có repository khác dùng database `orders` trên cùng server, có thể tạo provider, client và transaction manager riêng cho database đó nhưng vẫn dùng chung Driver. Client và transaction manager của cùng một repository group phải nhận cùng provider để database được chọn nhất quán trong transaction.

Database được xác định khi transaction bắt đầu. Không thay đổi lựa chọn database giữa các lời gọi repository trong cùng một transaction. Cũng không trộn entity được tải từ database này với entity được persist sang database khác như thể chúng thuộc cùng một graph.

## 3. Khi nào cần nhiều Driver?

Dùng nhiều Driver khi các kết nối thực sự khác nhau, chẳng hạn:

- Hai Neo4j server có URI khác nhau.
- Hai cluster hoặc môi trường độc lập.
- Hai bộ credential hoặc quyền truy cập tách biệt.
- Một kết nối tới hệ thống production và một kết nối tới hệ thống lưu trữ lịch sử.
- Ứng dụng cần tách pool, timeout, routing hoặc cấu hình TLS theo từng endpoint.

Mỗi Driver quản lý kết nối và connection pool riêng. Driver được thiết kế để dùng lâu dài và chia sẻ giữa các component; không tạo mới Driver cho từng request hoặc từng repository method.

Ví dụ cấu hình hai kết nối:

```yaml
app:
  neo4j:
    catalog:
      uri: ${CATALOG_NEO4J_URI}
      username: ${CATALOG_NEO4J_USERNAME}
      password: ${CATALOG_NEO4J_PASSWORD}
    orders:
      uri: ${ORDERS_NEO4J_URI}
      username: ${ORDERS_NEO4J_USERNAME}
      password: ${ORDERS_NEO4J_PASSWORD}
```

Hai endpoint có thể cùng thuộc một môi trường hoặc nằm ở các hệ thống khác nhau. Tên cấu hình `catalog` và `orders` giúp nhận diện kết nối trong Spring context.

## 4. Khai báo nhiều Driver và hạ tầng SDN

Khi có nhiều bean cùng kiểu `Driver`, không inject theo kiểu đơn thuần nếu Spring không thể xác định bean duy nhất. Dùng `@Qualifier` để chỉ rõ Driver nào được truyền cho client và transaction manager.

Ví dụ dưới đây minh họa hai graph server imperative. Mỗi nhóm có:

- Driver riêng.
- Neo4jClient riêng.
- Neo4jMappingContext riêng.
- Neo4jTransactionManager riêng.
- Neo4jTemplate riêng.

```java
import java.util.Set;

import org.neo4j.driver.AuthTokens;
import org.neo4j.driver.Driver;
import org.neo4j.driver.GraphDatabase;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import org.springframework.data.neo4j.core.Neo4jClient;
import org.springframework.data.neo4j.core.Neo4jTemplate;
import org.springframework.data.neo4j.core.convert.Neo4jConversions;
import org.springframework.data.neo4j.core.mapping.Neo4jMappingContext;
import org.springframework.data.neo4j.core.transaction.Neo4jTransactionManager;

@Configuration(proxyBeanMethods = false)
public class MultiNeo4jInfrastructureConfiguration {

    @Bean(name = "catalogDriver", destroyMethod = "close")
    Driver catalogDriver(
            @Value("${app.neo4j.catalog.uri}") String uri,
            @Value("${app.neo4j.catalog.username}") String username,
            @Value("${app.neo4j.catalog.password}") String password) {

        return GraphDatabase.driver(
            uri,
            AuthTokens.basic(username, password)
        );
    }

    @Bean(name = "ordersDriver", destroyMethod = "close")
    Driver ordersDriver(
            @Value("${app.neo4j.orders.uri}") String uri,
            @Value("${app.neo4j.orders.username}") String username,
            @Value("${app.neo4j.orders.password}") String password) {

        return GraphDatabase.driver(
            uri,
            AuthTokens.basic(username, password)
        );
    }

    @Bean
    Neo4jConversions neo4jConversions() {
        return new Neo4jConversions();
    }

    @Bean("catalogClient")
    Neo4jClient catalogClient(
            @Qualifier("catalogDriver") Driver driver) {

        return Neo4jClient.with(driver).build();
    }

    @Bean("ordersClient")
    Neo4jClient ordersClient(
            @Qualifier("ordersDriver") Driver driver) {

        return Neo4jClient.with(driver).build();
    }

    @Bean("catalogTransactionManager")
    Neo4jTransactionManager catalogTransactionManager(
            @Qualifier("catalogDriver") Driver driver) {

        return new Neo4jTransactionManager(driver);
    }

    @Bean("ordersTransactionManager")
    Neo4jTransactionManager ordersTransactionManager(
            @Qualifier("ordersDriver") Driver driver) {

        return new Neo4jTransactionManager(driver);
    }

    @Bean("catalogMappingContext")
    Neo4jMappingContext catalogMappingContext(
            Neo4jConversions conversions) {

        Neo4jMappingContext context =
            new Neo4jMappingContext(conversions);

        context.setInitialEntitySet(Set.of(
            Product.class,
            Category.class
        ));

        return context;
    }

    @Bean("ordersMappingContext")
    Neo4jMappingContext ordersMappingContext(
            Neo4jConversions conversions) {

        Neo4jMappingContext context =
            new Neo4jMappingContext(conversions);

        context.setInitialEntitySet(Set.of(
            PurchaseOrder.class,
            OrderLine.class
        ));

        return context;
    }

    @Bean("catalogTemplate")
    Neo4jTemplate catalogTemplate(
            @Qualifier("catalogClient") Neo4jClient client,
            @Qualifier("catalogMappingContext")
            Neo4jMappingContext mappingContext,
            @Qualifier("catalogTransactionManager")
            Neo4jTransactionManager transactionManager) {

        return new Neo4jTemplate(
            client,
            mappingContext,
            transactionManager
        );
    }

    @Bean("ordersTemplate")
    Neo4jTemplate ordersTemplate(
            @Qualifier("ordersClient") Neo4jClient client,
            @Qualifier("ordersMappingContext")
            Neo4jMappingContext mappingContext,
            @Qualifier("ordersTransactionManager")
            Neo4jTransactionManager transactionManager) {

        return new Neo4jTemplate(
            client,
            mappingContext,
            transactionManager
        );
    }
}
```

Các entity `Product`, `Category`, `PurchaseOrder` và `OrderLine` là những class domain của ứng dụng, được ánh xạ bằng các annotation SDN tương ứng. Mỗi mapping context nên biết các entity thuộc graph domain mà nó quản lý.

Một số nguyên tắc quan trọng trong cấu hình:

- `catalogClient` và `catalogTransactionManager` phải dùng cùng bean `catalogDriver`.
- `ordersClient` và `ordersTransactionManager` phải dùng cùng bean `ordersDriver`.
- Template phải nhận đúng client, mapping context và transaction manager trong cùng nhóm.
- Không dùng chung một template cho hai Driver khác nhau.
- `Neo4jConversions` có thể được chia sẻ nếu hai graph dùng cùng bộ converter; nếu mapping khác nhau, khai báo converter/context riêng.
- Driver được Spring quản lý vòng đời và đóng khi application context dừng. Không tự đóng Driver sau mỗi truy vấn.

Trong ứng dụng có cấu hình phức tạp hơn, có thể tạo các bean bằng configuration class riêng cho từng hệ thống thay vì gom tất cả vào một class.

## 5. Gắn repository package vào đúng template và transaction manager

Khai báo nhiều Driver thôi chưa đủ. Spring Data cần biết repository nào sử dụng hạ tầng nào.

Dùng nhiều cấu hình `@EnableNeo4jRepositories` và chỉ định ba reference:

- `neo4jTemplateRef`: template thực thi repository.
- `neo4jMappingContextRef`: mapping context chứa metadata entity.
- `transactionManagerRef`: transaction manager điều khiển thao tác repository.

Cấu hình cho catalog:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.data.neo4j.repository.config.EnableNeo4jRepositories;

@Configuration(proxyBeanMethods = false)
@EnableNeo4jRepositories(
    basePackages = "com.example.catalog.repository",
    neo4jTemplateRef = "catalogTemplate",
    neo4jMappingContextRef = "catalogMappingContext",
    transactionManagerRef = "catalogTransactionManager"
)
public class CatalogRepositoryConfiguration {
}
```

Cấu hình cho orders:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.data.neo4j.repository.config.EnableNeo4jRepositories;

@Configuration(proxyBeanMethods = false)
@EnableNeo4jRepositories(
    basePackages = "com.example.orders.repository",
    neo4jTemplateRef = "ordersTemplate",
    neo4jMappingContextRef = "ordersMappingContext",
    transactionManagerRef = "ordersTransactionManager"
)
public class OrdersRepositoryConfiguration {
}
```

Hai package repository phải tách biệt để mỗi repository chỉ được đăng ký bởi một cấu hình. Nếu cùng một repository interface bị quét bởi hai registrar, ứng dụng có thể gặp bean trùng hoặc repository được gắn sai hạ tầng.

Cách tổ chức package gợi ý:

```text
com.example
├── catalog
│   ├── domain
│   └── repository
│       └── ProductRepository.java
└── orders
    ├── domain
    └── repository
        └── PurchaseOrderRepository.java
```

Nhờ các reference rõ ràng, `ProductRepository` luôn dùng catalog graph, còn `PurchaseOrderRepository` luôn dùng orders graph.

## 6. Chọn đúng transaction manager trong service

Khi có nhiều bean `Neo4jTransactionManager`, không nên để `@Transactional` tự chọn một bean theo kiểu mặc định. Chỉ rõ transaction manager cần dùng bằng thuộc tính `transactionManager` hoặc `value`.

Ví dụ service ghi catalog:

```java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class CatalogService {

    private final ProductRepository productRepository;

    public CatalogService(ProductRepository productRepository) {
        this.productRepository = productRepository;
    }

    @Transactional(transactionManager = "catalogTransactionManager")
    public Product renameProduct(String id, String newName) {
        Product product = productRepository.findById(id)
            .orElseThrow();

        product.setName(newName);

        return productRepository.save(product);
    }
}
```

Service ghi orders chọn manager khác:

```java
@Service
public class OrderService {

    private final PurchaseOrderRepository orderRepository;

    public OrderService(PurchaseOrderRepository orderRepository) {
        this.orderRepository = orderRepository;
    }

    @Transactional(transactionManager = "ordersTransactionManager")
    public PurchaseOrder save(PurchaseOrder order) {
        return orderRepository.save(order);
    }
}
```

Tên transaction manager trong annotation phải trùng tên bean đã khai báo. Nếu bỏ qua lựa chọn khi có nhiều transaction manager, Spring có thể báo không xác định được manager hoặc dùng manager mặc định không đúng ý định.

Repository cũng đã được gắn transaction manager qua `transactionManagerRef`. Tuy nhiên, ở service chứa nghiệp vụ ghi rõ ràng, khai báo manager tường minh giúp người đọc biết transaction đang bao phủ graph nào.

## 7. Inject Neo4jClient hoặc Neo4jTemplate trực tiếp

Một service có thể sử dụng client/template thay vì repository. Khi có nhiều bean cùng kiểu, vẫn cần `@Qualifier`.

```java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.data.neo4j.core.Neo4jClient;
import org.springframework.stereotype.Service;

@Service
public class CatalogQueryService {

    private final Neo4jClient catalogClient;

    public CatalogQueryService(
            @Qualifier("catalogClient") Neo4jClient catalogClient) {
        this.catalogClient = catalogClient;
    }

    public long countProducts() {
        return catalogClient
            .query("MATCH (p:Product) RETURN count(p) AS total")
            .fetchAs(Long.class)
            .one()
            .orElse(0L);
    }
}
```

Tương tự, nếu cần thao tác mapping qua template:

```java
@Service
public class OrderGraphService {

    private final Neo4jTemplate ordersTemplate;

    public OrderGraphService(
            @Qualifier("ordersTemplate") Neo4jTemplate ordersTemplate) {
        this.ordersTemplate = ordersTemplate;
    }
}
```

Không inject `Neo4jClient` hoặc `Neo4jTemplate` chỉ theo type khi có nhiều bean cùng kiểu. Việc gắn nhầm client có thể khiến query chạy thành công nhưng đọc hoặc ghi nhầm hệ thống.

## 8. Nhiều database trong cùng server nhưng repository cần database cố định khác nhau

Có một biến thể nằm giữa hai cách trên: cùng một Driver nhưng mỗi nhóm repository luôn dùng một database khác nhau trên cùng server.

Ví dụ:

- `catalog` dùng database `catalog`.
- `orders` dùng database `orders`.

Có thể tạo hai `DatabaseSelectionProvider` riêng, nhưng dùng chung Driver:

```java
@Bean("catalogSelection")
DatabaseSelectionProvider catalogSelection() {
    return () -> DatabaseSelection.byName("catalog");
}

@Bean("ordersSelection")
DatabaseSelectionProvider ordersSelection() {
    return () -> DatabaseSelection.byName("orders");
}
```

Mỗi nhóm tạo client và transaction manager từ cùng Driver và cùng provider tương ứng:

```java
@Bean("catalogClient")
Neo4jClient catalogClient(
        @Qualifier("sharedDriver") Driver driver,
        @Qualifier("catalogSelection")
        DatabaseSelectionProvider selection) {

    return Neo4jClient.with(driver)
        .withDatabaseSelectionProvider(selection)
        .build();
}

@Bean("catalogTransactionManager")
Neo4jTransactionManager catalogTransactionManager(
        @Qualifier("sharedDriver") Driver driver,
        @Qualifier("catalogSelection")
        DatabaseSelectionProvider selection) {

    return new Neo4jTransactionManager(driver, selection);
}
```

Nhóm `orders` được cấu hình tương tự với `ordersSelection`, `ordersClient` và `ordersTransactionManager`.

Cách này tránh tạo thêm connection pool khi chỉ khác tên database. Mỗi repository group vẫn có template và transaction manager riêng để chọn database tương ứng.

## 9. Kết hợp Neo4j với một hệ quản trị khác

Ứng dụng có thể lưu graph trong Neo4j và dữ liệu nghiệp vụ khác trong PostgreSQL, MySQL hoặc một hệ thống khác. Khi đó, Spring thường có nhiều transaction manager, ví dụ:

- `catalogTransactionManager`: transaction của Neo4j catalog.
- `ordersTransactionManager`: transaction của Neo4j orders.
- `transactionManager`: transaction manager của JPA hoặc JDBC, tùy cấu hình.

Một method `@Transactional` chọn một manager cụ thể. Manager đó điều khiển tài nguyên mà nó quản lý; nó không tự động bao trọn mọi database mà service gọi đến.

Ví dụ một service JPA:

```java
@Transactional(transactionManager = "transactionManager")
public void updateCustomer(Customer customer) {
    customerRepository.save(customer);
}
```

Ví dụ service Neo4j:

```java
@Transactional(transactionManager = "catalogTransactionManager")
public Product saveProduct(Product product) {
    return productRepository.save(product);
}
```

Nếu một use case vừa ghi Neo4j vừa ghi PostgreSQL, không nên giả định hai transaction manager độc lập sẽ tự commit hoặc rollback như một transaction phân tán duy nhất. Một transaction có thể commit thành công trong khi transaction còn lại thất bại.

Với nghiệp vụ cần nhất quán giữa nhiều hệ thống, hãy cân nhắc:

- Transactional outbox để ghi sự kiện cùng transaction của một nguồn dữ liệu, sau đó phát sự kiện cho hệ thống còn lại.
- Saga hoặc quy trình bù trừ khi một bước sau thất bại.
- Idempotency key để có thể thực hiện lại thao tác an toàn.
- Tách quy trình thành các bước có trạng thái và có thể khôi phục.

Không dùng transaction manager của Neo4j để cố điều khiển transaction JDBC/JPA. Cũng không xem việc gọi hai service có `@Transactional` khác manager là một cam kết atomicity xuyên database.

## 10. Giới hạn transaction khi ghi vào nhiều Neo4j server

Mỗi `Neo4jTransactionManager` gắn với một Driver và transaction/session thuộc kết nối đó. Nếu một method cần ghi cả catalog server và orders server, hai manager tạo hai local transaction riêng.

Ví dụ luồng:

1. Ghi sản phẩm vào catalog.
2. Ghi tham chiếu sản phẩm vào orders.
3. Bước thứ hai thất bại.

Transaction catalog có thể đã commit trước khi transaction orders thất bại. Spring không tự rollback transaction đã commit trên server thứ nhất.

Nếu nghiệp vụ cần xử lý như một quy trình thống nhất, hãy thiết kế trạng thái trung gian, outbox, retry hoặc compensation. Đừng giữ transaction dài trên một server trong lúc chờ một server khác hoặc API ngoài.

Nếu dữ liệu thực sự cần một transaction ACID chung, cần xem lại ranh giới lưu trữ và kiến trúc. Hai Neo4j server độc lập không trở thành một transaction chung chỉ vì cùng chạy trong một Spring application context.

## 11. Cấu hình reactive với nhiều kết nối

Với reactive SDN, nguyên tắc phân tách vẫn giống imperative, nhưng các kiểu hạ tầng khác nhau:

| Imperative | Reactive |
| --- | --- |
| `Neo4jClient` | `ReactiveNeo4jClient` |
| `Neo4jTemplate` | `ReactiveNeo4jTemplate` |
| `Neo4jTransactionManager` | `ReactiveNeo4jTransactionManager` |
| `@EnableNeo4jRepositories` | `@EnableReactiveNeo4jRepositories` |

`@EnableReactiveNeo4jRepositories` có các thuộc tính `neo4jTemplateRef`, `neo4jMappingContextRef` và `transactionManagerRef`. Các reference cần trỏ tới bean reactive tương ứng.

Ví dụ chọn transaction manager reactive:

```java
@Bean("catalogReactiveTransactionManager")
ReactiveNeo4jTransactionManager catalogReactiveTransactionManager(
        @Qualifier("catalogDriver") Driver driver) {

    return new ReactiveNeo4jTransactionManager(driver);
}
```

Khi dùng reactive repository, method transactional cần trả về `Mono` hoặc `Flux` và sử dụng reactive transaction manager phù hợp:

```java
@Transactional(transactionManager = "catalogReactiveTransactionManager")
public Mono<Product> renameProduct(String id, String newName) {
    return reactiveProductRepository.findById(id)
        .switchIfEmpty(Mono.error(
            new IllegalArgumentException("Product not found")
        ))
        .flatMap(product -> {
            product.setName(newName);
            return reactiveProductRepository.save(product);
        });
}
```

Không dùng `Neo4jTransactionManager` imperative cho reactive repository. Mỗi nhóm repository reactive cũng phải được gắn đúng reactive template và reactive transaction manager.

## 12. Quản lý connection pool và vòng đời Driver

Một Driver duy trì connection pool và được thiết kế để tái sử dụng trong suốt vòng đời ứng dụng. Với nhiều Driver, mỗi Driver có pool và tài nguyên riêng.

Cần chú ý:

- Không tạo Driver trong controller hoặc service method.
- Dùng bean singleton do Spring quản lý.
- Đóng Driver khi application context dừng.
- Cấu hình pool size, connection timeout và retry phù hợp với từng endpoint.
- Theo dõi pool riêng của từng Driver; tổng số connection có thể tăng nhanh khi có nhiều server.
- Dùng secret manager hoặc biến môi trường để cấp credential.
- Chỉ cấp quyền database cần thiết cho từng Driver.
- Đặt tên bean phản ánh hệ thống và mục đích sử dụng.

Không đặt `@Primary` một cách tùy tiện chỉ để giải quyết lỗi nhiều bean cùng type. Nếu có một kết nối mặc định thực sự, có thể đánh dấu nó là primary, nhưng các repository và service vẫn nên dùng reference rõ ràng để tránh nhầm database.

## 13. Kiểm thử cấu hình nhiều database

Kiểm thử tích hợp cần chứng minh repository thực sự kết nối đúng graph. Chỉ xác nhận Spring context khởi động thành công là chưa đủ.

Một số kiểm tra nên có:

1. Khởi tạo hai Neo4j test database hoặc hai test container độc lập.
2. Ghi một node qua repository catalog.
3. Ghi một node khác qua repository orders.
4. Đọc lại qua đúng repository và xác nhận dữ liệu có mặt.
5. Truy vấn nhầm qua repository còn lại và xác nhận không thấy dữ liệu của graph kia.
6. Kiểm tra service dùng `@Transactional` manager đúng bằng cách gây lỗi và xác minh rollback trên đúng database.
7. Kiểm tra Driver được đóng khi context dừng nếu cấu hình vòng đời tùy chỉnh.

Nếu hai database nằm trên cùng một server, có thể dùng hai database name và một Driver với provider riêng. Nếu kiểm thử hai server độc lập, dùng hai test container hoặc endpoint cô lập để xác minh việc phân tách Driver.

## 14. Những lỗi thường gặp

| Lỗi | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Tạo nhiều Driver cho nhiều database trên cùng server mà không cần thiết | Nhầm database name với server endpoint | Dùng một Driver và DatabaseSelectionProvider |
| Nhiều Driver nhưng inject chỉ bằng type | Spring không xác định bean phù hợp | Dùng `@Qualifier` |
| Client và transaction manager dùng hai Driver khác nhau | Tài nguyên transaction không khớp với client | Dùng cùng Driver bean trong một nhóm |
| Hai repository config quét cùng package | Repository bị đăng ký trùng hoặc sai hạ tầng | Tách package và cấu hình basePackages rõ |
| Quên `neo4jTemplateRef` | Repository có thể dùng template mặc định | Trỏ tới template của đúng Driver |
| Quên `transactionManagerRef` | Repository có thể dùng transaction manager mặc định | Chỉ rõ manager theo repository group |
| Mapping context không chứa entity liên quan | SDN không có đủ metadata để mapping graph | Khai báo đầy đủ initial entity set |
| `@Transactional` không chỉ rõ manager | Dùng nhầm manager hoặc gặp lỗi ambiguity | Đặt `transactionManager` rõ ràng |
| Dùng một manager cho hai Driver | Manager chỉ đồng bộ transaction của Driver được cấu hình | Tạo manager riêng cho từng Driver |
| Nghĩ hai manager tạo atomic transaction xuyên server | Các local transaction commit độc lập | Dùng outbox, saga hoặc compensation |
| Dùng imperative manager với reactive repository | Không tương thích execution model | Dùng reactive client/template/manager |
| Tạo Driver mỗi request | Mở nhiều pool, tốn tài nguyên và kết nối | Dùng Driver bean singleton |
| Dùng credential giống nhau cho mọi hệ thống | Quyền truy cập không được tách biệt | Cấp credential tối thiểu cho từng endpoint |
| Database selection thay đổi giữa transaction | Các thao tác có thể trỏ đến graph khác nhau | Chọn database ổn định ở đầu transaction |

## 15. Quy trình thiết kế nhiều kết nối

Khi cần thêm kết nối Neo4j thứ hai, hãy thực hiện theo thứ tự:

1. Xác định đó là database khác trong cùng server hay một endpoint độc lập.
2. Nếu chỉ khác database name, ưu tiên một Driver và database selection.
3. Nếu endpoint/credential/pool độc lập, tạo Driver riêng.
4. Tạo Neo4jClient và Neo4jTransactionManager từ đúng Driver.
5. Tạo mapping context và template cho nhóm entity tương ứng.
6. Tách package repository và cấu hình `@EnableNeo4jRepositories` với đủ reference.
7. Dùng `@Qualifier` trong service và `transactionManager` trong `@Transactional`.
8. Xác định use case nào chỉ ghi một database và use case nào phối hợp nhiều resource.
9. Nếu cần nhất quán xuyên resource, thiết kế outbox/saga hoặc compensation.
10. Kiểm thử đúng endpoint, đúng database, đúng transaction manager và vòng đời Driver.

## 16. Câu hỏi tự kiểm tra

1. Khác biệt giữa nhiều database trong cùng Neo4j server và nhiều Neo4j server là gì?
2. Khi nào chỉ cần một Driver với `DatabaseSelectionProvider`?
3. Vì sao mỗi endpoint độc lập nên có Driver riêng?
4. Những bean SDN nào cần được tạo riêng cho từng Driver?
5. `neo4jTemplateRef` và `transactionManagerRef` trong `@EnableNeo4jRepositories` có vai trò gì?
6. Vì sao cần `@Qualifier` khi có nhiều bean `Driver` hoặc `Neo4jClient`?
7. Làm thế nào chọn đúng transaction manager bằng `@Transactional`?
8. Vì sao client và transaction manager trong một nhóm phải dùng cùng Driver?
9. Một transaction manager có thể điều khiển transaction của hai Driver độc lập không?
10. Vì sao hai local transaction không tự tạo atomic commit xuyên database?
11. Khi nào nên dùng transactional outbox hoặc saga?
12. Reactive repository cần những loại client, template và transaction manager nào?
13. Vì sao không nên tạo Driver mới cho từng request?
14. Những kiểm tra nào chứng minh repository đang truy cập đúng database?

## Tài liệu tham khảo

- [Spring Data Neo4j 8.1 – FAQ: Multiple databases và database selection](https://docs.spring.io/spring-data/neo4j/reference/faq.html)
- [Spring Data Neo4j – EnableNeo4jRepositories API](https://docs.spring.io/spring-data/neo4j/reference/api/java/org/springframework/data/neo4j/repository/config/EnableNeo4jRepositories.html)
- [Spring Data Neo4j – AbstractNeo4jConfig API](https://docs.spring.io/spring-data/neo4j/reference/api/java/org/springframework/data/neo4j/config/AbstractNeo4jConfig.html)
- [Spring Data Neo4j – Neo4jClient API](https://docs.spring.io/spring-data/neo4j/reference/api/java/org/springframework/data/neo4j/core/Neo4jClient.html)
- [Spring Data Neo4j – Neo4jTransactionManager API](https://docs.spring.io/spring-data/neo4j/reference/api/java/org/springframework/data/neo4j/core/transaction/Neo4jTransactionManager.html)
- [Spring Data Neo4j – EnableReactiveNeo4jRepositories API](https://docs.spring.io/spring-data/neo4j/reference/api/java/org/springframework/data/neo4j/repository/config/EnableReactiveNeo4jRepositories.html)
- [Spring Framework – Declarative transaction management](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative.html)

## Kết luận

Khi kết nối nhiều hệ thống, trước tiên hãy phân biệt database khác tên trên cùng Neo4j server với các endpoint độc lập. Một Driver có thể phục vụ nhiều database thông qua database selection; nhiều server hoặc credential độc lập cần các Driver riêng.

Trong SDN, mỗi nhóm repository phải được gắn đúng `Neo4jClient`, `Neo4jTemplate`, mapping context và `Neo4jTransactionManager`. Dùng `@Qualifier`, `neo4jTemplateRef`, `neo4jMappingContextRef`, `transactionManagerRef` và `@Transactional(transactionManager = ...)` để làm rõ lựa chọn. Với reactive, dùng các thành phần reactive tương ứng.

Mỗi transaction manager chỉ điều khiển transaction thuộc tài nguyên nó quản lý. Ghi vào nhiều database hoặc nhiều server không tự trở thành một transaction ACID chung. Hãy thiết kế outbox, saga hoặc compensation khi nghiệp vụ cần phối hợp nhiều resource. Phân tách bean rõ ràng, quản lý Driver lâu dài và kiểm thử đúng endpoint sẽ giúp tránh ghi nhầm dữ liệu và kiểm soát transaction trong ứng dụng Spring Data Neo4j.
