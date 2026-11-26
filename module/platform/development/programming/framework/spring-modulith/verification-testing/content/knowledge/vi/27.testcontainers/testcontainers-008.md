# Cô lập network và dữ liệu giữa test

## 1. Hợp đồng cô lập: hai test không được làm thay đổi kết luận của nhau

Trong học phần **SPRING_MODULITH_VERIFICATION_TESTING**, các bài `@ApplicationModuleTest` kiểm chứng hành vi của từng Spring application module, cùng các phép kiểm `ApplicationModules.verify()` bảo vệ ranh giới và luật phụ thuộc kiến trúc. Khi dùng Testcontainers để đưa PostgreSQL, Kafka, RabbitMQ hay Redis thật vào test, **một container hoạt động chính xác chưa đồng nghĩa các test đã độc lập**.

Xét hai test chạy đồng thời:

- Test A phát `OrderPaid(orderA)`, listener shipping ghi `Shipment(orderA, READY)`.
- Test B phát `OrderPaid(orderB)` và chờ shipment của B.
- Cả hai chia sẻ PostgreSQL container, cùng bảng `shipments`, cùng Spring `ApplicationContext`.

Nếu callback của A gọi `DELETE FROM shipments` không có điều kiện, nó có thể xóa row B. Nếu B chỉ assert “có ít nhất một shipment”, B có thể pass nhờ row A, dù listener B không chạy. **Kết quả test phụ thuộc vào lịch chạy**, không còn kiểm chứng đúng nghiệp vụ.

**Hợp đồng cô lập có thể kiểm chứng** là:

1. **Địa chỉ:** Một client của môi trường A chỉ phân giải alias và endpoint thuộc A, trừ những dependency được chia sẻ có chủ đích.
2. **Dữ liệu:** Query/assertion của A không đọc nhầm bản ghi, message hoặc cache entry của B.
3. **Ghi/xóa:** Setup và cleanup của A không sửa hoặc xóa fixture thuộc B.
4. **Thời gian:** Task bất đồng bộ và retry từ A không làm sai kết quả B sau khi A kết thúc.
5. **Vòng đời:** A không dừng network/container/connection pool mà B vẫn đang sử dụng.
6. **Tái lập:** Chạy một test riêng, chạy cả suite, đảo thứ tự và chạy song song đều phải cho cùng kết luận đối với contract.

| Tầng cô lập | Cơ chế thường dùng | Điều **không** tự được bảo đảm |
| --- | --- | --- |
| **Network** | `Network.newNetwork()`, `withNetwork(...)`, alias riêng theo network | Database bên ngoài network có dữ liệu riêng |
| **Container/process** | Instance/container riêng cho test hoặc suite | Dữ liệu bị bind mount hay external service đã được tách |
| **Database/schema** | Database/schema riêng hoặc fixture theo business ID | Spring singleton, broker offset, async task độc lập |
| **Message/cache** | Topic/queue/group/key prefix, event ID/correlation ID | Listener đã commit DB, chính xác một lần end-to-end |
| **Scheduling** | Không chia sẻ mutable globals; `@ResourceLock` khi thật cần | Network isolation hoặc khóa giữa **hai CI jobs** |

**Không có một annotation duy nhất đảm bảo cả sáu điều kiện.** Thiết kế phải xuất phát từ tài nguyên nào được dùng chung, test nào được chạy song song và bằng chứng cần quan sát.

## 2. Docker network: alias và hostname thuộc phạm vi nào?

Testcontainers hỗ trợ Docker user-defined networks:

```java
Network network = Network.newNetwork();

GenericContainer<?> redis =
        new GenericContainer<>(DockerImageName.parse("redis:7.4-alpine"))
                .withNetwork(network)
                .withNetworkAliases("cache");
```

Ở đây `Network` là `org.testcontainers.containers.Network`; `GenericContainer` và `DockerImageName` cũng thuộc Testcontainers. Đây là đoạn cấu hình, cần start container và close network đúng vòng đời.

Có **hai đường kết nối khác nhau**:

| Đường đi | Endpoint đúng | Khi nào sử dụng |
| --- | --- | --- |
| **JVM/JUnit trên host → container** | `container.getHost()` + `container.getMappedPort(port)` hoặc `postgres.getJdbcUrl()` | Spring `DataSource`, test HTTP/JDBC chạy trên máy/runner |
| **Container A → container B cùng Docker network** | `<network-alias>:<internal-port>` | App container gọi Redis `cache:6379`, DB `db:5432` |

Từ **container khác trong cùng network**, `cache` là tên DNS/alias. Từ **JVM trên host**, `cache` thường **không** phải một hostname có thể resolve trực tiếp. Ngược lại, mapped port của JVM không phải địa chỉ nên hard-code cho giao tiếp container-to-container.

### Cách tạo network riêng cho mỗi nhóm

```java
try (Network networkA = Network.newNetwork();
     Network networkB = Network.newNetwork()) {
    // Khởi động container thuộc từng network trong scope này.
}
```

Hai network có DNS scope riêng, nên alias `cache` có thể tồn tại ở **cả A lẫn B** mà không xung đột. Một client gắn vào A tìm `cache` của A; client gắn vào B tìm `cache` của B.

