# Khi nào cần nhiều DataSource trong một ứng dụng

## 1. DataSource là gì và khi nào cần nhiều hơn một?

`DataSource` là nguồn kết nối JDBC tới database. Trong ứng dụng Spring Data JPA thông thường, một `DataSource` cấp connection cho một `EntityManagerFactory`; factory này quản lý persistence unit, mapping Entity và các repository tương ứng.

Một ứng dụng có thể cần nhiều DataSource khi phải làm việc với các database độc lập, ví dụ:

- Database nghiệp vụ chính và database báo cáo/analytics.
- Database đơn hàng và database kế toán do hai hệ thống sở hữu.
- Database legacy cần truy cập trong giai đoạn chuyển đổi.
- Các database tách biệt theo bounded context hoặc yêu cầu bảo mật.
- Một database ghi chính và một read replica, nếu kiến trúc có chính sách định tuyến đọc/ghi rõ ràng.

Không nên thêm DataSource chỉ vì có nhiều bảng hoặc nhiều schema. Nếu các bảng cùng database, cùng transaction boundary và dùng chung mapping, một DataSource với một persistence unit thường đơn giản hơn. Nhiều DataSource kéo theo nhiều connection pool, EntityManagerFactory, transaction manager, migration và quy tắc vận hành.

## 2. Phân biệt nhiều schema, nhiều database và nhiều persistence unit

Ba khái niệm liên quan nhưng không đồng nghĩa:

| Khái niệm | Ý nghĩa | Cách thường triển khai |
| --- | --- | --- |
| Nhiều schema trong một database | Các nhóm bảng nằm ở schema khác nhau nhưng cùng database/connection | Một DataSource; mapping schema hoặc dùng tên bảng/schema phù hợp |
| Nhiều database | Các database có endpoint, credentials hoặc transaction riêng | Thường cần một DataSource cho mỗi database |
| Nhiều persistence unit | Các nhóm Entity có cấu hình/provider/lifecycle riêng | Mỗi persistence unit có EntityManagerFactory riêng; có thể dùng DataSource riêng hoặc dùng chung tùy kiến trúc |

Nếu chỉ cần truy cập `sales.customer` và `sales.order` trong cùng database, không nhất thiết phải tạo hai DataSource. Có thể map schema trong `@Table(schema = "sales")` hoặc cấu hình default schema tùy provider.

Nếu hai nhóm Entity cần transaction độc lập, cấu hình Hibernate khác nhau, hoặc database khác nhau, tách persistence unit sẽ làm ranh giới rõ ràng hơn.

## 3. Mỗi DataSource JPA thường đi cùng một bộ thành phần

Với hai database độc lập, cấu trúc phổ biến là:

```text
Orders database
   |
ordersDataSource
   |
ordersEntityManagerFactory
   |
ordersTransactionManager
   |
Order repositories + Order entities

Analytics database
   |
analyticsDataSource
   |
analyticsEntityManagerFactory
   |
analyticsTransactionManager
   |
Analytics repositories + Analytics entities
```

Mỗi `EntityManagerFactory` quản lý một persistence unit và tập Entity riêng. Mỗi nhóm repository phải được gắn với đúng factory và transaction manager. Việc tách này tránh repository của database A vô tình dùng connection hoặc transaction của database B.

Với cấu hình hai DataSource cố định, không nên để hai repository package bị scan lẫn nhau. Dùng `@EnableJpaRepositories` để chỉ rõ package, `entityManagerFactoryRef` và `transactionManagerRef`.

## 4. Cấu hình properties cho hai DataSource

Ví dụ `application.yml` với hai pool Hikari:

```yaml
app:
  datasource:
    orders:
      url: jdbc:postgresql://localhost:5432/orders_db
      username: orders_app
      password: ${ORDERS_DB_PASSWORD}
      driver-class-name: org.postgresql.Driver
      configuration:
        maximum-pool-size: 12
        minimum-idle: 2
    analytics:
      url: jdbc:postgresql://localhost:5432/analytics_db
      username: analytics_app
      password: ${ANALYTICS_DB_PASSWORD}
      driver-class-name: org.postgresql.Driver
      configuration:
        maximum-pool-size: 6
        minimum-idle: 1
```

