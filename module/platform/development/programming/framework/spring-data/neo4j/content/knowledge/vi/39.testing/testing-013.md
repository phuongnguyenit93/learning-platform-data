# Kiểm thử reactive cùng phạm vi commit và cleanup tường minh

Trong Spring Data Neo4j (SDN) reactive, một thao tác ghi chỉ thực sự chạy khi publisher được subscribe. Nếu service trả về một Mono hoặc Flux có transaction, Spring quản lý transaction theo vòng đời subscription và lưu transaction resource trong Reactor Context. Vì vậy, test phải chờ publisher hoàn tất rồi mới kết luận dữ liệu đã commit hoặc rollback.

Một test reactive đáng tin cậy cần chứng minh ba điều: mọi thao tác thuộc nghiệp vụ đã nằm trong cùng publisher/transaction; trạng thái graph được kiểm tra sau khi transaction kết thúc; và fixture được dọn bằng publisher cleanup riêng, có chờ hoàn tất. Gọi subscribe() rời rạc hoặc xóa dữ liệu bằng một lệnh cleanup không được chờ có thể khiến test pass giả, rò rỉ dữ liệu giữa test hoặc che giấu lỗi transaction.

## 1. Vòng đời publisher quyết định thời điểm test chạy

Mono và Flux là publisher lazy trong các thao tác reactive thông thường. Khi gọi một method trả Mono, code thường mới xây dựng pipeline; truy vấn database được thực thi khi có subscription.

Ví dụ:

~~~java
Mono<Person> result = personRepository.save(person);
~~~

Dòng lệnh trên chưa đủ để kết luận Person đã được ghi. Test phải subscribe và chờ publisher kết thúc:

~~~java
StepVerifier.create(result)
    .assertNext(person -> assertEquals("person-1", person.getId()))
    .verifyComplete();
~~~

verifyComplete() subscribe publisher, kiểm tra chuỗi signal và chờ publisher hoàn tất. Khi method transactional trả về reactive type, transaction manager có thể commit sau khi publisher complete bình thường hoặc rollback khi publisher kết thúc bằng error theo rollback rules.

Đừng assert trạng thái graph ngay sau khi chỉ tạo publisher. Nếu test không subscribe, thao tác ghi có thể chưa chạy. Nếu test chỉ gọi expectNext mà không gọi verify hoặc verifyComplete, subscription cũng chưa được thực thi.

## 2. Reactive transaction gắn với Reactor Context

Transaction imperative thường gắn với thread hiện tại. Reactive transaction dùng Reactor Context để truyền transaction resource xuyên suốt pipeline. Các operator Reactor chuẩn giữ context theo subscription; việc đổi scheduler không tự làm mất transaction.

Trong SDN reactive, transaction thường được quản lý bằng ReactiveNeo4jTransactionManager. Có thể đặt ranh giới bằng @Transactional trên service trả Mono/Flux hoặc bằng TransactionalOperator.

Ví dụ service dùng annotation:

~~~java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import reactor.core.publisher.Mono;

@Service
public class PersonService {

    private final ReactivePersonRepository personRepository;

    public PersonService(ReactivePersonRepository personRepository) {
        this.personRepository = personRepository;
    }

    @Transactional
    public Mono<Person> create(Person person) {
        return personRepository.save(person);
    }
}
~~~

Phương thức phải được gọi qua Spring proxy để transaction interceptor áp dụng. Test nên inject PersonService từ ApplicationContext, sau đó subscribe publisher được trả về.

Nếu dùng TransactionalOperator, bọc toàn bộ công việc cần nguyên tử:

~~~java
import org.springframework.transaction.reactive.TransactionalOperator;
import reactor.core.publisher.Mono;

public Mono<Person> create(Person person) {
    Mono<Person> work = personRepository.save(person)
        .flatMap(saved -> writeAudit(saved).thenReturn(saved));

    return work.as(transactionalOperator::transactional);
}
~~~

