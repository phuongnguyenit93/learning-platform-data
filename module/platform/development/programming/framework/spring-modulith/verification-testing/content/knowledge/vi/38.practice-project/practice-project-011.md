# Chạy database test bằng Testcontainers

> **Chương:** Dự án thực hành  
> **Module học:** `SPRING_MODULITH_VERIFICATION_TESTING` — kiểm chứng ranh giới kiến trúc Spring Modulith với `ApplicationModules`, quy tắc phụ thuộc module, `@ApplicationModuleTest`, event, database/integration tests và CI quality gate.

## 1. Đề bài: chứng minh hành vi với PostgreSQL thật, không chỉ H2 hoặc mock

Ứng dụng Spring Modulith có ba module `inventory`, `orders` và `billing`. `orders` nhận yêu cầu đặt đơn, hỏi tồn kho qua public `StockAvailability`, ghi bảng `placed_orders` và phát `OrderPlaced`; `billing` xử lý sự kiện và ghi `billing_receipts`. Một unit test với fake repository có thể chứng minh logic gọi hàm, nhưng không bắt được SQL sai, constraint thiếu, transaction không rollback hoặc listener không ghi dữ liệu thực.

**Nhiệm vụ:** chạy các test này trên **PostgreSQL trong Testcontainers**, dùng cùng migration SQL mà ứng dụng sẽ triển khai. Không kết nối database production hoặc giữ một PostgreSQL thủ công đang chạy ở cổng cố định.

| Kịch bản | Given | When | Then phải kiểm bằng database |
| --- | --- | --- | --- |
| DB-01 — đặt đơn thành công | SKU đủ tồn kho, order ID mới | `OrderManagement.place(...)` | Đúng một order row và một billing receipt |
| DB-02 — hết hàng | SKU được từ chối | `place(...)` | Không có order row và không có receipt |
| DB-03 — ràng buộc SQL | `amount_minor = 0` | Chèn row trực tiếp | PostgreSQL từ chối bằng constraint |
| DB-04 — lỗi listener | Listener thử nghiệm ném exception sau khi producer ghi | `place(...)` | Transaction rollback, không còn order/receipt |
| DB-05 — event được giao lại | Cùng `eventId` và payload | Publish lại cùng `OrderPlaced` | Receipt của consumer không tăng thành hai |
| DB-06 — module scope | Module `orders` với stub `inventory` | `@ApplicationModuleTest` gọi service | Bảng `placed_orders` và `PublishedEvents` đúng; không giả định billing chạy |

**Đầu ra nghiệm thu:** các test được phát hiện trong JUnit report, chạy thực sự với JDBC URL do Testcontainers cung cấp, Flyway đã áp dụng migration, asserts quan sát **committed state**, và CI FAIL khi một hành vi hoặc cấu trúc module bị vi phạm.

**Giới hạn:** Bài này tập trung **database integration verification**. PostgreSQL Testcontainers giúp kiểm SQL/constraint/transaction thật, nhưng bản thân nó không tự chứng minh broker delivery, exactly-once processing, distributed transaction hoặc hiệu năng production.

## 2. Cấu hình build và hạ tầng Testcontainers cần thiết

### 2.1. Chọn một stack phiên bản tương thích

Ví dụ sử dụng Java 21, Spring Boot 3.x có `@ServiceConnection`, Spring Modulith test support, JDBC, PostgreSQL, Flyway và JUnit Jupiter. Dùng BOM/parent của phiên bản đã chọn để quản lý versions; **không** ghép ngẫu nhiên Spring Boot/Modulith/Flyway/Testcontainers từ các bài viết khác nhau.

Các phần phụ thuộc quan trọng của `pom.xml` (đặt bên trong `<dependencies>`; parent/BOM đã có):

```xml
<!-- Runtime: JDBC và migration thật. -->
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-jdbc</artifactId>
</dependency>
<dependency>
    <groupId>org.postgresql</groupId>
    <artifactId>postgresql</artifactId>
    <scope>runtime</scope>
</dependency>
<dependency>
    <groupId>org.flywaydb</groupId>
    <artifactId>flyway-core</artifactId>
</dependency>
<!-- Cần với những thế hệ Flyway tách database support PostgreSQL. -->
<dependency>
    <groupId>org.flywaydb</groupId>
    <artifactId>flyway-database-postgresql</artifactId>
</dependency>

<!-- Spring Modulith core + test. -->
<dependency>
    <groupId>org.springframework.modulith</groupId>
    <artifactId>spring-modulith-starter-core</artifactId>
</dependency>
<dependency>
    <groupId>org.springframework.modulith</groupId>
    <artifactId>spring-modulith-starter-test</artifactId>
    <scope>test</scope>
</dependency>

<!-- Integration test với Spring-managed Testcontainers bean. -->
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-test</artifactId>
    <scope>test</scope>
</dependency>
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-testcontainers</artifactId>
    <scope>test</scope>
</dependency>
<dependency>
    <groupId>org.testcontainers</groupId>
    <artifactId>postgresql</artifactId>
    <scope>test</scope>
</dependency>
```

Spring Modulith cần BOM tương thích với Spring Boot parent. Đoạn trên là **dependency fragment**, không phải một POM đầy đủ. Nếu ứng dụng còn dùng web, thêm `spring-boot-starter-web`; nó **không bắt buộc** để test service/database trực tiếp như bài này.

### 2.2. Máy chạy test phải có container runtime

- Docker Engine, Docker Desktop hoặc một runtime được Testcontainers cấu hình/hỗ trợ.
- Quyền khởi chạy container và tải image `postgres:16-alpine` hoặc một PostgreSQL image được tổ chức cho phép.
- Tài nguyên CPU/RAM và kết nối image registry phù hợp.
- Không cần cài PostgreSQL trực tiếp, không tạo database test trong cluster production.

Nếu không có container runtime, test cần báo lỗi rõ, **không** im lặng chuyển sang H2 và vẫn được coi là gate PostgreSQL PASS.

### 2.3. Chọn test class names để build thực sự chạy

Trong bài này, đặt các class tên kết thúc bằng `Test`, ví dụ `ShopDatabasePostgresTest`, `OrderRollbackPostgresTest`, `OrdersModulePostgresTest`. Điều đó phù hợp với quy ước discovery phổ biến của Maven Surefire/JUnit Platform. Nếu đội dùng suffix `*IT`, cần cấu hình Maven Failsafe hoặc Gradle `integrationTest` task và nối vào CI quality gate.

### 2.4. Cấu hình datasource: không hardcode host hoặc port

Không viết:

```yaml
# Anti-pattern trong integration test Testcontainers:
spring:
  datasource:
    url: jdbc:postgresql://localhost:5432/shop_test
    username: postgres
    password: secret
```

Một container có thể dùng host/mapped port động. Cấu hình tĩnh dễ trỏ nhầm tới database ngoài container. Thay vào đó, `@ServiceConnection` ở mục 5 sẽ cung cấp connection details cho Spring Boot/Flyway.

## 3. Dùng migration thật: PostgreSQL schema là điều kiện của test

### 3.1. Một migration V1 có ownership rõ

Tạo `src/main/resources/db/migration/V1__create_order_and_billing_tables.sql`:

```sql
-- Bảng thuộc module orders.
CREATE TABLE placed_orders (
    id UUID PRIMARY KEY,
    sku VARCHAR(64) NOT NULL,
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    amount_minor BIGINT NOT NULL CHECK (amount_minor > 0),
    placed_at TIMESTAMPTZ NOT NULL
);

-- Bảng thuộc module billing. order_id là opaque reference.
CREATE TABLE billing_receipts (
    consumer_name VARCHAR(64) NOT NULL,
    event_id UUID NOT NULL,
    order_id UUID NOT NULL,
    amount_minor BIGINT NOT NULL CHECK (amount_minor > 0),
    PRIMARY KEY (consumer_name, event_id)
);
```

