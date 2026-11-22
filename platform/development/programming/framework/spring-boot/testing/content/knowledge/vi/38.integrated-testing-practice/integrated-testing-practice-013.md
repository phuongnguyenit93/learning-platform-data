# Tổng hợp ma trận yêu cầu, bằng chứng và giới hạn của từng loại test

Trong nhóm **Thực hành tích hợp** của module **Spring Boot - testing**, một hệ thống không được chứng minh đúng chỉ bằng câu “các test xanh”. Cần trả lời: **yêu cầu cụ thể nào đã được kiểm tra, ở tầng nào, bằng những assertion nào, và điều gì vẫn chưa được chứng minh?** Đây là mục đích của **ma trận truy vết yêu cầu – test – bằng chứng – giới hạn**. Nó kết nối unit testing, Mockito, Spring test slices, JDBC, API/HTTP integration, Testcontainers, contract testing, bảo mật, resilience và CI thành một cơ chế QA có thể giải thích, tái chạy và audit.

Bài học dùng **Java 17, Spring Boot 3.5, JUnit Jupiter 5, Mockito, Spring MVC/MockMvc, JdbcTemplate, H2 và TestRestTemplate**. Phần thực hành có project runnable, **18 JUnit methods** trải đều năm lớp test, kết hợp bảng yêu cầu/tiêu chí chấp nhận/bằng chứng/giới hạn. Có Java SE demo với lệnh `javac/java` và stdout chính xác. Một PostgreSQL Testcontainers test mở rộng được phân biệt rõ là **tùy chọn**, chỉ chạy khi thêm dependency và có Docker runtime.

**Kết luận cốt lõi:** Chọn loại test **rẻ nhất nhưng đủ chứng minh rủi ro cụ thể**. Pure unit có thể chứng minh thuật toán; Mockito chứng minh tương tác với collaborator giả lập; MockMvc chứng minh Spring MVC contract khi không mở server socket; JDBC slice chứng minh câu SQL trên **DB thực sự dùng ở test**; RANDOM_PORT chứng minh HTTP thực và persistence qua server thread; Testcontainers kiểm tra engine/protocol thật nhưng không tự chứng minh production HA/load/SLO. Những phần chưa có evidence phải được ghi rõ thay vì tự đặt trạng thái PASS.

## 1. Yêu cầu, assertion, phạm vi và giới hạn là bốn câu hỏi riêng

| Thành phần | Câu hỏi | Ví dụ | Không được làm |
| --- | --- | --- | --- |
| **Requirement** | App phải làm gì? | quantity 0/11 phải bị từ chối | Dùng coverage % thay business acceptance |
| **Evidence** | Test đã quan sát/khẳng định gì? | `assertThrows` và `verifyNoInteractions` | Chỉ gọi method không assert |
| **Boundary** | Các component thật nào chạy? | MVC thật nhưng service mock | Gọi đó là full end-to-end |
| **Limitation** | Điều gì chưa được chứng minh? | Không có real TCP/SQL trong MVC slice | Bỏ trống cột gap vì test xanh |
| **Artifact** | Ai có thể xem lại kết quả? | JUnit XML, CI run, commit, fixture | Chỉ chụp “BUILD SUCCESSFUL” |

Test phải có **oracle độc lập**: expected value lấy từ yêu cầu/contract, không tính từ cùng implementation đang được kiểm tra. Với lỗi, assert loại exception/status/code và side effects; với dữ liệu, assert exact rows/fields và state sau transaction. “Không ném lỗi” thường chưa đủ chứng minh business result.

Một test result chỉ có ý nghĩa khi kèm **version code, input/fixture, môi trường, framework/DB versions, thời điểm và test execution status**. Một method được định nghĩa chưa có nghĩa đã được JUnit engine discovery; một class bị skipped chưa phải VERIFIED.

## 2. Mô hình nhiều tầng test theo trách nhiệm

```text
        User / critical end-to-end journey
                     /\
                    /  \
             Real HTTP / API contract
                 /----------\
            Spring/DB integration
             /----------------\
        MVC / JDBC / JSON test slices
          /----------------------\
       Pure unit and Mockito tests
     /----------------------------\
    Compile, lint, type and static checks
```

Cấp cao thường mang nhiều component thật hơn, setup chậm hơn và failure khó định vị hơn. Cấp thấp kiểm tra nhiều trường hợp biên nhanh và nhất quán, nhưng không chứng minh collaboration giữa các hệ thống.

**Không đồng nhất:**

- Unit test **không bắt buộc có mock**: pure Java object có thể được test trực tiếp.
- Integration test **không bắt buộc Docker**: JDBC/H2 thực trong Spring test slice đã tích hợp database, nhưng mức giống PostgreSQL production thấp hơn.
- Test E2E **không chứng minh mọi điều kiện hệ thống**: một happy path vẫn bỏ qua permission, concurrency, cache expiry hoặc outage.
- Coverage **không chứng minh assertion đủ mạnh**: 100% LINE/BRANCH vẫn có thể để lọt bug off-by-one hoặc thiếu tenant filtering.

Ma trận phải thể hiện nhiều test bổ trợ cho cùng một requirement khi có nhiều failure boundaries.

## 3. Bảng chọn loại test – bằng chứng – giới hạn

| Test layer / công cụ | Thành phần thật trong test | Bằng chứng có giá trị | Giới hạn |
| --- | --- | --- | --- |
| JUnit pure unit | Logic Java thuần | Output, exception, invariants, boundary | Không Spring wiring/HTTP/DB |
| Mockito `@Mock`/`MockitoExtension` | Service thật, collaborator fake | `verify`, arguments, error propagation, no calls | Không chứng minh SQL/API thật, proxy/AOP |
| Spring `ApplicationContextRunner` | Bean config được chọn | Property binding, conditional bean, startup failure | Không full app/server |
| `@JsonTest` | JSON mapper/modules | Field names, dates, null, no sensitive fields | Không MVC status/auth |
| `@WebMvcTest` + `MockMvc` | MVC controller/converter/advice, thường mock service | HTTP status, headers, JSON, request binding | Không real socket; DB/service mock |
| `@WebFluxTest` + `WebTestClient` | Reactive web layer | Mono/Flux response, routing/status | Không full reactive deployment |
| `@RestClientTest` | Client construction, JSON/HTTP mapping, mock remote | Expected outbound URI/headers/request/body | Không remote server hoặc network timeout thật |
| `@JdbcTest` | JdbcTemplate + DataSource | SQL/row mapping, generated keys, DB constraints | H2 không phải PostgreSQL |
| `@DataJdbcTest` | Spring Data JDBC repositories/aggregate | Repository persistence/model mapping | Không MVC/full service |
| `@DataJpaTest` | JPA repositories/EntityManager | JPQL/flush/relations/constraints | Không HTTP; DB dialect có thể khác |
| `@SpringBootTest(MOCK)` + `@AutoConfigureMockMvc` | Full context và MVC mock environment | Bean wiring + HTTP contract qua MockMvc | Không TCP/embedded server |
| `@SpringBootTest(RANDOM_PORT)` | Embedded server, real HTTP, app services | POST/GET, headers, persistence commit | Không ingress/TLS/replica network nếu chưa dựng |
| Testcontainers | Real DB/broker/cache container | Engine-specific SQL/protocol/error semantics | Không HA/load/security prod |
| Consumer/provider contract | Contract fixtures và provider verification | Compatibility của schema/example | Không toàn bộ live provider behavior |
| Security integration | Auth filters, roles, security context | 401/403, tenant isolation, no side effects | Không thay threat modeling/pentest |
| Load/soak/fault injection | Target topology và workload | p95/p99, saturation, recovery | Không mô phỏng mọi production pattern |

