# Kiểm thử độc lập fragment và kết hợp với repository sinh tự động

## Mục tiêu bài học

Sau bài này, bạn có thể:

- Phân biệt kiểm thử logic của một repository fragment với kiểm thử proxy repository đã được Spring Data lắp ghép.
- Tạo fragment interface và implementation theo quy ước phát hiện của Spring Data Neo4j (SDN).
- Kiểm thử trực tiếp implementation bằng cách cấp các dependency cần thiết, không cần gọi qua repository proxy.
- Dùng `@DataNeo4jTest` để kiểm tra Cypher của fragment trên Neo4j test database.
- Xác minh một repository proxy cung cấp đồng thời CRUD, derived query và phương thức từ custom fragment.
- Chẩn đoán lỗi do sai tên implementation, sai package scan hoặc cấu hình test slice thiếu dependency.

## 1. Vì sao cần kiểm thử fragment ở hai mức?

Repository của Spring Data Neo4j có thể được tạo từ nhiều phần (fragment). Một repository thường kết hợp:

- Implementation nền cung cấp CRUD như `findById()`, `save()` và `deleteById()`.
- Các query method được Spring Data sinh từ tên phương thức.
- Các fragment tùy chỉnh do ứng dụng cung cấp.
- Các extension khác được bật trong repository.

Khi repository interface kế thừa một fragment interface, Spring Data ghép implementation của fragment vào proxy repository. Người dùng repository gọi các phương thức trên cùng một bean, dù chúng đến từ nhiều implementation khác nhau.

Vì vậy, cần kiểm tra hai câu hỏi riêng:

1. **Fragment có hoạt động đúng khi được gọi trực tiếp không?** Kiểm tra logic và Cypher của implementation mà chưa phụ thuộc vào việc Spring ghép repository proxy.
2. **Repository proxy có lắp ghép đúng không?** Kiểm tra các phương thức CRUD, derived query và fragment cùng xuất hiện trên một repository bean.

Nếu chỉ kiểm tra fragment trực tiếp, bạn chưa biết Spring có phát hiện đúng implementation hay không. Nếu chỉ kiểm tra repository proxy, khi có lỗi bạn khó xác định lỗi nằm trong logic fragment hay trong bước cấu hình và lắp ghép repository.

## 2. Quy ước fragment interface và implementation

Giả sử ứng dụng cần tìm người theo kỹ năng. Spring Data cho phép tách chức năng này thành một fragment riêng:

```java
import java.util.Collection;

public interface PersonSearchFragment {

    Collection<PersonSearchResult> findBySkill(String skill);
}
```

Kiểu kết quả của truy vấn:

```java
public record PersonSearchResult(String id, String name) {
}
```

Implementation có tên theo quy ước mặc định: tên fragment interface cộng hậu tố `Impl`.

```java
import java.util.Collection;

import org.springframework.data.neo4j.core.Neo4jClient;

public class PersonSearchFragmentImpl implements PersonSearchFragment {

    private final Neo4jClient neo4jClient;

    public PersonSearchFragmentImpl(Neo4jClient neo4jClient) {
        this.neo4jClient = neo4jClient;
    }

    @Override
    public Collection<PersonSearchResult> findBySkill(String skill) {
        return neo4jClient
            .query("""
                MATCH (p:Person)
                WHERE $skill IN p.skills
                RETURN p.id AS id, p.name AS name
                ORDER BY p.name, p.id
                """)
            .bind(skill).to("skill")
            .fetchAs(PersonSearchResult.class)
            .mappedBy((typeSystem, record) ->
                new PersonSearchResult(
                    record.get("id").asString(),
                    record.get("name").asString()
                )
            )
            .all();
    }
}
```

Một số quy tắc cần nhớ:

- Tên mặc định là `PersonSearchFragmentImpl`, không phải `PersonRepositoryImpl`.
- Implementation cần nằm trong package được repository infrastructure quét, thường là cùng package hoặc package con bên dưới package chứa repository.
- Hậu tố mặc định là `Impl`; có thể đổi bằng `repositoryImplementationPostfix` trong `@EnableNeo4jRepositories`.
- Implementation có thể là một Spring bean thông thường với constructor injection. Không cần tự tạo repository proxy bên trong fragment.
- `Neo4jClient` tích hợp với transaction management của Spring, nên truy vấn trong fragment có thể tham gia transaction đang hoạt động.

Cách đặt tên implementation theo repository interface, chẳng hạn `PersonRepositoryImpl`, là kiểu custom implementation lịch sử. Spring Data hiện khuyến nghị mô hình fragment-based và xem cách đặt tên cũ là deprecated.

