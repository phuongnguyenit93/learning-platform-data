# Thiết kế repository fragment và lớp triển khai

Bài học này thuộc chương **Repository mở rộng** của module **SPRING_DATA_NEO4J**. Repository của Spring Data Neo4j cung cấp sẵn CRUD, derived query và các tiện ích truy vấn phổ biến. Khi một use case cần logic riêng như tìm kiếm graph chuyên biệt, truy vấn nhiều bước, kiểm tra nghiệp vụ trước khi lưu hoặc tích hợp một dịch vụ khác, ta có thể mở rộng repository bằng repository fragment.

Repository fragment là một phần chức năng độc lập gồm interface và lớp triển khai. Repository chính kết hợp fragment với `Neo4jRepository`, nhờ đó người dùng repository có thể gọi cả API CRUD lẫn phương thức tùy biến. Đây là mô hình được Spring Data khuyến nghị để mở rộng từng repository và tái sử dụng chức năng giữa nhiều repository.

## 1. Repository được cấu thành từ nhiều fragment

Spring Data không xem repository chỉ là một interface cần một lớp `Impl` duy nhất. Repository proxy được tạo từ nhiều thành phần:

- **Base repository:** phần triển khai mặc định của store, ví dụ `SimpleNeo4jRepository`, cung cấp CRUD và các thao tác nền tảng.
- **Repository aspects:** các phần chức năng được Spring Data tích hợp như Query by Example hoặc Querydsl khi được bật.
- **Custom fragments:** các interface và implementation do ứng dụng định nghĩa.

Mỗi interface bổ sung vào khai báo repository có thể đóng góp một fragment vào composition. Nhờ đó, một repository có thể tập hợp nhiều năng lực độc lập thay vì dồn mọi phương thức tùy biến vào một lớp triển khai lớn.

Ví dụ:

```java
import com.example.graph.domain.Person;
import com.example.graph.repository.PersonSearchFragment;
import com.example.graph.repository.PersonStatisticsFragment;
import org.springframework.data.neo4j.repository.Neo4jRepository;

public interface PersonRepository extends
        Neo4jRepository<Person, String>,
        PersonSearchFragment,
        PersonStatisticsFragment {
}
```

Repository trên kết hợp CRUD của `Neo4jRepository` với tìm kiếm graph và thống kê do hai fragment cung cấp.

## 2. Bắt đầu bằng fragment interface

Hãy đặt tên fragment theo chức năng mà nó cung cấp, không đặt tên theo chi tiết triển khai. Ví dụ, `PersonSearchFragment` thể hiện khả năng tìm kiếm bổ sung cho repository:

Domain entity được sử dụng trong các ví dụ:

```java
package com.example.graph.domain;

import org.springframework.data.neo4j.core.schema.Id;
import org.springframework.data.neo4j.core.schema.Node;

@Node("Person")
public class Person {

    @Id
    private String id;

    private String name;

    // constructors, getters and setters
}
```

```java
package com.example.graph.repository;

import java.util.List;

import com.example.graph.domain.Person;

public interface PersonSearchFragment {

    List<Person> findPeopleBySkill(String skill);
}
```

Interface chỉ mô tả hợp đồng mà client cần dùng. Nó không cần kế thừa `Neo4jRepository` hoặc phụ thuộc trực tiếp vào `Neo4jTemplate`, `Neo4jClient` hay Driver. Giữ interface nhỏ giúp dễ tái sử dụng và kiểm thử.

## 3. Tạo implementation tương ứng

Theo quy ước mặc định, Spring Data tìm lớp triển khai bằng cách nối hậu tố `Impl` vào tên fragment interface. Với `PersonSearchFragment`, tên lớp là `PersonSearchFragmentImpl`:

```java
package com.example.graph.repository;

import java.util.List;
import java.util.Map;

import com.example.graph.domain.Person;
import org.springframework.data.neo4j.core.Neo4jOperations;

public class PersonSearchFragmentImpl implements PersonSearchFragment {

    private final Neo4jOperations neo4jOperations;

    public PersonSearchFragmentImpl(Neo4jOperations neo4jOperations) {
        this.neo4jOperations = neo4jOperations;
    }

    @Override
    public List<Person> findPeopleBySkill(String skill) {
        if (skill == null || skill.isBlank()) {
            throw new IllegalArgumentException("skill must not be blank");
        }

        return neo4jOperations.findAll("""
                MATCH (p:Person)-[:HAS_SKILL]->(:Skill {name: $skill})
                RETURN DISTINCT p
                ORDER BY p.name
                """,
            Map.of("skill", skill),
            Person.class
        );
    }
}
```

Implementation nhận `Neo4jOperations` qua constructor. Đây là abstraction của Spring Data Neo4j cho các thao tác persistence; implementation mặc định là `Neo4jTemplate`. Phương thức `findAll(query, parameters, Person.class)` chạy Cypher có tham số và ánh xạ node trả về thành `Person`.

Các giá trị đầu vào được bind qua map tham số. Không nối trực tiếp `skill` vào chuỗi Cypher. `DISTINCT` tránh trả cùng một người nhiều lần nếu graph có nhiều relationship phù hợp; `ORDER BY` xác định thứ tự kết quả.

## 4. Kết hợp fragment vào repository chính

Repository chính chỉ cần kế thừa interface fragment:

```java
package com.example.graph.repository;

import com.example.graph.domain.Person;
import org.springframework.data.neo4j.repository.Neo4jRepository;

public interface PersonRepository extends
        Neo4jRepository<Person, String>,
        PersonSearchFragment {
}
```

Client có thể gọi cả phương thức CRUD lẫn chức năng tìm kiếm:

```java
import java.util.List;

import com.example.graph.domain.Person;
import com.example.graph.repository.PersonRepository;

Person person = personRepository.findById("person-42")
    .orElseThrow();

List<Person> developers = personRepository.findPeopleBySkill("Java");
```

Không cần tự tạo lớp `PersonRepositoryImpl` để triển khai toàn bộ interface. Spring Data ghép base repository và fragment implementation khi tạo repository proxy.

## 5. Quy tắc đặt package và tên implementation

Repository infrastructure dò tìm implementation fragment trong package repository và các package con bên dưới. Cách bố trí đơn giản, dễ phát hiện là đặt fragment interface và implementation trong cùng package với repository:

```text
com.example.graph
├── domain
│   └── Person.java
└── repository
    ├── PersonRepository.java
    ├── PersonSearchFragment.java
    └── PersonSearchFragmentImpl.java
```

Với cấu trúc này, tên fragment interface và tên implementation khớp quy ước `FragmentName` + `Impl`. Lớp implementation có thể là một Spring bean thông thường; constructor injection hoạt động như với các bean khác.

Nếu muốn thay hậu tố mặc định, cấu hình `repositoryImplementationPostfix` trong `@EnableNeo4jRepositories`:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.data.neo4j.repository.config.EnableNeo4jRepositories;

@Configuration
@EnableNeo4jRepositories(
    basePackages = "com.example.graph.repository",
    repositoryImplementationPostfix = "Custom"
)
public class Neo4jRepositoryConfiguration {
}
```

Với cấu hình trên, implementation của `PersonSearchFragment` cần tên `PersonSearchFragmentCustom` thay vì `PersonSearchFragmentImpl`. Hãy giữ quy ước thống nhất trong module để việc dò tìm không gây nhầm lẫn.

## 6. Một repository có thể dùng nhiều fragment

Tách fragment theo nhóm trách nhiệm giúp tránh một implementation quá lớn. Ví dụ:

```java
public interface PersonStatisticsFragment {

    long countPeopleBySkill(String skill);
}
```

```java
import java.util.Map;

import org.springframework.data.neo4j.core.Neo4jOperations;