Đưa credentials vào environment/secret manager thay vì commit mật khẩu thật vào source control. Tên URL và database trong ví dụ chỉ là minh họa.

`DataSourceProperties` giúp bind URL, username, password và driver. Sau đó `initializeDataSourceBuilder()` tạo pool cụ thể; `@ConfigurationProperties` trên bean Hikari bind các tùy chọn pool dưới `configuration`.

## 5. Tạo DataSource và EntityManagerFactory cho database orders

Ví dụ dùng Spring Boot 3+, Jakarta Persistence và HikariCP. Đặt cấu hình trong package cấu hình của ứng dụng; các import thông thường được lược để tập trung vào wiring:

```java
@Configuration
@EnableJpaRepositories(
    basePackageClasses = OrderRepository.class,
    entityManagerFactoryRef = "ordersEntityManagerFactory",
    transactionManagerRef = "ordersTransactionManager"
)
public class OrdersJpaConfiguration {

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
            @Qualifier("ordersDataSourceProperties") DataSourceProperties properties) {
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
            .properties(Map.of("hibernate.hbm2ddl.auto", "validate"))
            .build();
    }

    @Bean
    @Primary
    public PlatformTransactionManager ordersTransactionManager(
            @Qualifier("ordersEntityManagerFactory") EntityManagerFactory entityManagerFactory) {
        return new JpaTransactionManager(entityManagerFactory);
    }
}
```

`basePackageClasses = OrderRepository.class` yêu cầu Spring scan package chứa repository marker này. `.packages(Order.class)` giới hạn Entity scan cho persistence unit orders. Nếu có nhiều package Entity, liệt kê các class marker tương ứng.

`@Primary` đánh dấu bộ orders làm lựa chọn mặc định khi một dependency cần bean cùng kiểu mà không có qualifier. Đây chỉ là lựa chọn mặc định cho injection/transaction selection; nó không kết hợp transaction giữa hai database.

`EntityManagerFactoryBuilder` thường được Spring Boot cung cấp khi dùng JPA auto-configuration. Khi tự tạo nhiều factory, cần kiểm tra cấu hình Boot của phiên bản dự án và tránh tạo thêm một EntityManagerFactory mặc định ngoài ý muốn.

## 6. Tạo bộ cấu hình cho database analytics

Database thứ hai có cấu hình riêng và không đánh dấu `@Primary`:

```java
@Configuration
@EnableJpaRepositories(
    basePackageClasses = AnalyticsRepository.class,
    entityManagerFactoryRef = "analyticsEntityManagerFactory",
    transactionManagerRef = "analyticsTransactionManager"
)
public class AnalyticsJpaConfiguration {

    @Bean
    @ConfigurationProperties("app.datasource.analytics")
    public DataSourceProperties analyticsDataSourceProperties() {
        return new DataSourceProperties();
    }

    @Bean
    @ConfigurationProperties("app.datasource.analytics.configuration")
    public HikariDataSource analyticsDataSource(
            @Qualifier("analyticsDataSourceProperties") DataSourceProperties properties) {
        return properties.initializeDataSourceBuilder()
            .type(HikariDataSource.class)
            .build();
    }

    @Bean
    public LocalContainerEntityManagerFactoryBean analyticsEntityManagerFactory(
            EntityManagerFactoryBuilder builder,
            @Qualifier("analyticsDataSource") DataSource dataSource) {
        return builder
            .dataSource(dataSource)
            .packages(AnalyticsRecord.class)
            .persistenceUnit("analytics")
            .properties(Map.of("hibernate.hbm2ddl.auto", "validate"))
            .build();
    }

    @Bean
    public PlatformTransactionManager analyticsTransactionManager(
            @Qualifier("analyticsEntityManagerFactory") EntityManagerFactory entityManagerFactory) {
        return new JpaTransactionManager(entityManagerFactory);
    }
}
```

