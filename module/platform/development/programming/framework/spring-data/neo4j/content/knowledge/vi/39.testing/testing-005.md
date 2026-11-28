# Neo4j Test Harness và kết nối qua Bolt khi phù hợp

Neo4j Test Harness giúp khởi động một Neo4j instance nhẹ ngay trong JVM của bài kiểm thử. Harness có thể mở Bolt endpoint để Neo4j Java Driver kết nối; nhờ đó Spring Data Neo4j (SDN) có thể chạy repository, template và `Neo4jClient` trên một database thật mà không cần cài Neo4j server riêng. Khi kiểm thử ứng dụng, cách làm này hữu ích cho mapping entity, relationship và Cypher. Tuy nhiên, harness vẫn là một instance cục bộ đơn lẻ; nếu cần xác minh Docker packaging, TLS, routing, cluster failover hoặc topology production, hãy dùng Testcontainers hay môi trường Neo4j tương ứng.

Bài học thuộc module **SPRING_DATA_NEO4J**, tập trung xây dựng tầng dữ liệu đồ thị qua node entity, relationship, repository và Cypher. Ta dùng `Person`, `Movie` và `ACTED_IN` để dựng harness, kết nối SDN qua Bolt, viết repository integration test, quản lý fixture và chọn đúng công cụ cho từng mức kiểm thử.

## 1. Test Harness giải quyết vấn đề gì?

Một unit test thuần Java có thể kiểm tra logic chuyển đổi hoặc validation mà không cần Neo4j. Nhưng các hành vi sau phụ thuộc database thực:

- SDN ánh xạ `@Node`, `@Relationship` và property sang graph như thế nào.
- Repository method sinh Cypher có đúng với model và query mong muốn không.
- Custom Cypher có hợp lệ và trả đúng shape để mapping không.
- Constraint, index, transaction và relationship persistence hoạt động như dự kiến.
- Neo4j Java Driver có thể kết nối và thực thi query qua Bolt hay không.

Test Harness cung cấp một Neo4j instance dùng cho test, có thể cấu hình extension/procedure, fixture và Bolt endpoint. Nó phù hợp cho integration test nhanh, lặp lại được, chạy cùng JVM với test process.

Điểm quan trọng: SDN không gọi trực tiếp embedded kernel của Harness. SDN sử dụng Neo4j Java Driver; ứng dụng vẫn kết nối tới database bằng Bolt URI do Harness cung cấp. Vì vậy, test có thể xác minh cả đường đi từ repository qua Driver tới Bolt server.

## 2. Chọn Test Harness, Testcontainers hay database dùng chung

| Công cụ | Cách chạy | Phù hợp khi | Giới hạn chính |
|---|---|---|---|
| Neo4j Test Harness | Neo4j chạy in-process trong JVM test | Test Cypher, mapping SDN, repository, procedure/extension và Bolt cục bộ | Không mô phỏng đầy đủ process/container/network/cluster production |
| Neo4j Testcontainers | Neo4j server chạy trong container riêng | Test gần môi trường server thực, plugin, config, version, TLS hoặc image | Cần Docker/compatible container runtime; khởi động thường nặng hơn |
| Neo4j test server dùng chung | Test kết nối tới server đã cài hoặc staging | Test môi trường tích hợp do team quản lý | Cần cô lập dữ liệu, quản lý lifecycle và tránh test ảnh hưởng nhau |
| Mock repository/driver | Không chạy Neo4j | Unit test logic nghiệp vụ và xử lý lỗi | Không kiểm tra Cypher, mapping hoặc transaction thật |

Không có lựa chọn duy nhất cho mọi test. Harness phù hợp khi cần database thật nhưng muốn setup nhẹ. Testcontainers phù hợp khi cần kiểm chứng server đóng gói và cấu hình giống triển khai hơn. Mock phù hợp khi chỉ kiểm tra logic không phụ thuộc database.

