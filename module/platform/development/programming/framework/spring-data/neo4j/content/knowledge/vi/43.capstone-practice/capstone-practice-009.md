# Kiểm thử bằng Testcontainers và đo truy vấn bằng PROFILE

Một ứng dụng Spring Data Neo4j (SDN) có thể chạy đúng trên máy phát triển nhưng thất bại khi triển khai vì query Cypher, schema, phiên bản Neo4j, transaction hoặc cách ánh xạ graph khác với môi trường thật. Kiểm thử bằng database giả lập không phát hiện đầy đủ các lỗi này. Một bài capstone hoàn chỉnh cần khởi chạy Neo4j thật trong Testcontainers, chạy repository và mapping qua SDN, sau đó đo execution plan bằng `PROFILE` trên dữ liệu có quy mô đủ lớn.

Trong bài thực hành này, bạn xây dựng một lát cắt ứng dụng quản lý nhân viên và phòng ban. Mỗi `Person` làm việc tại một `Department` thông qua relationship `WORKS_IN`. Bạn sẽ kiểm thử custom repository query, xác minh relationship mapping, tạo dữ liệu thử nghiệm có kiểm soát, so sánh plan trước và sau khi tạo index, rồi ghi lại bằng chứng hiệu năng.

Kết quả cần có là một bộ integration test chạy trên Neo4j container, một truy vấn có PROFILE đo được và một báo cáo ngắn giải thích vì sao plan thay đổi.

## Kiến trúc capstone

Lát cắt nghiệp vụ gồm ba thành phần chính:

- `Person`: nhân viên, có mã nhân viên và email.
- `Department`: phòng ban, có mã và tên.
- `WORKS_IN`: relationship từ nhân viên tới phòng ban.

~~~mermaid
flowchart LR
    T["JUnit 5 test"] --> S["Spring Boot test slice"]
    S --> R["PersonRepository"]
    S --> C["Neo4jClient"]
    R --> N["Neo4j Driver"]
    C --> N
    N --> TC["Neo4j trong Testcontainers"]
    TC --> G["Person - WORKS_IN - Department"]
    G --> P["Cypher PROFILE"]
~~~

Bài thực hành sử dụng hai kiểu kiểm tra khác nhau:

| Kiểu kiểm tra | Công cụ | Mục đích |
|---|---|---|
| Integration test | `@DataNeo4jTest` + Testcontainers | Xác minh query, transaction, entity và relationship mapping trên Neo4j thật |
| Query profiling | Cypher `PROFILE` qua Neo4j Browser hoặc Java Driver | Xem operator, số hàng thực tế, DB Hits và chi phí truy vấn |

Testcontainers tạo một Neo4j DBMS dùng riêng cho test. Spring Boot kết nối tới Bolt endpoint động do container cung cấp. Khi test kết thúc, container được dừng và xóa theo lifecycle của JUnit.

## Chuẩn bị dependency

Ứng dụng cần dependency SDN ở phạm vi chính, thường được quản lý qua Spring Boot:

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.testcontainers</groupId>
            <artifactId>testcontainers-bom</artifactId>
            <version>2.0.5</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>

<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-data-neo4j</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>
    <dependency>
        <groupId>org.testcontainers</groupId>
        <artifactId>testcontainers-neo4j</artifactId>
        <scope>test</scope>
    </dependency>
    <dependency>
        <groupId>org.testcontainers</groupId>
        <artifactId>testcontainers-junit-jupiter</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
~~~

Ví dụ dùng Testcontainers 2.x và BOM để đồng bộ phiên bản giữa core, Neo4j module và JUnit Jupiter integration. Nếu dự án đang dùng Testcontainers 1.x, hãy theo đúng artifact và package của major version đó; không trộn API 1.x với dependency 2.x.

Container cần một Docker API-compatible runtime như Docker Desktop, Docker Engine hoặc Testcontainers Cloud. CI cũng phải cung cấp container runtime hoạt động. Không cấu hình test kết nối tới một Neo4j cài sẵn trên máy lập trình viên.

Pin image Neo4j theo phiên bản tương thích với môi trường triển khai. Ví dụ dưới đây dùng `neo4j:5.26-community`; hãy thay bằng đúng phiên bản server mà ứng dụng hỗ trợ. Tránh dùng tag `latest` vì một lần pull image mới có thể âm thầm thay đổi hành vi test.

## Khai báo domain model

Entity `Department`:

~~~java
import org.springframework.data.neo4j.core.schema.Id;
import org.springframework.data.neo4j.core.schema.Node;
import org.springframework.data.annotation.Version;

@Node("Department")
public class Department {

    @Id
    private String departmentCode;

    private String name;

    @Version
    private Long version;

    protected Department() {
    }

    public Department(String departmentCode, String name) {
        this.departmentCode = departmentCode;
        this.name = name;
    }

