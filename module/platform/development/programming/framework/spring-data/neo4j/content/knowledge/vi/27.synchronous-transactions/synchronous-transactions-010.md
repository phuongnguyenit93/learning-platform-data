# Quản lý giao dịch lập trình bằng TransactionTemplate

Spring Data Neo4j (SDN) hỗ trợ quản lý transaction theo hai cách phổ biến: khai báo ranh giới bằng `@Transactional` hoặc điều khiển tường minh bằng `TransactionTemplate`. Với cách thứ hai, ứng dụng xác định chính xác đoạn lệnh cần chạy trong transaction, nhận `TransactionStatus` để đánh dấu rollback và lấy kết quả ngay sau khi transaction kết thúc.

`TransactionTemplate` đặc biệt hữu ích khi ranh giới transaction phụ thuộc điều kiện tại thời điểm chạy, khi cần bọc một đoạn xử lý trong private method hoặc lời gọi nội bộ cùng bean, hoặc khi cần chạy một nhóm thao tác `Neo4jClient`, `Neo4jTemplate` và repository như một đơn vị công việc. Bài học này tập trung vào ứng dụng SDN đồng bộ (imperative), cách cấu hình template, commit/rollback, propagation, read-only và kiểm thử.

## TransactionTemplate trong ứng dụng SDN đồng bộ

Neo4j là cơ sở dữ liệu có transaction. Các thao tác ghi phải nằm trong transaction; driver có thể tự quản lý transaction cho một số thao tác đơn lẻ, nhưng khi một use case gồm nhiều lệnh, cần có một ranh giới chung để tất cả cùng commit hoặc rollback.

`TransactionTemplate` thuộc Spring Framework, không phải API riêng của Neo4j. Nó nhận một `PlatformTransactionManager` và gọi callback trong transaction do transaction manager đó quản lý. Trong ứng dụng SDN imperative, transaction manager tương ứng là `Neo4jTransactionManager`.

SDN tích hợp transaction manager với Neo4j Java Driver. Khi transaction được mở, session và transaction native của Neo4j được đồng bộ với transaction Spring. Các thao tác từ repository, `Neo4jTemplate` và `Neo4jClient` dùng cùng cấu hình transaction có thể tham gia transaction đang chạy trên thread hiện tại.

Luồng xử lý:

~~~text
Service
  |
  v
TransactionTemplate.execute(...)
  |
  v
Neo4jTransactionManager
  |
  v
Neo4j transaction
  |
  +--> PersonRepository.save(...)
  |
  +--> ProjectRepository.save(...)
  |
  +--> Neo4jClient.query(...).run()
  |
  v
Callback kết thúc
  |
  +--> commit nếu thành công
  |
  +--> rollback nếu có lỗi hoặc được đánh dấu rollback-only
~~~

Điểm quan trọng là các thao tác phải dùng đúng `Neo4jTransactionManager` và chạy trong cùng ngữ cảnh đồng bộ. Nếu một repository dùng transaction manager khác hoặc thao tác được đẩy sang thread khác, chúng có thể không tham gia transaction đang mở.

## Lấy transaction manager và tạo TransactionTemplate

Trong ứng dụng Spring Boot có SDN, cấu hình thường tạo bean `Neo4jTransactionManager` với tên `neo4jTransactionManager` và alias `transactionManager`. Nếu ứng dụng chỉ có một `PlatformTransactionManager`, có thể inject trực tiếp kiểu interface đó. Nếu có nhiều transaction manager, chỉ rõ bean Neo4j bằng `@Qualifier`.

Ví dụ tạo template trong service:

~~~java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.data.neo4j.core.Neo4jClient;
import org.springframework.stereotype.Service;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.support.TransactionTemplate;

@Service
public class PersonProvisioningService {

    private final TransactionTemplate transactionTemplate;
    private final PersonRepository people;
    private final ProjectRepository projects;
    private final Neo4jClient neo4jClient;

    public PersonProvisioningService(
            @Qualifier("neo4jTransactionManager")
            PlatformTransactionManager transactionManager,
            PersonRepository people,
            ProjectRepository projects,
            Neo4jClient neo4jClient) {

        this.transactionTemplate = new TransactionTemplate(transactionManager);
        this.people = people;
        this.projects = projects;
        this.neo4jClient = neo4jClient;
    }
}
~~~

