# Tái tạo lỗi và chạy kiểm thử hồi quy sau đổi mô hình hoặc phiên bản

## 1. Vì sao kiểm thử hồi quy đặc biệt quan trọng với Neo4j?

Trong hệ thống sử dụng **Neo4j**, thay đổi mô hình dữ liệu không chỉ là đổi tên cột. Một thay đổi có thể biến property thành relationship, thay hướng liên kết, thay loại quan hệ, thêm constraint, đổi cách duyệt đường đi hoặc điều chỉnh index. Truy vấn **Cypher** có thể vẫn chạy thành công nhưng trả sai node, nhân đôi kết quả, thiếu đường đi hoặc tiêu tốn nhiều tài nguyên hơn.

Tương tự, khi nâng cấp **Neo4j Server**, **Java Driver**, **Spring Data Neo4j**, **APOC** hoặc **Graph Data Science (GDS)**, cú pháp, hành vi planner, API và khả năng tương thích có thể thay đổi. Một bài kiểm thử chỉ xác nhận “database khởi động được” chưa đủ để chứng minh ứng dụng tiếp tục hoạt động đúng.

Bài thuộc chương **Kiểm thử** của module **DATABASE_ENGINE_GRAPH_NEO4J**. Mục tiêu là thiết kế quy trình:

1. **Tái tạo lỗi** bằng dữ liệu đầu vào, phiên bản và điều kiện chạy được kiểm soát.
2. **Đóng băng hành vi nghiệp vụ cần giữ** trước khi đổi graph model hoặc nâng phiên bản.
3. **Chạy kiểm thử hồi quy tự động** trên database Neo4j thật, không chỉ mock Java repository.
4. **Đánh giá cả tính đúng đắn và hiệu năng**, kể cả điều kiện tranh chấp, dữ liệu không sạch và kết nối cụm.
5. **Đặt cổng kiểm soát triển khai** và có phương án phục hồi khi thay đổi không đạt yêu cầu.

**Nguyên tắc xuyên suốt:** bài test hữu ích không phải bài test lặp lại cách cài đặt hiện tại, mà là bài test có khả năng phát hiện **vi phạm hợp đồng nghiệp vụ** ngay cả khi mã nguồn hoặc sơ đồ graph đã thay đổi.

## 2. Phân loại lỗi cần tái tạo

| Nhóm lỗi | Ví dụ trong Neo4j | Bằng chứng tối thiểu |
|---|---|---|
| **Sai ngữ nghĩa truy vấn** | Sau đổi hướng **[:PLACED]**, danh sách đơn của Customer bị thiếu | Fixture, query, tham số, tập kết quả kỳ vọng |
| **Trùng/thiếu dữ liệu** | Migration tạo hai node Order cùng business key | Constraint, count, invariant và dữ liệu trước–sau |
| **Sai chiều/loại relationship** | Duyệt nhầm **DEPENDS_ON** theo chiều ngược | Sơ đồ cạnh có hướng và truy vấn kiểm tra |
| **Thay đổi tương thích** | Cypher/Java Driver/APOC không còn nhận cú pháp hoặc API cũ | Exact version, exception, vị trí lỗi |
| **Hồi quy hiệu năng** | Query từ index seek chuyển sang quét rộng; p95 tăng | Cùng workload, PROFILE, DB Hits, thời gian đo |
| **Lỗi giao dịch và cạnh tranh** | Hai request cùng key tạo trùng, deadlock hoặc lost update | Lịch chạy đồng thời, khóa, kết quả cuối |
| **Lỗi định tuyến/cụm** | Đọc ngay sau ghi qua replica không thấy thay đổi | Routing URI, bookmark, topology, thời điểm |
| **Lỗi nhập/xuất và plugin** | LOAD CSV xử lý null khác kỳ vọng; thiếu procedure GDS/APOC | File nguồn, cấu hình plugin, phiên bản và log |

Không nên chỉ dùng **assertEquals(expectedCount, actualCount)** cho mọi bài toán. Hai tập kết quả có cùng số phần tử vẫn có thể chứa **những node khác nhau**, sai hướng liên kết hoặc sai tenant.

### 2.1. Một lỗi có thể có nhiều nguyên nhân

Triệu chứng “API không tìm thấy Order O-1” có thể do:

- Migration thiếu relationship nối Customer với Order.
- Query mới dùng hướng **<-** thay vì **->**.
- Request mang **tenantId** sai.
- Dữ liệu chưa commit hoặc replica chưa bắt kịp bookmark.
- Index chưa **ONLINE**, khiến request timeout dù dữ liệu vẫn tồn tại.

Trước khi “sửa lỗi”, tạo một test nhỏ đủ phân biệt các nguyên nhân; nếu không, nhóm có thể sửa nhầm câu Cypher hoặc tăng timeout mà không chữa nguyên nhân thực.

## 3. Một báo cáo lỗi đủ điều kiện để tái tạo

Mẫu thông tin cho một bug Neo4j:

| Mục | Thông tin cần lưu |
|---|---|
| **Mô tả** | Điều người dùng làm, kết quả mong đợi và kết quả thực tế |
| **Phiên bản** | Neo4j Server, Java Driver, SDN, APOC/GDS nếu có, Java runtime |
| **Cypher language** | **Cypher 5** hay **Cypher 25** nếu server có tùy chọn |
| **Topology** | Standalone, cluster, Aura; URI **neo4j://** hay **bolt://** |
| **Schema** | Constraint, index và trạng thái **ONLINE** |
| **Dữ liệu tối thiểu** | Tập node, relationship, property gây lỗi, không chứa dữ liệu nhạy cảm |
| **Bước thực thi** | Lệnh seed, câu Cypher, tham số, thứ tự transaction |
| **Dấu vết** | Exception/code, thông báo, query plan, thời gian đo, log đã ẩn thông tin mật |
| **Kỳ vọng bất biến** | Ví dụ “mỗi Order có đúng một Customer trong cùng tenant” |

Đối với lỗi chỉ xảy ra dưới tải, bổ sung **số worker**, lịch chạy tương tranh, độ trễ, timeout và tần suất tái hiện. Đối với lỗi sau nâng cấp, lưu cả **phiên bản trước** và **phiên bản sau**.

### 3.1. Xác định phiên bản, schema và trạng thái

Trong môi trường được cấp quyền:

~~~cypher
CALL dbms.components()
YIELD name, versions, edition
RETURN name, versions, edition;
~~~

~~~cypher
SHOW CONSTRAINTS
YIELD name, type, labelsOrTypes, properties
RETURN name, type, labelsOrTypes, properties
ORDER BY name;
~~~

