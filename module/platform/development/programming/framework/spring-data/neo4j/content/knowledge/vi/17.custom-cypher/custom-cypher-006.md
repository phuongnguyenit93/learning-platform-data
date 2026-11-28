# Phân biệt tham số giá trị với label, kiểu quan hệ và cấu trúc Cypher

Khi viết Cypher tùy chỉnh trong Spring Data Neo4j (SDN), bạn thường truyền dữ liệu đầu vào bằng tham số như `$email`, `$status` hoặc `$createdAfter`. Các tham số này đại diện cho **giá trị** trong truy vấn. Chúng không mặc nhiên thay thế được mọi thành phần của cú pháp Cypher như label node, kiểu relationship, tên property hay từ khóa sắp xếp.

Phân biệt hai nhóm này rất quan trọng. Bind giá trị giúp truy vấn an toàn, dễ tái sử dụng và tránh lỗi khi dữ liệu chứa ký tự đặc biệt. Trong khi đó, những thành phần định hình cấu trúc truy vấn cần được viết tường minh, hoặc sử dụng cú pháp dynamic label/type/property được Neo4j hỗ trợ ở phiên bản tương ứng. Nếu phải xây dựng cấu trúc truy vấn động, ứng dụng cần kiểm soát chặt các lựa chọn được phép.

## 1. Tham số giá trị trong Cypher

Tham số giá trị được đặt sau dấu `$` và dùng ở vị trí biểu thức nhận giá trị. Ví dụ:

```cypher
MATCH (p:Person)
WHERE p.email = $email
  AND p.active = $active
RETURN p;
```

Trong truy vấn này:

- `Person` là label cố định trong cú pháp.
- `email` và `active` là property key cố định.
- `$email` và `$active` là giá trị được truyền khi thực thi.

Giá trị có thể là chuỗi, số, boolean, ngày giờ, danh sách hoặc map phù hợp với vị trí sử dụng. Ví dụ, tham số `$email` có thể nhận chuỗi `an@example.com`; Cypher không cần thay đổi cấu trúc khi giá trị thay đổi.

## 2. Bind tham số trong Spring Data Neo4j

Với repository method dùng `@Query`, tham số Java được liên kết với placeholder Cypher. Nên dùng `@Param` để thể hiện rõ tên liên kết, đặc biệt khi tên tham số Java không được lưu metadata lúc biên dịch.

```java
import java.util.Optional;

import org.springframework.data.neo4j.repository.Neo4jRepository;
import org.springframework.data.neo4j.repository.query.Query;
import org.springframework.data.repository.query.Param;

public interface PersonRepository extends Neo4jRepository<Person, Long> {

    @Query("""
        MATCH (p:Person)
        WHERE p.email = $email
        RETURN p
        """)
    Optional<Person> findByEmail(@Param("email") String email);
}
```

Khi gọi `findByEmail("an@example.com")`, SDN bind chuỗi đầu vào vào `$email`. Không cần nối email vào chuỗi Cypher. Cách này vừa giữ truy vấn ổn định, vừa tránh để nội dung người dùng nhập bị diễn giải thành cú pháp Cypher.

Với `Neo4jClient`, bạn có thể bind tham số theo chuỗi fluent API:

```java
return neo4jClient.query("""
        MATCH (p:Person)
        WHERE p.email = $email
        RETURN p.name AS name
        """)
    .bind(email).to("email")
    .fetchAs(String.class)
    .mappedBy((typeSystem, record) -> record.get("name").asString())
    .all();
```

Tên trong `.to("email")` phải khớp với `$email` trong Cypher. Dữ liệu được truyền riêng khỏi câu lệnh, kể cả khi giá trị chứa dấu nháy, dấu cách hoặc ký tự đặc biệt.

## 3. Vì sao không thể dùng `$label` như một giá trị thông thường?

Một cách viết dễ gây nhầm lẫn là:

```cypher
MATCH (n:$label)
RETURN n;
```

Ở dạng cú pháp Cypher thông thường, `$label` là placeholder cho một giá trị. Label `Person` lại là thành phần cấu trúc của pattern node. Vì vậy, không thể mặc định truyền chuỗi `"Person"` vào `$label` để thay thế label như cách truyền email vào `$email`.

Điều tương tự áp dụng cho kiểu relationship:

```cypher
MATCH (a)-[r:$relationshipType]->(b)
RETURN a, r, b;
```

Không nên giả định `$relationshipType` sẽ được thay thế thành tên kiểu relationship. Cú pháp parameter thông thường không phải cơ chế thay thế token cú pháp tùy ý.

## 4. Dynamic label và dynamic relationship type

Các phiên bản Neo4j mới hỗ trợ cú pháp dynamic label và dynamic relationship type thông qua biểu thức `$(...)`. Ví dụ:

```cypher
MATCH (n:$($label))
WHERE n.name = $name
RETURN n;
```

Và với relationship:

```cypher
MATCH (a)-[r:$($relationshipType)]->(b)
WHERE a.name = $sourceName
RETURN a, r, b;
```

Trong các ví dụ này, `$(...)` là cú pháp biểu thức dynamic label/type; `$label` và `$relationshipType` là tham số được bind. Đây là tính năng phụ thuộc phiên bản Neo4j/Cypher. Dynamic label và relationship type trong pattern `MATCH` được hỗ trợ từ Neo4j 5.26; hãy kiểm tra phiên bản server và chế độ Cypher của môi trường trước khi sử dụng.

Khi tính năng được hỗ trợ, có thể bind giá trị qua `Neo4jClient`:

```java
return neo4jClient.query("""
        MATCH (n:$($label))
        WHERE n.name = $name
        RETURN n.name AS name
        """)
    .bind(label).to("label")
    .bind(name).to("name")
    .fetchAs(String.class)
    .mappedBy((typeSystem, record) -> record.get("name").asString())
    .all();
```

Không phải mọi môi trường Neo4j đều có cùng khả năng dynamic label/type. Nếu ứng dụng phải hỗ trợ server cũ hơn, hãy chọn một trong các phương án có kiểm soát được trình bày ở phần tiếp theo.

## 5. Tên property và truy cập property động

Tên property viết trực tiếp trong biểu thức như `n.email` là một phần cấu trúc truy vấn. Nếu tên property cần thay đổi theo đầu vào, không thể dùng cách viết `n.$propertyName` như một placeholder thông thường.

Cypher hỗ trợ truy cập property động bằng dấu ngoặc vuông:

```cypher
MATCH (n:Person)
WHERE n[$propertyKey] = $value
RETURN n;
```

Ở đây `$propertyKey` cung cấp tên property cần đọc và `$value` cung cấp giá trị so sánh. Khi cần cập nhật một property động, cú pháp tương ứng có thể được dùng trong `SET`:

```cypher
MATCH (n:Person {id: $id})
SET n[$propertyKey] = $value
RETURN n;
```

Ví dụ này vẫn cần giới hạn các key được phép sửa theo nghiệp vụ. Không nên cho client tùy ý cập nhật mọi property trên node chỉ vì Cypher có thể truy cập key động.

## 6. Tham số map và danh sách giá trị

Tham số có thể mang map hoặc danh sách, không chỉ giá trị scalar. Ví dụ tạo node với một map property:

```cypher
CREATE (p:Person $properties)
RETURN p;
```

Tham số `$properties` có thể chứa các cặp key/value như `name`, `email` và `active`. Label `Person` vẫn được viết tường minh trong pattern. Với một tập giá trị cần so khớp, dùng `IN`:

```cypher
MATCH (p:Person)
WHERE p.email IN $emails
RETURN p;
```

