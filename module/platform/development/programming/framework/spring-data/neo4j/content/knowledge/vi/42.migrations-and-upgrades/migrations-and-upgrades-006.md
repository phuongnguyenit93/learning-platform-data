# Chuyển từ driver thuần sang client/template/repository theo từng ca sử dụng

Một ứng dụng dùng Neo4j có thể đã có nhiều lớp gọi trực tiếp Neo4j Java Driver: mở session, chạy Cypher, đọc record, tự tạo DTO và quản lý transaction. Khi đưa Spring Data Neo4j (SDN) vào, không cần thay toàn bộ các lời gọi này trong một lần. Có thể chuyển từng ca sử dụng sang `Neo4jClient`, `Neo4jTemplate` hoặc repository, giữ Driver cho những thao tác thực sự cần API mức thấp.

Điểm quan trọng nhất là hiểu ranh giới giữa các abstraction. Java Driver vẫn là nền tảng kết nối. `Neo4jClient` bổ sung tích hợp với transaction của Spring và cung cấp cách chạy Cypher có bind parameter. `Neo4jTemplate` bổ sung mapping theo domain model. Repository cung cấp API persistence ổn định theo aggregate/domain. Chọn abstraction theo hình dạng dữ liệu và trách nhiệm của từng ca sử dụng, sau đó chuyển từng luồng và xác minh lại hành vi.

## 1. Hiểu các lớp truy cập dữ liệu trong SDN

SDN xây dựng trên Neo4j Java Driver và cung cấp các lớp có mức trừu tượng tăng dần:

~~~mermaid
flowchart TB
    A[Service / use case] --> B[Repository]
    A --> C[Neo4jTemplate]
    A --> D[Neo4jClient]
    A --> E[Neo4j Java Driver]
    B --> C
    C --> D
    D --> E
~~~

| Thành phần | Vai trò | Chọn khi |
|---|---|---|
| Neo4j Java Driver | API kết nối Bolt mức thấp; quản lý session, transaction, routing, retry và records | Cần tính năng Driver cụ thể, điều khiển session/transaction trực tiếp hoặc thao tác ngoài mô hình mapping của SDN |
| `Neo4jClient` | Chạy Cypher, bind parameter và ánh xạ kết quả theo cách ứng dụng chỉ định; tham gia Spring transaction | Query tùy chỉnh, projection/DTO, báo cáo hoặc kết quả không cần hydrate entity |
| `Neo4jTemplate` | Thao tác với domain object qua mapping context của SDN, không cần tạo repository riêng | Cần save/find/delete hoặc query domain động trong một service |
| Spring Data repository | API persistence theo entity/aggregate, CRUD, derived query và custom `@Query` | Nghiệp vụ có thao tác dữ liệu ổn định, có thể diễn đạt bằng phương thức domain rõ ràng |

Các lớp này có thể cùng tồn tại trong một ứng dụng. Repository và template sử dụng mapping của SDN; Neo4jClient không tự hiểu domain model và không tự hydrate entity. Java Driver vẫn có thể được inject từ Spring Boot, nhưng transaction mở trực tiếp bằng Driver không tự tham gia Spring-managed transaction.

## 2. Giữ nguyên Driver làm nền tảng kết nối

Khi dùng Spring Boot với Neo4j starter, Driver thường được auto-configure từ namespace `spring.neo4j`. SDN client, template và repository được cấu hình từ hạ tầng này. Hãy inject bean hiện có thay vì tạo một `GraphDatabase.driver(...)` mới trong từng service.

Ví dụ cấu hình:

~~~yaml
spring:
  neo4j:
    uri: neo4j+s://graph.example.com:7687
    authentication:
      username: app_user
      password: ${NEO4J_PASSWORD}
  data:
    neo4j:
      database: appdb
~~~

Thuộc tính chọn database của SDN là `spring.data.neo4j.database`. Namespace `spring.neo4j.*` cấu hình Driver như URI và authentication; không nhầm hai nhóm thuộc tính này khi chuyển cấu hình từ code Driver sang Spring Boot.

Trong ứng dụng Spring:

~~~java
@Service
public class LegacyGraphReader {

    private final Driver driver;

    public LegacyGraphReader(Driver driver) {
        this.driver = driver;
    }
}
~~~

