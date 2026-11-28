# Giao dịch mặc định của CRUD và phương thức truy vấn tự khai báo

Spring Data Neo4j (SDN) cung cấp transaction mặc định cho các thao tác CRUD kế thừa từ repository. Những thao tác đọc cơ bản được đánh dấu read-only; các thao tác ghi như `save()` và `delete()` mở transaction đọc/ghi. Phương thức truy vấn do ứng dụng tự khai báo cần được xem xét riêng: SDN không thể suy luận mọi câu Cypher có chỉ đọc hay có thay đổi graph, vì vậy cần khai báo rõ transaction phù hợp.

Bài học thuộc module **SPRING_DATA_NEO4J**, tập trung xây dựng tầng dữ liệu đồ thị qua node entity, relationship, repository và Cypher. Ví dụ dùng `Person`, `Movie` và `ACTED_IN` để phân biệt transaction mặc định của CRUD với transaction cho derived query hoặc `@Query`, đồng thời thiết kế ranh giới giao dịch đồng bộ ở tầng service.

## 1. Vì sao thao tác repository cần transaction?

Neo4j là cơ sở dữ liệu giao dịch. Một thao tác ghi cần được thực hiện trong transaction để Neo4j có thể commit hoặc rollback thay đổi. SDN tích hợp với transaction manager của Spring để các lời gọi repository, template và client có thể tham gia cùng một đơn vị công việc.

Trong ứng dụng đồng bộ (*imperative*), transaction được quản lý theo luồng thực thi đồng bộ và thường được mở qua `@Transactional` hoặc `TransactionTemplate`. `Neo4jTransactionManager` kết nối transaction của Spring với transaction của Neo4j.

Một lời gọi repository độc lập vẫn có thể được quản lý bởi transaction mặc định của chính phương thức CRUD. Tuy nhiên, nếu một use case gồm nhiều lần đọc/ghi, cần đặt transaction ở tầng service để các bước cùng commit hoặc cùng rollback.

## 2. Transaction mặc định của CRUD repository

Implementation mặc định của repository SDN là `SimpleNeo4jRepository`. Lớp này được đánh dấu `@Transactional(readOnly = true)`. Các phương thức ghi ghi đè cấu hình đó bằng `@Transactional` thông thường, tức transaction đọc/ghi.

| Phương thức CRUD | Transaction mặc định | Ý nghĩa |
|---|---|---|
| `findById(id)` | Read-only | Đọc entity theo ID |
| `findAll()` / `findAllById(ids)` | Read-only | Đọc một hoặc nhiều entity |
| `findAll(Pageable)` / `findAll(Sort)` | Read-only | Đọc entity có phân trang hoặc sắp xếp |
| `existsById(id)` | Read-only | Kiểm tra sự tồn tại |
| `count()` | Read-only | Đếm entity của repository |
| `save(entity)` / `saveAll(entities)` | Read/write | Tạo mới hoặc cập nhật graph |
| `delete(entity)` / `deleteById(id)` | Read/write | Xóa entity |
| `deleteAll(...)` / `deleteAllById(...)` | Read/write | Xóa theo tập đầu vào hoặc toàn bộ domain type |

Các phương thức đọc CRUD kế thừa cấu hình read-only của lớp repository. Những phương thức ghi được đánh dấu `@Transactional` riêng để ghi đè `readOnly = true` của lớp.

Ví dụ:

```java
public interface PersonRepository extends Neo4jRepository<Person, Long> {
}
```

Không cần thêm annotation cho mỗi phương thức CRUD chuẩn:

```java
Person person = personRepository.findById(personId)
    .orElseThrow();

person.setName("Keanu Reeves");
Person saved = personRepository.save(person);
```

Lời gọi `findById()` dùng transaction đọc mặc định; `save()` dùng transaction ghi mặc định nếu chưa có transaction bên ngoài. Khi hai lời gọi được đặt trong một service có `@Transactional`, cả hai tham gia transaction bên ngoài đó.

## 3. Phương thức truy vấn tự khai báo không tự được đánh dấu read-only

Một repository có thể khai báo derived query:

```java
List<Person> findByNameContaining(String fragment);
```

Hoặc truy vấn Cypher tùy chỉnh:

```java
@Query("""
    MATCH (p:Person)-[:ACTED_IN]->(m:Movie)
    WHERE m.title = $title
    RETURN DISTINCT p
    """)
List<Person> findActorsForMovie(String title);
```

Mặc dù tên `find...` hoặc nội dung truy vấn có vẻ chỉ đọc, SDN không phân tích Cypher để kết luận mọi phương thức tự khai báo là read-only. Một truy vấn `@Query` có thể dùng `MERGE`, `CREATE`, `SET`, `DELETE` hoặc gọi procedure có tác dụng ghi. Vì vậy, không nên giả định phương thức truy vấn tự khai báo được gắn `readOnly = true` giống các phương thức đọc CRUD dựng sẵn.

Nếu biết chắc phương thức chỉ đọc, hãy đánh dấu rõ:

```java
@Transactional(readOnly = true)
List<Person> findByNameContaining(String fragment);
```

Nếu phương thức thực hiện thay đổi graph, hãy dùng transaction đọc/ghi:

```java
@Transactional
@Query("""
    MATCH (p:Person {personId: $personId})
    SET p.name = $newName
    """)
void renamePerson(String personId, String newName);
```

`@Transactional` không truyền `readOnly = true` tương đương cấu hình transaction ghi mặc định. Khai báo rõ ràng giúp người đọc biết phương thức có thể thay đổi graph và tránh vô tình chạy nó trong transaction chỉ đọc.

## 4. Đặt mặc định read-only ở cấp repository

Nếu hầu hết phương thức tự khai báo trong repository chỉ đọc, có thể đặt `@Transactional(readOnly = true)` trên interface:

```java
import org.springframework.data.neo4j.repository.Neo4jRepository;
import org.springframework.data.neo4j.repository.query.Query;
import org.springframework.transaction.annotation.Transactional;

@Transactional(readOnly = true)
public interface PersonRepository extends Neo4jRepository<Person, Long> {

    List<Person> findByNameContaining(String fragment);

    @Query("""
        MATCH (p:Person)-[:ACTED_IN]->(m:Movie)
        WHERE m.title = $title
        RETURN DISTINCT p
        """)
    List<Person> findActorsForMovie(String title);

    @Transactional
    @Query("""
        MATCH (p:Person {personId: $personId})
        SET p.name = $newName
        """)
    void renamePerson(String personId, String newName);
}
```

Hai phương thức tìm kiếm dùng cấu hình read-only ở cấp interface. `renamePerson()` ghi đè cấu hình đó bằng `@Transactional` để có transaction đọc/ghi.

Đây là một quy ước tiện lợi khi repository chủ yếu phục vụ truy vấn. Nếu repository có nhiều phương thức ghi hoặc mỗi phương thức có yêu cầu khác nhau, khai báo annotation trên từng method có thể rõ ràng hơn.

## 5. Read-only có ý nghĩa gì trong Neo4j?

`readOnly = true` mô tả ý định truy cập dữ liệu của transaction. Nó không phải cơ chế phân quyền thay thế tài khoản Neo4j và cũng không nên được dùng như một cách kiểm tra bảo mật rằng câu Cypher chắc chắn không ghi.

Trong môi trường Neo4j cluster có primary và read replica, thông tin read-only đặc biệt quan trọng: các truy vấn đọc có thể được định tuyến phù hợp tới thành phần phục vụ đọc, còn thao tác ghi phải được gửi tới primary. SDN và Neo4j Java Driver không phân tích nội dung Cypher để tự đoán câu lệnh là đọc hay ghi; mặc định hệ thống cần an toàn cho cả trường hợp truy vấn có thay đổi dữ liệu.

Vì vậy:

- Đánh dấu `readOnly = true` cho truy vấn chắc chắn chỉ đọc.
- Dùng `@Transactional` thông thường cho truy vấn ghi hoặc procedure có tác dụng ghi.
- Không đặt toàn bộ repository là read-only nếu bên trong có method ghi mà chưa ghi đè.
- Không dùng read-only như ranh giới bảo mật; quyền thực tế vẫn phải được cấu hình ở Neo4j.