Đảm bảo `OrderRepository` và `AnalyticsRepository` nằm trong các package scan tách biệt. Nếu cùng một repository bị scan bởi cả hai cấu hình, ứng dụng có thể khởi động lỗi hoặc repository được gắn sai persistence unit.

Trong ứng dụng thực tế, có thể trích phần tạo DataSource thành helper/configuration chung để giảm lặp, nhưng vẫn giữ bean name, qualifier, package scan và persistence unit tường minh.

## 7. Entity và repository phải thuộc đúng persistence unit

Ví dụ hai repository:

```java
public interface OrderRepository extends JpaRepository<Order, Long> {
}

public interface AnalyticsRepository extends JpaRepository<AnalyticsRecord, Long> {
}
```

Entity `Order` được scan bởi `.packages(Order.class)` trong orders factory; `AnalyticsRecord` được scan bởi analytics factory. Không đưa cùng một Entity mutable vào hai EntityManagerFactory trừ khi có lý do đặc biệt và đã hiểu rõ hai persistence context độc lập.

Một Entity được quản lý bởi orders EntityManagerFactory không thể được dùng như managed association trực tiếp trong analytics persistence unit. Nếu hai database tham chiếu cùng một business object, lưu ID hoặc business key ở database còn lại và trao đổi qua service/event/API.

JPA association như `@ManyToOne` và `@OneToMany` không tạo join xuyên hai persistence unit/database độc lập. Nếu cần tổng hợp dữ liệu từ cả hai database, đọc riêng rồi ghép ở service, dùng read model, hoặc xây một pipeline đồng bộ phù hợp.

## 8. Chọn đúng transaction manager

Mỗi `JpaTransactionManager` quản lý transaction cho một `EntityManagerFactory`. Khi có nhiều manager, chỉ dựa vào `@Transactional` không qualifier có thể chọn manager `@Primary` hoặc gặp mơ hồ nếu không có primary.

Chỉ rõ transaction manager ở service:

```java
@Service
public class OrderService {
    private final OrderRepository orders;

    public OrderService(OrderRepository orders) {
        this.orders = orders;
    }

    @Transactional(transactionManager = "ordersTransactionManager")
    public Order create(Order order) {
        return orders.save(order);
    }
}
```

Với analytics:

```java
@Service
public class AnalyticsService {
    private final AnalyticsRepository analytics;

    public AnalyticsService(AnalyticsRepository analytics) {
        this.analytics = analytics;
    }

    @Transactional(transactionManager = "analyticsTransactionManager")
    public AnalyticsRecord record(AnalyticsRecord record) {
        return analytics.save(record);
    }
}
```

Transaction annotation cần đặt trên method được gọi qua Spring proxy, thường là public service method. Self-invocation trong cùng object không đi qua proxy nên có thể không kích hoạt transaction như mong đợi.

## 9. Một method gọi hai database có tự động atomic không?

Không. Hai `JpaTransactionManager` cục bộ quản lý hai transaction riêng. `@Transactional("ordersTransactionManager")` không tự mở một transaction atomic bao trùm analytics database.

Ví dụ nếu một service ghi orders rồi gọi analytics repository, thao tác analytics có thể chạy trong transaction riêng theo manager của analytics repository. Analytics có thể commit thành công trong khi transaction orders rollback, hoặc ngược lại. Kết quả là dữ liệu hai database không đồng bộ.

Không nên giả định:

```java
@Transactional("ordersTransactionManager")
public void placeOrder(...) {
    orders.save(...);
    analytics.save(...); // Không tự tham gia transaction orders.
}
```

Đây là ví dụ về một thiết kế không atomic. Nếu cần ghi cả hai database như một đơn vị không thể tách, phải chọn giải pháp transaction phân tán hoặc thiết kế lại workflow.

