# Chuẩn bị fixture, constraint, index và dữ liệu kiểm thử

Một bài kiểm thử Spring Data Neo4j có giá trị khi nó chạy trên graph có trạng thái xác định, schema đúng với ứng dụng và dữ liệu đủ đại diện cho quy tắc nghiệp vụ. Nếu fixture không ổn định, constraint chưa được tạo hoặc index vẫn đang populate, kết quả kiểm thử có thể sai lệch giữa máy cá nhân và CI.

Trong bài này, fixture là tập dữ liệu và schema chuẩn bị cho một kịch bản kiểm thử. Fixture có thể gồm node, relationship, property, constraint và index. Cần quản lý vòng đời từng phần riêng: dữ liệu nghiệp vụ thường được tạo lại cho mỗi test, còn schema thường được tạo một lần cho database kiểm thử và giữ nguyên trong suốt vòng đời container.

Sau bài học, bạn có thể:

- Chọn Neo4j Test Harness hoặc Testcontainers theo mục tiêu kiểm thử.
- Dùng **@DataNeo4jTest** để kiểm thử repository và mapping.
- Khởi chạy Neo4j cô lập với Testcontainers và cấu hình kết nối động.
- Chuẩn bị constraint và index bằng Cypher trước khi nạp dữ liệu.
- Tạo fixture node/relationship có business key ổn định.
- Cô lập dữ liệu giữa các test và dọn dẹp đúng phạm vi.
- Kiểm tra uniqueness, existence, index state và query plan.
- Xử lý khác biệt giữa transaction imperative và reactive trong test.

## 1. Fixture kiểm thử gồm những gì?

Một fixture Neo4j thường có bốn phần:

| Thành phần | Nội dung | Ví dụ |
|---|---|---|
| Môi trường | Phiên bản Neo4j, edition, database và kết nối | Neo4j container cùng phiên bản production |
| Schema | Constraint và index cần cho ứng dụng | Person.personCode duy nhất |
| Graph fixture | Node, relationship và property | Person đặt Order, Order chứa Product |
| Quy tắc vòng đời | Tạo, cô lập, rollback hoặc xóa dữ liệu | Nạp fixture trước test, rollback sau test |

Các phần phải tương thích với nhau. Ví dụ, nếu schema yêu cầu orderCode duy nhất thì mọi fixture tạo nhiều Order phải dùng mã khác nhau. Nếu repository truy vấn theo status và createdAt, fixture nên có nhiều trạng thái và mốc thời gian khác nhau để kiểm tra cả kết quả lọc lẫn thứ tự.

Không dùng dữ liệu ngẫu nhiên hoàn toàn cho các trường mà test cần so sánh chính xác. Hãy giữ nội dung fixture ổn định và chỉ tạo namespace riêng cho từng test khi cần tránh va chạm.

## 2. Chọn Neo4j Test Harness hay Testcontainers

Hai lựa chọn phổ biến có mục đích khác nhau:

| Tiêu chí | Neo4j Test Harness | Testcontainers Neo4j |
|---|---|---|
| Cách chạy | Neo4j embedded trong cùng JVM với test | Neo4j chạy trong Docker container |
| Mục tiêu phù hợp | Kiểm thử extension, procedure hoặc logic cần khởi động Neo4j trong tiến trình test | Kiểm thử tích hợp repository, Driver, transaction và Cypher với server thật |
| Cô lập | Mỗi harness instance có vòng đời riêng | Container dùng image và cấu hình có thể pin theo phiên bản |
| Tốc độ | Thường khởi động nhanh, ít chi phí container | Có chi phí Docker và khởi động server |
| Độ tương đồng production | Thời gian và hiệu năng trong cùng JVM có thể khác server triển khai | Gần hơn với cách ứng dụng kết nối một Neo4j server độc lập |
| Yêu cầu môi trường | Thư viện harness tương thích với Neo4j/JDK | Docker hoặc container runtime tương thích |