    public String getDepartmentCode() {
        return departmentCode;
    }

    public String getName() {
        return name;
    }
}
~~~

Entity `Person` có một relationship hướng ra ngoài tới phòng ban:

~~~java
import org.springframework.data.neo4j.core.schema.Id;
import org.springframework.data.neo4j.core.schema.Node;
import org.springframework.data.neo4j.core.schema.Relationship;
import org.springframework.data.annotation.Version;

@Node("Person")
public class Person {

    @Id
    private String employeeCode;

    private String email;

    private String fullName;

    private boolean active;

    @Version
    private Long version;

    @Relationship(type = "WORKS_IN")
    private Department department;

    protected Person() {
    }

    public String getEmployeeCode() {
        return employeeCode;
    }

    public String getEmail() {
        return email;
    }

    public String getFullName() {
        return fullName;
    }

    public boolean isActive() {
        return active;
    }

    public Department getDepartment() {
        return department;
    }
}
~~~

Trong ví dụ này, `employeeCode` và `departmentCode` là business ID được lưu trên node. Vì các ID này được gán sẵn, hai entity có `@Version Long` để SDN phân biệt entity mới với entity đã lưu và áp dụng optimistic locking khi cập nhật. Fixture đặt `version: 0` cho node đã tồn tại. Khi dùng business ID làm `@Id`, dữ liệu cần có uniqueness constraint tương ứng. Ở bài capstone, schema có thể được tạo trước bằng migration:

~~~cypher
CREATE CONSTRAINT person_employee_code_unique
IF NOT EXISTS
FOR (p:Person)
REQUIRE p.employeeCode IS UNIQUE;
~~~

~~~cypher
CREATE CONSTRAINT department_code_unique
IF NOT EXISTS
FOR (d:Department)
REQUIRE d.departmentCode IS UNIQUE;
~~~

Đưa từng lệnh schema vào migration tương ứng. Không đặt nhiều statement độc lập trong một lời gọi `Neo4jClient.query()` nếu client/server chỉ nhận một statement.

Trong ứng dụng thực tế, chạy cùng bộ migration trên Testcontainers trước khi kiểm thử để schema trong test khớp môi trường triển khai. Riêng bài đo index bên dưới cố ý bắt đầu với database chưa có index trên `Person.email`; nếu migration đã tạo index này, baseline phải dùng database/schema riêng hoặc bỏ bước so sánh scan ban đầu.

## Viết repository query trả đầy đủ graph

Repository tìm các nhân viên thuộc một phòng ban:

~~~java
import java.util.List;
import org.springframework.data.neo4j.repository.Neo4jRepository;
import org.springframework.data.neo4j.repository.query.Query;
import org.springframework.data.repository.query.Param;

public interface PersonRepository extends Neo4jRepository<Person, String> {

    @Query("""
        MATCH (p:Person)-[r:WORKS_IN]->(d:Department)
        WHERE d.departmentCode = $departmentCode
        RETURN p, r, d
        ORDER BY p.employeeCode
        """)
    List<Person> findPeopleInDepartment(
        @Param("departmentCode") String departmentCode
    );
}
~~~

Custom query trả `p`, `r` và `d` để SDN có đủ node và relationship dựng aggregate `Person`. Nếu chỉ trả `p`, phần `department` trong entity có thể không được hydrate từ kết quả. Một entity đọc thiếu graph có thể không phù hợp để dùng làm aggregate ghi lại.

`ORDER BY p.employeeCode` tạo thứ tự ổn định cho kết quả và giúp test không phụ thuộc vào thứ tự mặc định của database. Cypher không đảm bảo thứ tự hàng nếu query không có `ORDER BY`.

## Cấu hình Neo4j Testcontainer

Tạo integration test slice và kết nối Spring Boot với container:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.data.neo4j.DataNeo4jTest;
import org.springframework.data.neo4j.core.Neo4jClient;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.neo4j.Neo4jContainer;
import org.testcontainers.utility.DockerImageName;

@Testcontainers
@DataNeo4jTest
class PersonRepositoryIntegrationTest {

    @Container
    static final Neo4jContainer neo4j =
        new Neo4jContainer(
            DockerImageName.parse("neo4j:5.26-community")
        ).withAdminPassword("test-password");

    @DynamicPropertySource
    static void neo4jProperties(DynamicPropertyRegistry registry) {
        registry.add("spring.neo4j.uri", neo4j::getBoltUrl);
        registry.add(
            "spring.neo4j.authentication.username",
            () -> "neo4j"
        );
        registry.add(
            "spring.neo4j.authentication.password",
            neo4j::getAdminPassword
        );
    }

    @Autowired
    PersonRepository people;

    @Autowired
    Neo4jClient client;
}
~~~

