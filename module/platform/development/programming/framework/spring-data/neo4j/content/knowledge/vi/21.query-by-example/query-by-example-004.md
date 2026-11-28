# Xử lý null, kiểu nguyên thủy và bỏ qua thuộc tính

Query by Example (QBE) trong Spring Data Neo4j cho phép tạo điều kiện tìm kiếm từ một entity mẫu (probe) thay vì viết riêng một truy vấn cho mọi tổ hợp bộ lọc. Tuy nhiên, kết quả phụ thuộc trực tiếp vào giá trị của từng thuộc tính trong probe. Thuộc tính `null`, thuộc tính kiểu nguyên thủy và thuộc tính được khai báo bỏ qua có ý nghĩa khác nhau khi Spring Data tạo truy vấn.

Nắm rõ các quy tắc này giúp tránh những lỗi thường gặp như vô tình lọc theo `0`, `false`, tìm các node có property null ngoài ý muốn hoặc khiến điều kiện tìm kiếm quá chặt. Trong ứng dụng dùng Spring Data Neo4j (SDN), ta cấu hình các quy tắc đó bằng `ExampleMatcher` rồi truyền `Example` vào repository.

## 1. Probe và ExampleMatcher

Probe là một instance của entity chứa các giá trị muốn dùng làm điều kiện tìm kiếm. `ExampleMatcher` mô tả cách xử lý những giá trị đó: kết hợp điều kiện theo AND hay OR, xử lý chuỗi, bao gồm null và bỏ qua thuộc tính nào.

Ví dụ entity `Person`:

```java
import org.springframework.data.annotation.Id;
import org.springframework.data.neo4j.core.schema.Node;

@Node("Person")
public class Person {

    @Id
    private String personId;

    private String name;
    private String city;
    private Integer age;
    private Boolean active;
    private Integer score;

    protected Person() {
    }

    public String getPersonId() { return personId; }
    public void setPersonId(String personId) { this.personId = personId; }
    public String getName() { return name; }
    public void setName(String name) { this.name = name; }
    public String getCity() { return city; }
    public void setCity(String city) { this.city = city; }
    public Integer getAge() { return age; }
    public void setAge(Integer age) { this.age = age; }
    public Boolean getActive() { return active; }
    public void setActive(Boolean active) { this.active = active; }
    public Integer getScore() { return score; }
    public void setScore(Integer score) { this.score = score; }
}
```

Repository cần kế thừa `Neo4jRepository` để làm việc với entity và hỗ trợ các thao tác QBE:

```java
import org.springframework.data.neo4j.repository.Neo4jRepository;

public interface PersonRepository extends Neo4jRepository<Person, String> {
}
```

Tạo probe và Example:

```java
import java.util.List;

import org.springframework.data.domain.Example;
import org.springframework.data.domain.ExampleMatcher;

Person probe = new Person();
probe.setCity("Da Nang");
probe.setActive(true);

ExampleMatcher matcher = ExampleMatcher.matchingAll()
        .withIgnorePaths("personId", "score");

Example<Person> example = Example.of(probe, matcher);
List<Person> people = personRepository.findAll(example);
```

Trong ví dụ, `city` và `active` là các điều kiện tìm kiếm. `personId` và `score` được bỏ qua. Các thuộc tính tham chiếu khác đang là `null` cũng được bỏ qua theo mặc định.

## 2. Null được xử lý thế nào?

Mặc định, QBE bỏ qua các thuộc tính tham chiếu có giá trị `null` trong probe. Vì vậy, một field không được gán không tự động trở thành điều kiện `IS NULL`.

Ví dụ:

```java
import java.util.List;

import org.springframework.data.domain.Example;

Person probe = new Person();
probe.setCity("Da Nang");
probe.setAge(30);

Example<Person> example = Example.of(probe);
List<Person> people = personRepository.findAll(example);
```

Các điều kiện có hiệu lực là `city = 'Da Nang'` và `age = 30`. Các thuộc tính tham chiếu `name` và `active` đang null được bỏ qua. Do đó, kết quả có thể chứa người ở Đà Nẵng, 30 tuổi với nhiều giá trị `name` và `active` khác nhau.

