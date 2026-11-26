# Bổ sung kiểm thử tích hợp, kiểm thử tải và hồ sơ hiệu năng cho đồ án Neo4j

## Mục tiêu học tập

Kết thúc bài thuộc chương **Đồ án thực hành**, bạn có thể:

1. Chuyển yêu cầu nghiệp vụ thành **test case và quality gate đo được**, phân biệt tính đúng với tốc độ.
2. Kiểm thử **Neo4j thực** thay vì chỉ mock repository: node, relationship, constraint, transaction rollback, tính idempotent, quyền truy cập và dữ liệu lỗi.
3. Dùng **JUnit 5 + Testcontainers** để chạy integration test với Java Driver/Spring Data Neo4j trên database tách biệt, có seed và cleanup xác định.
4. Thiết kế kịch bản **baseline, load, stress, spike, soak** có phân phối dữ liệu và tỷ lệ truy vấn gần với hệ thống thật.
5. Dùng **k6** gửi request API có kiểm tra nội dung, lập ngưỡng p95/p99, tỷ lệ lỗi, thông lượng và số iteration không phát được.
6. Giải thích kết quả bằng **Cypher EXPLAIN/PROFILE**, DB Hits, Rows, index, fan-out, heap, page cache, I/O và connection pool.
7. Viết **hồ sơ hiệu năng tái lập được**: môi trường, dataset, phiên bản, cấu hình, workload, kết quả, so sánh trước–sau, giới hạn và quyết định go/no-go.
8. Đặt kiểm thử trong CI phù hợp, bảo vệ dữ liệu và tránh chạy thử tải gây rủi ro lên production.

Module **DATABASE_ENGINE_GRAPH_NEO4J** ứng dụng Neo4j để mô hình hóa **property graph** và truy vấn liên kết/đường đi bằng Cypher, kết hợp constraint, index, dữ liệu nhập, Java Driver và Spring Data Neo4j. Bài này tổng hợp các năng lực đó thành **giai đoạn nghiệm thu** của một đồ án đã có API và mô hình graph: không chỉ chứng minh “demo chạy” mà chứng minh **đúng chức năng, ổn định ở tải mục tiêu, biết nguyên nhân nghẽn và có bằng chứng kiểm chứng**.

> **Phạm vi và tính tương thích:** Mã Java minh họa API của Spring Boot 3.x, JUnit 5, Neo4j Java Driver hiện đại và Testcontainers tương thích. Tên module/package của Testcontainers và cách đăng ký `@ServiceConnection` có thể thay đổi giữa các dòng lớn. Chọn một BOM nhất quán, ghim tag Neo4j, kiểm tra tài liệu cho các phiên bản thật. Bài **không yêu cầu chạy thử tải trên production**. Các con số và kết quả nêu dưới đây là dữ liệu học tập giả định, không phải cam kết mặc định của Neo4j.

## 1. Đồ án mẫu và các đầu ra phải nộp

Giả sử ứng dụng **Graph Commerce**:

- Khách hàng `Customer` đặt các `Order`.
- Đơn hàng chứa các `Product` thông qua relationship `CONTAINS` có thuộc tính `quantity`.
- API Java/Spring cung cấp tạo đơn, liệt kê đơn theo khách hàng, xem chi tiết sản phẩm của đơn và truy vấn sản phẩm mua chung.
- Neo4j giữ đồ thị theo business ID; API dùng Java Driver hoặc Spring Data Neo4j. Nếu PostgreSQL là nguồn đơn hàng có thẩm quyền và Neo4j chỉ là read model, các bài test phải bổ sung **eventual consistency/CDC**, không nhầm thời điểm source commit với thời điểm graph nhìn thấy dữ liệu.

~~~mermaid
flowchart LR
    C["Customer<br/>customerId"] -->|PLACED| O["Order<br/>orderId, status, totalCents"]
    O -->|"CONTAINS {quantity}"| P["Product<br/>sku, name, category"]
    API["Spring Boot API"] -->|Neo4j Driver / SDN| G[("Neo4j")]
    G --> C
    G --> O
    G --> P
    TEST["JUnit + Testcontainers"] -.->|Integration test| G
    LOAD["k6"] -->|HTTP workload| API
    MET["Metrics + profiling"] -.-> G
    MET -.-> API
~~~

**Đầu ra nghiệm thu đề xuất:**

| Artifact | Nội dung bắt buộc | Bằng chứng |
| --- | --- | --- |
| **Test matrix** | Functional case, invariant, failure mode, nguồn dữ liệu | Bảng case ID → expected result |
| **Integration suite** | Kết nối Neo4j thật, seed, test, teardown, rollback/constraint | Log pass/fail có version và commit |
| **Load scripts** | Workload profile, arrival rate, thời lượng, auth/test data, thresholds | Script được version hóa, command thực thi |
| **Raw performance results** | p50/p95/p99, error, throughput, dropped iterations, metrics tài nguyên | File kết quả/timestamps, không chỉ ảnh chụp |
| **Cypher plans** | `EXPLAIN`/`PROFILE` cho truy vấn đại diện | Operator, Rows, DB Hits, index sử dụng |
| **Performance dossier** | Baseline, môi trường, so sánh, kết luận, giới hạn | Bảng đo + go/no-go + đề xuất |
| **Recovery/verification notes** | Cách làm sạch dataset, khôi phục, kiểm tra regression | Runbook test và checklist sau sửa |

**Tiêu chí tổng quát:** Đồ án chưa đạt chỉ vì container khởi động hoặc một API trả HTTP 200. Phải có **assertion về graph và dữ liệu**, ngưỡng hiệu năng, kết quả thử dưới tải và giải thích nguyên nhân khi một ngưỡng không đạt.

## 2. Biến yêu cầu thành hợp đồng kiểm thử

Trước khi viết test, định nghĩa domain invariants:

1. `Customer.customerId`, `Order.orderId` và `Product.sku` là **business key** ổn định và duy nhất.
2. Mỗi đơn có **đúng một khách hàng đặt** trong mô hình bài tập; `PLACED` đi từ `Customer` tới `Order`.
3. Relationship `CONTAINS` nối đúng `Order` tới `Product`; `quantity` phải là số nguyên dương.
4. Tạo cùng một đơn với **cùng ID và payload** có thể chạy lại an toàn; payload mâu thuẫn phải bị từ chối hoặc xử lý theo chính sách rõ ràng.
5. Mỗi thao tác tạo đơn là một **transaction**, không có trạng thái nửa chừng nếu lỗi giữa các bước.
6. Người dùng chỉ đọc/ghi dữ liệu thuộc **tenant** được cấp quyền nếu hệ thống có multi-tenancy.
7. API phân trang/giới hạn kết quả phải có **thứ tự ổn định** để không nhân đôi hoặc bỏ sót khi đọc trang tiếp theo.

### 2.1. Bảng test case minh họa

| ID | Phép thử | Expected result | Cấp kiểm thử |
| --- | --- | --- | --- |
| IT-01 | Tạo Customer và Order, tạo `PLACED` | 1 Customer, 1 Order, 1 cạnh đúng hướng | Integration |
| IT-02 | Gửi lại cùng `orderId` và payload | Không nhân đôi node/cạnh | Integration |
| IT-03 | Cùng `orderId` với payload khác | Trả xung đột, không ghi đè âm thầm | Integration/API |
| IT-04 | Cố tạo hai Order trùng business key | Constraint chặn transaction thứ hai | Integration |
| IT-05 | Exception giữa nhiều câu Cypher cùng transaction | Toàn transaction rollback | Integration |
| IT-06 | Order không có Product hoặc thiếu property | Trả kết quả/validation theo hợp đồng | Integration |
| IT-07 | Relationship `CONTAINS.quantity <= 0` | API từ chối input; dữ liệu không đổi | API/Service |
| IT-08 | Người dùng tenant A truy vấn tenant B | Bị từ chối hoặc không có dữ liệu | Security integration |
| IT-09 | Truy vấn Customer có 0/1/10.000 Order | Kết quả đúng, không over-fetch graph | Integration + perf |
| LT-01 | 80 READ + 20 WRITE trong tải tổng 100 req/s | Đạt latency/error SLO | Load |
| LT-02 | Tải tăng tới giới hạn | Xác định điểm gãy và khả năng phục hồi | Stress |
| LT-03 | Giữ tải 60 phút | Không memory leak, pool leak hoặc backlog tăng vô hạn | Soak |

Các số lượng và tỷ lệ chỉ là **ví dụ xác lập hợp đồng**. Test performance phải phản ánh tải dự kiến của đồ án, không chọn RPS tùy ý để có đồ thị đẹp.

### 2.2. Tách correctness và non-functional requirements

- **Correctness gate:** API trả đúng business ID/status/quan hệ/hướng, tính duy nhất, rollback và quyền truy cập.
- **Reliability gate:** không sinh duplicate khi retry, xử lý timeout, báo lỗi rõ và phục hồi sau mất kết nối.
- **Performance gate:** p95/p99, throughput, error rate, tài nguyên, độ mới projection.
- **Operational gate:** có log, tracing, metrics, backup/cleanup và cách tái lập benchmark.

Nếu p95 rất thấp nhưng kết quả thiếu 25% relationship, đó là **FAIL**, không phải tối ưu thành công. Nếu dữ liệu đúng nhưng p99 vượt SLA, cũng **chưa được nghiệm thu**.

## 3. Chiến lược kiểm thử: unit, integration, API và load

Một bộ test cân đối không dùng duy nhất một mức:

| Mức | Môi trường | Nên kiểm tra | Không nên dùng để kết luận |
| --- | --- | --- | --- |
| **Unit** | Mock parser/service/validator | Validation, xây DTO, phân quyền nghiệp vụ độc lập | Neo4j transaction thật, Cypher syntax/index |
| **Repository/Driver integration** | Neo4j Testcontainers thật | Constraint, MERGE, relationship, mapping, commit/rollback | HTTP/auth/network thật của toàn hệ |
| **API integration** | Spring app + Neo4j container | JSON, status, auth, repository/service, error mapping | Khả năng chịu 100 req/s |
| **End-to-end** | Các service và hệ phụ thuộc cô lập | Workflow thực, CDC/outbox khi có, eventual consistency | Mọi failure mode của production |
| **Performance/load** | Môi trường staging giống production ở các biến quan trọng | Throughput, p95/p99, bottleneck, error rate dưới tải | Tính đúng transaction ở mọi đường biên nếu không có assertion riêng |
| **Recovery/failure** | Lab/cluster thử nghiệm | Restart, retry, backlog và phục hồi | Khả năng chịu lỗi thật khi topology khác |