**Giới hạn cần hiểu:**

- Theo tài liệu Testcontainers Java hiện hành, container được gắn tối đa **một** custom network qua API mạng này.
- User-defined network không thay thế authentication/authorization của PostgreSQL, Kafka hoặc Redis.
- Nếu container đồng thời **publish port lên host**, client có quyền truy cập host có thể đi qua đường host/mapped port; đừng hiểu network riêng là tường bảo mật tuyệt đối.
- Nếu hai test vẫn dùng **cùng một PostgreSQL bên ngoài** hoặc cùng một Kafka cluster bên ngoài, tạo network riêng cho những container client không tự tách dữ liệu ở server đó.
- Với `Testcontainers.exposeHostPorts(...)` hoặc host access đặc biệt, bạn đang chủ động mở thêm đường nối; chỉ bật khi contract test thật sự yêu cầu.

**Quy tắc:** network isolation giải quyết *ai nhìn thấy endpoint qua Docker DNS*, còn data isolation giải quyết *ai được nhìn thấy/đổi trạng thái nghiệp vụ*.

## 3. JUnit kiểm chứng hai network cùng alias nhưng không lẫn dữ liệu

Ví dụ chạy độc lập dưới đây tạo **hai Redis servers**, một ở network A và một ở network B. Cả hai đều mang alias `cache`. Mỗi network có một container “probe” riêng, dùng `redis-cli` để truy vấn alias trong **network của nó**.

Không cần publish cổng Redis lên host; mọi lệnh truy vấn được thực thi bên trong probe container qua `execInContainer(...)`. Đây là phép kiểm **network + data path thực**, không phải chỉ so sánh chuỗi cấu hình.

```java
package com.acme.testing;

import static org.assertj.core.api.Assertions.assertThat;

import java.time.Duration;

import org.junit.jupiter.api.Test;
import org.testcontainers.containers.GenericContainer;
import org.testcontainers.containers.Network;
import org.testcontainers.containers.wait.strategy.Wait;
import org.testcontainers.utility.DockerImageName;

class DockerNetworkIsolationTests {

    private static final DockerImageName REDIS =
            DockerImageName.parse("redis:7.4-alpine");

    @Test
    void sameAliasResolvesToDifferentRedisByNetwork()
            throws Exception {

        try (Network a = Network.newNetwork();
             Network b = Network.newNetwork();

             GenericContainer<?> redisA = new GenericContainer<>(REDIS)
                     .withNetwork(a)
                     .withNetworkAliases("cache")
                     .waitingFor(Wait.forLogMessage(
                             ".*Ready to accept connections.*\\n", 1)
                             .withStartupTimeout(Duration.ofSeconds(60)));

             GenericContainer<?> redisB = new GenericContainer<>(REDIS)
                     .withNetwork(b)
                     .withNetworkAliases("cache")
                     .waitingFor(Wait.forLogMessage(
                             ".*Ready to accept connections.*\\n", 1)
                             .withStartupTimeout(Duration.ofSeconds(60)));

             GenericContainer<?> probeA = new GenericContainer<>(REDIS)
                     .withNetwork(a)
                     .withCommand("sh", "-c",
                             "echo probe-ready; sleep 600")
                     .waitingFor(Wait.forLogMessage(
                             ".*probe-ready.*\\n", 1));

             GenericContainer<?> probeB = new GenericContainer<>(REDIS)
                     .withNetwork(b)
                     .withCommand("sh", "-c",
                             "echo probe-ready; sleep 600")
                     .waitingFor(Wait.forLogMessage(
                             ".*probe-ready.*\\n", 1))) {

            redisA.start();
            redisB.start();
            probeA.start();
            probeB.start();

            assertThat(a.getId()).isNotEqualTo(b.getId());

            var writeA = redisA.execInContainer(
                    "redis-cli", "SET", "shared-key", "alpha");
            var writeB = redisB.execInContainer(
                    "redis-cli", "SET", "shared-key", "beta");

            assertThat(writeA.getExitCode()).isZero();
            assertThat(writeB.getExitCode()).isZero();

            var readA = probeA.execInContainer(
                    "redis-cli", "-h", "cache",
                    "GET", "shared-key");
            var readB = probeB.execInContainer(
                    "redis-cli", "-h", "cache",
                    "GET", "shared-key");

            assertThat(readA.getExitCode()).isZero();
            assertThat(readB.getExitCode()).isZero();
            assertThat(readA.getStdout().trim()).isEqualTo("alpha");
            assertThat(readB.getStdout().trim()).isEqualTo("beta");
        }
        // Reverse close order: probes -> Redis servers -> networks.
    }
}
```

### Điều gì được kiểm chứng?

1. `Network.newNetwork()` tạo hai Docker networks có ID khác nhau.
2. `redisA` và `redisB` đều dùng alias `cache` nhưng trên **hai network khác**.
3. `SET shared-key alpha` và `SET shared-key beta` ghi vào **hai Redis process** riêng.
4. Probe A truy vấn `cache` qua DNS ở network A và nhận `alpha`; probe B nhận `beta`.
5. Hai dữ liệu **không bị đọc chéo** dù cùng key và cùng alias.
6. `try-with-resources` đóng container trước network, kể cả khi assertion ném exception.