TransactionalOperator tạo transaction cho publisher work. Không cần thêm một @Transactional bao quanh cùng pipeline nếu không có chủ đích propagation cụ thể.

## 3. Không dùng transaction imperative của test để giả lập reactive transaction

Spring TestContext có hỗ trợ transaction cho test method. Tuy nhiên, một JUnit method đồng bộ được đánh dấu @Transactional thường dùng transaction manager imperative và transaction gắn với thread. Không giả định annotation đó tự tạo reactive transaction trong Reactor Context; hỗ trợ test-managed reactive transaction còn phụ thuộc phiên bản Spring và cách test method khai báo publisher.

Một test như sau không phải cách đáng tin cậy để kiểm tra reactive transaction:

~~~java
@Transactional
@Test
void savesReactiveEntity() {
    personRepository.save(person).subscribe();
}
~~~

Ở đây test tự subscribe publisher, trong khi transaction của test method không nhất thiết là reactive transaction mà publisher cần. Test có thể kết thúc trước khi publisher hoàn thành và trạng thái commit/rollback không còn đúng với điều cần kiểm tra.

Thay vào đó:

- Đặt @Transactional trên service reactive được gọi qua Spring proxy; hoặc
- Dùng TransactionalOperator để bọc publisher trong service/test harness.
- Để StepVerifier subscribe và chờ publisher kết thúc.
- Đọc lại graph sau khi transaction kết thúc bằng một publisher mới.

Test method có thể là phương thức JUnit đồng bộ; StepVerifier.verifyComplete() là điểm chờ có chủ đích trong test. Điều cần tránh là tự gọi subscribe() hoặc block() trong code ứng dụng đang được kiểm tra.

## 4. Chọn ranh giới test: repository, service hay transaction

Không phải mọi test reactive đều cần cùng phạm vi:

| Mục tiêu | Cách kiểm thử | Phạm vi |
| --- | --- | --- |
| Repository reactive lưu/đọc đúng entity | StepVerifier + Neo4j thật | Một hoặc vài thao tác repository |
| Cypher qua ReactiveNeo4jClient trả đúng dữ liệu | StepVerifier + Neo4j thật | Một query |
| Repository và client cùng tham gia transaction | Gọi service reactive qua Spring proxy | Một use case nhiều thao tác |
| Rollback khi một thao tác giữa pipeline lỗi | Gây lỗi sau một lần ghi rồi đọc lại graph | Một transaction hoàn chỉnh |
| Cleanup fixture không chạy đua với test | StepVerifier chờ cleanup publisher | Vòng đời fixture |
| Retry hoặc cancellation | Kiểm tra signal, số lần subscription và trạng thái graph | Hành vi reactive cụ thể |

Repository test chứng minh mapping và query. Integration test với service bean chứng minh transaction boundary và wiring. Nếu chỉ mock repository, không thể chứng minh hai lần ghi thật sự thuộc cùng Neo4j transaction.

## 5. Thiết lập Neo4j thật cho reactive test

Dùng Neo4j Testcontainers để test chạy trên database cùng loại với ứng dụng. Pin image tag tương thích với phiên bản Neo4j và Driver mà dự án sử dụng; không dùng latest trong test ổn định.

Dependency thường cần:

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
<dependency>
    <groupId>io.projectreactor</groupId>
    <artifactId>reactor-test</artifactId>
    <scope>test</scope>
</dependency>
~~~

Nếu dự án quản lý dependency bằng BOM, dùng phiên bản đã được BOM quản lý. Test reactive phải chạy với reactive SDN stack và reactive Driver configuration của ứng dụng.

Ví dụ cấu hình integration test dùng singleton container:

~~~java
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.testcontainers.containers.Neo4jContainer;

@SpringBootTest
abstract class ReactiveNeo4jTestBase {

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
}
~~~

Đây là test base cho ví dụ integration. Container có vòng đời dài hơn các ApplicationContext được Spring TestContext cache tái sử dụng, tránh trường hợp context vẫn trỏ tới container đã dừng. Trong dự án thực tế có thể dùng cơ chế quản lý container chung của test suite; điều quan trọng là container không được dừng trước khi context còn sử dụng nó.

