# Phân biệt hành vi rollback của test với kết quả sau commit thực tế

Khi kiểm thử Spring Data Neo4j, một test có thể đọc được dữ liệu vừa ghi rồi vẫn kết thúc với database không có dữ liệu đó. Nguyên nhân thường là test đang chạy bên trong **test-managed transaction** của Spring TestContext và transaction này được rollback mặc định sau khi test hoàn tất.

Hành vi đó khác với transaction do service mở trong ứng dụng. Một service có `@Transactional` có thể commit thành công khi phương thức trả về, hoặc rollback khi runtime exception thoát khỏi transaction boundary. Muốn xác nhận kết quả thực tế sau commit, test phải quan sát database từ một transaction mới sau khi transaction ghi đã kết thúc.

## 1. Có hai loại transaction cần phân biệt

Trong integration test đồng bộ với Spring Data Neo4j, thường gặp hai loại transaction:

| Loại transaction | Ai bắt đầu? | Thời điểm kết thúc | Mặc định |
|---|---|---|---|
| Test-managed transaction | Spring TestContext khi test method/class được cấu hình `@Transactional` | Sau test method | Rollback |
| Application transaction | Spring transaction proxy khi service/repository có `@Transactional` | Khi phương thức transactional kết thúc | Commit nếu thành công; rollback theo rollback rules nếu thất bại |

Test-managed transaction thuộc cơ chế kiểm thử của Spring Framework. Nó giúp cô lập dữ liệu giữa các test bằng cách rollback thay đổi sau mỗi method. Transaction do service mở là hành vi của ứng dụng và phải được kiểm tra theo đúng ranh giới commit/rollback của service.

Với propagation mặc định `REQUIRED`, một service method được gọi trong khi test-managed transaction đang hoạt động sẽ tham gia transaction hiện có. Khi đó, service method trả về không có nghĩa dữ liệu đã commit; transaction bên ngoài của test vẫn còn mở.

Spring TestContext phải chọn đúng `PlatformTransactionManager` để mở test-managed transaction. Nếu ứng dụng có nhiều transaction manager, hãy chỉ định manager Neo4j phù hợp trong cấu hình `@Transactional` của test và service, dùng đúng bean name đã khai báo trong ứng dụng. Nếu test slice hoặc annotation tùy chỉnh có meta-annotation `@Transactional`, nó cũng có thể mở transaction dù test method không ghi annotation trực tiếp.

## 2. Vì sao test có thể đọc được dữ liệu nhưng database không giữ dữ liệu?

Giả sử test được đánh dấu `@Transactional`:

```java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.transaction.annotation.Transactional;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest
class PersonRepositoryTest {

    @Autowired
    PersonRepository repository;

    @Test
    @Transactional
    void savesPerson() {
        repository.save(new Person("P-100", "An"));

        assertThat(repository.findById("P-100")).isPresent();
    }
}
```

Trong lúc method chạy, lệnh `save` và `findById` cùng tham gia test-managed transaction. Test nhìn thấy dữ liệu vừa ghi vì nó đang đọc trong cùng transaction. Sau khi method kết thúc, Spring TestContext rollback transaction, nên node `Person` không được giữ lại trong database.

Assertion ở trên chỉ chứng minh thao tác đọc thấy thay đổi trong transaction hiện tại. Nó chưa chứng minh transaction đã commit hoặc một session khác có thể đọc dữ liệu.

## 3. Spring TestContext rollback mặc định

Khi test method hoặc test class được đánh dấu `@Transactional`, Spring TestContext mở test-managed transaction trước khi chạy method. Sau method, transaction được rollback mặc định.

Có thể diễn đạt rõ hành vi này bằng `@Rollback`:

```java
import org.junit.jupiter.api.Test;
import org.springframework.test.annotation.Rollback;
import org.springframework.transaction.annotation.Transactional;

@Test
@Transactional
@Rollback(true)
void changesAreRolledBackAfterTest() {
    repository.save(new Person("P-101", "Binh"));
}
```