**Không suy rộng quá mức:** test này không chứng minh Docker network chống được tác nhân có quyền truy cập Docker daemon, và không chứng minh hai Redis servers dùng chung một external persistence volume sẽ an toàn. Nó kiểm tra chính xác *đường đi và state* mà test thiết lập.

### Điều kiện chạy và cách đọc lỗi

- Cần JUnit 5, AssertJ, Testcontainers Core và Docker-compatible runtime; dùng Java hỗ trợ `var` và `try-with-resources`.
- Redis image `redis:7.4-alpine` cần có `redis-cli`, `sh` và lệnh `sleep`; đó là lý do dùng cùng image cho probe.
- `Wait.forLogMessage(...)` chờ log khởi động; nếu nâng image làm thay đổi log, cần thay wait strategy có ý nghĩa tương đương. Timeout ở bước start là lỗi **readiness**, không phải lỗi Redis key isolation.
- Nếu cả hai probe đều trả cùng một giá trị, kiểm tra network attachment/alias, đừng vội tăng timeout.
- Nếu Docker runtime trên CI có hạn chế network creation, test fail trước bước assert; phải sửa quyền và hạ tầng runner.

Một kiểm thử **cô lập network có bằng chứng** nên quan sát được hành vi từ cả hai phía như ở đây, thay vì chỉ assert rằng đã gọi `withNetwork(...)`.

## 4. Phạm vi network và vòng đời cleanup không được lệch

Các tài nguyên network, container và Spring context có thể sống trong những phạm vi khác nhau.

| Phạm vi mong muốn | Cách quản lý phù hợp | Điều cần tránh |
| --- | --- | --- |
| **Một JUnit method** | `try (Network n = Network.newNetwork(); GenericContainer<?> ... )` | Đóng network trước khi container ngừng sử dụng |
| **Một JUnit class** | Tạo network trong setup lớp; quản lý container/teardown cùng lớp | Để `@AfterEach` đóng network giữa các method |
| **Một Spring `ApplicationContext`** | Cấu hình các container là bean Spring hoặc import container config có lifecycle tương ứng | JUnit `static @Container` dừng trước context đang cache |
| **Nhiều test class trong cùng JVM** | Network/container sở hữu bởi một scope dùng chung rõ ràng | Một lớp tự gọi `network.close()` khi lớp khác còn cần |
| **Một CI job** | Runner/daemon được cô lập, tài nguyên gắn với job | Xóa Docker network/container của job khác |

`Network` implements `AutoCloseable`; `GenericContainer` cũng có cơ chế close/stop. Trong ví dụ ở mục 3, tài nguyên được khai báo theo thứ tự **network trước, container sau**, nên Java đóng container trước khi gọi `Network.close()`.

### Không nhầm “port exposed” với “network riêng”

Nếu chỉ cần Redis A nói chuyện với probe A trên **cùng Docker network**, việc publish `6379` ra host là không bắt buộc. Khi test Java/JDBC **chạy từ host**, lại cần endpoint mapped port và container host được Testcontainers trả về.

Không hard-code `localhost:5432`/`localhost:6379` vì:

- Testcontainers thường cấp mapped port động để tránh xung đột giữa test processes.
- Trên remote Docker/CI, host của container có thể khác `localhost`.
- Địa chỉ host không tương đương alias trong user-defined Docker network.

### Không dùng network để che lỗi dữ liệu

Nếu hai test dùng **chung server Redis** nhưng có hai Docker networks client khác nhau (qua một đường host hoặc gateway), cả hai vẫn có thể thao tác cùng key `shared-key`. Muốn dữ liệu độc lập, phải dùng **Redis instance khác**, key prefix riêng, hoặc database/namespace theo contract.

## 5. PostgreSQL: chọn mức cô lập từ khóa nghiệp vụ đến container riêng

Phần lớn flaky tests trong `@ApplicationModuleTest` xuất phát từ **dữ liệu dùng chung**, không phải việc thiếu Docker network riêng.

| Mức cô lập | Chiến lược | Hợp với | Giới hạn / rủi ro |
| --- | --- | --- | --- |
| **Row/business key** | `UUID.randomUUID()`; query và `DELETE WHERE order_id = ?` | CRUD/event-flow tests cùng DB, chạy song song | Global queries, triggers, sequences, retry vẫn có thể tác động |
| **Test transaction rollback** | `@Transactional` với Spring TestContext | Repository test chỉ ghi trong transaction test | **Không rollback** transaction độc lập do `Scenario`/async listener commit |
| **Schema riêng** | Schema theo suite/test context + datasource/migration tương ứng | Nhiều bảng, SQL names và data cần tách | `search_path`/default schema/connection pool phải cấu hình đúng; thay schema của datasource chung rất nguy hiểm |
| **Database riêng** | Database name + credentials/migration riêng | Suite/phân vùng integration lớn | Cùng PostgreSQL process vẫn chia CPU/locks cấp instance và một số global config |
| **Container riêng** | `PostgreSQLContainer` cho test class/suite/method | Test migration, retry/recovery, destructive DDL | Chi phí startup, RAM, Docker resource cao hơn |