`TransactionTemplate` được cấu hình một lần trong constructor và tái sử dụng cho các lời gọi service. Template giữ cấu hình transaction; mỗi lần gọi `execute` hoặc `executeWithoutResult`, nó mở hoặc tham gia transaction theo propagation đã thiết lập.

Nếu dự án chỉ có một transaction manager, constructor có thể nhận `PlatformTransactionManager` mà không cần qualifier. Nếu dự án có nhiều Neo4j driver, nhiều database hoặc nhiều transaction manager, phải inject đúng manager tương ứng với `Neo4jClient` và repository được sử dụng.

Các repository tối thiểu trong ví dụ:

~~~java
import org.springframework.data.neo4j.repository.Neo4jRepository;

public interface PersonRepository extends Neo4jRepository<Person, String> {
}
~~~

~~~java
import org.springframework.data.neo4j.repository.Neo4jRepository;

public interface ProjectRepository extends Neo4jRepository<Project, String> {
}
~~~

## Chạy nhiều thao tác trong một transaction

Giả sử một use case khởi tạo người dùng nội bộ cần lưu `Person`, lưu `Project` mặc định và tạo relationship `WORKS_ON`. Nếu một trong các thao tác thất bại, dữ liệu đã ghi trước đó cần được rollback.

~~~java
public void provision(Person person, Project project) {

    transactionTemplate.executeWithoutResult(status -> {

        people.save(person);
        projects.save(project);

        neo4jClient.query("""
            MATCH (p:Person {employeeCode: $employeeCode})
            MATCH (pr:Project {projectCode: $projectCode})
            MERGE (p)-[:WORKS_ON]->(pr)
            """)
            .bind(person.getEmployeeCode()).to("employeeCode")
            .bind(project.getProjectCode()).to("projectCode")
            .run();
    });
}
~~~

Trong callback:

1. `people.save(person)` lưu node Person.
2. `projects.save(project)` lưu node Project.
3. `Neo4jClient` tạo hoặc giữ relationship `WORKS_ON`.
4. Khi callback hoàn tất bình thường, template yêu cầu transaction commit.

`Neo4jClient` tích hợp với transaction của SDN. Khi được dùng trong callback với cùng transaction manager và cấu hình driver/database, query tham gia transaction hiện tại thay vì tự tạo một transaction độc lập. Vì vậy, nếu bước thứ ba ném exception, hai thao tác save trước đó cũng được rollback.

Ví dụ này giả định entity đã có các property định danh và getter tương ứng. Trong ứng dụng thực tế, cần xác thực dữ liệu đầu vào và bảo đảm hai node đã được lưu thành công trước khi tạo relationship. `MERGE` giúp tránh tạo thêm relationship trùng theo pattern được chỉ định, nhưng không thay thế kiểm tra các quy tắc nghiệp vụ khác.

### Dùng execute khi cần trả kết quả

`execute(TransactionCallback<T>)` trả lại giá trị mà callback cung cấp:

~~~java
String employeeCode = transactionTemplate.execute(status -> {
    Person saved = people.save(person);
    projects.save(project);

    return saved.getEmployeeCode();
});
~~~

Template chỉ trả kết quả sau khi callback hoàn tất và transaction đã được xử lý. Nếu callback ném exception, exception được truyền ra ngoài và transaction bị rollback theo quy tắc của transaction manager.

Dùng `executeWithoutResult(...)` khi không cần giá trị trả về. Dùng `execute(...)` khi cần trả ID, số lượng bản ghi hoặc kết quả nghiệp vụ sau transaction.

## Rollback khi có lỗi

Nếu callback ném một unchecked exception như `IllegalStateException`, `RuntimeException` hoặc `Error`, `TransactionTemplate` yêu cầu rollback rồi truyền exception ra ngoài:

~~~java
public void createThenFail(Person person) {

    transactionTemplate.executeWithoutResult(status -> {
        people.save(person);

        throw new IllegalStateException("Simulated failure");
    });
}
~~~

Sau khi exception thoát khỏi callback, transaction không commit. Node Person vừa lưu trong callback cũng bị rollback nếu thao tác save đã tham gia đúng transaction đó.

Có thể đánh dấu rollback-only mà không cần ném exception:

~~~java
Boolean accepted = transactionTemplate.execute(status -> {
    people.save(person);

    if (!businessRuleAllows(person)) {
        status.setRollbackOnly();
        return false;
    }

    return true;
});
~~~