Không thêm khóa ngoại tới `placed_orders` chỉ để “làm dữ liệu giống thật”: cross-module FK cần được review về schema ownership, lifecycle và sự kiện eventual. Với ví dụ synchronous trong một database, `order_id` được giữ như opaque identifier trong contract public.

### 3.2. Vì sao không dựng bảng lại bằng `@Sql(CREATE TABLE...)`?

Nếu production triển khai qua Flyway nhưng test tự chạy SQL tạo bảng khác, một test xanh có thể **che** lỗi migration thiếu `NOT NULL`, sai tên cột hoặc thiếu unique constraint. Dùng đúng `V1__...sql` trên database do Testcontainers dựng; query `flyway_schema_history` hoặc log migration để kiểm có migration chạy thật.

### 3.3. Cấu hình migration và tránh init trùng

Trong `src/main/resources/application.yml` của bài thực hành:

```yaml
spring:
  application:
    name: shop-testcontainers-demo
  flyway:
    enabled: true
  sql:
    init:
      mode: never
```

Flyway được bật khi dependencies tồn tại, tìm migration trong `classpath:db/migration` theo convention. Tắt basic `schema.sql`/`data.sql` initialization để tránh tạo bảng **hai lần** nếu project cũ còn file SQL bootstrap.

Không nhúng JDBC URL hoặc credentials production vào `application.yml` của test. Với production deployment, datasource được cấp từ secret/configuration bên ngoài; với integration test, `@ServiceConnection` cấp từ container.

### 3.4. Kiểm chính DB engine và kiểu dữ liệu

PostgreSQL `UUID` và `TIMESTAMPTZ` có behavior khác vài H2 mode; lệnh `ON CONFLICT (consumer_name,event_id) DO NOTHING` ở mục 4 là PostgreSQL-specific. Chính vì vậy nên chạy DB integration test bằng PostgreSQL container. Nhưng một PostgreSQL container vẫn là **một instance kiểm thử**, không tự tương đương cấu hình production về replication, isolation hoặc tải đồng thời.

## 4. Code Java tối thiểu cho luồng order → receipt

Chỉ dựng đúng các collaborators cần chứng minh database effects. Không thêm HTTP controller, customer/payment graph hoặc broker cho kịch bản hiện tại.

### 4.1. Cấu trúc ba module

```text
src/main/java/com/example/shop/
├── ShopApplication.java
├── inventory/
│   ├── StockAvailability.java
│   └── internal/FixedStockAvailability.java
├── orders/
│   ├── PlaceOrderCommand.java
│   ├── OrderPlaced.java
│   ├── OrderManagement.java
│   └── internal/JdbcOrderStore.java
└── billing/
    └── internal/JdbcBillingListener.java

src/test/java/com/example/shop/
├── PostgresTestConfig.java
├── ShopDatabasePostgresTest.java
├── OrderRollbackPostgresTest.java
├── ModuleArchitectureTest.java
└── orders/OrdersModulePostgresTest.java
```

`src/main/java/com/example/shop/ShopApplication.java`:

```java
package com.example.shop;

import java.time.Clock;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class ShopApplication {

    public static void main(String[] args) {
        SpringApplication.run(ShopApplication.class, args);
    }

    @Bean
    Clock applicationClock() {
        return Clock.systemUTC();
    }
}
```

### 4.2. Public `inventory` API và adapter mẫu

`src/main/java/com/example/shop/inventory/StockAvailability.java`:

```java
package com.example.shop.inventory;

public interface StockAvailability {
    boolean hasStock(String sku, int quantity);
}
```

`src/main/java/com/example/shop/inventory/internal/FixedStockAvailability.java`:

```java
package com.example.shop.inventory.internal;

import com.example.shop.inventory.StockAvailability;
import org.springframework.stereotype.Component;

@Component
public class FixedStockAvailability implements StockAvailability {
    @Override
    public boolean hasStock(String sku, int quantity) {
        return "SKU-001".equals(sku)
                && quantity > 0 && quantity <= 10;
    }
}
```

Trong dự án này inventory cố ý dùng stock adapter đơn giản, **không** cần thêm bảng tồn kho. Nhờ đó test database tập trung vào hai tables ghi qua `orders` và `billing`. `orders` chỉ import `inventory.StockAvailability` public.

### 4.3. Command và public event của `orders`

`src/main/java/com/example/shop/orders/PlaceOrderCommand.java`:

```java
package com.example.shop.orders;

import java.util.UUID;

public record PlaceOrderCommand(
        UUID orderId, String sku, int quantity, long amountMinor
) {
    public PlaceOrderCommand {
        if (orderId == null || sku == null || sku.isBlank()
                || quantity <= 0 || amountMinor <= 0) {
            throw new IllegalArgumentException("INVALID_ORDER");
        }
    }
}
```

`src/main/java/com/example/shop/orders/OrderPlaced.java`:

```java
package com.example.shop.orders;

import java.time.Instant;
import java.util.UUID;

public record OrderPlaced(
        UUID eventId,
        UUID orderId,
        String sku,
        int quantity,
        long amountMinor,
        Instant occurredAt
) {}
```

`eventId` khác `orderId`: sự kiện được gửi lại vẫn có `eventId` cũ, còn một sự kiện nghiệp vụ mới có ID riêng. `amountMinor` là số nguyên đơn vị nhỏ nhất theo hợp đồng giả định, không phải `double`; code mẫu chưa xử lý nhiều currency.

### 4.4. Repository JDBC do `orders` sở hữu

`src/main/java/com/example/shop/orders/internal/JdbcOrderStore.java`:

```java
package com.example.shop.orders.internal;

import java.sql.Timestamp;
import java.time.Instant;
import java.util.UUID;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

@Repository
public class JdbcOrderStore {

    private final JdbcTemplate jdbc;

    public JdbcOrderStore(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public void save(UUID orderId, String sku, int quantity,
                     long amountMinor, Instant placedAt) {
        jdbc.update(
            "INSERT INTO placed_orders "
                + "(id, sku, quantity, amount_minor, placed_at) "
                + "VALUES (?, ?, ?, ?, ?)",
            orderId, sku, quantity, amountMinor,
            Timestamp.from(placedAt)
        );
    }
}
```

`JdbcOrderStore` nằm trong `orders.internal` nhưng `OrderManagement` cùng module được phép dùng nó. Module `billing` không import repository của `orders`.

### 4.5. Application service có transaction và event publication

`src/main/java/com/example/shop/orders/OrderManagement.java`:

```java
package com.example.shop.orders;

import java.time.Clock;
import java.time.Instant;
import java.util.UUID;
import com.example.shop.inventory.StockAvailability;
import com.example.shop.orders.internal.JdbcOrderStore;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderManagement {

    private final StockAvailability stock;
    private final JdbcOrderStore store;
    private final ApplicationEventPublisher publisher;
    private final Clock clock;

    public OrderManagement(
            StockAvailability stock,
            JdbcOrderStore store,
            ApplicationEventPublisher publisher,
            Clock clock) {
        this.stock = stock;
        this.store = store;
        this.publisher = publisher;
        this.clock = clock;
    }

    @Transactional
    public OrderPlaced place(PlaceOrderCommand command) {
        if (!stock.hasStock(command.sku(), command.quantity())) {
            throw new IllegalStateException("OUT_OF_STOCK");
        }

        Instant now = clock.instant();
        store.save(command.orderId(), command.sku(), command.quantity(),
                command.amountMinor(), now);

        OrderPlaced event = new OrderPlaced(
                UUID.randomUUID(), command.orderId(),
                command.sku(), command.quantity(),
                command.amountMinor(), now
        );
        publisher.publishEvent(event);
        return event;
    }
}
```

