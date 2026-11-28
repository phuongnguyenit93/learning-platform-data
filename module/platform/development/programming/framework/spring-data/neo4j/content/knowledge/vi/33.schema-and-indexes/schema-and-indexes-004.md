# Phân biệt khai báo @Id với tạo constraint trong cơ sở dữ liệu

Trong Spring Data Neo4j, một entity cần có trường định danh để framework biết node nào tương ứng với object Java. Annotation `@Id` khai báo trường đó trong mô hình ánh xạ. Tuy nhiên, việc đánh dấu một property bằng `@Id` **không tự tạo uniqueness constraint trong Neo4j** và cũng không ngăn một client khác ghi node trùng giá trị.

Muốn database bảo vệ tính duy nhất, cần tạo constraint ở cấp schema bằng Cypher hoặc công cụ migration. Hai việc này giải quyết hai trách nhiệm khác nhau: `@Id` định nghĩa identity trong Java/SDN; constraint thực thi quy tắc dữ liệu cho mọi thao tác ghi vào database, kể cả từ ứng dụng khác.

## 1. @Id là metadata ánh xạ của entity

`@Id` thuộc package `org.springframework.data.neo4j.core.schema`. Nó đánh dấu property được Spring Data Neo4j sử dụng làm định danh của entity:

```java
import org.springframework.data.neo4j.core.schema.Id;
import org.springframework.data.neo4j.core.schema.Node;

@Node("Person")
public class Person {

    @Id
    private String personId;

    private String name;
    private String email;
}
```

Khi repository khai báo:

```java
import org.springframework.data.neo4j.repository.Neo4jRepository;

public interface PersonRepository extends Neo4jRepository<Person, String> {
}
```

kiểu ID `String` tương ứng với property `personId` được đánh dấu `@Id`. SDN dùng identity này để thực hiện các thao tác như `findById`, xác định entity và đồng bộ object graph.

`@Id` không phải câu lệnh DDL. Nó không tự tạo constraint, index hoặc quy tắc `UNIQUE` trong Neo4j. Nếu hai node `Person` có cùng `personId`, database vẫn có thể chứa cả hai khi chưa có constraint phù hợp.

## 2. Constraint là quy tắc được database thực thi

Constraint được khai báo trong Neo4j schema bằng Cypher. Ví dụ, để mỗi node `Person` có `personId` duy nhất:

```cypher
CREATE CONSTRAINT person_id_unique IF NOT EXISTS
FOR (p:Person)
REQUIRE p.personId IS UNIQUE;
```

Constraint này yêu cầu giá trị `personId` không bị trùng giữa các node mang label `Person`. Sau khi constraint được tạo, mọi thao tác ghi từ Spring Data Neo4j, Neo4j Browser, một service khác hoặc Neo4j Driver đều phải tuân thủ quy tắc đó.

Nếu một transaction cố tạo node `Person` có `personId` đã tồn tại, Neo4j từ chối thao tác và trả lỗi constraint violation. Transaction chứa thao tác ghi đó sẽ không thể commit thành công.

Phạm vi constraint được xác định bởi label và property. Constraint `:Person(personId)` không tự áp dụng cho node `Customer` hoặc `Employee`, dù chúng cũng có property cùng tên.

Nếu entity đổi tên property trong database bằng `@Property`, constraint phải tham chiếu tên property thực tế được lưu. Ví dụ:

```java
@Id
@Property("person_id")
private String personId;
```

thì Cypher constraint dùng `p.person_id`:

```cypher
CREATE CONSTRAINT person_id_unique IF NOT EXISTS
FOR (p:Person)
REQUIRE p.person_id IS UNIQUE;
```

## 3. Kết hợp @Id với uniqueness constraint

Với business ID do ứng dụng cấp, thường nên dùng cả mapping identity và constraint database:

```java
import org.springframework.data.annotation.Version;
import org.springframework.data.neo4j.core.schema.Id;
import org.springframework.data.neo4j.core.schema.Node;

@Node("Person")
public class Person {

    @Id
    private String personId;

    @Version
    private Long version;

    private String name;
    private String email;
}
```

`@Id` cho SDN biết property định danh. `@Version` giúp SDN nhận diện trạng thái mới/đã lưu với assigned ID và hỗ trợ optimistic locking. Constraint được tạo riêng trong database:

```cypher
CREATE CONSTRAINT person_id_unique IF NOT EXISTS
FOR (p:Person)
REQUIRE p.personId IS UNIQUE;
```

Ba thành phần không thay thế nhau:

| Thành phần | Trách nhiệm |
|---|---|
| `@Id` | Chỉ định property identity trong mô hình entity của SDN |
| `@Version` | Theo dõi version khi SDN lưu entity và phát hiện cập nhật cạnh tranh |
| `IS UNIQUE` constraint | Ngăn database lưu các node cùng label có giá trị property trùng nhau |

Với entity dùng assigned ID, để `version` là `null` trên object mới và để SDN quản lý giá trị sau khi lưu. Không tự tăng version trong service. Constraint cần tồn tại độc lập với annotation trên entity.

## 4. @Id với ID được sinh tự động

Nếu không muốn ứng dụng tự cấp ID, có thể dùng `@GeneratedValue` cùng `@Id`:

```java
import org.springframework.data.neo4j.core.schema.GeneratedValue;
import org.springframework.data.neo4j.core.schema.Id;
import org.springframework.data.neo4j.core.schema.Node;

@Node("Person")
public class Person {

    @Id
    @GeneratedValue
    private Long id;

    private String externalCode;
    private String email;
}
```

`@GeneratedValue` yêu cầu SDN cung cấp giá trị định danh theo generator được cấu hình. Nó không tạo uniqueness constraint cho `externalCode` hoặc `email`. Nếu nghiệp vụ yêu cầu email duy nhất, vẫn cần constraint riêng:

```cypher
CREATE CONSTRAINT person_email_unique IF NOT EXISTS
FOR (p:Person)
REQUIRE p.email IS UNIQUE;
```

ID kỹ thuật được sinh tự động và business key là hai khái niệm khác nhau. Nếu API hoặc hệ thống tích hợp cần một mã ổn định như `externalCode`, hãy lưu nó thành property riêng và bảo vệ bằng constraint tương ứng khi yêu cầu nghiệp vụ đòi hỏi duy nhất.

## 5. Uniqueness constraint không phải quy tắc bắt buộc property tồn tại

Một uniqueness constraint bảo đảm các giá trị đã có không trùng nhau. Nó không tự yêu cầu mọi node mang label đó phải có property.

Ví dụ:

```cypher
CREATE CONSTRAINT person_email_unique IF NOT EXISTS
FOR (p:Person)
REQUIRE p.email IS UNIQUE;
```

Constraint này ngăn hai node `Person` có cùng giá trị `email`. Nhưng node không có property `email` vẫn có thể tồn tại; uniqueness constraint không đồng nghĩa với `NOT NULL`.

Nếu email là trường bắt buộc, cần bổ sung quy tắc tồn tại. Ví dụ với phiên bản/edition Neo4j hỗ trợ property existence constraint:

```cypher
CREATE CONSTRAINT person_email_required IF NOT EXISTS
FOR (p:Person)
REQUIRE p.email IS NOT NULL;
```

Property existence constraint và node key constraint có yêu cầu hỗ trợ theo edition của Neo4j; hãy xác nhận khả năng trên cụm database đang triển khai. Trong môi trường không hỗ trợ loại constraint đó, cần kiểm tra ở tầng ứng dụng và cân nhắc quy tắc triển khai phù hợp. Validation trong Java không thay thế được constraint database nếu dữ liệu còn có thể được ghi từ client khác.

## 6. Constraint duy nhất trên nhiều property

Một số quy tắc nghiệp vụ chỉ yêu cầu duy nhất theo tổ hợp nhiều trường. Ví dụ, mã đơn hàng chỉ duy nhất trong phạm vi từng tenant; hai tenant khác nhau có thể dùng cùng `externalOrderId`.

Có thể tạo composite uniqueness constraint:

```cypher
CREATE CONSTRAINT order_tenant_external_id_unique IF NOT EXISTS
FOR (o:Order)
REQUIRE (o.tenantId, o.externalOrderId) IS UNIQUE;
```

Constraint này kiểm tra tổ hợp `(tenantId, externalOrderId)`. Nó cho phép cùng `externalOrderId` xuất hiện ở hai tenant khác nhau, nhưng không cho hai node `Order` cùng tenant có cùng mã ngoài.

Composite constraint không có nghĩa entity SDN tự động có composite `@Id`. `@Id` vẫn đánh dấu property identity theo mô hình entity. Nếu muốn SDN dùng một business ID duy nhất, ứng dụng có thể định nghĩa ID phù hợp; constraint tổ hợp vẫn có thể được dùng như quy tắc bổ sung ở database.