**Unit test với mock Neo4j repository không chứng minh câu Cypher có thể chạy**. Integration test bằng container thật kiểm tra parser/planner, index và transaction. Ngược lại, integration test một request không chứng minh service chịu được tải liên tục.

### 3.1. Môi trường tách biệt và dữ liệu có thể tái lập

- Container database **chỉ dành cho test**, không kết nối tới production.
- Ghim tag image và version theo target deploy, có thể dùng digest khi cần tái lập chính xác.
- Seed theo **cùng random seed/dataset version**; không dựa vào dữ liệu sống đang thay đổi.
- Trước mỗi test, cleanup chỉ trong test database/container đã được xác minh là dùng riêng.
- Không cho test chạy song song trên cùng database nếu cùng xóa toàn bộ graph trong `@BeforeEach`.
- Tránh dùng test read-only trên production để “đỡ mất thời gian dựng môi trường”; hiệu năng và bảo mật sẽ không kiểm soát được.

Đối với Neo4j multi-database/cluster, integration suite căn bản bằng container đơn **chưa kiểm thử failover/quorum**; bổ sung môi trường cluster riêng nếu yêu cầu có HA.

## 4. Mô hình graph, schema và fixture

Đồ án trước hết cần **schema tối thiểu và dữ liệu có quy luật** để test không thất bại ngẫu nhiên.

~~~cypher
CREATE CONSTRAINT customer_id_unique IF NOT EXISTS
FOR (c:Customer)
REQUIRE c.customerId IS UNIQUE;

CREATE CONSTRAINT order_id_unique IF NOT EXISTS
FOR (o:Order)
REQUIRE o.orderId IS UNIQUE;

CREATE CONSTRAINT product_sku_unique IF NOT EXISTS
FOR (p:Product)
REQUIRE p.sku IS UNIQUE;

CREATE RANGE INDEX order_created_at IF NOT EXISTS
FOR (o:Order) ON (o.createdAt);
~~~

Ví dụ fixture nhỏ:

~~~cypher
MERGE (c:Customer {customerId: 'C-101'})
SET c.displayName = 'Lan';

MERGE (o:Order {orderId: 'O-901'})
SET o.status = 'CREATED',
    o.totalCents = 150000,
    o.createdAt = datetime('2026-11-01T10:00:00Z');

MERGE (p:Product {sku: 'P-BOOK-1'})
SET p.name = 'Graph Book', p.category = 'Books';

MATCH (c:Customer {customerId: 'C-101'})
MATCH (o:Order {orderId: 'O-901'})
MATCH (p:Product {sku: 'P-BOOK-1'})
MERGE (c)-[:PLACED]->(o)
MERGE (o)-[r:CONTAINS]->(p)
SET r.quantity = 2;
~~~

### 4.1. Cần fixture cho các biên và độ lệch dữ liệu

| Loại fixture | Ví dụ | Lỗi dễ lộ |
| --- | --- | --- |
| Không có cạnh | Customer mới, chưa có Order | `MATCH` thay vì `OPTIONAL MATCH` làm biến mất Customer |
| Một cạnh | 1 Customer → 1 Order | Sai hướng relationship hoặc mapping |
| Bậc cao | 1 Customer → 10.000 Order | Fan-out, sort, over-fetch, độ trễ p99 |
| Dữ liệu phân cấp | Order → 20 Product | N+1, duplicate rows, `collect` phình |
| Dữ liệu null/thiếu | `displayName` null, thiếu `createdAt` | Java DTO mapping, sort, validation |
| Giá trị Unicode | Tên có dấu và emoji | Encoding/search/analyzer |
| Business key xung đột | 2 request cùng `orderId` | Constraint, idempotency, retry |
| Tenant khác | ID trùng giữa tenant | Cross-tenant graph leakage |

Không cần tạo 10.000 order trong một transaction đơn khổng lồ. Có thể seed bằng các batch có kích thước giới hạn và `UNWIND`:

~~~cypher
UNWIND $orders AS item
MERGE (c:Customer {customerId: item.customerId})
MERGE (o:Order {orderId: item.orderId})
SET o.status = item.status,
    o.totalCents = item.totalCents,
    o.createdAt = datetime(item.createdAt)
MERGE (c)-[:PLACED]->(o);
~~~

Ở test integration, `$orders` là danh sách map được tạo từ **test seed cố định**. Nếu chạy lại cùng dữ liệu, logic `MERGE` nên không tạo trùng; nhưng code seed không được ghi đè biến trạng thái runtime ngoài ý muốn. Với performance dataset có version/ID riêng, cần chạy kiểm tra số record **trước khi bắt đầu đo**.

### 4.2. Neo4j constraints và chỉ mục phải thực sự sẵn sàng

~~~cypher
SHOW INDEXES
YIELD name, type, state, populationPercent, labelsOrTypes, properties
RETURN name, type, state, populationPercent, labelsOrTypes, properties
ORDER BY name;
~~~

Nếu index quan trọng còn `POPULATING` hoặc `FAILED`, kết quả benchmark có thể phản ánh **giai đoạn xây index** chứ không phải hiệu năng ổn định. Ghi thời điểm population hoàn tất, sau đó đo cold-cache/warm-cache riêng.

## 5. Testcontainers và JUnit 5: chạy Neo4j thật

### 5.1. Chuẩn bị dependency

Ví dụ Gradle (Groovy DSL), giả định plugin Spring Boot và dependency management hoặc BOM đã khóa các phiên bản tương thích:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-neo4j'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.testcontainers:junit-jupiter'
    testImplementation 'org.testcontainers:neo4j'
}

tasks.withType(Test).configureEach {
    useJUnitPlatform()
}
~~~

**Lưu ý version:** Tên artifact/package trên phù hợp với dòng Testcontainers 1.x được dùng rộng rãi cùng Spring Boot 3.x; các dòng Testcontainers 2.x có thể dùng module/package khác. Dùng BOM của phiên bản mà dự án đã chọn; đừng ghép ngẫu nhiên JAR 1.x và 2.x. Testcontainers cần một **Docker runtime có thể sử dụng** trong máy dev/CI; nếu pipeline không có Docker thì test không tự chạy được.

Nếu dùng Spring Boot 3.x và `spring-boot-testcontainers`, `@ServiceConnection` có thể tự cung cấp `Neo4jConnectionDetails`. Ví dụ bên dưới dùng `@DynamicPropertySource` để hiển thị rõ từng biến kết nối và tránh phụ thuộc lớp cấu hình đặc biệt.

### 5.2. Một service nhỏ làm đối tượng kiểm thử

Ví dụ Java giả định project có package phù hợp và Spring có quét bean:

~~~java
import java.util.Map;
import org.neo4j.driver.Driver;
import org.neo4j.driver.Session;
import org.neo4j.driver.SessionConfig;
import org.springframework.stereotype.Service;

@Service
public final class GraphOrderService {
    private final Driver driver;

    public GraphOrderService(Driver driver) {
        this.driver = driver;
    }

    public void createOrder(
            String orderId, String customerId, long totalCents) {
        if (orderId == null || orderId.isBlank()
                || customerId == null || customerId.isBlank()
                || totalCents < 0) {
            throw new IllegalArgumentException("Invalid order");
        }
        var params = Map.<String, Object>of(
                "orderId", orderId,
                "customerId", customerId,
                "totalCents", totalCents);

        try (Session session = driver.session(
                SessionConfig.forDatabase("neo4j"))) {
            session.executeWriteWithoutResult(tx -> {
                var rows = tx.run("""
                    MERGE (c:Customer {customerId: $customerId})
                    MERGE (o:Order {orderId: $orderId})
                    ON CREATE SET
                      o.customerId = $customerId,
                      o.totalCents = $totalCents,
                      o.status = 'CREATED'
                    WITH c, o
                    WHERE o.customerId = $customerId
                      AND o.totalCents = $totalCents
                    MERGE (c)-[:PLACED]->(o)
                    RETURN o.orderId AS orderId
                    """, params).list();
                if (rows.size() != 1) {
                    throw new IllegalArgumentException(
                            "Order ID conflicts with existing payload");
                }
            });
        }
    }

    public long countOrders(String orderId) {
        try (Session session = driver.session(
                SessionConfig.forDatabase("neo4j"))) {
            return session.executeRead(tx -> tx.run("""
                MATCH (o:Order {orderId: $id})
                RETURN count(o) AS n
                """, Map.of("id", orderId))
                .single().get("n").asLong());
        }
    }

    public long countPlaced(String orderId) {
        try (Session session = driver.session(
                SessionConfig.forDatabase("neo4j"))) {
            return session.executeRead(tx -> tx.run("""
                MATCH (:Customer)-[:PLACED]->(o:Order {orderId: $id})
                RETURN count(*) AS n
                """, Map.of("id", orderId))
                .single().get("n").asLong());
        }
    }
}
~~~

Ý nghĩa của ví dụ:

- Dùng **Driver dùng chung** do Spring quản lý; tạo `Session` riêng cho mỗi operation.
- `executeWriteWithoutResult` thực hiện toàn bộ Cypher trong **một managed transaction**, rollback nếu có exception.
- `MERGE` theo business ID kết hợp **uniqueness constraint**; không dùng `elementId` làm ID liên hệ thống.
- Một `orderId` được gửi lại với payload không đổi không sinh thêm Order/cạnh trong mô hình đơn giản này.
- Payload mâu thuẫn trả lỗi và transaction rollback; production cần ánh xạ lỗi này sang HTTP `409 Conflict` và quy định trạng thái Order update rõ ràng.

**Phạm vi cần nâng cấp khi làm hệ thống thật:** Đoạn code chỉ minh họa một đơn có một chủ sở hữu không đổi, không xử lý order items, chuyển ownership, xóa, trạng thái đa bước, đa tenant hay ghi song song mức cao. Không dùng ví dụ làm đặc tả nghiệp vụ hoàn chỉnh. `MERGE` và constraint chống ID trùng; khi nhiều writer đồng thời tranh cùng một aggregate vẫn phải thiết kế retry/ordering và kiểm thử concurrent.

### 5.3. Integration test có container riêng

~~~java
import static org.junit.jupiter.api.Assertions.*;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.neo4j.driver.Driver;
import org.neo4j.driver.Session;
import org.neo4j.driver.SessionConfig;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.testcontainers.containers.Neo4jContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

@Testcontainers
@SpringBootTest
class GraphOrderIntegrationTest {
    @Container
    static Neo4jContainer<?> neo4j =
            new Neo4jContainer<>("neo4j:5.26")
                    .withAdminPassword("test-only-password");

