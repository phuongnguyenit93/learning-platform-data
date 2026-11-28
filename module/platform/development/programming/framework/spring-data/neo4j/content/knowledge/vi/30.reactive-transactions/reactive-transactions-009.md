# Kiểm thử reactive bằng StepVerifier và xác minh kết quả sau commit

Spring Data Neo4j (SDN) reactive sử dụng Reactive Streams và Project Reactor để thực hiện thao tác dữ liệu dưới dạng publisher như **Mono** và **Flux**. Vì publisher chỉ bắt đầu thực thi khi có subscription, kiểm thử reactive cần xác minh cả tín hiệu mà publisher phát ra lẫn trạng thái dữ liệu cuối cùng trong Neo4j.

**StepVerifier** giúp kiểm soát subscription, demand, phần tử được phát, lỗi và tín hiệu hoàn tất. Khi kiểm thử transaction, chỉ xác nhận publisher trả về entity là chưa đủ: cần chờ transaction hoàn tất, sau đó đọc lại dữ liệu bằng một subscription độc lập để chứng minh thay đổi đã commit. Với trường hợp lỗi, cần xác minh các ghi trước đó đã rollback và không còn nhìn thấy trong database.

Bài học này tập trung vào cách viết integration test cho reactive repository và ReactiveNeo4jClient, dùng StepVerifier để xác minh tín hiệu, kiểm tra commit/rollback qua TransactionalOperator và thiết kế test không phụ thuộc vào thread hoặc thứ tự chạy ngẫu nhiên.

## Vòng đời của reactive publisher trong bài kiểm thử

Một lời gọi repository reactive thường chỉ tạo publisher. Database query được thực thi khi publisher được subscribe. Do đó, chỉ gọi method mà không subscribe không chứng minh thao tác đã xảy ra:

~~~java
Mono<Person> saveOperation = people.save(person);
// Chưa có subscription: thao tác save chưa được thực thi.
~~~

StepVerifier thực hiện subscription khi gọi verify. Có thể hình dung luồng kiểm thử như sau:

~~~text
Test
 |
 | tạo Mono/Flux
 v
Reactive repository hoặc ReactiveNeo4jClient
 |
 | publisher chưa chạy
 v
StepVerifier.verify(...)
 |
 | subscribe và phát demand
 v
Reactive transaction manager
 |
 | commit hoặc rollback
 v
Neo4j
 |
 | subscription đọc mới
 v
StepVerifier xác minh trạng thái đã lưu
~~~

Cần phân biệt ba thời điểm:

1. **Tạo publisher:** xây dựng pipeline, chưa nhất thiết có truy cập database.
2. **Subscription:** publisher bắt đầu thực thi và phát tín hiệu theo demand.
3. **Kết thúc transaction:** transaction manager commit hoặc rollback trước khi publisher được xem là kết thúc theo hợp đồng của transaction operator.

Trong test xác minh commit, hãy đợi publisher được bọc bởi transaction hoàn tất rồi mới thực hiện truy vấn đọc độc lập. Cách này giúp phép đọc sau đó kiểm tra trạng thái đã commit thay vì chỉ nhìn thấy dữ liệu trong transaction đang mở.

## Chuẩn bị integration test

Một integration test cần kết nối tới Neo4j thật hoặc một Neo4j test instance tương thích với phiên bản Driver và SDN của dự án. Có thể dùng Testcontainers, Neo4j Test Harness hoặc một database riêng dành cho test. Không nên dùng mock repository để kết luận transaction đã commit hoặc rollback trong database.

Ví dụ domain tối giản:

~~~java
import org.springframework.data.neo4j.core.schema.Id;
import org.springframework.data.neo4j.core.schema.Node;

@Node("Person")
public class Person {

    @Id
    private String employeeCode;

    private String fullName;

    protected Person() {
    }

    public Person(String employeeCode, String fullName) {
        this.employeeCode = employeeCode;
        this.fullName = fullName;
    }