### 4.6. Synchronous listener do `billing` sở hữu

`src/main/java/com/example/shop/billing/internal/JdbcBillingListener.java`:

```java
package com.example.shop.billing.internal;

import com.example.shop.orders.OrderPlaced;
import org.springframework.context.event.EventListener;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Component;

@Component
public class JdbcBillingListener {

    private final JdbcTemplate jdbc;

    public JdbcBillingListener(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @EventListener
    public void on(OrderPlaced event) {
        jdbc.update(
            "INSERT INTO billing_receipts "
                + "(consumer_name, event_id, order_id, amount_minor) "
                + "VALUES (?, ?, ?, ?) "
                + "ON CONFLICT (consumer_name, event_id) DO NOTHING",
            "billing", event.eventId(),
            event.orderId(), event.amountMinor()
        );
    }
}
```

Với Spring event multicaster synchronous mặc định, listener được gọi trong luồng `publishEvent`. `JdbcTemplate` dùng cùng DataSource và tham gia transaction đang mở nếu service được gọi qua Spring proxy. Một runtime exception từ listener sẽ khiến transaction có thể rollback. **Không thay sang async/after-commit listener rồi giữ nguyên các giả định này.**

`ON CONFLICT DO NOTHING` minh họa receipt dedup cho **cùng consumer/eventId**, nhưng chưa đối chiếu payload khi eventId bị tái sử dụng với nội dung khác; production consumer cần chính sách phát hiện conflict và xử lý business effect trong cùng transaction phù hợp.

## 5. Khởi tạo PostgreSQL bằng `@ServiceConnection` trong test

### 5.1. Test-only container configuration

Tạo `src/test/java/com/example/shop/PostgresTestConfig.java`:

```java
package com.example.shop;

import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.boot.testcontainers.service.connection.ServiceConnection;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Primary;
import org.testcontainers.containers.PostgreSQLContainer;

@TestConfiguration(proxyBeanMethods = false)
public class PostgresTestConfig {

    @Bean
    @ServiceConnection
    PostgreSQLContainer<?> postgresContainer() {
        return new PostgreSQLContainer<>("postgres:16-alpine")
                .withDatabaseName("shop_it")
                .withUsername("shop_test")
                .withPassword("test_only_password");
    }

    @Bean
    @Primary
    Clock fixedDbTestClock() {
        return Clock.fixed(
                Instant.parse("2026-01-01T09:00:00Z"),
                ZoneOffset.UTC
        );
    }
}
```

Đây là pattern **Spring-managed Testcontainers bean**: Spring Boot test support quản lý lifecycle container; `@ServiceConnection` nhận dạng `PostgreSQLContainer` và tạo connection details cho DataSource/Flyway. Không đặt `@Container`/`@Testcontainers` của JUnit extension lên bean này — đó là **pattern khác**.

Test password trong code trên chỉ dành cho **container dùng một lần**, không phải credential production. Không copy database dump hoặc secrets thật vào image.

### 5.2. Import rõ ràng ở từng test context

```java
@SpringBootTest
@Import(PostgresTestConfig.class)
class ShopDatabasePostgresTest {
    // Các test ở mục 6.
}
```

Đây là một **fragment annotation** cho class hoàn chỉnh ở mục tiếp theo. `@TestConfiguration` không được chủ động component scan như production configuration, nên `@Import` làm nguồn cấu hình container rõ ràng trong test.

Một `ApplicationContext` được Spring test cache có thể tái sử dụng container bean theo cấu hình; hai contexts khác nhau có thể tạo hai containers khác nhau. **Không giả định** mỗi JUnit method tự có database hoàn toàn sạch chỉ vì dùng Testcontainers. Vẫn cần ID scenario riêng và cleanup hoặc transaction isolation.

### 5.3. Cách chứng minh đang dùng PostgreSQL, không dùng H2

Trong test có `@Autowired JdbcTemplate jdbc`:

```java
String dbProduct = jdbc.execute(
        (java.sql.Connection conn) ->
                conn.getMetaData().getDatabaseProductName());

assertEquals("PostgreSQL", dbProduct);
```

Đây là **fragment JUnit** cần `assertEquals` import. Đặt một assertion engine trong full integration test giúp tránh tình trạng “Testcontainers không boot nhưng test vẫn xanh vì fallback sang H2”. Có thể kiểm thêm Flyway history:

```java
Integer migrations = jdbc.queryForObject(
    "SELECT COUNT(*) FROM flyway_schema_history WHERE success = TRUE",
    Integer.class);
assertTrue(migrations >= 1);
```

Đoạn trên giả định Flyway đang giữ history trong schema mặc định; nếu đổi `spring.flyway.table` hoặc schema history, phải query đúng cấu hình thực tế.

### 5.4. Phương án khác: `@Testcontainers` + `@DynamicPropertySource`

Khi dự án chưa dùng Spring Boot `@ServiceConnection` hoặc muốn lifecycle do JUnit extension quản lý, có thể dùng pattern **thay thế**, không kết hợp cả hai cho cùng container:

```java
@Testcontainers
@SpringBootTest
class AlternativePostgresTest {

    @Container
    static PostgreSQLContainer<?> postgres =
            new PostgreSQLContainer<>("postgres:16-alpine");

    @DynamicPropertySource
    static void datasource(DynamicPropertyRegistry registry) {
        registry.add(
                "spring.datasource.url", postgres::getJdbcUrl);
        registry.add(
                "spring.datasource.username", postgres::getUsername);
        registry.add(
                "spring.datasource.password", postgres::getPassword);
    }
}
```

Đoạn **minh họa phương án khác** cần các imports Spring Test, Testcontainers JUnit Jupiter và dependency `org.testcontainers:junit-jupiter`. Khi chọn pattern này, test phải bảo đảm Flyway dùng cùng DataSource. Với bài chính, ta dùng `@ServiceConnection` ở mục 5.1 và không dán class alternative vào project.

### 5.5. Vì sao không dùng một container static chung cho toàn bộ test suite?

Container dùng lại có thể giảm thời gian boot, nhưng chia sẻ database state khiến tests phụ thuộc thứ tự. Nếu muốn tối ưu, cần quản lý **schema per test class, IDs riêng, transaction/cleanup**, và không để test thay đổi migration history của test khác. Tối ưu sau khi đã chứng minh tests độc lập trên môi trường CI.

## 6. Full integration test: cùng transaction tạo order và billing receipt

### 6.1. JUnit quan sát trạng thái đã commit

Tạo `src/test/java/com/example/shop/ShopDatabasePostgresTest.java`:

```java
package com.example.shop;

import static org.junit.jupiter.api.Assertions.*;

import java.sql.Timestamp;
import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.annotation.Import;
import org.springframework.jdbc.core.JdbcTemplate;
import com.example.shop.orders.OrderManagement;
import com.example.shop.orders.OrderPlaced;
import com.example.shop.orders.PlaceOrderCommand;

@SpringBootTest
@Import(PostgresTestConfig.class)
class ShopDatabasePostgresTest {

    @Autowired
    OrderManagement orders;

    @Autowired
    JdbcTemplate jdbc;

    @Autowired
    ApplicationEventPublisher publisher;

    private int orderRows(UUID id) {
        return jdbc.queryForObject(
            "SELECT COUNT(*) FROM placed_orders WHERE id = ?",
            Integer.class, id);
    }

    private int receiptRows(UUID orderId) {
        return jdbc.queryForObject(
            "SELECT COUNT(*) FROM billing_receipts WHERE order_id = ?",
            Integer.class, orderId);
    }

    private void removeScenario(UUID id) {
        jdbc.update(
                "DELETE FROM billing_receipts WHERE order_id = ?", id);
        jdbc.update(
                "DELETE FROM placed_orders WHERE id = ?", id);
    }

    @Test
    void storesOrderAndBillingReceiptOnPostgres() {
        UUID orderId = UUID.randomUUID();
        PlaceOrderCommand command =
                new PlaceOrderCommand(orderId, "SKU-001", 2, 1599L);

        try {
            OrderPlaced published = orders.place(command);

            assertEquals(orderId, published.orderId());
            assertNotEquals(orderId, published.eventId());
            assertEquals(1, orderRows(orderId));
            assertEquals(1, receiptRows(orderId));

            Long storedAmount = jdbc.queryForObject(
                "SELECT amount_minor FROM placed_orders WHERE id = ?",
                Long.class, orderId);
            assertNotNull(storedAmount);
            assertEquals(1599L, storedAmount.longValue());

            Timestamp storedTime = jdbc.queryForObject(
                "SELECT placed_at FROM placed_orders WHERE id = ?",
                Timestamp.class, orderId);
            assertNotNull(storedTime);
            assertEquals(published.occurredAt(),
                    storedTime.toInstant());

            UUID recordedEventId = jdbc.queryForObject(
                "SELECT event_id FROM billing_receipts "
                    + "WHERE order_id = ?",
                UUID.class, orderId);
            assertEquals(published.eventId(), recordedEventId);
        } finally {
            removeScenario(orderId);
        }
    }

    @Test
    void outOfStockLeavesNoOrderOrReceipt() {
        UUID orderId = UUID.randomUUID();

        try {
            IllegalStateException failure = assertThrows(
                IllegalStateException.class,
                () -> orders.place(new PlaceOrderCommand(
                        orderId, "SKU-OUT", 1, 999L)));

            assertEquals("OUT_OF_STOCK", failure.getMessage());
            assertEquals(0, orderRows(orderId));
            assertEquals(0, receiptRows(orderId));
        } finally {
            removeScenario(orderId);
        }
    }

    @Test
    void redeliveryOfSameEventDoesNotDuplicateReceipt() {
        UUID orderId = UUID.randomUUID();

        try {
            OrderPlaced event = orders.place(
                    new PlaceOrderCommand(
                            orderId, "SKU-001", 1, 1000L));

            // Mô phỏng redelivery đúng cùng eventId/payload.
            publisher.publishEvent(event);

            assertEquals(1, orderRows(orderId));
            assertEquals(1, receiptRows(orderId));

            UUID storedId = jdbc.queryForObject(
                "SELECT event_id FROM billing_receipts "
                    + "WHERE order_id = ?",
                UUID.class, orderId);
            assertEquals(event.eventId(), storedId);
        } finally {
            removeScenario(orderId);
        }
    }
}
```

**Vì sao không đặt `@Transactional` trên test class?** Nếu JUnit method được bọc trong một transaction do framework rollback cuối test, query trên **cùng connection** có thể thấy writes chưa commit và tạo ảo giác rằng producer/billing đã commit thành công. Ở đây service được gọi qua Spring-managed proxy; khi method `orders.place(...)` trả về, transaction service đã kết thúc, rồi test query bằng JDBC ngoài transaction test.

### 6.2. Kiểm chứng thực chất của ba tests

| Test | Điều khẳng định | Lỗi nó có thể phát hiện |
| --- | --- | --- |
| Thành công | DB row + receipt, amount, timestamp và event ID liên kết | SQL mapping sai, thiếu listener, không ghi DB |
| Hết hàng | Zero rows sau business rejection | Save hoặc publish trước khi kiểm stock |
| Redelivery | Hai publish attempts cùng logical event, một receipt | Thiếu unique/`ON CONFLICT`, duplicate side effect |

Số lượng row được query bằng `orderId` riêng cho scenario. Assertions không phụ thuộc việc database có rows của test khác hay không. Với môi trường tests chạy song song, random UUID collision cực khó nhưng **không** thay cho quản lý schema/cleanup đúng phạm vi.

### 6.3. Định nghĩa chính xác mức dedup đã kiểm

Test redelivery chứng minh **không chèn hai `billing_receipts` cho cùng `eventId`** trong implementation demo. Nó **không** chứng minh:

- Hai events khác ID nhưng cùng order không tạo hai business charges.
- Cùng event ID nhưng semantic payload thay đổi được phát hiện.
- Hai consumer instances chạy đồng thời vẫn có đầy đủ external side effect exactly-once.
- Event còn tồn tại sau crash giữa publish và commit.

Muốn mở rộng, thêm consumer scope + payload digest/contract conflict checks, transaction receipt–business effect và concurrency tests trên PostgreSQL. Không gắn nhãn “exactly-once” chỉ vì assertion `receiptRows == 1`.

### 6.4. Kiểm engine và migrations trong chính suite

Thêm một test khi setup có nguy cơ fallback:

```java
@Test
void databaseIsPostgresWithAppliedFlywayMigration() {
    String engine = jdbc.execute(
            (java.sql.Connection conn) ->
                    conn.getMetaData().getDatabaseProductName());

    assertEquals("PostgreSQL", engine);
    Integer migrations = jdbc.queryForObject(
            "SELECT COUNT(*) FROM flyway_schema_history "
                + "WHERE success = TRUE",
            Integer.class);
    assertTrue(migrations != null && migrations >= 1);
}
```

Đây là method bổ sung vào `ShopDatabasePostgresTest`, dùng chính `jdbc` đã autowire. Nếu project đổi Flyway history schema/table hoặc không dùng Flyway, sửa kiểm chứng phù hợp; **đừng** bỏ engine check rồi tiếp tục gọi đó là PostgreSQL integration suite.

## 7. PostgreSQL constraint và rollback: ép lỗi ở đúng thời điểm

### 7.1. Kiểm database rule ở database, không chỉ constructor Java

Constructor `PlaceOrderCommand` từ chối `amountMinor <= 0`; gọi constructor với 0 chỉ kiểm application validation. Muốn biết migration đã tạo `CHECK (amount_minor > 0)`, phải gửi một giá trị sai **trực tiếp vào PostgreSQL**.

Thêm vào `ShopDatabasePostgresTest`:

```java
@Test
void postgresRejectsInvalidAmountRegardlessOfJavaValidation() {
    UUID orderId = UUID.randomUUID();

    try {
        assertThrows(
            org.springframework.dao.DataIntegrityViolationException.class,
            () -> jdbc.update(
                "INSERT INTO placed_orders "
                    + "(id, sku, quantity, amount_minor, placed_at) "
                    + "VALUES (?, ?, ?, ?, ?)",
                orderId, "SKU-001", 1, 0L,
                Timestamp.from(
                    java.time.Instant.parse("2026-01-01T09:00:00Z"))
            )
        );

        assertEquals(0, orderRows(orderId));
    } finally {
        removeScenario(orderId);
    }
}
```