`@DynamicPropertySource` đăng ký URI và thông tin xác thực sau khi container được khởi động. Không hard-code cổng Bolt vì Testcontainers ánh xạ cổng động. `@DataNeo4jTest` cung cấp repository, transaction manager, client và template của SDN; nó không tự khởi chạy database, vì vậy container phải được cấu hình riêng.

`@DataNeo4jTest` còn thêm một imperative `@Transactional` ngầm định cho mỗi test. Các thay đổi dữ liệu trong test thường được rollback khi kết thúc. Với reactive test, transaction ngầm định của Spring test không tự chuyển thành reactive transaction; dùng `TransactionalOperator` hoặc service có reactive transaction phù hợp.

Container khai báo bằng field `static` và `@Container` được chia sẻ giữa các method trong cùng test class. JUnit Jupiter extension của Testcontainers hiện được kiểm thử cho chạy tuần tự; không bật parallel execution cho các test đang chia sẻ container và database này nếu chưa thiết kế cách cô lập dữ liệu. Khi Spring context được cache qua nhiều test class, cần quản lý vòng đời container phù hợp để context không trỏ tới container đã dừng.

## Tạo fixture có thể lặp lại

Trong cùng test class, thêm phương thức tạo dữ liệu:

~~~java
import java.util.List;
import java.util.Map;

private void createFixture() {
    client.query("""
        CREATE
            (:Department {
                departmentCode: "D-PLATFORM",
                name: "Platform",
                version: 0
            }),
            (:Department {
                departmentCode: "D-OPS",
                name: "Operations",
                version: 0
            })
        """)
        .run();

    client.query("""
        UNWIND $people AS row
        MATCH (d:Department {departmentCode: row.departmentCode})
        CREATE (p:Person {
            employeeCode: row.employeeCode,
            email: row.email,
            fullName: row.fullName,
            active: row.active,
            version: 0
        })-[:WORKS_IN]->(d)
        """)
        .bind(List.of(
            Map.of(
                "employeeCode", "E-001",
                "email", "lan@example.test",
                "fullName", "Lan Nguyen",
                "active", true,
                "departmentCode", "D-PLATFORM"
            ),
            Map.of(
                "employeeCode", "E-002",
                "email", "minh@example.test",
                "fullName", "Minh Tran",
                "active", true,
                "departmentCode", "D-PLATFORM"
            ),
            Map.of(
                "employeeCode", "E-003",
                "email", "an@example.test",
                "fullName", "An Pham",
                "active", false,
                "departmentCode", "D-PLATFORM"
            ),
            Map.of(
                "employeeCode", "E-004",
                "email", "binh@example.test",
                "fullName", "Binh Le",
                "active", true,
                "departmentCode", "D-OPS"
            )
        ))
        .to("people")
        .run();
}
~~~

Fixture có hai phòng ban, ba nhân viên ở Platform và một nhân viên ở Operations. Có cả nhân viên inactive để kiểm tra các predicate trạng thái ở những phần mở rộng sau này.

Gọi `createFixture()` trực tiếp trong từng test nghiệp vụ. Vì `@DataNeo4jTest` chạy test trong transaction imperative, fixture và thao tác repository trong cùng test được rollback sau test. Không cần xóa toàn bộ graph bằng `MATCH (n) DETACH DELETE n` ở đầu từng test khi đang dùng cơ chế rollback này. Test profiling có `NOT_SUPPORTED` nên tự seed và cleanup dữ liệu riêng.

## Kiểm thử repository và relationship mapping

Test query theo phòng ban:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

@Test
void queryReturnsPeopleAndHydratesDepartment() {
    createFixture();

    List<Person> result =
        people.findPeopleInDepartment("D-PLATFORM");

    assertThat(result)
        .extracting(Person::getEmployeeCode)
        .containsExactly("E-001", "E-002", "E-003");

    assertThat(result)
        .allSatisfy(person -> {
            assertThat(person.getDepartment()).isNotNull();
            assertThat(person.getDepartment().getDepartmentCode())
                .isEqualTo("D-PLATFORM");
            assertThat(person.getDepartment().getName())
                .isEqualTo("Platform");
        });
}
~~~

Test tham số không khớp:

~~~java
@Test
void queryReturnsEmptyListForUnknownDepartment() {
    createFixture();

    assertThat(people.findPeopleInDepartment("D-MISSING"))
        .isEmpty();
}
~~~

Test kiểm tra thứ tự kết quả vì query cam kết `ORDER BY p.employeeCode`:

~~~java
@Test
void queryUsesStableEmployeeCodeOrdering() {
    createFixture();

    List<Person> result =
        people.findPeopleInDepartment("D-PLATFORM");

    assertThat(result)
        .extracting(Person::getEmployeeCode)
        .containsExactly("E-001", "E-002", "E-003");
}
~~~