Nếu chạy một truy vấn ghi trong transaction được đánh dấu read-only, hành vi không phải là một cách được hỗ trợ để “thử xem có ghi được không”. Truy vấn có thể thất bại hoặc bị định tuyến không phù hợp trong cluster. Hãy khai báo đúng access mode ngay từ đầu.

## 6. Gộp nhiều repository call trong transaction của service

Các transaction mặc định ở repository bảo vệ từng lời gọi CRUD độc lập. Chúng không tự biến nhiều lời gọi liên tiếp thành một transaction chung nếu service không đặt ranh giới giao dịch.

Ví dụ, một use case đọc người, tìm các phim đã tham gia rồi tạo một bản ghi audit cần một transaction đọc/ghi chung:

```java
import java.util.List;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class PersonService {

    private final PersonRepository personRepository;
    private final MovieRepository movieRepository;
    private final AuditRepository auditRepository;

    public PersonService(
            PersonRepository personRepository,
            MovieRepository movieRepository,
            AuditRepository auditRepository) {
        this.personRepository = personRepository;
        this.movieRepository = movieRepository;
        this.auditRepository = auditRepository;
    }

    @Transactional
    public List<Movie> recordProfileView(Long personId) {
        Person person = personRepository.findById(personId)
            .orElseThrow();

        List<Movie> movies = movieRepository
            .findByActorsPersonId(person.getPersonId());

        auditRepository.save(new AuditEvent(
            "PERSON_PROFILE_VIEWED",
            person.getPersonId()
        ));

        return movies;
    }
}
```

Ví dụ giả định repository và entity phụ trợ đã được khai báo. `@Transactional` trên service tạo một đơn vị công việc: các lời gọi repository tham gia cùng transaction hiện tại. Nếu thao tác lưu audit thất bại và exception làm transaction rollback, các thao tác ghi trong cùng transaction cũng được hoàn tác.

Nếu use case chỉ đọc, có thể đánh dấu:

```java
@Transactional(readOnly = true)
public PersonDetails getPersonDetails(Long personId) {
    // Đọc Person và các Movie liên quan trong cùng transaction.
}
```

Đặt ranh giới ở service giúp transaction bao trùm đúng nghiệp vụ, thay vì phụ thuộc vào từng lần gọi repository riêng lẻ.

## 7. Cấu hình ở transaction bên ngoài có ưu tiên

Spring mặc định dùng propagation `REQUIRED` cho `@Transactional`. Khi một service đã mở transaction, repository method được gọi bên trong thường tham gia transaction hiện tại thay vì mở transaction độc lập mới.

Điều đó có nghĩa cấu hình của transaction bên ngoài quyết định hành vi thực tế của đơn vị công việc. Ví dụ:

```java
@Transactional(readOnly = true)
public PersonDetails loadDetailsAndUpdate(Long personId) {
    Person person = personRepository.findById(personId).orElseThrow();
    person.setName("New name");
    return new PersonDetails(personRepository.save(person));
}
```

Đoạn code này thiết kế sai: lời gọi `save()` bên trong không tự chuyển transaction read-only bên ngoài thành transaction ghi. Không đặt thao tác thay đổi graph trong một service transaction được đánh dấu read-only.

Hãy dùng transaction ghi cho use case có bất kỳ thao tác thay đổi dữ liệu nào:

```java
@Transactional
public Person rename(Long personId, String newName) {
    Person person = personRepository.findById(personId).orElseThrow();
    person.setName(newName);
    return personRepository.save(person);
}
```

Nếu cần tách phần đọc và ghi, hãy thiết kế các service/use case riêng với transaction boundary rõ ràng. Không trông chờ annotation ở repository con ghi đè access mode của transaction đã mở ở tầng trên.

## 8. Tùy chỉnh transaction của CRUD method

Nếu một CRUD method cần timeout hoặc thuộc tính transaction khác, có thể redeclare method trong repository và thêm annotation phù hợp:

```java
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.transaction.annotation.Transactional;

public interface MovieRepository extends Neo4jRepository<Movie, Long> {

    @Override
    @Transactional(readOnly = true, timeout = 5)
    Page<Movie> findAll(Pageable pageable);
}
```

Ví dụ minh họa cách redeclare để điều chỉnh metadata transaction. Chỉ đặt timeout khi có yêu cầu vận hành cụ thể và giá trị phù hợp với thời gian truy vấn thực tế. Khi method được gọi bên trong transaction service đã tồn tại, transaction bên ngoài vẫn chi phối theo propagation.

