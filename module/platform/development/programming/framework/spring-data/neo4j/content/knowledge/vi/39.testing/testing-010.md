# Kiểm thử @Query, ánh xạ record, projection và phân trang

Trong ứng dụng Spring Data Neo4j (SDN), một truy vấn tùy chỉnh có thể chạy đúng Cypher nhưng vẫn trả kết quả sai kiểu, thiếu relationship, ánh xạ nhầm alias hoặc phân trang sai tổng số phần tử. Vì vậy, kiểm thử không nên dừng ở việc xác nhận query không phát sinh exception. Cần kiểm tra dữ liệu graph đầu vào, tham số được bind, hình dạng record trả về, object/projection được tạo và metadata của trang.

Bài học này tập trung vào integration test cho repository có `@Query`, ánh xạ kết quả bằng Neo4j Driver `Record` qua `Neo4jClient`, interface projection và Java record DTO, cùng phân trang `Page`/`Slice`. Các ví dụ dùng graph nhân viên và phòng ban để minh họa cách xác minh cả node lẫn relationship.

## Mục tiêu và các lớp cần kiểm thử

Một custom query thường đi qua các lớp sau:

~~~text
JUnit test
   |
   v
Repository method / Neo4jClient
   |
   | Cypher + parameters
   v
Neo4j query execution
   |
   | records, nodes, relationships, scalar values
   v
SDN mapping / custom Record mapper
   |
   | entity, projection, Java record DTO
   v
Assertions
   |
   +--> values and relationships
   +--> empty/single/multiple results
   +--> page content and count
~~~

Mỗi lớp có một nhóm lỗi riêng:

| Thành phần | Điều cần xác minh |
|---|---|
| `@Query` | Cypher đúng, tham số bind đúng, predicate và hướng relationship đúng |
| Entity mapping | Property, ID và relationship được ánh xạ đầy đủ |
| Driver `Record` | Alias, kiểu dữ liệu, null và collection được đọc đúng |
| Java record DTO | Thứ tự/thành phần constructor và kiểu field khớp kết quả |
| Interface projection | Accessor khớp property của aggregate root |
| `Page` | Content, thứ tự, offset, total elements và total pages |
| `Slice` | Content và cờ hasNext |
| Test fixture | Dữ liệu độc lập, có đủ trường hợp biên và không phụ thuộc thứ tự test |

Nên dùng Neo4j thật trong integration test. Mock repository chỉ kiểm tra cách service gọi repository; nó không kiểm tra Cypher, query planner, constraint, driver record hay mapping thực tế.

## Chuẩn bị domain và repository mẫu

Ví dụ domain có Person làm aggregate root và Department được nối bằng relationship `WORKS_IN`:

~~~java
import org.springframework.data.neo4j.core.schema.Id;
import org.springframework.data.neo4j.core.schema.Node;
import org.springframework.data.neo4j.core.schema.Relationship;

@Node("Person")
public class Person {

    @Id
    private String employeeCode;

    private String fullName;

    private boolean active;

    @Relationship(type = "WORKS_IN")
    private Department department;

    protected Person() {
    }

    public Person(
            String employeeCode,
            String fullName,
            boolean active,
            Department department) {
        this.employeeCode = employeeCode;
        this.fullName = fullName;
        this.active = active;
        this.department = department;
    }