Driver bean vẫn hữu ích trong giai đoạn chuyển đổi. Tuy nhiên, một Driver tự tạo trong service sẽ có connection pool riêng và không được SDN transaction manager quản lý. Nếu tạo `Neo4jClient` thủ công, hãy truyền cùng Driver instance mà transaction manager đang dùng. Starter Spring Boot thường đã cung cấp sẵn client phù hợp, nên không cần tự tạo nếu không có yêu cầu cấu hình đặc biệt.

Với ứng dụng không dùng Spring Boot, cần cấu hình hạ tầng SDN thủ công, thường thông qua `AbstractNeo4jConfig`, `@EnableNeo4jRepositories` và transaction management. Khi đó, bảo đảm Driver được dùng chung cho client, template, repository và `Neo4jTransactionManager`.

## 3. Phân loại ca sử dụng trước khi thay code

Đừng chuyển một lớp truy cập dữ liệu chỉ theo tên API. Hãy phân loại từng thao tác hiện tại theo mục tiêu và kết quả cần trả:

| Ca sử dụng hiện tại | Hướng chuyển phù hợp | Lý do |
|---|---|---|
| Tìm một Person theo ID hoặc thuộc tính đơn giản | Repository derived query | API thể hiện ý nghĩa nghiệp vụ, dễ dùng lại |
| CRUD cho aggregate Person và relationship đã mapping | Repository hoặc `Neo4jTemplate` | SDN quản lý entity mapping và graph persistence |
| Cypher tùy chỉnh trả DTO cho màn hình/báo cáo | `Neo4jClient` | Tự kiểm soát Cypher và mapping DTO |
| Query phức tạp cần trả domain entity đã mapping | Repository `@Query` hoặc `Neo4jTemplate` | Tận dụng mapping context của SDN |
| Query động cho nhiều domain type, không muốn tạo nhiều repository | `Neo4jTemplate` | Dùng chung thao tác domain-aware |
| Quản lý session, bookmark hoặc transaction Driver đặc thù | Driver | Cần quyền điều khiển thấp hơn abstraction của SDN |
| Nhiều thao tác repository/client cần atomic | Spring `@Transactional` với SDN transaction manager | Các thao tác qua SDN cùng tham gia Spring-managed transaction |

Một use case có thể dùng nhiều abstraction. Ví dụ, service dùng repository để lấy aggregate, `Neo4jClient` để đọc projection phục vụ báo cáo và vẫn gọi Driver trực tiếp cho một thao tác đặc thù. Hãy đặt các thao tác này sau service boundary rõ ràng và tránh để controller phụ thuộc trực tiếp vào Driver hoặc Cypher.

## 4. Chuyển từ Driver sang Neo4jClient khi cần giữ Cypher

Đây thường là bước chuyển ít thay đổi nhất. Cypher có thể giữ nguyên, nhưng việc bind parameter và đọc kết quả chuyển sang fluent API của client.

### Trước khi chuyển: dùng Driver trực tiếp

~~~java
import java.util.Map;
import java.util.Optional;

public Optional<PersonSummary> findSummary(String personId) {
    try (var session = driver.session()) {
        return session.executeRead(tx -> {
            var result = tx.run("""
                MATCH (p:Person {personId: $personId})
                RETURN p.personId AS personId, p.name AS name
                """, Map.of("personId", personId));

            var records = result.list();
            if (records.isEmpty()) {
                return Optional.empty();
            }

            var record = records.get(0);
            return Optional.of(new PersonSummary(
                record.get("personId").asString(),
                record.get("name").asString()
            ));
        });
    }
}
~~~

### Sau khi chuyển: dùng Neo4jClient

~~~java
import java.util.Optional;
import org.springframework.data.neo4j.core.Neo4jClient;
import org.springframework.stereotype.Repository;

@Repository
public class PersonSummaryReader {

    private final Neo4jClient client;

    public PersonSummaryReader(Neo4jClient client) {
        this.client = client;
    }

    public Optional<PersonSummary> findSummary(String personId) {
        return client.query("""
                MATCH (p:Person {personId: $personId})
                RETURN p.personId AS personId, p.name AS name
                """)
            .bind(personId).to("personId")
            .fetchAs(PersonSummary.class)
            .mappedBy((typeSystem, record) -> new PersonSummary(
                record.get("personId").asString(),
                record.get("name").asString()
            ))
            .one();
    }
}

public record PersonSummary(String personId, String name) {
}
~~~

