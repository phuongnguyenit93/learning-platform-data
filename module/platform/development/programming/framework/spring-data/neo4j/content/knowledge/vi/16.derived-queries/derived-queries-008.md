# Phương thức count, exists và delete theo điều kiện

Spring Data Neo4j cho phép khai báo phương thức repository để đếm, kiểm tra sự tồn tại hoặc xóa entity theo điều kiện ngay trong tên phương thức. Thay vì tự viết Cypher cho mọi thao tác, ta dùng các tiền tố `countBy`, `existsBy`, `deleteBy` hoặc `removeBy`, sau đó mô tả điều kiện dựa trên property của entity.

Trong module `SPRING_DATA_NEO4J`, các phương thức này giúp tầng dữ liệu trả lời những câu hỏi thường gặp của nghiệp vụ: có bao nhiêu node thỏa điều kiện, một email đã được sử dụng chưa, hoặc cần xóa những entity nào theo trạng thái và thời điểm. Điều quan trọng là chọn đúng kiểu trả về, hiểu phạm vi điều kiện và kiểm soát tác động của thao tác xóa trên đồ thị.

## 1. Cấu trúc tên phương thức suy diễn

Spring Data phân tích tên query method thành hai phần:

- **Subject:** tiền tố cho biết loại thao tác, chẳng hạn `count`, `exists`, `delete` hoặc `remove`.
- **Predicate:** phần bắt đầu sau từ `By`, mô tả property và điều kiện lọc.

Ví dụ:

```java
long countByStatusAndActiveTrue(PersonStatus status);
boolean existsByEmail(String email);
long deleteByStatusAndLastSeenBefore(PersonStatus status, LocalDateTime cutoff);
```

Với `countByStatusAndActiveTrue`, subject `count` yêu cầu phép đếm; predicate là `StatusAndActiveTrue`. Tham số `status` được gắn với điều kiện `Status`, còn `ActiveTrue` là điều kiện boolean cố định nên không cần tham số thứ hai.

Phần predicate phải tham chiếu đúng property trong domain class. Spring Data kiểm tra tên property khi khởi tạo repository; nếu viết sai, ứng dụng có thể lỗi ngay lúc tạo application context thay vì đợi đến khi gọi phương thức.

## 2. Chuẩn bị entity và repository

Dùng một entity `Person` để minh họa các thao tác:

```java
import org.springframework.data.neo4j.core.schema.Id;
import org.springframework.data.neo4j.core.schema.Node;

import java.time.LocalDateTime;

@Node("Person")
public class Person {

    @Id
    private String id;

    private String email;
    private PersonStatus status;
    private boolean active;
    private LocalDateTime lastSeen;

    protected Person() {
    }

    public String getId() {
        return id;
    }
}
```

Enum trạng thái:

```java
public enum PersonStatus {
    ACTIVE,
    INACTIVE,
    SUSPENDED
}
```

Repository:

```java
import org.springframework.data.neo4j.repository.Neo4jRepository;

import java.time.LocalDateTime;
import java.util.List;

public interface PersonRepository extends Neo4jRepository<Person, String> {

    long countByStatus(PersonStatus status);

    long countByStatusAndActiveTrue(PersonStatus status);

    boolean existsByEmail(String email);

    boolean existsByEmailAndActiveTrue(String email);

    long deleteByStatusAndLastSeenBefore(
        PersonStatus status,
        LocalDateTime cutoff
    );

    List<Person> removeByStatus(PersonStatus status);
}
```

`PersonRepository` kế thừa `Neo4jRepository<Person, String>`, vì entity dùng `String` làm kiểu ID do ứng dụng cấp và lưu thành property `id`. Các phương thức mới được Spring Data suy diễn từ tên và metadata của `Person`; không cần viết phần triển khai thủ công.

## 3. countBy: đếm entity thỏa điều kiện

`countBy...` tạo một count projection và trả về kiểu số. Dùng nó khi cần số lượng phù hợp với một điều kiện, chẳng hạn số người đang hoạt động hoặc số hồ sơ chờ xử lý.