~~~cypher
SHOW INDEXES
YIELD name, type, state, populationPercent
RETURN name, type, state, populationPercent
ORDER BY name;
~~~

Ba nhóm thông tin trên giúp trả lời: server là bản nào, điều kiện ràng buộc có tồn tại không, index đã sẵn sàng dùng chưa. Một index **POPULATING** hoặc **FAILED** không thể được đánh giá như index **ONLINE**.

**Không chép nguyên toàn bộ log** chứa mật khẩu, token, URL có chữ ký, dữ liệu cá nhân hoặc payload khách hàng vào issue công khai. Ưu tiên một graph tổng hợp nhỏ tái tạo được lỗi.

### 3.2. Phân biệt lỗi tái hiện được và lỗi ngẫu nhiên

Mỗi bug nên được gắn ít nhất một trong ba nhãn:

- **Deterministic:** cùng dữ liệu và điều kiện chạy thì lỗi xuất hiện ổn định.
- **Concurrency-sensitive:** cần hai hoặc nhiều transaction chạy giao nhau mới xuất hiện.
- **Environment-sensitive:** chỉ xảy ra với topology, hệ điều hành, cài plugin, phiên bản hay dung lượng nhất định.

Đừng sửa test bằng cách thêm **Thread.sleep(2000)** tùy tiện. Ngủ theo thời gian không kiểm soát được scheduler hoặc replica; nếu cần thứ tự đồng thời, dùng **barrier**, **latch**, event log hoặc test harness kiểm soát thứ tự một cách rõ ràng.

## 4. Ví dụ xuyên suốt: đổi từ khóa ngoại sang relationship

Giả sử mô hình cũ lưu một mã Customer trực tiếp trên Order:

~~~text
(:DemoRegressionOrder {
  tenantId: 'shop-a',
  orderId: 'O-1',
  legacyCustomerId: 'C-1'
})
~~~

Ứng dụng mới muốn biểu diễn quan hệ đồ thị:

~~~text
(:DemoRegressionCustomer)
  -[:DEMO_REG_PLACED]->
(:DemoRegressionOrder)
~~~

**Hợp đồng nghiệp vụ cần giữ:** khi hỏi “Customer C-1 trong tenant shop-a đã đặt những đơn nào?”, cả cách truy vấn cũ và mới phải trả **O-1, O-2**, không được lấy đơn của tenant khác. Ngoài ra, chạy migration hai lần không được tạo relationship trùng.

### 4.1. Tập dữ liệu nhỏ nhưng có khả năng bắt lỗi

Chạy **một lần trong database kiểm thử riêng**, không áp dụng trực tiếp lên dữ liệu thật:

~~~cypher
CREATE CONSTRAINT demo_reg_customer_key IF NOT EXISTS
FOR (c:DemoRegressionCustomer)
REQUIRE (c.tenantId, c.customerId) IS UNIQUE;
~~~

~~~cypher
CREATE CONSTRAINT demo_reg_order_key IF NOT EXISTS
FOR (o:DemoRegressionOrder)
REQUIRE (o.tenantId, o.orderId) IS UNIQUE;
~~~

~~~cypher
CREATE
  (c1:DemoRegression:DemoRegressionCustomer {
    tenantId: 'shop-a', customerId: 'C-1'
  }),
  (c2:DemoRegression:DemoRegressionCustomer {
    tenantId: 'shop-a', customerId: 'C-2'
  }),
  (c3:DemoRegression:DemoRegressionCustomer {
    tenantId: 'shop-b', customerId: 'C-1'
  }),
  (:DemoRegression:DemoRegressionOrder {
    tenantId: 'shop-a', orderId: 'O-1', legacyCustomerId: 'C-1'
  }),
  (:DemoRegression:DemoRegressionOrder {
    tenantId: 'shop-a', orderId: 'O-2', legacyCustomerId: 'C-1'
  }),
  (:DemoRegression:DemoRegressionOrder {
    tenantId: 'shop-a', orderId: 'O-3', legacyCustomerId: 'C-2'
  }),
  (:DemoRegression:DemoRegressionOrder {
    tenantId: 'shop-b', orderId: 'O-4', legacyCustomerId: 'C-1'
  });
~~~

Tại sao fixture cần **shop-b / C-1**? Nếu không có trường hợp mã Customer trùng giữa các tenant, query mới thiếu điều kiện **tenantId** vẫn có thể vô tình vượt qua mọi test.

### 4.2. Query cũ và kết quả chuẩn

~~~cypher
MATCH (o:DemoRegressionOrder {
  tenantId: $tenantId,
  legacyCustomerId: $customerId
})
RETURN o.orderId AS orderId
ORDER BY orderId;
~~~

Với **tenantId = 'shop-a'** và **customerId = 'C-1'**, kết quả chuẩn là:

~~~text
O-1
O-2
~~~

Đây là **golden result** thể hiện hợp đồng nghiệp vụ, không phải chỉ là “ảnh chụp” từ phiên bản cũ được mặc định coi là luôn đúng. Nếu query cũ có lỗi đã biết, nhóm phải ghi rõ kỳ vọng đã được chủ nghiệp vụ xác nhận trước khi xây regression test.

### 4.3. Migration: tạo relationship từ property cũ

~~~cypher
MATCH (c:DemoRegressionCustomer)
MATCH (o:DemoRegressionOrder)
WHERE c.tenantId = o.tenantId
  AND c.customerId = o.legacyCustomerId
MERGE (c)-[:DEMO_REG_PLACED]->(o);
~~~

**MERGE** được áp dụng với hai endpoint đã xác định. Nếu chạy lại trên cùng graph mà không có thao tác nào khác tạo liên kết trùng, nó sẽ khớp relationship đã có thay vì tạo thêm.

Ở hệ thống thực, không nên quét mọi Customer và Order bằng mẫu này trên hàng triệu bản ghi. Cần lập kế hoạch **batch**, dùng index/constraint tìm endpoint theo business key, đối soát số hàng và theo dõi các bản ghi **không tìm thấy Customer** trước khi thực hiện migration.

### 4.4. Query mới và các assertion quan trọng

~~~cypher
MATCH (c:DemoRegressionCustomer {
  tenantId: $tenantId,
  customerId: $customerId
})-[:DEMO_REG_PLACED]->(o:DemoRegressionOrder)
RETURN o.orderId AS orderId
ORDER BY orderId;
~~~

Với bộ dữ liệu đã tạo, các assertion tối thiểu:

| Phép kiểm thử | Kỳ vọng |
|---|---|
| **shop-a / C-1** | **[O-1, O-2]** |
| **shop-a / C-2** | **[O-3]** |
| **shop-b / C-1** | **[O-4]** |
| Số Order toàn fixture | **4** |
| Số **DEMO_REG_PLACED** sau migration | **4** |
| Số relationship sau migration lần hai | **Vẫn 4** |
| Quan hệ nối hai tenant khác nhau | **0** |

Đối soát chéo tenant:

~~~cypher
MATCH (c:DemoRegressionCustomer)-[r:DEMO_REG_PLACED]->
      (o:DemoRegressionOrder)
WHERE c.tenantId <> o.tenantId
RETURN count(r) AS crossTenantRelationships;
~~~

Kết quả phải là **0**. Ngoài ra phải kiểm tra chiều **Customer → Order**, loại relationship và việc hai Order khác nhau có ID giống nhau trong tenant khác có được tách biệt đúng không.

### 4.5. Tạo một lỗi có chủ đích để xác nhận test thực sự bắt được

Thử thay query mới bằng:

~~~cypher
// CỐ Ý SAI: bỏ điều kiện tenant, có thể trả lẫn nhiều tenant.
MATCH (c:DemoRegressionCustomer {customerId: $customerId})
      -[:DEMO_REG_PLACED]->(o:DemoRegressionOrder)
RETURN o.orderId AS orderId
ORDER BY orderId;
~~~

Với **customerId = 'C-1'**, query sai trả thêm **O-4** từ shop-b. Nếu bộ test vẫn báo pass, bộ test đang thiếu assertion quan trọng hoặc fixture chưa đủ trường hợp biên.

Trong một hệ thống phân tán nhiều tenant, **test phân quyền/tenant isolation** có thể quan trọng hơn một phép so sánh tổng số node.

## 5. Các cấp kiểm thử nên kết hợp

| Cấp | Kiểm tra gì? | Dùng công cụ nào? | Ranh giới |
|---|---|---|---|
| **Unit test** | Chuẩn hóa ID, mapper DTO, dựng tham số Cypher, chính sách retry | JUnit, Mockito | Không chứng minh query Cypher thực chạy đúng |
| **Cypher integration test** | Pattern, index, constraint, transaction, kết quả graph | Neo4j thực + Java Driver | Chi phí khởi động/seed cao hơn mock |
| **Repository/service test** | SDN mapping, custom query, transaction boundary | Spring Test + Neo4j/Testcontainers | Cần cấu hình Spring và phiên bản tương thích |
| **Migration test** | Chuyển mô hình, đối soát trước/sau, chạy lại an toàn | Snapshot/fixture + Cypher migration | Phải giữ dữ liệu từ trạng thái cũ |
| **Contract/API test** | Cùng request trả cùng ý nghĩa, trạng thái HTTP, phân quyền | API test + Neo4j test DB | Thêm phụ thuộc các service liên quan |
| **Concurrency test** | Lost update, deadlock, idempotency và uniqueness | Nhiều transaction, latch/barrier | Lịch chạy không hoàn toàn xác định |
| **Performance regression** | p95, DB Hits, Rows, memory, timeout | EXPLAIN/PROFILE + tải đại diện | Kết quả chịu ảnh hưởng cache và hạ tầng |
| **Upgrade/cluster test** | Routing, bookmark, failover, tương thích plugin | Môi trường cluster thử nghiệm | Một container đơn không mô phỏng đủ cluster |

Không nhất thiết mọi thay đổi phải chạy một bộ end-to-end rất lớn ngay ở mỗi lần save code. Một quy trình hiệu quả dùng **test nhỏ, nhanh** trên mỗi commit; **integration** ở pull request; **migration, hiệu năng, cluster** ở cổng kiểm tra trước khi phát hành.

## 6. JUnit 5, Neo4j Java Driver và Testcontainers

### 6.1. Vì sao cần database thật?

Mock **Session**, **Transaction** hoặc repository có thể giúp kiểm tra logic Java, nhưng nó không tái tạo chính xác:

- Cách Neo4j khớp pattern Cypher và chiều relationship.
- **MERGE**, uniqueness constraint, null semantics, transaction rollback.
- Tác động của index, query planner hoặc thông báo lỗi của server.
- Hành vi khác nhau giữa các phiên bản Cypher và Neo4j.

**Testcontainers** có thể khởi động Neo4j trong container Docker với image được chọn, tạo một database test gần với môi trường thực hơn. Cần Docker/engine được hỗ trợ tại máy chạy test hoặc CI.

Trong **Testcontainers Java 2.x**, module Neo4j có artifact **org.testcontainers:testcontainers-neo4j** và class **org.testcontainers.neo4j.Neo4jContainer**. Với **Testcontainers 1.x**, artifact và package có thể khác. Hãy đồng bộ **Testcontainers, JUnit 5 và Neo4j Java Driver** theo dependency management của dự án, không trộn import của hai major version.

Ví dụ Gradle (các version cụ thể do dự án khóa bằng version catalog/BOM và kiểm tra tương thích):

~~~groovy
dependencies {
    implementation("org.neo4j.driver:neo4j-java-driver")
    testImplementation("org.junit.jupiter:junit-jupiter")
    testImplementation("org.testcontainers:testcontainers-neo4j")
}

tasks.test {
    useJUnitPlatform()
}
~~~

Không thêm cả **Testcontainers 1.x** và **2.x** trong cùng classpath. Mặc định test trên Neo4j **Community** là đủ cho nhiều câu Cypher thông thường; những tính năng Enterprise-only cần image, giấy phép và môi trường kiểm thử được phép sử dụng.

### 6.2. Một integration test có thể tái sử dụng

Đoạn Java minh họa **JUnit 5 + Testcontainers 2.x + Java Driver hiện đại**, chạy trên image **neo4j:5.26**; có thể đổi qua property **neo4j.test.image** để chạy trên version mục tiêu. Khi nâng version, khóa đúng patch hoặc image digest thay vì phụ thuộc tag **latest**.

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.neo4j.driver.AuthTokens;
import org.neo4j.driver.Driver;
import org.neo4j.driver.GraphDatabase;
import org.neo4j.driver.SessionConfig;
import org.testcontainers.neo4j.Neo4jContainer;

class ModelMigrationIT {
    private static final String PASSWORD = "test-only-password";
    private static final String IMAGE =
        System.getProperty("neo4j.test.image", "neo4j:5.26");

    private static final Neo4jContainer<?> NEO4J =
        new Neo4jContainer<>(IMAGE).withAdminPassword(PASSWORD);
    private static Driver driver;