Nếu chỉ kiểm tra repository reactive, dùng test slice Neo4j phù hợp với phiên bản Spring Boot và reactive dependencies của dự án. Nếu slice không nạp reactive configuration hoặc custom bean cần thiết, dùng @SpringBootTest hoặc import cấu hình rõ ràng.

## 6. Gắn fixture ID riêng cho từng test

Test chạy song song hoặc chạy lặp nhiều lần không nên dùng chung ID cố định. Tạo một testRunId duy nhất cho mỗi test method và gắn nó lên mọi node, relationship do fixture tạo.

Ví dụ:

~~~java
import java.util.UUID;

class ReactiveGraphIntegrationTest extends ReactiveNeo4jTestBase {

    // JUnit mặc định tạo test instance mới cho mỗi test method.
    private final String testRunId = UUID.randomUUID().toString();

    // Repository, ReactiveNeo4jClient và service được inject.
}
~~~

Trong fixture, dùng ID chứa testRunId hoặc property testRunId:

~~~cypher
CREATE (person:Person {
    id: $personId,
    testRunId: $testRunId,
    name: $name
})
~~~

Nếu tạo relationship, gắn cùng testRunId lên relationship:

~~~cypher
MATCH (person:Person {testRunId: $testRunId, id: $personId})
MATCH (team:Team {testRunId: $testRunId, id: $teamId})
CREATE (person)-[:MEMBER_OF {testRunId: $testRunId}]->(team)
~~~

Marker giúp truy vấn kiểm tra và cleanup chỉ nhắm vào dữ liệu của test hiện tại. Không dùng một marker chung cho toàn bộ test suite nếu nhiều test có thể chạy đồng thời.

Với test cần mô phỏng node global hoặc dữ liệu dùng chung, tạo fixture global riêng và không xóa nó trong cleanup của từng test. Các node thuộc fixture test nên được cô lập để cleanup không ảnh hưởng graph của test khác.

## 7. Cleanup phải là một reactive publisher được chờ hoàn tất

Không gọi subscribe() trong @BeforeEach hoặc @AfterEach rồi để test tiếp tục. Cleanup phải trả publisher và test phải chờ publisher complete.

Ví dụ dùng ReactiveNeo4jClient:

~~~java
import org.springframework.data.neo4j.core.ReactiveNeo4jClient;
import reactor.core.publisher.Mono;

private Mono<Void> cleanupFixture(String testRunId) {
    Mono<?> deleteRelationships = neo4jClient.query("""
            MATCH ()-[relationship]-()
            WHERE relationship.testRunId = $testRunId
            DELETE relationship
            """)
        .bind(testRunId).to("testRunId")
        .run();

    Mono<?> deleteNodes = neo4jClient.query("""
            MATCH (node)
            WHERE node.testRunId = $testRunId
            DETACH DELETE node
            """)
        .bind(testRunId).to("testRunId")
        .run();

    return deleteRelationships
        .then(deleteNodes)
        .then();
}
~~~

Đầu tiên xóa relationship có marker, sau đó xóa node fixture. DETACH DELETE là lớp bảo vệ cuối để node test không còn relationship treo. Cách này giả định fixture được cô lập và không nối tới node dùng chung. Nếu test tạo relationship tới dữ liệu global, hãy xóa đúng relationship do test sở hữu và kiểm tra kỹ phạm vi node trước khi dùng DETACH DELETE.

Nếu database schema cho phép nhiều loại relationship khác nhau, truy vấn MATCH ()-[relationship]-() không giới hạn type sẽ tìm mọi relationship rồi lọc theo marker. Với graph lớn, có thể dùng các relationship type đã biết để giới hạn phạm vi. Dù chọn cách nào, marker phải được gắn nhất quán khi tạo fixture.

Có thể dùng cleanup trước và sau mỗi test:

~~~java
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import reactor.test.StepVerifier;

@BeforeEach
void cleanBefore() {
    StepVerifier.create(cleanupFixture(testRunId))
        .verifyComplete();
}

@AfterEach
void cleanAfter() {
    StepVerifier.create(cleanupFixture(testRunId))
        .verifyComplete();
}
~~~

verifyComplete() chờ publisher cleanup kết thúc. Với test có thể bị treo do kết nối hoặc publisher không complete, đặt verify timeout phù hợp, ví dụ StepVerifier.create(cleanupFixture(testRunId)).verify(Duration.ofSeconds(10)). Nếu cleanup phát lỗi, test phải thất bại để lộ vấn đề dọn fixture. Không nuốt lỗi cleanup bằng onErrorResume(error -> Mono.empty()) vì dữ liệu sót lại có thể làm sai kết quả các test tiếp theo.

Cleanup trước test giúp test có thể chạy lại sau lần chạy bị gián đoạn. Cleanup sau test giải phóng dữ liệu ngay cả khi assertion của test thất bại. Cả hai dùng cùng testRunId riêng nên không đụng fixture của test khác.

## 8. Kiểm tra một thao tác reactive đã commit

Sau khi service publisher complete, kiểm tra dữ liệu bằng một publisher đọc riêng. Vì publisher ghi đã kết thúc, transaction của use case đã hoàn tất trước khi truy vấn xác minh bắt đầu.

Ví dụ service:

~~~java
@Transactional
public Mono<Person> createPerson(Person person) {
    return personRepository.save(person);
}
~~~

Test:

~~~java
@Test
void commitsPersonAfterPublisherCompletes() {
    Person person = new Person(
        testRunId,
        testRunId,
        "An"
    );

    StepVerifier.create(personService.createPerson(person))
        .assertNext(saved ->
            assertEquals(testRunId, saved.getTestRunId())
        )
        .verifyComplete();

    StepVerifier.create(personRepository.findById(testRunId))
        .assertNext(loaded ->
            assertEquals("An", loaded.getName())
        )
        .verifyComplete();
}
~~~

Ví dụ giả định Person có ID và testRunId phù hợp với constructor, getter và mapping của ứng dụng. Điểm quan trọng là test xác minh sau khi verifyComplete() của publisher ghi đã trả về. Không bọc toàn bộ test method trong một transaction ngoài khiến thao tác đọc có thể tham gia cùng transaction test.

Nếu test dùng TransactionalOperator thay vì @Transactional, quy tắc tương tự: verify publisher đã được bọc operator và kết thúc trước khi đọc dữ liệu.

## 9. Kiểm tra rollback sau lỗi ở giữa pipeline

Một transaction nhiều thao tác cần test cả trường hợp thao tác đầu thành công nhưng thao tác sau thất bại. Tạo lỗi sau khi cả repository và client đã phát lệnh ghi, rồi xác minh không còn dữ liệu nào sau transaction.

Ví dụ service:

~~~java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import reactor.core.publisher.Mono;

@Service
public class GraphWorkflowService {

    private final ReactivePersonRepository personRepository;
    private final ReactiveNeo4jClient neo4jClient;

    public GraphWorkflowService(
            ReactivePersonRepository personRepository,
            ReactiveNeo4jClient neo4jClient) {
        this.personRepository = personRepository;
        this.neo4jClient = neo4jClient;
    }

    @Transactional
    public Mono<Void> createThenFail(Person person, String testRunId) {
        return personRepository.save(person)
            .flatMap(saved ->
                neo4jClient.query("""
                        CREATE (:AuditEvent {
                            testRunId: $testRunId,
                            type: "PERSON_CREATED"
                        })
                        """)
                    .bind(testRunId).to("testRunId")
                    .run()
                    .then(Mono.error(
                        new IllegalStateException("Simulated failure")
                    ))
            )
            .then();
    }
}
~~~

Test:

~~~java
@Test
void rollsBackRepositoryAndClientWritesTogether() {
    Person person = new Person(
        testRunId,
        testRunId,
        "An"
    );

    StepVerifier.create(
        graphWorkflowService.createThenFail(person, testRunId)
    )
    .expectError(IllegalStateException.class)
    .verify();

    StepVerifier.create(countFixtureNodes(testRunId))
        .expectNext(0L)
        .verifyComplete();
}
~~~

countFixtureNodes là helper dùng ReactiveNeo4jClient để đếm node có testRunId. Truy vấn xác minh phải chạy sau khi verify() đã chờ error signal và transaction đã rollback.

Điều kiện để test này chứng minh được atomicity:

- Service được inject từ Spring ApplicationContext và gọi qua proxy.
- Method trả về Mono để Spring dùng reactive transaction management.
- Repository và ReactiveNeo4jClient dùng cùng reactive Driver/database selection và transaction manager.
- Lệnh tạo AuditEvent được nối vào publisher bằng flatMap/then.
- Error signal đi ra khỏi publisher transactional, không bị chuyển thành complete trước ranh giới transaction.

Nếu đặt onErrorResume để biến lỗi thành Mono.empty() bên trong transaction, transaction có thể thấy complete bình thường và commit. Khi cần trả response dự phòng, hãy xử lý error ở phía ngoài transaction boundary.

## 10. Kiểm tra commit của nhiều thao tác repository/client

Rollback test chứng minh lỗi ở giữa pipeline có thể hoàn tác các ghi trước đó. Cũng nên có test thành công để xác nhận mọi thay đổi cùng tồn tại sau commit.

Ví dụ một service lưu Person rồi tạo AuditEvent:

~~~java
@Transactional
public Mono<Person> createWithAudit(Person person, String testRunId) {
    return personRepository.save(person)
        .flatMap(saved ->
            neo4jClient.query("""
                    CREATE (:AuditEvent {
                        testRunId: $testRunId,
                        type: "PERSON_CREATED"
                    })
                    """)
                .bind(testRunId).to("testRunId")
                .run()
                .thenReturn(saved)
        );
}
~~~

Sau khi publisher complete, test truy vấn độc lập để xác nhận có đúng một Person và một AuditEvent:

~~~java
private Mono<Long> countFixtureNodes(String testRunId) {
    return neo4jClient.query("""
            MATCH (node)
            WHERE node.testRunId = $testRunId
            RETURN count(node) AS total
            """)
        .bind(testRunId).to("testRunId")
        .fetchAs(Long.class)
        .mappedBy((typeSystem, record) ->
            record.get("total").asLong()
        )
        .one();
}
~~~

Test thành công có thể xác minh cả hai ghi đã commit:

~~~java
@Test
void commitsPersonAndAuditEventTogether() {
    Person person = new Person(testRunId, testRunId, "An");

    StepVerifier.create(
        graphWorkflowService.createWithAudit(person, testRunId)
    )
    .assertNext(saved -> assertEquals(testRunId, saved.getTestRunId()))
    .verifyComplete();

    StepVerifier.create(countFixtureNodes(testRunId))
        .expectNext(2L)
        .verifyComplete();
}
~~~

Nếu test muốn phân biệt từng loại node, viết query count theo label hoặc trả hai count riêng. Không chỉ assert tổng số node nếu một loại node bị thiếu nhưng loại khác lại bị tạo trùng.

## 11. Cancellation, timeout và retry cũng là kết thúc subscription

Reactive publisher có thể kết thúc bằng complete, error hoặc cancellation. Cancellation không phải commit thành công. Khi subscriber hủy trước khi pipeline hoàn tất, transaction manager có thể rollback transaction đang mở; hành vi cụ thể cần được kiểm thử với transaction manager và phiên bản framework đang dùng.

Không dùng StepVerifier.thenCancel() rồi giả định dữ liệu đã commit. Nếu use case có timeout hoặc client disconnect, hãy xác định nghiệp vụ chấp nhận rollback, retry hay trạng thái không xác định như thế nào.