## 3. Entity và repository sẽ kết hợp với fragment

Entity dùng trong ví dụ:

```java
import java.util.List;

import org.springframework.data.neo4j.core.schema.Id;
import org.springframework.data.neo4j.core.schema.Node;

@Node("Person")
public class Person {

    @Id
    private String id;

    private String name;

    private List<String> skills;

    protected Person() {
    }

    public Person(String id, String name, List<String> skills) {
        this.id = id;
        this.name = name;
        this.skills = skills;
    }

    public String getId() {
        return id;
    }

    public String getName() {
        return name;
    }

    public List<String> getSkills() {
        return skills;
    }
}
```

Repository kế thừa cả repository nền và fragment:

```java
import java.util.List;

import org.springframework.data.neo4j.repository.Neo4jRepository;

public interface PersonRepository
        extends Neo4jRepository<Person, String>,
                PersonSearchFragment {

    List<Person> findByName(String name);
}
```

Repository này có ba nhóm chức năng:

| Phương thức | Nguồn implementation |
| --- | --- |
| `findById()`, `save()`, `existsById()` | Repository nền `Neo4jRepository` |
| `findByName()` | Derived query do Spring Data tạo |
| `findBySkill()` | `PersonSearchFragmentImpl` |

Khi ứng dụng inject `PersonRepository`, Spring trả về một proxy có các chức năng đã ghép. Service không cần biết phương thức nào được thực hiện bởi repository nền và phương thức nào được thực hiện bởi fragment.

## 4. Kiểm thử implementation fragment trực tiếp

Để kiểm tra riêng implementation, có thể tạo instance trực tiếp bằng constructor và truyền vào một `Neo4jClient` đã được cấu hình cho test. Cách này không gọi phương thức qua `PersonRepository` proxy, do đó giúp xác định fragment có thực thi đúng Cypher và ánh xạ kết quả hay không.

Với ứng dụng dùng Spring Boot, `@DataNeo4jTest` cung cấp hạ tầng test slice như transaction manager, `Neo4jClient`, `Neo4jTemplate` và repository được khai báo. Test slice này không tự khởi động Neo4j database; cần cấu hình kết nối tới Neo4j Testcontainers hoặc Neo4j test harness.

Ví dụ sau giả định test environment đã cấu hình kết nối Neo4j. Import của `@DataNeo4jTest` phụ thuộc phiên bản Spring Boot: Boot 3 dùng package `org.springframework.boot.test.autoconfigure.data.neo4j`; Boot 4 chuyển annotation sang package `org.springframework.boot.data.neo4j.test.autoconfigure`.

```java
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.data.neo4j.DataNeo4jTest;
import org.springframework.data.neo4j.core.Neo4jClient;

@DataNeo4jTest
class PersonSearchFragmentImplTest {

    @Autowired
    Neo4jClient neo4jClient;

    private PersonSearchFragmentImpl fragment;

    @BeforeEach
    void setUp() {
        fragment = new PersonSearchFragmentImpl(neo4jClient);

        neo4jClient.query("MATCH (p:Person) DETACH DELETE p").run();

        neo4jClient.query("""
            CREATE
              (:Person {
                  id: 'p-1',
                  name: 'An',
                  skills: ['Java', 'Neo4j']
              }),
              (:Person {
                  id: 'p-2',
                  name: 'Binh',
                  skills: ['Java']
              })
            """).run();
    }

    @Test
    void findsPeopleWithRequestedSkill() {
        var result = fragment.findBySkill("Neo4j");

        assertThat(result)
            .containsExactly(new PersonSearchResult("p-1", "An"));
    }
}
```

Trong test này:

- Fragment được tạo trực tiếp bằng `new PersonSearchFragmentImpl(neo4jClient)`.
- Test gọi `fragment.findBySkill()`, không gọi qua `PersonRepository`.
- Dữ liệu mẫu có hai người nhưng chỉ một người có kỹ năng `Neo4j`.
- Assertion xác nhận điều kiện Cypher, tham số `$skill` và mapping record sang `PersonSearchResult` cùng hoạt động đúng.

Đây là kiểm thử fragment ở mức component/integration với Neo4j test database, không phải unit test thuần túy. Nếu fragment có phần logic thuần Java như chuẩn hóa đầu vào, tính toán hoặc chuyển đổi dữ liệu, hãy tách phần đó thành hàm hoặc collaborator độc lập để kiểm thử bằng JUnit và Mockito mà không cần khởi động database.

