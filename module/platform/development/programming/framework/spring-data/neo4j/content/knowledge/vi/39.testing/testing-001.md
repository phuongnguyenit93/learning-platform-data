# Chọn unit test, repository test và integration test theo mục tiêu

Một ứng dụng Spring Data Neo4j (SDN) có nhiều lớp cần kiểm thử: quy tắc domain, service điều phối nghiệp vụ, ánh xạ entity thành node/relationship, truy vấn Cypher, transaction và cấu hình toàn bộ ứng dụng. Không phải mọi test đều cần khởi động Spring hoặc kết nối Neo4j. Chọn đúng cấp độ giúp test chạy nhanh, chỉ ra lỗi ở đúng lớp và vẫn kiểm chứng được những hành vi chỉ database thật mới thể hiện.

Ba cấp độ thường dùng là unit test, repository test và integration test. Unit test tập trung vào logic Java; repository test chạy các thao tác persistence trên Neo4j thật; integration test khởi tạo phần lớn hoặc toàn bộ application context để xác nhận các thành phần phối hợp đúng.

## 1. Chọn cấp độ kiểm thử theo câu hỏi cần trả lời

Trước khi viết test, hãy xác định điều cần chứng minh:

| Câu hỏi | Cấp độ phù hợp | Có cần Neo4j thật? |
| --- | --- | --- |
| Quy tắc xác nhận/hủy Order có đúng không? | Unit test | Không |
| Service có gọi collaborator đúng theo luồng nghiệp vụ không? | Unit test | Thường không |
| Node và relationship được lưu/đọc đúng không? | Repository test | Có |
| Derived query hoặc custom Cypher trả đúng graph không? | Repository test | Có |
| Custom converter, callback hoặc repository fragment có được SDN gọi đúng không? | Repository test | Có |
| Nhiều thao tác repository/client có commit hoặc rollback cùng nhau không? | Integration test | Có |
| Spring wiring, transaction manager và cấu hình ứng dụng có hoạt động cùng nhau không? | Integration test | Có |
| API, security, service và Neo4j phối hợp đúng không? | Integration/end-to-end test | Có |

Không cần dùng @SpringBootTest cho mọi trường hợp. Nếu đang kiểm tra một quy tắc domain thuần Java, khởi động cả Spring context chỉ làm test chậm và tăng số nguyên nhân có thể khiến test thất bại.

Ngược lại, mock repository không thể chứng minh SDN ánh xạ relationship đúng, Cypher chạy được hoặc Neo4j rollback dữ liệu như mong đợi. Những hành vi đó cần database thật.

## 2. Unit test: kiểm tra logic domain và service

Unit test chạy một lớp hoặc một nhóm nhỏ lớp Java mà không cần khởi động Spring ApplicationContext hay kết nối Neo4j. JUnit Jupiter dùng để tổ chức test; Mockito có thể tạo collaborator giả khi service phụ thuộc repository, clock hoặc gateway bên ngoài.

Các mục tiêu phù hợp:

- Quy tắc chuyển trạng thái của aggregate.
- Validation và invariant của domain.
- Tính toán giá trị, phân quyền nghiệp vụ hoặc quyết định workflow.
- Cách service phản ứng khi collaborator trả dữ liệu hoặc ném exception.
- Mapping thuần Java từ command sang object domain nếu không phụ thuộc SDN mapping.

Ví dụ kiểm tra quy tắc của Order:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import org.junit.jupiter.api.Test;

class OrderTest {

    @Test
    void confirmsPendingOrder() {
        Order order = Order.pending("order-100");

        order.confirm();

        assertEquals(OrderStatus.CONFIRMED, order.getStatus());
    }

    @Test
    void cannotConfirmCancelledOrder() {
        Order order = Order.cancelled("order-101");

        assertThrows(
            IllegalStateException.class,
            order::confirm
        );
    }
}
~~~

Test này kiểm tra hành vi domain trực tiếp. Nó không cần mock Neo4j vì trạng thái hợp lệ của Order phải được quyết định bởi domain model.