Với kiểm thử tích hợp Spring Data Neo4j, Testcontainers thường là lựa chọn tốt để xác minh tương tác qua Bolt với đúng phiên bản Neo4j. Neo4j Test Harness vẫn hữu ích khi kiểm thử stored procedure hoặc extension được nạp vào instance embedded.

Không kết nối test vào database development hoặc production dùng chung. Một test có thể tạo constraint, xóa node hoặc thay đổi index; môi trường riêng giúp tránh làm hỏng dữ liệu của người khác và giúp mỗi lần chạy bắt đầu từ trạng thái biết trước.

## 3. Dùng @DataNeo4jTest để kiểm thử tầng dữ liệu

**@DataNeo4jTest** là test slice của Spring Boot. Nó cấu hình các thành phần cần cho Spring Data Neo4j như repository, client, template và transaction manager, đồng thời quét các lớp node mapping. Các bean **@Component** thông thường không được quét tự động; nếu cần service trong test, hãy import service hoặc dùng **@SpringBootTest** cho kiểm thử rộng hơn.

Với Spring Boot 4.x, annotation nằm trong package:

~~~java
import org.springframework.boot.data.neo4j.test.autoconfigure.DataNeo4jTest;
~~~

Với Spring Boot 3.x, package cũ là:

~~~java
import org.springframework.boot.test.autoconfigure.data.neo4j.DataNeo4jTest;
~~~

Hãy dùng package và test module tương ứng với phiên bản Spring Boot của dự án. Spring Boot 4 tách test slice Neo4j thành module spring-boot-data-neo4j-test; các phiên bản Boot trước đó cung cấp annotation qua hạ tầng test autoconfigure.

Test slice không tự cung cấp một Neo4j server. Bạn vẫn cần cấu hình một endpoint, chẳng hạn Testcontainers hoặc Test Harness. Với test imperative, **@DataNeo4jTest** mặc định chạy trong transaction và rollback khi kết thúc mỗi test method. Điều này giúp dữ liệu graph do test tạo không tồn tại sau test.

Có thể inject repository trực tiếp:

~~~java
@DataNeo4jTest
class OrderRepositoryTest {

    @Autowired
    private OrderRepository orderRepository;

    @Test
    void findsOrderByBusinessCode() {
        // Fixture được chuẩn bị trước test.
    }
}
~~~

Transaction test mặc định là imperative. Không giả định annotation này tự rollback mọi thao tác reactive. Với reactive repository hoặc service, hãy kiểm thử bằng Reactor và **TransactionalOperator** hoặc thực hiện cleanup tường minh.

## 4. Khởi chạy Neo4j riêng bằng Testcontainers

Thêm các dependency test tương ứng với phiên bản được quản lý trong build:

~~~gradle
dependencies {
    testImplementation("org.springframework.boot:spring-boot-starter-test")
    testImplementation("org.springframework.boot:spring-boot-data-neo4j-test")
    testImplementation("org.testcontainers:testcontainers-neo4j:2.0.5")
    testImplementation("org.testcontainers:testcontainers-junit-jupiter:2.0.5")
}
~~~

Nếu dự án chưa dùng Spring Boot 4, hãy điều chỉnh dependency test slice theo phiên bản Boot đang sử dụng. Nên quản lý các dependency Testcontainers bằng BOM thay vì để nhiều module lệch phiên bản.

Ví dụ cấu hình container cho JUnit Jupiter:

~~~java
import org.springframework.boot.data.neo4j.test.autoconfigure.DataNeo4jTest;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.neo4j.Neo4jContainer;

@Testcontainers
@DataNeo4jTest
class OrderRepositoryTest {

    @Container
    static final Neo4jContainer neo4j =
        new Neo4jContainer("neo4j:5.26")
            .withAdminPassword("test-password");

    @DynamicPropertySource
    static void neo4jProperties(DynamicPropertyRegistry registry) {
        registry.add("spring.neo4j.uri", neo4j::getBoltUrl);
        registry.add("spring.neo4j.authentication.username", () -> "neo4j");
        registry.add("spring.neo4j.authentication.password", neo4j::getAdminPassword);
        registry.add("spring.data.neo4j.database", () -> "neo4j");
    }
}
~~~