Với constraint tổ hợp, cần bảo đảm các property tham gia có giá trị theo yêu cầu nghiệp vụ. Uniqueness constraint không tự thay thế quy tắc bắt buộc tồn tại của từng property.

## 7. Phân biệt uniqueness constraint và index

Index và constraint có mục tiêu khác nhau:

| Cơ chế | Mục tiêu | Có ngăn dữ liệu trùng? |
|---|---|---|
| Range index | Tăng tốc truy vấn lọc, tìm kiếm hoặc sắp xếp theo property phù hợp | Không |
| Uniqueness constraint | Bảo đảm giá trị hoặc tổ hợp property không trùng trong phạm vi label/type | Có |
| Property existence constraint | Bắt buộc property tồn tại trên entity thuộc phạm vi constraint | Không tự bảo đảm uniqueness |
| Node key constraint | Kết hợp tính tồn tại và duy nhất của một hoặc nhiều property trên node | Có |

Neo4j sử dụng range index để hỗ trợ uniqueness constraint; index backing constraint được quản lý cùng constraint. Không cần tạo thêm một range index trùng đúng cùng schema chỉ để thực hiện lại công việc của uniqueness constraint.

Nếu chỉ cần tăng tốc truy vấn theo `name` mà cho phép nhiều người trùng tên, tạo index:

```cypher
CREATE INDEX person_name_index IF NOT EXISTS
FOR (p:Person)
ON (p.name);
```

Nếu `email` phải duy nhất, tạo constraint:

```cypher
CREATE CONSTRAINT person_email_unique IF NOT EXISTS
FOR (p:Person)
REQUIRE p.email IS UNIQUE;
```

Không dùng index thường thay cho constraint. Query có thể nhanh hơn nhưng database vẫn chấp nhận các giá trị trùng.

## 8. Constraint chỉ áp dụng cho label/type được khai báo

Constraint được giới hạn theo label của node hoặc relationship type. Ví dụ:

```cypher
CREATE CONSTRAINT person_email_unique IF NOT EXISTS
FOR (p:Person)
REQUIRE p.email IS UNIQUE;
```

Một node có nhiều label, ví dụ `:Person:Customer`, vẫn thuộc phạm vi `:Person` và chịu constraint này. Một node chỉ có label `:Customer` thì không thuộc phạm vi đó.

Điều này quan trọng khi thiết kế label inheritance hoặc nhiều loại entity cùng dùng một property name. Nếu cần email duy nhất trên toàn bộ nhóm node có nhiều label khác nhau, một constraint theo một label đơn lẻ không tự tạo phạm vi toàn cục. Hãy chọn mô hình label chung hoặc một cơ chế định danh phù hợp để biểu diễn chính xác phạm vi uniqueness.

## 9. Tạo constraint trong migration hoặc quy trình triển khai schema

Không nên phụ thuộc vào thao tác lưu entity đầu tiên để tạo constraint. Constraint là schema của database, nên được quản lý như một thay đổi có phiên bản.

Ví dụ một migration Cypher:

```cypher
// V001__person_constraints.cypher
CREATE CONSTRAINT person_id_unique IF NOT EXISTS
FOR (p:Person)
REQUIRE p.personId IS UNIQUE;

CREATE CONSTRAINT person_email_unique IF NOT EXISTS
FOR (p:Person)
REQUIRE p.email IS UNIQUE;
```

Có thể chạy migration bằng công cụ quản lý schema mà dự án lựa chọn hoặc trong bước triển khai database được kiểm soát. Mỗi môi trường cần áp dụng cùng phiên bản schema để ứng dụng hoạt động nhất quán.

Trước khi tạo constraint trên dữ liệu đang tồn tại, cần kiểm tra duplicate và giá trị thiếu:

```cypher
MATCH (p:Person)
WHERE p.personId IS NOT NULL
WITH p.personId AS personId, count(*) AS occurrences
WHERE occurrences > 1
RETURN personId, occurrences
ORDER BY occurrences DESC;
```

Kiểm tra các node chưa có ID:

```cypher
MATCH (p:Person)
WHERE p.personId IS NULL
RETURN count(p) AS peopleWithoutId;
```