Nếu service phối hợp repository và notification gateway, có thể mock các collaborator:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import java.util.Optional;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

@ExtendWith(MockitoExtension.class)
class OrderApplicationServiceTest {

    @Mock
    OrderRepository orderRepository;

    @Mock
    NotificationGateway notificationGateway;

    @InjectMocks
    OrderApplicationService service;

    @Test
    void confirmsOrderAndRequestsNotification() {
        Order order = Order.pending("order-100");
        when(orderRepository.findById("order-100"))
            .thenReturn(Optional.of(order));
        when(orderRepository.save(order)).thenReturn(order);

        Order result = service.confirm("order-100");

        assertEquals(OrderStatus.CONFIRMED, result.getStatus());
        verify(orderRepository).save(order);
        verify(notificationGateway).requestConfirmation("order-100");
    }
}
~~~

Ví dụ giả định service phát yêu cầu notification theo hợp đồng của ứng dụng. Unit test xác nhận service gọi collaborator; nó không chứng minh notification đã được gửi hoặc transaction Neo4j đã commit.

### 2.1. Điều không nên kiểm tra bằng unit test

Không dùng mock để kết luận các hành vi sau đã đúng:

- SDN có ghi đúng label và property hay không.
- Relationship direction, relationship properties và graph hydration có đúng không.
- Derived query hoặc Cypher có cú pháp hợp lệ không.
- Custom converter có được mapping context sử dụng không.
- @Transactional có rollback transaction Neo4j thật không.

Các hành vi này phụ thuộc mapper, Driver, database và Spring infrastructure. Hãy dành chúng cho repository test hoặc integration test.

## 3. Repository test: kiểm thử mapping và truy vấn trên Neo4j thật

Repository test tập trung vào ranh giới persistence. Với Spring Boot, @DataNeo4jTest là test slice dành cho ứng dụng Neo4j. Slice này cấu hình các thành phần dữ liệu cần thiết như Neo4jTemplate, repository và mapping cho entity; các component ứng dụng thông thường không được tự động nạp như trong full application context.

Dùng repository test để xác minh:

- @Node, @Id và property mapping.
- @Relationship, hướng relationship và relationship properties.
- Lưu rồi đọc lại entity graph.
- Derived query, @Query, projection và custom result mapping.
- Custom repository fragment.
- Neo4jConversions, converter và entity callback.
- Constraint và hành vi database mà repository phụ thuộc.

Neo4j là graph database. H2 hoặc database quan hệ giả lập không thể thay thế việc kiểm tra Cypher, traversal và mapping graph. Một Neo4j thật trong container là lựa chọn phù hợp cho repository test có tính lặp lại.

## 4. Khởi động Neo4j bằng Testcontainers

Testcontainers tạo Neo4j trong container dành riêng cho test và tự dọn container khi test kết thúc. Dùng image tag cụ thể tương thích với phiên bản Neo4j/Driver của dự án; tránh dùng latest vì phiên bản database có thể thay đổi ngoài ý muốn.

Các dependency test thường cần:

~~~xml
<dependency>
    <groupId>org.testcontainers</groupId>
    <artifactId>neo4j</artifactId>
    <scope>test</scope>
</dependency>
<dependency>
    <groupId>org.testcontainers</groupId>
    <artifactId>junit-jupiter</artifactId>
    <scope>test</scope>
</dependency>
~~~

Nếu dự án quản lý phiên bản qua Testcontainers BOM, không khai báo version riêng cho từng dependency. Dùng phiên bản đã được dự án quản lý và tương thích với JUnit/Spring Boot hiện tại.

Ví dụ repository test:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.data.neo4j.DataNeo4jTest;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.testcontainers.containers.Neo4jContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

@DataNeo4jTest
@Testcontainers
class PersonRepositoryTest {

    @Container
    static final Neo4jContainer<?> neo4j =
        new Neo4jContainer<>("neo4j:5.26")
            .withAdminPassword("test-password");

