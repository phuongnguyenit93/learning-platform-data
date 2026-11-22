# Nhiều persistence unit gắn với các DataSource khác nhau

## 1. Vì sao cần nhiều persistence unit?

Trong một ứng dụng **Spring Boot Integration**, lớp tích hợp có thể phải đọc và ghi dữ liệu ở nhiều nguồn: cơ sở dữ liệu vận hành chứa đơn hàng, cơ sở dữ liệu phân tích, hoặc một hệ thống kế thừa do đơn vị khác quản lý. Mỗi nguồn có mô hình entity, tài khoản kết nối, schema migration, chính sách transaction và giới hạn hiệu năng riêng. Khi cần dùng **JPA/Hibernate** cho nhiều nguồn trong cùng một ứng dụng, ta có thể cấu hình **nhiều persistence unit**, mỗi unit dùng một `DataSource` và một `EntityManagerFactory` riêng.

Ví dụ trong bài:

- **Orders** dùng PostgreSQL database `orders_db`, chứa `OrderEntity` và `OrderRepository`; đây là nơi nắm giữ trạng thái đơn hàng.
- **Analytics** dùng PostgreSQL database `analytics_db`, chứa `OrderMetricEntity` và `OrderMetricRepository`; đây là bản ghi phân tích hoặc dữ liệu dẫn xuất.

Mục tiêu không chỉ là “kết nối được hai database”. Điều quan trọng hơn là đảm bảo **repository được gắn đúng EntityManagerFactory**, **transaction dùng đúng transaction manager**, **schema được quản lý riêng** và **lỗi của một nguồn không bị hiểu nhầm là rollback đồng thời ở tất cả nguồn**.

## 2. Phân biệt bốn thành phần

| Thành phần | Vai trò | Phạm vi trong ví dụ |
| --- | --- | --- |
| `DataSource` | Cấp kết nối JDBC đến database, thường dùng connection pool như HikariCP. | `ordersDataSource` và `analyticsDataSource` |
| Persistence unit | Tập entity được quản lý cùng cấu hình JPA và tên nhận diện logic. | `ordersPU` và `analyticsPU` |
| `EntityManagerFactory` | Tạo `EntityManager` và quản lý metadata/mapping, persistence context, cấu hình Hibernate cho một unit. | `ordersEntityManagerFactory` và `analyticsEntityManagerFactory` |
| `PlatformTransactionManager` | Mở, commit, rollback transaction tương ứng với tài nguyên; với JPA thường dùng `JpaTransactionManager`. | `ordersTransactionManager` và `analyticsTransactionManager` |

Trong một ứng dụng JPA đơn nguồn, Spring Boot thường tự cấu hình phần lớn các bean này. Khi có **hai nguồn JPA**, cần khai báo rõ các nhóm bean và ánh xạ repository để tránh hành vi phụ thuộc vào bean mặc định.

~~~mermaid
flowchart TB
    subgraph A["Orders persistence unit"]
        OR["OrderRepository"] --> OEM["ordersEntityManagerFactory"]
        OEM --> ODS["ordersDataSource"]
        OTM["ordersTransactionManager"] --> OEM
        ODS --> ODB[("orders_db")]
    end
    subgraph B["Analytics persistence unit"]
        AR["OrderMetricRepository"] --> AEM["analyticsEntityManagerFactory"]
        AEM --> ADS["analyticsDataSource"]
        ATM["analyticsTransactionManager"] --> AEM
        ADS --> ADB[("analytics_db")]
    end
~~~

**Không nhầm lẫn các trường hợp khác nhau:**

1. **Hai database độc lập và hai nhóm entity khác nhau:** hai `DataSource`, hai `EntityManagerFactory` và hai transaction manager thường là cách tổ chức rõ ràng.
2. **Hai schema trong cùng database:** có thể vẫn dùng một persistence unit với `@Table(schema = "...")` nếu cùng nguồn kết nối và transaction; chưa chắc cần hai unit.
3. **Đọc từ replica, ghi vào primary cùng một mô hình entity:** có thể phù hợp hơn với routing `DataSource`/mô hình đọc ghi chuyên biệt. Việc dùng hai unit không tự giải quyết vấn đề replica lag.
4. **Multi-tenant với cùng schema hoặc nhiều tenant cùng model:** cần xem cơ chế multi-tenancy của Hibernate hoặc routing datasource theo tenant; không nên tạo thủ công một persistence unit cho mỗi tenant khi số tenant lớn và biến động.