Không nên mock toàn bộ chuỗi fluent của `Neo4jClient` chỉ để xác nhận Cypher chạy đúng. Mock có thể xác nhận cách gọi API, nhưng không xác nhận cú pháp Cypher, tên property, kiểu dữ liệu hoặc kết quả truy vấn thực tế.

## 5. Kiểm thử repository proxy sau khi lắp ghép

Sau khi kiểm tra fragment trực tiếp, cần xác minh Spring Data đã ghép implementation vào repository proxy. Bài kiểm thử tiếp theo inject `PersonRepository` và gọi cả phương thức do Spring Data tạo lẫn phương thức của fragment.

```java
import static org.assertj.core.api.Assertions.assertThat;

import java.util.List;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.data.neo4j.DataNeo4jTest;
import org.springframework.data.neo4j.core.Neo4jClient;

@DataNeo4jTest
class PersonRepositoryCompositionTest {

    @Autowired
    PersonRepository personRepository;

    @Autowired
    Neo4jClient neo4jClient;

    @BeforeEach
    void setUp() {
        neo4jClient.query("MATCH (p:Person) DETACH DELETE p").run();

        personRepository.save(
            new Person("p-1", "An", List.of("Java", "Neo4j"))
        );
        personRepository.save(
            new Person("p-2", "Binh", List.of("Java"))
        );
    }

    @Test
    void combinesGeneratedMethodsAndCustomFragment() {
        assertThat(personRepository.existsById("p-1")).isTrue();

        assertThat(personRepository.findByName("An"))
            .extracting(Person::getId)
            .containsExactly("p-1");

        assertThat(personRepository.findBySkill("Neo4j"))
            .containsExactly(new PersonSearchResult("p-1", "An"));
    }
}
```

Test này xác minh ba đường gọi khác nhau trên cùng một bean:

1. `existsById()` đến từ repository nền.
2. `findByName()` được Spring Data tạo thành derived query.
3. `findBySkill()` được chuyển đến `PersonSearchFragmentImpl`.

Nếu fragment không được phát hiện, repository có thể không khởi tạo được hoặc không cung cấp phương thức fragment. Nếu derived query không hoạt động, vấn đề nằm ở tên property hoặc mapping domain. Nếu CRUD không hoạt động, cần kiểm tra entity mapping và cấu hình Neo4j. Tách các assertion như trên giúp khoanh vùng lỗi nhanh hơn.

## 6. Test slice @DataNeo4jTest và cấu hình Neo4j

`@DataNeo4jTest` tập trung vào các thành phần Neo4j: entity, repository, client, template và transaction infrastructure. Annotation này không nạp tất cả `@Component` hoặc cấu hình ứng dụng như một `@SpringBootTest` đầy đủ.

Một số đặc điểm cần nhớ:

- Test slice không tự cung cấp database. Cần cấu hình URI, thông tin xác thực và một test database phù hợp.
- Spring Data Neo4j khuyến nghị dùng Testcontainers Neo4j hoặc Neo4j test harness.
- Test slice có transaction imperative và mặc định các test imperative được rollback khi kết thúc.
- Nếu cần kiểm tra hành vi reactive, không dựa vào transaction mặc định của test slice như thể nó là reactive transaction. Hãy dùng `TransactionalOperator` hoặc cấu hình transaction phù hợp.
- Nếu fragment implementation phụ thuộc vào một bean ứng dụng bình thường mà test slice không quét, hãy import bean đó bằng `@Import` hoặc cung cấp test configuration riêng.

Ví dụ cấu hình dependency test với Spring Boot dependency management:

```gradle
dependencies {
    testImplementation("org.springframework.boot:spring-boot-starter-test")
    testImplementation("org.testcontainers:testcontainers-neo4j")
}
```

Testcontainers cần Docker hoặc runtime container tương thích. Nếu môi trường đã có Neo4j test harness, có thể dùng test harness thay thế. Không nên chạy test trên database phát triển dùng chung vì các lệnh seed và cleanup có thể làm thay đổi dữ liệu của người khác.

## 7. Kiểm tra thứ tự và xung đột giữa nhiều fragment

Một repository có thể kết hợp nhiều fragment:

```java
public interface PersonSearchFragment {
    Collection<PersonSearchResult> findBySkill(String skill);
}

public interface PersonExportFragment {
    List<PersonExportRow> exportByDepartment(String departmentCode);
}

public interface PersonRepository
        extends Neo4jRepository<Person, String>,
                PersonSearchFragment,
                PersonExportFragment {

    List<Person> findByName(String name);
}
```

Mỗi fragment có implementation tương ứng:

- `PersonSearchFragmentImpl`
- `PersonExportFragmentImpl`