    @DynamicPropertySource
    static void neo4jProperties(DynamicPropertyRegistry registry) {
        registry.add("spring.neo4j.uri", neo4j::getBoltUrl);
        registry.add("spring.neo4j.authentication.username",
            () -> "neo4j");
        registry.add("spring.neo4j.authentication.password",
            () -> "test-password");
        registry.add("spring.data.neo4j.database", () -> "neo4j");
    }

    @Autowired
    PersonRepository personRepository;

    @Test
    void savesAndLoadsPerson() {
        Person person = new Person("person-test-100", "An");

        personRepository.save(person);

        Person loaded = personRepository.findById("person-test-100")
            .orElseThrow();

        assertEquals("An", loaded.getName());
    }
}
~~~

Ví dụ giả định Person có constructor nhận ID và name, được đánh dấu @Node, và PersonRepository kế thừa Neo4jRepository<Person, String>. Hãy thay image tag bằng phiên bản Neo4j mà dự án hỗ trợ. Các property kết nối trong @DynamicPropertySource ghi đè cấu hình để Spring kết nối vào container đang chạy.

@DataNeo4jTest giúp giới hạn ApplicationContext ở phần dữ liệu. Nếu cần thêm converter, callback hoặc bean cấu hình riêng, import cấu hình tương ứng bằng @Import thay vì biến mọi repository test thành full application test.

## 5. Kiểm thử relationship và graph hydration

Một entity có thể được lưu đúng như một node nhưng association lại không được hydrate theo mong đợi. Vì vậy, cần có test kiểm tra cả hai đầu relationship và hướng của nó.

Ví dụ domain rút gọn:

~~~java
import java.util.Set;

import org.springframework.data.neo4j.core.schema.Id;
import org.springframework.data.neo4j.core.schema.Node;
import org.springframework.data.neo4j.core.schema.Relationship;

@Node("Person")
public class Person {

    @Id
    private String id;

    private String name;

    @Relationship(type = "MEMBER_OF", direction = Relationship.Direction.OUTGOING)
    private Set<Team> teams;

    protected Person() {
    }

    public Person(String id, String name, Set<Team> teams) {
        this.id = id;
        this.name = name;
        this.teams = teams;
    }

    public Set<Team> getTeams() {
        return teams;
    }

    public String getName() {
        return name;
    }
}
~~~

~~~java
@Node("Team")
public class Team {

    @Id
    private String id;

    private String name;

    protected Team() {
    }

    public Team(String id, String name) {
        this.id = id;
        this.name = name;
    }

    public String getId() {
        return id;
    }
}
~~~

Repository test nên lưu Person cùng Team, sau đó đọc lại Person và xác nhận association:

~~~java
@Test
void persistsAndHydratesMembershipRelationship() {
    Team team = new Team("team-test-1", "Platform");
    Person person = new Person(
        "person-test-1",
        "An",
        Set.of(team)
    );

    personRepository.save(person);

    Person loaded = personRepository.findById("person-test-1")
        .orElseThrow();

    assertTrue(
        loaded.getTeams().stream()
            .anyMatch(candidate -> "team-test-1".equals(candidate.getId()))
    );
}
~~~

Test này cần được điều chỉnh theo constructor, accessor và aggregate mapping thực tế của dự án. Nếu relationship có property riêng như joinedAt, hãy kiểm tra cả giá trị đó bằng @RelationshipProperties, không chỉ kiểm tra node ở hai đầu.

Đừng chỉ kiểm tra findById trả về một entity. Hãy xác minh graph có đúng cấu trúc mà use case yêu cầu.

## 6. Kiểm thử custom Cypher và repository method

Derived query có thể kiểm tra bằng repository test thông thường. Với @Query, hãy tạo dữ liệu có quan hệ và property đủ để phân biệt kết quả đúng/sai, sau đó gọi method repository như code ứng dụng.

Ví dụ:

~~~java
import java.util.List;

import org.springframework.data.neo4j.repository.Neo4jRepository;
import org.springframework.data.neo4j.repository.query.Query;
import org.springframework.data.repository.query.Param;