```java
long inactivePeople = personRepository.countByStatus(PersonStatus.INACTIVE);

long activePeople = personRepository.countByStatusAndActiveTrue(
    PersonStatus.ACTIVE
);
```

Hai phương thức trên biểu diễn các điều kiện tương ứng:

```text
countByStatus(INACTIVE)
    -> status = INACTIVE

countByStatusAndActiveTrue(ACTIVE)
    -> status = ACTIVE AND active = true
```

Khi không có entity phù hợp, kết quả đếm là `0`. Kiểu `long` phù hợp cho số lượng có thể lớn và tránh phải xử lý `null` như khi dùng kiểu wrapper trong một số hợp đồng API.

### Kết hợp nhiều điều kiện

Predicate có thể kết hợp bằng `And` và `Or`:

```java
long countByStatusAndActiveTrue(PersonStatus status);
long countByStatusOrActiveTrue(PersonStatus status);
```

Phương thức thứ hai có nghĩa `status = ? OR active = true`. Khi dùng `Or`, hãy đọc lại tên method như một biểu thức logic để tránh vô tình đếm một tập rộng hơn dự kiến.

Một số keyword thường gặp trong predicate:

| Keyword trong tên method | Ý nghĩa điều kiện |
|---|---|
| `And`, `Or` | Kết hợp điều kiện logic |
| `Before`, `After` | So sánh thời gian hoặc giá trị có thứ tự |
| `GreaterThan`, `LessThan` | Lớn hơn hoặc nhỏ hơn |
| `GreaterThanEqual`, `LessThanEqual` | Lớn hơn/bằng hoặc nhỏ hơn/bằng |
| `Between` | Nằm trong khoảng |
| `In`, `NotIn` | Thuộc hoặc không thuộc tập giá trị |
| `IsNull`, `IsNotNull` | Kiểm tra property null hoặc không null |
| `True`, `False` | Kiểm tra property boolean |
| `Containing`, `StartingWith`, `EndingWith` | Điều kiện chuỗi tương ứng |

Keyword cụ thể được hỗ trợ phụ thuộc store và phiên bản Spring Data. Khi dùng một toán tử ít phổ biến, hãy đối chiếu danh sách keyword của phiên bản Spring Data Neo4j đang sử dụng thay vì suy ra chỉ từ parser chung.

### countBy khác count() như thế nào?

`count()` là phương thức CRUD kế thừa từ repository và đếm toàn bộ entity thuộc kiểu repository. `countByStatus(...)` chỉ đếm các entity thỏa predicate.

```java
long allPeople = personRepository.count();
long suspendedPeople = personRepository.countByStatus(PersonStatus.SUSPENDED);
```

Không cần tải danh sách entity rồi gọi `.size()` chỉ để lấy số lượng. `countBy` thể hiện trực tiếp ý định đếm và cho phép database thực hiện phép tổng hợp.

## 4. existsBy: kiểm tra có entity phù hợp hay không

`existsBy...` trả về `boolean`, phù hợp với câu hỏi chỉ cần biết có ít nhất một entity thỏa điều kiện hay không.

```java
boolean emailTaken = personRepository.existsByEmail("an@example.com");

boolean activeAccountExists = personRepository.existsByEmailAndActiveTrue(
    "an@example.com"
);
```

Ví dụ kiểm tra trước khi đăng ký email mới:

```java
public void register(String email) {
    if (personRepository.existsByEmail(email)) {
        throw new EmailAlreadyRegisteredException(email);
    }

    // Tạo và lưu Person mới theo quy tắc nghiệp vụ.
}
```

Nếu chỉ cần câu trả lời có/không, hãy dùng `existsBy` thay vì `findBy...` để tải entity hoặc `countBy...` rồi so sánh với `0`. Kết quả boolean thể hiện đúng mục tiêu của use case.

### existsById là phương thức dành riêng

`existsById(ID id)` đã được định nghĩa trong hợp đồng CRUD. Nó kiểm tra property được đánh dấu `@Id`, bất kể tên property Java thực tế là gì.

Điều này quan trọng nếu entity có trường định danh tên `key` và một property khác tên `id`:

```java
@Node("Person")
public class Person {

    @Id
    private Long key;

    private String id;
}
```

Với repository khai báo `Neo4jRepository<Person, Long>`, `existsById(10L)` kiểm tra `key` vì `key` là trường `@Id`. Nếu muốn truy vấn property `id` thông thường, hãy dùng tên method có phần mô tả trước `By` để tránh trùng với phương thức CRUD, ví dụ:

```java
boolean existsPersonById(String id);
```

Quy tắc tương tự áp dụng cho `deleteById`: đây là phương thức CRUD xóa theo ID entity, không phải query method tùy ý dựa trên property có tên `id`. Với property thông thường, có thể dùng tên như `deletePersonById(String id)`.

## 5. deleteBy và removeBy: xóa entity theo điều kiện

`deleteBy...` và `removeBy...` là hai tiền tố dùng để khai báo thao tác xóa theo predicate. Ví dụ xóa những người có trạng thái đã chọn và lần hoạt động cuối trước một mốc thời gian:

```java
long deleted = personRepository.deleteByStatusAndLastSeenBefore(
    PersonStatus.INACTIVE,
    LocalDateTime.now().minusMonths(12)
);
```

Tên method biểu diễn điều kiện:

```text
status = INACTIVE
AND lastSeen < cutoff
```

Kết quả kiểu số cho biết số entity bị xóa theo thao tác repository. Nếu không có entity phù hợp, số lượng là `0`.

`removeBy...` là cách viết khác cho derived delete. Có thể khai báo phương thức trả về collection nếu use case cần nhận các entity đã bị xóa:

```java
List<Person> removeByStatus(PersonStatus status);
```

Tài liệu Spring Data Neo4j minh họa cả `long deleteBy...` và `List<T> removeBy...`. Hãy chọn kiểu trả về theo mục tiêu: dùng `long` hoặc `void` nếu chỉ cần kết quả thao tác; chỉ trả collection khi ứng dụng thực sự cần dữ liệu entity đã xóa. Collection lớn làm tăng lượng dữ liệu phải ánh xạ và giữ trong bộ nhớ.

### Phân biệt deleteById và deleteByStatus

| Method | Loại phương thức | Phạm vi |
|---|---|---|
| `deleteById(id)` | CRUD method kế thừa | Xóa entity theo trường `@Id` |
| `deleteByStatus(status)` | Derived delete query | Xóa các entity có property `status` thỏa điều kiện |
| `removeByStatus(status)` | Derived delete query | Cùng mục tiêu predicate, có thể trả các entity đã xóa |

Không gọi `deleteByStatus` khi mục tiêu là xóa một entity theo ID. Ngược lại, không dùng `deleteById` để truy vấn một property khác chỉ vì property đó có tên `id`.

## 6. Xóa node khác với xóa relationship

Một derived delete method được xây dựng quanh domain entity của repository. Ví dụ `deleteByStatus` tác động đến các entity `Person` thỏa predicate. Nếu mục tiêu chỉ là gỡ một cạnh `KNOWS` giữa hai người, đó là một thao tác khác: node ở hai đầu vẫn phải tồn tại.

Cypher minh họa xóa relationship:

```cypher
MATCH (p:Person {id: $personId})-[r:KNOWS]->(friend:Person)
WHERE friend.id = $friendId
DELETE r;
```

Cypher minh họa xóa node cùng các relationship gắn trực tiếp với node đó:

```cypher
MATCH (p:Person {id: $personId})
DETACH DELETE p;
```

`DELETE r` chỉ xóa relationship được match. `DETACH DELETE p` xóa node `p` cùng các relationship kề với nó. Khi dùng repository để xóa entity, cần hiểu quy tắc xóa graph của Spring Data Neo4j và mô hình domain; không mặc định thao tác xóa một entity đồng nghĩa với xóa toàn bộ node ở xa có thể đi tới từ entity đó.

Nếu yêu cầu nghiệp vụ là xóa relationship theo điều kiện, hoặc cần kiểm soát chính xác pattern Cypher được match, hãy dùng truy vấn Cypher tùy chỉnh qua `@Query` hoặc API truy vấn phù hợp. Derived delete không thay thế một thao tác xóa cạnh được xác định riêng.