    @DynamicPropertySource
    static void databaseProperties(DynamicPropertyRegistry registry) {
        registry.add("spring.neo4j.uri", neo4j::getBoltUrl);
        registry.add("spring.neo4j.authentication.username", () -> "neo4j");
        registry.add("spring.neo4j.authentication.password",
                () -> "test-only-password");
    }

    @Autowired Driver driver;
    @Autowired GraphOrderService service;

    @BeforeEach
    void resetGraphAndSchema() {
        // CHỈ trên container riêng của test: không bao giờ dùng ở prod!
        try (Session session = driver.session(
                SessionConfig.forDatabase("neo4j"))) {
            session.run("MATCH (n) DETACH DELETE n").consume();
            session.run("""
                CREATE CONSTRAINT customer_id_unique IF NOT EXISTS
                FOR (c:Customer) REQUIRE c.customerId IS UNIQUE
                """).consume();
            session.run("""
                CREATE CONSTRAINT order_id_unique IF NOT EXISTS
                FOR (o:Order) REQUIRE o.orderId IS UNIQUE
                """).consume();
        }
    }

    @Test
    void createAndReplaySameOrderIsIdempotent() {
        service.createOrder("O-T1", "C-T1", 125_000L);
        service.createOrder("O-T1", "C-T1", 125_000L);

        assertEquals(1L, service.countOrders("O-T1"));
        assertEquals(1L, service.countPlaced("O-T1"));
    }

    @Test
    void conflictingPayloadDoesNotOverwriteExistingOrder() {
        service.createOrder("O-T2", "C-T2", 100_000L);

        assertThrows(IllegalArgumentException.class,
                () -> service.createOrder("O-T2", "C-T2", 200_000L));
        assertEquals(1L, service.countOrders("O-T2"));
        assertEquals(1L, service.countPlaced("O-T2"));
    }

    @Test
    void exceptionRollsBackEntireNeo4jTransaction() {
        try (Session session = driver.session(
                SessionConfig.forDatabase("neo4j"))) {
            assertThrows(IllegalStateException.class,
                    () -> session.executeWriteWithoutResult(tx -> {
                        tx.run("""
                            CREATE (:Order {orderId: 'O-ROLLBACK'})
                            """).consume();
                        throw new IllegalStateException("forced rollback");
                    }));
        }
        assertEquals(0L, service.countOrders("O-ROLLBACK"));
    }
}
~~~

Các test dùng database **`neo4j` bên trong container riêng**. `MATCH (n) DETACH DELETE n` cố ý xóa toàn graph **chỉ trong môi trường test**; tuyệt đối không copy sang database dùng chung. Test class ví dụ **không được chạy song song với test class khác cùng thao tác cleanup**. Với suite lớn, sử dụng database riêng theo suite/container và fixture/rollback có kiểm soát.

### 5.4. Những assertion còn cần bổ sung

- **Constraint thật:** thử `CREATE` thêm `Order` có cùng `orderId`, kỳ vọng Neo4j trả lỗi constraint, transaction sau lỗi rollback.
- **Relationship direction:** `(c)-[:PLACED]->(o)` tồn tại, chiều ngược không bị tạo nhầm.
- **Order–Product:** `quantity > 0` được validate trước khi ghi, relationship không trùng theo hợp đồng.
- **Read sorting/pagination:** cùng một tập dữ liệu trả thứ tự ổn định; `LIMIT` không bỏ qua edge quan trọng.
- **Concurrent requests:** hai thread cùng order ID không tạo duplicate; ghi kết quả/exception để phân biệt conflict và transient failure.
- **Security:** không cho gọi API của tenant khác; không lấy tenant ID từ payload chưa xác thực.
- **Error mapping:** `ClientException`/constraint error chuyển thành mã HTTP phù hợp, không trả raw Cypher và secrets cho client.

Một test kiểu “không ném exception” chưa đủ. Hãy **assert cả trạng thái graph cuối cùng** sau request, kể cả trường hợp rollback và retry.

## 6. Spring Data Neo4j: test mapping và vòng đời transaction

Với Spring Data Neo4j (SDN), kiểm tra **repository/Neo4jClient thực** và cách ánh xạ entity graph:

~~~java
import org.springframework.data.neo4j.core.schema.Id;
import org.springframework.data.neo4j.core.schema.Node;
import org.springframework.data.neo4j.core.schema.Relationship;
import java.util.HashSet;
import java.util.Set;

@Node("Customer")
public class Customer {
    @Id
    private String customerId;
    private String displayName;

    @Relationship(type = "PLACED", direction =
            Relationship.Direction.OUTGOING)
    private Set<Order> orders = new HashSet<>();

    // Constructor/getter/setter theo yêu cầu SDN đang dùng.
}

@Node("Order")
public class Order {
    @Id
    private String orderId;
    private String status;
    // Constructor/getter/setter theo yêu cầu SDN đang dùng.
}
~~~

**Hai class là fragment về mapping**, chưa phải mã Java hoàn chỉnh để compile nếu chưa bổ sung constructor/getters/setters. Có thể dùng Java record/DTO cho màn hình đọc khi không cần quản lý toàn bộ entity graph.

### 6.1. `@DataNeo4jTest` và `@SpringBootTest`

| Cách khởi tạo | Phù hợp | Không bao gồm mặc định |
| --- | --- | --- |
| `@DataNeo4jTest` | Slice test repository, mapping, converter, `Neo4jClient` | Tất cả controller/security/service ngoài slice |
| `@SpringBootTest` | Full Spring context, service, transaction manager và integration với driver | HTTP socket thật trừ khi chỉ định web environment |
| `@SpringBootTest(webEnvironment=RANDOM_PORT)` | HTTP API E2E trong Spring app | Bên ngoài như Kafka/PostgreSQL nếu chưa dựng |
| Direct Java Driver + Testcontainers | Cypher, constraint, transaction, read/write | SDN mapping hoặc Controller nếu không gọi |

Nếu dùng `@ServiceConnection` trên Neo4jContainer, bổ sung dependency `spring-boot-testcontainers` phù hợp Spring Boot và theo hướng dẫn của version. Với `@DynamicPropertySource`, đăng ký URI/username/password như ví dụ ở phần 5.

### 6.2. Transaction rollback trong test có thể gây hiểu nhầm

Một số test framework tạo transaction bao quanh method và rollback sau khi test kết thúc. Nhưng:

- Nếu service dùng **một transaction manager khác**, hoặc ứng dụng gọi một service trên connection/process khác, không mặc định cùng transaction với method test.
- HTTP test chạy với **server ở thread khác** thường commit transaction độc lập; `@Transactional` đặt ở test method không thể tự rollback mọi thứ server đã commit.
- Managed transaction của **Java Driver** được tạo và commit riêng, không tự nằm trong transaction JUnit/Spring Test.
- TestContainers sạch sau khi dừng **không thay thế** kiểm tra rollback ngay trong test case.

Hãy **query lại trạng thái graph** sau khi chủ động gây lỗi; khi cần isolation, reset dữ liệu trong container test hoặc dùng fixture/key duy nhất. Không chỉ đánh giá test PASS vì framework “sẽ rollback”.

### 6.3. Kiểm thử over-fetching và DTO projection

Một endpoint chỉ cần `orderId`, `status`, `totalCents` nhưng repository có thể tải cả `Customer.orders` và `Order.items`. Nên có test:

- Với Customer bậc cao, API trả **giới hạn số Order** đã cam kết, không trả tất cả.
- DTO chỉ có field hợp đồng; không lộ thuộc tính nhạy cảm.
- Truy vấn dùng `ORDER BY` ổn định và `LIMIT`/cursor đúng.
- Quan sát số hàng/bytes trên wire và `DB Hits`, tránh **N+1** khi truy cập từng Order.

Không dùng “serialization JSON vẫn nhanh trong test nhỏ” để kết luận query không over-fetch. Dùng dataset có **node bậc cao** và đo thực tế dưới tải.

## 7. API integration: đi qua HTTP, security và dữ liệu graph

Định nghĩa API mẫu (chỉ là **hợp đồng minh họa**):

| HTTP | Endpoint | Hành vi |
| --- | --- | --- |
| `POST` | `/v1/orders` | Nhận `orderId, customerId, totalCents`; tạo đơn; trùng payload xử lý idempotent |
| `GET` | `/v1/customers/{customerId}/orders?limit=20` | Liệt kê Order theo thứ tự có định nghĩa |
| `GET` | `/v1/orders/{orderId}/products` | Trả danh sách Product và quantity |
| `GET` | `/actuator/health/readiness` | Kiểm tra dependency bắt buộc theo cấu hình |

Ví dụ JSON hợp đồng:

~~~json
{
  "customerId": "C-101",
  "orders": [
    {
      "orderId": "O-901",
      "status": "CREATED",
      "totalCents": 150000
    }
  ],
  "hasMore": false
}
~~~

Các API thực phải quyết định rõ:

- `201 Created` khi tạo mới; `200 OK` hoặc phản hồi idempotent khác cho replay; `409 Conflict` nếu order ID trùng nhưng payload mâu thuẫn.
- `400 Bad Request` với input không hợp lệ, `403 Forbidden` với tenant không được phép, `404 Not Found` với resource không tồn tại theo hợp đồng.
- Cách tính `hasMore`, order field và cursor để tránh trùng/bỏ sót khi có ghi đồng thời.
- Trả mã lỗi có correlation ID, **không để rò rỉ raw Cypher, stack trace hay secret**.

### 7.1. Test HTTP không dừng ở status code

Một test API quan trọng cần:

1. Gửi HTTP request có auth role hợp lệ.
2. Assert status, body schema, business fields, pagination và headers liên quan.
3. Truy vấn lại Neo4j bằng **business key** để kiểm tra hậu quả transaction.
4. Gửi request replay hoặc request lỗi; kiểm tra không tạo duplicate, không mất cạnh.
5. Với multi-tenant, test trường hợp ID ở tenant khác **không thể truy cập**.

Nếu production dùng Kafka/CDC để đưa Order vào Neo4j, test phải **đợi có giới hạn và kiểm tra version/watermark**, không giả định graph được cập nhật đồng thời với database nguồn. Không dùng `Thread.sleep(3000)` cố định làm bằng chứng nhất quán.

## 8. Thiết kế workload: đo hành vi thật, không chỉ bắn HTTP liên tục

Một kịch bản tải phải mô tả **arrival, phân phối request, dataset và trạng thái hệ thống**.

### 8.1. Phân phối hành vi ví dụ