    public String getEmployeeCode() {
        return employeeCode;
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

~~~java
import org.springframework.data.neo4j.core.schema.Id;
import org.springframework.data.neo4j.core.schema.Node;

@Node("Department")
public class Department {

    @Id
    private String departmentCode;

    private String name;

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

Repository minh họa query tùy chỉnh:

~~~java
import java.util.List;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Slice;
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

    List<PersonSummary> findByActiveTrue();

    List<PersonCard> findAllByActiveTrue();

    Page<Person> findByActiveTrue(Pageable pageable);
}
~~~

Query trả cả node Person và Department để SDN có dữ liệu ánh xạ relationship đã khai báo trong entity. Trong ví dụ đơn giản này relationship không có property riêng. Nếu domain dùng `@RelationshipProperties`, query cần trả cả relationship và các node liên quan để mapping có đủ dữ liệu.

Nếu chỉ trả `p`, SDN có thể ánh xạ Person nhưng không có đủ thông tin để dựng Department trong graph kết quả. Một entity được tải một phần có thể gây mất hoặc ghi đè dữ liệu nếu sau đó dùng lại làm đối tượng ghi. Với custom query chỉ phục vụ đọc, cân nhắc trả projection hoặc DTO thay vì một aggregate bị thiếu dữ liệu.

## Dùng @DataNeo4jTest và Testcontainers

`@DataNeo4jTest` tạo Spring test slice tập trung vào repository, mapping và các thành phần SDN. Kết hợp Testcontainers để kiểm thử với Neo4j DBMS thực tế, dùng phiên bản gần với môi trường triển khai.

Ví dụ cấu hình test:

~~~java
import org.junit.jupiter.api.Test;
import static org.assertj.core.api.Assertions.assertThat;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.data.neo4j.DataNeo4jTest;
import org.springframework.data.neo4j.core.Neo4jClient;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.testcontainers.neo4j.Neo4jContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

@Testcontainers
@DataNeo4jTest
class PersonRepositoryIntegrationTest {

    @Container
    static final Neo4jContainer neo4j =
        new Neo4jContainer("neo4j:5")
            .withAdminPassword("test-password");

    @DynamicPropertySource
    static void neo4jProperties(DynamicPropertyRegistry registry) {
        registry.add("spring.neo4j.uri", neo4j::getBoltUrl);
        registry.add("spring.neo4j.authentication.username", () -> "neo4j");
        registry.add("spring.neo4j.authentication.password", neo4j::getAdminPassword);
    }

    @Autowired
    PersonRepository people;

    @Autowired
    Neo4jClient client;
}
~~~

Hãy pin image tag theo phiên bản Neo4j được dự án hỗ trợ thay vì để test tự đổi phiên bản bất ngờ. Dependency test cần có module Testcontainers Neo4j, JUnit Jupiter integration và Spring Boot test support tương ứng với phiên bản Spring Boot đang dùng.

Với Testcontainers 2.x, các artifact module có tiền tố `testcontainers-`; ví dụ Maven dependencies khi đã quản lý version bằng Testcontainers BOM:

~~~xml
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
~~~

`@DataNeo4jTest` phù hợp khi cần kiểm tra repository và mapping. Test slice này cung cấp transaction manager, client, template và repository; nó cũng có transaction imperative ngầm định nên các thay đổi trong test được rollback khi test kết thúc. Transaction ngầm định đó không tự bao bọc reactive publisher; nếu kiểm thử reactive repository/service, dùng `TransactionalOperator` hoặc transaction reactive tương ứng.

Dùng `@SpringBootTest` khi test cần service, security, transaction orchestration hoặc cấu hình ứng dụng đầy đủ. Với Testcontainers 2.x, lớp container nằm trong package `org.testcontainers.neo4j`; các bản 1.x dùng package cũ `org.testcontainers.containers`. Hãy đồng bộ import và artifact theo major version của Testcontainers. Nếu dùng JUnit extension với static container và Spring context cache qua nhiều test class, chú ý vòng đời container: container có thể dừng sau class đầu trong khi context được tái sử dụng. Với suite lớn, cân nhắc quản lý container theo vòng đời Spring context.

Không dùng mock Driver trong bài test cần chứng minh Cypher thực sự chạy trên database.

### Chuẩn bị fixture có thể lặp lại

Test fixture nên có dữ liệu đủ để phân biệt query đúng và query sai. Ví dụ:

- Department `D-PLATFORM` có ba Person đang làm việc.
- Department `D-OPS` có hai Person.
- Có ít nhất một Person inactive.
- Có mã nhân viên và tên khác nhau để kiểm tra thứ tự.
- Có thể tạo hai Person cùng tên nhưng khác employeeCode để phát hiện query vô tình group hoặc distinct theo tên.

Có thể tạo fixture bằng repository và `Neo4jClient`. Ví dụ Cypher setup:

~~~java
import java.util.List;
import java.util.Map;

void createFixture() {
    client.query("""
        CREATE (platform:Department {
            departmentCode: $platformCode,
            name: "Platform"
        })
        CREATE (ops:Department {
            departmentCode: $opsCode,
            name: "Operations"
        })
        WITH platform, ops
        UNWIND $people AS row
        MATCH (d:Department {departmentCode: row.departmentCode})
        CREATE (p:Person {
            employeeCode: row.employeeCode,
            fullName: row.fullName,
            active: row.active
        })-[:WORKS_IN]->(d)
        """)
        .bind("D-PLATFORM").to("platformCode")
        .bind("D-OPS").to("opsCode")
        .bind(List.of(
            Map.of("employeeCode", "E-001", "fullName", "Lan Nguyen",
                "active", true, "departmentCode", "D-PLATFORM"),
            Map.of("employeeCode", "E-002", "fullName", "Minh Tran",
                "active", true, "departmentCode", "D-PLATFORM"),
            Map.of("employeeCode", "E-003", "fullName", "An Pham",
                "active", false, "departmentCode", "D-PLATFORM"),
            Map.of("employeeCode", "E-004", "fullName", "Binh Le",
                "active", true, "departmentCode", "D-OPS"),
            Map.of("employeeCode", "E-005", "fullName", "Khanh Do",
                "active", true, "departmentCode", "D-OPS")
        )).to("people")
        .run();
}
~~~

Helper tạo project cho test mapper:

~~~java
void createProjectsFor(String employeeCode, int count) {
    client.query("""
        MATCH (p:Person {employeeCode: $employeeCode})
        UNWIND range(1, $count) AS sequence
        CREATE (p)-[:WORKS_ON]->(:Project {
            name: "Project " + toString(sequence)
        })
        """)
        .bind(employeeCode).to("employeeCode")
        .bind(count).to("count")
        .run();
}
~~~

Helper tạo thêm một relationship cùng type để kiểm tra query không đếm trùng root node:

~~~java
void createDuplicateWorkRelationship(String employeeCode, String departmentCode) {
    client.query("""
        MATCH (p:Person {employeeCode: $employeeCode})
        MATCH (d:Department {departmentCode: $departmentCode})
        CREATE (p)-[:WORKS_IN]->(d)
        """)
        .bind(employeeCode).to("employeeCode")
        .bind(departmentCode).to("departmentCode")
        .run();
}
~~~

Đoạn setup dùng tham số thay cho nối chuỗi Cypher. Trong test thực tế, gọi fixture trước từng test hoặc tạo dữ liệu với UUID để không xung đột. Nếu test slice đã quản lý transaction rollback cho mỗi test, có thể tận dụng ranh giới đó; nếu test chạy ngoài transaction hoặc chia sẻ database, cần cleanup rõ ràng và không xóa dữ liệu của test khác.

Không để một test phụ thuộc vào dữ liệu mà test khác tạo. Test phải chạy độc lập, chạy lại được và không phụ thuộc thứ tự JUnit thực thi.

## Kiểm thử custom @Query và parameter binding

Một test cho repository query cần xác minh ít nhất:

1. Query chỉ trả Person thuộc Department được chỉ định.
2. Tham số có giá trị khác nhau tạo kết quả tương ứng.
3. Không có Department phù hợp thì kết quả rỗng.
4. Kết quả có thứ tự ổn định nếu query cam kết sắp xếp.
5. Relationship trong entity được ánh xạ đúng.

Ví dụ:

~~~java
@Test
void customQueryReturnsPeopleAndTheirDepartment() {
    createFixture();

    List<Person> result = people.findPeopleInDepartment("D-PLATFORM");

    assertThat(result)
        .extracting(Person::getEmployeeCode)
        .containsExactly("E-001", "E-002", "E-003");

    assertThat(result)
        .allSatisfy(person -> {
            assertThat(person.getDepartment()).isNotNull();
            assertThat(person.getDepartment().getDepartmentCode())
                .isEqualTo("D-PLATFORM");
        });
}
~~~

Test trường hợp không có kết quả:

~~~java
@Test
void customQueryReturnsEmptyListWhenDepartmentDoesNotExist() {
    createFixture();

    assertThat(people.findPeopleInDepartment("D-MISSING"))
        .isEmpty();
}
~~~

### Kiểm tra named parameter

Dùng named parameter như `$departmentCode` và gắn rõ tên bằng `@Param`. Điều này giúp query không phụ thuộc vào việc compiler có giữ tên tham số Java hay không.

Test nên truyền giá trị có dấu nháy, dấu gạch hoặc ký tự Unicode để xác nhận dữ liệu được bind như value, không bị ghép vào câu Cypher:

~~~java
import java.util.UUID;

@Test
void queryBindsValueInsteadOfConcatenatingCypher() {
    String unusualCode = "D-'PLATFORM-Đ-" + UUID.randomUUID();
    String employeeCode = "E-" + UUID.randomUUID();

    client.query("""
            CREATE (d:Department {departmentCode: $code, name: "Test"})
            CREATE (p:Person {
                employeeCode: $employeeCode,
                fullName: "Test Person",
                active: true
            })-[:WORKS_IN]->(d)
            """)
        .bind(unusualCode).to("code")
        .bind(employeeCode).to("employeeCode")
        .run();

    List<Person> found = people.findPeopleInDepartment(unusualCode);
    assertThat(found)
        .extracting(Person::getEmployeeCode)
        .containsExactly(employeeCode);
}
~~~

Không nối input vào chuỗi Cypher. Named parameter vừa giữ đúng kiểu dữ liệu, vừa tránh lỗi escaping và giảm nguy cơ Cypher injection.

### Kiểm tra mapping relationship

Nếu query trả graph, hãy xác minh cả endpoint và relationship. Chỉ kiểm tra số lượng Person có thể bỏ sót trường hợp query trả đúng node nhưng không hydrate Department.

Ví dụ assertion:

~~~java
Person person = result.get(0);

assertThat(person.getDepartment()).isNotNull();
assertThat(person.getDepartment().getDepartmentCode())
    .isEqualTo("D-PLATFORM");
assertThat(person.getDepartment().getName())
    .isEqualTo("Platform");
~~~

Nếu relationship có property, chẳng hạn role hoặc assignedAt, hãy thêm entity `@RelationshipProperties` trong fixture và xác minh các property đó sau mapping. Nếu query chỉ trả một phần graph, không dùng entity đó để cập nhật aggregate trừ khi đã thiết kế rõ semantics của partial update.

## Kiểm thử projection

Projection giới hạn dữ liệu cần đọc khi use case chỉ cần một phần thuộc tính. Với interface projection, accessor phải khớp property của aggregate root.

Ví dụ projection:

~~~java
public interface PersonSummary {

    String getEmployeeCode();

    String getFullName();
}
~~~

Thêm query method:

~~~java
List<PersonSummary> findByActiveTrue();
~~~

Test xác minh các accessor của projection trả đúng dữ liệu:

~~~java
@Test
void interfaceProjectionReturnsOnlyTheRequestedView() {
    createFixture();

    List<PersonSummary> result = people.findByActiveTrue();

    assertThat(result)
        .extracting(PersonSummary::getEmployeeCode)
        .containsExactlyInAnyOrder("E-001", "E-002", "E-004", "E-005");

    assertThat(result)
        .extracting(PersonSummary::getFullName)
        .contains("Lan Nguyen", "Minh Tran", "Binh Le", "Khanh Do");
}
~~~

Interface projection là proxy đọc từ aggregate root. Nó không phải entity độc lập có thể sửa rồi lưu như một Person đầy đủ. Hãy kiểm tra accessor, tên property và nullability. Nếu cần dữ liệu nested, tạo projection con cho relationship thay vì trả nguyên aggregate nếu không cần.

Projection có accessor khớp trực tiếp với property của aggregate root được gọi là closed projection; SDN có thể tối ưu query vì biết chính xác những thuộc tính cần đọc. Nếu dùng accessor tính toán bằng `@Value` (open projection), framework không thể giới hạn dữ liệu theo cùng cách vì biểu thức có thể truy cập nhiều property. Với field nullable, có thể dùng `Optional<String>` làm kiểu trả về của accessor và kiểm tra cả trạng thái empty trong test.

### DTO projection và Java record

Class-based DTO projection phù hợp khi cần kiểu trả về rõ ràng và bất biến. Java record có thể dùng làm DTO nếu constructor component khớp với dữ liệu được SDN ánh xạ.

Ví dụ:

~~~java
public record PersonCard(
    String employeeCode,
    String fullName
) {
}
~~~

Repository có thể khai báo một method trả DTO projection:

~~~java
List<PersonCard> findAllByActiveTrue();
~~~

Test mapping các component của record:

~~~java
@Test
void recordDtoProjectionMapsConstructorComponents() {
    createFixture();

    List<PersonCard> cards = people.findAllByActiveTrue();

    assertThat(cards)
        .extracting(PersonCard::employeeCode)
        .containsExactlyInAnyOrder("E-001", "E-002", "E-004", "E-005");
}
~~~

Với DTO projection, hãy kiểm tra component names, kiểu dữ liệu và trường nullable. Một component sai tên hoặc kiểu có thể khiến mapping không thành công khi query được thực thi. DTO có thêm trường tùy chỉnh cần được query cung cấp đúng dữ liệu tương ứng; không giả định mọi property trong record tự tồn tại trong entity.

Đối với kết quả tổng hợp phức tạp, chẳng hạn số project của từng Person, dùng `Neo4jClient` và mapping tường minh qua `Record` thường dễ kiểm soát hơn.

## Ánh xạ Neo4j Driver Record thành Java record DTO

Neo4j Driver trả về mỗi hàng dưới dạng `org.neo4j.driver.Record`. Đây là record dữ liệu của Driver, khác với cú pháp Java `record` dùng khai báo DTO.

`Neo4jClient` cung cấp `fetchAs` và `mappedBy` để ánh xạ mỗi Driver Record thành kiểu kết quả mong muốn. Mapper nhận `TypeSystem` và `Record`, do đó có thể đọc từng cột theo alias.

DTO ví dụ:

~~~java
public record PersonProjectSummary(
    String employeeCode,
    String fullName,
    long projectCount
) {
}
~~~

Phương thức đọc:

~~~java
import java.util.Optional;
import org.springframework.data.neo4j.core.Neo4jClient;

public class PersonReadQueries {

    private final Neo4jClient client;

    public PersonReadQueries(Neo4jClient client) {
        this.client = client;
    }

    public Optional<PersonProjectSummary> findProjectSummary(
            String employeeCode) {

        return client.query("""
                MATCH (p:Person {employeeCode: $employeeCode})
                OPTIONAL MATCH (p)-[:WORKS_ON]->(project:Project)
                RETURN p.employeeCode AS employeeCode,
                       p.fullName AS fullName,
                       count(project) AS projectCount
                """)
            .bind(employeeCode).to("employeeCode")
            .fetchAs(PersonProjectSummary.class)
            .mappedBy((typeSystem, record) ->
                new PersonProjectSummary(
                    record.get("employeeCode").asString(),
                    record.get("fullName").asString(),
                    record.get("projectCount").asLong()
                )
            )
            .one();
    }
}
~~~

Mapper phải đọc đúng alias trả về trong Cypher. Ví dụ nếu query đổi alias thành `code` nhưng mapper vẫn đọc `employeeCode`, test sẽ phát hiện ngay lỗi mapping.

Kiểm thử:

~~~java
@Test
void recordMapperConvertsAliasesAndNumericValues() {
    createFixture();
    createProjectsFor("E-001", 2);

    Optional<PersonProjectSummary> result =
        new PersonReadQueries(client).findProjectSummary("E-001");

    assertThat(result).contains(
        new PersonProjectSummary("E-001", "Lan Nguyen", 2L)
    );
}
~~~

Kiểm tra trường hợp `OPTIONAL MATCH` không tìm thấy project:

~~~java
@Test
void recordMapperReturnsZeroForPersonWithoutProjects() {
    createFixture();

    Optional<PersonProjectSummary> result =
        new PersonReadQueries(client).findProjectSummary("E-002");

    assertThat(result).contains(
        new PersonProjectSummary("E-002", "Minh Tran", 0L)
    );
}
~~~

### Kiểm tra null và collection trong Record

Khi Cypher dùng `OPTIONAL MATCH`, một cột có thể là null. Không gọi trực tiếp `asString()` trên null nếu domain cho phép giá trị vắng mặt. Kiểm tra `Value.isNull()` trước:

~~~java
String nickname = record.get("nickname").isNull()
    ? null
    : record.get("nickname").asString();
~~~

Với collection, dùng conversion theo từng Value:

~~~java
List<String> projectNames = record.get("projectNames")
    .asList(value -> value.asString());
~~~

Nếu cột là temporal, point, node hoặc relationship, dùng accessor tương ứng của Driver hoặc mapping function do SDN cung cấp. Không chuyển mọi giá trị sang String rồi parse lại nếu Driver đã có conversion type-safe.

### Kiểm tra cardinality của kết quả

Chọn API phù hợp với số hàng mà query dự kiến trả về:

| API | Kết quả | Dùng khi |
|---|---|---|
| `one()` | Optional cho tối đa một kết quả | Query theo business key hoặc ID |
| `all()` | Collection các kết quả | Query có nhiều hàng |

Với query dùng `one()`, test cả trường hợp không có kết quả và trường hợp query vô tình trả nhiều hàng. Nếu query theo ID hoặc business key mà có duplicate, không nên âm thầm chọn hàng đầu; cần phát hiện dữ liệu sai hoặc predicate thiếu điều kiện. Nếu nghiệp vụ chỉ cần một hàng trong nhiều kết quả, hãy định nghĩa `ORDER BY` và giới hạn rõ trong Cypher trước khi dùng API lấy một kết quả.

## Kiểm thử phân trang với Page và Slice

`Page<T>` cung cấp content và metadata như total elements, total pages, page number. Để tính tổng, Spring Data có thể chạy thêm count query. `Slice<T>` chỉ cần biết có phần tiếp theo hay không nên không cần count query riêng.

Với derived query, SDN có thể áp dụng `Pageable`:

~~~java
Page<Person> findByActiveTrue(Pageable pageable);
~~~

Test:

~~~java
@Test
void derivedQuerySupportsPageable() {
    createFixture();

    Page<Person> page = people.findByActiveTrue(
        PageRequest.of(0, 2, Sort.by("employeeCode").ascending())
    );

    assertThat(page.getContent()).hasSize(2);
    assertThat(page.getTotalElements()).isEqualTo(4);
    assertThat(page.getTotalPages()).isEqualTo(2);
    assertThat(page.getNumber()).isZero();
    assertThat(page.hasNext()).isTrue();
}
~~~

### Custom @Query trả Slice

Thêm method sau vào `PersonRepository` ở phần trên. Với custom query, Cypher phải nhận `$skip` và `$limit`. Nên đặt thứ tự ổn định trong query; SDN không tự chèn sort từ Pageable cho mẫu custom query này. Dùng Pageable unsorted:

~~~java
@Query("""
    MATCH (p:Person)-[:WORKS_IN]->(d:Department)
    WHERE d.departmentCode = $departmentCode
    RETURN DISTINCT p
    ORDER BY p.employeeCode
    SKIP $skip LIMIT $limit
    """)
Slice<Person> findSliceByDepartmentCode(
    @Param("departmentCode") String departmentCode,
    Pageable pageable
);
~~~

Query Slice ở đây chỉ trả root node Person để minh họa phân trang. Nó không hydrate Department trong entity; nếu cần relationship cho read model, hãy trả graph cần thiết hoặc dùng projection/DTO. Không dùng entity được tải một phần làm aggregate để ghi lại.

Test kiểm tra content và hasNext:

~~~java
@Test
void customSliceUsesSkipLimitAndReportsNextSlice() {
    createFixture();

    Slice<Person> first = people.findSliceByDepartmentCode(
        "D-PLATFORM", PageRequest.of(0, 2)
    );

    assertThat(first.getContent())
        .extracting(Person::getEmployeeCode)
        .containsExactly("E-001", "E-002");
    assertThat(first.hasNext()).isTrue();

    Slice<Person> second = people.findSliceByDepartmentCode(
        "D-PLATFORM", PageRequest.of(1, 2)
    );

    assertThat(second.getContent())
        .extracting(Person::getEmployeeCode)
        .containsExactly("E-003");
    assertThat(second.hasNext()).isFalse();
}
~~~

Với custom query trả Slice, cung cấp thứ tự trong Cypher và truyền Pageable không sort. Nếu thiếu `$skip` hoặc `$limit`, SDN có thể cảnh báo và kết quả không theo page size mong muốn.

### Custom @Query trả Page và countQuery

Thêm method sau vào `PersonRepository` ở phần trên. `Page` cần tổng số phần tử chính xác. Với custom query, khai báo thêm `countQuery`. Count query phải dùng cùng predicate nghiệp vụ với query lấy content.

~~~java
@Query(
    value = """
        MATCH (p:Person)-[:WORKS_IN]->(d:Department)
        WHERE d.departmentCode = $departmentCode
        RETURN DISTINCT p
        ORDER BY p.employeeCode
        SKIP $skip LIMIT $limit
        """,
    countQuery = """
        MATCH (p:Person)-[:WORKS_IN]->(d:Department)
        WHERE d.departmentCode = $departmentCode
        RETURN count(DISTINCT p)
        """
)
Page<Person> findPageByDepartmentCode(
    @Param("departmentCode") String departmentCode,
    Pageable pageable
);
~~~

Query Page cũng chỉ trả Person root; áp dụng cùng lưu ý về partial mapping. Count query phải đếm root entity theo đúng predicate.

Trong query có relationship, một Person có thể khớp nhiều hàng nếu graph có nhiều relationship cùng pattern. Vì vậy, query content dùng `DISTINCT p` thì count query cũng phải đếm `count(DISTINCT p)`. Nếu content đếm Person duy nhất nhưng count query đếm relationship rows, `totalElements` sẽ lớn hơn số entity thực tế.

Test các trang:

~~~java
@Test
void customPageReturnsCorrectContentAndTotalCount() {
    createFixture();
    createDuplicateWorkRelationship("E-001", "D-PLATFORM");

    Page<Person> first = people.findPageByDepartmentCode(
        "D-PLATFORM", PageRequest.of(0, 2)
    );

    assertThat(first.getContent())
        .extracting(Person::getEmployeeCode)
        .containsExactly("E-001", "E-002");
    assertThat(first.getTotalElements()).isEqualTo(3);
    assertThat(first.getTotalPages()).isEqualTo(2);
    assertThat(first.hasNext()).isTrue();

    Page<Person> last = people.findPageByDepartmentCode(
        "D-PLATFORM", PageRequest.of(1, 2)
    );

    assertThat(last.getContent())
        .extracting(Person::getEmployeeCode)
        .containsExactly("E-003");
    assertThat(last.getTotalElements()).isEqualTo(3);
    assertThat(last.hasNext()).isFalse();
}
~~~

Với custom query Page, truyền Pageable unsorted khi query đã định nghĩa ORDER BY. Nếu cần sort động, thiết kế query theo hướng SDN hỗ trợ sorting động hoặc dùng derived query. Không giả định Pageable sort sẽ tự thay thế ORDER BY cố định trong custom Cypher.

### Những trường hợp biên của pagination

Một test pagination đầy đủ nên kiểm tra:

- Trang đầu có đủ page size khi còn đủ kết quả.
- Trang cuối có ít phần tử hơn page size.
- Trang vượt quá tổng số trang trả content rỗng.
- Kết quả không lặp giữa hai trang liên tiếp.
- Thứ tự ổn định khi nhiều Person có cùng fullName.
- Total count khớp với predicate và DISTINCT của content query.
- Page size và offset được áp dụng đúng.
- Trường hợp không có kết quả trả totalElements bằng 0.

Luôn sắp xếp theo một khóa ổn định, thường là business key duy nhất. Chỉ ORDER BY fullName có thể không đủ nếu nhiều Person cùng tên; thêm employeeCode làm tie-breaker.

Offset pagination với SKIP lớn có thể chậm vì database phải bỏ qua nhiều hàng. Với tập dữ liệu rất lớn hoặc thay đổi liên tục, cân nhắc keyset pagination bằng cursor và property được index. Bài test keyset cần xác minh cursor trang trước không làm mất hoặc lặp phần tử ở trang sau.

## Kiểm thử custom query không trả domain entity

Không phải mọi kết quả Cypher đều là node entity. Một truy vấn có thể trả số lượng, tên relationship, điểm xếp hạng hoặc tổ hợp nhiều property. Không nên ép các kết quả này vào entity chỉ vì repository đang quản lý Person.

Ví dụ truy vấn trả tên Person và loại relationship:

~~~java
public record RelationshipSummary(
    String fullName,
    String relationshipType
) {
}
~~~

Dùng Neo4jClient để ánh xạ rõ ràng:

~~~java
import java.util.List;
import org.springframework.data.neo4j.core.Neo4jClient;

public class RelationshipQueries {

    private final Neo4jClient client;

    public RelationshipQueries(Neo4jClient client) {
        this.client = client;
    }

    public List<RelationshipSummary> findRelationshipSummary(String departmentCode) {
        return client.query("""
            MATCH (p:Person)-[r:WORKS_IN]->(d:Department)
            WHERE d.departmentCode = $departmentCode
            RETURN p.fullName AS fullName,
                   type(r) AS relationshipType
            ORDER BY p.fullName, p.employeeCode, relationshipType
            """)
            .bind(departmentCode).to("departmentCode")
            .fetchAs(RelationshipSummary.class)
            .mappedBy((typeSystem, record) ->
                new RelationshipSummary(
                    record.get("fullName").asString(),
                    record.get("relationshipType").asString()
                )
            )
            .all();
    }
}
~~~

Test xác minh cả giá trị và số lượng:

~~~java
@Test
void customRecordMappingReturnsRelationshipSummary() {
    createFixture();

    List<RelationshipSummary> result =
        new RelationshipQueries(client).findRelationshipSummary("D-PLATFORM");

    assertThat(result).hasSize(3);
    assertThat(result)
        .extracting(RelationshipSummary::relationshipType)
        .containsOnly("WORKS_IN");
}
~~~

Nếu query trả aggregate, kiểm tra trường hợp không có relationship. `count(project)` trên kết quả `OPTIONAL MATCH` trả 0 khi không có project; `count(*)` trong trường hợp này vẫn đếm hàng được giữ lại. Property của node hoặc relationship không tồn tại có thể thành null. Fixture cần có cả trường hợp đó để mapper được kiểm thử đầy đủ.

## Kiểm tra query và count query không bị lệch

Một lỗi phổ biến là query lấy content và count query có predicate khác nhau. Ví dụ content lọc active Person nhưng count query quên điều kiện active. Trang đầu vẫn trông hợp lý, song totalElements và totalPages sai.

Để phát hiện:

1. Tạo fixture có cả active và inactive Person.
2. Tạo nhiều Department để query filter theo mã.
3. Tạo trường hợp có nhiều relationship để buộc dùng DISTINCT.
4. Chạy Page và đối chiếu totalElements với kết quả độc lập từ count query.
5. Chạy trang cuối để kiểm tra offset và giới hạn.
6. Đổi tham số departmentCode và xác nhận content/count cùng thay đổi.

Có thể kiểm tra count trực tiếp bằng Neo4jClient:

~~~java
long expectedCount = client.query("""
        MATCH (p:Person)-[:WORKS_IN]->(d:Department)
        WHERE d.departmentCode = $departmentCode
        RETURN count(DISTINCT p) AS total
        """)
    .bind("D-PLATFORM").to("departmentCode")
    .fetchAs(Long.class)
    .one()
    .orElseThrow();

assertThat(page.getTotalElements()).isEqualTo(expectedCount);
~~~

Count query nên trả về một giá trị số. Không trả node hoặc nhiều hàng khi framework đang chờ một tổng số.

## Các lỗi thường gặp khi kiểm thử

| Lỗi | Hậu quả | Cách xử lý |
|---|---|---|
| Chỉ kiểm tra query không ném exception | Có thể trả sai node hoặc thiếu relationship | Assert nội dung, thứ tự và graph mapping |
| Không dùng dữ liệu fixture có phân biệt | Query sai vẫn có thể qua test | Tạo nhiều tenant/department, trạng thái và tên khác nhau |
| Alias trong Cypher khác tên mapper | Record mapping lỗi hoặc lấy sai field | Dùng alias nhất quán và test từng field |
| Gọi asString/asLong trên giá trị null | Runtime mapping exception | Kiểm tra isNull trước khi chuyển đổi |
| Dùng một entity partial làm dữ liệu ghi | Có thể làm mất relationship/property không được query tải | Dùng projection/DTO cho read model hoặc tải đầy đủ aggregate |
| Dùng interface projection với accessor sai tên | Proxy không đọc đúng property | Đối chiếu accessor với property của domain type |
| Nhầm Driver Record với Java record | Thiết kế mapper và DTO không rõ ràng | Phân biệt Record của Driver với Java record DTO |
| Dùng one() cho query có thể trả nhiều hàng | Lỗi cardinality hoặc kết quả không như dự kiến | Xác định query theo ID/key hoặc dùng all() |
| Dùng first() mà không ORDER BY | Hàng được chọn không ổn định | Định nghĩa thứ tự rõ ràng |
| Custom Page thiếu countQuery | Không tính được tổng số chính xác | Khai báo countQuery |
| Custom Slice thiếu $skip hoặc $limit | Page size/offset không được áp dụng đúng | Đưa cả hai parameter vào Cypher |
| Count query không dùng DISTINCT như content | totalElements bị đếm trùng | Đếm đúng root entity bằng count(DISTINCT p) |
| Dùng Pageable sort nhưng query đã ORDER BY cố định | Sort truyền vào không có tác dụng như mong đợi | Dùng Pageable unsorted hoặc thiết kế sort động |
| Dữ liệu test dùng ID cố định | Test chạy song song có thể xung đột | Dùng UUID hoặc database/container riêng |
| Test phụ thuộc thứ tự chạy | Kết quả không ổn định trên CI | Fixture độc lập và cleanup có scope |
| Mock Neo4j khi cần kiểm tra mapping | Không kiểm tra Cypher và driver conversion thật | Dùng Testcontainers hoặc Neo4j Test Harness |

## Quy trình viết một integration test hoàn chỉnh

Khi thêm một repository query hoặc projection mới, hãy thực hiện:

1. Xác định kiểu trả về: entity, projection, DTO hay scalar.
2. Viết fixture có dữ liệu hợp lệ, thiếu dữ liệu và trường hợp trùng.
3. Chạy query qua repository hoặc Neo4jClient với database test thật.
4. Assert tham số, số hàng, property và relationship.
5. Với Record mapper, assert từng alias và conversion type.
6. Với projection, assert accessor và nullability.
7. Với Page/Slice, assert content, thứ tự, hasNext và count.
8. Chạy test với tham số không tồn tại và dữ liệu biên.
9. Xác nhận cleanup hoặc rollback không để test khác bị ảnh hưởng.
10. Chạy lại test độc lập và cùng toàn bộ test suite để phát hiện phụ thuộc fixture.

Nên đặt tên test theo hành vi quan sát được, chẳng hạn `customQueryReturnsPeopleInDepartmentOrder`, `recordMapperHandlesNullableNickname` hoặc `pageCountMatchesDistinctPeople`. Tên rõ ràng giúp phân biệt lỗi Cypher, mapping và pagination khi CI báo thất bại.

## Bài tập thực hành

Với graph Person, Department và relationship WORKS_IN, hãy thực hiện:

1. Cấu hình `@DataNeo4jTest` với Testcontainers Neo4j.
2. Tạo fixture gồm ít nhất hai Department, năm Person và một Person inactive.
3. Viết `@Query` tìm Person theo departmentCode; kiểm tra named parameter và thứ tự.
4. Trả Person cùng Department qua query và xác minh relationship mapping.
5. Viết test trường hợp không có Department và kết quả rỗng.
6. Tạo interface projection chỉ có employeeCode và fullName; kiểm tra các accessor.
7. Tạo Java record DTO chứa employeeCode, fullName và projectCount.
8. Dùng Neo4jClient `fetchAs`/`mappedBy` để map Driver Record thành DTO.
9. Thêm OPTIONAL MATCH để kiểm tra projectCount bằng 0 và xử lý property null.
10. Viết derived query trả Page và kiểm tra totalElements, totalPages, hasNext.
11. Viết custom @Query trả Slice với SKIP/LIMIT và ORDER BY ổn định.
12. Viết custom @Query trả Page với countQuery dùng count(DISTINCT p).
13. Tạo dữ liệu có nhiều relationship để xác minh count không đếm trùng Person.
14. Kiểm tra trang đầu, trang cuối, trang vượt phạm vi và trang rỗng.
15. Chạy test độc lập và song song để xác nhận fixture không xung đột.

Khi kiểm thử SDN, hãy xác minh toàn bộ hợp đồng của truy vấn: Cypher và parameter, graph được trả về, cách ánh xạ Record/projection, cùng metadata phân trang. Dùng Testcontainers để chạy trên Neo4j thật; dùng DTO và mapper tường minh cho kết quả tùy chỉnh; giữ count query đồng nhất với content query và sắp xếp ổn định để các test phản ánh đúng hành vi ứng dụng.

Tài liệu tham khảo chính thức:

- [Spring Data Neo4j - Reference Documentation](https://docs.spring.io/spring-data/neo4j/reference/)
- [Spring Data Neo4j - Testing with Spring Boot and @DataNeo4jTest](https://docs.spring.io/spring-data/neo4j/reference/testing/testing-with-spring-boot.html)
- [Spring Data Neo4j - FAQ for custom Page and Slice queries](https://docs.spring.io/spring-data/neo4j/reference/faq.html)
- [Spring Data Neo4j - Projections](https://docs.spring.io/spring-data/neo4j/reference/repositories/projections.html)
- [Testcontainers for Java - Neo4j module](https://java.testcontainers.org/modules/databases/neo4j/)

