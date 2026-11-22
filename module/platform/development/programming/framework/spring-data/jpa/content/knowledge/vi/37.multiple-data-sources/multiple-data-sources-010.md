# Kiểm thử định tuyến, giao dịch và cách ly dữ liệu

## 1. Mục tiêu

Khi ứng dụng Spring Data JPA sử dụng nhiều nguồn dữ liệu, cần xác nhận mỗi thao tác đi đúng database, transaction bao trọn đúng công việc và dữ liệu giữa các nguồn không bị đọc hoặc ghi nhầm. Một cấu hình chạy được chưa đủ: sai routing có thể khiến query đọc từ primary, command ghi vào replica hoặc một transaction lấy connection trước khi thông tin định tuyến sẵn sàng.

Bài học dùng mô hình primary/replica để kiểm thử:
- Query có `@Transactional(readOnly = true)` được định tuyến tới read replica.
- Command có transaction ghi được định tuyến tới primary.
- Transaction rollback không để lại dữ liệu đã ghi dở.
- Dữ liệu chỉ tồn tại trên một nguồn không xuất hiện khi truy vấn nguồn còn lại.
- Phân biệt routing datasource, cách ly giữa các database và isolation level của transaction.
- Nhận biết giới hạn khi một business operation cần ghi vào nhiều database.

Sau bài học, bạn có thể tạo integration test với hai database độc lập, kiểm tra routing bằng dữ liệu đánh dấu khác nhau và xác nhận commit/rollback bằng cách đọc trực tiếp từng nguồn.

## 2. Các khái niệm cần phân biệt

Ba khái niệm thường bị nhầm lẫn:

| Khái niệm | Câu hỏi được trả lời | Ví dụ |
| --- | --- | --- |
| Data source routing | Connection của thao tác này lấy từ database nào? | Query đọc replica, command ghi primary. |
| Data isolation | Dữ liệu của nguồn/tenant này có bị lộ sang nguồn/tenant khác không? | Bản ghi chỉ có trong database tenant A không xuất hiện ở tenant B. |
| Transaction isolation | Một transaction nhìn thấy thay đổi của transaction khác ở mức nào? | `READ_COMMITTED`, `REPEATABLE_READ`, `SERIALIZABLE`. |

Routing quyết định nơi lấy connection. Data isolation là ranh giới dữ liệu và quyền truy cập. Transaction isolation do database áp dụng cho các transaction đang chạy. Kiểm thử một khía cạnh không tự chứng minh hai khía cạnh còn lại.

## 3. Primary/replica routing trong Spring

Một cấu hình phổ biến gửi thao tác ghi tới primary và thao tác đọc tới replica. Spring cung cấp `AbstractRoutingDataSource` để chọn một target DataSource dựa trên lookup key.

Ví dụ route key:

```java
package com.example.multidb;

public enum DataSourceRoute {
    PRIMARY,
    REPLICA
}
```

Routing datasource đọc trạng thái transaction hiện tại:

```java
package com.example.multidb;

import org.springframework.jdbc.datasource.lookup.AbstractRoutingDataSource;
import org.springframework.transaction.support.TransactionSynchronizationManager;

public class ReadWriteRoutingDataSource extends AbstractRoutingDataSource {
    @Override
    protected Object determineCurrentLookupKey() {
        boolean readOnly = TransactionSynchronizationManager.isCurrentTransactionReadOnly();
        return readOnly ? DataSourceRoute.REPLICA : DataSourceRoute.PRIMARY;
    }
}
```

Khi transaction được đánh dấu read-only, lookup key là `REPLICA`. Những transaction còn lại, kể cả khi không có transaction metadata, mặc định chọn `PRIMARY` để tránh gửi nhầm thao tác ghi sang replica.

`@Transactional(readOnly = true)` tự nó không tạo replica và cũng không tự route connection. Chính `ReadWriteRoutingDataSource` mới thực hiện lựa chọn ở ví dụ này. Read-only là transaction hint; quyền chỉ đọc thực sự nên được bảo vệ thêm bằng quyền database.

## 4. Vì sao cần LazyConnectionDataSourceProxy?