| Operation | Tỷ lệ mục tiêu | Dữ liệu | Độ phức tạp |
| --- | ---: | --- | --- |
| Lookup Customer | 40% | ID hiện có, 5% không tồn tại | Index seek |
| List Orders | 30% | 10% Customer bậc cao | Expand + sort + pagination |
| Order details/products | 10% | 1–20 Product/Order | 2-hop graph |
| Create Order | 15% | Business ID duy nhất mỗi request | `MERGE`/constraint + transaction |
| Idempotent replay/conflict | 5% | Key có sẵn và payload kiểm soát | Constraint/retry/error path |

Đây là **workload tham khảo**; không nên dùng tất cả ID được lựa chọn đồng đều nếu production có vài Customer chiếm đa số lưu lượng.

### 8.2. Mô hình arrival mở và đóng

| Loại mô hình | Ví dụ công cụ | Ý nghĩa |
| --- | --- | --- |
| **Closed model** | k6 `constant-vus`, `ramping-vus` | Một số VU cố định gửi request sau khi request trước hoàn tất; khi SUT chậm, arrival tự giảm |
| **Open model** | k6 `constant-arrival-rate` | Đặt mục tiêu số iteration bắt đầu/giây độc lập với latency; gần mô hình traffic đến từ ngoài |

**Vấn đề coordinated omission:** Nếu generator đợi response mới gửi request tiếp theo, lúc SUT quá chậm, số request bắt đầu giảm. Kết quả có thể che phần độ trễ và lỗi dưới tải mục tiêu. Arrival-rate giúp quan sát rõ hơn **mức tải dự định**, nhưng phải theo dõi `dropped_iterations`: nếu thiếu VU hoặc SUT chậm quá mức, generator **không tạo được đủ traffic**.

### 8.3. Tách workload đọc và ghi

Đối với Neo4j, WRITE có:

- Transaction log và index maintenance.
- Locking/constraint checks theo business key.
- I/O disk và tác động tới READ khi CPU/cache bị tranh chấp.

READ có:

- Index seeks, expand relationship, sort/aggregate và serialization.
- Page cache/cold-cache/warm-cache, số edge đi qua và fan-out.

Vì vậy, phải đo **READ only**, **WRITE only** và **mixed READ/WRITE**, không lấy một “tổng RPS” để kết luận tất cả tốt.

## 9. Chạy tải có kiểm soát: chuẩn bị môi trường và dữ liệu

Trước khi chạy k6/Gatling/JMeter:

1. Xác định SUT (system under test) là **URL staging chuyên dụng**, có quyền thử tải.
2. Ghi version Neo4j, Java Driver, Spring Boot, Java runtime, CPU/RAM/heap/page cache, disk type, topology và cấu hình connection pool.
3. Seed dataset có **kích thước và độ lệch** đại diện; index trọng yếu đã `ONLINE`.
4. Warm-up đủ thời gian để JVM/JIT, connection pool và cache ổn định; đo cold-cache riêng khi đó là mục tiêu.
5. Generator nằm ở host đủ CPU/network; đo CPU/RAM/network generator để tránh lỗi do **máy tạo tải**.
6. Xác định **run ID**, dải business ID và chính sách cleanup; không reuse dữ liệu ghi giữa các lần đo khi không muốn.
7. Thiết lập guardrail: max RPS, thời gian, abort thresholds, tài nguyên và người có quyền dừng.
8. Ghi timestamp, commit/config Git, loại workload và input parameter distribution.

### 9.1. Trạng thái dataset ảnh hưởng kết quả

Hai thử nghiệm có cùng RPS nhưng một lần có 1.000 Order, lần còn lại có 10 triệu Order **không thể so sánh trực tiếp**. Số node, relationship, index, độ dài chuỗi property, phân bố bậc và hot keys đều ảnh hưởng query planner, cache và lock contention.

Với READ, cần chọn tập ID cố định nhưng đại diện; với WRITE, tạo `orderId` mới theo mỗi iteration để không “benchmark” ngầm một lần `MERGE` replay. Phải đo replay/conflict thành **kịch bản riêng**, vì thao tác đó thường ít công việc hơn tạo mới.

### 9.2. Chấp thuận và bảo mật

- Không gửi PII/mật khẩu thật vào tập test, dashboard hoặc raw result.
- Không bắn traffic từ máy ngoài Internet vào DB Bolt production.
- Không dùng script tạo đơn thanh toán thật hay gửi email/SMS ngoài ý muốn.
- Tách tài khoản load test với account admin; giới hạn tenant/dataset và tốc độ.
- Không dùng tính năng tự nâng VU không giới hạn khiến generator hoặc SUT bị quá tải khó kiểm soát.
- Có **kịch bản dừng khẩn cấp** và xem dung lượng disk/transaction log trước khi test write dài.

## 10. Kịch bản k6: HTTP workload có assertion và threshold

Ví dụ sau giả định API ở phần 7 đã được triển khai trong **staging**, trả `201` cho một Order mới và `200` kèm mảng `orders` cho GET. Đường dẫn, mã response và contract phải điều chỉnh theo ứng dụng thật.

~~~javascript
import http from 'k6/http';
import { check } from 'k6';
import exec from 'k6/execution';

// Đặt mục tiêu 40 READ + 10 WRITE iteration/s trong 5 phút.
// Đây là tốc độ mô phỏng, không phải số request/s được cam kết.
export const options = {
  scenarios: {
    read_orders: {
      executor: 'constant-arrival-rate',
      exec: 'readOrders',
      rate: 40,
      timeUnit: '1s',
      duration: '5m',
      preAllocatedVUs: 50,
      maxVUs: 150,
    },
    create_orders: {
      executor: 'constant-arrival-rate',
      exec: 'createOrder',
      rate: 10,
      timeUnit: '1s',
      duration: '5m',
      preAllocatedVUs: 20,
      maxVUs: 80,
    },
  },
  thresholds: {
    'http_req_failed{operation:readOrders}': ['rate<0.005'],
    'http_req_duration{operation:readOrders}': [
      'p(95)<250', 'p(99)<500'
    ],
    'http_req_failed{operation:createOrder}': ['rate<0.01'],
    'http_req_duration{operation:createOrder}': ['p(95)<600'],
    checks: ['rate>0.99'],
    dropped_iterations: ['count==0'],
  },
};

const baseUrl = __ENV.BASE_URL;
const runId = __ENV.RUN_ID;
const customerId = __ENV.CUSTOMER_ID || 'C-101';

export function setup() {
  if (!baseUrl || !runId) {
    throw new Error('BASE_URL and unique RUN_ID are required');
  }
}

function requestHeaders() {
  const headers = { 'Content-Type': 'application/json' };
  if (__ENV.TEST_TOKEN) {
    headers.Authorization = 'Bearer ' + __ENV.TEST_TOKEN;
  }
  return headers;
}

function isExpectedReadResponse(response) {
  if (response.status !== 200) return false;
  try {
    const body = response.json();
    return body.customerId === customerId
      && Array.isArray(body.orders)
      && body.orders.length <= 20;
  } catch (_error) {
    return false;
  }
}

export function readOrders() {
  const url = baseUrl + '/v1/customers/'
    + encodeURIComponent(customerId) + '/orders?limit=20';
  const response = http.get(url, {
    headers: requestHeaders(),
    tags: { operation: 'readOrders' },
  });
  check(response, {
    'read status=200 and valid page': isExpectedReadResponse,
  });
}

export function createOrder() {
  // iterationInTest là chỉ số iteration của scenario trong test.
  // RUN_ID khác nhau ở mỗi lần chạy để tránh reuse business ID.
  const orderId = 'O-K6-' + runId + '-'
    + exec.scenario.iterationInTest;
  const payload = {
    orderId,
    customerId,
    totalCents: 150000,
  };
  const response = http.post(
    baseUrl + '/v1/orders',
    JSON.stringify(payload),
    {
      headers: requestHeaders(),
      tags: { operation: 'createOrder' },
    }
  );
  check(response, {
    'create status=201': (r) => r.status === 201,
  });
}
~~~

**Cách chạy từ máy có k6 và quyền thử tải staging** (minh họa, không phải kết quả thực đã đo):

~~~bash
# Dùng token giả lập/quyền lab, không ghi secret vào repo.
export BASE_URL='https://staging-graph.example.org'
export RUN_ID='lab-run-001'
export CUSTOMER_ID='C-101'

k6 run --summary-export=graph-load-summary.json graph-load.js
~~~

Điểm cần đọc kỹ:

- `constant-arrival-rate` đặt **iteration bắt đầu/giây**; k6 có thể phải tăng số VU để duy trì arrival khi response chậm.
- Mỗi iteration trong ví dụ phát **một HTTP request**; nếu thêm các request khác trong function, `iteration/s` không còn đồng nghĩa `request/s`.
- `preAllocatedVUs` và `maxVUs` **giới hạn máy tạo tải**. Nếu không đủ, `dropped_iterations` tăng; đó là một điều kiện FAIL cần điều tra, không lặng lẽ lấy latency của những request đã chạy.
- `checks` kiểm chứng **nội dung hợp đồng**, còn `http_req_failed` phụ thuộc phân loại HTTP response thành công/thất bại. Một response HTTP 200 trả sai khách hàng có thể qua HTTP metric nhưng **trượt check**.
- Các filter `{operation:...}` hoạt động nhờ tag đặt ở **từng request**. Nhãn không được là business ID riêng từng request vì gây cardinality lớn.
- `http_req_duration` đo thời gian sending + waiting + receiving, **không gồm thời gian DNS/connect/TLS ban đầu**. Để diễn giải end-to-end phải xem thêm `http_req_blocked`, `http_req_connecting`, `http_req_tls_handshaking` và thời gian phía ứng dụng.
- `RUN_ID` phải là giá trị **duy nhất cho từng lần chạy**; khi thử lại cùng ID có thể vô tình kiểm tra `MERGE` replay thay vì tạo đơn mới.
- `setup()` kiểm tra input, nhưng **không tạo sẵn Customer**. Hãy seed `C-101` ở staging trước, kiểm tra database và quyền đúng.

> **Điểm học quan trọng:** Không suy ra 50 request/s đạt được chỉ từ hai trường `rate`. Phải kiểm tra `http_reqs`, `iterations`, `dropped_iterations`, số VU thực tế và errors. Nếu generator bị CPU 100%, kết quả có thể phản ánh giới hạn máy phát tải thay vì Neo4j.

### 10.1. Giữ phép đo WRITE có ý nghĩa

Kịch bản trên sẽ tạo **một Order mới cho mỗi WRITE iteration**. Sau 5 phút ở tốc độ mục tiêu 10 WRITE/s, số Order lý tưởng được thêm là khoảng 3.000 nếu không có dropped iterations và mọi transaction thành công. Đây là **kiểm tra kỳ vọng**, không tự thay thế đối soát thực.

