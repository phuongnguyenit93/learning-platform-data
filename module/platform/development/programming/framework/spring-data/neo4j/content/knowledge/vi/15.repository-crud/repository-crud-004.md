# findById, findAllById và findAll

Spring Data Neo4j cung cấp các phương thức đọc cơ bản thông qua `Neo4jRepository`, trong đó `findById`, `findAllById` và `findAll` là ba cách lấy entity thường dùng nhất. Chúng khác nhau ở số lượng định danh đầu vào, hình dạng kết quả và lượng dữ liệu có thể phải tải từ Neo4j.

Trong module `SPRING_DATA_NEO4J`, repository là điểm truy cập tầng dữ liệu cho các node entity. Hiểu đúng hợp đồng của ba phương thức giúp xử lý trường hợp không tìm thấy dữ liệu, đọc nhiều entity theo lô và tránh tải toàn bộ graph ngoài nhu cầu của use case.

## 1. Khai báo repository và ID của entity

Các phương thức CRUD nhận diện entity thông qua trường được đánh dấu `@Id`. Kiểu ID trong khai báo repository phải khớp với kiểu của trường đó.

Ví dụ dùng ID do ứng dụng cấp và lưu thành property `id` trên node:

```java
import org.springframework.data.neo4j.core.schema.Id;
import org.springframework.data.neo4j.core.schema.Node;
import org.springframework.data.neo4j.core.schema.Relationship;

import java.util.HashSet;
import java.util.Set;

@Node("Person")
public class Person {

    @Id
    private String id;

    private String name;

    @Relationship(type = "KNOWS")
    private Set<Person> connections = new HashSet<>();

    protected Person() {
    }

    public Person(String id, String name) {
        this.id = id;
        this.name = name;
    }

    public String getId() {
        return id;
    }

    public String getName() {
        return name;
    }

    public void addRelation(Person target) {
        connections.add(target);
    }
}
```

Repository tương ứng:

```java
import org.springframework.data.neo4j.repository.Neo4jRepository;

public interface PersonRepository extends Neo4jRepository<Person, String> {
}
```

Tham số kiểu thứ nhất là entity `Person`; tham số kiểu thứ hai là kiểu ID `String`. Khi dùng ID nội bộ do Neo4j cấp, entity thường khai báo `@Id @GeneratedValue` với kiểu phù hợp, chẳng hạn `Long`, và repository khi đó phải khai báo `Neo4jRepository<Person, Long>`. Trong cả hai trường hợp, các phương thức dưới đây làm việc với ID mà Spring Data Neo4j ánh xạ cho entity.

Vì `id` là khóa do ứng dụng cấp, database nên bảo vệ tính duy nhất bằng constraint:

```cypher
CREATE CONSTRAINT person_id_unique IF NOT EXISTS
FOR (p:Person)
REQUIRE p.id IS UNIQUE;
```

`findById` không phải truy vấn theo một property bất kỳ. Nếu muốn tìm theo email, tên hoặc mã ngoài không phải trường `@Id`, hãy khai báo phương thức truy vấn theo property hoặc viết Cypher bằng `@Query`.

## 2. findById: tìm một entity theo ID

`findById(ID id)` nhận một ID và trả về `Optional<T>`:

```java
import java.util.Optional;

Optional<Person> result = personRepository.findById("person-001");
```

Kết quả có hai trạng thái:

- Có node phù hợp: `Optional` chứa entity `Person` đã được ánh xạ.
- Không có node phù hợp: trả về `Optional.empty()`.

Không nên giả định ID luôn tồn tại hoặc gọi `get()` mà chưa kiểm tra. Có thể xử lý rõ ràng bằng `orElseThrow`:

```java
public Person getRequiredPerson(String id) {
    return personRepository.findById(id)
        .orElseThrow(() -> new PersonNotFoundException(id));
}
```

Hoặc nếu trường hợp không tồn tại là bình thường trong use case:

```java
public Optional<Person> findPerson(String id) {
    return personRepository.findById(id);
}
```

ID truyền vào không được `null`; hãy xác thực dữ liệu đầu vào trước khi gọi repository. Với ID do ứng dụng quản lý, cần bảo đảm property đó ổn định và có unique constraint phù hợp trong Neo4j để một ID chỉ nhận diện một node theo quy tắc domain.

### Khi nào dùng findById?

Phương thức này phù hợp khi ứng dụng đã biết ID của một entity, ví dụ:

- Mở trang chi tiết người dùng từ URL chứa ID.
- Kiểm tra một node trước khi cập nhật hoặc tạo relationship.
- Kiểm tra entity có tồn tại trước khi thực hiện một quy tắc nghiệp vụ.
- Lấy một aggregate root để xử lý trong service.

Ví dụ kiểm tra trước khi liên kết hai người:

```java
Person source = personRepository.findById(sourceId)
    .orElseThrow(() -> new PersonNotFoundException(sourceId));

Person target = personRepository.findById(targetId)
    .orElseThrow(() -> new PersonNotFoundException(targetId));

source.addRelation(target);
personRepository.save(source);
```

Đoạn mã minh họa cách xử lý hai ID đầu vào rồi thêm relationship `KNOWS` từ `source` đến `target`. Nếu use case cần lấy nhiều entity theo danh sách ID, `findAllById` thường phù hợp hơn việc gọi `findById` lặp lại từng lần.

## 3. findAllById: tìm nhiều entity theo danh sách ID

`findAllById(Iterable<ID> ids)` nhận một `Iterable` các ID và trả về các entity tìm thấy:

```java
List<String> ids = List.of("person-001", "person-002", "person-003");

Iterable<Person> people = personRepository.findAllById(ids);
```

Phương thức này hữu ích khi một use case đã có danh sách ID, chẳng hạn danh sách thành viên của một nhóm, các node được chọn từ một sự kiện hoặc những người tham gia một phiên làm việc.

### Xử lý ID không tồn tại

Kết quả có thể ít phần tử hơn số ID đầu vào. Những ID không tìm thấy không tạo ra placeholder `null` trong kết quả; chúng đơn giản không có entity tương ứng.

```java
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.function.Function;
import java.util.stream.Collectors;

List<String> requestedIds = List.of(
    "person-001",
    "person-missing",
    "person-003"
);

List<Person> found = new ArrayList<>();
personRepository.findAllById(requestedIds).forEach(found::add);

System.out.println("Yêu cầu: " + requestedIds.size());
System.out.println("Tìm thấy: " + found.size());
```

Không nên giả định `found.size()` luôn bằng `requestedIds.size()`. Nếu nghiệp vụ cần thông báo chính xác ID nào bị thiếu, hãy đối chiếu tập ID yêu cầu với ID của các entity trả về:

```java
Set<String> foundIds = found.stream()
    .map(Person::getId)
    .collect(Collectors.toSet());

List<String> missingIds = requestedIds.stream()
    .filter(id -> !foundIds.contains(id))
    .toList();
```

Đoạn ví dụ dùng `Stream.toList()` của Java 16 trở lên. Với phiên bản Java cũ hơn, có thể thu kết quả vào `ArrayList` bằng `Collectors.toCollection(ArrayList::new)`.

### Không dựa vào thứ tự đầu vào

Hợp đồng của `findAllById` không bảo đảm thứ tự các entity trả về trùng với thứ tự ID đầu vào. Ví dụ, dù đầu vào là:

```text
[person-003, person-001, person-002]
```

kết quả không được bảo đảm theo thứ tự đó. Không nên dùng vị trí phần tử trong kết quả để suy ra vị trí ID tương ứng trong danh sách ban đầu. Nếu cần giữ thứ tự yêu cầu, hãy lập map theo ID rồi dựng lại danh sách:

```java
Map<String, Person> peopleById = found.stream()
    .collect(Collectors.toMap(
        Person::getId,
        Function.identity(),
        (first, duplicate) -> first
    ));

List<Person> ordered = new ArrayList<>();
for (String id : requestedIds) {
    Person person = peopleById.get(id);
    if (person != null) {
        ordered.add(person);
    }
}
```

Cách này giữ thứ tự của ID đầu vào và bỏ qua ID không tồn tại. Nếu danh sách đầu vào có ID lặp, vòng lặp cũng sẽ thêm entity tương ứng theo số lần ID xuất hiện; hãy quyết định rõ nghiệp vụ có cho phép lặp hay cần loại trùng trước khi gọi repository.

### Dùng findAllById thay cho nhiều lần findById

Nếu đã có một danh sách ID, gọi `findAllById` thường diễn đạt rõ mục đích đọc theo lô và giúp tránh viết vòng lặp gọi repository cho từng ID:

```java
// Không cần gọi repository một lần cho từng ID.
for (String id : requestedIds) {
    personRepository.findById(id).ifPresent(found::add);
}

// Có thể lấy theo lô bằng một lời gọi repository.
personRepository.findAllById(requestedIds).forEach(found::add);
```