## 3. Thêm dependency Neo4j Test Harness

Harness chỉ cần ở test scope. Với Maven:

```xml
<dependency>
    <groupId>org.neo4j.test</groupId>
    <artifactId>neo4j-harness</artifactId>
    <version>${neo4j.version}</version>
    <scope>test</scope>
</dependency>
```

Với Gradle:

```groovy
dependencies {
    testImplementation "org.neo4j.test:neo4j-harness:${neo4jVersion}"
}
```

`neo4j.version` hoặc `neo4jVersion` ở đây là version tương thích với dòng Neo4j mà ứng dụng đang kiểm thử. Hãy để Spring Boot/SDN dependency management hoặc BOM của dự án quản lý version nếu có; không chọn version Harness mới nhất một cách độc lập nếu nó kéo theo Neo4j server khác major/minor với stack ứng dụng. Khi nâng Neo4j, hãy nâng Harness theo ma trận tương thích và đọc release notes.

Ứng dụng cũng cần dependency SDN/Neo4j Driver trong main source và `spring-boot-starter-test` (hoặc JUnit Jupiter, Spring Test, AssertJ tương ứng) trong test scope. Không cần khai báo thêm một Neo4j server runtime riêng chỉ để dùng Harness.

## 4. Khởi động Neo4j in-process và lấy Bolt URI

API Harness hiện đại dùng `Neo4jBuilders` và `Neo4j`:

```java
import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.BeforeAll;
import org.neo4j.harness.Neo4j;
import org.neo4j.harness.Neo4jBuilders;

class Neo4jHarnessLifecycleTest {

    static Neo4j embeddedDatabase;

    @BeforeAll
    static void startDatabase() {
        embeddedDatabase = Neo4jBuilders.newInProcessBuilder()
            .withDisabledServer()
            .build();
    }

    @AfterAll
    static void stopDatabase() {
        if (embeddedDatabase != null) {
            embeddedDatabase.close();
        }
    }
}
```

`newInProcessBuilder()` tạo instance trong cùng JVM. `withDisabledServer()` tắt HTTP server không cần thiết cho bài test này; Bolt connector vẫn được Harness cung cấp để Driver kết nối. `boltURI()` trả URI có cổng được Harness cấp cho instance.

Không hardcode `bolt://localhost:7687`: cổng test có thể được cấp động và nhiều test có thể chạy song song. Luôn lấy URI từ `embeddedDatabase.boltURI()`.

Harness có thể được cấu hình thêm fixture, procedure, function hoặc unmanaged extension bằng các phương thức builder tương ứng. Chỉ bật HTTP server nếu test thật sự cần endpoint HTTP hoặc cần gọi extension qua HTTP; với SDN repository và Java Driver, Bolt là đủ.

## 5. Kết nối Spring Data Neo4j bằng DynamicPropertySource

Khi dùng Spring Boot test slice `@DataNeo4jTest`, cần đưa Bolt URI của Harness vào property `spring.neo4j.uri`. `@DynamicPropertySource` cho phép đăng ký property động trước khi Spring tạo Driver bean:

```java
import org.neo4j.harness.Neo4j;
import org.springframework.boot.test.autoconfigure.data.neo4j.DataNeo4jTest;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;

@DataNeo4jTest
class SomeNeo4jRepositoryTest {

    // Được khởi động trong @BeforeAll như phần trước.
    static Neo4j embeddedDatabase;

    @DynamicPropertySource
    static void neo4jProperties(DynamicPropertyRegistry registry) {
        registry.add("spring.neo4j.uri", embeddedDatabase::boltURI);
        registry.add("spring.neo4j.authentication.username", () -> "neo4j");
        registry.add("spring.neo4j.authentication.password", () -> null);
    }
}
```

Đây là mẫu rút gọn chỉ tập trung vào lifecycle và property. Phần sau ghép cấu hình này với repository và một test method hoàn chỉnh. Test Harness mặc định thường dùng cấu hình xác thực dành cho test; nếu bạn bật authentication trong builder/configuration, phải cung cấp username/password tương ứng.