## 3. Chuẩn bị package, dependency và cấu hình

Ví dụ sử dụng **Spring Boot 3.x, Java 17+, Spring Data JPA và PostgreSQL**; các import JPA thuộc `jakarta.persistence`. Dự án chỉ cần hai nhóm entity/repository và hai lớp cấu hình:

~~~text
com.example.integration
├── IntegrationApplication.java
├── orders
│   ├── entity/OrderEntity.java
│   ├── repository/OrderRepository.java
│   └── config/OrdersJpaConfiguration.java
└── analytics
    ├── entity/OrderMetricEntity.java
    ├── repository/OrderMetricRepository.java
    └── config/AnalyticsJpaConfiguration.java
~~~

Tách package repository rõ ràng là điều kiện quan trọng vì mỗi `@EnableJpaRepositories` sẽ gắn **một tập repository cụ thể** vào đúng persistence unit. Chỉ định entity qua `packages(...)` của builder là việc riêng, không thay thế cấu hình quét repository.

Các dependency Maven:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-data-jpa</artifactId>
    </dependency>
    <dependency>
        <groupId>org.postgresql</groupId>
        <artifactId>postgresql</artifactId>
        <scope>runtime</scope>
    </dependency>
</dependencies>
~~~

Ví dụ `application.yml` dùng hai tiền tố riêng, không đặt mật khẩu trực tiếp vào source:

~~~yaml
app:
  datasource:
    orders:
      url: jdbc:postgresql://localhost:5432/orders_db
      username: ${ORDERS_DB_USER}
      password: ${ORDERS_DB_PASSWORD}
      driver-class-name: org.postgresql.Driver
      configuration:
        maximum-pool-size: 10
        connection-timeout: 3000
    analytics:
      url: jdbc:postgresql://localhost:5432/analytics_db
      username: ${ANALYTICS_DB_USER}
      password: ${ANALYTICS_DB_PASSWORD}
      driver-class-name: org.postgresql.Driver
      configuration:
        maximum-pool-size: 5
        connection-timeout: 3000

spring:
  jpa:
    open-in-view: false
~~~

`DataSourceProperties` sẽ bind các thuộc tính kết nối `url`, `username`, `password`; còn các thuộc tính dưới `configuration` bind lên `HikariDataSource` thực tế. Vì sử dụng tiền tố tùy chỉnh `app.datasource.*`, hãy chắc chắn mã Java bên dưới cũng dùng đúng các tiền tố đó; cấu hình `spring.datasource.*` mặc định không tự sinh cả hai nguồn.

Thông số pool là **ví dụ để đọc hiểu**. Cần tính tổng số connection có thể mở bằng cách cộng pool của **mọi DataSource trên tất cả replica ứng dụng**, rồi đối chiếu giới hạn kết nối của từng database. Đặt timeout cũng cần xem SLA, network và thời gian query.

## 4. Tạo hai nhóm repository và entity riêng biệt

Định nghĩa tối thiểu cho miền Orders (mỗi type đặt ở file Java phù hợp với cấu trúc package):

~~~java
// orders/entity/OrderEntity.java
package com.example.integration.orders.entity;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import java.util.UUID;

@Entity
@Table(name = "orders")
public class OrderEntity {
    @Id
    private UUID id;

    @Column(nullable = false)
    private String status;

    protected OrderEntity() {} // JPA

    public OrderEntity(UUID id, String status) {
        this.id = id;
        this.status = status;
    }

    public UUID getId() { return id; }
    public String getStatus() { return status; }
    public void confirm() { this.status = "CONFIRMED"; }
}
~~~

~~~java
// orders/repository/OrderRepository.java
package com.example.integration.orders.repository;