Ứng dụng truyền `$emails` dưới dạng danh sách, chẳng hạn `List<String>`. Hãy xác thực nội dung map và danh sách ở tầng ứng dụng để tránh ghi các field ngoài phạm vi hoặc truy vấn với tập dữ liệu đầu vào quá lớn.

## 7. Những thành phần cấu trúc cần xử lý riêng

| Thành phần | Ví dụ viết cố định | Cách xử lý khi cần động |
|---|---|---|
| Giá trị property | `p.email = $email` | Bind tham số giá trị bình thường |
| Danh sách giá trị | `p.status IN $statuses` | Bind list hoặc collection |
| Map property khi tạo node | `CREATE (p:Person $properties)` | Bind map đã được kiểm tra |
| Label node | `MATCH (n:Person)` | Dùng dynamic label `:$(...)` nếu phiên bản hỗ trợ; nếu không, chọn từ allow-list và tạo query theo lựa chọn đã kiểm tra |
| Relationship type | `MATCH (a)-[:KNOWS]->(b)` | Dùng dynamic type `:$(...)` nếu phiên bản hỗ trợ; nếu không, chọn từ allow-list |
| Property key | `p.email` | Dùng truy cập động `p[$propertyKey]` khi phù hợp, đồng thời giới hạn key |
| Từ khóa và cấu trúc truy vấn | `ORDER BY p.name DESC` | Không bind token cú pháp; chọn cấu trúc từ các nhánh truy vấn được định nghĩa trước hoặc dùng API sort có kiểm soát |

Một nguyên tắc thực tế: tham số hóa dữ liệu, còn cấu trúc truy vấn phải nằm trong tập lựa chọn mà ứng dụng kiểm soát. Dynamic syntax là ngoại lệ có cú pháp riêng được Neo4j hỗ trợ; nó không biến mọi phần của Cypher thành placeholder tùy ý.

## 8. Xây dựng query động an toàn trên server cũ

Nếu phiên bản Neo4j chưa hỗ trợ dynamic label/type ở vị trí cần dùng, hãy tạo các nhánh truy vấn cố định theo danh sách cho phép. Ví dụ:

```java
String query = switch (entityKind) {
    case "person" -> "MATCH (n:Person) WHERE n.email = $value RETURN n.name AS name";
    case "company" -> "MATCH (n:Company) WHERE n.domain = $value RETURN n.name AS name";
    default -> throw new IllegalArgumentException("Unsupported entity kind");
};

return neo4jClient.query(query)
    .bind(value).to("value")
    .fetchAs(String.class)
    .mappedBy((typeSystem, record) -> record.get("name").asString())
    .all();
```

`entityKind` được đối chiếu với allow-list thông qua `switch`; chuỗi query chỉ được chọn từ các mẫu do ứng dụng định nghĩa. Giá trị `$value` vẫn được bind riêng. Không nối trực tiếp một label, relationship type hoặc đoạn Cypher do người dùng gửi vào query.

Nếu có nhiều biến thể, có thể dùng enum thay cho chuỗi tự do:

```java
enum EntityKind {
    PERSON,
    COMPANY
}
```

Enum giúp giới hạn đầu vào ở một tập lựa chọn hợp lệ. Tương tự, sort field và sort direction nên được ánh xạ từ enum hoặc allow-list thay vì lấy nguyên văn từ request.

## 9. Rủi ro bảo mật khi nối chuỗi Cypher

Nối chuỗi đầu vào vào query có thể khiến dữ liệu bị diễn giải thành cú pháp. Ví dụ không an toàn:

```java
String query = "MATCH (p:Person) WHERE p.email = '" + email + "' RETURN p";
```

Nếu `email` chứa dấu nháy và phần Cypher bổ sung, cấu trúc truy vấn có thể bị thay đổi. Cách đúng là dùng tham số:

```java
String query = "MATCH (p:Person) WHERE p.email = $email RETURN p";

return neo4jClient.query(query)
    .bind(email).to("email")
    .fetch().all();
```