public interface PersonRepository extends Neo4jRepository<Person, String> {

    @Query("""
        MATCH (person:Person)-[:MEMBER_OF]->(team:Team)
        WHERE team.name = $teamName
        RETURN person
        """)
    List<Person> findMembersOf(
        @Param("teamName") String teamName
    );
}
~~~

Test nên tạo ít nhất hai Team và nhiều Person, trong đó chỉ một nhóm Person tham gia Team được truy vấn. Điều này phát hiện trường hợp query bỏ sót predicate, sai relationship direction hoặc trả dữ liệu quá rộng.

Với custom Cypher trả DTO, kiểm tra tên alias, kiểu dữ liệu và nullability của từng cột. Nếu query dùng aggregation, OPTIONAL MATCH, collect() hoặc UNWIND, hãy chuẩn bị fixture phản ánh cả trường hợp có và không có kết quả.

Nếu method trả entity có relationship mapping, xác nhận custom query trả đủ các node/relationship mà mapping cần để hydrate graph. Việc chỉ RETURN một node có thể không cung cấp đủ dữ liệu để dựng toàn bộ association như khi dùng repository load thông thường.

Không chỉ assert số lượng kết quả. Hãy assert ID hoặc business key cụ thể để test không vô tình pass khi trả nhầm entity.

## 7. Kiểm thử converter, callback và repository fragment

Các phần mở rộng SDN cần được kiểm tra thông qua mapping context hoặc repository proxy thực tế:

| Thành phần | Kiểm thử cần có |
| --- | --- |
| Custom converter | Lưu value object rồi đọc lại, xác nhận round-trip |
| BeforeBindCallback | Lưu entity và xác nhận giá trị đã chuẩn hóa trong graph |
| AfterConvertCallback | Đọc entity và xác nhận field dẫn xuất đã được thiết lập |
| ReactiveBeforeBindCallback | Subscribe thao tác reactive và xác nhận callback chạy trong pipeline |
| Repository fragment | Gọi method qua repository bean, không gọi implementation bằng new |
| Custom result mapping | Chạy Cypher thật và kiểm tra DTO/record nhận đúng alias, kiểu và null |

Unit test riêng converter vẫn hữu ích để kiểm tra các trường hợp null hoặc dữ liệu không hợp lệ. Nhưng một integration test qua repository mới chứng minh converter đã được đăng ký và SDN thực sự dùng nó.

Tương tự, gọi trực tiếp new PersonSearchImpl(...) chỉ kiểm tra class implementation. Nó không kiểm tra fragment discovery, naming convention hoặc repository composition.

## 8. Integration test: kiểm tra toàn bộ application context

Repository test không nạp toàn bộ service, security, controller hoặc cấu hình ứng dụng. Khi cần xác minh các thành phần này phối hợp, dùng @SpringBootTest với Neo4j thật.

Integration test phù hợp để kiểm tra:

- Service gọi nhiều repository và Neo4jClient trong một transaction.
- Transaction manager và cấu hình Driver được chọn đúng.
- Spring phát hiện custom repository fragment.
- Event listener hoặc callback được đăng ký trong ApplicationContext.
- Converter và cấu hình mapping hoạt động cùng service.
- Cấu hình database, security hoặc web layer phối hợp với persistence.

Ví dụ cấu hình container có thể tái sử dụng trong lớp integration test:

~~~java
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.testcontainers.containers.Neo4jContainer;

@SpringBootTest
abstract class Neo4jIntegrationTestBase {

    static final Neo4jContainer<?> neo4j =
        new Neo4jContainer<>("neo4j:5.26")
            .withAdminPassword("test-password");

    static {
        neo4j.start();
    }

    @DynamicPropertySource
    static void neo4jProperties(DynamicPropertyRegistry registry) {
        registry.add("spring.neo4j.uri", neo4j::getBoltUrl);
        registry.add("spring.neo4j.authentication.username",
            () -> "neo4j");
        registry.add("spring.neo4j.authentication.password",
            () -> "test-password");
        registry.add("spring.data.neo4j.database", () -> "neo4j");
    }