Tag image trong ví dụ là minh họa. Hãy pin image theo phiên bản Neo4j và edition mà ứng dụng triển khai hỗ trợ; tránh dùng tag thay đổi liên tục như latest. Static container được chia sẻ giữa các method trong cùng test class và bị dừng sau class. Docker cần hoạt động trên máy developer và CI.

Testcontainers JUnit Jupiter hiện hỗ trợ lifecycle tuần tự. Không bật chạy song song các test dùng chung static container nếu chưa thiết kế cô lập database hoặc namespace dữ liệu riêng cho từng test.

## 5. Tạo schema fixture trước khi nạp dữ liệu

Schema fixture nên mô phỏng schema mà ứng dụng dùng ở môi trường thật. Ưu tiên chạy cùng migration Cypher mà quy trình triển khai sử dụng. Nếu test tự viết một bộ DDL khác với migration production, test có thể xanh dù schema thực tế bị thiếu hoặc sai.

Ví dụ ứng dụng bán hàng yêu cầu orderCode duy nhất và thường lọc đơn theo status, createdAt:

~~~cypher
CREATE CONSTRAINT order_code_unique IF NOT EXISTS
FOR (o:Order)
REQUIRE o.orderCode IS UNIQUE;

CREATE RANGE INDEX order_status_created_at IF NOT EXISTS
FOR (o:Order)
ON (o.status, o.createdAt);
~~~

Constraint uniqueness tạo range index backing trên orderCode. Không tạo thêm một range index khác có cùng label và property schema chỉ để tìm theo orderCode; backing index của constraint đã phục vụ lookup đó. Index thứ hai trong ví dụ phục vụ một mẫu truy vấn khác.

IF NOT EXISTS giúp lệnh có thể chạy lại khi schema tương ứng đã tồn tại. Tuy nhiên, nó không thay thế việc kiểm tra schema. Một index hoặc constraint khác có cùng tên, schema hoặc loại có thể làm lệnh không tạo thay đổi như bạn kỳ vọng. Hãy xác minh metadata sau khi bootstrap.

### Tạo schema ngoài transaction dữ liệu của từng test

Schema thường được tạo một lần sau khi container khởi động. Có thể dùng một Driver session riêng trong @BeforeAll, trước khi Spring test method bắt đầu transaction:

~~~java
import org.junit.jupiter.api.BeforeAll;
import org.neo4j.driver.AuthTokens;
import org.neo4j.driver.Driver;
import org.neo4j.driver.GraphDatabase;
import org.neo4j.driver.Session;

@BeforeAll
static void prepareSchema() {
    try (Driver driver = GraphDatabase.driver(
            neo4j.getBoltUrl(),
            AuthTokens.basic("neo4j", neo4j.getAdminPassword()));
         Session session = driver.session()) {

        session.run("""
            CREATE CONSTRAINT order_code_unique IF NOT EXISTS
            FOR (o:Order)
            REQUIRE o.orderCode IS UNIQUE
            """).consume();

        session.run("""
            CREATE RANGE INDEX order_status_created_at IF NOT EXISTS
            FOR (o:Order)
            ON (o.status, o.createdAt)
            """).consume();

        session.run("CALL db.awaitIndexes(60)").consume();
    }
}
~~~

Trong cùng class test, ghép phần bootstrap schema này với cấu hình container ở phần trước. Nếu dùng migration runner của ứng dụng, hãy khởi chạy chính migration đó thay vì chép DDL thành một phiên bản riêng trong test.

Index được tạo bất đồng bộ và có thể ở trạng thái POPULATING ngay sau lệnh tạo. CALL db.awaitIndexes(60) đợi các index hoàn tất trong giới hạn 60 giây. Test phụ thuộc index chỉ nên chạy sau khi index sẵn sàng.

## 6. Xác minh constraint và index đã có hiệu lực

Sau khi bootstrap, kiểm tra constraint:

~~~cypher
SHOW CONSTRAINTS
YIELD name, type, entityType, labelsOrTypes, properties
WHERE name = 'order_code_unique'
RETURN name, type, entityType, labelsOrTypes, properties
~~~

Kiểm tra index:

~~~cypher
SHOW INDEXES
YIELD name, state, type, labelsOrTypes, properties, owningConstraint
WHERE name = 'order_status_created_at'
RETURN name, state, type, labelsOrTypes, properties, owningConstraint
~~~

Trạng thái index cần là ONLINE. POPULATING nghĩa là index vẫn đang được xây dựng và chưa sẵn sàng phục vụ truy vấn. Có thể đợi một index cụ thể bằng CALL db.awaitIndex('order_status_created_at', 60) hoặc đợi toàn bộ bằng CALL db.awaitIndexes(60).

Không chỉ kiểm tra lệnh DDL không ném exception. Hãy xác nhận đúng tên, label/type, property và constraint ownership. Điều này phát hiện tình huống IF NOT EXISTS không tạo schema object mà test mong đợi.

## 7. Constraint fixture cần kiểm thử điều gì?

Constraint bảo vệ quy tắc dữ liệu tại database. Các test nên chứng minh cả dữ liệu hợp lệ được chấp nhận và dữ liệu vi phạm bị từ chối.

| Quy tắc | Test dữ liệu hợp lệ | Test dữ liệu vi phạm |
|---|---|---|
| Uniqueness | Hai mã khác nhau được lưu | Hai node cùng label có cùng business key bị từ chối |
| Existence | Node/relationship có property bắt buộc được lưu | Thiếu property bị từ chối |
| Property type | Property có kiểu được quy định được lưu | Ghi property sai kiểu bị từ chối |
| Key | Định danh tồn tại và duy nhất được lưu | Thiếu hoặc trùng một phần tử key bị từ chối |

Property existence, property type và key constraint phụ thuộc Neo4j Enterprise Edition. Uniqueness constraint có thể dùng trong Neo4j Community Edition. Nếu bài test phụ thuộc constraint chỉ có trên Enterprise, container test phải chạy image Enterprise hợp lệ và chấp nhận điều khoản license theo yêu cầu Neo4j.

Điểm dễ nhầm: uniqueness constraint không bắt buộc property phải xuất hiện. Nếu mọi Order đều phải có orderCode, cần existence hoặc key constraint ở edition hỗ trợ, hoặc validation ở service nếu dùng edition không có loại constraint đó.

### Kiểm thử uniqueness bằng transaction độc lập

Test kiểm tra constraint cần quan sát lỗi ghi thực tế. Có thể tắt transaction mặc định của test slice để mỗi lệnh client chạy trong transaction riêng:

~~~java
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.data.neo4j.core.Neo4jClient;
import org.neo4j.driver.exceptions.Neo4jException;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;
import java.util.UUID;

@DataNeo4jTest
@Transactional(propagation = Propagation.NOT_SUPPORTED)
class OrderConstraintTest {

    @Autowired
    private Neo4jClient neo4jClient;

    @Test
    void rejectsDuplicateOrderCode() {
        String code = "ORD-CONSTRAINT-" + UUID.randomUUID();

        try {
            neo4jClient.query("""
                CREATE (:Order {orderCode: $code})
                """)
                .bind(code).to("code")
                .run();

            assertThatThrownBy(() ->
                neo4jClient.query("""
                    CREATE (:Order {orderCode: $code})
                    """)
                    .bind(code).to("code")
                    .run()
            ).isInstanceOf(Neo4jException.class);
        } finally {
            neo4jClient.query("""
                MATCH (o:Order {orderCode: $code})
                DETACH DELETE o
                """)
                .bind(code).to("code")
                .run();
        }
    }
}
~~~

Đây là phần kiểm thử constraint bổ sung cho test context có cùng container và schema bootstrap ở trên; nếu tách thành class riêng, hãy tái sử dụng cấu hình container và bootstrap migration. Dùng business key dành riêng cho test để không va chạm fixture khác. Trong dự án thực tế, có thể kiểm tra thêm mã lỗi Neo4j cụ thể thay vì chỉ kiểm tra lớp exception.