**Lựa chọn mặc định thực tế:** nếu test chỉ thêm/đọc/xóa shipment theo `orderId`, dùng ID riêng, predicate đúng ID và cleanup có điều kiện thường đủ. Khi test kiểm chứng **migration từ trạng thái trống**, lỗi schema/global DDL hoặc recovery không kiểm soát, hãy dùng **database/container riêng**.

### Anti-pattern: cleanup global

```sql
-- Nguy hiểm trong shared database nếu các test đang song song:
DELETE FROM shipments;
TRUNCATE TABLE shipments CASCADE;
```

Test A có thể xóa row test B trước khi B assert. `TRUNCATE ... CASCADE` còn có thể tác động nhiều bảng liên quan.

**Cleanup theo phạm vi test:**

```sql
DELETE FROM shipments WHERE order_id = ?;
```

Nếu nghiệp vụ tạo thêm `shipment_items`, `audit_entries` hay outbox, dọn **theo cùng correlation/business key** và thứ tự FK chính xác. Những bảng không có correlation ID cần một chiến lược fixture/test namespace khác.

### Vì sao `@Transactional` không đủ?

`Scenario.publish(...)` tạo stimulus trong transaction mới để hỗ trợ transactional listeners, còn `@ApplicationModuleListener` xử lý **sau commit, bất đồng bộ, trong transaction riêng**. Dữ liệu từ transaction này **không tự rollback** khi JUnit rollback transaction của test.

Với Given cần listener ở transaction khác nhìn thấy, phải bảo đảm setup **đã commit** trước khi publish. Dùng `TransactionTemplate` khi test không có outer transaction; nếu có, cần tách setup/transaction propagation rõ ràng.

## 6. `@ApplicationModuleTest`: dữ liệu shipment độc lập dù dùng chung PostgreSQL

Ví dụ này dùng PostgreSQL thật, Spring-managed Testcontainer và hai test method cùng cấu hình context. Nó kiểm tra rằng mỗi `OrderPaid(id)` chỉ tạo shipment của **id hiện tại**, kết quả được đọc **sau commit**, và cleanup không xóa dữ liệu của method khác.

### 6.1. Cấu hình container theo Spring context

Dành cho **Testcontainers Java 2.x**:

```java
package com.acme.shipping;

import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.boot.testcontainers.service.connection.ServiceConnection;
import org.springframework.context.annotation.Bean;
import org.testcontainers.postgresql.PostgreSQLContainer;

@TestConfiguration(proxyBeanMethods = false)
class ShippingPostgresTestConfig {

    @Bean
    @ServiceConnection
    PostgreSQLContainer shippingDatabase() {
        return new PostgreSQLContainer("postgres:17-alpine")
                .withDatabaseName("shipping_test")
                .withUsername("test")
                .withPassword("test");
    }
}
```

Cần tương thích Spring Boot/Spring Modulith/Testcontainers BOM, `spring-boot-testcontainers`, `testcontainers-postgresql`, JDBC driver và starter JDBC/JPA của ứng dụng. **Không** gắn `@Testcontainers`/`@Container` lên bean này: container được Spring quản lý, sống cùng `ApplicationContext` có thể được cache.

### 6.2. Schema và implementation mục tiêu

Migration PostgreSQL minh họa (phải dùng version migration thực tế không trùng trong dự án):

```sql
CREATE TABLE shipments (
    order_id UUID PRIMARY KEY,
    status   VARCHAR(32) NOT NULL
);
```

Event ở API công khai của module order:

```java
package com.acme.order;

import java.util.UUID;

public record OrderPaid(UUID orderId) {}
```

Repository ở module shipping:

```java
package com.acme.shipping;

import java.util.List;
import java.util.Optional;
import java.util.UUID;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

@Repository
class ShipmentRepository {

    private final JdbcTemplate jdbc;

    ShipmentRepository(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    void saveReady(UUID id) {
        jdbc.update("""
                INSERT INTO shipments(order_id, status)
                VALUES (?, 'READY')
                ON CONFLICT (order_id)
                DO UPDATE SET status = EXCLUDED.status
                """, id);
    }

    Optional<String> statusOf(UUID id) {
        List<String> values = jdbc.query(
                "SELECT status FROM shipments WHERE order_id = ?",
                (rs, rowNum) -> rs.getString(1), id);
        return values.stream().findFirst();
    }

    int countOf(UUID id) {
        Integer count = jdbc.queryForObject(
                "SELECT COUNT(*) FROM shipments WHERE order_id = ?",
                Integer.class, id);
        return count == null ? 0 : count;
    }

    void deleteByOrderId(UUID id) {
        jdbc.update(
                "DELETE FROM shipments WHERE order_id = ?", id);
    }
}
```

Listener thuộc module shipping:

```java
package com.acme.shipping;

import com.acme.order.OrderPaid;
import org.springframework.modulith.events.ApplicationModuleListener;
import org.springframework.stereotype.Component;

@Component
class ShippingHandler {

    private final ShipmentRepository shipments;

    ShippingHandler(ShipmentRepository shipments) {
        this.shipments = shipments;
    }

    @ApplicationModuleListener
    public void on(OrderPaid event) {
        shipments.saveReady(event.orderId());
    }
}
```

`ON CONFLICT` giảm nguy cơ duplicate **row** khi event được gửi lại. Nó không chứng minh exactly-once cho những side effect khác (Kafka, email, external carrier).

### 6.3. Hai JUnit methods, một nguyên tắc cô lập

```java
package com.acme.shipping;

import static org.assertj.core.api.Assertions.assertThat;

import java.time.Duration;
import java.util.UUID;

import com.acme.order.OrderPaid;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.annotation.Import;
import org.springframework.modulith.test.ApplicationModuleTest;
import org.springframework.modulith.test.Scenario;
import org.springframework.transaction.support.TransactionTemplate;

@ApplicationModuleTest
@Import(ShippingPostgresTestConfig.class)
class ShippingDataIsolationTests {

    @Autowired ShipmentRepository shipments;
    @Autowired TransactionTemplate transactions;

    @Test
    void orderAIsIndependent(Scenario scenario) {
        assertIsolatedShipment(scenario);
    }

    @Test
    void orderBIsIndependent(Scenario scenario) {
        assertIsolatedShipment(scenario);
    }

    private void assertIsolatedShipment(Scenario scenario) {
        UUID id = UUID.randomUUID();
        UUID unrelatedId = UUID.randomUUID();

        assertThat(shipments.statusOf(id)).isEmpty();

        scenario.publish(new OrderPaid(id))
                .andCleanup(() ->
                        transactions.executeWithoutResult(tx ->
                                shipments.deleteByOrderId(id)))
                .andWaitAtMost(Duration.ofSeconds(8))
                .forStateChange(
                        () -> shipments.statusOf(id),
                        value -> value.filter("READY"::equals).isPresent())
                .andVerify(value -> {
                    assertThat(value).contains("READY");
                    assertThat(shipments.countOf(id)).isEqualTo(1);
                    assertThat(shipments.statusOf(unrelatedId)).isEmpty();
                });

        assertThat(shipments.statusOf(id)).isEmpty();
    }
}
```

**Điều test kiểm tra:**

1. Mỗi invocation tạo `UUID` khác nhau; test không phụ thuộc thứ tự JUnit chạy A/B.
2. `Scenario.publish` phát input event **một lần**, không lặp stimulus trong supplier polling.
3. `forStateChange(...)` truy vấn database lại đến khi đúng `READY` cho `id`; không pass do `Optional.of("PENDING")` hoặc row test khác.
4. `andVerify(...)` kiểm chứng đúng row, không assert toàn bảng.
5. `andCleanup(...)` xóa row **của id hiện tại** qua transaction riêng. Callback được gọi sau Scenario dù thành công hay thất bại, khi nó đã được đăng ký.
6. Assert cuối kiểm tra cleanup ở **happy path**. Khi Scenario ném exception, statement cuối không chạy — vì vậy nó không kiểm chứng được callback trong failure path.

Đây là ví dụ có thể triển khai trong Spring Boot project **đã có migration, datasource và transaction manager**. Không thể chạy chỉ bằng copy mỗi class test mà thiếu application/DB setup.

**Lưu ý quan trọng:** nếu Scenario timeout nhưng listener còn chạy hoặc có retry sau đó, callback cleanup có thể thực thi **trước** side effect đến muộn. Trong những test recovery/async có retry không dự đoán được, chọn isolation mạnh hơn (database/container riêng, chặn task đúng contract hoặc dọn theo lifecycle cuối được kiểm soát).

## 7. Cô lập event và transaction: correlation ID phải có mặt trong mọi phép chờ

Một Docker network riêng **không ngăn** Spring application event của các test trong cùng `ApplicationContext` bị nhận nhầm. Test Context có thể được cache; executor, singleton bean và event publisher có thể được chia sẻ.

### Trường hợp pass giả

```java
scenario.publish(new OrderPaid(orderId))
        .andWaitForEventOfType(ShipmentPrepared.class)
        .toArrive();
```

Nếu test khác vừa phát `ShipmentPrepared` của một đơn khác, test này có thể hoàn tất dù shipment của `orderId` hiện tại chưa xử lý xong.

### Chờ đúng event instance

```java
scenario.publish(new OrderPaid(orderId))
        .andWaitForEventOfType(ShipmentPrepared.class)
        .matching(event -> event.orderId().equals(orderId))
        .toArriveAndVerify(event ->
                assertThat(event.orderId()).isEqualTo(orderId));
```

`ShipmentPrepared` là event output **do dự án định nghĩa**; listener ví dụ ở mục 6 chỉ ghi DB, nên đoạn event-based này là **biến thể hợp đồng** khi application thực sự phát event `ShipmentPrepared`.

**Ba tầng correlation nên trùng khớp:**

- Stimulus: `OrderPaid(orderId)`.
- Observation: predicate DB `WHERE order_id = ?` hoặc matcher `event.orderId()`.
- Cleanup: `DELETE ... WHERE order_id = ?` hoặc xóa publication/fixture theo ID thích hợp.