Đối soát sau khi chạy bằng một **nhãn/tập dữ liệu test riêng** hoặc prefix ID đã định nghĩa. Ví dụ trên Neo4j chỉ dành cho staging:

~~~cypher
MATCH (o:Order)
WHERE o.orderId STARTS WITH $runOrderPrefix
RETURN count(o) AS createdOrders;
~~~

Truyền `$runOrderPrefix` = `O-K6-lab-run-001-`. Đảm bảo trường `orderId` không bị client giả mạo trên production và query này không scan quá lớn trong giờ cao điểm; với tập dữ liệu lớn, có thể quản lý danh sách ID test riêng hoặc dùng metadata `testRunId` được index.

Với k6 chỉ gửi HTTP, **thành công 201** vẫn chưa chứng minh Neo4j có đúng quan hệ. Phải kiểm tra tỷ lệ `PLACED`, không có duplicate và trạng thái đúng sau tải.

## 11. Năm loại kiểm thử tải và thứ tự chạy

| Loại | Mục tiêu | Cách chạy điển hình | Điều phải lưu |
| --- | --- | --- | --- |
| **Baseline** | Điểm chuẩn ở tải nhỏ | 1–5 req/s, workload ổn định | Latency, CPU, DB Hits, index state |
| **Load** | Chứng minh mục tiêu vận hành | Ví dụ 50 req/s hỗn hợp trong 5–15 phút | p95/p99, lỗi, throughput, saturation |
| **Stress** | Tìm điểm gãy khi tăng tải | Tăng từng nấc có giám sát, dừng khi vượt guardrail | Nấc lỗi đầu tiên, behavior khi saturation |
| **Spike** | Quan sát phản ứng khi traffic tăng đột ngột | Đổi arrival theo bậc trong thời gian giới hạn | Backlog, pool pending, recovery |
| **Soak** | Tìm leak/tích lũy và vấn đề dài hạn | Giữ tải ổn định 30–60 phút hoặc theo rủi ro | Heap trend, disk/log growth, timeout theo thời gian |

### 11.1. Phân biệt stress với thử phá hủy hệ thống

**Stress test không được mặc định là “đẩy đến khi máy chết”.** Cần đặt:

- Ngưỡng dừng: ví dụ error rate vượt 5% trong 3 cửa sổ đo, p99 vượt timeout, disk free xuống dưới mức an toàn.
- Quyền dừng job và cách giảm tải để hệ thống phục hồi.
- Tài khoản/tenant/dataset riêng cho kiểm thử.
- Cơ chế **cleanup và checkpoint** cho hàng chục nghìn Order vừa tạo.
- Bảng ghi giá trị arrival/throughput đạt được và trạng thái tài nguyên tại **mỗi nấc tải**.

Một service có thể tiếp nhận nhiều request hơn nhưng **throughput hoàn tất không tăng**, trong khi hàng chờ và p99 tăng mạnh. Đây là dấu hiệu saturation, không phải năng lực mở rộng thành công.

### 11.2. Recovery là một phần của kết quả

Sau khi dừng spike/stress, tiếp tục quan sát:

- API error rate có về baseline không?
- Java Driver connection pool/pending có hết backlog không?
- Neo4j heap/GC, page cache và disk I/O có bình ổn không?
- Có transaction kéo dài, constraint violation hoặc event backlog cần replay không?
- Đồ thị có còn **đúng node/relationship** sau hàng loạt retry không?

**Thời gian trở lại ổn định** là chỉ số quan trọng; đừng cắt biểu đồ ngay khi script k6 kết thúc.

## 12. Thiết lập giám sát để giải thích kết quả thử tải

Một bài benchmark tốt phải có dữ liệu **cùng mốc thời gian** ở ba tầng:

~~~mermaid
flowchart TB
    K["k6 generator<br/>RPS, latency, errors, dropped"] --> A["Spring API<br/>HTTP, thread, connection pool, GC"]
    A --> D[("Neo4j<br/>Bolt, tx, query, page cache, disk")]
    K -.-> M["Metrics / dashboard / report"]
    A -.-> M
    D -.-> M
    H["Host/container<br/>CPU, memory, I/O, network"] -.-> M
~~~

### 12.1. Metric tối thiểu theo tầng

| Tầng | Metric cần lưu | Giúp phân biệt |
| --- | --- | --- |
| **k6** | `http_reqs`, `http_req_duration` p50/p95/p99, `http_req_failed`, `checks`, `dropped_iterations` | SUT đạt rate? response đúng? |
| **Spring API** | HTTP latency theo operation, errors, thread/queue, JVM heap/GC, CPU | Chi phí trước/sau query |
| **Neo4j Java Driver** | Connection acquisition/pool pending, retries, timeout, routing/handshake | Request chờ phía client hay server? |
| **Neo4j database** | Transactions, Bolt connections, active/blocked transaction, index state, query log | Có lock, IO, schema issue? |
| **Neo4j process** | Heap, GC pause, page cache misses/hits, CPU, disk reads/writes | Saturation, cache và I/O |
| **Host/container** | CPU throttling, OOM, disk free/latency, network RTT | Nút thắt hạ tầng |
| **CDC/outbox nếu có** | Lag, event age, replay errors, DLQ, `sourceVersion` | Graph có hội tụ kịp sau WRITE? |

Metrics cụ thể có thể không được xuất sẵn ở tất cả phiên bản/edition. Với **Neo4j Enterprise self-managed**, xem export/JMX/Prometheus và Neo4j Ops Manager theo bản hỗ trợ; **Aura** có dashboard/API giới hạn theo gói. Ở phía Java, khả năng instrument driver pool tùy integration Micrometer/tracing; đừng tự khẳng định một metric có tên nào đó chắc chắn được bật mặc định.

### 12.2. Dấu hiệu nghẽn thường gặp

| Quan sát | Giả thuyết ưu tiên | Kiểm chứng |
| --- | --- | --- |
| p99 tăng, Neo4j CPU thấp, app pool pending tăng | Connection pool hoặc mạng/routing | Pool acquisition, count active/idle, TLS/network |
| p99 tăng, DB Hits/Rows tăng gấp nhiều lần | Cypher plan hoặc dữ liệu fan-out | `PROFILE`, tham số high-degree, schema |
| READ chậm khi WRITE tăng, transaction wait cao | Lock/contention ở hot node | `SHOW TRANSACTIONS`, query mix, batch sizes |
| Heap/GC tăng sau mỗi phút soak, không hồi | Giữ object/Result/graph projection | Memory telemetry, Java heap analysis, query lifecycle |
| Disk I/O tăng, page cache misses cao | Working set vượt page cache hoặc import cạnh tranh | Page cache, disk latency, dataset |
| `dropped_iterations` tăng nhưng server chưa bão hòa | Generator thiếu VU/CPU hoặc cấu hình arrival | Máy k6, preAllocatedVUs/maxVUs, network |
| WRITE trả 201 nhưng graph projection thiếu đơn mới | Kiến trúc outbox/CDC bị trễ hoặc response sai semantics | Source commit, consumer apply, watermark |

**Không kết luận từ một metric.** Một request chậm có thể gồm nhiều thành phần: DNS, HTTP queue, Java serialization, pool wait, Bolt, Cypher execution, network trả result. Gắn trace/correlation ID và timestamp khi phân tích.

### 12.3. Tracing và transaction metadata

Với Java Driver hỗ trợ `TransactionConfig`, có thể gắn metadata **không nhạy cảm** cho transaction:

~~~java
import java.time.Duration;
import java.util.Map;
import org.neo4j.driver.TransactionConfig;

var cfg = TransactionConfig.builder()
        .withTimeout(Duration.ofSeconds(5))
        .withMetadata(Map.of(
                "operation", "listCustomerOrders",
                "testRunId", "lab-run-001"))
        .build();

// Giả định session là một Session đã mở ở đúng database.
var rows = session.executeRead(tx -> tx.run("""
    MATCH (c:Customer {customerId: $id})-[:PLACED]->(o:Order)
    RETURN o.orderId AS orderId
    ORDER BY o.orderId
    LIMIT 20
    """, Map.of("id", "C-101")).list(), cfg);
~~~

Mã là **fragment**, cần context `session` hợp lệ. Có thể quan sát metadata ở log/transaction tùy quyền và cấu hình. Không gắn email, token, card number hoặc business ID nhạy cảm vào tracing tags. Tránh high-cardinality `testRunId` trên metric lâu dài nếu số lần chạy rất lớn; thích hợp hơn cho log/traces có retention.

## 13. EXPLAIN/PROFILE: chứng minh nguyên nhân trong Cypher

Xét truy vấn phục vụ `GET /v1/customers/{id}/orders?limit=20`:

~~~cypher
MATCH (c:Customer {customerId: $id})-[:PLACED]->(o:Order)
RETURN o.orderId AS orderId,
       o.status AS status,
       o.totalCents AS totalCents
ORDER BY o.createdAt DESC, o.orderId DESC
LIMIT 20;
~~~

Để xem plan mà **không chạy**:

~~~cypher
EXPLAIN
MATCH (c:Customer {customerId: $id})-[:PLACED]->(o:Order)
RETURN o.orderId AS orderId,
       o.status AS status,
       o.totalCents AS totalCents
ORDER BY o.createdAt DESC, o.orderId DESC
LIMIT 20;
~~~

Để đo Rows/DB Hits, **chỉ cho READ query an toàn trong lab/điều kiện được duyệt**:

~~~cypher
PROFILE
MATCH (c:Customer {customerId: $id})-[:PLACED]->(o:Order)
RETURN o.orderId AS orderId,
       o.status AS status,
       o.totalCents AS totalCents
ORDER BY o.createdAt DESC, o.orderId DESC
LIMIT 20;
~~~

**`EXPLAIN` chỉ lập kế hoạch; `PROFILE` chạy thật và tốn thêm chi phí đo.** `PROFILE` trên `CREATE`/`SET`/`DELETE` có thể ghi dữ liệu — không dùng trên production chỉ để xem plan.

### 13.1. Bảng đọc bằng chứng query plan

| Operator/metric | Bằng chứng | Hướng điều tra |
| --- | --- | --- |
| `NodeIndexSeek` / `NodeUniqueIndexSeek` | Có dùng index/constraint trên `customerId` không? | Nếu không, so predicate/kiểu index/param |
| `NodeByLabelScan` | Có quét nhiều node thay vì seek? | Kiểm tra label/index/selectivity |
| `Expand(All)` | Một Customer nhân thành bao nhiêu Order? | High-degree, fan-out, giới hạn traversal |
| `Sort` / `Top` | Có phải sắp xếp hàng nghìn Order trước `LIMIT`? | Đổi query shape khi semantics cho phép |
| `Rows` | Bao nhiêu hàng trung gian ở mỗi bước? | N+1, Cartesian/aggregation, filter placement |
| `DB Hits` | Bao nhiêu truy cập dữ liệu tầng store? | So baseline và query alternative |
| Page cache hits/misses | Có đang chạm I/O ngoài cache? | Cache warm/cold, workload tương tự |
| Memory/timing | Operator nào chịu phần lớn chi phí? | Join/order, sort, projection rộng |