Nếu dữ liệu vi phạm uniqueness, Neo4j không thể tạo constraint thành công. Cần làm sạch hoặc hợp nhất dữ liệu trùng theo quy tắc nghiệp vụ trước khi áp dụng migration. Không xóa node trùng tự động nếu chưa xác định cách bảo toàn relationship và dữ liệu phụ thuộc.

## 10. Kiểm tra constraint và index hiện có

Sau khi migration chạy, có thể kiểm tra schema bằng lệnh:

```cypher
SHOW CONSTRAINTS;
```

Hoặc xem các index:

```cypher
SHOW INDEXES;
```

Để kiểm tra constraint cụ thể theo tên:

```cypher
SHOW CONSTRAINTS
YIELD name, type, entityType, labelsOrTypes, properties
WHERE name = 'person_id_unique'
RETURN name, type, entityType, labelsOrTypes, properties;
```

Các lệnh `SHOW` giúp xác nhận schema đã được áp dụng ở đúng database. Trong môi trường có nhiều database, hãy chắc chắn lệnh migration và lệnh kiểm tra đang chạy trên database mà ứng dụng Spring Data Neo4j sử dụng.

## 11. Gỡ hoặc thay đổi constraint

Nếu cần thay đổi định nghĩa constraint, hãy tạo migration mới có kiểm soát. Có thể gỡ constraint theo tên:

```cypher
DROP CONSTRAINT person_email_unique IF EXISTS;
```

Sau đó tạo lại với định nghĩa mới. Việc gỡ constraint tạm thời làm database không còn bảo vệ quy tắc uniqueness tương ứng; chỉ thực hiện trong quy trình triển khai đã đánh giá ảnh hưởng và có bước tạo lại phù hợp.

Không xóa index backing của uniqueness constraint như thể đó là một index độc lập. Quản lý constraint qua tên constraint; Neo4j sẽ quản lý index hỗ trợ constraint.

## 12. Tình huống thực tế: ID ứng dụng và email duy nhất

Một ứng dụng có thể dùng `personId` làm identity nội bộ của entity và `email` làm business key dùng để đăng nhập. Mô hình Java:

```java
import org.springframework.data.annotation.Version;
import org.springframework.data.neo4j.core.schema.Id;
import org.springframework.data.neo4j.core.schema.Node;

@Node("Person")
public class Person {

    @Id
    private String personId;

    @Version
    private Long version;

    private String email;
    private String displayName;
}
```

Schema database:

```cypher
CREATE CONSTRAINT person_id_unique IF NOT EXISTS
FOR (p:Person)
REQUIRE p.personId IS UNIQUE;

CREATE CONSTRAINT person_email_unique IF NOT EXISTS
FOR (p:Person)
REQUIRE p.email IS UNIQUE;
```

Trong mô hình này:

- `personId` là identity mà repository dùng qua `@Id`.
- `version` được SDN quản lý để nhận diện entity mới và kiểm soát cập nhật cạnh tranh.
- `email` là business key có uniqueness constraint riêng.
- `displayName` có thể trùng giữa nhiều người và không cần constraint uniqueness.

Nếu hệ thống cho phép thay đổi email, constraint vẫn bảo vệ tính duy nhất trong suốt quá trình cập nhật. Nếu hai request đồng thời đặt cùng email cho hai người khác nhau, database chỉ cho một thao tác thành công; thao tác còn lại nhận lỗi constraint violation.

## 13. Xử lý lỗi khi vi phạm constraint

Khi database từ chối một thao tác do uniqueness constraint, Spring Data Neo4j chuyển lỗi Driver thành hệ thống exception truy cập dữ liệu của Spring. Ứng dụng nên xử lý theo ý nghĩa nghiệp vụ, chẳng hạn email đã được sử dụng.

Không nên chỉ bắt mọi `DataAccessException` rồi trả về thông báo “ID trùng”, vì exception có thể xuất phát từ constraint khác, lỗi kết nối hoặc lỗi truy vấn. Hãy phân loại nguyên nhân cụ thể theo Neo4j error code/constraint name ở tầng adapter phù hợp, sau đó chuyển thành exception nghiệp vụ rõ ràng.

Ví dụ ở tầng API, lỗi email đã tồn tại có thể được chuyển thành HTTP `409 Conflict`. Không trả nguyên thông báo nội bộ hoặc stack trace từ Neo4j cho client. Nếu constraint violation xảy ra trong transaction nhiều bước, transaction đó cần được rollback; không tiếp tục các thao tác phụ thuộc vào lần ghi đã thất bại.