## 10. Khi nào cần JTA/XA?

JTA với XA-capable resources và transaction manager phù hợp có thể phối hợp transaction qua nhiều resource bằng two-phase commit (2PC). Đây là lựa chọn khi yêu cầu atomic commit xuyên database là bắt buộc và các database/driver/cache resource hỗ trợ XA.

Đổi lại, hệ thống cần:

- XA DataSource/driver và transaction manager hỗ trợ JTA.
- Cấu hình enlist resource và persistence unit tham gia JTA.
- Transaction log/recovery và quy trình xử lý resource bị lỗi giữa 2PC.
- Giám sát transaction in-doubt, timeout, lock và connection usage.
- Kiểm thử failure/recovery trên môi trường gần production.

JTA/XA có chi phí vận hành và có thể làm transaction giữ resource lâu hơn. Không bật XA chỉ vì một request chạm hai repository. Trước tiên xác định có thật sự cần atomicity đồng thời hay có thể dùng eventual consistency.

## 11. Khi nào nên dùng Outbox hoặc Saga?

Nếu một database là nguồn dữ liệu chính và database còn lại là read model/analytics, thường có thể dùng local transaction kết hợp Outbox:

1. Trong transaction của orders database, ghi Order và một Outbox event vào cùng database.
2. Sau commit, worker đọc Outbox và publish event.
3. Consumer cập nhật analytics database trong transaction riêng.
4. Consumer xử lý idempotent để một event được nhận nhiều lần vẫn không tạo dữ liệu sai.
5. Retry và dead-letter handling giúp phục hồi khi analytics database tạm thời không sẵn sàng.

Outbox bảo đảm thay đổi nghiệp vụ và event được ghi cùng local transaction. Việc chuyển event sang database khác diễn ra bất đồng bộ, nên mô hình này là eventual consistency, không phải atomic 2PC.

Với workflow nhiều bước và cần bù trừ khi một bước thất bại, dùng Saga: mỗi bước commit local transaction và có compensating action phù hợp. Bù trừ là hành động nghiệp vụ, không phải rollback vật lý của transaction đã commit.

## 12. Nhiều DataSource cố định khác với Routing DataSource

Nhiều DataSource cố định có nghĩa repository A luôn dùng database A, repository B luôn dùng database B. Đây là cách phù hợp khi các nhóm dữ liệu có ownership rõ ràng.

`AbstractRoutingDataSource` giải quyết tình huống cần chọn một target DataSource theo lookup key, ví dụ tenant hoặc read/write route:

```java
public class TenantRoutingDataSource extends AbstractRoutingDataSource {
    @Override
    protected Object determineCurrentLookupKey() {
        return TenantContext.getCurrentTenant();
    }
}
```

Routing DataSource thường được cấu hình với một tập target DataSource và default target. Với JPA, nó thường đứng phía dưới một DataSource/EntityManagerFactory được dùng chung; route được chọn khi connection được lấy.

Đặt tenant/route context trước khi transaction bắt đầu và bảo đảm luôn clear trong `finally`. Không đổi route giữa một transaction đã lấy connection. Thread-local context cần được truyền đúng qua async/reactive boundary; không giả định nó tự truyền sang thread khác.

Với multi-tenancy phức tạp hoặc tenant-per-database, xem xét Hibernate multi-tenancy support hoặc kiến trúc tenant-aware DataSource chuyên biệt. Routing DataSource không tự giải quyết authorization: server phải xác thực tenant và áp đặt tenant context.

## 13. Read replica và routing đọc/ghi

Một số hệ thống dùng primary database cho write và replica cho read. Có thể dùng routing DataSource, nhưng phải xử lý các giới hạn:

- Replica có thể có replication lag, nên đọc ngay sau write có thể chưa thấy dữ liệu mới.
- Read-your-writes có thể yêu cầu route lần đọc tiếp theo về primary.
- Transaction read-only hint không tự bảo đảm router chọn replica; cần routing policy rõ ràng.
- Một transaction đã lấy connection từ primary không thể an toàn đổi sang replica giữa chừng.
- Health check và failover phải tránh route write tới replica.

Nếu API yêu cầu dữ liệu mới nhất sau thao tác ghi, đừng gửi truy vấn đó sang replica bất đồng bộ trừ khi có cơ chế consistency phù hợp.

## 14. Migration/schema management cho từng database

Mỗi database có schema version và quyền truy cập riêng. Khi dùng Flyway hoặc Liquibase, phải bảo đảm migration chạy trên đúng DataSource:

- Tạo migration location riêng, ví dụ `db/migration/orders` và `db/migration/analytics`.
- Cấu hình migration bean với đúng DataSource nếu ứng dụng có nhiều nguồn.
- Không để migration orders chạy nhầm trên analytics database.
- Dùng user database có quyền tối thiểu cần thiết.
- Kiểm thử migration trên từng database engine/version được triển khai.

Không dựa vào `hibernate.hbm2ddl.auto=update` để đồng bộ schema nhiều database trong production. Thường dùng `validate` hoặc tắt DDL generation, còn thay đổi schema được quản lý bằng migration có version.

## 15. Connection pool và giới hạn tài nguyên

Mỗi Hikari DataSource thường tạo một connection pool riêng. Nếu orders có maximum pool 12 và analytics có maximum pool 6, một instance ứng dụng có thể mở tới khoảng 18 connection từ hai pool, chưa tính connection quản trị, migration hoặc thành phần khác.

Khi chạy nhiều application instance, tổng connection tiềm năng tăng theo số instance. Hãy tính ngân sách connection trên toàn hệ thống so với giới hạn database.

Đặt pool size theo concurrency và capacity database, không đặt lớn chỉ để tránh chờ connection. Theo dõi active/idle/pending connection, acquisition timeout, query latency và connection leak. Dùng tên metric/health indicator khác nhau cho từng pool để biết database nào đang nghẽn.

## 16. Cấu hình Hibernate/JPA riêng cho từng persistence unit

Mỗi EntityManagerFactory có thể có cấu hình riêng:

- Hibernate dialect/provider properties nếu cần.
- DDL mode như `validate`.
- Naming strategy.
- Batch size và JDBC fetch size.
- Second-level cache/region.
- Mapping package và persistence unit name.

Đừng giả định mọi `spring.jpa.*` property mặc định của Boot tự động áp dụng giống nhau cho mọi EntityManagerFactory tự tạo. Với nhiều factory, bind cấu hình riêng theo prefix hoặc truyền vendor properties tường minh cho từng builder.

Giữ timezone, naming strategy, schema và cache policy nhất quán với database tương ứng. Một Entity có thể hoạt động ở persistence unit này nhưng lỗi ở unit kia nếu dialect, converter hoặc schema khác nhau.

## 17. Test nhiều DataSource

Với nhiều persistence unit, `@DataJpaTest` có thể không đủ vì slice test mặc định thường tập trung vào một cấu hình JPA. Có thể dùng `@SpringBootTest` và test database/container riêng cho mỗi DataSource, hoặc import rõ các cấu hình persistence unit cần kiểm tra.

Các test quan trọng:

1. Khởi động context và xác nhận cả hai DataSource/EntityManagerFactory được tạo.
2. Lưu Order qua OrderRepository và xác nhận hàng nằm trong orders database.
3. Lưu AnalyticsRecord qua AnalyticsRepository và xác nhận hàng nằm trong analytics database.
4. Xác nhận repository package được gắn đúng EntityManagerFactory.
5. Kiểm tra `@Transactional("ordersTransactionManager")` rollback orders transaction như mong đợi.
6. Kiểm tra transaction analytics độc lập và chứng minh rollback ở database này không tự rollback database kia.
7. Kiểm tra các Entity không bị quản lý nhầm bởi persistence unit còn lại.
8. Kiểm tra migration chạy trên đúng database.
9. Kiểm tra pool shutdown, health check và connection leak.
10. Nếu dùng XA, kiểm thử commit, rollback, timeout và recovery khi một resource bị lỗi.