Không nên coi đây là bảo đảm tuyệt đối về số round-trip hoặc kế hoạch thực thi của mọi phiên bản. Nếu hiệu năng quan trọng, hãy đo truy vấn thực tế, kích thước danh sách ID và graph được ánh xạ. Với danh sách rất lớn, chia thành các batch vừa phải để kiểm soát kích thước tham số, bộ nhớ và lượng dữ liệu trả về.

## 4. findAll: lấy toàn bộ entity

`findAll()` không nhận tham số và trả về tất cả entity thuộc kiểu repository:

```java
Iterable<Person> people = personRepository.findAll();

for (Person person : people) {
    System.out.println(person.getId() + " - " + person.getName());
}
```

Với repository `PersonRepository`, phương thức này tìm các node phù hợp với entity `Person` theo metadata mapping. Nó không giới hạn kết quả theo người dùng hiện tại, nhóm cụ thể hay điều kiện nghiệp vụ nào nếu không có truy vấn bổ sung.

`findAll()` phù hợp khi:

- Dữ liệu có quy mô nhỏ và use case thực sự cần toàn bộ entity.
- Tác vụ quản trị hoặc đồng bộ cần quét tất cả entity.
- Công việc nền cần xử lý toàn bộ tập dữ liệu và đã có chiến lược kiểm soát tài nguyên.

Không nên dùng `findAll()` cho màn hình danh sách có thể tăng trưởng không giới hạn hoặc API chỉ cần một phần dữ liệu. Việc lấy toàn bộ entity có thể làm tăng bộ nhớ JVM, lượng dữ liệu truyền giữa ứng dụng và Neo4j, chi phí ánh xạ node/relationship và thời gian phản hồi.

### findAll không bảo đảm thứ tự

Không dựa vào thứ tự tự nhiên của kết quả `findAll()`. Nếu giao diện cần sắp xếp theo tên, thời gian tạo hoặc ID, hãy chỉ định thứ tự trong truy vấn. Với Cypher tùy chỉnh, ví dụ:

```java
import org.springframework.data.neo4j.repository.query.Query;
import org.springframework.data.repository.query.Param;

import java.util.List;

@Query("""
    MATCH (p:Person)
    RETURN p
    ORDER BY p.name, p.id
    SKIP $skip
    LIMIT $limit
    """)
List<Person> findPeoplePage(
    @Param("skip") long skip,
    @Param("limit") long limit
);
```

`ORDER BY` tạo thứ tự xác định; thêm ID làm tiêu chí phụ giúp các entity có cùng tên vẫn có thứ tự ổn định. `SKIP` và `LIMIT` giới hạn số node trả về. Với tập dữ liệu thay đổi thường xuyên, phân trang offset có thể dịch chuyển kết quả giữa các lần gọi; các use case cần phân trang ổn định trên dữ liệu lớn có thể cân nhắc keyset pagination dựa trên khóa sắp xếp.

### Giảm dữ liệu cần đọc

Nếu màn hình chỉ cần ID và tên, không nhất thiết trả về entity đầy đủ. Có thể dùng projection để trả đúng trường cần thiết:

```java
public interface PersonSummary {
    String getId();
    String getName();
}
```

```java
@Query("""
    MATCH (p:Person)
    RETURN p.id AS id, p.name AS name
    ORDER BY p.name, p.id
    """)
List<PersonSummary> findAllSummaries();
```

Projection giúp giới hạn dữ liệu ứng dụng nhận và ánh xạ. Khi dùng custom query, tên alias trong `RETURN` phải khớp với property mà projection khai báo.

## 5. So sánh ba phương thức

| Phương thức | Đầu vào | Kết quả | Khi dùng |
|---|---|---|---|
| `findById(id)` | Một ID | `Optional<T>` | Tìm một entity và xử lý rõ trường hợp không tồn tại |
| `findAllById(ids)` | Một `Iterable<ID>` | `Iterable<T>` (hoặc kiểu collection cụ thể tùy API Spring Data đang dùng) | Đọc theo lô từ danh sách ID đã biết |
| `findAll()` | Không có | `Iterable<T>` (hoặc kiểu collection cụ thể tùy API Spring Data đang dùng) | Đọc toàn bộ entity khi quy mô và use case cho phép |

Các điểm cần nhớ:

- `findById` trả về `Optional`, không trả `null` để biểu diễn trường hợp không tìm thấy.
- `findAllById` có thể trả ít entity hơn số ID yêu cầu; không bảo đảm thứ tự đầu ra theo thứ tự đầu vào.
- `findAll` lấy toàn bộ entity của kiểu repository và không tự áp dụng điều kiện lọc hay sắp xếp nghiệp vụ.
- Cả ba phương thức làm việc với ID và metadata của entity; chúng không thay thế truy vấn theo property khác.
- Entity có relationship được ánh xạ có thể kéo theo chi phí đọc graph lớn hơn chỉ một node. Hãy xem xét kiểu trả về, mapping và truy vấn khi hiệu năng là yêu cầu quan trọng.