Với label/type động, cú pháp `$(...)` được hỗ trợ có thể tránh phải nối identifier vào query, nhưng ứng dụng vẫn cần allow-list theo quyền nghiệp vụ. Người dùng không nên được phép chọn tùy ý label hoặc relationship type chỉ vì tham số đã được bind.

## 10. Hiệu năng và khả năng sử dụng index

Truy vấn có label hoặc relationship type cố định giúp planner nhận diện cấu trúc rõ ràng và có thể tận dụng index tương ứng. Dynamic label/type có thể làm thay đổi cách planner lập kế hoạch hoặc khả năng tận dụng index tùy phiên bản Neo4j. Vì vậy:

- Dùng label và relationship type cố định khi nghiệp vụ không cần thay đổi chúng.
- Chỉ dùng dynamic label/type khi yêu cầu thực sự cần và server hỗ trợ.
- Kiểm tra kế hoạch với `EXPLAIN` hoặc `PROFILE` trên phiên bản Neo4j đang chạy.
- Đo hiệu năng với dữ liệu đại diện, không suy luận chỉ từ việc query có bind tham số.
- Với query động theo nhiều dạng entity, so sánh một query dynamic với các query cố định được chọn từ allow-list.

Parameterization cải thiện an toàn và khả năng tái sử dụng query; nó không tự đảm bảo truy vấn nhanh. Index vẫn phải phù hợp với label và property được truy vấn.

## 11. Những lỗi thường gặp

| Lỗi | Nguyên nhân | Cách xử lý |
|---|---|---|
| Viết `MATCH (n:$label)` | Dùng placeholder giá trị tại vị trí cú pháp label | Dùng `:$(...)` nếu Neo4j hỗ trợ hoặc chọn query từ allow-list |
| Viết `[r:$type]` cho relationship type | Nhầm tham số thường với token cấu trúc | Dùng dynamic relationship type có cú pháp được hỗ trợ hoặc query cố định |
| Nối email hoặc tên vào chuỗi Cypher | Không bind giá trị đầu vào | Dùng `$parameter` và `.bind(...).to(...)` hoặc `@Param` |
| Dùng raw input làm label/type | Có thể tạo cấu trúc truy vấn ngoài phạm vi nghiệp vụ | Kiểm tra allow-list hoặc enum |
| Dùng dynamic syntax trên server không hỗ trợ | Cú pháp không tương thích phiên bản | Kiểm tra phiên bản Neo4j/Cypher và chọn query cố định nếu cần |
| Cho phép dynamic property key không giới hạn | Có thể sửa nhầm property nhạy cảm hoặc field hệ thống | Chỉ cho phép các key nằm trong allow-list |
| Cho rằng bind parameter làm query luôn nhanh | Parameterization không thay thế index và query planning | Dùng `EXPLAIN`/`PROFILE` để đánh giá |

## 12. Tự kiểm tra

1. Vì sao `$email` có thể dùng làm giá trị điều kiện nhưng `$label` không thể mặc định thay thế label trong `MATCH`?
2. Cú pháp `:$(...)` giải quyết trường hợp dynamic label/type như thế nào?
3. Khi nào nên dùng `n[$propertyKey]` thay cho `n.propertyName`?
4. Nếu phải hỗ trợ Neo4j chưa có dynamic label/type, làm sao tạo query động an toàn?
5. Vì sao không nên nối trực tiếp dữ liệu người dùng vào chuỗi Cypher?
6. Parameterization có tự đảm bảo query tận dụng index và chạy nhanh không?

Hãy nhớ phân biệt dữ liệu đầu vào với cấu trúc của truy vấn. Bind giá trị bằng tham số Cypher; dùng dynamic syntax chỉ khi server hỗ trợ và có kiểm soát; còn những lựa chọn cấu trúc khác cần được giới hạn trong các mẫu query do ứng dụng quản lý.