Với test transaction mặc định được bật, một lỗi constraint có thể khiến transaction hiện tại bị đánh dấu rollback-only. Vì vậy, test xác minh lỗi ghi nên tách transaction rõ ràng như ví dụ hoặc dùng Driver session riêng.

## 8. Thiết kế graph fixture có tính xác định

Fixture cần phản ánh quan hệ mà repository ánh xạ. Ví dụ:

~~~cypher
(:Person {personCode: 'P-001'})
    -[:PLACED {placedAt: datetime('2026-11-20T09:00:00Z')}]->
(:Order {orderCode: 'ORD-001', status: 'NEW'})
    -[:CONTAINS {quantity: 2}]->
(:Product {sku: 'SKU-001', title: 'Graph Book'})
~~~

Hãy dùng business key như personCode, orderCode và sku trong fixture. Không dựa vào internal node ID hoặc giả định Neo4j cấp cùng một ID sau mỗi lần chạy. ID nội bộ không phải định danh ổn định của fixture.

Một bộ fixture hữu ích nên có:

- Node có đủ property bắt buộc và node có property tùy chọn bị thiếu.
- Relationship có property, hướng và loại đúng với entity mapping.
- Nhiều trạng thái hoặc category để kiểm tra điều kiện lọc.
- Một node không có relationship và một node có nhiều relationship để kiểm tra cardinality.
- Giá trị ở biên như ngày bắt đầu/kết thúc hoặc số lượng bằng 0 nếu nghiệp vụ cho phép.
- Business key duy nhất, dễ đọc trong assertion và log.

Giữ fixture nhỏ cho test repository. Dữ liệu hàng trăm nghìn node phù hợp với test hiệu năng riêng, không nên nạp lại trong mọi test method.

## 9. Nạp fixture theo lô bằng UNWIND

Có thể đặt một câu Cypher duy nhất trong src/test/resources/fixtures/orders.cypher:

~~~cypher
UNWIND $rows AS row
CREATE (p:Person {
    personCode: row.personCode,
    testScope: $scope
})
CREATE (o:Order {
    orderCode: row.orderCode,
    status: row.status,
    createdAt: row.createdAt,
    testScope: $scope
})
CREATE (p)-[:PLACED {
    placedAt: row.createdAt,
    testScope: $scope
}]->(o)
~~~

Test truyền dữ liệu làm parameter:

~~~java
import java.nio.charset.StandardCharsets;
import java.time.ZonedDateTime;
import java.util.List;
import java.util.Map;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.core.io.Resource;
import org.springframework.core.io.ResourceLoader;
import org.springframework.data.neo4j.core.Neo4jClient;

@Autowired
private ResourceLoader resourceLoader;

@Autowired
private Neo4jClient neo4jClient;

Resource fixture = resourceLoader.getResource(
    "classpath:fixtures/orders.cypher"
);
String fixtureCypher = fixture.getContentAsString(StandardCharsets.UTF_8);

String scope = "order-repository-test";

List<Map<String, Object>> rows = List.of(
    Map.of(
        "personCode", "P-001",
        "orderCode", "ORD-001",
        "status", "NEW",
        "createdAt", ZonedDateTime.parse("2026-11-20T09:00:00Z")
    ),
    Map.of(
        "personCode", "P-002",
        "orderCode", "ORD-002",
        "status", "PAID",
        "createdAt", ZonedDateTime.parse("2026-11-21T10:00:00Z")
    )
);

neo4jClient.query(fixtureCypher)
    .bind(rows).to("rows")
    .bind(scope).to("scope")
    .run();
~~~

Gọi đoạn nạp fixture này trong `@BeforeEach` của test imperative. UNWIND tạo graph fixture theo lô, giảm số lần round-trip tới database. Parameter giúp giữ dữ liệu tách khỏi câu Cypher và truyền temporal value theo kiểu Java phù hợp. testScope đánh dấu node và relationship thuộc fixture nào để cleanup có phạm vi.