`@Rollback(true)` là mặc định của test-managed transaction, nên không bắt buộc phải ghi annotation này. Viết tường minh có thể hữu ích khi tài liệu hóa ý định của test.

`@Commit` hoặc `@Rollback(false)` yêu cầu Spring commit test-managed transaction sau khi method kết thúc. Tuy nhiên, commit đó diễn ra trong quá trình kết thúc test, sau khi phần thân method đã chạy xong. Nếu cần đọc dữ liệu từ transaction mới ngay trong cùng test method sau commit, hãy dùng `TestTransaction` như phần sau.

## 4. Application transaction của service được commit khi nào?

Một service method có `@Transactional` thường bắt đầu transaction khi được gọi qua Spring proxy. Nếu không có transaction bên ngoài, proxy mở transaction mới và commit trước khi trả kết quả cho caller khi phương thức kết thúc bình thường. Nếu method tham gia transaction `REQUIRED` đã tồn tại, method chỉ kết thúc phần việc của nó; transaction bên ngoài vẫn quyết định thời điểm commit. Nếu runtime exception hoặc `Error` thoát khỏi transaction boundary, transaction được rollback theo mặc định.

Ví dụ entity và repository:

```java
import org.springframework.data.annotation.Version;
import org.springframework.data.neo4j.core.schema.Id;
import org.springframework.data.neo4j.core.schema.Node;

@Node("Person")
public class Person {

    @Id
    private String personId;

    @Version
    private Long version;

    private String name;

    protected Person() {
    }

    public Person(String personId, String name) {
        this.personId = personId;
        this.name = name;
    }

    public String getPersonId() {
        return personId;
    }

    public String getName() {
        return name;
    }
}
```

```java
import org.springframework.data.neo4j.repository.Neo4jRepository;

public interface PersonRepository extends Neo4jRepository<Person, String> {
}
```

`personId` là ID do ứng dụng cấp. `@Version Long` để `null` trên entity mới và được SDN quản lý khi lưu; nó hỗ trợ nhận diện entity mới cùng optimistic locking. Không tự gán version trong service.

Service tạo dữ liệu và một luồng cố ý phát sinh lỗi sau khi lưu:

```java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class PersonService {

    private final PersonRepository repository;

    public PersonService(PersonRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public Person create(String personId, String name) {
        return repository.save(new Person(personId, name));
    }

    @Transactional
    public void createThenFail(String personId) {
        repository.save(new Person(personId, "Rollback candidate"));
        throw new IllegalStateException("Simulated failure after save");
    }
}
```

Khi `create` được gọi qua Spring proxy và không có transaction bên ngoài, transaction của service commit trước khi caller nhận `Person`. Khi `createThenFail` ném `IllegalStateException`, exception thoát khỏi proxy nên transaction rollback, bao gồm thao tác `repository.save` đã tham gia transaction đó.

## 5. Kiểm tra commit thực tế bằng test không có @Transactional

Để xác nhận service transaction thực sự commit, không mở test-managed transaction bao quanh test method. Gọi service bean được Spring inject, chờ phương thức trả về rồi đọc lại bằng một repository call mới:

```java
import java.util.UUID;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest
class PersonCommitIntegrationTest {

    @Autowired
    private PersonService personService;

    @Autowired
    private PersonRepository personRepository;

    @Test
    void dataIsVisibleAfterServiceTransactionCommits() {
        String personId = "commit-" + UUID.randomUUID();

        try {
            Person saved = personService.create(personId, "An");

            assertThat(saved.getPersonId()).isEqualTo(personId);
            assertThat(personRepository.findById(personId))
                .get()
                .extracting(Person::getName)
                .isEqualTo("An");
        } finally {
            personRepository.deleteById(personId);
        }
    }
}
```

Test không có `@Transactional`, vì vậy lời gọi `personService.create` chạy transaction của ứng dụng và commit khi method kết thúc. Lệnh `findById` sau đó chạy ngoài transaction ghi, nên assertion kiểm tra dữ liệu đã commit.