Trong ví dụ, callback trả về `false` và đánh dấu transaction rollback-only. Template không commit các thay đổi đã thực hiện trước đó. Cách này phù hợp khi điều kiện từ chối là kết quả nghiệp vụ bình thường và caller cần nhận kết quả để xử lý.

Cần chú ý trường hợp bắt exception ngay bên trong callback:

~~~java
transactionTemplate.executeWithoutResult(status -> {
    try {
        people.save(person);
        projects.save(project);
        performAdditionalWork();
    } catch (RuntimeException ex) {
        logFailure(ex);
        // Nếu không ném lại và không đánh dấu rollback-only,
        // callback có thể kết thúc bình thường và transaction được commit.
        status.setRollbackOnly();
    }
});
~~~

Nếu bắt exception rồi không ném lại, template không thể biết callback đã gặp lỗi. Hãy ném lại exception hoặc gọi `status.setRollbackOnly()` trước khi kết thúc callback. Không nuốt lỗi rồi để transaction commit ngoài ý muốn.

`TransactionTemplate` không cung cấp quy tắc rollback theo checked exception giống cách nhiều người cấu hình `@Transactional(rollbackFor = ...)`. Callback `TransactionCallback` thường truyền lỗi qua unchecked exception; nếu cần xử lý checked exception, hãy chuyển nó thành unchecked exception phù hợp hoặc đánh dấu rollback-only trước khi trả về.

## Đặt cấu hình transaction cho template

Có thể cấu hình propagation, timeout và read-only trước khi sử dụng template:

~~~java
import org.springframework.transaction.TransactionDefinition;
import org.springframework.transaction.support.TransactionTemplate;

TransactionTemplate readOnlyTemplate =
    new TransactionTemplate(transactionManager);

readOnlyTemplate.setReadOnly(true);
readOnlyTemplate.setTimeout(10);

TransactionTemplate requiresNewTemplate =
    new TransactionTemplate(transactionManager);

requiresNewTemplate.setPropagationBehavior(
    TransactionDefinition.PROPAGATION_REQUIRES_NEW
);
~~~

Các thuộc tính cần biết:

| Thuộc tính | Ý nghĩa |
|---|---|
| `setPropagationBehavior(...)` | Chọn cách tham gia hoặc tạo transaction |
| `setIsolationLevel(...)` | Yêu cầu mức isolation theo abstraction của Spring; hiệu lực phụ thuộc transaction manager và database |
| `setTimeout(...)` | Đặt thời gian tối đa theo giây nếu transaction manager hỗ trợ |
| `setReadOnly(true)` | Đánh dấu transaction chỉ đọc để transaction manager và hạ tầng có thể tối ưu cách thực thi |
| `setName(...)` | Gắn tên transaction để hỗ trợ theo dõi nếu transaction manager sử dụng thông tin này |

Không thay đổi cấu hình của một template dùng chung theo từng request. Nếu cần một template đọc và một template ghi, tạo hai instance với cấu hình cố định. Với Neo4j, không nên giả định các mức isolation đặt theo tên của hệ quản trị quan hệ sẽ tạo ra hành vi tương đương; cần tuân theo isolation mà Neo4j hỗ trợ và kiểm tra transaction manager của phiên bản đang dùng.

### Propagation thường gặp

Propagation xác định template xử lý thế nào khi thread hiện tại đã có transaction:

| Propagation | Hành vi |
|---|---|
| `PROPAGATION_REQUIRED` | Mặc định; tham gia transaction hiện tại hoặc tạo transaction mới nếu chưa có |
| `PROPAGATION_REQUIRES_NEW` | Tạm ngưng transaction hiện tại và mở transaction độc lập mới |
| `PROPAGATION_SUPPORTS` | Tham gia transaction nếu đã có; nếu không thì chạy không có transaction mới |
| `PROPAGATION_MANDATORY` | Yêu cầu phải có transaction hiện tại; nếu không sẽ báo lỗi |
| `PROPAGATION_NEVER` | Yêu cầu không có transaction hiện tại |
| `PROPAGATION_NOT_SUPPORTED` | Tạm ngưng transaction hiện tại và chạy ngoài transaction |

Với `REQUIRED`, các lời gọi template lồng nhau dùng cùng transaction manager thường tham gia transaction đang có. Nếu transaction ngoài rollback, các thao tác trong transaction tham gia cũng rollback.

