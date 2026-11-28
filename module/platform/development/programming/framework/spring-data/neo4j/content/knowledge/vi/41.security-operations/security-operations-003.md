# Bind tham số để phòng Cypher injection

Cypher injection xảy ra khi dữ liệu do người dùng kiểm soát bị ghép trực tiếp vào câu truy vấn, khiến Neo4j phân tích dữ liệu đó như một phần cú pháp Cypher. Kẻ tấn công có thể thay đổi điều kiện lọc, mở rộng phạm vi đọc hoặc chèn thêm thao tác ghi/xóa nếu tài khoản database có quyền tương ứng.

Cách phòng vệ cơ bản là **giữ câu truy vấn cố định và truyền dữ liệu qua query parameters**. Spring Data Neo4j (SDN) hỗ trợ tham số trong `@Query`; `Neo4jClient` hỗ trợ `.bind()` và `.bindAll()`; Neo4j Java Driver nhận một `Map` tham số khi thực thi query. Neo4j xử lý các giá trị được bind như dữ liệu, không phân tích nội dung chuỗi đó thành cú pháp Cypher.

## 1. Cypher injection hình thành như thế nào?

Giả sử service tìm người theo email. Cách ghép chuỗi không an toàn:

```java
String cypher = "MATCH (p:Person) WHERE p.email = '" + email + "' RETURN p";
```

Nếu đầu vào là một email bình thường, query có thể hoạt động. Nhưng nếu đầu vào chứa dấu nháy và phần cú pháp Cypher như:

```text
' OR true //
```

Chuỗi ghép có thể trở thành:

```cypher
MATCH (p:Person) WHERE p.email = '' OR true //' RETURN p
```

Điều kiện `OR true` làm bộ lọc khớp với mọi `Person`; `//` chú thích phần còn lại của dòng. Một input lẽ ra chỉ là email đã làm thay đổi cấu trúc query.

Hậu quả phụ thuộc câu query và quyền của tài khoản kết nối Neo4j. Injection có thể làm lộ dữ liệu, bỏ qua bộ lọc tenant, sửa node/relationship hoặc xóa graph. Vì vậy, không ghép bất kỳ dữ liệu không đáng tin cậy nào vào query string.

## 2. Query parameter tách cú pháp khỏi dữ liệu

Viết lại query bằng placeholder:

```cypher
MATCH (p:Person)
WHERE p.email = $email
RETURN p;
```

Giá trị `email` được gửi riêng khi thực thi. Nếu giá trị là `' OR true //`, Neo4j so sánh thuộc tính email với đúng chuỗi ký tự đó. Dấu nháy, từ khóa và comment marker trong giá trị không trở thành cú pháp của query.

Giữ query template ổn định còn giúp Neo4j tái sử dụng execution plan cho những lần gọi chỉ khác parameter value. Vì vậy parameterization đồng thời hỗ trợ bảo mật và khả năng tái sử dụng query plan; không nên dựa vào cơ chế auto-parameterization để thay thế việc bind rõ ràng trong mã ứng dụng.

Hai phần được giữ riêng:

| Thành phần | Ví dụ | Nguồn |
|---|---|---|
| Query template | `MATCH (p:Person) WHERE p.email = $email RETURN p` | Mã ứng dụng, được review và quản lý phiên bản |
| Parameter | `email = "alice@example.com"` | Request, message hoặc dữ liệu nghiệp vụ sau khi validate |

Tham số phải được viết trực tiếp bằng cú pháp `$name`. Không đặt placeholder trong dấu nháy:

```cypher
// Đúng: email là parameter
MATCH (p:Person {email: $email}) RETURN p;

// Sai: đây là chuỗi literal "$email", không phải parameter
MATCH (p:Person {email: '$email'}) RETURN p;
```

Tên tham số phân biệt với giá trị. Ví dụ `$email` là tên placeholder; chuỗi được bind vào `email` có thể chứa ký tự bất kỳ hợp lệ với kiểu dữ liệu của Neo4j.

## 3. Dùng tham số trong Spring Data Neo4j @Query

Với repository, khai báo Cypher tĩnh và bind giá trị bằng `@Param`:

```java
import java.util.Collection;
import java.util.List;
import java.util.Optional;

import org.springframework.data.neo4j.repository.Neo4jRepository;
import org.springframework.data.neo4j.repository.query.Query;
import org.springframework.data.repository.query.Param;

public interface PersonRepository extends Neo4jRepository<Person, Long> {

    @Query("""
        MATCH (p:Person {email: $email})
        RETURN p
        """)
    Optional<Person> findByEmail(@Param("email") String email);
}
```