    private static final String OLD_QUERY = """
        MATCH (o:DemoRegressionOrder {
          tenantId: $tenant, legacyCustomerId: $customer
        })
        RETURN o.orderId AS id ORDER BY id
        """;
    private static final String NEW_QUERY = """
        MATCH (c:DemoRegressionCustomer {
          tenantId: $tenant, customerId: $customer
        })-[:DEMO_REG_PLACED]->(o:DemoRegressionOrder)
        RETURN o.orderId AS id ORDER BY id
        """;
    private static final String MIGRATION = """
        MATCH (c:DemoRegressionCustomer)
        MATCH (o:DemoRegressionOrder)
        WHERE c.tenantId = o.tenantId
          AND c.customerId = o.legacyCustomerId
        MERGE (c)-[:DEMO_REG_PLACED]->(o)
        """;

    @BeforeAll
    static void startServer() {
        NEO4J.start();
        driver = GraphDatabase.driver(
            NEO4J.getBoltUrl(),
            AuthTokens.basic("neo4j", PASSWORD)
        );
        driver.verifyConnectivity();
        try (var session = driver.session(
                SessionConfig.forDatabase("neo4j"))) {
            session.run("""
                CREATE CONSTRAINT demo_reg_customer_key IF NOT EXISTS
                FOR (c:DemoRegressionCustomer)
                REQUIRE (c.tenantId, c.customerId) IS UNIQUE
                """).consume();
            session.run("""
                CREATE CONSTRAINT demo_reg_order_key IF NOT EXISTS
                FOR (o:DemoRegressionOrder)
                REQUIRE (o.tenantId, o.orderId) IS UNIQUE
                """).consume();
        }
    }

    @AfterAll
    static void stopServer() {
        if (driver != null) driver.close();
        NEO4J.stop();
    }

    @BeforeEach
    void resetFixture() {
        try (var session = driver.session(
                SessionConfig.forDatabase("neo4j"))) {
            session.executeWriteWithoutResult(tx -> {
                // Chỉ xóa node mang nhãn đánh dấu của fixture.
                tx.run("""
                    MATCH (n:DemoRegression)
                    DETACH DELETE n
                    """).consume();
                tx.run("""
                    CREATE
                      (:DemoRegression:DemoRegressionCustomer {
                        tenantId:'shop-a', customerId:'C-1'
                      }),
                      (:DemoRegression:DemoRegressionCustomer {
                        tenantId:'shop-a', customerId:'C-2'
                      }),
                      (:DemoRegression:DemoRegressionCustomer {
                        tenantId:'shop-b', customerId:'C-1'
                      }),
                      (:DemoRegression:DemoRegressionOrder {
                        tenantId:'shop-a', orderId:'O-1',
                        legacyCustomerId:'C-1'
                      }),
                      (:DemoRegression:DemoRegressionOrder {
                        tenantId:'shop-a', orderId:'O-2',
                        legacyCustomerId:'C-1'
                      }),
                      (:DemoRegression:DemoRegressionOrder {
                        tenantId:'shop-a', orderId:'O-3',
                        legacyCustomerId:'C-2'
                      }),
                      (:DemoRegression:DemoRegressionOrder {
                        tenantId:'shop-b', orderId:'O-4',
                        legacyCustomerId:'C-1'
                      })
                    """).consume();
            });
        }
    }

    private List<String> orders(String query, String tenant, String customer) {
        try (var session = driver.session(
                SessionConfig.forDatabase("neo4j"))) {
            return session.executeRead(tx -> tx.run(
                query, Map.of("tenant", tenant, "customer", customer)
            ).list(row -> row.get("id").asString()));
        }
    }

    private void migrate() {
        try (var session = driver.session(
                SessionConfig.forDatabase("neo4j"))) {
            session.executeWriteWithoutResult(
                tx -> tx.run(MIGRATION).consume());
        }
    }

    private long relationshipCount() {
        try (var session = driver.session(
                SessionConfig.forDatabase("neo4j"))) {
            return session.executeRead(tx -> tx.run("""
                MATCH (:DemoRegressionCustomer)
                      -[r:DEMO_REG_PLACED]->
                      (:DemoRegressionOrder)
                RETURN count(r) AS total
                """).single().get("total").asLong());
        }
    }

    @Test
    void newModelKeepsBusinessAnswers() {
        List<String> before = orders(OLD_QUERY, "shop-a", "C-1");
        assertEquals(List.of("O-1", "O-2"), before);

        migrate();

        assertEquals(before, orders(NEW_QUERY, "shop-a", "C-1"));
        assertEquals(List.of("O-3"), orders(NEW_QUERY, "shop-a", "C-2"));
        assertEquals(List.of("O-4"), orders(NEW_QUERY, "shop-b", "C-1"));
    }

    @Test
    void migrationIsIdempotent() {
        migrate();
        migrate();
        assertEquals(4L, relationshipCount());
    }
}
~~~

**Cách đọc code:**

1. Container mang phiên bản Neo4j được chỉ rõ; không sử dụng database phát triển chung.
2. **@BeforeEach** tạo lại fixture từ trạng thái sạch nên test không phụ thuộc thứ tự chạy.
3. Ràng buộc uniqueness là một phần schema thật của Neo4j, không phải mock.
4. Test đầu so sánh **kết quả nghiệp vụ cũ/mới** và kiểm tra cả tenant trùng Customer ID.
5. Test thứ hai yêu cầu migration **idempotent**, chạy hai lần vẫn chỉ có bốn relationship.
6. **Session** được đóng sau từng công việc, **Driver** được dùng lại trong class test.

Code minh họa giả định các test trong class chạy **tuần tự** và không có test khác cùng sửa fixture trong container này. Nếu bật JUnit parallel execution, hãy **tách database/container mỗi test** hoặc thiết kế isolation phù hợp. Đừng xóa dữ liệu thật bằng **MATCH (n) DETACH DELETE n** trong môi trường dùng chung.

### 6.3. Chạy cùng test trên hai phiên bản

Ví dụ với Gradle (minh họa; thay tag theo release đã được dự án chấp thuận):

~~~bash
./gradlew test -Dneo4j.test.image=neo4j:5.26
./gradlew test -Dneo4j.test.image=neo4j:2026.10.2
~~~

Để property hệ thống tới JVM chạy test, cấu hình Gradle Test task hoặc truyền property qua cơ chế phù hợp của dự án. Nếu Gradle không chuyển **-Dneo4j.test.image** vào test JVM theo cách gọi đang dùng, thiết lập **systemProperty** rõ ràng trong task **test**. Trong CI, chạy ma trận riêng cho từng image; không chạy hai lệnh trên cùng cơ sở dữ liệu đang mang trạng thái chưa sạch.