Routing datasource đọc `TransactionSynchronizationManager.isCurrentTransactionReadOnly()`. Giá trị này phải có sẵn tại thời điểm routing datasource chọn physical connection.

Trong một số cấu hình JPA, transaction manager có thể yêu cầu connection khá sớm khi bắt đầu transaction. Nếu routing datasource chọn target trước khi transaction read-only metadata được gắn vào thread, query dự định đọc replica có thể bị route sang primary.

`LazyConnectionDataSourceProxy` trì hoãn việc lấy physical connection cho đến khi JDBC statement thực sự cần connection. Nhờ đó transaction metadata có thời gian được thiết lập trước khi `AbstractRoutingDataSource` chọn target.

```java
@Bean
@Primary
DataSource dataSource(@Qualifier("routingDataSource") DataSource routingDataSource) {
    return new LazyConnectionDataSourceProxy(routingDataSource);
}
```

Proxy này cũng phải là DataSource mà JPA `EntityManagerFactory` và transaction manager sử dụng. Không chỉ bọc một JdbcTemplate trong khi Hibernate vẫn dùng một datasource khác.

Routing được quyết định khi physical connection được lấy. Không đổi read-only flag hoặc tenant route giữa một transaction rồi mong các statement tiếp theo tự chuyển database. Một transaction nên dùng một nguồn nhất quán từ đầu đến cuối.

## 5. Cấu hình hai DataSource

Ví dụ dùng Java 17+, Spring Boot 3.x, Spring Data JPA, Hibernate và H2 cho integration test. Spring Boot quản lý phiên bản JPA provider và JDBC pool.

`src/main/java/com/example/multidb/DataSourceRoutingConfiguration.java`:

```java
package com.example.multidb;

import java.util.HashMap;
import java.util.Map;
import javax.sql.DataSource;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.autoconfigure.jdbc.DataSourceProperties;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Primary;
import org.springframework.jdbc.datasource.LazyConnectionDataSourceProxy;

@Configuration
public class DataSourceRoutingConfiguration {
    @Bean
    @ConfigurationProperties("app.datasource.primary")
    DataSourceProperties primaryDataSourceProperties() {
        return new DataSourceProperties();
    }

    @Bean
    @ConfigurationProperties("app.datasource.replica")
    DataSourceProperties replicaDataSourceProperties() {
        return new DataSourceProperties();
    }

    @Bean(name = "primaryTargetDataSource")
    DataSource primaryTargetDataSource(
            @Qualifier("primaryDataSourceProperties") DataSourceProperties properties) {
        return properties.initializeDataSourceBuilder().build();
    }

    @Bean(name = "replicaTargetDataSource")
    DataSource replicaTargetDataSource(
            @Qualifier("replicaDataSourceProperties") DataSourceProperties properties) {
        return properties.initializeDataSourceBuilder().build();
    }

    @Bean(name = "routingDataSource")
    DataSource routingDataSource(
            @Qualifier("primaryTargetDataSource") DataSource primary,
            @Qualifier("replicaTargetDataSource") DataSource replica) {
        Map<Object, Object> targets = new HashMap<>();
        targets.put(DataSourceRoute.PRIMARY, primary);
        targets.put(DataSourceRoute.REPLICA, replica);

        ReadWriteRoutingDataSource routing = new ReadWriteRoutingDataSource();
        routing.setTargetDataSources(targets);
        routing.setDefaultTargetDataSource(primary);
        routing.setLenientFallback(false);
        routing.afterPropertiesSet();
        return routing;
    }

    @Bean
    @Primary
    DataSource dataSource(@Qualifier("routingDataSource") DataSource routingDataSource) {
        return new LazyConnectionDataSourceProxy(routingDataSource);
    }
}
```

`@Primary` bảo đảm Spring Boot JPA auto-configuration chọn datasource đã được route. Hai target datasource vẫn có thể được inject riêng bằng `@Qualifier` cho migration, health check hoặc test fixture. Không inject target thô vào Repository/EntityManagerFactory nếu muốn query JPA đi qua routing.

Ví dụ cấu hình test trong `src/test/resources/application-test.properties`:

```properties
app.datasource.primary.url=jdbc:h2:mem:primarydb;DB_CLOSE_DELAY=-1
app.datasource.primary.username=sa
app.datasource.primary.password=
app.datasource.primary.driver-class-name=org.h2.Driver

app.datasource.replica.url=jdbc:h2:mem:replicadb;DB_CLOSE_DELAY=-1
app.datasource.replica.username=sa
app.datasource.replica.password=
app.datasource.replica.driver-class-name=org.h2.Driver

spring.jpa.database-platform=org.hibernate.dialect.H2Dialect
spring.jpa.hibernate.ddl-auto=none
spring.jpa.open-in-view=false
spring.sql.init.mode=never
```

Hai URL dùng hai database H2 độc lập. Trong production, thay URL, credential và pool setting bằng cấu hình được quản lý an toàn. Không dùng cùng một H2 database name cho cả hai target nếu mục tiêu test là chứng minh chúng tách biệt.

Với replica thật, schema và dữ liệu thường được đồng bộ từ primary bằng cơ chế replication. Ví dụ H2 không tự replication; test sẽ tạo dữ liệu đánh dấu riêng ở từng database để xác nhận route.

## 6. Entity và Repository dùng chung routing datasource

Entity ví dụ:

`src/main/java/com/example/multidb/Product.java`:

```java
package com.example.multidb;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import java.math.BigDecimal;

@Entity
@Table(name = "products")
public class Product {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, unique = true, length = 40)
    private String sku;

    @Column(nullable = false, length = 160)
    private String name;

    @Column(nullable = false, precision = 12, scale = 2)
    private BigDecimal price;

    protected Product() {
        // JPA cần constructor không tham số.
    }

    public Product(String sku, String name, BigDecimal price) {
        if (sku == null || sku.isBlank() || sku.length() > 40) {
            throw new IllegalArgumentException("SKU is required");
        }
        if (name == null || name.isBlank() || name.length() > 160) {
            throw new IllegalArgumentException("Name is required");
        }
        if (price == null || price.signum() < 0) {
            throw new IllegalArgumentException("Price must be zero or greater");
        }
        this.sku = sku.trim();
        this.name = name.trim();
        this.price = price;
    }

    public Long getId() { return id; }
    public String getSku() { return sku; }
    public String getName() { return name; }
    public BigDecimal getPrice() { return price; }
}
```

Command Repository có khả năng ghi:

```java
package com.example.multidb;

import java.util.Optional;
import org.springframework.data.jpa.repository.JpaRepository;

public interface ProductCommandRepository extends JpaRepository<Product, Long> {
    Optional<Product> findBySku(String sku);
}
```

Read Repository chỉ công bố truy vấn đọc và trả projection:

`src/main/java/com/example/multidb/ProductView.java`:

```java
package com.example.multidb;

import java.math.BigDecimal;

public interface ProductView {
    String getSku();
    String getName();
    BigDecimal getPrice();
}
```

```java
package com.example.multidb;

import java.util.Optional;
import org.springframework.data.repository.Repository;

public interface ProductReadRepository extends Repository<Product, Long> {
    Optional<ProductView> findBySku(String sku);
}
```

Read Repository extends marker `Repository` thay vì `JpaRepository`, nên API công khai không có `save()` hoặc `delete()`. Đây là ranh giới code hữu ích; quyền ghi ở database vẫn phải được quản lý riêng nếu cần enforcement.

## 7. Đặt transaction ở Service

Query Service đánh dấu transaction read-only để routing datasource chọn replica:

```java
package com.example.multidb;

import java.util.Optional;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class ProductQueryService {
    private final ProductReadRepository repository;

    public ProductQueryService(ProductReadRepository repository) {
        this.repository = repository;
    }

    @Transactional(readOnly = true)
    public Optional<ProductView> findBySku(String sku) {
        return repository.findBySku(sku);
    }
}
```

Command Service dùng transaction ghi và đi tới primary:

```java
package com.example.multidb;

import java.math.BigDecimal;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class ProductCommandService {
    private final ProductCommandRepository repository;

    public ProductCommandService(ProductCommandRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public Long create(String sku, String name, BigDecimal price) {
        Product saved = repository.saveAndFlush(new Product(sku, name, price));
        return saved.getId();
    }

    @Transactional
    public void createThenFail(String sku, String name, BigDecimal price) {
        repository.saveAndFlush(new Product(sku, name, price));
        throw new IllegalStateException("Simulated failure after insert");
    }
}
```

Method `createThenFail` flush insert xuống database trước khi ném runtime exception. Transaction interceptor vẫn rollback transaction khi exception thoát khỏi method, vì vậy test có thể xác nhận row không được commit.

Đặt `@Transactional` ở public method được gọi qua Spring proxy. Self-invocation, ví dụ một method trong cùng class gọi method khác có `@Transactional`, không đi qua proxy theo cách thông thường và có thể không áp dụng transaction annotation như mong đợi.

## 8. Kiểm thử route bằng dữ liệu đánh dấu

Để chứng minh query thực sự đi tới replica, seed hai database bằng các SKU khác nhau:

- Primary chỉ có `PRIMARY-ONLY`.
- Replica chỉ có `REPLICA-ONLY`.

Nếu Query Service route đúng, nó tìm thấy `REPLICA-ONLY` và không tìm thấy `PRIMARY-ONLY`. Nếu route nhầm primary, assertion đầu tiên sẽ thất bại.

Integration test dùng `@SpringBootTest` để khởi tạo toàn bộ routing configuration, JPA repositories và transaction proxy:

`src/test/java/com/example/multidb/DataSourceRoutingIntegrationTest.java`:

```java
package com.example.multidb;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import java.math.BigDecimal;
import javax.sql.DataSource;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.context.ActiveProfiles;

@SpringBootTest
@ActiveProfiles("test")
class DataSourceRoutingIntegrationTest {
    @Autowired
    private ProductQueryService queries;

    @Autowired
    private ProductCommandService commands;

    @Autowired
    @Qualifier("primaryTargetDataSource")
    private DataSource primary;

    @Autowired
    @Qualifier("replicaTargetDataSource")
    private DataSource replica;

    private JdbcTemplate primaryJdbc;
    private JdbcTemplate replicaJdbc;

    @BeforeEach
    void prepareDatabases() {
        primaryJdbc = new JdbcTemplate(primary);
        replicaJdbc = new JdbcTemplate(replica);
        prepare(primaryJdbc, "PRIMARY-ONLY", "Primary row");
        prepare(replicaJdbc, "REPLICA-ONLY", "Replica row");
    }

    private void prepare(JdbcTemplate jdbc, String sku, String name) {
        jdbc.execute("""
                create table if not exists products (
                    id bigint generated by default as identity primary key,
                    sku varchar(40) not null unique,
                    name varchar(160) not null,
                    price decimal(12,2) not null
                )
                """);
        jdbc.update("delete from products");
        jdbc.update(
                "insert into products(sku, name, price) values (?, ?, ?)",
                sku, name, new BigDecimal("10.00"));
    }

    private int count(JdbcTemplate jdbc, String sku) {
        return jdbc.queryForObject(
                "select count(*) from products where sku = ?", Integer.class, sku);
    }

    @Test
    void readOnlyTransactionUsesReplica() {
        assertThat(queries.findBySku("REPLICA-ONLY")).isPresent();
        assertThat(queries.findBySku("PRIMARY-ONLY")).isEmpty();
    }

    @Test
    void writeTransactionUsesPrimaryOnly() {
        commands.create("NEW-001", "Created product", new BigDecimal("25.00"));

        assertThat(count(primaryJdbc, "NEW-001")).isEqualTo(1);
        assertThat(count(replicaJdbc, "NEW-001")).isZero();
    }

    @Test
    void runtimeExceptionRollsBackThePrimaryWrite() {
        assertThatThrownBy(() -> commands.createThenFail(
                "ROLLBACK-001", "Temporary product", new BigDecimal("30.00")))
                .isInstanceOf(IllegalStateException.class)
                .hasMessage("Simulated failure after insert");

        assertThat(count(primaryJdbc, "ROLLBACK-001")).isZero();
        assertThat(count(replicaJdbc, "ROLLBACK-001")).isZero();
    }
}
```