## 7. Đặt thao tác xóa trong transaction và kiểm soát phạm vi

Xóa theo điều kiện có thể ảnh hưởng đến nhiều node. Hãy đặt thao tác vào service và xác định transaction theo ranh giới nghiệp vụ:

```java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class PersonMaintenanceService {

    private final PersonRepository people;

    public PersonMaintenanceService(PersonRepository people) {
        this.people = people;
    }

    @Transactional
    public long removeInactivePeople(LocalDateTime cutoff) {
        return people.deleteByStatusAndLastSeenBefore(
            PersonStatus.INACTIVE,
            cutoff
        );
    }
}
```

Trong ví dụ, transaction bao quanh use case xóa. Nếu nghiệp vụ gồm nhiều thao tác dữ liệu phải thành công hoặc rollback cùng nhau, hãy thực hiện chúng trong cùng transaction được cấu hình cho Spring Data Neo4j.

Trước một thao tác xóa diện rộng, có thể dùng count method với cùng predicate để xem quy mô dự kiến:

```java
long candidates = personRepository.countByStatusAndLastSeenBefore(
    PersonStatus.INACTIVE,
    cutoff
);
```

Phép đếm này hữu ích cho màn hình xác nhận hoặc log quản trị. Nó chỉ phản ánh trạng thái dữ liệu tại thời điểm truy vấn; nếu có ghi đồng thời, số đếm và số entity thực tế bị xóa ở lần gọi sau có thể khác nhau. Nếu yêu cầu cần khóa hoặc bảo đảm nghiêm ngặt trước thay đổi đồng thời, hãy thiết kế transaction và chiến lược đồng bộ phù hợp.

Các bước kiểm soát thực tế:

1. Xác định rõ predicate và tham số trước khi chạy.
2. Dùng `countBy...` với cùng điều kiện để ước lượng phạm vi.
3. Xác nhận tenant, trạng thái hoặc mốc thời gian nếu chúng là ranh giới dữ liệu.
4. Chọn kiểu trả về nhỏ nhất đáp ứng use case.
5. Đặt thao tác cùng các cập nhật liên quan trong transaction phù hợp.
6. Ghi log số lượng entity bị tác động và định danh điều kiện cần thiết để truy vết.

## 8. Khi nào chuyển sang Cypher tùy chỉnh?

Derived query phù hợp với điều kiện property có thể diễn đạt rõ bằng tên method. Khi logic vượt quá khả năng của parser hoặc cần điều khiển graph pattern cụ thể, hãy viết Cypher.

Các tình huống nên cân nhắc `@Query`:

- Xóa relationship giữa hai node nhưng giữ nguyên hai node.
- Điều kiện phụ thuộc vào nhiều nhánh relationship hoặc pattern đồ thị phức tạp.
- Cần `count(DISTINCT ...)`, aggregation hoặc phép tính không thể diễn đạt rõ qua tên method.
- Cần kiểm soát chính xác node/relationship nào được match và trả về.
- Tên method quá dài, khó đọc hoặc dễ hiểu nhầm thứ tự `And`/`Or`.

Ví dụ truy vấn kiểm tra và đếm số người có relationship `KNOWS` đi ra từ một người:

```java
import org.springframework.data.neo4j.repository.query.Query;
import org.springframework.data.repository.query.Param;

@Query("""
    MATCH (p:Person {id: $personId})-[:KNOWS]->(friend:Person)
    RETURN count(DISTINCT friend)
    """)
    long countKnownPeople(@Param("personId") String personId);
```

Cypher làm rõ pattern đồ thị và phép đếm node đích duy nhất. Khi truy vấn tùy chỉnh ghi hoặc xóa dữ liệu, hãy kiểm tra điều kiện `MATCH` trước trên dữ liệu thử nghiệm và đặt transaction đúng ranh giới nghiệp vụ.

## 9. Những lỗi thường gặp