public class PersonStatisticsFragmentImpl
        implements PersonStatisticsFragment {

    private final Neo4jOperations neo4jOperations;

    public PersonStatisticsFragmentImpl(Neo4jOperations neo4jOperations) {
        this.neo4jOperations = neo4jOperations;
    }

    @Override
    public long countPeopleBySkill(String skill) {
        return neo4jOperations.count("""
                MATCH (p:Person)-[:HAS_SKILL]->(:Skill {name: $skill})
                RETURN count(DISTINCT p)
                """,
            Map.of("skill", skill)
        );
    }
}
```

Repository kết hợp hai fragment:

```java
import com.example.graph.domain.Person;
import com.example.graph.repository.PersonSearchFragment;
import com.example.graph.repository.PersonStatisticsFragment;
import org.springframework.data.neo4j.repository.Neo4jRepository;

public interface PersonRepository extends
        Neo4jRepository<Person, String>,
        PersonSearchFragment,
        PersonStatisticsFragment {
}
```

Mỗi fragment có implementation riêng. Các fragment có thể được dùng lại trong nhiều repository nếu hợp đồng và kiểu domain phù hợp.

Thứ tự khai báo fragment có ý nghĩa khi nhiều fragment cung cấp cùng một method signature. Custom fragment có độ ưu tiên cao hơn base repository và repository aspects; thứ tự composition được dùng để xử lý trường hợp các fragment tùy biến xung đột. Tốt nhất, hãy tránh khai báo trùng method signature nếu không có chủ ý override rõ ràng.

## 7. Tái sử dụng fragment generic

Fragment không nhất thiết chỉ phục vụ một entity. Có thể khai báo generic interface để nhiều repository dùng chung chức năng. Ví dụ, một fragment chuẩn hóa thao tác lưu:

```java
public interface CustomizedSave<T> {

    <S extends T> S save(S entity);
}
```

Implementation generic:

```java
import org.springframework.data.neo4j.core.Neo4jOperations;

public class CustomizedSaveImpl<T> implements CustomizedSave<T> {

    private final Neo4jOperations neo4jOperations;

    public CustomizedSaveImpl(Neo4jOperations neo4jOperations) {
        this.neo4jOperations = neo4jOperations;
    }

    @Override
    public <S extends T> S save(S entity) {
        // Thực hiện kiểm tra hoặc xử lý chung trước khi ghi.
        return neo4jOperations.save(entity);
    }
}
```

Các repository có thể dùng fragment này:

```java
import com.example.graph.domain.Movie;
import com.example.graph.domain.Person;
import org.springframework.data.neo4j.repository.Neo4jRepository;

public interface PersonRepository extends
        Neo4jRepository<Person, String>,
        CustomizedSave<Person> {
}

public interface MovieRepository extends
        Neo4jRepository<Movie, String>,
        CustomizedSave<Movie> {
}
```

Trong ví dụ, custom fragment định nghĩa lại method `save` có cùng signature với base repository. Fragment tùy biến có thể ghi đè hành vi base khi repository composition được tạo. Implementation gọi `Neo4jOperations.save(entity)` để thực hiện thao tác persistence mặc định sau phần xử lý riêng; không gọi ngược `repository.save(entity)` từ chính fragment vì lời gọi có thể quay lại method override và gây đệ quy.

Chỉ nên override CRUD method khi có quy tắc chung thực sự cần áp dụng cho các repository sử dụng fragment. Nếu logic chỉ thuộc một use case, hãy tạo method có tên riêng như `saveWithPolicy` để tránh thay đổi semantics CRUD mà client đang kỳ vọng.

## 8. Inject Neo4jOperations, Neo4jClient hoặc Driver

Implementation fragment là Spring bean nên có thể inject các dependency cần thiết qua constructor:

| Dependency | Dùng khi | Đặc điểm |
|---|---|---|
| `Neo4jOperations` / `Neo4jTemplate` | Cần lưu, tìm và ánh xạ domain entity | Tận dụng mapping context của SDN |
| `Neo4jClient` | Cần chạy Cypher tùy biến và kiểm soát cách đọc record | Tích hợp với transaction Spring, nhưng mapping entity cần được yêu cầu rõ |
| Neo4j `Driver` | Cần chức năng cấp thấp của Java Driver | Ứng dụng tự chịu trách nhiệm session/result lifecycle và cách ánh xạ |
| Service khác | Cần gọi domain service hoặc thành phần tích hợp | Dùng dependency injection và các quy tắc Spring thông thường |

Với phần lớn custom repository query, `Neo4jOperations` hoặc `Neo4jClient` là lựa chọn phù hợp. Tránh tự tạo một `Driver` mới trong mỗi fragment; hãy dùng bean được cấu hình chung trong application context để giữ connection pool và transaction manager nhất quán.

## 9. Transaction trong custom fragment

Custom fragment có thể tham gia transaction Spring như các thành phần persistence khác. Ranh giới transaction thường được đặt ở service để một nghiệp vụ có thể phối hợp nhiều repository call:

```java
import java.util.List;