    // Autowire service và repository cần kiểm tra.
}
~~~

Đây là lớp test base trừu tượng dùng singleton container: container được khởi động một lần và Testcontainers dọn dẹp khi JVM kết thúc. Cách này tránh tình huống Spring TestContext cache tái sử dụng ApplicationContext sau khi container gắn với một test class đã dừng. Nếu chọn vòng đời container theo từng class, cần bảo đảm context không được tái sử dụng sau khi container đã đóng.

### 8.1. Kiểm thử transaction rollback

Giả sử một service tạo Order, ghi Audit và ném unchecked exception sau thao tác ghi. Integration test gọi service bean từ Spring context rồi kiểm tra graph không còn các thay đổi thuộc transaction đó:

~~~java
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertThrows;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;

class OrderWorkflowIntegrationTest extends Neo4jIntegrationTestBase {

    @Autowired
    OrderWorkflowService orderWorkflowService;

    @Autowired
    OrderRepository orderRepository;

    @Test
    void rollsBackAllGraphWritesWhenWorkflowFails() {
        assertThrows(
            IllegalStateException.class,
            () -> orderWorkflowService.createThenFail("order-test-rollback")
        );

        assertFalse(
            orderRepository.existsById("order-test-rollback")
        );
    }
}
~~~

Neo4jIntegrationTestBase đại diện cho lớp test base cung cấp cấu hình @SpringBootTest, container và dynamic properties ở trên. createThenFail phải là public method có @Transactional, ghi Order rồi ném IllegalStateException; test không được tự mở transaction bao ngoài nếu muốn xác minh commit/rollback ở ranh giới service.

Nếu service bắt exception rồi trả về bình thường, kết quả rollback sẽ phụ thuộc trạng thái rollback-only và rollback rule. Hãy tạo test riêng cho đúng nhánh xử lý exception mà ứng dụng sử dụng.

Rollback Neo4j không hoàn tác email, HTTP call hoặc message đã gửi ra ngoài. Nếu use case có side effect, test phải xác minh outbox hoặc cơ chế bù trừ tương ứng.

## 9. Kiểm thử reactive repository và transaction

Với SDN reactive, dùng ReactiveNeo4jRepository, ReactiveNeo4jClient và Reactor Test. StepVerifier subscribe publisher và kiểm tra signal; không gọi block() chỉ để tiện viết assertion trong test reactive.

Ví dụ:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import reactor.test.StepVerifier;

class ReactivePersonRepositoryTest extends ReactiveNeo4jIntegrationTestBase {

    @Autowired
    ReactivePersonRepository personRepository;

    @Test
    void savesAndLoadsPerson() {
        Person person = new Person("person-reactive-1", "An");

        StepVerifier.create(
            personRepository.save(person)
                .then(personRepository.findById("person-reactive-1"))
        )
        .assertNext(loaded ->
            assertEquals("An", loaded.getName())
        )
        .verifyComplete();
    }
}
~~~

Test base cần cấu hình reactive SDN và Neo4j container tương ứng. Ví dụ minh họa một chuỗi save rồi find; test transaction nhiều thao tác cần xác minh mọi publisher được nối trong cùng pipeline và dùng reactive transaction manager.

Các nguyên tắc quan trọng:

- Trả publisher từ service và subscribe bằng StepVerifier.
- Không gọi subscribe() bên trong service hoặc callback.
- Không tạo một subscription độc lập cho thao tác cần tham gia transaction.
- Kiểm tra cả onNext, onComplete và onError.
- Nếu kiểm tra rollback, truy vấn graph sau khi publisher transactional kết thúc để xác minh dữ liệu thực tế.

## 10. Chuẩn bị fixture và cô lập dữ liệu test

Test có thể chạy độc lập trên máy phát triển nhưng thất bại khi chạy song song hoặc khi một test để lại dữ liệu cho test sau. Cần thiết kế fixture có định danh riêng và cleanup rõ ràng.