Retry cũng có thể tạo subscription lại hoặc thực thi lại transaction callback. Khi test retry:

- Dùng command có idempotency key ổn định.
- Kiểm tra số lần gọi bằng counter hoặc spy ở ranh giới thích hợp.
- Xác minh không tạo node/event trùng.
- Dùng retry budget nhỏ và thời gian backoff có kiểm soát.
- Không dùng sleep trong test; với backoff theo thời gian, cân nhắc Reactor virtual time nếu operator hỗ trợ.

Test cancellation và retry nên tách khỏi test commit/rollback cơ bản để mỗi test chỉ chứng minh một hành vi.

## 12. Cô lập test khi chạy song song

Khi nhiều test dùng chung Neo4j container hoặc database, cleanup toàn cục như MATCH (n) DETACH DELETE n có thể xóa fixture của test khác. Đây là lỗi đặc biệt dễ gặp khi CI chạy test song song.

Các nguyên tắc cô lập:

1. Mỗi test method có testRunId duy nhất.
2. Mọi node và relationship fixture đều mang marker.
3. Cleanup chỉ xóa dữ liệu có marker của test hiện tại.
4. Không dùng ID cố định chung giữa các test chạy song song.
5. Không chia sẻ node fixture giữa test nếu cleanup của từng test có thể detach relationship của node đó.
6. Với test cần schema/database riêng, dùng database hoặc container riêng theo suite/worker.
7. Nếu test thay đổi constraint/index hoặc cấu hình DBMS, không chạy song song trên cùng database trừ khi đã cô lập được.
8. Cleanup phải hoàn tất trước khi test tiếp theo sử dụng lại fixture hoặc ID.

Một testRunId ngẫu nhiên giảm xung đột ID nhưng không tự giải quyết việc hai test cùng sửa một node global. Hãy cô lập graph fixture và chỉ chia sẻ dữ liệu bất biến.

## 13. Cleanup khi test thất bại hoặc bị hủy

@AfterEach vẫn là nơi phù hợp để dọn fixture sau assertion thất bại thông thường. Nếu tiến trình bị kill hoặc container dừng đột ngột, cleanup trong test có thể không chạy. Vì vậy, container/database riêng cho test suite là lớp cô lập quan trọng.

Có thể thêm một bước cleanup theo namespace trước khi chạy suite để xử lý dữ liệu còn sót từ lần chạy trước, nhưng namespace đó phải dành riêng cho suite và không được dùng bởi môi trường khác. Không chạy lệnh xóa toàn bộ graph trên database dùng chung.

Nếu cleanup cần nhiều query, ghép chúng tuần tự trong một publisher và verify publisher đó complete. Nếu cleanup query phát lỗi, giữ lỗi để test fail và điều tra. Không chuyển lỗi cleanup thành success chỉ để báo cáo test xanh.

## 14. Những lỗi thường gặp khi kiểm thử reactive

| Lỗi | Vì sao sai | Cách xử lý |
| --- | --- | --- |
| Tạo publisher nhưng không subscribe | Query chưa được thực thi | Dùng StepVerifier và verify |
| Gọi subscribe() trong service | Tạo subscription tách khỏi transaction của caller | Trả publisher và ghép bằng flatMap/then |
| Đặt @Transactional lên test method rồi gọi reactive repository | Transaction test imperative không tự tạo reactive context | Đặt transaction ở reactive service hoặc TransactionalOperator |
| Assert graph ngay sau khi gọi service | Transaction có thể chưa complete | Chờ verifyComplete/verify rồi mới đọc |
| Dùng một transaction cho cả test và cleanup | Cleanup có thể chưa độc lập với thao tác được kiểm tra | Chạy cleanup sau transaction và chờ riêng |
| Cleanup bằng MATCH toàn bộ graph | Xóa fixture của test khác | Dùng testRunId và phạm vi dữ liệu riêng |
| Cleanup subscribe rồi bỏ qua | Test tiếp theo có thể bắt đầu trước khi xóa xong | Trả Mono<Void> và verifyComplete |
| Nuốt lỗi cleanup | Dữ liệu sót lại làm sai kết quả về sau | Để cleanup error làm test thất bại |
| Mock repository để chứng minh rollback | Mock không có transaction Neo4j | Dùng Neo4j thật và gọi service qua Spring proxy |
| Đọc lại trong cùng transaction | Chưa chứng minh commit ra database | Đọc sau khi transactional publisher kết thúc |