Những assertion này kiểm tra đồng thời Cypher, bind parameter, dữ liệu trả về và mapping relationship. Nếu query chỉ trả Person mà thiếu relationship, test đầu sẽ phát hiện `department` null hoặc không đúng phòng ban.

Không chỉ kiểm tra số lượng kết quả. Hai query có thể cùng trả ba Person nhưng một query trả sai phòng ban hoặc thiếu relationship. Integration test cần xác minh cả property và graph structure mà use case yêu cầu.

## Tách test nghiệp vụ khỏi test đo hiệu năng

Một bộ integration test nên có hai nhóm:

1. **Test nghiệp vụ:** dùng fixture nhỏ, chạy nhanh, xác minh query và mapping. Các test này phù hợp với transaction rollback của `@DataNeo4jTest`.
2. **Test profiling:** tạo graph đủ lớn, tạo index, chạy `PROFILE` và thu thập execution plan. Test này cần chủ động quản lý transaction và dữ liệu vì PROFILE thực thi query thật.

Không dùng kết quả của một fixture bốn nhân viên để kết luận index có cải thiện hiệu năng trên graph lớn. Query plan được chọn dựa trên schema, statistics, cardinality và phân bố dữ liệu; dữ liệu quá nhỏ có thể khiến planner chọn scan dù index tồn tại.

## Tạo dữ liệu lớn cho bài đo

Trong profiling test, dùng `Driver` để tạo dữ liệu qua session riêng. Ví dụ tạo 100 phòng ban và 10.000 nhân viên:

~~~java
private void seedPerformanceDataset(Session session) {
    int departmentCount = 100;
    int personCount = 10_000;

    session.run("""
        UNWIND range(1, $departmentCount) AS i
        CREATE (:Department {
            departmentCode: "D-" + toString(i),
            name: "Department " + toString(i),
            version: 0
        })
        """, Map.of("departmentCount", departmentCount))
        .consume();

    session.run("""
        UNWIND range(1, $personCount) AS i
        MATCH (d:Department {
            departmentCode:
                "D-" + toString(((i - 1) % $departmentCount) + 1)
        })
        CREATE (p:Person {
            employeeCode: "E-" + toString(i),
            email: "person" + toString(i) + "@example.test",
            fullName: "Person " + toString(i),
            active: i % 5 <> 0,
            version: 0
        })-[:WORKS_IN]->(d)
        """, Map.of(
            "personCount", personCount,
            "departmentCount", departmentCount
        ))
        .consume();
}
~~~

`UNWIND` sinh dữ liệu theo dãy số, còn phép modulo phân bổ nhân viên đều vào các phòng ban. Dữ liệu có email duy nhất, thuận tiện để đo truy vấn tìm một nhân viên theo email.

Với dataset lớn hơn, chia dữ liệu thành các batch nhỏ và commit từng batch thay vì tạo một transaction rất dài. Dùng dữ liệu tổng hợp có phân bố gần workload thực tế: độ lệch số nhân viên giữa phòng ban, tỷ lệ active, độ trùng email/business key và số relationship trên mỗi node đều có thể ảnh hưởng execution plan.

## Đo query plan bằng EXPLAIN và PROFILE

`EXPLAIN` lập execution plan nhưng không thực thi query. Kết quả cho biết operator và số hàng ước lượng.

`PROFILE` thực thi query và trả execution plan cùng số liệu thực tế như Rows, DB Hits và memory. PROFILE có thể thực thi cả thao tác ghi nếu câu Cypher là query ghi; chỉ dùng trên database test hoặc với query đã được xác nhận là an toàn.

Query dùng để đo:

~~~cypher
MATCH (p:Person {email: $email})-[:WORKS_IN]->(d:Department)
RETURN p.employeeCode AS employeeCode,
       d.departmentCode AS departmentCode;
~~~

Trước khi tạo index, có thể chạy trong Neo4j Browser hoặc Cypher Shell:

~~~cypher
EXPLAIN
MATCH (p:Person {email: $email})-[:WORKS_IN]->(d:Department)
RETURN p.employeeCode AS employeeCode,
       d.departmentCode AS departmentCode;
~~~

Sau đó đo thực tế:

~~~cypher
PROFILE
MATCH (p:Person {email: $email})-[:WORKS_IN]->(d:Department)
RETURN p.employeeCode AS employeeCode,
       d.departmentCode AS departmentCode;
~~~

Trong Neo4j Browser, khai báo parameter trước khi chạy:

~~~cypher
:param email => "person9000@example.test";
~~~

Không so sánh thời gian của một lần chạy lạnh với một lần chạy nóng. Lần đầu có thể phải nạp dữ liệu vào page cache, trong khi lần sau đọc nhiều dữ liệu từ cache. Hãy chạy nhiều lần, ghi rõ trạng thái cache và so sánh DB Hits/Rows cùng execution plan.