Một số nguyên tắc:

1. Dùng ID test riêng, ví dụ person-test-<case> thay vì ID nghiệp vụ phổ biến.
2. Tạo đúng graph tối thiểu mà test cần.
3. Xóa dữ liệu theo ID hoặc namespace của test.
4. Nếu dùng DETACH DELETE, giới hạn pattern theo ID test; không xóa toàn bộ database dùng chung.
5. Không phụ thuộc thứ tự chạy test.
6. Dùng database/container riêng cho test suite hoặc test worker khi chạy song song.
7. Không tái sử dụng dữ liệu từ môi trường phát triển hoặc production.

Ví dụ cleanup theo ID:

~~~java
@AfterEach
void cleanup() {
    neo4jClient.query("""
            MATCH (node)
            WHERE node.id IN $ids
            DETACH DELETE node
            """)
        .bind(List.of("person-test-100", "team-test-100")).to("ids")
        .run();
}
~~~

Ví dụ giả định entity dùng property id được lưu trong graph, test dùng đúng các ID này và đã import java.util.List. Danh sách ID phải chỉ chứa node do fixture hiện tại tạo ra; không dùng cleanup này với ID dữ liệu dùng chung.

Một container riêng cho class hoặc suite thường đơn giản hơn việc chia sẻ một Neo4j database giữa nhiều test process. Nếu dùng container tĩnh được tái sử dụng qua nhiều test class, cần kiểm soát database và cleanup kỹ hơn.

## 11. Không thay Neo4j bằng mock hoặc database quan hệ

Mock repository phù hợp khi unit test service cần kiểm tra điều phối. Nó không thể mô phỏng đầy đủ:

- Cypher parser và planner.
- Node/relationship identity và traversal.
- Neo4j constraint, index và transaction semantics.
- SDN mapping context và entity hydration.
- Driver behavior và database selection.

H2 hoặc PostgreSQL cũng không thể xác nhận Cypher chạy đúng. Không dùng database quan hệ thay thế Neo4j trong repository test chỉ để test nhanh hơn.

Có thể dùng mock cho các collaborator bên ngoài graph như email gateway, payment client hoặc clock. Giữ Neo4j thật cho test kiểm tra persistence. Cách phân chia này giúp test nhanh ở nơi phù hợp và đáng tin cậy ở ranh giới database.

## 12. Test dữ liệu, transaction và schema cần tách mục tiêu

Không nên gom tất cả vào một test lớn. Tách test theo điều cần chứng minh:

| Nhóm test | Ví dụ assertion |
| --- | --- |
| Entity mapping | Property, ID, label được lưu và đọc đúng |
| Relationship mapping | Type, direction, target node và relationship properties đúng |
| Query behavior | Điều kiện, sort, pagination và projection trả đúng kết quả |
| Constraint | Duplicate key bị database từ chối |
| Converter/callback | Giá trị được chuyển đổi hoặc chuẩn hóa đúng |
| Transaction | Nhiều thao tác cùng commit hoặc rollback |
| Database selection | Request tenant chọn đúng database |
| Performance | Query plan và latency đáp ứng mục tiêu trên dữ liệu đại diện |

Performance test không nên chỉ dựa vào một repository integration test với vài node. Hãy dùng dataset có quy mô, phân bố degree và cardinality gần production, đo bằng PROFILE hoặc benchmark riêng.

Schema migration cũng cần test theo quy trình migration của dự án: tạo database sạch, chạy migration, xác nhận constraint/index và kiểm tra dữ liệu tương thích. Không giả định test slice tự kiểm tra toàn bộ migration pipeline.

## 13. Tổ chức test source set và đặt tên

Một cấu trúc đơn giản:

~~~text
src/
  main/
    java/
      .../domain/
      .../repository/
      .../service/
  test/
    java/
      .../domain/
        OrderTest.java
      .../service/
        OrderApplicationServiceTest.java
      .../repository/
        PersonRepositoryTest.java
      .../integration/
        OrderWorkflowIntegrationTest.java
        ReactiveOrderIntegrationTest.java