Entity tối thiểu dùng trong các ví dụ:

```java
import org.springframework.data.neo4j.core.schema.GeneratedValue;
import org.springframework.data.neo4j.core.schema.Id;
import org.springframework.data.neo4j.core.schema.Node;

@Node("Person")
public class Person {
    @Id
    @GeneratedValue
    private Long id;

    private String code;
    private String email;
    private String name;

    protected Person() {
    }

    public Person(String code, String email) {
        this.code = code;
        this.email = email;
    }

    public String getCode() { return code; }
    public String getEmail() { return email; }
    public String getName() { return name; }
}
```

Vì `Person.id` dùng `@GeneratedValue`, repository khai báo kiểu ID là `Long`. Các method `@Query` ở trên có thể nằm trong cùng interface.

`@Param("email")` liên kết tham số Java với placeholder `$email`. Cách khai báo tường minh giúp tránh phụ thuộc vào tên tham số được giữ trong bytecode. Nếu không dùng `@Param`, Spring Data có thể lấy tên tham số khi dự án được biên dịch với tùy chọn `-parameters`; Spring Boot Maven/Gradle plugin thường cấu hình tùy chọn này.

Không dùng cú pháp tham số cũ `${email}` hoặc `{email}` cho query mới. Từ Neo4j 4.0, cú pháp tham số Cypher là `$email`.

Có thể bind nhiều tham số trong cùng query:

```java
@Query("""
    MATCH (p:Person)
    WHERE p.status = $status
      AND p.email IN $emails
    RETURN p
    ORDER BY p.name
    """)
List<Person> findByStatusAndEmails(
    @Param("status") String status,
    @Param("emails") Collection<String> emails
);
```

Danh sách email được truyền như một giá trị list. Không nối các phần tử thành chuỗi `'a@example.com','b@example.com'` để đưa vào `IN`.

## 4. Dùng Neo4jClient.bind() và bindAll()

`Neo4jClient` cung cấp fluent API để gắn giá trị vào query:

```java
import java.util.List;
import java.util.Map;

import org.springframework.data.neo4j.core.Neo4jClient;
import org.springframework.stereotype.Repository;

@Repository
public class PersonLookup {
    private final Neo4jClient neo4jClient;

    public PersonLookup(Neo4jClient neo4jClient) {
        this.neo4jClient = neo4jClient;
    }

    public List<Map<String, Object>> findByEmail(String email) {
        return neo4jClient.query("""
                MATCH (p:Person {email: $email})
                RETURN p.code AS code, p.name AS name
                """)
            .bind(email).to("email")
            .fetch()
            .all();
    }
}
```

Query string không thay đổi theo email. `.bind(email).to("email")` gắn giá trị vào `$email`; `.fetch().all()` trả về các dòng kết quả dưới dạng map.

Khi có nhiều tham số, có thể dùng `.bindAll()`:

```java
Map<String, Object> parameters = Map.of(
    "status", "ACTIVE",
    "codes", List.of("P-100", "P-200")
);

List<Map<String, Object>> rows = neo4jClient.query("""
        MATCH (p:Person)
        WHERE p.status = $status
          AND p.code IN $codes
        RETURN p.code AS code, p.name AS name
        ORDER BY p.name
        """)
    .bindAll(parameters)
    .fetch()
    .all();
```

Tên key trong map phải khớp placeholder trong query. Neo4jClient không tự xác nhận mọi placeholder đều đã được bind hoặc không có giá trị thừa; driver sẽ báo lỗi khi thực thi nếu thiếu tham số cần thiết.

## 5. Bind tham số với Neo4j Java Driver

Nếu ứng dụng dùng Driver trực tiếp, truyền query và parameter map thành hai đối số riêng:

```java
import java.util.List;
import java.util.Map;

import org.neo4j.driver.Driver;
import org.neo4j.driver.Session;

public List<String> findNamesByEmail(Driver driver, String email) {
    try (Session session = driver.session()) {
        return session.run("""
                MATCH (p:Person {email: $email})
                RETURN p.name AS name
                """, Map.of("email", email))
            .list(record -> record.get("name").asString());
    }
}
```

