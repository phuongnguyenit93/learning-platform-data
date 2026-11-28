# Quy ước tên, phát hiện fragment và ghép giao diện

Spring Data Neo4j (SDN) cho phép mở rộng repository bằng các fragment: những interface nhỏ mô tả một nhóm hành vi riêng và lớp triển khai tương ứng. Spring Data phát hiện implementation theo quy ước tên, sau đó ghép fragment vào repository proxy. Nhờ vậy, repository có thể kết hợp CRUD có sẵn với các thao tác truy vấn hoặc xử lý dữ liệu đặc thù.

Để cơ chế này hoạt động ổn định, cần hiểu ba việc: tên implementation được suy ra từ tên fragment interface, package phải nằm trong phạm vi phát hiện của repository infrastructure, và repository interface phải kế thừa fragment muốn sử dụng. Một class có tên gần giống nhưng không đúng quy ước sẽ không tự động được ghép vào repository.

## 1. Repository fragment là gì?

Một repository thường kế thừa base interface của Spring Data Neo4j:

~~~java
public interface PersonRepository extends Neo4jRepository<Person, String> {
}
~~~

`Neo4jRepository` cung cấp các thao tác dữ liệu cơ bản. Khi cần thêm một khả năng riêng, ví dụ tìm kiếm theo prefix hoặc chạy một truy vấn đồ thị chuyên biệt, có thể khai báo fragment interface:

~~~java
import java.util.Collection;

public interface PersonSearch {
    Collection<PersonSummary> searchByNamePrefix(String prefix);
}
~~~

Fragment interface chỉ mô tả hợp đồng. Nó không cần kế thừa `Neo4jRepository`, cũng không cần tự tạo proxy. Spring Data sẽ ghép implementation của fragment vào repository chính khi phát hiện cấu trúc đúng.

Một repository có thể kết hợp nhiều fragment, mỗi fragment phụ trách một nhóm hành vi có ranh giới rõ ràng: tìm kiếm, thống kê, bulk update hoặc một tích hợp đặc thù.

## 2. Quy ước tên implementation mặc định

Theo mặc định, Spring Data dùng hậu tố `Impl` để tìm lớp triển khai của fragment. Tên lớp được tạo bằng cách nối tên fragment interface với hậu tố này:

| Fragment interface | Implementation mặc định |
| --- | --- |
| `PersonSearch` | `PersonSearchImpl` |
| `PersonStatistics` | `PersonStatisticsImpl` |
| `AuditOperations` | `AuditOperationsImpl` |

Ví dụ implementation của `PersonSearch`:

~~~java
import java.util.Collection;

import org.springframework.data.neo4j.core.Neo4jClient;

public class PersonSearchImpl implements PersonSearch {

    private final Neo4jClient neo4jClient;

    public PersonSearchImpl(Neo4jClient neo4jClient) {
        this.neo4jClient = neo4jClient;
    }

    @Override
    public Collection<PersonSummary> searchByNamePrefix(String prefix) {
        return neo4jClient.query("""
                MATCH (person:Person)
                WHERE person.name STARTS WITH $prefix
                RETURN person.id AS id, person.name AS name
                ORDER BY person.name, person.id
                """)
            .bind(prefix).to("prefix")
            .fetchAs(PersonSummary.class)
            .mappedBy((typeSystem, record) -> new PersonSummary(
                record.get("id").asString(),
                record.get("name").asString()
            ))
            .all();
    }
}
~~~

Ở đây, `PersonSearchImpl` phải khớp chính xác với `PersonSearch` cộng hậu tố `Impl`. Spring Data phát hiện implementation và đưa nó vào repository composition. Constructor injection cho phép implementation dùng `Neo4jClient`, `Neo4jTemplate` hoặc các bean Spring khác.

Ví dụ dùng DTO record:

~~~java
public record PersonSummary(String id, String name) {}
~~~

Với custom fragment, không bắt buộc implementation phải chỉ dùng repository abstraction. Fragment có thể dùng `Neo4jClient` cho Cypher tùy chỉnh hoặc `Neo4jTemplate` khi cần các thao tác mapping của SDN.

## 3. Package và phạm vi phát hiện

Để tránh lỗi phát hiện implementation, hãy đặt fragment interface và lớp implementation trong package của repository hoặc trong package con nằm trong phạm vi cấu hình repository. Ví dụ:

~~~text
com.example.people.repository
    PersonRepository.java
    PersonSearch.java
    PersonSearchImpl.java
    PersonSummary.java
~~~

Khi repository nằm trong `com.example.people.repository`, đặt fragment và implementation cùng package là cách đơn giản, dễ kiểm tra nhất. Nếu chia package theo module, hãy bảo đảm package implementation được bao phủ bởi phạm vi scan mà Spring Data sử dụng.

Spring Boot thường phát hiện repository từ package của lớp cấu hình ứng dụng chính. Nếu repository nằm ngoài phạm vi mặc định, có thể cấu hình `@EnableNeo4jRepositories` với `basePackages` hoặc `basePackageClasses` phù hợp. Không nên khai báo scan rộng toàn bộ project nếu không cần thiết vì có thể phát hiện nhầm repository hoặc implementation.

## 4. Ghép fragment vào repository interface

Repository chính phải kế thừa fragment interface. Chỉ có class `PersonSearchImpl` trong package là chưa đủ nếu `PersonRepository` không mở rộng `PersonSearch`.

~~~java
import org.springframework.data.neo4j.repository.Neo4jRepository;

public interface PersonRepository extends
        Neo4jRepository<Person, String>,
        PersonSearch {
}
~~~

Spring Data tạo repository proxy từ các thành phần đã ghép:

~~~mermaid
flowchart TD
    A["PersonRepository"] --> B["Neo4jRepository base implementation"]
    A --> C["PersonSearch fragment"]
    C --> D["PersonSearchImpl"]
    B --> E["Repository proxy được ghép"]
    D --> E
~~~

Caller chỉ cần inject `PersonRepository`; có thể gọi cả method CRUD và method của fragment:

~~~java
Person person = personRepository.findById(personId).orElseThrow();
Collection<PersonSummary> matches =
    personRepository.searchByNamePrefix("An");
~~~

Nếu repository kết hợp nhiều fragment, mỗi interface bổ sung một nhóm method:

~~~java
public interface PersonStatistics {
    long countByStatus(String status);
}

public interface PersonRepository extends
        Neo4jRepository<Person, String>,
        PersonSearch,
        PersonStatistics {
}
~~~

Implementation tương ứng là `PersonSearchImpl` và `PersonStatisticsImpl`. Spring Data phát hiện từng fragment độc lập rồi ghép cả hai vào repository.

## 5. Tùy chỉnh hậu tố implementation

Nếu dự án cần một hậu tố khác, có thể cấu hình `repositoryImplementationPostfix` trên `@EnableNeo4jRepositories`. Ví dụ dùng hậu tố `Custom`:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.data.neo4j.repository.config.EnableNeo4jRepositories;

@Configuration
@EnableNeo4jRepositories(
    basePackages = "com.example.people.repository",
    repositoryImplementationPostfix = "Custom"
)
public class Neo4jRepositoryConfiguration {
}
~~~

Với cấu hình này, implementation của `PersonSearch` cần tên `PersonSearchCustom`. Hậu tố phải thống nhất với cách đặt tên của các fragment implementation trong phạm vi repository configuration đó.

Chỉ đổi hậu tố khi có lý do rõ ràng, chẳng hạn quy ước chung của codebase hoặc tránh trùng tên với một class khác. Nếu đổi cấu hình nhưng quên đổi tên implementation, fragment sẽ không được phát hiện và repository có thể khởi tạo lỗi khi method tùy chỉnh được yêu cầu.

## 6. Phân biệt fragment implementation với tên RepositoryImpl cũ

Một quy ước cũ là tạo class tên `PersonRepositoryImpl` để triển khai tùy chỉnh cho `PersonRepository`. Cách này gắn implementation trực tiếp với tên repository interface, khiến việc chia nhiều hành vi tùy chỉnh và tái sử dụng giữa các repository khó rõ ràng hơn.

Cách tiếp cận fragment hiện đại gắn implementation với tên fragment interface:

| Cách tổ chức | Tên implementation | Đặc điểm |
| --- | --- | --- |
| Fragment-based | `PersonSearchImpl` | Mỗi fragment có hợp đồng và implementation riêng; có thể ghép vào repository |
| Repository-named implementation kiểu cũ | `PersonRepositoryImpl` | Gắn custom implementation vào một repository cụ thể; khó phân tách nhiều hành vi |