## So sánh scan và index seek

Với dataset capstone, tạo range index cho email:

~~~cypher
CREATE RANGE INDEX person_email_range
IF NOT EXISTS
FOR (p:Person)
ON (p.email);
~~~

Chờ index population hoàn tất trước khi đo:

~~~cypher
CALL db.awaitIndexes(60);
~~~

Chạy lại `EXPLAIN` và `PROFILE` với cùng query và parameter.

Kế hoạch trước khi có index thường có dạng:

~~~text
NodeByLabelScan
  -> Filter
  -> Expand
  -> ProduceResults
~~~

Kế hoạch sau khi có index có thể có dạng:

~~~text
NodeIndexSeek
  -> Expand
  -> ProduceResults
~~~

Tên operator và cách planner tổ chức plan có thể thay đổi theo phiên bản Neo4j, runtime và thống kê. Điều cần quan sát là điểm bắt đầu có dùng index seek không, số hàng trung gian có giảm không và DB Hits có giảm không.

| Chỉ số | Trước index | Sau index |
|---|---|---|
| Điểm bắt đầu | Có thể quét toàn bộ label Person | Tìm Person bằng email index |
| Rows tại anchor | Có thể kiểm tra nhiều node | Thường chỉ còn node phù hợp |
| DB Hits | Thường cao hơn khi label lớn | Thường giảm với predicate chọn lọc |
| Relationship expansion | Bắt đầu sau khi lọc scan | Bắt đầu từ node được seek |
| Chi phí ghi | Không có index email cần duy trì | Ghi Person phải cập nhật index |

Index không làm cho mọi query nhanh hơn. Nếu predicate chọn ra phần lớn node, label scan có thể rẻ hơn index seek rồi truy cập từng record. Luôn so sánh plan trên dữ liệu và tham số đại diện.

## Thu thập PROFILE qua Neo4j Java Driver

Có thể tự động hóa việc lấy plan trong integration test bằng Driver. `ResultSummary.queryProfile()` trả profiling information sau khi kết quả đã được tiêu thụ.

Ví dụ helper chạy query và lấy phần biểu diễn plan:

~~~java
import java.util.Map;
import org.neo4j.driver.Result;
import org.neo4j.driver.Session;
import org.neo4j.driver.summary.QueryProfile;
import org.neo4j.driver.summary.ResultSummary;

private record ProfileSnapshot(
    String plan,
    long rows,
    long dbHits
) {
}

private ProfileSnapshot profileQuery(Session session, String email) {
    Result result = session.run("""
        PROFILE
        MATCH (p:Person {email: $email})-[:WORKS_IN]->(d:Department)
        RETURN p.employeeCode AS employeeCode,
               d.departmentCode AS departmentCode
        """, Map.of("email", email));

    var rows = result.list();
    ResultSummary summary = result.consume();
    QueryProfile profile = summary.queryProfile().orElseThrow();

    assertThat(rows).hasSize(1);

    return new ProfileSnapshot(
        profile.arguments().get("string-representation").asString(),
        rows.size(),
        totalDbHits(profile)
    );
}

private long totalDbHits(QueryProfile profile) {
    long ownHits = profile.dbHits().orElse(0L);
    long childHits = profile.children().stream()
        .mapToLong(this::totalDbHits)
        .sum();
    return ownHits + childHits;
}
~~~

`ResultSummary` chỉ sẵn sàng sau khi stream record được tiêu thụ. `list()` giữ các record trong bộ nhớ; với query trả nhiều hàng, cân nhắc chỉ tiêu thụ nếu không cần giữ toàn bộ kết quả. Trong ví dụ, query được giới hạn bởi email duy nhất nên chỉ có một hàng.

Helper `totalDbHits` cộng DB Hits của từng operator trong cây plan. Neo4j hiển thị tổng DB Hits ở footer; việc cộng đệ quy giúp lưu cùng một số tổng trong báo cáo tự động:

~~~java
ProfileSnapshot snapshot = profileQuery(session, "person9000@example.test");
System.out.println(snapshot.plan());
System.out.println("Rows=" + snapshot.rows());
System.out.println("DB Hits=" + snapshot.dbHits());
~~~

Với Java Driver 6.2 trở lên, dùng `queryProfile()` và `QueryProfile`. Các API `profile()` và `ProfiledPlan` cũ đã được thay thế trong Driver hiện hành.

## Tích hợp profiling test với Testcontainers

Thêm `Driver` vào test class:

~~~java
import org.neo4j.driver.Driver;
import org.neo4j.driver.Session;
import org.neo4j.driver.SessionConfig;
import org.neo4j.driver.Result;
import org.neo4j.driver.summary.ResultSummary;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;

@Autowired
Driver driver;
~~~