## 15. Quy trình viết một reactive integration test

1. Xác định hành vi cần chứng minh: commit, rollback, thứ tự thao tác hay cleanup.
2. Chọn Neo4j thật có phiên bản tương thích với ứng dụng.
3. Cấu hình reactive SDN, Driver và ReactiveNeo4jTransactionManager.
4. Inject service/repository/client từ Spring context.
5. Tạo testRunId riêng cho test method.
6. Dọn fixture cũ bằng cleanup publisher và chờ complete.
7. Tạo fixture bằng publisher được ghép trong pipeline.
8. Dùng StepVerifier subscribe và chờ complete hoặc error.
9. Sau transaction, đọc graph bằng publisher mới để xác minh trạng thái đã commit/rollback.
10. Dọn fixture trong @AfterEach bằng publisher riêng và chờ complete.
11. Chạy test song song để phát hiện cleanup hoặc ID bị chia sẻ.
12. Nếu test dùng retry/cancellation, kiểm tra số subscription và idempotency riêng.

Một reactive test tốt không chỉ xác nhận giá trị Mono phát ra. Nó còn chứng minh transaction kết thúc đúng thời điểm, dữ liệu graph có trạng thái đúng sau commit/rollback và cleanup đã hoàn tất trước khi test kết thúc.

## 16. Bài tập tự kiểm tra

1. Vì sao gọi repository reactive mà không subscribe chưa làm query chạy?
2. Transaction reactive được truyền qua Reactor Context như thế nào?
3. Vì sao @Transactional trên test method JUnit không mặc nhiên tạo reactive transaction?
4. Khi nào nên dùng @Transactional và khi nào nên dùng TransactionalOperator?
5. Vì sao cần chờ StepVerifier.verifyComplete() trước khi đọc lại graph?
6. Làm thế nào để kiểm tra repository và ReactiveNeo4jClient cùng rollback?
7. Vì sao error signal cần đi qua transactional boundary để kích hoạt rollback?
8. onErrorResume đặt bên trong và bên ngoài transaction có thể tạo khác biệt gì?
9. Vì sao cleanup phải trả publisher và được chờ hoàn tất?
10. testRunId giúp cô lập fixture khi chạy song song ra sao?
11. Vì sao DETACH DELETE cần được giới hạn vào node do test sở hữu?
12. Cancellation khác complete như thế nào đối với transaction?
13. Cần kiểm tra điều gì khi retry có thể thực thi lại một reactive transaction?

Khi hoàn thành bài học, bạn cần viết được reactive test chờ đúng vòng đời publisher, chứng minh các thao tác repository/client cùng commit hoặc rollback, đọc trạng thái graph sau transaction và cleanup fixture tường minh. Đây là nền tảng để kiểm thử SDN reactive ổn định ngay cả khi test chạy lặp, song song hoặc gặp lỗi giữa pipeline.

## Tài liệu tham khảo

- [Spring Data Neo4j – Transactions](https://docs.spring.io/spring-data/neo4j/reference/transactions.html)
- [Spring Framework – Reactive Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction/programmatic.html)
- [Project Reactor – Testing with StepVerifier](https://projectreactor.io/docs/core/release/reference/testing.html)
- [Project Reactor – Context](https://projectreactor.io/docs/core/release/reference/advancedFeatures/context.html)
- [Testcontainers – Neo4j Module](https://java.testcontainers.org/modules/databases/neo4j/)