ID ngẫu nhiên giúp các lần chạy không va chạm dữ liệu. `finally` xóa node để test không để lại dữ liệu; thao tác xóa cũng được repository quản lý transaction riêng.

Đảm bảo `personService` là bean Spring được inject. Nếu tự khởi tạo service bằng `new PersonService(...)`, lời gọi sẽ bỏ qua transaction proxy và test không còn kiểm tra đúng hành vi `@Transactional`.

## 6. Kiểm tra rollback thực tế của service

Rollback của service nên được kiểm tra theo cùng nguyên tắc: test không mở transaction bên ngoài, gọi service method, bắt exception ở phía caller, rồi đọc lại bằng một transaction mới.

```java
import java.util.UUID;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

@SpringBootTest
class PersonRollbackIntegrationTest {

    @Autowired
    private PersonService personService;

    @Autowired
    private PersonRepository personRepository;

    @Test
    void rollsBackWritesWhenRuntimeExceptionEscapesService() {
        String personId = "rollback-" + UUID.randomUUID();

        assertThatThrownBy(() -> personService.createThenFail(personId))
            .isInstanceOf(IllegalStateException.class);

        assertThat(personRepository.findById(personId)).isEmpty();
    }
}
```

Sau khi `createThenFail` ném exception, Spring transaction interceptor rollback transaction trước khi exception tới test. `findById` được gọi sau đó trong transaction đọc mới và xác nhận node không tồn tại.

Nếu test method cũng được đánh dấu `@Transactional`, service với propagation `REQUIRED` sẽ tham gia transaction của test. Khi đó, việc bắt exception rồi đọc ngay trong cùng transaction có thể vẫn thấy dữ liệu chưa commit; assertion đó không chứng minh trạng thái sau rollback. Hãy bỏ `@Transactional` khỏi test khi muốn kiểm tra ranh giới transaction thực tế của service.

## 7. Dùng TestTransaction để chủ động commit test-managed transaction

Đôi khi test cần transaction để chuẩn bị dữ liệu, nhưng vẫn muốn xác nhận trạng thái sau commit trong cùng method. Spring TestContext cung cấp `TestTransaction` cho việc kết thúc test-managed transaction một cách tường minh:

```java
import java.util.UUID;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.transaction.TestTransaction;
import org.springframework.transaction.annotation.Transactional;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest
class ExplicitCommitIntegrationTest {

    @Autowired
    private PersonService personService;

    @Autowired
    private PersonRepository personRepository;

    @Test
    @Transactional
    void canReadFromANewTransactionAfterExplicitCommit() {
        String personId = "explicit-commit-" + UUID.randomUUID();

        personService.create(personId, "Chi");

        TestTransaction.flagForCommit();
        TestTransaction.end();

        try {
            assertThat(personRepository.findById(personId)).isPresent();
        } finally {
            personRepository.deleteById(personId);
        }
    }
}
```

`TestTransaction.flagForCommit()` đổi kết quả kết thúc của test-managed transaction hiện tại. `TestTransaction.end()` kết thúc transaction ngay tại vị trí gọi và commit thay đổi. Sau đó, `findById` chạy trong transaction repository mới, không còn đọc dữ liệu từ transaction test vừa kết thúc.

Chỉ gọi `TestTransaction` khi Spring TestContext đã mở test-managed transaction. Nếu test không có transaction đang hoạt động, `TestTransaction.end()` không phải cách để commit application transaction và sẽ báo không có transaction phù hợp.

Vì test đã chủ động commit, rollback mặc định cuối test không thể hoàn tác dữ liệu đó. Hãy dùng ID riêng và dọn dữ liệu bằng `finally` hoặc cơ chế cleanup đáng tin cậy.

## 8. @Commit và @Rollback(false) không giống TestTransaction.end()

`@Commit` và `@Rollback(false)` cấu hình cách Spring TestContext kết thúc test-managed transaction sau khi test method hoàn tất:

```java
import org.junit.jupiter.api.Test;
import org.springframework.test.annotation.Commit;
import org.springframework.transaction.annotation.Transactional;

@Test
@Transactional
@Commit
void commitsChangesAfterTheTestMethod() {
    repository.save(new Person("P-200", "Dung"));
}
```

Trong ví dụ này, commit diễn ra sau khi thân method kết thúc. Không thể gọi `findById` ngay sau `save` rồi kết luận dữ liệu đã commit, vì lệnh đọc vẫn chạy trong test-managed transaction hiện tại.

Nếu cần đọc sau commit trong cùng test method, dùng `TestTransaction.flagForCommit()` rồi `TestTransaction.end()`. Nếu chỉ cần để dữ liệu được giữ lại sau khi test chạy, `@Commit` hoặc `@Rollback(false)` có thể phù hợp, nhưng phải tự quản lý dữ liệu còn lại giữa các lần chạy.

## 9. Rollback rules của @Transactional

Mặc định, Spring rollback transaction khi `RuntimeException` hoặc `Error` thoát khỏi phương thức transactional. Checked exception không kích hoạt rollback theo mặc định.

Ví dụ muốn rollback khi một checked exception được ném:

```java
import org.springframework.transaction.annotation.Transactional;

@Transactional(rollbackFor = BusinessRuleException.class)
public void createThenReject(String personId) throws BusinessRuleException {
    repository.save(new Person(personId, "Pending"));
    throw new BusinessRuleException("Business rule rejected the operation");
}
```

`BusinessRuleException` trong ví dụ là checked exception do ứng dụng định nghĩa, kế thừa `Exception`.

Nếu muốn chỉ định không rollback với một loại exception, Spring hỗ trợ `noRollbackFor`. Hãy tránh cấu hình này nếu thao tác ghi trước exception không thể được chấp nhận độc lập.

Exception phải thoát khỏi transaction interceptor để rollback rules được áp dụng. Nếu service bắt exception rồi trả về bình thường, transaction có thể commit. Nếu nghiệp vụ buộc phải bắt exception bên trong, có thể đánh dấu transaction rollback-only bằng API transaction phù hợp, nhưng nên cân nhắc thiết kế để lỗi được truyền ra ngoài ranh giới transaction.

## 10. Ảnh hưởng của propagation tới kết quả test

Propagation quyết định transaction method tham gia hoặc tạo mới như thế nào:

| Propagation | Hành vi trong test có test-managed transaction |
|---|---|
| `REQUIRED` | Tham gia transaction của test nếu đang tồn tại; thay đổi thường bị rollback cùng test |
| `REQUIRES_NEW` | Tạm treo transaction test và mở transaction độc lập; transaction mới có thể commit dù transaction test bên ngoài rollback |
| `MANDATORY` | Yêu cầu transaction hiện tại; lỗi nếu không có transaction |
| `SUPPORTS` | Tham gia transaction nếu có; nếu không thì chạy không transaction |
| `NOT_SUPPORTED` | Tạm treo transaction hiện tại và chạy ngoài transaction |

Một test dùng `@Transactional` không đảm bảo mọi ghi trong call graph đều được rollback. Nếu service method dùng `REQUIRES_NEW`, transaction độc lập của nó có thể commit và dữ liệu vẫn tồn tại sau khi test transaction bên ngoài rollback.

Khi kiểm thử `REQUIRES_NEW`, hãy đọc lại dữ liệu sau khi cả service transaction và test-managed transaction đã kết thúc. Cũng cần cleanup rõ ràng vì rollback của transaction ngoài không xóa thay đổi đã commit trong transaction mới.

## 11. Kiểm tra transaction có thực sự được mở qua Spring proxy

`@Transactional` hoạt động thông qua Spring AOP proxy trong cấu hình thông thường. Một số cách gọi có thể bỏ qua proxy:

- Tự tạo service bằng `new` thay vì lấy bean từ Spring context.
- Gọi một method transactional khác trên cùng instance bằng `this.otherMethod()` (self-invocation).
- Đặt annotation lên method không được proxy intercept theo loại proxy và visibility/configuration đang dùng.
- Gọi logic trước khi Spring khởi tạo bean hoặc sau khi bean đã bị đóng.