Cypher và tên parameter vẫn được giữ. Phần mapping được đặt trong `mappedBy`, còn `one()` trả về `Optional` cho kết quả đơn. Nếu query có thể trả nhiều record, dùng `all()` hoặc `first()` theo đúng hợp đồng kết quả. `one()` phù hợp khi query phải trả đúng một record nếu có; đừng dùng nó cho query có thể trả nhiều kết quả.

Các lợi ích khi chuyển:

- Client tham gia Spring-managed transaction khi được cấu hình với Driver của SDN.
- Không cần tự mở và đóng session trong mỗi phương thức.
- Parameter được bind riêng khỏi câu Cypher, tránh nối chuỗi dữ liệu đầu vào.
- Có thể tự định nghĩa mapping sang DTO mà không cần tạo entity chỉ để nhận kết quả.
- Có API imperative và reactive tương ứng.

`Neo4jClient` là mapping-agnostic. Nó không tự hiểu `@Node`, `@Relationship` hay constructor của entity. Nếu kết quả là domain entity, hãy cân nhắc repository `@Query` hoặc template thay vì tự viết lại toàn bộ entity mapper.

## 5. Dùng Neo4jClient cho projection và Cypher tùy chỉnh

Một ca sử dụng đọc báo cáo thường không cần toàn bộ graph. Có thể trả một DTO phẳng:

~~~java
import java.util.List;

public record TeamMemberCount(String teamName, long memberCount) {
}
~~~

~~~java
public List<TeamMemberCount> countMembersByTeam() {
    return client.query("""
            MATCH (t:Team)<-[:MEMBER_OF]-(p:Person)
            RETURN t.name AS teamName, count(p) AS memberCount
            ORDER BY teamName
            """)
        .fetchAs(TeamMemberCount.class)
        .mappedBy((typeSystem, record) -> new TeamMemberCount(
            record.get("teamName").asString(),
            record.get("memberCount").asLong()
        ))
        .all()
        .stream()
        .toList();
}
~~~

Đây là trường hợp phù hợp với client: kết quả là dữ liệu báo cáo, không cần hydrate graph entity. Việc mapping DTO do code ứng dụng chịu trách nhiệm, nên hãy kiểm tra alias, kiểu dữ liệu và khả năng null của từng cột trả về.

Nếu không cần records mà chỉ cần summary/counters của lệnh ghi, dùng `run()`:

~~~java
var summary = client.query("""
        MATCH (p:Person {personId: $personId})
        SET p.status = $status
        """)
    .bind(personId).to("personId")
    .bind("ACTIVE").to("status")
    .run();

long propertiesSet = summary.counters().propertiesSet();
~~~

Ở client imperative, `run()` thực thi query ngay và trả summary. Với client reactive, `run()` trả publisher; query chỉ chạy khi publisher được subscribe. Không gọi `subscribe()` bên trong service để kích hoạt một thao tác reactive rồi bỏ publisher đi.

## 6. Chuyển sang Neo4jTemplate khi muốn giữ domain mapping

Nếu code Driver hiện tại đọc hoặc ghi graph rồi tự chuyển thành domain object, `Neo4jTemplate` có thể thay phần mapping thủ công. Template biết mapping metadata của SDN và có thể thao tác với entity được đánh dấu bằng `@Node`.

Ví dụ đọc và lưu domain object:

~~~java
import java.util.Optional;
import org.springframework.data.neo4j.core.Neo4jTemplate;
import org.springframework.stereotype.Service;

@Service
public class PersonGraphService {

    private final Neo4jTemplate template;

    public PersonGraphService(Neo4jTemplate template) {
        this.template = template;
    }

    public Optional<Person> findPerson(String personId) {
        return template.findById(personId, Person.class);
    }

    public Person save(Person person) {
        return template.save(person);
    }
}
~~~

`findById` nhận cả ID và kiểu domain vì template không bị ràng buộc vào một entity type như repository. `save` dùng metadata SDN để lưu entity cùng các relationship được khai báo trong mapping. Hãy đảm bảo domain type có `@Node`, ID được khai báo đúng và các relationship phản ánh đúng graph model.

Template phù hợp khi:

- Service thao tác với nhiều loại entity mà không muốn có một repository riêng cho từng loại.
- Query cần xây dựng động nhưng kết quả vẫn cần mapping thành domain object.
- Cần lưu hoặc đọc graph object qua mapping context mà không cần repository abstraction.
- Cần sử dụng các thao tác fluent của SDN.