    public String getEmployeeCode() {
        return employeeCode;
    }

    public String getFullName() {
        return fullName;
    }
}
~~~

Repository reactive:

~~~java
import org.springframework.data.neo4j.repository.ReactiveNeo4jRepository;

public interface PersonRepository
        extends ReactiveNeo4jRepository<Person, String> {
}
~~~

Để kiểm tra một transaction ghi nhiều node, thêm entity Project và repository tương ứng:

~~~java
import org.springframework.data.neo4j.core.schema.Id;
import org.springframework.data.neo4j.core.schema.Node;

@Node("Project")
public class Project {

    @Id
    private String projectCode;

    private String name;

    protected Project() {
    }

    public Project(String projectCode, String name) {
        this.projectCode = projectCode;
        this.name = name;
    }

    public String getProjectCode() {
        return projectCode;
    }

    public String getName() {
        return name;
    }
}
~~~

~~~java
import org.springframework.data.neo4j.repository.ReactiveNeo4jRepository;

public interface ProjectRepository
        extends ReactiveNeo4jRepository<Project, String> {
}
~~~

Test nên dùng ID duy nhất để tránh dữ liệu của lần chạy trước làm sai kết quả:

~~~java
String employeeCode = "test-" + UUID.randomUUID();
Person person = new Person(employeeCode, "Lan Nguyen");
~~~

Trong môi trường CI, nên cấp một database hoặc container riêng cho mỗi test suite, hoặc dọn dữ liệu test theo một nhãn/namespace được quản lý rõ ràng. Tránh xóa toàn bộ graph dùng chung nếu database có dữ liệu của tiến trình khác.

## Tạo TransactionalOperator cho Neo4j reactive

Trong ứng dụng SDN reactive, transaction manager là **ReactiveNeo4jTransactionManager**. Có thể tạo **TransactionalOperator** từ transaction manager này để bọc publisher:

~~~java
import org.springframework.data.neo4j.core.transaction.ReactiveNeo4jTransactionManager;
import org.springframework.transaction.reactive.TransactionalOperator;

TransactionalOperator transactions =
    TransactionalOperator.create(reactiveNeo4jTransactionManager);
~~~

Trong integration test dùng Spring context, inject transaction manager đã được cấu hình bởi SDN:

~~~java
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.data.neo4j.core.transaction.ReactiveNeo4jTransactionManager;
import org.springframework.transaction.reactive.TransactionalOperator;
import org.junit.jupiter.api.BeforeEach;

@SpringBootTest
class ReactiveTransactionIntegrationTest {

    @Autowired
    PersonRepository people;

    @Autowired
    ReactiveNeo4jTransactionManager transactionManager;

    private TransactionalOperator transactions;

    @BeforeEach
    void setUp() {
        transactions = TransactionalOperator.create(transactionManager);
    }
}
~~~

Đây là ví dụ cấu trúc test. Dự án cần có cấu hình kết nối Neo4j test riêng và các dependency kiểm thử tương ứng. Nếu ứng dụng có nhiều reactive transaction manager, hãy inject đúng bean Neo4j bằng qualifier thay vì dựa vào lựa chọn tự động.

Không tạo một transaction manager mới trong từng test. Hãy dùng manager mà repository và ReactiveNeo4jClient của Spring context đang sử dụng; nếu mỗi thành phần dùng manager hoặc driver khác nhau, chúng có thể không tham gia cùng transaction.

## Xác minh publisher bằng StepVerifier

StepVerifier cho phép mô tả tuần tự các tín hiệu mong đợi. Những thao tác thường dùng:

| API | Mục đích |
|---|---|
| create(publisher) | Tạo verifier và chuẩn bị subscription |
| expectNext(value) | Mong đợi phần tử bằng giá trị chỉ định |
| expectNextMatches(predicate) | Kiểm tra phần tử theo điều kiện |
| assertNext(consumer) | Chạy assertion trên phần tử kế tiếp |
| expectNextCount(n) | Mong đợi đúng số phần tử |
| expectError(type) | Mong đợi lỗi thuộc kiểu chỉ định |
| expectErrorMatches(predicate) | Kiểm tra lỗi bằng predicate |
| expectComplete() | Mong đợi tín hiệu hoàn tất |
| thenRequest(n) | Yêu cầu thêm n phần tử |
| thenCancel() | Hủy subscription |
| verify(timeout) | Chạy kịch bản và giới hạn thời gian chờ |

Ví dụ xác minh một repository method trả đúng một Person:

~~~java
StepVerifier.create(people.findById(employeeCode))
    .assertNext(found -> {
        assertThat(found.getEmployeeCode()).isEqualTo(employeeCode);
        assertThat(found.getFullName()).isEqualTo("Lan Nguyen");
    })
    .verifyComplete();
~~~

Nếu cần giới hạn thời gian cho test có thể treo do kết nối hoặc query, dùng verify với timeout:

~~~java
StepVerifier.create(people.findById(employeeCode))
    .expectNextMatches(person ->
        person.getEmployeeCode().equals(employeeCode)
    )
    .expectComplete()
    .verify(Duration.ofSeconds(10));
~~~

Không nên đặt timeout quá ngắn khiến test thất bại ngẫu nhiên trên CI tải cao. Chọn timeout theo thời gian khởi tạo database, độ trễ mạng và giới hạn của môi trường test.

## Xác minh dữ liệu sau khi transaction commit

Một test commit nên thực hiện hai bước riêng:

1. Ghi dữ liệu trong TransactionalOperator và đợi publisher kết thúc thành công.
2. Sau khi verifier hoàn tất, mở một subscription mới để đọc lại bằng repository.

Ví dụ:

~~~java
import java.time.Duration;
import java.util.UUID;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.data.neo4j.core.transaction.ReactiveNeo4jTransactionManager;
import org.springframework.transaction.reactive.TransactionalOperator;

import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest
class ReactiveCommitIntegrationTest {

    @Autowired
    PersonRepository people;

    @Autowired
    ReactiveNeo4jTransactionManager transactionManager;

    @Test
    void savesPersonAndReadsItAfterCommit() {
        TransactionalOperator transactions =
            TransactionalOperator.create(transactionManager);

        String employeeCode = "test-" + UUID.randomUUID();
        Person person = new Person(employeeCode, "Lan Nguyen");

        Mono<Person> write = transactions.transactional(
            people.save(person)
                .thenReturn(person)
        );

        StepVerifier.create(write)
            .expectNextMatches(saved ->
                saved.getEmployeeCode().equals(employeeCode)
            )
            .expectComplete()
            .verify(Duration.ofSeconds(10));

        // Đây là subscription mới, sau khi transaction phía trên đã hoàn tất.
        StepVerifier.create(people.findById(employeeCode))
            .assertNext(found -> {
                assertThat(found.getEmployeeCode()).isEqualTo(employeeCode);
                assertThat(found.getFullName()).isEqualTo("Lan Nguyen");
            })
            .expectComplete()
            .verify(Duration.ofSeconds(10));

        StepVerifier.create(people.deleteById(employeeCode))
            .verifyComplete();
    }
}
~~~

Lệnh **verify(...)** chờ publisher được bọc bởi TransactionalOperator kết thúc. Với transaction thành công, transaction manager hoàn tất commit trước khi tín hiệu kết thúc được truyền tới verifier. Truy vấn **findById** ở bước sau tạo subscription độc lập và xác minh dữ liệu có thể được đọc lại từ Neo4j.

Không dùng kết quả object vừa trả về từ save làm bằng chứng duy nhất của commit. Object đó có thể chỉ phản ánh giá trị trong bộ nhớ hoặc dữ liệu nhìn thấy trong transaction hiện tại. Phép đọc độc lập sau khi commit mới kiểm tra trạng thái đã được lưu.