Testcontainers với database engine tương thích production thường đáng tin cậy hơn việc chỉ dùng H2, đặc biệt khi có native SQL, dialect, schema hoặc migration riêng.

## 18. Lỗi thường gặp và cách xử lý

**Repository dùng nhầm database.** Kiểm tra `basePackageClasses`, `entityManagerFactoryRef` và `transactionManagerRef` của từng `@EnableJpaRepositories`.

**Spring báo có nhiều DataSource/TransactionManager và không biết chọn bean nào.** Đánh dấu một bộ mặc định bằng `@Primary` khi hợp lý, đồng thời dùng `@Qualifier` và transaction manager name ở nơi cần chỉ rõ.

**Entity không được tìm thấy hoặc `Not a managed type`.** Kiểm tra `.packages(...)` của đúng EntityManagerFactory và package của Entity.

**Repository scan trùng.** Tách package repository hoặc giới hạn scan bằng marker class; không để một interface được đăng ký trong hai cấu hình.

**`@Transactional` chỉ rollback một database.** `JpaTransactionManager` chỉ quản lý một persistence unit. Dùng JTA/XA nếu cần atomicity hoặc Outbox/Saga nếu chấp nhận eventual consistency.

**JPA association không join được Entity ở database khác.** Association không xuyên persistence unit. Trao đổi ID/business key và ghép dữ liệu ở service/read model.

**Đọc từ replica thấy dữ liệu cũ.** Kiểm tra replication lag và route read-your-writes về primary.

**Migration chạy nhầm database.** Gắn Flyway/Liquibase với DataSource cụ thể và dùng location/schema riêng.

**Database hết connection dù từng pool có vẻ nhỏ.** Tính tổng pool trên tất cả instance và thành phần nền; giảm maximum pool hoặc giới hạn concurrency.

## 19. Checklist quyết định có cần nhiều DataSource

- Các bảng có thật sự nằm ở database/endpoint độc lập hay chỉ khác schema?
- Có cần credentials, network boundary, pool hoặc availability riêng không?
- Các Entity có cần persistence unit và cấu hình Hibernate riêng không?
- Repository package đã tách rõ và gắn đúng EntityManagerFactory chưa?
- Mỗi persistence unit có transaction manager được đặt tên rõ chưa?
- Có cần transaction atomic xuyên database không? Nếu có, đã đánh giá JTA/XA chưa?
- Nếu chấp nhận eventual consistency, Outbox/Saga và idempotency đã được thiết kế chưa?
- Có association hoặc join nào đang giả định hai Entity cùng persistence unit không?
- Migration, schema validation, health check và pool metrics có tách theo database không?
- Đã kiểm thử routing, rollback, failure và connection capacity trên môi trường gần production chưa?

## 20. Kết luận

Nhiều DataSource phù hợp khi một ứng dụng thực sự phải truy cập nhiều database độc lập hoặc cần ranh giới kết nối/persistence riêng. Với JPA, mỗi database thường có DataSource, EntityManagerFactory, transaction manager và nhóm repository được cấu hình tường minh. `@Primary` chỉ chọn bean mặc định; nó không hợp nhất transaction.

Trước khi triển khai, hãy xác định ranh giới dữ liệu và transaction. Nếu cần atomic commit xuyên database, đánh giá JTA/XA; nếu có thể chấp nhận cập nhật bất đồng bộ, Outbox hoặc Saga thường phù hợp hơn. Cấu hình rõ repository scan, migration, connection pool và test từng database giúp hệ thống nhiều nguồn dữ liệu dễ vận hành và ít lỗi nhầm lẫn.