Vì test method **không** dùng `@Transactional` bao ngoài, statement lỗi ở auto-commit transaction không giữ toàn bộ test transaction PostgreSQL ở trạng thái aborted. Nếu bạn thêm `@Transactional` cho test rồi bắt `DataIntegrityViolationException` bên trong, các câu SQL kế tiếp trên cùng transaction có thể nhận lỗi `current transaction is aborted`; lúc đó cần thiết kế transaction boundary/rollback phù hợp.

**Chống false positive:** `DataIntegrityViolationException` có thể đến từ nhiều constraints. Trong test quan trọng, kiểm SQLState/constraint name theo driver và tạo **positive control** insert cùng các fields trừ `amount_minor`; không chỉ assert có exception rồi kết luận đúng CHECK đã chạy. Mục tiêu là kiểm **constraint mong đợi**, không phải một lỗi ngẫu nhiên khác.

### 7.2. Fault injection sau khi order đã được insert

Nếu lỗi xảy ra ở listener `billing` sau khi `orders` đã insert row, transaction có rollback cả hai bảng không? Thêm một **test-only event listener** ném runtime exception. Không đổi code production chỉ để tạo lỗi.

`src/test/java/com/example/shop/OrderRollbackPostgresTest.java`:

```java
package com.example.shop;

import static org.junit.jupiter.api.Assertions.*;

import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Import;
import org.springframework.context.event.EventListener;
import org.springframework.jdbc.core.JdbcTemplate;
import com.example.shop.orders.OrderManagement;
import com.example.shop.orders.OrderPlaced;
import com.example.shop.orders.PlaceOrderCommand;

@SpringBootTest
@Import({
        PostgresTestConfig.class,
        OrderRollbackPostgresTest.FailureOnlyInTest.class
})
class OrderRollbackPostgresTest {

    @TestConfiguration(proxyBeanMethods = false)
    static class FailureOnlyInTest {

        @Bean
        ThrowingListener throwingOrderPlacedListener() {
            return new ThrowingListener();
        }
    }

    static class ThrowingListener {

        @EventListener
        public void on(OrderPlaced event) {
            throw new IllegalStateException("TEST_LISTENER_FAILURE");
        }
    }

    @Autowired
    OrderManagement orders;

    @Autowired
    JdbcTemplate jdbc;

    private int count(String table, UUID orderId) {
        String sql = switch (table) {
            case "placed_orders" ->
                "SELECT COUNT(*) FROM placed_orders WHERE id = ?";
            case "billing_receipts" ->
                "SELECT COUNT(*) FROM billing_receipts WHERE order_id = ?";
            default -> throw new IllegalArgumentException("Invalid table");
        };
        return jdbc.queryForObject(sql, Integer.class, orderId);
    }

    @Test
    void listenerFailureRollsBackOrderAndAnyReceipt() {
        UUID id = UUID.randomUUID();
        try {
            IllegalStateException failure = assertThrows(
                IllegalStateException.class,
                () -> orders.place(new PlaceOrderCommand(
                        id, "SKU-001", 2, 1599L)));

            assertEquals(
                    "TEST_LISTENER_FAILURE", failure.getMessage());
            assertEquals(0, count("placed_orders", id));
            assertEquals(0, count("billing_receipts", id));
        } finally {
            jdbc.update(
                "DELETE FROM billing_receipts WHERE order_id = ?", id);
            jdbc.update(
                "DELETE FROM placed_orders WHERE id = ?", id);
        }
    }
}
```

**Bằng chứng thu được:** Order row được insert trước `publishEvent`; một synchronous listener ném exception; `@Transactional` trên Spring-managed `OrderManagement` rollback, nên khi method trả exception, test truy vấn PostgreSQL thấy không còn order row. Nếu listener `billing` đã ghi receipt trước khi listener lỗi được gọi, receipt cũng phải rollback vì cùng transaction.

**Giới hạn quan trọng:** Thứ tự gọi listeners không được bảo đảm theo ví dụ, nên test không khẳng định `JdbcBillingListener` đã ghi receipt **trước** fault. Nó khẳng định trạng thái cuối là 0/0 và fault sau order insert. Muốn chứng minh riêng **receipt đã ghi rồi bị rollback**, cần một test harness kiểm soát ordering (`@Order`, transaction observers, instrumentation) phù hợp runtime; không suy thêm từ một assertion 0/0.

### 7.3. Khác biệt khi thay listener bằng after-commit/async

Nếu đổi sang `@TransactionalEventListener(phase = AFTER_COMMIT)`, `@ApplicationModuleListener` hoặc broker asynchronous:

- Order transaction có thể đã commit **trước** khi billing listener chạy.
- Billing failure sau commit không thể rollback transaction order ban đầu theo cách ở mục 7.2.
- Test phải đợi hiệu ứng theo ID/timeout và kiểm retry/idempotency.
- Cần publication registry/outbox hoặc cơ chế bền vững phù hợp nếu có yêu cầu tránh mất event.

Không giữ nguyên test “0 order/0 receipt sau khi listener fail” mà đổi annotation bất đồng bộ rồi cho rằng thiết kế mới bị lỗi; khi kiến trúc giao dịch thay đổi, **expected behavior cũng phải được định nghĩa lại**.

## 8. `@ApplicationModuleTest` dùng PostgreSQL container và `PublishedEvents`

Full integration test ở mục 6 boot cả ba modules; còn `@ApplicationModuleTest` kiểm **module `orders`** với dependency từ `inventory` được thay bằng public test stub. Vẫn dùng PostgreSQL thật vì `orders.internal.JdbcOrderStore` là production bean cần kiểm mapping.

### 8.1. Test orders module độc lập với billing listener

`src/test/java/com/example/shop/orders/OrdersModulePostgresTest.java`:

```java
package com.example.shop.orders;

import static org.assertj.core.api.Assertions.assertThat;

import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Import;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.modulith.test.ApplicationModuleTest;
import org.springframework.modulith.test.PublishedEvents;
import com.example.shop.PostgresTestConfig;
import com.example.shop.inventory.StockAvailability;

@ApplicationModuleTest
@Import({
        PostgresTestConfig.class,
        OrdersModulePostgresTest.StockStub.class
})
class OrdersModulePostgresTest {

    @TestConfiguration(proxyBeanMethods = false)
    static class StockStub {

        @Bean
        StockAvailability availableStockForModuleTest() {
            return (sku, quantity) -> true;
        }
    }

    @Autowired
    OrderManagement orders;

    @Autowired
    JdbcTemplate jdbc;

    @Test
    void databaseRowAndPublishedEventAgree(
            PublishedEvents events) {
        UUID orderId = UUID.randomUUID();
        PlaceOrderCommand command =
                new PlaceOrderCommand(orderId, "SKU-TEST", 3, 3000L);

        try {
            OrderPlaced returned = orders.place(command);

            assertThat(returned.orderId()).isEqualTo(orderId);
            assertThat(returned.sku()).isEqualTo("SKU-TEST");
            assertThat(returned.quantity()).isEqualTo(3);

            Long persistedAmount = jdbc.queryForObject(
                "SELECT amount_minor FROM placed_orders WHERE id = ?",
                Long.class, orderId);
            assertThat(persistedAmount).isEqualTo(3000L);

            assertThat(events.ofType(OrderPlaced.class))
                    .anySatisfy(event -> {
                        assertThat(event.orderId()).isEqualTo(orderId);
                        assertThat(event.eventId())
                                .isEqualTo(returned.eventId());
                        assertThat(event.amountMinor()).isEqualTo(3000L);
                    });

            Integer receiptCount = jdbc.queryForObject(
                "SELECT COUNT(*) FROM billing_receipts "
                    + "WHERE order_id = ?",
                Integer.class, orderId);
            assertThat(receiptCount).isZero();
        } finally {
            jdbc.update(
                "DELETE FROM billing_receipts WHERE order_id = ?",
                orderId);
            jdbc.update(
                "DELETE FROM placed_orders WHERE id = ?",
                orderId);
        }
    }
}
```