Test profiling cần transaction độc lập vì nó seed dữ liệu, tạo index và chạy nhiều auto-commit statement qua Driver. Tắt imperative test transaction cho method này:

~~~java
@Test
@Transactional(propagation = Propagation.NOT_SUPPORTED)
void profileLookupBeforeAndAfterIndex() {
    try (Session session = driver.session(
            SessionConfig.builder()
                .withDatabase("neo4j")
                .build())) {

        String email = "person9000@example.test";

        try {
            seedPerformanceDataset(session);

            ProfileSnapshot before = profileQuery(session, email);

            session.run("""
                CREATE RANGE INDEX person_email_range
                IF NOT EXISTS
                FOR (p:Person)
                ON (p.email)
                """)
                .consume();

            session.run("CALL db.awaitIndexes(60)").consume();

            ProfileSnapshot after = profileQuery(session, email);

            assertThat(before.plan()).contains("NodeByLabelScan");
            assertThat(after.plan()).contains("NodeIndexSeek");
            assertThat(before.rows()).isEqualTo(after.rows());
            assertThat(before.dbHits()).isGreaterThan(after.dbHits());
        } finally {
            session.run("MATCH (n) DETACH DELETE n").consume();
        }
    }
}
~~~

Test trên giả định container là Neo4j mới, chưa có index email và phiên bản server cố định có các operator tương ứng. Nếu database đã được khởi tạo bằng migration có index, kết quả baseline sẽ khác. Hãy chạy baseline trước khi tạo index và bảo đảm fixture test không dùng chung database đã có schema từ test khác.

Trong code hoàn chỉnh, có thể đưa cleanup vào khối `finally` để graph vẫn được xóa nếu assertion thất bại. Container sẽ bị hủy khi test class kết thúc, nhưng cleanup giúp test dễ chạy lại nếu lifecycle container được tái sử dụng.

Không để test profiling phụ thuộc vào `@BeforeEach` fixture đang chạy trong transaction rollback rồi lại dùng một Driver session độc lập; hai session không tự chia sẻ transaction. Tạo dataset trực tiếp qua session như ví dụ hoặc chuyển toàn bộ thao tác fixture sang cùng cơ chế transaction mà test đang dùng.

## Đọc các chỉ số trong PROFILE

Một query plan có nhiều operator. Khi đọc plan, xem từ operator đầu vào tới operator trả kết quả và xác định bước nào tạo nhiều công việc nhất.

| Cột/chỉ số | Ý nghĩa | Cách sử dụng |
|---|---|---|
| Estimated Rows | Số hàng planner dự đoán | So với Rows để phát hiện estimate sai |
| Rows | Số hàng operator thực sự tạo ra | Tìm nơi số hàng tăng đột biến |
| DB Hits | Số lần truy cập storage/index theo đơn vị đo của Neo4j | Đánh giá khối lượng công việc database |
| Memory (Bytes) | Peak memory của operator | Tìm sort/aggregation cần nhiều bộ nhớ |
| Page Cache Hits/Misses | Số lần truy cập page cache | Đánh giá warm/cold cache; có thể phụ thuộc edition |
| Time (ms) | Thời gian pipeline/operator theo runtime | Dùng làm tín hiệu phụ, không phải benchmark duy nhất |

Một số operator thường gặp:

| Operator | Dấu hiệu |
|---|---|
| `NodeByLabelScan` | Quét node theo label |
| `AllNodesScan` | Quét toàn bộ node |
| `NodeIndexSeek` | Tìm node qua index |
| `NodeUniqueIndexSeek` | Tìm node bằng unique index/constraint |
| `Filter` | Lọc hàng sau operator trước |
| `Expand(All)` | Mở rộng relationship từ node đầu vào |
| `Sort` | Sắp xếp kết quả |
| `EagerAggregation` | Materialize dữ liệu trước khi tổng hợp |

DB Hits không phải số hàng trả về và cũng không phải số câu lệnh SQL. Đây là đơn vị công việc truy cập storage do Neo4j báo cáo. Một query chỉ trả một hàng vẫn có thể có DB Hits lớn nếu phải quét nhiều node hoặc mở rộng nhiều relationship.

Page cache statistics có thể không được cung cấp ở một số edition/cấu hình. Không coi thiếu page cache metrics là lỗi của query. Không so sánh số liệu page cache giữa lần chạy cold và warm.

## Cải thiện query sau khi đọc PROFILE

Nếu plan bắt đầu bằng `NodeByLabelScan` trên label lớn và sau đó `Filter` giữ lại một hàng, hãy kiểm tra predicate có thể được index hay không. Ví dụ, email là thuộc tính tìm kiếm chính xác và có tính chọn lọc cao, vì vậy range index phù hợp.