**Lưu ý:** Các `@…Test` slices chỉ tải một tập auto-configurations của Spring Boot. Nếu một component bị loại, cần `@Import` hoặc mock bean; không tự suy ra toàn app đã khởi động. Với tests transactional, rollback phụ thuộc Spring TestContext và thread; không quay lại side effect ngoài transaction.

## 4. Schema ma trận truy vết để dùng trong đội phát triển

| Cột | Mô tả |
| --- | --- |
| Requirement ID | ID ổn định trong ticket/spec |
| Acceptance criterion | Kết quả đo được và điều kiện biên |
| Risk/severity | Mức thiệt hại nếu sai |
| Test design/level | Unit, MVC, JDBC, HTTP, DB container, contract, perf |
| Fixture/input | Các input/rows/clock/profile/upstream responses |
| Expected evidence | Assertion chi tiết, exceptions, side effects |
| Test ID | File/class/method, hoặc đường dẫn contract |
| Actual run evidence | Report URL, commit, environment, status |
| Not proven | Rủi ro còn lại; không bỏ trống |
| Owner/CI gate | Team chịu trách nhiệm, tần suất chạy |
| State | VERIFIED / FAILED / PARTIAL / BLOCKED / NOT_IMPLEMENTED |

**Ví dụ:** “quantity phải thuộc [1,10], ngoài range POST trả 400 và không ghi order” là yêu cầu đo được. Ba lớp evidence có thể có: `OrderPolicyTest` ném exception; `OrderControllerTest` trả 400; `RealHttpOrderTest` thực HTTP 400 và SQL count=0. Không nên dùng một unit assertion để tuyên bố đã bảo vệ cả ba boundary.

## 5. Ma trận áp dụng cho API tạo đơn hàng

Project demo có `POST /orders` và `GET /orders/{id}`, SKU uppercase 2–12 ký tự, quantity 1..10, giá 250 cent mỗi đơn vị. Ghi DB qua JDBC, response tạo mới trả 201/Location, GET không thấy trả 404.

| ID | Điều kiện | Loại test tối thiểu | Assertions/evidence | Chưa được chứng minh |
| --- | --- | --- | --- | --- |
| ORD-01 | quantity 1 và 10 hợp lệ | Pure JUnit | Total 250/2500 | HTTP/JDBC |
| ORD-02 | quantity 0 và 11 không hợp lệ | Unit + MVC + real HTTP | Exception/400/DB count=0 | Ingress |
| ORD-03 | SKU null/lowercase bị từ chối | Unit + service | IllegalArgumentException, no SQL call | Unicode/locale policy khác |
| ORD-04 | Giá nhân đúng, không dùng floating point | Pure JUnit | 2 × 250 = 500 cents | Thuế/currency khác |
| ORD-05 | Service gửi đúng values tới repository | Mockito unit | verify("SKU-1",2,500) | Real SQL |
| ORD-06 | POST valid → 201, Location và JSON | MVC slice + HTTP | Status/header/id/body | Gateway/TLS |
| ORD-07 | GET existing → 200, record đúng | MVC/HTTP | SKU, qty, cents, id | Authorization |
| ORD-08 | GET missing → 404, không lộ lỗi nội bộ | MVC | HTTP 404 + generic JSON | Real routing/security |
| ORD-09 | SQL INSERT/SELECT roundtrip đúng | JDBC slice | Generated ID, fields, count | PostgreSQL-specific behavior |
| ORD-10 | DB chặn null SKU | JDBC slice | DataIntegrityViolationException | Schema production nếu khác |
| ORD-11 | POST HTTP thật commit DB | RANDOM_PORT | 201 + GET + DB count=1 | Cluster/replica |
| ORD-12 | Invalid HTTP request không ghi DB | RANDOM_PORT | 400 + DB count=0 | Concurrent side effect |
| ORD-13 | PostgreSQL dialect/driver thật | Testcontainers | SQL cast/constraints trên Postgres | HA/production load |
| ORD-14 | Duplicate POST/retry không tạo đơn trùng | Concurrency+DB+HTTP | Idempotency key/unique count | Chưa implement |
| ORD-15 | User sai quyền/tenant không truy cập | Security+DB | 401/403, no rows/leaks | Chưa implement |
| ORD-16 | Provider/consumer schema tương thích | Contract verification | Schema/version examples | Provider uptime |
| ORD-17 | Timeout không bị báo thành công giả | HTTP fault injection | Unknown/retry/reconciliation | Chưa implement |
| ORD-18 | p95 dưới SLO tại tải được duyệt | Load test | Workload + latency/error graphs | Test topology ≠ production |

**ORD-01..12** có mã test minh họa bên dưới ở các phạm vi khác nhau; **ORD-13** có test Docker optional; **ORD-14..18** là các khoảng trống của demo, không được báo “PASS”. Trong product thực, phải giao owner/mitigation riêng.

## 6. Phạm vi của project runnable

Tất cả file demo dùng package `example.evidence`. Có một Spring Boot main class, JDBC interface+implementation, policy, service, controller, advice, schema SQL, năm test classes. Không có auth, inventory, payment hoặc event bus; ví dụ phục vụ phân biệt **evidence theo tầng**, không được coi là hệ thống đơn hàng production.

```text
evidence-matrix/
├── build.gradle
└── src/
    ├── main/
    │   ├── java/example/evidence/
    │   │   ├── EvidenceApplication.java
    │   │   ├── OrderPolicy.java
    │   │   ├── OrderRequest.java
    │   │   ├── OrderReceipt.java
    │   │   ├── OrderStore.java
    │   │   ├── JdbcOrderStore.java
    │   │   ├── OrderNotFoundException.java
    │   │   ├── OrderService.java
    │   │   ├── OrderController.java
    │   │   ├── OrderErrorAdvice.java
    │   │   └── OrderPolicyDemo.java
    │   └── resources/
    │       ├── application.properties
    │       └── schema.sql
    └── test/java/example/evidence/
        ├── OrderPolicyTest.java
        ├── OrderServiceTest.java
        ├── OrderControllerTest.java
        ├── JdbcOrderStoreTest.java
        └── RealHttpOrderTest.java
```

**Sơ đồ hành vi:**

```text
POST /orders
  |
  v
OrderController -- JSON request/response & HTTP 201
  |
  v
OrderService ---- @Transactional
  |
  +---- OrderPolicy ---- SKU, quantity, totalCents (pure Java)
  |
  +---- OrderStore interface
           |
           v
       JdbcOrderStore ---- SQL / generated key / constraint
           |
           v
          H2

GET /orders/{id} -> OrderService.find -> JdbcOrderStore.find
                                  -> OrderNotFoundException -> 404
```