Spring context được cache giữa các test class. Nếu đóng Harness sau một class nhưng Spring context còn được cache và tái sử dụng, Driver trong context có thể vẫn trỏ tới URI đã đóng. Có thể dùng `@DirtiesContext(classMode = DirtiesContext.ClassMode.AFTER_CLASS)` cho test class có lifecycle riêng, hoặc dùng một Harness dùng chung với lifecycle tương ứng cho toàn bộ test suite.

## 6. Repository integration test hoàn chỉnh

Giả sử có entity `Movie` với business ID là `movieId`:

```java
import org.springframework.data.neo4j.core.schema.Id;
import org.springframework.data.neo4j.core.schema.Node;

@Node("Movie")
public class Movie {

    @Id
    private String movieId;

    private String title;

    private Integer released;

    protected Movie() {
    }

    public Movie(String movieId, String title, Integer released) {
        this.movieId = movieId;
        this.title = title;
        this.released = released;
    }

    public String getMovieId() { return movieId; }
    public String getTitle() { return title; }
    public Integer getReleased() { return released; }
}
```

Repository:

```java
import java.util.Optional;

import org.springframework.data.neo4j.repository.Neo4jRepository;

public interface MovieRepository extends Neo4jRepository<Movie, String> {

    Optional<Movie> findByTitle(String title);
}
```

Test:

```java
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.Test;
import org.neo4j.harness.Neo4j;
import org.neo4j.harness.Neo4jBuilders;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.data.neo4j.DataNeo4jTest;
import org.springframework.test.annotation.DirtiesContext;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;

@DataNeo4jTest
@DirtiesContext(classMode = DirtiesContext.ClassMode.AFTER_CLASS)
class MovieRepositoryHarnessTest {

    static Neo4j embeddedDatabase;

    @Autowired
    MovieRepository movieRepository;

    @BeforeAll
    static void startDatabase() {
        embeddedDatabase = Neo4jBuilders.newInProcessBuilder()
            .withDisabledServer()
            .build();
    }

    @AfterAll
    static void stopDatabase() {
        embeddedDatabase.close();
    }

    @DynamicPropertySource
    static void neo4jProperties(DynamicPropertyRegistry registry) {
        registry.add("spring.neo4j.uri", embeddedDatabase::boltURI);
        registry.add("spring.neo4j.authentication.username", () -> "neo4j");
        registry.add("spring.neo4j.authentication.password", () -> null);
    }

    @Test
    void shouldSaveAndReadMovieThroughRepository() {
        Movie saved = movieRepository.save(
            new Movie("M-100", "The Graph", 2025)
        );

        assertThat(saved.getMovieId()).isEqualTo("M-100");

        assertThat(movieRepository.findById("M-100"))
            .get()
            .extracting(Movie::getTitle)
            .isEqualTo("The Graph");

        assertThat(movieRepository.findByTitle("The Graph"))
            .get()
            .extracting(Movie::getReleased)
            .isEqualTo(2025);
    }
}
```

Ví dụ dùng import của Spring Boot 3.x. Với Spring Boot 4.x, module test Neo4j được tách riêng và package của `@DataNeo4jTest` chuyển sang `org.springframework.boot.data.neo4j.test.autoconfigure.DataNeo4jTest`; hãy dùng artifact và package tương ứng với major version dự án. Không trộn annotation/package của Boot 3 và Boot 4 trong cùng test.

`@DataNeo4jTest` là test slice: nó cấu hình infrastructure SDN và scan entity/repository phù hợp, nhưng không tự khởi động database. Harness và `@DynamicPropertySource` cung cấp kết nối. Các `@Component` hoặc service nghiệp vụ không được scan tự động trong slice; dùng `@Import(...)` nếu test cần chúng, hoặc dùng `@SpringBootTest` khi muốn kiểm tra toàn application context.