`REQUIRES_NEW` tạo ranh giới độc lập. Nếu transaction bên trong commit rồi transaction bên ngoài rollback, thay đổi đã commit trong transaction bên trong vẫn tồn tại. Dùng propagation này có chủ đích, chẳng hạn lưu một bản ghi kiểm toán cần tồn tại độc lập, và hiểu rõ hệ quả nhất quán dữ liệu.

Không mặc định sử dụng `NESTED` cho Neo4j. Nested transaction và savepoint là khả năng phụ thuộc transaction manager; không nên giả định Neo4j có savepoint như một số hệ quản trị quan hệ. Kiểm tra hỗ trợ thực tế của phiên bản SDN và Neo4j trước khi thiết kế nghiệp vụ dựa trên nested semantics.

## Transaction chỉ đọc

Một transaction chỉ đọc có thể giúp SDN và driver lựa chọn cách thực thi phù hợp. Điều này đặc biệt hữu ích khi Neo4j chạy trong cluster có primary và read replica: đánh dấu thao tác đọc cho phép hạ tầng định tuyến truy vấn đọc phù hợp hơn.

Ví dụ cấu hình một template đọc riêng trong constructor service:

~~~java
private final TransactionTemplate readOnlyTemplate;

public PersonReadService(PlatformTransactionManager transactionManager) {
    this.readOnlyTemplate = new TransactionTemplate(transactionManager);
    this.readOnlyTemplate.setReadOnly(true);
}
~~~

Dùng template để đọc qua `Neo4jClient`:

~~~java
import java.util.Collection;

public Collection<Person> findActivePeople() {

    return readOnlyTemplate.execute(status ->
        neo4jClient.query("""
            MATCH (p:Person)
            WHERE p.active = true
            RETURN p
            ORDER BY p.fullName, p.employeeCode
            """)
            .fetchAs(Person.class)
            .all()
    );
}
~~~

`readOnlyTemplate` được cấu hình một lần khi khởi tạo service. Đoạn code dùng `Collection<Person>` vì `Neo4jClient.fetchAs(...).all()` trả về collection.

`readOnly = true` là metadata/hint cho transaction manager và hạ tầng. Không dùng nó như cơ chế phân quyền hoặc thay thế quyền truy cập database. Một truy vấn tùy chỉnh có thể gọi procedure có tác dụng ghi; ứng dụng vẫn phải kiểm soát nội dung query và quyền của database user.

## Kết hợp TransactionTemplate với repository, Neo4jTemplate và Neo4jClient

Các API đồng bộ của SDN có thể phối hợp trong cùng transaction khi chúng dùng cùng transaction manager và ngữ cảnh kết nối:

- **Repository:** phù hợp với thao tác entity theo aggregate và các method đã định nghĩa.
- **Neo4jTemplate:** phù hợp khi cần mapping entity nhưng muốn thao tác qua template.
- **Neo4jClient:** phù hợp khi cần viết Cypher trực tiếp và ánh xạ record theo ý muốn.

Ví dụ kết hợp repository và `Neo4jClient` đã trình bày ở phần trước. Với `Neo4jTemplate`, cách gọi tương tự:

~~~java
transactionTemplate.executeWithoutResult(status -> {
    neo4jTemplate.save(person);
    neo4jTemplate.save(project);

    neo4jClient.query("""
        MATCH (p:Person {employeeCode: $employeeCode})
        MATCH (pr:Project {projectCode: $projectCode})
        MERGE (p)-[:WORKS_ON]->(pr)
        """)
        .bind(person.getEmployeeCode()).to("employeeCode")
        .bind(project.getProjectCode()).to("projectCode")
        .run();
});
~~~

Không tự mở một `Driver.session()` và transaction native riêng cho từng thao tác nếu mục tiêu là tham gia transaction Spring đang mở. Session/transaction tự tạo có thể không thuộc transaction được quản lý bởi `Neo4jTransactionManager`. Dùng các API SDN đã tích hợp hoặc cơ chế truy xuất transaction native được tài liệu SDN hỗ trợ cho trường hợp đặc biệt.

## TransactionTemplate và @Transactional

Cả hai cách đều dùng transaction manager của Spring, nhưng thể hiện ranh giới transaction theo cách khác nhau:

| Tiêu chí | `@Transactional` | `TransactionTemplate` |
|---|---|---|
| Cách khai báo | Annotation trên class/method | Callback bao quanh đoạn code |
| Ranh giới | Thường theo method được proxy quản lý | Chính xác theo block `execute` |
| Private method | Không được proxy gọi trực tiếp | Có thể gọi template từ private method |
| Self-invocation | Lời gọi nội bộ cùng bean không đi qua proxy mặc định | Template vẫn thực thi khi được gọi trực tiếp |
| Rollback-only | Qua `TransactionAspectSupport` hoặc ném exception | Qua `TransactionStatus.setRollbackOnly()` |
| Propagation/read-only | Qua thuộc tính annotation | Qua cấu hình template |
| Phù hợp | Service method có ranh giới ổn định | Ranh giới động hoặc cần điều khiển tường minh |

Nên dùng `@Transactional` cho service method có ranh giới ổn định và cần dễ đọc. Dùng `TransactionTemplate` khi cần quyết định rõ thời điểm bắt đầu/kết thúc transaction, khi chỉ một đoạn trong method cần transaction hoặc khi gọi từ private method/self-invocation mà proxy không can thiệp.

Không cần bọc mọi repository call đơn lẻ bằng một template nếu repository đã quản lý transaction phù hợp. Giá trị chính của template là gom nhiều thao tác thành một đơn vị công việc và cho phép điều khiển transaction ngay tại nơi thực thi.

## Thread, thời gian sống và tác dụng phụ ngoài database

Transaction đồng bộ của SDN gắn với thread thực thi. Hãy giữ toàn bộ callback trên cùng thread:

~~~java
transactionTemplate.executeWithoutResult(status -> {
    people.save(person);

    // Không chuyển thao tác database sang @Async,
    // CompletableFuture hoặc thread pool khác tại đây.
});
~~~

Nếu tạo tác vụ bất đồng bộ trong callback, thread mới không tự kế thừa transaction đang mở. Lệnh ghi ở thread khác có thể chạy trong transaction riêng hoặc không có transaction như mong muốn.

Giữ transaction ngắn và tập trung vào thao tác database. Không mở transaction rồi chờ người dùng, gọi HTTP chậm, gửi email hoặc chạy công việc dài. Những tác dụng phụ ngoài Neo4j không tự rollback cùng transaction graph. Nếu cần phát thông báo sau khi commit, dùng transaction synchronization/event after-commit hoặc mô hình outbox để tránh gửi thông báo cho dữ liệu đã rollback.

`TransactionTemplate` điều khiển transaction của transaction manager được truyền vào. Nếu callback đồng thời ghi vào Neo4j và một database quan hệ, việc dùng `Neo4jTransactionManager` không tự tạo một transaction phân tán bảo đảm atomicity cho cả hai hệ thống. Cần thiết kế outbox, saga hoặc giải pháp distributed transaction phù hợp nếu nghiệp vụ yêu cầu phối hợp nhiều tài nguyên.

## Kiểm thử commit và rollback

Kiểm thử tích hợp nên xác nhận trạng thái cuối trong Neo4j sau khi callback hoàn tất. Ví dụ dùng Spring Boot test với Neo4j test harness hoặc Testcontainers, và không đặt test trong một transaction ngoài khiến assertion đọc lại vẫn tham gia transaction thử nghiệm:

~~~java
@Test
void rollsBackAllWritesWhenCallbackFails() {
    Person person = new Person("E-01", "Lan Nguyen");

    assertThrows(IllegalStateException.class, () ->
        transactionTemplate.executeWithoutResult(status -> {
            people.save(person);
            projects.save(new Project("PR-01", "Graph Search"));

            throw new IllegalStateException("force rollback");
        })
    );

    assertThat(people.findById("E-01")).isEmpty();
    assertThat(projects.findById("PR-01")).isEmpty();
}
~~~

Test xác nhận cả Person và Project không còn sau rollback. Phần setup entity và repository cần khớp constructor thực tế của dự án. Có thể bổ sung test cho trường hợp callback kết thúc bình thường để xác nhận dữ liệu được commit, và test cho `setRollbackOnly()` để xác nhận callback trả về nhưng dữ liệu vẫn không được lưu.

Nên kiểm tra thêm:

- Nhiều repository cùng tham gia một transaction.
- `Neo4jClient` dùng chung transaction với repository.
- Exception xảy ra ở bước cuối làm rollback các bước trước.
- Exception bị bắt trong callback nhưng transaction được đánh dấu rollback-only.
- Transaction read-only được sử dụng cho query đọc.
- Template tham gia transaction ngoài khi dùng propagation `REQUIRED`.

## Những lỗi thường gặp

| Lỗi | Hậu quả | Cách xử lý |
|---|---|---|
| Inject nhầm `PlatformTransactionManager` | Repository và template có thể không dùng cùng transaction | Chỉ rõ `neo4jTransactionManager` khi có nhiều manager |
| Mỗi repository call tự chạy transaction riêng | Một phần use case có thể commit dù bước sau thất bại | Bọc các thao tác liên quan trong một `TransactionTemplate` |
| Dùng `Neo4jClient` với cấu hình khác manager/driver/database | Query không tham gia transaction đang mở | Dùng cùng cấu hình SDN và transaction manager |
| Bắt exception rồi bỏ qua | Callback kết thúc bình thường và transaction có thể commit | Ném lại exception hoặc gọi `setRollbackOnly()` |
| Dùng `REQUIRES_NEW` mà không hiểu commit độc lập | Transaction trong có thể commit dù transaction ngoài rollback | Chỉ dùng khi cần tính độc lập rõ ràng |
| Giả định có nested transaction/savepoint | Rollback từng phần không hoạt động như thiết kế | Kiểm tra hỗ trợ của Neo4j transaction manager |
| Gọi database ở thread khác trong callback | Thao tác không thuộc transaction hiện tại | Giữ callback đồng bộ trên cùng thread |
| Gửi email hoặc gọi HTTP trong transaction | Transaction bị kéo dài; side effect không rollback | Thực hiện sau commit hoặc dùng outbox |
| Dùng read-only như quyền cấm ghi | Query/procedure có tác dụng phụ vẫn có thể gây thay đổi tùy hạ tầng | Kiểm soát quyền và câu lệnh thực tế |
| Dùng TransactionTemplate đồng bộ trong reactive flow | Chặn thread và không tham gia reactive transaction | Dùng `ReactiveTransactionManager` và `TransactionalOperator` |

## Bài tập thực hành

Với các entity `Person` và `Project`, hãy thực hiện:

1. Inject `PlatformTransactionManager` của Neo4j và tạo `TransactionTemplate`.
2. Viết service lưu Person, Project và relationship `WORKS_ON` trong một callback.
3. Cố tình ném `IllegalStateException` sau thao tác save cuối; kiểm tra mọi thay đổi đều rollback.
4. Thử dùng `status.setRollbackOnly()` và trả về kết quả nghiệp vụ thay vì ném exception.
5. Dùng `execute(...)` để trả về employeeCode sau khi commit.
6. Tạo template read-only và dùng `Neo4jClient` để truy vấn danh sách Person.
7. Thử `PROPAGATION_REQUIRES_NEW` trong một tình huống có transaction ngoài và quan sát tính độc lập khi rollback.
8. Gọi template từ private method và so sánh với lời gọi private method có `@Transactional`.
9. Tạo integration test xác nhận repository và Neo4jClient cùng tham gia transaction.
10. Giải thích vì sao tác vụ chạy trên thread khác hoặc email gửi trước commit không được rollback cùng transaction Neo4j.

Khi quản lý giao dịch lập trình trong Spring Data Neo4j, hãy truyền đúng `Neo4jTransactionManager` vào `TransactionTemplate`, đặt các thao tác repository/template/client liên quan trong cùng callback và quyết định rõ cách commit hoặc rollback. Dùng `TransactionStatus` khi cần đánh dấu rollback-only, giữ callback đồng bộ và ngắn, đồng thời chọn propagation phù hợp với ranh giới nghiệp vụ.

Tài liệu tham khảo chính thức:

- [Spring Data Neo4j FAQ - TransactionTemplate và Neo4jClient](https://docs.spring.io/spring-data/neo4j/reference/faq.html)
- [Neo4jTransactionManager API](https://docs.spring.io/spring-data/neo4j/reference/api/java/org/springframework/data/neo4j/core/transaction/Neo4jTransactionManager.html)
- [Spring Framework - Programmatic transaction management](https://docs.spring.io/spring-framework/reference/data-access/transaction/programmatic.html)