| Biểu hiện | Nguyên nhân | Cách xử lý |
|---|---|---|
| Repository không khởi tạo được | Tên property trong predicate không tồn tại hoặc viết sai | Đối chiếu chính xác với property của entity và kiểu dữ liệu |
| `countBy...` trả số lớn hơn dự kiến | Predicate dùng `Or` làm mở rộng tập kết quả hoặc truy vấn quan hệ tạo nhiều đường match | Kiểm tra logic điều kiện; dùng Cypher với `count(DISTINCT ...)` nếu cần đếm node duy nhất |
| `existsBy...` không trả về boolean | Kiểu trả về không khớp với exists projection | Dùng `boolean` hoặc `Boolean` |
| Dùng `existsById` nhưng kiểm tra nhầm property | Nhầm phương thức CRUD dành riêng với derived query theo property tên `id` | Dùng `existsPersonById` hoặc tên khác tránh trùng chữ ký reserved |
| `deleteBy...` xóa nhiều dữ liệu hơn dự kiến | Predicate thiếu điều kiện hoặc dùng `Or` không đúng | Chạy count cùng predicate và rà lại từng tham số trước khi xóa |
| `deleteBy...` trả về kiểu không phù hợp | Khai báo kiểu kết quả không đúng với hợp đồng derived delete | Chọn `long`, `void` hoặc collection entity theo nhu cầu và phiên bản Spring Data |
| Muốn xóa một cạnh nhưng node cũng bị tác động | Dùng delete entity trong khi yêu cầu thực tế là xóa relationship | Viết Cypher match relationship rồi `DELETE r` |
| Xóa nhiều entity gây tốn tài nguyên | Trả về collection lớn hoặc thao tác trên phạm vi quá rộng | Chỉ trả số lượng khi có thể; giới hạn phạm vi và đánh giá batch/transaction |
| Kết quả count và số xóa thực tế khác nhau | Dữ liệu thay đổi giữa hai lần gọi | Xem count là số liệu tại thời điểm truy vấn, thiết kế đồng bộ nếu cần bảo đảm mạnh hơn |

## 10. Tự kiểm tra

1. Phần nào trong `countByStatusAndActiveTrue` là subject và phần nào là predicate?
2. Vì sao `countBy...` phù hợp hơn tải toàn bộ entity rồi gọi `.size()`?
3. Khi chỉ cần biết một email đã tồn tại hay chưa, nên dùng `existsByEmail` hay `countByEmail`?
4. `existsById` kiểm tra property tên `id` bất kỳ hay trường được đánh dấu `@Id`?
5. Khác biệt giữa `deleteByStatus` và `deleteById` là gì?
6. Khi nào nên trả `List<Person>` từ `removeByStatus` thay vì chỉ trả số lượng?
7. Vì sao xóa relationship `KNOWS` cần một Cypher pattern nhắm vào relationship thay vì derived delete của `Person`?
8. Vì sao count dùng để xem trước không bảo đảm số entity bị xóa sẽ giữ nguyên nếu có ghi đồng thời?

`countBy` trả lời câu hỏi có bao nhiêu entity thỏa điều kiện; `existsBy` trả lời có hay không; `deleteBy` và `removeBy` thực hiện xóa theo predicate. Hãy dùng đúng subject, đúng kiểu trả về và điều kiện đủ hẹp. Khi thao tác liên quan đến cấu trúc relationship hoặc graph pattern phức tạp, chuyển sang Cypher tường minh để kiểm soát chính xác phần đồ thị bị tác động.

## Tài liệu tham khảo

- [Spring Data Neo4j — Core concepts: derived count and delete queries](https://docs.spring.io/spring-data/neo4j/reference/repositories/core-concepts.html)
- [Spring Data Neo4j — Defining Query Methods](https://docs.spring.io/spring-data/neo4j/reference/repositories/query-methods-details.html)
- [Spring Data Neo4j — Repository query keywords](https://docs.spring.io/spring-data/neo4j/reference/repositories/query-keywords-reference.html)
- [Neo4j Cypher Manual — DELETE](https://neo4j.com/docs/cypher-manual/current/clauses/delete/)