Nếu dùng Neo4j cluster với read routing, hãy bảo đảm test đọc theo cơ chế causal consistency/bookmark phù hợp để truy vấn đọc nhìn thấy transaction vừa commit. Khi kiểm thử với một Neo4j instance đơn, vấn đề routing replica thường không xuất hiện.

## Kiểm thử nhiều thao tác trong cùng transaction

Một transaction thường bao gồm nhiều thao tác repository. Test nên xác minh tất cả dữ liệu cần thiết xuất hiện sau commit:

~~~java
Mono<Person> writeAggregate = transactions.transactional(
    people.save(person)
        .then(projects.save(project))
        .thenReturn(person)
);

StepVerifier.create(writeAggregate)
    .expectNextMatches(saved ->
        saved.getEmployeeCode().equals(person.getEmployeeCode())
    )
    .expectComplete()
    .verify(Duration.ofSeconds(10));

StepVerifier.create(people.findById(person.getEmployeeCode()))
    .expectNextMatches(saved ->
        saved.getFullName().equals(person.getFullName())
    )
    .expectComplete()
    .verify(Duration.ofSeconds(10));

StepVerifier.create(projects.findById(project.getProjectCode()))
    .expectNextMatches(saved ->
        saved.getName().equals(project.getName())
    )
    .expectComplete()
    .verify(Duration.ofSeconds(10));
~~~

Các lời gọi save nằm trong cùng publisher được bọc bởi một TransactionalOperator, nên cùng tham gia transaction reactive nếu repository dùng cùng ReactiveNeo4jTransactionManager. Hai truy vấn đọc sau đó xác minh cả hai node đã tồn tại sau commit.

Nếu use case có tạo relationship bằng ReactiveNeo4jClient, hãy đưa query tạo relationship vào cùng pipeline và cùng transaction context. Sau commit, dùng một truy vấn đọc độc lập kiểm tra cả hai endpoint và relationship. Chỉ xác nhận hai node tồn tại chưa chứng minh relationship đã được ghi.

## Kiểm thử rollback khi publisher phát lỗi

Để kiểm tra atomicity, tạo một publisher thực hiện một hoặc nhiều thao tác ghi rồi phát lỗi. TransactionalOperator nhận tín hiệu lỗi và rollback transaction:

~~~java
@Test
void rollsBackWritesWhenPublisherFails() {
    String employeeCode = "test-" + UUID.randomUUID();
    Person person = new Person(employeeCode, "Rollback Candidate");

    Mono<Void> writeAndFail = transactions.transactional(
        people.save(person)
            .then(Mono.<Void>error(
                new IllegalStateException("force rollback")
            ))
    );

    StepVerifier.create(writeAndFail)
        .expectError(IllegalStateException.class)
        .verify(Duration.ofSeconds(10));

    // Đọc bằng subscription mới sau khi rollback đã hoàn tất.
    StepVerifier.create(people.findById(employeeCode))
        .verifyComplete();
}
~~~

Test xác minh hai điều: publisher kết thúc bằng lỗi mong đợi; và truy vấn độc lập không tìm thấy Person. Nếu chỉ kiểm tra lỗi mà không đọc lại database, chưa chứng minh được thao tác ghi trước đó đã rollback.

Có thể mở rộng test với hai thao tác save:

~~~java
Mono<Void> writeTwoNodesAndFail = transactions.transactional(
    people.save(person)
        .then(projects.save(project))
        .then(Mono.<Void>error(
            new IllegalStateException("fail after both writes")
        ))
);
~~~

Sau khi xác minh lỗi, đọc lại cả Person và Project. Cả hai phải không tồn tại nếu mọi thao tác đã tham gia cùng transaction manager và transaction được rollback.

Nếu exception phát sinh từ constraint violation hoặc lỗi Cypher, hãy kiểm tra exception thực tế được truyền qua Reactor. Một số lỗi có thể được bọc trong exception của Spring Data hoặc Driver; khi đó dùng **expectErrorMatches** để xác minh loại lỗi gốc hoặc cause chain thay vì giả định mọi lỗi đều có cùng lớp.