Test tạo schema trên cả hai database vì đây là hai H2 database độc lập và không có replication tự động. `JdbcTemplate` trong test fixture kết nối trực tiếp tới target được inject bằng qualifier; các Repository JPA vẫn dùng datasource routing chính.

Test `readOnlyTransactionUsesReplica` xác nhận route bằng nội dung khác nhau ở hai nguồn. Test `writeTransactionUsesPrimaryOnly` xác nhận insert chỉ xuất hiện ở primary. Test rollback xác nhận insert đã flush nhưng không tồn tại sau khi transaction kết thúc bằng exception.

Chạy test:

```bash
mvn test
```

Kết quả mong đợi là Maven kết thúc với `BUILD SUCCESS` và cả ba test đều thành công. Đây là kết quả kỳ vọng của ví dụ, không phải log build đã chạy trong môi trường thực tế.

## 9. Kiểm thử transaction isolation level

Transaction isolation level là thuộc tính của transaction database, không phải lựa chọn primary/replica. Spring cho phép khai báo isolation trên `@Transactional`:

```java
import org.springframework.transaction.annotation.Isolation;
import org.springframework.transaction.annotation.Transactional;

@Transactional(isolation = Isolation.READ_COMMITTED)
public void updateCatalog() {
    // Đọc và ghi trong cùng transaction.
}
```

Các mức isolation phổ biến:

| Spring Isolation | Ý nghĩa khái quát |
| --- | --- |
| `DEFAULT` | Dùng mức mặc định của database/transaction manager. |
| `READ_UNCOMMITTED` | Có thể cho phép đọc dữ liệu chưa commit nếu database hỗ trợ. |
| `READ_COMMITTED` | Không đọc dữ liệu chưa commit; các lần đọc sau có thể thấy commit mới. |
| `REPEATABLE_READ` | Bảo vệ khả năng đọc lại cùng dòng theo semantics database; phantom behavior tùy engine. |
| `SERIALIZABLE` | Mức cô lập cao, database có thể khóa hoặc abort transaction để bảo đảm tương đương tuần tự. |

Ví dụ dùng `TransactionTemplate` để chọn isolation trong test hoặc code điều phối:

```java
TransactionTemplate transaction = new TransactionTemplate(transactionManager);
transaction.setIsolationLevel(TransactionDefinition.ISOLATION_READ_COMMITTED);

transaction.executeWithoutResult(status -> {
    // Thực hiện các thao tác JDBC/JPA tham gia transaction này.
});
```

Muốn kiểm thử isolation thực sự, cần hai transaction độc lập và điều phối thứ tự bằng latch/barrier: transaction A đọc, transaction B ghi và commit, sau đó A đọc lại. Kết quả lần đọc thứ hai phụ thuộc isolation level và database engine. Không dùng một persistence context duy nhất để giả lập hai transaction.

Isolation được đặt khi bắt đầu transaction mới. Nếu method tham gia một transaction đã tồn tại, isolation khai báo ở method bên trong thường không thay đổi isolation của transaction ngoài. Muốn phát hiện trường hợp cấu hình không tương thích, có thể bật `validateExistingTransaction` trên transaction manager hoặc thiết kế transaction boundary riêng.

Không chọn `SERIALIZABLE` mặc định cho mọi query; mức này có thể tăng contention, lock wait hoặc serialization failure. Chọn theo yêu cầu nghiệp vụ và đo trên database thật.

## 10. Cách ly dữ liệu giữa các nguồn và tenant

Trong ví dụ primary và replica là hai database riêng. Test marker chứng minh query route không đọc nhầm target và command không ghi vào replica. Đây là kiểm thử cách ly giữa các nguồn vật lý.

Nếu hệ thống dùng database riêng cho từng tenant, routing key thường phải chứa tenant đã xác thực. Một mẫu đơn giản dùng context theo thread:

```java
package com.example.multidb;

public final class TenantContext {
    private static final ThreadLocal<String> CURRENT = new ThreadLocal<>();

    private TenantContext() {
    }

    public static void set(String tenantId) {
        if (tenantId == null || tenantId.isBlank()) {
            throw new IllegalArgumentException("Tenant is required");
        }
        CURRENT.set(tenantId);
    }

    public static String getRequired() {
        String tenantId = CURRENT.get();
        if (tenantId == null) {
            throw new IllegalStateException("Tenant context is missing");
        }
        return tenantId;
    }

    public static void clear() {
        CURRENT.remove();
    }
}
```

