# Nullability và dữ liệu không đủ để gọi constructor

Khi Spring Data Neo4j (SDN) đọc một node và chuyển nó thành entity Java, framework phải tạo được đối tượng với các giá trị lấy từ dữ liệu đồ thị. Nếu entity được khởi tạo qua constructor, SDN cần xác định constructor phù hợp và cung cấp giá trị cho các tham số của constructor đó.

Vấn đề xuất hiện khi một property không tồn tại trên node, có giá trị `null` trong kết quả ánh xạ, hoặc truy vấn chỉ trả về một phần dữ liệu trong khi constructor yêu cầu nhiều tham số. Một constructor có tham số bắt buộc nhưng dữ liệu không đáp ứng được các yêu cầu đó có thể khiến quá trình materialization thất bại. Thiết kế entity và truy vấn cần thống nhất về thuộc tính bắt buộc, thuộc tính tùy chọn và hình dạng kết quả.

## 1. Vì sao constructor cần đủ dữ liệu?

SDN sử dụng metadata của entity để tạo đối tượng từ node. Với constructor-based materialization, tên tham số constructor được đối chiếu với tên thuộc tính persistent trong mô hình Java. Sau khi có đối tượng, các thuộc tính còn lại có thể được gán qua cơ chế property access nếu mô hình cho phép.

Ví dụ, entity có constructor yêu cầu `id`, `name` và `email`:

```java
@Node("Person")
public class Person {

    @Id
    private final String id;
    private final String name;
    private final String email;

    public Person(String id, String name, String email) {
        this.id = id;
        this.name = name;
        this.email = email;
    }
}
```

Constructor này thể hiện rằng cả ba giá trị đều cần có để tạo một `Person`. Nếu node cũ chưa có `email`, hoặc một truy vấn chỉ trả về `id` và `name`, dữ liệu đầu vào không còn đáp ứng đầy đủ hợp đồng mà constructor mô tả.

Điều đó không có nghĩa mọi property trong Neo4j đều phải tồn tại. Nó có nghĩa entity phải xác định rõ property nào có thể vắng mặt và constructor phải chấp nhận trạng thái đó, hoặc dữ liệu được truy vấn phải cung cấp đủ các giá trị bắt buộc.

## 2. SDN chọn constructor như thế nào?

Spring Data có quy tắc chọn constructor hoặc factory method để tạo persistent object. Các trường hợp phổ biến gồm:

- Nếu chỉ có một constructor, Spring Data sử dụng constructor đó.
- Nếu có nhiều constructor, có thể đánh dấu constructor dùng cho persistence bằng `@PersistenceCreator`.
- Nếu lớp có constructor không tham số và không có lựa chọn constructor khác được chỉ định, Spring Data có thể dùng constructor không tham số rồi gán các property sau đó.
- Với Java record, constructor canonical của record là điểm khởi tạo đối tượng.

`@PersistenceCreator` thuộc package `org.springframework.data.annotation`. Annotation này giúp chỉ rõ constructor dành cho quá trình ánh xạ khi lớp có nhiều constructor.

```java
import org.springframework.data.annotation.PersistenceCreator;
import org.springframework.data.neo4j.core.schema.Id;
import org.springframework.data.neo4j.core.schema.Node;

@Node("Person")
public class Person {

    @Id
    private final String id;
    private final String name;
    private final Integer age;

    public Person(String name) {
        this("generated-by-application", name, null);
    }

    @PersistenceCreator
    public Person(String id, String name, Integer age) {
        this.id = id;
        this.name = name;
        this.age = age;
    }
}
```

Constructor có `@PersistenceCreator` là constructor SDN dùng để dựng entity từ dữ liệu đã đọc. Constructor ngắn hơn có thể phục vụ việc tạo đối tượng trong nghiệp vụ ứng dụng. Cần bảo đảm tham số constructor persistence khớp với các thuộc tính persistent và kiểu dữ liệu tương ứng.

Để Spring Data đọc được tên tham số constructor Java, hãy bật lưu metadata tên tham số khi biên dịch, thường bằng tùy chọn `-parameters`. Nếu tên tham số không được lưu, framework có thể không xác định được tham số tương ứng với property. `@PersistenceCreator` chọn constructor; nó không tự sửa tên tham số hoặc bổ sung dữ liệu bị thiếu.