Ưu tiên fragment-based khi thêm chức năng mới. Chỉ giữ kiểu repository-named implementation khi đang bảo trì code cũ và đã xác nhận cơ chế phát hiện tương ứng của phiên bản Spring Data đang dùng. Tránh tạo đồng thời hai cơ chế cho cùng một method vì có thể khiến việc phân giải implementation khó đoán.

## 7. Thứ tự ưu tiên và xung đột method

Custom fragment có thể cung cấp method trùng chữ ký với method từ base repository hoặc repository aspect. Trong repository composition, implementation fragment được ưu tiên hơn base implementation và repository aspects; điều này cho phép ứng dụng thay đổi hành vi của method kế thừa khi có chủ đích.

Tuy nhiên, không nên để nhiều fragment cùng định nghĩa một method với chữ ký giống nhau nếu không có quy ước rõ ràng. Khi nhiều fragment cùng cung cấp method trùng, thứ tự composition có thể ảnh hưởng implementation được gọi. Hãy tránh xung đột bằng cách:

- Đặt tên method theo hành vi cụ thể, ví dụ `searchByNamePrefix` hoặc `rebuildSearchIndex`.
- Không khai báo cùng một chữ ký ở nhiều fragment độc lập.
- Nếu cố ý override method base, ghi rõ lý do và kiểm thử repository proxy thực tế.
- Giữ danh sách fragment trong repository interface ngắn và có ý nghĩa.

Đừng nhầm việc một fragment có method tên giống method CRUD với việc nó tự động thay thế mọi hành vi mặc định. Chữ ký, kiểu generic, khả năng phát hiện và thứ tự composition đều ảnh hưởng kết quả.

## 8. Tái sử dụng fragment và generic base repository

Một fragment có thể được dùng bởi nhiều repository nếu hành vi của nó thật sự chung. Ví dụ, một fragment cung cấp tìm kiếm theo một tiêu chí thống nhất có thể được ghép vào nhiều repository, nhưng implementation cần được thiết kế generic hoặc có dependency phù hợp với từng domain.

Với interface repository trung gian dùng generic type, hãy đánh dấu `@NoRepositoryBean` để Spring Data không cố tạo bean cho interface nền:

~~~java
import org.springframework.data.repository.NoRepositoryBean;
import org.springframework.data.neo4j.repository.Neo4jRepository;

@NoRepositoryBean
public interface BaseGraphRepository<T, ID> extends Neo4jRepository<T, ID> {
    // Chỉ khai báo những method thực sự dùng chung.
}
~~~

Repository cụ thể kế thừa base interface cùng các fragment riêng:

~~~java
public interface PersonRepository extends
        BaseGraphRepository<Person, String>,
        PersonSearch {
}
~~~

`@NoRepositoryBean` chỉ ngăn việc tạo repository bean cho interface trung gian; nó không phải annotation để phát hiện fragment implementation. Hai cơ chế có mục đích khác nhau.

Nếu mục tiêu là thay đổi cách triển khai một nhóm method cơ sở cho mọi repository, có thể cân nhắc custom repository base class qua cấu hình `repositoryBaseClass`. Fragment phù hợp hơn khi muốn bổ sung một khả năng độc lập mà không thay đổi toàn bộ base repository.

## 9. Các lỗi thường gặp khi fragment không được phát hiện

| Triệu chứng | Nguyên nhân thường gặp | Cách kiểm tra |
| --- | --- | --- |
| Không tìm thấy method fragment khi biên dịch | Repository interface chưa kế thừa fragment | Kiểm tra danh sách `extends` của repository |
| Repository không khởi tạo được | Implementation không được phát hiện hoặc thiếu dependency | Kiểm tra tên class, package và constructor dependencies |
| Spring báo thiếu implementation cho method tùy chỉnh | Tên implementation không theo hậu tố đã cấu hình | So sánh tên fragment interface và implementation |
| Đổi postfix nhưng fragment vẫn không hoạt động | Class vẫn dùng hậu tố cũ | Kiểm tra `repositoryImplementationPostfix` và tên file/class |
| Có nhiều bean implementation không mong muốn | Component scan và repository fragment discovery đăng ký cùng class theo hai cách không nhất quán | Kiểm tra cấu hình scan và bean definition |
| Method gọi nhầm implementation | Có nhiều fragment/base method trùng chữ ký | Loại bỏ trùng lặp hoặc làm rõ thứ tự composition |
| Repository ngoài package không được tạo | Package không nằm trong repository scan | Cấu hình `basePackages` hoặc `basePackageClasses` |