## 14. Lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Hai node có cùng giá trị `@Id` vẫn được ghi | Chỉ khai báo `@Id`, chưa có uniqueness constraint trong database | Tạo constraint `IS UNIQUE` trên label và property tương ứng. |
| Nghĩ `@GeneratedValue` tạo constraint cho email | Generator chỉ cấp identity cho field được đánh dấu | Tạo constraint riêng cho business key cần duy nhất. |
| Tạo constraint thất bại | Dữ liệu hiện có đã chứa giá trị trùng | Tìm duplicate, xử lý dữ liệu rồi chạy lại migration. |
| Vẫn tạo được node thiếu email | Uniqueness constraint không bắt buộc property tồn tại | Dùng property existence hoặc node key constraint nếu edition hỗ trợ; đồng thời validate ở service. |
| Tạo index nhưng dữ liệu vẫn trùng | Index thường chỉ hỗ trợ truy vấn, không kiểm tra uniqueness | Dùng uniqueness constraint. |
| Constraint không ảnh hưởng node label khác | Constraint chỉ áp dụng label/type được khai báo | Thiết kế label chung hoặc constraint đúng phạm vi dữ liệu. |
| Môi trường dev có constraint nhưng production không có | Schema không được quản lý bằng migration nhất quán | Áp dụng migration có phiên bản cho mọi database/môi trường. |
| Tạo range index trùng với constraint backing index | Không phân biệt index thường và index hỗ trợ uniqueness constraint | Kiểm tra `SHOW INDEXES` và tránh tạo index dư thừa. |

## 15. Quy trình triển khai @Id và constraint

1. Chọn identity cho entity: assigned business ID hoặc generated ID.
2. Đánh dấu property identity bằng `@Id`; dùng `@GeneratedValue` nếu ID do SDN sinh.
3. Với assigned ID, khai báo `@Version Long` và để SDN quản lý version.
4. Liệt kê các business key cần duy nhất, ví dụ email, mã đơn hàng hoặc mã ngoài.
5. Tạo uniqueness constraint bằng Cypher trong migration schema.
6. Nếu property bắt buộc phải có, bổ sung existence/node key constraint khi edition hỗ trợ và validation ở tầng ứng dụng.
7. Kiểm tra duplicate và dữ liệu thiếu trước khi tạo constraint trên database hiện hữu.
8. Dùng `SHOW CONSTRAINTS` và `SHOW INDEXES` để xác minh schema đã được triển khai.
9. Kiểm thử hai thao tác ghi cùng một business key và xác nhận chỉ một thao tác thành công.
10. Xử lý constraint violation thành lỗi nghiệp vụ phù hợp ở API/service boundary.

## 16. Ghi nhớ

`@Id` là metadata của Spring Data Neo4j, dùng để xác định property identity của entity trong mô hình Java. Nó không tự tạo uniqueness constraint và không bảo vệ database khỏi dữ liệu trùng. `@GeneratedValue` cũng chỉ giải quyết việc cấp ID cho field được đánh dấu; nó không tự làm cho các business key khác trở nên duy nhất.

Muốn Neo4j thực thi tính duy nhất, hãy tạo constraint như `CREATE CONSTRAINT ... REQUIRE n.property IS UNIQUE`. Constraint được áp dụng theo label/type và property; uniqueness không mặc nhiên yêu cầu property tồn tại. Index thường chỉ tăng tốc truy vấn, còn uniqueness constraint vừa bảo vệ dữ liệu vừa có index hỗ trợ. Hãy quản lý constraint bằng migration có phiên bản, kiểm tra dữ liệu cũ trước khi tạo và xác minh bằng `SHOW CONSTRAINTS` để mọi môi trường có cùng schema.

## Tài liệu tham khảo

- [Spring Data Neo4j – Mapping IDs](https://docs.spring.io/spring-data/neo4j/reference/object-mapping/mapping-ids.html)
- [Spring Data Neo4j – Metadata-based Mapping](https://docs.spring.io/spring-data/neo4j/reference/object-mapping/metadata-based-mapping.html)
- [Neo4j Manual – Constraints](https://neo4j.com/docs/cypher-manual/current/schema/constraints/)
- [Neo4j Manual – Indexes](https://neo4j.com/docs/cypher-manual/current/indexes/)