## 9. Transaction qua proxy và lời gọi nội bộ

`@Transactional` dạng annotation được Spring áp dụng thông qua proxy/AOP. Lời gọi từ bên ngoài bean đi qua proxy mới được xử lý theo cấu hình transaction. Một method trong cùng class gọi trực tiếp method khác (`self-invocation`) thường không đi qua proxy, nên annotation trên method được gọi nội bộ có thể không được áp dụng như mong đợi.

Ví dụ cần tránh:

```java
@Service
public class ImportService {

    public void importAll() {
        importOne(); // Gọi nội bộ, không đi qua proxy.
    }

    @Transactional
    public void importOne() {
        // Ghi graph.
    }
}
```

Nếu cần transaction cho toàn bộ import, hãy đặt annotation trên phương thức public được gọi từ bên ngoài:

```java
@Transactional
public void importAll() {
    importOne();
}
```

Hoặc tách thao tác thành một Spring bean khác để lời gọi đi qua proxy. Với logic nội bộ cần điều khiển transaction bằng code, dùng `TransactionTemplate` là một lựa chọn rõ ràng.

## 10. Dùng TransactionTemplate khi cần điều khiển bằng code

`TransactionTemplate` hữu ích khi ranh giới giao dịch không thể biểu diễn thuận tiện bằng proxy annotation, ví dụ cần chạy một đoạn code nội bộ trong transaction read-only:

```java
import org.springframework.stereotype.Service;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.TransactionDefinition;
import org.springframework.transaction.support.TransactionTemplate;

@Service
public class PersonReadService {

    private final TransactionTemplate readOnlyTransaction;
    private final PersonRepository personRepository;

    public PersonReadService(
            PlatformTransactionManager transactionManager,
            PersonRepository personRepository) {
        this.readOnlyTransaction = new TransactionTemplate(transactionManager);
        this.readOnlyTransaction.setReadOnly(true);
        this.readOnlyTransaction.setPropagationBehavior(
            TransactionDefinition.PROPAGATION_REQUIRED
        );
        this.personRepository = personRepository;
    }

    public Person load(Long id) {
        return readOnlyTransaction.execute(status ->
            personRepository.findById(id).orElseThrow()
        );
    }
}
```

`TransactionTemplate` sử dụng transaction manager được inject. Trong ứng dụng có nhiều transaction manager, cần inject đúng bean Neo4j. Không cần dùng `TransactionTemplate` cho mọi repository call; `@Transactional` trên service vẫn là cách đơn giản và phổ biến cho ranh giới nghiệp vụ.

## 11. Quy tắc rollback mặc định

Khi transaction Spring gặp lỗi, quy tắc rollback quyết định các thay đổi được commit hay hoàn tác. Mặc định, Spring đánh dấu rollback khi có `RuntimeException` hoặc `Error`. Checked exception không tự động kích hoạt rollback theo quy tắc mặc định.

Nếu use case cần rollback cả checked exception, khai báo:

```java
@Transactional(rollbackFor = Exception.class)
public void importPeople() throws Exception {
    // Nhiều thao tác ghi graph.
}
```

Không bắt exception rồi bỏ qua nếu nghiệp vụ yêu cầu rollback. Nếu cần chuyển đổi lỗi, hãy ném lại exception phù hợp hoặc chủ động đánh dấu transaction rollback-only.

## 12. Những lỗi thường gặp