Với Driver hiện đại, có thể dùng `driver.executableQuery(...).withParameters(Map.of(...)).execute()`. Cả hai cách đều giữ parameter bên ngoài query string. Dùng `try-with-resources` để đóng session sau khi hoàn tất.

```java
var result = driver.executableQuery("""
        MATCH (p:Person {email: $email})
        RETURN p.name AS name
        """)
    .withParameters(Map.of("email", email))
    .execute();
```

Không truyền câu Cypher do client gửi vào như một parameter để mong Neo4j chạy câu query đó. Parameter là dữ liệu của query hiện tại; nó không được parse đệ quy thành query mới.

## 6. Những kiểu dữ liệu có thể bind

Cypher parameter hỗ trợ nhiều kiểu giá trị:

| Kiểu | Ví dụ |
|---|---|
| Chuỗi | `String email` |
| Số nguyên/số thực | `Long age`, `Double score` |
| Boolean | `Boolean active` |
| List | `List<String> codes` |
| Map | `Map<String, Object> properties` |
| Temporal | `LocalDate`, `LocalDateTime`, `ZonedDateTime` khi driver hỗ trợ chuyển đổi |
| Node/relationship ID | Giá trị ID phù hợp với API và phiên bản Neo4j |

Ví dụ truyền list để lọc nhiều mã:

```cypher
MATCH (p:Person)
WHERE p.code IN $codes
RETURN p;
```

Ví dụ truyền map để tạo node:

```cypher
CREATE (p:Person $properties)
RETURN p;
```

Map `$properties` được gửi như một giá trị dữ liệu. Tuy nhiên, cần kiểm soát những key nào được phép ghi; parameterization ngăn injection cú pháp nhưng không tự giới hạn quyền sửa property.

## 7. Parameterize tất cả giá trị, kể cả LIMIT và SKIP

Các giá trị dùng trong filter, pagination, range và aggregation nên được bind:

```cypher
MATCH (p:Person)
WHERE p.age >= $minAge
  AND p.status IN $statuses
RETURN p
ORDER BY p.name
SKIP $offset
LIMIT $limit;
```

Trong Java, kiểm tra giới hạn nghiệp vụ trước khi bind:

```java
if (offset < 0 || limit < 1 || limit > 100) {
    throw new IllegalArgumentException("Invalid pagination range");
}
```

Binding giúp giá trị không thể thay đổi cấu trúc query. Validation vẫn cần thiết để ngăn người dùng yêu cầu quá nhiều dòng, độ sâu traversal quá lớn hoặc một range không hợp lệ làm tăng tải database.

## 8. Vì sao không thể viết `$label`, `$relationshipType` hoặc `$property` trực tiếp?

Query parameter thông thường thay thế literal/expression value. Label, relationship type và property key là thành phần cú pháp trong query plan, do đó các dạng sau không hợp lệ:

```cypher
// Không hợp lệ: parameter không thể đứng trực tiếp ở vị trí label
MATCH (n:$label) RETURN n;

// Không hợp lệ: parameter không thể đứng trực tiếp ở vị trí relationship type
MATCH (a)-[r:$relationshipType]->(b) RETURN r;

// Không hợp lệ: không thể truy cập property bằng cú pháp dot với parameter
MATCH (n:Person) WHERE n.$property = $value RETURN n;
```

Không giải quyết giới hạn này bằng cách nối raw input vào query. Với các phần cấu trúc thay đổi, dùng dynamic expressions được Neo4j hỗ trợ hoặc chọn một query template cố định từ allowlist do server quản lý.

## 9. Dynamic property access bằng dấu ngoặc vuông

Cypher hỗ trợ truy cập property bằng tên động qua toán tử `[]`:

```cypher
MATCH (p:Person)
WHERE p[$propertyName] = $value
RETURN p;
```

Trong đó `$propertyName` và `$value` đều là parameter. Ví dụ Java:

```java
@Query("""
    MATCH (p:Person)
    WHERE p[$propertyName] = $value
    RETURN p
    """)
List<Person> findByDynamicProperty(
    @Param("propertyName") String propertyName,
    @Param("value") String value
);
```

Dynamic property access giúp tránh ghép tên property vào chuỗi Cypher. Dù vậy, `propertyName` vẫn phải được allowlist theo use case. Ví dụ một API tìm kiếm chỉ được phép lọc theo `name`, `email` hoặc `status`; không nên cho client tùy ý chọn `passwordHash`, `tenantId` hoặc field nội bộ khác. Cú pháp an toàn khỏi injection không đồng nghĩa caller được quyền truy cập mọi property.