Khi cần một API ổn định, giàu ý nghĩa nghiệp vụ cho một aggregate cụ thể, repository thường dễ hiểu và dễ kiểm thử hơn việc gọi template trực tiếp từ mọi service.

## 7. Chuyển CRUD thông thường sang repository

Với các thao tác lặp lại theo domain, repository giúp loại bỏ phần lớn code truy cập dữ liệu:

~~~java
import java.util.Optional;
import org.springframework.data.neo4j.repository.Neo4jRepository;

public interface PersonRepository
        extends Neo4jRepository<Person, String> {

    Optional<Person> findByEmail(String email);
}
~~~

Service chỉ cần dùng ngôn ngữ nghiệp vụ:

~~~java
@Service
public class PersonService {

    private final PersonRepository people;

    public PersonService(PersonRepository people) {
        this.people = people;
    }

    public Person requireByEmail(String email) {
        return people.findByEmail(email)
            .orElseThrow(() -> new IllegalArgumentException("Person not found"));
    }
}
~~~

Repository derived query phù hợp khi điều kiện tìm kiếm có thể diễn đạt rõ bằng tên method. Nếu Cypher phức tạp hoặc cần kiểm soát projection, có thể khai báo `@Query`:

~~~java
import java.util.Optional;
import org.springframework.data.neo4j.repository.query.Query;

public interface PersonRepository
        extends Neo4jRepository<Person, String> {

    @Query("""
        MATCH (p:Person {personId: $personId})
        RETURN p
        """)
    Optional<Person> findGraphByPersonId(String personId);
}
~~~

Với custom query trả domain object có relationship, cần thiết kế result shape theo yêu cầu mapping của SDN. Thường mỗi root node cần một record, các relationship và node liên quan được `collect()` thành collection trong record đó. Trả nhiều record lặp cùng root node có thể khiến mapping tạo entity trùng hoặc không tái dựng đúng graph.

Repository cũng có thể mở rộng bằng custom repository fragment. Đây là cách kết hợp API CRUD và một số query đặc thù dùng `Neo4jClient` hoặc `Neo4jTemplate`, trong khi service vẫn chỉ phụ thuộc vào một repository interface.

## 8. Kết hợp repository với custom fragment

Khi repository đã là điểm truy cập chính của aggregate nhưng có một truy vấn báo cáo đặc thù, không nhất thiết tạo thêm một service persistence công khai khác:

~~~java
import java.util.List;
import org.springframework.data.neo4j.repository.Neo4jRepository;

public interface PersonSearch {
    List<PersonSummary> searchByRegion(String region);
}

public interface PersonRepository
        extends Neo4jRepository<Person, String>, PersonSearch {
}
~~~

Phần triển khai fragment dùng client:

~~~java
import java.util.List;
import org.springframework.data.neo4j.core.Neo4jClient;
import org.springframework.stereotype.Repository;

@Repository
public class PersonSearchImpl implements PersonSearch {

    private final Neo4jClient client;

    public PersonSearchImpl(Neo4jClient client) {
        this.client = client;
    }

    @Override
    public List<PersonSummary> searchByRegion(String region) {
        return client.query("""
                MATCH (p:Person)
                WHERE p.region = $region
                RETURN p.personId AS personId, p.name AS name
                ORDER BY p.name
                """)
            .bind(region).to("region")
            .fetchAs(PersonSummary.class)
            .mappedBy((typeSystem, record) -> new PersonSummary(
                record.get("personId").asString(),
                record.get("name").asString()
            ))
            .all()
            .stream()
            .toList();
    }
}
~~~

Tên class triển khai theo convention của repository fragment, ở đây là `PersonSearchImpl`. Nhờ đó, người gọi dùng `PersonRepository` cho cả thao tác CRUD lẫn truy vấn đặc thù. Nếu custom logic lớn, có thể tách fragment thành nhiều interface nhỏ để tránh một repository trở thành nơi tập trung mọi query.

## 9. Giữ transaction nhất quán trong quá trình chuyển đổi

Đây là điểm cần chú ý nhất khi một service dùng đồng thời Driver thuần và SDN.

`Neo4jClient`, `Neo4jTemplate` và repository được cấu hình bởi SDN có thể tham gia Spring-managed transaction. Ví dụ:

~~~java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class TeamMembershipService {

    private final PersonRepository people;
    private final Neo4jClient client;

    public TeamMembershipService(
            PersonRepository people,
            Neo4jClient client) {
        this.people = people;
        this.client = client;
    }

    @Transactional
    public void renamePersonAndAudit(String personId, String newName) {
        Person person = people.findById(personId)
            .orElseThrow();
        person.setName(newName);
        people.save(person);

        client.query("""
                MATCH (p:Person {personId: $personId})
                CREATE (p)-[:HAS_AUDIT_EVENT]->(
                    :AuditEvent {eventType: 'PERSON_RENAMED'}
                )
                """)
            .bind(personId).to("personId")
            .run();
    }
}
~~~

Repository và client dùng cùng hạ tầng Driver/transaction manager của SDN nên hai thao tác có thể nằm trong cùng transaction Neo4j. Nếu một thao tác ném exception khiến transaction rollback, thay đổi của cả hai được hoàn tác.

Ngược lại, một lời gọi `driver.session()` trực tiếp bên trong method `@Transactional` không tự tham gia transaction của Spring. Nếu code gọi `session.executeWrite()` riêng, thao tác đó có transaction và commit/rollback riêng. Khi transaction Spring bên ngoài rollback, transaction Driver riêng đã commit không tự hoàn tác theo.

Vì vậy:

- Dùng client/template/repository cho các thao tác cần chung transaction với service SDN.
- Giữ Driver trực tiếp ở một boundary độc lập nếu cần quản lý transaction riêng.
- Không giả định hai transaction manager tự phối hợp atomic chỉ vì cùng kết nối một Neo4j DBMS.
- Nếu buộc phải dùng Driver trực tiếp trong một quy trình nhiều bước, thiết kế rõ thứ tự commit, bù trừ hoặc idempotency.

Nếu code cũ dùng Driver managed transaction như `executeRead` hoặc `executeWrite`, hãy lưu ý Driver có thể tự retry callback khi gặp lỗi transient. Chuyển sang `@Transactional` của Spring không tự động giữ nguyên chính sách retry đó. Hãy xác định retry có còn cần thiết không, đặt nó ở đúng boundary và bảo đảm thao tác có thể chạy lại an toàn.

## 10. Phân biệt imperative và reactive khi chuyển API

SDN có hai bộ API tương ứng:

| Imperative | Reactive |
|---|---|
| `Neo4jClient` | `ReactiveNeo4jClient` |
| `Neo4jTemplate` | `ReactiveNeo4jTemplate` |
| `Neo4jRepository` | `ReactiveNeo4jRepository` |
| `Optional<T>`, `List<T>` | `Mono<T>`, `Flux<T>` |
| Thực thi khi gọi terminal method | Thực thi khi publisher được subscribe |

Hai client có vocabulary tương tự nhưng không API-compatible. Với reactive client, query không chạy cho tới khi publisher được subscribe; publisher thường chỉ được subscribe một lần. Hãy compose publisher bằng `map`, `flatMap`, `then` và trả nó cho caller.

Không gọi `block()` hoặc tự `subscribe()` để làm reactive code trông giống imperative. Không nên trộn imperative và reactive database access trong cùng một ứng dụng nếu không có lý do kiến trúc rõ ràng; hãy chọn một programming model nhất quán cho service và transaction boundary.

## 11. Bảo toàn hành vi Cypher và mapping khi chuyển đổi

Chuyển từ Driver sang SDN không chỉ là thay tên class. Hãy kiểm tra những khác biệt về dữ liệu và hành vi:

### ID và domain mapping

- Giữ nguyên business key hoặc internal ID mà code cũ đang dùng.
- Xác nhận `@Id`, `@GeneratedValue` và `@Property` ánh xạ đúng property trên node.
- Kiểm tra label và relationship type có khớp graph hiện tại không.
- Nếu có relationship properties, xác nhận model dùng `@RelationshipProperties`, `@RelationshipId` và `@TargetNode` phù hợp.

### Kết quả query

- Driver trả record và code cũ tự chọn cột; client cũng có thể map thủ công sang DTO.
- Template/repository dùng mapping context của SDN, nên cần result shape đúng để dựng entity graph.
- Với custom query trả aggregate có nhiều relationship, tránh nhiều record lặp cùng root node; dùng `collect()` cho các node/relationship liên quan khi phù hợp.
- Xác nhận null, collection rỗng, kiểu số, temporal và spatial value không bị thay đổi ngoài dự kiến.