| Lỗi | Hệ quả | Cách xử lý |
|---|---|---|
| Nghĩ mọi query method có `find` đều tự read-only | Custom `@Query` có thể chứa `MERGE` hoặc thao tác ghi | Đánh dấu `@Transactional(readOnly = true)` khi chắc chắn chỉ đọc |
| Nghĩ class-level read-only tự áp dụng đúng cho mọi method tự khai báo | Method query có thể có access mode không phù hợp | Khai báo transaction rõ ở repository hoặc service |
| Đặt repository read-only nhưng không ghi đè method ghi | Write method chạy trong transaction read-only | Thêm `@Transactional` cho method ghi hoặc chuyển boundary lên service |
| Gọi nhiều repository method và kỳ vọng chúng tự chung một transaction | Mỗi lời gọi độc lập có thể có transaction riêng | Đặt `@Transactional` trên service/facade |
| Gọi `save()` bên trong service read-only | Transaction bên ngoài vẫn chi phối | Đổi service sang transaction ghi |
| Coi `readOnly` là quyền cấm ghi | Nhầm access mode với cơ chế phân quyền | Quản lý quyền tại Neo4j và khai báo đúng transaction |
| Dùng `@Transactional` ở method private hoặc self-invocation | Proxy có thể không áp dụng annotation | Dùng public boundary qua proxy hoặc `TransactionTemplate` |
| Dùng checked exception và mong tự rollback | Transaction có thể commit theo mặc định | Cấu hình `rollbackFor` hoặc ném unchecked exception phù hợp |
| Dùng sai transaction manager trong ứng dụng nhiều database | Lời gọi không tham gia transaction Neo4j mong muốn | Chỉ định đúng bean transaction manager |

## 13. Checklist thiết kế transaction đồng bộ

- Xác định method đang dùng CRUD kế thừa hay query method tự khai báo.
- Nhớ rằng `SimpleNeo4jRepository` mặc định read-only; các CRUD method ghi có annotation ghi đè.
- Đánh dấu rõ query method chỉ đọc bằng `@Transactional(readOnly = true)`.
- Dùng `@Transactional` thông thường cho query method có thay đổi graph.
- Đặt transaction boundary tại service khi một use case gồm nhiều repository/client call.
- Không đặt thao tác ghi bên trong transaction read-only bên ngoài.
- Dùng đúng transaction manager Neo4j nếu ứng dụng có nhiều manager.
- Đảm bảo lời gọi transactional đi qua Spring proxy; cân nhắc `TransactionTemplate` cho logic nội bộ.
- Xác định rollback rule cho checked exception nếu use case cần.
- Kiểm thử cả trường hợp commit và rollback với Neo4j integration test.

## 14. Bài tập thực hành

1. Tạo `PersonRepository` và liệt kê các CRUD method đọc, ghi có transaction mặc định nào.
2. Viết `findByNameContaining` và đánh dấu `@Transactional(readOnly = true)`.
3. Viết `@Query` dùng `SET p.name = $newName`; đánh dấu `@Transactional` và giải thích vì sao không được read-only.
4. Đặt `@Transactional(readOnly = true)` ở cấp repository rồi ghi đè một method cập nhật bằng `@Transactional`.
5. Tạo service gọi `PersonRepository` và `MovieRepository` trong cùng một transaction read-only.
6. Tạo service lưu entity và ghi audit trong một transaction; cố ý phát sinh exception để kiểm tra rollback.
7. Thử gọi method ghi bên trong service read-only và giải thích vì sao annotation của method con không chuyển transaction bên ngoài thành read/write.
8. Tạo một method private được đánh dấu `@Transactional`, gọi nội bộ và quan sát proxy behavior; sau đó sửa bằng `TransactionTemplate`.
9. Thêm checked exception vào use case và cấu hình `rollbackFor` để kiểm chứng rollback.

Khi hoàn thành, bạn cần phân biệt được transaction mặc định của CRUD kế thừa với transaction của phương thức truy vấn tự khai báo. CRUD ghi có transaction đọc/ghi, CRUD đọc chuẩn được đánh dấu read-only; còn query method cần được đánh dấu theo đúng bản chất Cypher. Đặt transaction ở service giúp nhiều thao tác graph trở thành một đơn vị công việc nhất quán.

## Tài liệu tham khảo

- [Spring Data Neo4j — FAQ: read-only transactions and repository methods](https://docs.spring.io/spring-data/neo4j/reference/faq.html)
- [Spring Data Neo4j — SimpleNeo4jRepository API 8.1.x](https://docs.spring.io/spring-data/neo4j/reference/api/java/org/springframework/data/neo4j/repository/support/SimpleNeo4jRepository.html)
- [Spring Data Neo4j — Query Methods](https://docs.spring.io/spring-data/neo4j/reference/8.1/repositories/query-methods.html)
- [Spring Framework — Declarative Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative.html)
- [Spring Framework — Programmatic Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction/programmatic.html)