### Event registry và task đến muộn

Khi bật Spring Modulith Event Publication Registry có persistence, một publication failed/pending có thể được retry/resubmit sau lúc test đầu tiên kết thúc. Event handler cần **idempotency** và test recovery nên có database/registry fixture riêng. Không xóa toàn bộ bảng registry nếu nhiều test đang dùng cùng DB.

**Quan sát event chưa đồng nghĩa DB đã commit:** một listener có thể phát Spring event **trước khi transaction của nó commit**. Khi contract là “DB đã sẵn sàng”, ưu tiên `andWaitForStateChange(...)` query trạng thái đã commit, rồi mới cleanup.

### Vì sao rollback không bảo vệ event flow tự động?

`@Transactional` trên JUnit test chỉ rollback transaction do TestContext quản lý. Transaction độc lập của `Scenario` và `@ApplicationModuleListener` đã commit thì **không tự bị rollback**. Do đó:

- Given cần listener async đọc phải commit trước stimulus.
- Assertion phải chờ đúng state cuối.
- Cleanup dữ liệu commit phải dùng transaction riêng hoặc test database độc lập.
- Nếu handler phát Kafka/AMQP, DB rollback không “thu hồi” message đã ra broker.

## 8. Broker, cache và namespace: network riêng chưa đủ

Một Kafka broker hay RabbitMQ server **có thể được nhiều test truy cập qua các đường network khác nhau**. Khi cùng dùng server, các loại state bên trong vẫn chia sẻ.

| Công nghệ | State có thể giao thoa | Chiến lược cô lập |
| --- | --- | --- |
| **Kafka** | Topic, consumer group, offsets, messages còn retention | Topic riêng theo suite khi cần topology sạch; group riêng cho probe; record key/eventId theo test |
| **RabbitMQ** | Exchange, queue, binding, unacked/redelivered message | Queue/exchange namespace riêng; routing key/correlation ID; cleanup queue có owner |
| **Redis** | Key, TTL, lock, session, rate limit | Key prefix `it:<runId>:<id>`; xóa đúng prefix hoặc Redis/container riêng |
| **PostgreSQL** | Rows, sequences, locks, schema, event registry | Business key + cleanup; schema/database riêng cho global state |

### Kafka: topic, group và key là ba mục tiêu khác nhau

Ví dụ tên được tạo theo **suite run**:

```java
String runId = UUID.randomUUID().toString().replace("-", "");
String topic = "shipping-requests-it-" + runId;
String consumerGroup = "shipping-probe-" + runId;
String recordKey = orderId.toString();
```

Trong một test thực tế, `topic` và `consumerGroup` phải được đưa vào **cấu hình producer, consumer, admin/topic declaration** trước khi Spring client/listener khởi động. Chỉ sinh ba chuỗi trong test method **không** làm `@KafkaListener` đổi topic đã đăng ký.

Kiểm chứng record phải so cả **topic, key, payload/eventId**, không chỉ “đã đọc được một message”. Với test cần xác nhận consumer đã xử lý nghiệp vụ, kiểm tra state DB đã commit, không chỉ Spring `PublishedEvents`.

**Consumer group riêng không xóa record cũ:** group mới có thể đọc record còn retention khi dùng `auto.offset.reset=earliest`. Vì vậy vẫn cần correlation ID/record key và chiến lược offset/topology.

### RabbitMQ: đừng purge queue chung

Nếu test A purge queue `shipping.requests` trong `@AfterEach` còn test B đang chờ delivery, B có thể timeout. Nếu từng suite cần topology sạch, tạo queue riêng theo run ID, thiết lập binding đúng, rồi xóa **queue thuộc suite đó** khi consumer đã ngừng.

Với custom exchange, phải kiểm tra exchange + binding + routing key; việc broker ready không chứng minh message đã route tới đúng queue.

### Redis: không chỉ randomize key trong assertion

Nếu cùng Redis container, cấu hình application thực phải dùng prefix theo test/suite cho **mọi lệnh ghi**, không chỉ test query. Ví dụ:

```java
String key = "it:" + runId + ":" + orderId + ":shipment";
```

Khi handler production hard-code key `shipment:<orderId>`, một biến `key` trong test không làm handler dùng prefix đó. Hoặc inject namespace bằng configuration có chủ đích, hoặc cấp Redis instance/database riêng.

## 9. Parallel tests, Spring Context cache và kịch bản chẩn đoán

Network và DB isolation đúng vẫn có thể bị phá bởi **vòng đời** không khớp.

### Static container của JUnit khác bean container của Spring

- `@Testcontainers` + **instance `@Container`**: JUnit extension start/stop theo **method**.
- `@Testcontainers` + **static `@Container`**: start/stop theo **class**.
- `@TestConfiguration @Bean @ServiceConnection`: Spring Boot start/stop theo **`ApplicationContext`**, có thể được cache giữa các lớp.

Nếu JUnit dừng `static @Container` sau lớp A nhưng Spring tiếp tục dùng cached context chứa datasource của A trong lớp B, B có thể gặp `Connection refused`. Với nhiều `@ApplicationModuleTest` chia sẻ context, container do **Spring quản lý** thường phù hợp hơn.