## 7. build.gradle – phụ thuộc tối thiểu, không Docker

Tạo `build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.0'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'example'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'

    runtimeOnly 'com.h2database:h2'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

**Spring Boot 3.5** dùng Spring Framework 6.2, nên imports trong @WebMvcTest và `@MockitoBean` thuộc API dòng này. Khi chuyển Boot4, test starter/package changes cần được xem lại. Java17 là baseline. H2 là database thật chạy embedded nhưng không phải PostgreSQL. `useJUnitPlatform()` cho JUnit Jupiter test discovery.

**Maven/Gradle:** Dùng BOM của Boot để đồng bộ JUnit, Mockito, JDBC và Spring Test; không pin riêng một Jupiter Engine bất tương thích với Platform. Wrapper Gradle tương thích phải được tạo trước khi chạy `./gradlew`; build.gradle tự nó không sinh wrapper.

## 8. schema.sql và cấu hình embedded DB

Tạo `src/main/resources/application.properties`:

```properties
spring.datasource.generate-unique-name=true
spring.sql.init.mode=always
```

Tạo `src/main/resources/schema.sql`:

```sql
CREATE TABLE orders (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    sku VARCHAR(12) NOT NULL,
    quantity INTEGER NOT NULL,
    total_cents INTEGER NOT NULL
);
```

H2 runtime trên classpath cho phép Boot auto-config embedded DataSource. Mỗi context có thể dùng tên DB riêng; schema.sql chạy trong SQL initialization. `NOT NULL` là một contract DB có thể test bằng real SQL. Không có Flyway/Liquibase trong demo: với sản phẩm thật, migration cần được version hóa và kiểm thử trên PostgreSQL chính thức hoặc Testcontainers đúng engine.

## 9. OrderPolicy.java: logic không phụ thuộc Spring

Tạo `src/main/java/example/evidence/OrderPolicy.java`:

```java
package example.evidence;

public final class OrderPolicy {
    public int totalCents(String sku, int quantity) {
        if (sku == null
                || !sku.matches("[A-Z0-9-]{2,12}")) {
            throw new IllegalArgumentException("invalid sku");
        }

        if (quantity < 1 || quantity > 10) {
            throw new IllegalArgumentException(
                    "quantity must be 1..10");
        }

        return Math.multiplyExact(quantity, 250);
    }
}
```

Rules: SKU 2..12 uppercase ASCII/alphanumeric/hyphen; qty 1..10; price 250 integer cents. `sku==null` an toàn nhờ short-circuit `||`. `Math.multiplyExact` bảo vệ overflow nếu giới hạn thay đổi về sau, nhưng với qty≤10 thì không thể overflow tại contract hiện tại.

**Chứng cứ tầng unit:** expected từ rule: qty1 →250, qty10→2500, invalid→exception. **Chưa chứng minh:** Query binding, response mapping hoặc DB transaction.

## 10. DTO records cho request và response

Tạo `src/main/java/example/evidence/OrderRequest.java`:

```java
package example.evidence;

public record OrderRequest(String sku, int quantity) {
}
```

Tạo `src/main/java/example/evidence/OrderReceipt.java`:

```java
package example.evidence;

public record OrderReceipt(
        long id, String sku,
        int quantity, int totalCents) {
}
```

Spring Boot3.5 với Jackson hỗ trợ serialization/deserialization Java17 records. API response dùng các fields id,sku,quantity,totalCents. Khi thay đổi schema thật, cần tests về null/default, unknown fields, backwards compatibility, fields nhạy cảm, currency/precision, timezone và enum versioning.

## 11. OrderStore.java: repository abstraction

Tạo `src/main/java/example/evidence/OrderStore.java`:

```java
package example.evidence;

import java.util.Optional;

public interface OrderStore {

    long create(
            String sku, int quantity, int totalCents);

    Optional<OrderReceipt> find(long id);

    long count();
}
```

Service unit tests sẽ mock OrderStore để xác nhận **lời gọi**, không cần database. Nhưng Mockito không chứng minh SQL; cần JDBC slice để xác minh code của implementation.

## 12. JdbcOrderStore.java: SQL implementation

Tạo `src/main/java/example/evidence/JdbcOrderStore.java`:

```java
package example.evidence;

import java.sql.PreparedStatement;
import java.sql.Statement;
import java.util.Optional;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.support.GeneratedKeyHolder;
import org.springframework.jdbc.support.KeyHolder;
import org.springframework.stereotype.Repository;

@Repository
public class JdbcOrderStore implements OrderStore {
    private final JdbcTemplate jdbc;

    public JdbcOrderStore(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Override
    public long create(
            String sku, int quantity, int totalCents) {
        KeyHolder keys = new GeneratedKeyHolder();

        jdbc.update(connection -> {
            PreparedStatement ps =
                    connection.prepareStatement(
                            "INSERT INTO orders "
                            + "(sku, quantity, total_cents) "
                            + "VALUES (?, ?, ?)",
                            Statement.RETURN_GENERATED_KEYS);
            ps.setString(1, sku);
            ps.setInt(2, quantity);
            ps.setInt(3, totalCents);
            return ps;
        }, keys);

        Number key = keys.getKey();
        if (key == null) {
            throw new IllegalStateException(
                    "database did not return id");
        }
        return key.longValue();
    }

    @Override
    public Optional<OrderReceipt> find(long id) {
        return jdbc.query(
                "SELECT id, sku, quantity, total_cents "
                + "FROM orders WHERE id = ?",
                (rs, row) -> new OrderReceipt(
                        rs.getLong("id"),
                        rs.getString("sku"),
                        rs.getInt("quantity"),
                        rs.getInt("total_cents")),
                id).stream().findFirst();
    }

    @Override
    public long count() {
        Long value = jdbc.queryForObject(
                "SELECT COUNT(*) FROM orders", Long.class);
        return value == null ? 0L : value;
    }
}
```

SQL dùng prepared statement và bound parameters; generated key được kiểm tra không null. `JdbcTemplate` dịch SQLException thành hệ DataAccessException phù hợp. **JDBC integration evidence** phải assert ID, query result và constraint; không gọi unit mock repository là SQL test.

## 13. OrderNotFoundException và OrderService

Tạo `src/main/java/example/evidence/OrderNotFoundException.java`:

```java
package example.evidence;

public final class OrderNotFoundException
        extends RuntimeException {
    public OrderNotFoundException(long id) {
        super("order not found: " + id);
    }
}
```

Tạo `src/main/java/example/evidence/OrderService.java`:

```java
package example.evidence;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderService {
    private final OrderPolicy policy;
    private final OrderStore store;

    public OrderService(
            OrderPolicy policy, OrderStore store) {
        this.policy = policy;
        this.store = store;
    }

    @Transactional
    public OrderReceipt create(OrderRequest request) {
        int total = policy.totalCents(
                request.sku(), request.quantity());
        long id = store.create(
                request.sku(), request.quantity(), total);

        return new OrderReceipt(
                id, request.sku(),
                request.quantity(), total);
    }

    @Transactional(readOnly = true)
    public OrderReceipt find(long id) {
        return store.find(id)
                .orElseThrow(
                        () -> new OrderNotFoundException(id));
    }
}
```

Spring quản lý transaction thông qua proxy với `@Transactional` trên service bean. Nếu unit test gọi `new OrderService(...)`, code business vẫn chạy nhưng **không đi qua Spring transaction advice**. Vì vậy unit Mockito test không đủ chứng minh rollback/commit; HTTP integration hoặc Spring-managed service integration với database mới phù hợp.

## 14. OrderController và error advice

Tạo `src/main/java/example/evidence/OrderController.java`:

```java
package example.evidence;

import java.net.URI;

import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/orders")
public class OrderController {
    private final OrderService service;