## 7. Dùng Bolt trực tiếp khi cần kiểm tra Driver

Nếu test cần kiểm tra hành vi của Java Driver, session, transaction hoặc Bolt URI mà không đi qua repository, có thể kết nối trực tiếp:

```java
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.neo4j.driver.Driver;
import org.neo4j.driver.GraphDatabase;
import org.neo4j.driver.Session;
import org.neo4j.harness.Neo4j;
import org.neo4j.harness.Neo4jBuilders;

class BoltConnectionTest {

    @Test
    void driverCanRunCypherAgainstHarness() {
        try (Neo4j embedded = Neo4jBuilders.newInProcessBuilder()
                .withDisabledServer()
                .build();
             Driver driver = GraphDatabase.driver(embedded.boltURI());
             Session session = driver.session()) {

            long count = session.executeWrite(tx -> {
                tx.run("""
                    CREATE (:Person {personId: 'P-100', name: 'An'})
                    """).consume();

                return tx.run("MATCH (p:Person) RETURN count(p) AS total")
                    .single()
                    .get("total")
                    .asLong();
            });

            assertThat(count).isEqualTo(1L);
        }
    }
}
```

Ở đây Driver kết nối tới Bolt URI do Harness mở. Nếu Harness được cấu hình authentication, truyền `AuthTokens.basic(...)` hoặc token phù hợp vào `GraphDatabase.driver(...)`. Ví dụ không dùng `@DataNeo4jTest`; nó kiểm tra đường đi trực tiếp qua Driver.

Không cần dùng Driver trực tiếp khi mục tiêu chỉ là kiểm tra repository mapping. Hãy ưu tiên `Neo4jRepository`, `Neo4jTemplate` hoặc `Neo4jClient` mà ứng dụng thực tế dùng để test đúng tầng tích hợp.

## 8. Test qua Bolt có nghĩa là đang test điều gì?

Test Harness khởi động database in-process, nhưng Driver vẫn nói chuyện với database qua Bolt. Vì vậy, test này có thể phát hiện:

- Bolt connector không khởi động hoặc URI cấu hình sai.
- Driver không tạo được session hoặc transaction.
- Cypher gửi qua Driver bị lỗi cú pháp hoặc lỗi tham số.
- Repository/SDN không ánh xạ đúng kết quả nhận qua Driver.
- Transaction commit/rollback không có hành vi như mong đợi.

Nhưng nó không tự kiểm tra:

- Firewall, DNS, load balancer hoặc network policy giữa hai container/máy.
- TLS certificate chain và cấu hình encryption của môi trường production.
- Cluster routing, read replica, primary election hoặc failover.
- Connection pool behavior dưới tải mạng thật.
- Khác biệt filesystem, memory, CPU hoặc kernel giữa JVM test và server triển khai.

Vì Harness chạy cùng JVM, lỗi kết nối có thể khác với tình huống ứng dụng và Neo4j chạy trong hai process/container riêng. Muốn kiểm tra các yếu tố này, hãy chạy Neo4j qua Testcontainers hoặc staging có cấu hình tương tự production.

## 9. Dùng fixture để chuẩn bị graph

Test nên tạo graph nhỏ, có ý nghĩa và độc lập. Có thể tạo fixture bằng Cypher qua `Neo4jClient` trong `@BeforeEach`:

```java
import org.junit.jupiter.api.BeforeEach;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.data.neo4j.core.Neo4jClient;

@Autowired
Neo4jClient neo4jClient;

@BeforeEach
void createFixture() {
    neo4jClient.query("""
        CREATE (p:Person {personId: 'P-1', name: 'An'})
        CREATE (m:Movie {movieId: 'M-1', title: 'The Graph'})
        CREATE (p)-[:ACTED_IN]->(m)
        """).run();
}
```