Tenant routing datasource có thể dùng `TenantContext.getRequired()` làm lookup key. Context phải được thiết lập sau xác thực và trước khi mở transaction, rồi luôn xóa trong `finally` hoặc request filter. Không tin tenant ID tùy ý do client gửi lên nếu chưa kiểm tra quyền truy cập.

Với async executor, scheduler hoặc message listener, `ThreadLocal` không tự truyền sang thread khác. Cần truyền tenant context tường minh và xóa sau khi xử lý; nếu thiếu bước này, thread pool có thể giữ context của request trước và gây rò rỉ dữ liệu giữa tenant.

Integration test tenant isolation nên seed cùng một SKU vào hai database tenant với tên/giá khác nhau, đặt tenant context A rồi B và xác nhận mỗi context chỉ thấy bản ghi của chính nguồn đó. Test thêm trường hợp không có tenant context phải fail closed thay vì route về tenant mặc định.

Tenant isolation qua datasource không thay thế authorization. Ứng dụng vẫn cần xác thực tenant và giới hạn thao tác của user trong tenant đó. Nếu dùng chung một database và phân tách bằng `tenant_id`, mọi query cần áp dụng tenant predicate hoặc cơ chế filter được kiểm soát và kiểm thử.

## 11. Nhiều DataSource và transaction manager

Routing primary/replica ở trên dùng một `EntityManagerFactory` và một transaction manager làm việc với một routing DataSource. Từng transaction chọn một target connection.

Nếu ứng dụng có hai database độc lập cùng cần ghi trong một business operation, một `JpaTransactionManager` thông thường chỉ quản lý một `EntityManagerFactory`/DataSource. Hai transaction manager local riêng biệt không tự tạo một transaction atomic trên cả hai database.

Các lựa chọn:

- Nếu chỉ cần ghi một nguồn rồi đồng bộ nguồn khác bất đồng bộ, dùng transactional outbox và consumer idempotent.
- Nếu thật sự cần commit/rollback phân tán trên nhiều resource, đánh giá JTA/XA và chi phí vận hành.
- Nếu nghiệp vụ có thể chấp nhận eventual consistency, dùng saga/compensation và theo dõi trạng thái từng bước.

Không gọi hai service dùng hai transaction manager khác nhau rồi giả định một `@Transactional` bao ngoài sẽ rollback cả hai database. Phải chỉ rõ transaction manager bằng qualifier khi cấu hình nhiều persistence unit, ví dụ `@Transactional("ordersTransactionManager")`, và thiết kế cơ chế phối hợp nếu cần atomicity xuyên database.

## 12. Những lỗi routing và transaction thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Query read-only vẫn đi primary | Physical connection được lấy trước khi read-only metadata sẵn sàng. | Bọc routing datasource bằng `LazyConnectionDataSourceProxy` và kiểm thử bằng hai nguồn có marker khác nhau. |
| Command ghi vào replica | Method bị đánh dấu read-only hoặc route key mặc định sai. | Dùng `@Transactional` ghi, default target là primary và test insert trực tiếp trên hai nguồn. |
| `readOnly = true` không tự route | Không có routing datasource đọc transaction metadata. | Triển khai `AbstractRoutingDataSource`; readOnly chỉ là hint nếu không có routing logic. |
| Connection đổi nguồn giữa transaction | Code thay route context sau khi connection đã được lấy. | Chọn route trước transaction và giữ cố định đến commit/rollback. |
| Test đọc được row từ cả hai database | Hai target vô tình trỏ cùng URL hoặc fixture seed nhầm nguồn. | Dùng database name riêng, inject qualifier và kiểm tra URL/config trong test. |
| Rollback test vẫn thấy row | Service không chạy qua transaction proxy, exception bị bắt hoặc method không transactional. | Gọi public Service bean, để exception thoát ra và đọc lại bằng connection mới. |
| Query replica trả dữ liệu cũ | Replication bất đồng bộ hoặc replica lag. | Định nghĩa read-your-writes; route tạm về primary hoặc trả kết quả command. |
| Hai database không rollback cùng nhau | Dùng hai local transaction manager mà không có distributed transaction. | Dùng JTA/XA khi cần atomicity hoặc outbox/saga khi chấp nhận eventual consistency. |
| Tenant A nhìn thấy dữ liệu tenant B | Tenant context thiếu, stale hoặc query thiếu tenant predicate. | Fail closed, xác thực tenant, clear context trong finally và test cross-tenant access. |
| Transaction isolation test không ổn định | Dùng chung EntityManager hoặc dựa vào timing cố định. | Dùng transaction độc lập, latch/barrier và database production trong test quan trọng. |