import com.example.graph.domain.Person;
import com.example.graph.repository.PersonRepository;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class PersonSearchService {

    private final PersonRepository personRepository;

    public PersonSearchService(PersonRepository personRepository) {
        this.personRepository = personRepository;
    }

    @Transactional(readOnly = true)
    public List<Person> findDevelopers(String skill) {
        return personRepository.findPeopleBySkill(skill);
    }
}
```

Với một fragment chỉ đọc, `@Transactional(readOnly = true)` thể hiện rõ ý định. Với thao tác ghi hoặc phối hợp nhiều bước, dùng transaction ghi phù hợp. Custom implementation dùng `Neo4jOperations` hoặc `Neo4jClient` được cấu hình cùng hạ tầng SDN có thể tham gia transaction đang mở.

`@Transactional` dựa trên proxy Spring. Lời gọi phải đi qua proxy để transaction được áp dụng; self-invocation bên trong cùng object không kích hoạt một transaction mới chỉ vì method được gắn annotation. Đặt ranh giới transaction ở service công khai thường giúp hành vi dễ dự đoán hơn.

## 10. Khi fragment implementation nằm ngoài package repository

Mặc định, Spring Data dò tìm fragment implementation trong package repository và các package con. Nếu fragment nằm trong một thư viện hoặc package không được scan, có thể đăng ký fragment thông qua `META-INF/spring.factories`.

Ví dụ file `META-INF/spring.factories`:

```properties
com.example.search.SearchExtension=com.example.search.DefaultSearchExtension
```

Hợp đồng fragment được đóng gói trong thư viện có thể có dạng:

```java
package com.example.search;

import java.util.List;

public interface SearchExtension<T> {

    List<T> search(String text, int limit);
}
```

Repository chỉ cần thêm fragment interface:

```java
import com.example.graph.domain.Movie;
import com.example.search.SearchExtension;
import org.springframework.data.neo4j.repository.Neo4jRepository;

public interface MovieRepository extends
        Neo4jRepository<Movie, String>,
        SearchExtension<Movie> {
}
```

Cách đăng ký này hữu ích khi đóng gói chức năng dùng chung trong một thư viện độc lập. Với fragment nội bộ ứng dụng, đặt implementation trong phạm vi package repository thường đơn giản hơn.

## 11. Khi cần RepositoryMethodContext

Một fragment generic đôi khi cần biết repository nào đang gọi nó, ví dụ để chọn index tìm kiếm theo domain type. Spring Data cung cấp `RepositoryMethodContext` cho metadata của invocation, nhưng việc expose metadata bị tắt mặc định vì có chi phí.

Implementation fragment có thể triển khai marker interface `RepositoryMetadataAccess` để yêu cầu metadata cho các repository dùng fragment đó:

```java
import org.springframework.data.repository.core.support.RepositoryMetadataAccess;