Với `@DataNeo4jTest`, test slice mặc định chạy trong transaction và rollback khi test kết thúc. Fixture tạo qua cùng Spring-managed client thường nằm trong transaction test đó. Không nên giả định điều này áp dụng cho thao tác qua một Driver/session độc lập.

Nếu cần dọn dữ liệu thủ công, dùng khóa namespace riêng cho từng test hoặc xóa đúng label/relationship do test tạo. Tránh `MATCH (n) DETACH DELETE n` trên database dùng chung vì có thể xóa dữ liệu của test khác đang chạy song song.

## 10. Transaction test và giới hạn với reactive access

`@DataNeo4jTest` mặc định có transaction test imperative và rollback sau mỗi test. Điều này thuận tiện cho `Neo4jRepository` imperative.

Nếu test reactive repository hoặc service, không mặc định rằng transaction test imperative bao phủ publisher reactive. Spring Data Neo4j lưu ý cần dùng `TransactionalOperator` để kiểm tra reactive transaction hoặc gọi service method được cấu hình với reactive transaction manager đúng cách. Ví dụ:

```java
import org.springframework.transaction.reactive.TransactionalOperator;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

@Autowired
TransactionalOperator transactionalOperator;

@Test
void shouldExecuteReactiveWorkInTransaction() {
    Mono<Long> count = reactivePersonRepository.count()
        .as(transactionalOperator::transactional);

    StepVerifier.create(count)
        .expectNextCount(1)
        .verifyComplete();
}
```

Đoạn code minh họa việc bọc publisher bằng transaction operator; test thực tế cần fixture và assertion phù hợp với dữ liệu. Không gọi `.block()` trong test reactive chỉ để tiện assertion; dùng `StepVerifier` để subscribe và kiểm tra signal.

## 11. Khi nào cần Testcontainers thay cho Harness?

Chuyển sang Testcontainers hoặc Neo4j staging khi test cần một hoặc nhiều điều kiện sau:

- Kiểm tra đúng image/version Neo4j sẽ triển khai.
- Bật plugin như APOC hoặc extension với cấu hình gần production.
- Kiểm tra TLS, authentication, authorization và cấu hình server.
- Kiểm tra kết nối từ application container tới database container qua network.
- Kiểm tra import, file access, memory config hoặc startup behavior của server process.
- Kiểm tra edition-specific feature hoặc cấu hình database không có trong Harness mặc định.

Testcontainers Neo4j cung cấp container với Bolt URL động. Với SDN, nguyên tắc cấu hình tương tự Harness: khởi động container, đăng ký URI/credentials bằng `@DynamicPropertySource`, sau đó để Spring tạo Driver kết nối tới endpoint đó.

Ví dụ khung lifecycle (API module Testcontainers phụ thuộc version đang dùng):

```java
import org.springframework.boot.test.autoconfigure.data.neo4j.DataNeo4jTest;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.neo4j.Neo4jContainer;

@DataNeo4jTest
@Testcontainers
class Neo4jContainerTest {

    @Container
    static Neo4jContainer<?> neo4j = new Neo4jContainer<>("neo4j:5")
        .withAdminPassword("test-password");

    @DynamicPropertySource
    static void neo4jProperties(DynamicPropertyRegistry registry) {
        registry.add("spring.neo4j.uri", neo4j::getBoltUrl);
        registry.add("spring.neo4j.authentication.username", () -> "neo4j");
        registry.add("spring.neo4j.authentication.password", neo4j::getAdminPassword);
    }
}
```

Đây là ví dụ khái niệm; import `Neo4jContainer`, annotation `@Testcontainers`/`@Container` và dependency coordinates cần khớp phiên bản Testcontainers. Chọn tag image cùng major/minor mà ứng dụng hỗ trợ; không dùng tag động `latest` cho test cần tái lập.

Testcontainers một node cũng chưa kiểm tra cluster failover. Nếu cần kiểm tra routing và primary election, phải dựng topology nhiều member hoặc dùng môi trường staging cluster thực.