~~~

Tên test nên thể hiện hành vi và điều kiện, chẳng hạn:

- confirmsPendingOrder
- rejectsConfirmationForCancelledOrder
- hydratesOutgoingMembershipRelationship
- findsPeopleByTenantAndEmail
- rollsBackOrderAndAuditWhenWorkflowFails

Tránh tên chung chung như testSave, test1 hoặc works. Khi test thất bại, tên test nên giúp người đọc hiểu ngay hợp đồng nào bị vi phạm.

## 14. Quy trình chọn và viết test

1. Viết rõ hành vi cần chứng minh bằng một câu.
2. Nếu hành vi chỉ phụ thuộc logic Java, chọn unit test.
3. Nếu cần xác minh mapping, Cypher hoặc repository, chọn @DataNeo4jTest với Neo4j thật.
4. Nếu cần xác minh nhiều bean, transaction hoặc cấu hình ứng dụng, chọn @SpringBootTest.
5. Dùng Testcontainers với image Neo4j được pin phiên bản tương thích.
6. Tạo fixture tối thiểu, có ID riêng và cleanup theo phạm vi test.
7. Assert cả nội dung và cấu trúc graph cần thiết, không chỉ số lượng kết quả.
8. Kiểm tra lỗi và rollback tại ranh giới transaction thật.
9. Giữ side effect bên ngoài database ở mock hoặc kiểm tra qua outbox.
10. Chạy unit test thường xuyên; chạy repository/integration test trong pipeline CI phù hợp với môi trường container.
11. Khi test thất bại, phân biệt lỗi domain, mapping, Cypher, database, cấu hình và môi trường Docker.
12. Bổ sung regression test cho lỗi đã từng xảy ra.

## 15. Bài tập tự kiểm tra

1. Khi nào một unit test nên dùng mock repository?
2. Vì sao mock repository không chứng minh được @Relationship mapping đúng?
3. @DataNeo4jTest khác @SpringBootTest ở phạm vi ApplicationContext như thế nào?
4. Vì sao repository test cần Neo4j thật thay vì H2?
5. Testcontainers giúp kiểm soát phiên bản và vòng đời database test ra sao?
6. Khi nào cần kiểm tra @Query bằng integration test?
7. Làm thế nào để chứng minh hai thao tác repository rollback cùng nhau?
8. Vì sao phải gọi service qua Spring bean khi kiểm tra @Transactional?
9. StepVerifier có vai trò gì khi kiểm thử reactive repository?
10. Làm thế nào để cleanup fixture mà không xóa dữ liệu của test khác?
11. Vì sao custom converter nên được kiểm tra cả độc lập và qua repository?
12. Performance test khác repository correctness test ở mục tiêu nào?

Khi hoàn thành bài học, bạn cần chọn được cấp độ kiểm thử theo hành vi cần chứng minh: unit test cho logic domain/service, repository test cho mapping và Cypher trên Neo4j thật, integration test cho transaction và wiring toàn ứng dụng. Cách phân tầng này giúp test suite của Spring Data Neo4j vừa nhanh, vừa kiểm tra đúng những ranh giới mà mock không thể đại diện.

## Tài liệu tham khảo

- [Spring Boot – DataNeo4jTest](https://docs.spring.io/spring-boot/api/java/org/springframework/boot/test/autoconfigure/data/neo4j/DataNeo4jTest.html)
- [Spring Boot – Testing Spring Boot Applications](https://docs.spring.io/spring-boot/reference/testing/index.html)
- [Spring Data Neo4j – Testing](https://docs.spring.io/spring-data/neo4j/reference/testing.html)
- [Testcontainers – Neo4j Module](https://java.testcontainers.org/modules/databases/neo4j/)
- [Project Reactor – Testing with StepVerifier](https://projectreactor.io/docs/core/release/reference/testing.html)