## Xác minh rollback-only

Không phải lỗi nghiệp vụ nào cũng cần phát ra exception. Reactive transaction callback có thể được đánh dấu rollback-only thông qua transaction status khi dùng API phù hợp của Spring. Với test đơn giản, có thể mô phỏng điều kiện từ chối bằng lỗi publisher vì đây là đường đi phổ biến và rõ ràng.

Khi cần xác minh rollback-only mà vẫn trả một kết quả nghiệp vụ, dùng API callback của TransactionalOperator với ReactiveTransaction:

~~~java
Flux<Boolean> rejected = transactions.execute(status ->
    people.save(person)
        .then(Mono.fromSupplier(() -> {
            status.setRollbackOnly();
            return false;
        }))
);

StepVerifier.create(rejected)
    .expectNext(false)
    .expectComplete()
    .verify(Duration.ofSeconds(10));
~~~

Callback nhận transaction status trong Reactor Context. Khi status đã được đánh dấu rollback-only, transaction không commit dù publisher callback hoàn tất bình thường. Kết quả false vẫn có thể được phát tới subscriber; sau khi verifier hoàn tất, cần đọc lại bằng subscription độc lập để xác nhận Person không tồn tại.

~~~java
StepVerifier.create(people.findById(person.getEmployeeCode()))
    .verifyComplete();
~~~

Cần kiểm tra chữ ký API callback theo phiên bản Spring Framework đang dùng. Nếu dự án không dùng overload này, có thể đặt logic đánh dấu rollback-only trong reactive transaction callback tương ứng của phiên bản hoặc dùng lỗi publisher để kiểm thử đường rollback.

## Kiểm thử demand và cancellation

StepVerifier có thể bắt đầu với demand bằng 0 rồi yêu cầu từng phần tử:

~~~java
StepVerifier.create(people.findAll(), 0)
    .thenRequest(1)
    .expectNextCount(1)
    .thenRequest(2)
    .expectNextCount(2)
    .thenCancel()
    .verify(Duration.ofSeconds(10));
~~~

Test này cần fixture có ít nhất bốn Person. Nó xác minh pipeline phát dữ liệu khi có demand và subscriber có thể hủy sau khi nhận ba phần tử mà publisher vẫn còn dữ liệu.

Nếu publisher được bọc trong transaction, cancellation cũng là một tín hiệu kết thúc cần được kiểm tra. Reactive transaction của Spring xử lý cancel như một lý do rollback; subscriber không truyền nguyên nhân hủy cho transaction manager. Các operator như take(n), next() hoặc timeout có thể phát cancel khi chúng đã nhận đủ dữ liệu hoặc hết thời gian. Vì vậy, khi bọc Flux nhiều phần tử trong transaction, cần tiêu thụ đầy đủ output nếu mục tiêu là commit. Nếu chủ động hủy, hãy xác minh cleanup và trạng thái database sau đó; không coi thenCancel() đơn lẻ là bằng chứng rollback nếu chưa đọc lại trạng thái.

Ví dụ dùng take(1) để hủy một batch ghi sau phần tử đầu tiên:

~~~java
Flux<Person> batchWrite = transactions.transactional(
    Flux.just(first, second, third)
        .concatMap(people::save)
);

StepVerifier.create(batchWrite.take(1))
    .expectNextMatches(saved ->
        saved.getEmployeeCode().equals(first.getEmployeeCode())
    )
    .verifyComplete();

// take(1) đã hủy upstream; transaction bị rollback.
StepVerifier.create(people.findById(first.getEmployeeCode()))
    .verifyComplete();
~~~

Trong ví dụ này, nguồn có nhiều phần tử nên take(1) hoàn tất downstream bằng cách cancel upstream. TransactionalOperator nhận cancel và rollback; truy vấn đọc sau đó xác nhận node đầu tiên cũng không được commit. Nếu thay nguồn bằng một Mono hoặc Flux chỉ có một phần tử, publisher có thể hoàn tất tự nhiên và commit, vì vậy test phải có nhiều phần tử để kiểm tra cancellation thực sự.