Nếu fixture được lưu thành file resource, hãy đọc nội dung file thành một câu Cypher rồi bind parameter. Tránh ghép chuỗi giá trị đầu vào vào query hoặc viết một file chứa nhiều statement rồi tự tách bằng dấu chấm phẩy; dấu này có thể xuất hiện trong literal hoặc biểu thức.

## 10. Dọn dữ liệu và cô lập test

Với test imperative dùng transaction mặc định của @DataNeo4jTest, thao tác tạo và cập nhật graph trong test được rollback sau mỗi method. Điều đó giúp fixture không rò rỉ sang test tiếp theo.

Nếu test không chạy trong transaction, có thể xóa dữ liệu theo scope:

~~~cypher
MATCH (n)
WHERE n.testScope = $scope
DETACH DELETE n
~~~

Gắn testScope vào mọi node fixture và relationship fixture mà test sở hữu. DETACH DELETE xóa node cùng relationship liên quan; nếu nhiều test dùng chung graph, chỉ xóa node mang scope của test hiện tại.

Không chạy MATCH (n) DETACH DELETE n trên database dùng chung giữa nhiều test class. Lệnh này xóa toàn bộ graph data và có thể phá fixture của test khác. Với container dùng riêng cho một test class, xóa toàn bộ graph có thể chấp nhận được nhưng vẫn nên ưu tiên cleanup theo scope để dễ mở rộng.

Constraint và index là schema metadata. Xóa node không xóa constraint hoặc index. Với Testcontainers, schema tồn tại đến khi container bị hủy. Vì vậy:

- Tạo schema một lần trong bootstrap.
- Nạp và rollback hoặc xóa graph fixture theo từng test.
- Hủy container sau test class hoặc test suite.
- Không drop index/constraint sau từng method nếu các method khác cùng dùng schema đó.

Nếu bật chạy song song, dùng container/database riêng hoặc scope riêng cho từng test và bảo đảm không có thao tác cleanup chéo. JUnit extension của Testcontainers hiện được kiểm thử với execution tuần tự; chạy song song có thể gây side effect ngoài dự kiến.

## 11. Kiểm thử repository và relationship mapping

Một test repository nên xác minh cả kết quả truy vấn và graph đã được ánh xạ đúng:

~~~java
@Test
void findsOrderAndItsPlacedRelationship() {
    Order order = orderRepository.findByOrderCode("ORD-001")
        .orElseThrow();

    assertThat(order.getOrderCode()).isEqualTo("ORD-001");
    assertThat(order.getStatus()).isEqualTo("NEW");
    assertThat(order.getPerson().getPersonCode()).isEqualTo("P-001");
}
~~~

Đảm bảo query/repository method nạp relationship cần assertion. Nếu entity khai báo relationship nhưng truy vấn chỉ trả một node chưa nạp graph liên quan, assertion trên relationship có thể không phản ánh mapping bạn muốn kiểm tra.

Nên có test cho:

- Lưu entity có relationship rồi đọc lại graph.
- Relationship property như placedAt, quantity hoặc role.
- Repository derived query và custom Cypher query.
- Kết quả rỗng khi không có business key phù hợp.
- Nhiều node liên quan để phát hiện lỗi nhân bản hoặc thiếu kết quả.

## 12. Kiểm thử index và query plan

Index có hai khía cạnh cần xác minh:

1. Index được tạo đúng schema và đã ở trạng thái ONLINE.
2. Truy vấn có predicate tương thích để planner có thể tận dụng index.

Ví dụ kiểm tra index online:

~~~cypher
SHOW INDEXES
YIELD name, state, properties
WHERE name = 'order_status_created_at'
RETURN name, state, properties
~~~

Sau đó kiểm tra query plan:

~~~cypher
EXPLAIN
MATCH (o:Order)
WHERE o.status = $status
  AND o.createdAt >= $from
RETURN o
ORDER BY o.createdAt
~~~