**Lưu ý:** chạy test trên database mới của hai phiên bản **chưa thay thế** bài test **migrate dữ liệu đã có** từ version cũ. Bài kiểm tra nâng cấp phải có một nhánh riêng phục hồi snapshot cũ rồi chạy quá trình upgrade thật.

## 7. Thiết kế fixture để phát hiện lỗi, không chỉ làm test dễ pass

Một fixture tối thiểu nhưng có giá trị phải chứa những trường hợp mà logic sai sẽ **cho kết quả khác**:

| Tình huống | Vì sao phải có? |
|---|---|
| Hai Customer khác tenant trùng **customerId** | Bắt lỗi thiếu tenant scope |
| Hai Order của cùng Customer | Bắt lỗi chỉ lấy một Order |
| Một Customer không có Order | Kiểm tra kết quả rỗng, OPTIONAL MATCH/null |
| Một Order không tìm được Customer | Phát hiện mất liên kết trong migration |
| Relationship sai hướng | Bắt lỗi nhầm **->** với **<-** |
| Hai đường tới cùng node | Phát hiện query không dùng **DISTINCT** khi nghiệp vụ yêu cầu |
| ID có số 0 đầu, Unicode và ký tự đặc biệt | Bắt lỗi chuẩn hóa hoặc ép kiểu mã định danh |
| Timestamp/ngày không có hoặc ở ranh giới múi giờ | Bắt lỗi mặc định null và chuyển đổi thời gian |
| Hai request cùng idempotency key | Bắt lỗi tạo trùng và xử lý retry |

Với test tuyến/đường đi, hãy có một đồ thị nhỏ cho phép đối chiếu **số hop**, hướng relationship và tổng trọng số nếu dùng GDS. Nếu kết quả có nhiều đường đồng hạng, assertion phải so sánh **tập các đường hợp lệ** hoặc các ràng buộc cần thiết, không cố định một đường khi thuật toán không hứa thứ tự tie-break.

### 7.1. Test dữ liệu âm tính

Không chỉ kiểm tra những bản ghi hợp lệ. Ví dụ thử tạo Order trùng business key:

~~~cypher
CREATE (:DemoRegression:DemoRegressionOrder {
  tenantId: 'shop-a', orderId: 'O-1', legacyCustomerId: 'C-1'
});
~~~

Nếu fixture đã có O-1 và uniqueness constraint đang hiệu lực, câu lệnh phải **thất bại**. Đây là test âm tính quan trọng: một hệ thống không tự động đúng chỉ vì truy vấn đọc cho kết quả như mong đợi.

Tương tự, kiểm tra đầu vào thiếu khóa, property sai kiểu, mối quan hệ xuyên tenant và cập nhật đồng thời. Test cần assert **loại lỗi hoặc hậu điều kiện**, tránh phụ thuộc nguyên văn thông báo có thể thay đổi theo phiên bản.

### 7.2. Kiểm tra invariant thay vì chỉ so ảnh chụp

Các invariant có thể dùng lâu dài:

- Mỗi **(tenantId, orderId)** có tối đa một Order.
- Mỗi Order có đúng Customer nghiệp vụ tương ứng khi migration hoàn tất.
- Relationship **DEMO_REG_PLACED** phải có chiều Customer → Order.
- Không có relationship nối hai tenant khác nhau.
- Chạy migration lần thứ hai không làm tăng số node/relationship.
- API tạo đơn được retry với cùng key không phát sinh thêm side effect.

Chú ý sự khác biệt giữa **“tối đa một”** và **“đúng một”**: uniqueness constraint có thể bảo đảm tính duy nhất, nhưng chưa đủ để buộc mọi Order phải có Customer relationship.

## 8. Kiểm thử rollback, transaction và lỗi khi chạy nửa chừng

### 8.1. Một migration lỗi không nhất thiết rollback toàn bộ batch trước

Nếu migration chạy với **CALL { ... } IN TRANSACTIONS**, từng batch có thể commit riêng. Batch thứ ba gặp lỗi không tự rollback hai batch đầu đã commit. Vì vậy phải kiểm tra:

1. Có thể chạy lại migration **an toàn** sau khi sửa dữ liệu lỗi không?
2. Có phát sinh relationship trùng hoặc node rác sau lần chạy lại không?
3. Các bản ghi bị bỏ qua có được báo cáo thay vì im lặng mất dữ liệu không?
4. Ứng dụng có thể tạm thời đọc cả mô hình cũ và mới trong giai đoạn chuyển tiếp không?

Đừng viết test chỉ chạy migration một lần trên dữ liệu sạch; đó chưa phải bằng chứng có thể phục hồi sau lỗi giữa quá trình.

### 8.2. Tranh chấp, khóa và lost update

Với transaction đồng thời, cần thử ít nhất:

- Hai giao dịch cùng **MERGE** node theo business key có uniqueness constraint.
- Hai giao dịch cùng tăng một counter và bảo đảm không mất cập nhật.
- Hai transaction sửa các node theo thứ tự ngược, có thể gặp deadlock.
- Retry sau transient error không thực hiện side effect ngoài database hai lần.

Những test này nên dùng **CountDownLatch/CyclicBarrier** hoặc cơ chế điều phối có kiểm soát và có timeout. Không cố để các test deadlock bất định chạy trên CI vô thời hạn. Cần xác nhận trạng thái cuối **đúng và không trùng** sau tất cả lần thử, thay vì chỉ kiểm tra số exception.

### 8.3. Không dùng Testcontainers đơn lẻ để khẳng định cluster behavior

Một container Neo4j độc lập có thể kiểm tra **Cypher**, constraint, Java Driver và transaction cơ bản. Nó **không** tái tạo:

- Routing table của cluster nhiều server.
- Lag giữa reader/writer hoặc bookmark read-your-writes qua replica.
- Bầu lại leader và định tuyến lại sau failover.
- Topology, quyền Enterprise và tình huống phục hồi của cụm production.

Các tính năng đó cần test topology chuyên biệt và môi trường có cấu hình tương ứng. Đừng ghi “đã kiểm thử failover” nếu chỉ restart một container standalone.

## 9. Hồi quy hiệu năng: kết quả đúng nhưng chậm hơn

### 9.1. EXPLAIN và PROFILE đo những gì?

~~~cypher
EXPLAIN
MATCH (o:DemoRegressionOrder {
  tenantId: $tenantId,
  legacyCustomerId: $customerId
})
RETURN o.orderId AS orderId;
~~~

~~~cypher
PROFILE
MATCH (c:DemoRegressionCustomer {
  tenantId: $tenantId,
  customerId: $customerId
})-[:DEMO_REG_PLACED]->(o:DemoRegressionOrder)
RETURN o.orderId AS orderId;
~~~