Ví dụ kiểm tra demand nên được tách khỏi test commit/rollback để mỗi test chỉ chứng minh một hành vi rõ ràng. Không dùng onBackpressureDrop trong pipeline kiểm thử giao dịch nếu nghiệp vụ yêu cầu mọi lệnh ghi đều phải được thực hiện.

## Kiểm thử ReactiveNeo4jClient trong transaction

Repository không phải cách duy nhất để thao tác graph. ReactiveNeo4jClient cũng tham gia reactive transaction khi dùng cùng cấu hình SDN và transaction manager.

Ví dụ ghi một node bằng repository rồi tạo relationship bằng Cypher trong cùng transaction:

~~~java
Mono<Person> createAndLink = transactions.transactional(
    people.save(person)
        .then(projects.save(project))
        .then(
            client.query("""
                MATCH (p:Person {employeeCode: $employeeCode})
                MATCH (pr:Project {projectCode: $projectCode})
                MERGE (p)-[:WORKS_ON]->(pr)
                """)
                .bind(person.getEmployeeCode()).to("employeeCode")
                .bind(project.getProjectCode()).to("projectCode")
                .run()
        )
        .thenReturn(person)
);
~~~

Sau khi verifier xác nhận publisher hoàn tất, dùng một truy vấn đọc độc lập để xác minh pattern:

~~~cypher
MATCH (p:Person {employeeCode: $employeeCode})
      -[:WORKS_ON]->
      (pr:Project {projectCode: $projectCode})
RETURN count(*) AS relationshipCount;
~~~

Kết quả mong đợi là 1 nếu relationship được tạo đúng một lần. Nếu query tạo relationship có thể trả về nhiều dòng do graph có dữ liệu trùng, hãy dùng ràng buộc dữ liệu và điều kiện match rõ ràng để test có tính xác định.

Nếu test rollback, cố tình phát lỗi sau câu query tạo relationship rồi đọc lại graph. Cả node và relationship được tạo trong transaction đó phải biến mất. Đây là cách kiểm tra cả thao tác mapping entity và thao tác Cypher cùng tham gia một transaction.

## Dọn dữ liệu test và tránh test phụ thuộc lẫn nhau

Mỗi test nên tạo ID riêng bằng UUID hoặc một test namespace. Điều này tránh xung đột khi test chạy song song và tránh vô tình đọc dữ liệu từ lần chạy trước.

Một số nguyên tắc:

- Không dùng mã nhân viên cố định trong nhiều test chạy đồng thời.
- Không xóa toàn bộ database dùng chung trong mỗi test.
- Dọn node test sau khi hoàn tất bằng reactive repository hoặc query có điều kiện rõ ràng.
- Dùng database/container riêng cho test suite khi cần reset dữ liệu toàn bộ.
- Nếu có relationship, xóa theo mô hình và chính sách detach phù hợp; tránh để node liên quan còn sót lại.
- Đảm bảo test rollback không phụ thuộc vào dữ liệu được tạo bởi test commit trước đó.

Không đặt test reactive trong một transaction imperative của test framework rồi giả định nó sẽ bao bọc publisher. Reactive transaction dùng Reactor Context và ReactiveTransactionManager; hãy tạo transaction trong chính pipeline reactive bằng TransactionalOperator hoặc cơ chế reactive tương ứng. Với kiểm thử commit, cần để transaction kết thúc thật sự trước khi đọc lại.

## Những lỗi thường gặp