    public OrderController(OrderService service) {
        this.service = service;
    }

    @PostMapping
    public ResponseEntity<OrderReceipt> create(
            @RequestBody OrderRequest request) {
        OrderReceipt receipt = service.create(request);

        return ResponseEntity.created(
                URI.create("/orders/" + receipt.id()))
                .body(receipt);
    }

    @GetMapping("/{id}")
    public OrderReceipt find(@PathVariable long id) {
        return service.find(id);
    }
}
```

Tạo `src/main/java/example/evidence/OrderErrorAdvice.java`:

```java
package example.evidence;

import java.util.Map;

import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
public class OrderErrorAdvice {

    @ExceptionHandler(IllegalArgumentException.class)
    public ResponseEntity<Map<String, String>> badInput() {
        return ResponseEntity.badRequest()
                .body(Map.of("error", "invalid order input"));
    }

    @ExceptionHandler(OrderNotFoundException.class)
    public ResponseEntity<Map<String, String>> notFound() {
        return ResponseEntity.status(404)
                .body(Map.of("error", "order not found"));
    }
}
```

Controller trả **201 + Location + JSON** cho tạo mới, **200** cho GET, **400** cho invalid domain, **404** cho missing ID. Malformed JSON bị Spring MVC message conversion từ chối trước khi gọi service.

**Một test @WebMvcTest mock service** có thể assert body/header/status, nhưng không đo SQL hoặc network transport. Một full HTTP test có real service/DB sẽ bổ sung phạm vi ấy.

## 15. EvidenceApplication.java: một application root

Tạo `src/main/java/example/evidence/EvidenceApplication.java`:

```java
package example.evidence;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class EvidenceApplication {

    @Bean
    OrderPolicy orderPolicy() {
        return new OrderPolicy();
    }

    public static void main(String[] args) {
        SpringApplication.run(
                EvidenceApplication.class, args);
    }
}
```

Spring component scanning tìm repository/service/controller/advice cùng package. PricePolicy là Java thuần được khai báo thành bean qua cấu hình chính. Tránh có nhiều `@SpringBootConfiguration` không rõ scope trong cùng root test vì Boot test slices có thể tìm sai config.

## 16. OrderPolicyTest.java – 4 JUnit unit methods

Tạo `src/test/java/example/evidence/OrderPolicyTest.java`:

```java
package example.evidence;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

class OrderPolicyTest {
    private final OrderPolicy policy = new OrderPolicy();

    @Test
    void validBoundaryQuantitiesHaveExactTotals() {
        assertEquals(250,
                policy.totalCents("SKU-1", 1));
        assertEquals(2500,
                policy.totalCents("SKU-1", 10));
    }

    @Test
    void nullSkuIsRejected() {
        assertThrows(
                IllegalArgumentException.class,
                () -> policy.totalCents(null, 2));
    }

    @Test
    void lowercaseSkuIsRejected() {
        assertThrows(
                IllegalArgumentException.class,
                () -> policy.totalCents("sku-1", 2));
    }

    @Test
    void outsideQuantityRangeIsRejected() {
        assertThrows(
                IllegalArgumentException.class,
                () -> policy.totalCents("SKU-1", 0));
        assertThrows(
                IllegalArgumentException.class,
                () -> policy.totalCents("SKU-1", 11));
    }
}
```

Đây là **4 JUnit methods** để chứng minh ORD-01..04 trong phạm vi pure policy. Không chạy Spring context, SQL hay HTTP. Test đúng ở quantity=1 và 10 quan trọng: một mutant `quantity > 10` thành `quantity >= 10` sẽ bị test tại 10 bắt; chỉ test quantity=2 không phát hiện.

## 17. OrderServiceTest.java – 4 Mockito methods

Tạo `src/test/java/example/evidence/OrderServiceTest.java`:

```java
package example.evidence;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;

@ExtendWith(MockitoExtension.class)
class OrderServiceTest {

    @Mock
    OrderStore store;

    private OrderService service;

    @BeforeEach
    void setUp() {
        service = new OrderService(
                new OrderPolicy(), store);
    }

    @Test
    void passesCorrectValuesToRepository() {
        when(store.create("SKU-1", 2, 500))
                .thenReturn(42L);

        OrderReceipt result =
                service.create(new OrderRequest("SKU-1", 2));

        assertEquals(
                new OrderReceipt(42L, "SKU-1", 2, 500),
                result);
        verify(store).create("SKU-1", 2, 500);
    }

    @Test
    void invalidSkuDoesNotTouchStore() {
        assertThrows(
                IllegalArgumentException.class,
                () -> service.create(
                        new OrderRequest("lowercase", 2)));

        verifyNoInteractions(store);
    }

    @Test
    void invalidQuantityDoesNotTouchStore() {
        assertThrows(
                IllegalArgumentException.class,
                () -> service.create(
                        new OrderRequest("SKU-1", 11)));

        verifyNoInteractions(store);
    }

    @Test
    void repositoryErrorIsNotHidden() {
        when(store.create("SKU-1", 2, 500))
                .thenThrow(
                        new IllegalStateException("db unavailable"));

        assertThrows(
                IllegalStateException.class,
                () -> service.create(
                        new OrderRequest("SKU-1", 2)));

        verify(store).create("SKU-1", 2, 500);
    }
}
```

**4 methods**: real service + mock collaborator. `MockitoExtension` tạo @Mock. `verifyNoInteractions(store)` cho biết validation xảy ra **trước** external side effect. `verify(store).create("SKU-1",2,500)` cho biết arguments, không chỉ return từ mock. **Giới hạn:** Không chạy database hay Spring transaction proxy trong test này.

## 18. OrderControllerTest.java – 5 MockMvc methods

Tạo `src/test/java/example/evidence/OrderControllerTest.java`:

```java
package example.evidence;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.http.MediaType;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;

import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(OrderController.class)
class OrderControllerTest {

    @Autowired
    MockMvc mvc;

    @MockitoBean
    OrderService service;

    @Test
    void postCreatesResourceWithLocation() throws Exception {
        when(service.create(
                new OrderRequest("SKU-1", 2)))
                .thenReturn(
                        new OrderReceipt(42L, "SKU-1", 2, 500));

        mvc.perform(post("/orders")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(
                                "{\"sku\":\"SKU-1\",\"quantity\":2}"))
                .andExpect(status().isCreated())
                .andExpect(
                        header().string("Location", "/orders/42"))
                .andExpect(jsonPath("$.id").value(42))
                .andExpect(
                        jsonPath("$.totalCents").value(500));
    }