**Tại sao vẫn có bảng billing trong DB?** Flyway chạy migration của ứng dụng vào database mới, bao gồm cả hai bảng; nhưng `@ApplicationModuleTest` mặc định bootstrap **beans của module orders** chứ không boot consumer `billing`. Do đó với test isolation mặc định, receipt count cho order ID này bằng 0. Database chứa schema của nhiều modules **không đồng nghĩa** listener của module khác đã được boot.

### 8.2. Test này bảo vệ những gì?

| Phần | Được chứng minh | Không được chứng minh |
| --- | --- | --- |
| `@ApplicationModuleTest` | Service và repository orders chạy trong context phạm vi module | Billing subscriber/full flow |
| PostgreSQL + Flyway | SQL mapping và bảng `placed_orders` có thật | Distributed database semantics |
| `PublishedEvents` | Event được publish với ID/amount đúng | Consumer đã commit receipt |
| `StockAvailability` stub | Module orders gọi public inventory port | Inventory adapter/stock DB thật |
| Receipt count 0 | Trong test này không có effect của billing listener | Production không có billing hoặc event bị mất |

`anySatisfy` chỉ kiểm **ít nhất một event phù hợp**. Nếu hợp đồng yêu cầu đúng một event, thêm assertion cardinality phù hợp API `PublishedEvents` hiện dùng, không suy từ `anySatisfy`.

### 8.3. Thêm architectural test không cần container

`src/test/java/com/example/shop/ModuleArchitectureTest.java`:

```java
package com.example.shop;

import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

class ModuleArchitectureTest {

    @Test
    void verifiesBoundaries() {
        ApplicationModules.of(ShopApplication.class).verify();
    }
}
```

**Không import `PostgresTestConfig` vào structural test.** Nó chỉ phân tích module dependencies, không cần JDBC. Nếu developer cho `billing` import `orders.internal.JdbcOrderStore` hoặc tạo chu trình module, `verify()` phải FAIL dù các PostgreSQL tests có thể vẫn PASS. Ngược lại, `verify()` PASS không bảo đảm Flyway/SQL đúng.

### 8.4. Quyết định tier test theo câu hỏi

```text
Structural:
  ApplicationModules.verify()
  Không cần PostgreSQL container.

Module + DB:
  @ApplicationModuleTest(orders)
  PostgreSQL + Flyway + PublishedEvents
  Stub StockAvailability qua public API.

Full integration:
  @SpringBootTest
  PostgreSQL + Flyway + 3 modules
  Kiểm order/receipt sau transaction commit.
```

Đây là ba bằng chứng bổ sung, không nên dồn thành **một** `@SpringBootTest` đồ sộ rồi bỏ structural/module tests.

## 9. Cô lập test data, lifecycle container và transaction boundary

Testcontainers tạo database phù hợp với runtime, **không tự làm data isolation ở cấp JUnit method**. Việc Spring cache `ApplicationContext`, tái sử dụng container hoặc chạy tests song song có thể để lại rows và tạo false positive/false negative nếu fixture không được quản lý.

### 9.1. Một bảng quyết định isolation

| Tình huống | Cách làm nên chọn | Không nên suy |
| --- | --- | --- |
| Một test insert một order | UUID riêng, query/cleanup bằng ID đó | Database luôn trống vì container mới |
| Test fail trước khi cleanup | `try/finally` + database/schema reset khi cần | `@DirtiesContext` tự xóa mọi DB row |
| Tests được chạy song song | IDs riêng, tránh xóa cả bảng, kiểm transaction scopes | `DELETE FROM placed_orders` không có `WHERE` là an toàn |
| Module và full integration contexts | Container bean được import đúng context | Hai contexts luôn có cùng lifecycle/container |
| Retry cùng event | Giữ nguyên `eventId` và semantic payload | Tạo UUID event mới vẫn là redelivery |
| DB constraint negative case | Chạy statement lỗi ngoài test transaction hoặc xử lý rollback rõ | Có thể tiếp tục SQL trong PostgreSQL transaction đã aborted |
| Assert committed state | Không gắn `@Transactional` trên test khi muốn thấy commit của service | Thấy row trên cùng test connection đồng nghĩa commit |

### 9.2. `@Transactional` trên service và trên test là hai điều khác nhau

```text
Không có @Transactional trên JUnit method:

  Test -> Spring proxy OrderManagement.place(...)
         BEGIN
         INSERT placed_orders
         PUBLISH synchronous OrderPlaced
         INSERT billing_receipts
         COMMIT
  Test -> SELECT rows (transaction khác)
         Assert committed state

Có @Transactional trên JUnit method:

  Test BEGIN
    -> place(...) tham gia transaction test
    -> SELECT thấy uncommitted rows của cùng transaction
  Test ROLLBACK
```

Đừng dùng test thứ hai để kết luận service đã commit hai bảng. Nó phù hợp cho những test cần rollback isolation, nhưng **không** phù hợp để chứng minh thời điểm commit hoặc semantics listener sau commit.

### 9.3. Tại sao không dùng `@DirtiesContext` để “sửa” stale data?

`@DirtiesContext` làm Spring context bị loại khỏi cache; với container bean, có thể khiến container bị dừng và tạo context/database mới ở lần sau. Nó có chi phí khởi động và **không phải** cơ chế dọn dữ liệu được thiết kế cho mọi chiến lược Testcontainers. Nếu vấn đề là test tạo row không cleanup đúng ID, hãy sửa data isolation trước.

### 9.4. Khác biệt giữa test-only seed và migration

Migrations làm **schema đúng**. Fixtures làm **scenario state đúng**. Không đặt 10,000 orders trong `V1__...sql` chỉ để một test có data; điều đó khiến mọi context phải load dataset nặng và tests phụ thuộc state ban đầu.

Với database test nhỏ:

1. Flyway tạo schema và constraints.
2. Test method cấp `orderId` và `eventId` theo case.
3. Gọi production service hoặc insert seed có chủ đích đúng tầng.
4. Query theo ID để assert.
5. Cleanup đúng các rows của scenario.

Nếu cần migration compatibility với dữ liệu lịch sử, tạo một **database riêng ở phiên bản cũ**, seed V1 rows, rồi chạy migration mới. Không dùng DB đã auto-migrate V2 trước `@BeforeEach` để giả lập “V1 → V2”.

### 9.5. Tối ưu Testcontainers chỉ sau khi tests đúng

Một container image mới có thể cần pull lần đầu, rồi startup PostgreSQL/Flyway trước khi test chạy. Tối ưu hợp lệ:

- Giữ test classes cùng loại context khi có thể để tận dụng Spring context cache.
- Dùng Testcontainers reusable mode **chỉ** với chính sách isolation/cleanup phù hợp; không coi nó là default an toàn cho CI.
- Tránh mở nhiều containers cho một scenario không cần multi-DB.
- Chia unit/structural tests (không dùng container) với DB integration tests (cần container) để lỗi được phân loại rõ.

**Không đổi PostgreSQL sang H2 chỉ để rút thời gian CI** nếu mục tiêu của bài là kiểm PostgreSQL-specific SQL, constraint và transaction.

## 10. Chạy bằng Maven/Gradle và thiết lập CI quality gate

### 10.1. Lệnh chạy local theo một build tool

Maven Wrapper:

```bash
# Structural test: không khởi động database container.
./mvnw -B -Dtest=ModuleArchitectureTest test

# Chạy database integration tests được đặt tên *Test.
./mvnw -B -Dtest=ShopDatabasePostgresTest,OrderRollbackPostgresTest,OrdersModulePostgresTest test

# Chạy toàn bộ quality gate đã được nối vào lifecycle.
./mvnw -B verify
```

Nếu project dùng Gradle với `useJUnitPlatform()`:

```bash
./gradlew test --tests 'com.example.shop.ShopDatabasePostgresTest'
./gradlew test --tests 'com.example.shop.OrderRollbackPostgresTest'
./gradlew test --tests 'com.example.shop.orders.OrdersModulePostgresTest'
./gradlew check
```

Không cần chạy cả Maven và Gradle. Với Gradle custom `integrationTest` task, phải nối vào `check` hoặc CI required jobs; với Maven classes tên `*IT`, cấu hình Failsafe/plugin lifecycle thích hợp. Đừng đổi tên lớp test khiến JUnit không được phát hiện rồi thấy build xanh.

### 10.2. CI workflow minh họa

Ví dụ GitHub Actions chạy trên runner có Docker:

```yaml
name: modulith-postgres-test

on:
  push:
  pull_request:

jobs:
  verify:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: "21"
          cache: maven
      - name: Run architecture, module and PostgreSQL tests
        run: ./mvnw -B verify
```

Workflow thuộc **project thực hành**; chỉ copy khi repository có Maven Wrapper, build dependencies và Docker-compatible runner. Với hệ thống CI doanh nghiệp, pin actions theo security policy, cấu hình cache/registry và đặt job `verify` làm **required check**. CI không cần khởi tạo PostgreSQL service riêng trên fixed port khi Testcontainers đã quản lý container.

### 10.3. Bằng chứng tối thiểu phải có trong JUnit report

| Test class | Evidence |
| --- | --- |
| `ModuleArchitectureTest` | `verify()` executed và PASS |
| `ShopDatabasePostgresTest` | Happy path, out-of-stock, redelivery, constraint, PostgreSQL engine test được chạy |
| `OrderRollbackPostgresTest` | Fault injection rollback test executed |
| `OrdersModulePostgresTest` | `@ApplicationModuleTest`/`PublishedEvents` và DB row check executed |
| Build/report | Không skipped/NO-SOURCE, failure tạo exit code khác 0 |

Xem `target/surefire-reports` (Maven) hoặc `build/test-results/<task>`, `build/reports/tests/<task>` (Gradle). Kiểm **tên test + số tests executed**, không chỉ dòng `BUILD SUCCESS`. Nếu Docker không có, database tests phải FAIL rõ, không được `@DisabledIfEnvironmentVariable` để biến môi trường chưa chuẩn bị thành gate xanh.

### 10.4. Triệu chứng thường gặp khi chạy Testcontainers

| Triệu chứng | Nguyên nhân cần kiểm | Hướng xử lý |
| --- | --- | --- |
| `Could not find a valid Docker environment` | Container runtime chưa chạy/không thể truy cập | Khởi động/cấp quyền Docker, xem Testcontainers runtime settings |
| Image pull bị lỗi | Mạng/registry/tag bị chặn | Dùng registry/image được phép, kiểm network; không fallback H2 |
| `Connection refused` đến localhost:5432 | Test đang dùng JDBC URL hardcode thay vì service details | Gỡ override URL, dùng `@ServiceConnection` |
| `No qualifying bean of type DataSource` | Thiếu JDBC/driver hoặc service connection | Kiểm dependencies/test config/import |
| `Flyway unsupported database` | Flyway PostgreSQL support/version thiếu | Bổ sung module DB và BOM tương thích |
| `relation "placed_orders" does not exist` | Migration chưa áp dụng hoặc schema khác | Kiểm `db/migration`, Flyway log/history, active schema |
| `relation already exists` | Có `schema.sql` và Flyway cùng tạo bảng | Chỉ chọn một cơ chế schema chính |
| `current transaction is aborted` sau insert lỗi | Bắt SQL exception trong PostgreSQL transaction chưa rollback | Kết thúc/rollback transaction trước câu SQL tiếp theo |
| Happy path có order, không receipt | Listener không được boot hoặc thành async | Kiểm `@SpringBootTest` full context và listener semantics |
| Module test có billing receipt bất ngờ | Test bootstrap mở rộng/tồn dư state | Xem scope module, schema cache, ID và cleanup |
| CI xanh nhưng PostgreSQL tests vắng mặt | Surefire/Failsafe/Gradle task không tìm thấy test | Kiểm naming và required job |

### 10.5. Khi test lỗi, đọc theo thứ tự

1. **Đã có container runtime?** Kiểm lỗi Testcontainers/Docker đầu tiên.
2. **Kết nối đúng PostgreSQL?** Assert JDBC metadata, xem connection details của test.
3. **Schema có từ migration?** Kiểm `flyway_schema_history` và DDL constraints.
4. **Service có đi qua Spring proxy?** Kiểm transaction boundary, không gọi trực tiếp object tự `new` cho DB test.
5. **Listener đang synchronous hay async?** Xác định thời điểm commit/observation đúng contract.
6. **Test data có cô lập?** UUID riêng, không cleanup toàn bảng, không để receipt cũ.
7. **JUnit report có test?** Khi không có executed tests, build xanh không chứng minh điều gì về DB.

### 10.6. Negative probes để kiểm gate thực sự nhạy

Chỉ trên nhánh thử, hoàn nguyên trước merge:

| Thay đổi cố ý | Test dự kiến FAIL |
| --- | --- |
| Xóa `CHECK (amount_minor > 0)` trong migration **trên DB sạch** | Database constraint negative test |
| Bỏ `publisher.publishEvent(event)` | Full integration receipt test; module `PublishedEvents` test |
| Bỏ `@Transactional` trên `OrderManagement.place` | Fault injection rollback test |
| Bỏ `ON CONFLICT DO NOTHING` | Duplicate redelivery test |
| Cho `billing` import `orders.internal.JdbcOrderStore` | `ModuleArchitectureTest` |

**Cẩn trọng với migration:** Không sửa migration đã triển khai trong production; negative probe chỉ thực hiện trong môi trường thực hành/branch tạm và DB container sạch. Với ứng dụng đang phát hành, thay đổi schema thông qua migration tiếp theo và test nâng cấp V1→V2 thay vì rewrite lịch sử.

## 11. Bài thực hành, checklist nghiệm thu và câu hỏi tự kiểm tra

### 11.1. Bài A — Biến test dùng H2 thành PostgreSQL Testcontainers

**Bối cảnh:** Một project cũ đang có `@SpringBootTest` với H2 và một test insert row nhưng không kiểm database engine.

Thực hiện:

1. Khai báo Testcontainers PostgreSQL, `spring-boot-testcontainers`, JDBC driver và Flyway dependencies.
2. Tạo `PostgresTestConfig` với `@Bean @ServiceConnection PostgreSQLContainer<?>`.
3. Import cấu hình test ở đúng `@SpringBootTest` class.
4. Gỡ JDBC URL tĩnh hoặc H2-only overrides trong test configuration.
5. Viết assertion `DatabaseMetaData.getDatabaseProductName() == "PostgreSQL"`.
6. Xác nhận Flyway chạy file `V1__create_order_and_billing_tables.sql`.

**Bằng chứng nộp:** JUnit report có database engine test PASS và log migration của database container, không phải PostgreSQL ngoài máy.

### 11.2. Bài B — Kiểm dữ liệu đúng sau transaction commit

Thực hiện:

1. Tạo `PlaceOrderCommand` với `orderId` mới và `SKU-001` đủ hàng.
2. Gọi Spring-managed `OrderManagement.place(...)`.
3. Assert PostgreSQL có đúng một row `placed_orders` theo `orderId`.
4. Assert receipt thuộc consumer `billing` có đúng `eventId` do service trả về.
5. Assert `amount_minor` và `placed_at` giữ giá trị đúng.
6. Lặp với `SKU-OUT`, assert exception và hai bảng không có row cho order ID đó.

**Bằng chứng nộp:** Test methods cùng SQL assertions/transaction boundaries; cleanup theo scenario ID, không xóa dữ liệu của test khác.

### 11.3. Bài C — Constraint và rollback có chủ đích

Thực hiện:

1. Chèn trực tiếp `amount_minor=0` và chứng minh PostgreSQL từ chối vì CHECK constraint.
2. Thêm test-only listener ném exception ở thời điểm nhận event.
3. Xác nhận order row đã được insert **trước khi publish**, nhưng sau exception không có committed order/receipt.
4. Trên nhánh thử, bỏ `@Transactional` khỏi service để thấy rollback test chuyển đỏ.
5. Khôi phục annotation và chạy lại suite.

**Bằng chứng nộp:** Negative test FAIL đúng nguyên nhân khi thử mutation; suite PASS lại ở code đúng. Không đưa failure injector vào source production.

### 11.4. Bài D — Module test khác full integration test thế nào?

Thực hiện:

1. Đặt `OrdersModulePostgresTest` trong package `com.example.shop.orders`.
2. Dùng `@ApplicationModuleTest`, import PostgreSQL test config và stub `StockAvailability` qua public interface.
3. Kiểm DB row `placed_orders` và `PublishedEvents` có event đúng.
4. Xác nhận `billing_receipts` không có effect cho order ID đó **khi boot ở standalone mode mặc định**.
5. So sánh với `ShopDatabasePostgresTest` boot cả ba modules và có receipt thật.
6. Chạy `ApplicationModules.verify()` riêng, không khởi động container.

**Bằng chứng nộp:** Bảng so sánh ba test tiers kèm report; giải thích vì sao structural PASS không tự chứng minh SQL/event runtime.

### 11.5. Bài E — CI và redelivery

Thực hiện:

1. Publish lại **cùng** `OrderPlaced` (giữ `eventId`), kiểm receipt vẫn bằng một.
2. Thử bỏ `ON CONFLICT DO NOTHING` và chạy lại test để xác nhận lỗi duplicate-key làm gate đỏ.
3. Khôi phục code và xác nhận engine/migration/integration tests đều được JUnit phát hiện.
4. Đưa Maven `verify` hoặc Gradle `check` đã nối integration tasks vào CI required check.
5. Ghi lại giới hạn: dedup đơn giản chưa so payload conflict và chưa xử lý durable event delivery.

**Bằng chứng nộp:** CI test report, kết quả negative probe, mô tả rõ guarantee nào đã/đang chưa kiểm.

### 11.6. Checklist nghiệm thu

**Hạ tầng và schema**

- [ ] Test chạy trên PostgreSQL image do Testcontainers quản lý, không phải host/port cố định.
- [ ] `@ServiceConnection` có hiệu lực và `DatabaseMetaData` xác nhận PostgreSQL.
- [ ] Không có H2 fallback bị nhầm thành PostgreSQL test.
- [ ] Flyway sử dụng migration của ứng dụng, không dựng bản sao schema bằng test-only SQL.
- [ ] PostgreSQL driver và Flyway database support tương thích dependency versions.
- [ ] Không dùng production credentials, production DB dump hoặc external data trong fixture.

**Hành vi và transaction**

- [ ] Order thành công được persist với đúng `orderId`, SKU, quantity, amount và timestamp.
- [ ] Billing receipt có cùng `eventId` và `orderId` mà public event công bố.
- [ ] Hết hàng không tạo order/receipt.
- [ ] PostgreSQL constraint từ chối dữ liệu invalid do test trực tiếp chèn vào.
- [ ] Listener failure sau order insert khiến transaction hiện tại rollback như contract synchronous.
- [ ] Test không có `@Transactional` ngoài service khi đang assert committed state.
- [ ] Redelivery giữ nguyên event ID/payload và không tạo receipt thứ hai.
- [ ] Không tuyên bố exactly-once hay after-commit behavior khi chưa có tests tương ứng.

**Module và CI**

- [ ] `@ApplicationModuleTest` dùng public inventory stub, không import `inventory.internal`.
- [ ] `PublishedEvents` kiểm event thật được publish từ service trong module test.
- [ ] Full `@SpringBootTest` xác minh effect của cả ba modules với PostgreSQL.
- [ ] `ApplicationModules.verify()` chạy độc lập, không cần container.
- [ ] ID/test data/cleanup được cô lập; tests không phụ thuộc execution order.
- [ ] Surefire/Gradle reports cho thấy test methods đã chạy, không `skipped` hoặc `NO-SOURCE`.
- [ ] Docker/Testcontainers không sẵn sàng làm required DB gate FAIL rõ ràng.
- [ ] CI không dùng `skipTests`, `ignoreFailures`, `|| true` hoặc `continue-on-error` để bỏ qua lỗi.
- [ ] Negative probes đã được gỡ khỏi production branch trước merge.

### 11.7. Câu hỏi tự kiểm tra

1. Tại sao một test dùng H2 PASS không đủ chứng minh `ON CONFLICT DO NOTHING` và PostgreSQL constraints đúng?
2. `@ServiceConnection` giải quyết vấn đề nào khi Testcontainers ánh xạ cổng database động?
3. Sự khác nhau giữa Spring-managed `@Bean PostgreSQLContainer` và JUnit `@Container` là gì?
4. Vì sao vẫn cần cleanup/UUID riêng khi PostgreSQL container được khởi tạo tự động?
5. Kiểm `flyway_schema_history` giúp phát hiện loại lỗi nào?
6. Vì sao không nên bao test DB committed-state bằng `@Transactional` theo quán tính?
7. Khi listener synchronous ném exception sau order insert, kết quả transaction kỳ vọng là gì?
8. Khi đổi listener sang after-commit/async, test rollback ở mục 7 cần thay đổi vì sao?
9. `@ApplicationModuleTest` có PostgreSQL thật chứng minh điều gì mà một unit fake repository không chứng minh?
10. `PublishedEvents` có chứng minh receipt đã commit trong `billing` không?
11. Vì sao trùng `eventId` và trùng `orderId` là hai tình huống khác nhau?
12. Khi CI báo `BUILD SUCCESS` nhưng không có `ShopDatabasePostgresTest` trong report, quality gate thiếu gì?
13. Thử bỏ `@Transactional` khỏi service trên branch tạm giúp kiểm tính nhạy của test nào?
14. Nếu Docker không chạy, tại sao chuyển sang H2 tự động là một kết quả sai với mục tiêu của bài?

**Ghi nhớ:** Database test bằng Testcontainers chỉ có giá trị khi thực sự dùng **PostgreSQL container + migration thật + service/repository/listener thật + assertion đọc trạng thái committed**. Trong Spring Modulith, kết hợp `@SpringBootTest` cho luồng ba module, `@ApplicationModuleTest`/`PublishedEvents` cho hợp đồng module, `ApplicationModules.verify()` cho kiến trúc tĩnh, rồi ràng buộc tất cả bằng CI required checks. Không nhầm một test H2/fake, một event được publish, hoặc một transaction test chưa commit với bằng chứng database integration đã được kiểm chứng.