## 12. Kiểm thử procedure và extension

Harness đặc biệt hữu ích khi phát triển stored procedure hoặc extension chạy bên trong Neo4j. Có thể đăng ký class procedure với builder trước khi khởi động:

```java
Neo4j embedded = Neo4jBuilders.newInProcessBuilder()
    .withDisabledServer()
    .withProcedure(MovieProcedures.class)
    .build();
```

Sau đó dùng Driver qua `embedded.boltURI()` để gọi procedure bằng Cypher:

```cypher
CALL custom.movieTitles()
YIELD title
RETURN title;
```

Harness có thể cấu hình fixture và extension để test contract của procedure trong môi trường cô lập. Hãy kiểm tra annotation/registration và dependencies của procedure phù hợp với đúng version Neo4j đang dùng.

## 13. Chạy test song song và quản lý lifecycle

Mỗi test cần database state độc lập. Có một số cách tổ chức:

- Một Harness dùng chung cho test class, kết hợp transaction rollback hoặc fixture có namespace riêng.
- Một Harness mới cho mỗi test khi cần cô lập hoàn toàn, đổi lại thời gian startup tăng.
- Một Harness dùng chung cho suite với fixture được dọn theo test ID và không chạy các test ghi đè cùng dữ liệu song song.

Tránh dùng chung một `Session` giữa các test thread. Driver thread-safe và có thể dùng chung; Session là đối tượng có state transaction và không nên dùng đồng thời từ nhiều thread.

Đảm bảo Harness được đóng kể cả khi test thất bại. Có thể dùng `@AfterAll`, JUnit extension hoặc `try-with-resources` tùy lifecycle. Nếu dùng Spring context cache, phối hợp đóng context và Harness để tránh bean Driver trỏ vào endpoint đã tắt.

## 14. Lỗi thường gặp

| Lỗi | Nguyên nhân | Cách xử lý |
|---|---|---|
| Hardcode `bolt://localhost:7687` | Cổng có thể được cấp động hoặc bị chiếm | Dùng `embeddedDatabase.boltURI()` |
| Chỉ thêm `neo4j-harness` nhưng Spring không kết nối | Harness chưa được đưa vào `spring.neo4j.uri` | Đăng ký URI bằng `@DynamicPropertySource` |
| Dùng version Harness không tương thích | Harness kéo theo server/dependency khác với SDN stack | Căn version theo Neo4j được hỗ trợ và BOM |
| Nghĩ `withDisabledServer()` tắt cả Bolt | Nhầm HTTP server với Bolt connector | Dùng `boltURI()`; chỉ bật HTTP khi cần |
| Đóng Harness khi Spring context vẫn được cache | Driver còn trỏ tới server đã đóng | Dùng shared lifecycle hoặc `@DirtiesContext` |
| Tin `@DataNeo4jTest` tự cung cấp database | Test slice chỉ cấu hình Spring infrastructure | Khởi động Harness/Testcontainers và cung cấp connection properties |
| Mong `@DataNeo4jTest` load toàn bộ service | Test slice không scan mọi component | Dùng `@Import` hoặc `@SpringBootTest` |
| Cho rằng thao tác Driver độc lập được rollback cùng Spring test transaction | Driver mở transaction/session riêng | Cleanup riêng hoặc dùng Spring-managed client trong test |
| Test reactive dựa vào imperative test transaction | Reactive transaction cần Reactor context/manager | Dùng `TransactionalOperator` và `StepVerifier` |
| Xóa toàn bộ graph trong `@BeforeEach` khi chạy song song | Test có thể xóa dữ liệu của test khác | Dùng fixture namespace hoặc database riêng |
| Dùng Harness để kết luận cluster failover hoạt động | Harness mặc định là instance đơn trong JVM | Dùng topology cluster trong staging hoặc test setup chuyên biệt |