EXPLAIN hiển thị kế hoạch dự kiến mà không thực thi truy vấn. PROFILE thực thi truy vấn và bổ sung số liệu thực tế như số row và database hits. Dùng cả hai trên tập dữ liệu đủ đại diện nếu cần đánh giá hiệu năng.

Tránh khẳng định một test chức năng phải có đúng một operator hoặc số database hits cố định. Planner có thể thay đổi theo phiên bản Neo4j, thống kê, kích thước dữ liệu và độ chọn lọc. Trong test chức năng, xác minh index ONLINE và kết quả truy vấn đúng. Dành assertion về latency, throughput hoặc query plan cho bộ test hiệu năng riêng với dữ liệu và môi trường được kiểm soát.

## 13. Test transaction imperative và reactive

Với repository imperative, @DataNeo4jTest mặc định dùng transaction test và rollback khi method kết thúc. Có thể tạo fixture qua repository hoặc Neo4jClient trong @BeforeEach, thực hiện assertion trong test rồi để Spring rollback.

Với reactive repository:

- Không dựa vào transaction imperative mặc định để rollback reactive pipeline.
- Dùng TransactionalOperator khi cần xác minh transaction reactive.
- Chờ pipeline hoàn tất bằng Reactor Test như StepVerifier.
- Dùng business key hoặc scope riêng và cleanup tường minh khi test không rollback.

Với @SpringBootTest(webEnvironment = RANDOM_PORT), request HTTP chạy trong thread và transaction riêng so với transaction của test method. Rollback transaction ở test không tự rollback transaction do server xử lý. Hãy cleanup dữ liệu được tạo qua HTTP hoặc thiết kế fixture có scope riêng.

## 14. Kiểm thử Enterprise-only constraint

Property existence, property type và key constraint chỉ khả dụng trên Neo4j Enterprise Edition. Nếu ứng dụng phụ thuộc các quy tắc này, test phải chạy đúng edition để tránh bỏ sót lỗi.

Ví dụ image Enterprise trong Testcontainers cần chấp nhận license theo hướng dẫn của Neo4j:

~~~java
Neo4jContainer neo4j = new Neo4jContainer("neo4j:5.26-enterprise")
    .withEnv("NEO4J_ACCEPT_LICENSE_AGREEMENT", "yes")
    .withAdminPassword("test-password");
~~~

Ví dụ trên cần image Enterprise và điều khoản license hợp lệ. Nếu dự án chỉ dùng Community Edition, hãy kiểm thử uniqueness constraint trong Neo4j và kiểm thử các quy tắc bắt buộc/kiểu dữ liệu tại service validator tương ứng.

Không giả lập Enterprise constraint bằng một test chỉ kiểm tra Java validation rồi kết luận database đã bảo vệ quy tắc. Hai lớp bảo vệ cần được kiểm thử riêng.

## 15. Những lỗi thường gặp

**Dùng database đang có dữ liệu từ lần chạy trước.** Test có thể phụ thuộc dữ liệu còn sót. Dùng Testcontainers hoặc Test Harness riêng và fixture được tạo có kiểm soát.

**Dùng phiên bản Neo4j khác production.** Test có thể bỏ lỡ khác biệt Cypher, constraint hoặc planner. Pin image phù hợp với phiên bản triển khai.

**Cho rằng @DataNeo4jTest tự khởi chạy Neo4j.** Test slice cấu hình Spring Data Neo4j, còn endpoint database vẫn phải được cung cấp.

**Nạp fixture trước khi tạo constraint.** Dữ liệu trùng hoặc thiếu property có thể khiến tạo constraint thất bại. Tạo schema trước rồi nạp dữ liệu hợp lệ.

**Cho rằng IF NOT EXISTS xác minh schema.** Lệnh này không thay thế kiểm tra tên, loại, label và property thực tế bằng SHOW CONSTRAINTS/SHOW INDEXES.

**Tạo index rồi truy vấn ngay.** Index có thể đang POPULATING. Dùng db.awaitIndex() hoặc db.awaitIndexes() trước test phụ thuộc index.

**Dùng cùng business key cho nhiều test chạy song song.** Constraint uniqueness sẽ tạo xung đột. Dùng namespace hoặc container riêng cho từng test.