Trong integration test, inject service bean qua `@Autowired` hoặc constructor injection. Nếu một method cần transaction boundary riêng, đặt nó trên bean được gọi qua proxy hoặc tái cấu trúc thành một collaborator riêng; đừng dựa vào self-invocation.

## 12. Kiểm tra dữ liệu sau commit bằng session khác

Một lần đọc qua repository sau khi service method trả về thường tạo transaction mới. Nếu muốn kiểm tra ở mức driver, có thể mở session mới sau khi commit:

```java
import org.neo4j.driver.Driver;
import org.neo4j.driver.Session;
import org.neo4j.driver.SessionConfig;

public boolean existsInNewDriverSession(Driver driver, String personId) {
    try (Session session = driver.session(
            SessionConfig.builder()
                .withDatabase("neo4j")
                .build())) {

        return session.executeRead(tx ->
            tx.run("MATCH (p:Person {personId: $personId}) RETURN count(p) > 0 AS found",
                    java.util.Map.of("personId", personId))
                .single()
                .get("found")
                .asBoolean()
        );
    }
}
```

Đây là session độc lập, không đọc trạng thái chưa commit của transaction ghi. Trong cụm Neo4j, session này chỉ duy trì causal consistency nếu được khởi tạo với bookmark tương ứng, chẳng hạn bookmark mà ứng dụng thu thập từ cơ chế bookmark management của SDN. Dùng chung `Driver` không tự động chuyển bookmark của SDN sang session tạo trực tiếp bằng Driver API. Nếu mở driver/session độc lập không mang bookmark, một reader có thể chưa theo kịp replication; để test read-after-write trên cluster, hãy truyền bookmark phù hợp hoặc định tuyến kiểm tra tới writer.

Thông thường, repository read sau khi service transaction commit là đủ để kiểm tra hành vi ứng dụng. Chỉ dùng driver session riêng khi muốn xác minh rõ ranh giới kết nối hoặc tích hợp với thành phần ngoài SDN.

## 13. Test rollback không thay thế cleanup dữ liệu ngoài transaction

Rollback chỉ hoàn tác thay đổi thuộc transaction Neo4j đó. Các hành động ngoài transaction như gửi email, gọi HTTP service, ghi file hoặc publish message tới hệ thống không tham gia cùng transaction có thể vẫn xảy ra dù Neo4j rollback.

Trong test nghiệp vụ nhiều thành phần, hãy kiểm tra riêng các side effect ngoài database. Nếu cần tính nguyên tử giữa Neo4j và message broker, một transaction Neo4j đơn lẻ không tạo ra distributed transaction tự động; cần thiết kế outbox hoặc cơ chế phối hợp phù hợp.

Đối với dữ liệu test đã commit, dùng một trong các cách cleanup:

- Xóa theo ID duy nhất sau khi assertion hoàn tất.
- Dùng database/schema cô lập cho mỗi test suite hoặc mỗi test run.
- Tạo fixture có namespace riêng và xóa toàn bộ fixture theo namespace sau test.

Không dựa vào rollback test-managed transaction để dọn dữ liệu đã được ghi bởi `REQUIRES_NEW`, session độc lập hoặc thao tác Cypher chạy ngoài transaction đó.