**EXPLAIN** chỉ tạo kế hoạch, **không chạy truy vấn**. **PROFILE** chạy truy vấn thật và cung cấp số liệu như **Rows**, **DB Hits**, bộ nhớ/toán tử khi runtime hỗ trợ. Nếu dùng **PROFILE trên một truy vấn ghi**, dữ liệu vẫn **bị thay đổi**; không profile lệnh migration trên production khi chưa đánh giá tác động.

Các điểm cần theo dõi:

| Chỉ số | Câu hỏi |
|---|---|
| **Rows** | Có tạo số hàng trung gian tăng đột biến do fan-out? |
| **DB Hits** | Đường truy cập mới phải đọc nhiều dữ liệu hơn không? |
| **Index Seek/Scan** | Query tìm node bằng index hay quét lượng lớn nhãn? |
| **Expand / VarLengthExpand** | Duyệt relationship đúng loại/hướng và bounded depth không? |
| **Estimated Rows vs Rows** | Planner có ước lượng sai độ chọn lọc nghiêm trọng không? |
| **Memory / page cache** | Có pressure về bộ nhớ/I/O không? |
| **p50/p95/p99 latency** | Người dùng có bị chậm hơn ở tải đại diện không? |

**Không so sánh nguyên văn execution plan** từng ký tự giữa hai Neo4j version rồi kết luận một version sai. Planner có thể đổi tên toán tử, thứ tự thực thi và runtime mà vẫn cho kết quả đúng và nhanh hơn. Regression test nên kiểm tra **hành vi**, **budget hiệu năng** và những đặc điểm quan trọng như tránh full scan trên bảng rất lớn.

### 9.2. Phép đo phải tương đương

- Dùng cùng tập dữ liệu về **kích thước, phân phối và độ chọn lọc**.
- Dùng cùng các tham số (mã phổ biến và mã hiếm; không chỉ một ví dụ đẹp).
- Giữ tương đương môi trường CPU/RAM/disk, cấu hình, số kết nối và tải nền.
- Phân biệt **cold cache** với **warm cache**; chạy đủ lượt làm nóng.
- Chạy nhiều mẫu và tính phân phối; không so thời gian của một lần chạy duy nhất.
- Tách tác động **migration schema/index** khỏi tác động **upgrade server** nếu có thể.

Tạo hoặc xóa index/constraint có thể kích hoạt lập lại kế hoạch, và thống kê dữ liệu mới cũng ảnh hưởng planner. Vì thế, query plan đổi sau schema migration **không tự đồng nghĩa** lỗi hiệu năng; phải đo thực tế.

### 9.3. Đặt ngưỡng hồi quy có ý nghĩa

Ví dụ chính sách nhóm (các ngưỡng cần được dự án quyết định, không phải chuẩn Neo4j):

| Kiểm tra | Điều kiện chấp nhận minh họa |
|---|---|
| **Tính đúng** | 100% invariant bắt buộc pass |
| **p95 API truy vấn trọng tâm** | Không vượt SLO đã cam kết |
| **DB Hits ở query định danh** | Không tăng bất thường khi dữ liệu/phân phối cố định |
| **Thời gian migration** | Nằm trong cửa sổ vận hành được cấp |
| **Dung lượng và bộ nhớ** | Không vượt ngân sách hạ tầng |
| **Lỗi transient / retry** | Không tăng quá mức chấp nhận |

Với tập fixture chỉ bảy node, **DB Hits và thời gian** chưa có giá trị để đánh giá hiệu năng production; hãy dùng thêm một dataset **lớn, đại diện và ẩn danh** cho bộ performance regression riêng.

## 10. Nâng cấp phiên bản Neo4j và Cypher: các kiểm tra bắt buộc

### 10.1. Khóa các thành phần của môi trường

Một **test matrix** nên ghi rõ:

| Thành phần | Trước thay đổi | Sau thay đổi |
|---|---|---|
| **Neo4j Server** | Phiên bản đang chạy | Phiên bản đích, cố định tag/patch |
| **Cypher language** | Cypher 5 hoặc chế độ hiện có | Cypher 5 / Cypher 25 nếu được hỗ trợ |
| **Java Driver** | Major/minor trước | Phiên bản mục tiêu tương thích |
| **Spring Data Neo4j** | Phiên bản framework | Phiên bản mục tiêu |
| **APOC / GDS** | Plugin và version tương thích | Plugin khớp server đích |
| **Schema** | Index/constraint hiện có | Schema sau migration |
| **Data** | Snapshot/fixture cũ | Dữ liệu sau migration thực tế |

Từ **Neo4j 2025.06**, server hỗ trợ chọn **Cypher 5** hoặc **Cypher 25**. Không viết **CYPHER 25** trong câu truy vấn chạy trên server đời cũ không hỗ trợ nó.

~~~cypher
// Chạy trên server hỗ trợ tùy chọn ngôn ngữ này.
CYPHER 5
MATCH (n:DemoRegressionOrder)
RETURN count(n) AS total;
~~~

~~~cypher
// Chỉ chạy trên Neo4j 2025.06+ hỗ trợ Cypher 25.
CYPHER 25
MATCH (n:DemoRegressionOrder)
RETURN count(n) AS total;
~~~

Khi thay đổi cả server và default Cypher language, khó xác định lỗi phát sinh do yếu tố nào. Do đó nên thử trước với **cùng ngôn ngữ Cypher** trên server cũ/mới (nếu có thể), rồi tách một lượt để kiểm tra việc chuyển **Cypher 5 → Cypher 25**.

### 10.2. Đừng mặc định nâng cấp có thể downgrade

Theo hướng dẫn vận hành Neo4j, **downgrade không được hỗ trợ**. Kế hoạch rollback cho một database đã nâng cấp cần sử dụng **backup/snapshot trước nâng cấp** và quy trình **restore** đã được tập dượt; không đơn giản cài lại binary cũ rồi mở database mới.

Với lộ trình từ Neo4j cũ sang các bản năm 2025–2026, cần tuân thủ **LTS checkpoint** và hướng dẫn cụ thể cho version nguồn/đích. Ví dụ đường nâng cấp từ các bản trước **Neo4j 5.26 LTS** tới 2025–2026 phải đi qua checkpoint tương ứng, theo tài liệu chính thức. Không bỏ qua bước chỉ vì một test container mới khởi động được.

### 10.3. Bài thử upgrade khác bài thử khởi tạo mới

**Test trên database mới:** tạo fixture từ đầu trong image Neo4j đích, chạy câu Cypher.

**Test upgrade thực:** khởi tạo/khôi phục một **database được tạo bởi phiên bản nguồn**, chạy nâng cấp theo quy trình hỗ trợ, sau đó:

- Xác nhận database và schema đã sẵn sàng, index ở trạng thái phù hợp.
- Chạy **cùng golden queries** và các invariant.
- Chạy migration mô hình nếu có, kiểm tra idempotency.
- Kiểm tra driver, SDN, plugin, các thủ tục được phép, định tuyến theo topology.
- Kiểm tra hiệu năng, log, cảnh báo deprecated/removed.
- Thử phương án **restore backup trước upgrade** trên môi trường diễn tập.

Kết quả thành công trên **hai container mới độc lập** không đủ để xác nhận **store format, dữ liệu lịch sử hoặc đường nâng cấp**.

## 11. Quy trình an toàn khi đổi mô hình dữ liệu

Một phương pháp giảm rủi ro là **expand → migrate → verify → contract**:

~~~mermaid
flowchart LR
  A["Baseline: query cũ + invariant"] --> B["Expand: thêm schema/đường đọc mới"]
  B --> C["Migrate: chuyển dữ liệu theo batch"]
  C --> D{"Verify: đối soát + regression"}
  D -->|"PASS"| E["Contract: bỏ đường cũ theo kế hoạch"]
  D -->|"FAIL"| F["Dừng rollout, sửa hoặc restore theo phương án"]
~~~

### 11.1. Baseline

Trước khi đổi:

1. Định nghĩa rõ câu hỏi nghiệp vụ, tập dữ liệu vàng và các invariant.
2. Lưu query cũ, kết quả mong đợi, phiên bản và schema.
3. Ghi p95/DB Hits làm baseline cho query quan trọng.
4. Bảo đảm có môi trường thử nghiệm và dữ liệu có thể khôi phục.

### 11.2. Expand

Thêm schema mới theo hướng **tương thích tạm thời**, ví dụ thêm relationship **DEMO_REG_PLACED** nhưng chưa xóa **legacyCustomerId**. Nếu áp dụng production, lưu ý migration kết quả có thể có phần trăm dữ liệu mới chưa đủ trong giai đoạn chuyển tiếp.

### 11.3. Migrate

Chạy migration có thể lặp lại, thường chia batch trên graph lớn. Đối soát số node đã chuyển, số quan hệ tạo thành, bản ghi không tìm được endpoint và lỗi vi phạm constraint. Nếu hệ thống vẫn nhận ghi trong thời gian migration, cần cơ chế **dual-write** hoặc **change capture** có kiểm soát để không bỏ sót thay đổi phát sinh trong lúc chạy.

### 11.4. Verify

Trước khi chuyển tất cả truy vấn sang mô hình mới:

- So sánh kết quả query cũ/mới trên nhiều tenant và tập dữ liệu đại diện.
- Chạy lại migration để xác nhận idempotency.
- Kiểm tra ràng buộc định danh, relationship hướng/loại và các bất biến dữ liệu.
- Chạy test đồng thời và performance regression.
- Kiểm tra hành vi Java Driver, SDN repository mapping và API.

### 11.5. Contract

Chỉ xóa property cũ, index cũ hoặc nhánh code cũ sau khi có chứng cứ query mới đã bao phủ nghiệp vụ, không còn reader/worker/consumer phụ thuộc mô hình cũ và thời gian quan sát được đáp ứng. **Không gộp “thêm quan hệ mới” và “xóa trường cũ” vào một deploy lớn** khi hệ thống cần rollout nhiều bước.

**Lưu ý:** dù mỗi bước đều có test, việc migration production và thay schema có thể cần kế hoạch backup/restore riêng; transaction trong Neo4j không rollback những thay đổi đã commit từ nhiều batch.

## 12. Vận hành bộ kiểm thử trong CI/CD

Ví dụ pipeline khái niệm:

~~~text
Pull request:
  - Compile + static checks
  - Unit tests cho mapping/validation
  - Testcontainers: Cypher + constraint + migration nhỏ
  - Tests idempotency / tenant isolation

Release candidate:
  - Matrix phiên bản Neo4j/driver/Cypher
  - Diễn tập upgrade snapshot dữ liệu cũ
  - Contract/API tests
  - Performance regression với dataset đại diện
  - Kiểm tra plugin, security, cluster nếu hệ thống dùng

Production deployment:
  - Backup và phương án restore đã thử
  - Expand/migrate/verify/contract theo từng bước
  - Theo dõi lỗi, latency, query logs đã ẩn thông tin nhạy cảm
  - Dừng rollout nếu invariant hoặc SLO bị vi phạm
~~~

**Nguyên tắc CI:**

- Mỗi job có database/container riêng hoặc cơ chế namespace thực sự tách biệt.
- Pin Neo4j image và các dependency; ghi version vào test report.
- Fixture bất biến hoặc được tạo lại trước test; không dựa vào thứ tự test.
- Artifact khi test fail gồm seed đã ẩn danh, stack trace, truy vấn và các tham số không nhạy cảm.
- Với benchmark, chạy trên runner tương đương, không dùng ngưỡng quá nhạy với nhiễu.
- Không phát sinh yêu cầu ghi hay xóa vào production từ bài integration test.

### 12.1. Mẫu báo cáo cho một bài regression

| Trường | Giá trị cần ghi |
|---|---|
| **Test ID** | Ví dụ REG-ORDER-MIGRATION-001 |
| **Source/target version** | Neo4j, Java Driver, Cypher mode |
| **Fixture** | Tên dữ liệu, hash/checksum hoặc commit tham chiếu |
| **Thay đổi** | Migration script, thay query hay nâng binary |
| **Expected** | Kết quả nghiệp vụ và invariant |
| **Actual** | Kết quả và chênh lệch |
| **Performance** | p95, DB Hits, Rows, tải, cỡ dữ liệu |
| **Status** | PASS / FAIL / BLOCKED |
| **Rollback evidence** | Backup nào đã được diễn tập restore |

Không yêu cầu mọi test phải có benchmark; thông tin hiệu năng có thể chỉ bắt buộc ở **performance suite**. Quan trọng nhất là mỗi lỗi được ghi lại bằng một test **thực sự fail trên phiên bản lỗi và pass sau khi sửa**.

## 13. Các lỗi thường gặp khi viết kiểm thử Neo4j