public class DefaultSearchExtension<T>
        implements SearchExtension<T>, RepositoryMetadataAccess {

    // Implementation dùng RepositoryMethodContext khi cần.
}
```

Chỉ bật cơ chế này khi implementation thực sự cần metadata như domain type hoặc thông tin repository. Không bật expose metadata toàn cục nếu chỉ một fragment cần nó, vì mọi invocation có thể phải chịu thêm chi phí.

## 12. Phân biệt fragment với custom base repository

Repository fragment và custom base repository giải quyết hai phạm vi khác nhau:

| Nhu cầu | Cách mở rộng |
|---|---|
| Thêm một nhóm chức năng cho một vài repository | Repository fragment |
| Chia chức năng thành nhiều implementation có thể tái sử dụng | Nhiều repository fragments |
| Thay đổi hành vi nền tảng cho mọi repository trong cấu hình | Custom base repository |
| Thay đổi cách Spring tạo repository proxy hoặc composition | Repository factory customization |

Nếu muốn thay đổi hành vi mặc định của tất cả repository, SDN cho phép kế thừa `SimpleNeo4jRepository` và cấu hình `repositoryBaseClass`:

```java
import org.springframework.data.neo4j.core.Neo4jEntityInformation;
import org.springframework.data.neo4j.core.Neo4jOperations;
import org.springframework.data.neo4j.repository.support.SimpleNeo4jRepository;

public class CustomNeo4jRepository<T, ID>
        extends SimpleNeo4jRepository<T, ID> {

    public CustomNeo4jRepository(
            Neo4jOperations neo4jOperations,
            Neo4jEntityInformation<T, ID> entityInformation) {
        super(neo4jOperations, entityInformation);
    }
}
```

Đăng ký base class:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.data.neo4j.repository.config.EnableNeo4jRepositories;

@Configuration
@EnableNeo4jRepositories(
    basePackages = "com.example.graph.repository",
    repositoryBaseClass = CustomNeo4jRepository.class
)
public class Neo4jRepositoryConfiguration {
}
```

Constructor nhận `Neo4jOperations` và `Neo4jEntityInformation` theo yêu cầu của base class SDN. Chỉ dùng cách này khi thay đổi cần áp dụng rộng cho repository được cấu hình. Với chức năng chỉ thuộc một nhóm repository, fragment thường rõ ràng và ít ảnh hưởng hơn.

Tùy biến repository factory hoặc factory bean là cấp mở rộng sâu hơn, cho phép thay đổi cách tạo proxy và đăng ký fragment. Đây là lựa chọn dành cho framework extension hoặc nhu cầu hạ tầng đặc biệt, không phải cách mặc định để thêm một phương thức tìm kiếm.

## 13. Tránh kiểu triển khai repository đơn lẻ cũ

Trước đây, Spring Data thường dò một lớp có tên bằng tên repository cộng `Impl`, ví dụ `PersonRepositoryImpl`. Cách làm này có thể khiến Spring coi lớp đó là custom implementation của toàn repository và dẫn tới hành vi khó dự đoán khi package có nhiều repository hoặc implementation.

Tài liệu Spring Data hiện khuyến nghị mô hình fragment-based thay cho quy ước single-custom-implementation cũ. Hãy đặt tên implementation theo fragment interface:

```text
PersonSearchFragment       -> PersonSearchFragmentImpl
PersonStatisticsFragment   -> PersonStatisticsFragmentImpl
CustomizedSave             -> CustomizedSaveImpl
```

Tránh dùng `PersonRepositoryImpl` như một lớp chứa mọi phương thức tùy biến. Nếu cần mở rộng repository, khai báo các fragment rõ chức năng và kết hợp chúng trong interface repository.

## 14. Xử lý trùng tên implementation và wiring thủ công