### Ghi dữ liệu

- So sánh chính xác `MERGE`, `CREATE`, `SET`, `DELETE` và điều kiện lọc cũ.
- Không giả định `template.save(entity)` tương đương với mọi câu `MERGE` viết tay. Save theo entity mapping có thể ghi các relationship thuộc graph được mô tả bởi object.
- Với lệnh cập nhật chuyên biệt hoặc tác động đến dữ liệu ngoài aggregate mapping, giữ Cypher tường minh trong `Neo4jClient` hoặc repository `@Query`.
- Xác nhận query counters, số node/relationship/property thay đổi và tính idempotent của thao tác.

## 12. Bind parameter và xử lý phần query động an toàn

Khi chuyển code, tránh nối dữ liệu đầu vào trực tiếp vào Cypher:

~~~java
// Không nên: ghép input vào câu query
String cypher = "MATCH (p:Person {name: '" + name + "'}) RETURN p";
~~~

Dùng named parameter:

~~~java
client.query("""
        MATCH (p:Person {name: $name})
        RETURN p
        """)
    .bind(name).to("name")
    .fetch()
    .all();
~~~

Parameter hóa giá trị không đồng nghĩa với parameter hóa được label, relationship type hoặc tên property. Nếu query cần chọn label/type động, dùng allowlist các giá trị hợp lệ và cơ chế literal/query builder phù hợp của SDN/Cypher DSL. Không nhận trực tiếp tên label hoặc relationship type tùy ý từ request.

## 13. Lộ trình chuyển đổi từng bước

Một lộ trình an toàn có thể chia thành các đợt nhỏ:

1. **Lập danh sách lời gọi Driver:** ghi lại Cypher, parameters, database, kết quả, transaction boundary, retry, bookmark và các tính năng Driver đặc thù.
2. **Xác định domain model:** chọn entity nào cần `@Node`, ID nào cần giữ, relationship nào cần mapping và đâu là aggregate root.
3. **Phân loại theo use case:** CRUD/derived query sang repository; query Cypher trả DTO sang client; thao tác domain mapping động sang template; tính năng thấp cấp giữ Driver.
4. **Chọn một luồng đọc đơn giản:** chuyển sang repository hoặc client, giữ nguyên query semantics và so sánh dữ liệu trả về.
5. **Chuyển luồng ghi:** kiểm tra `CREATE`/`MERGE`/`SET`, transaction, rollback và query counters trước khi bật cho traffic thật.
6. **Đưa transaction boundary về service:** gom repository/client/template trong Spring-managed transaction khi cần atomic.
7. **Chuyển các ca còn lại theo nhóm:** ưu tiên nhóm có cùng mapping và query shape; không đổi toàn bộ API cùng một đợt.
8. **Theo dõi sau mỗi lần chuyển:** latency, lỗi, số connection, transaction rollback, dữ liệu tạo/cập nhật và query plan.
9. **Loại bỏ code cũ sau khi xác nhận:** chỉ xóa session helper, mapper hoặc repository wrapper Driver khi không còn caller.

Không chạy song song hai luồng ghi lên cùng dữ liệu chỉ để so sánh kết quả; có thể tạo node/relationship trùng hoặc side effect kép. Nếu cần shadow comparison, chỉ chạy query đọc an toàn và giới hạn tải.

## 14. Kiểm thử trước và sau khi chuyển

Với mỗi ca sử dụng, giữ lại một bộ dữ liệu kiểm thử đại diện và xác nhận:

| Nhóm kiểm thử | Điều cần so sánh |
|---|---|
| Read semantics | Số kết quả, thứ tự nếu có, null/empty, relationship được hydrate |
| Write semantics | Node/relationship/property được tạo, cập nhật hoặc xóa |
| Transaction | Commit khi thành công, rollback khi lỗi ở bước giữa |
| Concurrency | Hai request đồng thời, cập nhật cùng node và retry |
| Mapping | ID, enum, temporal, spatial, collection và relationship properties |
| Performance | p50/p95, records, payload size, DB hits và allocation nếu cần |
| Operational | Logs, metrics, timeout, pool usage và database selection |

Nếu dùng repository `@Query`, kiểm tra query trả đúng record shape cho SDN. Nếu dùng `Neo4jClient`, kiểm tra mapping function với giá trị null và kiểu dữ liệu thật. Nếu giữ Driver, xác nhận session và transaction được đóng đúng cách.