Tên/cột operator có thể khác theo phiên bản Neo4j/Cypher. **Không bắt buộc plan text giống nhau** giữa hai phiên bản; gate cần căn cứ correctness, latency và chi phí.

### 13.2. Truy vấn kiểm tra schema

~~~cypher
SHOW INDEXES
YIELD name, type, state, populationPercent, labelsOrTypes, properties
RETURN name, type, state, populationPercent, labelsOrTypes, properties
ORDER BY name;
~~~

~~~cypher
SHOW CONSTRAINTS;
~~~

Một số index ở trạng thái `POPULATING`/`FAILED` có thể chưa được planner sử dụng như index `ONLINE`. Trong báo cáo phải ghi **trạng thái index tại thời điểm đo**, chứ không chỉ nói “đã tạo index”.

### 13.3. Bẫy: LIMIT không bảo đảm chỉ xử lý 20 hàng

Giả sử Customer `C-HOT` có 70.000 Order:

~~~cypher
MATCH (c:Customer {customerId: 'C-HOT'})-[:PLACED]->(o:Order)
RETURN o.orderId
ORDER BY o.createdAt DESC
LIMIT 20;
~~~

Planner có thể vẫn phải duyệt/sắp xếp số lượng lớn Order trước khi chọn 20. Để giảm chi phí, có thể thiết kế **bộ dữ liệu/đường truy vấn theo nhu cầu** (ví dụ keyset pagination, materialized summary, relationship thuộc tính đã index trên node thích hợp), nhưng phải **giữ nguyên hợp đồng nghiệp vụ** khi tối ưu.

Không thay “20 Order mới nhất” bằng “20 Order bất kỳ” rồi báo p95 giảm mạnh mà coi là thành công.

## 14. Cách thiết kế thí nghiệm so sánh trước–sau

**Thí nghiệm tốt kiểm soát biến**, không chạy một lần trước rồi một lần sau trong hai môi trường khác nhau và tuyên bố tối ưu thành công.

### 14.1. Những biến phải cố định hoặc công bố

| Biến | Vì sao quan trọng |
| --- | --- |
| **Neo4j version, edition, runtime, store format** | Planner, operator, index/provider thay đổi qua release |
| **Java Driver, Spring Boot/SDN, JDK** | Query generation, pool, retry, JIT, serialization |
| **CPU, RAM, heap, page cache, disk** | Trực tiếp quyết định saturation và I/O |
| **Dataset count và skew** | Node bậc cao ảnh hưởng traversal/p99 |
| **Constraint/index + state** | `ONLINE` và selectivity thay đổi plan |
| **Network/generator placement** | RTT, TLS, generator CPU và dropped iterations |
| **Workload tỷ lệ READ/WRITE** | Ghi tạo lock/index I/O, đọc chiếm CPU/cache |
| **Warm-up/cold-cache state** | First query compile/cache khác steady state |
| **Concurrency/arrival rate** | Thay đổi queueing và saturation |
| **Background jobs** | Backup/import/GDS/CDC có thể tranh tài nguyên |

Nếu không thể giữ một biến cố định, hãy ghi **sự khác biệt và rủi ro diễn giải** trong hồ sơ.

### 14.2. Quy trình A/B minh họa

~~~text
1) Chuẩn bị dataset snapshot D1, index ONLINE.
2) Chạy warm-up theo cùng profile.
3) Chạy A (query/index version cũ) tại 10, 30, 50 req/s.
4) Ghi metrics, query plans, timestamps, CPU/GC/disk.
5) Reset graph về snapshot D1 hoặc trạng thái tương đương.
6) Chạy B (tối ưu Cypher/index) tại đúng các mức tải.
7) Lặp thêm lần để thấy phương sai; đổi thứ tự A/B khi thích hợp.
8) So correctness, p95/p99, throughput, error, DB Hits/Rows.
9) Kiểm tra hồi quy ở WRITE và những API khác.
10) Quyết định giữ B, sửa tiếp hay rollback về A.
~~~

**Thứ tự A trước B có thể tạo lợi thế cache/JIT cho B.** Trong điều kiện có thể, sử dụng warm-up và lặp đo để giảm thiên lệch; kết quả một lần chạy không đủ chứng minh chênh lệch 5% là thật.

### 14.3. Khi cần so sánh theo phiên bản

Nếu nâng Neo4j 5 lên bản 2025/2026 và đồng thời đổi Cypher version/index/store format:

1. So **binary cũ và mới** với cùng query và index tương đương.
2. Sau đó mới thử **store format mới** nếu edition cho phép.
3. Cuối cùng thử **Cypher 5 vs Cypher 25** ở bản hỗ trợ.

Không gom tất cả thay đổi trong một lần đo; nếu p99 tăng sẽ khó biết nguyên nhân.

## 15. SLI, SLO và ngưỡng nghiệm thu cho đồ án

### 15.1. Định nghĩa chỉ số

- **Latency:** p50 phản ánh trung vị; p95/p99 phản ánh đuôi chậm. Đặt riêng theo operation READ/WRITE.
- **Throughput:** số request/transaction **hoàn tất thành công** mỗi giây, không chỉ số request đến.
- **Error rate:** tỷ lệ HTTP lỗi, timeout, transaction failed và assertion sai; các loại phải được phân biệt.
- **Availability SLI:** số request hợp lệ đáp ứng tiêu chí thành công / tổng số request hợp lệ trong phạm vi đo.
- **Freshness:** nếu Neo4j là projection, thời gian từ source commit đến khi graph có version tương ứng.
- **Saturation:** điểm tải mà tăng arrival không còn tăng throughput tương ứng nhưng làm p99/lỗi/queue tăng.

Ví dụ:

\[
\mathrm{SLI_{success}}=\frac{\text{số yêu cầu hợp lệ hoàn tất đúng và đúng hạn}}{\text{tổng số yêu cầu hợp lệ}}
\]

`HTTP 200` nhưng response sai customer/thiếu Order **không được tính thành công về nghiệp vụ**. Ngược lại, API từ chối request sai input đúng theo contract có thể được phân loại riêng, không mặc định tính là service error.

### 15.2. SLO giả định và gate

| Operation | SLO ví dụ | Failure gate |
| --- | --- | --- |
| `GET Customer Orders` | p95 < 250 ms, p99 < 500 ms | Vượt ở workload 40 READ/s |
| `POST Create Order` | p95 < 600 ms, lỗi < 1% | Vượt ở workload 10 WRITE/s |
| API correctness | 100% assertions domain quan trọng | Sai relationship/tenant/business ID |
| Dropped iterations | 0 ở mức tải mục tiêu | Máy phát tải không đạt arrival |
| Transaction integrity | Không có duplicate theo `orderId` | Ghi lặp sau retry |
| Projection freshness khi có CDC | 99% event hiển thị trong 10 giây | Backlog/freshness vượt mục tiêu |

**Tất cả là số liệu học tập.** Không chọn 250 ms chỉ vì xuất hiện trong script; quyết định SLO theo giá trị ứng dụng, traffic thực và khả năng tài nguyên, được người sở hữu nghiệp vụ chấp thuận.

### 15.3. Lỗi thường gặp khi dùng percentile

- **Trung bình 100 ms không chứng minh p99 tốt.** Vài request 10 giây vẫn có thể gây timeout/gián đoạn.
- **p99 của 20 request** có độ tin cậy kém cho mô tả đuôi tải; cần đủ mẫu và nhiều lần đo khi cần.
- **Percentile của từng phút không thể lấy trung bình số học để có p95 toàn test**. Phải dùng raw distribution/histogram/công cụ tính percentile chung.
- **Những iteration bị drop không có latency request để tính p99**. Luôn báo riêng dropped iterations và achieved throughput.
- Nếu retry che lỗi ở tầng driver, API có thể trả 200 nhưng latency tăng; lưu **retry rate** và end-to-end user latency.

## 16. Hồ sơ hiệu năng: cấu trúc báo cáo có thể kiểm chứng

Hồ sơ hiệu năng (*performance dossier*) là tài liệu để người khác **lặp phép đo** và quyết định có phát hành không. Không chỉ là một ảnh screenshot Grafana.

### 16.1. Mẫu biểu mẫu báo cáo

~~~text
PERFORMANCE DOSSIER — Graph Commerce
Report ID / timestamp UTC:
Owner / reviewer:
Git commit/tag application:
Neo4j version / edition / deployment:
Java version / Driver / SDN version:
API deployment config / pod replicas:
Neo4j CPU / RAM / heap / page cache / disk:
Driver pool / tx timeout / retry config:
Graph dataset ID + seed + checksum:
Node counts / relationship counts / high-degree distribution:
Index / constraint list + state:
Load generator version / host / CPU / network:
Endpoints and operation mix:
Auth/test data policy (no secrets in report):
Warm-up / steady / stress / recovery windows:
Arrival targets and achieved RPS:
Errors + failed correctness checks:
Dropped iterations:
Latency p50 / p95 / p99 by operation:
Resource bottleneck evidence:
EXPLAIN/PROFILE snapshots:
Comparison with accepted baseline:
Assumptions, invalid runs, confounders:
Business correctness verification after load:
Decision: PASS / FAIL / INCONCLUSIVE
Follow-ups + owners + rerun conditions:
~~~

**PASS** khi đạt cả correctness và ngưỡng tải dưới điều kiện thí nghiệm hợp lệ; **FAIL** khi một gate không đạt; **INCONCLUSIVE** khi thiếu mẫu, generator nghẽn hoặc dữ liệu/biến kiểm soát không phù hợp. Không ép một lần chạy không hợp lệ thành PASS.

### 16.2. Bảng số liệu minh họa (không phải kết quả đã chạy)

| Kịch bản | Target RPS | Achieved RPS | READ p95/p99 | WRITE p95 | Error | Dropped | Kết luận |
| --- | ---: | ---: | --- | ---: | ---: | ---: | --- |
| Baseline | 10 | 10 | 58 / 95 ms | 110 ms | 0,00% | 0 | PASS |
| Load A | 50 | 49,8 | 230 / 420 ms | 520 ms | 0,30% | 0 | PASS theo SLO ví dụ |
| Stress B | 100 | 83 | 710 / 1.900 ms | 1.400 ms | 7,20% | 1.050 | FAIL; đã vượt điểm chịu tải |
| Optimized A | 50 | 49,9 | 135 / 290 ms | 530 ms | 0,20% | 0 | PASS, cần đối soát correctness |