## 10. Dynamic label và relationship type từ Neo4j 5.26

Từ Neo4j 5.26, Cypher hỗ trợ dynamic label và relationship type trong pattern bằng biểu thức `$()`:

```cypher
MATCH (n:$($label))
RETURN n;
```

```cypher
MATCH (source)-[r:$($relationshipType)]->(target)
RETURN source, r, target;
```

`label` và `relationshipType` là parameter được bind bình thường. Giá trị phải là chuỗi hoặc list chuỗi không null theo yêu cầu của cú pháp. Một relationship chỉ có đúng một type, vì vậy một list nhiều type không tạo ra relationship có nhiều type.

Ví dụ dùng Neo4jClient:

```java
import java.util.List;
import java.util.Map;

import org.springframework.data.neo4j.core.Neo4jClient;

public List<Map<String, Object>> findByLabelAndProperty(
        Neo4jClient neo4jClient,
        String label,
        String propertyName,
        String value) {

    return neo4jClient.query("""
            MATCH (n:$($label))
            WHERE n[$propertyName] = $value
            RETURN n
            """)
        .bind(label).to("label")
        .bind(propertyName).to("propertyName")
        .bind(value).to("value")
        .fetch()
        .all();
}
```

Đối với Neo4j trước 5.26, không dùng cú pháp dynamic label/type này. Hãy chọn giữa một số query template tĩnh bằng enum/allowlist hoặc nâng cấp server. Dynamic matching có thể có khác biệt về query plan và hiệu năng theo phiên bản Neo4j; kiểm tra `EXPLAIN`/`PROFILE` trên phiên bản thực tế, đặc biệt khi cần tận dụng index.

Ngay cả khi dynamic label/type được bind an toàn, vẫn phải allowlist các label/type được phép. Ví dụ endpoint tìm kiếm công khai có thể chỉ cho phép `Person` và `Company`, không được phép truy vấn các label nội bộ hoặc dữ liệu quản trị.

## 11. Chọn query template bằng allowlist khi cần tương thích phiên bản cũ

Với server cũ không hỗ trợ dynamic label/type, có thể chọn một trong các query cố định:

```java
enum SearchKind {
    PERSON,
    COMPANY
}

String queryFor(SearchKind kind) {
    return switch (kind) {
        case PERSON -> "MATCH (n:Person) WHERE n.name = $value RETURN n";
        case COMPANY -> "MATCH (n:Company) WHERE n.name = $value RETURN n";
    };
}
```

`SearchKind` phải được tạo từ lựa chọn đã kiểm tra ở tầng API/service. Dữ liệu người dùng chỉ được dùng để chọn một nhánh enum hợp lệ; nó không được nối vào query string. Parameter `$value` vẫn bind riêng:

```java
neo4jClient.query(queryFor(kind))
    .bind(searchValue).to("value")
    .fetch()
    .all();
```

Allowlist ở đây gồm những chuỗi query literal do lập trình viên định nghĩa. Không tạo allowlist bằng cách nhận một chuỗi tùy ý rồi kiểm tra sơ sài bằng regex; hãy chuyển request sang enum hoặc giá trị miền đã định nghĩa.

## 12. Sort field và sort direction

Giá trị sort field và direction thường được dùng để dựng `ORDER BY`. Không thể viết `ORDER BY $field $direction` rồi kỳ vọng parameter trở thành identifier hoặc từ khóa. Với các lựa chọn hữu hạn, chọn query template cố định:

```java
enum PersonSort {
    NAME_ASC,
    NAME_DESC,
    CREATED_ASC,
    CREATED_DESC
}

String sortQuery(PersonSort sort) {
    return switch (sort) {
        case NAME_ASC -> "MATCH (p:Person) RETURN p ORDER BY p.name ASC LIMIT $limit";
        case NAME_DESC -> "MATCH (p:Person) RETURN p ORDER BY p.name DESC LIMIT $limit";
        case CREATED_ASC -> "MATCH (p:Person) RETURN p ORDER BY p.createdAt ASC LIMIT $limit";
        case CREATED_DESC -> "MATCH (p:Person) RETURN p ORDER BY p.createdAt DESC LIMIT $limit";
    };
}
```