| Lỗi | Hậu quả | Cách xử lý |
|---|---|---|
| Chỉ gọi repository method mà không subscribe | Không có bằng chứng query đã chạy | Dùng StepVerifier để subscribe |
| Chỉ xác minh entity trả về từ save | Chưa chứng minh transaction đã commit | Đọc lại bằng subscription độc lập sau verify |
| Kiểm tra lỗi nhưng không kiểm tra database | Chưa chứng minh rollback | Đọc lại và xác nhận node/relationship không tồn tại |
| Dùng transaction manager imperative cho reactive repository | Publisher không tham gia đúng transaction | Dùng ReactiveNeo4jTransactionManager |
| Repository và client dùng manager/driver khác nhau | Các thao tác có thể commit độc lập | Dùng cùng cấu hình và transaction manager |
| Tự gọi subscribe() trong service | Tách luồng thực thi khỏi verifier và transaction context | Trả Mono/Flux cho tầng gọi |
| Dùng timeout quá ngắn | Test thất bại ngẫu nhiên trên CI | Chọn timeout theo môi trường và khởi tạo database |
| Test dùng ID cố định | Xung đột khi chạy song song hoặc chạy lại | Sinh ID duy nhất cho từng test |
| Dùng dữ liệu của test khác | Kết quả phụ thuộc thứ tự chạy | Tạo fixture độc lập và dọn dữ liệu |
| Dùng @Transactional imperative ở cấp test | Không bảo đảm quản lý publisher reactive | Dùng TransactionalOperator trong pipeline |
| Hủy subscription rồi khẳng định rollback ngay | Có thể kiểm tra trước khi cleanup hoàn tất | Chờ tín hiệu cleanup và xác minh database |
| Chỉ kiểm tra hai node, bỏ qua relationship | Không phát hiện relationship chưa commit | Đọc lại pattern graph đầy đủ |

## Bài tập thực hành

Với reactive repository PersonRepository và ProjectRepository, hãy thực hiện:

1. Tạo integration test kết nối Neo4j test instance.
2. Inject ReactiveNeo4jTransactionManager và tạo TransactionalOperator.
3. Dùng StepVerifier xác minh một Mono phát đúng Person và hoàn tất.
4. Ghi Person và Project trong cùng transaction, đợi verify hoàn tất rồi đọc lại từng node.
5. Tạo relationship bằng ReactiveNeo4jClient trong cùng transaction và xác minh bằng một query đọc độc lập.
6. Phát IllegalStateException sau hai thao tác ghi; xác minh cả hai node đều không tồn tại.
7. Tạo một test lỗi do constraint hoặc Cypher và kiểm tra exception được truyền tới StepVerifier.
8. Bắt đầu StepVerifier với demand bằng 0, yêu cầu từng phần tử và hủy subscription.
9. Kiểm tra cleanup sau cancellation nếu publisher đang nằm trong transaction.
10. Dùng UUID để tạo dữ liệu test và thiết kế cleanup không xóa dữ liệu của test khác.
11. Chạy test song song và xác nhận không có xung đột ID hoặc phụ thuộc thứ tự.
12. Giải thích vì sao kết quả trả về từ save không thay thế phép đọc độc lập sau commit.

Khi kiểm thử reactive transaction trong Spring Data Neo4j, hãy xác minh cả tín hiệu publisher và trạng thái graph sau khi transaction kết thúc. StepVerifier kiểm tra demand, dữ liệu, lỗi và completion; truy vấn đọc bằng subscription mới xác nhận commit; còn test phát lỗi rồi đọc lại database chứng minh rollback. Dùng ReactiveNeo4jTransactionManager đúng cấu hình, giữ các thao tác trong cùng Reactor Context và tạo dữ liệu test độc lập để kết quả có thể lặp lại.

Tài liệu tham khảo chính thức:

- [Spring Data Neo4j - Reactive transactions](https://docs.spring.io/spring-data/neo4j/reference/transactions.html)
- [Spring Framework - Reactive transaction management](https://docs.spring.io/spring-framework/reference/data-access/transaction/programmatic.html)
- [TransactionalOperator API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/transaction/reactive/TransactionalOperator.html)
- [Project Reactor - Testing with StepVerifier](https://projectreactor.io/docs/core/release/reference/testing.html)
- [Neo4j Java Driver - Reactive programming](https://neo4j.com/docs/java-manual/current/reactive/)