Lỗi fragment thường xuất hiện khi Spring tạo repository proxy lúc khởi động. Đọc phần `Caused by` trong stack trace để phân biệt lỗi không phát hiện implementation với lỗi dependency trong constructor của implementation.

## 10. Kiểm thử việc phát hiện và ghép fragment

Một kiểm thử tích hợp nên xác minh cả ba phần: Spring tạo repository bean, fragment method có thể được gọi và method thực thi đúng truy vấn Neo4j.

~~~java
@DataNeo4jTest
class PersonRepositoryFragmentTest {

    @Autowired
    PersonRepository personRepository;

    @Test
    void findsPeopleByNamePrefix() {
        // Chuẩn bị node Person trong database kiểm thử.
        Collection<PersonSummary> result =
            personRepository.searchByNamePrefix("An");

        assertThat(result)
            .extracting(PersonSummary::name)
            .contains("An Nguyen");
    }
}
~~~

Ví dụ giả định test fixture đã tạo một node `Person` có tên `An Nguyen`. Ngoài kết quả nghiệp vụ, cần xác nhận application context khởi tạo thành công với đúng implementation class. Nếu kiểm thử chỉ gọi trực tiếp `new PersonSearchImpl(...)`, nó không kiểm tra được cơ chế fragment discovery và repository composition.

## 11. Quy trình thêm một fragment mới

1. Xác định một nhóm hành vi riêng chưa phù hợp với derived query hoặc `@Query` thông thường.
2. Tạo fragment interface với tên thể hiện khả năng mà nó cung cấp.
3. Tạo implementation theo tên fragment cộng hậu tố đã cấu hình, mặc định là `Impl`.
4. Đặt interface và implementation trong package được repository infrastructure phát hiện.
5. Cho repository cụ thể kế thừa fragment interface.
6. Inject dependency bằng constructor và triển khai thao tác bằng `Neo4jClient`, `Neo4jTemplate` hoặc thành phần phù hợp.
7. Khởi động Spring context và kiểm thử method qua repository proxy.

Không tạo fragment chỉ để bọc một derived query đơn giản. Các method như `findByStatus` hoặc truy vấn ổn định có thể biểu diễn trực tiếp trong repository. Fragment phù hợp khi có logic truy vấn hoặc thao tác riêng, cần nhiều bước, tái sử dụng hoặc cần phối hợp với API khác.

## 12. Bài tập tự kiểm tra

1. Fragment interface khác repository interface kế thừa `Neo4jRepository` ở vai trò nào?
2. Với fragment `PersonSearch`, tên implementation mặc định phải là gì?
3. Vì sao chỉ tạo `PersonSearchImpl` mà không cho `PersonRepository` kế thừa `PersonSearch` thì method không xuất hiện trong repository?
4. `repositoryImplementationPostfix` ảnh hưởng đến việc phát hiện class ra sao?
5. Custom fragment có thể ảnh hưởng thế nào đến method trùng chữ ký từ base repository?
6. `@NoRepositoryBean` giải quyết vấn đề gì và khác fragment discovery như thế nào?
7. Khi nào nên dùng fragment, khi nào chỉ cần derived query hoặc `@Query`?
8. Vì sao cần kiểm thử method thông qua repository proxy thay vì chỉ khởi tạo implementation class trực tiếp?

Khi hoàn thành bài học, bạn cần tổ chức được fragment interface và implementation theo đúng quy ước tên, đặt chúng trong phạm vi phát hiện, ghép nhiều hành vi vào repository interface và xử lý xung đột method có chủ đích. Cách tổ chức này giúp repository SDN mở rộng theo từng khả năng mà vẫn dễ đọc, tái sử dụng và kiểm thử.

## Tài liệu tham khảo

- [Spring Data – Custom repository implementations](https://docs.spring.io/spring-data/commons/reference/repositories/custom-implementations.html)
- [Spring Data Neo4j – Repository configuration](https://docs.spring.io/spring-data/neo4j/reference/repositories/index.html)