**Testcontainers JUnit Jupiter extension được tài liệu mô tả là đã kiểm thử với thực thi tuần tự; chạy parallel bằng extension không được hỗ trợ chính thức.** Khi cần parallel module tests, không nên mặc định mọi kết hợp lifecycle đều an toàn chỉ vì test của bạn có UUID riêng.

### Khóa những thao tác global không thể namespace

Một test thực sự cần thay đổi schema chung có thể dùng JUnit Jupiter `@ResourceLock`:

```java
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.parallel.ResourceAccessMode;
import org.junit.jupiter.api.parallel.ResourceLock;

@ResourceLock(
        value = "shared-shipping-schema",
        mode = ResourceAccessMode.READ_WRITE)
@Test
void migratesSharedSchema() {
    // Thao tác DDL/schema chung có chủ đích.
}
```

Lock được JUnit engine tôn trọng giữa các test **cùng khai báo resource key đó**; nó không khóa một CI process khác hoặc một tool kết nối DB bên ngoài. Không dùng lock làm lý do để bỏ cleanup theo ID trong các test CRUD.

### Runbook: test pass một mình, fail khi chạy cùng suite

| Biểu hiện | Tầng cần kiểm tra | Cách chứng minh nguyên nhân |
| --- | --- | --- |
| Probe ở network A đọc giá trị B | Docker network/alias | Log `Network.getId()`, container attachment và truy vấn từ **hai** probe |
| Test B `Connection refused` sau A | Container/context lifecycle | Kiểm tra ai stop container; Spring context có được cache không |
| Duplicate key trên PostgreSQL | Fixture/state | Xác định `orderId` cố định hoặc row test trước chưa cleanup |
| B pass dù listener B bị tắt | Assertion quá rộng | Buộc query/matcher đúng ID, không dùng `count(*) > 0` |
| B timeout khi A chạy song song | Cleanup/race | Tìm `deleteAll()`, `TRUNCATE` hoặc schema reset từ A |
| Kafka consumer không thấy message | Group/offset/assignment | Kiểm tra group, assignment, `auto.offset.reset` và key |
| RabbitMQ nhận sai payload | Queue/routing | Kiểm tra queue/binding namespace và correlation ID |
| Row đã xóa lại xuất hiện | Async retry/event registry | Correlate transaction, retry logs và post-cleanup writes |
| CI khác bị mất container | Docker runner/resource owner | Kiểm tra resource labels, network/volume ownership; không chạy global prune |

**Chẩn đoán theo thứ tự:** kiểm tra network endpoint → actual datasource/broker → fixture ID → transaction commit → assertion predicate → cleanup → listener async/retry → lifecycle và CI concurrency. Đừng tăng `Thread.sleep` hoặc timeout khi chưa xác định đúng tầng.

## 10. Kiểm chứng trên CI, checklist và bài tập

Một bộ kiểm thử có ý nghĩa nên gồm **hai phép chứng minh độc lập**:

- **Network isolation test:** hai Docker networks có alias `cache` giống nhau; Redis A/B giữ hai giá trị khác nhau; probe bên A/B đọc đúng giá trị.
- **Data isolation/module test:** hai invocation `Scenario` có `orderId` riêng; query DB chờ `READY` đúng ID; cleanup không xóa fixture của invocation khác.

Bên cạnh đó, chạy:

```java
import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

class ModuleArchitectureTests {

    @Test
    void boundariesRemainValid() {
        ApplicationModules.of(Application.class).verify();
    }
}
```

`Application.class` phải được thay bằng Spring Boot application class thật. Phép kiểm `verify()` không cần Docker, không thay thế network/data tests; ngược lại, hai container Redis riêng không tự phát hiện việc module shipping import `order.internal.*`.

### Ma trận chạy đề xuất

| Cách chạy | Mục tiêu phát hiện |
| --- | --- |
| Chạy test A riêng nhiều lần | Ổn định cơ bản, không phụ thuộc fixture cũ |
| Chạy A rồi B, sau đó đảo thứ tự | State leakage và thứ tự chạy |
| Chạy nguyên suite có context cache | Container lifecycle và singleton leakage |
| Chạy parallel theo cấu hình được hỗ trợ | Cleanup đua nhau, shared groups/locks |
| Chạy trên runner sạch | Migration/bootstrap thực tế và network permissions |
| Chạy failure/retry có DB/broker riêng | Side effect đến muộn và idempotency |

**Checklist trước khi đánh dấu module test đạt:**