## 3. Phân biệt property bắt buộc và property tùy chọn

Neo4j không lưu property có giá trị `null` như một giá trị thông thường; property không tồn tại trên node thường được nhìn thấy như giá trị vắng mặt khi ánh xạ. Vì vậy, entity cần biểu diễn được những thuộc tính có thể chưa có dữ liệu.

Trong Java, kiểu tham chiếu như `String`, `Integer` và `Boolean` có thể nhận `null`. Kiểu nguyên thủy như `int` và `boolean` không thể biểu diễn trạng thái vắng mặt. Nếu dữ liệu có thể thiếu, dùng wrapper type để giữ được sự khác biệt giữa chưa có giá trị và giá trị mặc định.

```java
@Node("Person")
public class Person {

    @Id
    private String id;

    private String name;
    private Integer age;
    private Boolean verified;
}
```

Với mô hình này:

- `name` có thể được coi là bắt buộc theo quy tắc nghiệp vụ.
- `age == null` biểu thị chưa biết tuổi hoặc node chưa có property `age`.
- `verified == null` khác với `verified == false`: trạng thái chưa xác định khác với trạng thái đã xác nhận là false.

Nếu dùng `int age`, ứng dụng không thể phân biệt tuổi chưa được cung cấp với tuổi bằng `0` chỉ dựa trên giá trị field. Dùng wrapper type khi cần bảo toàn ý nghĩa của dữ liệu không đầy đủ.

## 4. Bảo vệ invariant trong constructor

Nếu một thuộc tính thực sự bắt buộc, hãy kiểm tra nó ở nơi tạo entity. Điều này giúp phát hiện dữ liệu không hợp lệ ngay khi ánh xạ thay vì để lỗi lan sang các bước xử lý nghiệp vụ.

```java
import java.util.Objects;

import org.springframework.data.annotation.PersistenceCreator;
import org.springframework.data.neo4j.core.schema.Id;
import org.springframework.data.neo4j.core.schema.Node;

@Node("Person")
public class Person {

    @Id
    private final String id;
    private final String name;
    private final Integer age;

    @PersistenceCreator
    public Person(String id, String name, Integer age) {
        this.id = Objects.requireNonNull(id, "id is required");
        this.name = Objects.requireNonNull(name, "name is required");
        this.age = age;
    }
}
```

Trong ví dụ, `id` và `name` là bắt buộc, còn `age` có thể vắng mặt. Nếu một node không có `name`, constructor từ chối tạo entity. Đây là cách bảo vệ invariant của mô hình miền, nhưng cũng đồng nghĩa dữ liệu cũ phải được bổ sung hoặc truy vấn phải được thiết kế để trả về đủ property bắt buộc trước khi ánh xạ thành `Person`.

Không nên biến mọi property thành bắt buộc chỉ vì constructor có thể nhận chúng. Hãy chọn yêu cầu dựa trên quy tắc nghiệp vụ. Một profile chưa có ngày sinh vẫn có thể là một người hợp lệ; một bản ghi không có mã định danh có thể không đủ điều kiện để được xem là entity.

## 5. Dữ liệu không đầy đủ do truy vấn Cypher

Một node có thể chứa đủ property, nhưng câu truy vấn tùy chỉnh chỉ trả về một phần dữ liệu. Đây là nguồn lỗi thường gặp khi dùng `@Query` hoặc `Neo4jClient`.

Truy vấn trả về node:

```cypher
MATCH (p:Person {id: $id})
RETURN p
```

Trả về `p` giúp SDN nhận được node cùng các property của nó để ánh xạ entity. Trong khi đó, truy vấn sau chỉ trả về hai giá trị:

```cypher
MATCH (p:Person {id: $id})
RETURN p.id AS id, p.name AS name
```

Kết quả thứ hai là một record gồm `id` và `name`, không phải node `Person` đầy đủ. Nếu cố ánh xạ record này thành entity có constructor yêu cầu thêm `email`, `age` hoặc các property khác, dữ liệu không đủ để đáp ứng hợp đồng constructor.

Khi chỉ cần một phần dữ liệu, hãy khai báo projection hoặc DTO đúng với kết quả truy vấn. Ví dụ interface projection:

```java
public interface PersonSummary {
    String getId();
    String getName();
}
```

```java
@Query("""
    MATCH (p:Person)
    WHERE p.active = true
    RETURN p.id AS id, p.name AS name
    """)
List<PersonSummary> findActiveSummaries();
```

Projection mô tả chính xác dữ liệu use case cần. Nó tránh việc tạo một entity đầy đủ từ một kết quả chỉ có vài cột. Nếu nghiệp vụ cần entity, hãy trả về node và để SDN ánh xạ theo metadata entity.

## 6. Tên tham số constructor phải khớp tên property Java

Khi ánh xạ constructor, Spring Data đối chiếu tên tham số với thuộc tính persistent của entity. Tên tham số là tên trong mô hình Java, không phải lúc nào cũng giống property key trong Neo4j.

Ví dụ, entity có khai báo:

```java
@Property("display_name")
private final String name;
```

Constructor nên nhận tham số `name` tương ứng với thuộc tính Java:

```java
@PersistenceCreator
public Person(String id, String name) {
    this.id = id;
    this.name = name;
}
```

SDN sử dụng metadata `@Property("display_name")` để đọc hoặc ghi key `display_name` trong Neo4j. Không đổi tên tham số constructor thành `display_name` chỉ vì đó là key lưu trữ. Giữ tên tham số theo property Java để mapping có thể liên kết đúng.

## 7. Xử lý dữ liệu cũ và property vắng mặt

Trong quá trình phát triển, entity thường được mở rộng bằng thuộc tính mới. Các node đã tồn tại từ trước có thể chưa có property đó. Nếu thuộc tính mới là tùy chọn, dùng kiểu tham chiếu và cho phép `null` là một cách giữ tương thích.

Ví dụ, ứng dụng thêm `nickname` vào `Person`:

```java
private String nickname;
```

Các node cũ không có `nickname` vẫn có thể được ánh xạ nếu entity và constructor cho phép giá trị này vắng mặt. Nếu `nickname` được thêm vào constructor với yêu cầu không null, cần có bước migration bổ sung giá trị hoặc một chiến lược mặc định rõ ràng.

Không nên tự động gán giá trị mặc định cho mọi property bị thiếu. `0`, `false` hoặc chuỗi rỗng có thể mang ý nghĩa nghiệp vụ khác với “chưa biết”. Chỉ dùng `coalesce` trong Cypher hoặc giá trị mặc định trong constructor khi đó là quy tắc được xác định rõ.

Ví dụ, nếu nghiệp vụ xác định người dùng mới luôn ở trạng thái chưa xác minh, bạn có thể dùng `coalesce` trong một truy vấn cụ thể:

```cypher
MATCH (p:Person)
RETURN p.id AS id,
       p.name AS name,
       coalesce(p.verified, false) AS verified
```

Kết quả này phù hợp với một projection có trường `verified`. Nếu dùng để ánh xạ entity, hãy chắc chắn việc mặc định `false` đúng với toàn bộ dữ liệu cũ và không che giấu trạng thái chưa biết.

## 8. Nullability trong Java, Kotlin và validation

Java không biểu diễn nullability trong hệ thống kiểu ở mức ngôn ngữ. Một tham số kiểu `String` về mặt Java vẫn có thể nhận `null`, trừ khi có cơ chế kiểm tra bổ sung. Hãy thể hiện quy tắc bắt buộc bằng constructor guard, validation hoặc annotation nullability được dự án sử dụng nhất quán.

Kotlin có kiểu nullable và non-nullable ở cấp ngôn ngữ:

```kotlin
@Node("Person")
data class Person(
    @Id val id: String,
    val name: String,
    val nickname: String? = null
)
```

Trong ví dụ, `id` và `name` là non-null, còn `nickname` có thể null và có giá trị mặc định. Spring Data hỗ trợ Kotlin constructor và các tham số có giá trị mặc định theo metadata Kotlin. Tuy nhiên, nếu dữ liệu không cung cấp một tham số non-null bắt buộc, quá trình tạo đối tượng vẫn không thể thỏa mãn hợp đồng kiểu. Giá trị mặc định của Kotlin chỉ áp dụng khi tham số có thể được bỏ qua theo cơ chế khởi tạo được hỗ trợ; không nên giả định nó thay thế cho việc thiết kế dữ liệu đúng.