Đây là hành vi hữu ích cho form tìm kiếm: người dùng chỉ nhập những trường muốn lọc, các trường để trống không tham gia truy vấn.

### Bao gồm null bằng withIncludeNullValues()

Nếu nghiệp vụ cần tìm node mà một property thực sự chưa có giá trị, có thể yêu cầu matcher bao gồm null:

```java
import java.util.List;

import org.springframework.data.domain.Example;
import org.springframework.data.domain.ExampleMatcher;

Person probe = new Person();
probe.setCity("Da Nang");
probe.setName(null);

ExampleMatcher matcher = ExampleMatcher.matchingAll()
        .withIncludeNullValues()
        .withIgnorePaths("personId", "age", "active", "score");

Example<Person> example = Example.of(probe, matcher);
List<Person> people = personRepository.findAll(example);
```

Với cấu hình này, `city` được so khớp với giá trị đã cho và `name` được dùng làm điều kiện null. Các thuộc tính còn lại được bỏ qua tường minh để tránh vô tình đưa null của chúng vào điều kiện.

Trong graph, property không tồn tại và property được gỡ bằng `REMOVE` đều được xem là không có giá trị khi kiểm tra null. Vì vậy, điều kiện null trong QBE phù hợp để tìm node chưa có property tương ứng.

`withIncludeNullValues()` tác động đến tất cả thuộc tính tham chiếu null không bị bỏ qua trong probe. Nếu bật tùy chọn này mà không kiểm tra các field khác, điều kiện tìm kiếm có thể trở nên quá chặt. Hãy dùng `withIgnorePaths(...)` cho những thuộc tính null chỉ đơn giản là không được người dùng cung cấp.

## 3. Phân biệt null, chuỗi rỗng và giá trị mặc định

Null không giống chuỗi rỗng hoặc số 0. Với mặc định bỏ qua null, một thuộc tính `String` có giá trị `null` không tham gia điều kiện; nhưng `""` là một giá trị chuỗi có thật và có thể được dùng làm điều kiện so khớp.

Tương tự:

| Giá trị trong probe | Kiểu thuộc tính | Hành vi mặc định |
|---|---|---|
| `null` | `String`, `Integer`, `Boolean` | Bỏ qua thuộc tính |
| `""` | `String` | Là giá trị chuỗi, được so khớp |
| `0` | `Integer` hoặc `int` | Là giá trị, được so khớp |
| `false` | `Boolean` hoặc `boolean` | Là giá trị, được so khớp |

Nếu form web dùng chuỗi rỗng để biểu diễn “không nhập”, tầng chuyển đổi request nên chuẩn hóa chuỗi rỗng thành null trước khi tạo probe, hoặc chủ động bỏ qua field đó trong matcher. Không nên kỳ vọng QBE tự hiểu `""` là null.

## 4. Kiểu nguyên thủy luôn có giá trị mặc định

Java primitive không thể chứa null. Khi tạo object mới, các field nguyên thủy được gán giá trị mặc định:

- `int`, `long`, `short`, `byte` có giá trị `0`.
- `boolean` có giá trị `false`.
- `double` và `float` có giá trị `0.0`.
- `char` có giá trị ký tự `\u0000`.

QBE nhìn thấy những giá trị này như giá trị thực trong probe, không thể biết chúng là do người dùng nhập hay do Java tự khởi tạo. Vì vậy, một field `int age` chưa được gán vẫn có thể tạo điều kiện tìm `age = 0`.

Ví dụ dễ gây kết quả sai:

```java
import org.springframework.data.annotation.Id;
import org.springframework.data.neo4j.core.schema.Node;

@Node("LegacyPerson")
public class LegacyPerson {

    @Id
    private String personId;

    private int age;
    private boolean active;
}
```

```java
import org.springframework.data.neo4j.repository.Neo4jRepository;

public interface LegacyPersonRepository
        extends Neo4jRepository<LegacyPerson, String> {
}
```