## 15. Checklist chọn và viết integration test

- Xác định test cần kiểm tra mapping/Cypher, Driver/Bolt, server config hay cluster.
- Dùng Harness cho test SDN repository và Cypher nhanh, lặp lại được.
- Dùng `neo4j-harness` ở test scope và version tương thích với Neo4j runtime.
- Khởi động Harness một lần theo lifecycle rõ ràng và đóng sau test.
- Lấy URI bằng `boltURI()`; không hardcode port.
- Đăng ký `spring.neo4j.uri` và credentials qua `@DynamicPropertySource`.
- Dùng `@DataNeo4jTest` cho repository slice; `@SpringBootTest` khi cần toàn application context.
- Dùng `Neo4jClient`/repository để test SDN path; dùng Driver trực tiếp khi cần test Bolt/Driver cụ thể.
- Quản lý fixture và rollback; không giả định Driver độc lập tham gia Spring test transaction.
- Với reactive transaction, dùng `TransactionalOperator` hoặc service reactive được cấu hình đúng.
- Dùng Testcontainers khi cần process/container/config/plugin/TLS gần production.
- Dùng cluster thật hoặc topology nhiều member khi cần kiểm tra routing/failover.
- Tránh chia sẻ mutable fixture hoặc Session giữa test chạy song song.

## 16. Bài tập thực hành

1. Thêm `neo4j-harness` vào test scope với version tương thích với Neo4j runtime.
2. Khởi động Harness bằng `Neo4jBuilders.newInProcessBuilder()` và đọc `boltURI()`.
3. Viết `@DataNeo4jTest` dùng `@DynamicPropertySource` để kết nối SDN tới Harness.
4. Lưu và đọc lại `Movie` qua `Neo4jRepository`; kiểm tra ID và property.
5. Tạo `Person`, `Movie`, `ACTED_IN` bằng `Neo4jClient` và xác nhận graph qua repository.
6. Dùng `GraphDatabase.driver(embedded.boltURI())` chạy một query qua Bolt.
7. Cấu hình một procedure bằng `.withProcedure(...)` và gọi procedure qua Cypher.
8. Tạo test dùng `@Import` để đưa service nghiệp vụ vào `@DataNeo4jTest`.
9. So sánh rollback của thao tác repository với thao tác qua Driver độc lập.
10. Viết reactive repository test sử dụng `StepVerifier` và `TransactionalOperator`.
11. Thay Harness bằng Testcontainers và cấu hình Bolt URL động.
12. Liệt kê những điều Harness không thể xác minh về TLS, Docker network, routing và cluster failover.

Khi hoàn thành, bạn cần biết Test Harness là Neo4j instance chạy in-process, còn SDN và Java Driver vẫn kết nối qua Bolt URI. Hãy chọn Harness cho integration test nhanh về mapping, repository và Cypher; chọn Testcontainers hoặc cluster staging khi cần xác minh cấu hình server, network, TLS, routing hay failover giống production.

## Tài liệu tham khảo

- [Spring Data Neo4j — Testing with Spring Boot and @DataNeo4jTest](https://docs.spring.io/spring-data/neo4j/reference/testing/testing-with-spring-boot.html)
- [Spring Boot — Auto-configured Data Neo4j Tests](https://docs.spring.io/spring-boot/reference/testing/spring-boot-applications.html)
- [Neo4j Java Reference — Setting up a plugin project and Test Harness](https://neo4j.com/docs/java-reference/current/extending-neo4j/project-setup/)
- [Neo4j Java Reference — Testing user-defined procedures and functions](https://neo4j.com/docs/java-reference/current/extending-neo4j/user-defined-procedures-functions/)
- [Neo4j Java Reference — Bolt connector for embedded Neo4j](https://neo4j.com/docs/java-reference/current/java-embedded/bolt/)
- [Neo4j Java Driver Manual](https://neo4j.com/docs/java-manual/current/)