## 13. Quy trình kiểm thử đáng tin cậy

1. Dùng hai database test có URL/name khác nhau; không để hai target vô tình trỏ cùng nguồn.
2. Tạo schema và seed dữ liệu đánh dấu riêng cho từng nguồn.
3. Gọi Query Service qua Spring proxy với `@Transactional(readOnly = true)` và xác nhận chỉ thấy marker của replica.
4. Gọi Command Service với transaction ghi và xác nhận row chỉ xuất hiện ở primary.
5. Buộc một command flush rồi ném runtime exception; xác nhận dữ liệu không tồn tại sau rollback.
6. Đọc lại trực tiếp từng target bằng qualifier để tránh chính routing logic che giấu lỗi.
7. Kiểm thử replica lag/read-your-writes nếu production dùng replication bất đồng bộ.
8. Nếu có tenant routing, test từng tenant, tenant context thiếu và context được clear sau request.
9. Nếu isolation level quan trọng, điều phối hai transaction độc lập và chạy test trên đúng database engine.
10. Nếu cần ghi nhiều database trong một business operation, test failure giữa các bước và xác nhận cơ chế XA/outbox/saga.

## 14. H2 và database production

H2 phù hợp để kiểm tra lookup key, cấu hình bean, query repository cơ bản và rollback trong một môi trường nhẹ. Tuy nhiên H2 không chứng minh được:

- Replication lag hoặc hành vi read replica thật.
- Locking, isolation, deadlock và timeout giống PostgreSQL/MySQL/SQL Server.
- Giới hạn connection pool và failover của production.
- JDBC driver behavior và SQL dialect của database triển khai.

Với routing/transaction có ảnh hưởng tới tính đúng đắn, nên bổ sung integration test bằng Testcontainers trên database production. Có thể khởi tạo primary và replica test độc lập để kiểm tra routing; nếu cần mô phỏng replication, phải cấu hình replication thực hoặc dùng test environment có hành vi đồng bộ tương ứng.

## 15. Checklist hoàn thành

- [ ] Giải thích được routing datasource và lookup key.
- [ ] Dùng `AbstractRoutingDataSource` để chọn primary/replica.
- [ ] Hiểu vì sao `LazyConnectionDataSourceProxy` cần thiết khi route theo transaction metadata.
- [ ] Đặt `@Transactional(readOnly = true)` ở Query Service và transaction ghi ở Command Service.
- [ ] Xác nhận query đọc từ replica bằng marker riêng.
- [ ] Xác nhận command ghi vào primary và không ghi replica.
- [ ] Kiểm thử rollback sau khi insert đã flush.
- [ ] Phân biệt data source routing với transaction isolation level.
- [ ] Kiểm thử tenant/data isolation và fail closed khi thiếu context.
- [ ] Hiểu `ThreadLocal` không tự truyền qua async thread.
- [ ] Biết một local transaction manager không đảm bảo atomicity trên hai database.
- [ ] Chọn outbox/saga hoặc JTA/XA theo yêu cầu nhất quán.
- [ ] Bổ sung Testcontainers khi hành vi database-specific ảnh hưởng nghiệp vụ.

Khi hoàn thành, bạn có thể kiểm thử đường đi của connection, ranh giới dữ liệu và hành vi commit/rollback trong ứng dụng Spring Data JPA sử dụng nhiều nguồn dữ liệu.