```java
import java.util.List;

import org.springframework.data.domain.Example;

LegacyPerson probe = new LegacyPerson();
Example<LegacyPerson> example = Example.of(probe);
List<LegacyPerson> people = legacyPersonRepository.findAll(example);
```

Nếu dùng một entity có các field primitive tương tự làm probe, `age` mặc định bằng `0` và `active` mặc định bằng `false`. Hai giá trị này có thể được đưa vào điều kiện dù người dùng chưa chọn tuổi hoặc trạng thái.

### Ưu tiên wrapper cho bộ lọc tùy chọn

Nếu một thuộc tính có thể không được cung cấp trong form tìm kiếm, hãy dùng wrapper như `Integer`, `Long`, `Boolean` thay vì primitive:

```java
private Integer age;
private Boolean active;
```

Wrapper có thể giữ null, nên mặc định QBE bỏ qua field chưa được gán. Khi người dùng thực sự chọn `age = 0` hoặc `active = false`, ứng dụng có thể gán giá trị đó rõ ràng vào probe.

Không nhất thiết phải đổi kiểu của entity miền nghiệp vụ chỉ vì QBE. Nếu thuộc tính bắt buộc trong domain và cần giữ primitive, có thể giữ nguyên entity và cấu hình `withIgnorePaths("age", "active")` cho các trường hợp không muốn dùng giá trị mặc định làm điều kiện. Một DTO tìm kiếm riêng với wrapper types cũng là lựa chọn phù hợp khi form có nhiều trạng thái đầu vào.

## 5. Bỏ qua thuộc tính bằng withIgnorePaths()

`withIgnorePaths(...)` yêu cầu matcher không sử dụng các thuộc tính được chỉ định khi tạo điều kiện từ probe. Tên truyền vào là tên property của entity Java, không phải tên label hoặc relationship type trong Neo4j.

Ví dụ, bỏ qua định danh và điểm số:

```java
ExampleMatcher matcher = ExampleMatcher.matchingAll()
        .withIgnorePaths("personId", "score");
```

Khi đó, dù probe có `personId` hoặc `score` được gán giá trị, các field này không tham gia điều kiện QBE.

Điều này hữu ích trong các trường hợp:

1. Bỏ qua ID vì ID của probe không phải điều kiện tìm kiếm.
2. Bỏ qua field primitive có giá trị mặc định nhưng không được người dùng chọn.
3. Bỏ qua field kỹ thuật hoặc field chỉ phục vụ ứng dụng.
4. Dùng một probe chung cho nhiều use case nhưng mỗi use case có tập điều kiện khác nhau.

Matcher có tính bất biến: các phương thức `with...` trả về một matcher mới. Hãy giữ kết quả trả về thay vì gọi phương thức rồi bỏ qua giá trị:

```java
ExampleMatcher base = ExampleMatcher.matchingAll();
ExampleMatcher withoutScore = base.withIgnorePaths("score");
```

Trong ví dụ, `base` không bị thay đổi; `withoutScore` là matcher mới có thêm quy tắc bỏ qua `score`.

## 6. Kết hợp include-null và ignore-paths

Hai tùy chọn có thể được dùng cùng nhau. `withIncludeNullValues()` đưa các field tham chiếu null vào điều kiện; `withIgnorePaths(...)` loại bỏ những field không muốn xét, kể cả khi chúng có giá trị.

```java
import java.util.List;

import org.springframework.data.domain.Example;
import org.springframework.data.domain.ExampleMatcher;

Person probe = new Person();
probe.setCity("Da Nang");
probe.setName(null);
probe.setActive(false);

ExampleMatcher matcher = ExampleMatcher.matchingAll()
        .withIncludeNullValues()
        .withIgnorePaths("personId", "age", "score");

Example<Person> example = Example.of(probe, matcher);
```

Ý nghĩa:

- `city` phải bằng `Da Nang`.
- `name` phải null hoặc không có property.
- `active` phải bằng `false`; đây là giá trị Boolean được gán tường minh, không phải null.
- `personId`, `age` và `score` không tham gia điều kiện.

Hãy đọc probe và matcher như một bộ lọc hoàn chỉnh. Không chỉ nhìn vào giá trị field; cần xét cả null handler và ignore paths để biết điều kiện cuối cùng.