Tất cả số liệu **giả định**, mục đích là minh họa cách nhìn toàn diện:

- `Achieved RPS` có thể thấp hơn target vì dropped iterations, thất bại hoặc giới hạn generator.
- Bản “Optimized A” giảm READ latency nhưng WRITE tăng nhẹ từ 520 lên 530 ms; cần kiểm tra còn dưới SLO và không tăng quá mức tài nguyên.
- Stress B cho biết **giới hạn hệ thống ở cấu hình đó**, không chứng minh Neo4j nói chung chỉ chịu 83 RPS.

### 16.3. Hồ sơ query plan

| Query ID | Param category | Plan trước | Plan sau | DB Hits trước/sau | p95 trước/sau | Kết luận |
| --- | --- | --- | --- | --- | --- | --- |
| Q-READ-01 | Customer ít Order | Index seek + expand | Index seek + expand | 85 / 82 | 40 / 38 ms | Không thay đổi lớn |
| Q-READ-02 | Customer 10.000 Order | Expand + Sort | Filter/Top tốt hơn | 40.000 / 9.500 | 340 / 125 ms | Cải thiện trong lab |
| Q-WRITE-01 | Order mới | MERGE + constraint | MERGE + constraint | 600 / 615 | 510 / 530 ms | Tăng nhẹ, còn trong SLO |

Những con số/plan là **minh họa cấu trúc báo cáo**, không khẳng định một query nào tự sinh plan như vậy. Với mỗi row, kèm **query text, dữ liệu tham số đã ẩn danh, version, index state và raw plan** để người khác đối chiếu.

## 17. Phân tích nguyên nhân và tối ưu có chứng cứ

Giả sử sau load test thấy `GET Customer Orders` có p99 = 1.400 ms, trong khi `POST Create Order` vẫn đạt. Thử theo thứ tự:

1. **Kiểm tra generator:** dropped iterations có tăng? CPU k6 có nghẽn? Nếu có, điều chỉnh generator và chạy lại trước khi quy lỗi cho DB.
2. **Kiểm tra app:** pool pending, HTTP queue, serialization và số lần gọi repository. Nếu p99 phía app cao nhưng query Neo4j nhanh, tập trung ở app/network.
3. **Kiểm tra query:** `PROFILE` ở Customer bậc cao, số Rows/DB Hits/Sort, có index seek đúng không.
4. **Kiểm tra resource:** page cache miss, disk I/O, CPU, GC và công việc background đồng thời.
5. **Đề xuất một thay đổi:** thêm index thực sự phù hợp, sửa query shape/limit, dùng DTO, chuyển từ N+1 sang batch, hoặc phân trang.
6. **Đo A/B trên cùng dataset và tải**, kiểm tra không đổi semantics hoặc làm WRITE xấu đi.
7. **Đưa bằng chứng vào hồ sơ:** bản plan, metrics và quyết định có giữ thay đổi hay không.

### 17.1. Tránh tối ưu nhầm

Ví dụ query:

~~~cypher
MATCH (c:Customer {customerId: $id})-[:PLACED]->(o:Order)
RETURN o.orderId AS orderId
ORDER BY o.createdAt DESC
LIMIT 20;
~~~

Nếu muốn chọn “20 Order gần nhất”, cần xác định tie-breaker và điều kiện khi `createdAt` null. Đổi thành:

~~~cypher
MATCH (c:Customer {customerId: $id})-[:PLACED]->(o:Order)
RETURN o.orderId AS orderId
ORDER BY o.createdAt DESC, o.orderId DESC
LIMIT 20;
~~~

Sửa thứ tự có thể giúp kết quả **ổn định hơn**, nhưng không tự giảm fan-out. Hãy đo `Rows`/`DB Hits`; với Customer có hàng vạn Order, cần xem lại **mô hình truy vấn theo access pattern** thay vì thêm index trùng.

### 17.2. Khi nào nên scale out?

Nếu một truy vấn vẫn nặng vì thiếu index hoặc trả quá nhiều dữ liệu, thêm secondary thường **không làm query đơn lẻ hết tốn công**. Với Neo4j Enterprise cluster, secondary giúp phân phối nhiều READ độc lập; throughput có thể tăng nếu routing đúng và có CPU/RAM/disk phù hợp. **Một standard database vẫn có một writer tại một thời điểm**, nên thêm primary không tự nhân WRITE throughput.

Đo trước–sau và ghi topology/failure domain; không kết luận từ số lượng pod/container.

## 18. CI/CD: quyết định quality gate nào chạy ở đâu?

### 18.1. Pipeline gợi ý

~~~mermaid
flowchart LR
    PR["Pull request"] --> U["Unit tests"]
    U --> I["Testcontainers integration"]
    I --> C{"Correctness gate"}
    C -->|FAIL| X["Block merge"]
    C -->|PASS| B["Build artifact"]
    B --> S["Deploy staging"]
    S --> L["Load test có quyền và quota"]
    L --> P["Raw metrics + dossier"]
    P --> G{"Performance go/no-go"}
    G -->|FAIL| R["Investigate / revert"]
    G -->|PASS| A["Release approval"]
~~~

Gợi ý phân tầng:

| Pipeline | Bài test | Vì sao |
| --- | --- | --- |
| **PR/merge request** | Unit + integration Testcontainers + schema/constraint cases | Phản hồi nhanh, phát hiện regression correctness |
| **Nightly** | Full API integration, dataset biên, concurrency và CDC khi có | Giữ chất lượng workflow nhiều component |
| **Trước release** | Load/stress trên staging sát production, profile và report | Quyết định SLO/go-no-go |
| **Theo lịch vận hành** | Soak, synthetic read/write và trend performance | Phát hiện leak/regression dài hạn |

Một lần đo 60 phút cho mỗi commit PR thường **không kinh tế**; ngược lại không nên bỏ kiểm thử tải trước phát hành tính năng traversal mới trên graph lớn.

### 18.2. Các command minh họa

~~~bash
# Chạy tại repo của ứng dụng đã cấu hình Testcontainers/JUnit.
# Không dùng các command này nếu chưa xác minh đúng môi trường test.
./gradlew test

# Ở runner staging có k6 và đã được cho phép thử tải:
k6 run --summary-export=graph-load-summary.json graph-load.js
~~~

Các command chỉ là **ví dụ để người học tự triển khai**. Bài không mặc định project có Gradle Wrapper hay file `graph-load.js`, không chứng minh đã chạy test. Khi tích hợp CI thật phải có artifact upload, biến môi trường, cấp quyền runner và job timeout.

### 18.3. Gate trong CI nên đọc gì?

- **Exit code JUnit/test runner** và số tests skipped/failure; không chấp nhận job xanh nếu test integration bị skip vì Docker không sẵn.
- **k6 threshold exit code** và `dropped_iterations`; nếu k6 không đạt target arrival do generator, phải đánh dấu test **inconclusive/fail theo policy**.
- **Performance report artifact** gồm môi trường, dataset ID và timestamps, tránh chỉ lưu console 30 dòng cuối.
- **Correctness after load**: đối soát số Order, `PLACED`, conflict/replay và không mất dữ liệu.
- **Baseline comparison** có ngưỡng regression công bố trước, không thay tiêu chí sau khi thấy kết quả.

**Không** để CI tự động tạo/xóa một database production, hoặc tự bắn stress từ runner public vào endpoint đang phục vụ khách hàng.

## 19. Kiểm thử lỗi và phục hồi (phần mở rộng của capstone)

Một hệ thống đạt load test khi mọi thứ khỏe chưa chắc vận hành tốt khi có lỗi.

| Tình huống | Phép thử an toàn trong lab | Expected result |
| --- | --- | --- |
| Neo4j container tạm dừng/restart | Gián đoạn node test riêng, không prod | App trả lỗi rõ/retry giới hạn rồi phục hồi |
| Driver mất connection gần commit | Mô phỏng network failure theo tool lab | Không nhân đôi Order; kiểm tra business ID trước replay |
| API nhận cùng create request hai lần | Gửi payload/idempotency key giống nhau | Một Order, một relationship `PLACED` |
| Constraint bị vi phạm | Cố `CREATE` Order trùng business ID | Transaction thất bại, graph không bị ghi nửa |
| Transaction xử lý quá thời hạn | Giới hạn timeout trong lab cho query tốn thời gian | Tự rollback/giải phóng resource theo cơ chế |
| Index chưa `ONLINE` | Tạo index trong lab có dữ liệu thử | Health/perf gate không báo PASS sai |
| Source-of-truth/CDC bị trễ | Dừng consumer mô phỏng | API/metrics biểu thị stale; backlog phục hồi đúng |
| Kết nối tenant trái quyền | Credential/tenant test giả | Không truy cập graph không được phép |

### 19.1. Bảo vệ transaction với retry

Neo4j Driver có thể tự retry managed transaction `executeRead`/`executeWrite` khi gặp lỗi transient được nhận diện. Vì callback có thể được gọi lại:

- Dùng **business ID/constraint** thay vì sinh ID mới ngẫu nhiên trong callback khi retry.
- Không gửi email, trừ tiền hoặc publish message trực tiếp trong callback mà không có cơ chế idempotency/outbox.
- Với exception lúc gần commit, không tự khẳng định “chưa ghi”: cần **query lại business key** và áp dụng chiến lược retry an toàn.
- Test cả hậu quả **sau** lỗi/retry, không chỉ nhìn Java exception.

**Lưu ý lab:** Mô phỏng mất kết nối chính xác tại commit không luôn dễ tái lập; nếu không tạo được fault injection đáng tin, viết rõ phạm vi test và bổ sung runbook/manual drill thay vì ghi PASS giả.

### 19.2. Không dùng chaos test để phá cluster production

Không dừng hai trong ba primary để “kiểm tra quorum” ở môi trường thật; không xóa transaction logs hoặc store files; không làm đầy disk. Nếu mục tiêu có HA, dựng **cluster thử nghiệm** với edition tương ứng, kiểm tra primary/secondary, read/write routing và failover theo runbook chính thức.

## 20. Lộ trình triển khai đồ án theo từng mốc