Spring Data ghép các fragment theo thứ tự khai báo trong repository interface. Custom fragment có độ ưu tiên cao hơn implementation nền và repository aspects. Điều này cho phép fragment tùy chỉnh một phương thức có cùng chữ ký với phương thức nền, nhưng cũng có thể tạo ra kết quả bất ngờ nếu hai fragment cùng khai báo một method signature.

Khi có nhiều fragment, hãy kiểm tra:

- Mỗi fragment interface có một implementation được phát hiện đúng.
- Các method signature không xung đột ngoài chủ ý.
- Nếu cố ý override method nền, test xác nhận implementation nào được gọi.
- Các repository dùng chung fragment đều có thể inject các dependency của fragment.
- Các fragment không phụ thuộc vòng lặp vào repository proxy đang chứa chính chúng.

Để giảm mơ hồ, nên đặt tên method theo nghiệp vụ cụ thể thay vì ghi đè CRUD khi không cần thiết.

## 8. Phân biệt lỗi fragment với lỗi repository composition

Bảng sau giúp khoanh vùng lỗi:

| Triệu chứng | Vùng cần kiểm tra |
| --- | --- |
| Tạo trực tiếp fragment và gọi method vẫn lỗi | Cypher, binding, mapping kết quả hoặc logic trong implementation |
| Fragment trực tiếp chạy được nhưng repository không khởi tạo | Tên implementation, package scan, constructor dependency hoặc fragment interface |
| Repository khởi tạo được nhưng method fragment không tìm thấy | Repository chưa kế thừa đúng fragment interface hoặc method chưa được khai báo |
| CRUD chạy nhưng derived query lỗi | Tên property, kiểu dữ liệu hoặc query derivation |
| Derived query chạy nhưng fragment trả kết quả sai | Cypher tùy chỉnh, tham số và mapping record |
| Test slice không tạo được bean phụ thuộc | Bean không nằm trong phạm vi component scan của `@DataNeo4jTest`; cân nhắc `@Import` |
| Test pass riêng lẻ nhưng thất bại khi chạy cả suite | Dữ liệu test không được cô lập, transaction không rollback hoặc test dùng chung database |

Nếu Spring không tìm thấy implementation, kiểm tra tên class theo dạng `<FragmentInterfaceName>Impl`, package của repository và cấu hình `repositoryImplementationPostfix`. Không tạo một lớp `<RepositoryName>Impl` theo quy ước cũ để chữa lỗi phát hiện fragment; hãy sửa đúng cấu trúc fragment.

## 9. Kiểm thử fragment có transaction và dữ liệu phụ thuộc

Fragment có thể sử dụng `Neo4jClient`, `Neo4jTemplate` hoặc một collaborator khác. Khi truy vấn chạy qua `Neo4jClient`, client tham gia transaction Spring nếu dùng cùng cấu hình driver và transaction manager của ứng dụng.

Trong test slice imperative:

- Dữ liệu được tạo trong `@BeforeEach` thường nằm trong transaction test.
- Truy vấn của fragment tham gia cùng transaction đó.
- Khi test kết thúc, transaction được rollback theo mặc định.
- Không cần xóa dữ liệu bằng lệnh cleanup ở cuối mỗi test nếu transaction rollback đang hoạt động và mọi thao tác đều tham gia transaction đó.

Nếu test chủ động mở session hoặc transaction riêng, dùng reactive client, hoặc tắt transaction test, cần quản lý cleanup rõ ràng. Không giả định mọi thao tác database đều tự rollback chỉ vì class có `@DataNeo4jTest`.

Với fragment thực hiện nhiều thao tác ghi, nên kiểm tra cả trường hợp thành công và rollback khi một bước sau thất bại. Có thể đặt nghiệp vụ trong service có `@Transactional` để ranh giới transaction rõ ràng, còn fragment đảm nhiệm thao tác dữ liệu chuyên biệt.

## 10. Quy trình thiết kế và kiểm thử thực tế

Một quy trình hiệu quả cho repository customization:

1. Xác định chức năng không phù hợp với derived query hoặc `@Query` thông thường.
2. Tạo fragment interface chỉ khai báo các method thuộc chức năng đó.
3. Viết implementation có hậu tố `Impl`, constructor inject dependency cần thiết.
4. Kiểm thử trực tiếp fragment: kiểm tra logic Java riêng và kiểm tra Cypher với Neo4j test database.
5. Cho repository interface kế thừa cả repository nền và fragment interface.
6. Kiểm thử repository proxy để xác nhận CRUD, derived query và fragment method cùng hoạt động.
7. Nếu có nhiều fragment, kiểm tra method signature và thứ tự ưu tiên.
8. Chạy test trong database cô lập, tránh dữ liệu dùng chung.
9. Khi nâng cấp Spring Data, kiểm tra lại package annotation test và quy ước discovery theo phiên bản Spring Boot/SDN đang dùng.