    @Test
    void domainValidationBecomes400() throws Exception {
        when(service.create(
                new OrderRequest("SKU-1", 0)))
                .thenThrow(
                        new IllegalArgumentException("invalid qty"));

        mvc.perform(post("/orders")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(
                                "{\"sku\":\"SKU-1\",\"quantity\":0}"))
                .andExpect(status().isBadRequest())
                .andExpect(
                        jsonPath("$.error")
                                .value("invalid order input"));
    }

    @Test
    void getReturnsExistingReceipt() throws Exception {
        when(service.find(42L))
                .thenReturn(
                        new OrderReceipt(42L, "SKU-1", 2, 500));

        mvc.perform(get("/orders/42"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.sku").value("SKU-1"))
                .andExpect(
                        jsonPath("$.totalCents").value(500));
    }

    @Test
    void notFoundMapsTo404() throws Exception {
        when(service.find(999L))
                .thenThrow(new OrderNotFoundException(999L));

        mvc.perform(get("/orders/999"))
                .andExpect(status().isNotFound())
                .andExpect(
                        jsonPath("$.error")
                                .value("order not found"));
    }

    @Test
    void malformedJsonNeverCallsService() throws Exception {
        mvc.perform(post("/orders")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{bad-json"))
                .andExpect(status().isBadRequest());

        verifyNoInteractions(service);
    }
}
```

**5 methods** assert binding/serialization, 201+Location, JSON, error mappings 400/404 và malformed JSON. `@MockitoBean` của Spring Framework6.2 là cách override/tạo **bean mock trong ApplicationContext**, khác với Mockito field `@Mock`.

**Giới hạn:** MockMvc không mở network socket và service là mock; nó **không** chứng minh transaction/database/real server. Khi có Spring Security, MVC slice có thể áp security filters; phải có tests có user/roles/CSRF tương ứng, không tùy tiện tắt tất cả security filters chỉ để test xanh.

## 19. JdbcOrderStoreTest.java – 3 @JdbcTest methods

Tạo `src/test/java/example/evidence/JdbcOrderStoreTest.java`:

```java
package example.evidence;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.jdbc.JdbcTest;
import org.springframework.context.annotation.Import;
import org.springframework.dao.DataIntegrityViolationException;
import org.springframework.jdbc.core.JdbcTemplate;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

@JdbcTest
@Import(JdbcOrderStore.class)
class JdbcOrderStoreTest {

    @Autowired
    JdbcOrderStore store;

    @Autowired
    JdbcTemplate jdbc;

    @Test
    void insertAndFindRoundtrip() {
        long id = store.create("SKU-1", 2, 500);

        assertTrue(id > 0);
        assertEquals(
                new OrderReceipt(id, "SKU-1", 2, 500),
                store.find(id).orElseThrow());
        assertEquals(1L, store.count());
    }

    @Test
    void unknownIdReturnsEmpty() {
        assertFalse(
                store.find(9_999_999L).isPresent());
        assertEquals(0L, store.count());
    }

    @Test
    void notNullConstraintIsEnforcedByDatabase() {
        assertThrows(
                DataIntegrityViolationException.class,
                () -> jdbc.update(
                        "INSERT INTO orders "
                        + "(sku, quantity, total_cents) "
                        + "VALUES (?, ?, ?)",
                        (Object) null, 1, 250));
    }
}
```

**3 methods** dùng JDBC/DataSource **thật trên H2**. `@JdbcTest` thường mặc định transactional và rollback cuối method; `@Import(JdbcOrderStore.class)` chọn repository implementation vì slice không tự đưa toàn bộ service/DAO tùy ý vào. `schema.sql` tạo bảng; DB NOT NULL thật sự ném SQLException được Spring translate thành `DataIntegrityViolationException`.

`@DataJdbcTest` dành cho Spring Data JDBC repositories/aggregates; bài này viết JDBC trực tiếp nên `@JdbcTest` hợp lý. Nếu production dùng PostgreSQL, H2 test chưa kiểm chứng PostgreSQL syntax, index, isolation, JSONB, migration hay driver.

## 20. RealHttpOrderTest.java – 2 HTTP integration methods

Tạo `src/test/java/example/evidence/RealHttpOrderTest.java`:

```java
package example.evidence;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.client.TestRestTemplate;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.jdbc.core.JdbcTemplate;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class RealHttpOrderTest {

    @Autowired
    TestRestTemplate http;

    @Autowired
    JdbcTemplate jdbc;

    @BeforeEach
    void prepare() {
        jdbc.update("DELETE FROM orders");
    }

    @AfterEach
    void cleanup() {
        jdbc.update("DELETE FROM orders");
    }

    @Test
    void postCommitsAndGetReturnsSameReceipt() {
        ResponseEntity<OrderReceipt> created =
                http.postForEntity(
                        "/orders",
                        new OrderRequest("SKU-1", 2),
                        OrderReceipt.class);

        assertEquals(
                HttpStatus.CREATED, created.getStatusCode());

        OrderReceipt receipt = created.getBody();
        assertNotNull(receipt);
        assertTrue(receipt.id() > 0);
        assertEquals(500, receipt.totalCents());

        assertNotNull(
                created.getHeaders().getLocation());
        assertEquals(
                "/orders/" + receipt.id(),
                created.getHeaders()
                        .getLocation().getPath());

        ResponseEntity<OrderReceipt> fetched =
                http.getForEntity(
                        "/orders/{id}",
                        OrderReceipt.class,
                        receipt.id());

        assertEquals(
                HttpStatus.OK, fetched.getStatusCode());
        assertEquals(receipt, fetched.getBody());

        assertEquals(
                1L,
                jdbc.queryForObject(
                        "SELECT COUNT(*) FROM orders",
                        Long.class));
    }

    @Test
    void invalidPostReturns400AndDoesNotPersist() {
        ResponseEntity<String> result =
                http.postForEntity(
                        "/orders",
                        new OrderRequest("SKU-1", 0),
                        String.class);

        assertEquals(
                HttpStatus.BAD_REQUEST,
                result.getStatusCode());
        assertNotNull(result.getBody());
        assertTrue(result.getBody()
                .contains("invalid order input"));

        assertEquals(
                0L,
                jdbc.queryForObject(
                        "SELECT COUNT(*) FROM orders",
                        Long.class));
    }
}
```

**2 methods** mở embedded server qua `RANDOM_PORT` thật và dùng `TestRestTemplate` gửi request qua HTTP loopback. Những assertions kết hợp **HTTP 201/400, Location, body, GET, JDBC count** có bằng chứng mạnh hơn MockMvc service mock.

**Vì sao @AfterEach DELETE quan trọng:** HTTP server xử lý request trên **thread khác** test method, nên @Transactional trên test không rollback server-side transaction. Demo chủ động cleanup. Tuy nhiên, xóa toàn bảng chỉ an toàn khi test database không bị chia sẻ với những test writers chạy song song; hệ thống thật nên dùng per-test schema/database, test tenant/ID hoặc cleanup có ownership rõ.

**Giới hạn:** Loopback chưa test ingress proxy, TLS, auth provider, multi-replica consistency, production database, retry storm hoặc p95 under load. Cần test riêng nếu các điều ấy là requirements.

## 21. Tổng số phương thức test và ma trận chứng minh

| Test class | Số @Test methods | Phạm vi |
| --- | ---: | --- |
| `OrderPolicyTest` | 4 | SKU/quantity/price pure Java |
| `OrderServiceTest` | 4 | Mockito interactions |
| `OrderControllerTest` | 5 | MVC route, JSON, status |
| `JdbcOrderStoreTest` | 3 | SQL/constraint H2 |
| `RealHttpOrderTest` | 2 | Real HTTP + committed DB state |
| **Tổng** | **18** | |

**18 là số methods định nghĩa trong mã nguồn**, không có nghĩa 18 methods đã chạy trong môi trường của người học. Để chuyển thành VERIFIED, CI phải có executed count, skipped count, error details và artifact. Không lấy số branch coverage hoặc số test methods để suy ra yêu cầu đã đầy đủ.

**Mapping:** ORD-01..04 dựa unit; ORD-05 dựa Mockito; ORD-06..08 dựa MVC; ORD-09/10 dựa JDBC; ORD-11/12 dựa HTTP/JDBC; ORD-13..18 yêu cầu các bài kiểm chứng bổ sung.

## 22. OrderPolicyDemo.java – Java SE stdout xác định

Tạo `src/main/java/example/evidence/OrderPolicyDemo.java`:

```java
package example.evidence;

public class OrderPolicyDemo {
    public static void main(String[] args) {
        OrderPolicy policy = new OrderPolicy();

        System.out.println(
                "one=" + policy.totalCents("SKU-1", 1));
        System.out.println(
                "two=" + policy.totalCents("SKU-1", 2));
        System.out.println(
                "ten=" + policy.totalCents("SKU-1", 10));

        try {
            policy.totalCents("SKU-1", 11);
        } catch (IllegalArgumentException error) {
            System.out.println(
                    "invalid=" + error.getMessage());
        }
    }
}
```

Chạy từ project root bằng JDK17+:

```bash
javac -d out src/main/java/example/evidence/OrderPolicy.java src/main/java/example/evidence/OrderPolicyDemo.java
java -cp out example.evidence.OrderPolicyDemo
```

Stdout **chính xác**:

```text
one=250
two=500
ten=2500
invalid=quantity must be 1..10
```

Chạy Java SE demo **không** khởi động Spring/JUnit/JDBC/HTTP và không được ghi vào ma trận là Spring integration PASS. Nó là bài kiểm chứng độc lập cho logic thuần Java.

## 23. Lệnh chạy JUnit và lấy bằng chứng từ build

Linux/macOS:

```bash
./gradlew test --tests example.evidence.OrderPolicyTest
./gradlew test --tests example.evidence.OrderServiceTest
./gradlew test --tests example.evidence.OrderControllerTest
./gradlew test --tests example.evidence.JdbcOrderStoreTest
./gradlew test --tests example.evidence.RealHttpOrderTest
./gradlew clean test
```

Windows PowerShell:

```powershell
.\gradlew.bat test --tests "example.evidence.OrderPolicyTest"
.\gradlew.bat test --tests "example.evidence.OrderServiceTest"
.\gradlew.bat test --tests "example.evidence.OrderControllerTest"
.\gradlew.bat test --tests "example.evidence.JdbcOrderStoreTest"
.\gradlew.bat test --tests "example.evidence.RealHttpOrderTest"
```

Build reports thường ở:

```text
build/test-results/test/*.xml
build/reports/tests/test/index.html
```

Ghi liên kết CI job, commit SHA, JDK/Boot versions, test name, fixture schema và environment. Đọc cả counts **executed/skipped/failed**; build SUCCESSFUL chưa chắc tất cả requirements được test nếu test engine không discover, filter excludes hoặc test bị skip. Không viết stdout Gradle cố định, vì logging và tasks up-to-date/caching khác nhau.

## 24. PostgreSQL Testcontainers: mức bằng chứng bổ sung

Nếu ORD-13 yêu cầu PostgreSQL thật, H2 không đủ. Với **Boot3.5/Testcontainers1.x**, thêm vào `dependencies` của build.gradle:

```groovy
testImplementation 'org.springframework.boot:spring-boot-testcontainers'
testImplementation 'org.testcontainers:junit-jupiter'
testImplementation 'org.testcontainers:postgresql'
testRuntimeOnly 'org.postgresql:postgresql'
```

Sau đó có thể thêm file `src/test/java/example/evidence/PostgresEvidenceTest.java` (test **tùy chọn**, không tính trong 18 methods của demo mặc định):

```java
package example.evidence;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.testcontainers.service.connection.ServiceConnection;
import org.springframework.jdbc.core.JdbcTemplate;

import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

import static org.junit.jupiter.api.Assertions.assertEquals;

@SpringBootTest
@Testcontainers
class PostgresEvidenceTest {

    @Container
    @ServiceConnection
    static PostgreSQLContainer<?> postgres =
            new PostgreSQLContainer<>("postgres:16-alpine")
                    .withDatabaseName("evidence");

    @Autowired
    JdbcTemplate jdbc;

    @Test
    void usesActualPostgresUuidType() {
        String value = jdbc.queryForObject(
                "SELECT '00000000-0000-0000-0000-000000000001'::uuid::text",
                String.class);

        assertEquals(
                "00000000-0000-0000-0000-000000000001",
                value);
    }
}
```

Đây là real Postgres protocol/driver/SQL trên container, **cần Docker-compatible runtime**. `@ServiceConnection` tạo connection details để app DataSource dùng container, không hardcode mapped port/password. Nếu container không start, job phải FAIL hoặc BLOCKED/explicitly skipped, không được báo DB VERIFIED.

**Chưa chứng minh:** DB production HA, isolation với data lớn, migration drift, replication/network latency hoặc security policies. Khi migrate từ H2 sang Postgres, test Flyway/Liquibase migration và các unique/index/locking/transaction semantics trên engine thật.

**Giới hạn phiên bản:** Testcontainers2 đi với Boot4 thay đổi artifacts PostgreSQL/JUnit Jupiter và PostgreSQLContainer import. Ví dụ dùng Testcontainers1 tương thích Boot3.5, không copy nguyên xi khi nâng Boot4.

## 25. Contract tests – consumer fake khác provider verification

Một contract test cần phân biệt:

- **Unit fake gateway**: app xử lý 200/404/503 giả lập theo expected mapping.
- **`@RestClientTest`/MockRestServiceServer**: request URI, headers, JSON serializer và response decode với mock HTTP server semantics ở client layer.
- **WireMock loopback real socket**: network/protocol request được gửi tới một HTTP server giả lập, kiểm tra timeout/error mapping ở client.
- **Consumer-driven contract** (ví dụ Pact): ghi kỳ vọng consumer và chạy provider verification trên provider thực hoặc môi trường đủ thật.
- **Staging E2E**: request qua các service boundaries thực.
- **Production monitoring**: provider drift/outages/latency sau rollout.

Một mock trả 200 như fixture của mình **không chứng minh** provider production luôn trả schema đó. Provider contract verification **không chứng minh** production performance/retry. Ma trận phải ghi riêng kết quả consumer test, provider verification, contract version và rủi ro không được bao phủ.

## 26. Security, tenant và dữ liệu nhạy cảm

| Requirement | Test level | Evidence nên có | Limitation |
| --- | --- | --- | --- |
| Chưa login không POST được | MVC/security integration | 401 + no DB write | Không verify external IdP |
| User role sai không ghi được | Security + real service | 403 + zero side effects | Token transport chưa kiểm |
| User tenant A không đọc tenant B | DB/HTTP security integration | 403/404, no cross-tenant row | Replica/cache path chưa kiểm |
| JWT signature/expiry bị từ chối | Auth filter integration | 401, no service call | IdP outages/rotation còn rủi ro |
| JSON không lộ token/password | `@JsonTest` + MVC | Sensitive fields absent | Logging/trace còn rủi ro |
| CSRF với form/session flows | MockMvc + spring-security-test | Missing token rejected | Deployment cookie policy |

**@WithMockUser** thuận tiện kiểm tra authorization khi Spring Security đã được tích hợp, nhưng nó không chứng minh provider JWT signature/OIDC discovery. Demo **không có Spring Security**; ORD-15 là gap chưa implement, không được suy ra security VERIFIED từ những HTTP tests hiện có.

## 27. Transaction và async: test-managed rollback không phải universal cleanup

Theo Spring TestContext, test transaction thường bind vào **ThreadLocal** ở thread chạy test. Với `@JdbcTest` hoặc `@Transactional` test, mặc định rollback khi method kết thúc (trừ cấu hình khác). Nhưng:

- Trong `@SpringBootTest(webEnvironment=RANDOM_PORT)`, HTTP client/server chạy trên threads khác nhau nên server transaction **không** rollback theo test thread.
- `@Async` executor hoặc worker chạy ngoài thread của test, không tự kế thừa test-managed transaction.
- `@Transactional(REQUIRES_NEW)` có propagation và commit scope khác.
- `assertTimeoutPreemptively(...)` có thể chạy body trên thread khác, khiến database calls thoát test transaction. Với DB-bound tests cân nhắc non-preemptive timeout khi phù hợp.
- External HTTP/messaging side effects không được rollback bởi local DB transaction.
- Client timeout không chứng minh server chưa commit; retry POST cần idempotency key hoặc reconciliation.

**Evidence đúng:** khi kiểm thử rollback, tạo lỗi rồi truy vấn state ở transaction boundary phù hợp; khi thực HTTP, query dữ liệu sau response và cleanup committed rows; khi async, chờ completion có bounded timeout và assert worker-side state. Chỉ thấy annotation `@Transactional` trên service không chứng minh behavior đã được test.

## 28. Concurrency và idempotency là gaps riêng

Một test tạo order thành công một lần không chứng minh duplicate prevention khi hai requests đến đồng thời. Requirement ORD-14 cần:

1. Contract định nghĩa cùng idempotency key → tối đa một logical order.
2. DB unique constraint hoặc explicit transactional state machine.
3. Concurrent requests với barrier/latch để đẩy calls cùng lúc.
4. Bounded Future.get/wait và cleanup executor.
5. Assert **final DB state**, response/error behavior và count.
6. Retry sau timeout và process restart trong kịch bản phù hợp.

Ngay cả khi một stress test pass, nó không vét hết mọi interleaving, nên vẫn cần reasoning về atomicity/DB constraints và production observability. Chưa có idempotency trong demo, nên ORD-14 = NOT_IMPLEMENTED.

## 29. Resilience/timeout/fallback: loại test nào chứng minh được gì?

| Câu hỏi | Evidence tốt | Không được suy luận |
| --- | --- | --- |
| Client request timeout thực hoạt động? | Local HTTP server giữ response, bounded failure | Mock exception là network timeout test |
| Retry chỉ khi lỗi transient? | Fake gateway + virtual time/attempt counter | Retry luôn an toàn cho POST |
| Circuit breaker OPEN đúng threshold? | Real breaker state + fake port, assert no new call | OPEN dừng in-flight calls |
| HALF_OPEN recovery đúng? | State transition/probe tests | Thread.sleep một lần chứng minh đủ |
| Fallback có policy an toàn? | 503/degraded marker + no false success | Fallback data luôn đúng mọi tenant |
| Provider phục hồi dưới outage? | Controlled fault injection + recovery metrics | Một success = production SLO |

Test binding cấu hình timeout khác với test network timeout; test fallback policy khác với test application consistency sau timeout. Ma trận nên tách các assertion ấy. Khi lỗi có side effects quan trọng, không bao giờ trả “success” từ một fallback chỉ vì upstream unavailable.

## 30. Config/profile và Spring TestContext cache

Với `@ConditionalOnProperty`, nên dùng `ApplicationContextRunner.withPropertyValues(...)` để test nhiều config vectors nhanh và cô lập; với full app có `@SpringBootTest(properties=...)` hoặc `@TestPropertySource`. Không dùng `System.setProperty` toàn JVM giữa các parallel tests và cho rằng bean đã được rebind sau khi context refresh.

Ví dụ **snippet, không phải file runnable độc lập**:

```java
new ApplicationContextRunner()
    .withUserConfiguration(MyConfiguration.class)
    .withPropertyValues("app.feature.enabled=false")
    .run(context -> {
        assertThat(context)
            .doesNotHaveBean(ExternalFeature.class);
    });
```

Cần các classes/imports thực, không được chép nguyên snippet rồi tuyên bố compile. Context runner chứng minh **bean presence/binding**, không HTTP/DB. Spring TestContext caching reuse contexts với config tương đương; singleton mutable caches có thể leak giữa tests. `@DirtiesContext` chỉ làm recreate context, không tự reset static fields/System properties/Locale/TimeZone, external DB/file hoặc background tasks.

## 31. Evidence report và trạng thái QA có thể hành động

| State | Nghĩa chính xác | Quyết định |
| --- | --- | --- |
| VERIFIED | Test chạy trên environment phù hợp, assertions pass, artifacts có sẵn | Ghi commit/version và giới hạn |
| FAILED | Expected và observed khác nhau | Triaging, chặn gate theo severity |
| PARTIAL | Chỉ một phần requirement/boundary có evidence | Ghi gaps/owners |
| BLOCKED | Không chạy vì thiếu Docker, credentials, environment | Không gọi PASS |
| NOT_IMPLEMENTED | Chưa có tests hoặc khả năng cần kiểm chứng | Ticket, owner, deadline/mitigation |
| NOT_APPLICABLE | Không áp dụng theo phạm vi được phê duyệt | Lưu rationale |

Một **hồ sơ minh họa**, không phải kết quả chạy thực:

```json
{
  "requirementId": "ORD-11",
  "test": "RealHttpOrderTest.postCommitsAndGetReturnsSameReceipt",
  "environment": "Java17/Boot3.5/H2",
  "expected": [
    "HTTP 201",
    "Location matches generated ID",
    "HTTP GET returns stored receipt",
    "SQL count = 1"
  ],
  "execution": "EXAMPLE_NOT_EXECUTED",
  "limitations": [
    "PostgreSQL not proven",
    "TLS/ingress not proven",
    "concurrent duplicate handling not proven"
  ]
}
```

**Đặc biệt:** Khi publish bài học hoặc review code mà chưa chạy test thật, giữ nhãn `EXAMPLE_NOT_EXECUTED`. “Source có 18 @Test methods” là thông tin cấu trúc; “18 tests PASS” là kết quả chỉ có thể xác nhận từ runner.

## 32. CI, test counts, coverage và artifacts

Chạy:

```bash
./gradlew clean test
```

Các JUnit/Gradle artifacts thông thường:

```text
build/test-results/test/*.xml
build/reports/tests/test/index.html
```

Lưu **commit SHA, JDK/Boot/DB version, test IDs, environment, input fixtures, executed/skipped/failed counts và report URLs**. Một build xanh với tests bị filter/skip không đủ chứng minh toàn bộ yêu cầu. Nếu chạy Testcontainers, cần Docker-compatible runtime trong CI; nếu job bắt buộc, không skip âm thầm.

JaCoCo LINE/BRANCH là tín hiệu code paths được thực thi nhưng **không** đánh giá chất lượng assertions. Một `assertDoesNotThrow` có thể xanh trong khi logic trả giá sai; test đúng phải assert exact totalCents, HTTP status/body và final DB state.

Nếu dùng mutation testing (PIT), mutant thay `quantity > 10` thành `quantity >= 10` nên bị unit test qty10 bắt. Nhưng mutation score cũng có equivalent mutants và không thay thế compliance/contract tests.

CI nên tách jobs: fast pure/Mockito/MVC/JDBC, real HTTP integration, optional real DB container, contract/security/performance theo rủi ro. Với failures, upload logs/reports bằng CI “always” nhưng **không** nuốt exit code với `|| true`.

## 33. Những lỗi phổ biến

1. Dùng unit test policy để tuyên bố API HTTP đã được xác nhận.
2. Chỉ dựa Mockito stub để tuyên bố database constraint pass.
3. Đánh dấu MockMvc là HTTP real socket test.
4. Xem H2 là bằng chứng PostgreSQL JSONB/locking/transactions.
5. Đánh dấu PASS khi container test không chạy vì Docker unavailable.
6. Test `@Transactional` bằng `new Service()` mà không qua Spring proxy.
7. Tưởng test transaction rollback trên thread HTTP server.
8. Dùng `assertTimeoutPreemptively` gây DB work ngoài ThreadLocal transaction.
9. Chỉ assert 201 mà không assert Location/JSON/DB state.
10. Chỉ test happy path, bỏ negative/null/boundaries.
11. Expected được tính từ method đang test, không có oracle độc lập.
12. Test được định nghĩa nhưng không được JUnit runner discovery.
13. Coverage cao nhưng test không có assertions.
14. Không có provider verification, chỉ dùng fake response của consumer.
15. Chạy concurrency test nhưng không chờ tất cả workers và assert final state.
16. Gọi @WithMockUser test là bằng chứng JWT signature integration.
17. Không kiểm tra 401/403/no side effects khi auth requirement trọng yếu.
18. Thay đổi global System properties/Locale/TimeZone làm CI flaky.
19. Spring singleton mutable state leak qua TestContext cache.
20. Phối hợp full context với mọi unit test khiến quá chậm, khó chẩn đoán.
21. Không cleanup HTTP committed rows hoặc executors sau test.
22. Không ghi hạn chế của evidence khi báo cáo QA.
23. Một Docker/Testcontainers test dùng image không được pin/kiểm soát.
24. Upload test reports/trace logs chứa PII/secrets công khai.
25. Dùng performance benchmark trên laptop để cam kết production SLO.

## 34. Checklist hoàn tất ma trận

**Requirement:** Có ID và acceptance criterion đo được? Có risk/owner/priority? Với một điều kiện có biên, có cases đúng biên và ngoài biên? Có negative failure/side-effect requirement?

**Test design:** Đã chọn ranh giới test đủ chứng minh, không over-test full context? Có tách unit/mock/MVC/JDBC/HTTP/container/contract/security/perf? Khi test dùng mock, có ghi phần gì bị thay giả không?

**Evidence:** Có assertions exact values/status/body/exception? Có verify interactions/noInteractions? Có SQL query sau commit để chứng minh persistence? Môi trường/fixture/version và test execution result có artifact? Có tách discovered methods với executed methods?

**Limitations:** H2 vs PostgreSQL có được ghi? MockMvc vs TCP có được phân biệt? TestThread vs serverThread transaction? Contract mock vs provider real? Security fixture vs token verification? Load test topology vs production?

**CI:** Required jobs có chạy, không skip? Có Docker runtime cho Testcontainers nếu bắt buộc? Có publish JUnit XML/report, coverage và logs đúng quyền? Có ghi PARTIAL/BLOCKED/NOT_IMPLEMENTED với owner thay vì gán PASS? Có xem lại gaps khi yêu cầu thay đổi?

**Kết luận:** **Ma trận yêu cầu – bằng chứng – giới hạn** là cách chuyển “nhiều test” thành “có căn cứ tin vào hành vi quan trọng”. Một yêu cầu có thể cần nhiều lớp evidence; một test có thể chứng minh tốt một boundary và hoàn toàn không chứng minh boundary khác. Hãy chọn test theo rủi ro, viết assertions độc lập, đọc artifacts thật và chủ động ghi **điều chưa được kiểm chứng**. Đó là nền tảng để Spring Boot testing phục vụ quyết định phát hành chứ không chỉ tạo số test xanh.

## 35. Tài liệu tham khảo chính thức

- [Spring Boot 3.5 – Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html): @SpringBootTest, MockMvc, RANDOM_PORT, slices, transactional caveats.
- [Spring Boot 3.5 – Test Slices](https://docs.spring.io/spring-boot/3.5/appendix/test-auto-configuration/slices.html): JdbcTest/DataJdbcTest/DataJpaTest/JsonTest/RestClientTest.
- [Spring Boot 3.5 – Testcontainers](https://docs.spring.io/spring-boot/3.5/reference/testing/testcontainers.html): @ServiceConnection, @Container, Docker lifecycle.
- [Spring Framework – Test-managed Transactions](https://docs.spring.io/spring-framework/reference/6.2/testing/testcontext-framework/tx.html): ThreadLocal rollback và preemptive timeout.
- [Spring Framework – MockitoBean](https://docs.spring.io/spring-framework/reference/testing/annotations/integration-spring/annotation-mockitobean.html): bean override và mocks.
- [Spring Framework – MockMvc](https://docs.spring.io/spring-framework/reference/testing/mockmvc.html): MVC contract without real server.
- [Spring Framework – TestContext Caching](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/ctx-management/caching.html): context lifecycle và shared state.
- [JUnit Jupiter 5 User Guide](https://docs.junit.org/5.12.2/user-guide/): tests/assertions/extensions.
- [Mockito](https://site.mockito.org/): verification và mock lifecycle.
- [Testcontainers for Java](https://java.testcontainers.org/): real DB/broker integration.
- [JaCoCo Counters](https://www.jacoco.org/jacoco/trunk/doc/counters.html): line/branch limitations.