1. **Chỉ test với mock repository.** Mock không phát hiện Cypher sai chiều, null semantics hoặc lỗi constraint của server.
2. **Dùng dữ liệu có sẵn của developer.** Test phụ thuộc máy và thứ tự chạy, khó tái tạo trên CI.
3. **Không pin Neo4j/driver/plugin versions.** Lỗi chỉ xảy ra ở một bản cụ thể nhưng mất thông tin chứng cứ.
4. **So sánh số lượng thay vì tập node/relationship.** Hai kết quả cùng count vẫn có thể sai tenant.
5. **Fixture quá sạch.** Không có trùng ID giữa tenant, thiếu property, relationship sai hướng nên code lỗi vẫn pass.
6. **Sửa assertion theo kết quả mới mà chưa hỏi nghiệp vụ.** Test biến lỗi hồi quy thành “hành vi được chấp nhận”.
7. **Đặt ORDER BY không có rồi assert thứ tự tuyệt đối.** Cypher không bảo đảm thứ tự trả về nếu không yêu cầu rõ.
8. **Assert exact error message hoặc exact query plan.** Hai thứ có thể đổi qua phiên bản trong khi ý nghĩa vẫn đúng.
9. **Quên test migration lần hai.** Các thao tác không lũy đẳng tạo node/relationship trùng khi retry.
10. **Dùng Thread.sleep để tạo race condition.** Test chập chờn do scheduler/tốc độ CI.
11. **Dùng PROFILE trên lệnh ghi ở production.** PROFILE thực thi truy vấn, không chỉ quan sát kế hoạch.
12. **Chỉ thử image mới, không thử upgrade dữ liệu cũ.** Bỏ sót store format và dữ liệu lịch sử.
13. **Mặc định Testcontainers standalone mô phỏng cluster.** Không kiểm tra replica lag, bookmark và failover thật.
14. **Cho rằng nâng binary có thể downgrade để rollback.** Neo4j yêu cầu phương án restore thích hợp.
15. **Bỏ qua index POPULATING hoặc FAILED.** Test timing/performance có thể bị hiểu sai.

## 14. Bài tập vận dụng

### Bài 1 — Tạo minimal reproducible case

Một API sau migration trả cả đơn của tenant shop-b khi tra Customer C-1 ở shop-a. Hãy viết ba node Customer/Order tối thiểu và hai câu Cypher đủ tạo lại lỗi. Nêu giá trị tham số và assertion sẽ thất bại nếu query bỏ **tenantId**.

### Bài 2 — Golden test và migration idempotent

Chạy fixture mục 4, lưu kết quả query cũ, thực thi migration sang **DEMO_REG_PLACED**, so sánh query mới, rồi chạy migration lần hai. Hãy giải thích vì sao chỉ có bốn relationship cuối cùng là điều kiện cần nhưng **chưa đủ** để chứng minh đúng tenant/hướng.

### Bài 3 — Tìm lỗi trong bộ test

Một test chỉ kiểm tra **count(Order) = 4** trước/sau migration. Hãy nêu ít nhất bốn lỗi dữ liệu mà test đó không phát hiện được và đề xuất các invariant tương ứng.

### Bài 4 — Regression khi đổi Cypher language

Một ứng dụng nâng từ Neo4j 5.26 lên bản 2026 hỗ trợ Cypher 5 và Cypher 25. Hãy thiết kế ma trận chạy cùng query ở hai cấu hình Cypher, phân biệt lỗi cú pháp, thay đổi hành vi, kết quả và hiệu năng. Tại sao phải cố định language mode trong phép so sánh đầu tiên?

### Bài 5 — Tranh chấp và retry

Hai worker cùng tạo Order có business key **(tenantId, orderId)**. Đề xuất integration test có uniqueness constraint, đồng thời cố ý gửi hai transaction cạnh tranh. Sau khi kết thúc, cần kiểm tra những điều kiện nào để chứng minh không có node trùng và không có side effect lặp?

### Bài 6 — Diễn tập upgrade

Bạn có snapshot của Neo4j trước upgrade, phiên bản server đích, bộ Java Driver/SDN và APOC mới. Hãy trình bày tuần tự những việc cần kiểm tra từ phục hồi snapshot, khởi động theo hướng dẫn, tạo index, chạy golden tests cho tới xác minh rollback bằng backup cũ.

### Bài 7 — Hồi quy hiệu năng

Một truy vấn vẫn trả chính xác cùng tập Order nhưng p95 tăng gấp ba sau khi thêm relationship. Hãy liệt kê cách thu thập **PROFILE**, số hàng trung gian, **DB Hits**, index và phân phối dữ liệu để phân biệt lỗi planner, fan-out và thay đổi môi trường test.

## 15. Ghi nhớ

Để kiểm soát hồi quy khi thay đổi **mô hình property graph** hoặc **phiên bản Neo4j**, phải bắt đầu bằng **một lỗi có thể tái tạo**, một **fixture có khả năng làm lộ lỗi** và những **invariant nghiệp vụ rõ ràng**. Kiểm thử tốt cần bao phủ cả node, relationship, chiều liên kết, loại, khóa định danh, transaction, tenant scope và hành vi gọi lại.

Java Driver, JUnit 5 và Testcontainers giúp chạy Cypher trên Neo4j thật trong môi trường lặp lại được. Nhưng một container mới không thay thế được thử nghiệm **migrate store cũ, topology cluster hay hiệu năng tải lớn**. Trước triển khai, hãy chạy **golden queries, migration idempotency, constraint checks, regression về hành vi và performance**, đồng thời chuẩn bị **backup/restore** vì nâng cấp Neo4j không hỗ trợ downgrade đơn giản.

### Tài liệu tham khảo chính thức

- [Neo4j Cypher Manual – MERGE và xử lý dữ liệu](https://neo4j.com/docs/cypher-manual/current/clauses/merge/)
- [Neo4j Cypher Manual – Constraints](https://neo4j.com/docs/cypher-manual/current/constraints/)
- [Neo4j Cypher Manual – EXPLAIN/PROFILE và execution plans](https://neo4j.com/docs/cypher-manual/current/planning-and-tuning/execution-plans/)
- [Neo4j Cypher Manual – Query plan caching](https://neo4j.com/docs/cypher-manual/current/planning-and-tuning/caching/)
- [Neo4j Upgrade and Migration Guide – Introduction](https://neo4j.com/docs/upgrade-migration-guide/current/)
- [Neo4j Upgrade and Migration Guide – Neo4j 2025–2026](https://neo4j.com/docs/upgrade-migration-guide/current/version-2025-2026/)
- [Neo4j Operations Manual – Backup and restore](https://neo4j.com/docs/operations-manual/current/backup-restore/)
- [Neo4j Java Driver Manual – Transactions](https://neo4j.com/docs/java-manual/current/transactions/)
- [Testcontainers for Java – Neo4j module](https://java.testcontainers.org/modules/databases/neo4j/)
- [JUnit 5 – User Guide](https://junit.org/junit5/docs/current/user-guide/)