Hãy giữ test fragment và test composition thành hai nhóm rõ ràng. Khi một test thất bại, nhóm test sẽ cho biết lỗi nằm trong implementation hay trong quá trình Spring lắp ghép repository.

## 11. Những lỗi thường gặp

| Lỗi | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Implementation tên `PersonRepositoryImpl` | Dùng quy ước custom implementation cũ | Đặt theo tên fragment, ví dụ `PersonSearchFragmentImpl` |
| Fragment implementation nằm ngoài package được quét | Repository infrastructure không phát hiện class | Đưa class vào package cùng hoặc bên dưới package repository, hoặc cấu hình discovery phù hợp |
| Repository không kế thừa fragment interface | Proxy không có method fragment | Thêm fragment interface vào `extends` |
| Dùng `@DataNeo4jTest` nhưng không có database | Test slice không tự khởi động Neo4j | Cấu hình Testcontainers hoặc test harness |
| Test fragment chỉ mock repository proxy | Không kiểm tra Cypher trong implementation | Gọi trực tiếp fragment implementation và kiểm tra với test database |
| Chỉ test fragment trực tiếp | Không biết proxy có lắp ghép đúng không | Thêm test inject repository và gọi cả method nền lẫn fragment |
| Test dùng database chung | Dữ liệu test ảnh hưởng lẫn nhau | Dùng database/container riêng và transaction rollback |
| Test reactive dựa vào rollback imperative | Chọn sai transaction manager | Dùng `TransactionalOperator` hoặc cấu hình reactive transaction |
| Nhiều fragment khai báo cùng method | Method resolution phụ thuộc thứ tự composition | Tránh trùng chữ ký hoặc viết test xác nhận thứ tự ưu tiên |

## 12. Câu hỏi tự kiểm tra

1. Repository fragment gồm những thành phần nào?
2. Vì sao implementation của `PersonSearchFragment` mặc định có tên `PersonSearchFragmentImpl`?
3. Kiểm thử trực tiếp fragment khác gì với kiểm thử qua `PersonRepository` proxy?
4. Vì sao cần một test xác nhận CRUD, derived query và fragment method cùng hoạt động?
5. `@DataNeo4jTest` cung cấp những hạ tầng nào và không cung cấp điều gì?
6. Vì sao nên dùng Neo4j Testcontainers hoặc test harness thay cho database phát triển dùng chung?
7. Khi test slice không tải một bean phụ thuộc của fragment, có thể xử lý thế nào?
8. Spring Data giải quyết thứ tự khi nhiều fragment có method trùng chữ ký ra sao?
9. Vì sao không nên quay lại quy ước implementation `PersonRepositoryImpl`?
10. Khi dùng reactive repository, vì sao phải kiểm tra transaction test riêng?

## Tài liệu tham khảo

- [Spring Data Neo4j 8.1 – Custom Repository Implementations](https://docs.spring.io/spring-data/neo4j/reference/repositories/custom-implementations.html)
- [Spring Data Neo4j – Testing with Spring Boot and @DataNeo4jTest](https://docs.spring.io/spring-data/neo4j/reference/testing/testing-with-spring-boot.html)
- [Spring Data Commons – Custom Repository Implementations](https://docs.spring.io/spring-data/commons/reference/repositories/custom-implementations.html)
- [Spring Boot – Auto-configured Data Neo4j Tests](https://docs.spring.io/spring-boot/reference/testing/spring-boot-applications.html)

## Kết luận

Kiểm thử repository customization cần xác nhận cả implementation fragment lẫn repository proxy đã được Spring Data lắp ghép. Gọi trực tiếp fragment giúp kiểm tra Cypher, tham số và mapping mà không phụ thuộc vào proxy. Kiểm thử qua repository giúp xác nhận CRUD, derived query và method tùy chỉnh cùng hoạt động trên một bean.

Dùng `<FragmentName>Impl` theo quy ước discovery, đặt implementation trong phạm vi package repository được quét và cấu hình Neo4j test database riêng. Với `@DataNeo4jTest`, hãy nhớ test slice cung cấp hạ tầng Spring Data Neo4j nhưng không tự khởi động database; các test imperative mặc định rollback transaction khi kết thúc. Hai nhóm kiểm thử rõ ràng sẽ giúp phát hiện nhanh lỗi trong Cypher, mapping, dependency injection hoặc quá trình ghép repository.