## 7. Bỏ qua thuộc tính theo từng use case

Có thể định nghĩa các matcher khác nhau cho các loại tìm kiếm khác nhau mà không phải thay đổi entity.

Ví dụ tìm kiếm danh bạ chỉ theo tên và thành phố:

```java
ExampleMatcher contactMatcher = ExampleMatcher.matchingAll()
        .withIgnorePaths("personId", "age", "active", "score");
```

Ví dụ tìm người đang hoạt động theo thành phố, nhưng không lọc tuổi:

```java
Person probe = new Person();
probe.setCity("Da Nang");
probe.setActive(true);

ExampleMatcher activeMatcher = ExampleMatcher.matchingAll()
        .withIgnorePaths("personId", "age", "score");
Example<Person> activeExample = Example.of(probe, activeMatcher);
```

Ví dụ tìm người có `active = false`:

```java
Person probe = new Person();
probe.setActive(false);

ExampleMatcher inactiveMatcher = ExampleMatcher.matchingAll()
        .withIgnorePaths("personId", "name", "city", "age", "score");
```

Trong ví dụ cuối, `active` là điều kiện duy nhất. Vì `Boolean` được gán `false`, matcher so khớp với giá trị false thay vì bỏ qua field.

Nếu cần kết hợp các điều kiện theo OR, có thể dùng `ExampleMatcher.matchingAny()`. Null và ignore paths vẫn cần được xem xét theo cùng nguyên tắc; việc đổi AND sang OR không biến null thành giá trị tự động.

## 8. Kết hợp quy tắc chuỗi với null và ignore paths

Ngoài null handler, matcher có thể cấu hình cách so khớp chuỗi. Ví dụ tìm tên chứa từ khóa, không phân biệt chữ hoa chữ thường, đồng thời bỏ qua các field khác:

```java
import static org.springframework.data.domain.ExampleMatcher.GenericPropertyMatchers.contains;

ExampleMatcher matcher = ExampleMatcher.matchingAll()
        .withIgnorePaths("personId", "age", "active", "score")
        .withMatcher("name", contains().ignoreCase());
```

`withMatcher("name", ...)` chỉ áp dụng quy tắc chuỗi cho property `name`. Các field null khác tiếp tục bị bỏ qua theo mặc định. Nếu bật `withIncludeNullValues()`, các field null không bị ignore cũng được đưa vào điều kiện, nên cần kết hợp ignore paths có chủ đích.

QBE phù hợp với những bộ lọc tương đối đơn giản được tạo từ property của một probe. Nếu use case cần nhóm điều kiện phức tạp, traversal qua nhiều loại relationship, biểu thức OR lồng nhau hoặc logic Cypher chuyên biệt, hãy cân nhắc repository `@Query` hay `Neo4jClient` thay vì cố ép toàn bộ yêu cầu vào `ExampleMatcher`.

## 9. Các lỗi thường gặp

| Lỗi | Hệ quả | Cách xử lý |
|---|---|---|
| Nghĩ null mặc định có nghĩa tìm property null | QBE bỏ qua field null nên kết quả rộng hơn mong đợi | Dùng `withIncludeNullValues()` khi thật sự cần điều kiện null |
| Bật include-null mà không ignore field chưa nhập | Nhiều điều kiện `IS NULL` được thêm ngoài ý muốn | Bỏ qua các field null không phải tiêu chí tìm kiếm |
| Dùng primitive cho filter tùy chọn | `0` hoặc `false` mặc định trở thành điều kiện | Dùng wrapper type hoặc `withIgnorePaths()` |
| Nghĩ chuỗi rỗng giống null | `""` vẫn là một giá trị được so khớp | Chuẩn hóa đầu vào hoặc ignore field khi rỗng |
| Quên bỏ qua ID | Probe có ID được dùng làm điều kiện ngoài ý muốn | Thêm ID vào `withIgnorePaths()` khi không cần tìm theo ID |
| Gọi `withIgnorePaths()` nhưng không giữ matcher mới | Quy tắc bỏ qua không được áp dụng | Gán kết quả trả về cho biến matcher |
| Dùng QBE cho điều kiện graph quá phức tạp | Khó diễn đạt hoặc không phù hợp với khả năng QBE | Viết Cypher tùy chỉnh bằng `@Query` hoặc `Neo4jClient` |