## 14. Lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Test thấy node sau `save`, nhưng node biến mất sau test | Test-managed transaction rollback mặc định | Phân biệt assertion trong transaction với kiểm tra sau commit. |
| Test bắt exception nhưng vẫn đọc thấy node | Exception được bắt trong test-managed transaction; dữ liệu chưa rollback cho tới khi transaction kết thúc | Kiểm tra từ test không có `@Transactional` sau khi service proxy rollback. |
| Test tưởng service đã commit khi method trả về | Service tham gia transaction ngoài của test theo `REQUIRED` | Chạy test không có test-managed transaction hoặc kết thúc transaction bằng `TestTransaction`. |
| Test rollback nhưng dữ liệu vẫn tồn tại | Service dùng `REQUIRES_NEW` hoặc ghi qua session riêng đã commit | Kiểm tra propagation và cleanup transaction độc lập. |
| Checked exception không rollback | Spring mặc định rollback với unchecked exception và `Error` | Dùng `rollbackFor` cho checked exception cần rollback. |
| Runtime exception bị bắt trong service nhưng dữ liệu vẫn commit | Exception không thoát khỏi transaction interceptor | Ném lại exception hoặc đánh dấu transaction rollback-only. |
| `@Transactional` không có tác dụng trong test | Service được tạo bằng `new` hoặc self-invocation bỏ qua proxy | Dùng Spring-managed bean và gọi qua proxy. |
| Dữ liệu test đã commit làm test sau thất bại | Dùng `@Commit`, `@Rollback(false)` hoặc `TestTransaction.end()` mà không cleanup | Dùng ID riêng và cleanup trong `finally`. |
| Session mới trên cluster đọc dữ liệu cũ | Session không có causal bookmark và reader chưa theo kịp | Truyền bookmark hoặc đọc từ writer trong kiểm tra read-after-write. |

## 15. Quy trình kiểm thử rollback và commit

1. Xác nhận test đang dùng Neo4j thật hoặc môi trường integration có transaction semantics tương đương; mock repository không chứng minh được rollback của database.
2. Xác định test method có `@Transactional` hay meta-annotation mở test-managed transaction hay không.
3. Kiểm tra propagation của service method, đặc biệt `REQUIRED` và `REQUIRES_NEW`.
4. Để kiểm tra service commit/rollback, ưu tiên test method không có test-managed transaction.
5. Gọi service bean được Spring inject để transaction proxy thực sự chạy.
6. Với rollback, để runtime exception thoát khỏi service proxy rồi đọc lại bằng repository call mới.
7. Với commit, gọi service method thành công rồi đọc lại bằng repository call mới sau khi method trả về.
8. Nếu cần test-managed transaction, dùng `TestTransaction.flagForCommit()` và `TestTransaction.end()` trước khi kiểm tra từ transaction mới.
9. Kiểm tra rollback rules cho checked exception và exception bị bắt bên trong service.
10. Dùng ID duy nhất, cleanup mọi dữ liệu đã commit và xác nhận side effect ngoài database riêng biệt.
11. Nếu kiểm tra qua session độc lập trong cluster, bảo đảm causal bookmark hoặc đọc từ writer.

## 16. Ghi nhớ

Test-managed transaction của Spring TestContext thường rollback sau mỗi test method; nó có thể làm test đọc được dữ liệu vừa ghi nhưng không để dữ liệu tồn tại sau test. Application transaction của service có `@Transactional` commit khi phương thức trả về bình thường và rollback theo rollback rules khi exception phù hợp thoát khỏi transaction boundary.

Muốn xác nhận kết quả sau commit thực tế, hãy chạy test không có `@Transactional` ở cấp test, gọi service bean qua Spring proxy rồi đọc lại bằng repository trong transaction mới. Muốn chủ động kết thúc test-managed transaction ngay trong test, dùng `TestTransaction.flagForCommit()` và `TestTransaction.end()` rồi mới đọc lại. Chú ý `REQUIRES_NEW`, checked exception, self-invocation và dữ liệu đã commit cần cleanup; rollback của test không thể hoàn tác transaction độc lập hoặc side effect bên ngoài Neo4j.

## Tài liệu tham khảo

- [Spring Framework – TestContext Transaction Management](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/tx.html)
- [Spring Framework – Declarative Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative.html)
- [Spring Framework – Transaction Propagation](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-propagation.html)
- [Spring Data Neo4j – Transactions](https://docs.spring.io/spring-data/neo4j/reference/transactions.html)
- [Neo4j Java Driver – Transactions](https://neo4j.com/docs/java-manual/current/transactions/)