## 6. Ví dụ service kết hợp ba cách đọc

Service có thể đóng gói cách xử lý kết quả để controller không phải biết chi tiết repository:

```java
import org.springframework.stereotype.Service;

import java.util.ArrayList;
import java.util.List;
import java.util.Optional;

@Service
public class PersonQueryService {

    private final PersonRepository people;

    public PersonQueryService(PersonRepository people) {
        this.people = people;
    }

    public Optional<Person> findOne(String id) {
        return people.findById(id);
    }

    public List<Person> findMany(List<String> ids) {
        List<Person> result = new ArrayList<>();
        people.findAllById(ids).forEach(result::add);
        return result;
    }

    public List<Person> findEveryPerson() {
        List<Person> result = new ArrayList<>();
        people.findAll().forEach(result::add);
        return result;
    }
}
```

Service trên chuyển kết quả dạng `Iterable` thành `List` để tầng gọi dễ sử dụng. Với tập dữ liệu lớn, không nên chuyển toàn bộ kết quả `findAll()` thành `List` nếu use case không cần giữ tất cả trong bộ nhớ; hãy dùng truy vấn có giới hạn, projection hoặc xử lý theo batch.

## 7. Những lỗi thường gặp

| Biểu hiện | Nguyên nhân | Cách xử lý |
|---|---|---|
| `findById` không tìm thấy dù node tồn tại | Truyền nhầm kiểu/giá trị ID hoặc nhầm ID property với `elementId` hay ID nội bộ | Kiểm tra `@Id`, generator và kiểu ID trong `Neo4jRepository` |
| Phát sinh lỗi khi gọi `findById(null)` | ID đầu vào không hợp lệ | Kiểm tra null trước khi gọi repository |
| Code giả định luôn có kết quả | Không xử lý `Optional.empty()` | Dùng `orElse`, `orElseGet` hoặc `orElseThrow` theo nghiệp vụ |
| `findAllById` trả ít phần tử hơn đầu vào | Một số ID không tồn tại | Đối chiếu ID yêu cầu với ID tìm thấy nếu cần báo phần tử thiếu |
| Entity trả về không theo thứ tự ID đầu vào | Hợp đồng phương thức không bảo đảm thứ tự | Dựng lại thứ tự bằng map theo ID hoặc dùng truy vấn có `ORDER BY` phù hợp |
| `findAll()` chậm hoặc tốn bộ nhớ | Tập node lớn hoặc mapping kéo theo nhiều relationship | Dùng truy vấn có điều kiện, `SKIP`/`LIMIT`, projection hoặc xử lý batch |
| Kết quả hiển thị thay đổi thứ tự giữa các lần gọi | Không có `ORDER BY` | Chỉ định thứ tự rõ ràng và thêm khóa phụ duy nhất |
| Tìm theo email bằng `findById` không đúng | Email không phải trường ID được ánh xạ | Dùng query method theo property hoặc `@Query` |

## 8. Tự kiểm tra

1. Vì sao `findById` trả về `Optional<T>` thay vì một entity có thể `null`?
2. Nếu truyền năm ID vào `findAllById` nhưng chỉ ba ID tồn tại, ứng dụng cần xử lý kết quả như thế nào?
3. Có thể giả định `findAllById` trả kết quả theo đúng thứ tự danh sách ID đầu vào không? Vì sao?
4. `findAll()` có tự sắp xếp theo tên hoặc ID không?
5. Khi repository dùng `Neo4jRepository<Person, Long>`, kiểu ID đó phải tương ứng với thành phần nào trong entity?
6. Vì sao projection và truy vấn có giới hạn phù hợp hơn `findAll()` cho màn hình danh sách lớn?
7. Khi cần tìm `Person` theo email, nên dùng `findById` hay một query method khác?

Ba phương thức đọc cơ bản có phạm vi rõ ràng: `findById` lấy một entity theo ID, `findAllById` lấy các entity ứng với một tập ID, còn `findAll` lấy toàn bộ entity thuộc repository. Hãy xử lý `Optional`, ID bị thiếu và thứ tự kết quả một cách tường minh; đồng thời kiểm soát lượng dữ liệu graph được tải để repository CRUD hoạt động phù hợp với quy mô ứng dụng.