- [ ] Mỗi nhóm cần cách ly có `Network.newNetwork()` hoặc giải pháp network tương đương; không dùng alias toàn cục vô ý.
- [ ] Đường JVM → container lấy `getHost()/getMappedPort()` hoặc typed connection URL; đường container → container dùng network alias/internal port.
- [ ] Không publish host port nếu không cần; không xem network là security boundary tuyệt đối.
- [ ] Network và các container có lifecycle/owner rõ ràng; đóng container **trước** network.
- [ ] Mỗi test có business ID riêng; mọi query, event matcher và cleanup dùng đúng ID.
- [ ] Không dọn toàn bảng/topic/queue đang được test khác sử dụng.
- [ ] Given đã commit khi listener bất đồng bộ cần đọc; không phụ thuộc rollback JUnit cho `Scenario`.
- [ ] Chờ state đã commit bằng predicate rõ ràng; không dùng delay tùy ý.
- [ ] Event/outbox/retry có chiến lược idempotency và cách ly mạnh hơn khi cần.
- [ ] Spring TestContext cache và container lifecycle không xung đột.
- [ ] Với broker, phân biệt topic/queue, consumer group, offset và correlation ID.
- [ ] Có test migration/schema mới khi kiểm chứng bootstrap sạch; không dựa vào DB reuse tình cờ.
- [ ] CI dùng runtime có quyền tạo network, đủ resources và không xóa resource của job khác.
- [ ] `ApplicationModules.verify()` vẫn thuộc quality gate kiến trúc.

### Bài tập có đáp án gợi ý

1. **Hai alias trùng:** Dựng hai Docker network, mỗi network có Redis alias `cache`. Viết một probe trên từng network và chứng minh giá trị `shared-key` không bị đọc chéo. *Gợi ý:* `Network.newNetwork()`, `withNetworkAliases(...)`, `execInContainer(...)`.
2. **Host vs network:** Một container app gọi `cache:6379` thành công, nhưng test Java trên host không resolve được `cache`. Vì sao? *Gợi ý:* DNS alias có phạm vi Docker network; JVM dùng `getHost()/getMappedPort()` nếu đã publish port.
3. **Cleanup global:** Test A gọi `DELETE FROM shipments` sau khi B đã lưu shipment. Vì sao B timeout? *Gợi ý:* xóa theo `orderId`.
4. **Rollback sai kỳ vọng:** Test dùng `@Transactional` và `Scenario.publish`. Vì sao row listener commit vẫn có sau test? *Gợi ý:* transaction mới/async listener.
5. **Event không cùng ID:** Test B nhận `ShipmentPrepared` của A và pass. Sửa matcher như thế nào? *Gợi ý:* `event.orderId().equals(orderIdB)`.
6. **Kafka cũ:** Hai consumer groups khác nhau nhưng cùng topic vẫn thấy record cũ. Cần thêm gì? *Gợi ý:* offset strategy và event ID/key; group riêng không xóa retention.
7. **Context cache:** JUnit `static @Container` dừng sau lớp A, Spring context vẫn cache. Sửa lifecycle như thế nào? *Gợi ý:* Spring-managed container bean.
8. **Schema migration:** Một test thay đổi `public` schema và không thể chạy song song. Giải pháp cô lập mạnh hơn row-level là gì? *Gợi ý:* schema/database/container riêng, hoặc `@ResourceLock` nếu bắt buộc.
9. **Async cleanup:** `Scenario` timeout, cleanup đã xóa row, nhưng retry tái tạo nó. Test cần thay đổi gì? *Gợi ý:* chờ lifecycle cuối có ý nghĩa, idempotency, database riêng cho recovery tests.
10. **Quality gate:** Vì sao hai network cô lập đúng không chứng minh ứng dụng tuân thủ module dependencies? *Gợi ý:* thêm `ApplicationModules.verify()`.

## Tài liệu tham khảo

- [Testcontainers Java — Networking and communicating with containers](https://java.testcontainers.org/features/networking/): `Network.newNetwork()`, alias, host/mapped port, custom network và cleanup qua `AutoCloseable`.
- [Testcontainers Java — JUnit 5 integration](https://java.testcontainers.org/test_framework_integration/junit_5/): instance/static `@Container`, lifecycle và giới hạn khi chạy parallel.
- [Spring Boot — Testcontainers](https://docs.spring.io/spring-boot/reference/testing/testcontainers.html): Spring-managed container beans, `@ServiceConnection` và tương tác với Spring TestContext cache.
- [Spring Framework — TestContext Context Caching](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/ctx-management/caching.html): cache keys, eviction và context lifecycle.
- [Spring Framework — Transaction Management in Tests](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/tx.html): test-managed transaction và giới hạn rollback.
- [Spring Modulith — Integration Testing Application Modules](https://docs.spring.io/spring-modulith/reference/testing.html): `@ApplicationModuleTest`, `Scenario`, state/event waiting và transaction mới.
- [Spring Modulith — Scenario.When Javadoc](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/test/Scenario.When.html): `andCleanup(...)` sau hoàn tất Scenario.
- [Spring Modulith — Working with Application Events](https://docs.spring.io/spring-modulith/reference/events.html): `@ApplicationModuleListener`, publication registry và retry.
- [Spring Modulith — Verification](https://docs.spring.io/spring-modulith/reference/verification.html): `ApplicationModules.verify()` và luật phụ thuộc.
- [JUnit Jupiter — ResourceLock](https://docs.junit.org/5.14.4/api/org.junit.jupiter.api/org/junit/jupiter/api/parallel/ResourceLock.html): khóa tài nguyên dùng chung giữa những test cùng tham gia JUnit engine.