Sau đó chỉ bind `limit`. Không ghép trực tiếp giá trị `sort` hoặc `direction` từ request vào query. Nếu dùng dynamic property access như `p[$sortProperty]` trên phiên bản phù hợp, vẫn cần allowlist property được phép sắp xếp; direction phải được chọn từ các nhánh query cố định.

## 13. Parameterization không thay thế authorization

Một query bind an toàn vẫn có thể trả dữ liệu mà user không được phép xem nếu điều kiện authorization bị thiếu.

Ví dụ không đủ an toàn về nghiệp vụ:

```cypher
MATCH (p:Person {code: $personCode})
RETURN p;
```

Query không bị injection, nhưng nếu API nhận `personCode` của bất kỳ tenant nào và không kiểm tra quyền, người dùng vẫn có thể đọc dữ liệu người khác.

Với multi-tenant, tenant ID nên lấy từ security principal đã xác thực và luôn nằm trong predicate:

```cypher
MATCH (p:Person {tenantId: $tenantId, code: $personCode})
RETURN p;
```

Service lấy `$tenantId` từ context đáng tin cậy ở server, không tin giá trị tenant do client tự gửi. Kiểm tra quyền trên resource trước khi đọc/ghi, và kiểm thử rằng một tenant không thể truy cập node thuộc tenant khác.

Ngoài parameterization, áp dụng quyền Neo4j tối thiểu cho user ứng dụng. Nếu một service chỉ đọc, cấp quyền đọc phù hợp; không dùng tài khoản quản trị database cho mọi endpoint. Phân quyền ở database là lớp bảo vệ bổ sung nếu có lỗi trong logic ứng dụng.

## 14. Parameter map và thao tác SET property

Cypher có thể nhận map parameter để tạo node hoặc cập nhật nhiều property. Nhưng cần hiểu semantics của từng toán tử:

```cypher
MATCH (p:Person {code: $code})
SET p += $properties
RETURN p;
```

`SET p += $properties` hợp nhất các property trong map vào node; những property không có trong map vẫn được giữ. Ngược lại:

```cypher
MATCH (p:Person {code: $code})
SET p = $properties
RETURN p;
```

`SET p = $properties` thay thế toàn bộ property hiện có bằng map được truyền vào. Những property không có trong map sẽ bị loại bỏ. Đây không phải Cypher injection, nhưng một map do client kiểm soát có thể gây cập nhật quá quyền hoặc xóa dữ liệu ngoài ý muốn.

Hãy tạo map từ các field được phép trong command object, không chuyển nguyên request body thành map ghi graph. Với các field nhạy cảm như `tenantId`, `roles`, `status`, `createdAt` hoặc version, chỉ server mới được quyết định giá trị.

## 15. Regex và biểu thức do người dùng cung cấp

Bind regex cũng ngăn chuỗi regex trở thành cú pháp Cypher, nhưng giá trị vẫn được diễn giải như regular expression:

```cypher
MATCH (p:Person)
WHERE p.name =~ $regex
RETURN p;
```

Nếu người dùng nhập `.*`, họ có thể yêu cầu khớp gần như mọi tên. Đây không phải injection vì cấu trúc query không đổi, nhưng có thể làm truy vấn rộng hơn dự kiến. Regex phức tạp cũng có thể gây tốn tài nguyên.

Nếu nghiệp vụ chỉ cần tìm chuỗi literal, ưu tiên `CONTAINS`, `STARTS WITH` hoặc `=` với parameter:

```cypher
MATCH (p:Person)
WHERE p.name CONTAINS $searchText
RETURN p;
```

Nếu thực sự cần regex, giới hạn độ dài, cú pháp và phạm vi kết quả; cân nhắc escape các ký tự regex theo semantics mà ứng dụng yêu cầu. Parameterization bảo vệ cấu trúc Cypher, không tự chuyển regex thành tìm kiếm literal.

## 16. Cẩn trọng với APOC và query được thực thi động

Một số APOC procedure nhận chuỗi Cypher rồi thực thi query thứ hai bên trong procedure. Khi dùng những API như vậy, parameter của query ngoài và parameter của query bên trong là hai lớp khác nhau.

Nguyên tắc:

- Giữ query string bên trong procedure là template do ứng dụng quản lý.
- Truyền dữ liệu qua parameter map của procedure nếu procedure hỗ trợ.
- Không nối dữ liệu request vào chuỗi Cypher thứ hai.
- Kiểm tra tài liệu và security guideline của procedure cụ thể; không phải mọi procedure đều có cùng semantics hoặc cùng mức an toàn.
- Không cấp quyền gọi các procedure nguy hiểm cho database user không cần sử dụng chúng.

Parameterization của câu gọi APOC bên ngoài không tự bảo vệ một câu Cypher mới mà procedure tự dựng bằng string concatenation. Cần xem xét toàn bộ chuỗi thực thi từ query ngoài tới query bên trong.

## 17. Kiểm thử để chứng minh input được xem là dữ liệu

Tạo test với các giá trị có ký tự dễ phá cú pháp:

```java
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.data.neo4j.DataNeo4jTest;

@DataNeo4jTest
class PersonCypherParameterTests {

    @Autowired
    PersonRepository repository;

    @Test
    void suspiciousLookingEmailIsTreatedAsLiteralData() {
        String unusualEmail = "' OR true //";
        repository.save(new Person("P-ATTACK", unusualEmail));

        var result = repository.findByEmail(unusualEmail);

        assertThat(result).isPresent();
        assertThat(result.orElseThrow().getCode()).isEqualTo("P-ATTACK");
    }
}
```

Test giả định `Person` có constructor và getter phù hợp, repository dùng query parameter `$email` ở phần trước, và database test đã được cấu hình. Input có dấu nháy, từ khóa `OR` và comment marker được lưu/tìm như một chuỗi email literal.

Có thể mở rộng test với các giá trị:

```text
O'Reilly@example.com
name`WITH`MATCH@example.com
' OR true //
Nguyễn Văn A@example.com
text with spaces
line-one
line-two
```

Kiểm tra thêm rằng:

1. Query chỉ trả đúng node khớp giá trị literal.
2. Một input có cú pháp giống Cypher không tạo thêm node hoặc relationship.
3. Query có tenant predicate không trả dữ liệu của tenant khác.
4. Các list parameter rỗng/lớn được xử lý theo chính sách ứng dụng.
5. Giá trị `limit`, `offset` và traversal depth nằm trong giới hạn cho phép.

## 18. Checklist review code để phòng Cypher injection

Khi review repository/service có truy vấn động, kiểm tra:

- [ ] Query string không chứa dữ liệu request được nối bằng `+`, `String.format`, template interpolation hoặc `formatted()`.
- [ ] Mọi scalar value dùng `$parameter`.
- [ ] `@Query` dùng `@Param` tường minh hoặc dự án có cấu hình `-parameters`.
- [ ] `Neo4jClient` dùng `.bind()`/`.bindAll()`; Driver dùng parameter map.
- [ ] Không đặt placeholder trong dấu nháy.
- [ ] List filter dùng list parameter thay vì tạo danh sách literal bằng nối chuỗi.
- [ ] Label/type/property key động dùng cú pháp dynamic được Neo4j hỗ trợ hoặc query template cố định từ allowlist.
- [ ] Sort field/direction được chọn từ enum hoặc query template cố định.
- [ ] Tenant ID và access scope đến từ context đã xác thực.
- [ ] Map ghi graph chỉ chứa field mà caller được phép thay đổi.
- [ ] Regex và pagination được validate để kiểm soát phạm vi/chi phí query.
- [ ] APOC hoặc procedure thực thi Cypher động được review cả query lồng bên trong.
- [ ] Database user tuân theo least privilege.
- [ ] Có integration test với input chứa dấu nháy, comment marker, backtick và chuỗi giống cú pháp Cypher.

## 19. Lỗi thường gặp