## 10. Quy trình tạo probe an toàn

Khi xây dựng form tìm kiếm, hãy thực hiện theo trình tự:

1. Xác định field nào là bộ lọc tùy chọn và dùng wrapper type cho các giá trị có thể chưa được cung cấp.
2. Chuẩn hóa dữ liệu đầu vào; quyết định chuỗi rỗng có nghĩa là bỏ qua hay tìm chuỗi rỗng.
3. Tạo probe mới cho mỗi lần tìm kiếm, tránh tái sử dụng object có thể còn giá trị từ request trước.
4. Xác định field nào phải được ignore, đặc biệt là ID, field primitive mặc định và field kỹ thuật.
5. Chỉ bật include-null khi use case thực sự muốn tìm property null; bỏ qua tường minh các field null không liên quan.
6. Chọn `matchingAll()` hay `matchingAny()` theo logic AND/OR của nghiệp vụ.
7. Kiểm tra kết quả với các trường hợp null, `0`, `false`, chuỗi rỗng và field bị bỏ qua.

Tách bước chuẩn hóa đầu vào khỏi bước tạo `Example` giúp quy tắc tìm kiếm dễ kiểm thử. Nếu bộ lọc có nhiều trạng thái như “không quan tâm”, “bằng null”, “bằng giá trị cụ thể”, DTO filter riêng sẽ thể hiện ý định rõ hơn một entity probe đơn thuần.

## 11. Bài tập thực hành

Tạo một số node `Person` có dữ liệu khác nhau:

```cypher
CREATE
  (:Person {personId: 'P-01', name: 'Lan', city: 'Da Nang', age: 30, active: true, score: 0}),
  (:Person {personId: 'P-02', name: 'Minh', city: 'Da Nang', age: 0, active: false, score: 10}),
  (:Person {personId: 'P-03', name: 'Hoa', city: 'Hue', age: 30, active: false, score: 0}),
  (:Person {personId: 'P-04', city: 'Da Nang', age: 30, active: true, score: 5});
```

Thực hiện các yêu cầu:

1. Tạo probe chỉ có `city = "Da Nang"` và xác nhận các field null được bỏ qua theo mặc định.
2. Tạo probe có `active = false` và dùng wrapper `Boolean`; xác nhận kết quả chỉ gồm node có giá trị false.
3. Tạo probe với field `int age` chưa gán để quan sát giá trị mặc định `0` có thể trở thành điều kiện.
4. Thêm `withIgnorePaths("age")` và so sánh kết quả.
5. Dùng `withIncludeNullValues()` để tìm người chưa có `name`, đồng thời ignore các field null khác.
6. Thử `name = ""` và giải thích vì sao nó khác với `name = null`.
7. Tạo matcher tìm tên chứa chuỗi không phân biệt hoa thường.
8. Viết test cho các trường hợp `null`, `0`, `false`, chuỗi rỗng và ignore paths.

Sau bài tập, hãy giải thích được tại sao wrapper type phù hợp với filter tùy chọn, khi nào cần include-null và vì sao ignore paths là cách kiểm soát rõ ràng các thuộc tính không nên tham gia QBE.

## Kết luận

QBE mặc định bỏ qua thuộc tính tham chiếu null trong probe. `withIncludeNullValues()` đưa null vào điều kiện so khớp, còn `withIgnorePaths()` loại các thuộc tính được chỉ định khỏi truy vấn. Primitive luôn có giá trị mặc định như `0` hoặc `false`, vì vậy có thể tạo điều kiện ngoài ý muốn; dùng wrapper type cho filter tùy chọn hoặc ignore field primitive khi cần. Hãy phân biệt null với chuỗi rỗng, cấu hình matcher theo từng use case và kiểm thử các giá trị biên để truy vấn Neo4j phản ánh đúng ý định tìm kiếm.