Nếu có nhiều lớp implementation cùng khớp tên fragment ở các package khác nhau, Spring Data dùng bean name để giải quyết. Bean name mặc định được hình thành từ tên fragment interface viết thường chữ cái đầu cộng hậu tố implementation.

Nếu implementation cần cấu hình đặc biệt hoặc cần wiring thủ công, có thể khai báo bean với tên phù hợp để repository infrastructure sử dụng bean đó thay cho việc tự tạo implementation. Khi làm vậy, cần bảo đảm bean name khớp fragment và postfix đang cấu hình. Tránh đăng ký đồng thời nhiều bean cùng đại diện cho một fragment nếu không có quy tắc phân giải rõ ràng.

## 15. Kiểm thử repository fragment

Fragment nên được kiểm thử ở hai mức:

1. **Unit test implementation:** mock `Neo4jOperations` hoặc dependency ngoài để kiểm tra đầu vào, tham số Cypher và cách xử lý kết quả.
2. **Integration test repository:** dùng Neo4j Test Harness hoặc Testcontainers để xác nhận Spring phát hiện fragment, ghép implementation vào repository proxy và truy vấn hoạt động với graph thực.

Các trường hợp nên xác minh:

- Repository khởi động thành công và gọi được method fragment.
- `Neo4jOperations` nhận đúng Cypher, map tham số và domain type.
- Kết quả không trùng khi graph có nhiều relationship phù hợp.
- Transaction ở service bao trùm được các thao tác fragment và repository cần phối hợp.
- Nhiều fragment cùng được phát hiện trong một repository.
- Fragment generic được tái sử dụng bởi các repository domain khác nhau.
- Nếu fragment override `save`, hành vi mới được gọi và phần delegate không gây đệ quy.
- Nếu dùng custom postfix hoặc `spring.factories`, implementation vẫn được phát hiện theo cấu hình.

## 16. Nguyên tắc thiết kế

- Tạo fragment interface theo một trách nhiệm rõ ràng và giữ hợp đồng nhỏ.
- Đặt implementation theo tên fragment cộng `Impl` mặc định, trong package repository hoặc package con được scan.
- Kết hợp fragment bằng cách cho repository chính kế thừa interface fragment.
- Dùng constructor injection và các abstraction SDN như `Neo4jOperations` hoặc `Neo4jClient`.
- Chia các nhóm chức năng thành nhiều fragment thay vì gom vào một lớp triển khai lớn.
- Chỉ override CRUD method khi cần thay đổi semantics có chủ đích; tránh gọi ngược repository gây đệ quy.
- Đặt transaction boundary ở service khi một nghiệp vụ phối hợp nhiều repository hoặc fragment.
- Dùng custom base repository khi thay đổi áp dụng cho toàn bộ repository; chỉ dùng factory customization cho nhu cầu hạ tầng sâu.
- Ưu tiên mô hình fragment-based thay cho tên implementation cũ theo repository interface.

Repository fragment giúp mở rộng repository theo từng năng lực có thể tái sử dụng. Khi interface mô tả rõ chức năng, implementation giữ riêng logic persistence và repository chính chỉ kết hợp các fragment cần thiết, cấu trúc truy cập dữ liệu sẽ dễ kiểm thử, dễ thay đổi và ít phụ thuộc vào một lớp triển khai khổng lồ.

## Tài liệu tham khảo

- [Spring Data Neo4j 8.1 – Custom Repository Implementations](https://docs.spring.io/spring-data/neo4j/reference/repositories/custom-implementations.html)
- [Spring Data Neo4j 8.1 – FAQ: Custom base repositories](https://docs.spring.io/spring-data/neo4j/reference/faq.html)
- [Spring Data Commons – Custom Repository Implementations](https://docs.spring.io/spring-data/commons/reference/repositories/custom-implementations.html)
- [Spring Data Neo4j – Neo4jTemplate API](https://docs.spring.io/spring-data/data-neo4j/docs/current/api/org/springframework/data/neo4j/core/Neo4jTemplate.html)