Nếu plan đã dùng `NodeIndexSeek` nhưng DB Hits vẫn lớn, hãy xem bước relationship traversal. Một node có thể có rất nhiều relationship; index chỉ giúp tìm anchor, không làm cho việc mở rộng graph miễn phí.

Các bước điều chỉnh phổ biến:

1. Chọn anchor node có predicate chọn lọc.
2. Tạo index cho predicate thường xuyên dùng.
3. Dùng relationship type và hướng cụ thể.
4. Giới hạn độ sâu traversal nếu nghiệp vụ không cần đường đi không giới hạn.
5. Trả về các property cần thiết thay vì toàn bộ graph.
6. Tránh `DISTINCT`, `ORDER BY` hoặc aggregation trên tập hàng lớn nếu không cần.
7. So sánh lại cùng query và parameter sau mỗi thay đổi.

Ví dụ query chọn lọc:

~~~cypher
MATCH (p:Person {email: $email})-[:WORKS_IN]->(d:Department)
RETURN p.employeeCode, d.departmentCode;
~~~

Ví dụ query mở rộng quá rộng:

~~~cypher
MATCH (p:Person)-[*1..5]-(connected)
WHERE p.email = $email
RETURN DISTINCT connected;
~~~

Nếu use case chỉ cần phòng ban của nhân viên, traversal nhiều bước và không giới hạn relationship type là thừa. Hãy mô tả chính xác đường graph nghiệp vụ cần đọc.

## Đo trước và sau một cách công bằng

Báo cáo hiệu năng phải giữ các điều kiện so sánh giống nhau:

- Cùng phiên bản Neo4j, Java Driver và schema.
- Cùng số node, relationship và phân bố property.
- Cùng query text và parameter.
- Cùng trạng thái index population.
- Cùng trạng thái page cache hoặc ghi rõ warm/cold.
- Cùng mức concurrency.
- Chạy nhiều lần và ghi lại p50/p95 nếu đo latency ở tầng ứng dụng.

Không lấy một lần chạy `PROFILE` làm kết luận production. PROFILE bổ sung instrumentation nên có overhead; thời gian của operator có thể phụ thuộc runtime và pipeline fusion. Dùng DB Hits, Rows và cấu trúc plan để tìm bottleneck; dùng load test hoặc metrics ứng dụng để đo latency thực tế.

Nếu query đã được gọi thường xuyên trong ứng dụng, hãy ghi nhận thêm thời gian end-to-end từ service, số lần gọi repository, độ trễ connection pool và chi phí mapping graph. Query plan chỉ mô tả phần thực thi ở database.

## Quy trình hoàn thành capstone

~~~mermaid
flowchart TD
    A["Khai báo entity và relationship"] --> B["Tạo PersonRepository @Query"]
    B --> C["Khởi chạy Neo4j Testcontainer"]
    C --> D["Kết nối Spring bằng DynamicPropertySource"]
    D --> E["Seed fixture nhỏ và kiểm thử mapping"]
    E --> F["Seed graph lớn cho profiling"]
    F --> G["PROFILE trước index"]
    G --> H["Tạo range index và awaitIndexes"]
    H --> I["PROFILE sau index"]
    I --> J["Đọc Rows, DB Hits và operator"]
    J --> K["Viết báo cáo và kết luận"]
~~~

Các deliverable phải có:

1. Entity `Person` và `Department` với relationship `WORKS_IN`.
2. Repository có custom `@Query` trả graph đầy đủ.
3. Testcontainers config với image Neo4j được pin version.
4. Integration test kiểm tra parameter, kết quả, thứ tự và relationship mapping.
5. Profiling test tạo graph đủ lớn, chạy `PROFILE` trước và sau index.
6. Báo cáo operator, Rows, DB Hits và index được sử dụng.
7. Giải thích giới hạn của số liệu và đề xuất tối ưu tiếp theo.

## Checklist đánh giá

| Tiêu chí | Đạt khi |
|---|---|
| Container lifecycle | Test tự khởi chạy và hủy Neo4j container |
| Version alignment | Image Neo4j tương thích với phiên bản triển khai |
| Dynamic connection | URI/credentials lấy từ container, không hard-code port |
| Test isolation | Fixture độc lập và không phụ thuộc thứ tự chạy |
| Query correctness | Kết quả và relationship đúng với fixture |
| Mapping | SDN hydrate được Department từ graph trả về |
| Dataset | Có đủ dữ liệu để planner lựa chọn index seek |
| Baseline | Lưu plan trước khi tạo index |
| Indexed plan | Xác minh index online và plan sau thay đổi |
| Metrics | Ghi Rows, DB Hits, memory và page cache nếu có |
| Interpretation | Giải thích operator và bước tốn chi phí |
| Repeatability | Có thể chạy lại test trên môi trường CI có container runtime |

## Lỗi thường gặp