import com.example.integration.orders.entity.OrderEntity;
import java.util.UUID;
import org.springframework.data.jpa.repository.JpaRepository;

public interface OrderRepository extends JpaRepository<OrderEntity, UUID> {}
~~~

Miền Analytics có các entity và repository riêng:

~~~java
// analytics/entity/OrderMetricEntity.java
package com.example.integration.analytics.entity;

import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import java.util.UUID;

@Entity
@Table(name = "order_metrics")
public class OrderMetricEntity {
    @Id
    private UUID id;
    private long orderCount;

    protected OrderMetricEntity() {}
    public OrderMetricEntity(UUID id, long orderCount) {
        this.id = id;
        this.orderCount = orderCount;
    }
}
~~~

~~~java
// analytics/repository/OrderMetricRepository.java
package com.example.integration.analytics.repository;

import com.example.integration.analytics.entity.OrderMetricEntity;
import java.util.UUID;
import org.springframework.data.jpa.repository.JpaRepository;

public interface OrderMetricRepository
        extends JpaRepository<OrderMetricEntity, UUID> {}
~~~

Chỉ đưa `OrderEntity` vào persistence unit Orders và `OrderMetricEntity` vào unit Analytics. Một mối quan hệ `@ManyToOne`/`@OneToMany` không thể tự tạo phép join JPA xuyên hai persistence unit. Nếu cần liên kết, giữ khóa ID như dữ liệu bình thường và kết hợp kết quả ở tầng ứng dụng hoặc dùng cơ chế tích hợp phù hợp.

## 5. Cấu hình Orders: DataSource, EntityManagerFactory, transaction manager

Ví dụ lớp `OrdersJpaConfiguration`:

~~~java
package com.example.integration.orders.config;

import com.example.integration.orders.entity.OrderEntity;
import com.example.integration.orders.repository.OrderRepository;
import com.zaxxer.hikari.HikariDataSource;
import jakarta.persistence.EntityManagerFactory;
import java.util.Map;
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
import javax.sql.DataSource;

@Configuration(proxyBeanMethods = false)
@EnableJpaRepositories(
        basePackageClasses = OrderRepository.class,
        entityManagerFactoryRef = "ordersEntityManagerFactory",
        transactionManagerRef = "ordersTransactionManager")
public class OrdersJpaConfiguration {

    @Bean("ordersDataSourceProperties")
    @Primary
    @ConfigurationProperties("app.datasource.orders")
    DataSourceProperties ordersDataSourceProperties() {
        return new DataSourceProperties();
    }

    @Bean("ordersDataSource")
    @Primary
    @ConfigurationProperties("app.datasource.orders.configuration")
    HikariDataSource ordersDataSource(
            @Qualifier("ordersDataSourceProperties") DataSourceProperties props) {
        return props.initializeDataSourceBuilder()
                .type(HikariDataSource.class)
                .build();
    }