| Lỗi | Vì sao không an toàn hoặc không đúng | Cách sửa |
|---|---|---|
| Nối email vào query string | Input có thể thay đổi cú pháp Cypher | Dùng `$email` và bind giá trị |
| Dùng `'$email'` trong Cypher | Neo4j nhận chuỗi literal `$email` | Dùng `email: $email` không có dấu nháy |
| Dùng `$label` trực tiếp sau dấu `:` | Parameter không đứng trực tiếp ở vị trí label | Neo4j 5.26+: `:$($label)`; phiên bản cũ: query allowlist |
| Dùng `$type` trực tiếp trong `[:$type]` | Parameter không đứng trực tiếp ở vị trí relationship type | Neo4j 5.26+: `[:$($type)]`; phiên bản cũ: query allowlist |
| Dùng `n.$property` | Property key không thể parameterize theo cú pháp dot | Dùng `n[$property]` hoặc query cố định |
| Nối `ORDER BY` từ request | Field/direction trở thành cú pháp query | Enum và query template cố định |
| Nhận nguyên map request để `SET n = $map` | Có thể thay thế/xóa toàn bộ property node | Tạo map từ field allowlist; hiểu rõ `SET n +=` và `SET n =` |
| Chỉ bind tham số nhưng bỏ tenant predicate | Không phải injection nhưng vẫn có thể đọc chéo tenant | Lấy tenant từ principal và kiểm tra quyền |
| Cho phép regex tùy ý | Query có thể quá rộng hoặc tốn tài nguyên | Chọn semantics tìm kiếm phù hợp và validate regex |
| Nghĩ rằng query ngoài bind thì APOC query trong an toàn | Procedure có thể dựng query thứ hai từ chuỗi | Bind parameter cho query lồng và review procedure |
| Tin auto-parameterization của Neo4j | Không bảo đảm input không bị ghép vào cấu trúc query | Chủ động parameterize mọi giá trị |

## 20. Quy trình triển khai

1. Viết Cypher template cố định cho use case.
2. Thay mọi literal lấy từ request bằng placeholder `$name`.
3. Dùng `@Param`, `Neo4jClient.bind()`/`bindAll()` hoặc Driver parameter map để truyền dữ liệu.
4. Với list, map, date và số, truyền kiểu dữ liệu thực thay vì serialize thành đoạn Cypher.
5. Với label/type/property động, dùng dynamic expressions đúng phiên bản hoặc chọn template từ allowlist.
6. Validate giới hạn số dòng, độ sâu traversal, regex và field sort.
7. Lấy tenant/access scope từ security context và áp dụng trong query.
8. Giới hạn quyền database user theo chức năng service.
9. Viết integration test với payload có ký tự đặc biệt và xác minh graph không bị thay đổi ngoài ý muốn.
10. Review mọi procedure/APOC có khả năng thực thi Cypher lồng nhau.

## 21. Tự kiểm tra

1. Cypher injection khác dữ liệu đầu vào thông thường như thế nào?
2. Vì sao bind `$email` ngăn chuỗi `' OR true //` thay đổi cấu trúc query?
3. Cách khai báo `@Query` với `@Param` trong Spring Data Neo4j là gì?
4. `Neo4jClient.bind()` và `bindAll()` có nhiệm vụ gì?
5. Vì sao không đặt placeholder trong dấu nháy?
6. Có thể bind list cho điều kiện `IN` và `LIMIT` không?
7. Vì sao `$label` và `$relationshipType` không dùng trực tiếp ở mọi vị trí cú pháp?
8. Dynamic label/type bằng `:$(expr)` được hỗ trợ từ Neo4j phiên bản nào?
9. Dynamic property access `n[$propertyName]` khác `n.$propertyName` như thế nào?
10. Vì sao allowlist vẫn cần thiết dù đã dùng dynamic expressions?
11. Parameterization có tự bảo vệ dữ liệu giữa các tenant không?
12. `SET n = $properties` khác `SET n += $properties` ở điểm nào?
13. Vì sao regex parameter có thể an toàn về cú pháp nhưng vẫn tạo query tốn tài nguyên?
14. Khi dùng APOC thực thi Cypher động, cần kiểm tra những lớp query nào?

## Tài liệu tham khảo

- [Neo4j Cypher Manual — Parameters](https://neo4j.com/docs/cypher-manual/current/syntax/parameters/)
- [Neo4j Cypher Manual — Dynamic labels, types and properties](https://neo4j.com/docs/cypher-manual/current/clauses/where/)
- [Neo4j Java Driver Manual — Query parameters](https://neo4j.com/docs/java-manual/current/query-simple/)
- [Neo4j Java Driver Manual — Dynamic values in property keys, relationship types and labels](https://neo4j.com/docs/java-manual/current/query-advanced/)
- [Spring Data Neo4j — Custom queries and parameters](https://docs.spring.io/spring-data/neo4j/reference/appendix/custom-queries.html)
- [Spring Data Neo4j — Neo4jClient parameter binding](https://docs.spring.io/spring-data/neo4j/reference/appendix/neo4j-client.html)
- [Neo4j APOC — Security guidelines](https://neo4j.com/docs/apoc/current/security-guidelines/)