| Mốc | Công việc | Đầu ra kiểm tra |
| --- | --- | --- |
| **M1** | Chốt use case, invariant, API contract và SLO | Test matrix, ngưỡng nghiệm thu |
| **M2** | Tạo schema/fixture, pin version, dựng Testcontainers | IT-01 đến IT-05 chạy trên Neo4j thật |
| **M3** | Thêm API/security tests và trường hợp data skew | IT-06 đến IT-09, test result raw |
| **M4** | Seed staging, instrument API/Neo4j, chuẩn bị load generator | Dashboard cùng timestamp, dataset card |
| **M5** | Chạy baseline/load/stress/spike/soak có guardrail | k6 raw metrics, kết quả từng nấc |
| **M6** | PROFILE query nóng, tối ưu có đối chứng | Trước–sau Rows/DB Hits/p95/p99 |
| **M7** | Đối soát sau tải, viết dossier, quyết định go/no-go | Biên bản nghiệm thu và runbook |

### 20.1. Thứ tự làm việc thực tế

**Bước 1 — Chốt yêu cầu:** Bổ sung một bảng mô tả graph schema, các endpoint, dữ liệu test và phân phối read/write. Định nghĩa thế nào là “tạo đơn thành công” và trạng thái sau replay.

**Bước 2 — Dựng integration suite:** Đảm bảo container chạy Neo4j thật với schema, seed và cleanup. Viết assert graph bằng Cypher sau khi gọi service/API; kiểm thử rollback và conflict trước các kịch bản hiệu năng.

**Bước 3 — Chuẩn hóa dataset:** Chọn dataset ID, random seed, số Customer/Order/Product, fan-out và tỷ lệ data skew. Viết hướng dẫn bootstrap/checksum và bước kiểm tra đủ index `ONLINE`.

**Bước 4 — Chạy baseline:** Chụp môi trường, commit, query plan, CPU/heap/page cache và response time ở mức tải thấp. Nếu correctness fail, **dừng tại đây**, không bắn load.

**Bước 5 — Chạy mục tiêu:** Cấu hình k6 arrival rate và threshold. Ghi cả achieved throughput và dropped iterations; bảo đảm máy tạo tải không nghẽn.

**Bước 6 — Chẩn đoán:** Với operation fail, lấy `PROFILE` trên dataset/param đại diện, đối chiếu Rows/DB Hits, lock wait, pool và resource. Đặt giả thuyết rồi chọn một sửa đổi có lý do.

**Bước 7 — Đo lại:** Reset về dataset cùng trạng thái, đo A/B và kiểm tra regression các endpoint khác; không đổi nhiều biến đồng thời.

**Bước 8 — Nộp hồ sơ:** Ghi PASS/FAIL/INCONCLUSIVE, hạn chế thí nghiệm, nguyên nhân và hướng xử lý tiếp; đính kèm artifact theo đường dẫn nhóm quản lý.

## 21. Rubric chấm đồ án gợi ý (100 điểm)

| Tiêu chí | Điểm | Đạt tối đa khi |
| --- | ---: | --- |
| Domain invariants và test matrix | 15 | Bao phủ happy path, conflict, edge, tenant/error |
| Integration tests trên Neo4j thật | 25 | Testcontainers, constraints, relationships, rollback, idempotency; setup tái lập |
| API integration/security | 10 | Assert HTTP **và** trạng thái graph cuối cùng |
| Dataset và workload realism | 15 | Dữ liệu skew, READ/WRITE mix, open/closed model, generator đúng tải |
| Metrics và query profiling | 15 | k6 + app + Neo4j metrics; `EXPLAIN/PROFILE` có DB Hits/Rows |
| Hồ sơ hiệu năng và A/B | 15 | Có raw results, điều kiện đo, ngưỡng, so sánh, giải thích và kết luận |
| An toàn vận hành, CI và khả năng tái lập | 5 | Không chạm production, có cleanup/runbook/owners |
| **Tổng** | **100** | Correctness là điều kiện bắt buộc để nghiệm thu |

**Quy tắc chặn:** Dù tổng điểm cao, nếu kiểm thử làm lộ dữ liệu tenant khác, tạo duplicate đơn do retry hoặc tự động xóa dữ liệu ngoài lab, bài đồ án cần **khắc phục trước khi phát hành**.

## 22. Những sai lầm phổ biến khi kiểm thử Neo4j

| Sai lầm | Hậu quả | Cách sửa |
| --- | --- | --- |
| Chỉ mock repository | Không kiểm tra Cypher, constraint, transaction thật | Testcontainers + Neo4j thật |
| Test không cleanup/không seed | Kết quả phụ thuộc thứ tự test trước | Dataset deterministic, DB riêng |
| Dùng `DETACH DELETE` nhầm production | Mất graph | Kiểm tra namespace/container và quyền |
| Benchmark 100 Customer nhỏ | Không phát hiện fan-out ở high-degree nodes | Seed phân phối bậc đúng |
| Chỉ đo average latency | Che timeout/p99 và trải nghiệm xấu | p95/p99 + lỗi + dropped |
| Dùng constant VUs rồi gọi là 100 req/s cố định | Arrival giảm khi SUT chậm | Chọn executor đúng; đo achieved RPS |
| Không đo generator CPU | Nhầm bottleneck k6 thành Neo4j | Theo dõi host k6 và iteration drops |
| Coi HTTP 200 là đúng | API có thể trả sai relationship/tenant | Checks + query đối soát graph |
| Reuse `orderId` ở mọi test WRITE | Đo idempotent MERGE thay vì tạo mới | RUN_ID duy nhất, test replay riêng |
| Benchmark khi index `POPULATING` | Plan và I/O không ổn định | Đợi `ONLINE` hoặc ghi rõ mục tiêu |
| `PROFILE` query WRITE trên prod | Thay đổi dữ liệu ngoài ý muốn | Chỉ profile WRITE trong lab/transaction kiểm soát |
| Thêm nhiều index không đo | Tăng disk và chi phí ghi | So plan/DB Hits và write regression |
| Thay đổi dữ liệu giữa A và B | Không so sánh được | Snapshot/seed version giống nhau |
| K6 PASS nhưng thiếu Order trong Neo4j | Thành công HTTP giả hoặc async lag | Post-load correctness/reconciliation |
| Không giữ raw report | Khó tái lập/đối soát | Lưu script, dataset, configs, raw metrics |

## 23. Checklist nghiệm thu cuối cùng

- [ ] Mọi API có **hợp đồng input/output và domain invariants** rõ ràng.
- [ ] Dùng đúng phiên bản Neo4j, Java Driver, Spring Boot/SDN và Testcontainers tương thích.
- [ ] Integration test kết nối **Neo4j thật**, không chỉ mock; chạy trong database/container **cách ly**.
- [ ] Tạo đúng uniqueness constraint và assert node/relationship/hướng/thuộc tính.
- [ ] Kiểm thử replay, payload conflict, rollback, concurrent writes và lỗi invalid data.
- [ ] Kiểm thử security/multi-tenant, không để query/API trả dữ liệu trái quyền.
- [ ] Dữ liệu seed có **high-degree nodes, null, Unicode, đa dạng số item** và random seed.
- [ ] Test API assert **nội dung nghiệp vụ** và trạng thái graph sau commit.
- [ ] Load script có workload mix, arrival model, thời lượng, RUN_ID, ngưỡng và guardrail.
- [ ] Có baseline, load, stress/spike và soak theo nhu cầu, không phá production.
- [ ] Báo cả **target/achieved RPS, p50/p95/p99, lỗi, checks, dropped iterations**.
- [ ] Lưu metrics API, Driver, Neo4j, OS/container cùng timeline để xác định bottleneck.
- [ ] Các index quan trọng `ONLINE`; có `EXPLAIN/PROFILE` cho query nóng.
- [ ] Phân biệt `Rows`, `DB Hits`, pool wait, cache misses và thời gian app/network.
- [ ] So sánh A/B trên cùng dataset/workload, không đổi nhiều biến rồi quy kết tùy ý.
- [ ] Sau load, đối soát **Order/PLACED/CONTAINS**, không có duplicate hoặc mất dữ liệu.
- [ ] Khi dùng CDC/outbox, kiểm tra freshness, backlog, idempotency và các event bị trễ.
- [ ] Pipeline có quality gates, exit codes và artifact; không coi job skipped là pass.
- [ ] Hồ sơ hiệu năng ghi rõ môi trường, git commit, config, dataset, limitations và kết luận.
- [ ] Nêu PASS/FAIL/INCONCLUSIVE theo SLO và đúng dữ liệu, có owner và kế hoạch cải thiện.
- [ ] Có runbook cleanup/restore và chỉ thử lỗi trên lab được phép.

## Tài liệu tham khảo

- [Neo4j Java Driver — Transactions, retries và session lifecycle](https://neo4j.com/docs/java-manual/current/transactions/)
- [Neo4j Java Driver — Connect to the database](https://neo4j.com/docs/java-manual/current/connect/)
- [Spring Data Neo4j — Testing with Spring Boot](https://docs.spring.io/spring-data/neo4j/reference/testing/testing-with-spring-boot.html)
- [Spring Boot — Testcontainers và DynamicPropertySource/ServiceConnection](https://docs.spring.io/spring-boot/reference/testing/testcontainers.html)
- [Testcontainers — Neo4j module](https://java.testcontainers.org/modules/databases/neo4j/)
- [Neo4j Cypher — Understanding query execution plans](https://neo4j.com/docs/cypher-manual/current/planning-and-tuning/execution-plans/)
- [Neo4j Cypher — Query tuning](https://neo4j.com/docs/cypher-manual/current/planning-and-tuning/query-tuning/)
- [Neo4j Cypher — Constraints](https://neo4j.com/docs/cypher-manual/current/constraints/)
- [Neo4j Operations — Monitoring và metrics](https://neo4j.com/docs/operations-manual/current/monitoring/)
- [Grafana k6 — Scenarios và executors](https://grafana.com/docs/k6/latest/using-k6/scenarios/executors/)
- [Grafana k6 — Constant arrival rate](https://grafana.com/docs/k6/latest/using-k6/scenarios/executors/constant-arrival-rate/)
- [Grafana k6 — Metrics reference](https://grafana.com/docs/k6/latest/using-k6/metrics/reference/)
- [Grafana k6 — Thresholds](https://grafana.com/docs/k6/latest/using-k6/thresholds/)

**Kết luận:** Giai đoạn cuối của đồ án Neo4j không chỉ là thêm vài test và chụp một biểu đồ latency. Một hồ sơ đạt chất lượng phải **kiểm thử property graph thật**, xác minh transaction/constraint/relationship, tái lập workload với dữ liệu có độ lệch thực tế, đo p95/p99 và lỗi dưới tải, rồi giải thích bằng **EXPLAIN/PROFILE, index, DB Hits, Rows và tài nguyên**. Chỉ khi correctness, reliability, performance và an toàn vận hành đều có bằng chứng, nhóm mới có cơ sở quyết định **go/no-go** thay vì dựa vào một bản demo chạy được.