**Xóa toàn bộ graph trong cleanup.** MATCH (n) DETACH DELETE n có thể xóa fixture do test khác sở hữu. Cleanup theo testScope.

**Cho rằng rollback xóa schema.** Rollback dữ liệu test không phải cách quản lý vòng đời index và constraint. Bootstrap schema riêng và hủy container sau suite.

**Dựa vào internal node ID trong fixture.** ID nội bộ có thể thay đổi giữa các lần chạy. Dùng business key có ý nghĩa.

**So sánh query plan cứng giữa mọi phiên bản.** Planner và thống kê thay đổi. Xác minh index state trong test chức năng, đo hiệu năng trong suite chuyên biệt.

**Dùng @Transactional imperative cho reactive test.** Transaction reactive cần TransactionalOperator hoặc cách quản lý vòng đời reactive riêng.

## 16. Tự kiểm tra

1. Fixture Neo4j gồm những thành phần nào?
2. Khi nào nên chọn Test Harness và khi nào nên chọn Testcontainers?
3. @DataNeo4jTest cấu hình những thành phần gì và có tự khởi chạy Neo4j server không?
4. Vì sao nên pin image Neo4j theo phiên bản production?
5. Vì sao phải tạo constraint trước khi nạp dữ liệu fixture?
6. Uniqueness constraint có bắt buộc property phải tồn tại không?
7. IF NOT EXISTS có thay thế việc xác minh schema không?
8. Vì sao phải đợi index ở trạng thái ONLINE?
9. Làm thế nào để cleanup fixture mà không xóa dữ liệu của test khác?
10. Vì sao transaction rollback mặc định không áp dụng tương tự cho reactive access hoặc HTTP request chạy qua server?
11. Khi nào nên kiểm tra EXPLAIN và khi nào nên dùng PROFILE?

**Bài tập thực hành:** Tạo test slice cho OrderRepository bằng @DataNeo4jTest và một Neo4j Testcontainer cùng phiên bản production. Bootstrap uniqueness constraint cho Order.orderCode và range index cho (status, createdAt), sau đó đợi index online. Tạo fixture gồm hai Person, ba Order và relationship PLACED; mỗi test dùng một scope riêng. Viết test đọc Order cùng Person relationship, test lọc Order theo status và khoảng ngày, test từ chối orderCode trùng trong transaction độc lập, và test xác minh index có trạng thái ONLINE. Chạy lại suite hai lần liên tiếp để xác nhận dữ liệu không rò rỉ giữa các lần chạy.

## Tài liệu tham khảo

- [Spring Data Neo4j — Testing](https://docs.spring.io/spring-data/neo4j/reference/testing.html)
- [Spring Data Neo4j — Testing with Spring Boot and @DataNeo4jTest](https://docs.spring.io/spring-data/neo4j/reference/testing/testing-with-spring-boot.html)
- [Spring Boot 4.2 — Auto-configured Data Neo4j Tests](https://docs.spring.io/spring-boot/reference/testing/spring-boot-applications.html)
- [Testcontainers for Java — Neo4j Module](https://java.testcontainers.org/modules/databases/neo4j/)
- [Testcontainers for Java — Jupiter / JUnit 5](https://java.testcontainers.org/test_framework_integration/junit_5/)
- [Neo4j Cypher Manual — Constraints](https://neo4j.com/docs/cypher-manual/current/schema/constraints/)
- [Neo4j Cypher Manual — Create constraints](https://neo4j.com/docs/cypher-manual/current/schema/constraints/create-constraints/)
- [Neo4j Cypher Manual — Indexes](https://neo4j.com/docs/cypher-manual/current/indexes/)
- [Neo4j Cypher Manual — Show indexes](https://neo4j.com/docs/cypher-manual/current/indexes/performance-indexes/list-indexes/)
- [Neo4j Operations Manual — Built-in procedures (db.awaitIndex/db.awaitIndexes)](https://neo4j.com/docs/operations-manual/current/procedures/built-in-procedures/)