    @Bean("ordersEntityManagerFactory")
    @Primary
    LocalContainerEntityManagerFactoryBean ordersEntityManagerFactory(
            EntityManagerFactoryBuilder builder,
            @Qualifier("ordersDataSource") DataSource ds) {
        return builder
                .dataSource(ds)
                .packages(OrderEntity.class)
                .persistenceUnit("ordersPU")
                .properties(Map.of("hibernate.hbm2ddl.auto", "validate"))
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
~~~

Giải thích những điểm dễ bị nhầm:

1. `@ConfigurationProperties("app.datasource.orders")` bind thông tin kết nối vào `DataSourceProperties`; phương thức `initializeDataSourceBuilder()` xử lý hợp lý tên thuộc tính JDBC `url` khi xây dựng Hikari.
2. `@ConfigurationProperties("app.datasource.orders.configuration")` gắn cấu hình pool lên `HikariDataSource`. Không trộn cấu hình pool của Orders và Analytics.
3. `builder.dataSource(ds).packages(OrderEntity.class).persistenceUnit("ordersPU")` tạo persistence unit Orders; `packages` quét entity trong package của class được truyền vào.
4. `entityManagerFactoryRef` và `transactionManagerRef` ánh xạ tất cả repository được quét trong package Orders vào đúng các bean có tên đã khai báo.
5. `@Primary` làm Orders trở thành lựa chọn mặc định khi có nhiều bean cùng type. Nó cũng giúp cơ chế auto-configuration cần một `DataSource` duy nhất có thể xác định ứng viên chính. **@Primary không tự chọn database theo entity hoặc theo nghiệp vụ.**
6. `hibernate.hbm2ddl.auto=validate` kiểm tra mapping so với schema hiện hữu khi khởi động; ví dụ này cố tình không để Hibernate tự tạo hay sửa bảng ở môi trường tích hợp.

Trong Spring Boot 3.x, `EntityManagerFactoryBuilder` thường được cung cấp qua cấu hình JPA của Boot khi có `DataSource` phù hợp. Tùy phiên bản và mức độ tự cấu hình bị thay thế, dự án có thể cần tự khai báo builder và các `JpaVendorAdapter`/vendor properties; đừng sao chép cấu hình giữa hai dòng Spring Boot khác nhau mà bỏ qua chữ ký API và auto-configuration thực tế.

## 6. Cấu hình Analytics theo cặp bean tương ứng

Lớp `AnalyticsJpaConfiguration` tạo một nhóm độc lập:

~~~java
package com.example.integration.analytics.config;

import com.example.integration.analytics.entity.OrderMetricEntity;
import com.example.integration.analytics.repository.OrderMetricRepository;
import com.zaxxer.hikari.HikariDataSource;
import jakarta.persistence.EntityManagerFactory;
import java.util.Map;
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
import javax.sql.DataSource;

@Configuration(proxyBeanMethods = false)
@EnableJpaRepositories(
        basePackageClasses = OrderMetricRepository.class,
        entityManagerFactoryRef = "analyticsEntityManagerFactory",
        transactionManagerRef = "analyticsTransactionManager")
public class AnalyticsJpaConfiguration {

    @Bean("analyticsDataSourceProperties")
    @ConfigurationProperties("app.datasource.analytics")
    DataSourceProperties analyticsDataSourceProperties() {
        return new DataSourceProperties();
    }

    @Bean("analyticsDataSource")
    @ConfigurationProperties("app.datasource.analytics.configuration")
    HikariDataSource analyticsDataSource(
            @Qualifier("analyticsDataSourceProperties") DataSourceProperties props) {
        return props.initializeDataSourceBuilder()
                .type(HikariDataSource.class)
                .build();
    }

    @Bean("analyticsEntityManagerFactory")
    LocalContainerEntityManagerFactoryBean analyticsEntityManagerFactory(
            EntityManagerFactoryBuilder builder,
            @Qualifier("analyticsDataSource") DataSource ds) {
        return builder
                .dataSource(ds)
                .packages(OrderMetricEntity.class)
                .persistenceUnit("analyticsPU")
                .properties(Map.of("hibernate.hbm2ddl.auto", "validate"))
                .build();
    }

    @Bean("analyticsTransactionManager")
    PlatformTransactionManager analyticsTransactionManager(
            @Qualifier("analyticsEntityManagerFactory")
            EntityManagerFactory emf) {
        return new JpaTransactionManager(emf);
    }
}
~~~

**Quy tắc quan trọng:** Hai annotation `@EnableJpaRepositories` phải quét hai phạm vi repository **không chồng lấn**, nếu không có thể gặp lỗi đăng ký bean trùng hoặc repository được tạo bằng sai `EntityManagerFactory`. Vị trí package cũng cần nằm dưới gốc component scan của ứng dụng, hoặc được `@Import` rõ ràng.

Đặt tên bean đủ rõ để phân biệt với tên mặc định `entityManagerFactory`/`transactionManager`. Một số thư viện hoặc cấu hình bổ sung có thể giả định các tên mặc định này; phải cung cấp ref/qualifier phù hợp, tránh dựa vào đoán ngầm.

## 7. Chọn transaction đúng nguồn dữ liệu

Tại lớp service, khai báo transaction manager cho từng thao tác:

~~~java
import com.example.integration.orders.entity.OrderEntity;
import com.example.integration.orders.repository.OrderRepository;
import java.util.UUID;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderService {
    private final OrderRepository orders;

    public OrderService(OrderRepository orders) {
        this.orders = orders;
    }

    @Transactional("ordersTransactionManager")
    public void confirm(UUID orderId) {
        OrderEntity order = orders.findById(orderId)
                .orElseThrow(() -> new IllegalArgumentException("Order not found"));
        order.confirm();
        // Dirty checking ghi thay đổi khi flush/commit.
    }
}
~~~

~~~java
import com.example.integration.analytics.entity.OrderMetricEntity;
import com.example.integration.analytics.repository.OrderMetricRepository;
import java.util.UUID;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class AnalyticsService {
    private final OrderMetricRepository metrics;

    public AnalyticsService(OrderMetricRepository metrics) {
        this.metrics = metrics;
    }

    @Transactional(transactionManager = "analyticsTransactionManager")
    public void record(UUID eventId) {
        metrics.save(new OrderMetricEntity(eventId, 1));
    }
}
~~~

Ở ví dụ trên, `@Transactional("ordersTransactionManager")` bao phủ thao tác trên Orders; `@Transactional(transactionManager = "analyticsTransactionManager")` bao phủ Analytics. Spring Data repository cũng dùng manager được cấu hình trong `@EnableJpaRepositories` khi tự mở transaction cho repository method, nhưng **transaction bao trùm một ca sử dụng** nên đặt ở service với manager phù hợp.

Các điểm cần chú ý:

- `@Transactional` không chỉ ra manager có thể chọn manager mặc định/`@Primary`, rồi dễ gây hiểu lầm rằng mọi repository cùng nằm trong một transaction.
- `@Transactional(readOnly = true)` là gợi ý tối ưu và ý định truy cập chỉ đọc; không phải cơ chế bảo mật hay bảo đảm mọi database đều từ chối lệnh ghi.
- Transaction qua Spring proxy không tự áp dụng khi gọi một phương thức `@Transactional` từ một phương thức khác **trong cùng object** (self-invocation).
- Persistence context chỉ quản lý entity thuộc unit của nó. Truyền entity đã load ở Orders sang Analytics `EntityManager` không chuyển nó thành entity managed ở unit thứ hai.
- Nếu inject `EntityManager` trực tiếp, dùng `@PersistenceContext(unitName = "ordersPU")` hoặc `@PersistenceContext(unitName = "analyticsPU")` để xác định unit; không inject một EntityManager không định danh rồi kỳ vọng Spring tự route.

## 8. Không có transaction ACID toàn cục chỉ vì dùng hai `@Transactional`

Đây là rủi ro quan trọng nhất của thiết kế nhiều persistence unit:

~~~mermaid
sequenceDiagram
    participant App as Application service
    participant O as Orders DB
    participant A as Analytics DB
    App->>O: Bắt đầu transaction Orders
    App->>A: Ghi metric với transaction Analytics
    A-->>App: Commit Analytics thành công
    App->>O: Commit Orders
    O-->>App: Commit thất bại
    Note over O,A: Analytics có metric nhưng Orders không xác nhận
~~~

`JpaTransactionManager` quản lý **một** `EntityManagerFactory`/`DataSource`. Nếu service gọi tuần tự hai service có hai transaction manager khác nhau, mỗi bên commit độc lập. Ngay cả khi một phương thức ngoài có `@Transactional("ordersTransactionManager")` rồi gọi repository Analytics, operation Analytics thường chạy với transaction manager của chính nó. Rollback Orders **không** mặc nhiên rollback được Analytics.

### 8.1. Chọn cách phối hợp theo ràng buộc nghiệp vụ

| Yêu cầu | Hướng tiếp cận thường hợp lý | Đánh đổi |
| --- | --- | --- |
| Tất cả thay đổi phải atomic và cùng owner | Đặt dữ liệu cần bảo vệ bất biến trong **một ranh giới transaction cục bộ** khi thiết kế được. | Có thể cần điều chỉnh ownership/schema dịch vụ. |
| Orders là nguồn sự thật; Analytics được phép chậm | Commit Orders kèm **transactional outbox**, sau đó gửi event; Analytics consumer xử lý idempotent. | Eventual consistency, outbox relay, retry, lag và đối soát. |
| Nhiều bước nghiệp vụ ở các hệ thống độc lập | Saga/orchestration, trạng thái trung gian, timeout và hành động bù trừ. | Bù trừ không tương đương rollback tức thời. |
| Bắt buộc atomic across resource có hỗ trợ XA | Xem xét JTA/XA với transaction coordinator được cấu hình đúng, kiểm tra hỗ trợ của database/driver. | Lock/coordination, chi phí vận hành, phục hồi giao dịch phân tán phức tạp. |

Với Orders và Analytics, một mẫu điển hình là ghi `OrderConfirmed` vào **outbox của Orders trong cùng transaction tạo trạng thái CONFIRMED**. Sau commit, relay publish event qua broker như RabbitMQ/Kafka; Analytics xử lý sự kiện và ghi metric bằng transaction cục bộ của Analytics. Consumer nhận lại event phải tránh tăng metric hai lần bằng một khóa `eventId` duy nhất, ví dụ bảng inbox có unique constraint, hoặc cách cập nhật dữ liệu idempotent tương đương.

~~~mermaid
flowchart LR
    O["OrderService"] -->|"Một transaction"| DB[("Orders + Outbox")]
    DB --> R["Outbox relay"]
    R --> B[("Broker")]
    B --> C["Analytics consumer"]
    C -->|"Một transaction"| A[("Analytics + Inbox")]
~~~

**Outbox không đảm bảo broker chỉ phát một lần:** nếu relay crash sau khi broker nhận nhưng trước khi đánh dấu đã publish, cùng event có thể được gửi lại. Cần thiết kế idempotency ở phía Analytics. Nếu dữ liệu chuyển giữa hai nguồn mà không qua broker, vẫn phải có cơ chế checkpoint, đối soát và retry để xử lý trạng thái từng phần.

## 9. Phối hợp schema migration và cấu hình Hibernate

Mỗi persistence unit thường có vòng đời schema riêng. Nếu dùng Flyway hoặc Liquibase, phải xác định chính xác **migration chạy trên DataSource nào**, cách đặt đường dẫn script, bảng version và thứ tự khởi tạo. Không giả định cấu hình migration tự động mặc định của Spring Boot sẽ chạy đầy đủ trên cả hai nguồn.

Ví dụ cách tổ chức:

~~~text
src/main/resources/db/migration/
├── orders/
│   ├── V1__create_orders.sql
│   └── V2__create_outbox.sql
└── analytics/
    ├── V1__create_order_metrics.sql
    └── V2__create_consumer_inbox.sql
~~~

Cần tạo cấu hình migration riêng cho từng `DataSource` (hoặc quy trình migration ngoài ứng dụng), đặt đúng locations và kiểm soát migration trước khi các `EntityManagerFactory` bắt đầu kiểm tra schema. Tùy việc dùng Flyway/Liquibase, thứ tự khởi tạo cần được cấu hình rõ. Trong ví dụ ở mục 5–6, `hibernate.hbm2ddl.auto=validate` chỉ **kiểm tra** schema; nó không tạo hay cập nhật bảng.

Các thuộc tính `spring.jpa.*` thường được người dùng kỳ vọng áp dụng cho mọi persistence unit, nhưng khi tự xây các `EntityManagerFactory`, cần kiểm tra thuộc tính nào thực sự được truyền vào builder từng unit. Những tùy chỉnh như naming strategy, dialect, SQL formatting, batch size, timezone, second-level cache hoặc multi-tenancy có thể phải khai báo rõ cho từng unit. Khác biệt giữa các database hoặc Hibernate version càng đòi hỏi cấu hình riêng thay vì sao chép nguyên xi.

Nếu hai nguồn dùng hai loại RDBMS khác nhau, mỗi `EntityManagerFactory` cần đúng Hibernate dialect/driver và kiểu dữ liệu tương ứng. Để Hibernate tự suy dialect qua JDBC metadata có thể phù hợp khi kết nối khả dụng; trong môi trường hạn chế metadata hoặc dialect đặc biệt, phải chủ động kiểm soát cấu hình theo version.

## 10. Lỗi thường gặp và dấu hiệu nhận biết

| Triệu chứng | Nguyên nhân thường gặp | Cách kiểm tra và xử lý |
| --- | --- | --- |
| `Not a managed type: ...OrderEntity` | Entity không thuộc package được quét bởi `ordersEntityManagerFactory` hoặc import sai unit. | Kiểm tra `packages(OrderEntity.class)`, vị trí entity và `@Entity`. |
| Repository dùng sai bảng/database | Phạm vi `@EnableJpaRepositories` chồng lấn, bean ref sai hoặc một package bị quét mặc định ngoài dự kiến. | Chỉ định `basePackageClasses` riêng; xác nhận `entityManagerFactoryRef` và `transactionManagerRef`. |
| `NoUniqueBeanDefinitionException` | Có nhiều `DataSource`, `EntityManagerFactory` hoặc `PlatformTransactionManager` cùng type nhưng injection không rõ. | Dùng `@Qualifier`/bean name, `@Primary` cho default nếu cần. |
| `No bean named 'entityManagerFactory'` | Thư viện hoặc cấu hình kỳ vọng tên mặc định, trong khi ứng dụng đặt tên tùy chỉnh. | Cập nhật điểm phụ thuộc để dùng tên đúng, hoặc tạo alias khi hợp lý. |
| `No EntityManager with actual transaction available` | Thao tác ghi/flush chạy ngoài transaction JPA phù hợp. | Đặt `@Transactional` ở service, dùng đúng manager, kiểm tra proxy và nơi gọi. |
| `Connection is closed`, timeout pool | Pool quá nhỏ, leak, query chậm hoặc database bị giới hạn kết nối. | Theo dõi active/idle/pending connection, timeout, query latency và tổng pool theo replica. |
| Orders rollback nhưng Analytics đã commit | Hai local transaction manager không phối hợp atomicity. | Thiết kế outbox/saga/đối soát; chỉ dùng XA nếu bắt buộc và được hỗ trợ. |
| Migration chạy sang database không mong muốn | Auto-config chỉ chọn DataSource mặc định hoặc cấu hình locations sai. | Gắn migration với từng DS và verify qua bảng version/schema thực tế. |
| `LazyInitializationException` | Truy cập lazy association sau khi EntityManager/session đã đóng. | Lấy dữ liệu cần thiết trong đúng transaction; dùng DTO/projection/fetch plan phù hợp. |
| Đọc dữ liệu Analytics cũ hơn Orders | Analytics là projection bất đồng bộ hoặc đọc từ replica có lag. | Xác định SLA độ trễ, hiển thị trạng thái và đọc từ owner khi cần dữ liệu mới nhất. |

Một ví dụ nguy hiểm khác là đặt cùng một tên bảng `orders` ở hai database rồi coi việc truy vấn thành công là bằng chứng đã chọn đúng nguồn. Test nên kiểm tra **database/schema thực tế**, dữ liệu sentinel và trạng thái trong từng datasource, không chỉ kiểm tra repository method trả về danh sách.

## 11. Kiểm thử hai persistence unit một cách thực chất

Đối với nhiều nguồn dữ liệu, kiểm thử slice `@DataJpaTest` thông thường không phải lúc nào cũng tự mang đủ cấu hình và cả hai database cần thiết. Với bài kiểm thử tích hợp, nên dùng `@SpringBootTest` và cấu hình Testcontainers hoặc hai database độc lập, sau đó ánh xạ URL của từng datasource vào đúng properties.

Một ma trận kiểm thử có giá trị:

1. **Boot và wiring:** ứng dụng tạo đúng hai `DataSource`, hai `EntityManagerFactory`, hai `JpaTransactionManager`; mỗi repository trỏ đến đúng database.
2. **Độc lập giao dịch:** ghi Orders thành công không tự tạo dòng ở Analytics; rollback Analytics không xóa dữ liệu Orders đã commit.
3. **Tránh nhầm entity:** repository Orders chỉ quản lý `OrderEntity`, repository Analytics chỉ quản lý `OrderMetricEntity`; thử lưu entity khác PU phải báo lỗi đúng.
4. **Migration:** cả hai database có đủ bảng theo version mong đợi, migration không chạy chéo nguồn.
5. **Lỗi kết nối một DB:** khi Analytics không khả dụng, xử lý Orders theo yêu cầu nghiệp vụ vẫn đưa ra kết quả rõ ràng và có cơ chế retry cho phần Analytics nếu được phép.
6. **Chống trùng event:** cùng một `OrderConfirmed` được consumer Analytics nhận hai lần không làm tăng metric hai lần.
7. **Pool và quan sát:** kiểm tra giới hạn connection của từng nguồn; dashboard phân biệt Orders với Analytics.
8. **Dữ liệu nhất quán cuối cùng:** khi relay/consumer chậm, hệ thống thể hiện đúng trạng thái đang chờ, lag metric tăng và hội tụ sau khi phục hồi.

Nếu muốn dùng transaction test để rollback dữ liệu kiểm thử, hãy chỉ rõ manager. Một `@Transactional("ordersTransactionManager")` trên test **không** rollback những commit đã thực hiện với `analyticsTransactionManager`. Khi cần dọn cả hai database, phải dùng cleanup cụ thể, transaction độc lập hoặc tạo lại môi trường test.

### 11.1. Quan sát theo từng nguồn

Đặt định danh metric/log cho từng pool, ví dụ `orders-pool` và `analytics-pool` bằng `pool-name` của Hikari, để quan sát connection usage và timeout theo nguồn. Nên theo dõi:

- `active`, `idle`, `pending` connection; connection acquisition time và timeout của từng pool.
- Query latency, slow query, deadlock và transaction duration theo database.
- Số lần retry, độ trễ event/outbox, consumer lag, DLQ và trường hợp đối soát không khớp.
- Lỗi migration, mismatch schema và các lần thay đổi version Hibernate/driver.

Không ghi password, JDBC URL chứa credentials hoặc dữ liệu cá nhân nhạy cảm vào log. Phân quyền DB theo nguyên tắc ít quyền nhất; tài khoản Analytics không nhất thiết cần quyền cập nhật bảng Orders.

## 12. Checklist thiết kế

Trước khi đưa cấu hình multi-persistence-unit vào vận hành, xác nhận các điều kiện sau:

- [ ] Mỗi `DataSource` có prefix cấu hình, pool, tài khoản, quyền truy cập và health/metric rõ ràng.
- [ ] Mỗi tập entity chỉ thuộc persistence unit mong muốn; các package repository được tách sạch.
- [ ] Mỗi `@EnableJpaRepositories` khai báo chính xác `entityManagerFactoryRef` và `transactionManagerRef`.
- [ ] Các service thực hiện thay đổi dữ liệu khai báo transaction manager phù hợp, không giả định rollback xuyên database.
- [ ] Mỗi schema có migration và quy trình deploy/rollback schema riêng; Hibernate không tự sửa schema ngoài ý muốn.
- [ ] Những luồng dữ liệu xuyên database có chính sách consistency, retry, idempotency, đối soát và giám sát.
- [ ] Test tích hợp dùng **hai database thật hoặc môi trường có tính tương đương phù hợp**, kiểm tra nguồn vật lý và tình huống một bên lỗi.

Với **Spring Boot Integration**, nhiều persistence unit là một cách phân định ranh giới kỹ thuật rất hữu ích: JPA/Hibernate quản lý entity và transaction cục bộ của từng nguồn, còn các luồng tích hợp HTTP, message broker, cache hoặc Spring Integration đảm nhận trao đổi dữ liệu giữa các ranh giới đó. Khi thiết kế dựa trên **quyền sở hữu dữ liệu, hợp đồng thông điệp và yêu cầu nhất quán** ngay từ đầu, cấu hình multi-DataSource sẽ dễ kiểm soát hơn và tránh được giả định sai về giao dịch toàn cục.