Nếu dùng Bean Validation, có thể kết hợp `@NotNull` hoặc `@NotBlank` để xác thực dữ liệu ở ranh giới ứng dụng. Validation không tự bổ sung property thiếu trong Neo4j; nó chỉ phát hiện dữ liệu vi phạm quy tắc khi validation được thực thi.

## 9. Cách chẩn đoán lỗi khởi tạo entity

Khi SDN không thể tạo entity từ node hoặc kết quả Cypher, hãy kiểm tra theo thứ tự:

1. **Constructor được chọn:** lớp có bao nhiêu constructor? Có cần đánh dấu constructor persistence bằng `@PersistenceCreator` không?
2. **Tên tham số:** tên tham số có được lưu khi biên dịch Java không? Chúng có khớp với tên property Java không?
3. **Dữ liệu node:** các property bắt buộc có thực sự tồn tại trên node không? Kiểm tra bằng Cypher `RETURN properties(p)`.
4. **Hình dạng kết quả:** truy vấn trả về node (`RETURN p`) hay chỉ trả về một số cột? Entity có đang được dựng từ một projection thiếu dữ liệu không?
5. **Nullability:** constructor có nhận `null` ở các property tùy chọn không? Có dùng primitive cho dữ liệu có thể thiếu không?
6. **Kiểu dữ liệu:** giá trị Neo4j có chuyển đổi được sang kiểu tham số constructor không?
7. **Dữ liệu cũ:** property mới có được migration hoặc có chiến lược mặc định tương thích không?

Một truy vấn kiểm tra nhanh các property đang lưu:

```cypher
MATCH (p:Person {id: $id})
RETURN properties(p) AS storedProperties
```

Nếu dữ liệu đầy đủ nhưng vẫn lỗi, kiểm tra constructor được chọn và tên tham số trước khi thay đổi schema. Nếu dữ liệu thiếu thật, quyết định rõ property đó là tùy chọn hay cần migration.

## 10. Những lỗi thường gặp

| Tình huống | Nguyên nhân | Cách xử lý |
|---|---|---|
| Mapping lỗi khi thêm constructor thứ hai | Spring Data không xác định được constructor persistence mong muốn | Đánh dấu constructor phù hợp bằng `@PersistenceCreator` |
| Constructor nhận `null` ngoài dự kiến | Node cũ không có property hoặc query trả về thiếu field | Xác định property bắt buộc/tùy chọn và kiểm tra kết quả truy vấn |
| Entity dùng primitive cho property tùy chọn | Primitive không biểu diễn được trạng thái vắng mặt | Dùng wrapper như `Integer` hoặc `Boolean` |
| Constructor parameter không được map | Tên tham số không khớp property hoặc thiếu metadata tham số | Biên dịch với `-parameters` và dùng đúng tên property Java |
| Dùng entity cho kết quả aggregate | Query trả về scalar hoặc một phần cột thay vì node đầy đủ | Dùng interface projection hoặc DTO |
| Giá trị mặc định che giấu dữ liệu chưa biết | `0`, `false` hoặc chuỗi rỗng bị coi là dữ liệu thật | Chỉ đặt default khi có quy tắc nghiệp vụ rõ ràng |

## 11. Tự kiểm tra

1. Khi nào cần dùng `@PersistenceCreator` cho entity?
2. Vì sao constructor parameter cần khớp tên property Java?
3. Điều gì khác nhau giữa property không tồn tại và property có giá trị mặc định `false`?
4. Vì sao kiểu `Integer` phù hợp hơn `int` khi tuổi có thể chưa được cung cấp?
5. Khi Cypher chỉ trả về `id` và `name`, vì sao nên dùng projection thay vì ánh xạ sang entity đầy đủ?
6. Nếu một property mới là bắt buộc nhưng node cũ chưa có, cần giải quyết bằng cách nào?

Thiết kế nullability và constructor cùng nhau giúp SDN tạo entity từ đồ thị một cách dự đoán được. Hãy để constructor phản ánh các invariant thật sự của mô hình, dùng kiểu nullable cho dữ liệu tùy chọn và chọn projection khi truy vấn chỉ cung cấp một phần thông tin.