| Lỗi | Hậu quả | Cách xử lý |
|---|---|---|
| Kết nối test tới Neo4j cài trên máy | Kết quả phụ thuộc môi trường và dữ liệu cũ | Dùng Testcontainers |
| Dùng tag `latest` | Test thay đổi khi image được cập nhật | Pin phiên bản Neo4j |
| Hard-code cổng Bolt | Test lỗi trong CI hoặc khi chạy song song | Dùng `getBoltUrl()` |
| Quên JUnit Jupiter integration | Annotation container không được xử lý | Thêm `testcontainers-junit-jupiter` |
| Dùng chung container khi chạy song song | Test có thể đọc/xóa dữ liệu của nhau | Tắt parallel hoặc cô lập database/fixture |
| Chỉ assert số lượng kết quả | Bỏ sót mapping relationship sai | Assert property và endpoint |
| Query không trả relationship/node cần ánh xạ | Aggregate bị thiếu dữ liệu | Trả đầy đủ graph trong custom query |
| Fixture quá nhỏ | Planner có thể chọn scan dù index có mặt | Dùng dataset profiling riêng |
| Không chờ index online | Query profile trước khi index sẵn sàng | Dùng `CALL db.awaitIndexes(...)` |
| Chỉ nhìn thời gian một lần chạy | Kết luận bị ảnh hưởng bởi cache và nhiễu | Lặp lại và ghi điều kiện đo |
| Cho rằng PROFILE chỉ đọc | Query ghi có thể thay đổi graph | Chỉ profile query đã xác nhận an toàn trên test DB |
| Coi DB Hits là số record | Đánh giá sai lượng công việc | Đọc Rows và DB Hits riêng biệt |
| Dùng `@DataNeo4jTest` transaction cho session Driver độc lập | Fixture và query profile có thể không nhìn thấy cùng dữ liệu | Dùng cùng transaction hoặc `Propagation.NOT_SUPPORTED` và quản lý session riêng |
| Cleanup toàn bộ graph dùng chung | Làm hỏng dữ liệu test khác | Cleanup theo scope hoặc dùng container/database riêng |
| Chỉ profile query, không đo tầng ứng dụng | Bỏ qua connection, mapping và service overhead | Kết hợp profiling với metrics/load test |

## Bài tập mở rộng

Sau khi hoàn thành lát cắt cơ bản, tiếp tục:

1. Tạo composite index cho truy vấn lọc nhân viên theo `active` và `departmentCode`; so sánh với range index email.
2. Thêm property `since` vào relationship `WORKS_IN` và profile truy vấn lọc theo thời gian bắt đầu.
3. Thêm query lấy danh sách nhân viên có phân trang, đo ảnh hưởng của `ORDER BY` và `SKIP` lớn.
4. Thử một Department có degree cao hơn nhiều phòng ban khác để quan sát chi phí `Expand(All)`.
5. So sánh trả toàn bộ entity graph với DTO chỉ chứa `employeeCode` và `departmentCode`.
6. Chạy profiling với nhiều parameter có cardinality khác nhau và giải thích vì sao plan/Rows có thể thay đổi.
7. Viết báo cáo ngắn đề xuất index và query shape phù hợp cho workload đọc/ghi của ứng dụng.

Khi hoàn thành capstone, bạn đã kiểm chứng được cả hai mặt của tầng dữ liệu SDN: repository và mapping hoạt động đúng trên Neo4j thật, đồng thời query plan được đo trên dữ liệu có quy mô thay vì suy đoán từ thời gian chạy một lần. Testcontainers giúp kiểm thử lặp lại trên database đúng phiên bản; `PROFILE` cung cấp bằng chứng về operator và khối lượng công việc database; các kết quả đó là cơ sở để chọn index, anchor và graph traversal phù hợp.

Tài liệu tham khảo chính thức:

- [Spring Data Neo4j - Testing with Spring Boot and @DataNeo4jTest](https://docs.spring.io/spring-data/neo4j/reference/testing/testing-with-spring-boot.html)
- [Testcontainers for Java - Neo4j module](https://java.testcontainers.org/modules/databases/neo4j/)
- [Testcontainers for Java - JUnit Jupiter integration](https://java.testcontainers.org/test_framework_integration/junit_5/)
- [Testcontainers for Java - Docker runtime requirements](https://java.testcontainers.org/supported_docker_environment/)
- [Neo4j Cypher Manual - Understanding query plans and PROFILE](https://neo4j.com/docs/cypher-manual/current/planning-and-tuning/execution-plans/)
- [Neo4j Java Driver Manual - Query execution summary and QueryProfile](https://neo4j.com/docs/java-manual/current/result-summary/)
- [Neo4j Java Driver API - QueryProfile](https://neo4j.com/docs/api/java-driver/current/org.neo4j.driver/org/neo4j/driver/summary/QueryProfile.html)