## 15. Những lỗi thường gặp khi chuyển đổi

| Lỗi | Hệ quả | Cách xử lý |
|---|---|---|
| Tạo Driver mới trong mỗi service | Nhiều connection pool và không đồng bộ transaction với SDN | Inject Driver bean do Spring quản lý |
| Nghĩ Driver session trực tiếp tham gia `@Transactional` | Giao dịch Driver có thể commit độc lập | Dùng client/template/repository cho thao tác cần Spring transaction |
| Dùng Neo4jClient rồi kỳ vọng tự map `@Node` | DTO/entity không được hydrate theo mapping context | Tự `mappedBy` hoặc dùng template/repository |
| Dùng repository cho mọi query dù kết quả chỉ là báo cáo | Tạo entity và abstraction không cần thiết | Dùng client với projection |
| Dùng template cho mọi thao tác đơn giản | Service phải biết nhiều chi tiết persistence | Dùng repository cho API domain ổn định |
| Chuyển query nhưng thay đổi result shape | Mapping relationship sai hoặc lặp entity | Trả một record cho mỗi root node, collect nhánh liên quan |
| Nối chuỗi input vào Cypher | Nguy cơ Cypher injection và lỗi escaping | Bind parameter, allowlist identifier động |
| Dùng `save` như thể nó luôn tương đương `MERGE` cũ | Graph có thể thay đổi theo mapping của entity | So sánh write semantics và relationship được lưu |
| Dùng reactive client nhưng không subscribe/compose publisher | Query không được thực thi | Trả publisher cuối và để caller quản lý subscription |
| Gọi `block()` trong reactive service | Chặn thread và làm sai transaction context | Dùng reactive chain xuyên suốt |
| Shadow-write hai implementation cùng lúc | Side effect kép và dữ liệu trùng | Shadow-read hoặc so sánh trên môi trường thử nghiệm |
| Xóa Driver code trước khi kiểm thử transaction | Mất tính năng đặc thù hoặc thay đổi rollback | Chuyển từng use case, kiểm thử và theo dõi trước khi dọn code |

## 16. Tự kiểm tra

1. Neo4jClient khác Neo4jTemplate ở mức mapping domain như thế nào?
2. Vì sao repository phù hợp với CRUD và derived query theo aggregate?
3. Khi nào nên giữ Java Driver thuần trong ứng dụng Spring?
4. Vì sao phải dùng cùng Driver instance cho SDN client và transaction manager?
5. Điều gì xảy ra nếu gọi `driver.session()` trực tiếp bên trong method `@Transactional`?
6. Vì sao query trả entity graph cần chú ý một record cho mỗi root node?
7. Làm thế nào chuyển query Driver trả DTO sang `Neo4jClient` mà giữ nguyên Cypher?
8. Vì sao `template.save(entity)` không mặc nhiên tương đương với mọi câu `MERGE` viết tay?
9. Reactive client thực thi query tại thời điểm nào?
10. Vì sao shadow-write không phải cách an toàn để so sánh hai implementation?

Chuyển từ Driver thuần sang SDN nên diễn ra theo từng ca sử dụng. Dùng repository cho persistence theo domain, template cho thao tác domain mapping linh hoạt, client cho Cypher tùy chỉnh và projection, còn Driver cho những trường hợp cần API mức thấp. Giữ một Driver do Spring quản lý, đưa các thao tác cần atomic vào đúng transaction boundary và xác minh lại read/write semantics trước khi loại bỏ code cũ.

Tài liệu tham khảo:

- [Spring Data Neo4j – Building blocks](https://docs.spring.io/spring-data/neo4j/reference/introduction-and-preface/building-blocks.html)
- [Spring Data Neo4j – Neo4jClient](https://docs.spring.io/spring-data/neo4j/reference/appendix/neo4j-client.html)
- [Spring Data Neo4j – Repositories](https://docs.spring.io/spring-data/neo4j/reference/repositories.html)
- [Spring Data Neo4j – Custom queries](https://docs.spring.io/spring-data/neo4j/reference/appendix/custom-queries.html)
- [Spring Data Neo4j – Neo4jTemplate API](https://docs.spring.io/spring-data/neo4j/reference/api/java/org/springframework/data/neo4j/core/Neo4jTemplate.html)
- [Spring Boot – Working with Neo4j](https://docs.spring.io/spring-boot/reference/data/nosql.html)
